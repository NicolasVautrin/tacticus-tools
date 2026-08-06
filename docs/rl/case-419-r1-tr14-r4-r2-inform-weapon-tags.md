# #419-r1-tr14-r4-r2 — `InformWeapon` : les trois clés portées, sur les DEUX voies

**Résolu**, résidu `-r1` inclus. Build `rnca9r7q6c`, ghidra-mcp sur le binaire installé, session
Frida 1.

```powershell
python scripts/python/probe_419r1tr14r4r2_inform_weapon_tags.py                  # cast live x2
python scripts/python/probe_419r1tr14r4r2_inform_weapon_tags.py --contre-epreuve # 5 mutations, 0 runner
python -m pytest scripts/python/tests/engine/runner/test_419r1tr14r4r2_inform_weapon_tags_offline.py -q
# la voie ATTAQUE NORMALE (#419-r1-tr14-r4-r2-r1)
python scripts/python/probe_419r1tr14r4r2r1_normal_attack_inform_weapon.py                  # 4 porteurs live
python scripts/python/probe_419r1tr14r4r2r1_normal_attack_inform_weapon.py --contre-epreuve # 7 mutations, 0 runner
python -m pytest scripts/python/tests/engine/runner/test_419r1tr14r4r2r1_normal_attack_inform_weapon_offline.py -q
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

## 7. Ce qui n'est PAS couvert

* **Résidu `#419-r1-tr14-r4-r2-r1-r1` — la branche SPÉCIALE de `FeederTendrils` n'est portée que
  pour son TAG.** La même branche exécute aussi `Heal(ConfigVar 0x20)` et `AddEffect(0x429)`, que
  le port ne joue pas. Ne pas lire « `FeederTendrils` est porté » : seul son `useSpecial` l'est.
* **Résidu `#419-r1-tr14-r4-r2-r1-r2` — `OptimizedGait_NormalAttack` : l'ANCRE du gate n'est pas
  tranchée.** `EntityExtensions$$HasEffect(<entité du champ `+8` des `AbilityEntities`>, state,
  0x4e2, null)` : caster ou cible ? L'inscrire au jugé écrirait un `Use_Special` faux sur un
  porteur réel (`admecRuststalker`, dans le pool). Débloqueur : lire le layout d'`AbilityEntities`,
  ou monter les deux régimes (effet `0x4e2` sur le caster / sur la cible) et mesurer.
* **Les trois porteurs non portés** de la surcharge à 3 arguments (`StranglethornCannon`,
  `IncendiaryShells`, `OptimizedGait_TriggerAttack`) ne sont pas dans `engine/` : rien à corriger.
* **Le reste du groupe `Ability_Power` de l'attaque normale** (`NormalAttack_AtomicDamage`,
  `Group=Damage`, `UnitDamaged`) n'est pas émis par `engine.streams` — hors périmètre de cette
  tranche, qui ne porte que le pas `Action=Info`.
