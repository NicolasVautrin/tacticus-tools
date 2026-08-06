"""`GroupType` -- le vocabulaire des GROUPES du flux de replay natif.

Mirror 1:1 de `IdunBattle.Streams.GroupType`, le 1er argument de
`IdunBattle.Streams.StreamDispatcher$$StartGroup`. C'est ce qui s'ecrit apres `Group=` sur
la ligne d'ouverture d'un groupe -- `IdunBattle.BattleStream.Loggers.StreamCache$$StartGroup`
formate l'enum, donc le NOM du membre, jamais son ordinal.

⚠ LE PERIMETRE SE DERIVE DE CET ENUM, JAMAIS DE L'OBSERVE. Le recensement live de #477-r11
n'avait vu que 16 de ces membres sur deux batailles : un comparateur calibre sur l'observe
serait muet sur les autres, SANS LE DIRE (cf. `#477-r13`).
"""
from __future__ import annotations

from enum import IntEnum


class GroupType(IntEnum):
    """`IdunBattle.Streams.GroupType` -- VERBATIM du build (104 valeurs).

    Re-derivable : `data/symbols/<CURRENT>/frida/enums.tsv`, ligne `IdunBattle.Streams.GroupType`.
    """

    None_ = 0
    AddUnit = 1
    AddMachine = 2
    System_GameSetup = 3
    System_StartMatch = 4
    System_ProcessDeaths = 5
    System_ProcessRemovals = 6
    System_UnitDrafting = 7
    System_RerollDraftOption = 8
    System_StartTurn = 9
    System_PickUnit = 10
    User_MoveUnit = 11
    User_UseAbility = 12
    User_PlaceUnit = 13
    User_RemoveUnit = 14
    User_EndTurn = 15
    User_Surrender = 16
    User_CheatAmmo = 17
    Test_AbilityDamage = 18
    Test_DirectDamage = 19
    Test_MachineDamage = 20
    Ability_Power = 21
    Effect_Refresh = 22
    User_Effect_Manipulation = 23
    SpawnUnitsOfTurn = 24
    SpawnUnitsOfWave = 25
    Damage = 26
    TileDamage = 27
    MachineDamage = 28
    DamageChain = 29
    DarkDragon = 30
    Ability_Heal = 31
    Ability_Attack = 32
    Ability_Attack_2 = 33
    Ability_Summon = 34
    Ability_Move = 35
    Ability_Displace = 36
    Ability_Buff = 37
    Ability_Stance = 38
    Ability_State = 39
    Ability_Other = 40
    ResurrectUnit = 41
    Ability_AtomicGroup = 42
    EffectAdditionalHits = 43
    ReviveUnit = 44
    Attack = 45
    RarityCapTransform = 46
    StartTurn = 47
    EndTurn = 48
    Ability_CustomGroup = 49
    HornOfDespair_LightUnits = 50
    HornOfDespair_DarkUnits = 51
    HornOfDespair_Darkness = 52
    SummonIceElemental_Spawn = 53
    AirshipStrike_Attack = 54
    EjectEject = 55
    MechRepair = 56
    RocketBarrage = 57
    Zinger = 58
    ZingerAbility = 59
    VolatileRockets = 60
    NormalAttack_AtomicDamage = 61
    StormOfFlensingBlades_Attacks = 62
    MortisRound_AttackAndPush = 63
    PrecisionShot_Attack = 64
    MultiThreatEliminator_Attack = 65
    ArmoriumCherub_Attack = 66
    FragBomb_Damage = 67
    StormOfWrath_Attack = 68
    BringerOfDespair_Attacks = 69
    PsychicMaelstrom_Attack = 70
    SpawnTermagants_Spawn = 71
    SupremeCommander_Spawn = 72
    Drachnyen_AtomicGroup = 73
    PlagueWind_Attack = 74
    PlagueWind_Attack1 = 75
    PlagueWind_Attack2 = 76
    PlagueWind_Attack3 = 77
    FrenziedFiring = 78
    ThunderousAssault_AtomicGroup = 79
    GetEmRuntz_AtomicGroup = 80
    IncendiarySheels_AtomicGroup = 81
    TemplarInitiateNormalAttack_AtomicGroup = 82
    DrachnyenNormalAttack_AtomicGroup = 83
    BasiliskBarrage = 84
    StranglethornCannon_AtomicGroup = 85
    SanctorumMissile_Attack = 86
    ScythingTalons_AtomicGroup = 87
    ProperKilly_Attack1 = 88
    ProperKilly_Attack2 = 89
    EreWeGo_AtomicGroup = 90
    DarkTalon = 91
    MortarionsPlagueWind_Attack = 92
    MortarionsPlagueWind_Attack1 = 93
    MortarionsPlagueWind_Attack2 = 94
    MortarionsPlagueWind_Attack3 = 95
    AnvilShieldBlock = 96
    Doombolt = 97
    SpiritualLeader_SummonDecoy = 98
    SpiritualLeader_SummonNeophyte = 99
    CultDemagogue_SummonDecoy = 100
    CultDemagogue_SummonNeophyte = 101
    RevealFogOfWar = 102
    TerritoryCapture = 103

# TEMP mesure #486-r11
