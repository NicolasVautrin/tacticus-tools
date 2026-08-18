# case-589-r2-r1-r1 — la destination EST marchable, et ce n'est pas ce qui ferme le régime

Tranche `[opus]` du 2026-08-18. Quatre items d'un même axe MOUVEMENT ont été soumis ensemble ;
celui-ci est le seul qui demandait un travail de RE. Les trois autres sont traités en §5.

## 1. Ce que le résidu demandait, et pourquoi la réponse ne pouvait pas venir d'un recensement

`#589-r2-r1` a posé une **levée** (`BeelineSansChemin`) là où le port avalait l'absence de chemin
beeline, et l'a déclarée sûre parce qu'« aucun mouvement légal » ne l'atteint sur les 779 boards.
Le résidu `#589-r2-r1-r1` contestait l'hypothèse : *les deux extrémités du mouvement sont
marchables* n'était établi que pour le mouvement JOUEUR, pas pour la route DSL `MoveUnit`/`FlyUnit`,
dont la destination sort d'un **sélecteur de tuiles**. Ce qui fermerait, écrivait-il : « recenser,
pour chacun de ces call-sites, si le sélecteur peut rendre une tuile NON MARCHABLE ».

**Ce recensement est inutile — un gate le domine.** La question ne se pose pas au niveau du
sélecteur, parce qu'entre le sélecteur et `GetConnectedPathTo` il y a un refus inconditionnel.

## 2. La chaîne, LUE de bout en bout

`IdunBattle.Entities.Behaviours.MoveUnitBehaviour$$Execute` résout ses deux sélecteurs (sujet,
tuiles) puis appelle le slot `MoveUnit` du `IOperationProcessor` (idx `0x65`). Il ne filtre rien
lui-même. En aval :

| étage | ce qui est lu |
|---|---|
| `IdunBattle.Operations.MoveUnitOperation$$Execute` | **sept gates inconditionnels**, dans l'ordre ; le 3ᵉ est `$$TilesAreWalkable(unit, position)` où `position` est la **DESTINATION** |
| `IdunBattle.Operations.MoveUnitOperation$$TilesAreWalkable` | boucle sur l'empreinte, exige le slot `IBattleQuery` `0xa1` (`IdunBattle.Core.Services.BattleQuery$$IsWalkableTile`) sur CHAQUE tuile, sinon log + `return false` |
| `IdunBattle.Operations.MoveUnitOperation$$CalculatePaths` | 9ᵉ out-param `connectedPath` = slot `IBattleQuery` `0x15` |
| `IdunBattle.Core.Services.BattleQuery$$GetConnectedPathTo` | délègue au slot `IMovementQuery` `8` |
| `IdunBattle.Core.Services.MovementQuery$$GetConnectedPathTo` | la re-densification par beeline, et son déréférencement nu |

Le gate tombe **avant** `IsLikeFlying`, **avant** `GetUnitPosition`, **avant** `SetReservation` —
donc avant toute mutation et avant `CalculatePaths`. Aucune option ne le contourne (`options+0x13`
ne gouverne que `IsAllowedToMove`).

⇒ **la destination d'un `MoveUnit`/`FlyUnit` DSL est marchable, quel que soit le sélecteur qui l'a
produite.** Les quatre producteurs d'override recensés par `#448-r1-r1-r2`
(`IdunBattleLogic.Entities.DSLBehaviors$$FlyUnit`,
`IdunBattleLogic.Entities.Abilities.Active.Loki.TreasonOfTzeentchAbility$$ExecuteBehaviour`,
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.NovaBoost_AttackAbility$$CreateBehaviour`, la
lambda de `Visit(CheatMoveUnitMessage)`) y passent tous — un gate en aval du sélecteur rend leur
énumération sans objet.

### 2 bis. La prémisse écrite était FAUSSE, et elle a survécu à deux fiches

`#589-r2-r1` écrivait — dans la docstring de `BeelineSansChemin`, dans `mesurer_regime` et dans le
cliquet — que « `MovementQuery$$GetConnectedPathTo` n'est appelé que par
`IdunBattle.Entities.UnitExtensions$$RecordTilesMoved` ». C'est faux :
`RecordTilesMoved(unit, tiles, state)` prend un **entier** — son corps entier est
`if (n < 1) return; comp[+0xec] += n; comp[+0xf0] += n;` — il ne calcule aucun chemin.

Appelants **exhaustifs** du slot `0x15` (relevé littéral sur le décompilé du binaire entier) :

* `IdunBattle.Operations.MoveUnitOperation$$CalculatePaths` — la route COMBAT ;
* `IdunBattle.View.FSM.VisualBattleQuery$$GetVisualPathTo` — la route VUE, qu'aucun mirror du
  moteur ne porte.

Et `$$TilesAreWalkable` n'a **qu'un seul** appelant : `MoveUnitOperation$$Execute`.

## 3. La mesure RENVERSE l'énoncé : ce n'est pas la destination qui ferme

`mesurer_regime` ventile désormais l'étage [3] en trois hypothèses. Sur `Waves_Xenos_13` (le seul
des 779 boards à poche isolée), board DÉRIVÉ de l'entrée versionnée :

