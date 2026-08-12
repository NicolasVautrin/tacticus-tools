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
| DSLBehaviors | 62 | 7 | 14 | 0 | 0 | 18 | 26 | 127 |
| DSLFactory | 0 | 0 | 0 | 0 | 0 | 3 | 2 | 5 |
| DSLFormulas | 37 | 1 | 14 | 0 | 2 | 16 | 43 | 113 |
| DSLSelectors | 87 | 7 | 14 | 0 | 0 | 25 | 62 | 195 |
| DSLTriggers | 48 | 6 | 51 | 1 | 0 | 0 | 59 | 165 |
| TargetsSelector | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 3 |
| **TOTAL** | **234** | **29** | **93** | **1** | **2** | **62** | **192** | **613** |

**Porte atteste** (`PORTE` + `PORTE_ALIAS_FACADE` + `PORTE_HORS_FACADE`) = **356 / 613**.
`CITE_A_QUALIFIER` (62) n'est NI porte NI absent : l'artefact apparait dans `engine/**` sans porteur Python identifiable. C'est un etat A TRANCHER, pas un zero.

**43 verdicts viennent de `docs/rl/dsl-port-attestations.tsv`** -- le canal ou un HUMAIN tranche ce qu'aucune heuristique de nom ne peut apparier (un PREDICAT collapse dans un `matches()`). Chaque ligne est re-verifiee a chaque run (symbole present dans le build, ancre resolue, primitive citee) ; detail : `docs/rl/case-337-dsl-triggers-attestation.md`.

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
| 3 | DSLSelectors | `Direct` | CITE_A_QUALIFIER | 42 | 33 | 28 |
| 4 | DSLFormulas | `Min` | PORTE_SANS_CITATION | 18 | 17 | 13 |
| 5 | DSLBehaviors | `IfAlive` | CITE_A_QUALIFIER | 20 | 14 | 11 |
| 6 | DSLFormulas | `Subtract` | CITE_A_QUALIFIER | 14 | 13 | 6 |
| 7 | DSLFactory | `Triggered` | CITE_A_QUALIFIER | 19 | 12 | 8 |
| 8 | DSLBehaviors | `AddDynamicStatModifierEffectToOwner` | CITE_A_QUALIFIER | 12 | 9 | 6 |
| 9 | DSLSelectors | `DamageProfileFromConfig` | CITE_A_QUALIFIER | 16 | 9 | 6 |
| 10 | DSLBehaviors | `AddFlag` | CITE_A_QUALIFIER | 9 | 8 | 4 |
| 11 | DSLBehaviors | `AddStaticStatModifierEffectToOwner` | CITE_A_QUALIFIER | 10 | 7 | 3 |
| 12 | DSLSelectors | `None` | CITE_A_QUALIFIER | 8 | 7 | 6 |
| 13 | DSLSelectors | `UnitsWithRarity` | NON_PORTE | 7 | 7 | 5 |
| 14 | DSLSelectors | `CreateSnapshot` | CITE_A_QUALIFIER | 6 | 6 | 4 |
| 15 | DSLSelectors | `FreeTilesOrAdjacentFreeTiles` | NON_PORTE | 6 | 6 | 3 |
| 16 | DSLSelectors | `SortTargetsByDamagePredictionSelector` | CITE_A_QUALIFIER | 6 | 6 | 5 |
| 17 | DSLTriggers | `HasRarity` | NON_PORTE | 6 | 6 | 5 |
| 18 | DSLTriggers | `get_OwnerOrOwnerTileIsTarget` | NON_PORTE | 6 | 6 | 6 |
| 19 | DSLBehaviors | `AddTemporaryAttackOverrideEffect` | CITE_A_QUALIFIER | 5 | 5 | 3 |
| 20 | DSLBehaviors | `ResetTemporaryAttackOverrideEffect` | CITE_A_QUALIFIER | 5 | 5 | 3 |
| 21 | DSLBehaviors | `AddExtraBlockEffectToOwner` | CITE_A_QUALIFIER | 5 | 4 | 3 |
| 22 | DSLSelectors | `Attackable` | CITE_A_QUALIFIER | 4 | 4 | 4 |
| 23 | DSLSelectors | `BondedEntityFromEffect` | CITE_A_QUALIFIER | 5 | 4 | 4 |
| 24 | DSLBehaviors | `AddActiveAbility` | CITE_A_QUALIFIER | 3 | 3 | 2 |
| 25 | DSLBehaviors | `DeactivateEffect` | CITE_A_QUALIFIER | 3 | 3 | 2 |
| 26 | DSLBehaviors | `RefreshEffects` | NON_PORTE | 3 | 3 | 3 |
| 27 | DSLBehaviors | `RemoveActiveAbility` | CITE_A_QUALIFIER | 3 | 3 | 2 |
| 28 | DSLBehaviors | `RemoveFlag` | NON_PORTE | 3 | 3 | 2 |
| 29 | DSLFormulas | `ConfigConstString` | NON_PORTE | 3 | 3 | 1 |
| 30 | DSLFormulas | `FirstHitInCurrentAttackDamageRange` | CITE_A_QUALIFIER | 3 | 3 | 3 |
| 31 | DSLFormulas | `TimesAttackMadeThisTurn` | CITE_A_QUALIFIER | 3 | 3 | 2 |
| 32 | DSLFormulas | `UnitMovementRangeWithBonus` | CITE_A_QUALIFIER | 3 | 3 | 2 |
| 33 | DSLSelectors | `Killer` | NON_PORTE | 4 | 3 | 2 |
| 34 | DSLTriggers | `CanUseAbility` | NON_PORTE | 3 | 3 | 1 |
| 35 | DSLTriggers | `IsInTeamSynapseRange` | NON_PORTE | 4 | 3 | 1 |
| 36 | DSLTriggers | `IsMachine` | NON_PORTE | 3 | 3 | 2 |
| 37 | DSLTriggers | `IsUnitOnTileWithEffect` | NON_PORTE | 6 | 3 | 3 |
| 38 | DSLBehaviors | `ChangeCooldown` | NON_PORTE | 3 | 2 | 1 |
| 39 | DSLBehaviors | `InvalidateCaches` | NON_PORTE | 3 | 2 | 2 |
| 40 | DSLBehaviors | `TransferDamage` | NON_PORTE | 2 | 2 | 0 |

