# #419-r1-tr14-r4-r2 — `InformWeapon` : les trois clés portées, sur les DEUX voies

**Résolu**, résidus `-r1`, `-r1-r1` et `-r1-r2` inclus. Build `rnca9r7q6c`, ghidra-mcp sur le
binaire installé, session Frida 1.

```powershell
python scripts/python/probe_419r1tr14r4r2_inform_weapon_tags.py                  # cast live x2
python scripts/python/probe_419r1tr14r4r2_inform_weapon_tags.py --contre-epreuve # 5 mutations, 0 runner
python -m pytest scripts/python/tests/engine/runner/test_419r1tr14r4r2_inform_weapon_tags_offline.py -q
# la voie ATTAQUE NORMALE (#419-r1-tr14-r4-r2-r1)
python scripts/python/probe_419r1tr14r4r2r1_normal_attack_inform_weapon.py                  # 4 porteurs live
python scripts/python/probe_419r1tr14r4r2r1_normal_attack_inform_weapon.py --contre-epreuve # 7 mutations, 0 runner
python -m pytest scripts/python/tests/engine/runner/test_419r1tr14r4r2r1_normal_attack_inform_weapon_offline.py -q
# les DEUX branches SPECIALES (#419-r1-tr14-r4-r2-r1-r1 et -r1-r2), SS7bis / SS7ter
python scripts/python/probe_419r1tr14r4r2r1r1_normal_attack_special_branches.py --volet 1   # FeederTendrils : Heal + Pinned
python scripts/python/probe_419r1tr14r4r2r1r1_normal_attack_special_branches.py --volet 2   # OptimizedGait : l'ANCRE, 3 bras
python scripts/python/probe_419r1tr14r4r2r1r1_normal_attack_special_branches.py --contre-epreuve  # 5 mutations, 0 runner
python -m pytest scripts/python/tests/engine/runner/test_419r1tr14r4r2r1r1_normal_attack_special_branches_offline.py -q
```

## 1. Le décompilé

`IdunBattleLogic.Entities.DSLBehaviors$$InformWeapon(damageProfileType, isMelee, useSpecial)`
construit un `Dictionary<TagKey,int>` puis l'emballe. Les trois clés sont des
`IdunBattle.Streams.TagKey`, **lues** dans `data/symbols/<CURRENT>/frida/enums.tsv` :

| clé | membre | valeur écrite | condition |
|---|---|---|---|
| `0x93` | `Attack_Weapon_DamageProfile` | `HasValue ? (int)value : -1` (`-1` **est** `DamageProfileType.None_`) | inconditionnelle |
| `0x92` | `Attack_Weapon_IsMelee` | le **2ᵉ** argument | inconditionnelle |
| `0x94` | `Attack_Weapon_Use_Special` | le **3ᵉ** argument | **seulement si non nul** (`if ((char)useSpecial != 0)`) |

La surcharge à deux arguments `$$InformWeapon(weapon: WeaponProfile, useSpecial)` ne fait que
dériver puis déléguer : `damageProfileType = Nullable(weapon->{+0x10})`,
`isMelee = IdunShared.Battle.WeaponProfile$$get_IsMelee(weapon)`.

## 2. La docstring du foyer se trompait sur QUATRE points, pas un

