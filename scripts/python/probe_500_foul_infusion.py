#!/usr/bin/env python
"""probe #500 -- `FoulInfusion` (1038) CONFRONTEE au natif, etage par etage.

CE QUI EST MESURE
-----------------
Avant #500 l'ability etait un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, donc la decision
la choisissait et l'execution l'ignorait -- 0 effet, 0 degat, AUCUNE erreur. Le probe monte UN etat
discriminant, PREND une capture (`decisionView`/`observeBattle`/`combatSnapshot`/`boardGraph`/
`tileMeta` + `dumpRng`), REJOUE le cast hors-ligne sur cette capture, puis lance le cast NATIF sur
le MEME runner -- et confronte QUATRE etages, pas un scalaire :

  E1 QUI est buffe   -- l'ensemble des porteurs de l'effet 0x432 = 1074 `FoulInfusion_ExtraHits` ;
  E2 QUI est frappe  -- la cible tiree par `PickRandomly(Attackable(AdjacentEnemies(Caster)), 1)` ;
  E3 COMBIEN         -- le total inflige, arme + le coup additionnel `Toxic` que le buff ajoute ;
  E4 la SEQUENCE     -- le buff est pose AVANT l'attaque, donc l'attaque LIBRE du cast en beneficie.

MONTAGE (board `MC1_67`, seed 500) -- CHAQUE unite y sert a discriminer UNE lecture
------------------------------------------------------------------------------------
    deathPutrifier   (5,5)   le caster (`Pestillian`, HERO du pool, trait `ContagionsOfNurgle`)
    deathBlightlord  (5,6)   allie CHAOS a distance 1   -> DOIT etre buffe
    deathRotbone     (5,7)   allie CHAOS a distance 2   -> ne doit PAS l'etre (rayon d'aura = 1 au
                             tour 1 : `GetRangeOnOwnerTurn(TurnsStarted)`)
    ultraApothecary  (6,5)   allie NON-Chaos a distance 1 -> ne doit PAS l'etre (`UnitsWithTrait`)
    necroWarden      (4,5)   ennemi ADJACENT
    orksNob          (5,4)   ennemi ADJACENT            -> pool de DEUX, donc le tirage discrimine

`--hp-target 400000` : sans lui la cible MEURT et l'accord `hp == 0` ne discrimine RIEN sur le
montant (mesure : le premier montage tuait la cible, 7873 de degat pour 7029 PV).

LES CINQ CONTRE-EPREUVES (`--ab`) -- toutes DISCRIMINANTES, mesurees le 2026-08-07
----------------------------------------------------------------------------------
Un accord ne vaut que si le desaccord etait possible. Chaque variante ne change QU'UNE lecture du
mirror, et chacune s'ecarte du natif :

    REF   mirror                            buffs {77,79}      frappe 85   total 13847  == NATIF
    AB1   sans `scale_from_source`          buffs {77,79}      frappe 85   total  9701  (coup
          (l'`AbilityStateReference` natif)                                 additionnel 42 au lieu
                                                                            de 4188)
    AB2   ordre INVERSE (attaque, puis buff) buffs {77,79}     frappe 85   total  9659  (AUCUN
                                                                            coup additionnel)
    AB3   sans `UnitsWithTrait(Chaos)`      buffs {77,79,83}   frappe 85   total 13847
    AB4   rayon CONSTANT 2 (pas la formule) buffs {77,79,81}   frappe 85   total 13847
    AB5   sans le tirage `PickRandomly`     buffs {77,79}      frappe 87   total  6782

⚠ AB2 est celle qui compte : le NOMBRE de coups d'arme y est IDENTIQUE au mirror, seule la
SEQUENCE change. Un critere sur le compte de coups serait reste VERT.

Usage (depuis `scripts/python`, ASCII only) :
    python probe_500_foul_infusion.py            # montage + capture + rejeu + cast natif
    python probe_500_foul_infusion.py --ab       # + les cinq contre-epreuves hors-ligne
    python probe_500_foul_infusion.py --keep     # ne dispose PAS le runner
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

HOST = "http://127.0.0.1:8765"
PYDIR = os.path.dirname(os.path.abspath(__file__))

FOUL_INFUSION = 1038                       # `ActiveAbilityType.FoulInfusion`
EXTRA_HITS = 1074                          # `EffectType.FoulInfusion_ExtraHits` (0x432)

CASTER = "deathPutrifier"                  # `Pestillian` -- seul porteur LINEUP de 1038
ALLY_CHAOS_NEAR = "deathBlightlord"        # Chaos, distance 1  -> buffe
ALLY_CHAOS_FAR = "deathRotbone"            # Chaos, distance 2  -> HORS aura au tour 1
ALLY_PLAIN = "ultraApothecary"             # non-Chaos, distance 1 -> filtre par UnitsWithTrait
FOE_A = "necroWarden"
FOE_B = "orksNob"

BOARD = "MC1_67"
SEED = 500
#: Les six tuiles du montage. `(5,5)` a pour voisins hex (4,4) (4,5) (5,4) (5,6) (6,4) (6,5) --
#: donc `deathRotbone` en (5,7) est a distance 2, et les DEUX ennemis sont adjacents.
PLACES = ((CASTER, "5,5"), (ALLY_CHAOS_NEAR, "5,6"), (ALLY_CHAOS_FAR, "5,7"), (ALLY_PLAIN, "6,5"))
A_PLACES = ((FOE_A, "4,5"), (FOE_B, "5,4"))


# ------------------------------------------------------------------ transport

def _sid():
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))["session"]["id"]


def _rpc(sid, method, body=None, timeout=120):
    payload = json.dumps({"method": method,
                          "args": [body] if body is not None else []}).encode("utf-8")
    req = urllib.request.Request("%s/api/scripts/%s/rpc" % (HOST, sid), data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode("utf-8"))
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _duel(args, timeout=400):
    p = subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=PYDIR,
                       capture_output=True, text=True, timeout=timeout)
    return p


# ------------------------------------------------------------------ montage

def build(state_file: str):
    """Monte le runner du montage ci-dessus. Rend `runnerId`, ou `None` si le build echoue."""
    argv = ["build", "--seed", str(SEED), "--board", BOARD, "--hp-target", "400000",
            "--p-units", ",".join(v for v, _t in PLACES),
            "--a-units", ",".join(v for v, _t in A_PLACES),
            "--state-file", state_file]
    for vid, tile in PLACES:
        argv += ["--place", "%s:%s" % (vid, tile)]
    for vid, tile in A_PLACES:
        argv += ["--a-place", "%s:%s" % (vid, tile)]
    p = _duel(argv)
    if p.returncode != 0:
        print("[build] rc=%s\n%s\n%s" % (p.returncode, p.stdout[-1200:], p.stderr[-1200:]))
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        return int(json.load(f)["runnerId"])


def unites(sid, rid):
    """{visualId: {'id','pos','hp','effects'}} -- aucun id d'entite en dur."""
    dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = {
            "id": u.get("id"), "pos": (p.get("col"), p.get("row")), "hp": u.get("hp"),
            "effects": [e.get("effectType") for e in (u.get("effects") or [])
                        if isinstance(e, dict)]}
    return out