Lire la colonne **verdict port** : ce tableau melange volontairement les trois
etats non attestes. `PORTE_SANS_CITATION` (`Sum`, `Min`, `Multiply`) est du code qui
EXISTE mais ne cite aucun artefact -- l'action y est d'ATTESTER, pas de porter.
`CITE_A_QUALIFIER` demande une relecture. Seul `NON_PORTE` est du portage sec :

### 3bis. Le backlog SEC : primitives `NON_PORTE` avec un levier mesure

**77 primitives** `NON_PORTE` debloquent au moins une ability confrontable (sur 192 `NON_PORTE` au total -- les autres ont un levier mesure a zero, ce qui est une mesure, pas une ignorance).

| # | famille | primitive | symbole | abilities | dont confrontables | dont pool |
|---:|---|---|---|---:|---:|---:|
| 1 | DSLSelectors | `UnitsWithRarity` | `IdunBattleLogic.Entities.DSLSelectors$$UnitsWithRarity` | 7 | 7 | 5 |
| 2 | DSLSelectors | `FreeTilesOrAdjacentFreeTiles` | `IdunBattleLogic.Entities.DSLSelectors$$FreeTilesOrAdjacentFreeTiles` | 6 | 6 | 3 |
| 3 | DSLTriggers | `HasRarity` | `IdunBattleLogic.Entities.DSLTriggers$$HasRarity` | 6 | 6 | 5 |
| 4 | DSLTriggers | `get_OwnerOrOwnerTileIsTarget` | `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerOrOwnerTileIsTarget` | 6 | 6 | 6 |
| 5 | DSLBehaviors | `RefreshEffects` | `IdunBattleLogic.Entities.DSLBehaviors$$RefreshEffects` | 3 | 3 | 3 |
| 6 | DSLBehaviors | `RemoveFlag` | `IdunBattleLogic.Entities.DSLBehaviors$$RemoveFlag` | 3 | 3 | 2 |
| 7 | DSLFormulas | `ConfigConstString` | `IdunBattleLogic.Entities.DSLFormulas$$ConfigConstString` | 3 | 3 | 1 |
| 8 | DSLSelectors | `Killer` | `IdunBattleLogic.Entities.DSLSelectors$$Killer` | 4 | 3 | 2 |
| 9 | DSLTriggers | `CanUseAbility` | `IdunBattleLogic.Entities.DSLTriggers$$CanUseAbility` | 3 | 3 | 1 |
| 10 | DSLTriggers | `IsInTeamSynapseRange` | `IdunBattleLogic.Entities.DSLTriggers$$IsInTeamSynapseRange` | 4 | 3 | 1 |
| 11 | DSLTriggers | `IsMachine` | `IdunBattleLogic.Entities.DSLTriggers$$IsMachine` | 3 | 3 | 2 |
| 12 | DSLTriggers | `IsUnitOnTileWithEffect` | `IdunBattleLogic.Entities.DSLTriggers$$IsUnitOnTileWithEffect` | 6 | 3 | 3 |
| 13 | DSLBehaviors | `ChangeCooldown` | `IdunBattleLogic.Entities.DSLBehaviors$$ChangeCooldown` | 3 | 2 | 1 |
| 14 | DSLBehaviors | `InvalidateCaches` | `IdunBattleLogic.Entities.DSLBehaviors$$InvalidateCaches` | 3 | 2 | 2 |
| 15 | DSLBehaviors | `TransferDamage` | `IdunBattleLogic.Entities.DSLBehaviors$$TransferDamage` | 2 | 2 | 0 |
| 16 | DSLFormulas | `MultiStatValueFromEffect` | `IdunBattleLogic.Entities.DSLFormulas$$MultiStatValueFromEffect` | 2 | 2 | 2 |
| 17 | DSLSelectors | `UnitsWithSameVisualId` | `IdunBattleLogic.Entities.DSLSelectors$$UnitsWithSameVisualId` | 3 | 2 | 0 |
| 18 | DSLTriggers | `Any` | `IdunBattleLogic.Entities.DSLTriggers$$Any` | 4 | 2 | 0 |
| 19 | DSLTriggers | `CurrentAttackDamageProfileIs` | `IdunBattleLogic.Entities.DSLTriggers$$CurrentAttackDamageProfileIs` | 2 | 2 | 0 |
| 20 | DSLTriggers | `IsSpecialActiveAbility` | `IdunBattleLogic.Entities.DSLTriggers$$IsSpecialActiveAbility` | 2 | 2 | 0 |
| 21 | DSLTriggers | `IsSteppableUnit` | `IdunBattleLogic.Entities.DSLTriggers$$IsSteppableUnit` | 2 | 2 | 0 |
| 22 | DSLTriggers | `IsTargetable` | `IdunBattleLogic.Entities.DSLTriggers$$IsTargetable` | 2 | 2 | 2 |
| 23 | DSLTriggers | `IsUnitWithStatAmount` | `IdunBattleLogic.Entities.DSLTriggers$$IsUnitWithStatAmount` | 2 | 2 | 1 |
| 24 | DSLTriggers | `WasCrit` | `IdunBattleLogic.Entities.DSLTriggers$$WasCrit` | 2 | 2 | 1 |
| 25 | DSLBehaviors | `AddStatOverrideEffectToOwner` | `IdunBattleLogic.Entities.DSLBehaviors$$AddStatOverrideEffectToOwner` | 1 | 1 | 0 |
| 26 | DSLBehaviors | `InformList` | `IdunBattleLogic.Entities.DSLBehaviors$$InformList` | 1 | 1 | 0 |
| 27 | DSLBehaviors | `ReAddMachine` | `IdunBattleLogic.Entities.DSLBehaviors$$ReAddMachine` | 1 | 1 | 0 |
| 28 | DSLBehaviors | `SetEffectLevel` | `IdunBattleLogic.Entities.DSLBehaviors$$SetEffectLevel` | 2 | 1 | 0 |
| 29 | DSLFormulas | `AverageDistance` | `IdunBattleLogic.Entities.DSLFormulas$$AverageDistance` | 3 | 1 | 1 |
| 30 | DSLFormulas | `CriticalHitsThisTurn` | `IdunBattleLogic.Entities.DSLFormulas$$CriticalHitsThisTurn` | 1 | 1 | 1 |

