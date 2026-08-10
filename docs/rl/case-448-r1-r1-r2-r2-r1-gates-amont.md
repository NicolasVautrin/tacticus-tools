# case-448-r1-r1-r2-r2-r1 / #550-r1 — les SEPT gates AMONT de `MoveUnitOperation`, le LIFT-OFF, et la RÉSERVATION

Tranche MOUVEMENT / TUILES / gates d'Operation. Build `rnca9r7q6c`. Foyers édités :
`engine/runner/operations/movement.py`, `engine/runner/operations/tile_reservation.py` (neuf),
`engine/runner/state.py`, `engine/runner/abilities/behaviours/movement.py`,
`engine/entities/pathfinding/{base,walk}_pathfinder.py` (documentation).

> **LIVRÉ + CONFRONTÉ (2026-08-10).** Les sept gates sont au rang natif ; le LIFT-OFF existe ;
> la réservation est un état réel. Témoin **LIVE** avec contrôle positif mordant sur le seul gate
> drivable de l'extérieur, et contre-épreuve à **5 mutants / 5 rouges** offline.

## 1. Les sept gates, lus VERBATIM en tête d'`Execute`

```
if (!IsAllowedToMove(unit, options.<+0x13>))                    return;   // G1
if ( UnitIsOnTiles(unit, position))                             return;   // G2
if (!TilesAreWalkable(unit, position))                          return;   // G3
if (!TilesMatchUnitFeetCount(unit, position))                   return;   // G4
if ( IsDisallowedEmptyPosition(unit, position, options.<+0x15>))return;   // G5
if ( IsPositionReservedForOtherUnit(unit, position))            return;   // G6
if ( IsPositionReservedForDrafting(unit, position))             return;   // G7
```

Trois d'entre eux **refusent quand ils rendent VRAI** ; recopier la polarité au jugé en aurait
inversé la moitié. **Aucun n'appelle `RemoveReservation`** — ils sont AMONT de `SetReservation`,
il n'y a rien à retirer. C'est ce qui les distingue des deux gates d'abandon déjà portés.

| gate | corps natif | port |
|---|---|---|
| G1 `IsAllowedToMove` | `(!ignoreBlockers && !CanMove) \|\| IsDead \|\| HasFled` → refus | `turnflow._can_move` / `UnitComponent.alive` / `UnitFlagsComponent.FLED` |
| G2 `UnitIsOnTiles` | `feet.Count == tiles.Count && ∀ foot : tiles.Contains(GetMainTile(foot))` | `get_unit_feet` vs l'empreinte de destination |
| G3 `TilesAreWalkable` | `∀ tile : BattleQuery$$IsWalkableTile(tile)` = `tile != null && IsTile(tile) && comp.<+0x10> == 0` | `board.id_at` + `board.walkable` |
| G4 `TilesMatchUnitFeetCount` | `tiles.Count == 0 \|\| feet.Count == tiles.Count` | porté, **INERTE** sous le collapse mono-hex, et c'est dit |
| G5 `IsDisallowedEmptyPosition` | `position.Count == 0 && !allowNullTargetPosition` | l'unique gardien du LIFT-OFF |
| G6 `IsPositionReservedForOtherUnit` | `BattleQuery$$IsTileReservedForAnotherUnit(position, unit)` | `tile_reservation` (§3) |
| G7 `IsPositionReservedForDrafting` | `∃ tile : IsTilePendingDrafting(tile, state, null)` | **NON PORTÉ**, direction PERMISSIVE dite |

`HasFled` est un corps d'une ligne : `UnitExtensions$$HasFlag(unit, 9)`. `G7` lit le
`DraftingComponent` des joueurs, que le runner n'a pas et qu'aucune seed BC ne publie — le
fabriquer depuis autre chose serait une hypothèse déguisée en mirror.

## 2. La branche `allowNullTargetPosition` — le LIFT-OFF

```csharp
if (position.Count == 0) {                       // G5 a déjà refusé si !options.<+0x15>
    processor.<slot 7>(unit, removeTileFromUnit: true);      // RemoveUnitFromTiles
    EvaluateAfterMoveTriggers(unit, position, previousPosition, movementSteps: 0,
                              isInterimStep: options.<+0x14>, triggeringAbilityOrEffect);
    return;
}
```

