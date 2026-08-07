"""Port de `IdunBattle.Entities.Selectors.SortTargetsByDamagePredictionSelector` (noeud DSL
`IdunBattleLogic.Entities.DSLSelectors$$SortTargetsByDamagePredictionSelector`) — tri de cibles par
la PREDICTION de degat de l'attaque, avec priorite aux KILLS.

C'est le pendant, cote PREDICTION REELLE (post-armure), du tri IA pre-armure
`SortUnitsByDamageUtilitySelector` (`damage_utility.py`) : deux selecteurs natifs DISTINCTS, deux
modules de port distincts.

SIGNATURES NATIVES (`frida/methods.tsv`, verbatim) :

    DSLSelectors.SortTargetsByDamagePredictionSelector(
        attacker: ITargetsSelector, units: ITargetsSelector,
        ability: IAbilityTypeSelector, damage: IAmountFormula, hits: IAmountFormula,
        damageProfileType: IDamageProfileSelector, attackerSelectionType: UnitSelectionType)
    SortTargetsByDamagePredictionSelector..ctor(
        attacker, targets, ability, damage, damageProfileType, hits, attackerSelectionType,
        query: IBattleQuery, state: IMatchState)

Le ctor STOCKE `query` et `state` en champs (`+0x50` / base) : le `state` porte ci-dessous en champ
du noeud est donc un MIRROR, pas une entorse au DSL.

DECOMPILE (`…SortTargetsByDamagePredictionSelector$$Select`, lecture integrale) :

    targets  = (+0x20).SelectUniqueUnits(entities, attackerSelectionType)   # ITargetsSelector slot 4
    attacker = (+0x18).SelectUnit(entities, attackerSelectionType)          # ITargetsSelector slot 7
    if attacker == null : return new List<IEntity>()                        # liste VIDE
    ability  = (+0x28) != null ? (+0x28).<slot 0>(entities) : default(AbilityOrEffect)
    profile  = (+0x38).<slot 0>(entities)
    position = EntityExtensions.GetUnitPosition(attacker, state)
    dmgMin   = (+0x30).CalculateMin(entities)         # IAmountFormula slot 2
    dmgAvg   = (+0x30).CalculateAverage(entities)     #                slot 4
    dmgMax   = (+0x30).CalculateMax(entities)         #                slot 3
    nbHits   = (+0x40).Calculate(entities)            #                slot 1
    return targets.OrderByDescending(u => key(u)).ToList()

    key(u) :                                          # <>c__DisplayClass9_0.<Select>b__0
        pMin = query.GetMultiHitAttackPrediction(attacker, u, position, ability, dmgMin, profile, nbHits)
        pAvg = query.GetMultiHitAttackPrediction(attacker, u, position, ability, dmgAvg, profile, nbHits)
        pMax = query.GetMultiHitAttackPrediction(attacker, u, position, ability, dmgMax, profile, nbHits)
        if pMax.WillBeKill  : return int.MaxValue          # 0x7fffffff
        if pMin.MightBeKill : return int.MaxValue - 1      # 0x7ffffffe
        return MinMaxDamage.Avg(pAvg.<+0x60>)

Les slots d'`IAmountFormula` sont LUS dans les metadonnees IL2CPP du build
(`data/symbols/<build>/metadata/interface_slots.tsv`) : `0 IsSimple · 1 Calculate · 2 CalculateMin ·
3 CalculateMax · 4 CalculateAverage`. L'appariement min/max n'est donc PAS deduit de la semantique :
c'est bien le MAX qui alimente `WillBeKill` et le MIN qui alimente `MightBeKill`.

`IdunBattle.Core.Services.BattleQuery$$GetMultiHitAttackPrediction` = `hits` appels de
`$$GetAttackPrediction` avec `previousHitsPrediction` threade + `DamagePredictionResult$$Add` — c'est
exactement ce que fait deja `services/damage_prediction.get_attack_prediction` (qui delegue a
`get_multi_hit_attack_prediction`).

`IdunBattle.Core.Services.MinMaxDamage$$Avg` = `Round((Fix64(Min) + Fix64(Max)) / 2)` (LU) ;
`IdunBattle.DSL.AAmountFormula$$CalculateAverage` = `(CalculateMin + CalculateMax) / 2` en division
ENTIERE quand `IsSimple` est faux (LU : `(iVar16 + iVar15) / 2`), sinon `Calculate` seul.

RESIDUS NOMMES (aucun n'est un fit ; tous sont des lectures ou des etages non modelises) :

  * **le champ `+0x60`** dont le natif prend l'`Avg` n'est pas identifie NOMINALEMENT : le layout de
    `DamagePredictionResult` de ce build (0xa0 octets) porte cinq `MinMaxDamage` — `+0x14`
    (HealthDamage, lu par `$$get_WillBeKill`@+0x1c / `$$get_MightBeKill`@+0x20 /
    `$$get_HealthDamageWithBlock`), `+0x24` (ShieldDamage, lu par `$$get_ShieldDamage`) et trois
    cumulees par `$$Add` (`+0x40`, `+0x50`, `+0x60`). Le port prend `accurate_health_damage`, la
    seule des trois qui soit un degat SANTE. Ce choix n'affecte le classement QUE parmi les cibles
    qui ne franchissent NI `WillBeKill` NI `MightBeKill` (les deux premiers rangs sont, eux, lus
    sans ambiguite).
  * **bouclier et scenarios de BLOCK non modelises** dans la prediction montee ici — meme residu que
    `damage_utility.py` (`shieldBefore = 0`).
  * **tie-break** : `OrderByDescending` .NET est STABLE ; le port utilise `sorted(..., reverse=True)`
    qui l'est aussi, donc l'ordre SOURCE est preserve a cle egale. Fidele tant que l'appelant fournit
    la source dans l'ordre natif.
"""
from __future__ import annotations

