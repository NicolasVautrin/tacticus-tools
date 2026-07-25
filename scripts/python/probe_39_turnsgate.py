"""Probe #39 (fable-solver) — discriminant per-JOUEUR vs turnsStarted>1 pour 1180 HeroicFusillade.

Contexte (case-31 demi-partie A) : le verdict historique « le natif n'emet JAMAIS 1180 cote
a-units » repose sur 4 experiences ou « camp de Judh » etait CONFONDU avec « numero de tour de
Judh » (a-units => toujours mesure au 1er tour ; p-units => tour >= 2). Le slot-4
`ShouldEvaluate(unit)` de HeroicFusilladePlaybook (corps folde IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$ShouldEvaluate, decouvert en #46)
gate `GetStat(unit, 0xc=TurnsStarted) > 1` — il bloque 1180 au 1er tour de l'unite QUEL QUE
SOIT le camp.

Ce probe rejoue le scenario canonique (seed 909, board MC1_67, rosters defaut — Judh u85
a-units) et pousse le walk JUSQU'AU 2e TOUR de Judh, cote a-units, en verifiant a chaque
decision de Judh :
  - turnsStarted(u85) (via combatSnapshot / stat 12) ;
  - etat 1180 (usable / fromHere / targets) ;
  - gate2 natif (>=1 p-unit adjacente a la cible Hero) calcule sur les VRAIES positions ;
  - la decision native (aiStepDryRun).

Verdict attendu si l'hypothese turnsStarted est la bonne : au tour 2 de Judh (turnsStarted=2),
avec cibles legales + gate2 vrai, le natif EMET 1180 DEPUIS LE CAMP A-UNITS => gate per-joueur
REFUTE (artefact experimental), mecanisme reel = slot-4 turnsStarted>1 (deja porte).

Usage : python probe_39_turnsgate.py --runner <rid> [--max-steps 40]
(runner deja construit : rl_duel build --seed 909 --board MC1_67 --state-file <propre>)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import hexgeo  # noqa: E402


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


JUDH_VID = "genesKelermorph"
AB = 1180


def unit_rows(dv: dict) -> list:
    return dv.get("units") or []


def positions(dv: dict) -> dict:
    out = {}
    for u in unit_rows(dv):
        p = u.get("pos") or {}
        if p.get("col") is not None:
            out[u["id"]] = (p["col"], p["row"])
    return out


def judh_id(dv: dict) -> int | None:
    for u in unit_rows(dv):
        if u.get("visualId") == JUDH_VID:
            return u["id"]
    return None


def teams(dv: dict) -> dict:
    return {u["id"]: u.get("team") for u in unit_rows(dv)}


def turns_started(sid: int, rid: int, uid: int) -> int | None:
    """GetStat(unit, 12=TurnsStarted) via combatSnapshot (mirror engine.playbook.scene:
    units[].entityId + stats.turnsStarted)."""
    snap = _r(sid, "combatSnapshot", {"runnerId": rid})
    for u in (snap.get("units") or []):
        if u.get("entityId") == uid:
            st = u.get("stats") or {}
            if st.get("turnsStarted") is not None:
                return int(st["turnsStarted"])
    return None


def gate2_truth(dv: dict, caster: int) -> list:
    """Pour chaque ennemi du caster : (id, pos, #ennemis-du-caster adjacents a lui)."""
    pos = positions(dv)
    tm = teams(dv)
    my_team = tm.get(caster)
    enemies = [u for u, t in tm.items() if t not in (my_team, None) and u in pos]
    rows = []
    for t in enemies:
        others = [pos[e] for e in enemies if e != t]
        adj = sum(1 for p in others if hexgeo.distance(pos[t], p) == 1)
        rows.append((t, pos[t], adj))
    return rows


def ab_state(sid: int, rid: int, uid: int) -> dict:
    at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": uid, "abilityId": AB})
    for uu in (at.get("units") or []):
        if uu.get("unitId") != uid:
            continue
        for a in (uu.get("abilities") or []):
            if a.get("abilityId") == AB:
                return {"usable": a.get("usable"), "fromHereCount": a.get("fromHereCount"),
                        "targets": [t.get("targetId") for t in (a.get("targets") or [])
                                    if t.get("kind") == "unit"]}
    return {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, required=True)
    ap.add_argument("--max-steps", type=int, default=40)
    args = ap.parse_args()
    sid = _resolve_session()
    rid = args.runner

    emitted = None
    for step in range(args.max_steps):
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            print("step %2d: walk end (%s)" % (step, dry.get("error") or "no action"))
            break
        msgs = (dry.get("action") or {}).get("messages") or []
        uid = dry.get("activatedUnitId")
        if uid is None:
            for m in msgs:
                uid = m.get("unitId") or m.get("casterId")
                if uid is not None:
                    break
        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        jid = judh_id(dv)
        kinds = [(m.get("cls"), m.get("abilityType"), m.get("targetId")) for m in msgs]
        if uid == jid:
            ts = turns_started(sid, rid, jid)
            st = ab_state(sid, rid, jid)
            g2 = gate2_truth(dv, jid)
            print("step %2d: JUDH u%s turnsStarted=%s state1180=%s" % (step, jid, ts, st))
            print("          gate2 (ennemis de Judh, #allies-de-cible adjacents): %s" % g2)
            print("          NATIVE ACTION: %s" % kinds)
            used_1180 = any((k[1] == AB) for k in kinds)
            if used_1180:
                emitted = (step, ts, kinds)
                print("  >>> NATIF EMET 1180 COTE A-UNITS (turnsStarted=%s) <<<" % ts)
                break
        else:
            print("step %2d: u%s %s" % (step, uid, kinds))
        acts = []
        for m in msgs:
            if m.get("cls") == "MoveUnitMessage":
                acts.append({"kind": "move", "unitId": m["unitId"],
                             "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
            elif m.get("cls") == "ActiveAbilityMessage":
                acts.append({"kind": "ability", "casterId": m["casterId"],
                             "targetId": m.get("targetId"), "abilityType": m["abilityType"]})
            elif m.get("cls") == "FinishUnitTurnMessage":
                acts.append({"kind": "finish", "unitId": m["unitId"]})
        if acts:
            _r(sid, "applyAction", {"runnerId": rid, "actions": acts}, 40)

    print()
    if emitted:
        print("VERDICT: per-player gate REFUTE - natif emet 1180 team 2 au tour %s" % emitted[1])
    else:
        print("VERDICT: pas d'emission 1180 observee sur ce walk (voir etats ci-dessus)")


if __name__ == "__main__":
    main()