Le **slot 7** est identifié par RECOUPEMENT, pas par supposition :
`IdunBattle.Entities.Behaviours.RemoveUnitFromItsTilesBehaviour$$Execute` appelle le MÊME slot avec
la MÊME signature `(unit, <bool>)`, et le port en a déjà le mirror
(`operations/remove_unit_from_tiles.py`).

Rien de la séquence nominale n'est joué : ni `SetMovedFlag`, ni `KillSteppableUnits`, ni
`UpdateCharging`, ni `RecordTilesMoved`, ni `RefreshEffects`. **Seul** le vecteur after-move, à
`movementSteps = 0`.

⚠ **`()` N'EST PAS `None`, et la distinction est LUE.** Le natif pose
`comp.<+0xa8> = Nullable(UnitPositionId(position))` : sur une position VIDE le `Nullable` a quand
même une VALEUR, donc le gate `if (!ovr.HasValue || IsDead) return` **ne mord pas**. Le port code
donc « override posé, empreinte vide » par le tuple VIDE et « aucun override » par `None`. Les
confondre ferait retomber TOUT lift-off sur un refus muet — le bug le plus facile à écrire ici.

**Consommateur à câbler, hors de mon foyer** : `abilities/loki/quickening.py` collapse encore
l'échange en deux mouvements directs (`enforce_native_gates=False`), et sa docstring dit
explicitement que le collapse **dépend** de l'absence du gate d'occupation. La mécanique du
lift-off existe désormais ; le rebranchement appartient à l'agent qui possède `runner/abilities/**`.

## 3. La RÉSERVATION (#550-r1) — un no-op qui n'en était pas un

Cinq mirrors (`operations/tile_reservation.py`), tous sur `TileContentComponent+0x34`
(`Nullable<int>`) :

```
ReserveForUnit(tile, unit)          content.<+0x34> = Nullable(unit.Id)          — AUCUN gate
RemoveReserveForUnit(tile, unit)    if (HasValue && Value == unit.Id) = null     — gate d'IDENTITÉ
IsTileReserved(tile)                HasValue
IsTileReservedForUnit(tile, unit)   unit != null && HasValue && Value == unit.Id
IsTileReservedForOtherUnit(tile, allowedUnit)
        allowedUnit == null : HasValue
        sinon               : !(HasValue && Value == allowedUnit.Id)
BattleQuery.IsTileReservedForAnotherUnit(tiles, unit)     — l'agrégateur du gate G6
        ∃ tile : IsTileReserved(tile) && !IsTileReservedForUnit(tile, unit)
```

### 3.1 DEUX HOMONYMES, DEUX POLARITÉS **OPPOSÉES**

Sur une tuile **NON réservée** et un `allowedUnit` non nul,
`TileExtensions$$IsTileReservedForOtherUnit` rend **VRAI** et
`BattleQuery$$IsTileReservedForAnotherUnit` rend **FAUX**. Ce n'est pas une lecture hâtive : le
décompilé calcule littéralement `!(HasValue && Value == allowedUnit.Id)`, et son raccourci
`if (!HasValue) return true` **confirme** la formule au lieu de la contredire. Le test
`test_4b_les_DEUX_polarites_opposees_sont_FIGEES` existe pour empêcher qu'un lecteur « corrige »
la première en croyant à une coquille.

### 3.2 CE QUE ÇA CHANGE : `CanAddUnit` **EXIGE** la réservation quand son `parent` est non nul

```csharp
CanAddUnitFromAbility(tile, state, parent, allowSteppable) {
    if (!IsFreeTile(tile, state, allowSteppable, false, false)) return false;
    if (IsTileReservedForOtherUnit(tile, parent))               return false;
    if (IsTilePendingDrafting(tile, state, null))               return false;
    return true;
}
```

et `CanAddUnitTileSelector$$Select` résout `parent` par un **sélecteur**
(`this.<+0x20>.SelectUnit(entities, 3)`). Avec un `parent` non nul et aucune réservation, **aucune
tuile ne passe**. Le `Reserve(Owner, targetTiles)` que l'arbre de `1121 ItItches` place AVANT son
`Foreach(CanAddUnit(targetTiles, Owner, ...))` est donc **ce qui fait passer** ce `CanAddUnit` :
le nœud est load-bearing, et le verdict « no-op porté » de #550 est **infirmé**.