def capture(sid, rid):
    """L'etat COMPLET juste avant le cast natif -- c'est le substrat du rejeu porte."""
    return {
        "dv": _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150),
        "ob": _rpc(sid, "observeBattle", {"runnerId": rid}, 90),
        "snap": _rpc(sid, "combatSnapshot", {"runnerId": rid}, 120),
        "tm": _rpc(sid, "tileMeta", {"runnerId": rid}, 120),
        "tiles": _rpc(sid, "boardGraph", {"runnerId": rid}, 90)["tiles"],
        "rng": _rpc(sid, "dumpRng", {"runnerId": rid}, 60),
    }


def assert_montage(u):
    """Un montage DEGENERE rendrait l'accord trivial : on echoue AVANT de mesurer, jamais apres."""
    manquants = [v for v in (CASTER, ALLY_CHAOS_NEAR, ALLY_CHAOS_FAR, ALLY_PLAIN, FOE_A, FOE_B)
                 if v not in u]
    if manquants:
        raise SystemExit("montage invalide : unites absentes %r" % (manquants,))
    voulu = dict(PLACES) | dict(A_PLACES)
    mauvais = [(v, u[v]["pos"], voulu[v]) for v in voulu
               if u[v]["pos"] != tuple(int(x) for x in voulu[v].split(","))]
    if mauvais:
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %r" % (mauvais,))


# ------------------------------------------------------------------ rejeu hors-ligne

