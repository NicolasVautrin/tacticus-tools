#!/usr/bin/env python3
"""MESURE : les citations `Classe$$Membre` du depot resolvent-elles dans la table courante ?

POURQUOI CETTE SONDE EXISTE
---------------------------
Le depot cite ses fonctions natives par SYMBOLE, jamais par adresse (cf. `CLAUDE.md`, « on cite
un SYMBOLE, jamais une adresse »). Ces citations ne sont donc utiles que si elles resolvent
REELLEMENT dans `data/symbols/<CURRENT>/ghidra/functions.tsv`. Rien ne le verifiait.

Le 2026-07-29 la table produite pour le nouveau build est sortie en notation POINTEE
(`Classe.Methode`) au lieu de `Classe$$Membre` : **0 citation sur 1 266 resolvait**, et le diff
inter-build affichait 0,43 % de symboles communs -- la signature trompeuse d'un jeu entierement
reecrit. Cause : un changement d'outillage (retrait de l'applier Il2CppDumper le 2026-07-25)
dont personne n'avait re-joue l'aval. Aucune garde ne pouvait le voir : les trois axes de
`symbols_sync.py` verifient la PROVENANCE (sha256, estampilles, build charge), jamais la FORME.

DEUX SORTIES, ET ELLES NE DISENT PAS LA MEME CHOSE
---------------------------------------------------
- **taux de resolution** : si effondre, c'est la FORME de la table qui est en cause, pas le jeu.
  C'est le signal que la garde de la tache #255 doit lire.
- **liste des citations PERDUES** (resolvaient contre un build de reference, plus contre celui-ci) :
  la, c'est le jeu qui a bouge. **Majorant**, pas inventaire : `CLAUDE.md` rappelle qu'une absence
  dans les tables ne prouve rien -- les corps generiques partages (`Playbook<__Il2Cpp...>`) et les
  corps triviaux dedupliques y figurent sans avoir disparu du binaire.

POPULATION DE REFERENCE -- le point METHODOLOGIQUE de cette sonde
------------------------------------------------------------------
On ne mesure PAS sur toutes les citations extraites : l'extraction est bruyante (formes courtes
sans namespace, artefacts Markdown), et melanger noie le signal. On restreint aux citations qui
resolvaient VERBATIM dans la table d'un build de REFERENCE -- seule population dont on sait
qu'elle etait bien formee. Sans ce filtre, la mesure brute donnait 27,5 % la ou la vraie valeur
etait 81,9 %, et l'ecart aurait ete impute au jeu.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "python"))

from symbols_layout import archived_builds, current_build  # noqa: E402

SYMBOLS = REPO / "data" / "symbols"
PERIMETRE = ("scripts/python/engine", "docs/rl")

# Suite de segments pointes, `$$`, puis le membre. Volontairement LARGE : on mesure, on ne
# valide pas une grammaire. Le bruit est ecarte par la population de reference, pas par le regex.
CITE = re.compile(r"[A-Za-z_][\w.`<>\[\]]*\$\$[\w.`<>]+")


def table(build: str) -> set[str]:
    p = SYMBOLS / build / "ghidra" / "functions.tsv"
    if not p.is_file():
        raise SystemExit("table absente pour le build %s : %s" % (build, p))
    out = set()
    with p.open(encoding="utf-8") as fh:
        for ligne in fh:
            if ligne.startswith("#"):
                continue
            parts = ligne.rstrip("\n").split("\t")
            if len(parts) >= 2:
                out.add(parts[1])
    return out


def citations() -> Counter:
    trouvees: Counter[str] = Counter()
    for racine in PERIMETRE:
        base = REPO / racine
        if not base.is_dir():
            continue
        for f in base.rglob("*"):
            if f.suffix not in (".py", ".md") or not f.is_file():
                continue
            try:
                txt = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in CITE.findall(txt):
                trouvees[m] += 1
    return trouvees


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", default=None, help="build a mesurer (defaut : data/symbols/CURRENT)")
    ap.add_argument("--reference", default=None,
                    help="build servant de population de reference (defaut : la premiere archive)")
    ap.add_argument("--seuil", type=float, default=0.0,
                    help="taux minimal attendu en %% ; sous ce seuil, sortie 1 (usage garde)")
    ap.add_argument("--lister", type=int, default=40, help="nb de citations perdues a afficher")
    args = ap.parse_args()

    build = args.build or current_build()
    archives = archived_builds()
    reference = args.reference or (archives[0] if archives else None)

    courante = table(build)
    cites = citations()
    uniques = sorted(cites)
    print("build mesure : %s  (%d symboles)" % (build, len(courante)))
    print("citations `$$` distinctes : %d  (occurrences : %d)"
          % (len(uniques), sum(cites.values())))

    if reference is None:
        # Sans build de reference, on ne peut PAS distinguer « citation mal formee » de
        # « symbole disparu ». On mesure quand meme le taux brut, en le DISANT.
        n = sum(1 for s in uniques if s in courante)
        print("")
        print("AUCUN build archive -- population de reference indisponible.")
        print("  taux BRUT (bruit d'extraction inclus, sous-estime) : %d / %d  (%.1f %%)"
              % (n, len(uniques), 100.0 * n / max(1, len(uniques))))
        return 0

    ref = table(reference)
    valides = [s for s in uniques if s in ref]
    n = sum(1 for s in valides if s in courante)
    taux = 100.0 * n / max(1, len(valides))
    print("reference    : %s  (%d citations bien formees)" % (reference, len(valides)))
    print("")
    print("  RESOLUTION : %d / %d  (%.1f %%)" % (n, len(valides), taux))

    perdues = sorted(s for s in valides if s not in courante)
    print("")
    print("=== citations PERDUES : %d  (majorant -- voir docstring) ===" % len(perdues))
    for s in perdues[:args.lister]:
        print("  %s" % s)
    if len(perdues) > args.lister:
        print("  ... et %d autres (--lister N pour en voir plus)" % (len(perdues) - args.lister))

    if args.seuil and taux < args.seuil:
        print("")
        print("ECHEC : taux %.1f %% < seuil %.1f %%." % (taux, args.seuil))
        print("  Un effondrement DU TAUX accuse la FORME de la table, pas le jeu :")
        print("  verifier `grep -c '\\$\\$' data/symbols/%s/ghidra/functions.tsv`." % build)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
