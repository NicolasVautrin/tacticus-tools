# `MinDistance` — distance HEX, jamais un chemin ; le proxy Chebyshev ouvrait un gate fermé

**Question binaire.** `IdunBattleLogic.Entities.DSLFactory$$MinDistance` mesure-t-il une distance
**HEX** entre tuiles, ou une distance de **CHEMIN** (pathfinding) ? Et le proxy Chebyshev qui le
remplaçait dans le chemin de DÉGÂT diverge-t-il du natif sur une configuration atteignable en
bataille ?

**Réponse : distance HEX.** Le dépôt affirmait **les deux**, à deux endroits différents ; l'un des
deux commentaires était faux et il était recopié dans du code qui tourne. Le proxy diverge, et pas
marginalement : sur le board MC1_67 il change la réponse du gate `<= 2` pour **5,82 %** des paires
de tuiles jouables, toujours dans le sens **permissif**.

---

## 1. L'énoncé natif, établi au décompilé (`gqfc5mff6c`)

### 1.1 La chaîne, appelant par appelant

`IdunBattleLogic.Entities.DSLFactory$$MinDistance(ctx, selA, selB)` construit une instance de la
classe `DAT_18324e3c0` en lui passant les **deux sélecteurs**. L'ancre fiable est le **singleton de
classe**, pas le nom du ctor : ghidra le folde et le mislabelle en
`HasUsedActiveAbilityThisTurnTrigger___ctor` (même piège que le comparateur du case #48, où le ctor
foldé faisait croire à `AmountIsEqualOrGreater`).

Le `Calculate` de cette classe est `IdunBattle.Entities.Formulas.MinDistanceFormula$$Calculate` :

```
best = int.MaxValue                                  # 0x7fffffff
foreach a in selector@+0x10.Select(ctx):
    pa = GetComponent<PositionComponent>(a)
    foreach b in selector@+0x18.Select(ctx):
        pb = GetComponent<PositionComponent>(b)
        best = Math.Min(best, PositionComponent.Distance(pb, pa))
return best
```

`IdunBattle.Entities.Components.PositionComponent$$Distance(a, b)` :

```
cubeA = AxialCoordinate.ToCubeCoordinate(a + 0x10)   # le champ axial vit à PositionComponent+0x10
cubeB = AxialCoordinate.ToCubeCoordinate(b + 0x10)
return CubeCoordinate.Distance(cubeA, cubeB)
```

`IdunBattle.Utils.Hex.AxialCoordinate$$ToCubeCoordinate(axial)` — la convention offset est
**explicite**, choisie par le 3ᵉ champ de l'axial (`axial+0x8`) :

```
off = (flag == 0) ? col + (col & 1) : col & ~1
x   = col ;  z = row - off / 2 ;  y = -(x + z) ;  cube+0xc = flag
```

`IdunBattle.Utils.Hex.CubeCoordinate$$Distance(a, b)` = `Max(Max(|dx|, |dy|), |dz|)`.

**Aucun pathfinding nulle part** : ni graphe, ni file, ni coût de terrain, ni obstacle. C'est de la
géométrie hexagonale pure, en coordonnées cube, sur la convention offset **odd-q** — et
`PositionComponent$$.ctor` pose le flag à **0**, donc la branche `col + (col & 1)`, qui est
exactement `hexgeo.to_cube` du dépôt.

Les deux formes de distance cube coïncident : `(|dx|+|dy|+|dz|)/2` (hexgeo) et `Max(|dx|,|dy|,|dz|)`
(natif) sont **égales** sur tout cube valide, où `x + y + z = 0`.

### 1.2 D'où venait la confusion : deux natifs distincts aux noms voisins

| symbole | ce qu'il mesure |
|---|---|
| `IdunBattleLogic.Entities.DSLFactory$$MinDistance` (nœud DSL) | **HEX** (§1.1) |
| `IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy` (utilité IA de MOUVEMENT) | **CHEMIN** — il itère les tuiles du `ClosestEnemy` (`EntityExtensions$$IterateTiles`), demande une **route** au service de pathfinding par un slot d'interface, et en lit la longueur (`route+0x18`) |

`engine/utilities/move.py` a **raison** d'écrire « distance de CHEMIN » : sa glose vaut pour le
second natif. Elle avait été recopiée à tort sur le premier.

### 1.3 Le gate concerné

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateTrigger`, lu verbatim :

```
On(8, 1)
  & AmountIsOdd(CurrentHitIndex())
  & get_OwnerIsCaster
  & !AmountIsGreater( MinDistance(owner@0x160, target@0x178), Direct(2) )
