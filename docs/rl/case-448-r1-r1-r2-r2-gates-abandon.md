# case-448-r1-r1-r2-r2 / -r1-r2 / -462-…-r4-r3 — `MoveUnitOperation` est une opération à ÉTAPES, et deux d'entre elles peuvent REFUSER le mouvement

Trois résidus du même foyer (`engine/runner/operations/movement.py`), tous les trois des symptômes
d'une seule réduction : le port ramenait `IdunBattle.Operations.MoveUnitOperation$$Execute` à
« poser la position finale ». Build `rnca9r7q6c`.

> **PORTÉS + CONFRONTÉS (2026-08-07).** Les deux gates d'abandon sont au rang natif, sous un
> discriminant explicite. Témoin non nul offline pour les trois items ; témoin **live** pour le gate
> d'occupation, sur deux boards, avec contrôle positif mordant. La tranche a par ailleurs trouvé
> **un port qui DÉPENDAIT de l'absence d'un des gates** — c'est le point le plus utile.

## 1. Les étages, lus VERBATIM — branche RÉELLE

```
G1..G7  IsAllowedToMove / UnitIsOnTiles / TilesAreWalkable / TilesMatchUnitFeetCount /
        IsDisallowedEmptyPosition / IsPositionReservedForOtherUnit / IsPositionReservedForDrafting
E0      isLikeFlying = IsLikeFlying(unit, options)
E1      currentPosition = GetUnitPosition(unit)
        movementStartPosition = currentPosition, ou GetPreviousPositionThisTurn si VIDE
E2      endTile = position.MainTile ; feet = GetUnitFeet(unit) ; startTile = start[0]
E3      comp.<+0xa8> = Nullable(UnitPositionId(position))          (a)
E4      SetReservation(unit, position)
E5      if (!options.<+0x12>) {
            On(0x1f = PreUnitMove)                                 (b)
            if (!TilesAreEmpty(unit, position)) { RemoveReservation ; return }      <<< GATE 1
        }
E6      ovr = comp.<+0xa8> ; comp.<+0xa8> = null                   (c)
        if (!ovr.HasValue || IsDead(unit)) { RemoveReservation ; return }
E7      if (ToUnitPosition(ovr) != position) { RemoveReservation ; options.<+0x12> = 1 ;
                                               return Execute(<nouvelle position>) }
E8      if (position.Count == 0) { <branche allowNullTargetPosition +0x15> }
E9      CalculatePaths(...) -> path, connectedPath
E10     if (path == null || path.Count == 0) { log ; RemoveReservation ; return }   <<< GATE 2
E11     steppableUnits = BattleQuery.<slot 0x8f>(position)
E12     processor.<slot 0x7e>(unit, position, false)          <- L'ÉCRITURE DE POSITION EST *ICI*
E13     log du mouvement
E14     AddMoveEvent × N (un par pas de `path`, ou un seul si `Count == 1`)
E15     KillSteppableUnits(this, unit, steppableUnits)
E16..26 UpdateCharging / SetMovedFlag(+0x11) / Add(ArrivedAtFinalTile)(+0x10) / RemoveReservation /
        movementSteps / RecordTilesMoved(+0x16) / RefreshEffects({7,null}) /
        EvaluateAfterMoveTriggers / On(0x1c) / RefreshEffects({7,null})
```

**Les deux gates tombent AVANT E12.** Ils sont **PERMISSIFS quand ils manquent** : le port bougeait
toujours — ni erreur, ni crash, donc invisible en self-play. C'est la signature exacte du gisement
« entrer au registre sans son masque de ciblage », transposée au mouvement.

## 2. `AddMoveEvent` est du canal de VUE — la moitié du résidu qui n'était PAS à porter

