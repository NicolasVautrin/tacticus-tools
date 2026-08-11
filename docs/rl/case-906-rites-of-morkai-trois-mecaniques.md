# #906 — `1211 RitesOfMorkai` : l'audit classe UNE mécanique, le natif en fait TROIS

**Statut : PORTÉ ET CONFRONTÉ LIVE.** Face COMBAT complète (les trois volets), face DÉCISION non
portée (résidu `#906-r1`). Porteur `spaceWolfPriest` « Baldr » (Space Wolves, lineup) — **hors
seed BC**, amené par injection catalogue.

## 1. Ce que l'audit disait, et ce que le décompilé dit

L'audit `combat-ability-coverage.md` classait `1211` en **`EFFECT/BUFF`**. C'est vrai d'**une**
mécanique sur trois. `IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfMorkaiAbility$$ExecuteBehaviour`
fait, dans cet ordre :

```
zone  = Cache( Owner@DSLSelectors+0x30
               op_Addition
               UnitsWithoutTrait( SurroundingFriends( Owner@+0x30,
                                      range  = AbilityConfiguration$$GetNumberConstant(0x16 = range),
                                      unique = true, unitSelectionType = 3 ),
                                  trait = 0x5 = UnitTrait.Mechanical, selectionType = 3 ),
               matchAbilityEntities = true )

e1    = DSLBehaviors$$AddEffect( 0x5de = 1502 RitesOfMorkai,
                                 abilityState = AActiveAbility$$get_AbilityStateReference(this),
                                 targets = zone,
                                 turns   = TurnsFromRounds(ConfigConst(0x45 = nrOfRounds, config@+0x60)) )

e2    = DSLBehaviors$$AddEffect( 0x5f9 = 1529 RitesOfMorkai_ExtraDamage,
                                 abilityState = <un SECOND get_AbilityStateReference>,
                                 targets = DSLSelectors$$Filter( zone,
                                     HasTrait(ActiveTarget@+0x68, 0x3f6 = 1014 FinalJustice)
                                     op_BitwiseOr
                                     HasEffect(ActiveTarget@+0x68, 0x5ae = 1454 FinalVengeance_UnitEffect,
                                               onlyActive = 0, effectTargetType = 6 = Both) ),
                                 turns   = TurnsFromRounds(ConfigConst(0x45)) )

sel   = ValidNormalAttackTargets( Owner@+0x30, Tiles(Owner@+0x30), null, null, null )
        op_BitwiseAnd
        AdjacentEnemies( Owner@+0x30, unique = true, selectionType = 3 )
sel   = SortUnitsByDamageUtility( sel, Owner@+0x30, UnitNormalAttackType(Owner@+0x30),
                                  UtilityDefinition(0x23 = UtilityType.Damage),
                                  DSLFormulas$$NormalAttackDamage(Owner@+0x30),
                                  unitSelectionType = 0 = Any, hits = null )

atk   = DSLBehaviors$$If( DSLTriggers$$AmountIsGreaterThanZero(sel),
                          DSLBehaviors$$UseNormalAttack(Owner@+0x30, sel, null, null, <ZEROEE>),
                          <else> = null )

AActiveAbility$$Execute( op_Addition(op_Addition(e1, e2), atk) )
```

Le **troisième volet est une ATTAQUE NORMALE complète** — profil, coups, crit, block, riposte,
after-hit sont ceux de l'**arme de Baldr**, pas de l'ability (dont la config n'a même pas de
`damageProfile`). La colonne d'audit dérive du `damageProfile` de l'ability : elle ne peut
structurellement pas le voir. L'i2 le dit pourtant en clair : « After using this ability, Baldr
immediately performs a normal melee attack against an adjacent enemy. »

## 2. Les quatre points de structure qui ne sont pas cosmétiques

* **Le `Cache` de la zone est PARTAGÉ** par `e1` et par le `Filter` de `e2` — c'est le même objet
  sélecteur. Sans mémoïsation, la seconde pose relirait un plateau déjà muté par la première.
