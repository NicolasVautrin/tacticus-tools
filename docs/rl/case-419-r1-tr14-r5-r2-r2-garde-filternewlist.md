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
