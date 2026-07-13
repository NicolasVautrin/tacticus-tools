"""engine.entities.DamageProfileType -- enum natif `DamageProfileType` (mirror 1:1 complet).

Mirror 1:1 de `IdunBattle.Entities.Enum.DamageProfileType` (24 membres) genere depuis `data/il2cpp_enums.tsv`
(build gqfc5mff6c) -- meme demarche que `UnitTrait` (#146) / `EventTriggerType` (#155) /
`DamageTrait` (#156). Source unique id<->nom : les constantes id-hex eparses du port sont
converties vers cet enum (#158). GENERE (transcription exacte du tsv, zero typo) ; regenerable
via scripts scratchpad/enum_gen.py.

Valeur == id natif. ATTENTION (#157/#158) : le MEME id peut appartenir a des enums DIFFERENTS
selon le contexte (ex. 1017 = `EffectType.ActOfFaith` ET `UnitTrait.BigTarget`) -> chaque site
de conversion verifie l'enum correct.
"""
from __future__ import annotations

from enum import IntEnum


class DamageProfileType(IntEnum):
    """Mirror 1:1 de `IdunBattle.Entities.Enum.DamageProfileType` (24 membres). Valeur == id natif."""
    Physical = 0
    Projectile = 1
    Flame = 3
    Bolter = 4
    Particle = 5
    Acid = 6
    Plasma = 7
    Melta = 8
    Gauss = 10
    Enmitic = 11
    Psychic = 13
    Power = 14
    DirectDamage = 15
    Energy = 16
    Chain = 17
    Blast = 18
    HeavyRound = 19
    Piercing = 20
    Las = 21
    Bio = 22
    Pulse = 23
    Toxic = 24
    Eviscerate = 25
    None_ = -1


# index natif -> NOM de profil BC (= nom du membre, sauf `None_` -> "None" : le profil BC est litteralement
# "None", que Python ne peut nommer). Derive de l'enum (source unique, plus de table transcrite a la main ;
# #158 remplace les 2 copies DAMAGE_PROFILE_BY_INDEX/_PROFILE_BY_INDEX de predict.py/active_ability.py).
PROFILE_NAME_BY_INDEX: dict[int, str] = {
    int(m): ("None" if m is DamageProfileType.None_ else m.name) for m in DamageProfileType
}
