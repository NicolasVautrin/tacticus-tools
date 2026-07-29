# Build rnca9r7q6c -- citations qui ne resolvent plus

Genere par `scripts/python/probe_251_citation_resolution.py` le 2026-07-29.
**Re-generer plutot que citer ces chiffres** : ils se periment au prochain build.

    build mesure : rnca9r7q6c  (146262 symboles)
    citations `$$` distinctes : 4599  (occurrences : 10357)
    reference    : gqfc5mff6c  (1266 citations bien formees)
    RESOLUTION : 1037 / 1266  (81.9 %)

## Comment lire cette liste

C'est un **MAJORANT de citations a revenir verifier**, PAS un inventaire de mecaniques
retirees du jeu. `CLAUDE.md` (« L'ABSENCE d'une methode dans les tables ne prouve RIEN »)
rappelle deux raisons d'y figurer sans avoir disparu du binaire :

- **corps generiques partages** -- les bases `Playbook<T>`, `Bucket<T>`... ne sont pas
  dumpees, et le corps `__Il2CppFullySharedGenericType` materialise varie d'un build a
  l'autre. Ils sont isoles en section 2 pour ne pas polluer le vrai signal ;
- **corps triviaux dedupliques** -- IL2CPP partage un meme corps entre N classes, la
  table n'en nomme QU'UNE. La citation d'une autre disparait sans que rien ne bouge.

Trancher une entree exige donc une seconde source : slot de vtable a l'execution, ou
recherche du symbole voisin dans la table courante.

## 1. Types metier (219 citations, 39 types)

### `FixMath.NET.Fix64`
- `FromInt`

### `GameCamera`
- `GetGuiId`
- `ShouldBlurBackground`
- `get_ScreenStatus`
- `get_ShouldDisableRenderingWhenBehindSomething`

### `IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook`
- `ShouldEvaluate`

### `IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook`
- `ShouldEvaluate`

### `IdunBattle.AI.Playbook.Loki.MasterOfTheTutelariesPlaybook.u003Cu003Ec__DisplayClass6_0`
- `u003CEvaluateNonComparableu003Eb__0`

### `IdunBattle.AI.Utilities.AUnitEffectsUtility`
- `.ctor`

### `IdunBattle.Core.Damage`
- `GetTotal`

### `IdunBattle.Entities.Abilities.AActiveAbility`
- `SetsEndTurnFlags`

### `IdunBattle.Entities.Behaviours.AttackBehaviour.u003Cu003Ec`
- `u003CExecuteu003Eb__5_0`

### `IdunBattle.Entities.Components.PersistentDataComponent`
- `PersistDatau003C__Il2CppFullySharedGenericStructTypeu003E`
- `TryGetPersistDatau003C__Il2CppFullySharedGenericStructTypeu003E`

### `IdunBattle.Entities.Effects.ADamageDefenseModifierAbilityEffect`
- `CreateEffectDamageMalusForDefense`

### `IdunBattle.Entities.Effects.ADynamicStatModifierEffect`
- `.ctor`

### `IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect`
- `CreateActiveCondition`

### `IdunBattle.Entities.Effects.Loki.AstartesBanner_AdditionalHitsEffect`
- `CreateTargetSelector`

### `IdunBattle.Entities.Effects.Loki.BaseFleshmetalGunsEffect`
- `.ctor`

### `IdunBattle.Entities.Effects.Loki.BlackRage_AutomaticUnitEffect`
- `.ctor`

### `IdunBattle.Entities.Effects.Loki.ConquerorImperativeEffect`
- `CreateTargetSelector`

### `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect`
- `CreateTargetTrigger`

### `IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect`
- `GetReviveChance`
- `GetReviveHP`

### `IdunBattle.Entities.Effects.Loki.PsychicFortress_DmgReductionEffect`
- `CreateTargetSelector`

### `IdunBattle.Entities.Selectors.AllAliveMachinesSelector`
- `.ctor`

### `IdunBattle.Entities.TileExtensions`
- `CanAddUnit`

### `IdunBattle.Utils.PRNG.MersenneTwister`
- `init_genrand`

