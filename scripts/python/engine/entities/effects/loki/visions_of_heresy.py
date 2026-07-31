"""`VisionsOfHeresy_ExtraPierceMelee` (0x541 = 1345) et `VisionsOfHeresy_ExtraPierceRanged`
(0x542 = 1346) — le canal PERCAGE conditionnel du passif `VisionsOfHeresy` (TriggeredAbilityType
0x4f0 = 1264) de `bloodDeathCompany` (<< Lucien >>, Death Company). case-366-r1.

## UNE classe native, DEUX `EffectType` — tranche par le SLOT, pas par le nom

`probe_366_inventaire_effets_forme_b.py --csv` rend pour les deux ids le MEME slot
`Il2CppClass*` et le meme `$$.ctor` :

    1345 -> Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.VisionsOfHeresy_ExtraPierceEffect
    1346 -> (le MEME slot)

et ce slot est DISTINCT de celui de l'instance generique `IdunBattle.Entities.Effects.
StaticStatModifierEffect` (celui de `1171`/`1251`/`1256`, le lot G1 de case-371) : c'est donc bien
une classe DEDIEE, qui DERIVE de `StaticStatModifierEffect` (son `$$.ctor` appelle
`IdunBattle.Entities.Effects.StaticStatModifierEffect$$.ctor`) et n'ajoute qu'une
`CreateActiveCondition`.

Le discriminant melee/ranged n'est donc PAS dans la classe d'effet : il est dans le `statType`
que le POSEUR passe a la feuille DSL. `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
VisionsOfHeresy_ExtraPierceAbility$$CreateBehaviour` (MIRROR 1:1 du decompile) :

    amount = ConfigVar(0x3f = extraPierceRatio, <abilityState>, <config de l'ability>)
      AddStaticStatModifierEffect(Owner, 0x541 = 1345, statType = 0x15 = 21 EXTRA_PIERCE_MELEE,
                                  amount, turns = NULL, isHidden)
    & AddStaticStatModifierEffect(Owner, 0x542 = 1346, statType = 0x16 = 22 EXTRA_PIERCE_RANGED,
                                  amount, turns = NULL, isHidden)
    (les deux combinees par `IdunBattle.DSL.AbilityBehaviour$$op_BitwiseAnd`)

`turns = NULL` => PERMANENTS (aucun timer) ; ce qui les eteint est la CONDITION, pas une duree.
Cote port, les deux classes ci-dessous ne different QUE par `get_stat_modification_stat()` — c'est
le parametre de pose, materialise par-EffectType parce que le registre du port est keye par NOM.

Le `$$.ctor` de l'effet ecrit `mov edx, 0x4f0` avant `AbilityOrEffect$$op_Implicit` : l'`EffectSource`
est l'ability **1264 VisionsOfHeresy**, donc la config lue est la sienne.

## CANAL — le STAT, lu par la formule de percage

`IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio` (decompile) :

    extra    = GetStat(attacker, 0x1a = 26 ExtraPierce)
    extraDir = GetStat(attacker, isMelee ? 0x15 = 21 : 0x16 = 22)
    base     = GetPiercingRatio(damageProfile, GetTraits(attacker))
    return Min(100, Max(base > 0, extraDir + extra + defMod + attMod + base))

Ce n'est donc NI un `EffectBonus.ForPiercing` (le canal de `GravitonRifle_ExtraPierce` /
`Hailstrike_ExtraPierce`, qui entre en `attackModifier`/`defenderModifier`), NI un groupe #179 :
c'est une **stat-modification** sur 21/22, posee/retiree par le cycle
`AStatModifierEffect.ApplyModification`/`RevertModification`. Cote port, `ctx.extra_pierce_melee` /
`ctx.extra_pierce_ranged` sont adossees a `get_stat(Current)` (cf. `entities/unit_context.py`),
donc la contribution de ces effets y entre par le driver `refresh_stat_modifier_effects`.

## ACTIVE-CONDITION — `HealthPct <= healthPct`

`Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.VisionsOfHeresy_ExtraPierceEffect$$CreateActiveCondition` :

    HealthPctIsBelowOrEqual( Owner, ConfigConst(0x4f = healthPct) )

La surcharge de `IdunBattle.Entities.Formulas.ConfigAmount$$.ctor` appelee ici est TRANCHEE PAR SES
XREFS ENTRANTES (jamais a l'oeil) : c'est celle qu'appelle `IdunBattleLogic.Entities.DSLFormulas$$ConfigConst`,
donc `0x4f` est un **AbilityConstantType** (`constants["healthPct"]` = 50), pas une variable.
`IdunBattleLogic.Entities.DSLTriggers$$HealthPctIsBelowOrEqual` alloue un
`IdunBattle.Entities.Conditions.StatPercentageIsBelowOrEqualAbilityTrigger` sur la stat **5 = HEALTH** ;
son `$$ShouldTrigger` calcule `GetStat(5, part 0 CURRENT) / GetStat(5, part 2 MAXIMUM) <= pct/100`
en Fix64 (`op_LessThanOrEqual`) — comparaison INCLUSIVE. Jumeau structurel deja porte :
`HammerOfWrath_ConditionalDamageEffect` (meme helper, meme constante 0x4f, meme comparaison entiere).

i2 (`Abilities/VisionsOfHeresy_CurrentLevelDescription`) : « If Lucien is at or below {healthPct}%
Health, all of his attacks have +{extraPierceRatio}% pierce ratio. »

## MAGNITUDE

`ConfigVar(0x3f)` = `gameconfig.ability("VisionsOfHeresy").variables["extraPierceRatio"][level]`
(10 -> 20 sur 65 niveaux ; 20 au niveau normalise 50). `extraPierceRatio` n'est **PAS** dans
`variablesAffectedByRarityBonus` (qui ne contient que `minDmg`/`maxDmg`) -> AUCUN scaling de rarete,
et `ability_var` applique cette regle config-driven toute seule.

`VisionsOfHeresy` est une ability **PASSIVE** (`GC.unit("bloodDeathCompany").passiveAbilities`) ->
le niveau qui indexe la variable est `ability_level` (= `unitConfig.passiveAbilityLevel`, propage
par `EffectsState.seed` au capte et par `_materialize_owner_effect` au seed d'init).

## POSE / SEED

Owner-effects poses a l'INIT de l'ability (meme mecanisme qu'`AnvilShield` / `HammerOfWrath`) ->
`ABILITY_INIT_OWNER_EFFECTS["VisionsOfHeresy"]`. Sans ce seed ils seraient ABSENTS de tout runner
demarrant Lucien au-dessus de 50 % PV : `decisionView.effects` n'expose que les effets ACTIFS
(GROUND TRUTH #100), donc le canal de capture ne peut pas les livrer tant que la condition est
fausse — et le bonus n'apparaitrait JAMAIS quand Lucien descend en cours de bataille.

Le `ChangeStat` n'est PAS declare en `applied_stat_mods` : il est pilote par
`runner/operations/refresh_effects.py` (mirror `IdunBattle.Operations.RefreshEffectsOperation`
ActivateEffect/DeactivateEffect -> `AStatModifierEffect.ApplyModification`/`RevertModification`),
pour que la contribution SUIVE la condition dans les DEUX sens. `get_stat_modification_stat/amount`
restent declares : c'est ce que lit l'ATTRIBUTION du seed (`stat_modifications_by_source`) quand
l'effet est capte live (donc deja actif).
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect
from ..magnitude import ability_var

_ABILITY_ID = "VisionsOfHeresy"          # TriggeredAbilityType 0x4f0 = 1264 (passif, bloodDeathCompany)


class VisionsOfHeresyExtraPierceEffect(BaseEffect):
    """Base commune des deux `EffectType` — mirror de l'UNIQUE classe native
    `VisionsOfHeresy_ExtraPierceEffect` (un seul slot `Il2CppClass*` pour 1345 et 1346).

    Ne porte PAS de `get_stat_modification_stat` : le `statType` est le parametre que le poseur
    (`VisionsOfHeresy_ExtraPierceAbility$$CreateBehaviour`) passe a `AddStaticStatModifierEffect`,
    donc il vit dans les sous-classes par-EffectType."""

    def is_active(self, unit_state: "Mapping | None" = None) -> bool:
        """`CreateActiveCondition` = `HealthPctIsBelowOrEqual(Owner, ConfigConst(0x4f = healthPct))`.
        `unit_state` = `{hp, max_hp}` (convention `unit_state_for_effects`). PV non captes -> True
        (degradation fidele : on ne masque pas l'effet a tort — meme regime qu'`AnvilShield` /
        `HammerOfWrath`).

        Comparaison ENTIERE exacte `100*hp <= pct*max` : pour des PV entiers la division Fix64 du
        natif ne bascule jamais autrement, et l'egalite au bord (2*hp == max) est rendue 0.5 exact
        -> `<=` vrai."""
        s = unit_state or {}
        hp, mx = s.get("hp"), s.get("max_hp")
        pct = ability_var(_ABILITY_ID, "healthPct", is_constant=True)   # ConfigConst(0x4f) = 50
        if hp is None or mx is None or not mx or pct is None:
            return True
        return 100 * int(hp) <= int(pct) * int(mx)

    def get_stat_modification_amount(self) -> "int | None":
        """`GetStatModificationAmount` = le `ConfigVar(0x3f = extraPierceRatio)` que le poseur a fige
        dans l'effet. Indexe par le niveau de la PASSIVE (`ability_level`), repli stack level.
        `extraPierceRatio` hors `variablesAffectedByRarityBonus` -> non scale par la rarete."""
        lvl = self.ability_level if self.ability_level is not None else self.level
        return ability_var(_ABILITY_ID, "extraPierceRatio", lvl,
                           multiplier_pct=self.ability_variables_multiplier)

    # `reverted_stats()` : le DEFAUT de la base (`[get_stat_modification_stat()]`) est deja le mirror
    # exact de la paire `ApplyModification`/`RevertModification` -> rien a surcharger ici.


class VisionsOfHeresyExtraPierceMeleeEffect(VisionsOfHeresyExtraPierceEffect):
    """`VisionsOfHeresy_ExtraPierceMelee` (0x541 = 1345) — `statType = 0x15 = 21`."""

    def get_stat_modification_stat(self) -> "int | None":
        return 21                                    # StatType.EXTRA_PIERCE_MELEE


class VisionsOfHeresyExtraPierceRangedEffect(VisionsOfHeresyExtraPierceEffect):
    """`VisionsOfHeresy_ExtraPierceRanged` (0x542 = 1346) — `statType = 0x16 = 22`."""

    def get_stat_modification_stat(self) -> "int | None":
        return 22                                    # StatType.EXTRA_PIERCE_RANGED
