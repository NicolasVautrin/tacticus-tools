# #433-r3 — le nœud DSL `IsAdjacent` est un UNIVERSEL, et il porte la porte d'ÉLÉVATION

**Verdict : QUIRK PORTÉ, trois termes.** Le terme d'**élévation** est CONFRONTÉ LIVE, sur deux
géométries distinctes. Le **quantificateur** et l'**identité** sont portés par fidélité et
discriminés hors-natif : aucun call-site natif lu ne les atteint, et c'est dit comme tel (§5).

## 1. Le fait natif, lu

`IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$ShouldTrigger`, transcrit du décompilé :

```
A = <sel a>.Select(entities, selectionType)      // slot 3 ; ctor : a@+0x20, b@+0x28,
B = <sel b>.Select(entities, selectionType)      //          selectionType@+0x18, query@+0x10
if (A == null || B == null) throw;
if (!A.Any() || !B.Any()) return false;
foreach (x in A) foreach (y in B)
    if (!query.AreEntitiesAdjacent(x, y)) return false;      // slot 0x60
return true;
```

Le `.ctor` est lisible tel quel (`IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$.ctor`),
et son unique appelant est `IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent(a, b, selectionType)`,
qui lui passe le `query` pris sur la factory.

Trois lectures, chacune contre le port d'avant :

* **QUANTIFICATEUR UNIVERSEL.** La sortie `1` est atteinte quand le `MoveNext` de l'énumérateur de
  `A` rend faux — c'est-à-dire quand l'énumération s'ÉPUISE sans échec ; l'unique autre sortie
  (`return uVar9 & 0xff…00`, donc faux) est prise dès qu'une paire échoue. `forall`, pas `exists`.
  Le port faisait `any(...)` : divergence **PERMISSIVE** — il déclenchait des triggers que le natif
  refuse, sans erreur ni crash.
  ⚠ La classe **SŒUR** `IdunBattle.Entities.Triggers.IsAdjacentTilesTrigger$$ShouldTrigger` (celle
  du vslot 0x748 Titanhammer) est, elle, un `exists` : elle `return 1` dès la première paire
  adjacente. Les deux ne se déduisent pas l'une de l'autre — elles se LISENT.
* **Le vide n'est pas le `All` de C#.** Le natif teste `Any()` sur les DEUX listes AVANT la boucle
  et rend **faux** ; un `all(...)` nu rendrait **vrai** sur une liste vide. Les listes `null`, elles,
  LÈVENT.
* **La comparaison par paire est `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent`,
  surcharge `(entity1, entity2)`** — donc `AreTilesAdjacent(GetTiles(x), GetTiles(y))`, donc
  `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent` scalaire
  = `(|dElev| < 2) & (t1 == t2 || ConnectivityComponent$$IsNeighbour(t1, t2))` : **porte
  d'élévation** ET **court-circuit d'identité**, tous deux absents du port d'avant (#433-r1).

### Quelle surcharge ? le slot 0x60, tranché par DEUX lectures indépendantes

Les trois surcharges de `BattleQuery$$AreEntitiesAdjacent` sont `(IList, IList)`, `(IList, entity)`
et `(entity, entity)`. Le trigger appelle le **slot 0x60** avec deux `get_Current` d'énumérateurs
de sélecteurs — donc deux **entités nues** : seule la surcharge `(entity1, entity2)` a cette
signature. Recoupé indépendamment par (a) `IdunBattle.View.FSM.VisualBattleQuery$$AreAdjacent`, qui
résout deux vues en deux ENTITÉS avant d'appeler ce même slot ; (b) l'ordre des trois lambdas du
décorateur `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery`
(`u003Cu003Ec__DisplayClass117_0/118_0/119_0$$u003CAreEntitiesAdjacentu003Eb__0` → slots
`0x60/0x61/0x62`), dont l'ordre des DisplayClass suit celui des wrappers `(entity,entity)`,
`(IList,entity)`, `(IList,IList)`.

