# tacticus-tools

Hooking Frida de **WH40K Tacticus** (Windows PC build, Unity 6 IL2CPP) — monorepo TypeScript.

## Structure

- Racine : `C:\Users\nicolasv\tacticus-tools`
- `frida/` — codebase active (hooks TS + host TS, bundlé par `frida-compile`)
  - `frida/hooks/` — script injecté dans Tacticus
  - `frida/host/` — serveur Node qui pilote les sessions Frida (Express + WS)
  - `frida/public/` — frontend browser (statique, servi sur `/view/`)
  - `frida/dist/` — outputs build (gitignored)
- `scripts/frida/` — scripts Frida one-shot **vivants**, hors bundle (notamment
  `dump-il2cpp-full.js`, qui produit toute la chaîne de symboles).
- `hooks-legacy/` — hooks et probes **historiques** (versionnés, consultables). Rien
  de vivant ne doit en dépendre. Voir `hooks-legacy/README.md`.
- `data/` — **VERSIONNÉ à la racine, aucune règle ne l'ignore** (depuis le 2026-07-26). Règle de
  partage : **`data/` = ce qu'on LIT, `logs/` = ce qu'on ÉCRIT**. Les `data/` NICHÉS
  (`frida/data/`, `scripts/python/data/`) sont des sorties runtime, eux ignorés.
  ⚠ Un fichier laissé non suivi sous `data/` n'est protégé par RIEN : `git clean` et un
  `worktree remove --force` l'effacent sans trace. L'indexer est ce qui le sauve.
