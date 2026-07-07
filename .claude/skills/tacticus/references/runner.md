# Lancer un runner (source unique)

> **Doc canonique du LANCEMENT DE RUNNER.** Orchestrateur (via `!include` CLAUDE.md), agent
> `validator` et agent `re-expert` pointent TOUS ici — ne pas dupliquer ces règles ailleurs.

## 0. Warmup d'abord — INCONDITIONNEL

Après tout (re)inject / host-restart / session froide, **AVANT tout RPC/build/probe** :
`warmupGameSingletons({ force: true })` (autonome — pilote la nav campagne lui-même, **aucun clic
humain**). Sans ça : caches `MethodInfo*` Frida-side vides + init IL2CPP non amorcée → build/RPC
crashent (`0x2c`). Un probe qui « marche » sans warmup ne prouve rien (le jeu était déjà warm d'une
nav précédente). Le warmup est un **process standalone** : ne pas raisonner sur ses internals, ni
bâtir un runner « depuis l'état qu'il a capturé » — un runner se construit depuis une **seed BC**
(§1), indépendamment du warmup.

## 1. Construire un runner — `rl_duel build`

**Seule voie.** Construit un runner ISOLÉ depuis la **seed BC sur disque**, le **déploie**
(`initAndStart`), et rend des units observables. C'est ce qu'utilisent la conftest (`build_runner`) et
les agents.

```bash
python rl_duel.py build --seed <s> --state-file <fichier propre> [options]
```

Options utiles (build) :
- `--roster N` (défaut 5) : taille des rosters au tirage ALÉATOIRE seedé.
- `--p-units "id1,id2,..."` / `--a-units "..."` : rosters EXPLICITES team 1 (moi) / team 2 (adverse).
  Les ids doivent être dans le **pool spawnable** du rank (`--list-pool` pour le voir). Team 1 est
  placée aux spawn points du board dans l'ordre → positions déterministes.
- `--rank R` (défaut 17) : niveau/pool (`_load_unspawnable` filtre les ids qui throw au spawn).
- `--board <id>` / `--board-pool <pvp|syncPvp|global>` : **choix du board** (cf. §2).
- `--p-mow/--a-mow/--mow` : Machines of War. `--crit/--crit-target/--block-target/--hp-target` :
  restaurent des stats de combat sur les templates (crit/block/kill déterministe).

Puis piloter : `rl_duel.py view|act|play|aiturn|abilities ...` (lisent le `runnerId` du `--state-file`),
ou `engine_validate.py --runner <id> --steps N` pour l'agreement. Chaque `build` sur un `--state-file`
ne dispose QUE le runner enregistré dans CE fichier (les frères sont intouchés — cf. §3).

## 2. Choix du board (mécaniques board-dépendantes)

Élévation, trench, couverture/LOS, slot MoW **dépendent du board**. Le **choisir**, ne pas le subir :

- **Caractériser STATIQUEMENT** (offline, sans live) via `board.py` : parse `BC.Board.Tiles[].{TileId,
  Elevation, ForceUnplayable}` + `SpawnPointSets` → élévation, terrain, jouabilité, spawns, LOS. Les
  boards dumpés (par `dumpPvpAndSyncBoards`) sont dans `data/boards/{pvp,syncPvp,global}/<id>.json`
  (`{id, kind, spawnPointsSet, board}`). → filtrer le pool pour l'id qui remplit la condition
  (ex. **surplomb = tous les pvp** ; **trench** = `C3_46/C3_47/C3_59/MC3_40` ; **block-dense** =
  `C3_06/C3_31` ; **MoW** = tous les pvp).
- **Injecter le board choisi** : `rl_duel build --board <id>` (id fixe, swap à la normalisation) ou
  `--board-pool <kind>` (aléatoire seedé, filtré aux boards avec assez de spawns/côté + MoW-capable si
  un MoW est en jeu). Mutuellement exclusifs.

## 3. Discipline runner — SYSTÉMATIQUE, sans condition

- `python` (PAS `py`), depuis `scripts/python`, **stdout ASCII only** (cp1252).
- **`--state-file` propre + `--runner` explicite** sur les commandes de pilotage — ne JAMAIS raisonner
  « je suis seul ».
- **Coexistence par défaut** : un build ne touche jamais les runners frères ; il ne dispose que le
  runner enregistré dans SON `--state-file`. Cap dur `MAX_RUNNERS=10` → au cap le build **REFUSE**
  (dispose TES runners, jamais ceux des autres).
- **Dispose tes runners en fin de passe** (`disposeRunner({runnerId})` ; `listRunners` pour vérifier
  l'atelier vide). Exclusifs : traces globales (`scorer*`, `aiUtilityTrace*`…) + ops de session.
