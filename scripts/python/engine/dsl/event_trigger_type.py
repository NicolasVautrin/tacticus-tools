"""engine.dsl.event_trigger_type — enum natif `EventTriggerType` (id <-> nom).

Mirror 1:1 de l'enum natif `EventTriggerType` (dump.cs `gqfc5mff6c`, TypeDefIndex 11646), l'argument
de `DSLFactory.On(EventTriggerType triggerType, ...)`. LA source unique des ids d'evenement de
trigger — remplace les constantes `TRIGGER_*` eparses (meme demarche que `UnitTrait` / `UtilityType`).

Annotations sur les membres CONSOMMES par le port (runner/operations/triggers.py) :
  - NormalAttack (38) : attaque NORMALE (per-attaque, voie normale) -> ecoute Psyker (splash Smite).
  - Attack (9)        : attaque d'ABILITY (per-attaque, voie ability/splash) -> ecoute reset ActOfFaith
                        (`@181219f90 = On(9) & OwnerIsCaster & WasCrit & HasEffect`).
  - AttackHit (8)     : after-HIT per-coup (`EvaluateAfterHitTriggers @180e25fc0` dispatche 8 TOUJOURS).
  - UnitBlocked (61)  : dispatche par `EvaluateAfterHitTriggers` sur la branche `param_6` (0x3d).
                        ⚠ l'ancien port l'appelait a tort `TRIGGER_AFTER_CRIT`/"after-crit" (mislabel :
                        la valeur 0x3d=61 est UnitBlocked ; param_6 = vraisemblablement le flag BLOCK,
                        a confirmer via le caller). Non consomme par le port.
  - UnitAfterMove (4) : after-move (`EvaluateAfterMoveTriggers`) -> Overwatch, RangedAutoAttack.
  - PreUnitDeath (1)  : mort (OnPreDeath/OnDeath @180df7ad0) -> FinalJustice, TheBetrayer, ActOfFaith accum.
  - TurnStart_Actions (22)            : `On(0x16)`, debut de tour (StartTurnOperation @180ea3fb0).
  - TurnStart_EffectActivation (18)   : `On(0x12)` tick de tour -> Contaminated re-apply (@180f3a1d0).
  - TurnStart_EnvironmentEffects (20) : `On(0x14)` tick de tour -> Fire DoT + DryBush spread (@18121e390).
"""
from __future__ import annotations

from enum import IntEnum


class EventTriggerType(IntEnum):
    """`EventTriggerType` @dump.cs TypeDefIndex 11646. Valeur == id natif passe a `DSLFactory.On`."""
    UnitDeath = 0
    PreUnitDeath = 1
    PreUnitDeath_2 = 2
    PendingDeathAdded = 3
    UnitAfterMove = 4
    PreAttack = 5
    PreAttackHit = 6
    PreAttackDamageHit = 7
    AttackHit = 8
    Attack = 9
    AttackDamageAttack = 10
    UnitAbility = 11
    UnitActiveAbility = 12
    UnitTriggeredAbility = 13
    UnitPostAbility = 14
    DamageTaken = 15
    DamageDealt = 16
    PostDamageTaken = 17
    TurnStart_EffectActivation = 18
    TurnStart_Other = 19
    TurnStart_EnvironmentEffects = 20
    TurnStart_DelayedAttacks = 21
    TurnStart_Actions = 22
    TurnEnd = 23
    MatchSetup = 24
    MatchInit = 25
    MatchStart = 26
    MatchEnd = 27
    ArrivedAtFinalTile = 28
    UnitPositionChanged_2 = 29
    HealthChanged = 30
    PreUnitMove = 31
    Custom = 32
    AbilityInit = 33
    PostAbilityInit = 34
    UnitDisplaced = 35
    UnitPositionChanged_1 = 36
    UnitRemoved = 37
    NormalAttack = 38
    ShieldChanged = 39
    ArmorChanged = 40
    UnitFinishedTurn = 41
    UnitFinishedTurnNormally = 42
    PreUnitAbility = 43
    UnitHealed = 44
    UnitHealedWithRemoveEffects = 45
    UnitRevived = 46
    UnitResurrected = 47
    UnitMemberDeath = 48
    UnitRepaired = 49
    SpecificAbilityInit = 50
    UnitAdded = 51
    PreUnitFled = 52
    UnitFled = 53
    PostUnitKill = 54
    UnitDefeated = 55
    AttackChanged = 56
    BlockDamageChanged = 57
    PreDamageTaken = 58
    PhaseEnd = 59
    UnitBecameTargetable = 60
    UnitBlocked = 61
    PreEffectAdded = 62
    EffectAdded = 63
    PreEffectRemoved = 64
    EffectRemoved = 65
    InitialMatchUnitAdded = 66
    FinalDamage = 67
    PreMachineDestroyed = 68
    MachineDestroyed = 69
    UnitConfigChanged = 70
    UnitBecameUntargetable = 71
    CompletedSpawningWave = 72
    PreTerritoryCaptured = 73
    TerritoryCaptured = 74
    AttackInAtomicGroup = 75
    UnitTransformed = 76
