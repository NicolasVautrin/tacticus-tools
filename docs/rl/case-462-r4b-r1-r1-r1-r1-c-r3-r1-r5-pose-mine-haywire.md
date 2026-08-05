# #462-r4b-r1-r1-r1-r1-c-r3-r1-r5 -- la POSE de la mine Haywire

(EN COURS -- RE offline, la confrontation live attend la reouverture de la fenetre DRAIN.)

## 1. Les artefacts natifs, lus sur `rnca9r7q6c`

Slots de `DSLFactory` (`this+0x28`), lus verbatim au decompile :
`+0x78` = `DSLBehaviors`, `+0x80` = `DSLFormulas`, `+0x88` = `DSLTriggers`, `+0x90` = `DSLSelectors`.
`DSLSelectors+0x30` = le selecteur `Owner` ; `DSLTriggers+0x40` = le selecteur `Actor`.

### `HaywireMineAbility$$CreateTrigger` (1531)

```
  ( On(4 = UnitAfterMove) & OwnerIsActor & TriggeringAbilityIsNone )
| ( On(41 = UnitFinishedTurnNormally) & OwnerIsActor
    & AmountIsZero( GetPersistentData(AbilityOrEffect(self), Owner, <cle statique>) ) )
```

### `HaywireMineAbility$$CreateBehaviour`

```
tiles = Cache(
          If( AmountIsGreaterThanZero(PreviousTile(Owner)) & HasFlag(Owner, 0),
              CanAddUnit(PreviousTile(Owner), Actor),
              First(SortTilesByUtilityForSummon(Randomize(CanAddUnit(AdjacentTiles(Owner), Actor)),
                                                7, Owner), 1) ),
          1)
spawn = Spawn(Owner, tiles, GetStringConstant(8), WithStatsFromConfig(abilityState))
       & AddPersistentData(AbilityOrEffect(self), Owner, <cle statique>, DSLFormulas+0x20 = Direct(1))

triggerType == 32 (Custom)  ->  spawn
sinon                       ->  If( AmountIsGreaterThanZero(Count(tiles)),
                                    spawn,
                                    TriggerAbilityDelayed(Owner, 0x5fb, 3) )
```

### `HaywireMine_ResetAbility`

```
CreateTrigger   : On(40 = UnitFinishedTurn) & OwnerIsActor
CreateBehaviour : triggerType == 32 (Custom) -> Nothing()
                  sinon                      -> ClearPersistentData(AbilityOrEffect(self), Owner, <cle statique>)
```

## 2. Reste a etablir

* la valeur de la cle statique `DAT_1833596e8` et de `GetStringConstant(8)` ;
* le sens exact de `HasFlag(Owner, 0)` (`HasFlagAbilityTrigger$$ShouldTrigger`) ;
* l'ordre relatif de `On(40)` et `On(41)` dans `FinishUnitTurnOperation` ;
* `TriggerAbilityDelayedBehaviour$$Execute` (le re-essai delaye).
