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
  (`{id, kind, spawnPointsSet, board}`).
- **Injecter le board choisi** : `rl_duel build --board <id>` (id fixe, swap à la normalisation) ou
  `--board-pool <kind>` (aléatoire seedé, filtré aux boards avec assez de spawns/côté + MoW-capable si
  un MoW est en jeu). Mutuellement exclusifs.

### 2bis. TROUVER un board qui porte un terrain donné (recette générale)

Ne PAS deviner ni hardcoder une liste d'ids : **énumérer les 779 dumps + compter le terrain** avec
`board.py`. C'est LA façon de débloquer une validation de mécanique board-dépendante (couverture, trench,
LOS, eau…) — l'ancien blocage « aucun seed n'a de cover » venait de n'avoir jamais scanné le pool.

```python
# depuis scripts/python ; python (pas py) ; ASCII only
import json; from pathlib import Path
import board as B, rl_collect_batch as R
WANT = "DryBush"          # <- le TileId cherche (cf. inventaire ci-dessous)
rows = []
for kind in ("pvp", "syncPvp", "global"):
    d = R.BOARDS_DIR / kind
    for p in sorted(d.glob("*.json")) if d.exists() else []:
        dump = json.loads(p.read_text(encoding="utf-8"))
        bd = B.Board({"Board": dump["board"], "SpawnPointSetIndex": dump.get("spawnPointsSet", 0)})
        n = bd.terrain_counts().get(WANT, 0)
        if n: rows.append((dump["id"], kind, n))
for r in sorted(rows, key=lambda x: -x[2])[:8]: print("id=%-10s kind=%-7s %s=%d" % (r[0], r[1], WANT, r[2]))
# puis: rl_duel build --board <id>   (board.py <bc.json> pour la carte ASCII + spawns)
```

**Inventaire terrain (scan des 779 dumps, build `gqfc5mff6c`)** — `TileId` → nb de boards qui en portent :
`Grass`(779), `Block`(662, LOS/bloque l'entree), `Swamp`(461, malus mvt), **`DryBush`(455)**,
`Water`(307), `Bridge`(287), **`Trench`(77)**, `BrokenIce`(40), `FirstAid`(25), `HulkWall`(17),
`HulkDoor`(15). Le terrain vit dans le `TileId` de la BC — **pas besoin d'un RPC tile-ability** pour le
lire (il est aussi projete live via `projectTile.tileDefId`, cf. `match-state.ts`).

**Mapping terrain → mécanique** (confirmé) : **`DryBush` = LightCover** (couverture legere : l'unite SUR
la tuile recoit **-2 coups des attaques ranged multi-hit, min 1** ; effet 1013 pose par `LightCoverAbility`
de tuile, gate compute-time = cible ACTUELLEMENT sur tuile cover) ; **`Trench` = modificateur de DEGAT
positionnel** (`CalculateAttackerModifiersForPrediction @181000590`, famille RangedInMelee, cf. #61 —
PAS un reducteur de coups). Les autres (`Water`/`Bridge` = LOS/mvt, `BrokenIce`, `FirstAid`, `HulkWall`/
`HulkDoor`) : mecanique par gameconfig/RE au besoin.

**Boards riches pour VALIDER** (dérivés du scan, pas hardcodés) : couverture — `C4_09`(pvp, 17 DryBush),
`C1_25`(pvp, 15) ; trench — `C2_19`(global, 17), `C2_20`(13) ; **les DEUX à la fois** —
`SyncPvp_Arctic_06`(DryBush 7 + Trench 13). L'arène par défaut `MC1_67` a déjà 3 DryBush + 4 Swamp.

## 3. Discipline runner — SYSTÉMATIQUE, sans condition

- `python` (PAS `py`), depuis `scripts/python`, **stdout ASCII only** (cp1252).
- **`--state-file` propre + `--runner` explicite** sur les commandes de pilotage — ne JAMAIS raisonner
  « je suis seul ».
- **Coexistence par défaut** : un build ne touche jamais les runners frères ; il ne dispose que le
  runner enregistré dans SON `--state-file`. Cap dur `MAX_RUNNERS=10` → au cap le build **REFUSE**
  (dispose TES runners, jamais ceux des autres).
- **Dispose tes runners en fin de passe** (`disposeRunner({runnerId})` ; `listRunners` pour vérifier
  l'atelier vide). Exclusifs : traces globales (`scorer*`, `aiUtilityTrace*`…) + ops de session.
