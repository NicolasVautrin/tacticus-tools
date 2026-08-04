# #433-r4-r2-r1-r2-r2 — les gardes « ami » de la ligne de vue

**Verdict : FERMÉ.** Les deux gardes sont portées et alimentées ; le seul écart **RESTRICTIF** de
tout le cas `#433-r4-r2` passe de **1 faux négatif à 0**, avec deux témoins et une contre-épreuve
« même tuile, occupant échangé » qui excluent l'accord dégénéré.

Deux résultats de méthode valent autant que le port :

* la lecture héritée était **FAUSSE** — `EntityExtensions$$GetCurrentPlayer` ne résout **pas**
  l'occupant d'une tuile, et les deux gardes ne lisent donc **pas la même chose** ;
* la donnée **n'était pas manquante au capteur** : `observeBattle.units[].teamId` + `col`/`row`
  la publie déjà. Comme `isWall` en `#433-r4-r2-r1-r2`, elle était **jetée par le port**.
  **Aucune réinjection.**

## 1. Les deux gardes, LUES — et leur ASYMÉTRIE

```
TargetingQuery.u003Cu003Ec__DisplayClass34_0$$u003CGetPossibleTargetsForOptionsu003Eb__1(target)
    if (UnitExtensions.IsFriend(target, ctx.caster, ctx.query.state))   return false;   # GARDE 1
    return ctx.query.GetTilesObscuringTerrain(...).Count > 0;

TargetingQuery$$GetTilesObscuringTerrain(caster, casterTiles, target, options)
    if (!config.<EnableObscuringTerrain @+0x10>)                              return empty;
    if (UnitExtensions.IsFriendOrHasFriendlyUnitOnIt(target, caster, state))  return empty;  # GARDE 2
```

Les deux comparent un `TeamId`, et **c'est là que s'arrête la ressemblance**.

### Garde 1 — `UnitExtensions$$IsFriend(unit, other, state)`

```
p1 = EntityExtensions.GetCurrentPlayer(unit,  state) ;  t1 = p1 ? p1.<PlayerComponent @+0x20>.<+0x24> : 0
p2 = EntityExtensions.GetCurrentPlayer(other, state) ;  t2 = p2 ? p2.<PlayerComponent @+0x20>.<+0x24> : 0
return t1 == t2
```

`EntityExtensions$$GetCurrentPlayer` ne branche que sur **trois** classes — `PlayerEntity` (rend
`this`), `FootEntity` (`GetUnit` puis récursion) et `UnitEntity` (`OwnerComponent+0x20`) — puis
retombe sur un `TryGetComponent<OwnerComponent>` que la **`TileEntity` ne porte pas**.

⇒ **sur une TUILE, `GetCurrentPlayer` rend `null`, donc `0`.** La garde vaut
`TeamId(caster) == Environment(0)` : une **constante du caster**, pas une propriété de la tuile.

> ⚠ **RÉFUTATION.** La fiche `#433-r4-r2-r1-r2` écrivait : « `GetCurrentPlayer` sur une tuile résout
> l'unité qui l'OCCUPE (branche `UnitExtensions$$GetUnit` du décompilé) ». Cette branche est celle
> de **`FootEntity`**. L'identité des quatre classes est établie par leurs **xrefs**, pas à l'œil :
> `Blueprints$$UnitFoot` / `FootEntity$$Copy` pour celle qu'on prenait pour la tuile,
> `Blueprints$$Tile` / `TileEntity$$Copy` pour la vraie, `Blueprints$$Unit` / `UnitEntity$$Copy` et
> `Blueprints$$Player` / `PlayerEntity$$Copy` pour les deux autres. Le port passait `False` — juste
> dans nos runners, mais **par accident**.

`PlayerComponent+0x24` **est** le `TeamId` : `StateExtensions.u003CGetTeamPlayersu003Ed__39$$MoveNext`
filtre les joueurs par exactement ce champ contre son argument `teamId`, et
`Blueprints$$Player` pose le `PlayerComponent` à `PlayerEntity+0x20`. L'enum
`IdunBattle.Core.TeamId` vaut `0=Environment, 1=Team1_Default, 2=Team2_DefaultEnemy, 3=Team3`.

**Le zéro est une COÏNCIDENCE piégeuse** : c'est à la fois la valeur de repli d'un
`GetCurrentPlayer` muet **et** une équipe réelle. Nos runners déclarent
`Players = {p1: 1, p2: 2, env: 0}` avec **zéro unité** côté Environment — la garde y est donc
**INERTE**, mais pas par nature : un caster d'équipe Environment désactiverait tout l'étage.

### Garde 2 — `UnitExtensions$$IsFriendOrHasFriendlyUnitOnIt(entity, unit, state)`

```
if (entity == null || unit == null)            return false;
if (!EntityExtensions.IsUnit(unit))            return false;      # inline : FUN_180002590(1, <Entity>, unit) == 1
u = UnitExtensions.GetUnit(entity, state);                        # TESTE TileEntity -> l'OCCUPANT
if (u == null)                                 return false;
return teamOf(GetCurrentPlayer(u)) == teamOf(GetCurrentPlayer(unit));
```

