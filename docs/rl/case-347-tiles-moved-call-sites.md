# case-347 — les 4 call-sites natifs de `RecordTilesMoved`

Résidu `#335-r1`. #335/#340 avaient porté 1 call-site sur 4 (`MoveUnitOperation$$Execute`).
Ce cas traite les 3 autres.

## 1. Le recensement, lu au décompilé (`rnca9r7q6c`)

`list_xrefs` sur `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved` — **4 appelants**, dont
2 dans le même `MoveUnitOperation$$Execute` (branche SIMULATION et branche RÉELLE) :

| appelant | quantité enregistrée | déjà porté ? |
|---|---|---|
| `IdunBattle.Operations.MoveUnitOperation$$Execute` (×2) | `BattleQuery.GetNumTilesMoved(connectedPath)` = **longueur de CHEMIN** | #335 |
| `IdunBattle.Operations.DisplaceUnitOperation$$AddTilesMoved` | `BattleQuery.GetDistance(previousTiles, [dest])` = **distance HEX** | ce cas |
| `IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition` | `BattleQuery.GetDistance(tileAvant, tileApres)` = **distance HEX** | ce cas |

**Le fait qui structure tout** : les 2 call-sites manquants comptent en **distance hexagonale**,
pas en longueur de chemin. `BattleQuery$$GetDistance` (les 4 surcharges) délègue au slot d'interface
9/10/0xb de `IdunBattle.Core.Services.MovementQuery$$GetDistance`, dont le corps est
`min over (a,b) of CubeCoordinate.Distance(a, b)` — aucun pathfinding, aucun contournement
d'obstacle. Le discriminant « hex 3 → 4 tuiles de chemin » de #335 **ne s'applique donc pas** à ces
deux-là : c'est l'inverse qui est vrai, un port qui y compterait en chemin serait faux.

## 2. `AddTilesMoved` — le gate qui l'éteint presque partout

```csharp
// IdunBattle.Operations.DisplaceUnitOperation$$AddTilesMoved
if (options.recordTilesMoved /* +0x10 */) {
    if (!UnitExtensions.IsEnemy(caster, target, state)) {
        n = battleQuery.GetDistance(previousTiles, TExtensions.ToList(tileToDisplace));
        UnitExtensions.RecordTilesMoved(target, n, state);
    }
}
```

`options+0x10` est recopié depuis `DisplaceUnitBehaviourOptions+0x1c` par
`IdunBattle.Entities.Behaviours.DisplaceUnitBehaviour$$Execute`. Balayage **exhaustif** des 8
constructeurs de `DisplaceUnitBehaviour` (xrefs de son `.ctor`) :

| feuille DSL | `DisplaceDirection` | `+0x1c` = enregistre |
|---|---|---|
| `DSLBehaviors$$PushUnit` | 0 Push | **non** |
| `DSLBehaviors$$PushAwayFromBlacklistTiles` | 1 | **non** |
| `DSLBehaviors$$PushToPrioritizedTiles` | 2 | **non** |
| `DSLBehaviors$$DisplaceUnitInAdjacentDirection` | 3 AdjacentVector | **non** |
| `DSLBehaviors$$DisplaceUnit` | 4 Direct | **non** |
| `DSLBehaviors$$SwitchPosition` | 5 SwitchPosition | **OUI** |
| `DSLBehaviors$$PullUnitOneTile` | 6 | **non** |
| `DSLBehaviors$$Teleport` | 4 Direct | **OUI** |

⇒ **le PUSH ne compte rien** : `record_tiles=False` posé par #335 sur le `MoveUnitOperation` du
push est exact, et il n'y a rien à ajouter côté push. Le piège du double comptage annoncé n'existe
pas dans ce sens-là — mais l'inverse (porter `AddTilesMoved` sans son gate) l'aurait créé.

## 3. Les deux moitiés de `SwitchPosition` ne sont PAS symétriques

`IdunBattle.Operations.DisplaceUnitOperation$$SwitchPosition` appelle `AddTilesMoved` deux fois :

```csharp
if (!deadTarget) { MoveUnit(target -> tileCaster); AddTilesMoved(caster, target, [tileTarget], tileCaster, options); }
if (!deadCaster) { MoveUnit(caster -> tileTarget); AddTilesMoved(caster, caster,  [tileCaster], tileTarget, options); }
```

