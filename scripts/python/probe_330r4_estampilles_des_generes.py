#!/usr/bin/env python3
"""#330-r4/r5 -- l'ESTAMPILLE d'un artefact GENERE doit nommer le build COURANT.

CE QUE CE CLIQUET GARDE, ET LE TROU EXACT QU'IL BOUCHE
-------------------------------------------------------
Le CONTENU des artefacts derives du build est deja garde, chacun par le sien :
`probe_252` (6 tables `frida/hooks/data/*.ts`), `probe_275` (`enum_maps.py`), `probe_270`
(`ActiveAbilityType` et ses recopies), `probe_313` (38 mirrors `IntEnum` en bijection). Tous
etaient VERTS le 2026-08-15 -- pendant que DOUZE artefacts declaraient sortir d'un build
ANTERIEUR (`data/symbols/rnca9r7q6c/frida/enums.tsv`, `data/dumps/kqkbjqfb6c/dump.cs`,
`build=rnca9r7q6c`).

L'accord contenu <-> build etait donc un ACCIDENT de cette migration, et il a ete MESURE comme
tel : les trois regenerateurs en simulation rendaient `0 ajoute / 0 retire / 0 renomme` partout.
Aucune bijection ne peut voir ce trou -- une bijection compare une TABLE au BUILD COURANT, elle
ne lit jamais ce que le fichier DECLARE.

⚠ ET POUR UN SCAN D'INSTRUCTIONS, L'ESTAMPILLE EST LE SEUL SIGNAL QUI EXISTE.
`docs/rl/dsl-usage/*.tsv` sort d'un balayage des XREFS du binaire : aucune bijection membre a
membre ne peut le rattraper, un simple deplacement de code le perime. Que son contenu n'ait pas
bouge entre `rnca9r7q6c` et `t6dpr4k06g` ne se savait PAS avant de rejouer le scan (#330-r5) --
et c'est precisement pour ne plus dependre de cette chance que ce cliquet existe.

LE CRITERE, ET CE QU'IL ECARTE (un compte filtre DIT ce qu'il filtre)
---------------------------------------------------------------------
Un fichier est retenu quand ses `TETE` premieres lignes portent A LA FOIS :
  * une MARQUE DE GENERATION (`Auto-genere`, `GENERE`, `Regenerate`, `schema_version`, ...) ;
  * une DECLARATION DE SOURCE datee -- `data/symbols/<build>/`, `data/dumps/<build>/`,
    `build=<build>` -- portee par une ligne de COMMENTAIRE ou de prose, jamais par une ligne
    de donnees.

Sont ECARTES, et chaque motif est COMPTE a chaque run :
  * `lignes de DONNEES` -- un cache versionne porte une ligne PAR build (`scripts/cliquets-cache/
    probe_326_inventaire_natif.tsv` : `data/symbols/gqfc5mff6c<TAB>...`). Ce sont ses cles, pas
    son estampille ; les compter ferait rougir un artefact CORRECT, et un cliquet qui rougit a
    tort se fait desarmer dans la semaine ;
  * `pas de marque de generation` -- la prose historique. << RE faite sur `gqfc5mff6c` >> dans
    une case-doc datee est un fait EXACT ; le corriger detruirait ce qu'il documente. Cet axe
    est celui de `#330-r1`/`#330-r2`, pas celui-ci ;
  * `declare le build courant` -- le cas nominal.

CE QU'IL NE VOIT PAS, ET QU'IL DIT
-----------------------------------
Un artefact genere qui ne DECLARE aucune source lui est structurellement invisible. Ce n'est pas
un silence : le compte `generes SANS declaration de source` est imprime a chaque run. Un
artefact derive du build qui n'ecrit pas d'ou il sort est un residu a lui seul.

    python probe_330r4_estampilles_des_generes.py            # inventaire
    python probe_330r4_estampilles_des_generes.py --cliquet   # rc 1 s'il reste une estampille

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "python") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "python"))

import build_hash  # noqa: E402
import repo_read  # noqa: E402

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis (#486-r12).
#:
#: `toujours: True`, impose par le PERIMETRE : le balayage est `git ls-files` ENTIER moins quatre
#: prefixes -- n'importe quel fichier versionne, quelle que soit sa place et son extension, peut
#: acquerir une marque de generation et une estampille. Le borner par des chemins rouvrirait le
#: trou que #458 a mesure sur `probe_431` (967 fichiers dans un seau MUET).
#:
#: `build: True` est MESURE, pas suppose : le verdict compare l'estampille declaree a
#: `data/symbols/CURRENT`. Un changement de build fait rougir CHAQUE artefact genere qui n'a pas
#: ete rejoue -- c'est litteralement sa raison d'etre.
DECLENCHEUR = {
    "chemins": ("*", "**"),
    "build": True,
    "toujours": True,
    "raison": "Le perimetre est `git ls-files` ENTIER moins quatre prefixes, et le verdict "
              "confronte l'estampille declaree a `data/symbols/CURRENT` : tout fichier "
              "versionne et tout changement de build peuvent le faire changer d'avis.",
}

#: Nombre de lignes de tete ou une estampille compte. Meme ordre de grandeur que
#: `probe_330 --stamp-lines` (12) ; 14 couvre les en-tetes TSV a 7 lignes de commentaire suivies
#: d'un preambule.
TETE = 14

#: Le fichier se DECLARE genere. Motifs LUS dans les en-tetes du depot, pas devines.
GENERE_RE = re.compile(
    r"auto[- ]?gener|\bGENERE\b|\bGENERES\b|Regenerate|REGENERER|schema_version"
    r"|generated by|FICHIER GENERE|Auto-generated",
    re.IGNORECASE)

#: Une ligne de COMMENTAIRE ou de prose -- par opposition a une ligne de DONNEES. C'est ce qui
#: distingue une estampille d'une CLE de cache (cf. `probe_326_inventaire_natif.tsv`).
COMMENTAIRE_RE = re.compile(r"^\s*(#|//|/\*|\*|>|<!--|\"\"\"|'''|--)")

#: Les `.md` n'ont pas de syntaxe de commentaire : toute leur tete est de la prose.
PROSE_EXT = {".md", ".txt"}

EXCLUS = ("data/symbols/", ".claude/worktrees/", "node_modules/", "frida/dist/")

#: `<generateur>` tel que l'en-tete le nomme. Sans lui, un rouge est un cul-de-sac : le lecteur
#: sait QUOI est perime, pas COMMENT le reparer.
GENERATEUR_RE = re.compile(r"(?:python\s+)?(scripts/python/[\w./-]+\.py(?:\s+[\w-]+)?)")


def _declarations(build_re: re.Pattern) -> list:
    """[(motif, regex)] -- ou un build se DECLARE comme source d'un artefact."""
    h = build_re.pattern
    return [
        ("chemin data/symbols", re.compile(r"data[\\/]symbols[\\/]" + h)),
        ("chemin data/dumps", re.compile(r"data[\\/]dumps[\\/]" + h)),
        ("estampille build=", re.compile(r"build\s*=\s*`?" + h)),
    ]


