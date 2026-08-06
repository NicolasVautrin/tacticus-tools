"""probe_181 -- CLIQUET : aucune ability du registre ne doit etre SANS son TARGETING_OPTIONS.

Croise ABILITY_CLASSES (engine/runner/abilities/handler.py) avec
getattr(cls, "TARGETING_OPTIONS", None) -- le MEME acces que
`engine/runner/abilities/targeting.py::get_invalid_target_reason`, MRO comprise -- et ventile
par module d'origine.

#430 : ce probe RENDAIT `0` INCONDITIONNELLEMENT. Il etait cite comme << cliquet >> par le
`CLAUDE.md` (<< faire passer probe_181 avant d'ouvrir une PR >>) et par toutes les case-docs,
mais il ne pouvait PAS rougir -- un inventaire deguise en garde-fou. Mesure : renommer le
`TARGETING_OPTIONS` de `HarbingerOfDestructionAbility` (1008) le laissait VERT. Le gate est
pose ici ; le zero global qu'il exige est celui deja atteint (98/98 le 2026-08-01).

Le gate porte sur le compte GLOBAL, jamais sur le perimetre `--module` (qui ne filtre que
l'affichage detaille) : une ability sans masque est une degradation PERMISSIVE du moteur
(`getattr(...) is None` -> retour 0 immediat, aucun gate de ciblage), quel que soit son module.

Sortie ASCII stricte (console cp1252).

Usage:
    python probe_181_targeting_gaps.py [--module necrons,orks,votann,genestealer]
"""

from __future__ import annotations

import argparse
import sys

from engine.runner.abilities.handler import ABILITY_CLASSES

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis (#486-r12).
#: MESURE (`probe_486r12_declencheurs.py --mesurer`) : 366 fichiers ouverts, dont `data/seed-bc.json`
#: -- que ce fichier de 76 lignes ne nomme NULLE PART. Il arrive par la cascade d'import de
#: `ABILITY_CLASSES`, et c'est exactement ce qu'une relecture du source ne peut pas donner.
DECLENCHEUR = {
    "chemins": ("scripts/python/**/*.py", "data/seed-bc.json"),
    "build": False,
    "toujours": False,
    "raison": "Il n'a AUCUN perimetre de fichiers : il importe `ABILITY_CLASSES` et croise le "
              "registre en memoire. Le declencheur est donc la FERMETURE D'IMPORT de "
              "`engine.runner.abilities.handler` -- prise a tout `scripts/python/**` parce "
              "qu'un import indirect peut atteindre n'importe quel module (mesure : il lit "
              "`gameconfig.py`, hors `engine/`). Aucune dependance au build : le masque lu est "
              "`getattr(cls, 'TARGETING_OPTIONS')`, une valeur du PORT.",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--module",
        default="",
        help="filtre CSV sur le nom court du module (ex. necrons,orks,votann,genestealer)",
    )
    args = ap.parse_args()
    wanted = {m.strip() for m in args.module.split(",") if m.strip()}

    rows = []
    for ability_type, cls in sorted(ABILITY_CLASSES.items()):
        mod = cls.__module__.rsplit(".", 1)[-1]
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        rows.append((ability_type, cls.__name__, mod, opts))

    total = len(rows)
    with_mask = [r for r in rows if r[3] is not None]
    without = [r for r in rows if r[3] is None]

    print("ABILITY_CLASSES        : %d" % total)
    print("avec TARGETING_OPTIONS : %d" % len(with_mask))
    print("MANQUANTES (global)    : %d" % len(without))
    print("")

    by_mod = {}
    for ability_type, name, mod, opts in without:
        by_mod.setdefault(mod, []).append((ability_type, name))
    print("-- manquantes ventilees par module --")
    for mod in sorted(by_mod):
        print("  %-16s %d" % (mod, len(by_mod[mod])))
    print("")

    if wanted:
        print("-- detail perimetre %s --" % ",".join(sorted(wanted)))
        n = 0
        for ability_type, name, mod, opts in without:
            if mod in wanted:
                n += 1
                print("  %-6d %-40s %s" % (ability_type, name, mod))
        print("  total perimetre manquant: %d" % n)
        print("")
        print("-- deja poses dans le perimetre --")
        for ability_type, name, mod, opts in with_mask:
            if mod in wanted:
                print("  %-6d %-40s %s  rules=0x%x" % (ability_type, name, mod, opts.rules))
        print("")

    if without:
        print("[181] ROUGE -- %d ability(s) au registre SANS masque de ciblage :" % len(without))
        for ability_type, name, mod, _ in without:
            print("  MANQUANT %-6d %-40s %s" % (ability_type, name, mod))
        print("  => poser le litteral lu au `<X>Ability$$.ctor` (piege des surcharges PRESET+flags")
        print("     et de la recopie d'un champ STATIQUE : cf. CLAUDE.md). Sans masque,")
        print("     `get_invalid_target_reason` rend 0 immediatement -- aucun gate, degradation")
        print("     PERMISSIVE, ni erreur ni crash.")
        return 1

    print("[181] OK -- les %d ability(s) du registre portent leur TARGETING_OPTIONS." % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
