# #433-r4-r1-r4-r2 — `is_adjacent` énumère la liste STOCKÉE, plus la couronne hex

**FERMÉ.** `battle_query.is_adjacent` porte désormais les **deux** étages de
`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` : l'ÉNUMÉRATION
de la liste stockée (`neigh_by_pos`) puis la PORTE d'élévation (`elev_by_pos`, #433-r4-r1-r4).
**62 call-sites branchés**, 16 tests offline (**6 mutations → 6 rouges**, arbre restauré
bit-exact), et **confronté live à un oracle NATIF INDÉPENDANT** du canal (§4).

Le risque annoncé — « exposer les ~18 arêtes one-way de la capture » — est **RÉFUTÉ**, pas
contourné : **0 arête one-way** dans les trois vues, sur quatre boards (§2), et le décompilé dit
pourquoi (§1). Le solde du basculement est **strictement non négatif** : il ferme **4** arêtes
permissives sur `C1_74`, **38** sur `C3_14`, et n'en ouvre **aucune**.

## 1. Le décompilé — la liste est SYMÉTRIQUE par construction

`IdunBattle.Operations.InitializeConnectivityOperation$$Execute`, remis en C# :

```
foreach (tile in state.<tuiles>) {
    var neighbours = new List<int>();
    for (int e = 0; e < Enum.GetValues(typeof(TileEdge)).Length; e++) {   // n = 6
        if (!tile.TileComponent.HasEdge(e))                     continue;   // (1) MOI
        (col, row) = (pos.ColumnAt(e), pos.RowAt(e));
        if (!board.IsPositionInside(col, row))                  continue;   // (2)
        var id = board.tiles[col, row];  if (id == 0)           continue;   // (3)
        if (!state.GetEntity(id).TileComponent.HasEdge((n/2 + e) % n)) continue;  // (4) L'AUTRE
        neighbours.Add(id);
    }
    tile.ConnectivityComponent.Neighbours = neighbours;                     // +0x10
}
return ConnectTeleportTiles(this, teleportTiles);
```

**`n = 6`** est LU, pas supposé : `IdunBattle.Operations.AddTileOperation$$RotateTileEdges` fait
`edges[i] = (rotation + edges[i]) % 6`. Donc `opp(e) = (e + 3) % 6` est une **involution**, et le
critère `(1) ∧ (4)` est symétrique. `(2)` et `(3)` portent sur le voisin, or les deux tuiles
existent — l'itération ne parcourt que des tuiles du plateau. `ConnectTeleportTiles` n'écrit que
`ConnectivityComponent+0x18` (le jumeau de téléport), **jamais** la liste `+0x10`, et il l'écrit
**dans les deux sens**.

**Le graphe est STATIQUE pour toute la bataille** — donc mémoïser le canal est sûr, et un canal
capté une fois ne peut pas se périmer. C'est LU, pas supposé : `IdunBattle.Entities.Components.TileComponent`
n'expose que `HasEdge` / `.ctor` / `.cctor` / `Copy` / `GetComponentId` / `ToString` — **aucun
mutateur d'élévation** (`+0x18` est posé au ctor) ; `ConnectivityComponent` de même — ses seuls
écrivains sont `InitializeConnectivityOperation$$Execute` (`+0x10`, une fois, via
`Core.Services.OperationProcessor$$InitializeConnectivity`) et `$$ConnectTeleportTiles` (`+0x18`).
⚠ Corollaire : une tuile **TEMPORAIRE** apparue APRÈS cette passe n'a pas de connectivité. Le port
la fait retomber sur sa couronne hex (repli par clé) — plus permissif que le natif, donc dans le
sens de dégradation déjà connu, jamais une restriction inventée.

⇒ `Neighbours` est symétrique. La porte du capteur (`|dElev| < 2`) l'est aussi (valeur absolue).
**Le champ `boardGraph.neighbours` ne peut donc pas porter d'arête à sens unique** — la mention
« ~18 arêtes one-way, quirks de capture aux bords » du docstring de `board.py` datait des flags
`(true,true,true)` d'avant #148, dont `onlyEmptyOrSteppable` teste la **tuile voisine seule** :
*celui-là* était asymétrique. Ligne corrigée.

## 2. La mesure — `probe_433r4r1r4r2_is_adjacent_substrat_live.py`

