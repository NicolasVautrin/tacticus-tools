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
from ...damage_trait import DamageTrait
from ...rarity import Rarity            # `idun.meta.Rarity` -- gate `HasRarity` (#999-r3-r1)
from ...triggered_ability_type import TriggeredAbilityType
from ...traits.unit_trait import UnitTrait
from ..base import (BaseEffect, is_at_range as _is_at_range, is_melee_attack, is_not_charging,
                    is_ranged_attack, relic_ability_state, target_is_on_fire_tile,
                    tiles_moved_this_turn)
from ..magnitude import ability_var, global_value, trait_var


def _damage_profile_has_trait(profile_name, trait: DamageTrait) -> bool:
    """`IdunBattleLogic.Entities.DSLTriggers$$DamageProfileHasTrait` -- le profil du COUP porte-t-il
    ce `DamageTrait` ?

    Les `DamageProfile.Traits` du gameconfig sont des NOMS de chaine : le check est name-based
    (`DamageTrait.X.name in Traits`), jamais un int brut -- meme regle que
    `active_ability.get_pierce` pour `LasCannon`. Profil ABSENT (`None`) = **non mesure** -> gate
    FERME (degradation RESTRICTIVE, comme tout gate d'`att_ctx` a cle absente)."""
    if not profile_name:
        return False
    try:
        import gameconfig as _GC
    except Exception:
        return False
    return trait.name in ((_GC.damage_profile(profile_name) or {}).get("Traits") or ())


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
    « Hostile Acquisition » du trait `PrioritisedEfficiency` (1059). PORTEURS (7, tous Leagues of
    Votann) : les 4 heros `votanBeserk` / `votanIronmaster` / `votanMemnyr` / `votanUthar`, le SUMMON
    `votanSmnSteeljack` (spawne par IronkinSteeljack) et 2 npc (`votanBeserk_LHE`,
    `votanNpc2Steeljack`). #121.

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


class TwistedScienceExtraDmgEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.TwistedScience_ExtraDmgEffect$$CreateEffectDamageBonusForAttack`
    (effet `EffectType.TwistedScience_ExtraDmg` = 0x54c = 1356) -- MIRROR du decompile :

        return EffectBonus.ForAddition( DSLTriggers.get_OwnerIsCaster,
                                        DSLFormulas.ConfigVar(8 = extraDmg,
                                                              BaseEffect.GetAbilityState(this),
                                                              <config @effet+0x60>) )

    Le porteur (`genesBiophagus` "Hollan", passif `TwistedScience` 1278) pose cet effet sur la cible
    de son soin QUAND elle est de faction `Genestealers` -- cf.
    `IdunBattleLogic.Entities.Abilities.Active.Loki.TwistedScience_HealAbility$$ExecuteBehaviour`,
    dont le volet `If(HasFaction(Target@+0x60, 15 Genestealers, 3), AddEffect(0x54c, ...))` en est
    le SEUL poseur du build.

    GATE = `get_OwnerIsCaster` **SEUL** -- lu, jamais deduit d'un voisin. Ni `IsNormalAttack`
    (contraste `SmashaEad` / `FeederTendrils`, dont le `if is_prediction: return None` vient de la),
    ni `IsMeleeAttack` / `IsRangedAttack`, ni `CreateTargetSelector`, ni `CreateActiveCondition` :
    aucun de ces symboles n'existe pour cette classe (methods.tsv ne lui declare que
    `CreateEffectDamageBonusForAttack` et `.ctor`), et l'i2 le corrobore --
    `UnitEffects/TwistedScience_ExtraDmg_Description` = "Deals +{[extraDmg]} Damage **with all
    attacks**". Le bonus vaut donc pour TOUTE attaque du porteur, y compris en PREDICTION :
    recopier le gate `is_prediction` de ses voisins de module serait la faute inverse. JUMEAU
    EXACT, corps pour corps, de `PrimarchOfTheFirstLegionExtraDamageEffect` ci-dessous.

    MAGNITUDE = `ConfigVar` var index **8 = `extraDmg`** (`AbilityVariableType.extraDmg`), lue dans
    la config de **`TwistedScience`** -- l'entree gameconfig du PASSIF 1278 ; l'active 1167
    `Heal_TwistedScience` n'a AUCUNE entree gameconfig. `variablesAffectedByRarityBonus = ["hp",
    "extraDmg"]` -> le multiplicateur de rarete s'applique. `ForAddition` -> canal `additive @+0x10`
    de `IdunBattle.Core.Services.DamageModifiers$$Add`, applique APRES percage/armure.

    RESIDU HERITE (meme forme que `PrimarchOfTheFirstLegion`, bug #68) : le natif resout son
    `ConfigVar` contre l'`AbilityState` que l'effet PORTE -- celui que
    `AddEffect(0x54c, abilityState = AActiveAbility.AbilityStateReference, ...)` lui a passe, donc
    l'etat d'ability du CASTER (Hollan). Cote port, `AddEffect(scale_from_source=True)` propage bien
    niveau + multiplicateur de la SOURCE au moment de la pose ; un effet arrive par `load_state`
    (canal live) retombe en revanche sur les champs de l'unite PORTEUSE. Sur le regime confronte
    (rank uniforme) les deux coincident."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        amt = ability_var("TwistedScience", "extraDmg", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, amt) if amt is not None else None


class PrimarchOfTheFirstLegionExtraDamageEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.PrimarchOfTheFirstLegion_ExtraDmgEffect$$
    CreateEffectDamageBonusForAttack` (effet `EffectType` 0x5f3 = 1523) -- MIRROR du decompile :

        EffectBonus.ForAddition(get_OwnerIsCaster, ConfigVar(8 = extraDmg, <abilityState>, ...))

    Pose par
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PrimarchOfTheFirstLegionAbility$$CreateBehaviour`
    sur l'allie Dark Angels qui vient d'encaisser un coup a la place du Lion (#418), pour
    `TurnsFromRounds(nrOfRounds = 1)`.

    ⚠ Le gate natif est **`get_OwnerIsCaster` SEUL** -- lu, et c'est l'ecart avec ses jumeaux de ce
    module : `SmashaEad` et `FeederTendrils` portent en plus un `IsNormalAttack` (d'ou leur
    `if is_prediction: return None`, ce predicat evaluant FALSE en contexte de prediction). Ici il
    n'y a AUCUN second conjoint : le bonus s'applique a TOUTE attaque du porteur, y compris en
    prediction. Ne pas recopier le gate `is_prediction` des voisins serait la faute inverse.

    MAGNITUDE = `ConfigVar` var index 8 = `extraDmg`, la SEULE variable de l'entree gameconfig de
    `PrimarchOfTheFirstLegion` (`variablesAffectedByRarityBonus: ["extraDmg"]` -> scale par le
    multiplier). `ForAddition` -> canal `additive @+0x10` de
    `IdunBattle.Core.Services.DamageModifiers$$Add`, applique POST-percage/armure.

    ⚠ RESIDU HERITE (bug #68, pas propre a cet effet) : le natif resout son `ConfigVar` contre
    l'`abilityState` que `AddEffect` lui a passe -- celui du LION. Cote port, `BaseEffect` ne porte
    que le niveau/multiplier de l'unite qui PORTE l'effet (ici l'allie). Sur le regime confronte
    (greffe, niveaux normalises identiques) les deux coincident ; ils divergeraient si le Lion et
    son allie avaient des niveaux d'ability distincts."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        amt = ability_var("PrimarchOfTheFirstLegion", "extraDmg", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, amt) if amt is not None else None


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


class HyperCorrosiveAcidExtraDamagePctEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.HyperCorrosiveAcid_ExtraDamagePctEffect` (`EffectType`
    0x5a8 = **1448**) -- l'effet pose par l'ability **MYTHIQUE** `HyperCorrosiveAcid` (0x5af = 1455)
    des MoW `tyranBiovore` / `tyranNpcMowBiovore. La POSE est portee depuis #1035
    (`runner/operations/triggers/loki/hyper_corrosive_acid.py`) ; c'est la face DEGAT qui manquait,
    et son verrou etait le canal de RARETE (residu `#1035-r1`, ferme par `#999-r3-r1`).

    i2 : << Enemies that are damaged by a friendly **Spore Mine** take +{extraDmgPct}% Damage from
    attacks by **Mythic** characters for {nrOfRounds} round. >>

    ## MIRROR 1:1 -- `...HyperCorrosiveAcid_ExtraDamagePctEffect$$CreateEffectDamageBonusForAttack`

        EffectBonus.ForPercentIncrease(
            get_OwnerIsTarget
            & ( AreFriends( Caster@<DSLSelectors+0x48>,
                            EffectSource(Effect@<DSLSelectors+0x38>), 0, false )
                & HasRarity( Caster@<DSLSelectors+0x48>, idun.meta.Rarity.Mythic = 5 )
                & HasTrait(  Caster@<DSLSelectors+0x48>, 0x10 = UnitTrait.Hero ) ),
            DSLFormulas$$ConfigVar( 0xa = AbilityVariableType.extraDmgPct,
                                    GetAbilityState(effet), effet@+0x60 ) )

    ## LE CANAL EST CELUI DE LA CIBLE, **PAS** L'AURA -- et c'est LU, pas suppose
    `search_symbols_by_name` sur cette classe rend **deux** symboles (`$$.ctor` et
    `$$CreateEffectDamageBonusForAttack`) : il n'y a **AUCUN `$$CreateTargetSelector`**. L'Owner de
    l'effet est donc son PORTEUR, et `get_OwnerIsTarget` dit que ce porteur est la CIBLE du coup
    -> le canal port est `create_effect_damage_malus_for_defense` (la boucle des effets de la
    CIBLE), pas `create_aura_defense_damage_malus_for_ally`. Le residu `#999-r3-r1` rangeait cet
    effet parmi les consommateurs des agregateurs d'AURA : re-mesure, c'est faux.

    Malgre le nom natif << ...ForAttack >>, l'effet MAJORE le degat que son porteur RECOIT --
    meme mold qu'`ExemplarOfHateTargetEffect` / `ChronometronExtraDamageEffect`.

    ## LES TROIS CONJOINTS, ET D'OU ILS VIENNENT
      1. `AreFriends(Caster, EffectSource(Effect))` -- l'ATTAQUANT est un allie du BIOVORE.
         `EffectSource` = `EffectComponent.SourceUnit @+0x10` = `self.source` cote port ; son equipe
         se resout par `attacker_ctx["team_by_id"]`, celle de l'attaquant par `attacker_ctx["team"]`
         (MEME idiome que `ChronometronExtraDamageEffect`).
      2. `HasRarity(Caster, Mythic)` -- `BaseUnitComponent.Rarity` (+0x74) de l'ATTAQUANT, lu dans
         `attacker_ctx["rarity"]` (#999-r3-r1 ; foyers `damage_model._unit_rarity` /
         `prediction._shared._entity_rarity`). TRI-ETAT : `None` = NON MESURE -> gate FERME.
         C'est LE conjoint qui tenait cet effet hors du registre : sans lui, tout attaquant Hero ami
         du Biovore aurait beneficie du bonus -- terme PERMISSIF.
      3. `HasTrait(Caster, 0x10 = UnitTrait.Hero)` -- `attacker_ctx["traits"]`.

    ## MAGNITUDE
    `ConfigVar(0xa = extraDmgPct)` sur la config de l'ability `HyperCorrosiveAcid`, indexee par
    `GetAbilityState(effet)` = l'`AbilityStateReference` BAKEE dans `EffectComponent+0x18` a la
    pose (#382/#1038) -- celle de la MoW POSEUSE, pas du porteur (ici les deux DIFFERENT par
    construction : `source = Owner`, `targets = Target`). Pour une TERTIAIRE ce couple est
    `level 1..4 / mult 100`. Gameconfig : `extraDmgPct = [10, 13, 16, 20]`,
    `variablesAffectedByRarityBonus = ['extraDmgPct']`. `ability_level` absent -> AUCUNE
    contribution (<< present != applique >>), jamais un repli sur `self.level` (qui est un niveau de
    STACK, pas un `AbilityState`)."""

    #: Cle gameconfig de l'ability qui pose l'effet -- la config qu'indexe `ConfigVar`.
    ABILITY_ID = "HyperCorrosiveAcid"
    #: `AbilityVariableType` 0xa = 10, resolu par son NOM (jamais par l'ordinal : `AbilityConstantType`
    #: 10 nomme autre chose).
    VAR_EXTRA_DMG_PCT = "extraDmgPct"

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        ac = attacker_ctx or {}
        # 1. `AreFriends(Caster@+0x48, EffectSource(Effect@+0x38), 0, false)`
        a_team = ac.get("team")
        s_team = (ac.get("team_by_id") or {}).get(self.source) if self.source is not None else None
        if a_team is None or s_team is None or a_team != s_team:
            return None                                   # equipe inconnue -> gate muet (fidele)
        # 2. `HasRarity(Caster@+0x48, idun.meta.Rarity.Mythic = 5)` -- #999-r3-r1. Comparaison au
        #    MEMBRE d'enum, jamais a l'ordinal : cinq enums du build partagent les six memes
        #    ordinaux de rarete (cf. `entities/rarity.py`). `None` (non mesure) -> FERME.
        if ac.get("rarity") != Rarity.Mythic:
            return None
        # 3. `HasTrait(Caster@+0x48, 0x10 = UnitTrait.Hero)`
        if UnitTrait.Hero.name not in (ac.get("traits") or frozenset()):
            return None
        lvl = self.ability_level
        if lvl is None:
            return None                                   # `ConfigVar` sans `AbilityState` -> inerte
        pct = ability_var(self.ABILITY_ID, self.VAR_EXTRA_DMG_PCT, lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        if not pct:
            return None
        # owner = le DEFENSEUR (l'effet vit sur la cible) -> le degat RECU augmente.
        return for_percent_increase(False, int(pct))

    # #437-r1-r1-r1 : le natif DECLARE `CreateEffectDamageBonusForAttack` (slot 0x16) -> son
    # `EffectBonus` atterrit dans `attackModifiers`, MALGRE le trigger `get_OwnerIsTarget`. Canal
    # POURCENT, donc l'attribution a une CONSEQUENCE ARITHMETIQUE (un `Fix64.Round` par
    # accumulateur non nul, cf. `BaseEffect`).
    DEFENSE_MALUS_NATIVE_FACE = "attacker"


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
    - GATE `IsCharging` (case-r32, RETROFIT) : le noeud DSL resout le slot
      `IdunBattle.Core.Services.BattleQuery$$IsCharging(caster, target)` = `AreEntitiesAdjacent(caster,
      target) && UnitComponent.ChargedUnitIds@+0x190.Contains(target.Id)`. Porte par le gate PARTAGE
      `is_not_charging(att_ctx)` (foyer `effects/base.py`), alimente per-coup par le contexte d'attaque.
      ⚠ Ce n'est PAS `HasFlag(Moved)` : l'ancien proxy `has_moved` accordait l'additif a un caster qui
      bouge vers une cible DEJA adjacente avant son pas -- cas ou `UpdateCharging` n'ajoute rien, donc
      ou le natif n'accorde RIEN. `get_IsMelee` (IdunBattleLogic.Entities.Abilities.Active.Loki.FeederTendrils_NormalAttackAbility$$ExecuteBehaviour) reste le second gate ->
      l'additif n'est ACTIF qu'en attaque MELEE de CHARGE. Contrairement a SmashaEad, PAS de
      `if is_prediction: return None` : ici IsNormalAttack=TRUE (c'est l'attaque normale de l'unite,
      incluse dans decisionView).
    ⚠ A confirmer live (Deathleaper n'a pas encore ete rejoue depuis le retrofit) : niveau/mult reels de
    u87 (infere L50/mult1.8). Le cas NEGATIF du gate est, lui, VERROUILLE sur le jumeau AvalancheOfMuscle
    (`test_ischarging_extra_damage_live.py`, meme foyer de gate)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        if is_ranged:                       # get_IsMelee (IdunBattleLogic.Entities.Abilities.Active.Loki.FeederTendrils_NormalAttackAbility$$ExecuteBehaviour) -> melee uniquement
            return None
        if is_normal_attack is False:       # IsNormalAttack (IdunBattleLogic.Entities.DSLTriggers$$IsNormalAttack)
            return None
        if is_not_charging(att_ctx):        # IsCharging (IdunBattleLogic.Entities.DSLTriggers$$IsCharging -> BattleQuery$$IsCharging)
            return None
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
    - GATE `IsCharging` (case-r32, RETROFIT) : `IdunBattleLogic.Entities.DSLTriggers$$IsCharging(caster@0x160,
      target@0x178)` resout le slot `IdunBattle.Core.Services.BattleQuery$$IsCharging(caster, target)` =
      `AreEntitiesAdjacent(caster, target) && UnitComponent.ChargedUnitIds@+0x190.Contains(target.Id)`,
      liste alimentee par `IdunBattle.Operations.MoveUnitOperation$$UpdateCharging` (unites devenues
      NOUVELLEMENT adjacentes pendant le pas) et videe par `IdunBattle.Operations.FinishUnitTurnOperation$$Execute`.
      Porte par le gate PARTAGE `is_not_charging(att_ctx)` (foyer `effects/base.py`), threade per-coup.
      ⚠ REMPLACE le proxy `has_moved` (`UnitFlag.Moved`), strictement PLUS LARGE : MESURE live
      (`test_ischarging_extra_damage_live.py`, astraBullgryn L50 mult 180 %) -- caster qui BOUGE vers une
      cible DEJA adjacente avant son pas : natif `[3336,3158,2479,2533]`, port-avec-proxy
      `[3935,3757,3078,3132]` = **+599 par coup de trop**, sur les 4 coups. Le regime CHARGE, lui, etait
      deja bit-exact : SEUL le gate divergeait.
      astraBullgryn est MELEE-only (aucune attaque ranged) -> le gate `is_ranged` est un no-op ; conserve
      pour rester le calque strict de FeederTendrils.
    - PAS de `is_normal_attack` gate (contrairement a FeederTendrils) : le natif n'a PAS le noeud IsNormalAttack."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        if is_ranged:                       # melee-only (astraBullgryn ; calque FeederTendrils)
            return None
        if is_not_charging(att_ctx):        # IsCharging (IdunBattleLogic.Entities.DSLTriggers$$IsCharging -> BattleQuery$$IsCharging)
            return None
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
        # turn »). Le prédicat natif est le MÊME des deux côtés — `HasFlagAbilityTrigger$$ShouldTrigger`
        # -> `UnitFlagsComponent$$Has` sur l'ECS — et les DEUX faces le portent désormais :
        #  * COMBAT (#60/#101) : `components.unit_has_moved`, flag posé par `set_moved_flag` dans
        #    `MoveUnitOperation` et seedé depuis le live par `snapshot._load_unit_flags` ;
        #  * PRÉDICTION (#266) : `prediction.prediction_has_moved` = `HasFlag(u, Moved)` (via
        #    `Scene.moved_by_id` <- `combatSnapshot.unitFlags`) **OU** tuile candidate ≠ tuile courante
        #    — ce second terme n'est pas un proxy mais le mirror de
        #    `SimulateEffectsOperation$$DoActionInSimulatedTile`, qui appelle `SetMovedFlag` avant
        #    d'évaluer la prédiction d'une tuile simulée puis restaure.
        # None (contexte hors combat/prédiction, ou capteur `unitFlags` non mesuré) → bonus appliqué
        # (fallback, comportement antérieur).
        # Un état rechargé par `load_state` connaît DÉSORMAIS le flag : `combatSnapshot.units[].
        # unitFlags` (capteur O5 de `rpc-snapshot.ts`, qui invoque `IdunBattle.Entities.
        # UnitExtensions$$HasFlag`) est seedé par `snapshot._load_unit_flags`. Avant ce câblage RIEN
        # ne peuplait le `UnitFlagsComponent` sur un état rechargé (`set_moved_flag` n'est appelé que
        # par `MoveUnitOperation`, voie offline) : tout replay-diff d'une attaque SUIVANT un
        # déplacement accordait ce +25% que le natif refuse (case-o10 §6, mesuré live 5868 / offline
        # 7096 sur `blackObliterator` — l'offline rendait la MÊME valeur qu'immobile).
        # `| HasFlag(Self, 0xc = Teleported)` (décompilé relu) : un déplacement qui était un TELEPORT
        # ne retire PAS le bonus. Threadé dans `att_ctx` par `attacker_modifiers` (COMBAT) et par
        # `prediction_has_teleported` (PRÉDICTION, #266) — clé absente (appelants historiques) →
        # branche `has_moved` seule, comme avant.
        if has_moved and not (att_ctx or {}).get("has_teleported"):
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


class MeltaExtraDmgEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.Melta_ExtraDmgEffect$$CreateEffectDamageBonusForAttack`
    (EffectType `Melta_ExtraDmg` = 0x511 = 1297) -- MIRROR 1:1 du decompile (`rnca9r7q6c`) :

        cond = op_BitwiseAnd( DamageProfileHasTrait(0x5 = DamageTrait.OnMelta),
                              HasTrait(Target@DSLSelectors+0x60, 0x405 = UnitTrait.Vehicle) )
        amt  = ConfigConst(0xf) = globalValues.meltaDamageExtraDmgPct = 50
        return EffectBonus.ForPercentIncrease(cond, amt)

    = le **+50 % vs Vehicle** que l'i2 `Keywords/DMG_Melta` annonce (« Deals +50% damage against
    Vehicle units »). Jumeau STRUCTUREL de `BeastSlayerExtraDmgEffect` ci-dessous, a UNE difference
    LUE : le premier conjoint n'est PAS un noeud melee mais `DamageProfileHasTrait(OnMelta)`.

    ⚠ CET EFFET N'EST PORTE PAR AUCUNE UNITE -- ET C'EST LE NATIF QUI EN DECIDE AINSI.
    `IdunBattleLogic.Entities.Abilities.Damage.Loki.OnMeltaDamageAbility$$CreateBehaviour` le pose
    par `AddEffect(0x511, AbilityStateReference, targets = First(AllTiles(), amount: 1))` : le
    support est **UNE TUILE ARBITRAIRE** (`<DSLSelectors+0x18>` = `AllTilesSelector`, ecrit
    NOMMEMENT par `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared`), pas l'attaquant.
    MESURE live (#488-r1, `MC1_67`, RPC `tileMeta`) : l'effet est sur la tuile **(0,0)**, et le
    bonus mord IDENTIQUEMENT que l'attaquant s'y tienne ou non.

    Ce n'est pas une anomalie mais la consequence de l'architecture native :
    `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` invoque
    le slot de bonus **SANS AUCUN FILTRE de proprietaire ni de position** -- il passe a chaque effet
    l'`AbilityEntities` complet (attaquant, cible, tuile, arme) et laisse l'effet decider. Or les
    DEUX conjoints du gate ci-dessus portent sur le COUP et sur la CIBLE, jamais sur le porteur :
    la tuile n'est qu'un support d'existence. L'ability etant GLOBALE (aucun owner, cf.
    `GLOBAL_TRIGGERS`) et son trigger `On(0x19 = EventTriggerType.MatchInit, true)` inconditionnel,
    l'effet est present dans TOUTE bataille -- d'ou son inscription dans `MATCH_WIDE_EFFECTS`
    (`effects/__init__.py`) plutot que dans les effets d'une unite.

    ⚠ HISTORIQUE -- NE PAS RE-CLASSER EN DEAD-CODE SANS RE-MESURER. `case-72` a conclu DEAD-CODE sur
    le build `gqfc5mff6c`, ou `$$CreateTrigger` etait REELLEMENT absent. Sur `rnca9r7q6c` la classe
    le DECLARE (slot de vtable a la profondeur 0, RPC `resolveMethodPtr`) et le +50 % est MESURE :
    a armure egalisee et geometrie identique, `tauShadowsun` predit `[9014-13520]` contre
    `admecDestroyer` (Vehicle) et `[6008-9014]` contre DEUX temoins non-Vehicle -- rapport 1,5000
    exact, et il disparait en melee (profil non-Melta). Detail :
    `docs/rl/case-488-r1-onmelta-vivant-ou-mort.md`."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        # 1er conjoint : `DamageProfileHasTrait(OnMelta)` -- le profil du COUP, threade dans
        # `att_ctx["damage_profile"]` par les DEUX faces (prediction `normal_attack`/`abilities`,
        # combat `damage_model.attacker_modifiers`). Cle absente -> gate FERME.
        if not _damage_profile_has_trait((att_ctx or {}).get("damage_profile"), DamageTrait.OnMelta):
            return None
        # 2e conjoint : `HasTrait(Target@0x60, Vehicle)` -- MEME substrat que BeastSlayer
        # (`target_trait_names` cote combat, `_entity_traits` cote prediction).
        if not target_traits or UnitTrait.Vehicle.name not in target_traits:
            return None
        pct = global_value("meltaDamageExtraDmgPct")
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


#: `HasTrait(Target@<DSLSelectors+0x60>, X)` de `BeastSnagga_ExtraDmgEffect$$CreateDamageModifier`,
#: par leur MEMBRE d'enum (#270-r1-r1-r3). Meme paire que `_BEAST_SLAYER_TARGET_TRAITS` ci-dessus,
#: et c'est une LECTURE INDEPENDANTE : les deux effets sont deux classes natives distinctes, dont
#: les corps se trouvent coincider. Un futur build qui changerait l'un des deux ne changerait pas
#: forcement l'autre -- partager la constante ferait glisser les deux ensemble, en silence.
_BEAST_SNAGGA_TARGET_TRAITS = frozenset({UnitTrait.Vehicle.name, UnitTrait.BigTarget.name})


class BeastSnaggaExtraDmgEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.BeastSnagga_ExtraDmgEffect$$CreateDamageModifier` (trait
    `BeastSnagga` 0x406 = 1030, effet `BeastSnagga_ExtraDmg` 0x438 = 1080). #1015-r1.

    ⚠ **LE CORPS DECOMPILE EST IDENTIQUE, INSTRUCTION POUR INSTRUCTION, A CELUI DE
    `BeastSlayer_ExtraDmgEffect$$CreateDamageModifier`** -- meme `ConfigConst(0xf)`, memes deux
    `HasTrait(Target@<DSLSelectors+0x60>, 0x405 Vehicle | 0x3f9 BigTarget)`, meme
    `get_OwnerIsCaster & IsMeleeAttack`, meme construction inline du `Nullable<EffectBonus>` (le
    seul ecart est le drapeau d'init de classe). Ce n'est donc PAS << recopier le voisin de forme >>
    -- c'est le MEME artefact natif, LU des deux cotes :

        amount  = ConfigConst( AbilityConstantType.extraDmgPct = 0xf, config@this+0x60 )
        trigger = get_OwnerIsCaster & IsMeleeAttack
                  & ( HasTrait(Target, UnitTrait.Vehicle) | HasTrait(Target, UnitTrait.BigTarget) )

    et le champ ecrit est le meme slot du bonus que `BeastSlayer` -> **`ForPercentIncrease`**
    (contraste LU avec `MonsterSlayerOfCaliban_ExtraDmg`, meme paire de traits cible mais
    `ForAddition` et AUCUN gate de nature).

    SOURCE DES VALEURS -- et pourquoi ce n'est pas `ability_var`. `BeastSnagga` n'existe PAS dans
    `units.abilities` du gameconfig (`GC.ability("BeastSnagga")` rend `null`, exactement comme
    `BeastSlayer`) : la config que lit `ConfigConst` est SYNTHETISEE depuis
    `globalValues.traitVariables`, et la `BattleConfiguration` la publie sous
    `Abilities.PassiveAbilities.BeastSnagga.Constants = {extraDmgPct: 20, blockChance: 10,
    blockDmgPct: 20}` (LU dans `data/seed-bc.json`). C'est cette table-la qui donne l'appariement
    NOMME `traitVariables -> AbilityConstantType`.

    ⚠ **L'APPARIEMENT NE PEUT PAS SE FAIRE PAR LA VALEUR** : `extraDmgPct` et `blockDmgPct` valent
    TOUS DEUX 20 sur ce trait. Ce qui tranche, c'est le NOM et l'arbre : `beastSnaggaDmgBonus` est
    le bonus de degat (`ConfigConst(0xf)` ici), `beastSnaggaDmgAsMaxHpPct` est le montant de block
    exprime en % des PV max (`GetNumberConstant(0x36)` de `BeastSnaggaAbility$$CreateBehaviour`,
    ou il est l'argument d'un `PercentageOf(StatAmount(Owner, Health, Maximum), ...)`). Chez
    `BeastSlayer` les deux valeurs different (20 / 100) et l'erreur se serait vue ; ici elle serait
    SILENCIEUSE sur l'axe degat et fausse de 5x sur l'axe block.

    OBSERVABLE : +20 % de degat MELEE contre les cibles `BigTarget` / `Vehicle`. `target_traits`
    = les noms de traits de la CIBLE ; `None` (contexte sans cible) -> pas de bonus, jamais un
    bonus devine (meme regime que `BeastSlayer`)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        if not is_melee_attack(is_ranged):             # IsMeleeAttack -> melee uniquement
            return None                                # #106 : nature NON prouvee melee -> gate FAUX
        if not target_traits or _BEAST_SNAGGA_TARGET_TRAITS.isdisjoint(target_traits):
            return None                                # cible ni BigTarget ni Vehicle -> 0
        pct = trait_var("BeastSnagga", "beastSnaggaDmgBonus")
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

    - `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsActor` (owner@0x148 vs actor@0x158) vs `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsCaster`
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


class FuelledByFuryExtraDamageEffect(BaseEffect):
    """`FuelledByFury_ExtraDamage` (EffectType 0x52b=1323, nom capte "FuelledByFury_ExtraDamage" ;
    passif triggered `FuelledByFury` 0x4e3=1251 d'`ultraTitus` << Titus >>, Ultramarines/Imperial) --
    i2 : << Deals +153 Damage with all attacks for each time a friendly Character has used an active
    ability this battle. >> #1323.

    TROISIEME membre de la fratrie `Multiply(ConfigVar(8=extraDmg), EffectLevel)` apres BeaconOfRage
    (1298) et TerrifyingCrescendo (1424) -- et c'est FuelledByFury qui en porte le corps PARTAGE :
    `IdunBattle.Entities.Effects.Loki.FuelledByFury_ExtraDamageEffect$$GetCurrentExtraDamage`
    (refcount 10) = `Multiply(ConfigVar(8, GetAbilityState(effet), effet+0x60), EffectLevel(effet@0x150))`,
    dont TerrifyingCrescendo HERITE.

    - degat `IdunBattle.Entities.Effects.Loki.FuelledByFury_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` :
      `EffectBonus.ForAddition(DSLFactory.get_OwnerIsCaster, GetCurrentExtraDamage())` -- bonus FLAT
      additif (AUCUN `ForPercent*`), meme canal additif que BeaconOfRage/SmashaEad
      (`IdunBattle.Core.Services.DamageModifiers$$Add`, applique par coup). Le noeud `get_OwnerIsCaster`
      est le SEUL de la conjonction : PAS de gate `IsRangedAttack` (contrairement a TerrifyingCrescendo),
      PAS de `IsNormalAttack`, PAS de `IsMeleeAttack`, PAS de gate sur un trait de la cible -- d'ou le
      i2 << with ALL attacks >> (normale ET ability, melee ET distance).
    - magnitude : `extraDmg[abilityLevel PASSIF] x multiplier x EffectLevel`. `extraDmg` = variables
      `FuelledByFury` (2 (L1) -> 138 (L50) -> 153 (L65)), DANS `variablesAffectedByRarityBonus` ->
      scale par le multiplier de rarete de l'unite (comme TerrifyingCrescendo, contrairement a
      BeaconOfRage). Le << 248/coup >> observe = `round(138 x 180/100)` = extraDmg[L50] x mult 180 %,
      pour UN stack ; i2 << +153 >> = extraDmg[L65] a mult 100 %.
    - `EffectLevel` = le compteur d'abilities actives alliees, accumule par la face TRIGGER
      (`runner/operations/triggers/loki/fuelled_by_fury.py`, mirror de
      `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ExtraDamageAbility$$CreateTrigger`
      + `$$CreateBehaviour`). Le niveau abouti arrive TEL QUEL dans `decisionView.effects[].level`
      (comme BeaconOfRage / TerrifyingCrescendo) -> on lit `self.level` sans re-calcul offline.
      AUCUN cap : `IncreaseEffectLevel(Owner@0x148, 0x52b, amount=NULL, max=NULL)` -- l'amount NULL
      retombe sur `df@0xc0 = Const(1)` (`IdunBattleLogic.Entities.DSLBehaviors$$IncreaseEffectLevel`) et
      le `max` NULL desactive le clamp d'`IdunBattle.Operations.IncreaseEffectLevelOperation$$Execute`.
    - niveau/level inconnu -> inerte (degradation fidele, meme regle que ses deux jumeaux).

    Les deux autres membres de la famille FuelledByFury sont HORS de cette classe : `FuelledByFury_
    BlockOverkill` (1354, `UnitFlag.PreventOverkill`) vit dans `runner/components.py` (#178), et
    `FuelledByFury_CanRevive` (1324) n'est pas porte (backlog #66-r2)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        # trigger natif = `get_OwnerIsCaster` SEUL (aucun autre noeud dans
        # `...FuelledByFury_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`) -> tous profils,
        # normale ET ability, melee ET distance. `OwnerIsCaster` est vrai par construction sur ce
        # canal (`_attacker_effect_bonuses` n'itere que les effets de l'ATTAQUANT).
        fury = self.level                              # EffectLevel (stack), sans cap natif
        if not fury or int(fury) <= 0:
            return None
        if self.ability_level is None:                 # ConfigVar sans AbilityState -> pas de magnitude
            return None
        per = ability_var("FuelledByFury", "extraDmg", self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        if not per:
            return None
        return for_addition(True, int(per) * int(fury))   # Multiply(ConfigVar(extraDmg), EffectLevel)


class ModifiedExoarmourExtraDmgEffect(BaseEffect):
    """`ModifiedExoarmour_ExtraDmg` (EffectType 0x608 = **1544**) — volet OFFENSIF du passif
    `ModifiedExoarmour` (TriggeredAbilityType 0x5f9 = 1529) de `votanChampion` <<Kimm>>. case-322.

    MIRROR 1:1 de `IdunBattle.Entities.Effects.Loki.ModifiedExoarmour_ExtraDmgEffect$$
    CreateEffectDamageBonusForAttack` :

        EffectBonus.ForAddition( get_OwnerIsCaster & IsMeleeAttack, GetCurrentDamageBonus() )

    et de `IdunBattle.Entities.Effects.Loki.ModifiedExoarmour_ExtraDmgEffect$$GetCurrentDamageBonus` :

        Multiply( ConfigVar(8 = extraDmg, GetAbilityState, EffectSource),
                  TilesMovedThisTurn(Self) )

    TROIS lectures font la MAGNITUDE, et aucune ne se devine (case-322 SS 2) :

    1. **`MultiplyAmount$$Calculate` est un produit d'ENTIERS** (`(int)a * (int)b`, decompile) — pas
       une multiplication Fix64 : la valeur de config est arrondie AVANT d'etre multipliee.
    2. **`ConfigAmount$$Calculate` -> `AbilityConfiguration$$GetVariableForLevel` ->
       `$$TryGetVariableArrayForLevel`**, dont le corps est
       `v = int(arr[clamp(level-1)])` puis, SSI `varType` est dans `_variablesAffectedByRarityBonus`
       (this+0x28), `v = (int) Fix64.Round( Fix64(multiplierPct) / 100 * v )`. C'est EXACTEMENT
       `magnitude.ability_var(..., multiplier_pct=...)` — meme foyer, meme arrondi (ancre partagee :
       `PowerTrip.armorIgnored[L50] = 277 x 1.8 -> 499`). `extraDmg` EST dans la liste rarity du
       gameconfig de `ModifiedExoarmour` (verifie, pas suppose).
    3. **`TilesMovedThisTurn`** = le facteur, PAS un gate on/off : le bonus est `V x n`, donc
       l'`ActiveCondition` `AmountIsGreaterThanZero(n)` est REDONDANTE avec la magnitude (n = 0 rend
       un additif nul). Elle est quand meme mirroree par `is_active` ci-dessous — le natif l'ecrit.

    PLACEMENT — `ForAddition` ecrit `DamageModifiers.Addition @+0x10`, consomme par le canal DEJA
    porte `attacker_additive_pre=True` (#75/#70) : l'additif s'ajoute a la base PAR COUP **AVANT**
    percage/armure, puis traverse le %-list. Rien a re-ordonnancer.
    C'est ce placement qui ferme les deux residus de #312 : l'ecart ne se compose pas « apres coup »
    (`624 x n x M`), il se materialise par `Fix64.Round((base_percee + V x n / f) x M)` UNE FOIS PAR
    COUP. Les six tuiles de melee de la fixture, min ET max, tombent alors bit-exactes — y compris la
    tuile (4,0) que le modele multiplicatif ratait de 2 (`probe_322_exoarmour_magnitude.py`).

    GATES LUS (et rien d'autre — les callees du decompile sont
    {GetCurrentDamageBonus, get_OwnerIsCaster, IsMeleeAttack, op_BitwiseAnd, ForAddition,
     Nullable.ctor}) :
      * `get_OwnerIsCaster` : VRAI par construction sur ce canal (`_attacker_effect_bonuses` n'itere
        que les effets de l'ATTAQUANT) ;
      * `IsMeleeAttack` : gate PARTAGE `is_melee_attack(is_ranged)` — nature non prouvee melee =>
        aucune contribution. MESURE #312 : les sept tuiles a distance de la fixture sont EXACTES
        sans ce bonus, les six de melee ne le sont qu'avec ;
      * **AUCUN** `IsNormalAttack` -> le bonus vaut aussi pour les attaques d'ABILITY ;
      * **AUCUN** gate `has_moved` : `TilesMovedThisTurn` n'est PAS `HasFlag(Moved)` (un teleport pose
        `Moved` sans enregistrer de tuile ; un `DisplaceUnitOperation` enregistre des tuiles).

    NIVEAU — `GetAbilityState` sur l'effet indexe `variables[level]` du config de `ModifiedExoarmour`,
    qui est un PASSIF : cascade `active_ability_level -> ability_level -> level`, la meme que
    `AvalancheOfMuscle`/`CondemnorStake`. Multiplier = le GLOBAL de l'unite.

    MATERIALISATION — l'effet est POSE des le deploiement (`ModifiedExoarmourAbility$$CreateBehaviour`
    = `AddEffect(0x607) & AddEffect(0x608)`) mais son `IsActive` natif est FAUX tant que l'unite n'a
    pas bouge : le canal `decisionView` par DEFAUT ne le publie donc pas (MESURE live : `1543
    PierceReduction` present des le deploiement, `1544` seulement avec `includeInactive`). D'ou les
    deux pieces d'infra qui accompagnent ce port : l'entree `ModifiedExoarmour` de
    `factory.ABILITY_INIT_OWNER_EFFECTS` (le seed) et `active_condition_ported` (le flag capte est
    perime pour un effet dont la condition porte sur l'etat SIMULE)."""

    # Le flag `EffectComponent.IsActive` capte decrit l'etat REEL (n = 0 hors deplacement) ; la
    # prediction evalue l'etat SIMULE, que le natif recalcule (`RefreshSimulatedEffects`).
    active_condition_ported = True
    # TEMOIN d'ENTITE : `ModifiedExoarmourAbility$$CreateBehaviour` = `AddEffect(0x607) &
    # AddEffect(0x608)` -- UNE SEULE expression (`AbilityBehaviour$$op_Addition`), donc les deux
    # effets sont poses ENSEMBLE ou pas du tout. `ModifiedExoarmour_PierceReduction` (0x607=1543)
    # n'a AUCUN `CreateActiveCondition` (ses seuls membres natifs sont `.ctor` et
    # `CreatePiercingMalusForDefense`) -> il est TOUJOURS actif, donc TOUJOURS publie par le canal
    # `decisionView` par defaut. Sa presence atteste que le behaviour a tourne sur CETTE entite ;
    # son absence, que l'unite n'a pas le passif (MESURE : c'est exactement ce que discrimine le
    # contre-bras `--passive-off` de #312, ou le seed BC vide `PassiveAbilities`).
    seed_witness_effect = "ModifiedExoarmour_PierceReduction"

    def is_active(self, unit_state=None) -> bool:
        """`ModifiedExoarmour_ExtraDmgEffect$$CreateActiveCondition` =
        `AmountIsGreaterThanZero( TilesMovedThisTurn(Self) )`.

        `tiles_moved_this_turn` ABSENT du `unit_state` = **non mesure** (la `Scene` de prediction est
        construite AVANT de connaitre la tuile candidate) -> on ne ferme pas : la magnitude, qui EST
        `V x n`, rend alors l'effet inerte toute seule. Presente -> le gate natif, verbatim.

        Cote COMBAT la cle EST desormais posee (case-322-r1) : `UnitEffectStateView` la lit de
        `ActorStatisticsComponent+0xf0` (`runner/components.py::unit_tiles_moved_this_turn`), que
        `MoveUnitOperation` tient a jour. Le gate y est donc le gate NATIF, plus une degradation."""
        n = (unit_state or {}).get("tiles_moved_this_turn")
        return True if n is None else int(n) > 0

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        if not is_melee_attack(is_ranged):        # IsMeleeAttack (BattleQuery$$IsMeleeAttack)
            return None
        # `TilesMovedThisTurn(Self)` -- foyer partage. DEUX alimentations, aucune devinee :
        #  * DECISION : `prediction_tiles_moved_this_turn` (compteur reel + pas simule) ;
        #  * COMBAT (case-322-r1) : `attacker_modifiers` lit le compteur REEL de l'ECS, tenu par
        #    `MoveUnitOperation` -> une charge de Kimm FACTURE desormais son bonus en combat.
        n = tiles_moved_this_turn(att_ctx)
        if not n or int(n) <= 0:                  # non threade, ou aucune tuile parcourue -> inerte
            return None
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        v = ability_var("ModifiedExoarmour", "extraDmg", lvl,
                        multiplier_pct=self.ability_variables_multiplier)
        if not v:
            return None
        # `MultiplyAmount$$Calculate` = produit d'ENTIERS : `v` est DEJA l'entier arrondi rendu par
        # `TryGetVariableArrayForLevel` (round(mult/100 x brut)), jamais un flottant a re-arrondir.
        return for_addition(True, int(v) * int(n))


class SpecialIssueCombiMeltaExtraDmgEffect(BaseEffect):
    """`SpecialIssueCombiMelta_ExtraDmg` (`EffectType` 0x61c = **1564**) -- classe native
    `Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.SpecialIssueCombiMelta_ExtraDmgEffect`.
    Jumeau de `SpecialIssueCombiMelta_AdditionalHits` (1563, `effects/loki/hits.py`) : meme porteur
    (`darkaSternguard` « Ramus », npc `darkaBossSternguardLHE`), meme poseur
    (`SpecialIssueCombiMelta_InitAbility$$CreateBehaviour` = `AddEffect(0x61b) & AddEffect(0x61c)`
    sur `Owner@DSLSelectors+0x30`), PORTEE DIFFERENTE.

    ## Corps natif, lu VERBATIM (`...$$CreateEffectDamageBonusForAttack`)
    ```
    EffectBonus.ForAddition(
        get_OwnerIsCaster
          & IsAtRange( Caster@DSLSelectors+0x48, Target@DSLSelectors+0x60, DSLFormulas+0x20 )
          & IsNormalAttack,
        ConfigAmount( query, config@this+0x60, GetAbilityState(this), 8 ) )
    ```
    `DSLFormulas+0x20 = Const(1)` (champ PRE-CONSTRUIT du `.ctor`, cf. `effects/base.py::is_at_range`)
    et `IsAtRange` compare par **EGALITE** -> ce bonus mord a la **distance 1 EXACTEMENT**, pas
    « a portee 1 ». `AbilityVariableType(8) = extraDmg`, dans `variablesAffectedByRarityBonus` du kit
    -> x multiplier de rarete.

    ## LA PREDICTION L'APPLIQUE -- mesure, pas hypothese
    Contrairement a `SmashaEadEffect` (dont le port neutralise l'additif en display parce que le noeud
    `IsNormalAttack` y evalue FAUX), l'empreinte NATIVE du §3 de
    `docs/rl/case-419-r1-tr11-special-issue-combi-melta.md` montre le montant plat DANS la prediction :
    a d = 1 le natif annonce `3457-4661` la ou le port sans 1545 annonce `2409-3614`, soit un ECART
    PLAT (+1048 / +1047) -- exactement la signature d'un `ForAddition`. Ce canal n'est donc PAS gate
    par `is_prediction` ; il l'est par `is_normal_attack`, que la facade de prediction d'attaque
    NORMALE passe a VRAI.

    ## CONTEXTE
    `att_ctx` porte deja `att_pos` ET `t_pos` (les deux faces les threadent) -- c'est le canal 1563
    qui exigeait l'enrichissement. Position manquante -> gate FAUX (cf. `is_at_range`)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        if is_normal_attack is False:                 # IsNormalAttack (3e conjoint, LU)
            return None
        c = att_ctx or {}
        if not _is_at_range(c.get("att_pos"), c.get("t_pos"), 1):   # DSLFormulas+0x20 = Const(1)
            return None
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        amt = ability_var("SpecialIssueCombiMelta", "extraDmg", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, int(amt)) if amt else None


# Traits CIBLE qualifiant `IdunBattle.Entities.Effects.Loki.HeavyGravCannonEffect$$DamageCondition` :
# TROIS noeuds `IdunBattleLogic.Entities.DSLTriggers$$HasTrait(factory, factory+0x178 = target, X)` fusionnes par
# `IdunBattle.DSL.AbilityTrigger$$op_BitwiseOr`. `IdunBattle.Entities.Enum.UnitTrait` (dump enums
# gqfc5mff6c) : 5 = Mechanical, 0x3f5 = 1013 MkXGravis, 0x40f = 1039 TerminatorArmour. MEME triple que
# `GravitonRifle_ExtraPierce` (loki/votann.py) -- deux armes anti-blindage du meme moule, sets ecrits
# separement parce que ce sont DEUX listes natives distinctes (aucune constante partagee cote natif).
_HEAVY_GRAV_CANNON_TARGET_TRAITS = frozenset({"Mechanical", "MkXGravis", "TerminatorArmour"})


class HeavyGravCannonEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.HeavyGravCannonEffect` -- **EffectType 1291** (`HeavyGravCannon`),
    passif `HeavyGravCannon` d'`admecDestroyer` <<Sy-Gex>> (AdeptusMechanicus, seul porteur du build).
    DEUX canaux, UNE condition partagee.

    PIEGE D'HOMONYMIE (trois ids distincts, VERIFIES au dump d'enums) :
      * `EffectType` 1291 = `HeavyGravCannon`      <- CET effet (nom capte live) ;
      * `TriggeredAbilityType` 1233 = `HeavyGravCannon` <- l'ABILITY dont on lit la config ;
      * `TriggeredAbilityType` 1291 = `SelfRepairMechanism` (rien a voir).
    `IdunBattle.Entities.Effects.Loki.HeavyGravCannonEffect$$.ctor` =
    `BaseEffect(AbilityOrEffect.op_Implicit(0x4d1 = 1233), 1)` -> les `ConfigVar` ci-dessous se resolvent
    contre la config de l'ABILITY 1233, c.-a-d. `gameconfig.ability("HeavyGravCannon")`
    (`variables` = exactement `{extraDmg, extraPierceRatio}`, `variablesAffectedByRarityBonus = [extraDmg]`).

    CONDITION PARTAGEE -- `IdunBattle.Entities.Effects.Loki.HeavyGravCannonEffect$$DamageCondition`
    (MIRROR du decompile ; les DEUX canaux l'appellent, ce n'est PAS un etage distinct par canal) :

        ( get_OwnerIsActor & IsRangedAttack )
        & ( HasTrait(target, 5) | HasTrait(target, 0x3f5) | HasTrait(target, 0x40f) )

    CANAL 1 -- `...$$CreateEffectDamageBonusForAttack` (MIRROR) :
        `EffectBonus.ForAddition( DamageCondition(this),
                                  ConfigVar(8 = extraDmg, GetAbilityState(this), config@this+0x60) )`
      = FLAT additif sur l'attaque du porteur (canal `DamageModifiers$$Add` @+0x10, applique par coup —
      meme canal que CondemnorStake/BeaconOfRage/SmashaEad). `extraDmg` ∈ `variablesAffectedByRarityBonus`
      -> scale x `AbilityVariablesMultiplier` du porteur.

    CANAL 2 -- `...$$CreatePiercingBonusForAttack` (MIRROR) :
        `EffectBonus.ForPiercing( DamageCondition(this),
                                  ConfigVar(0x3f = 63 extraPierceRatio, GetAbilityState(this), config@+0x60) )`
      = ADDITIF au ratio de percage du coup, sommé par
      `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio`
      (`Min(100, Max(base>0, dirPierce + extraPierce + <ces bonus> + basePiercingRatio))`) — canal port
      `create_effect_piercing_bonus_for_attack` (slot ATTAQUANT, mirror de Hailstrike/GravitonRifle ;
      le slot `create_piercing_bonus_for_attack` est la variante `OwnerIsTarget`, hors sujet ici).
      `extraPierceRatio` est HORS `variablesAffectedByRarityBonus` -> le multiplier y est inerte (40 -> 60).

    NIVEAU : `GetAbilityState(this)` = l'AbilityState de la SOURCE de l'effet ; ici owner == source ==
    porteur (owner-effect d'un PASSIF), et `HeavyGravCannon` est dans `passiveAbilities` d'admecDestroyer
    -> `self.ability_level` (= `unitConfig.passiveAbilityLevel`, ce que `EffectsState.seed` propage),
    repli `self.level`. Niveau inconnu -> inerte (degradation fidele, jamais un `extraDmg[0]` mal indexe).

    GROUND TRUTH (case-101 §3.2, seed 777 MC1_67, Sy-Gex -> necroOverlord qui EST `Mechanical`) :
    `extraDmg[50] x 160% = round(277 x 1.6) = 443` == `live 3510 - offline 3067` EXACT. Le canal PERCAGE y
    est INERTE (`extraPierceRatio[50] = 60` -> pierce_eff 1+60 = 61 %, mais le percage natif est un
    PLANCHER `max(0, d - armor, d x pierce%)` et `d - armor` domine : 5419-1909 = 3510 > 5419 x 0.61) —
    d'ou le 2e montage discriminant (cible a armure haute) qui le fait MORDRE.

    GATE `IsRangedAttack` : tri-etat #106 (`is_ranged is None` = nature non threadee -> le predicat natif
    `BattleQuery$$IsRangedAttack` est FAUX, donc pas de bonus). GATE CIBLE : `target_traits` (None = cible
    inconnue -> pas de bonus, « present != applique »). `get_OwnerIsActor` : ce canal n'est appele QUE pour
    l'attaque du porteur -> implicitement VRAI (== CondemnorStake/SmashaEad) ; le canal PERCAGE, lui, le
    verifie explicitement (`owner_id == att_id`) car son agregateur boucle sur les effets du caster."""

    def _damage_condition(self, is_ranged: "bool | None",
                          target_traits: "frozenset[str] | None") -> bool:
        """`IdunBattle.Entities.Effects.Loki.HeavyGravCannonEffect$$DamageCondition` — volet evaluable
        offline (le `get_OwnerIsActor` est verifie par l'appelant, cf. docstring de classe)."""
        if not is_ranged_attack(is_ranged):                       # IsRangedAttack
            return False
        return bool(target_traits) and not _HEAVY_GRAV_CANNON_TARGET_TRAITS.isdisjoint(target_traits)

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        # `ForAddition(DamageCondition, ConfigVar(8 = extraDmg))`. AUCUN gate no-move / IsNormalAttack /
        # profil : `DamageCondition` est la SEULE condition du decompile.
        if not self._damage_condition(is_ranged, target_traits):
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        if lvl is None:
            return None                                           # ConfigVar sans AbilityState -> inerte
        amt = ability_var("HeavyGravCannon", "extraDmg", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, int(amt)) if amt else None

    def create_effect_piercing_bonus_for_attack(self, ctx=None) -> "int | None":
        """`...$$CreatePiercingBonusForAttack` — bonus ADDITIF au ratio de percage du coup courant.
        `ctx` (fourni par `piercing_bonus_from_effects`) : `{owner_id, att_id, is_ranged, target_traits,
        owner_ctx, ...}` — `owner_id == att_id` mirror `get_OwnerIsActor`, `is_ranged`/`target_traits`
        mirrorent le reste de `DamageCondition`. PAS de `IsOverwatchAttack` (contraste Hailstrike) ni de
        `CurrentAbilityIs` (contraste GravitonRifle) : le decompile n'a que `DamageCondition`."""
        c = ctx or {}
        oid, aid = c.get("owner_id"), c.get("att_id")
        if oid is None or aid is None or oid != aid:              # get_OwnerIsActor
            return None
        if not self._damage_condition(c.get("is_ranged"), c.get("target_traits")):
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        if lvl is None:
            return None
        amt = ability_var("HeavyGravCannon", "extraPierceRatio", lvl,
                          multiplier_pct=self.ability_variables_multiplier)   # hors rarityBonus -> mult inerte
        return int(amt) if amt else None


class ChaliceOfBaalExtraDmgEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.ChaliceOfBaalEffect$$CreateEffectDamageBonusForAttack`
    (`EffectType.ChaliceOfBaal_ExtraDmg` = 0x621 = **1569**) -- MIRROR du decompile :

        EffectBonus.ForAddition( get_OwnerIsActor & IsMeleeAttack & IsNormalAttack,
                                 DSLFormulas$$ConfigVar(AbilityVariableType.extraDmg = 8,
                                                        GetAbilityState(this), <effet+0x60>) )

    Le `ForAddition` est INLINE (le compilo l'a fondu : le `ConfigVar` est ecrit au champ additif
    `+0x10` de la struct, meme layout que `IdunBattle.Entities.Effects.EffectBonus$$ForAddition`) ->
    canal `additive` de `IdunBattle.Core.Services.DamageModifiers$$Add`, applique POST-percage par
    `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`.

    `IdunBattle.Entities.Effects.Loki.ChaliceOfBaalEffect$$.ctor` = `BaseEffect(AbilityOrEffect(
    TriggeredAbilityType.ChaliceOfBaal = 0x60e), true)` -- `mov edx, 0x60e` LU AUX OCTETS, et le
    `call` resout sur `IdunBattle.Core.AbilityOrEffect$$op_Implicit(triggeredAbility:
    TriggeredAbilityType)`, PAS sur les surcharges `ActiveAbilityType` / `EffectType` (les trois
    enums partagent des centaines d'ordinaux, l'ordinal seul n'aurait rien tranche). Le `ConfigVar`
    lit donc l'entree gameconfig **`ChaliceOfBaal`** (`variables.extraDmg`, 10 paliers de RELIQUE).

    POSE : `...ChaliceOfBaalAbility$$CreateBehaviour` -> `AddEffect(0x621, AbilityStateReference,
    source = Owner@DSLSelectors+0x30, targets, turns = <DSLFormulas+0x20> = Direct(1))` sur le
    porteur + ses allies adjacents NON MECANIQUES, pour UN TOUR
    (`runner/operations/triggers/loki/chalice_of_baal.py`).

    GATES, lus et pas devines :
      * `get_OwnerIsActor` -- ce canal n'est appele QUE pour les attaques du PORTEUR de l'effet
        (`_attacker_effect_bonuses` n'itere que les effets de l'attaquant) -> implicitement VRAI,
        comme pour `SmashaEad` / `CondemnorStake` ;
      * `IsMeleeAttack` -- tri-etat #106 (`is_ranged is None` = nature non prouvee -> gate FERME) ;
      * `IsNormalAttack` -- le noeud evalue FAUX en contexte de PREDICTION D'AFFICHAGE (meme
        verdict que `SmashaEad`, #71 : l'`AbilityIsNormalAttackTrigger` n'a aucune ability dans le
        contexte), d'ou le `if is_prediction: return None`.

    `extraDmg` n'est PAS dans un `variablesAffectedByRarityBonus` pour cette entree (la cle est
    absente du gameconfig de `ChaliceOfBaal`) -> `ability_var` rend le multiplicateur inerte ; on le
    passe quand meme, c'est le natif qui decide.

    ⚠ NIVEAU -- le natif resout son `ConfigVar` contre l'`AbilityState` que l'`AddEffect` lui a
    passe, c.-a-d. celui du PORTEUR DE LA RELIQUE (`scale_from_source=True` cote port le propage a
    la pose). `_source_scaling` lit le couple ACTIF/PASSIF de la source, pas son couple TERTIAIRE :
    sur un runner normalise les deux valent 50 et `ability_var` clampe au dernier des 10 paliers,
    donc les deux lectures coincident ; elles divergeraient sur une relique de bas niveau. Meme
    residu que `DawnBlade` avant #357."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        if not is_melee_attack(is_ranged):            # IsMeleeAttack (tri-etat #106)
            return None
        if is_normal_attack is False:                 # IsNormalAttack
            return None
        if is_prediction:                             # cf. docstring (#71, jumeau SmashaEad)
            return None
        # `ConfigVar(extraDmg, GetAbilityState(this), <config ChaliceOfBaal>)` -- l'etat d'ability
        # est le TERTIAIRE du PORTEUR DE LA RELIQUE (cf. `relic_ability_state`). Repli sur les
        # champs de l'effet quand le canal ne l'annonce pas : c'est le cas d'un ALLIE buffe, qui
        # n'equipe pas la relique -- residu NOMME (le niveau du poseur n'est pas propage aux
        # allies ; sur un runner normalise les deux clampent au meme palier).
        r_lvl, r_mult = relic_ability_state(att_ctx, "ChaliceOfBaal")
        lvl = r_lvl if r_lvl is not None else (
            self.active_ability_level if self.active_ability_level is not None
            else (self.ability_level if self.ability_level is not None else self.level))
        mult = r_mult if r_mult is not None else self.ability_variables_multiplier
        amt = ability_var("ChaliceOfBaal", "extraDmg", lvl, multiplier_pct=mult)
        return for_addition(True, amt) if amt else None


class VitarusEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.VitarusEffect$$CreateEffectDamageBonusForAttack`
    (`EffectType.Vitarus` = 0x5ba = **1466**) -- MIRROR du decompile :

        EffectBonus.ForAddition(
              Any( Tiles(Target@DSLSelectors+0x60),
                   HasEffect(<element@+0x68>, EffectType.Fire = 5, onlyActive: false,
                             EffectTargetType.Both = 6) )
            & get_OwnerIsCaster
            & IsMeleeAttack
            & (   IsNormalAttack(CurrentAbility@<DSLSelectors+0x88>)
                | AreEqual(CurrentAbility@<+0x88>,
                           AbilityOrEffect(TriggeredAbilityType.FuryOfTheAncients = 0x4df = 1247)) ),
            DSLFormulas$$ConfigVar(AbilityVariableType.extraDmg = 8, GetAbilityState(this),
                                   <effet+0x60>) )

    `IdunBattle.Entities.Effects.Loki.VitarusEffect$$.ctor` = `BaseEffect(AbilityOrEffect(
    TriggeredAbilityType.Vitarus = 0x5be), true)` (`mov edx, 0x5be` LU aux octets, `call` resolu sur
    la surcharge `TriggeredAbilityType` d'`op_Implicit`) -> le `ConfigVar` lit l'entree gameconfig
    **`Vitarus`** (`variables.extraDmg`, 10 paliers de RELIQUE).

    L'effet est pose sur son porteur A L'INIT par `Vitarus_InitAbility` (parent
    `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility`, dont le seul override est
    `$$GetEffectType` = `return 0x5ba`) -- canal `ABILITY_INIT_OWNER_EFFECTS["Vitarus"]`.

    LE COUPLE EST UN VA-ET-VIENT : la MEME condition gouverne le `CreateBehaviour` de
    `VitarusAbility`, qui ETEINT le feu quand il etait la et le POSE sinon
    (`runner/operations/triggers/loki/vitarus.py`). L'ordre est structurel : ce bonus est calcule
    PENDANT le coup (`damage_model.attacker_modifiers`), le feu est mute APRES l'attaque
    (`On(9 = Attack)`) -- donc « feu present -> +extraDmg PUIS extinction », « feu absent ->
    pas de bonus PUIS ignition ».

    GATES :
      * la tuile de la cible en feu -> foyer PARTAGE `effects/base.py::target_is_on_fire_tile`
        (`t_pos` + `tile_effects_by_pos`, le meme canal que `PsychicStalk`) ;
      * `get_OwnerIsCaster` -- implicitement VRAI sur ce canal (effets de l'ATTAQUANT) ;
      * `IsMeleeAttack` -- tri-etat #106 ;
      * `IsNormalAttack | CurrentAbilityIs(1247)` -- `att_ctx["ability_type"]` porte
        `CurrentAbilityIs` (`None` = voie NORMALE). ⚠ MEME residu que l'ability : le
        `ChainAttackDamage` de `FuryOfTheAncients` n'annonce pas son kind, donc il entre par le
        premier disjoint ; observable identique, cf. `triggers/loki/vitarus.py`.
      * `is_prediction` -- **AUCUN** `if is_prediction: return None` ici, et c'est LU : le natif
        n'a pas de gate de prediction, et son `IsNormalAttack` est VRAI pour l'attaque normale du
        porteur (qui EST dans `decisionView`). Recopier le gate de `SmashaEad` serait la faute
        inverse (cf. `TwistedScience` / `PrimarchOfTheFirstLegion` dans ce meme module).

    ===============================================================================================
    MAGNITUDE ET PLACEMENT -- BIT-CONFRONTES LIVE (#1005-r1, 2026-08-18, build `t6dpr4k06g`)
    ===============================================================================================
    Le residu demandait d'isoler le PLACEMENT du canal additif, en supposant DEUX canaux au choix
    (`for_addition` POST-percage vs `attacker_additive_pre` PRE-percage). **Cette prémisse est
    REFUTEE : il n'y a qu'UN canal, et il est PRE-percage.** Trois sources, deux structurelles et
    une live -- le detail des deux premieres vit au foyer, `services/effect_bonus.py::for_addition` :

      1. DECOMPILE -- `DamagePrediction$$CalculateBaseDamageWithAllModifiers` (l'etage POST-percage)
         ne lit **jamais** `DamageModifiers.Addition@+0x10` ; seulement `@+0x20` / `@+0x28` /
         `@+0x18` / `@+0x30` / l'`Override`. Un additif attaquant ne peut donc pas y etre consomme.
      2. RECENSEMENT -- les 17 call-sites d'`apply_pierce_and_modifiers` sous `engine/**` passent
         TOUS `attacker_additive_pre=True` ; aucun ne passe `False`.
      3. MESURE LIVE DISCRIMINANTE -- montage a variable UNIQUE, qui elimine la variance du roll en
         lisant les BORNES de prediction au lieu des degats tires. `bloodMephiston` porte
         `Vitarus` (`--equip-relic`, `TertiaryAbilityLevel = 1`), un `orksNob` adjacent, board
         `MC1_67`, seed 31337 -- MEME unite, MEME position `(3,4)`, MEME regime d'effets des deux
         cotes (`RapidAssault_*` DEJA consomme aux deux lectures, ce qui est le piege du montage :
         le mesurer avant/apres sa consommation contaminerait le delta). Seule variable : le feu
         sur la tuile de la cible, allume puis eteint par le va-et-vient de `VitarusAbility`.

             feu PRESENT  : [5814 - 7623]        (3 coups de melee, `3hmp100`)
             feu ABSENT   : [3609 - 5418]
             DELTA        :  2205    2205        -- IDENTIQUE sur les DEUX bornes

         `2205 = 3 x 735` et `735 = 490 x 1.5`. Les deux hypotheses se separent NUMERIQUEMENT :

             POST-percage (additif NU)     -> delta attendu = 3 x 490       = 1470   REFUTE
             PRE-percage  (additif SCALE)  -> delta attendu = 3 x 490 x 1.5 = 2205   CONFIRME

         Reconstruction bit-exacte des deux bornes, per-coup : `(802 + 490) x 1.5 = 1938 = 5814/3`
         et `(1204 + 490) x 1.5 = 2541 = 7623/3`. Le facteur `1.5` est le MEME sur min et max, donc
         multiplicatif et applique APRES l'additif -- c'est exactement la signature du PRE-percage.

    ⚠ **UN ECART SUPERIEUR A LA VALEUR NOMINALE N'EST PAS UNE ANOMALIE A FITTER.** Le residu notait
    « ~+539/coup alors que `extraDmg[1] = 490` » et cherchait a reconcilier les 49. Il n'y a rien a
    reconcilier : `490` est la magnitude EXACTE (aucun multiplicateur de rarete -- la liste
    `variablesAffectedByRarityBonus` est ABSENTE du gameconfig de `Vitarus`), et tout ecart mesure
    vaut `extraDmg x <%-mod du coup>`, un facteur qui change d'un montage a l'autre. Fitter le
    scalaire aurait fabrique une constante fausse ; c'est la DECOMPOSITION PAR ETAGE (bornes de
    prediction, variable unique) qui tranche."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        if not is_melee_attack(is_ranged):            # IsMeleeAttack (tri-etat #106)
            return None
        # `IsNormalAttack(CurrentAbility@+0x88) | AreEqual(CurrentAbility@+0x88, 1247)` -- UN SEUL
        # canal, les deux disjoints lisant le MEME selecteur.
        cur = (att_ctx or {}).get("ability_type")
        if cur is not None and int(cur) != int(TriggeredAbilityType.FuryOfTheAncients):
            return None
        if not target_is_on_fire_tile(att_ctx):       # Any(Tiles(Target), HasEffect(Fire))
            return None
        # `ConfigVar(extraDmg, GetAbilityState(this), <config Vitarus>)` : l'etat d'ability est le
        # TERTIAIRE du porteur -- MESURE `level = 1, mult = 100` contre `50 / 180` pour ses passifs
        # (cf. `relic_ability_state`). Cet effet ne vit QUE sur le porteur de la relique, donc la
        # cle est toujours la sur le canal ATTAQUANT ; le repli couvre les appelants historiques.
        r_lvl, r_mult = relic_ability_state(att_ctx, "Vitarus")
        lvl = r_lvl if r_lvl is not None else (
            self.active_ability_level if self.active_ability_level is not None
            else (self.ability_level if self.ability_level is not None else self.level))
        mult = r_mult if r_mult is not None else self.ability_variables_multiplier
        amt = ability_var("Vitarus", "extraDmg", lvl, multiplier_pct=mult)
        return for_addition(True, amt) if amt else None
