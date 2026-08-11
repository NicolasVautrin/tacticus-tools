"""#907 -- MESURE de `1044 IncendiaryShells` (Black Templars), face EXECUTION : natif vs port.

Ce probe MESURE (il ne garde rien -- c'est le role de `test_907_incendiary_shells_live.py`).

MONTAGE, et pourquoi CE chemin-la. Les deux porteurs de 1044 sont `templNpc2Neophyte` (NPC) et
`templNeophyte` (SUMMON). Le SUMMON N'A AUCUN INVOCATEUR : balayage EXHAUSTIF du gameconfig --
`templNeophyte` n'apparait que dans sa PROPRE entree `units`, aucune ability ne le cite (ni
`unitToSpawn`, ni `unitId`, ni `unitId_2`). La voie « spawner son summoner » n'existe donc pas ici ;
ce n'est pas une commodite, c'est la SEULE voie. Le NPC, lui, arrive par le CHEMIN DE STATS
EXPLICITE (`--explicit-stats`, #419-r1-tr12-r2) : SES stats (`units.npc[id].stats[]` ->
`ActiveAbilityLevel 65`, `AbilityVariablesMultiplierPercentage 200`), SES traits, SES armes.
AUCUNE greffe.
(Contraste : `templInitiate`, le summon de `1053 DevoutPush`, EST invoque -- par
`EnvFactionSummons:BlackTemplars` / `:SpaceWolves`, `nrOfSummons = 3`.)

TROIS volets, et chacun dit ce qu'il DISCRIMINE :

  * `degat`  -- UN cast, SEQUENCE coup par coup natif vs port, sur un `State` dont le MT est cale
    sur `dumpRng`. Puis QUATRE MUTANTS de l'arbre, chacun rejoue sur un `State` RECHARGE du MEME
    instantane : un mutant qui n'ecarte pas la sequence est un temoin AVEUGLE, et il est NOMME.
  * `gate`   -- le masque, confronte cible par cible a l'ORACLE natif `abilityReason`
    (`TargetingQuery$$GetInvalidTargetReason`), sur DEUX geometries : LIBRE (aucun ennemi au
    contact) et MELEE (un ennemi au contact). C'est la seule facon d'exercer
    `forceMeleeTarget = RangedBool.True`, le champ du preset `+0x140` qui ARME le clamp de
    `TargetingQuery$$GetRange` (`v = min(1, v) ; onlyAdjacent = true`).
  * `spawn`  -- lecture des positions de spawn (sert a caler les `--a-place` des deux geometries).

Usage (depuis `scripts/python`) :
    python probe_907_incendiary_shells.py --state-file <ABSOLU propre>            # tout
    python probe_907_incendiary_shells.py --state-file <...> --volet gate
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

import requests

import gameconfig as GC
import hexgeo
import stream_events as SE

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.blacktemplars import (INCENDIARY_SHELLS_ID, INCENDIARY_SHELLS_PROFILE,
                                                   IncendiaryShellsAbility)
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

PYDIR = Path(__file__).resolve().parent
HOST = "http://127.0.0.1:8765"

ABILITY = int(ActiveAbilityType.IncendiaryShells)          # 1044
PORTEUR = "templNpc2Neophyte:45"                           # forme `<unitId>:<palier>`, VERBATIM
PORTEUR_VIS = "templNpc2Neophyte"
ALLIE = "ultraTitus"
ENNEMIS = ("eldarRanger", "astraBullgryn", "darkaCompanion")
BOARD = "MC1_67"
SEED = "999"

#: Geometries, en coordonnees ABSOLUES du board `MC1_67` calees sur le spawn MESURE du porteur
#: (`--volet spawn` : `templNpc2Neophyte` en (1,0), l'allie `ultraTitus` en (0,0)). Le probe
#: RE-MESURE les distances apres build et refuse un montage qui n'a pas le spectre voulu.
GEOMETRIES = {
    # aucun ennemi au contact -> `ShouldApplyRangedInMelee` FAUX -> aucun clamp : d = 2 doit PASSER
    "libre": {ENNEMIS[0]: (1, 2), ENNEMIS[1]: (1, 3), ENNEMIS[2]: (3, 3)},
    # un ennemi au contact -> clamp ARME par `forceMeleeTarget = RangedBool.True` : d = 2 REFUSE
    "melee": {ENNEMIS[0]: (1, 2), ENNEMIS[1]: (1, 3), ENNEMIS[2]: (1, 1)},
}


# ------------------------------------------------------------------------------- transport

def _sid():
    return requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"]


def _rpc(sid, method, body=None, timeout=180):
    r = requests.post(f"{HOST}/api/scripts/{sid}/rpc",
                      json={"method": method, "args": [body] if body is not None else []},
                      timeout=timeout).json()
    return r.get("result", r)


def _build(sid, state_file: str, places: dict | None, armure: int = 0) -> int:
    # ⚠ ORDRE : `--hp-target` met `Armor`/`FixedArmor` a 0 (cf. runner.md) ; `--armor-target` est le
    # pendant qui les repose. Sans armure, le PERCAGE du profil est INERTE -- c'est ce qui rendait le
    # mutant `profile=Physical` AVEUGLE (Flame pierce 25 vs Physical pierce 1, tous deux sans effet
    # sur une armure nulle).
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD, "--no-ai",
           "--state-file", state_file, "--explicit-stats", PORTEUR,
           "--p-units", "%s,%s" % (PORTEUR, ALLIE),
           "--a-units", ",".join(ENNEMIS),
           "--block-target", "0,0", "--hp-target", "400000",
           "--armor-target", str(int(armure))]
    for vis, (c, r) in (places or {}).items():
        cmd += ["--a-place", "%s:%d,%d" % (vis, c, r)]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    Path(state_file).parent.mkdir(parents=True, exist_ok=True)
    if p.returncode != 0 or not Path(state_file).exists():
        raise RuntimeError("build KO rc=%d : %s" % (p.returncode, (p.stderr or p.stdout)[-1500:]))
    return int(json.loads(Path(state_file).read_text(encoding="utf-8"))["runnerId"])


def _pos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def _dist(a, b):
    pa, pb = _pos(a), _pos(b)
    if None in pa or None in pb:
        return None
    return hexgeo.distance(pa, pb)


def _capture(sid, rid):
    """Instantane COMPLET : vue + etat porte + MT cale sur `dumpRng`. Le `State` est reconstruit a
    chaque appel -- c'est ce qui permet de rejouer N mutants depuis le MEME point."""
    dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
    ab = _rpc(sid, "unitAbilityStates", {"runnerId": rid}, 60)
    bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    mt = _rpc(sid, "dumpRng", {"runnerId": rid}, 30)
    return {"dv": dv, "ob": ob, "snap": snap, "ab": ab, "bg": bg, "mt": mt}


