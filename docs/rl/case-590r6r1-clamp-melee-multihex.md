# #590-r6-r1 / -r2 / -r3 — le clamp mêlée en multi-hex, le threading, et le foyer déplacé

Trois résidus de la tranche `#590-r6`, résolus ensemble. **Deux énoncés sur trois étaient
partiellement faux** — pas sur le fond, sur *l'étage accusé*.

## 1. `#590-r6-r1` — la double boucle, et le SECOND écart que le résidu ne nommait pas

`IdunBattle.Core.Services.AttackQuery$$ShouldApplyRangedInMelee` (slot `IAttackQuery 21`) délègue à
`IdunBattle.Core.Services.DamageCalculations$$ShouldApplyRangedInMelee`, dont le corps est :

```
if (attackerTiles == null || attackerTiles.Count == 0) return false;
if (!HasTrait(attacker, 0xb) && !ignoreTrait)          return false;
if (UnitExtensions.HasFlag(attacker, 0x1c))            return false;
foreach (attackerTile in attackerTiles)                  // BOUCLE 1 — tous les pieds
  foreach (adj in <voisins de attackerTile>)             // BOUCLE 2
    u = UnitExtensions.GetUnit(adj, state);
    if (u != null && IsUnit(u) && !IsFriend(attacker, u, state)
        && !TileExtensions.HasSteppableUnit(adj, state)
        && DamageCalculations.CanMeleeAttackOverElevationDifference(attackerTile, adj)
        && IsTargetable(u) && IsAlive(u, state))  return true;
return false;
```

Le résidu nommait la **boucle 1**. Le décompilé en donne un **second**, de même direction :
`IdunBattle.Entities.UnitExtensions$$GetUnit(adj, state)` — les trois surcharges lues — suit
`TileContentComponent -> UnitFootComponent -> unité parente`. **N'importe quel pied résout en son
unité.** Le port, lui, comparait la `PositionComponent` (main tile) de chaque entité à l'ensemble des
voisins : une **cible** multi-hex touchant par un pied non principal était invisible. L'élévation
suivait — `CanMeleeAttackOverElevationDifference(attackerTile, adj)` prend la tuile **adjacente** et
le **pied de la boucle**, jamais deux main tiles.

Les deux écarts sont **PERMISSIFS** (portée laissée entière là où le natif rabat à 1) et **bornés au
multi-hex** : sur une unité à 1 pied des deux côtés, les deux formes coïncident exactement. C'est ce
qui explique qu'ils aient pu vivre, et c'est aussi ce qui rend tout montage mono-hex incapable de les
voir.

Porté dans `targeting.should_apply_ranged_in_melee` (+ le foyer neuf `_occupants_by_tile_id`, une
passe unique, tous les pieds, vivants seulement — même convention que `state.unit_at`) et dans son
**jumeau** `mv71._occupants_by_tile`, qui portait le volet CIBLE à l'identique.

### Le montage qui le confronte, et le fait qui le rend possible

