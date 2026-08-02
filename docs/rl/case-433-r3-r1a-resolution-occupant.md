# #433-r3-r1a — la résolution d'occupant lit le `TileContentComponent`, pas la main tile

**Verdict : QUIRK PORTÉ, et l'énoncé est RÉFUTÉ DANS LES DEUX SENS.** Le périmètre re-dérivé par AST
donne **17 classes**, pas 14 : `UnitsDirectlyBehind` n'était nommé nulle part et divergeait, tandis
que **`Unobscured` divergeait sur l'axe INVERSE de celui annoncé** (le référent `from` est bien une
main tile ; c'est la CIBLE qui se lit sur toute l'empreinte). Et la RE a trouvé **un second quirk
que l'énoncé ne mentionnait pas** : le voisinage d'une entité multi-hex est l'UNION du voisinage de
tous ses pieds. Confronté LIVE sur **deux canaux natifs indépendants**.

## 1. Le périmètre, RE-MESURÉ (jamais hérité)

`probe_433_r3_r1_dsl_footprint_scan.py --step scan` (AST, fermeture transitive intra-fichier) sur
**362 fichiers** : **17 classes de nœud**, 26 sites. Confrontation aux deux listes de la fiche
précédente :

| | compte | classes |
|---|---|---|
| annoncées DIVERGENTES (fiche §7) | 14 | toutes retrouvées |
| annoncées D'ACCORD | 2 | `MovableTilesInRange`, `Tiles` |
| **hors des deux listes** | **1** | **`UnitsDirectlyBehind`** |

`UnitsDirectlyBehind` collapse sur `_pos` à **quatre** endroits (`units.py:229,230,240,258`) et son
décompilé (`IdunBattleLogic.Entities.DSLSelectors$$UnitsDirectlyBehind`) est un empilement de trois
constructions qui lisent toutes l'empreinte. Il est corrigé ici.

`CanAddUnit`, cité par la fiche comme 15ᵉ, n'apparaît plus au scan : #433-r3-r1 l'a déjà fait passer
par `_feet`.

## 2. Le foyer natif est `SelectUnit`, pas `GetUnit`

L'énoncé pointait `IdunBattle.Entities.UnitExtensions$$GetUnit`. C'en est le fond, mais **le foyer
DSL est un cran au-dessus** — et c'est lui qui unifie les 17 nœuds :

```
IdunBattle.DSL.TargetsSelector$$SelectUnit(entity, selectionType)     // surcharge ENTITE
    if (EntityExtensions.IsUnitFoot(e) || EntityExtensions.IsTile(e))
        e = UnitExtensions.GetUnit(e, state);
    return (e != null && IsUnit(e) && MatchesUnitSelectionType(e, selectionType, state)) ? e : null;
```

et `GetUnit` sur une TUILE **boucle** :

```
tcc = tile.TileContentComponent;            if (!tcc.IsFilled()) return null;
e = state.GetEntity(tcc.content);           // le contenu est une entite-PIED
// e est un FootEntity -> la surcharge PIED le re-resout en son unite proprietaire
```

Le contenu d'une tuile est bien un **pied** : `IdunBattle.Entities.Blueprints$$UnitFoot` alloue une
`IdunBattle.Core.FootEntity` par pied, et `IdunBattle.Operations.MoveUnitOperation$$UnitIsOnTiles`
lit `GetMainTile` **par pied** (`GetUnitFeet(unit)` puis `GetMainTile(foot)`). ⇒ **n'importe quel
pied résout en l'unité.**

Le consommateur DSL : `IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select` appelle, sur son
sélecteur de tuiles, `IdunBattle.DSL.TargetsSelector$$SelectAllUnits` (flag `unique == 0`) ou
`$$SelectUniqueUnits` (flag `!= 0`) — tous deux bouclent `SelectUnit` sur chaque élément.

## 3. Le second quirk, que rien n'annonçait : le VOISINAGE s'unionne sur les pieds

Les DEUX itérateurs natifs de voisinage **ouvrent par la même boucle** :

```
// BattleQuery.<IterateAdjacentTiles>d__95$$MoveNext
// BattleQuery.<IterateSurroundingTiles>d__117$$MoveNext
foreach (tile in EntityExtensions.IterateTiles(entity, state))
    foreach (t in tileQuery.Iterate<Adjacent|Surrounding>Tiles(tile, ...)) yield t;
```

⇒ `AdjacentTiles(origin)` / `SurroundingTiles(origin, r)` d'une entité multi-hex sont l'**UNION** du
voisinage de tous ses pieds, collectée dans un `OrderedSet` (dédoublonnée, première apparition
gagnante). Le port partait d'une seule tuile.

