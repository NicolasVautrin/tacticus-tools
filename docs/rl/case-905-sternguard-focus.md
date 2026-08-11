# case-905 — `1228 SternguardFocus` : l'audit disait EFFECT/BUFF, le natif fait une ATTAQUE NORMALE

Porteurs : **`darkaSternguard`** (« Ramus », HERO `kind` lineup, DarkAngels) et
**`darkaBossSternguardLHE`** (npc). Kit gameconfig identique des deux côtés : deux armes
(`Melta` melee 1 coup / `Bolter` `Range 3` 1 coup), active `SternguardFocus`, passif
`SpecialIssueCombiMelta`.

## 1. L'arbre natif, tel que LU

`IdunBattleLogic.Entities.Abilities.Active.Loki.SternguardFocusAbility$$ExecuteBehaviour` —
mirror 1:1, terme à terme (slots de `IdunBattleLogic.Entities.DSLSelectors` du build
`rnca9r7q6c` : `+0x30 Owner`, `+0x48 Caster`, `+0x60 Target`, `+0x68 ActiveTarget/Subject` ;
slots du DSL : `ability+0x30` = le DSL, `dsl+0x78` = `DSLBehaviors`, `dsl+0x80` = `DSLFormulas`,
`dsl+0x88` = `DSLTriggers`, `dsl+0x90` = `DSLSelectors` — mapping RECOUPÉ sur
`...HailstrikeAbility$$ExecuteBehaviour`, déjà porté) :

```
cap    = DSLFormulas$$ConfigVar( abilityType  = 0x4cc = 1228 SternguardFocus,
                                 unit         = Owner@+0x30,
                                 variableType = 0x0d = maxDmg )
pct    = DSLFormulas$$ConfigVar( 0x4cc, Owner@+0x30, 0x4a = dmgPct )
amount = DSLFormulas$$PercentageOfAttackCappedAtMax( unit = Subject@+0x68,
                                                     statPart = 0x3 = Initial,
                                                     cap, pct, roundingRule = 0 = Default )
b1     = DSLBehaviors$$AddTemporaryAttackOverrideEffect( targets = Caster@+0x48, amount )
b2     = DSLBehaviors$$UseNormalAttack( caster = Caster@+0x48, target = Target@+0x60,
                                        parentAbility = Nullable(AbilityOrEffect(...)),
                                        triggerAbilityOrEffect = default, options = <ZÉROÉE> )
b3     = DSLBehaviors$$ResetTemporaryAttackOverrideEffect( targets = Caster@+0x48 )
AActiveAbility$$Execute( this, op_Addition(op_Addition(b1, b2), b3), entities )
```

Les trois helpers de `DSLBehaviors`/`DSLFormulas` sont des **composites sans nœud dédié** (corps
lus) :

* `$$AddTemporaryAttackOverrideEffect(targets, amount)` =
  `new AddStatOverrideEffectBehaviour(targets, effectType = 0x510 TemporaryStatOverride,
  source = null, amount, durée = null, flag = 1)`, `statType = 0 = StatType.ATTACK` ;
* `$$ResetTemporaryAttackOverrideEffect(targets)` = `RemoveEffect(targets, Nullable(0x510), 0)` ;
* `$$PercentageOfAttackCappedAtMax` = `Min(cap, PercentageOf(StatAmount(unit, ATTACK, statPart),
  pct, roundingRule))`.

**Quatre lectures qui ne se devinent pas.**

1. **`statPart = 3 = Initial`, pas `Current`.** `...ExemplarOfHateAbility$$GetAttackDamage` et
   `...MyWillBeDoneOverlordAbility$$CreateBehaviour` passent `0 = Current` ; ici le littéral est
   `3`, relu à l'identique dans `...SternguardFocusAbility$$GetOverrideAttackDamageAmount` (la
   face PRÉDICTION, dont le corps est la même chaîne `cap`/`pct`/`amount`). Conséquence : un buff
   d'`Attack` en cours **n'entre pas** dans le pourcentage.
2. **La surcharge de `ConfigVar` est `(ActiveAbilityType, unit, variableType)`** — attribuée par
   **XREFS ENTRANTES** (`list_xrefs` sur les cinq surcharges : `$$ExecuteBehaviour` et
   `$$GetOverrideAttackDamageAmount` appellent celle-là, jamais la `TriggeredAbilityType`), donc
   `0x4cc` est bien un `ActiveAbilityType`. Son corps est
   `new ConfigAmount(abilityType, abilitiesDatabase, unitSelector, variableType)` : le NIVEAU
   vient de l'UNITÉ (`Owner`), pas d'un `abilityState`.
3. **`UseNormalAttack`, pas `UseNormalAttackIfAble`** (xrefs entrantes également).
4. **Aucun `ExecuteAtomic`** : l'`op_Addition` part directement à `AActiveAbility$$Execute`.

## 2. La prémisse héritée était FAUSSE à moitié

