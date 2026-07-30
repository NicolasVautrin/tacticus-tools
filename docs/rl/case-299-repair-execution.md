# case-299 — la face EXÉCUTION de la RÉPARATION RÉGULIÈRE (`28 Repair`, `1119 Repair_GalvanicField`)

**Ce que #298 avait établi** : le rail de DÉCISION de la réparation est complet — l'ability est dans
`ActiveAbilityComponent.Abilities`, le ciblage l'accepte, `PredictRepair` la prédit, l'IA la PROPOSE.
**Ce que #298 n'avait pas porté** (c'était une tâche de RE, sans port spéculatif) : la face COMBAT.

Résultat mesuré avant ce cas — la pire forme de dégradation :

```
{'ability_type': 28, 'ported': False,
 'flags': {'ability_used_flag': True, 'turn_finished': True,
           'finish': {'newly_arrived': True, 'newly_finished': True, 'arrived_triggers': []}}}
```

Le cast est **ACCEPTÉ**, le tour est **CONSOMMÉ** (`ability_used_flag`, `turn_finished`), et **zéro PV
restauré**. Ni erreur, ni crash. Un entraînement RL apprendrait à « réparer » gratuitement.

---

## 1. Chaîne native (décompilé = vérité)

```
IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$CreateBehaviour
  mechanic = <bundle@0x90>+0x48                    # `Caster`
  selector = <bundle@0x90>+0x60                    # `ActiveTarget`
  amount   = this.<vtable +0x4b8>()                # = RepairAbility$$RepairAmount
  options  = RepairBehaviourOptions.ForRepair()    # scope 0, removeEffects 1
  -> IdunBattleLogic.Entities.DSLBehaviors$$Repair(mechanic, selector, amount, source, options)
  -> IdunBattle.Entities.Behaviours.RepairBehaviour$$Execute
       foreach target in Select(+0x58):
           processor.<slot 0x58>(mechanic, target, amount, options+0x10, options+0x14, source@+0x68)
  -> Core.Services.OperationProcessor$$RepairUnit                (caller MINCE, aucune logique)
  -> IdunBattle.Operations.RepairUnitOperation$$Execute
```

`RepairUnitOperation$$Execute`, mirror lu verbatim :

```
if (!attackQuery.<slot 0x12>(caster, target, scope, removeEffects)) return {};  # EntityCanBeRepaired
fillUp   = target.GetComponent<FillUpStatComponent>(Health)
pred     = damagePrediction.<slot 2>(caster, target, GetUnitPosition(caster), amount, scope, source)
repaired = FillUpStatComponent$$FillUp(fillUp, pred.fillUp)                     # LA MUTATION
```

`IdunBattle.Core.Services.DamagePrediction$$PredictRepair` :

```
predicted = amount
if (EntityExtensions.IsActor(caster))
    predicted = (int)( Fix64((int)mod.flatBonus + amount) * mod.multiplier )    # RepairModifier
health = GetStat(target, 5 Health, 0 Current)
if (scope == 1)          predicted = Min(predicted, GetGroupUnitHealLimit(target, health))
if (IsBoss(target))      predicted = Min(predicted, GetStat(target, 5, 3 Initial) - health)
return CONCAT44( FillUpStatComponent$$MaxFillUp(fillUp, predicted), health )
```

`FillUp` et `MaxFillUp` sont le MÊME `Min(amount, CurrentMaximumValue - current)` : l'un le calcule,
l'autre l'applique — la composition ne sature donc qu'UNE fois.

`IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$RepairAmount` :

```
Multiply( StatAmount(Caster, 0 = ATTACK, 0 = Current), Max( WeaponHighestHits(Caster), Get(1) ) )
```

**`RepairMachineOperation` N'EXISTE PAS** dans ce build (`search_symbols_by_name` = 0 résultat) : la
mention de #298 était une supposition, pas une lecture. Le seul chemin est `RepairUnitOperation`.

### 1119 `Repair_GalvanicField`

`Repair_GalvanicFieldAbility$$.ctor` = `return RepairAbility..ctor(this)` — masque, portée,
`forceMeleeTarget` et `AbilityAttackType` **hérités**, pas recopiés.

```
Repair_GalvanicFieldAbility$$CreateBehaviour
  = RepairAbility.CreateBehaviour(this, state) & CreateAttackBehavior(dsl, <sel@0x60> - <mech@0x48>)

Repair_GalvanicFieldAbility$$CreateAttackBehavior(dsl, actingUnits)
  affected = DSLSelectors.UnitsAffectedByHealType(actingUnits, 1 = Mechanical)
  node     = PercentageOfAttackCappedAtMax(Subject, 3 = Initial,
                                           ConfigVar(0x4af = 1199 GalvanicField, 0xd  maxDmg),
                                           ConfigVar(0x4af = 1199 GalvanicField, 0x4a dmgPct))
  = ( AddStatOverrideEffect(affected, 0x4da = 1242 GalvanicField_DmgOverride, 0 = ATTACK, node, 0, 1)
    & PerformAIAttackFromCurrentPosition(affected, <abilityState@0x30>, 0, false) )
    & RemoveEffect(affected, Nullable(0x4da), 0)
```

