"""#1027 -- CONFRONTATION LIVE des deux actives npc d'`admecBossBelisarius` :
`InvocationOfMachineVengeance` (1172) et `SolarAtomizer` (1174).

Un SEUL montage sert les deux : Belisarius pose `MachineVengeance` sur tous ses allies mecaniques
avec 1172, ce qui CREE le substrat que 1174 transfere. La fixture est nommee et reutilisable
(`monter()`), et le probe joue les deux casts dans l'ordre.

    python probe_1027_belisarius_actives.py --state-file <ABSOLU hors data/> [--build]

Sortie ASCII. Ce probe MESURE (il n'assertionne rien) ; le cliquet est
`tests/engine/runner/test_1027_belisarius_actives_offline.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

BOARD = "MC1_67"
SEED = 777
#: Le roster de la fixture. `admecBossBelisarius:4` = le vrai palier du boss (34277 PV) ;
#: `admecDominus`/`admecDestroyer` sont les allies MECANIQUES sur lesquels 1172 pose la pile et
#: depuis lesquels 1174 la transfere.
P_UNITS = "admecBossBelisarius:4,admecDominus,admecDestroyer"
A_UNITS = "admecMarshall,admecRuststalker"


def _run(args: list, timeout: int = 300) -> tuple:
    env = dict(os.environ)
    env["TACTICUS_ALLOW_ROSTER_DEFICIT"] = "1"       # id remappe -> faux rouge de roster
    p = subprocess.run([sys.executable] + args, cwd=_HERE, env=env,
                       capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout or ""), (p.stderr or "")


def monter(state_file: str) -> int:
    """FIXTURE NOMMEE -- monte le runner de Belisarius. Rend le rc du build."""
    rc, out, err = _run(["rl_duel.py", "build", "--board", BOARD, "--seed", str(SEED),
                         "--state-file", state_file,
                         "--explicit-stats", "admecBossBelisarius:4",
                         "--p-units", P_UNITS, "--a-units", A_UNITS])
    for line in (out + err).splitlines():
        if "[explicit-stats]" in line or "[build] board swap" in line or "runnerId" in line:
            print("   " + line.strip()[:160])
    return rc


def _view(state_file: str) -> dict:
    rc, out, err = _run(["rl_duel.py", "view", "--state-file", state_file, "--json"])
    for blob in (out, err):
        blob = blob.strip()
        if blob.startswith("{"):
            return json.loads(blob)
        i = blob.find("\n{")
        if i >= 0:
            try:
                return json.loads(blob[i + 1:])
            except ValueError:
                pass
    print("[view] SORTIE NON JSON (rc=%d) -- 400 premiers caracteres :" % rc)
    print((out or err)[:400])
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--build", action="store_true", help="(re)monter la fixture")
    a = ap.parse_args()
    if a.build or not os.path.exists(a.state_file):
        print("[1027] MONTAGE")
        rc = monter(a.state_file)
        print("[1027] build rc=%d" % rc)
    dv = _view(a.state_file)
    print("[1027] cles de la vue : %s" % sorted(dv.keys())[:16])
    for u in (dv.get("units") or []):
        vid = str(u.get("visualId") or "")
        if "Belisarius" in vid or "admec" in vid:
            print("  u%s %-34s (%s,%s) hp=%s" % (u.get("id"), vid, u.get("col"), u.get("row"),
                                                 u.get("hp")))
            for ab in (u.get("abilities") or []):
                print("      %-8s id=%-6s usable=%s %s" % (ab.get("kind"), ab.get("id"),
                                                           ab.get("usable"), ab.get("name")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