* **`AddEffect` est la surcharge à 4 arguments** `(effectType, abilityState, targets, turns)`, dont
  le corps (`IdunBattleLogic.Entities.DSLBehaviors$$AddEffect`) passe **littéralement `0` en
  `source`** à `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$.ctor` ⇒ **chaque cible est sa
  propre source**. C'est ce qui rend cohérent le revive SELF de 1502
  (`RitesOfMorkaiEffect$$CreateTargetFilter` = `get_OwnerIsTarget`). L'`abilityState`, lui, reste
  ancré sur le **CASTER** (`get_AbilityStateReference` =
  `DSLSelectors$$AbilityState(Caster@DSLSelectors+0x48, <l'active>)`).
* **`unitSelectionType = 0 = Any`** au `SortUnitsByDamageUtility` — LU au désassemblage
  (`mov dword ptr [rsp+0x30], r13d`, `r13d` zéroé). Sa jumelle structurelle
  `MartialExemplarAbility$$ExecuteBehaviour` passe `3` au même rang : recopier son littéral par
  analogie de forme aurait inventé un filtre.
* **AUCUN `Cache` sur la branche d'attaque**, alors que le même sélecteur y est consommé deux fois
  (par `AmountIsGreaterThanZero` puis par `UseNormalAttack`) : le natif l'évalue deux fois. Lu, pas
  supposé — le `Cache` du corps porte sur la ZONE.

## 3. Deux prédicats « mécanique » qui coexistent et DIFFÈRENT

| où | prédicat natif | ce qu'il écarte |
|---|---|---|
| la **ZONE** | `UnitsWithoutTrait(…, 0x5)` | le trait `Mechanical` **SEUL** |
| la **CIBLE** | `RitesOfMorkaiAbility$$GetDynamicInvalidTargetReason` → `UnitExtensions$$IsMechanical` | la **DISJONCTION** `Mechanical(5) \| LivingMetal(0x3e8) \| Vehicle(0x405)` |

Conséquence lue : un Necron `LivingMetal` **sans** `Mechanical` est refusé comme cible directe et
**reste dans la zone** si Baldr en vise une autre. Harmoniser les deux aurait été une invention.

Le gate dynamique complet est `target != null ? (IsMechanical(target) ? 2 : 0) : 2` — la branche
`target == null` est **explicite** au décompilé, pas une chute par défaut.

## 4. Le masque et l'`AbilityAttackType` — LUS, pas déduits

`RitesOfMorkaiAbility$$.ctor`, désassemblé :

```
mov  rax, [<TargetingRange klass> + 0xb8]           ; ses statics
movups xmm2, [rax + 0x18] / movsd xmm1, [rax + 0x28] ; copie de <statics + 0x18>, 24 octets
lea  r8, [rsp + 0x80]                                ; arg3 range = &cette copie
mov  r9d, 1  /  movzx edx, r9b                       ; forceMeleeTarget = 1 ; isSelfCasting = 1
mov  qword ptr [rsp + 0x20], 0x2008402               ; arg5 rules
mov  qword ptr [rsp + 0x28], 0  /  [rsp + 0x30], 0   ; les DEUX délégués dynamiques à null
call <TargetingOptions..ctor à 6 arguments>
mov  r8d, 2  ;  call <AActiveAbility..ctor>          ; 3e arg = AbilityAttackType.Others
```

* **Forme FLAGS DIRECTS** — tranchée par l'**ADRESSE APPELÉE**, confrontée à `frida/methods.tsv` :
  le `call` vise la surcharge `(isSelfCasting, range, forceMeleeTarget, rules,
  getDynamicInvalidCasterReason, getDynamicInvalidTargetReason)`. Les deux autres surcharges
  homonymes (`(template)` et `(template, additionalRules)`) vivent à d'autres adresses — c'est la
  seconde qui aurait exigé d'OU-er un preset. Le littéral **EST** donc le masque.
* `0x2008402` décomposé **exhaustivement**, aucun bit résiduel : `TargetMatchesDynamicRule(0x2)` |
  `TargetIsFriendly(0x400)` | `CasterIsPossibleTarget(0x8000)` |
  `AllowObscuredTargetByElevation(0x2000000)`.
