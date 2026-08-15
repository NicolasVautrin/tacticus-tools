# #433-r4-r1-r1-r2 — la LoS d'`IsObscured` : RE COMPLÈTE, port NON MODIFIÉ (foyer occupé)

> **RE-MESURE DU 2026-08-15 — LIRE LE §6 AVANT LE §3.** Le §3 affirme « le port n'a **aucun**
> mirror de `DrawLineBetweenCoordinates` ». C'est **FAUX**, et ça l'était déjà à l'écriture : le
> mirror COMPLET a été livré le **2026-08-04** par `fd832e65` (`#433-r4-r2-r1-r2`), soit **six
> jours avant** cette fiche. Il vivait dans `engine/services/movement_query.py`, c'est-à-dire dans
> la face COMBAT, pendant que la fiche cherchait dans `engine/battle_query.py`, la face DÉCISION.
> Ce n'est donc pas une ABSENCE, c'est un **FORK** — et le §6 le chiffre.

**RE faite le 2026-08-10** sur `rnca9r7q6c`. **Aucune édition de code** : le foyer
`scripts/python/engine/battle_query.py` est le territoire d'un agent en vol sur la même vague
(`engine/playbook/**` + `engine/battle_query.py`). Cette fiche livre la lecture pour que le port
soit une transcription, pas une nouvelle enquête.

## 1. L'énoncé du résidu est EXACT — et ce qu'il en concluait ne l'était pas

Le résidu décrit le port : « distance 1 jamais obscurcie, distance EXACTEMENT 2 gatée par
l'élévation, distance >= 3 et MURS non modélisés -> passe-tout ». C'est bien ce que fait
`battle_query.is_target_tile_obscured` (`if hexgeo.distance(fk, tk) != 2 … return False`).

Ce que le résidu laissait entendre — que le régime `>= 3` serait hors du périmètre natif, l'anneau
de `1186` valant 2 — est **faux** : le natif y calcule bel et bien, et sa condition n'est pas une
distance.

## 2. Le corps natif, lu

`IdunBattle.Core.Services.TargetingQuery$$IsTargetTileObscured(from, target, onlyWalls)` :

```
count = <IMovementQuery slot 0x10>(from, target, ((onlyWalls & 0xff ^ 1) * 2) + 4, 2).Count;
return count > 0;
```

Deux **littéraux** confirmés, tous deux conformes au port : `obscuringType = 6` quand
`onlyWalls == false` (élévation bit 2 **+ murs bit 4**), et `blockingElevationDifference = 2`.

`IdunBattle.Core.Services.MovementQuery$$GetTilesObscuringTerrain(from, to, obscuringType,
blockingElevationDifference)` (surcharge par TUILE) :

```
GetLinesBetweenTiles(line1, line2, GetMainTile(from), GetMainTile(to));
lineA = FirstOrFallbackIfOutsidePlayableArea(line1, line2, closure);
lineB = FirstOrFallbackIfOutsidePlayableArea(line2, lineA, closure);
if (lineA.Count > 2) {                                   // <<< LA CONDITION
    if (obscuringType & 2) {
        DetermineBlockingTiles(index = 1,               elevationToCompare = elev(from), closure);
        DetermineBlockingTiles(index = lineA.Count - 2, elevationToCompare = elev(to),   closure);
    }
    if (obscuringType & 4) DetermineBlockingWalls(closure);
}
```

**LA CONDITION EST `lineA.Count > 2`, PAS `distance == 2`.** La ligne compte les tuiles, extrémités
incluses :

| dist hex | `Count` | `Count > 2` | index testés | ce que le port fait |
|---|---|---|---|---|
| 1 | 2 | non | — | rend `False` — **conforme** |
| 2 | 3 | **oui** | `1` et `1` (la MÊME tuile, deux références) | conforme |
| 3 | 4 | **oui** | `1` (vs `elev(from)`) et `2` (vs `elev(to)`) — **deux tuiles distinctes** | rend `False` — **ÉCART** |
| n | n+1 | **oui** | `1` et `n-1` | rend `False` — **ÉCART** |

Et **seuls DEUX index sont testés, quelle que soit la longueur** : le voisin de `from` contre
l'élévation de `from`, et le voisin de `to` contre celle de `to`. Le natif ne balaie **pas** toute
la ligne — un port naïf qui itérerait toutes les tuiles intermédiaires serait plus bloquant que lui.

`…g__DetermineBlockingTiles|40_0(index, elevationToCompare, closure)`, relu :

```
a = GetTileAt(lineA[index]);  b = GetTileAt(lineB[index]);
blkA = a != null && (elev(a) - elevationToCompare) >= closure.threshold;   // threshold = +0x18 = 2
blkB = b != null && (elev(b) - elevationToCompare) >= closure.threshold;
if (a == b) { if (!blkA) return;  add(a); }
else        { if (!(blkA & blkB)) return;  add(a); add(b); }
```

⇒ la « fat-line » du port (deux candidates, `ET` logique) est un **mirror exact** de cet étage. Ce
qui manque est l'ITÉRATION au-dessus et le producteur de lignes.

