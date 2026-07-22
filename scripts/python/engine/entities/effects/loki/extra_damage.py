"""Effets `Effects.Loki` — famille BONUS DE DÉGÂT ATTAQUANT (`create_effect_damage_bonus_for_attack` /
`create_aura_attack_bonus` / aura attack). 1 classe par effet natif (VA citée). Cf. `loki/__init__.py`.

Chaque classe override UNIQUEMENT ce qu'elle implémente dans le natif (lu en ghidra). Les magnitudes
non encore confirmées par nom gameconfig renvoient None (pas de contribution) = on N'INVENTE PAS de
valeur non prouvée (cf. doc §17.4 « présent ≠ appliqué »)."""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import (EffectBonus, for_addition, for_subtraction,
                                       for_percent_decrease, for_percent_increase,
                                       for_percent_subtraction_capped)
from ..base import BaseEffect
from ..magnitude import ability_var, global_value, trait_var


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
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        pct = trait_var("RapidAssault", "rapidAssaultExtraDmgPct")
        return for_percent_increase(True, pct) if pct is not None else None

    @property
    def removed_after_attack(self) -> bool:
        return True


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
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
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
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
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
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        # Gate natif = OwnerIsCaster SEUL (@180f3e340) : aucun re-gate is_ranged/is_normal/is_prediction.
        # Ce chemin n'est appele que pour les attaques du porteur -> OwnerIsCaster implicitement TRUE.
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        amt = ability_var("DecoysAndMisdirection", "extraDmg", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        # ForAddition -> canal `additive @+0x10` applique POST-percage (DamageModifiers.Add @181005f10).
        return for_addition(True, amt) if amt is not None else None


class LordOfTempestsExtraDamageEffect(BaseEffect):
    """`LordOfTempests_ExtraDamageEffect` (Effects.Loki, EffectType 0x4d4=1236, nom capté
    "LordOfTempests_ExtraDamage" — passif de Njal spaceStormcaller). i2 : « Njal's normal attacks deal
    +237 Damage for each hex surrounding him that is covered in Ice. » (#29, lead 1 agreement-stages).

    - hexes `GetHexesIncreasingDamage @180f56b40` : `EntitiesWithAnyEffect(SurroundingTiles(owner, 0, 1),
      0x11, domain Tiles)` = les tuiles du RING-1 du caster porteuses de l'effet **Ice** — le CENTRE ne
      compte PAS (vérifié bit-exact seed 31337 s18 : (2,4) elle-même glacée -> count=3 = ring-1 seul).
    - dégât `CreateEffectDamageBonusForAttack @180f569a0` : `EffectBonus.ForAddition(get_OwnerIsCaster,
      Multiply(ConfigVar(8=extraDmg, GetAbilityState(effet)), Count(hexes)))` — FLAT additif, canal
      standard `DamageModifiers.Add @181005f10` appliqué PAR COUP (comme SmashaEad/BeaconOfRage).
    - condition d'activité `CreateActiveCondition @180f56950` : `AmountIsGreaterThanZero(Count(hexes))`
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
    - gate `is_normal_attack` : l'i2 dit « normal attacks » (le trigger-flag struct copié @param_2+0x14
      n'est pas décodé ; gate conservateur aligné i2 — la spéciale Stormcaller ne porte pas le bonus).
    - La 2e moitié du passif (« each enemy hit covers its hex in Ice ») =
      `LordOfTempests_AddIceAbility.CreateBehaviour/CreateTrigger @1811085d0/@181108670` (face RUNTIME,
      arbre DSL AddEffect tile-domain) — PORTÉE #35 (`runner/operations/triggers/loki/lord_of_tempests.py`,
      case-35) : le runner pose la glace en simulant ; la prédiction lit la glace DÉJÀ posée (tileMeta
      frais), elle n'en pose pas. Côté COMBAT runner l'att_ctx positionnel vient de
      `damage_model._positional_att_ctx` (state.effects tuiles), symétrique du tileMeta."""

    ICE_TILE_EFFECT = "Ice"   # nom d'effet de tuile capté (tileMeta.effects[].name, vérifié live 31337)

    def get_hexes_increasing_damage(self, att_ctx) -> int:
        """`GetHexesIncreasingDamage @180f56b40` -> COUNT des tuiles ring-1 (centre EXCLU) autour de la
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
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
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
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
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
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
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
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        if is_ranged:                                  # IsMeleeAttack -> melee uniquement
            return None
        if not target_traits or _BEAST_SLAYER_TARGET_TRAITS.isdisjoint(target_traits):
            return None                                # cible ni BigTarget ni Vehicle -> 0
        pct = trait_var("BeastSlayer", "beastSlayerExtraDmgPct")
        return for_percent_increase(True, pct) if pct is not None else None


class MartialKatahDmgBonusEffect(BaseEffect):
    """`MartialKatah_DmgBonusEffect.CreateEffectDamageBonusForAttack @180f58930` (trait MartialKatah,
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


class BeaconOfRageExtraDamageEffect(BaseEffect):
    """`BeaconOfRage_ExtraDamageEffect` (EffectType 0x512=1298, nom capté "BeaconOfRage_ExtraDamage" ;
    AbilityOrEffect 0x4d4=1236 = BeaconOfRage, passive d'Azkor worldEightbound) — i2 : « For each time
    he was attacked in battle, up to a maximum of 8 times, Azkor deals +315 Damage » (+315 = extraDmg
    au niveau max 65). #189.

    - dégât `CreateEffectDamageBonusForAttack @180f33130` : `ForAddition(get_OwnerIsCaster,
      Multiply(ConfigVar(8=extraDmg, GetAbilityState(effet)), EffectLevel(effet)))` — bonus FLAT
      additif (AUCUN ForPercent*), trigger OwnerIsCaster SEUL (tous profils, normale ET spéciale) ;
      même canal additif que SmashaEad (#69 : `DamageModifiers` additif, appliqué par
      `CalculateBaseDamageWithAllModifiers @18102d3f0`).
    - niveau de RAGE = `EffectLevel` de l'instance = `min(TotalTimesAttacked, nrOfAttacks=8)` :
      `ABeaconOfRageAbility.GetCurrentSelfEffectLevel @180e12fa0` = `Min(TotalTimesAttacked(unit),
      ConfigConst(0x59=nrOfAttacks))`, écrit par `GetUpdateSelfEffectBehaviour @180e13230`
      (`AddEffect(0x512)` si absent & level>0, puis `SetEffectLevel(0x512, level)`) → arrive tel quel
      dans decisionView.effects[].level (Level @0x68). PAS de re-calcul offline : le level capté EST
      la vérité (le cap est appliqué à l'ÉCRITURE par le natif ; TotalTimesAttacked non capté).
    - magnitude : `extraDmg[abilityLevel]` (variables BeaconOfRage, 1→315 sur 65 niveaux, HORS
      variablesAffectedByRarityBonus → pas de scaling multiplier) × level. `ability_level` = niveau
      PASSIF du porteur (Scene ablvl_by_id) ; niveau inconnu → inerte (dégradation fidèle).

    La variante `BeaconOfRage_FriendlyExtraDamage` (0x513=1299 : 50% du bonus, attaques MÊLÉE des
    amis Chaos adjacents, gate `OwnerIsCaster & IsMeleeAttack`, `PercentageOf(..., 50) @180f33370`,
    active SSI le porteur a ≥1 kill — `GetCurrentFriendEffectLevel @180e12f10 = If(UnitsDefeated-
    Amount>0, selfLevel, 0)`) = effet-aura SÉPARÉ (`BeaconOfRageFriendlyExtraDamageEffect`)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        # trigger natif @180f33130 = get_OwnerIsCaster SEUL — tous profils, normale ET spéciale.
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


class BeaconOfRageFriendlyExtraDamageEffect(BaseEffect):
    """`BeaconOfRage_FriendlyExtraDamageEffect` (EffectType 0x513=1299, nom capté
    "BeaconOfRage_FriendlyExtraDamage") — variante AURA de BeaconOfRage (le SELF 0x512=1298 =
    `BeaconOfRageExtraDamageEffect`). i2 : « 50% of the extra damage from Beacon of Rage is added to the
    damage of melee attacks of adjacent friendly Chaos units. » #191.

    L'effet vit sur le PORTEUR (Azkor) : `GetUpdateFriendEffectBehaviour @180e13040` fait
    `AddEffect(0x513, owner@0x148)` + `SetEffectLevel(owner, 0x513, ...)` SUR AZKOR (jamais sur les amis)
    → capté dans decisionView.effects d'AZKOR, PAS de l'ami. Il se PROJETTE sur ses amis Chaos adjacents
    (canal AURA côté SOURCE, comme AstartesBanner / DaughterOfTheAbyss).

    - dégât `CreateEffectDamageBonusForAttack @180f33370` : `ForAddition(get_OwnerIsCaster &
      IsMeleeAttack, PercentageOf(Multiply(ConfigVar(8=extraDmg, GetAbilityState), EffectLevel(effet)),
      0x32=50, mode 0))` = FLAT additif = **50 % du bonus SELF** (`extraDmg[ablvl Azkor] × rage`), arrondi
      half-to-even. Trigger : l'AMI attaque (OwnerIsCaster projeté) en MÊLÉE (même canal additif
      `DamageModifiers.Add` que le self BeaconOfRage / SmashaEad).
    - cible `CreateTargetSelector @180f335b0` : `UnitsWithTrait(AdjacentFriends(owner@0x148, 1, 3),
      0x7ea=2026=Chaos, 3)` = amis d'Azkor ring-1 (hex-adjacents) de grande-alliance Chaos.
    - niveau/présence `GetCurrentFriendEffectLevel @180e12f10` = `If(UnitsDefeatedAmount(Azkor)>0,
      GetCurrentSelfEffectLevel, 0)` : l'effet n'est AJOUTÉ sur Azkor (behaviour @180e13040 :
      `If(UnitsDefeatedAmount>0 & !HasEffect(0x513), AddEffect)`) QUE si Azkor a ≥1 kill, avec pour level
      la même RAGE que le self (`Min(TotalTimesAttacked, 8)`). ⇒ la PRÉSENCE de l'effet dans la capture
      encode DÉJÀ le gate ≥1-kill + la rage → on lit `self.level` tel quel (comme le self, PAS de recalcul
      offline de UnitsDefeatedAmount).

    Gate grande-alliance Chaos (trait 2026) = ABSENT de gameconfig.traits → dérivé de GrandAllianceId
    (`GrandAlliance.GetTrait @1815647a0` : Imperial→26, Xenos→0x3ee, Chaos→0x7ea=2026), comme le gate
    Imperial de RitesOfBattle. Magnitude `extraDmg` = ability_var BeaconOfRage indexée sur l'ablvl PASSIF
    d'AZKOR (source), pas de l'ami (l'effet-entité porte l'ablvl d'Azkor). Ctx aura = {owner_id/pos/team,
    att_id/att_pos/att_team, att_grand_alliance, is_melee}."""

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if not c.get("is_melee"):                             # IsMeleeAttack @180f33370
            return None
        if c.get("att_id") == c.get("owner_id"):              # AdjacentFriends exclut le porteur (self)
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                       # AdjacentFriends : bénéficiaire = ALLIÉ d'Azkor
        if c.get("att_grand_alliance") != "Chaos":            # UnitsWithTrait(0x7ea=2026=Chaos)
            return None
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        import hexgeo
        if hexgeo.distance(op, ap) > 1:                       # AdjacentFriends(owner, radius 1) = hex-adjacent
            return None
        if self.level is None or int(self.level) <= 0:        # rage (EffectLevel) — gate >=1-kill baké à l'écriture
            return None
        if self.ability_level is None:                        # ConfigVar sans AbilityState -> pas de magnitude
            return None
        per = ability_var("BeaconOfRage", "extraDmg", self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        if not per:
            return None
        from fractions import Fraction
        self_bonus = int(per) * int(self.level)               # Multiply(ConfigVar(extraDmg), EffectLevel)
        friendly = round(Fraction(self_bonus * 50, 100))      # PercentageOf(x, 0x32=50, mode 0 = half-to-even)
        return for_addition(True, friendly) if friendly else None


class LordOfTheHostExtraDamageEffect(BaseEffect):
    """`LordOfTheHost_ExtraDamageEffect` (effet 0x562=1378, nom capté "LordOfTheHost_ExtraDamage",
    passif LordOfTheHost 0x515=1301 de bloodDante) — AURA côté SOURCE : l'effet vit sur DANTE
    (capté chez lui, permanent), il se projette sur ses amis. i2 : « Other friendly units within
    2 hexes with Rapid Assault or Flying deal +extraDmg Damage with melee attacks. » #57c.

    - dégât `CreateEffectDamageBonusForAttack @180f56e30` : `ForAddition(IsMeleeAttack &
      OwnerIsCaster, ConfigVar(8=extraDmg, GetAbilityState))` = +extraDmg[ablvl Dante]×mult FLAT
      additif PRÉ-perçage PAR COUP (canal `DamageModifiers.additive`, comme SmashaEad/BeaconOfRage).
    - cible `CreateTargetSelector @180f56fb0` : `Unique(UnitsWithTrait(SurroundingFriends(owner,
      ConfigConst(0x16)=range=2), 0x413=RapidAssault) + UnitsWithTrait(idem, 4=Flying))` — amis
      (self exclu) à ≤2 hexes du porteur, porteurs du trait RapidAssault OU Flying.
    - ré-évaluation PAR TUILE CANDIDATE (#57c prouvé, modèle RitesOfBattle #49/#153) : 12345 s18
      u77 bloodSanguinary RÉEL à dist-3 de Dante (AUCUN effet posé sur lui live), le natif ajoute
      quand même le bonus à la candidate (0,4) dist-2.

    VALIDÉ (probe_57c_flathits.py A) : Dante ablvl=50 mult=180 → a = extraDmg[50]×1.8 = 898.2
    pré-perçage par coup, puis ×1.25 RapidAssault, ×4 coups → nat = off + 4488 EXACT min&max
    (7704/12324 vs 3216/7836, armure 1205 traversée pierce 20)."""

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if not c.get("is_melee"):                             # IsMeleeAttack (@180f56e30)
            return None
        if c.get("att_id") == c.get("owner_id"):              # SurroundingFriends : self exclu
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                       # bénéficiaire = AMI du porteur
        traits = c.get("att_traits") or frozenset()
        if "RapidAssault" not in traits and "Flying" not in traits:
            return None                                       # UnitsWithTrait(0x413 RapidAssault | 4 Flying)
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        rng = ability_var("LordOfTheHost", "range", is_constant=True) or 2   # ConfigConst 0x16
        import hexgeo
        if hexgeo.distance(op, ap) > int(rng):
            return None
        if self.ability_level is None:                        # ConfigVar sans AbilityState -> pas de magnitude
            return None
        amt = ability_var("LordOfTheHost", "extraDmg", self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, amt) if amt else None


class DoomExtraDmgEffect(BaseEffect):
    """`Doom_extraDmgEffect` (effet 0x45a=1114, nom capté "Doom_extraDmg", passif Doom de
    eldarFarseer Eldryon) — AURA côté SOURCE gate CIBLE : les ENNEMIS à EXACTEMENT `range`(=2)
    hexes d'Eldryon prennent +extraDmg des attaques NORMALES des amis d'Eldryon (+extraDmg_2 de
    TOUTES les attaques des amis Aeldari). i2 : « All enemy units exactly 2 hexes away from
    Eldryon take +extraDmg Damage from other friendly unit's normal attacks. Other friendly
    Aeldari units deal +extraDmg_2 Damage with all their attacks to affected units instead. » #57c.

    - dégât `CreateEffectDamageBonusForAttack @180f3f780` : `ForAddition(OwnerIsTarget &
      AreFriends(attaquant, EffectSource) & !AreEqual(attaquant, EffectSource) &
      (HasFaction(attaquant, Aeldari) | IsNormalAttack), ConditionalAmount(HasFaction(att,
      Aeldari), ConfigVar(9=extraDmg_2), ConfigVar(8=extraDmg)))` — FLAT PRÉ-perçage PAR COUP.
    - cible `CreateTargetSelector @180f3fa80` : `SurroundingEnemies(owner, ConfigConst(0x16)=
      range) − SurroundingEnemies(owner, range−1)` = ennemis à EXACTEMENT range hexes du porteur.
    - AUCUN effet posé sur la cible doomée (#57c : Shadowsun dist-2 exacte, effectAbilityStates
      vide d'un Doom chez elle) — l'effet vit sur le PORTEUR, le selector est évalué à la demande.

    VALIDÉ (probe_57c_flathits.py B, 54321 s7 u79 genesPatriarch→t95 tauShadowsun dist-2
    d'Eldryon ablvl=50 mult=180) : a = extraDmg[50]×1.8 = 898.2 pré-perçage par coup ×5 coups,
    l'armure 1806 mange la part bloquée → nat 5060/6470 = off + 2240 EXACT min&max."""

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        tp, op = c.get("t_pos"), c.get("owner_pos")
        if not tp or not op:
            return None
        if c.get("tgt_team") is None or c.get("tgt_team") == c.get("owner_team"):
            return None                                       # SurroundingEnemies : cible ENNEMIE du porteur
        if c.get("att_id") == c.get("owner_id"):              # !AreEqual(attaquant, EffectSource)
            return None
        if c.get("owner_team") != c.get("att_team"):          # AreFriends(attaquant, EffectSource)
            return None
        rng = int(ability_var("Doom", "range", is_constant=True) or 2)   # ConfigConst 0x16
        import hexgeo
        if hexgeo.distance(op, tp) != rng:                    # EXACTEMENT range (soustraction ring r-1)
            return None
        is_aeldari = (c.get("att_faction") == "Aeldari")      # HasFaction(attaquant, Aeldari)
        if not is_aeldari and c.get("is_normal_attack") is False:
            return None                                       # branche non-Aeldari gated IsNormalAttack
        if self.ability_level is None:
            return None
        var = "extraDmg_2" if is_aeldari else "extraDmg"      # ConditionalAmount(Aeldari -> 9, sinon 8)
        amt = ability_var("Doom", var, self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, amt) if amt else None


class _SpotterReworkedAuraBase(BaseEffect):
    """Base commune des deux effets-aura du passif SpotterReworked 0x5df=1503 (astraOrdnance Thaddeus) —
    AURA côté SOURCE : `SpotterReworkedAbility.CreateBehaviour @1811a1920` pose les DEUX effets sur le
    PORTEUR (`AddEffect(0x40f=1039) + AddEffect(0x428=1064)`), chacun se projette sur ses amis via son
    TargetSelector. i2 : « Other friendly units within {range} hexes deal +{extraDmg} Damage with ranged
    attacks ; Heavy Weapon units deal +{extraDmg_2} instead. » Le « instead » = sélecteurs mutuellement
    exclusifs sur le trait HeavyWeapon 0x3e9=1001. Sélecteur commun (@180f6c860 / @180f6cb40) :
    `SurroundingFriends(owner, ConfigConst(0x16)=range=2, 1, 3) → UnitsWithRangedAttacks → fork trait`
    (self exclu, ami à ≤range hexes).

    ⚠ `UnitsWithRangedAttacks @180e00610` N'EST PAS un filtre arme-ranged pur : c'est l'UNION
    (`TargetsSelector.op_Addition`, même sens que LordOfTheHost RapidAssault+Flying) de
    `UnitsWithWeaponsSelector(type 2=ranged)` ET `TilesOnSameElevationSelector(réf=DSLFactory+0x28
    = entité du contexte (porteur), maxDiff=2)` — `GetElevationDifference @180ec4ee0` =
    abs(élév_a − élév_b), garde si ≤ 2. Un ami SANS arme ranged est donc INCLUS dès que sa tuile
    (candidate en prédiction) est à ≤2 d'élévation de la tuile du porteur — MESURÉ live (probe_66 :
    Baraqiel darkaTerminator melee-only reçoit +extraDmg_2, +~399/coup). Sur les boards à faible
    amplitude d'élévation (MC1_67 : 3–4) le nœud est un pass-through. Board absent du ctx →
    retombe sur le terme arme seul (conservateur). #66."""

    _VAR = ""                 # ConfigVar(8)=extraDmg | ConfigVar(9)=extraDmg_2
    _WANT_HEAVY = False       # UnitsWithoutTrait(1001) | UnitsWithTrait(1001)

    def _trigger_ok(self, c: Mapping) -> bool:
        raise NotImplementedError

    @staticmethod
    def _in_ranged_attacks_selector(c: Mapping) -> bool:
        """`UnitsWithRangedAttacks @180e00610` : arme ranged au kit OU |Δélévation| ≤ 2 vs porteur."""
        if c.get("att_has_ranged_weapon"):
            return True
        b, op, ap = c.get("board"), c.get("owner_pos"), c.get("att_pos")
        if b is None or not op or not ap:
            return False
        to, ta = b.tile_at(op[0], op[1]), b.tile_at(ap[0], ap[1])
        if to is None or ta is None:
            return False
        return abs(int(ta.get("elevation") or 0) - int(to.get("elevation") or 0)) <= 2

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if not self._trigger_ok(c):
            return None
        if c.get("att_id") == c.get("owner_id"):              # SurroundingFriends : self exclu
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                       # bénéficiaire = AMI du porteur
        if not self._in_ranged_attacks_selector(c):           # UnitsWithRangedAttacks (union, cf. classe)
            return None
        traits = c.get("att_traits") or frozenset()
        if ("HeavyWeapon" in traits) != self._WANT_HEAVY:     # UnitsWith[out]Trait(0x3e9=1001)
            return None
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        rng = ability_var("SpotterReworked", "range", is_constant=True) or 2   # ConfigConst 0x16
        import hexgeo
        if hexgeo.distance(op, ap) > int(rng):
            return None
        if self.ability_level is None:                        # ConfigVar sans AbilityState -> pas de magnitude
            return None
        amt = ability_var("SpotterReworked", self._VAR, self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, amt) if amt else None


class SpotterReworkedExtraDamageEffect(_SpotterReworkedAuraBase):
    """`SpotterReworked_ExtraDamageEffect` (effet 0x40f=1039) — amis SANS HeavyWeapon.
    - dégât `CreateEffectDamageBonusForAttack @180f6c680` : `ForAddition(OwnerIsActor & IsRangedAttack,
      ConfigVar(8=extraDmg, GetAbilityState), source 0x5df)` = +extraDmg[ablvl Thaddeus]×mult FLAT
      additif PRÉ-perçage PAR COUP (canal `DamageModifiers.additive`, comme LordOfTheHost).
    - cible `CreateTargetSelector @180f6c860` : `UnitsWithoutTrait(UnitsWithRangedAttacks(
      SurroundingFriends(owner, range=2)), 0x3e9=HeavyWeapon)`."""

    _VAR = "extraDmg"
    _WANT_HEAVY = False

    def _trigger_ok(self, c: Mapping) -> bool:
        return c.get("is_melee") is False                     # IsRangedAttack (@180f6c680)


class SpotterReworkedHeavyWeaponEffect(_SpotterReworkedAuraBase):
    """`SpotterReworked_HeavyWeaponEffect` (effet 0x428=1064) — amis AVEC HeavyWeapon, « instead ».
    - dégât `CreateEffectDamageBonusForAttack @180f6c980` : `ForAddition(OwnerIsActor,
      ConfigVar(9=extraDmg_2, GetAbilityState), source 0x5df)` — trigger SANS IsRangedAttack (fidèle
      au décompilé : un porteur HeavyWeapon à arme ranged garde le bonus même sur un coup MÊLÉE).
    - cible `CreateTargetSelector @180f6cb40` : `UnitsWithTrait(UnitsWithRangedAttacks(
      SurroundingFriends(owner, range=2)), 0x3e9=HeavyWeapon)`."""

    _VAR = "extraDmg_2"
    _WANT_HEAVY = True

    def _trigger_ok(self, c: Mapping) -> bool:
        return True                                           # OwnerIsActor seul (@180f6c980)
