"""Effets `Effects.Loki` — famille BONUS DE DÉGÂT ATTAQUANT, volet **DIRECT** : l'effet-entité vit sur
l'attaquant et buffe SA propre attaque (`create_effect_damage_bonus_for_attack`, hook primaire).
1 classe par effet natif (VA citée). Cf. `loki/__init__.py`.

Le volet **AURA** de la même famille — effet posé sur le PORTEUR, projeté sur d'autres unités via un
`CreateTargetSelector` natif (hooks `create_aura_*`) — vit dans `extra_damage_aura.py`.

Chaque classe override UNIQUEMENT ce qu'elle implémente dans le natif (lu en ghidra). Les magnitudes
non encore confirmées par nom gameconfig renvoient None (pas de contribution) = on N'INVENTE PAS de
valeur non prouvée (cf. doc §17.4 « présent ≠ appliqué »)."""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import (EffectBonus, for_addition, for_percent_decrease,
                                       for_percent_increase)
from ...active_ability_type import ActiveAbilityType
from ..base import BaseEffect, is_melee_attack, is_ranged_attack
from ..magnitude import ability_var, trait_var


class RapidAssaultExtraDamageEffect(BaseEffect):
    """`RapidAssault_ExtraDamageEffect` (effet 0x4cd=1229).
    - dégât IdunBattle.Entities.Effects.Loki.RapidAssault_ExtraDamageEffect$$CreateEffectDamageBonusForAttack : `ForPercentIncrease(ConfigConst key 0xf)` = trait var `rapidAssaultExtraDmgPct` (=25, scalaire).
    - cycle de vie : posé à l'init d'ability (`IdunBattleLogic.Entities.Abilities.Active.Loki.RapidAssaultAbility$$CreateBehaviour `AddEffect(0x4cd)`),
      RETIRÉ en fin de tour si l'unité a attaqué (`IdunBattleLogic.Entities.Abilities.Active.Loki.RapidAssault_RemoveExtraDamageEffectAbility$$CreateTrigger =
      `On(0x17) & UnitsAttackedThisTurn>0 & HasEffect(0x4cd)`).
    VALIDÉ live : +25% → u94→u84 3012-4524 EXACT."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        pct = trait_var("RapidAssault", "rapidAssaultExtraDmgPct")
        return for_percent_increase(True, pct) if pct is not None else None

    @property
    def removed_after_attack(self) -> bool:
        return True


class PrioritisedEfficiencyExtraDmgEffect(BaseEffect):
    """`PrioritisedEfficiency_ExtraDmg` (EffectType 0x5c9=**1481**) -- volet OFFENSIF de la stance
    « Hostile Acquisition » du trait `PrioritisedEfficiency` (1059 ; x3 Leagues of Votann :
    votanBeserk / votanIronmaster / votanUthar). #121.

    MIRROR 1:1 de `IdunBattle.Entities.Effects.Loki.PrioritisedEfficiency_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` :

        EffectBonus.ForPercentIncrease( DSLFactory.get_OwnerIsCaster,
                                        DSLFactory.ConfigConst(0xf, source@effet+0x60) )

    Le corps natif est le JUMEAU EXACT de `RapidAssault_ExtraDamage` ci-dessus (meme paire
    `get_OwnerIsCaster` + `ConfigConst(0xf)`, meme `ForPercentIncrease`) -- d'ou la meme forme de port.

    ETAGE (la question de #121) -- `ForPercentIncrease` ecrit la **%-list** du `DamageModifiers`
    ATTAQUANT (`IdunBattle.Core.Services.DamageModifiers$$Add` : `pct_list.Add(GetMultiplierFromDamageBonus(+25))`),
    consommee par `IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers` **APRES** percage/armure
    (`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`) et AVANT l'additif @+0x10.
    Ce n'est donc NI un scale des bornes d'arme/config, NI un additif : sur une cible a armure > 0 les deux
    placements different de `0.25 x armure_effective` par coup (cf. le test discriminant #121).

    CONDITIONS (lues, pas supposees) : le SEUL noeud de condition est `get_OwnerIsCaster` --
      * pas de `IsNormalAttack` -> s'applique aux attaques NORMALES **et** aux attaques d'ABILITY
        (i2 : « Deals +{[extraDmgPct]}% Damage with all attacks ») ;
      * pas de `IsMeleeAttack`/`IsRangedAttack` -> melee ET distance ;
      * pas de gate sur un trait de la cible, pas de `CreateActiveCondition`, pas de
        `CreateTargetSelector` (aucun de ces symboles n'existe pour cet effet) -> present == applique ;
      * `OwnerIsCaster` = l'effet ne compte que pour les attaques de SON PORTEUR. Il est vrai par
        construction sur ce canal (`_attacker_effect_bonuses` n'itere que les effets de l'ATTAQUANT) ;
        cote DEFENSE l'effet est muet (aucun `CreateEffectDamageMalusForDefense`) -> un Votann ATTAQUE
        ne prend PAS +25 % de degat.

    MAGNITUDE = `ConfigConst(0xf)`, PAS un litteral natif. `ConfigConst(key, source)` construit un
    `IdunBattle.Entities.Formulas.ConfigAmount` (slot constante) dont `Calculate` finit sur
    `IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(key)` de la config designee par
    `source` = le champ +0x60 de l'effet, pose par son ctor. Ce ctor est DEDUPLIQUE par IL2CPP avec
    celui de `PrioritisedEfficiency_DmgReductionEffect` (corps byte-identiques) : la table FRIDA
    attribue le RVA `f66060` a `PrioritisedEfficiency_ExtraDmgEffect..ctor` et n'a AUCUNE ligne pour
    `...DmgReductionEffect..ctor`, tandis que ghidra a pose l'etiquette `...DmgReductionEffect$$.ctor`
    sur `180f66060` -- MEME corps, deux noms. Il lit
    `BaseEffect(AbilityOrEffect(0x5ce), 1)` ou **0x5ce = 1486 = TriggeredAbilityType.PrioritisedEfficiency**
    (surtout PAS EffectType 1486 = AncestralFortune_ExtraBlockChance -- enums homonymes).
    Cote gameconfig, la config d'une triggered DERIVEE D'UN TRAIT = `globalValues.traitVariables`,
    clef `<trait camelCase> + <nom de la constante>` -> `prioritisedEfficiencyExtraDmgPct` (= 25).
    Deux precedents confirment que la clef 0xf est le generique `extraDmgPct` : `RapidAssault` 0xf ->
    `rapidAssaultExtraDmgPct` (validee live) et, symetriquement, 0x72 -> `<trait>DmgReductionPct`
    (`MartialKatah`, `PrioritisedEfficiency`). Le placeholder i2 `{[extraDmgPct]}` le corrobore.

    CYCLE DE VIE (HORS PERIMETRE #121, residu nomme) : la POSE/BASCULE de la stance vit dans
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.APrioritisedEfficiencyAbility$$GetSetOffensiveStanceBehaviour`
    (= `RemoveAllStanceEffects & AddEffect(1479 marqueur) & AddEffect(1481 CET effet) &
    AddStaticStatModifierEffectToOwner(1482 +1 Movement) & SetPersistentData(...)`), pilote par
    `...PrioritisedEfficiency_InitAbility$$CreateBehaviour` / `..._UpdateStanceAbility$$CreateBehaviour`
    -- qui dependent du substrat PERSISTENT-DATA absent du port. L'effet est donc SEEDE depuis l'etat
    live capte (`decisionView.effects`), pas encore pose par le moteur offline."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        # ConfigConst(0xf) = trait var `prioritisedEfficiencyExtraDmgPct` (= 25). Aucun autre noeud
        # de condition dans le natif -> aucun gate ici (cf. docstring).
        pct = trait_var("PrioritisedEfficiency", "prioritisedEfficiencyExtraDmgPct")
        return for_percent_increase(True, pct) if pct else None


class SmashaEadExtraDamageEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.SmashaEadEffect$$CreateEffectDamageBonusForAttack` (orksNob "Tanksmasha", ability
    SmashaEad, EffectType "SmashaEad") : `EffectBonus.ForAddition(OwnerIsCaster & IsNormalAttack,
    ConfigVar(8=extraDmg, EffectSource))` = +`extraDmg[level]` x multiplier au degat des attaques
    NORMALES du porteur — FLAT additif (PAS %, contrairement a RapidAssault).

    Placement (#69, natif LU) : `ForAddition` ecrit le champ DamageBonus (+5) de l'EffectBonus ->
    `IdunBattle.Core.Services.DamageModifiers$$Add` fait `additif @+0x10 += FromInt(v)`, applique APRES percage/armure
    par `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` (meme canal `additive` que tout ForAddition).
    Il n'existe PAS de canal additif "de base" pre-percage dans le natif -> le kind "BaseAddition"
    invente a ete retire ; le `+66` observe post-percage etait confondu par l'aura #49 + BeastSlayer.

    Effet pose par `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SmashaEadAbility$$CreateTrigger` quand le porteur a traverse >=2 hexes
    ce tour (condition d'EFFECT-CREATION, deja bakee dans l'effet materialise ; le bonus s'applique
    tant que l'effet est actif -> pas de re-gate ici). `extraDmg` in variablesAffectedByRarityBonus ->
    scale par le multiplier de l'unite. i2 : "+437 Damage" (au niveau/mult affiche). ability ACTIVE ->
    indexe activeAbilityLevel. (L'effet porte AUSSI -dmgReductionPct au degat RECU via
    `IdunBattle.Entities.Effects.Loki.SmashaEadEffect$$CreateEffectDamageMalusForDefense` = cote DEFENSE, PORTE #119 ci-dessous.)"""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        # #71 : trigger natif = OwnerIsCaster & IsNormalAttack (IdunBattle.Entities.Effects.Loki.SmashaEadEffect$$CreateEffectDamageBonusForAttack). Le noeud DSL IsNormalAttack
        # (= `IsRegularAttack(ability DECLENCHANTE)` IdunBattle.Entities.Triggers.AbilityIsNormalAttackTrigger$$ShouldTrigger/idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsRegularAttack, FALSE si pas d'ability dans le
        # contexte) evalue FALSE dans le contexte PREDICTION DISPLAY (verdict re-expert : additif absent de
        # decisionView ; off_sans ~= oracle) -> l'additif ne doit PAS entrer dans la DamageModifiers de
        # PREDICTION. En COMBAT (is_prediction=False) l'additif est applique.
        # ⚠ #68 (BUG MAGNITUDE = MULTIPLIER, RE close bit-exact) : le COMBAT live applique +300/coup exact
        # (round(extraDmg[L50]=333 x 90/100)) alors que ce port applique +599 (round(333 x 180/100)) -> SUR-
        # applique ~2x. Le niveau (50), la variable (extraDmg) et l'index (level-1) sont CORRECTS ; SEUL le
        # multiplier est faux : `self.ability_variables_multiplier=180` est le multiplier GLOBAL/primaire de
        # l'unite (UnitConfig+0x74), or la TRIGGERED SmashaEad a son PROPRE multiplier par-ability = 90
        # (`GetAbilityVariablesMultiplierPercentage(abilityId)IdunMetaLogic.UserProgress.UnitConfigUtil$$GetAbilityVariablesMultiplierPercentageForProgressionIndex` est PAR-ABILITY). Ce multiplier
        # par-ability des triggered n'est capte par AUCUN champ actuel -> fix FIDELE = nouveau capteur (tache
        # #75) ; presence CORRECTE. Test xfail test_getstuckin_combat_absolute_bit_exact -> xpass apres fix.
        if is_prediction:
            return None
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        amt = ability_var("SmashaEad", "extraDmg", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        # ForAddition -> canal `additive @+0x10` applique POST-percage (IdunBattle.Core.Services.DamageModifiers$$Add).
        return for_addition(True, amt) if amt is not None else None

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        """`IdunBattle.Entities.Effects.Loki.SmashaEadEffect$$CreateEffectDamageMalusForDefense` (cote DEFENSE, #119) :
        `EffectBonus.ForPercentDecrease(OwnerIsTarget, ConfigVar 0x46=dmgReductionPct)` — l'effet REDUIT le
        degat RECU par son porteur de `dmgReductionPct`% (i2 « takes -33% Damage » tant que l'effet actif =
        le porteur a traverse >=2 hexes ; la CONDITION est deja bakee dans la materialisation de l'effet ->
        pas de re-gate ici). Gate natif = `OwnerIsTarget` SEUL (decompile IdunBattle.Entities.Effects.Loki.SmashaEadEffect$$CreateEffectDamageMalusForDefense) -> AUCUN gate
        melee/normal : s'applique a TOUTE attaque recue. `dmgReductionPct` NON rarity-affected (BC
        `VariablesAffectedByUnitRarityMultiplier=[extraDmg]`) -> multiplier no-op (pas de bug #68 cote defense).
        #119 : reconstruit BIT-EXACT offline (Kariyan->orksNob : RapidAssault x1.25 + DEF -33% = oracle
        [1002,1745] EXACT ; sans ce malus le port sur-predisait x1.49). Meme ConfigVar 0x46 que GuardianOrganism
        (#89), mais ici un ForPercentDecrease PLAT (pas un PercentSubtractionCapped)."""
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        red = ability_var("SmashaEad", "dmgReductionPct", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        if not red:
            return None
        return for_percent_decrease(False, abs(int(red)))   # owner=defenseur (l'effet est sur la cible)


class FeederTendrilsExtraDamageEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.FeederTendrils_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` (Deathleaper,
    effet 0x4ad=1197 ; IdunBattle.Entities.Effects.Loki.FeederTendrils_ExtraDamageEffect$$.ctor = `ABondEffect(AbilityOrEffect 0x4ad)`). JUMEAU BIT-A-BIT de
    `SmashaEadExtraDamageEffect IdunBattle.Entities.Effects.Loki.SmashaEadEffect$$CreateEffectDamageBonusForAttack` avec UN gate `IsCharging` en plus :
    `EffectBonus.ForAddition(OwnerIsCaster & IsNormalAttack & IsCharging, ConfigVar(8=extraDmg, EffectSource))`.

    - MAGNITUDE = `ability_var("FeederTendrils", "extraDmg", level) x multiplier` (`ConfigVar` var index 8 =
      `extraDmg`, seule var dmg de FeederTendrils, dans `variablesAffectedByRarityBonus` ; extraDmg[L1]=10,
      [L50]=554, [L65]=728 = le « +728 Damage » i2). Multiplier = le GLOBAL de l'unite (`self.ability_variables_
      multiplier`, UnitConfig+0x74), PAS le per-ability #68 : `FeederTendrils_NormalAttack` (1120) EST l'attaque
      NORMALE de l'unite (pas une triggered) -> le multiplier standard s'applique. Aucun scaling par AbilityState
      (`IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState` ne sert qu'a indexer `level` dans `GetVariableForLevel`).
    - PLACEMENT = additif attaquant PRE-percage per-coup (canal `attacker_additive_pre`, MEME que SmashaEad #75 :
      `ForAddition` -> `IdunBattle.Core.Services.DamageModifiers$$Add`, applique par bout dans `GetDamageWithPiercing`). RE-valide
      (reconciliation MIN exacte, u87 seed 42, A=554x1.8=997/coup) : u83/u81 delta=3x997=2991 EXACT ; u85 min=
      3x339=1017 ; u79 min=718~=717 (%-list 0.8). Les MAX u79/u85 qui s'ecartent = caps HP (deja geres par
      target_limits/overkill du port). Le delta VARIE par cible via le regime percage/armure par bout, PAS via
      des stacks.
    - GATE `IsCharging` (`AverageDistanceFormula IdunBattle.Entities.Formulas.AverageDistanceFormula$$Calculate` : l'unite s'est-elle rapprochee de la cible = a-t-elle
      charge) ET `get_IsMelee` (IdunBattleLogic.Entities.Abilities.Active.Loki.FeederTendrils_NormalAttackAbility$$ExecuteBehaviour) -> l'additif n'est ACTIF qu'en attaque MELEE de CHARGE (deplacement au
      contact). En prediction-display les tuiles d'attaque rankees SONT des tuiles de charge -> gate TRUE (les 4
      samples portent l'additif). Contrairement a SmashaEad, PAS de `if is_prediction: return None` : ici
      IsNormalAttack=TRUE (c'est l'attaque normale de l'unite, incluse dans decisionView).
    ⚠ A confirmer live (validator, quand un slot runner se libere) : niveau/mult reels de u87 (infere L50/mult1.8) ;
    cas NEGATIF IsCharging (attaque sans deplacement -> additif doit DISPARAITRE) non teste par les 4 samples."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        if is_ranged:                       # IsCharging & get_IsMelee (IdunBattleLogic.Entities.Abilities.Active.Loki.FeederTendrils_NormalAttackAbility$$ExecuteBehaviour) -> melee uniquement
            return None
        if is_normal_attack is False:       # IsNormalAttack (IdunBattleLogic.Entities.DSLFactory$$IsNormalAttack)
            return None
        if has_moved is False:              # IsCharging (IdunBattleLogic.Entities.DSLFactory$$IsCharging) : charge = deplacement vers la cible
            return None                     # (has_moved None = inconnu -> applique, cas prediction-display)
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        amt = ability_var("FeederTendrils", "extraDmg", lvl,
                          multiplier_pct=self.ability_variables_multiplier)  # GLOBAL (pas per-ability #68)
        return for_addition(True, amt) if amt is not None else None


class AvalancheOfMuscleExtraDamageEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.AvalancheOfMuscleTargetEffect$$CreateEffectDamageBonusForAttack` (astraBullgryn passif
    AvalancheOfMuscle, AstraMilitarum ; effet EffectType 1025 "AvalancheOfMuscle_ExtraDamage" ; IdunBattle.Entities.Effects.Loki.AvalancheOfMuscleTargetEffect$$.ctor = `ABondEffect(AbilityOrEffect 0x404=1028)`). JUMEAU de `FeederTendrilsExtraDamageEffect
    IdunBattle.Entities.Effects.Loki.FeederTendrils_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` avec UNE difference : PAS de noeud `IsNormalAttack`.
    `EffectBonus.ForAddition(OwnerIsCaster & IsCharging, ConfigVar(8=extraDmg, GetAbilityState, EffectSource))`.

    RE (decompile = verite) : les callees de IdunBattle.Entities.Effects.Loki.AvalancheOfMuscleTargetEffect$$CreateEffectDamageBonusForAttack = {get_OwnerIsCaster, IsCharging, op_BitwiseAnd,
    GetAbilityState, ConfigVar, Nullable.ctor} -> DEUX noeuds trigger SEULEMENT (OwnerIsCaster & IsCharging).
    `IsNormalAttack` (present chez FeederTendrils) est ABSENT ici -> le bonus s'applique a TOUTE attaque du
    porteur en CHARGE, pas seulement l'attaque normale. Le `ForAddition` est inline (le compilo l'a fondu :
    ConfigVar ecrite au champ additif +0x10 = param_1[2], meme layout que IdunBattle.Entities.Effects.EffectBonus$$ForAddition),
    donc canal ADDITIF identique a FeederTendrils/SmashaEad (`IdunBattle.Core.Services.DamageModifiers$$Add`, applique
    par coup PRE-percage cote combat, canal `attacker_additive_pre`).

    - MAGNITUDE = `ability_var("AvalancheOfMuscle", "extraDmg", level) x multiplier` (`ConfigVar` var index 8 =
      `extraDmg`, SEULE var de l'ability, dans `variablesAffectedByRarityBonus` ; extraDmg[L1]=6, [L65]=437).
      `IdunBattleLogic.Entities.Abilities.Active.Loki.AvalancheOfMuscleAbility$$GetExtraDamage` = `AbilityConfiguration.GetVariableForLevel(config, 8, ...)` sur le config de
      `AvalancheOfMuscleAbility` (le PASSIF du porteur) -> level = niveau passif d'astraBullgryn (cascade
      active_ability_level -> ability_level -> level, comme FeederTendrils). Multiplier = le GLOBAL de l'unite
      (`self.ability_variables_multiplier`) : AvalancheOfMuscle est un PASSIF (pas une triggered) -> a VALIDER
      live que le multiplier global est le bon (piege #68/#75 per-ability vs global).
    - GATE `IsCharging` (`AverageDistanceFormula IdunBattle.Entities.Formulas.AverageDistanceFormula$$Calculate` via `IdunBattleLogic.Entities.DSLFactory$$IsCharging` : l'unite
      s'est-elle rapprochee de la cible = a-t-elle charge). astraBullgryn est MELEE-only (aucune attaque
      ranged) -> le gate `is_ranged` est un no-op ; conserve pour rester le calque strict de FeederTendrils
      (meme noeud IsCharging). Cote combat `has_moved = unit_has_moved(state, unit_id)` = flag natif
      `UnitFlag.Moved` (proxy de charge) ;
      en prediction-display les tuiles rankees sont des tuiles de charge -> has_moved None/True -> gate TRUE.
    - PAS de `is_normal_attack` gate (contrairement a FeederTendrils) : le natif n'a PAS le noeud IsNormalAttack."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        if is_ranged:                       # IsCharging melee (astraBullgryn melee-only ; calque FeederTendrils)
            return None
        if has_moved is False:              # IsCharging (IdunBattleLogic.Entities.DSLFactory$$IsCharging) : charge = deplacement vers la cible
            return None                     # (has_moved None = inconnu -> applique, cas prediction-display)
        # PAS de gate is_normal_attack : IdunBattle.Entities.Effects.Loki.AvalancheOfMuscleTargetEffect$$CreateEffectDamageBonusForAttack n'a AUCUN noeud IsNormalAttack (RE decompile).
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        amt = ability_var("AvalancheOfMuscle", "extraDmg", lvl,
                          multiplier_pct=self.ability_variables_multiplier)  # GLOBAL (pas per-ability #68)
        return for_addition(True, amt) if amt is not None else None


class DecoysAndMisdirectionExtraDamageEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.DecoysAndMisdirection_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` (Genestealer
    Cults ability DecoysAndMisdirection 0x518=1304, effet 0x563=1379 "DecoysAndMisdirection_ExtraDamage") :
    `EffectBonus.ForAddition(OwnerIsCaster, ConfigVar(8=extraDmg, EffectSource))` = +`extraDmg[level]` x
    multiplier au degat de TOUTES les attaques du porteur (l'ami buffe) -- FLAT additif, meme canal
    `additive @+0x10` que SmashaEad (IdunBattle.Core.Services.DamageModifiers$$Add, applique POST-percage par
    IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers).

    Pose sur un ami quand un decoy est spawn a cote de lui / quand un ami se deplace sur un decoy (i2 :
    « it deals +582 Damage until the end of its turn »). IdunBattle.Entities.Effects.Loki.DecoysAndMisdirection_ExtraDamageEffect$$.ctor : EffectSource = AbilityOrEffect
    0x518 (DecoysAndMisdirection) -> extraDmg indexe sur le niveau de CETTE ability du SOURCE (genesPrimus).

    DIFFERENCE cle vs SmashaEad (#71) : le gate natif est `get_OwnerIsCaster` SEUL (IdunBattle.Entities.Effects.Loki.DecoysAndMisdirection_ExtraDamageEffect$$CreateEffectDamageBonusForAttack decompile :
    AUCUN noeud IsNormalAttack ni IsMeleeAttack). OwnerIsCaster est TRUE des que le porteur attaque (ce
    chemin n'est appele QUE pour les attaques du porteur) -> l'additif s'applique en PREDICTION comme en
    COMBAT (contrairement a SmashaEad dont IsNormalAttack evalue FALSE en display-prediction, #71).
    Comportement = Neuroparasite (#88, additif present dans decisionView).

    extraDmg in variablesAffectedByRarityBonus (=[minDmg,maxDmg,extraDmg]) -> scale x multiplier de l'unite.
    ⚠ Validator traps (spec #134) : (1) multiplier GLOBAL de l'unite vs per-ability du passif (cf. bug
    #68/#75 SmashaEad ; ici passif 1304, per-ability non capte -> defaut global self.ability_variables_
    multiplier, a valider live) ; (3) niveau/multiplier = ceux du SOURCE (genesPrimus), pas du buffe (comme
    RitesOfBattle aura). extraDmg[L1..65]=[8..582]. VALIDATION live PENDING (build genesPrimus -> Decoy ->
    ami buffe attaque -> aiPredict/decisionView additif +extraDmg)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        # Gate natif = OwnerIsCaster SEUL (IdunBattle.Entities.Effects.Loki.DecoysAndMisdirection_ExtraDamageEffect$$CreateEffectDamageBonusForAttack) : aucun re-gate is_ranged/is_normal/is_prediction.
        # Ce chemin n'est appele que pour les attaques du porteur -> OwnerIsCaster implicitement TRUE.
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        amt = ability_var("DecoysAndMisdirection", "extraDmg", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        # ForAddition -> canal `additive @+0x10` applique POST-percage (IdunBattle.Core.Services.DamageModifiers$$Add).
        return for_addition(True, amt) if amt is not None else None


class LordOfTempestsExtraDamageEffect(BaseEffect):
    """`LordOfTempests_ExtraDamageEffect` (Effects.Loki, EffectType 0x4d4=1236, nom capté
    "LordOfTempests_ExtraDamage" — passif de Njal spaceStormcaller). i2 : « Njal's normal attacks deal
    +237 Damage for each hex surrounding him that is covered in Ice. » (#29, lead 1 agreement-stages).

    - hexes `IdunBattle.Entities.Effects.Loki.LordOfTempests_ExtraDamageEffect$$GetHexesIncreasingDamage` : `EntitiesWithAnyEffect(SurroundingTiles(owner, 0, 1),
      0x11, domain Tiles)` = les tuiles du RING-1 du caster porteuses de l'effet **Ice** — le CENTRE ne
      compte PAS (vérifié bit-exact seed 31337 s18 : (2,4) elle-même glacée -> count=3 = ring-1 seul).
    - dégât `IdunBattle.Entities.Effects.Loki.LordOfTempests_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` : `EffectBonus.ForAddition(get_OwnerIsCaster,
      Multiply(ConfigVar(8=extraDmg, GetAbilityState(effet)), Count(hexes)))` — FLAT additif, canal
      standard `IdunBattle.Core.Services.DamageModifiers$$Add` appliqué PAR COUP (comme SmashaEad/BeaconOfRage).
    - condition d'activité `IdunBattle.Entities.Effects.Loki.LordOfTempests_ExtraDamageEffect$$CreateActiveCondition` : `AmountIsGreaterThanZero(Count(hexes))`
      (l'effet n'est « actif » que s'il y a >=1 hex glacé adjacent — évalué à la POSITION COURANTE par
      le natif ; côté port la magnitude re-count par POSITION CANDIDATE rend ce gate redondant : count=0
      -> bonus None).
    - POSITION-DÉPENDANT : la chaîne display threade la UnitPosition CANDIDATE de bout en bout (#153) ->
      le count se fait autour de la TUILE D'ATTAQUE évaluée (`att_ctx["att_pos"]`), PAS la position
      réelle. VALIDÉ BIT-EXACT (seed 31337 s18, u89 Njal -> u81 Mephiston, extraDmg[50]x180%=400/hex,
      3 hits) : à (3,3) 1 hex glacé -> (642+400)x3 = 3126-4092 == natif ; à (2,4) 3 hexes ->
      (642+1200)x3 = 5526-6492 == natif (aiPlaybookPredict col/row).
    - MAGNITUDE : `extraDmg[ablvl passif] x multiplier` (variables LordOfTempests, [L1..65]=[3..237],
      in variablesAffectedByRarityBonus -> scale x mult ; u89 : 222x1.8=400). i2 « +237 » = extraDmg[65].
    - gate `is_normal_attack` : l'i2 dit « normal attacks » — **MESURÉ LIVE (#217, probe_217 B)** :
      cast Stormcaller (1113) avec l'effet ACTIF pré-cast (1 hex glacé ring-1, hydraté) et 3 hexes
      glacés ring-1 à l'instant de l'attaque -> le natif applique **+0** (offline sans gate aurait mis
      +extraDmg x 3 par coup ; l'écart mesuré était exactement 3600 = 400x3x3 hits). Le natif n'applique
      donc PAS ce bonus aux attaques d'ABILITY (le trigger-flag struct @param_2+0x14 reste non décodé au
      bit près, mais son EFFET est mesuré = gate normal-only). Côté combat le vecteur ability threade
      `is_normal_attack=False` (`execute_ability_attack` -> `attacker_modifiers`, #217).
    - La 2e moitié du passif (« each enemy hit covers its hex in Ice ») =
      `LordOfTempests_AddIceAbility.CreateBehaviour/CreateTrigger IdunBattleLogic.Entities.Abilities.Triggered.Loki.LordOfTempests_AddIceAbility$$CreateBehaviour/IdunBattleLogic.Entities.Abilities.Triggered.Loki.LordOfTempests_AddIceAbility$$CreateTrigger` (face RUNTIME,
      arbre DSL AddEffect tile-domain) — PORTÉE #35 (`runner/operations/triggers/loki/lord_of_tempests.py`,
      case-35) : le runner pose la glace en simulant ; la prédiction lit la glace DÉJÀ posée (tileMeta
      frais), elle n'en pose pas. Côté COMBAT runner l'att_ctx positionnel vient de
      `damage_model._positional_att_ctx` (state.effects tuiles), symétrique du tileMeta."""

    ICE_TILE_EFFECT = "Ice"   # nom d'effet de tuile capté (tileMeta.effects[].name, vérifié live 31337)

    def get_hexes_increasing_damage(self, att_ctx) -> int:
        """`IdunBattle.Entities.Effects.Loki.LordOfTempests_ExtraDamageEffect$$GetHexesIncreasingDamage` -> COUNT des tuiles ring-1 (centre EXCLU) autour de la
        position d'attaque candidate porteuses de l'effet Ice. att_ctx None / sans données -> 0."""
        c = att_ctx or {}
        pos = c.get("att_pos")
        tfx = c.get("tile_effects_by_pos")
        if pos is None or not tfx:
            return 0
        import hexgeo
        return sum(1 for p, names in tfx.items()
                   if names and self.ICE_TILE_EFFECT in names and hexgeo.distance(pos, p) == 1)

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        if is_normal_attack is False:        # i2 : « normal attacks » (gate conservateur, cf. docstring)
            return None
        count = self.get_hexes_increasing_damage(att_ctx)
        if count <= 0:                       # ActiveCondition AmountIsGreaterThanZero(Count) -> inerte
            return None
        lvl = (self.ability_level if self.ability_level is not None else self.level)
        per = ability_var("LordOfTempests", "extraDmg", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        if not per:
            return None
        # Multiply(ConfigVar(extraDmg), Count) -> ForAddition = canal additif PAR COUP standard.
        return for_addition(True, int(per) * int(count))


class CrushingStrikeEffect(BaseEffect):
    """`CrushingStrikeEffect` (Effects.Loki, effet 0x4a2=1186 ; IdunBattle.Entities.Effects.Loki.CrushingStrikeEffect$$.ctor, base
    `ADamageDefenseModifierAbilityEffect`).
    - dégât `IdunBattle.Entities.Effects.Loki.CrushingStrikeEffect$$CreateDamageModifier : `ForPercentIncrease(OwnerIsCaster & IsNormalAttack &
      IsMeleeAttack, ConfigConst key 0xf)` = trait var `crushingStrikeExtraDmgPct` (=50, constante
      plate via `AbilityConfiguration.GetNumberConstant` — cf. `IdunBattle.Entities.Formulas.ConfigAmount$$Calculate` —
      NON rarity-scalée).
    - condition d'activité `IdunBattle.Entities.Effects.Loki.CrushingStrikeEffect$$CreateActiveCondition : NOT HasFlag(HasMoved) (« if it has
      not moved this turn ») — en PRÉDICTION la tuile candidate fixe le flag (`has_moved`), en COMBAT le
      flag natif `UnitFlag.Moved` du `UnitFlagsComponent` (`components.unit_has_moved`, #60/#101).
    VALIDÉ live #98 (darkaTerminator u80→u78 seed777 roster1) : préd depuis (6,6) not-moved elev2>1
    = ×2.25 = CrushingStrike(×1.5) × ÉlévationBonus(×1.5) [composition %-list multiplicative] ;
    depuis les tuiles déplacées (elev égale) = ×1.0 EXACT (5307,7959)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        if not is_melee_attack(is_ranged):       # gated IsMeleeAttack (IdunBattle.Entities.Effects.Loki.CrushingStrikeEffect$$CreateDamageModifier)
            return None                          # #106 : nature NON prouvee melee -> gate FAUX (mirror BattleQuery)
        if is_normal_attack is False:            # gated IsNormalAttack (spéciale mêlée → pas de bonus)
            return None
        if has_moved:                            # ActiveCondition NOT HasFlag(HasMoved) (IdunBattle.Entities.Effects.Loki.CrushingStrikeEffect$$CreateActiveCondition)
            return None
        pct = trait_var("CrushingStrike", "crushingStrikeExtraDmgPct")
        return for_percent_increase(True, pct) if pct is not None else None


class HeavyWeaponExtraDmgEffect(BaseEffect):
    """`HeavyWeapon_ExtraDmgEffect` (effet 1008 ; ctor `DamageModifierAbilityEffect(0x3e9)`).
    - dégât `IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier : `EffectBonus.ForPercentIncrease(cond, amount)` où
      `amount = ConditionalAmount(TriggeringAbilityIs(AbilityOrEffect(0x3ec=1004 MortisRound)) ?
      Multiply(base, Direct(2)) : base)`, `base = ConfigConst key 0xf` = trait var `heavyWeaponExtraDmg`
      (=25, scalaire) ; condition = `OwnerIsCaster & IsRangedAttack & ((F@0xa0 & !HasFlag(TurnFinished=3))
      | !F@0xa0) & (!HasFlag(Moved=0) | HasFlag(Teleported=0xc))`. ⇒ **+25% de dégât sur les attaques
      RANGED** (normale, overwatch ET ability — le gate est IsRangedAttack, PAS IsNormalAttack), **x2
      (+50%) quand l'ability déclenchante est MortisRound** (0x3ec est le SEUL id du décompilé ; i2
      « The Heavy Weapon trait applies double to this ability » n'existe que sur MortisRound, #47).
      L'ability déclenchante est lue du contexte d'attaque per-coup -> `att_ctx["trigger_ability_type"]`
      (threadé par `execute_ability_attack` via `attacker_modifiers`) ; attaque normale/overwatch/clé
      absente -> branche base.
    Porté par le trait HeavyWeapon (qui accorde aussi l'Overwatch) → s'applique au tir d'overwatch."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        if not is_ranged_attack(is_ranged):      # gated IsRangedAttack (no-op sur mêlée / contexte inconnu)
            return None                          # #106 : foyer unique du predicat (mirror BattleQuery)
        # Gate NO-MOVE (`!HasFlag(HasMoved=0)` IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier ; i2 : « When this unit has not moved this
        # turn »). En PRÉDICTION la tuile candidate fixe le flag : has_moved=True (candidat avec
        # déplacement) → pas de bonus (GROUND TRUTH step-23 : rangées ranged u78 SANS ×1.25 depuis les
        # tuiles déplacées ; step-11 : « ×1.25 selon tuile »). En COMBAT (#60/#101) l'état est lu SUR LE
        # FLAG NATIF (`components.unit_has_moved` = `UnitFlagsComponent.Has(unit, UnitFlag.Moved)`, posé
        # par `set_moved_flag` dans MoveUnitOperation) -> `attacker_modifiers` passe un bool défini : le
        # bonus s'annule si l'unité a bougé ce tour. None (contexte hors combat/prédiction) → bonus
        # appliqué (fallback). ⚠ Un état rechargé par `load_state` NE connaît PAS le flag (aucun RPC ne
        # l'expose) : une fixture qui SAIT que le caster a bougé doit poser le flag (cf. tests live).
        if has_moved:
            return None
        pct = trait_var("HeavyWeapon", "heavyWeaponExtraDmg")
        if pct is None:
            return None
        # #47 : branche `ConditionalAmount(TriggeringAbilityIs(0x3ec=1004), Multiply(base, Direct(2)),
        # base)` du décompilé IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier — amount DOUBLÉ (+50%) quand le coup est déclenché par
        # MortisRound. `trigger_ability_type` = l'AbilityOrEffect du coup, présent seulement sur le
        # vecteur ABILITY (execute_ability_attack) ; absent (attaque normale/overwatch) = branche base.
        if att_ctx and att_ctx.get("trigger_ability_type") == int(ActiveAbilityType.MortisRound):
            pct = pct * 2                        # Multiply(base, Direct(2))
        return for_percent_increase(True, pct)


class RangedSpecialistEffect(BaseEffect):
    """`RangedSpecialistEffect` (trait RangedSpecialist — i2 : « If this unit did not start its turn
    adjacent to an enemy unit, it deals +33% Damage with ranged attacks »).
    - dégât IdunBattle.Entities.Effects.Loki.RangedSpecialistEffect$$CreateEffectDamageBonusForAttack : `EffectBonus.ForPercentIncrease((OwnerIsCaster & IsRangedAttack &
      !TriggeringAbilityIs(0x434)) | (branche 0x434 overwatch), Get(ConfigConst 0xf))` =
      **+rangedSpecialistDmgPct% sur les attaques RANGED** (toutes tuiles — la condition « pas parti
      adjacent » est l'état ACTIF de l'effet, reflété par la capture isActive, PAS un gate de tuile).
    MAGNITUDE : `traitVariables.rangedSpecialistDmgPct` = 33. GROUND TRUTH step-8 seed777 :
    u80→u94 ranged natif = moteur ×1.33 exact (per-coup 534 = round(401×1.33)), mêlée intacte."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        if not is_ranged_attack(is_ranged):      # gated IsRangedAttack (IdunBattle.Entities.Effects.Loki.RangedSpecialistEffect$$CreateEffectDamageBonusForAttack)
            return None                          # #106 : foyer unique du predicat (mirror BattleQuery)
        pct = trait_var("RangedSpecialist", "rangedSpecialistDmgPct")
        return for_percent_increase(True, pct) if pct is not None else None


# Traits cible gatant BeastSlayer_ExtraDmg (natif `HasTrait(target, X)`) : UnitTrait.BigTarget=1017(0x3f9),
# UnitTrait.Vehicle=1029(0x405) (dump.cs #146 ; l'ancien commentaire INVERSAIT les hex). Code gate par NOM,
# noms gameconfig confirmes (unit_map find --trait BigTarget/Vehicle).
_BEAST_SLAYER_TARGET_TRAITS = frozenset({"BigTarget", "Vehicle"})


class BeastSlayerExtraDmgEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.BeastSlayer_ExtraDmgEffect$$CreateDamageModifier` (trait BeastSlayer, effet
    `BeastSlayer_ExtraDmg`) : `ForPercentIncrease(ConfigConst 0xf = beastSlayerExtraDmgPct=20)` gate
    `OwnerIsCaster & IsMeleeAttack & (HasTrait(target, BigTarget=1017) | HasTrait(target, Vehicle=1029))`.
    => +20% de degat MELEE vs Big Targets / Vehicles (i2). Variable de TRAIT -> globale, NON scalee.
    `target_traits` = noms de traits de la CIBLE ; None (contexte sans cible : prediction generique,
    trigger, ability/splash melee) -> pas de bonus (cible inconnue -> "present != applique").
    Cf. docs/rl/case-68-orksnob-attacker-effects.md."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        if not is_melee_attack(is_ranged):             # IsMeleeAttack -> melee uniquement
            return None                                # #106 : nature NON prouvee melee -> gate FAUX
        if not target_traits or _BEAST_SLAYER_TARGET_TRAITS.isdisjoint(target_traits):
            return None                                # cible ni BigTarget ni Vehicle -> 0
        pct = trait_var("BeastSlayer", "beastSlayerExtraDmgPct")
        return for_percent_increase(True, pct) if pct is not None else None


class MartialKatahDmgBonusEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.MartialKatah_DmgBonusEffect$$CreateEffectDamageBonusForAttack` (trait MartialKatah,
    Custodes ex. custoBladeChampion/custoTrajann) : `EffectBonus.ForPercentIncrease(OwnerIsCaster &
    HasTrait(target, Summon=2), Direct(GetNumberConstant cfg 0xf = martialKatahExtraDmgPct=100))`.
    => +100% de dégât vs SUMMONS — AUCUN gate mêlée/ranged/normal (i2 « all attacks against Summons »),
    et APPLIQUÉ en prédiction display (validé live #57d : NAT[cand] = off ×2 exact, 1357 s18 u81→u168
    Bloodletter Summon [15174,22752]). Variable de TRAIT → globale, NON scalée (cf. BeastSlayer).
    (Le -20% défenseur du même trait = MartialKatahDmgReductionEffect, canal défense, #105.)"""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        if not target_traits or "Summon" not in target_traits:
            return None                               # HasTrait(target, UnitTrait.Summon=2)
        pct = trait_var("MartialKatah", "martialKatahExtraDmgPct")
        return for_percent_increase(True, pct) if pct is not None else None


class CondemnorStakeExtraDmgEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.CondemnorStake_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` (adeptCanoness
    <<Roswitha>> passif CondemnorStake, Sisterhood/Imperial ; effet EffectType 1076 "CondemnorStake_ExtraDmg" ;
    IdunBattle.Entities.Effects.Loki.CondemnorStake_ExtraDmgEffect$$.ctor = `BaseEffect(AbilityOrEffect 0x42e=1070=CondemnorStake)`). JUMEAU de
    `AvalancheOfMuscleExtraDamageEffect IdunBattle.Entities.Effects.Loki.AvalancheOfMuscleTargetEffect$$CreateEffectDamageBonusForAttack` avec UNE difference : le noeud `IsCharging` est remplace
    par `HasTrait(target, Psyker)`.
    `EffectBonus.ForAddition(OwnerIsActor & HasTrait(target, 0x3ea=1002=Psyker),
    ConfigVar(8=extraDmg, GetAbilityState, EffectSource))`.

    RE (decompile = verite, IdunBattle.Entities.Effects.Loki.CondemnorStake_ExtraDmgEffect$$CreateEffectDamageBonusForAttack) : les callees = {GetAbilityState, ConfigVar, get_OwnerIsActor,
    HasTrait(*(factory+0x178)=target, 0x3ea, ...), op_BitwiseAnd, Nullable.ctor} -> DEUX noeuds trigger
    (OwnerIsActor & HasTrait(target, Psyker)). AUCUN noeud IsCharging / IsNormalAttack / IsMeleeAttack /
    IsRangedAttack -> le bonus s'applique a TOUTE attaque du porteur (normale ET ability, melee ET ranged)
    CONTRE une cible Psyker. Le `ForAddition` est inline (ConfigVar ecrite au champ additif, meme layout que
    AvalancheOfMuscle/SmashaEad IdunBattle.Entities.Effects.EffectBonus$$ForAddition) -> canal ADDITIF identique (IdunBattle.Core.Services.DamageModifiers$$Add,
    applique par coup, canal `attacker_additive_pre`).

    - `IdunBattleLogic.Entities.DSLFactory$$get_OwnerIsActor` (owner@0x148 vs actor@0x158) vs `IdunBattleLogic.Entities.DSLFactory$$get_OwnerIsCaster`
      (owner@0x148 vs caster@0x160) : trigger d'identite "l'owner est l'acteur/le caster". Ce chemin
      `CreateEffectDamageBonusForAttack` n'est appele QUE pour l'attaque du PORTEUR -> OwnerIsActor est
      implicitement TRUE (== traitement OwnerIsCaster/OwnerIsActor de DecoysAndMisdirection/SpotterReworked).
    - GATE CIBLE `HasTrait(target@0x178, 0x3ea=1002=Psyker)` : la cible porte-t-elle le trait Psyker.
      Porte via `target_traits` (== BeastSlayer/MartialKatah/DaughterOfTheAbyss) : cible sans Psyker /
      contexte sans cible (target_traits None) -> pas de bonus ("present != applique"). GAP infra PARTAGE
      (non specifique a ce port) : `target_traits` n'est threade QUE sur le chemin d'attaque NORMALE
      (damage.py:400) -> le bonus n'entre PAS sur les attaques d'ABILITY (ex. BrazierOfHolyFire) -- MEME
      limite que BeastSlayer/MartialKatah. adeptCanoness s'observe sur ses attaques NORMALES (Chain melee +
      Bolter ranged) vs Psyker.
    - MAGNITUDE = `ability_var("CondemnorStake", "extraDmg", level) x multiplier` (ConfigVar var index 8 =
      `extraDmg`, SEULE var de l'ability, per-niveau [30(L1)..2183(L65)], DANS variablesAffectedByRarityBonus
      -> scale x multiplier). `GetVariableForLevel(config, 8, GetAbilityState)` sur le config de CondemnorStake
      (le PASSIF) -> level = niveau passif d'adeptCanoness (cascade active_ability_level -> ability_level ->
      level, comme AvalancheOfMuscle). Multiplier = le GLOBAL de l'unite (`self.ability_variables_multiplier`) :
      passif (pas triggered) -> a VALIDER live que le multiplier global est le bon (piege #68/#75). i2 "+2183
      Damage" = extraDmg[L65] base (NE PAS hardcoder 2183, lu de gameconfig).
    - PAS de gate is_ranged / is_normal / is_charging : IdunBattle.Entities.Effects.Loki.CondemnorStake_ExtraDmgEffect$$CreateEffectDamageBonusForAttack n'a AUCUN autre noeud (RE decompile)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        # GATE CIBLE HasTrait(target, 0x3ea=1002=Psyker) (IdunBattle.Entities.Effects.Loki.CondemnorStake_ExtraDmgEffect$$CreateEffectDamageBonusForAttack). Cible non-Psyker / cible inconnue
        # (target_traits None : chemins ability/prediction generique) -> pas de bonus.
        if not target_traits or "Psyker" not in target_traits:
            return None
        # OwnerIsActor implicitement TRUE (chemin appele uniquement pour l'attaque du porteur). PAS de gate
        # is_ranged / is_normal / is_charging : IdunBattle.Entities.Effects.Loki.CondemnorStake_ExtraDmgEffect$$CreateEffectDamageBonusForAttack n'a AUCUN autre noeud trigger (RE decompile).
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        amt = ability_var("CondemnorStake", "extraDmg", lvl,
                          multiplier_pct=self.ability_variables_multiplier)  # GLOBAL (pas per-ability #68)
        return for_addition(True, amt) if amt is not None else None


class BeaconOfRageExtraDamageEffect(BaseEffect):
    """`BeaconOfRage_ExtraDamageEffect` (EffectType 0x512=1298, nom capté "BeaconOfRage_ExtraDamage" ;
    AbilityOrEffect 0x4d4=1236 = BeaconOfRage, passive d'Azkor worldEightbound) — i2 : « For each time
    he was attacked in battle, up to a maximum of 8 times, Azkor deals +315 Damage » (+315 = extraDmg
    au niveau max 65). #189.

    - dégât `IdunBattle.Entities.Effects.Loki.BeaconOfRage_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` : `ForAddition(get_OwnerIsCaster,
      Multiply(ConfigVar(8=extraDmg, GetAbilityState(effet)), EffectLevel(effet)))` — bonus FLAT
      additif (AUCUN ForPercent*), trigger OwnerIsCaster SEUL (tous profils, normale ET spéciale) ;
      même canal additif que SmashaEad (#69 : `DamageModifiers` additif, appliqué par
      `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`).
    - niveau de RAGE = `EffectLevel` de l'instance = `min(TotalTimesAttacked, nrOfAttacks=8)` :
      `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ABeaconOfRageAbility$$GetCurrentSelfEffectLevel` = `Min(TotalTimesAttacked(unit),
      ConfigConst(0x59=nrOfAttacks))`, écrit par `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ABeaconOfRageAbility$$GetUpdateSelfEffectBehaviour`
      (`AddEffect(0x512)` si absent & level>0, puis `SetEffectLevel(0x512, level)`) → arrive tel quel
      dans decisionView.effects[].level (Level @0x68). PAS de re-calcul offline : le level capté EST
      la vérité (le cap est appliqué à l'ÉCRITURE par le natif ; TotalTimesAttacked non capté).
    - magnitude : `extraDmg[abilityLevel]` (variables BeaconOfRage, 1→315 sur 65 niveaux, HORS
      variablesAffectedByRarityBonus → pas de scaling multiplier) × level. `ability_level` = niveau
      PASSIF du porteur (Scene ablvl_by_id) ; niveau inconnu → inerte (dégradation fidèle).

    La variante `BeaconOfRage_FriendlyExtraDamage` (0x513=1299 : 50% du bonus, attaques MÊLÉE des
    amis Chaos adjacents, gate `OwnerIsCaster & IsMeleeAttack`, `PercentageOf(..., 50) IdunBattle.Entities.Effects.Loki.BeaconOfRage_FriendlyExtraDamageEffect$$CreateEffectDamageBonusForAttack`,
    active SSI le porteur a ≥1 kill — `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ABeaconOfRageAbility$$GetCurrentFriendEffectLevel = If(UnitsDefeated-
    Amount>0, selfLevel, 0)`) = effet-aura SÉPARÉ (`BeaconOfRageFriendlyExtraDamageEffect`)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        # trigger natif IdunBattle.Entities.Effects.Loki.BeaconOfRage_ExtraDamageEffect$$CreateEffectDamageBonusForAttack = get_OwnerIsCaster SEUL — tous profils, normale ET spéciale.
        rage = self.level                              # EffectLevel (stack), déjà cappé à l'écriture
        if not rage or int(rage) <= 0:
            return None
        if self.ability_level is None:                 # ConfigVar sans AbilityState → pas de magnitude
            return None
        per = ability_var("BeaconOfRage", "extraDmg", self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        if not per:
            return None
        return for_addition(True, int(per) * int(rage))


class TerrifyingCrescendoExtraDmgEffect(BaseEffect):
    """`TerrifyingCrescendo_ExtraDmgEffect` (EffectType 0x590=1424, nom capte "TerrifyingCrescendo_ExtraDmg" ;
    passif triggered TerrifyingCrescendo 0x59b=1435 d'emperNoiseMarine <<Shiron>>, EmperorsChildren/Chaos) —
    i2 : << Shiron's ranged attacks deal +218 Damage for each time he Overkilled or would have Suppressed an
    enemy unit, up to a maximum of 6 times. >> #204. JUMEAU STRUCTUREL de BeaconOfRage (meme
    Multiply(ConfigVar(8=extraDmg), EffectLevel)) avec UNE difference : le gate IsRangedAttack.

    - degat `IdunBattle.Entities.Effects.Loki.TerrifyingCrescendo_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` : `EffectBonus.ForAddition(IsRangedAttack &
      OwnerIsCaster, GetCurrentExtraDamage())` = bonus FLAT additif (AUCUN ForPercent*), meme canal additif
      que BeaconOfRage/SmashaEad (`IdunBattle.Core.Services.DamageModifiers$$Add`, applique par coup). SEULE difference vs
      BeaconOfRage IdunBattle.Entities.Effects.Loki.BeaconOfRage_ExtraDamageEffect$$CreateEffectDamageBonusForAttack (OwnerIsCaster seul) : le noeud DSL `IsRangedAttack` IdunBattle.Entities.Effects.Loki.TerrifyingCrescendo_ExtraDmgEffect$$CreateEffectDamageBonusForAttack (donc le bonus
      est ABSENT des attaques MELEE / des attaques d'ability non-ranged du porteur).
    - `IdunBattle.Entities.Effects.Loki.FuelledByFury_ExtraDamageEffect$$GetCurrentExtraDamage` (HERITE de FuelledByFury_ExtraDamageEffect ; refcount 10) =
      `Multiply(ConfigVar(8=extraDmg, GetAbilityState(effet)), EffectLevel(effet))`. extraDmg = variables
      TerrifyingCrescendo, 3 (L1) -> 218 (L65), DANS variablesAffectedByRarityBonus -> scale x multiplier
      de l'unite (contrairement a BeaconOfRage dont extraDmg est HORS rarityBonus = mult no-op). i2 << +218 >>
      = extraDmg[L65].
    - niveau de CRESCENDO = `EffectLevel` de l'instance, cappe a `buffMaxLevel=6` (constants). Accumulation
      `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateTrigger` = disjonction :
        (branche 1) `On(0) & OwnerIsActor & TargetIsOverkilled`  = le porteur OVERKILL une cible ;
        (branche 2) `On(0x3e=62) & OwnerIsActor & TriggeringEffectIs(0x429=1065)` = le porteur POSE
                    l'effet Pinned/Suppressed (0x429=1065, applique par le trait SuppressiveFire a chaque
                    ennemi touche en ranged) = << would have Suppressed >>.
      `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateBehaviour` = `AddEffectOrIncreaseLevel(0x590, stateRef, ..., Direct(GetNumberConstant
      (cfg, 0x62)))` = +1 stack par declenchement (Direct d'une constante), plafonne a buffMaxLevel=6. Le
      level cappe arrive TEL QUEL dans decisionView.effects[].level (comme BeaconOfRage IdunBattleLogic.Entities.Abilities.Triggered.Loki.ABeaconOfRageAbility$$GetUpdateSelfEffectBehaviour) -> on lit
      `self.level` sans re-calcul offline (le natif enforce le cap A L'ECRITURE ; le compteur de triggers
      n'est pas capte). Un tir ranged qui touche & overkill peut incrementer 2x (suppress + overkill) dans
      le meme evenement -- le compteur, pas le port : on lit le level abouti.
    - magnitude : `extraDmg[abilityLevel PASSIF] x multiplier x level`. `ability_level` = niveau du passif
      du porteur (Scene ablvl_by_id = passive_ability_level) ; niveau/level inconnu -> inerte (degradation
      fidele). VALIDE live #204 (probe_204_crescendo : native ranked per-tuile == offline pour L=0..6 stacks,
      cas 0-stack inclus ; controle melee = pas de bonus)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        if not is_ranged_attack(is_ranged):            # gate IsRangedAttack IdunBattle.Entities.Effects.Loki.TerrifyingCrescendo_ExtraDmgEffect$$CreateEffectDamageBonusForAttack (melee/inconnu -> 0)
            return None                                # #106 : foyer unique du predicat (mirror BattleQuery)
        crescendo = self.level                         # EffectLevel (stack), deja cappe (buffMaxLevel=6) a l'ecriture
        if not crescendo or int(crescendo) <= 0:
            return None
        if self.ability_level is None:                 # ConfigVar sans AbilityState -> pas de magnitude
            return None
        per = ability_var("TerrifyingCrescendo", "extraDmg", self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        if not per:
            return None
        return for_addition(True, int(per) * int(crescendo))   # Multiply(ConfigVar(extraDmg), EffectLevel)