`IdunBattle.Operations.MoveUnitOperation$$AddMoveEvent` ne touche **aucun** composant ECS : il
construit un `Dictionary<int,int>` (`0x79` = pathTile, `0x80` = isLastTile, `0x7a..0x7f` = les
pieds 1..6) et le pousse dans `AOperation.get_Events()` par `AddStep(3, unit.Id, dict)`. Ses seules
autres opérations sont des **lectures** (`HasTrait(unit, 0x13 = Burrow)`, `IsTeleportationTile`, qui
choisissent une valeur d'enum de *visuel*). Non porté, comme le step `0x25` d'
`OverrideMovementTargetOperation` et le `Inform{0x79}` du Miss.

⇒ ce qui mordait dans `#448-r1-r1-r2-r2`, c'est la **GARDE** `path` vide — et elle exige quand même
de matérialiser `path`.

## 3. GATE 1 — `TilesAreEmpty` : le SEUL gate d'occupation de tout `Execute`

```csharp
foreach (var tile in feetTiles) {
    var content = tile.GetComponent<TileContentComponent>();
    if (!content.IsFilled())                                continue;
    if (TileExtensions.HasSteppableUnit(tile, state))       continue;
    if (TileExtensions.ContainsUnit(content, state, unit))  continue;
    logger.Log(...);  return false;
}
return true;
```

La lecture d'origine (`case-448-r1` §6.2) le décrivait comme « il mordrait si un trigger
`PreUnitMove` faisait OCCUPER la tuile d'arrivée ». **C'est plus large** : aucun des sept gates
amont ne teste l'occupation — `UnitIsOnTiles` demande « y suis-je déjà ? »,
`IsPositionReservedForOtherUnit` lit la RÉSERVATION, pas l'occupant. Le gate mord donc aussi quand
la destination était occupée **avant** le vecteur. Aucun trigger requis.

Les trois exemptions sont load-bearing : `HasSteppableUnit` (sinon un decoy bloquerait le mouvement
que `KillSteppableUnits` est là pour écraser), `ContainsUnit(self)` (multi-pieds), `!IsFilled`.

**Rang** : le gate est **DANS** le bloc `if (options.<+0x12> == 0)`, donc la RELANCE après déviation
ne le rejoue pas. C'est lu à la pile d'accolades, pas choisi.

## 4. GATE 2 — `path` vide, et ce que `CalculatePaths` fait vraiment

```csharp
if (movementStartPosition == null) throw;
if (movementStartPosition.Count == 0) { path = connectedPath = [endTile, endTile]; return; }
int movement       = GetStat(unit, 1 = Movement);
int pathfinderType = MovementQuery.GetPathfinderTypeForUnit(unit);
bool likeFlying    = MoveUnitOperation.IsLikeFlying(unit, options);
if (UnitPosition.IsEmpty(previousPosition)) pathfinderType = PathfinderType.Fly;  // 3
if (options.<+0x8>.HasValue)                pathfinderType = options.<+0x8>.Value;
Nullable<int> useTeleporter = (likeFlying && GetDistance(startTile, endTile) > movement)
                            ? movement : null;
path          = Pathfinders.GetPath(pathfinderType, unit, startTile, endTile, useTeleporter);
connectedPath = BattleQuery.GetConnectedPathTo(unit, startTile, endTile);
```

Deux points **lus, pas déduits** : l'ordre des deux écrasements (le forçage `Fly` de la position
vide vient AVANT l'override, donc **l'override gagne**) ; et la branche
`movementStartPosition.Count == 0` rend `[endTile, endTile]`, une liste **non vide** — c'est ce qui
empêche le gate de mordre sur `GhostRevive`, `EchoesFromTheWarp` et `StormboyzStrike_Fallback`,
dont le caster arrive de nulle part.

## 5. LE POINT LE PLUS UTILE — un port DÉPENDAIT de l'absence du gate

`abilities/loki/quickening.py` portait déjà, en toutes lettres :

> natif = lift-off (MoveUnit -> Null) puis MoveIn ; **MoveUnitOperation pose la position sans check
> d'occupation** -> l'echange direct (caster->target, swap->origin) rend l'etat NET identique.

Le natif RETIRE l'unité du plateau (lift-off) avant que l'autre entre ; le port COLLAPSE l'échange
en deux mouvements directs, donc le caster entre sur une tuile **encore occupée** — une géométrie
que le natif ne produit jamais. Brancher le gate sur `emit_after_move` (qui code déjà « ce
call-site mirroite `SetUnitPositionOperation` », et vaut `True` ici, à juste titre : les deux
moitiés natives sont des call-sites de `DSLBehaviors$$MoveUnit`) aurait **cassé `TheQuickening` en
silence**.

D'où un discriminant **distinct** : `enforce_native_gates` — et il a **deux** familles de porteurs à
`False`, ce qu'un seul drapeau existant ne pouvait pas exprimer :

