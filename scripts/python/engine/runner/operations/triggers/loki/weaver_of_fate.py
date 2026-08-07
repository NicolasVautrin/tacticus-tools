"""WeaverOfFate (trait 1041 / triggered ability 1161, Abraxas thousInfernalMaster) — #202 tranche A.

Mirror du kit natif `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility` :

- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility$$CreateTrigger` (= `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility$$GetTrigger` parametre par l'effet) :
    On(9=Attack)
    & AmountIsEqualOrGreater(
        UnitsThatTakenDamageThisTurn(
            Enemies(<dsl>+0x30 = Owner, DSLSelectors$$AllUnits(), UnitSelectionType.Any = 0),
            profil 0xd=13 Psychic),
        Get(3))                                  # seuil 3 EN DUR (pas une variable de niveau)
  ⚠ La source est la primitive **pool 8** (`EntityPool.AllUnits`, MORTS INCLUS) et le
  `selectionType` vaut **0 = Any**, la ou tous les autres call-sites du jeu passent le champ
  partage `<dsl>+0x20` (`AllAliveUnits`) avec `3 = OnlyAliveAndTargetable`. Cf. `_enemies_of`
  ci-dessous (#514).
    & Not(HasEffect(caster, 0x4a1=1185 WeaverOfFate_MaxOutDamage))
  `On(9)` = event GENERIQUE de FIN d'attaque (`FinishAttackOperation IdunBattle.Operations.FinishAttackOperation$$Execute`), sans gate
  OwnerIsCaster/Target : le compte + le Not(HasEffect) sont les seuls gates.
- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility$$CreateBehaviour` : `AddEffect(1185, abilityStateRef, caster, Nullable(1))` —
  effet-marqueur pose sur SOI, duree 1 tour (« on that turn »).
- Selecteur `UnitsThatTakenDamageThisTurnSelector` (`IdunBattle.Entities.Formulas.UnitsThatTakenDamageThisTurnSelector$$Select`, IdunBattle.Entities.Formulas.UnitsThatTakenDamageThisTurnSelector$$.ctor) :
  garde les unites dont le Dictionary `receivedDamageThisTurn` (ActorStatisticsComponent @+0x80)
  CONTIENT la cle profil — seule la PRESENCE de la cle compte (le compte d'instances est ignore).
  Store ecrit par `IdunBattle.Operations.RegisterDamageOperation$$Execute` -> `IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterReceivedDamage` (TryAdd(profil,1) sinon +1), reset par-unite du joueur ENTRANT dans
  `IdunBattle.Operations.StartTurnOperation$$ResetUnit` -> `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetReceivedDamageThisTurn`.

Consommation de l'effet 1185 (face COMBAT) : `IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage`
(cf. `is_attack_max_out_damage` ci-dessous), appelee par `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$GetDamage` / `IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$GetDamage` (HitDamage construit (max, null)
-> AUCUN tirage) + la branche crit d'`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (base du crit = max), et cote
PREDICTION par `IdunBattle.Core.Services.DamagePrediction$$IsAttackMaxOutDamage` <- `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1b0a`.
"""
from __future__ import annotations

from typing import Optional

from .....entities.effect_type import EffectType
from .....entities.damage_profile_type import DamageProfileType
from .....dsl.event_trigger_type import EventTriggerType
from ....state import State
from ....components import UnitComponent, OwnerComponent
from ..base import TriggeredAbility, TriggerEvent
from ...effects import AddEffectOperation

WEAVER_MAXOUT = int(EffectType.WeaverOfFate_MaxOutDamage)      # 1185 (0x4a1)
_PSYCHIC = int(DamageProfileType.Psychic)                      # 13 (0xd) — arg du selecteur natif
_THRESHOLD = 3                                                 # DSLFactory.Get(3) — constante EN DUR
# 2e branche de `IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage` : `HasTriggeredAbility(unit, 0x5d6=1494
# ParagonSpear)` -> appel conditionnel INLINE (mange par ghidra). Porteur DISTINCT (hors kit
# Abraxas) — NON mirrore ici (residu case-202 §6 : a porter avec le kit ParagonSpear).


def units_that_taken_damage_this_turn(state: State, unit_ids, profile_id: int) -> list[int]:
    """Mirror `IdunBattle.Entities.Formulas.UnitsThatTakenDamageThisTurnSelector$$Select` : filtre `unit_ids` sur
    `ContainsKey(receivedDamageThisTurn, profile_id)` (presence de la CLE, compte ignore)."""
    out: list[int] = []
    for uid in unit_ids:
        e = state.get_entity(uid)
        uc = e.get_component(UnitComponent) if e is not None else None
        if uc is not None and profile_id in (uc.received_damage_this_turn or {}):
            out.append(uid)
    return out


