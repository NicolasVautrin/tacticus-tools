# Case #124 — le gate d'ELEVATION manquait aux DEUX faces DECISION de la ligne hex

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

- **DIRECTION du beam DarkTalonStrike (residu ANTERIEUR, hors perimetre)** : la feuille modelise
  `best` par le prolongement du rayon `caster -> aim`, alors que
  `DarkTalonStrikeAbility$$GetTilesInBestLine` le CHOISIT parmi les 6 `AdjacentTiles(target@0x178)`
  via `SortByFormula(AngleBetweenLines, ASC)` puis `SortByFormula(Count(Units(GetTilesInLine)),
  DESC)` + `First(1)` (tris STABLES -> cle primaire = #ennemis alignes). Le port est donc une
  **BORNE INFERIEURE** de l'utilite native quand une autre direction aligne davantage d'ennemis.
  Deja flagge avant #124 ; #124 ne l'aggrave ni ne le corrige.
- **AIM depuis l'ORIGINE uniquement** pour 1092 (`fromHere`) : le natif balaie aussi les tuiles de
  MOVE. Residu anterieur, inchange.
- **Arbitrage Comparable 1197 vs attaque normale** : mesure C4_02 (etat ou le natif CASTE 1197
  depuis (3,6) sur la tuile 54) — le generateur bespoke produit EXACTEMENT ce candidat
  (`{target 54, to (3,6), pred 5.32, full 25.32}`) mais le moteur rend quand meme `69` parce que la
  meilleure attaque Comparable score plus haut. **Divergence PRE-EXISTANTE et ORTHOGONALE au gate**
  (identique avec et sans gate) : le terme `Tile(7)` d'elevation (10 vs 20 entre les deux positions)
  domine l'ecart de degat. **Candidat de suite** : confronter l'utilite d'ACTION 1197 vs normale sur
  un etat ou le natif caste 1197.
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
