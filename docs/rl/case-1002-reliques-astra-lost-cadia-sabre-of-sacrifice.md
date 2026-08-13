# Reliques ASTRA MILITARUM : `RelicOfLostCadia` (1459) et `SabreOfSacrifice` (1478)

Build de reference : `rnca9r7q6c`. Les deux abilities sont des `TriggeredAbilityType` de relique,
voie `item` — elles n'entrent NI dans `ABILITY_CLASSES`, NI dans `TARGETING_OPTIONS`, NI dans
`ABILITY_ATTACK_TYPE`. Canal etabli au decompile : `$$CreateTrigger` + `$$CreateBehaviour` sur les
deux ⇒ `RELIC_ABILITY_TRIGGERS`.

## 1. `RelicOfLostCadia` 1459 — DEUX classes natives

Porteurs (pool rank 17) : `astraBullgryn`, `astraOrdnance`, `astraPrimarisPsy`.
i2 : « Friendly surrounding Imperial Summons have Final Vengeance. When the relic bearer is
defeated, summons a Cadian Guardsman in its hex with 5817 Health, 3492 Damage and 1166 Armour. »

### 1.a `RelicOfLostCadiaAbility` — la pose de l'effet

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RelicOfLostCadiaAbility$$CreateTrigger` :

```
  On(0x4  = UnitAfterMove,        ownerNeedsToBeAlive: 1)
| ( On(0x32 = UnitAdded,          ownerNeedsToBeAlive: 1) & IsAlive(Actor@DSLSelectors+0x40) )
| On(0x3b = UnitBecameTargetable, ownerNeedsToBeAlive: 1)
| On(0x2d = UnitRevived,          ownerNeedsToBeAlive: 1)
| OnOwnerSpecificAbilityInit(this.AbilityType = 0x5b3 = 1459)
```

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RelicOfLostCadiaAbility$$CreateBehaviour` :

```
If( get_OwnerIsCaster,
    AddEffect( 0x5ae = 1454 EffectType.FinalVengeance_UnitEffect,
               AbilityStateReference,
               source  = Owner@DSLSelectors+0x30,
               targets = IsImperialAndSummon( SurroundingFriends(
                             unit  = Owner@DSLSelectors+0x30,
                             range = <DSLFormulas+0x20> = Direct(1),
                             unique: 1, unitSelectionType: 3) ),
               options = default(Nullable<AddEffectBehaviourOptions>) ),
    If( AreFriends(Owner@+0x30, Caster@+0x48, comparisonType: 0, anyEntity: 0)
        op_BitwiseAnd IsInRange(Owner@+0x30, Caster@+0x48, range = <DSLFormulas+0x20> = Direct(1)),
        AddEffect( 0x5ae, AbilityStateReference, source = Owner@+0x30,
                   targets = IsImperialAndSummon(Caster@+0x48), options = default ),
        null ) )
```

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RelicOfLostCadiaAbility$$IsImperialAndSummon`
= `UnitsWithTraits(targets, [0x1a = 26 Imperial, 0x2 = 2 Summon], selectionType: 3)`.

### 1.b `RelicOfLostCadiaAbility_SummonUnit` — le spawn a la mort

```
CreateTrigger   = On(0x0 = UnitDeath, ownerNeedsToBeAlive: 0) & get_OwnerIsTarget
CreateBehaviour = Spawn( parentSelector = Owner@DSLSelectors+0x30,
                         tiles = PickRandomly( FreeTilesOrAdjacentFreeTiles( Tiles(Target@+0x60) ),
                                               amount: 1, allowDuplicates: 0,
                                               maxDuplicatesAllowed: 0x7fffffff,
                                               ignoreForcedTargets: 0 ),
                         spawnUnitId = Config.GetStringConstant(0x0),
                         options = SpawnUnitOptions.WithStatsFromConfig(Config, abilityState,
                                                                        null, null) )
```

## 2. `SabreOfSacrifice` 1478 — UNE classe native

Porteur (pool rank 17) : `astraDreir`.
i2 : « When Dreir or Death Riders adjacent to Dreir are charging, their attacks Suppress their
targets for 1 round. After charging and until the start of their next turn, they additionally have
+1018 Armour for each friendly unit that has been defeated this battle. »

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SabreOfSacrificeAbility$$CreateTrigger` :

```
On(0x9 = Attack, ownerNeedsToBeAlive: 1)
  op_BitwiseAnd IsCharging(Caster@DSLSelectors+0x48, Target@DSLSelectors+0x60)
  op_BitwiseAnd ( get_OwnerIsCaster
                  op_BitwiseOr ( AreEqual(Parent(Caster@+0x48, root: 0), Owner@+0x30)
                                 op_BitwiseAnd IsUnitWithVisualId(Caster@+0x48,
                                                                  Config.GetStringConstant(0x0))
                                 op_BitwiseAnd IsAdjacent(Owner@+0x30, Caster@+0x48,
                                                          selectionType: 3) ) )
```

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SabreOfSacrificeAbility$$CreateBehaviour` :

```
  AddEffect( 0x429 = 1065 EffectType.Pinned, AbilityStateReference,
             source = Owner@+0x30, targets = Target@+0x60,
             options = default(Nullable<AddEffectBehaviourOptions>) )
op_BitwiseAnd
  AddStaticStatModifierEffect( targets = Caster@+0x48,
                               effectType = 0x5c1 = 1473 SabreOfSacrifice_ExtraArmor,
                               statType   = 0x10 = 16 StatType.FixedArmor,
                               amount     = GetCurrentExtraArmor(abilityState),
                               turns      = TurnsFromRounds(<DSLFormulas+0x20> = Direct(1)),
                               isHidden   = 0 )
```

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SabreOfSacrificeAbility$$GetCurrentExtraArmor` :

```
Multiply( Count( Filter( AllUnits(),
                           AreFriends(Owner@+0x30, It@+0x68, comparisonType: 0, anyEntity: 0)
                           op_BitwiseAnd HasBeenDefeated(It@+0x68)
                           op_BitwiseAnd IsNormalUnit(It@+0x68) ) ),
          Get( Config.GetVariableForLevel(0x1b = 27 extraArmor, abilityState, null) ) )
```

## 3. Etat de la tranche

RE faite. Port et confrontation live en cours.
