# #354-r1 — `MyWillBeDoneOverlord` (face COMBAT) : porté et confronté live

`TriggeredAbilityType` **1556**, passif EFFECTIF de `necroOverlord` depuis le build `rnca9r7q6c`
(il a remplacé `MartialApotheosis`, cf. `case-354`). Porteur **HERO, au pool** — confrontable sans
injection. Face DÉCISION (`MyWillBeDoneOverlordPlaybook` / `…NonOwnerPlaybook`) hors périmètre (#271-r4).

Port : `scripts/python/engine/runner/operations/triggers/loki/my_will_be_done_overlord.py`
(+ `runner/abilities/behaviours/persistent_data.py`,
+ `entities/effects/loki/my_will_be_done_overlord.py` pour l'effet 1581, #358).
Garde : `tests/engine/runner/test_my_will_be_done_overlord_live.py` — **21 tests, tous verts**
(15 pour la face COMBAT, +6 pour la magnitude de 1581).

## 1. Ce que le natif fait

`…MyWillBeDoneOverlordAbility$$CreateTrigger` =
`(On(0x12 TurnStart_EffectActivation) & AmountIsGreaterThanZero(GetPersistentDataListAsEntities))`
**|** `(On(0x29 UnitFinishedTurnNormally) & get_OwnerIsActor)`.

`…$$CreateBehaviour` se branche sur le `triggerType` : sur `0x12` → `ClearAllPersistentData` ; sinon
`If(GetTargetFriend, <override & attaque libre & reset & mémorisation>,
AddDynamicStatModifierEffectToOwner(0x62d, ATTACK, Sum(TurnsFromRounds(1), Direct(1))))`.

`…$$GetTargetFriend` = `First(SortByFormula(A.Otherwise(B).Otherwise(C).Otherwise(D),
StatAmount(it, ATTACK, CURRENT), ascending = 0))` sur
`Filter(AdjacentFriends(…), Mechanical & aUneCible & !déjàJoué)`, les quatre groupes étant
`(Necron, Hero)`, `(!Necron, Hero)`, `(Necron, !Hero)`, `(!Necron, !Hero)`.

**Tous les littéraux re-dérivés** de `data/symbols/rnca9r7q6c/frida/enums.tsv` :
`18 = TurnStart_EffectActivation`, `41 = UnitFinishedTurnNormally`, `5 = Mechanical`, `16 = Hero`,
`7 = Necrons`, `1556 = MyWillBeDoneOverlord`, `1296 = TemporaryStatOverride`,
`1581 = MyWillBeDoneOverlord_ExtraDamage`, `13 = maxDmg`, `74 = dmgPct`.

## 2. `persistent_data.py` n'est pas une abstraction inventée

Le doute était légitime (un « support de liste persistante » sans artefact). Il tombe : le composant
est **nommé dans le binaire** — `IdunBattle.Entities.Components.PersistentDataComponent`, avec
`PersistDataList` / `TryGetPersistDataList` / `ClearAllPersistentData` / `GetOrCreateAbilityData`, et
la clé vient de `IdunBattle.Core.AbilityOrEffect$$GetPersistentDataId`. Les trois primitives portées
mirrorent `AddToPersistentDataListBehaviour$$Execute`,
`IsInPersistentDataListTrigger$$ShouldTrigger` et `ClearPersistentDataBehaviour$$ExecuteClearAll`.
Le décompilé confirme le point le plus contre-intuitif du port : **`List.Add` inconditionnel**, aucune
déduplication — c'est le prédicat amont qui évite le doublon.

## 3. Deux défauts trouvés — dans la VALIDATION, pas dans le port

Le port lui-même s'est révélé fidèle (agreement live bit-exact). Les deux défauts étaient dans ce qui
était censé le prouver.

### 3.1 Le montage de la branche ELSE mesurait deux instants différents

Mesuré : `1581 live={79: 2} port={79: 3}`. Ce n'est **pas** une durée fausse. Le porteur était SEUL
de son camp, donc son `finish` faisait **basculer le tour** (`turn` 3 → 4, `toActivate` `[79]` → `[77]`)
et un tick décrémentait l'effet avant l'observation. Décomposition par étage :
`DSLFormulas$$.ctor` pose bien `+0x20 = Direct(1)`, `AddDynamicStatModifierEffectToOwner` a bien la
signature `(effectType, statType, turns, isHidden)` — les deux étages sont justes.

Preuve : avec un allié-tampon **exilé** à distance ≥ 3 (inéligible mais encore à activer), le tour ne
bascule plus (`turn` 3 → 3) et le live rend **`{79: 3}`**, la valeur exacte du port.

Le test ne pouvait pas le voir : il comparait `set(live_eff) == set(port_eff)`, donc les **porteurs**,
jamais les **durées**. Il compare désormais les dicts complets, vérifie `turn_before == turn_after`, et
ancre la valeur 3 = `Sum(TurnsFromRounds(1) = 2, Direct(1))`.

### 3.2 Trois contrefactuels sur quatre ne testaient rien

Rejoués tels quels, `ascending`, `notargets` et `nomechanical` ne changeaient **aucune** élection — les
tests rougissaient, à juste titre : c'est le montage M1 qui n'exerçait pas ces étages.

| mutation | pourquoi M1 la laisse inerte | montage qui l'exerce |
|---|---|---|
| `nogroups` | — (exercée par M1) | M1 |
| `ascending` | un seul membre par groupe → le sens du tri ne départage rien | **M5** |
| `notargets` | les deux alliés ont une cible | **M5** |
| `nomechanical` | les deux alliés sont `Mechanical` | **M6** |

**M5** — trois Necrons (tous groupe A) : `necroDestroyer` 400 et `necroWarden` 3000 avec cible ;
`necroSpyder` 9000 placé hors de portée. Le choix de `necroSpyder` est **contraint** : c'est le seul
Necron du pool dont `weapons` ne porte aucune entrée `Range` (mêlée pure). Les trois autres tirent à
2–3 hexes et gardent une cible depuis n'importe quel voisin du hub — le premier jet donnait ce rôle à
`necroDestroyer` (Range 2) et laissait `notargets` inerte.

**M6** — aucun allié Necron, donc groupe A vide : `admecDominus` (`Mechanical`, 400) contre
`astraCreed` (`Hero` nu, 3000). Nécessaire parce qu'**aucun Necron n'est non-`Mechanical`** : tant
qu'un Necron est éligible, le groupe A gagne et retirer le gate ne déplace rien.

Les quatre mutations divergent désormais.

## 4. Confrontation live

- **Agreement (M1)** : deux activations, `d_live == d_port` sur chaque unité (−259, −242).
- **Préférence de groupe** : `necroWarden` (Necron+Hero, ATK 400) est élu alors qu'`admecDominus`
  (Hero non-Necron, ATK 3000) est adjacent et éligible — la chaîne `Otherwise` prime sur le tri.
- **Purge** : le même allié rejoue à l'activation suivante (volet `On(0x12)`).
- **Branche ELSE** : effet 1581 sur le porteur, `remaining = 3` live et port.

Montage obligatoire : `necroOverlord:PassiveAbilities=[1556]`. Le seed BC porte encore l'**ancien**
passif (1045 `MartialApotheosis`) tandis que le port lit le gameconfig vivant — sans ce patch la mesure
compare deux SOURCES de kit, pas le port.

## 5. L'effet 1581 : où sa magnitude est lue (#358, résidu fermé)

`extraDmg` n'apparaît dans **aucune** fonction de la classe d'ability — ni les trois RE'ées ci-dessus,
ni le helper `…$$GetFriendAttackDamage`, qui ne sert que l'override d'attaque de la branche THEN
(`maxDmg`/`dmgPct`). Refuser d'inventer était donc juste : le consommateur est **ailleurs, et générique**.

L'effet **n'a aucune classe native dédiée**. Il est instancié par une lambda de la base d'effets :

    IdunBattle.Core.Services.EffectsDatabase.<>c$$<InitializeEffects>b__14_574
      -> new DynamicStatModifierEffect(AbilityType(0x614 = 1556), variableType = 8 = extraDmg,
                                       isNegative = 0, canBeImmuneTo = 0)

(les quatre littéraux sont **lus au désassembleur** — ghidra perd l'immédiat de l'`AbilityType`), et sa
magnitude sort du corps générique
`IdunBattle.Entities.Effects.DynamicStatModifierEffect$$GetDynamicStatModificationAmount` :
`ConfigVar(AbilityOrEffect(1556), EffectSource(Get(effect)), 8)`, **nié si `isNegative`** (le signe est un
champ de l'effet, `+0x4a4`). La STAT, elle, vient de l'entité-effet
(`AStatModifierEffect$$GetStatModificationStat` lit le composant écrit par le behaviour) = `0 = Attack`.

**Le lien lambda ↔ `EffectType` est mécanique, pas une inférence.** Dans `EffectsDatabase$$InitializeEffects`,
chaque enregistrement écrit le delegate dans le champ statique `<>9__14_N` juste avant
`Add(dict, effectType, delegate)` ; les statiques de `<>c` sont `[<>9, <>9__14_0, …]`, donc
`offset = 8 × (N+1)`. Mesuré : la fonction contient **511 appels `Add`**, tous vers la même cible, pour
**511 `EffectType` distincts** (aucun doublon), et **511 stores** de delegate — offsets tous multiples de
8, 511 indices `N` distincts. Les **14** lambdas qui appellent `DynamicStatModifierEffect$$.ctor` tombent
chacune sur un `EffectType` distinct (dont les trois du lot Votann déjà portés). Ici :
`offset 0x11f8` → `N = 574` → `EffectType 0x62d = 1581`.

Ce balayage est un outil, pas une lecture ponctuelle : **`scripts/python/probe_358_effects_database_registry.py`**
rend, pour n'importe quel `EffectType`, sa lambda, ses callees NOMMÉES et — si c'est bien un
`DynamicStatModifierEffect` — les quatre arguments du ctor. Il **se contrôle sur des cas déjà portés
ailleurs** : `1541 AugmentedAssault_ReduceArmor` → `(1221, 48 armorReduction, isNegative = 1)`,
`1485/1486 AncestralFortune_*` → `(1207, 65/62, isNegative = 0)` — identiques à ce que `votann.py` avait
établi sur un AUTRE build ; `1296 TemporaryStatOverride` → `StatOverrideEffect$$.ctor` et
`1583 Helspear_IgnoreArmor` → `Helspear_IgnoreArmorEffect$$.ctor`, donc **pas** des
`DynamicStatModifierEffect` (le probe le dit au lieu d'inventer des arguments — c'est exactement le
faux positif qu'une fenêtre de lecture non bornée avait produit au premier jet).

Port : `entities/effects/loki/my_will_be_done_overlord.py`, canal EAGER `applied_stat_mods` /
`reverted_stats` (mirror `AStatModifierEffect$$ApplyModification` part 5 / `$$RevertModification` part 6),
même moule que `votann.py`. `ADynamicStatModifierEffect$$RefreshValueInternal` n'est qu'un
revert-puis-apply : le `ConfigVar` ne dépendant que du niveau d'ability de la source, il rend la même
valeur — le canal eager est fidèle à l'observable.

**Confrontation live (montage M4, allié-tampon exilé) — trois régimes, `live == port` à chaque fois :**

| régime du porteur | `extraDmg[passif] × mult` | Δ ATTACK live | Δ ATTACK port |
|---|---|---|---|
| passif 50, mult 180 (nominal) | 499 × 1,8 = **898** | +898 | +898 |
| passif 50, mult **100** | **499** | +499 | +499 |
| passif **20**, actif 50, mult 180 | 47 × 1,8 = **85** | +85 | +85 |

`statModSources(attack)` rend `total = Δ`, **`residual = 0`**, et une source unique marquée
`self: false, sourceIsUnit: false` = l'**entité-effet** (le `modificationEntity = Entity(effect)` natif).
Le troisième régime est le discriminant du niveau : `PassiveAbilityLevel` bouge, `ActiveAbilityLevel` non
— un port qui lirait le niveau actif rendrait 898 là où le natif rend 85.

**Généralisation (montage M7)** : la branche ELSE atteinte par une VOIE D'ENTRÉE différente — l'unique
allié (`astraCreed`, `Hero` nu) est **adjacent** au porteur **et** a une cible à portée, donc seul le gate
`HasTrait(it, Mechanical)` l'écarte. Le buff y est bit-identique (+898, `residual = 0`, `turn` stable).
Les deux distances sont assertées par la garde : sans elles, M7 retomberait silencieusement sur M4.

## 5bis. Résidus nommés restants

- `MyWillBeDoneOverlord_FriendlyAttackedMarker` (1582) n'apparaît dans aucune des deux fonctions, **et
  n'a aucune entrée dans `EffectsDatabase$$InitializeEffects`** : sur les 511 `Add` balayés, 1581 et 1583
  y sont, 1582 **non** (le maximum enregistré est 1583). Aucune classe d'effet ne lui est donc associée
  côté natif non plus — à trancher séparément (hors périmètre #358).
- `GetPersistentDataListAsEntities` n'est pas porté en **sélecteur** : le gate de purge est collapsé en
  « la liste est non vide ».
- Le terme `!TriggeringAbilityIs(1557 PhasalSubjugator) | IsUnitWithVisualId(…)` est **omis** : sur le
  vecteur porté (`On(0x29)`) le canal `TriggeringAbility` est vide, donc le terme est tautologique. Il
  devra être posé le jour où `PhasalSubjugator_TriggerPassiveAbility` (branche `Custom`) entre au registre.
- Quirk porté : le natif passe le **même** objet `GetTargetFriend()` aux quatre feuilles et au `If`,
  **sans `Cache`** (contrairement à `ExemplarOfHate`) — l'arbre est donc re-résolu contre l'état muté.
  Le port mirrore ; y ajouter un cache serait une divergence silencieuse.
