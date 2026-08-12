# #943-r4 / #943-r6-r1 — le critère d'entrée était un token de PROSE, et l'étape qui l'aurait vu n'était jouée par personne

Deux résidus ouverts sur le **même probe** et le **même foyer**
(`probe_433r4r1r4r2_neigh_channel_wired.py`), et une seule tranche : le FOND de #943-r4 (les 26
sites muets) et le câblage de l'`etape1` (#943-r6-r1).

## 1. Ce qui n'allait pas, mesuré

Les étapes 2 et 4 gardent « un mirror **déclaré** du substrat stocké fait-il de la géométrie
nue ? ». Leur critère d'ENTRÉE est `any(nat in docstring for nat in NATIFS_LISTE_STOCKEE)` — une
propriété de la **prose**, pas du code. Mesure héritée de #943-r6 (`etape6`, balayage par le
CONTENU) :

```
30 fonctions d'engine/ comparent une distance hex a 1
 2 vues par etape2 (declarantes, sans canal)   <- les 2 rouges, tolérés
 2 touchent le canal (etape4)
26 MUETTES -- invisibles aux etapes 2 et 4 par construction
```

Le cas d'école était nommé : `imperative.create_aura_attack_damage_bonus_for_ally` applique
**exactement** le même `hexgeo.distance != 1` que son jumeau `icon_of_obstinacy` — l'un invisible,
l'autre rouge.

Et l'`etape1` (l'invariant de couple sur les call-sites) était **ROUGE** sur
`engine/runner/abilities/admec.py`, sans que rien ne le voie : ce fichier de test est **le seul de
la banque à importer le probe**, et il appelait `etape2/3/4/5`, jamais `etape1`. Les quatre étapes
*neuves* avaient chacune leur test de câblage ; l'ancienne n'en avait pas.

## 2. Le tri des 26 — natif par natif, au décompilé

C'est le fond de la tranche. **La géométrie hex n'est PAS un vice en soi** : elle est le mirror
EXACT partout où le natif est lui-même géométrique. Les substrats ont été lus :

| substrat natif | verdict | corps lu |
|---|---|---|
| `TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` | **GÉOMÉTRIQUE** | balaie le cube `[c-d, c+d]^3` sous `x+y+z == 0`, puis `StateExtensions$$GetTileAt(axial)`. Ni liste stockée ni porte d'élévation |
| `MovementQuery$$GetDistance(originTiles, destTiles)` | **GÉOMÉTRIQUE** | `min` de `Utils.Hex.CubeCoordinate$$Distance` sur les pieds |
| `MovementQuery$$u003CGetTilesObscuringTerrainu003Eg__DetermineBlockingTiles|40_0` | **GÉOMÉTRIQUE** | lit deux **listes de coordonnées** à l'index, puis `GetTileAt` — une ligne hex |
| `DSLSelectors$$AdjacentFriends(unit, unique, sel)` | **LISTE STOCKÉE** | `Friends(unit, Units(AdjacentTiles(unit)) - unit, sel)` ; `AdjacentEnemies` = le pendant exact avec `Enemies` |
| `BattleQuery$$GetAdjacentUnits(from, …)` (slots 122-124) | **LISTE STOCKÉE** | corps entier = `GetUnitsOnTiles(IterateAdjacentTiles(from, 0, 1, 1), …)` |
| `BattleQuery$$GetAdjacentEnemies(from, pid, ign)` (slots 125-126) | **LISTE STOCKÉE** | idem, `enemiesOf` passé à `GetUnitsOnTiles` |
| `TileExtensions$$IsNeighbourOf(tile, other)` | **LISTE STOCKÉE** | énumère `ConnectivityComponent+0x10` de `tile` et compare l'id — **sans** porte d'élévation |
| `Triggers.IsAdjacentAbilityTrigger$$ShouldTrigger` | **LISTE STOCKÉE** | `AreEntitiesAdjacent` (slot 96) sur chaque paire → `MovementUtil$$AreTilesAdjacent` → `IsNeighbour` |
| `MovementQuery$$IsAdjacent(t1, t2)` | **LISTE STOCKÉE** | `GetAdjacentTiles(t1, 0, 1, 1).Contains(t2)` |

