# case-366-r1 — `1115 InescapableAccuracy_extraCritChance` : le ctor fondu ne fait PAS une classe

> Extrait du gisement des 96 (`case-366-gisement-96-effets.md` §3.3, groupe G3).
> Sa fiche d'inventaire annonçait « classe propre, **ctor fondu avec 1116** ». Le ctor est bien
> fondu — pour les **trois** ids, pas deux — et les classes sont bien **trois**. C'est le slot
> `Il2CppClass*` qui le dit, jamais le nom du ctor.

## 1. Identité — TROIS classes, UN corps de ctor

`IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_141`,
`…b__14_142` et `…b__14_143` allouent chacune depuis un **`Il2CppClass*` DIFFÉRENT**, puis appellent
le **MÊME** corps de `$$.ctor`. IL2CPP déduplique les corps bit-identiques : ici les trois classes
dérivent de `BaseEffect` avec la **même constante d'ability**, donc leurs trois ctors compilent au
même code et un seul survit dans la table — celui que Ghidra nomme
`…InescapableAccuracy_ExtraCritDamageEffect$$.ctor`. **Le nom du ctor ne dit rien de l'identité de
classe** (51 noms de ctor couvrent plusieurs classes dans ce binaire).

Les trois tables de méthodes le confirment, et se lisent d'un bloc :

| table | méthodes | classe |
|---|---|---|
| 1 | `.ctor`, `CreateActiveCondition`, `ActiveCondition`, `CreateTargetSelector`, `CreateBlockHitReductionTrigger` | `…_OverridHitsEffect` = **1117** |
| 2 | `.ctor`, `CreateActiveCondition`, `CreateTargetSelector`, **`CreateCritChanceBonus`** | `…_ExtraCritChanceEffect` = **1115** |
| 3 | `.ctor`, `CreateActiveCondition`, `CreateTargetSelector`, `CreateCritDamageBonus` | `…_ExtraCritDamageEffect` = **1116** |

`CreateActiveCondition` et `CreateTargetSelector` sont eux aussi des corps **dédupliqués** (une
seule adresse, référencée par les **trois** tables) — d'où leurs noms Ghidra empruntés à des classes
arbitraires (`…_ExtraCritDamageEffect$$CreateActiveCondition`,
`IdunBattle.Entities.Effects.Loki.WhisperingWebEffect$$CreateTargetSelector`). Le second rend
`<DSLSelectors+0x30>` = **Owner**.

**Ce port ne couvre QUE 1115.** `1116` (canal `CreateCritDamageBonus`, `ConfigVar(0x42)`) et `1117`
(canal `BaseEffect$$BlockHitsReduction`) restent non portés : ce sont des canaux **différents**, les
inscrire par analogie serait un port spéculatif.

## 2. Source de config — la TRIGGERED 1115, pas l'EffectType 1115

Corps de ctor partagé (bytes relus, pas déduits) :

```
mov edx, 0x45b                                        ; 1115
call IdunBattle.Core.AbilityOrEffect$$op_Implicit      ; surcharge TRIGGERED
call IdunBattle.Entities.Effects.BaseEffect$$.ctor(this, abilityOrEffect,
                                                   hasAutomaticActivation: 1)
```

La surcharge d'`op_Implicit` est tranchée **par son adresse** (les quatre portent le même nom) :
c'est celle dont le corps appelle `IdunBattle.Core.AbilityOrEffect$$set_TriggeredAbility`.

`0x45b = 1115` vaut dans **deux** enums (`enums.tsv`) : `EffectType.InescapableAccuracy_extraCritChance`
**et** `TriggeredAbilityType.InescapableAccuracy`. C'est le second qui est lu — et c'est la seule
lecture cohérente : le corps étant **partagé** par 1116 et 1117, l'autre lecture leur ferait lire la
config de l'effet 1115. ⇒ config = `abilities.InescapableAccuracy`, indexée par le niveau d'ability
**PASSIVE** du porteur (`GC.unit("eldarMauganRa").passiveAbilities`).

## 3. La POSE — les trois d'un bloc, permanents

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.InescapableAccuracyAbility$$CreateBehaviour` :

```
  AddEffect( 0x45b = 1115, <abilityStateReference>, targets = <DSLSelectors+0x30> = Owner, turns = NULL )
+ AddEffect( 0x45c = 1116, <idem> )
+ AddEffect( 0x45d = 1117, <idem> )
    (fusionnés par IdunBattle.DSL.AbilityBehaviour$$op_Addition)
