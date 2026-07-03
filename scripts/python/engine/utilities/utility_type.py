"""`UtilityType` — enum natif des utilites d'IA (dump.cs gqfc5mff6c, `enum UtilityType` TypeDefIndex 12038).

Mirror 1:1 des valeurs natives. Sert de cle a `UtilitiesDatabase` (GetUtility) et d'argument a
`GetMovementUtility`. Les COMPOSITES (Tile=7, Damage=34, UnitMovement=6, …) sont des instances
`ComposedUtility` enregistrees a ces valeurs — PAS des classes dediees."""
from __future__ import annotations

from enum import IntEnum


class UtilityType(IntEnum):
    Spawn = 0
    SingleAdjacency = 1
    TriggeredAbilities = 2
    UnitSpecificBehaviours = 3
    TriggeredAbilitiesNonOwner = 4
    UnitMovementFromTemporary = 5
    UnitMovement = 6
    Tile = 7
    Elevation = 8
    TileEffects = 9
    UnitEffectsAdjacent = 10
    UnitEffectsSurrounding = 11
    UnitEffectsRanged = 12
    TemporaryTile = 13
    TilePendingBlockableSummon = 14
    RangedAdjacentEnemy = 15
    MinDistanceToClosestEnemy = 16
    MaxDistanceToUnitTile = 17
    MaxDistanceToEnemies = 18
    SteppableUnit = 19
    KustomForceField = 20
    DefenderOfTheGreaterGood = 21
    SaviorProtocols = 22
    MoltenForm = 23
    CapturePoint = 24
    Contaminated = 25
    PowerUp = 26
    DislikeStartingTilesUtility = 27   # nom natif de la CONSTANTE d'enum (le meme que la classe)
    DespoiledGround = 28
    SummonDislikeDoorOpening = 29
    HeroLikeDoorOpening = 30
    EnvEndBombardment = 31
    MovementSuggestion = 32
    TileDistance = 33
    Damage = 34
    DamageDealt = 35
    KillUnit = 36
    OverkillUnit = 37
    DislikeObjects = 38
    DislikeEnvironmentUnits = 39
    OnlyImperviousUnitIfCanBeDamaged = 40
    EnemyOnTerritoryTile = 41
    AttackTargetWithEffect = 42
    DislikeBoss = 43
    Heal = 44
    AddedTileEffects = 45
    Repair = 46
    RepairedAmount = 47
    DanceOfDaggers = 48
    AdjacentQuickSlash = 49
    RoyalGuard_AvoidAdjacentEnemies = 50
    SwornProtector_AvoidAdjacentEnemies = 51
    DevoutPush_AdjacentRangedEnemies = 52
    RammingSpeed_MostAdjacentEnemies = 53
    WireweaveNet_FirstAttack = 54
    MV71SniperDroneSquad_ClosestToParent = 55
    EarlyWarningOverride_SpawnSummon = 56
    DoctrinaImperatives_AttractMechanicals = 57
    EchoesFromTheWarp_FriendliesAvoidGhost = 58
    OptimizedGait_AdjacentFriends = 59
    Phantasm_AvoidFriendlyPhantasm = 60
    BioMinefield_MoveTowardsTarget = 61
    MasterOfTheTutelaries_MoveTowardsTarget = 62
    HypersensoryAbilities_BonusForFirstAttack = 63
    DecoysAndMisdirection_AttractToDecoys = 64
    TheArdentBlade_Geminae = 65
    LeadingTheCharge_ChargeTile = 66
