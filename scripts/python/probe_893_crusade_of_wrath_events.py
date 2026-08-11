"""#893 -- DUMP BRUT des evenements d'un cast de `1049 CrusadeOfWrath`.

Outil de MESURE (pas un test) : monte le runner nominal du confront live, joue le cast, et imprime
le flux d'evenements TAG PAR TAG. Il existe parce que les noms de tags ne se devinent pas -- c'est
lui qui a etabli que l'attaque normale gratuite n'emet PAS `Source_Id`, et que `mutated` rend
`False` sur un cast qui pose pourtant quatre effets.

Usage :
    python probe_893_crusade_of_wrath_events.py [--keep]
ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import probe_112_darkangels as PR                                          # noqa: E402
import probe_27_custom_utility_inventory as INV                            # noqa: E402

from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402

LOGS = HERE.parents[1] / "logs"
ABILITY = int(ActiveAbilityType.CrusadeOfWrath)
BOARD = "MC1_67"

PORTEUR = "templHelbrecht"
POS = {PORTEUR: (3, 4), "templSwordBrother": (4, 4), "astraBullgryn": (3, 6), "tauMarksman": (0, 4)}
POS_ENN = {"necroWarden": (2, 4), "necroSpyder": (5, 4)}


def _run(args) -> int:
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          check=False).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="#893 : dump brut des evenements du cast 1049")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    LOGS.mkdir(parents=True, exist_ok=True)
    p = Path(a.state_file) if a.state_file else (LOGS / "rs_893_events.json")

    args = ["build", "--seed", "893893", "--board", BOARD, "--rank", "17", "--no-ai",
            "--p-units", ",".join(POS), "--a-units", ",".join(POS_ENN),
            "--armor-target", "0", "--hp-target", "400000", "--state-file", str(p)]
    for vis, (c, r) in POS.items():
        args += ["--place", "%s:%d,%d" % (vis, c, r)]
    for vis, (c, r) in POS_ENN.items():
        args += ["--a-place", "%s:%d,%d" % (vis, c, r)]
    if _run(args) != 0 or not p.exists():
        print("[893] PAS MESURE : build KO")
        return 2

    rid = int(json.loads(p.read_text(encoding="utf-8"))["runnerId"])
    sid = INV._session_id()
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ids = {u.get("visualId"): u.get("id") for u in (dv.get("units") or [])}
        print("[893] runner=%d ids=%r" % (rid, ids))
        hel = ids[PORTEUR]
        abil = [x for u in (dv.get("units") or []) if u.get("id") == hel
                for x in (u.get("abilities") or [])]
        print("[893] abilities du porteur : %r" % (abil,))
        res = PR.rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": hel, "targetId": hel, "abilityType": ABILITY}}, 240)
        for act in (res.get("actions") or []):
            print("[893] action ok=%r mutated=%r actionConsumed=%r events=%d"
                  % (act.get("ok"), act.get("mutated"), act.get("actionConsumed"),
                     len(act.get("events") or [])))
            for e in (act.get("events") or []):
                print("      %-7s step=%-4r entity=%-5r source=%-28r tags=%s"
                      % (e.get("kind"), e.get("step"), e.get("entity"), e.get("source"),
                         (e.get("tags") or "") if e.get("step") == 4 else
                         (e.get("tags") or "")[:220]))
    finally:
        if not a.keep:
            try:
                PR.rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
