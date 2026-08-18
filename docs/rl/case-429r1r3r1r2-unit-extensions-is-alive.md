# #429-r1-r3-r1-r1 + -r2 — La liveness native a TROIS branches, le port n'en lisait qu'une

**Livré le 2026-08-05.** Build de référence : `rnca9r7q6c`.

`#429-r1-r3-r1` avait mesuré la divergence — port **10 375 dégâts** sur une unité que le natif
refuse — et l'avait laissée OUVERTE, gardée par ATTRIBUTION, derrière deux résidus. Les deux sont
fermés ici, et la fermeture a trouvé un **troisième** trou, dans l'écrivain.

## 1. Ce que le natif teste — lu, pas supposé

`IdunBattle.Entities.UnitExtensions$$IsAlive(entity, state)` n'est **pas**
`IdunBattle.Entities.Components.HealthComponent$$IsAlive` (hp ≥ 1) :

```
unit = UnitExtensions.GetUnit(entity, state);            // 3 surcharges : unité / tuile / pied
if (unit == null) return EntityExtensions.GetEntityType(entity) == 6;   // EntityType.Machine
if (UnitFlagsComponent.Has(unit.UnitFlags, 6)) return false;           // UnitFlag.Dead
if (!state.GetPool(0).Contains(unit))          return false;           // EntityPool.AliveUnits
return HealthComponent.IsAlive(unit.Health);
```

Les trois constantes sont **lues** dans `data/symbols/<build>/frida/enums.tsv` :
`IdunBattle.Entities.Enum.UnitFlag` → `6=Dead` ; `IdunBattle.Entities.Enum.EntityPool` →
`0=AliveUnits` — le **même** accesseur sert `1=DefeatedUnits` à
`IdunBattle.Core.Services.BattleQuery$$GetAllDeadUnits` et `8=AllUnits` à `$$GetAllUnits`, ce qui
identifie le slot sans ambiguïté ; `IdunBattle.Entities.Enum.EntityType` → `6=Machine`.

Le pool n'a que **deux** écrivains : `IdunBattle.Operations.FleeOperation$$Execute` (ajout à
`DefeatedUnits`) et `IdunBattle.Operations.ResurrectUnitOperation$$UpdatePools` (retrait de
`DefeatedUnits`, ajout à `AliveUnits`).

## 2. Le porteur offline de la branche POOL existait déjà — personne ne le lisait

`UnitComponent.alive`. Ce n'est pas une approximation : le canal live qui le seede **EST** cette
fonction native — `decisionView` publie `alive: invokeBool(isAliveMi, [e, statePtr])`
(`frida/hooks/features/ai-step/projection.ts`), `isAliveMi` étant `UnitExtensions$$IsAlive`. Le
mirror `unit_extensions_is_alive` (`engine/runner/components.py`) enchaîne donc les trois branches
sur des porteurs qui existaient tous.

**Deux lecteurs** sont routés par lui — les deux, et seulement les deux, dont le décompilé appelle
littéralement ce service :

| lecteur porté | fonction native |
|---|---|
| `components.unit_is_dead` | `UnitExtensions$$IsDead` = `!IsAlive(u, state) && !HasFlag(u, 9)` |
| `operations/active_ability.is_dead_unit_and_not_allowed_by_ability` | `ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility` |

`is_alive_and_not_fled` n'en fait **pas** partie, et c'est lu : `UnitExtensions$$IsAliveAndNotFled`
va chercher `HealthComponent$$IsDead` directement. La contre-épreuve du probe porte sur ce **nom**,
pas sur un seuil.

## 3. La confrontation — et la branche qui mord est ISOLÉE

Régime FLED (trait `BattleFatigue` → `FleeOperation`, seul écrivain du flag 9). Montage : foyer
partagé `installer_regime_fled` (sorti de `#429-r1-r3-r1`, plus aucune duplication).

