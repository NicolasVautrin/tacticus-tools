# #433-r4-r1-r1 — `WallOfMirrors` (1186) portée, les deux faces confrontées LIVE

**PORTÉE** (`runner/abilities/loki/wall_of_mirrors.py`, arbre DSL + registre + effet 1398), face
DÉCISION confrontée par l'oracle 1 bit et face EXÉCUTION par la tuile d'atterrissage. **10 tests
offline** (6 mutations → 6 rouges, arbre restauré bit-exact) et **4 tests live**.

## 1. Ce que le décompile dit, et les trois points qu'il fallait trancher

| point | verdict, et comment il a été tranché |
|---|---|
| masque de ciblage | **`0x6004012` EXACTEMENT**. Le call-site `WallOfMirrorsAbility$$.ctor+0xae` vise la surcharge **PRIMITIVE à 7 paramètres** de `TargetingOptions$$.ctor` — tranchée par ses **xrefs entrantes**, pas à l'œil. Elle écrit `rules` **tel quel** dans `options+0x28` : aucun preset, donc aucun `|` à appliquer. Décomposition exhaustive, somme exacte : `TargetMatchesDynamicRule \| CasterHasNotMoved \| TargetIsEnemy \| AllowObscuredTarget`. `range` = `TargetingRange statics+0x48` = `RANGE_WHOLE_BOARD` ; `forceMeleeTarget = 1 = RangedBool.False`. |
| `AbilityAttackType` | **`2 = Others`** — 3e argument d'`AActiveAbility$$.ctor` (`this+0x68`). Littéral transcrit, jamais déduit du profil de dégât : l'arbre attaque pourtant (par `UseNormalAttack`), même lecture que Drachnyen en sens inverse. |
| slot `<klass+0x2b8>` du gate | **`IdunBattle.DSL.TargetsSelector$$Count`**, tranché MÉCANIQUEMENT par un SECOND call-site non ambigu : `NovaBoostAbility$$GetDynamicInvalidCasterReason` fait `iVar = <klass+0x2b8>(sel, entities); return (1 < iVar) ? 0 : 4` — on ne compare pas `> 1` un pointeur de liste. |

**Le `If` ne couvre QUE l'attaque**, pas le vol : `<DSLTriggers+0x20>` = `OwnerIsAlive`, au MÊME
emplacement que chez ses trois autres porteurs lus (`RammingSpeed`, `SkyStrike`,
`ExemplarOfTheKauyon`) — APRÈS le déplacement, AVANT l'attaque. `WallOfMirrorsAbility$$ExecuteBehaviour`
en est le **QUATRIÈME** porteur (la fiche de `entities/triggers.py::OwnerIsAlive` en listait trois).

**Le retrait de l'`Untargetable` cible `Owner@+0x30`, celui du `WallOfMirrors` cible `Caster@+0x48`** —
deux slots nativement distincts (`get_OwnerIsActor` = `AreEqual(+0x30, +0x40)` les sépare). Le port
les cite tels quels ; ils coïncident à l'exécution (`ctx.owner` non threadé pour une active).

## 2. La greffe — condition ÉTABLIE, pas supposée

Les deux porteurs sont hors-jeu et la **voie summon est FERMÉE**, re-mesurée ici :
`tauSmnStealthSuit` n'est cité que par `units.abilities.ATemptingTrap.constants.unitId`, et
`ATemptingTrap` n'apparaît dans **aucune** liste d'abilities d'unité du gameconfig (0 porteur sur les
5 voies dérivables). Reste la **greffe** (`case-92` §5bis), dont la condition est lue au décompile :

* `WallOfMirrorsPlaybook$$.ctor` = `ComparablePlaybook(this, 0x4a2)` → playbook chargé **PAR ID
  D'ABILITY** ;
* `$$GetUseProbability` = `Fix64.FromIntFraction(0x4b, 0x64)` = **0,75 CONSTANTE** (ne lit ni `unit`
  ni `actionTiles`) ;
* `$$EvaluateNonComparable` n'ouvre que des helpers **génériques** de `Playbook<T>`
  (`GetEligibleTargetsSelectable`, `CalculateUtilityFromDamageEvent`, `GetMovementUtility`) plus la
  constante `Fix64(1)` de son `.cctor` — **aucune lecture de stat ni de trait du caster**.

Greffon retenu : `tauCrisis` (T'au, pool, arme Pulse portée 2).

## 3. Ce que le LIVE a mesuré

**Face DÉCISION — l'oracle 1 bit.** `abilityReason` rend le masque `TargetingRule` rompu, cible par
cible ; les DEUX conjoints sont exercés SÉPARÉMENT, dans le même état :

| Markerlight | `GetPossibleTiles()` | natif | port |
|---|---|---|---|
| ✓ | 9 tuiles | `0x0` | `0x0` |
| ✗ | 5 tuiles | `0x2` | `0x2` |
| ✓ | **0** (anneau entièrement occupé, cible poussée au coin `(0,0)`) | `0x2` | `0x2` |

⚠ **`abilityTargets` ne convient PAS** : il n'énumère que les unités du `toActivate` courant (mesuré :
`unitCount = 0` pour un caster hors tour), donc son zéro serait un zéro de HARNAIS. C'est
`abilityReason` qui porte l'oracle.