**Le piège d'exclusion, confirmé au décompilé.** La branche `includeCenter == 0` de
`IdunBattleLogic.Entities.DSLSelectors$$SurroundingTiles` est
`SurroundingTiles(origin, includeCenter: 1, ...) op_Subtraction Tiles(origin)`, et `Tiles` =
`IdunBattle.Entities.Selectors.UnitsMainTilesSelector$$Select` = `GetMainTile` **par entité**. On ne
retranche donc **qu'une tuile** : les pieds secondaires de l'origine RESTENT dans l'anneau, et une
origine multi-hex **se sélectionne elle-même**. Retrancher toute l'empreinte serait une seconde
erreur — le port ne le fait pas, et un test l'atteste.

## 4. Ce que la RE a réfuté, nœud par nœud

| nœud | ce que la fiche annonçait | ce que dit le décompilé |
|---|---|---|
| `Units`, `HasUnit` | occupant par n'importe quel pied | **confirmé** (`SelectUnit` → `GetUnit`) |
| `Adjacent*` / `Surrounding*` | union du voisinage des pieds du centre | **confirmé** (`IterateTiles` en tête des deux itérateurs) |
| `SurroundingTiles` | exclusion = main tile seule | **confirmé** (`- Tiles(origin)` = `UnitsMainTilesSelector`) |
| `UnitsOnTilesWithEffect` | vrai dès qu'UNE tuile porte l'effet | **confirmé** (`IsUnitOnTileEffectTrigger$$ShouldTrigger`, existentiel) |
| `Unobscured` | « côté cible : toutes les tuiles » | **confirmé côté CIBLE** (`TargetingQuery$$IsTargetUnitObscured` = ET sur `IterateTiles(target)`) — **mais le référent `from` est un `GetMainTile`** (`UnobscuredEntitiesSelector$$Select`), là où le port était DÉJÀ d'accord : l'élargir aurait été une régression |
| `CasterTile` / `OwnerTile` / `TargetTile` | « collapses de port » | **PIRE que ça** : `CasterTileSelector$$Select` n'a **aucune** branche `GetMainTile` — son fallback est `EntityExtensions.GetTiles(caster)`, l'empreinte ENTIÈRE ; idem `TargetTilesSelector$$Select`. Et `DSLSelectors$$InitializeShared` alloue `CasterTile` (+0x50) et `CasterTiles` (+0x58) depuis **le même pointeur de classe**, même ctor `(state)` — le singulier ne se distingue du pluriel par RIEN (même forme qu'`IsSurrounding` == `IsInRange`). **Non porté** : résidu `#433-r3-r1a-r2` (§7) |
| `Tiles` | d'accord | **confirmé** (`UnitsMainTilesSelector$$Select` → `GetMainTile` par entité) |
| `MovableTilesInRange` | d'accord | non ré-ouvert (le ctor prend `unitSelector` **et** `unitTileSelector` séparés) |
| `UnitsDirectlyBehind` | *absent de la fiche* | **divergeait** : anneau, occupant, et distance du candidat lisent tous l'empreinte ; seul le SEUIL compare deux main tiles (`MinDistance(Tiles(caster), Tiles(target))`) |

## 5. Le port — UN foyer, trois fonctions dans `dsl/base.py`

* **`_occupants_by_tile(units)`** — index `{(col,row) -> unité}` construit sur `_feet`, mirror de
  `SelectUnit`/`GetUnit`/`TileContentComponent`. Vivants seulement (#57m : `KillUnit` libère la
  tuile). **Consommé par `Units.select`, `triggers.py::_units_on` (→ `HasUnit`, `AreEnemies`)** —
  les deux boucles d'occupation qui existaient sont supprimées, il n'en reste qu'une.
* **`_origin_tiles(origin, board)`** — mirror du `foreach tile in IterateTiles(entity)` qui ouvre les
  deux itérateurs. Domaine mixte comme le natif : dict → `_feet`, position → `[pos]`, liste → elle-même,
  id de tuile → `board.coord`.
* **`_main_tile(origin)`** — mirror `GetMainTile`, et **c'est exactement ce que soustrait**
  `- Tiles(origin)`.

`_within` compose les deux bouts : le centre par `_origin_tiles`, l'occupant par `_feet`, l'exclusion
par `_main_tile`. **Sur des unités mono-tuile la formule se réduit terme à terme à l'ancienne**
(`d <= radius and (include_center or d > 0)`) — aucune variation possible hors multi-hex, et un test
l'atteste. `_tile_enum_rank` accepte désormais la liste des pieds du centre (concaténation dans
l'ordre des pieds, dédoublonnée = `OrderedSet`), et le rang d'une unité est celui du **premier** de
ses pieds atteint par l'énumération (le natif itère les TUILES, la première occurrence fixe la place).

Branchés sur le foyer : `Units`, `_units_on`, `_within` (donc `AdjacentUnits`/`AdjacentEnemies`/
`AdjacentFriends`/`SurroundingUnits`/`SurroundingEnemies`/`SurroundingFriends`), `SurroundingTiles`,
`UnitsOnTilesWithEffect`, `Unobscured`, `UnitsDirectlyBehind`.

## 6. Le rayon de souffle, MESURÉ

`probe_433_r3_r1_dsl_footprint_scan.py --step occupancy` (AST) rapporte les lecteurs **exécutables**
et la FORME de leur origine — parce que c'est elle qui décide si le correctif peut mordre :

* **101 sites exécutables** (contre ~200 mentions textuelles).
* **25 à origine ENTITÉ** (`Target()`, `Caster()`, `Owner()`, `Subject()`…) → les DEUX moitiés du
  correctif mordent.
* **52 à origine TUILE** (`CasterTile()`, `TargetTile()`, `OwnerTile()`, `FixedTile(...)`) →
  l'empreinte du CENTRE est déjà perdue en amont ; seul le correctif d'OCCUPANT y mord.
  C'est le résidu `#433-r3-r1a-r2`.
* Le reste (24) passe une variable locale — non classable par AST seul.

**Le correctif d'occupant, lui, mord sur les 101** : il porte sur les unités balayées, pas sur le
centre.

## 7. Ce qui a été MESURÉ

### LIVE — `test_433_r3_r1a_occupancy_live.py`, 10/10

Porteur multi-hex : `ultraDreadnought` (MoW du pool) → `DutyEternal` (1158) → `ultraSmnDreadnought`
sur **3 tuiles**, board `MC1_67`, montage et critère de discriminance IMPORTÉS de
`test_multihex_dutyeternal_live.py` (`_pick_anchor` : attaquant à d=1 d'un pied, d≥2 de `feet[0]`
**et** de `feet[-1]`).

**Deux oracles natifs INDÉPENDANTS**, et aucun cast à mesurer (donc le piège `toActivate` de la
tranche précédente — un refus silencieux qui ressemble à une mesure — n'existe pas ici) :

| canal natif | ce qu'il dit |
|---|---|
| `boardGraph.tiles[].occupantUnitId` (= projection du `TileContentComponent`) | les **3** pieds portent l'id du Galatian |
| `aiMovableTiles` (le pathfinder lit `TileContentComponent$$IsFilled`) | les **3** pieds sont infranchissables |

| cran | mesure |
|---|---|
| port `_occupants_by_tile` | résout les 3 pieds → accord tuile pour tuile avec le natif |
| contre-épreuve (collapse main tile) | ne voit QUE `feet[0]` |
| `Units(<tuile d'un pied non-ancre>)` | rend le Galatian / collapse : **vide** |
| `HasUnit(<idem>)` | vrai |
| `AdjacentUnits(Caster())` | contient le Galatian / collapse : **absent** |

### OFFLINE — `test_433_r3_r1a_occupancy_offline.py`, 26/26

Un axe par nœud, chacun avec sa contre-épreuve. **Contre-épreuve de la contre-épreuve, mesurée** :
patcher le seul `engine.dsl.base._feet` laissait `units.py` sur son import par nom et rendait
2 contre-épreuves VERTES pour rien — le helper patche donc les **trois** modules porteurs.

**Mutation-test du fichier entier** : `_feet` forcé au collapse main tile → **14 rouges sur 26**
(revert vérifié : 0 occurrence du marqueur). Un test qui ne peut pas rougir ne garde rien.

### Non-régression — **20 fichiers, 152 tests verts**

Face COMBAT (live) : `test_plasma_grenade_splash_live` (1), `test_stikkbomb_migration_live` (1),
`test_jakhal_stimms_live` (3), `test_plasma_cannon_lateral_live` (1), `test_gauntlets_combat_live` (1),
`test_death_nova_live` (5), `test_harvester_live` (3), `test_targeting_adjacency_rules_live` (22),
`test_multihex_dutyeternal_live` (20), `test_433_r3_r1_dsl_footprint_live` (4),
`test_dark_talon_strike_live` (2), `test_doom_siren_live` (4), `test_splash_targeting_live` (10),
`test_scything_talons_migration_live` (1), `test_psyker_splash_live` (1),
`test_splash_range_clamp_live` (18).

Face DÉCISION (live) : `test_thrice_blessed_decision_live` (4) — c'est le consommateur direct du
foyer (`HasUnit(Subject) & AreEnemies(Owner, Units(Subject))`) —, `test_plasma_grenade_decision_live` (8),
`test_mass_driver_splash_prediction_live` (5), `test_stikkbomb_decision_live` (9).

Offline : `test_433_r3_isadjacent_node_offline` (15), `test_433_r3_r1_dsl_footprint_offline` (18),
`test_433_r1_identity_shortcircuit_offline`.

**Banque de cliquets : VERTE, 30/30** (mur 117,2 s).

⚠ **Trois rouges de `test_multihex_substrate.py` PRÉEXISTENT** (`IndexError` sur
`board.neighbours_native(...)` vide) — tâche **#457**, confiée ailleurs. Contre-épreuve faite en
restaurant `scripts/python/engine` à `HEAD~1` : **mêmes trois échecs**, donc hors de cette tranche.

⚠ **`test_stikkbomb_decision_live` a d'abord rendu 9 ERRORS — de CONTENTION, pas de fix.** Le
symptôme est une `AssertionError` au **setup** du fixture de montage (aucune assertion de test
évaluée), et il n'apparaît que sous 4 processus pytest concurrents ; **rejoué SEUL le fichier rend
9/9**. C'est une mesure du plafond de parallélisme, pas un verdict : ce fichier monte 7 bras A/B
(≈ 14 min), et l'agréger à un lot de 4 le pousse hors de sa fenêtre.

## 8. Résidus NOMMÉS

* **`#433-r3-r1a-r1` — le flag `unique` de `Units` n'est pas modélisé.** Le natif tranche par
  `IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$.ctor(state, tilesSelector, unique,
  selectionType)`, posé par `IdunBattleLogic.Entities.DSLSelectors$$Units` : `unique == 0` →
  `SelectAllUnits` (List, **aucun** dédoublonnage — une unité occupant DEUX tuiles du sélecteur sort
  **deux fois**) ; `unique != 0` → `SelectUniqueUnits` (`ArraySet`). Le port fait toujours l'équivalent
  d'`unique = 1`, qui est le flag des deux call-sites natifs LUS (les deux `Units(..., 1, 3)` de
  `UnitsDirectlyBehind`). ⚠ Ce régime **n'était pas atteignable avant ce commit** (l'index par main
  tile rendait au plus une tuile par unité) : la correction le rend observable. Relever le flag aux
  ~100 call-sites portés est une tranche à part.