from typing import Optional

from ...dsl.base import TargetsSelector, resolve_unit
from ...entities.damage_profile_type import DamageProfileType
from ...services.damage_prediction import get_attack_prediction
from ..components import HealthComponent, StatsComponent
from ..damage_model import (attacker_modifiers, defender_modifiers, defender_fixed_armor,
                            apply_elevation_bonus, apply_trench_reduction, target_trait_names)

# `int.MaxValue` / `int.MaxValue - 1` : les deux rangs LITTERAUX de `<Select>b__0`. Ce ne sont pas des
# seuils fittes — ils sont ecrits tels quels dans le decompile (`0x7fffffff` / `0x7ffffffe`).
KEY_WILL_BE_KILL = 0x7FFFFFFF
KEY_MIGHT_BE_KILL = 0x7FFFFFFE


def multi_hit_attack_prediction(state, attacker_id: int, target_id: int, amount: int, hits: int,
                                damage_profile: str, pierce: int, is_melee: bool = False,
                                ability_type: Optional[int] = None):
    """`IdunBattle.Core.Services.BattleQuery$$GetMultiHitAttackPrediction(attacker, target,
    attackerPosition, ability, damage, damageProfile, hits)` monte depuis le `State` runner.

    Les entrees PAR CIBLE sont assemblees avec les MEMES primitives publiques que l'EXECUTION
    (`damage_ops/ability.execute_ability_attack`) — `attacker_modifiers` (famille ATTACK : nature du
    coup, traits de la cible, profil et ability declenchante threades), les feuilles POSITIONNELLES
    (elevation / trench), `defender_fixed_armor` et `defender_modifiers` — puis le calcul lui-meme
    passe par le foyer unique `services/damage_prediction`. Ce n'est donc PAS un fork du calcul : le
    natif a lui aussi DEUX chemins (prediction / execution) qui partagent `$$PredictAttackRaw`.

    Rend `None` quand la cible n'a pas de `HealthComponent` (rien a predire)."""
    att = state.get_entity(attacker_id)
    tgt = state.get_entity(target_id)
    thc = tgt.get_component(HealthComponent) if tgt is not None else None
    if thc is None:
        return None
    asc = att.get_component(StatsComponent) if att is not None else None
    ahc = att.get_component(HealthComponent) if att is not None else None
    _ranged = (not is_melee) if is_melee is not None else None
    if asc is None:
        from ...services.damage_modifiers import DamageModifiers   # differe PORTEUR : cycle services<->runner
        mods, active = DamageModifiers(), []
    else:
        mods, active = attacker_modifiers(state, attacker_id, ahc.hp if ahc else None,
                                          target_id=target_id, is_ranged=_ranged,
                                          is_normal_attack=False,
                                          target_traits=target_trait_names(state, target_id),
                                          damage_profile=damage_profile,
                                          trigger_ability_type=ability_type)
    apply_elevation_bonus(state, mods, attacker_id, target_id)
    apply_trench_reduction(state, mods, attacker_id, target_id, damage_profile)
    armor = defender_fixed_armor(state, target_id)
    def_mods, _da = defender_modifiers(state, target_id, thc.hp, is_melee=is_melee,
                                       damage_profile=damage_profile, attacker_id=attacker_id,
                                       is_normal_attack=False)
    # Differe PORTEUR : `operations.damage` importe `damage_ops`, qui importe ce paquet -> hisser
    # fermerait le cycle (meme raison, ecrite, que le `from ..damage import AttackDamageOperation`
    # de `damage_ops/ability.py`).
    from .damage import AttackDamageOperation
    AttackDamageOperation._apply_defender_flat_reductions(mods, def_mods)
    return get_attack_prediction(
        target_current_health=int(thc.hp or 0), initial_damage=int(amount), hits=int(hits),
        profile_type=int(DamageProfileType[damage_profile]), armor=armor, pierce_pct=int(pierce),
        mods=mods, attacker_effects=active)


