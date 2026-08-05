# `#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1` — la lecture BRUTE de `ctx.traits` : le patron, inventorié et **ventilé**

**Livré le 2026-08-05**, build `rnca9r7q6c`.
Probe : `scripts/python/probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_r1_substrat_traits.py`
(`--step {inventaire,ventilation,loi,contre}`, **100 % offline**).
Garde : `tests/engine/runner/test_ctx_traits_substrat_ventilation_offline.py` (11).

## 1. Le compte re-dérivé — et l'écart avec l'annonce

La fiche `-r3` annonçait « **54 sites / 29 fichiers** », en disant elle-même que c'était un balayage
approché (la prose des docstrings y comptait). Re-dérivé **par AST** :

| | annoncé (`-r3`) | re-dérivé (`--step inventaire`) |
|---|---|---|
| accès à l'attribut `traits` sous `engine/` | 54 | **66** |
| fichiers | 29 | **31** |
| dont ÉCRITURES (seed `#264`, leaf `AddTrait`) | — | **3** |
| dont le FOYER lui-même | — | **1** |
| **lectures BRUTES** = le gisement | 54 | **62** |

Ne pas recopier ces chiffres non plus : `--step inventaire` les rejoue, et le garde rougit dès
qu'un site apparaît ou disparaît.

## 2. La LOI de ventilation — dérivée, pas prudentielle

La question par site est « le sujet peut-il être une entité chargée **déjà morte** ? ». Elle se
tranche par deux prémisses, toutes deux **vérifiées exécutablement** (`--step loi`) :

* **P1 — `StatsComponent` absent ⟺ `alive == False` AU CHARGEMENT.** Le capteur n'enumère que les
  entités pour lesquelles la méthode native `IsAlive` rend vrai
  (`frida/hooks/features/ai-step/rpc-snapshot.ts`, bloc `allUnits` :
  `if (!invokeBool(isAliveMi, [e, statePtr])) return;`), et `decisionView.units[].alive` **invoque
  la même méthode** (`projection.ts`). Ce n'est donc pas « les morts sont filtrés » par hasard :
  c'est le même prédicat des deux côtés.
* **P2 — aucune voie du port ne rend VIVANTE une entité chargée morte.**
  `IdunBattle.Operations.ReviveUnitOperation$$Execute` n'est atteint que par
  `kill_unit_revive_gate`, donc par une mort **survenue pendant le run** ;
  `IdunBattle.Operations.ResurrectUnitOperation$$Execute` n'est atteint que par
  `EnvAmbushResurrectAbility`, dont `GetUnitsEligibleForResurrect` exige
  `UnitComponent.turn_defeated` — écrit **uniquement** par `AmbushSummonAbility`, à la mort, pendant
  le run. Aucun chargement ne le seede.

⇒ **Un site dont le sujet est gaté VIVANT est INERTE** — pas par précaution, parce que le seul
cadavre du port n'a **aucun chemin vers la vie**. C'est ce corollaire qui rend 39 verdicts
légitimes au lieu de « probablement sans effet ».

## 3. La ventilation (`--step ventilation`, table croisée à l'AST)

| verdict | sites | ce qu'il dit |
|---|---|---|
| `INERTE-VIVANT` | **39** | sujet gaté vivant (loi ci-dessus) |
| `INERTE-FRAIS` | **9** | entité créée pendant le run — `ctx` fabriqué sur place (`spawn.py`) |
| `INERTE-AMONT` | **5** | pour un cadavre, un gate antérieur refuse avant la lecture |
| `INERTE-AVAL` | **2** | lecture atteinte, mais un gate postérieur refuse de toute façon |
| `HORS-ECS` | **3** | le `.traits` ne désigne pas le `UnitContext` d'une entité ECS |
| `WRITE` | **3** | écritures (seed `#264`, leaf `AddTrait`) |
| `FOYER` | **1** | `entity_trait_names` |
| **`INDÉCIDABLE`** | **2** | appelants non énumérés — **non convertis**, résidu `#462-…-r3-r1-r1` |
| **`ATTEIGNABLE`** | **2** | → convertis par cette tranche |

