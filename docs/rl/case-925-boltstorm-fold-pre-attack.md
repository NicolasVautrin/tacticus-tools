# `#925` — `Boltstorm` : les quatre faces, et le `On(PreAttack = 5)` que le FOLD n'aurait pas dû émettre

**Cas soumis** : « porte le passif `Boltstorm`, porteur `templAggressor` ».
**Ce que la RE a établi** : les quatre faces étaient **déjà portées**. Le travail réel est ailleurs —
un **écart de port** dans la face COMBAT, un **verdict DEAD** jamais gravé, et un **faux `manque 1`**
de l'audit dont la cause est structurelle.

---

## 1. L'inventaire des faces — établi au décompilé, pas au tableau

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BoltstormAbility` (base
`IdunBattle.Entities.Abilities.BaseTriggeredAbility`) n'expose **que deux méthodes** :
`$$GetAdditionalTargets` et `$$GetAllTargets` — deux **arbres de ciblage**, ni `$$CreateTrigger`
ni `$$CreateBehaviour`. Le passif agit en faisant **substituer l'attaque normale** de son porteur
(`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` →
`ActiveAbilityType.Boltstorm_NormalAttack` = 1128), et c'est cette attaque concrète qui porte le
corps.

| # | face | artefact natif | verdict |
|---|---|---|---|
| 1 | DÉCISION owner, ATTACK | `IdunBattle.AI.Playbook.Loki.BoltstormPlaybook$$CalculateAttackUtilityInStepsInternal` | **PORTÉE** (#446) — `engine/playbook/boltstorm.py` |
| 2 | DÉCISION owner, MOVE | `BoltstormPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` | **DEAD** — `yield Fix64.op_Implicit(0)` constant |
| 3 | DÉCISION, prédiction | `IdunBattleLogic.Entities.Abilities.Active.Loki.Boltstorm_NormalAttackAbility$$GetAdditionalDamagePrediction` (+ `$$PredictAttack`, gate `!IsMelee`) | **PORTÉE** (#446-r1) |
| 4 | COMBAT | `...Boltstorm_NormalAttackAbility$$ExecuteBoltstorm` (CLEAVE) + `$$GetCustomNormalAttackBehaviour` (FOLD primaire) | **PORTÉE** (#478, #419-r3) — **corrigée ici** |

Il n'y a **pas** de face « non-owner » : le playbook est chargé par ability du décideur, et
`Boltstorm_NormalAttackPlaybook` (`IdunBattle.AI.Playbook.Loki`) n'override **rien** — son `.ctor`
délègue à `ALoki_NormalAttackPlaybook<T>` avec le seul littéral `0x468` (= 1128).

**Face 2, DEAD, gravée** : `MoveNext` pose `Fix64.op_Implicit(0)` dans le champ de résultat de la
machine à états puis rend `true` une fois. Le port n'entre donc pas au registre
`TRIGGERED_MOVE_PLAYBOOKS`, et **son absence EST le comportement natif** — assertionné par
`tests/engine/test_925_boltstorm_faces_offline.py`, avec le cran qui rend l'assertion non vide (le
registre doit être PEUPLÉ, sinon un `not in` passerait sans rien prouver).

---

## 2. L'écart trouvé — le FOLD primaire ouvrait une attaque

### 2.1 Ce que le natif écrit

`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetAttackDamageBehaviour`
monte **UN SEUL** `IdunBattleLogic.Entities.DSLBehaviors$$Attack` autour des **trois** volets :

```
b1 = DSLBehaviors$$AttackDamage(caster@0x48, Target@0x60, <vslot 0x4d8>, Direct(weapon+0x10),
                                <vslot 0x4c8>, source, options)     # les coups d'ARME