⇒ Tant que `entities/selectors/tiles.py::CanAddUnit` ne lit PAS la réservation, **les deux
omissions se compensent** et l'observable est inchangé. Le jour où elle la lira, elle devra lire
ce modèle-ci — et inversement, l'ajouter sans lui ferait spawner ZÉRO unité sur `ItItches`.
Résidu **`#550-r4`**, foyer `entities/selectors/tiles.py` (autre agent).

## 4. Mesures

### 4.1 Offline — `probe_448r1r1r2r2r1_gates_amont.py --offline` (boards `C4_09` + `C3_23`)

| bras | verdict |
|---|---|
| G1 × 3 (`Stationary` / `IsDead` / `HasFled`), chacun avec son contrôle positif | refuse / le contrôle bouge |
| G2 tuile propre | `abandon='unit-is-on-tiles'`, `movementSteps` non posé ; gate OFF rejoue tout |
| G3 bras `IsTile` (hors plateau) + bras `walkable == False` (`C3_23`, 4 tuiles `ForceUnplayable`) | refuse ; gate OFF pose |
| G5 + E8 | sans l'octet : refus ; avec : `feet == []`, `steps = 0`, `path = None` |
| G6 + cycle Set/Remove | refuse si réservée par un AUTRE ; passe si réservée par SOI ; table VIDE après un move nominal |
| polarités opposées | `BattleQuery=False` / `TileExtensions=True` sur la même tuile |
| `enforce_native_gates=False` | bouge malgré G1 **et** G6 |

`C3_23` n'est pas un choix : `C4_09` n'a **aucune** tuile non walkable, donc sans ce second board
le bras `TileComponent.<+0x10> != 0` de `IsWalkableTile` n'était **pas exercé du tout**.

### 4.2 Contre-épreuve — `--mutants` : **5 mutants, 5 ROUGES**

`M1-G1` 3 bras KO · `M2-G2` 1 · `M3-G3` 2 · `M5-G5` 1 · `M6-G6` 1. Aucun bras n'est inerte.

### 4.3 LIVE — le seul gate drivable de l'extérieur (`MC1_67`, seed 777)

