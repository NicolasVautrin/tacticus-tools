#!/usr/bin/env python
"""Probe #49 : DIAGNOSTIC du overfire Gauntlets(1000) 31337 s14 (u87 Calgar).

Hypothese Unobscured REFUTEE (re-expert #8 : arc natif (5,4) = 3 = le notre, aucun ring-2
obscurci sur MC1_67). Suspect n1 : Gauntlets INDISPONIBLE au s14 (cooldown/munitions ou
effet famille `_CantUseAbility`) que notre moteur croit castable — le dispatch NC
(`choose_action`, noncomparable/__init__.py:139) filtre `usable is False` mais n'applique
PAS `can_use_ability` (gate effets porte en 62d0442 pour le path Comparable seulement).

Ce probe walke 31337 jusqu'au s14 et dump la VERITE dv de u87 :
  - action native du pas (attendu : move (3,4) + 69->81, PAS 1000)
  - entree abilities id=1000 BRUTE (usable, cooldown, munitions, tout champ present)
  - effets ACTIFS de u87 (recherche suffixe _CantUseAbility)

Usage: python probe_49_gauntlets.py [--seed 31337] [--stop-step 14] [--uid 87]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine_validate import native_chunk  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_49gnt_state.json"


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int) -> int:
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[49gnt] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=31337)
    ap.add_argument("--stop-step", type=int, default=14)
    ap.add_argument("--uid", type=int, default=87)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed)
    print(f"[49gnt] seed={args.seed} runner={rid} -> walk jusqu'au pas {args.stop_step}")

    try:
        stop_dry = None
        for step in range(args.stop_step + 1):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[49gnt] natif epuise au pas {step} ({dry.get('error')})")
                return 3
            if step == args.stop_step:
                stop_dry = dry
                break
            acts = []
            for m in (dry["action"]["messages"] or []):
                if m.get("cls") == "MoveUnitMessage":
                    acts.append({"kind": "move", "unitId": m["unitId"],
                                 "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
                elif m.get("cls") == "ActiveAbilityMessage":
                    acts.append({"kind": "ability", "casterId": m["casterId"],
                                 "targetId": m.get("targetId"),
                                 "abilityType": m["abilityType"]})
                elif m.get("cls") == "FinishUnitTurnMessage":
                    acts.append({"kind": "finish", "unitId": m["unitId"]})
            if acts:
                _r(sid, "applyAction", {"runnerId": rid, "actions": acts}, 60)

        nat = native_chunk(stop_dry.get("action") or {})
        print(f"[49gnt] pas {args.stop_step} natif: ability={nat.get('ability')} "
              f"move={nat.get('move')}")

        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1}, 60)
        me = next((u for u in (dv.get("units") or []) if u.get("id") == args.uid), None)
        if me is None:
            print(f"[49gnt] u{args.uid} absent du decisionView")
            return 4
        print(f"[49gnt] u{args.uid} pos={me.get('pos')} visual={me.get('visualId')}")
        print("[49gnt] --- abilities (BRUT) ---")
        for ab in (me.get("abilities") or []):
            print("   ", json.dumps(ab, ensure_ascii=True))
        print("[49gnt] --- effets ACTIFS ---")
        cant = []
        for e in (me.get("effects") or []):
            nm = str(e.get("name") or "")
            print(f"    {nm} remaining={e.get('remaining')} src={e.get('source')} "
                  f"lvl={e.get('level')} type={e.get('effectType')}")
            if nm.endswith("_CantUseAbility"):
                cant.append(nm)
        print(f"[49gnt] VERDICT effets bloquants actives: {cant if cant else 'AUCUN'}")
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            print(f"[49gnt] runner {rid} dispose")
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
