#!/usr/bin/env python
"""#270-r1-r1-r2 -- `StatType` sous `strict=False` : la TABLE et la PROCEDURE, pas le renommage.

CE QUE CE PROBE EST, ET CE QU'IL N'EST PAS. Il ne renomme RIEN. Il rend les trois choses sans
lesquelles le renommage n'est pas executable : le COMPTE re-derive, la TABLE de correspondance
`port -> build` derivee du dump (jamais ecrite a la main), et la PROCEDURE, avec son garde.

POURQUOI LE RENOMMAGE N'EST PAS JOUE ICI. `docs/rl/backlog.md` est touche par 36 des 40 dernieres
PR mergees ; un sweep de 183 fichiers Python entrerait en conflit avec toute PR en vol. Le meme
argument vaut ici : ce n'est pas une question de cout, c'est le MERGE qui l'interdit. La tranche
d'execution se planifie quand la flotte est calme.

LE DEFAUT VISE. `StatType` est inscrit `strict=False` au registre de `probe_313` : le port
RECONVENTIONNE les noms (`CRIT_CHANCE` pour `CriticalChance`, UPPER_CASE partout), donc
`StatType.CRIT_CHANCE` nomme le PORT, pas le build. `strict=False` relache les NOMS et JAMAIS les
VALEURS -- les 27 valeurs restent confrontees au build a chaque passe. La voie #427 (retenue pour
`KillUnitStep`) est de renommer les membres en VERBATIM du jeu et de passer le mirror en
`strict=True`.

LE GARDE EXISTE DEJA, et il n'y a pas lieu d'en ecrire un second :
`probe_270r4r2_empreinte_valeurs.py` hache la VALEUR de tout attribut de module ET de classe
d'`engine/`, canonicalisee par `int(x)` RECURSIVEMENT (un `IntEnum` EST un `int`), contre un arbre
temoin extrait COMPLET (sans `data/`, les caches lazy restent vides d'un cote et rendent des
divergences FAUSSES). C'est exactement la doctrine que la procedure ci-dessous applique -- avec une
particularite MESUREE ici : un renommage de membre est vu comme DISPARU + APPARU, donc chacun des
membres renommes doit etre declare `--disparition-voulue`, et une declaration qui ne correspond a
aucune disparition FAIT ECHOUER. La porte se referme d'elle-meme.

Usage, depuis `scripts/python` :

    python probe_270r1r1r2_renommage_stattype.py             # constat + table + procedure
    python probe_270r1r1r2_renommage_stattype.py --json
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

MIRROR = "engine/entities/stats.py"
CLASSE = "StatType"


def references() -> dict:
    """`{fichier: n}` des references EXECUTABLES `StatType.<MEMBRE>` -- par AST, jamais par grep.

    ⚠ L'ECART AVEC LE GREP EST MESURE, et il va dans les deux sens : un balayage textuel rend
    776 references dans 213 fichiers, dont des occurrences en PROSE (docstrings citant
    `StatType.Range`, `StatType.Health` -- des noms qui n'existent meme pas dans le mirror). Le
    renommage ne doit toucher QUE l'executable ; la prose se relit, elle ne se substitue pas."""
    out: dict = {}
    membres: dict = {}
    for p in sorted(PYDIR.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        n = 0
        for x in ast.walk(arbre):
            if (isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name)
                    and x.value.id == CLASSE):
                membres[x.attr] = membres.get(x.attr, 0) + 1
                n += 1
        if n:
            out[str(p.relative_to(PYDIR)).replace("\\", "/")] = n
    return {"par_fichier": out, "par_membre": membres}


def acces_dynamiques() -> list:
    """`getattr(StatType, <x>)` -- les sites qu'une substitution par AST ne verrait PAS.

    Les chercher fait partie du constat : une procedure qui promet << par AST, jamais par regex >>
    doit dire ce que l'AST ne couvre pas."""
    out = []
    for p in sorted(PYDIR.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for x in ast.walk(arbre):
            if (isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
                    and x.func.id == "getattr" and x.args
                    and isinstance(x.args[0], ast.Name) and x.args[0].id == CLASSE):
                out.append("%s:%d" % (str(p.relative_to(PYDIR)).replace("\\", "/"), x.lineno))
    return out


def table_de_correspondance(build: str | None = None) -> dict:
    """`{membre du PORT: nom du BUILD}` -- DERIVE du dump, jamais ecrit.

    L'appariement se fait par la VALEUR (l'ordinal), qui est precisement ce que `strict=False`
    n'a jamais relache. C'est ce qui rend la table sure : elle ne suppose aucune regle de
    transformation de casse -- et il y en aurait besoin, `CRIT_CHANCE` -> `CriticalChance` n'etant
    pas une simple recasse."""
    import probe_313_enum_mirror_bijection as P
    b = build or P.current_build()
    m = P.PAR_CLS[CLASSE]
    port = P.membres_mirror(m.rel, m.cls)          # {valeur: {noms}}
    jeu = P.enum_natif(b, m.cle)
    table, sans_pendant, recasse_seule = {}, [], 0
    for val, noms_port in sorted(port.items()):
        noms_jeu = sorted(jeu.get(val) or [])
        for n in sorted(noms_port):
            if not noms_jeu:
                sans_pendant.append((n, val))
                continue
            table[n] = noms_jeu[0]
            if n.replace("_", "").lower() == noms_jeu[0].lower():
                recasse_seule += 1
    return {"build": b, "table": table, "sans_pendant": sans_pendant,
            "recasse_seule": recasse_seule}


def rapport(js: bool) -> int:
    refs = references()
    corr = table_de_correspondance()
    par_f, par_m = refs["par_fichier"], refs["par_membre"]
    total = sum(par_f.values())
    engine = {k: v for k, v in par_f.items() if k.startswith("engine/")}
    tests = {k: v for k, v in par_f.items() if k.startswith("tests/")}
    autres = {k: v for k, v in par_f.items()
              if not k.startswith("engine/") and not k.startswith("tests/")}
    if js:
        print(json.dumps({"total": total, "fichiers": len(par_f), "membres": par_m,
                          "correspondance": corr}, indent=2, sort_keys=True))
        return 0

    print("== CONSTAT re-derive (AST, executable seulement) ==")
    print("   references `%s.<MEMBRE>` : %d dans %d fichiers" % (CLASSE, total, len(par_f)))
    print("      engine/ : %-4d dans %-3d fichiers" % (sum(engine.values()), len(engine)))
    print("      tests/  : %-4d dans %-3d fichiers" % (sum(tests.values()), len(tests)))
    print("      autres  : %-4d dans %-3d fichiers  (probes, outillage)"
          % (sum(autres.values()), len(autres)))
    print("   membres DISTINCTS effectivement ecrits : %d sur %d au mirror"
          % (len(par_m), len(corr["table"])))
    print("   ⚠ la ligne de backlog annoncait 553 references / 169 fichiers : RE-DERIVER, le")
    print("     corpus a grossi et le critere (AST vs grep) n'etait pas le meme.")

    print("")
    print("== TABLE de correspondance PORT -> BUILD (derivee du dump %s) ==" % corr["build"])
    ecrits = set(par_m)
    for port_nom in sorted(corr["table"]):
        jeu = corr["table"][port_nom]
        marque = "  <- ECRIT %dx" % par_m[port_nom] if port_nom in ecrits else ""
        egal = "IDENTIQUE" if port_nom == jeu else ""
        print("   %-24s -> %-24s %-10s%s" % (port_nom, jeu, egal, marque))
    print("   dont un simple changement de CASSE suffirait : %d / %d"
          % (corr["recasse_seule"], len(corr["table"])))
    if corr["sans_pendant"]:
        print("   ⚠ SANS PENDANT dans le build (le renommage ne peut PAS les nommer) :")
        for n, v in corr["sans_pendant"]:
            print("        %-24s = %d" % (n, v))

    print("")
    print("== PROCEDURE (a jouer quand la flotte est calme -- PAS dans cette tranche) ==")
    print("   1. EMETTRE l'empreinte de reference AVANT toute edition :")
    print("        python probe_270r4r2_empreinte_valeurs.py --emettre <ref.json>")
    print("   2. RENOMMER les membres de `%s` dans `%s` en verbatim du build" % (CLASSE, MIRROR))
    print("      (table ci-dessus), et passer son entree du registre `probe_313` en `strict=True`.")
    print("   3. SUBSTITUER les %d sites EXECUTABLES -- par AST, jamais par regex :" % total)
    print("      un `%s.<MEMBRE>` est un `ast.Attribute` dont le `value` est `Name('%s')`."
          % (CLASSE, CLASSE))
    print("      La PROSE (docstrings, commentaires) se RELIT : elle cite deja des noms qui")
    print("      n'existent pas au mirror, donc une substitution textuelle y ecrirait du faux.")
    print("   4. COMPARER, en declarant CHAQUE membre renomme :")
    print("        python probe_270r4r2_empreinte_valeurs.py --comparer <ref.json> \\")
    print("            --disparition-voulue engine.entities.stats.%s.<ANCIEN> ..." % CLASSE)
    print("      Un renommage est vu DISPARU + APPARU ; les VALEURS, elles, ne doivent pas")
    print("      bouger (canonicalisation `int(x)`, un `IntEnum` EST un `int`). Une declaration")
    print("      qui ne correspond a AUCUNE disparition FAIT ECHOUER -> la porte se referme.")
    print("   5. REJOUER `probe_313` : l'entree doit passer `strict=True` sans MANQUANT ni MORT.")
    print("")
    print("== PORTEE -- ce que la procedure ne couvre PAS ==")
    print("   - les %d references hors `engine/` (tests, probes) changent AUSSI : elles sont"
          % (sum(tests.values()) + sum(autres.values())))
    print("     dans le meme sweep, et c'est ce qui rend le lot indivisible.")
    dyn = acces_dynamiques()
    print("   - acces DYNAMIQUES (`getattr(StatType, ...)`), qu'une substitution AST ne verrait")
    print("     pas : %d trouve(s)%s" % (len(dyn), (" -- " + ", ".join(dyn)) if dyn else ""))
    if not dyn:
        print("     ZERO n'est pas une preuve d'absence : une cle textuelle dans un dict de")
        print("     configuration echapperait aussi a cette recherche.")
    print("   - `StatPart`, voisin immediat du meme fichier, est dans le MEME cas et n'est PAS")
    print("     traite ici (il n'a pas ete mesure).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    return rapport(a.json)


if __name__ == "__main__":
    sys.exit(main())