Le second passe `target = caster` : `IsEnemy(caster, caster)` est **toujours faux**, donc
**le caster enregistre TOUJOURS** sa distance. La cible, elle, n'enregistre que si elle est
**amie** du caster — ce qui est le cas du seul consommateur porté, `SorcerousFacade`, dont le
ciblage est `TargetIsFriendly` + trait `Psyker` : les **deux** unités sont créditées.

## 4. `SetRevivePosition` — le 4e call-site

```csharp
mainTile = GetMainTile(unit)                       // AVANT toute écriture de position
if (!revivePosition.HasValue) return;              // revive IN-PLACE -> rien
... MoveUnit(unit, pos) ; KillSteppableUnits(...)
if (mainTile != null && revivePosition.Value.MainTile != null)
    RecordTilesMoved(unit, GetDistance(mainTile, revivePosition.Value.MainTile), state)
```

Rang natif : entre `KillSteppableUnits` et la construction des `AbilityEntities`/les deux events de
position. Seul poseur non nul de `revivePosition` dans le build :
`IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateTargetTriggerBehaviour`.

## 5. Le port

| pièce | fichier |
|---|---|
| `MovementQuery$$GetDistance` (distance hex min entre deux ensembles) | `engine/battle_query.py::get_distance` |
| `DisplaceUnitOperation$$AddTilesMoved` + `UnitExtensions$$IsEnemy` | `engine/runner/operations/displace.py::_add_tiles_moved` / `_is_enemy` |
| le gate `DisplaceUnitBehaviourOptions+0x1c` | `SwitchPositionOperation(record_tiles=True)` / `DisplaceUnitOperation(record_tiles=False)` |
| le comptage du revive | `engine/runner/operations/revive.py::_set_revive_position` |

## 6. Ce qui n'est PAS confronté live, et pourquoi

**Aucun des trois mécanismes n'a de lecteur du compteur atteignable.** Verdict : port fidèle au
décompilé, **NON CONFRONTÉ**. Ce qui a été essayé :