## 3. Le substrat manquant a un nom

`IdunBattle.Core.Services.MovementUtil$$GetLinesBetweenTiles(line1, line2, fromTile, toTile)` =
**deux** appels à `IdunBattle.Core.Services.MovementUtil$$DrawLineBetweenCoordinates(line, from,
to, <flag>)`, avec `flag = 0` puis `flag = 1`. C'est exactement le nudge `±eps` que la docstring du
port **supposait** sans le lire : il est ici LU, et c'est le 4ᵉ paramètre d'un tracé de ligne cube.

Le port n'a **aucun** mirror de `DrawLineBetweenCoordinates` : il reconstruit les candidates par
`hexgeo.neighbors(from) ∩ ring1(to)`, ce qui n'est exact que pour `dist == 2` (où « voisin commun »
et « 2ᵉ tuile de la ligne » coïncident). Porter le régime `>= 3` exige donc ce mirror-là, plus
`…g__FirstOrFallbackIfOutsidePlayableArea|40_2` (qui choisit/replie une ligne sortant de la zone
jouable — non lu ici).

## 4. Ce que ça change, et pourquoi ce n'est pas urgent pour `1186`

Pour `WallOfMirrors` (1186) l'anneau est à distance **exactement 2**, donc le filtre y est actif et
correct : la garde offline dédiée de #433-r4-r1-r1 reste valable. L'écart mord ailleurs — partout où
un `Unobscured`/`IsObscured` est évalué à distance >= 3, c'est-à-dire **toutes** les abilities à
portée > 2 qui filtrent la ligne de vue. Le port y est **PERMISSIF** : il accorde des cibles que le
natif obscurcit.

Deuxième écart, indépendant et **toujours armé** : le bit 4 (`DetermineBlockingWalls`) est dans le
mask `6` à **tous** les appels d'`IsTargetTileObscured`, et le port n'a aucun `wall_by_pos`.

## 5. Ce qui n'est PAS fait

- **Aucune édition** : `engine/battle_query.py` appartient à un autre agent de la vague. Ce résidu
  doit repartir avec ce foyer, une fois libre.
- `…g__FirstOrFallbackIfOutsidePlayableArea|40_2` et
  `…g__DetermineBlockingWalls|40_1` ne sont pas lus — ils sont nommés, pas décrits.
- `MovementUtil$$DrawLineBetweenCoordinates` n'est pas lu non plus : c'est l'étage à transcrire, et
  son nudge (`flag 0/1`) est ce qui produit les deux lignes.
- Aucune mesure de l'ampleur : combien de call-sites portés évaluent la LoS à distance >= 3 n'a pas
  été compté.

---

## 6. RE-MESURE DU 2026-08-15 — ce n'est pas une absence, c'est un FORK, et il est chiffré

### 6.1 Les trois manques du §5 étaient déjà comblés — ailleurs

`engine/services/movement_query.py` portait, depuis `fd832e65` (2026-08-04), **la totalité** de ce
que le §5 déclare non lu : `MovementUtil$$DrawLineBetweenCoordinates` (avec son nudge, LU au
`MovementUtil$$.cctor` : `(1·10⁻⁶, 2·10⁻⁶, −3·10⁻⁶)`, construit en `Fix64.Pow(10, -6)` × {1, 2, −3}),
`…g__FirstOrFallbackIfOutsidePlayableArea|40_2`, `…g__DetermineBlockingWalls|40_1`, et même un
substrat `PositionBoard(elev_by_pos, is_wall_by_pos)` **écrit exprès pour la face DÉCISION**.

**La leçon de méthode** : chercher un mirror par le NOM du foyer où on l'attend (`battle_query`)
au lieu du NOM DU NATIF (`GetTilesObscuringTerrain`) fait conclure « absent » sur du code livré.
Un `git grep get_tiles_obscuring_terrain` l'aurait rendu ; un `git grep` dans le seul fichier
qu'on édite, non.

### 6.2 L'écart des deux mirrors, exhaustivement (`probe_433r4r1r1r2_los_fork.py`)

8 plateaux 7×7, élévations aléatoires 0–4, **17 536 paires** ordonnées à distance ≤ 6 :

| dist | paires | désaccords | v1 bloque | complet bloque |
|---|---|---|---|---|
| 1 | 1 920 | **0** | 0 | 0 |
| 2 | 3 136 | **0** | 808 | 808 |
| 3 | 3 648 | **1 390** | 0 | 1 390 |
| 4 | 3 616 | **1 254** | 0 | 1 254 |
| 5 | 3 072 | **1 212** | 0 | 1 212 |
| 6 | 2 144 | **768** | 0 | 768 |

**Le v1 est BIT-EXACT là où il répond** : ses « voisins communs » sont exactement les deux
candidates des lignes nudgées, pour toute paire à distance 2. Au-delà, il rend `False`
inconditionnellement — **4 624 désaccords sur 12 480 paires (37 %)**, tous PERMISSIFS.