| | MC1_67 / 777 | C1_74 / 777 (spawn NATUREL) |
|---|---|---|
| flags natifs de l'enfui | **`[9, 26]`** | **`[9, 26]`** |
| `hp` | 1000 / 1000 | 1000 / 1000 |
| dans `combatSnapshot.units` | non | non |
| dans `unitsNotAlive` | **oui** | **oui** |
| natif, cast sur l'enfui | **0** événement | **0** événement |
| témoin (cible vivante) | 2 événements, groupe `[12]` | 2 événements, groupe `[12]` |
| port nominal | refus, `not_alive_and_not_fled = "target"` | idem |
| gate de MESSAGE seul débranché | **refus**, `dead_target_not_allowed = True` | idem |
| les DEUX débranchés | **10 375** | **9 797** |

Le flag `Dead` (6) est **absent** et les PV sont **pleins** : ni l'une ni l'autre des deux branches
observables ne peut expliquer le refus natif. Reste le pool — et c'est vérifié **par mutation sur
l'état live réel**, pas sur un état fabriqué :

| mutation | `unit_extensions_is_alive` | attaque, gate de MESSAGE débranché |
|---|---|---|
| aucune | `False` | refus |
| `uc.alive = True` (l'unité **rentre** dans le pool) | **`True`** | **10 375** |
| … puis `UnitFlag.Dead` posé | **`False`** | refus |

Les trois branches sont donc exercées, et chacune **discrimine**.

Sur le même état, les deux mirrors de liveness du port **divergent** :
`HealthComponent$$IsAlive` → `True`, `UnitExtensions$$IsAlive` → `False`. `unit_is_dead` reste
`False` — `IsDead` exclut expressément `Fled`, et router la liveness ne transforme pas un enfui en
mort.

## 4. Le canal — l'absence se DIT, elle ne se devine pas

`combatSnapshot.unitsNotAlive` est déployé et lu. Ce qui manquait était le **tri-état** : le
lecteur faisait `snapshot.get("unitsNotAlive") or []`, qui rend la même chose pour « lu, aucune
entité non vivante » et pour « le bundle ne porte pas le champ ». `_load_unit_flags` écrit
désormais `state.unit_flags_seed` :

| snapshot | `units_not_alive_channel` | `units_not_alive` |
|---|---|---|
| champ absent (bundle antérieur) | `"absent"` | `None` |
| champ à `null` (capteur non résolu) | `"muet"` | `None` |
| champ à `[]` | `"lu"` | `0` |
| champ peuplé | `"lu"` | *n* |

**Aucun chemin ne fabrique un zéro** — même règle que `host_inputs.py`. Mesure live :
`{'units': 1, 'units_not_alive': 4, 'units_not_alive_channel': 'lu'}`.

⚠ Le probe partagé lisait lui aussi `units` seul : `_flags_par_unite` parcourt désormais les deux
blocs, et `canal_units_not_alive` nomme l'état du bloc.

## 5. Trouvé en chemin — l'ÉCRIVAIN de la branche manquait, et un gate écrit était INERTE

Un mirror de liveness ne vaut que si l'opération qui **sort** l'unité du pool le fait aussi
offline. Le `FleeOperation` porté ne posait que le flag 9.

Le décompilé de `FleeOperation$$Execute` enchaîne, **dans cet ordre** :
`OperationProcessor.RemoveUnit(unit, removeEffects: 0, param4: 1)` (slot **6**, celui de
`Core.Services.OperationProcessor$$RemoveUnit` → `IdunBattle.Operations.RemoveUnitOperation$$Execute`,
**unique appelant de code** de cette Operation) → `AddToPools(unit, [DefeatedUnits])` →
`UnitFlagsComponent.Add(unit, 9)`. La mesure le corrobore : l'enfui porte **`26 = UnitFlag.Removed`**,
qui n'a qu'**un** poseur dans tout le binaire.

Conséquence en cascade, et c'est le **rouge** qu'il fallait attribuer :
`test_cosmic_horror_on_kill_retriggers_battle_fatigue_only_on_carriers` exigeait `Pinned` sur les
deux bystanders. L'arbre natif est `TriggerAbility(0x401) & IfAlive(subject, AddEffect(0x429))` —
le gate `IfAlive` est **après** le re-trigger. Le port l'avait écrit, avec une docstring qui
affirmait que « la victime qui fuit reste vivante » : cette phrase est **réfutée par la mesure**. Le
gate était donc écrit mais **inerte**, et le test avait figé l'état inerte. Le test asserte
désormais l'inverse — porteur enfui **non** `Pinned`, non-porteur (qui n'a pas fui) `Pinned` : une
assertion **plus forte**, et discriminante.

