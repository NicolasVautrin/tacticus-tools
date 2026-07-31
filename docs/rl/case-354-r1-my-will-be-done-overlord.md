# #354-r1 — `MyWillBeDoneOverlord` (face COMBAT) : porté et confronté live

`TriggeredAbilityType` **1556**, passif EFFECTIF de `necroOverlord` depuis le build `rnca9r7q6c`
(il a remplacé `MartialApotheosis`, cf. `case-354`). Porteur **HERO, au pool** — confrontable sans
injection. Face DÉCISION (`MyWillBeDoneOverlordPlaybook` / `…NonOwnerPlaybook`) hors périmètre (#271-r4).

Port : `scripts/python/engine/runner/operations/triggers/loki/my_will_be_done_overlord.py`
(+ `runner/abilities/behaviours/persistent_data.py`).
Garde : `tests/engine/runner/test_my_will_be_done_overlord_live.py` — **15 tests, tous verts**.

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

## 5. Résidus nommés

- `EffectType.MyWillBeDoneOverlord_ExtraDamage` (1581) est **posé** mais aucune classe d'effet ne le
  porte → effet présent sans stat-mod. Sa magnitude native vient de
  `DynamicStatModifierEffect$$GetDynamicStatModificationAmount` ; la variable `extraDmg` du gameconfig
  en est la source évidente mais n'est lue par aucune des deux fonctions RE — non porté plutôt qu'inventé.
- `MyWillBeDoneOverlord_FriendlyAttackedMarker` (1582) n'apparaît dans aucune des deux fonctions.
- `GetPersistentDataListAsEntities` n'est pas porté en **sélecteur** : le gate de purge est collapsé en
  « la liste est non vide ».
- Le terme `!TriggeringAbilityIs(1557 PhasalSubjugator) | IsUnitWithVisualId(…)` est **omis** : sur le
  vecteur porté (`On(0x29)`) le canal `TriggeringAbility` est vide, donc le terme est tautologique. Il
  devra être posé le jour où `PhasalSubjugator_TriggerPassiveAbility` (branche `Custom`) entre au registre.
- Quirk porté : le natif passe le **même** objet `GetTargetFriend()` aux quatre feuilles et au `If`,
  **sans `Cache`** (contrairement à `ExemplarOfHate`) — l'arbre est donc re-résolu contre l'état muté.
  Le port mirrore ; y ajouter un cache serait une divergence silencieuse.
