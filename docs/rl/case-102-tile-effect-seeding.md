# case-102 — `load_state` seede les effets de TUILE (déverrouillage de la PHASE 2 tile-driven)

Build `gqfc5mff6c`. Verrou de **HARNAIS**, pas de moteur : `load_state` reconstruisait l'état offline
depuis une capture live **sans les effets portés par les TUILES**. Toute mécanique dont la condition
porte sur une tuile (feu, glace, contaminé, zones posées) repartait donc d'un plateau VIERGE — le port
ne pouvait pas partir du même état que le natif, donc **aucun test ne pouvait trancher**. C'est une
classe entière de validations qui était bloquée, pas une ability.

---

## 1. RE — où vivent les effets de tuile côté natif

**Une tuile est une ENTITÉ qui porte ses effets exactement comme une unité.** Trois lectures du
décompilé le prouvent :

- `IdunBattle.Operations.AddEffectOperation$$Execute(op, source, target, builder, effectType, options)`
  prend une **cible `IEntity` quelconque**. Son unique branchement unité-spécifique (le contrôle
  d'immunité `HasFlag(target, 6)`) est **gardé par `IdunBattle.Entities.EntityExtensions$$IsUnit`** —
  autrement dit le natif prévoit explicitement que la cible n'en soit pas une.
- `IdunBattle.Operations.AddEffectOperation$$AddNewEffect` fait
  `GetComponent<EffectsOwnedComponent>(target) -> List.Add(effectEntityId)` **sans jamais regarder
  l'EntityType** de la cible. Le même composant, la même liste.
- la relecture est symétrique : `IdunBattle.Entities.TileExtensions$$HasTileStatusEffect` parcourt la
  liste possédée de l'entité-tuile, et `IdunBattle.Entities.EntityExtensions$$HasOneOfEffects` opère
  sur une `IEntity` **indifférenciée** (domaine mixte unité|tuile).

**Le canal live existait déjà.** Côté hooks, `readEffectsByUnit` et `readEffectsByTile`
(`frida/hooks/game/effects.ts`) sont deux jumeaux : **même lecture** de
`EffectsOwnedComponent.ActiveEffectIds`, **mêmes champs** (`{name, effectType, remaining, level,
source}` lus sur l'`EffectComponent` de chaque entité-effet), **même filtre de vivacité**
(`!IsActive || Removed` -> drop) ; seul le filtre d'EntityType change. Ils alimentent respectivement
`decisionView.units[].effects` et **`tileMeta.tiles[].effects`**.

> Conclusion de recon : **aucun hook nouveau n'était nécessaire.** Le consommateur était prêt
> (`ctx.tile_has_effect` / `UnitsOnTilesWithEffect` #217), le canal de capture était prêt (`tileMeta`),
> et la face DÉCISION le consommait déjà par pas (`engine/ai/context.py` -> `Scene.tile_effects_by_pos`).
> **Seul le vecteur de seeding du RUNNER manquait.**

---

## 2. Le vecteur

`engine/runner/snapshot.py` :

```python
def load_state(decision, observe, snapshot=None, board=None, tiles=None) -> State:
```

`tiles` = le payload du RPC `tileMeta` (dict complet ou liste brute). Point d'injection **UNIQUE**,
exactement comme `board` l'est depuis `case-64` — et pour la même raison : un état chargé ne doit pas
dépendre d'une hydratation dispersée chez l'appelant.

- **`_load_tile_effects(state, tiles, board)`** — mirror de l'append natif. Pour chaque ligne de
  `tileMeta` : (col,row) -> `board.id_at` -> **id d'entité-tuile**, puis `EffectFactory.create(...)`
  et `EffectsState.add_effect(tile_id, eff)` — l'homonyme port de
  `AddEffectOperation$$AddNewEffect`, **le chemin par lequel passe déjà la POSE en combat** (la glace
  de LordOfTempests vit dans `state.effects.by_unit[tile_id]`, cf. `case-35`). Il n'y a pas deux
  modèles d'effet de tuile : il y en a un seul, désormais alimenté par ses deux bouts.
- **`board` requis** : `tileMeta` ne rend que (col,row) ; l'id d'entité-tuile — celui que
  `state.effects` et `AddEffectOperation` utilisent — ne vient que de `boardGraph`. Pas de board ->
  pas de seed.
- **`tiles=None` par défaut** -> comportement des ~100 appelants existants **strictement inchangé**.
- **Ordre** : après `_load_stats_and_effects` (qui REMPLACE `state.effects` par un
  `EffectsState.seed` frais) et après la pose des `StatsComponent`.

### Pourquoi pas `EffectsState.seed` (la voie des unités)

Ses dictionnaires `mult_by_unit` / `ability_level_by_unit` sont keyés **par porteur** — ce qui n'a pas
de sens pour une tuile : elle n'a aucun `unitConfig`, et elle peut porter des effets de **sources
différentes** (deux feux posés par deux MoW). Le natif, lui, bake l'`AbilityStateReference`
(`EffectComponent.AbilityState`) **par entité-effet, à la création, depuis la SOURCE**. On matérialise
donc effet PAR effet avec l'état de SA source (`_source_ability_state`, qui lit le `StatsComponent.ctx`
de l'unité désignée par `EffectComponent.SourceUnitId` = le champ `source` du capteur). C'est
**strictement plus fidèle** que la clé par porteur — laquelle reste une approximation documentée pour
les unités. Source inconnue/non chargée -> neutre `(100, None, None)`, le défaut de `EffectFactory`.

### Empreinte confrontable

Même idiome que `snapshot`/`snapshot_live`/`diff` :

- `tile_effects_footprint(state)` -> `{tile_id: {effectType: remaining}}` (`remaining` None -> 0,
  comme le capteur live rend 0 quand `HasTurns` est faux) ;
- `tile_effects_footprint_live(tiles, board)` -> **la même**, calculée directement depuis `tileMeta`
  (chemin INDÉPENDANT du loader) ;
- `snapshot(state)["tiles"]` / `snapshot_live(dec, obs, tiles=, board=)["tiles"]`, comparés par `diff`
  **uniquement quand les deux côtés fournissent le canal** — les appelants historiques
  `diff(snapshot_live(dec, ob), snapshot(st))` gardent exactement leur sémantique.

---

## 3. Le contre-effet, et son correctif : `IsTileStatusEffect`

Rendre le seed FIDÈLE fait entrer dans l'état offline **la vraie liste native**, qui contient des
effets de tuile **qui ne sont PAS des « status »**. Mesure live (`C1_02`, à la construction) :

| tuile | effets portés |
|---|---|
| Swamp | `BlockEnteringUnits` (0) + `Thorns_DefenseReduction` (0xb) |
| autre | `Melta_ExtraDmg` (0x511) |
| après cast `DaemonicOrdnance` | `Fire` (5) |

Or `IdunBattle.Entities.TileExtensions$$HasTileStatusEffect` **filtre** : il ne retient que les
EffectType du set de
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$IsTileStatusEffect`
(= `OrderedSet.Contains(<champ statique +0x28>, effectType)`). Le set est bâti par
`StaticBattleRules.Effect$$.cctor` et contient **EXACTEMENT 5 membres**, lus 1:1 dans l'ordre des
`OrderedSet.Add` du décompilé :

```
0x3a Darkness · 0x05 Fire · 0x11 Ice · 0x4dc Contaminated · 0x5c4 DespoiledGround
```

**Sans ce filtre, le seed sur-appliquerait** le +1 coup de
`IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits` — gaté par
`LetTheGalaxyBurnAbility$$TargetHasTileEffect` -> `HasTileStatusEffectTrigger$$ShouldTrigger` ->
`HasTileStatusEffect` — **sur tout board portant du Swamp**. Le trou était **invisible** avant #102 :
la liste offline ne contenait que ce que le runner avait posé lui-même (Fire/Ice, tous des status).

Port : `engine/services/static_battle_rules.py` (`is_tile_status_effect`,
`TILE_STATUS_EFFECT_TYPES`, `TILE_STATUS_EFFECT_NAMES`). Implanté **là** et non à côté de
`default_amount_of_rounds` (l'autre membre porté de `StaticBattleRules.Effect`, dans
`runner/operations/effects.py`) parce que le prédicat est consommé par `engine/entities/**` ET par
`engine/runner/**`, et que `entities/` n'importe jamais `runner/`. Appliqué aux deux faces :

- COMBAT — `damage_model.tile_status_effects_by_pos` filtre par `effect_type` ;
- PRÉDICTION — `entities/effects/loki/hits.py` (gate `TargetHasTileEffect`) intersecte les NOMS avec
  `TILE_STATUS_EFFECT_NAMES` (le canal `Scene.tile_effects_by_pos` ne transporte que des noms). Cette
  face était **déjà** non filtrée avant #102 (elle lit `tileMeta` brut) : le correctif la répare aussi.

---

## 4. Validation (live, session saine — le crash de session a été rejoué intégralement après)

### 4.1 Empreinte (`test_load_state_seeds_tile_effects_live`, `probe_102_tile_effect_seed.py` volet A)

Runner `C1_02` / seed 4242 / MoW `blackForgefiend`, après un cast `DaemonicOrdnance` :

```
offline = {12:{1297:0}, 17:{0:0,11:0}, 20:{5:2}, 21:{5:2}, 24:{0:0,11:0}, 27:{5:2}, 37:{0:0,11:0}}
live    = {12:{1297:0}, 17:{0:0,11:0}, 20:{5:2}, 21:{5:2}, 24:{0:0,11:0}, 27:{5:2}, 37:{0:0,11:0}}
TEMOIN (load_state SANS `tiles`) = {}
```

7 tuiles, 4 EffectType distincts, durées incluses : **identiques**. Le `diff` canonique est muet.
Le témoin — l'ancien comportement — rend un plateau vide : **c'est le vecteur qui porte le résultat**.

### 4.2 Consommateur réel (`test_tile_effect_seed_drives_daemonic_ordnance_targeting_live`, volet B)

`DaemonicOrdnanceAbility$$GetAllDamageableTargets` =
`Enemies(Units(Filter(zone, HasEffect(Tiles(Subject), 5=Fire))))` — l'attaque ne frappe QUE les
ennemis déjà debout sur une tuile en feu (2-phases par construction). On allume, on **déplace** un
ennemi sur le feu (doctrine drive-positions), on passe le tour (l'activation de la MoW est consommée),
puis on rejoue le cast des deux côtés :

```
blessés offline = {49}     live = {49}     TEMOIN (sans seed) = {}
```

Sans le seed, le filtre de zone rend un ensemble **vide** et l'ability ne frappe personne : le
discriminant est binaire, pas marginal.

### 4.3 Contre-effet (`test_non_status_tile_effect_does_not_arm_ltgb_live`, volet C)

Angrax (`blackTerminator`, trait LetTheGalaxyBurn) attaque une cible **posée sur des tuiles à effets
NON-status**. La branche B du gate natif est DÉTERMINISTE (+1 systématique) ; la branche A est un roll
`Maybe(LetTheGalaxyBurnChancePct=33)`. 14 échantillons :

```
(BlockEnteringUnits, Thorns_DefenseReduction) -> 5,4,5,4,5   |   (Melta_ExtraDmg) -> 5,4,5,5,4,4,4,4
base = 4 observé 6 fois sur 14
```

Le natif rend `base` sur ces tuiles : **il ne les compte pas comme status** -> le filtre est confirmé
LIVE (et non seulement au décompilé). P(faux négatif) = 0.33^6 = 0.13 %.

### 4.4 Consommateurs migrés (le hack de contournement disparaît)

Trois harnais re-posaient la glace **à la main** parce que `load_state` ne l'hydratait pas. Ils
consomment désormais le vecteur, et leurs assertions historiques tiennent :

| harnais | consommateur natif exercé | résultat |
|---|---|---|
| `test_lord_of_tempests_ice_live.py` (3 tests) | `LordOfTempests_ExtraDamageEffect$$GetHexesIncreasingDamage` (snowball = +extraDmg × Count(Ice ring-1)) | **bit-exact** vs live |
| `test_anvil_shield_stun_live.py` (3 tests) | `AnvilShieldAbility_FrozenAttackerAdvantage$$CreateTrigger` (`IsUnitOnTileWithEffect(caster, Ice)`) | la précondition vient du LOAD ; Stun/1201/block reproduits |
| `probe_217_stormcaller.py` (2 scénarios) | `UnitsOnTilesWithEffect(Enemies, Ice)` + snowball | glaces pré-existantes seedées ; dégâts **1671/1670 bit-exacts** |

Dans `test_anvil_shield_stun_live`, la re-pose manuelle est remplacée par une **assertion** : si le
load n'hydratait pas la tuile, le test tomberait au lieu de se maquiller.

### 4.5 Gardes rejouées (aucune régression)

`test_let_the_galaxy_burn_live.py` (3), `test_runner_state_live.py` + `test_mow_caster_load_live.py`
(9, la forme canonique `snapshot`/`diff`), `test_mow_groups_bcd_live.py` (6 + 1 skip pré-existant sans
rapport), `test_runner_move_live.py` (2 + 1 xfail), `test_lightcover_gate_live.py` +
`test_runner_attack_live.py` (3).

---

## 5. Ce qui n'est PAS couvert

1. **`tiles` reste opt-in.** `load_state` ne fait pas de RPC (et ne doit pas en faire) : chaque
   appelant qui veut les effets de tuile passe `tiles=tileMeta`, exactement comme il passe `board`.
   Les ~100 probes/tests historiques restent au comportement d'avant tant qu'ils ne le passent pas —
   **c'est voulu** (zéro changement silencieux), mais cela veut dire qu'un harnais tile-driven écrit
   plus tard peut encore oublier le canal. Un test tile-driven doit vérifier son empreinte de seed.
2. **`tileMeta` ne rend pas l'id de tuile** : la jointure passe par `board.id_at(col,row)`. Ajouter
   `id` à la projection de `tileMeta` (`frida/hooks/features/ai-step/rpc-board.ts`) supprimerait la
   dépendance au board — non fait ici (changement de hook = reinject, hors périmètre).
3. **Évolution des durées.** `EffectsState.on_turn_end(unit_id)` est appelé PAR UNITÉ : les timers des
   effets **portés par les tuiles** ne sont pas décrémentés par le runner. Le seed les charge avec le
   `remaining` live exact (donc un état rechargé est juste), mais une simulation multi-tours offline
   ne fera pas expirer un feu de tuile. C'est le pendant, côté durée, du gap de transition tuile
   documenté dans `terrain-effects.md` §0 (B1) — non traité ici (sujet : le vecteur de seeding).
4. **`BlockEnteringUnits` (0) est désormais VISIBLE offline** sur les boards qui en portent (mesuré :
   `C1_02`). `terrain-effects.md` §2 affirmait le gate pathfinding bit-0x1 « INERTE car aucun board
   courant ne le porte » : c'est **faux**, et corrigé là-bas. Le pathfinder ne lit toujours pas cet
   effet (#131 reste déféré) — mais l'argument « inatteignable » ne tient plus.
5. **Multi-source / `AbilityState` par effet** : `_source_ability_state` lit le `StatsComponent` de la
   source. Si la source n'est pas dans l'état chargé (unité morte retirée de la capture, effet
   d'environnement), on retombe sur le neutre `(100, None, None)`. Aujourd'hui inerte (aucun
   consommateur d'effet de tuile ne lit son multiplicateur), mais à re-examiner le jour où une
   magnitude d'effet de tuile en dépendra.
6. **`IsTileStatusEffect` sur un autre build** : le set est lu au `cctor` de `gqfc5mff6c`. Il fait
   partie des constantes à revalider à chaque changement de hash (comme `_DEFAULT_ROUNDS`).

---

## 6. Fichiers

- `scripts/python/engine/runner/snapshot.py` — `tiles=`, `_tile_rows`, `_source_ability_state`,
  `_load_tile_effects`, `tile_effects_footprint(_live)`, `"tiles"` dans `snapshot`/`snapshot_live`/`diff`.
- `scripts/python/engine/services/static_battle_rules.py` — `is_tile_status_effect` +
  `TILE_STATUS_EFFECT_TYPES` / `_NAMES`.
- `scripts/python/engine/runner/damage_model.py` — filtre dans `tile_status_effects_by_pos`.
- `scripts/python/engine/entities/effects/loki/hits.py` — filtre du gate `TargetHasTileEffect`.
- `scripts/python/engine/runner/operations/effects.py` — renvoi vers le foyer du prédicat.
- `scripts/python/probe_102_tile_effect_seed.py` — probe versionné (volets A + B + témoin).
- `scripts/python/tests/engine/runner/test_load_state_tile_effects_live.py` — 3 tests (A/B/C).
- Migrés : `test_lord_of_tempests_ice_live.py`, `test_anvil_shield_stun_live.py`,
  `probe_217_stormcaller.py`, `test_let_the_galaxy_burn_live.py` (stub `effect_type=5` + garde
  non-status).
