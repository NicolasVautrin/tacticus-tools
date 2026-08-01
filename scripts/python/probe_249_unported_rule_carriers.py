"""#249 -- carte « regle de ciblage NON PORTEE -> abilities PORTEUSES », desormais DERIVEE.

CE QUI A CHANGE (#429), ET POURQUOI
------------------------------------
Ce probe portait une table SAISIE, `TARGET_RULES_AUDIT`, de **13** regles -- « les 13 regles que
l'inventaire en tete de `targeting.py` recense comme NON PORTEES par la cascade CIBLE ». Elle
avait DEUX defauts, et ils se cumulaient :

1. **PERIMETRE MUET.** 13 regles sur les 46 GATE de l'enum : le probe ne couvrait pas la cascade
   CASTER, ni la branche `GetCasterNotAddedReason`, ni la ligne de vue -- mais son titre et sa
   sortie (« abilities touchees par >= 1 regle NON PORTEE : 6 / 103 ») se lisaient comme une
   reponse a la question ENTIERE. La bonne reponse, re-derivee, est **25** regles non portees et
   **103 / 103** abilities touchees (dont **26** hors regles armees par defaut).

2. **COMPTE DE PORTEURS FAUX PAR CONSTRUCTION.** Il comptait « les masques qui posent le bit ».
   Or TROIS regles du filtre statique ne sont PAS armees par leur propre bit :
     * `TargetIsAllowedForCaster` (TAUNT) est armee par `TargetIsEnemy | TargetIsCasterOrEnemy`
       et desarmee par `AllowIgnoreForcedAttackTarget` -- son bit n'est JAMAIS teste. Compte par
       le bit : **0**. Compte par l'armement : **59**.
     * `TargetIsNotSteppable` est armee par son bit OU par `get_IsUnitTargeting` (= ABSENCE des
       bits 6/44/46) sans `AllowSteppableUnit`. Par le bit : **1**. Par l'armement : **83**.
     * `TargetIsUnit` est armee par l'ABSENCE des trois autres tetes de domaine.
   Le « 9 des 13 regles auditees ont ZERO porteur -- il n'y a rien a y porter » qui a longtemps
   accompagne cette table etait donc, pour deux d'entre elles, un zero de METHODE.

La table saisie a disparu. Le probe DELEGUE a `probe_429_targeting_rule_inventory.py`, qui
derive l'enum du dump, l'etat de port de l'AST et l'armement du role natif relu. Ce fichier
reste comme POINT D'ENTREE historique (les case-docs et le backlog le citent nommement) et
comme VUE BORNEE : il n'imprime que la cascade CIBLE, et il le DIT.

Sortie : ASCII seulement (console cp1252).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import probe_429_targeting_rule_inventory as P  # noqa: E402
from engine.runner.abilities.targeting_rule_inventory import RULE_ROLE  # noqa: E402

# PERIMETRE EXPLICITE de cette vue -- la cascade CIBLE seule. Ce n'est PAS l'inventaire complet :
# celui-la est `probe_429_targeting_rule_inventory.py`, et c'est lui qui prouve sa couverture.
PERIMETRE = "GATE_TARGET"

# Le perimetre HISTORIQUE de la table saisie, conserve pour chiffrer l'ecart -- pas pour decider.
PERIMETRE_HISTORIQUE_13 = (
    "TargetIsHealable", "TargetIsRepairable", "TargetTileIsFreeOrEnemy", "TargetIsDisplaceable",
    "TargetTileHasEnemyUnit", "CasterHasFreeAdjacentTile", "TargetIsAllowedForCaster",
    "TargetIsNotAnObject", "TargetHas1Tiles", "TargetHas3Tiles", "TargetHas7Tiles",
    "TargetIsHero", "TargetIsNotSteppable",
)


def main() -> int:
    from engine.runner.abilities.handler import ABILITY_CLASSES
    masks = P.collect_masks()
    rendues = set(P.rules_returned_by_port())

    with_mask = sum(1 for aid in ABILITY_CLASSES
                    if getattr(ABILITY_CLASSES[aid], "TARGETING_OPTIONS", None) is not None)
    print("ABILITY_CLASSES = %d ; masques poses = %d ; manquants = %d"
          % (len(ABILITY_CLASSES), with_mask, len(ABILITY_CLASSES) - with_mask))
    print("masques lisibles au total (registre + table UNPORTED) = %d" % len(masks))
    print("")
    print("VUE BORNEE : cascade CIBLE seulement (%s). Inventaire COMPLET et preuve de" % PERIMETRE)
    print("couverture : `python scripts/python/probe_429_targeting_rule_inventory.py`.")
    print("")

    cibles = [n for n, r in RULE_ROLE.items() if r.kind == PERIMETRE]
    non_portees = [n for n in cibles if RULE_ROLE[n].code(n) not in rendues]
    print("--- CASCADE CIBLE : %d regles, %d non portees ---------------------------"
          % (len(cibles), len(non_portees)))
    touchees = set()
    lignes = []
    for n in sorted(non_portees):
        carriers = P.armed_carriers(n, masks)
        touchees.update(carriers)
        lignes.append((len(carriers), n, carriers))
    for cnt, n, carriers in sorted(lignes, key=lambda t: (-t[0], t[1])):
        arme = RULE_ROLE[n].armed_by
        bit = int(getattr(P.TR, n)) if hasattr(P.TR, n) else 0
        par_le_bit = sum(1 for _a, (r, _x) in masks.items() if bit and (r & bit))
        ecart = ""
        if cnt != par_le_bit:
            ecart = "   (compte par le BIT : %d -- FAUX, cf. l'armement)" % par_le_bit
        print("%-42s -> %3d ability(s) armee(s)%s" % (n, cnt, ecart))
        if arme is not None:
            print("      ARME PAR : %s" % arme)
        for aid in carriers[:12]:
            print("      %5d  %s  mask=0x%x" % (aid, masks[aid][1], masks[aid][0]))
        if len(carriers) > 12:
            print("      ... et %d autres" % (len(carriers) - 12))
    print("")
    print("abilities touchees par >= 1 regle CIBLE non portee : %d / %d" % (len(touchees), len(masks)))

    # --- ce que le perimetre historique de 13 regles ne voyait PAS ------------------------
    hors = sorted(n for n in non_portees if n not in PERIMETRE_HISTORIQUE_13)
    print("")
    print("regles CIBLE non portees INVISIBLES du perimetre historique (13 regles) : %d" % len(hors))
    if hors:
        print("  " + ", ".join(hors))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
