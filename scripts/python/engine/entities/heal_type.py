"""engine.entities.HealType -- enum natif `IdunBattle.Entities.Enum.HealType` (mirror 1:1).

Source unique : `data/symbols/<build>/frida/enums.tsv`, ligne
`IdunBattle.Entities.Enum.HealType  0=NonMechanical,1=Mechanical,2=Any` (build `rnca9r7q6c`).

C'est le second parametre d'`IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType`, dont le TYPE
DECLARE est LU dans `frida/methods.tsv` :

    IdunBattle.Entities.UnitExtensions.IsAffectedByHealType
        unit : IdunBattle.Core.IEntity, healType : IdunBattle.Entities.Enum.HealType

-- pas deduit du nom court, qui n'aurait rien apparie d'autre ici mais a deja apparie FAUX deux fois
sur ce registre (`Corner`, `Edge`). Meme type au parametre d'`AttackQuery$$EntityIsAffectedByHealType`
et de sa version cachee.

Le corps natif lit ce discriminant APRES un court-circuit par trait :

    if (GetBaseUnitComponent(unit)?.HasTrait(0x421 AffectedByHealAndRepair) == true) return true;
    if (healType == NonMechanical &&  IsMechanical(unit)) return false;
    if (healType == Mechanical    && !IsMechanical(unit)) return false;
    return true;                                   // `Any` ne filtre rien

-> `NonMechanical` (0) est donc le heal BIOLOGIQUE (il EXCLUT les mecaniques), et `Mechanical` (1) la
reparation. Le nom dit ce que la valeur ACCEPTE, pas ce qu'elle vise : l'ecrire par son membre est ce
qui empeche de lire `0` comme « pas de type ».

⚠ Qualification d'enum (regle du CLAUDE.md) : `0` et `1` sont AUSSI des membres de `DamageReason`,
`KillUnitStep`, `EffectTargetType`, `PathfinderType`... -- ne jamais ecrire l'ordinal nu sur ce canal.
"""
from __future__ import annotations

from enum import IntEnum


class HealType(IntEnum):
    """`IdunBattle.Entities.Enum.HealType` -- mirror 1:1 (cf. le module)."""

    NonMechanical = 0
    Mechanical = 1
    Any = 2


__all__ = ["HealType"]
