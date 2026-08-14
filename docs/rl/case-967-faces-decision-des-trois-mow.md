# #967 — les SIX faces DÉCISION des trois MACHINES OF WAR

Six abilities dont la face **COMBAT** était portée et confrontée (case-90, case-117, #902) et dont
la face **DÉCISION** était absente : l'IA les choisissait avec un scoring qui n'est pas celui du
natif, et c'est **invisible en replay** puisque l'exécution, elle, est fidèle.

| id | ability | porteur | classe playbook native | base (`frida/classes.tsv`) | `MIN_UTILITY` (`.cctor`) | `get_Priority` (#170) |
|---|---|---|---|---|---|---|
| 1213 | `DeathOnTheWind` | `darkaStormSpeeder` | `IdunBattle.AI.Playbook.Loki.DeathOnTheWindPlaybook` | `NonComparablePlaybook`1` | **2** | **1000** |
| 1214 | `Hailstrike` | `darkaStormSpeeder` | `...Loki.HailstrikePlaybook` | `NonComparablePlaybook`1` | 1 | 0 |
| 1142 | `MalleusRocketLauncher` | `astraOrdnanceBattery` | `...Loki.MalleusRocketLauncherPlaybook` | `NonComparablePlaybook`1` | 1 | 0 |
| 1143 | `ForwardSpotter` | `astraOrdnanceBattery` | `...Loki.ForwardSpotterPlaybook` | `NonComparablePlaybook`1` | 1 | 0 |
| 1223 | `ReanimationBeam` | `necroReanimator` | `...Loki.ReanimationBeamPlaybook` | `NonComparablePlaybook`1` | 1 | **-1000** |
| 1224 | `NanoscarabRepairProtocols` | `necroReanimator` | `...Loki.NanoscarabRepairProtocolsPlaybook` | `NonComparablePlaybook`1` | 1 | 0 |

**Corps propres, fondu ICF : aucun.** Recensement fait **au bloc d'adresses**
(`probe_967_playbook_blocks.py` sur `ghidra/functions.tsv`), pas par grep : chaque classe occupe un
bloc **contigu**, le voisin immédiat appartenant à une autre classe. 1213 en a **six**
(`EvaluateNonComparable`, `GetCustomUnitOrderUtility`, `HasPossibleTarget`, `ShouldEvaluate`,
`.cctor`, `.ctor` + une lambda `<HasPossibleTarget>b__0` dans la région des closures), 1214 **six**
(`EvaluateNonComparable`, `GetPierceRatioUtility`, `GetTargetUtility`,
`HasRangedAttackAndCanAttackThisTurn`, `.cctor`, `.ctor`), les quatre autres **trois**.

**Le `.ctor` ment sur la hiérarchie, six fois sur six** : le décompilé nomme
`ComparablePlaybook<...>..ctor` (corps trivial dédupliqué — piège #487-r1 / #945 / #957). La base
est LUE dans `frida/classes.tsv`.

**Reachability** : LUE dans `metadata/active_playbook_builders.tsv`
(`IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders`) — six entrées du dict `active`, une
par ability. Aucune n'est du code registered-but-dead.

## Combien existaient déjà : ZÉRO

C'est le fait que l'orchestrateur demandait, et l'audit qui les liste y est structurellement
aveugle. `git grep` sur les six noms **et** sur les six ids, dans tout `scripts/python` : **aucune
des six n'était portée**, ni dans `PLAYBOOKS`, ni dans un module tiers, ni par une route détournée.

Ce qui existait, en revanche, ce sont **deux traces justes** — et c'est ce qui rend le zéro
intéressant :

1. **`_base.NATIVE_PRIORITY` portait déjà 1213 = 1000 et 1223 = -1000**, issues du sweep exhaustif
   des 258 `ActiveAbilityType` (#170). La table connaissait donc l'existence des deux playbooks
   avant qu'aucun ne soit porté. Le port se contente de les LIRE (`native_priority(...)`).
2. **`ai/action_generators.py` et `predict.py` EXCLUAIENT déjà 1224** du routage Comparable-repair
   (`_COMPARABLE_REPAIR_IDS = {Repair(28)}` — son commentaire nomme explicitement
   « `NanoscarabRepairProtocols`, NonComparable-repair, exclu » — et `_REPAIR_NC_KEYS`).
   L'exclusion est **correcte**. Sa conséquence ne l'était pas : sans playbook NC enregistré, 1224
   devenait une ability que le moteur ne proposait **jamais**. Une exclusion juste avait creusé un
   trou complet.

## Le piège de #957 se rejoue sur 1213 — et il se voit à l'envers

`DeathOnTheWindPlaybook$$EvaluateNonComparable` construit son arbre **hors** de la boucle de
cibles :

```
foreach entities in GetEligibleTargetsSelectable(caster, casterPosition):
    tiles   = <DeathOnTheWindAbility>$$GetMachineAttackTiles(this.ability@+0x68)
    targets = <DeathOnTheWindAbility>$$GetMachineAttackTargets(this.ability, tiles)
    util    = Fix64( targets.<ITargetsSelector slot 2 = Count>(entities) )
```

Les deux constructeurs ne prennent **que** l'ability. On lirait volontiers « arbre identique à
chaque tour de boucle, donc terme constant sur les cibles ». **Faux** : l'arbre est un *sélecteur
DSL*, et c'est `Count(entities)` qui l'**évalue**, `entities` étant le contexte de la cible
courante. Les référents `Target@+0x60` / `Subject@+0x68` s'y résolvent **cible par cible**.
Le terme est donc exactement le contraire d'une constante — il *est* l'utilité.

Le slot **2 d'`ITargetsSelector` est `Count`** (`metadata/interface_slots.tsv` : 0 = `Select`,
1 = `SelectFirst`, 2 = `Count`), pas une déduction de nom.

## Les six utilités, terme à terme

- **1213** `util = |ennemis sur ({tuile visée} ∪ ligne(best))|` où `best` = la tuile du ring-1
  maximisant le nombre d'ennemis sur `TilesBehindInLine(Target, d, nrOfTiles-1)`, tri
  `SortByFormula(..., DESC)` **stable**. Deux écarts avec la famille voisine `ThriceBlessedConflagration`
  (1187) : la ligne est **bornée** à `nrOfTiles - 1`, et il n'y a **aucun `FilterContinuous`** —
  les trous ne cassent pas le compte. Copier la feuille de 1187 serait faux sur les deux axes.
  `MIN_UTILITY = 2` : l'occupant comptant déjà pour 1, il faut un **second** ennemi aligné.
- **1214** `util = (100 - PiercingRatio de l'arme de l'allié) + rng.Next(0,10) + 500·bonus`, avec
  `bonus` vrai si `HasTrait(Overwatch)` ou (arme/ability à distance **et**
  `CanAttackAnyUnitFromAnyTileWithAnyAbility`). L'utilité **décroît** avec le perçage déjà possédé —
  Hailstrike buffe le perçage, l'IA le donne à qui en manque le plus. `w->+0x18` est le
  `DamageProfile` et `+0x14` son `PiercingRatio` (confirmé par le gameconfig, qui range
  `PiercingRatio` sous le **profil**, pas sous l'arme).
- **1142** `util = (+3 ennemi / -3 ami / 0 vide pour l'occupant de la tuile visée) + Σ(+1 ennemi /
  -1 ami) sur les unités ADJACENTES`. Le signe est lu, pas deviné : `((f & 0xff) ^ 1) * 2 - 1`.
  Deux gates : `util > 0` **inline** (aucune action n'est même construite) puis `AddAction` à
  `>= 1`. Sur des entiers ils coïncident ; le port écrit les deux parce que le natif les écrit.
- **1143** `util = 1 + |{tuiles libres adjacentes à la cible d'où le Cadian invoqué aurait une
  cible}|`. **Le plancher `Fix64(1)` posé AVANT la boucle est tout** : `AlphaWarriorPlaybook` (1112)
  partage le slot 195 et le même `MIN_UTILITY = 1`, mais émet le booléen **nu** — chez lui le seuil
  fait un VETO, ici il ne refuse jamais.
- **1224** `util = GetStat(target, 0 = ATTACK)`. Squelette **identique** à `MindControlPlaybook`,
  qui lit `5 = HEALTH` au même emplacement : seul l'ordinal diffère, et la confusion serait
  silencieuse. Ne lit **pas** `hpToRepair` — c'est l'effet 1545 qui le lit (#902).
- **1223** `util = Fix64(1)`, constante, `= MIN_UTILITY` : keep-first sur l'ordre du sélecteur.
  Tier **-1000**, donc 1224 (tier 0) prime **toujours** sur elle, par l'ordre des générateurs.

## Résidu #945-r1 fermé : la branche MACHINE du slot 195

`HasSummonTargetInAttackRangeAtTile` (slot 195, `interface_slots.tsv`) bifurque sur
`EntityExtensions.IsMachine(parent)`. `AlphaWarriorPlaybook` (porteur `tyranWingedPrime`, une
unité) ne l'atteignait pas, d'où le résidu. **`ForwardSpotter` la rend obligatoire** : son porteur
`astraOrdnanceBattery` est une MoW.

```
HasSummonTargetInAttackRangeAtTileWithMachineParent(machineParent, unitId, tile):
    player  = EntityExtensions.GetOriginalPlayer(machineParent, state)
    foreach target in GetAllEnemiesOf(player.Id):
        if (IsTargetInAttackRangeForSummon(machineParent, unitId, tile, target)) return true
    return false
```

La différence n'est pas cosmétique : la branche unité ne teste **que** `GetNearestEnemy`, la branche
machine les teste **tous**. Recopier la première sur une MoW serait strictement plus restrictif.
Les deux vivent désormais dans le foyer `engine/playbook/noncomparable/summon_attack_range.py`,
dont `alpha_warrior.py` est lecteur (`machine_parent=False` — comportement inchangé).

## Validation

**Offline** — `tests/engine/playbook/test_967_mow_decision_faces_offline.py`, 19 tests, verts.
Vert au premier passage ne prouve rien : **`probe_967_morsure.py` applique 11 mutations** (seuil de
1213, `FilterContinuous` fantôme, gate `ShouldEvaluate` neutralisé, perçage inversé, bonus annulé,
plancher de 1143 retiré, pénalité amie de 1142 inversée, terme d'occupant annulé, tier de 1223
remonté, utilité de 1224 aplatie, ordre du sélecteur remplacé par un tri) et **les 11 mordent**,
restauration vérifiée.

**Live** — `astraOrdnanceBattery` est au pool (8 MoW spawnables au rank 17). Runner seed 777 /
board MC1_67, `engine_validate --runner`, tour d'IA **observé** :

| | step 11 |
|---|---|
| natif | `u83 ABIL ab=1143 tgt=84` |
| port #967 | `ability(ab=1143, tgt=84)` — **MATCH** |
| témoin (registre amputé de 1142/1143) | `finish(ab=None, tgt=None)` — **MISS** |

La contre-épreuve a été **vérifiée avant d'être jouée** (assertion que 1142 et 1143 ont bien
disparu de `PLAYBOOKS`), et le registre restauré ensuite.

## Ce qui n'est PAS couvert

- **Quatre faces sont PORTÉES-NON-CONFRONTÉES** : `darkaStormSpeeder` et `necroReanimator` ne sont
  pas dans les 8 MoW spawnables au rank 17. « Absent du pool » n'est pas « non confrontable » — la
  voie est l'injection catalogue. **#967-r5**.
- **1142 n'a pas tiré** sur le régime monté (`munitions` manquantes au tour 1, bataille finie avant
  recharge) : elle est dans le même sac que les quatre ci-dessus.
- `GetCustomUnitOrderUtility` (**#967-r1**), le terme aléatoire de 1214 (**#967-r3**),
  `HasRangedAbility` (**#967-r4**).

## #967-r2 — FERMÉ : le 5ᵉ argument est `includeNonWalkable`, et il désarmait un filtre

**La chaîne, relue verbatim sur `rnca9r7q6c`.** Ghidra nomme la surcharge à 6 paramètres, ce qui
tranche l'ambiguïté que le résidu laissait ouverte :

```
IdunBattleLogic.Entities.DSLSelectors$$SurroundingTiles(this, origin, includeCenter, range,
                                                        onlyMovable, includeNonWalkable)
  -> IdunBattle.Entities.Selectors.SurroundingTilesSelector$$.ctor : this+0x29 = includeNonWalkable
  -> IdunBattle.Entities.Selectors.SurroundingTilesSelector$$Select :
         slot(query, tile, range, 0, /* checkWalkable */ (this+0x29 == 0), onlyMovable, 1)
```

Le 5ᵉ argument **hors `this`** est donc `includeNonWalkable`, et il est **inversé** en chemin :
`includeNonWalkable == 1` ⇒ `checkWalkable = false` ⇒ **aucun filtre de marchabilité** ;
`== 0` ⇒ filtre **armé**. C'est ce qui explique les deux littéraux du résidu —
`DeathOnTheWindAbility$$GetMachineAttackTiles` (1213) passe `1`,
`ThriceBlessedConflagrationAbility$$GetTilesInBestLine` (1187) passe `0`.

**L'écart n'était ni inerte ni masqué : c'était un FORK entre les deux faces de 1187.** La face
DÉCISION posait déjà le filtre en dur (`_best_line_direction` appelle
`bq.get_surrounding_tiles(..., check_walkable=True, ...)`) ; la face COMBAT
(`runner/abilities/sisterhood.py::thrice_blessed_get_tiles_in_best_line`) passait par le nœud DSL,
qui construit un `hexgeo.disk` **pur**. Le combat admettait donc comme direction de beam des tuiles
que sa propre prédiction refusait — du côté **permissif**, donc silencieux.

**Fix** : le nœud porte `include_non_walkable`, défaut `True` = le comportement d'avant (les 7
call-sites qui ne le nomment pas sont inchangés, étage 2 de la garde) ; `sisterhood.py` pose
`False`, le littéral LU. 1213 garde le défaut, littéral LU aussi.

**Garde** — `tests/engine/test_967r2_include_non_walkable_offline.py`, 4 étages, vue ROUGE par deux
mutations adversariales :

| mutation | étages rouges |
|---|---|
| A — retirer `include_non_walkable=False` du call-site 1187 | 3 et 4 |
| B — désarmer le filtre dans le nœud | 1 et 4 |

⚠ **L'étage 4 a d'abord été un FAUX VERT, et c'est la mutation qui l'a montré.** Il reconstruisait
son propre nœud `SurroundingTiles(..., include_non_walkable=False)` : sous la mutation A il restait
**vert** alors qu'il est précisément l'étage censé voir le fork. Il extrait désormais le nœud de
l'arbre **réel** de 1187. Un étage qui fabrique son sujet ne garde que lui-même.

**Non-régression** : 159 tests offline (ring, wall-of-mirrors, sélecteur de spawn, first-among-traitors,
kustom-force-field, collapses impératifs, faces décision #957/#979/#967, règles de ciblage #287-r11-r1).

**Résidu ouvert** : **#967-r10** — le filtre **MUR** (`tileComponent+0x41`, première ligne
d'`IsTileValidForList`, indépendante de `checkWalkable`) n'est porté pour **aucune** valeur du
paramètre. Il toucherait les 7 call-sites d'un coup, donc il se mesure séparément.
→ **FERMÉ**, section suivante.

## #967-r10 — FERMÉ : le mur est filtré AVANT `checkWalkable`, et les deux octets voisins ne sont pas ceux qu'on croyait

**La chaîne, relue maillon par maillon** — l'énoncé du résidu ne citait que le *dernier*, et une
citation qui saute un étage est exactement ce qui a fait porter #948-r1 sur le mauvais symbole :

```
IdunBattle.Entities.Selectors.SurroundingTilesSelector$$Select
  -> slot 102 d'IBattleQuery = IterateSurroundingTiles   (metadata/interface_slots.tsv)
     avec checkWalkable = (this+0x29 == 0)               <- le mapping d'includeNonWalkable (#967-r2)
  -> IdunBattle.Core.Services.BattleQuery.u003CIterateSurroundingTilesu003Ed__117$$MoveNext
  -> ITileQuery
  -> IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext
     (triple boucle cube ascendante ; IsTileValidForList(tile, originTile, checkWalkability,
      checkElevation: 0))
  -> IdunBattle.Core.Services.TileUtil$$IsTileValidForList
```

et le corps du maillon terminal :

```
if (tileComponent+0x41 != '\0')   return false            # MUR — avant tout test de walkability
if (checkWalkability == '\0')     return tileComponent+0x40 == '\0'
else                              IsWalkable(tile, checkFog: 1) && ...
```

**L'IDENTITÉ DES DEUX OCTETS a dû être LUE, pas déduite** — ils sont adjacents, donc les confondre
ne lève rien, et le dépôt les avait **inversés** :

| octet | ce qu'il est | fonction qui le PROUVE |
|---|---|---|
| `+0x41` | `IsWall` | `IdunBattle.Entities.Pathfinding.FlyPathfinder$$IsAnyAdjacentTileWall` rend `true` sur `*(char*)(comp+0x41) != 0`, et rien d'autre |
| `+0x40` | `IsInFogOfWar` | `IdunBattle.Entities.TileExtensions$$IsInFogOfWar` rend **exactement** `*(byte*)(comp+0x40)` |

`engine/runner/abilities/astramilitarum.py` écrivait l'inverse (« `+0x40` est le champ que
`TileExtensions$$IsWalkable` lit comme MUR », et en résidu « `+0x41` n'a aucun substrat offline
distinct »). Son **comportement** était juste — il filtre `isWall`, qui *est* `+0x41` — mais sa
prose désignait le mauvais octet ; prose corrigée, code inchangé.

**Le fix** : `_is_wall` dans le nœud, appliqué **inconditionnellement**, en amont du gate
walkable. Substrat = la clé `isWall` du `boardGraph` (`match-state.ts`, `COMP_FIELD.tileIsWall`).

**Pourquoi PAS `Board.is_wall()`**, dont le repli documenté est `not walkable` : ce repli **fond
les deux axes**. Mesuré — `C3_01` porte **14** tuiles `walkable=False` / `isWall=False`
(Block/Water), et `C6_06` en porte **5** : l'emprunter les aurait retirées du disque, alors que le
natif les **garde** sous `includeNonWalkable = 1`. Clé absente ⇒ gate **inerte**, jamais un `False`
fabriqué depuis une non-mesure.

**Témoin NON NUL** (`probe_967r10_murs_du_disque.py`, 4 boards, boardGraph live) :

| board | tuiles | `isWall & !walkable` | `isWall & walkable` | `!isWall & !walkable` | r=1 centres/retirées | r=2 |
|---|---|---|---|---|---|---|
| MC1_67 | 63 | 0 | 0 | 1 | 0/0 | 0/0 |
| C3_01 | 63 | 0 | 0 | **14** | 0/0 | 0/0 |
| C1_74 | 63 | 0 | 0 | 3 | 0/0 | 0/0 |
| **C6_06** | 63 | **13** | 0 | 5 | **36/72** | **54/206** |

Les murs ne vivent que sur les boards **Space Hulk** : `HulkWall` = **168** tuiles réparties sur
**17** boards `C6_*` dans la BC (`data/boards/`), zéro ailleurs. Une mesure faite sur les boards
usuels (`MC1_67`, `C3_01`, `C1_74`) rend donc un **témoin nul parfaitement crédible** — c'est ce
qui a failli faire conclure « inerte ».

**Ce qui reste NON COUVERT, et c'est le point honnête de cette fermeture.** L'écart de **72 tuiles
sur 36 disques** est mesuré **au nœud**. En aval, la plupart des consommateurs le **neutralisent**
déjà : `CanAddUnit` filtre `walkable` (donc les 13 murs de `C6_06`, tous `walkable=False`) —
c'est le cas d'`orks`/SquigMine et des deux `wall_of_mirrors` ; `Units(tiles)` ne peut rendre
aucune unité posée sur un mur (`living_lightning`) ; et `sisterhood`/1187 arme déjà le gate
walkable. **Le seul call-site où l'écart est observable est `darkangels`/1213
`DeathOnTheWindAbility$$GetMachineAttackTiles`** : son `ring` alimente
`SortByFormula → PickFirstN(1)`, c'est-à-dire le **choix de direction** de la ligne d'attaque, sans
aucun filtre walkable en aval — et 1213 est précisément celui qui passe `includeNonWalkable = 1`.
Une tuile mur pouvait donc **gagner le tri** et faire tirer la ligne dans une direction que le
natif refuse.

**Montage exact pour la confronter** (non joué, budget) : `C6_06` (13 murs), MoW dark angels,
cible placée adjacente à au moins un `HulkWall`, et une géométrie où ce mur maximise
`Count(Enemies(Units(GetTilesInLine())))` — le discriminant est la **direction retenue**, relevée
des deux côtés, jamais un total.

**Garde** : `tests/engine/entities/test_967r10_surrounding_tiles_walls_offline.py`, 7 étages, vue
ROUGE avant fix sur 4 discriminants (mur sous chacune des deux valeurs d'`includeNonWalkable`,
indépendance des deux axes, centre mur). Deux étages sont là pour empêcher la *sur*-correction :
`test_les_deux_axes_sont_independants_non_walkable_reste` (Block/Water restent) et
`test_gate_inerte_si_le_board_ne_publie_pas_iswall`.

**Résidu ouvert** : **#967-r11** — le **FOG** (`+0x40`), testé par les **deux** branches du natif
(`return tileComponent+0x40 == 0` quand `checkWalkability == 0`, `IsWalkable(tile, checkFog: 1)`
sinon), donc coupant lui aussi quelle que soit la valeur d'`includeNonWalkable`. La clé `isInFog`
existe côté hook (`rpc-board.ts`) et est lue par `engine/ai/context.py`, mais `Board` ne l'expose
par aucun accesseur et elle n'est pas confrontée ici : gate inerte, dit comme tel.

---

## #967-r11 — le FOG, TROISIÈME axe du même maillon, et son `BLOCAGE: seeding` était PÉRIMÉ

**Fermé le 2026-08-14.** La ligne ci-dessus disait « gate inerte » ; c'était vrai du **port**, pas
du **substrat**. Mesuré : `boardGraph` publie `isInFog` sur **63/63** tuiles des trois boards
testés, au même rang qu'`isWall`. Aucun capteur à poser — le blocage annoncé n'existait plus.

### Le décompilé, relu verbatim sur `rnca9r7q6c`

`IdunBattle.Core.Services.TileUtil$$IsTileValidForList` — le maillon terminal, déjà celui de
#967-r10 :

```
if (tileComponent+0x41 != 0)   return false                     # MUR   (#967-r10)
if (checkWalkability == 0)     return tileComponent+0x40 == 0   # FOG, branche 1
else                           IsWalkable(tile, tileComponent, tile+0x40,
                                          checkFog: CONCAT71(checkElevation >> 8, 1))
```

`IdunBattle.Entities.TileExtensions$$IsWalkable` — la surcharge à **quatre arguments** (il en
existe trois, désambiguïsées par l'**arité** ; les deux autres prennent `(tile, checkFog)`) :

```
if (movement+0x10 != 0)   return false           # MARCHABILITE (MovementComponent)
if (checkFog == 0)        return true
return tileComponent+0x40 == 0                   # FOG, branche 2 -- MEME octet
```

Le littéral `1` de `checkFog` est écrit **en dur** par l'appelant (octet bas de
`CONCAT71(checkElevation >> 8, 1)`) : ce n'est **pas** `checkElevation` qui le pilote. Donc le fog
coupe dans les deux branches, exactement comme le mur.

Identité de l'octet, **lue** et non déduite du voisinage :
`IdunBattle.Entities.TileExtensions$$IsInFogOfWar` rend **exactement** `*(byte*)(comp+0x40)`.

### Trois axes indépendants, désormais tous portés

| axe | offset natif | conditionnel ? | accesseur du port |
|-----|--------------|----------------|-------------------|
| MUR | `TileComponent+0x41` | non | `_is_wall` (#967-r10) |
| FOG | `TileComponent+0x40` | non | `_is_in_fog` (#967-r11) |
| MARCHE | `MovementComponent+0x10` | armé par `includeNonWalkable == 0` | `_walkable` (#967-r2) |

Le discriminant qui interdit de rabattre le fog sur la marchabilité est **mesuré** :
`probe_967r11_fog_du_disque.py`, seed 777.

| board | tuiles | `isInFog` publié | `fog & !walk` | `fog & walk` | `!fog & !walk` | effet r=1 | effet r=2 |
|-------|--------|------------------|---------------|--------------|----------------|-----------|-----------|
| `MC1_67` | 63 | 63 | 0 | 0 | 1 | 0/0 | 0/0 |
| `C6_02` | 63 | 63 | 1 | **31** | 21 | 41 centres / **155** tuiles | 50 / **413** |
| `C3_01` | 63 | 63 | 0 | 0 | 14 | 0/0 | 0/0 |

Les **31** tuiles `fog && walkable` sont le régime discriminant : le gate walkable ne peut pas les
couper, et fondre les deux axes les garderait. Ce 31/63 corrobore, par un chemin indépendant, la
mesure de #433-r4. Symétriquement, les 21 tuiles `!fog && !walk` (Block/Water) doivent **rester**
sous `includeNonWalkable = 1` — le filtre fog ne doit pas y toucher.

L'effet est mesuré **par différence sur le seul gate fog** (sous-classe qui neutralise
`_is_in_fog`), pas contre un disque `hexgeo.disk` pur : comparer au disque pur mélangerait les
trois axes.

### Rayon de souffle et value-preserving

Le rayon est **dérivé du code par AST** (`probe_967r11_rayon_de_souffle.py`, qui résout aussi la
voie **attributaire** qu'un recensement d'`ImportFrom` rate) : **6 fichiers, 7 sites** sous
`engine/`, plus 4 fichiers de tests/probes. Les call-sites sont `DeathOnTheWind` (darkangels),
`WallOfMirrors` (×2), `SquigMine` (orks), `ThriceBlessedConflagration` (sisterhood), `NovaCharge`
(tau), `LivingLightning`.

**Value-preserving** : `MC1_67` et `C3_01` — les boards de la quasi-totalité des tests — portent
**zéro** tuile en brouillard, donc le correctif y est un **no-op exact**. Un board qui n'a pas pu
être monté n'est jamais compté comme un board sans fog (les `C6_*` n'ont que 3-4 spawns : sans
`--p-units` ils sortent en `BUILD KO`, et lire ce KO comme un zéro fabriquerait le
value-preserving qu'on cherche à établir).

### Garde

`tests/engine/entities/test_967r11_surrounding_tiles_fog_offline.py` — 9 étages, fixture nommée
`board_trois_axes` / `board_fog`. Vue **ROUGE** par mutation adversariale (gate retiré) : **6
tests sur 9** tombent ; les 3 restants sont les non-régressions qui doivent rester vertes des deux
côtés (`gate inerte sans la clé`, `disque sans fog inchangé`, `non-marchable sans fog reste`).

Message verbatim :

```
AssertionError: le centre EN BROUILLARD est reste sous includeCenter=1 : [8, 7, 13, 12, 11, 18, 17]
```