def _state(cap):
    board = Board(cap["bg"]["tiles"], adjacency="evenq")
    st = load_state(cap["dv"], cap["ob"], cap["snap"], board=board, ability_states=cap["ab"])
    rng = IntBasedMersenneTwister()
    rng.mt = list(cap["mt"]["mt"])
    rng.mti = cap["mt"]["mti"]
    st.rng = rng
    return st


def _units(cap):
    return [u for u in ((cap["dv"] or {}).get("units") or []) if u.get("alive")]


def _by_vis(cap, vis):
    return next((u for u in _units(cap) if (u.get("visualId") or "") == vis), None)


def _hexi(h):
    try:
        return int(str(h), 16) if h else 0
    except ValueError:
        return 0


# ------------------------------------------------------------------------------ volet DEGAT

def _montants_natifs(res, cible_id):
    """SEQUENCE coup par coup du NATIF, pas resolu PAR NOM (`SE.step_id`) -- un ordinal fige
    designerait le pas VOISIN au prochain retrait de membre, sans erreur ni trace."""
    out = []
    for act in ((res or {}).get("actions") or []):
        for e in (act.get("events") or []):
            if e.get("step") != SE.step_id("UnitDamaged"):
                continue
            try:
                t = json.loads(e.get("tags") or "{}")
            except Exception:
                continue
            if (t.get("Active_Ability_Type") == ABILITY
                    and int(t.get("Target_Id", -1)) == int(cible_id)):
                out.append(int(t["Amount"]))
    return out


def _port_sequence(cap, caster, cible, tree_factory=None):
    """Rejoue le port sur un `State` RECHARGE de `cap`. `tree_factory` != None -> MUTANT."""
    import engine.runner.abilities.blacktemplars as BT
    st = _state(cap)
    runner = Runner(st).install_default_handlers(20)
    ancien = BT.incendiary_shells_tree
    if tree_factory is not None:
        BT.incendiary_shells_tree = tree_factory
    try:
        runner.apply(ActiveAbilityMessage(int(caster), int(cible), ABILITY))
    finally:
        BT.incendiary_shells_tree = ancien
    diag = runner.ability_handler.last or {}
    return [int(x) for x in ((diag.get("attack") or {}).get("per_hit") or [])], diag


