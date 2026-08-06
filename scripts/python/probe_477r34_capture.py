#!/usr/bin/env python3
"""#477-r34 -- l'EXTRACTEUR : monte un scenario, sauve le flux BRUT dans `logs/`, et imprime les
sous-arbres HORS PERIMETRE des couples `Action=PrepareTurn` + `Group=StartTurn`.

    python probe_477r34_capture.py --board MC1_67 --tours 2 \
        --p-units adeptHospitaller,astraBullgryn --a-units blackTerminator,worldJakhal \
        --etiquette MC1_67-2v2

Il ne rend AUCUN verdict -- il sert a LIRE ce qu'une tranche a laisse dehors, et a le RELIRE
sans re-monter de runner (le flux est mis en cache dans `logs/`, et `--flux <chemin>` rejoue un
flux deja capture). C'est lui qui a servi a cadrer #477-r34 (quelles formes bloquent quoi) puis
a CRAFTER le roster `adeptCanoness` du quatrieme scenario de `probe_477r22`.

ASCII only (console Windows cp1252).
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
import probe_477r22_turn_phase as R22  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / "logs"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--tours", type=int, default=2)
    ap.add_argument("--p-units", default="")
    ap.add_argument("--a-units", default="")
    ap.add_argument("--etiquette", default="capture")
    ap.add_argument("--flux", default="")
    ap.add_argument("--session", type=int, default=None)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    chemin = OUT / ("477r34-flux-%s.txt" % args.etiquette)
    if args.flux:
        flux = Path(args.flux).read_text(encoding="utf-8")
    elif chemin.is_file():
        print("[477-r34] flux DEJA capture : %s" % chemin)
        flux = chemin.read_text(encoding="utf-8")
    else:
        session = args.session if args.session is not None else R15A.session_courante()
        state = OUT / ("state-477r34-%s.json" % args.etiquette)
        rid = R19.build(args.board, state, args.p_units, args.a_units)
        try:
            for _ in range(args.tours):
                q = subprocess.run([sys.executable, "rl_duel.py", "aiturn",
                                    "--state-file", str(state)],
                                   cwd=str(HERE), capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=900)
                if q.returncode != 0:
                    break
            flux = (R15A.rpc(session, "replayOutputStream",
                             {"runnerId": rid, "maxChars": 8000000}).get("outputStream") or "")
        finally:
            R15A.dispose(state)
        chemin.write_text(flux, encoding="utf-8", newline="")
        print("[477-r34] flux ecrit : %s (%d lignes)" % (chemin, flux.count("\n")))

    couples = R22.couples_du_flux(flux)
    print("[477-r34] %d couple(s)" % len(couples))
    total = 0
    for k, c in enumerate(couples):
        if not c.hors:
            continue
        print("")
        print("=== COUPLE #%d racine=%s prof=%d : %d bloc(s) hors perimetre"
              % (k, c.racine, c.prof, len(c.hors)))
        for h in c.hors:
            total += h["lignes"]
            print("--- HORS (%d lignes) : %s | %s" % (h["lignes"], h["raison"], h["forme"]))
            for l in h["texte"]:
                print(l)
    print("")
    print("[477-r34] TOTAL hors perimetre = %d ligne(s)" % total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
