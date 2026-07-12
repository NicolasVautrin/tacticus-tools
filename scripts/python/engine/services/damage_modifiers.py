"""Port FIDÈLE de DEUX classes natives (gqfc5mff6c) — RE intégrale + tracée live, doc §17 :
  • `IdunBattle.Core.Services.DamageModifiers`   = le STRUCT accumulateur (d'où le nom du module) ;
  • la TRANCHE "MODIFIER" de `IdunBattle.Core.Services.DamageCalculations` = les feuilles qui construisent /
    appliquent ce struct (multiplier, cap, builder attaquant, feuilles positionnelles + leur config).

⚠ `DamageCalculations` est une grosse classe service ÉCLATÉE PAR CONCERN dans le port (convention du repo,
PAS une classe = un module) : la tranche MODIFIER est ICI ; la tranche COMBAT (crit/block/evasion) est dans
`damage_combat.py` ; les builders qui itèrent les EFFETS (`CalculateAttackerModifiersForPrediction` boucle,
`CalculateDefenderModifiersForPrediction`) vivent dans `entities/effects/__init__.py`. Chaque tranche cite
sa VA. Voir aussi `damage_prediction.py` (= classe `DamagePrediction`, le pipeline PredictAttackRaw).

Fonctions/données natives portées 1:1 ICI (VA citée) :
  • `DamageModifiers`                                    (struct)        Empty@181006370 / Add@181005f10
  • `DamageCalculations.GetMultiplierFromDamageBonus`    @181005210      (1 ± pct/100)
  • `DamageCalculations.ApplyCappedModifiers`            @181000020      (réducteur : v=clamp(round(v×mult),±cap))
  • `DamageCalculations.CalculateAttackerModifiersForPrediction` @181000590  (builder = boucle sur param_5)
  • leaves positionnels : CalculateElevationBonusModifier@181003ea0 /
    CalculateRangedInMeleeReduction@181004700 / CalculateTrenchReduction@181004830
  • config `DamageCalculations.Init @181005790` : ELEVATION_BONUS_PCT / EFFECT_NO_ELEVATION (section Damage
    de la BC) — consommee a l'identique par la prediction (playbook) ET le combat (runner).

CHAÎNE (RE §17, tracée live §17.7) : dans `PredictAttackRaw`, `CalculateBaseDamageWithAllModifiers`
applique le modifier **par coup, APRÈS perçage/armure** via `ApplyCappedModifiers`. `param_5` (la liste
de sources) = **les EFFETS actifs de l'unité** (interface effets `DAT_1831b7938` slot 9, §17.8) — chacun
fournit sa contribution via `CreateEffect*ForAttack` (→ `EffectBonus`). Donc le builder = « pour chaque
effet actif, ajoute sa contribution à l'accumulateur ».

⚠ Zones d'ombre (generic-sharing / non tranché statiquement, marquées HYPOTHÈSE) : (a) placement exact
de l'`additif` plat (Addition/Subtraction) vs le `%-list` — ici additif appliqué après le %-list ;
(b) arrondi Fix64 mode 1 ≈ `round()` Python (résidu ±1-3 connu).
"""
from __future__ import annotations

import json as _json
from dataclasses import dataclass, field

from .effect_bonus import EffectBonus, for_addition, for_subtraction
from .. import weights as _weights

# Config `DamageCalculations` (section Damage de la BattleConfiguration) — le natif la charge via
# `DamageCalculations.Init @181005790`. Ces constantes appartiennent au port de DamageCalculations (ce
# module), consommees a l'identique par la PREDICTION (playbook) ET le COMBAT (runner) — pas de fork.
_DMG_CFG: dict = _json.loads(_weights.DEFAULT_BC.read_text(encoding="utf-8")).get("Damage", {}) \
    if _weights.DEFAULT_BC.exists() else {}
ELEVATION_BONUS_PCT: int = int(_DMG_CFG.get("ElevationBonus", 50))   # CalculateElevationBonusModifier @181003ea0
EFFECT_NO_ELEVATION: int = 0x423   # effectType gate (0x423) : elevation coupee si attaquant OU cible le porte


