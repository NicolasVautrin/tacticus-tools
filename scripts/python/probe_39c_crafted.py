"""Probe #39c — scenario DISCRIMINANT crafte : Judh (genesKelermorph) cote A-UNITS (team 2),
cibles Hero groupees (necroWarden x2 p-units TENUES adjacentes et immobiles), SANS source
de perturbation du compteur TurnsStarted (pas de custoKyrus/1202).

Deroule :
  - p-steps (team 1, wardens) : PILOTES par le probe (moves scriptes pour rester adjacents
    et a portee de Judh, sinon finish) — jamais l'IA.
  - a-steps (team 2, Judh) : decision NATIVE (aiStepDryRun) appliquee telle quelle.
  - a chaque decision de Judh : turnsStarted, etat 1180 (usable/fromHere/targets), gate2
    (l'autre warden adjacent a la cible), action native.

Hypotheses departagees :
  H_perplayer (port actuel)   : le natif n'emet JAMAIS 1180 (Judh team 2).
  H_turnsgate (slot-4 ts>1)   : le natif EMET 1180 au tour >= 2 de Judh des que cibles+gates OK.

Usage : python probe_39c_crafted.py --runner <rid> [--max-steps 30]
(build prealable : rl_duel build --seed 4242 --board MC1_67
   --p-units necroWarden,necroWarden --a-units genesKelermorph --state-file <propre>)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import hexgeo  # noqa: E402


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


AB = 1180
JUDH_VID = "genesKelermorph"


def dv_units(sid, rid):
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
    return dv.get("units") or []


def ts_all(sid, rid):
    snap = _r(sid, "combatSnapshot", {"runnerId": rid})
    return {u.get("entityId"): int((u.get("stats") or {}).get("turnsStarted") or 0)
            for u in (snap.get("units") or [])
            if (u.get("stats") or {}).get("turnsStarted") is not None}


def ab_state(sid, rid, uid):
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
    ap.add_argument("--max-steps", type=int, default=30)
    args = ap.parse_args()
    sid = _resolve_session()
    rid = args.runner

    units = dv_units(sid, rid)
    jid = next(u["id"] for u in units if u.get("visualId") == JUDH_VID)
    wardens = [u["id"] for u in units if u.get("visualId") == "necroWarden"]
    print("judh=%s wardens=%s" % (jid, wardens))

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

        units = dv_units(sid, rid)
        pos = {u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in units
               if (u.get("pos") or {}).get("col") is not None}

        if uid in wardens:
            # p-step SCRIPTE : approcher Judh en restant adjacents entre wardens ; sinon finish.
            me = pos.get(uid)
            other = next((w for w in wardens if w != uid), None)
            opos = pos.get(other)
            jpos = pos.get(jid)
            mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
            mine = next((u for u in (mov.get("units") or []) if u.get("unitId") == uid), {})
            tiles = [(t["col"], t["row"]) for t in (mine.get("tiles") or [])]
            best = None
            for t in tiles:
                if opos is not None and hexgeo.distance(t, opos) != 1:
                    continue     # rester ADJACENT a l'autre warden (gate2 garanti)
                dj = hexgeo.distance(t, jpos) if jpos else 99
                if best is None or dj < best[1]:
                    best = (t, dj)
            acts = []
            if best is not None and best[0] != me and (jpos is None or best[1] < (hexgeo.distance(me, jpos) if me and jpos else 99)):
                acts.append({"kind": "move", "unitId": uid,
                             "to": {"col": best[0][0], "row": best[0][1]}})
            acts.append({"kind": "finish", "unitId": uid})
            print("step %2d WARDEN u%s scripted %s" % (step, uid, acts[0] if len(acts) > 1 else "finish"))
            _r(sid, "applyAction", {"runnerId": rid, "actions": acts}, 40)
            continue

        kinds = [(m.get("cls", "?")[:6], m.get("abilityType"), m.get("targetId")) for m in msgs]
        if uid == jid:
            ts = ts_all(sid, rid)
            st = ab_state(sid, rid, jid)
            wpos = {w: pos.get(w) for w in wardens}
            wadj = (len(wardens) == 2 and all(p is not None for p in wpos.values())
                    and hexgeo.distance(*wpos.values()) == 1)
            print("step %2d JUDH ts=%s state1180=%s wardens=%s adj=%s" % (
                step, ts.get(jid), st, wpos, wadj))
            print("          NATIVE: %s" % kinds)
            if any(m.get("abilityType") == AB for m in msgs):
                emitted = (step, ts.get(jid))
                print("  >>> NATIF EMET 1180 COTE A-UNITS (ts=%s) <<<" % ts.get(jid))
                break
        else:
            print("step %2d u%s %s" % (step, uid, kinds))

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
        print("VERDICT: H_perplayer REFUTEE - natif emet 1180 team 2 (step %s, ts=%s)" % emitted)
    else:
        print("VERDICT: pas d'emission 1180 sur ce walk")


if __name__ == "__main__":
    main()
