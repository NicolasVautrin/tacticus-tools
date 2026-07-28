# Case R1-b — l'ORDRE des tuiles de move dans le sweep de position

**Verdict : la question est TRANCHÉE, et le diagnostic hérité était FAUX.** L'`OrderedSet` porte
l'ordre d'**INSERTION** du pathfinder — `[origine] + aiMovableTiles`, à l'identique. Ce n'est pas un
tri, et ce n'est pas l'ordre `ranked`. Ce qui faisait « régresser » son imposition n'est **pas**
l'ordre : ce sont des **ties ARTEFACTS DU PORT**, que le natif sépare strictement (mesuré : Δ 5.0 et
Δ 59.0 en utilité d'action sur les deux seuls chunks discriminants de 10 couples).

---

## 1. Les trois affirmations héritées, re-confrontées

Entrée **R1-b** de `port-residuals-inventory.md` §4.a, telle qu'elle était rédigée :

> Symptôme : tie 192.851 entre deux tuiles de move (`C4_09`/seed 999, pas 14) : le natif prend
> `(4,4)` = 1re **rankée** ; imposer l'ordre `aiMovableTiles` fait **RÉGRESSER** pos 15/20 → 14/20.
> Symboles : `IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFromTiles` (slot 4
> d'`IMovementQuery`) + l'`ExceptWith` de `IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFor`.

| # | Affirmation | Verdict | Mesure |
|---|---|---|---|
| (a) | le tie 192.851 existe (`C4_09`/999 pas 14, deux tuiles de move) | **VRAI côté PORT, FAUX côté NATIF** | port : `(4,4)` et `(6,4)` à **192.8506** exact. Natif : `(4,4)` = **207.8506**, `(6,4)` = **202.8506** — Δ **5.0**, pas un tie |
| (b) | imposer l'ordre `aiMovableTiles` fait régresser pos 15/20 → 14/20 | **VRAI, et reproduit** | `probe_r1_agreement_matrix` : `C4_09`/999 pos exact **15/20 → 14/20**, `<=1hex` 17/20 → 16/20. Les 3 autres couples de `case-r1` : **inchangés** |
| (c) | les deux symboles sont les bons maillons | **PARTIELLEMENT** | `GetMovablePositionsFromTiles` : **OUI**, c'est bien lui qui décide l'ordre. « l'`ExceptWith` de `GetMovablePositionsFor` » : **NON — c'est un `UnionWith`** (§2.2) |

⇒ (a) est l'erreur de fond : le dossier hérité prenait une égalité **du port** pour une égalité **du
jeu**, et en déduisait que seul l'ordre pouvait trancher. L'ordre n'avait rien à trancher.

---

## 2. L'ordre natif, établi au décompilé

### 2.1 La chaîne, du tactic à la tuile

```
IdunBattle.AI.Tactics.DefaultAiUnitTactic.<CalculateNextActionForUnit>d__5$$MoveNext
    tiles = ABaseAiUnitTactic$$GenerateActionTiles(unit, false, 0)
    foreach (gen in generators) gen.GenerateActions(unit, position, tiles)   // 1re non-nulle
```

`IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles` :

```csharp
var tiles = battleQuery.slot_0xe(unit, false, 0);                  // GetCurrentAndMovablePositionsFor
foreach (var active in ActiveAbilityComponent(unit).Actives)       // hook playbook, RESTREINT seulement
    PlaybookDatabase.LoadPlaybook(active.Ability.Id)?.slot1(unit, ref tiles);
return tiles;                                                      // AUCUN tri
```

`IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor` :

```csharp
var set = new OrderedSet<UnitPosition>( EntityExtensions.GetUnitPosition(unit) );   // COURANTE, en TÊTE
set.UnionWith( movementQuery.GetMovablePositionsFor(unit, flag, default) );
return set;
```

`IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFor` :

```csharp
if (UnitExtensions.HasTrait(unit, 0x418)) return new OrderedSet<UnitPosition>();   // vide
var feet  = UnitExtensions.GetFeetCount(unit);
var tiles = GetMovableTilesFor(unit, flag, options);          // OrderedSet<Tile>
tiles.UnionWith( EntityExtensions.IterateTiles(unit) );        // <-- UnionWith, PAS ExceptWith (§2.2)
return GetMovablePositionsFromTiles(tiles, feet);
```

`IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFromTiles` :

```csharp
if (tiles.Count == 0)  return new OrderedSet<UnitPosition>();
if (feetCount == 1)    return UnitPositionExtensions.ToUnitPositionList(tiles);   // <-- le cas nominal
/* feetCount > 1 */    ... GetPossibleTileListsFromMovableTiles + IsValidUnitFeetList ...
```

`IdunBattle.Core.UnitPositionExtensions$$ToUnitPositionList` boucle `for i in 0 .. Count-1` sur la
**liste** de l'`OrderedSet` et `Add` chaque position ⇒ **ordre PRÉSERVÉ**.

Et le contenu de `tiles` vient de `IdunBattle.Core.Services.MovementQuery$$GetMovableTilesFor`, qui
alloue l'`OrderedSet` puis le passe en sortie à `…$$FindAnyOrAllMoveableTiles` →
`…$$AnyOrFillMoveableTiles`, lequel fait, pour chaque pied de l'unité,
`allTiles.AddRange( GetReachableTiles(…) )` puis (bonus de portée) `AddRange(extra)`, et enfin
`result.UnionWith(allTiles)` ⇒ **ordre d'expansion du pathfinder, purement d'insertion**.

### 2.2 Pourquoi `UnionWith` et pas `ExceptWith`

Les deux call-sites passent par le même method-info `gshared` (`FUN_180003bd0(0, DAT_18321f710, a, b)`) :
l'un est `tiles.??(IterateTiles(unit))` dans `GetMovablePositionsFor`, l'autre est
`param_8.??(allTiles)` en fin d'`AnyOrFillMoveableTiles`, **où `param_8` est l'`OrderedSet` VIDE que
`GetMovableTilesFor` vient d'allouer et va retourner**. Un `ExceptWith` y rendrait toujours
l'ensemble vide — or `aiMovableTiles` rend des tuiles. C'est donc **`UnionWith`**.

Conséquence : `GetMovablePositionsFor` **AJOUTE** les tuiles propres de l'unité *à la fin*, il ne les
retire pas. Sans effet sur l'ordre observé : `GetCurrentAndMovablePositionsFor` a déjà mis la
position courante en **tête** de son `OrderedSet`, et le doublon est absorbé.

### 2.3 Ce que l'`OrderedSet` garantit

`idun.shared.collections.OrderedSet<T>` **EST une `List<T>`** (l'objet lui-même est passé à
`List<T>.Add`) doublée d'un `HashSet<T>` à `+0x28` :

- `$$Add` : `hashSet.Add(item)` puis, si nouveau, `List.Add(item)` → **ordre d'insertion** ;
- `$$UnionWith` → `$$SyncListWithSet` : `RemoveExtraEntriesFromList()` puis, pour chaque item de la
  source, `if (set.Contains(x) && !List.Contains(x)) List.Add(x)` → **append dans l'ordre de la source** ;
- `$$RemoveExtraEntriesFromList` : boucle **à rebours** avec `List.RemoveAt(i)` → **ordre des
  survivants préservé**.

C'est aussi pourquoi le RPC `aiMovableTiles` expose exactement cet ordre : `extractTiles` lit la
`List<T>` interne (`items@0x10`, `size@0x18`) de l'`OrderedSet` rendu par le **même**
`GetMovableTilesFor`.

**⇒ ordre natif = `[origine] + aiMovableTiles`, à l'identique.**

### 2.4 Les trois boucles imbriquées, et le keep-first

```
ActiveAbilityActionGenerator.<GenerateActions>d__7$$MoveNext
    foreach ability in ActiveAbilityActionGenerator$$GetUnitAbilitiesInOrder     <- MAJEURE
        foreach position in tiles                                                <- MÉDIANE
            Bucket$$Merge(bucket, playbook.Evaluate(unit, position, ctx))
        if (tiles.Count == 0)  ...  NullPosition ...                             <- seulement si VIDE
ComparablePlaybook<T>$$EvaluateInternal
        foreach target in BasePlaybook$$GetEligibleTargetsEntities               <- MINEURE
            if (utility > best) best = GenerateAction(position, target, utility)     // `>` STRICT
Bucket<T>$$AddAction
    if (bucket.Action == null) bucket.Action = a; else if (a.Utility > bucket.Action.Utility) …
```

`AddAction` seede le premier et ne remplace que sur `>` **STRICT** : **keep-first à chaque étage**.
La POSITION domine la CIBLE — pas l'inverse.

### 2.5 `ranked` n'est l'ordre de RIEN dans le générateur d'action

`ranked` (les `attackPlans` du hook) est produit par un shrink-and-recall de
`IdunBattle.Core.Services.AttackQuery$$GetBestTileToAttackFrom`, qui parcourt l'ensemble et garde
l'argmax STRICT d'une **utilité de MOUVEMENT** (`IdunBattle.AI.Utilities.UtilityMovementCase` passé
au slot 8 du calculateur d'`AttackQuery+0x28`). Cette utilité n'entre dans **aucune** boucle du
générateur d'action. Le port la consommait comme ordre de sweep : c'était un proxy, pas un mirror.

---

## 3. Confirmation LIVE de l'ordre — le natif lui-même

`probe_r1b_native_sweep_order.py` arme les hooks existants de `scorer-damage-trace` (RVA
`gqfc5mff6c`) le temps d'**un seul** `aiStepDryRun`, puis les désarme. La **séquence** des tuiles
caster vues par `ComparablePlaybook<T>$$CalculateActionUtility` EST l'ordre d'énumération natif.

| couple / pas | ordre NATIF observé | `== action_tiles` | `== ranked` |
|---|---|---|---|
| `C4_09`/999 pas 14 (`templAncient`) | `(5,5) (5,6) (6,4) (4,4) (4,3) (3,5) (3,6) (5,3) (3,3) (2,4) (2,6)` | **OUI** | non |
| `C4_09`/31337 pas 22 (`admecMarshall`) | `(4,5) (5,6) (5,5) (3,6) (5,4) (4,3) (2,5) (2,4) (1,5) (1,6)` | **OUI** | non |

Deux couples indépendants, 21 tuiles, **zéro écart**. La RE du §2 est confirmée par observation
directe.

---

## 4. Le vrai coupable : le TERME DE TUILE, pas l'ordre

Le même dump donne l'utilité d'action native par candidat et son terme de tuile
(`ComparablePlaybook<T>$$CalculateUtilityFromTilePrediction`, le composite `Tile(7)` complet).

### `C4_09`/999 pas 14 — le « tie 192.851 » du dossier

| tuile | élév. | natif `Tile(7)` | natif u(action) | port `Tile(7)` | port u(action) |
|---|---|---|---|---|---|
| **(4,4)** | 3 | **45** | **207.8506** | 30 | 192.8506 |
| (6,4) | 3 | 40 | 202.8506 | 30 | 192.8506 |
| (5,5) origine | 2 | 35 | 197.8506 | 20 | 182.8506 |
| (5,3) | 2 | 35 | 197.8506 | 20 | 182.8506 |
| (4,3) | 2 | 10 | 172.8506 | −5 | 157.8506 |

La part **dégât + custom** du port est **EXACTE** : natif `207.8506 − 45 = 162.8506` = port
`161.8506 + 1` (le `+1` de `ALoki_NormalAttackPlaybook<T>$$CalculateCustomUtility`). **Tout l'écart
est dans le terme de tuile**, et il n'est PAS constant : `+15` partout sauf `(6,4)` à `+10` — donc
il SÉPARE les deux tuiles que le port égalise.

### `C4_09`/31337 pas 22 — encore plus net

| tuile | élév. | natif `Tile(7)` | natif u(action) | port u(action) |
|---|---|---|---|---|
| **(2,4)** | 3 | **45** | **127.7786** | 58.7948 |
| (3,6) | 3 | 40 | 68.7949 | 58.7948 |
| (2,5) | 3 | 35 | 63.7948 | 58.7948 |

Le port égalise **trois** tuiles à `58.7948` ; le natif les sépare de **59 points** entre la première
et la deuxième. Ici l'écart dépasse même le terme de tuile (45 − 40 = 5) : la **prédiction de dégât
par position** diverge aussi.

Décomposition du terme natif (feuilles hookées) : `Tile(7) = Elevation + TileEffects + X`, avec
`Elevation` et `TileEffects` **exacts côté port** (elev 3 → 30, elev 2 → 20 ; `TileEffects` −25 sur
Swamp, +9 sur DryBush, tous reproduits) et `X ∈ [0 .. 25]` **manquant, position-dépendant**. Les
29 enfants du composite sont listés par `scorerComposedDump` ; côté port, `TILE_LEAVES` en range
plus de la moitié en « portées fidèle, DORMANTES (gate sur metadata non plombée → 0) » —
`UnitEffectsAdjacent(10)`, `UnitEffectsSurrounding(11)`, `UnitEffectsRanged(12)`,
`RangedAdjacentEnemy(15)`, `SteppableUnit(19)`, `TriggeredAbilitiesNonOwner(4)`,
`UnitSpecificBehaviours(3)`… C'est **là** qu'est le résidu, et il est désormais chiffré.

---

## 5. Ce qui a été porté

`engine/ai/action_generators.py` — `ComparableAbilityGenerator` :

1. **`_sweep_tiles(ctx, rk_tiles_union)`** (neuf) — mirror nommé de la liste `tiles` : rend
   `ctx.action_tiles` **à l'identique** (origine en tête, puis l'ordre de `GetMovableTilesFor`), plus
   en queue les `ranked` qui en seraient absentes (filet ; l'ensemble est le même par construction).
   Sa docstring porte toute la chaîne du §2.
2. **`_action_utility(ctx, pb, ab, tgt, tile)`** (extrait, refactor pur) — un tour de la boucle CIBLE
   d'`EvaluateInternal` : `u_full + CalculateCustomUtility` (+ le terme lifesteal SpiritLeech #84).
3. **`_best_attack` re-imbriqué en MIRROR** : `ability` (majeure, ordre de `plan["evals"]` = ordre
   ability-major de `computeAttackPlans` = `GetUnitAbilitiesInOrder`) → **`tile`** (médiane,
   `_sweep_tiles`) → `target` (mineure, triée par `bq.iterate_surrounding_tiles_order_key` = ordre
   d'énumération de `GetEligibleTargetsEntities`, #57g). Keep-first `>` STRICT aux trois étages.
   L'ancien tie-break #57g explicite (« même ability + même tuile → cible de plus petit rang cube »)
   devient **structurel** : le tri des cibles + keep-first le produisent.

### Ce que ça change, et pour qui

Le port **forkait** : la voie OFFLINE (`state_bridge._plans_for_unit`) construit déjà `ranked` dans
l'ordre `cand_tiles = [origine] + move_tiles`, donc l'ancien `_best_attack` y balayait **déjà**
l'ordre natif ; seule la voie LIVE (`decisionView.attackPlans`, ordre `GetBestTileToAttackFrom`) en
sortait. **Un natif, deux ordres.** Le moteur qui joue réellement (self-play, RL) est la voie
offline : ce commit aligne la voie LIVE sur elle et sur le natif — il ne dégrade pas le produit, il
rend la mesure honnête.

---

## 6. Mesure AVANT / APRÈS

### 6.1 Les 4 couples de `case-r1` (`probe_r1_agreement_matrix.py`, harnais complet)

| board / seed | pos exact | pos <=1hex | ability | stay |
|---|---|---|---|---|
| `MC1_67` / 777 | 20/20 → 20/20 | 20/20 → 20/20 | 20/20 → 20/20 | 4/4 → 4/4 |
| `C3_01` / 31337 | 17/18 → 17/18 | 18/18 → 18/18 | 11/14 → 11/14 | 2/2 → 2/2 |
| `C4_09` / 999 | 15/20 → **14/20** | 17/20 → **16/20** | 14/20 → 14/20 | 4/5 → 4/5 |
| `MC1_67` / 2468 | 17/19 → 17/19 | 18/19 → 18/19 | 14/15 → 14/15 | 3/3 → 3/3 |

`ability` et `stay` : **strictement inchangés**. `pos` : **−1**, sur le seul chunk `C4_09`/999 pas 14.

### 6.2 Le sweep ISOLÉ, 13 couples (`probe_r1b_move_tile_order.py`)

Trois structures comparées à la décision native sur (ability, cible, tuile), même ensemble candidat,
même utilité par candidat : `pair_rank` (le port d'AVANT) / `pair_action` (pair-major + ordre natif)
/ `ab_tile_tgt` (le MIRROR livré).

| couple | pair_rank | pair_action | ab_tile_tgt | divergences entre les 3 |
|---|---|---|---|---|
| `MC1_67`/777 | 14/20 | 14/20 | 14/20 | 0 |
| `MC1_67`/2468 | 9/15 | 9/15 | 9/15 | 0 |
| `MC1_67`/999 | 13/17 | 13/17 | 13/17 | 0 |
| `C3_01`/31337 | 9/14 | 9/14 | 9/14 | 0 |
| `C3_01`/999 | 11/20 | 11/20 | 11/20 | 0 |
| `C4_09`/999 | **11/20** | 10/20 | 10/20 | **1** (pas 14) |
| `C4_09`/4242 | 7/16 | 7/16 | 7/16 | 0 |
| `C4_09`/1234 | 14/19 | 14/19 | 14/19 | 0 |
| `C4_09`/31337 | **10/16** | 9/16 | 9/16 | **1** (pas 22) |
| `C4_09`/777 | 14/20 | 14/20 | 14/20 | 0 |
| `C4_02`/4242 | 9/17 | 9/17 | 9/17 | 0 |
| `C4_02`/999 | 12/19 | 12/19 | 12/19 | 0 |
| `MC1_44`/555 | 7/9 | 7/9 | 7/9 | 0 |
| **total** | **140/222** | **138/222** | **138/222** | **2** |

**−2 chunks sur 222**, et les **deux** sont les chunks dont le §4 prouve qu'ils ne sont **pas** des
ties natifs (Δ natif = 5.0 et 59.0). `pair_action` et `ab_tile_tgt` ne divergent **jamais** : le
ré-imbriquement des boucles est neutre sur ces 13 couples, seul l'ORDRE des tuiles agit.

Le montage est bien DISCRIMINANT : sur les 13 couples, l'ordre `ranked` diffère de l'ordre
`action_tiles` sur **5 à 16 pas par couple**, et **50 pas portent un tie** (≥ 2 tuiles à l'utilité
max) — l'ordre avait donc toutes ses chances de peser, il n'a pesé que 2 fois.

⚠ **C'est une régression de métrique assumée.** Le proxy `ranked` gagnait ces 2 chunks par
coïncidence — `GetBestTileToAttackFrom` classe par une utilité de mouvement qui, elle, est
position-résolue, là où le port ne l'est pas. Sur `C4_09`/4242 pas 15 (même board, mêmes tuiles
`(6,4)`/`(4,4)`, ability 1014) le proxy se trompe **aussi** : il n'a rien d'un mécanisme.

---

## 7. Gardes

`tests/engine/test_move_tile_sweep_order_live.py` (+ montage `tests/engine/_move_tile_sweep_order.py`),
3 tests × 2 montages :

- `test_sweep_tiles_is_the_native_action_tiles_order` — `_sweep_tiles` rend `action_tiles` à
  l'identique, origine en tête, sans queue parasite ;
- `test_tie_is_won_by_the_earliest_action_tile` — à utilité égale, la tuile la plus tôt dans
  `action_tiles` gagne (keep-first) ;
- `test_tie_tiles_are_not_in_action_tiles_order_under_ranked` — n'assertit que sur un montage où les
  deux ordres **divergent** ; SKIP explicite sinon (un montage non discriminant ne doit pas passer
  pour une preuve).

**Vues ROUGES** par mutation adversariale (re-imposition de l'ordre `ranked` dans `_sweep_tiles`) :
**5 failed / 1 skipped**. Messages VERBATIM :

```
AssertionError: sweep de position REORDONNE : attendu action_tiles=[(5, 4), (5, 5), (6, 4), (6, 3),
(5, 3), (4, 3), (4, 4), (5, 2), (4, 2), (3, 4), (3, 5), (5, 1), (4, 1), (3, 2), (3, 3), (2, 4)],
obtenu [(5, 4), (6, 4), (4, 4), (5, 5), (3, 4), (3, 5), (2, 4)]
```

```
AssertionError: tie sur [(6, 4), (4, 4)] a u=140.7557 : le sweep doit retenir la 1re tuile
d'action_tiles ((6, 4)), il a retenu (4, 4). action_tiles=[(5, 4), (5, 5), (6, 4), (6, 3), (5, 3),
(4, 3), (4, 4), (5, 2), (4, 2), (3, 4), (3, 5), (5, 1), (4, 1), (3, 2), (3, 3), (2, 4)]
ranked=[(6, 4), (4, 4), (5, 4), (5, 5), (3, 4), (3, 5), (2, 4)]
```

Sans mutation : **5 passed, 1 skipped** (le skip = `C4_09`/4242 pas 15, montage non discriminant,
dit tel quel).

Non-régression re-jouée : `test_playbook_live.py` + `test_stay_in_place_live.py` +
`test_move_tile_sweep_order_live.py` → **10 passed, 1 skipped**.

---

## 8. Ce qui n'est PAS couvert

- **Le terme de tuile `Tile(7)` — résidu NEUF `N13`** (`port-residuals-inventory.md` §4.a, chiffré
  au §4 ci-dessus) — c'est le vrai gisement révélé ici,
  et il est plus gros que R1-b : `X ∈ [0..25]` manquant PAR TUILE, plus une **prédiction de dégât
  par position** qui diverge (`C4_09`/31337 pas 22 : Δ 59). Point d'ancrage :
  `ComparablePlaybook<T>$$CalculateUtilityFromTilePrediction` (déjà hooké,
  `scorerTileTermTraceDump`) et les 29 enfants listés par `scorerComposedDump`.
- **`feetCount > 1`** — `GetMovablePositionsFromTiles` passe alors par
  `…$$GetPossibleTileListsFromMovableTiles` + `…$$IsValidUnitFeetList`, dont l'ordre n'est PAS celui
  de `GetMovableTilesFor` et dont les éléments sont des positions MULTI-TUILES. Le port modélise une
  position par un `(col,row)` : hors périmètre, non exercé par les 10 couples (tous mono-tuile).
- **Le trait `0x418`** (`GetMovablePositionsFor` rend un ensemble VIDE) — lu au décompilé, non porté
  ni exercé.
- **`FilterMovementTiles`** (slot 1 du playbook, hook de `GenerateActionTiles`) — seul corps existant
  `TriggeredAbilityPlaybook<T>$$FilterMovementTilesForMaxMovement` (RunsAround / RunsAway /
  SaviorProtocols) ; il RESTREINT, il ne réordonne ni n'ajoute. Non porté, comme avant ce cas.
- **L'ordre des ABILITIES** (boucle majeure) est pris de `plan["evals"]`, pas lu de
  `GetUnitAbilitiesInOrder` — dont `…$$ShouldRandomizeOrder` + `ListExtensions$$Shuffle` peuvent
  RANDOMISER l'ordre pour certains acteurs. Non exercé ici (aucune divergence inter-ability sur les
  10 couples), mais c'est une hypothèse non levée.

---

## 9. Reproduire

```
cd scripts/python
python probe_r1b_native_sweep_order.py --seed 999   --board C4_09 --step 14   # ordre NATIF + utilites
python probe_r1b_native_sweep_order.py --seed 31337 --board C4_09 --step 22
python probe_r1b_move_tile_order.py    --seed 999   --board C4_09 --steps 26  # 3 structures + ties
python probe_r1_agreement_matrix.py --couples MC1_67:777:24 C3_01:31337:26 C4_09:999:26 MC1_67:2468:24
python -m pytest tests/engine/test_move_tile_sweep_order_live.py tests/engine/test_playbook_live.py \
                 tests/engine/test_stay_in_place_live.py
```

⚠ `probe_r1b_native_sweep_order.py` arme des hooks **RVA build-spécifiques** (`gqfc5mff6c`) : il
vérifie le hash avant, arme pour UN `aiStepDryRun`, et désarme (`scorerDamageTraceOff`) en `finally`.
