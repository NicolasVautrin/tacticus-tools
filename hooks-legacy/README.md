# hooks-legacy — ancien répertoire de hooks Frida

Cette arborescence est **legacy**. La codebase active est maintenant `frida/` (TypeScript + `frida-compile`).

## Ce qui reste utilisé (one-shots autonomes)

Scripts injectés ponctuellement via shell, toujours fonctionnels :

- `_oneshot/dump-symbols.js`, `dump-il2cpp-full.js`, `dump-abilities.js`,
  `dump-enum-attrs.js`, `dump-gameconfig.js`, `capture-battle-config.js` —
  producteurs des `data/*.json` utilisés partout (symbols.json, abilities, enums)
- `_oneshot/enable-debug-menu.js` — tentative d'activation des cheat menus
- `_oneshot/resolve-symbols.js` — résolution offsets → noms
- `_oneshot/probe-*.js` — probes ponctuelles (attrs, assemblies, class flags)
- `_oneshot/trace-battleconfig-ctor.js` — trace instanciation BattleConfiguration
- `_oneshot/run-headless-battle.js` — battle headless exploratoire
- `_oneshot/scan-ptr-dat.js`, `inspect-ptr-dat.js` — investigation pointer data
- `autoplay/pick-next-observer.js`, `pick-next-movenext-observer.js`,
  `pick-next-force-order.js` — **à porter dans `frida/`** quand on fera le
  tree exploration (hook `DefaultGroupOperator.PickNextUnit`)
- `ai/ai-services.js`, `ai/ai-decisions.js` — probes AttackQuery / Targeting /
  DamagePrediction / DefaultAiUnitTactic
- `battle/battle-end.js` — detector `ShowPvpBattleEndCommand`

## Ce qui est obsolete (gardé en git pour historique, non référencé)

Remplacé par `frida/hooks/` :

- `autoplay/full-recorder.js` — porté dans `frida/hooks/` (distribué en
  `il2cpp/`, `game/`, `features/`, `runtime/`)
- `_utils/il2cpp-helpers.js`, `il2cpp-invoke.js`, `il2cpp-serializer.js`,
  `il2cpp-gc-root.js`, `matchstate-reader.js` — portés en TS
- `autoplay/replay-sim.js` — approche `ReplayRunner` abandonnée (crashe
  access violation 0x4 sur 2ème build)
- `autoplay/simulate-turn.js` — swap `runner._state` abandonné (67 services
  gardent leur propre ref `_state`, swap ignoré)
- `autoplay/ai-plays-me.js` — absorbé par `cheatRunAi` + `simAndCommit`
- `autoplay/player-turn.js` — driver auto-play obsolete
- `autoplay/action-queue.js`, `turn-observer.js`, `input-capture.js`,
  `message-factory.js`, `recv-handler.js` — infra ancien pattern
- `battle/all-actions.js`, `battle/player-input.js` — redondants
- `ai/ai-turn.js` — trivial, couvert par `recorder.ts`
- `_test/*` — tests manuels historiques

## Injection d'un one-shot legacy

```bash
PID=$(adb -s f32224e7 shell "ps -A | grep -i tacticus" | awk '{print $2}')
cat hooks-legacy/_utils/il2cpp-helpers.js \
    hooks-legacy/_oneshot/dump-symbols.js \
    > /tmp/composed.js
# ... then inject via frida/ host as usual
```

Pour le workflow standard (`simAndCommit`, `compareStandalone`, etc.), utiliser
directement `frida/dist/hooks.js` — voir `frida/README.md`.
