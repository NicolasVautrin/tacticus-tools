"""#469 -- LE MUR DE LA BANQUE **ET** CE QU'ELLE PREND A LA FLOTTE, mesures conjointes.

LE PIEGE QUE CE PROBE EXISTE POUR EVITER
----------------------------------------
`ratchets-bg` est cense << cacher le mur >>. C'est vrai de la LATENCE de l'orchestrateur -- il
merge pendant que la banque tourne -- et FAUX du cout global : la banque prend le CPU des agents,
qui ralentissent, ce qui rallonge la banque, etc. Mesurer le seul mur, c'est optimiser le chiffre
VISIBLE au detriment du chiffre INVISIBLE.

Ce probe mesure donc DEUX choses dans la meme fenetre, et refuse de rendre l'une sans l'autre :

  * le MUR de la banque (ce que voit celui qui l'attend) ;
  * le TEMOIN D'AGENT -- un cliquet reel, joue en boucle PENDANT la banque, dont la duree dit
    combien un agent est ralenti. Sa baseline est prise dans la MEME fenetre, banque eteinte.

Le total qui compte est `mur + surcout_temoin x nb_agents`, jamais le mur seul.

CE QUI EST TENU FIXE
--------------------
Le COMMIT (donc le perimetre de `probe_457 --since`, cause (b)) et l'arbre. Le seul degre de
liberte est `-ThrottleLimit`. Sans cela on comparerait deux diffs, et le facteur 2,9x deja mesure
entre un diff de carrefour et un diff doc-seule ecraserait tout effet du parallelisme.

CE QUI NE PEUT PAS ETRE TENU FIXE, ET QUI EST DONC RAPPORTE
----------------------------------------------------------
La charge de fond de la flotte : elle appartient a l'orchestrateur. Chaque condition rapporte les
coeurs occupes mesures pendant elle. Deux conditions jouees sous des charges tres differentes ne
se comparent pas, et le dire vaut mieux que de rendre un ratio propre.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent
RACINE = ICI.parent.parent

sys.path.insert(0, str(ICI))
from probe_469_contention_deconfusion import Charge, _banque_en_vol   # noqa: E402


def _jouer_temoin(argv: list) -> float:
    t = time.perf_counter()
    subprocess.run([sys.executable] + argv, cwd=str(ICI),
                   capture_output=True, text=True, errors="replace")
    return round(time.perf_counter() - t, 2)


class BoucleTemoin(threading.Thread):
    """Le TEMOIN tourne en boucle pendant toute la banque, et s'arrete avec elle.

    Un seul passage ne dirait rien : la banque n'a pas un profil plat (elle demarre a plein
    parallelisme et se vide par la fin). Une boucle echantillonne toute la fenetre.
    """

    def __init__(self, argv: list) -> None:
        super().__init__(daemon=True)
        self.argv = argv
        self.durees = []
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            self.durees.append(_jouer_temoin(self.argv))

    def arreter(self) -> None:
        self._stop.set()


# Classes de priorite Win32. La classe est HERITEE par les process enfants : la poser sur le
# `pwsh` de la banque la pose donc sur les 44 python qu'il lance, sans toucher a `ratchets.ps1`.
_PRIORITES = {
    "normale": 0x00000020,        # NORMAL_PRIORITY_CLASS
    "basse": 0x00004000,          # BELOW_NORMAL_PRIORITY_CLASS
    "inactif": 0x00000040,        # IDLE_PRIORITY_CLASS
}


def condition(throttle: int, temoin: list, racine: Path, since: str | None,
              priorite: str = "normale") -> dict:
    argv = ["pwsh", "-File", str(racine / "scripts" / "ratchets.ps1")]
    if throttle > 0:
        argv += ["-ThrottleLimit", str(throttle)]
    if since:
        argv += ["-Since", since]
    boucle = BoucleTemoin(temoin)
    ch = Charge()
    t0 = time.perf_counter()
    boucle.start()
    proc = subprocess.run(argv, cwd=str(racine), capture_output=True, text=True, errors="replace",
                          creationflags=_PRIORITES.get(priorite, 0x20))
    mur = round(time.perf_counter() - t0, 1)
    boucle.arreter()
    boucle.join(timeout=300)
    charge = ch.lire()
    # Le mur ANNONCE par la banque est le sien (le parallele seul) ; le notre inclut son
    # demarrage et sa mise en page. On garde les deux : un ecart entre eux est une information.
    mur_annonce = None
    for l in (proc.stdout or "").splitlines():
        if "mur" in l and " s." in l:
            try:
                mur_annonce = float(l.rsplit("Mur ", 1)[-1].split(" s.")[0].replace(",", "."))
            except Exception:
                pass
    return {
        "throttle": throttle,
        "priorite": priorite,
        "rc": proc.returncode,
        "mur_mesure_s": mur,
        "mur_annonce_s": mur_annonce,
        "charge_coeurs": charge[0] if charge else None,
        "temoin_n": len(boucle.durees),
        "temoin_median_s": round(statistics.median(boucle.durees), 2) if boucle.durees else None,
        "temoin_min_s": min(boucle.durees) if boucle.durees else None,
        "temoin_series": boucle.durees,
        "contexte": _banque_en_vol(),
        "queue_sortie": (proc.stdout or "").splitlines()[-6:],
    }


def baseline_temoin(temoin: list, n: int) -> dict:
    ch = Charge()
    d = [_jouer_temoin(temoin) for _ in range(n)]
    charge = ch.lire()
    return {"n": n, "median_s": round(statistics.median(d), 2), "min_s": min(d), "series": d,
            "charge_coeurs": charge[0] if charge else None, "contexte": _banque_en_vol()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--throttles", default="0,6",
                    help="valeurs a comparer ; 0 = defaut de ratchets.ps1 (min(cliquets, coeurs))")
    ap.add_argument("--priorites", default=None,
                    help="au lieu de comparer des throttles, comparer des PRIORITES de process "
                         "(normale,basse,inactif) a throttle constant")
    ap.add_argument("--temoin", default="probe_313_enum_mirror_bijection.py",
                    help="cliquet joue en boucle comme temoin d'agent")
    ap.add_argument("--since", default=None)
    ap.add_argument("--baseline", type=int, default=3)
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)

    temoin = a.temoin.split()
    out = {"quand": time.strftime("%Y-%m-%d %H:%M:%S"),
           "commit": subprocess.run(["git", "-C", str(RACINE), "rev-parse", "HEAD"],
                                    capture_output=True, text=True).stdout.strip(),
           "since": a.since, "temoin": a.temoin, "conditions": []}

    print("[469c] baseline du temoin, banque ETEINTE")
    out["baseline_avant"] = baseline_temoin(temoin, a.baseline)
    print("       median %.2f s  min %.2f s  (charge %s coeurs)"
          % (out["baseline_avant"]["median_s"], out["baseline_avant"]["min_s"],
             out["baseline_avant"]["charge_coeurs"]))

    if a.priorites:
        plan = [(0, p) for p in a.priorites.split(",") if p.strip()]
    else:
        plan = [(int(x), "normale") for x in a.throttles.split(",") if x.strip()]

    for t, prio in plan:
        print("[469c] banque, throttle=%s priorite=%s" % (t or "defaut", prio))
        c = condition(t, temoin, RACINE, a.since, prio)
        out["conditions"].append(c)
        print("       mur %.1f s (annonce %s)  rc=%s  charge %s coeurs"
              % (c["mur_mesure_s"], c["mur_annonce_s"], c["rc"], c["charge_coeurs"]))
        print("       temoin : %d passage(s), median %s s, min %s s"
              % (c["temoin_n"], c["temoin_median_s"], c["temoin_min_s"]))

    print("[469c] baseline du temoin APRES (la derive de fond se lit dans l'ecart des deux)")
    out["baseline_apres"] = baseline_temoin(temoin, a.baseline)
    print("       median %.2f s  min %.2f s  (charge %s coeurs)"
          % (out["baseline_apres"]["median_s"], out["baseline_apres"]["min_s"],
             out["baseline_apres"]["charge_coeurs"]))

    base = statistics.median([out["baseline_avant"]["median_s"], out["baseline_apres"]["median_s"]])
    print("")
    print("%-10s %-9s %10s %10s %10s %10s" %
          ("throttle", "priorite", "mur s", "temoin s", "temoin/base", "charge"))
    for c in out["conditions"]:
        r = round(c["temoin_median_s"] / base, 2) if c["temoin_median_s"] else None
        c["temoin_sur_baseline"] = r
        # Le TOTAL est ce qui decide, jamais le mur seul : la banque ne << cache >> son cout que
        # pour celui qui l'attend, elle le facture a chaque agent pendant toute sa duree.
        c["surcout_par_agent_s"] = round(c["mur_mesure_s"] * (r - 1.0), 0) if r else None
        print("%-10s %-9s %10.1f %10s %10s %10s"
              % (c["throttle"] or "defaut", c["priorite"], c["mur_mesure_s"],
                 c["temoin_median_s"], r, c["charge_coeurs"]))
    print("")
    print("surcout inflige a CHAQUE agent (mur x (temoin/base - 1)) :")
    for c in out["conditions"]:
        print("  throttle %-7s priorite %-9s -> %s s" %
              (c["throttle"] or "defaut", c["priorite"], c["surcout_par_agent_s"]))
    out["baseline_retenue_s"] = base

    dest = Path(a.json) if a.json else (RACINE / "logs" / "probe469" /
                                        ("mur-%s.json" % time.strftime("%Y%m%d-%H%M%S")))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("[469c] -> %s" % dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
