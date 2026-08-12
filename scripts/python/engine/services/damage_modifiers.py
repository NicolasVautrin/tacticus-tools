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
from fractions import Fraction

import engine.services.fix64 as _fx   # module FRERE, pas `from . import` (#270-r4-r2)
# #920-r1 : foyer d'arrondi PARTAGE `IdunBattle.DSL.AAmountFormula$$RoundFix64Result` (#344), le MEME
# que consomme le noeud DSL `entities/formulas.py::PercentageOf`. Forme B (`import X` puis `X.foo()`)
# et NON differe : classe mecaniquement GRATUIT -- `import engine.dsl.base` dans un process FRAIS ne
# fait PAS atterrir `engine.services.damage_modifiers` dans `sys.modules` (6 modules `engine.*`
# charges), donc hisser ne ferme aucun cycle.
import engine.dsl.base as _dsl_base
from .effect_bonus import EffectBonus
from .. import weights as _weights
from .battle_query import are_tiles_adjacent

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
    # #437-r1-r1-r1 — CONVENTION UNIFORME : dans TOUT `DamageModifiers`, `pct_list` est
    # l'accumulateur ATTAQUANT et `pct_list_defender` l'accumulateur DEFENSEUR — quel que soit le
    # BUILDER qui l'a rempli. Le routage se fait a l'entree (`add_modifier`, sur
    # `EffectBonus.native_face`), plus au site de fusion. C'est ce qui permet a un effet porte par
    # la CIBLE d'atterrir cote ATTAQUANT quand le natif le veut (`Terrifying_ExtraDefense`, qui sort
    # par `CreateDamageModifier` -> forwarder `CreateEffectDamageBonusForAttack`), et
    # symetriquement a `Stunned_DamageModifier`, porte par l'ATTAQUANT, d'atterrir cote DEFENSEUR
    # (il sort par `CreateEffectDamageMalusForDefense`, trigger `OwnerIsActor`).
    #
    # #446-r2 — LES ENTREES DU DEFENSEUR, FUSIONNEES DANS L'ACCUMULATEUR DE L'ATTAQUANT, VIVENT A
    # PART. Le natif tient DEUX `Nullable<DamageModifiers>` (`attackModifiers`, `defenseModifiers`)
    # et `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` les
    # consomme en QUATRE etapes ORDONNEES : `ApplyCappedModifiers(attaquant)`,
    # `ApplyCappedModifiers(defenseur)`, puis `CalculateBaseDamageWithModifiers(attaquant)` et
    # `CalculateBaseDamageWithModifiers(defenseur)` -- ces DEUX dernieres portant chacune un
    # `Fix64.Round(., AwayFromZero)`. Le port fusionnait les deux faces dans UNE seule `pct_list`,
    # donc UN seul arrondi : l'arrondi INTERMEDIAIRE entre les deux faces manquait. Mesure #446-r2 :
    # cible sur tuile Thorns (modification de stat DEFENSE -50 -> x1.5 cote DEFENSEUR) sans bonus
    # d'elevation (donc face ATTAQUANT a 1.0) -- natif 1302 contre 1299 pour le port sur 3 coups.
    # La PREDICTION fusionne (elle n'a qu'un `mods`) -> ce champ porte la face DEFENSEUR ; le COMBAT
    # garde ses deux appels distincts (`apply_pierce_and_modifiers(att_mods)` puis
    # `apply_all_modifiers(def_mods)`) et n'utilise donc PAS ce champ.
    pct_list_defender: list[tuple[float, int | None]] = field(default_factory=list)
    # `Multiplier@0x30` — le slot que `IdunBattle.Core.Services.DamageModifiers$$Add` (surcharge
    # 1-ARGUMENT) multiplie, et que le DERNIER etage de `CalculateBaseDamageWithAllModifiers`
    # consomme via `CalculateBaseDamageWithModifiers` (slot 0x10), donc APRES un `Fix64.Round`.
    # #462-r4a : le port ne l'alimentait PAS (champ mort) et fusionnait tout dans la `%-list`, ce
    # qui perdait exactement cet arrondi. Seules les MODIFICATIONS DE STAT y entrent
    # (`from_stat_mod`) ; les %-list d'effets et les feuilles positionnelles restent dans la liste.
    multiplicative: float = 1.0
    # Le `Multiplier@0x30` de la face DEFENSEUR, quand elle est fusionnee dans CET accumulateur
    # (prediction et COMBAT). Deux slots distincts parce que le natif les consomme en DEUX etages
    # ORDONNES : `CalculateBaseDamageWithModifiers(attackModifiers.Multiplier)` PUIS
    # `(defenseModifiers.Multiplier)`, chacun avec son propre `Round`.
    multiplicative_defender: float = 1.0
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
        mult = get_multiplier_from_damage_bonus(pct)
        # #437-r1-r1-r1 -- ROUTAGE PAR FACE. `pct_list`/`multiplicative` = l'accumulateur
        # ATTAQUANT (`attackModifiers`), `pct_list_defender`/`multiplicative_defender` =
        # l'accumulateur DEFENSEUR. Cette convention vaut DESORMAIS dans TOUT `DamageModifiers`,
        # y compris celui que rend le builder defenseur -- avant, ce dernier entassait tout dans
        # `pct_list` et le site de fusion DEPLACAIT en bloc, ce qui rendait la face structurellement
        # indicible et forcait a la deduire du builder. Le natif, lui, ne la deduit pas : il verse
        # dans l'accumulateur du builder dont le SLOT a ete invoque (cf. `EffectBonus.native_face`).
        to_def = (eb.native_face == "defender")
        if eb.from_stat_mod:
            # #462-r4a : canal `Multiplier@0x30` (surcharge 1-ARG de `DamageModifiers$$Add`), pas la
            # LISTE. Le natif y route le PRODUIT des modifications de stat -- ici on multiplie
            # entree par entree, ce qui est le MEME produit (`GetMultiplierFromDamageBonus`
            # surcharge LISTE = `x = One ; foreach -> x = Mul(x, m)`).
            if to_def:
                acc.multiplicative_defender *= mult
            else:
                acc.multiplicative *= mult
        elif to_def:
            acc.pct_list_defender.append((mult, eb.cap))
        else:
            acc.pct_list.append((mult, eb.cap))
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
    return apply_pct_entries(value, mods.pct_list)


