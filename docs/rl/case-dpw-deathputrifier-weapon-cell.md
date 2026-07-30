# case dpw — les BORNES de la cellule d'ARME de `deathPutrifier` en mêlée

**Critère (binaire)** : quelles sont les BORNES que le natif utilise pour l'attaque d'arme mêlée de
`deathPutrifier`, et d'où vient l'écart avec celles du port ?

| | bornes de la cellule d'arme (réduites) | largeur |
|---|---|---|
| **PORT** (avant) | `[2248, 3373]` | 1126 |
| **NATIF** | **`[2248, 3621]`** | **1374** |

Le BAS est **identique**, seul le HAUT diffère (+248). Le terme qui les sépare est
**l'armure du défenseur RÉEL** : `1496` côté port contre **`1197`** côté natif — l'écart est le
debuff `ContagionsOfNurgle_ArmorReduction1` (−20 % de `FixedArmor`) que le natif pose sur
`astraSmnKell` **au moment où il APPARAÎT dans l'aura Contagion**, et que le port ne posait pas.

---

## 0. Le symptôme, et pourquoi son signe alterne

Résidu relevé par R6-c (`case-r6c-amount-group-bounds.md` §4), montage `foul` (le porteur caste
`FoulInfusion` 1038 puis attaque en mêlée), board `MC1_67`, `--crit 0,0 --block-target 0,0
--hp-target 90000 --armor-target 6000` :

| seed | live | offline (avant) |
|---|---|---|
| 777 | 3219 | 2333 |
| 12345 | 3529 | 2649 |
| 314159 | 2923 | 2505 |
| 88 | **2750** | **3170** |

L'écart CHANGE DE SIGNE sur le seed 88. C'est la signature d'une divergence de **BORNES** et non
d'un facteur : le tirage est `lo + (r mod W)`, donc une largeur `W` différente change le RÉSIDU du
modulo, pas seulement l'échelle.

L'étage de réduction est
`idun.…StaticBattleRules.Damage$$GetDamageWithPiercing` =
`max(0, d − armure, d × perçage%)` — une fonction **affine par morceaux**. Baisser l'armure fait
basculer le HAUT de la cellule de la branche PERÇAGE vers la branche ARMURE **sans toucher le
BAS** : la cellule s'élargit par le haut. C'est exactement la forme observée.

C'est aussi pourquoi le GROUPE de coups additionnels du même coup (`FoulInfusion_ExtraHits`,
valeur brute 2792, profil Toxic) était **bit-exact malgré l'armure fausse** : `2792 − 1496` et
`2792 − 1197` sont tous deux inférieurs à `0.7 × 2792 = 1954.4`, donc la branche perçage l'emporte
des DEUX côtés et sa valeur est **armure-indépendante** (`1954` sur les 4 seeds). L'argument
« l'armure est juste puisque le groupe l'est » de `case-r6c` §4 ne tenait donc pas : ce montage-là
n'était pas discriminant sur l'armure.

---

## 1. Résolution de la cellule NATIVE — sans modèle

`probe_dpw_weapon_cell.py` rejoue la MÊME attaque offline sur le MÊME flux RNG (aligné : natif 3
tirages = port 3) et enregistre chaque `IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal`.
Le coup d'arme vaut `LO + (r mod W)` avec `r = genrand_int32() >> 1` — CONNU des deux côtés. On
BALAIE alors `(LO, W)` et on retient ceux qui reproduisent les 4 valeurs live **à l'unité** :

```
solutions A (cellule): [(2248, 3621, 1374)]   total 1
```

**Unique sur 4 flux.** Une cellule qui tient sur 4 résidus de modulo différents n'est pas un
scalaire fitté.

## 2. Décomposition par étage — ce qui est identique, ce qui diffère

Cellule d'arme du port (`damage_ops/normal.py::_reduced_bounds`), arguments capturés au replay :

