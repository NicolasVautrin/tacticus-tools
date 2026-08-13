# #1032 -- `1193 NovaCharge` et `1052 CallRipperSwarms` : deux no-op silencieux fermes

Numero **#1032** alloue par `probe_468_collision_numeros.py --suggere` (reservation exclusive dans
le `.git` commun).

Les deux actives etaient ABSENTES d'`ABILITY_CLASSES` : `ported:False`, 0 degat, 0 effet, aucune
erreur -- la DECISION pouvait les choisir pendant que l'EXECUTION les ignorait.

## 1. Ce que le natif fait, etage par etage

### 1.1 `1193 NovaCharge` (`tauBossRiptide`, NPC boss) -- MARQUAGE, pas attaque

`IdunBattleLogic.Entities.Abilities.Active.Loki.NovaChargeAbility$$ExecuteBehaviour` -- les trois
feuilles, dans l'ordre des deux `IdunBattle.DSL.AbilityBehaviour$$op_BitwiseAnd` :

```
lineTiles = Cache( NovaChargeAbility$$GetLineTiles(), matchAbilityEntities: true )
marked    = NovaChargeAbility$$GetAdditionalMarkedTiles(lineTiles)

pending = DSLBehaviors.AddBondEffect( 0x583 = 1411 NovaCharge_PendingAttack,
                                      AbilityStateReference,
                                      source       = Caster@DSLSelectors+0x48,
                                      targets      = Caster@+0x48,
                                      bondedEntity = Owner@+0x30,
                                      options      = <struct 0x20 octets ZERO> )
markLine = DSLBehaviors.AddEffect( 0x584 = 1412 NovaCharge_PendingTarget_Line,
                                   AbilityStateReference, source = Caster@+0x48,
                                   targets = lineTiles, <options ZERO> )      # surcharge 6-args
markOne  = DSLBehaviors.AddEffect( 0x585 = 1413 NovaCharge_PendingTarget_Single,
                                   AbilityStateReference, source = Caster@+0x48,
                                   targets = marked,    <options ZERO> )      # surcharge 6-args
Execute( (pending & markLine) & markOne )
```

