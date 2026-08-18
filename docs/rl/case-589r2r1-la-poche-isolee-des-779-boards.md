# case-589-r2-r1 — la poche isolée des 779 boards

`#589-r2` avait trouvé le seul régime où `n_C < n_G` : quand la **beeline** ne rend aucun chemin
entre deux waypoints, `IdunBattle.Core.Services.MovementQuery$$GetConnectedPathTo` **déréférence un
nul** alors que le port écrivait `for mid in (sub or [])[1:-1]` et comptait le saut pour **1**
arête. Il l'avait mesuré non atteint sur **2** boards, en disant que **285 des 287 boards à
`Bridge`** ne l'étaient pas — parce que chaque mesure exigeait une **capture live** (le champ
`connectivity` n'existe que sur une bataille montée).

## 1. Ce qui lève la borne : la connectivité devient DÉRIVABLE sans le jeu

`IdunBattle.Operations.InitializeConnectivityOperation$$Execute`, relu verbatim :

    foreach (tile) foreach (edge in Enum.GetValues(typeof(Edge)))            // 6 valeurs
      if (!tile.TileComponent.HasEdge(edge))                                  continue
      (col,row) = (PositionComponent.ColumnAt(edge), PositionComponent.RowAt(edge))
      if (!BoardComponent.IsPositionInside(col,row) || grille[col,row] == 0)  continue
      if (!voisin.TileComponent.HasEdge((n/2 + edge) % n))                    continue   // n=6 -> +3
      connectivity.Add(nid)

**Aucune élévation.** Et `IdunBattle.Entities.Components.TileComponent$$HasEdge` n'est qu'un
`Contains` sur le tableau stocké à `TileComponent+0x20`, tableau que
`IdunBattle.Operations.AddTileOperation$$RotateTileEdges` a fait tourner de `Rotation` crans.

⇒ le masque d'arêtes est une fonction de **(TileId, Rotation, ForceUnplayable)**. Il y en a **63**
sur les 779 boards de `data/boards/**` (11 `TileId`), et **15 boards** suffisent à tous les
rencontrer.

## 2. L'inversion, sa borne, et le contrôle qui la rend crédible

On lit le `connectivity` capté et on **inverse** : chaque arête présente atteste l'arête chez les
DEUX tuiles. C'est une **borne inférieure** (une arête que nulle configuration ne réalise reste
invisible), et c'est ce qui rend le tri sûr :

* **connexe dérivé ⇒ connexe réel** ⇒ le régime y est **impossible** ;
* **morcelé dérivé ⇒ CANDIDAT** seulement, à confirmer par une capture.

La borne est refermée par la **rotation**, contrainte structurelle **vérifiée** et non postulée :
`Bridge` l'exhibe seul (rot 0 = {NE,SW}, rot 1 = {SE,NW}, rot 2 = {N,S}, période 3), donc
`masque(t, r) = masque(t, 0)` décalé de `+r`. Le sens du décalage est lu dans les données.

**Validation croisée** : la connectivité dérivée est comparée arête par arête à l'observée sur
**20 boards**, dont **3 hold-out** tenus hors de l'ajustement (`C1_74`, `C3_14`, `MC1_67`) —
**0 manquante, 0 en trop** partout. Avant consolidation, les hold-out `C3_14` et `MC1_67` rendaient
4 manquantes chacun et **0 en trop** : exactement la direction que la borne prédit.

La **marchabilité** se dérive de la même clé (**63** tranchées, **0 ambiguë** sur 20 captures).
Entrée versionnée : `data/symbols/<build>/metadata/tile_edges.tsv`.

## 3. La mesure sur les 779

| | |
|---|---|
| boards mesurés | **779** (0 non mesuré : aucune clé de tuile hors table) |
| connexes | **778** ⇒ régime **impossible** |
| morcelés | **1** — `Waves_Xenos_13`, composantes `[69, 1]` |

Le premier tour en donnait **2** ; `Waves_Imperial_13` a été **réfuté par sa capture** (10 arêtes
que la borne ratait, toutes sur `BrokenIce` *unplayable*, seule clé à témoin unique), puis absorbé
dans l'ajustement.