| hypothèse | sauts non recousus |
|---|---|
| aucune | **61** |
| DESTINATION marchable (le gate LU, §2) | **61** |
| DÉPART marchable | **0** |
| les deux | **0** |

Les 61 sauts partent **tous** de la poche `(3, 4)`. **Le gate établi par lecture ne retire donc
aucun cas** : ce qui ferme le régime est la tuile de DÉPART, et l'énoncé du résidu visait le
mauvais côté.

Contre-épreuve jouée : rendre la poche MARCHABLE fait passer `sauts_sans_depart` de **0 à 122** et
`sauts_sans_legaux` de **0 à 122**. Le cran discrimine.

### 3 bis. Ce qui reste ouvert — `#589-r3`

Le départ est `movementStartPosition = GetUnitPosition(unit)` (ou `GetPreviousPositionThisTurn` si
vide) : la tuile où l'unité **se tient**. Elle n'a aucun gate de marchabilité propre. L'autre
écrivain de position, `IdunBattle.Operations.SetUnitPositionOperation$$Execute`, n'a que **deux**
gates, LUS : `feet.Count == position.Count` et `!HasFlag(unit, 6 = Dead)`. Rien n'y teste
`IsWalkableTile`. Ce que la mesure établit est donc **empirique** (0 sur le seul board à poche),
pas structurel.

## 4. Ce qui est livré, et pourquoi c'est exécutable

* `engine/services/movement_query.py` — la docstring de `BeelineSansChemin` porte la RE juste
  (appelants exhaustifs, gate G3, la ventilation, le renvoi vers `#589-r3`).
* `probe_589r2r1_beeline_sans_chemin.py` — `mesurer_regime` rend `sauts_sans_dest` et
  `sauts_sans_depart` ; `--only REGIME` les imprime séparément et sort en `rc=1` dès que le régime
  est atteint **sous le seul gate G3** (le critère est désormais le plus exigeant des trois).
* `tests/engine/entities/pathfinding/test_589r2r1_beeline_sans_chemin_offline.py` — deux étages
  neufs :
  * **la ventilation** (`sauts_sans_dest > 0` ASSERTIONNÉ non vide, `sauts_sans_depart == 0`) ;
    sans le non-vide, la seconde assertion deviendrait vacante ;
  * **le gate, JOUÉ** — `MoveUnitOperation` refuse une destination non marchable avec
    `last_abandoned == "tiles-not-walkable"`, et l'accepte gates éteints. Sans ce second bras,
    « ça refuse » serait compatible avec un montage où rien ne bouge jamais.

**Mutants joués.** M1 — retirer le gate G3 du port : l'étage 4 rougit (`path-empty` au lieu de
`tiles-not-walkable`). ⚠ Instructif : le mouvement reste refusé, mais par le gate `path` vide,
**en aval** de `CalculatePaths` — donc `get_connected_path_to` EST atteint. C'est ce qui rend le
gate G3 load-bearing pour cette famille et non redondant. M2 — poche marchable : `0 → 122` (§3).

## 5. Les trois autres items de la tranche

### 5.1 `#448-r1-r1-r1-r1-r2-r1` — PÉRIMÉ, le rebranchement est fait depuis le 2026-08-04

La fiche disait « aucun pathfinder n'est rebranché sur `neighbours_connectivity` ». **Faux** : le
commit `3ceb9da6` l'a fait, la case-doc `case-448-r1-r1-r1-r1-flying-tiles-moved.md` §14 le
confronte au natif (5/5 mesures discriminantes CANAL), et le cliquet qui garde le sujet **déclare
lui-même** avoir remplacé la garde de périmètre (`test_448r1r1r1r1r2_connectivity_channel_offline.py`,
lignes 93-98). Re-mesuré : les quatre routes de la famille `BasePathfinder$$AddNeighbours` passent
par `Board.base_add_neighbours` (`beeline_pathfinder.find_path`,
`ignore_terrain_pathfinder.get_path_node_counts`, `walk_pathfinder.get_reachable_levels`,
`board.walk_maps_by_pos`) ; `fly_pathfinder` lit la géométrie (override réel) et
`teleport_pathfinder` le champ hérité (son natif porte la porte).

