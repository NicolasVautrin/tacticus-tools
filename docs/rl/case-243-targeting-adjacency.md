# case-243 — les deux règles d'adjacence du filtre de ciblage (bits 32 et 42)

**Question posée** : les bits `TargetIsNotAdjacent` (32) et `TargetIsNotAdjacentToEnemy` (42) sont
**déclarés** par des masques posés au registre mais **non portés** — le moteur ne refuse donc jamais
sur eux. Le prédicat natif est-il dérivable de l'état que le port possède déjà, ou dépend-il d'un
étage réellement absent ?

**Réponse : les DEUX sont dérivables**, et portés dans le maillon générique
(`engine/runner/abilities/targeting.py`), pas en special-case par ability.

---

## 1. Les deux prédicats au décompilé

Tout se passe dans la surcharge **7 arguments** de
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (le filtre statique). Ses
paramètres : `(this, caster, casterTiles, target, options, ignoreRangeChecks, range)`. En tête de
fonction elle calcule `targetTiles = IdunBattle.Entities.EntityExtensions$$GetTiles(target, state)`.

### bit 32 — `TargetIsNotAdjacent` (`0x100000000`)

```c
if ((rules >> 0x20) & 1) {
    if (battleQuery.<slot 0x62>(targetTiles, casterTiles)) -> broken(0x100000000)
}
```

`slot 0x62` = la surcharge **LISTE × LISTE** d'`IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent`
→ `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(IList, IList)`. Sémantique : « la cible
est AU CONTACT du caster ⇒ REFUS ». C'est l'exact inverse du volet `only_adjacent` de la portée, qui
utilise le **slot 0x61** (`(casterTiles, target)`).

### bit 42 — `TargetIsNotAdjacentToEnemy` (`0x40000000000`)

```c
if ((rules >> 0x2a) & 1) {
    units = battleQuery.<slot 0x80>(targetTiles, caster, false);
    if (units.Count > 0) -> broken(0x40000000000)
}
```

`slot 0x80` = `IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies(IList<Tile>, IEntity, bool)` :

```
players = state.GetEntity(unit.OwnerComponent.CurrentPlayerEntityId)
GetUnitsOnTiles( IterateAdjacentTiles(tiles, false, true, true), friendOf: null, enemyOf: players, onlyNonSteppable )
  -> BattleQuery$$CountOrGetUnitsOnTiles :
       u = UnitExtensions.GetUnit(tile, state);        si null -> skip
       si onlyNonSteppable && IsSteppable(u)           -> skip          (call-site : false)
       si enemyOf != null && !IsEnemy(u, enemyOf)      -> skip
       set.Add(u)
```

« Ennemi » se lit **par rapport au CASTER**, pas à la cible — indispensable, puisque le seul porteur
du bit (`SporeMineLauncher` 1145) cible une **TUILE**, qui n'a pas de camp.

### Comment les index de slot ont été LUS (et non devinés)

Le décorateur `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery` ré-appelle l'inner
`IBattleQuery` par le **même index d'interface**, depuis des lambdas nommées :

| lambda | slot |
|---|---|
| `…u003Cu003Ec__DisplayClass117_0$$u003CAreEntitiesAdjacentu003Eb__0` | 0x60 |
| `…u003Cu003Ec__DisplayClass118_0$$u003CAreEntitiesAdjacentu003Eb__0` | 0x61 |
| `…u003Cu003Ec__DisplayClass119_0$$u003CAreEntitiesAdjacentu003Eb__0` | **0x62** |
| `…u003Cu003Ec__DisplayClass152_0..155_0$$u003CGetAdjacentEnemiesu003Eb__0` | 0x7d…**0x80** |
| `…u003Cu003Ec__DisplayClass102_0$$u003CGetFreeAdjacentTilesu003Eb__0` | **0x52** |

C'est la seule lecture qui donne l'index sans supposer l'ordre de déclaration de l'interface.

### Deux pièges de lecture rencontrés

