# R28 — `PickRandomly` : dans quel ORDRE, et sur quel ENSEMBLE ?

Deux questions distinctes, et il faut répondre aux deux : l'**ordre** des candidats présenté au tirage,
et la **nature** de ce qu'on tire. Un tirage juste sur un ensemble faux est faux.

Build `gqfc5mff6c`. Décompilé = vérité, live = confirmation.

---

## 1. Le sélecteur natif, lu de bout en bout

`IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` :

```
candidates = source.Select(entities).ToList()          // <-- AUCUN tri
if (amountNode != null) this.amount = amountNode.Calculate(entities)
result = new List<T>()
if (!this.skipForcedTargets)                            // champ +0x38
    APickSelector.AddForcedTargetsAndUpdateCandidates(entities.Caster, candidates, result)
i = result.Count
while (i < amount) {
    if (candidates.Count < 1) return result              // SEULE sortie anticipée
    idx = rng.NextInternal(0, candidates.Count)          // 1 TIRAGE, inconditionnel
    result.Add(candidates.ElementAt(idx))
    if (!allowRepeat) candidates.RemoveAt(idx)           // champ +0x30
    else if (result.Count(x => x == picked) == maxRepeat) candidates.RemoveAt(idx)   // +0x34
    i++
}
```

Champs, lus aux deux `PickRandomAmountSelector$$.ctor` : `+0x18` sélecteur source · `+0x20` amount
(int) · `+0x28` amount (nœud) · `+0x30` `allowRepeat` · `+0x34` `maxRepeat` · `+0x38` gate des
forced-targets · `+0x40` fournisseur de RNG.

`IdunBattleLogic.Entities.DSLFactory$$PickRandomly` (les deux surcharges) propage ses 5ᵉ/6ᵉ/7ᵉ arguments
tels quels ; les `ExecuteBehaviour` lus passent `(…, 0, 0x7fffffff, false)` — donc `allowRepeat=false`,
`maxRepeat=0x7fffffff`, **forced-targets ACTIVÉ**.

**Le seul tri du chemin** est celui d'`IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` :

```
targets = this.targetSelector.Select(entities)
if (targets.Count > 1) targets = targets.OrderBy(b__5_0).ToList()   // APRES la résolution
foreach (t in targets) ExecuteTarget(caster, t, …)
```

Il s'applique donc **après** le `PickRandomly`, jamais avant.

---

## 2. Sous-item 1 — l'ordre du pool : RÉEL, porté, confirmé live

### Ce qui n'allait pas

`behaviours/combat.py` id-triait la liste **avant** le tirage (`sorted(…, key=id)` puis
`_pick_randomly_n` puis re-tri), même motif dans les deux collapses impératifs `necrons.py` (Harbinger)
et `darkangels.py` (Supercharge). Ce pré-tri n'a **aucun homologue natif**. À index de tirage égal il
faisait piquer une **autre** unité dès que `|pool| > amount`.

Il ne suffisait pas de le retirer : l'ordre qui restait dessous (`ctx.units`, ≈ ordre des ids) n'était
pas davantage l'ordre natif. Le natif n'énumère pas des entités — il **itère les TUILES** du sélecteur
et résout l'occupant de chacune (`UnitsOnTilesSelector$$Select`). Il y a **deux itérateurs distincts** :

| sélecteur DSL | itérateur natif | ordre |
|---|---|---|
| `AdjacentTiles(x)` | `BattleQuery$$GetAdjacentTiles` → `TileQuery$$IterateAdjacentTiles` | la **liste d'adjacence STOCKÉE** sur la tuile = le champ brut `boardGraph.neighbours` |
| `SurroundingTiles(x, r)` | `BattleQuery$$GetSurroundingTiles` → `TileQuery$$IterateSurroundingTiles` | **triple boucle CUBE** : `for x in [cx-r,cx+r] { for y in [cy-r,cy+r] { for z in [cz-r,cz+r] { if (x+y+z==0) yield GetTileEntityAt(ToAxial(x,y,z)) }}}` |

