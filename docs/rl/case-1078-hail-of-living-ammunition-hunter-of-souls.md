# case-1078 — `HailOfLivingAmmunition` et `HunterOfSouls` : deux `GAP-MENTION` à porteur `S?`

Deux passifs de `passive-ability-coverage.md`, section « GAPS non confrontables », porteurs `S?`.
`GAP-MENTION` ne voulait dire ici **rien d'autre que « le nom apparaît quelque part »** : établi
**par exécution** (voir §1), **aucun** des deux n'était câblé dans un seul des registres.

Verdict : `HailOfLivingAmmunition` **PORTÉ et CONFRONTÉ** (4 phases live, 3 contre-épreuves) ;
`HunterOfSouls` **NON PORTÉ**, RE complète et porteur établi, trois résidus nommés.

## 1. Ce qui existait au registre — PAR EXÉCUTION, jamais par grep

Balayage des **14** registres (les 7 de `runner/operations/triggers/dispatch/registry.py`,
`EFFECT_CLASSES`, `ABILITY_INIT_OWNER_EFFECTS`, `TRAIT_DERIVED_ABILITIES`,
`CUSTOM_NORMAL_ATTACK_BY_PASSIVE`, `ABILITY_CLASSES`, `ABILITY_ATTACK_TYPE`,
`TRIGGERED_ABILITY_BEHAVIOURS`), chacun interrogé avec **son propre** enum d'indexation :

| clé | résultat |
|---|---|
| `TriggeredAbilityType.HailOfLivingAmmunition` = 1042 | **ABSENT des 14** |
| `EffectType.HailOfLivingAmmunition_ExtraHits` = 1042 | **ABSENT des 14** |
| `TriggeredAbilityType.HunterOfSouls` = 1497 | **ABSENT des 14** |
| `EffectType.HunterOfSouls_ExtraDamage` = 1495 | **ABSENT des 14** |

⚠ **Un balayage naïf rend DEUX faux positifs, tous deux par collision d'ordinal entre enums** :
`ABILITY_CLASSES[1042]` existe — c'est `ActiveAbilityType.FlailSwing`, pas notre passif ; et
`EFFECT_TRIGGERS[1497]` existe — c'est `EffectType.Maugetar_HasNotMoved`, pas
`TriggeredAbilityType.HunterOfSouls`. Interroger un registre avec le mauvais enum **rend une
entrée**, et elle se lit comme « déjà câblé ».

Les seules occurrences des deux noms dans `engine/**` sont des **mirrors d'enum** et des
**avertissements de prose** sur ces mêmes collisions (`effects/factory.py`,
`effects/loki/norn_crown.py`, `triggers/loki/neuroparasite.py`, `runner/abilities/loki/summon.py`).

## 2. `HailOfLivingAmmunition` (1042) — porté

### 2.1 Porteur : VOIE 3 (jumeau npc), et les deux autres voies sont ÉLIMINÉES par mesure

