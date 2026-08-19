"""probe_63_verify : valide le fix #63 (state.board charge dans _combat_replay) via un state-file
UNIQUE a cet agent (pas le _pytest_duel_state.json partage). Exerce le helper CORRIGE :
  - replay_normal_attack (MELEE, pathfinding) : doit RESTER bit-exact (positions plates).
  - replay_attack_driven (RANGED depuis surplomb) : doit DEVENIR bit-exact (elevation appliquee).
ASCII only ; dispose ses runners.
"""
from __future__ import annotations

import os
import sys
import json
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tests", "engine", "runner"))
import rl_collect_batch as R                                    # noqa: E402
from _combat_replay import replay_normal_attack, replay_attack_driven   # noqa: E402

_SID = R._resolve_session()
_STATE = os.path.abspath(os.path.join(          # SORTIE -> logs/, jamais data/ (#349)
    os.path.dirname(__file__), "..", "..", "logs", "runners",
    "_probe63v_a5a63eef_state.json"))
_BOARD = "MC1_67"
_created = []


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _rpc(method, body=None, timeout=60):
    return _unwrap(R._rpc(_SID, method, [body] if body is not None else [], timeout=timeout))


def _build(seed="777", extra=None, board=_BOARD):
    extra = list(extra or [])
    board_args = [] if any(x in ("--board", "--board-pool") for x in extra) else ["--board", board]
    pydir = os.path.dirname(os.path.abspath(__file__))
    subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", str(seed),
                    "--state-file", _STATE, *board_args, *extra],
                   cwd=pydir, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.exists(_STATE):
        raise RuntimeError("build KO")
    rid = json.loads(open(_STATE).read())["runnerId"]; _created.append(rid)
    return {"rid": rid}


def _show(tag, r):
    if not r["ok"]:
        print(f"  {tag}: SKIP {r['reason']}"); return
    ok = (r["off_ph"] == r["live_ph"])
    extra = f" a_elev={r.get('a_elev')} t_elev={r.get('t_elev')}" if "a_elev" in r else ""
    print(f"  {tag}: bitexact={ok} armor={r['armor']} pierce={r['pierce']}{extra}")
    print(f"    live={r['live_ph']} off={r['off_ph']}")


def main():
    w = _unwrap(R._rpc(_SID, "autoBootExtraire", [{}], timeout=180))
    print("amorce ok=", isinstance(w, dict) and w.get("ok"))
    try:
        print("necroDestroyer->necroOverlord (MELEE, doit rester bitexact)")
        _show("melee", replay_normal_attack(_rpc, _build, "necroDestroyer", target="necroOverlord"))
        for att in ("necroDestroyer", "templHelbrecht"):
            print(f"{att}->ultraApothecary (RANGED surplomb, doit etre bitexact APRES fix)")
            _show("ranged-elev", replay_attack_driven(_rpc, _build, att, "ultraApothecary",
                                                      want_dist=2, require_higher_elev=True))
    finally:
        for rid in _created:
            try:
                R._rpc(_SID, "disposeRunner", [{"runnerId": rid}], timeout=20)
            except Exception:
                pass


if __name__ == "__main__":
    main()
