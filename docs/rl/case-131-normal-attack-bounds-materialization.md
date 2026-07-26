# case-131 — Divergence de l'ATTAQUE NORMALE quand les bornes de degat sont REDUITES

## 1. Le critere

> **A quel ETAGE, exactement, le port diverge-t-il du natif sur une attaque normale dont les
> bornes de degat sont reduites ?**

**Reponse : l'etage de MATERIALISATION des cellules min/max reduites.** Le natif ARRONDIT
(`FixMath.NET.Fix64$$Round(·, AwayFromZero)`) ; le port TRONQUAIT (`FixMath.NET.Fix64$$op_Explicit`
= `raw >> 32`). Les ENTREES de cet etage (stat Attack, spread, percage, armure, modifiers, nombre
de coups, flux RNG) concordent — c'est prouve ci-dessous, tirage brut a l'appui — et seule sa
SORTIE diverge, d'exactement **+1 sur une borne**. Comme le tirage est
`Next(min, max+1)` = `min + raw % (max - min + 1)`, ce +1 change la **largeur du modulo** : la
valeur tiree n'est pas decalee de 1, elle est completement differente.

Ce n'est **pas** un probleme d'ORDRE `reduce-then-roll` / `roll-then-reduce` : l'ordre du port
etait deja juste (et le balayage exhaustif de 1025 combinaisons de case-117 §5ter, qui ne trouvait
rien, le confirmait a contrario — il cherchait dans le mauvais espace).

## 2. La chaine native (symboles VERBATIM)

```
IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$ExecuteNormalAttack
  -> ...ALoki_NormalAttackAbility$$GetAttackDamageBehaviour
  -> IdunBattleLogic.Entities.DSLFactory$$AttackDamage            (noeud degat =
       IdunBattleLogic.Entities.DSLFactory$$NormalAttackDamage = StatAmountFormula(Attack))
  -> IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$GetDamage
       -> IdunBattle.Core.HitDamage$$.ctor(min, max)              (struct {Min@+0, Max@+4})
  -> IdunBattle.Operations.AttackDamageOperation$$Execute
       -> IdunBattle.Operations.AttackDamageOperation$$GetAttackHits
       -> IdunBattle.Operations.AttackDamageOperation$$ExecuteHits   (boucle des coups)
            -> IdunBattle.Operations.AttackDamageOperation$$ExecuteHit  (LE per-coup)
```

`ExecuteHit`, dans l'ordre lu au decompile :

| # | appel | consommation RNG | role |
|---|---|---|---|
| 1 | `IdunBattle.Core.HitDamage$$GetDamage` | 0 si `Min == Max` | attaque NORMALE : struct DEGENERE -> 0 tirage |
| 2 | slot 0xa `IdunBattle.Core.Services.DamagePrediction$$RollCritical` | 1 si `cc >= 1` | crit du coup |
| 3 | **slot 4 `IdunBattle.Core.Services.DamagePrediction$$PredictAttack`** | 0 | **produit les CELLULES min/max REDUITES** |
| 4 | slot 8 `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` | **1, TOUJOURS** | `Next(min, max+1)` = LA valeur du coup |
| 5 | sous-op `0x42` | 0..N | split bouclier/armure-pool + block |

`RandomlyResolveMinMaxDamage(this, minMax)` lit `minMax+0x8` (min) et `minMax+0xc` (max) et appelle
`IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal(min, max + 1)` — mirror exact du port.

### Le point structurel : les cellules du COMBAT viennent de la PREDICTION

`PredictAttack` (les deux surcharges) est un **cache** : son unique corps de calcul est
`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` (xrefs : seuls
`DamagePrediction.<>c__DisplayClass12_0$$<PredictAttack>b__0` et `...DisplayClass13_0$$...` l'appellent
— ce sont les lambdas-fabriques du cache).

Et `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` (le reducteur
percage/armure/modifiers) n'a que **DEUX** appelants dans tout le binaire :
`IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` (scalaire, cellule degeneree) et
`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` (deux appels : borne min, borne max).
Une attaque normale a une cellule de largeur > 1 (elle tire dedans) -> **ses cellules ne peuvent
venir que de `PredictAttackRaw`**.