```

Les deux arguments de `MinDistance` sont des sélecteurs d'**UNITÉ** (`@0x160` = owner/caster,
`@0x178` = target), distincts des sélecteurs de TUILES (`CasterTiles@0x170`, `TargetTiles@0x190`).

---

## 2. Les deux commentaires du dépôt, et lequel avait tort

| fichier | ce qu'il disait | verdict |
|---|---|---|
| `engine/entities/traits/combat.py` | « Proxy distance (Chebyshev sur coordonnées offset) du MinDistance natif **(pathfinding)** » | **FAUX** — glose du natif homonyme, recopiée sur le nœud DSL |
| `engine/entities/selectors/units.py` | « `DSLFactory$$MinDistance` (**distance hex** entre MainTiles) » | **JUSTE** sur le fond ; précisé (le `Min` porte sur le produit cartésien des sélecteurs, pas sur des « MainTiles ») |

Les deux sont réconciliés dans le même commit, et le premier a été remplacé par une fonction
nommée — `entities.traits.combat.min_distance` — qui porte la chaîne d'appel complète et le nom du
natif homonyme à ne pas confondre.

---

## 3. Ce que le proxy Chebyshev en faisait

### 3.1 Il sous-estime TOUJOURS — donc il est PERMISSIF

`max(|dcol|, |drow|)` sur coordonnées offset n'est pas la distance hex. Balayage exhaustif 24×24
(`probe_min_distance_metric.py --stage offline`) :

* **0 violation** de `hex >= cheby` ⇒ le proxy ne sur-estime jamais ;
* écart maximal **12** sur la fenêtre ⇒ l'erreur n'est bornée par **aucune constante**.

Conséquence directe sur un gate `!(MinDistance > 2)` : le proxy **OUVRE ce que le natif FERME**.
C'est la signature exacte de la dégradation permissive — ni erreur, ni crash, invisible en
self-play, et c'est le trou qu'un entraînement irait exploiter.

### 3.2 Ce n'est pas un cas de coin

Les paires discriminantes du gate `<= 2` valent toutes `hex == 3, cheby == 2`, et leur patron
dépend de la **parité de la colonne de départ** (asymétrie odd-q) — **12 patrons** `(dcol, drow)` :

```
parité 0 : (-2,-2) (-2,+2) (-1,-2) (+1,-2) (+2,-2) (+2,+2)
parité 1 : (-2,-2) (-2,+2) (-1,+2) (+1,+2) (+2,-2) (+2,+2)
```

Sur le board **MC1_67** (7×9, 62 tuiles jouables, 1891 paires) :

| grandeur | valeur |
|---|---|
| paires dont la distance diffère | **881 (46,6 %)** |
| paires dont le **gate `<= 2` diverge** | **110 (5,82 %)** |

---

## 4. La mesure live

### 4.1 Le montage, et pourquoi il n'existait pas

Tout gate de distance se lit de la **même façon** dans un montage ordinaire, que le port mesure en
hex ou en Chebyshev — les deux métriques coïncident sur la majorité des paires, et notamment sur
les deux configurations qu'on monte spontanément (cible adjacente ; cible loin en ligne droite).
C'est pour cela que le gap a survécu à plusieurs campagnes : **un lot où les deux hypothèses
donnent le même résultat ne conclut rien.** La PR #177 l'avait d'ailleurs contourné explicitement
(son `_want_far` exige `cheby >= 3`, précisément pour neutraliser l'écart).

`_min_distance_metric_regime.py` fabrique le **complément** : la bande étroite `hex == 3 &&
cheby <= 2`. Le porteur y est **déplacé** (`_drive_ability` balaie `aiMovableTiles`), jamais
« bloqué par la géométrie de spawn ». `DakkaDakkaDakka` portant à 3 hex, la bande reste castable.

Montage : `orksKillaKan` (GetStuckIn) caste `DakkaDakkaDakka` (1171, 6 coups → 3 index impairs),
régime perçage-dominant (`--armor-target 6000`), crit et block neutralisés.

### 4.2 Le résultat — bande discriminante `split`, seed 777, MC1_67

Caster (4,6), cible (6,8) : **hexgeo = 3, cheby = 2**.

```
AVANT le fix
  live     =[300, 305, 332, 314, 311, 347]
  shipped  =[300, 305, 302, 367, 347, 347]   MISMATCH   <- le proxy ouvrait le gate
  no_maybe =[300, 305, 332, 314, 311, 347]   OK         <- le natif l'avait fermé
  always   =[300, 305, 302, 367, 347, 347]   MISMATCH
  -> shipped MISMATCH  no_maybe OK  parity MISMATCH  always MISMATCH  (discriminant: oui)

APRÈS le fix
  -> shipped OK  no_maybe OK  parity OK  always MISMATCH  (discriminant: oui)
