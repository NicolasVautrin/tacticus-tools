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

**Seule voie.** Construit un runner ISOLÉ depuis la **seed BC sur disque** + un **board dumpé**, le
**déploie** (`initAndStart`), et rend des units observables. C'est ce qu'utilisent la conftest
(`build_runner`) et les agents.

> **⚠ ARTEFACTS LIVE À RÉGÉNÉRER (per-hash, PURGEABLES — cf. #159).** Le harnais lit DEUX artefacts sous
> `data/` (entièrement **gitignore** → JAMAIS versionnés, effacés par tout ménage de `data/` : `git clean
> -fdx`, nettoyage disque) :
> - `data/seed-bc.json` — le **seed BC template** (skeleton Players/Utilities/mode), lu par `_load_seed_bc`.
> - `data/boards/{pvp,syncPvp,global}/<id>.json` — les **~800 board dumps**, lus par `_load_board_dump`.
>
> S'ils manquent, `rl_duel build` échoue **franchement** (erreur actionnable, plus de skip vert silencieux).
> **Régénère-les en UNE commande** (session warmée) : `python dump_boards.py` (capture live via
> `dumpBattleConfig` + `dumpPvpAndSyncBoards`). **À REFAIRE au changement de hash du build.**

```bash
python dump_boards.py                                    # (re)génère seed-bc.json + data/boards/ (une fois par hash)
python rl_duel.py build --seed <s> --board <id> --state-file <fichier propre> [options]
```

Options utiles (build) :
- `--roster N` (défaut 5) : taille des rosters au tirage ALÉATOIRE seedé.
- `--p-units "id1,id2,..."` / `--a-units "..."` : rosters EXPLICITES team 1 (moi) / team 2 (adverse).
  Les ids doivent être dans le **pool spawnable** du rank (`--list-pool` pour le voir). Team 1 est
  placée aux spawn points du board dans l'ordre → positions déterministes.
- `--rank R` (défaut 17) : niveau/pool (`_load_unspawnable` filtre les ids qui throw au spawn).
- `--board <id>` / `--board-pool <pvp|syncPvp|global>` : **choix du board — OBLIGATOIRE** (le seed BC est
  un skeleton dont le board par défaut n'a pas de spawns 5v5 fiables ; build sans board = refus). Cf. §2.
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
  (`{id, kind, spawnPointsSet, board}`). **Absents ? → `python dump_boards.py` les régénère** (cf. §1,
  artefacts per-hash purgeables).
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
positionnel** (`IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction`, famille RangedInMelee, cf. #61 —
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

## 4. Piloter une bataille PAS-À-PAS (scénario contrôlé, sans l'IA)

Pour reproduire un cas précis (cast d'une ability donnée à une position choisie, confront d'un capteur…),
on pilote le runner action-par-action. Le runner est un **bac à sable** : **`applyAction` n'applique QU'UNE
action et ne fait PAS jouer l'IA** (le tour ne passe pas tant qu'on ne le décide pas) — on garde donc la
main totale sur la géométrie.

**Recette vérifiée (bout-en-bout)** — ex. driver un cast GetEmRuntz d'orksRuntherd à portée d'ennemis :

1. **Warmup** (§0), puis **build** (§1) avec rosters EXPLICITES + board choisi (`--p-units`/`--a-units`
   depuis le **pool spawnable** — `--list-pool` d'abord ; attention, les **summons** type `orksBoy`/`grot`
   NE sont PAS dans le pool, ce sont des unités invoquées en combat).
2. **Recon des actifs** : `abilities --unit <U> [--ability <id>]` → pour chaque ability, `now[..]` (castable
   **sans bouger**), `+move[..]` (castable **après déplacement** ce tour), `∅` (no-op certain). `moves --unit
   <U>` = tuiles de déplacement légales (carte ASCII). `view` = carte décision complète.
3. **Placer** l'unité : `act move --unit <U> --to C,R`. Ré-`abilities` pour confirmer que la cible/le cast
   voulu passe de `+move` à `now`.
4. **Armer** le capteur voulu (tracer/probe) via `POST /api/scripts/<sid>/rpc` (body `{method, args, timeout}`)
   — ex. `dslTraceArm(ns, cls, n)`. Le `sid` = la session `running` (auto-résolue par `rl_duel`, ou
   `/api/admin/status`).
5. **Déclencher** l'action ciblée : `act ability --caster <U> --target <T> --ability <id>` (cible ENTITÉ),
   ou `act ability --caster <U> --to C,R --ability <id>` (cible **hex libre** : summons sur tuile, murs,
   marquage). La cascade native complète est imprimée (events + spawns + réactions adverses).
6. **Lire** le capteur (ex. `dslTraceLastCast`), **désarmer** (`dslTraceDisarm`).
7. **Dispose** (§3).

**Contrôle des DEUX teams** : `applyAction` ne vérifie PAS la propriété du `casterId`/`unitId` — je peux
donc **piloter les unités adverses aussi** (bouger/attaquer/caster n'importe quelle unité des 2 teams). Le
flag `ctrl` de la carte ne sert qu'à l'affichage, pas à brider l'action. ⇒ pour monter une géométrie exacte
(ennemi adjacent, cible à une case précise…), **drive les positions des 2 camps** plutôt que subir les
spawns (cf. mémoire « drive positions, don't blame geometry »).

**Fin de tour à la demande** : `act endturn` clôt le tour de la **team courante** (bascule à l'autre camp) —
à déclencher **quand je veux**, pas besoin d'épuiser les activations. `act finish --unit <U>` termine juste
l'activation d'UNE unité (sans finir le tour). Pour laisser l'IA native jouer un tour complet d'une team à
la place (au lieu du pilotage manuel), `aiturn`. Combiner librement : pilotage manuel d'un camp + `endturn` +
`aiturn` de l'autre, dans l'ordre voulu.