```
value=3212  pierce=70  armor=1496  pct_list=[]  additive=0  extra_pierce=0  armor_pen=0
value=4818  pierce=70  armor=1496  ...
```

* `base` = `GetStat(Attack)` = **4015** (`combatSnapshot`) → `IdunBattle.Core.Services.
  DamagePrediction$$GetBaseDamageFix64` → pré-perçage `[3212, 4818]` (spread ±20 % symétrique,
  `IdunBattle.Core.Services.DamageCalculations$$CalculateDamageSpread` =
  `Round(base × DamageSpreadPercentage/100)`).
* Le BAS natif (2248) est `Round(0.7 × 3212)` : il **PINCE** `pierce = 70` et `base = 4015`. Un
  perçage différent ferait bouger le bas ; une base différente aussi. Les deux sont donc JUSTES.
* Aucun `%`-mod ni additif : le coup du groupe vaut exactement `Round(2792 × 0.7) = 1954`.
* `ExtraMaxDamage` (le SEUL terme natif qui gonfle le HAUT sans toucher le BAS,
  `GetBaseDamageFix64` : `max += FromInt(param_5)`) est **écarté par le décompilé** :
  `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` fait
  `if (!IsMeleeAttack(...)) extra = GetStat(attaquant, 0x19) ; else extra = 0`, et
  `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` rend VRAI dès que
  `GetAbilityAttackRangeType == 1` (l'arme unique de `deathPutrifier` est mêlée). `GetStat(0x19)`
  vaut 0 de toute façon (`combatSnapshot.extraMaxDamage`).

Reste **l'armure**. `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor`
(lu verbatim) :

```
armure = Math.Max( GetStat(defender, 0x10 = FixedArmor) − (int)<penetration>, 0 )
repeat n:  damage = GetDamageWithPiercing(damage, perçage, armure)
```

`4818 − 3621 = 1197` : la seule armure qui rend `[2248, 3621]` est **1197** (et elle est unique —
le bas exige `armure ≥ 964` pour rester sur la branche perçage).

## 3. Le défenseur RÉEL n'est pas la cible du message — et son armure change PENDANT l'attaque

Le montage est un 1v1 `deathPutrifier` vs `astraCreed`… mais `astraCreed` porte **`SwornProtector`**.
Roster live capté par le probe, AVANT / APRÈS l'attaque :

```
AVANT  77 astraCreed (6,8) armor 4800 eff[1071] | 79 deathPutrifier (5,8) eff[1070,1225,1074]
APRÈS  77 astraCreed (6,7) armor 4800 eff[1071] | 79 deathPutrifier (5,8) …
       99 astraSmnKell (6,8) armor 1197 eff[1062, 1071]
```

L'attaque réveille `On(PreUnitAbility = 0x2b)` → `SwornProtectorAbility` INVOQUE Kell puis
`SwornProtector_Protect` échange les positions ; la re-résolution de cible d'
`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` (#120bis) envoie alors les coups sur
**Kell**. Le port fait déjà tout ça (`cible attaquée = <Kell>` au replay).

Ce que le port ne faisait PAS : Kell **apparaît à 1 hex de `deathPutrifier`**, donc DANS son aura
Contagion — et le natif lui pose immédiatement le debuff d'armure : `1496 → 1197`
(= `1496 − round(1496 × 20/100)`). Côté port Kell gardait `1496`.

## 4. La RE du vecteur manquant

### 4.1 `IdunBattleLogic.Entities.Abilities.Active.Loki.ContagionsOfNurgle_AddEffectToNewUnit_Ability`

```
$$CreateTrigger =
    ( On(0x33 = UnitAdded) | On(0x2f = UnitResurrected) | On(0x2e = UnitRevived) )
    & op_LogicalNot( AreEqual(owner@0x148, target@0x178) )
    & AreEnemies(owner@0x148, target@0x178)

$$CreateBehaviour =
    sel = Cache( FromTrigger(target@0x178, op_LogicalNot(HasEffect(target@0x178, 0x42f, 0, 6))), 1 )
    AddEffect(0x42f = 1071, AbilityStateReference, owner@0x148, sel, <ZERO>)
  & AddEffect(0x430 = 1072, AbilityStateReference, owner@0x148, sel, <ZERO>)
```

Le frère `ContagionsOfNurgle_AddEffectInitially_Ability` (trigger `OnOwnerSpecificAbilityInit(0x431)`)
pose la MÊME paire sur `Enemies(owner)` à l'init de bataille.

### 4.2 `IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect`

`.ctor` = `AStatModifierEffect(AbilityOrEffect(0x431), 0, 0, 1, 1)` puis
`+0x488 = <clé de constante>`, `+0x48c = <min>`, `+0x490 = <max>`. Les DEUX seules constructions
(`IdunBattle.Core.Services.EffectsDatabase` `b__14_93` / `b__14_94`) :

⚠ Le parent est bien `AStatModifierEffect`, **pas** `ADynamicStatModifierEffect` (lecture corrigée
par `case-cvc` §1.1 : `ADynamicStatModifierEffect$$CreateTargetTrigger` utilise `+0x488` comme cache
de pointeur, or le ctor y écrit un `int`).

| effet | ctor | variable de trait | fenêtre active |
|---|---|---|---|
| `0x42f` = 1071 `_ArmorReduction1` | `(0x41, 1, 1)` | `contagionsOfNurgleArmorOneAura` = **−20** | exactement 1 aura |
| `0x430` = 1072 `_ArmorReduction2` | `(0x42, 2, 0x7fffffff)` | `contagionsOfNurgleArmorTwoOrMoreAuras` = **−40** | 2 auras ou plus |

```
$$GetStatModificationAmount = AbilityConfiguration.GetNumberConstant(config, this+0x488)
$$CreateActiveCondition =
      AmountIsEqualOrGreater( ContagionsOfNurgleAmount(EffectSource(effect@0x150), owner@0x148),
                              Get(this+0x48c) )
    & AmountIsEqualOrGreater( Get(this+0x490), ContagionsOfNurgleAmount(…) )
$$CalculateRange(unit) = s = GetStat(unit, 0xc = TurnsStarted) ; s > 2 ? (s > 4 ? 3 : 2) : 1
$$GetMaxRange = Direct(3)
```

`CalculateRange` était DÉJÀ portée (`abilities/deathguard.contagions_of_nurgle_range`, partagée avec
`SpawnPoxwalkersAbility`) — le port la réutilise, il ne la re-dérive pas.

## 5. Le port

* `engine/entities/effects/loki/status.py` : `ContagionsOfNurgleArmorReductionEffect`
  (`get_stat_modification_stat` = FixedArmor ; `applied_stat_mods` = le `ChangeStat` EAGER posé à
  l'application ; `reverted_stats` = son symétrique). Le delta est PLAT et pré-calculé
  `-round(FixedArmor × |pct| / 100)` — même convention que `ContaminatedUnitEffect`, l'autre
  `ADynamicStatModifierEffect` FixedArmor déjà porté.
  ⚠ **`applied_stat_mods` est OBLIGATOIRE** : `AddEffectOperation._apply_stat_mods` n'exécute QUE
  cette forme. La paire `get_stat_modification_*` seule ne sert qu'à l'ATTRIBUTION du delta au
  chargement (`stat_modifications_by_source`) — l'effet serait PRÉSENT mais n'entrerait jamais dans
  le `GetStat(FixedArmor)` du runner (mesuré : `defender_fixed_armor` rendait encore 1496 après la
  pose).
* `engine/runner/operations/triggers/loki/contagions_of_nurgle.py` : le vecteur, avec le compte
  d'auras (collapse de `ContagionsOfNurgleAmount`) et la sélection de variante par la fenêtre
  `[min, max]` de `CreateActiveCondition`.
* `engine/runner/operations/spawn.py` : `on_unit_added(state, unit_id)` — le foyer `On(UnitAdded)`
  du port, appelé par les **5** sites de création d'unité, APRÈS la pose de la position (les gates
  de portée en dépendent).

### Ce qui n'est PAS porté, et pourquoi

* **`AddEffectInitially`** (`OnOwnerSpecificAbilityInit`) : DÉLIBÉRÉMENT absent. Le runner ne rejoue
  pas l'init de bataille, il recharge un `combatSnapshot` où le debuff est DÉJÀ cuit dans
  `GetStat(FixedArmor)` (mesure : `astraCreed` 6000 → 4800) et l'effet 1071 déjà matérialisé par
  `decisionView.effects`. Le porter appliquerait le −20 % une seconde fois.
* ~~**La paire `AddEffect(1071) & AddEffect(1072)`** est collapsée à l'instance ACTIVE.~~
  **DÉFAIT par `case-cvc`** : le natif pose les DEUX, et le canal `decisionView { includeInactive:
  true }` les montre toutes deux sur chaque ennemi du porteur (mesure : `active: false` / `false`
  hors du disque). L'observable de ce montage-ci restait juste — le canal par DÉFAUT droppe les
  inactives — mais le collapse rendait la bascule 1071 ↔ 1072 structurellement impossible.
* ~~**Le cycle de vie** : l'effet n'est posé qu'à l'APPARITION…~~ — **CLOS par
  `case-cvc-contagions-lifecycle.md`**. Les trois manques étaient UN SEUL mécanisme : la fenêtre
  `[min, max]` de `CreateActiveCondition`, ré-évaluée à chaque `RefreshEffectsOperation`, sur deux
  instances coexistantes. Le port matérialise désormais la condition (`is_active`), et le driver
  `refresh_stat_modifier_effects` ÉCRIT le flag `EffectComponent.IsActive @+0x5c` (le producteur qui
  manquait) et applique/reverte la `ValueModification`. Mesuré des deux côtés, sans re-seed :
  sortie d'aura 1387 → 2312, croissance d'aura 2312 → 1850 sans que personne ne bouge.
* **`UnitResurrected` / `UnitRevived`** : branches non câblées (aucun montage).
* ~~**`ContagionsOfNurgleAmount`** est COLLAPSÉ…~~ — **RÉSOLU par `case-cvc` §1.2** :
  `ContagionsOfNurgleAmountFormula$$Calculate` DÉLÈGUE au slot `0x95` d'`IBattleQuery` =
  `BattleQuery$$GetInRangeAuraAmount`, déjà porté par case-224. Le port délègue au même mirror. Deux
  différences avec le collapse : comparateur **INCLUSIF** (mesuré live) et filtre d'appartenance
  « alliés de l'`EffectSource` », pas « ennemis de la cible ».

---

## 6. La mesure

```
python probe_dpw_weapon_cell.py --seeds 777,12345,314159,88          # confront live/offline
python probe_dpw_weapon_cell.py --seeds 777,12345,314159,88 --solve  # + résolution de la cellule
python probe_dpw_weapon_cell.py --carrier deathBlightlord --plain --seeds 777,12345,88   # généralisation
python -m pytest tests/engine/runner/test_contagions_of_nurgle_new_unit_live.py -q
```

### 6.a Montage principal — `deathPutrifier`, 4 seeds

| seed | live | port (après) | contrefactuel (vecteur neutralisé) |
|---|---|---|---|
| 777 | 3219 | **3219** | 2333 |
| 12345 | 3529 | **3529** | 2649 |
| 314159 | 2923 | **2923** | 2505 |
| 88 | 2750 | **2750** | 3170 |

Cellule port `[2248, 3621]` = cellule native résolue ; contrefactuel `[2248, 3373]`. Flux aligné
(natif 3 = port 3). Le groupe `#179` du même coup reste `1954` sur les 4 seeds (non-régression R6-c).
**4/4 port, 0/4 contrefactuel.**

### 6.b Généralisation — `deathBlightlord`, attaque mêlée NUE (aucun cast)

Autre porteur d'aura, autre arme (`Power`, perçage 40, **3 coups**), autre base (`Attack` 2609), et
plus de `FoulInfusion` du tout — SEUL l'étage « le summon apparaît dans l'aura » est commun.

| | cellule d'arme | live seed 88 |
|---|---|---|
| port (armure 1197) | `[890, 1934]` | `1725 / 1174 / 1834` — **tous dedans** |
| contrefactuel (armure 1496) | `[835, 1635]` | `1725` et `1834` **HORS cellule** |

Deux valeurs live au-dessus du plafond du contrefactuel : la réfutation est **indépendante du
tirage** (une cellule est un intervalle DUR), donc elle vaut même là où le flux n'est pas aligné —
et il ne l'est pas ici : **natif 5 tirages contre 3 au port** (résidu NEUF, cf. §7).

---

## 7. Ce qui n'est PAS couvert

* ~~**RÉSIDU NEUF, mesuré par la généralisation §6.b**~~ — **CLOS par
  `case-207-haze-of-corruption-target-finder.md`**. Sur le montage `deathBlightlord` (mêlée nue sur
  Creed, `SwornProtector` déclenché), le natif consommait **5** `genrand_int32` contre **3** au port,
  les deux tirages manquants EN AMONT des coups (les 3 valeurs live sortent de la MÊME cellule
  `[890, 1934]`, sur `raw[2..4]`). L'étage est
  `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility` :
  `On(0x2b = PreUnitAbility) & get_OwnerIsCaster` →
  `PickRandomly(Damageable(AdjacentEnemies(Self@0x148, 1, 3) & AdjacentFriends(Target@0x178, 1, 3)), 2)`
  = `min(|pool|, 2)` tirages AVANT tout coup. Deux tirages ici parce que `SwornProtector` fait
  ré-émettre `On(0x2b)` par la ré-entrée `ExecuteForReplacedTarget` (#120bis) et que le pool vaut
  **1 à chaque émission** : c'est **1 + 1**, pas un forfait de 2. ⚠ La piste « effets `1375` / `1147`
  sur le porteur » notée ici était FAUSSE (`TerminatorArmour_Visual` / `TerminatorArmour_ReduceDmg`,
  purement défensifs) ; et le montage `foul` de §6.a est aligné simplement parce que `deathPutrifier`
  ne porte pas `HazeOfCorruption`. Port désormais 5/5 sur 4 seeds, per-coup bit-exact.

* ~~La variante **`_ArmorReduction2` (−40 %, 2 auras ou plus)** n'a aucun montage~~ — **MESURÉE LIVE
  par `case-cvc` §4.2** : deux porteurs `ContagionsOfNurgle` dans le MÊME roster adverse
  (`rl_duel build --a-units deathTyphus,deathBlightlord,deathPutrifier`) suffisent, et les positions
  se pilotent. Résultat : `amount = 2` → 1072 actif, `FixedArmor` 2312 → **1387** (= −40 %), live et
  port identiques, sur deux boards.
* ~~Le **cycle de vie** de l'effet~~ — **CLOS**, cf. `case-cvc-contagions-lifecycle.md`.
* La face **PRÉDICTION** : `engine/services/…` lit l'armure du défenseur par le même
  `GetStat(FixedArmor)`, donc elle hérite du fix quand l'unité est SEEDÉE depuis un snapshot ; une
  unité spawnée EN COURS de simulation n'entre dans la prédiction que via l'ECS, donc par le même
  canal. Aucun montage de prédiction n'a été confronté ici.
* Le champ `armor` du dict rendu par `AttackDamageOperation.execute` est ÉCRASABLE par une
  sous-attaque de la cascade after-hit : ne PAS s'en servir comme mesure de l'armure du coup (piège
  rencontré ici — `defender_fixed_armor` est le foyer fiable).