**Face EXÉCUTION — la tuile d'atterrissage**, replay OFFLINE sur la MÊME capture et le MÊME
`state.rng` (`dumpRng`) : natif **(0,3)** == port **(0,3)**, et la tuile appartient bien à
`GetPossibleTiles()` (9 candidates). `First(SortTilesByUtility(…, 7))` est déterministe (zéro
tirage) — l'égalité est donc une mesure forte de tout l'arbre.

**Dégât, deux régimes** (même capture, même rng, cible qui SURVIT — `--hp-target 400000`) :

| régime | natif | port | verdict |
|---|---|---|---|
| armure **0** | 18653 | 18653 | accord exact — mais **DÉGÉNÉRÉ sur le canal perçage** (mesuré : ON == OFF) |
| armure **4000** | **7669** | **6296** | **écart +1373 (+21,8 %)**, cf. §4 |
| attaque normale NUE, armure 4000 | 2953 | 2953 | accord exact → **l'écart n'est pas antérieur** |

## 4. Résidus NOMMÉS

* **`#433-r4-r1-r1-r1` — la MAGNITUDE du bonus de perçage diverge sous armure.**
  `WallOfMirrorsEffect$$CreatePiercingBonusForAttack` = `ForAddition(get_OwnerIsCaster,
  DSLFormulas.Get(GetNumberConstant(config@0x60, 0x40)))` — UN SEUL gate. `0x40 = extraPierce = 15`,
  tranché par élimination (la config 1186 n'a que `range` (0x16, ancré) et `extraPierce`).
  Le port **MORD** — contre-épreuve interne, même état + même rng : bonus ON = 6296, OFF = 5027
  (+1269) — mais le natif rend 7669, soit **+1373 de plus**. L'étage est LOCALISÉ (l'attaque normale
  nue est bit-exacte au même régime d'armure), la magnitude ne l'est pas. **Non fitté**
  (doctrine : jamais ajuster un scalaire). Deux pistes non départagées : (a) le natif applique le
  bonus AUSSI aux coups de `CyclicIonBlaster_AdditionalHits` (3203 de dégât dans ce montage) là où le
  port le borne aux coups principaux ; (b) `DSLFormulas$$Get` n'est pas un `Const`.
  Retirer l'effet ÉLOIGNE (écart 2642) : il est gardé.
* **`#433-r4-r1-r1-r2` — la LoS de `IsObscured` hérite des bornes v1 de `Unobscured`** :
  distance 1 jamais obscurcie, distance EXACTEMENT 2 gatée par l'élévation, distance ≥ 3 et MURS non
  modélisés → passe-tout. L'anneau de 1186 vaut exactement 2, donc le filtre y est ACTIF (garde
  offline dédiée), mais un `range` de config différent le rendrait muet.
* **`#433-r4-r1-r2` (hérité) — le bras de rattrapage de `FilterTilesIfCanAttackTargetTileFrom` reste
  STRUCTURELLEMENT MORT chez ce consommateur** tant que la cible est mono-hex : anneau à distance
  exacte 2 ⇒ aucune candidate n'est adjacente à la tuile cible. Confirmé sur les 9 candidates du
  montage. Le régime multi-hex reste NON INSTRUIT.
* **`ExecuteBehaviour` : la branche `Untargetable`** (pose avant le vol / retrait après) n'a **aucun
  observable mesuré** — le port l'exécute (`emitted` le liste), mais aucun overwatch n'a été déclenché
  par le vol dans les montages joués.

## 5. Ce qui a bougé HORS de l'ability

* `entities/triggers.py::IsObscured` — nœud NEUF, mirror de
  `IsObscuredAbilityTrigger$$ShouldTrigger` (ET sur le PRODUIT des deux sélecteurs, **vacuement
  vrai**), plus le helper `_items` (variante de `dsl.base._units_of` qui accepte un scalaire du
  domaine TUILE — `_units_of` LÈVE sur un id de tuile nu, ce que rend `ActiveTarget()` sous un
  `Filter`).
* `entities/selectors/units.py::Filter` — pose désormais **`active_target` en plus de `subject`** :
  le slot natif lié par `FromTriggerSelector` est `ability+0x180` = **ActiveTarget**, et un arbre qui
  le cite sous son nom lisait jusqu'ici le liant ENGLOBANT. Aucun prédicat existant ne lit
  `active_target` sous un `Filter` — le changement est inerte pour eux.
* `entities/effects/loki/wall_of_mirrors.py::WallOfMirrorsEffect` — effet **1398**, canal PERÇAGE
  (cf. résidu r1).

## 6. Relevé de validation (2026-08-04)

* `tests/engine/test_433_r4_r1_r1_wall_of_mirrors_offline.py` — **10 passed**.
* Mutations : anneau sans soustraction (**5 failed**), `CanAddUnit` retiré (**2 failed**), LoS retirée
  (**1 failed**), dernier étage retiré (**1 failed**), masque faux (**1 failed**),
  `ABILITY_ATTACK_TYPE` retiré (**1 failed**) — arbre restauré, sha256 identiques.
* `tests/engine/test_433_r4_r1_r1_wall_of_mirrors_live.py` — **4 passed** (26,6 s).
* Régression ciblée : `test_433_r4_r1_filter_tiles_can_attack_offline.py` (le nœud partagé) et
  `test_effect_markerlight`-adjacents, cf. le corps de la PR.