Le degat vient de la PHASE 2 (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.
NovaCharge_AttackAbility$$CreateBehaviour`, `TriggeredAbilityType` 1324), HORS de ce port --
exactement comme `NovaShield` 1194 / `NovaBoost` 1192 (cf. `runner/abilities/tau.py`).

`NovaChargeAbility$$GetLineTiles` (MIRROR) -- trois lignes paralleles issues du caster :

```
center = CenterTiles(CasterTile@DSLSelectors+0x58)
dir    = DSLFormulas.DirectionTo(center, Target@+0x60)               # IVectorFormula
next1  = NextTileInLine(center, dir)
cw     = NextTileClockwise(fromTile = Target@+0x60, aroundTile = center)
dir2   = DSLFormulas.DirectionTo(next1, cw)
next2  = NextTileInLine(cw, dir2)
s      = <TilesBehindInLineSettings : +0x10 = 0, +0x11 = 0>
lines  = ( Target@+0x60 + TilesBehindInLine(Target@+0x60, dir, s, maxAmount: null) )
       + ( cw           + TilesBehindInLine(cw,           dir, s, maxAmount: null) )
       + ( next2        + TilesBehindInLine(next2,        dir, s, maxAmount: null) )
return Filter( lines - CasterTile@+0x58, op_LogicalNot(DSLTriggers.IsTrenchTile(ActiveTarget@+0x68)) )
```

`NovaChargeAbility$$GetAdditionalMarkedTiles(lineTiles)` (MIRROR) :

```
n      = DSLFormulas.ConfigConst(0x11 = nrOfTargets, config@this+0x60)
rest   = Randomize( Filter( (AllTiles@+0x18 - lineTiles) - CasterTile@+0x58,
                            op_LogicalNot(IsTrenchTile(ActiveTarget@+0x68)) ) )
enemies = Enemies( Owner@+0x30, rest, UnitSelectionType 3 )
prio    = Tiles( NormalUnits(enemies, 3) )  +  Tiles(enemies)
        + ( rest & SurroundingTiles( TilesWithEnemies(Owner@+0x30),
                                     includeCenter: true, range: 2, onlyMovable: false ) )
return First( Unique(prio) & rest, amount = n, ignoreForcedTargets: false )
```

### 1.2 `1052 CallRipperSwarms` (`tyranBossHiveTyrantLeviathan`, NPC boss) -- SUMMON EN ATTENTE

`IdunBattleLogic.Entities.Abilities.Active.Loki.CallRipperSwarmsAbility$$ExecuteBehaviour`
(MIRROR 1:1, UNE seule feuille) :

```
n       = AbilityConfiguration.GetNumberConstant(config@this+0x60, 0x10 = nrOfSummons)
enemies = Enemies( Caster@DSLSelectors+0x48, AllAliveUnits@+0x20, UnitSelectionType 3 )
tiles   = First( SortByFormula( CanAddUnit(AllTiles@+0x18),
                                DSLFormulas.AverageDistance(ActiveTarget@+0x68, enemies),
                                ascending: false ),
                 amount = n, ignoreForcedTargets: false )
return Execute( DSLBehaviors.AddBondEffect( 0x446 = 1094 CallRipperSwarms_PendingSummon,
                                            AbilityStateReference,
                                            source       = Caster@+0x48,
                                            targets      = tiles,
                                            bondedEntity = Caster@+0x48,
                                            options      = <struct 0x20 octets ZERO> ) )
```

Le SPAWN reel vit dans `IdunBattle.Entities.Effects.Loki.CallRipperSwarms_PendingSummonEffect`
(deux `DSLFactory.Triggered` : `On(0x15) & IsTurnOf(bonded)` et `On(0x1f) & OwnerIsTargetTile`,
tous deux `-> TriggerAbility(CallRipperSwarms_Spawn*) & GetRemoveEffectBehaviour()`) puis dans
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.CallRipperSwarms_SpawnAbility$$CreateBehaviour`
(`Spawn(..., WithStatsFromConfig, onAppearance = PerformAIAttack(...))`). PHASE 2, HORS de ce port
-- meme decoupe que `TunnelingHorror` 1011 (`runner/abilities/necrons.py`).

## 2. Les deux donnees obligatoires du registre, LUES au decompile

| | `TARGETING_OPTIONS` | `ABILITY_ATTACK_TYPE` |
|---|---|---|
| `1193 NovaCharge` | forme **FLAGS DIRECTS** : `TargetingOptions..ctor(&opts, isSelfCasting: 0, range: TargetingRange.CustomRange(...), forceMeleeTarget: 1, rules: **0x2000000042**, 0, 0)` | `AActiveAbility..ctor(this, &opts, **2**)` = `AbilityAttackType.Others` |
| `1052 CallRipperSwarms` | forme **PRESET STATIQUE COPIE** : aucun `TargetingOptions..ctor` ; recopie des 0x40 octets de `<TargetingOptions statics>+0x280`. `IdunBattle.Core.Services.TargetingOptions$$.cctor` y ecrit `+0x00 = 1` (isSelfCasting), `+0x08` <- `<TargetingRange statics>+0x60`, `+0x20 = 1` (forceMeleeTarget = RangedBool.False), `+0x28 = **0x8004**` | `AActiveAbility..ctor(this, &opts, **2**)` = `AbilityAttackType.Others` |

Decomposition EXHAUSTIVE des masques (aucun bit residuel) :

* `0x2000000042` = `1 << 1` `TargetMatchesDynamicRule` + `1 << 6` `TargetIsTile` + `1 << 37`
  `CasterHas7Tiles` -- ce dernier est la signature du boss `tauBossRiptide`, une unite a 7 tuiles.
* `0x8004` = `1 << 2` `CasterMatchesDynamicRule` + `1 << 15` `CasterIsPossibleTarget`. Le preset
  `<statics>+0x280` est le MEME que celui d'`ExemplarOfTheMontkaAbility` (`runner/abilities/tau.py`,
  masque identique deja LU par une autre tranche) -- confirmation croisee, deux lectures
  independantes du meme bloc du `.cctor`.

## 3. Vocabulaire DSL neuf pose par cette tranche

| Noeud | Mirror natif | Fichier |
|---|---|---|
| `PickFirstN` | `IdunBattle.Entities.Selectors.PickFirstNSelector$$Select` (= `DSLSelectors$$First(entities, amount, ignoreForcedTargets)`) | `entities/selectors/units.py` |
| `AverageDistance` | `IdunBattleLogic.Entities.DSLFormulas$$AverageDistance` -> `AverageDistanceFormula$$Calculate` -> `BattleQuery$$GetAverageDistance` | `entities/selectors/geometry.py` |
| `TilesWithEnemies` | `IdunBattleLogic.Entities.DSLSelectors$$TilesWithEnemies` (= `Tiles(Enemies(of, AllAliveUnits, 3))`) | `entities/selectors/units.py` |
| `CenterTiles` | `IdunBattleLogic.Entities.DSLSelectors$$CenterTiles` -> `CenterTilesSelector$$Select` -> `IBattleQuery` slot 93 `BattleQuery$$GetCenterTiles` | `entities/selectors/geometry.py` |
| `NextTileInLine` | `IdunBattleLogic.Entities.DSLSelectors$$NextTileInLine` (= `TilesBehindInLineSelector` variante `IVectorFormula`, `maxAmount = DSLFormulas+0x20`) | `entities/selectors/geometry.py` |
| `NextTileClockwise` | `IdunBattleLogic.Entities.DSLSelectors$$NextTileClockwise` -> `NextTileInCircleSelector$$Select` | `entities/selectors/geometry.py` |

(Etat de la fiche en cours de tranche -- les sections VALIDATION et RESIDUS sont ecrites en fin
de tranche, quand les mesures existent.)
