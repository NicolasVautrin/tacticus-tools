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

## 7. `#419-r1-tr14-r5-r2-r2-r1` — le capteur du canal PRÉ-FABRIQUE, écrit (#466), NON CONFRONTÉ

Le résidu était bloqué sur un **canal**, pas sur une question ouverte (§5). Le canal est écrit.
**Aucune ligne de §7.3 n'est une mesure du capteur** : rien n'a tiré, faute de fenêtre de reinject.
§7.1 et §7.2, elles, sont des mesures — prises sur le bundle DÉPLOYÉ, qui ne porte pas le capteur.

### 7.1 L'offset `+0xa0` : la piste de la PR #575 est CONFIRMÉE, et par deux chemins

La fiche du résidu donnait `UnitConfiguration@+0xa0` comme piste. Deux lectures indépendantes la
transforment en mesure, sur `rnca9r7q6c` :

| chemin | ce qu'il rend |
|---|---|
| décompilé — `IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromActive` | énumère `config.<+0xa0>` (`List.GetEnumerator` gshared, éléments lus en `uint32`) puis appelle `StaticBattleRules.ActiveAbility$$GetCustomNormalAttack` sur chacun |
| métadonnées IL2CPP live — RPC `classFields("IdunBattle.Configuration", "UnitConfiguration")` | `ActiveAbilities` @**`0xa0`**, type `List\`1` |

Les deux voisins cités par la case-doc de la tranche concordent aussi (`PassiveAbilities` @`0xa8`,
`Traits` @`0xd0`), ce qui interdit un décalage global d'un champ.

**TROISIÈME lecture, concordante** : `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities`
— le lecteur que nommait la fiche du résidu — termine par
`while (i < List.get_Count(config.<+0xa0>)) AddActiveAbility(List.get_Item(config.<+0xa0>, i), …)`.
Le même champ, par un troisième chemin. (Le corps corrobore au passage `PASSIVE_HIERARCHY = 2` :
il énumère `config.<+0xa8>` vers `TriggeredAbilityComponent$$TryAdd(…, 2)`, et la branche
tertiaire `config.<+0xb0>` vers `TryAdd(…, 3)`.)

**La JOINTURE entité → configuration est LUE, pas supposée.**
`IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent(entity, config)` écrit, dans l'ordre :

```
baseUnitComponent.<Id @+0x10>        = config.<Id @+0x10>
baseUnitComponent.<QuestUnitId @+0x18> = config.<QuestUnitId @+0x20>
baseUnitComponent.<VisualId @+0x20>  = config.<VisualId @+0x18>
```

⇒ la clé est `BaseUnitComponent.Id`, obtenue par la fonction NOMMÉE
`IdunBattle.Entities.UnitExtensions$$GetBaseUnitComponent` — celle que la fabrique appelle
elle-même. Jointure **N→1** assumée (deux camps peuvent porter la même unité) ; le cas contraire
(deux configurations de même `Id`) est publié par `configLayout.configIdCollisions`.

### 7.2 Ce que la PRÉMISSE vaut, MESURÉ sur le bundle déployé