⚠ **Le commentaire de `runner/abilities/targeting.py` qui écrit `0x5f/0x60/0x61` est daté d'un build
antérieur** : sur `rnca9r7q6c` le groupe a glissé d'un cran (`0x60/0x61/0x62`). L'assignation
surcharge↔rang qu'il donne est, elle, **inchangée** — c'est un décalage uniforme, pas une erreur de
lecture. Non corrigé ici (hors périmètre) : résidu `#433-r3-r3`.

### Le 3e argument va au SÉLECTEUR, pas au prédicat

`selectionType` (`UnitSelectionType`, champ `+0x18`) n'est lu QUE comme 2e argument du `Select` des
deux sélecteurs (slot 3). Il n'entre pas dans la comparaison par paire. Le port le prend au
constructeur pour mirrorer la signature native et le garder **inerte** — c'est ce qui rend la faute
anticipée par `#433-r1` (« ne le câble pas dans la comparaison ») visible plutôt que possible.
La couche sélecteur du port ne consomme pas encore le `UnitSelectionType` : résidu `#433-r3-r2`.

## 2. Le port

`engine/entities/triggers.py::IsAdjacent` — `forall` sur le produit, `not pa or not pb → False`,
et chaque paire tranchée par **`engine/services/battle_query.py::are_tiles_adjacent(a, b, board)`**,
le foyer déjà posé par #433-r1 (identité + élévation avec board ; adjacence hex pure sans board).
**Aucun 5e mirror d'adjacence n'est créé** — et le contre-exemple de #433-r1 reste intact :
`battle_query.is_adjacent` (mirror d'`IterateAdjacentTiles`) ne rend jamais la tuile source.

### Le board n'avait pas besoin d'être « threadé » — il est déjà là

C'était le verrou annoncé, et la mesure le lève : `dsl/base.py::DslContext` porte **déjà** un champ
`board`, alimenté sur les DEUX faces — `entities_from_state(..., board=state.board)` côté COMBAT
(`runner/abilities/behaviours/context.py`), `board=scene.board` côté DÉCISION
(`playbook/prediction/*`, `playbook/tile_targets.py`, `playbook/resurrection_orb.py`). Les **six**
consommateurs portés du nœud passent tous par l'un des deux. Le nœud lit `ctx.board` ; rien à
câbler chez les appelants.

**Sites qui retombent sur la dégradation sans board**, nommés : `entities/abilities/triggered_ability.py`
(`DslContext()` nu) et `entities/abilities/active_ability.py::_hits_ctx` — deux contextes de
FORMULE (dégât / coups) où aucun `IsAdjacent` n'est construit : branche **inerte**, pas un trou.
Plus tout `DslContext` de test construit sans `board=`.

⚠ La dégradation n'est sûre que sur un board **plat** (`|dElev| = 0 < 2` partout). Elle reste une
DÉGRADATION, jamais un mirror.

### Le mode d'adjacence du `Board` n'est pas neutre

En `adjacency="native_sym"` la porte d'élévation est **déjà bakée** dans le champ `neighbours`
capté (le capteur passe par `TileQuery$$IterateAdjacentTiles`, qui l'applique) ; en `evenq` elle ne
l'est pas. Le natif, lui, la porte dans la primitive, **quelle que soit** la source de voisinage —
donc le port la pose explicitement. C'est pourquoi les montages de mesure (probe et test) sont en
`evenq` : c'est le seul mode où un port qui ignore la porte se distingue d'un port qui la porte.

## 3. Ce qui a été MESURÉ — offline

`probe_433_r3_isadjacent_node.py`, étapes A–E, et le test-garde
`tests/engine/runner/test_433_r3_isadjacent_node_offline.py` (15 tests).

| terme | montage | port |
|---|---|---|
| (Q) quantificateur | `A = {u1 adjacente, u2 loin}`, `B = {cible}` | **False** (`any` rendait True) |
| (Q) témoin | `A = {u1 adjacente}` seule | True |
| (E) élévation | voisine hex à `|dElev|` = 0 / 1 / 2 / 3 | True / True / **False** / **False** |
| (I) identité | `IsAdjacent(x, x)`, y compris sur une tuile à élévation 5 | **True** |
| vide | cible absente, ou entité sans tuile | **False** (un `all` nu rendrait True) |
| 3e argument | `selectionType ∈ {None, 0, 1, 2, 3}` | verdict **invariant** |
| sans board | voisines hex / non voisines / `(x, x)` | True / False / True |

**Les trois corrections MORDENT SÉPARÉMENT** — contre-épreuve par mutation RÉELLE du nœud
(`--mutate` = retour à `any(hexgeo.distance == 1)`) : A(Q), B(E) et C(I) rougissent, chacune pour
son propre motif ; le test-garde tombe à **6 échecs sur 15**. La 4ᵉ (l'inertie du 3ᵉ argument) a sa
propre contre-épreuve, `--mutate-seltype`, qui câble l'argument en seuil de distance : **seule**
l'étape D rougit alors. Une correction qui ne mordrait pas se dirait ; aucune n'est dans ce cas.

## 4. Ce qui a été MESURÉ — LIVE

Consommateur : l'étage MOVE de
`IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour` (1025) =
`If(Not(IsAdjacent(caster, target)), MoveUnit(caster, dest))`. Choisi parce que Celestine **VOLE** :
la destination (tuile libre ring-1 de la cible) est toujours atteignable, donc le régime n'est
jamais rabattu par le pathfinding — le verdict du nœud est le SEUL degré de liberté. Harnais
importé de `probe_165b_sky_strike_border.py` (jamais recopié) ; drive par **chemin de marche** et
non par gradient hex (le pas glouton s'immobilise dans un minimum local au bord d'une falaise —
mesuré sur `C2_02`, la cible restait à `(3,5)`).

| montage | natif | port (livré) | port MUTÉ (`any` + hexgeo) |
|---|---|---|---|
| `MC1_67` — caster `(1,2)` élév. **2**, cible `(1,3)` élév. **4**, dist hex 1 | **CHARGE → `(2,3)`** | `IsAdjacent = False` → `(2,3)` **ACCORD** | `IsAdjacent = True` → `(1,2)` → **DÉSACCORD** |
| `C2_02` — caster `(4,3)` élév. **4**, cible `(5,4)` élév. **2**, dist hex 1 | **CHARGE → `(6,3)`** | → `(6,3)` **ACCORD** | — |
| `MC1_67` TÉMOIN — `(0,0)` et `(0,1)`, élév. **3** toutes deux | **NE BOUGE PAS** | → `(0,0)` **ACCORD** | → `(0,0)` accord |

Le critère est le **déplacement par rapport au port non muté**, pas l'écart au natif.

Le **témoin plat n'est pas décoratif** : sans lui, un port qui rendrait *toujours* `False` passerait
le cran. Deux boards distincts parce que la mécanique est géométrique — un résultat sur un seul
board n'en est pas un.

Que le natif CHARGE sur deux tuiles voisines à `|dElev| = 2` est, en soi, la mesure directe de la
porte : s'il les voyait adjacentes, le `Not(IsAdjacent)` fermerait le move.

## 5. Le quantificateur : porté par FIDÉLITÉ, régime NON ATTEINT — et pourquoi

Aucun call-site natif de `DSLTriggers$$IsAdjacent` ne passe un sélecteur PLURIEL. Lus pour ce cas :
`MedicusMinistorumAbility$$CreateTrigger` (`sel+0x60`, `sel+0x30`),
`SynapticImperativeAbility$$CreateTrigger` (`+0x30`, `+0x60`),
`LifewardsAbility$$CreateTrigger` (`+0x30`, `+0x60`),
`TerrorsLament_HitReductionEffect$$CreateEffectHitsBonusForAttack` (`+0x48`, `+0x30`),
`LegendaryCommander_ExtraHitsEffect$$CreateTargetSelector` (`+0x30`, `+0x68` — le second est le
sujet d'un `Filter`, donc unitaire), et `DSLFormulas$$AttackHits`, dont l'**unique** appelant
(`ExemplarOfHateAbility$$GetAttacker`) passe lui aussi deux champs de bundle. S'y ajoutent les
quinze arbres déjà transcrits côté port (Waaagh, RammingSpeed, VigilanceEternal, SkyStrike,
TheBetrayer, HarlequinsPanoply, HatefulAssault, DrawFire, SwornProtector, BattleFatigue,
Narthecium/TaintedNarthecium, SaviorProtocols, custodes, `ABondEffect`), tous en
`Owner`/`Caster`/`Actor`/`Target`/`Self`/`Parent`.

Sur des singletons `exists ≡ forall`. Le quantificateur est donc porté **parce que le natif le dit**,
et son régime divergent n'est atteint par aucun call-site lu — même forme de verdict que le régime
(I) de #433-r1. L'étape A le discrimine hors-natif ; c'est le maximum disponible, et il est écrit
tel quel plutôt que rabattu en « sans objet ».

## 6. Le cliquet

Le test-garde rejoint l'entrée **`pytest_adjacency`** de `scripts/ratchets.ps1` (le fichier est la
source unique — sa composition n'est pas recopiée ici) : même gisement que #433-r1, coût marginal
quasi nul (offline pur). **Peut rougir, mesuré** : sous mutation RÉELLE du nœud, 6 des 15 tests
tombent, couvrant les trois termes ET la branche sans board.

## 7. Résidus NOMMÉS

* **`#433-r3-r1` — EMPREINTES. FERMÉ pour CINQ nœuds — `docs/rl/case-433-r3-r1-empreintes-dsl.md`.**
  Le natif compare bien `GetTiles(x) × GetTiles(y)`, et `IsInRange`/`IsSurrounding`/`IsCharging`/
  `MinDistance` relèvent du même traitement (chacun LU, aucun déduit d'`IsAdjacent`). Les cinq
  passent désormais par `dsl/base.py::_feet` et par le foyer unique
  `services/battle_query.py::are_entities_adjacent`, qui délègue à
  `runner/abilities/targeting.py::are_entities_adjacent` (#R30). Confronté LIVE (Galatian 3 pieds ×
  `VigilanceEternal`).
  ⚠ Le « comme tous les nœuds frères » écrit ici était une PISTE, et le balayage AST l'a réfutée
  dans les deux sens : le périmètre réel est de **24 nœuds**, pas 4 ; `IsSurrounding` s'est révélé
  être **la même classe native** qu'`IsInRange` ; et `IsInRange` porte un quirk que rien n'annonçait
  (sélecteur vide → VRAI). **14 sélecteurs restent divergents**, classés par gravité dans la
  case-doc (résidu `#433-r3-r1a`) — le foyer est la résolution de l'occupant d'une tuile.
* **`#433-r3-r2` — `UnitSelectionType` non consommé.** Le 3ᵉ argument est stocké et inerte ; la
  couche sélecteur du port n'applique aucun filtre `OnlyAlive`/`OnlyTargetable` à ce titre. Observable
  seulement si un sélecteur pouvait rendre une entité morte ou non ciblable là où le natif la
  filtrerait — ce qui viderait la liste et rendrait FAUX au lieu de VRAI.
* **`#433-r3-r3` — numérotation de slots datée.** Le bloc de commentaire de
  `runner/abilities/targeting.py` annonce `0x5f/0x60/0x61` pour les trois surcharges
  d'`AreEntitiesAdjacent` et `0x7c..0x7f` pour `GetAdjacentEnemies` ; sur `rnca9r7q6c` le premier
  groupe est à `0x60/0x61/0x62`. Décalage uniforme d'un cran, assignation surcharge↔rang inchangée.
  Un balayage des slots d'interface cités en commentaire, au changement de build, reste à faire.
