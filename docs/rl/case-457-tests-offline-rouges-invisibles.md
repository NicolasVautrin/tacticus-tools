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