**L'empreinte ne vient pas de l'unité — elle vient du BOARD.** `GB_Belisarius_01` porte
`BossPlatforms = [{Size: 3, Tiles: [(3,7), (2,7), (3,8)]}]`, et
`IdunBattle.Operations.SetupGameOperation$$AddBossUnit` spawne `BC.BossUnit.UnitId` sur cette LISTE
de tuiles (mesure #894-r2). **N'importe quelle unité amenée par ce canal a donc 3 pieds** — ce qui
permet de choisir le porteur, et il fallait le choisir :

* `admecBossBelisarius`, porteur « naturel » du board, a une arme **sans `Range`** → portée 1, et il
  n'est pas ranged → `onlyAdjacent` est déjà vrai avant tout clamp. **Les deux champs que le clamp
  écrit y sont indistinguables** : montage écarté après mesure ;
* `necroWarden` a `weapons[].Range = 3` → `UnitExtensions$$IsRanged` vrai → avec le préset générique
  (`onlyAdjacent = IfNotRangedCaster`, `forceMeleeTarget = IfRangedCaster`), la portée vaut 3 et
  `onlyAdjacent` est FAUX sans clamp, VRAI avec. La bascule porte sur les deux champs.

`--explicit-stats` est **réservé aux NPC/SUMMON** (la formule héros lève sur eux) : l'ajouter sur un
héros rend `--explicit-stats necroWarden: 0`.

### Mesure live

| bras | natif `abilityTargets.fromHere` | port AVANT | port APRÈS |
|---|---|---|---|
| témoin, aucun ennemi proche | `[93]` | `[93]` | `[93]` |
| ennemi au contact d'un pied **non principal** | `[95]` | **`[93, 95]`** | `[95]` |

`targets` (déplacement inclus) vaut `[93, 95]` dans le second bras : E2 reste atteignable **en
bougeant**, donc la différence sur `fromHere` est bien le clamp et pas une cible disparue. Côté
port : `clamp False -> True`, `get_range (3, False) -> (1, True)`. **Une cible illégale acceptée
-> zéro.**

### ⚠ Le capteur `abilityReason` NE PEUT PAS voir cet écart (résidu `#590-r13`)

Il passe `getUnitMainTile(caster)` à la surcharge **`IEntity`** d'`AttackQuery$$GetInvalidTargetReason`,
qui fait `UnitPosition..ctor(&pos, attackerTile)`, puis la `TargetingQuery$$GetInvalidTargetReason`
atteinte fait `TExtensions.ToList(casterTile)` : le natif n'y voit **qu'une tuile**. Sur le montage
ci-dessus il rend `hex = 0x0` (« valide ») dans les deux bras. Le capteur juste est
`abilityTargets.fromHere`, qui passe `UnitPosition{Tiles = GetTiles(unit, state)}`.

Deux pièges de lecture, tous deux mesurés :

* le champ `ok` d'`abilityReason` **reste `True` sur un refus** — c'est `targetReason.hex` qui porte
  le verdict ;
* les entrées de `targets`/`fromHere` sont clées par **`targetId`**, ni `unitId` ni `squadId` : une
  lecture par la mauvaise clé rend `[]` alors que `fromHereCount` vaut 1. Un zéro qui n'est pas une
  mesure.

## 2. `#590-r6-r3` — le threading manquait, mais la fiche accusait `PickTile`

Le threading manquait bien : `MV71SniperDroneSquadAttackAbility.get_dynamic_invalid_target_reason`
ne **déclarait** pas `caster_tiles`, donc `_invoque_regle_dynamique` (threading par signature) ne le
transmettait pas. C'est porté.

Mais le remède annoncé — « le propager à `_filter_can_attack_target_tile_from` » — aurait écrit un
étage que le natif n'a pas. Quatre décompilés :

| symbole | ce qu'il fait de `casterTiles` |
|---|---|
| `MV71SniperDroneSquadAttackAbility$$GetDynamicInvalidTargetReason` | memset 0x128, puis écrit **seulement** `+0x08 caster`, `+0x10 target`, `+0x18 caster`, `+0x48 casterTiles` (`targetTiles` n'est écrit nulle part) |
| `IdunBattle.Entities.Abilities.AbilityEntities$$get_CasterPosition` | rend `this+0x48` s'il est non nul, sinon un `UnitPosition` bâti sur `this+0x40` |
| `IdunBattle.Entities.Triggers.IsRangedAttackAbilityTrigger$$ShouldTrigger` | `pos = HasCasterPosition ? CasterPosition : EntityExtensions$$GetUnitPosition(caster, state)` |
| `MV71SniperDroneSquadAttackAbility$$PickTile` | **ne touche jamais `+0x48`** — lit `Target` pour l'anneau et la LdV, passe le caster en tant qu'**ENTITÉ** à `BattleQuery$$IsTargetInAttackRangeForSummon` (slot 0xc4) comme à `FilterTilesIfCanAttackTargetTileFromSelector$$Select` |

L'étage lecteur est donc **`IsMeleeAttack`**, et lui seul. `caster_tiles` y va, et nulle part
ailleurs. Reste **inerte en pratique** (l'unique consommateur de position hypothétique est la branche
mobile de `1101`, dont l'acteur est un summon, jamais un `tauMarksman`) : le mirror est fidèle, pas
utile aujourd'hui.

## 3. `#590-r6-r2` — le levier 1 était disponible, et il marche

`UnitExtensions$$CanMove` + `_has_active_movement_blocker` ont déménagé de
`runner/operations/turnflow.py` vers `runner/components.py`, sous le nom `unit_extensions_can_move`
(aligné sur les trois mirrors `unit_extensions_*` déjà là).

**La mesure qui l'autorise** : `import engine.runner.components` dans un process FRAIS ne fait
atterrir dans `sys.modules` ni `abilities.handler`, ni `abilities.loki.attempted_possession`, ni
`operations.turnflow`. L'arête **disparaît** — elle n'est pas contournée.

Effets mesurés :

* le différé **PORTEUR** d'`attempted_possession` est supprimé (hissé, **forme B**) ;
* celui de `movement.py::_is_unit_allowed_to_move` aussi — il était porteur **envers `turnflow`**,
  pas envers `components` ;
* l'import de `BLOCK_UNIT_MOVEMENT_EFFECT_TYPES`, différé dans `turnflow`, devient **GRATUIT** dans
  `components` (mesure inverse : charger `instinctive_behaviour` seul ne tire pas `runner.components`)
  et est hissé en tête, forme B.

**Aucun ré-export laissé dans `turnflow`** : ce serait un baril (#485-r1-r1). Les quatre lecteurs
visent le foyer par son chemin plein. `migrate_485r1_barils_reexport.py morsure` : le foyer n'est ni
`DEJA_INERTE` ni `HISSAGE_DESARMERAIT`.

Recâblés : `turnflow`, `movement`, `attempted_possession`, `probe_1015r1`, le cliquet de substrat
`probe_462` (clé FICHIER+NOM), et les deux `monkeypatch.setattr` de
`test_590r6_movement_tiles_targets_offline` + l'import de `test_287r1r1`. ⚠ La justification du
cliquet `probe_462` affirmait « son unique appelant est `has_tiles_to_move_to` » — **déjà faux avant
ce déplacement** (`movement.py` et `attempted_possession` l'appellent) ; corrigée au passage, sans
toucher au classement, qui tient : les deux appelants supplémentaires n'ouvrent pas le gate (l'un lit
un `is False` strict, l'autre n'entre en branche que sur un `is True` mesuré).

## 4. Gardes

* `tests/engine/runner/test_590r6r1_clamp_melee_multihex_offline.py` — 15 items. Vu **8 failed /
  7 passed** sur un worktree témoin détaché à l'arbre d'avant. Chaque bascule porte un témoin
  multi-hex non nul, et l'étage 3 asserte que le régime **mono-hex est inchangé**.
  ⚠ Le cran `get_range` était d'abord **vert par vacuité** : le préset générique rend
  `only_adjacent = True` dans les deux bras pour un caster non-`Ranged` (mesuré :
  `Range(value=0, only_adjacent=True)`). Remplacé par un masque à `overrideRange` explicite, qui
  bascule sur les deux champs — `(5, False)` contre `(1, True)`.
* `tests/engine/runner/test_590r6r3_threading_surcharge_type_offline.py` — 10 items, vu **5 failed /
  5 passed** sur le même témoin. Son mutant a d'abord été vert (`assert 0 != 0`) sur une ligne de 6
  tuiles où `PickTile` réussit : il faut le montage **SATURÉ** pour que le bras mêlée soit le seul à
  décider.
* `probe_590r6r1_clamp_melee_multihex_live.py` — la confrontation, les deux capteurs côte à côte.
