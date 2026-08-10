# case-310 — `LivingMetal` : l'artefact natif est un `Repair(…, ForRegenerate)`, pas un `Heal`

**Verdict** : bug de câblage CONFIRMÉ au décompilé, corrigé, validé live et par mutation adversariale.
Le balayage des autres consommateurs de `HealUnitOperation` rend **0 autre rescapé**, énuméré.

---

## 1. Ce que dit le décompilé (build `rnca9r7q6c`)

`IdunBattleLogic.Entities.Abilities.Active.Loki.LivingMetalRepairAbility$$CreateBehaviour`, relu
verbatim :

```
pct    = IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(config, 0x12)
self   = <DSLSelectors+0x30>                          # Owner
amount = DSLFormulas$$PercentageOf( DSLFormulas$$StatAmount(self, 5 Health, 2 Maximum),
                                    DSLFormulas$$Direct(pct) )
opts   = IdunBattle.Entities.Behaviours.RepairBehaviourOptions$$ForRegenerate()
return   IdunBattleLogic.Entities.DSLBehaviors$$Repair(self, self, amount,
                                                       AbilityOrEffect(...), opts)
```

et `…$$CreateTrigger` = `<DSLTriggers+0x28> & DSLTriggers$$On(0x13, true) &
DSLTriggers$$IsDamaged(self)` — inchangé, déjà porté.

`RepairBehaviourOptions$$ForRegenerate` écrit `+0x10 = 1` (scope) puis `+0x14 = 0` (removeEffects) ;
`$$ForRepair` écrit l'inverse. Ce sont les **deux seules** fabriques du build.

**La fiche héritée disait vrai.** Le port appelait `HealUnitOperation`.

## 2. Pourquoi ce n'est pas cosmétique — et où la fiche héritée s'arrête trop tôt

Les deux Operations natives finissent sur le **même** `FillUpStatComponent$$FillUp`, donc l'état PV
bougeait. L'écart vit dans les étages qui les séparent, et il va **dans les deux sens** :

| # | étage | présent dans | conséquence du mauvais câblage |
|---|---|---|---|
| a | `AttackQuery$$EntityCanBeRepaired` (slot 0x12) | repair seul | **permissif** : aucune cible n'était refusée |
| b | `RepairModifier` de `PredictRepair` (gate `IsActor`) | repair seul | **chiffré** : les bonus de réparation REÇUS par la cible étaient ignorés |
| c | cap de GROUPE `scope == 1` de `PredictRepair` | repair seul | le cap existait, mais **ré-écrit à la main dans le trigger et appliqué AVANT (b)** — l'ordre natif est (b) puis (c) |
| d | `EntityExtensions.HasEffect(entity, 0x4f Cursed)` | **heal seul** | **restrictif** : le port REFUSAIT une régen que le natif accorde |

Le (d) n'était nommé nulle part, et c'est le plus intéressant : `RepairUnitOperation$$Execute`
n'a **aucun** test d'`EffectType.Cursed`. Son seul équivalent est
`UnitExtensions$$HasHealBlockers`, qui lit le dict `HealthComponent+0x78` — un conteneur DISTINCT.
Contrôle : aucune classe `CursedEffect` n'existe dans le binaire ; l'`EffectType` 79 n'est lu que
par `HealUnitOperation`.

### ⚠ Le critère de la fiche, tel qu'énoncé, n'est PAS atteignable — et il faut le dire

> « Une unité NON réparable (non mécanique, ou immunisée par `IsAffectedByHealType`) est-elle
> soignée par `LivingMetal` côté port ? »

La cible de ce behaviour est le **porteur lui-même** (`Repair(self, self, …)`), et

```
IsAffectedByHealType(unit, 1) = HasTrait(unit, 0x421 AffectedByHealAndRepair) || IsMechanical(unit)
IsMechanical(unit)            = HasTrait(5 Mechanical) || HasTrait(1000 LivingMetal) || HasTrait(0x405 Vehicle)
```

**Porter `LivingMetal`, c'est être `IsMechanical`.** Le disjunct passe donc toujours. `IsMachine`
(Machine of War) ne mord pas non plus : `python unit_map.py find --trait LivingMetal` rend **52**
porteurs (41 npc, 6 lineup, 4 summons, 1 tuto) et **aucune MoW**. Et `IsDamagedUnit` est déjà
garanti en amont par le `IsDamaged(self)` du `CreateTrigger`.

