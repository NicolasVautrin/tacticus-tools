# Case-37 — Move résiduel 909 s4 : TileEffects LightCover + Elevation whole-board

**Statut : RÉSOLU (porté + validé).** Suite directe de [case-36](case-36-triggered-abilities-move.md) (TrigAb move).
Build `gqfc5mff6c`. Deux gaps pré-existants de la feuille `Tile(7)`, révélés une fois le terme
`TriggeredAbilities(2)` porté : la tuile `(3,2)` restait un miss `move-formula` (u89 tyranTyrantGuard,
seed 909, step 4).

## Symptôme (walk stages 909, après case-36)

```
step 4 u89: pos native->(3, 2) engine->(0, 3)   [move-formula]
  move_terms (AVANT #37) :
    (3, 2): tile=45  mindist=-700  u=-655  pathdist=7
    (0, 3): tile=50  mindist=-700  u=-650  pathdist=7   <- engine choisit (0,3) : -650 > -655
```

Natif : `(3,2)` tile = **59**. Décomposition mesurée (L3 + board) :

| tuile | terrain | elev | Elevation(8) | TileEffects(9) | TrigAb(2) | tile-term | u (=tile−700) |
|---|---|---|---|---|---|---|---|
| (3,2) | DryBush | 2 | 20 (Mult×2, ni min ni max) | **+9 (LightCover)** | +30 | **59** | **−641** |
| (0,3) | Grass | 4 | 50 (Mult×4 + HighestElevation) | 0 | 0 | 50 | −650 |

`−641 > −650` → natif choisit `(3,2)`. Deux termes manquaient offline : **+9 LightCover** et le **−5 indu**.

## Gap 1 — TileEffects(9) : LightCover terrain non alimenté

La feuille `TileEffectsUtility` ne sommait que `meta.effects` = effets DYNAMIQUES du tileMeta
(`EffectsOwnedComponent`, ex. Fire/Ice). Le **LightCover d'une DryBush est un cover STATIQUE de terrain**,
jamais présent dans cette liste.

**RE (`TileEffectsUtility.<EvaluateMovementInSteps>d__1.MoveNext @1810fbe50`, verdict re-expert case-37).**
Deux boucles sur la tuile candidate :
- **Loop1** : composant `DAT_1831b74c8` (List@+0x10) = effets DYNAMIQUES matérialisés sur la tuile
  (`EffectType@+0x58` → `Default.TileEffects.<EffectName>`, ×`StatusEffectMultiplier` si `IsTileStatusEffect`).
- **Loop2** : composant `DAT_1831b9908` (Collection@+0x18) = **abilities HÉBERGÉES par la tuile** (terrain).
  Chaque élément → `Unit.get_Id @180376b00` (= un `AbilityType`) → `AbilityType.ToString` →
  `Default.TileEffects.<AbilityName>` (caché dans un dict@this+0x60).

