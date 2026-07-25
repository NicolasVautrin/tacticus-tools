#!/usr/bin/env python
"""Probe #45 (fable) - discriminant cause racine du residu x1.5 GreatFrostAxe / Stormcaller.

Deux hypotheses en conflit a trancher par la DONNEE (une variable = l'elevation) :
  H_ice  : le +50% = bonus crit-sur-Ice (IdunBattle.Entities.Effects.IceEffect$$CreateEffectDamageBonusForAttack).
           REFUTE au decompile : formule = PercentageOf(GetStat(CRIT_DAMAGE), EffectConfig(5)),
           gate AttackDamageIsCritical -> 0 sur des coups non-crit (DidCrit=0) et cd=0.
  H_elev : le +50% = bonus d'ELEVATION (Damage.ElevationBonus=50, feuille du builder attaquant
           PARTAGE IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction) que le vecteur ability-family offline n'applique pas.

Cas (positions FORCEES par applyAction, board MC1_67) :
  gfa_flat  : GreatFrostAxe (attack-family), att elev == cible -> attendu ratio 1.0 (aucune diver.)
  gfa_high  : GreatFrostAxe, att elev > cible               -> H_elev predit live=1.5x offline (pre-fix)
  storm_flat: Stormcaller (ability-family), att elev == cible -> ratio 1.0
  storm_high: Stormcaller, att elev > cible  === DATAPOINT DECISIF : l'ability-family recoit-elle
              l'elevation ? live=1.5x offline -> OUI (gate famille du WIP FAUX) ; live==offline -> NON.

Usage : python probe_45_shared_bonus.py [--case gfa_flat|gfa_high|storm_flat|storm_high|all]
ASCII only (cp1252). State-file UNIQUE par cas ; dispose au teardown.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

from engine.runner.snapshot import load_state                     # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister            # noqa: E402
from engine.entities.pathfinding.board import Board               # noqa: E402
from engine.runner.abilities.spacewolves import great_frost_axe_tree  # noqa: E402
from engine.runner.abilities.loki.stormcaller import stormcaller_tree  # noqa: E402
from engine.runner.abilities.behaviours import entities_from_state  # noqa: E402
from engine.dsl.effects import ExecutionContext                   # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
A_UNITS = "necroOverlord,necroWarden,necroWarden"

SPEC = {
    "gfa_flat":   ("spaceWulfen", 1089, "flat"),
    "gfa_high":   ("spaceWulfen", 1089, "high"),
    "storm_flat": ("spaceStormcaller", 1113, "flat"),
    "storm_high": ("spaceStormcaller", 1113, "high"),
}


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _find(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _tags(e):
    tg = e.get("tags")
    return (json.loads(tg) if isinstance(tg, str) else tg) or {}


def build(seed, tag, caster_vis):
    state = ROOT / "data" / "rl-state" / f"p45sb-{tag}-{uuid.uuid4().hex[:6]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(state),
         "--board", "MC1_67", "--roster", "1", "--p-units", caster_vis, "--a-units", A_UNITS,
         "--hp-target", "300000", "--hp-player", "300000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        print(f"[45sb] build {tag} KO: {(proc.stderr or proc.stdout or '')[-400:]}")
        sys.exit(2)
    return json.loads(state.read_text())["runnerId"], state


def _pick_tiles(bg, occupied, relation):
    tiles = {t["id"]: t for t in bg["tiles"]}
    for t in bg["tiles"]:
        if not t.get("walkable") or (t["col"], t["row"]) in occupied:
            continue
        for nid in (t.get("neighbours") or []):
            n = tiles.get(nid)
            if n is None or not n.get("walkable") or (n["col"], n["row"]) in occupied:
                continue
            et, en = t.get("elevation") or 0, n.get("elevation") or 0
            if relation == "high" and en > et:
                return t, n
            if relation == "flat" and en == et:
                return t, n
    return None, None


def _offline_per_hit(tree, dec1, ob1, snap1, bg, s_cast, cid, eid):
    st = load_state(dec1, ob1, snap1)
    st.board = Board(bg["tiles"], adjacency="native_sym")
    rng = IntBasedMersenneTwister()
    rng.mt = list(s_cast["mt"]); rng.mti = s_cast["mti"]
    st.rng = rng
    ectx = ExecutionContext(state=st, rng=st.rng)
    tree.execute(entities_from_state(st, cid, eid), ectx)
    out = {}
    for n, p in ectx.emitted:
        if n == "AttackWithAttackDamage" and p.get("attack"):
            out[p.get("target")] = {"per_hit": p["attack"].get("per_hit") or [],
                                    "crits": p["attack"].get("crits") or []}
    return out


def run_case(sid, case, seed):
    caster_vis, ability, relation = SPEC[case]
    rid, state_file = build(seed, case, caster_vis)
    rpc = lambda m, b, t=120: (_rpc(sid, m, [dict(b)], timeout=t).get("result") or {})
    try:
        caster = None
        for _ in range(16):
            dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            if not _ok(dec):
                print(f"[45sb:{case}] decisionView KO"); return
            caster = _find(dec, caster_vis)
            if caster is None:
                print(f"[45sb:{case}] caster absent"); return
            if caster.get("owner") == dec.get("currentPlayer"):
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        else:
            print(f"[45sb:{case}] tour caster jamais atteint"); return
        cid = caster["id"]
        target = next((u for u in (dec.get("units") or [])
                       if u.get("alive") and u.get("owner") != caster.get("owner")
                       and u.get("visualId") == "necroWarden"), None)
        if target is None:
            print(f"[45sb:{case}] cible absente"); return
        eid = target["id"]
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            print(f"[45sb:{case}] boardGraph KO"); return
        occupied = {((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
                    for u in (dec.get("units") or []) if u.get("alive") and u.get("pos")}
        tt, ta = _pick_tiles(bg, occupied, relation)
        if tt is None:
            print(f"[45sb:{case}] aucune paire de tuiles {relation} libre"); return
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": eid, "to": {"col": tt["col"], "row": tt["row"]}}}, 90)
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cid, "to": {"col": ta["col"], "row": ta["row"]}}}, 90)
        dec1 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob1 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap1 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s_cast = rpc("dumpRng", {"runnerId": rid}, 30)
        if snap1 is None or not _ok(s_cast):
            print(f"[45sb:{case}] snapshot/dumpRng KO"); return
        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": eid, "abilityType": ability},
            "captureEvents": True}, 120)
        if not _ok(cast):
            print(f"[45sb:{case}] cast KO: {str(cast)[:200]}"); return
        a0 = (cast.get("actions") or [{}])[0]
        live = [{"amt": int(_tags(e).get("Amount") or 0), "crit": int(_tags(e).get("Attack_DidCrit") or 0)}
                for e in (a0.get("events") or [])
                if _tags(e).get("Target_Id") == eid and "Amount" in _tags(e)
                and _tags(e).get("Active_Ability_Type") == ability]
        tree = great_frost_axe_tree() if ability == 1089 else stormcaller_tree()
        off = _offline_per_hit(tree, dec1, ob1, snap1, bg, s_cast, cid, eid)
        off_ph = (off.get(eid) or {}).get("per_hit") or []
        et, ea = tt.get("elevation") or 0, ta.get("elevation") or 0
        fam = "attack" if ability == 1089 else "ability"
        print(f"[45sb:{case}] fam={fam} elev att={ea} cible={et} ({relation})")
        print(f"[45sb:{case}] live per-hit = {[h['amt'] for h in live]}  crits={[h['crit'] for h in live]}")
        print(f"[45sb:{case}] off  per-hit = {off_ph}")
        for i, h in enumerate(live):
            if i < len(off_ph) and off_ph[i]:
                print(f"[45sb:{case}]   hit{i}: live={h['amt']} off={off_ph[i]} "
                      f"ratio={h['amt']/off_ph[i]:.4f} delta={h['amt']-off_ph[i]}")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            state_file.unlink()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="all",
                    choices=["gfa_flat", "gfa_high", "storm_flat", "storm_high", "all"])
    ap.add_argument("--seed", type=int, default=45501)
    args = ap.parse_args()
    sid = _resolve_session()
    cases = (["gfa_flat", "gfa_high", "storm_flat", "storm_high"]
             if args.case == "all" else [args.case])
    for i, c in enumerate(cases):
        run_case(sid, c, args.seed + i)


if __name__ == "__main__":
    main()
