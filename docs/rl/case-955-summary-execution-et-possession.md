# #955 — `SummaryExecution` (Yarrick) et `Possession` (Archimatos)

Deux passifs de kit, chacun le dernier item manquant de son kit ; les deux porteurs
(`astraYarrick`, `blackPossession`) sont au pool, aucune injection catalogue.

## 1. Recensement — par le bloc `methodPointers`, jamais par grep de nom

Le tableau de pointeurs du PE est lu (`GameAssembly.dll` du build `rnca9r7q6c`), résolu pointeur
par pointeur contre `data/symbols/rnca9r7q6c/ghidra/functions.tsv`, et **segmenté par classe**.
Un corps est **PROPRE** quand il n'est le corps d'aucune autre classe ; les autres sont fondus par
l'ICF et n'apparaissent donc sous **aucun** nom exploitable au grep.

| classe | slots | propres | faces DÉDUPLIQUÉES (invisibles au grep) |
|---|---|---|---|
| `…Abilities.Active.Loki.SummaryExecutionAbility` | 3 | **2** | `.ctor` (= `UnityEngine.Scripting.RequiredByNativeCodeAttribute$$.ctor`, corps vide) |
| `…Abilities.Active.Loki.SummaryExecutionAddBaseEffectAbility` | 3 | **1** | `CreateTrigger` (corps ICF partagé, **58** références), `.ctor` |
| `IdunBattle.Entities.Effects.Loki.SummaryExecutionEffect` | 4 | **3** | `CreateTargetSelector` (= `…SummaryExecution_AlwaysEffectEffect$$CreateTargetSelector`) |
| `IdunBattle.Entities.Effects.Loki.SummaryExecution_AlwaysEffectEffect` | 3 | **3** | — |
| **total `SummaryExecution`** | **13** | **9 (69 %)** | |
| `…Abilities.Active.Loki.PossessionAbility` | 3 | **2** | `.ctor` |
| **total `Possession`** | **3** | **2 (67 %)** | |

