# case-155 — le `-25 Swamp` revient à UN foyer (fork de port fermé) ; `MaybeTrigger` : périmé

Build `gqfc5mff6c`. Résidu nommé de #146, deux items. Le second était **périmé** ; le premier était un
**fork de port** — un concept natif, deux implémentations offline — dont la RE montre qu'il reposait en
plus sur une **erreur de nature** : les deux tables ne miroitaient pas la même boucle native.

---

## 1. RE — `TileEffectsUtility` a DEUX boucles, deux sources, deux espaces de noms

`IdunBattle.AI.Utilities.TileEffectsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext`, lu
verbatim, fait sur la tuile candidate (`UnitPosition$$get_MainTile`) deux passes distinctes :

| | source | nom du poids | multiplicateur |
|---|---|---|---|
| **Loop1** | `GetComponent<EffectsOwnedComponent>(mainTile)` → par effet possédé, `EffectComponent+0x58` | `((EffectType)+0x58).ToString()` → `Default.TileEffects.<EffectType>` | × `TileEffectsUtility$$GetStatusEffectMultiplier` **seulement si** `StaticBattleRules.Effect$$IsTileStatusEffect` |
| **Loop2** | collection d'abilities **hébergées** par la tuile → `Unit.get_Id(ability)` | `ActiveAbilityType.ToString()` → `Default.TileEffects.<AbilityName>` | aucun |

Les deux passes sont gardées par `BaseUtility$$HasUtilityValue(name)` : **un nom sans poids BC ne
contribue rien**.

### Qui produit quoi

- **DryBush → `+9 LightCover` = Loop2.**
  `IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility$$CreateBehaviour` =
  `AddEffect(0x3f5, abilityStateRef, UnitsThatNeedEffect())` — l'effet est posé sur les **UNITÉS**,
  jamais sur la tuile. La tuile ne porte donc **aucun** effet `LightCover` : le +9 ne peut venir que de
  la boucle des abilities hébergées. (Cohérent avec la mesure L3 de case-37 : une DryBush **VIDE**
  rend déjà +9.)
- **Swamp → `-25 Thorns_DefenseReduction` = Loop1.**
  `IdunBattleLogic.Entities.Abilities.Tiles.ThornsBlockMovementAbility$$CreateBehaviour` =
  ```
  n  = AbilityConfiguration.GetNumberConstant(config, 0x14)
  b1 = DSLFactory.AddBlockEnteringUnitsEffect(0)
  b2 = DSLFactory.AddStaticStatModifierEffectToOwner(0xb, 3, Direct(n))
  return b1 & b2
  ```
  `…ToOwner` = **sur la tuile elle-même**. Une Swamp porte donc `Thorns_DefenseReduction` (0xb) dans
  son `EffectsOwnedComponent` — ce que case-102 avait déjà **mesuré live** (`C1_02` : Swamp =
  `BlockEnteringUnits`(0) + `Thorns_DefenseReduction`(0xb)) et que ce cas re-mesure sur `MC1_67`
  (§4, volet B). Et **aucune** clé `Default.TileEffects.SwampBlockMovement` / `…ThornsBlockMovement`
  n'existe : sur une Swamp, **Loop2 ne rend rien**.

> C'est là que le port se trompait de nature : le −25 était rangé dans une table « terrain → ability
> hébergée » alors qu'il vient du canal **dynamique**. La table statique ne pouvait donc que dériver
> du canal réel — et il n'existait **aucun endroit** où les deux se rencontraient pour le montrer.

---

## 2. L'état d'avant — le fork, et pourquoi il devenait faux en silence

Deux tables pour un seul concept apparent :

- `engine/utilities/tile.py::TERRAIN_TILE_EFFECTS = {"DryBush": ("LightCover",)}` — partagée, lue par
  **7** call-sites ;
- `engine/runner/operations/spawn.py::_PLACEMENT_TERRAIN_EFFECTS = {"Swamp": ("Thorns_DefenseReduction",)}`
  — **locale**, lue par le seul `_sort_tiles_by_utility_for_summon` (+ recopiée dans `probe_130`).

Le site de placement concaténait les deux ; les six autres ne voyaient que DryBush. Le mode de
défaillance n'était pas une valeur fausse **aujourd'hui**, mais une **bombe à retardement** : le site
de placement était le seul à ne PAS lire `state.effects`. Le jour où son harnais aurait passé
`tiles=tileMeta` à `load_state` (case-102, opt-in), la Swamp aurait compté **−50** : une fois par le
canal dynamique, une fois par la table. Aucune erreur, aucun crash — juste un tri de placement faux.