@dataclass
class DamageModifiers:
    """Accumulateur `DamageModifiers` (struct ~0x40 : additif@+0x10, %-list@+0x18, mult@+0x30=1,
    detail@+0x38). `pct_list` = liste de `(mult, cap)` (mult=1±pct/100 ; cap=None si non plafonné)."""
    additive: float = 0.0
    pct_list: list[tuple[float, int | None]] = field(default_factory=list)
    multiplicative: float = 1.0
    details: list[EffectBonus] = field(default_factory=list)
    # axe ARMURE/PERÇAGE (champs du DamageModifiers natif lus par CalculateBaseDamageWithAllModifiers
    # @18102d3f0 → GetBaseDamageWithFixedPiercedArmor) — distinct du scalaire dégât (additif/%-list) :
    extra_pierce: int = 0          # @0x20 : pierce_eff = clamp(pierce + extra_pierce, 0, 100)
    armor_penetration: int = 0     # @0x28 : armor_eff = max(FixedArmor − armor_penetration, 0)
    ignore_armor: bool = False     # ignore-armure totale → armor_eff = 0 (pénétration ≥ armure)
    # Réductions DYNAMIQUES CAPÉES (défenseur, ex. GuardianOrganism) : liste de (pct, cap) — soustrait
    # `min(pct% × dégât_courant, cap)` du dégât APRÈS %-list+additif (CurrentDamage). Distinct du %-list
    # (multiplicatif) : c'est une ForSubtraction dont le montant dépend du dégât courant, plafonné.
    capped_reductions: list[tuple[int, int | None]] = field(default_factory=list)
    # Additifs DÉFENSEUR de SOUSTRACTION (ex. Nightshroud_DmgReduction @180f5bff0 : `ForSubtraction(
    # OwnerIsTarget, ConfigVar(0x12)=dmgReduction×mult)`, valeur config ex. 499 @{lvl50,mult180}). C'est le
    # slot additif @+0x10 côté DÉFENSEUR : le natif l'ajoute à la BASE **PRÉ-perçage** (comme l'additif
    # ATTAQUANT #75 ; `CalculateBaseDamageWithAllModifiers @18102d3f0` NE re-consomme PAS @+0x10) -> DILUÉ
    # par perçage/armure PUIS scalé ×%-list. On garde ces montants dans un canal SÉPARÉ de `additive`
    # (l'additif attaquant) pour les fusionner SANS le pré-scale ×M spécifique au ForAddition défenseur
    # Neuroparasite (cf. prediction.py) : ils sont soustraits de `additive` au merge, appliqués pré-perçage.
    flat_reductions: list[int] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "DamageModifiers":
        """DamageModifiers.Empty @181006370 : additif=0, mult=One, listes vides, pas de pénétration."""
        return cls()


def get_multiplier_from_damage_bonus(bonus_pct: int) -> float:
    """DamageCalculations.GetMultiplierFromDamageBonus @181005210 :
        b ≥ 1  → 1 + b/100      (bonus)
        b < 1  → 1 − |b|/100     (réduction ; b ≤ 0)."""
    if bonus_pct < 1:
        return 1.0 - (-bonus_pct) / 100.0
    return 1.0 + bonus_pct / 100.0


def add_modifier(acc: DamageModifiers, eb: EffectBonus) -> None:
    """DamageModifiers.Add @181005f10 — intègre UNE contribution d'effet dans l'accumulateur.
      • Addition/Subtraction  → additif ±= value (plat)
      • PercentIncrease/Decrease → %-list.Add((GetMultiplierFromDamageBonus(±value), cap))
      • detail-list .Add (bookkeeping)
    (Piercing/Override = axes séparés — non intégrés au scalaire dégât ici.)"""
    if eb.kind == "Addition":
        acc.additive += eb.value
    elif eb.kind == "Subtraction":
        if eb.owner_is_caster:
            acc.additive -= eb.value            # ATTAQUANT : base pré-perçage (stat-debuff #49/#64)
        else:
            acc.flat_reductions.append(eb.value)  # DÉFENSEUR : plat POST-%-list (Nightshroud @180f5bff0)
    elif eb.kind in ("PercentIncrease", "PercentDecrease"):
        pct = eb.value if eb.kind == "PercentIncrease" else -eb.value
        acc.pct_list.append((get_multiplier_from_damage_bonus(pct), eb.cap))
    elif eb.kind == "Piercing":
        acc.extra_pierce += eb.value            # axe perçage (@0x20) — pas le scalaire dégât
    elif eb.kind == "ArmorPenetration":
        acc.armor_penetration += eb.value       # axe armure (@0x28)
    elif eb.kind == "IgnoreArmor":
        acc.ignore_armor = True                 # ignore-armure totale → armor_eff = 0
    elif eb.kind == "PercentSubtractionCapped":
        acc.capped_reductions.append((eb.value, eb.cap))   # −min(pct%×dmg, cap), appliqué post-mods
    acc.details.append(eb)


