"""`RealityUnbound` (`TriggeredAbilityType.RealityUnbound` = 1174) — passif de `thousTzaangor`
« Yazaghor » (HERO Thousand Sons, present dans `rl_duel.py build --list-pool` rank 17).

i2 (autoritatif) : « For each different enemy unit that was dealt Psychic Damage this turn Yazaghor
deals **+181 Maximum Damage** with his normal **ranged** attacks. If **three or more** different
enemy units have been dealt Psychic Damage this turn he gains **+1 Movement** and his normal ranged
attack gets **+1 Range** until the end of this turn. »

DEUX classes natives, DEUX events, DEUX volets — le passif accorde les deux.

## Volet A — Movement + Range (`RealityUnboundAbility`)

- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RealityUnboundAbility$$CreateTrigger` n'a PAS de
  corps propre : c'est un **fold ICF** (absent de la table de fonctions ghidra ; les octets a son RVA
  sont `mov rcx,[this+0x28] ; xor r8d,r8d ; mov edx,0x4b5 ; jmp <cible>`) dont la cible est
  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility$$GetTrigger` — un trigger
  GENERIQUE parametre par un `EffectType`. **Ne pas se fier au nom** : ce n'est pas une parente avec
  WeaverOfFate, c'est le meme corps partage. Arbre (lu) :

      On(9 = Attack, subject=1)
      & AmountIsEqualOrGreater(
            UnitsThatTakenDamageThisTurn( Enemies(self@0x148, AllUnits), 0xd = Psychic ),
            Get(3) )                                  # seuil 3 EN DUR (pas une variable de niveau)
      & Not( HasEffect(self@0x148, <effectType>, activeOnly=1, flags=6) )

  Ici `<effectType> = 0x4b5 = 1205 RealityUnbound_Movement` : l'anti-re-trigger du tour est l'effet
  Movement lui-meme (contraste WeaverOfFate, qui passe son propre marqueur 1185).

- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RealityUnboundAbility$$CreateBehaviour` :

      op_Addition(
        AddStaticStatModifierEffect(self@0x148, 0x4b5 = 1205, stat = 1    = MOVEMENT,
                                    GetNumberConstant(cfg, 0xe = extraMovement),
                                    turns = Nullable<int>(1), isHidden = 0),
        AddStaticStatModifierEffect(self@0x148, 0x4b6 = 1206, stat = 0x18 = EXTRA_RANGE,
                                    GetNumberConstant(cfg, 0xd = extraRange),
                                    turns = Nullable<int>(1), isHidden = 0) )

## Volet B — ExtraMaxDamage (`RealityUnboundExtraMaxDamageAbility`)

- `...RealityUnboundExtraMaxDamageAbility$$CreateTrigger` :

      On(0x43 = 66 = FinalDamage, subject=1)
      & HasTakenDamageOfDamageProfileThisTurnAmountOfTimes(
            unit = target@0x178, damageProfile = 0xd = Psychic, times = 1, unitSelectionType = 2)
      & AreEnemies(target@0x178, self@0x148)

- `...RealityUnboundExtraMaxDamageAbility$$CreateBehaviour` (corps IDENTIQUE a son `$$AddModifier`) :

      AddStaticStatModifierEffect(self@0x148, 0x4b7 = 1207, stat = 0x19 = EXTRA_MAX_DAMAGE,
                                  GetVariableForLevel(cfg, 0x49 = extraMaxDmg, abilityState),
                                  turns = Nullable<int>(1), isHidden = 0)

`IdunBattle.Entities.Triggers.HasTakenDamageOfDamageProfileThisTurnAmountOfTimesTrigger$$ShouldTrigger`
est une **EGALITE STRICTE** (`receivedDamageThisTurn[profil] == times`), pas un `>=` : avec
`times = 1`, le trigger ne fire QUE sur la PREMIERE instance de degat Psychic encaissee par cette
cible ce tour. C'est exactement le « for each **different** enemy unit » de l'i2 — chaque ennemi ne
compte qu'une fois, et le 2e coup Psychic sur la MEME cible ne redonne rien. (`unitSelectionType`
@+0x20 n'est JAMAIS lu par `ShouldTrigger` -> non porte, sans effet.)

Qualification des enums (dump du build) : `AbilityConstantType` 0xd = `extraRange`, 0xe =
`extraMovement` ; `AbilityVariableType` 0x49 = `extraMaxDmg` (dans `variablesAffectedByRarityBonus`
-> rarity-scale) ; `DamageProfileType` 0xd = `Psychic` ; `EventTriggerType` 0x42 = `FinalDamage` et
9 = `Attack` ; `StatType` 1 = MOVEMENT, 0x18 = EXTRA_RANGE, 0x19 = EXTRA_MAX_DAMAGE.

## Consommation des stats posees (ce qui rendait ce port no-op)

Avant ce port, `EXTRA_RANGE` et `EXTRA_MAX_DAMAGE` n'avaient AUCUN consommateur dans `engine/` :
poser le stat-mod n'aurait rien change. Les deux foyers natifs sont desormais mirrores :
- `EXTRA_MAX_DAMAGE` -> `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` :
  `if (!IsMeleeAttack(...)) extra = GetStat(attaquant, 0x19) ; else 0`, passe en 5e argument de
  `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64` (`max += extra`). Cable dans
  `damage_ops.py::execute` (`_reduced_bounds`), gate `_ranged`.
- `EXTRA_RANGE` -> `IdunBattle.Core.Services.TargetingQuery$$GetRange` :
  `range = GetStat(u, 0x18) + FindLongestRangedWeapon(u).range` sur la seule branche ranged. Cable
  dans `triggers/base.py::_max_attack_range`.
`MOVEMENT` etait, lui, deja consomme (`state_bridge._move_range` lit le stat live).

DOCTRINE #149 : les deux `CreateTrigger` sont COLLAPSES imperativement dans `matches()` (choix de
repo, cf. `docs/rl/dsl-effect-nodes.md`) ; les deux `CreateBehaviour` sont de VRAIS ARBRES DSL
(`Seq` = `op_Addition`, feuilles `AddStaticStatModifierEffect`).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import Seq
from .....entities.damage_profile_type import DamageProfileType
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.selectors import Caster
from .....entities.stats import StatType
from ....components import OwnerComponent, StatsComponent, UnitComponent
from ....abilities.behaviours import entities_from_state
from ....abilities.behaviours.effects import AddStaticStatModifierEffect
from ....state import State
from ..base import TriggeredAbility, TriggerEvent
from .weaver_of_fate import _alive_enemies_of, units_that_taken_damage_this_turn

ABILITY_ID = "RealityUnbound"
RU_MOVEMENT = int(EffectType.RealityUnbound_Movement)                # 1205 (0x4b5)
RU_RANGE = int(EffectType.RealityUnbound_Range)                      # 1206 (0x4b6)
RU_EXTRA_MAX_DAMAGE = int(EffectType.RealityUnbound_ExtraMaxDamage)  # 1207 (0x4b7)
_PSYCHIC = int(DamageProfileType.Psychic)                            # 0xd — arg du selecteur natif
_THRESHOLD = 3                                                       # `Get(3)` litteral du trigger
_TIMES = 1                                                           # `times` du trigger volet B


def reality_unbound_extra_movement() -> int:
    """`AbilityConfiguration.GetNumberConstant(cfg, 0xe = extraMovement)` = gameconfig
    `RealityUnbound.constants.extraMovement` (=1). 0 si la cle manque (no-op fidele)."""
    v = ability_var(ABILITY_ID, "extraMovement", is_constant=True)
    return 0 if v is None else int(v)


def reality_unbound_extra_range() -> int:
    """`AbilityConfiguration.GetNumberConstant(cfg, 0xd = extraRange)` = gameconfig
    `RealityUnbound.constants.extraRange` (=1). 0 si la cle manque."""
    v = ability_var(ABILITY_ID, "extraRange", is_constant=True)
    return 0 if v is None else int(v)


def reality_unbound_extra_max_damage(state: State, owner_id: int) -> int:
    """`AbilityConfiguration.GetVariableForLevel(cfg, 0x49 = extraMaxDmg, abilityState)` — variable
    PER-NIVEAU. `RealityUnbound` etant un PASSIF, le niveau est `passive_ability_level` (jamais
    `active_ability_level` — meme regle que DestroyerHive/Hypersensory), et `extraMaxDmg` figure dans
    `variablesAffectedByRarityBonus` -> scale par `ability_variables_multiplier`."""
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None)
    if ctx is None:
        return 0
    lvl = int(getattr(ctx, "passive_ability_level", 0) or 0)
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
    return int(ability_var(ABILITY_ID, "extraMaxDmg", lvl, multiplier_pct=mult) or 0)


def _are_enemies(state: State, a_id: Optional[int], b_id: Optional[int]) -> bool:
    """`IdunBattleLogic.Entities.DSLFactory$$AreEnemies(a, b)` sur deux selecteurs MONO-unite :
    equipes DIFFERENTES. Une entite sans `OwnerComponent` (ou absente) -> False."""
    if a_id is None or b_id is None:
        return False
    ea, eb = state.get_entity(a_id), state.get_entity(b_id)
    oa = ea.get_component(OwnerComponent) if ea is not None else None
    ob = eb.get_component(OwnerComponent) if eb is not None else None
    return oa is not None and ob is not None and oa.team != ob.team


def has_taken_damage_of_damage_profile_this_turn_amount_of_times(
        state: State, unit_id: Optional[int], profile_id: int, times: int) -> bool:
    """Mirror 1:1 de `IdunBattle.Entities.Triggers.
    HasTakenDamageOfDamageProfileThisTurnAmountOfTimesTrigger$$ShouldTrigger` :

        ContainsKey(receivedDamageThisTurn, profile) && receivedDamageThisTurn[profile] == times

    **EGALITE STRICTE** (`local_res10[0] == *(int *)(this + 0x1c)`) — pas un `>=`. Cle absente ->
    False (le `ContainsKey` garde). Le champ `unitSelectionType` (this+0x20) n'est PAS lu."""
    e = state.get_entity(unit_id) if unit_id is not None else None
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None:
        return False
    d = uc.received_damage_this_turn or {}
    if profile_id not in d:
        return False
    return int(d[profile_id]) == int(times)