**Consequence : le combat de l'attaque normale et la prediction IA appellent LA MEME fonction
native.** Le port en avait DEUX implementations (`damage_ops.execute::_reduced_bounds` cote combat,
`services/damage_prediction.predict_attack_raw` cote prediction) — divergence STRUCTURELLE de type
« check-own-port » (1 natif -> N ports), dont la materialisation n'etait qu'un symptome.

### L'etage fautif, lu au decompile

`CalculateBaseDamageWithAllModifiers(this, baseDamage, ..., attackerMods, defenderMods, ...)` :

1. `Fix64.FromInt(baseDamage)` ;
2. extraPierce / armorPenetration extraits des deux `Nullable<DamageModifiers>` ;
3. `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor` (percage + armure) ;
4. `if attackerMods.HasValue` : slot 0x11 (`ApplyCappedModifiers`) ; idem defenseur ;
5. `if attackerMods.HasValue` : **slot 0x10 ->
   `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers`** ; idem defenseur ;
6. override defenseur eventuel.

`CalculateBaseDamageWithModifiers(this, damage, multiplier)` (decompile integral, court) :

```
v = FixMath.NET.Fix64$$op_Multiply(damage, multiplier)
if v <= Fix64.Zero : return Fix64.Zero
if v >  Fix64.Zero and v < Fix64.One : return Fix64.One
return FixMath.NET.Fix64$$Round(v, mode 1 = AwayFromZero)
```

-> **l'arrondi est INCONDITIONNEL des qu'un `Nullable<DamageModifiers>` HasValue** (attaquant OU
defenseur). Le port cote combat sortait ce Fix64 par `apply_all_modifiers(...)` sans
`round_materialize`, c'est-a-dire par `to_int` = `op_Explicit` = **floor**.

## 3. Le tableau par etage (live vs offline)

Montage (a) = celui de case-117 §5ter, reproduit a l'identique : board `MC1_67`, seed 31337,
`darkaAzrael` buffe par `Hailstrike` (percage 65 -> 80) tirant au Plasma a portee 2 sur
`astraBullgryn` (FixedArmor 3513, PV enormes). Probe : `scripts/python/probe_131_normal_attack_bounds.py`.

| etage | entree | sortie LIVE | sortie OFFLINE | verdict |
|---|---|---|---|---|
| stat Attack (`StatAmountFormula`) | — | 2813 | 2813 | **concordent** (le controle sans buff de case-117 est bit-exact : live 1798 == offline 1798) |
| spread (`DamageCalculations$$CalculateDamageSpread`) | 2813, 20 % | 563 -> [2250, 3376] | idem | **concordent** |
| percage (`DamagePrediction$$GetAttackPiercingDamageRatio`) | Plasma 65 + bonus 15 | 80 | 80 | **concordent** (envelope case-117 §5bis, + le cas armure-0 bit-exact) |
| armure (`GetStat(16)`) | — | 3513 | 3513 | **concordent** |
| crit (`RollCritical`) | cc = 0 | pas de crit | `crits=[False]` | **concordent** (0 tirage) |
| **cellules (`PredictAttackRaw` -> `CBDWAM` -> `CalculateBaseDamageWithModifiers`)** | 2250 / 3376 x fix(0.80) = 1800.0000001 / **2700.8000000** | **[1800, 2701]** | **[1800, 2700]** | **DIVERGENT — c'est l'etage** |
| tirage (`RandomlyResolveMinMaxDamage`) | meme `genrand>>1` = 1550165595 | 1800 + r%902 = **1921** | 1800 + r%901 = **2301** | consequence mecanique du precedent |

Le tirage brut est **identique** dans les deux modeles (verifie et imprime par le probe) : il n'y a
ni desynchronisation ni tirage brule. Seule la largeur du modulo (902 vs 901) change.

### Mesure (a) — 6 tirs, montage case-117 §5ter