```

`always` (canal branché **sans** le gate de distance) reste MISMATCH après le fix : le montage
prouve donc toujours que le gate **existe** et qu'il est **fermé** ici — ce n'est pas un « tout
coïncide » vide.

### 4.3 Le témoin — `agree`, cible adjacente

Caster (5,8), cible (6,8) : **hexgeo = 1, cheby = 1**. Les deux métriques valent 1, donc aucune
hypothèse de métrique ne les sépare.

```
live     =[300, 305, 302, 367, 347, 347]      identique AVANT et APRÈS
shipped  =[300, 305, 302, 367, 347, 347]  OK  identique AVANT et APRÈS
no_maybe =[300, 305, 332, 314, 311, 347]  MISMATCH
```

**Bit-exact de part et d'autre du fix.** Sans lui, un `shipped OK` dans la bande discriminante ne
distinguerait pas « la métrique est juste » de « le canal entier s'est éteint ».

Recoupement non cherché : le `live` du témoin **est** le `shipped` d'avant-fix de la bande
discriminante, au coup près — cohérent, puisque la seule variable est l'état du gate.

### 4.4 Garde vue ROUGE (mutation adversariale)

Le proxy remis en place dans `min_distance`, les **deux** seeds `split` échouent et le témoin reste
**vert** :

```
[MINDIST split] seed=31337 live=[323, 348, 306, 373, 327, 353]
[MINDIST split] shipped  =[323, 348, 307, 323, 353, 302, 331]
[MINDIST split] no_maybe =[323, 348, 306, 373, 327, 353]
E   AssertionError: [split seed 31337] le port LIVRE ne reproduit pas le live dans la bande ou les
E   deux metriques DESACCORDENT : shipped=[323, 348, 307, 323, 353, 302, 331]
E   live=[323, 348, 306, 373, 327, 353] (gate ferme=[323, 348, 306, 373, 327, 353])
E   Left contains one more item: 331
FAILED test_min_distance_metric_live.py::test_min_distance_gate_uses_hex_metric_live[777]
FAILED test_min_distance_metric_live.py::test_min_distance_gate_uses_hex_metric_live[31337]
2 failed, 2 passed
```

Sur la seed 31337 l'effet est plus fort qu'un décalage de flux : le proxy **matérialise un 7ᵉ coup**
(`331`) que le natif n'inflige pas.

Même mutation sur le test de la PR #178, à sa nouvelle distance 3 :

```
[DDD A dist=3] snappa=u83 cible=u77 autres=[79, 81]
[DDD A] live=[2001, 2035, 2211, 2093, 2073, 2313]
[DDD A] off =[2001, 2035, 2016, 2446, 2313, 2313]
E   AssertionError: per-coup offline [...] != live [...]  (At index 2 diff: 2016 != 2211)
FAILED test_dakka_dakka_dakka_live.py::test_dakka_main_volley_live_equals_offline[3]
1 failed, 4 passed
```

⇒ la distance 3 **est** discriminante ; ce n'est pas un cas ajouté qui passerait trivialement.

---

## 5. Le fix

Foyer **unique**, consommé par les deux faces du même gate natif :

```
engine/entities/traits/combat.py::min_distance          # mirror nommé, hexgeo.distance
  <- GetStuckInTrait.as_attacker_bonus_hits             # face PRÉDICTION
  <- engine/runner/damage_model.py::getstuckin_combat_chance   # face COMBAT
       <- damage_ops/normal.py   (attaque normale)
       <- damage_ops/ability.py  (vecteur ability)
