"""#1015-r1 -- `InstinctiveBehaviourBlockMovementEffect$$CreateActiveCondition`, l'ARBRE.

POURQUOI CE MODULE EST SEPARE DE `instinctive_behaviour.py`, ET C'EST MESURE (pas un gout).
L'arbre a besoin d'`engine.entities.triggers`, qui importe `engine.services.movement_query`, qui
importe `engine.runner.components`, qui importe `engine.entities.effects` (donc `factory`, donc la
CLASSE d'effet). Laisser l'arbre dans le module de la classe fermait donc le cycle

    runner/components -> entities/effects/__init__ -> factory -> loki/instinctive_behaviour
                      -> entities/triggers -> services/movement_query -> runner/components

et faisait echouer l'import de `engine.runner.components` avec un `ImportError` sur
`OwnerComponent` (mesure : `probe_313` etape 5 ROUGE sur `ABILITY_TRIGGERS`, et
`import engine.runner.operations.triggers.dispatch.registry` en echec SEUL).

La parade est la PREMIERE de la doctrine -- **DEPLACER**, pas differer : la classe d'effet reste
dans `instinctive_behaviour.py` (elle ne lit qu'une CLE du `unit_state`, donc elle n'a besoin
d'aucun noeud DSL), et l'arbre vit ici, dans un module que la cascade `factory` ne traverse PAS.
Son unique lecteur (`runner/components.py::UnitEffectStateView.__getitem__`) l'importe au moment
ou une instance de 1235 demande la cle -- un import PARESSEUX de fonction, pas un differe pour
cacher un cycle : la cascade n'a simplement plus d'arete a fermer.

Le decompile op par op, la lecture de `<DSLTriggers+0x28>`, la non-collapsabilite des deux `Any`
et le piege `as_ids` sont documentes en tete d'`instinctive_behaviour.py`.
"""
from __future__ import annotations

from ....dsl.base import AbilityTrigger
from ...selectors.accessors import ActiveTarget, Owner
from ...selectors.units import ForcedAttackTargets, Tiles
from ...triggers import (AmountIsGreaterThanZero, Any, IsInAttackOrAbilityRange, IsTurnOf,
                         IsWalkable, TriggerAnd)


def block_movement_active_condition() -> AbilityTrigger:
    """`IdunBattle.Entities.Effects.Loki.InstinctiveBehaviourBlockMovementEffect$$
    CreateActiveCondition` -- ARBRE 1:1 :

        fat = DSLSelectors$$ForcedAttackTargets( Owner@<DSLSelectors+0x30> )
        c1  = DSLTriggers$$AmountIsGreaterThanZero( fat )
        c2  = DSLTriggers$$Any( fat, DSLTriggers$$IsInAttackOrAbilityRange(
                                         Owner@+0x30, <DSLSelectors+0x68> ) )
        c3  = DSLTriggers$$Any( DSLSelectors$$Tiles(Owner@+0x30),
                                DSLTriggers$$IsWalkable( <DSLSelectors+0x68> ) )
        return ( <DSLTriggers+0x28> op_BitwiseAnd c3 ) op_BitwiseAnd ( c1 op_BitwiseAnd c2 )

    L'ORDRE des `op_BitwiseAnd` est celui du natif. Les quatre conjoints sont des predicats PURS,
    donc la conjonction commute et le VERDICT n'en depend pas ; c'est la STRUCTURE qu'on
    transcrit."""
    c1 = AmountIsGreaterThanZero(ForcedAttackTargets(Owner()))
    # `Any(fat, IsInAttackOrAbilityRange(Owner@+0x30, <DSLSelectors+0x68>))` -- l'ELEMENT courant
    # est le slot `ActiveTarget` (`AbilityEntities$$.ctor(base, selected)`), cf. le noeud `Any`.
    c2 = Any(ForcedAttackTargets(Owner()),
             IsInAttackOrAbilityRange(Owner(), ActiveTarget()))
    x = TriggerAnd(c1, c2)
    # `Any(Tiles(Owner@+0x30), IsWalkable(<DSLSelectors+0x68>))` -- domaine ID DE TUILE
    # (`board.walkable(tid)`), d'ou `as_ids=True` : sans lui le gate serait FAUX en silence.
    c3 = Any(Tiles(Owner(), as_ids=True), IsWalkable(ActiveTarget()))
    y = TriggerAnd(IsTurnOf(Owner()), c3)                 # `<DSLTriggers+0x28> & c3`
    return TriggerAnd(y, x)


def evaluate_block_movement(state, unit_id: int) -> bool:
    """EVALUE l'arbre ci-dessus pour `unit_id`, dans un `AbilityEntities` ou `Owner == le porteur`.

    C'est le point d'entree que `runner/components.py::UnitEffectStateView` publie sous la cle
    `instinctive_behaviour_block_movement` (PARESSEUSE : rien n'est calcule tant qu'aucune instance
    de 1235 ne la lit). Le detour par une cle plutot qu'un appel direct depuis `is_active` est la
    convention de TOUTES les `CreateActiveCondition` portees -- l'effet ne connait qu'un `Mapping`.

    `entities_from_state(state, owner_id, owner_id, owner_id=owner_id)` : sur une triggered-ability
    le natif pose `Owner == Caster == le porteur` (`BaseTriggeredAbility$$Execute`), et c'est aussi
    ce que fait `RefreshEffectsOperation$$ShouldBeActive`, qui ECRIT l'owner dans `ctx+0x18` --
    l'un des QUATRE champs qu'il renseigne pour evaluer une `CreateActiveCondition`."""
    from ....runner.abilities.behaviours.context import entities_from_state  # DIFFERE, PORTEUR :
    #     `runner.abilities.behaviours.context` importe `runner.components`, qui importe CE module
    #     (cle paresseuse). Hisser fermerait le cycle.
    ents = entities_from_state(state, int(unit_id), int(unit_id), owner_id=int(unit_id))
    return bool(block_movement_active_condition().should_trigger(ents))
