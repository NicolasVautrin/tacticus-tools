# case-303 — `FabricatorClawArray` : la SECONDE réparation du `necroSpyder` (résidu N20 clos)

Ce cas ferme le résidu que la **généralisation** de #299 avait fait apparaître : sur le `necroSpyder`,
et sur lui seul, le port SOUS-réparait de façon parfaitement reproductible — natif **10457**, port
**6025**. L'écart n'était pas dans la réparation ; c'était une **seconde** réparation, celle du passif
`FabricatorClawArray`, qui part dans le même tour.

Ne pas confondre avec **#242** (fermée) : celle-là portait sur `FabricatorClawArrayPlaybook` (1006) et
son cap `mov eax,1 ; ret` — la face **DÉCISION**. Ici c'est la face **COMBAT** du **passif** : autre
classe native, autre chemin.

---

## 1. Chaîne native (décompilé = vérité, build `rnca9r7q6c`)

`IdunBattleLogic.Entities.Abilities.Active.Loki.FabricatorClawArrayAbility$$CreateTrigger` :

```
On(0x1c = ArrivedAtFinalTile, ownerNeedsToBeAlive = 1)
  & get_OwnerIsActor
  & op_LogicalNot( AmountIsZero( GetTargetSelector() ) )
```

* `IdunBattleLogic.Entities.DSLTriggers$$On(type, ownerNeedsToBeAlive)` = `EventTrigger(type) &
  <owner-alive @this+0x20>` — le volet « owner vivant » est le gate `CanGetAbilityTrigger` du dispatch
  porté, pas une clause à ré-écrire.
* `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsActor` = `AreEqual(DSLSelectors+0x30,
  DSLSelectors+0x40)`. **C'est cette fonction qui NOMME les deux slots** : `+0x30 = Owner`,
  `+0x40 = Actor`. Le tableau complet se déduit de l'ordre de `DSLSelectors$$InitializeShared` croisé
  avec les deux call-sites lus : `+0x30 Owner · +0x38 Effect · +0x40 Actor · +0x48 Caster`.
* `IdunBattleLogic.Entities.DSLTriggers$$AmountIsZero(selector)` (surcharge SÉLECTEUR) =
  `op_LogicalNot( AmountIsGreaterAbilityTrigger(selector, <Zero @formulas+0x20>) )`.

`...$$GetTargetSelector` :

```
PickRandomly( Repairable( UnitsAffectedByHealType( AdjacentFriends(Owner, 1, 3), 1 ),
                          scope = 0, removeEffects = 1, unitSelectionType = 3 ),
              amount = 1, allowDuplicates = 0, maxDuplicates = 0x7fffffff, ignoreForced = false )
.Otherwise(
PickRandomly( UnitsWithNegativeEffects( <le MÊME UnitsAffectedByHealType> ),
              1, 0, 0x7fffffff, false ) )
```

Le fallback part de `UnitsAffectedByHealType`, **pas** de `Repairable` (lu : le second `PickRandomly`
reçoit `pvVar2`, le résultat du filtre heal-type). Il vise donc les alliés mécaniques adjacents NON
réparables mais porteurs d'un effet négatif — le volet « purge » de `ForRepair` (`removeEffects = 1`).

`...$$CreateBehaviour` :

```
Repair( mechanic = Owner@DSLSelectors+0x30,
        selector = GetTargetSelector(),
        amount   = DSLFormulas.Direct( AbilityConfiguration.GetVariableForLevel(
                         config, 0x24 = hpToRepair, abilityState, fallbackToDefault = 0) ),
        source   = AbilityOrEffect(this),
        options  = RepairBehaviourOptions.ForRepair() )        # scope 0, removeEffects 1
```

`mechanic = +0x30 = Owner`, là où `IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$CreateBehaviour`
prend `+0x48 = Caster`. Pour une TRIGGERED les deux coïncident (`BaseTriggeredAbility$$Execute`
exécute le behaviour sur son propre porteur).

### Les deux émetteurs d'`On(0x1c)`, et pourquoi les DEUX comptent ici

* `IdunBattle.Operations.MoveUnitOperation$$Execute` : `Add(ArrivedAtFinalTile)` puis, après
  `EvaluateAfterMoveTriggers`, publie `On(0x1c)` **ssi le flag venait d'être ajouté** ;
* `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` : `Add(...)` puis publie `On(0x1c)` ssi le
  flag venait d'être ajouté **et** `!forced`.

