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
from .....entities.effects.loki import close_combat_weakness as _ccw_effect
from .....dsl.event_trigger_type import EventTriggerType
from ..base import EffectTrigger, TriggerEvent
from ...effects import AddEffectOperation

#: l'effet PORTEUR du trigger (celui qui porte `CreateTargetTrigger`).
CLOSE_COMBAT_WEAKNESS_REDUCE_DMG = int(EffectType.CloseCombatWeakness_ReduceDmg)          # 0x46a
#: le MARQUEUR d'un tour que son behaviour pose.
CLOSE_COMBAT_WEAKNESS_STARTED_TURN = int(
    EffectType.CloseCombatWeakness_StartedTurnAdjacentToEnemy)                            # 0x469


def _owner_active_effect_names(state: State, unit_id: int) -> frozenset:
    """`HasEffect(<selecteur>, <EffectType>, onlyActive: TRUE, targetType: 6)` cote port.

    `onlyActive` se lit sur `EffectsState.active_effects`, qui conjugue le FLAG
    `EffectComponent.IsActive @+0x5c` et la `CreateActiveCondition` -- exactement les deux
    conjoints natifs, et la MEME lecture que
    `triggers/loki/reactivate_overwatch.py::AReactivateOverwatchHitReductionPurge.matches`.

    C'est le substrat qu'attend `CloseCombatWeaknessReduceDmgEffect.nearby_enemies_condition`
    (`att_ctx["owner_effect_names"]`) : sur ce canal, le selecteur `Owner@DSLSelectors+0x30` des
    deux `HasEffect` de la condition designe le PORTEUR du trigger."""
    eff = getattr(state, "effects", None)
    if eff is None:
        return frozenset()
    from ....components import unit_state_for_effects   # DIFFERE: cf. `matches` ci-dessous
    return frozenset(e.name for e in eff.active_effects(
        int(unit_id), unit_state_for_effects(state, int(unit_id))) if e.name)


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

    def _instance_is_active(self, state: State, adjacent_enemies) -> bool:
        """GATE `EffectComponent.IsActive @+0x5c` du rail TARGETS (#1074).

        Ce trigger vient de `IdunBattle.Entities.Effects.Loki.CloseCombatWeakness_ReduceDmg_Effect$$
        CreateTargetTrigger` (corps RELU, build `rnca9r7q6c`), donc il est evalue par
        `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets`, qui teste
        `IsActive` PAR CIBLE -- sur l'`EffectComponent` RE-FETCH depuis l'entite-effet -- AVANT
        `ShouldTrigger`.

        ⚠ POUR CET EFFET, LE FLAG CAPTE NE REPOND PAS : `CloseCombatWeaknessReduceDmgEffect`
        porte `active_condition_ported = True` parce que le natif REECRIT `+0x5c` a chaque refresh
        depuis `$$CreateActiveCondition`, dont le corps ENTIER est `return NearbyEnemiesCondition()`.
        Le mirror du gate est donc la CONDITION elle-meme, evaluee par le FOYER UNIQUE de la classe
        d'effet -- lire `e.active` ici recopierait un flag PERIME (position REELLE au moment de la
        capture), exactement ce que `case-322` proscrit.

        CE QUE LE GATE AJOUTE, et il n'y a qu'un terme : le trigger exige deja
        `HasAdjacentEnemies(Owner, Tiles(Owner)) >= 1`, ce qui satisfait la DISJONCTION de la
        condition (`HasAdjacentEnemies | HasEffect(1129)`). Le terme NEUF est donc le conjoint
        gauche -- `NOT HasEffect(Owner, 0x478 = SuppressCloseCombatWeakness, onlyActive: true, 6)`.
        Sans lui, un porteur sous `EarlyWarningOverride` se posait quand meme le marqueur 1129 pour
        un tour : le malus repartait alors au tour suivant, apres l'expiration de la suppression, la
        ou le natif ne l'avait jamais arme.

        TRI-ETAT conserve : `nearby_enemies_condition` rend `None` quand un terme n'est pas mesure
        -> on NE FERME PAS (degradation PERMISSIVE, la meme que celle du canal magnitude).
        Aucune instance 1130 portee -> `True` : sans instance il n'y aurait aucun trigger a evaluer
        (meme forme que `HarlequinsPanoplyIgnoreHitsRemove._instance_is_active`).

        CONFRONTABILITE DU REGIME -- MESUREE, et le gate n'est PAS theorique. Croisement du
        gameconfig (trait `CloseCombatWeakness` x ability `EarlyWarningOverride`, seule poseuse de
        `1144` et sur `Owner@0x148`, donc sur ELLE-MEME) : **quatre** unites portent les DEUX --
        `tauBossCrisis`, `tauBossCrisisInc`, `tauBossCrisisLHE`, `tauNpcCrisis`, toutes `npc`. Et le
        porteur LINEUP `tauCrisis` a deja l'ability : il ne lui manque que le trait, que
        `rl_duel build --unit-stat "tauCrisis:Traits=[...]"` force (voie deja etablie par #1015-r1).
        Le montage live est donc : `tauCrisis` au pool avec le trait force, un ennemi amene AU
        CONTACT, cast d'`EarlyWarningOverride`, puis lecture de `decisionView.effects` au debut du
        tour suivant -- `1129` doit etre ABSENT. **NON CONFRONTE LIVE a ce jour** (#1074) : la
        branche est mirroree et confrontee OFFLINE (`test_1015r1_..._offline.py` section 6)."""
        eff = getattr(state, "effects", None)
        if eff is None:
            return True
        insts = [e for e in (eff.by_unit.get(int(self.owner_id)) or [])
                 if (not e.consumed) and int(e.effect_type) == int(self.effect_type)
                 and isinstance(e, _ccw_effect.CloseCombatWeaknessReduceDmgEffect)]
        if not insts:
            return True
        ctx = {_ccw_effect.CTX_ADJACENT_ENEMIES: adjacent_enemies,
               "owner_effect_names": _owner_active_effect_names(state, self.owner_id)}
        return any(i.nearby_enemies_condition(ctx) is not False for i in insts)

    def matches(self, state: State, ev: "TriggerEvent") -> bool:
        """Le natif teste `IsActive` AVANT `ShouldTrigger` ; ici le terme geometrique est evalue
        d'abord parce que le gate en CONSOMME le compteur (`HasAdjacentEnemies(Caster, CasterTile)`
        de la condition, MEME arbre). Le verdict est une CONJONCTION, donc l'ordre ne le change
        pas -- et calculer l'arbre deux fois serait le seul autre choix."""
        from ....components import close_combat_weakness_adjacent_enemies_count
        n = close_combat_weakness_adjacent_enemies_count(state, self.owner_id)
        if n is None or int(n) < 1:                 # AmountIsEqualOrGreater(<ennemis>, Direct(1))
            return False
        return self._instance_is_active(state, int(n))

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