def _mutants():
    """Les MUTANTS de l'arbre. Chacun change UNE grandeur LUE au decompile ; celui qui n'ecarte pas
    la sequence est un temoin AVEUGLE, et le probe le NOMME au lieu de le taire."""
    from engine.entities.behaviours import AtomicGroup, op_and
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage, InformWeapon

    def _t(**kw):
        base = dict(is_melee=None, ability_type=ABILITY)
        base.update(kw)
        profil = base.pop("profile", INCENDIARY_SHELLS_PROFILE)
        return lambda: AtomicGroup(op_and(
            InformWeapon(profil, is_melee=False, use_special=False),
            AttackWithAttackDamage(__import__(
                "engine.entities.selectors.accessors", fromlist=["Target"]).Target(),
                INCENDIARY_SHELLS_ID, profil, **base)))

    return [
        ("hits=2 (au lieu de nrOfHits=3)", _t(hits_override=2)),
        ("profile=Physical (au lieu de Flame)", _t(profile="Physical")),
        ("native_factory=ability (1 tirage/coup au lieu de 2)", _t(native_factory="ability")),
        ("is_melee=True (nature declaree MELEE)", _t(is_melee=True)),
        # LE mutant qui a trouve le bug : `False` n'est PAS un synonyme prudent de `None`.
        ("is_melee=False (nature declaree RANGED -- l'aura BigTarget mord)", _t(is_melee=False)),
    ]


def volet_degat(sid, rid, regime="armure=0") -> int:
    cap = _capture(sid, rid)
    caster = _by_vis(cap, PORTEUR_VIS)
    cibles = [u for u in _units(cap) if u.get("team") != caster.get("team")]
    cibles.sort(key=lambda u: (_dist(caster, u) or 99, int(u["id"])))
    cible = cibles[0]
    print("[907/degat/" + regime + "]caster=%s cible=%s d=%s" % (caster["id"], cible["id"],
                                                   _dist(caster, cible)))
    print("[907/degat/" + regime + "]constants=%r" % ((GC.ability(INCENDIARY_SHELLS_ID) or {}).get("constants"),))

    port, diag = _port_sequence(cap, caster["id"], cible["id"])
    res = _rpc(sid, "applyAction", {"runnerId": rid,
                                    "action": {"kind": "ability", "casterId": int(caster["id"]),
                                               "targetId": int(cible["id"]),
                                               "abilityType": ABILITY}}, 240)
    a0 = ((res or {}).get("actions") or [{}])[0]
    natif = _montants_natifs(res, cible["id"])
    print("[907/degat/" + regime + "]natif ok=%r mutated=%r" % (a0.get("ok"), a0.get("mutated")))
    print("[907/degat/" + regime + "]NATIF per_hit=%r somme=%d" % (natif, sum(natif)))
    print("[907/degat/" + regime + "]PORT  per_hit=%r somme=%d  informed=%r"
          % (port, sum(port), diag.get("informed_weapon")))
    accord = bool(natif) and port == natif
    print("[907/degat/" + regime + "]ACCORD=%s" % accord)

    # DISCRIMINANCE du temoin lui-meme : une sequence CONSTANTE n'exercerait aucun tirage.
    print("[907/degat/" + regime + "]temoin : %d valeur(s) distincte(s) sur %d coup(s)"
          % (len(set(natif)), len(natif)))

    aveugles = []
    for nom, fab in _mutants():
        seq, _ = _port_sequence(cap, caster["id"], cible["id"], tree_factory=fab)
        mord = seq != natif
        print("[907/degat/" + regime + "]MUTANT %-55s -> %r  %s" % (nom, seq, "MORD" if mord else "AVEUGLE"))
        if not mord:
            aveugles.append(nom)
    if aveugles:
        print("[907/degat/" + regime + "]MUTANTS AVEUGLES (a NOMMER dans le rapport) : %r" % (aveugles,))
    return 0 if accord else 1


# ------------------------------------------------------------------------------- volet GATE

def volet_gate(sid, rid, nom_geo) -> tuple[int, list]:
    """Confrontation cible par cible du masque au NATIF, sur la geometrie `nom_geo`."""
    from engine.runner.abilities.targeting import get_invalid_target_reason
    cap = _capture(sid, rid)
    st = _state(cap)
    caster = _by_vis(cap, PORTEUR_VIS)
    ability = IncendiaryShellsAbility()
    cid = int(caster["id"])
    rows = []
    for u in _units(cap):
        uid = int(u["id"])
        nat = _rpc(sid, "abilityReason", {"runnerId": rid, "casterId": cid,
                                          "abilityType": ABILITY, "targetId": uid}, 60)
        nt = _hexi((nat.get("targetReason") or {}).get("hex"))
        if nt == 0x1:
            continue                          # `ValidRequest` : refus EN AMONT du filtre de cible
        pt = int(get_invalid_target_reason(st, cid, uid, ability) or 0)
        rows.append({"geo": nom_geo, "uid": uid, "vis": u.get("visualId"),
                     "side": "ALLIE" if u.get("team") == caster.get("team") else "ENNEMI",
                     "dist": _dist(caster, u), "nat": nt, "port": pt})
    for r in rows:
        print("[907/gate/%-5s] u%-3d %-20s %-6s d=%-3s natif=%-12s port=%-12s %s"
              % (nom_geo, r["uid"], r["vis"], r["side"], r["dist"], hex(r["nat"]), hex(r["port"]),
                 "OK" if r["nat"] == r["port"] else "DESACCORD"))
    ko = [r for r in rows if r["nat"] != r["port"]]
    return (1 if ko else 0), rows