Trois vues, et le discriminant est la comparaison **directe des deux substrats** (leçon de
`#589-r1` : un critère qui mélange une 3ᵉ valeur noie le cas utile) :

    G = couronne hex even-q          N = `neighbours` = C ∩ {|dElev| < 2}
    C = `connectivity` (brut)        G_gated = G ∩ {|dElev| < 2}   <- ce que le port FAISAIT

| board | tuiles | one-way G/C/N | PERMISSIF (`G_gated \ N`) | RESTRICTIF (`N \ G_gated`) | port avec/sans canal |
|---|---|---|---|---|---|
| `C1_74` (2 `Bridge`) | 63 | **0/0/0** | **4** | **0** | 0 / 4 |
| `C3_14` (15 `Bridge`) | 63 | **0/0/0** | **38** | **0** | 0 / 38 |
| `MC1_67` | 63 | **0/0/0** | 0 | 0 | 0 / 0 |
| `C6_25` (murs) | 63 | **0/0/0** | 0 | 0 | 0 / 0 |

Le permissif se lit **entièrement** comme `(G \ C) ∩ {|dElev| < 2}` (cran vérifié : une 3ᵉ cause
rougirait), il va **par paires** (0 arête sans sa réciproque), et il est **exclusivement** sur des
`Bridge`. `C1_74` est le cas le plus PAUVRE, pas le cas typique — même contraste que #589-r1.

## 3. Le fix — un canal, un accès, deux étages

* **`battle_query.is_adjacent(tile, pos, elev_by_pos, neigh_by_pos)`** : énumération PUIS porte,
  dans l'ordre du natif. Rejouer la porte sur le canal capté est **idempotent** (`N` la porte
  déjà) et c'est le mirror, pas une défense ajoutée. Les trois dérivées (`are_entities_adjacent`,
  `count_adjacent`, `count_adjacent_matching`) la propagent.
* **`battle_query.neigh_map(ctx)`** — accès UNIQUE, tri-état. Les contextes du port ont **trois
  formes** (`AiDecisionContext` et `Scene` = objets, `tile_leaf_ctx` = dict) : un accès écrit à la
  main à chaque call-site retomberait sur `AttributeError` chez l'une ou l'autre.
* **Le canal se DÉRIVE du board**, jamais ne se stocke en double :
  `entities/pathfinding/board.py::adjacent_neigh_by_pos` (foyer, tri-état), lu par
  `DslContext.__post_init__` et la property `Scene.neigh_by_pos`. Même parade que #433-r4-r1-r4 :
  brancher au constructeur empêche le prochain de rouvrir le trou en silence.
* **TRI-ÉTAT partout** : `None` = pas de canal → repli GÉOMÉTRIQUE nommé (le comportement d'avant,
  permissif et documenté). Jamais `{}`, qui se lirait « aucune tuile n'a de voisin » et rendrait le
  prédicat faux partout — dégradation restrictive massive, le vice de `#381-r3`. La granularité est
  **la clé** : une tuile hors capture retombe sur la géométrie pour ELLE SEULE.
* **62 call-sites** branchés (35 fichiers). Le cliquet `probe_433r4r1r4r2_neigh_channel_wired.py`
  (dans la banque) garde l'**invariant de couple** : qui passe l'élévation passe le voisinage.

⚠ **Trois voisinages coexistent sur un `Board` et ne sont PAS interchangeables** (#381-r3) :
`neighbours_native` (liste stockée + porte — celui-ci), `base_add_neighbours` (connectivity BRUT,
le PATHFINDING), `neighbours_geometric` (la couronne, le VOL).

## 4. Validation

**OFFLINE — `test_433r4r1r4r2_is_adjacent_substrat_offline.py`, 16 passed.** Axes : le montage
discriminant, l'arête hors liste dans les deux sens, le repli géométrique, le tri-état (canal
absent / clé absente / liste vide), l'indépendance des deux étages, la dérivation
`DslContext`/`Scene`, `neigh_map` sur les trois formes, la propagation aux trois dérivées et la
survie du court-circuit d'identité (#433-r1).

**Contre-épreuve par MUTATION** (patch vérifié mordant, arbre restauré, sha256 bit-exact) :

