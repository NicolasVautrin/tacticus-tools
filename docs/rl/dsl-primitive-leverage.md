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


Build mesure : `rnca9r7q6c`. Table phase 1 (#325) : **ABSENTE -- la colonne de levier vaut `NON_MESURABLE_P1`**.

## 1. Couverture du port, par famille de primitive

| famille | PORTE | PORTE_ALIAS_FACADE | PORTE_HORS_FACADE | PORTE_ARTEFACT_AUTRE | PORTE_SANS_CITATION | CITE_A_QUALIFIER | NON_PORTE | total |
|---|---|---|---|---|---|---|---|---|
| DSLBehaviors | 46 | 5 | 3 | 0 | 0 | 16 | 57 | 127 |
| DSLFactory | 0 | 0 | 0 | 0 | 0 | 2 | 3 | 5 |
| DSLFormulas | 30 | 1 | 1 | 0 | 3 | 18 | 60 | 113 |
| DSLSelectors | 64 | 3 | 2 | 0 | 0 | 20 | 106 | 195 |
| DSLTriggers | 32 | 1 | 1 | 1 | 0 | 46 | 84 | 165 |
| **TOTAL** | **172** | **10** | **7** | **1** | **3** | **102** | **310** | **605** |

**Porte atteste** (`PORTE` + `PORTE_ALIAS_FACADE` + `PORTE_HORS_FACADE`) = **189 / 605**.
`CITE_A_QUALIFIER` (102) n'est NI porte NI absent : l'artefact apparait dans `engine/**` sans porteur Python identifiable. C'est un etat A TRANCHER, pas un zero.

## 2. Joignabilite des abilities (etage B)

| verdict | abilities |
|---|---:|
| CONFRONTABLE_POOL | 221 |
| SANS_PORTEUR_MESURE | 82 |
| HORS_KIT_UNITE | 82 |
| CONFRONTABLE_INJECTION | 52 |
| NON_PERTINENT_NPC | 50 |
| SUMMON_SANS_SUMMONER_MESURE | 32 |
| CONFRONTABLE_SUMMON | 25 |
| CONFRONTABLE_RELIQUE_A_EQUIPER | 24 |
| CONFRONTABLE_SUMMON_INJECTION | 4 |

La voie RELIQUE a **trois** etats et non deux (`RELIQUE_EQUIPEE_SEED` / `RELIQUE_POOL_A_EQUIPER` / `RELIQUE_HORS_POOL`) : « porteur dans le pool » ne dit pas « arrive en bataille AVEC sa relique ».

## 3. Classement des primitives NON PORTEES par levier

**NON MESURABLE** -- la table `primitive <-> abilities` de la phase 1 (#325) n'a pas
atterri. Le classement n'est PAS estime : un ordre invente sur des xrefs devinees
vaudrait moins que son absence. Relancer avec `--p1 <table>` le produit sans autre
changement (le lecteur accepte TSV/JSON et trois formes de nom de chaque cote ;
cf. `scripts/python/tests/test_326_dsl_join_offline.py`).

### Inventaire brut des primitives NON PORTEES (matiere de la jointure)

Sans la table phase 1 on ne peut pas les ORDONNER, mais on peut les NOMMER -- et c'est
deja ce qui manquait. Table complete (avec les `CITE_A_QUALIFIER`, non listees ici) :
`logs/326_dsl_primitive_coverage.tsv`.

**DSLBehaviors** (57) : `AddActiveAbility`, `AddBlockEnteringUnitsEffect`, `AddFlag`, `AddPersistentData`, `AddReinforcementPoint`, `AddResurrectDraftPoint`, `AddStatOverrideEffectToOwner`, `AddStaticStatModifierEffectToOwner`, `AddTemporaryAttackOverrideEffect`, `AddToPersistentDataList`, `AssignAbilityVariationToEffect`, `AttackMachine`, `AttackTiles`, `ChainAbilityDamage`, `ChainAttackDamage`, `ChainSpawnBehaviour`, `ChangeCooldown`, `ClearAllPersistentData`, `Clone`, `CloneMachine`, `DecreaseEffectLevel`, `DirectDamage`, `DisplaceUnitInAdjacentDirection`, `Do`, `ExecuteAdditionalHitsWithDamageProfileType`, `FinishAttack`, `Flee`, `FlyUnit`, `InformList`, `InvalidateCaches`, `OverrideUnitMovementTarget`, `PerformAIMovement`, `PullUnitOneTile`, `PushAwayFromBlacklistTiles`, `PushToPrioritizedTiles`, `ReAddMachine`, `RefreshEffects`, `RemoveActiveAbility`, `RemoveAllForcedAttackTargets`, `RemoveFlag`, `RemoveReservation`, `RemoveUnitFromItsTiles`, `Repeat`, `Reserve`, `ResetMovement`, `ResetPreviousPosition`, `ResetTemporaryAttackOverrideEffect`, `RotateUnit`, `SetActiveAbilityUsed`, `SetEffectLevel`, `SpawnRandom`, `StartAttack`, `Teleport`, `TransferDamage`, `TransferHit`, `Transform`, `UseNormalAttack`

**DSLFactory** (3) : `.ctor`, `Init`, `Triggered`

**DSLFormulas** (60) : `.ctor`, `AbilityLevelFromPlayerCurrentRarity`, `AttackPiercingRatio`, `AttackWeaponRange`, `AverageDistance`, `BlockedHits`, `CasterEffectPierceAddition`, `ConfigConstString`, `CriticalHitsThisTurn`, `CurrentDamage`, `CurrentPlayerTurnsStarted`, `CurrentShieldAmount`, `DamagePredictionFormula`, `DirectionTo`, `EffectRemainingTurns`, `EnhancementStack`, `EnhancementStackForTarget`, `GetAllPersistentDataCombined`, `HealthDamageFromEvent`, `IncreasedAmount`, `LastAttackDamageMade`, `MeleeAttackHits`, `MeleeWeaponHits`, `MinPathLength`, `MovementSteps`, `MultiStatValueFromEffect`, `MultiplyPercentageRecursively`, `NonLethalDamage`, `NormalAttackRange`, `NumControlledTerritory`, `Percent`, `PercentageOfStatCappedAtMax`, `PlayerAverageUnitLevel`, `PlayerTurnOrder`, `PlayerTurnsStarted`, `ReducedAmount`, `RotateVector`, `RowWithMostUnits`, `StatNegativeModification`, `Subtract`, `TilesMovedLastTurn`, `TilesMovedThisTurn`, `TimesAttackMadeThisTurn`, `TimesBlockedThisTurn`, `TimesHealedThisTurn`, `TimesReceivedAttackedThisTurn`, `TotalDamageDealt`, `TotalTurnsFinished`, `TotalTurnsWithAttacksMade`, `TriggerBoolNumber`, `TurnDefeated`, `UnitCurrentDirection`, `UnitIdFromUnit`, `UnitLevel`, `UnitRow`, `UnitsDefeatedAmount`, `UnitsTeamId`, `VectorFromAdjacentTo`, `VisualUnitIdFromUnit`, `WeaponHighestHits`

**DSLSelectors** (106) : `.ctor`, `AbilityState`, `AbilityStateFromEffect`, `AbilityStateFromLevel`, `AdjacentTilesIntersection`, `AtIndex`, `Attackable`, `AttackableEnemies`, `AttackableFriends`, `Attacker`, `BloodRunsAngerRisesWarCallsSelector`, `BondEffects`, `CanAddMultiTileUnit`, `CenterTiles`, `ClosestPositionToTarget`, `ConditionalSelector`, `CornerTiles`, `CreateSnapshot`, `CurrentAttackDamageProfile`, `CurrentPlayer`, `DeadUnits`, `Duplicate`, `EdgeTiles`, `EdgeTilesByDirection`, `EffectTarget`, `EmptyOrHasSteppableUnit`, `EmptyTiles`, `EnemyMachine`, `EnhancementTarget`, `Entities`, `EntitiesIsNotTargetOfEffect`, `EntitiesWithBondEffect`, `FilterTilesIfCanAttackTargetTileFrom`, `ForcedAttackTargets`, `FreeTilesNearUnits`, `FreeTilesOrAdjacentFreeTiles`, `GetDefaultUnitSelectionType`, `GetPersistentDataListAsEntities`, `Healable`, `Killer`, `KillingDamageProfile`, `Last`, `LimitUnitDuplications`, `MachinePrimaryAbilityType`, `MachineSecondaryAbilityType`, `MainTileFromBossPlatform`, `MainTileOfUnits`, `Nearest`, `NearestAttackableEnemies`, `NearestFreeTilesAmount`, `NextTileClockwise`, `NextTileInLine`, `NonSteppableUnits`, `None`, `NormalAttackDamageProfile`, `NormalMeleeAttackDamageProfile`, `OriginalOwner`, `PendingMovingTile`, `Player`, `PlayersByTeam`, `PreviousTile`, `RandomAdjacentFreeTile`, `SafestTiles`, `SortByMinDistance`, `SortByRow`, `SortTargetsByDamagePredictionSelector`, `SpawnPointTilesOfPlayer`, `SpawnTiles`, `TargetableUnits`, `TerritoryOwner`, `TerritoryTiles`, `TileBehindFilled`, `TileBehindTargetFromSourceDirection`, `TilesAtRow`, `TilesForUnitAtTile`, `TilesInConeShapeForBossWide`, `TilesInDiamondShape`, `TilesInLineFromUnit`, `TilesInPath`, `TilesUnitCanAttackFrom`, `TilesWithEnemies`, `TilesWithTriggeredAbility`, `TilesWithoutPowerUps`, `TurnStartTile`, `UnitNormalRepairType`, `UnitsAttackedThisTurn`, `UnitsDefeatedBy`, `UnitsFromPlayer`, `UnitsFromTeam`, `UnitsNotFromFaction`, `UnitsWhoCanAttack`, `UnitsWithAnyValidTarget`, `UnitsWithFlag`, `UnitsWithRangedAbilities`, `UnitsWithRangedWeapons`, `UnitsWithRangedWeaponsExcludingDamageProfile`, `UnitsWithRarity`, `UnitsWithSameVisualId`, `UnitsWithStatBiggerThan`, `UnitsWithTraits`, `UnitsWithTriggeredAbility`, `UnitsWithoutFlag`, `UnitsWithoutRangedWeapons`, `UnitsWithoutTraits`, `UnobscuredTiles`, `WalkableAndBrokenIce`

**DSLTriggers** (84) : `.ctor`, `ActorHasTriggeredAbility`, `All`, `AmountIsEven`, `Any`, `AreEquivalent`, `AttackUsedAttackDamage`, `CanBeDisplaced`, `CanMove`, `CanUseAbility`, `Contains`, `CurrentAttackDamageProfileIs`, `CurrentAttackDamageProfilesContain`, `CurrentAttackDamageProfilesContainOtherThan`, `DamageProfileHasTrait`, `DamageProfileIs`, `HasAdjacentEnemies`, `HasAdjacentFreeTiles`, `HasBeenDefeated`, `HasBlockedThisTurn`, `HasPersistentData`, `HasRarity`, `HasTakenDamageOfDamageProfileThisTurn`, `HasTile`, `HasTriggeredAbilityBeenTriggered`, `IsAIPlayer`, `IsAdjacentTiles`, `IsAtRange`, `IsAttackAbility`, `IsDamageEventOverkilledTarget`, `IsEffectCreatedThisTurn`, `IsEffectTarget`, `IsEmptyOrSteppable`, `IsEnemyTurn`, `IsEnhancementTarget`, `IsEntityWithIdTarget`, `IsFirstDamagingHitInSeries`, `IsHero`, `IsHumanPlayer`, `IsInAttackOrAbilityRange`, `IsInPersistentDataList`, `IsInStraightLine`, `IsInTeam`, `IsKilledThisTurn`, `IsMachine`, `IsMoving`, `IsNormalAttackOrHealOrRepair`, `IsNormalUnit`, `IsObscured`, `IsOverwatchAttack`, `IsOwnerOfEffect`, `IsOwnerTileReserved`, `IsPartialAttackAbility`, `IsPlayerDefeated`, `IsReplacedUnit`, `IsSameFaction`, `IsSpawnTile`, `IsSpawnedByRoomRevealUnit`, `IsSpecialActiveAbility`, `IsSteppableUnit`, `IsTargetable`, `IsTeamDefeated`, `IsTerritoryTile`, `IsTrenchTile`, `IsTriggeringAbilityNormalAttackOrHealOrRepair`, `IsUnitOnTileWithEffect`, `IsUnitWithId`, `IsUnitWithStatAmount`, `IsUnitWithVisualId`, `IsWalkable`, `OnAttackFromAbility`, `OnDeath`, `StatPercentageIsBelowOrEqual`, `TriggeringAbilityHasAttackType`, `TriggeringAbilityIsNone`, `TriggeringAbilityIsNormalAttack`, `WasBlock`, `WasCrit`, `get_CasterIsCasterTile`, `get_CasterIsTarget`, `get_OwnerIsCasterTile`, `get_OwnerIsTargetTile`, `get_OwnerOrOwnerTileIsTarget`, `get_OwnerTileIsTarget`

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

**69 exports**, dont **56 citent un artefact natif** (alias) et **13 n'en citent aucun** :

| export | site | ce que la docstring en dit |
|---|---|---|
| `And` | `scripts/python/engine/entities/selectors/units.py:98` | `TargetsSelector.op_BitwiseAnd` : intersection par id. |
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

Re-derive le 2026-07-31 : **aucun de ces 13 n'est un nom invente** -- ce sont
des slots de la factory (`Caster`, `CasterTile`, `Subject`, `Target`, `TargetTile`,
cf. `IdunBattleLogic.Entities.DSLFactory$$InitializeShared`), des OPERATEURS
(`And`/`TileIntersect` = `TargetsSelector.op_BitwiseAnd`), de l'infrastructure de
port (`Emit`, `OperationResult`, `resolve_unit`) ou des vehicules de collapse
declares comme tels (`FixedTiles`, `UnitSet`). Le compte, lui, doit rester
surveille : c'est ce chiffre qui reagirait a une invention.
