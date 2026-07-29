#!/usr/bin/env python
"""#236 -- les GATES D'ENTREE de la feuille de mouvement `MinDistanceToClosestEnemy(16)`.

`<EvaluateMovementInSteps>IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`
court-circuite la feuille sur QUATRE gates, AVANT tout calcul de distance -- chacun rend
`Fix64.FromInt(0)` (soit 0.0, PAS `NO_PATH_UTILITY`) :

  1. `case.Unit == null`                                            (`case+0x10`)
  2. `IdunBattle.Entities.UnitExtensions$$IsNonAttacking(case.Unit)`  (trait 0x409 = 1033)
  3. `case.ClosestEnemy == null`                                    (`case+0x20`)
  4. `!IdunBattle.AI.Utilities.UnitCanBeDamagedUtility$$UnitCanBeDamaged(case.Unit, case.ClosestEnemy)`
     = ClosestEnemy `Impervious` (trait 0x1c = 28) ET `GetStat(unit, 9 = CriticalChance) == 0`

Aucun n'etait porte (ni face LIVE ni face OFFLINE) : le port attribuait un terme de distance la
ou le natif rend zero -> il PREFERE des tuiles que le natif n'evalue pas. La degradation est
PERMISSIVE et STRUCTURELLEMENT INVISIBLE en agrement (`MovementActionGenerator.generate` est un
argmax pur : un ecart UNIFORME ne deplace aucun choix). D'ou ce probe, qui confronte TUILE PAR
TUILE et jamais par un taux d'accord.

MONTAGE DU GATE 3 (le seul des quatre qui soit CONFRONTABLE LIVE avec des unites du pool) :
un roster adverse compose a 100 % de porteurs du trait `TeleportStrike`. Au premier tour, les
cinq portent l'effet `TeleportStrike_TeleportingIn` -> `IdunBattle.Entities.UnitExtensions$$IsTargetable`
est FAUX -> `FindClosestEnemy` ne retient AUCUN candidat -> `ClosestEnemy == null`, et le RPC
`pathDistToEnemies` (mirror des memes predicats natifs) rend `ok=false "aucun ennemi vivant"`.
Les ennemis restent VIVANTS et POSITIONNES (`ctx.epos` non vide), donc l'ancien port basculait
sur son repli HEX et rendait `wMin * hexdist` != 0 la ou le natif rend 0.

Gates 2 et 4 : leurs porteurs de kit sont EXCLUSIVEMENT npc (`orksNpc4AmmoGrot` /
`orksNpc5LootGrotTeam` pour NonAttacking ; les trois `LootObj_Strongbox_*` pour Impervious) et
AUCUN ne passe `buildNormalizedBC` ("v2 patch: system error") -> non spawnables en runner. Le
gameconfig n'accorde ces traits par AUCUNE ability (`AddTrait`). Ils sont donc exerces ici sur la
face OFFLINE, en posant le trait dans le substrat que `HasTrait` lit reellement
(`UnitContext.traits` = `BaseUnitComponent+0x48`, ce qu'ecrit le leaf DSL `AddTrait`).

Usage (depuis scripts/python, session Frida deja warmee) :
  python probe_236_mindist_gates.py --state-file <ABSOLU>.json [--seed 12345] [--board MC1_67]
  python probe_236_mindist_gates.py --runner <rid> --unit <uid>      # runner deja monte
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine import weights  # noqa: E402
from engine.ai import context as _ai_ctx  # noqa: E402
from engine.ai import state_bridge as _sb  # noqa: E402
from engine.entities.pathfinding.board import Board as _Board  # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait  # noqa: E402
from engine.runner.components import StatsComponent  # noqa: E402
from engine.runner.snapshot import load_state  # noqa: E402
from engine.utilities.move import MIN_DIST_UTILITY, UtilityMovementCase  # noqa: E402

PYDIR = Path(__file__).resolve().parent

# Roster adverse 100 % `TeleportStrike` -> les cinq sont `TeleportStrike_TeleportingIn` au tour 1,
# donc NON CIBLABLES -> `FindClosestEnemy` rend null. Tous dans `rl_duel --list-pool` (rank 17).
DEEP_STRIKE_ROSTER = "bloodDante,blackTerminator,darkaTerminator,spaceRockfist,worldTerminator"
MOVER_ROSTER = "ultraTitus,spaceStormcaller"


def _mk_rpc(sid: int):
    def rpc(method, body, timeout=60):
        r = _rpc(sid, method, [body], timeout=timeout)
        return (r.get("result") or {}) if isinstance(r, dict) else {}
    return rpc


def _build(state_file: str, seed: int, board: str, a_units: str) -> int:
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
           "--p-units", MOVER_ROSTER, "--a-units", a_units, "--state-file", state_file]
    out = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True)
    for line in (out.stdout or "").splitlines():
        if line.startswith("[build] runnerId="):
            return int(line.split("runnerId=")[1].split()[0])
    print(out.stdout)
    print(out.stderr, file=sys.stderr)
    raise RuntimeError("build KO")


def _rows(ctx, wt, case):
    """Terme MinDist par tuile du movable set, avec et sans le `case` (donc avec/sans gates)."""
    order = [(t["col"], t["row"]) for t in ctx.move_tiles]
    out = []
    for t in order:
        u_no = MIN_DIST_UTILITY.evaluate_movement(
            t, ctx.tgt_epos or ctx.epos, wt, ctx.pathdist_by_pos, case=None)
        u_yes = MIN_DIST_UTILITY.evaluate_movement(
            t, ctx.tgt_epos or ctx.epos, wt, ctx.pathdist_by_pos, case=case)
        out.append((t, u_no, u_yes))
    return out


def _print_face(label, rows, expect_zero: bool) -> int:
    """Rend le nombre de tuiles NON CONFORMES a l'attendu natif."""
    bad = 0
    print("  %-10s %-14s %-14s %s" % ("tile", "port SANS gate", "port AVEC gate", "verdict"))
    for t, u_no, u_yes in rows:
        ok = (u_yes == 0.0) if expect_zero else (u_yes == u_no)
        if not ok:
            bad += 1
        print("  %-10s %-14s %-14s %s" % (t, u_no, u_yes, "OK" if ok else "DIVERGE"))
    print("  [%s] %d tuiles, %d non conformes (attendu natif = %s)"
          % (label, len(rows), bad, "0 partout (gate)" if expect_zero else "inchange"))
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--unit", type=int, default=None)
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--nominal", action="store_true",
                    help="roster adverse ORDINAIRE (aucun gate ne mord) -> garde de non-regression")
    a = ap.parse_args()

    sid = _resolve_session()
    rpc = _mk_rpc(sid)
    wt = weights.load()
    a_units = MOVER_ROSTER if a.nominal else DEEP_STRIKE_ROSTER
    rid = a.runner if a.runner is not None else _build(
        a.state_file or str(PYDIR / "probe236_state.json"), a.seed, a.board, a_units)

    dv = rpc("decisionView", {"runnerId": rid}, 90)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
    mov_by_unit = {m.get("unitId"): m for m in (mov.get("units") or [])}
    mine = [u for u in (dv.get("units") or []) if u.get("ctrl") and u.get("alive")]
    uid = a.unit if a.unit is not None else (mine[0].get("id") if mine else None)
    if uid is None:
        print("[error] aucune unite controlee vivante", file=sys.stderr)
        return 2

    pdr = rpc("pathDistToEnemies", {"runnerId": rid, "unitId": uid}, 90)
    print("== runner %d, mover u%d (%s) ==" % (rid, uid, a.board))
    print("   RPC pathDistToEnemies: ok=%s err=%r enemyCount=%s closestResolved=%s"
          % (pdr.get("ok"), pdr.get("error"), pdr.get("enemyCount"), pdr.get("closestResolved")))

    ctx = _ai_ctx.build(rpc, rid, dv, mov_by_unit, uid, wt, None)
    print("   ctx.epos=%s" % (sorted(ctx.epos),))
    print("   ctx.tgt_epos=%s" % (sorted(ctx.tgt_epos or []),))
    print("   ctx.pathdist_by_pos vide ? %s" % (not ctx.pathdist_by_pos))
    print("   ctx.mindist_case=%s" % (ctx.mindist_case,))

    gate_bites = not a.nominal
    bad = 0
    print("\n-- face LIVE (engine.ai.context.build) --")
    bad += _print_face("live", _rows(ctx, wt, ctx.mindist_case), gate_bites)

    obs = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    bg = rpc("boardGraph", {"runnerId": rid}, 90)
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    bd = _Board(bg["tiles"], adjacency="native_sym")
    state = load_state(dv, obs, snap, board=bd, tiles=tm)   # `board=` OBLIGATOIRE (sinon repli hex)
    octx = _sb.build_from_state(state, uid)
    print("\n-- face OFFLINE (engine.ai.state_bridge.build_from_state) --")
    print("   octx.mindist_case=%s" % (octx.mindist_case,))
    bad += _print_face("offline", _rows(octx, wt, octx.mindist_case), gate_bites)

    # --- GATE 2 (IsNonAttacking) : hors portee live (porteurs npc non normalisables), exerce sur
    #     le substrat que `HasTrait` lit reellement -- exactement ce qu'ecrit le leaf DSL `AddTrait`.
    sc = state.get_entity(uid).get_component(StatsComponent)
    if sc is not None and sc.ctx is not None:
        sc.ctx.traits = list(sc.ctx.traits or []) + [UnitTrait.NonAttacking.name]
        octx2 = _sb.build_from_state(state, uid)
        print("\n-- face OFFLINE, GATE 2 : AddTrait(NonAttacking) sur le mover --")
        print("   octx2.mindist_case=%s" % (octx2.mindist_case,))
        bad += _print_face("offline/nonattacking", _rows(octx2, wt, octx2.mindist_case), True)
        sc.ctx.traits = [t for t in sc.ctx.traits if t != UnitTrait.NonAttacking.name]

    # --- GATE 4 (UnitCanBeDamaged) : ClosestEnemy `Impervious` + CriticalChance du mover a 0.
    #     Exerce sur un case CONSTRUIT (l'etat live ne peut pas produire ce couple : aucun porteur
    #     Impervious n'est spawnable, et ceux du gameconfig sont `Object`+Attack 0 donc
    #     `IsIrrelevantObject` -> jamais retenus comme ClosestEnemy).
    print("\n-- GATE 4 (case construit) : ClosestEnemy Impervious x CriticalChance du mover --")
    for crit, exp in ((0, True), (15, False)):
        c = UtilityMovementCase(unit=uid, unit_traits=(), unit_crit_chance=crit,
                                closest_enemy=999,
                                closest_enemy_traits=(UnitTrait.Impervious.name,))
        u = MIN_DIST_UTILITY.evaluate_movement((0, 0), [(3, 3)], wt, {(0, 0): 4}, case=c)
        ok = (u == 0.0) if exp else (u != 0.0)
        bad += 0 if ok else 1
        print("   crit=%-3d -> U=%-14s attendu %s  %s"
              % (crit, u, "0 (gate)" if exp else "non nul", "OK" if ok else "DIVERGE"))

    print("\n== TOTAL non conformes : %d ==" % bad)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
