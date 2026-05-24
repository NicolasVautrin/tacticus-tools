# RL pipeline — état au 2026-05-24

## TL;DR

Pipeline RL JSON-only stable à **~87% success rate** (13/15 ou 9/10 avec seed=123).
Fail #10 déterministe et résistant à toutes nos hypothèses (gcRoot, Unity frames,
RNG, roster content). Cause exacte non-identifiée. Hooks de diagnostic en place.

## Acquis nets de cette session

### Architecture
- **1 seul point de mutation BC** (JSON-only via `buildNormalizedBC`) — supprimé
  `_normalizeLiveTemplates` + `normalizeBcAndBuildRunner` + 357 lignes de dead code
- `normalize-bc.ts` : 428 lignes → 71 lignes
- `live-bc.ts` : 315 lignes → 32 lignes
- Bundle : 604 KB → 589 KB

### Naming
- `warmupCampaignGameModeSource` → `warmupGameSingletons` (capture plusieurs
  singletons, pas que CGMS)
- Fichier renommé : `warmup-cgms.ts` → `warmup-singletons.ts`

### Déterminisme
- **Engine seed paramétrable** dans `initRunner({configJson, seed?})` →
  `buildRunner(config, {seed})` → forward à `IdunRunner.Initialize` 2nd arg
- Python script dérive `engine_seed = (batch_seed * 1009 + idx * 2654435761) & 0x7fffffff`
  → rosters et turn counts identiques entre runs avec même `--seed`

### gcRoot leak réparé
**Cause** : `gcRoot.add()` partout sans cleanup symétrique :
- `configPtr` dans `initRunner`
- `AddUnitMessage` dans `buildAddUnitMessage`
- `CheatRunAIMessage` dans `autoPlayRunner`
- Surtout : `recorder.ts` pin chaque message Apply'd (top + AI sub-messages),
  jamais unpinné

