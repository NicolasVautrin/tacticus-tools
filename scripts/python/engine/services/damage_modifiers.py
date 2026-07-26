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
  • `DamageModifiers`                                    (struct)        IdunBattle.Core.Services.DamageModifiers$$Empty / Add@181005f10
  • `IdunBattle.Core.Services.DamageCalculations$$GetMultiplierFromDamageBonus      (1 ± pct/100)
  • `IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers      (réducteur : v=clamp(round(v×mult),±cap))
  • `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction  (builder = boucle sur param_5)
  • leaves positionnels : IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier /
    IdunBattle.Core.Services.DamageCalculations$$CalculateRangedInMeleeReduction / IdunBattle.Core.Services.DamageCalculations$$CalculateTrenchReduction
  • config `IdunBattle.Core.Services.DamageCalculations$$Init` : ELEVATION_BONUS_PCT / EFFECT_NO_ELEVATION (section Damage
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

from . import fix64 as _fx
from .effect_bonus import EffectBonus
from .. import weights as _weights

# Config `DamageCalculations` (section Damage de la BattleConfiguration) — le natif la charge via
# `IdunBattle.Core.Services.DamageCalculations$$Init`. Ces constantes appartiennent au port de DamageCalculations (ce
# module), consommees a l'identique par la PREDICTION (playbook) ET le COMBAT (runner) — pas de fork.
_DMG_CFG: dict = _json.loads(_weights.DEFAULT_BC.read_text(encoding="utf-8")).get("Damage", {}) \
    if _weights.DEFAULT_BC.exists() else {}
ELEVATION_BONUS_PCT: int = int(_DMG_CFG.get("ElevationBonus", 50))   # IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier
# TRENCH (IdunBattle.Core.Services.DamageCalculations$$CalculateTrenchReduction) : config native = pourcentage NEGATIF (=-50) -> le port passe
# la MAGNITUDE a calculate_trench_reduction (kind PercentDecrease -> add_modifier flippe le signe -> x0.5).
# PREDICTION (playbook) ET COMBAT (runner, #181) l'utilisent -- source unique ICI (pas de fork), comme
# ELEVATION_BONUS_PCT.
TRENCH_PCT: int = abs(int(_DMG_CFG.get("TrenchReductionPercentage", -50)))   # IdunBattle.Core.Services.DamageCalculations$$CalculateTrenchReduction
# Profils de degat qui IGNORENT la reduction Trench (idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$IgnoreTrenchReduction = List.Contains(
# staticList, profile)). Liste native = config STATIQUE hors section Damage de la BC (aucune cle ici) ->
# defaut VIDE (aucun profil exempte) tant que non RE'd/exposee (#125). A raffiner si un cas live montre une
# NON-reduction sur-trench pour un profil donne.
_TRENCH_IGNORED_PROFILES: "frozenset[str]" = frozenset()
# EFFECT_NO_ELEVATION (= int(EffectType.Trench), 1059) est défini EN BAS de module : l'import `entities.effect_type`
# déclenche `entities/__init__` -> effects -> re-import de CE module (cycle) ; le placer après les défs le rompt (#158).


@dataclass
class DamageModifiers:
    """Accumulateur `DamageModifiers` (struct ~0x40 : additif@+0x10, %-list@+0x18, mult@+0x30=1,
    detail@+0x38). `pct_list` = liste de `(mult, cap)` (mult=1±pct/100 ; cap=None si non plafonné)."""
    additive: float = 0.0
    pct_list: list[tuple[float, int | None]] = field(default_factory=list)
    multiplicative: float = 1.0
    details: list[EffectBonus] = field(default_factory=list)
    # axe ARMURE/PERÇAGE (champs du DamageModifiers natif lus par CalculateBaseDamageWithAllModifiers
    # IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers → GetBaseDamageWithFixedPiercedArmor) — distinct du scalaire dégât (additif/%-list) :
    extra_pierce: int = 0          # @0x20 : pierce_eff = clamp(pierce + extra_pierce, 0, 100)
    armor_penetration: int = 0     # @0x28 : armor_eff = max(FixedArmor − armor_penetration, 0)
    ignore_armor: bool = False     # ignore-armure totale → armor_eff = 0 (pénétration ≥ armure)
    # Réductions DYNAMIQUES CAPÉES (défenseur, ex. GuardianOrganism) : liste de (pct, cap) — soustrait
    # `min(pct% × dégât_courant, cap)` du dégât APRÈS %-list+additif (CurrentDamage). Distinct du %-list
    # (multiplicatif) : c'est une ForSubtraction dont le montant dépend du dégât courant, plafonné.
    capped_reductions: list[tuple[int, int | None]] = field(default_factory=list)
    # Additifs DÉFENSEUR de SOUSTRACTION (ex. Nightshroud_DmgReduction IdunBattle.Entities.Effects.Loki.Nightshroud_DmgReduction_Effect$$CreateDamageDefenseModifier : `ForSubtraction(
    # OwnerIsTarget, ConfigVar(0x12)=dmgReduction×mult)`, valeur config ex. 499 @{lvl50,mult180}). C'est le
    # slot additif @+0x10 côté DÉFENSEUR : le natif l'ajoute à la BASE **PRÉ-perçage** (comme l'additif
    # ATTAQUANT #75 ; `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` NE re-consomme PAS @+0x10) -> DILUÉ
    # par perçage/armure PUIS scalé ×%-list. On garde ces montants dans un canal SÉPARÉ de `additive`
    # (l'additif attaquant) pour les fusionner SANS le pré-scale ×M spécifique au ForAddition défenseur
    # Neuroparasite (cf. prediction.py) : ils sont soustraits de `additive` au merge, appliqués pré-perçage.
    flat_reductions: list[int] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "DamageModifiers":
        """IdunBattle.Core.Services.DamageModifiers$$Empty : additif=0, mult=One, listes vides, pas de pénétration."""
        return cls()


def get_multiplier_from_damage_bonus(bonus_pct: int) -> float:
    """IdunBattle.Core.Services.DamageCalculations$$GetMultiplierFromDamageBonus :
        b ≥ 1  → 1 + b/100      (bonus)
        b < 1  → 1 − |b|/100     (réduction ; b ≤ 0)."""
    if bonus_pct < 1:
        return 1.0 - (-bonus_pct) / 100.0
    return 1.0 + bonus_pct / 100.0


def add_modifier(acc: DamageModifiers, eb: EffectBonus) -> None:
    """IdunBattle.Core.Services.DamageModifiers$$Add — intègre UNE contribution d'effet dans l'accumulateur.
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
            acc.flat_reductions.append(eb.value)  # DÉFENSEUR : plat PRÉ-perçage (Nightshroud IdunBattle.Entities.Effects.Loki.Nightshroud_DmgReduction_Effect$$CreateDamageDefenseModifier, cf. flat_reductions)
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


def apply_capped_modifiers(value, mods: DamageModifiers) -> "_fx.Fix64":
    """IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers — réducteur du `%-list`, ARITHMÉTIQUE Fix64
    EXACTE (#30a) :
        POUR CHAQUE (mult, cap) : value = Fix64Mul(value, mult_raw)   [mul TRONQUANT, pas d'arrondi]
                                  si cap : value = Clamp(Round(value, AwayFromZero), −cap, +cap)
        retour : Fix64 FRACTIONNAIRE (`.raw` exact) — AUCUNE matérialisation int ici.
    `mult_raw` = reconstruction exacte du raw natif depuis le float stocké (`mult_raw_from_float`,
    cf. `IdunBattle.Core.Services.DamageCalculations$$GetMultiplierFromDamageBonus` = `One ± Div(FromInt(|pct|), FromInt(100))`).

    ⚠ COMPOSITION SANS ARRONDI INTERMÉDIAIRE pour les entrées NON capées (#98, MESURÉ live : u80
    darkaTerminator ×1.5×1.5 → bouts natifs per-coup 3980/5969 = floor(1769×2.25)/floor(2653×2.25) ;
    un Round PAR entrée donnerait 2653.5→2654→3981 ≠ 3980 natif). Le décompilé IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers montre un
    `Round(·,1)+Clamp` par entrée — la mesure #98 prouve que les bonus multi-mults validés ne passent
    PAS chacun par ce Round (fold côté data : Multiplier slot / entrée unique) ; on garde la sémantique
    MESURÉE : mul tronquant par entrée, Round+Clamp UNIQUEMENT sur entrée capée (mirror décompile,
    aucun consommateur actuel : tous les pct portés sont cap=None).

    ⚠ MATÉRIALISATION %-list = `Round(·, mode 1)` EN FIN D'APPEL quand la liste est NON vide
    (VALIDÉ live : ThunderousAssault combat 6948 = Round(6947.x), floor→6947 régresse ; tous les
    single-mult historiques = Round(v×m) bit-exact). Liste VIDE → valeur INCHANGÉE (fractionnaire,
    perçage #111) : la conversion est alors faite au caller (prédiction : Round des bornes ;
    COMBAT : op_Explicit=floor du dégât tiré, `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`). Le retour est
    toujours un Fix64 (`.raw` exact — intégral si matérialisé)."""
    v_raw = _fx.from_number(value)
    if not mods.pct_list:
        return _fx.Fix64(v_raw)
    for mult, cap in mods.pct_list:
        v_raw = _fx.mul(v_raw, _fx.mult_raw_from_float(mult))
        if cap is not None:
            cap_raw = _fx.from_int(cap)
            v_raw = max(-cap_raw, min(cap_raw, _fx.round_raw(v_raw, 1)))
    return _fx.Fix64(_fx.round_raw(v_raw, 1))


def apply_all_modifiers(value: int, mods: DamageModifiers, round_materialize: bool = False) -> int:
    """Combinaison %-list + additif — ORDRE TRANCHÉ par RE de `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers : ApplyCappedModifiers(%-list attaquant) → (%-list défenseur) → ApplyAdditive(additif
    attaquant @+0x10) → (additif défenseur) → override défenseur éventuel. Donc %-list PUIS additif,
    plancher >= 0 (Fix64.Max(dmg, 0)). ⚠ PRÉDICTION d'attaque : l'additif s'applique UNE FOIS PAR
    ATTAQUE sur le total agrégé (cf. get_attack_prediction §5, call-sites PredictAttackRaw AVANT la
    boucle d'events) — cette fonction combinée reste pour le chemin COMBAT (valeur tirée).

    `round_materialize` (défaut False = comportement HISTORIQUE strictement inchangé) — mirror de
    l'étage MULTIPLICATEUR de `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` (étape 6 = slot 0x10 ->
    `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers` : `v = Fix64.Round(Mul(v,
    multiplier), AwayFromZero=1)`, le `Round` étant IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers+0x148 ; `FixMath.NET.Fix64$$Round` avec flag=1 =
    half-AWAY-FROM-ZERO). Ce `Round` est INCONDITIONNEL dès qu'un `Nullable<DamageModifiers>` HasValue —
    indépendamment du fait que la %-list soit vide (dans `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` le
    `param_7` défenseur est TOUJOURS construit via le slot 0xf, donc l'arrondi passe toujours). Le port
    ne matérialise ce Round que dans `apply_capped_modifiers` **quand la %-list est NON vide** ; %-list
    VIDE -> la valeur reste fractionnaire et le caller la TRONQUE ici (`FixMath.NET.Fix64$$op_Explicit =
    `raw >> 32` = floor). => divergence de ±1 quand le produit du perçage tombe juste sous un entier
    (le Fix64 de `pierce/100` est légèrement < à la fraction exacte : `Div(70,100)` = 0.6999999999534).

    **MESURÉ LIVE — 2 datapoints, famille ABILITY amount-mode** (probe_deathnova, PutridExplosion sur
    ultraTitus armure 1850, profil Toxic pierce 70) : base 200 -> Fix64 139.99999999068 -> natif **140**
    (floor donnerait 139) ; base 201 -> 140.69999999 -> natif **141** (floor 140). Corroboré par le DoT
    feu, qui matérialise DÉJÀ par `int(round(...))` dans `execute_direct` (1908 x 25% = 476.99999999 ->
    live 477).

    **#131 — les BORNES de l'ATTAQUE NORMALE l'activent AUSSI** (`damage_ops.execute::_reduced_bounds`) :
    leurs cellules min/max ne sont pas un calcul propre au combat mais la sortie de
    `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` (slot 4
    `IdunBattle.Core.Services.DamagePrediction$$PredictAttack`, cache), résolue par le slot 8
    `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` — MÊME fonction native
    que la PRÉDICTION, donc MÊME matérialisation. Mesuré live per-COUP (probe_131) sur 2 régimes
    indépendants : Plasma p=80 (cellules [1800,2700] tronquées vs [1800,2701] arrondies -> live 6/6
    arrondi) et Power p=40 3 coups sans buff ([899,1350] vs [900,1350] -> live 17/18 arrondi, le 18ᵉ
    étant le coup létal écrêté aux PV restants). L'ancien verdict « live-validé bit-exact AVEC la
    troncature » venait de régimes NON discriminants (ex. p=65 sur base 2813 : floor == round).

    ⚠ RESTENT tronquants (résidu nommé, chiffré, hors #131) : ability bounds-mode famille ATTACK
    (`damage_ops:execute_ability_attack::_reduce` quand `is_attack_damage_op=True`), `execute_normal_like`,
    `additional_hits`. Ils passent par le MÊME `PredictAttackRaw` natif (avec `predefined`) et sont donc
    suspects du même ±1 — mais aucun n'a été confronté live sur un régime discriminant : campagne de
    mesure propre à faire avant de basculer."""
    v_raw = apply_capped_modifiers(value, mods).raw
    if mods.additive:
        v_raw = v_raw + _fx.from_number(mods.additive)
    # COMBAT : conversion int finale = TRONCATURE (`op_Explicit`, `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`),
    # PAS round. Fix64 EXACT de bout en bout (#30a) : `v_raw` porte le fractionnaire du perçage/%-list
    # sans bruit float -> `to_int` (floor) = le natif bit-exact.
    # `round_materialize` : l'étage MULTIPLICATEUR natif (Round AwayFromZero) s'intercale AVANT cette
    # troncature -> le Fix64 est alors déjà entier et `to_int` devient un no-op (cf. docstring).
    v = _fx.to_int(_fx.round_raw(v_raw, 1) if round_materialize else v_raw)
    # ⚠ Les réductions DYNAMIQUES CAPÉES du DÉFENSEUR (GuardianOrganism) ne sont PLUS appliquées ici :
    # `CurrentDamage` du natif = la valeur UNIQUE post-mods (le dégât TIRÉ), donc en COMBAT la soustraction
    # se fait PAR VALEUR TIRÉE (cf. `apply_capped_reductions`, appelé dans `_run_hits` APRÈS le tirage), PAS
    # sur les bornes min/max (les appliquer per-borne = 33%×min ≠ 33%×max rétrécit la plage de roll -> désync
    # RNG, #91). La PRÉDICTION (min/max) les STRIPPE aussi (`predict_attack_raw`) et applique un FLAT (D=centre).
    return max(0, v)


def capped_reduction_flat(reference: int, capped_reductions) -> int:
    """Montant FLAT total de réduction CAPÉE du DÉFENSEUR (ex. GuardianOrganism_DamageReduction IdunBattle.Entities.Effects.Loki.GuardianOrganism_DamageReductionEffect$$CreateEffectDamageMalusForDefense :
    `ForSubtraction(Min(PercentageOf(CurrentDamage, pct), cap))`). Le natif PRÉ-ÉVALUE le défender-mod en
    SCALAIRE UNIQUE (`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` reçoit min ET max le MÊME montant) où
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
    """IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction — boucle sur `param_5`
    (= les EFFETS actifs de l'unité, §17.8) et accumule chaque contribution. `effect_bonuses` =
    [effet.CreateEffectDamageBonusForAttack(...) pour chaque effet actif] (None = pas de contribution)."""
    acc = DamageModifiers.empty()
    for eb in effect_bonuses:
        if eb is not None:
            add_modifier(acc, eb)
    return acc


def calculate_modifiers_from_stat_modifications(stat_component, negate: bool = False) -> list[EffectBonus]:
    """`IdunBattle.Core.Services.DamageCalculations$$CalculateModifiersFromStatModifications` — convertit les
    **modifications per-source** d'un `StatComponent` (le dict `ValueModification`, cf. entities/stats.py)
    en entrées **POURCENT** de la %-list. RE complète #194 (corrige la lecture FLAT initiale de #49,
    jamais activée — le gate `apply_stat_mod_debuff` est resté False partout) :
      • garde native `if get_CurrentValue() != Initial(+0x48)` (base+mods ≠ base) → liste vide sinon ;
      • pour chaque KeyValuePair (sourceEntity → IModifier) de `StatComponent.get_Modifications()` :
        `v = IModifier.GetValue()` (montant EFFECTIF, même slot 0 que `IdunBattle.Entities.Components.ValueModification$$GetModificationFromEntity`), **négé** si `param_3`=negate → entrée struct `{cond=1 @0x00, Nullable<int> v @0x20}` ;
      • le champ @0x20 est le slot POURCENT : le caller folde chaque entrée via
        `IdunBattle.Core.Services.DamageCalculations$$GetMultiplierFromDamageBonus` (= `1 + v/100`, `v<1 → 1 − (−v)/100`) puis
        `DamageModifiers.Add` + `List.AddRange(damageModifiers@0x38, entries)` → la %-list, exactement
        comme un `EffectBonus` d'effet. GROUND TRUTH #194 (C2_19, jakhal sur tuile Thorns) :
        modification defense = −50 (tile), face DÉFENSEUR negate=1 → +50 → ×1.5 = ratio oracle/engine
        mesuré 1.5020/1.5003 EXACT.

    Faces natives (xref IdunBattle.Core.Services.DamageCalculations$$CalculateModifiersFromStatModifications) : DÉFENSEUR `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction+0x436`
    = DefenseComponent (stat 3) de la CIBLE, negate=**1** (PORTÉ, #194/#197) ; ATTAQUANT
    `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction+0x71c` = AttackComponent (stat 0) de l'attaquant,
    negate=**0**, gated `plStack_290 != null` + interface slot 3 (`DAT_1831b7f78`) — gate NON élucidé
    et prouvé INERTE sur le chemin normal-attack (#49 bit-exact sans lui) → NON câblé (cf. tâche RE
    dédiée). ⚠ Les 2 xref IdunBattle.Core.Services.DamageCalculations$$CalculateModifiersFromStatModifications sont les builders nommés « ForPrediction », mais ceux-ci sont
    PARTAGÉS prédiction+combat (misnomer — invoqués par delegate via `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`
    slot 0xf), donc le fold DÉFENSEUR s'applique AUSSI au COMBAT réel (MESURÉ LIVE #197 : dégât réel sur
    occupant Thorns = ×1.5, impossible sous ×1.0). Foldé pour les DEUX faces DANS
    `build_defender_modifiers_from_effects` (fin du fork). Duck-typé sur `StatComponent`
    (`.get_current_value()`, `.initial`, `.modification.per_source`)."""
    if stat_component is None:
        return []
    if stat_component.get_current_value() == stat_component.initial:   # aucune modification -> rien
        return []
    sign = -1 if negate else 1
    return [EffectBonus("PercentIncrease", sign * int(amount), owner_is_caster=True)
            for amount in stat_component.modification.per_source.values() if amount]


def build_defender_modifiers(effect_bonuses: list[EffectBonus | None]) -> DamageModifiers:
    """IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction — SYMÉTRIQUE de l'attaquant :
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
    """IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier : +ElevationPercentage (config) si la tuile de
    l'attaquant est PLUS HAUTE que celle de la cible. Sauté si l'attaquant OU la cible a l'effet
    0x423 (`attacker_or_target_has_no_elev_effect`). Renvoie None sinon."""
    if attacker_or_target_has_no_elev_effect:
        return None
    if attacker_elevation > target_elevation:
        return EffectBonus("PercentIncrease", elevation_pct, owner_is_caster=True)
    return None


def calculate_ranged_in_melee_reduction(
        should_apply: bool, ranged_in_melee_reduction_pct: int) -> EffectBonus | None:
    """IdunBattle.Core.Services.DamageCalculations$$CalculateRangedInMeleeReduction → IdunBattle.Core.Services.DamageCalculations$$ShouldApplyRangedInMelee :
    si un attaquant RANGED (trait 0xb) est adjacent à un ennemi melee-able → −RangedInMeleeReduction
    (config). `should_apply` = résultat de ShouldApplyRangedInMelee (adjacence résolue en amont)."""
    if should_apply:
        return EffectBonus("PercentDecrease", ranged_in_melee_reduction_pct, owner_is_caster=True)
    return None


def calculate_trench_reduction(
        attacker_tile, target_tile, target_has_trench_effect: bool,
        attacker_has_indirect_fire: bool, profile_ignored: bool, board,
        trench_reduction_pct: int) -> EffectBonus | None:
    """IdunBattle.Core.Services.DamageCalculations$$CalculateTrenchReduction — mirror COMPLET (gate + apply MONOLITHIQUE, comme le natif).

    Le natif APPLIQUE la reduction PAR DEFAUT (main gate franchi) et ne la SUPPRIME que dans la sous-branche
    IsTrench(attackerTile). Params = handles offline des Tile objects natifs (#183 : le natif ne passe pas de
    "board", chaque Tile PORTE terrain + voisins) :
      - attacker_tile / target_tile : (col,row) | None. attackerTile = tuile candidate (param_4) ;
        target_tile = GetMainTile(world, cible) = la tuile de la cible.
      - target_has_trench_effect    : HasEffect(cible, EffectType.Trench 0x423) — effet de tuile (cible sur/
        adjacente a une tuile Trench, pose par TrenchAbility IdunBattleLogic.Entities.Abilities.Tiles.Loki.TrenchAbility$$CreateBehaviour ; confirme live Arctic_06 u84).
      - attacker_has_indirect_fire  : HasTrait(attaquant, UnitTrait.IndirectFire 0x3ed).
      - profile_ignored             : idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$IgnoreTrenchReduction(profile) (defaut vide #125).
      - board                       : graphe de tuiles (#183). IsTrench(attackerTile) = board.terrain_at ;
        IsNeighbourOf/IsAdjacentTo = are_tiles_adjacent (voisins natifs `native_sym`).

    MAIN GATE : attackerTile present ET cible porte Trench ET profil non-exempte ET
                ( attaquant !IndirectFire  OU  (tuile cible && IsAdjacentTo(attackerTile, tuileCible)) ).
    SOUS-BRANCHE IsTrench(attackerTile) : SUPPRIME la reduction si l'attaquant est SUR une tuile Trench ET
                voisin direct de la cible (IsNeighbourOf) -- OU ligne attackerTile->cible INTEGRALEMENT
                Trench (CASE3 #182 : delegate @LAB_181004bb9 = MovementQuery.GetLinesBetweenTiles, RE'd et
                porte via hexgeo.line ; seule la ligne flag-0 decide, cf. docs/rl/case-182-trench-case3.md).
    Mesures live (board C2_19 bloodMephiston) : HORS-Trench non-adjacent -> APPLIQUE (natif 1002-1506) ;
    SUR-Trench + adjacent -> SKIP (natif 3009-4515) ; ligne-toute-Trench -> SKIP (natif 2006-3010, CASE3)."""
    from .battle_query import are_tiles_adjacent
    # (0) profil exempte (IgnoreTrenchReduction) -> aucune reduction
    if profile_ignored:
        return None
    # (1) MAIN GATE : attackerTile + cible-Trench requis ; IndirectFire -> uniquement si adjacent
    if attacker_tile is None or not target_has_trench_effect:
        return None
    if attacker_has_indirect_fire:
        if target_tile is None or are_tiles_adjacent(attacker_tile, target_tile, board) is not True:
            return None
    # (2) SOUS-BRANCHE IsTrench(attackerTile). board threade en pratique (#183) ; board=None = etat degrade
    #     (RPC boardGraph KO) ou IsTrench est inevaluable -> sous-branche inerte -> APPLY (defaut main-gate),
    #     PAS un skip silencieux du gate (le board EST cense etre present).
    if board is not None and board.terrain_at(*attacker_tile) == "Trench":   # IsTrench(attackerTile)
        if target_tile is None:
            return None                                              # natif GetMainTile==0 -> return empty
        if are_tiles_adjacent(attacker_tile, target_tile, board) is True:    # IsNeighbourOf -> supprime
            return None
        # CASE3 (#182, delegate @LAB_181004bb9 RE'd) : le natif appelle MovementQuery.GetLinesBetweenTiles
        # IdunBattle.Core.Services.MovementQuery$$GetLinesBetweenTiles -> IdunBattle.Core.Services.MovementUtil$$DrawLineBetweenCoordinates/IdunBattle.Core.Services.MovementUtil$$DrawLineBetweenCoordinates (linedraw cube-lerp,
        # endpoints INCLUS) pour tracer DEUX lignes attackerTile->targetMainTile (flag 0/1 = nudge epsilon
        # de tie-break). SEULE la ligne flag-0 (line_A) decide : SUPPRIME la reduction ssi line_A est
        # INTEGRALEMENT Trench. La ligne flag-1 est enumeree par le natif mais son resultat n'affecte JAMAIS
        # la sortie (ses deux issues -- MoveNext-false OU tuile non-Trench -- menent toutes deux a APPLY
        # @LAB_181004e45). hexgeo.line = meme algo Red Blob (cube-lerp + cube_round) ; le nudge epsilon
        # flag-0 n'est PAS reproduit -> tie-break potentiellement different sur une geometrie AMBIGUE (ligne
        # pile entre deux hex), mais un vrai couloir tout-Trench reste robuste. Une tuile de la ligne
        # hors-plateau (terrain_at=None) -> pas "Trench" -> APPLY (conservateur). cf.
        # docs/rl/case-182-trench-case3.md.
        import hexgeo
        line_a = hexgeo.line(attacker_tile, target_tile)             # flag-0 line, attacker->target inclus
        if line_a and all(board.terrain_at(c, r) == "Trench" for (c, r) in line_a):
            return None                                              # line_A tout-Trench -> SKIP
        # sinon APPLY (fall-through)
    # (3) APPLY : -TrenchReductionPercentage%
    return EffectBonus("PercentDecrease", trench_reduction_pct, owner_is_caster=True)


# --- Import différé (bas de module) : rompt le cycle entities/__init__ -> effects -> services.damage_modifiers.
# Placé APRÈS DamageModifiers/apply_all_modifiers pour que la back-edge `effects/__init__` les trouve définies (#158).
from ..entities.effect_type import EffectType  # noqa: E402
EFFECT_NO_ELEVATION: int = int(EffectType.Trench)   # 1059 — effectType gate : elevation coupee si attaquant OU cible porte Trench
