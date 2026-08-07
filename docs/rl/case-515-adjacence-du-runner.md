# #515 (résidu `#497-r1`) — l'adjacence du RUNNER est une ÉNUMÉRATION, pas un disque

**État : LIVRÉ.** Foyer réparé, confronté LIVE sur le montage qui l'avait révélé, sur
`rnca9r7q6c`. `engine/dsl/base.py::_within` décidait l'appartenance par `hexgeo.distance <= r` ;
le natif énumère la liste d'adjacence **stockée** puis applique une porte d'élévation.

## 1. Le natif — DEUX itérateurs, et un seul est une couronne

`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, structure LUE :

    elev0 = tile[+0x20][+0x18];                                    // d__8+0x48, lu UNE fois
    foreach (nid in tile[+0x30][+0x10])                             // ConnectivityComponent.Neighbours
        t = state.GetTileEntity(nid); if (t == null) continue;
        if (!allowTemporary  && IsTemporary(t))         continue;
        if ( onlyWalkable    && !IsWalkable(t, true))   continue;
        if ( onlyEmptyOrStep && !IsEmptyOrSteppable(t)) continue;
        if (Math.Abs(elev0 - t[+0x20][+0x18]) < 2) yield return t;  // porte INCONDITIONNELLE

Deux étages, dans cet ordre : une **énumération** de liste stockée, puis une **porte**. Signature
lue dans `data/symbols/rnca9r7q6c/frida/methods.tsv` :
`IterateAdjacentTiles(from, onlyEmptyOrSteppable, onlyWalkableTiles, allowTemporary)`.

**La porte est SYMÉTRIQUE, portée par la PAIRE — jamais par l'arête.** Elle prend la valeur
absolue (`iVar4 = -iVar10; if (iVar4 < 0) iVar4 = iVar10; if (iVar4 < 2)`). Le substrat l'est
aussi par construction : `IdunBattle.Operations.InitializeConnectivityOperation$$Execute` exige
`TileComponent$$HasEdge(e)` chez la tuile **et** `HasEdge((e+3) % 6)` chez le voisin — d'où les
**0 arête one-way** mesurés par #433-r4-r1-r4-r2 sur quatre boards.

**Ce que le natif ne fait PAS, et c'est la BORNE de la réparation.**
`IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` (le rayon
quelconque) est une **triple boucle en coordonnées cube** (`x`,`y`,`z` avec `x+y+z == 0`) résolue
par `IdunBattle.Entities.StateExtensions$$GetTileAt` : **aucune liste stockée, aucune porte
d'élévation**. Unifier les deux primitives aurait été un bug, pas une réparation — c'est
exactement ce que `test_515_surrounding_traverse_la_marche` interdit.

## 2. Le rayon de souffle — mesuré avant l'édition

`probe_515_adjacence_rayon_de_souffle.py`, cinq étages, offline pur.

| étage | mesure |
|---|---|
| SITES (AST) | `order='adjacent'` **61** instanciations, `order='surrounding'` **22** (hors périmètre) |
| TOPOLOGIE (675 boards) | **17 204** arêtes de couronne refusées sur **196 454** (**8,76 %**) |
| | la porte MORD sur **586 boards / 675** (**86,8 %**) |
| MONOTONIE | **0** violation d'inclusion : la réparation ne peut que RETIRER |
| RE-JEU | **23** fichiers CHAUDS, 23 tièdes, 0 inerte, 143 indéterminés |

Les « **294** call-sites » du backlog étaient un **grep textuel** ; l'AST en compte **61** qui
instancient réellement un sélecteur `order='adjacent'` (le grep large rendait 450, docstrings
comprises). C'est cette mesure-là qui a rendu la tranche jouable.

**Contrôle croisé indépendant** : la mesure offline (élévations du BC re-dérivées, porte rejouée)
retrouve sur `MC1_67` exactement les **18 arêtes / 11 tuiles** que #497 avait mesurées LIVE sur le
`boardGraph` capté. Deux voies disjointes, même chiffre — donc sur ce board la porte explique la
**totalité** de l'écart, sans refus `HasEdge` résiduel. (L'offline **minore** en général : il ne
voit pas `HasEdge`.)

**Le périmètre de re-jeu est DÉRIVÉ, en deux crans.** Le cran BOARD seul rend **110** fichiers
sensibles — inexploitable, parce que presque tout montage utilise `MC1_67`, où la porte mord. Le
cran POSITION (le fichier écrit-il un couple `(col,row)` qui **tombe** sur une tuile touchée ?)
descend à **23**. Ce cran est **exact**, pas approché : la porte étant symétrique, les deux bouts
de chaque arête perdue sont dans l'ensemble des tuiles touchées.

## 3. La réparation

Foyer unique neuf : `engine/dsl/base.py::_adjacent_tiles_native(board, centers)`, **tri-état** —
`None` = aucun centre résolvable (repli géométrique nommé, permissif) ; `[]` = centre résolu,
zéro voisin, et **c'est exact**. `_within` en tire l'**ENSEMBLE**, `_tile_enum_rank` l'**ORDRE** :
avant, l'ordre venait déjà de la liste stockée et l'appartenance de la géométrie — deux sources
pour une même relation.

Le tri-état n'est pas une précaution : un board réel produit `[]`. `C1_74` porte deux `Water`
(`(2,5)` et `(4,5)`, élévation 1) entourées de 3 et 4 — tous leurs voisins stockés sont hors
portée. Confondre `[]` et `None` aurait rendu la réparation **inerte précisément sur les tuiles
qu'elle vise** (le vice de `#381-r3`, qui inventait six voisins là où le natif n'en a aucun).