L'audit classe `1228` en **EFFECT/BUFF**. L'effet `0x510 TemporaryStatOverride` existe bien, mais
il est **posé puis retiré dans le même cast** : son seul rôle est d'armer une **ATTAQUE NORMALE**,
dont le profil, le nombre de coups et la portée viennent de l'**ARME du caster**. La colonne
d'audit dérive du `damageProfile` de l'ability, et `1228` n'en a **aucun** au gameconfig
(`constants` = `{cooldownTurns: 3}` seul) — elle ne peut donc pas voir le volet DÉGÂT. C'est le
même angle mort que `1216 MartialExemplar`.

## 3. Le masque — forme PRESET-COPIE, lue au DÉSASSEMBLAGE

Le décompilé de `...SternguardFocusAbility$$.ctor` avait perdu les immédiats ; les octets, eux,
les portent :

```
mov  rax, [<classe IdunBattle.Core.Services.TargetingOptions>]
mov  rax, [rax + 0xB8]                  ; ses static_fields
movups xmm0/xmm1, [rax + 0x00 .. 0x3F]  ; les 0x40 octets du preset <statics>+0x00
xor  r9d, r9d ; mov r8d, 2 ; call AActiveAbility..ctor(this, &opts, 2, 0)
```

**Aucun `TargetingOptions..ctor` n'est appelé** : ce n'est donc PAS la surcharge « preset +
flags ». Le masque effectif est ce qu'`IdunBattle.Core.Services.TargetingOptions$$.cctor` écrit
dans ce preset :

| champ | valeur |
|---|---|
| `<statics>+0x00` `isSelfCasting` | 0 |
| `<statics>+0x08` `range` | copie de `<TargetingRange statics>+0x00` = `RANGE_ADJACENT_IF_MELEE_CASTER` |
| `<statics>+0x20` `forceMeleeTarget` | 2 = `RangedBool.IfRangedCaster` |
| `<statics>+0x28` `rules` | **0x4002** = `TargetMatchesDynamicRule` \| `TargetIsEnemy` |

`AbilityAttackType` = **2 = Others** (3ᵉ argument, `mov r8d, 2`).

⚠ Le preset `<statics>+0x00` porte le **même** masque `0x4002` que `<statics>+0x140` (celui de
`PlasmaCannon`/`Supercharge`) mais **ni le même `range`** (`TargetingRange+0x00` vs `+0x18`
`useRangeFromConfig`) **ni le même `forceMeleeTarget`** (2 vs 0) : les deux presets ne sont pas
interchangeables.

**Bit `0x2` `TargetMatchesDynamicRule` — délégué non lisible.** Aucun
`SternguardFocusAbility$$GetDynamicInvalidTargetReason` dans `frida/methods.tsv`, mais un corps
`xor eax,eax ; ret` est DÉDUPLIQUÉ par IL2CPP : l'absence ne prouve rien. Le port laisse la règle
au défaut `0` (permissif). Confirmé live : `abilityReason` rend `targetReason = 0x0` sur une cible
ennemie ordinaire aux distances 1, 2 et 3.

## 4. `SetsEndTurnFlags` — surchargé, valeur NON LUE, verdict MESURÉ (résidu `#905-r1`)

`...SternguardFocusAbility$$SetsEndTurnFlags` = `return <DSLTriggers>+0x60;`. Or les deux
constantes du cache sont `+0x40` (TRUE) et `+0x48` (FALSE), établies par
`IdunBattleLogic.Entities.DSLTriggers$$Direct(value)` (`value != 0 -> +0x40`, sinon `+0x48`) et
recoupées par le DÉFAUT `IdunBattle.Entities.Abilities.AActiveAbility$$SetsActiveAbilityUsedFlag`
(qui rend `+0x40`) et par `...WarHowlAbility$$SetsEndTurnFlags` (fold-winner des 14 overrides
« ne termine pas le tour », 30 refs, qui rend `+0x48`). **`+0x60` n'est ni l'un ni l'autre.**

`1228` est donc, avec `1106 WarHowl`, l'une des DEUX seules abilities du build à surcharger ce
virtual, et la SEULE dont la valeur ne soit pas une des deux constantes. La classe de `+0x60` est
sans champ (ctor partagé avec celui de `+0x40`, aucun argument), n'est rendue par **aucun**
accesseur de `DSLTriggers`, et n'est référencée que par le ctor de `DSLTriggers` et par un
`isinst` d'`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$GetEventTriggers` (où sa présence
exempte l'ability du log « aucun event trigger ») — donc **aucun nom**.

**Verdict pris par la MESURE** (`probe_905_sternguard_focus.py --case flags`, quatre régimes :
caster seul / allié DarkAngels adjacent / après mouvement / distances 1-2-3) : `hasAction` reste
`True` après le cast **et** l'attaque normale enchaînée MUTE, 4 fois sur 4.
**Témoin de discrimination** (`--case control`, même runner, même séquence) : `1150 PlasmaCannon`,
hors `NO_END_TURN_ABILITY_TYPES`, rend `hasAction = False` et son attaque enchaînée est REFUSÉE
(`mutated = False`). Sans ce témoin, la mesure ne dirait rien.