La poche de `Waves_Xenos_13` est la tuile `(3,4)` : un `Block`, **non marchable**, au
`ConnectivityComponent` **vide**. Sur ce board :

| étage | mesure |
|---|---|
| [1] beeline | 4476 couples à `d_hex > 1`, **126 sans chemin** |
| [2] vol | 4284 sauts à recoudre, **61 sans chemin beeline** |
| [3] **dont issus d'un MOUVEMENT LÉGAL** | **0** |

`GetConnectedPathTo` n'est appelé que par `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved`,
donc **après** un déplacement : ses deux extrémités sont marchables. Sous cette contrainte le
compte tombe à zéro. **Chiffres identiques en capture live et en board DÉRIVÉ** — toute la chaîne
est offline-reproductible.

## 4. Le correctif : une LEVÉE, qui est à la fois le mirror et le refus exécutable

`get_connected_path_to` lève `BeelineSansChemin` au lieu d'écrire `(sub or [])[1:-1]`. La case-doc
`#589-r2` posait l'alternative « établir que le graphe est connexe là où un volant atterrit — et
alors **nommer** la dégradation — ou rendre le port fidèle » : les deux se rejoignent, une prose
n'arrêtant pas un comportement.

⚠ **Ne pas confondre les deux absences** : celle du `path` a une branche native
(`if (path == null) return new List { from, to };`) et se dégrade ; celle du `sub` n'en a aucune.

## 5. Contre-épreuves et non-régression

| mutant | mesuré |
|---|---|
| retour à `(sub or [])` | étage 1 **rouge** |
| `Block` déclaré marchable | `sauts_sans_legaux` **0 → 126** |
| `Grass rot=0` privé de sa direction `N` | boards morcelés **1 → 11** |

Rejoués verts après le correctif : `test_589r1_tiles_moved_consumers_offline.py` +
`test_448_r1_r1_r1_r1_flying_tiles_moved_offline.py` (**38 passed**),
`probe_589r1 --only SCAN --board C1_74` (**PASS**), `probe_589r2 --only INV / --only BORNE /
--only GATE --board C1_74` (**PASS**, 3590 sauts réellement recousus traversent la levée).

## 6. Reproduction

    python probe_589r2r1_beeline_sans_chemin.py --only INV
    python probe_589r2r1_beeline_sans_chemin.py --only CAPTURE                 # LIVE, 1 runner/board
    python probe_589r2r1_beeline_sans_chemin.py --only MASQUES --boards <17> --holdout <3> --regenerer
    python probe_589r2r1_beeline_sans_chemin.py --only SCAN                    # OFFLINE, 779 boards
    python probe_589r2r1_beeline_sans_chemin.py --only REGIME --board Waves_Xenos_13 --derive
    python -m pytest tests/engine/entities/pathfinding/test_589r2r1_beeline_sans_chemin_offline.py

## 7. Ce qui n'est PAS couvert

* **L'hypothèse « les deux extrémités sont marchables »** est lue au natif pour le mouvement
  joueur (`GetMovableTilesFor` → `RemoveAll(!IsMovableTile)`), **pas** re-vérifiée pour la route
  DSL `MoveUnit`/`FlyUnit`, dont la destination vient d'un sélecteur → résidu **`#589-r2-r1-r1`**.
  Le pire cas est borné : 1 board sur 779, et la levée dit exactement où.
* **Le corpus est celui de `data/boards/**` au build courant.** Un board livré plus tard n'est pas
  mesuré tant que le balayage n'est pas rejoué — l'étage 3 du cliquet le fait à chaque passe.
* **Les portes (`HulkDoor`)** sont traitées comme des tuiles statiques : si le jeu ouvre/ferme des
  arêtes en cours de bataille, la table ne le voit pas. Aucune des 20 captures ne l'exhibe.
* **Aucune confrontation live du correctif lui-même** : par construction, il n'existe aucun
  montage jouable qui l'atteigne — c'est le résultat de la tranche, pas son angle mort.