## 4. Les deux sites atteignables — et pourquoi la conversion NAÏVE était une régression

* `runner/operations/triggers/genestealer.py::_valid_dead_decoys`
* `runner/operations/triggers/dispatch/move_death.py::post_unit_kill_triggers_for_move`

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ADecoysAndMisdirectionAbility$$GetValidDeadDecoys`,
relu VERBATIM sur `rnca9r7q6c` :

```
Filter( AllDeadUnits,
          AreFriends(sel@0x30 owner, sel@0x68 it)
        & HasTrait(sel@0x68 it, 0x41d = 1053 Decoy)
        & IsKilledThisTurn(sel@0x68 it)                  <-- NON PORTE
        & AreEqual(Killer(it), sel@0x40)                 <-- NON PORTE
        & Contains(Tiles(sel@0x40), MainTileOfUnits(it)) )
```

Le port **collapse** les deux conjoints manquants en une co-localisation. Or un cadavre **au
chargement** est exactement une unité qui n'a **pas** été tuée ce tour — et la co-localisation ne
l'écarte pas (un mort ne bloque pas l'occupation : le mover peut s'arrêter sur sa tuile). Ce qui
l'écartait, c'était le `set()` de la lecture brute : **par accident, mais dans le bon sens**.
Mesure (`--step contre`, `genesSmnDecoy`) :

```
mort PENDANT le run     : BRUT ['Decoy','Steppable']  FOYER ['Decoy','Steppable','Xenos']  IsKilledThisTurn VRAI
cadavre AU CHARGEMENT   : BRUT []                     FOYER ['Decoy','Steppable','Xenos']  IsKilledThisTurn FAUX
```

Une conversion nue aurait donc fait **blaster** (G2) et **émettre un `On(0x35 = PostUnitKill)`** pour
un kill qui n'a jamais eu lieu. La conversion livrée **nomme** l'exclusion avant de réparer le
substrat :

```python
sc = e.get_component(StatsComponent)
if sc is None:
    continue                                   # collapse d'`IsKilledThisTurn` : cadavre AU CHARGEMENT
traits = entity_trait_names(sc.ctx, uc.visual_id)
```

Value-preserving aujourd'hui, et **robuste demain** : le jour où un `StatsComponent` sera posé sur
les cadavres, l'exclusion ne disparaîtra pas en silence.

## 5. Ce qui n'a **pas** été converti, et pourquoi ce n'est pas de la timidité

Les **60** autres lectures brutes sont laissées telles quelles. Deux raisons, pas une :

1. la loi les rend inertes (le sujet ne peut pas être un cadavre) ;
2. **la conversion n'est pas neutre** : `entity_trait_names` **ajoute** le pseudo-trait de
   grande-alliance quand `ctx.traits_measured` est faux (état construit hors capture, summon —
   `build_summon_context` ne pose pas le drapeau). Un site testant `Imperial`/`Xenos`/`Chaos`
   changerait donc de verdict. Convertir en masse ne serait pas du bruit inoffensif : ce serait un
   changement de comportement non instruit, sur 60 sites.

## 6. Contre-épreuves — 4 mutants, 4 détectés

| mutant | garde |
|---|---|
| A — lecture BRUTE restaurée | **2 rouges** / 11 |
| B — conversion NAÏVE (foyer, sans le gate `IsKilledThisTurn`) | **4 rouges** |
| C — foyer remplacé par une recopie **locale équivalente** | **1 rouge** (volet PROVENANCE, AST) |
| D — prémisse P2 cassée (cadavre-au-chargement ressuscitable) | **1 rouge** |

Le mutant C est l'angle mort mesuré en `#643` puis `#646` : une recopie strictement équivalente est
comportementalement indistinguable, donc **aucun** critère de VALEUR ne peut la voir. Le volet
PROVENANCE (AST, pas grep) exige que la fonction **appelle** `entity_trait_names`.

## 7. Non-régression