Le §5 affirmait « le canal POST-fabrique contient déjà la réponse » sur **un** bras témoin. Mesure
refaite le 2026-08-04 sur un runner neuf (`--seed 777 --board MC1_67`, six unités), en confrontant
`unitAbilityStates.units[].actives` (POST) au `BC.Units[].ActiveAbilities` **effectivement envoyé
au runner** (relu du `--state-file`, donc après `buildNormalizedBC` — qui ne réécrit **pas** ce
champ : `normalize-bc/json-build.ts` ne touche qu'à `ActiveAbilityLevel`, et le dit) :

| entité | PRE (`BC.Units[].ActiveAbilities`) | POST (`actives`) | l'entrée EN PLUS |
|---|---|---|---|
| `templAggressor` | `[1048]` | `[1048, 1128]` | `1128 Boltstorm_NormalAttack` |
| `eldarRanger` | `[1063]` | `[1063, 69]` | `69 Loki_NormalAttack` |
| `orksNob` | `[1152]` | `[1152, 69]` | `69` |
| `tauMarksman` | `[1069]` | `[1069, 1076]` | `1076 MV71SniperDroneSquadAttack` |
| `necroWarden` | `[1005]` | `[1005, 69]` | `69` |
| `astraBullgryn` | `[1017]` | `[1017, 69]` | `69` |

**6/6** : POST = PRE ∪ {l'attaque normale que la fabrique vient d'écrire}, **rien de manquant**.
Et les six entrées ajoutées sont **toutes régulières** (`REGULAR_ATTACK_ABILITY_TYPES`, 18 valeurs,
re-dérivées) — c'est-à-dire que `normal_attack_already_present`, branchée sur ce canal, rendrait
non-`None` pour **6 unités sur 6**, quelle que soit la voie amont. La tautologie de §5 n'est donc
plus un raisonnement, c'est un compte.

Symétriquement, **aucune** des entrées PRE n'est régulière : **0 sur les 175 unités du seed**
(1048/1063/1152/1069/1005/1017 pour ces six-là). Sur le canal PRÉ-fabrique la garde rendrait
`None` partout — le repli générique s'applique, ce qui est la réponse du natif. Le gisement de
production reste donc VIDE : le capteur ne ferme pas un écart, il rend la garde **falsifiable**,
ce que le régime monté (`catalog_inject.graft_active_ability`) exerce.

### 7.3 Ce qui est livré — `frida/hooks/features/ai-step/rpc-snapshot.ts`

`unitAbilityStates` publie, **par unité** : `configId` (la clé de jointure lue) et `configActives`
(`[{type, name}]`), plus, au niveau réponse, `configLayout`.

* **TRI-ÉTAT STRICT** : `configActives === null` = **PAS MESURÉ** — clé illisible, entité sans
  configuration dans la BC (une unité **INVOQUÉE**, qui naît d'une opération de spawn et non de
  `BC.Units`), ou liste non décodable. `[]` = **mesuré, configuration sans actif** : c'est le cas
  de **50 des 175** entrées du seed, donc le confondre avec « pas mesuré » détruirait précisément
  ce que ce canal existe pour permettre.
* **Offsets résolus PAR NOM, sans repli littéral.** Un nom absent au prochain build doit rendre
  « pas mesuré », jamais la lecture d'un offset devenu celui d'un autre champ (le piège que
  `fieldOffsetOr` documente : `-1` est *truthy*). Les littéraux du décompilé sont publiés dans
  `configLayout.decompiled*` **pour le diagnostic seul** — ils ne servent jamais à lire.
* **Le STRIDE de `List<ActiveAbilityType>` est DÉRIVÉ du tableau** (`class_get_element_class` +
  `class_is_valuetype` + `class_instance_size`), pas supposé ; un stride ≠ 4 rend `null` et publie
  ce qu'il a vu, au lieu de nombres plausibles.
* **Le port n'est PAS branché.** `normal_attack_already_present` reste hors de `custom_normal_attack` :
  brancher change un résultat observable, donc c'est spéculatif tant que la mesure n'a pas eu lieu.
  Le cliquet `test_419r1tr14r5r2r2_filter_new_list_live.py` est inchangé.
* **Condition d'émission des lignes INCHANGÉE** (`actives.length || triggered.length`) : l'élargir
  ferait passer des unités du repli KIT à une mesure `[]` côté `_load_active_abilities`, un
  changement de comportement qu'aucune mesure ne couvre. Les 6 unités du montage ci-dessus
  apparaissent toutes, donc la condition ne coûte rien ici.

### 7.4 PLAN DE MESURE — ce que la fenêtre doit jouer, et ce que chaque résultat tranche

Prérequis : reinject + `autoBootExtraire({force:true})`. Puis, depuis `scripts/python` :

```
python rl_duel.py build --seed 777 --board MC1_67 \
  --p-units "tauMarksman,necroWarden,astraBullgryn" \
  --a-units "templAggressor,eldarRanger,orksNob" --state-file <ABSOLU unique>
# puis RPC unitAbilityStates { runnerId }
```

| # | mesure | résultat attendu | ce qu'un ÉCART trancherait |
|---|---|---|---|
| 1 | `configLayout.bcResolved` et les cinq `*Resolved` | tous `true` | un `false` ⇒ classe ou méthode non indexée : le capteur est INOPÉRANT et **rien d'autre n'est interprétable**. C'est le premier à lire |
| 2 | `configLayout.activeAbilitiesOff` / `idOff` / `baseUnitComponentIdOff` | `0xa0` / `0x10` / `0x10`, égaux aux `decompiled*` publiés à côté | un écart ⇒ la disposition a bougé depuis `rnca9r7q6c` : **confronter avant de lire les crans 3-7**, et corriger la case-doc, pas le code (les offsets sont déjà résolus par nom) |
| 3 | `configLayout.bcUnits` / `bcUnitsWithActives` / `elemClass` / `elemStride` / `unreadableActiveLists` | `175` / `125` / `ActiveAbilityType` / `4` / **`0`** | `bcUnits` très différent ⇒ ce n'est pas la BC attendue (runner construit d'une autre seed). `elemStride ≠ 4` ⇒ le capteur a refusé de lire : **c'est le comportement voulu**, et `elemClass` dit pourquoi. `unreadableActiveLists > 0` ⇒ des configurations dont le `List` n'a pas été décodé (`_items` nul sur une liste vide, typiquement) : elles sortent en `configActives: null`, donc **les compter avant de lire le cran 4**, jamais les prendre pour des `[]` |
| 4 | **`configActives` des 6 unités** | exactement les colonnes PRE de §7.2 : `[1048]`, `[1063]`, `[1152]`, `[1069]`, `[1005]`, `[1017]` | c'est LE cran. Il reproduit, par la lecture LIVE de `UnitConfiguration`, ce que §7.2 a lu du fichier envoyé. Un écart ⇒ soit le runner n'a pas reçu ce BC, soit `+0xa0` n'est pas ce champ : **ventiler unité par unité**, jamais moyenner |
| 5 | **`configActives` vs `actives` sur les mêmes 6 lignes** | `actives ∖ configActives` = exactement `{1128, 69, 69, 1076, 69, 69}`, et `configActives ∖ actives` = ∅ | c'est ce qui rend la garde NON tautologique. Si les deux listes sont ÉGALES, le capteur lit le composant et non la configuration ⇒ **ancrage à revoir, et surtout ne pas brancher la garde** |
| 6 | `normal_attack_already_present(configActives)` sur les 6 | `None` **6 fois** (aucune entrée régulière) ; le même appel sur `actives` rend non-`None` 6 fois | l'un ou l'autre qui dévie ⇒ `REGULAR_ATTACK_ABILITY_TYPES` a changé de contenu : re-dériver la table du `.cctor` avant toute conclusion |
| 7 | `configLayout.unmatchedEntities` + `configActives === null` sur un montage à INVOQUÉ (ajouter `orksRuntherd` côté joueur, jouer `GetEmRuntz`, relire) | `0` avant le cast ; **> 0** après, et les lignes des invoqués portent `configActives: null` (jamais `[]`) | `[]` sur un invoqué ⇒ le tri-état est cassé et le canal MENT : un invoqué serait lu « configuration sans actif », ce qui ferait appliquer le repli générique à une unité dont on n'a rien lu. `unmatchedEntities > 0` **sans** invoqué ⇒ la jointure par `Id` rate un cas à nommer |

