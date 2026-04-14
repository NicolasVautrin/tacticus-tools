# Frida Hooks — Modules & Conventions

## Workdir

`C:/Users/nicolasv/tacticus-tools/hooks/`

## Modules

### _utils/ (bibliotheque partagee)

| Module | Provides |
|--------|----------|
| `il2cpp-helpers.js` | `il2cpp`, `s()`, `findClass()`, `findMethod()`, `hook()`, `getStack()`, `getFieldOffset()`, `readIl2cppString()`, `readMsgDetails()` |
| `il2cpp-invoke.js` | `il2cpp_object_new()`, `il2cpp_runtime_invoke()`, `invokeMethod()`, `createObject()` |
| `il2cpp-serializer.js` | `serialize(objPtr, depth)` — generique IL2CPP -> JSON |
| `matchstate-reader.js` | `runnerInstance`, `isPlayerTurn()`, `getSerializedState()`, `getEntityById()`, `getUnitTile()`, `queryReachableTiles()`, `queryDamagePrediction()` |

### autoplay/ (composition pour l'auto-play)

| Module | Role |
|--------|------|
| `message-factory.js` | `createMessage(cmd)`, `createEndTurnMessage()`, `createAbilityMessage()`, `createMoveMessage()` |
| `action-queue.js` | **Interceptor.replace** sur `IdunGameViews.Update`. RPC dispatch, play bloquant, runner capture depuis `GameViews._runner`. Provides: `pendingActions`, `pendingRpc`, `pendingPlay`, `events` |
| `turn-observer.js` | Hooks Apply, ApplyAiMessage, StreamDispatcher (Action, StartGroup). Validation failure hooks sur MoveUnitOperation. Pousse dans `events`. |
| `input-capture.js` | Hook `UnitSelectionFsm.HandleMouseButtonUpThisFrame`. Serialize entity+tile depth 4 sur chaque tap. |
| `recv-handler.js` | `recv("action")`, `recv("rpc")`, `recv("cleanup")`. Bridge entre backend et script queues. |

### Autres (standalone, pas composes avec autoplay)

| Module | Role |
|--------|------|
| `battle/all-actions.js` | Hook `IdunRunner.Apply` — toutes les actions |
| `battle/player-input.js` | Hook `StateMachineActions.ApplyInput` + stack |
| `battle/battle-end.js` | Hook `ShowPvpBattleEndCommand.Execute` |
| `ai/ai-decisions.js` | Hook `DefaultAiUnitTactic.CalculateNextActionForUnit` |
| `ai/ai-turn.js` | Hook `AiControl.RunComputerActionsForPlayer` |
| `ai/ai-services.js` | Observer AttackQuery, DamagePredictionQuery, TargetingQuery. Composable avec autoplay. |
| `_oneshot/dump-symbols.js` | Dump methodes + enums -> symbols.json |
| `_oneshot/dump-abilities.js` | Dump AbilitiesDatabase configs. Requiert _utils/ + matchstate-reader. En combat. |

## Composition (autoplay)

Ordre strict — chaque module depend des precedents :

```bash
cat _utils/il2cpp-helpers.js \
    _utils/il2cpp-invoke.js \
    _utils/il2cpp-serializer.js \
    _utils/matchstate-reader.js \
    autoplay/message-factory.js \
    autoplay/action-queue.js \
    autoplay/turn-observer.js \
    autoplay/input-capture.js \
    autoplay/recv-handler.js \
    > composed.js
```

## Injection

Le payload est trop gros pour curl (~48K). Ecrire le JSON dans un fichier avec `node -e`, puis `curl -d @fichier`. Toujours passer `log_dir` sinon les logs vont dans `logs/`.

## Conventions

Header metadata :
```javascript
// hook: Description courte
// requires: _utils/il2cpp-helpers, _utils/il2cpp-invoke
// provides: functionName(), variableName
```

- try-catch obligatoire dans les callbacks onEnter/onLeave
- `getStack()` retourne des offsets int bruts (resolus cote backend via symbols.json)

## Interceptor.replace vs attach

`action-queue.js` utilise **Interceptor.replace** sur `IdunGameViews.Update` (pas attach). Raison : Frida supprime les hooks imbriques sur le meme thread (same-thread suppression). Les hooks attach sur `StreamDispatcher`, `MoveUnitOperation` etc. ne se declenchent pas quand ils sont appeles depuis un callback attach sur Update.

Avec replace, le code est traite comme la fonction native elle-meme, pas un callback, donc les hooks imbriques fonctionnent.

## Graceful cleanup (reinjectoin)

Le backend envoie `{type: "cleanup"}` avant `script.unload()`. Le script repond `{t: "cleanup_done"}`. Le backend attend la confirmation + sleep 50ms, puis unload. Ceci evite de crasher le jeu en detachant le replace pendant un frame Update.

`recv-handler.js` contient le handler cleanup.

## Ce qui crashe

- `DebugSymbol.fromAddress()` : crash immediat.
- `NullBattleAILogger.AddSelectedAction` : methode trop petite, attach echoue (fail gracieux avec try-catch).
- Stop manuel d'une session avec Interceptor.replace actif : crash. Toujours utiliser la reinjectoin (le backend cleanup proprement).
