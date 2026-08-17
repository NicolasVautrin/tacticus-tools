"""#5 -- CHANTIER `DslContext` live-state : la MESURE avant l'architecture.

La ligne de backlog dit << Architecture a poser, pas d'enigme a trancher >> et pointe
`docs/rl/dsl-live-context-substrate.md`, dont l'etat declare (2026-07-18) est << Voie A
IMPLEMENTEE (fondation + 1er cas) >>. Ce probe ne pose AUCUNE architecture : il mesure ce qui est
deja la, ce qui reste, et surtout le RAYON DE SOUFFLE d'une edition de `engine/dsl/base.py` -- le
socle que tout le moteur consomme.

Pourquoi un probe et pas une prose : les quatre chiffres ci-dessous se PERIMENT (ils bougent a
chaque tranche livree), et un plan de chantier chiffre de memoire est exactement ce que la doctrine
du depot interdit. On les re-derive.

ETAGES

  1. RAYON DE SOUFFLE de `engine/dsl/base.py` -- qui l'importe, et QUOI. Un socle se mesure par
     SYMBOLE : `DslContext` (le contrat de contexte) et `_pos`/`_feet` (les lecteurs de position)
     n'ont pas le meme rayon, et c'est la difference qui dit ce qu'on peut changer sans rupture.
  2. VOIE A -- l'etat du live-state. `LiveUnit` (la vue dont les champs MUTABLES sont re-lus de
     l'etat a chaque acces) existe-t-elle, et QUI la construit ? C'est le seul canal par lequel un
     arbre DSL unique peut re-evaluer un predicat de position APRES une mutation intra-arbre.
  3. CONSTRUCTEURS de `DslContext` -- le chantier annonce << 11 constructeurs >>. Le compte se
     re-derive, et chacun est classe LIVE (il passe par le substrat runner) ou FIGE.
  4. `Cache` -- le noeud natif `IdunBattleLogic.Entities.DSLSelectors$$Cache`, qui fige l'IDENTITE (pas la position). Le
     chantier le declarait absent puis present ; on regarde.

Usage :
    python probe_5_dslcontext_live_state.py            # les quatre etages
    python probe_5_dslcontext_live_state.py --detail   # + la liste des sites
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import subprocess
import sys

RACINE = pathlib.Path(__file__).resolve().parent
ENGINE = RACINE / "engine"
SOCLE = "engine/dsl/base.py"


def _fichiers() -> list[pathlib.Path]:
    """Le perimetre, DERIVE de `git ls-files`. Une panne de git est PAS MESURE, jamais un
    perimetre vide -- meme regle que les autres recenseurs du depot."""
    try:
        out = subprocess.run(["git", "-C", str(RACINE.parent.parent), "ls-files", "-z",
                              "scripts/python/engine/**/*.py", "scripts/python/engine/*.py"],
                             capture_output=True, text=True, timeout=60, check=True)
    except (OSError, subprocess.SubprocessError) as exc:            # noqa: BLE001
        raise SystemExit("PAS MESURE : `git ls-files` muet (%s)" % exc)
    base = RACINE.parent.parent
    return [base / r for r in out.stdout.split("\0") if r]


def _arbres():
    for f in _fichiers():
        try:
            yield f, ast.parse(f.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue                                   # illisible = ABSENT, pas un zero


def etage1_rayon(detail: bool) -> dict:
    """Qui importe `engine.dsl.base`, et QUEL symbole. Le module est atteint par des imports
    RELATIFS de profondeur variable (`..dsl.base`, `...dsl.base`, `....dsl.base`) : on apparie sur
    le suffixe `dsl.base`, jamais sur une profondeur devinee."""
    par_symbole: dict[str, list[str]] = {}
    fichiers: set[str] = set()
    for f, arbre in _arbres():
        rel = f.as_posix().split("scripts/python/")[-1]
        for n in ast.walk(arbre):
            if not isinstance(n, ast.ImportFrom):
                continue
            mod = n.module or ""
            if not (mod == "dsl.base" or mod.endswith(".dsl.base")
                    or (n.level and mod.endswith("dsl.base"))):
                continue
            fichiers.add(rel)
            for a in n.names:
                par_symbole.setdefault(a.name, []).append(rel)
    print("[1] RAYON DE SOUFFLE de `%s` : %d fichier(s) importateur(s), %d symbole(s) distincts"
          % (SOCLE, len(fichiers), len(par_symbole)))
    for sym, sites in sorted(par_symbole.items(), key=lambda kv: -len(kv[1])):
        print("      %-24s %3d lecteur(s)" % (sym, len(sites)))
        if detail and len(sites) <= 8:
            for s in sorted(sites):
                print("            " + s)
    print("    LIRE : un symbole a 3 lecteurs se change en une tranche ; `DslContext` ne se change")
    print("    qu'en COMPATIBILITE (champ neuf a defaut None), jamais en rupture de contrat.")
    return par_symbole


def etage2_liveunit(detail: bool) -> int:
    """`LiveUnit` -- la vue dont les champs MUTABLES sont re-lus a chaque acces. C'est le canal de
    la << voie A >> : sans lui, un arbre DSL unique lit des positions PERIMEES apres un `MoveUnit`
    intra-arbre."""
    definitions, constructions = [], []
    for f, arbre in _arbres():
        rel = f.as_posix().split("scripts/python/")[-1]
        for n in ast.walk(arbre):
            if isinstance(n, ast.ClassDef) and n.name == "LiveUnit":
                definitions.append("%s:%d" % (rel, n.lineno))
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == "LiveUnit"):
                constructions.append("%s:%d" % (rel, n.lineno))
    print("[2] VOIE A -- `LiveUnit` : %d definition(s), %d construction(s)"
          % (len(definitions), len(constructions)))
    for d in definitions:
        print("      def  " + d)
    if detail:
        for c in sorted(constructions):
            print("      new  " + c)
    if not definitions:
        print("    ⚠ ABSENTE : la voie A n'est PAS en place, contrairement a ce que la fiche"
              " declare.")
    return len(constructions)


def _nom_appele(n: ast.Call) -> str:
    """Le nom de la fonction appelee, qu'elle soit NUE (`DslContext(...)`) ou QUALIFIEE
    (`base.DslContext(...)`). Ne les distinguer pas est le vice qui a fait rendre 5 la ou le
    depot en porte 12 : un recenseur ne rend pas zero sur ce qu'il ne visite pas."""
    if isinstance(n.func, ast.Name):
        return n.func.id
    if isinstance(n.func, ast.Attribute):
        return n.func.attr
    return ""


