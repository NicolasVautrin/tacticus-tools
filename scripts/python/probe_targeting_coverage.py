"""MESURE la permissivite du gate de ciblage, PAR ABILITY -- ensembles desormais DERIVES.

CE QUE CA REPOND
----------------
Une regle de `TargetingRule` non portee ne refuse JAMAIS -- degradation PERMISSIVE assumee (le
port ne peut pas inventer un refus qu'il ne sait pas decider). La consequence n'est pas neutre :
le moteur offline accepte des casts que le natif REFUSE, et un entrainement ira exploiter cet
espace d'action elargi. C'est silencieux : ni erreur, ni crash.

Angle propre de ce probe : la vue PAR ABILITY (« quelles regles cette ability exige-t-elle que
le port n'implemente pas ? »). La vue PAR REGLE est `probe_429_targeting_rule_inventory.py` ;
la vue bornee a la cascade CIBLE est `probe_249_unported_rule_carriers.py`.

CE QUI A CHANGE (#429)
----------------------
Ce probe portait DEUX listes SAISIES : `PORTEES` (7 regles « effectivement consommees par la
cascade portee ») et `NON_REGLES` (16 bits « qui ne sont pas des regles de refus »). La premiere
etait **PERIMEE** : elle ignorait les 14 regles portees depuis (#241 portee, #243 adjacence,
#245 healable, #249 tuile-ennemie, #250 domaine + dynamique caster, #253 tuile, #366-r1 clause
tuile-nulle...). Consequence MESUREE : le probe annoncait **48 masques sur 102** exigeant une
regle « inerte », et listait comme non portees `TargetIsTile`, `TargetTileIsFree`,
`TargetHasFreeAdjacentTile`, `TargetIsNotAdjacent`, `TargetTileHasEnemyUnit`, `TargetIsSummon`,
`TargetIsHealable`, `TargetIsInRange`, `TargetIsUnit`, `TargetIsActor` -- **dix regles qui sont
portees**. Une liste de « ce qui est porte », ecrite a la main, se perime a chaque tranche
livree : c'est la donnee qu'on ne saisit jamais.

Les deux listes viennent maintenant de la derivation :
  * PORTE       = le port RENDS la regle comme code de refus (AST, `rules_returned_by_port`) ;
  * NON-REGLE   = `RULE_ROLE[...].kind` vaut PERMISSION / REASON / READER_UNKNOWN.

Ce probe MESURE, il ne garde pas. La GARDE est
`tests/engine/runner/test_targeting_rule_inventory.py`.

Sortie ASCII only (console Windows cp1252).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import probe_429_targeting_rule_inventory as P  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES  # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR  # noqa: E402
from engine.runner.abilities.targeting_rule_inventory import RULE_ROLE  # noqa: E402

GATE_KINDS = ("GATE_TARGET", "GATE_CASTER", "GATE_ADD_CASTER")


def main() -> int:
    rendues = set(P.rules_returned_by_port())
    # Un bit est « exigible » s'il est un GATE dont le port ne rend pas le code de refus.
    manquantes_set = {n for n, r in RULE_ROLE.items()
                      if r.kind in GATE_KINDS and r.code(n) not in rendues}

    avec, sans = [], []
    for aid, cls in sorted(ABILITY_CLASSES.items()):
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        (sans if opts is None else avec).append((aid, cls, opts))

    print("registre : %d abilities, %d avec masque, %d SANS"
          % (len(ABILITY_CLASSES), len(avec), len(sans)))
    print("  (une ability sans masque n'est gatee par RIEN -- retour 0 immediat)")
    print("regles GATE de l'enum : %d ; portees par le port : %d ; NON portees : %d"
          % (sum(1 for r in RULE_ROLE.values() if r.kind in GATE_KINDS),
             sum(1 for n, r in RULE_ROLE.items() if r.kind in GATE_KINDS and r.code(n) in rendues),
             len(manquantes_set)))
    print("")

    manquantes = {}
    inertes = 0
    for aid, cls, opts in avec:
        r = int(opts.rules)
        # ARMEMENT, pas « bits poses » : trois regles sont armees par AUTRE CHOSE que leur bit.
        noms = sorted(n for n in manquantes_set if _armee(n, r))
        if not noms:
            continue
        inertes += 1
        print("%-5d %-34s %s" % (aid, cls.__name__, " ".join(noms)))
        for n in noms:
            manquantes[n] = manquantes.get(n, 0) + 1

    print()
    print("%d masques sur %d exigent au moins une regle NON PORTEE offline" % (inertes, len(avec)))
    print()
    print("regles non portees, par frequence -- c'est l'ordre de rentabilite d'un portage :")
    for nom, n in sorted(manquantes.items(), key=lambda kv: (-kv[1], kv[0])):
        arme = RULE_ROLE[nom].armed_by
        print("  %-42s %3d ability(s)%s"
              % (nom, n, "" if arme is None else "   [ARME PAR : %s]" % arme))
    return 0


def _armee(nom: str, rules: int) -> bool:
    pred = P.ARMED_BY.get(nom)
    if pred is not None:
        return bool(pred(rules))
    bit = getattr(TR, nom, None)
    return bool(bit is not None and (rules & int(bit)))


if __name__ == "__main__":
    sys.exit(main())