Les valeurs LIVE reproduisent exactement la serie documentee en §5bis/§5ter.

| tir | `genrand>>1` | LIVE | cellules TRONQUEES [1800,2700] | cellules ARRONDIES [1800,2701] |
|---|---|---|---|---|
| 0 | 1550165595 | **1921** | 2301 | **1921** |
| 1 | 620728158 | **2422** | 2226 | **2422** |
| 2 | 798042694 | **2700** | 2665 | **2700** |
| 3 | 1871319181 | **2015** | 2546 | **2015** |
| 4 | 470082455 | **2445** | 1921 | **2445** |
| 5 | 1425479661 | **2153** | 2153 | **2153** |

**arrondi = live 6/6 ; troncature = live 1/6** (le tir 5 est une coincidence : `r%901 == r%902`).
Le datapoint historique « live 1921 / offline 2301 » est le tir 0 : il est integralement explique.

### Mesure (b) — 2e cas DISCRIMINANT, **sans aucun buff**

Meme attaquant mais son arme de **MELEE** (`Power`, `PiercingRatio` 40, **3 coups**), aucun effet
pose, block neutralise au build (`--block-target 0,0`), seed 777. Bornes brutes [2250, 3376] ->
`x fix(0.40)` = 899.9999998 / 1350.3999997 -> cellules **[899, 1350]** (troncature) vs
**[900, 1350]** (arrondi).

| tir | LIVE per-coup | TRONQUEES | ARRONDIES |
|---|---|---|---|
| 0 | [1043, 941, 1183] | [934, 922, 1100] | **[1043, 941, 1183]** |
| 1 | [910, 1295, 1047] | [1110, 1058, 1211] | **[910, 1295, 1047]** |
| 2 | [940, 916, 1045] | [1206, 1281, 1046] | **[940, 916, 1045]** |
| 3 | [1100, 1052, 1253] | [1321, 1290, 1275] | **[1100, 1052, 1253]** |
| 4 | [917, 1236, 943] | [1150, 960, 1059] | **[917, 1236, 943]** |
| 5 | [1237, 933, **712**] | [970, 956, 1001] | [1237, 933, **1117**] |

**arrondi = live 17/18 coups ; troncature = 0/18.** Le seul ecart (tir 5, coup 3) est le **coup
letal** : la cible tombe a 0 PV, le natif rapporte le montant APPLIQUE (712 = PV restants) la ou
l'offline expose la valeur pre-ecretage — axe distinct (cap PV), pas l'etage teste. Une passe
anterieure sur un runner a block ACTIF avait de meme un ecart isole (712/1195 -> block) : deux
confonds identifies, aucun ne touche les cellules.

### Pourquoi le controle de case-117 etait bit-exact

Le regime n'etait **pas discriminant** : a percage 65 sur base 2813,
`2250 x fix(0.65) = 1462.4999997` (frac < 0.5 -> floor == round) et
`3376 x fix(0.65) = 2194.3999998` (idem). C'est ce qui a fait passer le port pendant longtemps :
les regimes valides jusqu'ici tombaient tous du bon cote. `probe_131 --phase scan` enumere les
regimes discriminants (28 sur un echantillon de 6 bases x 10 ratios) — c'est un cas **frequent**,
pas une singularite.

## 4. Le correctif

`scripts/python/engine/runner/operations/damage_ops.py`, `_DamageOpsMixin.execute::_reduced_bounds` :
les DEUX bornes se materialisent desormais par `apply_all_modifiers(..., round_materialize=True)`
(= `Fix64$$Round(·, AwayFromZero)`), mirror de
`DamageCalculations$$CalculateBaseDamageWithModifiers`. Un seul etage change ; aucun tirage
supplementaire, aucune branche nouvelle.

`scripts/python/engine/services/damage_modifiers.py` : la docstring d'`apply_all_modifiers` listait
« bornes d'attaque NORMALE » comme residu tronquant « live-valide bit-exact » — corrigee (le
verdict venait de regimes non discriminants) et la liste des residus restants precisee.

