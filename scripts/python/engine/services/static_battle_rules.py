"""Port FIDÈLE de `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage`.

Règles de combat STATIQUES (perçage/armure). 1:1 avec le natif (gqfc5mff6c), VA citées.

Constantes statiques du jeu (à confirmer par lecture des cctor DAT) :
  • W_LASCANNON_PIERCE_BONUS : bonus de perçage si le profil a le trait 3 (LasCannon) ET
    l'attaquant a le trait 1001 (0x3e9) ou 1016 (0x3f8). DAT_183218fd8[0]. (défaut connu : inconnu
    précis → exposé en paramètre, 0 par défaut, à plomber via gameconfig/cctor.)
"""
from __future__ import annotations


def get_piercing_ratio(profile_piercing_ratio: int, profile_has_trait3: bool,
                       attacker_has_trait_1001_or_1016: bool,
                       lascannon_bonus: int = 0) -> int:
    """StaticBattleRules.Damage.GetPiercingRatio (@181559a40).

        p = profile.PiercingDamageRatio                 # WeaponProfile/DamageProfile @+0x14
        if profile.HasTrait(3) and (attacker has trait 1001|1016): p += <const DAT_183218fd8>
        return clamp(0, 100, p)
    """
    p = profile_piercing_ratio
    if profile_has_trait3 and attacker_has_trait_1001_or_1016:
        p += lascannon_bonus
    return max(0, min(100, p))


def get_damage_with_piercing(damage: int, pierce_pct: int, armor: int) -> int:
    """StaticBattleRules.Damage.GetDamageWithPiercing (@1815598b0) — LE cœur armure/perçage.

        pierced     = damage × pierce%/100        # fraction qui IGNORE l'armure
        after_armor = max(0, damage − armor)
        return max(after_armor, pierced)          # le perçage est un PLANCHER

    (Fix64 en interne ; troncature à la sortie. `damage`/`armor`/résultat = ints de dégât.)
    """
    pierced = damage * pierce_pct // 100
    after_armor = damage - armor
    if after_armor < 0:
        after_armor = 0
    return after_armor if after_armor > pierced else pierced