Résultat du tri, **26 sites** : **5 GÉOMÉTRIQUE** (le port est exact, les câbler serait une
RÉGRESSION), **21 LISTE_STOCKÉE**.

Deux cas valent d'être lus, parce qu'ils montrent que la ressemblance de forme ne conclut rien :

* `services/movement_query.py::is_valid_unit_feet_list` écrit `hexgeo.distance(t_i, t_j) != 1`
  **puis** `all(is_adjacent(board, …))`. Le natif fait **littéralement les deux** :
  `GetDistance(t_i,t_j) == 1` (cube) sur les trois paires, **puis** `IsAdjacent(t_i,t_j)`
  (connectivité). Le port est fidèle, et sa géométrie n'est pas un oubli du canal ;
* `entities/selectors/units.py::select` (`UnitsDirectlyBehind`) compare `<= 1` sur un anneau issu
  de `SurroundingTiles(target, includeCenter:1, 1)` — géométrique par construction.

## 3. Ce qui est livré : le critère porte sur le CONTENU, l'entrée au registre exige une LECTURE

`etape6` restait **hors verdict**, et sa docstring disait pourquoi : « coter ces sites sans les
avoir LUS un par un ferait l'erreur que ce cliquet reproche aux ports ». C'était vrai — **tant que
personne ne les avait lus**. Ils le sont.

* `GEOMETRIE_NUE_CLASSEE` : `(chemin, fonction) -> (classe, natif LU)`. **Tout site à géométrie nue
  qui n'y est pas ROUGIT**, quelle que soit sa docstring. Un site ne peut donc plus être invisible
  parce qu'il ne nomme pas son natif — au pire il est NON CLASSÉ, et ça se voit.
* Le verdict est porté par `etape6_non_classee` ; `etape6` reste la mesure **brute**, exactement
  comme `etape2` sous sa tolérance.
