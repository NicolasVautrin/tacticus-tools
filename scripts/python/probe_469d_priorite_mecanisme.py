"""#469 -- PREUVE DU MECANISME : ceder la priorite rend-il du CPU au premier plan ?

POURQUOI CE PROBE EXISTE (et pourquoi le precedent ne suffisait pas)
--------------------------------------------------------------------
La parade de #469 abaisse la classe de priorite de la banque de fond. Le bras qui la valide sur la
banque REELLE coute ~35 min par condition, et cette machine porte jusqu'a QUATRE banques
concurrentes qui demarrent et s'arretent sans prevenir : mesure du 2026-08-04, le meme temoin
passe de 26,5 a 47,6 s d'un tour a l'autre SANS qu'on ait rien change. Un effet de 20-40 % ne se
lit pas dans ce bruit-la.

Le remede n'est pas de mesurer plus longtemps -- c'est de mesurer AUTREMENT :

  * la charge est POSEE UNE FOIS et ne bouge plus (aucun spawn dans la boucle de mesure) ;
  * on ne bascule que sa CLASSE DE PRIORITE, par `SetPriorityClass` sur les process deja vivants,
    ce qui est instantane ;
  * on ALTERNE a haute frequence (quelques secondes), donc une derive de fond frappe les deux
    conditions PAREIL et s'annule dans la comparaison appariee.

C'est le meme principe que l'alternance A,B,C de `probe_469b`, pousse d'un cran : la ou l'autre
alternait des conditions de 30 s, celui-ci alterne des mesures de 1 s.

CE QUI EST COMPARE
------------------
Un temoin CPU pur, en priorite NORMALE, mesure sous deux regimes de bruit de fond IDENTIQUES en
volume et en nature -- seule leur priorite differe. Si le temoin est plus rapide quand le bruit est
en priorite BASSE, le mecanisme de la parade est etabli : ceder la priorite rend du CPU.

Sortie ASCII stricte (cp1252).
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import statistics
import subprocess
import sys
import time
from pathlib import Path

NORMAL = 0x00000020
BELOW_NORMAL = 0x00004000
PROCESS_SET_INFORMATION = 0x0200

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenProcess.restype = ctypes.c_void_p


def _poser_priorite(pid: int, classe: int) -> bool:
    h = _k32.OpenProcess(PROCESS_SET_INFORMATION, False, pid)
    if not h:
        return False
    try:
        return bool(_k32.SetPriorityClass(ctypes.c_void_p(h), classe))
    finally:
        _k32.CloseHandle(ctypes.c_void_p(h))


def _temoin(n: int) -> float:
    t = time.perf_counter()
    x = 0.0
    for i in range(1, n):
        x += math.sqrt(i) / (i + 1.0)
    return time.perf_counter() - t


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--k", type=int, default=10, help="process de bruit de fond")
    ap.add_argument("--cycles", type=int, default=12, help="alternances NORMALE / BASSE")
    ap.add_argument("--n", type=int, default=1_500_000, help="taille du temoin (~1 s isole)")
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)

    prog = ("import math\nx=0.0\ni=1\n"
            "while True:\n x+=math.sqrt(i)/(i+1.0)\n i+=1\n if i>10**9: i=1\n")
    bruit = [subprocess.Popen([sys.executable, "-c", prog],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
             for _ in range(a.k)]
    print("[469d] bruit de fond : %d process CPU" % a.k)
    try:
        time.sleep(2.0)
        _temoin(a.n)                              # amorce, jamais compte
        mesures = {"normale": [], "basse": []}
        refus = 0
        for c in range(a.cycles):
            # L'ORDRE ALTERNE d'un cycle a l'autre : sinon << basse >> serait systematiquement
            # mesure apres << normale >>, et toute derive INTRA-cycle lui serait imputee.
            ordre = (NORMAL, BELOW_NORMAL) if c % 2 == 0 else (BELOW_NORMAL, NORMAL)
            for classe in ordre:
                nom = "normale" if classe == NORMAL else "basse"
                for p in bruit:
                    if not _poser_priorite(p.pid, classe):
                        refus += 1
                time.sleep(0.4)                   # laisser l'ordonnanceur reagir
                mesures[nom].append(_temoin(a.n))
        for p in bruit:                           # rendre la machine propre avant d'imprimer
            _poser_priorite(p.pid, NORMAL)
    finally:
        for p in bruit:
            try:
                p.kill()
            except OSError:
                pass
        for p in bruit:
            try:
                p.wait(timeout=10)
            except Exception:
                pass

    if refus:
        print("[469d] ATTENTION : %d refus de SetPriorityClass -- mesure NON CONCLUANTE" % refus)
        return 99

    mn = statistics.median(mesures["normale"])
    mb = statistics.median(mesures["basse"])
    # APPARIEMENT : chaque cycle fournit un couple mesure a quelques secondes d'intervalle. La
    # mediane des RAPPORTS est immunisee contre une derive de fond, la ou un rapport de medianes
    # ne l'est pas -- et c'est precisement la derive qui rendait `probe_469b` illisible ici.
    couples = [b / n for n, b in zip(mesures["normale"], mesures["basse"]) if n > 0]
    apparie = statistics.median(couples) if couples else None

    print("")
    print("temoin sous bruit NORMALE : median %.3f s  (n=%d)" % (mn, len(mesures["normale"])))
    print("temoin sous bruit BASSE   : median %.3f s  (n=%d)" % (mb, len(mesures["basse"])))
    print("rapport BASSE / NORMALE   : %.3f  (medianes)" % (mb / mn))
    print("rapport APPARIE par cycle : %.3f  <- < 1 = ceder la priorite REND du CPU" % apparie)
    gagnants = sum(1 for r in couples if r < 1.0)
    print("cycles ou BASSE est plus rapide : %d / %d" % (gagnants, len(couples)))

    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(
            {"quand": time.strftime("%Y-%m-%d %H:%M:%S"), "k": a.k, "cycles": a.cycles,
             "median_normale_s": round(mn, 3), "median_basse_s": round(mb, 3),
             "rapport_medianes": round(mb / mn, 3), "rapport_apparie": round(apparie, 3),
             "cycles_gagnants": gagnants, "couples": [round(r, 3) for r in couples],
             "series": {k: [round(x, 3) for x in v] for k, v in mesures.items()}},
            indent=1), encoding="utf-8")
        print("[469d] -> %s" % a.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
