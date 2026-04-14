# RPC API

## Endpoint

`POST /api/scripts/{run_session_id}/rpc`

```json
{"method": "string", "args": {}, "timeout": 10.0}
```

## Methodes

### get_state

Retourne le MatchState serialise brut. Taille ~185KB a depth 6.

```bash
curl -s -X POST http://127.0.0.1:8765/api/scripts/{N}/rpc \
  -H "Content-Type: application/json" \
  -d '{"method":"get_state","args":{"depth":6}}'
```

### play (bloquant)

Execute une action, attend `isPlayerTurn()`, retourne le nouveau state + `_events`.

Actions disponibles :
- `end_turn` — fin de tour (attend la fin du tour IA)
- `ability` — `casterId`, `targetId`, `abilityType`
- `move` — `unitId`, `positions: [{col, row}]`

```bash
# Move
curl -s -X POST http://127.0.0.1:8765/api/scripts/{N}/rpc \
  -d '{"method":"play","args":{"action":"move","unitId":63,"positions":[{"col":3,"row":4}]}}'

# Ability
curl -s -X POST http://127.0.0.1:8765/api/scripts/{N}/rpc \
  -d '{"method":"play","args":{"action":"ability","casterId":63,"targetId":79,"abilityType":0}}'

# End turn (timeout long pour attendre l'IA)
curl -s -X POST http://127.0.0.1:8765/api/scripts/{N}/rpc \
  -d '{"method":"play","args":{"action":"end_turn"},"timeout":60}'
```

### get_reachable_tiles

Appelle `Pathfinders.FindReachableTiles()` du jeu. Retourne les IDs des tiles atteignables.

```bash
curl -s -X POST http://127.0.0.1:8765/api/scripts/{N}/rpc \
  -d '{"method":"get_reachable_tiles","args":{"unitId":63}}'
```

Reponse : `{"unitId": 63, "depth": 4, "tileIds": [25, 33, 42, ...], "count": 11}`

### get_damage_prediction

Non implemente (necessite construction de `UnitPosition`).

## Pipeline RPC

```
Client -> POST /rpc -> backend -> script.post({type:"rpc",...})
  -> recv("rpc") -> pendingRpc queue -> Update hook (main thread) -> execute
  -> send({t:"rpc_response",...}) -> backend resolve Future -> HTTP response
```

Pour `play`, le flow est different :
```
recv("rpc") -> pendingPlay = {id, args} -> Update hook execute l'action
  -> attend isPlayerTurn() sur les frames suivants
  -> send({t:"rpc_response", result: state + _events})
```

## Format des events (_events)

Le champ `_events` dans la reponse `play` contient les events captures pendant l'execution :

### Stream events (enums resolus par le backend)
```json
{"step": {"_enum": "IdunBattle.Streams.StepType", "_value": 3, "_name": "ChangePosition"}, "entity": 90, "tags": {"Unit_Foot_Tile_Id_1": 30, "Is_Last_Tile": 1}}
{"step": {"_enum": "IdunBattle.Streams.StepType", "_value": 4, "_name": "UnitDamaged"}, "entity": 90, "tags": {...}}
```

### Stream group events
```json
{"group": {"_enum": "IdunBattle.Streams.GroupType", "_value": 11, "_name": "User_MoveUnit"}, "entity": 90, "source": null}
{"group": {"_enum": "IdunBattle.Streams.GroupType", "_value": 21}, "entity": 81, "source": "HatefulAssault"}
```

Note : les events ne contiennent que les stream events du jeu (StreamDispatcher). Les Apply messages (nos propres actions) ne sont pas inclus dans `_events`.

### Validation failures
```json
{"_validation": "TilesAreWalkable", "passed": false}
```

## Python helpers (lib/)

`C:/Users/nicolasv/frida-ide-workdir/tacticus/lib/`

```python
from lib.rpc import RpcClient
from lib.state import GameState
from lib.hex import hex_distance

client = RpcClient(session_id=90)
state = client.get_state()

# Units
for u in state.player_units:
    print(u.name, u.hp, u.pos)

# Reachable tiles
tiles = client.get_reachable_tiles(u.id)

# Units (enrichis)
for u in state.player_units:
    print(u.name, u.hp, u.pos, u.normal_attack_type, u.has_attacked)

# Actions
state = client.move(unit_id=63, col=3, row=4)
state = client.attack(caster_id=63, target_id=79, ability_type=u.normal_attack_type)  # ability_type obligatoire
state = client.end_turn()

# Events de la derniere action
for ev in state.events:
    print(ev)

# Hex math
dist = hex_distance((0, 1), (3, 5))
neighbors = hex_neighbors(3, 5)
```
