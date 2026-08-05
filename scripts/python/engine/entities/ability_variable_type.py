"""`AbilityVariableType` -- l'index des VARIABLES par niveau d'une ability
(`IdunBattle.Configuration.AbilityVariableType`).

Mirror 1:1 de l'enum natif, re-derivable de `data/symbols/<build>/frida/enums.tsv`.

CE QU'IL DESIGNE, ET COMMENT ON LE SAIT. C'est le type DECLARE du premier parametre des
accesseurs de variable :

    IdunBattle.Configuration.AbilityConfiguration.GetVariableForLevel
        (variableType : IdunBattle.Configuration.AbilityVariableType, ...)
    IdunBattle.Configuration.AbilityConfiguration.TryGetVariableForLevel   (idem)
    idun.meta.StatefulAbilityConfiguration.GetVariableForLevel             (idem)

LU dans la table des methodes du build (`frida/methods.tsv`), pas deduit d'un nom court.

⚠ NE PAS LE CONFONDRE AVEC `AbilityConstantType` -- cf. l'avertissement symetrique de
`ability_constant_type.py`. Le discriminant est l'ACCESSEUR appele au site, jamais l'ordinal.

⚠ LE BUILD SAUTE LA VALEUR 132 : la table va de 0 a 158 pour 158 membres. Un mirror qui
« comblerait » le trou decalerait tout ce qui suit -- c'est exactement la forme RENUMEROTE que
`probe_313` existe pour attraper.
"""
from __future__ import annotations

from enum import IntEnum


class AbilityVariableType(IntEnum):
    """`IdunBattle.Configuration.AbilityVariableType` -- VERBATIM du build (158 valeurs).

    Re-derivable : `data/symbols/<CURRENT>/frida/enums.tsv`, cle `IdunBattle.Configuration.AbilityVariableType`.
    Sous garde de `probe_313_enum_mirror_bijection.py` (bijection exigee)."""

    maxAdjacentTargets = 0
    maxNrOfJumps = 1
    minProjectiles = 2
    maxProjectiles = 3
    nrOfProjectiles = 4
    baseDmg = 5
    minBaseDmg = 6
    maxBaseDmg = 7
    extraDmg = 8
    extraDmg_2 = 9
    extraDmgPct = 10
    dmg = 11
    minDmg = 12
    maxDmg = 13
    minAdjacentDmg = 14
    maxAdjacentDmg = 15
    dmgToAdjacent = 16
    adjacentDmg = 17
    dmgReduction = 18
    extraHits = 19
    blockDmg = 20
    blockChance = 21
    blockDmg_2 = 22
    extraChance = 23
    armor = 24
    armorToRepair = 25
    armorToSteal = 26
    extraArmor = 27
    extraHpToHeal = 28
    hp = 29
    extraHp = 30
    hpToSteal = 31
    hpToHeal = 32
    hpToHeal_1 = 33
    hpToHeal_2 = 34
    hpForFire = 35
    hpToRepair = 36
    minHp = 37
    hpPct = 38
    shieldHp = 39
    chanceOfIce = 40
    summonHp = 41
    summonDmg = 42
    summonArmor = 43
    objectHp = 44
    unitToSpawn = 45
    hpReduction = 46
    nrOfHits = 47
    armorReduction = 48
    maxSummons = 49
    landmineDmg = 50
    extraSummons = 51
    minLandmines = 52
    maxLandmines = 53
    minDmg_2 = 54
    maxDmg_2 = 55
    minDmg_3 = 56
    maxDmg_3 = 57
    chance = 58
    chance_2 = 59
    goldMin = 60
    goldMax = 61
    extraBlockChance = 62
    extraPierceRatio = 63
    armorIgnored = 64
    extraCritChance = 65
    extraCritDmg = 66
    summonHp_2 = 67
    summonDmg_2 = 68
    summonArmor_2 = 69
    dmgReductionPct = 70
    maxHpToHeal = 71
    extraDmgPct_2 = 72
    extraMaxDmg = 73
    dmgPct = 74
    hpToHealPct = 75
    buffMaxLevel = 76
    dmg_2 = 77
    nrOfAttacks = 78
    nrOfSummons = 79
    nrOfCrits = 80
    pierceRatio = 81
    nrOfKills = 82
    range = 83
    summonCritChance = 84
    summonBlockDmg = 85
    summonBlockChance = 86
    summonCritDmg = 87
    summonCritChance_2 = 88
    summonBlockDmg_2 = 89
    summonBlockChance_2 = 90
    summonCritDmg_2 = 91
    summonAbilityLevel = 92
    extraArmorPct = 93
    dmgPctReduction = 94
    summonHp_3 = 95
    summonDmg_3 = 96
    summonArmor_3 = 97
    summonCritChance_3 = 98
    summonBlockDmg_3 = 99
    summonBlockChance_3 = 100
    summonCritDmg_3 = 101
    nrOfTiles = 102
    effectLevel = 103
    nrOfRounds = 104
    spawnDmg = 105
    spawnHp = 106
    spawnArmor = 107
    spawnCritChance = 108
    spawnCritDmg = 109
    spawnBlockChance = 110
    spawnBlockDmg = 111
    spawnDmg_2 = 112
    spawnHp_2 = 113
    spawnArmor_2 = 114
    spawnCritChance_2 = 115
    spawnCritDmg_2 = 116
    spawnBlockChance_2 = 117
    spawnBlockDmg_2 = 118
    spawnDmg_3 = 119
    spawnHp_3 = 120
    spawnArmor_3 = 121
    spawnCritChance_3 = 122
    spawnCritDmg_3 = 123
    spawnBlockChance_3 = 124
    spawnBlockDmg_3 = 125
    spawnDmg_4 = 126
    spawnHp_4 = 127
    spawnArmor_4 = 128
    spawnCritChance_4 = 129
    spawnCritDmg_4 = 130
    spawnBlockChance_4 = 131
    spawnBlockDmg_4 = 133
    spawnDmg_5 = 134
    spawnHp_5 = 135
    spawnArmor_5 = 136
    spawnCritChance_5 = 137
    spawnCritDmg_5 = 138
    spawnBlockChance_5 = 139
    spawnBlockDmg_5 = 140
    spawnDmg_6 = 141
    spawnHp_6 = 142
    spawnArmor_6 = 143
    spawnCritChance_6 = 144
    spawnCritDmg_6 = 145
    spawnBlockChance_6 = 146
    spawnBlockDmg_6 = 147
    maxNrOfActivations = 148
    maxHp = 149
    shieldPct = 150
    critDmgReduction = 151
    critChanceReduction = 152
    extraPierce = 153
    nrOfUnits = 154
    nrOfRepairs = 155
    hp_2 = 156
    extraArmor_2 = 157
    extraDmg_3 = 158