def apply_pct_entries(value, entries) -> "_fx.Fix64":
    """Le CORPS de `apply_capped_modifiers`, sur une liste d'entrees EXPLICITE. Extrait (#446-r2)
    pour que la face DEFENSEUR fusionnee (`DamageModifiers.pct_list_defender`) traverse EXACTEMENT
    le meme etage que la face ATTAQUANT, dans un appel SEPARE.

    ⚠ #437-r1-r1 -- ce que cette fonction mirroire N'EST PAS `ApplyCappedModifiers`. Ce foyer-la
    arrondit PAR ENTREE et inconditionnellement, donc y decouper une liste en deux appels serait
    ARITHMETIQUEMENT NEUTRE ; et sa liste `@0x18` n'est alimentee par AUCUN chemin porte (mesure
    au capteur `effect-bonus-trace` : 0 sur 199 et 0 sur 693, deux montages). Ce qui est mirroire
    ici est l'accumulateur `Multiplier@0x30` d'UNE face : compose sans arrondi entre ses entrees,
    puis materialise UNE fois -- exactement `CalculateBaseDamageWithModifiers` (etape 3 ou 4 de
    `CalculateBaseDamageWithAllModifiers`), dont l'appel est INCONDITIONNEL par `Nullable` non nul.
    C'est aussi ce qui explique #98 (deux `x1.5` sur la MEME face composes sans arrondi : meme
    accumulateur, un seul `Round`) sans contredire le decompile."""
    v_raw = _fx.from_number(value)
    if not entries:
        return _fx.Fix64(v_raw)
    for mult, cap in entries:
        v_raw = _fx.mul(v_raw, _fx.mult_raw_from_float(mult))
        if cap is not None:
            cap_raw = _fx.from_int(cap)
            v_raw = max(-cap_raw, min(cap_raw, _fx.round_raw(v_raw, 1)))
    return _fx.Fix64(_fx.round_raw(v_raw, 1))


