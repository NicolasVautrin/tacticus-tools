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
`offset = 8 × (N+1)`. Mesuré (chiffres **corrigés par #364**, cf. §5ter) : la fonction contient
**607 appels `Add`** pour **607 `EffectType` distincts** (aucun doublon) et **607 stores** de delegate —
offsets tous multiples de 8, 607 indices `N` distincts, et exactement **607** fabriques
`<>9__14_N` présentes en binaire, ce qui **ferme** l'inventaire. Les **14** lambdas qui appellent
`DynamicStatModifierEffect$$.ctor` tombent chacune sur un `EffectType` distinct (dont les trois du lot
Votann déjà portés) — compte re-dérivé sous l'inventaire complet, inchangé. Ici :
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

## 6. L'effet 1582 : INERTIE DÉMONTRÉE (#364, résidu fermé)

**Verdict : `1582 MyWillBeDoneOverlord_FriendlyAttackedMarker` est déclaré par l'enum et n'existe
nulle part ailleurs.** Ce n'est pas un port manquant : il n'y a rien à porter. La docstring du port
qui le mentionnait en résidu était donc fidèle — mais elle l'affirmait sans l'avoir établi.

**L'identifiant d'abord.** `data/symbols/rnca9r7q6c/frida/enums.tsv` :
`1581 = MyWillBeDoneOverlord_ExtraDamage`, `1582 = MyWillBeDoneOverlord_FriendlyAttackedMarker`,
`1583 = Helspear_IgnoreArmor`. Contrôle nécessaire — ce build a déjà renuméroté deux membres en
silence (1563/1564, #318), et une chasse menée sur le mauvais identifiant rendrait un « absent »
parfaitement faux. La garde ré-assertent le nom, pas seulement la valeur.

**Les trois voies par lesquelles un `EffectType` peut vivre, toutes trois fermées :**

| voie | mesure | résultat |
|---|---|---|
| fabrique dans `EffectsDatabase$$InitializeEffects` | 607 `Add`, inventaire **fermé** | **absent** (1581 et 1583 y sont) |
| immédiat chargé par du code | segment de code entier, encodages **32 et 16 bits** | **0** instruction `IdunBattle` |
| tableau statique en données | sections hors code | **50** occurrences — contre **70** pour 1581 et **47** pour 1583 |

La troisième ligne est un **contrôle négatif**, pas une preuve : 1582 est un entier banal. Ce qui
compte est que sa présence en données soit du même ordre que celle de ses voisins **vivants** — les
hits voisins forment des triplets de 12 octets `(index, valeur, 0xFFFFFFFF)` où 1581, 1582 et 1583
figurent au même titre : c'est de la métadonnée IL2CPP, pas une voie de pose.

Les deux seules instructions du binaire qui chargent `0x62e` sont `I2.Loc.ArabicTable$$.ctor` et
`System.Globalization.HebrewCalendar$$GetDayOfYear` — des coïncidences numériques hors du jeu.
Le **gameconfig** n'est pas une quatrième voie : il ne nomme aucun `EffectType` créateur d'effet —
`MyWillBeDoneOverlord_ExtraDamage` (1581), pourtant vivant et posé, n'y figure pas davantage.

**Ce que « inerte » veut dire exactement** — lu dans `IdunBattle.Core.Services.EffectsDatabase$$GetEffect` :
un `EffectType` sans fabrique **ne lève pas**. Le cache (`this+0x50`) rate, le `TryGetValue` sur le
dictionnaire de fabriques (`this+0x48`) rate à son tour, le natif formate `System.Enum$$ToString` de
la clé dans un message de log et construit un `IdunBattle.Entities.Effects.NoneEffect`. La
dégradation native est **définie** et silencieuse côté gameplay. « Inerte » = « même posé, il ne
ferait rien » — pas « impossible à poser ».

**Ce n'est pas une singularité, c'est un régime.** Le build déclare **629** membres d'`EffectType`,
**607** ont une fabrique, **22** n'en ont pas : deux sentinelles (`None`, `STRIPPED`), sept
emplacements morts nommés comme tels (`UNUSED_2/6/10/13`, `NotUsed`, `Not_Used`, `Unused`), trois
mocks de test, `Boss8_Mini_2_2`, des reliquats de mécaniques retirées (`Duel_Taunt`, `ShadeAttack_*`,
`Cursed`, `MegaShooterMisfire_ExtraDmg`, `WeaversOfFate`, `ArcaneShield`, `InfernalCannon`) — et 1582.
Dans cette cohorte, 1582 se range avec les plus morts : `1353 NotUsed` et `1373 UNUSED_13` sont, avec
lui, les seuls dont **aucune** fonction `IdunBattle` ne charge la valeur.

**Le porteur est confrontable, et il a déjà été confronté.** `MyWillBeDoneOverlord` (1556) est un
passif de `necroOverlord` — **HERO, dans le pool** (rank 17, 97 unités régulières spawnables) ; les
cinq autres porteurs (`necroBossOverlord`, `necroNpcOverlord`, …) sont npc, aucun MoW, aucun summon,
aucune relique. L'inertie de 1582 n'est donc **pas** un défaut d'accès : elle est établie sur un
vecteur que §4 a effectivement joué en live.

Garde : `scripts/python/tests/engine/test_effect_1582_inertia_binary.py` (offline pure, ~2 s) — un
test par voie, plus la fermeture de l'inventaire, le typage des clés, l'anti-zéro-menteur sur
1581/1583 et le contexte de cohorte. Les quatre ont été vues **rouges** par mutation adversariale.
Si un futur build donne une fabrique à 1582, ou si du code se met à le poser, elle rougit — et c'est
le signal qu'il faut le PORTER.

### 6.1 Ce que #364 a corrigé dans l'outil, et pourquoi ça dépasse 1582

L'inventaire de #358 était **incomplet, et son incomplétude était invisible**. Ses deux balayages
partageaient l'octet-clé `4c 8b c6` (`mov r8, rsi`) : ils n'étaient pas indépendants, et leur accord
parfait (511 == 511) était un accord sur la **même cécité**.

Relu au désassembleur, `InitializeEffects` fait **607** enregistrements. Les **96** manquants
n'appellent pas le thunk mais `Dictionary<,>$$Add` **directement**, et passent leur clé **par
adresse** — le dictionnaire gshared ayant une clé `ValueType`, IL2CPP l'écrit dans un slot de pile :

    mov qword ptr [rcx + 0x20], rsi     ; store du delegate au statique <>9__14_3
    lea rdx, [rsp + 0x28]               ; arg2 = &slot
    mov r8, rsi                         ; arg3 = le delegate
    mov dword ptr [rsp + 0x28], 5       ; le LITTERAL, en pile   (5 = Fire)
    call Dictionary<,>$$Add             ; appel DIRECT

Après `mov r8, rsi`, l'octet suivant est `C7` (`mov mem, imm32`) et non `BA` (`mov edx, imm32`) —
d'où la cécité. Conséquence : **96 `EffectType` étaient rapportés « NON ENREGISTRÉ → aucune classe
d'effet native »**, dont `5 Fire`, `17 Ice`, `31 StatModifier`, `1004 MightOfHeroes_ExtraHits`,
`1099 Waaagh_ExtraMovement`, `1244 Contaminated` — tous parfaitement vivants. C'est exactement le
faux négatif que le CLAUDE.md interdit de traiter comme une preuve de mort, et il était produit par
notre propre outillage.

Ce qui l'a fermé n'est pas un troisième motif d'octets mais une **source indépendante** : le nombre
de fabriques `<>9__14_N` présentes dans le binaire (**607**) doit égaler le nombre d'`Add` vus. Un
balayage partiel casse cette égalité ; c'est ce que `test_registry_inventory_is_closed` assertent, et
la mutation qui ré-introduit la cécité rend le message chiffré `96 appel(s) d'ajout sur 607 n'ont
PAS de clé résolue`. Compter « enregistrés + orphelins == membres » n'aurait rien prouvé : les
orphelins étant dérivés des enregistrés, l'égalité est vraie par construction — y compris avec 96
sites manquants.

`probe_364.registry` est désormais l'implémentation **unique** de la loi ; `probe_358` la consomme.

## 7. Résidus nommés restants

- `GetPersistentDataListAsEntities` n'est pas porté en **sélecteur** : le gate de purge est collapsé en
  « la liste est non vide ».
- Le terme `!TriggeringAbilityIs(1557 PhasalSubjugator) | IsUnitWithVisualId(…)` est **omis** : sur le
  vecteur porté (`On(0x29)`) le canal `TriggeringAbility` est vide, donc le terme est tautologique. Il
  devra être posé le jour où `PhasalSubjugator_TriggerPassiveAbility` (branche `Custom`) entre au registre.
- Quirk porté : le natif passe le **même** objet `GetTargetFriend()` aux quatre feuilles et au `If`,
  **sans `Cache`** (contrairement à `ExemplarOfHate`) — l'arbre est donc re-résolu contre l'état muté.
  Le port mirrore ; y ajouter un cache serait une divergence silencieuse.
