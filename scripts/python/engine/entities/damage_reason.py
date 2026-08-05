"""engine.entities.DamageReason -- enum natif `IdunBattle.Operations.DamageReason` (mirror 1:1).

Source unique : `data/symbols/<build>/frida/enums.tsv`, ligne
`IdunBattle.Operations.DamageReason  0=Ability,1=Knockback,2=Steppable` (build `rnca9r7q6c`).

C'est le premier champ (`+0x00`) du `KillUnitOperationOptions` natif, celui que
`IdunBattle.Operations.KillUnitOperation$$Execute` passe en 5e argument a
`IdunBattle.Operations.KillUnitOperation$$RecordDeathReason` (sous le gate `options+0x44`), et qui
finit dans la `DamageSource` gravee sur `UnitComponent+0x108` (cote port : `death_source[1]`,
cf. `runner/components.py`). C'est LUI que compare
`IdunBattle.Entities.Triggers.HasDeathReasonTrigger$$IsMatchingDeathReason`.

Les trois constructeurs d'options du binaire posent chacun une valeur DIFFERENTE :
  * `IdunBattle.Operations.KillUnitOperationOptions$$ForDefault`   -> `+0x00 = 0` (`Ability`) ;
  * `IdunBattle.Operations.KillUnitOperationOptions$$ForSteppable` -> `+0x00 = 2` (`Steppable`) ;
  * `Knockback` (1) n'a aucun constructeur nomme -- il est pose inline par la famille deplacement.

⚠ Qualification d'enum (regle du CLAUDE.md) : `2` est AUSSI `EffectTargetType`, `KillUnitStep`,
`StatPart`... -- ne jamais ecrire l'ordinal nu sur ce canal.
"""
from __future__ import annotations

from enum import IntEnum


class DamageReason(IntEnum):
    """Mirror 1:1 de `IdunBattle.Operations.DamageReason` (3 membres). Valeur == id natif."""
    Ability = 0
    Knockback = 1
    Steppable = 2