def reality_unbound_move_range_tree():
    """Arbre E de `...RealityUnboundAbility$$CreateBehaviour` — MIRROR 1:1 :

        op_Addition(
            AddStaticStatModifierEffect(Self, 1205, MOVEMENT,    extraMovement, turns=Direct(1)),
            AddStaticStatModifierEffect(Self, 1206, EXTRA_RANGE, extraRange,    turns=Direct(1)) )

    `Self@0x148 == Caster()` (triggered : Owner == Caster). `turns` natif = `Nullable<int>(1)` = une
    valeur DEJA en TOURS -> `duration_turns=1` (surtout PAS `duration_rounds`, qui est le noeud
    `TurnsFromRounds` et passerait par `ConvertRoundsToTurns`). « until the end of this turn »."""
    move = AddStaticStatModifierEffect(Caster(), RU_MOVEMENT, int(StatType.MOVEMENT),
                                       Const(reality_unbound_extra_movement()),
                                       name=EffectType.RealityUnbound_Movement.name,
                                       duration_turns=1)
    rng = AddStaticStatModifierEffect(Caster(), RU_RANGE, int(StatType.EXTRA_RANGE),
                                      Const(reality_unbound_extra_range()),
                                      name=EffectType.RealityUnbound_Range.name,
                                      duration_turns=1)
    return Seq(move, rng)                       # `IdunBattle.DSL.AbilityBehaviour$$op_Addition`