1. Le `GetTiles(target)` du bloc bit 42 transite par un corps IL2CPP **dédupliqué** `return param_1;`
   (une identité), que ghidra étiquette `idun.tests.TestItemModel$$GetNextLevelItemModel`
   (refcount 2590). Ce n'est **pas** une extraction de première tuile.
2. `IdunBattle.Entities.EntityExtensions$$IterateTiles` a **trois** branches
   (`UnitFootComponent` → la tuile du pied ; `TileComponent` → **l'entité elle-même** ;
   `UnitComponent` → l'empreinte). C'est la 2ᵉ qui rend `[la tuile]` pour une cible-tuile —
   `components.get_unit_feet` (mirror de `GetUnitFeetIds`) ne couvre que la 3ᵉ et rend `[]`, ce qui
   aurait désarmé les deux règles pour toute ability tile-target.

---

## 2. Ce que la mesure a imposé EN PLUS : l'ORDRE

Le natif s'arrête à la **PREMIÈRE** règle rompue. Porter une règle sans porter celles qui la
précèdent produit un refus **pour la mauvaise raison** — ce que le contrat de fidélité de `case-115`
§3 interdit explicitement (`jamais : port != 0 et port != natif`).

Première passe de `probe_243_not_adjacent.py` : sur `bloodIntercessor` → `necroWarden` u81 à d=1, le
natif rend `0x20 TargetHasFreeAdjacentTile` (la cible est encerclée) et le port rendait
`0x100000000`. Trois maillons **antérieurs** ont donc dû entrer dans le même commit :

| maillon | position native | prédicat |
|---|---|---|
| branche `TargetIsTile` (tête du filtre) | **1ʳᵉ** règle de refus | `!IsWalkable(GetMainTile(target), true)` et pas `AllowUnwalkableTargetTile` → **littéral 1** |
| bit 5 `TargetHasFreeAdjacentTile` | après portée/LoS | `battleQuery.<slot 0x52>(target).Count == 0` |
| bit 12 `TargetTileIsFree` | bloc TUILE | `!TileExtensions$$CanAddUnit(mainTile, state, 1, 0, 0)` |

> ⚠ **`ValidRequest` (`0x1`) n'est pas toujours « ability indisponible ».** Le natif REUTILISE ce
> littéral pour « tuile-cible non marchable », depuis la cascade elle-même. Un oracle qui exclurait
> `0x1` du contrat à l'aveugle (comme le fait, légitimement pour son périmètre,
> `test_targeting_masks_live.py`) masquerait un vrai désaccord : **5 tuiles de C3_30 le montrent**.
> Le discriminant sûr est la **dépendance à la cible** — une raison de disponibilité sort AVANT que
> la cible ne soit regardée, donc elle vaut pour TOUTES les cibles du couple (ability, caster).

---

## 3. Ce qui n'est PAS porté, et pourquoi

* **bit 21 `CasterHasFreeAdjacentTile`** — même prédicat que le bit 5 sur le CASTER, mais **aucun
  masque du registre ne le porte** : rien à valider, le porter serait spéculatif.
* **Le terme « tuile RÉSERVÉE »** de `CanAddUnit` (`Position+0x2c`) — capté par aucun RPC, donc
  non modélisé (dégradation permissive). C'est la **même** limitation, déjà assumée, que
  `engine/battle_query.py::can_add_unit`, le pendant DÉCISION du prédicat — pas un nouveau résidu.
* **`TileExtensions$$IsTemporary`** — non modélisé côté `Board`. Conséquence bornée : les deux
  surcharges natives de `GetFreeAdjacentTiles` (slots 0x52 et 0x53) ne diffèrent QUE par ce flag,
  elles coïncident donc offline.

---

## 4. Validation

Oracle = `abilityReason` (masque `TargetingRule` natif). Montage nommé :
`probe_243_not_adjacent.py` (+ fixture `tests/engine/runner/_not_adjacent_stage.py`), garde
`tests/engine/runner/test_targeting_adjacency_rules_live.py`.

