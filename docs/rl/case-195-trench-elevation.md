# Case #195 — Élévation effective des tuiles Trench = champ BC − 1 (prémisse « −1 » raffinée)

**Status : RESOLVED (session 23). Prémisse initiale (« Trench = −1 par convention, composant
ElevationComponent absent ») RÉFUTÉE par mesure. Règle réelle mesurée sur 6 boards : Trench
effectif = champ BC − 1. Le board ENGINE numérique (boardGraph) baked déjà ce −1 (prédiction
bit-exacte #182/#184) → aucun bug numérique. Seul le board dérivé du champ BC brut
(`board.py::Board`, oracle-card, élévation latente/non consommée) était faux → aligné.**

## Prémisse initiale (partiellement fausse)
Le diag #194 (C2_19) avait noté : tileMeta live donne élévation −1 pour les Trench alors que le
champ BC `Board.Tiles[..].Elevation` dit 0, et hypothèse « `GetElevation @180ec4fd0` rend −1 si
l'ElevationComponent est ABSENT → les Trench n'en ont pas ». **Réfuté** : sur C2_16 les Trench
sont à élévation **1** (valeur positive), donc le composant EXISTE et porte une vraie valeur.

## Ground truth (LIVE boardGraph vs champ BC, 6 boards, probes 195)
Le −1 de C2_19 n'est pas une convention TileId mais la VALEUR (0 − 1). Règle uniforme :

| Board | champ BC Trench | live Trench (boardGraph=tileMeta) | Δ |
|---|---|---|---|
| C2_19 | 0 | −1 | −1 |
| C2_20 | 0 | −1 | −1 |
| C2_17 | 1 | 0 | −1 |
| C2_18 | 1 | 0 | −1 |
| C2_16 | 2 | 1 | −1 |
| C2_32 | 2 | 1 | −1 |

**Règle : Trench effectif = champ BC − 1** (terrain CREUSÉ d'un niveau), uniforme, SANS clamp.
TOUS les autres TileId (Grass/Swamp/DryBush/Water/Bridge/Block) gardent leur champ BC à
l'identique (confronté par-TileId, boardGraph.elev == tileMeta.elev, 0 mismatch). NB : le JSON
`data/boards/global/*.json` est en repère par-position POTENTIELLEMENT DÉCALÉ du live pour
certains boards (C2_16), mais les DISTRIBUTIONS par-TileId concordent → la règle se lit
par-TileId, pas par-position.

## Native (VAs gqfc5mff6c)
`TileExtensions.GetElevation @180ec4fd0` : `if HasComponent(tile, ElevationComponent) → return
*(component + 0x18) ; else return -1`. Le composant est PRÉSENT pour les Trench (valeur BC−1
écrite au board-build) — le sentinel −1 « absent » n'est PAS le chemin observé (C2_16 Trench=1
prouve le composant présent). Capté par `readTileComponent` (frida match-state.ts,
`COMP_FIELD.tileElevation`) → boardGraph/tileMeta exposent la valeur EFFECTIVE (BC−1 déjà appliqué).

## Où ça compte (et où non)
- **Board ENGINE numérique** (`engine/entities/pathfinding/board.Board`) : construit depuis le RPC
  `boardGraph` (LIVE) → élévation EFFECTIVE (Trench = BC−1) DÉJÀ correcte. Toute la prédiction
  positionnelle (ElevationBonus #98, CanMeleeAttackOverElevationDifference #187,
  `battle_query.are_tiles_adjacent` |Δelev|<2) lit ce board → **correcte, bit-exacte** (#182/#184).
  Le `Scene.from_state` runner lit `state.board` = capture boardGraph live → correct aussi.
  **AUCUN fix engine requis, aucun risque de régression** (touched here = board.py seulement).
  ⚠ NE PAS appliquer le −1 dans `pathfinding.board.Board` : il consomme boardGraph où BC−1 est
  DÉJÀ baked → double soustraction (Trench −2).
- **Board dérivé du champ BC brut** (`scripts/python/board.py::Board`) : SEUL lecteur du champ BC
  `Elevation` (grep exhaustif : tout le reste lit `elevation` d'une source live). Il alimente la
  carte ASCII oracle ; son élévation est **latente** (l'oracle ne consomme pas l'élévation — grep
  `oracle.py` : 0 hit). Il rendait Trench = champ BC brut (0/1/2) au lieu de BC−1 → **aligné** ici.

## Fix
`scripts/python/board.py` : helper `_effective_elevation(tile_id, bc_elevation)` = `bc − 1 si
TileId=="Trench" sinon bc`, appliqué au parse (`Board.__init__`). Docstring = règle mesurée + VAs +
avertissement « ne pas appliquer côté boardGraph ».

## Validation
- `_effective_elevation` : 8/8 cas (Trench 0→−1, 1→0, 2→1 ; Grass/Swamp/Water/Block/Bridge identité).
- `Board` sur C2_19 → Trench [−1], C2_16 → Trench [1] : == live boardGraph. Grass/autres inchangés.
- Board ENGINE (boardGraph) non touché → prédiction bit-exacte #182/#194 préservée.

## Anchors
GetElevation @180ec4fd0 ; readTileComponent (frida hooks/game/match-state.ts, COMP_FIELD.tileElevation) ;
boardGraph/tileMeta RPC (frida hooks/features/ai-step/rpc-board.ts). Port : scripts/python/board.py
::_effective_elevation. Probes : scratchpad probe_195_bcfree.py (boardGraph par-TileId, BC-free).