**Après la fenêtre, et seulement après** : brancher `normal_attack_already_present` dans
`custom_normal_attack` sur le canal `configActives` (tri-état : `None` ⇒ voie non gardée,
comportement d'aujourd'hui), puis rejouer `test_419r1tr14r5r2r2_filter_new_list_live.py` **et** la
contre-épreuve de la voie ACTIVE (#565) — celle-là même que le branchement sur le canal POST
rendait inerte. Les deux doivent être VERTES ensemble ; si #565 redevient inerte, le branchement
s'est fait sur le mauvais canal.

⚠ **Ce qui restera NON COUVERT même après la fenêtre** : le second-ordre `AddDerivedAbilities`
(§6) — le capteur lit la configuration, pas ce que la fabrique dérive ensuite —, et le paramètre
`this.<+0x20>` du ctor du factory, toujours supposé constant.

## 7.5 LA FENÊTRE A TIRÉ (2026-08-04) — capteur CONFIRMÉ, garde BRANCHÉE, résidu FERMÉ

Confronté sur la session 3, build `rnca9r7q6c`, montage §7.4 (`--seed 777 --board MC1_67`, six
unités). **Crans 1 à 6 : conformes, à l'unité près. Cran 7 : RÉFUTÉ — sa prémisse était fausse.**

| # | attendu | obtenu |
|---|---|---|
| 1 | les cinq `*Resolved` à `true` | tous `true` |
| 2 | `activeAbilitiesOff`/`idOff`/`baseUnitComponentIdOff` = `0xa0`/`0x10`/`0x10`, égaux aux `decompiled*` | **exactement** (`160`/`16`/`16`) |
| 3 | `bcUnits` 175, `bcUnitsWithActives` 125, `elemClass` `ActiveAbilityType`, `elemStride` 4, `unreadableActiveLists` 0 | **exactement**, plus `configIdCollisions: []` |
| 4 | `configActives` = les colonnes PRE du §7.2 | `[1048]`, `[1063]`, `[1152]`, `[1069]`, `[1005]`, `[1017]` — **6/6 exact** |
| 5 | `actives ∖ configActives` = `{1128, 69, 69, 1076, 69, 69}` et `configActives ∖ actives` = ∅ | **exactement**, unité par unité |
| 6 | `normal_attack_already_present` : `None` 6× sur PRE, non-`None` 6× sur POST | **6/6 et 6/6** |
| 7 | un INVOQUÉ sort en `configActives: null`, `unmatchedEntities > 0` | **RÉFUTÉ** — voir ci-dessous |

**Cran 7, réfuté par la mesure.** La prémisse — « une unité invoquée naît d'une opération de spawn,
pas de `BC.Units` » — est **fausse pour ce build**. `orksRuntherd` caste `GetEmRuntz` (1045), deux
`orksGrot` apparaissent, et le capteur rend pour chacun `configId: "orksGrot"`,
`configActives: []`, `unmatchedEntities` toujours `0`. Contrôle offline : le seed BC porte bien une
entrée `orksGrot` avec `ActiveAbilities: []`. Le canal est donc **juste**, et ce `[]` est une VRAIE
mesure — exactement le cas que §7.3 disait devoir distinguer d'un `null` (50 des 175 entrées).

⇒ **la branche `null` du tri-état n'est exercée par AUCUN montage constructible sur ce seed** :
toute entité vient d'une `UnitConfiguration` de `BC.Units` (vérifié aussi pour `orksOrkBoys`, le
summon du Waaagh). C'est un résidu nommé, pas un vert.