### Inventaire brut des primitives NON PORTEES (matiere de la jointure)

Sans la table phase 1 on ne peut pas les ORDONNER, mais on peut les NOMMER -- et c'est
deja ce qui manquait. Table complete (avec les `CITE_A_QUALIFIER`, non listees ici) :
`logs/326_dsl_primitive_coverage.tsv`.

**DSLBehaviors** (26) : `AddBlockEnteringUnitsEffect`, `AddReinforcementPoint`, `AddResurrectDraftPoint`, `AddStatOverrideEffectToOwner`, `AssignAbilityVariationToEffect`, `AttackMachine`, `AttackTiles`, `ChainSpawnBehaviour`, `ChangeCooldown`, `Clone`, `CloneMachine`, `DecreaseEffectLevel`, `Do`, `FinishAttack`, `InformList`, `InvalidateCaches`, `PushAwayFromBlacklistTiles`, `ReAddMachine`, `RefreshEffects`, `RemoveFlag`, `RotateUnit`, `SetActiveAbilityUsed`, `SetEffectLevel`, `SpawnRandom`, `TransferDamage`, `TransferHit`

**DSLFactory** (2) : `.ctor`, `Init`

**DSLFormulas** (43) : `.ctor`, `AbilityLevelFromPlayerCurrentRarity`, `AverageDistance`, `BlockedHits`, `CasterEffectPierceAddition`, `ConfigConstString`, `CriticalHitsThisTurn`, `CurrentPlayerTurnsStarted`, `CurrentShieldAmount`, `DirectionTo`, `EnhancementStack`, `EnhancementStackForTarget`, `IncreasedAmount`, `LastAttackDamageMade`, `MeleeAttackHits`, `MeleeWeaponHits`, `MinPathLength`, `MultiStatValueFromEffect`, `MultiplyPercentageRecursively`, `NonLethalDamage`, `NormalAttackRange`, `NumControlledTerritory`, `Percent`, `PercentageOfStatCappedAtMax`, `PlayerAverageUnitLevel`, `PlayerTurnOrder`, `ReducedAmount`, `RotateVector`, `RowWithMostUnits`, `StatNegativeModification`, `TimesHealedThisTurn`, `TimesReceivedAttackedThisTurn`, `TotalDamageDealt`, `TotalTurnsFinished`, `TriggerBoolNumber`, `UnitCurrentDirection`, `UnitIdFromUnit`, `UnitLevel`, `UnitRow`, `UnitsDefeatedAmount`, `UnitsTeamId`, `VisualUnitIdFromUnit`, `WeaponHighestHits`