Le **+9 LightCover vient de Loop2** : `LightCoverAbility @1811c14e0` vit dans le namespace
`Abilities.**Tiles**.Loki.*` = ability de terrain hébergée par la DryBush. (L'`EffectType 1013` /
`LightCoverEffect @180f55950` du namespace `Entities.**Effects**` est appliqué aux UNITÉS sur le cover, PAS
à la tuile — une DryBush vide n'a AUCUN LightCoverEffect en Loop1.) → **une DryBush candidate rend +9 même
sans unité dessus**. Confirmé par L3 : `(3,2)` = exactement **9** (et non 9+15 : DryBush n'héberge que
LightCover pour cette feuille, pas `DryBush_DefenseBonus`).

**Proxy offline** : la seule source de cover statique est le terrain (`tileDefId`, boardGraph). Mapping
validé `DryBush → ("LightCover",)` (`Default.TileEffects.LightCover = 9`). cf.
[terrain-effects.md](terrain-effects.md) §2 (`DryBush <=> LightCover`).

## Gap 2 — Elevation(8) : min/max sur le candidate-set, pas le board

La harness calculait `elevation_min`/`elevation_max` sur les **tuiles candidates** → `(3,2)` (elev 2 = min des
candidats) recevait `LowestElevation = −5` à tort.

**RE (`ElevationUtility$$LoadRelevantTileElevations @1810ef690`, verdict re-expert case-37 — réponse (a)).**
La fonction (one-shot, garde `this+0x68`) énumère un **composant board-singleton sur le World** (`this+0x10`,
getter sans paramètre unité) = **la collection de TOUS les tiles du board** ; chaque élément → `TileComponent`
→ `.Elevation@+0x18` ; met à jour `max@this+0x60` (seed 0) / `min@this+0x64` (seed 10). **Ni l'unité, ni les
reachable, ni le candidate-set.** → min/max = extrêmes d'élévation du **board ENTIER**.

Board 909/MC1_67 : elev ∈ {1:17, 2:20, 3:20, 4:6} → **min=1, max=4**. `(3,2)` elev 2 n'est PAS le min du
board (1 l'est) → **pas de −5**. `(0,3)` elev 4 == max → HighestElevation +10 (déjà appliqué, board max ==
candidate max == 4). *(Note : seed max=0 / min=10 ne change rien tant que le board a des elev dans [1,4] ;
latent pour un board tout-négatif, non rencontré.)*

## Port (offline, 0 reinject — `engine/**`)

- **`engine/utilities/tile.py`** : `TERRAIN_TILE_EFFECTS = {"DryBush": ("LightCover",)}` + helper
  `terrain_tile_effects(terrain)` ; docstrings ElevationUtility (min/max board-entier) + module.
  *(Renommé `TERRAIN_HOSTED_ABILITIES` par `case-155`, qui a rattaché cette table à la boucle native
  dont elle vient — Loop2, les abilities HÉBERGÉES — et lui a adjoint le repli Loop1
  `TERRAIN_TILE_OWNED_EFFECTS` ; le helper prend un 2e argument `dynamic`.)*
- **`engine/ai/context.py`** : `_board_terrain(rpc, rid)` (`{(col,row): tileDefId}` depuis le boardGraph CACHÉ
  — 0 RPC en plus) + champ `terrain_by_pos` de `AiDecisionContext`.
- **`engine/ai/state_bridge.py`** : `_board_topology_maps` rend aussi `terrain_by_pos` (depuis `state.board`,
  path runner-sim) → parité live/offline.
- **`engine/move.py`** (`best_move_faithful`) : nouveau param `terrain_by_pos` ; min/max Elevation sur
  `elev_by_pos` COMPLET (board) ; `meta.effects` = dynamiques (Loop1) + `terrain_tile_effects` (Loop2).
- **`engine/ai/action_generators.py`** : passe `terrain_by_pos=ctx.terrain_by_pos`.
- **`engine_agreement_stages.py`** (`_move_utils`, mirror du walk) : mêmes deux fixes.

Portée : le canal cover-de-terrain de la feuille MOVE `TileEffects(9)` est SÉPARÉ (par construction native)
du chemin DÉGÂT `LightCoverEffect.CreateEffectHitsBonusForAttack @180f556b0` (via `board.terrain_at`, déjà
porté A3/#113). Pas de fork : deux fonctions natives distinctes.

## Validation

- **Offline** (`check37.py`) : `terrain_tile_effects("DryBush")==["LightCover"]` ; `TileEffects` somme +9 ;
  `Elevation (3,2) board[1..4] = 20` (ni High ni Low) vs OLD candidate-min=2 = 15 (−5 indu) ; `(0,3)=50`.
- **Live** (walk stages 909, 20 pas) : **step 4 u89 native→(3,2) engine→(3,2) [EXACT]** (le miss phare
  ferme). Move agreement 12/16 → **13/16** ; catégorie `move-formula` = **0** (était 1). step 19 u89 reste
  EXACT (case-36 préservé). Les 3 misses `move` restants = `pos-downstream-of-ability` (catégorie distincte,
  inchangée) → aucune régression.

## VAs

`TileEffectsUtility.<d__1>.MoveNext @1810fbe50` (Loop2 `DAT_1831b9908` = tile-hosted abilities,
`Unit.get_Id @180376b00` = AbilityType) · `LightCoverAbility @1811c14e0` (Abilities.Tiles.Loki) ·
`ElevationUtility$$LoadRelevantTileElevations @1810ef690` (board-singleton, min@+0x64/max@+0x60) ·
`ElevationUtility.<d__8>.MoveNext @1811019a0` · ctor `@1810efa20` (seed min=10).