**Volet MURS** (mask `4` seul, plateau PLAT à 25 % de murs) : **1 098 paires bloquées sur 2 192**.
Le v1 en bloque **0** par construction. Le canal existe pourtant : mesure live (runner MC1_67,
`boardGraph`) — **63 tuiles sur 63** portent `elevation` ET `isWall`, et `AiDecisionContext` /
`NCContext` transportent déjà `is_wall_by_pos`.

### 6.3 Ce qui a été LIVRÉ, et ce qui a été ÉCRIT PUIS RETIRÉ

**Livré — volet 1, le prérequis STRUCTUREL.** Le foyer complet est extrait dans
`engine/services/line_of_sight.py`, module FEUILLE : sa cascade `engine.*` passe de **178** modules
à **3**. C'est ce qui rendait le branchement impossible, et ce n'était pas un détail :
`movement_query` tire `engine.entities.selectors.units`, qui fait
`from ...battle_query import is_target_tile_obscured` — un import statique
`battle_query → movement_query` aurait fermé le cycle que garde `#477-r35` (probe VERT après le
déplacement : **712 modules, 0 non importable seul**). `movement_query` ré-exporte les 11 symboles,
donc aucun call-site `MQ.<nom>` ne bouge, et aucun patcheur n'est désarmé (vérifié :
`git grep "setattr(.*movement_query"` ne rend qu'un **commentaire**, sur `get_distance`).

Le tracé y est aussi **mémoïsé** — `_draw_line_cached`, `lru_cache(65536)`. C'est value-preserving
par construction (le tracé ne dépend que de `(start, end, nudgeDirection)`, ni du plateau, ni des
élévations, ni des murs, ni du seuil), et ce n'est pas un confort : mesure sur le consommateur
réel `get_tiles_obscuring_terrain` (20 000 appels, plateau 12×12) — **88,6 → 28,7 µs/appel,
facteur 3,1×**, pour **9 031 paires bloquées des deux côtés**. Le gain profite dès maintenant à
`services/ability_range.py`, seul consommateur du foyer.

**Écrit puis RETIRÉ — volet 2, le passe-plat.** Brancher `is_target_tile_obscured` sur le foyer
rougit **deux** assertions de `tests/engine/test_433r4r1r4r1_unobscured_canal_offline.py`
(étages 1 et 3), et elles ont **une seule cause** : un **CONFLIT DE CONTRAT sur l'inconnu**.

| une candidate de fat-line dont l'élévation n'est PAS captée | v1 | foyer complet |
|---|---|---|
| traitement | **RETIRÉE** de la liste → règle mono-candidate | `GetTileAt → null` → `blk = false` |
| verdict (crête à 4 sur l'autre) | **BLOQUE** | **NE BLOQUE PAS** (l'`ET` de la fat-line échoue) |

**Le natif ne tranche pas** : il n'a AUCUN état « élévation inconnue » —
`IdunBattle.Entities.TileExtensions$$GetElevationDifference` déréférence et lève. Les deux sont
donc des conventions de PORT, et celle du v1 est **versionnée et gardée**.

### 6.4 Ce qui reste, et l'argument pour trancher

Le régime est **INATTEIGNABLE LIVE** (63/63 tuiles portent `elevation`) : les deux contrats sont
indiscernables en bataille. Mais brancher sans trancher rendrait `master` ROUGE, donc le correctif
a été retiré et l'écart est désormais **écrit et chiffré dans la docstring** du v1.

L'argument en faveur du contrat du foyer, pour qui reprendra : le natif n'a qu'**UNE** forme de
non-blocage sans lecture d'élévation, `GetTileAt == null`, et le foyer en est la transcription.
« Retirer une candidate » n'a **aucune** contrepartie native — `DetermineBlockingTiles` prend
TOUJOURS `lineA[index]` **et** `lineB[index]`, et son seul régime mono-candidate est `tileA == tileB`
(les deux lignes tombant sur la même tuile). Trancher exige donc de réécrire le **véhicule** des
étages 1 et 3 de `test_433r4r1r4r1` — jamais la propriété qu'ils gardent, qui est que
`Unobscured` LIT `ctx.elev_by_pos` au lieu de re-dériver `by_coord` avec un défaut `0`, et qui
reste vraie dans les deux contrats.

Restent ensuite, dans le même résidu : câbler `is_wall_by_pos` (le canal est là), et retirer les
gates `dist == 2` écrits **AUX SITES** — `entities/selectors/units.py`, `entities/triggers.py` et
`battle_query.surrounding_enemies` — car tant qu'ils sont là, la correction du foyer y est inerte.
Ce dernier est **légitime** (sa zone est un ring-2, `SurroundingTilesSelector(r=2)`) ; les deux
autres sont le même bug, recopié au site. Les **cinq** call-sites qui ne bornent pas et où la
correction mordra : `playbook/boltstorm.py`, `playbook/light_im_up.py`,
`playbook/noncomparable/_base.py`, `playbook/noncomparable/doombolt.py`,
`playbook/noncomparable/summon_attack_range.py`.
