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

### 3bis. Généralisation — autre board, autre empreinte, et l'axe INVERSE

**Board `MC1_67`, seed `31337`, `--place "ultraTitus:3,5"`** (l'unité est DÉPLACÉE pour forcer la
configuration, pas laissée où le spawn la met), Galatian posé aux pieds `(1,4) (2,4) (1,5)` :

| tuile | natif | port APRÈS | port AVANT |
|---|---|---|---|
| `(3,5)` `(2,5)` `(3,4)` | `True` | `True` | **`False`** |
| `(2,3)` | `True` | `True` | `True` |
| `(3,3)` `(3,6)` `(2,6)` `(2,2)` | `False` | `False` | `False` |

**8 accords natif == port sur 8**, dont **4 témoins négatifs**, et **3** divergences de l'ancien
régime — sur une empreinte et un board différents du premier montage.

**Axe INVERSE — le caster est multi-hex.** `--tuiles current` interroge
`unitPositionCurrent(caster)` = `GetUnitPosition` = l'empreinte. Galatian **caster**
(`AncientFury_NormalAttack`) contre `ultraTitus` mono-tuile en `(3,5)` : natif `True`, port APRÈS
`True`, port AVANT **`False`**. Témoin négatif du même axe (`ultraCalgar` en `(0,2)`) : `False`
partout — et le probe **refuse alors de conclure** (« contre-épreuve vide »), ce qui est le
comportement voulu : un montage qui ne discrimine pas ne rend pas un vert.

Les **deux bouts** de la surcharge `AreEntitiesAdjacent(tiles, unit)` sont donc confrontés : le
`tiles` (position du caster) et le `unit` (dont le natif prend `GetTiles`).

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

* ~~**#10024-r1**~~ — **RÉSOLU (2026-08-18).** La garde de position est descendue sur la branche
  `Normal(3)`, la seule qui lise une position. Le décompilé confirme la fiche : `if (iVar1 == 1)
  return 1;` sort **avant** le `HasFlag(caster, 0x15)`, et `Ranged(2)` / `None(0)` retombent sur le
  `return` final — aucune de ces trois cases ne touche une position. Seul comportement changé :
  `attackRangeType: Melee` + position(s) `None` rend désormais `True`. Cliquet
  `tests/engine/runner/test_10024r1_ordre_des_etages_offline.py` (6 étages, 28 tests), vu **rouge
  par mutation** (7 failed / 21 passed) — dont l'étage 4, un invariant **AST**, seul capable de
  mordre sur un réordonnancement, et l'étage 5bis qui exige que la divergence soit *exactement*
  `Melee` sans position. Résidu ouvert : **#10024-r2**.
* **#10024-r2** — **le fix de #10024-r1 est INERTE à l'étage des appelants.** Recensement fait
  pendant la tranche : `runner/battle_query_state.is_melee_attack` (le plus gros rayon — face
  COMBAT et `damage_utility`) et `playbook/light_im_up.is_melee_attack` portent **leur propre**
  garde de position, en tête, avant d'entrer dans le foyer ; seul `playbook/heavy_bolt_pistol`
  appelle sans garde. La faute est donc reproduite un étage plus haut, sur des sites hors du foyer
  déclaré ici. ⚠ Ce qui reste à établir avant de les déplacer : le natif déréférence
  `casterPosition` **sans garde**, donc une position absente n'existe pas de son côté (une unité en
  bataille a toujours des tuiles). Ces gardes protègent un régime **dégénéré du port**, pas un
  régime natif — les retirer changerait un verdict que rien ne mesure.
  **FOYER:** `scripts/python/engine/runner/battle_query_state.py`,
  `scripts/python/engine/playbook/light_im_up.py` — **BLOCAGE:** `porteur`
