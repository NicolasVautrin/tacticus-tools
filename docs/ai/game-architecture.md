# Game Architecture — WH40K Tacticus

## ECS (Entity-Component-System)

Le combat utilise un ECS. `MatchState._entities` (List<IEntity>) contient ~90 entites :

| Type | Classe | Count | Role |
|------|--------|-------|------|
| 0 | TileEntity | ~63 | Grille hex, position, contenu, walkability |
| 1 | UnitEntity | ~10 | Stats, HP, abilities, faction |
| 2 | MatchEntity | 1 | Board, turn state, active players |
| 4 | PlayerEntity | 2-3 | Humain (type=0), IA (type=1), Environment (type=2) |
| 5 | FootEntity | ~10 | Lien unite <-> tuile (1 par unite) |
| 6 | ? | 1 | |
| 7 | ? | 2 | |
| 8 | ? | variable | Effets, buffs, debuffs |

## Structure des entites

### UnitEntity (type 1)

Composants en proprietes directes (pas dans un tableau) :

| Composant | Champs cles |
|-----------|------------|
| `Owner` (OwnerComponent) | `PlayerEntityId` (3=humain, 4+=IA) |
| `Component` (UnitComponent) | `Id` (string), `Faction`, `Rank`, `Level`, `Power`, `QuestUnitId`, `VisualId` |
| `Health` (HealthComponent) | `RemainingValue`, `InitialValue`, `MaximumValue` |
| `Armor` (ArmorComponent) | `RemainingValue`, `InitialValue` |
| `Attack` (AttackComponent) | `InitialValue` |
| `Defense` (DefenseComponent) | `InitialValue` |
| `Movement` (MovementComponent) | `InitialValue` |
| `Range` (RangeComponent) | `InitialValue` |
| `CritChance`, `CritDamage` | `InitialValue` |
| `ActiveAbility` | `NormalAttackType` (enum int), `Abilities` |
| `TriggeredAbility` | `Abilities` (overwatch, etc.) |
| `Weapons` | armes equipees |
| `ActorStatistics` | damage dealt, kills, moves |

### TileEntity (type 0)

| Composant | Champs cles |
|-----------|------------|
| `Position` (PositionComponent) | `Coordinate.Column`, `Coordinate.Row`, `Coordinate.Layout` |
| `Component` (TileComponent) | `Id` ("Grass", "Unplayable"), `Elevation`, `SpawnPointPlayerId` |
| `Connectivity` | `NeighbourIds` (list[int]) |
| `Content` (TileContentComponent) | `ContentId` (0 = vide, >0 = unite entity id) |
| `TileMovement` | `WalkableType` (0=walkable, 2=unplayable) |
| `Owner` | `PlayerEntityId` |

### FootEntity (type 5) — lien unite <-> tuile

```json
{"Component": {"UnitId": 79, "TileId": 67}}
```

### PlayerEntity (type 4)

```json
{"Component": {"PlayerId": 11, "Name": "player", "Type": 0, "TeamId": 1}}
```
- `Type`: 0=humain, 1=IA, 2=environnement

### MatchEntity (type 2)

```json
{"Turn": {"_currentPlayerId": 3}, "Board": {"Height": 9, "Width": 7}}
```

## Grille hexagonale

- Coordonnees axiales offset (even-r) : Column + Row
- Board typique : 7 colonnes x 9 rangees
- Joueur en bas (row 0-2), IA en haut (rows 6-8)
- `NeighbourIds` sur chaque tile donne la topologie

## Operations (mutateurs du MatchState)

~150 Operations dans `BattleLogicAssembly/IdunBattle/Operations/`. Passent par `OperationProcessor`.

Principales :
- Combat : `AttackDamageOperation`, `DealDamageOperation`, `AbilityDamageOperation`
- Mouvement : `MoveUnitOperation`, `DisplaceUnitOperation`
- Abilities : `ActiveAbilityOperation`, `TriggerTriggeredAbilityOperation`
- Unites : `AddUnitOperation`, `KillUnitOperation`, `HealUnitOperation`
- Effets : `AddEffectOperation`, `RemoveEffectOperation`
- Tour : `ChangeTurnOperation`, `StartTurnOperation`, `EndTurnOperation`

## Systeme IA du jeu

- `PlaybookDatabase` : 432 playbooks
- `DefaultAiUnitTactic` : decide par unite
- `UtilityDefinition` avec buckets ponderes
- Stack : `Update -> RunComputerActionsForCurrentPlayerSequentially -> CalculateAndApplyAllComputerActions -> ApplyAiMessage -> Apply`

## Services du runner

Accessibles via les backing fields du runner :
- `<Pathfinders>k__BackingField` — pathfinding (FindReachableTiles, FindPath)
- `<DamagePrediction>k__BackingField` — prediction de degats
- `<TargetingQuery>k__BackingField` — ciblage (GetValidTargets, HasValidTargets)
- `_state` — MatchState courant

## Combats headless

Le moteur de combat (`IdunRunner`, `BattleLogicAssembly`) est 100% decouple de Unity — pas de MonoBehaviour, pas de rendering. Combats simulables en ~100ms.

### Pipeline capture → simulation

1. **Capturer** via `hooks/_oneshot/capture-battle-config.js`
   - Hook `IdunGameViews.Update` → `_runner` → `<Configuration>k__BackingField`
   - Serialise via `JsonConvert.SerializeObject` (Newtonsoft natif)
   - `readIl2cppString` limitee a 500 chars — le script utilise `_readIl2cppStringLarge` (2M)
   - Sortie : `data/arena-battle-config-newtonsoft.json` (525 KB)

2. **Deserialiser** via `hooks/_oneshot/run-headless-battle.js`
   - `JsonConvert.DeserializeObject(String, Type, JsonSerializerSettings)` — 3 args
   - Type obtenu via `il2cpp_type_get_object(il2cpp_class_get_type(bcClass))`

3. **Executer** via `AutomaticBattleRunner`
   - Voler `_logger` (0x50) et `_timeSource` (0x58) du runner actif
   - `.ctor(logger, config, maxTurns, false, false, timeSource)` puis `.Run()`
   - Retourne `AutomaticBattleResult` en ~100ms

### Notes

- `stop_previous` dans `/api/scripts/run` arrete auto les sessions precedentes
- Les configs PvP n'ont que les `PredefinedUnits` adverses, et **c'est la forme correcte** : la
  lineup du joueur n'entre JAMAIS dans ce canal, elle arrive par le déploiement (placeholders
  convertis au START). Pour simuler, la poser par le déploiement — jamais en l'écrivant dans
  `PredefinedUnits`, ce qui fabrique un état que le jeu ne produit pas.
