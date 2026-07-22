#!/usr/bin/env python
"""Probe #60 — trait Swarm face ATTAQUANT (hits = membres vivants) + heal-limit GroupUnit.

Design (pool rank 17 : pas de swarm lineup -> le swarm arrive par SUMMON) :
P = necroSpyder (ScarabHive 1007 -> 2x necroSmnSwarm 5 membres Mechanical Swarm ; porte aussi
Repair 28 GRANTED via trait Mechanic = le chemin Comparable-repair generique) + admecManipulus
(Repair_GalvanicField 1119, bespoke #85) ; A = bloodSanguinary (3h Chain melee). Le member-cap
DEFENSE (#57d, natif) borne chaque coup a une frontiere de membre -> apres l'attaque de sang le
hp du scarab atterrit sur une frontiere et k membres sont morts ; LivingMetal (regen % debut de
tour) fait REVIVRE des membres -> variation des deux sens.

Phases : (1) APPROCHE — avancer le spyder vers sang jusqu'a ce que ScarabHive ait une cible
legale (abilityTargets) ; (2) CAST 1007 -> scarabs ; (3) MESURE a chaque debut de tour P :
 (a) GROUND TRUTH formule : statDelta.extraHits natif du scarab == -min(n_base-1, membres
     manquants) (`SwarmAbility.CreateBehaviour @181225e20`) ; manquants lus du stat 20
     (numberOfMembers Current/delta) ET rederives du hp (`group_unit_stat_part(4, hpMax, n, hp)`
     mirror @180ed3929/@180f9b3a0) -> doivent coincider (derivation hp->membres == champ
     maintenu natif +0x18).
 (b) ATTRIBUTION : apres build_predictor, le stat-17 du scarab est EXPLIQUE par
     SWARM_HIT_REDUCTION_SOURCE (residu CAPTURED_SOURCE == 0) — validation non-circulaire de
     l'attribution d'hydratation (unit_context.from_snapshot #60).
 (c) AGREMENT rows : attaques normales rankees du scarab vs sang, oracle natif == offline
     (TOL 3) — hits reduits (5-k) couverts bout en bout.
 (d) HEAL-LIMIT (discriminant du flag) : rows repair (spyder 28 / manipulus 1119) vs le scarab
     endommage. `PredictHeal/PredictRepair @181037180/@181038280` gatent le cap groupe par un
     flag d'appel : hp sur une frontiere de membre => group_limit ~0 => fill capee ~0 (flag=1)
     vs fill=min(amt, missing)>0 (flag=0). Rows natives imprimees + les 2 hypotheses -> le flag
     observe fixe _HEAL_GROUP_CAP/_REPAIR_GROUP_CAP (action_generators).

ASCII only (cp1252). Usage: python probe_60_swarm.py [--seed 60001] [--max-rounds 10]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.playbook import scene as SC  # noqa: E402
from engine.playbook.scene import Scene  # noqa: E402
from engine.playbook import prediction  # noqa: E402
from engine.entities.stats import StatType, CAPTURED_SOURCE  # noqa: E402
from engine.entities.effects.loki.hits import SWARM_HIT_REDUCTION_SOURCE  # noqa: E402
from engine.services.trait_damage_limits import (  # noqa: E402
    group_unit_stat_part, get_group_unit_heal_limit, is_at_group_unit_heal_limit)

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "_60_swarm_state.json"
TOL = 3
P_UNITS = "necroSpyder,admecManipulus"
A_UNITS = "bloodSanguinary"
W, H = 7, 9
MV = {"necroSpyder": 3, "admecManipulus": 3, "necroSmnSwarm": 4}
SPY_VIS, MAN_VIS, SANG_VIS, SWARM_VIS = ("necroSpyder", "admecManipulus",
                                         "bloodSanguinary", "necroSmnSwarm")
SCARAB_HIVE = 1007


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int) -> int:
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67",
         "--p-units", P_UNITS, "--a-units", A_UNITS,
         "--hp-target", "40000"],   # sang tanke le chip des scarabs (splits + act-on-appearance)
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[60] build KO: {(proc.stderr or proc.stdout or '')[-400:]}", file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def _alive(dv: dict) -> list[dict]:
    return [u for u in (dv.get("units") or []) if u.get("alive")]


def _by_vis(dv: dict, vis: str) -> list[dict]:
    return [u for u in _alive(dv) if u.get("visualId") == vis]


def _pos(u: dict) -> tuple:
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _snap_unit(snap: dict, eid: int) -> dict:
    return next((u for u in (snap.get("units") or []) if u.get("entityId") == eid), {})


def _collect_rows(dec: dict, predictor: dict, scene, att_id: int, tgt_id: int,
                  tgt_pos: tuple) -> list[dict]:
    rows = []
    for apl in (dec.get("attackPlans") or []):
        if apl.get("unitId") != att_id or att_id not in predictor["ctx_by_id"]:
            continue
        norm_ids = {ab.get("id") for u in (dec.get("units") or []) if u.get("id") == att_id
                    for ab in (u.get("abilities") or []) if ab.get("kind") == "normal"}
        for ev in (apl.get("evals") or []):
            if ev.get("targetId") != tgt_id:
                continue
            if norm_ids and ev.get("abilityId") not in norm_ids:
                continue
            for rk in (ev.get("ranked") or []):
                if rk.get("dmgMax") is None or rk.get("col") is None:
                    continue
                tile = (rk["col"], rk["row"])
                ev_off = prediction.make_normal_attack_predictions(scene, att_id, tgt_id, tile)
                res = ev_off.prediction.accurate_health_damage
                rows.append({"tile": tile, "d_tgt": hexgeo.distance(tile, tgt_pos),
                             "oracle": (rk.get("dmgMin"), rk.get("dmgMax")),
                             "offline": (res.min, res.max)})
    return rows


def _agree(r: dict) -> bool:
    return max(abs(r["oracle"][0] - r["offline"][0]),
               abs(r["oracle"][1] - r["offline"][1])) <= TOL


def _repair_rows(dec: dict, caster_ids: list[int], swarm_id: int) -> list[dict]:
    out = []
    for apl in (dec.get("attackPlans") or []):
        if apl.get("unitId") not in caster_ids:
            continue
        for ev in (apl.get("evals") or []):
            if ev.get("targetId") == swarm_id and ev.get("abilityId") != 69:
                out.append({"caster": apl.get("unitId"), **{k: ev.get(k) for k in
                            ("abilityId", "utility", "value", "score", "ranked") if k in ev}})
    return out


def _move(rpc, rid, uid, cur, goal, occupied, mv) -> tuple:
    cands = [t for t in hexgeo.disk(cur[0], cur[1], mv)
             if 0 <= t[0] < W and 0 <= t[1] < H and t not in occupied and t != cur]
    cands.sort(key=lambda t: (hexgeo.distance(t, goal), hexgeo.distance(t, cur)))
    for t in cands[:12]:
        try:
            r = rpc("applyAction", {"runnerId": rid, "actions": [
                {"kind": "move", "unitId": uid, "to": {"col": t[0], "row": t[1]}}]}, 60)
        except Exception:
            continue
        if isinstance(r, dict) and r.get("ok", True) and not r.get("error"):
            return t
    return cur


def _finish(rpc, rid, uid) -> None:
    try:
        rpc("applyAction", {"runnerId": rid, "actions": [{"kind": "finish", "unitId": uid}]}, 60)
    except Exception:
        pass


def _aiturn() -> None:
    subprocess.run([sys.executable, "rl_duel.py", "aiturn", "--state-file", str(STATE)],
                   cwd=str(PYDIR), capture_output=True, text=True,
                   encoding="utf-8", errors="replace")


def _endturn(rpc, rid) -> None:
    """FIN DE TOUR explicite (reserve deliberee) : les scarabs non-agis ne splittent NI n'attaquent
    (ScarabSummon/attaque = a l'ACTIVATION) -> aiturn ne joue que le tour ENNEMI."""
    try:
        rpc("applyAction", {"runnerId": rid, "actions": [{"kind": "endturn"}]}, 60)
    except Exception:
        pass


def _repair_eligibility(rpc, rid, caster_ids: list[int], swarm_id: int) -> dict:
    """GROUND TRUTH eligibilite (`EntityCanBeHealed/Repaired @181054fa0/@181055080` cote natif) :
    pour chaque repairer, le scarab est-il dans les cibles legales de ses abilities repair ?"""
    out = {}
    for cid in caster_ids:
        try:
            at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid}, 60)
        except Exception:
            continue
        for u in (at.get("units") or []):
            for ab in (u.get("abilities") or []):
                if ab.get("kind") == "normal":
                    continue
                tgts = {t.get("targetId") for t in (ab.get("targets") or [])}
                out[f"u{cid}:{ab.get('abilityId')}"] = (swarm_id in tgts)
    return out


