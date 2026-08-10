# #5 — `DslContext` live-state : l'état MESURÉ, et pourquoi « architecture à poser » est périmé

**Mesuré le 2026-08-10.** Probe versionné : `scripts/python/probe_5_dslcontext_live_state.py`
(quatre étages, périmètre dérivé de `git ls-files`). Aucune refonte de `engine/dsl/base.py` :
la mesure dit qu'il n'y en a pas à faire.

## 1. Ce que la ligne de backlog annonçait

« Chantier `DslContext` live-state — **Architecture à poser, pas d'énigme à trancher** »,
`FOYER: scripts/python/engine/dsl/base.py`. La fiche pointée
(`docs/rl/dsl-live-context-substrate.md`) déclare son état au **2026-07-18** : « Voie A
IMPLÉMENTÉE (fondation + 1er cas) », « RESTE (généralisation) : seul le contexte RUNNER est live ;
la surface T/S entière le devient **cas-par-cas** ».

## 2. Ce que la mesure rend

| étage | mesure |
|---|---|
| rayon de souffle de `engine/dsl/base.py` | **100** fichiers importateurs, **22** symboles distincts |
| dont `DslContext` lui-même | **5** lecteurs directs |
| dont `Const` / `TargetsSelector` | **73** / **29** lecteurs |
| voie A — `LiveUnit` | **1** définition (`runner/abilities/behaviours/context.py`), **4** constructions |
| producteurs de contexte | **12** constructions `DslContext(...)` (**10** avec `board`), **20** dérivations `replace(...)` |
| `Cache` (fige l'IDENTITÉ, pas la position) | **1** définition (`entities/selectors/geometry.py`), **26** usages |

**Le chiffre qui débloque tout** : le socle est importé par 100 fichiers, mais le **contrat de
contexte** n'a que **5 lecteurs directs**. Ajouter un champ à `DslContext` (défaut `None`) est donc
une opération à 5 sites, pas à 100 — les 95 autres consomment `Const`, `TargetsSelector`, `_pos`,
`_feet`, etc., qui ne bougent pas. C'est exactement ce que la tranche #433-r3-r2 de ce même agent a
fait sans rien casser.

## 3. Verdict : l'énoncé est PÉRIMÉ, et le reste n'est pas une architecture

Les **deux** moitiés du modèle à deux modes que la fiche prescrit sont **en place** :

- **position live par référence** — `LiveUnit` existe et est construite (4 sites) ;
- **identité figée EXPLICITEMENT** — `Cache` existe et compte **26** usages, c'est-à-dire qu'il
  n'est plus « absent du port » comme la fiche l'écrivait, mais largement adopté.

Ce qui reste est ce que la fiche appelle elle-même « **généralisation cas-par-cas** » : chaque
ability qui mute puis re-teste. Ce n'est **pas** une architecture à poser — c'est une suite de
tranches, chacune bornée à son ability, et chacune déjà outillée par la fondation.

**Conséquence de dispatch** : `#5` ne doit plus partir comme un chantier de socle. Il doit être
soit refermé, soit ré-ouvert sous la forme d'un inventaire des abilities « mutate-then-predicate »
non repliées — et cet inventaire-là **ne se dérive pas à l'AST** (le probe le dit dans sa portée :
il ne sait pas distinguer une composition repliée en arbre d'une recâblée à la main ; ce tri se
fait au décompilé).

## 4. Ce qui n'est PAS couvert

- Le probe compte des **sites**, pas des comportements : un import n'est pas un usage, et un
  `DslContext` construit n'est pas un arbre évalué.
- Le **type** du premier argument d'un `replace(...)` n'est pas décidable à l'AST : les 20 sites
  sont **listés, jamais attribués**. Les prendre pour des `DslContext` serait un majorant présenté
  comme une mesure.
- ⚠ **Le recenseur a d'abord sous-compté**, et c'est instructif : en ne visitant que les appels
  **nus** `DslContext(...)`, il rendait **5** là où le dépôt en porte **12**, et il était
  totalement aveugle aux **20** dérivations. Réparé en dérivant le nom appelé (`ast.Name` **ou**
  `ast.Attribute`) et en ajoutant la voie `replace`. Même vice que celui recensé dans le CLAUDE.md
  pour les littéraux d'enum — un recenseur ne rend pas zéro sur ce qu'il ne visite pas.
- Aucune confrontation live : ce chantier n'a pas de face observable propre.