**Fix** :
- Ajout `pinForRunner(runnerId, ptr)` dans runner-registry.ts → tracking par runner
- `disposeRunner` libère tous les `pinnedRefs` du runner
- `purgeLogForOrigin` (sim-engine.ts) appelle `gcRoot.remove(ptr(entry.ptr))`
  pour chaque entrée purgée (vrai trou : recorder pin permanent jusqu'à purge)
- Suppression des `gcRoot.add(msg)` transients dans `buildAddUnitMessage` et
  `autoPlayRunner` (le runner.Apply args garde naturellement les refs alive)
- `gcRoot.add(configPtr)` conservé MAIS via `pinForRunner` → free au dispose

**Résultat** : gcRoot stable à **2 entries constant** sur 11 inits
(vs `1 → 3 → 106 → 239 → ... → 960` avant). Pas la cause du fail.

### Per-turn yield dans autoPlayRunner
**Hypothèse** : la boucle while complete dans une seule frame Unity → main
thread starvation.

**Fix** : `autoPlayRunner` refactoré en `async`, **un `queueOnMainThread` par
turn** au lieu d'un pour toute la battle. Entre 2 turns le pump return,
Update() complete, Unity tick une frame, prochain Update drain le turn suivant.

**Frame counter** dans `state.frameNo`, incrémenté par main pump
(`IdunGameViews.Update`) et menu pump (`UnityFreezeDetector.Update`).
Chaque turn emit son `frameNo` → mesure empirique : **`frameDelta=1` constant
entre turns** (Unity tick bien 1 frame entre chaque turn).

**Résultat** : Unity respire entre turns mais **fail #10 toujours là** →
théorie main-thread starvation INVALIDÉE empiriquement.

## Diagnostic — ce qu'on sait pas / sait sur le fail #10

### Symptômes
- Seed=123 → battles #10 et #14 fail à `phase=init err='system error'`
- Standalone (warmup fresh + même roster + même engine_seed) → success
- Même position #10 avec roster différent : peut crash ou pas
- **`IdunRunner.Initialize` enter mais ne return pas** (confirmé via Interceptor)

### Hooks d'observation installés (tous best-effort, JSONL stream)
| Hook | Statut | Fire au fail #10 ? |
|---|---|---|
| `Process.setExceptionHandler` (SEH) | OK | ❌ Non |
| `il2cpp_runtime_invoke` *exc out-param check | OK | ❌ `*exc` null |
| `il2cpp_unhandled_exception` (Interceptor) | OK | ❌ Non |
| `il2cpp_runtime_class_init` (rate-limited) | OK | Pas pertinent |
| `IdunRunner.Initialize` (init-trace) | OK | ✅ Enter sans Leave |
| **`kernelbase.dll!RaiseException`** filter 0xE06D7363 | **JUSTE AJOUTÉ** | **À TESTER** |
| **`kernelbase.dll!OutputDebugStringW`** | **JUSTE AJOUTÉ** | **À TESTER** |
| Native error wrapped → emit `invoke_native_error` avec backtrace + managed exc decode | OK | Backtrace = Frida runtime (post-unwind) |

### Hypothèses testées et invalidées
| Hypothèse | Invalidée par |
|---|---|
| Roster content (necroPlasmancer trigger) | Standalone OK avec même roster |
| Seed BC obsolète (necroPlasmancer renommé en thutmose) | Refuté — Thutmose = display label, ID = necroPlasmancer |
| gcRoot accumulation | Fix réduit à 2 sustained, fail persiste |
| Unity main thread starvation | frameDelta=1 entre turns, fail persiste |
| RNG non-déterministe | engine_seed forwardé, turn counts identiques |

### Hypothèse restante (Gemini)
**Native C++ exception 0xE06D7363** :
- (a) `*exc` null car IL2CPP catch QUE `Il2CppExceptionWrapper`
- (b) Process.setExceptionHandler ne fire pas car Frida VEH ignore intentionnellement 0xE06D7363
- (c) `il2cpp_unhandled_exception` bypass (managed runtime out of loop)
- (d) Frida wrap en "system error" générique
- Cause possible : accumulation côté Unity native (NativeArrays, ECS, pools)
  malgré Unity frame tick — peut-être un autre type de queue plus lente à
  drainer.

**Prochaine étape** : tester le hook `RaiseException` filter `0xE06D7363`
(implémenté dans `crash-trap.ts` mais pas encore validé empiriquement). Si
fire au moment du fail → backtrace native du throw → savoir quel sous-système
Unity throw.

## État technique

- Session Frida active : id=1, pid 68096 (Tacticus rmvdp0v56c)
- Bundle : `frida/dist/hooks.js` (post-rebuild avec RaiseException hook)
- Test command : `python scripts/python/rl_collect_batch.py -n 15 --max-turns 30 --seed 123`
- ai-traces : `frida/data/ai-traces/<sessionId>-<iso>.jsonl`

## Hooks features installés (actifs)
- `crash-trap.ts` : SEH + il2cpp_unhandled_exception + class_init + **RaiseException
  + OutputDebugStringW** (juste ajoutés)
- `init-trace.ts` : IdunRunner.Initialize enter/leave avec gcRoot count

## Tâches

- **#12** [in_progress] Scaler batch RL (n=10 puis n=50) — bloqué par fail #10
- **#13** [pending] Persister singleton ptrs côté host (survie reinjects)
- **#14** [completed] Diag initRunner 'no runnerId'
- **#15** [completed] Diag autoPlayRunner 'Apply failed: system error'
- **#16** [pending] Fix Unity main-thread starvation — invalidée empiriquement

## Reprise post-compact

1. `curl -s http://127.0.0.1:8765/api/admin/status` → check session
2. Bundle déjà built avec RaiseException hook → pas besoin de rebuild
3. **Test direct du hook RaiseException** : run batch n=10 seed=123, fail #10 attendu
4. Inspecter JSONL : `grep '"evt":"raise_exception"' frida/data/ai-traces/*.jsonl`
   et `grep '"evt":"debug_string"'` pour le contexte Unity
5. Si fire → on a la backtrace native du throw → savoir quel sous-système

## Dead code à nettoyer (post-validation)
- `init-trace.ts` : `installExceptionCtorHook` jamais réutilisé (testé, trop hot)
- `_resolveExceptionFields`, `_excMessageOff` dans init-trace.ts (résidu)

## Renames récents
- `warmup-cgms.ts` → `warmup-singletons.ts`
- `warmupCampaignGameModeSource` → `warmupGameSingletons`
- `gcRoot.add(...)` transient → `pinForRunner(runnerId, ...)`
