# #966 — `HealingBalms` (`spaceWolfPriest`) et `WayOfTheShortBlade` (`tauFarsight`)

Build : `rnca9r7q6c`. Les deux faces DÉCISION étaient **déjà portées** avant cette tranche
(`HealingBalms_HealPlaybook` #27-4d ; `WayOfTheShortBladeNonOwnerPlaybook` #477-r33) — le travail
est la face **COMBAT**, qui était **nulle** pour les deux.

## 1. Recensement — par la colonne « classe déclarante », base LUE dans `frida/classes.tsv`

### `HealingBalms` (`TriggeredAbilityType` 0x5de = **1502**)

| classe native | base (LUE `classes.tsv`) | slots | corps propres | fondu ICF |
|---|---|---|---|---|
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HealingBalmsAbility` | `IdunBattle.Entities.Abilities.BaseTriggeredAbility` | 3 | **1** (`CreateBehaviour`) | **OUI** — `CreateTrigger` **et** `.ctor` |
| `IdunBattleLogic.Entities.Abilities.Active.Loki.HealingBalms_HealAbility` | `IdunBattle.Entities.Abilities.AActiveAbility` | 3 | 3 (`ExecuteBehaviour`, `GetDynamicInvalidTargetReason`, `.ctor`) | non |
| `IdunBattle.Entities.Effects.Loki.HealingBalmsEffect` | `IdunBattle.Entities.Effects.BaseEffect` | 3 | 3 (`.ctor`, `CreateTargetTrigger`, `CreateTargetTriggerBehaviour`) | non (`CreateTargetSelector` absent = hérité) |
| `IdunBattle.AI.Playbook.Loki.HealingBalms_HealPlaybook` | `ComparablePlaybook<HealingBalms_HealAbility>` | 4 | 4 | non |
| `IdunBattle.View.AbilityConfigs.Loki.HealingBalmsVisuals` | `AActiveAbilityVisualsBase` | — | — | (vue, hors périmètre) |

**Le `CreateTrigger` fondu, lu au bloc `methodPointers`.** Absent de `ghidra/functions.tsv` ET de
`frida/methods.tsv` — l'absence ne prouve rien. Le bloc de pointeurs range les classes en ordre
**alphabétique** par triplets `(CreateTrigger, CreateBehaviour, .ctor)` ; les trois triplets lus :

    Haywire<b>Mine</b>SteppableAbility : (HaywireMineSteppableAbility$$CreateTrigger,
                                         HaywireMineSteppableAbility$$CreateBehaviour, <.ctor>)
    <b>Headwoppas</b>KillchoppaAbility : (<corps de WayOfTheShortBlade_InitAbility$$CreateTrigger>,
                                         HeadwoppasKillchoppaAbility$$CreateBehaviour, <.ctor>)
    <b>HealingBalms</b>Ability        : (<corps de SummaryExecutionAddBaseEffectAbility$$CreateTrigger>,
                                         HealingBalmsAbility$$CreateBehaviour, <.ctor>)

Le `.ctor` de chacun est fondu avec `UnityEngine.Scripting.RequiredByNativeCodeAttribute$$.ctor`.
⇒ `HealingBalmsAbility$$CreateTrigger` = `return <DSLTriggers+0x30>` =
`On(0x21 = AbilityInit) & <YesTrigger> & get_OwnerIsActor` — le trigger d'INIT partagé. C'est un
passif d'INIT, **jamais** un `ABILITY_TRIGGERS`.

### `WayOfTheShortBlade` (`TriggeredAbilityType` 0x5dc = **1500**)

| classe native | base (LUE `classes.tsv`) | slots | corps propres | fondu ICF |
|---|---|---|---|---|
| `...Triggered.Loki.WayOfTheShortBlade_InitAbility` | `BaseTriggeredAbility` | 3 | 2 (`CreateTrigger`, `CreateBehaviour`) | `.ctor` |
| `...Triggered.Loki.WayOfTheShortBlade_AttackAbility` | `BaseTriggeredAbility` | 3 | 2 (`CreateTrigger`, `CreateBehaviour`) | `.ctor` |
| `IdunBattle.Entities.Effects.Loki.AWayOfTheShortBladeEffect` | `BaseEffect` | — | 1 (`GetAffectedUnits`) | `.ctor` |
| `IdunBattle.Entities.Effects.Loki.WayOfTheShortBladeEffect` | `AWayOfTheShortBladeEffect` | — | 4 (`CreateTargetSelector`, `IsValidAttackForBonus`, `CreateEffectDamageBonusForAttack`, `IgnoreArmor`) | `.ctor` |
| `...Effects.Loki.WayOfTheShortBlade_AdditionalAttackMarkerEffect` | `AWayOfTheShortBladeEffect` | — | 3 (`.ctor`, `CreateTargetSelector`, `CreateActiveCondition`) | `CreateActiveCondition` **partagé** (`= <DSLTriggers+0x40>` = constante VRAIE) |
| `IdunBattleLogic.Playbook.Triggered.Loki.WayOfTheShortBladeNonOwnerPlaybook` | `TriggeredAbilityNonOwnerPlaybook<WayOfTheShortBlade_InitAbility>` | — | `CalculateAttackUtilityInSteps` + son itérateur | non |

⚠ **Collision d'ordinal à qualifier** : `EffectType.WayOfTheShortBlade_AdditionalAttackMarker = 1500`
**et** `TriggeredAbilityType.WayOfTheShortBlade = 1500`. Idem côté HealingBalms :
`EffectType.RitesOfMorkai = 1502` = `TriggeredAbilityType.HealingBalms`.

## 2. Le critère d'émetteur — réponse CHIFFRÉE

Recensement **exécutable** (AST sur tout `TriggerEvent(EventTriggerType.X, …)` de `engine/**`) :
**42 `EventTriggerType` distincts émis, 45 sites littéraux + 4 sites à argument dynamique**.

| face à trigger | événement natif | émetteur côté port ? |
|---|---|---|
| `HealingBalmsAbility$$CreateTrigger` | `On(0x21 AbilityInit)` (`<DSLTriggers+0x30>`) | **sans objet** — canal `ABILITY_INIT_OWNER_EFFECTS`, pas un event (`SpecificAbilityInit = 49` n'est jamais émis, par construction) |
| `HealingBalmsEffect$$CreateTargetTrigger` | `On(0x13 = 19 TurnStart_Other)` | **OUI**, 1 site : `triggers/dispatch/turn.py:62` |
| `WayOfTheShortBlade_InitAbility$$CreateTrigger` | `OnOwnerSpecificAbilityInit` | **sans objet** — même canal |
| `WayOfTheShortBlade_AttackAbility$$CreateTrigger` | `On(0x9 Attack)` | **OUI**, 2 sites : `dispatch/attack.py:350`, `:483` |

**Aucun NON.** Les deux faces à trigger réel de la tranche ont leur émetteur ; aucune n'entrerait
*registered-but-dead*. (Le critère avait révélé deux trous structurels sur d'autres tranches —
`EffectAdded (0x3e)` et `On(0x39 PreDamageTaken)` ; ici il ne trouve rien, et c'est le résultat.)

## 3. `HealingBalms` — PORTÉ (face COMBAT)

RE et arbres : docstrings de `engine/runner/abilities/loki/healing_balms.py` (§SWAP + §ACTIVE),
`engine/entities/effects/loki/healing_balms.py`, `engine/runner/operations/triggers/loki/healing_balms.py`.

Ce qui entre au registre, DANS LE MÊME COMMIT :

| registre | entrée |
|---|---|
| `ABILITY_CLASSES` | `1212 -> HealingBalms_HealAbility` |
| `TARGETING_OPTIONS` | `0x8402` (`TargetMatchesDynamicRule|TargetIsFriendly|CasterIsPossibleTarget`), `range = TargetingRange` statics+0x00 = `RANGE_ADJACENT_IF_MELEE_CASTER`, `forceMeleeTarget = 2` |
| `ABILITY_ATTACK_TYPE` | `1212 -> Others` (3ᵉ argument d'`AActiveAbility..ctor`) |
| `EFFECT_CLASSES` | `HealingBalms_ExtraCritDamage` (1503, `CriticalDamage`), `HealingBalms_ExtraCritChance` (1504, `CriticalChance`) |
| `EFFECT_TRIGGERS` | `1508 -> [HealingBalmsDelayedHeal]` (`On(TurnStart_Other) & IsTurnOf(Owner)`) |

**Ce que le SWAP n'a PAS reçu, et pourquoi c'est une mesure** : `HealingBalmsAbility$$CreateBehaviour`
(`AddFlag(CanHealFullHealthUnits) + RemoveActiveAbility(18) + AddActiveAbility(1212)`) n'a **aucune**
entrée de registre. Mesuré live (§5) : `decisionView` publie sur Baldr `1212 HealingBalms_Heal`
(`level 50`, `multiplier 180`) et **pas** `18 Heal` — le runner natif a déjà joué l'`AbilityInit` au
spawn. Le rejouer côté port serait un no-op au mieux, une double-pose au pire.

**Le piège du voisin de forme, évité et mesuré** : `...HealingBalms_HealAbility$$GetDynamicInvalidTargetReason`
a un corps **strictement plus court** que celui de son voisin `TwistedScience_HealAbility` — il ne
teste que `IsAffectedByHealType(target, 0)`, sans consulter `AttackQuery.EntityCanBeHealed`. C'est
là, et **pas** dans le flag `CanHealFullHealthUnits`, que vit le « can heal friendly units even if
they are at full Health » de l'i2. Recopier le voisin aurait fermé le ciblage sur exactement le cas
que l'ability existe pour ouvrir — **confirmé live** (§5, étage 4).

## 4. `WayOfTheShortBlade` — face COMBAT **NON PORTÉE**, RE COMPLÈTE consignée

La RE est **entière** (tous les corps lus) ; le port ne l'est pas — budget de tranche. Les arbres,
mirrorables en l'état :

    ...WayOfTheShortBlade_InitAbility$$CreateTrigger  = OnOwnerSpecificAbilityInit(this.AbilityType)
    ...WayOfTheShortBlade_InitAbility$$CreateBehaviour =
        AddEffect(0x5db = 1499 _DamageBuff, AbilityStateReference, Owner@+0x30, Owner@+0x30)
          op_BitwiseAnd
        AddEffect(0x5dc = 1500 _AdditionalAttackMarker, AbilityStateReference, Owner, Owner)

    AWayOfTheShortBladeEffect$$GetAffectedUnits =
        UnitsWithTrait( SurroundingFriends(Owner@+0x30,
                            range = GetNumberConstant(config, 0x16 = range),
                            unique = true, OnlyAliveAndTargetable),
                        0x10 = UnitTrait.Hero, OnlyAliveAndTargetable )

    WayOfTheShortBladeEffect$$CreateTargetSelector =
        Unique( UnitsWithRangedWeapons(GetAffectedUnits())
                op_Addition UnitsFromFaction(GetAffectedUnits(), 0x9 = Tau, OnlyAliveAndTargetable) )
        # ⚠ SANS `+ Owner` -- l'i2 dit « of OTHER friendly Characters » : Farsight n'a PAS le buff

    WayOfTheShortBlade_AdditionalAttackMarkerEffect$$CreateTargetSelector =
        UnitsFromFaction(GetAffectedUnits(), 0x9 = Tau, OnlyAliveAndTargetable)
        op_Addition Owner@+0x30                       # ⚠ AVEC `+ Owner` : Farsight EST marqué
    ...$$CreateActiveCondition = <DSLTriggers+0x40>   # constante VRAIE, toujours actif

    WayOfTheShortBladeEffect$$IsValidAttackForBonus =
        get_OwnerIsCaster
          & IsNormalAttack  & IsRangedAttack
          & NOT CurrentAttackDamageProfileIs(0xd = DamageProfileType.Psychic)
          & AmountIsGreaterThanZero( UnitsWithTrait(
                Friends(Owner@+0x30, AdjacentUnits(Target@+0x60, unique, OnlyAliveAndTargetable),
                        OnlyAliveAndTargetable),
                0x10 = Hero, OnlyAliveAndTargetable) )
    WayOfTheShortBladeEffect$$CreateEffectDamageBonusForAttack =
        Nullable( EffectBonus.ForPercentIncrease(IsValidAttackForBonus(),
                      ConfigVar(0xa = extraDmgPct, GetAbilityState(), config@+0x60)) )
    WayOfTheShortBladeEffect$$IgnoreArmor =
        ConfigVar(0x40 = armorIgnored, GetAbilityState(), config@+0x60)

    ...WayOfTheShortBlade_AttackAbility$$CreateTrigger =
        On(0x9 = Attack, ownerNeedsToBeAlive: 1)
          & IsMeleeAttack()
          & AreFriends(Caster@+0x48, Owner@+0x30, ByCurrentTeam, anyEntity: false)
          & IsEffectTarget(Caster@+0x48, 0x5dc = 1500 _AdditionalAttackMarker)
    ...WayOfTheShortBlade_AttackAbility$$CreateBehaviour =
        AddFlag(Caster@+0x48, 0x15 = UnitFlag.ForceRangedAttack)
          & UseNormalAttackIfAble(Caster@+0x48, Target@+0x60, <parentAbility>, <trigger>, <options>)
          & RemoveFlag(Caster@+0x48, 0x15)

**Ce que la structure dit et que le tooltip ne dit pas** :

* les deux effets ont des sélecteurs **DIFFÉRENTS**, et l'écart est un seul terme : le marqueur
  ajoute `+ Owner`, le buff de dégât non. Recopier l'un pour l'autre donnerait à Farsight un buff
  que le natif lui refuse ;
* le buff couvre `(Hero amis dans range AVEC arme à distance)` **∪** `(Hero amis dans range de
  faction Tau)` — une **union**, pas une intersection ;
* la condition du bonus regarde les voisins de la **CIBLE** (`AdjacentUnits(Target)`), pas ceux du
  porteur ;
* `AddFlag(ForceRangedAttack)` **encadre** l'attaque supplémentaire et est **retiré juste après** :
  c'est ce qui réalise le « even if they are adjacent to it » sans laisser le flag collé.

## 5. Confrontation LIVE — ce qui est mesuré, et ce qui ne l'est pas

Runner `build#1200`, board `MC1_67`, seed `31337`, seed BC augmenté par
`catalog_inject --units spaceWolfPriest,tauFarsight`. Probe : `scripts/python/probe_966_healing_balms_short_blade.py`.

| étage | mesure | verdict |
|---|---|---|
| 1. **CO-INJECTION** | `catalog_inject` accepte la LISTE : `catalogue Units 175 -> 177`, **4** configs d'ability ajoutées (`RitesOfMorkai`, `HealingBalms`, `ExemplarOfTheMontka`, `WayOfTheShortBlade`). Les deux porteurs spawnent dans la MÊME équipe : `u81 [spaceWolfPriest]` @(1,0) et `u83 [tauFarsight]` @(0,0) | **OK** — la co-injection de deux porteurs de FACTIONS DIFFÉRENTES fonctionne |
| 2. **SWAP `18 -> 1212`** | `decisionView` sur `u81` : `[69 Loki_NormalAttack, 1211 RitesOfMorkai, 1212 HealingBalms_Heal (level 50, multiplier 180)]` — **`18 Heal` ABSENTE** | **OK** — le substrat livre le swap ; l'arbitrage « pas d'entrée de registre » est MESURÉ, pas supposé |
| 3. **`WayOfTheShortBlade` init** | effets publiés sur `u83` : `WayOfTheShortBlade_DamageBuff`, `WayOfTheShortBlade_AdditionalAttackMarker` (+ ses autres passifs). L'allié Tau `u87 [tauCrisis]` n'en porte **aucune instance** | **OK** — `_InitAbility$$CreateBehaviour` confirmé : les DEUX effets vivent sur le PORTEUR, la projection est un SÉLECTEUR d'aura, pas des instances par cible |
| 4. **ciblage de 1212 à PV PLEINS** | `abilityTargets(1212)` sur `u81` : **2** cibles — `85 spaceBlackmane` (allié adjacent) **et `81 spaceWolfPriest` (lui-même)**, toutes deux à PV pleins (runner frais) | **OK** — `CasterIsPossibleTarget` (0x8000) confirmé ET absence de gate `EntityCanBeHealed` confirmée |

**NON COUVERT, et nommé** :

* **l'EXÉCUTION du cast de 1212 n'est pas confrontée** : la forme d'`applyAction` employée
  (`{"kind":"ability","unitId","abilityId","targetId"}`) est revenue `ok = None` sans muter le
  runner ; le budget de tranche s'est arrêté là. Les effets `1503`/`1504`/`1508` posés, la magnitude
  du soin, le RÉ-ARMEMENT par `RemoveEffect` et le soin RETARDÉ au `TurnStart_Other` suivant sont
  donc **PORTÉS-NON-CONFRONTÉS**. Résidu **#966-r3** ;
* **le SIGNE des deux stat-mods (1503/1504) n'est pas LU** : `isNegative` vit dans la lambda
  `EffectsDatabase.<InitializeEffects>b__14_*`, que ni la recherche littérale `0x5df`/`1503` dans le
  pseudo-C ni les xrefs n'exposent sur ce build. POSITIF retenu sur trois indices concordants (i2,
  noms `extra*`, jumeau `AncestralFortune_ExtraCritChance`) et **aucun décompilé**. Résidu **#966-r1** ;
* **le flag `CanHealFullHealthUnits`** n'a pas de substrat porté et **aucun consommateur porté ne le
  lit** (son lecteur est le `18 Heal` générique, lui-même hors `ABILITY_CLASSES` — #931-r1).
  Résidu **#966-r2** ;
* **`WayOfTheShortBlade` face COMBAT** : non portée. Résidu **#966-r4**.