| fichier | résultat |
|---|---|
| `test_ctx_traits_substrat_ventilation_offline.py` (neuf) | **11 verts** |
| `test_barbed_ovipositor_object_or_steppable_offline.py` + `battle_fatigue` + `master_tutelaries` | **70 verts** (lot de 4 avec le neuf) |
| `test_decoys_misdirection_migration_live.py` (G2 = le site converti) | **3 verts**, 0 skipped |
| `test_462_r4b_r1_r1_r1_r1_c_r3_r1_crush_steppable_live.py` (`move_death`) | **6 verts** |
| `test_ambush_migration_live.py` / `test_decoy_foundation_live.py` / `test_cosmic_horror_live.py` | **5 / 3 / 6 verts** |

## 8. Ce qui n'est PAS couvert

* **Le régime cadavre n'est pas confronté LIVE sur les deux sites convertis.** Il l'a été en `-r3`
  (PR #646) sur `barbed_ovipositor`, sur un état réel rechargé ; ici la discrimination est établie
  **offline**, sur des `visualId` RÉELS, et par le décompilé pour le sens du refus. Budget live
  tendu au moment de la tranche (`liveRunners 11` pour un plafond de 4).
* **`IsKilledThisTurn` reste NON PORTÉ** — seulement *collapsé*, et son discriminant (`sc is None`)
  est un artefact du port, pas un concept natif. Résidu `#462-…-r3-r1-r3`.
* **Les deux sites `INDÉCIDABLE`** (`UnitEffectStateView` / `Scene.unit_state`) n'ont pas été
  tranchés : l'énumération exhaustive de leurs ~15 appelants n'a pas été faite. Résidu
  `#462-…-r3-r1-r1`.
* **La face DÉCISION n'a pas de pendant exécutable de P1** : `Scene.ctx_by_id` est peuplé par
  `build_predictor` depuis le même `combatSnapshot`, donc la loi vaut, mais elle n'est vérifiée
  qu'en face COMBAT (`snapshot.load_state`).

## 9. Résidus

* **`#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r1`** — les deux sites **INDÉCIDABLE** :
  `runner/components.py::UnitEffectStateView.__init__` et `playbook/scene.py::Scene.unit_state`,
  substrat des `CreateActiveCondition`. Le seul driver énuméré (`refresh_stat_modifier_effects`)
  sort sur `us is None` et n'atteint donc aucun cadavre, mais les autres appelants d'`active_effects`
  (~15 sites, `damage_model` en tête) n'ont **pas** été énumérés. La dégradation y est
  **PERMISSIVE** : clé `traits` absente ⇒ une condition de TRAIT rend VRAI (#208). Travail =
  l'énumération, pas la conversion.
* **`#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r2`** — **un cadavre-au-chargement ne porte AUCUNE
  triggered-ability.** `triggers/dispatch/core.py::collect_triggered_abilities` fait
  `if sc is None: continue` : les **cinq** chemins de registration (trait, passive, active dérivée,
  relique en dur, relique équipée) sont sautés d'un bloc. C'est la forme la plus large du même
  défaut — le substrat n'y est pas seulement aveugle, l'entité est **absente du registre**. Aucune
  conséquence observable *aujourd'hui* (les triggers concernés sont des `fire_on_death` dont la mort
  a déjà eu lieu, et `EnvAmbushResurrect` est global), mais la question native n'est pas tranchée :
  `IdunBattleLogic.Core.Services.Caches.AbilityAndEffectCache` retire-t-il l'entité à la mort ?
* **`#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r3`** — **porter `IsKilledThisTurn` pour de vrai.**
  `IdunBattleLogic.Entities.DSLTriggers$$IsKilledThisTurn` est un nœud DSL à part entière, et
  `AreEqual(Killer(it), sel@0x40)` avec lui. Le port les collapse en co-localisation sur **deux**
  sites, et leur seul discriminant offline est la présence du `StatsComponent` — un artefact. Le
  port n'a pas d'horodatage de mort général : `UnitComponent.turn_defeated` n'est écrit que par
  `AmbushSummonAbility`. L'écrire à **chaque** mort (`damage.py`, `movement.py::_kill_steppable_units`,
  `resurrect.py`, `remove_unit.py`) rendrait les deux sites gatables par le vrai critère.