Or tout cast d'active termine le tour (`AddFlagsAfterAbilityExecution` → `FinishUnitTurnOperation`).
Le Spyder qui **bouge** puis **répare** exerce donc les deux : `On(0x1c)` part au move, et le cast qui
suit ne le re-publie pas. C'est ce qui rend le chiffre de #299 décomposable en `RepairAmount`
+ `hpToRepair`, et jamais en `2 × hpToRepair`.

## 2. Ce qui est porté

| fichier | contenu |
|---|---|
| `engine/runner/operations/triggers/loki/fabricator_claw_array.py` | l'ability : `matches` = arbre du trigger, `execute_behaviour` = arbre du behaviour, `hp_to_repair` |
| `engine/entities/selectors/units.py` | nœuds `UnitsAffectedByHealType`, `Repairable`, `UnitsWithEffectsOfType` + fabrique `UnitsWithNegativeEffects` |
| `engine/entities/selectors/geometry.py` | nœud `PickRandomly` (délègue à `_pick_randomly_n`, foyer unique de la loi #130/#215) |
| `engine/entities/selectors/accessors.py` | accesseur de slot `Owner` (`factory+0x148` = `DSLSelectors+0x30`) |
| `engine/dsl/base.py` · `runner/abilities/behaviours/context.py` | accesseurs `entity_can_be_repaired`, `pick_randomly` (+ `has_effect_of_type`, déclaré et non branché) |
| `engine/runner/operations/triggers/dispatch/registry.py` | `ABILITY_TRIGGERS["FabricatorClawArray"]` |

**Doctrine #149 respectée** : l'artefact natif est un `CreateTrigger` + `CreateBehaviour`, donc le port
est un ARBRE DSL — aucun ciblage recâblé à la main. Les quatre nœuds qui manquaient au vocabulaire ont
été portés **à leur place** dans `entities/selectors/`, pas inlinés dans l'ability. La frontière reste
le `.Execute` de la feuille : `Repair` APPELLE `RepairUnitOperation` (#299), elle ne la ré-écrit pas.

La surcharge à TROIS arguments d'`IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired` (slot
0x13), que #299 avait laissée non portée faute de call-site, devient atteignable par
`RepairableUnitsSelector$$Select`. Elle n'a **pas** de seconde implémentation : relue verbatim, elle
EST la 4-args avec `caster = null` (le seul disjunct qui disparaît est
`caster != null && HasFlag(caster, 0x18 CanRepairFullHealthUnits)`), donc le nœud l'atteint par
`entity_can_be_repaired(state, None, entity, scope, remove_effects)`.

### DEUX évaluations, DEUX arbres, DEUX tirages — et c'est MESURÉ

`CreateTrigger` et `CreateBehaviour` sont deux fabriques distinctes : chacune appelle
`GetTargetSelector()` et obtient donc **sa propre** instance de `PickRandomly`. À chaque `On(0x1c)`,
le natif évalue l'arbre du trigger (1er tirage, sous `AmountIsZero`) puis, s'il passe, l'arbre du
behaviour (2e tirage). Aucun `Cache` n'intervient.

Ce n'est pas une lecture de confort : elle est **discriminée live**. Avec deux alliés mécaniques
blessés adjacents, l'état MT capturé donne `next_internal(0, 2) = [0, 1, ...]` — les deux premiers
tirages diffèrent. Le natif répare `admecRuststalker` = `pool[1]` ; le port aussi. La mutation
adversariale « `matches` ne consomme plus le PRNG » fait basculer le port sur `pool[0]` =
`necroWarden`, et le test tombe :

```
AssertionError: le port n'a pas choisi la MEME cible que le natif :
live={'admecRuststalker': 4432, 'necroWarden': 0}
offline={'admecRuststalker': 0, 'necroWarden': 4432} (tirages=[0, 1])
```

## 3. Mesures (live vs port)

| scénario | montage | natif | port |
|---|---|---|---|
| **MOVE SEUL** (aucun cast) | Spyder → tuile adjacente à l'allié blessé | **+4432** | +4432 |
| 2e move, MÊME tour | idem, second pas | **0** | 0 |
| arrivée à distance 2 | tuile libre à `dist(cible) >= 2` | **0** | 0 |
| allié à 100 % PV | `--hp-player` seul (pas de `--unit-stat`) | **0** | 0 |
| allié blessé NON mécanique | `ultraApothecary` | **0** | 0 |
| fin de tour SANS bouger | `FinishUnitTurnMessage` (port) | — | +4432 |
| **pool de 2** (`PickRandomly`) | 2 alliés mécaniques blessés adjacents | `admecRuststalker` | `admecRuststalker` |
| **#299 recomposé** (move+cast) | `--hp-player 300000`, `RemainingHealth=1` | **+10457** | **+10457** |

`4432 = hpToRepair[50] 2216 × multiplier 200 %` — `hpToRepair` est dans
`variablesAffectedByRarityBonus`, donc le multiplicateur de rareté s'applique
(`AbilityConfiguration$$TryGetVariableArrayForLevel`).

**Le PRNG doit être calé** (`dumpRng` → `state.rng`) pour toute mesure dont le pool dépasse 1 :
`_pick_randomly_n` retombe sinon sur `pool[:n]`, un choix déterministe qui coïncide par accident
quand le pool tient dans un élément et diverge dès qu'il y en a deux (mesuré : natif
`admecRuststalker`, port non calé `necroWarden`).