def reality_unbound_extra_max_damage_tree(amount: int):
    """Arbre E de `...RealityUnboundExtraMaxDamageAbility$$CreateBehaviour` — MIRROR 1:1 :

        AddStaticStatModifierEffect(Self, 1207, EXTRA_MAX_DAMAGE, ConfigVar(extraMaxDmg), turns=1)

    `amount` est le FOLD du noeud `GetVariableForLevel` (meme regime que `ArcaneShield`/`DestroyerHive`
    : la magnitude config est resolue imperativement, la STRUCTURE de l'arbre est preservee)."""
    return AddStaticStatModifierEffect(Caster(), RU_EXTRA_MAX_DAMAGE,
                                       int(StatType.EXTRA_MAX_DAMAGE), Const(int(amount)),
                                       name=EffectType.RealityUnbound_ExtraMaxDamage.name,
                                       duration_turns=1)


class RealityUnboundAbility(TriggeredAbility):
    """Volet A — `On(9=Attack)` : des que >= 3 ennemis DISTINCTS ont encaisse du degat Psychic ce
    tour, Yazaghor gagne +1 Movement (effet 1205) et +1 Range (effet 1206) pour 1 tour.

    `matches` = collapse du trigger `WeaverOfFateAbility$$GetTrigger(0x4b5)` (cf. en-tete). Aucun gate
    `OwnerIsCaster` cote natif : `On(9)` est l'event GENERIQUE de fin d'attaque, le comptage et le
    `Not(HasEffect)` sont les SEULS gates -> une attaque de N'IMPORTE QUI peut armer le passif (c'est
    ce que dit l'i2 : « enemy units that WERE DEALT Psychic damage », par qui que ce soit)."""
    event_id = int(EventTriggerType.Attack)                # On(9)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # Not(HasEffect(self@0x148, 0x4b5, activeOnly=1, flags=6)) — anti re-trigger tant que le buff
        # du tour est pose (le natif passe l'effet MOVEMENT, pas un marqueur dedie).
        if state.effects is not None and state.effects.has_effect(
                self.owner_id, effect_type=RU_MOVEMENT):
            return False
        # AmountIsEqualOrGreater(UnitsThatTakenDamageThisTurn(Enemies(self, AllUnits), Psychic), Get(3))
        enemies = _alive_enemies_of(state, self.owner_id)
        hit = units_that_taken_damage_this_turn(state, enemies, _PSYCHIC)
        return len(hit) >= _THRESHOLD

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        reality_unbound_move_range_tree().execute(
            entities_from_state(state, self.owner_id, ev.target_id), ectx)
        placed = [p for n, p in ectx.emitted if n == "AddStaticStatModifierEffect"]
        if not placed:
            return None
        return {"type": "reality_unbound_move_range", "unit": int(self.owner_id),
                "movement": reality_unbound_extra_movement(),
                "range": reality_unbound_extra_range(),
                "placed": [p["effect_type"] for p in placed]}


