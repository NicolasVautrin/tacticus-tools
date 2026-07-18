"""Effets `Effects.Loki` — famille MALUS DE DÉGÂT DÉFENSEUR (`create_effect_damage_malus_for_defense` +
auras de réduction). Réduit le dégât REÇU par le porteur (ou par ses alliés / l'ennemi via aura).
1 classe par effet natif (VA citée). Cf. `loki/__init__.py`."""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import (EffectBonus, for_addition, for_subtraction,
                                       for_percent_decrease, for_percent_increase,
                                       for_percent_subtraction_capped)
from ..base import BaseEffect
from ..magnitude import ability_var, global_value, trait_var


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
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None) -> EffectBonus | None:
        lvl = self.ability_level if self.ability_level is not None else self.level
        v = ability_var("FightingRetreat", "dmgReduction", lvl,
                        multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, -int(v)) if v else None


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


class OverwhelmingWrathRangeDmgReductionEffect(BaseEffect):
    """`OverwhelmingWrath_RangeDmgReductionEffect` (EffectType 0x515=1301, nom capté
    "OverwhelmingWrath_RangeDmgReduction" ; famille `ADamageDefenseModifierAbilityEffect`, ctor
    @180f5d850 = base(0x475=1141 = OverwhelmingWrath, l'ACTIVE d'Azkor worldEightbound)) — i2 :
    « Until the beginning of his next turn Azkor Taunts all adjacent enemies and takes -64% Damage
    from ranged attacks. » Effet TRANSIENT (rem=1 capté), posé par l'ExecuteBehaviour de l'ability
    (@1811f8bc0), expire au début du tour suivant du porteur. #190.

    - dégât `CreateDamageDefenseModifier @180f5d6e0` : `EffectBonus.ForPercentDecrease(
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
        if is_melee is not False:                # gated IsRangedAttack @180f5d6e0
            return None
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        pct = ability_var("OverwhelmingWrath", "dmgReductionPct", lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        if not pct:
            return None
        return for_percent_decrease(False, abs(int(pct)))   # owner=défenseur (l'effet est sur la cible)
