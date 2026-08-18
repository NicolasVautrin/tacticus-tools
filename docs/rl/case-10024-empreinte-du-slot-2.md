# #10024 — `BattleQuery$$IsMeleeAttack` compare des **EMPREINTES**, et le port comparait deux **MAIN TILES**

Le slot 2 d'`IBattleQuery` — celui dont `#494-r2` vient d'établir qu'il décide **seul** le caractère
melee de l'attaque normale, et que **99** classes d'effet du port relisent — refusait une adjacence
que le natif accorde, dès qu'une des deux unités occupe plus d'une tuile. Sans erreur, sans trace.

Mesures : `python scripts/python/probe_10024_empreinte_is_melee.py --volet <lecture|geometrie|live|confrontation>`
(build `t6dpr4k06g`, 2026-08-18). Cliquet : `scripts/python/tests/engine/runner/test_10024_empreinte_is_melee_offline.py`.

## 1. La lecture — quatre décompilés, et c'est le deuxième qui surprend

| # | artefact natif | ce qu'il dit |
|---|---|---|
| 1 | `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` | signature `(ability:Nullable<AbilityOrEffect>, caster:IEntity, casterPosition:`**`IdunBattle.Core.UnitPosition`**`, target:IEntity)` |
| 2 | `IdunBattle.Core.UnitPosition` | `System.ValueType` à **UN champ** : une `List<IEntity>` de tuiles |
| 3 | `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent(tiles:IList<IEntity>, unit:IEntity)` | `tiles2 = EntityExtensions.GetTiles(unit, state); return MovementUtil.AreTilesAdjacent(tiles, tiles2);` |
| 4 | `IdunBattle.Entities.EntityExtensions$$GetUnitPosition(unit, state)` | corps **entier** : `return GetTiles(unit, state);` |

