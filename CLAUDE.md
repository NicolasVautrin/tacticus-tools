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
- `data/` — dumps IL2CPP, gameconfig, boards — gitignored, **à une exception près** :
  `data/symbols/<HASH>/` (la table de symboles) est VERSIONNÉE.
- `sources_win/` — décompilation Ghidra de `GameAssembly.dll` — gitignored
- `STATUS.md` — état d'avancement vivant du projet

## Cible Windows

- **Exe** : `C:\Users\nicolasv\AppData\Local\tacticus\games\<HASH>\Tacticus.exe`
- **GameAssembly.dll** : ~60 MB, IL2CPP AOT (Unity 6000.3.8f1)
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

## Workflow RL — runner isolé

> **Le LANCEMENT DE RUNNER est centralisé dans `.claude/skills/tacticus/references/runner.md`**
> (inclus ci-dessus, pointé par les agents `validator`/`re-expert`) : warmup obligatoire, voie
> `rl_duel build`, choix de board (`--board`/`--board-pool` + `board.py`), discipline runner.
> C'est LA source unique — ne pas dupliquer ces règles ici.

Pour entraîner un agent RL / valider le moteur sans toucher au battle in-game, on monte un
**runner isolé** depuis une **seed BC sur disque** (`rl_duel build`), déployé et pilotable à
volonté sans casser le jeu actif. Rappel des deux points les plus violés (détail : `runner.md`) :

1. **Warmup une fois par session Frida** (après chaque inject/reinject), AVANT tout RPC/build :
   `warmupGameSingletons({ force: true })`. **Autonome — aucun clic humain** : pilote la nav
   (campagne → node → play → capture ctor) et force l'init des singletons/classes.
   Claude l'appelle directement après chaque (re)inject et NE demande JAMAIS de cliquer une battle.
   Le cycle **s'arrête à la capture** et laisse le jeu sur l'écran de bataille (`stopAfterCapture`,
   défaut) : c'est l'état ATTENDU, pas un warmup incomplet. Les runners isolés ne consomment
   pas l'écran campagne. Pour l'écran rendu propre malgré le risque de wedge :
   `warmupGameSingletons({ force: true, stopAfterCapture: false })`.

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
- **Commit** : `data/` (SAUF `data/symbols/`, qui est versionnée EXPRÈS),
  `frida/dist/`, `server/`, `logs/`, `frida/assets/raw/`, `sources_win/`.
  (`hooks-legacy/` EST versionné — l'ancienne mention ici était fausse.)

## Protocole RE + portage (DÉCISION + COMBAT)

Le protocole complet — recon du kit, RE fidèle (décompilé = vérité, jamais l'expérience live),
mirror 1:1 des fonctions natives nommées, décomposition par étage (jamais fitter un scalaire),
validation des DEUX faces (décider ≠ exécuter) — vit dans le skill `tacticus-re-port`
(invocable via `/tacticus-re-port`), inclus ci-dessous. C'est LA source unique de cette doctrine.

### Gate de confrontabilité : HERO / MoW / SUMMON — jamais NPC

Avant de porter une mécanique (ou d'exiger un datapoint live), établir **qui la porte** et si ce
porteur est atteignable en bataille. Trois catégories seulement comptent, et les chemins de
vérification sont **distincts** :

- **HERO / MACHINE OF WAR** → présence **directe** dans `python scripts/python/rl_duel.py --list-pool`
  (rank courant). C'est **la seule porte valable** — surtout pas `kind == lineup` de gameconfig,
  qui ment.
- **SUMMON** → compte **aussi**, **même absent de `--list-pool`**. On l'amène en bataille en spawnant
  son **summoner** (qui, lui, doit être dans le pool) : le summon apparaît dans l'équipe du summoner
  et agit dès son apparition. **Ne jamais conclure « non confrontable » d'un carrier summon.**
- **NPC** → hors-jeu, jamais confrontable. Un item dont **tous** les porteurs sont npc n'est pas
  « bloqué », il est **NON PERTINENT** : ne pas y brûler d'agent (sauf demande explicite de mirror +
  toggle offline).

**Pourquoi** : les deux erreurs symétriques ont déjà coûté. Compter les npc comme spawnables envoie un
solver valider une branche impossible ; inversement, ranger un carrier **summon** en « non confrontable »
rabat à tort un port validable-live sur du mirror-offline (vécu le 2026-07-25 sur TwoManTeam/Diminutive,
corrigé en cours de route). Toujours **ventiler les porteurs hero / mow / summon / npc** et dire par
quel chemin chacun arrive en bataille.

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
- **Dette MESURÉE** : `ABILITY_CLASSES` = 76 entrées, **1 seule** (`WaaaghAbility`, 1058) porte son
  masque. Le compte est passé de 60 à 75 manquants : c'est le SEUL gisement que notre propre
  cadence de portage aggrave, chaque nouveau port l'alimentant.
- **Source du masque** : le littéral passé par `<X>Ability$$.ctor` à
  `IdunBattle.Core.Services.TargetingOptions$$.ctor`. **Piège** : l'overload **PRESET + flags**
  (`TargetingOptions..ctor(&opts, &preset, <flags>, 0)`, ex.
  `IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$.ctor`) — le littéral
  visible n'est PAS le masque effectif. Ne renseigner que les masques EFFECTIVEMENT lus ; recopier
  le littéral sans vérifier l'overload produit un masque FAUX, pire que l'absence.

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
4. **⛔ Ne (ré)injecter NI redémarrer le host tant qu'un autre agent tourne.** C'est le SEUL
   geste réellement proscrit : il stoppe la session Frida et casse le harnais des autres. Tout
   le reste (mêmes fichiers, mêmes sujets, RPC concurrents, runners) est libre — un worktree
   est figé au commit de lancement, donc les éditions de l'appelant ne peuvent pas le perturber.
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

Le reste de la conduite de campagne (pipeline de dispatch, routage opus/fable, workflow de
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