def volet_gate_mutants(sid, rid, nom_geo, rows) -> None:
    """CONTREFACTUELS du masque : chaque champ bascule, sur le MEME etat. Un champ dont la bascule
    ne change AUCUNE ligne n'est pas demontre porteur -- il est NOMME."""
    from dataclasses import replace
    from engine.runner.abilities.targeting import (RANGE_ADJACENT, RANGED_BOOL_FALSE,
                                                   get_invalid_target_reason)
    from engine.runner.abilities.targeting_rule import TargetingRule as TR
    cap = _capture(sid, rid)
    st = _state(cap)
    caster = _by_vis(cap, PORTEUR_VIS)
    cid = int(caster["id"])
    base = IncendiaryShellsAbility.TARGETING_OPTIONS

    variantes = [
        ("fmtFlip : force_melee_target RangedBool.True -> False",
         replace(base, force_melee_target=RANGED_BOOL_FALSE)),
        ("range RANGE_FROM_CONFIG -> RANGE_ADJACENT",
         replace(base, range=RANGE_ADJACENT)),
        ("rules : retrait de TargetIsEnemy",
         replace(base, rules=TR.TargetMatchesDynamicRule)),
        ("TARGETING_OPTIONS = None (l'etat d'AVANT le masque)", None),
    ]
    for nom, opts in variantes:
        class _Mut(IncendiaryShellsAbility):
            __slots__ = ()
        _Mut.TARGETING_OPTIONS = opts
        m = _Mut()
        diffs = []
        for r in rows:
            pt = int(get_invalid_target_reason(st, cid, r["uid"], m) or 0)
            if pt != r["port"]:
                diffs.append((r["uid"], r["vis"], r["dist"], hex(r["port"]), hex(pt),
                              hex(r["nat"])))
        print("[907/gate/%-5s] CONTREFACTUEL %-52s -> %d ligne(s) changee(s) %s"
              % (nom_geo, nom, len(diffs), diffs if diffs else "(AVEUGLE)"))


# ------------------------------------------------------------------------------ volet SPAWN

def volet_spawn(sid, rid) -> int:
    cap = _capture(sid, rid)
    caster = _by_vis(cap, PORTEUR_VIS)
    for u in _units(cap):
        print("[907/spawn] id=%-3s vis=%-22s team=%s pos=%r d=%s"
              % (u.get("id"), u.get("visualId"), u.get("team"), _pos(u), _dist(caster, u)))
    return 0


# ------------------------------------------------------------------------------------ main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--volet", default="tout", choices=("tout", "degat", "gate", "spawn"))
    a = ap.parse_args(argv)
    sid = _sid()
    print("[907] session=%s" % sid)
    rc = 0

    if a.volet in ("tout", "spawn"):
        rid = _build(sid, a.state_file, None)
        try:
            print("[907] rid=%s (spawn)" % rid)
            rc |= volet_spawn(sid, rid)
        finally:
            _rpc(sid, "disposeRunner", {"runnerId": rid}, 60)

    if a.volet in ("tout", "gate"):
        for nom_geo, places in GEOMETRIES.items():
            rid = _build(sid, a.state_file, places)
            try:
                print("[907] rid=%s (gate/%s)" % (rid, nom_geo))
                r, rows = volet_gate(sid, rid, nom_geo)
                rc |= r
                volet_gate_mutants(sid, rid, nom_geo, rows)
            finally:
                _rpc(sid, "disposeRunner", {"runnerId": rid}, 60)

    if a.volet in ("tout", "degat"):
        # DEUX regimes : armure 0 (le nombre de COUPS est l'observable) puis armure HAUTE (le
        # PERCAGE du profil devient l'observable -- sans lui le mutant `profile` est AVEUGLE).
        for armure in (0, 3000):
            rid = _build(sid, a.state_file, GEOMETRIES["libre"], armure=armure)
            try:
                print("[907] rid=%s (degat, armure=%d)" % (rid, armure))
                rc |= volet_degat(sid, rid, regime="armure=%d" % armure)
            finally:
                _rpc(sid, "disposeRunner", {"runnerId": rid}, 60)

    print("[907] rc=%d" % rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
