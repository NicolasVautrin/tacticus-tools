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
from .....entities.triggered_ability_type import (TriggeredAbilityType,
                                                  entity_triggered_ability_ids)
from ....state import State
from ....components import StatsComponent, UnitComponent, OwnerComponent
from ..base import TriggeredAbility, TriggerEvent
from ...effects import AddEffectOperation

WEAVER_MAXOUT = int(EffectType.WeaverOfFate_MaxOutDamage)      # 1185 (0x4a1)
#: SECONDE branche d'`IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage` (#1013) -- la
#: relique `custoKyrus`. `TriggeredAbilityType`, PAS `EffectType` : le natif teste
#: `HasTriggeredAbility`, une lecture du KIT DECLENCHE.
PARAGON_SPEAR = int(TriggeredAbilityType.ParagonSpear)         # 1494 (0x5d6)
_PSYCHIC = int(DamageProfileType.Psychic)                      # 13 (0xd) — arg du selecteur natif
_THRESHOLD = 3                                                 # DSLFactory.Get(3) — constante EN DUR
# 2e branche de `IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage` :
# `HasTriggeredAbility(unit, 0x5d6 = 1494 ParagonSpear)`. Porteur DISTINCT (hors kit Abraxas), et
# elle EST mirroree depuis #1013 -- `is_attack_max_out_damage_on_crit` ci-dessous. Le motif qui la
# tenait ouverte (<< porteur hors kit >>, residu case-202 §6) etait PERIME : c'est une RELIQUE, et
# `custoKyrus` est DANS le pool rank 17 -> confrontable par `--equip-relic` seul (#237/#357).


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
    l'effet 1185 ACTIF sur l'attaquant.

    La SECONDE branche du meme natif (`HasTriggeredAbility(1494 ParagonSpear)`) vit dans
    `is_attack_max_out_damage_on_crit` ci-dessous : elle est gatee sur le coup CRITIQUE, celle-ci
    ne l'est pas -- deux predicats, deux portees."""
    if state.effects is None:
        return False
    return bool(state.effects.has_effect(attacker_id, effect_type=WEAVER_MAXOUT))


def is_attack_max_out_damage_on_crit(state: State, attacker_id: int) -> bool:
    """SECONDE branche d'`IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage` (#1013) :

        if (IsOwnerOfEffect(attacker, 0x4a1) || IsTargetOfEffect(attacker, 0x4a1)) return true;
        if (UnitExtensions.HasTriggeredAbility(attacker, 0x5d6))                 // 1494 ParagonSpear
            return <entities+0xf8>;                                              // = isCritical
        return false;

    Le natif rend, pour un porteur de `ParagonSpear`, le champ `isCritical` de l'`AbilityEntities`
    que l'appelant vient de batir -- donc **le max-out ne vaut QUE pour un coup CRITIQUE**, la ou
    la branche effet 1185 vaut inconditionnellement. Ce champ est LU au site :
    `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` construit son `AbilityEntities` avec
    le resultat de `RollCritical` en 23e argument, et n'appelle `IsAttackMaxOutDamage` que sous
    `if (isCritical != 0)`.

    ⚠ CE PREDICAT NE REGARDE PAS QUELLE ABILITY FRAPPE : `HasTriggeredAbility` lit le KIT du
    porteur. Tout coup critique de `custoKyrus` equipe de la lance est maximise -- son attaque
    normale et `VigilanceEternal` comprises, pas seulement la lance elle-meme.

    MESURE (#1013, `probe_1013_paragon_spear.py`, flux RNG PROUVE aligne -- meme `mti`, meme
    tableau MT final) : `custoKyrus` + relique niveau 1, `CritChance = 100`, cible sans reduction,
    natif = **11292 sur TROIS seeds** alors que les tirages different, soit
    `2 x (maxDmg[1] + CritDamage) = 2 x (2940 + 2706)`. La loi a ete CONFIRMEE PAR PREDICTION aux
    niveaux 3 et 5 (11926 et 12562, tous deux atteints). En `CritChance = 0`, le natif VARIE avec
    la seed et le port l'egalait deja bit-exact : c'est bien le crit, et lui seul, qui maxe.

    Le motif qui justifiait de ne pas la porter (« porteur hors kit — residu case-202 §6 ») etait
    PERIME : `ParagonSpear` est une RELIQUE, et son porteur `custoKyrus` est DANS le pool rank 17
    -- confrontable par `--equip-relic` seul depuis #237/#357."""
    ctx = _unit_ctx(state, attacker_id)
    if ctx is None:
        return False                       # canal absent -> on ne fabrique pas un max-out
    return PARAGON_SPEAR in entity_triggered_ability_ids(ctx, getattr(ctx, "visual_id", None))


def _unit_ctx(state: State, unit_id: int):
    """`StatsComponent.ctx` de l'unite, ou None. Le kit DECLENCHE se lit la (foyer unique
    `entities/triggered_ability_type.entity_triggered_ability_ids`), jamais du gameconfig : une
    RELIQUE equipee n'est visible que par ce canal (#357)."""
    e = state.get_entity(unit_id) if state is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    return getattr(sc, "ctx", None) if sc is not None else None