`UnitExtensions$$GetUnit`, lui, **teste bien `TileEntity`** (`TileContentComponent+0x38`,
`IsFilled`) et résout l'occupant. Cette garde vaut donc « la tuile porte une unité de la **même
équipe** que le caster » — et **c'est elle qui mord**.

Le premier gate `IsUnit(caster)` est constant à vrai pour notre consommateur (le caster est
toujours une unité).

## 2. Ce qui est porté

* **`engine/services/targeting_query.friend_gates_for_tile_target(caster_team, occupant_team)`** —
  foyer UNIQUE des deux gardes, rendant le couple `(target_is_friend,
  target_is_friend_or_has_friendly_unit)` que le mirror prenait déjà en paramètres. `TEAM_ENVIRONMENT
  = 0` y est nommé et cité.
* **`engine/services/ability_range`** — `_obscured`, `_ability_covers_tile` et
  `is_tile_in_range_of_any_ability` acceptent `caster_team` / `team_by_pos` et les transmettent aux
  **deux** termes de l'union (attaque normale **et** chaque ability).
* **`engine/playbook/noncomparable/_base.occupant_team_by_pos(ctx)`** — `{(col,row): TeamId}` de
  l'occupant **VIVANT**, dérivé de `ctx.obs_units`. Le filtre `isDead` est LU : le natif passe par
  `TileContentComponent$$IsFilled`, et une dépouille ne remplit plus sa tuile — c'est aussi
  pourquoi la source n'est **pas** `decisionView`, qui garde les morts.
* **`early_warning_override`** — `caster_team` est lu sur la tuile de l'ennemi lui-même
  (`team_by_pos[ep]`) : la même carte sert aux deux bouts de la comparaison.

**Zéro modification de câblage** : `NCContext.obs_units` était déjà transmis par
`NonComparableGenerator.generate`.

## 3. L'ORACLE — et pourquoi ce n'est PAS celui de #568/#574

`ncEvaluate --sweep` ne balaie que `GetCurrentAndMovablePositionsFor(caster du playbook)` : des
tuiles **libres**, plus l'origine — occupée par une unité **ennemie** du caster natif. Aucune ne
peut porter un **allié** du caster : ce montage est **structurellement aveugle** à la garde 2.

On prend donc l'autre entrée du **même slot `0xe`** : `aiMovableTiles {threat: true}` invoque
`AttackQuery$$GetAllTilesInAbilityRange(unit, moveTiles, true)`, et sa zone couvre **tout le
plateau, tuiles occupées comprises**.

