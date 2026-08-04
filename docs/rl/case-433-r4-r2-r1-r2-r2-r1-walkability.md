# #433-r4-r2-r1-r2-r2-r1 — l'étage qui retire les tuiles NON MARCHABLES

**Verdict : FERMÉ.** L'étage est nommé, porté et confronté sur quatre boards. L'écart
**PERMISSIF** passe de **34 tuiles attribuées à tort à 0** sur le régime le plus mordant, et de
**40 à 0** sur celui qui porte les deux volets — contre **1 seule tuile** dans la mesure héritée.

## 1. La réponse à la question binaire

**Le retrait vit dans `IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange`, donc EN AMONT
de la ligne de vue.** Ce n'est pas un quatrième prédicat : c'est un `RemoveAll` **interne à la
fonction qui CONSTRUIT la zone**, appliqué avant que les trois `RemoveAll` de
`GetPossibleTargetsForOptions` ne la voient.

```
GetTilesInRange(caster, casterTiles, options, range)
    ... 5 branches de construction ; les deux qui passent par un slot IBattleQuery
        (0x67 GetTilesInRadius, 0x51 GetAdjacentTiles) recoivent DEJA `onlyWalkableTiles`
        = le meme bit — le RemoveAll final leur est donc IDEMPOTENT
    if ((options.Rules & AllowUnwalkableTargetTile) == 0)          # bit 43
        RemoveAll(zone, TargetingQuery.<>c.<GetTilesInRange>b__36_0)

TargetingQuery.u003Cu003Ec$$u003CGetTilesInRangeu003Eb__36_0(t)
    = !TileExtensions.IsWalkable(t, checkFog: true)
```

Le prédicat est un délégué **statique en cache** (`<>c`), pas une closure : d'où l'absence de
`DisplayClass` et le fait qu'il ne dépend d'aucun contexte d'appel.

**Il est donc indispensable pour les branches qui ne filtrent pas** : `UseWholeBoard`
(slot `0x69` `GetAllTiles`) et la branche `casterTiles` d'une portée nulle.

## 2. DEUX volets, DEUX canaux — et le second n'est pas dérivable du premier

```
IsWalkable(tile, checkFog)
    if (tile == null)                            return false
    m = tile.<MovementComponent @+0x40>
    if (m.<+0x10> != 0)                          return false      # terrain infranchissable
    if (!checkFog)                               return true
    return tile.<TileComponent @+0x20>.<IsInFogOfWar @+0x40> == 0
```