⇒ **Le gate est TAUTOLOGIQUE sur ce chemin.** Il est porté pour rester isomorphe au natif, pas
parce qu'un scénario de bataille saurait le faire refuser. Le régime (a) se teste donc sur un
**témoin** (`ultraApothecary`), en appelant le trigger par son chemin exact : c'est un contrôle
**structurel** du câblage, et le test le dit dans sa docstring.

Ce qui rend le bug réellement mesurable, ce sont (b) et (d).

## 3. Le fix

`engine/runner/operations/triggers/loki/living_metal.py` :

```python
repaired = RepairUnitOperation.execute(state, self.owner_id, self.owner_id, amount,
                                       scope=REGENERATE_SCOPE,            # ForRegenerate -> 1
                                       remove_effects=REGENERATE_REMOVE_EFFECTS)   # -> False
```

Doctrine #149 respectée : la **feuille** calcule le montant déclaratif (`PercentageOf(StatAmount)`)
et **appelle** l'Operation impérative ; elle n'en ré-écrit aucun étage. Le cap de groupe fait à la
main disparaît du trigger.

`engine/runner/operations/repair.py` — étage (2) de `predict_repair`, jusque-là non porté parce
qu'aucun call-site n'armait `scope = 1` :

```python
if int(scope) == 1:
    amt = min(amt, get_group_unit_heal_limit(mx, _group_unit_members(state, target_id), cur))
```

`_group_unit_members` mirror `GetComponent<NumberOfMembersComponent>(target)+0x10` (`nrOfMembers`) sur le
substrat runner (`StatsComponent.ctx.number_of_members`) — la même source que le `n` que le trigger
lisait.

**Résidu NOMMÉ, conséquence chiffrée nulle** : `attack_query.is_at_group_unit_heal_limit` est un
stub `False`, désormais ATTEINT (le gate le consulte sous `scope == 1`). Ce n'est pas une
indulgence : `IsAtGroupUnitHealLimit` est terme à terme `GetGroupUnitHealLimit <= 0` (les deux
natifs calculent le même `GetGroupUnitMaxHealthWithRemainingMembers`, l'un le compare à
`currentHealth`, l'autre l'en soustrait). L'étage (2) rend donc `predicted <= 0` exactement quand
le gate aurait refusé → `filled <= 0` → `return 0`, sans mutation ni trigger. `attack_query.py` est
par ailleurs le territoire d'un autre agent en vol — le stub n'a pas été touché.