Le résidu parent n'en annonçait qu'un (l'interversion). `combat.py::InformWeapon` affirmait :

1. « → `ActivateEffectBehaviour` » — **FAUX**. `ActivateEffectBehaviour$$.ctor` n'a **aucune**
   surcharge prenant un `Dictionary` (ses deux ctors : `(ITargetsSelector)` et
   `(ITargetsSelector, EffectType)`). Preuve structurelle du vrai destinataire : `InformWeapon`
   et `DSLBehaviors$$Inform(Dictionary<TagKey,Int32>)` instancient le **MÊME `Il2CppClass*`**,
   par le même ctor à 3 arguments ⇒ c'est `IdunBattle.Entities.Behaviours.InformBehaviour`.
2. « `0x92` = damageProfile » — **FAUX**, `0x92` est `isMelee`.
3. « `0x93` = weaponId dérivé du profil → nom d'arme » — **FAUX** : c'est l'**ordinal du
   `DamageProfileType`**. Mesuré live : `0` pour `Physical`, `14` pour `Power`.
4. « via l'opération `0x2c` » — **FAUX**, il n'y a aucune Operation.
   `InformBehaviour$$Execute` itère le dictionnaire, évalue chaque `IAmountFormula` et remplit le
   dict de tags de sortie ; **aucune** mutation de `HealthComponent`/`StatsComponent`, **aucun**
   tirage. L'émission se fait par `IdunBattle.Operations.InformOperation$$Execute`, qui ne fait
   QUE dispatcher un pas `StepType.Info` (**29**).

⇒ « COMBAT-INERTE » restait **juste**, mais par un mécanisme **entièrement autre**. Et
« no-op » était faux : le canal est **STREAM**, donc directement OBSERVABLE — c'est même ce qui
a rendu la confrontation live possible. Lecture indépendante concordante :
`docs/rl/case-477r18r4-tagkey-sans-producteur.md` §2(a).

**Propagation, comptée** : **6** sites portaient l'affirmation fausse (plus que les cinq de #302
tr5) — `combat.py` (le foyer, les 4 erreurs), `loki/heavy_bolt_pistol.py`, `admec.py`,
`deathguard.py`, `case-419-r1-tr14-r4-face-combat-heavy-bolt-pistol.md`, `backlog.md`. Tous corrigés.

## 2bis. Les DEUX voies, et pourquoi la seconde est la plus fréquente

La surcharge à **trois** arguments a **6** xrefs nommées ; celle à **deux** en a **une seule** —
`ALoki_NormalAttackAbility$$ExecuteInformWeapon`, qui est elle-même appelée par **9**
`<X>_NormalAttackAbility`. La voie ATTAQUE NORMALE est donc la plus fréquente, et c'est la seule
où `isMelee` n'est **pas** un littéral (§5).

## 3. `isMelee` est un LITTÉRAL D'APPELANT, et il DIFFÈRE — c'est ce qui rend le port vérifiable

Les **6** xrefs de la surcharge à 3 arguments, lues une par une :

| porteur | `isMelee` | `useSpecial` | porté ? |
|---|---|---|---|
| `HeavyBoltPistolAbility$$CreateBehaviour` | **1** | 0 | oui |
| `FlailSwingAbility$$ExecuteBehaviour` | **1** | 0 | oui |
| `SentinelDirectivesAbility$$ExecuteBehaviour` | **0** | 0 | oui |
| `StranglethornCannonAbility$$ExecuteBehaviour` | 0 | 0 | non |
| `IncendiaryShellsAbility$$ExecuteBehaviour` | 0 | 0 | non |
| `OptimizedGait_TriggerAttackAbility$$CreateBehaviour` | **dynamique** | **`HasEffect(target, 0x4e2)`** | non |

Un port qui écrirait une constante passerait sur un seul porteur : d'où l'étage
anti-régime-dégénéré (les deux porteurs confrontés doivent **différer**).

## 4. La confrontation live (MC1_67, seed 41902)

| porteur | flux natif | port | verdict |
|---|---|---|---|
| `SentinelDirectives` | `{DamageProfile: 0, IsMelee: 0}` | idem | OK |
| `FlailSwing` | `{DamageProfile: 14, IsMelee: 1}` | idem | OK |

4/4 clés, **`Use_Special` absente des deux côtés 2/2** (prédiction `useSpecial == 0` vérifiée, pas
contournée), discriminant `IsMelee` 0≠1 OK. Le `0` vs `14` est aussi la preuve live que `0x93`
porte l'ordinal de l'enum et non un weaponId.

## 5. Contre-épreuve — `a_mordu` publié séparément du verdict