Ce que cela change au modèle, et c'est lu : `casterTiles` y est le **movable set**, pas le
singleton `{GetMainTile}`. La surcharge LISTE de `MovementQuery$$GetTilesObscuringTerrain`
**intersecte** alors les ensembles par tuile de départ — mirror déjà porté (#444), consommé tel
quel.

**Trois mesures qui gouvernent le montage, et qu'on ne devine pas :**

| levier | mesure (2026-08-04) |
|---|---|
| movable set COMPLET (`Movement` nominal) | **0** tuile obscurcie sur tout le plateau — l'intersection annule tout |
| `Movement = 0` | movable set **vide** ⇒ `GetAllTilesInAbilityRange` rend une zone **vide** |
| `overrideRange = 1` à la MESURE | movable set = les voisines ; utilisable |

D'où le levier retenu : **`MovementOptions.OverrideRange`**, passé au RPC *au moment de la mesure*.
Il **découple** le mouvement nécessaire pour PLACER les unités (`--unit-stat Movement=8`) de la
portée utilisée pour MESURER — ce qu'un `--unit-stat` seul ne permet pas.

Le montage est **forcé, pas subi** : `_pick_caster_tile` choisit la tuile du greffon qui maximise
le nombre de tuiles obscurcies (le port ne sert qu'à **choisir** ; le verdict reste la partition
native, relue sur l'état FINAL).

## 4. La CONFRONTATION — trois verdicts natifs distincts, même terrain

Board `MC1_67`, `1161 TwinSmartMissileSystem` (`UseWholeBoard`, aucun `AllowObscuredTarget*` ⇒
`ObscuringType = 6`, aucun `TargetMatchesDynamicRule` ⇒ le 3ᵉ prédicat n'est même pas construit)
greffée **seule** sur `custoBladeChampion` (arme de **mêlée**, et le prédicat est structurellement
muet à `d = 1` — l'arme ne peut donc pas masquer la mesure). Caster en `(0,6)`, `moveTiles` = 4.

| tuile | état | verdict NATIF |
|---|---|---|
| `T_ami (6,2)` | obscurcie, occupée par un **allié** (team 2 = celle du caster) | **ACCEPTE** |
| `T_ennemi (1,2)` | obscurcie, occupée par un **ennemi** (team 1) | REFUSE |
| `T_vide (2,2)`, `(5,2)` | obscurcies, **vides** | REFUSE |

Les deux derniers sont les **témoins** : ce n'est ni « une tuile occupée est exemptée » (T_ennemi
le réfute), ni « l'étage ne mord pas sur ce terrain » (T_vide le réfute). Il reste **l'amitié**.

**Écart chiffré, sur les 62 tuiles marchables :**

| | faux positifs | faux négatifs |
|---|---|---|
| port AVANT (gardes non alimentées) | 0 | **1** — `(6,2)` |
| port APRÈS | **0** | **0** |

### La CONTRE-ÉPREUVE : la même tuile, l'occupant échangé

L'allié est sorti de `(6,2)` vers une tuile non obscurcie, l'ennemi y est amené, et la zone est
relue. **Même tuile, même caster, même movable set, même géométrie** (`obscurcie = True` dans les
deux passes) — seul l'occupant change d'équipe :

```
occupant team 2 (allié du caster)  ->  natif ACCEPTE
occupant team 1 (ennemi)           ->  natif REFUSE
```

C'est le natif comparé à **lui-même** : aucune explication par le terrain ni par la distance ne
survit.

## 5. Ce qui n'est PAS couvert

* **Le régime de la garde 2 dans le consommateur ACTUEL est INATTEIGNABLE, et c'est mesuré.**
  `EarlyWarningOverridePlaybook` (branche A) est le seul appelant de
  `is_tile_in_range_of_any_ability`, et il n'interroge que des tuiles du sweep : libres, ou
  l'origine (occupée par un ennemi du caster natif). L'écart y vaut donc **0 avant comme après**.
  Le port est juste **à son foyer** ; il le restera pour tout consommateur futur, et c'est ce que
  la mesure du §4 établit — sur l'autre entrée du même slot.
  ⚠ Une porte étroite subsiste : une tuile portant une unité **`Steppable`** est « libre » au sens
  d'`IsFreeTile`. Les porteurs (`astarSmnHaywireMine`, `genesSmnDecoy`, les `powup*`/`LootObj_*`
  npc) ne sont pas spawnables au rank 17 (`--a-units` les refuse, injection catalogue comprise) :
  **non confronté**, et sans conséquence tant qu'aucun summon steppable n'entre en jeu.
* **La garde 1 est INERTE dans nos runners** (aucun caster d'équipe Environment) — portée pour
  ce qu'elle est, jamais exercée live.
* **Les MACHINES OF WAR** sont hors du canal `observeBattle.units` (elles vivent dans `.mows`).
  Une tuile qu'une MoW occupe est donc vue VIDE : le port retire là où le natif pourrait garder.
  Même sens d'écart que celui qui préexistait.
* **Le bridge OFFLINE** (`state_bridge._obs_units`) rend une ligne par unité — la tuile
  **principale** seulement — là où le live projette **un pied par ligne** et couvre l'empreinte
  complète. Écart sur les seules unités multi-hex.
* **La walkability** : le natif retire les tuiles non marchables à un étage **AMONT** de la ligne
  de vue (mesuré ici : **0** non-marchable dans la zone native, sur 1). Le sweep du probe s'y
  restreint — sinon il compterait comme écart de cette tranche un écart qui n'est pas le sien.
  **FERMÉ depuis** : l'étage est `TargetingQuery$$GetTilesInRange` (`RemoveAll` interne, gaté par
  `AllowUnwalkableTargetTile`), porté et confronté sur quatre boards —
  `docs/rl/case-433-r4-r2-r1-r2-r2-r1-walkability.md`.
* **La généralisation par BOARD est bloquée, et c'est chiffré** : sur `C6_17` et `C1_04`, la
  meilleure position de caster rend **0** tuile obscurcie une fois l'intersection appliquée sur le
  movable set. La contre-épreuve « occupant échangé » remplace ce contrôle, et le remplace
  avantageusement : elle fait varier **la seule variable en cause**.

## 6. Validation

* **OFFLINE** — `tests/engine/test_433_r4_r2_r1_r2_r2_friend_gates_offline.py` : **13 passed**
  (asymétrie des deux gardes sur les 20 couples d'équipes, `TeamId.Environment`, court-circuit de
  `IsFriend` avant la géométrie, annulation de l'ensemble d'obscurcissement, câblage des deux
  termes de l'union, dégradation du canal muet, filtre des morts).
* **LIVE** — `tests/engine/test_433_r4_r2_r1_r2_r2_friend_gates_live.py` : **8 passed**.
* **NON-RÉGRESSION** — `test_433_r4_r2_r1_r2_line_of_sight_live.py` **7**,
  `test_356_noncomparable_oracle_live.py` **14**, `test_433_r4_r2_r1_ability_range_live.py` **6**,
  `test_433_r4_r2_adjacency_foyer_live.py` **7**,
  `test_433_r4_r2_r1_r1_a_whole_board_gates_live.py` **3**, et **40 passed** offline sur les deux
  fichiers de la lignée.
  ⚠ Le dernier a d'abord rougi sur `montage REFUSE : caster ou ennemi absent du decisionView`
  pendant une passe à **5 runners simultanés**, puis est passé vert rejoué seul : contention du
  budget partagé, pas une régression.
* **BANQUE** — `scripts/ratchets.ps1 -Since origin/master`, relevé daté dans le rapport de PR.