⇒ `1228` entre dans `NO_END_TURN_ABILITY_TYPES`, et reste HORS de
`NO_ABILITY_USED_FLAG_ABILITY_TYPES` (elle ne surcharge pas `SetsActiveAbilityUsedFlag` ; le
cooldown `constants.cooldownTurns = 3` rend ce flag-là inobservable au tour du cast).

## 5. Montage — porteur LINEUP par injection catalogue, et pourquoi PAS le npc

`darkaSternguard` est **hors du pool** (`rl_duel build --list-pool` : 5 DarkAngels, pas lui) →
**injection catalogue** (`catalog_inject.write_augmented_seed_bc`, `case-92` §6), puis
`initAndStart` sur ce seed BC augmenté. Le npc `darkaBossSternguardLHE` serait montable par
`--explicit-stats`, mais il porte **exactement le même kit** : le prendre n'apporterait aucune
mécanique de plus et mélangerait « port de l'ability » et « port des stats npc » (formule
`UnitProgression$$GetNpcStats`, voie distincte). Il n'est PAS joué — c'est une non-couverture
assumée, pas une impossibilité.

⚠ **Le premier montage ne discriminait pas, et c'était le TÉMOIN.** Avec `blackTerminator` en
face, le natif refusait `1228` — mais aussi **l'attaque normale 69** — avec
`targetReason = 0x20000000 TargetIsTargetable` : le trait `TeleportStrike` fait deep-striker
l'unité, qui n'est pas encore posée sur le plateau. Le refus n'avait rien à voir avec l'ability.
`blackObliterator` (sans ce trait) rend le montage confrontable.

## 6. Confront LIVE (MC1_67, seed 905905, rank 17)

La **DISTANCE** est le seul axe qui change le résultat observable sans changer l'arbre : elle
décide l'ARME (`Melta` à 1, `Bolter` à 2-3) **et** quelle branche du passif
`SpecialIssueCombiMelta` mord (`d == 1` extra-dmg, `d == 2` coup additionnel, `d == 3` `Pinned`).

| régime | live | port | verdict |
|---|---|---|---|
| d = 1 (`Melta`) | `Amount = [4435]`, ΔPV 4435 | `damage_total = 4435` | BIT-EXACT |
| d = 2 (`Bolter` + coup additionnel 1563) | `Amount = [2201, 2358]`, ΔPV 4559 | `total = 2201` + `additional_hits.total = 2358` = **4559** | BIT-EXACT |
| d = 3 (`Bolter`, + `Pinned` 1065 posé) | `Amount = [2201]`, ΔPV 2201 | `damage_total = 2201` | BIT-EXACT |
| override, branche CAP | `UnitStats_Attack_Override = 3989` | `min(3989, Attack) = 3989` | EXACT |
| override, branche POURCENTAGE (`Damage` du caster abaissé à 1200) | `= 1200` | `= 1200` | EXACT |
| retrait de l'override | tag `-2147483648` puis aucun `1296` résiduel | aucun `1296` sur le caster | NET-ZÉRO |

⚠ **`total` de l'`AttackDamageOperation` n'inclut PAS les coups additionnels.** Lire le seul
`total` à `d = 2` faisait croire à une divergence (`279` port contre `[279, 2358]` live dans le
régime `Damage = 1200`) alors que le port était juste : la décomposition par étage — rejouer
l'**attaque normale NUE**, sans jamais caster `1228` — l'a montré en une passe (`--case normal` :
port `total = 2682` + `additional_hits = 2358`, live `[2682, 2358]`). Le diagnostic de
`execute_behaviour` expose désormais les DEUX volets et leur somme (`damage_total`).

## 7. Ce qui n'est PAS couvert

* **L'axe `statPart = 3 Initial` vs `0 Current` n'est pas discriminé LIVE** : dans tous les
  régimes joués le caster n'a aucune modification d'`Attack`, donc les deux lectures coïncident.
  Le `3` est lu sur DEUX artefacts natifs indépendants ; l'étage 6 du test le discrimine
  **offline**, en posant une vraie modification (`change_stat`) sur l'état chargé et en vérifiant
  (a) que les deux lectures divergent alors, (b) que l'arbre porté prend `Initial`. Le lever
  live exigerait un `StatModifier` d'`Attack` sur une unité du camp JOUEUR : `--unit-modifier`
  ne s'applique qu'aux unités PRÉDÉFINIES du camp adverse (`SetupGameOperation$$AddPredefinedUnits`).
* **`darkaBossSternguardLHE`** n'est pas joué (§5).
* **`SetsActiveAbilityUsedFlag`** est inobservable au tour du cast (cooldown 3).
* **La classe de `<DSLTriggers>+0x60`** : résidu `#905-r1`.