```

`turns = NULL` ⇒ **PERMANENTS**. Ce qui les éteint est la CONDITION, pas une durée.

## 4. Les deux artefacts de 1115

### 4.1 CANAL — `CreateCritChanceBonus`, DEUX nœuds

```
EffectBonus.ForAddition( get_OwnerIsCaster & IsRangedAttack,
                         ConfigVar(0x41 = extraCritChance, GetAbilityState(effect), config@+0x60) )
```

C'est le canal ouvert par `1222 WarHowl_ExtraDamage_Unstoppable` :
`IdunBattle.Core.Services.DamagePrediction$$GetCritChanceBonusFromEffects` bâtit son
`AbilityEntities` (caster = owner = l'attaquant, target = le défenseur), évalue le trigger de chaque
`EffectBonus` (`IdunBattle.Entities.Effects.BaseEffect$$CritChanceBonus`, cache à `entities+0x3b0`)
et accumule `addition − subtraction` ; son consommateur unique est
`IdunBattle.Core.Services.DamagePrediction$$RollCritical` = `clamp(GetStat(9) + somme, 0, 100)`.

**N'HÉRITE RIEN DE SON VOISIN.** Là où `1222` porte **quatre** nœuds
(`get_OwnerIsCaster & IsMeleeAttack & IsNormalAttack & AmountIsGreaterThanZero(StatAmount(Caster,
CriticalChance))`), `1115` n'en porte que **deux** :

* le gate d'attaque est l'**INVERSE** — `IsRangedAttack`, surcharge **sans argument** (tranchée par
  la cible du `call`, `IdunBattleLogic.Entities.DSLTriggers$$IsRangedAttack` →
  `IdunBattle.Entities.Triggers.IsRangedAttackAbilityTrigger`) ;
* **pas** de `IsNormalAttack` ⇒ le bonus vaut **aussi** pour les attaques d'ABILITY à distance ;
* **pas** d'`AmountIsGreaterThanZero` ⇒ aucun gate sur `GetStat(9)` (cf. le résidu §7.1).

### 4.2 GATE — `CreateActiveCondition` = `NOT HasFlag(Owner, UnitFlag.Moved)`

```
op_LogicalNot( HasFlag( <DSLSelectors+0x30> = Owner, flag = 0 ) )
```

`IdunBattleLogic.Entities.DSLTriggers$$HasFlag` alloue un
`IdunBattle.Entities.Conditions.HasFlagAbilityTrigger(unit, flag, contains: 1)` dont le
`$$ShouldTrigger` est `IdunBattle.Entities.Components.UnitFlagsComponent$$Has(unit, flag)` ;
**`flag = 0` = `UnitFlag.Moved`**. ⇒ Maugan Ra qui a bougé ce tour ne bénéficie plus du bonus.
Même prédicat natif que `IdunBattle.Entities.Effects.Loki.CrushingStrikeEffect$$CreateActiveCondition`
(#98) et que le gate no-move de `HeavyWeapon_ExtraDmg` — **même store unique**, le
`UnitFlagsComponent`, donc les deux axes (DÉGÂT et CRIT) ne peuvent pas diverger.

Le port le rend **deux fois**, comme `ModifiedExoarmour_ExtraDmg` (case-322) rend son
`AmountIsGreaterThanZero(TilesMovedThisTurn)` : par `is_active` (la place NATIVE de la condition,
qui vaut pour tout consommateur d'`active_effects` — clé `has_moved` ajoutée à
`UnitEffectStateView`) et par le gate du canal (`att_ctx["has_moved"]`, posé au foyer unique
`runner/operations/damage.py::AttackDamageOperation._crit_params`).

### 4.3 Magnitude

`ConfigVar(0x41)` = `gameconfig.ability("InescapableAccuracy").variables["extraCritChance"][level]`
— 10 → 15 sur 65 niveaux, **15** au niveau normalisé 50. `extraCritChance` n'est **PAS** dans
`variablesAffectedByRarityBonus` (qui ne contient que `extraCritDmg`) ⇒ aucun scaling de rareté, et
`ability_var` applique cette règle config-driven toute seule. Le résidu #382 (« le multiplicateur
vient de la SOURCE, le port lit le PORTEUR ») est donc **doublement inerte** ici : la variable n'est
pas scalée, et l'effet est posé par le porteur sur lui-même (source == porteur).

## 5. Le criterion, et les bras qui le tranchent

> « Le port ajoute-t-il — **et refuse-t-il d'ajouter après un mouvement** — la contribution de 1115
> comme le natif ? », mesuré là où l'effet MORD : le dégât per-coup d'une salve **à distance**.

`probe_366_r1_inescapable_accuracy_crit_chance.py`, deux bras × (référence + mutation
adversariale). Le porteur est `eldarMauganRa` (HERO, **dans le pool** — vérifié
`rl_duel build --list-pool`), seul porteur `lineup` du passif ; les cinq autres entrées
d'`unit_map find --ability InescapableAccuracy` sont des variantes de BOSS npc.

Contraintes de montage, chacune payée par une mesure fausse évitée :

* **la salve doit être RANGED** — Maugan Ra a **deux** armes (`weapons[0]` mêlée 5 coups,
  `weapons[1]` `HeavyRound` 6 coups `Range` 3). Au CONTACT l'attaque normale bascule sur l'arme
  mêlée et `IsRangedAttack` se ferme : la géométrie impose `2 <= d <= 3` **avant et après** le pas ;
* **`--block-target 0,0`** — le canal BLOCK de la cible est celui que porte le jumeau NON PORTÉ
  `1117` (`CreateBlockHitReductionTrigger` → `BaseEffect$$BlockHitsReduction`). Sans cette
  neutralisation, un écart imputable à 1117 se lirait comme un écart de 1115 ;
* **ennemis sans `Overwatch`** (`necroWarden`, `necroOverlord`) — Maugan Ra porte lui-même
  `Overwatch`, et le montage déplace les deux camps ;
* **`--crit 50,700`** — `CritChance > 0` est obligatoire au bras de référence (cf. §7.1).

<!-- MESURES: à compléter -->

## 6. Ce qui n'est PAS couvert

* **`1116 InescapableAccuracy_extraCritDmg`** (canal `CreateCritDamageBonus`, `ConfigVar(0x42)`,
  même `CreateActiveCondition`) et **`1117 InescapableAccuracy_overrideHits`** (canal
  `BaseEffect$$BlockHitsReduction`, non porté côté moteur) : hors périmètre de cette tranche. La
  structure établie ici (identité, source de config, pose, active-condition) leur sert telle quelle.
* **La face PRÉDICTION** : `services/damage_prediction.py` n'appelle `crit_chance_bonus_from_effects`
  nulle part (`could_crit(ctx.crit_chance, …)` seul) — le +extraCritChance n'entre pas dans la
  prédiction de dégât. Gap **préexistant du canal** (case-366-r1 §6.4 de la fiche WarHowl), pas de
  ce port.
* **Le vecteur OVERWATCH** de Maugan Ra n'est pas exercé. Il passe par `damage_ops/normal.py` avec
  `_ranged = True`, donc `IsRangedAttack` s'y **ouvrirait** — mais l'`ActiveCondition` porte sur
  `UnitFlag.Moved` de l'OWNER, purgé au `StartTurnOperation` : non mesuré.
* **Le canal `create_effect_crit_chance_bonus_for_attack` ne balaie que les effets de l'ATTAQUANT**
  alors que le natif énumère les entités porteuses d'effets de tout l'état (même limite que
  `crit_damage_bonus_from_effects`). Sans conséquence pour 1115, dont le trigger commence par
  `get_OwnerIsCaster`.

## 7. Résidus NOMMÉS

### 7.1 `could_crit` du port inclut le bonus d'effet, le natif NON

`IdunBattle.Core.Services.DamageCalculations$$CouldCrit(attacker)` (décompilé) :

```
GetStat(attacker, 0x9) >= 1  AND  GetStat(attacker, 0xa) >= 1
```

— **la stat BRUTE, le bonus d'effet n'y entre pas**. Le port, lui, appelle
`could_crit(GetStat(9) + Σbonus, GetStat(10))` (`AttackDamageOperation._crit_params`). Sur un
porteur à `GetStat(9) == 0`, le natif ne tire donc **aucun** crit alors que le port en tirerait à
15 % — un tirage PRNG de plus, donc **tous** les coups suivants décalés.

C'est exactement ce que le gate `AmountIsGreaterThanZero` de `1222` masquait côté WarHowl. Ici le
natif ne l'écrit pas, donc **le résidu est nu**. Il est STRUCTUREL au port
(`services/damage_combat.py::could_crit` + son appelant, partagé par les trois vecteurs d'attaque),
pas propre à cette classe : le corriger demande de faire remonter `GetStat(9)` brute jusqu'à
`could_crit`. **NON CORRIGÉ ici**, et mesurable par le bras dédié du probe
(`--crit 0,700 --expect-diverge`).

### 7.2 Le niveau d'ability n'est propagé qu'en PASSIVE

`EffectsState.seed` propage `ability_level` (= `unitConfig.passiveAbilityLevel`), ce qui est
exactement ce que lit cette classe (`InescapableAccuracy` est une passive). Aucun repli
`active_ability_level` n'est nécessaire, contrairement aux 18 classes qui lisent une ability ACTIVE.
Rien à ouvrir.
