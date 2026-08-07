# #494 — `1102 Doombolt` : l'ordre des cibles, et les DEUX causes que le montage d'origine mélangeait

`test_doombolt_live.py` reste **VERT** alors que la 4ᵉ cible (celle à 0 coup) diffère du natif.
Le test n'est pas aveugle : `test_doombolt_zero_hit_target_and_sort_order_live` fait bien `N = 3` sur
**4** cibles et asserte l'ordre. Ce qui lui manque est la **GÉOMÉTRIE** qui fait diverger le tri —
ses quatre cibles sont placées par le montage `db-4`, où l'accord tient.

Mesures : `python scripts/python/probe_494_doombolt_sort_order.py --regime <A|B|C|I1..I5|J1|K1>`
(board `MC1_67`, seed 777, build `rnca9r7q6c`, 2026-08-07).

## 1. La divergence, reproduite et décomposée

Géométrie de `case-487` §8 (régime `A`) : `thousAhriman@(3,3)`, `orksNob@(3,4)` (cible du message),
`orksWarboss@(4,4)`, `orksBigMek@(2,4)`, `orksRuntherd@(3,5)`.

| étage | mesure |
|---|---|
| 0 — régime | `hp = maxHp = 400000` partout (`--hp-target`, qui met aussi `Armor = FixedArmor = 0`) |
| 1 — ordre SOURCE du port (`DoomboltAbility$$GetTargets`, avant tri) | `[83, 85, 79, 81]` |
| 2 — utilité portée par cible | **les 4 EXACTEMENT ÉGALES** (`0.2992485038`) |
| 3 — ordre final PORT | `[79, 81, 83, 85]`, coups `[1,1,1,0]` → frappe `{79, 81, 83}` |
| 4 — ordre final NATIF (séquence d'évènements) | `[79, 81, 85, 83]` → frappe `{79, 81, 85}` |

Les utilités portées étant **toutes égales**, le classement du port est entièrement décidé par son
**tie-break**, et `sort_units_by_damage_utility` impose `sorted(int(c) for c in candidates)` — l'ordre
par **id**, que son propre en-tête déclare être une approximation. C'est donc là que porte l'écart,
pas dans la répartition des coups (juste des deux côtés).

## 2. Le montage hétérogène MÉLANGE deux causes — et c'est lui qu'il fallait corriger d'abord

`orksBigMek` porte le trait **`Mechanic`** et POSE un `statDelta {fixedArmor: +1197}` sur ses
voisins. Mesuré, ligne `combatSnapshot` par ligne :

| régime | `orksBigMek` | `fixedArmor` résolu (79 / 81 / 83 / 85) |
|---|---|---|
| `A` | `(2,4)` | 1197 / **0** / 1197 / 1197 |
| `B` | `(4,3)` | 1197 / 1197 / 1197 / **0** |

**Déplacer UNE unité change l'ARMURE des autres.** Un A/B de position sur ce roster ne mesure donc
pas ce qu'il prétend mesurer. Et l'unité SANS le bonus est, dans les deux régimes, **la première du
classement natif** parmi les non-cibles : l'armure entre bien dans l'utilité native.

⇒ **Confirmation INDÉPENDANTE de `#527-r1`, sur une SECONDE ability**, et par un mécanisme
différent de celui qui l'avait établie (là : `--armor-target` posé à la main sur `AncestralFortune` ;
ici : une **aura**, donc une asymétrie d'armure *pilotée par la géométrie*). Le foyer accusé est le
même — `_target_utility` (`engine/runner/operations/damage_utility.py`) fabrique une prédiction
**pré-armure**, donc le port voit quatre cibles ex æquo là où le natif en distingue une.

## 3. Le régime PROPRE : N × `orksNob` identiques

Pour isoler l'ordre, les régimes `I*`/`J1`/`K1` montent **N copies de la même unité** — mêmes traits,
mêmes stats, `statDelta` VIDE partout (`REGIME EGALISE : OUI` imprimé par le probe). Plus aucune
stat de cible ne peut ordonner : ce qui reste est purement géométrique.

| régime | positions (cible du message en tête) | ordre SOURCE port | NATIF observé |
|---|---|---|---|
| `I1` | `(3,4) (4,4) (2,4) (3,5)` | `[83, 85, 79, 81]` | `[79, 85, 81, 83]` |
| `I3` | `(2,3) (1,4) (4,4) (3,5)` | `[81, 79, 85, 83]` | `[79, 85, 83, 81]` |
| `I5` | `(2,3) (1,4) (1,3) (3,5)` | `[81, 83, 79, 85]` | `[79, 83, 85, 81]` |
| `J1` | 5 cibles, `(2,3) (1,4) (1,3) (3,5) (4,4)` | `[81, 83, 79, 85, 87]` | `[79, 83, 85, …]` |
| `K1` | 3 cibles, `(3,4) (2,4) (4,4)` | `[81, 79, 83]` | `[79, 83, 81]` |

**Réfuté** : l'ordre par id (ce que le port impose), l'id décroissant, `cube-lex (x,y)` seul,
`cube-lex (x,y)` décroissant, `cube-lex (y,x)`, `cube-lex (z,x)`.

**Compatible avec les 7 géométries** (les 5 ci-dessus + `A` et `B` une fois l'étage armure inclus) :
l'ordre d'énumération des tuiles `cube-lex (x, y)` **ASCENDANT**, puis une **rotation d'un cran vers
la gauche** (le premier de l'énumération passe en dernier), puis le tri STABLE par utilité, puis le
`Remove(cible); Insert(0, cible)` de l'ability.

Deux des sept sont des **prédictions hors échantillon**, et elles portent sur un observable que
l'ordre seul ne donne pas — `C` change, donc la RÉPARTITION change :

* `J1` (5 cibles, `N = 3` → `[1,1,1,0,0]`) sépare une rotation d'UN cran d'une rotation de DEUX :
  prédit `[79, 83, 85, …]`, mesuré `[79, 83, 85]`.
* `K1` (3 cibles) sépare la rotation d'une **cible ABSENTE de la liste** : une absence donnerait
  `C = 2` donc `[2, 1]` (deux coups sur la cible du message) ; la rotation donne `C = 3` donc
  `[1, 1, 1]`. Mesuré : `[1, 1, 1]` — **l'absence est réfutée, la rotation tient**.

## 4. La rotation est MESURÉE, elle n'est pas ATTRIBUÉE — donc elle n'est pas portée

Toute la chaîne native a été LUE, et **aucun de ses étages ne réordonne** :

* `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` — triple
  boucle CUBE, **`f0` en boucle EXTERNE, `f1` en boucle MÉDIANE**, émission
  `CubeCoordinate(f0, f1, f2)`. `IdunBattle.Utils.Hex.CubeCoordinate$$ToAxialCoordinate` fixe
  `col = f0` et `row = (f0 + (f0 & 1))/2 + f2`, donc `f0 = x`, `f2 = z`, `f1 = y` — l'énumération
  est bien `lex(x, y)` ASCENDANT, exactement ce que `hexgeo.disk` produit ;
* `IdunBattle.Core.Services.BattleQuery$$GetSurroundingTiles` — `OrderedSet.Add` dans l'ordre de
  l'itérateur, **aucun tri** ;
* `IdunBattle.Entities.Selectors.SurroundingTilesSelector$$Select` — `OrderedSet.AddRange` ;
* `IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select` → `IdunBattle.DSL.TargetsSelector$$SelectUniqueUnits`
  — `ArraySet.Add` puis `ToList`. Les DEUX corps sont lus :
  `idun.shared.collections.ArraySetu003C__Il2CppFullySharedGenericTypeu003E$$Add` écrit à l'index
  `count` (et `$$Resize` quand il est plein), `…$$ToList` boucle `0 .. count-1` en `List.Add` —
  **ordre d'insertion STRICT**, aucune réorganisation par hachage ;
* `IdunBattle.Entities.Selectors.UnitsByTeamSelector$$Select` → `$$CountOrAdd` — `List.Add` filtré
  par `IdunBattle.Entities.UnitExtensions$$IsFriend` ;
* `IdunBattle.Entities.Selectors.UnobscuredEntitiesSelector$$Select` — `List.Add` filtré ;
* `IdunBattleLogic.Entities.DSLSelectors$$Damageable` — `UnitsWithoutTrait(source, 0x40e, 3)`
  (`0x40e` = `UnitTrait.Invincible`).

Le tri lui-même (`IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector$$Select`) est un
`System.Linq.Enumerable.OrderBy` sur `Fix64.op_UnaryNegation(dict[u])`, donc **STABLE** : à utilité
égale il rend l'ordre source tel quel.

⇒ Il y a un cran de un entre ce que le décompilé donne et ce que le live rend, et **je ne sais pas
d'où il vient**. Écrire `rot-1` dans le moteur serait un **fit** : une permutation mesurée sur sept
points mais qu'aucune fonction native ne justifie. Elle reste donc au **résidu `#494-r1`**.

## 5. Résidus

* **`#494-r1`** — l'ordre natif à utilité égale est l'énumération de tuiles `cube-lex (x, y)`
  **rotée d'un cran à gauche** ; mesuré sur 7 géométries (dont 2 prédictions hors échantillon), non
  attribué à un étage natif malgré la lecture complète de la chaîne (§4). Tant qu'il n'est pas
  attribué, le tie-break du port reste FAUX (`sorted(by id)`) et la 4ᵉ cible peut différer.
  Rejouer : `python probe_494_doombolt_sort_order.py --regime I1|I3|I5|J1|K1`.
  Pistes NON explorées, dans l'ordre où je les prendrais : le corps gshared de
  `System.Linq.Enumerable.OrderBy`/`OrderedEnumerable` sous IL2CPP (le seul comparateur du chemin) ;
  `idun.shared.collections.OrderedSet$$Add`/`$$AddRange`/`$$Remove` (l'`ArraySet`, lui, est LU et
  strictement insertion-ordonné) ; et `IdunBattle.DSL.TargetsSelector$$op_Subtraction`, qui retire
  la tuile du centre du disque `includeCenter = 1`.
* **`#527-r1`** (existant, agent en vol) — confirmé ici sur une seconde ability. Le montage à
  aura (`orksBigMek` `Mechanic`) en est un second témoin, à armures **non posées à la main**.
* **Hors périmètre, LU en chemin** : `IdunBattleLogic.Entities.DSLSelectors$$Damageable` n'est pas
  « vivant et PV > 0 » (ce que porte `entities/selectors/units.Damageable`) mais
  `UnitsWithoutTrait(source, UnitTrait.Invincible, 3)`. Non mesuré, non porté ici — le signaler,
  pas le corriger au passage.