def _hive_target(rpc, rid, spy_id: int) -> tuple:
    """(targetId legal de ScarabHive SANS bouger, targetId AVEC move) — None si aucun."""
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": spy_id}, 60)
    for u in (at.get("units") or []):
        for ab in (u.get("abilities") or []):
            if ab.get("abilityId") != SCARAB_HIVE:
                continue
            fh = [t.get("targetId") for t in (ab.get("fromHere") or [])
                  if t.get("targetId") is not None]
            tg = [t.get("targetId") for t in (ab.get("targets") or [])
                  if t.get("targetId") is not None]
            return (fh[0] if fh else None, tg[0] if tg else None)
    return (None, None)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=60001)
    ap.add_argument("--max-rounds", type=int, default=10)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed)
    rpc = lambda m, b, t=90: _r(sid, m, b, t)   # noqa: E731
    print(f"[60] seed={args.seed} runner={rid}")
    n_gt = n_gt_ok = n_attr = n_attr_ok = 0
    all_rows, ks_seen = [], set()
    hive_cast = False
    try:
        dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        ids = {v: (_by_vis(dv0, v) or [{}])[0].get("id") for v in (SPY_VIS, MAN_VIS, SANG_VIS)}
        if any(x is None for x in ids.values()):
            print(f"[60] roster KO ({ids})"); return 2
        spy, man, sang = ids[SPY_VIS], ids[MAN_VIS], ids[SANG_VIS]
        print(f"[60] spyder=u{spy} manipulus=u{man} sang=u{sang} cp={dv0.get('currentPlayer')}")

        for rnd in range(args.max_rounds):
            dec = rpc("decisionView", {"runnerId": rid, "maxRank": 99, "allAbilities": True}, 120)
            if not _by_vis(dec, SANG_VIS):
                print(f"[60] sang mort round {rnd} -> stop"); break
            spy_u = (_by_vis(dec, SPY_VIS) or [None])[0]
            sang_u = _by_vis(dec, SANG_VIS)[0]
            swarms = _by_vis(dec, SWARM_VIS)
            sp = _pos(sang_u)

            # phase CAST : des que ScarabHive a une cible legale
            if not hive_cast and spy_u is not None:
                fh, tg = _hive_target(rpc, rid, spy)
                if fh is not None:
                    r = rpc("applyAction", {"runnerId": rid, "actions": [
                        {"kind": "ability", "casterId": spy, "targetId": fh,
                         "abilityType": SCARAB_HIVE}]}, 90)
                    ok = isinstance(r, dict) and not r.get("error")
                    print(f"[60] r{rnd}: CAST ScarabHive -> u{fh} ok={ok}")
                    hive_cast = ok
                    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 99,
                                               "allAbilities": True}, 120)
                    swarms = _by_vis(dec, SWARM_VIS)
                else:
                    print(f"[60] r{rnd}: approche (hive sans cible, tg-avec-move={tg})")

            # phase MESURE sur chaque scarab vivant
            snap = rpc("combatSnapshot", {"runnerId": rid}, 40) if swarms else None
            predictor = SC.build_predictor(rpc, rid) if swarms else None
            scene = None
            if predictor is not None:
                sctx = SC.step_context(predictor, dec)
                scene = Scene.from_predictor_sctx(predictor, sctx, None)
            for sw in swarms:
                swid = sw["id"]
                su = _snap_unit(snap, swid)
                st, sd = su.get("stats") or {}, su.get("statDelta") or {}
                n_cur = int(st.get("numberOfMembers") or 0)
                d_n = int(sd.get("numberOfMembers") or 0)
                n_base = n_cur - d_n
                missing_stat = -d_n
                d_xh = int(sd.get("extraHits") or 0)
                xh_cur = int(st.get("extraHits") or 0)
                hp = int(st.get("health") or 0)
                hp_max = hp - int(sd.get("health") or 0)
                missing_hp = group_unit_stat_part(4, hp_max, n_base, hp) if n_base > 1 else 0
                exp_mod = -min(n_base - 1, missing_stat) if n_base > 1 else 0
                gt_ok = (d_xh == exp_mod) and (missing_hp == missing_stat)
                n_gt += 1
                n_gt_ok += int(gt_ok)
                ks_seen.add(missing_stat)
                print(f"[60] r{rnd} scarab u{swid}: hp={hp}/{hp_max} members={n_cur}/{n_base} "
                      f"missing stat={missing_stat} hp-derive={missing_hp} "
                      f"xh={xh_cur} delta={d_xh} attendu={exp_mod} "
                      f"{'OK' if gt_ok else '** GT MISS **'}")
                ctx = (predictor or {}).get("ctx_by_id", {}).get(swid)
                comp = ctx.stats.components.get(int(StatType.EXTRA_HITS)) if ctx else None
                if comp is not None:
                    srcs = dict(comp.modification.per_source)
                    residual = srcs.get(CAPTURED_SOURCE, 0)
                    part = srcs.get(SWARM_HIT_REDUCTION_SOURCE, 0)
                    cur_off = ctx.stats.get_stat(int(StatType.EXTRA_HITS), 0)
                    attr_ok = (residual == 0 and part == d_xh and cur_off == xh_cur)
                    n_attr += 1
                    n_attr_ok += int(attr_ok)
                    print(f"[60]   attr: part={part} residuel={residual} cur={cur_off} "
                          f"(natif {xh_cur}) nMembers(ctx)={ctx.number_of_members} "
                          f"{'OK' if attr_ok else '** ATTR MISS **'}")
                if scene is not None:
                    rows = _collect_rows(dec, predictor, scene, swid, sang, sp)
                    for x in rows:
                        x["rnd"], x["k"] = rnd, missing_stat
                    all_rows += rows
                # heal-limit : eligibilite native + PredictRepair NATIF invoque en direct
                # (`aiPlaybookPredict` famille repairs + scorer `pairUtility`) vs les 2 hypotheses
                # (cap groupe ON/OFF). A une frontiere de membre : glim=0 -> cap ON => fill 0 /
                # utilite 0 ; cap OFF => fill=min(amt, missingHp)>0. Discriminant DIRECT du flag.
                if missing_stat > 0 and n_base > 1:
                    glim = get_group_unit_heal_limit(hp_max, n_base, hp)
                    at_lim = is_at_group_unit_heal_limit(hp_max, n_base, hp)
                    rrows = _repair_rows(dec, [spy, man], swid)
                    elig = _repair_eligibility(rpc, rid, [spy, man], swid)
                    print(f"[60]   repair: missingHp={hp_max - hp} group_limit={glim} "
                          f"at_limit={at_lim} elig={elig} rows={json.dumps(rrows)[:400]}")
                    for cid, abid in ((spy, 28), (man, 1119)):
                        try:
                            pp = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": cid,
                                                           "targetId": swid, "abilityType": abid}, 60)
                            pu = rpc("pairUtility", {"runnerId": rid, "unitId": cid,
                                                     "targetId": swid, "abilityType": abid}, 60)
                        except Exception as e:
                            print(f"[60]   predict u{cid} ab{abid} KO: {e}")
                            continue
                        print(f"[60]   NATIF u{cid} ab{abid}: repairs="
                              f"{json.dumps(pp.get('repairs'))[:300]} "
                              f"pairUtility={pu.get('utility')} (err={pu.get('error')})")

            # tour P : scarab-1 (mesure) colle a sang, les autres scarabs s'ECARTENT (pas d'attaque
            # groupee -> sang survit et ne tape QUE le scarab mesure) ; spyder approche tant que le
            # hive n'est pas caste ; puis ENDTURN explicite (reserve : les non-agis ne splittent pas).
            occupied = {_pos(u) for u in _alive(dec)}
            if swarms:
                sw0 = swarms[0]
                cur = _pos(sw0)
                if hexgeo.distance(cur, sp) > 1:
                    ring1 = [t for t in hexgeo.ring(sp[0], sp[1], 1)
                             if 0 <= t[0] < W and 0 <= t[1] < H and t not in occupied]
                    if ring1:
                        goal = min(ring1, key=lambda t: hexgeo.distance(t, cur))
                        _move(rpc, rid, sw0["id"], cur, goal, occupied, MV[SWARM_VIS])
                far = (0, 0)
                for u in swarms[1:]:
                    cu = _pos(u)
                    if hexgeo.distance(cu, sp) <= 2:
                        _move(rpc, rid, u["id"], cu, far, occupied, MV[SWARM_VIS])
            if spy_u is not None and not hive_cast:
                _move(rpc, rid, spy, _pos(spy_u), sp, occupied, MV[SPY_VIS])
            _endturn(rpc, rid)
            _aiturn()

        print(f"[60] ks couverts (membres manquants observes): {sorted(ks_seen)}")
        bad = [x for x in all_rows if not _agree(x)]
        for x in all_rows:
            print(f"  r{x['rnd']} k={x['k']} tile={x['tile']} d_tgt={x['d_tgt']} "
                  f"oracle={x['oracle']} offline={x['offline']} "
                  f"{'OK' if _agree(x) else '** MISS **'}")
        print(f"[60] BILAN: groundtruth {n_gt_ok}/{n_gt} | attribution {n_attr_ok}/{n_attr} | "
              f"rows {len(all_rows) - len(bad)}/{len(all_rows)}")
        if n_gt_ok != n_gt or n_attr_ok != n_attr or bad:
            return 1
        if not (ks_seen - {0}):
            print("[60] /!\\ AUCUN membre mort observe -> scenario non discriminant"); return 4
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 15)
            print(f"[60] runner {rid} dispose")
        except Exception as e:
            print(f"[60] dispose KO: {e}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
