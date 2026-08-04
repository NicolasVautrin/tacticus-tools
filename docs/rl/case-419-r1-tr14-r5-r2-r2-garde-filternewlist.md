# #419-r1-tr14-r5-r2-r2 — la garde `FilterNewList` du repli générique de l'attaque normale

Dernier étage de la cascade de dispatch de l'attaque normale
(`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility`), après PASSIVE (#557),
ACTIVE (#565) et TRAIT (#569).

**Question binaire** : la garde qui précède le repli générique est-elle portée ? Non — et son
absence est **PERMISSIVE** : le port pose une attaque normale générique là où le natif
**s'abstient d'en poser une**.

## 1. Le corps natif, lu verbatim

`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility`, le `else` final :

```csharp
else {                                                    // aucune des 3 voies n'a gagné
    var f = <>c.<>9__10_0 ??= new Func<ActiveAbilityEntry,bool>(<>c.<>9,
                                    <>c.<AddNormalAttackAbility>b__10_0);
    var list = ListExtensions.FilterNewList(comp.<+0x20>, f);
    if (list == null) throw;
    if (0 < list.Count) return;                           // <-- LA GARDE : rien n'est ajouté
    type  = this.<+0x20>;
    state = new AbilityState(new Level(1, 0), config.<+0x74>);
}
ActiveAbilityComponent.Add(comp, type, state, null);
```

La forme `if (0 < list.Count) return;` rapportée par #565 est **confirmée** (`list+0x18` = `_size`
d'une `List<T>`). Ce qui n'avait **pas** été lu, et qui fait tout le sens de la garde, c'est le
prédicat et la collection.

### 1.1 Le prédicat — `IdunBattle.Entities.Factories.UnitFactory.u003Cu003Ec$$u003CAddNormalAttackAbilityu003Eb__10_0`

```csharp
a => StaticBattleRules.ActiveAbility.IsRegularAttack(a.<+0x44>)
```

Un seul appel, aucune autre condition. `a.<+0x44>` est l'`ActiveAbilityType` de l'entrée — établi
par `IdunBattle.Entities.Components.ActiveAbilityComponent$$Add`, qui écrit `entry.<+0x44> = abilityType`.

### 1.2 La collection — `comp.<+0x20>`

`comp` est l'`ActiveAbilityComponent` de l'entité. Son `+0x20` est la
`KeyedCollection<ActiveAbilityType, ActiveAbilityEntry>` que `...ActiveAbilityComponent$$Add`
alimente. Le même `Add` pose aussi, **pour toute entrée qui passe `IsRegularAttack`**,
`comp.<+0x28>` — c'est-à-dire `NormalAttackType`, le champ que le harnais lit déjà.

### 1.3 `FilterNewList` GARDE ce qui rend vrai (ce n'est pas un `RemoveAll`)

`idun.shared.extensions.ListExtensions$$FilterNewListu003C__Il2CppFullySharedGenericTypeu003E`
copie la source dans une `List<T>` neuve puis délègue à
`idun.shared.extensions.ListExtensions$$FilterInPlaceu003C__Il2CppFullySharedGenericTypeu003E`,
dont la boucle est descendante :

```csharp
for (int i = list.Count - 1; i >= 0; i--)
    if (!predicate(list[i])) list.RemoveAt(i);
return list;
```

Donc `FilterNewList(src, p)` == `src.Where(p).ToList()`. La garde se lit :
**« s'il existe DÉJÀ, dans l'`ActiveAbilityComponent`, au moins une ability qui est une attaque
régulière, ne pose pas l'attaque normale générique »**.

### 1.4 `IsRegularAttack` — table déjà portée, re-dérivée ici

`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsRegularAttack`
= `Contains` sur l'`OrderedSet<ActiveAbilityType>` du champ statique `+0x18` de
`StaticBattleRules.ActiveAbility`, rempli par son `$$.cctor`.

**Re-lu indépendamment** dans le `.cctor` pour cette tranche : **18 entrées**, dans cet ordre —
`0x011, 0x045, 0x406, 0x416, 0x434, 0x43e, 0x45a, 0x460, 0x468, 0x463, 0x466, 0x47a, 0x48a,
0x472, 0x49a, 0x49e, 0x4b5, 0x4c4`. Elles coïncident **exactement**, valeur par valeur et dans le
même ordre, avec `REGULAR_ATTACK_ABILITY_TYPES` de
`engine/runner/abilities/attack_type.py` (porté en amont pour `AbilityIsNormalAttackTrigger`).

⇒ **Aucune table nouvelle n'est à écrire.** Le port de cette garde doit RÉUTILISER
`engine.runner.abilities.attack_type.is_regular_attack` — en re-dériver une seconde serait un fork.

⚠ Le champ statique `+0x18` n'est **pas** celui de la voie ACTIVE : `GetCustomNormalAttack` lit
`+0x28` (un `Dictionary`), et le `.cctor` écrit encore `+0x00`, `+0x08`, `+0x10`, `+0x20`. Cinq
collections statiques distinctes dans la même classe — les confondre donnerait un prédicat faux.

## 2. L'ordre dans la fabrique — ce qui rend la garde NON VIDE

`IdunBattle.Entities.Factories.UnitFactory$$Build` est l'**unique** appelant de
`AddNormalAttackAbility` (xrefs : 1 `UNCONDITIONAL_CALL`). Il enchaîne, dans cet ordre :

```
UnitFactory$$AddConfiguredAbilities(entity, config, ...)     <-- AVANT
UnitFactory$$AddNormalAttackAbility(this, entity, config, ...)
UnitFactory$$AddDerivedAbilities(entity, config, ...)
UnitFactory$$AddDerivedBehaviours(this, entity, config)
```

**`AddConfiguredAbilities` court AVANT.** C'est lui qui monte les abilities configurées de
l'entité dans l'`ActiveAbilityComponent`. Au moment où la garde s'évalue, la collection n'est donc
pas vide : elle contient déjà ce que `BC.Units[].ActiveAbilities` (et la tertiaire/relique) a posé.

La garde n'est donc pas défensive ni morte : elle dit **« cette unité tient déjà son attaque
normale de sa configuration — ne lui en superpose pas une générique »**.

`IdunBattle.Entities.Factories.UnitFactory$$AddActiveAbility` appelle
`IdunBattle.Entities.Components.ActiveAbilityComponent$$Add` **inconditionnellement** pour chaque
entrée — il n'y a aucun filtre entre `config.ActiveAbilities` et la collection que la garde teste.

Le générique posé au repli est `this.<+0x20>`, écrit par
`IdunBattle.Entities.Factories.UnitFactory$$.ctor(this, unitsConfiguration, logger, normalAbilityType)` :
c'est un **paramètre de construction**, pas une constante en dur. Mesuré `Loki_NormalAttack` (69)
sur tous les bras.

## 3. L'effet observable, énoncé AVANT la mesure

La garde mord **ssi `BC.Units[].ActiveAbilities` contient une des 18 attaques régulières**. Dans ce
cas le natif n'ajoute rien, et `NormalAttackType` reste celle déjà montée. Sans la garde, la
générique serait ajoutée et **écraserait** `comp.<+0x28>` — c'est précisément ce que la garde
protège.

Le port ne la modélisait pas : il tombait sur son repli générique. **L'écart est donc du côté
PERMISSIF** — le port pose une attaque normale là où le natif s'abstient, et se trompe en plus de
type (générique au lieu de celle qui est montée).

## 4. La confrontation live (`probe_419r1tr14r5r2r2_filter_new_list`, board `MC1_67`)

Quatre unités, **un seul build**, la variable étudiée étant la NATURE de l'active montée. Le levier
est `BC.Units[].ActiveAbilities`, ÉCRIT — comme en -r2 et -r2-r1.

| rôle | actives | passives | natif MESURÉ | port |
|---|---|---|---|---|
| `preuve` | `[TemplarInitiateNormalAttack]` | `[]` | **`TemplarInitiateNormalAttack`** | `Loki_NormalAttack` |
| `temoin-nonreg` | `[UnstoppableMomentumReworked]` | `[]` | `Loki_NormalAttack` | `Loki_NormalAttack` |
| `temoin-origine` | (origine) | `[]` | `Loki_NormalAttack` | `Loki_NormalAttack` |
| `ordre-pas` | `[TemplarInitiateNormalAttack]` | `[Boltstorm]` | `Boltstorm_NormalAttack` | `Boltstorm_NormalAttack` |

**4/4 conformes à l'attendu natif.** La garde est donc VIVANTE, et `ordre-pas` borne son RANG : une
voie de rang supérieur gagne même quand une régulière est montée.

⚠ **Le montage écrit l'id DIRECTEMENT.** `catalog_inject.graft_active_ability` est inutilisable
ici : il synthétise une config d'ability, or **aucune des 18 n'en a** (0/18 au gameconfig, 0/131
dans `BC.Abilities.ActiveAbilities` du seed). C'est structurel — une attaque normale n'est pas une
ability de catalogue, le natif la résout par TYPE.

## 5. Pourquoi la garde est PORTÉE mais NON BRANCHÉE — un arbitrage mesuré

Le foyer `normal_attack_already_present` (mirror 1:1) est livré et **s'accorde au natif sur les
4 bras**. Il n'est pourtant pas appelé par `custom_normal_attack`, et ce n'est pas un oubli :

* **Le substrat exact manque.** Le natif teste la collection AVANT l'ajout du générique
  (`config.ActiveAbilities`). Le seul canal du port, `UnitContext.active_abilities`, lit
  l'`ActiveAbilityComponent` APRÈS la fabrique. **Mesuré** : bras témoin →
  `['FireAndReposition', 'Loki_NormalAttack']` — le générique y est.
* **Le brancher court-circuite les trois voies amont.** Le canal contenant déjà le résultat, la
  « dernière régulière » y est toujours `NormalAttackType` : la garde répondrait juste **même voie
  passive/active/trait coupée**. Mesuré : branchée, elle rend INERTE la contre-épreuve de la voie
  ACTIVE (#565) — `1 failed / 5 passed`, contre `6 passed` une fois débranchée. C'est un accord en
  régime dégénéré, pas de la fidélité gagnée.
* **Et le gain en production est NUL.** La garde ne mord que si une régulière figure dans
  `BC.Units[].ActiveAbilities` : **0 sur les 175 unités du seed**, et aucune des 18 n'est attribuée
  par les 5 voies du gameconfig. Seul un montage ÉCRIT l'exerce.

**Échange refusé** : fermer un écart inatteignable en production au prix d'affaiblir la garde d'un
écart atteignable. Ce qui reste ouvert est donc un problème de **CANAL**, pas de RE.

## 6. Résidus

* **`#419-r1-tr14-r5-r2-r2-r1` — brancher la garde exige un canal `UnitConfiguration.ActiveAbilities`**
  (l'état PRE-fabrique). Aujourd'hui `unitAbilityStates.actives` ne publie que l'état POST-fabrique.
  L'écart mesuré qui subsiste est la seule ligne `preuve` (natif `TemplarInitiateNormalAttack`,
  port `Loki_NormalAttack`), et il est **figé par un cliquet** dans
  `test_419r1tr14r5r2r2_filter_new_list_live.py` : ce test rougit si l'écart s'élargit **comme**
  s'il se ferme. Point d'ancrage natif à exposer : `UnitConfiguration@+0xa0`, lu par
  `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities`.
* **Second ordre** : si `IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities` posait une
  active RÉGULIÈRE (il appelle `ActiveAbilityComponent$$Add` par trois chemins —
  `GetDerivedActiveAbilities` d'une active, d'un passif, et `Trait.GetActiveAbility`), elle serait
  la dernière du composant et fausserait la lecture « dernière régulière ». Aucun des 4 bras n'en
  produit ; ce n'est pas une preuve générale.
* **Hors périmètre, nommé** : `this.<+0x20>` (le générique) est un paramètre du ctor du factory.
  Le port le suppose constant (`Loki_NormalAttack`) ; l'appelant du ctor n'a pas été lu.