def fichiers_suivis() -> list[str] | None:
    """`None` si git est muet -- jamais une liste vide, qui se lirait comme une mesure."""
    try:
        r = subprocess.run(["git", "ls-files", "-z"], cwd=str(REPO),
                           capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return [p for p in r.stdout.split("\0") if p and not any(p.startswith(x) for x in EXCLUS)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cliquet", action="store_true",
                    help="rc 1 s'il reste un artefact GENERE a estampille perimee")
    ap.add_argument("--tete", type=int, default=TETE)
    args = ap.parse_args()

    # La CIBLE avant tout compte -- meme discipline que `probe_330` et `probe_431` (#330-r3).
    try:
        rap = build_hash.verifier_la_forme()
        forme_refusee = ""
    except build_hash.FormeRefusee as exc:
        rap = build_hash.rapport_des_sources()
        forme_refusee = str(exc)
    build_hash.imprimer_les_sources(rap)
    if forme_refusee:
        print("  !! FORME REFUSEE -- %s" % forme_refusee.replace("\n", "\n     "))
        print("")
        print("CLIQUET ROUGE : sans forme valide, ce balayage ne peut RIEN affirmer.")
        return 1 if args.cliquet else 0
    courant = rap["courant"]
    decl = _declarations(build_hash.build_re())
    print("")

    fichiers = fichiers_suivis()
    if fichiers is None:
        print("NON MESURE : `git ls-files` est muet -- aucun verdict sur le depot.")
        return 1 if args.cliquet else 0
    octets = repo_read.read_bytes_many([REPO / r for r in fichiers])

    perimes: list = []
    ecartes: Counter = Counter()
    generes_sans_declaration: list = []
    n_generes = 0
    for rel, data in zip(fichiers, octets):
        if data is None:
            ecartes["fichier ILLISIBLE (OSError)"] += 1
            continue
        try:
            lignes = repo_read.to_text(data, errors="replace").splitlines()[:args.tete]
        except UnicodeDecodeError:                      # pragma: no cover -- errors=replace
            ecartes["fichier non UTF-8"] += 1
            continue
        tete = "\n".join(lignes)
        if not GENERE_RE.search(tete):
            ecartes["pas de marque de generation dans l'en-tete"] += 1
            continue
        n_generes += 1
        est_prose = Path(rel).suffix.lower() in PROSE_EXT
        trouve = False
        for lineno, ligne in enumerate(lignes, 1):
            commentaire = est_prose or bool(COMMENTAIRE_RE.match(ligne))
            for motif, rx in decl:
                m = rx.search(ligne)
                if not m:
                    continue
                trouve = True
                h = m.group(1)
                if not commentaire:
                    ecartes["ligne de DONNEES (cle de cache, pas estampille)"] += 1
                    continue
                if h == courant:
                    ecartes["declare le build COURANT"] += 1
                    continue
                gen = GENERATEUR_RE.search(tete)
                perimes.append((rel, lineno, motif, h,
                                gen.group(1) if gen else "GENERATEUR INCONNU",
                                ligne.strip()[:110]))
        if not trouve:
            generes_sans_declaration.append(rel)

    print("=== ARTEFACTS GENERES ET LEUR ESTAMPILLE (build courant : %s) ===" % courant)
    print("fichiers suivis balayes                      : %d" % len(fichiers))
    print("  portant une MARQUE DE GENERATION en tete   : %d" % n_generes)
    print("  ... dont l'estampille est PERIMEE          : %d occurrence(s) dans %d fichier(s)"
          % (len(perimes), len({p[0] for p in perimes})))
    print("")
    print("ECARTES -- et ce que chaque motif ecarte :")
    for motif, n in sorted(ecartes.items(), key=lambda kv: -kv[1]):
        print("    %-52s %d" % (motif, n))
    print("")
    print("⚠ CE QUE CE CLIQUET NE PEUT PAS VOIR".replace("⚠", "!!"))
    print("  generes SANS aucune declaration de source  : %d" % len(generes_sans_declaration))
    print("  Un artefact derive du build qui n'ecrit pas d'ou il sort est invisible ici -- ce")
    print("  n'est pas un silence, c'est le compte ci-dessus. Il ne fait PAS rougir : beaucoup")
    print("  de generes ne derivent d'aucun build (audits de couverture, index de foyers).")
    print("")

    if perimes:
        print("  --- ESTAMPILLES PERIMEES ---")
        for rel, lineno, motif, h, gen, txt in sorted(perimes):
            print("    %s:%d  [%s %s]" % (rel, lineno, motif, h))
            print("        %s" % txt)
            print("        REJOUER : %s" % gen)
        print("")

    if args.cliquet:
        if perimes:
            print("CLIQUET ROUGE : %d estampille(s) perimee(s) sur un artefact GENERE."
                  % len(perimes))
            print("  La correction est un RE-JEU du generateur, JAMAIS une reecriture du champ :")
            print("  reecrire l'estampille a la main la rend vraie et le CONTENU faux, ce qui est")
            print("  strictement pire -- on perd le seul signal qui restait.")
            return 1
        print("CLIQUET VERT : tout artefact genere qui declare une source nomme le build courant.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
