#!/usr/bin/env python
"""#10033 -- RECENSEMENT de la face LIVE, l'axe que `probe_457` ne voit PAS.

CE QUE CE PROBE MESURE, ET CE QU'IL NE MESURE PAS
--------------------------------------------------
`probe_457_offline_tests_green.py` s'annonce « TOUT fichier de test qui n'est pas `_live.py` doit
etre VERT ». Le critere est explicite dans son code (`not name.endswith("_live.py")`) et il est
DECLARATIF : le suffixe est tenu par le depot, pas devine. Consequence jamais chiffree jusqu'ici :
la majorite du corpus de tests est HORS de son perimetre, et personne n'a jamais mesure sa couleur.

Ce probe repond a « COMBIEN de fichiers `_live.py` sont rouges ». Il ne les repare pas, et il
n'essaie PAS de tout jouer : une passe complete de la face live monterait un ou plusieurs runners
par fichier, sur un pump PARTAGE avec les autres agents. Il travaille donc en DEUX modes, et le
second est explicitement un ECHANTILLON.

  --collect      GRATUIT (aucun runner). Compte les fichiers et les tests, et surtout attrape les
                 ERREURS DE COLLECTE -- un fichier qui ne collecte pas est rouge sans qu'aucun
                 runner n'ait ete monte. C'est la seule partie du recensement qui soit exhaustive.
  --echantillon  Joue N fichiers TIRES AU SORT (graine fixe -> reproductible) et ventile leurs
                 echecs. Le resultat est un TAUX SUR UN ECHANTILLON, jamais un inventaire.

⚠ TOUT COMPTE FILTRE DIT CE QU'IL FILTRE. C'est la regle que ce fichier applique partout, et elle
vient d'une faute reelle : un recensement offline lu a travers un `Select-Object -Last 45` avait
donne « 23 echecs sur 19 fichiers » la ou la mesure complete en donnait 51 sur 39. Toute sortie
d'ici imprime la fraction couverte ET la phrase « CE QUE CETTE MESURE NE COUVRE PAS ».

⚠ UN ECHEC LIVE N'EST PAS FORCEMENT UNE DETTE DE PORT. Il peut venir du MONTAGE (board, porteur
hors pool, roster), d'une CONTENTION de runner, d'un GARDE de harnais, ou d'un instrument DESARME
-- ce dernier cas est exactement `#10031`, ou deux rouges accusaient la geometrie alors que la
cause etait une liaison d'import. La ventilation ci-dessous est une AIDE A LA LECTURE : elle range
sous `NON CLASSE` tout ce qu'elle ne reconnait pas, et ce seau est imprime en entier.

ASCII only (console Windows cp1252). Usage (depuis scripts/python) :
    python probe_10033_recensement_live.py --collect
    python probe_10033_recensement_live.py --echantillon 30 --workers 3
"""
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
TESTS = PYDIR / "tests"

#: Les familles de cause, DANS L'ORDRE D'ESSAI. Chaque entree est (etiquette, motif). Le seau
#: `NON CLASSE` recoit tout le reste et il est imprime INTEGRALEMENT -- une liste blanche de causes
#: ne peut pas montrer la cause qu'elle a oubliee.
FAMILLES = (
    ("harnais indisponible (host/session/drain)",
     r"host/session indisponible|runner creation paused|503|session indispo|host injoignable"),
    ("montage KO (build/roster/board)",
     r"montage KO|roster attendu absent|build.*(echou|KO)|introuvable dans data/boards|"
     r"boardGraph indispo|aucune unite confrontable"),
    ("porteur / pool",
     r"absent du pool|non confrontable|--list-pool|aucun porteur|0 porteur"),
    ("auto-controle de discriminance (le test dit qu'il ne prouverait rien)",
     r"ne prouverait rien|NON CONCLUANT|ne discrimine pas|non discriminante|geometrie ne prouve"),
    ("garde de harnais (#455 / #486-r15 / skip vert)",
     r"DECLENCHEUR|green_skip|passed == 0 and skipped|TACTICUS_ALLOW"),
    ("timeout / RPC",
     r"[Tt]imeout|TimeoutError|read timed out|Connection.*refus"),
)


def fichiers_live() -> "list[str]":
    """Les `_live.py`, en chemins relatifs a `scripts/python`. DERIVE du disque, jamais liste."""
    return sorted(p.relative_to(PYDIR).as_posix() for p in TESTS.rglob("*_live.py"))


def fichiers_hors_perimetre_457() -> "list[str]":
    """Ce que `probe_457` EXCLUT, re-derive par SON critere (`not name.endswith('_live.py')`) --
    de sorte que si le critere change la-bas, ce compte le suit au lieu de mentir."""
    return fichiers_live()