Garde ROUGE vue AVANT le port (mutation adversariale `ABILITY_TRIGGERS.pop("FabricatorClawArray")`,
= l'état `origin/master`), message verbatim :

```
[FCA/move] hpToRepair=4432 live=4432 offline=0
AssertionError: offline 0 != hpToRepair 4432
```

## 4. Résidus NOMMÉS

* **`UnitsWithNegativeEffects` (le fallback d'`Otherwise`)** : `UnitsWithEffectsOfTypeSelector$$Select`
  teste `EntityExtensions.HasEffectOfType(entity, state, effectsDatabase, 1)`, et le `1` n'est **pas**
  un `EffectType` — `IsOwnerOfEffectOfType` lit la CATÉGORIE portée par la DÉFINITION de chaque effet
  (`def+0x58`, un `Nullable<int>`). Ce canal n'est pas dans le seed (même trou que
  `attack_query.has_negative_unit_effect`, qui lit un AUTRE conteneur natif,
  `EffectsComponent+0x100`). L'accesseur `ctx.has_effect_of_type` est donc déclaré et **non branché**,
  et le sélecteur rend `[]`. Conséquence bornée et UNILATÉRALE : le fallback ne peut que RATER une
  cible, jamais en inventer une, et il n'est atteint que si aucun allié mécanique adjacent n'est
  réparable.
* **`unitSelectionType = 3`** (mode d'occupation main/steppable propagé au `Select` de la source) :
  le port n'a pas ce paramètre côté sélecteurs sources — résidu déjà partagé par tous les call-sites
  d'`AdjacentFriends`.
* **`source = AbilityOrEffect(this)`** (attribution de la réparation) : aucun observable d'état porté,
  non modélisé — même choix que la feuille `Repair` de #299.
* **Les résidus de `RepairUnitOperation` restent ceux de #299** (`removeEffects` non purgé, cap de
  groupe inerte, cap boss, event `UnitRepaired` + statistiques) : ce cas n'y touche pas.

## 5. Gardes

* `scripts/python/tests/engine/runner/test_fabricator_claw_array_live.py` — 8 tests (move seul,
  une-fois-par-activation, distance, cible pleine, cible non mécanique, fin de tour sans bouger,
  `PickRandomly` sur pool de 2 avec sa clause de non-dégénérescence, cliquet de registre).
* `scripts/python/tests/engine/runner/test_repair_execution_live.py` — le test `necroSpyder` de #299
  passe de « `live == offline + hpToRepair` » (résidu chiffré) à « `live == offline` », décomposé
  selon le vecteur qui a publié `On(0x1c)` (`UnitFlagsComponent.ARRIVED_AT_FINAL_TILE` déjà posé ou
  non à la capture).
* `scripts/python/probe_303_fabricator_claw_array.py` — mesure par étage (config, trigger étage par
  étage, move seul, contrôle du second move).
* Cliquets re-joués : `probe_181_targeting_gaps.py` (97/97, **0** masque manquant),
  `probe_120_pre_unit_ability_fork.py` (étape 0 : **0** `AbilityAttackType` manquant),
  `probe_273_gitignored_inputs.py --only-scan`.

## 6. Confrontabilité des porteurs

`FabricatorClawArray` a **6** porteurs (balayage des 683 kits) : `necroSpyder` (**lineup — HERO du
pool**) et cinq `npc` (`necroBossC1Spyder`, `necroBossSpyder`, `necroBossSpyderLEG`,
`necroBossSpyderLHE`, `necroNpcSpyder`), tous avec le même jeu de traits. Le port est donc confronté
sur le SEUL porteur confrontable, et les cinq autres ne sont pas « bloqués » mais hors-jeu.
