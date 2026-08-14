"""`CloseCombatWeakness_ReduceDmg` (1130) -- son couple `CreateTargetTrigger` /
`CreateTargetTriggerBehaviour`, c'est-a-dire le MARQUEUR de debut de tour. #1015-r1.

MIRROR 1:1, noeud par noeud :

    `IdunBattle.Entities.Effects.Loki.CloseCombatWeakness_ReduceDmg_Effect$$CreateTargetTrigger` =
        op_BitwiseAnd( On(0x12 = EventTriggerType.TurnStart_EffectActivation, ownerNeedsToBeAlive: true),
                       HasAdjacentEnemies(unit = Owner@DSLSelectors+0x30,
                                          unitTile = Tiles(Owner@+0x30),
                                          includeObjects: false, includeSteppables: false) )

    `...$$CreateTargetTriggerBehaviour` =
        AddEffect( 0x469 = 1129 `EffectType.CloseCombatWeakness_StartedTurnAdjacentToEnemy`,
                   abilityState = Direct(GetAbilityStateReference(this)),
                   source  = Owner@+0x30,
                   targets = Owner@+0x30,
                   turns   = <DSLFormulas+0x20> = **Direct(1)** )

⚠ `turns` est `Direct(1)` -- UN TOUR SEC, et **pas** `TurnsFromRounds(1)` : la table de constantes de
`IdunBattleLogic.Entities.DSLFormulas$$.ctor` pose `+0x18 = Direct(0)`, `+0x20 = Direct(1)`,
`+0x28 = Direct(2)`, `+0x30 = Direct(100)`, `+0x38 = Direct(-1)`, et c'est le slot `+0x20` qui est
passe. Confondre les deux doublerait la duree dans un duel a deux joueurs (le piege exact de #98 sur
`Contaminated`).

⚠ Le trigger n'est PAS gate `IsTurnOf(Owner)` : `On(0x12, true)` tire a CHAQUE debut de tour, donc
aussi au tour ADVERSE. C'est ce que dit le decompile (aucun `IsTurnOf` dans la conjonction), et c'est
coherent avec la formulation i2 (« started the turn adjacent »), le marqueur etant de toute facon
re-pose tant que le contact dure.

A QUOI IL SERT : `...$$NearbyEnemiesCondition` lit `HasEffect(Owner@+0x30, 0x469)` en DISJONCTION du
terme geometrique. Sans ce marqueur, un porteur qui COMMENCE son tour au contact puis se DESENGAGE
perdrait le malus alors que le natif le garde -- une divergence PERMISSIVE (le port surestimerait ses
degats) sur exactement le geste qu'une unite T'AU fait le plus souvent.

ASCII only (cp1252).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from .....entities.effect_type import EffectType
from .....dsl.event_trigger_type import EventTriggerType
from ..base import EffectTrigger, TriggerEvent
from ...effects import AddEffectOperation

#: l'effet PORTEUR du trigger (celui qui porte `CreateTargetTrigger`).
CLOSE_COMBAT_WEAKNESS_REDUCE_DMG = int(EffectType.CloseCombatWeakness_ReduceDmg)          # 0x46a
#: le MARQUEUR d'un tour que son behaviour pose.
CLOSE_COMBAT_WEAKNESS_STARTED_TURN = int(
    EffectType.CloseCombatWeakness_StartedTurnAdjacentToEnemy)                            # 0x469


class CloseCombatWeaknessMarkStartedTurnAdjacent(EffectTrigger):
    """`On(0x12) & HasAdjacentEnemies(Owner, Tiles(Owner))` -> `AddEffect(1129, Owner, turns = 1)`.

    `matches` reutilise le FOYER UNIQUE du terme geometrique
    (`runner.components.close_combat_weakness_adjacent_enemies_count`, qui execute l'arbre
    `entities/effects/loki/close_combat_weakness.py::has_adjacent_enemies_selector`) : le natif
    appelle le MEME `HasAdjacentEnemies` ici et dans `NearbyEnemiesCondition`, seuls les deux
    selecteurs d'entree changent (`Owner`/`Tiles(Owner)` ici, `Caster`/`CasterTile` la-bas), et sur
    ce canal les deux designent la MEME unite : le porteur.

    `None` (porteur sans equipe ni tuile) -> le trigger ne tire pas : degradation RESTRICTIVE, jamais
    un marqueur pose sur une inconnue."""
    event_id = EventTriggerType.TurnStart_EffectActivation
    effect_type = CLOSE_COMBAT_WEAKNESS_REDUCE_DMG

    def matches(self, state: State, ev: "TriggerEvent") -> bool:
        from ....components import close_combat_weakness_adjacent_enemies_count
        n = close_combat_weakness_adjacent_enemies_count(state, self.owner_id)
        return n is not None and int(n) >= 1        # AmountIsEqualOrGreater(<ennemis>, Direct(1))

    def execute_behaviour(self, state: State, ev: "TriggerEvent") -> Optional[dict]:
        eff = AddEffectOperation.execute(
            state, source=self.owner_id, target=self.owner_id,
            effect_type=CLOSE_COMBAT_WEAKNESS_STARTED_TURN,
            name=EffectType.CloseCombatWeakness_StartedTurnAdjacentToEnemy.name,
            duration_override=1)                    # turns = <DSLFormulas+0x20> = Direct(1)
        if eff is None:
            return None                             # gate natif « meme type deja present » -> no-op
        return {"effect": EffectType.CloseCombatWeakness_ReduceDmg.name,
                "owner": self.owner_id,
                "applied": EffectType.CloseCombatWeakness_StartedTurnAdjacentToEnemy.name}
