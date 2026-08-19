# Lancer un runner (source unique)

> **Doc canonique du LANCEMENT DE RUNNER.** Orchestrateur (via `!include` CLAUDE.md), agent
> `validator` et agent `re-expert` pointent TOUS ici — ne pas dupliquer ces règles ailleurs.

## 1. Construire un runner — `rl_duel build`

**Seule voie.** Construit un runner ISOLÉ depuis la **seed BC sur disque** + un **board dumpé**, le
**déploie** (`initAndStart`), et rend des units observables. C'est ce qu'utilisent la conftest
(`build_runner`) et les agents.

> **⚠ ARTEFACTS LIVE À RÉGÉNÉRER (per-hash — cf. #159).** Le harnais lit DEUX artefacts sous `data/`
> — **VERSIONNÉ** depuis `f467e64` : `data/` ne porte que des **ENTRÉES**, les **sorties** de run vont
> dans `logs/` (et `rl_duel --state-file` REFUSE un chemin sous `data/`, #349) :
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
- `--unit-stat "VisualId:Champ=Valeur;…"` : patch **PER-UNIT** de `BC.Units` (valeur JSON, répétable).
  Le seul levier qui produit un ÉCART entre deux unités du même camp — cf. §3 « Crafter l'état ».

Puis piloter : `rl_duel.py view|act|play|aiturn|abilities ...` (lisent le `runnerId` du `--state-file`),
ou `engine_validate.py --runner <id> --steps N` pour l'agreement. Chaque `build` sur un `--state-file`
ne dispose QUE le runner enregistré dans CE fichier (les frères sont intouchés — cf. §3).

### 1bis. Porteur ABSENT du seed BC → `catalog_inject.py` (jamais « non confrontable »)

Le seed BC est la capture d'UNE bataille : son catalogue ne contient que les unités possédées ce
jour-là. **17 unités `lineup` du gameconfig n'y sont pas** (les 4 Votann, `thousDaemonPrince`,
`necroReanimator`, `darkaStormSpeeder`, …) → `--p-units <id>` répond « hors pool ». Ce n'est PAS
une limite du jeu : le catalogue se complète.

```bash
python catalog_inject.py --missing                        # qui manque
python catalog_inject.py --units <ids> --out <absolu>.json # seed BC augmenté (le partagé est intact)
python rl_duel.py build --seed-bc <absolu>.json --board <id> --p-units <id> [--p-mow <id>]
```

**Deux catalogues, pas un** : `BC.Units` (l'unité) ET `BC.Abilities` (Variables/Constants de
chaque ability). Injecter le premier seul donne un porteur qui se déploie, s'affiche… et **faute
au cast** (« system error » = exception managée : config d'ability vide →
`AbilityConfiguration$$GetVariableForLevel` lève). `catalog_inject` fait les deux. Détail,
dérivations et validation : `docs/rl/case-92-catalog-injection.md`.

**Depuis un test/probe Python** : `catalog_inject.write_augmented_seed_bc(<out>, [<ids>])` — jamais
un `copy.deepcopy` d'une entrée `Units` existante avec les ids réécrits. Ce clone à la main ne pose
QUE `BC.Units`, donc il rejoue exactement le « system error » ci-dessus ; il porte en plus les STATS
de l'unité clonée, ce qui fausse toute ability dont le dégât lit `StatAmount(Attack)` (#226).

**La cause SYMÉTRIQUE, à la migration de build (#254)** : une config d'ability *présente mais
PÉRIMÉE*. Le seed BC est capturé sur UN build, `gameconfig.py` lit le fichier VIVANT ; une MAJ qui
AJOUTE une variable/constante à une ability laisse la capture en arrière, et
`AbilityConfiguration$$GetStringConstant` LÈVE sur clé absente → même « system error », **au
déploiement** si la clé est lue à la construction du trigger d'un PASSIF (mesuré :
`ultraInceptorSgt`/`ShockAssault`, tout build dont un roster le contient tombait). `_load_seed_bc`
re-synthétise donc `BC.Abilities` depuis le gameconfig courant à chaque chargement
(`catalog_inject.refresh_ability_configs`) — no-op mesuré sur 273/277 entrées. Détail :
`docs/rl/case-254-build-migration-blockers.md`.

> ⚠ **Ce rattrapage ÉCRASE ce qu'une fixture vient d'écrire dans `BC.Abilities`, sans un mot** — et
> sa 2ᵉ boucle **COMBLE** une config volontairement absente. Deux fautes mesurées : le régime
> discriminant de #369 n'a jamais été joué (`LightImUp.minDmg` écrit `20000`, relu `831`), et le bras
> négatif de `probe_226` rendait `ok=True` comme ses témoins. **Toute fixture qui patche un seed BC
> sur disque appelle `probe_380_seed_bc_patch_survival.assert_survives(<path>)` après l'écriture** ;
> les deux clés opt-in du sidecar `<seed-bc>.pins.json` sont `pinnedAbilityConfigs` (valeur patchée)
> et `withheldAbilityConfigs` (absence délibérée). Un patch **en mémoire** (`bc = _load_seed_bc(None)`
> PUIS patch) survit, lui : c'est l'ORDRE qui décide. Détail :
> `docs/rl/case-375-capteur-triggered-muet.md` §2 et `docs/rl/case-380-recensement-patchs-seed-bc.md`.

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
  runner enregistré dans SON `--state-file`. Cap dur `MAX_RUNNERS` → au cap le build **REFUSE**
  (dispose TES runners, jamais ceux des autres).
- **Un `runnerId` disposé n'est JAMAIS réattribué** (compteur monotone côté hooks — `case-377`).
  Piloter un id périmé est donc **refusé franchement** (`runner N not found`), jamais silencieux : ça
  ne pollue le runner de personne. ⚠ **Ce n'est pas une dispense de `--state-file`** — l'id littéral
  d'un runner **vivant** d'autrui, lui, PASSE (aucun contrôle d'`owner`).
- **Après un reinject, repars sur un `--state-file` PROPRE.** La garantie ci-dessus vaut **par
  session Frida** : le compteur repart de `0` alors que les state-files survivent sur disque, et
  ce sont les **PETITS** numéros le danger (ids croissants — `runnerId=2` a mis moins de dix
  minutes à passer de libre au pytest d'un autre agent, mesuré). Depuis `#379`, `rl_duel` estampe
  le state-file de l'identité de session au `build` et **REFUSE en rc 2** (`MISMATCH`, ou pas
  d'estampille sur un fichier antérieur au démarrage de la session) ; un fichier sans estampille
  mais écrit pendant la session courante passe en **AVERTISSANT** — c'est « non vérifiable », pas
  « OK ». Détail : `case-379`.
- **⚠ UN `SKIPPED` N'EST PAS UN SUCCÈS.** Au cap saturé, le build échoue → `pytest.skip` → une passe
  entière rend `sssssss`, des `s` qui *ressemblent* à du vert alors que **RIEN n'a été validé**
  (mesuré le 2026-07-25 : 7/7 tests d'un agent skippés, cap 10/10 pris par un autre). **Après CHAQUE
  passe pytest, lis le compte de skips ET leur raison** ; si elle contient `runner cap reached`, la
  passe est NULLE — refais-la après avoir libéré des slots. Ne conclus JAMAIS « pas de régression »
  sur une passe dont tu n'as pas lu les raisons de skip. (Depuis `f880be1`, `conftest.py` attend
  qu'un slot se libère puis **échoue franchement** — mais un agent lancé sur une base antérieure,
  ou un test qui fait son propre `rl_duel build`, garde l'ancien comportement.)
- **Libère tes runners AU FIL DE L'EAU**, pas en fin de passe : les tenir tous jusqu'au teardown
  affame les autres agents (c'était la cause du cap saturé ci-dessus).

### ⚠ TU AS LA MAÎTRISE TOTALE DU SETUP DE TEST — « pas atteignable » est presque toujours FAUX

La bataille n'est pas un donné qu'on subit : **tu la FABRIQUES**. Tu choisis qui est présent, à
quel rang, avec combien de PV, sur quel plateau, et tu déplaces les unités où tu veux avant de
mesurer. Une condition rare EN JEU NATUREL n'est PAS une condition coûteuse à TESTER — c'est
exactement ce que le runner isolé existe pour produire.

Leviers **réels** de `rl_duel.py build` (vérifiés dans l'argparse, ne pas en inventer d'autres) :

| besoin | levier |
|---|---|
| qui est là, dans quel camp | `--p-units` / `--a-units`, `--p-mow` / `--a-mow`, `--roster` |
| faire DURER la bataille (saturer un cap de summons, voir N tours) | `--hp-target` (ennemi), `--hp-player` (mon camp) — force `Health` ET `RemainingHealth`, **et met `Armor`/`FixedArmor` à 0**. ⚠ **Piège de mesure** : forcer les PV supprime donc SILENCIEUSEMENT l'étage armure (mesuré : `adeptMorvenn` 2411 → 0, `necroWarden` 2008 → 0), et avec lui tout régime où la branche perçage du plancher mordrait. Pour mesurer l'armure, ne pas forcer les PV |
| TUER à la demande — en particulier une unité **INVOQUÉE** | `--dmg-target` : force le stat `Damage` des a-units. Les PV d'un summon viennent du **kit du summoner**, pas du roster : `--hp-target`/`--hp-player` ne l'atteignent PAS |
| choisir l'**ARMURE** de la cible (et donc quelle branche du plancher perçage gagne) | `--armor-target N` : force `Armor`+`FixedArmor` des a-units. Pendant manquant de `--hp-target` (qui les met à 0). **HAUTE** → la branche PERÇAGE de `GetDamageWithPiercing` (`max(0, d − armure, d × pierce%)`) l'emporte, le dégât reste FRACTIONNAIRE : c'est le SEUL régime où la matérialisation finale (arrondi vs troncature) est observable. **BASSE** → branche armure, dégât entier = régime TÉMOIN. Aucune armure du roster rank 17 ne dépasse 3513, donc sur un profil à perçage bas (Physical = 1 %) ce levier est le seul chemin (mesuré R6) |
| **un ÉCART entre deux unités du MÊME camp** (deux `Health` différents = deux niveaux d'utilité), ou n'importe quel champ de `BC.Units` que les flags globaux n'atteignent pas (`Movement`, `ActiveAbilities`, …) | `--unit-stat "VisualId:Champ=Valeur[,Champ=Valeur][;VisualId:…]"`, répétable, valeur JSON. Les flags ci-dessus forcent une valeur UNIQUE sur TOUT un camp : ils ne peuvent par construction produire aucun écart intra-camp. Mesuré (#286) : discriminer un coefficient MULTIPLICATIF exige deux régimes à écart NON nul — impossible sans ce levier. ⚠ Le patch s'applique au BC **déjà normalisé**, comme les autres : `buildNormalizedBC` RECALCULE `Health`/`Damage` au rank cible, donc patcher le seed BC en amont ne sert à rien (mesuré : 9035/9035 au lieu des 200000 demandés). Pas de virgule DANS une valeur. ⚠ **`Shield` n'est PAS un levier** : le champ arrive bien dans le BC envoyé, et AUCUN chemin de déploiement natif ne le lit (`BattleConfigBuilder$$GetUnitConfiguration` saute `UnitConfiguration.Shield@+0x4c` ; `ShieldComponent` naît VIDE et son unique écrivain est `CreateShieldOperation`). `rl_duel build` le dit maintenant par un `[warn]`. Pour un bouclier RÉEL : le faire POSER en bataille (#342) |
| **un BOUCLIER sur une unité** | mettre `thousSorcerer` **dans l'équipe de la cible** (`--a-units "<cible>,thousSorcerer"`) : son `ArcaneShield` est trigged par `On(0x1c = ArrivedAtFinalTile)`, donc le simple déplacement de placement le pose (5483 pts / 2 tours au rank 17). Autres porteurs : `adeptExorcist` (MoW, `ShieldOfFaith`), `worldTerminator` (`WrathfulDevotion`). Détail : `docs/rl/case-342-shield-lever.md` |
| géométrie (adjacence, ligne, portée, spawns) | `--board` / `--board-pool`, puis **drive des positions** par `applyAction move` — cf. « Choisir le board » ci-dessous. ⚠ **Un acteur qui n'a qu'UNE option n'est pas une mesure** : avant de lire une préférence native entre deux cibles, vérifier que les deux sont dans `abilityTargets.fromHere` (mesuré #286 : sur un board où une cible était hors de portée, le natif retenait l'autre **quelle que soit** la formule testée — verdict parfaitement lisible et entièrement vide) |
| niveau / magnitudes | `--rank` |
| isoler l'aléa (crit, block) | `--crit`, `--crit-target`, `--block-target` |
| neutraliser l'IA adverse | `--no-ai` |
| cibler un cast précis | `--caster`, `--ability`, `--target` |

Et la contrepartie : **avant d'écrire « branche non confrontée » / « non atteignable » /
« bloqué par la géométrie de spawn » dans un rapport, demande-toi quel levier ci-dessus rendrait
l'état atteignable.** Si un flag suffit, ce n'est pas une limite du cas — c'est une bataille à
re-crafter, et la livrer sans le faire, c'est livrer un port non validé.

> Cas vécu (2026-07-25) : le résidu `ReachedSummonCap` a dormi des semaines derrière la
> justification « divergence seulement quand le cap de summons est PLEIN — rare, tardif ». Vrai
> en jeu naturel ; **faux comme argument de validation** : un `--hp-target` élevé fait durer la
> bataille, le summoner survit et sature son cap. Un flag, pas un scénario.
>
> Suite du même cas, et c'est le point le plus important : confronter la branche « summons MORTS
> comptés » exigeait de **tuer** des invoqués — or **aucun levier existant ne le pouvait** (leurs
> PV viennent du kit du summoner). La bonne réponse n'a pas été « branche non atteignable » : ça a
> été **d'ajouter le levier manquant** (`--dmg-target`). Quand aucun flag ne produit ton état, le
> défaut est dans l'outil, pas dans le cas — élargis l'outil.

**Le vrai piège** : un port qui échoue DU BON CÔTÉ (rend une valeur conservatrice, donc
sous-tire au lieu de mal-tirer) ne produit **aucun désaccord mesurable** — aucune statistique
d'agrément ne peut le voir. Ces trous-là ne remontent jamais tout seuls : il faut aller les
chercher en craftant l'état.

#### Choisir le board — c'est une VARIABLE EXPÉRIMENTALE, pas une formalité

**779 boards** sont disponibles (`data/boards/` : 675 `global`, 69 `pvp`, 35 `syncPvp`). Le
board fixe le terrain, l'**élévation**, la jouabilité des tuiles et les spawns — donc il fixe
une partie de ce que tu crois mesurer. **`board.py` te les fait lire AVANT de construire**
(terrain `TileId`, `Elevation`, `ForceUnplayable`, `SpawnPointSets`, depuis la BC) : choisis un
board qui PORTE la propriété dont tu as besoin, au lieu de la découvrir après coup.

Ce que le board décide, et qui a déjà produit de FAUX diagnostics :

- **Nombre de voisins au spawn.** Un spawn en coin ou en bord a **moins de 6 voisins** → toute
  mécanique d'adjacence, d'anneau ou d'AoE est **silencieusement sous-exercée**, et un port faux
  peut passer. Vécu (#90) : la zone d'un `PlagueburstMortar` mesurée depuis un coin ne prouvait
  rien ; il a fallu **rejouer au centre sur un autre board (`C2_02`)** pour couvrir le voisinage
  complet. Corollaire : si ta mécanique compte des voisins, **exige explicitement une tuile à 6
  voisins**, ne l'espère pas.
- **Élévation.** Elle entre dans le calcul de dégât. Vécu (#63) : une « divergence d'armure de
  0.58 » attribuée au moteur était en réalité une différence d'élévation non voulue entre les
  deux camps — un gap de HARNAIS lu comme un bug moteur.
- **Terrain.** Cover et effets de tuile (`DryBush` → `Camouflage`, #62) gatent des mécaniques :
  un board sans le terrain requis rend la branche **inatteignable** et le contre-cas **vide**.
- **Distance entre spawns.** Décide si une unité ranged tire au tour 1 ou passe trois tours à
  marcher — donc si ta mesure arrive avant que l'état que tu voulais observer ait expiré.

**Discipline de généralisation.** Un résultat obtenu sur UN SEUL board n'est pas un résultat dès
que la mécanique touche à la géométrie : c'est peut-être un artefact de ce board. Rejoue sur
**au moins deux couples (board, seed) distincts** — patron déjà appliqué (#95 : `MC1_67/31337`,
`C3_01/777`, `C4_09/999` ; #61 : quatre géométries donnant 7/6/5/4 coups, ce qui a précisément
révélé que la base de `FrenziedFiring` était géométrique et non un bug de canal).

⚠ `--board` est **OBLIGATOIRE** au build : le board par défaut du seed BC n'a pas de spawns 5v5
(#159). Les boards se régénèrent par `python dump_boards.py` **à chaque changement de hash**.
- **Dispose tes runners en fin de passe** (`disposeRunner({runnerId})` ; `listRunners` pour vérifier
  l'atelier vide). Exclusifs : traces globales (`scorer*`, `aiUtilityTrace*`…) + ops de session.

## 4. Piloter une bataille PAS-À-PAS (scénario contrôlé, sans l'IA)

Pour reproduire un cas précis (cast d'une ability donnée à une position choisie, confront d'un capteur…),
on pilote le runner action-par-action. Le runner est un **bac à sable** : **`applyAction` n'applique QU'UNE
action et ne fait PAS jouer l'IA** (le tour ne passe pas tant qu'on ne le décide pas) — on garde donc la
main totale sur la géométrie.

**Recette vérifiée (bout-en-bout)** — ex. driver un cast GetEmRuntz d'orksRuntherd à portée d'ennemis :

1. **Build** (§1) avec rosters EXPLICITES + board choisi (`--p-units`/`--a-units`
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