def etat_porte(cap):
    """`State` charge depuis la capture, PRNG cale sur `dumpRng` (rejeu bit-exact)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state
    board = Board(cap["tiles"], adjacency="native_sym")
    st = load_state(cap["dv"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"])
    d = cap["rng"]
    if isinstance(d, dict) and d.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt, rng.mti = list(d["mt"]), d["mti"]
        st.rng = rng
    return st


def _hp(st, ids):
    from engine.runner.components import HealthComponent
    out = {}
    for i in ids:
        e = st.get_entity(int(i))
        h = e.get_component(HealthComponent) if e is not None else None
        out[int(i)] = None if h is None else h.hp
    return out


def rejeu_porte(cap, caster_id, ids):
    """Rejoue le cast par le CHEMIN COMPLET du moteur (`Runner.apply(ActiveAbilityMessage)`), pas
    par un appel direct a `execute_behaviour` : c'est ce qui exerce le registre `ABILITY_CLASSES`
    et rend `ability_handler.last['ported']` -- l'observable qui distingue le port du NO-OP."""
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner
    st = etat_porte(cap)
    avant = _hp(st, ids)
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=int(caster_id), target_id=int(caster_id),
                                      ability_type=FOUL_INFUSION))
    last = getattr(runner.ability_handler, "last", None) or {}
    apres = _hp(st, ids)
    buffes = set()
    if st.effects is not None:
        for uid in ids:
            for e in (st.effects.by_unit.get(int(uid)) or []):
                if not e.consumed and int(getattr(e, "effect_type", -1)) == EXTRA_HITS:
                    buffes.add(int(uid))
    delta = {i: (avant[i] - apres[i]) for i in avant
             if avant[i] is not None and apres[i] is not None and avant[i] != apres[i]}
    return {"last": last, "buffes": buffes, "delta": delta,
            "detail": (last.get("result") or {})}


# ------------------------------------------------------------------ contre-epreuves

def contre_epreuves(cap, caster_id, ids):
    """Les cinq variantes. Chacune ne change QU'UNE lecture -- si l'une d'elles rendait le MEME
    resultat que le mirror, la lecture correspondante ne serait pas mesuree par ce montage."""
    from engine.dsl.base import TargetsSelector, _units_of, Const
    from engine.dsl.effects import ExecutionContext
    from engine.entities.behaviours import op_add
    from engine.entities.formulas import AuraEffectRange
    from engine.entities.selectors.accessors import Owner
    from engine.entities.selectors.tiles import Caster
    from engine.entities.selectors.units import (AdjacentEnemies, SurroundingFriends, Union,
                                                 UnitsWithTrait, UnitsWithoutTrait)
    from engine.runner.abilities.behaviours.combat import UseActiveAbility
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.runner.abilities.behaviours.effects import AddEffect
    import engine.runner.abilities.loki.foul_infusion as FI

    class _SansTirage(TargetsSelector):
        """`PickRandomly` remplace par « le premier du pool » : AUCUN `genrand_int32` consomme."""
        def __init__(self, src):
            self.src = src

        def select(self, ctx):
            return _units_of(self.src, ctx)[:1]

    def _buff(cible_sel, scale=True):
        return AddEffect(FI.EXTRA_HITS, FI.EXTRA_HITS_NAME, cible_sel, duration_rounds=2,
                         scale_from_source=scale)

    def _atk(sel=None):
        return UseActiveAbility(Caster(), sel if sel is not None
                                else FI.foul_infusion_attack_target())

    variantes = {
        "REF": FI.foul_infusion_tree,
        "AB1_sans_scale": lambda: op_add(_buff(FI.foul_infusion_buff_targets(), scale=False),
                                         _atk()),
        "AB2_ordre_inverse": lambda: op_add(_atk(), _buff(FI.foul_infusion_buff_targets())),
        "AB3_sans_trait_chaos": lambda: op_add(
            _buff(Union(SurroundingFriends(Caster(), AuraEffectRange(Owner(), FI.AURA_EFFECT)),
                        Caster())), _atk()),
        "AB4_rayon_const_2": lambda: op_add(
            _buff(Union(UnitsWithTrait(SurroundingFriends(Caster(), Const(2)), FI.CHAOS),
                        Caster())), _atk()),
        "AB5_sans_tirage": lambda: op_add(
            _buff(FI.foul_infusion_buff_targets()),
            _atk(_SansTirage(UnitsWithoutTrait(AdjacentEnemies(Caster()), FI.STEPPABLE)))),
    }
    out = {}
    for nom, fabrique in variantes.items():
        st = etat_porte(cap)
        avant = _hp(st, ids)
        ectx = ExecutionContext(state=st, rng=st.rng)
        fabrique().execute(entities_from_state(st, int(caster_id), int(caster_id)), ectx)
        apres = _hp(st, ids)
        cible = next((p["target"] for n, p in ectx.emitted if n == "UseActiveAbility"), None)
        out[nom] = {
            "buffes": sorted({p["target"] for n, p in ectx.emitted
                              if n == "AddEffect" and p.get("placed")}),
            "cible": cible,
            "total": sum(avant[i] - apres[i] for i in avant
                         if avant[i] is not None and apres[i] is not None and i != int(caster_id)),
        }
    return out


