"""Port FIDÈLE de `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage`
(+ un membre de `StaticBattleRules.Effect`, cf. `is_tile_status_effect`).

Règles de combat STATIQUES (perçage/armure). 1:1 avec le natif (gqfc5mff6c), VA citées.

Constantes statiques du jeu (LUES au cctor natif, VA citées) :
  • W_LASCANNON_PIERCE_BONUS = 50 : bonus de perçage si le profil a `DamageTrait.LasCannon` (3, cf.
    entities/damage_trait.py) ET l'attaquant a `UnitTrait.HeavyWeapon` (1001) ou `UnitTrait.Emplacement`
    (1016) (cf. entities/traits/unit_trait.py). Valeur RÉSOLUE (#71) : `StaticBattleRules.DamageTrait$$.idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.DamageTrait$$.cctor fait `**(int **)(DAT_183218fd8 + 0xb8) = 0x32` (= 50), écriture du static_field[0] de la classe
    `StaticBattleRules.DamageTrait` ; `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetPiercingRatio` lit `iVar3 += **(int **)(cls + 0xb8)`
    (offset 0xb8 = Il2CppClass.static_fields). C'est un static field INTRINSÈQUE au natif (pas un paramètre)
    → `get_piercing_ratio` l'applique par défaut.
"""
from __future__ import annotations

from . import fix64 as _fx

# Bonus de perçage LasCannon — static_field[0] de `StaticBattleRules.DamageTrait` écrit à 0x32 par sa cctor
# idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.DamageTrait$$.cctor (`**(int **)(cls + 0xb8) = 0x32`), lu par `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetPiercingRatio`. VALEUR NATIVE = 50.
W_LASCANNON_PIERCE_BONUS = 50


# --- `StaticBattleRules.Effect` : le discriminant << STATUS de tuile >> ---------------------------
# `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$IsTileStatusEffect
# = `OrderedSet.Contains(<set statique>, effectType)`, le set etant bati par
# `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$.cctor (champ statique
# +0x28) avec EXACTEMENT ces 5 membres, lus 1:1 dans l'ordre des `OrderedSet.Add` du decompile.
#
# POURQUOI ICI et pas a cote de `default_amount_of_rounds` (l'autre membre porte de
# `StaticBattleRules.Effect`, dans `runner/operations/effects.py`) : ce predicat est consomme par
# `engine/entities/**` (le gate `TargetHasTileEffect` de LetTheGalaxyBurn) ET par `engine/runner/**`
# (`damage_model.tile_status_effects_by_pos`). Or `entities/` n'importe JAMAIS `runner/` (aucune
# inversion de couche dans l'arbre) ; `engine/services/` est la couche que les deux importent deja.
#
# ENJEU (#102) : une tuile porte des effets qui ne sont PAS des status (mesure live `C1_02` :
# `BlockEnteringUnits`=0 et `Thorns_DefenseReduction`=0xb sur les Swamp, `Melta_ExtraDmg`=0x511).
# `IdunBattle.Entities.TileExtensions$$HasTileStatusEffect` les EXCLUT via ce set. Tant que
# `load_state` ne seedait pas les effets de tuile, la liste offline ne contenait que ce que le runner
# avait pose lui-meme (Fire/Ice, tous des status) et l'absence de filtre etait INVISIBLE ; depuis le
# seed elle porte la VRAIE liste native, donc le filtre est OBLIGATOIRE.
TILE_STATUS_EFFECT_TYPES: frozenset = frozenset({0x3a, 0x05, 0x11, 0x4dc, 0x5c4})
#                                                ^Darkness ^Fire ^Ice ^Contaminated ^DespoiledGround

# MEMES membres, par NOM : le canal PREDICTION (`tileMeta.tiles[].effects[].name` ->
# `Scene.tile_effects_by_pos`) ne transporte que des noms, pas des EffectType.
TILE_STATUS_EFFECT_NAMES: frozenset = frozenset(
    {"Darkness", "Fire", "Ice", "Contaminated", "DespoiledGround"})


def is_tile_status_effect(effect_type) -> bool:
    """`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$IsTileStatusEffect
    -- cet EffectType compte-t-il comme un STATUS de tuile ? (cf. `TILE_STATUS_EFFECT_TYPES`)"""
    return effect_type is not None and int(effect_type) in TILE_STATUS_EFFECT_TYPES


def get_piercing_ratio(profile_piercing_ratio: int, profile_has_lascannon: bool,
                       attacker_has_heavy_weapon_or_emplacement: bool,
                       lascannon_bonus: int = W_LASCANNON_PIERCE_BONUS) -> int:
    """StaticBattleRules.Damage.GetPiercingRatio (idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetPiercingRatio).

        p = profile.PiercingDamageRatio                 # WeaponProfile/DamageProfile @+0x14
        if profile.HasTrait(DamageTrait.LasCannon) and attacker.HasTrait(HeavyWeapon|Emplacement): p += 50 (idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.DamageTrait$$.cctor)
        return clamp(0, 100, p)
    `profile_has_lascannon` = `DamageProfile.HasTrait(DamageTrait.LasCannon)` (précalc appelant) ;
    `attacker_has_heavy_weapon_or_emplacement` = `HasTrait(attacker, UnitTrait.HeavyWeapon|Emplacement)` (précalc appelant).
    `lascannon_bonus` = W_LASCANNON_PIERCE_BONUS (50) par défaut — le natif le lit du static field, pas d'un param.
    """
    p = profile_piercing_ratio
    if profile_has_lascannon and attacker_has_heavy_weapon_or_emplacement:
        p += lascannon_bonus
    return max(0, min(100, p))


def get_damage_with_piercing(damage, pierce_pct: int, armor: int) -> "_fx.Fix64":
    """StaticBattleRules.Damage.GetDamageWithPiercing (idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetDamageWithPiercing) — LE cœur armure/perçage.
    ARITHMÉTIQUE Fix64 EXACTE (#30a) — l'ordre des ops natif est LOAD-BEARING :

        pierceFrac  = Fix64Div(FromInt(pierce), FromInt(100))   # div ARRONDI → ex. 0.15 devient
                                                                # 0.1499999999767… (raw 644245094)
        pierced     = Fix64Mul(damage, pierceFrac)              # mul TRONQUANT
        after_armor = damage − FromInt(armor)
        return max(Zero, after_armor, pierced)                  # le perçage est un PLANCHER

    ⚠ Le port float faisait `damage × pierce / 100.0` — ordre différent (mul avant div) ET float64 :
    sur 777s6, natif 1850×fix(0.15)=277.4999…→floor 277 vs float 277.5→round 278 (±1/coup, ×hits).
    ⚠ RENVOIE UN Fix64 (FRACTIONNAIRE, `.raw` exact) — le natif NE tronque PAS ici (aucun
    `op_Explicit`/`Round` en sortie) ; la matérialisation int UNIQUE se fait EN AVAL (prédiction ET
    combat : op_Explicit = floor, IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1ed7+/`IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`). `damage` peut être
    fractionnaire (Fix64 des coups chaînés hit_mult>1) — passthrough exact via `.raw`."""
    d_raw = _fx.from_number(damage)
    pierce_frac = _fx.div(_fx.from_int(pierce_pct), _fx.from_int(100))
    pierced = _fx.mul(d_raw, pierce_frac)
    after_armor = d_raw - _fx.from_int(armor)
    # mirror natif : part de Zero (static +0x28), max avec after_armor puis avec pierced
    best = after_armor if after_armor > 0 else 0
    if pierced > best:
        best = pierced
    return _fx.Fix64(best)