La machine réparée attaque immédiatement, Attack surchargée, puis l'override est retiré (net-zéro).
Même patron, feuille pour feuille, que
`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$GetTriggerAttackBehaviour`.

## 2. Métadonnées de registre (le CLIQUET)

`IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$.ctor` — forme **1 « flags directs »**
(surcharge vérifiée au décompilé : celle qui écrit `rules` telle quelle à `options+0x28`, ni preset
combiné, ni copie statique) :

```
TargetingOptions..ctor(&opts, 0, &<TargetingRange statics>+0x30, 2, 0x8002, 0, 0)
  isSelfCasting    = 0
  range            = TargetingRange statics+0x30 = RANGE_ADJACENT (onlyAdjacent + overrideRange 1)
  forceMeleeTarget = 2 = RangedBool.IfRangedCaster
  rules            = 0x8002 = CasterIsPossibleTarget | TargetMatchesDynamicRule
ADeprecatedActiveAbility..ctor(this, &opts, 2)  ->  AActiveAbility..ctor(..., 2 = Others)
```

Le masque ne porte **aucune** règle de camp ni de domaine : tout le refus vit dans la règle DYNAMIQUE
(bit 1), d'où l'importance des deux `GetDynamicInvalidTargetReason` portés.

## 3. Ce qui est porté

| fichier | contenu |
|---|---|
| `engine/runner/operations/repair.py` | `RepairUnitOperation` (impératif, doctrine #149) + `predict_repair` + l'adaptateur `RepairModifier` |
| `engine/runner/abilities/repair.py` | `RepairAbility` (28) et `Repair_GalvanicFieldAbility` (1119), masque, règles dynamiques, volet attaque de 1119 |
| `engine/runner/abilities/behaviours/stats.py` | la feuille DSL `Repair` **rebranchée** sur `RepairUnitOperation` (elle appelait `HealUnitOperation`, ce qui court-circuitait le gate, le `RepairModifier` et les caps) |
| `engine/runner/abilities/handler.py` · `attack_type.py` | entrées au registre + `AbilityAttackType.Others` |

Module **non factionnel** à dessein : `28` est dérivée du trait `Mechanic`
(`UnitFactory$$AddDerivedAbilities` ← `StaticBattleRules.Trait$$GetActiveAbility`) et ses porteurs
traversent cinq factions (`admecDominus`, `admecManipulus`, `necroSpyder`, `orksBigMek`,
`votanIronmaster`) — la ranger dans `admec.py` aurait été faux.

## 4. Mesures (live vs port)

| scénario | montage | natif | port | verdict |
|---|---|---|---|---|
| `admecDominus` / 28 | `_repair_stage`, cible `RemainingHealth=2000` | **+5022** | +5022 | `Attack 5022 × 1 hit` |
| `admecManipulus` / 1119 | idem | **+5024** | +5024 | `Attack 5024 × 1 hit` |
| cap `MaxFillUp` | cible à `hp_max − 100` | **+100** | +100 | le montant (5024) est capé par le manque |
| cible à 100 % | même montage, seule la santé change | — | **0** | gate `EntityCanBeRepaired` |
| cible NON mécanique (`ultraApothecary`, blessée) | roster dédié | — | **0** | `IsAffectedByHealType(.,1)` ; la même cible est SOIGNABLE (type 0) |
| `necroSpyder` / 28 (5 coups) | `--hp-player 300000`, `RemainingHealth=1` | **+10457** | +6025 | écart **+4432**, entièrement expliqué — cf. §5 |

Garde rouge par MUTATION adversariale (registre ramené à l'état `origin/master`), message VERBATIM :

```
AssertionError: ability 28 NON routee cote combat ({'ability_type': 28, 'ported': False,
  'flags': {'caster': 81, 'found': True, 'ability_used_flag': True, 'turn_finished': True,
  'finish': {'unit': 81, 'found': True, 'forced': False, 'newly_arrived': True,
  'newly_finished': True, 'arrived_triggers': []}}}) -- c'est EXACTEMENT le residu #299
```

## 5. Résidu NEUF trouvé par la généralisation — `FabricatorClawArray` (N20)

`necroSpyder` est le seul porteur du trait `Mechanic` dont l'arme a **5 coups** : il exerce le
facteur `Max(WeaponHighestHits, 1)`, invisible chez les deux AdMec (×1). Sa mesure a d'abord donné un
écart apparent de +7, **artefact de saturation** : avec le montage standard le manque valait 6032, et
tout montant au-delà était masqué par `MaxFillUp`. En supprimant la saturation
(`--hp-player 300000` + `RemainingHealth=1`), l'écart réel apparaît : **10457 vs 6025**.

Il n'est pas dans la réparation : c'est le PASSIF du Spyder.

```
IdunBattleLogic.Entities.Abilities.Active.Loki.FabricatorClawArrayAbility$$CreateTrigger
    = On(0x1c = ArrivedAtFinalTile) & OwnerIsActor & !AmountIsZero(GetTargetSelector())
...$$CreateBehaviour
    = Repair(Owner, GetTargetSelector(), Direct(ConfigVar(0x24 = hpToRepair)), ForRepair)
...$$GetTargetSelector
    = PickRandomly(Repairable(UnitsAffectedByHealType(AdjacentFriends(Owner,1,3), 1), 0,1,3), 1)
      Otherwise PickRandomly(UnitsWithNegativeEffects(...), 1)
```

Tout cast d'active TERMINE le tour (`AddFlagsAfterAbilityExecution` → `FinishUnitTurnOperation` →
`UnitFlags.Add(ArrivedAtFinalTile)`), donc le trigger part juste après la réparation.

**4432 = `hpToRepair[50] = 2216` × `multiplier 200 %`** — à l'unité près. La face COMBAT de la
réparation est donc JUSTE ; le manque est une ability PASSIVE, hors périmètre de ce cas. Verrouillé
par une égalité exacte (`live == offline + hpToRepair`), qui garantit du même coup le facteur `× 5`.

## 6. Résidus NOMMÉS du port lui-même

* **`removeEffects`** (`processor.<slot 0x5b>`, purge des effets négatifs) : `ForRepair` pose bien
  `removeEffects = 1`, mais le port n'a aucun marqueur « effet négatif » (même trou que
  `attack_query.has_negative_unit_effect`). `cleansed` vaut toujours 0 — l'écart ne porte que sur les
  effets purgés, jamais sur les PV.
