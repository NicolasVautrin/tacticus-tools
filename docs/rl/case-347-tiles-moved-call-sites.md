# case-347 — les 4 call-sites natifs de `RecordTilesMoved`

Résidu `#335-r1`. #335/#340 avaient porté 1 call-site sur 4 (`MoveUnitOperation$$Execute`).
Ce cas traite les 3 autres.

## 1. Le recensement, lu au décompilé (`rnca9r7q6c`)

`list_xrefs` sur `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved` — **4 appelants**, dont
2 dans le même `MoveUnitOperation$$Execute` (branche SIMULATION et branche RÉELLE) :

| appelant | quantité enregistrée | déjà porté ? |
|---|---|---|
| `IdunBattle.Operations.MoveUnitOperation$$Execute` (×2) | `BattleQuery.GetNumTilesMoved(connectedPath)` = **longueur de CHEMIN** | #335 |
| `IdunBattle.Operations.DisplaceUnitOperation$$AddTilesMoved` | `BattleQuery.GetDistance(previousTiles, [dest])` = **distance HEX** | ce cas |
| `IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition` | `BattleQuery.GetDistance(tileAvant, tileApres)` = **distance HEX** | ce cas |

**Le fait qui structure tout** : les 2 call-sites manquants comptent en **distance hexagonale**,
pas en longueur de chemin. `BattleQuery$$GetDistance` (les 4 surcharges) délègue au slot d'interface
9/10/0xb de `IdunBattle.Core.Services.MovementQuery$$GetDistance`, dont le corps est
`min over (a,b) of CubeCoordinate.Distance(a, b)` — aucun pathfinding, aucun contournement
d'obstacle. Le discriminant « hex 3 → 4 tuiles de chemin » de #335 **ne s'applique donc pas** à ces
deux-là : c'est l'inverse qui est vrai, un port qui y compterait en chemin serait faux.

## 2. `AddTilesMoved` — le gate qui l'éteint presque partout

```csharp
// IdunBattle.Operations.DisplaceUnitOperation$$AddTilesMoved
if (options.recordTilesMoved /* +0x10 */) {
    if (!UnitExtensions.IsEnemy(caster, target, state)) {
        n = battleQuery.GetDistance(previousTiles, TExtensions.ToList(tileToDisplace));
        UnitExtensions.RecordTilesMoved(target, n, state);
    }
}
```

`options+0x10` est recopié depuis `DisplaceUnitBehaviourOptions+0x1c` par
`IdunBattle.Entities.Behaviours.DisplaceUnitBehaviour$$Execute`. Balayage **exhaustif** des 8
constructeurs de `DisplaceUnitBehaviour` (xrefs de son `.ctor`) :

| feuille DSL | `DisplaceDirection` | `+0x1c` = enregistre |
|---|---|---|
| `DSLBehaviors$$PushUnit` | 0 Push | **non** |
| `DSLBehaviors$$PushAwayFromBlacklistTiles` | 1 | **non** |
| `DSLBehaviors$$PushToPrioritizedTiles` | 2 | **non** |
| `DSLBehaviors$$DisplaceUnitInAdjacentDirection` | 3 AdjacentVector | **non** |
| `DSLBehaviors$$DisplaceUnit` | 4 Direct | **non** |
| `DSLBehaviors$$SwitchPosition` | 5 SwitchPosition | **OUI** |
| `DSLBehaviors$$PullUnitOneTile` | 6 | **non** |
| `DSLBehaviors$$Teleport` | 4 Direct | **OUI** |

⇒ **le PUSH ne compte rien** : `record_tiles=False` posé par #335 sur le `MoveUnitOperation` du
push est exact, et il n'y a rien à ajouter côté push. Le piège du double comptage annoncé n'existe
pas dans ce sens-là — mais l'inverse (porter `AddTilesMoved` sans son gate) l'aurait créé.

## 3. Les deux moitiés de `SwitchPosition` ne sont PAS symétriques

`IdunBattle.Operations.DisplaceUnitOperation$$SwitchPosition` appelle `AddTilesMoved` deux fois :

```csharp
if (!deadTarget) { MoveUnit(target -> tileCaster); AddTilesMoved(caster, target, [tileTarget], tileCaster, options); }
if (!deadCaster) { MoveUnit(caster -> tileTarget); AddTilesMoved(caster, caster,  [tileCaster], tileTarget, options); }
```

Le second passe `target = caster` : `IsEnemy(caster, caster)` est **toujours faux**, donc
**le caster enregistre TOUJOURS** sa distance. La cible, elle, n'enregistre que si elle est
**amie** du caster. Sur le seul call-site porté (`SorcerousFacade_SwitchAbility`, qui switche avec
un ennemi), le compteur bouge donc pour le caster seul.