class RealityUnboundExtraMaxDamageAbility(TriggeredAbility):
    """Volet B — `On(66=FinalDamage)` : a la PREMIERE instance de degat Psychic encaissee par un
    ennemi ce tour, Yazaghor gagne +extraMaxDmg de degat MAXIMUM (effet 1207) pour 1 tour.

    STACK : le natif appelle `AddStaticStatModifierEffect` une fois par ennemi distinct **sans
    `RemoveEffect` prealable** (contraste explicite avec `MasterAnnihilator` et `FleshmetalGuns`, qui
    font Remove+Add), et l'i2 dit « FOR EACH different enemy unit ... +181 » -> les instances
    CUMULENT. Cote port c'est la classe d'effet 1207 qui porte `stacks_stat_mod_on_add = True`
    (patron ActOfFaith), sans quoi le gate « deja-present » d'`AddEffectOperation` no-operait les
    poses suivantes."""
    event_id = int(EventTriggerType.FinalDamage)           # On(0x43 = 67)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # HasTakenDamageOfDamageProfileThisTurnAmountOfTimes(target@0x178, Psychic, times=1)
        if not has_taken_damage_of_damage_profile_this_turn_amount_of_times(
                state, ev.target_id, _PSYCHIC, _TIMES):
            return False
        # AreEnemies(target@0x178, self@0x148)
        return _are_enemies(state, ev.target_id, self.owner_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        if state.effects is None:
            return None
        amount = reality_unbound_extra_max_damage(state, self.owner_id)
        if amount <= 0:
            return None                    # magnitude nulle (niveau/config absent) -> no-op fidele
        ectx = ExecutionContext(state=state, rng=state.rng)
        reality_unbound_extra_max_damage_tree(amount).execute(
            entities_from_state(state, self.owner_id, ev.target_id), ectx)
        placed = [p for n, p in ectx.emitted if n == "AddStaticStatModifierEffect"]
        if not placed:
            return None
        return {"type": "reality_unbound_extra_max_damage", "unit": int(self.owner_id),
                "victim": int(ev.target_id) if ev.target_id is not None else None,
                "amount": amount}