def calculate_base_damage_with_modifiers(damage, multiplier: float = 1.0) -> "_fx.Fix64":
    """`IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers` (slot 0x10) --
    l'etage MULTIPLICATEUR (`DamageModifiers.Multiplier@0x30`), mirror LU du decompile :

        x = Fix64.op_Multiply(baseDamage, multiplier)
        if x <= Fix64.Zero                     : return Fix64.Zero      # statics+0x28
        if Fix64.Zero < x && x < Fix64.One     : return Fix64.One       # statics+0x20
        return Fix64.Round(x, AwayFromZero)

    ⚠ Ce que ce mirror APPORTE, et c'est TOUT l'objet de #446-r2 : `CalculateBaseDamageWithAllModifiers`
    l'appelle DEUX FOIS -- une fois avec le multiplicateur de l'ATTAQUANT, une fois avec celui du
    DEFENSEUR -- et l'appel est INCONDITIONNEL des que le `Nullable<DamageModifiers>` correspondant
    HasValue, donc **meme quand le multiplicateur vaut 1**. C'est cet arrondi-la, sur un
    multiplicateur NEUTRE, qui MATERIALISE la sortie fractionnaire du percage avant que le
    multiplicateur de l'autre face ne s'applique.

    Mesure #446-r2 (`MC1_67`, `templAggressor` -> `astraBullgryn` sur tuile Thorns) : percage
    `1445 x fix(0.20)` = `288.99999993` (Fix64, JUSTE sous 289) ; face attaquant a 1.0 ->
    `Round(288.99999993) = 289` ; face defenseur a 1.5 (modification de stat DEFENSE -50, negee) ->
    `Round(289 x 1.5) = Round(433.5) = 434`. Sans l'arrondi intermediaire on obtient
    `Round(288.99999993 x 1.5) = Round(433.49999990) = 433` -- le `-1` par coup, `-3` sur 3 coups.

    `multiplier` reste un float (format `pct_list` du port) : `mult_raw_from_float` reconstruit le
    raw natif EXACT pour tout pourcentage entier (cf. sa docstring)."""
    x = _fx.mul(_fx.from_number(damage), _fx.mult_raw_from_float(multiplier))
    if x <= 0:
        return _fx.Fix64(0)
    if x < _fx.ONE:
        return _fx.Fix64(_fx.ONE)
    return _fx.Fix64(_fx.round_raw(x, 1))


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

    **CAMPAGNE HeavyGravCannon (2026-07-26) — l'ability bounds-mode famille ATTACK BASCULE AUSSI** (`damage_ops:execute_ability_attack`,
    `_round_mat = True` inconditionnel). Sa campagne discriminante a enfin pu être faite : sur ce vecteur
    la valeur finale n'est FRACTIONNAIRE que si les DEUX %-list sont vides (sinon `ApplyCappedModifiers`
    arrondit déjà en fin d'appel) ET si la branche PERÇAGE du plancher `max(0, d − armure, d × pierce%)`
    l'emporte — régime que le canal perçage de `HeavyGravCannonEffect` (+extraPierceRatio=60 sur un
    profil à PiercingRatio=1) fabrique enfin. MESURE (probe_hgc_1291 `--case round`, SentinelDirectives,
    14 casts, 2 régimes d'armure) : armure 2411 → d=4976 exact 3305.59 (floor 3305 / round 3306) live
    **3306** et d=4812 exact 3205.55 (floor 3205 / round 3206) live **3206** ; les 12 autres casts ont
    une partie fractionnaire < .5 (ou nulle) et donnent floor == round == live. ⇒ live == arrondi 14/14,
    == troncature 12/14, les 2 écarts tombant EXACTEMENT sur frac ≥ .5 (un additif oublié aurait donné un
    +1 systématique). Les validations bit-exact « avec la troncature » de ce vecteur portaient toutes sur
    des régimes NON discriminants (valeur entière).

    **R6 (2026-07-28) — `execute_normal_like` ET `additional_hits` BASCULENT AUSSI** : les trois
    derniers vecteurs COMBAT arrondissent donc désormais, comme le natif. Ce n'étaient pas trois lois
    mais UNE SEULE : `execute_normal_like` (mode `amount` d'`AttackWithAttackDamage` + le
    `UseNormalAttackIfAble` on-appearance d'un summon) et les DEUX voies de coups additionnels
    (`IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType` ->
    `ExecuteHits` ; `IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute`
    -> slot 0x3c `Core.Services.OperationProcessor$$AttackDamage` ->
    `IdunBattle.Operations.AttackDamageOperation$$Execute` -> `ExecuteHits`) retombent sur le MÊME
    per-coup `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` que l'attaque d'arme, donc sur
    le MÊME slot 0x10. Le prérequis de mesure (%-list vides + branche perçage gagnante) a été fabriqué
    par le levier NEUF `rl_duel build --armor-target` — aucune armure du roster ne suffisait sur un
    profil à perçage bas. MESURES : `normal_like` (DeathFromAbove/`ultraSmnInceptor`, Bolter p20,
    cellules [159,239] tronquées vs [160,239] arrondies) = live == arrondi **30/30**, == troncature
    **0/30**, plus un TÉMOIN non discriminant (branche armure) 12/12 sur les deux modèles ;
    `additional_hits` (SquigHound, predefined [2660,3988], Physical p1, armure 6000) = live == arrondi
    **14/14**, == troncature **10/14**, les 4 écarts tombant exactement sur frac >= .5.
    Détail : `docs/rl/case-r6-materialisation-normal-like-additional-hits.md`."""
    v_raw = apply_capped_modifiers(value, mods).raw
    # #437-r1-r1-r1 — la face DEFENSEUR de CET accumulateur, s'il en porte une. STRICTEMENT no-op
    # tant que la liste est vide (`apply_pct_entries([])` rend la valeur INCHANGEE, sans `Round`),
    # ce qui est le cas sur tous les call-sites COMBAT : `_apply_defender_flat_reductions` a deja
    # DEPLACE les deux faces de `def_mods` vers l'accumulateur du coup. La ligne existe pour que le
    # cas contraire soit CALCULE au lieu d'etre SILENCIEUSEMENT PERDU -- une face defenseur non
    # vide arrivant ici etait purement et simplement droppee avant.
    if mods.pct_list_defender:
        v_raw = apply_pct_entries(_fx.Fix64(v_raw), mods.pct_list_defender).raw
    # #462-r4a — l'étage MULTIPLICATEUR (`Multiplier@0x30`, slot 0x10). Les %-list se composent
    # AVANT lui (ci-dessus), les modifications de STAT y entrent (`from_stat_mod`). `1.0` = no-op
    # strict (aucun `Round` surnuméraire : `calculate_base_damage_with_modifiers` n'est appelé que
    # si le slot est effectivement alimenté), donc rétro-compat exacte partout où il n'y a pas de
    # stat-modification — c'est-à-dire dans l'immense majorité des cas.
    if mods.multiplicative != 1.0:
        v_raw = calculate_base_damage_with_modifiers(_fx.Fix64(v_raw), mods.multiplicative).raw
    if mods.multiplicative_defender != 1.0:
        v_raw = calculate_base_damage_with_modifiers(_fx.Fix64(v_raw),
                                                     mods.multiplicative_defender).raw
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
    `reference` = D (le centre, possiblement fractionnaire .5). = Sum min(PercentageOf(D, pct), cap).
    Liste vide -> 0 (combat sans réduction capée = BIT-EXACT inchangé).

    #920-r1 — `PercentageOf` ARRONDIT, il ne tronque pas. Corps de
    `IdunBattle.Entities.Formulas.PercentageOf$$CalculateInternal` RELU VERBATIM (build `rnca9r7q6c`) :

        p = Fix64(percentage) ; p = Round(p / 100 * 100, 0) / 100
        v = Fix64(finalAmount) * p
        v = Round(v * 100, 0) / 100                  # arrondi au CENTIEME
        return AAmountFormula.RoundFix64Result(v, this@+0x20)

    Il n'y a **AUCUNE troncature** dans cette chaîne : les deux `Round` sont des `Fix64.Round`
    (demi-vers-le-PAIR), et `RoundFix64Result` retombe sur le même `Fix64.Round` pour tout mode
    autre que `1`=Ceiling / `2`=Floor. Le mode est **LU**, pas supposé :
    `GuardianOrganism_DamageReductionEffect$$CreateEffectDamageMalusForDefense` construit
    `ForSubtraction(get_OwnerIsTarget, Min(PercentageOf(CurrentDamage, ConfigVar(0x46), <mode 0>),
    ConfigVar(0x12)))` — le `0` est le 4ᵉ argument littéral de `DSLFormulas.PercentageOf`.

    C'est le MÊME foyer d'arrondi que le nœud DSL `entities/formulas.py::PercentageOf`, qui, lui,
    était déjà fidèle : ce helper SCALAIRE en était la seule copie divergente.

    ⚠ Le témoin qui revendiquait l'inverse (« #91 : D->flat=177=floor, PAS 178=round ») est
    RETIRÉ : il n'est reproductible NULLE PART dans le dépôt (aucun probe, aucun test, aucune
    case-doc ne le porte — seule cette docstring l'énonçait), et il se contredisait lui-même deux
    lignes plus haut (« flat≈178 »). Il est réfuté par une mesure live REPRODUCTIBLE, celle de
    `#920` (`probe_920_maw_claws_of_thyrax_live.py --n 0 --porteur-defenseur`, `blackHaarken` →
    `tyranTyrantGuard`) : D = 3106, pct = 33 → natif **1025**, troncature **1024**, d'où le
    `DELTA [1, 1, 1, 1]` constant sur quatre montants tous différents.

    ⚠ NON TRANCHÉ (résidu #920-r3) : le natif reçoit `finalAmount` en **int32**
    (`Fix64.op_Implicit(int)` dans le décompilé), alors que les trois call-sites du port passent
    un centre `(lo + hi) / 2.0` qui peut valoir `.5`. Aucune mesure ne discrimine ce cas — les
    montages mesurés tombent tous sur un centre ENTIER. La chaîne ci-dessous est donc jouée sur la
    référence fractionnaire telle quelle, sans pré-arrondi inventé."""
    flat = 0
    for _pct, _cap in capped_reductions:
        # `p = Round(pct / 100 * 100, 0) / 100` — neutre pour un `pct` entier, joué quand même
        # (mirror 1:1) ; `Fraction` représente la chaîne EXACTEMENT, sans erreur binaire.
        _p = Fraction(_dsl_base._round_fix64(Fraction(_pct), 0), 100)
        _v = Fraction(reference) * _p
        # `v = Round(v * 100, 0) / 100` — l'arrondi au CENTIEME. Il n'est PAS neutre quand la
        # référence est fractionnaire, d'où sa présence explicite.
        _v = Fraction(_dsl_base._round_fix64(_v * 100, 0), 100)
        _r = _dsl_base._round_fix64(_v, 0)          # `RoundFix64Result(., mode 0)` = Fix64.Round
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


def calculate_modifiers_from_stat_modifications(stat_component, negate: bool = False,
                                                native_face: str = "attacker") -> list[EffectBonus]:
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
    # `from_stat_mod=True` (#462-r4a) : ces entrees-la, et ELLES SEULES, atterrissent dans
    # `Multiplier@0x30` -- le caller natif les folde par `GetMultiplierFromDamageBonus` surcharge
    # LISTE puis `DamageModifiers$$Add(this, modifier)` surcharge 1-ARG, ce qui les place APRES le
    # `Round` de l'etage MULTIPLICATEUR, alors que les %-list d'effets se composent avant lui.
    # `native_face` (#437-r1-r1-r1) : le fold DEFENSE est fait PAR `CalculateDefenderModifiers
    # ForPrediction` (donc `defenseModifiers.Multiplier@0x30`), le fold ATTACK par son homologue.
    # Ce n'est pas une option -- c'est le builder appelant qui le sait, et l'appelant DOIT le dire.
    return [EffectBonus("PercentIncrease", sign * int(amount), owner_is_caster=True,
                        from_stat_mod=True, native_face=native_face)
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
