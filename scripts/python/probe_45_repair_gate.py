#!/usr/bin/env python
"""Probe #45 : mesure DECISIVE repair-vs-attack sur u83 (admecDominus, seed 777 MC1_67).

Marche la trajectoire NATIVE (aiStepDryRun -> applyAction, mirror engine_validate) et
S'ARRETE PILE quand u83 est active en etant BLESSE (hp < hpMax) -- l'etat de la
divergence s4/s15 (le moteur offline choisit self-repair 28, le natif attaque 69).
A cet etat (AVANT apply), mesure au NATIF :
  - ncEvaluate(u83, 28, sweep) : Bucket du RepairPlaybook par position (util native du
    scorer CalculateUtilityFromPredictions -- vide => gate d'eligibilite interne) ;
  - ncEvaluate(u83, 69, sweep) : Bucket de l'attaque normale (util native) ;
  - aiPlaybookPredict(u83, 28, target=83) : fills natifs (hpFill/armorFill).
Sortie ASCII console + dump JSON data/_45_gate_probe.json.

Usage: python probe_45_repair_gate.py [--runner N] [--max-steps 40]
Pre-requis: session warmee + runner 777 fraichement construit (rl_duel build).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine_validate import native_chunk  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "data"


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def u_stat(sid: int, rid: int, squad: int) -> dict | None:
    obs = _r(sid, "observeBattle", {"runnerId": rid}, 30)
    for u in obs.get("units") or []:
        if u.get("squadId") == squad:
            return u
    return None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, required=True)
    ap.add_argument("--unit", type=int, default=83)
    ap.add_argument("--max-steps", type=int, default=40)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = args.runner
    uid = args.unit

    stop_dry = None
    for step in range(args.max_steps):
        me = u_stat(sid, rid, uid)
        if me is None:
            print(f"[probe45] u{uid} introuvable -- abort"); return 2
        if me.get("isDead"):
            print(f"[probe45] u{uid} MORT au pas {step} -- trajectoire perdue, rebuild requis")
            return 3
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            print(f"[probe45] natif epuise au pas {step} ({dry.get('error')})"); return 4
        nat = native_chunk(dry.get("action") or {})
        # Chunk COMPOSE : activatedUnitId peut etre None -> fallback sur l'unite
        # du chunk (mirror engine_validate.run_agreement).
        au = dry.get("activatedUnitId") or nat.get("unit")
        damaged = (me.get("hp") or 0) < (me.get("hpMax") or 0)
        print(f"  step {step:2}: next=u{au} nat={nat['ability'] or nat['move'] or 'finish'}"
              f"  u{uid}.hp={me.get('hp')}/{me.get('hpMax')} dmg={damaged}")
        if au == uid and damaged:
            stop_dry = dry
            print(f"[probe45] STOP au pas {step} : u{uid} active et blesse -- mesures")
            break
        acts = []
        for m in (dry["action"]["messages"] or []):
            if m.get("cls") == "MoveUnitMessage":
                acts.append({"kind": "move", "unitId": m["unitId"],
                             "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
            elif m.get("cls") == "ActiveAbilityMessage":
                acts.append({"kind": "ability", "casterId": m["casterId"],
                             "targetId": m.get("targetId"), "abilityType": m["abilityType"]})
            elif m.get("cls") == "FinishUnitTurnMessage":
                acts.append({"kind": "finish", "unitId": m["unitId"]})
        if acts:
            _r(sid, "applyAction", {"runnerId": rid, "actions": acts}, 60)
    if stop_dry is None:
        print("[probe45] condition jamais atteinte"); return 5

    me = u_stat(sid, rid, uid)
    rep = _r(sid, "ncEvaluate",
             {"runnerId": rid, "unitId": uid, "abilityType": 28, "sweep": True}, 180)
    atk = _r(sid, "ncEvaluate",
             {"runnerId": rid, "unitId": uid, "abilityType": 69, "sweep": True}, 180)
    fills = _r(sid, "aiPlaybookPredict",
               {"runnerId": rid, "unitId": uid, "targetId": uid, "abilityType": 28}, 120)
    # #45 mesure DECISIVE : le scoreur natif lui-meme (CalculateUtilityFromPredictions)
    # sur les DEUX paires, depuis la tuile courante.
    pu_rep = _r(sid, "pairUtility",
                {"runnerId": rid, "unitId": uid, "targetId": uid, "abilityType": 28}, 120)
    nat_ab = native_chunk(stop_dry.get("action") or {}).get("ability") or {}
    pu_atk = None
    if nat_ab.get("ability") is not None and nat_ab.get("target") is not None:
        pu_atk = _r(sid, "pairUtility",
                    {"runnerId": rid, "unitId": uid, "targetId": nat_ab["target"],
                     "abilityType": nat_ab["ability"]}, 120)

    def best(r: dict) -> str:
        out = []
        for p in (r.get("positions") or []):
            u = p.get("util")
            tag = ("empty" if p.get("bucket") == "empty"
                   else (f"{u:.3f}" if isinstance(u, (int, float)) else str(p.get("error"))))
            out.append(f"    pos={p.get('pos')} cur={p.get('cur')} hvt={p.get('hvt')} -> {tag}"
                       + (f" act={p.get('action')}" if p.get("action") else ""))
        return "\n".join(out) if out else "    (aucune position)"

    print(f"\n[probe45] u{uid} hp={me.get('hp')}/{me.get('hpMax')}"
          f" armor={me.get('armor')}/{me.get('armorMax')} pos=({me.get('col')},{me.get('row')})")
    print(f"[probe45] natif voulait: {native_chunk(stop_dry.get('action') or {})}")
    print(f"[probe45] REPAIR(28) playbook={rep.get('playbookClass')}:")
    print(best(rep))
    print(f"[probe45] ATTACK(69) playbook={atk.get('playbookClass')}:")
    print(best(atk))
    print(f"[probe45] fills natifs (28 self): count={fills.get('repairCount')}"
          f" repairs={fills.get('repairs')} err={fills.get('repairError')}")
    print(f"[probe45] pairUtility NATIF repair(28->self): {pu_rep.get('utility')}"
          f" (pb={pu_rep.get('playbookClass')} err={pu_rep.get('error')})")
    if pu_atk is not None:
        print(f"[probe45] pairUtility NATIF attack({nat_ab.get('ability')}->"
              f"{nat_ab.get('target')}): {pu_atk.get('utility')}"
              f" (pb={pu_atk.get('playbookClass')} err={pu_atk.get('error')})")

    out = {"unit": uid, "me": me, "stop_dry": stop_dry, "repair": rep, "attack": atk,
           "pairUtility": {"repair": pu_rep, "attack": pu_atk},
           "fills": {"repairCount": fills.get("repairCount"),
                     "repairs": fills.get("repairs"),
                     "repairError": fills.get("repairError")}}
    (DATA / "_45_gate_probe.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"[probe45] dump -> {DATA / '_45_gate_probe.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
