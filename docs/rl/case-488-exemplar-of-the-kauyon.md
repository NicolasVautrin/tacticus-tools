# #488 -- `1087 ExemplarOfTheKauyon` : le port d'un TELEPORT-PUIS-ATTAQUE

Porteur lineup : `tauShadowsun` (Commander Shadowsun, HERO, rank 17, dans le pool).
Porteurs npc : `tauBossShadowsun`, `tauBossShadowsunInc`, `tauBossShadowsunLHE`, `tauNpcShadowsun`.

Etat avant : **NO-OP SILENCIEUX** -- absente d'`ABILITY_CLASSES`, donc la decision choisit le cast
et l'execution l'ignore (0 degat, 0 effet, 0 erreur).

## 1. Ce que le natif ECRIT

`IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfTheKauyonAbility$$ExecuteBehaviour`,
lu noeud par noeud (offsets de `IdunBattleLogic.Entities.DSLSelectors`, convention deja etablie
dans le port : `caster@0x48`, `target@0x60`, `Subject@0x68`, `AllTiles@0x18`) :

```
teleport = DSLBehaviors.Teleport( caster@0x48, target@0x60 )
aiAttack = DSLBehaviors.PerformAIAttackFromCurrentPosition( target@0x60, null, null, false )
exTile   = DSLSelectors.Entity( entities+0x40 )              # tuile du caster CAPTUREE au cast
unitId   = AbilityConfiguration.GetStringConstant( 0 )       # "unitId" -> tauSmnDroneCommandLink
opts     = SpawnUnitOptions.WithStatsFromConfig( config, abilityState, null, null )
opts.onAppearance = DSLBehaviors.AddTrait( Subject@0x68, 0x418, null )   # UnitTrait.Stationary
tileSel  = First( CanAddUnit( exTile + SortByDistance( Randomize( AllTiles@0x18 ), exTile ) ), 1 )
spawn    = DSLBehaviors.Spawn( caster@0x48, tileSel, unitId, opts )
addEff   = DSLBehaviors.AddEffect( 0x49d, abilityStateRef, caster@0x48, caster@0x48, default )
remEff   = DSLBehaviors.RemoveEffect( caster@0x48, (int?)0x49d, null )
tree     = teleport & If( triggers@0x20, addEff & aiAttack & remEff ) & spawn
AActiveAbility.Execute( entities, this, tree )
```

`0x49d` = `EffectType.ExemplarOfTheKauyon_AdditionalHits` (1181), `0x418` = `UnitTrait.Stationary`
(1048).

## 2. Ciblage

`ExemplarOfTheKauyonAbility$$.ctor` :
`TargetingOptions..ctor(&opts, isSelfCasting=0, range=&<TargetingRange statics+0x48>,
forceMeleeTarget=1, rules=0x6001042, null, null)` puis `AActiveAbility..ctor(this, &opts, 2)`.

-> `ABILITY_ATTACK_TYPE` = **2** (`AbilityAttackType.Others`), litteral lu au ctor.

(en cours de redaction)