**Le substrat porte déjà les deux étages** : `Board.neighbours_native` lit le champ
`boardGraph.neighbours`, capté par `BattleQuery$$GetAdjacentTiles(t, false, false, true)` — donc
par ce même itérateur, filtres de terrain OFF et porte ON. Identité déjà établie
(`Board.base_add_neighbours`) : `neighbours == connectivity ∩ {arêtes de |dElev| < 2}`. Rejouer la
porte dans `_within` aurait été redondant, pas plus fidèle.

## 4. Ce que la confrontation a mesuré

`probe_497_silent_death.py --variantes`, montage inchangé (même board, même seed, mêmes positions
forcées, MT offline calé sur le MT live) :

| scénario | avant | après |
|---|---|---|
| nominal, `branche`, `cap`, `mort` | bit-exact | **bit-exact** (inchangés) |
| `elevation` (marche 2→4) | port `[81, 83, 85, 87]` vs natif `[81]` | **`[81]` des deux côtés** |

9 706 PV de dégât fantôme supprimés sur ce seul montage. Les quatre autres scénarios ne bougent
pas : le résidu portait sur `_within`, et sur rien d'autre du port de 1068.

## 5. Un ACCORD qui était le produit de deux fautes qui se compensaient

`tests/engine/runner/test_433_r3_r1a_occupancy_offline.py` a rougi immédiatement
(`AdjacentUnits` → `[]`). **Ce n'était pas une régression** : son `_flat_board()` posait
`"neighbours": []` sur toutes les tuiles d'un plateau censé être entièrement connecté — une
déclaration **fausse**, que l'ancien `_within` ne lisait pas. Les deux fautes s'annulaient.

Réparé côté **montage** (le champ porte désormais la géométrie even-q, ce qu'un plateau plat
produit réellement), jamais en affaiblissant la primitive. L'axe testé par ce fichier
(l'empreinte multi-hex) est inchangé : **26/26** verts après.

Trois autres fichiers posent `"neighbours": []` (`test_462_r4b_..._tile_owner_gate_live.py`,
`test_302_5_mow_position_offline.py`, `test_448_r1_stormboyz_port_offline.py`) — tous verts, ils
ne passent pas par la voie `order='adjacent'`.

## 6. Validation

* **Garde neuve, dans le bon sens** — `#497` n'assertait rien, et c'était juste : un test écrit à
  ce moment-là aurait figé le bug.
  * `tests/engine/runner/test_515_adjacence_elevation_offline.py` (**11**) — le foyer, sa
    **contre-épreuve** (l'ancienne primitive rejouée doit inverser le verdict, et le test vérifie
    que la mutation a mordu), son tri-état sur quatre chemins, la **borne**
    (`surrounding` traverse la marche ; `adjacent` au rayon 2 reste géométrique), la monotonie sur
    les 675 boards **avec témoin de non-dégénérescence**, et le contrôle croisé offline/live.
  * `tests/engine/runner/test_515_adjacence_elevation_live.py` (**4**) — le montage `elevation`
    retourné, contre l'oracle NATIF. Deux crans de non-dégénérescence : la porte doit refuser des
    arêtes **sur le `boardGraph` capté**, et les quatre orks doivent être alignés à distance hex 1
    (sans quoi l'arrêt à un maillon ne prouverait rien — un montage à un seul ennemi rendrait le
    même `[81]`).
* **Périmètre de re-jeu dérivé** (§2), joué : voir §7.
### Résidu `#515-r1` — le filtre `onlyWalkableTiles` du sélecteur n'est PAS dans le substrat

**Non couvert par cette tranche, et c'est un axe DISTINCT de la porte d'élévation.**
`IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` appelle son itérateur avec les
littéraux `(tile, 0, 1, 1)` — soit, contre la signature lue dans `frida/methods.tsv`
(`IterateAdjacentTiles(from, onlyEmptyOrSteppable, onlyWalkableTiles, allowTemporary)`),
**`onlyWalkableTiles = true`**. Le capteur du `boardGraph`, lui, utilise `(t, false, false, true)`
(#148). Le champ `neighbours` sur-atteint donc encore le sélecteur, des tuiles **non walkable**.

Ce que la lecture d'`IdunBattle.Entities.TileExtensions$$IsWalkable(tile, checkFog)` donne, et qui
sépare deux sous-cas :

* le composant `tile[+0x40]` avec `[+0x10] != 0` — le mur. `IsWalkable` **ne lit pas l'occupant**,
  donc pour la voie UNITÉ il faudrait qu'une unité se tienne sur un mur. Vraisemblablement inerte.
* `checkFog` (passé à `true` par l'itérateur) → `tile[+0x20][+0x40] == 0`, le **brouillard**. Une
  tuile embuée **peut** porter une unité, et là le filtre mordrait pour de bon. Le `boardGraph` ne
  publie pas ce flag — c'est le canal manquant.

**Rien de tout cela n'est mesuré**, et le sens de l'écart est le même que celui qu'on vient de
réparer (permissif). Pour le trancher il faut soit publier `isFogged` dans le `boardGraph`, soit
mesurer live si une unité peut occuper une tuile refusée par `IsWalkable`. Cette tranche ne le
fait pas et n'a rien changé sur cet axe.

* **Autres points NON couverts** : `MatchesUnitSelectionType` sur la résolution d'occupant (résidu
  `#433-r3-r2`, préexistant) ; les 143 fichiers `indéterminés` du cran de re-jeu (ni board ni
  position littérale lisible — jamais classés hors périmètre, seulement non priorisés).
