# tacticus-tools

Hooking Frida de **WH40K Tacticus** (Windows PC build, Unity 6 IL2CPP) — monorepo TypeScript.

## Structure

- Racine : `C:\Users\nicolasv\tacticus-tools`
- `frida/` — codebase active (hooks TS + host TS, bundlé par `frida-compile`)
  - `frida/hooks/` — script injecté dans Tacticus
  - `frida/host/` — serveur Node qui pilote les sessions Frida (Express + WS)
  - `frida/public/` — frontend browser (statique, servi sur `/view/`)
  - `frida/dist/` — outputs build (gitignored)
- `hooks-legacy/` — ancien répertoire de hooks, conservé pour one-shots (dumps,
  probes historiques). Voir `hooks-legacy/README.md` pour classification.
- `data/` — dumps IL2CPP (`symbols.json`, abilities, enums) — gitignored
- `sources_win/` — décompilation Ghidra de `GameAssembly.dll` — gitignored
- `STATUS.md` — état d'avancement vivant du projet

## Cible Windows

- **Exe** : `C:\Users\nicolasv\AppData\Local\tacticus\games\<HASH>\Tacticus.exe`
- **GameAssembly.dll** : ~60 MB, IL2CPP AOT (Unity 6000.3.8f1)
- **Pas d'`adb`, pas de device, pas de `frida-server`** : injection locale via `frida.getLocalDevice()`

### Hash du build = identité du dump

