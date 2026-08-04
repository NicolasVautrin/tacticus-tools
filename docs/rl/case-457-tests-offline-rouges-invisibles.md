# #457 — trois rouges permanents dans `test_multihex_substrate.py`, et le trou qui les cachait

Deux axes, tranchés séparément : **(a)** la cause des rouges, **(b)** pourquoi rien ne les voyait.

## 1. La mesure

`master` post-#513, `scripts/python` :

```
python -m pytest tests/engine/runner/test_multihex_substrate.py -q
-> 3 failed, 15 passed
```

Compte **inchangé** par #513 (qui a pourtant remué `dsl/base.py`, `entities/triggers.py`,
`services/battle_query.py`, `services/movement_query.py`, `entities/selectors/*`) : les trois rouges
lui sont antérieurs et indépendants.

Les trois — `test_is_valid_unit_feet_list_accepts_native_shapes[7]`,
`test_possible_tile_lists_and_movable_positions`, `test_dislike_starting_tiles_overlap_semantics` —
tombent sur le même `IndexError: list index out of range` : `board.neighbours_native(...)` rend une
liste **vide**, donc `ring[0]` n'existe pas.

## 2. La cause — le MONTAGE, pas le moteur

`_flat_board()` posait `"neighbours": []` sur chaque tuile : un champ **présent et vide**.

`Board.neighbours_native` distingue depuis `#381-r3` (`7c4959ab`, 2026-08-01) le champ **absent**
du champ **présent-et-vide** :

| avant `#381-r3` | après |
| --- | --- |
| `if not raw: return self.neighbours(tid)` | `if raw is None: return self.neighbours(tid)` |
| `[]` repliait sur l'adjacence `evenq` → 6 voisins | `[]` rend `[]` |

Le fichier date du 2026-07-27 (`94b71187`), le changement du 2026-08-01 : le test était vert à sa
naissance et l'est resté jusqu'à ce que le repli change de sens sous lui.

**Le port est JUSTE et la correction de `#381-r3` l'est aussi** : un champ présent-et-vide est une
mesure légitime sur un board réel — `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles`
applique une porte d'élévation inconditionnelle, donc une tuile dont tous les voisins stockés sont à
deux niveaux d'écart ressort réellement sans aucun voisin (mesuré sur `C1_74` : les deux `Water`).
Confondre les deux cas **inventait six voisins là où le natif n'en a aucun**.

Correctif : le montage remplit `neighbours` (even-q clippé aux bords), comme les ~20 autres montages
offline du dépôt. **Il était le seul site du dépôt à poser `[]` littéral** — le gisement est unique,
ce n'est pas un vice systémique.

Les murs restent dans la liste : le capteur `boardGraph` appelle
`IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles(tile, false, false, true)`
(`requireWalkable = 0`).

### La piste de l'orchestrateur, réfutée dans son mécanisme

Proposée : « un `neighbours_native` appelé **sans pathfinder résolu** pourrait rendre vide au lieu de
lever ». **Faux** — `neighbours_native` ne consulte aucun pathfinder et n'a aucun pathfinder à
manquer ; c'est un accesseur au champ brut de la tuile. La piste désignait en revanche le **bon
commit** (`#381-r3` / PR #451) : elle s'est trompée de mécanisme, pas de coupable.

### Le quatrième défaut : un VERT VACUEUX

`test_dislike_starting_tiles_footprint_follows_feet_count` appelle le **même** `neighbours_native` et
**passait**. Avec `ring == []`, son assertion terminale devient
`set([center]) == {center} | set([])` — trivialement vraie. Le bilan réel était donc
**3 rouges + 1 vert à zéro assertion utile**, pas 3 rouges.

Deux gardes posés : `test_flat_board_publishes_native_neighbours` (le montage doit exposer 6 voisins
sur une tuile intérieure, moins mais jamais zéro sur un coin) et un `assert len(ring) == 6` dans le
test concerné. 18 → **19 tests, tous verts**.

## 3. Pourquoi c'était invisible — et le cliquet

Trois causes **cumulées**, dont aucune n'est un oubli individuel :

1. `CLAUDE.md` proscrit la suite complète — à raison : **405 des 489** fichiers de test montent un
   runner et satureraient la session Frida partagée.
2. Un agent ne rejoue que les tests de **sa** tranche. Ce fichier n'était la tranche de personne.
3. Les trois entrées pytest de la banque (`pytest_signatures`, `pytest_attestations`,
   `pytest_adjacency`) **nomment leurs fichiers à la main**. C'est une **allowlist** : on n'y entre
   que si quelqu'un y pense. Personne n'y a pensé pour celui-là.

C'est la forme déjà trouvée par #435 et #455, et la correction durable a chaque fois été d'entrer le
garde dans la banque.

`probe_457_offline_tests_green.py` la généralise : **son périmètre se dérive** au lieu d'être nommé,
donc un fichier offline neuf y entre tout seul. Il est le seul cliquet de la banque dans ce cas.

### Le critère de périmètre, et celui qui a été RÉFUTÉ par mesure

Retenu : `not name.endswith("_live.py")` — déclaratif, tenu par le dépôt. **84 fichiers.**

Essayé puis **réfuté** : classer par la **clôture de fixtures** (`"host" not in item.fixturenames`).
Il rendait **153** fichiers « offline » — dont des **dizaines de `*_live.py`**, qui montent leur
runner **à la main**, sans passer par `host`/`live_session`/`build_runner`. Joué tel quel, ce critère
partait monter des runners et a dépassé **600 s** avant d'être tué (session 12 vérifiée après :
**0 runner** laissé).

La clôture de fixtures reste utilisée, mais comme **filet** et non comme critère : un item d'un
fichier non-`_live.py` qui réclame quand même une fixture live est **déselectionné et rapporté**
(mesuré : **1 item**, `test_act_of_faith_crit_resets_both_paths.py`, fichier mixte). On ne rougit pas
dessus — ce cliquet garde « les tests offline sont verts », pas « le nommage est parfait ».

Une seule racine suffit à reconnaître le live : `host` et `live_session` couvrent **exactement** les
mêmes 359 fichiers, et `rpc` / `build_runner` / `live_runner` en sont des sous-ensembles stricts
(294 / 248 / 2) — la clôture calculée par pytest est transitive.

### Le coût, et pourquoi trois shards

Mesures **isolées** (reproductibles, hors contention) :