**DSLSelectors** (62) : `.ctor`, `AbilityStateFromLevel`, `AdjacentTilesIntersection`, `AttackableFriends`, `BloodRunsAngerRisesWarCallsSelector`, `BondEffects`, `CanAddMultiTileUnit`, `CenterTiles`, `CornerTiles`, `CurrentAttackDamageProfile`, `Duplicate`, `EdgeTiles`, `EdgeTilesByDirection`, `EmptyTiles`, `EnemyMachine`, `EnhancementTarget`, `EntitiesIsNotTargetOfEffect`, `EntitiesWithBondEffect`, `ForcedAttackTargets`, `FreeTilesNearUnits`, `FreeTilesOrAdjacentFreeTiles`, `Killer`, `KillingDamageProfile`, `LimitUnitDuplications`, `MachinePrimaryAbilityType`, `MachineSecondaryAbilityType`, `MainTileFromBossPlatform`, `NearestAttackableEnemies`, `NearestFreeTilesAmount`, `NextTileClockwise`, `NextTileInLine`, `NormalAttackDamageProfile`, `NormalMeleeAttackDamageProfile`, `OriginalOwner`, `SafestTiles`, `SortByMinDistance`, `SpawnPointTilesOfPlayer`, `SpawnTiles`, `TargetableUnits`, `TerritoryOwner`, `TerritoryTiles`, `TileBehindFilled`, `TilesAtRow`, `TilesForUnitAtTile`, `TilesInConeShapeForBossWide`, `TilesInDiamondShape`, `TilesInLineFromUnit`, `TilesInPath`, `TilesWithEnemies`, `TilesWithTriggeredAbility`, `TilesWithoutPowerUps`, `TurnStartTile`, `UnitsFromPlayer`, `UnitsFromTeam`, `UnitsNotFromFaction`, `UnitsWhoCanAttack`, `UnitsWithRangedAbilities`, `UnitsWithRangedWeaponsExcludingDamageProfile`, `UnitsWithRarity`, `UnitsWithSameVisualId`, `UnitsWithoutFlag`, `WalkableAndBrokenIce`