`AdjacentTilesSelector$$Select` accumule dans un `OrderedSet` (ordre d'insertion) ;
`SurroundingTilesSelector$$Select` fait de même via `AddRange`. `CombinedSelector$$SelectExclusion`
(`op_Subtraction`) préserve l'ordre de l'opérande GAUCHE. Les filtres en aval (`Enemies`, `Damageable`,
`Unobscured`, `TilesOnSameElevation`, `FromTrigger`) reconstruisent une liste dans l'ordre reçu.

`hexgeo.to_cube`/`from_cube` sont exactement `AxialCoordinate$$ToCubeCoordinate` /
`CubeCoordinate$$ToAxialCoordinate` (branche offset-parity 0), et `hexgeo.disk` énumère dans l'ordre de
la triple boucle — d'où sa réutilisation directe.

### Ce qui a été porté

- `Board.neighbours_native(tid)` = champ brut `neighbours`, ni trié ni symétrisé (foyer unique ;
  `spawn._adjacent_tiles` y délègue). `neighbours()` reste la topologie (triée/symétrisée) du
  pathfinding.
- `_tile_enum_rank(board, center, radius, order)` (`dsl/base.py`) = l'ordre d'énumération des tuiles,
  `order ∈ {adjacent, surrounding}`.
- `_within(..., board, order)` trie **stablement** son résultat par ce rang. **L'ENSEMBLE est
  inchangé** : une unité dont la tuile n'apparaît pas dans l'énumération reste, en fin de liste.
- Les sélecteurs passent leur itérateur : `AdjacentUnits`/`AdjacentEnemies`/`AdjacentFriends` →
  `adjacent` ; `SurroundingUnits`/`SurroundingEnemies`/`SurroundingFriends` → `surrounding` ;
  `UnitsDirectlyBehind` → `surrounding` (sa chaîne part de `SurroundingTiles(target,1,1)`).
  Le nœud `AdjacentTiles` lit `neighbours_native`.
- Les trois sites de pré-tri sont supprimés ; le tri par id vit désormais **après** le pick, là où
  `AttackBehaviour$$Execute` le place.
- Sans `board` (tests unitaires, contextes sans graphe) l'ordre historique est conservé : c'est une
  **dégradation documentée**, jamais un mirror.

### Confirmation live

`probe_r28_pick_order.py` (versionné) monte des géométries **craftées pour que l'ordre TUILE et l'ordre
ID soient opposés**, et confronte trois modèles : le live, le port (ordre source) et le port d'avant
(pool id-trié), rejoués sur le **même état RNG**.

| scénario | pool (ordre source) | victime M_SRC | victime M_ID | **victime LIVE** | genrand live / port |
|---|---|---|---|---|---|
| BringerOfDespair 1022, `blackTerminator`, MC1_67/777 — 3 ennemis adjacents au caster, `amount=1` | `[81, 79]` (id-trié : `[79, 81]`) | **79** | 81 | **79** | 25 / 19 (confond hors-R28, cf. §5) |
| BringerOfDespair 1022, C2_37/31337 | `[53, 51]` (id-trié : `[51, 53]`) | **53** | 51 | **53** | **19 / 19, per-coup bit-exact (8 coups, ratios 1.0)** |
| PlasmaCannon 1150, `darkaTerminator`, MC1_67/777 — **3** unités directly-behind, `amount=2`, ids assignés à contre-sens du rang cube | rang cube | **[81, 83]** | [79, 81] | **[81, 83]** | **16 / 16, per-coup bit-exact (7 coups)** |

Les deux itérateurs sont donc confirmés séparément. Le modèle id-trié est **réfuté** dans les trois cas
(sur PlasmaCannon il désigne une unité qui ne prend **aucun** dégât live, et consomme 20 genrand au lieu
de 16).

---

## 3. Sous-item 2 — Fragstorm tire des HEXES : RÉEL, porté, **invalidable live**

`FragstormAbility$$ExecuteBehaviour` :

```
adjTiles = AdjacentTiles(target@0x178)
sel      = adjTiles  op_Subtraction  Tiles(Friends(caster@0x160, adjTiles, 3))
splash   = AttackWithAttackDamage(caster, PickRandomly(sel, GetNumberConstant(0x11)), …, 0x32)
```

`sel` est un sélecteur de **TUILES**. Les tuiles VIDES y restent : seules les tuiles portant un **ami du
caster** sont soustraites. Le natif ne résout l'occupant qu'à `AttackDamageBehaviour$$ExecuteTarget`,
donc **après** le tirage et après l'`OrderBy` — un hex piqué sans occupant est un **coup gaspillé**.

Le port tirait des OCCUPANTS (`Alive(Sub(AdjacentUnits, AdjacentFriends))`) : cardinal du pool faux
(donc nombre de tirages faux, donc tout le flux RNG aval décalé) **et** ensemble touché faux (tout
ennemi adjacent était touché dès qu'ils étaient ≤ 4).

Porté : `Sub(AdjacentTiles(TargetTile()), Tiles(Friends(Units(AdjacentTiles(TargetTile()))), as_ids=True))`
+ feuille `multi=True, pick_n=4, tile_domain=True` (tire des ids de tuile → `OrderBy` par id de tuile →
occupant vivant de chacune, aucun ⇒ rien). `Tiles(as_ids=True)` est nécessaire : `Tiles` rendait des
POSITIONS, qui ne se soustraient pas à des ids — la soustraction aurait été un no-op silencieux.

**Pourquoi ce volet n'est pas confronté live** : le seul porteur de `Fragstorm` (1078) est
`templSmnAggressor`, un **summon** dont le seul invocateur est le power-up
`PowerUp_SummonSpawn_templSmnAggressor` — aucune unité du pool ne l'amène en bataille. `templAggressor`
(Burchard), lui, est bien au `--list-pool` mais porte une **autre** ability,
`FragstormGrenadeLauncher` (chaîne de coups restants, aucun `PickRandomly`). Le volet reste donc un
**mirror-offline**, gardé par une assertion **structurelle** (`test_fragstorm_migration_live.py`) : le
pool résolu doit être exactement `neighbours_native(tuile cible) − tuiles amies` **et contenir au moins
une tuile vide**, sans quoi le test dit lui-même qu'il ne sépare pas les deux modèles.

---

## 4. Sous-item 3 — `AddForcedTargetsAndUpdateCandidates` : NON PERTINENT (verdict, pas un trou)

```
void AddForcedTargetsAndUpdateCandidates(Entity caster, List<T> candidates, List<T> result) {
    if (caster == null) return;
    if (caster.GetOnlyTargets().Count <= 0) return;              // <-- sortie de fait
    for (i = candidates.Count - 1; i >= 0; i--) {
        if (result.Count >= amount) return;
        if (caster.GetOnlyTargets().Contains(candidates[i].Id)) {
            result.Add(candidates[i]);
            if (!allowRepeat) candidates.RemoveAt(i);
        }
    }
}
```

`entities.Caster` = slot `+0x8` de l'`AbilityEntities` (établi par `CasterSelector$$Select`, qui lit ce
même slot ; `ActorSelector` lit `+0x0`).
`IdunBattle.Entities.UnitExtensions$$GetOnlyTargets` rend la liste d'ids stockée à `+0x50` du composant
de cibles forcées (vide si l'`OwnerComponent` est overridé).

**Cette liste n'a qu'un seul écrivain natif** :
`IdunBattleLogic.Entities.Abilities.Active.Loki.InstinctiveBehaviour_UpdateTargetAbility$$CreateBehaviour`
— l'unique XREF de `IdunBattleLogic.Entities.DSLFactory$$AddForcedAttackTarget` (les deux autres XREFs
sont des tables de données). Les porteurs du trait `InstinctiveBehaviour` (2021) sont **23 unités**, tous
npc/summons Tyranides (Ripper Swarm, Hormagaunt, Barbgaunt, Termagant, Spore Mine) et **aucun n'a
d'active ability** — donc aucun n'atteint jamais un `PickRandomly`.

Sur tout porteur confrontable la liste est vide : la fonction retourne immédiatement, `i = result.Count`
vaut 0, et **aucun tirage n'est consommé**. La porter serait un no-op spéculatif. Le verdict est écrit
dans le docstring de `_pick_randomly_n`, avec la condition de réouverture (un porteur
d'`InstinctiveBehaviour` qui gagnerait une ability à `PickRandomly`).

`abilities/targeting.py:79` (`TargetIsAllowedForCaster`, bit 23) touche le **même** `GetOnlyTargets`
mais sur un autre axe (gate de cible d'un cast) : hors périmètre R28, et ce fichier n'a pas été modifié.

---

## 5. Garde anti-sur-correction, et ce qui n'est PAS couvert

**Anti-sur-correction.** Un changement d'ordre décale toute la séquence RNG en aval ; un scénario où
l'ordre ne doit RIEN changer doit rester bit-exact. C'est exactement le rôle de
`test_pick_randomly_rng_live.py` (PlasmaCannon, régimes `k=1` et `k=2` avec `amount=2` : le pool tient
dans `amount`, donc **tout** le pool est pris quel que soit l'ordre). Les 11 tests restent verts après le
changement, per-coup bit-exact live/port sur la main ET le splash.

**Non couvert, nommé** :

- **Fragstorm (§3)** — mirror-offline, porteur hors pool. Rien ne le confronte au live.
- **Porte d'élévation d'`IterateAdjacentTiles`** — le natif ne voit un voisin ring-1 que si
  `|Δélévation| < 2` ; le port garde son test de distance hex pour l'ENSEMBLE et ne réordonne que ce
  qu'il a déjà sélectionné. Sur les géométries mesurées le champ brut `neighbours` et la distance hex 1
  coïncidaient (aucune unité « hors rang »). Résidu distinct, non traité ici.
- **Écart de comptage du 1ᵉʳ scénario BringerOfDespair** (live 25 genrand / port 19 ; 5 événements de
  dégât par cible au lieu de 4) — **confond hors R28** : le 2ᵉ scénario, même ability, même port, est
  bit-exact à 19/19 avec 4+4 coups. Le surplus vient donc de l'état de cette bataille-là (un canal de
  dégât supplémentaire), pas du tirage. Non instruit.
- **`SendInTheNextWave`** (`astramilitarum.py`) — son pool est déjà construit par `hexgeo.disk`, donc
  **déjà** dans l'ordre cube natif ; aucun pré-tri à retirer. Vérifié, laissé tel quel.
- **Supercharge** — le port a hérité du même correctif d'ordre que PlasmaCannon (même nœud
  `UnitsDirectlyBehind`) mais n'a pas eu son propre scénario live ; son résidu propre (le natif
  ré-évalue son `PickRandomly` à chaque `Select`, le port n'en fait qu'un) reste ouvert et documenté sur
  place.

---

## 6. Fichiers

| Fichier | Rôle |
|---|---|
| `engine/entities/pathfinding/board.py` | `neighbours_native` (foyer unique de l'ordre brut) |
| `engine/dsl/base.py` | `_tile_enum_rank` (les deux itérateurs) + `_within(board, order)` |
| `engine/entities/selectors/tiles.py` | `AdjacentTiles` lit l'ordre brut |
| `engine/entities/selectors/units.py` | itérateur par sélecteur ; `Tiles(as_ids=)` ; `UnitsDirectlyBehind` en ordre cube |
| `engine/runner/abilities/behaviours/combat.py` | pick en ordre source, `OrderBy` après ; mode `tile_domain` |
| `engine/runner/abilities/loki/splash.py` | Fragstorm en hexes ; verdict forced-targets dans `_pick_randomly_n` |
| `engine/runner/abilities/necrons.py`, `darkangels.py` | pré-tri supprimé |
| `engine/runner/operations/spawn.py` | `_adjacent_tiles` délègue à `neighbours_native` |
| `scripts/python/probe_r28_pick_order.py` | probe (2 modes : BringerOfDespair, PlasmaCannon) |
| `tests/engine/runner/test_pick_order_native_live.py` | garde (2 oracles offline + 2 scénarios live discriminants) |
| `tests/engine/runner/test_fragstorm_migration_live.py` | garde structurelle du pool en hexes |