### `IdunBattleLogic.Core.Services.Caches.AbilityAndEffectCache`
- `AddSortedu003Cobjectu003E`

### `IdunBattleLogic.Entities.Abilities.Active.ArcScourgeAbility`
- `SetsActiveAbilityUsedFlag`
- `SetsEndTurnFlags`

### `IdunBattleLogic.Entities.Abilities.Active.BlightGrenadesAbility`
- `GetDamageFormula`

### `IdunBattleLogic.Entities.Abilities.Active.LightOfSanguiniusAbility`
- `GetDamage`

### `IdunBattleLogic.Entities.Abilities.Active.Loki.AberrantHypermorphAbility`
- `ExecuteBehaviour`

### `IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility`
- `GetHits`

### `IdunBattleLogic.Entities.Abilities.Active.Loki.CombatRestorativesAbility`
- `HealTargets`

### `IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility`
- `CreateTrigger`
- `GetValidTargets`

### `IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility`
- `GetResurrectTiles`

### `IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility`
- `CreateBehaviour`

### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ExtraDamageAbility`
- `CreateTrigger`

### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.KanOpenerEffect`
- `IgnoreArmor`

### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility`
- `HasToManySummons`

### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility.u003Cu003Ec__DisplayClass7_0`
- `u003CPredictAttacku003Eb__0`
- `u003CPredictAttacku003Eb__1`

