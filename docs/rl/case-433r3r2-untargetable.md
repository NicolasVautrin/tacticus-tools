# #433-r3-r2 — le volet `Untargetable` du `UnitSelectionType`, et le canal qui aurait été inerte

**Livré le 2026-08-10** (build `rnca9r7q6c`). Foyers :
`scripts/python/engine/entities/unit_selection_type.py`,
`scripts/python/engine/entities/triggers.py`,
`scripts/python/engine/entities/selectors/units.py`. Garde :
`scripts/python/tests/engine/test_433r3r2_untargetable_offline.py`.

## 1. La ligne de backlog était périmée sur son verbe

Elle disait « **STOCKÉ mais non CONSOMMÉ** » et prescrivait « le nœud le garde INERTE et documenté ».
Faux depuis #524, qui avait porté le volet `IsAlive`. Ce qui restait est le second volet,
`!HasFlag(unit, UnitFlag.Untargetable)` — et la docstring du nœud le lisait comme un no-op bénin.

## 2. Le trou était exactement là où il coûte le plus

`IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType` :

```
if (selectionType == OnlyAlive)              return IsAlive(unit, state);
if (selectionType == OnlyTargetable)         return !HasFlag(unit, 0x11);
if (selectionType == OnlyAliveAndTargetable) return IsAlive(unit, state) && !HasFlag(unit, 0x11);
return true;                                 // Any
```

`OnlyTargetable` (2) **n'appelle pas `IsAlive`**. Pour ce `selectionType`, le seul filtre natif était
donc précisément le seul que le port n'avait pas : le nœud ne filtrait **rien du tout**. C'est le
régime de `runner/operations/behaviour.py`
(`IdunBattleLogic.Entities.Abilities.Active.Loki.BattleFatigueAbility$$CreateTrigger` →
`IsAdjacent(self@+0x30, dying@+0x60, 2)`).

La docstring d'avant tirait de ce trou une conclusion rassurante — « les trois call-sites qui passent
`2` sont INCHANGÉS » — qui était vraie, et qui était le défaut.

## 3. Un TROISIÈME port du prédicat, et le foyer hissé

