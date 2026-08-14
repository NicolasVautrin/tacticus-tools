"""Effets `Effects.Loki` — famille MALUS DE DÉGÂT DÉFENSEUR (`create_effect_damage_malus_for_defense` +
auras de réduction). Réduit le dégât REÇU par le porteur (ou par ses alliés / l'ennemi via aura).
1 classe par effet natif (VA citée). Cf. `loki/__init__.py`."""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import (EffectBonus, for_addition, for_piercing, for_subtraction,
                                       for_percent_decrease, for_percent_increase,
                                       for_percent_subtraction_capped)
from ..base import BaseEffect, is_turn_of_owner
from ..magnitude import ability_var, bc_effect_config, global_value, trait_var
from ...rarity import Rarity            # `idun.meta.Rarity` -- gate `HasRarity` (#1025-r1)
from ...traits.unit_trait import is_mechanical   # `UnitExtensions$$IsMechanical` -- foyer UNIQUE
# `StaticBattleRules.Effect$$IsTileStatusEffect` par NOM -- le set que
# `TileExtensions$$HasTileStatusEffect` interroge (#1038-r1). MEME import que `loki/hits.py`.
from ....services.static_battle_rules import TILE_STATUS_EFFECT_NAMES


class MarkerlightEffect(BaseEffect):
    """`MarkerlightEffect` (effet **1122=0x462**, `Entities.Effects.Loki`) — la cible est « marquée ».
    `.IdunBattle.Entities.Effects.Loki.MarkerlightEffect$$.ctor` = `DamageModifierAbilityEffect..ctor(this, 0x462, Nullable(1))`.
    `IdunBattle.Entities.Effects.Loki.MarkerlightEffect$$CreateDamageModifier` : trigger = `OwnerIsTarget & HasFaction(actor@0x158, 9=T'au, 3)
    & IsRangedAttack` ; bonus = `EffectBonus.ForPercentIncrease(Direct(GetEffectConfig(4)))` —
    slot service 0xbe(4) = la règle GLOBALE `MarkerlightDmgBonusPct` de la section BC `Effect`
    (`unitEffectVariables.markerlightDmgBonusPct` = **15** ; même mécanisme `IdunBattle.Core.Services.BattleQuery$$InitEffectConfig` que Pinned EffectConfig(0/1)).

    ⇒ malus DÉFENSEUR : les attaques **RANGED** d'un attaquant **T'au** contre le porteur font
    **+15 %**. Gates lus du contexte : `is_melee is False` (RANGED prouvé ; None = nature inconnue →
    None, présent ≠ appliqué) + `attacker_ctx["faction"] == "Tau"` (threadé par
    `damage_model.defender_modifiers` ; absent → None).

    Pose (MV71SniperDroneSquadAttack IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour étape (e)) : sur la CIBLE, durée
    `Sum(TurnsFromRounds(1), Direct(1))` = fin du prochain tour du caster — identique à
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.StructuralAnalyser_AddMarkerlightAbility$$CreateBehaviour`.
    ⚠ NON porté (flaggé) : le retrait au HEAL/REPAIR de la cible (i2 « Healing or repairing removes
    the effect ») — cycle de vie durée-seule offline."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if is_melee is not False:                              # gated IsRangedAttack (None = inconnu)
            return None
        # #437-r1-r1-r1 -- FACE : cf. `DEFENSE_MALUS_NATIVE_FACE` ci-dessous.
        if not (attacker_ctx and attacker_ctx.get("faction") == "Tau"):   # HasFaction(actor, 9=T'au)
            return None
        pct = bc_effect_config("MarkerlightDmgBonusPct", 15)   # règle globale (unitEffectVariables)
        if not pct:
            return None
        return for_percent_increase(False, int(pct))           # owner=défenseur (dégât REÇU +15 %)

    # #437-r1-r1-r1 : `MarkerlightEffect` derive de `DamageModifierAbilityEffect` (classes.tsv) et
    # n'implemente QUE `CreateDamageModifier` (methods.tsv) -> sa contribution sort par le forwarder
    # `IdunBattle.Entities.Effects.DamageModifierAbilityEffect$$CreateEffectDamageBonusForAttack`,
    # que seul `CalculateAttackerModifiersForPrediction` invoque : le natif la verse donc dans
    # `attackModifiers`, MALGRE le trigger `OwnerIsTarget`. CONSEQUENCE ARITHMETIQUE REELLE (canal
    # POURCENT) : le `+15 %` prend le `Round` de la face ATTAQUANTE.
    DEFENSE_MALUS_NATIVE_FACE = "attacker"


class ExemplarOfHateTargetEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.ExemplarOfHate_TargetEffect` (effet **1293=0x50d**) — pose sur la
    CIBLE par `IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfHateAbility$$ExecuteBehaviour`
    (`AddEffect(0x50d, stateRef, source=caster@0x160, target@0x178, TurnsFromRounds(2))`, #112).

    `IdunBattle.Entities.Effects.Loki.ExemplarOfHate_TargetEffect$$CreateEffectDamageBonusForAttack`
    (MIRROR du DECOMPILE) :
        trigger = get_OwnerIsTarget & ( IsMeleeAttack | IsOverwatchAttack )
        montant = ConfigVar(8 = extraDmg, GetAbilityState(effect), config@+0x60)
        -> EffectBonus ADDITIF (le corps est INLINE : la struct construite pose le montant au champ
           +0x10, EXACTEMENT le slot ecrit par `IdunBattle.Entities.Effects.EffectBonus$$ForAddition`
           (`param_1[2] = amount`) et distinct de ForPercentIncrease (+0x08) / ForSubtraction (+0x18) /
           ForOverride (+0x28)).
    i2 : « For this round and the next, all friendly units deal +<extraDmg> Damage against that enemy
    with melee or Overwatch attacks. »

    Malgre le nom natif « ...ForAttack », le trigger est `OwnerIsTarget` : l'effet vit sur la VICTIME et
    MAJORE le degat qu'elle RECOIT -> canal PORT `create_effect_damage_malus_for_defense` (le meme mold
    que `NeuroparasiteEffect`, dont la docstring documente l'additif POSITIF cote defenseur).

    MAGNITUDE : `ConfigVar` resolu contre l'`AbilityState` de la SOURCE (Asmodai) -> l'`AddEffect` du port
    passe `scale_from_source=True` (niveau d'ability + multiplier de rarete du poseur seedes sur
    l'instance). `extraDmg` EST dans `variablesAffectedByRarityBonus` (554 @mult100 -> 997 @mult180).

    RESIDU FLAGGE : la branche `IsOverwatchAttack` du `op_BitwiseOr` n'est PAS threadee (le port ne
    distingue pas un coup d'overwatch d'un coup ranged ordinaire au site de resolution defenseur) ->
    seule la moitie MELEE contribue. Un tir d'overwatch ne recoit donc pas le +extraDmg : c'est un
    MANQUE, jamais un sur-compte."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if is_melee is not True:              # IsMeleeAttack (prouve melee) ; IsOverwatchAttack = residu
            return None
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else self.ability_level)       # ExemplarOfHate = ability ACTIVE du poseur
        v = ability_var("ExemplarOfHate", "extraDmg", lvl,
                        multiplier_pct=self.ability_variables_multiplier)
        return for_addition(False, int(v)) if v else None      # owner=cible -> additif au degat RECU

    # #437-r1-r1-r1 : le natif implemente `CreateEffectDamageBonusForAttack` (methods.tsv) -> face
    # ATTAQUANT, malgre le trigger `OwnerIsTarget` (le nom natif le disait deja, la docstring
    # ci-dessus l'avait lu, mais le port en tirait la face du BUILDER et non du SLOT).
    # ⚠ REGIME DEGENERE, et c'est pourquoi rien ne bouge : le canal est ADDITIF (`Addition@+0x10`),
    # et `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` SOMME le `+0x10` des DEUX
    # accumulateurs avant `CalculateBaseDamageWithAllModifiers` (RE #462-r4b-r1). Les deux
    # attributions predisent donc EXACTEMENT le meme nombre. On pose la face parce qu'elle est LUE,
    # pas parce qu'elle changerait un resultat.
    DEFENSE_MALUS_NATIVE_FACE = "attacker"


class ChronometronExtraDamageEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.Chronometron_ExtraDamageEffect` (effet **1550 = 0x60e**) — pose
    sur CHAQUE ennemi du disque rayon 2 autour du caster par
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ChronometronAbility$$ExecuteBehaviour`
    (`necroChronomancer` « Thothmek », active 1226).

    `IdunBattle.Entities.Effects.Loki.Chronometron_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`
    (MIRROR du DECOMPILE, corps INLINE) :

        trigger =   get_OwnerIsTarget
                  & IsUnit(caster@0x160)
                  & AreFriends(caster@0x160, EffectSource(Effect@0x150))
        montant =   Multiply( If( IsMechanical(caster@0x160),
                                  ConfigVar(9 = extraDmg_2),      # branche VRAIE
                                  ConfigVar(8 = extraDmg) ),      # branche FAUSSE
                              TimesEffectApplied(Effect@0x150) )
        source  =   Nullable<AbilityOrEffect>(0x4ca = 1226 Chronometron)

    KIND = **ForAddition** (additif PLAT, pas un pourcentage) : le corps inline ecrit le montant au champ
    `+0x10` de la struct `EffectBonus`, EXACTEMENT le slot qu'ecrit
    `IdunBattle.Entities.Effects.EffectBonus$$ForAddition` (`param_1[2] = amount`) — distinct de
    ForPercentIncrease (`+0x08`), ForSubtraction (`+0x18`), ForOverride (`+0x28`). Meme lecture que
    `ExemplarOfHateTargetEffect` ci-dessus.

    Malgre le nom natif « ...ForAttack », le trigger est `OwnerIsTarget` : l'effet vit sur la VICTIME et
    MAJORE le degat qu'elle RECOIT -> canal PORT `create_effect_damage_malus_for_defense` (meme mold que
    `ExemplarOfHateTargetEffect` / `NeuroparasiteEffect`, qui documentent l'additif POSITIF cote defenseur).

    LES TROIS ENTREES, et d'ou elles viennent (residu transverse R9 — c'etait le trou : l'effet etait
    MATERIALISE mais INERTE faute de contexte) :
      1. `AreFriends(caster, EffectSource(Effect))` = l'attaquant est un ALLIE du Chronomancer.
         `EffectSource(Effect@0x150)` = `IdunBattleLogic.Entities.DSLFactory$$EffectSource` sur l'entite-effet
         COURANTE = `EffectComponent.SourceUnit @+0x10` = `self.source` cote port. On resout SON equipe via
         `attacker_ctx["team_by_id"]` (l'attaquant, lui, donne `attacker_ctx["team"]`).
      2. `IsMechanical(caster)` = `IdunBattleLogic.Entities.DSLFactory$$IsMechanical`, qui construit
         `AmountIsEqualOrGreater(TraitAmountSelector(caster, Mechanical), Value(1))` — le `3` du 3e argument
         est le mode de recherche partage (`HasFaction(…, 0x14, 3)` le passe aussi), PAS un id de trait.
         => `HasTrait(caster, Mechanical)`, lu dans `attacker_ctx["traits"]`.
         ⚠ Le gate porte sur l'**ATTAQUANT**, pas sur la cible.
      3. `TimesEffectApplied(Effect)` = `EffectComponent.TimesApplied @+0x6c` de CETTE instance
         (`BaseEffect.times_applied`, defaut natif **1**) — cf. son commentaire dans `base.py`.

    CYCLE DE VIE — c'est une CHARGE A USAGE UNIQUE, pas un buff persistant :
    `...$$CreateRemoveEffectTrigger` = `On(9) & OwnerIsTarget & IsUnit(caster) & AreFriends(caster,
    EffectSource)` -> l'effet est CONSOMME a la fin du 1er coup d'un allie du Chronomancer (porte par
    `runner/operations/triggers/loki/chronometron.py`, `EFFECT_TRIGGERS[1550]`).

    MAGNITUDE : `ConfigVar` resolu contre l'`AbilityState` de la SOURCE (le Chronomancer) -> l'`AddEffect`
    du port passe `scale_from_source=True`. `extraDmg` ET `extraDmg_2` sont dans
    `variablesAffectedByRarityBonus` -> les deux subissent le multiplier de rarete du poseur."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        ac = attacker_ctx or {}
        if ac.get("id") is None or not ac.get("is_unit"):      # IsUnit(caster@0x160)
            return None
        # AreFriends(caster@0x160, EffectSource(Effect@0x150)) — l'attaquant et le POSEUR de l'effet.
        a_team = ac.get("team")
        s_team = (ac.get("team_by_id") or {}).get(self.source) if self.source is not None else None
        if a_team is None or s_team is None or a_team != s_team:
            return None                                        # equipe inconnue -> gate muet (fidele)
        # If(IsMechanical(caster), ConfigVar(9=extraDmg_2), ConfigVar(8=extraDmg))
        # ⚠ #116-e -- `IdunBattle.Entities.UnitExtensions$$IsMechanical` est une DISJONCTION de
        # TROIS traits (`Mechanical` 5 | `LivingMetal` 0x3e8 | `Vehicle` 0x405), pas le seul
        # `Mechanical`. Ce site testait `"Mechanical" in traits` : FAUX et silencieux -- un Necron
        # porte `LivingMetal` sans `Mechanical`, et Chronometron est une ability NECRON, donc ses
        # allies sont massivement dans ce cas. Le raccourci ne levait pas : il lisait l'AUTRE
        # branche du `If`, soit `extraDmg` au lieu d'`extraDmg_2`.
        var = "extraDmg_2" if is_mechanical(ac.get("traits")) else "extraDmg"
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else self.ability_level)                        # Chronometron = ability ACTIVE du poseur
        v = ability_var("Chronometron", var, lvl, multiplier_pct=self.ability_variables_multiplier)
        if not v:
            return None
        n = int(self.times_applied or 0)                       # Multiply(…, TimesEffectApplied(Effect))
        if n <= 0:
            return None
        return for_addition(False, int(v) * n)                 # owner=cible -> additif au degat RECU

    # #437-r1-r1-r1 : natif = `CreateEffectDamageBonusForAttack` (methods.tsv) -> face ATTAQUANT,
    # malgre le trigger `OwnerIsTarget`. REGIME DEGENERE (canal ADDITIF `Addition@+0x10`, somme sur
    # les DEUX accumulateurs par `PredictAttackRaw`, RE #462-r4b-r1) : les deux attributions
    # predisent le meme nombre. Posee parce qu'elle est LUE.
    DEFENSE_MALUS_NATIVE_FACE = "attacker"


class HeraldOfTheApocalypseExtraDamageEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.HeraldOfTheApocalypse_ExtraDamageEffect` (effet **1027 = 0x403**)
    -- pose sur la cible ET sur l'ennemi DIRECTEMENT DERRIERE elle par
    `IdunBattleLogic.Entities.Abilities.Active.Loki.HeraldOfTheApocalypseAbility$$ExecuteBehaviour`
    (`blackHaarken` << Haarken Worldclaimer >>, active 1020). #BL-1020r, case-bl-1029-1020 Sec.5.2.

    `IdunBattle.Entities.Effects.Loki.HeraldOfTheApocalypse_ExtraDamageEffect$$
    CreateEffectDamageBonusForAttack` (MIRROR du DECOMPILE, build `rnca9r7q6c`) :

        trigger = get_OwnerIsTarget & IsUnit(caster@DSLSelectors+0x48)
        montant = ConfigVar( 8 = extraDmg, GetAbilityState(effet), config@effet+0x60 )
        source  = Nullable<AbilityOrEffect>( 0x3fc = 1020 HeraldOfTheApocalypse )
        -> EffectBonus.ForAddition(trigger, montant)

    KIND = **ForAddition** : l'appel `IdunBattle.Entities.Effects.EffectBonus$$ForAddition` est EXPLICITE
    dans le decompile (pas inline, contrairement a `ExemplarOfHate` / `Chronometron` ci-dessus) -> additif
    PLAT, canal `Addition@+0x10` de `IdunBattle.Core.Services.DamageModifiers$$Add`.

    DEUX conjoints, et RIEN d'autre -- pas de `IsMeleeAttack`, pas de `DamageProfileIs`, pas d'`AreFriends`
    (contraste avec ses deux jumeaux de ce module). Le bonus vaut donc pour l'attaque de N'IMPORTE QUELLE
    unite, alliee ou ennemie du poseur, en melee comme a distance. i2 : << Affected enemies receive
    +<extraDmg> Damage from the next attack made by a unit against them. >>

    Malgre le nom natif << ...ForAttack >>, le trigger est `OwnerIsTarget` : l'effet vit sur la VICTIME et
    MAJORE le degat qu'elle RECOIT -> canal PORT `create_effect_damage_malus_for_defense` (meme mold que
    `ExemplarOfHateTargetEffect` / `ChronometronExtraDamageEffect` / `NeuroparasiteEffect`).

    CYCLE DE VIE -- CHARGE A USAGE UNIQUE (<< the NEXT attack >>) :
    `...$$CreateRemoveEffectTrigger` (et son jumeau `$$GetRemoveTrigger`, corps identiques) =
    `On(9 = EventTriggerType.Attack, ownerNeedsToBeAlive = 1) & get_OwnerIsTarget & IsUnit(caster)` ->
    `IdunBattle.Entities.Effects.BaseEffect$$GetRemoveEffectBehaviour` = `RemoveEffect(<cette instance>)`.
    Porte par `runner/operations/triggers/loki/herald_of_the_apocalypse.py` (`EFFECT_TRIGGERS[1027]`).
    Sans ce retrait le port donnerait un bonus PERMANENT la ou le natif donne UNE charge -- c'est la
    lecon de `chronometron.py`, et c'est pourquoi les deux volets sont dans la meme tranche.

    MAGNITUDE : `ConfigVar` resolu contre l'`AbilityState` de la SOURCE (Haarken) -> l'`AddEffect` de
    `runner/abilities/blacklegion.py` passe `scale_from_source=True`. `extraDmg` EST dans
    `variablesAffectedByRarityBonus` (avec `minDmg`/`maxDmg`/`armorReduction`) -> scale par le multiplier
    de rarete du poseur. `extraDmg[L1..65] = [18 .. 1310]` ; i2 << +1310 Damage >> = `extraDmg[65]`.

    ⚠ `armorReduction` (4e variable de la config 1020) n'est lu NI par l'`ExecuteBehaviour` de 1020 NI
    par cet effet : variable d'inventaire, non portee (case-bl-1029-1020 Sec.3)."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        ac = attacker_ctx or {}
        if ac.get("id") is None or not ac.get("is_unit"):      # IsUnit(caster@DSLSelectors+0x48)
            return None
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else self.ability_level)                        # HeraldOfTheApocalypse = ability ACTIVE
        v = ability_var("HeraldOfTheApocalypse", "extraDmg", lvl,
                        multiplier_pct=self.ability_variables_multiplier)
        return for_addition(False, int(v)) if v else None      # owner=cible -> additif au degat RECU

    # #437-r1-r1-r1 : le natif implemente `CreateEffectDamageBonusForAttack` (symbole PROPRE dans la
    # table, pas un forwarder `DamageModifierAbilityEffect`) -> le natif verse dans `attackModifiers`,
    # malgre le trigger `OwnerIsTarget`. REGIME DEGENERE, comme ses deux jumeaux : le canal est ADDITIF
    # (`Addition@+0x10`) et `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` SOMME le
    # `+0x10` des DEUX accumulateurs avant `CalculateBaseDamageWithAllModifiers` (RE #462-r4b-r1) --
    # les deux attributions predisent le meme nombre. Posee parce qu'elle est LUE.
    DEFENSE_MALUS_NATIVE_FACE = "attacker"


class SuperchargeExtraPiercingEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.Supercharge_ExtraPiercingEffect` (effet **1208=0x4b8**) — pose sur
    la cible ET les <=2 unites derriere elle par
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SuperchargeAbility$$ExecuteBehaviour`
    (`AddEffect(0x4b8, stateRef, caster@0x160, op_Addition(target@0x178, behind), TurnsFromRounds(1))`).

    `IdunBattle.Entities.Effects.Loki.Supercharge_ExtraPiercingEffect$$CreatePiercingBonusForAttack`
    (MIRROR du DECOMPILE) :
        profile = AbilityConfiguration.GetDamageProfile(config@+0x60)          # Plasma
        trigger = DamageProfileIs(profile) & get_OwnerIsTarget
        montant = ConfigVar(0x3f = extraPierceRatio, GetAbilityState(effect), config@+0x60)
        -> EffectBonus.ForPiercing(trigger, montant)      # axe PERCAGE @+0x20, PAS le scalaire degat
    i2 : « ... all with +<extraPierceRatio>% pierce ratio. Until the beginning of Sarquael's next turn,
    any further hits that deal Plasma Damage against these units also have +<extraPierceRatio>% pierce
    ratio. »

    Canal PORT = `create_piercing_bonus_for_attack` (slot d'interface DEDIE, agrege par
    `build_defender_modifiers_from_effects` puis fusionne dans le percage effectif par
    `AttackDamageOperation._apply_defender_flat_reductions` : `pierce_eff = clamp(pierce + extra, 0,100)`).
    Le profil vient de la CONFIG de l'ability source (`Supercharge.constants.damageProfile` = Plasma), pas
    d'un litteral. Magnitude indexee par l'`AbilityState` du poseur -> `scale_from_source=True` a la pose
    (`extraPierceRatio` n'est PAS dans `variablesAffectedByRarityBonus` -> multiplier inerte)."""

    def create_piercing_bonus_for_attack(self, damage_profile: str | None = None,
                                         is_melee: bool | None = None) -> EffectBonus | None:
        import gameconfig as _GC
        prof = ((_GC.ability("Supercharge") or {}).get("constants") or {}).get("damageProfile")
        if not prof or (damage_profile or "") != prof:         # DamageProfileIs(GetDamageProfile(config))
            return None
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else self.ability_level)                        # Supercharge = ability ACTIVE du poseur
        v = ability_var("Supercharge", "extraPierceRatio", lvl,
                        multiplier_pct=self.ability_variables_multiplier)
        return for_piercing(False, int(v)) if v else None      # owner=cible (percage de QUI l'attaque)


class TerrifyingExtraDefenseEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Terrifying_ExtraDefense_Effect$$CreateDamageModifier : réduit le dégât MÊLÉE reçu par
    son PORTEUR (l'effet est sur la CIBLE). Trigger natif = `get_OwnerIsTarget & IsMeleeAttack`
    (AbilityOrEffect 0x62) ; valeur = `ConfigConst(0x28)`.

    ⚠ Le trait `Terrifying` (id 0x22=34) N'EST PAS lu en direct dans le calcul de dégât (≠ MkXGravis
    `HasTrait(cible, 0x3f5)` IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor). Il DÉRIVE une triggered ability qui pose CET effet sur le porteur
    — chaîne RE'd intégralement (#73) : `Trait..idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor` dict `GetTriggeredAbility` (+0x0, lu par
    `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetTriggeredAbility`) mappe trait 0x22 -> TriggeredAbilityType 0x62 ;
    `IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities` ajoute cette ability (`TerrifyingAbilityAbility`
    IdunBattleLogic.Entities.Abilities.Active.TerrifyingAbilityAbility$$.ctor = `AOwnerEffectSpecificTriggeredAbility(0x62)`) ; son `IdunBattle.Entities.Abilities.AOwnerEffectSpecificTriggeredAbility$$CreateTrigger` =
    `OnOwnerSpecificAbilityInit(0x62)` -> à l'init du porteur, sa behaviour `AddEffect(owner,
    Terrifying_ExtraDefense 0x62)`. Effet enregistré `EffectsDatabase.<InitializeEffects>b__14_11`. Côté
    port : matérialisé pour un porteur CAPTÉ live (`decisionView.effects`, ex. eldarMauganRa) et, faute de
    capture (summon spawné), seedé via `TRAIT_DERIVED_ABILITIES["Terrifying"]` (factory.py).

    Magnitude = `ConfigConst(0x28)` = `clientGameConfig.globalValues.terrifyingBonus` (= **-30**, signé comme
    `elevationBonus`=+50 / `trenchBonus`=-50) — LU en gameconfig (PAS un trait var : `trait("Terrifying")`
    est vide). ⇒ malus défenseur `PercentDecrease(|−30|)` = ×0.70 gated `IsMeleeAttack` (no-op sur attaque
    ranged / contexte inconnu). VALIDÉ bit-exact LIVE (#73, eldarMauganRa : per-hit combat offline == live en
    mêlée ×0.70 ET ranged ×1.0)."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if not is_melee:                         # gated IsMeleeAttack
            return None
        # ConfigConst(0x28) = globalValues.terrifyingBonus (= -30 signé, mirror elevation/trench @globalValues).
        red = global_value("terrifyingBonus")
        if not red:
            return None
        return for_percent_decrease(False, abs(int(red)))   # owner_is_caster=False (effet sur le défenseur) -> x0.70

    # #437-r1-r1-r1 -- LE CAS QUI A NOMME LE RESIDU. `Terrifying_ExtraDefense_Effect` derive de
    # `DamageModifierAbilityEffect` (classes.tsv) et n'implemente QUE `CreateDamageModifier`
    # (methods.tsv) : sa contribution sort par le forwarder
    # `IdunBattle.Entities.Effects.DamageModifierAbilityEffect$$CreateEffectDamageBonusForAttack`,
    # invoque par le SEUL `CalculateAttackerModifiersForPrediction` -> le natif la verse dans
    # `attackModifiers`, bien que l'effet vive sur la CIBLE (`OwnerIsTarget`).
    # CONFIRME A LA MESURE (capteur `effect-bonus-trace`, #466) : sur le montage `--two-faces` de
    # #462-r4a, UN SEUL accumulateur compose `1 -> 0.6999999999534339 -> 1.0499999998137355`, les
    # DEUX bonus etant etiquetes `face=attacker`. Consequence : `Round(725 x 1.50 x 0.70)` = 761
    # natif, contre 762 si le `x0.70` prenait un `Round` a lui.
    DEFENSE_MALUS_NATIVE_FACE = "attacker"


class MartialKatahDmgReductionEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.MartialKatah_DmgReductionEffect$$CreateDamageModifier` (trait MartialKatah, Custodes
    ex. custoTrajann / custoVexilusPraetor) : réduit le dégât des ATTAQUES NORMALES reçues par son PORTEUR.
    Trigger natif = `OwnerIsTarget & IsNormalAttack` (DSLFactory.get_OwnerIsTarget & IsNormalAttack, op&) ;
    valeur = `ConfigConst(0x72)` = `martialKatahDmgReductionPct` (=20) ; kind `EffectBonus.ForPercentDecrease`.
    ⇒ malus défenseur `PercentDecrease(20)` GATÉ `IsNormalAttack` (no-op sur les spéciales config-based).
    i2 : « Normal attacks against this unit deal -{dmgReductionPct}% Damage. » (le +extraDmgPct% vs Summons
    est l'effet SÉPARÉ MartialKatah_DmgBonus, canal attaquant.)

    Gate `IsNormalAttack` : lu via `attacker_ctx["is_normal_attack"]` (threadé par la PRÉDICTION —
    make_normal_attack_predictions=True, generate_multi_hit_attack_prediction=False). Absent (combat runner,
    att_ctx sans le flag) → None = INERTE (port PRÉDICTION-first, cf. GuardianOrganism #89/#91). L'effet est
    sur le DÉFENSEUR → `owner_is_caster=False`."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if not (attacker_ctx and attacker_ctx.get("is_normal_attack")):   # gated IsNormalAttack
            return None
        red = trait_var("MartialKatah", "martialKatahDmgReductionPct")     # ConfigConst 0x72 (=20)
        if not red:
            return None
        return for_percent_decrease(False, abs(int(red)))   # owner=défenseur (l'effet est sur la cible)

    # #437-r1-r1-r1 : `MartialKatah_DmgReductionEffect` derive de `DamageModifierAbilityEffect`
    # (classes.tsv) et n'implemente QUE `CreateDamageModifier` (methods.tsv) -> face ATTAQUANT,
    # malgre le trigger `OwnerIsTarget`. CONSEQUENCE ARITHMETIQUE REELLE (canal POURCENT) : le
    # `x0.80` prend le `Round` de la face attaquante. ⚠ Son JUMEAU `MartialKatah_DmgBonus` est,
    # lui, un `CreateEffectDamageBonusForAttack` direct -- les DEUX volets du MEME trait sont donc
    # sur la MEME face, ce qui n'etait pas le cas avant ce correctif.
    DEFENSE_MALUS_NATIVE_FACE = "attacker"


class PrioritisedEfficiencyDmgReductionEffect(BaseEffect):
    """`PrioritisedEfficiency_DmgReduction` (EffectType 0x5cb=**1483**) — volet DEFENSIF de la stance
    « Fortify Takeover » du trait `PrioritisedEfficiency` (1059, 7 porteurs Votann : 4 heros + le summon
    `votanSmnSteeljack` + 2 npc — cf. extra_damage.py). Jumeau exact de
    `PrioritisedEfficiencyExtraDmgEffect` (extra_damage.py) : MEME trait, MEME source de config, face
    opposee du pipeline. #121.

    MIRROR 1:1 de
    `IdunBattle.Entities.Effects.Loki.PrioritisedEfficiency_DmgReductionEffect$$CreateEffectDamageMalusForDefense` :

        EffectBonus.ForPercentDecrease( DSLFactory.get_OwnerIsTarget,
                                        DSLFactory.ConfigConst(0x72, source@effet+0x60) )

    Aucun autre noeud : PAS de gate `IsNormalAttack` (≠ `MartialKatah_DmgReduction` ci-dessus, meme
    ConfigConst 0x72 mais gate normal-only), PAS de gate melee/profil, pas d'`ActiveCondition`.
    ⇒ −`prioritisedEfficiencyDmgReductionPct` % (= 33) sur **TOUT** degat recu par le porteur, quel
    que soit le vecteur — i2 : « Fortify Takeover: Takes -{[dmgReductionPct]}% Damage. »

    `ConfigConst(0x72)` = constante `dmgReductionPct` de la config de la triggered derivee du trait
    (`AbilityOrEffect(0x5ce = 1486 = TriggeredAbilityType.PrioritisedEfficiency)`, pose par le ctor
    `IdunBattle.Entities.Effects.Loki.PrioritisedEfficiency_DmgReductionEffect$$.ctor`) → gameconfig
    `globalValues.traitVariables.prioritisedEfficiencyDmgReductionPct`. `owner_is_caster=False` :
    l'effet vit sur le DEFENSEUR (`get_OwnerIsTarget`).

    POSE (hors perimetre #121) :
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.APrioritisedEfficiencyAbility$$GetSetDefensiveStanceBehaviour`
    (`RemoveAllStanceEffects & AddEffect(1480 marqueur) & AddEffect(1483 CET effet) &
    SetPersistentData(...)`) — substrat persistent-data absent du port, l'effet est SEEDE depuis
    `decisionView.effects`."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        # ConfigConst(0x72) = trait var `prioritisedEfficiencyDmgReductionPct` (= 33). Le natif
        # n'a QUE `get_OwnerIsTarget` -> aucun gate ici.
        red = trait_var("PrioritisedEfficiency", "prioritisedEfficiencyDmgReductionPct")
        if not red:
            return None
        return for_percent_decrease(False, abs(int(red)))   # owner=defenseur (l'effet est sur la cible)


class VexillaMagnificaDmgReductionEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.VexillaMagnifica_DmgReductionEffect$$CreateDamageDefenseModifier` (active
    VexillaMagnifica 1183, custoVexilusPraetor — effet 0x567=1383, nom capté
    "VexillaMagnifica_DmgReduction") : réduit le dégât reçu par son PORTEUR. #29 lead 2 (la pièce
    ×0.34 du miss 777 s15).

    Trigger natif = `get_OwnerIsTarget` SEUL (décompilé IdunBattle.Entities.Effects.Loki.VexillaMagnifica_DmgReductionEffect$$CreateDamageDefenseModifier : AUCUN gate profil/mêlée/normal)
    → s'applique à TOUT dégât reçu, prédiction ET combat. Valeur = `ConfigVar(0x46=dmgReductionPct,
    GetAbilityState(effet))` = `dmgReductionPct[ablvl]` des variables VexillaMagnifica (=66 à tous
    les niveaux utiles, HORS variablesAffectedByRarityBonus → multiplier no-op ; même clé 0x46 que
    SmashaEad/GuardianOrganism/OverwhelmingWrath). `EffectBonus.ForPercentDecrease` → entrée %-list
    multiplicative standard. VALIDÉ BIT-EXACT (777 s15, u83 stunné -> u87 porteur) :
    ×0.8 (MartialKatah) × 0.5 (Stunned) × 0.34 (CE malus) = 219-437 == natif.

    NB : l'effet est posé par le toggle actif VexillaMagnifica (le porteur « plante la bannière ») —
    la POSE runner-face n'est pas portée ; ici on consomme l'effet CAPTÉ (présent = actif)."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        red = ability_var("VexillaMagnifica", "dmgReductionPct", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        if not red:
            return None
        return for_percent_decrease(False, abs(int(red)))   # owner=défenseur (l'effet est sur la cible)


_TERMINATOR_EXCLUDED: "frozenset[str] | None" = None


def _terminator_excluded_profiles() -> "frozenset[str]":
    """Profils de dégât PERÇANT le TerminatorArmour (`terminatorArmourExcludedDmgProfiles` du trait,
    = "Psychic,DirectDamage") → set de noms. Lu une fois en gameconfig, mis en cache."""
    global _TERMINATOR_EXCLUDED
    if _TERMINATOR_EXCLUDED is None:
        raw = ""
        try:
            import gameconfig as _GC
            raw = ((_GC.trait("TerminatorArmour") or {}).get("variables") or {}).get(
                "terminatorArmourExcludedDmgProfiles") or ""
        except Exception:
            raw = ""
        _TERMINATOR_EXCLUDED = frozenset(p.strip() for p in raw.split(",") if p.strip())
    return _TERMINATOR_EXCLUDED


class TerminatorArmourReduceDmgEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.TerminatorArmour_ReduceDmg_Effect$$CreateEffectDamageMalusForDefense : réduit de
    `terminatorArmourDmgReduction`% (=-75) le dégât reçu par son PORTEUR, SAUF si le profil de dégât de
    l'attaque figure dans `terminatorArmourExcludedDmgProfiles` (=Psychic,DirectDamage). Trigger natif =
    `OwnerIsTarget & NOT DamageProfileIs(excludedArray)` (ConfigConst 0x4c=reduction, 0x52=array via
    `EffectBonus.ForPercentIncrease`) — NON gated mêlée (≠ Terrifying, s'applique mêlée ET ranged).
    Valeurs LUES en gameconfig (trait TerminatorArmour), -75% confirmé LIVE (u96 encaisse 904 vs u94 3616,
    même attaquant → ratio 0.25 = -75%)."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        red = trait_var("TerminatorArmour", "terminatorArmourDmgReduction")   # -75 (magnitude 75)
        if not red:
            return None
        if damage_profile and damage_profile in _terminator_excluded_profiles():
            return None                                     # profil perçant (Psychic/DirectDamage) → pas de réduction
        return for_percent_decrease(False, abs(int(red)))   # owner=défenseur (l'effet est sur la cible)


class GuardianOrganismDamageReductionEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.GuardianOrganism_DamageReductionEffect$$CreateEffectDamageMalusForDefense` (trait
    GuardianOrganism, tanks Tyranides ex. tyranTyrantGuard) : réduit le dégât REÇU par son porteur de
    `min(dmgReductionPct% × CurrentDamage, dmgReduction[cap] × mult)` — `EffectBonus.ForSubtraction(
    OwnerIsTarget, Min(PercentageOf(CurrentDamage, ConfigVar(0x46)), ConfigVar(0x12)))`. Réduction
    DYNAMIQUE (fraction du dégât courant) + CAPÉE absolue -> kind `PercentSubtractionCapped` (≠ un simple
    PercentDecrease : le cap plafonne le MONTANT soustrait, pas le %).
      - pct = ConfigVar(0x46) = `dmgReductionPct` [25..33 par niveau, NON rarity-scaled].
      - cap = ConfigVar(0x12) = `dmgReduction` [20..1455, rarity-scaled × mult].
    AURA (`IdunBattle.Entities.Effects.Loki.GuardianOrganism_DamageReductionEffect$$CreateTargetSelector` = Self + `AdjacentFriends(range 1)`) : l'effet se MATÉRIALISE
    sur chaque bénéficiaire (self + amis ring-1) -> capté dans SA liste (source = le porteur GuardianOrganism).
    Côté port l'effet est DÉJÀ sur le défenseur (comme Terrifying/Terminator) ; `self.ability_level` /
    `self.ability_variables_multiplier` sont ceux de la **SOURCE** de l'effet — le porteur de
    `GuardianOrganism` — depuis #382 (`baked_ability_state` : le natif BAKE l'`AbilityStateReference`
    du caster dans l'entité-effet à la pose). Sur le bénéficiaire == le porteur, c'est le même état
    qu'avant ; sur un ami ring-1, c'est désormais celui du porteur d'aura et non plus celui du
    défenseur. Aucun threading. Aucun gate profil/mêlée/attaquant (OwnerIsTarget seul).
    Symptôme non-porté (probe #86a) : port sur-prédit dégât->TyrantGuard (off 3205 vs natif 2324)."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        lvl = self.ability_level if self.ability_level is not None else self.level
        pct = ability_var("GuardianOrganism", "dmgReductionPct", lvl)   # ConfigVar 0x46 (non scalé)
        if not pct:
            return None
        cap = ability_var("GuardianOrganism", "dmgReduction", lvl,      # ConfigVar 0x12 (rarity-scalé)
                          multiplier_pct=self.ability_variables_multiplier)
        return for_percent_subtraction_capped(False, int(pct), int(cap) if cap else None)


class NightshroudDmgReductionEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.Nightshroud_DmgReduction_Effect$$CreateDamageDefenseModifier` (ability Nightshroud de
    Sibyll Devine `astraPrimarisPsy`, base `ADamageDefenseModifierAbilityEffect(0x416)` = IdunBattle.Entities.Effects.Loki.Nightshroud_DmgReduction_Effect$$.ctor) :
    réduit d'un montant PLAT le dégât REÇU par son porteur — `EffectBonus.ForSubtraction(OwnerIsTarget,
    ConfigVar(0x12)=dmgReduction × mult)`. i2 : « All friendly units starting their turn adjacent to Sibyll
    Devine gain Infiltrate for that turn and take -{dmgReduction} Damage from each hit in their and the next
    enemy turn. » (le grant Infiltrate + la durée their+next-enemy-turn = cycle de vie de l'effet ; le
    ForSubtraction est le SEUL terme de dégât).
      - montant = ConfigVar(0x12) = `dmgReduction` [5..364 par niveau, RARITY-SCALÉ : dmgReduction ∈
        variablesAffectedByRarityBonus] × `mult` (= `*(effet+0x60)`) = niveau/mult de la **SOURCE**
        (Sibyll), pas du défenseur, depuis #382 — l'état est BAKÉ dans l'entité-effet à la pose
        (`baked_ability_state`), comme pour l'AURA GuardianOrganism #89.
    AUCUN gate (OwnerIsTarget SEUL -> s'applique mêlée ET ranged, normale ET spéciale, tout profil de dégât ;
    ≠ le percent-decrease gaté de Terrifying/MartialKatah). PER-COUP : « -X Damage from EACH hit » -> additif
    DÉFENSEUR @+0x10 soustrait de la BASE **PRÉ-perçage** (comme l'additif attaquant #75), donc DILUÉ par
    perçage/armure PUIS scalé ×%-list -> son effet SANTÉ ≪ la valeur config. Canal `flat_reductions` (fusionné
    dans `mods.additive` au merge prediction, SANS le pré-scale ×M de Neuroparasite). MESURÉ LIVE (#111,
    ArmoriumCherub u92->custoTrajann adjacent à Sibyll, varTrace {lvl50,mult180}) : valeur config **499** ;
    dilué par le facteur perçage/armure (~0.31) -> ~155/coup de dégât SANTÉ = oracle [1620,2744] (le "155"
    n'est PAS la config mais 499 traversant l'armure). Port sans NS = [2240,3364] (sur-préd +620 agg)."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        lvl = self.ability_level if self.ability_level is not None else self.level
        red = ability_var("Nightshroud", "dmgReduction", lvl,          # ConfigVar 0x12 (rarity-scalé × mult)
                          multiplier_pct=self.ability_variables_multiplier)
        if not red:
            return None
        return for_subtraction(False, abs(int(red)))   # owner=défenseur (effet sur la cible) ; plat PRÉ-perçage (#120)


class TimesplinterMantleDamageReductionEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.TimesplinterMantle_DamageReductionEffect` (EffectType
    **1551 = 0x60f**), pose au DEBUT DE CHAQUE TOUR par
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TimesplinterMantleAbility$$CreateBehaviour`
    sur `necroChronomancer` << Thothmek >> ET ses allies MECANIQUES non-`Steppable` adjacents.

    `...TimesplinterMantle_DamageReductionEffect$$.ctor` =
    `DamageModifierAbilityEffect..ctor(this, 0x5fe, 0)` -> l'`AbilityOrEffect` de l'effet est le
    **`TriggeredAbilityType` 1534 = TimesplinterMantle** (c'est de LUI que vient l'indexation des
    variables), pas un `EffectType`.

    `...$$CreateDamageDefenseModifier` (surcharge tranchee par l'ADRESSE du `call`,
    `probe_951_call_targets.py`) :

        EffectBonus.ForSubtraction(
            trigger        = get_OwnerIsTarget  op_BitwiseAnd  IsUnit(Caster@DSLSelectors+0x48),
            damageSubtraction = ConfigVar(0x12 = dmgReduction, GetAbilityState(effect), config),
            abilityOrEffect   = AbilityOrEffect(TriggeredAbilityType 1534) )

    => reduction PLATE du degat RECU par le porteur, meme fabrique et meme bac que `Nightshroud`
    (`flat_reductions`, additif DEFENSEUR @`EffectBonus+0x18`, PRE-percage donc DILUE par
    perçage/armure). `dmgReduction` est dans `variablesAffectedByRarityBonus` -> multiplier applique ;
    l'etat d'ability est celui de la SOURCE (Thothmek) puisque le natif lit `GetAbilityState(effect)`
    = l'`AbilityStateReference` BAKE a la pose (#382, `baked_ability_state`) -- d'ou
    `scale_from_source=True` au call-site de pose.

    ⚠ AUCUN gate de nature de coup ni de profil (contraste `TerminatorArmour`/`MartialKatah`) : le
    trigger n'a que les deux noeuds ci-dessus.

    `IsUnit(Caster@+0x48)` -- TAUTOLOGIQUE sur ce canal cote port, et c'est DIT plutot que devine :
    la boucle `create_effect_damage_malus_for_defense` n'est parcourue que depuis le pipeline
    d'ATTAQUE (`damage_model.defender_modifiers` / `prediction`), dont l'attaquant est toujours une
    unite. Le regime qui le discriminerait -- un degat de TUILE/ENVIRONNEMENT recu par un porteur de
    1551 -- n'est pas atteignable dans un duel de runner sans board a effets de tuile. NON CONFRONTE,
    residu nomme. Le MEME noeud est, lui, porte EXPLICITEMENT sur le trigger de retrait
    (`runner/operations/triggers/loki/timesplinter_mantle.py`), ou l'acteur est connu.

    CYCLE DE VIE : `...$$CreateRemoveEffectTrigger` = `(On(9 = Attack) & OwnerIsTarget &
    IsUnit(Caster)) | On(0x17 = TurnEnd)` -> l'effet est une CHARGE A USAGE UNIQUE consommee par la
    premiere attaque recue, et de toute facon balayee a la fin du tour courant. Aucune duree n'est
    posee (`AddEffect` avec des options ZERO et `1551` absent de `DefaultAmountOfRounds`) : le retrait
    ne peut venir QUE de ces triggers."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        lvl = self.ability_level if self.ability_level is not None else self.level
        red = ability_var("TimesplinterMantle", "dmgReduction", lvl,   # ConfigVar 0x12 (rarity-scale)
                          multiplier_pct=self.ability_variables_multiplier)
        if not red:
            return None
        return for_subtraction(False, abs(int(red)))   # EffectBonus +0x18 = Subtraction (plat PRE-percage)


class NeuroparasiteEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$CreateEffectDamageMalusForDefense` (passif du Neurothrope
    `Neuroparasite`, EffectType 0x49f=1183, base `ABondEffect` = lien cible<->Neurothrope infecteur).
    Malgré le nom « MalusForDefense », c'est un ADDITIF **POSITIF** au dégât PSYCHIQUE reçu (le porteur =
    une faiblesse infligée) :
      `EffectBonus.ForAddition(OwnerIsTarget & AreEqual(BondedEntity, damageSource) & DamageProfileIs(0xd),
                               Multiply(ConfigVar(8=extraDmg, sourceAbilityState), EffectLevel))`
    = **+extraDmg[niveauSource] × niveau_de_parasite** au dégât psychique de LE Neurothrope qui a infecté la
    cible. i2 : « Psychic Damage dealt by the Neurothrope is increased by +1237 Damage for each level of a
    Neuroparasite on the target » (`extraDmg[L65]=1237` ; max 15 niveaux via `IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$GetMaximumLevel`).

    Gates natifs (IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$CreateEffectDamageMalusForDefense) :
      - `DamageProfileIs(0xd=Psychic)` -> uniquement le dégât PSYCHIQUE (`damage_profile == "Psychic"`).
      - `AreEqual(BondedEntity, damageSource)` -> uniquement les attaques de CE Neurothrope (l'effet `source`
        = le Neurothrope infecteur). `attacker_ctx["id"]` threadé par le builder : si connu et != source ->
        pas de bonus (un AUTRE psyker n'en profite pas).
      - `EffectLevel` = niveau de STACK du parasite sur la cible (`self.level`, capté decisionView.effects[].level).

    Magnitude `ConfigVar(8=extraDmg)` = INDEXÉE par le niveau de l'ability Neuroparasite du Neurothrope SOURCE
    (`GetAbilityState(effect)`), × SON multiplier (`extraDmg` in `variablesAffectedByRarityBonus`). L'attaquant
    ÉTANT le source (gate AreEqual), le builder passe `attacker_ctx["ability_level"]/["multiplier"]` = ceux du
    Neurothrope (`scene.ablvl_by_id`/`scene.mult`). Source inconnu (`ability_level` None : chemin combat runner
    qui ne matérialise pas encore le parasite) -> pas de bonus (dégradation fidèle, PAS un extraDmg[0] mal-indexé).

    VALIDÉ LIVE (#86, Neurothrope vs orksRuntherd VANILLA, parasite lvl0->1, aiPredict oracle) :
      - L'effet est bien MATÉRIALISÉ côté cible (EffectType capté = **1218** `Neuroparasite` ; le ctor 0x49f=1183
        est l'`AbilityOrEffect`, distinct — le routage factory se fait par NOM, ok).
      - MAGNITUDE `extraDmg[50]=942 × mult(1.8) = 1696` EXACTE = per-level natif AVANT le %-list attaquant
        (confirme le MULTIPLIER = mult UNITÉ, comme PowerTrip ; lève l'incertitude #75 pour ce passif).
      - PLACEMENT = AVANT le %-list attaquant (scalé ×%-mods), TRANCHÉ par 2 SÉPARATEURS (#88, RÉSOLU) :
        RangedSpecialist ON (M=1.33) -> Δ per-level=2256 ; OFF (Neuro démarre adjacent, M=1) -> Δ=1696
        (L1'=(3302,4106) EXACT, réfute l'hypothèse "flat 2256"). `(base+1696)×M` EXACT sur les 2 régimes.
    Le placement est câblé dans `prediction.py _add_positional_and_defender_mods` : l'additif défenseur est
    PRE-SCALÉ par le produit des %-mods avant merge dans `mods.additive` (= équivalent algébrique de avant-%list,
    `(base+A)×M = base×M + A×M`, l'`apply_all_modifiers` porté appliquant l'additif après le %-list §17.7).
    Sémantique : "damage DEALT by the Neurothrope is increased" = dégât ATTAQUANT -> scalé par ses %-mults.
    VALIDÉ port==natif BIT-EXACT (L0 (2136,3205), L1 (4392,5461)). ⚠ ISOLÉ au def additive (Neuroparasite = seul
    consommateur) ; le placement de l'additif ATTAQUANT (SmashaEad) reste après-%list (#70/#75, séparateur att
    non mesuré).

    CYCLE DE VIE (#462-r4b-r1-r1-r1) : le parasite est désormais POSÉ **par le port lui-même** — la
    ligne qui disait ici « Combat : parasite non matérialisé par le runner -> def additive=0 ->
    inerte » décrivait une cause DOUBLEMENT fausse (l'inertie venait du fork prédiction/combat sur
    l'axe MAGNITUDE, fermé par #462-r4b-r1-r1 ; et la POSE existe depuis
    `runner/operations/triggers/loki/neuroparasite.py`). `NeuroparasiteAbility$$CreateTrigger/
    $$CreateBehaviour` (`On(9)` + `AddBondEffect(0x4c2)`) et les DEUX `Triggered()` de
    `NeuroparasiteEffect$$CreateHandleTriggerAbilitiesInternal` (montée de niveau sur frappe PSYCHIQUE
    et sur pose de `Pinned`, cap `$$GetMaximumLevel` = `buffMaxLevel[lvl] + NornCrown`) sont portés et
    confrontés live. `self.level` n'est donc plus figé à ce que le seed a capté."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if (damage_profile or "") != "Psychic":       # DamageProfileIs(0xd=Psychic)
            return None
        ac = attacker_ctx or {}
        aid = ac.get("id")
        if aid is not None and self.source is not None and aid != self.source:
            return None                               # AreEqual(BondedEntity, damageSource) : autre attaquant
        lvl = int(self.level or 0)                    # EffectLevel = niveau de parasite sur la cible
        if lvl <= 0:
            return None
        src_lvl = ac.get("ability_level")             # niveau de l'ability Neuroparasite du Neurothrope SOURCE
        if src_lvl is None:
            return None                               # source non résolu -> pas d'indexation extraDmg fidèle
        per = ability_var("Neuroparasite", "extraDmg", src_lvl,
                          multiplier_pct=ac.get("multiplier") or 100)
        if not per:
            return None
        return for_addition(False, int(per) * lvl)    # owner=cible (défenseur) ; additif POSITIF au dégât reçu


class FightingRetreatDmgReductionEffect(BaseEffect):
    """`FightingRetreat_DamageReductionEffect` (effet 1157 `FightingRetreatDmgReduction`) — debuff posé
    par FightingRetreat (Darkstrider) sur les ennemis adjacents (« deal -582 Damage for one round »).
    - dégât IdunBattle.Entities.Effects.Loki.FightingRetreat_DamageReductionEffect$$CreateEffectDamageBonusForAttack : `EffectBonus.ForAddition(OwnerIsCaster, Multiply(ConfigVar(0x12=dmgReduction),
      MinusOne))` = **-dmgReduction PLAT** sur les attaques du PORTEUR (additif, PAS un pct).
      `dmgReduction` = variable par niveau (lvl65=582), flaggée `variablesAffectedByRarityBonus`.
    ⚠ Niveau/multiplier fidèles = ceux du CASTER SOURCE (Darkstrider, abilityState de l'effet), non
      captés pour un debuff d'origine ennemie → fallback niveau/multiplier du PORTEUR (approximation
      documentée ; identique en pratique sur rosters au même palier)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        lvl = self.ability_level if self.ability_level is not None else self.level
        v = ability_var("FightingRetreat", "dmgReduction", lvl,
                        multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, -int(v)) if v else None


class LightOfSanguiniusDmgReductionEffect(BaseEffect):
    """`LightOfSanguinius` (EffectType **0x560 = 1376**) -- le debuff que pose
    `IdunBattleLogic.Entities.Abilities.Active.LightOfSanguiniusAbility$$ExecuteBehaviour` (1177,
    `bloodDante`) sur la CIBLE et les ennemis qui l'entourent. Il reduit le degat que le PORTEUR
    INFLIGE (face ATTAQUANT), pas celui qu'il recoit. #510.

    `IdunBattle.Entities.Effects.Loki.LightOfSanguinius_DamageReductionEffect$$.ctor` =
    `DamageModifierAbilityEffect..ctor(this, 0x499 = 1177, Nullable(1))` -- la config lue est donc
    celle de l'ability ACTIVE `LightOfSanguinius`.

    MIRROR 1:1 de `...LightOfSanguinius_DamageReductionEffect$$CreateDamageModifier` (build
    `rnca9r7q6c`), terme a terme :

        pct    = ConfigVar( 0x46 = dmgReductionPct, GetAbilityState(effet), config@effet+0x60 )
        double = Multiply( pct, <DSLFormulas+0x28> = Direct(2) )
        seuil  = ConfigConst( 0x4f = healthPct, config@effet+0x60 )
        amount = DSLFormulas.If( NOT( HealthPctIsBelowOrEqual(Target@DSLSelectors+0x60, seuil) ),
                                 pct, double )
        return EffectBonus.ForPercentDecrease( DSLTriggers.get_OwnerIsCaster, amount )

    ⇒ `-dmgReductionPct %` sur TOUT degat inflige par le porteur, **DOUBLE** quand la cible du coup
    (`Target@+0x60` = le DEFENDEUR, pas le porteur) est a `healthPct %` de PV ou moins.
    i2 : « The target and enemy units surrounding it deal -{dmgReductionPct}% Damage for
    {nrOfRounds} round. This effect is doubled if they attack friendly units that are at or below
    {healthPct}% Health. » -- le « friendly units » de l'i2 est bien la cible du coup, vue depuis
    Dante.

    AUCUN autre gate : ni melee/ranged, ni profil, ni `IsNormalAttack`, ni `ActiveCondition`
    (contraste `MartialKatah_DmgReduction`, gate normal-only) -> il mord sur TOUT vecteur.

    FACE. `LightOfSanguinius_DamageReductionEffect` derive de `DamageModifierAbilityEffect` et
    n'implemente que `CreateDamageModifier` : sa contribution sort par le forwarder
    `IdunBattle.Entities.Effects.DamageModifierAbilityEffect$$CreateEffectDamageBonusForAttack`,
    donc dans l'accumulateur ATTAQUANT -- et le trigger `get_OwnerIsCaster` le confirme
    (`owner_is_caster=True`). C'est le meme canal que `FightingRetreat_DamageReduction` ci-dessus.

    `HealthPctIsBelowOrEqual` = `IdunBattle.Entities.Conditions.StatPercentageIsBelowOrEqualAbility
    Trigger$$ShouldTrigger` sur la stat 5 = HEALTH : `GetStat(5, Current) / GetStat(5, Maximum) <=
    pct/100` en Fix64, comparaison INCLUSIVE. Equivalent entier EXACT `100*hp <= pct*max` (meme
    lecture que `VisionsOfHeresyExtraPierceEffect.is_active` et que `_regenerate_precondition`).

    SUBSTRAT. `tgt_hp` / `tgt_hp_max` sont threades dans `att_ctx` par les TROIS faces
    (`runner/damage_model.attacker_modifiers`, `playbook/prediction/normal_attack`,
    `playbook/prediction/abilities`). Cles ABSENTES -> branche NON doublee (`pct` seul), degradation
    RESTRICTIVE et NOMMEE : on n'invente pas un doublement sur un substrat non mesure. La reduction
    de BASE, elle, ne depend d'aucun contexte et s'applique toujours.

    ⚠ IL N'Y A **PAS** DE FORK PREDICTION / COMBAT ICI, et c'est une REFUTATION, pas une absence de
    mesure (`probe_510_light_of_sanguinius_live.py`). Un gate `is_prediction` a ete pose puis RETIRE
    le meme jour, parce que l'ANTI-CONFOND TEMPOREL a montre que le discriminant n'etait pas le
    canal mais le TOUR :

      * mesure qui a induit en erreur -- `aiPlaybookPredict` interroge sur un ennemi PENDANT LE TOUR
        DU JOUEUR : facteur 0,70 CONSTANT dans trois regimes (porteur a 18,8 % PV, defenseur a 40 %
        PV, les deux a 100 % PV). Aucun doublement : on aurait conclu « la prediction ne double
        jamais » ;
      * la MEME requete, sur le MEME couple, avec le MEME effet actif, APRES `endturn` -- donc quand
        l'unite affectee appartient a l'equipe ACTIVE -- rend **(1040, 1560) = x0,40**, soit le
        DOUBLEMENT. Le canal n'a pas change ; le tour, si.
      * COMBAT, au meme instant : attaquant affecte -> defenseur a 40 % PV, live = 2778 ; port avec
        doublement ARME = **2778 (bit-exact)**, port DESARME = 5091. Meme montage avec un defenseur
        a 100 % PV : ARME == DESARME == live.

    ⇒ le doublement est REEL sur les DEUX faces, et le port ne le gate PAS. CE QUI EST GARDE de
    l'episode : `aiPlaybookPredict` invoque sur une unite qui n'est PAS de l'equipe active rend une
    prediction a CONTEXTE DEGRADE -- la lecture qui l'explique est la garde de
    `IdunBattle.Entities.Conditions.StatPercentageIsBelowOrEqualAbilityTrigger$$ShouldTrigger`, qui
    resout d'abord son SELECTEUR (`this+0x10`, slot 7 `SelectSingle`) et **rend 0 = FAUX des qu'il
    ne resout AUCUNE entite**. Un `Target@DSLSelectors+0x60` non renseigne suffit donc a effacer la
    branche, sans erreur. Ce qui reste NON LU (residu `#510-r1`) : POURQUOI ce slot est vide
    hors-tour, c'est-a-dire la construction de l'`AbilityEntities` dans
    `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction`.

    NIVEAU. `ConfigVar(..., GetAbilityState(effet))` lit l'etat d'ability de la SOURCE (Dante) : cote
    port c'est `scale_from_source=True` sur l'`AddEffect` de la feuille DSL, qui pose
    `active_ability_level` + le multiplier de rarete du CASTER sur l'effet materialise.
    ⚠ Sur un effet SEEDE depuis `decisionView.effects` (debuff d'origine ENNEMIE), ces champs
    portent le niveau du PORTEUR, pas celui de la source -- meme approximation documentee que
    `FightingRetreatDmgReductionEffect`, et sans consequence sur un roster au meme palier.
    `dmgReductionPct` n'est PAS dans `variablesAffectedByRarityBonus` (qui ne contient que
    `minDmg`/`maxDmg`) -> le multiplier est un no-op, `ability_var` applique la regle config-driven."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else self.ability_level)
        pct = ability_var("LightOfSanguinius", "dmgReductionPct", lvl,       # ConfigVar(0x46)
                          multiplier_pct=self.ability_variables_multiplier)
        if not pct:
            return None
        c = att_ctx or {}
        hp, mx = c.get("tgt_hp"), c.get("tgt_hp_max")
        seuil = ability_var("LightOfSanguinius", "healthPct", is_constant=True)   # ConfigConst(0x4f)
        # `NOT(HealthPctIsBelowOrEqual(Target, seuil))` -> `pct` ; sinon `Multiply(pct, Direct(2))`.
        # AUCUN gate `is_prediction` : le doublement est mesure sur les DEUX faces (cf. la
        # REFUTATION dans la docstring de classe -- un tel gate a ete pose puis retire).
        double = (hp is not None and mx and seuil is not None
                  and 100 * int(hp) <= int(seuil) * int(mx))
        return for_percent_decrease(True, int(pct) * (2 if double else 1))   # OwnerIsCaster


class ElectrochaffBackupsDamageReductionPctEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.ElectrochaffBackups_DamageReductionPctEffect` (`EffectType`
    0x5a6 = **1446**) -- l'effet pose par l'ability **MYTHIQUE** `ElectrochaffBackups`
    (`TriggeredAbilityType` 0x5ae = 1454) des MoW `tauBroadside` << Tson'ji >> / `tauNpcMoWBroadside`
    sur l'ENNEMI marque ou blesse a distance. La POSE est portee depuis #1025
    (`runner/operations/triggers/loki/electrochaff_backups.py`) ; c'est la face DEGAT qui manquait,
    et son verrou etait le canal de RARETE (residu `#1025-r1`).

    i2 (`/Abilities/ElectrochaffBackups_CurrentLevelDescription`) : << Enemy units that have a
    **Markerlight** or have been damaged by a **ranged attack** deal -{dmgReductionPct}% Damage to
    **Mythic** characters for {nrOfRounds} round. >>

    ## MIRROR 1:1 -- `...ElectrochaffBackups_DamageReductionPctEffect$$CreateDamageModifier`

        EffectBonus.ForPercentDecrease(
            get_OwnerIsCaster
            & ( HasRarity(  Target@<DSLSelectors+0x60>, idun.meta.Rarity.Mythic = 5 )
                & AreFriends( Target@<DSLSelectors+0x60>,
                              EffectSource(Effect@<DSLSelectors+0x38>), 0, false ) ),
            DSLFormulas$$ConfigVar( 0x46 = AbilityVariableType.dmgReductionPct,
                                    GetAbilityState(effet), effet@+0x60 ) )

    ## LE CANAL EST CELUI DU PORTEUR-ATTAQUANT, **PAS** L'AURA -- et c'est LU, pas suppose
    `search_symbols_by_name` sur cette classe rend **deux** symboles (`$$.ctor` et
    `$$CreateDamageModifier`) : il n'y a **AUCUN `$$CreateTargetSelector`**. L'Owner de l'effet est
    donc son PORTEUR, et `get_OwnerIsCaster` dit que ce porteur est le CASTER du coup -> le canal
    port est `create_effect_damage_bonus_for_attack` (la boucle des effets de l'ATTAQUANT), pas un
    agregateur d'aura. La ligne de backlog qui rangeait cet effet sous un `CreateTargetSelector`
    etait fausse ; re-mesure au decompile (#1025-r1).

    C'est le SYMETRIQUE EXACT d'`HyperCorrosiveAcid_ExtraDamagePct` (1448) : meme famille de MoW
    mythique, meme forme d'arbre, mais le trigger y est `get_OwnerIsTarget` et les conjoints portent
    sur `Caster@<DSLSelectors+0x48>`. Ici ils portent sur `Target@<DSLSelectors+0x60>`.

    ## LES TROIS CONJOINTS, ET D'OU ILS VIENNENT
      1. `get_OwnerIsCaster` -- VRAI par construction sur ce canal : `_attacker_effect_bonuses`
         n'itere QUE les effets de l'attaquant, donc l'Owner de chaque effet parcouru EST le caster
         (meme idiome que `MartialInspiration` / `RitesOfMorkai`). Aucun gate a ecrire.
      2. `HasRarity(Target@+0x60, Mythic)` -- `BaseUnitComponent.Rarity` (+0x74) de la CIBLE DU
         COUP, lu dans `att_ctx["tgt_rarity"]` (#1025-r1 ; foyers `damage_model._unit_rarity` /
         `prediction._shared._entity_rarity`). TRI-ETAT : `None` = NON MESURE -> gate FERME.
         C'est LE conjoint qui tenait cet effet hors du registre : sans lui, l'attaquant marque
         verrait TOUTES ses attaques reduites -- terme PERMISSIF, et de loin le plus gros.
      3. `AreFriends(Target@+0x60, EffectSource(Effect@+0x38), 0, false)` -- la CIBLE DU COUP est
         une alliee du BROADSIDE. `EffectSource` = `EffectComponent.SourceUnit @+0x10` =
         `self.source` cote port ; son equipe se resout par `att_ctx["team_by_id"]`, celle de la
         cible par `att_ctx["tgt_team"]` (MEME idiome que `HyperCorrosiveAcidExtraDamagePctEffect`
         vu de l'autre bord). ⚠ Ce conjoint N'EST PAS redondant avec le `AreEnemies(Owner, Target)`
         du trigger de POSE : celui-la contraint le PORTEUR, celui-ci contraint la CIBLE DE SON COUP.
         Un porteur qui frappe une unite NEUTRE, un objet, ou (via un `Taunt`/charme) l'un des siens
         n'ecope de rien.

    ## AUCUN AUTRE GATE, ET C'EST LU
    Ni `IsMeleeAttack`, ni `IsRangedAttack`, ni `IsNormalAttack`, ni `DamageProfileIs` : le
    decompile ne porte que les trois conjoints ci-dessus. L'effet mord donc sur TOUT vecteur --
    attaque normale, ability, smite, riposte. C'est ce qui l'a fait threader sur les NEUF sites
    d'`att_ctx` du canal ATTAQUE, et pas seulement sur la normale.

    ## MAGNITUDE -- et c'est l'etat d'ability de la **SOURCE**, MESURE, pas suppose
    `ConfigVar(0x46 = dmgReductionPct)` sur la config de l'ability `ElectrochaffBackups`, indexee
    par `GetAbilityState(effet)` = l'`AbilityStateReference` BAKEE dans `EffectComponent+0x18` a la
    pose -- le 2e argument natif d'`AddEffect`, `BaseTriggeredAbility$$get_AbilityStateReference
    (this)`, donc l'etat de la MoW POSEUSE et **jamais** celui du porteur (les deux DIFFERENT par
    construction : `source = Owner`, `targets = Target`, et ils sont d'equipes OPPOSEES).

    ⚠ MESURE (#1025-r1) : apres pose par le trigger, l'instance materialisee porte
    `ability_level = None` -- `AddEffect` du port ne bake l'etat de la source que sous
    `scale_from_source`, non pose sur ce call-site (ni sur celui de 1448). Lire `self.ability_level`
    rendrait donc un effet INERTE en combat. Le canal qui porte l'etat de n'importe quel proprietaire
    est `att_ctx["tertiary_ability_state_of"]` -- callable `(owner_id, ability) -> (level, mult)`,
    foyer UNIQUE `runner/operations/triggers/base.py::triggered_ability_state` (#357), qui rend
    l'etat **TERTIAIRE** quand l'ability y est montee (le cas d'une mythique de MoW) et le PASSIF
    sinon. MEME cle et MEME semantique que `NornCrownEffect` / `HeadwoppasKillchoppaEffect`.
    On l'interroge avec `self.source` -- la MoW poseuse -- et non avec le porteur.
    Canal absent (face PREDICTION, contexte offline, probe) -> repli NOMME sur les niveaux que
    l'instance porte deja, exactement le repli de `NornCrownEffect._amount`.

    Gameconfig : `dmgReductionPct = [10, 13, 16, 20]`,
    `variablesAffectedByRarityBonus = ['dmgReductionPct']`. Aucun niveau resolu -> AUCUNE
    contribution (<< present != applique >>)."""

    #: Cle gameconfig de l'ability qui pose l'effet -- la config qu'indexe `ConfigVar`.
    ABILITY_ID = "ElectrochaffBackups"
    #: `AbilityVariableType` 0x46 = 70, resolu par son NOM (jamais par l'ordinal : `AbilityConstantType`
    #: 70 nomme autre chose).
    VAR_DMG_REDUCTION_PCT = "dmgReductionPct"
    #: callable `(owner_id, ability_name) -> (level, multiplier)` -- mirror de `GetAbilityState(effet)`
    #: (#357). MEME cle que `NornCrownEffect` / `HeadwoppasKillchoppaEffect` : le foyer UNIQUE
    #: `runner/operations/triggers/base.py::triggered_ability_state`.
    CTX_ABILITY_STATE_OF = "tertiary_ability_state_of"

    def _amount(self, att_ctx) -> "int | None":
        """`ConfigVar(0x46 = dmgReductionPct, GetAbilityState(effet), <config@effet+0x60>)` --
        interroge l'etat d'ability de la **SOURCE** (`EffectComponent.SourceUnit @+0x10`), cf. la
        docstring de classe. Canal absent -> repli NOMME sur les niveaux de l'instance."""
        c = att_ctx or {}
        fn = c.get(self.CTX_ABILITY_STATE_OF)
        lvl = mult = None
        if fn is not None and self.source is not None:
            lvl, mult = fn(self.source, self.ABILITY_ID)
        if lvl is None:
            lvl = self.ability_level if self.ability_level is not None else self.level
            mult = self.ability_variables_multiplier
        if not lvl:
            return None
        return ability_var(self.ABILITY_ID, self.VAR_DMG_REDUCTION_PCT, lvl,
                           multiplier_pct=int(mult if mult is not None else 100))

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        c = att_ctx or {}
        # 2. `HasRarity(Target@+0x60, idun.meta.Rarity.Mythic = 5)` -- comparaison au MEMBRE d'enum,
        #    jamais a l'ordinal : cinq enums du build partagent les six memes ordinaux de rarete
        #    (cf. `entities/rarity.py`). `None` (non mesure) -> FERME.
        if c.get("tgt_rarity") != Rarity.Mythic:
            return None
        # 3. `AreFriends(Target@+0x60, EffectSource(Effect@+0x38), 0, false)`
        t_team = c.get("tgt_team")
        s_team = (c.get("team_by_id") or {}).get(self.source) if self.source is not None else None
        if t_team is None or s_team is None or t_team != s_team:
            return None                                   # equipe inconnue -> gate muet (fidele)
        pct = self._amount(att_ctx)                       # ConfigVar(0x46) sur l'etat de la SOURCE
        if not pct:
            return None
        # owner = l'ATTAQUANT (`get_OwnerIsCaster`) -> le degat INFLIGE baisse.
        return for_percent_decrease(True, int(pct))


class ShadowInTheWarpLessDmgEffect(BaseEffect):
    """`ShadowInTheWarp_LessDmg_Effect` (effet 1053=0x41d) — AURA de RÉDUCTION du dégât PSYCHIQUE. L'effet
    vit sur le PORTEUR (trait ShadowInTheWarp, ex. tyranSmnWarrior) et se PROJETTE sur les ENNEMIS
    environnants (psykers) : quand un tel ennemi attaque en PSYCHIQUE, son dégât est réduit.
    - dégât `IdunBattle.Entities.Effects.Loki.ShadowInTheWarp_LessDmg_Effect$$CreateEffectDamageBonusForAttack : `ForPercentIncrease(OwnerIsActor &
      DamageProfileIs(0xd=Psychic), ConfigConst(0x3b))` = `shadowInTheWarpDmgModifier`% (=-25, négatif).
    - cible `IdunBattle.Entities.Effects.Loki.ShadowInTheWarp_LessDmg_Effect$$CreateTargetSelector : `SurroundingEnemies(range=ConfigConst 0x16) &
      UnitsWithTrait(0x3ea) & UnitsNotFromFaction(0xc)`.
    MAGNITUDE + PORTÉE LUES du trait (`traitVariables.shadowInTheWarpDmgModifier=-25`, `shadowInTheWarpRange=2`).
    ⚠ Filtre `UnitsWithTrait(0x3ea)` (psyker) NON décodable offline (pas de map TRAIT) → SUR-APPROXIMÉ au
    seul gate PSYCHIQUE (tout ennemi attaquant en Psychic dans la portée subit le malus) ; raffinement quand
    le trait 0x3ea sera mappé. Canal AURA côté SOURCE (`create_aura_attack_damage_malus_for_enemy`), agrégé
    par `aura_attack_damage_malus_from_enemies` et ajouté aux modifiers de l'ATTAQUANT en prédiction."""

    def create_aura_attack_damage_malus_for_enemy(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if (c.get("damage_profile") or "") != "Psychic":    # DamageProfileIs(0xd) IdunBattle.Entities.Effects.Loki.ShadowInTheWarp_LessDmg_Effect$$CreateEffectDamageBonusForAttack
            return None
        if c.get("owner_team") is None or c.get("owner_team") == c.get("att_team"):
            return None                                       # SurroundingEnemies : l'attaquant est ENNEMI du porteur
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        import hexgeo
        rng = trait_var("ShadowInTheWarp", "shadowInTheWarpRange")
        if hexgeo.distance(op, ap) > int(rng if rng else 2):  # SurroundingEnemies(range ConfigConst 0x16)
            return None
        red = trait_var("ShadowInTheWarp", "shadowInTheWarpDmgModifier")   # -25 (ConfigConst 0x3b)
        if not red:
            return None
        return for_percent_decrease(True, abs(int(red)))      # OwnerIsActor : malus sur l'attaque de l'ennemi


class DaughterOfTheAbyssFriendlyDmgReductionPctEffect(BaseEffect):
    """`DaughterOfTheAbyss_FriendlyDmgReductionPctEffect` (effet 0x58b=1419, passif DaughterOfTheAbyss
    d'Atlacoya custoAtlacoya) — AURA de RÉDUCTION du dégât PSYCHIQUE REÇU par les AMIS du porteur
    (i2 : « Psychic Damage dealt to other friendly units within 2 hexes of Atlacoya is reduced by 33% »).
    L'effet vit sur le PORTEUR (posé par `IdunBattleLogic.Entities.Abilities.Triggered.Loki.DaughterOfTheAbyssAbility$$CreateBehaviour :
    AddEffect(0x58b) — capté live source=Atlacoya, JAMAIS matérialisé sur les amis) et se PROJETTE sur
    les cibles à la CALC (boucle state-wide EffectWithTarget × cibles de `CalculateDefenderModifiers-
    ForPrediction` IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction).
    - dégât `IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_FriendlyDmgReductionPctEffect$$CreateEffectDamageMalusForDefense : `(OwnerIsTarget & DamageProfileIs(0xd=
      Psychic)) -> -ConfigVar(0x46=dmgReductionPct, abilityState)` (négation via nœud Direct(-1), mirror
      du jumeau Owner IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_OwnerDmgReductionEffect$$CreateEffectDamageMalusForDefense `Multiply(ConfigVar, factory+0xd8)`).
    - cibles (selector famille, jumeau symétrique IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_ExtraDamagePctEffect$$CreateTargetSelector) : amis du porteur dans le rayon
      `constants.range` (=2), « OTHER » ⇒ exclut le porteur (qui a SON OwnerDmgReduction).
    MAGNITUDE : `dmgReductionPct[ablvl]` (25→33, hors variablesAffectedByRarityBonus ⇒ PAS de scaling
    rareté). GROUND TRUTH #184 (seed 2024 MC1_67) : bloodMephiston (Psychic) → tgts 81/83/85/79 tous à
    ≤2 hexes d'Atlacoya (6,8) = natif ×0.67 EXACT (2016,3024 = 1003×1.25×[0.8,1.2]×3×0.67), cible ALLIÉE
    de Mephiston (hors aura) = ×1.0 (3009,4515) ; u91 worldExecutions (profil Power) = bit-exact sans
    réduction. C'était le ~1.49x du flip-flop #184 (1/0.67), PAS un écart de hit-count."""

    def create_aura_defense_damage_malus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if (c.get("damage_profile") or "") != "Psychic":      # DamageProfileIs(0xd) IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_FriendlyDmgReductionPctEffect$$CreateEffectDamageMalusForDefense
            return None
        if c.get("tgt_id") == c.get("owner_id"):              # « OTHER friendly units » : exclut le porteur
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("tgt_team"):
            return None                                       # SurroundingFriends : cible ALLIÉE du porteur
        op, tp = c.get("owner_pos"), c.get("t_pos")
        if not op or not tp:
            return None
        import hexgeo
        rng = ability_var("DaughterOfTheAbyss", "range", is_constant=True)   # ConfigConst 0x16 (=2)
        if hexgeo.distance(op, tp) > int(rng if rng else 2):
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        pct = ability_var("DaughterOfTheAbyss", "dmgReductionPct", level=lvl)
        if not pct:
            return None
        return for_percent_decrease(True, abs(int(pct)))      # -33% @L50 (négation Direct(-1) native)


class DaughterOfTheAbyssOwnerDmgReductionEffect(BaseEffect):
    """`DaughterOfTheAbyss_OwnerDmgReductionEffect` (effet 0x58a=1418) — réduction PLATE du dégât
    PSYCHIQUE reçu par le PORTEUR lui-même (i2 : « Atlacoya takes -1892 Psychic Damage »). L'effet est
    dans la liste d'effets de la CIBLE quand Atlacoya est visée ⇒ canal défenseur STANDARD.
    - dégât `IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_OwnerDmgReductionEffect$$CreateEffectDamageMalusForDefense : `(OwnerIsTarget & DamageProfileIs(0xd=
      Psychic)) -> Multiply(ConfigVar(0x12=dmgReduction, abilityState), Direct(-1) factory+0xd8)`
      = soustraction plate (slot additif défenseur @+0x10, mirror Nightshroud #111/#120).
    MAGNITUDE : `dmgReduction[ablvl]` ∈ variablesAffectedByRarityBonus ⇒ × multiplier de l'unité.
    ⚠ NON VALIDÉ LIVE (#184) : structure lue du décompilé (jumeau exact de Nightshroud IdunBattle.Entities.Effects.Loki.Nightshroud_DmgReduction_Effect$$CreateDamageDefenseModifier,
    lui validé) mais aucune mesure native vs Atlacoya-cible obtenue (hors plans dans les seeds
    d'audit + rows toujours predOptimistic via son Parry_ReduceHits) — placement per-hit additif
    présumé par la famille."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if (damage_profile or "") != "Psychic":               # DamageProfileIs(0xd) IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_OwnerDmgReductionEffect$$CreateEffectDamageMalusForDefense
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        amt = ability_var("DaughterOfTheAbyss", "dmgReduction", level=lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        if not amt:
            return None
        # owner=défenseur (effet sur la cible) → flat_reductions PRÉ-perçage (routage Nightshroud #120)
        return for_subtraction(False, abs(int(amt)))


class OverwhelmingWrathRangeDmgReductionEffect(BaseEffect):
    """`OverwhelmingWrath_RangeDmgReductionEffect` (EffectType 0x515=1301, nom capté
    "OverwhelmingWrath_RangeDmgReduction" ; famille `ADamageDefenseModifierAbilityEffect`, IdunBattle.Entities.Effects.Loki.OverwhelmingWrath_RangeDmgReductionEffect$$.ctor = base(0x475=1141 = OverwhelmingWrath, l'ACTIVE d'Azkor worldEightbound)) — i2 :
    « Until the beginning of his next turn Azkor Taunts all adjacent enemies and takes -64% Damage
    from ranged attacks. » Effet TRANSIENT (rem=1 capté), posé par l'ExecuteBehaviour de l'ability
    (IdunBattleLogic.Entities.Abilities.Active.Loki.OverwhelmingWrathAbility$$ExecuteBehaviour), expire au début du tour suivant du porteur. #190.

    - dégât `IdunBattle.Entities.Effects.Loki.OverwhelmingWrath_RangeDmgReductionEffect$$CreateDamageDefenseModifier` : `EffectBonus.ForPercentDecrease(
      get_OwnerIsTarget & IsRangedAttack, ConfigVar(0x46=dmgReductionPct, GetAbilityState(effet)))`
      → le dégât des attaques RANGED reçues par le porteur est réduit de `dmgReductionPct`%.
      Gate RANGED strict (aucun filtre profil/normal) ; contexte inconnu (is_melee=None) → no-op.
    - MAGNITUDE : `dmgReductionPct[ablvl]` (24→64, plateau à 64 dès L36 ; HORS
      variablesAffectedByRarityBonus=[minDmg,maxDmg] → multiplier no-op). Ability ACTIVE →
      active_ability_level, fallback ability_level (seed = passif ; plateau ⇒ écart no-op) / level.

    GROUND TRUTH #190 (seed 777 MC1_67 iter-4, session 22) : meph (1,4) → Azkor (3,4) dist 2
    (ranged), tout Grass, elev 3=3 — l'hypothèse « positionnelle » de la tâche est RÉFUTÉE par
    mesure (toggles no-elev/no-board strictement inertes) : oracle=(532,798) = engine ×0.360 EXACT
    min ET max = 1−0.64 ; à iter-5 (effet expiré) le MÊME couple matche BIT-EXACT → transient,
    pas positionnel. (L'effet jumeau `OverwhelmingWrath_PendingAttack` 0x514=1300 = l'attaque
    différée 2× Eviscerate au début du tour suivant — hors canal modifier, non porté ici.)"""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if is_melee is not False:                # gated IsRangedAttack IdunBattle.Entities.Effects.Loki.OverwhelmingWrath_RangeDmgReductionEffect$$CreateDamageDefenseModifier
            return None
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        pct = ability_var("OverwhelmingWrath", "dmgReductionPct", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        if not pct:
            return None
        return for_percent_decrease(False, abs(int(pct)))   # owner=défenseur (l'effet est sur la cible)


class FireAndRepositionReduceDmgEffect(BaseEffect):
    """`FireAndReposition_ReduceDmgEffect` (EffectType 0x456=1110, nom capte
    "FireAndReposition_ReduceDmg") -- pose sur ELLE-MEME par l'active `FireAndReposition` (0x427=1063)
    de `eldarRanger` (Calandis). i2 : « May move as normal and attack. After attacking, she may make
    one more normal movement. **In the following enemy turn, she takes -{dmgReduction} Damage from
    ranged attacks.** Can only be used if Calandis has a target in range. »

    MIRROR 1:1 de
    `IdunBattle.Entities.Effects.Loki.FireAndReposition_ReduceDmgEffect$$CreateEffectDamageMalusForDefense` :

        EffectBonus.ForSubtraction(
            get_OwnerIsTarget & IsRangedAttack & NOT <DSLTriggers+0x28>,
            ConfigVar(0x12 = dmgReduction, GetAbilityState(effet), config@+0x60) )

    * **Canal = LECTURE PAR COUP cote DEFENSE**, pas une stat ni une aura : `ForSubtraction` sur le
      slot `EffectBonus` @+0x18, agrege par
      `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` ->
      cote port `flat_reductions`, additif DEFENSEUR **PRE-percage** (meme placement exact que
      `NightshroudDmgReductionEffect`, ground truth #120/#111) -- donc DILUE par percage/armure puis
      scale x%-list UNE fois. Le montant config n'est PAS le degat sante retire.
    * **`DSLTriggers+0x28` = `IsTurnOf(Owner)`** : le champ est ecrit par
      `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` avec la MEME classe
      (`DAT_1833ab568`) et la meme forme d'appel que
      `IdunBattleLogic.Entities.DSLTriggers$$IsTurnOf(selector)`, sur `DSLSelectors+0x30` = **Owner**
      (identification etablie, `entities/selectors/accessors.py`). Donc le gate est
      **`NOT IsTurnOf(Owner)`** = « pas pendant le tour du porteur ». Il n'est PAS redondant avec la
      duree `TurnsFromRounds(1)` : il ferme la fenetre du RESTE du tour de Calandis, ou un tir
      ennemi peut la toucher -- l'**OVERWATCH** (elle-meme porte le trait `Overwatch`, ses cibles
      aussi). Lu du contexte par `is_turn_of_owner(attacker_ctx)` ; non threade -> AUCUNE reduction.
    * **`IsRangedAttack`** (`is_melee is False`) : une attaque de melee reçue n'est PAS reduite ;
      nature du coup inconnue (`None`) -> no-op (convention #106).
    * **MAGNITUDE** : `ConfigVar(0x12)` = `variables["dmgReduction"][level]` (65 niveaux, 30 -> 2183)
      **x mult de rarete** (`dmgReduction` est dans `variablesAffectedByRarityBonus`). Le `.ctor`
      ecrit `mov edx, 0x427` avant la surcharge `AbilityOrEffect$$op_Implicit` qui appelle
      `set_ActiveAbility` (tranchee par son corps, pas par son nom) => l'`AbilityState` que resout
      `GetAbilityState(effet)` est celle de l'ability **ACTIVE** -> `active_ability_level` d'abord
      (meme cascade que `OverwhelmingWrathRangeDmgReductionEffect`).

    Pose (`IdunBattleLogic.Entities.Abilities.Active.Loki.FireAndRepositionAbility$$ExecuteBehaviour`) :
    `UseActiveAbility(Owner, Target, UnitNormalAttackType(Owner)) + ResetMovement(...)
    + AddEffect(0x456, <AbilityStateReference>, source=Owner, targets=Owner, TurnsFromRounds(1))`.
    Source == porteur => l'`AbilityState` bakee par le natif est bien celle du porteur (ce cas n'est
    PAS dans le regime « porteur != source » de #382)."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if is_melee is not False:                      # IsRangedAttack (None = nature inconnue)
            return None
        if is_turn_of_owner(attacker_ctx) is not False:  # NOT IsTurnOf(Owner) -- non threade => muet
            return None
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        red = ability_var("FireAndReposition", "dmgReduction", lvl,   # ConfigVar 0x12 (rarity-scale)
                          multiplier_pct=self.ability_variables_multiplier)
        if not red:
            return None
        return for_subtraction(False, abs(int(red)))   # owner=defenseur ; plat PRE-percage (#120)


class SereneUnifierSenseOfStoneEffect(BaseEffect):
    """`SereneUnifierSenseOfStoneEffect` (EffectType 0x491=1169, nom capte "SereneUnifierSenseOfStone")
    — phase 1 du cycle du passif `SereneUnifier` (TriggeredAbilityType 0x479=1145) de `tauAunShi`
    (Aun'Shi). i2 : « Aun'Shi and friendly units around him take -{dmgReductionPct}% Damage. » #192.

    MIRROR 1:1 de
    `IdunBattle.Entities.Effects.Loki.SereneUnifierSenseOfStoneEffect$$CreateEffectDamageMalusForDefense` :

        EffectBonus.ForPercentDecrease( DSLFactory.get_OwnerIsTarget,
                                        DSLFactory.ConfigVar(0x46, GetAbilityState(effet), mult@+0x60),
                                        Nullable<AbilityOrEffect>(0x479 = 1145 SereneUnifier) )

    Aucun autre noeud : PAS de gate melee/ranged, PAS de gate profil de degat, PAS de gate normal-only,
    pas d'`ActiveCondition`. ⇒ −`dmgReductionPct`% sur **TOUT** degat recu par le porteur, quel que soit
    le vecteur. Jumeau STRUCTUREL EXACT de `VexillaMagnificaDmgReductionEffect` ci-dessus (meme
    `ForPercentDecrease(OwnerIsTarget seul, ConfigVar 0x46)`), et de la famille `PrioritisedEfficiency_
    DmgReduction` (meme forme, ConfigConst au lieu de ConfigVar).

    ⚠ CE N'EST PAS UNE AURA cote SOURCE, malgre le libelle « aura d'equipe ». Le decompile tranche :
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SereneUnifierAbility$$CreateBehaviour` pose la
    phase 1 par `AddEffect(0x491, AbilityStateReference, source = owner@0x160, targets = <selecteur>,
    TurnsFromRounds(1))` — l'effet est donc **MATERIALISE sur CHAQUE beneficiaire** (il apparait dans
    SA liste `decisionView.units[].effects`, `source` = Aun'Shi), et son unique noeud de declenchement
    est `get_OwnerIsTarget`. Canal PORT = `create_effect_damage_malus_for_defense` STANDARD (l'effet vit
    sur le DEFENSEUR), PAS `create_aura_defense_damage_malus_for_ally` : il n'existe AUCUN
    `SereneUnifierSenseOfStoneEffect$$CreateTargetSelector`, la selection est faite UNE FOIS a la pose.
    Selecteur natif (pour memoire, il appartient a la POSE) :
    `(AdjacentFriends(owner, 1) + owner) + UnitsFromFaction(SurroundingFriends(owner, ConfigConst(0x16)
    = range = 2) − AdjacentFriends(owner, 1), UnitFaction.Tau = 9)` = Aun'Shi LUI-MEME + ses amis
    adjacents (TOUTE faction) + ses amis T'au a distance 2. Mesure #192 : les 3 beneficiaires attendus
    portent bien 1169 avec `src` = Aun'Shi.

    MAGNITUDE : `ConfigVar(0x46)` = `dmgReductionPct` de la config de `SereneUnifier` (25 → 50, plateau
    a 50 des L50 ; **HORS** `variablesAffectedByRarityBonus` = ['extraDmg'] ⇒ multiplier INERTE, il est
    passe pour la forme comme sur `VexillaMagnifica`). SereneUnifier est le PASSIF d'Aun'Shi ⇒
    `ability_level` (passiveAbilityLevel), fallback `level`.

    RESIDU (identique a `FightingRetreatDmgReductionEffect`) : le natif indexe `ConfigVar` sur
    l'`AbilityState` de la **SOURCE** (Aun'Shi, `AddEffect` passe SON `AbilityStateReference`) ; l'effet
    seede depuis `decisionView.effects` porte, lui, le niveau du **PORTEUR** (`EffectFactory.create`).
    Sur un roster homogene (tous les heros au meme palier, cas des runners) les deux coincident ;
    ils divergeraient sur un banc a paliers melanges. La POSE (behaviour turn-start + cycle
    `Modulo(PlayerTurnsStarted, 3)`) n'est pas portee — l'effet est CONSOMME tel qu'il est capte, comme
    `VexillaMagnifica_DmgReduction` / `PrioritisedEfficiency_DmgReduction`.

    GROUND TRUTH #192 (`probe_192_sense_of_stone.py`, MC1_67 seed 20137, cast 1137 MurderousSwing de
    `worldExecutions` sur 2 cibles) : banc AVEC porteur mais AVANT le turn-start adverse (1169 absent)
    = rapport offline/live 1,0000 ; MEME banc apres 2 `endturn` (1169 present, rem=1, src=Aun'Shi) =
    **2,0000 EXACT sur les DEUX cibles** ; banc temoin (porteur remplace par une vanille, MEMES 2
    `endturn`) = 1,0000. 2,0000 = 1/(1−50/100) avec `dmgReductionPct[L50] = 50`."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        # ConfigVar(0x46) = `dmgReductionPct` de SereneUnifier. Le natif n'a QUE `get_OwnerIsTarget`
        # -> aucun gate ici (ni melee/ranged, ni profil, ni normal-only).
        lvl = self.ability_level if self.ability_level is not None else self.level
        pct = ability_var("SereneUnifier", "dmgReductionPct", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        if not pct:
            return None
        return for_percent_decrease(False, abs(int(pct)))   # owner=defenseur (l'effet est sur la cible)


class PsychicFortressDmgReductionEffect(BaseEffect):
    """`PsychicFortress_DmgReductionEffect` (effet 0x3f2=1010, passif PsychicFortress de Tigurius
    ultraTigurius ; base `ADamageDefenseModifierAbilityEffect(1000=0x3e8=PsychicFortress AbilityOrEffect)`,
    IdunBattle.Entities.Effects.Loki.PsychicFortress_DmgReductionEffect$$.ctor) — AURA de RÉDUCTION PLATE du dégât PSYCHIQUE REÇU par les AMIS ring-1 du porteur.
    L'effet vit sur le PORTEUR (posé par `IdunBattleLogic.Entities.Abilities.Active.Loki.PsychicFortressAbility$$CreateBehaviour` :
    `AddEffect(0x3f2, AbilityStateRef, context@0x148)` — capté live source=Tigurius, JAMAIS matérialisé
    sur les amis) et se PROJETTE sur les cibles à la CALC (boucle state-wide EffectWithTarget × cibles de
    `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction`, canal `aura_defense_damage_malus_from_units`).

    - dégât `IdunBattle.Entities.Effects.Loki.PsychicFortress_DmgReductionEffect$$CreateDamageModifier` : `EffectBonus.ForAddition(OwnerIsTarget &
      DamageProfileIs(0xd=Psychic), Multiply(ConfigVar(0x12=dmgReduction, GetAbilityState(effet),
      mult@+0x60), Direct(-1)@factory+0xd8))` = SOUSTRACTION plate négative (slot additif défenseur @+0x10,
      jumeau STRUCTUREL EXACT de `DaughterOfTheAbyss_OwnerDmgReduction IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_OwnerDmgReductionEffect$$CreateEffectDamageMalusForDefense` et `Nightshroud IdunBattle.Entities.Effects.Loki.Nightshroud_DmgReduction_Effect$$CreateDamageDefenseModifier`).
    - cibles `IdunBattle.Entities.Effects.Loki.PsychicFortress_DmgReductionEffect$$CreateTargetSelector` : `Friends(SurroundingUnits(context@0x148, range=1,
      includeCenter=false))` = amis à distance EXACTEMENT 1 (ring-1), EXCLUT le porteur (includeCenter=false).

    MAGNITUDE : `dmgReduction[ablvl]` (12->873, RARITY-SCALÉ : dmgReduction ∈ variablesAffectedByRarityBonus)
    × mult du porteur (Tigurius = le carrier de l'aura -> `self.ability_level`/`self.ability_variables_multiplier`).
    i2 : « ... Also reduces incoming Psychic Damage by 873. » Placement PRÉ-perçage (`for_subtraction(False)`
    -> `flat_reductions`) présumé par la famille Nightshroud (jumeau structurel, validé #120) : additif défenseur
    plat soustrait de la BASE pré-perçage, dilué par perçage/armure PUIS scalé ×%-list. Gate Psychic-only
    (l'aura protège les amis du porteur contre les attaques PSYCHIQUES des psykers ennemis).

    ⚠ RECTIFICATION #437-r1-r1-r1 : la ligne « base `ADamageDefenseModifierAbilityEffect` » ci-dessus
    est FAUSSE. `data/symbols/<build>/frida/classes.tsv` donne le parent
    `IdunBattle.Entities.Effects.DamageModifierAbilityEffect`, et `methods.tsv` ne lui connait que
    `CreateDamageModifier` — cohérent avec le symbole cité plus haut. La face NATIVE est donc
    ATTAQUANT (cf. `AURA_DEFENSE_MALUS_NATIVE_FACE` ci-dessous)."""

    def create_aura_defense_damage_malus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if (c.get("damage_profile") or "") != "Psychic":     # DamageProfileIs(0xd) IdunBattle.Entities.Effects.Loki.PsychicFortress_DmgReductionEffect$$CreateDamageModifier
            return None
        if c.get("tgt_id") == c.get("owner_id"):              # SurroundingUnits(includeCenter=false) exclut le porteur
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("tgt_team"):
            return None                                       # Friends : cible ALLIÉE du porteur
        op, tp = c.get("owner_pos"), c.get("t_pos")
        if not op or not tp:
            return None
        import hexgeo
        if hexgeo.distance(op, tp) != 1:                      # SurroundingUnits(range=1, includeCenter=false) = ring-1 exact IdunBattle.Entities.Effects.Loki.PsychicFortress_DmgReductionEffect$$CreateTargetSelector
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        amt = ability_var("PsychicFortress", "dmgReduction", lvl,   # ConfigVar 0x12 (rarity-scalé × mult)
                          multiplier_pct=self.ability_variables_multiplier)
        if not amt:
            return None
        return for_subtraction(False, abs(int(amt)))          # owner=défenseur -> flat_reductions pré-perçage (famille Nightshroud)

    # #437-r1-r1-r1 : parent `DamageModifierAbilityEffect`, seul slot `CreateDamageModifier`
    # -> face ATTAQUANT. REGIME DEGENERE (canal ADDITIF `Addition@+0x10`, somme sur les DEUX
    # accumulateurs par `PredictAttackRaw`, RE #462-r4b-r1) : aucune valeur ne bouge.
    AURA_DEFENSE_MALUS_NATIVE_FACE = "attacker"


def camo_cloak_cover(unit_state: "Mapping | None") -> bool:
    """MIRROR de `IdunBattle.Entities.Effects.Loki.CamoCloak_DmgReductionEffect$$HasValidEffectTrigger`
    -- le PREDICAT unique du kit CamoCloak, appele DEUX fois par le natif (cf.
    `CamoCloakDmgReductionEffect` ci-dessous) :

        DSLTriggers.HasEffect(<sel>, 0x3f5 = 1013 LightCover, onlyActive = 0, effectTargetType = 6)
        op_BitwiseOr
        DSLTriggers.IsEffectTarget(<sel>, 0x402 = 1026 BigTarget_AdjacentEffect)

    Les deux membres sont les DEUX effets du jeu qui retirent des COUPS a une attaque ranged recue
    (`LightCoverEffect` -2, `BigTargetAdjacentEffect` -1) -- c'est la lecture EXACTE de l'i2
    « Whenever an incoming ranged attack has its number of hits reduced for any reason ». Le natif
    n'enumere PAS « toute reduction de coups » : il nomme ces deux ids, et rien d'autre (ni
    `Camouflage`, ni `Diminutive`, ni `FightingRetreat`, qui reduisent pourtant aussi les coups).

    ⚠ `onlyActive = 0` (LU au decompile) : le natif ne filtre PAS sur `EffectComponent.IsActive` --
    d'ou le mirror `EffectsState.has_effect` (qui ne filtre que `consumed`) et non `active_effects`
    (qui, lui, reboucle sur `is_active` et se mordrait la queue).

    Cles du `unit_state` (`runner.components.unit_state_for_effects` / `playbook.scene.Scene.
    unit_state`), tri-etat comme partout : ABSENTES = « donnee non threadee » -> True (« present ==
    actif », le canal `decisionView` par defaut ne publie QUE les effets actifs)."""
    if unit_state is None:
        return True
    lc = unit_state.get("has_effect_light_cover")
    bt = unit_state.get("is_target_of_big_target_adjacent")
    if lc is None and bt is None:
        return True
    return bool(lc) or bool(bt)


class CamoCloakDmgReductionEffect(BaseEffect):
    """`CamoCloak_DmgReductionEffect` (EffectType 0x3f6 = **1014**, nom capte "CamoCloak_DmgReduction")
    -- owner-effect PERMANENT du passif `CamoCloak` de `ultraEliminatorSgt` << Certus >> (et du summon
    `ultraSmnEliminator`). i2 : « Whenever an incoming ranged attack has its number of hits reduced
    for any reason, it deals -{dmgReduction} Damage per hit to this unit. »

    POSE -- `IdunBattleLogic.Entities.Abilities.Active.Loki.CamoCloakAbility$$CreateBehaviour` :

        AddEffect(0x3f6, <BaseTriggeredAbility.get_AbilityStateReference>, Owner@0x148, duree = 0)

    (`BaseTriggeredAbility` : malgre le namespace `Abilities.Active.Loki`, c'est une TRIGGERED --
    `TriggeredAbilityType.CamoCloak = 0x3eb = 1003`, et `unit_map kit` la classe `voie: passive`.)
    Duree nulle => permanent, pose a l'init du porteur.

    DEGAT -- `IdunBattle.Entities.Effects.Loki.CamoCloak_DmgReductionEffect$$CreateDamageModifier`
    (corps INLINE, mirror 1:1) :

        EffectBonus.ForAddition(
            get_OwnerIsTarget
              & HasValidEffectTrigger(Target@0x178)          # cf. `camo_cloak_cover` ci-dessus
              & IsRangedAttack,
            Multiply( ConfigVar(0x12 = dmgReduction, GetAbilityState(effet), config@+0x60),
                      Direct(-1)@DSLFormulas+0x38 ) )

    * **KIND = ForAddition** : le corps inline ecrit le montant au champ **+0x10** de la struct
      `EffectBonus`, EXACTEMENT le slot qu'ecrit `IdunBattle.Entities.Effects.EffectBonus$$ForAddition`
      (`ret+0x10 = amount`) -- distinct de ForPercentIncrease (+0x08), ForSubtraction (+0x18),
      ForOverride (+0x28). Le `x Direct(-1)` rend le montant NEGATIF : c'est une SOUSTRACTION PLATE.
      JUMEAU STRUCTUREL EXACT de `IdunBattle.Entities.Effects.Loki.PsychicFortress_DmgReductionEffect$$CreateDamageModifier`
      (meme `ForAddition(Multiply(ConfigVar 0x12, Direct(-1)))`, meme slot) -> canal port
      `for_subtraction(False, |amt|)` = `flat_reductions`, additif DEFENSEUR **PRE-percage**
      (famille Nightshroud, ground truth #120/#111). Ce n'est donc **PAS** le canal
      `CreateEffectDamageMalusForDefense` de `1110 FireAndReposition` (slot +0x18) ni une pose de
      `statType` : deux noms natifs differents, meme bac d'arrivee cote port.
    * **`IsRangedAttack`** : une melee recue n'est PAS reduite ; nature inconnue (`None`) -> no-op.
    * **MAGNITUDE** : `ConfigVar(0x12)` = `variables["dmgReduction"][level]` de l'ability
      **CamoCloak** (65 niveaux, 5 -> 364 ; L50 = 277) **x mult de rarete** (`dmgReduction` est dans
      `variablesAffectedByRarityBonus`). Le `.ctor` fait `mov edx, 0x3eb` puis
      `jmp DamageModifierAbilityEffect$$.ctor` (RVA calculee depuis l'encodage du `jmp`), dont
      l'`AbilityOrEffect$$op_Implicit` appelle **`set_TriggeredAbility`** (surcharge tranchee par son
      CORPS, jamais par son nom) => l'`AbilityState` resolue est celle d'une ability NON-active,
      c.-a-d. le niveau PASSIF du porteur -> `ability_level` (jamais `active_ability_level`).

    ACTIVE-CONDITION -- `IdunBattle.Entities.Effects.Loki.CamoCloak_DmgReductionEffect$$CreateActiveCondition`
    = `HasValidEffectTrigger(Owner@0x148)`, c.-a-d. **le meme predicat** que celui du trigger de
    degat, sur `Owner` au lieu de `Target`. Sous le `get_OwnerIsTarget` en tete du AND, les deux
    selecteurs designent la MEME entite : le gate de couvert est donc porte UNE fois, dans
    `is_active` -- le repeter dans le canal de degat serait redondant, et surtout impossible (ce
    canal ne recoit que `is_melee`/`damage_profile`/`attacker_ctx`, aucun contexte du DEFENSEUR).
    `active_effects` filtre par `is_active` AVANT d'appeler le canal (`damage_model.
    defender_modifiers`, `Scene.effects`) : l'ordre du natif est preserve.

    POSE HORS COUVERT -- case-366-r1-camo-seed, MESURE et non deduite. La pose native est
    INCONDITIONNELLE (le `CreateBehaviour` ci-dessus n'a aucun `If`), donc l'instance EXISTE
    toujours ; hors couvert elle est INERTE, pas ABSENTE. Le canal `decisionView` par DEFAUT
    DROPPE les inertes (d'ou l'illusion d'absence) ; `decision_view_seed_body`
    (`includeInactive`) la publie avec `active: false`. Le port materialise donc l'instance dans
    LES DEUX cas : par le canal quand il la porte, sinon par
    `factory.ABILITY_INIT_OWNER_EFFECTS["CamoCloak"]` (idempotent).

    `active_condition_ported` reste **False** : l'instance seedee nait `active = True` et c'est
    `is_active` (la condition PORTEE) qui la ferme ; le flag capte, quand il existe, garde son mot
    a dire. Ce qui la RALLUME quand la sim fait entrer le porteur en couvert est le SECOND
    `RefreshEffects(RefreshEffectTrigger.UnitPositionChanged)` d'
    `IdunBattle.Operations.MoveUnitOperation$$Execute`
    (`runner/operations/movement.py::refresh_effects_after_move_triggers`) : le premier tombe
    AVANT `EvaluateAfterMoveTriggers`, donc avant que `LightCoverAbility` n'ait pose `1013`."""

    def is_active(self, unit_state: Mapping | None = None) -> bool:
        return camo_cloak_cover(unit_state)          # CreateActiveCondition = HasValidEffectTrigger(Owner)
    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if is_melee is not False:                    # IsRangedAttack (None = nature inconnue -> muet)
            return None
        # `GetAbilityState(effet)` sur un `AbilityOrEffect` TriggeredAbility -> niveau PASSIF.
        lvl = self.ability_level if self.ability_level is not None else self.level
        red = ability_var("CamoCloak", "dmgReduction", lvl,      # ConfigVar 0x12 (rarity-scale)
                          multiplier_pct=self.ability_variables_multiplier)
        if not red:
            return None
        return for_subtraction(False, abs(int(red)))  # x Direct(-1) -> flat_reductions pre-percage

    # #437-r1-r1-r1 : derive de `DamageModifierAbilityEffect` (classes.tsv), n'implemente que
    # `CreateDamageModifier` (methods.tsv) -> face ATTAQUANT. REGIME DEGENERE : le canal est
    # ADDITIF (`Addition@+0x10`, valeur negative), et `PredictAttackRaw` SOMME le `+0x10` des DEUX
    # accumulateurs avant `CalculateBaseDamageWithAllModifiers` (RE #462-r4b-r1) -> les deux
    # attributions predisent le meme nombre. Posee parce qu'elle est LUE.
    DEFENSE_MALUS_NATIVE_FACE = "attacker"


#: Nom gameconfig du PASSIF -- la CONFIG que `ConfigVar(config@+0x60)` indexe. C'est le NOM, jamais
#: l'ordinal : `EffectType 1118` et `TriggeredAbilityType 1118` nomment deux choses differentes, et
#: la config du passif est la TRIGGERED **1009** (cf. l'en-tete de `WhipcoilBodyReduceDmgEffect`).
_WHIPCOIL_ABILITY_ID = "WhipcoilBody"
#: `AbilityVariableType 0x12 = 18` (`frida/enums.tsv`), DANS `variablesAffectedByRarityBonus`.
_WHIPCOIL_DMG_VAR_KEY = "dmgReduction"


class WhipcoilBodyReduceDmgEffect(BaseEffect):
    """`WhipcoilBody_ReduceDmg` (`EffectType` 0x45e = **1118**) -- owner-effect PERMANENT du passif de
    kit `WhipcoilBody` : le PORTEUR subit `-dmgReduction` de degat PLAT sur toute attaque de MELEE
    dont il est la cible. #1016.

    i2 : << This unit takes -{[dmgReduction]} Damage from melee attacks. >> (509 au dernier des
    65 paliers) -- l'i2 ne mentionne NI adjacence NI camp de l'attaquant, et le decompile non plus.

    ## LES DEUX ARTEFACTS NATIFS, ET CE QU'ILS N'OVERRIDENT PAS

        IdunBattleLogic.Entities.Abilities.Triggered.Loki.WhipcoilBodyAbility
            : IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility        (`frida/classes.tsv`)
        IdunBattleLogic.Entities.Abilities.Triggered.Loki.WhipcoilBody_ReduceDmgEffect
            : IdunBattle.Entities.Effects.BaseEffect                            (`frida/classes.tsv`)

    Blocs `methodPointers` du PE, LUS (les corps dedupliques par l'ICF resolus par leur ADRESSE,
    jamais par le nom que ghidra leur donne) -- deux blocs CONTIGUS, ce qui les cadre l'un l'autre :

        WhipcoilBody_ReduceDmgEffect : [ .ctor,
                                         CreateActiveCondition  = <DSLTriggers+0x40>,
                                         CreateTargetSelector   = <DSLSelectors+0x30> = Owner,
                                         CreateEffectDamageMalusForDefense ]
        WhipcoilBodyAbility          : [ GetEffectType, .ctor ]

    `WhipcoilBodyAbility` n'override donc QUE `$$GetEffectType`, dont le corps ENTIER est
    `return 0x45e` : l'appariement ability -> effet est **LU**, pas devine (meme forme exacte que
    `ToughToKill_CritAbility` / `Ramshackle` / `Skullsmasher`). Tout le reste vient de la base :

        IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateTrigger
            = OnOwnerSpecificAbilityInit(this.AbilityType@+0x10)
        IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateCondition
            = <DSLTriggers+0x70> = YesTrigger
        IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateBehaviour
            = If( CreateCondition(abilityState),
                  AddEffect( GetEffectType(), AbilityState(Owner@DSLSelectors+0x30, abilityType),
                             targets = Owner@+0x30, source = Owner@+0x30, turns = <zeroe> ),
                  null )

    -> owner-effect PERMANENT pose a l'init du porteur. `CreateActiveCondition` de l'effet est
    `<DSLTriggers+0x40>`, la constante VRAIE (meme type que le `YesTrigger` de `+0x70`, `+0x48` en
    etant l'`op_LogicalNot`) : l'effet est TOUJOURS ACTIF, donc TOUJOURS publie par
    `decisionView.effects` (canal ACTIF-ONLY) -- pas d'`active_condition_ported`, et le seed
    `ABILITY_INIT_OWNER_EFFECTS["WhipcoilBody"]` n'est qu'un FILET (idempotent).

    ## LE CANAL, LU EN ENTIER

        IdunBattleLogic.Entities.Abilities.Triggered.Loki.WhipcoilBody_ReduceDmgEffect$$
        CreateEffectDamageMalusForDefense =
            EffectBonus.ForSubtraction(
                get_OwnerIsTarget & IsMeleeAttack,
                ConfigVar(0x12 = dmgReduction, GetAbilityState(effet), config@+0x60) )

    * **DEUX conjoints, pas quatre.** C'est le contraste a ne PAS rater avec le voisin de forme
      `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrorsLament_DamageReductionEffect$$
      CreateEffectDamageMalusForDefense`, qui enchaine `IsAdjacent(Caster@+0x48, Owner@+0x30, 3)
      & AreEnemies(Owner@+0x30, Caster@+0x48, 0) & IsMeleeAttack` : celui-ci n'a **ni** `IsAdjacent`
      **ni** `AreEnemies`, et son premier operande est `get_OwnerIsTarget`. Recopier le trigger du
      voisin restreindrait la reduction aux seuls attaquants adjacents et ennemis -- une faute
      silencieuse, qui ne leve pas.
    * **AUCUNE patte AURA, et ce n'est pas un oubli.** `get_OwnerIsTarget` =
      `AreEqual(Owner@DSLSelectors+0x30, Target@DSLSelectors+0x60)` : des que le porteur n'est pas
      la cible du coup, le trigger est FAUX. La moitie `Owner != cible` de la boucle
      `effets x cibles` de `IdunBattle.Core.Services.DamageCalculations$$
      CalculateDefenderModifiersForPrediction` ne peut donc rien produire -> pas de
      `create_aura_defense_damage_malus_for_ally` (contraste, la encore, avec `TerrorsLament`, dont
      le trigger porte sur `(Caster, Owner)` et accorde donc les deux pattes).
    * **`ForSubtraction`, pas `ForAddition`** : tranche par l'ADRESSE de la cible du `call`
      (`IdunBattle.Entities.Effects.EffectBonus$$ForSubtraction`, qui ecrit le montant au champ
      `+0x18` de la struct `EffectBonus`) -> reduction PLATE versee dans `flat_reductions`, additif
      DEFENSEUR pre-percage. Meme canal que `Nightshroud_DmgReduction` et
      `TerrorsLament_DamageReduction`.
    * PAS de `DEFENSE_MALUS_NATIVE_FACE` : l'effet derive de `BaseEffect` (pas de
      `DamageModifierAbilityEffect`) et implemente DIRECTEMENT
      `CreateEffectDamageMalusForDefense` -- la contribution sort donc bien par la face DEFENSEUR,
      contrairement a `Terrifying_ExtraDefense_Effect` / `MarkerlightEffect`, dont le forwarder
      `IdunBattle.Entities.Effects.DamageModifierAbilityEffect$$CreateEffectDamageBonusForAttack`
      la verse cote attaquant.

    ## ⚠ QUATRE ENUMS, LE MEME ENTIER

        EffectType            0x45e = 1118 = WhipcoilBody_ReduceDmg   <- CE qu'on lit ici
        TriggeredAbilityType  0x45e = 1118 = TerrorsLament            <- une AUTRE ability, REELLE
        TriggeredAbilityType         1009  = WhipcoilBody             <- la CONFIG du passif
        ActiveAbilityType            1009  = ResurrectionOrb          <- deja portee, necrons.py:723

    Lire `1118` comme une `TriggeredAbilityType` chercherait la config de `TerrorsLament` : elle
    existe et porte elle aussi un `dmgReduction`, donc l'erreur ne leverait PAS -- elle rendrait la
    mauvaise magnitude, en silence. C'est pourquoi la cle de config est le NOM `"WhipcoilBody"`.

    ## PORTEURS (`unit_map find --ability WhipcoilBody`, voie `passive`) -- 4, dont 1 summon

    `necroNpc4Destroyer`, `necroNpc4DestroyerLHE`, `necroNpc4DestroyerSurv` (npc) et
    `necroSmnDestroyer` (SUMMON). ⚠ `necroSmnDestroyer` est un summon **SANS invocateur d'unite** :
    la seule ability du gameconfig qui le declare est `EnvFactionSummons:Necrons`, qu'AUCUNE unite
    ne porte (meme constat que `necrons.py` pour `TunnelingHorror`). La confrontation live passe
    donc par la GREFFE du passif sur une unite du pool (`case-92` sec.5bis), et la condition de
    greffe est VERIFIEE au decompile : cet arbre ne lit NI stat NI trait du porteur -- seulement
    `ConfigVar(dmgReduction)` de la config `WhipcoilBody` et le fait que le porteur soit la cible
    d'un coup de melee.

    ASCII only.
    """

    def _amount(self) -> "int | None":
        """`ConfigVar(0x12 = dmgReduction, GetAbilityState(effet), config@+0x60)`.

        `AbilityVariableType 0x12 = 18 = dmgReduction` (`frida/enums.tsv`) -- et NON
        `AbilityConstantType 0x12 = hpPct`, l'autre lecture possible du meme ordinal : c'est
        `IdunBattleLogic.Entities.DSLFormulas$$ConfigVar` (-> `GetVariableForLevel`) qui tranche,
        pas `GetNumberConstant`. `WhipcoilBody.variables.dmgReduction` a **65 paliers** (7 -> 509)
        et figure dans `variablesAffectedByRarityBonus` -> le multiplicateur de rarete MORD.

        `AOwnerEffectTriggeredAbility$$CreateBehaviour` bake `AbilityState(Owner, abilityType)` --
        l'etat du PASSIF du porteur -> `ability_level` de l'instance (jamais
        `active_ability_level`), pose par le seed comme par la capture `decisionView.effects`."""
        lvl = self.ability_level if self.ability_level is not None else self.level
        v = ability_var(_WHIPCOIL_ABILITY_ID, _WHIPCOIL_DMG_VAR_KEY, lvl,
                        multiplier_pct=int(self.ability_variables_multiplier or 100))
        return int(v) if v else None

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        """PATTE SELF, et la SEULE -- cf. l'en-tete de la classe.

        `get_OwnerIsTarget` est COLLAPSE dans le canal lui-meme : cet agregateur n'est appele que
        pour l'effet du DEFENSEUR courant (`damage_model.defender_modifiers` /
        `playbook.prediction._shared`), donc `Owner == Target` par construction du site d'appel.
        Il ne reste qu'`IsMeleeAttack` a evaluer.

        `is_melee` suit la convention tri-etat #106 : `None` = nature de l'attaque NON DECLAREE ->
        le gate se FERME (degradation RESTRICTIVE, meme lecture que `ParryEffect` et
        `TerrorsLamentDamageReductionEffect`). Le regime permissif inverse ferait porter la
        reduction a des attaques a distance, que le natif n'y soumet pas."""
        if is_melee is not True:                     # gate IsMeleeAttack (None = nature inconnue)
            return None
        v = self._amount()
        return for_subtraction(False, v) if v else None   # owner = le DEFENSEUR -> flat_reductions


# ==================================================================================================
# Les DEUX auras de REDUCTION de degat des abilities MYTHIQUES de MACHINE OF WAR (#1038-r1/#1042-r1).
#
# Elles partagent EXACTEMENT la meme face DEGAT -- meme slot natif, meme canal, meme variable :
#
#     <X>_DamageReductionEffect$$CreateEffectDamageMalusForDefense
#         = EffectBonus.ForPercentDecrease(
#               get_OwnerIsTarget,
#               ConfigVar(AbilityVariableType.dmgReductionPct = 0x46, GetAbilityState(effet),
#                         <effet+0x60>) )
#
# et ne different QUE par leur `$$CreateTargetSelector`. Le corps de 1443 est INLINE (ghidra n'y
# montre aucun `call` a `EffectBonus$$ForPercentDecrease`), celui de 1445 appelle la fabrique
# EXPLICITEMENT -- et les deux ecrivent le MEME champ. Verifie en relisant
# `IdunBattle.Entities.Effects.EffectBonus$$ForPercentDecrease`, dont le corps est :
#
#     out@+0x00 = trigger
#     out@+0x08 = Multiply( Direct(-1), amount )        <- le slot POURCENT
#
# et le corps inline de 1443 ecrit litteralement `local_a8 = get_OwnerIsTarget` puis
# `uStack_a0 = <noeud binaire>( <noeud a -1 = 0xffffffff>, ConfigVar )`, c.-a-d. les deux memes
# champs, dans le meme ordre, avec la meme negation. Ce n'est donc pas une famille SUPPOSEE : les
# deux corps sont le meme code, l'un inline et l'autre non.
#
# CANAL PORT : les DEUX exposent un `$$CreateTargetSelector`, donc ce sont des `EffectWithTarget` --
# `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` itere
# `<effet> x <CIBLES du selecteur>` en ecrivant `AbilityEntities+0x18 (Owner) <- CHAQUE CIBLE`, si
# bien que `get_OwnerIsTarget` y signifie << la cible du coup est-elle l'une des cibles du selecteur
# ? >>. Le canal est donc `create_aura_defense_damage_malus_for_ally`, JAMAIS
# `create_effect_damage_malus_for_defense` (qui donnerait la reduction a la MoW porteuse, que le
# natif n'en fait beneficier dans aucun des deux cas).
#
# FACE NATIVE : les deux classes derivent de `IdunBattle.Entities.Effects.BaseEffect` (ctor relu :
# `BaseEffect..ctor(this, AbilityOrEffect(<la triggered>), hasAutomaticActivation = 1)`) et
# implementent le slot `CreateEffectDamageMalusForDefense` EN PROPRE -- pas le forwarder
# `DamageModifierAbilityEffect$$CreateEffectDamageBonusForAttack`. La face est donc DEFENSEUR,
# c.-a-d. le defaut `BaseEffect.AURA_DEFENSE_MALUS_NATIVE_FACE` : rien a declarer (#437-r1-r1-r1).
#
# MAGNITUDE : `ConfigVar(0x46)` est indexe par `GetAbilityState(effet)` = l'`AbilityStateReference`
# BAKEE dans `EffectComponent+0x18` a la pose. Les deux effets sont des OWNER-effects
# (`AddEffect(..., source = Owner, targets = Owner)`), donc source == porteur : le couple se relit
# sur l'INSTANCE (`self.ability_level` / `self.ability_variables_multiplier`), que
# `snapshot._rebake_tertiary_owner_effects` a deja re-bake sur le couple TERTIAIRE (1..4 / 100) --
# et non sur celui des PASSIFS (50 / 180 en runner normalise). C'est ce re-bake qui rend le niveau
# EXACT ici ; sans lui `ability_var` lirait `dmgReductionPct[50]`, hors des 4 paliers mythiques.
# Les deux configs portent `dmgReductionPct = [10, 13, 16, 20]` et `variablesAffectedByRarityBonus =
# ['dmgReductionPct']` -> le multiplicateur MORD.
# ==================================================================================================

#: `AbilityVariableType 0x46 = 70 = dmgReductionPct`, resolu par son NOM (`frida/enums.tsv`).
#: ⚠ `AbilityConstantType 70` nomme AUTRE CHOSE : c'est `DSLFormulas$$ConfigVar` (-> `GetVariableFor
#: Level`) qui tranche au call-site, pas `GetNumberConstant` -- confondre les deux ne leverait pas.
_MYTHIC_VAR_DMG_REDUCTION_PCT = "dmgReductionPct"
#: Nom gameconfig de l'ability MYTHIQUE dont la config est indexee -- le NOM, jamais l'ordinal.
#: `TriggeredAbilityType 0x5aa = 1450 = ContemptuousDisregard` (l'`AbilityOrEffect` du ctor de 1443),
#: `TriggeredAbilityType 0x5ab = 1451 = WisdomOfTheAncients` (celui du ctor de 1445).
_CONTEMPTUOUS_DISREGARD_ABILITY_ID = "ContemptuousDisregard"
_WISDOM_OF_THE_ANCIENTS_ABILITY_ID = "WisdomOfTheAncients"

#: Cle du callable PAR PORTEUR pose par les DEUX facades (COMBAT `runner/damage_model.py`,
#: PREDICTION `playbook/prediction/_shared.py`) -- mirror du `$$CreateTargetSelector` de 1445,
#: evalue contre l'etat REEL. Rend un `frozenset` d'ids, ou `None` = NON MESURE. MEME forme et MEME
#: raison que `obsessive_annunciation.CTX_ADJACENT_ENEMY_IDS_OF` (#954).
CTX_WISDOM_TARGET_IDS_OF = "wisdom_of_the_ancients_target_ids_of"


class ContemptuousDisregardDamageReductionEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.ContemptuousDisregard_DamageReductionEffect` (`EffectType`
    0x5a3 = **1443**) -- AURA de reduction de degat de l'ability MYTHIQUE `ContemptuousDisregard`
    (`TriggeredAbilityType` 0x5aa = 1450) des MoW `blackForgefiend` / `blackNpcMowForgefiend`.
    #1038-r1.

    La POSE est portee depuis #1038 (`ABILITY_INIT_OWNER_EFFECTS["ContemptuousDisregard"]`,
    owner-effect PERMANENT a l'init) ; c'est la face DEGAT qui manquait, et son verrou tenait en
    DEUX pieces, toutes deux tombees : le canal de RARETE (#999-r3-r1) puis l'entree d'une MoW
    porteuse dans l'univers des agregateurs d'aura (#999-r3-r1-r1).

    ## MIRROR 1:1 -- `...ContemptuousDisregard_DamageReductionEffect$$CreateTargetSelector`

        Filter( UnitsWithRarity( Friends(of = Owner@<DSLSelectors+0x30>, entities = AllUnits(), 3),
                                 idun.meta.Rarity.Mythic = 5, 3 ),
                HasTileStatusEffect( Tiles(<DSLSelectors+0x68> = l'element courant du Filter) ) )

    `DSLSelectors$$Filter(entities, filter)` = `FromTrigger(entities, filter, requireContinuous: 0)`,
    et `IdunBattle.Entities.Selectors.FromTriggerSelector$$Select` COPIE l'`AbilityEntities` puis
    **ECRIT le candidat courant a `+0x20` de la copie** avant d'evaluer le trigger -- c'est ce qui
    fait de `<DSLSelectors+0x68>` l'element courant, et non une cible globale. Le prompt de ce port
    l'appelait `ActiveTarget` ; les deux noms designent le meme slot.

    ⇒ la CIBLE du coup beneficie de la reduction ssi elle est (a) une ALLIEE de la MoW,
    (b) de rarete **Mythic**, et (c) sur une tuile qui porte un STATUS-EFFECT de tuile.

    ## LES TROIS ETAGES, ET OU CHACUN SE LIT

      1. `Friends(Owner, AllUnits(), 3)` -> `owner_team == tgt_team`. `Friends` ne retire PAS le
         sujet (`UnitExtensions$$IsFriend(u, u)` est VRAI), mais l'agregateur `aura_defense_damage_
         malus_from_units` n'appelle jamais un porteur sur lui-meme (les deux facades excluent
         `uid == tgt_id` de leurs carriers) : la patte SELF est structurellement hors de portee de
         ce canal. Elle est de toute facon INATTEIGNABLE sur le porteur naturel -- une MoW n'occupe
         aucune tuile, donc l'etage 3 la refuse. RESIDU NOMME : sur un porteur ON-BOARD obtenu par
         GREFFE, le natif pourrait se l'appliquer a lui-meme ; le port ne le peut pas (#1038-r1-r1).
      2. `UnitsWithRarity(., idun.meta.Rarity.Mythic = 5, 3)` -> `tgt_rarity`.
         `IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select` lit
         `GetBaseUnitComponent(e)+0x74` et compare par EGALITE STRICTE (`== this+0x20`), jamais un
         seuil. Canal threade par #999-r3-r1. TRI-ETAT : `None` = NON MESURE -> le gate se FERME.
      3. `HasTileStatusEffect(Tiles(candidat))` -> `t_pos` + `tile_effects_by_pos`.
         `Tiles` = `IdunBattle.Entities.Selectors.UnitsMainTilesSelector` -> la MAIN TILE seule.
         `IdunBattle.Entities.Triggers.HasTileStatusEffectTrigger$$ShouldTrigger` delegue a
         `IdunBattle.Entities.TileExtensions$$HasTileStatusEffect`, qui ne retient QUE les effets
         dont l'`EffectType` est dans le set statique de
         `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$IsTileStatus
         Effect` -- d'ou l'intersection avec `TILE_STATUS_EFFECT_NAMES` ci-dessous. Le filtre est
         INDISPENSABLE cote PREDICTION (`scene.tile_effects_by_pos` porte les noms BRUTS de
         `tileMeta`, y compris `BlockEnteringUnits` / `Thorns_DefenseReduction` / `Melta_ExtraDmg`)
         et IDEMPOTENT cote COMBAT (`tile_status_effects_by_pos` l'applique deja).

    ⚠ CE QUE LA MESURE #1038 NE DISAIT PAS. Elle rapporte `targetIds: []` << y compris avec un ami
    MYTHIQUE place sur une tuile `DryBush` (`LightCover`) >>. `LightCover` n'est PAS un status de
    tuile (le set natif vaut exactement `{Darkness, Fire, Ice, Contaminated, DespoiledGround}`), et
    `LightCover` n'est meme pas porte par la TUILE mais par les UNITES qui s'y tiennent
    (`IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility$$UnitsThatNeedEffect`). Ce
    bras ne separait donc RIEN : son ensemble vide est le comportement NORMAL. La confrontation de
    cet effet exige une tuile portant l'un des cinq status.

    ## MAGNITUDE

    `ConfigVar(0x46 = dmgReductionPct)` sur la config de `ContemptuousDisregard`
    (`[10, 13, 16, 20]`, rarity-scale) -- cf. l'encadre commun ci-dessus pour l'`AbilityState`.
    i2 : << Mythic allies standing on a tile with a status effect take -{dmgReductionPct}% Damage. >>

    Aucun gate de MELEE, de PROFIL ni d'attaquant : le trigger du malus est `get_OwnerIsTarget`
    SEUL, tout le ciblage vivant dans le selecteur."""

    ABILITY_ID = _CONTEMPTUOUS_DISREGARD_ABILITY_ID
    VAR_DMG_REDUCTION_PCT = _MYTHIC_VAR_DMG_REDUCTION_PCT

    def create_aura_defense_damage_malus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        # 1. `Friends(of = Owner@<+0x30>, entities = AllUnits(), 3)` -- equipe non mesuree => FERME.
        ot, tt = c.get("owner_team"), c.get("tgt_team")
        if ot is None or tt is None or ot != tt:
            return None
        # 2. `UnitsWithRarity(., idun.meta.Rarity.Mythic = 5, 3)` -- comparaison au MEMBRE d'enum,
        #    jamais a l'ordinal (cinq enums du build partagent les six ordinaux de rarete, cf.
        #    `entities/rarity.py`). `None` (non mesure) -> FERME.
        if c.get("tgt_rarity") != Rarity.Mythic:
            return None
        # 3. `Filter(., HasTileStatusEffect(Tiles(<element courant>)))` -- la MAIN TILE de la CIBLE.
        tfx, tp = c.get("tile_effects_by_pos"), c.get("t_pos")
        if tfx is None or tp is None:
            return None                                    # canal non threade -> gate FERME
        if not (set(tfx.get(tuple(tp)) or ()) & TILE_STATUS_EFFECT_NAMES):
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        pct = ability_var(self.ABILITY_ID, self.VAR_DMG_REDUCTION_PCT, lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        if not pct:
            return None
        # `ForPercentDecrease` -> %-list DEFENSEUR (face native par defaut). `owner_is_caster` est
        # INERTE sur ce kind (`services/damage_modifiers.py::add_modifier` ne le lit que pour
        # Addition/Subtraction) : on ecrit `False` parce que le beneficiaire est le DEFENSEUR.
        return for_percent_decrease(False, abs(int(pct)))


class WisdomOfTheAncientsDamageReductionEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.WisdomOfTheAncients_DamageReductionEffect` (`EffectType`
    0x5a5 = **1445**) -- AURA de reduction de degat de l'ability MYTHIQUE `WisdomOfTheAncients`
    (`TriggeredAbilityType` 0x5ab = 1451) de la MoW `ultraDreadnought` << Galatian >> /
    `ultraNpcMoWDreadnought`. #1042-r1.

    La POSE est portee et confrontee live depuis #1042 (`ABILITY_INIT_OWNER_EFFECTS`) ; c'est la
    face DEGAT qui manquait.

    ## MIRROR 1:1 -- le `$$CreateTargetSelector`, relu au decompile

        ValidCharacter(x)  = UnitsWithRarity(x, idun.meta.Rarity.Mythic = 5,
                                             UnitSelectionType.OnlyAliveAndTargetable = 3)
        A = ValidCharacter( AdjacentFriends(Owner@<DSLSelectors+0x30>, unique = true, 3) )
        B = ValidCharacter( Friends(of = Owner@<+0x30>, entities = AllUnits@<+0x20>, 3) )
        F = Filter( B, AmountIsGreaterThanZero(
                           UnitsWithTrait( ValidCharacter( AdjacentFriends(
                                               <+0x68> = l'element courant, unique = true, 3) ),
                                           UnitTrait.Hero = 0x10, 3 ) ) )
        return ConditionalSelector( IsMachine(Owner@<+0x30>), ifTrue = F, ifFalse = Unique(A + F) )

    `DSLSelectors$$AdjacentFriends(unit, unique, selectionType)` (surcharge tranchee par la POSITION
    des arguments -- un `1` litteral ne peut pas etre un selecteur de tuile) se developpe en
    `Friends( reference = unit, Units(AdjacentTiles(unit), unique, sel) op_Subtraction unit, sel )`.
    Donc : les unites des tuiles ADJACENTES a `unit`, elle-meme exclue, AMIES de `unit`.

    ⇒ la CIBLE du coup beneficie ssi elle est MYTHIQUE et ALLIEE de la MoW, ET (a) elle a
    elle-meme un ami MYTHIQUE portant `Hero` adjacent (branche `F`), OU (b) elle est adjacente au
    PORTEUR (branche `A`, hors d'atteinte quand le porteur est la MoW -- voir ci-dessous).
    i2 : << ... adjacent to Galatian ... >> pour la branche `A`.

    ## LE `ConditionalSelector` N'EST PAS PORTE, ET C'EST UNE EQUIVALENCE, PAS UN RACCOURCI

    `IdunBattle.Entities.EntityExtensions$$IsMachine(e)` = `GetEntityType(e) == 6`
    (`EntityType.Machine`). Or une entite `EntityType.Machine` n'a **ni tuile ni pied** -- MESURE
    des DEUX cotes du port : cote COMBAT `runner/snapshot.py::_load_machines` ne pose aucun
    `PositionComponent` (c'est meme le DISCRIMINANT ecrit dans `MachineComponent`), cote DECISION
    `playbook/scene.py::step_context` ne verse une MoW dans `pos_by_id` que `if m.get("pos")`,
    `null` par construction. Le probe `probe_1042_wisdom_of_the_ancients_live.py` le mesure aussi
    en live : << sur la MoW porteuse, `AdjacentFriends(Owner)` est structurellement VIDE >>.

        IsMachine(Owner) VRAI  =>  AdjacentTiles(Owner) = {}  =>  A = {}  =>  Unique(A + F) == F

    Les deux branches COINCIDENT donc exactement la ou la condition est vraie, et le port evalue
    `Unique(A + F)` inconditionnellement. Ce n'est valable que tant qu'aucune entite ne peut etre A
    LA FOIS machine ET positionnee ; le garde `test_1038r1_1042r1_auras_mythiques_mow_offline.py`
    (etage `A vide sans position de porteur`) le tient, et rougira si cette premisse tombe.

    ## CANAL DE CONTEXTE -- UN callable PAR PORTEUR, comme `ObsessiveAnnunciation` (#954)

    Contrairement a 1443, ce selecteur pose des questions que le contexte d'un coup ne porte PAS :
    l'adjacence d'un TIERS a la cible, sa rarete et son trait. Le port re-evalue donc le
    `$$CreateTargetSelector` COMPLET par `wisdom_of_the_ancients_target_ids_of(owner_id)`, resolu
    par DEUX substrats (`damage_model` sur l'ECS, `prediction/_shared` sur la `Scene`) avec le MEME
    foyer d'adjacence NATIVE que `_friend_heroes_adjacent_to` (#1019) -- la liste stockee du
    `ConnectivityComponent` plus la porte d'elevation, jamais `hexgeo.distance == 1`, qui
    sur-compte au bord d'une marche (#271).

    TRI-ETAT : callable absent, ou porteur sans equipe -> `None` = NON MESURE -> le gate se FERME
    (jamais un ensemble vide invente, qui se lirait comme << mesure, et personne >>).

    ## MAGNITUDE

    `ConfigVar(0x46 = dmgReductionPct)` sur la config de `WisdomOfTheAncients` (`[10, 13, 16, 20]`,
    rarity-scale) -- cf. l'encadre commun ci-dessus. Le malus n'a AUCUN gate de rarete : tout le
    ciblage vit dans le selecteur (`CreateEffectDamageMalusForDefense` = `ForPercentDecrease(
    get_OwnerIsTarget, ConfigVar(0x46))`, appel EXPLICITE a la fabrique).
    GROUND TRUTH #1042 : ratio **0.800** sur la prediction native au palier 4 (`dmgReductionPct[4]
    = 20`, multiplier 100)."""

    ABILITY_ID = _WISDOM_OF_THE_ANCIENTS_ABILITY_ID
    VAR_DMG_REDUCTION_PCT = _MYTHIC_VAR_DMG_REDUCTION_PCT
    CTX_TARGET_IDS_OF = CTX_WISDOM_TARGET_IDS_OF

    def create_aura_defense_damage_malus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        # `get_OwnerIsTarget` DEVELOPPE : << la cible du coup est-elle l'une des cibles du
        # selecteur ? >> La boucle native ecrit `AbilityEntities+0x18 (Owner) <- CHAQUE CIBLE`,
        # l'agregateur du port pose `owner_id = le PORTEUR` -> on RE-EVALUE le selecteur.
        oid, tid = c.get("owner_id"), c.get("tgt_id")
        resolver = c.get(self.CTX_TARGET_IDS_OF)
        if oid is None or tid is None or not callable(resolver):
            return None
        targets = resolver(int(oid))
        if targets is None or int(tid) not in targets:     # `None` = NON MESURE -> FERME
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        pct = ability_var(self.ABILITY_ID, self.VAR_DMG_REDUCTION_PCT, lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        if not pct:
            return None
        return for_percent_decrease(False, abs(int(pct)))   # %-list DEFENSEUR (face native)