### `IdunBattleLogic.Entities.DSLFactory`
- `AbilityHasAttackType`
- `AbilityLevelAmount`
- `ActivateEffect`
- `AddBondEffect`
- `AddDynamicStatModifierEffect`
- `AddDynamicStatModifierEffectToOwner`
- `AddEffect`
- `AddEffectOrIncreaseLevel`
- `AddExtraBlockEffectToOwner`
- `AddOrUpdateStaticStatModifierEffect`
- `AddStatOverrideEffect`
- `AddStaticStatModifierEffect`
- `AddTrait`
- `AddTriggeredAbility`
- `AdjacentEnemies`
- `AdjacentFriends`
- `AdjacentTiles`
- `AdjacentUnits`
- `Alive`
- `AmountIsEqual`
- `AmountIsEqualOrGreater`
- `AmountIsGreater`
- `AmountIsGreaterThanZero`
- `AmountIsOdd`
- `AmountIsZero`
- `AngleBetweenLines`
- `AreEnemies`
- `AreEqual`
- `AttackDamage`
- `AttackDamageIsCritical`
- `AttackWithAbilityDamage`
- `AttackWithAttackDamage`
- `Cache`
- `CanBeRevived`
- `CanSwitchPosition`
- `ChangeEffectTurns`
- `ChangeStat`
- `ClearPersistentData`
- `ConditionalAmount`
- `ConfigVar`
- `ContagionsOfNurgleAmount`
- `Count`
- `DamageProfileFromConfig`
- `Damageable`
- `DeactivateEffect`
- `Difference`
- `Direct`
- `Divide`
- `Double`
- `EffectFromOwner`
- `EffectsFromUnitSource`
- `Enemies`
- `Entity`
- `EntityId`
- `Filter`
- `FilterContinuous`
- `FinishTurn`
- `First`
- `Friends`
- `Get`
- `Group`
- `Half`
- `HasAnyEffect`
- `HasBeenAttackedAmountThisTurnIsEqualOrGreater`
- `HasBeenRevivedByAbility`
- `HasEffect`
- `HasFaction`
- `HasFlag`
- `HasNegativeModifier`
- `HasTileStatusEffect`
- `HasTrait`
- `HasUnit`
- `HealthPctIsBelowOrEqual`
- `HeroUnits`
- `If`
- `InitializeShared`
- `IsActiveAbilityCountedAsUsed`
- `IsAdjacent`
- `IsAlive`
- `IsCharging`
- `IsDead`
- `IsDefeated`
- `IsDirectTargetAttack`
- `IsFirstHitInSeries`
- `IsInRange`
- `IsInTeamContagionsOfNurgleAura`
- `IsMeleeAttack`
- `IsNormalAttack`
- `IsObjectOrSteppable`
- `IsPersistentData`
- `IsRangedAttack`
- `IsRepairable`
- `IsSurrounding`
- `IsTurnOf`
- `IsUnit`
- `Kill`
- `LastHitDamageTakenLastTurn`
- `Max`
- `Maybe`
- `Min`
- `MinDistance`
- `Modulo`
- `MovableTilesInRange`
- `Negative`
- `NonSteppableOrObjectUnits`
- `NormalAttackDamage`
- `OnDeathEvent`
- `OnPreDeath`
- `OwnerHasFinishedMinTurns`
- `OwnerOfEffect`
- `Parent`
- `PercentageOf`
- `PercentageOfAttackCappedAtMax`
- `PerformAIAction`
- `PerformAIAttack`
- `PerformAIAttackFromCurrentPosition`
- `PickRandomly`
- `PrimaryActiveAbilityLevelAmount`
- `PushUnit`
- `RandomAmount`
- `Randomize`
- `RemoveMachine`
- `RemoveTriggeredAbility`
- `RemoveUnit`
- `Repair`
- `ResetActiveAbility`
- `ResetTurn`
- `Resurrect`
- `Revive`
- `RoundsStarted`
- `SetCache`
- `SetPersistentData`
- `SortByDistance`
- `SortByFormula`
- `SortTilesByUtility`
- `SortTilesByUtilityForSummon`
- `SortUnitsByDamageUtility`
- `SortedAttackSeries`
- `StatAmount`
- `SurroundingEnemies`
- `SurroundingFriends`
- `SurroundingTiles`
- `SurroundingUnits`
- `SwitchPosition`
- `ThreeTileUnitSpawnShape`
- `TileHasTriggeredAbility`
- `Tiles`
- `TilesAtDistance`
- `TilesBehindInLine`
- `TilesUnitCanMoveToChargeTarget`
- `TotalActiveAbilityUsed`
- `TotalRepairActionsAmount`
- `TriggerAbility`
- `TurnsFromRounds`
- `TurnsUntilUnitOwnerTurn`
- `Unique`
- `UnitMovementRangeWithBonus`
- `UnitNormalAttackType`
- `Units`
- `UnitsDamagedThisPhase`
- `UnitsDirectlyBehind`
- `UnitsFromFaction`
- `UnitsOnTilesWithEffect`
- `UnitsThatCanHaveActiveAbilityReset`
- `UnitsWithId`
- `UnitsWithIds`
- `UnitsWithRangedAttacks`
- `UnitsWithTrait`
- `UnitsWithVisualId`
- `UnitsWithoutTrait`
- `Unobscured`
- `ValidNormalAttackTargets`
- `VisualUnitIdFromUnitId`

### `meta_pvp_screen_test.u003Cu003Ec`
- `u003CStartu003Eb__6_1`

## 2. Corps generiques partages (10 citations) -- MESURE depuis, cf. #259

> **La mesure demandee ici a ete faite** (`docs/rl/case-259-couverture-gshared.md`, sonde
> `probe_259_gshared_coverage.py`). Leur absence n'est PAS le churn attendu d'une mise a jour :
> la table de `gqfc5mff6c` en nommait **4 882**, celle du build courant **0**, parce que ces
> noms venaient du seul applier legacy Il2CppDumper, supprime le 2026-07-25. Deux taches
> ouvertes (#259-a, #259-b) ; deux de ces citations bloquent #257.

### `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E`
- `AddAction`

### `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E`
- `.ctor`
- `GenerateMultiHitAttackPredictions`
- `MakeEffectPredictions`

### `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E`
- `CalculateUtilityFromDamageEvent`
- `CalculateUtilityFromHealEvent`
- `CountEnemiesOnTiles`
- `GetMovementUtility`

### `IdunBattle.AI.Playbook.TriggeredAbilityNonOwnerPlaybooku003C__Il2CppFullySharedGenericTypeu003E`
- `GetUtilityValue`

### `IdunBattle.AI.Playbook.TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E`
- `IsRegularAttack`