def apply_capped_modifiers(value: int, mods: DamageModifiers) -> int:
    """DamageCalculations.ApplyCappedModifiers @181000020 — réducteur du `%-list` :
        POUR CHAQUE (mult, cap) : value = value × mult   [Fix64, PAS d'arrondi int intermédiaire]
                                  si cap : value = clamp(round(value), −cap, +cap)
        retour : round(value)   [conversion int UNIQUE en fin de chaîne]
    ⚠ COMPOSITION SANS ARRONDI INTERMÉDIAIRE (#98, MESURÉ live) : le natif compose les entrées %-list
    en Fix64 (fractionnaire) et ne matérialise l'int qu'UNE fois — un arrondi PAR entrée divergeait de
    ±1/coup dès 2 mults (u80 darkaTerminator, CrushingStrike×Élévation = ×1.5×1.5 : bouts natifs per-coup
    3980/5969 = round(1769×2.25)/round(2653×2.25) ; round-par-entrée donnait 3981/5970). Une entrée
    CAPÉE matérialise (clamp sur int) à sa position — sans consommateur actuel (les pct portés sont tous
    cap=None) ; mono-mult : round(v×m) STRICTEMENT inchangé (tous les cas validés ×1.25/×1.33/×0.7/×0.25
    préservés bit-exact). L'`additif` plat est appliqué à part — cf. apply_all_modifiers.

    ⚠ CONVERSION int DÉFÉRÉE AU CALLER : `ApplyCappedModifiers @181000020` renvoie un **Fix64** ; liste %-list
    VIDE -> valeur **INCHANGÉE (fractionnaire)** — l'arrondi/troncature UNIQUE est fait par l'appelant
    (prédiction: Round ; COMBAT: op_Explicit=troncature, cf. `apply_all_modifiers`/`CalculateAbilityDamage`
    @18102cb50). C'est nécessaire depuis que `get_damage_with_piercing` renvoie le fractionnaire du perçage
    (#111) : floorer/arrondir ici perdrait le fractionnaire AVANT le point de conversion natif. Liste NON
    vide -> on matérialise l'int UNE fois (round, #98 : compose sans arrondi intermédiaire)."""
    v = float(value)
    if not mods.pct_list:
        return v                      # %-list VIDE -> Fix64 INCHANGÉ (@181000020 ne touche pas la valeur) ;
                                      # la conversion int est faite au caller (prédiction Round / COMBAT
                                      # op_Explicit troncature) — nécessaire depuis le perçage fractionnaire #111.
    for mult, cap in mods.pct_list:
        v = v * mult
        if cap is not None:
            v = float(max(-cap, min(cap, round(v))))
    return round(v)                   # %-list NON vide -> matérialise l'int UNE fois (round, #98 : compose
                                      # sans arrondi intermédiaire) ; la troncature/round finale du caller = no-op.