class SortTargetsByDamagePrediction(TargetsSelector):
    """`IdunBattle.Entities.Selectors.SortTargetsByDamagePredictionSelector$$Select` — MIRROR.

    Champs (mapping ctor natif LU, pas devine) : `+0x18` attacker · `+0x20` targets · `+0x28` ability
    · `+0x30` damage · `+0x38` damageProfileType · `+0x40` hits · `+0x48` attackerSelectionType ·
    `+0x50` query (et `state` par la base).

    Le port ne tient pas de noeud `IAmountFormula` pour le degat : il recoit les DEUX bornes de
    `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage` (`minDmg`/`maxDmg`[level], via
    `ability_attack_params`) et derive la moyenne comme `AAmountFormula$$CalculateAverage`. Le noeud
    natif est un `DSLFormulas$$Cache(MinMaxDamage(...))` : `Cache` ne change AUCUNE valeur (il
    memorise l'evaluation pour le cast), et `IsSimple` y est faux des que `minDmg != maxDmg`.

    `attackerSelectionType = 3` (`UnitSelectionType.OnlyAliveAndTargetable`) au call-site Fragstorm :
    le port ne modelise pas `UnitExtensions$$MatchesUnitSelectionType` ; l'effet « vivant » est deja
    porte par le `Damageable(...)` de la source et par `resolve_unit` sur l'attaquant."""

    __slots__ = ("state", "attacker", "targets", "ability_type", "damage_min", "damage_max",
                 "hits", "damage_profile", "pierce", "is_melee")

    def __init__(self, state, attacker: TargetsSelector, targets: TargetsSelector,
                 ability_type: Optional[int], damage_min: int, damage_max: int, hits: int,
                 damage_profile: str, pierce: int, is_melee: bool = False):
        self.state = state
        self.attacker, self.targets = attacker, targets
        self.ability_type = ability_type
        self.damage_min, self.damage_max = int(damage_min), int(damage_max)
        self.hits, self.damage_profile, self.pierce = int(hits), damage_profile, int(pierce)
        self.is_melee = bool(is_melee)

    def _damage_average(self) -> int:
        """`IdunBattle.DSL.AAmountFormula$$CalculateAverage` — `(CalculateMin + CalculateMax) / 2`,
        division ENTIERE C# (troncature vers zero ; les deux bornes sont >= 0 ici)."""
        return (self.damage_min + self.damage_max) // 2

    def _key(self, attacker_id: int, target_id: int) -> int:
        """`…SortTargetsByDamagePredictionSelector.u003Cu003Ec__DisplayClass9_0$$u003CSelectu003Eb__0`."""
        def _pred(amount):
            return multi_hit_attack_prediction(
                self.state, attacker_id, target_id, amount, self.hits, self.damage_profile,
                self.pierce, is_melee=self.is_melee, ability_type=self.ability_type)

        p_max = _pred(self.damage_max)
        if p_max is None:
            return 0
        hp = int(p_max.current_health or 0)
        # `$$get_WillBeKill` = `CurrentHealth@0x00 <= HealthDamage.Min@0x1c` (borne BASSE) ; le port
        # lit la MEME representation NON capee (`raw_health_damage`), cf. l'en-tete de
        # `DamagePredictionResult`. La sortie en tete sur `CannotBeGuaranteedKilled@0x89` n'est pas
        # modelisee (aucun porteur dans le lot) -> residu nomme.
        if hp > 0 and int(p_max.raw_health_damage.min or 0) >= hp:
            return KEY_WILL_BE_KILL
        p_min = _pred(self.damage_min)
        # `$$get_MightBeKill` = `CurrentHealth@0x00 <= HealthDamage.Max@0x20` (borne HAUTE).
        if p_min is not None and hp > 0 and int(p_min.raw_health_damage.max or 0) >= hp:
            return KEY_MIGHT_BE_KILL
        p_avg = _pred(self._damage_average())
        if p_avg is None:
            return 0
        mm = p_avg.accurate_health_damage
        # `IdunBattle.Core.Services.MinMaxDamage$$Avg` = `Round((Min + Max) / 2)`, arrondi Fix64.
        return int(round((int(mm.min or 0) + int(mm.max or 0)) / 2))

    def select(self, ctx):
        att = resolve_unit(self.attacker, ctx)          # (+0x18).SelectUnit(entities, selectionType)
        if att is None or att.get("id") is None:
            return []                                   # `return new List<IEntity>()` — liste VIDE
        attacker_id = int(att["id"])
        units = list(self.targets.evaluate(ctx))        # (+0x20).SelectUniqueUnits(entities, ...)
        if self.state is None:
            return units                                # hors runner : aucune prediction evaluable
        # `OrderByDescending` .NET = tri STABLE decroissant -> `sorted(reverse=True)` (stable aussi).
        return sorted(units, key=lambda u: self._key(attacker_id, int(u.get("id"))), reverse=True)
