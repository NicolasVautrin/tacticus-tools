# case-317 — Inventaire des 13 appelants natifs de `DSLBehaviors$$Repair`

**Critère** : pour chacun des 13 call-sites de `IdunBattleLogic.Entities.DSLBehaviors$$Repair`,
l'artefact porté côté Python est-il un `Repair` ou un `Heal` — et si c'est un `Heal`, est-ce une
faute ?

**Réponse, mesurée** : côté port, **aucun** des 13 n'est câblé sur le soin. Les 4 portés passent
tous par `RepairUnitOperation` (dont `LivingMetalRepair`, rebranché par #310) ; les 9 restants ne
sont **pas portés du tout** — ce sont des tranches neuves, pas des rescapés du bug #310. Le
balayage AST inverse (`probe_310_heal_vs_repair_callers.py`) le confirme dans l'autre sens : 10
déclarations, **toutes `HEAL`**, 0 rescapé.

Re-dérivation : `python scripts/python/probe_317_repair_callers_inventory.py`
(la table native vient de ghidra, la ventilation des porteurs est dérivée du gameconfig à chaque
exécution).

---

## 1. Ce que la fiche #310 disait de FAUX (corrigé ici, et pourquoi ça compte)

| affirmation #310 | mesure #317 |
|---|---|
| « `LivingMetal` est le SEUL call-site `ForRegenerate` du build — les 12 autres passent `ForRepair` » | **FAUX**. `IdunBattle.Entities.Effects.Loki.LifeStealEffect$$CreateTargetTriggerBehaviour` passe lui aussi `$$ForRegenerate`. Et **deux** appelants n'appellent AUCUNE fabrique : ils écrivent les champs à la main après `RepairBehaviourOptions$$.ctor` — dont `EnhancementRegenerationAbility`, qui pose `scope = 1`. ⇒ **3** call-sites arment le cap de GROUPE, pas 1. |
| « `NetherRealmCasket_LivingMetalBonusEffect` (1456) est DEAD : `unit_map.py find --ability NetherRealmCasket` rend 0 unité » | **FAUX, et le raisonnement est le piège du cas.** `unit_map find --ability` ne lit que `activeAbilities` + `passiveAbilities` : il est **aveugle aux reliques**. `NetherRealmCasket` est l'ability de l'item `R_Booster_Crit_NetherRealmCasket`, `allowedUnits = [necroWarden, necroSpyder, necroDestroyer]` — **trois héros du pool** — et `necroSpyder` la porte **déjà équipée** dans le seed BC courant (`Units[].TertiaryAbility = 1462`). `necroSpyder` a le trait `LivingMetal`. Le bonus est donc **atteignable**, pas mort. |

Le second point est exactement la faute que #310 dénonçait, transposée d'un axe à l'autre : #310
classait par le NOM de l'artefact, ici on classait par un OUTIL aveugle à une voie d'attribution.

## 2. Les trois voies d'attribution d'une ability — et celle qu'on oublie

1. **`activeAbilities` / `passiveAbilities`** du gameconfig → `ABILITY_TRIGGERS` /
   `ACTIVE_ABILITY_TRIGGERS` (`triggers/dispatch/registry.py`) ;
2. **`traits`** → `TRAIT_TRIGGERS` (ex. `LivingMetal` → `LivingMetalRepair` ; le trait `Mechanic`
   accorde l'`ActiveAbilityType 28 Repair`, qui n'a AUCUNE entrée `units.abilities`) ;
3. **RELIQUE** — deux formes, et le port n'en voit aucune :
   * `relicAbilities` en dur sur l'unité (les 5 npc `tauBossFarsight*` / `tauNpcFarsight` portent
     `DawnBlade` ainsi) ;
   * item relique ÉQUIPÉ par le joueur : `items[*].abilityId` + `allowedUnits`, matérialisé dans
     `BattleConfiguration.Units[].TertiaryAbility` (+ `TertiaryAbilityLevel`,
     `TertiaryAbilityVariablesMultiplierPercentage`). **4 unités sur 175** du seed BC en portent
     une (`necroSpyder` 1462, `orksRuntherd` 1475, `admecMarshall` 1457, `admecRuststalker` 1457).

