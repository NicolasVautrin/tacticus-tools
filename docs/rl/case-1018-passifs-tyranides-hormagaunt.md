# #1018 — `HungeringSwarm` PORTÉ + CONFRONTÉ, `AdrenalGlands` en résidu `#1018-r1`

Deux passifs, **mêmes six porteurs** (`tyranNpc1Hormagaunt`, `…Kronos`, `…Gorgon`,
`…_SyncPvp_Kronos`, `…_SyncPvp_Gorgon` — npc — et `tyranSmnHormagaunt` — summon), **un seul
montage**. Build `rnca9r7q6c`.

## 0. Le montage — npc confrontables par `--explicit-stats`, pas par injection catalogue

```
rl_duel build --board MC1_67 --p-units "tyranNpc1Hormagaunt,X,X" --explicit-stats tyranNpc1Hormagaunt
              --a-units ultraTitus --place "tyranNpc1Hormagaunt:2,4" --place "X:4,4" --place "X:3,5"
              --a-place "ultraTitus:3,4" --hp-target 900000 --armor-target 0 --crit 0,0 --block-target 0,0
```

`decisionView.effects` rend **les deux** effets sur chaque Hormagaunt (`AdrenalGlands_Effect`,
`HungeringSwarm_ExtraHits`) : la voie summon n'a pas été nécessaire. Fixture nommée :
`tests/engine/runner/test_hungering_swarm_live.py::swarm_runner`, paramétrée par phase.

## 1. `HungeringSwarm_ExtraHits` (1041) — PORTÉ, confronté 3/3