def _enemies_of(state: State, owner_id: int) -> list[int]:
    """`Enemies( <dsl>+0x30 = Owner, DSLSelectors$$AllUnits(), UnitSelectionType.Any = 0 )` --
    unites d'une AUTRE equipe que le porteur, **MORTES COMPRISES**.

    ⚠ Le port filtrait `alive` jusqu'a #514, sur l'hypothese ecrite « les morts sont retires du
    board natif ». Le decompile la REFUTE sur les DEUX etages, et les deux vont dans le meme sens :

      * la SOURCE est `IdunBattleLogic.Entities.DSLSelectors$$AllUnits` ->
        `IdunBattle.Entities.Selectors.AllUnitsSelector$$Select` -> `IBattleQuery` slot 136
        `GetAllUnits` -> `IdunBattle.Core.Services.BattleQuery$$GetAllUnits` =
        `state.GetPool(EntityPool.AllUnits)`, sans aucun predicat de vie -- et non le champ partage
        `<dsl>+0x20` (`AllAliveUnitsSelector`, slot 137, `EntityPool.AliveUnits`) que prennent tous
        les autres `Enemies`/`Friends` du jeu ;
      * le `selectionType` passe ici est **`0 = UnitSelectionType.Any`**
        (`IdunBattle.Entities.Enum.UnitSelectionType` = `0=Any,1=OnlyAlive,2=OnlyTargetable,
        3=OnlyAliveAndTargetable`, et `IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType`
        n'appelle `IsAlive` que sur `1` et `3`). Or TOUS les autres call-sites passent `3`. Ce `0`
        est donc DELIBERE, et c'est le second signal independant.

    CE QUE CA CHANGE, ET POURQUOI C'EST OBSERVABLE : le gate est « au moins 3 ennemis ont recu du
    degat Psychic CE TOUR ». Un ennemi TUE par ce meme degat compte pour le natif ; il ne comptait
    pas pour le port, qui ratait donc le declenchement dans le regime le plus frequent (les 3 cibles
    d'une salve psychique dont une meurt). Degradation SILENCIEUSE et RESTRICTIVE.

    Le pool `EntityPool.AllUnits` contient bien les morts -- MESURE, pas deduit du nom :
    `probe_514_extra_pierce_cadavres.py` (regime `cadavre`) lit `UnitStats_ExtraPierce_Modification
    = 10` cote natif, soit `extraPierceRatio x 1`, avec pour seul allie « defeated » un cadavre."""
    ent = state.get_entity(owner_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    if oc is None:
        return []
    out: list[int] = []
    for uid, e in state.entities.items():
        if uid == owner_id:
            continue
        oc2 = e.get_component(OwnerComponent)
        if oc2 is None or oc2.team == oc.team:
            continue
        if e.get_component(UnitComponent) is None:
            continue                       # `TargetsSelector$$SelectUnit` : seules les UNITES
        out.append(uid)
    return out


class WeaverOfFateAbility(TriggeredAbility):
    """`WeaverOfFateAbility` (triggered 1161) — cf. en-tete de module pour l'arbre natif."""
    event_id = int(EventTriggerType.Attack)        # On(9) — fin de CHAQUE attaque (normale ET ability)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # Not(HasEffect(caster, 1185)) — anti re-trigger tant que l'effet du tour est pose.
        if state.effects is not None and state.effects.has_effect(
                self.owner_id, effect_type=WEAVER_MAXOUT):
            return False
        enemies = _enemies_of(state, self.owner_id)
        hit = units_that_taken_damage_this_turn(state, enemies, _PSYCHIC)
        return len(hit) >= _THRESHOLD                          # AmountIsEqualOrGreater(..., Get(3))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        eff = AddEffectOperation.execute(
            state, self.owner_id, self.owner_id, WEAVER_MAXOUT,
            name="WeaverOfFate_MaxOutDamage",
            duration_override=1)   # Nullable(1) natif (IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility$$CreateBehaviour) = 1 TOUR, PAS TurnsFromRounds -> pas de conversion (#98)
        if eff is None:
            return None
        return {"type": "weaver_of_fate_maxout", "unit": int(self.owner_id)}


def is_attack_max_out_damage(state: State, attacker_id: int) -> bool:
    """Mirror `IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage` (branche effet) :
    `IsOwnerOfEffect(unit, 1185) || IsTargetOfEffect(unit, 1185)` — offline les deux roles
    coincident (effet self-cast stocke par-porteur dans EffectsState.by_unit) -> presence de
    l'effet 1185 ACTIF sur l'attaquant. La branche `HasTriggeredAbility(1494 ParagonSpear)`
    n'est PAS mirroree (porteur hors kit — residu case-202 §6)."""
    if state.effects is None:
        return False
    return bool(state.effects.has_effect(attacker_id, effect_type=WEAVER_MAXOUT))