Le gap (3) est déjà nommé ailleurs : `probe_193_move_playbook_inventory.py` volet 2 mesure
« BC.Units avec une RELIQUE équipée que le port n'expose PAS », et
`engine/ai/context.py::live_triggered_ability_ids` (RPC `unitAbilityStates`) est la seule lecture
FIDÈLE du kit déclenché — côté DÉCISION uniquement. Le rail COMBAT
(`triggers/dispatch/core.py::collect_triggered_abilities`) n'a pas ce canal.

## 3. L'inventaire — 13 call-sites

`scope`/`removeEffects` = `RepairBehaviourOptions+0x10` / `+0x14`. Les deux fabriques statiques,
relues verbatim sur `rnca9r7q6c` : `$$ForRepair` = `(0, 1)`, `$$ForRegenerate` = `(1, 0)`.

| # | symbole natif (`$$CreateBehaviour` sauf mention) | artefact | options | enum QUALIFIÉ | porté COMBAT |
|---|---|---|---|---|---|
| 1 | `…Active.RepairAbility` | `Repair` | ForRepair | `ActiveAbilityType` 28 `Repair` / 1119 `Repair_GalvanicField` | **oui** (#299) |
| 2 | `…Active.Loki.FabricatorClawArrayAbility` | `Repair` | ForRepair | `ActiveAbilityType` 1006 | **oui** (#303) |
| 3 | `…Active.Loki.InspiredToGreatnessAbility$$RepairOrHeal` | `If(IsRepairable, Repair, Heal)` | ForRepair (branche THEN) | `ActiveAbilityType` 1082 | **oui** (les 2 branches) |
| 4 | `…Active.Loki.LivingMetalRepairAbility` | `Repair` | **ForRegenerate** | `TriggeredAbilityType` 1010 | **oui** (#310) |
| 5 | `…Active.Loki.ReanimationBeamAbility$$ExecuteBehaviour` | `Repair` | ForRepair | `ActiveAbilityType` 1223 | non |
| 6 | `…Active.Loki.ReanimationBeamAbility$$GetRepairBehaviour` | `Repair` | ForRepair | `ActiveAbilityType` 1223 | non |
| 7 | `…Active.Loki.RelentlessMarchAbility` | `AddEffect(0x3f3) + Repair` | ForRepair | `TriggeredAbilityType` 1004 (**homonyme** d'`ActiveAbilityType` 1004 `MortisRound`) | non |
| 8 | `…Active.Loki.DefendTheDivineWorkAbility$$ExecuteBehaviour` | `Repair` | ForRepair | `ActiveAbilityType` 1117 | non (DÉCISION portée) |
| 9 | `…Triggered.Loki.DawnBlade_HealAbility` | **`Repair`** | ForRepair | `TriggeredAbilityType` 1501 `DawnBlade` (l'`EffectType` 1501 est `DawnBlade_ExtraDmg` — autre enum) | non |
| 10 | `…Triggered.Loki.EnhancementRegenerationAbility` | `If(Repairable, Repair, Heal)` | **ctor ad-hoc** `+0x10=1` (scope), `+0x14=0`, `+0x15=1`, `+0x18=1` | `TriggeredAbilityType` 1433 | non |
| 11 | `…Triggered.Loki.PowerUp_HealingAbility$$AdditionalBehavior` | `If(IsMechanical, Repair, Heal)` | **ctor ad-hoc** `+0x10=0`, `+0x14=1`, `+0x16=1` | `TriggeredAbilityType` 1273 | non |
| 12 | `…Triggered.Loki.SelfRepairMechanismAbility` | `Repair` | ForRepair | `TriggeredAbilityType` 1291 | non |
| 13 | `IdunBattle.Entities.Effects.Loki.LifeStealEffect$$CreateTargetTriggerBehaviour` | `If(IsRepairable, Repair, Heal)` | **ForRegenerate** | `EffectType` posé par `TriggeredAbilityType` 1309 `EnhancementLifeSteal` | non |

### Le piège du cas, en une ligne

**#9 `DawnBlade_HealAbility` ment DEUX FOIS** : son nom dit `Heal` alors qu'elle construit un
`Repair`, et la variable qu'elle lit s'appelle `hpToHeal` —
`GetVariableForLevel(config, 0x20, …)`, et `AbilityVariableType` 32 = `hpToHeal` (les autres
appelants lisent `0x24` = 36 = `hpToRepair`). Deux noms, deux fois faux : seul l'artefact tranche.

## 4. Confrontabilité, ventilée porteur par porteur

| # | ability gameconfig | hero / MoW | summon | npc | verdict |
|---|---|---|---|---|---|
| 1 | — (trait `Mechanic` → 28 ; passif `GalvanicField` → 1119) | `admecManipulus`, `necroSpyder`, … (pool) | — | — | confrontable, **déjà porté** |
| 2 | `FabricatorClawArray` | `necroSpyder` (**pool**) | — | 5 | confrontable, **déjà porté** |
| 3 | `InspiredToGreatness` | `tauAunShi` (**pool**) | — | 4 | confrontable, **déjà porté** |
| 4 | — (trait `LivingMetal`) | 6 lineup | 4 | 41 | confrontable, **déjà porté** |
| 5–6 | `ReanimationBeam` | `necroReanimator` (**MoW, hors pool → injectable**) | — | 1 | **confrontable** |
| 7 | `RelentlessMarch` | `necroWarden` (**pool**) | — | 5 | **confrontable** |
| 8 | `DefendTheDivineWork` | `admecManipulus` (**pool**) | — | 5 | **confrontable** |
| 9 | `DawnBlade` | `tauFarsight` — **par la RELIQUE `R_Crit_DawnBlade` uniquement** (hors pool) | — | 5 (`relicAbilities` en dur) | confrontable côté NATIF ; **le port n'a pas le canal relique** (§2) |
| 10 | `EnhancementRegeneration` | **aucun** — accordée par un `liveEvents/idunLiveEventConfigs[…]/enhancements/Regeneration_01` | — | — | **NON confrontable** (hors bataille régulière) |
| 11 | `PowerUp_Healing` | — | — | `powupHealing` : traits `Steppable`/`Invincible`/`Immune` = **power-up de TERRAIN**, pas une unité npc hostile | présence board-dépendante, **non mesurée ici** |
| 12 | `SelfRepairMechanism` | **aucun porteur** | — | — | **DEAD sur ce build** : aucune référence hors du catalogue ; son successeur `SelfRepairMechanismReworked` (1474, `admecBossBelisarius`) construit un `AddStaticStatModifierEffectToOwner`, **pas** un `Repair` |
| 13 | `EnhancementLifeSteal` | **aucun** — `liveEvents/…/enhancements/LifeSteal_01` | — | — | **NON confrontable** |

## 5. Tranches ouvertes (une par ability, non portées ici)

Par ordre de valeur décroissante (porteur confrontable × écart mesurable) :

1. **`RelentlessMarchAbility`** (triggered 1004, `necroWarden`, **dans le pool**) —
   `AddEffect(0x3f3)` + `Repair(Owner, UnitsWithoutTrait(Friends(AdjacentUnits(Owner)), 0x418), …)`.
   Le porteur est directement spawnable : c'est la tranche la moins chère à valider live.
   ⚠ qualifier l'enum : 1004 est **`TriggeredAbilityType.RelentlessMarch`**, homonyme d'id avec
   `ActiveAbilityType.MortisRound`.
2. **`DefendTheDivineWorkAbility`** (active 1117, `admecManipulus`, **dans le pool**) — face
   DÉCISION déjà portée (playbook NonComparable), face COMBAT à faire :
   `Repair(Caster, Friends(AdjacentUnits) + Caster, …)` puis `ExecuteAtomic(0x2a)` +
   `Repair_GalvanicFieldAbility$$CreateAttackBehavior`. Deux Operations à enchaîner.
3. **`ReanimationBeamAbility`** (active 1223, MoW `necroReanimator`, hors pool → `catalog_inject`)
   — les call-sites #5 et #6 sont **la même feuille** ; seul le volet REVIVE est porté
   (`triggers/loki/reanimation_beam.py`). Sélecteur :
   `Repairable(EntitiesWithAnyEffect(MechanicalUnits(Friends(Owner)), 0x609))`.
4. **`DawnBlade_HealAbility`** (triggered 1501) — portée par cette PR côté behaviour + trigger,
   **câblage relique non fermé** (§6).
5. **`PowerUp_HealingAbility`** (triggered 1273) — dépend d'un power-up de terrain ; commencer par
   MESURER si un board du pool en pose un.
6. **`SelfRepairMechanismAbility`** (1291) — **dead-code**, ne pas porter.
7. **`EnhancementRegenerationAbility`** (1433) / **`LifeStealEffect`** (1309) — enhancements de
   live-event, hors bataille régulière : mirror offline seulement, aucun montage possible.
   ⚠ Ce sont pourtant **2 des 3** call-sites `scope == 1` : toute évolution du cap de GROUPE de
   `predict_repair` doit les citer.

## 6. Tranche portée : `DawnBlade_HealAbility`

Cf. `engine/runner/operations/triggers/loki/dawn_blade.py` pour la RE in extenso. En bref :

```
CreateTrigger  = On(UnitDeath = 0, ownerNeedsToBeAlive = true)
                 & get_OwnerIsActor
                 & IsDefeatedByMeleeAttack(Targets@0x60, countRevived = false,
                                                          countResurrected = true)
CreateBehaviour = Repair( Owner@0x30, Owner@0x30,
                          Get(GetVariableForLevel(cfg, 0x20 = hpToHeal)),
                          AbilityOrEffect(DawnBlade 1501), ForRepair )
```

Doctrine #149 respectée : la feuille calcule le montant déclaratif et **appelle**
`RepairUnitOperation` ; elle n'en ré-écrit aucun étage.

### Le gate MORD-il ? (question posée par le cas — réponse : OUI, deux fois)

Contrairement à `LivingMetal` (gate `EntityCanBeRepaired` **tautologique** : porter `LivingMetal`
implique `IsMechanical`), ici le gate mord réellement :

* la cible est le porteur `tauFarsight`, dont les traits sont
  `Hero, BeastSlayer, BigTarget, Flying, Mechanical` → `IsAffectedByHealType` passe par
  `IsMechanical`. Ce disjunct-là ne mord pas ;
* **mais** `IsDamagedUnit` n'est PAS garanti en amont (contrairement à `LivingMetal`, dont le
  `CreateTrigger` porte un `IsDamaged(self)`) : un Farsight à PV pleins qui tue en mêlée
  **ne répare rien**. C'est un refus réel du gate, et c'est ce que le test exerce ;
* le gate de TRIGGER `IsDefeatedByMeleeAttack` mord aussi : un kill à DISTANCE ne déclenche pas.

### Résidus NOMMÉS de cette tranche

* **canal RELIQUE** : le seul porteur non-npc (`tauFarsight`) obtient `DawnBlade` par l'item
  `R_Crit_DawnBlade`, matérialisé dans `BC.Units[].TertiaryAbility` — que
  `collect_triggered_abilities` ne lit pas (§2). Le câblage posé ici lit `relicAbilities` du
  gameconfig, ce qui couvre les porteurs qui l'ont **en dur** (les 5 npc Farsight) et rend le
  trigger inerte pour le héros. Fermer le gap demanderait de faire descendre le kit déclenché
  RÉEL (RPC `unitAbilityStates`, déjà consommé côté DÉCISION) jusqu'au rail COMBAT — chantier
  distinct, hors périmètre de cette tranche ;
* **`countRevived` / `countResurrected`** de `UnitsDefeatedByMeleeAttackSelector` : le natif teste
  `UnitExtensions.HasFlag(unit, 0x14)` / `HasFlag(unit, 0xe)` sur la victime. Le port ne modélise
  pas ces deux flags ; il retient la condition principale (`la victime est morte du coup en
  cours`), ce qui coïncide dans tout régime porté (une victime revivée ne passe pas par
  `unit_death_triggers`, cf. la garde revive de `_kill_unit_operation`) ;
* **`DawnBlade_InitAbility`** (2ᵉ classe native du même id 1501) et l'effet
  `DawnBladeEffect` (`EffectType` 1501 `DawnBlade_ExtraDmg`, +dégât mêlée cumulatif, 2 triggers
  propres `On(0x17)` / `On(9)`) ne sont **pas** portés : c'est l'autre moitié du kit relique, hors
  périmètre « appelants de `$$Repair` ».
