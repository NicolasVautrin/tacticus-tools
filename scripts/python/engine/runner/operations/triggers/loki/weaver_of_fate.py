"""WeaverOfFate (trait 1041 / triggered ability 1161, Abraxas thousInfernalMaster) — #202 tranche A.

Mirror du kit natif `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility` :

- `CreateTrigger @1811acc50` (= `GetTrigger @1811acd60` parametre par l'effet) :
    On(9=Attack)
    & AmountIsEqualOrGreater(
        UnitsThatTakenDamageThisTurn(Enemies(caster, AllUnits), profil 0xd=13 Psychic),
        Get(3))                                  # seuil 3 EN DUR (pas une variable de niveau)
    & Not(HasEffect(caster, 0x4a1=1185 WeaverOfFate_MaxOutDamage))
  `On(9)` = event GENERIQUE de FIN d'attaque (`FinishAttackOperation @180e71310`), sans gate
  OwnerIsCaster/Target : le compte + le Not(HasEffect) sont les seuls gates.
- `CreateBehaviour @1811acb90` : `AddEffect(1185, abilityStateRef, caster, Nullable(1))` —
  effet-marqueur pose sur SOI, duree 1 tour (« on that turn »).
- Selecteur `UnitsThatTakenDamageThisTurnSelector` (`Select @180f2e230`, ctor @180f2e580) :
  garde les unites dont le Dictionary `receivedDamageThisTurn` (ActorStatisticsComponent @+0x80)
  CONTIENT la cle profil — seule la PRESENCE de la cle compte (le compte d'instances est ignore).
  Store ecrit par `RegisterDamageOperation.Execute @180e86de0` -> `RegisterReceivedDamage
  @180f922c0` (TryAdd(profil,1) sinon +1), reset par-unite du joueur ENTRANT dans
  `StartTurnOperation.ResetUnit @180ea5a10` -> `ResetReceivedDamageThisTurn @180f923c0`.

Consommation de l'effet 1185 (face COMBAT) : `UnitExtensions.IsAttackMaxOutDamage @180ed7a50`
(cf. `is_attack_max_out_damage` ci-dessous), appelee par `AttackDamageBehaviour.GetDamage
@180fbb250` / `AbilityDamageBehaviour.GetDamage @180f8c560` (HitDamage construit (max, null)
-> AUCUN tirage) + la branche crit d'`ExecuteHit @180e5eff0` (base du crit = max), et cote
PREDICTION par `DamagePrediction.IsAttackMaxOutDamage @1810329f0` <- `PredictAttackRaw @181034aba`.
"""
from __future__ import annotations

from typing import Optional

from .....entities.effect_type import EffectType
from .....entities.damage_profile_type import DamageProfileType
from .....dsl.event_trigger_type import EventTriggerType
from ....state import State
from ....components import UnitComponent, OwnerComponent
from ..base import TriggeredAbility, TriggerEvent

WEAVER_MAXOUT = int(EffectType.WeaverOfFate_MaxOutDamage)      # 1185 (0x4a1)
_PSYCHIC = int(DamageProfileType.Psychic)                      # 13 (0xd) — arg du selecteur natif
_THRESHOLD = 3                                                 # DSLFactory.Get(3) — constante EN DUR
# 2e branche de `IsAttackMaxOutDamage @180ed7a50` : `HasTriggeredAbility(unit, 0x5d6=1494
# ParagonSpear)` -> appel conditionnel INLINE (mange par ghidra). Porteur DISTINCT (hors kit
# Abraxas) — NON mirrore ici (residu case-202 §6 : a porter avec le kit ParagonSpear).


def units_that_taken_damage_this_turn(state: State, unit_ids, profile_id: int) -> list[int]:
    """Mirror `UnitsThatTakenDamageThisTurnSelector.Select @180f2e230` : filtre `unit_ids` sur
    `ContainsKey(receivedDamageThisTurn, profile_id)` (presence de la CLE, compte ignore)."""
    out: list[int] = []
    for uid in unit_ids:
        e = state.get_entity(uid)
        uc = e.get_component(UnitComponent) if e is not None else None
        if uc is not None and profile_id in (uc.received_damage_this_turn or {}):
            out.append(uid)
    return out


def _alive_enemies_of(state: State, owner_id: int) -> list[int]:
    """`Enemies(caster, AllUnits)` : unites VIVANTES d'une AUTRE equipe que le porteur (les morts
    sont retires du board natif — `AllUnits` n'itere que les listes `units` des PlayerComponent,
    purgees par RemoveUnitOperation @180e8add0)."""
    ent = state.get_entity(owner_id)
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    if oc is None:
        return []
    out: list[int] = []
    for uid, e in state.entities.items():
        if uid == owner_id:
            continue
        oc2 = e.get_component(OwnerComponent)
        uc2 = e.get_component(UnitComponent)
        if oc2 is None or oc2.team == oc.team:
            continue
        if uc2 is not None and not uc2.alive:
            continue
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
        enemies = _alive_enemies_of(state, self.owner_id)
        hit = units_that_taken_damage_this_turn(state, enemies, _PSYCHIC)
        return len(hit) >= _THRESHOLD                          # AmountIsEqualOrGreater(..., Get(3))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        from ...effects import AddEffectOperation              # lazy : cycle triggers<->operations
        eff = AddEffectOperation.execute(
            state, self.owner_id, self.owner_id, WEAVER_MAXOUT,
            name="WeaverOfFate_MaxOutDamage",
            duration_override=1)   # Nullable(1) natif (@1811acb90) = 1 TOUR, PAS TurnsFromRounds -> pas de conversion (#98)
        if eff is None:
            return None
        return {"type": "weaver_of_fate_maxout", "unit": int(self.owner_id)}


def is_attack_max_out_damage(state: State, attacker_id: int) -> bool:
    """Mirror `UnitExtensions.IsAttackMaxOutDamage @180ed7a50` (branche effet) :
    `IsOwnerOfEffect(unit, 1185) || IsTargetOfEffect(unit, 1185)` — offline les deux roles
    coincident (effet self-cast stocke par-porteur dans EffectsState.by_unit) -> presence de
    l'effet 1185 ACTIF sur l'attaquant. La branche `HasTriggeredAbility(1494 ParagonSpear)`
    n'est PAS mirroree (porteur hors kit — residu case-202 §6)."""
    if state.effects is None:
        return False
    return bool(state.effects.has_effect(attacker_id, effect_type=WEAVER_MAXOUT))
