# Case #124 — le gate d'ELEVATION manquait aux DEUX faces DECISION de la ligne hex

> Ce document couvre DEUX cas de la meme geometrie de ligne hex : **#124** (le gate d'ELEVATION,
> §1-8) et **#126** (la DIRECTION du beam DarkTalonStrike, §9). Le second etait le premier residu
> nomme au §7 du premier.

**Statut** : 2/2 items PORTES + CONFRONTES LIVE (conformite ET discriminance). Correctif 100 %
Python (`scripts/python/**`) — aucun changement `frida/hooks`, aucun rebuild, aucun reinject.
Build `gqfc5mff6c`. Spillover de #117 (face COMBAT, merge en `169b4b2`).

| item | ability | feuille DECISION | verdict |
|---|---|---|---|
| (a) | `DarkTalonStrike` 1092 (`darkaAzrael`, HERO) | `engine/playbook/noncomparable/dark_talon_strike.py::_beam_count` | **QUIRK PORTE + VALIDE LIVE** (conforme + discriminant + mutation-test) |
| (b) | `ExcruciatingFrequencies` 1197 (`emperNoiseMarine`, HERO) | `engine/playbook/excruciating_frequencies.py::_line_tiles` | **QUIRK PORTE + VALIDE LIVE** (idem) |

Code : `engine/battle_query.py` (`get_tiles_behind`, `is_tile_valid_for_list`,
`tiles_behind_accessors`) · `engine/entities/selectors.py` (`TilesBehindInLine` -> adaptateur) ·
les deux feuilles ci-dessus.
Test : `tests/engine/test_line_elevation_gate_decision_live.py` · Probe :
`scripts/python/probe_124_line_elevation_decision.py`.

---

## 1. La question, et la reponse

> Sur un board ou la ligne de tir traverse une marche d'elevation >= 2, la face DECISION offline
> rend-elle la MEME decision que le natif ?

**Avant #124 : NON, pour les deux items.** Les deux feuilles tiraient un rayon cube droit
(`tile_k = caster + k*dir`) sans aucun gate, donc comptaient des ennemis que l'attaque ne
toucherait jamais -> elles proposaient un cast que le natif refuse.

**Apres #124 : OUI** — mesure live, chiffres au §4.

## 2. La face DECISION passe par LA MEME fonction native que la face COMBAT (verifie, pas suppose)

C'etait l'hypothese a confirmer. Elle tient, au decompile :

- `IdunBattle.AI.Playbook.Loki.DarkTalonStrikePlaybook$$EvaluateNonComparable` : pour CHAQUE cible
  eligible, appelle `DarkTalonStrikeAbility$$GetTilesInBestLine(ability)` puis
  `DarkTalonStrikeAbility$$GetAttackTargets(ability, bestLine)`, et evalue le selecteur rendu via un
  slot d'interface avec le contexte de la cible (`FUN_1801e40c0(selector, <iface>, 2)`). Ce sont les
  MEMES fonctions que la face COMBAT — l'arbre DSL est construit une fois et evalue paresseusement.
- `IdunBattle.AI.Playbook.Loki.ExcruciatingFrequenciesPlaybook$$MakeDamagePredictions` : appelle
  `ExcruciatingFrequenciesAbility$$GetAttackTargets` (= `Enemies(Units(GetAffectedTiles))`) puis
  `GenerateMultiHitAttackPredictions`. Meme remarque.

Donc **aucune divergence entre les deux faces natives** : un seul gate, un seul mirror a porter.

### Les settings, relus au decompile

`IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$GetTilesInLine` et
`...ExcruciatingFrequenciesAbility$$GetAffectedTiles` ecrivent tous deux
`*(undefined2 *)(settings + 0x10) = 0x101` — c'est-a-dire `+0x10 = 1` (checkWalkable) ET
`+0x11 = 1` (updateReference), en UN store 16 bits. Confirme l'inventaire de #117 (1/1 · 1/1).