b2 = <vslot 0x4e8>(abilityState)          # = $$GetCustomNormalAttackBehaviour = le FOLD
b  = AbilityBehaviour$$op_BitwiseAnd(b1, b2)
b3 = DSLBehaviors$$ExecuteAdditionalHitsWithDamageProfileType(...)
b  = AbilityBehaviour$$op_BitwiseAnd(b, b3)
return IdunBattleLogic.Entities.DSLBehaviors$$Attack(caster@0x48, target, b, source)
```

Le FOLD est donc une **feuille NUE** —
`Boltstorm_NormalAttackAbility$$GetCustomNormalAttackBehaviour` rend un
`DSLBehaviors$$If(DSLTriggers$$IsRangedPosition, <AttackDamage>, null)`, **aucun** `$$Attack`.
Or `StartAttack` (slot **58**) n'est poussé que par
`IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`, et
`IdunBattle.Operations.StartAttackOperation$$Execute` est le seul émetteur d'
`EvaluateAbilitiesImmediately(EventTriggerType.PreAttack = 5)` sur cette voie.

⇒ **un `Attack(...)` = un `StartAttack` = un `On(5)`**, pour la cible primaire.

Le **CLEAVE**, lui, appelle la **même feuille** (`$$GetAdditionalDamageBehaviour`) mais l'enveloppe
dans son **propre** `$$Attack` (`$$GetAdditionalTargetsAttackBehavior`) : il émet bien un `On(5)`
**par cible additionnelle**.

### 2.2 Ce que le port faisait

`AttackWithAttackDamage` prend `is_outside_attack=True` **par défaut** (#512-r2), et
`_attack_damage_leaf` — le foyer **partagé** par les deux volets — ne le passait pas. Les deux
volets étaient donc traités comme des feuilles emballées. **Un `On(5)` de trop par cast**, sur la
cible primaire. Mesure : **4 émissions contre 3 natives**.

Le trou avait été **écrit noir sur blanc à l'envers** dans
`engine/runner/operations/triggers/loki/suppressive_fire.py` : « un splash composé dans le
`Attack(...)` d'une autre attaque […] n'émet pas de `PreAttack` — **et le port ne lui en émet pas
non plus** ». La première moitié est juste, la seconde était fausse, et pour la raison exacte que
la phrase précédente énonce : le port **n'avait pas de canal** pour dire « feuille nue » avant
#512-r2, et #419-r3 (qui a créé le fold) est antérieur au câblage de ce canal.

### 2.3 Le correctif

`engine/runner/abilities/loki/additional_targets.py` :

* `fold_emits_pre_attack()` → `False` — **point de MUTATION** de module (même rôle que
  `fold_inherits_attack_state` pour #419-r3), avec le décompilé en docstring ;
* `_attack_damage_leaf(..., is_outside_attack=True)` — le drapeau devient un **argument**, parce que
  c'est très exactement ce qui **distingue** les deux consommateurs de la feuille partagée ;
* `primary_fold_tree` passe `fold_emits_pre_attack()` ; `cleave_tree` passe `True` **explicitement**
  (le défaut aurait suffi, l'écrire dit que c'est LU et non hérité).

---

## 3. Pourquoi l'écart ne se voyait pas — et ce qu'il a fallu ARMER

Les **deux seuls** consommateurs portés de l'event 5 :

| consommateur | effet | tirage `state.rng` ? |
|---|---|---|
| `SuppressiveFireAddEffectAbility` (trait `SuppressiveFire`, que `templAggressor` porte) | pose `Pinned` (1065) | **non** |
| `LetTheGalaxyBurnArmAbility` (trait `LetTheGalaxyBurn`, 5 héros Black Legion) | arme un flag persistant | **oui** — `Maybe(ConfigConst(0x2a))` |

Sur le porteur naturel, l'écart est donc **structurellement inerte** : la cible primaire a déjà reçu
`Pinned` de l'attaque primaire, et la seconde pose est refusée par le gate « déjà présent » d'
`IdunBattle.Operations.AddEffectOperation$$Execute`. Mesure : `probe_478 --regime boltstorm` est
**VERT avant comme après** le fix (natif = port : primaire 4214, cleave `necroWarden` 4372 /
`necroDestroyer` 7310, ventilation `[1804, 436, 456 | 474, 490, 554]`).

Le montage **greffe** donc le trait canal sur l'**entité** (`--unit-stat Traits=[...]`, qui réécrit
le seed BC, donc mord **des deux côtés**). Un `On(5)` de trop devient alors un **tirage** de trop,
qui déplace tout le flux.

### 3.1 La mesure (`probe_925_fold_pre_attack.py`)

```
traits MESURES sur l'entite : ['Hero', 'LetTheGalaxyBurn']
[etage 1] emissions On(PreAttack=5) : corrige 3 | mutant 4
[etage 2] NATIF   coups primaire [449, 436, 456, 542, 619, 513, 493]
          CORRIGE arme [449, 436, 456, 542] + fold [619, 513, 493]
[etage 3] MUTANT  arme [449, 436, 456, 542] + fold [490, 554, 642]
```

Le port corrigé égale la ventilation native **coup par coup** ; le mutant s'en écarte sur les trois
coups du fold. `a_mordu = True`.

### 3.2 Le verdict porte sur la VENTILATION, pas sur le total de PV — et c'est motivé

Ce montage réveille une divergence **tierce**, antérieure et étrangère au fold : le port attribue le
`+1 coup` de `LetTheGalaxyBurn` à la cible **PRIMAIRE** là où le natif l'attribue à une cible du
**CLEAVE**.

```
[rapport] PV primaire  natif 3508 (somme des coups 3508) | corrige 4134 (somme 3508)
          PV addts     natif {necroWarden: 1185, necroDestroyer: 1654}
                     | corrige {necroWarden: 1185, necroDestroyer: 1129}
          MUTANT primaire 4177 addts {necroWarden: 1173, necroDestroyer: 1594}
```

Deux crans autorisent à la sortir du verdict au lieu de la taire :

1. le **NATIF est cohérent** — `somme(coups) == delta de PV` (3508 = 3508), assertionné ; le port,
   lui, inflige à la primaire un coup que sa propre ventilation ne rapporte pas ;
2. l'écart **subsiste dans les DEUX régimes** du port (4134 et 4177), donc il n'est pas un effet du
   drapeau testé.

Résidu **`#925-r1`**.