| mutation | `a_mordu` | attendu | rougit | verdict |
|---|---|---|---|---|
| M1 `FlailSwing isMelee 1→0` | oui | oui | oui | OK |
| M2 `SentinelDir isMelee 0→1` | oui | oui | oui | OK |
| M3 `Use_Special inconditionnelle` | oui | oui | oui | OK |
| M4a interversion `0x92`/`0x93` sur `FlailSwing` | oui | oui | oui | OK |
| M4b interversion `0x92`/`0x93` sur `SentinelDirectives` | **non** | **non** | non | OK |

⚠ **M4b est INERTE PAR ALGÈBRE, et c'est mesuré, pas subi** : sur `SentinelDirectives`,
`Physical` vaut `0` **et** `isMelee` vaut `0` — la faute exacte de l'ancienne docstring ne change
**rien** sur ce porteur. C'est `FlailSwing` (14 vs 1) qui la révèle. L'équivalence est
assertionnée **dans les deux sens** (test 5), donc sa disparition rougira au lieu de passer.
Même forme que l'inertie `Chain`/`Bolter` (ratio 20) du parent.

## 5. La voie ATTAQUE NORMALE (`-r1`) — dérivée, pas littérale

`ALoki_NormalAttackAbility$$ExecuteBehaviour` :

```
weapon = FindAttackWeapon(entities);                     // slot 0xaf d'IBattleQuery
if (weapon == null) return default;                      // NI Inform, NI attaque, NI triggers
ExecuteInformWeapon(this, weapon, entities, /*useSpecial*/ 0);
ExecuteNormalAttack(this, abilityState, entities, weapon);
return ExecuteTriggerAbilities(this, entities, weapon);
```

Le flux natif porte donc ces tags sur **chaque** attaque normale — mesuré, forme exacte :

```
Group=Ability_Power Entity=83 Source=Loki_NormalAttack InitialTarget=77
    Action=Info Entity=NO_ENTITY
        Tag=Attack_Weapon_IsMelee:1
        Tag=Attack_Weapon_DamageProfile:14
    Group=NormalAttack_AtomicDamage ...
```

⚠ **Le vert de `probe_477r15a` était HONNÊTE MAIS MUET, et c'est un TROU DE PÉRIMÈTRE de
l'oracle.** Il ne compare que le groupe racine `System_GameSetup` (le déploiement) ; ces lignes
vivent sous un groupe racine `User_UseAbility`, jamais visité. Son 204/204 + 316/316 ne disait
donc **rien** de ce morceau — et il reste vert après le port, à l'identique.