* **La classification est VÉRIFIABLE, pas déclarative** : `SUBSTRATS_LUS` liste les corps
  effectivement décompilés par classe, et un test exige que chaque entrée cite un substrat **de sa
  classe** et **aucun de l'autre**. Sans ce cran, ranger un site en `GEOMETRIQUE` coûterait un trait
  de plume — la dispense que le registre existe pour interdire. Contre-épreuve paramétrée dans les
  deux sens (substrat de l'autre classe → rouge ; substrat inconnu → rouge).
* Quatre gardes de plus : périmètre non vide (un balayage aveugle n'est pas un vert), entrée
  **PÉRIMÉE** (qui ne désigne plus aucun site) → rouge, une géométrie nue **neuve et muette** →
  rouge, et **vider le registre fait réapparaître tous les muets** (le vert vient du registre, pas
  d'un gisement disparu).

⚠ **Ce que la clé `(chemin, nom)` ne sépare pas** : `hits.py` porte DEUX
`create_aura_additional_hits_for_ally` (deux classes, deux abilities). Une entrée couvre les deux,
donc la disparition de l'une ne périme pas l'entrée. C'est **nommé** plutôt que corrigé : une clé
par LIGNE périmerait à chaque édition — le vice que la tolérance de #943-r6 évite déjà.

## 4. Les trois réparations moteur, et pourquoi CELLES-LÀ

**`admec.py::ArcScourgeAbility.get_dynamic_invalid_target_reason` — TROIS défauts, pas un.**
Le rouge de l'`etape1`. Le natif appelle le slot `0x7a` = `GetAdjacentUnits(target, 0, 0, 0)`, dont
le corps entier est `GetUnitsOnTiles(IterateAdjacentTiles(target, 0, 1, 1), …)`.

1. Le port passait `are_entities_adjacent(tpos, upos, elev)` — **voisinage absent** (le rouge
   dénoncé par l'`etape1`) ;
2. **`elev` valait `None` à tous les coups** : il était lu par
   `getattr(state.board, "elevation_by_pos", None)`, un attribut qui **n'existe nulle part**
   (`Board` porte `elev_by_pos`, et le foyer est `elevations_by_pos(board)`). Seul site du dépôt à
   porter ce nom — la porte d'élévation était morte ici aussi, en silence ;
3. **`state.units()` N'EXISTE PAS.** Trouvé **en craftant le scénario de généralisation**, pas en
   lisant : `State` n'expose aucune méthode de ce nom, et ce site était le seul du dépôt à
   l'appeler. Le gate levait donc `AttributeError` à **chaque** consultation, et
   `targeting.get_invalid_target_reason` l'appelle **sans `try`**. Ce troisième défaut est le seul
   des trois qui soit BRUYANT — et c'est précisément pour ça qu'aucune des deux lectures
   précédentes ne l'avait vu : elles cherchaient une dégradation *silencieuse*. La source devient
   `state.entities`, comme aux deux autres sites qui mirrorent le même itérateur ; seule la SOURCE
   change (le natif `GetUnitsOnTiles(tiles, null, null, 0)` ne filtre ni équipe ni état).

**`base.py::_fighting_retreat_sets_flags` — la seule des DEUX faces à ne pas porter le canal.**
Corps lu : `Direct(!Any(<slot 0x7d>(caster, pid, 0)))`, slot 125 = `GetAdjacentEnemies` →
`IterateAdjacentTiles`. La face DÉCISION du même natif,
`playbook/noncomparable/fighting_retreat.py`, consomme **déjà**
`bq.count_adjacent(tile, ctx.epos, ctx.elev_by_pos, bq.neigh_map(ctx))`. Câbler ici **résorbe** une
divergence de faces au lieu d'en créer une.

**`votann.py::_ancestral_fortune_attack_target`** — `AdjacentEnemies(caster, 1)` → `AdjacentTiles`
→ `IterateAdjacentTiles`. Foyer unique, aucune face jumelle.

**Pourquoi pas les 19 autres.** Ce sont majoritairement des **couples runner/décision** — « un nœud
natif, deux substrats : l'ECS côté runner, les tables de `Scene` côté décision », ce que `scene.py`
écrit en toutes lettres. N'en câbler qu'un côté **crée** la divergence de faces que la réparation
d'`_fighting_retreat_sets_flags` vient de résorber. La réparation est un déplacement au foyer, pour
la famille : résidu **#943-r7**.

## 5. L'écart de comportement, mesuré

Les trois réparations sont **strictement RESTRICTIVES** : `hexgeo` seul SUR-atteint la liste
stockée (mesure #930 : 4 arêtes sur `C1_74`, 38 sur `C3_14`, **0** dans l'autre sens), et la porte
`|dElev| < 2` ne peut que retrancher.

Ampleur de la **porte d'élévation** seule, re-dérivée offline sur les **779** boards versionnés
(`data/boards/**`, script jetable — le board JSON porte l'élévation mais **pas** le graphe de
connectivité, qui vient du `boardGraph` live) :

```
aretes hex non orientees          : 113 260
COUPEES par |dElev| >= 2          :  10 129  (8,9 %)
boards a 0 arete coupee           :      97
pire board (MC2_60)               :  62 / 158  (39,2 %)
```

C'est l'ordre de grandeur de ce qu'`admec.py` ignorait par son attribut mort. **L'écart du premier
étage (l'énumération) n'est PAS mesurable offline** — il exige le `boardGraph`, donc une session
live.

Sens des écarts, par site :

* `ArcScourge.get_dynamic_invalid_target_reason` : **moins** de conducteurs trouvés ⇒ le gate
  `TargetMatchesDynamicRule` REFUSE plus souvent. Durcissement, conforme au natif ;
* `_fighting_retreat_sets_flags` : **moins** d'ennemis comptés adjacents ⇒ rend `True` plus souvent
  ⇒ les flags de fin de tour sont posés dans plus de cas ;
* `_ancestral_fortune_attack_target` : **moins** de candidats ⇒ peut rendre `None` (pas d'attaque)
  là où la couronne en trouvait un.

Sur un board **plat sans canal capté**, les trois sont des **no-op démontrables** : `is_adjacent`
dégrade seul en `hexgeo` quand les deux canaux sont `None`.

### L'étage 1 (l'énumération), lui, se mesure LIVE — et il a été mesuré

`probe_433r4r1r4r2_is_adjacent_substrat_live.py --board MC2_60 --board C4_69` (les deux boards que
la mesure d'élévation ci-dessus désigne comme les plus mordants) :

| board | `|G_gated|` | `|N|` | permissives fermées | restrictives ouvertes | port AVEC canal | port SANS canal |
|---|---|---|---|---|---|---|
| `MC2_60` | 192 | 170 | **22** | **0** | **0 désaccord** | **22 désaccords** |
| `C4_69` | 196 | 188 | **8** | **0** | **0 désaccord** | **8 désaccords** |

Zéro arête one-way, zéro permissive sans réciproque. **Le port AVEC canal est en accord PARFAIT
avec le natif ; le port SANS canal — celui d'avant, sur les trois sites — en diverge sur toutes les
arêtes du gisement.** C'est la confirmation directe de ce que les trois réparations changent.

⚠ **Et l'écart mesuré ici n'est PAS la porte d'élévation** : sur les 22 arêtes de `MC2_60`,
`|dElev|` vaut **0 ou 1** — elles sont fermées par l'ÉNUMÉRATION (`G \ C`), typiquement autour des
tuiles `Bridge`. Les deux mesures sont donc **complémentaires et disjointes** : 8,9 % des arêtes
tombent par la porte (offline, 779 boards), et d'autres encore par la liste stockée (live).

### Le scénario de généralisation, et sa contre-épreuve

`tests/engine/runner/test_943r4_adjacence_cablee_offline.py` (12 tests, 100 % offline) monte un
**vrai `Board`** dont deux tuiles sont hex-voisines **sans** figurer dans la liste stockée l'une de
l'autre — le régime que la mesure live ci-dessus établit comme réel. Il exerce les **deux étages**
(énumération, puis porte `|dElev|` paramétrée sur 0/1/2/3), le **tri-état** du canal (`neighbours`
ABSENT ≠ VIDE, le vice de #381-r3), et porte ses propres prémisses (les positions sont bien
hex-adjacentes ; sans conducteur, ArcScourge refuse de toute façon).

**Contre-épreuve mesurée**, arbre témoin détaché sur le commit de base (`308f2cea`), même fichier
de test : **8 des 12 tests ÉCHOUENT**. Les 4 qui passent sont exactement ceux qui doivent passer —
la prémisse hex, le no-op sans board, la contre-épreuve « liste qui CONFIRME » (verdict inchangé)
et le tri-état.

⚠ Le montage a dû être corrigé deux fois, et les deux corrections sont des résultats : un
duck-type réduit à `by_id` suffit aux deux foyers de canal mais **pas** au chemin complet
(`AncestralFortune` descend dans `damage_model.apply_elevation_bonus`, qui appelle `board.tile_at`)
— d'où le vrai `Board` ; et un montage à deux unités mesure le refus *par défaut* d'ArcScourge, pas
son adjacence — d'où la troisième unité, et le test de prémisse qui le dit.

## 6. #943-r6-r1 — l'`etape1` est câblée, et le rouge qu'elle dénonçait est réparé

Dans **le même commit**, et dans cet ordre : le rouge d'abord (`admec.py`), le câblage ensuite.
L'inverse aurait rendu `master` rouge. Deux tests : l'arbre courant vert sur un périmètre non vide
(108 call-sites gatés par l'élévation, 0 sans voisinage), et le câblage au verdict de `main()`.

## 7. Coût du cliquet

`main()` re-balayait les 438 arbres plusieurs fois de trop (les étapes 2 et 4 sont les plus chères,
et l'étape 5 les rejoue une fois par natif suspendu). Les résultats bruts sont désormais calculés
une fois et passés aux étapes qui les FILTRENT : **38 s → 29 s** (-24 %), verdict et ventilation
identiques.

⚠ **Contrainte pour qui substitue une étape** : `etape2_hors_tolerance`, `etape5` et
`etape6_non_classee` reçoivent un argument nommé en plus des arbres. Une substitution de test doit
accepter `**kw`. L'oubli lève `TypeError` — un échec bruyant, pas un faux vert, mais qui accuse le
mauvais coupable.

## 8. Ce qui n'est PAS couvert

* **Les 19 sites `LISTE_STOCKEE`** (résidu **#943-r7**) : classés, natif LU cité, **non réparés**.
  Ils sont nommément listés dans `GEOMETRIE_NUE_CLASSEE`.
* **Les 2 sites de `GEOMETRIE_NUE_TOLEREE`** (#943-r4 d'origine, `aura_selectors` et
  `icon_of_obstinacy`) restent tolérés : ils sont *déclarants*, donc vus par l'`etape2`, et
  appartiennent à la même famille #271. Ils sont hors du registre de l'étape 6 par construction
  (celle-ci ne rend que les MUETS) — les deux registres sont disjoints.
* **Le SUBSTRAT est confronté live, les TROIS ABILITIES ne le sont pas.**
  `probe_433r4r1r4r2_is_adjacent_substrat_live.py` établit que le port AVEC canal est en accord
  parfait avec le natif (§5), donc que le prédicat consommé par les trois sites est le bon. Ce qui
  n'a **pas** été joué, c'est le comportement observable des abilities elles-mêmes en bataille :
  `test_votann_lot1_live.py` (`AncestralFortune`), `test_tau_lot1_live.py` (`FightingRetreat`) et
  un porteur de `1173 ArcScourge` (`admecBossBelisarius`). Raison : ces trois montages exigeraient
  en plus un board où la liste stockée contredit la couronne SOUS les unités concernées — ce que le
  test offline crafte, mais qu'un runner ne donne pas par construction de spawn.
* **Les entrées 457 de `test_946_counter_attack_offline.py` et
  `test_947_948_extra_damage_passives_offline.py`** ont été mesurées en même temps que la mienne
  (`--measure-missing` ne sait pas cibler un fichier). Ce sont des fichiers d'autres tranches, que
  `loop_status` signalait déjà comme non mesurés ; la mesure les trouve **verts et offline**, ce qui
  tranche leur alternative dans le sens (a). Diff : 29 lignes ajoutées, 0 supprimée.
* **L'écart `are_entities_adjacent` vs `is_adjacent` sur `admec.py`** n'est pas traité : le natif
  passe par `IterateAdjacentTiles` (qui ne rend JAMAIS la tuile source), alors que le port garde
  `are_entities_adjacent`, qui porte le court-circuit d'identité `t1 == t2`. Le port exclut déjà
  `uid == target_id`, donc l'écart n'existerait que pour deux unités **distinctes co-localisées** —
  régime que le jeu n'admet pas. Noté, non changé.
* **`GetEmRuntzAbility$$GetSpawnTileSelector`** porte DEUX `AdjacentTiles` (`CanAddUnit(AdjacentTiles
  (caster)) & Unique(AdjacentTiles(ennemis sans trait 0x1b))`) : les **deux** comparaisons de
  `_spawn_tile_count` sont concernées, pas seulement la première. Le registre le classe ; la
  réparation appartient à #943-r7.
