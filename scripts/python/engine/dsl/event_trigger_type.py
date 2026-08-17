"""engine.dsl.event_trigger_type — enum natif `EventTriggerType` (id <-> nom).

Mirror 1:1 de `IdunBattle.DSL.EventTriggerType`, l'argument de
`DSLFactory.On(EventTriggerType triggerType, ...)`. LA source unique des ids d'evenement de
trigger — remplace les constantes `TRIGGER_*` eparses (meme demarche que `UnitTrait` / `UtilityType`).

**SOURCE RE-DERIVABLE** : `data/symbols/<CURRENT>/frida/enums.tsv`, ligne
`IdunBattle.DSL.EventTriggerType`. Ne PAS citer un TypeDefIndex de `dump.cs` — celui de l'ancien
port (11646, build `gqfc5mff6c`) renvoyait a un artefact qui n'existe plus et n'etait pas
verifiable.

⚠ **CES VALEURS SONT IMPLICITES, DONC ELLES SE DECALENT.** Mesure du 2026-07-29
(`gqfc5mff6c` -> `rnca9r7q6c`) : le jeu a RETIRE `ArmorChanged` (qui valait 40) au MILIEU de la
liste, ce qui a decale de -1 les **36 membres suivants** (41..76 -> 40..75) ; les 40 premiers
n'ont pas bouge et il n'y a eu aucun ajout. Au prochain changement de build, confronter
**NOM PAR NOM** contre `enums.tsv` — jamais supposer un decalage uniforme, et surtout jamais
conclure depuis le dernier membre (l'inventaire initial avait accuse `UnitTransformed`, qui ne
faisait que subir le decalage comme les autres).

Annotations sur les membres CONSOMMES par le port (runner/operations/triggers.py) :
  - NormalAttack (38) : attaque NORMALE (per-attaque, voie normale) -> ecoute Psyker (splash Smite).
  - Attack (9)        : attaque d'ABILITY (per-attaque, voie ability/splash) -> ecoute reset ActOfFaith
                        (`IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaith_RemoveEffectAbility$$CreateTrigger = On(9) & OwnerIsCaster & WasCrit & HasEffect`).
  - AttackHit (8)     : after-HIT per-coup (`IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` dispatche 8 TOUJOURS).
  - UnitBlocked (60)  : dispatche par `EvaluateAfterHitTriggers` sur la branche `param_6`.
                        ⚠ le littéral a lire dans le decompile vaut `0x3c` sur `rnca9r7q6c` — il
                        valait `0x3d` avant le retrait d'`ArmorChanged`. Le natif etant recompile,
                        SON literal se decale aussi : ne pas transposer un chiffre d'un build a
                        l'autre.
                        ⚠ l'ancien port l'appelait a tort `TRIGGER_AFTER_CRIT`/"after-crit" (mislabel :
                        la branche est UnitBlocked ; param_6 = vraisemblablement le flag BLOCK,
                        a confirmer via le caller). Non consomme par le port.
  - UnitAfterMove (4) : after-move (`EvaluateAfterMoveTriggers`) -> Overwatch, RangedAutoAttack.
  - PreUnitDeath (1)  : mort (OnPreDeath/OnDeath IdunBattleLogic.Entities.DSLTriggers$$OnDeathEvent) -> FinalJustice, TheBetrayer, ActOfFaith accum.
  - TurnStart_Actions (22)            : `On(0x16)`, debut de tour (StartTurnOperation IdunBattle.Operations.StartTurnOperation$$Execute).
  - TurnStart_EffectActivation (18)   : `On(0x12)` tick de tour -> Contaminated re-apply (IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$CreateHandleTriggerAbilitiesInternal).
  - TurnStart_EnvironmentEffects (20) : `On(0x14)` tick de tour -> Fire DoT + DryBush spread (IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateTrigger).
"""
from __future__ import annotations

from enum import IntEnum


class EventTriggerType(IntEnum):
    """`IdunBattle.DSL.EventTriggerType`. Valeur == id natif passe a `DSLFactory.On`.

    76 membres sur le build `rnca9r7q6c` (77 sur `gqfc5mff6c`, cf. le retrait d'`ArmorChanged`)."""
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
    # --- `ArmorChanged` occupait 40 sur `gqfc5mff6c` ; RETIRE par la MAJ du 2026-07-29.
    #     Tout ce qui suit est decale de -1. Aucun consommateur ne le nommait.
    UnitFinishedTurn = 40
    UnitFinishedTurnNormally = 41
    PreUnitAbility = 42
    UnitHealed = 43
    UnitHealedWithRemoveEffects = 44
    UnitRevived = 45
    UnitResurrected = 46
    UnitMemberDeath = 47
    UnitRepaired = 48
    SpecificAbilityInit = 49
    UnitAdded = 50
    PreUnitFled = 51
    UnitFled = 52
    PostUnitKill = 53
    UnitDefeated = 54
    AttackChanged = 55
    BlockDamageChanged = 56
    PreDamageTaken = 57
    PhaseEnd = 58
    UnitBecameTargetable = 59
    UnitBlocked = 60
    PreEffectAdded = 61
    EffectAdded = 62
    PreEffectRemoved = 63
    EffectRemoved = 64
    InitialMatchUnitAdded = 65
    FinalDamage = 66
    PreMachineDestroyed = 67
    MachineDestroyed = 68
    UnitConfigChanged = 69
    UnitBecameUntargetable = 70
    CompletedSpawningWave = 71
    PreTerritoryCaptured = 72
    TerritoryCaptured = 73
    AttackInAtomicGroup = 74
    UnitTransformed = 75