* La portée est `TargetingRange` statics **`+0x18`** = `RANGE_FROM_CONFIG` (`.cctor` y écrit
  `+0x18 = 1 ; +0x1c = 1`, soit `useRangeFromConfig`) — le **même** static que `GrapnelLauncher` et
  `Foehammer`, et un **autre** que les `+0x30` (Adjacent) et `+0x60` (Self) des voisins du module.
* `AbilityAttackType = 2 = Others` **malgré** l'attaque normale que l'arbre enchaîne. Le
  contre-sens était facile ; le ctor tranche.

## 5. L'effet 1529, et le corps qui porte DEUX noms

`IdunBattle.Entities.Effects.Loki.RitesOfMorkai_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` :

```
EffectBonus.ForAddition( DSLTriggers.get_OwnerIsCaster,
                         DSLFormulas.ConfigVar(0x8 = extraDmg, GetAbilityState(this), config@+0x60) )
```

**UN SEUL nœud de trigger** — ni `IsMeleeAttack`, ni `IsNormalAttack`, aucun `op_BitwiseAnd` (lu à
l'assembleur : un seul `call` de trigger avant le `ForAddition`). Contraste exact avec
`1222 WarHowl_ExtraDamage_Unstoppable`, qui en porte trois. L'i2 : « deal +extraDmg Damage **with
all attacks** ». Recopier les trois gates de 1222 par analogie de forme aurait éteint le bonus sur
les tirs et sur les attaques d'ability, silencieusement.

Sa `CreateActiveCondition` est **le même corps machine** que
`$$HasAnyKindOfFinalVengeance` : la même adresse occupe **deux slots** du bloc `methodPointers` de
la classe (0x18 d'écart), et le build `gqfc5mff6c` nommait ce corps `CreateActiveCondition` là où
`rnca9r7q6c` le nomme `HasAnyKindOfFinalVengeance`. Déduplication IL2CPP — deux noms, une fonction.

`onlyActive = 0` sur le `HasEffect` est **lu et il mord** : le natif accepte une instance 1454
INERTE, alors que le défaut du nœud porté est `True`.

## 6. Un correctif de foyer PARTAGÉ, et sa mesure

`AddEffect` (`runner/abilities/behaviours/effects.py`) lisait le scaling `scale_from_source` sur
`src` — ce qui était exact tant que tous les call-sites portés faisaient coïncider `source` et
`abilityState`. La surcharge 4-args les **dissocie** : `source` est NULL (→ la cible) tandis que
l'`abilityState` reste celui du caster. Sans correctif, `scale_from_source=True` +
`source_from_target=True` donnait `_source_scaling(state, None)` = `(None, None, None)` — **aucun
scaling**.

**Mesure live** (mutant `no_scale`) : le port tombe de **19408** à **15856** de dégât sur
l'attaque de suivi, soit **3552** de moins, et diverge du natif. `extraDmg` **et** `hp` sont tous
deux dans `variablesAffectedByRarityBonus` de la config `RitesOfMorkai` : l'écart de multiplicateur
entre deux unités est donc numérique, et il aurait été silencieux.

## 7. Confrontation live — montage, discrimination, mutants

**Montage** : `spaceWolfPriest` est hors seed BC ⇒ `catalog_inject.write_augmented_seed_bc` +
`rl_duel build --seed-bc` (la voie de référence, déjà mesurée sur CE porteur en #229). Roster
choisi pour **discriminer**, un allié par verdict attendu :

| unité | traits | verdict attendu |
|---|---|---|
| `spaceWolfPriest` (caster) | `Hero, Healer, FinalJustice, Terrifying` | 1502 + 1529 |
| `spaceWulfen` | `Hero, FinalJustice, Unstoppable` | 1502 + 1529 |
| `astraCreed` | `Hero` | **1502 seul** |
| `admecMarshall` | `Hero, Mechanical` | **ni l'un ni l'autre** |

`probe_906_rites_of_morkai_live.py`, board `MC1_67`, seed 777, `--hp-target 60000` :

```
V1 zone 1502     port=[81, 83, 85]   natif=[81, 83, 85]   OK
V2 filtre 1529   port=[81, 83]       natif=[81, 83]       OK
V3 attaque       port=[77]           natif=[77]           OK
                 hp: 60000 - 19408 -> port=40592  natif=40592  OK
```

**Deux bras, et aucun n'exerce tout** — Baldr n'a que six voisins. Alliés d'abord : le MÉCANIQUE
arrive au contact et son exclusion prouve le filtre de trait, mais l'ennemi reste enfermé à 2 hexes
(V3 muet). Ennemi d'abord : V3 est exercé, mais `admecMarshall` reste à 2 et son exclusion ne
prouve plus que la portée. Le probe **dit lequel est exercé**, allié par allié.

**Le `--hp-target 60000` est load-bearing** : au premier jet la cible mourait (10040 PV pour 12063
de dégât) et les deux côtés rendaient `hp = 0` — un accord **saturé**, qu'un port infligeant 11000
aurait passé.

**Cinq mutants, tous MORDENT** (le vert s'y lit à l'envers : un mutant inerte dénonce un témoin
aveugle) :

| mutant | effet mesuré |
|---|---|
| `no_extra_dmg` (canal +extraDmg muet) | 19408 → **15820**, V3 DIVERGE |
| `no_filter` (Filter Final Vengeance neutralisé) | 1529 sur `[81,83,85]`, V2 DIVERGE |
| `no_mech_filter` (UnitsWithoutTrait neutralisé) | 1502 sur `[81,83,85,**87**]`, V1 DIVERGE |
| `range0` (rayon forcé à 0) | V1 DIVERGE |
| `no_scale` (scaling lu sur le porteur) | 19408 → **15856**, V3 DIVERGE |

Le mutant `no_extra_dmg` prouve en outre un fait que rien d'autre n'établissait : **le natif
applique bien `+extraDmg` sur l'attaque de suivi, dans le même cast** — l'effet 1529 est posé avant
et mord immédiatement.

## 8. Ce qui n'est PAS couvert

* **Face DÉCISION** : `IdunBattle.AI.Playbook.Loki.RitesOfMorkaiPlaybook` (`ShouldEvaluate` +
  `EvaluateNonComparable`, plus trois lambdas de closure) n'est pas portée — résidu **`#906-r1`**.
  L'IA choisit donc 1211 par le chemin générique.
* **`--far`** (allié à 2 hexes) n'a pas été joué : le mutant `range0` établit que le rayon est lu et
  mord, mais rien ne distingue live `range = 1` de `range = 2`.
* **`active_condition_ported` reste FALSE** pour 1529 : `is_active` mirrore la
  `CreateActiveCondition`, mais les deux membres du `op_BitwiseOr` n'ont pas la même sûreté de
  mesure. Le port exige donc `e.active` **et** `is_active` — dégradation restrictive.
* **Le scaling d'une instance SEEDÉE** (état rechargé où le natif avait déjà posé) retombe sur le
  porteur : résidu **`#382`**, partagé par les 135 entrées d'`EFFECT_CLASSES`, antérieur à cette
  tranche.
* **`AllowObscuredTargetByElevation`** est inerte offline : aucune règle d'obstruction n'est portée
  par la cascade de ciblage. Le bit est une **permission**, pas un refus — le noter évite qu'il soit
  relu un jour comme un gate.
* **Le revive lui-même** (1502) n'est pas re-confronté ici : il l'a été par #229
  (`probe_1502_rites_of_morkai_live.py`). Cette tranche ferme le trou inverse — **rien ne le posait
  jamais hors seed**.

## 9. Où c'est

| quoi | où |
|---|---|
| l'arbre + la classe + le masque + le gate dynamique | `engine/runner/abilities/spacewolves.py` |
| l'effet 1529 | `engine/entities/effects/loki/rites_of_morkai.py` |
| le revive 1502 (antérieur) | `engine/runner/operations/triggers/loki/rites_of_morkai.py` |
| le correctif de pose | `engine/runner/abilities/behaviours/effects.py` |
| la confrontation live + les 5 mutants | `scripts/python/probe_906_rites_of_morkai_live.py` |
| les 6 étages de garde offline | `scripts/python/tests/engine/runner/test_906_rites_of_morkai_offline.py` |