**DSLTriggers** (59) : `.ctor`, `All`, `AmountIsEven`, `Any`, `AreEquivalent`, `CanUseAbility`, `CurrentAttackDamageProfileIs`, `CurrentAttackDamageProfilesContainOtherThan`, `Direct`, `HasAdjacentFreeTiles`, `HasPersistentData`, `HasRarity`, `HasTriggeredAbilityBeenTriggered`, `HasUsedActiveAbilityThisTurn`, `IsAIPlayer`, `IsAttackAbility`, `IsDamageEventOverkilledTarget`, `IsEffectCreatedThisTurn`, `IsEmptyOrSteppable`, `IsEnemyTurn`, `IsEnhancementTarget`, `IsEntityWithIdTarget`, `IsHumanPlayer`, `IsInAttackOrAbilityRange`, `IsInStraightLine`, `IsInTeam`, `IsInTeamSynapseRange`, `IsMachine`, `IsMoving`, `IsNormalAttackOrHealOrRepair`, `IsOwnerOfEffect`, `IsOwnerTileReserved`, `IsPartialAttackAbility`, `IsPlayerDefeated`, `IsReplacedUnit`, `IsSameFaction`, `IsSpawnTile`, `IsSpawnedByRoomRevealUnit`, `IsSpecialActiveAbility`, `IsSteppableUnit`, `IsTargetable`, `IsTeamDefeated`, `IsTerritoryTile`, `IsTriggeringAbilityNormalAttackOrHealOrRepair`, `IsUnitOnTileWithEffect`, `IsUnitWithId`, `IsUnitWithStatAmount`, `IsWalkable`, `OnAttackFromAbility`, `StatPercentageIsBelowOrEqual`, `TriggeringAbilityHasAttackType`, `TriggeringAbilityIsNormalAttack`, `WasCrit`, `get_CasterIsCasterTile`, `get_CasterIsTarget`, `get_OwnerIsCasterTile`, `get_OwnerIsTargetTile`, `get_OwnerOrOwnerTileIsTarget`, `get_OwnerTileIsTarget`

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
| `Difference` | 2 | `scripts/python/engine/entities/formulas.py:67` (Difference) |
| `Null` | 1 | `scripts/python/engine/entities/selectors/geometry.py:806` (Null) |

Ces noms ne sont plus dans les classes-factory du build : soit la primitive a
ete RETIREE du jeu, soit elle a ete RENOMMEE. Dans les deux cas la citation ne se
resout plus par grep, et le port qui s'en reclame n'est plus atteste.

## 6. L'axe symetrique : exports Python sans primitive native homonyme

Un nom Python sans primitive homonyme n'est pas fautif en soi : il peut porter la
CLASSE DE NOEUD (alias), un SLOT de la factory ou une piece d'infrastructure. Mais
c'est aussi la ou se logerait un nom INVENTE, alors on le compte.

**99 exports**, dont **82 citent un artefact natif** (alias) et **17 n'en citent aucun** :

