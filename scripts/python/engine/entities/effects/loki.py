"""Effets du namespace natif `IdunBattle.Entities.Effects.Loki` — 1 classe par effet (VA citée).

Chaque classe override UNIQUEMENT ce qu'elle implémente dans le natif (lu en ghidra). Les magnitudes
non encore confirmées par nom gameconfig renvoient None (pas de contribution) = on N'INVENTE PAS de
valeur non prouvée (cf. doc §17.4 « présent ≠ appliqué »). RapidAssault = seul cas magnitude validé.
"""
from __future__ import annotations

from collections.abc import Mapping

from ...services.effect_bonus import (EffectBonus, for_addition, for_subtraction,
                                      for_percent_decrease, for_percent_increase,
                                      for_percent_subtraction_capped)
from .base import BaseEffect, SubEffectSpec, SAME_TURNS
from .magnitude import ability_var, global_value, trait_var
from ...services.damage_combat import BlockSource


class RapidAssaultExtraDamageEffect(BaseEffect):
    """`RapidAssault_ExtraDamageEffect` (effet 0x4cd=1229).
    - dégât @180f67940 : `ForPercentIncrease(ConfigConst key 0xf)` = trait var `rapidAssaultExtraDmgPct` (=25, scalaire).
    - cycle de vie : posé à l'init d'ability (`RapidAssaultAbility.CreateBehaviour` @181224950 `AddEffect(0x4cd)`),
      RETIRÉ en fin de tour si l'unité a attaqué (`RemoveExtraDamageEffectAbility.CreateTrigger` @181224af0 =
      `On(0x17) & UnitsAttackedThisTurn>0 & HasEffect(0x4cd)`).
    VALIDÉ live : +25% → u94→u84 3012-4524 EXACT."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True) -> EffectBonus | None:
        pct = trait_var("RapidAssault", "rapidAssaultExtraDmgPct")
        return for_percent_increase(True, pct) if pct is not None else None

    @property
    def removed_after_attack(self) -> bool:
        return True


class SquigHoundAdditionalHitsEffect(BaseEffect):
    """`SquigHound_AdditionalHitsEffect` (effet 0x50c=1292, orksRuntherd) — ajoute des coups HETEROGENES
    a l'attaque du porteur : `nrOfHits` coups a degat PROPRE [minDmg,maxDmg] (vars 0xc/0xd de l'ability
    SquigHound, ctor AbilityOrEffect 0x43a=1082) et profil PROPRE (`damageProfile`). Gate = OwnerIsCaster.

    Natif : `SquigHound_AdditionalHitsEffect.CreateAdditionalHits @180f6d000` -> `EffectAdditionalHits.Create
    @180f405b0` {condition=OwnerIsCaster, minDmg=GetMinMaxDamage(effect,idx0)=RandomAmount(ConfigVar(0xc),
    ConfigVar(0xd)), count=GetNumberConstant(0x2f=nrOfHits), damageProfile=GetDamageProfile(config).Value,
    maxDmg=GetMinMaxDamage(effect,idx1)}. `GetMinMaxDamage @180f11cc0` (overload 2-arg @180f11da0) indexe
    les vars sur l'`AbilityStateFromEffect` (= le niveau de l'ability source sur l'unite, `ability_level`).
    minDmg/maxDmg in `variablesAffectedByRarityBonus` -> x multiplier. Les coups squig ont leur perce/profil
    propres et sont prev-threades APRES les coups d'arme (overkill continu) -> chemin `extra_groups` de
    `get_multi_hit_attack_prediction`. VALIDE live seed 500 (u87 orksRuntherd L50 mult200 :
    [minDmg50,maxDmg50]=[1330,1994]x2 = [2660,3988] par coup squig, count=2, profil Physical pierce 1)."""

    def additional_hit_groups(self, ctx: "Mapping | None" = None) -> "list[dict] | None":
        lvl = self.ability_level if self.ability_level is not None else self.level
        mn = ability_var("SquigHound", "minDmg", lvl, multiplier_pct=self.ability_variables_multiplier)
        mx = ability_var("SquigHound", "maxDmg", lvl, multiplier_pct=self.ability_variables_multiplier)
        count = ability_var("SquigHound", "nrOfHits", is_constant=True)  # numberConstant 0x2f
        if mn is None or mx is None or not count or count <= 0:
            return None
        try:
            import gameconfig as _GC
            profile = ((_GC.ability("SquigHound") or {}).get("constants") or {}).get("damageProfile") \
                or "Physical"
        except Exception:
            profile = "Physical"
        return [{"count": int(count), "min": int(mn), "max": int(mx), "profile": profile}]


class SmashaEadExtraDamageEffect(BaseEffect):
    """`SmashaEadEffect.CreateEffectDamageBonusForAttack @180f6bee0` (orksNob "Tanksmasha", ability
    SmashaEad, EffectType "SmashaEad") : `EffectBonus.ForAddition(OwnerIsCaster & IsNormalAttack,
    ConfigVar(8=extraDmg, EffectSource))` = +`extraDmg[level]` x multiplier au degat des attaques
    NORMALES du porteur — FLAT additif (PAS %, contrairement a RapidAssault).

    Placement (#69, natif LU) : `ForAddition` ecrit le champ DamageBonus (+5) de l'EffectBonus ->
    `DamageModifiers.Add @181005f10` fait `additif @+0x10 += FromInt(v)`, applique APRES percage/armure
    par `CalculateBaseDamageWithAllModifiers @18102d3f0` (meme canal `additive` que tout ForAddition).
    Il n'existe PAS de canal additif "de base" pre-percage dans le natif -> le kind "BaseAddition"
    invente a ete retire ; le `+66` observe post-percage etait confondu par l'aura #49 + BeastSlayer.

    Effet pose par `SmashaEadAbility.CreateTrigger @1811a0610` quand le porteur a traverse >=2 hexes
    ce tour (condition d'EFFECT-CREATION, deja bakee dans l'effet materialise ; le bonus s'applique
    tant que l'effet est actif -> pas de re-gate ici). `extraDmg` in variablesAffectedByRarityBonus ->
    scale par le multiplier de l'unite. i2 : "+437 Damage" (au niveau/mult affiche). ability ACTIVE ->
    indexe activeAbilityLevel. (L'effet porte AUSSI -dmgReductionPct au degat RECU via
    `CreateEffectDamageMalusForDefense @180f6c060` = cote DEFENSE, PORTE #119 ci-dessous.)"""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True) -> EffectBonus | None:
        # #71 : trigger natif = OwnerIsCaster & IsNormalAttack (@180f6bee0). Le noeud DSL IsNormalAttack
        # (= `IsRegularAttack(ability DECLENCHANTE)` @180f8d260/@181555b40, FALSE si pas d'ability dans le
        # contexte) evalue FALSE dans le contexte PREDICTION DISPLAY (verdict re-expert : additif absent de
        # decisionView ; off_sans ~= oracle) -> l'additif ne doit PAS entrer dans la DamageModifiers de
        # PREDICTION. En COMBAT (is_prediction=False) l'additif est applique.
        # ⚠ #68 (BUG MAGNITUDE = MULTIPLIER, RE close bit-exact) : le COMBAT live applique +300/coup exact
        # (round(extraDmg[L50]=333 x 90/100)) alors que ce port applique +599 (round(333 x 180/100)) -> SUR-
        # applique ~2x. Le niveau (50), la variable (extraDmg) et l'index (level-1) sont CORRECTS ; SEUL le
        # multiplier est faux : `self.ability_variables_multiplier=180` est le multiplier GLOBAL/primaire de
        # l'unite (UnitConfig+0x74), or la TRIGGERED SmashaEad a son PROPRE multiplier par-ability = 90
        # (`GetAbilityVariablesMultiplierPercentage(abilityId)@181696230` est PAR-ABILITY). Ce multiplier
        # par-ability des triggered n'est capte par AUCUN champ actuel -> fix FIDELE = nouveau capteur (tache
        # #75) ; presence CORRECTE. Test xfail test_getstuckin_combat_absolute_bit_exact -> xpass apres fix.
        if is_prediction:
            return None
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        amt = ability_var("SmashaEad", "extraDmg", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        # ForAddition -> canal `additive @+0x10` applique POST-percage (DamageModifiers.Add @181005f10).
        return for_addition(True, amt) if amt is not None else None

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        """`SmashaEadEffect.CreateEffectDamageMalusForDefense @180f6c060` (cote DEFENSE, #119) :
        `EffectBonus.ForPercentDecrease(OwnerIsTarget, ConfigVar 0x46=dmgReductionPct)` — l'effet REDUIT le
        degat RECU par son porteur de `dmgReductionPct`% (i2 « takes -33% Damage » tant que l'effet actif =
        le porteur a traverse >=2 hexes ; la CONDITION est deja bakee dans la materialisation de l'effet ->
        pas de re-gate ici). Gate natif = `OwnerIsTarget` SEUL (decompile @180f6c060) -> AUCUN gate
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
    """`FeederTendrils_ExtraDamageEffect.CreateEffectDamageBonusForAttack @180f48ea0` (Deathleaper,
    effet 0x4ad=1197 ; ctor @180f49050 = `ABondEffect(AbilityOrEffect 0x4ad)`). JUMEAU BIT-A-BIT de
    `SmashaEadExtraDamageEffect @180f6bee0` avec UN gate `IsCharging` en plus :
    `EffectBonus.ForAddition(OwnerIsCaster & IsNormalAttack & IsCharging, ConfigVar(8=extraDmg, EffectSource))`.

    - MAGNITUDE = `ability_var("FeederTendrils", "extraDmg", level) x multiplier` (`ConfigVar` var index 8 =
      `extraDmg`, seule var dmg de FeederTendrils, dans `variablesAffectedByRarityBonus` ; extraDmg[L1]=10,
      [L50]=554, [L65]=728 = le « +728 Damage » i2). Multiplier = le GLOBAL de l'unite (`self.ability_variables_
      multiplier`, UnitConfig+0x74), PAS le per-ability #68 : `FeederTendrils_NormalAttack` (1120) EST l'attaque
      NORMALE de l'unite (pas une triggered) -> le multiplier standard s'applique. Aucun scaling par AbilityState
      (`GetAbilityState @180f11780` ne sert qu'a indexer `level` dans `GetVariableForLevel`).
    - PLACEMENT = additif attaquant PRE-percage per-coup (canal `attacker_additive_pre`, MEME que SmashaEad #75 :
      `ForAddition` -> `DamageModifiers.Add @181005f10`, applique par bout dans `GetDamageWithPiercing`). RE-valide
      (reconciliation MIN exacte, u87 seed 42, A=554x1.8=997/coup) : u83/u81 delta=3x997=2991 EXACT ; u85 min=
      3x339=1017 ; u79 min=718~=717 (%-list 0.8). Les MAX u79/u85 qui s'ecartent = caps HP (deja geres par
      target_limits/overkill du port). Le delta VARIE par cible via le regime percage/armure par bout, PAS via
      des stacks.
    - GATE `IsCharging` (`AverageDistanceFormula @180f0c7e0` : l'unite s'est-elle rapprochee de la cible = a-t-elle
      charge) ET `get_IsMelee` (@1811dd850) -> l'additif n'est ACTIF qu'en attaque MELEE de CHARGE (deplacement au
      contact). En prediction-display les tuiles d'attaque rankees SONT des tuiles de charge -> gate TRUE (les 4
      samples portent l'additif). Contrairement a SmashaEad, PAS de `if is_prediction: return None` : ici
      IsNormalAttack=TRUE (c'est l'attaque normale de l'unite, incluse dans decisionView).
    ⚠ A confirmer live (validator, quand un slot runner se libere) : niveau/mult reels de u87 (infere L50/mult1.8) ;
    cas NEGATIF IsCharging (attaque sans deplacement -> additif doit DISPARAITRE) non teste par les 4 samples."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True) -> EffectBonus | None:
        if is_ranged:                       # IsCharging & get_IsMelee (@1811dd850) -> melee uniquement
            return None
        if is_normal_attack is False:       # IsNormalAttack (@180df4690)
            return None
        if has_moved is False:              # IsCharging (@180df3210) : charge = deplacement vers la cible
            return None                     # (has_moved None = inconnu -> applique, cas prediction-display)
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        amt = ability_var("FeederTendrils", "extraDmg", lvl,
                          multiplier_pct=self.ability_variables_multiplier)  # GLOBAL (pas per-ability #68)
        return for_addition(True, amt) if amt is not None else None


class DecoysAndMisdirectionExtraDamageEffect(BaseEffect):
    """`DecoysAndMisdirection_ExtraDamageEffect.CreateEffectDamageBonusForAttack @180f3e340` (Genestealer
    Cults ability DecoysAndMisdirection 0x518=1304, effet 0x563=1379 "DecoysAndMisdirection_ExtraDamage") :
    `EffectBonus.ForAddition(OwnerIsCaster, ConfigVar(8=extraDmg, EffectSource))` = +`extraDmg[level]` x
    multiplier au degat de TOUTES les attaques du porteur (l'ami buffe) -- FLAT additif, meme canal
    `additive @+0x10` que SmashaEad (DamageModifiers.Add @181005f10, applique POST-percage par
    CalculateBaseDamageWithAllModifiers @18102d3f0).

    Pose sur un ami quand un decoy est spawn a cote de lui / quand un ami se deplace sur un decoy (i2 :
    « it deals +582 Damage until the end of its turn »). ctor @180f3e4a0 : EffectSource = AbilityOrEffect
    0x518 (DecoysAndMisdirection) -> extraDmg indexe sur le niveau de CETTE ability du SOURCE (genesPrimus).

    DIFFERENCE cle vs SmashaEad (#71) : le gate natif est `get_OwnerIsCaster` SEUL (@180f3e340 decompile :
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
                                              is_normal_attack: bool | None = True) -> EffectBonus | None:
        # Gate natif = OwnerIsCaster SEUL (@180f3e340) : aucun re-gate is_ranged/is_normal/is_prediction.
        # Ce chemin n'est appele que pour les attaques du porteur -> OwnerIsCaster implicitement TRUE.
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        amt = ability_var("DecoysAndMisdirection", "extraDmg", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        # ForAddition -> canal `additive @+0x10` applique POST-percage (DamageModifiers.Add @181005f10).
        return for_addition(True, amt) if amt is not None else None


class AnvilShieldAdditionalBlockEffect(BaseEffect):
    """`AnvilShield_AdditionalBlock` (effet 0x4b2=1202, StaticStatModifierEffect) — buff BLOCK_DAMAGE
    self de Arjac (spaceRockfist) quand il BLOQUE. Pose par `AnvilShieldAbility_ApplyAdditionalBlockAnd
    BlockChance.CreateBehaviour @180e16340` : `AddStaticStatModifierEffect(0x4b2, statType 8=BLOCK_DAMAGE,
    GetVariableForLevel(0x14))` (2e effet de la meme behaviour = 0x4b0=1200 BlockChanceBelowHealthCap,
    stat 7=BLOCK_CHANCE / var blockChance, gate sante -> NON porte ici, ambiguite abs-vs-% du cap).

    Magnitude = ability_var AnvilShield `blockDmg` (idx enum 0x14 <-> stat 8 BLOCK_DAMAGE ; blockDmg in
    variablesAffectedByRarityBonus -> scale x multiplier de l'unite). blockDmg[L1..65]=[10..728]. Effet
    INCONDITIONNEL (pas d'ActiveCondition). AnvilShield = ability ACTIVE -> index activeAbilityLevel
    (fallback passif/stack). EffectSource = AbilityOrEffect 0x493 (=AnvilShield, ability enum).

    ⚠ Pose par le vecteur ON-BLOCK (materialisation d'effet on-block, NON porte) -> INERTE tant que non
    materialise (fidelite-safe : « present != applique ») ; une fois present sur Arjac (seed live / vecteur),
    le stat-layer applique +blockDmg a la stat BLOCK_DAMAGE (stat 8, lue par CalculateBlockChances #30).
    Validation live possible via un scenario BLOCK (Arjac bloque -> statModSources stat 8), cf. BeastSlayer #72."""

    def get_stat_modification_stat(self) -> int | None:
        return 8                                     # StatType.BLOCK_DAMAGE

    def get_stat_modification_amount(self) -> int | None:
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        return ability_var("AnvilShield", "blockDmg", lvl,
                           multiplier_pct=self.ability_variables_multiplier)


class ContaminatedUnitEffect(BaseEffect):
    """`Contaminated_Unit` (effet 0x4dd=1245, `ContaminatedStatModifierEffect`, ctor @180f3a560 =
    ADynamicStatModifierEffect FixedArmor) — SOUS-effet pose sur une UNITE occupant/entrant une tuile
    `Contaminated` (0x4dc), 1 round. Debuff dynamique de la stat FixedArmor (=16).

    Le NATIF calcule le montant a l'apply (`ADynamicStatModifierEffect.GetStatModificationAmount @180f090f0`
    -> `GetDynamicStatModificationAmount @180f3a460` = -X% du FixedArmor courant) et l'applique via ChangeStat.
    Cote port : le vecteur tile-effect (#128, `ContaminatedTileEffect`) calcule le delta a l'apply et le stocke
    dans `self.value` -> `get_stat_modification_amount` renvoie `self.value`.

    >>> MAGNITUDE (#132 RESOLUE 2026-07-14, RE re-expert decompile) : `GetDynamicStatModificationAmount
    @180f3a460` = `-BattleQuery.GetEffectConfig(EffectType=6)` (interface IBattleQuery slot 0xbe, arg 6 =
    EffectType litteral). `BattleQuery.GetEffectConfig @1810610b0` = lookup `Dict<EffectType,int>@+0xd0`
    peuple par `InitEffectConfig @18106e9c0` depuis `BattleConfiguration.Effect` ; l'entree EffectType=6
    (offset +0x28) = **`ContaminatedArmorReductionPct` = 30**. => -30 % du FixedArmor cible. Source = section
    `Effect` de la BC (lue, PAS hardcodee) ; le vecteur `ContaminatedTileEffect` pre-calcule le DELTA PLAT
    `value = -round(FixedArmor * 30/100)` a la pose (le stat-layer l'applique en additif). ⚠ MODE % infere
    du nom `...Pct` + magnitude (le -30 flat serait negligeable) ; le modKind exact du chemin ChangeStat
    partage (flat vs percent) et le %-de-base-vs-courant restent a CONFIRMER live (drop d'armure via
    statModSources sur un occupant contamine)."""

    def get_stat_modification_stat(self) -> int | None:
        return 16                                    # StatType.FIXED_ARMOR

    def get_stat_modification_amount(self) -> int | None:
        # Delta calcule a l'apply par le vecteur (= -round(FixedArmor_courant * X/100)) et stocke dans value.
        # None tant que X non resolu (#132) -> aucune contribution stat (mais l'effet reste PRESENT).
        return self.value


class RitesOfBattleExtraDmgEffect(BaseEffect):
    """`RitesOfBattleExtraDmgEffect` (Effects.Loki) — AURA stat-mod +dégât de Calgar (2 EffectTypes
    permanents sur le porteur : Basic `...ExtraDmgBasic` 1002 / Imperial `...ExtraDmgImperial` 1003).
    `RitesOfBattleAbility.CreateBehaviour @181225340` → 2 `DynamicStatModifierEffect` sur le SOURCE ;
    `CreateTargetSelector` = `AdjacentUnits(1) @180de8320` (source EXCLUE) → `Friends @180df0040` →
    `With/WithoutTrait(0x1a=26)` (26 = grande-alliance Imperial, `GrandAlliance.GetTrait @1815647a0`).
    Montant `GetDynamicStatModificationAmount` = `GetVariableForLevel(idx8→extraDmg | idx9→extraDmg_2,
    niveau SOURCE)` × multiplier SOURCE (les 2 vars dans `variablesAffectedByRarityBonus`) ; ajouté à la
    **modification** du stat **Attack**. RE-validé : `extraDmg_2[L50]×1.8 = 1298` (Imperial, u92 adjacent
    à Calgar) ; `extraDmg[L50]×1.8 = 898` (basic).

    ⚠ Modélisée UNIQUEMENT côté SOURCE via `create_aura_attack_bonus` (l'effet-entité vit sur le PORTEUR,
    pas sur le buffé → PAS de `get_stat_modification_*` target-side : le porteur ne se self-buff pas,
    AdjacentUnits l'exclut). La sélection Basic/Imperial + le montant sont ré-évalués PAR CANDIDAT."""

    def create_aura_attack_bonus(self, ctx: Mapping | None = None) -> int | None:
        """AURA `RitesOfBattleAbility` @181225340 (2 effets permanents sur Calgar : Basic 1002 / Imperial
        1003) : +extraDmg/_2 au DÉGÂT DE BASE des ALLIÉS ring-1 du porteur, gate grande-alliance Imperial.
        `AdjacentUnits(1) @180de8320` (source EXCLUE) → `Friends @180df0040` (même équipe) →
        `With/WithoutTrait(0x1a=26)`. Montant = `GetVariableForLevel(var, niveau SOURCE) × multiplier SOURCE`
        (RE-validé : `extraDmg_2[L50]×1.8 = 1298`, `extraDmg[L50]×1.8 = 898`). Modélisé CÔTÉ SOURCE
        (l'effet-entité vit sur Calgar, pas sur le buffé) et ré-évalué PAR CANDIDAT (adjacence à `att_pos`)."""
        c = ctx or {}
        if c.get("owner_id") == c.get("att_id"):
            return None                                  # AdjacentUnits exclut la source (op_Subtraction self)
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                  # Friends = même équipe que le porteur
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        import hexgeo
        if hexgeo.distance(op, ap) != 1:                 # AdjacentUnits(range 1) — pure adjacence HEX
            return None
        # Gate trait 0x1a=26 = grande-alliance Imperial (GrandAlliance.GetTrait @1815647a0 : Imperial→26).
        # ABSENT de gameconfig.traits → dérivé de GrandAllianceId. Les 2 effets sont MUTUELLEMENT EXCLUSIFS
        # ("instead") : Basic→WithoutTrait(26) (non-Imperial), Imperial→WithTrait(26).
        target_imperial = (c.get("att_grand_alliance") == "Imperial")
        effect_imperial = bool(self.name and self.name.endswith("Imperial"))
        if effect_imperial != target_imperial:
            return None
        var = "extraDmg_2" if effect_imperial else "extraDmg"
        return ability_var("RitesOfBattle", var, c.get("owner_level"),
                           multiplier_pct=c.get("owner_mult") or 100)


class PathOfCommandExtraDmgEffect(BaseEffect):
    """`PathOfCommandExtraDmgEffect` (Effects.Triggered.Loki) — AURA stat-mod +Attack de Loki
    (`PathOfCommand_ExtraDmg` 1112). `PathOfCommandAbility.CreateBehaviour @181110f10` pose 2 effets
    DynamicStatModifier sur le SOURCE (Loki) : ExtraDmg (0x458=1112) + ExtraCrit (0x453=1107).
    `CreateTargetSelector @180f4bf30` = `SurroundingFriends(owner, range=GetNumberConstant(0x16)=2)` =
    `SurroundingTiles(range) - Tiles(self)` → `Friends` → alliés (même équipe) à distance hex <=2, SOURCE
    EXCLUE (comme RitesOfBattle mais range 2 au lieu de 1).

    Montant `GetDynamicStatModificationAmount @18119c7b0` = `If(IsSameFaction(owner, target), v8+v9, v8)`
    avec `v8 = GetVariableForLevel(8=extraDmg, niveau SOURCE)`, `v9 = (9=extraDmg_2, niveau SOURCE)` (mêmes
    enum-keys 8/9 = extraDmg/extraDmg_2 que RitesOfBattle) × multiplier SOURCE (les 2 dans
    `variablesAffectedByRarityBonus`). `IsSameFaction` = **même FACTION** (FactionId, ex. Aeldari), PAS la
    grande-alliance : `IsSameFaction` s'appuie sur `UnitExtensions.HasFaction @180ed6450` (compare le champ
    FactionId string). CONFIRMÉ RE + LIVE (discriminateur : allié Aeldari adjacent = extraDmg+extraDmg_2=+699 ;
    allié Ork = Xenos MAIS pas Aeldari = extraDmg SEUL=+400). → allié même faction → extraDmg+extraDmg_2 ; autre
    faction (même Xenos) → extraDmg seul. (⚠ DIFFÉRENT de RitesOfBattle dont le gate extraDmg_2 = grande-alliance
    Imperial via trait 26.) Ajouté à la **modification** du stat **Attack**.

    ⚠ Modélisée CÔTÉ SOURCE via `create_aura_attack_bonus` (l'effet-entité vit sur Loki, pas sur le buffé) et
    ré-évaluée PAR CANDIDAT (distance <=2 à `att_pos`). PAS de `get_stat_modification_*` target-side (Loki ne
    se self-buff pas : SurroundingFriends l'exclut). L'axe CRIT (ExtraCrit 1107 = extraCritChance) = effet
    SÉPARÉ non porté ici (nécessite un canal aura-crit dédié — TODO)."""

    def create_aura_attack_bonus(self, ctx: Mapping | None = None) -> int | None:
        c = ctx or {}
        if c.get("owner_id") == c.get("att_id"):
            return None                                  # SurroundingFriends exclut la source (- Tiles(self))
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                  # Friends = même équipe que le porteur (Loki)
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        import hexgeo
        rng = ability_var("PathOfCommand", "range", is_constant=True) or 2   # GetNumberConstant(0x16)=range=2
        if hexgeo.distance(op, ap) > rng:                # SurroundingFriends(range) — portée hex du porteur
            return None
        lvl, mult = c.get("owner_level"), (c.get("owner_mult") or 100)
        base = ability_var("PathOfCommand", "extraDmg", lvl, multiplier_pct=mult) or 0
        # If(IsSameFaction(owner, target), extraDmg + extraDmg_2, extraDmg) — IsSameFaction = même FACTION
        # (FactionId, cf. HasFaction @180ed6450), PAS grande-alliance. Confirmé live (Ork Xenos = extraDmg seul).
        ofac, afac = c.get("owner_faction"), c.get("att_faction")
        if ofac is not None and ofac == afac:
            base += ability_var("PathOfCommand", "extraDmg_2", lvl, multiplier_pct=mult) or 0
        return base or None


class StandVigilExtraArmorEffect(BaseEffect):
    """`StandVigil_ExtraArmorEffect` (Effects.Loki) — buff **StatModification** +armure, **SELF-buff**
    (l'unité se buffe elle-même en « stand vigil » = sans se déplacer). `GetDynamicStatModificationAmount
    @180f6d910` = `ConfigVar(key 0x51c=1308, EffectSource, 0x1b)` = ability var
    `StandVigil.extraArmor[level]` (FLAT), ajouté à la **modification** du stat **FixedArmor** (=16) via
    `ChangeStat` (part 5/9 ; revert part 6).

    **Self-buff** ⇒ la source EST l'unité porteuse → `level` = niveau de l'ability StandVigil de l'unité
    elle-même (`self.ability_level` capté depuis unitConfig, sinon `self.level`) → magnitude EXACTE
    offline ⇒ **résidu 0 validable live** (contrairement à RitesOfBattle, buff cross-unité)."""

    def get_stat_modification_stat(self) -> int | None:
        return 16                                   # StatType.FIXED_ARMOR

    def get_stat_modification_amount(self) -> int | None:
        # StandVigil = ability ACTIVE → indexer sur activeAbilityLevel (fallback passif, puis stack level).
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        return ability_var("StandVigil", "extraArmor", lvl)


class CrushingStrikeEffect(BaseEffect):
    """`CrushingStrikeEffect` (Effects.Loki, effet 0x4a2=1186 ; ctor @180f3af20, base
    `ADamageDefenseModifierAbilityEffect`).
    - dégât `CreateDamageModifier` @180f3ad90 : `ForPercentIncrease(OwnerIsCaster & IsNormalAttack &
      IsMeleeAttack, ConfigConst key 0xf)` = trait var `crushingStrikeExtraDmgPct` (=50, constante
      plate via `AbilityConfiguration.GetNumberConstant` — cf. `ConfigAmount.Calculate @180f171c0` —
      NON rarity-scalée).
    - condition d'activité `CreateActiveCondition` @180f3ad50 : NOT HasFlag(HasMoved) (« if it has
      not moved this turn ») — en PRÉDICTION la tuile candidate fixe le flag (`has_moved`), en COMBAT
      `state.moved_this_turn` (#60).
    VALIDÉ live #98 (darkaTerminator u80→u78 seed777 roster1) : préd depuis (6,6) not-moved elev2>1
    = ×2.25 = CrushingStrike(×1.5) × ÉlévationBonus(×1.5) [composition %-list multiplicative] ;
    depuis les tuiles déplacées (elev égale) = ×1.0 EXACT (5307,7959)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True) -> EffectBonus | None:
        if is_ranged:                            # gated IsMeleeAttack (@180f3ad90)
            return None
        if is_normal_attack is False:            # gated IsNormalAttack (spéciale mêlée → pas de bonus)
            return None
        if has_moved:                            # ActiveCondition NOT HasFlag(HasMoved) (@180f3ad50)
            return None
        pct = trait_var("CrushingStrike", "crushingStrikeExtraDmgPct")
        return for_percent_increase(True, pct) if pct is not None else None


class HeavyWeaponExtraDmgEffect(BaseEffect):
    """`HeavyWeapon_ExtraDmgEffect` (effet 1008 ; ctor `DamageModifierAbilityEffect(0x3e9)`).
    - dégât `CreateDamageModifier` @180f4f030 : `EffectBonus.ForPercentIncrease(cond, amount)` où
      `amount = ConditionalAmount(TriggeringAbilityIs(0x3ec) ? amount×2 : amount)`, `amount = ConfigConst
      key 0xf` = trait var `heavyWeaponExtraDmg` (=25, scalaire) ; condition = `OwnerIsCaster &
      IsRangedAttack & flags`. ⇒ **+25% de dégât sur les attaques RANGED** (le ×2 si l'ability
      déclenchante est 0x3ec = raffinement non porté ; l'attaque normale/overwatch n'est pas 0x3ec).
    Porté par le trait HeavyWeapon (qui accorde aussi l'Overwatch) → s'applique au tir d'overwatch."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True) -> EffectBonus | None:
        if not is_ranged:                        # gated IsRangedAttack (no-op sur mêlée / contexte inconnu)
            return None
        # Gate NO-MOVE (`!HasFlag(HasMoved=0)` @180f4f030 ; i2 : « When this unit has not moved this
        # turn »). En PRÉDICTION la tuile candidate fixe le flag : has_moved=True (candidat avec
        # déplacement) → pas de bonus (GROUND TRUTH step-23 : rangées ranged u78 SANS ×1.25 depuis les
        # tuiles déplacées ; step-11 : « ×1.25 selon tuile »). En COMBAT (#60) l'état est DÉSORMAIS tracé
        # (`state.moved_this_turn` -> `attacker_modifiers` passe un bool défini) : le bonus s'annule si
        # l'unité a bougé ce tour. None (contexte hors combat/prédiction) → bonus appliqué (fallback).
        if has_moved:
            return None
        pct = trait_var("HeavyWeapon", "heavyWeaponExtraDmg")
        return for_percent_increase(True, pct) if pct is not None else None


class RangedSpecialistEffect(BaseEffect):
    """`RangedSpecialistEffect` (trait RangedSpecialist — i2 : « If this unit did not start its turn
    adjacent to an enemy unit, it deals +33% Damage with ranged attacks »).
    - dégât @180f67520 : `EffectBonus.ForPercentIncrease((OwnerIsCaster & IsRangedAttack &
      !TriggeringAbilityIs(0x434)) | (branche 0x434 overwatch), Get(ConfigConst 0xf))` =
      **+rangedSpecialistDmgPct% sur les attaques RANGED** (toutes tuiles — la condition « pas parti
      adjacent » est l'état ACTIF de l'effet, reflété par la capture isActive, PAS un gate de tuile).
    MAGNITUDE : `traitVariables.rangedSpecialistDmgPct` = 33. GROUND TRUTH step-8 seed777 :
    u80→u94 ranged natif = moteur ×1.33 exact (per-coup 534 = round(401×1.33)), mêlée intacte."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True) -> EffectBonus | None:
        if not is_ranged:                        # gated IsRangedAttack (@180f67520)
            return None
        pct = trait_var("RangedSpecialist", "rangedSpecialistDmgPct")
        return for_percent_increase(True, pct) if pct is not None else None


# Traits cible gatant BeastSlayer_ExtraDmg (natif `HasTrait(target, X)`) : UnitTrait.BigTarget=1017(0x3f9),
# UnitTrait.Vehicle=1029(0x405) (dump.cs #146 ; l'ancien commentaire INVERSAIT les hex). Code gate par NOM,
# noms gameconfig confirmes (unit_map find --trait BigTarget/Vehicle).
_BEAST_SLAYER_TARGET_TRAITS = frozenset({"BigTarget", "Vehicle"})


class BeastSlayerExtraDmgEffect(BaseEffect):
    """`BeastSlayer_ExtraDmgEffect.CreateDamageModifier @180f336c0` (trait BeastSlayer, effet
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
                                              is_normal_attack: bool | None = True) -> EffectBonus | None:
        if is_ranged:                                  # IsMeleeAttack -> melee uniquement
            return None
        if not target_traits or _BEAST_SLAYER_TARGET_TRAITS.isdisjoint(target_traits):
            return None                                # cible ni BigTarget ni Vehicle -> 0
        pct = trait_var("BeastSlayer", "beastSlayerExtraDmgPct")
        return for_percent_increase(True, pct) if pct is not None else None


class BeastSlayerExtraBlockEffect(BaseEffect):
    """`BeastSlayerAbility.CreateAddBlockEffectBehaviour @180e18b70` (trait BeastSlayer, effet
    `BeastSlayer_ExtraBlock`, cote DEFENSE) : `AddExtraBlockEffectToOwner(chance, amount)` avec
    chance=`GetBlockChance @180e19120`=`GetNumberConstant(0x2d=beastSlayerBlockChance)` (=10) et
    amount=`GetBlockDamage @180e19160`=`PercentageOf(StatAmount(0x10=FixedArmor),
    GetNumberConstant(0x36=beastSlayerBlockAsMaxArmorPct))` (=100% du FixedArmor COURANT).
    => source de BLOCK SUPPLEMENTAIRE (roll separe : +10% chance de bloquer 100% de l'armure courante
    en degat), ABSENTE du scalaire GetStat(7/8) (verifie LIVE 2026-07-09 : orksNob blockChance=0). Le
    natif la tient dans `GetMultiValueStat(7)`. Variables de TRAIT -> globales, NON scalees par le mult.
    Cf. docs/rl/case-68-orksnob-attacker-effects.md (#72)."""

    def create_effect_block_source_for_defense(self, defender_fixed_armor: int = 0):
        chance = trait_var("BeastSlayer", "beastSlayerBlockChance")
        pct = trait_var("BeastSlayer", "beastSlayerBlockAsMaxArmorPct")
        if not chance or pct is None:
            return None
        amount = int(int(defender_fixed_armor) * int(pct) / 100)   # PercentageOf(FixedArmor, blockDmgPct)
        if amount <= 0:
            return None
        # block_id = la chance (id natif dans failedList @181002350) : une source EXCLUE apres son 1er
        # echec sur un coup (exclusion inter-coups, cf. AttackDamageOperation._run_hits #72).
        return BlockSource(chance=int(chance), amount=amount, block_id=int(chance))


class TerrifyingExtraDefenseEffect(BaseEffect):
    """`Terrifying_ExtraDefense_Effect.CreateDamageModifier` @180f47ba0 : réduit le dégât MÊLÉE reçu par
    son PORTEUR (l'effet est sur la CIBLE). Trigger natif = `OwnerIsTarget & IsMeleeAttack` (AbilityOrEffect
    0x62) ; valeur = `ConfigConst(0x28)`. La valeur n'est PAS exposée par gameconfig (trait/effet Terrifying
    = variables vides) ; magnitude **30 confirmée LIVE** (scorer ×0.70 sur eldarMauganRa, seed777 step22).
    ⇒ malus défenseur `PercentDecrease(30)` gated `IsMeleeAttack` (no-op sur attaque ranged / contexte inconnu)."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if not is_melee:                         # gated IsMeleeAttack
            return None
        return for_percent_decrease(False, 30)   # owner_is_caster=False (l'effet est sur le défenseur)


class MartialKatahDmgReductionEffect(BaseEffect):
    """`MartialKatah_DmgReductionEffect.CreateDamageModifier @180f58b30` (trait MartialKatah, Custodes
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
    """`TerminatorArmour_ReduceDmg_Effect.CreateEffectDamageMalusForDefense` @180f70f80 : réduit de
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
    """`GuardianOrganism_DamageReductionEffect.CreateEffectDamageMalusForDefense @180f4c630` (trait
    GuardianOrganism, tanks Tyranides ex. tyranTyrantGuard) : réduit le dégât REÇU par son porteur de
    `min(dmgReductionPct% × CurrentDamage, dmgReduction[cap] × mult)` — `EffectBonus.ForSubtraction(
    OwnerIsTarget, Min(PercentageOf(CurrentDamage, ConfigVar(0x46)), ConfigVar(0x12)))`. Réduction
    DYNAMIQUE (fraction du dégât courant) + CAPÉE absolue -> kind `PercentSubtractionCapped` (≠ un simple
    PercentDecrease : le cap plafonne le MONTANT soustrait, pas le %).
      - pct = ConfigVar(0x46) = `dmgReductionPct` [25..33 par niveau, NON rarity-scaled].
      - cap = ConfigVar(0x12) = `dmgReduction` [20..1455, rarity-scaled × mult].
    AURA (`CreateTargetSelector @180f4c890` = Self + `AdjacentFriends(range 1)`) : l'effet se MATÉRIALISE
    sur chaque bénéficiaire (self + amis ring-1) -> capté dans SA liste (source = le porteur GuardianOrganism).
    Côté port l'effet est DÉJÀ sur le défenseur (comme Terrifying/Terminator) : `self.ability_level`/
    `self.ability_variables_multiplier` = ceux du porteur = le DÉFENSEUR (EffectsState.seed les propage) ->
    niveau/mult CORRECTS sans threading. Aucun gate profil/mêlée/attaquant (OwnerIsTarget seul).
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
    """`Nightshroud_DmgReduction_Effect.CreateDamageDefenseModifier @180f5bff0` (ability Nightshroud de
    Sibyll Devine `astraPrimarisPsy`, base `ADamageDefenseModifierAbilityEffect(0x416)` = ctor @180f5c190) :
    réduit d'un montant PLAT le dégât REÇU par son porteur — `EffectBonus.ForSubtraction(OwnerIsTarget,
    ConfigVar(0x12)=dmgReduction × mult)`. i2 : « All friendly units starting their turn adjacent to Sibyll
    Devine gain Infiltrate for that turn and take -{dmgReduction} Damage from each hit in their and the next
    enemy turn. » (le grant Infiltrate + la durée their+next-enemy-turn = cycle de vie de l'effet ; le
    ForSubtraction est le SEUL terme de dégât).
      - montant = ConfigVar(0x12) = `dmgReduction` [5..364 par niveau, RARITY-SCALÉ : dmgReduction ∈
        variablesAffectedByRarityBonus] × `mult` (= `*(effet+0x60)`) = niveau/mult du porteur = le DÉFENSEUR
        (EffectsState.seed les propage sur chaque allié ring-1 de Sibyll, comme l'AURA GuardianOrganism #89).
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


class NeuroparasiteEffect(BaseEffect):
    """`NeuroparasiteEffect.CreateEffectDamageMalusForDefense @180f5b840` (passif du Neurothrope
    `Neuroparasite`, EffectType 0x49f=1183, base `ABondEffect` = lien cible<->Neurothrope infecteur).
    Malgré le nom « MalusForDefense », c'est un ADDITIF **POSITIF** au dégât PSYCHIQUE reçu (le porteur =
    une faiblesse infligée) :
      `EffectBonus.ForAddition(OwnerIsTarget & AreEqual(BondedEntity, damageSource) & DamageProfileIs(0xd),
                               Multiply(ConfigVar(8=extraDmg, sourceAbilityState), EffectLevel))`
    = **+extraDmg[niveauSource] × niveau_de_parasite** au dégât psychique de LE Neurothrope qui a infecté la
    cible. i2 : « Psychic Damage dealt by the Neurothrope is increased by +1237 Damage for each level of a
    Neuroparasite on the target » (`extraDmg[L65]=1237` ; max 15 niveaux via `GetMaximumLevel @180f5bdc0`).

    Gates natifs (@180f5b840) :
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
    non mesuré). Combat : parasite non matérialisé par le runner -> def additive=0 -> inerte."""

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
    - dégât @180f493a0 : `EffectBonus.ForAddition(OwnerIsCaster, Multiply(ConfigVar(0x12=dmgReduction),
      MinusOne))` = **-dmgReduction PLAT** sur les attaques du PORTEUR (additif, PAS un pct).
      `dmgReduction` = variable par niveau (lvl65=582), flaggée `variablesAffectedByRarityBonus`.
    ⚠ Niveau/multiplier fidèles = ceux du CASTER SOURCE (Darkstrider, abilityState de l'effet), non
      captés pour un debuff d'origine ennemie → fallback niveau/multiplier du PORTEUR (approximation
      documentée ; identique en pratique sur rosters au même palier)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True) -> EffectBonus | None:
        lvl = self.ability_level if self.ability_level is not None else self.level
        v = ability_var("FightingRetreat", "dmgReduction", lvl,
                        multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, -int(v)) if v else None


class FightingRetreatHitReductionEffect(BaseEffect):
    """`FightingRetreat_HitReductionEffect` (effet 1158 `FightingRetreatHitReduction`) — même debuff,
    axe COUPS (« They also have 1 fewer hits, to a minimum of one »).
    - hits @180f495d0 : `EffectBonus.ForAdditionWithMinimum(OwnerIsCaster, Multiply(MinusOne,
      ConfigConst(0x2c=hitsReduction=1)), min=Direct(1))` = **-1 coup, PLANCHER 1**. Le plancher est
      appliqué chez les consommateurs de hits (`max(1, …)`, cf. predict_validate)."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True) -> EffectBonus | None:
        # trigger natif = OwnerIsCaster SEUL (@180f495d0, pas de IsNormalAttack) -> TOUTES les attaques.
        n = ability_var("FightingRetreat", "hitsReduction", is_constant=True)   # ConfigConst 0x2c (=1)
        return for_addition(True, -int(n)) if n else None


# TileId (terrain BC) qui HÉBERGE la LightCoverAbility (Abilities.Tiles.Loki @1811c14e0) : les tuiles de
# couverture = DryBush. Source : empirique live (gqfc5mff6c) — une unité posée sur une tuile DryBush porte
# l'effet 'LightCover', absente ailleurs ; + `UnitsThatNeedEffect @1811c1830` = Units(coverPatch@0x148) =
# unités SUR la tuile porteuse de l'ability. Utilisé par le COMBAT pour le gate `AreEqual(coverPatch, target)`
# (@180f556b0) = "la cible est sur SA tuile de cover". Pas un hardcode de debug : mapping terrain->ability.
LIGHT_COVER_TILE_ID = "DryBush"


class LightCoverEffect(BaseEffect):
    """`LightCoverEffect` — couverture légère (effet de TUILE posé par `LightCoverAbility`
    Abilities.Tiles.Loki, `UnitsThatNeedEffect` @1811c1830 = unités SUR les tuiles de couverture).
    - hits @180f556b0 : `EffectBonus.ForAdditionWithMinimum(OwnerIsTarget(tuiles égales) &
      !IsMeleeAttack, -ConfigConst(0x2c=hitsReduction), min=Direct(1))` = **-hitsReduction coups
      sur les attaques NON-mêlée reçues par le porteur, plancher 1**. Le trigger `OwnerIsTarget(tuiles
      égales)` = `AreEqual(Tiles(coverPatch@0x148), Tiles(target@0x178))` = **la cible se tient sur LA
      tuile de cover** à laquelle l'effet est lié (approx. fidèle du port : la cible est sur UNE tuile
      DryBush, cf. `defender_on_cover`).
    MAGNITUDE : `globalValues.lightCoverHitReduction` = 2 (LightCoverAbility = ability de TUILE,
    absente de `units.abilities` — sa config vit dans les valeurs globales).
    GROUND TRUTH step-13 seed777 (trace AllMods, u90→u84 porteur LightCover) : ranged 4→2 coups
    partout, mêlée dist 1 → 4 coups (gate !IsMeleeAttack) — natif dMin/dMax reproduits exacts.

    ⚠ GATE compute-time `defender_on_cover` (A3, #113) : le natif RE-vérifie `AreEqual(coverPatch, target)`
    À CHAQUE calcul d'attaque — l'effet ne réduit PAS si la cible a quitté la tuile de cover. En PRÉDICTION
    (single-step, cible immobile) la présence de l'effet (IsActive live) ⟺ sur-cover → gate no-op (on passe
    `defender_on_cover=None` = "inconnu" → applique sur présence). En RUNNER-SIM (multi-step) l'effet peut
    PERSISTER après un move hors-cover (tant que B1 ne le retire pas) → le COMBAT passe
    `defender_on_cover = (terrain de la cible == DryBush)` pour ne PAS sur-appliquer un effet périmé."""

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None,
                                             defender_on_cover: bool | None = None) -> EffectBonus | None:
        if is_melee:                        # trigger natif = !IsMeleeAttack (@180f556b0)
            return None
        if defender_on_cover is False:      # AreEqual(coverPatch, target) FAUX : cible hors tuile de cover
            return None                     # (None = inconnu -> on applique sur présence, cas prédiction)
        n = global_value("lightCoverHitReduction")   # miroir du ConfigConst 0x2c (=2)
        return for_addition(True, -int(n)) if n else None


class ParryEffect(BaseEffect):
    """`ParryEffect` (effet `Parry_ReduceHits`, trait Parry — i2 : « reduces incoming melee multi-hit
    attacks by 1 hit, to a minimum of 1 »).
    - hits @180f5d860 : `EffectBonus.ForAdditionWithMinimum(OwnerIsTarget & IsMeleeAttack,
      -ConfigConst(0x2c=hitsReduction), min=Direct(1))` = **-1 coup MÊLÉE reçu, plancher 1**
      (jumeau mêlée de LightCover). MAGNITUDE : `traitVariables.parryHitReduction` = 1.
    GROUND TRUTH step-6 seed777 (trace AllMods, u86→u94 porteur Parry) : mêlée dist 1 = 4 coups
    vs ranged = 5 (base 3 + PowerTrip 1 + MasterAnnihilator 1) — natif reproduit exact."""

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None,
                                             defender_on_cover: bool | None = None) -> EffectBonus | None:
        if not is_melee:                    # trigger natif = IsMeleeAttack (@180f5d860)
            return None
        n = trait_var("Parry", "parryHitReduction")  # miroir du ConfigConst 0x2c (=1)
        return for_addition(True, -int(n)) if n else None


class MasterAnnihilatorAdditionalHitEffect(BaseEffect):
    """`MasterAnnihilator_AdditionalHitEffect` (effet `MasterAnnihilator_extraHit` — DEBUFF posé par
    Vitruvius sur SA cible d'attaque normale ; i2 : « Attacks by any friendly unit against the
    affected enemy score an additional hit, except attacks that deal Psychic Damage »).
    - hits @180f58d50 : `EffectAdditionalHits.Create(OwnerIsTarget & !AreEqual(
      CurrentAttackDamageProfile, 0xd=Psychic), count=ConfigConst(0x2f nrOfHits=1),
      dmg=FirstHitInCurrentAttackDamageRange capé ConfigVar(0xd maxDmg))` = **+1 coup reçu par le
      porteur (attaques non-Psychic)**. Les attaquants = ennemis du porteur = alliés du poseur (le
      gate « friendly unit » de l'i2 est structurel, pas dans le trigger).
    ⚠ CAP du coup bonus (dmg <= maxDmg[lvl] ex. 5456) non modélisé (per-coup observé << cap) — TODO.
    GROUND TRUTH step-6 seed777 : u86→u94 ranged = 5 coups (3 arme + 1 PowerTrip + 1 MA) vs 4 sur
    les cibles non marquées (88/96)."""

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None,
                                             defender_on_cover: bool | None = None) -> EffectBonus | None:
        if damage_profile == "Psychic":     # !AreEqual(profil, 0xd=Psychic) (@180f58d50)
            return None
        n = ability_var("MasterAnnihilator", "nrOfHits", is_constant=True)   # ConfigConst 0x2f (=1)
        return for_addition(True, int(n)) if n else None


class BigTargetAdjacentEffect(BaseEffect):
    """`BigTargetAdjacentEffect` — AURA du trait BigTarget (i2 : « Adjacent friendly units receive
    -1 hit from ranged attacks, to a minimum of 1 »). L'effet est POSSÉDÉ par le porteur BigTarget
    (capté dans SA liste d'effets) ; ses bénéficiaires = les ALLIÉS ring-1 HEX désignés dynamiquement
    (TargetSelector @180f33c70, refresh @180f33ce0) — PAS le porteur lui-même (GROUND TRUTH step-13
    seed777 : u86 porteur = 4 coups pleins ; u80 allié adjacent = 3 coups).
    - hits @180f33ac0 : `ForAdditionWithMinimum(OwnerIsTarget & IsRangedAttack, Direct(-1),
      min=Direct(1))` — valeur -1 codée dans le natif (pas de config).
    Canal AURA (le porteur n'est pas la cible de l'attaque) : ctx fourni par l'agrégateur
    `aura_hits_malus_for_defense` = {owner_id/pos/team, tgt_id, t_pos, tgt_team, is_melee}."""

    def create_aura_hits_malus_for_defense(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if c.get("is_melee") or c.get("owner_id") == c.get("tgt_id"):
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("tgt_team"):
            return None                     # bénéficiaires = alliés du porteur uniquement
        op, tp = c.get("owner_pos"), c.get("t_pos")
        if not op or not tp:
            return None
        import hexgeo                       # ring-1 HEX (parité validée vs boardGraph)
        if hexgeo.distance(op, tp) != 1:
            return None
        return for_addition(True, -1)       # Direct(-1) @180f33ac0


class AstartesBannerExtraHitEffect(BaseEffect):
    """`AstartesBanner_AdditionalHitsEffect` (effet capté "AstartesBanner_ExtraHit", passif AstartesBanner
    ex. templAncient) — AURA +coups : les ALLIÉS dans le rayon 2 du porteur marquent +extraHits coups avec
    leurs attaques MÊLÉE (i2 : « Other friendly units within 2 hexes score an additional hit with their melee
    attacks. This additional hit can deal a maximum of 5456 Damage »). L'effet est POSSÉDÉ par le PORTEUR
    (capté dans SA liste d'effets, comme BigTarget) ; bénéficiaires = SurroundingFriends (exclut self).
    - hits `CreateAdditionalHits @180f323b0` : `ForAddition(OwnerIsCaster & IsMeleeAttack, ConfigVar(0xd=
      extraHits, sourceAbilityState))` + cap dégât 5456 sur le coup ajouté (FirstHitInCurrentAttackDamageRange
      + max). ⚠ CAP 5456 du coup ajouté NON porté (refine : ne mord que si dégât/coup > 5456 ; le +1 coup
      COUNT est l'effet principal, GROUND TRUTH ultraApothecary 1->2 @seed999 via AstartesBanner de templAncient).
    - cible `CreateTargetSelector @180f325f0` : `SurroundingFriends(range=ConfigConst 0x16=2, exclut self)`.
    Canal AURA côté SOURCE (`create_aura_hits_bonus_for_attack`, agrégé par `aura_hits_bonus_for_attack`),
    SYMÉTRIQUE de BigTarget (défenseur). Magnitude `extraHits` indexée sur le niveau d'ability du PORTEUR
    (`GetAbilityState` -> `self.ability_level`). Ctx aura = {owner_id/pos/team, att_id/att_pos/att_team, is_melee}."""

    def create_aura_hits_bonus_for_attack(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if not c.get("is_melee"):                          # IsMeleeAttack
            return None
        if c.get("att_id") == c.get("owner_id"):           # SurroundingFriends exclut le porteur (self)
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                    # bénéficiaires = ALLIÉS du porteur
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        import hexgeo
        rng = ability_var("AstartesBanner", "range", is_constant=True)   # ConfigConst 0x16 (=2)
        if hexgeo.distance(op, ap) > int(rng if rng else 2):             # SurroundingFriends(range)
            return None
        n = ability_var("AstartesBanner", "extraHits", is_constant=True)  # constante extraHits (=1)
        return for_addition(True, int(n)) if n else None


class ShadowInTheWarpLessDmgEffect(BaseEffect):
    """`ShadowInTheWarp_LessDmg_Effect` (effet 1053=0x41d) — AURA de RÉDUCTION du dégât PSYCHIQUE. L'effet
    vit sur le PORTEUR (trait ShadowInTheWarp, ex. tyranSmnWarrior) et se PROJETTE sur les ENNEMIS
    environnants (psykers) : quand un tel ennemi attaque en PSYCHIQUE, son dégât est réduit.
    - dégât `CreateEffectDamageBonusForAttack` @180f6b420 : `ForPercentIncrease(OwnerIsActor &
      DamageProfileIs(0xd=Psychic), ConfigConst(0x3b))` = `shadowInTheWarpDmgModifier`% (=-25, négatif).
    - cible `CreateTargetSelector` @180f6b5f0 : `SurroundingEnemies(range=ConfigConst 0x16) &
      UnitsWithTrait(0x3ea) & UnitsNotFromFaction(0xc)`.
    MAGNITUDE + PORTÉE LUES du trait (`traitVariables.shadowInTheWarpDmgModifier=-25`, `shadowInTheWarpRange=2`).
    ⚠ Filtre `UnitsWithTrait(0x3ea)` (psyker) NON décodable offline (pas de map TRAIT) → SUR-APPROXIMÉ au
    seul gate PSYCHIQUE (tout ennemi attaquant en Psychic dans la portée subit le malus) ; raffinement quand
    le trait 0x3ea sera mappé. Canal AURA côté SOURCE (`create_aura_attack_damage_malus_for_enemy`), agrégé
    par `aura_attack_damage_malus_from_enemies` et ajouté aux modifiers de l'ATTAQUANT en prédiction."""

    def create_aura_attack_damage_malus_for_enemy(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if (c.get("damage_profile") or "") != "Psychic":    # DamageProfileIs(0xd) @180f6b420
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
    L'effet vit sur le PORTEUR (posé par `DaughterOfTheAbyssAbility.CreateBehaviour` @180e1f540 :
    AddEffect(0x58b) — capté live source=Atlacoya, JAMAIS matérialisé sur les amis) et se PROJETTE sur
    les cibles à la CALC (boucle state-wide EffectWithTarget × cibles de `CalculateDefenderModifiers-
    ForPrediction` @181002c30).
    - dégât `CreateEffectDamageMalusForDefense` @180f3cde0 : `(OwnerIsTarget & DamageProfileIs(0xd=
      Psychic)) -> -ConfigVar(0x46=dmgReductionPct, abilityState)` (négation via nœud Direct(-1), mirror
      du jumeau Owner @180f3d070 `Multiply(ConfigVar, factory+0xd8)`).
    - cibles (selector famille, jumeau symétrique @180f3cd00) : amis du porteur dans le rayon
      `constants.range` (=2), « OTHER » ⇒ exclut le porteur (qui a SON OwnerDmgReduction).
    MAGNITUDE : `dmgReductionPct[ablvl]` (25→33, hors variablesAffectedByRarityBonus ⇒ PAS de scaling
    rareté). GROUND TRUTH #184 (seed 2024 MC1_67) : bloodMephiston (Psychic) → tgts 81/83/85/79 tous à
    ≤2 hexes d'Atlacoya (6,8) = natif ×0.67 EXACT (2016,3024 = 1003×1.25×[0.8,1.2]×3×0.67), cible ALLIÉE
    de Mephiston (hors aura) = ×1.0 (3009,4515) ; u91 worldExecutions (profil Power) = bit-exact sans
    réduction. C'était le ~1.49x du flip-flop #184 (1/0.67), PAS un écart de hit-count."""

    def create_aura_defense_damage_malus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if (c.get("damage_profile") or "") != "Psychic":      # DamageProfileIs(0xd) @180f3cde0
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
    - dégât `CreateEffectDamageMalusForDefense` @180f3d070 : `(OwnerIsTarget & DamageProfileIs(0xd=
      Psychic)) -> Multiply(ConfigVar(0x12=dmgReduction, abilityState), Direct(-1) factory+0xd8)`
      = soustraction plate (slot additif défenseur @+0x10, mirror Nightshroud #111/#120).
    MAGNITUDE : `dmgReduction[ablvl]` ∈ variablesAffectedByRarityBonus ⇒ × multiplier de l'unité.
    ⚠ NON VALIDÉ LIVE (#184) : structure lue du décompilé (jumeau exact de Nightshroud @180f5bff0,
    lui validé) mais aucune mesure native vs Atlacoya-cible obtenue (hors plans dans les seeds
    d'audit + rows toujours predOptimistic via son Parry_ReduceHits) — placement per-hit additif
    présumé par la famille."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if (damage_profile or "") != "Psychic":               # DamageProfileIs(0xd) @180f3d070
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        amt = ability_var("DaughterOfTheAbyss", "dmgReduction", level=lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        if not amt:
            return None
        # owner=défenseur (effet sur la cible) → flat_reductions PRÉ-perçage (routage Nightshroud #120)
        return for_subtraction(False, abs(int(amt)))


class DaughterOfTheAbyssExtraDamagePctEffect(BaseEffect):
    """`DaughterOfTheAbyss_ExtraDamagePctEffect` (effet 0x589=1417) — les Psykers ENNEMIS dans le rayon
    du porteur REÇOIVENT +extraDmgPct% de dégât (i2 : « Enemy Psykers within 2 hexes receive +20%
    Damage »). Même mécanique state-wide que le jumeau Friendly, polarité inverse :
    - dégât `CreateEffectDamageBonusForAttack` @180f3cb60 (bonus sur l'attaque CONTRE la cible de l'effet) ;
    - cibles `CreateTargetSelector` @180f3cd00 : `SurroundingEnemies(owner, ConfigConst 0x16=range) &
      UnitsWithTrait(0x3ea=Psyker)`.
    Porté sur le canal aura-défense (le dégât REÇU par la cible augmente) — gate trait CIBLE Psyker via
    `tgt_traits` (gameconfig). MAGNITUDE : `extraDmgPct[ablvl]` (15→20, hors rarityBonus)."""

    def create_aura_defense_damage_malus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if c.get("owner_team") is None or c.get("owner_team") == c.get("tgt_team"):
            return None                                       # SurroundingEnemies : cible ENNEMIE du porteur
        if "Psyker" not in (c.get("tgt_traits") or ()):        # UnitsWithTrait(0x3ea=1002 Psyker)
            return None
        op, tp = c.get("owner_pos"), c.get("t_pos")
        if not op or not tp:
            return None
        import hexgeo
        rng = ability_var("DaughterOfTheAbyss", "range", is_constant=True)   # ConfigConst 0x16 (=2)
        if hexgeo.distance(op, tp) > int(rng if rng else 2):
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        pct = ability_var("DaughterOfTheAbyss", "extraDmgPct", level=lvl)
        if not pct:
            return None
        return for_percent_increase(True, abs(int(pct)))


class PowerTripFullHealthEffect(BaseEffect):
    """`PowerTrip_FullHealthEffect` — axe COUPS (hits), actif SSI PV pleins.
    - hits @180f64cf0 : `ForAddition(ConfigConst key 0x2b)` = constante `extraHit` de l'ability PowerTrip (=1).
    - condition @180f64cb0 : `!IsDamaged` (hp == max).
    MAGNITUDE résolue : `gameconfig.ability('PowerTrip').constants['extraHit']` = 1 → +1 coup quand PV pleins."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True) -> EffectBonus | None:
        # trigger natif @180f64cf0 = `IsNormalAttack & OwnerIsCaster` -> ATTAQUE NORMALE SEULEMENT
        # (l'appliquer aux spéciales sur-prédisait DakkaDakkaDakka -> régression steps 6/13).
        if not is_normal_attack:
            return None
        n = ability_var("PowerTrip", "extraHit", is_constant=True)   # key 0x2b → constante extraHit (=1)
        return for_addition(True, n) if n else None

    def is_active(self, unit_state: Mapping | None = None) -> bool:
        s = unit_state or {}
        hp, mx = s.get("hp"), s.get("max_hp")
        if hp is None or mx is None:        # max_hp non capté → ne pas masquer l'effet à tort
            return True
        return hp >= mx


class PowerTripIgnoreArmorEffect(BaseEffect):
    """`PowerTrip_IgnoreArmorEffect` — « Normal attacks ignore X Armour » = axe PÉNÉTRATION.
    ⚠ Le natif `PowerTrip_IgnoreArmorEffect.CreateEffectDamageBonusForAttack` @180f64fa0 = NO-OP
    (EffectBonus condition-seule, valeur 0) ; la pénétration est en fait bâtie DIRECTEMENT dans
    `CalculateAttackerModifiersForPrediction` @181000590 (lit la config PowerTrip de l'attaquant), pas
    portée par l'effet — pattern d'exploitation directe (cf. §17.17). On l'attribue ICI (l'effet
    représente la présence de PowerTrip ⇒ sa présence GATE correctement la pénétration : normal attack,
    owner=caster). Magnitude = `armorIgnored[level] × AbilityVariablesMultiplierPercentage/100` arrondi
    (§17.21, var flaggée `variablesAffectedByRarityBonus`). VÉRIFIÉ live u90 : 277 × 1.8 = round(498.6)
    = 499 = pénétration @0x28 attaquant ⇒ per-bout u90→u86 [341,1265], ×6 = oracle [2048,7592].
    `armorReduction` (full-health) = axe SÉPARÉ (debuff stateful de la stat FixedArmor cible, hors
    prédiction — la prédiction lit l'armure courante) → non porté ici (cf. PowerTrip_OnAttackAbility)."""

    def get_armor_penetration(self, is_normal_attack: bool = True) -> int | None:
        # Gate ATTAQUE NORMALE (i2 : « Normal attacks ignore X Armour ») — GROUND TRUTH step-13 :
        # DakkaDakkaDakka (spéciale, même porteur u90) per-coup natif 404/728 vs 78 = armure PLEINE
        # (2208), la pénétration 499 ne s'applique qu'au normal (per-coup 416/1598).
        if not is_normal_attack:
            return None
        # armorIgnored indexé par le niveau de l'ABILITY (passive, =50), PAS le stack level (=1), scalé par
        # le multiplier de l'unité. `ability_level` seedé depuis l'unité ; fallback `level` si absent.
        lvl = self.ability_level if self.ability_level is not None else self.level
        return ability_var("PowerTrip", "armorIgnored", lvl,
                           multiplier_pct=self.ability_variables_multiplier)


class StunnedEffect(BaseEffect):
    """`StunnedEffect` (effet COMPOSITE 0x48a=1162) — `ApplyInternal` @180f6eb30 spawne 3 SOUS-effets
    quand Stunned est appliqué (confirmé live : parent rem=1 + enfants 1165 rem=1, 1166/1167 rem=0) :
      - `AddBlockAbilitiesSubEffect` @180f6e870 → 0x48d=1165 Stunned_CantUseAbility, via
        `AddSubEffectWithSameTurns` ⇒ MÊME durée que le parent.
      - `ApplyMovementModifier` @180f6ef30 → 0x48e=1166 Stunned_MovementOverride, via
        `AddStatOverrideEffect` (durée 0 = permanent/lié au parent) ; gardé par `StatAmount(movement)>0`
        côté natif (simplification ici : toujours spawné — la quasi-totalité des units ont movement>0 ;
        reverté par `ResetMovementModifier`).
      - `ApplyDamageModifier` @180f6e9b0 → 0x48f=1167 Stunned_DamageModifier, via `AddEffect(turns=0)`
        (permanent/lié au parent ; reverté par `ResetDamageModifier`).
    Les enfants portent `parent_type=1162` (lien `ParentEffect@+0x70`) ; ils n'ont pas eux-mêmes de
    sous-effets. VALIDÉ live (templSwordBrother/ThunderousAssault → tyranTyrantGuard)."""

    def sub_effects_on_apply(self) -> list[SubEffectSpec]:
        return [
            SubEffectSpec(0x48d, "Stunned_CantUseAbility", turns=SAME_TURNS),  # AddSubEffectWithSameTurns
            SubEffectSpec(0x48e, "Stunned_MovementOverride", turns=0),         # AddStatOverrideEffect (cond. mvt>0)
            SubEffectSpec(0x48f, "Stunned_DamageModifier", turns=0),           # AddEffect turns=0
        ]


class ActOfFaithBuffEffect(BaseEffect):
    """`ActOfFaithBuffEffect` (effet 0x3f9=1017, namespace `Effects.Loki`) — buff de crit empilable du
    trait ActOfFaith (Adepta Sororitas).

    C'est un effet **StatModification** (mute GetStat), PAS un modifier calc-time :
      - `ApplyModification` @180f302f0 : deux `ChangeStat` sur le porteur —
          crit-chance (`Position(9,5)`)  += `actOfFaithExtraCritChance` (=10) **FLAT** (la valeur
            observable get_CurrentValue plafonne à 100 via GetClampedValue) ;
          crit-damage (`Position(10,5)`) += `Ceiling(GetStat(10=critDmg, part=3) × actOfFaithExtraCritDmgPct%
            =25%)` où `part=3` = la stat de **BASE** (StatComponent.GetStatPart@180fa8bb0 → offset 0x48, SANS
            modifications) ⇒ boost **FLAT** sur la crit-dmg hors-ActOfFaith (PAS compound). Confirmé live :
            3 stacks base 250 → +63 plat à chaque fois (250->313->376->439).
      - `RevertInternal` @180f306e0 : annule les deux ChangeStat (delta natif stocké @+0xb8).

    Posé par `ActOfFaithAbility` (trigger mort/kill d'allié Imperial), retiré — TOUS les stacks — par
    `ActOfFaith_RemoveEffectAbility` au crit du porteur. La mutation de stat est faite par le TRIGGER
    (`operations.triggers`), PAS ici : ctx.crit_chance/crit_damage sont déjà effet-inclusifs (GetStat) →
    ne PAS contribuer aux hooks calc-time crit (sinon double-compte). Cette classe ne porte que les DELTAS
    appliqués par CE stack (`cc_delta`/`cd_delta`), pour un revert exact (l'addition compound est
    ordre-dépendante à l'aller, mais le revert = simple soustraction des deltas stockés, donc exact).

    ⚠ Un stack SEEDÉ depuis un snapshot live (déjà fondu dans ctx) ne connaît pas ses deltas (0 par
    défaut) : un reset de stacks seedés ne re-baisse pas la stat. Le chemin VALIDÉ accumule depuis 0
    (deltas exacts) ; le seeding mid-accumulation est un edge case documenté."""
    cc_delta: int = 0   # delta crit-chance OBSERVÉ par CE stack (info/report)
    cd_delta: int = 0   # delta crit-damage OBSERVÉ par CE stack (info/report)
    stat_mod_source = None   # clé de source ChangeStat (revert par-source via UnitStats.revert_stat)


class KanOpenerEffect(BaseEffect):
    """`KanOpenerEffect` (triggered) — `IgnoreArmor` @180f65100 = `ConfigVar(key 0x40)` = pénétration
    d'armure per-niveau (axe armure, contrairement à PowerTrip dont la réduction est stateful on-attack).
    ⚠ KillaKan n'a PAS KanOpener (kit = PowerTrip) ; clé 0x40 → nom var gameconfig non résolu pour les
    unités qui l'ont → pénétration None tant qu'inconnue (à mapper quand on porte une unité KanOpener)."""

    def get_armor_penetration(self, is_normal_attack: bool = True) -> int | None:
        # TODO: mapper la clé 0x40 → var gameconfig (per-niveau) puis return ability_var(..., self.level).
        return None


class TauntedEffect(BaseEffect):
    """`TauntedEffect.ApplyInternal` @180f47510 (effet COMPOSITE 27 = `Taunted_OnlySpecificTargets`,
    base `ABondEffect` — lien cible↔tauntant). À l'application, spawne 3 SOUS-effets via
    `AddSubEffectWithSameTurns` (⇒ MÊME durée que le parent) :
      - 0x19=25  `Taunted_BlockMovement`        (la cible ne peut plus se déplacer)
      - 0x1a=26  `Taunted_CantUseAbility`        (la cible ne peut plus utiliser d'ability active)
      - 0x4d5=1237 `Taunted_RefreshUnitTurnFinished`
    Le natif enregistre aussi le `BondedEntityId` (la cible est forcée d'attaquer le tauntant) — c'est un
    effet de CIBLAGE IA (concern playbook, non porté ici : on matérialise l'effet + ses enfants ; le
    `source` de l'effet = le tauntant capture la direction du bond). VALIDÉ live attendu : la cible porte
    27 + 25/26/1237 (parent 1 round, enfants same-turns) après CrushingClaws."""

    def sub_effects_on_apply(self) -> list[SubEffectSpec]:
        return [
            SubEffectSpec(0x19, "Taunted_BlockMovement", turns=SAME_TURNS),      # AddSubEffectWithSameTurns
            SubEffectSpec(0x1a, "Taunted_CantUseAbility", turns=SAME_TURNS),     # AddSubEffectWithSameTurns
            SubEffectSpec(0x4d5, "Taunted_RefreshUnitTurnFinished", turns=SAME_TURNS),
        ]


class PinnedEffect(BaseEffect):
    """`PinnedEffect.ApplyInternal` @180f5e6d0 (effet 1065 `Pinned` ; UI = « Suppressed »). Effet
    stat-mod SIMPLE (pas de sous-effet nommé) : un `ChangeStat(Position(1,5), statType=4 = Movement,
    valeur = Negative(EffectConfig(1)))` sur la cible ⇒ réduit le MOUVEMENT (la cible « pinned » ne peut
    pas avancer le tour suivant).

    ⚠ Contributions NON encore portées (présent ≠ appliqué, §17.4) : (1) la réduction de Movement (le
    mouvement n'est pas dans le chemin de combat/dégât porté) ; (2) `PinnedEffect.CreateEffectDamageBonusForAttack`
    @180f5e8e0 (malus de dégât quand l'unité Pinned attaque) — à RE + porter si on modélise le débuff
    offensif. Ici on MATÉRIALISE l'effet (nom 1065 sur la cible) — c'est le scope de la tranche EFFETS."""
