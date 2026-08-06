# #419-r1-tr14-r4-r2 — `InformWeapon` : deux clés portées, et une docstring fausse sur QUATRE points

**Résolu.** Build `rnca9r7q6c`, ghidra-mcp sur le binaire installé, session Frida 1.

```powershell
python scripts/python/probe_419r1tr14r4r2_inform_weapon_tags.py                  # cast live x2
python scripts/python/probe_419r1tr14r4r2_inform_weapon_tags.py --contre-epreuve # 5 mutations, 0 runner
python -m pytest scripts/python/tests/engine/runner/test_419r1tr14r4r2_inform_weapon_tags_offline.py -q
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

## 6. Ce qui n'est PAS couvert

* **`useSpecial != 0` n'est confronté nulle part.** Lus : **8 littéraux `0` sur 8** (5 des 6 xrefs
  à 3 arguments + 3 des 9 xrefs de `ALoki_NormalAttackAbility$$ExecuteInformWeapon`), **1**
  dynamique, **6** non lus. Le seul chemin pouvant poser `0x94` est `OptimizedGait_Trigger
  AttackAbility$$CreateBehaviour` — **non porté**. Le port pose la clé si `use_special`, et c'est
  gardé structurellement (test 2), mais jamais observé à `1` dans le flux.
* **Les trois porteurs non portés** (`StranglethornCannon`, `IncendiaryShells`, `OptimizedGait`)
  ne sont pas dans `engine/` : rien à corriger, rien à confronter.
* **Résidu `#419-r1-tr14-r4-r2-r1` — le chemin ATTAQUE NORMALE ne pose pas ces tags côté port.**
  `ALoki_NormalAttackAbility$$ExecuteInformWeapon` est le porteur le plus fréquent (9 appelants),
  et son `isMelee` est **dérivé de l'arme** (`WeaponProfile$$get_IsMelee`), pas d'un littéral.
  Notre attaque normale n'émet aucun `InformWeapon`. `probe_477r15a` reste VERT (204/204,
  316/316), donc rien ne diverge sur son périmètre — mais ce n'est pas une preuve que le tag est
  produit : il peut être hors du périmètre confronté. Débloqueur : vérifier si
  `Attack_Weapon_IsMelee` figure parmi les tags qu'une attaque normale PORTÉE doit émettre, et
  lire les 6 xrefs restantes pour clore le chiffre de `useSpecial`.