**Le contrôle qui manquait, trouvé en cherchant : la MACHINE.** `ultraDreadnought` rend
`configActives = [1158, 1159]` et `actives = [1158, 1159]` — **PRE == POST exactement**, parce que
`IdunBattle.Entities.Factories.MachineFactory$$Build` n'appelle **jamais**
`UnitFactory$$AddNormalAttackAbility`. C'est le seul cas où la différence PRE/POST doit être VIDE,
et c'est ce qui prouve que la différence observée sur les six autres est bien l'écriture de la
fabrique — et non un artefact de lecture. Il remplace avantageusement le cran 7.

### 7.6 CE QUI EST BRANCHÉ, et la contre-épreuve qui le valide

La garde est branchée sur le canal PRE, sur le patron exact des trois voies voisines :

* parsing PARTAGÉ `engine.runner.snapshot.config_active_ability_names_by_unit` (foyer unique) ;
* seed des DEUX faces — `snapshot._load_config_active_abilities` (COMBAT),
  `playbook.scene._seed_measured_config_actives` (DÉCISION) + le re-seed des ARRIVANTS ;
* porté par `UnitContext.config_active_abilities`, en TRI-ÉTAT ;
* threadé aux trois postes d'appel de la cascade (`playbook/prediction/normal_attack.py`,
  `runner/abilities/targeting.py`, `runner/operations/damage.py`) ;
