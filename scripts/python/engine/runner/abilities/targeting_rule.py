"""Mirror 1:1 de `IdunBattle.Core.Services.TargetingRule` -- GENERE, ne pas editer a la main.

Les regles de ciblage natives sont un enum de FLAGS **64 bits**, lu a `TargetingOptions+0x28` et
consomme par `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (cascade 7-args).
Chaque membre est un bit ; quelques-uns sont des COMPOSITES (plusieurs bits), conserves tels quels
parce que le natif les declare.

Produit par `scripts/python/gen_targeting_rule.py` depuis
`data/symbols/t6dpr4k06g/frida/enums.tsv`. Regenerer apres chaque re-dump ; la coherence
module <-> dump est gardee par `scripts/python/probe_targeting_rule_bits.py`.

`IntFlag` et non `IntEnum` : un masque est une COMBINAISON, et `rules & TargetingRule.TargetIsEnemy`
doit rester un test d'entier -- les consommateurs existants comparent des ints, rien a changer chez
eux.
"""
from __future__ import annotations

from enum import IntFlag


class TargetingRule(IntFlag):
    None_                                      = 0x0   # natif : None
    ValidRequest                               = 1 << 0
    TargetMatchesDynamicRule                   = 1 << 1
    CasterMatchesDynamicRule                   = 1 << 2
    AddCasterIfMatchesDynamicRule              = 1 << 3
    CasterHasNotMoved                          = 1 << 4
    TargetHasFreeAdjacentTile                  = 1 << 5
    TargetIsTile                               = 1 << 6
    AddCaster                                  = 1 << 7
    TargetIsHealable                           = 1 << 8
    TargetIsAtRange                            = 1 << 9
    TargetIsFriendly                           = 1 << 10
    AddCasterIfAtLeastOneTarget                = 1 << 11
    TargetTileIsFree                           = 1 << 12
    TargetIsSummon                             = 1 << 13
    TargetIsEnemy                              = 1 << 14
    CasterIsPossibleTarget                     = 1 << 15
    TargetIsRepairable                         = 1 << 16
    TargetTileIsFreeOrEnemy                    = 1 << 17
    TargetIsDisplaceable                       = 1 << 18
    TargetTileHasEnemyUnit                     = 1 << 19
    AllowSteppableUnit                         = 1 << 20
    CasterHasFreeAdjacentTile                  = 1 << 21
    AddCasterIfAtLeastOneFreeTileInRange       = 1 << 22
    TargetIsAllowedForCaster                   = 1 << 23
    TargetIsUnobscured                         = 1 << 24
    AllowObscuredTargetByElevation             = 1 << 25
    AllowObscuredTargetByWalls                 = 1 << 26
    AllowObscuredTarget                        = 0x6000000
    TargetIsInRange                            = 1 << 27
    CasterCanMove                              = 1 << 28
    TargetIsTargetable                         = 1 << 29
    AllowNullCasterTile                        = 1 << 30
    CasterHasCompletedOneTurn                  = 1 << 31
    TargetIsNotAdjacent                        = 1 << 32
    TargetIsNotAnObject                        = 1 << 33
    AbilityIsNotDisabledByConfigModification   = 1 << 34
    CasterHas1Tiles                            = 1 << 35
    CasterHas3Tiles                            = 1 << 36
    CasterHas7Tiles                            = 1 << 37
    AllowDeadTarget                            = 1 << 38
    TargetIsCaster                             = 1 << 39
    AllowIgnoreForcedAttackTarget              = 1 << 40
    AllowUntargetableTarget                    = 1 << 41
    TargetIsNotAdjacentToEnemy                 = 1 << 42
    AllowUnwalkableTargetTile                  = 1 << 43
    TargetIsMachine                            = 1 << 44
    TargetIsUnit                               = 1 << 45
    TargetIsActor                              = 1 << 46
    TargetHas1Tiles                            = 1 << 47
    TargetHas3Tiles                            = 1 << 48
    TargetHas7Tiles                            = 1 << 49
    TargetIsHero                               = 1 << 50
    TargetIsNotSteppable                       = 1 << 51
    CasterHas2TurnsLeft                        = 1 << 52
    CasterIsMachine                            = 1 << 53
    AlreadyUseThisTurn                         = 1 << 54
    CasterHasNoTile                            = 1 << 55
    AllowTargetWithoutTile                     = 1 << 56
    TargetIsCasterOrEnemy                      = 1 << 57
