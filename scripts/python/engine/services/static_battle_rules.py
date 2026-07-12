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


def get_damage_with_piercing(damage: float, pierce_pct: int, armor: int) -> float:
    """StaticBattleRules.Damage.GetDamageWithPiercing (@1815598b0) — LE cœur armure/perçage.

        pierced     = damage × pierce%/100        # fraction qui IGNORE l'armure
        after_armor = max(0, damage − armor)
        return max(after_armor, pierced)          # le perçage est un PLANCHER

    ⚠ RENVOIE UN Fix64 (FRACTIONNAIRE) — le natif décompilé NE tronque PAS ici : `pierced =
    Fix64.Multiply(damage, pierce/100)` garde le fractionnaire, et le résultat reste Fix64 (aucun
    `op_Explicit`/`Round` en sortie). L'arrondi/troncature UNIQUE se fait EN AVAL : `%-list`
    (`ApplyCappedModifiers @181000020` = `Fix64.Round` PAR ENTRÉE ; liste vide -> valeur inchangée) puis
    la conversion int finale (prédiction: Round ; COMBAT `CalculateAbilityDamage @18102cb50`: op_Explicit
    = TRONCATURE). Flooré ici, le fractionnaire du perçage était perdu AVANT le %-list -> ±1/coup dès qu'un
    %-mod suit un perçage fractionnaire (#111 Nightshroud borne max : 548.x floor->548 ×1.25=685 vs
    fractionnaire 548.x×1.25=686). `damage` peut être fractionnaire (coups chaînés hit_mult>1)."""
    pierced = damage * pierce_pct / 100.0
    after_armor = damage - armor
    if after_armor < 0:
        after_armor = 0
    return after_armor if after_armor > pierced else pierced