Tacticus stocke chaque build dans `C:\Users\nicolasv\AppData\Local\tacticus\games\<HASH>\`
où `<HASH>` (ex. `nb3o9lmt6c`, `uu2fr8mv6c`, …) **change à chaque mise à jour**
du jeu. Toutes les RVAs IL2CPP, dumps Il2CppDumper (`data/win_dump/`,
`data/dumps/<HASH>/`), décompilations Ghidra (`sources_win/`) et caches
analytiques (`data/all_game_targets_win.tsv`, `call_graph_win.json`, …) sont
**spécifiques à ce hash**. Une RVA résolue contre le mauvais dump donne un
nom de méthode incohérent — symptôme classique : la stack pointe vers une
méthode qui n'existe pas dans le binaire actif (typique : `findMethod` retourne
RVA différente de celle dumpée), et tous les hooks installés via RVA hardcodée
(ex. `RVA_BUCKET_ADD_ACTION = 0x1478820`) tombent sur du code aléatoire.

**Avant de consulter `sources_win/` ou `data/dumps/<HASH>/` ou de croiser
une stack frame contre `all_game_targets_win.tsv` :**

1. Lire le hash du build courant :
   ```bash
   ls -d /c/Users/nicolasv/AppData/Local/tacticus/games/*/
   ```
2. Lire le hash du dump :
   ```bash
   cat data/dumps/<HASH>/HASH    # ancien data/win_dump/HASH
   ```
3. **Si les deux ne matchent pas, refuser l'analyse offline** : signaler à
   l'utilisateur, demander un re-dump avant tout. Forcer la désynchronisation
   silencieuse a déjà coûté plusieurs heures de debug.

### Règle de code : résolution runtime, pas de RVA hardcodées

**Tout hook doit résoudre son entry point en runtime** via la table IL2CPP :

```ts
const klass = findClassAnywhere(ns, cls);              // helpers.ts
const mptr = findMethod(klass, methodName);            // helpers.ts
Interceptor.attach(mptr.ptr, { ... });
```

**Aucune RVA hardcodée**, ni en constante, ni en fallback `?? il2cppBase.add(0x...)`.
Une RVA copiée d'un dump devient invalide au prochain changement de hash, et
`Interceptor.attach` réussit silencieusement sur du code aléatoire — symptôme
que le hook ne fire jamais (ou fire et crashe). Si `findClassAnywhere` ou
`findMethod` ne trouve pas la méthode (rare — typiquement des gshared bodies
ou des classes non indexées par `image_get_class`), c'est une vraie limitation
à investiguer, **pas** un cas pour ressortir un RVA offline.

Cette règle s'applique aux dumps offline pareil : tout `data/dumps/<hash>/*.tsv`
ou `*.json` n'a de valeur que pour la **lecture humaine** (consulter du code
décompilé, comprendre l'archi). Aucun hook live ne doit en dépendre.

## Démarrage

```bash
cd frida && npm run dev
```

Host sur `http://127.0.0.1:8765`. Front sur `http://127.0.0.1:8765/view/`.

## Workflow utilisateur (validé)

1. Lancer Tacticus, attendre que le menu principal soit pleinement loaded.
2. Ouvrir le front (`/view/`).
3. Cliquer **INJECT** dans l'UI (auto-discovery du PID via `_Data/` adjacent à l'exe).
4. Cliquer un battle de campagne in-game (= warmup) → l'agent capture
   `lastSource` + `lastUnitProgression` + `IdunUniverse` automatiquement, push
   `builder_ready` au front, qui déclenche un refresh catalog.
5. Builder front : tout est armé. On peut générer la `BattleConfiguration` de
   n'importe quelle node (events inactifs inclus) sans relancer une battle.

## Workflow RL — runner isolé avec config patchée

Pour entraîner un agent RL sans toucher au battle in-game, on utilise un
**runner isolé** construit depuis la `BattleConfiguration` capturée. Le runner
isole complètement le state — on peut le créer/détruire à volonté sans casser
le jeu actif.

**Procédure obligatoire dans cet ordre** :

1. **Warmup une fois** par session Frida (après chaque inject/reinject) :
   ```
   warmupCampaignGameModeSource({ force: true })
   ```
   Sans ça : `lastSource._currentBattle` est null ou stale → tous les
   `buildPatchedRunner` / `inspectBattleConfig` échouent. Le warmup
   déclenche `CampaignGameModeSource.LoadBattle` qui peuple `_currentBattle`.

2. **Build runner isolé** (avec patch optionnel) :
   ```
   buildPatchedRunner({
     aiUnits: ["necroNpc1Warrior:6", ...], // 10 strings exactes
     randomizeAi: true,                     // optionnel
     templateOverrides: { ... },            // optionnel (HP/dmg sur player roster)
   })
   ```
   Retourne `{ runnerId, runner, seed, bcPtr, patch }`. Le patch s'applique
   in-place sur `lastSource._currentBattle`. **`Initialize()` du runner consume
   les `PredefinedUnits` patchées et auto-spawn les enemies** — pas besoin
   d'appeler `spawnPredefinedUnits` séparément.

3. **Observer l'état** :
   ```
   observeBattle({ runnerId })
   ```
   Renvoie `{ stage, byType, units: [{ entityId, visualId, hp, ... }] }`.
   À ce stade : `stage=Setup` (0), 10 units présentes côté AI.

4. **Itérer sans repasser par la game UI** : le `lastSource._currentBattle`
   reste valide tant que la session Frida n'est pas réinjectée. On peut
   re-patch + re-buildPatchedRunner autant qu'on veut. Chaque appel crée
   un nouveau `runnerId`.

**À NE PAS oublier** :
- Re-warmup après chaque `reinject` (la mémoire managée du wrapper survit
  mais les caches Frida-side perdent les MethodInfo*).
- `buildPatchedRunner` mute la BC source — clone si on veut comparer
  multiple variants.
- Les unit IDs AI sont au format `"unitId:level"` (ex. `"necroNpc1Warrior:6"`),
  pas juste `"necroNpc1Warrior"`.

## Build + Injection

```bash
cd frida && npm run build:hooks   # → frida/dist/hooks.js (~110 KB)
```

L'**injection se fait via l'UI** (`POST /api/admin/inject`) — pas en ligne de
commande. Le host gère device discovery, attach, load script, session lifecycle.

Pour info : (file:///C:/Users/nicolasv/tacticus-tools/frida/host/admin.ts) +
(file:///C:/Users/nicolasv/tacticus-tools/frida/public/src/admin.js).

## Arrêt

- Ctrl+C dans le terminal `npm run dev`, ou
- `curl -s -X POST http://127.0.0.1:8765/api/_dev/shutdown` (graceful).

## Restart du host (pour Claude)

Quand tu modifies du code dans `frida/host/` (router, config-store, sessions,
admin, …) le host doit être redémarré — `npm run dev` lance `tsx host/index.ts`
**sans watch**. Procédure :

1. Shutdown graceful : `curl -s -X POST http://127.0.0.1:8765/api/_dev/shutdown`
2. Relance en background : `cd frida && npm run dev > /tmp/host.log 2>&1 &`
3. Vérification : `curl -s http://127.0.0.1:8765/api/health` doit retourner
   `{"status":"ok"}` après ~3 s.

**Important** : le restart du host **réinjecte** l'agent Frida via auto-restore
(load fresh `dist/hooks.js` dans le PID Tacticus). L'état mémoire du précédent
agent est perdu — donc :
- `lastSource` (CampaignGameModeSource), `lastUnitProgression`, `lastUniverse`
  redeviennent `null`
- Les RPCs `buildCampaignConfig` / `dumpCampaignCatalog` / etc. répondent
  "no live CampaignGameModeSource captured" jusqu'à re-warmup
- **L'utilisateur doit cliquer une battle de campagne in-game** pour
  ré-armer (le hook `CampaignGameModeSource..ctor` recapture sur navigation)

Re-build de `dist/hooks.js` requis uniquement quand `frida/hooks/*` a changé
(`npm run build:hooks` avant le restart).

## Ne jamais

- **Utiliser `--reload`/hot-reload côté host** : casse les sessions Frida
  actives, peut crash Tacticus si `Interceptor.replace` est en cours.
- **Stop manuel d'une session avec `Interceptor.replace` actif** sans le
  protocole cleanup graceful (crash le jeu).
- **Heap scans automatiques** (`Process.enumerateRanges`, `Memory.scan`) :
  Frida suspend les threads de la cible pendant le scan IL2CPP heap (~10 s sur
  Tacticus PC). UnityFreezeDetector (qui est lui-même hooké pour le pump)
  conclut que le main thread est figé → tue le process. Heap scans uniquement
  sur action utilisateur explicite, gated par `allowHeapScan: true`.
- **Broad-hooks sur méthodes UI hot** (`UnitProgression.Get*/Has*/...`) : la
  surcharge des trampolines × hot path = destabilisation IL2CPP cctor cascade.
- **Hook permanent sur des property getters** appelés par les sérialisations
  Newtonsoft du jeu (ex. `GameConfigData.get_gameConfigDto`) : 27 000 appels/s
  → frame >960 ms → crash.
- **Commit** : `data/`, `frida/dist/`, `hooks-legacy/`, `server/`, `logs/`,
  `frida/assets/raw/`, `sources_win/`.

## Documentation détaillée

!include .claude/skills/tacticus/references/frida-host.md
!include .claude/skills/tacticus/references/hooks.md
!include .claude/skills/tacticus/references/rpc-api.md
!include .claude/skills/tacticus/references/knowledge.md
!include .claude/skills/tacticus/references/game-architecture.md
!include .claude/skills/tacticus/references/decompilation.md
!include .claude/skills/tacticus/references/ai-engine-audit.md