def etage3_constructeurs(detail: bool) -> int:
    """Les PRODUCTEURS de contexte, en DEUX voies -- et la seconde manquait.

    Le chantier annoncait << 11 constructeurs >> ; un recenseur qui ne comptait que les appels NUS
    `DslContext(...)` en rendait 5. Deux voies existent, et la seconde est majoritaire :

      * CONSTRUCTION : `DslContext(...)`, nue ou qualifiee ;
      * DERIVATION : `dataclasses.replace(<ctx>, ...)` -- un contexte NEUF, derive d'un existant.
        C'est ce que font `Foreach`/`Filter` pour lier leur sujet, et c'est le mecanisme meme dont
        le chantier parle (le natif RECONSTRUIT son `AbilityEntities` entre enfants).

    ⚠ Le TYPE du premier argument d'un `replace` n'est PAS decidable a l'AST. Les sites sont donc
    LISTES, pas attribues : la partition est exhaustive, l'imputation reste a l'oeil. Un compte qui
    prendrait ces sites pour des `DslContext` serait un MAJORANT presente comme une mesure.
    """
    avec_board, sans_board, derives = [], [], []
    for f, arbre in _arbres():
        rel = f.as_posix().split("scripts/python/")[-1]
        for n in ast.walk(arbre):
            if not isinstance(n, ast.Call):
                continue
            nom = _nom_appele(n)
            site = "%s:%d" % (rel, n.lineno)
            if nom == "DslContext":
                (avec_board if any(k.arg == "board" for k in n.keywords)
                 else sans_board).append(site)
            elif nom == "replace" and n.args:
                derives.append(site)
    total = len(avec_board) + len(sans_board)
    print("[3] PRODUCTEURS de contexte")
    print("      CONSTRUCTION `DslContext(...)` : %d -- %d AVEC `board`, %d sans"
          % (total, len(avec_board), len(sans_board)))
    print("      DERIVATION `replace(<x>, ...)` : %d site(s) -- TYPE NON DECIDABLE a l'AST,"
          " listes et non attribues" % len(derives))
    if detail:
        for s in sorted(avec_board):
            print("      board  " + s)
        for s in sorted(sans_board):
            print("      nu     " + s)
        for s in sorted(derives):
            print("      repl   " + s)
    print("    LIRE : seuls les contextes AVEC board evaluent une geometrie -- ce sont eux que la")
    print("    question << position live ou figee ? >> concerne. Les DERIVATIONS sont le mecanisme")
    print("    meme du chantier (le natif reconstruit son `AbilityEntities` entre enfants).")
    return total


def etage4_cache(detail: bool) -> int:
    """Le noeud `Cache` (`IdunBattleLogic.Entities.DSLSelectors$$Cache`) fige l'IDENTITE d'une
    selection, JAMAIS sa position -- c'est la moitie << figee explicitement >> du modele a deux
    modes que le chantier decrit."""
    definitions, usages = [], []
    for f, arbre in _arbres():
        rel = f.as_posix().split("scripts/python/")[-1]
        for n in ast.walk(arbre):
            if isinstance(n, ast.ClassDef) and n.name == "Cache":
                definitions.append("%s:%d" % (rel, n.lineno))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Cache":
                usages.append("%s:%d" % (rel, n.lineno))
    print("[4] `Cache` (fige l'IDENTITE, pas la position) : %d definition(s), %d usage(s)"
          % (len(definitions), len(usages)))
    for d in definitions:
        print("      def  " + d)
    if detail:
        for u in sorted(usages):
            print("      use  " + u)
    return len(usages)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--detail", action="store_true", help="liste les sites")
    args = ap.parse_args()

    etage1_rayon(args.detail)
    print("")
    etage2_liveunit(args.detail)
    print("")
    etage3_constructeurs(args.detail)
    print("")
    etage4_cache(args.detail)
    print("")
    print("PORTEE DE LA MESURE -- ce que ce probe ne dit PAS :")
    print("  * il compte des SITES, pas des comportements : un import n'est pas un usage, et un")
    print("    `DslContext` construit n'est pas un arbre evalue ;")
    print("  * il ne sait pas dire si une composition structurelle est repliee en ARBRE ou")
    print("    recablee a la main -- ce tri se fait au decompile, pas a l'AST ;")
    print("  * il ne voit que `scripts/python/engine/**` (perimetre derive de `git ls-files`).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