**Résidu NOMMÉ, ATTEIGNABLE** — ⚠ **cette fiche l'a d'abord classé DEAD, et c'était FAUX**
(rectifié par #317, mesuré par #323) : le 3ᵉ implémenteur de `BaseEffect$$RepairBonus`,
`NetherRealmCasket_LivingMetalBonusEffect` (`EffectType` **1456**), a un gate
`get_OwnerIsTarget & TriggeringAbilityIs(LivingMetalRepair)` — c'est la **seule** branche que ce
rebranchement pourrait rendre atteignable, **et elle l'est**.

Le verdict d'origine (« `python unit_map.py find --ability NetherRealmCasket` rend **0 unité** »)
venait d'un **outil aveugle à la voie RELIQUE** : `find --ability` ne lisait alors que
`activeAbilities` + `passiveAbilities`. Mesure #323 : **18 porteurs**, dont les **3 héros du pool**
de `items/R_Booster_Crit_NetherRealmCasket.allowedUnits` (`necroWarden`, `necroSpyder`,
`necroDestroyer`), et `necroSpyder` la porte **ÉQUIPÉE** dans le seed BC
(`Units[].TertiaryAbility = 1462 = TriggeredAbilityType.NetherRealmCasket` ; ne pas confondre avec
l'`EffectType` 1462 `TheArdentBlade`). Ce qui bloque n'est donc pas l'absence de porteur, mais
l'absence du canal `triggering_ability` dans `engine.predict` **et** du canal relique dans le rail
COMBAT (résidus N317-a / N317-b). Détail : `docs/rl/case-323-unit-map-attribution-voies.md`.
⚠ **N317-a est fermé depuis (#357)** — le rail COMBAT lit la relique équipée
(`case-357-rail-relique-equipee.md`) ; il reste à le brancher sur les capture-helpers partagés
(`#357-r1`) et à porter l'ability 1456 elle-même.

## 4. Validation — le ROUGE a été VU AVANT

Mutation adversariale : re-branchement sur `HealUnitOperation` (avec la clé `repaired` conservée,
pour que seuls les ÉTAGES rougissent, pas le renommage).

```
FAILED test_living_metal_refuses_a_non_repairable_target
E   AssertionError: le trigger a REGENERE une cible non reparable ({'type': 'living_metal_repair',
    'unit': 81, 'amount': 1004, 'repaired': 1004, 'pct': 10}) -- c'est EXACTEMENT le residu #310
    (HealUnitOperation ne consulte pas EntityCanBeRepaired)
[LIVINGMETAL/gate] temoin=ultraApothecary hp=2000/10038 -> {'type': 'living_metal_repair', ...}

FAILED test_living_metal_is_not_blocked_by_cursed
E   AssertionError: un porteur sous Cursed n'a PAS regenere (delta=0, attendu 854) -- le gate 0x4f
    de HealUnitOperation s'applique encore, alors que RepairUnitOperation ne le porte pas
[LIVINGMETAL/cursed] attendu=854 offline=0 entry=None

FAILED test_living_metal_applies_the_repair_modifier
E   AssertionError: offline 854 != base 854 + RepairModifier 797 -- l'etage 1 de PredictRepair
    n'est pas traverse (c'est ce que HealUnitOperation ignorait)
[LIVINGMETAL/modifier] base=854 hpToRepair(lvl=50 mult=180)=797 attendu=1651 offline=854

FAILED test_living_metal_module_does_not_call_heal_unit_operation
4 failed, 2 passed
```

Les **2 verts** de la mutation sont exactement ceux qui ne peuvent pas séparer les deux voies : le
régime nominal live (les deux Operations mutent les PV pareil sur un porteur sain) et la garde
d'ORDRE, qui teste `predict_repair` et non le trigger. **C'est précisément pour ça que le bug a
survécu** — aucun test existant ne pouvait le voir.

Après restauration du fix : **6 passed**.

### Montage — fixture NOMMÉE, deux arms

`tests/engine/runner/_living_metal_stage.py` : `necroWarden` (porteur, blessé par `--unit-stat
RemainingHealth`) + `ultraApothecary` (témoin non mécanique, blessé LUI AUSSI — sinon son refus
s'expliquerait par `IsDamagedUnit` et le contrôle ne séparerait plus rien) + `orksWarboss`, board
`MC1_67`, seed 777, `advance=0`. `make_effect(...)` pose un effet matérialisé sur l'état capturé
(regimes Cursed / Nanoscarab) — `necroReanimator`, le poseur réel de 1545, est **hors du pool
spawnable** (l'un des 17 lineup absents du seed BC, `runner.md` §1bis).

### Non-régression live

| garde | résultat |
|---|---|
| `probe_203_livingmetal.py` | `offline 3000 == live 3000`, scoping OK — **OK** |
| `probe_203_swarm.py` | cap de groupe : `offline 0 == live 0`, 10 % non capé = 222 — **OK** |
| `test_repair_execution_live.py` + `test_fabricator_claw_array_live.py` | **15 passed** |
| `probe_181_targeting_gaps.py` | 97/97, 0 manquante |
| `probe_120_pre_unit_ability_fork.py` | registre 97, littéral manquant : aucun |
| `probe_273_gitignored_inputs.py --only-scan` | conforme |

### Ce qui n'est PAS couvert

* le régime (b) **RepairModifier** n'est validé qu'OFFLINE (conformité au décompilé) : l'effet 1545
  est posé sur l'état capturé. Le monter live exige `catalog_inject` pour `necroReanimator` + le
  pilotage d'un cast de MoW — faisable, non fait ;
* le régime (d) **Cursed** est dans le même cas : aucun poseur d'`EffectType` 79 n'a été cherché
  dans le pool (le prédicat natif est lu, pas mesuré) ;
* le gate (a) n'a **aucun** régime de bataille (cf. §2) — c'est un contrôle structurel ;
* `VoltagheistField_RepairReduction` (1382), le 2ᵉ implémenteur de `RepairBonus`, n'a pas été
  exercé : son `VoltagheistField_OnInitAbility` le pose sur son **propre** porteur
  (`admecSmnElectropriest`, traits `Summon`/`Mechanical`/`Resilient`), qui n'a pas `LivingMetal` —
  il ne peut donc pas influer sur cette régen.

## 5. Le balayage des autres rescapés — ÉNUMÉRÉ

`scripts/python/probe_310_heal_vs_repair_callers.py` (cliquet, à faire passer avant toute PR qui
touche au soin) :

* **sens PORT → NATIF**, par **AST** et pas grep (une mention en docstring ne doit pas compter — le
  module `living_metal.py` PARLE de `HealUnitOperation` dans son en-tête sans l'appeler) :
  **12 sites d'appel, 10 fichiers**, chacun déclaré avec le symbole natif qui le justifie →
  **10 déclarations, toutes `HEAL`, 0 autre rescapé**. Un site non déclaré fait ÉCHOUER le probe ;
  contre-épreuve jouée : la ré-introduction d'un appel dans `living_metal.py` rend
  `non declares=1 -> ** FAIL **` ;
* **sens NATIF → PORT** : **13** appelants de `IdunBattleLogic.Entities.DSLBehaviors$$Repair`,
  **4 portés** côté COMBAT (`RepairAbility` 28/1119, `FabricatorClawArray`,
  `InspiredToGreatness$$RepairOrHeal`, et désormais `LivingMetalRepair`). Les **9 ouverts**, avec
  leur raison :

| symbole | état |
|---|---|
| `…Loki.ReanimationBeamAbility$$ExecuteBehaviour` / `$$GetRepairBehaviour` | 1223, MoW `necroReanimator` — seul le volet REVIVE est porté |
| `…Loki.RelentlessMarchAbility$$CreateBehaviour` | `TriggeredAbilityType` 1004 (**homonyme d'id** avec `ActiveAbilityType.MortisRound`) |
| `…Loki.DefendTheDivineWorkAbility$$ExecuteBehaviour` | 1117 — playbook NonComparable porté (DÉCISION), face COMBAT non portée |
| `…Triggered.Loki.DawnBlade_HealAbility$$CreateBehaviour` | 1501 — **le nom dit `Heal`, l'artefact construit un `Repair`** |
| `…Triggered.Loki.EnhancementRegenerationAbility$$CreateBehaviour` | 1433 — fork `Repair` **et** `Heal` |
| `…Triggered.Loki.PowerUp_HealingAbility$$AdditionalBehavior` | 1273 — fork `Repair` **et** `Heal` |
| `…Triggered.Loki.SelfRepairMechanismAbility$$CreateBehaviour` | 1291 |
| `IdunBattle.Entities.Effects.Loki.LifeStealEffect$$CreateTargetTriggerBehaviour` | fork `Repair` **et** `Heal` ; le lifesteal PORTÉ est `SpiritLeech`, une ability distincte qui construit bien un `$$Heal` |

Aucun de ces 9 n'est dans `ABILITY_CLASSES` ni dans un registre de triggers : ce sont des tranches
neuves, pas des rescapés du même bug.

## 6. Re-dérivation

```bash
python probe_310_heal_vs_repair_callers.py                    # le cliquet + les deux inventaires
python probe_203_livingmetal.py                               # non-regression live du montant
python probe_203_swarm.py                                     # non-regression live du cap de groupe
python -m pytest tests/engine/runner/test_living_metal_repair_live.py -q
python unit_map.py find --trait LivingMetal                   # 52 porteurs, aucune MoW
python unit_map.py find --ability NetherRealmCasket           # 18 porteurs (3 heros du pool, voie:item)
python probe_323_ability_carrier_voies.py                     # les 5 voies d'attribution + le gisement
```

⚠ La 2ᵉ ligne rendait `0 unite` avant #323 (`unit_map` ne lisait ni `relicAbilities` ni
`items[*].abilityId`) et cette fiche en avait conclu « l'effet 1456 est DEAD ». **C'est ce zéro
qui était faux, pas l'effet** — cf. §3 et `docs/rl/case-323-unit-map-attribution-voies.md`.

Les tables natives du probe (les xrefs) ne sont pas dérivables du checkout ; leur commande de
re-dérivation ghidra est citée dans sa docstring.
