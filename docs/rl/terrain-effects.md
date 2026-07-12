# Terrain & power-up tile effects — RE map + port plan (workstream A+B)

Build `gqfc5mff6c`. Objectif : porter TOUS les effets de tuile (terrain + power-ups) qui touchent le
combat, en PREDICTION (oracle/damage view) ET dans le RUNNER offline (sim multi-tour). Origine : #113
(LightCover) etendu par l'utilisateur a l'ensemble terrain + power-ups.

## 0. Distinction structurante (mesuree live)

- **Prediction (etat courant)** : les effets de tuile sont DEJA captes — `decisionView.effects`
  (IsActive-filtered) porte `LightCover`/`Trench`/... ; `combatSnapshot.statDelta`/shields portent les
  boosts power-up + boucliers. => la prediction est correcte SAUF la ou le port IGNORE un effet capte.
- **Runner multi-step** : le runner materialise les effets UNE FOIS au build (snapshot) et ne modelise
  AUCUNE transition tuile (gagner/perdre un effet en entrant/sortant d'une tuile, ramasser un power-up,
  heal FirstAid, fire-spread). => gap analogue #123, mais generalise a toutes les mecaniques de tuile.

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
| `ThornsBlockMovementAbility` | 1811c8d70 | Thorns | bloque mvt | movement |
| `BrokenIceAbility` | 1811bed00 | BrokenIce | fall-through blocker | movement |

### LightCover (DryBush) — PORTE (prediction correcte)
`LightCoverEffect.CreateEffectHitsBonusForAttack @180f556b0` (decompile lu) :
`gate = AreEqual(Tiles(ctx@0x148=coverPatch), Tiles(ctx@0x178=targetTile)) & !IsMeleeAttack`
`bonus = ForAdditionWithMinimum(gate, Direct(-hitsReduction=GetNumberConstant(0x2c)), min=Direct(1))`.
Magnitude `globalValues.lightCoverHitReduction=2`. Autres : `IsUnitAffected @1811c1690`,
`UnitsThatNeedEffect @1811c1830`, `IsTallGrass @180ec6210`. Port : `engine/entities/effects/loki.py
LightCoverEffect` (via `hits_malus_from_defender_effects`). Le gate `AreEqual(coverPatch,target)` n'est
PAS porte (le port applique -2 des que l'effet est materialise) — OK en prediction (effet=IsActive=on-cover)
mais FAUX en runner-sim (effet perime apres move). Fix fidele = gate compute-time sur cover_hexes.

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
### DryBushFireSpread — a RE (1811bf5c0) : DoT quand DryBush prend feu (propagation).
### FirstAid — heal (`FirstAidHealAbility @1811c0490`, `FirstAidHealEffect` .ctor @180f44360,
CreateTargetSelector @180f3ca70, CreateTargetTrigger @180f44250) : heal les unites sur la tuile.
### Thorns/BrokenIce/Swamp — mouvement (Thorns @1811c8d70 ; BrokenIceBlockerEffect Apply @180f36c20 /
Revert @180f36e10 ; `SwampBlockMovement` desc @1809cdf10 ; `DSLFactory.WalkableAndBrokenIce @180e01e40`).

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
- B2. Power-up pickup on-move (APowerUpAbility -> stat boost / armor / shield / bomb).
- B3. FirstAid heal-on-tile (turn/step trigger).
- B4. Thorns/Swamp/BrokenIce : blocage mouvement (pathfinding).
- B5. DryBush fire-spread (DoT propagation).

Validation : chaque slice confronte offline vs live sur un board portant le terrain (cf. 1).
Prerequis live : warmup apres chaque (re)inject.
