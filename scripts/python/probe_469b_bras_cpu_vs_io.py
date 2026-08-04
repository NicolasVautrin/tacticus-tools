"""#469 -- LE BRAS : a nombre de process INJECTES EGAL, qu'est-ce qui ralentit un vrai cliquet ?

POURQUOI CE BRAS-LA
-------------------
`probe_469_contention_deconfusion.py` etablit sur des SONDES que, sous charge, le cout d'OUVRIR
un fichier explose (0,43 ms -> 19 ms) pendant que le calcul pur ne bouge que de +23 % et que le
debit en octets reste nul-cout. Une sonde n'est pas une charge de travail : il reste a montrer que
c'est bien cette ressource-la qui gouverne le MUR d'un cliquet reel.

Le bras est a un seul degre de liberte. On joue le MEME cliquet, sur le MEME arbre, avec le MEME
nombre K de process injectes, et on ne change QUE LEUR NATURE :

    A  temoin            -- rien d'injecte
    B  K process CPU     -- calcul pur, aucune ouverture de fichier
    C  K process I/O     -- ouvertures de fichiers en boucle, calcul negligeable

B et C prennent le meme nombre de creneaux d'ordonnancement. Si le cliquet ralentit surtout sous
B, il est borne par le CPU et `-ThrottleLimit` est le bon levier, regle sur les coeurs. S'il
ralentit surtout sous C, il est borne par une ressource d'ACCES FICHIER que le nombre de coeurs ne
decrit pas -- et regler le parallelisme sur les coeurs serait precisement l'erreur que #469 vise.

LES CONDITIONS SONT ALTERNEES (A,B,C,A,B,C...) et non groupees : la charge de fond de cette
machine varie de minute en minute (quatre agents, un host, un IDE), et grouper les conditions
attribuerait cette derive a la condition.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent


BELOW_NORMAL = 0x00004000


def _charge(k: int, genre: str, base: Path, priorite_basse: bool = False):
    if genre == "cpu":
        prog = ("import math\nx=0.0\ni=1\n"
                "while True:\n x+=math.sqrt(i)/(i+1.0)\n i+=1\n if i>10**9: i=1\n")
    else:
        prog = ("import glob\n"
                "fs=sorted(glob.glob(r'%s\\\\*.py'))\n"
                "while True:\n"
                " for p in fs:\n"
                "  try:\n"
                "   open(p,'rb').read(1)\n"
                "  except OSError: pass\n" % str(base))
    flags = BELOW_NORMAL if priorite_basse else 0
    return [subprocess.Popen([sys.executable, "-c", prog], creationflags=flags,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(k)]


def _tuer(procs):
    for p in procs:
        try:
            p.kill()
        except OSError:
            pass
    for p in procs:
        try:
            p.wait(timeout=10)
        except Exception:
            pass


def jouer(argv_cliquet: list) -> tuple:
    t = time.perf_counter()
    r = subprocess.run([sys.executable] + argv_cliquet, cwd=str(ICI),
                       capture_output=True, text=True, errors="replace")
    return round(time.perf_counter() - t, 2), r.returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cliquet", action="append", required=True,
                    help="argv du cliquet, ex. probe_440_repo_root_scan_guard.py (repetable)")
    ap.add_argument("--k", type=int, default=8, help="process injectes par condition")
    ap.add_argument("--tours", type=int, default=2)
    ap.add_argument("--priorite", action="store_true",
                    help="ajouter la condition D : MEME charge CPU, mais en priorite BASSE "
                         "(preuve du mecanisme de la parade #469)")
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)

    base = ICI
    # `D_cpu_basse` est la PREUVE DU MECANISME de la parade #469, et elle coute 60 s la ou
    # repliquer le bras complet en coute 35 minutes. B et D injectent EXACTEMENT la meme charge
    # CPU ; la seule difference est sa CLASSE DE PRIORITE. Si D ralentit nettement moins que B,
    # alors abaisser la priorite d'une charge de fond rend bien du CPU au premier plan -- ce qui
    # est tout ce que la parade pretend faire.
    conditions = ("A_temoin", "B_cpu", "C_io", "D_cpu_basse") if a.priorite else \
                 ("A_temoin", "B_cpu", "C_io")
    resultats = {}
    for tour in range(a.tours):
        for cond in conditions:
            procs = []
            if cond == "B_cpu":
                procs = _charge(a.k, "cpu", base)
            elif cond == "C_io":
                procs = _charge(a.k, "io", base)
            elif cond == "D_cpu_basse":
                procs = _charge(a.k, "cpu", base, priorite_basse=True)
            if procs:
                time.sleep(2.0)
            try:
                for spec in a.cliquet:
                    args = spec.split()
                    sec, rc = jouer(args)
                    cle = (args[0], cond)
                    resultats.setdefault(cle, []).append(sec)
                    print("tour %d  %-10s %-46s %8.2f s  rc=%d"
                          % (tour, cond, args[0], sec, rc))
            finally:
                _tuer(procs)

    print("")
    print("%-40s %9s %9s %9s %9s %7s %7s %7s" %
          ("cliquet", "A temoin", "B cpu+%d" % a.k, "C io+%d" % a.k, "D cpuBAS", "B/A", "C/A", "D/A"))
    lignes = []
    for nom in sorted({c[0] for c in resultats}):
        def med(cond):
            v = resultats.get((nom, cond))
            return statistics.median(v) if v else None
        ta, tb, tc, td = med("A_temoin"), med("B_cpu"), med("C_io"), med("D_cpu_basse")
        f = lambda x: round(x / ta, 2) if (ta and x) else None
        print("%-40s %9.2f %9.2f %9.2f %9s %7s %7s %7s"
              % (nom, ta, tb, tc, td if td else "-", f(tb), f(tc), f(td)))
        lignes.append({"cliquet": nom, "A_temoin_s": ta, "B_cpu_s": tb, "C_io_s": tc,
                       "D_cpu_basse_s": td, "ratio_B_sur_A": f(tb), "ratio_C_sur_A": f(tc),
                       "ratio_D_sur_A": f(td), "k": a.k})
    if any(l.get("D_cpu_basse_s") for l in lignes):
        print("")
        print("B et D injectent la MEME charge CPU : seule sa PRIORITE change. D << B prouve")
        print("que ceder la priorite rend du CPU au premier plan -- le mecanisme de la parade.")

    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(
            {"quand": time.strftime("%Y-%m-%d %H:%M:%S"), "k": a.k, "tours": a.tours,
             "resume": lignes,
             "brut": {"%s|%s" % k: v for k, v in resultats.items()}}, indent=1), encoding="utf-8")
        print("[469b] -> %s" % a.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