Detail nouveau, lu ici : les slots DSL des deux call-sites different, et ca change la tuile de
REFERENCE initiale (`InitializeShared` : `0x148 Owner · 0x160 Caster · 0x168 CasterTile ·
0x178 Target · 0x180 ActiveTarget · 0x190 TargetTiles`) :

| ability | `from` | `to` | count | reference d'elevation initiale |
|---|---|---|---|---|
| `DarkTalonStrikeAbility$$GetTilesInLine` | `Target@0x178` (la tuile VISEE) | `best` (voisine de la cible) | null | la tuile **visee** |
| `ExcruciatingFrequenciesAbility$$GetAffectedTiles` | `CasterTile@0x168` | `TargetTiles@0x190` (l'aim) | `Direct(nrOfTiles)` | la tuile du **caster** |

Consequence pour DarkTalonStrike : la tuile VISEE n'est JAMAIS gatee — elle entre par
`target@0x178 op_Addition GetTilesInLine(best)`, hors de la ligne ; la premiere marche testee est
`visee -> best`. Pour ExcruciatingFrequencies la premiere marche testee est `caster -> aim`.

`GetAffectedTiles` enveloppe en outre le tout dans `DSLFactory$$SortReverse` : **ordre seulement**.
L'utilite de decision est une SOMME sur les ennemis touches -> non porte cote decision (il
compterait cote COMBAT, ou l'ordre fixe la consommation du RNG coup par coup).

## 3. Le correctif : UN mirror, trois consommateurs

Le port avait deja la bonne geometrie… mais **cote COMBAT seulement**, ecrite dans
`selectors.TilesBehindInLine`. Recopier la marche dans les deux feuilles de decision aurait cree un
fork de port (1 natif -> 3 ports). La marche a donc ete extraite en **mirror UNIQUE**, en domaine
POSITION, dans `engine/battle_query.py` (ou vivent deja les autres slots `IBattleQuery`) :

- `get_tiles_behind(frm, to, max_count, check_walkable, update_reference, walkable_at,
  elevation_at, tile_exists)` = `IdunBattle.Core.Services.BattleQuery$$GetTilesBehind` ;
- `is_tile_valid_for_list(tile, ref, check_walkable, walkable_at, elevation_at)` =
  `IdunBattle.Core.Services.TileUtil$$IsTileValidForList` (le 4e argument natif `checkElevation`
  est le litteral `1` a l'unique call-site -> cable a True) ;
- `tiles_behind_accessors(walkable_by_pos, elev_by_pos)` = l'adaptation aux cartes OFFLINE de la
  face DECISION (`ctx.walkable_by_pos` = boardGraph `IsWalkableTile`, `ctx.elev_by_pos` = tileMeta).

Les trois consommateurs deviennent des ADAPTATEURS :

| consommateur | face | substrat |
|---|---|---|
| `engine/entities/selectors.py::TilesBehindInLine` | COMBAT | `board.id_at` / `board.walkable` / `board.elevation` (tile-ids) |
| `dark_talon_strike.py::_beam_count` | DECISION | `ctx.walkable_by_pos` / `ctx.elev_by_pos` |
| `excruciating_frequencies.py::_line_tiles` | DECISION | idem |

Degradation SURE : accesseur absent (carte vide) -> le gate correspondant est INERTE (borne
SUPERIEURE : on ne tronque jamais une ligne a l'aveugle), c'est-a-dire le comportement pre-#124.

## 4. Confrontation LIVE — conformite ET discriminance

Oracle = l'IA NATIVE sur le MEME etat : `aiDryRunAllUnits` (-> `CalculateNextActionForUnit`),
jamais `aiPredict` (preview d'attaque). Chaque item est mesure TROIS fois sur l'etat identique :
natif · moteur GATE (post-#124) · moteur RAYON DROIT (feuille remise a la geometrie pre-#124).

### (a) DarkTalonStrike — board `C4_02`, colonne 5, elevations `[1,1,3,3]`

Azrael (5,5) · ennemi VISE (5,6) · ennemi (5,7) DERRIERE la marche `1 -> 3` · les 3 autres parques
loin et mutuellement eloignes (`>= 3` hexes : des ennemis parques alignes formeraient une ligne
parasite). `fromHere(1092)` = `[(5,6)]`.

| | ability | cible |
|---|---|---|
| natif | **69** (attaque normale) | 77 |
| moteur GATE | **69** | 77 |
| moteur RAYON DROIT | **1092** | 63 (entite-tuile) |

Mecanique : le rayon droit compte `visee + (5,7)` = **2** >= `MIN_UTILITY` (2, du
`DarkTalonStrikePlaybook$$.cctor`) -> le generateur NonComparable SORT et prime sur tout Comparable.
Le rayon gate s'arrete a la marche -> util **1** < 2 -> aucun NC -> fallback Comparable = ce que
fait le natif.

### (b) ExcruciatingFrequencies — board `C3_59`, falaise `0 -> 4`

Le scenario a demande un board choisi, pas subi. Sur `C4_02` le natif **CONTOURNE** la marche :
depuis (3,6) sa ligne `[(4,6),(5,7),(6,7)]` PASSE le gate (elevations 2/2/3/3) et touche 1 ennemi —
le rayon droit et le rayon gate donnent alors la MEME reponse, et le scenario ne discrimine pas.

Il fallait donc une fenetre **AVEUGLE** : (P, t1, t2, t3) telle que le rayon droit depuis P
franchisse la marche ET qu'AUCUNE position du voisinage-mouvement de P (BFS sur la porte
`|Delta elev| < 2`, profondeur 5 = portee de deplacement observee + marge) ne permette une ligne
GATEE contenant t2/t3. Scan des 104 boards pvp/syncPvp (walkabilite = `playable` ET
`TileId not in {Block, Water}` — mesure : le `boardGraph` LIVE de `C4_41` marque 11 de ses 63 tuiles
non-walkables, toutes `Block`/`Water`) : **2 boards** repondent a profondeur 5 — `C3_59` et `C3_70`.

Retenu `C3_59` : P=(3,4) e1 · t1=(2,4) e0 · t2=(1,5) e4 · t3=(0,5) e4, **voisinage aveugle = 40
tuiles**. Ennemis sur t2/t3, `--hp-target 600` (tuables : la marge du candidat 1197 devient massive
au lieu de se jouer a 0,3 point d'utilite de tuile).

| | ability | cible | candidats 1197 du generateur bespoke |
|---|---|---|---|
| natif | **69** | 77 | — |
| moteur GATE | **69** | 77 | `[]` |
| moteur RAYON DROIT | **1197** | 34 (entite-tuile) | `[{target 34, to None, pred 479.3, full 489.3}]` |

(concurrent : meilleure attaque Comparable `u=239.7 full=259.7` -> le candidat rayon-droit gagne
largement, la discriminance ne tient pas a un tie.)

**Deux ennemis de profils DISTINCTS** (`eldarRanger` + `astraBullgryn`) : a profils EGAUX le choix
de cible de l'attaque normale est un TIE que moteur et natif tranchent depuis des positions
differentes (mesure : natif `69->79 to=(3,5)` vs moteur `69->77 to=(4,4)`) — axe POSITIONNEMENT
(proxy a plancher, cf. `test_playbook_live`), sans rapport avec #124.

### Mutation-test (le gate est PORTANT)

`check_walkable=True -> False` dans les DEUX feuilles de production : les 2 tests ECHOUENT
(`[b] le generateur GATE produit [{...1197...}] alors que le natif refuse 1197`). Revert ->
2 passed. Le test est donc incapable de passer sur un port qui ignore `IsTileValidForList`.

## 5. Placement : le chemin de mouvement, pas la ligne droite

Le driver de placement de #117 approchait chaque destination par `hexgeo.line` (ligne hex droite).
Sur un board a relief ca ne place RIEN au-dela d'une falaise. Le harnais de #124 (probe + test)
prend ses waypoints sur un **BFS du graphe de mouvement natif** (walkable + `|Delta elev| < 2`,
`TileQuery$$IterateAdjacentTiles`), ce qui rend n'importe quelle tuile d'une composante connexe
atteignable en plusieurs activations. C'est ce qui a permis de poser des ennemis sur un palier
qu'aucune ligne ne voit.

## 6. Non-regression (tests CIBLES rejoues, tous verts)

| test | ce qu'il couvre |
|---|---|
| `test_dark_talon_strike_live.py` (2 scenarios) | face COMBAT 1092, dont `[elevation_break]` + son assertion « gate portant » — le refactor du selecteur en adaptateur ne l'a pas bouge |
| `test_storm_speeder_live.py` | `DeathOnTheWind` (settings `0/1` : gate INACTIF) + `Hailstrike` |
| `test_mow_groups_bcd_live.py` | `ThriceBlessedConflagration` (settings `0/0`, l'autre consommateur COMBAT) — 1 skip de scenario preexistant (« le marquage n'a pas survecu jusqu'au 2e cast »), pas un skip de harnais |
| `test_playbook_live.py` | agrement DECISION global (ability EXACT + plancher positionnement) |
| `test_units_directly_behind_offline.py`, `test_lascannon_pierce_offline.py` | selecteurs offline |

## 7. Ce qui n'est PAS couvert

- ~~**DIRECTION du beam DarkTalonStrike**~~ -> **RESOLU par #126, section 9 ci-dessous.**
- **AIM depuis l'ORIGINE uniquement** pour 1092 (`fromHere`) : le natif balaie aussi les tuiles de
  MOVE. Residu anterieur, inchange.
- **Arbitrage Comparable 1197 vs attaque normale** : mesure C4_02 (etat ou le natif CASTE 1197
  depuis (3,6) sur la tuile 54) — le generateur bespoke produit EXACTEMENT ce candidat
  (`{target 54, to (3,6), pred 5.32, full 25.32}`) mais le moteur rend quand meme `69` parce que la
  meilleure attaque Comparable score plus haut. **Divergence PRE-EXISTANTE et ORTHOGONALE au gate**
  (identique avec et sans gate) : le terme `Tile(7)` d'elevation (10 vs 20 entre les deux positions)
  domine l'ecart de degat. **TRANCHE par #128** (`docs/rl/case-128-tile-elevation-utility.md`) : le
  soupcon porte sur le terme d'elevation etait FAUX — ce terme est un mirror exact (gate
  `get_IgnoreTileUtility` = `xor al,al`, `MakeFinalTilePrediction` = identite, composite `Tile(7)` =
  29 feuilles lues dans la carte de composition, BC `{10,10,-5}`) et le natif paie le MEME `+10/niveau`
  (mesure S3 : a degat natif identique il choisit la tuile e3 contre six tuiles e2). L'etage divergent
  est l'ENSEMBLE DE CANDIDATS (le port score depuis la tuile d'ORIGINE, absente de l'enumeration
  native) ; un residu subsiste sur cet etat precis (#128 §6).
- **Cible de l'attaque normale a profils EGAUX** : tie tranche par la position (axe positionnement,
  plancher 45 %). Contourne dans le test par deux ennemis de profils distincts.
- **`tileComponent+0x40` vs `IsWalkable`** : residu herite de #117 — le natif distingue `+0x41`
  (mur) de `+0x40` (drapeau de tuile) ; les deux substrats offline ne connaissent que `IsWalkable`,
  qui fond les deux. Inerte pour les call-sites portes.

## 8. TROISIEME consommateur ? — inventaire COMPLET des call-sites (lu au decompile)

`list_xrefs` sur les deux surcharges de `IdunBattleLogic.Entities.DSLFactory$$TilesBehindInLine` :

**Surcharge a `settings` (celle qui porte le gate)** — 4 call-sites deja inventories par #117
(`DarkTalonStrike` 1/1, `ExcruciatingFrequencies` 1/1, `DeathOnTheWind` 0/1,
`ThriceBlessedConflagration` 0/0) **plus 9 non portes** :
`InstrumentsOfVengeance_AttackAbility$$AttackLine` · `...$$AttackTargetTiles` ·
`InstrumentsOfVengeanceAbility$$GetEffectBehavior` · `RadBombardmentAbility$$GetAffectedTiles` ·
`DiveAttackAbilityBase$$GetTargetTilesSelector` ·
`UnstoppableMomentumReworkedAbility$$GetAllTilesInLine` / `$$ExecuteBehaviour` ·
`ArmouredMight_MoveAbility$$GetAllTilesInLine` / `$$ExecuteBehaviour` ·
`HeraldOfTheApocalypseAbility$$ExecuteBehaviour`.

**Seconde surcharge (sans `settings`)** : `SolarAtomizerAbility$$GetTargetTiles` ·
`NovaChargeAbility$$GetLineTiles` · `TheWailingDoomStrikesAbility$$GetAffectedTiles` /
`$$GetAreaTiles` · `InstrumentsOfVengeanceAbility$$GetEffectBehavior`.

**AUCUN de ces 13 n'a de geometrie de ligne portee aujourd'hui** (verifie : `engine/` ne contient
que leurs ids d'enum ; `RadBombardment` est meme dans `_NO_DAMAGE_ABILITIES`). Il n'y a donc pas de
troisieme consommateur a corriger — mais toute future tranche qui porte l'un d'eux doit lire ses
settings au call-site et passer par `engine.battle_query.get_tiles_behind`.

---

# Case #126 — la DIRECTION du beam DarkTalonStrike : le port DEDUISAIT, le natif CHOISIT

**Statut** : 1/1 item PORTE + CONFRONTE LIVE (conformite ET discriminance, sur DEUX boards) +
mutation-test. Correctif 100 % Python (`scripts/python/**`) — aucun changement `frida/hooks`, aucun
rebuild, aucun reinject. Build `gqfc5mff6c`. Residu nomme au §7 ci-dessus, ANTERIEUR a #124.

| item | ability | feuille DECISION | verdict |
|---|---|---|---|
| (c) | `DarkTalonStrike` 1092 (`darkaAzrael`, HERO) | `engine/playbook/noncomparable/dark_talon_strike.py::_best_line_direction` | **QUIRK PORTE + VALIDE LIVE** |

Code : `engine/battle_query.py` (`connecting_edge`, `get_vector`, `get_angle_between_vectors`,
`get_adjacent_tiles`) · `engine/entities/formulas.py` (`AngleBetweenLines` -> adaptateur) ·
`engine/playbook/noncomparable/dark_talon_strike.py` (`_best_line_direction`, `_line_enemy_count`,
`_beam_count`). Tests : `tests/engine/test_dark_talon_beam_direction_decision_live.py` (LIVE) +
`tests/engine/entities/test_beam_best_line_direction_offline.py` (structure du tri, invisible du
live). Probe : `scripts/python/probe_126_dark_talon_beam_direction.py`.

## 9.1. La question, et la reponse

> Sur un etat ou plusieurs directions de beam sont possibles depuis la cible, la face DECISION
> offline choisit-elle la MEME tuile que le natif ?

**Avant #126 : NON.** `_beam_count` modelisait `best` par le prolongement `caster -> aim`. Le port
etait donc une **BORNE INFERIEURE** — il ne pouvait que SOUS-estimer le nombre d'ennemis alignes,
donc **rater des casts que le natif fait**. Mesure : sur le scenario du §9.4, natif `1092` vs port
`69` (attaque normale).

**Apres #126 : OUI** — natif et port rendent `1092` sur la MEME entite-tuile, sur deux boards.

## 9.2. L'arbre natif, lu au decompile

`IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$GetTilesInBestLine` (slots
`InitializeShared` : `0x148 Owner · 0x160 Caster · 0x178 Target · 0x180 ActiveTarget`) :

    ring    = AdjacentTiles(target@0x178)
    nearest = First( SortByDistance(AdjacentTiles(caster@0x160), target@0x178), 1 )
    angle   = AngleBetweenLines(caster@0x160, nearest, target@0x178, subject@0x180)
    count   = Count( Units( GetTilesInLine(subject@0x180) ) )
    best    = First( SortByFormula( SortByFormula(ring, angle, ASC), count, DESC ), 1 )
    return    target@0x178  op_Addition  GetTilesInLine(best)

Trois lectures qui ne se devinent pas :

1. **Le SENS des tris.** `IdunBattleLogic.Entities.DSLFactory$$SortByFormula(sel, formula, flag)` ->
   `IdunBattle.Entities.Selectors.SortByFormulaSelector$$.ctor(this, inner@0x18, formula@0x20,
   shared, flag@0x28)`, et `$$Select` teste `if (this+0x28 == 0) OrderByDescending else OrderBy`.
   Au call-site : `SortByFormula(ring, angle, 1)` = **ASCENDANT**, puis
   `SortByFormula(..., count, 0)` = **DESCENDANT**. `Enumerable.OrderBy`/`OrderByDescending` sont
   STABLES -> le tri applique EN DERNIER domine : **cle primaire = le compte**, tie-break = l'angle,
   puis l'ordre de `ring`.
2. **La formule d'angle est EXACTE et entiere.**
   `IdunBattle.Entities.Formulas.AngleBetweenLinesFormula$$Calculate` evalue ses 4 selecteurs
   (`+0x10 = caster`, `+0x18 = nearest`, `+0x20 = target`, `+0x28 = subject`) puis appelle deux
   slots du service : `0x70 = IdunBattle.Core.Services.BattleQuery$$GetVector` sur chaque paire,
   `0x71 = BattleQuery$$GetAngleBetweenVectors` sur les deux vecteurs.
   - `GetVector(a, b)` : `MainTile(a) == MainTile(b)` -> vecteur par defaut ; sinon
     `IdunBattle.Utils.Hex.AxialCoordinate$$ConnectingEdge` -> `IdunBattle.Utils.Hex.CubeDirections$$EdgeToNeighbor(diff)`,
     qui hache le delta cube en `100*x + 10*y + z` et ne mappe QUE 6 valeurs
     (`-9 -> 0 · 90 -> 1 · 99 -> 2 · 9 -> 3 · -90 -> 4 · -99 -> 5`) — tout autre delta rend un
     `Nullable<Edge>` VIDE, donc le vecteur par defaut (arete 0).
   - `GetAngleBetweenVectors` EST `IdunBattle.Utils.Hex.EdgeExtensions$$GetAngleTo(e1, e2)` :
     `d = |e1-e2| ; a = d*60 ; if (a > 120) a = (6-d)*60` -> **0/60/120/180/120/60**.
   Consequence : `nearest` etant la voisine du caster la plus proche de la cible, l'angle **0** est
   exactement le PROLONGEMENT `caster -> aim`. Le prolongement n'etait donc pas faux, il etait le
   **tie-break** promu a tort en regle.
3. **`ring` n'est PAS le ring-1 geometrique.**
   `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` appelle le slot `0x4f` avec
   `(entity, 0, 1, 1)` = `BattleQuery$$GetAdjacentTiles(from, onlyEmptyOrSteppable=false,
   onlyWalkableTiles=true, allowTemporary=true)`, qui delegue a
   `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` : celui-ci
   filtre les non-walkables **et** applique la porte `|elev(src) - elev(voisin)| < 2`,
   **INCONDITIONNELLE** (elle ne depend d'aucun des trois flags). C'est la MEME porte que le
   mouvement et que `IsTileValidForList` — un palier a +2 est hors du beam comme il est hors du pas.

## 9.3. Le correctif : trois slots de plus dans le mirror unique

Meme regle qu'au §3 : **1 fonction native = 1 foyer offline**. Les briques manquaient en domaine
POSITION, elles rejoignent `engine/battle_query.py` :

| ajout | natif |
|---|---|
| `connecting_edge(src, dst)` | `AxialCoordinate$$ConnectingEdge` + `CubeDirections$$EdgeToNeighbor` |
| `get_vector(a, b)` | `BattleQuery$$GetVector` (slot 0x71) |
| `get_angle_between_vectors(v1, v2)` | `BattleQuery$$GetAngleBetweenVectors` (slot 0x72) = `EdgeExtensions$$GetAngleTo` |
| `get_adjacent_tiles(pos, ...)` | `BattleQuery$$GetAdjacentTiles` (slot 0x4f) -> `TileQuery.<IterateAdjacentTiles>d__8` |

`get_adjacent_tiles` ne mirrore QUE la combinaison de flags LUE au call-site et **leve** sur les
autres (pas de substrat offline pour `IsTemporary`/`IsEmptyOrSteppable`) : mentir par defaut aurait
cree un faux mirror generique. Les deux faces deviennent des ADAPTATEURS :

| consommateur | face | substrat |
|---|---|---|
| `engine/entities/formulas.py::AngleBetweenLines` | COMBAT (noeud DSL) | selecteurs -> `_tile_positions` |
| `engine/playbook/.../dark_talon_strike.py::_best_line_direction` | DECISION | `ctx.walkable_by_pos` / `ctx.elev_by_pos` |

La face COMBAT portait DEJA l'arbre complet en DSL
(`engine/runner/abilities/darkangels.py::dark_talon_get_tiles_in_best_line`) : #126 ne la change pas
(doctrine #149 — natif DSL reste DSL), il lui retire seulement sa copie locale de la table d'aretes.
La feuille de DECISION, elle, ne peut pas evaluer un arbre DSL (substrat `decisionView`) : elle
mirrore la STRUCTURE du tri, deux `list.sort` successifs (stables, comme `OrderBy`).

Degradation SURE : carte absente -> `get_adjacent_tiles` rend les 6 voisins geometriques et le gate
d'elevation est inerte (borne SUPERIEURE), l'argmax reste actif.

## 9.4. Confrontation LIVE — conformite ET discriminance

Oracle = l'IA NATIVE sur le MEME etat (`aiDryRunAllUnits` -> `CalculateNextActionForUnit`), jamais
`aiPredict`. Trois mesures sur l'etat identique : natif · moteur ARGMAX (post-#126) · moteur
PROLONGEMENT (feuille remise a la geometrie pre-#126).

Scenario DERIVE du board (aucune tuile hardcodee) : **coude a 60 deg**. Caster `P`, chaine
d'ennemis `E1 = P + d1`, `E2 = E1 + d2`, `E3 = E1 + 2*d2` avec `d2` a une arete de `d1`
=> `dist(P, E3) = 3`, **hors de la portee de cast** (mesure : `abilityTargets` ne rend qu'UN aim
`fromHere`, `E1`) — donc **pas de tie** entre les deux bouts de la chaine. Toutes les tuiles au MEME
palier (le gate #124 reste inerte : on n'exerce QUE la direction) et le prolongement `E1 + d1`
existe, walkable et VIDE.

| | ability | cible (entite-tuile) |
|---|---|---|
| natif | **1092** | 27 |
| moteur ARGMAX | **1092** | 27 |
| moteur PROLONGEMENT | **69** (attaque normale) | 79 |

Mecanique : le prolongement `P -> E1` ne touche personne -> `util(E1) = 1` (la tuile visee seule)
< `MIN_UTILITY` (2, du `DarkTalonStrikePlaybook$$.cctor`) -> **aucun** candidat NonComparable ->
fallback Comparable. L'argmax retient la direction `E1 -> E2` (2 ennemis alignes) ->
`util(E1) = 1 + 2 = 3` -> cast, comme le natif.

**Generalisation (2e couple board/seed)** : `C1_25` / seed 777 — `P=(1,3) E1=(2,2) E2=(3,3)
E3=(4,3)`, natif `1092`/28, argmax `1092`/28, prolongement `69`/49. Meme verdict.
(1er couple : `MC1_67` / seed 41171 — `P=(0,5) E1=(1,6) E2=(2,5) E3=(3,5)`.)

**Mutation-test (l'argmax est PORTANT)** : `_best_line_direction` remis au prolongement EN
PRODUCTION -> le test ECHOUE (`util(argmax, aim E1)=1`, moteur `69` vs natif `1092`). Revert ->
vert. Le test est donc incapable de passer sur un port qui DEDUIT la direction.

## 9.5. Ce que le LIVE ne peut PAS distinguer (et le test offline qui le garde)

La face DECISION n'observe du beam que son UTILITE : a comptes EGAUX, deux directions donnent la
MEME utilite, donc la MEME action. **Le tri par angle et l'ordre de `ring` sont invisibles d'un
agreement live** — ils ne changent que la ligne effectivement frappee, cote COMBAT.
`tests/engine/entities/test_beam_best_line_direction_offline.py` garde donc, hors live :
`GetAngleTo` (0/60/120/180/120/60), le ring gate (walkabilite + `|Delta elev| < 2` + bord de
plateau), la hierarchie count-DESC > angle-ASC, et la troncature d'elevation SOUS l'argmax.

## 9.6. Ce qui n'est PAS couvert par #126

- **Interaction gate x argmax en LIVE** : chaque face est gardee separement (le gate par
  `test_line_elevation_gate_decision_live`, l'argmax par `test_dark_talon_beam_direction_...`).
  Un etat ou la marche fait BASCULER le choix de direction (direction riche bloquee, direction
  pauvre retenue) n'est pas confronte au natif — il l'est offline (§9.5, dernier test).
- **Ordre d'enumeration de `ring`** : le natif suit `tile.Neighbours` (liste pre-calculee du
  composant tuile), le port suit `hexgeo.neighbors`. Tie-break de DERNIER recours entre directions
  d'utilite EGALE -> inerte pour la decision ; il deviendrait observable si la face COMBAT
  consommait ce foyer (elle a son propre arbre DSL, ordonne par ses propres selecteurs).
- **AIM depuis l'ORIGINE uniquement** (`fromHere`) : residu ANTERIEUR, inchange (cf. §7).
- **`ThriceBlessedConflagrationPlaybook` (1187) : le MEME motif d'argmax, face DECISION NON PORTEE.**
  `IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$GetTilesInBestLine`
  a la meme forme — `best = First(SortByFormula(ring, Count(GetTilesInLine(subject)), DESC), 1)` —
  avec DEUX differences lues au decompile : (a) **pas de tri par angle** (un seul `SortByFormula`,
  donc le tie-break est directement l'ordre de `ring`) ; (b) `ring = SurroundingTiles(target@0x178,
  includeCenter=0, radius=1, ...)`, PAS `AdjacentTiles` — donc `IsTileValidForList(tile, src, 1, 0)`
  (walkable, SANS test d'elevation) au lieu de la porte `|Delta elev| < 2`. Sa face COMBAT est
  portee et fidele (`engine/runner/abilities/sisterhood.py::thrice_blessed_get_tiles_in_best_line`).
  Sa face DECISION `IdunBattle.AI.Playbook.Loki.ThriceBlessedConflagrationPlaybook$$EvaluateNonComparable`
  existe nativement mais n'a **aucun port offline** (`engine/playbook/` ne la connait pas) : ce n'est
  donc pas une direction FAUSSE a corriger, c'est une feuille NonComparable ABSENTE. **Candidat de
  suite**, hors perimetre #126.
- **`ExcruciatingFrequencies` (1197) : pas de motif d'argmax** (verifie au decompile).
  `ExcruciatingFrequenciesAbility$$GetAffectedTiles` = `SortReverse(TilesBehindInLine(
  CasterTile@0x168, TargetTiles@0x190, settings{0x101}, Direct(nrOfTiles)))` — la direction est
  DONNEE par l'aim, il n'y a rien a choisir. Sa feuille `_line_tiles` reste correcte.
