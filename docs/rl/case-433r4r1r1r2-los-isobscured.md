# #433-r4-r1-r1-r2 — la LoS d'`IsObscured` : RE COMPLÈTE, port NON MODIFIÉ (foyer occupé)

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
