"""#963-r3 -- `LifewardsBondEffect$$CreateActiveCondition`, l'ARBRE.

MODULE SEPARE de `lifewards.py` pour la MEME raison MESUREE que
`instinctive_behaviour_condition.py` (dont il reprend le patron a l'identique) : l'arbre a besoin
d'`engine.entities.triggers`, qui tire `engine.services.movement_query`, qui tire
`engine.runner.components`, qui tire `engine.entities.effects` -- donc `factory`, donc la CLASSE
d'effet. Laisser l'arbre dans le module de la classe fermerait le cycle

    runner/components -> entities/effects/__init__ -> factory -> loki/lifewards
                      -> entities/triggers -> services/movement_query -> runner/components

La parade est la PREMIERE de la doctrine -- DEPLACER, pas differer : la classe d'effet reste dans
`lifewards.py` (elle ne lit qu'une CLE du `unit_state`), l'arbre vit ici, dans un module que la
cascade `factory` ne traverse PAS.

LE DECOMPILE, LU VERBATIM (build `t6dpr4k06g`) :

    IdunBattle.Entities.Effects.Loki.LifewardsBondEffect$$CreateActiveCondition =
        DSLTriggers$$IsAdjacent( Owner@<DSLSelectors+0x30>,
                                 DSLSelectors$$Parent( Owner@<DSLSelectors+0x30> ),
                                 UnitSelectionType.OnlyAliveAndTargetable = 3 )

Corps ENTIER, un seul appel apres la resolution du selecteur `Parent`.

⚠ **LE `3` N'EST PAS UN RAYON**, c'est le `selectionType` que `IsAdjacentAbilityTrigger$$ShouldTrigger`
passe aux DEUX `Select` (mesure #462-r4b-r1-r1-r1-r1-b : le ctor lu est
`(selector1, selector2, selectionType, query)`). Le lire comme une distance rendrait le gate
uniformement vrai.

⚠ **ET IL DIFFERE DE CELUI DU TRIGGER DE L'ABILITY**, qui vaut `0` (`UnitSelectionType.Any`) --
`LifewardsAbility$$CreateTrigger` porte `IsAdjacent(Owner@+0x30, Target@+0x60, 0)`. Les deux
arguments sont LUS, pas harmonises : `0` laisse passer une Celestine `Untargetable`, `3` non.
"""
from __future__ import annotations

from ....dsl.base import AbilityTrigger
from ...selectors.accessors import Owner
from ...selectors.tiles import Parent
from ...triggers import IsAdjacent
from ...unit_selection_type import UnitSelectionType

#: `IsAdjacent(..., 3)` -- le `selectionType` du call-site natif, PAS un rayon.
BOND_ADJACENCY_SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)


def lifewards_bond_active_condition() -> AbilityTrigger:
    """`LifewardsBondEffect$$CreateActiveCondition` -- ARBRE 1:1 (cf. l'en-tete du module)."""
    return IsAdjacent(Owner(), Parent(Owner()), BOND_ADJACENCY_SELECTION)


def evaluate_lifewards_bond_adjacent(state, unit_id: int) -> bool:
    """EVALUE l'arbre ci-dessus pour `unit_id`, dans un `AbilityEntities` ou `Owner == le porteur`.

    Point d'entree publie par `runner/components.py::UnitEffectStateView` sous la cle
    `lifewards_bond_adjacent_to_parent` (PARESSEUSE : rien n'est calcule tant qu'aucune instance de
    1060 ne la lit). Le detour par une cle plutot qu'un appel direct depuis `is_active` est la
    convention de TOUTES les `CreateActiveCondition` portees -- l'effet ne connait qu'un `Mapping`.

    `entities_from_state(state, owner_id, owner_id, owner_id=owner_id)` : c'est ce que fait
    `RefreshEffectsOperation$$ShouldBeActive`, qui ECRIT l'owner dans `ctx+0x18`.

    ⚠ `Parent(Owner)` rend `[]` pour toute unite du roster initial (`UnitComponent.parent_id` nul),
    et `IsAdjacentAbilityTrigger$$ShouldTrigger` rend FALSE sur un ensemble vide -- mirror exact.
    Une instance de 1060 posee sur une unite SANS parent est donc INERTE, cote natif comme ici."""
    from ....runner.abilities.behaviours.context import entities_from_state  # DIFFERE, PORTEUR :
    #     `runner.abilities.behaviours.context` importe `runner.components`, qui importe CE module
    #     (cle paresseuse). Hisser fermerait le cycle.
    ents = entities_from_state(state, int(unit_id), int(unit_id), owner_id=int(unit_id))
    return bool(lifewards_bond_active_condition().should_trigger(ents))