## 6. Les gardes

`tests/engine/runner/test_429r1r3r1r2_unit_extensions_is_alive_live.py` — **11 tests, ~40 s** :
périmètre du mirror (routés + contre-épreuve par NOM), tri-état du canal (4 cas, aucun zéro
fabriqué), l'écrivain en rollout **pur** (offline, sans runner), puis le live — le canal, la branche
attribuée, les deux étages qui divergent, l'accord natif/port et la décomposition par étage avec sa
contre-épreuve.

Re-joués **après** le fix : `test_429r1r3r1_message_gate_perimeter_live` (11),
`test_429r1r3_dead_target_message_gate_live` (12), `test_429r1r1_normal_attack_dead_target_live` (7),
`test_429r1_dead_target_gate_live` (7), `test_429r1r1r1_ability_attack_dead_target_live` (9),
`test_unit_flags_live` (3), `test_runner_attack_live` (2), `test_dead_attacker_noop_live` (3),
`test_ability_target_gate_live` (13), `test_battle_fatigue_object_or_steppable_offline` (11),
`test_black_legion_1029_1020_live` (10), `test_448_r1_r1_r2_r1_dsl_after_move_offline` (16),
`test_cosmic_horror_live` (6), `test_fear_of_the_unseen_live` (4), `test_ai_approach_live` (4).

## 7. Ce qui n'est PAS couvert

* **Deux tests ROUGES PRÉEXISTANTS**, sans rapport avec cette tranche et **mesurés comme tels** :
  `test_448_r2c_fear_of_the_unseen_live.py::test_at_remaining_one_the_step_poses_1241_then_lands_the_carrier`
  et `::test_a_second_step_no_longer_poses_the_moving_marker` rendent **2 failed / 2 passed** avec le
  moteur remis à `origin/master` (les six fichiers touchés remis un par un, puis restaurés).
* **La branche MACHINE n'est pas confrontée** : elle est portée telle quelle (`MachineComponent`
  présent ⇒ toujours vivante, mirror du `EntityType == Machine` natif) et **préserve à l'identique**
  le comportement d'avant (une MoW n'a aucun `HealthComponent`, donc l'ancien `unit_is_alive`
  rendait déjà `True`). Aucun régime live ne l'exerce ici.
* **La distinction `pool` / `GetUnit == null`** n'est pas séparée : sur une unité, `GetUnit` rend
  toujours l'entité, donc la question ne se pose que pour les tuiles et les pieds — hors régime.