Le prédicat existait déjà **deux** fois : `matches_unit_selection_type` (foyer #524, face DÉCISION)
et le dérivateur runner `selectors/units.py::_selection_ok` (#585-r1), dont la docstring écrivait
« un SECOND port du prédicat aurait été un fork ». Le nœud `IsAdjacent` en avait pourtant écrit un
**troisième**, à la main, structurellement aveugle au flag.

Le dérivateur est **hissé** dans `entities/unit_selection_type.py::selection_ok_from_ctx` — la
**feuille** de l'enum (3 modules `engine.*` dans sa cascade, contre 108 pour `aura_selectors`).
C'est ce qui permet aux deux consommateurs de le partager **sans créer d'arête**.
`_selection_ok` reste comme alias mince pour ses lecteurs.

## 4. Le piège : `has_unit_flag` seul aurait été INERTE — mesuré

Le canal direct `ctx.has_unit_flag` (mirror
`IdunBattle.Entities.Components.UnitFlagsComponent$$Has`) existe et **répond**. Mais **aucun chemin
du port n'inscrit `0x11`** : côté natif le flag est posé par
`IdunBattle.Entities.Effects.Common.UntargetableEffect$$ApplyInternal` et retiré par
`$$RevertInternal` ; côté port, cette base est modélisée par le **domaine** de ses `EffectType`
dérivés (`UNTARGETABLE_EFFECT_TYPES`, foyer unique de `entities/effects/aura_selectors.py`).

Un dérivateur qui n'aurait lu que `has_unit_flag` aurait donc rendu `targetable = True` **partout** —
c'est-à-dire une **mesure affirmée à tort**, pire qu'une non-mesure puisqu'elle ferme le tri-état.
Le fix aurait été vert sur ses propres gardes et mort en live.

Les **deux** canaux sont donc lus, en OU (ils décrivent la même chose côté natif — l'un est posé par
l'autre) :

1. `ctx.has_unit_flag(unit, Untargetable)` — fait autorité s'il rend VRAI ; le jour où le port
   posera le flag, rien ne changera ici ;
2. `ctx.has_effect(unit, <type>)` sur `UNTARGETABLE_EFFECT_TYPES` — le canal **porté aujourd'hui**,
   le même que lit `playbook/adjacency.py::is_targetable` côté DÉCISION.

Tri-état préservé : aucun des deux branché ⇒ `targetable = None` = **PAS MESURÉ**, et
`matches_unit_selection_type` dégrade la clause en VRAI. Un contexte sans canal (face DÉCISION,
arbre de test) se comporte comme avant, bit pour bit.

L'import de `UNTARGETABLE_EFFECT_TYPES` est **différé** et le différé est classé **PORTEUR** par le
protocole : charger `aura_selectors` seul dans un process frais charge `unit_selection_type` — hisser
fermerait un cycle. Coût mesuré en prime : 3 → 108 modules.

## 5. Rayon de souffle, validation, et ce qui n'est PAS couvert

**Rayon mesuré** (AST sur `engine/**`) : **50 call-sites** passent un `selection_type` explicite —
`UnitsWithTrait` 20, `UnitsWithoutTrait` 15, `Friends` 8, `IsAdjacent` 4, `Units` 2,
`MechanicalUnits` 1. Tous gagnent le volet `Untargetable` par le foyer partagé. La dégradation qu'ils
portaient était **permissive** (le port comptait une unité en deep-strike que le natif écarte).

**9 gardes offline**, `4 mutations / 4 rouges` (vues avant le fix) :

| mutation | rouges | message |
|---|---|---|
| filtre `IsAlive` local restauré | 2 | `assert True is False` + `le noeud doit PASSER PAR le foyer, pas seulement l'importer / assert []` |
| tri-état rabattu (`targetable = False`) | 1 | `assert False is True` |
| canal d'effets coupé | 1 | `assert True is False` (étage 2bis) |

⚠ L'étage 4 a d'abord été **inerte** : il comparait les identités (`triggers.selection_ok_from_ctx is
<foyer>`) et restait vert sous la mutation qui remet le filtre local — l'import survit à la scission
de l'usage, donc il ne prouvait rien. Il vérifie désormais l'**appel** (espion posé sur le binding
du module consommateur).

Non-régression, offline : `test_419r1tr14r5r2r1r1r1r3_should_execute_gates`, `test_524r1_bond_sous_effets`,
`test_433_r4_r2_adjacency_foyer`, `test_433r4r1r4_elevation_gate_dsl`,
`test_462_r4b_r1_r1_r1_r1_bond_removal`, `test_365_selector_montage` → **101 passed**.
`probe_433_r3_isadjacent_node.py --offline` → **OK / rc 0**.

**NON COUVERT :**

- **`#433-r3-r2-r1`** — le port n'inscrit **jamais** `UnitFlag.Untargetable` dans
  `UnitFlagsComponent`. Le canal direct reste donc muet, et toute la non-ciblabilité passe par le
  domaine d'effets, qui est un **sous-ensemble CONFRONTÉ** (3 `EffectType` sur les 5+ dérivées
  natives d'`UntargetableEffect` : `1573` et `JustSummonedEffect` en sont dehors, pour des raisons
  distinctes déjà écrites dans `aura_selectors.py`). Foyers hors de cette tranche.
- **Aucune confrontation LIVE.** Le régime discriminant exige une unité en deep-strike adjacente au
  caster au moment où un nœud `IsAdjacent(…, 2 ou 3)` s'évalue. Il est atteignable (les porteurs de
  `TeleportStrike` sont au pool rank 17) mais le montage n'a pas été joué ici.
- Le **quantificateur** d'`IsCharging` (`#433-r3-r1b`) devient portable maintenant que le filtre
  existe — la docstring du nœud le nommait comme dépendant de ce résidu. Non fait.
- **Rouge PRÉEXISTANT de `master` rencontré au passage** :
  `test_448_r1_stormboyz_port_offline.py::test_O2_le_noeud_SortTilesByUtility_se_RE_EVALUE` —
  `TypeError: <lambda>() takes from 3 to 4 positional arguments but 5 were given`
  (`engine/selectors/tiles.py:369` passe 5 arguments à `ctx.sort_tiles_by_utility`, le stub du test
  en accepte 4). **Contre-épreuve faite sur l'arbre témoin `3f552f5e`** : message identique. Sans
  rapport avec cette tranche ; foyer `entities/selectors/tiles.py`.