| famille | call-sites | pourquoi |
|---|---|---|
| stand-ins de `SetUnitPositionOperation$$Execute` | `displace.py` ×5 (push/pull/switch), `behaviour.py` (fuite) | ce natif n'a NI `CalculatePaths` NI `TilesAreEmpty` — les jouer **inventerait** un refus |
| collapse assumé | `quickening.py` ×2 | le port ne reproduit pas la géométrie du lift-off |

## 6. Le montage qui ISOLE — allié, pas ennemi

Un occupant **ENNEMI** est refusé par les DEUX gates :
`IdunBattle.Entities.Pathfinding.WalkPathfinder$$UnitIsBlockedByEnemyUnit` interdit l'arête qui mène
à sa tuile, donc `CalculatePaths` rendrait `path = null` de toute façon. Monter le bras avec un
ennemi le rendrait vert **par recouvrement**, et un retrait du gate ne le ferait pas rougir.
Un **ALLIÉ** laisse passer le pathfinding : seul `TilesAreEmpty` peut alors refuser.

Trouvé en écrivant le test (le bras « relance » rougissait pour cette raison), pas prévu.
Le recouvrement est désormais **assertionné** plutôt que subi (`test_3b2`).

## 7. Mesures

### 7.1 Offline (`probe_448r1r1r2r2_gates_abandon.py --offline`, board `C4_09`)

