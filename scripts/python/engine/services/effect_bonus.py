"""Port FIDÈLE de `IdunBattle.Entities.Effects.EffectBonus` (gqfc5mff6c).

Chaque effet construit sa contribution de dégât/coups via ces fabriques (RE : ce sont les seules
sources de bonus que le builder modifier consomme — cf. playbook-engine.md §17). Le `CreateEffect*
ForAttack` d'un effet appelle l'une d'elles avec une **constante de config** (`DSLFactory.ConfigConst`)
comme magnitude, puis renvoie un `EffectBonus` (Nullable). Ex. confirmé :
  IdunBattle.Entities.Effects.Loki.RapidAssault_ExtraDamageEffect$$CreateEffectDamageBonusForAttack :
      = EffectBonus.ForPercentIncrease(ownerIsCaster, ConfigConst(effect, 0xf=extraDmgPct))

`IdunBattle.Entities.Effects.EffectBonus$$ForPercentIncrease = pur emballage `{ownerIsCaster, value}` (AUCUNE condition ;
les conditions sont (a) la présence de l'effet — cycle de vie triggers — et (b) la logique propre du
`CreateEffect*ForAttack` de chaque effet, portée par-effet). Famille des fabriques (toutes @180f40xxx) :
ForPercentIncrease/ForPercentDecrease/ForAddition/ForSubtraction/ForPiercing/ForOverride/ForReset
+ CappedEffectBonus.Create (variante avec plafond).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EffectBonus:
    """Mirror de `EffectBonus` (struct valeur). On garde le strict nécessaire au calcul du modifier.

    `kind` = la fabrique d'origine ; `value` = sa magnitude (pct pour Percent*, montant pour
    Addition/Subtraction, ratio pour Piercing, valeur pour Override) ; `owner_is_caster` = à qui le
    bonus s'applique (l'attaquant pour un buff offensif) ; `cap` = plafond (CappedEffectBonus, None=∞)."""
    kind: str
    value: int = 0
    owner_is_caster: bool = True
    cap: int | None = None
    # #462-r4a -- CANAL D'ARRIVEE dans l'accumulateur : `Multiplier@0x30` (True) ou la LISTE @0x18
    # (False, le defaut). `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersFor
    # Prediction` traite les MODIFICATIONS DE STAT a part des EFFETS : elles passent par
    # `GetMultiplierFromDamageBonus(<la LISTE des stat-mods>)` (surcharge liste, produit unique)
    # suivi de `DamageModifiers$$Add(this, modifier)` -- la surcharge 1-ARGUMENT, qui ecrit
    # `Multiplier@0x30`. Ce slot est consomme par le DERNIER etage de
    # `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`
    # (`CalculateBaseDamageWithModifiers`, slot 0x10), donc APRES un `Fix64.Round` -- alors que la
    # %-list, elle, se compose SANS arrondi intermediaire (#98). Les deux canaux ne sont donc PAS
    # interchangeables des que le percage sort fractionnaire. MESURE : case-462-r4a §3.
    from_stat_mod: bool = False
    # #437-r1-r1-r1 -- L'ACCUMULATEUR NATIF ou cette contribution atterrit : `attackModifiers`
    # ("attacker") ou `defenseModifiers` ("defender"). C'est ce qui decide COMBIEN de `Fix64.Round`
    # `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` applique (un
    # par accumulateur non nul, cf. #437-r1-r1) -- donc une valeur observable, pas un detail.
    #
    # ⚠ CE N'EST PAS « qui PORTE l'effet », et les confondre a coute un `-1` (#586) :
    # `Terrifying_ExtraDefense` vit sur la CIBLE et le natif le verse cote ATTAQUANT. La face est
    # le SLOT VIRTUEL par lequel la contribution sort -- `CreateEffectDamageBonusForAttack`
    # (0x16, invoque par `CalculateAttackerModifiersForPrediction`) contre
    # `CreateEffectDamageMalusForDefense` (0x1a, invoque par son homologue defenseur). Les DEUX
    # builders enumerent le MEME dictionnaire d'effets de l'etat ; le trigger (`OwnerIsTarget` /
    # `OwnerIsActor`) choisit QUELLE unite declenche, jamais l'accumulateur.
    #
    # La valeur est POSEE PAR LE BUILDER (c'est lui qui sait quel slot il mirroire), depuis un
    # attribut de la classe d'effet ; le defaut ci-dessous sert les `EffectBonus` construits hors
    # boucle d'effets -- les feuilles POSITIONNELLES (elevation / ranged-in-melee / trench), que le
    # natif calcule DANS `CalculateAttackerModifiersForPrediction` lui-meme.
    # Table complete + garde : `scripts/python/probe_437r1r1r1_effect_face_table.py`.
    native_face: str = "attacker"


# IdunBattle.Entities.Effects.EffectBonus$$ForPercentIncrease — +value % (multiplicatif 1+value/100)
def for_percent_increase(owner_is_caster: bool, value: int,
                         cap: int | None = None) -> EffectBonus:
    return EffectBonus("PercentIncrease", value, owner_is_caster, cap)


# IdunBattle.Entities.Effects.EffectBonus$$ForPercentDecrease — −value % (multiplicatif 1−value/100)
def for_percent_decrease(owner_is_caster: bool, value: int,
                         cap: int | None = None) -> EffectBonus:
    return EffectBonus("PercentDecrease", value, owner_is_caster, cap)


# IdunBattle.Entities.Effects.EffectBonus$$ForAddition — +value plat (additif). Écrit le champ DamageBonus (+5) de
# l'EffectBonus → `IdunBattle.Core.Services.DamageModifiers$$Add` fait `additif @+0x10 += FromInt(v)`.
#
# ⚠ CE COMMENTAIRE A DIT « APRÈS perçage/armure » PENDANT DES MOIS, ET C'ÉTAIT FAUX DEPUIS #70/#75.
# Corrigé et RE-MESURÉ le 2026-08-18 sur `t6dpr4k06g` (#1005-r1), par deux sources indépendantes :
#
#   1. DÉCOMPILÉ — `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`
#      (l'étage POST-perçage) lit, sur chacun des deux `Nullable<DamageModifiers>`, EXACTEMENT :
#      `Piercing@+0x20`, `IgnoreArmor@+0x28` (les deux sommés par `Fix64.op_Addition` et passés en
#      dernier argument de `$$GetBaseDamageWithFixedPiercedArmor`), la liste `@+0x18` via le slot
#      `0x11` `ApplyCappedModifiers`, `Multiplier@+0x30` via le slot `0x10`, puis l'`Override` du
#      défenseur. **`Addition@+0x10` n'y est lu NULLE PART.** Un additif attaquant ne PEUT donc pas
#      être consommé après le perçage : il entre dans le `baseDamage` que cette fonction REÇOIT.
#   2. RECENSEMENT du port — les 17 call-sites d'`apply_pierce_and_modifiers` sous `engine/**`
#      passent TOUS `attacker_additive_pre=True` ; **aucun** ne passe `False` (le `False` n'est plus
#      qu'un défaut de signature, que sa propre docstring déclare « chemin legacy plus utilisé »).
#
# ⇒ IL N'Y A QU'UN SEUL PLACEMENT, ET IL EST PRÉ-PERÇAGE, pour TOUT `ForAddition` de l'ATTAQUANT.
# Le placement n'est PAS une propriété de l'`EffectBonus` : `for_addition` ne le porte pas, c'est le
# CALCULATEUR (`services/damage_prediction.apply_pierce_and_modifiers`) qui le fixe, uniformément.
# Lire une docstring d'effet (`SmashaEad` vs `FeederTendrils`) comme désignant « deux canaux » est
# donc un contresens : elles décrivent le même canal, et seules certaines l'écrivaient à jour.
# CONSÉQUENCE OBSERVABLE, qui est le vrai discriminant : un additif pré-perçage traverse le perçage
# PUIS la %-list, donc il ressort SCALÉ par les %-mods — un additif post-perçage, lui, ressortirait
# NU. Un écart mesuré supérieur à la valeur nominale de la variable n'est donc pas une anomalie à
# fitter, c'est la signature attendue de ce placement.
#
# Reste vrai de la ligne d'origine : il n'existe pas de kind « BaseAddition » côté natif (#69).
def for_addition(owner_is_caster: bool, value: int) -> EffectBonus:
    return EffectBonus("Addition", value, owner_is_caster)


# IdunBattle.Entities.Effects.EffectBonus$$ForSubtraction — −value plat (additif)
def for_subtraction(owner_is_caster: bool, value: int) -> EffectBonus:
    return EffectBonus("Subtraction", value, owner_is_caster)


# Réduction DYNAMIQUE CAPÉE : `ForSubtraction(Min(PercentageOf(CurrentDamage, pct), cap))` — soustrait
# `min(pct% × dégât_courant, cap)` du dégât REÇU. `value` = pct, `cap` = plafond ABSOLU de la réduction
# (≠ la sémantique `cap` de CappedEffectBonus qui plafonne le RÉSULTAT). Ex. GuardianOrganism_DamageReduction
# IdunBattle.Entities.Effects.Loki.GuardianOrganism_DamageReductionEffect$$CreateEffectDamageMalusForDefense : pct=ConfigVar(0x46=dmgReductionPct), cap=ConfigVar(0x12=dmgReduction). Appliqué APRÈS le
# %-list + additif (CurrentDamage = dégât post-mods), cf. `apply_all_modifiers`. `cap=None` = non plafonné.
def for_percent_subtraction_capped(owner_is_caster: bool, pct: int,
                                   cap: int | None = None) -> EffectBonus:
    return EffectBonus("PercentSubtractionCapped", pct, owner_is_caster, cap)


# IdunBattle.Entities.Effects.EffectBonus$$ForPiercing — bonus de PERÇAGE (axe armure, pas le scalaire dégât).
# Alimente le champ pierce-extra du DamageModifiers (struct @0x20) sommé dans
# IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers → pierce_eff = clamp(pierce + extra, 0, 100).
def for_piercing(owner_is_caster: bool, value: int) -> EffectBonus:
    return EffectBonus("Piercing", value, owner_is_caster)


# Axe ARMOR-PENETRATION (struct DamageModifiers @0x28) — `armor_eff = max(FixedArmor − pénétration, 0)`
# (IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers ; sommé attaquant+défenseur). Source par-effet =
# méthode d'interface dédiée (ex. IdunBattleLogic.Entities.Abilities.Triggered.Loki.KanOpenerEffect$$IgnoreArmor = ConfigVar key 0x40), PAS
# CreateEffectDamageBonusForAttack (qui n'alimente que additif/percent via DamageModifiers.Add).
def for_armor_penetration(owner_is_caster: bool, value: int) -> EffectBonus:
    return EffectBonus("ArmorPenetration", value, owner_is_caster)


# Ignore-armure TOTALE (pénétration ≥ armure) — `armor_eff = 0`. Variante booléenne pour les effets
# « ignore l'armure » sans valeur numérique de pénétration.
def for_ignore_armor(owner_is_caster: bool = True) -> EffectBonus:
    return EffectBonus("IgnoreArmor", 0, owner_is_caster)