**(2) est le nœud.** `UnitPosition` n'est pas une tuile déguisée : son `$$.ctor(tile)` construit une
`List` **vide** et n'y ajoute la tuile que si elle est non nulle ; `$$get_MainTile` rend `list[0]`
(donc la main tile est une **conséquence** de l'empreinte, jamais son identité) ; `$$IsEmpty` est
`MainTile == null` ; `$$NullPosition` rend la liste vide. Au niveau ABI la struct **est** le pointeur
de liste (8 octets), et c'est pour cela que le corps d'`IsMeleeAttack` peut passer son 3ᵉ paramètre
**tel quel** à la surcharge `(IList<IEntity>, IEntity)`.

**(4) ferme le côté caster.** Un appelant sans ancre d'ability passe `GetUnitPosition(caster)` — qui
n'est qu'un alias de `GetTiles`. Le port lisait ici une main tile (`battle_query_state.unit_position`,
dont la docstring disait « `GetUnitPosition` réduit à sa MAIN TILE » : la réduction était l'erreur).

**Laquelle des trois surcharges ?** Établi par **xref**, pas par ressemblance :
`BattleQuery$$IsMeleeAttack`, `$$IsRangedAttack` et les **deux** sites de `$$GetAttackRangeType`
appellent tous la surcharge `(tiles, unit)`. Les deux autres — `(entity1, entity2)` et
`(tiles1, tiles2)` — ne sont appelées que par `$$IsCharging` et `$$AreUnitsInMelee`. La surcharge
`(tiles, unit)` est aussi celle qu'appelle `$$GetAttackWeaponForDefaultNormalAttack` (cf. §5).

`MovementUtil$$AreTilesAdjacent(IList, IList)` est un **OU sur toutes les paires** : le verdict
EMPREINTE **domine** donc toujours le verdict MAIN TILE (la paire des main tiles est l'une des
paires), et la seule divergence possible est « natif accorde, port refusait ». C'est un invariant
d'ordre, pas une observation — l'étage 5 du cliquet l'assertionne sur une couronne complète.

## 2. Le régime, chiffré

**Géométrie** (`--volet geometrie`, 24 boards dumpés, empreintes 3-hex dérivées de la géométrie du
board, cible mono-tuile balayée) :

| mesure | valeur |
|---|---|
| empreintes 3-hex visitées | **5 322** |
| couples où les deux modèles s'accordent | **16 820** |
| couples **divergents** (natif oui, main tile non) | **20 644** |
| ratio divergents / total | **0,551** |
| inversions (main tile oui, empreinte non) | **0** — impossible par construction |

Autrement dit **55 % de la couronne d'adjacence** d'une unité 3-hex était perdue. Ce n'est pas un
cas de bord : la couronne d'une main tile compte 6 tuiles, celle d'un triangle de 3 pieds en compte
~12.

**Porteurs.** Aucun champ de gameconfig ne porte la taille d'une unité — elle est fixée au spawn par
la liste de tuiles passée à `AddUnitOperation`. Le canal qui la dit est `decisionView.units[].feet`.
Mesuré live : `ultraSmnDreadnought` « Galatian », posé au sol par `1158 DutyEternal` de la MoW
`ultraDreadnought` (l'une des **8** MoW spawnables), porte **3 pieds**. Le seed BC porte par ailleurs
**6** unités à `NumberOfMembers > 1` (swarms nécrons/tyranides/Nurgle, `TwoManTeam` astra) — leur
nombre de **tuiles** n'a pas été mesuré ici, cf. §6.

## 3. La confrontation live — un oracle natif DIRECT du slot 2

`ncPlaybookPredict(abilityKind: "triggered", col, row)` rend `gates.isMeleeAttack`, **lu sur le
`UtilityAttackCase` réellement soumis, avant toute invocation d'utilité** — donc une erreur en aval
ne le salit pas. La chaîne est
`IdunBattle.AI.Playbook.TriggeredAbilityPlaybook<T>$$IsMeleeAttack(case)` → `IBattleQuery` slot 2,
avec `casterPosition = unitPositionAtTile(caster, tile)`. Le playbook n'est qu'un **récepteur** : la
méthode générique ne lit que le case, donc l'ability triggered choisie n'a pas à être portée par le
caster.

Runner 702, board `global` (seed 777), Galatian posé aux pieds `(0,3) (0,4) (1,4)` (main tile
`(0,3)`), caster `ultraTitus`, ability soumise `Loki_NormalAttack` :

| tuile du caster | dist. à la MAIN TILE | dist. min. aux pieds | **natif** | port APRÈS | port AVANT |
|---|---|---|---|---|---|
| `(0,1)` | 2 | 2 | `False` | `False` | `False` |
| `(0,2)` | 1 | 1 | `True` | `True` | `True` |
| **`(2,3)`** | **2** | **1** | **`True`** | **`True`** | **`False`** |
| `(1,2)` | 2 | 2 | `False` | `False` | `False` |
| `(0,0)` | 3 | 3 | `False` | `False` | `False` |

Un discriminant, trois témoins négatifs, un témoin positif. Le port d'AVANT diverge **exactement** là
où la géométrie l'exige, et nulle part ailleurs — l'accord des quatre autres lignes est ce qui rend
la cinquième interprétable.

## 4. Le port

**Foyer unique de la double boucle** : `engine/services/battle_query.are_entities_adjacent`, qui
gagne une **troisième voie de substrat**. Elle en avait deux (un `Board`, ou rien) ; les trois slots,
eux, reçoivent des **cartes** (`neigh_by_pos` / `elev_by_pos`, `Board.walk_maps_by_pos()`), pas un
`Board`. C'est ce trou qui les avait fait emprunter la primitive **scalaire** au lieu du foyer.

**`as_unit_position`** est le mirror de `UnitPosition` : une tuile `(col, row)` y vaut l'empreinte à
un élément (c'est littéralement `$$.ctor(tile)`, et c'est la forme exacte d'une position **candidate**,
`AbilityEntities+0x40` emballée par `$$get_CasterPosition`) ; une séquence de tuiles vaut l'empreinte ;
`None`/vide vaut `$$NullPosition`. C'est un **adaptateur d'API Python**, pas une déduction sur le natif :
le natif, lui, ne voit jamais qu'une `UnitPosition`.

**`battle_query_state.unit_tiles`** est le mirror de `GetUnitPosition` (= `GetTiles`), délégué à
`runner/components.get_unit_feet`. `unit_position` reste — c'est `get_MainTile` appliqué au résultat —
mais **hors du chemin du prédicat**.

**Consommateurs recâblés** (les trois que la fiche du résidu nommait) :

* `runner/abilities/loki/heavy_bolt_pistol.is_melee_attack` **délègue** désormais au foyer runner
  `battle_query_state` au lieu de remonter les quatre entrées lui-même — deux montages du même slot
  qui dérivent, c'est un bug silencieux par construction ;
* `playbook/light_im_up` et `playbook/heavy_bolt_pistol` passent la cible par
  `playbook.adjacency.iterate_tiles`, le foyer DÉCISION de `GetTiles`.

Le quatrième consommateur (`runner/operations/damage_utility`, celui de `#494-r2`) passe déjà par
`battle_query_state.normal_attack_is_melee` : il est corrigé sans être touché. C'est le **plus gros
rayon** — c'est lui qui alimente `attacker_modifiers(is_ranged=)` / `defender_modifiers(is_melee=)`.

**Strict no-op sur les unités mono-hex** : leur empreinte est `[main tile]`, donc le OU sur les paires
se réduit à la paire unique d'avant. Le cliquet le garde (étage 4, « la mutation est inerte »).

## 5. Ce que la tranche NE couvre PAS

* **`attack_tile` de la face DÉCISION reste une TUILE.** `IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFor`
  rend un `IOrderedSet<UnitPosition>` : pour un caster **multi-hex**, une position candidate est un
  **ensemble** de tuiles, que la face DÉCISION du port ne matérialise pas. Exact pour tout caster à un
  pied (le cas de tous les héros) ; sous-estime pour un caster multi-hex. Résidu.
* **`runner/operations/damage_ops/normal.py`** calcule son adjacence de sélection d'arme par
  `are_tiles_adjacent(main, main)` — **même surcharge native**
  (`$$GetAttackWeaponForDefaultNormalAttack` appelle `AreEntitiesAdjacent(tiles, unit)`, xref lue),
  **même vice**, et il est bien plus observable que le slot 2 : Galatian a une arme mêlée `Power`
  (5 coups) et une arme `Projectile` `Range 2` (6 coups), donc le choix change le **nombre de coups**.
  Non touché (hors du foyer déclaré). S'y ajoute que la **distance** y est `hexgeo.distance(main, main)`
  alors que le natif passe `MovementQuery$$GetDistance(tilesA, target)` — un **troisième** axe.
* **`runner/operations/triggers/loki/empyric_ambush._is_melee_attack`** et
  `runner/operations/triggers/base._is_ranged_position` ré-implémentent le switch sur des main tiles.
  Même vice, sites distincts.
* **`runner/abilities/loki/mv71._is_melee_attack`** collapse `CasterPosition` sur `_first_tile` : c'est
  un **autre** artefact natif (`MV71SniperDroneSquadAttackAbility$$IsMeleeAttack`, un `IsRangedAttackAbilityTrigger`),
  mais son `ShouldTrigger` finit sur le même `AreEntitiesAdjacent`.
* **L'ORDRE de la garde de position dans `is_melee_attack`** : le natif branche AVANT de lire toute
  position, donc une ability `attackRangeType: Melee` interrogée sans position rend `true` côté natif
  et `false` ici. Écart **antérieur** et **non touché** — c'est un axe différent (résidu `#10024-r1`).
* Le nombre de **tuiles** des 6 unités à `NumberOfMembers > 1` du seed BC n'est pas mesuré : le champ
  compte des *membres*, pas des pieds, et rien n'établit l'égalité.

## Résidus

* **#10024-r1** — `is_melee_attack` teste ses positions AVANT le switch, le natif après. Une ability
  `attackRangeType: Melee` / `Ranged` / `None` ne lit **aucune** position côté natif.
  **FOYER:** `scripts/python/engine/services/battle_query.py` — **BLOCAGE:** `aucun`