def apply_all_modifiers(value: int, mods: DamageModifiers) -> int:
    """Combinaison %-list + additif — ORDRE TRANCHÉ par RE de `CalculateBaseDamageWithAllModifiers`
    @18102d3f0 : ApplyCappedModifiers(%-list attaquant) → (%-list défenseur) → ApplyAdditive(additif
    attaquant @+0x10) → (additif défenseur) → override défenseur éventuel. Donc %-list PUIS additif,
    plancher >= 0 (Fix64.Max(dmg, 0)). ⚠ PRÉDICTION d'attaque : l'additif s'applique UNE FOIS PAR
    ATTAQUE sur le total agrégé (cf. get_attack_prediction §5, call-sites PredictAttackRaw AVANT la
    boucle d'events) — cette fonction combinée reste pour le chemin COMBAT (valeur tirée)."""
    v = apply_capped_modifiers(value, mods)
    if mods.additive:
        v = v + mods.additive
    # COMBAT : conversion int finale = TRONCATURE (`op_Explicit`, `CalculateAbilityDamage @18102cb50`),
    # PAS round. `apply_capped_modifiers` a déjà matérialisé l'int si %-list non vide (troncature = no-op) ;
    # %-list vide -> `v` reste le fractionnaire du perçage -> troncature = floor natif du dégât tiré.
    v = int(v)
    # ⚠ Les réductions DYNAMIQUES CAPÉES du DÉFENSEUR (GuardianOrganism) ne sont PLUS appliquées ici :
    # `CurrentDamage` du natif = la valeur UNIQUE post-mods (le dégât TIRÉ), donc en COMBAT la soustraction
    # se fait PAR VALEUR TIRÉE (cf. `apply_capped_reductions`, appelé dans `_run_hits` APRÈS le tirage), PAS
    # sur les bornes min/max (les appliquer per-borne = 33%×min ≠ 33%×max rétrécit la plage de roll -> désync
    # RNG, #91). La PRÉDICTION (min/max) les STRIPPE aussi (`predict_attack_raw`) et applique un FLAT (D=centre).
    return max(0, v)


def capped_reduction_flat(reference: int, capped_reductions) -> int:
    """Montant FLAT total de réduction CAPÉE du DÉFENSEUR (ex. GuardianOrganism_DamageReduction @180f4c630 :
    `ForSubtraction(Min(PercentageOf(CurrentDamage, pct), cap))`). Le natif PRÉ-ÉVALUE le défender-mod en
    SCALAIRE UNIQUE (`CalculateBaseDamageWithAllModifiers @18102d3f0` reçoit min ET max le MÊME montant) où
    `CurrentDamage` = D = le CENTRE du dégât post-perçage/mods (= (lo+hi)/2 des bornes réduites) — CONFIRMÉ LIVE
    (#91 : Tyrant Guard, D≈centre -> flat≈178 soustrait IDENTIQUE à chaque coup, PAS 33%×valeur-tirée). Ce flat
    est le MÊME pour tous les coups d'un même type (non-crit/crit) et se soustrait de chaque valeur tirée.
    `reference` = D (le centre, possiblement fractionnaire .5) ; `PercentageOf` en Fix64 TRONQUE (confirmé LIVE
    #91 : D->flat=177=floor, PAS 178=round). = Sum min(trunc(pct%×reference), cap). Liste vide -> 0 (combat
    sans réduction capée = BIT-EXACT inchangé)."""
    flat = 0
    for _pct, _cap in capped_reductions:
        _r = int(reference * _pct / 100.0)          # Fix64 : troncature (PAS round)
        if _cap is not None:
            _r = min(_r, _cap)
        flat += _r
    return flat


def build_attacker_modifiers(effect_bonuses: list[EffectBonus | None]) -> DamageModifiers:
    """DamageCalculations.CalculateAttackerModifiersForPrediction @181000590 — boucle sur `param_5`
    (= les EFFETS actifs de l'unité, §17.8) et accumule chaque contribution. `effect_bonuses` =
    [effet.CreateEffectDamageBonusForAttack(...) pour chaque effet actif] (None = pas de contribution)."""
    acc = DamageModifiers.empty()
    for eb in effect_bonuses:
        if eb is not None:
            add_modifier(acc, eb)
    return acc


