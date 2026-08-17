"""HP-floor `HypersensoryAbilities_MinimalHealthEffect` — Apply/Revert IMPÉRATIFS + driver de ré-évaluation
de l'ActiveCondition (gqfc5mff6c). G6a du chantier Genestealer Cults (passif Judh).

Frontière déclaratif/impératif (doctrine #149) : la FORMULE du plancher + le pct config + la condition DSL
`IsEnemyTurn & Not(HasBeenAttackedAmountThisTurn>=1)` vivent sur la CLASSE d'effet
(`HypersensoryMinimalHealthEffect`, entities/effects/loki.py) ; ici = l'OPÉRATION ECS (mute
`HealthComponent.minimal_health`) + le DRIVER qui ré-évalue la condition aux transitions et appelle
Apply/Revert. Le clamp effectif du dégât est dans `HealthComponent.reduce` (mirror `IdunBattle.Entities.Components.FillUpStatComponent$$Reduce`).

Chaîne native RE'd (VA citées) :

    IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility$$CreateBehaviour   AddEffect(0x564=1380, owner) [self, init passif]
    IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$CreateActiveCondition   And(IsEnemyTurn(owner),
                                                                   Not(HasBeenAttackedAmountThisTurn(owner)>=1))
    IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$ApplyInternal   MinimalHealth@+0x1c = Min(Round(hp x hpPct/100), hp-1)
    IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$RevertInternal   MinimalHealth@+0x1c = null
    (compteur) IdunBattleLogic.Entities.DSLTriggers$$HasBeenAttackedAmountThisTurnIsEqualOrGreater  (source @+0x34)

Le natif ré-évalue la condition via le framework d'effet (Apply au FALSE->TRUE, Revert au TRUE->FALSE) ; les
DEUX transitions fonctionnellement nécessaires = (1) début de tour (IsEnemyTurn bascule + reset du compteur)
et (2) après une attaque reçue (compteur -> >=1). Le port les pose explicitement (`evaluate_minimal_health`
au turn-start, `record_attacked` après chaque attaque encaissée).
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import UnitComponent, OwnerComponent, HealthComponent
from ...entities.effects.loki.status import HypersensoryMinimalHealthEffect
from ...entities.effect_type import EffectType

# Flag once/turn du passif (G6b) : `HypersensoryAbilities_HasBeenAttacked` (0x57f=1407), posé par
# MoveAndSpawnDecoy après sa réaction. Retiré au début de CHAQUE tour (comme le compteur) -> la réaction
# se ré-arme « the first time EACH enemy turn ». Cf. operations/triggers/genestealer.py (G6b).
HYPERSENSORY_HASBEENATTACKED = int(EffectType.HypersensoryAbilities_HasBeenAttacked)   # 1407 (0x57f)


def _minimal_health_effect(state: State, unit_id: int) -> Optional[HypersensoryMinimalHealthEffect]:
    """L'instance (non consommée) du HP-floor Hypersensory portée par l'unité, ou None. (Une seule par unité
    — effet self-posé à l'init de l'ability passive.)"""
    if state.effects is None:
        return None
    for e in state.effects.by_unit.get(int(unit_id), []):
        if isinstance(e, HypersensoryMinimalHealthEffect) and not e.consumed:
            return e
    return None


class MinimalHealthEffectOperation:
    """`HypersensoryAbilities_MinimalHealthEffect` Apply/Revert (IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$ApplyInternal / IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$RevertInternal) — mute
    `HealthComponent.minimal_health`. Feuille IMPÉRATIVE appelée par le driver `evaluate_minimal_health`."""
    __slots__ = ()

    @staticmethod
    def apply(state: State, unit_id: int, eff: HypersensoryMinimalHealthEffect) -> Optional[int]:
        """`IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$ApplyInternal : `MinimalHealth = Min(Round(hp x hpPct/100), hp-1)` (snapshot du HP
        courant). No-op (None) si pas de HealthComponent / hp non capté / pct absent. Renvoie le plancher posé."""
        ent = state.get_entity(unit_id)
        hc = ent.get_component(HealthComponent) if ent is not None else None
        if hc is None or hc.hp is None:
            return None
        floor = eff.compute_floor(hc.hp)
        if floor is None:
            return None
        hc.minimal_health = int(floor)
        return int(floor)

    @staticmethod
    def revert(state: State, unit_id: int) -> None:
        """`IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$RevertInternal : `MinimalHealth = null` (efface le plancher). No-op si pas de
        HealthComponent."""
        ent = state.get_entity(unit_id)
        hc = ent.get_component(HealthComponent) if ent is not None else None
        if hc is not None:
            hc.minimal_health = None


def reset_times_attacked(state: State) -> None:
    """Nouveau tour -> remet `times_attacked_this_turn` à 0 pour TOUTES les unités (le compteur natif
    `HasBeenAttackedAmountThisTurn` est per-tour). Appelé par `start_turn_triggers`.

    #G6b : retire aussi le flag once/turn `HypersensoryAbilities_HasBeenAttacked` (0x57f=1407) posé par
    MoveAndSpawnDecoy -> la réaction de Judh se ré-arme à chaque tour (« the first time EACH enemy turn »).
    Retrait = `consumed=True` (has_effect ignore les consommés). Sûr même si l'effet expire aussi via son
    timer (`on_turn_end`) : idempotent."""
    for e in state.entities.values():
        uc = e.get_component(UnitComponent)
        if uc is not None:
            uc.times_attacked_this_turn = 0
    if state.effects is not None:
        for effs in state.effects.by_unit.values():
            for ef in effs:
                if not ef.consumed and ef.effect_type == HYPERSENSORY_HASBEENATTACKED:
                    ef.consumed = True


def evaluate_minimal_health(state: State, player_id: Optional[int]) -> list:
    """Driver de ré-évaluation de l'ActiveCondition du HP-floor au DÉBUT DE TOUR (mirror du framework d'effet
    évaluant `IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$CreateActiveCondition). Pour chaque porteur du HP-floor : si `IsEnemyTurn(owner)`
    (le player entrant N'EST PAS celui du porteur) ET pas encore attaqué ce tour (compteur remis à 0 juste
    avant) -> `Apply` (snapshot du plancher = pct% du HP courant) ; sinon -> `Revert` (efface). Renvoie la
    liste des {unit, floor} posés (diagnostic)."""
    if state.effects is None:
        return []
    out: list = []
    for uid in list(state.effects.by_unit.keys()):
        eff = _minimal_health_effect(state, uid)
        if eff is None:
            continue
        ent = state.get_entity(uid)
        oc = ent.get_component(OwnerComponent) if ent is not None else None
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if oc is None or uc is None or not uc.alive:
            MinimalHealthEffectOperation.revert(state, uid)
            continue
        is_enemy_turn = (player_id is not None and oc.player is not None
                         and int(player_id) != int(oc.player))
        already_attacked = uc.times_attacked_this_turn >= 1
        if is_enemy_turn and not already_attacked:
            floor = MinimalHealthEffectOperation.apply(state, uid, eff)
            if floor is not None:
                out.append({"unit": int(uid), "floor": floor})
        else:
            MinimalHealthEffectOperation.revert(state, uid)
    return out


def record_attacked(state: State, target_id: int) -> None:
    """La cible vient d'encaisser une ATTAQUE (pas un DoT) -> mirror de
    `IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterAttackReceived`, qui incrémente
    les DEUX compteurs D'UN SEUL GESTE (`*(int*)(this+0x34) += 1 ; *(int*)(this+0x38) += 1`, LU ;
    le 3e bump `+0x3c` est gaté par `totalCrits > 0` et n'a aucun lecteur porté) :
      * `times_attacked_this_turn` (@+0x38) — per-tour, remis à 0 par `reset_times_attacked` ;
      * `total_times_attacked` (@+0x34) — TOTAL DE LA BATAILLE, jamais remis à 0 (aucun `Reset*` du
        composant natif ne l'écrit) ; lu par `TotalTimesAttackedFormula`.
    Puis ré-évalue l'ActiveCondition du HP-floor : `HasBeenAttacked>=1` rend `Not(...)` faux ->
    `RevertInternal` efface le plancher (le coup SUIVANT du tour peut tuer). No-op sur une unité sans
    HP-floor (mais les compteurs sont incrémentés quand même — ils servent aussi au trigger
    MoveAndSpawnDecoy (G6b) et au snowball de coups de `BloodyFury`)."""
    ent = state.get_entity(target_id)
    uc = ent.get_component(UnitComponent) if ent is not None else None
    if uc is None:
        return
    uc.times_attacked_this_turn += 1
    uc.total_times_attacked += 1
    if _minimal_health_effect(state, target_id) is not None:
        MinimalHealthEffectOperation.revert(state, target_id)