### 3.3 GÉNÉRALISATION — le second porteur de fold, gate INVERSE

Le foyer corrigé (`_attack_damage_leaf`) est **partagé** : confronter le seul `Boltstorm` ne
distinguerait pas « le fix est juste » de « le fix est juste sur ce porteur ». `--regime rr` monte
`adeptMorvenn` / `RighteousRepugnance`, dont le fold gate `<DSLTriggers+0x18>` = **`IsMeleePosition`**
— l'**inverse** de `Boltstorm` — avec le même trait canal greffé :

```
[etage 1] emissions On(PreAttack=5) : corrige 2 | mutant 3
[etage 2] NATIF   coups primaire [1076, 1073, 964, 507, 563, 526]
          CORRIGE arme [1076, 1073, 964] + fold [507, 563, 526]
[etage 3] MUTANT  arme [1076, 1073, 964] + fold [557, 614, 572]
```

Les deux régimes sont paramétrés dans la garde jumelle (`case` / `case_rr`).

---

## 4. Le faux `manque 1` de `kit-coverage` — cause structurelle, pas approximation

`audit_kit_coverage.py` interrogeait **trois** registres pour un passif : `ABILITY_TRIGGERS`,
`ABILITY_INIT_OWNER_EFFECTS`, `EFFECT_CLASSES` (par nom). Un passif qui n'a **ni trigger ni
behaviour** — parce qu'il agit en substituant l'attaque normale — ne peut figurer dans **aucun** des
trois, **quel que soit l'état du port**. Ce n'était donc pas un faux positif d'approximation : c'était
une contre-vérité structurelle, et elle est ce qui a fait dispatcher ce cas.

**Quatrième voie ajoutée** : `engine.services.custom_normal_attack.CUSTOM_NORMAL_ATTACK_BY_PASSIVE`
— le foyer de la cascade `UnitFactory$$AddNormalAttackAbility`, keyé par le **nom du passif**, la
même clé que `passiveAbilities` du gameconfig.

Effet mesuré : **12** passifs cessent d'être comptés manquants, dont **3** touchent des unités
`lineup` — `Boltstorm` (`templAggressor`), `OptimizedGait` (`admecRuststalker`),
`RighteousRepugnance` (`adeptMorvenn`), tous trois portés et confrontés. Bilan de l'audit :
kits complets **80 → 83**, items manquants **48 → 45**.

---

## 5. Validation

| ce qui est joué | résultat |
|---|---|
| `probe_925_fold_pre_attack.py` (`--regime boltstorm` **et** `--regime rr`) | **OK** (3 étages + rapport) |
| `tests/engine/test_925_fold_pre_attack_live.py` | **13 passed** (6 tests × 2 porteurs + non-régression) |
| `tests/engine/test_925_boltstorm_faces_offline.py` | **7 passed** |
| `probe_478 --regime boltstorm` (avant ET après le fix) | **OK**, identique au natif |
| `tests/engine/test_478_cleave_live.py` (3 régimes, 4 contre-épreuves) | **13 passed** |
| `probe_419r3_fold_attack_state.py` | **OK**, `a_mordu = True` |
| `tests/engine/runner/test_suppressive_fire_live.py` + `test_415_suppressive_fire_pair_term_live.py` | **6 passed** |

---

## 6. Ce qui n'est PAS couvert

* **La seconde pose de `Pinned` n'a jamais été observée côté natif** — sur le montage, les trois
  cibles sont distinctes, donc le natif crée trois entités-effet pour trois `On(5)`. On ne mesure
  donc pas ce que le natif ferait d'un `On(5)` **répété sur la même cible** ; la preuve que le fold
  n'en émet pas reste la **LECTURE** (`$$GetAttackDamageBehaviour` : un seul `$$Attack`), le live
  n'en est que la confirmation.
* **Un seul board (`MC1_67`) et un seul seed (`4463111`)** — la géométrie du montage est dérivée
  (aucune constante de tuile), mais l'amplitude ne s'estime pas depuis un board.
* **Les autres cliquets de la banque `probe_457` n'ont pas été rejoués** — seule la sélection ciblée
  l'a été. En revanche `--measure-missing` a gravé l'empreinte des **8** fichiers qui en étaient
  dépourvus (7 antérieurs à cette tranche), et cette gravure a rendu **confrontable pour la première
  fois** la déclaration de `test_909_decision_actives_offline.py`, qui manquait `data/i2_en.json` :
  corrigé ici, dans la même PR.
* **Les autres feuilles NUES du port n'ont pas ce canal** — résidu `#925-r2` : le drapeau
  `is_outside_attack` ne pilote que la voie **BORNES** (`execute_ability_attack`) ; la voie
  **`amount`** (`execute_normal_like`) émet `On(5)` **inconditionnellement**. Conséquence mesurable :
  `IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$CreateTargetTriggerBehaviour`
  accumule **N** feuilles nues dans un seul `$$Attack` et le port en émettrait **N**.
* **La divergence `LetTheGalaxyBurn`** (`#925-r1`) est mesurée mais non instruite.