# ------------------------------------------------------------------ main

def mesure(sid, state_file, avec_ab=False, garder=False):
    """Le montage COMPLET, rendu comme un dict -- c'est le foyer que le test consomme."""
    rid = build(state_file)
    if rid is None:
        return None
    try:
        u = unites(sid, rid)
        assert_montage(u)
        ids = [u[v]["id"] for v in (CASTER, ALLY_CHAOS_NEAR, ALLY_CHAOS_FAR, ALLY_PLAIN,
                                    FOE_A, FOE_B)]
        cid = u[CASTER]["id"]
        cap = capture(sid, rid)
        port = rejeu_porte(cap, cid, ids)
        ab = contre_epreuves(cap, cid, ids) if avec_ab else None
        p = _duel(["act", "ability", "--caster", str(cid), "--ability", str(FOUL_INFUSION),
                   "--target", str(cid), "--state-file", state_file, "--runner", str(rid)])
        apres = unites(sid, rid)
        natif = {
            "buffes": {apres[v]["id"] for v in apres if EXTRA_HITS in (apres[v]["effects"] or [])},
            "delta": {u[v]["id"]: u[v]["hp"] - apres[v]["hp"] for v in u
                      if v in apres and u[v]["hp"] is not None and apres[v]["hp"] is not None
                      and u[v]["hp"] != apres[v]["hp"]},
            "rc": p.returncode,
        }
        return {"rid": rid, "ids": {v: u[v]["id"] for v in u}, "caster": cid,
                "avant": {v: u[v] for v in u}, "port": port, "natif": natif, "ab": ab}
    finally:
        if not garder:
            _duel(["dispose", "--state-file", state_file, "--runner", str(rid)], timeout=120)


def main() -> int:
    ap = argparse.ArgumentParser(description="probe #500 -- FoulInfusion (1038) vs natif")
    ap.add_argument("--ab", action="store_true", help="joue aussi les cinq contre-epreuves")
    ap.add_argument("--keep", action="store_true", help="ne dispose PAS le runner")
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()
    sf = a.state_file or os.path.join(tempfile.gettempdir(), "p500_fi_%d.json" % os.getpid())
    m = mesure(_sid(), sf, avec_ab=a.ab, garder=a.keep)
    if m is None:
        print("[500] build KO -- rien mesure")
        return 99
    ids = m["ids"]
    print("[500] runner=%s caster=u%s" % (m["rid"], m["caster"]))
    print("      unites : " + " ".join("%s=u%s" % (v, i) for v, i in sorted(ids.items())))
    print("  E1 buffes   PORT=%s  NATIF=%s"
          % (sorted(m["port"]["buffes"]), sorted(m["natif"]["buffes"])))
    print("  E3 delta hp PORT=%s  NATIF=%s" % (m["port"]["delta"], m["natif"]["delta"]))
    print("     last    = %r" % (m["port"]["last"].get("ported"),))
    if m["ab"]:
        print("  -- contre-epreuves (hors-ligne, meme capture) --")
        for nom, r in m["ab"].items():
            print("     %-22s buffes=%s cible=%s total=%s"
                  % (nom, r["buffes"], r["cible"], r["total"]))
    accord = (set(m["port"]["buffes"]) == set(m["natif"]["buffes"])
              and m["port"]["delta"] == m["natif"]["delta"])
    print("[500] %s" % ("ACCORD port/natif sur E1+E3" if accord else "DESACCORD"))
    return 0 if accord else 1


if __name__ == "__main__":
    raise SystemExit(main())
