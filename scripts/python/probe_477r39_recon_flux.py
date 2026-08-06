#!/usr/bin/env python3
"""#477-r39 / r38 -- RECONNAISSANCE : capturer le flux brut des deux scenarios qui portent les
familles encore hors perimetre (`Action=HealInfo`, `Group=ResurrectUnit`).

    python probe_477r39_recon_flux.py --etiquette MC1_67-2v2

C'est un OUTIL DE MESURE, pas un garde : il ecrit le flux dans `logs/` pour que la RE soit lue
sur du texte reel plutot que devinee. Meme montage que `probe_477r22_turn_phase.py`
(memes boards, memes rosters, meme seed), un runner a la fois, dispose dans le `finally`.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import probe_477r15a_stream_conformance as R15A  # noqa: E402
import probe_477r19_process_removals as R19  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / "logs"

#: LES MEMES QUATRE PLANS QUE `probe_477r22_turn_phase.py`, recopies pour que la reconnaissance
#: porte sur le corpus exact de la tranche.
PLANS = {
    "C1_02": ("C1_02", "", ""),
    "MC1_67": ("MC1_67", "", ""),
    "MC1_67-2v2": ("MC1_67", "adeptHospitaller,astraBullgryn", "blackTerminator,worldJakhal"),
    "MC1_67-2v2-sans-soin": ("MC1_67", "adeptCanoness,astraBullgryn",
                             "blackTerminator,worldJakhal"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--etiquette", default="MC1_67-2v2")
    ap.add_argument("--tours", type=int, default=2)
    args = ap.parse_args()

    session = args.session if args.session is not None else R15A.session_courante()
    board, pu, au = PLANS[args.etiquette]
    state = OUT / ("state-477r39-recon-%s.json" % args.etiquette)
    state.parent.mkdir(parents=True, exist_ok=True)
    rid = R19.build(board, state, pu, au)
    try:
        joues = 0
        for _ in range(args.tours):
            q = subprocess.run([sys.executable, "rl_duel.py", "aiturn",
                                "--state-file", str(state)],
                               cwd=str(HERE), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=900)
            if q.returncode != 0:
                break
            joues += 1
        flux = (R15A.rpc(session, "replayOutputStream",
                         {"runnerId": rid, "maxChars": 8000000}).get("outputStream") or "")
    finally:
        R15A.dispose(state)
    cible = OUT / ("477r39-flux-%s.txt" % args.etiquette)
    with open(cible, "w", encoding="utf-8", newline="") as f:
        f.write(flux)
    print("[recon] %s : %d tour(s), %d lignes -> %s"
          % (args.etiquette, joues, flux.count("\n"), cible))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
