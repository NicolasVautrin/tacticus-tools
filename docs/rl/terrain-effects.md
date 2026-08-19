# Terrain & power-up tile effects — RE map + port plan (workstream A+B)

Build `gqfc5mff6c`. Objectif : porter TOUS les effets de tuile (terrain + power-ups) qui touchent le
combat, en PREDICTION (oracle/damage view) ET dans le RUNNER offline (sim multi-tour). Origine : #113
(LightCover) etendu par l'utilisateur a l'ensemble terrain + power-ups.

## 0. Distinction structurante (mesuree live)

- **Prediction (etat courant)** : les effets de tuile sont DEJA captes — `decisionView.effects`
  (IsActive-filtered) porte `LightCover`/`Trench`/... ; `combatSnapshot.statDelta`/shields portent les
  boosts power-up + boucliers. => la prediction est correcte SAUF la ou le port IGNORE un effet capte.
- **Runner multi-step** : les transitions de tuile sont portees UNE PAR UNE (jamais une infra
  generique) — a ce jour : stat-mod DEFENSE enter/leave (#198), pose de la couverture a l'ENTREE
  (residu O3), fire-spread (#127), FirstAid (#130). RESTENT hors port : pickup de power-up (#B2),
  BrokenIce, ShrubBonusDefense.
- **SEED des effets de TUILE : RESOLU (#102, `case-102-tile-effect-seeding.md`)**. `load_state(...,
  tiles=tileMeta)` charge desormais les effets portes par les TUILES (meme cle entite-tuile que la pose
  `AddEffectOperation`). Avant, un etat offline recharge mi-bataille repartait d'un plateau VIERGE ->
  toute mecanique tile-driven etait INCONFRONTABLE.
- **EVOLUTION des effets de TUILE : RESOLU (residu O3, `case-o3-tile-effect-dynamics.md`)**. Le tick de
  duree natif (`IdunBattle.Operations.EndTurnOperation$$RefreshEffects`) itere TOUTES les entites-EFFET
  — aucune distinction unite/tuile — puis RETIRE celles dont `EffectComponent$$ShouldBeRemoved`
  (`HasTurns && Duration == 0`). Le port decremente desormais avec le clamp natif de
  `EffectComponent$$RemoveOneTurn` et RETIRE a echeance (avant : le feu de tuile brulait pour
  toujours, `has_effect` ne filtrant que `consumed`). La POSE de la couverture a l'entree est portee
  au meme endroit (`LightCoverAbility`, `On(0x24=UnitPositionChanged_1)`).

Preuve empirique (runner C1_25/SyncPvp_Arctic_06) : `LightCover` et `Trench` sont IsActive-gate sur
"actuellement sur la tuile" — l'effet DISPARAIT de `decisionView.effects` des que l'unite quitte la
tuile (u50 (4,5)DryBush LightCover=True -> (1,4)Grass LightCover=False ; u84 (2,0)Trench Trench=True ->
(0,0)Grass Trench=False). `DryBush` <=> `LightCover`, `TileId==Trench` <=> `Trench` (confirme).

## 1. Inventaire terrain (scan 779 boards, board.py `terrain_counts`)

`Grass`(779), `Block`(662), `Swamp`(461), `DryBush`(455), `Water`(307), `Bridge`(287), `Trench`(77),
`BrokenIce`(40), `FirstAid`(25), `HulkWall`(17), `HulkDoor`(15). Le terrain vit dans `TileId` de la BC
(lisible offline via board.py ; live via `projectTile.tileDefId`). Boards de validation : DryBush
`C4_09`(17)/`C1_25`(15) ; Trench `C2_19`(17) ; LES DEUX `SyncPvp_Arctic_06`(DryBush7+Trench13) ;
arene `MC1_67` = 3 DryBush. Recette board-finding : skill `runner.md` 2bis.

## 2. Tile-abilities (`IdunBattleLogic.Entities.Abilities.Tiles.*`) — VAs

| Ability | VA CreateBehaviour | Terrain | Effet | Axe |
|---|---|---|---|---|
| `Loki.LightCoverAbility` | 1811c14e0 | DryBush/TallGrass | -2 coups ranged (min1) | **damage/hits** |
| `ShrubBonusDefenseAbility` | 1811c4e10 | Shrub/DryBush | +bonus defense | **damage** |
| `Loki.TrenchAbility` | 1811c8e30 | Trench | -50% degat | **damage** |
| `DryBushAbility` | 1811bf560 | DryBush | (base) | - |
| `DryBushFireSpreadAbility` | 1811bf5c0 | DryBush en feu | DoT fire spread | **damage** |
| `FirstAidHealAbility` | 1811c0490 | FirstAid | heal sur tuile | heal |
| `ThornsBlockMovementAbility` | 1811c8d70 | **Swamp** | bloque mvt + **−50 DEFENSE** | movement + **damage** |
| `BrokenIceAbility` | 1811bed00 | BrokenIce | fall-through blocker | movement |

### LightCover (DryBush) — PORTE (prediction correcte)
`LightCoverEffect.CreateEffectHitsBonusForAttack @180f556b0` (decompile lu) :
`gate = AreEqual(Tiles(ctx@0x148=coverPatch), Tiles(ctx@0x178=targetTile)) & !IsMeleeAttack`
`bonus = ForAdditionWithMinimum(gate, Direct(-hitsReduction=GetNumberConstant(0x2c)), min=Direct(1))`.
Magnitude `globalValues.lightCoverHitReduction=2`. Autres : `IsUnitAffected @1811c1690`,
`UnitsThatNeedEffect @1811c1830`, `IsTallGrass @180ec6210`. Port : `engine/entities/effects/loki.py
LightCoverEffect` (via `hits_malus_from_defender_effects`). Le gate `AreEqual(coverPatch,target)` EST
porte (A3, flag compute-time `defender_on_cover` = terrain de la cible == DryBush) : hors-cover le -2
tombe, l'effet restant PRESENT — c'est le comportement natif (ground truth live). La POSE a l'ENTREE
est portee elle aussi (residu O3, `light_cover_on_enter`) : `CreateTrigger` = `(On(0x19=MatchInit) |
On(0x33=UnitAdded) | On(0x24=UnitPositionChanged_1) | On(0x2e=UnitRevived) | On(0x2f=UnitResurrected))
& NOT AmountIsZero(UnitsThatNeedEffect)` ; `UnitsThatNeedEffect` = `UnitsWithoutTraits(
EntitiesWithoutEffects(Units(coverPatch), [0x3f5]), <cctor: BigTarget 1017 / Vehicle 1029 /
Mounted 0>)`. Seul `On(0x24)` est cable (move + push) ; spawn/revive sur cover = residu documente.

### Trench — NO-OP (gap prediction reel)
`CalculateTrenchReduction @181004830` (decompile lu) : reduction -TrenchReductionPercentage (BC Damage
`Damage.TrenchReductionPercentage=-50`) SI cible `HasEffect(0x423=TrenchEffect)` + `IsTrench(tile)` +
(`!HasTrait(attacker,0x3ed)` OU cible adjacente au param_4) + `!IgnoreTrenchReduction(damageProfile)`.
`IsTrench @180ec6f80 = IsTileWithId(tile, "Trench")`. Effet `TrenchEffect` (.ctor @180f73fb0,
CreateCheckAndRemoveEffectAbilities @180f73e40). `IgnoreTrenchReduction @181559b70` (profils exemptes,
a RE). `TrenchTilesSelector.Select @180efb7e0`, `DSLFactory.Trench @180dfe4a0`. Port actuel :
`damage_modifiers.calculate_trench_reduction(target_on_trench, pct)` existe mais `target_on_trench=False`
CODE EN DUR (prediction.py) -> jamais applique. Fix = materialiser `TrenchEffect` (defender -50%) +
brancher sur presence effet (mirror LightCover), gate `IgnoreTrenchReduction`.

### ShrubBonusDefense — a RE/verifier (1811c4e10) : +defense sur shrub. Capte comme statDelta ? ou effet ?
### DryBushFireSpread — **PORTE (#127, 2026-07-14)** : propagation du feu entre tuiles DryBush.
Ability portee PAR LA TUILE DryBush (chaque DryBush la porte). RE decompile (build gqfc5mff6c) :
- `CreateTrigger @1811bf730` = `On(0x14=env-tick) & HasEffect(self@0x148, FireEffect=5)` -> une tuile DryBush
  ne propage QUE quand elle est elle-meme en feu.
- `CreateBehaviour @1811bf5c0` = `Maybe(SetOnFire, AdjacentTiles(self@0x148) &
  TilesWithTriggeredAbility(0x39=DryBushFireSpread=57) & EntitiesWithoutEffects(Fire=5),
  chance=GetNumberConstant(config,0x25))`. Le filtre `TriggeredAbility 0x39=57` (enum `TriggeredAbilityType`)
  <=> tuile DryBush (seules les DryBush portent cette ability) -> proxy fidele `tile_def_id == 'DryBush'` (aucun
  autre TileId ne la porte sur gqfc5mff6c ; pas de terrain TallGrass dans l'inventaire §1). `chance` = le
  number-constant 0x25 du tile-ability = globalValue `dryBushFireSpreadProbability` = **10** (%).
- Pose = `AddEffect(FireEffect=5)` sur la voisine, duree = `DefaultAmountOfRounds(5)` = **2** (aucun override).
PORT : `engine/runner/operations/triggers.py::dry_bush_fire_spread` (appele par `tile_tick_triggers` APRES le
DoT `On(0x14)`). SNAPSHOT des tuiles-source en debut de tick -> pas de cascade meme-tick (le trigger natif gate
`HasEffect(self,5)` a l'instant du dispatch). 1 `next_bool(10)` par voisine DryBush-sans-feu (`Maybe` per-cible,
MEME motif que `FireOfAbsolution`). Valide OFFLINE (logic test : spread->DryBush, skip Grass, snapshot, roll-fail).
⚠ RNG stochastique (10%) -> confrontation LIVE = STRUCTURELLE uniquement (non bit-exact, comme le ignite empty-hex
de FireOfAbsolution) ; PENDING.
### FirstAid — heal (#130) — RE COMPLETE 2026-07-14, PORT bloque sur HealOperation (partage #94)

Une tuile FirstAid porte l'effet `FirstAidHealEffect` (EffectType 10=0xa) : `FirstAidHealAbility.CreateBehaviour
@1811c0490` = `AddEffect(tile, 0xa, abilityStateRef)`.
- **Trigger** `FirstAidHealEffect.CreateTargetTrigger @180f44250` = `On(0x13) & IsTurnOf(Units(units-on-tile))`.
  L'event 0x13 est emis par `StartTurnOperation.Execute @180ea3fb0` (sequence VERIFIEE 0x12->0x13->0x14->0x15->0x16).
  => fire au DEBUT DU TOUR du joueur, pour chaque unite du joueur COURANT posee sur une tuile FirstAid.
- **Magnitude** `CreateTargetTriggerBehaviour @180f44090` = `Heal(tiles, targets, amount, HealBehaviourOptions{+0x32=1})`
  avec `amount = PercentageOf(StatAmount(target, stat=5, part=2)=maxHP, Direct(GetNumberConstant(0x13)=healPct))`
  = healPct% de la maxHP. `targets = Tiles(UnitsWithoutTrait(Units(units-on-tile), trait=0x19=25))` INTERSECT
  targetSelector@0x88 (les unites sur la tuile SAUF trait 0x19). `CreateTargetSelector @180f3ca70` = Units(tile).

**PORT (recette)** : B0 OK -- `state.board.coords_with_terrain("FirstAid")` identifie les tuiles (le board
capte `tileDefId`). A l'event 0x13 de StartTurn (a AJOUTER a StartTurnOperation.execute, entre le tick 0x12 et
0x14) : pour chaque tuile FirstAid, chaque unite du `player` courant dessus (hors trait 0x19), `heal =
round(maxHP * healPct/100)` puis appliquer via HealOperation (clamp maxHP + event UnitHealed). healPct =
config const 0x13 de l'ability "FirstAidHeal" (gameconfig). stat 5/part 2 = maxHP (a confirmer via StatType/StatPart).

**BLOQUEUR** : aucun HealOperation n'existe cote runner (cf. loki.py:497 #94 "necessite un HealOperation combat").
Le porter (RE `DSLFactory.Heal` + l'operation ECS qui mute HP + emet l'event) est un prealable PARTAGE avec #94.
Validation live : board avec tuiles FirstAid + une unite du joueur dessus au StartTurn -> observer le heal (25 boards en ont).
### Thorns/BrokenIce/Swamp — mouvement (#131) — RE COMPLETE 2026-07-14, DEFERE (aucun trigger jouable confirme)

TOUS effet-driven (JAMAIS un blocage statique de terrain ; le static-block est REFUTE live : Swamp
walkable=TRUE + dans aiMovableTiles, SyncPvp_Arctic_06). Le blocage = pose de `BlockEnteringUnitsTileEffect`
(.ctor @180f35510, exemption `NotBlockingMovementOfTraits @18155b370`) OU flip du flag walkable (BrokenIce).

- **Thorns/SWAMP** `ThornsBlockMovementAbility.CreateBehaviour @1811c8d70` = `AddBlockEnteringUnitsEffect(0,0)
  & AddStaticStatModifierEffectToOwner(0xb, stat 3=DEFENSE, Direct(GetNumberConstant(0x14)))` (block +
  −50 DEFENSE). ⚠ **Le tile-def porteur est SWAMP, PAS "Thorns"** (aucun board n'a de tileDefId "Thorns" ;
  marche live probe_198_map : `{Grass:0, Trench:0, DryBush:0, Swamp:-50}` ; desc localisée `SwampBlockMovement
  @1809cdf10`). L'effet `ThornsDefenseReductionEffect` (`CreateTargetSelector @180f47ea0` =
  `UnitsWithoutTrait(Units(tile), Immune)`). Face combat au LOAD = #197 (fold DEFENSE ×1.5) ; matérialisation
  DYNAMIQUE enter/leave = **#198 PORTÉ+VALIDÉ** (`tiles.apply_tile_defense_on_move`, cf. case-198). #131
  (blocage mouvement) reste déféré.
- **BrokenIce** `BrokenIceAbility.CreateTrigger @1811bed90` = fire sur events d'ENTREE d'unite
  (`On(0x19=25) | On(0x1d=29) | On(0)|On(0x35)`, gates `OwnerIsTargetTile`/`OwnerIsCasterTile`,
  `!HasTrait(0x1b=27)`, `!TriggeringAbilityIs(0x47f)`). `CreateBehaviour @1811bed00` : si event==0x19 ->
  `AddBlockEnteringUnitsEffect` (la glace se brise -> bloque) ; sinon `AddEffect(0x12, abilityStateRef)`.
  `BrokenIceBlockerEffect` Apply @180f36c20 SET tileComp+0x10=1 / Revert @180f36e10=0 -> flip DYNAMIQUE du
  flag walkable (IsWalkable false). `DSLFactory.WalkableAndBrokenIce @180e01e40` = selecteur combine.
- **Swamp** `SwampBlockMovement` (PassiveAbilityType 5, desc @1809cdf10) = env-ability du board ; pose
  `BlockEnteringUnits` SOUS CONDITION (non identifiee) -> ne bloque PAS par defaut (empirique).

**Gate pathfinding natif** : `IdunBattle.Entities.Pathfinding.BasePathfinder$$NodesInNextLevel` gate
l'expansion sur `IdunBattle.Entities.Pathfinding.WalkPathfinder$$IsValidContinuePathTile` =
`IdunBattle.Entities.Pathfinding.WalkPathfinder$$GetTileBlockingReasons == 0` (sauf start) : bit 0x1 =
effet block-entering, bit 0x2 = « l'hex FINIT le mouvement » (`WalkPathfinder$$GetEffectiveDepth` ->
`Min(1, depth)`), bit 0x4 = occupant ennemi. Le predicat d'arete
`IdunBattle.Entities.Pathfinding.WalkPathfinder$$IsValidPathNode` NE regarde PAS l'effet (juste
walkable comp+0x10 + elev + !ennemi).

⚠ **CORRECTION (2026-07-27, case-r5)** : la phrase « une tuile block-entering ne peut etre ni TRAVERSEE
ni un STOP » etait **FAUSSE sur la moitie STOP**. Le gate est UNIQUEMENT sur l'EXPANSION : mesure live
`MC1_67` a portee forcee 1/2/3, les tuiles Swamp (4,6) et (1,6) SONT dans `aiMovableTiles` — on peut
s'y ARRETER, on ne peut pas CONTINUER au-dela. C'est un CUL-DE-SAC, pas un mur.

**Port — FAIT (2026-07-27, case-r5, #131 volet bit-0x1)** : `walk_pathfinder.get_reachable_levels`
accepte un `can_continue` (mirror du gate de `NodesInNextLevel`), `entities/pathfinding/tile_blocking.py`
le derive de `State.effects.by_unit[tile_entity_id]` (+ exemption
`static_battle_rules.not_blocking_movement_of_traits` = Mounted/Vehicle/Unstoppable), et
`ai/state_bridge._move_tiles` le pose. Agrement `aiMovableTiles` 5 boards, 0 ecart dans les deux sens
(cf. case-r5 §6). Reste NON porte : le bit 0x2 (aucun datapoint sur la condition qui le pose).

⚠ **La pose de l'effet est CONDITIONNELLE — ne JAMAIS gater sur le TERRAIN.** Mesure du 2026-07-27 :
`MC1_67`/`MC1_64`/`C2_26`/`C1_47` ont des tuiles block-entering ; `PVP_desert_04` n'en a AUCUNE live.
Un gate sur `tileDefId == 'Swamp'` sur-bloquerait. Le port lit l'EFFET (EffectType 0), jamais le
tile-def. La CONDITION de pose de `SwampBlockMovement` reste a RE.

⚠ **CORRECTION (#102)** : l'affirmation « INERTE car aucun board courant ne le porte » etait **FAUSSE**.
Mesure live (`tileMeta`, board `C1_02`, des la construction du runner) : les tuiles **Swamp** portent
`BlockEnteringUnits` (EffectType 0) **et** `Thorns_DefenseReduction` (0xb). Ces effets etaient
invisibles offline tant que `load_state` ne seedait pas les effets de tuile ; ils le sont desormais
(`state.effects.by_unit[tile_id]`) — **a condition d'appeler `load_state(..., tiles=tileMeta)`** :
sans ce canal le gate #131 est un no-op SILENCIEUX.

### ICE dynamique (0x11) — #133, MECANIQUE RE'd 2026-07-16 (carrier jouable Arjac + Stormcaller)

⚠ DEUX classes distinctes : `IceTileEffect` (@180310a90 Freeze / @180310b60 Melt / FreezeCoroutine) =
couche VUE Unity (coroutine, view-only) ; **`IdunBattle.Entities.Effects.IceEffect`** (@180f44bc0 ctor) =
l'EFFET DE COMBAT (namespace Entities.Effects, comme les autres effets). C'est le second qui compte.

`IceEffect.ctor @180f44bc0` = `ABondEffect(1,0,...)`, EffectType `0x11`, pose
`NotBlockingMovementOfTraits(0x11)` @+0x488 -> **MECANIQUE 1 = blocage de mouvement** (comme BrokenIce ci-dessus,
exemption par trait). `IceEffect.CreateEffectDamageBonusForAttack @180f44940` -> **MECANIQUE 2 = bonus de
degat conditionnel au CRIT** : trigger = `AttackDamageIsCritical` AND `AreEqual(Units(owner,1,3), target)` AND
`NOT HasTrait(target, Immune=0x19)` ; magnitude = `PercentageOf(StatAmount(owner, CRIT_DAMAGE=10), EffectConfig(5))`.
(Direction exacte buff/debuff + selecteur `Units(owner,1,3)` = interpretation A TRANCHER, non devinee.)

Placeurs de tuiles ICE : `AnvilShieldAbility_ApplyIce @180e16480` (Arjac spaceRockfist, ON-BLOCK, cf. #133) ET
`StormcallerAbility.GetAddIceTiles @18120cf70` (2e carrier). Effet lie a l'attaquant gele :
`AnvilShield_FrozenAttackerAdvantageEffect` (1201, ctor @180f31e50) = `ADynamicStatModifierEffect`,
EffectSource `0x493` (AnvilShield 1171), `CreateTargetTrigger @180f31dc0` = `On(0xe) & AreEqual(target@0x178,
EffectSource)` -> avantage DYNAMIQUE contre l'attaquant gele specifique.

**Port : PARTIEL** — le PLACEUR LordOfTempests est PORTÉ (#35, `case-35` :
`LordOfTempests_AddIceAbility @181108670/@1811085d0` → `triggers/loki/lord_of_tempests.py`, pose Ice(17)
sur la tuile de chaque ennemi touché par une normale de Njal, durée défaut 2 rounds, replay-diff 2/2 ;
+ couplage combat att_ctx → snowball `LordOfTempests_ExtraDamage` bit-exact). Le 2e PLACEUR est PORTÉ
aussi (#217, case-217) : l'ACTIVE **Stormcaller 1113** (`ExecuteBehaviour @18120cc20` : zone
`GetAddIceTiles @18120cf70` = cible+ring-1, puis 3× Psychic sur `UnitsOnTilesWithEffect(Enemies, Ice)`
= TOUS les ennemis sur glace, puis Stun 1 round des Flying du cache — `runner/abilities/loki/
stormcaller.py`, probe_217 bit-exact). RESTENT GATE : le placeur Arjac on-block (#128/#133), le blocage
mouvement (#131, defere faute de board jouable), le crit-bonus (mecanique 2), le gate sante de 1200
(ABS-vs-% a trancher live), le dynamique 1201. Seul `1202 AnvilShield_AdditionalBlock` etait deja
porte (loki.py, cf. #133).

## 3. Power-ups (`Abilities.Triggered.Loki.APowerUpAbility` family)

Pickups poses sur des tuiles (`TileExtensions.HasPowerup @180ec5570`, `UnitExtensions.IsPowerUp
@180ed8d00`, `DSLFactory.TilesWithoutPowerUps @180dfdbf0`). Ramasses en marchant dessus -> effet persistant.
Types : `AbsoluteStatBoostType` / `PctBasedStatBoostType` (`AddPctBasedBoost @180e138d0`) -> `PowerUp_Effect`
(.ctor @180f46470) ; armor -> `PowerUp_ArmorEffect` (.ctor @180f460e0) ; shield (`AddShield @180e13cb0`,
`PowerUp_ReinforcementShieldAbility.IncreaseShield @181113050`, `IsPowerUpThatAppliesShieldToTarget
@181581fc0`) ; `PowerUp_BombAbility @181112540` ; resurrect. Spawn : `APowerup_SpawnAbility.GetSpawnTile
@181106240`, `GetKillBehaviour @1811060c0`, `GetPowerUps @1815815f0`. IA : `PowerUpTileUtility @1810f15b0`
(`EvaluateAttackInSteps @1810f14c0`, `EvaluateMovementInSteps @1810fd130`). En prediction : les boosts
ramasses sont deja captes (statDelta/shields). En runner-sim : le pickup-on-move n'est pas modelise.

### 3bis. Placement des power-ups dans la BC (ou vivent-ils sur le board)

Scan des 782 dumps `data/boards/**` (probe_powerup_detail.py) : les power-ups ne sont PAS un `TileId`
terrain (les tuiles ne portent que Rotation/TileId/Elevation/RoomID/ForceUnplayable). Ils sont places
par le **spawn-point-set** :

    board.SpawnPointSets[i].GameModeTiles[].PowerUpUnits[] = { "UnitId": "<powup...>", "Position": {Column, Row} }

(a cote de `Player0/1SummonTiles`, `TerritoryTiles`, `SyncPvpRuleset`, `Mode`). Chaque power-up = une
UNITE neutre posee sur une tuile (ramassee en marchant dessus, cf. §3). **36 boards distincts** en portent,
TOUS du mode Sync-PvP (familles `SyncPvp_*` + `Infested_SyncPvp_*`, + le campagne `C2_31`) ; aucun board
d'arene/campagne standard. 5 types de `UnitId` :

| UnitId | effet | occurrences |
|---|---|---|
| `powupDamage` | boost degat | 65 |
| `powupMeleeHits` | +coups melee | 60 |
| `powupArmor` | boost armure | 59 |
| `powupHealth` | soin/PV | 57 |
| `powupHits` | +coups (ranged) | 41 |

Boards les plus riches (validation B2) : **`SyncPvp_Arctic_01`** (20 power-ups = 5 types x4),
`SyncPvp_Desert_01` (15 = 5x3), puis ~10 chacun (`SyncPvp_Arctic_06` — qui porte AUSSI la Trench —,
`SyncPvp_Temperate_02/03`, `SyncPvp_Desert_04/05`, ...).

**CONSTAT B2 (live, verifie 2026-07-12)** : `rl_duel build --board SyncPvp_Arctic_01` N'INSTANCIE PAS les
power-ups. Le runner construit a `units=2` (les 2 rosters), 3 players (team1/team2/Environment) mais
l'Environment porte **zero unite** ; aucune entite type-1 `powup*` ; `boardGraph.occupantUnitId` = seulement
les 2 combattants. => le spawn des `GameModeTiles.PowerUpUnits` appartient a la logique d'INIT du mode
Sync-PvP, court-circuitee par le chemin de build generique du runner. **Consequence** : B2 n'est PAS
atteignable en montant simplement une seed board — il faut d'abord un pas de SPAWN explicite (porter le
spawn natif des power-up units depuis `GameModeTiles.PowerUpUnits` via `AddUnitOperation`, cf. le spawn de
summon #33/#65) AVANT de pouvoir porter le pickup-on-move. B2 est donc plus gros que "juste le pickup".

## 4. Positionnels non-terrain (rappel, deja portes #58/#61)
Elevation `CalculateElevationBonusModifier @181003ea0` (+50% surplomb, porte). RangedInMelee
`@181004700` / `ShouldApplyRangedInMelee @181005810` (-50% ranged adjacent ennemi, porte).

## 5. Plan (slices)

**A. Gaps PREDICTION (petit, validable maintenant)**
- A1. **[DONE `d9d0e6c`]** Trench : le natif a UNE seule fonction `CalculateTrenchReduction @181004830` gatee sur
  `HasEffect(target, 0x423=TrenchEffect)`. Le port a son homonyme `calculate_trench_reduction(
  target_on_trench, pct)` mais l'appelle avec `target_on_trench=False` CODE EN DUR (prediction.py:130).
  FIX (PAS de nouvelle classe = pas de duplication) : gater `target_on_trench` sur "la cible a un effet
  Trench" (effet nomme 'Trench' dans decisionView.effects = tgt_effects, IsActive => on-trench) +
  `!IgnoreTrenchReduction(damage_profile)` (@181559b70 = List.Contains(profils, dp) ; RE la liste, defaut
  vide). NB `calculate_trench_reduction` owner_is_caster=True (attaquant) = maths identiques a -50% defender.
  Valider SyncPvp_Arctic_06 (u84 sur Trench, necroDestroyer 6 ranged -> oracle -50% vs offline).
- A2. ShrubBonusDefense : RE + wirer si non capte.
- A3. **[DONE — non commite]** LightCover : gate compute-time fidele. Le natif
  `LightCoverEffect.CreateEffectHitsBonusForAttack @180f556b0` RE-verifie a CHAQUE attaque
  `AreEqual(Tiles(coverPatch@0x148), Tiles(target@0x178)) & !IsMeleeAttack` -> -ConfigConst(0x2c), min 1.
  Le port ne gardait que `!IsMeleeAttack` + la PRESENCE de l'effet (correct en prediction : cible immobile,
  presence IsActive live <=> sur-cover). En RUNNER-SIM l'effet peut PERSISTER apres un move hors-cover
  (faute de B1). FIX : threader `defender_on_cover` (= terrain de la cible == DryBush, via `state.board`
  #124) dans la formule partagee `attack_hits_with_modifiers` -> `hits_malus_from_defender_effects` ->
  `LightCoverEffect.create_effect_hits_malus_for_defense` ; `False`=hors-cover (drop), `None`=inconnu
  (applique-sur-presence = prediction inchangee). Combat (`AttackDamageOperation.execute`) calcule le gate ;
  prediction laisse None. DryBush = TileId hote de LightCoverAbility (empirique live + `UnitsThatNeedEffect
  @1811c1830 = Units(coverPatch@0x148)`). VALIDE LIVE (SyncPvp_Arctic_06) : cible sur DryBush -> 3 ranged
  hits chutent a 1 (-2) ; DEPLACEE sur Grass, effet CONSERVE -> 3 hits (gate, pas retrait). Regression
  getstuckin combat bit-exact + predict 2/2 verts. Test : `tests/engine/runner/test_lightcover_gate_live.py`.
- A4. DryBushFireSpread : DoT (RE + port si pertinent combat).

**B. Runner-sim tile-triggers (grand)**
- B0. **[DONE — non commite, valide live]** INFRA : `tileDefId` (+`isTemporary`) dans `boardGraph`
  (rpc-board.ts) ; `Board` (pathfinding) accessors `tile_def_id`/`terrain_at`/`coords_with_terrain`. Valide
  live 63/63 tuiles sur SyncPvp_Arctic_06 (Trench 13/DryBush 7/Block 6/Swamp 2/Grass 35). [prerequis de A3
  + tout B ; consomme par le gate LightCover A3 via `state.board.terrain_at`]
- B1. LightCover/Trench/Shrub : add/remove effet on enter/leave terrain (MoveUnitOperation).
  **[LightCover : DONE — residu O3, `case-o3-tile-effect-dynamics.md`]** POSE a l'ENTREE via
  `On(0x24=UnitPositionChanged_1)` (move ET push), gate de traits du `.cctor` porte, valide live
  (pose + non-pose sur BigTarget + composition 6->4 coups). Le "remove on leave" n'existe PAS cote
  natif pour LightCover : l'effet est CONSERVE et neutralise par le gate compute-time (A3). RESTENT :
  Trench, Shrub, et les 4 autres events de `CreateTrigger` (spawn/revive sur cover).
- B2. Power-up pickup on-move (APowerUpAbility -> stat boost / armor / shield / bomb).
- B3. FirstAid heal-on-tile (turn/step trigger).
- B4. Thorns/Swamp/BrokenIce : blocage mouvement (pathfinding).
- B5. **[DONE #127, 2026-07-14 — offline]** DryBush fire-spread : `dry_bush_fire_spread` au tick `On(0x14)`
  (cf. §2 `DryBushFireSpread`). Propagation feu DryBush->DryBush adjacent, `next_bool(dryBushFireSpreadProbability
  =10)` par voisine, snapshot source. Validation LIVE structurelle PENDING (stochastique).

Validation : chaque slice confronte offline vs live sur un board portant le terrain (cf. 1).
Prerequis live : amorce apres chaque (re)inject.

## 6. Effets de tuile DYNAMIQUES (poses en COMBAT par unit/MoW) — famille decoy/fire/ice/poison

Distincts du terrain STATIQUE (§2, baked dans TileId) : ces effets sont materialises PENDANT le combat
(AddEffect sur `Tiles(target)`) par une ability, puis appliques aux UNITES qui occupent/entrent/demarrent
un tour sur la tuile. RE 2026-07-12 (4 familles, VAs citees). **Dependance commune** : tous ont besoin du
VECTEUR tile/step-trigger du runner (enter-tile On(4) / round-tick On(0x12) / turn-start-on-tile) pour etre
valides OFFLINE end-to-end -> #128 (B1) est l'UNLOCK partage. Les CLASSES d'effet (magnitudes) sont portables
decompile-first independamment ; leur PLACEMENT est gate sur #128.

### 6.1 CONTAMINATED (Toxic) — #132 — debuff -X% ARMURE (PAS un DoT)
Effet tuile 0x4dc=1244 "Contaminated" (0 degat/tour) ; sous-effet 0x4dd=1245 "Contaminated_Unit"
(ContaminatedStatModifierEffect, ADynamicStatModifierEffect FixedArmor, ctor @180f3a560) = -X% FixedArmor
DYNAMIQUE sur l'unite, 1 round. Placement : `OnToxicDamageAbility @1811c3c00` (If IsFirstHitInSeries &
Maybe(toxicDamageContaminationChance=25%) -> AddEffect(0x4dc, Tiles(target))) ;
`ContaminatedEffect.CreateHandleTriggerAbilitiesInternal @180f3a1d0` = On(0x12 round-tick)/On(4 enter-tile)
gate !HasEffect(0x4dd) -> re-applique 0x4dd. Immunite `EntityIsImmuneToEffect @180f3a400` = HasTrait(0x7eb=
2027) OU IsMechanical. Carriers jouables : deathPutrifier/tyranParasite/admecMarshall/genesBiophagus/
admecDominus. **CAVEAT MAGNITUDE (non resolu)** : `GetDynamicStatModificationAmount @180f3a460` lit le pct via
un appel d'INTERFACE (slot 0xbe sur objet @effect+0x50, arg=6) puis NEGATE. Le nom "contaminatedArmorReduction
Pct=30" de la 1re spec N'EST PAS dans gameconfig (`global_value`->None ; trait Toxic variables={}). NE PAS
hardcoder 30 -> resoudre la vraie source (@180f3a460 + base @180f090f0 : quel stat-part) AVANT le port. Bug
incident corrige+commite (9e9a64c) : `_DEFAULT_ROUNDS[0x4dc]`=2 (etait 1, natif @181559ff0=2).

### 6.2 FIRE (DryBush en feu) — #127 — DoT turn-start
FireEffect (EffectType 5) : DoT debut de tour = ~20% initial HP (`fireDmgPct=20`), decay 2 rounds
(_DEFAULT_ROUNDS[5]=2), spread 10% aux DryBush adjacents (`dryBushFireSpreadProbability=10`,
`DryBushFireSpreadAbility @1811bf5c0`). Carriers : adeptCanoness(BrazierOfHolyFire)/thousAhriman/eldarRanger.
Le runner EndTurn ne fait AUCUN DoT -> gap. Vecteur turn-start-on-fire-tile = #128.

**CONFRONTATION LIVE (2026-07-12, runner adeptRetributor flamer Flame -> blackHaarken) — 3 DIVERGENCES du port :**
- (1) PLACEMENT **confirme** : l'attaque Flame pose bien `FireEffect(type 5)` sur la/les tuile(s) cible (lu via
  `tileMeta.tiles[].effects`). Direction du port OK.
- (2) **AoE MULTI-TUILE** — **RESOLU (§6.6, 2026-07-13)** : PAS une arme AoE. Le multi-tuile (5 tuiles observees)
  vient du **passif `FireOfAbsolution`** de Vindicta (splash 3x Flame sur ennemis adjacents + 30% ignite/hex vide).
  Le port generique OnFire (1 tuile-cible) est CORRECT ; le passif est un trait a part, porte separement (§6.6).
- (3) **MAGNITUDE DoT (port FAUX)** : mesure live = **477** sur blackHaarken (maxHP 9539). Le port applique un
  forfait plat 20% max = **1908**. Or **477 = 1908 x 0.25** EXACTEMENT = base(20% max) x PiercingRatio(Flame=25%).
  => le DoT N'EST PAS armor-independant : c'est une attaque profil **Flame** (`AttackWithAbilityDamage(..., Flame,
  Direct(3))`) qui PASSE PAR LE PIPELINE PERCAGE/ARMURE normal (PiercingRatio 25% perce, le reste absorbe par
  l'armure de la cible ; blackHaarken tres blinde -> 75% non-perce entierement bloque -> net = 25% de la base).
  L'i2 « 20% of initial Health » decrit la BASE, pas le net. Le port doit router la base 20%-max via
  `apply_pierce_and_modifiers` (Flame, armure cible), PAS un `hp -= 20%*max` plat. SUR-applique jusqu'a ~4x.
- (4) **DUREE** — **RE-RESOLU (#127) puis CORRIGE (2026-07-14, confrontation MoW propre)** : `DefaultAmountOf
  Rounds(5) @181559ff0` = **2 ROUNDS** (switch decompile : {5,17,18,58,1244,1476}->2, 79->3, {1065,1162}->1,
  sinon null) ; `OnFireDamageAbility @1811c3a60` = `AddEffect(5, ..., 0, 0)` sans override -> le count NATIF est
  bien 2 rounds. ⚠ Mon explication precedente « remaining=3-4 = artefact de RE-ignition Vindicta » etait **FAUSSE**.
  Confrontation PROPRE (MoW blackForgefiend, `DaemonicOrdnance` -> cascade `Effect_Refresh «Fire» Effect_Remaining
  Turns=4`, source EnvFireTileDamage=24, ZERO Vindicta) : le natif stocke la duree en **TURNS** = `ConvertRounds
  ToTurns(DefaultAmountOfRounds)`. Le `3-4` Vindicta etait la MEME chose (pas une re-ignition).
  **#174 RESOLU (RE re-expert 2026-07-14)** : `ConvertRoundsToTurns @181058af0 = count(joueurs du turnOrder,
  PlayerType != 2) x rounds`. PlayerType@+0x20 = **config STATIQUE** (prouve via `VisualBattleQuery.GetPlayerType
  ForEntity @1804aecc0` + `AddPlayerOperation @180e4d840` ; Environment=2 exclu) -> `count` = **CONSTANTE de
  bataille**, PAS un etat de tour. Donc `TurnsFromRounds` n'est PAS un simple ×2 : c'est ×count.
  **Le port est CORRECT pour nos runners** : dans nos 1v1, `count = 1` -- PROUVE par le test committe
  `test_effect_stun_live` (Stunned DefaultAmountOfRounds=1 -> convert(1) = live_remaining = 1). count etant
  constant, TOUT effet round y dure `rounds x 1` -> le feu = 2 turns = `remaining=2` du port = JUSTE (pas de
  sous-duree). L'ancre `Effect_RemainingTurns=4` etait une bataille **count=2** (arene MoW), que le port NE
  SIMULE PAS. => `turns_per_round=1` (accessors.py/base.py) est CORRECT pour notre domaine de validation ; le
  ~2x n'est **LATENT que pour count>=2**. Fix futur (si un jour on valide du count>=2) = `convert_rounds_to_turns
  (state, rounds)` lisant le turnOrder runtime (capteur requis : dumpEntityComponents ne balaye pas les Player).

Bilan : l'offline « 23/23 » validait le port contre une SPEC (mon interpretation i2), pas contre le natif. Live
REFUTE la magnitude (armor-routing), l'AoE et la duree. Placement = seul point confirme. -> #127/#136 a corriger.

**GATE IMMUNITE FEU — RESOLU (2026-07-12, dump.cs gqfc5mff6c)** : `EnvFireTileAbility.CreateBehaviour
@18121e040` = `Foreach(UnitsWithoutTraits([0x1b=27, 0x19=25]) & Units(EntitiesWithAnyEffect(5)), AttackWith
AbilityDamage(...))`. Les 2 trait-ids sont l'enum **UnitTrait** (PAS l'enum EFFECT ou 25/27=Taunted_*) :
`0x1b=27=Steppable` (tokens marchables : decoys/mines), `0x19=25=Immune`. Le DoT EXCLUT donc tout occupant
portant Steppable OU Immune. **PORTE** (`FireTileDoT` gate `_is_immune_to_fire`, `ctx.traits`=noms gameconfig
cf. unit_context.py:191) + offline-valide (test_tile_vector J/J2/J3). NB : l'i2 « excluding Flying and
Unstoppable » concerne l'arret-MOUVEMENT (« entering a Fire hex ends movement »), pas ce gate de DAMAGE.

### 6.3 ICE — #133 — Arjac AnvilShield on-block (RE approfondie 2026-07-12)
`spaceRockfist` (Arjac) active AnvilShield (ability enum 0x493=1171 ; vars blockChance[15..20], blockDmg
[10..728 rarity], const healthPct=35). Sur un BLOCK, 4 sous-behaviours (`Triggered.Loki.AnvilShieldAbility_*`) :
- **ApplyAdditionalBlockAndBlockChance @180e16340** : 2 StaticStatModifierEffects self sur Arjac ->
  `0x4b2=1202 AnvilShield_AdditionalBlock` (stat 8 BLOCK_DAMAGE, blockDmg, INCONDITIONNEL) **[PORTE — leaf
  loki.py + factory, L65=728]** ; `0x4b0=1200 AnvilShield_BlockChanceBelowHealthCap` (stat 7 BLOCK_CHANCE,
  blockChance=20) **[PORTE #100]** — l'ambiguite abs-vs-% du cap est TRANCHEE par le decompile :
  `AnvilShield_BlockChanceBelowHealthCapEffect$$CreateActiveCondition` =
  `AmountIsEqualOrGreater(Direct(GetNumberConstant(0x4f=healthPct=35)), StatAmount(Self, 5=HEALTH,
  **1=CURRENT_PCT**))` -> c'est bien un POURCENTAGE (live : blockChance 0 a 100 % PV, 20 a 31.8 %).
- **ApplyIce @180e16480** : pose ICE (dynamic 0x11) sur la TUILE de l'attaquant (!= static BrokenIce 0x12 #131,
  != Freeze-coroutine view-only `AnvilShieldEffectVisual`). Placement tuile = **vecteur #128**.
- **ApplyStun** (`AnvilShieldAbility_ApplyStun$$CreateTrigger`/`$$CreateBehaviour`) : Stun (0x48a) sur
  l'attaquant MELEE bloque, gate `HasEffect(1200|1201, **activeOnly**)` **[PORTE #100]**.
- **FrozenAttackerAdvantage** (`AnvilShieldAbility_FrozenAttackerAdvantage$$CreateTrigger`/
  `$$CreateBehaviour`) : effet dynamique `0x4b1=1201` (`AnvilShield_FrozenAttackerAdvantageEffect$$.ctor`,
  `$$CreateTargetTrigger` = `On(0xe=UnitPostAbility) & AreEqual(target, EffectSource)`) = +20 % block
  TRANSITOIRE contre l'attaquant gele **[PORTE #100]** — vecteur `On(0x2b=PreUnitAbility)` ajoute, effet
  consomme en fin d'ability (ground truth live : absent de decisionView juste apres l'attaque).
Carrier jouable (Arjac). 1202 validable via scenario BLOCK live (statModSources stat 8), cf. BeastSlayer #72.

### 6.4 DECOY — #134 — genesPrimus DecoysAndMisdirection
Actif `CultDemagogue` (1179, i2 gameconfig 2026-07-12) : « Targets an enemy within 2 hexes and places decoys
on up to 8 random free hexes within 2 hexes around the target ; then summons Neophyte Hybrids on half of the
decoys... » -> le cast EXIGE un ENNEMI <=2 hexes. Passif `DecoysAndMisdirection` (1304) : (a) spawn genesSmnDecoy
(BuffFriends @180e1fe30) + AddEffect(1390 JustSummoned) ; (b) DamageEnemies @180e20190 = Blast(0x12) par decoy
mort (GetValidDeadDecoys @180e13550) — death-trigger mirror FinalJustice ; (c) effet 0x563=1379.

**PORTE (2026-07-12, decompile-faithful, NON commite)** : classe `DecoysAndMisdirectionExtraDamageEffect`
(loki.py) + registree "DecoysAndMisdirection_ExtraDamage" (effect-type-names.ts:502). Natif
`CreateEffectDamageBonusForAttack @180f3e340` relu = `ForAddition(get_OwnerIsCaster, ConfigVar(8=extraDmg,
EffectSource ability 0x518=1304))` ; ctor @180f3e4a0 = AbilityOrEffect 0x518. Gate **OwnerIsCaster SEUL** (PAS
d'IsNormalAttack) -> additif +extraDmg a TOUTES les attaques de l'ami buffe, en PREDICTION + COMBAT (cf.
Neuroparasite ; contraste SmashaEad #71 qui se gate hors-prediction via IsNormalAttack). Magnitude decompile +
gameconfig (extraDmg[L1..65]=[8..582], rarity-affected) + i2 (« +582 Damage ») ; canal additif POST-percage =
celui deja bit-exact #75/#88. Offline : emet +582 aux 2 chemins. GAP restant : spawn-op + placement 1379
(on-move-onto-decoy = trigger tile-step #128) + Blast retaliation + JustSummoned. VALIDATION live gatee (placer
1379 exige le vecteur spawn/on-move, non porte). Traps : multiplier global vs per-ability passif (#68/#75) ;
niveau/mult = du SOURCE genesPrimus (comme RitesOfBattle aura).

### 6.5 PLACEMENT on-hit (vecteur commun Fire/Contaminated) — RESOLU (agent RE, 2026-07-12)

Comment un tile-effect dynamique se POSE en combat. Verdict re-expert (decompile-prouve, build gqfc5mff6c) :

**Emetteur = `ADamageOperation.EvaluateAfterHitTriggers @180e25fc0`**, appele PER-COUP en fin de resolution
de chaque hit par les 3 `ExecuteHit` (`AttackDamageOperation @180e5eff0`, `AbilityDamageOperation @180e29d50`,
`MachineDamageOperation @180e785b9`). Enfile 2 ops via `IOperationsBuffer` (slots 0x3d conditionnel / 8 incond.)
-> `OperationProcessor.EvaluateAbilities @180e07a60` -> `EvaluateTriggerOperation.Execute @180e6fac0` -> construit
un `BattleEvent(eventId, abilityEntities)` -> `ExecuteInternal @180e6ef40` matche le registre de triggers. Le
payload porte attaquant, cible, **GetTiles(cible) et GetTiles(attaquant)** (les tuiles), le DamageProfile, isCrit.
DEUX events emis ici : **0x10** (gate sur le flag « landed », param_6) et **0x26** (after-hit inconditionnel,
deja emis par le runner). RESERVE non tranchee a l'octet (couche gshared IOperationsBuffer) : la correspondance
formelle slot(0x3d/8)->eventId(0x10/0x26) ; HYPOTHESE 0x10=landed / 0x26=inconditionnel. **Non bloquant pour le
port : 0x10 et 0x26 sont au MEME site** (`after_hit_normal_attack`).

**`OnFireDamageAbility`** (Damage.Loki) : Trigger @1811c3ae0 = `On(0x10) & DamageProfileHasTrait(1=OnFire) &
NOT(TriggeringEffectIs(5))` ; Behaviour @1811c3a60 = `AddEffect(5=FireEffect, Tiles(cible+0x178))` INCONDITIONNEL.
`Tiles(0x178)` = `DSLFactory.Tiles @180dfdc60` sur la tuile CIBLE = **tuile occupee courante de la cible** (PAS un
ring AoE ; wrappe en SortReverseSelector sans expansion). Anti-boucle = le NOT(TriggeringEffectIs(5)) empeche le
DoT du feu de reposer du feu. **RNG-FREE** (pose inconditionnelle).

**`OnToxicDamageAbility`** (Damage.Loki) : Trigger @1811c3d20 = `On(0x10) & DamageProfileHasTrait(4=OnToxic) &
NOT(TriggeringEffectIs(0x4dc))` ; Behaviour @1811c3c00 = `If(IsFirstHitInSeries() & Maybe(ConfigConst 0x2a),
AddEffect(0x4dc=Contaminated, Tiles(cible+0x178)))`. CONDITIONNEL : (a) **1er coup de la salve** (`get_IsFirstHit`
@180fa0c00), (b) **proba** `Maybe(toxicDamageContaminationChance=25%)` (globalValues) -> **consomme du RNG**.

**Gate offline (par NOM, sans ids)** : `DamageProfile.HasTrait @18157c2d0` = `List.Contains(profile.Traits, id)`.
Les 6 traits de profil natifs <-> gameconfig : id1=OnFire=Flame, id4=OnToxic=Toxic(PiercingRatio 70), + Blast
(HitsMultipleMembers), Las (LasCannon), Psychic (NoBlocking), Melta (OnMelta). => lire
`gameconfig.damage_profile(<profil arme attaquante>)['Traits']` et tester `'OnFire'`/`'OnToxic'`.

**Point d'insertion runner** = `triggers.py` `after_hit_normal_attack` (event 0x26 deja porte, MEME site que 0x10).
FIRE = portable proprement (inconditionnel, RNG-free, per-attaque suffit car anti-boucle rend les repeats no-op).

**TOXIC : PORTE ET VALIDE LIVE** (`triggers/loki/on_toxic_damage.py` ; case-doc
`case-1203-on-toxic-damage.md`). Les 4 pieges annonces sont tranches :
(1) granularite per-coup vs per-attaque -> le ET natif COURT-CIRCUITE (`MultipleAbilityTrigger$$
ShouldTrigger` : le droit n'est evalue que si le gauche est vrai), donc le natif ne tire QU'AU coup
d'index 0 de chaque serie ; le vecteur per-attaque du port EST ce coup -> `is_first_hit=True` pose
explicitement, meme compte de tirages (1 par serie, donc 1 par cible) ;
(2) proba 25 % lue en config (`globalValues.toxicDamageContaminationChance`), ancree par test sur la
constante BC `Abilities.PassiveAbilities.OnToxicDamageAbility.Constants.chance` — jamais hardcodee ;
(3) tuile-cible unique CONFIRMEE live (`Tiles(Target())` = MainTile de la cible) ;
(4) anti-boucle structurelle (l'effet de tuile 1244 n'inflige aucun degat `Toxic`) + gate
`already-present` d'`AddEffectOperation`.
Point de placement du tirage : APRES les tirages degat/crit/block du coup, cable sur les DEUX vecteurs
(`after_hit_normal_attack` et `execute_ability_attack`) — verifie par la disparition du « tirage de
retard » de `test_rad_bombardment_live` (geometrie 2 cibles) et par
`probe_1203_toxic_contamination.py` (canal arme 1/1 vs desarme 0/1 face au live).
SOURCE de l'effet pose = la TUILE elle-meme (la surcharge `AddEffect` a 5 args passe un selecteur SOURCE
NUL et `AddEffectBehaviour$$Execute` retombe sur la cible), PAS le caster.

### 6.6 FireOfAbsolution (passif Vindicta) + ArmoriumCherub (actif 1014) — PORTE + VALIDE LIVE (2026-07-13)

L'« AoE multi-tuile » du §6.2 (2) n'etait PAS une arme AoE : c'est le **passif `FireOfAbsolution`**
d'adeptRetributor «Vindicta» (specifique a CETTE unite). Le port generique OnFire (1 tuile-cible) reste CORRECT ;
le multi-tuile vient d'un trait a part.

**Mecanisme natif** (`FireOfAbsolutionAbility.CreateBehaviour @18121f380`, decompile relu 1:1) :
`Inform(0xb3,target) & AttackWithAttackDamage(caster, AdjacentUnits(target,kind=3) - caster - target,
Direct(dmg=GetVariableForLevel 0xb), Flame, nrOfHits=GetNumberConstant 0x2f=3) & Maybe(SetOnFire,
AdjacentTiles(target), chance=GetNumberConstant 0x2a=30)`.
- `AdjacentUnits(kind=3)` = ennemis du caster (cf. StikkbombAbility « team-param 3 -> ennemis »).
- `Direct(dmg)` = valeur FIXE (min==max, PAS de spread), routee par percage/armure + crit/block du pipeline
  d'attaque (contexte-attaquant present, contrairement au DoT de tuile §6.2 qui n'a pas de crit). dmg = var 'dmg'.
- Le multi-tuile feu = BYPRODUIT : chaque coup Flame (trait OnFire) pose du feu sur la tuile de la cible splash ;
  + `Maybe(30%)` allume chaque hex adjacent VIDE (stochastique).
- Se declenche sur TOUTE attaque RANGED de l'unite (arme normale 4x Flame OU actif ArmoriumCherub).

**Actif `ArmoriumCherub` (1014, `ExecuteBehaviour @1811b4000`)** = 4x Flame ranged range 2 (minDmg/maxDmg[level],
nrOfHits=4). Attaque ranged => declenche AUSSI le passif (splash + ignite) = collateral.

**PORTE** :
- `_on_fire_damage_ability` cable dans `execute_ability_attack` (damage.py) : les attaques d'ABILITY posent enfin
  le feu (le vecteur after-hit n'etait cable que pour l'attaque normale) -> ferme le gap generique #136.
- `_fire_of_absolution_after_attack` (triggers.py) : gate passif (gameconfig passiveAbilities + ranged) ; splash
  `_adjacent_enemies_of` via execute_ability_attack (Direct = min==max=dmg) ; ignite `next_bool(30)` par voisin
  (RNG order flagge). Cable dans `after_hit_normal_attack` + `ArmoriumCherubAbility.execute_behaviour` (loki.py,
  registre 1014).

**VALIDATION LIVE (RID 8, seed 777)** :
- Attaque NORMALE : feu sur cible + 2 ennemis adjacents + 1 hex vide (30%), splash **1497** sur chaque adjacent =
  dmg 1996 x plancher percage 25% x3. Le port calcule 1996 -> 499/coup x3 = **1497 = BIT-EXACT**.
- Actif ArmoriumCherub : cast ok, MEME empreinte, splash **1872** sur les 2 adjacents (identiques = Direct).
  1872 = (1996 + ~500 crit-dmg ActOfFaith) x 25% x3 : le splash a CRIT -> confirme LIVE qu'**ActOfFaith (crit
  chance+dmg) s'applique a l'AoE** (ctx partage via `_crit_params`, 3 vecteurs). Le collateral de l'ACTIF est reel.

**GAPS** :
- **#138 RESOLU** : le reset ActOfFaith fire desormais AUSSI au crit d'une ability/splash. RE : `EvaluateAfterHitTriggers`
  @180e25fc0 est porte par `ADamageOperation` -> PARTAGE par l'attaque normale ET les attaques d'ability (dispatch
  `WasCrit`, branche `param_6 != 0` -> event 0x3d). Le port ne cablait le vecteur generique (`evaluate_trigger_operation`)
  que pour l'attaque normale ; `execute_ability_attack`/`execute_normal_like` appellent maintenant `after_hit_ability_attack`
  (triggers.py). VALIDE : moteur reset ActOfFaith au crit d'une ability (`test_act_of_faith_ability_reset_live` :
  accumulate-from-0 -> crit ability -> crit revient a la base) + `execute_ability_attack`/psyker-splash restent bit-exact
  (aucune regression, pas de recursion Psyker : `ranged=False` = guard). Reset per-CIBLE de splash = fidele (chaque cible
  = un `execute_ability_attack` distinct qui relit GetStat post-reset). Approximations restantes (#140) : reset AGREGE
  1x/sous-attaque (non per-coup, meme approx que le vecteur normal) ; vecteur COMPLET (Psyker) pour abilities exige d'abord
  le cap phase-triggers natif ; overwatch non couvert.
- **#139** : « ArmoriumCherub does not end Vindicta's turn » (turn-flow) NON porte offline (`execute_behaviour` ne
  gere aucune turn-flow ; flag CODE-DERIVED via `SetsEndTurnFlags` DSL, PAS config). No-op pour le replay-diff actuel.
- Ignite 30% + timing exact du passif vs coups primaires = RNG order non calibre bit-exact (flagge in-code).
