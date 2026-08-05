"""`StepType` -- le vocabulaire des ACTIONS du flux de replay natif.

Mirror 1:1 de `IdunBattle.Streams.StepType`, le 1er argument de
`IdunBattle.Streams.StreamDispatcher$$Action`. C'est ce qui s'ecrit apres `Action=`.

⚠ Une `Action=` existe A PROFONDEUR 0, hors de tout groupe : `StreamCache$$Action` n'exige
aucun groupe ouvert (mesure #477-r11 : `PrepareTurn`, `ChangeStats`, `FinishMatch`). Un
parseur qui exige un groupe ouvert rejette du flux VALIDE.
"""
from __future__ import annotations

from enum import IntEnum


class StepType(IntEnum):
    """`IdunBattle.Streams.StepType` -- VERBATIM du build (62 valeurs).

    Re-derivable : `data/symbols/<CURRENT>/frida/enums.tsv`, ligne `IdunBattle.Streams.StepType`.
    """

    None_ = 0
    StartMatch = 1
    StartTurn = 2
    ChangePosition = 3
    UnitDamaged = 4
    HealInfo = 5
    RepairInfo = 6
    AddPlayer = 7
    AddTile = 8
    AddUnit = 9
    AddMachine = 10
    RemoveUnit = 11
    ChangeStats = 12
    ChangeAbility = 13
    FinishMatch = 14
    ReceiveEffect = 15
    LoseEffect = 16
    ActivateEffect = 17
    DeactivateEffect = 18
    UpdateEffect = 19
    UpdateEffectTurns = 20
    AttackTile = 21
    UnitDraft = 22
    SpawnPointDraft = 23
    ExtraAttackDamage = 24
    DirectlyKillUnit = 25
    LootInfo = 26
    RemoveUnitFromTiles = 27
    Revive = 28
    Info = 29
    TerritoryCapture = 30
    TerritoryScoreModifierChange = 31
    AddVictoryPoints = 32
    RemoveVictoryPoints = 33
    UpdateAbilityModification = 34
    TransferDamage = 35
    Resurrect = 36
    OverrideMovementTarget = 37
    PrepareTurn = 38
    ChangeUnitOwner = 39
    UpdateEffectLevel = 40
    UnitFled = 41
    RotateUnit = 42
    AddMachinePlatform = 43
    MachineHit = 44
    RemoveMachine = 45
    SpendAmmo = 46
    ChangePlayerReinforcement = 47
    ChangeUnitConfig = 48
    AddScore = 49
    SetTempPlayer = 50
    ResetTempPlayer = 51
    AddReinforcementShield = 52
    PickUnit = 53
    ChangeResurrectDraftingPoints = 54
    AddOrUpdateShield = 55
    RemoveShield = 56
    RevealFogOfWar = 57
    HideDoorActivationTile = 58
    OpenDoor = 59
    ReaddMachine = 60
    PlayerInitialRarity = 61