| forme | mesure (2026-08-02) |
| --- | --- |
| d'un bloc | 84 fichiers, **896 tests, 116 s** — dont ~56 s d'**import** de modules |
| éclaté en 3 shards | **22 s / 28 s / 86 s** |

Joué d'un bloc il **devient** le mur (~132 s) ; éclaté, son plus long shard passe **sous** lui. Même
arbitrage que `probe_283`, pour la même raison — à une nuance près, qui joue en sens inverse :
éclater **multiplie l'import fixe** (~40 s par process Python), donc le CPU cumulé monte (116 s →
136 s) pendant que la latence max baisse. C'est la latence qui décide ici, parce que la banque a
plus de slots (22 cœurs) que de vagues.

⚠ **Le mur de la banque n'est PAS une mesure stable** : la machine est partagée avec les autres
agents. Quatre relevés du même jour, sur des compositions quasi identiques, ont rendu 126,6 / 136,2 /
159,1 / **319,8** s. Aucun arbitrage fin ne peut s'appuyer dessus — d'où le choix de trancher sur les
mesures isolées ci-dessus. Le seul relevé exploitable est un **dos-à-dos** dans la même fenêtre.

Le shard se dérive d'un **md5 du chemin relatif**, pas d'un modulo sur l'index du tri : un fichier
neuf ne redistribue donc pas les autres. Union des trois **vérifiée stricte** : 30 + 30 + 24 = 84,
aucun doublon, aucun manquant.

### Contre-épreuve : le cliquet ROUGIT sur son gisement

Montage fautif restauré (`git checkout 5987622b -- <le fichier>`), shard 0 rejoué :

```
3 failed, 316 passed
[457] VERDICT: FAIL -- au moins un test offline est ROUGE (pytest rc=1)   RC=1
```

Correctif restauré : `320 passed`, `RC=0`. `probe_439` classe les trois entrées **capables de
rougir** ; `probe_440` étape 3 (écriture d'un cliquet dans l'arbre de production) : **0**, grâce à
`-p no:cacheprovider`, qui empêche pytest de déposer `.pytest_cache` sous `scripts/python/` que la
banque énumère en parallèle (#455).

Un shard **vide** rend `1`, pas `0` : un périmètre effondré (glob faux, `git ls-files` muet) doit se
dire, pas passer pour un succès.

## 4. Relevé de la banque

Relevé daté, joué depuis ce worktree — la banque se **définit** dans `scripts/ratchets.ps1`, elle ne
se recopie pas ici.

**Dos-à-dos**, même fenêtre, machine la plus calme obtenue (`-Skip probe_457` puis complet) :

| composition | verdict | mur |
| --- | --- | --- |
| 30 cliquets (sans #457) | VERTE | **136,2 s** |
| 33 cliquets (avec `probe_457:s0/s1/s2`) | VERTE | **147,2 s** |

Coût marginal **+11 s (+8 %)**. Un dos-à-dos antérieur, sous charge plus forte, avait rendu
126,6 → 178,4 s (+41 %) : l'écart entre les deux mesures est le bruit de la machine partagée, pas une
propriété du cliquet.

⚠ Piège d'outillage rencontré : `pwsh -File scripts/ratchets.ps1 -Skip a,b` passe **une seule
chaîne** `"a,b"` et n'exclut donc **rien** — la banque rapporte alors son compte complet. Vérifier le
nombre de cliquets annoncé avant de lire un mur.

## 5. Résidus nommés

- **`#457-r1` — deux appels au MÊME natif portés sur DEUX vues du `Board`.**
  `IdunBattle.Core.Services.MovementQuery$$IsAdjacent` et la branche `feetCount == 7` de
  `IdunBattle.Core.Services.MovementQuery$$GetPossibleTileListsFromMovableTiles` mirrorent tous deux
  `GetAdjacentTiles(t, false, true, true)` (mêmes flags, même slot). Le port lit `board.neighbours()`
  pour le premier (trié **et symétrisé**) et `board.neighbours_native()` pour le second (ordre brut,
  **non symétrisé**). Sur le plateau plat du test les deux coïncident — c'est pourquoi rien ne le
  signale — mais sur un board capté, `native_sym` ajoute les arêtes inverses que le brut n'a pas.
  Une des deux lectures est fausse ; laquelle demande de trancher quelle vue le natif consulte, ce
  qui sort du périmètre de ce cas. Non confronté.
- **`#457-r2` — le flag `requireWalkable = 1` n'est appliqué nulle part.** Les deux appels ci-dessus
  passent `(0, 1, 1)`, et `docs/rl/playbook/playbooks.md` §#148 — source indépendante, qui a établi
  le mapping en lisant les **ctors** des deux itérateurs — confirme que `MovementQuery.IsAdjacent`
  passe bien `param4 = requireWalkable = 1`. Or le `boardGraph` est capté avec `(0, 0, 1)` (murs
  inclus, à dessein) et le port ne réapplique le filtre nulle part : il rend donc `True` là où le
  natif rend `False` pour une tuile non marchable. Inerte sur un plateau tout marchable, mordant dès
  qu'un mur entre dans une empreinte candidate.
- **`#457-r3` — un test live SANS suffixe `_live.py` ET sans fixture live serait joué par le
  cliquet**, et monterait un runner depuis la banque. Aucun cas aujourd'hui (84 fichiers, 896 tests,
  aucun montage observé) ; le filet de déselection ne couvre que la voie par fixtures.
- **`#457-r4` — les 24 fichiers de test sans suffixe** (`_live` ni `_offline`) restent tels quels.
  Le cliquet les joue, donc l'invisibilité est fermée sans les renommer ; mais leur nature ne se lit
  toujours pas au nom.

## 6. `#457-r5` — le périmètre du cliquet ratait 23 fichiers, dont 21 gardés par personne

**Le cliquet censé garder « tout test offline est vert » n'en énumérait que 86 sur 109.**

`TESTS_GLOB = "scripts/python/tests/**/test_*.py"` : `**/` **exige un niveau intermédiaire**, donc
les fichiers posés **directement** dans `tests/` en étaient exclus. Mesuré le 2026-08-02, contre-épreuve
du glob lui-même :

| pathspec | fichiers |
| --- | --- |
| `scripts/python/tests/**/test_*.py` | 496 |
| `scripts/python/tests/test_*.py` | 23 |
| total réel | **519** |

Deux des 23 étaient rattrapés par les allowlists (`pytest_signatures`, `pytest_attestations`).
**Les 21 autres n'étaient joués par aucune entrée de la banque** — et ce sont des gardes de premier
rang : `test_431_build_pin_offline`, `test_host_inputs_offline`, `test_391_conftest_dir_identity_offline`,
les quatre ratchets d'enum, `test_366_r1_bcpatch_port_blindspot_offline`, `test_323_unit_map_voies_offline`.
Dont `test_449_r2_spread_face_combat_offline.py`, que l'orchestrateur avait dû rejouer **à la main**
en validant #515 : s'être appuyé sur la banque ne l'aurait pas couvert.

**La garde anti-effondrement existait mais ne voyait que le cas TOTAL.** §3 ci-dessus se prémunit
d'un périmètre vide (« un shard vide rend 1, pas 0 — un périmètre effondré, glob faux, doit se
dire »). C'est un périmètre **partiel** qui est arrivé, et un périmètre partiel passe pour un succès.
Un compte non nul n'est pas une preuve de couverture.