**Géométrie FORCÉE, jamais subie** : les trois héros sont DÉPLACÉS au contact d'ennemis distincts,
puis **deux `endturn`** purgent le flag `Moved` (`StartTurnOperation` purge les flags du joueur
entrant) — sans quoi `CasterHasNotMoved` (0x10, présent dans les masques de 1058 et 1153) sortirait
du volet CASTER et **masquerait** le bit 32. Le runner est bâti `--no-ai`.

**Rouge AVANT / vert APRÈS** (MC1_67, seed 777) — « avant » = la même ability privée des quatre
bits, ce qui est indiscernable d'une règle non portée :

| ability | caster | cible | natif | AVANT | APRÈS |
|---|---|---|---|---|---|
| 1058 Waaagh | orksWarboss | necroWarden d=1 | `TargetIsNotAdjacent` | **`TargetIsInRange`** (mauvaise raison) | `TargetIsNotAdjacent` |
| 1153 HammerOfWrath | bloodIntercessor | necroWarden d=1 | `TargetIsNotAdjacent` | **0 (accepté)** | `TargetIsNotAdjacent` |
| 1139 SentinelDirectives | admecDestroyer | necroWarden d=1 | `TargetIsNotAdjacent` | **0 (accepté)** | `TargetIsNotAdjacent` |
| 1145 SporeMineLauncher | tyranBiovore (MoW) | tuile libre voisine d'un ennemi | `TargetIsNotAdjacentToEnemy` | **0 (accepté)** | `TargetIsNotAdjacentToEnemy` |
| 1145 SporeMineLauncher | tyranBiovore (MoW) | tuile OCCUPÉE voisine d'un ennemi | `TargetTileIsFree` | **0 (accepté)** | `TargetTileIsFree` |
| 1145 SporeMineLauncher | tyranBiovore (MoW) | tuile libre loin de tout ennemi | 0 | 0 | 0 |

Le cas Waaagh est le plus instructif : ce n'était **pas** un trou permissif mais une violation de
contrat **préexistante**, latente parce qu'aucune géométrie de test n'amenait un ennemi à d=1 du
Warboss.

**Contrat sur l'ensemble des couples mesurés** : 18 couples (3 casters × 6 unités) + 3 tuiles →
**0 refus inventé, 0 refus pour la mauvaise raison**, 3 reproductions exactes de `TargetIsNotAdjacent`.

**Généralisation** (AUTRE board `C3_30`, AUTRE seed `31337`, AUTRES porteurs des bits 5 et 12 qui ne
portent PAS 32/42 : 1009 `necroOverlord`, 1003 `ultraInceptorSgt`, 1112 `tyranWingedPrime`, 1201
`orksRukkatrukk` MoW ; unités ET échantillon de tuiles) : **88 couples, 0 hors contrat, 0 refus
inventé, 0 mauvaise raison, 25 reproductions exactes**.

**Confrontabilité des porteurs** : `orksWarboss`, `bloodIntercessor`, `admecDestroyer`,
`necroOverlord`, `ultraInceptorSgt`, `tyranWingedPrime` = HERO présents dans
`rl_duel.py build --list-pool` ; `tyranBiovore` et `orksRukkatrukk` = **MoW du pool MoW**.

### Non couvert

* Le bit 21 (aucun porteur) et le terme « tuile réservée » de `CanAddUnit` (non observable).
* `1219 IronkinSteeljack` porte le bit 12 mais n'a pas été exercé (porteur hors des deux montages) —
  il passe par le même maillon générique que 1112/1145/1201, tous trois confrontés.
* La face **EXÉCUTION** : ce cas ne touche que la DÉCISION de ciblage. Les behaviours des quatre
  abilities sont inchangées, et leurs tests live (`test_waaagh_cast_gate_live`,
  `test_hammer_of_wrath_live`, `test_sentinel_directives_live`, `test_spore_mine_launcher_live`)
  ont été rejoués verts.