* le capteur direct `actorStats.tilesMovedThisTurn` (livré par #340, `rpc-snapshot.ts`) **n'est pas
  déployé** : le hook actif publie `{entityId, totalAttacksMade, totalTurnsWithAttacksMade}` et
  rien d'autre. Une **réinjection** le rendrait mesurable — c'est la seule pièce manquante ;
* la voie indirecte de #335 (le dégât de `ModifiedExoarmour_ExtraDmg`) exige que l'unité **déplacée**
  soit `votanChampion`. Or `SorcerousFacade` — seul porteur de `SwitchPosition` — exige une cible
  **Psyker**, que Kimm n'est pas (`Hero`, `PrioritisedEfficiency`, `Unstoppable`) ; le `Teleport` DSL
  n'a qu'un porteur (`ExemplarOfTheKauyon`, `tauShadowsun`) et téléporte le **caster** ; le revive à
  position n'existe que via le `GhostEffect` de `thousTerminator`, qui ressuscite son propre porteur.
  Les trois autres consommateurs de `DSLFormulas$$TilesMovedThisTurn` (`EmpyricAmbush`/`eldarLhykhis`,
  `SmashaEad`/`orksNob`, `MastersOfManoeuvre`/`darkaStormSpeeder`) ne sont pas Psyker non plus ;
* faire subir un **push** à Kimm (test négatif du gate) est monté mais inexploitable : un push
  n'arrive que pendant le tour adverse, et `EndTurnOperation` remet `+0xf0` à 0 **inconditionnellement**
  avant que Kimm puisse attaquer.

Ce qui **est** mesuré (`probe_347_tiles_moved_call_sites.py`, MC1_67/909, `gap=3`) : le cast 1100
échange bien les deux tuiles LIVE (`(1,0)↔(0,2)`, distance hex 3), le port reproduit les positions
à l'identique, et il crédite **3 à chacune des deux unités**. Le probe **dit** que le compteur natif
n'est pas mesuré au lieu de rendre un zéro.

## 7. Gardes (`tests/engine/runner/test_347_tiles_moved_call_sites_offline.py`, 12 tests)

Offline et déterministes, parce que c'est le seul régime disponible. Deux mutations adversariales,
**vues rouges** :

| mutation | rouges |
|---|---|
| gate `record_tiles` (`+0x1c`) neutralisé | 2 (`..._is_off_without_the_options_gate`, `switch_records_nothing_without_the_options_gate`) |
| gate `!IsEnemy` neutralisé | 2 (`..._refuses_an_enemy_target`, `switch_credits_only_the_caster_against_an_enemy`) |

Non-régression rejouée : `test_sorcerous_facade_combat_live` + `test_thunderous_assault_push_live`
(11 passed) · `test_tiles_moved_combat_live` + `test_tiles_moved_prediction_live` (16 passed) ·
`test_ghost_revive_live` + `test_revive_cancels_death_events_live` (8 passed) ·
`probe_181` (98/98, 0 manquante) · `probe_120` étape 0 · `probe_273 --only-scan`.

## 8. Résidus OUVERTS

* **`#347-r1` — le lift-off de `TheQuickening` n'est toujours pas facturé.** #340 le nommait comme
  un troisième item ; la RE a montré que l'explication portée était **fausse** et que la valeur
  native n'est pas déterminée par la seule géométrie du cast :
  le **lift-off** (`MoveUnit` vers une `UnitPosition` vide) **sort avant** `RecordTilesMoved` — la
  branche `Count(position) == 0 && MoveUnitOptions+0x15` de `MoveUnitOperation$$Execute` retire
  l'unité du board et retourne ; le **move-in** facture `GetNumTilesMoved(connectedPath)` avec
  `movementStartPosition = GetPreviousPositionThisTurn(unit)` (~~`UnitComponent+0x98`~~ —
  ⚠ **RECTIFICATIF #546, 2026-08-08 : le COMPOSANT est faux.** Sur `rnca9r7q6c`,
  `UnitComponent+0x98` est `PendingHit` ; les quatre `Nullable<UnitPositionId>` vivent sur
  **`IdunBattle.Entities.Components.MovementComponent`** — `TurnStartPosition@+0x78`,
  `PreviousPosition@+0x88`, `PreviousPositionThisTurn@+0x98`, `PendingPosition@+0xa8`.
  L'offset coïncide, le composant non : un capteur écrit sur la foi de cette ligne aurait lu
  `PendingHit` **sans lever**), écrit par `SetUnitPositionOperation$$SavePreviousPosition`, effacé
  par `ResetPreviousPositionBehaviour`, donc une valeur qui dépend de l'**historique de mouvement
  du tour**. Commentaire corrigé dans `abilities/loki/quickening.py`.
  **CAPTEUR DÉPLOYÉ ET CONFRONTÉ (#546, fenêtre du 2026-08-08) — le CANAL est vert, le DÉCODAGE
  est MUET.** `movementLayout` rend `componentResolved: true`, `toTileListResolved: true`, et les
  quatre offsets **résolus PAR NOM** égalent les replis décompilés (`0x78/0x88/0x98/0xa8`) : le
  rectificatif de composant ci-dessus est confirmé par une seconde voie. La transition
  DISCRIMINE — l'unité qui bouge passe `previousPositionThisTurn` de `null` à non-nul, celle qui
  ne bouge pas reste `null`. Mais `tiles` sort `null` sur les quatre champs.
  ⚠ **Et cette transition ne dit RIEN de la cause** : la disposition du `Nullable<T>` était
  SUPPOSÉE (`hasValue` à `off + 8`) alors que `frida/hooks/game/match-state.ts` a déjà mesuré
  `hasValue` EN PREMIER sur ce build — sous cette disposition, l'octet lu est l'octet bas du
  POINTEUR de liste, donc le drapeau « marche » par ACCIDENT. Correctif livré : la disposition est
  désormais **DÉRIVÉE des métadonnées**, les 16 octets bruts sont publiés, et la cause est nommée.
  Ce résidu attend donc **`#347-r3`**, pas une fenêtre de plus.
  Détail : `case-546-une-seule-fenetre-de-reinject.md` §6.3.
* **`#347-r2` — mesuré en marge, hors périmètre** : `TheQuickening` **refuse** une tuile occupée par
  un **allié** (`Attackable(Units(Target))` est vide, donc aucun `MoveOut` n'est émis pour
  l'occupant et le move-in du caster échoue sur tuile pleine) ; et `GetDynamicInvalidTargetReason`
  retire du ciblage les tuiles occupées par un **ennemi** (`movable − Enemies`). Le port, lui, prend
  « n'importe quel occupant vivant » (`_living_unit_id_on`). À qualifier séparément.
* **`sworn_protector.switch_position`** échange les `PositionComponent` en direct au lieu de passer
  par `SwitchPositionOperation` : il ne compte donc rien, et son commentaire cite un
  `DisplaceUnitBehaviour..ctor` à 8 arguments qui n'existe plus (le ctor du build en a 5). Non
  touché ici.