| voie | verdict |
|---|---|
| 1 — invocateur unité | **EXCLUE**. Balayage EXHAUSTIF du gameconfig (toute chaîne de l'arbre) : `tyranSmnTermagant` apparaît **3 fois**, toutes dans les `constants.unitIds` de ses propres passifs (`HailOfLivingAmmunition`, `BroodProgenitor`, `SynapticBacklash`). Aucune `constants.unitId*` ne le nomme ; les trois `SpawnTermagants{,2,3}` invoquent des `GuildBoss1Npc*`. Confirmé à l'exécution : `catalog_inject.explicit_stats("tyranSmnTermagant")` refuse — « aucune ability du gameconfig ne déclare `tyranSmnTermagant` » |
| 2 — ability d'ENVIRONNEMENT | **EXCLUE**. `EnvFactionSummons:Tyranids` invoque `tyranSmnBarbgaunt` |
| 3 — jumeau npc | **RETENUE**, et ce n'est même pas un mirror par `visualId` : les **cinq** npc Termagant portent le passif eux-mêmes (`units.npc.<id>.passiveAbilities[0]`). `--explicit-stats tyranNpc3Termagant:45` |

⚠ Le nom entre au pool **suffixé du palier** ; `--p-units` doit reprendre la chaîne VERBATIM.

### 2.2 RE

`IdunBattleLogic.Entities.Abilities.Active.Loki.HailOfLivingAmmunitionAbility` dérive
d'`IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility` (`frida/classes.tsv`) et n'override
que `$$GetEffectType`, dont le corps ENTIER est `return 0x412` — l'appariement ability → effet est
**LU**. Ni `CreateBehaviour` ni `CreateTrigger` à porter.
⚠ Le namespace `Active` ne dit PAS la voie : le kit l'attribue en `passiveAbilities`, l'ordinal
1042 est un `TriggeredAbilityType`, et `ActiveAbilityType` 1042 est `FlailSwing`.

`IdunBattle.Entities.Effects.Loki.HailOfLivingAmmunitionExtraHitsEffect$$CreateEffectHitsBonusForAttack` :

```
ids = GetStringArrayConstant(config@this+0x60, AbilityConstantType.unitIds = 0x37)
sel = DSLSelectors.AdjacentFriends(Owner@DSLSelectors+0x30, unique = true, selectionType = 3)
sel = DSLSelectors.UnitsWithIds(sel, ids)
amt = Multiply( Direct(GetNumberConstant(config, AbilityConstantType.extraHit = 0x2b)), Count(sel) )
trg = get_OwnerIsActor & IsRangedAttack
-> EffectBonus.ForAddition(trg, amt)
```

**Ce n'est PAS le jumeau `HungeringSwarm` (1041), et les deux écarts sont LUS** — recopier le
voisin de forme aurait compté le mauvais voisinage sur la mauvaise attaque :

| | 1041 `HungeringSwarm` | 1042 `HailOfLivingAmmunition` |
|---|---|---|
| centre du voisinage | la **CIBLE** (`AdjacentUnits(Target) − Caster`, puis `Friends(Owner)`) | l'**ATTAQUANT** (`AdjacentFriends(Owner)`) |
| gate de nature | `IsMeleeAttack` | `IsRangedAttack` |

### 2.3 Le bug trouvé : `UnitsWithIds` comparait le mauvais id

La phase `kronos` (géométrie **identique** à `armed`, seul l'id du voisin change) a rendu :

| voisin | `visualId` observé | natif | port AVANT |
|---|---|---|---|
| `tyranNpc3Termagant:45` | `tyranNpc3Termagant` | **+2** | +2 |
| `tyranNpc3TermagantKronos:45` | `GuildBoss1Npc2TyranTermagantKronos` | **+0** | **+2** ✘ |

`IdunBattle.Entities.UnitExtensions$$HasUnitId(unit, id, state)` =
`GetUnitIdWithoutRarity(GetUnitId(GetUnit(unit))) == id`, et
`IdunBattle.Entities.UnitExtensions$$GetUnitId` lit le champ **+0x10** du composant d'identité —
l'id de **CONFIG**. La `VisualId` vit à **+0x20** et c'est la **seule des deux qu'un canal live
publie** (`decisionView.units[].visualId` ← `UnitComponent.VisualId`, `frida/hooks/game/match-state.ts`).
Le `visualId` du Kronos EST dans `unitIds`, son id de config ne l'est pas.

**Réparation** (`engine/entities/selectors/units.py::has_unit_id`) : le `visualId` observé est
**RÉSOLU** vers les id de config du gameconfig qui peuvent le présenter (`visualId(c) or c`), et
`cfg_id` est testé contre CET ensemble ; **repli sur la comparaison historique** quand aucune unité
du gameconfig ne présente cet id (contenu de guild boss) — la réparation ne RETIRE donc aucun
comportement.

**Rayon de souffle MESURÉ** sur les cinq constantes `unitIds`/`affectedUnitIds` du gameconfig :
**6 verdicts changent**, tous sur les **deux mêmes** `visualId` (`...Kronos`, `...Gorgon`) et sur
les trois listes Termagant ; `HungeringSwarm` (#1018) et `SupremeCommander` (#119) changent de **0**,
et **aucun** `visualId` n'est ambigu pour ces consommateurs. Les trois fichiers live correspondants
ont été rejoués : **27 passed**.

⚠ **Un second cran, trouvé par le RE-JEU live et PAS par le recensement.** Le résolveur fait
satisfaire **plusieurs** volets de l'union à la même unité (un Termagant npc peut être
`tyranNpc3Termagant` **ou** `tyranSmnTermagant`, tous deux listés) : le port a rendu **+4** pour
+2 natif. On retient le PREMIER id de la liste que l'unité peut présenter, le doublon d'un `ids`
qui RÉPÈTE un id étant conservé (le natif n'insère aucun `Unique`). Le recensement offline ne
pouvait pas voir ce cran : il modélisait le VERDICT, pas la MULTIPLICITÉ de l'union.

### 2.4 Confrontation live (`probe_1078_hail_of_living_ammunition.py`, board `MC1_67`)

Attaquant `tyranNpc3Termagant:45` en (3,4) — arme `2x Bio r2` à distance, `1x Physical` en mêlée ;
cible `ultraTitus` armure 0, PV 900 000.

| phase | voisins | cible | coups natifs | bonus natif | port |
|---|---|---|---|---|---|
| `armed` | 2× `tyranNpc3Termagant`, d(att) = 1 | d = 2 | **4** | +2 | **+2** |
| `far` | LES MÊMES, d(att) = 2 | d = 2 | **2** | +0 | **+0** |
| `melee` | 2× `tyranNpc3Termagant`, d(att) = 1 | d = 1 | **1** | +0 | **+0** |
| `kronos` | 2× `tyranNpc3TermagantKronos`, d(att) = 1 | d = 2 | **2** | +0 | **+0** |

Les trois contre-épreuves cassent des rails **différents** et aucune ne se déduit d'une autre :
`far` = la GÉOMÉTRIE à roster constant ; `melee` = la NATURE DU COUP à géométrie constante (seule
la cible bouge) ; `kronos` = le FILTRE D'ID à géométrie **et** nature constantes.

Les deux tuiles de voisinage sont à **élévation 3, la même que l'attaquant** : la porte
`|dElev| < 2` de `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles` ne peut pas trancher
entre les deux lectures d'adjacence, donc le montage ne dépend pas du résidu `#497-r1`.

## 3. `HunterOfSouls` (1497) — NON PORTÉ, RE complète

### 3.1 Porteur : VOIE 1, et elle est ÉTABLIE

Le summon `thousSmnDaemonPrince` (« Z'Kar ») est invoqué par `AetherStride`
(`ActiveAbilityType` 1208, `constants.unitId = thousSmnDaemonPrince`), portée par la **Machine of
War** `thousDaemonPrince` (lineup) et par le npc MoW `thousNpcMowDaemonPrince`. Aucun jumeau npc
n'existe pour le summon — c'est le **seul** des deux items dans ce cas.

`thousDaemonPrince` n'est **pas** dans les 8 MoW du pool, mais il est dans
`catalog_inject.py --missing` → injectable. Et surtout : **#1022 a déjà monté ce chemin** —
`AetherStride` est GREFFÉE sur `ultraDreadnought` (MoW du pool) via
`catalog_inject.graft_active_ability`, la condition de greffe étant vérifiée au décompilé, et
`thousSmnDaemonPrince` est **déjà dans `BC.Units` du seed**. Le porteur est donc **CONFRONTABLE** ;
`AetherStride` elle-même est déjà au registre (`ABILITY_CLASSES[1208]`).

### 3.2 RE — cinq artefacts natifs, dont un invisible des tables (ICF)

* `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HunterOfSoulsAbility` — `CreateBehaviour`,
  `GetLocalizationData`. Son `CreateTrigger` n'existe **pas** comme symbole : corps **dédupliqué**,
  appartenance établie dans le bloc de pointeurs (`0x1832609c8`, slot précédant immédiatement son
  `CreateBehaviour`, même disposition que le run de `HunterOfSouls_KilledAbility`), puis confirmée
  par le CONTENU — même corps que
  `IdunBattleLogic.Entities.Abilities.Active.Loki.LethalMiasmaAbility$$CreateTrigger` =
  `On(0x16 = TurnStart_Actions, ownerNeedsToBeAlive: 1) & <DSLTriggers+0x28>`.
* `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HunterOfSouls_KilledAbility` —
  `CreateTrigger` = `On(0x36 = UnitDefeated) & get_OwnerIsTarget` ;
  `CreateBehaviour` = `AddFlag(Owner@+0x30, 0x16) + ReAddMachine(Parent(Owner@+0x30, root: 0),
  NOT HasFlag(Owner@+0x30, 0x3))`.
* `IdunBattle.Entities.Effects.Loki.HunterOfSouls_ExtraDamageEffect` (`EffectType 0x5d7 = 1495`) —
  `.ctor`, `CreateEffectDamageBonusForAttack`, `GetDamageBonusMultiplier`, `GetUnits`.
* `IdunBattle.View.AbilityConfigs.Loki.HunterOfSoulsVisuals` — vue, hors périmètre.
* `aiUtilities.Default.UnitEffectsAdjacent.HunterOfSouls_ExtraDamage` = **20** (face DÉCISION).

`HunterOfSoulsAbility$$CreateBehaviour` :

```
If( NOT HasEffect(Owner@+0x30, 0x5d7 = 1495, null, 6),
    AddEffect(0x5d7, AbilityStateReference, targets = Owner@+0x30, turns = null) )
op_Addition
( PerformAIAttack(Owner@+0x30, allowMoveAction: 1, null, null, null)
  op_Addition AddFlag(Owner@+0x30, 0x16)
  op_Addition RemoveUnit(Owner@+0x30)
  op_Addition ReAddMachine(Parent(Owner@+0x30, root: 0), <DSLTriggers+0x70>) )
```

`HunterOfSouls_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` :

```
sel = UnitsWithTrait( AdjacentFriends(Owner@+0x30, unique = 1, selectionType = 3),
                      UnitTrait.Psyker = 0x3ea, 3 )
amt = Multiply( ConfigVar(AbilityVariableType.extraDmg = 8, GetAbilityState(this), config@+0x60),
                Count(sel) )
-> EffectBonus.ForAddition( get_OwnerIsCaster, amt )
```

`$$GetUnits(dsl)` = `Count(<le MÊME sous-arbre>)` seul — c'est ce que lit la face DÉCISION ;
`$$GetDamageBonusMultiplier(dsl, bonusMultiplier, abilityState, config)` =
`Multiply(ConfigVar(8), bonusMultiplier)`. `extraDmg` **est** dans
`variablesAffectedByRarityBonus` → scalé par le multiplicateur de rareté du porteur.
Jumeau structurel exact : `EnmityForTheUnworthy_ExtraDamage` (1400, #948), à ceci près que le
filtre est un **trait** (`UnitsWithTrait(Psyker)`) et non une **faction**, et qu'il n'y a **aucun**
étage `NonSteppableOrObjectUnits` ni aucune `CreateActiveCondition`.

### 3.3 Pourquoi le port n'est pas livré

Le `CreateBehaviour` de l'ability exige **trois nœuds DSL que le port n'a pas** — `RemoveUnit`,
`ReAddMachine`, `AddFlag` (seul `PerformAIAttack` existe, dans
`runner/abilities/behaviours/summon.py`) : c'est un blocage d'**étage**, pas de porteur. L'effet
1495, lui, est portable seul mais demande une **clé de contexte per-coup neuve** (« amis Psyker
adjacents ») dans deux foyers très partagés (`runner/damage_model.py` **et**
`playbook/prediction/normal_attack.py`) plus le montage greffé de #1022 pour la confrontation —
tranche à part entière. Livrer l'effet sans le confronter serait un port spéculatif.

## 4. Résidus

* **`#1078-r1`** — le volet MONO-ID `entities/selectors/geometry.py::UnitsWithId` mirrore le MÊME
  `IdunBattle.Entities.Selectors.UnitsWithIdSelector` et compare encore le `visualId` directement.
  Il n'est **pas** basculé sur `has_unit_id` parce que son consommateur `SynapticLinchpin`
  (`constants.unitId = tyranSmnHormagaunt`) tombe dans le régime **AMBIGU** que les cinq listes
  `unitIds`/`affectedUnitIds` n'exercent pas : `tyranNpc1Hormagaunt` est présenté par le npc **et**
  par le summon, et seul le summon est listé — la résolution y sur-approximerait. Basculer demande
  sa propre re-validation live.
* **`#1078-r2`** — `HunterOfSoulsAbility` / `HunterOfSouls_KilledAbility` non portées : il manque
  les nœuds DSL `RemoveUnit`, `ReAddMachine` et `AddFlag`. Le conjoint `<DSLTriggers+0x28>` du
  trigger (construit par `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` comme
  `QuoteInstruction(Owner@DSLSelectors+0x30, <entities+0x10>)`) n'est pas nommé.
* **`#1078-r3`** — `HunterOfSouls_ExtraDamage` (1495) non porté : l'arbre est lu et minuscule, mais
  il exige une clé de contexte per-coup neuve dans les deux foyers de substrat, et sa confrontation
  passe par le montage greffé de #1022.