`IdunBattle.Core.Services.BattleQuery$$IsWalkableTile` — la source du champ `walkable` du
`boardGraph` — vaut `IsTile(tile) && comp.<+0x10> == 0` : **le premier volet SEUL**, elle n'a pas
de paramètre `checkFog`. Le second se lit sur `isInFog` (`TileComponent+0x40`, publié par #403).

**Mesuré** : sur `C6_02`, **31 tuiles sur 63** sont `walkable == True` **et** `isInFog == True`.
Rabattre l'un sur l'autre laisse donc 26 faux positifs (cf. §4). Le fog est corrélé **exactement**
à `Tile.RoomID >= 0` (space hulk) : 32 tuiles `RoomID >= 0`, 32 en fog.

## 3. Ce qui est porté

* **`engine/services/targeting_query.tile_removed_by_walkability(rules, walkable, is_in_fog)`** —
  foyer UNIQUE, avec `ALLOW_UNWALKABLE_TARGET_TILE = 1 << 43`. Tri-état strict : un canal `None`
  rend son volet inerte, un `rules` non RE-lu désarme l'étage.
* **`engine/services/ability_range`** — `_unwalkable`, appliqué au terme **attaque normale** et à
  **chaque ability**, entre le rayon et la ligne de vue (l'ordre natif ; les `RemoveAll` en aval
  sont commutatifs, celui-ci est le seul en amont).
* **Le canal `is_in_fog_by_pos`** : `context._board_is_in_fog` (caché par rid, comme `walkable`),
  `state_bridge._board_fog_map`, `AiDecisionContext`, `NCContext`, `NonComparableGenerator`,
  `EarlyWarningOverridePlaybook`. **Aucun capteur neuf, aucune réinjection** — le champ était
  publié et jeté, comme `isWall` en `#433-r4-r2-r1-r2` et `teamId` en `-r2-r2`.

## 4. La confrontation — quatre boards, deux volets séparés

Montage repris de `#433-r4-r2-r1-r2-r2` : `1161 TwinSmartMissileSystem` (`UseWholeBoard`,
`rules = 0x40004000`, donc **sans** le bit 43) greffée seule sur `custoBladeChampion` (arme de
mêlée : le prédicat de ligne de vue est structurellement muet à `d = 1`). Oracle =
`aiMovableTiles {threat: true}` → `AttackQuery$$GetAllTilesInAbilityRange`, zone = tout le plateau.
Position du caster **choisie** pour maximiser le gisement, jamais subie.

| board | tuiles | non marchables | `walkable && fog` | zone NATIVE | port AVANT | port **1 volet** | port APRÈS |
|---|---|---|---|---|---|---|---|
| `C5_19` | 63 | 34 | 0 | 29 | **34 FP** | 0 | **0** |
| `C6_02` | 63 | 22 | 31 | 10 | **40 FP** | **26 FP** | **0** |
| `MC1_74` | 63 | 6 | 0 | 53 | 6 FP | 0 | **0** |
| `MC1_67` | 63 | 1 | 0 | 62 | 1 FP | 0 | **0** |

Faux négatifs : **0** partout, avant comme après — l'étage ne peut que retirer.

**Trois choses que ce tableau établit, et qu'un total nu n'aurait pas dites :**

* sur `C5_19`, `zone_native == 29 == 63 - 34` **exactement** : le natif ne met **aucune** tuile
  non marchable dans la zone, et il n'en retire aucune autre ;
* la colonne **1 volet** est la contre-épreuve : un port qui lirait le seul `walkable` reste faux
  de 26 tuiles. Le `0` de la colonne APRÈS serait sinon compatible avec ce modèle-là ;
* la ventilation par cause sur `C6_02` — 14 FP non marchables + 26 FP en fog + **0 autre** —
  impute chaque écart à SON volet, et montre qu'aucun écart d'une autre cause ne subsiste.

**Le greffon est en TEAM 1, et c'est ce qui rend le régime FOG confrontable** : les 15 boards à fog
sont tous des `C6_*`, où l'équipe 2 n'est **pas déployée** (mesuré : 0 unité team 2 sur `C6_02`,
`C6_13`, `C6_14`). La zone de `GetAllTilesInAbilityRange` ne dépend d'aucun ennemi.

## 5. Ce qui n'est PAS couvert

* ~~**32 abilities du pool spawnable n'ont pas leur masque RE-lu**~~ — **FERMÉ** le 2026-08-04 par
  `#433-r4-r2-r1-r2-r2-r1-r1` (`case-433-r4-r2-r1-r2-r2-r1-r1-masques-du-pool.md`) : les 32 sont
  lues, `TARGETING_RANGE_BY_ABILITY` est **supprimée** (elle forkait la portée de son propre
  masque), et **aucune** des 32 ne porte le bit 43 — le taux de base passe de 1/106 à **1/138**,
  seul `1116 RadBombardment` le portant. Le terme de l'**attaque normale** reste gaté
  (`NORMAL_ATTACK_TARGETING_OPTIONS.rules = 0x4002`). Confronté live sur une ability **du pool** —
  la présente tranche ne l'avait fait que sur une ability **greffée**.
* **Le fog est CACHÉ par rid**, comme `walkable`/`isWall`. Mesuré **stable** (32 tuiles inchangées
  après deux `endturn` sur `C6_02`) ; un mode qui le révélerait en cours de bataille rendrait le
  cache faux.
* **Deux court-circuits amont de `GetPossibleTargetsForOptions` ne sont pas modélisés** :
  `TargetIsCaster` (bit 39, zone = `casterTiles` **sans** passer par `GetTilesInRange`) et
  `TargetIsMachine` (bit 44). Ils court-circuitent aussi le rayon, donc ils précèdent tout ce que
  ce module porte.
* **Les ajouts postérieurs au `RemoveAll`** : `CasterIsPossibleTarget` (bit 15) et
  `TargetIsCasterOrEnemy` (bit 57) réinjectent `casterTiles` **après** le retrait — une tuile de
  caster non marchable resterait donc dans la zone native. Non exercé ici (aucun des masques du
  montage ne les porte).
* **Le régime FOG n'est confronté que côté team 1** (cf. §4) ; aucun board à fog ne déploie deux
  camps.

## 6. Validation

* **OFFLINE** — `tests/engine/test_433_r4_r2_r1_r2_r2_r1_walkability_offline.py` : **15 passed**
  (table de vérité du foyer, bit 43 confronté à l'enum du registre, les deux volets, tri-état,
  câblage attaque normale + par ability, `1116` exempte, l'étage mord sans canal de ligne de vue,
  les quatre seams du canal `isInFog`).
* **CONTRE-ÉPREUVE DE MUTATION** — 5 mutations du port, **5 rouges**. Elle a servi à quelque chose :
  la 5ᵉ (couper l'appel dans le terme **par ability**) laissait d'abord le fichier **VERT**, parce
  que le garde interrogeait le FOYER et non son CÂBLAGE — deux choses indépendantes. D'où
  `test_the_ability_term_wiring_is_guarded_beyond_its_foyer`, qui exerce le chemin complet sur une
  tuile à `d = 3` (hors portée de l'arme, donc le terme normal ne peut pas la couvrir).
* **LIVE** — `tests/engine/test_433_r4_r2_r1_r2_r2_r1_walkability_live.py` : **8 passed**
  (deux régimes, garde anti-dégénérescence sur chacun, contre-épreuve 1 volet, ventilation).
* **NON-RÉGRESSION** — offline : **135 passed** sur les 7 fichiers de la lignée `#433-r4-r2` ;
  live : `test_433_r4_r2_r1_r2_r2_friend_gates_live` **8**, `..._r2_line_of_sight_live` **7**,
  `..._r1_ability_range_live` **6**, `..._r1_r1_a_whole_board_gates_live` **3**,
  `..._r1_r1_c_caster_gates_live` **13**, `test_433_r4_r2_adjacency_foyer_live` **7**,
  `test_356_noncomparable_oracle_live` **14**.
* **BANQUE** — `scripts/ratchets.ps1`, relevé daté dans le rapport de PR.