| | position | `unitFlags` |
|---|---|---|
| natif, `move (1,0) → (1,0)` | inchangée | `[]` → `[]` |
| **CONTRÔLE POSITIF**, `move (1,0) → (2,0)` | `(2,0)` | `[]` → `[0, 1, 4]` |
| port, gates **ON**, même vecteur | inchangée, `abandon='unit-is-on-tiles'` | pas de `Moved` — **ACCORD** |
| port, gates **OFF** (= le port d'AVANT) | — | **`Moved` posé** — **DÉSACCORD** |

`Moved` ferme la règle de ciblage `CasterHasNotMoved` de tout cast ultérieur du **même tour** : la
dégradation était silencieuse *et* conséquente.

⚠ **Les six autres gates ne sont pas drivables ainsi** — `applyAction {kind:"move"}` traverse la
validation d'entrée native avant `Execute`, et une destination non walkable / réservée / vide n'est
dans aucun canal d'action (déjà mesuré, `case-448-r1-r1-r2-r2` §7.2). Le décompilé établit l'étage.

⚠ **PIÈGE DE CAPTEUR, mesuré en chemin.** Trois identifiants circulent et deux portent le même
nom : `combatSnapshot.units[].entityId` vaut les MÊMES `77..95` que
`observeBattle.units[].squadId`, tandis qu'`observeBattle.units[].entityId` vaut `78..96` et
n'indexe **rien**. Lire par ce dernier faisait rendre « capteur muet » à un capteur vivant. Le
probe DIT désormais ce qu'il n'a pas trouvé, au lieu d'un `None` qui se lit comme une panne.

### 4.4 Non-régression

Offline : **260** tests sur 15 fichiers de la famille mouvement / téléport / burrow / stormboyz /
displace. Live : **8 fichiers**, 29 tests — dont `test_the_quickening_live`, `test_it_itches_live`,
`test_366_r1_tunneling_horror_live` (retour sur le plateau après retrait de tuiles),
`test_498r3_switch_position_gate_live` (les stand-ins de `SetUnitPositionOperation`).

## 5. Ce qui n'est PAS porté, nommément

* **G7 / `IsTilePendingDrafting`** — pas de phase de drafting côté runner. PERMISSIF.
* **Le multi-pieds** — G2 et G4 bouclent sur `feetTiles` ; le port ne matérialise que la main tile,
  donc G4 est structurellement inerte sur une unité multi-hex. Résidu préexistant, inchangé.
* **La branche SIMULATION d'`Execute`** (`if (IsSimulation)` juste après `GetUnitFeet`) : elle pose
  la position par le slot `0x7e` et court-circuite tout le reste, avec son propre gate
  `HasTriggeredAbility(0x5f9) || (0x4de)` pour décider si elle paie un `CalculatePaths`
  (`MoveUnitOperation$$UnitNeedsAccurateNumTilesMovedInSimulation`). Le runner ne joue jamais en
  simulation.
* **Le LOG natif** de chaque refus (`AOperation.get_Logger` + `StackDict`) : pas de canal de
  journal. La RAISON est publiée à la place (`last_abandoned`, sept valeurs distinctes).
* **`SetUnitPositionOperation$$Execute` a SES PROPRES gates**, que les stand-ins du port ne jouent
  pas : `feet.Count != position.Count` et `HasFlag(unit, 6 = Dead)`. Résidu **`#550-r4`** (même
  ligne, foyer `operations/displace.py`).

## 6. `PositionComponent+0x88` vs `+0x98` — le résidu `#462-…-r5-r2` est CONFIRMÉ, et sa cause est trouvée

La fiche disait « ils divergent ensuite par leurs remises à zéro » sans la nommer. Elle est ici :

* **Écrivains** (les deux slots, MÊME valeur) : `SetUnitPositionOperation$$SavePreviousPosition`
  (appelé par nom **et** inliné dans `$$Execute`, où il est de surcroît sauté en simulation) et
  `RemoveUnitFromTilesOperation$$Execute` (étape 6).
* **Remise à zéro des DEUX** : `ResetPreviousPositionBehaviour$$Execute` — un seul call-site dans
  tout le binaire, `SwornProtector_ProtectAbility$$CreateBehaviour`.
* **Remise à zéro de `+0x98` SEUL** : `IdunBattle.Operations.StartTurnOperation$$Execute`, dans sa
  seconde boucle (`comp.<+0x98> = comp.<+0xa0> = 0` pour chaque unité du pool). ⇐ **LA cause.**

`+0x98` est donc « position précédente **CE TOUR** » et `+0x88` « position précédente » tout court.
Le seul lecteur de `+0x98` est `EntityExtensions$$GetPreviousPositionThisTurn`, dont l'**unique**
appelant de code est `MoveUnitOperation$$Execute` (étape E1) — c'est le fallback de
`movementStartPosition` quand l'unité est HORS PLATEAU, et il fait basculer `CalculatePaths` de la
branche dégénérée `[endTile, endTile]` vers un vrai chemin de VOL depuis la tuile quittée.

E1 est porté (`_movement_start_position`), mais son second bras est **structurellement
inatteignable** : le port n'a qu'un champ (`PositionComponent.previous`), et le retrait du plateau
(`set_unit_feet(uid, [])`) **supprime la `PositionComponent`**, donc `previous` avec elle. Fermer
exige, hors de mon foyer : un second champ dans `runner/components.py` (écrit par
`save_previous_position`, survivant au retrait de plateau) et son effacement dans
`turnflow`/`StartTurnOperation`.

## 7. `#448-r1-r1-r1-r1-r1` — la règle de départage EST lue ; ce qui ne l'est pas, c'est la FILE

```csharp
if (!costs.ContainsKey(n) || newCost < costs[n].cost) { pq.Enqueue(...); costs[n] = (tile, newCost); }
```

`<` **STRICT**, sur le **COÛT SEUL**, sans aucun terme de longueur : à coût égal le natif garde le
parent déjà inscrit, c'est-à-dire le PREMIER trouvé. La moitié réellement illisible est l'ordre de
sortie de la `idun.shared.collections.PriorityQueue` entre priorités égales.

Le port compare `(coût, nœuds)` — une règle que le natif n'a pas. **MESURÉE INERTE** :
`probe_448r1r1r1r1r1_departage_cout_egal.py`, 60 boards, **18 200 paires joignables**, avec le coût
RÉEL du `WalkPathfinder` (le seul régime non uniforme que le port atteigne) → **0 divergence** de
coût, **0** de nœuds. Non corrigée, et la raison est écrite : gain mesuré nul, risque non nul (le
nombre de nœuds est l'entrée de `movementSteps`, confronté live par #448-r1-r1-r1).

## 8. `#550-r3` — domaine TUILE vs domaine UNITÉ : CONFIRMÉ, et deux régimes de plus

`UnitsByTeamSelector$$CountOrAdd` lu verbatim : il résout l'occupant
(`GetUnitOrMachine(entity)`) pour le TEST `IsFriend`, puis **`result.Add(entity)`** — l'entité
SOURCE. `Enemies(<tuiles>)` rend donc des TUILES. Le port insère un `Units(...)` explicite.

Écart de REPRÉSENTATION, comme la fiche le disait — mais elle nommait **un seul** régime divergent
(le multi-hex). Il y en a **trois** :

1. **multi-hex** : `Tiles(<unité>)` rend l'empreinte ENTIÈRE, là où le natif garde les seules
   tuiles intersectées ;
2. **DOUBLONS** : deux tuiles du même occupant produisent DEUX entrées natives et **une** seule
   après `Units(...)` — tout `Count(Enemies(<tuiles>))` en domaine tuile diverge alors ;
3. **`GetUnitOrMachine`** : le natif accepte une MACHINE OF WAR comme occupant qualifiant.

Aucun n'est atteignable sur `1121 ItItches` (`IsDisplaceable` refuse `BigTarget`). Foyer
`entities/selectors/units.py`, hors de ma tranche : **RAPPORTÉ**, non édité.

## 9. `#462-…-r5-r3` — `allowSteppable` par call-site : la lecture INVERSE le résidu

`CanAddUnitTileSelector$$Select` calcule `allowSteppable = !this.<+0x28>.ShouldTrigger(entities, 0x20)`.
Les **trois** surcharges de `DSLSelectors$$CanAddUnit` construisent le même sélecteur
`(state, tiles, parent, trigger)` :

| surcharge | xrefs | `parent` | `trigger` |
|---|---|---|---|
| `CanAddUnit(tiles)` | **123** | un sélecteur d'unité par DÉFAUT construit sur place | `<contexte partagé>.<+0x88>.<+0x48>`, **en dur** |
| `CanAddUnit(tiles, isSteppable)` | 19 | idem | celui de l'appelant |
| `CanAddUnit(tiles, parent, isSteppable)` | 5 | celui de l'appelant | celui de l'appelant |

Le littéral de slot `+0x48` est **le même** que celui que #550 a mesuré sur le call-site d'`ItItches`
et identifié comme `op_LogicalNot(YesTrigger)` ⇒ `ShouldTrigger` faux ⇒ **`allowSteppable = TRUE`**.

⇒ si l'identification tient, **123 call-sites sur 147 passent `allowSteppable = TRUE` en dur**, et
le port — dont le défaut est `allow_steppable=False` — y est **RESTRICTIF** : il refuse une tuile
occupée par un `Steppable` que le natif accepte. Le résidu annonçait le risque au futur (« le jour
où l'un d'eux passera le trigger complémentaire ») ; la lecture le met au **présent**, et sur la
grande majorité des sites.

⚠ **RESTE À CONFIRMER, et je le dis plutôt que de le supposer acquis** : que
`<contexte partagé>.<+0x88>` soit bien l'instance `DSLTriggers`. Confirmation exécutable : relever
le 5e argument du ctor aux trois surcharges et le confronter au `DSLTriggers$$.ctor`. Foyer
`entities/selectors/tiles.py` — hors de ma tranche.

## 10. Reproduction

    python scripts/python/probe_448r1r1r2r2r1_gates_amont.py --offline
    python scripts/python/probe_448r1r1r2r2r1_gates_amont.py --mutants
    python scripts/python/probe_448r1r1r2r2r1_gates_amont.py --live --board MC1_67 --seed 777
    python scripts/python/probe_448r1r1r1r1r1_departage_cout_egal.py --boards 60
    python -m pytest scripts/python/tests/engine/runner/test_448_r1_r1_r2_r2_r1_gates_amont_offline.py
    python -m pytest scripts/python/tests/engine/runner/test_448_r1_r1_r2_r2_r1_gates_amont_live.py