| export | site | ce que la docstring en dit |
|---|---|---|
| `ActiveAbilityType` | `scripts/python/engine/entities/active_ability_type.py:23` | Mirror 1:1 de `IdunBattle.Entities.Enum.ActiveAbilityType` (260 membres). Valeur == id natif. |
| `Caster` | `scripts/python/engine/entities/selectors/tiles.py:30` | L'unite CASTER (`caster@+0x168`, ref passee aux selecteurs). Accesseur unit-domain = |
| `EffectTargetType` | `scripts/python/engine/entities/effect_target_type.py:29` | `IdunBattle.Entities.Enum.EffectTargetType` -- VERBATIM du build (3 valeurs). |
| `Emit` | `scripts/python/engine/entities/behaviours.py:193` | Feuille GENERIQUE emettant UNE Operation : patron des feuilles concretes (`SpawnUnit`, |
| `FixedTiles` | `scripts/python/engine/entities/selectors/accessors.py:111` | Sélecteur de tuile(s) LITTÉRAL(es) — PAS un noeud natif : VÉHICULE DE COLLAPSE (doctrine slice-18/19) |
| `OperationResult` | `scripts/python/engine/dsl/effects.py:25` | Retour de tout `*Behaviour.Execute` natif (8 slots ; byte@+0x20 = flag succes/COURT-CIRCUIT) ; |
| `Subject` | `scripts/python/engine/entities/selectors/accessors.py:178` | Élément COURANT lié par un `Filter` (mirror du sélecteur-sujet natif `ability+0x180` = |
| `Target` | `scripts/python/engine/entities/selectors/accessors.py:215` | Cible principale de l'ability (l'UNITÉ, pas sa tuile — cf. `TargetTile`). Mirror du contexte |
| `TileIntersect` | `scripts/python/engine/entities/selectors/tiles.py:572` | Intersection de deux ensembles de TUILES (ids) — `op_BitwiseAnd` du domaine tile |
| `UnitSelectionType` | `scripts/python/engine/entities/unit_selection_type.py:35` | `IdunBattle.Entities.Enum.UnitSelectionType` -- VERBATIM du build (4 valeurs). |
| `UnitSet` | `scripts/python/engine/entities/selectors/units.py:277` | Feuille = un ensemble d'unités explicite (ex. `{mainTarget}` pour la soustraction AoE). |
| `UnitTrait` | `scripts/python/engine/entities/traits/unit_trait.py:25` | `UnitTrait` @dump.cs TypeDefIndex 24364. Valeur == `traitId` natif ; nom == nom gameconfig. |
| `aura_current_range` | `scripts/python/engine/entities/effects/aura.py:137` | slot 2 = `GetCurrentRange()` evalue sur le PORTEUR. |
| `aura_next_turn_range` | `scripts/python/engine/entities/effects/aura.py:151` | slot 3 = `GetNextTurnRange()`. Contagions : |
| `aura_trait` | `scripts/python/engine/entities/effects/aura.py:112` | slot 0 = `GetTrait()` : le `UnitTrait` que le PORTEUR doit avoir pour que l'aura existe |
| `first_triggered_ability_of` | `scripts/python/engine/runner/abilities/behaviours/grants.py:129` | `Enumerable.First(caster.GetComponent<TriggeredAbilityComponent>().<coll @+0x18>)` -- la |
| `resolve_unit` | `scripts/python/engine/dsl/base.py:105` | Evalue un noeud (souvent `Subject()`/`Target()`) en UN dict d'unite : dict direct, ou 1er dict d'une |

Re-derive le 2026-07-31 : **aucun de ces 17 n'est un nom invente** -- ce sont
des slots de la factory (`Caster`, `CasterTile`, `Subject`, `Target`, `TargetTile`,
cf. `IdunBattleLogic.Entities.DSLFactory$$InitializeShared`), des OPERATEURS
(`And`/`TileIntersect` = `TargetsSelector.op_BitwiseAnd`), de l'infrastructure de
port (`Emit`, `OperationResult`, `resolve_unit`) ou des vehicules de collapse
declares comme tels (`FixedTiles`, `UnitSet`). Le compte, lui, doit rester
surveille : c'est ce chiffre qui reagirait a une invention.
