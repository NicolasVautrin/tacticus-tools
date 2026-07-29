"""#249 -- RE-DERIVE la carte « regle de ciblage NON PORTEE -> abilities PORTEUSES ».

Pourquoi ce probe existe : l'inventaire en tete de
`engine/runner/abilities/targeting.py` declare 13 regles NON PORTEES, mais rien ne disait
COMBIEN d'abilities du registre les portent -- d'ou deux affirmations « seul porteur »
COMMITEES et FAUSSES (`CasterHasFreeAdjacentTile` chez 1028 seul ; `TargetIsNotAnObject`
chez 1113 seul). Ce probe recompte a partir des DEUX sources de masque du port
(`ABILITY_CLASSES[aid].TARGETING_OPTIONS` et `TARGETING_OPTIONS_UNPORTED`), donc il ne peut
pas se desynchroniser du code.

Il verifie AUSSI qu'aucun masque ne pose de bit hors enum `TargetingRule`.

Sortie : ASCII seulement (console cp1252).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED  # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR  # noqa: E402


# Les 13 regles que l'inventaire en tete de `targeting.py` recense comme NON PORTEES par la cascade
# CIBLE avant #249, avec leur etat APRES #249. Toute divergence entre cette table et l'inventaire est
# un bug de l'un des deux. `True` = la cascade du port l'evalue desormais.
TARGET_RULES_AUDIT = [
    (TR.TargetIsHealable,          False),   # bit  8 -- fiche #245
    (TR.TargetIsRepairable,        False),   # bit 16
    (TR.TargetTileIsFreeOrEnemy,   False),   # bit 17
    (TR.TargetIsDisplaceable,      False),   # bit 18
    (TR.TargetTileHasEnemyUnit,    True),    # bit 19 -- PORTEE par #249
    (TR.CasterHasFreeAdjacentTile, False),   # bit 21 -- INERTE chez ses DEUX porteurs (#249)
    (TR.TargetIsAllowedForCaster,  False),   # bit 23
    (TR.TargetIsNotAnObject,       False),   # bit 33
    (TR.TargetHas1Tiles,           False),   # bit 47
    (TR.TargetHas3Tiles,           False),   # bit 48
    (TR.TargetHas7Tiles,           False),   # bit 49
    (TR.TargetIsHero,              False),   # bit 50
    (TR.TargetIsNotSteppable,      False),   # bit 51
]


def collect_masks():
    """(aid -> (rules, source)) pour les DEUX sources de masque du port."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    out = {}
    for aid, klass in sorted(ABILITY_CLASSES.items()):
        opts = getattr(klass, "TARGETING_OPTIONS", None)
        if opts is not None:
            out[int(aid)] = (int(opts.rules), klass.__name__)
    for aid, opts in sorted(TARGETING_OPTIONS_UNPORTED.items()):
        if int(aid) not in out:
            out[int(aid)] = (int(opts.rules), "UNPORTED-table")
    return out


def main() -> int:
    from engine.runner.abilities.handler import ABILITY_CLASSES
    masks = collect_masks()
    registry = len(ABILITY_CLASSES)
    with_mask = sum(1 for aid in ABILITY_CLASSES
                    if getattr(ABILITY_CLASSES[aid], "TARGETING_OPTIONS", None) is not None)
    print("ABILITY_CLASSES = %d ; masques poses = %d ; manquants = %d"
          % (registry, with_mask, registry - with_mask))
    print("masques lisibles au total (registre + table UNPORTED) = %d" % len(masks))

    known = 0
    for r in TR:
        known |= int(r)
    stray = {}
    for aid, (rules, name) in masks.items():
        extra = rules & ~known
        if extra:
            stray[aid] = (extra, name)
    print("bits hors enum TargetingRule : %d" % len(stray))
    for aid, (extra, name) in sorted(stray.items()):
        print("  %d %-28s bits 0x%x" % (aid, name, extra))

    print("")
    print("--- LES 13 REGLES DE L'AUDIT x PORTEURS --------------------------------")
    touched = set()
    for rule, ported in TARGET_RULES_AUDIT:
        carriers = sorted(aid for aid, (rules, _n) in masks.items() if rules & int(rule))
        if not ported:
            touched.update(carriers)
        bit = int(rule).bit_length() - 1
        print("%-26s (bit %2d, 0x%-15x) [%s] -> %d porteur(s) : %s"
              % (rule.name, bit, int(rule), "PORTEE   " if ported else "NON PORTEE",
                 len(carriers),
                 ", ".join(str(a) for a in carriers) if carriers else "-"))
        for aid in carriers:
            print("      %5d  %s  mask=0x%x" % (aid, masks[aid][1], masks[aid][0]))
    print("")
    print("abilities touchees par >= 1 regle NON PORTEE : %d / %d"
          % (len(touched), len(masks)))
    print("  " + ", ".join(str(a) for a in sorted(touched)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