### 5.2 `#175-r1` — PÉRIMÉ, et le site qu'il a créé ne doit PAS être rebranché

La fiche est déjà à l'état « confrontée live le 2026-08-15, reliquat = `#175-r5` (`BLOCAGE:
capteur`) ». Ce qui restait à trancher est le **jumeau en domaine POSITION** né de cette tranche,
`ignore_terrain_pathfinder.get_path_node_counts_by_pos`, seul site de la famille qui lise encore
le champ amputé. **MESURÉ, et le choix est LOAD-BEARING** :

| régime | champ amputé vs canal |
|---|---|
| `elev_by_pos` FOURNI | résultats **identiques** — le rebranchement serait inerte |
| `elev_by_pos` ABSENT | ils **divergent** ; le canal SUR-ATTEINT (il compte joignable la tuile à élévation 2 que le natif refuse) |

Le port ne peut pas rejouer la porte d'élévation sans l'élévation, alors que le champ hérité la
porte déjà (le capteur passe par `TileQuery$$IterateAdjacentTiles`). Un rebranchement « par
cohérence » ne gagnerait rien dans le premier régime et casserait le second. Cran :
`test_le_JUMEAU_EN_DOMAINE_POSITION_reste_sur_le_champ_AMPUTE_et_c_est_LOAD_BEARING`.

### 5.3 `#429-r1-r3-r1-r2-r1` — RETIRÉ, mais la fiche se trompait sur l'observable

`IdunBattle.Operations.FleeOperation$$Execute` est relu **en entier** : `On(0x33 = PreUnitFled)` →
abandon si `IsDead` → statistiques d'acteur → `RecordFlee` → `RemoveEffects(0)` →
`<slot 6 = RemoveUnit>` → `AddToPools(DefeatedUnits)` → `UnitFlag 9` → `RemoveEffects(1)` →
`On(0x34)` → `On(0x36)` → `RemoveEffects(2)` → `UnregisterEntityFromTriggers`. **Aucun appel au
slot `MoveUnit`, aucun à `SetUnitPosition`**, et rien à la place : l'unité n'est plus sur le
plateau. Le déplacement `_safest_tile` du port est donc supprimé, avec sa fonction et quatre
imports.

⚠ **La fiche annonçait « il la mute » et un retournement qui « rougit aujourd'hui ». Les deux sont
FAUX, mesuré.** Depuis `#429-r1-r3-r1-r2`, `RemoveUnitOperation` pose `UnitComponent.alive = False`
et le `MoveUnitOperation` qui suivait tombait sur le bras `IsDead` du gate d'override
(`last_abandoned == "override-unit-dead"`). La position ne bougeait donc **plus** — mais par
**accident de collapse et pour une raison fausse** : `IdunBattle.Entities.UnitExtensions$$IsDead`
teste `HasFlag(unit, 6 = Dead)`, pas `Removed`, et une enfuie garde ses PV pleins ; côté natif ce
gate ne mordrait pas.

Le cran ne pouvait donc pas porter sur la position — il aurait été vert dès le premier jour et le
serait resté après n'importe quelle régression du collapse. Il **compte les constructions de
`MoveUnitOperation`** pendant `FleeOperation.execute` (`--volet flee`) : `1 → 0`, avec témoin
non dégénéré (un `MoveUnitOperation` nu bouge bien sur le même montage). La substitution porte sur
`MoveUnitOperation.__init__`, c'est-à-dire sur la **classe** : patcher l'attribut du module
`behaviour` aurait cessé de mordre à l'instant même où l'import disparaît — un cran qui devient
vert parce que sa cible a disparu ne garde plus rien.

L'entrée correspondante de `CALL_SITES` (`test_448_r1_r1_r2_r2_gates_abandon_offline.py`) est
retirée avec le site, ce que le message de son propre cliquet exige.

## 6. Résidus

* **`#589-r3`** — rien n'établit que le DÉPART d'un mouvement soit marchable (§3 bis).
* `#175-r5` — inchangé (`BLOCAGE: capteur`).
* Le second appelant de `GetConnectedPathTo`, `IdunBattle.View.FSM.VisualBattleQuery$$GetVisualPathTo`,
  n'est porté par aucun mirror ; il n'entre dans aucune conclusion de cette tranche.