def _pytest(args: "list[str]", sortie: Path, timeout: int) -> int:
    """Joue pytest en REDIRIGEANT vers un FICHIER. Jamais un pipe : un flux tronque par un `head`
    ou un `Select-Object` se lit comme une mesure complete -- faute deja commise, 51 echecs lus
    comme 23."""
    with sortie.open("w", encoding="utf-8", errors="replace") as fh:
        p = subprocess.run([sys.executable, "-m", "pytest", *args],
                           cwd=str(PYDIR), stdout=fh, stderr=subprocess.STDOUT,
                           text=True, timeout=timeout)
    return p.returncode


def mode_collect(verbose: bool = True) -> dict:
    """GRATUIT et EXHAUSTIF : la collecte de toute la face live. Aucun runner n'est monte."""
    live = fichiers_live()
    assert live, "aucun fichier `_live.py` trouve -- le recenseur ne visite plus rien"
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "collect.txt"
        rc = _pytest(["tests", "--collect-only", "-q", "-p", "no:cacheprovider",
                      "--ignore-glob=*_offline.py"], out, timeout=1800)
        txt = out.read_text(encoding="utf-8", errors="replace")
    nodeids = [l.strip() for l in txt.splitlines() if "::" in l and l.strip().startswith("tests/")]
    par_fichier = Counter(n.split("::")[0] for n in nodeids)
    collectes = {f for f in par_fichier if f.endswith("_live.py")}
    erreurs = re.findall(r"^ERROR (\S+)", txt, flags=re.M)
    muets = sorted(set(live) - collectes)
    res = {"fichiers_live": len(live), "fichiers_collectes": len(collectes),
           "tests_live": sum(c for f, c in par_fichier.items() if f.endswith("_live.py")),
           "fichiers_sans_aucun_test": muets, "erreurs_de_collecte": sorted(set(erreurs)),
           "rc_pytest": rc}
    if verbose:
        print("[10033] COLLECTE -- exhaustive, aucun runner monte")
        print("   fichiers `_live.py` sur le disque ..... %d" % res["fichiers_live"])
        print("   fichiers qui COLLECTENT ............... %d" % res["fichiers_collectes"])
        print("   tests collectes dans ces fichiers ..... %d" % res["tests_live"])
        print("   fichiers SANS AUCUN test collecte ..... %d %s"
              % (len(muets), muets[:6] if muets else ""))
        print("   ERREURS de collecte ................... %d %s"
              % (len(res["erreurs_de_collecte"]), res["erreurs_de_collecte"][:6]))
        print("   ⚠ CE QUE CETTE MESURE NE COUVRE PAS : la COULEUR. Un fichier qui collecte peut")
        print("     echouer a l'execution ; seul `--echantillon` en dit quelque chose, et seulement")
        print("     sur la fraction tiree.")
    return res