* **aucun RPC supplémentaire** : même payload que les trois seeds voisins.

`custom_normal_attack` appelle désormais `normal_attack_already_present(config_active_abilities)`
en QUATRIÈME position, après la branche TRAIT — le `else` du `else` du `else`, comme le natif.
**Pas de repli KIT** sur cette voie, et c'est délibéré : aucune des 18 attaques régulières n'est une
ability de catalogue, un repli n'aurait rien à lire.

**LA CONTRE-ÉPREUVE #565, VERBATIM.** C'est le test qui dit si le trou est fermé ou seulement
déplacé — branchée sur le canal POST, la garde le faisait tomber (`1 failed / 5 passed`) :

```
$ python -m pytest tests/engine/test_419r1tr14r5r2r2_filter_new_list_live.py \
                   tests/engine/test_419r1tr14r5r2_active_normal_attack_live.py -p no:randomly -q
..............                                                           [100%]
14 passed in 93.80s (0:01:33)
```

`test_la_contre_epreuve_mord_sur_la_preuve_et_seulement_la` est VERT **avec la garde branchée** :
voie active coupée, `astraBullgryn` porte `config.ActiveAbilities = [PoundThemToDust]`, or `1124`
n'est PAS une attaque régulière — la garde ne mord pas, le repli générique s'applique, et le bras
`preuve` retombe bien sur `Loki_NormalAttack`. La contre-épreuve garde donc son pouvoir de
falsification. Sur le canal POST elle l'avait perdu : `[1124, 1126]` contient `1126`, qui EST
régulière, donc la garde répondait juste **par le résultat qu'elle était censée prédire**.

**Non-régression rejouée après le branchement** : `test_419r1tr14r5_normal_attack_dispatch_live`
(6), `test_419r1tr14r5r2r1_trait_normal_attack_live` (6),
`test_419r1tr14r5_r1r4_normal_attack_table_live` (9), `test_419r1tr14_heavy_bolt_pistol_live` (6),
`test_419r1tr14r5r2r1r1_normal_attack_should_execute_live` (7) — **34 passed**, plus les 14
ci-dessus.

### 7.7 L'ENJEU, dit par un chiffre — ce que le branchement NE ferme pas

Le gisement de PRODUCTION reste **VIDE** : 0 des 175 unités du seed n'a d'attaque régulière dans
`BC.Units[].ActiveAbilities`, et aucune des 18 n'est attribuée par les 5 voies du gameconfig. Le
branchement **ne ferme donc aucun écart observable en jeu** — il rend la garde FALSIFIABLE, et
c'est le montage ÉCRIT (`probe_419r1tr14r5r2r2_filter_new_list`) qui l'exerce. C'est exactement
l'arbitrage de l'auteur de #575, et il avait raison de ne pas le brancher sur le canal POST : ce
qui a changé n'est pas le calcul du coût, c'est la disponibilité du bon substrat.

**Résidus après cette tranche** :

* **`-r2-r2-r1-r1`** — la branche `null` du tri-état de `configActives` n'est exercée par aucun
  montage : toutes les entités du seed ont leur `UnitConfiguration`. Elle reste une borne
  défensive non confrontée. Un porteur la produirait s'il existait une entité dont le
  `BaseUnitComponent.Id` n'est pas dans `BC.Units` — non trouvé sur ce build.
* **`-r2-r2-r2`** — `AddDerivedAbilities` (§6) et le paramètre `this.<+0x20>` du ctor du factory
  restent hors mesure, inchangés.
