# #965 — `WhisperingWeb` (`eldarLhykhis`) et `RefusalToBeOutdone` (`emperExultant`)

Deux passifs de kit, classés **GAP-MENTION** par `docs/rl/passive-ability-coverage.md` et
confirmés non portés par `git grep` (aucune occurrence dans `scripts/python/engine`).

Build de référence : `rnca9r7q6c` (hash du jeu installé == hash de `data/symbols/`, vérifié).

## 1. Recensement — par la colonne « classe déclarante »

Base LUE dans `data/symbols/rnca9r7q6c/frida/classes.tsv`, jamais déduite du namespace.

| classe native | base (LUE) | slots | corps propres | fondu ICF |
|---|---|---|---|---|
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WhisperingWebAbility` | `IdunBattle.Entities.Abilities.BaseTriggeredAbility` | 96 | `CreateTrigger`, `CreateBehaviour` | non |
| `IdunBattle.Entities.Effects.Loki.WhisperingWebEffect` | `IdunBattle.Entities.Effects.ABondEffect` | 1152 | `.ctor`, `CreateEffectDamageBonusForAttack` | **oui** — `CreateTargetSelector` |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RefusalToBeOutdoneAbility` | `IdunBattle.Entities.Abilities.BaseTriggeredAbility` | 96 | `CreateTrigger`, `CreateBehaviour`, `RecordHitBehaviour`, `GetUpdateAttackStatBehaviour`, `GetUpdateCritStatBehaviour`, `GetCurrentExtraDmg`, `GetCurrentExtraCritDmg`, `GetSavedDamageForFriend`, `SetSavedDamageForFriend`, `GetLocalizationData`, `.cctor` | non |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RefusalToBeOutdone_ResetStatsAbility` | `IdunBattle.Entities.Abilities.BaseTriggeredAbility` | 96 | `CreateTrigger`, `CreateBehaviour` | non |

**Le namespace `...Abilities.Triggered.Loki.` est confirmé par la base** : les quatre abilities
dérivent de `BaseTriggeredAbility` ⇒ elles entrent dans `ABILITY_TRIGGERS`, **jamais** dans
`ABILITY_CLASSES`. Corollaire : **ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` ne sont dus**
(ces registres ne concernent que les actives).

`WhisperingWebEffect$$CreateTargetSelector` est le corps **dédupliqué par ICF** que ~250 classes
partagent (`return <DSLSelectors+0x30>` = `Owner`) : il est déjà identifié comme tel par
`case-389-ramming-speed-combat.md`, `case-919-icon-of-obstinacy.md`, `case-932-deathwing.md`,
`case-952-hunters-beyond-death-et-galvanic-field.md`. Ce n'est **pas** un corps propre à
`WhisperingWebEffect` ; le nom ghidra désigne un propriétaire arbitraire.

### Ids — LUS, jamais appariés par nom seul

| nom | enum | ordinal |
|---|---|---|
| `WhisperingWeb` | `TriggeredAbilityType` | 1554 |
| `WhisperingWeb` | `EffectType` | 1579 (`0x62b`) |
| `RefusalToBeOutdone` | `TriggeredAbilityType` | 1441 |
| `RefusalToBeOutdone_ExtraDamage` | `EffectType` | 1430 (`0x596`) |
| `RefusalToBeOutdone_ExtraCritDamage` | `EffectType` | 1511 (`0x5e7`) |

⚠ **`RefusalToBeOutdone_ResetStats` n'a AUCUN ordinal `TriggeredAbilityType`** — vérifié dans
l'enum natif (`data/symbols/rnca9r7q6c/frida/enums.tsv` ne porte que `1441` et `1554` pour ces
deux familles), et `gameconfig` ne donne qu'**un** passif à `emperExultant`
(`passiveAbilities = ['RefusalToBeOutdone']`). La classe de reset est donc une **sous-ability sans
id propre**, montée par la principale — cf. §4.

## 2. Le critère d'émetteur — face à trigger par face à trigger