* **`#433-r3-r1a-r2` — `CasterTile` / `OwnerTile` / `TargetTile` rendent UNE position.** Le natif rend
  une LISTE (`GetTiles`, §4). **52 des 101 lecteurs** passent par eux, et le correctif d'origine y est
  donc inerte. Les élargir exige de convertir ~10 consommateurs SCALAIRES : destination de `MoveUnit`
  (`Cache(TargetTile())`), `TilesBehindInLine`, `SortByDistance`, `MovableTilesInRange`, `CanAddUnit`,
  `tiles_unit_can_move_to_charge_target`. Tranche distincte.
* **`#433-r3-r1a-r3` — `MatchesUnitSelectionType` non porté.** `IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType`
  vaut `0` = tout · `1` = vivant · `2` = non-`HasFlag(0x11)` · `3` = vivant ET non-`HasFlag(0x11)`, et
  le `selectionType` est un littéral PAR CALL-SITE (`DSLSelectors$$GetDefaultUnitSelectionType(onlyAlive)`
  = `2 + onlyAlive`). Le port applique un filtre VIVANT inconditionnel. C'est le résidu hérité
  `#433-r3-r2`, dont le foyer est désormais nommé.
* **`#433-r3-r1a-r4` — la chaîne END-TO-END « une AoE endommage par un pied secondaire » n'est PAS
  confrontée.** Elle exige un porteur de splash DÉTERMINISTE dans le pool ET une géométrie où le
  splash passe par un pied non-ancre ; les deux porteurs `AdjacentEnemies(TargetTile())` **purs** du
  port (`PlasmaGrenade`, `Stikkbomb`) sont npc/summon, et `DoomSiren` tire au hasard dans sa pool. Les
  deux oracles natifs du §7 mesurent la CAUSE (l'index d'occupation) sur deux canaux ; l'EFFET en aval
  reste non confronté.
* **`#433-r3-r1a-r5` — l'élévation de `UnitsDirectlyBehind` reste ancrée sur la main tile de la
  cible.** Le natif passe `TilesOnSameElevation(target, cands, 1)` — une comparaison PAR TUILE. Le
  port compare l'élévation de chaque pied candidat à celle de `_main_tile(target)`. Écart inobservable
  tant que la cible est mono-hex.
* **`#433-r3-r1a-r6` — trois rouges préexistants** dans `test_multihex_substrate.py` (§7, tâche #457).

Résidus hérités toujours ouverts : `#433-r3-r1b` (quantificateur d'`IsCharging` — le natif prend UNE
unité de chaque côté via `TargetsSelector$$SelectUnit`, surcharge SÉLECTEUR = un `FirstOrDefault`
filtré, dont le corps est maintenant lu et cité), `#433-r3-r1c` (l'empreinte n'existe pas côté
DÉCISION), `#433-r3-r1d` (namespace `DSLSelectors` vs `DSLFactory` dans les docstrings),
`#433-r3-r2`/`#433-r3-r3`.
