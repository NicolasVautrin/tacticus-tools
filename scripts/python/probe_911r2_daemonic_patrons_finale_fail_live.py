#!/usr/bin/env python
"""probe #911-r2 -- CONFRONTATION de la face FAIL de `DaemonicPatrons_Finale` (0x5c1 = 1473).

CRITERE BINAIRE, pose avant toute methode :

    << Quand l'effet `DaemonicPatrons_DmgReduction` (0x5b9 = 1465) QUITTE `emperFlawlessBlade`
       (<< Hascule >>) alors qu'il n'a re-arme AUCUNE fois son actif 1203, le natif lui inflige-t-il
       `hpPct` % de ses PV COURANTS -- et le PORT rend-il le MEME montant, depuis le meme etat et le
       meme flux PRNG ? >>

L'observable est le DELTA DE PV du porteur sur le SEUL tick de fin de tour qui retire 1465.

## POURQUOI CE PROBE EXISTE A COTE DE `probe_911r1_...`

`#911-r1` a confronte la face SUCCESS (deux bras, port == natif, contre-epreuve `NOPORT` qui mord).
La face FAIL a un vecteur DIFFERENT -- `On(0x40 = EffectRemoved)` au lieu d'`On(0x36 = UnitDefeated)`
-- donc un montage different : il faut attendre l'EXPIRATION de 1465, la ou le probe `-r1` s'arrete
au kill. Le reste du montage (seed BC augmente d'`emperFlawlessBlade`, `--crit 0,0`) est REUTILISE
tel quel, par import : aucune duplication.

## LE MONTAGE, et pourquoi chaque piece y est

  * `emperFlawlessBlade` est HORS POOL et HORS seed BC -> `catalog_inject.write_augmented_seed_bc`
    (fonction `seed_bc_avec_hascule` du probe `-r1`).
  * Le cast de 1203 est OBLIGATOIRE : c'est lui qui POSE 1465 (et qui CONSOMME l'actif, ce qui rend
    VRAI le 4e conjoint `NOT CanUseAbility(Owner, 1203)`). Sans cast, il n'y a ni effet a retirer ni
    gate a satisfaire.
  * AUCUN kill entre le cast et l'expiration : un kill sur la cible TAUNTEE ferait fire la face
    SUCCESS, qui re-arme 1203 -- et le 4e conjoint de la FAIL fermerait le gate. Les deux faces sont
    les deux branches du meme << if he does / if he does not >>. Ce probe monte la branche NEGATIVE,
    donc Hascule n'attaque JAMAIS.
  * `--crit 0,0` / `--block-target 0,0` : aucun canal aleatoire n'entre dans le montant.
  * Le porteur est a PV PLEINS jusqu'au tick, donc `StatAmount(Owner, HEALTH, variant 0 = COURANT)`
    est CONNU : le montant attendu est `hpPct % x PV`, ce qui rend la mesure lisible sans oracle
    intermediaire.

## LES DEUX BRAS, et pourquoi il en faut DEUX

  * `FAIL` (defaut) -- l'actif 1203 est CONSOMME et jamais re-arme : au retrait de 1465, le natif
    DOIT infliger les degats.
  * `--temoin-sans-cast` -- le MEME nombre de tours passe, la MEME unite, mais AUCUN cast : ni 1465
    ni consommation d'actif. Aucun degat ne doit tomber, des deux cotes. Sans ce bras, une chute de
    PV due a tout AUTRE canal (un DoT, une IA qui frappe, un effet de tuile) se lirait comme la face
    FAIL.

La contre-epreuve `NOPORT` (la classe `DaemonicPatronsFinaleFailAbility` retiree
d'`ACTIVE_ABILITY_TRIGGERS`) doit CHANGER l'observable offline : sans elle, << ca concorde >> ne
prouverait rien.

Usage (depuis `scripts/python`, ASCII only) :
    python probe_911r2_daemonic_patrons_finale_fail_live.py
    python probe_911r2_daemonic_patrons_finale_fail_live.py --temoin-sans-cast
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))

import probe_911r1_daemonic_patrons_finale_live as P1   # noqa: E402

CARRIER = P1.CARRIER               # `emperFlawlessBlade` << Hascule >>
ALLY = P1.ALLY
ABILITY_TYPE = P1.ABILITY_TYPE     # 1203
DP_TAUNTED = P1.DP_TAUNTED         # 27
DP_EXTRA_DAMAGE = P1.DP_EXTRA_DAMAGE   # 1464
DP_DMG_REDUCTION = 1465            # `EffectType.DaemonicPatrons_DmgReduction` = 0x5b9
REGISTRY_KEY = P1.REGISTRY_KEY     # "DaemonicPatrons"
MAX_ENDTURNS = 10                  # borne dure : la duree posee vaut 3 tours, jamais 10


def seed_bc_avec_hascule() -> str:
    return P1.seed_bc_avec_hascule()


def build(a, seed_bc):
    """MEME build que `-r1`, moins le `--unit-stat Damage` (Hascule ne frappe pas ici)."""
    fd, sf = tempfile.mkstemp(prefix="probe_911r2_", suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build",
            "--seed", str(a.seed), "--state-file", sf, "--board", a.board,
            "--seed-bc", seed_bc,
            "--p-units", "%s,%s" % (CARRIER, ALLY),
            "--a-units", "%s,%s" % (a.target_unit, a.other_unit),
            "--hp-target", str(a.hp_target), "--hp-player", str(a.hp_player),
            "--no-ai", "--crit", "0,0", "--block-target", "0,0"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("build KO : %s" % ((p.stderr or p.stdout or "")[-900:]))
        return None, sf
    return json.loads(Path(sf).read_text())["runnerId"], sf


def _hp(dv, unit_id):
    for u in (dv.get("units") or []):
        if u.get("id") == unit_id:
            return u.get("hp")
    return None


def _endturn(h):
    h.rpc("applyAction", {"runnerId": h.rid, "action": {"kind": "endturn"}}, 40)
    h.endturns += 1


def stage(h, a):
    """Monte le regime et rend `(rec, raison)`. `raison is None` == regime ATTEINT.

    ETAPES : placements (une cible ADJACENTE, le second ennemi ECARTE) -> cycle de tour -> CAST de
    1203 sur la cible (pose 27 sur elle, 1464/1465 sur Hascule, actif consomme) -> `endturn` un par
    un jusqu'au tick qui RETIRE 1465, en SNAPSHOTANT juste avant CHAQUE tick.

    Le snapshot retenu est celui du tick DECISIF -- c'est celui-la, et lui seul, que l'offline
    rejouera par `EndTurnMessage`."""
    import hexgeo
    dv = h.dview()
    me = h.by_visual(CARRIER, dv)
    if me is None:
        return None, "porteur %s absent du deploiement" % CARRIER
    h.my_player = me.get("owner")
    ens = h.enemies_of(h.my_player, dv)
    if len(ens) < 2:
        return None, "il faut 2 ennemis (la cible du taunt et un ECARTE) -- %d trouve(s)" % len(ens)
    cible, ecarte = ens[0], ens[1]

    marchables = [h.board.coord(t) for t in sorted(h.board.by_id) if h.board.walkable(t)]
    occupe = {p for p in (P1._pos_of(u) for u in h.alive(dv)) if p is not None}
    libres = [c for c in marchables if c not in occupe]

    plan = None
    for anchor in sorted(libres):
        contacts = [s for s in libres if hexgeo.distance(s, anchor) == 1]
        loin = [s for s in libres if hexgeo.distance(s, anchor) >= 5]
        if contacts and loin:
            plan = (anchor, contacts[0], loin[0])
            break
    if plan is None:
        return None, "geometrie non realisable (un contact + un poste eloigne)"
    anchor, contact, poste_loin = plan

    if not h.place(me["id"], anchor):
        return None, "placement de Hascule refuse"
    if not h.place(cible["id"], contact):
        return None, "placement de la cible du taunt refuse"
    if not h.place(ecarte["id"], poste_loin):
        return None, "placement du second ennemi refuse"

    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint (avant le cast)"

    if not a.temoin_sans_cast:
        res = h.rpc("applyAction", {"runnerId": h.rid, "action": {
            "kind": "ability", "casterId": me["id"], "targetId": cible["id"],
            "abilityType": ABILITY_TYPE}}, 60)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        if not a0.get("ok"):
            return None, "cast de 1203 refuse : %s" % str(res)[:300]
        dv = h.dview()
        eff = P1._effets(dv, me["id"])
        if DP_DMG_REDUCTION not in eff:
            return None, ("l'effet 1465 n'est PAS pose apres le cast (effets = %s) -- il n'y a rien "
                          "a retirer" % sorted(eff))
        etat = P1._active_state_live(dv, me["id"])
        if etat is None or etat.get("usable"):
            return None, ("l'actif est encore utilisable APRES le cast (%s) -- le 4e conjoint "
                          "`NOT CanUseAbility` ne mordrait pas" % etat)

    # --- LE TICK : `endturn` un par un, snapshot AVANT chaque tick ---------------------------
    trace = []
    for i in range(MAX_ENDTURNS):
        dv = h.dview()
        if not (dv.get("units") or []):
            _endturn(h)                          # aucune unite activable -> on rouvre un tour
            continue
        eff = P1._effets(dv, me["id"])
        hp_avant = _hp(dv, me["id"])
        snap = h.snapshot()
        _endturn(h)
        dv2 = h.dview()
        eff2 = P1._effets(dv2, me["id"])
        hp_apres = _hp(dv2, me["id"])
        trace.append({"pas": i, "avant": sorted(eff), "apres": sorted(eff2),
                      "hp_avant": hp_avant, "hp_apres": hp_apres,
                      "reste_1465": eff2.get(DP_DMG_REDUCTION)})
        retire = (DP_DMG_REDUCTION in eff) and (DP_DMG_REDUCTION not in eff2)
        if a.temoin_sans_cast and i + 1 >= a.temoin_pas:
            return ({"unit": me["id"], "cible": cible["id"], "snapshot": snap,
                     "hp_avant": hp_avant, "hp_apres": hp_apres, "retire": False,
                     "trace": trace}, None)
        if retire:
            return ({"unit": me["id"], "cible": cible["id"], "snapshot": snap,
                     "hp_avant": hp_avant, "hp_apres": hp_apres, "retire": True,
                     "trace": trace}, None)
        if not a.temoin_sans_cast and DP_DMG_REDUCTION not in eff and i > 0:
            return None, ("1465 a disparu sans qu'aucun tick ne soit capture (trace = %s)" % trace)
    return None, ("1465 n'a pas expire en %d endturns (trace = %s)" % (MAX_ENDTURNS, trace))


def _hp_port(st, unit_id):
    from engine.runner.components import HealthComponent
    e = st.get_entity(int(unit_id))
    hc = e.get_component(HealthComponent) if e is not None else None
    return None if hc is None else int(hc.hp)


def replay(h, rec, mutate=None):
    """Rejeu OFFLINE du MEME tick de fin de tour (`EndTurnMessage`), RNG cale sur le dump du
    snapshot pris juste AVANT le tick live.

    MUTATION `NOPORT` : la classe `DaemonicPatronsFinaleFailAbility` retiree de l'entree
    `"DaemonicPatrons"` d'`ACTIVE_ABILITY_TRIGGERS` -- c'est le registre qui materialise la
    triggered derivee (`GetDerivedTriggeredAbilities[0x4b3] = [0x5c1]`). Restauree en `finally`."""
    from engine.runner.messages import EndTurnMessage
    from engine.runner.runner import Runner
    from engine.runner.snapshot import load_state
    from engine.runner.operations.triggers.dispatch.registry import ACTIVE_ABILITY_TRIGGERS
    from engine.runner.operations.triggers.loki.daemonic_patrons import (
        DaemonicPatronsFinaleFailAbility)

    saved = list(ACTIVE_ABILITY_TRIGGERS.get(REGISTRY_KEY) or ())
    try:
        if mutate == "NOPORT":
            ACTIVE_ABILITY_TRIGGERS[REGISTRY_KEY] = [
                c for c in saved if c is not DaemonicPatronsFinaleFailAbility]
        s = rec["snapshot"]
        st = load_state(s["dv"], s["ob"], s["snap"], board=h.board)
        dump = s.get("rng")
        if isinstance(dump, dict) and dump.get("mt"):
            st.rng = P1_seed_rng(dump)
        hp0 = _hp_port(st, rec["unit"])
        eff0 = _effets_port(st, rec["unit"])
        Runner(st).install_default_handlers(20).apply(EndTurnMessage(advance=True))
        return {"hp_avant": hp0, "hp_apres": _hp_port(st, rec["unit"]),
                "eff_avant": eff0, "eff_apres": _effets_port(st, rec["unit"])}
    finally:
        ACTIVE_ABILITY_TRIGGERS[REGISTRY_KEY] = saved


def P1_seed_rng(dump):
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(dump["mt"])
    rng.mti = dump["mti"]
    return rng


def _effets_port(st, unit_id):
    if st.effects is None:
        return []
    return sorted({int(e.effect_type) for e in st.effects.by_unit.get(int(unit_id), [])
                   if not e.consumed})


def mesurer(a, rpc, Board, Harness, rid) -> dict:
    """LA MESURE, sur un runner DEJA construit -- sans impression ni verdict.

    Rend `{ok, why, bras, live, offline, noport, attendu_pct}`. `ok: False` = le REGIME n'a pas ete
    atteint (montage), jamais un verdict de fidelite."""
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    h = Harness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
    bras = "TEMOIN SANS CAST" if a.temoin_sans_cast else "FAIL"
    rec, why = stage(h, a)
    if rec is None:
        return {"ok": False, "why": "montage : %s" % why, "bras": bras}
    off = replay(h, rec)
    mut = replay(h, rec, mutate="NOPORT")
    return {"ok": True, "why": None, "bras": bras,
            "attendu": (not a.temoin_sans_cast),
            "live": {"hp_avant": rec["hp_avant"], "hp_apres": rec["hp_apres"],
                     "retire": rec["retire"], "trace": rec["trace"]},
            "offline": off, "noport": mut, "_h": h, "_rec": rec}


def run(a, rpc, Board, Harness, seed_bc) -> int:
    rid, sf = build(a, seed_bc)
    if rid is None:
        Path(sf).unlink(missing_ok=True)
        return 2
    try:
        m = mesurer(a, rpc, Board, Harness, rid)
        if not m.get("ok"):
            print("REFUS (%s)" % m.get("why"))
            return 2
        live, off, mut = m["live"], m["offline"], m["noport"]
        for t in live["trace"]:
            print("    [tick %d] effets %s -> %s | hp %s -> %s"
                  % (t["pas"], t["avant"], t["apres"], t["hp_avant"], t["hp_apres"]))
        d_live = (live["hp_avant"] or 0) - (live["hp_apres"] or 0)
        d_off = (off["hp_avant"] or 0) - (off["hp_apres"] or 0)
        d_mut = (mut["hp_avant"] or 0) - (mut["hp_apres"] or 0)
        print("[%s] LIVE    : hp %s -> %s (perte %d), 1465 retire=%s"
              % (m["bras"], live["hp_avant"], live["hp_apres"], d_live, live["retire"]))
        print("[%s] OFFLINE : hp %s -> %s (perte %d), effets %s -> %s"
              % (m["bras"], off["hp_avant"], off["hp_apres"], d_off,
                 off["eff_avant"], off["eff_apres"]))
        print("[%s] NOPORT  : perte %d" % (m["bras"], d_mut))

        rc = 0
        if off["hp_avant"] is None or off["hp_apres"] is None or live["hp_avant"] is None:
            print("REFUS : PV NON MESURES (live=%s offline=%s)" % (live, off))
            return 2
        if m["attendu"]:
            if d_live <= 0:
                print("REFUS : le NATIF n'inflige RIEN au retrait de 1465 -- le regime ne "
                      "discrimine pas")
                return 2
            attendu = int(round(live["hp_avant"] * a.hp_pct / 100.0))
            print("[%s] attendu (%d%% des PV COURANTS) : %d" % (m["bras"], a.hp_pct, attendu))
        else:
            if d_live != 0:
                print("FAUTE : le TEMOIN perd %d PV alors qu'aucun 1465 n'est retire" % d_live)
                rc |= 1
        if d_off != d_live:
            print("FAUTE : port perte=%d != natif perte=%d" % (d_off, d_live))
            rc |= 1
        if m["attendu"]:
            if d_mut == d_off:
                print("FAUTE : NOPORT rend la MEME perte que le port (%d) -- l'accord ne prouve "
                      "rien" % d_off)
                rc |= 1
            else:
                print("[%s] mord   : True (port=%d vs NOPORT=%d)" % (m["bras"], d_off, d_mut))
        return rc
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        Path(sf).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--target-unit", default="necroWarden")
    ap.add_argument("--other-unit", default="necroSpyder")
    ap.add_argument("--hp-target", type=int, default=900000)
    ap.add_argument("--hp-player", type=int, default=900000)
    ap.add_argument("--hp-pct", type=int, default=30,
                    help="`hpPct` du gameconfig au palier du runner (50) -- sert d'ORDRE DE "
                         "GRANDEUR imprime, jamais d'oracle : l'oracle est le NATIF.")
    ap.add_argument("--temoin-pas", type=int, default=3, dest="temoin_pas",
                    help="BRAS TEMOIN : nombre de ticks joues sans cast.")
    ap.add_argument("--temoin-sans-cast", action="store_true", dest="temoin_sans_cast",
                    help="BRAS TEMOIN : aucun cast de 1203 -- ni 1465 a retirer, ni actif "
                         "consomme. Aucune perte de PV ne doit tomber, des deux cotes.")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    print("== #911-r2 DaemonicPatrons_Finale FAIL (triggered 1473) -- board %s seed %s%s"
          % (a.board, a.seed, " [TEMOIN SANS CAST]" if a.temoin_sans_cast else ""))

    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=60):
        return P1._unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    seed_bc = seed_bc_avec_hascule()
    try:
        rc = run(a, rpc, Board, ChargeRegimeHarness, seed_bc)
    finally:
        Path(seed_bc).unlink(missing_ok=True)
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL(%d)" % rc))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