**La face cachée qui CHANGE le port** : `SummaryExecutionEffect` n'a **pas** de
`CreateTargetSelector` propre — son slot pointe sur le corps de son voisin
`SummaryExecution_AlwaysEffectEffect`. Les DEUX effets ont donc **le même sélecteur d'aura**
(`Friends(Owner, UnitsWithTrait(AllAliveUnits, BattleFatigue))`). Le lire « Owner » (effet SELF,
comme le piège de #952) ou l'omettre aurait rendu `1031` inerte.

**Ce que le tableau du dispatch donnait pour `Possession` était FAUX** : les quatre classes
`AttemptedPossession*` (`_PossessedEffect`, `…Ability`, `…Playbook`) appartiennent à
`ActiveAbilityType.AttemptedPossession = 1101`, l'**active de `thousSorcerer`** (Thaumachus), pas
au passif `TriggeredAbilityType.Possession = 1034` de `blackPossession`. Elles sont **déjà
portées** (`engine/runner/abilities/loki/attempted_possession.py`,
`engine/playbook/noncomparable/attempted_possession.py`,
`engine/entities/effects/loki/possession.py`). `Possession` n'a **ni effet, ni playbook** : son
bloc entier tient en trois slots.

## 2. `SummaryExecution` — les arbres (mirror 1:1)

```
SummaryExecutionAddBaseEffectAbility$$CreateTrigger
    = <DSLTriggers+0x30>                    # trigger d'INIT partagé, cf. #952 :
                                            # On(0x21 = AbilityInit) & <YesTrigger> & get_OwnerIsActor
SummaryExecutionAddBaseEffectAbility$$CreateBehaviour
    AddDynamicStatModifierEffectToOwner( effectType = 0x413 = EffectType.SummaryExecution_BaseEffect,
                                         statType   = 0     = StatType.Attack,
                                         turns      = null (PERMANENT),
                                         isHidden   = false )

SummaryExecution_AlwaysEffectEffect$$CreateTargetSelector
    Friends( Owner@<DSLSelectors+0x30>,
             UnitsWithTrait( AllAliveUnits@<DSLSelectors+0x20>,
                             0x3f7 = UnitTrait.BattleFatigue,
                             3 = UnitSelectionType.OnlyAliveAndTargetable ),
             3 )
SummaryExecution_AlwaysEffectEffect$$GetDynamicStatModificationAmount
    ConfigVar( 0x409 = TriggeredAbilityType.SummaryExecution,
               EffectSource( Get(effect) ),
               8 = AbilityVariableType.extraDmg )

SummaryExecutionAbility$$CreateTrigger
      NOT HasEffect(Owner@+0x30, 0x407 = EffectType.SummaryExecution_Effect,
                    onlyActive = false, targetType = 6)
    & On(0x33 = EventTriggerType.PreUnitFled, ownerNeedsToBeAlive = true)
    & AreFriends(Owner@+0x30, Actor@<DSLSelectors+0x40>, 0, anyEntity = false)
    & TriggeringAbilityIs( 0x401 = TriggeredAbilityType.BattleFatigue )
SummaryExecutionAbility$$CreateBehaviour
      AddDynamicStatModifierEffectToOwner( 0x407 = SummaryExecution_Effect, StatType.Attack,
                                           null, false )
    & Kill( Owner@+0x30, Actor@+0x40, KillUnitBehaviourOptions.ForDirectKill() )

SummaryExecutionEffect$$CreateTargetSelector        = LE MEME CORPS que celui de 1043 (ICF)
SummaryExecutionEffect$$GetDynamicStatModificationAmount
    ConfigVar( SummaryExecution, EffectSource(Get(effect)), 9 = AbilityVariableType.extraDmg_2 )
SummaryExecutionEffect$$ApplyInternal
    AStatModifierEffect.ApplyInternal(owner, target, effect)
    ; BaseEffect.AddSubEffect(effect, target, 0x437 = EffectType.IgnoreBattleFatigue, turns = null)
```

Les deux `.ctor` d'effet appellent
`AStatModifierEffect..ctor(sourceAbility, unitEffectType = null, canBeImmuneTo = false,
keepOnRevive = true, isMultiply = false)` — donc canal **ADDITIF** sur le stat, jamais
multiplicatif.

**L'ANNULATION DE LA FUITE EST DANS `FleeOperation`, PAS DANS LE PASSIF.**
`IdunBattle.Operations.FleeOperation$$Execute` commence par

```
IOperationProcessor.<slot 81 = EvaluateAbilities>( actor = unit, caster = unit, target = unit,
                                                   eventType = 0x33 = PreUnitFled,
                                                   abilityOrEffect = triggeringAbilityOrEffect )
if (UnitExtensions.IsDead(unit)) return;        // <- la fuite est ABANDONNEE
```

C'est le « executed **instead** » de l'i2 : le `Kill` du passif rend l'unité morte, et le natif
sort avant `RecordFlee` / `RemoveUnit` / `UnitFlag 9` / `On(0x34 = UnitFled)`.

## 3. `Possession` — l'arbre (mirror 1:1)

```
PossessionAbility$$CreateTrigger
      ( On(0x35 = EventTriggerType.PostUnitKill, ownerNeedsToBeAlive = true)
        & get_OwnerIsActor )
    & ( AreEnemies(Owner@+0x30, Target@<DSLSelectors+0x60>, 0)
        & NOT IsObjectOrSteppable(Target@+0x60) )
    & NOT TriggeringAbilityIs( 0x438 = TriggeredAbilityType.ItsGonnaBlow )

PossessionAbility$$CreateBehaviour
    unitId  = AbilityConfiguration.GetStringConstant(cfg, 0 = AbilityConstantType.unitId)    # blackSmnBloodletter
    unitId2 = AbilityConfiguration.GetStringConstant(cfg, 4 = AbilityConstantType.unitId_2)  # thousSmnBlueHorror
    optsA   = SpawnUnitOptions.WithStatsFromConfig (cfg, abilityState, null, null)   # -> ordinal 1
    optsB   = SpawnUnitOptions.WithStatsFromConfig2(cfg, abilityState, null, null)   # -> ordinal 2
    hex     = PickRandomly( FreeTilesOrAdjacentFreeTiles( Tiles(Target@+0x60) ),
                            amount = 1, allowDuplicates = false,
                            maxDuplicatesAllowed = 0x7fffffff, ignoreForcedTargets = false )
    cond    = NOT IsDefeatedByMeleeAttack(Target@+0x60, countRevived = true, countResurrected = true)
    return    If( cond,
                  Spawn(Owner@+0x30, hex, unitId2, optsB),     # kill NON-melee -> Blue Horror
                  Spawn(Owner@+0x30, hex, unitId,  optsA) )    # kill MELEE     -> Bloodletter
```

`WithStatsFromConfig` / `WithStatsFromConfig2` sont deux **thunks** vers la même surcharge à
5 arguments, avec `ordinal = 1` / `ordinal = 2` — c'est l'ordinal qui choisit
`summonHp`/`summonDmg` (1) contre `summonHp_2`/`summonDmg_2` (2). La surcharge appelle
`SetStatFromConfig` **sept** fois : `0x29 summonHp -> 5`, `0x2a summonDmg -> 0`,
`0x2b summonArmor -> 0x10`, `0x56 summonBlockChance -> 7`, `0x55 summonBlockDmg -> 8`,
`0x54 summonCritChance -> 9`, `0x57 summonCritDmg -> 10` ; le gameconfig de `Possession` ne
fournit que les deux premières paires.

`IsDefeatedByMeleeAttack(u, r, s)` = `AmountIsGreaterThanZero(UnitsDefeatedByMeleeAttack(u, r, s))`,
et `UnitsDefeatedByMeleeAttackSelector$$IsValidUnit` exige `<composant>+0x178 != 0` (le drapeau
« défait par une attaque de MÊLÉE ») **et** (`HasFlag(9 = Fled)` | `HealthComponent.IsDead` |
`countRevived && HasFlag(0x14)` | `countResurrected && HasFlag(0xe)`).

## 4. Surcharges tranchées par l'ADRESSE RÉELLE de la cible du `call` (`E8 rel32`)

* `DSLFormulas$$ConfigVar` a **cinq** surcharges ; les deux `GetDynamicStatModificationAmount`
  visent `180ea83e0` = `ConfigVar(abilityType, unit, variableType)` — donc le **premier**
  argument `0x409` est un `TriggeredAbilityType`, pas un `AbilityVariableType`, et le
  `8`/`9` final est la variable. Lire `ConfigVar(8, …)` comme dans #952 aurait inversé les deux.
* `DSLBehaviors$$If` a trois surcharges ; celle visée prend `(IAbilityTrigger, ifBehaviour,
  elseBehaviour)`.
* `DSLSelectors$$PickRandomly` a deux surcharges ; celle visée prend `amount : System.Int32`.
* `BaseEffect$$AddSubEffect` a deux surcharges ; celle visée est **sans** `EffectBuilder`
  (`effect, target, effectType, turns`).
* Les deux `AbilityOrEffect$$op_Implicit` des `TriggeringAbilityIs` sont lus **aux octets** :
  `BA 01 04 00 00` (`mov edx, 0x401`) à `SummaryExecutionAbility$$CreateTrigger+0x11c`, et
  `BA 38 04 00 00` (`mov edx, 0x438`) à `PossessionAbility$$CreateTrigger+0x13a` — le décompilé
  ne montre qu'un `local_28` non initialisé.
