# #996 — Six no-op silencieuses : la RECONNAISSANCE d'abord (1010 / 1015 / 1053 / 1185 / 1133 / 1208)

**Build** : `rnca9r7q6c`. **Source** : `mcp__ghidra__decompile_function` sur les
`<X>Ability$$ExecuteBehaviour` — décompilé = vérité.

## Pourquoi cette fiche existe

`docs/rl/combat-ability-coverage.md` porte une colonne « catégorie » **qui n'est pas vérifiée** :
elle dérive du `damageProfile` de l'**ARME du porteur**, pas du behaviour de l'ability. Pour une
ability NON portée, l'`ExecuteBehaviour` n'est connu de personne, donc la catégorie ne *peut* pas
être dérivée (résidu `#491-r2`). **Mesuré ici : 4 des 6 catégories annoncées sont FAUSSES.**

| id | ability | catégorie ANNONCÉE | VERDICT | ce que le cast fait RÉELLEMENT |
|---|---|---|---|---|
| 1010 | `StormOfFlensingBlades` | EFFECT/BUFF | **FAUSSE** | **DEUX attaques NORMALES** du caster sur la cible, dans un `AtomicGroup(GroupType.StormOfFlensingBlades_Attacks)` |
| 1015 | `PrecisionShot` | DAMAGE(Energy) | **FAUSSE** | le cast **ne frappe pas** : `UseActiveAbility(Caster, Caster, 1012 PrecisionShot_Aim)` — patron 2-PHASES |
| 1053 | `DevoutPush` | EFFECT/BUFF | **FAUSSE** | attaque NORMALE sur la cible + `Kill(DeadUnits(Tiles(Target)))` + `PerformAIMovement(Caster, Direct(1))` |
| 1185 | `ForwardObservers` | EFFECT/BUFF | **CONFIRMÉE** | deux `AddEffect` (`1122 Markerlight` sur la cible, `1397 ForwardObservers_DamageReduction` sur l'Owner) |
| 1133 | `WarConstruct` | EFFECT/BUFF | **CONFIRMÉE** | deux `AddEffect` (`1302 IgnoreUsedAbilityInOverwatch` sur l'Owner, `1286 WarConstruct_CounterAttack` sur la cible), 1 round chacun |
| 1208 | `AetherStride` | SUMMON | **CONFIRMÉE, mais incomplète** | `Spawn` sur une `ThreeTileUnitSpawnShape` **&** `RemoveMachine(Caster)` : la MoW **disparaît**, remplacée par les unités spawnées |

## 1010 `StormOfFlensingBlades` — DOUBLE ATTAQUE NORMALE

`IdunBattleLogic.Entities.Abilities.Active.Loki.StormOfFlensingBladesAbility$$ExecuteBehaviour` :

```
AtomicGroup( groupType = 0x3e = GroupType.StormOfFlensingBlades_Attacks,
             delegate  = <>c__DisplayClass1_0$$<ExecuteBehaviour>b__0,
             null )
```

Le corps réel est dans le délégué
`...StormOfFlensingBladesAbility.u003Cu003Ec__DisplayClass1_0$$u003CExecuteBehaviouru003Eb__0`,
qui **boucle deux fois** (`i = 0, 1`) et, à chaque tour :

```
UseActiveAbility( subject     = Caster@+0x48,
                  targets     = Target@+0x60,
                  abilityType = DSLSelectors$$UnitNormalAttackType(Caster@+0x48),
                  source      = Nullable<AbilityOrEffect>(op_Implicit(this)),
                  <opts A>, <opts B{ +0x8 : (i == 0), +0xa : 1 }> )
puis AActiveAbility$$Execute(ability, ce behaviour)
```

Le **seul** champ qui varie entre les deux itérations est le flag `(i == 0)` de la 3ᵉ structure
d'options. Le champ voisin vaut `1` aux deux tours. Aucun `AttackWithAttackDamage`, aucun
`AddEffect` : la catégorie « EFFECT/BUFF » est fausse — c'est un cast qui FRAPPE, deux fois, avec
l'arme normale de l'unité (`UnitNormalAttackType`), donc résolue par distance.

## 1015 `PrecisionShot` — le cast NE FRAPPE PAS (2-PHASES)

`IdunBattleLogic.Entities.Abilities.Active.Loki.PrecisionShotAbility$$ExecuteBehaviour` :

```
AActiveAbility$$Execute(
   UseActiveAbility( subject     = Caster@+0x48,
                     targets     = Caster@+0x48,          # <-- le CASTER, pas la cible
                     abilityType = 0x3f4 = 1012 PrecisionShot_Aim,
                     source      = Nullable<AbilityOrEffect>(op_Implicit(this)),
                     <opts ZERO>, <opts ZERO> ) )
```

C'est **tout** le cast. La famille native est un triptyque :
`PrecisionShotAbility` (1015) → `PrecisionShot_AimAbility` (1012) → `PrecisionShot_AttackAbility`
(1013). Les artefacts qui matérialisent la 2ᵉ phase existent et sont nommés :
`IdunBattle.Entities.Effects.Loki.PrecisionShot_AimEffect$$BlockMovement`,
`...PrecisionShot_AimEffect$$CreateHandleTriggerAbilitiesInternal`,
`IdunBattle.AI.Playbook.Loki.PrecisionShot_AimPlaybook` / `PrecisionShot_AttackPlaybook`.
**« DAMAGE(Energy) » décrit l'arme du Deathmark, pas ce cast.**

## 1053 `DevoutPush` — ATTAQUE + MOUVEMENT, pas un buff

`IdunBattleLogic.Entities.Abilities.Active.Loki.DevoutPushAbility$$ExecuteBehaviour` :

```
[1] atk  = UseActiveAbility( Caster@+0x48, Target@+0x60,
                             DSLSelectors$$UnitNormalAttackType(Caster@+0x48),
                             Nullable<AbilityOrEffect>(op_Implicit(this)), <opts ZERO>, <opts ZERO> )
[2] kill = DSLBehaviors$$Kill( Caster@+0x48,
                               DSLSelectors$$DeadUnits( DSLSelectors$$Tiles(Target@+0x60) ), null )
[3] mv   = DSLBehaviors$$PerformAIMovement( Caster@+0x48, DSLFormulas$$Direct(1), this+0xf0 )
AActiveAbility$$Execute( op_Addition( op_Addition([1], [2]), [3] ) )
```

Le nom « Push » induit en erreur : **rien ne pousse la cible**. Le caster attaque, on FINALISE la
mort des unités mortes présentes sur les tuiles de la cible (`Kill` = l'étape qui libère la case),
puis le caster **avance de 1** via `PerformAIMovement`. L'ordre `[2]` avant `[3]` est le point de
fidélité : sans le `Kill`, la case n'est pas libre au moment du mouvement.

`this+0xf0` est un champ de l'ability passé en 3ᵉ argument de `PerformAIMovement` (non résolu à ce
stade — à lire au `.ctor`).

## 1185 `ForwardObservers` — EFFECT/BUFF **CONFIRMÉE**

`IdunBattleLogic.Entities.Abilities.Active.Loki.ForwardObserversAbility$$ExecuteBehaviour` :

```
[1] AddEffect( 0x462 = 1122 EffectType.Markerlight, AbilityStateReference,
               source = @+0x30, targets = Target@+0x60,
               DSLFormulas$$TurnsFromRounds( GetNumberConstant(0x45 = nrOfRounds) ) )
[2] AddEffect( 0x575 = 1397 EffectType.ForwardObservers_DamageReduction, AbilityStateReference,
               source = @+0x30, targets = @+0x30,
               DSLFormulas$$TurnsFromRounds( GetNumberConstant(0x77 = nrOfRounds_2) ) )
AActiveAbility$$Execute( op_Addition([1], [2]) )
```

Deux durées DISTINCTES (`nrOfRounds` et `nrOfRounds_2`) — les confondre serait le premier écart.
Artefact d'effet nommé : `IdunBattle.Entities.Effects.Loki.ForwardObservers_DamageReductionEffect$$CreateEffectDamageMalusForDefense`.

## 1133 `WarConstruct` — EFFECT/BUFF **CONFIRMÉE**

`IdunBattleLogic.Entities.Abilities.Active.Loki.WarConstructAbility$$ExecuteBehaviour` :

```
[1] AddEffect( 0x516 = 1302 EffectType.IgnoreUsedAbilityInOverwatch, AbilityStateReference,
               @+0x30, DSLFormulas$$TurnsFromRounds(1) )
[2] AddEffect( 0x506 = 1286 EffectType.WarConstruct_CounterAttack, AbilityStateReference,
               Target@+0x60, DSLFormulas$$TurnsFromRounds(1) )
AActiveAbility$$Execute( op_Addition([2], [1]) )
```

Les DEUX durées sont le **littéral 1** (aucune constante de config). L'effet de contre-attaque a
tout son appareil natif nommé :
`IdunBattle.Entities.Effects.Loki.WarConstruct_CounterAttackEffect$$GetCounterAttackBehaviour` /
`$$GetCounterAttackTrigger` / `$$GetCounterAttackCondition` / `$$GetDamage` / `$$CreateActiveCondition`.

## 1208 `AetherStride` — SUMMON confirmée, mais le caster DISPARAÎT

`IdunBattleLogic.Entities.Abilities.Active.Loki.AetherStrideAbility$$ExecuteBehaviour` :

```
opts = SpawnUnitOptions$$WithStatsFromConfig( config@0x60, abilityType, 0, 0 )

[a] AddTrait( targets = @+0x68, 0x418 = 1048 UnitTrait.Stationary, null )
[b] If( DSLTriggers$$ActorHasTriggeredAbility(@+0x30, 0x5d8 = 1496 TriggeredAbilityType.CabalOfSorcerers),
        AddTriggeredAbility( @+0x68, 0x5d8, DSLSelectors$$AbilityState(@+0x30, op_Implicit(abilityType)) ),
        null )
[c] If( DSLFormulas$$Count( UnitsWithTrait( AdjacentFriends(@+0x68, true, 3),
                                            0x3ea = 1002 UnitTrait.Psyker, 3 ) ),
        PerformAIAttack( @+0x68, null, formulas@+0x18, null, null ),
        null )
opts.Behaviour(+0x18) = op_Addition( op_BitwiseAnd([a], [b]), [c] )
opts+0x50 = UnitExtensions$$GetQuestUnitId(...) ; opts+0x60 = 1

[d] spawn = DSLBehaviors$$Spawn( Caster@+0x48,
                                 DSLSelectors$$ThreeTileUnitSpawnShape(Target@+0x60),
                                 AbilityConfiguration$$GetStringConstant(config@0x60, 0),
                                 opts )
[e] rm    = DSLBehaviors$$RemoveMachine( Caster@+0x48 )
AActiveAbility$$Execute( op_BitwiseAnd([e], [d]) )
```

Le sélecteur `@+0x68` est celui des unités SPAWNÉES (il ne peut pas être le caster : `AddTrait`
`Stationary` et `PerformAIAttack` s'appliquent aux nouvelles unités, cf. `AdjacentFriends(@+0x68)`
lu par le playbook `AetherStridePlaybook$$HasAdjacentFriendlyPsyker`). Le port devra le confirmer
sur la structure du contexte DSL avant d'écrire quoi que ce soit.

**La MoW est retirée du plateau** (`RemoveMachine(Caster)`) : « SUMMON » est vrai mais sous-décrit
— c'est une TRANSFORMATION. Un port qui n'émettrait que le `Spawn` laisserait Z'Kar sur le board.

## Porteurs et chemin d'arrivée en bataille

Recensement `unit_map.py find --ability <NOM>` (⚠ **par NOM, pas par id** : les six rendent
`0 unités` interrogées par ordinal, et ce zéro n'est PAS une preuve de mort — c'est un défaut
d'interrogation). Croisé avec `rl_duel.py build --list-pool`.

| id | porteurs | kinds | chemin |
|---|---|---|---|
| 1010 | `necroNpc2FlayedOne`, `necroNpc2TutFlayedOne`, `necroNpc2TutFlayedOneFTUEtest` | N | **greffe** sur une unité du pool (`case-92` §5bis) |
| 1015 | `necroNpc3Deathmark` (npc), `necroSmnDeathmark` (**summon**) | NS | summon via son summoner, ou greffe |
| 1053 | `templNpc1Initiate` (npc), `templInitiate` (**summon**) | NS | summon via son summoner, ou greffe |
| 1185 | `tauNpc5StealthSuit` (npc), `tauSmnStealthSuit` (**summon**) | NS | summon via son summoner, ou greffe |
| 1133 | `eldarNpc4Wraithguard`, `eldarNpc4WraithguardSurv` | N | **greffe** |
| 1208 | `thousDaemonPrince` « Z'Kar » (**lineup MoW**), `thousNpcMowDaemonPrince` | LN | MoW **hors** des 8 MoW spawnables du pool -> **injection catalogue** (`case-92` §6) |

Aucune des six n'est « non confrontable ». Le pool courant ne contient pas `thousDaemonPrince` ;
absent du pool != non confrontable.

## Ce que cette fiche ne tranche PAS

- La 3ᵉ structure d'options de `UseActiveAbility` (1010) : quel champ porte le flag `(i == 0)`.
- `this+0xf0` de `DevoutPush` (3ᵉ argument de `PerformAIMovement`).
- Le sélecteur `@+0x30` de `ForwardObservers` / `WarConstruct` (Owner ? Actor ?) — à établir sur
  la structure du contexte DSL, pas au flair.
- `@+0x68` d'`AetherStride` (présumé « unités spawnées »), et `GetStringConstant(config, 0)`
  (l'`unitId` spawné).
- Les masques `TARGETING_OPTIONS` et les littéraux `ABILITY_ATTACK_TYPE` des six (lus au `.ctor`,
  ability par ability).