**Verdict sur le gisement : aucun rouge caché.** Les 24 fichiers entrants sont **tous verts**
(24/24, 300 tests), et les trois shards du périmètre complet rendent `rc=0`. Le trou était réel mais
n'avait pas encore mordu — ce que le cliquet garde désormais, c'est demain.

### La correction

Le répertoire est passé à git (`git ls-files scripts/python/tests`, qui descend seul, **sans
sémantique `**` à deviner**) et la sélection se fait en Python sur le basename. Le critère couvre
les **deux** conventions pytest (`test_*.py` **et** `*_test.py`) : `pytest.ini` ne pose pas
`python_files`, donc le périmètre doit couvrir ce que pytest **collecte**, pas ce qui se trouve exister.

**Garde posée** : `scripts/python/tests/test_457_r5_perimetre_offline.py` (8 tests) — accord entre
**deux dérivations indépendantes sur l'axe qui a cassé** (pathspec git *vs* walk disque intersecté à
`git ls-files` **sans pathspec**), plus une propriété dédiée sur la profondeur 1, plus le critère de
nommage. **Anti-vacuité** posée partout : deux ensembles vides seraient trivialement égaux — chaque
test asserte d'abord que sa source n'est pas vide (leçon du vert vacueux, §2).
Le fichier est lui-même en profondeur 1 : il ne peut pas être invisible au trou qu'il garde.

### Le coût a changé d'ordre — et c'est assumé