### Garde LIVE

`scripts/python/tests/engine/runner/test_normal_attack_bounds_rounding_live.py` verrouille **trois**
choses, dont la troisieme la rend non aveugle :

1. le regime **est** discriminant (cellules tronquees != cellules arrondies) — sinon la garde ne
   prouverait rien et l'assertion tombe ;
2. cellules **arrondies** == live, PER-COUP ;
3. cellules **tronquees** != live — **la garde rougirait si la loi etait la troncature.**

Le probe `probe_131_normal_attack_bounds.py` force explicitement les DEUX materialisations (il ne
compare pas « le port tel quel » a « le port patche ») : il reste un oracle discriminant apres le
correctif.

## 5. Ce qui n'est PAS couvert

- **Le FORK reste, seule la materialisation est reconciliee.** `_reduced_bounds` demeure une
  re-implementation partielle de `PredictAttackRaw`. Divergences connues du fork, toutes LUES au
  decompile, aucune mesuree :
  * **plancher 1** : `CalculateBaseDamageWithModifiers` rend `Fix64.One` quand `0 < v < 1` (et
    `PredictAttackRaw` refait `IdunBattle.Core.Services.MinMaxDamageFix64$$MathMax(&dmg, One)`,
    porte cote prediction sous #170). Le combat ne l'a pas -> une cellule dans `(0, 0.5)` rend 0
    offline et 1 nativement. N'affecte que percage tres bas + armure lourde ; **non confronte live**.
  * `extraMax` (`GetBaseDamageFix64` + stat 0x19), split bouclier PER-COUP, cap PV `rem`,
    `ApplyTraitDamageLimits` : le combat les traite ailleurs (`_run_hits` mode 1, `_target_shield`,
    `_apply_damage_pipeline`) au lieu de les lire de la meme sortie. Reconcilier reellement les deux
    faces sur `predict_attack_raw` est un chantier a part entiere.
- **Les autres vecteurs COMBAT restent TRONQUANTS** (residu nomme, chiffre) : ils passent par le
  MEME `PredictAttackRaw` natif (avec `predefined`) et sont donc suspects du meme +-1, mais aucun
  n'a ete confronte live sur un regime discriminant :
  * `damage_ops.execute_ability_attack::_reduce` quand `is_attack_damage_op=True` (famille ATTACK,
    `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`) — la famille ABILITY
    (`is_attack_damage_op=False`) arrondit deja depuis #90 ;
  * `damage_ops.execute_normal_like` (splash Psyker) ;
  * `operations/additional_hits` (coups additionnels heterogenes #179/#202-B).
  Chacun exige son propre montage discriminant (`probe_131 --phase scan` donne les regimes).
- **Ordre `ApplyCappedModifiers` / additif / `Round`** : le port arrondit deja en fin
  d'`apply_capped_modifiers` quand la %-list est NON vide, et ajoute l'additif DEFENSEUR avant le
  `Round` final ; le natif intercale `Mult+Round` par cote (attaquant puis defenseur). Inerte tant
  que `def_mods.additive == 0` (cas de toutes les mesures ici) — non exerce.
- **Face DECISION** : inchangee. La prediction utilise deja l'arrondi (`_materialize`) ; ce cas la
  rapproche du combat au lieu de l'en eloigner.
- Le confond **coup letal** (montant applique ecrete aux PV restants) et le confond **block** sont
  identifies et neutralises dans la garde (skip explicite), pas modelises.

## 6. Reproduire

```
python probe_131_normal_attack_bounds.py --phase scan          # regimes discriminants, 100 % offline
python probe_131_normal_attack_bounds.py --phase hailstrike -n 6 \
    --state <ABSOLU>.json                                      # le datapoint case-117 5ter
python probe_131_normal_attack_bounds.py --phase plain -n 6 --tanky --block-target "0,0" \
    --dist 1 --attacker darkaAzrael --p-units "darkaAzrael,ultraApothecary" \
    --a-units "astraBullgryn,astraBullgryn" --seed 777 --state <ABSOLU>.json
```