* **`get_tiles` / `get_unit`** (`operations/active_ability.py`) continuent d'utiliser
  `HealthComponent$$IsAlive`. C'est **délibéré** : `IdunBattle.Entities.EntityExtensions$$GetTiles`
  = `IterateTiles(entity, state)`, **sans aucun gate de liveness** — leur usage du prédicat est une
  convention d'occupation du port, pas un mirror. Les router y fabriquerait un refus que le natif ne
  fait pas. (Le natif garde d'ailleurs le `UnitFootComponent.TileId` d'un cadavre, cf. `case-429r1r3`
  — l'écart y est *inverse* et préexistant.)
* **Un seul régime** exerce la branche pool en live (FLED) ; il est confronté sur **deux boards**
  (MC1_67 avec placements, C1_74 en **spawn naturel**) mais **un seul seed utile** (777 ; 31337 et
  123 ne produisent aucune fuite, re-mesuré). Le régime RETIRÉ-SANS-FUITE (`RemoveUnitOperation`
  seule) n'est pas confronté.

## 8. Résidu nommé — **FERMÉ le 2026-08-18, et l'énoncé ci-dessous se trompait deux fois**

> **`#429-r1-r3-r1-r2-r1` est CLOS.** Le déplacement est retiré (`_safest_tile` supprimé avec son
> unique appel et quatre imports), après relecture *complète* de
> `IdunBattle.Operations.FleeOperation$$Execute` : aucun `MoveUnit`, aucun `SetUnitPosition`, et
> **rien à la place** — l'unité vient d'être retirée du plateau, sa position n'a plus de lecteur.
>
> ⚠ **Mais les deux affirmations soulignées plus bas sont FAUSSES, mesuré.** « Il la mute quand
> même » : NON — depuis cette tranche même, `RemoveUnitOperation` pose
> `UnitComponent.alive = False`, et le `MoveUnitOperation` qui suivait tombait sur le bras `IsDead`
> du gate d'override (`last_abandoned == "override-unit-dead"`). Et donc « elle rougit
> aujourd'hui » : NON — le retournement proposé était **vert dès le premier jour**.
>
> C'était un **accident de collapse, et pour une raison fausse** :
> `IdunBattle.Entities.UnitExtensions$$IsDead` teste `HasFlag(unit, 6 = Dead)`, pas `Removed`, et
> une enfuie garde ses PV pleins — côté natif ce gate ne mordrait pas. Le comportement juste
> reposait donc sur un gate qui n'a rien à voir avec lui.
>
> **Le cran posé porte sur l'APPEL**, pas sur la position : `--volet flee` compte les constructions
> de `MoveUnitOperation` pendant `FleeOperation.execute` (`1 → 0`), avec témoin non dégénéré, et la
> substitution est posée sur `MoveUnitOperation.__init__` — la **classe** — parce que patcher
> l'attribut du module `behaviour` aurait cessé de mordre à l'instant où l'import disparaît.
> Détail : `docs/rl/case-589r2r1r1-le-gate-etait-du-mauvais-cote.md` §5.3.

*Énoncé d'origine, conservé pour ce qu'il enseigne :*

* **`#429-r1-r3-r1-r2-r1` — le DÉPLACEMENT de fuite du port n'existe pas en natif.**
  `FleeOperation.execute` déplace l'enfui vers `_safest_tile` ; le décompilé de
  `FleeOperation$$Execute` n'appelle **ni** le slot `MoveUnit` **ni** `SetUnitPosition` (le port le
  dit déjà lui-même), et la mesure live le confirme sur **deux boards** : la position publiée de
  l'enfui est **identique** avant et après (MC1_67 : `(1,4)` → `(1,4)` ; C1_74 : `(4,1)` → `(4,1)`).
  Depuis cette tranche l'unité est de toute façon retirée du plateau, donc ce déplacement mute une
  position que plus rien ne devrait lire — mais il la mute quand même.
  **Condition de retournement exécutable** :
  ```
  python scripts/python/probe_429r1r3r1r2_unit_extensions_is_alive.py --volet flee
  ```
  ajouter à `volet_flee` l'assertion « la position de l'enfuie est INCHANGÉE après
  `FleeOperation.execute` » ; elle rougit aujourd'hui, elle passera quand le déplacement sera retiré.

## 9. Re-dériver

```
python scripts/python/probe_429r1r3r1r2_unit_extensions_is_alive.py --volet scan
python scripts/python/probe_429r1r3r1r2_unit_extensions_is_alive.py --volet trietat
python scripts/python/probe_429r1r3r1r2_unit_extensions_is_alive.py --volet flee
python scripts/python/probe_429r1r3r1r2_unit_extensions_is_alive.py --volet fled --state-file <ABSOLU>
python scripts/python/probe_429r1r3r1r2_unit_extensions_is_alive.py --volet fled --sans-place --board C1_74 --state-file <ABSOLU>
python -m pytest tests/engine/runner/test_429r1r3r1r2_unit_extensions_is_alive_live.py -q
```