```

`_cheby` disparaît des deux modules. `getstuckin_combat_chance` mélangeait d'ailleurs les deux
métriques dans la même fonction : `_cheby` pour le gate de portée, mais le service partagé
`are_tiles_adjacent` (hex + porte d'élévation) pour compter les alliés adjacents.

### 5.1 Inventaire des autres consommateurs — ils n'ont PAS la même réponse

| site | ce que le natif fait | verdict |
|---|---|---|
| `engine/entities/traits/combat.py::_cheby` | `MinDistance` = hex | **CORRIGÉ** |
| `engine/runner/damage_model.py::_cheby` | `MinDistance` = hex | **CORRIGÉ** |
| `predict_samples.py::_cheby` l.87-88 | *aucun natif* — heuristique de pilotage (choisir la tuile qui rapproche d'un ennemi) | **laissé** : ne mirrore rien ; sous-estimer y choisit une tuile légèrement sous-optimale, ne fausse aucune mesure |
| `predict_samples.py::_cheby` l.143 | *aucun natif* — appliqué à un couple **(min, max) de DÉGÂTS**, pas à des positions : norme infinie pour la tolérance d'agrément | **laissé** : nom trompeur, sémantique correcte |
| `_probe_overwatch.py::cheby` | *aucun natif* — même heuristique de pilotage | **laissé** |
| `engine/entities/selectors/units.py::UnitsDirectlyBehind` | `MinDistance(caster, cand) > MinDistance(caster, target)` | déjà `hexgeo.distance` — **correct**, validé live (`test_plasma_cannon_lateral_live`) |
| `engine/runner/abilities/bloodangels.py` | `MinDistance(It, CasterTiles)` — sélecteur de **TUILES** | déjà hex — **correct** ; c'est le cas où le `Min` balaie bien une empreinte |
| `engine/utilities/move.py` | `MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy` = **chemin** | **correct**, et c'est un natif DIFFÉRENT |

**Ne pas généraliser depuis le premier site** : trois occurrences de `cheby` sur cinq ne mirroraient
aucune primitive native, et le seul autre `MinDistance*` du dépôt mesure réellement un chemin.

### 5.2 La porte d'élévation `|dElev| < 2` — elle n'appartient PAS à ce gate

`engine/battle_query.py::is_adjacent` / `are_entities_adjacent` portent une porte d'élévation. Le
proxy `_cheby` l'ignorait — **et le natif `MinDistance` l'ignore aussi** :
`CubeCoordinate$$Distance` ne lit que les composantes `[0]`, `[1]`, `[2]` du cube ; le 4ᵉ champ,
propagé par `ToCubeCoordinate` et `Difference`, est le **flag de convention offset**, pas une
élévation.

Ce sont deux primitives natives distinctes :

* `MinDistanceFormula` — distance pure, **sans** élévation ;
* `MovementUtil$$AreTilesAdjacent` — `dElev < 2 && (a == b || IsNeighbour(a, b))`.

⇒ aucun retrofit d'élévation à faire sur ce gate ; l'ajouter serait une invention.

### 5.3 Piste « min sur les EMPREINTES » — RÉFUTÉE au décompilé

`MinDistanceFormula$$Calculate` fait `GetComponent<PositionComponent>` sur chaque élément rendu par
les sélecteurs et n'appelle **jamais** `EntityExtensions$$IterateTiles` ni `GetTiles`. Les deux
natifs qui, eux, veulent l'empreinte, les appellent explicitement :

```
MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy -> EntityExtensions$$IterateTiles(...)
BattleQuery$$AreEntitiesAdjacent -> MovementUtil$$AreTilesAdjacent(GetTiles(a), GetTiles(b))
```

Le `Min` porte donc sur le **produit cartésien des deux sélecteurs**. L'empreinte n'entre en jeu
que si le sélecteur est un sélecteur de TUILES (`CasterTiles@0x170`) — ce qui explique le préfixe
`Min-` et le cas `bloodangels.py`. Le trigger `GetStuckIn` passe `owner@0x160` / `target@0x178`,
donc des **unités** : une seule paire, une seule distance.

⚠ **Non distingué LIVE** : aucun porteur `GetStuckIn` du pool n'est multi-tuile, donc le montage ne
sépare pas « position d'ancrage » de « min sur l'empreinte ». Le verdict repose sur le décompilé
seul.

---

## 6. Ce qui n'est PAS couvert

* **Le volet multi-tuile** (§5.3) : réfuté au décompilé, non confronté live faute de porteur.
* **La branche `flag != 0`** de `ToCubeCoordinate` (convention **even-q**) : `PositionComponent$$.ctor`
  pose le flag à 0 et aucun call-site porté ne le change ; la branche existe dans le binaire mais
  n'est jamais exercée par les montages. Si un board ou une entité posait ce flag, `hexgeo` serait
  faux — non détecté par les gardes actuelles.
* **La division C signée** `(int)off / 2` de `ToCubeCoordinate` tronque vers zéro, là où le `//` de
  `hexgeo` arrondit vers `-inf`. Sans effet pour `col >= 0`, ce qui est le cas de toute colonne de
  plateau ; jamais exercé hors de ce domaine.
* **Les autres gates de distance** (`IsCharging`, les règles d'adjacence) : ils passent par
  `MovementUtil$$AreTilesAdjacent`, une primitive **différente**, déjà portée en hex + élévation.
  Aucun n'a été re-mesuré ici.
* **La face PRÉDICTION du fold GetStuckIn** n'est exercée par aucun montage live de ce cas : elle ne
  compte le fold que si `GetBonusHitChance == 100` (≥ 2 orks ou ≥ 4 alliés adjacents à la cible),
  configuration qu'aucune des seeds jouées ne réunit. Le fix y est **structurellement identique**
  (même fonction `min_distance`), mais l'effet de la métrique sur cette face reste non confronté.