* **cap de GROUPE** (`GetGroupUnitHealLimit`, gate `scope == 1`) : non porté ; les DEUX fabriques du
  build (`ForRepair`) passent `scope = 0`, la branche est INERTE.
* **cap BOSS** : `UnitExtensions$$IsBoss` lit le champ `UnitComponent+0x88` (ce n'est **pas**
  `HasTrait(Boss)`), qu'aucun canal de seed n'expose. Sans conséquence sur ce substrat : le cap boss
  vaut `GetStat(Health, Initial) − current` et l'étage suivant cape à `CurrentMaximumValue − current`
  ; le canal offline n'expose qu'UN plafond, les deux bornes s'y confondent.
* **event `UnitRepaired` + statistiques** (`ActorStatisticsComponent$$AddRestoreHealthAction`,
  compteurs `+0xcc/+0xd0/+0xe0/+0xe4`) et les vecteurs `processor.<slot 0x51>` `On(0x30)` / `On(0x1e)`
  : non portés. Le SEUL consommateur porté d'`On(48)` est le stat-mod `EXTRA_HITS` du trait `Swarm`,
  déjà câblé par l'appel direct à `on_group_unit_hp_changed` (même raccourci que `HealUnitOperation`).
* **`HasValidTargets` de la règle dynamique de 1119** : le cooldown de l'attaque normale
  (`ActiveAbility$$get_CanCurrentlyBeUsed`) n'est pas modélisé → dégradation PERMISSIVE.
* **choix de cible de `PerformAIAttackFromCurrentPosition`** (volet attaque de 1119) : approximé par
  l'ennemi le plus proche à portée, comme chez son précédent `TheQuickening` ; le roll reste RNG.

## 7. Gardes

* `scripts/python/tests/engine/runner/test_repair_execution_live.py` — 7 tests (2 porteurs confrontés
  live, cap `MaxFillUp`, cible pleine, cible non mécanique, `necroSpyder`/N20, cliquet de registre).
* `scripts/python/probe_299_repair_amount_stages.py` — décomposition par étage du montant
  (`--repairer`, `--repairee`, `--hp-player`, `--damaged`), l'outil qui a séparé « saturation » de
  « vrai écart ».
* Cliquets re-joués : `probe_181_targeting_gaps.py` (97 abilities, **0** masque manquant),
  `probe_120_pre_unit_ability_fork.py` (étape 0 : **0** `AbilityAttackType` manquant),
  `probe_249_unported_rule_carriers.py` (aucun bit hors enum, 6/97 abilities touchées par une règle
  non portée — les deux nouvelles n'en ajoutent aucune).