| mutation | résultat |
|---|---|
| canal ignoré par `is_adjacent` (l'état d'AVANT) | rc 1 — **8 failed** / 8 passed |
| dérivation `DslContext` retirée | rc 1 — 1 failed |
| canal absent coté `{}` au lieu de `None` | rc 1 — 1 failed |
| tuile sans champ `neighbours` cotée `[]` au lieu d'omise | rc 1 — 1 failed |
| porte d'élévation retirée après la bascule | rc 1 — 2 failed |
| `Scene` ne dérive plus son canal | rc 1 — 1 failed |

**LIVE — l'oracle est INDÉPENDANT du canal**, et c'est le point qui compte :
`neigh_by_pos` dérive de `boardGraph.neighbours`, donc confronter le port à ce même champ ne prouve
que le CÂBLAGE. L'oracle retenu est le **splash de `FragBomb`** (1017, `astraBullgryn`) —
`splash = AdjacentUnits(Target) - Caster`, donc `AdjacentTiles` puis `Units`, donc le MÊME
itérateur — lu dans les **events de dégât d'une bataille**.

`tests/engine/runner/test_433r4r1r4r2_adjacent_tiles_bridge_live.py`, **4 passed** (`C3_14`,
arête `(1,1)–(1,2)` **dérivée du board**, jamais hardcodée) :

| lecture | verdict |
|---|---|
| **NATIF** | frappe le TÉMOIN (voisin réel), **n'a jamais touché** le FANTÔME (voisin géométrique hors liste) |
| **port AVEC canal** | `is_adjacent(a, fantôme) = False`, `is_adjacent(a, témoin) = True` — **ACCORD** |
| **port SANS canal** | `is_adjacent(a, fantôme) = True` — **DÉSACCORD** |

Le témoin est ce qui interdit de lire « fantôme épargné » comme un splash simplement inerte ; le
cran de montage vérifie que la porte d'élévation n'explique **pas** l'écart (`|dElev| < 2`).

**Régression** : 424 tests offline verts sur 28 fichiers (famille 433, substrat DSL, sélecteurs,
pathfinding, playbooks touchés). Un seul rouge, **de MONTAGE** : le spy de
`test_433_r4_r2_adjacency_foyer_offline` recopiait l'arité du foyer (`def spy_are(a, b, e=None)`)
— rendu **transparent** (`*a, **kw`), il compte des appels sans figer une signature.

## 5. Résidus NOMMÉS

* **`#433-r4-r1-r4-r2-r1` — quatre foyers voisins partagent le vice et ne sont PAS branchés** :
  `battle_query.in_arc` / `count_enemies_in_arc` (ring-1 via `is_adjacent`),
  `battle_query.is_charging` (via `are_entities_adjacent`) et `battle_query.newly_adjacent_ids`
  (mirror de `MoveUnitOperation$$UpdateCharging`, `hexgeo.distance == 1` nu). Chacun a ses propres
  appelants, donc son propre rayon ; aucun n'est dans le périmètre nommé de ce résidu.
* **`#433-r4-r1-r4-r2-r2` — `playbook/noncomparable/heroic_fusillade.py` appelle `count_adjacent`
  SANS élévation ni voisinage** (`bq.count_adjacent(tpos, others)`). Hors gisement du cliquet par
  construction (il garde le COUPLE) : c'est une dégradation antérieure, à trancher sur son propre
  décompilé.
* **`#433-r4-r1-r4-r2-r3` — le gisement n'est chiffré que sur 4 boards.** `Bridge` apparaît sur
  **287** des 779 boards ; les 283 autres ne sont pas mesurés, et le contraste 4 vs 38 dit que
  l'amplitude n'est **pas** estimable depuis un board.
* **`#433-r4-r1-r4-r2-r4` — l'aval n'est pas mesuré.** On a montré que la primitive change de
  verdict et que le natif est d'accord ; on n'a **pas** mesuré de quel montant une utilité de
  playbook bouge quand un ennemi cesse d'être compté adjacent.

## 6. Reproduction

    python probe_433r4r1r4r2_is_adjacent_substrat_live.py
    python probe_433r4r1r4r2_is_adjacent_substrat_live.py --board C3_14
    python probe_433r4r1r4r2_neigh_channel_wired.py
    python -m pytest tests/engine/test_433r4r1r4r2_is_adjacent_substrat_offline.py
    python -m pytest tests/engine/runner/test_433r4r1r4r2_adjacent_tiles_bridge_live.py
