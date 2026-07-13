"""engine.entities.damage_trait — enum natif `DamageTrait` (traits de PROFIL DE DEGAT).

Mirror 1:1 de l'enum natif `DamageTrait` (dump.cs `gqfc5mff6c`, TypeDefIndex 24353) : les traits portes
par un `DamageProfile` (arme / attaque), DISTINCTS des `UnitTrait` (traits d'unite, TypeDefIndex 24364,
cf. entities/traits/unit_trait.py). Teste via `DamageProfile.HasTrait(DamageTrait)`.

Le port referencait ces traits en ints bruts (`profile_has_trait3`, `PROFILE_TRAIT_HITS_MULTIPLE_MEMBERS
= 2`, `DamageProfileHasTrait(1)`...) -> cet enum est la source unique id<->nom (meme demarche que
`UnitTrait` #146 / `EventTriggerType` #155).

Usages dans le port :
  - NoBlocking (0)          : `PredictAttackRaw` skip la boucle multi-outcome (outcome unique).
  - OnFire (1)              : `OnFireDamageAbility` pose du feu on-hit (trigger `DamageProfileHasTrait(1)`).
  - HitsMultipleMembers (2) : "Blast" -> `ApplyGroupUnitDamageLimit` SKIP le member-cap (trait_damage_limits).
  - LasCannon (3)           : bonus de percage si l'attaquant a HeavyWeapon(1001)/Emplacement(1016)
                              (`profile_has_trait3` dans get_piercing_ratio / static_battle_rules).
  - OnToxic (4)             : attaque Toxic -> pose Contaminated (OnToxicDamageAbility, #137).
  - OnMelta (5)             : attaque Melta.
"""
from __future__ import annotations

from enum import IntEnum


class DamageTrait(IntEnum):
    """`DamageTrait` @dump.cs TypeDefIndex 24353. Valeur == id natif (arg de `DamageProfile.HasTrait`)."""
    Unknown = -1
    NoBlocking = 0
    OnFire = 1
    HitsMultipleMembers = 2   # "Blast"
    LasCannon = 3
    OnToxic = 4
    OnMelta = 5