- `sources_win/` — décompilation Ghidra de `GameAssembly.dll` — gitignored
- `STATUS.md` — **instantané HISTORIQUE du 2026-05-03** (ère « Tacticus Builder » : pipeline
  d'injection et de build de nœud). **Ce n'est pas l'état du projet** — ne pas s'y fier.

### Où lire l'avancement (ces fichiers-là, pas `STATUS.md`)

- `docs/rl/backlog.md` — **les tâches OUVERTES**, versionné (le tracker `TaskCreate`/`TaskList` vit
  côté compte et a déjà disparu d'une session). Les tâches finies n'y sont plus : elles ont leur
  `docs/rl/case-<n>-*.md`. ⚠ Il décrit des INTENTIONS HORODATÉES, pas l'état du code — confronter
  au commit courant avant de dispatcher.
- `docs/rl/kit-coverage.md` et `docs/rl/combat-ability-coverage.md` — **audits GÉNÉRÉS** de la
  couverture (`audit_kit_coverage.py`, `audit_combat_ability_coverage.py`, depuis `scripts/python/`).
  Les régénérer après tout port et au changement de build ; **ne jamais résoudre un conflit dessus
  — les REGÉNÉRER**.
- Les chiffres se **re-dérivent**, ils ne se citent pas : ils bougent à chaque tranche livrée.

## Cible Windows

- **Exe** : `C:\Users\nicolasv\AppData\Local\tacticus\games\<HASH>\Tacticus.exe`
- **GameAssembly.dll** : ~60 MB, IL2CPP AOT (Unity **6000.3.13f1** au 2026-08-04 — comme le
  `<HASH>`, ça bouge à chaque mise à jour : le LIRE dans `meta.unityVersion` de la réponse
  d'inject, jamais recopier cette ligne. Elle est restée à `6000.3.8f1` plusieurs builds durant.)
- **Pas d'`adb`, pas de device, pas de `frida-server`** : injection locale via `frida.getLocalDevice()`

### Hash du build = identité du dump

Tacticus stocke chaque build dans `C:\Users\nicolasv\AppData\Local\tacticus\games\<HASH>\`
où `<HASH>` (ex. `nb3o9lmt6c`, `uu2fr8mv6c`, …) **change à chaque mise à jour**
du jeu. Toutes les RVAs IL2CPP, le dump `data/il2cpp_full.json` et ses TSV,
la table `data/symbols/<HASH>/` et les décompilations Ghidra (`sources_win/`) sont
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

**Quand il n'y a RIEN à résoudre** (placeholder `FUN_*` sans `MethodInfo`, point interne, `DAT_*`,
corps d'itérateur), l'exigence n'est pas « pas d'adresse » — c'est **détecter la péremption et
REFUSER de s'attacher**. Foyer unique : `pinnedAddress` de `frida/hooks/il2cpp/build-pin.ts`
(pendant live de `build_pin.require_pinned`, #431). Le porteur DÉCLARE son build, le foyer le
confronte à celui qui est chargé, et rend `null` en le disant. **C'est le SEUL module où
`il2cppBase.add(<constante>)` a le droit d'exister**.
⚠ La phrase « reste en VA, et c'est voulu » (§ suivant) est écrite pour la **CITATION**, jamais
pour l'**ATTACHEMENT** : mesuré le 2026-08-04, les six adresses en dur des hooks étaient **6/6
périmées**, et la seule encore armée attachait `Interceptor` **au milieu d'une autre fonction**.
⚠ Et « résolu au runtime » ne suffit pas non plus : sur une **définition générique**, `findMethod`
rend le **thunk d'invocation**, pas le corps gshared — `bucket-audit` se déclarait `enabled` avec
**0 fire**. Passer par l'**instance inflatée** (#259-b). Détail : `docs/rl/case-475-adresses-epinglees.md`.

### Règle d'écriture : on cite un SYMBOLE, jamais une adresse

**Toute référence à du code natif — commentaire, docstring, message de test, doc —
s'écrit avec le symbole Ghidra VERBATIM, jamais avec une VA.**

```
IdunBattle.Core.Services.DamagePrediction$$CalculateDirectDamage      ✅
`CalculateDirectDamage @18102f130`                                    ❌
```

- **Point interne** à une fonction : `<symbole>+0x<offset>`.
- **Échappement conservé tel quel** (`u003C` = `<`, `u003E` = `>`) : c'est ce qui rend le
  grep code ↔ table immédiat.
- **Les offsets RELATIFS restent** : champs de struct (`+0xa8`), slots de vtable, RVA
  calculées en code depuis l'image base. Seules les **VA absolues** sont proscrites.

**Pourquoi** : churn inter-build **mesuré** (build de mai → `gqfc5mff6c`) — les noms sont
stables à **97,5 %**, les adresses changent à **100 %**. Une citation par adresse est donc
fausse dès la mise à jour suivante, **silencieusement** : on ne l'apprend qu'en lisant du
décompilé qui ne correspond à rien. Le symbole, lui, survit et se re-résout d'un grep.

**Comment résoudre** une adresse trouvée dans Ghidra :

```bash
python scripts/python/ghidra_symbols.py whereis <VA>     # -> <symbole>+0x<offset>
```

ou, 100 % offline (ghidra-mcp éteint), un grep dans `data/symbols/<build>/functions.tsv`
(format `<adresse>\t<symbole>`). Migration d'un lot existant :
`scripts/python/migrate_va_to_symbol.py` (token-aware — il ne réécrit QUE dans les
commentaires et chaînes, jamais un littéral exécutable) ; `probe_va_in_code_vs_prose.py`
est le garde-fou à passer avant.

**Reste en VA, et c'est voulu** : les adresses qui ne résolvent que sur un placeholder
`FUN_<addr>` (le « symbole » n'y est que l'adresse déguisée) et les thunks de la table
d'imports. Les lister plutôt que les maquiller.

### L'ABSENCE d'une méthode dans les tables ne prouve RIEN

**`frida/methods.tsv` et `ghidra/functions.tsv` sont indexées par ADRESSE**, et IL2CPP
**déduplique les corps triviaux** (`mov eax,imm32 ; ret`, `xor eax,eax ; ret`, un `ret` nu…).
Un corps partagé par N classes n'a donc qu'**UN SEUL propriétaire** dans la table. S'y ajoute
que les **bases génériques** (`Playbook<T>`, `NonComparablePlaybook<T>`…) sont **absentes du
dump**, donc un getter hérité n'y est pas lisible non plus.

⇒ **« `<Classe>$$<Méthode>` n'apparaît pas dans la table » ne permet JAMAIS de conclure
« la classe ne surcharge pas ».** Ghidra ne nommera aucun de ces corps non plus.

**Mesuré (2026-07-27)** : `methods.tsv` = 121 502 lignes, **0 RVA répétée** ; `get_Priority`
y occupe **3 lignes pour 22 surcharges réelles**. C'est exactement ce faux négatif qui avait
fait écrire « aucun override n'existe » — puis **supprimer** deux valeurs justes en les
croyant périmées.

**Les génériques pleinement partagés sont absents du dump FRIDA, présents dans le dump
GHIDRA.** Mesuré le 2026-07-31 sur `rnca9r7q6c` : `__Il2CppFullySharedGeneric` = **4 874**
dans `ghidra/functions.tsv`, **0** dans `frida/methods.tsv` (dont **2 184**
`IdunBattle.AI.Playbook`). Le zéro Frida est structurel — le `methodPointer` d'une définition
générique est un thunk, pas le corps. Donc : chercher un générique dans **Ghidra**, et ne pas
conclure à l'illisibilité de la couche `Playbook`. Détail :
**`docs/rl/case-259-couverture-gshared.md`**.

**Comment conclure pour de vrai** : invoquer le **slot de vtable** sur l'instance (runtime,
cf. `reference_il2cpp_methodptr_uninit_class`), balayer **toutes** les valeurs d'enum
concernées plutôt que les classes trouvées, et recouper par une seconde source indépendante.
Détail de la méthode : `docs/rl/case-170-get-priority.md`.

## Workflow RL — runner isolé

> **Le LANCEMENT DE RUNNER est centralisé dans `.claude/skills/tacticus/references/runner.md`**
> (inclus ci-dessus, pointé par les agents `validator`/`re-expert`) : warmup obligatoire, voie
> `rl_duel build`, choix de board (`--board`/`--board-pool` + `board.py`), discipline runner.
> C'est LA source unique — ne pas dupliquer ces règles ici.

Pour entraîner un agent RL / valider le moteur sans toucher au battle in-game, on monte un
**runner isolé** depuis une **seed BC sur disque** (`rl_duel build`), déployé et pilotable à
volonté sans casser le jeu actif. Rappel des deux points les plus violés (détail : `runner.md`) :

1. **Warmup une fois par session Frida**, AVANT tout RPC/build. Sans lui : caches `MethodInfo*`
   vides + init IL2CPP non amorcée → crash `0x2c`. Il est **autonome** (pilote la nav lui-même,
   rend la main sur l'écran CAMPAGNE, sait sortir seul d'un écran de bataille hérité, ~12 s) :
   **ne JAMAIS demander à un humain de cliquer une battle ni de ramener la campagne.**
   Session froide → `warmupGameSingletons({ force: true })`.
   La PROCÉDURE (inject, endpoints host, fenêtres) est orchestrateur-only : skill
   `tacticus-orchestration`. Un agent ne (ré)injecte pas — cf. invariant 4 plus bas.

   > **RÈGLE INCONDITIONNELLE — warmup après CHAQUE (re)inject, AVANT tout RPC/probe, SANS EXCEPTION**,
   > y compris les probes « self-contained » montés depuis une seed BC sur disque (ex.
   > `rl_probe_step.py`, `rl_collect_batch`). Un (re)inject repart avec des caches `MethodInfo*`
   > Frida-side vides + la couche d'init IL2CPP non ré-amorcée dont dépend `initAndStart`. Un probe
   > qui « marche » sans warmup ne prouve rien (jeu déjà warm par chance) → au prochain build froid
   > c'est le crash `0x2c` (metadata non initialisée). Ne jamais raisonner « ce mode-là n'a pas
   > besoin de warmup ».

2. **Build + pilotage** : `rl_duel build --seed <s> --state-file <propre> [--p-units/--a-units,
   --board/--board-pool, ...]` puis `view/act/play/aiturn` ou `engine_validate.py --runner <id>`.
   Discipline runner (state-file propre, `--runner` explicite, coexistence/MAX_RUNNERS, dispose
   tes runners jamais ceux des autres) : `runner.md` §3.

## Sorties console Python — ASCII only (Windows cp1252)

La console Windows (et les tools Bash/PowerShell) tourne en **cp1252**, pas UTF-8.
Tout caractère non-ASCII envoyé à `stdout` (un `print`, un message d'assertion pytest
affiché via `-s`, une f-string de diagnostic) lève **`UnicodeEncodeError`** et fait
**crasher le script / échouer le test** — un faux négatif qui masque le vrai résultat
(les assertions, elles, passaient).

- **Dans tout `print`/log/sortie de script ou de test Python : ASCII uniquement.**
  Remplacer les symboles courants : `->` (pas `→`), `OK`/`X` (pas `✓`/`✗`), `<=`/`>=`
  (pas `≤`/`≥`), `Delta`/`d=` (pas `Δ`), `x` (pas `×`), `v`/`down` (pas `↓`), `...`
  (pas `…`). Le français accentué (é, è, à) est **aussi** non-ASCII → l'éviter dans les
  chaînes *imprimées* (OK dans les commentaires/docstrings non imprimés).
- **Pytest** : ne pas compter sur `-s` pour voir des prints contenant du non-ASCII (ça
  crashe). Invoquer pytest **sans `-s`** (sortie capturée) ; si une diagnostic est
  vraiment nécessaire à l'écran, la garder ASCII ou poser `PYTHONIOENCODING=utf-8`.
- **Pourquoi** : faute déjà commise plusieurs fois (`→`/`✓`/`Δ`/`↓` dans des prints) ;
  le contenu *écrit dans un fichier* via `open(..., encoding="utf-8")` n'est PAS concerné,
  seulement ce qui part vers la console.

## Tests du moteur Python — NE PAS relancer la suite complète

Après une modif, **ne lancer QUE les tests CIBLÉS de la tranche touchée**, jamais toute la
suite `tests/engine/` — **beaucoup trop lourd**.

- **Pourquoi** : chaque test live monte une (ou plusieurs) bataille(s) isolée(s) via le runner
  (build + nav + RPC). Un seul fichier = quelques dizaines de secondes à plusieurs minutes ; la
  suite entière = ~10 min+ et sature la session Frida. C'est un coût disproportionné pour valider
  un changement localisé.
- **Comment** : invoquer pytest sur les **fichiers pertinents uniquement** (ex. slice DAMAGE →
  `test_damage_roll_live.py` + `test_runner_attack_live.py` + les tests crit/block ; slice EFFETS →
  `test_effect_*_live.py`). Inclure un test de garde par dépendance impactée (ex. une modif d'un
  composant partagé `effects`/`base` → relancer aussi un test damage qui consomme ce chemin), mais
  **pas plus**.
- **Suite complète** : seulement sur **demande explicite** de l'utilisateur, ou avant un jalon
  (commit d'une tranche), pas après chaque édition.
- **PLUSIEURS modules à lancer → les lancer EN PARALLÈLE, 4 à la fois.** Mesuré le 2026-07-29 sur
  7 fichiers : 278 s en série → 80 s. Le harnais le supporte déjà (state-files isolés par PID,
  runner en `scope="module"`), donc N processus pytest, ou `pytest-xdist -n 4 --dist loadfile`
  (`--dist loadfile` OBLIGATOIRE : sans lui xdist répartit les *tests* et chaque worker
  reconstruit le runner du module). **Pas plus de 4** : le rendement tombe à 23 % dès 6 workers,
  et le pump est partagé avec les autres agents.
- **Le plafond de 4 borne ce qui MONTE UN RUNNER, pas la parallélisation.** C'est le critère :
  runner/RPC → 4 max (pump partagé) ; **purement offline → autant que le CPU**.
  ⚠ Deux probes lancés ENSEMBLE qui portent le même littéral de state-file se marchent dessus —
  **4 groupes, 16 probes sur 526** (`_49gnt`, `_32ct`, `state.json`, `_57h`). Non bloquant : les
  108 porteurs de littéral acceptent tous `--state-file`, donc un chemin explicite dissout la
  collision. Les 264 probes qui prennent leur chemin *uniquement* par argument ne sont isolés que
  si l'appelant leur en donne un distinct.
- **Un FICHIER dont le bilan est `passed == 0 and skipped > 0` fait désormais ROUGIR la passe
  (#455).** Le skip n'est pas le défaut — l'INVISIBILITÉ l'est : `test_summon_trait_effects_live.py`
  rendait 8 skipped / 0 passed / rc 0 sur `master`, zéro assertion évaluée, trouvé en ÉCARTANT une
  PR. Le garde #77 ne le voyait pas : il lit la RAISON d'un skip, et un skip de MONTAGE ne porte
  aucun marqueur de harnais. Si ton fichier rougit ainsi : **répare le montage** (c'était le cas —
  8 skipped → 8 passed) ou **nomme** l'impossibilité, jamais retirer le skip pour faire taire.
  Le garde se tait sur sélection partielle (`-k`, nodeid, `-x`) ; échappatoire consciente
  `TACTICUS_ALLOW_GREEN_SKIP=1`. Détail : `docs/rl/case-455-fichier-integralement-skippe.md`.
- **Un fichier dont TOUS les tests ont DISPARU rougit aussi (#455-r3)** — autre porte, même vice.
  Il n'émet aucun report, donc aucun bilan : le critère ci-dessus lui est structurellement aveugle,
  et pytest ne le signale (`rc=5`) que s'il est joué SEUL. Le discriminant est la **COLLECTE**, pas
  la sélection : `-k`/`-m`/`--deselect` filtrent APRÈS elle, un nodeid explicite n'émet aucun report
  de collecte — donc **aucune allowlist**. Un helper reste hors de portée par son NOM (`_x.py`,
  hors `python_files`). Deux volets : hook `pytest_collectreport` à chaque passe, et un balayage
  statique à périmètre dérivé dans le cliquet (le runtime ne voit que ce qu'une passe joue).

## Tu OUVRES un résidu ⇒ tu DEMANDES son numéro, tu ne le choisis pas (#468)

```powershell
python scripts/python/probe_468_collision_numeros.py --suggere [parent]
```

Rien n'allouait les numéros : ils étaient pris au vol, et une collision ne se voyait **qu'à l'œil au
merge**. Deux le 2026-08-04 à quelques heures d'écart, plus une **quadruple** (`#420-r1`, quatre
dossiers) que le cliquet a trouvée à son premier passage.

- **Les deux modes ont des critères INVERSES, et c'est voulu.** Détecter porte sur la **position**
  (1ʳᵉ cellule, tête de puce, préfixe de case-doc) — sur `docs/rl`, 6 580 occurrences `#<n>` pour
  836 définitions, donc un critère par présence rougirait sur presque tous les renvois. Attribuer
  porte sur l'**UNION** (mentions et messages de commit compris) : **un numéro seulement cité est
  déjà pris**. Mesuré : 13 racines `< 500` n'existent QUE dans `git log`.
- **Une mesure incomplète ne rend JAMAIS de numéro** (git muet → 99, rien suggéré), et on ne
  recycle pas un trou — une PR peut être en vol.
- ⚠ La **puce** de résidu d'une case-doc est une 4ᵉ position de définition **de fait**, non gardée
  (`#468-r7`) ; et `#<n>` désigne à la fois une tâche et une PR (`#468-r8`), ce qui rend
  `git log --grep` structurellement ambigu.

## L'état de la BOUCLE — `loop_status.py`, déclenché tout seul (#467)

```powershell
python scripts/python/loop_status.py          # flotte / livraison / harnais
```

Il garde la **BOUCLE** : agents en vol vs plafond, commits non poussés, worktrees d'agents
nettoyables, PR ouvertes, session Frida, drain, et **`liveRunners`** (le budget partagé des
4-en-parallèle, que personne ne peut deviner).

- **Il se déclenche seul** : hook `Stop` du projet (`.claude/settings.json` →
  `scripts/hooks/loop-status.ps1`). Une checklist qu'il faut PENSER à lancer est oubliable —
  mesuré le 2026-08-04, un tour terminé à **1 agent sur 5** avec 30 commits non poussés et
  4 worktrees livrés, sans que rien ne le signale.
- **Il se TAIT** quand il n'y a rien à faire, et le critère de silence est **dérivé** : hors
  campagne (0 agent, 0 worktree, 0 PR, 0 commit d'avance), silence total.
- **Tri-état obligatoire** sur tout ce qui vient du host ou de `gh` : `null` = **PAS mesuré**,
  jamais rendu comme un zéro (même règle que `host_inputs.py`). Un `liveRunners` rabattu sur 0
  fait lancer 4 tests sur un budget inconnu — faute déjà commise.
- **Un verdict doit dire À QUOI il s'applique — jamais rendre pour l'état COURANT ce qui juge un
  ANCÊTRE (#472).** Mesuré : le hook a répété trois tours de suite un verdict pour une cause déjà
  corrigée, `HEAD` ayant changé deux fois entre-temps ; re-mesuré à froid, **48 commits** d'écart.
  Un verdict **PÉRIMÉ** reste **AFFICHÉ** avec les deux commits — il change d'**accusé** (contexte,
  pas signal), pas d'existence, et n'est rabattu **ni sur un vert ni sur un rouge**.
- ⚠ **Le chiffre du plafond (5) est le SEUL qui ne soit pas une mesure** : c'est un paramètre
  d'orchestration (`--max-agents`, `TACTICUS_DISPATCH_CAP`). Résidu `#467-r1`.
- ⚠ **Une panne de capteur doit porter son NOM (#467-r6).** `gh` rendait `rc=127` pour ses trois
  pannes — binaire absent, délai dépassé, `OSError` — parce que toutes retombaient sur la même
  sentinelle. Résultat **mesuré** : l'incident a été diagnostiqué « `gh` absent du PATH » alors que
  `gh` était sur le PATH (identique sous `pwsh` et sous le `powershell.exe -NoProfile` du hook) et
  que la vraie cause était le **budget** — 2,90 s pour 3,00 s en solo, **5 tours sur 8** aveugles
  dans le tour complet, **0/8** après correctif. Un capteur qui ne sait pas nommer sa panne fait
  corriger la mauvaise cause. La piste « remplacer `gh` par du git pur » est **réfutée** :
  `--no-merged origin/master` sur les remotes rend **79** branches pour **1** PR ouverte (elles
  survivent au squash-merge), et le filtre de fraîcheur qui la sauverait rate les PR *anciennes*,
  les plus oubliables.
  ⚠ **Et un `rc` ne NOMME rien** — mesuré sur `gh 2.88.1` : `rc=1` couvre à lui seul le token
  invalide (HTTP 401), le dépôt inconnu (GraphQL) et l'erreur d'usage ; `4` = non authentifié. Seul
  le **stderr** les sépare, et le lecteur le **jetait**. Une table `rc -> libellé` aurait rendu un
  *mot* à la place d'une *cause*. Même vice côté **git**, où `RC_MUET` couvrait délai dépassé et
  erreur système sur le capteur qui court sous les 3 s du hook. Et nommer ne suffit pas s'il n'y a
  personne pour lire : un `git status` en échec rendait `push`/`sale`/`nettoyage` muets d'un bloc.
- ⚠ **Un repli sur cache peut SIGNALER, jamais RASSURER.** Servi quand `gh` est muet, il n'est
  retenu que s'il porte une PR **ouverte** : un cache disant « 0 PR » ne prouve rien, et le rabattre
  en mesure ferait taire l'outil sur une PR ouverte depuis. Aucun chemin ne fabrique un zéro.
- **Deux probes** gardent SA fidélité, et le second existe parce que le premier ne pouvait pas
  voir son gisement : les deux probes #467 **substituent** `http_json`, donc un champ disparu côté
  host les laissait verts tous les deux. `probe_467r4` confronte le contrat au **code source** du
  host, liste des champs **dérivée** de `mesurer_harnais`. Détail :
  `docs/rl/case-467-etat-de-boucle.md`.

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
- **Commit** : `frida/dist/`, `server/`, `logs/`, `frida/assets/raw/`, `sources_win/`.
  (`hooks-legacy/` EST versionné — l'ancienne mention ici était fausse. **`data/` à la racine
  aussi** : la ligne qui l'interdisait ici datait d'avant le 2026-07-26 et faisait laisser
  non suivies des entrées que `git clean` détruit — cf. section Structure.)

## Protocole RE + portage (DÉCISION + COMBAT)

Le protocole complet — recon du kit, RE fidèle (décompilé = vérité, jamais l'expérience live),
mirror 1:1 des fonctions natives nommées, décomposition par étage (jamais fitter un scalaire),
validation des DEUX faces (décider ≠ exécuter) — vit dans le skill `tacticus-re-port`
(invocable via `/tacticus-re-port`), inclus ci-dessous. C'est LA source unique de cette doctrine.

### Gate de confrontabilité : HERO / MoW / SUMMON — jamais NPC

Avant de porter une mécanique (ou d'exiger un datapoint live), établir **qui la porte** et si ce
porteur est atteignable en bataille. Trois catégories de porteur comptent, et les chemins de
vérification sont **distincts** :

- **HERO / MACHINE OF WAR** → présence dans `python scripts/python/rl_duel.py build --list-pool`
  (rank courant) — surtout pas `kind == lineup` de gameconfig, qui ment.
  **ABSENT DU POOL ≠ NON CONFRONTABLE** — le pool dérive du seed BC, capture d'**UNE** bataille.
  Un héros hors pool s'**injecte** (`catalog_inject.write_augmented_seed_bc` + `build --seed-bc`) :
  recette et pièges dans **`docs/rl/case-92-catalog-injection.md` §6**. Seul refus légitime :
  `data/unspawnable_rank<N>.json`. Mesuré le 2026-07-29 — `spaceWolfPriest`, classé « non
  confrontable » par un solveur, entre au pool (97 → 98) par cette voie.
- **SUMMON** → compte **aussi**, **même absent de `--list-pool`**. On l'amène en bataille en spawnant
  son **summoner** (qui, lui, doit être dans le pool) : le summon apparaît dans l'équipe du summoner.
  **Ne jamais conclure « non confrontable » d'un carrier summon.**
  ⚠ **Mais on l'OBSERVE, on ne le COMMANDE pas** — et le confondre a coûté un faux verrou (#291,
  `docs/rl/case-291-summon-activation.md`). Le natif TERMINE le tour de toute unité qui apparaît
  pendant le tour de son propriétaire (`SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` →
  `FinishUnitTurn(spawned, isTerminated: true)` → `MarkUnitAsNoActionAvailable`, sauf traits
  `Steppable`/`Hero`), donc un summon **n'entre JAMAIS** dans `decisionView.toActivate`, et
  `aiDryRunAllUnits` rend pour lui `FinishUnitTurnMessage` — c'est la réponse CORRECTE du natif, pas
  un trou de harnais. Il agit par deux chemins, qui sont les points d'observation :
  **(a)** le nœud DSL `PerformAIAction` de l'ability du summoner (→ `ComputerAction` forcé) — ses
  déplacements/abilities sont dans les **events du cast**, portés par l'entité du summon ;
  **(b)** `PlayAutomaticUnits` au **turn-start suivant** de sa team (trait `Summon`/`Object`) — se lit
  au delta d'état pris au tout début de son tour, avant toute action. Recette et probe :
  `probe_291_summon_activation.py`.
- **NPC** → le porteur est hors-jeu. Mais **« npc-only » n'implique PAS « non confrontable »** :
  quand le natif charge le playbook **PAR ABILITY** et que son utilité ne lit ni stats ni traits du
  caster, l'ability se **GREFFE** sur une unité du pool. Mesuré le 2026-07-31 — `1194 NovaShield`,
  seul porteur `tauBossRiptide` (npc), confrontée sur `tauCrisis` : **bug de port trouvé**. Recette :
  `docs/rl/case-92-catalog-injection.md` §5bis. Vérifier la condition avant de greffer ; à défaut,
  écrire NON CONFRONTÉ, jamais « non pertinent ».

#### Une ability de RELIQUE se ventile en TROIS états, jamais deux

« Confrontable / non confrontable » est un axe **faux** pour une relique — et le rabattre à deux a
produit au moins **six verdicts « 0 porteur, DEAD » démontrés FAUX** (recensés dans
`docs/rl/case-323-unit-map-attribution-voies.md`). Les trois états :

1. **Équipée au seed** → confrontable *tout de suite*, sans rien monter. Lire
   `BC.Units[].TertiaryAbility`. Mesuré : **4 unités** du seed en portent une (3 abilities
   distinctes — `admecMarshall` et `admecRuststalker` partagent la même). `buildNormalizedBC` la
   **préserve** (`normalize-bc/json-build.ts` ne touche qu'à `TertiaryAbilityLevel`).
2. **Porteur au pool, relique NON équipée** → **montage ÉCRIT (#237)** :
   `rl_duel build --equip-relic "<unitId>:<Ability>[:level]"`, ou `catalog_inject.equip_relic` /
   `write_relic_seed_bc` depuis un test. C'est le cas de loin le plus fréquent : sur les **56**
   unités du seed éligibles à une relique — **toutes dans le pool** — **52 y arrivent sans**.
3. **Porteur hors pool** → injection catalogue, comme un héros hors pool (**9** unités), **puis**
   le montage de l'état 2.

**Le montage tient en TROIS écritures, et DEUX échouent EN SILENCE** (RE :
`docs/rl/case-237-relique-forcee.md`) : `BC.Units[].TertiaryAbility` (sans lui,
`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` ne monte rien, sans erreur) ;
la config d'ability dans `BC.Abilities.PassiveAbilities` (**29 des 32** abilities de relique sont
absentes du seed → « system error » au cast, même verrou que #226) ; et
**`TertiaryAbilityLevel >= 1`** — `IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel`
(foyer UNIQUE des quatre accesseurs de variable) convertit par `Idun.Shared.Level$$ToZeroBasedIndex`,
qui **lève `InvalidOperationException` sur `<= 0`**, et `0` est exactement ce que porte toute
entrée sans relique (`0` = « verrouillé », cf. `Idun.Shared.Level$$CreateValidOrLockedLevel`).
**Pas de borne haute** : le même foyer clampe (`idx >= len` → `len - 1`).
⚠ **L'ORDRE** : `buildNormalizedBC` réécrit le niveau à `targetAbilityLevel` (50) **seulement si
`TertiaryAbility` est déjà non nul** — poser la relique APRÈS la normalisation (`--unit-stat`,
patch du template) laisse le niveau à `0`, verrou armé en silence.

**Le piège central** : `rl_duel build --list-pool` répond à « quels `unitId` normalisent au rank
cible », **pas** à « arrive en bataille AVEC sa relique ». Une gate passée sur le seul pool ne conclut
donc **rien** sur une ability de relique.

⚠ **Corollaire outillage** : `unit_map.py find --ability` lisait 2 voies d'attribution sur 5 et était
**aveugle aux reliques** — c'est ainsi qu'un « 0 unité » a fait classer un effet vivant en DEAD.
Depuis #323 il lit les 5 et **imprime les 4 non couvertes** quand il rend zéro. Un zéro de cet outil
n'est donc plus une preuve de mort — et ne l'a jamais été. Ne jamais conclure « pas de porteur » d'un
seul outil de recensement.

Même forme pour les **MACHINES OF WAR** : leurs `mythicAbilities` (**11**) sont invisibles de toute
autre voie. Les neuf voies d'attribution, mesurées, vivent dans `case-323` §2.

**Pourquoi** : les deux erreurs symétriques ont déjà coûté. Compter les npc comme spawnables envoie un
solver valider une branche impossible ; inversement, ranger un carrier **summon** en « non confrontable »
rabat à tort un port validable-live sur du mirror-offline (vécu le 2026-07-25 sur TwoManTeam/Diminutive,
corrigé en cours de route). Toujours **ventiler les porteurs hero / mow / summon / npc** et dire par
quel chemin chacun arrive en bataille — et pour une relique, **lequel des trois états**.

### DSL-effet vs impératif : c'est l'ARTEFACT NATIF qui tranche (#149)

Avant de porter/migrer un behaviour, demander **« quel est l'artefact natif ? »** :

- Natif = `CreateBehaviour`/`ExecuteBehaviour`/`CreateTrigger`, sélecteur ou formule (un **arbre de nœuds
  `DSLFactory`**, kinds E/T/S/V) → **DOIT être un arbre DSL** ; jamais de logique (ciblage, re-trigger,
  exclusion de trait) recâblée à la main dans un `execute_*` — elle doit **émerger** des nœuds.
- Natif = `Operation.Execute` (mutateur ECS), `Effect.ApplyModification`/`ReverseModification`, pathfinding,
  scheduler, PRNG, pipeline Apply → **RESTE impératif** (mirror fidèle). Une **feuille DSL l'APPELLE**.

**La frontière = le `.Execute` d'une feuille DSL** : au-dessus (structure de l'arbre + sélecteurs/formules) =
déclaratif → DSL ; en-dessous (l'Operation) = impératif → Operation. **Piège** : un helper qui FUSIONNE le
behaviour (`AddEffect`) et le `ApplyModification` de l'effet (ex. `_apply_act_of_faith_stack`) — les SÉPARER
(feuille DSL au-dessus, Operation/effet impératif en-dessous), ne pas wrapper le mélange. Classification par
ability + roadmap des tranches restantes : **`docs/rl/dsl-effect-nodes.md`** (section « Classification »).

### Entrer au registre SANS son masque de ciblage = régression silencieuse (règle de non-régression)

**Une ability qui entre dans `ABILITY_CLASSES` pose son `TARGETING_OPTIONS` DANS LE MÊME COMMIT.**

- **Pourquoi** : `get_invalid_target_reason` / `get_invalid_caster_reason`
  (`engine/runner/abilities/targeting.py`) commencent par
  `options = getattr(ability, "TARGETING_OPTIONS", None)` ; `None` ⇒ **retour 0 immédiat, aucun
  gate**. Le moteur accepte alors des casts que `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget`
  REFUSE (ami/ennemi, cible == caster, caster ayant bougé). La dégradation est **permissive** :
  ni erreur, ni crash — donc invisible en self-play, et c'est exactement le trou qu'un
  entraînement irait exploiter.
- **Dette RÉSORBÉE — re-mesurée le 2026-08-01** (compte re-dérivé du code, pas hérité —
  `python scripts/python/probe_181_targeting_gaps.py`) : `ABILITY_CLASSES` = **98 entrées**,
  **98** portent leur masque, **0 manquante**. Trajectoire des MANQUANTES : 75 → 53 → 40 → **0**,
  et le zéro tient depuis, à travers **quatre** entrées neuves (94 → 98 entre le 2026-07-30 et le
  2026-08-01). Le pendant `ABILITY_ATTACK_TYPE` est lui aussi à **0 manquant**.
  ⚠ **Zéro n'est pas un acquis, c'est un CLIQUET** : ce gisement est le seul que notre propre
  cadence de portage alimente — chaque ability entrée sans son masque le rouvre. La règle
  ci-dessus (masque posé DANS LE MÊME COMMIT) est donc désormais ce qui MAINTIENT le zéro,
  pas ce qui le vise.
  ⚠ Il ne le tenait PAS avant #430 : `probe_181` rendait `0` inconditionnellement — un inventaire
  déguisé en garde-fou, que cette ligne prescrivait pourtant de « faire passer ».
  ⚠ Ces chiffres se périment vite : les re-dériver plutôt que citer cette ligne.
- **Source du masque** : le littéral passé par `<X>Ability$$.ctor` à
  `IdunBattle.Core.Services.TargetingOptions$$.ctor`. **Piège** : l'overload **PRESET + flags**
  (`TargetingOptions..ctor(&opts, &preset, <flags>, 0)`, ex.
  `IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$.ctor`) — le littéral
  visible n'est PAS le masque effectif. Ne renseigner que les masques EFFECTIVEMENT lus ; recopier
  le littéral sans vérifier l'overload produit un masque FAUX, pire que l'absence.
- **Deuxième forme du piège, MESURÉE le 2026-07-27 (PR #126)** : certaines abilities
  **n'appellent AUCUN ctor** — elles recopient les 0x40 octets d'un champ **statique** de
  `TargetingOptions`, et le masque effectif est la constante écrite par
  `IdunBattle.Core.Services.TargetingOptions$$.cctor` à `<preset>+0x28`. Les presets ne sont pas
  interchangeables (`statics+0x168` = `0x4002`, `statics+0x68` = `0x4000`) : sur 10 abilities d'un
  même lot, 9 valaient `0x4002` et JakhalStimms `0x4000`. **Lire ability par ability, ne jamais
  généraliser « toutes les offensives valent X ».**

### Même règle pour `ABILITY_ATTACK_TYPE` — l'autre donnée obligatoire du registre

**Une ability qui entre dans `ABILITY_CLASSES` pose AUSSI son littéral `AbilityAttackType`,
DANS LE MÊME COMMIT.** C'est le pendant exact de la règle ci-dessus, sur l'axe DÉGÂT.

- **Pourquoi** : le garde-fou `probe_120` étape 0 le vérifie — et il **échouait sur `origin/master`**
  le 2026-07-27, sur trois abilities entrées sans leur littéral : `1036 FrenziedFiring` (`d2be96e`),
  puis `1041 BrazierOfHolyFire` et `1116 RadBombardment` (`825f69f`). Les deux dernières n'ont été
  découvertes **qu'au re-jeu après rebase** d'un autre agent : le trou ne s'était vu dans aucune des
  deux PR qui l'avaient creusé.
- **Même signature de dégradation** que `TARGETING_OPTIONS` : ni erreur ni crash, et **le seul
  gisement que notre propre cadence de portage aggrave** — chaque nouveau port l'alimente.
- **Comment** : relire le littéral au décompilé (jamais le déduire du nom de l'ability ni du profil
  de dégât).

!include .claude/skills/tacticus-re-port/SKILL.md

## Agents — invariants (valent AUSSI si tu es toi-même un agent qui en lance un)

Les solveurs disposent de tous les outils : **un agent lance couramment un `re-expert`**. Ces
règles ne sont donc pas réservées à l'orchestrateur — elles s'appliquent à quiconque dispatche.

1. **Toujours `isolation: "worktree"`**, sans exception. Sans elle, l'agent partage le working
   directory et peut corrompre l'arbre de son appelant (déjà vécu : un `return /float(...)`
   laissé dans `engine/utilities/tile.py` cassait tout l'import `engine`).
2. **Ne JAMAIS passer `model:`** à l'invocation. Le paramètre écrase le frontmatter et retombe
   sur la fenêtre 200 K — l'enum d'invocation ne sait pas exprimer le suffixe `[1m]`.
3. **Aucune étape 0 : un worktree frais est RUNNABLE par son seul checkout** (depuis le
   2026-07-26). `data/` est VERSIONNÉ et ne contient que des ENTRÉES — `symbols/`,
   `boards/`, `seed-bc.json`, `i2_en.json`. La junction vers l'arbre principal est
   SUPPRIMÉE : chaque agent lit les entrées de SON commit, et écrit ses sorties dans
   SON `logs/` (gitignoré), qui **meurt avec son worktree**. Corollaire : plus de
   discipline « nom unique par agent » sur les state-files, et un `worktree remove`
   ne peut plus rien détruire de partagé. **Rien de produit par un run ne va dans
   `data/`** — s'il y atterrit, il apparaît dans `git status`, et c'est le garde-fou.
   Deux gardes le tiennent (#349, après **25** sites trouvés sur **19** fichiers) :
   `probe_273 --only-scan` **étape 0c** rougit si un chemin `data/<x>` construit dans
   `scripts/python/**` ne désigne pas une entrée VERSIONNÉE, et `rl_duel --state-file` /
   `catalog_inject --out` **refusent** (rc 2) un chemin sous `data/` — ce second garde
   couvre les appelants hors Python, que le balayage ne voit pas.

   ⚠ **TROISIÈME catégorie, qu'un worktree ne verra JAMAIS** (mesurée par #273) : les
   artefacts écrits par un processus **hors du checkout** — le host Node (`frida/data/ai-traces`,
   `rl-batches`, `meta`) — ou par l'utilisateur (`.env`). Ce ne sont ni des entrées versionnées
   ni des sorties du run ; ils vivent dans l'arbre principal, et c'est correct. L'invariant ne
   promet pas qu'un worktree les voie. Ce qu'il exige, c'est qu'un lecteur **DISE qu'il ne les
   voit pas au lieu de rendre un zéro** : toute lecture d'une entrée gitignorée passe par
   `scripts/python/host_inputs.py` (tri-état `null` = pas mesuré / `[]` = mesuré et vide).
   Symptôme si on l'oublie : un
   balayage rend `0 fichier` et se lit comme « rien à signaler » — mesuré, `rl_ingest --all`
   ingérait **zéro** batch depuis un worktree, sans erreur.

   ⛔ **JAMAIS DE JUNCTION (ni lien symbolique) depuis ton worktree vers l'arbre principal.**
   Pas pour `node_modules`, pas pour `frida/hooks/scratch`, pas pour `data/` — pour rien.
   **Pourquoi** : sous Windows, une suppression récursive forcée (`git worktree remove --force`,
   `Remove-Item -Recurse`) **SUIT le point de reparse et vide la CIBLE**. Mesuré le 2026-07-31 :
   `frida/hooks/scratch` (67 modules, gitignorés, jamais versionnés, aucune copie ailleurs) a été
   détruit dans l'arbre principal par cette voie, et `frida/node_modules` amputé. Le bundle est
   devenu inconstructible. Un agent qui a « nettoyé sa junction avant de rendre la main » ne prouve
   rien : la destruction a lieu au `worktree remove`, après son départ.
   **Si un build te manque une dépendance** : `npm ci` dans TON worktree (`package-lock.json` est
   versionné, ~10 s) — jamais un lien vers l'arbre du voisin. Si une **source** te manque, c'est
   qu'elle est gitignorée à tort : dis-le, ne la contourne pas. Le cliquet
   `probe_365_versioned_imports_gitignored.py` rougit sur cette faute (un fichier versionné qui
   importe statiquement une cible gitignorée ou absente).
4. **⛔ Ne (ré)injecter NI redémarrer le host TOI-MÊME, jamais.** Ce geste stoppe la session
   Frida et casse le harnais des autres agents. Il appartient à l'orchestrateur, qui dispose
   d'une procédure sûre (mode DRAIN). Si ton travail exige un reinject — un correctif
   `frida/hooks/*` à activer, un capteur neuf à poser — **livre le code et DIS-LE dans ton
   rapport** : la fenêtre sera planifiée. Tout le reste (mêmes fichiers, mêmes sujets, RPC
   concurrents, runners) est libre — un worktree est figé au commit de lancement, donc les
   éditions de l'appelant ne peuvent pas le perturber.

   Corollaire — **si un build de runner te revient en `503 runner creation paused`** : c'est une
   fenêtre de maintenance volontaire, **de quelques minutes**, pas une panne. Tu **ATTENDS, tu ne
   t'arrêtes PAS**. Dans cet ordre :

   1. **Commite immédiatement** ce que tu as, même partiel, même non validé. Un agent qui rend la
      main avec un worktree **PROPRE** le perd — il est auto-supprimé, et sa reprise repart
      silencieusement dans l'**arbre principal**, où il éditerait `master`.
   2. **Dispose TES runners** (jamais ceux des autres). C'est ce qui fait converger la fenêtre :
      tant qu'un runner traîne, la maintenance attend après toi.
   3. **Attends la réouverture** : `GET /api/admin/drain` jusqu'à `enabled == false`, en espaçant
      les sondages (pas de boucle serrée de retries sur le build lui-même — chaque refus est
      compté et n'avance à rien). Puis **reprends ton travail là où tu en étais**.
   4. Si la fenêtre dépasse largement l'échelle de la minute, **alors** seulement rends ton état :
      ce que tu as établi, ce qui reste à confronter, et **le montage exact** que tu comptais
      jouer — c'est ce qui te fera repartir vite quand je te reprendrai.

   Et dans tous les cas : **ne conclus RIEN de ce refus.** Ce n'est ni un « porteur non
   confrontable », ni un « régime inatteignable », ni un « montage impossible ». Écris
   « NON CONFRONTÉ — fenêtre DRAIN ».
5. **Une modif Python `engine/**` n'exige NI rebuild NI reinject** : ce code tourne dans le
   process pytest/probe et parle au runner par RPC. Seul `frida/hooks/*` vit dans Frida.
6. **Le worktree part de `origin/master`** — ni de la branche courante, ni des changements non
   commités. Pour qu'un agent voie du travail en cours : le commiter et le POUSSER d'abord.
7. **Un agent mis en pause avec un worktree PROPRE le PERD** — il est auto-supprimé (règle
   « auto-cleaned if unchanged »), et la reprise par `SendMessage` le fait repartir dans
   l'**arbre principal**, silencieusement : l'invariant 1 saute et l'agent édite `master`.
   Cause racine : une pause est rapportée `completed` — le harnais ne distingue pas « fini,
   rien à garder » de « en pause, n'a PAS ENCORE écrit ». Vise donc le profil « RE d'abord,
   édition ensuite » (un `re-expert`/`opus-solver` qui lit du décompilé 20 min avant sa
   première édition). **Parade, mesurée le 2026-07-26 : faire écrire l'agent TÔT** — une
   édition réelle, ou à défaut un fichier jetable `git add`-é. Un worktree SALE survit
   intégralement à la pause (cwd, index, branche, `master` non contaminé). À défaut, avant
   toute reprise d'un agent qui va écrire : lui faire vérifier `pwd` +
   `git rev-parse --show-toplevel`, et relancer un agent frais s'il n'y est plus.
   NB : dans `git worktree list`, `locked` = agent EN COURS d'exécution, **pas** « worktree
   conservé » — un agent arrêté mais sale apparaît `unlocked` et bien présent.

Le reste de la conduite de campagne (pipeline de dispatch — `opus-solver` et lui seul, workflow de
livraison par PR, reprise d'un agent par `SendMessage`, exploitation de la plateforme,
migration au changement de build) vit dans le skill **`tacticus-orchestration`**, chargé à la
demande — il ne sert qu'à l'orchestrateur et n'a pas à peser sur le contexte de chaque agent.

## Documentation détaillée

!include .claude/skills/tacticus/references/rpc-api.md
!include .claude/skills/tacticus/references/runner.md

<!-- TODO références à (ré)écrire contre le code actuel (les drafts d'avril
     dans .claude/worktrees/agent-a0e45617/ sont périmés) : frida-host.md,
     game-architecture.md, decompilation.md, ai-engine-audit.md, knowledge.md.
     Ne pas !include tant qu'ils n'existent pas dans ce tree (résolution à vide). -->

