# Carte du vocabulaire DSL : couverture du port, ponderee par le levier (#326)

> **DOCUMENT GENERE** -- `python scripts/python/probe_326_dsl_join.py [--p1 <table #325>]`.
> En cas de conflit au rebase : **on REGENERE, on ne fusionne pas**. Les chiffres se periment a
> chaque build et a chaque port ; les re-deriver plutot que citer cette page.

Chaine de production (trois probes, trois tables machine dans `logs/`) :

| etage | probe | sortie | question |
|---|---|---|---|
| A1 | `probe_326_dsl_primitive_inventory.py` | `logs/326_dsl_primitives_native.tsv` | quelles PRIMITIVES le build expose-t-il ? |
| A2 | `probe_326_dsl_port_matching.py` | `logs/326_dsl_primitive_coverage.tsv` | laquelle est PORTEE, par quel artefact ? |
| B | `probe_326_ability_reachability.py` | `logs/326_ability_reachability.tsv` | quelle ability est CONFRONTABLE, par quel chemin ? |
| C | `probe_326_dsl_join.py` | `logs/326_dsl_primitive_leverage.tsv` | quelle primitive NON PORTEE debloque le plus d'abilities confrontables ? |


Build mesure : `rnca9r7q6c`. Table phase 1 (#325) : **`docs/rl/dsl-usage/dsl-usage-edges.tsv`**.

## 1. Couverture du port, par famille de primitive

| famille | PORTE | PORTE_ALIAS_FACADE | PORTE_HORS_FACADE | PORTE_ARTEFACT_AUTRE | PORTE_SANS_CITATION | CITE_A_QUALIFIER | NON_PORTE | total |
|---|---|---|---|---|---|---|---|---|
| AbilityBehaviour | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 2 |
| AbilityTrigger | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 3 |
| DSLBehaviors | 48 | 5 | 5 | 0 | 0 | 12 | 57 | 127 |
| DSLFactory | 0 | 0 | 0 | 0 | 0 | 2 | 3 | 5 |
| DSLFormulas | 31 | 1 | 9 | 0 | 3 | 11 | 58 | 113 |
| DSLSelectors | 67 | 3 | 7 | 0 | 0 | 12 | 106 | 195 |
| DSLTriggers | 36 | 3 | 38 | 1 | 0 | 0 | 87 | 165 |
| TargetsSelector | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 3 |
| **TOTAL** | **182** | **20** | **59** | **1** | **3** | **37** | **311** | **613** |

**Porte atteste** (`PORTE` + `PORTE_ALIAS_FACADE` + `PORTE_HORS_FACADE`) = **261 / 613**.
`CITE_A_QUALIFIER` (37) n'est NI porte NI absent : l'artefact apparait dans `engine/**` sans porteur Python identifiable. C'est un etat A TRANCHER, pas un zero.

**31 verdicts viennent de `docs/rl/dsl-port-attestations.tsv`** -- le canal ou un HUMAIN tranche ce qu'aucune heuristique de nom ne peut apparier (un PREDICAT collapse dans un `matches()`). Chaque ligne est re-verifiee a chaque run (symbole present dans le build, ancre resolue, primitive citee) ; detail : `docs/rl/case-337-dsl-triggers-attestation.md`.

## 2. Joignabilite des abilities (etage B)

| verdict | abilities |
|---|---:|
| CONFRONTABLE_POOL | 263 |
| SANS_PORTEUR_MESURE | 82 |
| HORS_KIT_UNITE | 82 |
| NON_PERTINENT_NPC | 57 |
| CONFRONTABLE_INJECTION | 53 |
| CONFRONTABLE_SUMMON | 36 |
| SUMMON_SANS_SUMMONER_MESURE | 32 |
| CONFRONTABLE_RELIQUE_A_EQUIPER | 24 |
| CONFRONTABLE_SUMMON_INJECTION | 4 |

La voie RELIQUE a **trois** etats et non deux (`RELIQUE_EQUIPEE_SEED` / `RELIQUE_POOL_A_EQUIPER` / `RELIQUE_HORS_POOL`) : « porteur dans le pool » ne dit pas « arrive en bataille AVEC sa relique ».

## 3. Classement des primitives NON PORTEES par levier

Aretes de la table phase 1 : **11180** | **retenues : 8966 (80.2 %)** | rejetees cote primitive : 0 | rejetees cote owner : 2214.

Les rejets sont VENTILES, pas jetes -- par `owner_kind` de la phase 1 : `ability` 1239, `effect` 586, `dsl-internal` 217, `utility` 120, `other` 52.

Ce qui reste non resolu est **structurel** : bases abstraites (`A*Ability`,
`*Base`), abilities d'ENVIRONNEMENT (`Env*`, `PowerUp*`), internes du DSL
lui-meme, et couche `utility`. Aucune ne repond a un nom d'ability du
gameconfig -- ce n'est pas un defaut de lecture, c'est qu'elles n'en ont pas.


| # | famille | primitive | verdict port | abilities | dont confrontables | dont pool |
|---:|---|---|---|---:|---:|---:|
| 1 | DSLFormulas | `Direct` | CITE_A_QUALIFIER | 149 | 101 | 83 |
| 2 | DSLFormulas | `Multiply` | PORTE_SANS_CITATION | 65 | 54 | 35 |
| 3 | DSLFormulas | `Sum` | PORTE_SANS_CITATION | 58 | 43 | 32 |
| 4 | DSLSelectors | `Direct` | CITE_A_QUALIFIER | 42 | 33 | 28 |
| 5 | DSLFormulas | `Min` | PORTE_SANS_CITATION | 18 | 17 | 13 |
| 6 | DSLBehaviors | `IfAlive` | CITE_A_QUALIFIER | 20 | 14 | 11 |
| 7 | DSLFormulas | `Subtract` | NON_PORTE | 14 | 13 | 6 |
| 8 | DSLFactory | `Triggered` | NON_PORTE | 19 | 12 | 8 |
| 9 | DSLFormulas | `GetPersistentData` | CITE_A_QUALIFIER | 19 | 12 | 3 |
| 10 | DSLBehaviors | `AddDynamicStatModifierEffectToOwner` | CITE_A_QUALIFIER | 12 | 9 | 6 |
| 11 | DSLBehaviors | `SetPersistentData` | CITE_A_QUALIFIER | 15 | 9 | 4 |
| 12 | DSLSelectors | `DamageProfileFromConfig` | CITE_A_QUALIFIER | 16 | 9 | 6 |
| 13 | DSLBehaviors | `AddFlag` | NON_PORTE | 9 | 8 | 4 |
| 14 | DSLTriggers | `OnDeath` | NON_PORTE | 12 | 8 | 6 |
| 15 | DSLBehaviors | `AddStaticStatModifierEffectToOwner` | NON_PORTE | 10 | 7 | 3 |
| 16 | DSLBehaviors | `ClearPersistentData` | CITE_A_QUALIFIER | 8 | 7 | 1 |
| 17 | DSLBehaviors | `UseNormalAttackIfAble` | CITE_A_QUALIFIER | 8 | 7 | 6 |
| 18 | DSLSelectors | `None` | NON_PORTE | 8 | 7 | 6 |
| 19 | DSLSelectors | `NormalUnits` | CITE_A_QUALIFIER | 10 | 7 | 6 |
| 20 | DSLSelectors | `UnitsWithRarity` | NON_PORTE | 7 | 7 | 5 |
| 21 | DSLTriggers | `DamageProfileIs` | NON_PORTE | 11 | 7 | 5 |
| 22 | DSLBehaviors | `AddPersistentData` | NON_PORTE | 10 | 6 | 0 |
| 23 | DSLSelectors | `CreateSnapshot` | NON_PORTE | 6 | 6 | 4 |
| 24 | DSLSelectors | `FreeTilesOrAdjacentFreeTiles` | NON_PORTE | 6 | 6 | 3 |
| 25 | DSLSelectors | `SortTargetsByDamagePredictionSelector` | NON_PORTE | 6 | 6 | 5 |
| 26 | DSLTriggers | `CurrentAttackDamageProfilesContain` | NON_PORTE | 7 | 6 | 4 |
| 27 | DSLTriggers | `HasRarity` | NON_PORTE | 6 | 6 | 5 |
| 28 | DSLTriggers | `IsNormalUnit` | NON_PORTE | 6 | 6 | 2 |
| 29 | DSLTriggers | `get_OwnerOrOwnerTileIsTarget` | NON_PORTE | 6 | 6 | 6 |
| 30 | DSLBehaviors | `AddTemporaryAttackOverrideEffect` | NON_PORTE | 5 | 5 | 3 |
| 31 | DSLBehaviors | `ResetTemporaryAttackOverrideEffect` | NON_PORTE | 5 | 5 | 3 |
| 32 | DSLTriggers | `Contains` | NON_PORTE | 9 | 5 | 3 |
| 33 | DSLTriggers | `HasAdjacentEnemies` | NON_PORTE | 8 | 5 | 5 |
| 34 | DSLTriggers | `IsOverwatchAttack` | NON_PORTE | 5 | 5 | 4 |
| 35 | DSLTriggers | `IsUnitWithVisualId` | NON_PORTE | 6 | 5 | 3 |
| 36 | DSLBehaviors | `AddExtraBlockEffectToOwner` | CITE_A_QUALIFIER | 5 | 4 | 3 |
| 37 | DSLBehaviors | `Repeat` | NON_PORTE | 6 | 4 | 3 |
| 38 | DSLBehaviors | `ResetMovement` | NON_PORTE | 4 | 4 | 2 |
| 39 | DSLBehaviors | `UseNormalAttack` | NON_PORTE | 6 | 4 | 1 |
| 40 | DSLFormulas | `NormalAttackDamage` | CITE_A_QUALIFIER | 5 | 4 | 1 |

Lire la colonne **verdict port** : ce tableau melange volontairement les trois
etats non attestes. `PORTE_SANS_CITATION` (`Sum`, `Min`, `Multiply`) est du code qui
EXISTE mais ne cite aucun artefact -- l'action y est d'ATTESTER, pas de porter.
`CITE_A_QUALIFIER` demande une relecture. Seul `NON_PORTE` est du portage sec :

### 3bis. Le backlog SEC : primitives `NON_PORTE` avec un levier mesure

**177 primitives** `NON_PORTE` debloquent au moins une ability confrontable (sur 311 `NON_PORTE` au total -- les autres ont un levier mesure a zero, ce qui est une mesure, pas une ignorance).

| # | famille | primitive | symbole | abilities | dont confrontables | dont pool |
|---:|---|---|---|---:|---:|---:|
| 1 | DSLFormulas | `Subtract` | `IdunBattleLogic.Entities.DSLFormulas$$Subtract` | 14 | 13 | 6 |
| 2 | DSLFactory | `Triggered` | `IdunBattleLogic.Entities.DSLFactory$$Triggered` | 19 | 12 | 8 |
| 3 | DSLBehaviors | `AddFlag` | `IdunBattleLogic.Entities.DSLBehaviors$$AddFlag` | 9 | 8 | 4 |
| 4 | DSLTriggers | `OnDeath` | `IdunBattleLogic.Entities.DSLTriggers$$OnDeath` | 12 | 8 | 6 |
| 5 | DSLBehaviors | `AddStaticStatModifierEffectToOwner` | `IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffectToOwner` | 10 | 7 | 3 |
| 6 | DSLSelectors | `None` | `IdunBattleLogic.Entities.DSLSelectors$$None` | 8 | 7 | 6 |
| 7 | DSLSelectors | `UnitsWithRarity` | `IdunBattleLogic.Entities.DSLSelectors$$UnitsWithRarity` | 7 | 7 | 5 |
| 8 | DSLTriggers | `DamageProfileIs` | `IdunBattleLogic.Entities.DSLTriggers$$DamageProfileIs` | 11 | 7 | 5 |
| 9 | DSLBehaviors | `AddPersistentData` | `IdunBattleLogic.Entities.DSLBehaviors$$AddPersistentData` | 10 | 6 | 0 |
| 10 | DSLSelectors | `CreateSnapshot` | `IdunBattleLogic.Entities.DSLSelectors$$CreateSnapshot` | 6 | 6 | 4 |
| 11 | DSLSelectors | `FreeTilesOrAdjacentFreeTiles` | `IdunBattleLogic.Entities.DSLSelectors$$FreeTilesOrAdjacentFreeTiles` | 6 | 6 | 3 |
| 12 | DSLSelectors | `SortTargetsByDamagePredictionSelector` | `IdunBattleLogic.Entities.DSLSelectors$$SortTargetsByDamagePredictionSelector` | 6 | 6 | 5 |
| 13 | DSLTriggers | `CurrentAttackDamageProfilesContain` | `IdunBattleLogic.Entities.DSLTriggers$$CurrentAttackDamageProfilesContain` | 7 | 6 | 4 |
| 14 | DSLTriggers | `HasRarity` | `IdunBattleLogic.Entities.DSLTriggers$$HasRarity` | 6 | 6 | 5 |
| 15 | DSLTriggers | `IsNormalUnit` | `IdunBattleLogic.Entities.DSLTriggers$$IsNormalUnit` | 6 | 6 | 2 |
| 16 | DSLTriggers | `get_OwnerOrOwnerTileIsTarget` | `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerOrOwnerTileIsTarget` | 6 | 6 | 6 |
| 17 | DSLBehaviors | `AddTemporaryAttackOverrideEffect` | `IdunBattleLogic.Entities.DSLBehaviors$$AddTemporaryAttackOverrideEffect` | 5 | 5 | 3 |
| 18 | DSLBehaviors | `ResetTemporaryAttackOverrideEffect` | `IdunBattleLogic.Entities.DSLBehaviors$$ResetTemporaryAttackOverrideEffect` | 5 | 5 | 3 |
| 19 | DSLTriggers | `Contains` | `IdunBattleLogic.Entities.DSLTriggers$$Contains` | 9 | 5 | 3 |
| 20 | DSLTriggers | `HasAdjacentEnemies` | `IdunBattleLogic.Entities.DSLTriggers$$HasAdjacentEnemies` | 8 | 5 | 5 |
| 21 | DSLTriggers | `IsOverwatchAttack` | `IdunBattleLogic.Entities.DSLTriggers$$IsOverwatchAttack` | 5 | 5 | 4 |
| 22 | DSLTriggers | `IsUnitWithVisualId` | `IdunBattleLogic.Entities.DSLTriggers$$IsUnitWithVisualId` | 6 | 5 | 3 |
| 23 | DSLBehaviors | `Repeat` | `IdunBattleLogic.Entities.DSLBehaviors$$Repeat` | 6 | 4 | 3 |
| 24 | DSLBehaviors | `ResetMovement` | `IdunBattleLogic.Entities.DSLBehaviors$$ResetMovement` | 4 | 4 | 2 |
| 25 | DSLBehaviors | `UseNormalAttack` | `IdunBattleLogic.Entities.DSLBehaviors$$UseNormalAttack` | 6 | 4 | 1 |
| 26 | DSLSelectors | `Attackable` | `IdunBattleLogic.Entities.DSLSelectors$$Attackable` | 4 | 4 | 4 |
| 27 | DSLSelectors | `ConditionalSelector` | `IdunBattleLogic.Entities.DSLSelectors$$ConditionalSelector` | 5 | 4 | 2 |
| 28 | DSLSelectors | `UnitsWithRangedWeapons` | `IdunBattleLogic.Entities.DSLSelectors$$UnitsWithRangedWeapons` | 4 | 4 | 2 |
| 29 | DSLTriggers | `ActorHasTriggeredAbility` | `IdunBattleLogic.Entities.DSLTriggers$$ActorHasTriggeredAbility` | 7 | 4 | 2 |
| 30 | DSLBehaviors | `AddActiveAbility` | `IdunBattleLogic.Entities.DSLBehaviors$$AddActiveAbility` | 3 | 3 | 2 |

### Inventaire brut des primitives NON PORTEES (matiere de la jointure)

Sans la table phase 1 on ne peut pas les ORDONNER, mais on peut les NOMMER -- et c'est
deja ce qui manquait. Table complete (avec les `CITE_A_QUALIFIER`, non listees ici) :
`logs/326_dsl_primitive_coverage.tsv`.

**DSLBehaviors** (57) : `AddActiveAbility`, `AddBlockEnteringUnitsEffect`, `AddFlag`, `AddPersistentData`, `AddReinforcementPoint`, `AddResurrectDraftPoint`, `AddStatOverrideEffectToOwner`, `AddStaticStatModifierEffectToOwner`, `AddTemporaryAttackOverrideEffect`, `AddToPersistentDataList`, `AssignAbilityVariationToEffect`, `AttackMachine`, `AttackTiles`, `ChainAbilityDamage`, `ChainAttackDamage`, `ChainSpawnBehaviour`, `ChangeCooldown`, `ClearAllPersistentData`, `Clone`, `CloneMachine`, `DecreaseEffectLevel`, `DirectDamage`, `DisplaceUnitInAdjacentDirection`, `Do`, `ExecuteAdditionalHitsWithDamageProfileType`, `FinishAttack`, `Flee`, `FlyUnit`, `InformList`, `InvalidateCaches`, `OverrideUnitMovementTarget`, `PerformAIMovement`, `PullUnitOneTile`, `PushAwayFromBlacklistTiles`, `PushToPrioritizedTiles`, `ReAddMachine`, `RefreshEffects`, `RemoveActiveAbility`, `RemoveAllForcedAttackTargets`, `RemoveFlag`, `RemoveReservation`, `RemoveUnitFromItsTiles`, `Repeat`, `Reserve`, `ResetMovement`, `ResetPreviousPosition`, `ResetTemporaryAttackOverrideEffect`, `RotateUnit`, `SetActiveAbilityUsed`, `SetEffectLevel`, `SpawnRandom`, `StartAttack`, `Teleport`, `TransferDamage`, `TransferHit`, `Transform`, `UseNormalAttack`

**DSLFactory** (3) : `.ctor`, `Init`, `Triggered`

**DSLFormulas** (58) : `.ctor`, `AbilityLevelFromPlayerCurrentRarity`, `AttackPiercingRatio`, `AttackWeaponRange`, `AverageDistance`, `BlockedHits`, `CasterEffectPierceAddition`, `ConfigConstString`, `CriticalHitsThisTurn`, `CurrentDamage`, `CurrentPlayerTurnsStarted`, `CurrentShieldAmount`, `DamagePredictionFormula`, `DirectionTo`, `EffectRemainingTurns`, `EnhancementStack`, `EnhancementStackForTarget`, `GetAllPersistentDataCombined`, `HealthDamageFromEvent`, `IncreasedAmount`, `LastAttackDamageMade`, `MeleeAttackHits`, `MeleeWeaponHits`, `MinPathLength`, `MovementSteps`, `MultiStatValueFromEffect`, `MultiplyPercentageRecursively`, `NonLethalDamage`, `NormalAttackRange`, `NumControlledTerritory`, `Percent`, `PercentageOfStatCappedAtMax`, `PlayerAverageUnitLevel`, `PlayerTurnOrder`, `PlayerTurnsStarted`, `ReducedAmount`, `RotateVector`, `RowWithMostUnits`, `StatNegativeModification`, `Subtract`, `TimesAttackMadeThisTurn`, `TimesBlockedThisTurn`, `TimesHealedThisTurn`, `TimesReceivedAttackedThisTurn`, `TotalDamageDealt`, `TotalTurnsFinished`, `TotalTurnsWithAttacksMade`, `TriggerBoolNumber`, `TurnDefeated`, `UnitCurrentDirection`, `UnitIdFromUnit`, `UnitLevel`, `UnitRow`, `UnitsDefeatedAmount`, `UnitsTeamId`, `VectorFromAdjacentTo`, `VisualUnitIdFromUnit`, `WeaponHighestHits`

**DSLSelectors** (106) : `.ctor`, `AbilityState`, `AbilityStateFromEffect`, `AbilityStateFromLevel`, `AdjacentTilesIntersection`, `AtIndex`, `Attackable`, `AttackableEnemies`, `AttackableFriends`, `Attacker`, `BloodRunsAngerRisesWarCallsSelector`, `BondEffects`, `CanAddMultiTileUnit`, `CenterTiles`, `ClosestPositionToTarget`, `ConditionalSelector`, `CornerTiles`, `CreateSnapshot`, `CurrentAttackDamageProfile`, `CurrentPlayer`, `DeadUnits`, `Duplicate`, `EdgeTiles`, `EdgeTilesByDirection`, `EffectTarget`, `EmptyOrHasSteppableUnit`, `EmptyTiles`, `EnemyMachine`, `EnhancementTarget`, `Entities`, `EntitiesIsNotTargetOfEffect`, `EntitiesWithBondEffect`, `FilterTilesIfCanAttackTargetTileFrom`, `ForcedAttackTargets`, `FreeTilesNearUnits`, `FreeTilesOrAdjacentFreeTiles`, `GetDefaultUnitSelectionType`, `GetPersistentDataListAsEntities`, `Healable`, `Killer`, `KillingDamageProfile`, `Last`, `LimitUnitDuplications`, `MachinePrimaryAbilityType`, `MachineSecondaryAbilityType`, `MainTileFromBossPlatform`, `MainTileOfUnits`, `Nearest`, `NearestAttackableEnemies`, `NearestFreeTilesAmount`, `NextTileClockwise`, `NextTileInLine`, `NonSteppableUnits`, `None`, `NormalAttackDamageProfile`, `NormalMeleeAttackDamageProfile`, `OriginalOwner`, `PendingMovingTile`, `Player`, `PlayersByTeam`, `PreviousTile`, `RandomAdjacentFreeTile`, `SafestTiles`, `SortByMinDistance`, `SortByRow`, `SortTargetsByDamagePredictionSelector`, `SpawnPointTilesOfPlayer`, `SpawnTiles`, `TargetableUnits`, `TerritoryOwner`, `TerritoryTiles`, `TileBehindFilled`, `TileBehindTargetFromSourceDirection`, `TilesAtRow`, `TilesForUnitAtTile`, `TilesInConeShapeForBossWide`, `TilesInDiamondShape`, `TilesInLineFromUnit`, `TilesInPath`, `TilesUnitCanAttackFrom`, `TilesWithEnemies`, `TilesWithTriggeredAbility`, `TilesWithoutPowerUps`, `TurnStartTile`, `UnitNormalRepairType`, `UnitsAttackedThisTurn`, `UnitsDefeatedBy`, `UnitsFromPlayer`, `UnitsFromTeam`, `UnitsNotFromFaction`, `UnitsWhoCanAttack`, `UnitsWithAnyValidTarget`, `UnitsWithFlag`, `UnitsWithRangedAbilities`, `UnitsWithRangedWeapons`, `UnitsWithRangedWeaponsExcludingDamageProfile`, `UnitsWithRarity`, `UnitsWithSameVisualId`, `UnitsWithStatBiggerThan`, `UnitsWithTraits`, `UnitsWithTriggeredAbility`, `UnitsWithoutFlag`, `UnitsWithoutRangedWeapons`, `UnitsWithoutTraits`, `UnobscuredTiles`, `WalkableAndBrokenIce`

**DSLTriggers** (87) : `.ctor`, `ActorHasTriggeredAbility`, `All`, `AmountIsEven`, `Any`, `AreEquivalent`, `AttackUsedAttackDamage`, `CanBeDisplaced`, `CanMove`, `CanUseAbility`, `Contains`, `CurrentAttackDamageProfileIs`, `CurrentAttackDamageProfilesContain`, `CurrentAttackDamageProfilesContainOtherThan`, `DamageProfileHasTrait`, `DamageProfileIs`, `Direct`, `HasAdjacentEnemies`, `HasAdjacentFreeTiles`, `HasBeenDefeated`, `HasBlockedThisTurn`, `HasPersistentData`, `HasRarity`, `HasTakenDamageOfDamageProfileThisTurn`, `HasTile`, `HasTriggeredAbilityBeenTriggered`, `IsAIPlayer`, `IsAdjacentTiles`, `IsAtRange`, `IsAttackAbility`, `IsDamageEventOverkilledTarget`, `IsEffectCreatedThisTurn`, `IsEffectTarget`, `IsEmptyOrSteppable`, `IsEnemyTurn`, `IsEnhancementTarget`, `IsEntityWithIdTarget`, `IsFirstDamagingHitInSeries`, `IsFirstHitGroupInAttack`, `IsHero`, `IsHumanPlayer`, `IsInAttackOrAbilityRange`, `IsInPersistentDataList`, `IsInStraightLine`, `IsInTeam`, `IsInTeamSynapseRange`, `IsKilledThisTurn`, `IsMachine`, `IsMoving`, `IsNormalAttackOrHealOrRepair`, `IsNormalUnit`, `IsObscured`, `IsOverwatchAttack`, `IsOwnerOfEffect`, `IsOwnerTileReserved`, `IsPartialAttackAbility`, `IsPlayerDefeated`, `IsReplacedUnit`, `IsSameFaction`, `IsSpawnTile`, `IsSpawnedByRoomRevealUnit`, `IsSpecialActiveAbility`, `IsSteppableUnit`, `IsTargetable`, `IsTeamDefeated`, `IsTerritoryTile`, `IsTrenchTile`, `IsTriggeringAbilityNormalAttackOrHealOrRepair`, `IsUnitOnTileWithEffect`, `IsUnitWithId`, `IsUnitWithStatAmount`, `IsUnitWithVisualId`, `IsWalkable`, `OnAttackFromAbility`, `OnDeath`, `StatPercentageIsBelowOrEqual`, `TriggeringAbilityHasAttackType`, `TriggeringAbilityIsNone`, `TriggeringAbilityIsNormalAttack`, `WasBlock`, `WasCrit`, `get_CasterIsCasterTile`, `get_CasterIsTarget`, `get_OwnerIsCasterTile`, `get_OwnerIsTargetTile`, `get_OwnerOrOwnerTileIsTarget`, `get_OwnerTileIsTarget`

## 4. Ce qui n'est PAS mesurable, et pourquoi

* **Levier natif** : le nombre d'abilities qui APPELLENT une primitive vient des xrefs
  du binaire (phase 1 / #325). Ce document ne le re-derive pas.
* **Voies d'attribution non couvertes** (`trait`, `liveevent`, `summon`, `tile`, cf.
  `unit_map.VOIES_NON_COUVERTES`) : toute ability rendue `SANS_PORTEUR_MESURE` les porte
  en colonne. Ce zero ne prouve pas qu'elle est morte.
* **Abilities sans classe native reperee** (0) : le mapping ability <-> classe native lit
  `classes.tsv` (et non `methods.tsv`, ou une classe sans methode nommee manque -- ex.
  `AblativePlatingAbility`). Ce qui reste est un NON MESURE, pas une absence de code.

### L'axe UTILITY / gshared est MESURABLE sur ce checkout -- verifie, pas suppose

La consigne heritee dit que les corps pleinement partages ne sont plus nommes
(`4882 -> 0`, `docs/rl/case-259-couverture-gshared.md`). **Re-derive le 2026-07-31 sur les
tables VERSIONNEES, ce n'est pas l'etat courant** :

| table | `gqfc5mff6c` | `rnca9r7q6c` |
|---|---:|---:|
| `ghidra/functions.tsv`, marqueur `__Il2CppFullySharedGeneric` | 4882 | 4874 |
| `frida/methods.tsv`, meme marqueur | 0 | 0 |

**Un chiffre gshared sans son MOTIF n'est pas une mesure.** Les motifs sont EMBOITES,
donc deux lectures honnetes different d'un facteur 1,7 sans se contredire. Sur
`rnca9r7q6c`, colonne SYMBOLE de `ghidra/functions.tsv`, test sous-chaine :

| motif | ghidra | frida |
|---|---:|---:|
| `__Il2CppFullySharedGeneric` (prefixe -- celui de `probe_259`) | 4874 | 0 |
| `FullySharedGenericType` | 4011 | 0 |
| `FullySharedGenericStructType` | 912 | 0 |
| `u003C__Il2CppFullySharedGenericTypeu003E` (forme delimitee) | 2830 | 0 |

Le `2830` et le `4874` sont donc **la meme realite lue a deux granularites** : le second
est un prefixe qui englobe `StructType` et les formes non delimitees. Aucun motif ne
rend zero cote Ghidra. Re-deriver :
`python scripts/python/probe_326_dsl_primitive_inventory.py --compare gqfc5mff6c`.

Le `0` cote Frida est STRUCTUREL et vaut pour les deux builds (le `methodPointer` d'une
definition generique est un thunk, pas le corps) : le lire comme l'effondrement decrit
par #259 serait un faux. `probe_259_gshared_coverage.py` re-joue confirme -- famille
`GSHARED` 4882 -> 4874 (ratio 0.998), *familles en chute : 0*, et 100 % des methodes
frida retrouvent leur nom Ghidra sur le build courant (contre 91,1 % a la reference).
Mesurer soi-meme : `python scripts/python/probe_326_dsl_primitive_inventory.py
--compare gqfc5mff6c`.

## 5. Citations PERIMEES du port (symbole absent du build courant)

| primitive citee | citations | premier site |
|---|---:|---|
| `Difference` | 2 | `scripts/python/engine/entities/formulas.py:43` (Difference) |
| `Null` | 1 | `scripts/python/engine/entities/selectors/geometry.py:553` (Null) |

Ces noms ne sont plus dans les classes-factory du build : soit la primitive a
ete RETIREE du jeu, soit elle a ete RENOMMEE. Dans les deux cas la citation ne se
resout plus par grep, et le port qui s'en reclame n'est plus atteste.

## 6. L'axe symetrique : exports Python sans primitive native homonyme

Un nom Python sans primitive homonyme n'est pas fautif en soi : il peut porter la
CLASSE DE NOEUD (alias), un SLOT de la factory ou une piece d'infrastructure. Mais
c'est aussi la ou se logerait un nom INVENTE, alors on le compte.

**69 exports**, dont **57 citent un artefact natif** (alias) et **12 n'en citent aucun** :

| export | site | ce que la docstring en dit |
|---|---|---|
| `Caster` | `scripts/python/engine/entities/selectors/tiles.py:21` | L'unite CASTER (`caster@+0x168`, ref passee aux selecteurs). Accesseur unit-domain = |
| `CasterTile` | `scripts/python/engine/entities/selectors/accessors.py:19` | Tuile du caster (`UnitPosition.MainTile` du casterPosition passé par le generator) — pour une |
| `Emit` | `scripts/python/engine/entities/behaviours.py:152` | Feuille GENERIQUE emettant UNE Operation : patron des feuilles concretes (`SpawnUnit`, |
| `FixedTiles` | `scripts/python/engine/entities/selectors/accessors.py:32` | Sélecteur de tuile(s) LITTÉRAL(es) — PAS un noeud natif : VÉHICULE DE COLLAPSE (doctrine slice-18/19) |
| `OperationResult` | `scripts/python/engine/dsl/effects.py:24` | Retour de tout `*Behaviour.Execute` natif (8 slots ; byte@+0x20 = flag succes/COURT-CIRCUIT) ; |
| `Subject` | `scripts/python/engine/entities/selectors/accessors.py:75` | Élément COURANT lié par un `Filter` (mirror du sélecteur-sujet natif `ability+0x180` = |
| `Target` | `scripts/python/engine/entities/selectors/accessors.py:112` | Cible principale de l'ability (l'UNITÉ, pas sa tuile — cf. `TargetTile`). Mirror du contexte |
| `TargetTile` | `scripts/python/engine/entities/selectors/accessors.py:26` | Tuile de la cible principale (`MainTile` de la cible) — centre de `SurroundingUnits`. |
| `TileIntersect` | `scripts/python/engine/entities/selectors/tiles.py:196` | Intersection de deux ensembles de TUILES (ids) — `op_BitwiseAnd` du domaine tile |
| `UnitSet` | `scripts/python/engine/entities/selectors/units.py:164` | Feuille = un ensemble d'unités explicite (ex. `{mainTarget}` pour la soustraction AoE). |
| `first_triggered_ability_of` | `scripts/python/engine/runner/abilities/behaviours/grants.py:119` | `Enumerable.First(caster.GetComponent<TriggeredAbilityComponent>().<coll @+0x18>)` -- la |
| `resolve_unit` | `scripts/python/engine/dsl/base.py:64` | Evalue un noeud (souvent `Subject()`/`Target()`) en UN dict d'unite : dict direct, ou 1er dict d'une |

Re-derive le 2026-07-31 : **aucun de ces 12 n'est un nom invente** -- ce sont
des slots de la factory (`Caster`, `CasterTile`, `Subject`, `Target`, `TargetTile`,
cf. `IdunBattleLogic.Entities.DSLFactory$$InitializeShared`), des OPERATEURS
(`And`/`TileIntersect` = `TargetsSelector.op_BitwiseAnd`), de l'infrastructure de
port (`Emit`, `OperationResult`, `resolve_unit`) ou des vehicules de collapse
declares comme tels (`FixedTiles`, `UnitSet`). Le compte, lui, doit rester
surveille : c'est ce chiffre qui reagirait a une invention.