def calculate_modifiers_from_stat_modifications(stat_component, negate: bool = False) -> list[EffectBonus]:
    """`DamageCalculations.CalculateModifiersFromStatModifications @181004380` — convertit les
    **modifications per-source** d'un `StatComponent` (le dict `ValueModification`, cf. entities/stats.py)
    en `EffectBonus` PLATS. `param_3`=`negate` fixe le SIGNE : `True` → `ForSubtraction` (**DEBUFF** :
    retire la modification), `False` → `ForAddition`. Une contribution par source (KeyValuePair du dict).
    Garde native `if get_CurrentValue() != Initial(+0x48)` : liste vide si le stat n'a aucune modification.

    ⚠ **PRÉDICTION-ONLY** — appelé UNIQUEMENT par `CalculateAttackerModifiersForPrediction @181000cac`
    et `CalculateDefenderModifiersForPrediction @181003066` (xref confirmé), JAMAIS par le combat
    (`CalculateAbilityDamage`/`HitDamage.GetDamage` dealent la base PLEINE = Current). C'est le
    mécanisme du gap #49 : la PRÉDICTION ramène la base `Current→Initial` en soustrayant les
    stat-modifications (debuff), le COMBAT garde Current. Duck-typé sur `StatComponent`
    (`.get_current_value()`, `.initial`, `.modification.per_source`)."""
    if stat_component is None:
        return []
    if stat_component.get_current_value() == stat_component.initial:   # aucune modification -> rien
        return []
    make = for_subtraction if negate else for_addition
    return [make(True, int(amount))
            for amount in stat_component.modification.per_source.values() if amount]


def build_defender_modifiers(effect_bonuses: list[EffectBonus | None]) -> DamageModifiers:
    """DamageCalculations.CalculateDefenderModifiersForPrediction @181002c30 — SYMÉTRIQUE de l'attaquant :
    itère les effets de la CIBLE et accumule chaque `CreateEffectDamageMalusForDefense` (slot 0x1a) →
    DamageModifiers (%-list de réduction, typiquement PercentDecrease). Même accumulateur que l'attaquant
    (`add_modifier`) ; appliqué au dégât reçu via `apply_all_modifiers`. (Le natif ajoute aussi 2 additifs
    @+0x20/@+0x28 = maluses 0x19/0x1b — non portés ici tant qu'aucun effet de la famille ne les fournit.)"""
    acc = DamageModifiers.empty()
    for eb in effect_bonuses:
        if eb is not None:
            add_modifier(acc, eb)
    return acc


# ─── Leaves positionnels (chacun = un `EffectBonus` selon la position/terrain) ──────────────────────

def calculate_elevation_bonus_modifier(
        attacker_elevation: int, target_elevation: int, elevation_pct: int,
        attacker_or_target_has_no_elev_effect: bool = False) -> EffectBonus | None:
    """CalculateElevationBonusModifier @181003ea0 : +ElevationPercentage (config) si la tuile de
    l'attaquant est PLUS HAUTE que celle de la cible. Sauté si l'attaquant OU la cible a l'effet
    0x423 (`attacker_or_target_has_no_elev_effect`). Renvoie None sinon."""
    if attacker_or_target_has_no_elev_effect:
        return None
    if attacker_elevation > target_elevation:
        return EffectBonus("PercentIncrease", elevation_pct, owner_is_caster=True)
    return None


def calculate_ranged_in_melee_reduction(
        should_apply: bool, ranged_in_melee_reduction_pct: int) -> EffectBonus | None:
    """CalculateRangedInMeleeReduction @181004700 → ShouldApplyRangedInMelee @181005810 :
    si un attaquant RANGED (trait 0xb) est adjacent à un ennemi melee-able → −RangedInMeleeReduction
    (config). `should_apply` = résultat de ShouldApplyRangedInMelee (adjacence résolue en amont)."""
    if should_apply:
        return EffectBonus("PercentDecrease", ranged_in_melee_reduction_pct, owner_is_caster=True)
    return None


def calculate_trench_reduction(
        target_on_trench_adjacent: bool, trench_reduction_pct: int) -> EffectBonus | None:
    """CalculateTrenchReduction @181004830 : cible sur tuile trench + conditions d'adjacence →
    −TrenchReduction (config). `target_on_trench_adjacent` = conditions résolues en amont."""
    if target_on_trench_adjacent:
        return EffectBonus("PercentDecrease", trench_reduction_pct, owner_is_caster=True)
    return None
