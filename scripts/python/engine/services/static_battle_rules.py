"""Port FIDÈLE de `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage`.

Règles de combat STATIQUES (perçage/armure). 1:1 avec le natif (gqfc5mff6c), VA citées.

Constantes statiques du jeu (à confirmer par lecture des cctor DAT) :
  • W_LASCANNON_PIERCE_BONUS : bonus de perçage si le profil a `DamageTrait.LasCannon` (3, cf.
    entities/damage_trait.py) ET l'attaquant a `UnitTrait.HeavyWeapon` (1001) ou `UnitTrait.Emplacement`
    (1016) (cf. entities/traits/unit_trait.py). DAT_183218fd8[0]. (défaut connu : inconnu précis → exposé
    en paramètre, 0 par défaut, à plomber via gameconfig/cctor.)
"""
from __future__ import annotations

from . import fix64 as _fx


def get_piercing_ratio(profile_piercing_ratio: int, profile_has_lascannon: bool,
                       attacker_has_heavy_weapon_or_emplacement: bool,
                       lascannon_bonus: int = 0) -> int:
    """StaticBattleRules.Damage.GetPiercingRatio (@181559a40).

        p = profile.PiercingDamageRatio                 # WeaponProfile/DamageProfile @+0x14
        if profile.HasTrait(DamageTrait.LasCannon) and attacker.HasTrait(HeavyWeapon|Emplacement): p += <const DAT_183218fd8>
        return clamp(0, 100, p)
    `profile_has_lascannon` = `DamageProfile.HasTrait(DamageTrait.LasCannon)` (précalc appelant) ;
    `attacker_has_heavy_weapon_or_emplacement` = `HasTrait(attacker, UnitTrait.HeavyWeapon|Emplacement)` (précalc appelant).
    """
    p = profile_piercing_ratio
    if profile_has_lascannon and attacker_has_heavy_weapon_or_emplacement:
        p += lascannon_bonus
    return max(0, min(100, p))


def get_damage_with_piercing(damage, pierce_pct: int, armor: int) -> "_fx.Fix64":
    """StaticBattleRules.Damage.GetDamageWithPiercing (@1815598b0) — LE cœur armure/perçage.
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
    combat : op_Explicit = floor, @181034e87+/`CalculateAbilityDamage @18102cb50`). `damage` peut être
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