**Ce qui est porté** : `InformWeapon.from_weapon(weapon, useSpecial)` (surcharge à 2 arguments —
`damageProfileType = weapon.DamageProfile`, `isMelee = battle_query.weapon_is_melee`, le prédicat
`Range is None || Range < 2` déjà en place) ; `streams/inform_ops.py` (foyer **unique** des trois
clés + mirror d'`InformOperation$$Execute` → `Action=Info Entity=NO_ENTITY`) ; et l'appel dans
`damage_ops/normal.py`, au point exact du natif (juste après le gate d'arme).

**Confrontation live** (MC1_67, seed 41902), 4 porteurs, port == natif **8/8** clés
inconditionnelles + **4/4** conditionnelle, et le **texte** du flux reproduit ligne à ligne 4/4 :

| porteur | régime | flux natif | port |
|---|---|---|---|
| `deathBlightlord` | contact | `{IsMelee: 1, Profile: 14}` | idem |
| `astraBullgryn` | contact | `{IsMelee: 1, Profile: 0}` | idem |
| `admecDestroyer` | distance 3 | `{IsMelee: 0, Profile: 0}` | idem |
| `tyranDeathleaper` | **charge** | `{IsMelee: 1, Profile: 22, Use_Special: 1}` | idem |

Trois pièges sont fermés par ce corpus, chacun par un porteur qu'aucun autre ne remplace : les
`IsMelee` **diffèrent** (constante impossible) ; `astraBullgryn` et `admecDestroyer` partagent le
profil `0` avec des `IsMelee` **opposés** (dériver `isMelee` du profil impossible) ; et
`admecDestroyer` porte **deux** armes, donc son `isMelee` dépend de la **distance**, pas de l'unité.

## 6. `useSpecial` : le chiffre est CLOS, et deux sites posent `1`

Les **15** sites qui fixent l'argument sont lus — **12** littéraux `0`, **2** littéraux `1`,
**1** dynamique :

| voie | site | `useSpecial` |
|---|---|---|
| 3 args | `HeavyBoltPistol` / `FlailSwing` / `SentinelDirectives` / `StranglethornCannon` / `IncendiaryShells` | `0` (×5) |
| 3 args | `OptimizedGait_TriggerAttackAbility$$CreateBehaviour` | `HasEffect(target, 0x4e2)` |
| `ExecuteInformWeapon` | `ALoki` / `ProperKilly` / `RighteousRepugnance` / `TalonOfHorus` / `Boltstorm`×2 / `Fealty` | `0` (×7) |
| `ExecuteInformWeapon` | **`FeederTendrils_NormalAttackAbility$$ExecuteBehaviour`** | **`1`** sous `IsCharging(caster,target) & weapon.IsMelee` |
| `ExecuteInformWeapon` | **`OptimizedGait_NormalAttackAbility$$ExecuteBehaviour`** | **`1`** sous `HasEffect(<?>, 0x4e2)` |

⚠ **Le second terme du `&` de `FeederTendrils` est `WeaponProfile$$get_IsMelee(weapon)`, pas un
second prédicat de charge.** Le lire comme un `IsCharging` seul poserait la clé sur un *tir* de
charge, que le natif ne pose pas.

**Confronté** : `tyranDeathleaper` déplacé au contact (donc `UpdateCharging`) écrit bel et bien
`Tag=Attack_Weapon_Use_Special:1` dans le flux. C'est la **première** observation de cette clé.
Le port la reproduit via le foyer unique `custom_normal_attack.inform_weapon_use_special`.

## 7bis. La branche SPÉCIALE de `FeederTendrils` (`-r1`) — le soin ET l'effet, portés

Le bloc existe **DEUX FOIS** dans le binaire, instruction pour instruction : inliné dans
`FeederTendrils_NormalAttackAbility$$ExecuteBehaviour`, et comme corps autonome de
`IdunBattleLogic.Entities.Abilities.Active.Loki.FeederTendrils_NormalAttackAbility$$ExecuteSpecialAttack`.
C'est une lecture de contrôle gratuite, et elle concorde.

```csharp
amount  = DSLFormulas.ConfigVar(0x20, abilityState, this@+0x60);   // AbilityVariableType.hpToHeal
options = HealBehaviourOptions.ForHeal(AbilityOrEffect.op_Implicit(<this>));
b = DSLBehaviors.Heal(healer: sel@+0x30, selector: sel@+0x30, amount, options)   // le CASTER
  + DSLBehaviors.AddEffect(0x429, AbilityStateReference, targets: sel@+0x60, turns: null); // la CIBLE
return ExecuteAtomic(this, b, entities, 0x2a);        // GroupType.Ability_AtomicGroup
```

⚠ **LES DEUX ANCRES DIFFÈRENT, et c'est le point le plus facile à rater.** `Heal` reçoit `+0x30`
**deux fois** (`healer` ET `selector` de `DSLBehaviors$$Heal(this, healer, selector, amount,
options)`) ; `AddEffect` reçoit `+0x60`. Ce que ces deux slots désignent est établi par le MÊME
`ExecuteBehaviour`, deux lignes plus haut : `DSLTriggers$$IsCharging(this, caster, target)` (noms de
paramètres du dump) y reçoit `(*(sel+0x30), *(sel+0x60))`. Lecture de contrôle indépendante —
`CordClawAbility$$ExecuteBehaviour` pose son self-buff via ce même `+0x30`, et le port l'écrit déjà
`Caster()`. Écrire les deux feuilles sur la même ancre serait **silencieux** : `Pinned` porte un
malus de dégât ATTAQUANT ×0.70, donc la faute déplacerait un chiffre au tour SUIVANT.

**Littéraux qualifiés** : `0x429` = `EffectType.Pinned` ; `0x2a` = `GroupType.Ability_AtomicGroup`
(⚠ 42 est aussi `StepType.RotateUnit`) ; `0x20` = `AbilityVariableType.hpToHeal` (⚠ 32 est aussi
`AbilityConstantType.hpForArmor` — tranché par la **surcharge** `ConfigVar(this, variableType,
abilityState, config)`, pas par le nom). `turns = null` ⇒ durée DÉFAUT ; contraste LU dans le même
binaire, `CordClaw` passe `TurnsFromRounds(2)` à la même position.

**Le niveau** : `hpToHeal` n'existe pas sous `FeederTendrils_NormalAttack` au gameconfig — c'est le
PASSIF `FeederTendrils` qui la porte, cohérent avec la fabrique (`AddNormalAttackAbility` monte
l'attaque substituée avec le `triggeredAbilityState`). Le port lit `passive_ability_level`, fallback
actif — même règle et même précédent que `MV71SniperDroneSquad`.

**Confrontation live** (MC1_67), deux régimes qui DIFFÈRENT sur les TROIS observables :

| régime | HP caster | `Pinned` sur la cible | `Use_Special` |
|---|---|---|---|
| CHARGE (au contact, arme mêlée) | 392342 → 395632 (**+3290**) | absent → **présent** | **1** |
| NO_STEP (mêlée, sans charge) | 388050 → 388050 (**0**) | absent → absent | absent |

et **+3290 est exactement ce que le port pose** (`hpToHeal` niv. 50, mult. 180).

⚠ **LE TÉMOIN DOIT ÊTRE NON NUL À DEUX TITRES, et le second ne s'est vu qu'à la mesure.** La garde
`Healable` (HP < max) rend le soin inerte sur une unité pleine — première passe : 400000 → 400000
des deux côtés, un accord qui ne prouve rien. Mais `HealUnitOperation` **PLAFONNE aussi le soin à
`hp_max`** : une blessure de 1356 pour un `hpToHeal` de 3290 a fait lire un « écart de montant »
qui n'existait pas. Il faut donc creuser un trou **plus profond que le soin attendu** — c'est ce que
fait le probe (cible = 2 × le montant).

⚠ **Et une garde branchée sur un champ ABSENT ne se déclenche jamais, en silence** :
`decisionView.units[]` ne porte AUCUN champ de PV max, donc un `hp >= hp_max` y est toujours faux.
Même forme que le premier faux négatif de cette tranche — `observeBattle.units[]` n'a pas de champ
`effects` (seul `decisionView` les porte), et le lecteur branché dessus rendait une liste vide sans
erreur, ce qui se lisait « régime non armé ».

## 7ter. L'ANCRE d'`OptimizedGait_NormalAttack` (`-r2`) — c'est le CASTER

Le gate est `EntityExtensions$$HasEffect(<entités du champ `+8`>, state, 0x4e2, null)` — et
`HasEffect(entity, state, requestedEffectType, onlyActive)` = `IsOwnerOfEffect(...) ||
IsTargetOfEffect(...)`, avec `onlyActive = null` (donc **pas** de filtre `IsActive` : le mirror est
`EffectsState.has_effect`, qui ne filtre que `consumed`).

**RE.** `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` écrit ses champs avec les noms de
paramètres du dump : `+0x00 = actor`, **`+0x08 = caster`**, `+0x10 = target`, `+0x18 = owner`,
`+0x20 = activeTarget`, `+0x30 = targetTile`, `+0x40 = casterTile`, `+0x7c = parentAbilityOrEffect`,
`+0x98 = triggerAbilityOrEffect`. L'appariement nom↔offset est vérifié par **SIX** getters
concordants de la même classe (`get_ParentAbilityType` → `+0x7c`, `get_TriggerAbilityType` →
`+0x98`, `get_IsFirstHit` → `+0x108` = `hitIndex`, `get_IsFirstHitGroup` → `+0x110`,
`get_HasCasterPosition` → `+0x48`/`+0x40`, `get_HasTargetPosition` → `+0x38`/`+0x30`), et la struct
fait **0x128** octets — exactement ce que l'`ExecuteBehaviour` recopie (0x25 qwords).

**MESURE** (`admecRuststalker` dans CHAQUE camp, trois bras séparants) :

| bras | `0x4e2` sur le caster | sur la cible | `Tag=Attack_Weapon_Use_Special` |
|---|---|---|---|
| `aucun` | non | non | **absent** |
| `caster` | **oui** | non | **1** |
| `cible` | non | **oui** | **absent** |

Le bras `cible` est le **discriminant** : l'effet EST sur la cible et le natif n'écrit rien. Une
ancre-cible aurait écrit le tag. Le régime s'arme parce que `CordClaw` pose
`CordClaw_AdditionHits` **sur son propre caster** (self-buff mesuré, `remaining=3`) — faire caster
l'adversaire met donc l'effet sur la cible, et sur elle seule.

⚠ **NE PAS GÉNÉRALISER** : `OptimizedGait_TriggerAttackAbility$$CreateBehaviour` (la surcharge à 3
arguments) ancre SON `HasEffect` sur la **CIBLE**. Deux abilities, deux ancres ; l'une n'autorise
rien sur l'autre.

⚠ **Deux pièges de MONTAGE, tous deux à refus SILENCIEUX** (`ok=True`, aucun effet — signature
#111) : un cast sur une unité qui a déjà agi, et un cast par une unité dont ce n'est pas le tour.
D'où le cran `hasAction` **sur l'unité visée nommément** — avec un même `visualId` dans les deux
camps, « le premier de ce `visualId` dont l'owner est le joueur courant » désigne tantôt l'un
tantôt l'autre, et la même unité a casté dans deux bras censés être opposés.

## 7. Ce qui n'est PAS couvert

* **Le `Pinned` posé par cette branche n'est PAS confronté sur son EFFET AVAL** (malus de mouvement
  et ×0.70 de dégât attaquant). Ce qui est mesuré ici, c'est sa POSE (présent/absent sur la cible) ;
  `PinnedEffect` est porté et validé par ailleurs (`status.py`).
* **L'ORDRE des deux feuilles entre elles n'est pas observable** et ne peut pas l'être : elles sont
  pures (aucun tirage) et portent sur des unités distinctes. Il est mirroré, pas mesuré.
* **La position du bloc AVANT `ExecuteNormalAttack` n'a pas d'observable AUJOURD'HUI** : `Pinned`
  gate `OwnerIsCaster`, donc il ne touche pas l'attaque qui suit (dont l'attaquant est le caster).
  Elle est portée parce que c'est celle du natif, et gardée par un test de position.
* **Le groupe `Ability_AtomicGroup` n'est pas ÉMIS dans le flux** par `engine.streams` — le port
  joue l'arbre, pas son enveloppe de présentation. Hors périmètre, comme le reste du groupe
  `Ability_Power`.
* **Les trois porteurs non portés** de la surcharge à 3 arguments (`StranglethornCannon`,
  `IncendiaryShells`, `OptimizedGait_TriggerAttack`) ne sont pas dans `engine/` : rien à corriger.
* **Le reste du groupe `Ability_Power` de l'attaque normale** (`NormalAttack_AtomicDamage`,
  `Group=Damage`, `UnitDamaged`) n'est pas émis par `engine.streams` — hors périmètre de cette
  tranche, qui ne porte que le pas `Action=Info`.
