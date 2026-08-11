"""#907 -- EXPLORATION du montage (positions/distances) avant d'ecrire le temoin. Jetable-utile."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

from engine.entities.pathfinding.board import Board

PYDIR = Path(__file__).resolve().parent
HOST = "http://127.0.0.1:8765"


def _sid():
    return requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"]


def _rpc(sid, method, body=None, timeout=180):
    r = requests.post(f"{HOST}/api/scripts/{sid}/rpc",
                      json={"method": method, "args": [body] if body is not None else []},
                      timeout=timeout).json()
    return r.get("result", r)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="999")
    a = ap.parse_args(argv)
    sid = _sid()
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", a.seed, "--board", a.board,
           "--no-ai", "--state-file", a.state_file,
           "--explicit-stats", "templNpc2Neophyte:45",
           "--p-units", "templNpc2Neophyte:45,ultraTitus",
           "--a-units", "eldarRanger,astraBullgryn,darkaCompanion",
           "--armor-target", "0", "--block-target", "0,0", "--hp-target", "400000"]
    r = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0 or not Path(a.state_file).exists():
        print("build KO rc=%d\n%s" % (r.returncode, (r.stderr or r.stdout or "")[-2500:]))
        return 1
    rid = json.loads(Path(a.state_file).read_text(encoding="utf-8"))["runnerId"]
    print("rid=%s" % rid)
    try:
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")
        from engine.entities.effects.aura_selectors import hex_distance
        units = [u for u in ((dv or {}).get("units") or []) if u.get("alive")]
        car = next(u for u in units if u.get("visualId") == "templNpc2Neophyte")
        def _cr(u):
            p = u.get("pos")
            if isinstance(p, dict):
                return (p.get("col"), p.get("row"))
            return tuple(p) if isinstance(p, (list, tuple)) else p
        for u in units:
            try:
                d = hex_distance(_cr(car), _cr(u))
            except Exception as e:
                d = "ERR %s" % e
            print("  id=%s vis=%s team=%s pos=%r feet=%r d=%s"
                  % (u.get("id"), u.get("visualId"), u.get("team"), u.get("pos"), u.get("feet"), d))
        print("board size=%d" % len(bg.get("tiles") or []))
        return 0
    finally:
        _rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        print("dispose %s" % rid)


if __name__ == "__main__":
    raise SystemExit(main())