---

## 3. Le fix — un foyer, deux tables NOMMÉES d'après leur boucle

`engine/utilities/tile.py` :

```python
TERRAIN_HOSTED_ABILITIES   = {"DryBush": ("LightCover",)}              # Loop2
TERRAIN_TILE_OWNED_EFFECTS = {"Swamp": ("Thorns_DefenseReduction",)}   # repli Loop1

def terrain_tile_effects(terrain, dynamic=None) -> list:
    out  = list(TERRAIN_HOSTED_ABILITIES.get(terrain or "", ()))
    have = set(dynamic or ())
    out += [n for n in TERRAIN_TILE_OWNED_EFFECTS.get(terrain or "", ()) if n not in have]
    return out
```

- **Loop2 n'est jamais dédupliqué** (le natif somme les deux boucles) ; **le repli Loop1 l'est
  toujours** contre le canal dynamique de l'appelant. C'est cette asymétrie qui rend le repli
  inoffensif au lieu d'additif.
- Le repli existe **uniquement** parce que `load_state(tiles=…)` est opt-in : un état non hydraté ne
  porte aucun effet de tuile, alors que le natif pose celui de la Swamp au setup de la bataille. Il
  s'efface de lui-même dès que le canal réel est là.
- **`BlockEnteringUnits` n'y figure pas, exprès** : aucun poids `Default.TileEffects` ne le nomme
  (Loop1 le rejette sur `HasUtilityValue`), et le faire entrer dans les listes offline réveillerait le
  gate de pathfinding non porté (#131, cf. case-102 §5.4).

**Tous les call-sites passent désormais leur canal dynamique** — c'est ce qui rend le double comptage
structurellement impossible :

| call-site | canal dynamique passé |
|---|---|
| `engine/move.py` | `effects_by_pos` (tileMeta) |
| `engine/playbook/base.py::tile_utility` | `ctx.effects_by_pos` |
| `engine_agreement_stages.py` | `ctx.effects_by_pos` |
| `engine/runner/damage_model.py::_positional_att_ctx` | `state.effects.by_unit[tid]` |
| `engine/runner/abilities/loki/mv71.py` (×2) | `state.effects` / `scene.tile_effects_by_pos` |
| `engine/runner/operations/spawn.py::_sort_tiles_by_utility_for_summon` | `state.effects.by_unit[tid]` **(neuf)** |
| `probe_128`, `probe_57h2` | `ctx.effects_by_pos` |

Le site de placement lit maintenant `state.effects` **comme tout le monde** : c'est le port de Loop1
qui manquait à ce site, pas une table de plus. `_PLACEMENT_TERRAIN_EFFECTS` est supprimée.

---

## 4. Validation live (`probe_155_swamp_tile_effect_fork.py`, session 14)

Géométrie de case-130 SS5 rejouée à l'identique — `admecMarshall`/ControlEdict, `MC1_67`, seed 777,
caster **forcé** sur `t15` : pool natif `[t16 Grass elev3, t25 Grass elev3, t24 Swamp elev4]`. Sans le
−25, `t24` vaudrait 50 (la plus haute) ; avec, elle vaut 25 et perd contre les 30 des Grass.

```
[A] NON hydraté   effets lus {16:[], 25:[], 24:[]}
                  tri [16,25,24]   LIVE [16] | PORT [16] genrand=2   OK
[B] HYDRATÉ       effets lus {16:['Contaminated'], 25:[],
                              24:['BlockEnteringUnits','Thorns_DefenseReduction']}
                  tri [16,25,24]   LIVE [16] | PORT [16] genrand=2   OK
                  convergence des deux régimes : OK (même ordre, même tuile)
[C] TÉMOIN        repli neutralisé -> tri [24,16,25], PORT [24] != live [16]
```

- **[B] confirme la RE au live** : `tileMeta` rend bien, sur la tuile `t24`, exactement les deux effets
  que `ThornsBlockMovementAbility$$CreateBehaviour` pose.
- **[B] est la garde anti-fork** : les deux canaux **se recouvrent** au lieu de s'additionner. Avant ce
  cas, ce régime n'était mesuré nulle part — c'est précisément l'angle mort qui laissait les deux
  copies dériver.
- **[C] est l'anti-tautologie** : sans le −25 le port place **sur la Swamp**, donc [A] et [B] mesurent
  bien le −25 et pas la géométrie.

### Tests

- **Neuf** : `tests/engine/runner/test_swamp_tile_effect_foyer_live.py` — 9 offline (règle de
  déduplication asymétrique Loop1/Loop2, terrains neutres, **anti-refork** : les deux tables sont les
  seules sources et ne se recouvrent pas) + 3 live (le canal dynamique porte bien Thorns ; les deux
  régimes s'accordent avec le live et entre eux ; témoin sans le −25). **12 passed.**
- **Rejoués** (0 skip pour cap runner) : `test_placement_sort_rng_live` 16 ; `test_mv71_sniper_drone_live`
  + `test_lightcover_gate_live` 6 ; `test_lord_of_tempests_ice_live` + `test_pick_randomly_one_rng_live`
  18 ; `test_move_tile_sweep_order_live` + `test_runner_move_live` 5 passed / 3 skip (montages non
  discriminants, raisons lues) / 1 xfail ; `test_load_state_tile_effects_live` + `test_runner_attack_live`
  5. **50 passed, 0 échec.**

---

## 5. Item (b) — `MaybeTrigger` : **PÉRIMÉ**, avec preuve

Le registre le donnait « non porté ». Il l'est, et 1:1. Décompilé de
`IdunBattle.Entities.Triggers.MaybeTrigger$$ShouldTrigger` :

```
chance = <formule V @+0x20>.Calculate(entities)
if (!ANonDeterministicAbilityTrigger.CanUseRandom(this)) return 99 < chance;
return DisallowablePseudoRNG.NextBool(this@+0x18, chance);
```

`engine/entities/triggers.py::MaybeTrigger.should_trigger` porte les trois lignes, dont la branche
`!CanUseRandom` → `99 < ch` (le port matérialise `!CanUseRandom` par `rng is None`) et le RNG **en
champ d'instance**, pris au constructeur comme le natif. Le port date de `case-1203` (nœud) et
`case-o4a-maybe-trigger-rng.md` (câblage PileIn + validation live 4/4 datapoints) ; `backlog.md` le
donne déjà barré. **Aucune action** — l'entrée #146 décrivait une intention horodatée, pas l'état du
code.

---

## 6. Ce qui n'est PAS couvert

1. **Le repli reste un repli.** Le vrai correctif de fond serait de mirrorer l'INITIALISATION native
   (les `CreateBehaviour` des abilities de terrain posent leurs effets au setup) au chargement du
   board, ce qui rendrait `TERRAIN_TILE_OWNED_EFFECTS` inutile. Non fait ici : ça ferait entrer
   `BlockEnteringUnits` dans l'état offline et réveillerait le gate pathfinding **non porté** (#131) —
   blast radius hors périmètre d'un résidu.
2. **Les autres terrains ne sont pas inventoriés.** Seuls DryBush et Swamp ont eu leur ability de tuile
   lue au décompilé. `Water`, `Bridge`, `BrokenIce`, `FirstAid`, `HulkWall`/`HulkDoor` peuvent héberger
   des abilities à poids BC (`Default.TileEffects` contient entre autres `Trench=25`,
   `Shrub_BonusDefense=25`, `SpiderWeb=-25`, `DryBush_DefenseBonus=15` — dont aucun n'est rattaché à un
   terrain aujourd'hui). Chaque ajout demande de lire le `CreateBehaviour` **et** de trancher sa boucle.
3. **Le nouveau canal du site de placement n'est mesuré que sur les effets STATIQUES d'une Swamp.**
   `_sort_tiles_by_utility_for_summon` lit désormais tous les effets dynamiques de la tuile (Fire, Ice,
   `Contaminated`…) : le natif les compte via Loop1, mais aucun scénario live monté ici ne place un
   summon à côté d'une tuile en FEU. Le régime est fidèle par construction, non confronté sur ce cas.
4. **Le multiplicateur de durée de Loop1 reste non porté** (`GetStatusEffectMultiplier`, appliqué aux
   seuls status-effects) — antérieur à ce cas, `TileEffectsUtility` somme le poids brut. Sans effet ici :
   `Thorns_DefenseReduction` n'est pas un tile-status (case-102 §3), donc le natif lui applique déjà le
   poids brut.
5. **On-appearance non portée** (3e item de la fiche #146) : hors périmètre, toujours ouvert.