| face | événement natif | émetteur côté port |
|---|---|---|
| `WhisperingWebAbility$$CreateTrigger` | `EventTriggerType.NormalAttack` (`0x26` = 38) | **OUI** — `engine/runner/operations/triggers/dispatch/attack.py` |
| `RefusalToBeOutdoneAbility$$CreateTrigger` branche A | `EventTriggerType.AttackHit` (`0x8`) | **OUI** — `dispatch/attack.py` (deux sites) |
| `RefusalToBeOutdoneAbility$$CreateTrigger` branche B | `EventTriggerType.UnitTransformed` (`0x4b` = 75) | **NON** |
| `RefusalToBeOutdone_ResetStatsAbility$$CreateTrigger` branche A | `EventTriggerType.TurnEnd` (`0x17` = 23) | **OUI** — `dispatch/turn.py` |
| `RefusalToBeOutdone_ResetStatsAbility$$CreateTrigger` branche B | `EventTriggerType.NormalAttack` (`0x26`) | **OUI** |

⚠ **`UnitTransformed` (75) n'a AUCUN émetteur côté port** — balayage de `scripts/python` et
`frida` : le nom n'apparaît que dans les deux **mirrors d'enum**
(`engine/dsl/event_trigger_type.py`, `frida/hooks/data/event-trigger-type-names.ts`), jamais dans
un site d'émission. Aucun trigger porté ne s'y abonne non plus. C'est un **vecteur mort côté
port**, et il le reste après cette tranche : la branche B est donc portée **structurellement**
(l'arbre la contient, fidèle au natif) mais **jamais évaluée**. Ce qu'elle ferait — un simple
REFRESH des deux stat modifiers — est de toute façon refait par la branche A à chaque coup
enregistré, donc l'absence d'émetteur **ne rend pas le passif faux**, seulement en retard d'un
refresh dans le régime `UnitTransformed`. Résidu `#965-r1`.

## 3. `WhisperingWeb` — RE

### `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WhisperingWebAbility$$CreateTrigger`

```
On(EventTriggerType.NormalAttack = 0x26, ownerNeedsToBeAlive = 1)
  & IsRangedAttack
  & get_OwnerIsCaster
  & AreEnemies(Target@<DSLSelectors+0x60>, Caster@<DSLSelectors+0x48>)
```

### `...WhisperingWebAbility$$CreateBehaviour`

```
sel = OwnerOfEffect( EffectsFromUnitSource(Owner@<DSLSelectors+0x30>, EffectType.WhisperingWeb) )
    RemoveEffect(sel, Nullable(EffectType.WhisperingWeb), null)
  + AddBondEffect(EffectType.WhisperingWeb, AbilityStateReference,
                  source  = Caster@<DSLSelectors+0x48>,
                  targets = Target@<DSLSelectors+0x60>,
                  bondWith= Caster@<DSLSelectors+0x48>,
                  turns   = default)
```

Le `RemoveEffect` en tête est le **mono-cible** : Lhykhis retire la toile de sa cible précédente
avant de la poser sur la nouvelle. Le sélecteur remonte de l'effet à **son porteur**
(`OwnerOfEffect`), la source étant Lhykhis lui-même.

### `IdunBattle.Entities.Effects.Loki.WhisperingWebEffect$$CreateEffectDamageBonusForAttack`

```
trigger = get_OwnerIsTarget
        & ( AreFriends(Caster@<DSLSelectors+0x48>, EffectSource(<DSLSelectors+0x38>))
            & IsHero(Caster@<DSLSelectors+0x48>) )
amount  = ConfigVar(AbilityVariableType.extraDmg = 8) * CurrentHitIndex()
return EffectBonus.ForAddition(trigger, amount)
```

`gameconfig` confirme l'unicité de la variable : `WhisperingWeb.variables` ne contient que
`extraDmg` (65 niveaux, `variablesAffectedByRarityBonus = ['extraDmg']`).

⚠ **Le montant CROÎT AVEC L'INDEX DU COUP** (`CurrentHitIndex`), il n'est pas plat : le premier
coup d'une salve ne reçoit pas le même bonus que le cinquième. Un port qui appliquerait
`extraDmg` à plat divergerait sur toute unité multi-coups — c'est l'étage à mesurer en priorité.

## 4. `RefusalToBeOutdone` — RE

### `...RefusalToBeOutdoneAbility$$CreateTrigger`

```
A = On(EventTriggerType.AttackHit = 0x8, ownerNeedsToBeAlive = 1)
  & <DSLTriggers+0x28>                                     /* = IsTurnOf(Owner) */
  & AreFriends(Caster@<DSLSelectors+0x48>, Owner@<DSLSelectors+0x30>)
  & AreEnemies(Owner@<DSLSelectors+0x30>, Target@<DSLSelectors+0x60>)
  & HasTrait(Caster@<DSLSelectors+0x48>, UnitTrait.Hero = 0x10)
  & AmountIsGreaterThanZero(CurrentDamage())
  & op_LogicalNot( DamageProfileIs(0xd) )
  & IsAdjacent(Target@<DSLSelectors+0x60>, Owner@<DSLSelectors+0x30>, 2)
B = On(EventTriggerType.UnitTransformed = 0x4b, ownerNeedsToBeAlive = 1) & get_OwnerIsTarget
return A | B
```

`<DSLTriggers+0x28>` = **`IsTurnOf(Owner)`** — identification établie par #366-r1
(`case-366-r1-fire-and-reposition-reduce-dmg.md` §2), qui corrige le nommage antérieur erroné
`get_OwnerIsActor`.

### `...RefusalToBeOutdoneAbility$$CreateBehaviour(abilityState, triggerType)`

```
if triggerType == EventTriggerType.AttackHit:
    return RecordHitBehaviour(abilityState)
return If( AmountIsGreaterThanZero(GetCurrentExtraCritDmg()), GetUpdateCritStatBehaviour() )
     + If( AmountIsGreaterThanZero(GetCurrentExtraDmg()),     GetUpdateAttackStatBehaviour() )
```

Le second bras n'est atteint que par la branche B du trigger — donc **jamais côté port** (§2).

### `...RefusalToBeOutdoneAbility$$RecordHitBehaviour(abilityState)`

```
cur   = CurrentDamage()
saved = GetPersistentData(AbilityOrEffect, Owner@<DSLSelectors+0x30>,
                          EntityId(Caster@<DSLSelectors+0x48>))
cnt   = GetPersistentData(AbilityOrEffect, Owner@<DSLSelectors+0x30>, <cle statique du .cctor>)

return If( AmountIsZero(saved) & HasTrait(Caster@<DSLSelectors+0x48>, UnitTrait.Chaos = 0x7ea),
             SetPersistentData(AbilityOrEffect, Owner, <cle statique>,
                               Sum(cnt, <DSLFormulas+0x20>))
           + GetUpdateCritStatBehaviour() )
     + If( AmountIsGreater(cur, saved),
             SetPersistentData(AbilityOrEffect, Owner, EntityId(Caster), cur)
           + GetUpdateAttackStatBehaviour() )
```

`<DSLFormulas+0x20>` = `Direct(1)` — le `.ctor` de `DSLFormulas` alloue `+0x18`=0, `+0x20`=1,
`+0x28`=2, `+0x30`=100, `+0x38`=-1 (déjà établi, cf. `abilities/behaviours/persistent_data.py`).

Le `.cctor` (`...RefusalToBeOutdoneAbility$$.cctor`) écrit une **chaîne statique** dans le champ
de classe `+0xb8` : c'est la clé du **compteur d'amis Chaos**, distincte des clés `EntityId(ami)`.

Deux accumulateurs, donc, sur le même sac `PersistentData` du porteur :
* une clé **par ami** portant le **MAXIMUM** de ses dégâts du tour (`AmountIsGreater`) — l'*Outrage* ;
* **une** clé compteur, incrémentée à la **PREMIÈRE** contribution de chaque ami **Chaos**
  (`AmountIsZero(saved)` est la garde de primo-contribution).

### Les deux formules

```
GetCurrentExtraDmg(abilityState, dsl, config) =
    PercentageOf( GetAllPersistentDataCombined(AbilityOrEffect, Owner@<DSLSelectors+0x30>,
                                               excludedKeys = [ <cle statique> ]),
                  config.GetVariableForLevel(AbilityVariableType.extraDmgPct = 0xa), 0 )

GetCurrentExtraCritDmg(abilityState, dsl, config) =
    Multiply( GetPersistentData(AbilityOrEffect, Owner@<DSLSelectors+0x30>, <cle statique>),
              Get( config.GetVariableForLevel(AbilityVariableType.extraCritDmg = 0x42) ) )
```

⚠ **L'exclusion de la clé compteur est LOAD-BEARING** : sans elle, le compteur d'amis Chaos serait
sommé dans l'Outrage et gonflerait le bonus de Damage. C'est le rôle du tableau `excludedKeys`
à un élément.

### Les deux poseurs de stat

```
GetUpdateAttackStatBehaviour = AddOrUpdateStaticStatModifierEffect(
        Owner@<DSLSelectors+0x30>, EffectType.RefusalToBeOutdone_ExtraDamage = 0x596,
        StatType.Attack = 0, GetCurrentExtraDmg(), null, false)

GetUpdateCritStatBehaviour   = AddOrUpdateStaticStatModifierEffect(
        Owner@<DSLSelectors+0x30>, EffectType.RefusalToBeOutdone_ExtraCritDamage = 0x5e7,
        StatType.CriticalDamage = 0xa, GetCurrentExtraCritDmg(), null, false)
```

### `...RefusalToBeOutdone_ResetStatsAbility`

```
CreateTrigger =
    ( On(EventTriggerType.TurnEnd = 0x17, ownerNeedsToBeAlive = 1) & <DSLTriggers+0x28> )
  | ( On(EventTriggerType.NormalAttack = 0x26, ownerNeedsToBeAlive = 1)
      & get_OwnerIsCaster & <DSLTriggers+0x28> )

CreateBehaviour =
    ClearAllPersistentData(AbilityOrEffect, Owner@<DSLSelectors+0x30>)
  + ( RemoveEffect(Owner@<DSLSelectors+0x30>, Nullable(EffectType.RefusalToBeOutdone_ExtraDamage))
    + RemoveEffect(Owner@<DSLSelectors+0x30>, Nullable(EffectType.RefusalToBeOutdone_ExtraCritDamage)) )
```

Ce qui mirrore exactement l'i2 : « At the end of his turn or after Laviscus performs a normal
attack, his *Outrage* resets. »

## 5. Nœud DSL manquant

Inventaire des primitives citées par les deux arbres, croisé contre `scripts/python/engine` :
**toutes existent sauf une**.

| nœud natif | port |
|---|---|
| `IdunBattleLogic.Entities.DSLFormulas$$GetAllPersistentDataCombined` | **ABSENT** — à porter |

Ce recensement s'est révélé **incomplet d'un nœud** à l'écriture, et c'est instructif :
`AddOrUpdateStaticStatModifierEffect` **apparaissait** dans `git grep` (9 occurrences) mais
seulement en **prose** — la classe portée est `AddStaticStatModifierEffect`, sans le `OrUpdate`.
Un recensement par `grep` de NOM compte les mentions, pas les définitions.

| nœud natif | port |
|---|---|
| `IdunBattleLogic.Entities.DSLFormulas$$GetAllPersistentDataCombined` | **ABSENT** — porté par cette tranche |
| `IdunBattleLogic.Entities.DSLBehaviors$$AddOrUpdateStaticStatModifierEffect` | **ABSENT** — porté par cette tranche |

Tout le reste (`GetPersistentData`, `SetPersistentData`, `ClearAllPersistentData`,
`AmountIsGreater`, `AmountIsZero`, `AmountIsGreaterThanZero`, `PercentageOf`, `Sum`, `Multiply`,
`EntityId`, `CurrentDamage`, `CurrentHitIndex`, `IsAdjacent`, `AreFriends`, `AreEnemies`,
`IsHero`, `HasTrait`, `DamageProfileIs`, `IsTurnOf`, `EffectSource`, `EffectsFromUnitSource`,
`OwnerOfEffect`, `AddBondEffect`, `RemoveEffect`, `ConfigVar`) était déjà porté.

### Les deux nœuds neufs, et ce que leur lecture a corrigé

**`GetAllPersistentDataCombined$$SumAbilityData`** est une **SOMME** des valeurs **entières**
rangées sous l'`abilityId`, qui **saute** toute valeur d'un autre type (le natif teste la classe de
l'objet boxé) et **exclut** les clés listées par l'appelant (`String.op_Equality`). Un
`excludedKeys` nul n'exclut rien.

**`AddOrUpdateStaticStatModifierEffect`** n'est **pas** un `Add` inconditionnel :

```
If( op_LogicalNot( AmountIsEqual(amount, CurrentStatModifierAmountFormula(targets, effectType, statType)) ),
    RemoveEffect(targets, Nullable(effectType)) & AddStaticStatModifierEffect(targets, ...) )
```

C'est **load-bearing dans les deux sens**. (a) Sans le remove-puis-add, `AddStaticStatModifierEffect`
seul est un **no-op** sur effet déjà présent (`AddEffectOperation` rend `None`) — la stat resterait
figée à la première valeur, donc l'Outrage ne monterait jamais. (b) Sans la garde d'idempotence, on
détruirait et recréerait l'entité-effet à chaque coup, même à montant inchangé.

⚠ Le ctor du nœud conditionnel est étiqueté `IdunBattle.Entities.Behaviours.PerformAIMovementBehaviour$$.ctor`
par ghidra : corps **dédupliqué par ICF** (ctor à trois champs `cond`/`then`/`else`), le nom désigne
un propriétaire arbitraire. La nature `If` est établie par la **forme de l'appel**, pas par le nom.

## 6. Co-injection des deux porteurs — l'hypothèse TIENT

Aucun des deux n'est au pool (`rl_duel build --list-pool`, rank 17, 97 unités) : les deux sont des
`lineup`. Ils s'injectent donc, et `catalog_inject.write_augmented_seed_bc` prend bien une **LISTE**
d'`unitIds` :

```
write_augmented_seed_bc(out, ['eldarLhykhis', 'emperExultant'])
  -> UNITS AJOUTEES   ['eldarLhykhis', 'emperExultant']
  -> CONFIGS AJOUTEES ['EmpyricAmbush', 'WhisperingWeb', 'EuphoricStrikes', 'RefusalToBeOutdone']
```

**Deux porteurs de deux factions différentes (Aeldari, EmperorsChildren) entrent dans un seul seed,
avec leurs quatre configs d'ability (2 actives + 2 passives), en un seul appel.** La faction n'est
pas un facteur : l'augmentation porte sur le bloc `Units` et sur `BC.Abilities`, ni l'un ni l'autre
n'étant partitionné par faction. Le montage est donc payé **une fois pour deux items**.

## 7. Ce que la tranche livre, par item

| item | verdict | ce qui est porté |
|---|---|---|
| `RefusalToBeOutdone` (1441) | **PORTÉ** (hors branche morte) | les deux classes natives, les trois disjoints de trigger, `RecordHitBehaviour`, les deux formules, les deux poseurs de stat, le reset |
| `WhisperingWeb` (1554) | **PORTÉ PARTIELLEMENT** | l'ability (pose + retrait mono-cible). La magnitude de l'effet 1579 est le résidu `#965-r2` |

Résidus ouverts : **`#965-r1`** (le vecteur `UnitTransformed` sans émetteur) et **`#965-r2`**
(le threading de `hit_index` dans le pipeline de dégât).
