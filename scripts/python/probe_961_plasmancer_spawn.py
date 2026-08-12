#!/usr/bin/env python
"""Probe #961 -- RE-MESURE de la spawnabilite de `necroPlasmancer`, l'UNIQUE entree d'
`rl_collect_batch.UNSPAWNABLE_FALLBACK`.

POURQUOI. Le porteur de `LivingLightning` (1007) est `necroPlasmancer`. Il EST au catalogue
`BC.Units` du seed BC et il PASSE le filtre de stats de `buildNormalizedBC` -- il est ecarte du pool
par une LISTE ECRITE, pas par une mesure du jour :

    UNSPAWNABLE_FALLBACK = {"necroPlasmancer"}     # rl_collect_batch.py

Le commentaire qui l'accompagne date d'un balayage exhaustif fait sur un ANCIEN build (<< As of rank
17, only necroPlasmancer fails >>). La doctrine interdit de conclure << non confrontable >> d'une
liste heritee : on RE-MESURE, et la mesure de l'echec est le resultat.

COMMENT. `_load_unspawnable` lit le GLOBAL `UNSPAWNABLE_FALLBACK` de son propre module quand le
cache `data/unspawnable_rank<N>.json` est absent (il l'est). On le vide donc EN MEMOIRE (le fichier
versionne n'est pas touche), puis on demande un build ordinaire. Trois issues, toutes rendues
explicitement :
  * `SPAWNE`      -- l'unite se deploie : la liste est PERIMEE, `LivingLightning` est confrontable ;
  * `THROW`       -- le build echoue : l'exception managee est RECOPIEE, la liste est confirmee ;
  * `IMPOSSIBLE`  -- le montage n'a pas pu etre etabli (pas de session, board, ...).

ASCII only (cp1252). Usage :
    python probe_961_plasmancer_spawn.py [--seed 777] [--board MC1_67]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import rl_collect_batch as RCB                                            # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                       # noqa: E402

ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_961_plasmancer_spawn.json"
CARRIER = "necroPlasmancer"


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)

    before = set(RCB.UNSPAWNABLE_FALLBACK)
    print("[961] UNSPAWNABLE_FALLBACK (ecrit) = %s" % sorted(before))
    if CARRIER not in before:
        print("[961] %s n'y est PLUS -- rien a re-mesurer" % CARRIER)
        return 0

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.unlink(missing_ok=True)
    # Le sous-processus `rl_duel.py build` a SON propre import : on lui passe la levee par
    # l'environnement plutot que par une mutation locale, via un petit shim `-c`.
    code = (
        "import sys; sys.path.insert(0, %r);"
        "import rl_collect_batch as R; R.UNSPAWNABLE_FALLBACK = set();"
        "import rl_duel; sys.exit(rl_duel.main(%r))"
        % (str(PYDIR),
           ["build", "--seed", str(args.seed), "--board", str(args.board),
            "--state-file", str(STATE), "--p-units", CARRIER,
            "--a-units", "orksRuntherd"])
    )
    proc = subprocess.run([sys.executable, "-c", code], cwd=str(PYDIR),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    if STATE.exists():
        rid = json.loads(STATE.read_text())["runnerId"]
        print("[961] VERDICT = SPAWNE (runner=%s) -- la liste UNSPAWNABLE_FALLBACK est PERIMEE "
              "pour %s sur ce build" % (rid, CARRIER))
        sid = _resolve_session()
        view = (_rpc(sid, "decisionView", [{"runnerId": rid, "maxRank": 1}],
                     timeout=60).get("result") or {})
        for u in (view.get("units") or []):
            if u.get("visualId") == CARRIER:
                print("     %s id=%s hp=%s effets=%s"
                      % (CARRIER, u.get("id"), u.get("hp"),
                         [e.get("name") for e in (u.get("effects") or [])]))
        if not args.keep:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=60)
        return 0
    print("[961] VERDICT = THROW -- le build a echoue. Sortie brute (fin) :")
    print(out[-2500:])
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