def mode_echantillon(n: int, graine: int, workers: int, timeout: int,
                     verbose: bool = True) -> dict:
    """Joue N fichiers TIRES AU SORT. Le resultat est un TAUX SUR ECHANTILLON, jamais un inventaire.

    `workers` borne les runners simultanes : le pump est PARTAGE avec les autres agents, et la
    doctrine du depot plafonne a 4 toute passe qui monte des runners."""
    live = fichiers_live()
    assert live, "aucun fichier `_live.py` trouve -- le recenseur ne visite plus rien"
    n = min(int(n), len(live))
    tire = sorted(random.Random(graine).sample(live, n))
    # PARALLELISME PAR PROCESSUS, pas par `xdist` : le plugin n'est PAS installe sur cet arbre
    # (`import xdist` -> ModuleNotFoundError), et la doctrine du depot autorise explicitement les
    # deux voies (« N processus pytest, ou pytest-xdist -n 4 --dist loadfile »). Le decoupage est
    # PAR FICHIER, ce qui reproduit `--dist loadfile` : un fichier = un processus = un runner en
    # `scope="module"`, jamais deux workers qui reconstruisent le meme runner.
    with tempfile.TemporaryDirectory() as d:
        parts = [tire[i::max(1, workers)] for i in range(max(1, workers))]
        procs, sorties, rc = [], [], 0
        for i, part in enumerate(parts):
            if not part:
                continue
            s = Path(d) / ("part%d.txt" % i)
            sorties.append(s)
            fh = s.open("w", encoding="utf-8", errors="replace")
            procs.append((subprocess.Popen(
                # `-rsfE` et PAS `-rs` : `-r` REMPLACE la liste des caracteres rapportes, donc un
                # `-rs` seul EFFACE les lignes `FAILED ...` du short summary. Mesure de la faute,
                # faite sur ce probe meme : premier tir a 30 fichiers, `2 failed` au bilan et
                # `0 item rouge` au recensement. Le cran `_coherence` ci-dessous rougit desormais
                # sur cet ecart au lieu de le taire.
                [sys.executable, "-m", "pytest", "-q", "-rsfE", "--tb=line",
                 "-p", "no:cacheprovider", *part],
                cwd=str(PYDIR), stdout=fh, stderr=subprocess.STDOUT, text=True), fh))
        for p, fh in procs:
            try:
                rc = max(rc, p.wait(timeout=timeout))
            except subprocess.TimeoutExpired:
                p.kill()
                rc = 99
            finally:
                fh.close()
        txt = "\n".join(s.read_text(encoding="utf-8", errors="replace") for s in sorties)
    echecs = sorted(set(re.findall(r"^(?:FAILED|ERROR) (tests/\S+)", txt, flags=re.M)))
    fich_rouges = sorted({e.split("::")[0] for e in echecs})
    # ventilation : le MESSAGE de chaque echec, classe par la premiere famille qui matche.
    classe, non_classe = Counter(), []
    for e in echecs:
        bloc = "\n".join(l for l in txt.splitlines() if e.split("::")[0] in l or "assert" in l)
        contexte = txt[max(0, txt.find(e) - 4000): txt.find(e) + 400] if e in txt else bloc
        for etiquette, motif in FAMILLES:
            if re.search(motif, contexte):
                classe[etiquette] += 1
                break
        else:
            non_classe.append(e)
    # SKIPS -- l'autre face de l'invisibilite (#455) : un fichier `passed == 0 and skipped > 0`
    # rend `rc 0` et zero assertion evaluee. Sur la face LIVE c'est le regime le plus probable
    # (montage indisponible), donc le compter fait partie du recensement, pas du confort.
    skips = Counter(m.split(":")[0] for m in
                    re.findall(r"^SKIPPED \[\d+\] (\S+)", txt, flags=re.M))
    bilan = dict(zip(("passed", "failed", "skipped", "error"), (0, 0, 0, 0)))
    for cle in bilan:
        bilan[cle] = sum(int(x) for x in re.findall(r"(\d+) %s" % cle, txt))
    # CRAN DE COHERENCE -- un recenseur qui compte MOINS que le bilan de pytest MENT, et il ment
    # dans le sens rassurant. C'est arrive sur ce fichier meme (`-rs` au lieu de `-rsfE`), et un
    # « 0 rouge » se serait lu comme un inventaire. On ne rougit PAS sur l'inegalite inverse : le
    # bilan est agrege sur plusieurs processus et une meme ligne peut y etre comptee autrement.
    attendu = bilan["failed"] + bilan["error"]
    coherent = len(echecs) >= attendu
    res = {"echantillon": n, "univers": len(live), "graine": graine, "workers": workers,
           "fichiers_rouges": fich_rouges, "items_rouges": echecs,
           "ventilation": dict(classe), "non_classe": non_classe, "rc_pytest": rc,
           "fichiers_tires": tire, "skips_par_fichier": dict(skips), "bilan": bilan,
           "coherent": coherent}
    assert coherent, (
        "RECENSEUR INCOHERENT : pytest annonce %d failed/error, le recensement n'en liste que %d. "
        "Le parseur ne voit pas ce que la passe a produit -- ne PAS lire ce resultat comme un "
        "inventaire." % (attendu, len(echecs)))
    if verbose:
        pct = 100.0 * n / len(live)
        print("[10033] ECHANTILLON -- %d fichier(s) sur %d (%.1f %%), graine %d, %d worker(s)"
              % (n, len(live), pct, graine, workers))
        print("   fichiers ROUGES dans l'echantillon .... %d / %d" % (len(fich_rouges), n))
        print("   items rouges .......................... %d" % len(echecs))
        print("   bilan pytest agrege ................... %s" % res["bilan"])
        print("   items SKIPPES ......................... %d, sur %d fichier(s)"
              % (sum(skips.values()), len(skips)))
        for etiquette, c in classe.most_common():
            print("      %-58s %d" % (etiquette, c))
        if non_classe:
            print("      NON CLASSE (imprime EN ENTIER -- une liste blanche de causes ne peut pas")
            print("      montrer la cause qu'elle a oubliee) : %d" % len(non_classe))
            for e in non_classe:
                print("          %s" % e)
        print("   ⚠ CE QUE CETTE MESURE NE COUVRE PAS : les %d autres fichiers (%.1f %%), et TOUTE"
              % (len(live) - n, 100.0 - pct))
        print("     dependance a l'etat de la session au moment du tir (contention de runner,")
        print("     fenetre DRAIN, autre agent). Un rouge d'ici n'est PAS forcement une dette de")
        print("     port -- il faut le lire.")
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--collect", action="store_true", help="recensement gratuit (aucun runner)")
    ap.add_argument("--echantillon", type=int, default=0, help="nombre de fichiers a jouer")
    ap.add_argument("--graine", type=int, default=10033)
    ap.add_argument("--workers", type=int, default=3,
                    help="runners simultanes (<= 4 : le pump est partage)")
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.workers > 4:
        raise SystemExit("--workers > 4 : le pump est PARTAGE, la doctrine du depot plafonne a 4")
    out = {}
    if a.collect or not a.echantillon:
        out["collect"] = mode_collect(verbose=not a.json)
    if a.echantillon:
        out["echantillon"] = mode_echantillon(a.echantillon, a.graine, a.workers, a.timeout,
                                              verbose=not a.json)
    if a.json:
        print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
