"""`AbilityConstantType` -- l'index des CONSTANTES d'une ability
(`IdunBattle.Configuration.AbilityConstantType`).

Mirror 1:1 de l'enum natif, re-derivable de `data/symbols/<build>/frida/enums.tsv`.

CE QU'IL DESIGNE, ET COMMENT ON LE SAIT. C'est le type DECLARE du premier parametre des quatre
accesseurs de constante :

    IdunBattle.Configuration.AbilityConfiguration.GetNumberConstant
        (constantType : IdunBattle.Configuration.AbilityConstantType)
    IdunBattle.Configuration.AbilityConfiguration.TryGetNumberConstant       (idem)
    IdunBattle.Configuration.AbilityConfiguration.GetStringArrayConstant     (idem)
    IdunBattle.Configuration.AbilityConfiguration.TryGetStringArrayConstant  (idem)

LU dans la table des methodes du build (`frida/methods.tsv`), pas deduit d'un nom court.

⚠ NE PAS LE CONFONDRE AVEC `AbilityVariableType`. Les deux sont des index d'ability, ils
partagent 141 ordinaux, et ils nomment autre chose a valeur egale : `22` est `range` ici et
`blockDmg_2` la-bas ; `47` est `nrOfHits` des deux cotes, mais `12` est `minAdjacentEnemies`
ici et `minDmg` la-bas. Le discriminant est l'ACCESSEUR appele au site
(`GetNumberConstant`/`GetStringArrayConstant` -> ce fichier ; `GetVariableForLevel` ->
`ability_variable_type.py`), jamais l'ordinal.

Le nom du membre est le nom de la cle dans le gameconfig (`constants.range`,
`constants.nrOfHits`, ...) : c'est la meme chaine des deux cotes.
"""
from __future__ import annotations

from enum import IntEnum


class AbilityConstantType(IntEnum):
    """`IdunBattle.Configuration.AbilityConstantType` -- VERBATIM du build (141 valeurs).

    Re-derivable : `data/symbols/<CURRENT>/frida/enums.tsv`, cle `IdunBattle.Configuration.AbilityConstantType`.
    Sous garde de `probe_313_enum_mirror_bijection.py` (bijection exigee)."""

    unitId = 0
    unitId_red = 1
    unitId_green = 2
    unitId_blue = 3
    unitId_2 = 4
    unitId_2_red = 5
    unitId_2_green = 6
    unitId_2_blue = 7
    unitToSpawn = 8
    unitToSpawn_red = 9
    unitToSpawn_green = 10
    unitToSpawn_blue = 11
    minAdjacentEnemies = 12
    extraRange = 13
    extraMovement = 14
    extraDmgPct = 15
    nrOfSummons = 16
    nrOfTargets = 17
    hpPct = 18
    HealPercentage = 19
    DefenseBonus = 20
    attackBonus = 21
    range = 22
    nrOfTiles = 23
    nrOfTilesToHit_1 = 24
    nrOfTilesToHit_2 = 25
    drunkIncreasePct = 26
    minProjectilesPerTile = 27
    maxProjectilesPerTile = 28
    nrOfProjectilesMin = 29
    nrOfProjectilesMax = 30
    nrOfProjectiles = 31
    hpForArmor = 32
    hpToHeal = 33
    iceRange = 34
    turns = 35
    maxMov = 36
    spreadProbability = 37
    lootMultiplierIncreasePct = 38
    cooldownTurns = 39
    defensePct = 40
    maxTargets = 41
    chance = 42
    extraHit = 43
    hitsReduction = 44
    blockChance = 45
    damageProfile = 46
    nrOfHits = 47
    extraCritChance = 48
    extraCritDmgPct = 49
    nrOfHits_2 = 50
    chance_2 = 51
    damageModifier = 52
    damageModifier_2 = 53
    blockDmgPct = 54
    unitIds = 55
    nrOfProjectiles_2 = 56
    chance_3 = 57
    chance_4 = 58
    dmgPct = 59
    maxSummons = 60
    factionId = 61
    affectedUnitIds = 62
    damageProfile_2 = 63
    extraPierce = 64
    armorReduction = 65
    armorReduction2 = 66
    nrOfHeroes = 67
    range_2 = 68
    nrOfRounds = 69
    summonId = 70
    minNrOfHits = 71
    maxNrOfHits = 72
    pierceRatio = 73
    extraArmorPct = 74
    hitsReduction_2 = 75
    dmgPctReduction = 76
    hitsReduction_3 = 77
    affectedDamageProfile = 78
    healthPct = 79
    shieldPct = 80
    movement = 81
    excludedDamageProfiles = 82
    dmgPctReduction_2 = 83
    nrOfSummons_2 = 84
    hitsReductionPct = 85
    minSummons = 86
    minSummons_2 = 87
    maxSummons_2 = 88
    nrOfAttacks = 89
    unitDamageProfile = 90
    knockbackRange = 91
    extraDmgPct_2 = 92
    totalBlockChance = 93
    totalChance = 94
    auraRange = 95
    nrOfShells = 96
    currentHp = 97
    buffMaxLevel = 98
    stunChance = 99
    extraHits = 100
    damageProfile_3 = 101
    nrOfHits_3 = 102
    nrOfProjectiles_3 = 103
    initialCooldownTurns = 104
    effectTurns = 105
    effectTurns_2 = 106
    munitionsCost = 107
    shieldHp = 108
    unitId_3 = 109
    amount = 110
    cooldownReduction = 111
    cooldownIncrease = 112
    cooldownIncrease_2 = 113
    dmgReductionPct = 114
    effectLevel = 115
    repairPct = 116
    maxAdjacentTargets = 117
    effectLevel_2 = 118
    nrOfRounds_2 = 119
    nrOfUnits = 120
    nrOfUnits_2 = 121
    nrOfUnitIds = 122
    unitId_4 = 123
    unitId_5 = 124
    unitId_6 = 125
    heroId = 126
    trait = 127
    affectedDamageProfile_2 = 128
    nrOfUnits_3 = 129
    nrOfUnits_4 = 130
    armorReductionPct = 131
    minHpPct = 132
    maxHpPct = 133
    extraPierceRatio = 134
    armorPct = 135
    tilesTraversed = 136
    nrOfRepairs = 137
    extraCritDmg = 138
    maxNrOfAttacks = 139
    affectedUnitId = 140
