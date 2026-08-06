"""engine.entities.VictoryConditionType -- enum natif `idun.Shared.Battle.VictoryConditionType`
(mirror 1:1).

Source unique : `data/symbols/<build>/frida/enums.tsv`, ligne
`idun.Shared.Battle.VictoryConditionType  0=MainPlayerHasNoHeroesAndSummons,
1=MainPlayerRoundLimitation,2=KillAllEnemyUnits,...` (build `rnca9r7q6c`).

C'est la CLE du dictionnaire `BC.Victory.VictoryConditions`, celui que
`IdunBattle.Core.Services.BattleQuery$$GetMaxRounds` interroge :

    victoryConfig.<Dictionary @+0x18>.TryGetValue(1, out v)  ->  Nullable<int>(v)

Le litteral `1` du decompile est donc `MainPlayerRoundLimitation`, et la VALEUR associee est le
PLAFOND DE ROUNDS du match. Le consommateur qui a rendu ce mirror necessaire est
`IdunBattle.Core.Services.BattleQuery$$HasMinimumRemainingTurns`, sous le bit `CasterHas2TurnsLeft`
de `IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason` (cf.
`engine.services.battle_query.has_minimum_remaining_turns`).

⚠ Qualification d'enum (regle du CLAUDE.md) : `1` est AUSSI `DamageReason.Knockback`,
`UnitTrait`(1), `EffectTargetType`(1)... -- ne jamais ecrire l'ordinal nu sur ce canal. Le nom
seul rend la faute visible : `MainPlayerRoundLimitation` (1) et `KillAllEnemyUnits` (2) sont
voisins, et lire la mauvaise cle donnerait un plafond de rounds egal a un booleen de condition.
"""
from __future__ import annotations

from enum import IntEnum


class VictoryConditionType(IntEnum):
    """Mirror 1:1 d'`idun.Shared.Battle.VictoryConditionType` (8 membres). Valeur == id natif."""
    MainPlayerHasNoHeroesAndSummons = 0
    MainPlayerRoundLimitation = 1
    KillAllEnemyUnits = 2
    VictoryPoints = 3
    KillEnemyBossUnit = 4
    KillAllEnemyUnitsInclPlayer1Objects = 5
    KillAllEnemyMainUnits = 6
    MainPlayerWinsIfAllUnitsAreDead = 7