| bras | gates ON | gates OFF (le port d'AVANT) |
|---|---|---|
| A1 destination walkable, `path = None` | reste en `(3,7)`, `abandon='path-empty'` | **se pose en `(1,2)`** |
| A2 destination occupée par un ALLIÉ | reste, `abandon='tiles-not-empty'` | **superposition** |
| A2 occupant ENNEMI, gate 1 sauté | `abandon='path-empty'` (recouvrement) | — |
| A3 exemptions Steppable / mort / vide | passe (3/3) | — |
| A4 `last_crushed` | `[{unit:2, killer:1, reason:2}]`, état identique | — |
| A5 `last_path` | `len(path) == counts[dst]` | — |
| A6 unité hors plateau | `[to, to]`, jamais d'abandon | — |

**242 boards sur 779** ont plus d'une composante connexe à la marche dans les dumps
`data/boards/` : le régime « destination walkable mais injoignable » n'est pas un cas de bord.

### 7.2 Live (`--live`, session 2, un runner par board, disposé)

| board | contrôle POSITIF | bras | natif | port SANS le gate |
|---|---|---|---|---|
| `MC1_07` | `(6,1)→(6,2)` **bouge** | `(3,7)→(2,7)` OCCUPÉE (distance 1) | **ne bouge pas** | `(2,7)` = **superposition** |
| `MC1_07` | idem | `(6,2)→(0,8)` coupée par les ennemis | **ne bouge pas** | — |
| `MC1_11` | `(0,8)→(1,8)` **bouge** | `(5,8)→(6,8)` OCCUPÉE | **ne bouge pas** | `(6,8)` = superposition |
| `C4_09` | `(2,1)→(2,2)` **bouge** | — | — | — |

Le contrôle positif est **obligatoire** : sans lui, « le natif n'a pas bougé » se lirait comme un
verdict alors que ce pourrait être un montage inerte.

⚠ **CE QUE LA MESURE LIVE N'ISOLE PAS.** `applyAction {kind:"move"}` traverse la validation d'entrée
native avant d'atteindre `MoveUnitOperation$$Execute` ; une destination occupée ou injoignable n'est
pas dans `aiMovableTiles` non plus. Le témoin établit donc la **DIRECTION** du verdict (natif ne
bouge pas / port bouge), le **décompilé** établit l'étage. Isoler l'étage exigerait une feuille DSL
dont le sélecteur peut désigner une telle tuile — résidu `#448-r1-r1-r2-r2-r1`.

⚠ **Le régime GÉOMÉTRIQUE n'existe pas sur les boards LIVE testés.** Les « îlots » des dumps
`data/boards/` ressortent **non-walkable** dans le `boardGraph` du capteur (`C4_09` : 70 tuiles /
walkable 37 live contre 62 offline), et `TilesAreWalkable` (gate G3, amont) les refuse déjà. Le
gate `path` vide est donc atteint en pratique par le blocage **dynamique** par unités ennemies —
mesuré sur `MC1_07` : 2 tuiles joignables à vide, coupées par les 5 ennemis.

## 8. Le CLIQUET, et pourquoi il est la vraie valeur du fichier de test

`tests/engine/runner/test_448_r1_r1_r2_r2_gates_abandon_offline.py` étage 6 relève **par AST** les
14 call-sites de `MoveUnitOperation` d'`engine/**` et exige que chacun DÉCLARE le natif qu'il
mirroite. Un call-site neuf qui ne se prononcerait pas rouvrirait le gisement **en silence** : rien
ne casserait, l'unité bougerait simplement là où le natif refuse. Même remède que « entrer au
registre sans son masque » : déclarer dans le même commit.

L'étage 6b vérifie que le kwarg **écrit au site** correspond à sa déclaration — un registre qui ne
regarde pas le site redeviendrait vert dès qu'on change le site sans changer la table.

## 9. Un montage qui MENTAIT, rendu visible

`test_448_r1_stormboyz_port_offline.py::_grid` déclarait `adjacency="evenq"` **et** posait
`"neighbours": []` sur chaque tuile — ce qui l'annule : `Board.neighbours_native` distingue le champ
**absent** (repli géométrique) du champ **présent et vide** (« aucun voisin », état légitime — deux
`Water` de `C1_74` sont dans ce cas). Le plateau était **entièrement déconnecté**, et rien ne le
montrait tant que le port ne calculait aucun chemin (`_num_tiles_moved` rendait `0`,
`record_tiles_moved(0)` était un no-op). Le gate `path` vide l'a fait rougir. Champ retiré.

## 10. Ce qui n'est PAS porté, nommément

* ~~**La RÉSERVATION**~~ — **PORTÉE depuis #550-r1**, et son résidu ~~**`#448-r1-r2-r1`**~~ est
  **FERMÉ** (cf. `case-462-r4b-r1-r1-r1-r1-c-r3-r1-r6-prevent-revive.md` §3). Les trois pièces
  existent : `SetReservation`, `RemoveReservation` et leur lecteur, le gate amont G6
  `IsPositionReservedForOtherUnit`. **Ce paragraphe était donc PÉRIMÉ**, et il faut le lire ainsi :
  la phrase « sans lecteur, la porter serait un no-op » a cessé d'être vraie au moment où G6 est
  entré. Ce qui reste exact, c'est la caractérisation du RÉGIME — G6 ne mord que sur un mouvement
  **imbriqué**, parce que les quatre autres poseurs (`DSLBehaviors$$Reserve` :
  `TheQuickening` ×2, `NovaBoost`, `EreWeGo`, `ItItches` ×2) retirent la réservation dans le même
  arbre. Ce régime est désormais **monté et confronté** (`probe_448r1r2r1_reservation_regime.py`,
  4/4 : témoin, refus `position-reserved`, contre-épreuve par neutralisation de `SetReservation`,
  et cycle complet).
* **Les SEPT gates amont** (`IsAllowedToMove`, `UnitIsOnTiles`, `TilesAreWalkable`,
  `TilesMatchUnitFeetCount`, `IsDisallowedEmptyPosition`, `IsPositionReservedForDrafting`) et la
  **branche `allowNullTargetPosition`** (`position.Count == 0` → retrait du plateau +
  `EvaluateAfterMoveTriggers(movementSteps = 0)`, celle du lift-off de `TheQuickening`). Résidu
  **`#448-r1-r1-r2-r2-r1`**.
* **`AddMoveEvent`** — canal de VUE, cf. §2. Comme partout ailleurs dans `operations/`.
* **Le LOG natif** de l'abandon (`AOperation.get_Logger` + un `StackDict` à trois entrées) : le
  runner n'a pas de canal de journal. La RAISON est publiée à la place (`last_abandoned`).
* **Le multi-pieds** : `TilesAreEmpty` et `KillSteppableUnits` bouclent sur `feetTiles`, le port ne
  matérialise que la main tile. Résidu préexistant, inchangé.
* **`useTeleporter`** : argument mort sur les deux routes lues (`#448-r1-r1-r1-r1` §4), non
  re-vérifié ailleurs. Préexistant.

## 11. Reproduction

    python scripts/python/probe_448r1r1r2r2_gates_abandon.py --offline
    python scripts/python/probe_448r1r1r2r2_gates_abandon.py --live --boards MC1_07,MC1_11
    python -m pytest scripts/python/tests/engine/runner/test_448_r1_r1_r2_r2_gates_abandon_offline.py