Les 24 entrants pèsent **2150 s en série** pour ~300 tests, contre 116 s pour les 896 tests
préexistants : **~20× le coût par test**. Rien d'anormal — ce sont les **gardes de dépôt**
(balayages d'arbre, tables de symboles, 669 kits), là où la profondeur ≥ 2 abrite les tests
unitaires du moteur. Les cinq plus lourds : `test_380_seed_bc_patch_survival` 268 s,
`test_431_build_pin` 258 s, `test_366_r1_bcpatch_port_blindspot` 234 s, `test_enum_ordinal_ratchet`
201 s, `test_additional_hits_variant_signatures` 169 s.

Simulation sur les durées mesurées (`shard_of` réel, md5 % N) :

| shards | mur | écart-type |
| --- | --- | --- |
| 3 | 924 s | 217 |
| 4 | 697 s | 121 |
| **8** | **629 s** | 176 |
| 16 | 443 s | 131 |

**Passage à 8 shards** (banque 33 → 38 entrées, union re-vérifiée stricte : 110 = 110 distincts,
0 doublon, 0 manquant). Au-delà le rendement s'effondre : le md5 **regroupe les lourds**, et le
plancher irréductible est le fichier le plus lourd, insécable. Sharder n'est donc plus le levier ;
alléger les balayages l'est (`#457-r6`), et **#524 vient de le démontrer** sur `probe_431` :
périmètre ×2,1 pour **−14 %** de temps, le `Path.match` coûtant plus cher que le gisement qu'il ratait.

⚠ **La simulation SURESTIME — c'est la mesure isolée qui fait foi.** Mur réel des 8 shards, mesuré
isolé (`ratchets.ps1 -Only probe_439,probe_440,probe_457`, 10 cliquets, `rc=0`) : **297,8 s**, shard
le plus long 295,7 s, le plus court 48,3 s. La simulation annonçait 629 s parce qu'elle additionne
des durées par fichier **déjà gonflées par la contention** (5 agents actifs au moment du profil).
Même leçon que §4 : un mur ne se déduit pas, il se mesure isolé.

⚠ **Ne jamais « régler » ce coût en rétrécissant le périmètre** : c'est exactement la faute réparée ici.

### Convergence indépendante

**#458 / PR #524 a trouvé la même sémantique le même jour, sur un autre outil** : `probe_431` ratait
17 fichiers « par le haut » — « le `**` exige un segment, donc un fichier posé à la racine même du
glob échappe ». Deux outils, deux auteurs, un seul vice. C'est la **cinquième** forme du « périmètre
saisi au lieu d'être dérivé », et la première où le périmètre *se voulait* dérivé : c'est la
**sémantique du glob** qui le restreignait en silence.

### Résidus ouverts par cette section

- **`#457-r6` — les gardes de dépôt coûtent 20× le coût/test des tests moteur.** 2150 s pour ~300
  tests ; `test_391_conftest_dir_identity_offline` fait **1 test en 122 s**. Ces balayages relisent
  l'arbre indépendamment les uns des autres ; un cache d'arbre partagé (fixture de session) est le
  levier. Chiffré, non traité.
- **`#457-r7` — le probe rend un FAUX `VERDICT: FAIL` s'il est lancé hors `scripts/python`.** Les
  chemins passés à `pytest.main` sont relatifs au rootdir ; depuis la racine du dépôt il rend
  `pytest rc=4` (*usage error*, « file or directory not found ») que le probe traduit en rouge de
  test. La banque le lance depuis le bon répertoire, donc le gisement est nul aujourd'hui — mais un
  rc d'usage ne doit pas se lire comme un rouge de gisement.

## 7. `#457-r6` — le mur de la banque : ce qui le fait, et ce qui ne le fait PAS

Objectif pose le 2026-08-02 : **passer le mur sous 60 s** (il etait a 244 s).

### Ce qui NE le fait pas : le parallelisme

`ForEach-Object -Parallel -ThrottleLimit N` **est deja** un pool de N workers qui depile une file.
Le mur n'en depend pas :

| throttle | mur | dont le plus long cliquet |
| --- | --- | --- |
| 6 | 244,9 s | 236,9 s |
| 10 | 228,3 s | 228,0 s |
| 16 | 234,8 s | 234,7 s |

Le mur EGALE la duree d'**une seule tache indivisible**. Quinze workers finissaient et attendaient.

### Le plafond REEL, mesure

Scaling d'un cliquet qui parse l'arbre (`probe_431`), N instances simultanees :

| N | 1 | 8 | 16 |
| --- | --- | --- | --- |
| mur | 20,8 s | 40,0 s | 60,7 s |

⇒ **~5 workers effectifs**, pas 16. Ces taches sont limitees par la bande passante memoire (AST de
~1900 fichiers), pas par les coeurs. Contre-epreuve : `probe_313`, qui lit une TABLE au lieu de
parser l'arbre, scale presque parfaitement (16 instances = 21,6 s contre 17,6 s pour une seule).
La difference n'est donc pas la machine, c'est la NATURE de la charge.

**Consequence : mur minimal ≈ travail_total / 5.** Somme isolee de la banque = **675 s** ⇒ plancher
~135 s. **Tenir 60 s exige de diviser le travail par deux — aucun ordonnancement n'y suffira.**

### Ce qui a ete fait

1. **Ordonnancement LPT** (`ratchets.ps1`) : les cliquets partaient dans l'ordre de DECLARATION,
   `probe_181` (1,2 s) en tete et les shards lourds en fin. Durees relues du run precedent
   (`logs/ratchets/durations.json`), inconnu = suppose maximal. **N'affecte ni le verdict ni le
   code de sortie** : des poids perimes coutent du mur, jamais un faux vert.
2. **Parallelisme sur les coeurs PHYSIQUES** (16) et non logiques (22).
3. **Shardage par COUT** de `probe_457` (bin-packing LPT) au lieu du md5, qui repartissait par
   NOMBRE : il avait concentre 4 fichiers lourds dans `s7` (**106 s** isole contre **4,8 s** pour
   `s3`), et ce shard faisait A LUI SEUL tout le mur. Apres : **60 / 38 / 32 x 6**.
   Poids regeneres par `probe_457 --measure` (un seul passage chronometrant chaque fichier —
   mesurer fichier par fichier couterait 110 demarrages a 3,1 s et surestimerait d'autant).

**Mur : 244 → 213-229 s.** Le plancher est desormais le fichier le plus lourd, insecable.

### La regression que ce travail a INDUITE, et sa correction

`test_431_build_pin_offline.py` **mutait l'arbre de production** pour verifier que le cliquet
rougit. Isole seul dans son shard par le nouveau partitionnement, LPT le fait demarrer en PREMIER
— exactement quand `probe_431` balaie ce meme arbre. **Banque ROUGE 2 fois sur 2**, sur des
residus TRANSITOIRES qui n'existaient deja plus quand on allait les chercher (`git status` propre,
`git grep` muet). Le defaut etait pre-existant et occasionnel ; le partitionnement l'a rendu
SYSTEMATIQUE.

C'est **#455 dans l'autre sens** : la-bas un cliquet CREAIT un fichier sous `scripts/python/` ;
ici un test y MODIFIE des fichiers, pendant qu'une dizaine de cliquets enumerent le meme arbre.

Correction : les trois tests de mutation operent dans un **worktree jetable** (`git worktree add`
sur un tmpdir SYSTEME, fixture de module). Aucune option n'a ete ajoutee a `probe_431` — il derive
sa racine de son PROPRE chemin, donc lancer la copie du worktree suffit a l'y confiner. Le
worktree part de `HEAD`, ce qui rend au passage le test independant du working tree.
Cout : +25 s sur ce fichier (60 → 85 s), assume — la correction prime sur le mur.

⚠ Un autre garde a fait son travail pendant ce chantier : la premiere version de `--measure`
ecrivait ses poids **a cote du probe**, sous `scripts/python/`. **`probe_440` a rougi, a raison.**
Les poids vivent donc sous `logs/` — gitignore, donc un checkout frais retombe sur le repli md5 :
mur sous-optimal, **verdict inchange**.

### Ce qui reste pour atteindre 60 s

**`#457-r6` reste OUVERT.** Le gisement est identifie et chiffre : une dizaine de cliquets
(`probe_431`, `probe_440`, `probe_273`, `probe_319`, `probe_365`, les 6 etapes de `probe_283`…)
**re-parsent chacun les memes ~1900 fichiers**. Mutualiser ce balayage — un AST parse UNE fois,
consomme par tous — est le seul levier qui reste, et #524 en a deja donne la preuve de concept sur
`probe_431` : perimetre x2,1 pour **-14 %** de temps.

Cibles secondaires, mesurees isolees : `test_431_build_pin` 85 s (dont 3 tests qui relancent le
cliquet entier), `test_391_conftest_dir_identity` **1 seul test en ~78 s**,
`test_enum_ordinal_ratchet` ~38 s, `test_ability_registry_ratchet` ~31 s.

⚠ Chiffres a RE-DERIVER (`probe_457 --measure`, puis un relevé isolé), jamais a citer.

## 8. `#457-r6` (suite) -- le poste de cout n'etait PAS l'AST : c'etait l'OUVERTURE des fichiers

Le diagnostic herite designait `ast.parse` (« une dizaine de cliquets re-parsent chacun les memes
~1900 fichiers »). **Mesure, et il est FAUX** -- ou plutot : il designe le deuxieme poste, pas le
premier.

### La mesure qui renverse le diagnostic

Machine calme, arbre du worktree (3254 fichiers versionnes, 58,7 Mo) :

| operation | mesure (2026-08-03) |
| --- | --- |
| lecture en SERIE, fichiers JAMAIS LUS depuis leur ecriture | **12,3 - 16,8 s** |
| lecture en SERIE, memes fichiers deja lus une fois | **0,3 - 0,9 s** |
| lecture en 16 THREADS, fichiers jamais lus | 3,3 - 7,6 s |
| decodage utf-8 + fins de ligne des 58,7 Mo | 0,16 s |
| `ast.parse` de tout `scripts/python/**` (1603 fichiers) | 7,1 s |
| un `ast.walk` complet de ces 1603 arbres | 2,9 s |

**Le declencheur est l'EXTENSION, pas le chemin.** La premiere ventilation comparait des RACINES
(`scripts/` 7,36 ms/fichier contre `data/` 0,75 et `docs/` 0,65) — elle confondait deux variables,
puisque ces racines different AUSSI par leur contenu. Contre-epreuve 2x2 qui les separe : 400
fichiers IDENTIQUES, copies en `.py` et en `.txt`, dans le depot et hors depot, un process frais par
case.

| | `.py` | `.txt` |
| --- | --- | --- |
| dans le depot (`logs/`) | **15,29** ms/fichier | 0,72 |
| hors depot (`%TEMP%`) | **12,50** ms/fichier | 0,52 |

Facteur ~20 sur l'extension, ~1,2 sur le chemin. Signature d'un **scanner on-first-read a cache**.
⚠ Ce n'est pas la protection temps reel de Defender (`RealTimeProtectionEnabled: False`), mais ce
champ NE SUFFIT PAS a conclure : `AMRunningMode` (`Passive Mode` / `EDR Block Mode` = un autre
produit est primaire) n'a jamais ete lu. Cause exacte NON identifiee, `fltmc filters` exigeant
l'elevation :

```powershell
fltmc filters                 # tout nom hors bindflt/FsDepends/WdFilter/storqosflt/wcifs/
fltmc instances -v C:         #   CldFlt/FileCrypt/luafv/npsvctrig/Wof/FileInfo = le suspect
Get-MpComputerStatus | Format-List AMRunningMode, RealTimeProtectionEnabled
Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct
```

⚠ **REFUTE le 2026-08-03 : le cout n'est PAS par PROCESSUS.** Cette section a d'abord conclu
« deux PROCESS consecutifs donnent 16,8 s et 16,8 s ». Mesure sur l'arbre reel (1605 `.py`), trois
process FRAIS consecutifs, rien entre eux : **12,3 s / 0,90 s / 0,29 s**. Le cache du filtre est
SYSTEME, il sert tous les process. Le cout se paie une fois **par FICHIER**, au premier acces depuis
son ecriture.
Consequence : **la banque ne le paie pas 35 fois.** Le premier lecteur rechauffe l'arbre pour les
34 autres. Le profil `cProfile` (`_io.open` = 16,4 s des 41,1 s de `probe_431` instrumente, poste
NUMERO UN) mesurait donc un run FROID, pas un regime.

⚠ **CORRIGE UNE SECONDE FOIS le meme jour, en sens INVERSE — et c'est la mesure qui tranche, deux
fois contre moi.** La redaction precedente ajoutait « ni a chaque run » : FAUX. **Le cache
n'est pas DURABLE.** Mesure : `scripts/python` rendu a **0,29 s** le matin, **12,98 s** une heure
plus tard, sans qu'aucun de ses fichiers n'ait ete reecrit. Il tient donc entre PROCESSUS d'une
meme fenetre (16,7 -> 0,63 s a l'instant) mais **ne survit pas d'un run de banque au suivant**.
⚠ **TTL ou EVICTION sous pression : NON ETABLI.** Les runs intercalaires lisent des dizaines de
milliers de fichiers, donc les deux hypotheses collent. Ne pas trancher a l'oeil.

**Ce que ca coute, mesure sur la banque COMPLETE** (n=1 de chaque cote, a re-derier) :

| etat de l'arbre | mur |
| --- | --- |
| arbre principal CHAUD (lu juste avant) | **205,2 s** |
| worktree NEUF, integralement froid | **293,1 s** |

Soit **~88 s, +43 %** — bien au-dessus de la variance de +/- 15 %, et ~5x le cout froid SERIE
(16,7 s), ce qui suggere une amplification sous les 16 voies paralleles (16 process frappant
simultanement des fichiers inconnus du filtre). Suggere, PAS etabli.
**Consequence pour l'arbitrage : l'exclusion machine vaut PLUS que ce que la premiere correction
disait** — elle se paie a chaque run de `ratchets-bg` (worktree neuf par construction) et a chaque
worktree d'agent.

⚠ **Corollaire de methode : une mesure ISOLEE d'un cliquet est trompeuse dans les DEUX sens.**
Jouee juste apres un voisin qui a lu le meme arbre, elle est artificiellement basse ; jouee la
premiere, artificiellement haute. Les mesures « avant/apres » d'un cliquet pris seul ci-dessous
sont donc systematiquement bruitees de +/- 50 % -- **seul le mur de la banque, dos-a-dos, tranche.**

### Ce qui a ete fait

1. **`scripts/python/repo_read.py`** -- lecture PARALLELE (16 threads, l'`open` bloque hors GIL),
   avec `to_text` qui reproduit exactement `Path.read_text(encoding="utf-8")`, fins de ligne
   universelles comprises. Ce n'est pas une invention : `probe_273` portait cette recette DEPUIS
   #409, seul. Le module la generalise.
   Branches dessus : `probe_431`, `probe_283` (ses 5 etapes lisantes), `probe_274`, `probe_443r1c`,
   `probe_440`, `probe_313`, `probe_455`.
2. **`probe_431` : cinq `ast.walk` par fichier ramenes a UN** (`_Index`, meme forme que celui de
   `probe_440`). 26,4 -> 11,7 s isole.
3. **Trois entrees retirees de la banque** (`pytest_signatures`, `pytest_attestations`,
   `pytest_adjacency`) : elles nommaient A LA MAIN cinq fichiers que le perimetre DERIVE de
   `probe_457` joue deja depuis #457-r5. **40,4 s de travail strictement redondant** (durees
   isolees). Ce n'est pas un retrecissement -- l'union des tests joues est INCHANGEE, et c'est
   prouve mecaniquement par `tests/test_457_r6_banque_sans_doublon_offline.py`, qui derive la
   banque (`probe_439`) et le perimetre (`probe_457`) et rougit sur tout recoupement.

**La FIDELITE est prouvee par diff de sortie, pas par relecture** : les 5 etapes de `probe_283`,
`probe_274`, `probe_313` et `probe_455` rendent une sortie **IDENTIQUE A LA LIGNE PRES** a celle du
run de reference ; `probe_431`, `probe_443r1c` et `probe_440` ne different que par leur compteur de
fichiers lus (+1 : `repo_read.py` lui-meme).

### Ce qui NE marche pas, mesure

- **Une descente d'AST plus rapide** : une reimplementation de `ast.walk` sans ses deux
  generateurs imbriques rend **x1,34** (2,89 -> 2,16 s), ordre BFS identique verifie sur les 1603
  arbres. Trop peu pour justifier un mirror d'une fonction de la bibliotheque standard. Ecarte.
- **Baisser le degre de parallelisme.** Mur mesure, meme fenetre : throttle 4 -> **280,1 s**,
  6 -> 240,2 s, 8 -> **226,7 s**, 16 -> 234,7 / 242,4 s. Tout est dans le bruit sauf 4, qui est
  franchement pire. Le defaut (coeurs physiques) reste le bon choix.
- **La lecture parallele n'aide PAS un process deja chaud.** Dans `probe_457`, les fichiers de test
  s'enchainent dans une meme session pytest : le premier rechauffe l'arbre pour les suivants. Mesure
  par `--measure` : `test_431_build_pin` 59,2 -> **41,4 s** (il relance un PROCESS par mutation,
  donc il en profite), mais `test_enum_ordinal_ratchet` 35,7 -> 45,1 s (il appelle les etapes
  EN PROCESS, ou le pool de threads ne rachete pas son cout). Total du perimetre : 290,9 -> 297,2 s,
  a 45 tests pres. **Le gain se joue entre PROCESS, pas a l'interieur d'un.**

### Le releve, dos-a-dos dans la meme fenetre

Machine calme, memes poids d'ordonnancement des deux cotes (`durations.json` et
`457-durations.json` restaures a l'identique avant CHAQUE run), deux releves par cote :

| etat | somme ISOLEE (`-Serial`) | mur (2 releves) |
| --- | --- | --- |
| avant (38 cliquets, `8e4a09f5`) | **739,6 s** | 261,6 / 281,9 s |
| lecture parallele seule (38 cliquets) | -- | 234,7 / 242,4 s |
| + les 3 doublons retires (35 cliquets) | **677,9 s** | **199,4 / 206,4 s** |

⚠ Un TROISIEME releve du cote « apres », joue plus tard sur l'etat livre, a rendu **234,5 s**
(banque VERTE, 35 cliquets, rc 0). Il est au-dessus des deux du dos-a-dos et il est INSCRIT ICI :
la variance du mur sur cette machine partagee est de l'ordre de +/- 15 %, et c'est exactement
pourquoi seul un dos-a-dos dans la MEME fenetre vaut quelque chose. Le lire comme une regression
serait la meme erreur que lire 199,4 s comme un acquis.

⚠ **QUATRIEME releve, 2026-08-03, machine calme (flotte vide) : `205,2 s`** — banque VERTE, 35
cliquets, rc 0. **Il VALIDE les 199,4 / 206,4 s annonces par #526**, que la validation de
l'orchestrateur n'avait pas reussi a reproduire (279,2 / 263,6 s) et avait inscrits « equivalent,
pas ameliore ». C'etait la FENETRE de mesure qui etait defavorable, pas le chiffre de l'auteur.
Structure du mur a ce releve : il EST le bloc des 8 shards de `probe_457` (160,6 -> 205,0 s), tout
le reste finissant dessous — le shardage par cout les fait atterrir groupes. Ces durees sont SOUS
CONTENTION 16 voies ; isole, un shard fait ~50 s, et l'ecart est exactement l'efficacite de 2,7-2,9
workers effectifs.

**Mur : -26 %. Somme isolee : -8,3 %**, dont 40,4 s de deduplication et ~21 s d'optimisation. Le
mur baisse BEAUCOUP plus que la somme isolee, et c'est le point : le gain se manifeste SOUS
CONTENTION, quand 16 process font chacun leurs 3254 ouvertures en serie et se bloquent
mutuellement. Vu par cliquet, sur le meme run parallele, avant -> apres : `probe_431` 157,4 ->
29,6 s, `probe_283:exec` 194,3 -> 63,2 s, `probe_274` 157,3 -> 53,8 s, `probe_440` 81,3 -> 36,5 s.

### Le verdict sur l'objectif de 60 s : HORS D'ATTEINTE, et voici le chiffre

Le mur ne peut pas descendre sous `travail_total / efficacite`, et les deux termes sont mesures :

* **travail total = 677,9 s** (somme isolee, apres tout ce qui precede) ;
* **efficacite = 2,7 a 2,9** workers effectifs (677,9 / 203 s de mur moyen). Ce n'est PAS un
  probleme d'ordonnancement : throttle 4 -> 280,1 s, 6 -> 240,2 s, 8 -> 226,7 s, 16 -> 234,7 s.
  Entre 6 et 16 tout est dans le bruit. La machine ne soutient pas plus, un point c'est tout.

Pour un mur de 60 s a cette efficacite, il faudrait un travail total de **~170 s**. On est a 678,
soit un facteur **4**. Et ce facteur bute sur une structure, pas sur du gras :

* **`probe_457` pese 402,6 s a lui seul, soit 59 % du travail** -- 297,2 s de tests (1240 tests,
  112 fichiers) plus ~105 s de DEMARRAGE des 8 sessions pytest (interpreteur, imports `engine` /
  `pytest` / `gameconfig`, conftest). ⚠ Ce residu etait attribue a l'OUVERTURE des fichiers ; cette
  attribution NE TIENT PLUS (cf. la refutation ci-dessus) et n'a pas ete re-ventilee. Son perimetre
  est DERIVE : le reduire est exactement la faute que #457-r5 repare.
* **Son shard le plus long fait 74,8 s isole** -- donc meme a parallelisme parfait, le mur ne peut
  pas descendre sous 75 s sans re-sharder plus fin. Or sharder plus fin AJOUTE du travail
  (~13 s d'ouverture de session par shard) : a 12 shards le max tomberait vers 55 s mais le travail
  monterait a ~730 s, et le mur (travail/2,8) resterait a ~260 s. **Sharder n'est plus un levier.**

### Ce qu'il faudrait pour y arriver -- non fait, chiffre

1. **Supprimer le surcout systeme a l'ouverture.** ⚠ **Sa valeur a d'abord ete SUR-ESTIMEE ICI**,
   sur le « une fois par process » refute plus haut : ce n'est PAS un plancher d'E/S de
   `16,8 s x ~35 process`, et en regime etabli la banque ne le paie pas du tout. Ce qu'une
   EXCLUSION du depot gagnerait reellement : le PREMIER run apres un `merge`/`checkout` (~12 s), et
   surtout **chaque worktree d'agent**, dont l'arbre est integralement neuf pour le filtre. Reel,
   mais **sans effet sur les 678 s de travail** — donc ce n'est plus le levier n°1 qu'annoncait
   la premiere redaction. Action MACHINE, hors depot.
2. **Fusionner les process.** Les ~13 balayages et les 8 shards paient chacun son demarrage Python,
   ses imports (`engine`, `pytest`, `gameconfig` a 1,5 s), et sa PREMIERE lecture de l'arbre. Un
   cliquet multiplexe qui parse une fois et joue N analyses supprimerait tout cela d'un coup.
   Cout : la granularite du rapport ROUGE, et un plancher de mur egal a la duree de ce process
   unique. C'est le seul levier qui reste dans le depot, et il est STRUCTUREL.
3. **Un cache d'analyse inter-run** : ECARTE. Un cache perime rend un faux VERT, et le symptome
   serait silencieux -- exactement ce que toute cette case-doc combat.

⚠ Chiffres a RE-DERIVER (`probe_457 --measure`, `ratchets.ps1 -Serial`, puis un dos-a-dos),
jamais a citer.

## 9. `#464` — `--measure` ÉCRIVAIT sur un échec de MONTAGE, et vidait un fichier VERSIONNÉ

**Ferme `#457-r7`**, qui n'en décrivait que la moitié visible.

### La mesure

Lancé depuis la **racine du dépôt** au lieu de `scripts/python/` — les chemins passés à
`pytest.main` sont relatifs au rootdir que fixe `scripts/python/pytest.ini` :

```
ERROR: file or directory not found: tests/engine/entities/pathfinding/test_381r3_...py
no tests ran in 0.00s
[457] empreinte -> scripts/ratchets-457-footprints.json : 0 fichier(s) de test, ...
[457] --measure : 129 fichier(s), 0.0 s de tests mesures en 2.0 s de mur
[457] --measure : pytest rc=4 -- poids ecrits, mais l'arbre est ROUGE      RC=1
-> git diff --stat : 3 insertions(+), 632 deletions(-)
```

Trois fautes **cumulées**, et c'est le cumul qui fait le dégât :

1. un `pytest rc=4` (erreur d'**usage** — rien n'a tourné) rendu comme `rc=1`, c'est-à-dire un
   verdict de **gisement** (« l'arbre est ROUGE ») ;
2. l'écriture faite **avant** la décision, donc annoncée au passé (« poids écrits, mais… ») ;
3. la cible de l'écriture est **versionnée** — l'échec ne se contente pas de se lire comme une
   mesure, il **persiste**.

### Le dégât n'est PAS celui que le fichier annonçait

`_footprints_path` documentait le risque d'une empreinte périmée : « elle sélectionne **TROP** et
retombe continûment sur le rejeu total ». Une empreinte **vidée** fait l'**inverse**.
`impacted_files` lit `rel not in par_test` comme « ce test n'ouvre **aucun** fichier du dépôt, ses
dépendances sont d'import pur → **le graphe d'imports le couvre** » et le **saute**. Un `par_test`
vide fait donc sauter tout test dont la seule dépendance est une **donnée** (`data/symbols/…`,
`docs/…`, `frida/hooks/*.ts`) — un **FAUX VERT partagé et versionné**, exactement ce que
l'asymétrie poids/empreinte du fichier était censée interdire.

### La correction — deux verrous, dans cet ordre

1. **`_exiger_cwd()`** refuse **avant de jouer quoi que ce soit**, pour tout mode qui invoque
   pytest (mesure **et** shard). `--list` n'invoque rien (l'énumération passe par
   `git -C <racine>`) et reste jouable de partout.
2. **`_ecrire_mesure()` est le FOYER UNIQUE d'écriture**, et **décide avant d'écrire** : refus si
   pytest rend 2/3/4/5, ou si **aucun** fichier joué n'a produit de report. Ce second verrou couvre
   ce que le CWD ne cause pas (un fichier disparu entre `git ls-files` et l'exécution, un `-x`
   interrompu). Le critère est le **nombre de reports**, jamais la durée — un fichier offline pur
   passe ses 4 tests en moins de 5 ms.

Le code de sortie est **99**, la convention déjà tenue par `scripts/ratchets-bg.ps1` : « aucun
verdict sur le dépôt », à ne lire ni comme un rouge **ni comme un vert**. Le mode shard rend
désormais 99 lui aussi sur un rc 2/3/4 — c'est `#457-r7` fermé. `rc=5` y **reste rouge** : un shard
qui a des fichiers et n'en collecte aucun est anormal (gisement de `probe_455` r3).

### L'arbitrage : REFUSER, pas `chdir` — alors que le dépôt a le précédent inverse

Trois scripts corrigent le CWD au lieu de le vérifier (`probe_391` L176, `probe_433_r1` L507,
`probe_433_r3` L543 : `os.chdir(HERE)`). Ce n'est **pas** ce qui est fait ici, et la raison est
propre à ce probe :

- un `chdir` aurait fait **tourner** la mesure — 976,9 s **et une écriture** — depuis un montage
  que personne n'a voulu ; « ça marche quand même » n'est pas neutre quand la sortie est
  versionnée ;
- le mode shard est un **cliquet** : son verdict doit être attribuable à un montage explicite, et
  le contrat `rc=99` (« non mesuré ») n'existe pas sous `chdir` ;
- un `chdir` rend l'exigence **invisible** : le prochain script naîtra fragile sans qu'on
  l'apprenne, alors que le message de refus nomme le répertoire exact.

### Le recensement demandé — combien d'autres scripts sont fragiles

Balayage AST de `scripts/python/**` (hors `tests/`), critère « passe un chemin **relatif** à une API
qui résout depuis le CWD, **sans** neutraliser le CWD (`cwd=` explicite, `os.chdir`, vérification) » :

| axe | fragiles | neutralisés |
| --- | --- | --- |
| invocation de **pytest** (relatif au rootdir) | **0** (après ce correctif) | 6 — `probe_418`, `probe_426`, `probe_431_build_pin_mutants`, `probe_455`, `probe_462` par `cwd=` explicite ; `probe_391` par `os.chdir` |
| invocation d'un **script frère** (`subprocess.run([py, "rl_duel.py", …])`) | **13 fichiers** | 183 par `cwd=` explicite |

`probe_457` était donc **le seul** fragile sur l'axe qui a mordu. Les 13 de l'autre axe sont d'une
classe différente — l'échec y est **bruyant** (Python : *can't open file*) et **sans persistance** ;
ils ne sont **pas** corrigés ici (hors périmètre), et sont nommés en résidu `#464-r1`.

### Contre-épreuves

| épreuve | avant | après |
| --- | --- | --- |
| `--measure` depuis la racine | `rc=1`, **632 lignes** retirées d'un fichier versionné | `rc=99`, **`git status` propre** |
| `--shard 0/8` depuis la racine | `VERDICT: FAIL` (faux rouge) | `rc=99`, rien joué |
| `--shard 0/8 --list` depuis la racine | OK | OK (inchangé — le garde ne le bloque pas) |

**Par mutation** (`tests/test_457_r9_refus_d_ecrire_offline.py`, 17 tests) — chaque mutation a été
vérifiée APPLIQUÉE avant d'être jouée, un patch qui ne matche pas rendant un vert qui ne prouve
rien :

| mutation | verdict |
| --- | --- |
| garde CWD retiré de `main()` | **4 rouges** / 13 verts |
| refus d'écrire retiré de `_ecrire_mesure` | **5 rouges** / 12 verts |
| empreinte réécrite en mode incrémental | **1 rouge** |
| une écriture posée hors du foyer unique | **1 rouge** |
| *(témoin, sans mutation)* | 17 verts |

Le garde de **foyer unique** est structurel : il dérive par AST les fonctions du probe qui écrivent
un fichier et exige que l'ensemble soit exactement `{_ecrire_mesure}`. C'est lui qui rend le refus
non contournable — le vice initial était précisément que la décision s'imprimait **après** les deux
`write_text`.

## 10. `#463` — une garde d'ÉQUILIBRAGE imposait 12 min bloquantes par PR

### La mesure, et la nuance qu'elle corrige

Tout fichier de test offline **neuf** n'a pas de poids ; `bins_of` lui donne le poids **maximum**
connu (choix sûr), il déplace donc les vrais lourds et fait monter la charge maximale — sans
qu'aucun poids ne soit faux, et **sans le moindre risque de faux vert** (`bins_of` partitionne
l'ensemble quels que soient les poids). La seule sortie était `--measure`, **976,9 s / 1471 tests**.

⚠ **L'énoncé « tout fichier neuf fait rougir » est une simplification — mesuré, le déclenchement est
en `nb_neufs % 8`.** Profil figé sur la queue lourde réelle (268 / 258 / 234 / 201 / 169 s sur
110 fichiers), ratio `max(charges) / max(plancher, moyenne)` pour 0 à 8 fichiers sans poids :

| neufs | 0 | 1 | 2 | 3 | **4** | **5** | **6** | **7** | 8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ratio | 1,000 | 1,000 | 1,000 | 1,104 | **1,381** | **1,623** | **1,836** | **1,963** | 1,000 |

Seuil = 1,35. **Rouge de 4 à 7, vert de 0 à 3 et à 8** — et le ratio est **indépendant du poids des
fichiers légers** (identique à 2,0 s et 5,0 s) : il est porté par la structure, pas par les données.
Un seul fichier neuf ne bloquait donc **pas** ; c'est une tranche qui en ajoute 4 ou plus.

### L'asymétrie qui trahissait le mauvais calibrage

`logs/` est gitignoré ⇒ un agent en worktree frais **n'a aucun poids**, la garde y **SKIPPE**, et
elle ne tirait donc que dans l'arbre de l'orchestrateur — sur le chemin critique de livraison. Une
garde dont le gisement n'existe que chez celui qui livre n'est pas une garde, c'est un péage.

### Les DEUX remèdes, cumulés — et pourquoi les deux

1. **Mesure incrémentale** (`--measure-missing`) : ne chronomètre que les fichiers **sans poids**,
   **fusionne** dans le JSON existant, et **purge** les clés hors périmètre (un test supprimé ne
   doit pas gonfler le `defaut` de `bins_of`). Elle **n'écrit PAS l'empreinte** : `_commit` horodate
   l'empreinte **entière**, la rafraîchir après avoir joué 2 fichiers prétendrait une fraîcheur
   qu'elle n'a pas et transformerait `impacted_files` en faux vert. C'est l'asymétrie que le fichier
   documentait déjà, appliquée. Corollaire d'implémentation : l'audit hook global de `_FilesPerTest`
   n'est **plus installé** en mode incrémental.
2. **Dégradation de la garde** : le critère porte désormais sur les **seuls fichiers pesés**
   (`equilibre_des_bins`), et les fichiers sans poids sont **rapportés**, pas opposés. Le nom du
   test l'annonçait déjà — « quand les poids existent ».

**Un seul des deux ne suffit pas.** Le remède 1 seul laisse la garde bloquante pour quiconque ne
lance pas la mesure (et un agent en worktree frais ne peut pas la lancer utilement : ses poids
meurent avec son worktree). Le remède 2 seul laisse le mur se dégrader **en silence** — d'où
l'impression, à chaque shard, du compte de fichiers sans poids et de la commande qui les mesure.

### Contre-épreuves

- **La garde MORD toujours** (`test_le_critere_d_equilibre_REJETTE_une_partition_desequilibree`),
  sur deux montages indépendants : (a) la partition **md5** du repli, sur un jeu où LPT équilibre —
  c'est le gisement historique (4 lourds concentrés dans `s7`, 106 s contre 4,8 s) ; (b) un
  déséquilibre **insécable mais réel à poids complets** — 9 fichiers égaux pour 8 bins, ratio 1,78.
- **La dégradation tient quel que soit `nb_neufs`** (paramétré 0/3/4/7/8), et les cas 4 et 7
  vérifient que l'**ancien** critère rougissait bien : sans cela l'assertion serait un vert vacueux.
- **Mutation** : ancien critère restauré ⇒ **1 rouge** (`test_des_fichiers_SANS_poids_…`).

### Résidus

- **`#464-r1`** — **13 fichiers de `scripts/python/**` invoquent un script frère par chemin relatif
  sans `cwd=`** (`_probe_overwatch`, `predict_samples`, `predict_sweep`, `probe_106_*`,
  `probe_111_*`, …). Fragilité réelle au CWD, mais l'échec y est **bruyant** et **sans
  persistance** — aucune écriture versionnée en jeu. Non corrigé (hors périmètre). Le patron sûr
  est déjà majoritaire dans le dépôt : **183** appels passent `cwd=` explicite.
- **`#463-r1`** — **rien ne mesure les poids d'un fichier neuf automatiquement.** Un shard ne peut
  pas le faire : les 8 shards tournent **en parallèle** et écriraient le même JSON (c'est #455 dans
  l'autre sens). `--measure-missing` reste donc un geste **explicite**, et son oubli coûte du mur,
  jamais un verdict.
- **`#463-r2`** — **la marge de 1,35 n'a pas été re-dérivée.** Elle est héritée de #457-r6 et
  n'était contrainte par aucune mesure ici ; le test la porte désormais en constante nommée
  (`MARGE_EQUILIBRE`), ce qui la rend au moins visible et mutable.
