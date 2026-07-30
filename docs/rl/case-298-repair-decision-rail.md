# #298 — le rail de DÉCISION de la réparation : il EXISTE, il est ATTEINT, et voici son gate

**Verdict : le rail existe et l'IA propose la réparation.** La prémisse du résidu #278
(« `PredictRepair` n'est JAMAIS appelé malgré 2 cibles légales ») **ne se reproduit pas** sur le
montage canonique, dans la MÊME session Frida (`session 2`, injectée le 2026-07-30T14:20:11Z, donc
**après** le correctif `33292bc4` de 16:08:10+02:00 — le canal `PredictRepair` porte bien le décodage
corrigé). Mesuré : **62 events `repair_prediction` sur `Repair_GalvanicField` + 9 sur `Repair`**, et
l'action que l'IA propose pour le réparateur est l'`ActiveAbilityMessage` de réparation.

Le rail est **`ActiveAbilityActionGenerator`** — l'hypothèse héritée est donc CONFIRMÉE, mais pas
pour la raison qu'on croyait : ce n'est pas malgré le slot `RepairType`, c'est parce que l'ability
dérivée du trait est une **entrée de plein droit de `ActiveAbilityComponent.Abilities`**.

**Le seul gate est un gate d'ÉTAT, pas de harnais** :

```
IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired
    exige  AttackQuery$$IsDamagedUnit(entity)
    ET     UnitExtensions$$IsAffectedByHealType(entity, 1)
```

Une cible à 100 % de PV, ou non mécanique, n'est **pas** une cible de réparation : zéro cible, zéro
prédiction, zéro event — **sans erreur ni trace**. C'est exactement la forme qui se lit à tort comme
« le rail n'existe pas ».

---

## 1. La chaîne native, lue au décompilé

### 1.1 L'ability de réparation est DÉRIVÉE DU TRAIT, et elle entre dans `Abilities`

`IdunBattle.Entities.Components.ActiveAbilityComponent` (layout confirmé au dump du build courant) :

```
Dictionary<BEntityId, ActiveAbilityBlocker> Blockers;   // 0x18
ActiveAbilityKeyedCollection             Abilities;     // 0x20   <- la COLLECTION
ActiveAbilityType                        NormalAttackType;  // 0x28
ActiveAbilityType                        RepairType;        // 0x2C  <- un SLOT, un POINTEUR
ActiveAbilityType                        PrimaryMachineAbilityType;   // 0x30
ActiveAbilityType                        SecondaryMachineAbilityType; // 0x34
```

`RepairType` est un **index**, pas un stockage parallèle : `IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities`
ajoute l'ability elle-même à la collection. Sa troisième boucle parcourt les **traits** de la config :

```
foreach (trait in config.<traits @+0xd0>) {
    t = StaticBattleRules.Trait$$GetTriggeredAbility(trait);
    if (t.HasValue) TriggeredAbilityComponent$$TryAdd(...);
    a = StaticBattleRules.Trait$$GetActiveAbility(trait);          // dict statique Trait -> ActiveAbilityType
    if (a.HasValue) {
        state = new AbilityState(new Level(1, 0), config.<+0x74>);
        ActiveAbilityComponent$$Add(activeAbilities, a.Value, state, null);   // <- ENTRE DANS `Abilities`
    }
}
```

C'est ce `Add` qui rend la réparation atteignable. `IdunBattle.Entities.UnitExtensions$$GetRepairType`,
lui, ne fait que lire `*(uint*)(component + 0x2c)` — il sert aux **sélecteurs** (`IdunBattleLogic.Entities.AbilityTypeSelector.UnitNormalRepairAbilitySelector$$Select`,
`IdunBattleLogic.Entities.DSLSelectors$$UnitNormalRepairType`) et aux prédicats de playbook
(`IdunBattle.AI.Playbook.Loki.GravitonRiflePlaybook$$HasAnyRepairTarget`), **jamais** au générateur d'actions.

### 1.2 Le type entre dans le jeu d'abilities d'un générateur

`IdunBattle.AI.Tactics.ABaseAiActorTactic` porte les deux jeux :

```
IOrderedSet<ActiveAbilityType>                        _comparableAbilities;      // 0x38
Dictionary<AbilityPriority, IOrderedSet<ActiveAbilityType>> _nonComparableAbilities; // 0x40
```

`IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists` les remplit en **balayant tout
l'enum** `ActiveAbilityType` :

```
foreach (at in Enum.GetValues<ActiveAbilityType>()) {
    if (!_query.<slot 0xbc>() && !StaticBattleRules.ActiveAbility$$IsRegularAbilityType(at)
                              &&  StaticBattleRules.ActiveAbility$$IsIdunAbility(at)) continue;
    if (!this.IsValidAbilityType(at)) continue;                 // virtuel ; la base rend true
    pb = PlaybookDatabase$$LoadPlaybook(at, fallbackToDefault: true);
    if (pb == null) continue;
    (pb.IsComparable ? _comparableAbilities
                     : _nonComparableAbilities[pb.Priority]).Add(at);
}
```

`IdunBattle.AI.Tactics.ABaseAiActorTactic$$GetDefaultActiveAbilityActionGenerators` en fait **six**
`ActiveAbilityActionGenerator` : cinq sur `_nonComparableAbilities[p]` pour
`p ∈ {1000, 100, 0, -100, -1000}`, **puis un sur `_comparableAbilities`**.

`IdunBattle.AI.Playbook.Common.RepairPlaybook$$.ctor` appelle
`ComparablePlaybook<RepairAbility>..ctor(this, 0x1c)` — **28 `Repair`** ;
`IdunBattle.AI.Playbook.Loki.Repair_GalvanicFieldPlaybook$$.ctor` appelle
`ComparablePlaybook<Repair_GalvanicFieldAbility>..ctor(this, 0x45f)` — **1119 `Repair_GalvanicField`**.
Les deux sont **COMPARABLES**, donc dans `_comparableAbilities`, donc dans le **6ᵉ** générateur. Et les
deux sont bien **enregistrés** : `IdunBattle.AI.PlaybookDatabase.u003Cu003Ec$$u003CInitializePlaybookBuildersu003Eb__31_121`
construit `Repair_GalvanicFieldPlaybook`.

### 1.3 Le générateur itère la collection BRUTE — c'est le point qui débloque tout

`IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator$$GetUnitAbilitiesInOrder(activeAbilityComponent)` :

```
list = new List<ActiveAbilityType>();
foreach (ActiveAbility ab in activeAbilityComponent.<Abilities @0x20>)   // Collection<T>.GetEnumerator
    if (this._abilityTypes.Contains(ab.<type @+0x44>))                   // _abilityTypes @0x28
        list.Add(ab.<type @+0x44>);
if (ShouldRandomizeOrder(list)) ListExtensions.Shuffle(list, _random);
return new OrderedSet<ActiveAbilityType>(list);
```

**Aucun filtre `IsActiveAbility`.** C'est toute la différence avec
`ActiveAbilityComponent$$GetActives` — que notre harnais utilise — qui, lui, filtre. D'où le fait,
mesuré, que la réparation ressorte de `abilityTargets` en **`kind = "granted"`** (pass complémentaire
`ActiveAbilityComponent$$GetUnusedAbilities`) et non `"active"` : les deux itèrent la MÊME collection,
donc le générateur la voit.

Le tirage de `ActiveAbilityActionGenerator$$ShouldRandomizeOrder` ne concerne **pas** la réparation :
`ActiveAbilityActionGenerator$$AbilitiesWithRandomOrder` ne contient que
`{0x46e, 0x46f, 0x470, 0x4c2}`. Le rail est donc **déterministe** — vérifié 6/6 (§2).

### 1.4 Le gate, et il est d'ÉTAT

`IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired` (surcharge à 5 paramètres,
`(this, caster, entity, scope, removeEffects)`) :

```
if (!EntityExtensions$$IsMachine(entity)
    && (   AttackQuery$$IsDamagedUnit(entity)
        || (removeEffects && AttackQuery$$HasNegativeUnitEffect(entity))
        || (caster != null && UnitExtensions$$HasFlag(caster, 0x18)))
    && !UnitExtensions$$HasHealBlockers(entity)
    &&  UnitExtensions$$IsAffectedByHealType(entity, 1))          // 1 = Repair
{
    return scope == 0 ? true : !AttackQuery$$IsAtGroupUnitHealLimit(entity);
}
return false;
```

La surcharge à 4 paramètres est la même sans le volet `caster`/`HasFlag(0x18)`.

En aval : `Repair_GalvanicFieldPlaybook$$MakeRepairPredictions` (et `RepairPlaybook$$MakeRepairPredictions`)
appelle le slot 0x2a de `IBattleQuery` avec `(caster, casterPosition, target, amount, 0, abilityOrEffect)`
et range le résultat dans un `Dictionary<IEntity, RepairPredictionResult>` — c'est cet appel qui atteint
`IdunBattle.Core.Services.DamagePrediction$$PredictRepair`, sur lequel notre hook est posé.

---

## 2. Mesure — quatre étages, un capteur par étage, aucun hook neuf

Capteurs **déjà armés** (aucune réinjection) :

| étage | ce qu'il répond | capteur |
|---|---|---|
| E0 | l'ability est-elle dans `ActiveAbilityComponent.Abilities` ? | RPC `abilityTargets` → `unitAbilityTypes` (`GetActives` puis `GetUnusedAbilities`) ; le champ `kind` dit laquelle |
| E1 | est-elle dans le `_abilityTypes` d'un générateur ? | trace **L2** → event `candidates`, champ `abilities` |
| E2 | son playbook est-il ÉVALUÉ ? | trace **L1** → `playbook_eval_begin` (`BasePlaybook.Evaluate`) |
| E3 | la prédiction est-elle calculée ? | trace **L1** → `repair_prediction` (hook `DamagePrediction$$PredictRepair`) |

Probe : `python scripts/python/probe_298_repair_rail.py` (jamais `--l3`).
Montage : fixture nommée `repair_stage` → `tests/engine/runner/_repair_stage.py`.

### 2.1 E1 — preuve directe, lue dans la trace

Les six `ActiveAbilityActionGenerator` d'un tour de `admecManipulus`, dans l'ordre de
`GetDefaultActiveAbilityActionGenerators` (la trace tronque à 16 entrées) :

```
GEN 1  9 abilities  ['BreathOfSilence', 'EreWeGo', 'DeathScream', ...]
GEN 2  4 abilities  ['Catalyst', 'GunnersKillOnSight', 'SolarAtomizer', 'ThriceBlessedConflagration']
GEN 3 16 abilities  ['GauntletsOfUltramar', 'MightOfHeroes', ...]
GEN 4  3 abilities  ['MacroPlasmaIncinerator', 'SquigMine', 'InfernalCannon']
GEN 5  6 abilities  ['MyWillBeDone', 'DaGreatWaaagh', ...]
GEN 6 16 abilities  ['NormalAttack', 'Heal', 'Repair', 'Loki_NormalAttack', 'MortisRound', ...]
```

`Repair` (28) est la **3ᵉ entrée** de `_comparableAbilities` (GEN 6). `Repair_GalvanicField` (1119) y est
aussi mais hors des 16 premiers (ensemble trié par valeur d'enum) — E2 le prouve à sa place.

### 2.2 E2 — ordre d'évaluation, pas de court-circuit

```
playbook_eval_begin (caster = admecManipulus)
  DefendTheDivineWorkPlaybook   x5
  Loki_NormalAttackPlaybook     x4
  Repair_GalvanicFieldPlaybook  x5     <- ATTEINT
```

Le générateur comparable évalue **toutes** ses abilities ; il ne s'arrête pas à la première.

### 2.3 E3 + choix de l'IA — le tableau discriminant

Une seule variable change d'une ligne à l'autre. Même roster, même board (`MC1_67`), même seed,
mêmes tuiles de spawn (`advance = 0` sauf ligne A), `aiDryRunAllUnits` rejoué.

| # | montage (delta unique) | cibles de réparation | `repair_prediction` | playbooks évalués | ability proposée |
|---|---|---|---|---|---|
| **A** | `--advance 2`, cible abîmée par l'IA (6514/8032) | 1 | **5** (identique sur **6/6** passes) | 4, dont `Repair_GalvanicFieldPlaybook` | **1119** |
| **B0** | `--advance 0`, cible à **100 %** | **0** | **0** | aucun | aucune |
| **B1** | B0 + `RemainingHealth=2000` sur la cible | 1 | **3** | 2, dont `Repair_GalvanicFieldPlaybook` | **1119** |
| **C** | B1 + réparateur `admecDominus` (sans `GalvanicField`) | 1 | **3** | 2, dont `RepairPlaybook` | **28** |
| **D** | B1 + cible **non mécanique** (`astraDreir`, blessée) | **0** | **0** | aucun | aucune |

* **B0 vs B1** isole `AttackQuery$$IsDamagedUnit` : c'est la santé de la cible, et rien d'autre.
* **B1 vs D** isole `UnitExtensions$$IsAffectedByHealType(entity, 1)` : une cible blessée **non
  mécanique** n'est pas réparable.
* **B1 vs C** couvre les **deux** membres de `StaticBattleRules.ActiveAbility$$IsRegularRepair`
  (`{0x1c, 0x45f}`) : le trait `Mechanic` dérive `Repair` (28) ; un passif qui spécialise le slot
  `RepairType` le remplace (`GalvanicField` → 1119).

Échantillon d'event (B1) — le décodage `33292bc4` est cohérent, `currentHealth + totalHeal` retombe
sur la santé MAX de la cible :

```json
{"evt":"repair_prediction","caster":{"name":"admecManipulus"},"target":{"name":"admecRuststalker"},
 "amount":5024,"prediction":{"currentHealth":2000,"totalHeal":5024},
 "playbook":"Repair_GalvanicFieldPlaybook","playbookAbility":"Repair_GalvanicField"}
```

### 2.4 Piège de montage, mesuré — `--hp-player` ne blesse PERSONNE

`--hp-player N` écrit **`Health` ET `RemainingHealth`** à `N` : l'unité reste à **100 %**, donc
`IsDamagedUnit` reste FAUX et le montage annule le scénario qu'il devait créer (mesuré : 0 cible, 0
prédiction). Le seul levier correct est `--unit-stat "<cible>:RemainingHealth=<n>"`, qui laisse la
santé MAX en place. Le montage `_repair_stage.build_args` l'expose sous `damaged_repairee`.

---

## 3. Ce qu'il faudrait pour obtenir un ZÉRO — et ce que #278 a probablement mesuré

Le zéro de #278 n'a **pas** pu être reproduit sur son propre montage, dans la même session, avec les
capteurs dans le même état (`installed=true`, `L1`/`L2` armés, `PredictRepair="ok"`). Ce qui est
établi, c'est la **liste close** des conditions qui rendent un zéro, toutes vérifiées comme
suffisantes ci-dessus :

1. **aucune cible réparable dans l'état** — `IsDamagedUnit` faux (B0) ou `IsAffectedByHealType(…, 1)`
   faux (D). C'est le cas de loin le plus facile à produire par accident ;
2. **la trace L1 n'est pas armée au moment de l'appel** — le hook `PredictRepair` sort en tête sur
   `if (!traceState.enabled.L1) return;`. ⚠ `aiTraceStatus` publie **deux** informations distinctes :
   `installStatus.PredictRepair = "ok"` dit que le hook est **POSÉ**, `enabled.L1` dit qu'il **ÉMET**.
   Lire la première pour conclure sur la seconde est une erreur silencieuse ;
3. **fenêtre de lecture fausse sur le JSONL** — la trace est **SESSION-GLOBALE** : tous les runners de
   la session écrivent le même fichier, et la projection d'entité par défaut est `{"name": <visualId>}`,
   **sans `entityId`**. Un filtrage par `entityId` ne matche donc **rien** (erreur commise et corrigée
   dans ce cas même) ; un filtrage trop large attribue les events d'un autre agent.

Note d'attribution : sur la même session, un autre runner faisait tourner `admecDominus` /
`RadBombardmentPlaybook` pendant la mesure. Le filtrage par **roster** (visualIds du runner) est
obligatoire, et c'est ce que fait `probe_298_repair_rail.summarize`.

---

## 4. Le vrai résidu, qui est OFFLINE — et une ligne d'inventaire à corriger

Côté moteur Python, au commit de ce cas
(`python scripts/python/probe_decision_noop_gap.py`, **14** items `DECIDENT sans EXECUTER`) :

| id | décide (registres) | exécute (`ABILITY_CLASSES`) | conséquence offline |
|---|---|---|---|
| `28` `Repair` | **oui** — `engine.playbook.base.REGISTRY` | **non** | cast ACCEPTÉ, tour consommé, **zéro soin** |
| `1119` `Repair_GalvanicField` | **non** | **non** | l'IA portée ne le propose même pas ; rejoué, no-op silencieux |

**`docs/rl/port-residuals-inventory.md` affirmait que `28 Repair` est « un TAG de playbook générique,
pas une ability », « dormant par construction », « hors périmètre ».** C'est **FAUX**, et la
justification (« aucune entrée `abilities` du gameconfig ne s'appelle `Repair` ») était le piège :
l'ability n'est pas dans le gameconfig parce qu'elle est **dérivée d'un TRAIT** au montage de l'unité
(`UnitFactory$$AddDerivedAbilities` ← `StaticBattleRules.Trait$$GetActiveAbility(Mechanic)`), pas
parce qu'elle n'existe pas. Mesuré : `admecDominus` porte l'id **28** en bataille, l'IA native
**propose** `ActiveAbilityMessage abilityType=28`. Le compte « 10 items réels » qui en défalquait
`28 Repair` est donc à relever d'une unité.

Porteurs `Mechanic` **HERO et dans le pool rank 17** (donc confrontables sans injection de catalogue) :
`admecManipulus` (→ 1119), `admecDominus`, `necroSpyder`, `orksBigMek` (→ 28). Aucun n'est npc-only.

---

## 5. Reproduire

```bash
cd scripts/python
python probe_298_repair_rail.py --advance 0 --damaged 2000            # B1 : rail atteint, 1119
python probe_298_repair_rail.py --advance 0                           # B0 : controle, 0
python probe_298_repair_rail.py --repairer admecDominus --advance 0 --damaged 2000   # C : 28
python probe_298_repair_rail.py --repairee astraDreir --advance 0 --damaged 2000     # D : 0
python -m pytest tests/engine/runner/test_repair_decision_rail_live.py -q            # 5 tests
```

Le probe monte et **dispose** son runner (`--keep` pour le garder). Il n'active que `L1`/`L2` —
**jamais `L3`** (hooks session-globaux : crash si un autre agent walke l'IA).