`IdunBattleLogic.Entities.Abilities.Active.Loki.HungeringSwarmAbility$$GetEffectType` → `0x411` ;
parent `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility` (l'ability pose seule son effet
sur l'owner → **ni `CreateBehaviour` ni `CreateTrigger` à porter**).

`IdunBattle.Entities.Effects.Loki.HungeringSwarmExtraHitsEffect$$CreateEffectHitsBonusForAttack` :

```
ForAddition( get_OwnerIsActor & IsMeleeAttack,
             Multiply( Direct(GetNumberConstant 0x2b = extraHit),
                       Count(UnitsWithIds(
                                 Friends(of = Owner@DSLSelectors+0x30,
                                         entities = AdjacentUnits(Target@+0x60, unique, 3)
                                                      op_Subtraction Caster@+0x48,
                                         selectionType = 3),
                                 GetStringArrayConstant 0x37 = unitIds)) ) )
```

`CreateActiveCondition`/`CreateTargetSelector` = corps dédupliqué partagé par 320 classes
(`return null`) → ni gate d'activité, ni aura.

**La constante ne couvre PAS les variantes, et c'est LU.**
`unitIds = "tyranNpc1Hormagaunt,tyranNpc2RipperSwarm,tyranSmnHormagaunt,tyranSmnRipperSwarm"`.
Le filtre natif est `IdunBattle.Entities.UnitExtensions$$HasUnitId` =
`idun.shared.UnitNamingConventions$$GetUnitIdWithoutRarity(GetUnitId(u)) == id`, et
`GetUnitIdWithoutRarity` est **littéralement `configUnitId.Split(':')[0]`** : il retire un suffixe
de *rareté*, jamais un suffixe de *variante*. Deux Kronos adjacents ne se comptent donc pas.
⚠ `entities/selectors/units.py::UnitsWithIds` cite encore `GetUnitIdWithoutLevel` — sur ce build
c'est `…WithoutRarity`. Même sémantique pour ce port ; **signalé, non édité** (foyer partagé).

**Aucune réduction offline** : `tyranSmnHormagaunt.visualId == "tyranNpc1Hormagaunt"` et
`tyranSmnRipperSwarm.visualId == "tyranNpc2RipperSwarm"` — la constante liste déjà les *deux*
formes de chaque unité, comme l'`affectedUnitIds` de SupremeCommander. Filtre exact des deux côtés.

### GROUND TRUTH (arme de l'Hormagaunt = 2 coups)

| phase | géométrie des 2 pairs | `unitId` des pairs | NATIF | PORT |
|---|---|---|---|---|
| `armed` | ADJACENTS à la cible | `tyranNpc1Hormagaunt` (dans la liste) | **4** | +2 |
| `far` | `d(cible) = 3` | `tyranNpc1Hormagaunt` (dans la liste) | **2** | +0 |
| `kronos` | ADJACENTS à la cible | `…HormagauntKronos` (**hors** liste) | **2** | +0 |

`far` et `kronos` sont **indépendantes** : `far` casse la géométrie à roster constant, `kronos`
casse le filtre à géométrie constante (mêmes traits, même nom d'affichage « Hormagaunt », mêmes
deux passifs, mêmes tuiles). Sans la seconde, « +2 » serait aussi bien expliqué par « 2 alliés
adjacents, quels qu'ils soient ». **Contre-épreuve de la garde** : retirer `UnitsWithIds` du port
laisse `armed` et `far` VERTS et ne fait rougir que `kronos` —
`AssertionError: [kronos] le PORT rend +2, attendu +0`.

### Trois manques trouvés par décomposition par étage

1. **`vid_by_id`** — substrat de `UnitsWithIds`. La docstring de `build_hits_board` le proscrivait ;
   elle visait l'usage comme **identité** (deux instances du même type indiscernables), qui reste
   proscrit. Ici c'est l'usage **inverse** — un prédicat de *type*, où l'indiscernabilité est
   exactement ce que `HasUnitId` exige. Docstring mise à jour, pas contournée.
2. **`hp_by_id` / `hpmax_by_id`** — **premier étage divergent** : `AdjacentUnits` rendait `[]` sur
   un board peuplé, parce que `engine/dsl/base.py::_is_alive` classe MORT tout dict sans `hp > 0`
   ni `hpMax` (sa dégradation nommée). Santé **LUE** des deux côtés — un `hp = 1` inventé aurait
   fait passer le compte pour une mauvaise raison.
3. **Cycle d'import**, fermé dans l'ordre de la doctrine : sélecteurs par **sous-module** (forme de
   `loki/summary_execution.py`) ; `entities.formulas` **différé**, et différé **PORTEUR** —
   mesuré : hisser ferme `formulas → services.movement_query → runner.components →
   entities.effects.__init__ → factory → ce module → formulas`, et `import engine.entities.formulas`
   en process frais levait alors `ImportError`. Forme B (module lié).

## 2. `AdrenalGlands_Effect` (1049) — NON PORTÉ, résidu `#1018-r1`, RE complète ci-dessous

`…AdrenalGlandsAbility$$GetEffectType` → `0x419`, même parent `AOwnerEffectTriggeredAbility`.
i2 : « May move with +1 Movement if that move ends in a hex adjacent to an enemy ».
`abilities.AdrenalGlands.constants = {"extraMovement": "1"}`.

`IdunBattle.Entities.Effects.Loki.AdrenalGlandsEffect$$CreateRangeBonusForMovement(owner)` —
**seul implémenteur du hook dans tout le build** :

```
EffectRangeBonus { Trigger = null,                                  // +0x0
                   ExtraRange = GetNumberConstant(0xe = extraMovement),   // +0x8
                   ExtraRangeCondition = tile => IsValidExtraMove(owner, tile),  // +0x10
                   ReduceRange = null }                             // +0x18
```

`…$$IsValidExtraMove(owner, movementEndTile)` (slots `IBattleQuery` tranchés par **arité + type
des args**, jamais par le dump de mai) :

```
p = GetCurrentOwnerEntityId(owner)
cur = Query.GetAdjacentEnemies(owner,           p, ignoreSteppables: false)   // slot 0x7d
end = Query.GetAdjacentEnemies(movementEndTile, p, ignoreSteppables: false)
foreach (enemy in end)
    if (!cur.Contains(enemy) && IsNearestTileToMoveToMeleeWithEnemy(owner, enemy, movementEndTile))
        return true;
return false;
```

`…$$IsNearestTileToMoveToMeleeWithEnemy(owner, enemy, tile)` :

```
path = Query.GetPathTo(owner, tile);            // slot 0x13, 2 args
if (path == null) return false;
d = path.Count;                                 // ICollection<IEntity>.get_Count
foreach (t in Query.GetAdjacentTiles(enemy, onlyEmptyOrSteppable: false,
                                     onlyWalkableTiles: true, allowTemporary: true))  // slot 0x4f, 4 args
{
    if (t == tile) continue;
    if (!t.IsWalkable(checkFog: true)) continue;
    if (!t.IsFreeTile(State, allowSteppable: true, allowTemporaryTile: false, allowAnyUnit: false)) continue;
    p2 = Query.GetPathTo(owner, t);
    if (p2 != null && p2.Count < d) return false;   // une tuile STRICTEMENT plus proche existe
}
return true;
```

⚠ Le décompilé Ghidra écrit `tile` là où la boucle porte sur `t` (registres confondus). Le
discriminant n'est pas le pseudo-C : `while (tile == t) continue` juste avant n'a de sens que si la
suite porte sur `t`, et `tile` étant par construction *walkable et libre* (c'est une destination de
mouvement), lire `tile` rendrait les deux filtres invariants — donc inertes.

**Consommation** : `BaseEffect$$RangeBonusForMovement(entities)` appelle le hook, court-circuite si
`Trigger != null` et ne passe pas, puis convertit en `IdunBattle.Core.Services.RangeBonus`
`{ExtraRange@+0x0, ExtraRangeCondition@+0x8, ReduceRange@+0x10}`. Côté `MovementQuery` :

* `$$MovementRangeWithAppliedBonus(unit, baseRange, bonuses)` ne lit **que `ReduceRange`** (`null`
  ici) → AdrenalGlands **n'augmente pas la portée brute** ;
* `$$GetExtraReachableTiles(defaultReachableTiles, pathfinderType, unit, rangeBonus)` : pour chaque
  tuile atteignable normalement, énumère les tuiles à `ExtraRange` de plus, écarte celles déjà
  atteignables, et **ne garde que celles où `ExtraRangeCondition(t)` est vrai**.

⇒ AdrenalGlands ajoute des **tuiles supplémentaires conditionnelles** (« +1 mouvement seulement si
ça amène au contact d'un ennemi *nouveau*, et par la tuile la plus proche de lui »), pas de la
portée.

### Pourquoi il n'est pas livré ici

L'étage manquant côté port n'est pas l'effet : c'est **toute la chaîne**. `create_range_bonus_for_movement`
n'existe pas sur `BaseEffect`, il n'y a **aucun** agrégateur `RangeBonus`, et
`engine/services/movement_query.py::get_movable_tiles_for` — foyer de **tout** le mouvement du
moteur — n'a pas de point d'entrée pour des tuiles extra conditionnelles. Le porter demande le hook,
l'agrégateur, le mirror de `GetExtraReachableTiles`, et les deux helpers ci-dessus (qui exigent
`GetPathTo`, `GetAdjacentEnemies`, `GetAdjacentTiles`, `IsWalkable`, `IsFreeTile`). Livrer ça sans
budget de validation adversariale sur un foyer aussi partagé serait un port mou.

⚠ Piège de montage pour le successeur : les Hormagaunts portent
`InstinctiveBehaviour_BlockMovement` (« si une cible est à portée, cette unité ne bouge pas ») —
tout scénario de mouvement doit être monté **hors portée** de tout ennemi, sinon le trait masque
l'effet mesuré.

## 3. Ce qui n'est PAS couvert

* `AdrenalGlands` : rien de porté (résidu `#1018-r1`).
* `HungeringSwarm` : le canal **AURA** n'est pas concerné (l'effet est un self-effect strict, pas
  de `CreateTargetSelector`) ; le porteur **summon** (`tyranSmnHormagaunt`) n'a pas été amené en
  bataille — inutile ici, l'effet ne lit ni stats ni traits du caster et les npc suffisent.
* Aucune mesure sur une attaque d'**ability** en mêlée (l'arbre n'a pas d'`IsNormalAttack`, donc le
  bonus devrait valoir aussi pour elles) : non confronté.
