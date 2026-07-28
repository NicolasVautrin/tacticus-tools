"""probe #217 -- CONFRONTATION LIVE du routage de ciblage de SorcerousFacade (1100).

Monte un runner ThousandSons (thousTzaangor porteur de 1100 + thousSorcerer, l'ALLIE Psyker) face a
3 ennemis, rapproche le Tzaangor jusqu'a ce que le natif offre une cible pour 1100, puis compare
TROIS ensembles de paires (ability, cible) :

  1. NATIF                -- RPC `abilityTargets` = `IdunBattle.Core.Services.BattleQuery$$GetAllValidTargetsFromAllPossibleMovementTiles`,
                             ce que `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsEntities` consomme ;
  2. LIVE decisionView    -- `attackPlans` du hook (`projection.ts::computeAttackPlans`), qui appelle
                             `IdunBattle.Core.Services.AttackQuery$$GetBestTileToAttackFrom` par (unite, ability, ennemi). Ce
                             natif-la GATE chaque tuile par `AttackQuery.GetInvalidTargetReason` ->
                             `rankCount` DOIT valoir 0 sur un ennemi pour une ability `TargetIsFriendly` ;
  3. OFFLINE state_bridge -- `ability_targets_offline` + les `plans` de `build_from_state`, les deux
                             coutures que le fix #217 corrige.

CRITERE BINAIRE : aucune paire (1100, ENNEMI) dans (2) avec `rankCount > 0`, et aucune dans (3).

Usage : python probe_217_facade_live.py [--board MC1_67] [--seed 217]
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo
import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
FACADE = 1100
CASTER = "thousTzaangor"
ALLY = "thousSorcerer"


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _upos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="217")
    args = ap.parse_args()

    sid = R._resolve_session()
    state_file = Path(__file__).resolve().parents[2] / "logs" / (
        "_probe217_%s_%s.json" % (args.board, args.seed))
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", args.seed, "--board", args.board,
         "--p-units", "%s,%s" % (CASTER, ALLY),
         "--a-units", "ultraApothecary,ultraEliminatorSgt,ultraTitus",
         "--state-file", str(state_file)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("BUILD KO:", (p.stderr or p.stdout or "")[-500:])
        return 1
    rid = json.loads(state_file.read_text())["runnerId"]

    def rpc(m, b, t=120):
        return _unwrap(R._rpc(sid, m, [b], timeout=t))

    rc = 0
    try:
        from engine.entities.pathfinding.board import Board
        from engine.runner.snapshot import load_state
        from engine.ai.state_bridge import ability_targets_offline, build_from_state
        from engine.ai.tactic import DefaultAiUnitTactic

        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")

        def dv(all_ab=True):
            return rpc("decisionView", {"runnerId": rid, "maxRank": 32,
                                        "allAbilities": all_ab}, 180)

        def find(d, vis):
            return next((u for u in (d.get("units") or []) if u.get("visualId") == vis), None)

        def native_targets(uid):
            at = rpc("abilityTargets", {"runnerId": rid, "unitId": uid, "allAbilities": True}, 180)
            for u in (at.get("units") or []):
                if u.get("unitId") != uid:
                    continue
                for a in (u.get("abilities") or []):
                    if a.get("abilityId") == FACADE:
                        return a
            return {}

        # --- RAPPROCHER le caster : la regle dynamique de 1100 exige que le caster puisse porter
        #     son attaque NORMALE depuis les tuiles de cast (`SorcerousFacadeAbility$$GetDynamicInvalidTargetReason`).
        entry = {}
        for _ in range(12):
            d = dv()
            me = find(d, CASTER)
            if me is None or not me.get("alive"):
                print("NO CASTER")
                return 1
            if d.get("currentPlayer") != me.get("owner"):
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            entry = native_targets(me["id"])
            if entry.get("targets"):
                break
            foes = [u for u in (d.get("units") or [])
                    if u.get("owner") != me.get("owner") and u.get("alive")]
            if not foes:
                break
            goal = min(foes, key=lambda e: hexgeo.distance(_upos(me), _upos(e)))
            mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            for who in (me["id"], (find(d, ALLY) or {}).get("id")):
                if who is None:
                    continue
                mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == who), None)
                tiles = [(t["col"], t["row"]) for t in ((mu or {}).get("tiles") or [])
                         if t.get("col") is not None]
                if tiles:
                    best = min(tiles, key=lambda t: (hexgeo.distance(t, _upos(goal)), t))
                    rpc("applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": who,
                        "to": {"col": best[0], "row": best[1]}}}, 60)
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

        d0 = dv()
        ob0 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap0 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        me = find(d0, CASTER)
        uid = int(me["id"])
        team_by_id = {u.get("id"): u.get("owner") for u in (d0.get("units") or [])}
        my_team = me.get("owner")
        print("rid=%s board=%s caster=u%s@%s ally=u%s" % (
            rid, args.board, uid, _upos(me), (find(d0, ALLY) or {}).get("id")))

        # (1) NATIF
        nat = [(t.get("kind"), t.get("targetId")) for t in (entry.get("targets") or [])]
        nat_enemy = [t for (k, t) in nat if k == "unit" and team_by_id.get(t) not in (None, my_team)]
        print("1) NATIF abilityTargets(1100).targets = %s" % (nat,))
        print("   dont ENNEMIS : %s" % (nat_enemy,))

        # (2) LIVE decisionView.attackPlans
        plan = next((p for p in (d0.get("attackPlans") or []) if p.get("unitId") == uid), {})
        live = [(e.get("targetId"), e.get("rankCount")) for e in (plan.get("evals") or [])
                if e.get("abilityId") == FACADE]
        live_nonzero = [t for (t, rk) in live if rk]
        print("2) LIVE attackPlans (1100, ennemi) -> (targetId, rankCount) = %s" % (live,))
        print("   avec rankCount > 0 : %s" % (live_nonzero,))

        # (3) OFFLINE state_bridge
        st = load_state(d0, ob0, snap0, board=board)
        off_at = ability_targets_offline(st, uid, FACADE)
        off_t = [(t.get("kind"), t.get("targetId"))
                 for u in (off_at.get("units") or []) if u.get("unitId") == uid
                 for a in (u.get("abilities") or []) if a.get("abilityId") == FACADE
                 for t in (a.get("targets") or [])]
        ctx = build_from_state(st, uid)
        off_pairs = sorted({(e.get("abilityId"), e.get("targetId"))
                            for e in ((ctx.plans.get(uid) or {}).get("evals") or [])
                            if e.get("abilityId") == FACADE})
        print("3) OFFLINE ability_targets_offline(1100) = %s" % (off_t,))
        print("   OFFLINE plans (1100, cible) = %s" % (off_pairs,))

        # CONTRE-MESURE « AVANT le fix » : on DESARME le veto natif (le predicat rend False, comme
        # quand aucun masque n'est RE-lu) et on re-derive les memes deux ensembles. L'ecart mesure
        # ICI, dans le meme etat de bataille, est exactement ce que le fix retire.
        import engine.ai.state_bridge as SB
        _keep = SB._refuses_all_enemy_targets
        try:
            SB._refuses_all_enemy_targets = lambda _aid: False
            pre_at = SB.ability_targets_offline(st, uid, FACADE)
            pre_t = [(t.get("kind"), t.get("targetId"))
                     for u in (pre_at.get("units") or []) if u.get("unitId") == uid
                     for a in (u.get("abilities") or []) if a.get("abilityId") == FACADE
                     for t in (a.get("targets") or [])]
            pre_ctx = SB.build_from_state(st, uid)
            pre_pairs = sorted({(e.get("abilityId"), e.get("targetId"))
                                for e in ((pre_ctx.plans.get(uid) or {}).get("evals") or [])
                                if e.get("abilityId") == FACADE})
            pre_dec = DefaultAiUnitTactic().calculate_next_action(pre_ctx)
        finally:
            SB._refuses_all_enemy_targets = _keep
        print("   [AVANT fix] ability_targets_offline(1100) = %s" % (pre_t,))
        print("   [AVANT fix] plans (1100, cible)           = %s" % (pre_pairs,))

        # (4) DECISION offline du spine (`DefaultAiUnitTactic`) -- ce que le fix change VRAIMENT
        #     pour un entrainement : l'action retenue.
        dec = DefaultAiUnitTactic().calculate_next_action(build_from_state(st, uid))
        print("4) DECISION offline APRES fix = %s" % (dec,))
        print("   DECISION offline AVANT fix = %s" % (pre_dec,))

        # (5) FACE EXECUTION (`engine.runner.operations.summon_ai._apply_active_ability`) : on FORCE
        #     le cast (1100, ENNEMI) -- celui que le natif refuse -- et on lit le ROUTAGE. Avant le
        #     fix, le repli generique `AttackWithAttackDamage` frappait l'ennemi ; apres, l'ability
        #     retombe sur le no-op documente des abilities non portees.
        from engine.runner.operations import summon_ai as SA
        foe = next((u["id"] for u in (d0.get("units") or [])
                    if u.get("alive") and u.get("owner") != my_team), None)

        from engine.runner.components import HealthComponent, PositionComponent

        def _hp(state_, who):
            e = state_.get_entity(int(who))
            hc = e.get_component(HealthComponent) if e is not None else None
            return None if hc is None else hc.hp

        def _force(state_):
            # DEPLACER le caster AU CONTACT de la cible (on force la configuration, on ne la subit
            # pas) : le repli generique resout sa portee comme une attaque d'ability.
            fe = state_.get_entity(int(foe))
            fp = fe.get_component(PositionComponent) if fe is not None else None
            ce = state_.get_entity(uid)
            cp = ce.get_component(PositionComponent) if ce is not None else None
            occupied = {(p.col, p.row) for e in state_.entities.values()
                        for p in (e.get_component(PositionComponent),) if p is not None}
            if fp is not None and cp is not None and board is not None:
                tid = board.id_at(fp.col, fp.row)
                for n in (board.neighbours(tid) if tid is not None else []):
                    c, r_ = board.coord(n)
                    if (c, r_) not in occupied and board.walkable(n):
                        cp.col, cp.row = c, r_
                        break
            before = _hp(state_, foe)
            r = SA._apply_active_ability(state_, uid, int(foe), FACADE)
            after = _hp(state_, foe)
            dmg = None if (before is None or after is None) else (before - after)
            return r.get("routed"), "pv cible %s -> %s (degat=%s)" % (before, after, dmg)

        st_a = load_state(d0, ob0, snap0, board=board)
        route_after = _force(st_a)
        st_b = load_state(d0, ob0, snap0, board=board)
        try:
            SA._is_active_attack_ability = (
                lambda _aid, _f=SA._is_active_attack_ability: True if _aid == FACADE else _f(_aid))
            route_before = _force(st_b)
        finally:
            pass
        print("5) EXECUTION forcee (1100, ennemi u%s) APRES fix = %s" % (foe, route_after))
        print("   EXECUTION forcee (1100, ennemi u%s) AVANT fix = %s" % (foe, route_before))

        ok_live = not live_nonzero
        ok_off = not off_pairs
        ok_nat = not nat_enemy
        print("")
        print("natif SANS cible ennemie   : %s" % ("OK" if ok_nat else "ECHEC"))
        print("live attackPlans rank 0    : %s" % ("OK" if ok_live else "ECHEC"))
        print("offline SANS paire ennemie : %s" % ("OK" if ok_off else "ECHEC"))
        rc = 0 if (ok_nat and ok_live and ok_off) else 1
        print("VERDICT : %s" % ("OK" if rc == 0 else "ECHEC"))
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:                                # noqa: BLE001
            pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
