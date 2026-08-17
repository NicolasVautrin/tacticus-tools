"""Oracles CONFIG des tests moteur -- une valeur BRUTE se LIT, elle ne s'ecrit pas (#110).

QUAND s'en servir. Une assertion de test porte soit une valeur CALCULEE (le moteur la derive par une
formule : coups appliques apres reductions, degat resolu) -- son oracle est alors le LIVE, on interroge le
moteur natif ; soit une valeur BRUTE (une constante de config lue TELLE QUELLE par le natif) -- son oracle
est la CONFIG, et c'est CE module. Le decompile tranche entre les deux, il ne sert pas a autre chose ici.

LE PIEGE QUE CE MODULE FERME. Un `GC.<lookup>(...) or 0` degrade en SILENCE : si la cle est renommee par un
patch, l'oracle rend 0, l'assertion compare 0 a 0 et reste VERTE en n'ayant plus rien verifie. Toutes les
fonctions ci-dessous ECHOUENT FRANCHEMENT sur une cle absente -- l'indisponibilite de l'oracle doit se voir.

L'AUTRE PIEGE : LA BONNE CLE. Des cles voisines partagent la valeur (`parryHitReduction`,
`diminutiveHitReduction`, `camouflageHitReduction_1` valent 1 ; toutes trois sont lues par le meme
`GetNumberConstant(config, 0x2c)`, chacune depuis la config de SON ability). Lire la voisine passe vert
aujourd'hui et devient faux au prochain rebalance. La cle exacte est donc un ARGUMENT NOMME ici, et le
message d'assertion la porte verbatim.

ASCII only.
"""
from __future__ import annotations

import gameconfig as GC


# ---------------------------------------------------------------- profils de degat (PiercingRatio)

def damage_profile_pierce(profile: str) -> int:
    """`damageProfiles.<profile>.PiercingRatio`.

    BRUTE : `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetPiercingRatio`
    lit `DamageProfile.PiercingDamageRatio` (champ +0x14) TEL QUEL, puis n'y ajoute que le bonus LasCannon
    (gate profil LasCannon + attaquant HeavyWeapon/Emplacement) avant `clamp(0,100)`. Hors de ce gate, le
    perçage d'un profil EST la valeur de config."""
    dp = GC.damage_profile(profile)
    assert dp is not None, \
        f"damageProfiles.{profile} absent du gameconfig -- oracle indisponible (pas un test vert)"
    raw = dp.get("PiercingRatio")
    assert raw is not None, \
        f"damageProfiles.{profile}.PiercingRatio absent -- oracle indisponible (pas un test vert)"
    return int(raw)


def ability_damage_profile(ability: str) -> "str | None":
    """`abilities.<ability>.constants.damageProfile`, ou None si l'ability n'a pas cette constante.

    C'est la source que lit `IdunBattle.Configuration.AbilityConfiguration$$GetDamageProfile`. Toutes les
    abilities ne passent PAS par la : certaines fournissent un litteral `DamageProfileType` directement a
    `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (ex. `HarvesterOfSoulsAbility$$ExecuteBehaviour`
    -> `Nullable<DamageProfileType>(0x13 = HeavyRound)`) -- pour celles-la le NOM du profil est un fait de
    structure, pas une valeur de config, et seul son `PiercingRatio` se lit ici."""
    return ((GC.ability(ability) or {}).get("constants") or {}).get("damageProfile")


def assert_ability_damage_profile(ability: str, profile: str) -> None:
    """Verrou config<->port pour les abilities dont le behaviour natif appelle
    `IdunBattle.Configuration.AbilityConfiguration$$GetDamageProfile` : le profil que le port passe doit
    etre celui que la config declare. A n'utiliser QUE sur ces abilities-la (cf. `ability_damage_profile`)."""
    got = ability_damage_profile(ability)
    assert got == profile, (
        f"abilities.{ability}.constants.damageProfile = {got!r} != {profile!r} passe par le port "
        f"(AbilityConfiguration.GetDamageProfile) -- le port ne route plus le profil declare")


# ---------------------------------------------------------------- variables de trait / globales

def trait_variable(trait: str, key: str) -> int:
    """`traitVariables.<key>` (resolue via le trait porteur). `key` est EXACTE et nommee par l'appelant :
    plusieurs variables de traits partagent la meme valeur, lire la voisine passerait vert."""
    variables = (GC.trait(trait) or {}).get("variables") or {}
    assert key in variables, (
        f"traitVariables.{key} absent (trait {trait}) -- oracle indisponible (pas un test vert)")
    return int(variables[key])


def global_constant(key: str) -> int:
    """`clientGameConfig.globalValues.<key>`. Echoue si absente (jamais de repli sur 0)."""
    raw = GC.global_value(key)
    assert raw is not None, \
        f"globalValues.{key} absent du gameconfig -- oracle indisponible (pas un test vert)"
    return int(raw)


# ---------------------------------------------------------------- variables per-niveau

def ability_variable_levels(ability: str, key: str) -> list:
    """`abilities.<ability>.variables.<key>` = le TABLEAU per-niveau complet (index = niveau-1).

    Sert a DERIVER une plage attendue au lieu de l'ecrire : les bornes d'une variable level-indexee sont
    `min`/`max` de ce tableau, pas deux litteraux."""
    variables = (GC.ability(ability) or {}).get("variables") or {}
    levels = variables.get(key)
    assert levels, \
        f"abilities.{ability}.variables.{key} absent ou vide -- oracle indisponible (pas un test vert)"
    return list(levels)
