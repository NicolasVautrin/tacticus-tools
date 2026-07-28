# R6 — matérialisation finale de `execute_normal_like` et de `additional_hits`

**Question (binaire)** : ces deux vecteurs COMBAT doivent-ils **ARRONDIR**
(`Fix64.Round(·, AwayFromZero)`) là où ils **TRONQUAIENT** (`op_Explicit` = `raw >> 32`) ?

**Réponse : OUI, les deux.** Ce n'étaient pas trois lois de matérialisation mais **une seule**, et
les trois derniers vecteurs COMBAT retombent tous sur la même fonction native.

---

## 1. RE — le décompilé, d'abord (gqfc5mff6c)

L'étage en question est le **MULTIPLICATEUR**, dernier étage de
`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` (slot 0x10),
c'est-à-dire `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers`, **lu
verbatim** :

```
v = Fix64.op_Multiply(damage, multiplier)
if (v <= Zero) return Zero
if (v > Zero && v < One) return One
return FixMath.NET.Fix64$$Round(v, 1)          // 1 = AwayFromZero
```

`CalculateBaseDamageWithAllModifiers` l'appelle **une fois par côté dont le
`Nullable<DamageModifiers>` a `HasValue`** (attaquant puis défenseur) : l'arrondi est donc
**inconditionnel**, indépendamment du fait que la `%-list` soit vide.

Reste à établir que les deux vecteurs passent bien par là. **Ils y passent tous les deux, par la
même `ExecuteHit` que les coups d'arme** :

| vecteur offline | chaîne native |
|---|---|
| `execute_normal_like` | mode `amount` de `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` **et** `UseNormalAttackIfAble` on-appearance d'un summon — famille ATTACK ⇒ `IdunBattle.Operations.AttackDamageOperation$$Execute` → `ExecuteHits` → `ExecuteHit` |
| `additional_hits`, groupes **SANS** profil | `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType` — sa dernière instruction est `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` |
| `additional_hits`, groupes **AVEC** profil (SquigHound, CordClaw, InfernalPacts…) | `IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute` → slot **0x3c** de l'interface OperationProcessor = `Core.Services.OperationProcessor$$AttackDamage` (signature identifiée par l'appariement des 6 arguments) → `IdunBattle.Operations.AttackDamageOperation$$Execute` → `ExecuteHits` |

Et `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` matérialise sa cellule par le slot 4
`IdunBattle.Core.Services.DamagePrediction$$PredictAttack` (cache → `PredictAttackRaw`, qui appelle
`CalculateBaseDamageWithAllModifiers`) puis le slot 8
`IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage`.

⇒ **Un coup additionnel, ou un coup de `normal_like`, ne peut pas se matérialiser autrement que les
coups d'arme de la MÊME `ExecuteHit`** — dont l'arrondi est mesuré depuis #131 (attaque normale) et
la campagne HeavyGravCannon (ability bounds-mode famille ATTACK). Tronquer ici était un **fork de
port** : une opération native, plusieurs façades offline dont certaines fausses.

---

## 2. Le régime discriminant, et le levier qui a manqué

L'arrondi n'est **observable** que si la valeur réduite est FRACTIONNAIRE, ce qui exige :

* **(a)** les DEUX `%-list` VIDES — sinon
  `IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers` arrondit déjà en fin d'appel ;
* **(b)** la branche PERÇAGE du plancher
  `idun.…StaticBattleRules.Damage$$GetDamageWithPiercing` (`max(0, d − armure, d × pierce%)`)
  l'emporte, i.e. `armure > d × (1 − pierce/100)` — sinon `d − armure` est ENTIER ;
* **(c)** la partie fractionnaire de `d × fix(pierce/100)` est ≥ .5. `fix(p/100)` est **légèrement
  inférieur** à la fraction exacte dès que `p/100` n'est pas dyadique (`Div(20,100)` =
  0.1999999999534…), donc tout `d` dont le produit exact est ENTIER donne une fraction ~0.99999 —
  le cas le plus discriminant.

**(b) était le blocage.** Sur un profil à perçage bas (`Physical` = 1 %), aucune armure du roster
rank 17 ne suffit : le maximum mesuré est `astraBullgryn` **3513**, et il faut `> 0,99 × 2660`
pour le seul bord bas du groupe SquigHound — et `astraBullgryn` porte `BigTarget`, ce qui réveille
`BeastSlayer_ExtraDmg` (+20 %) du porteur et **casse (a)**.

**Levier ajouté** : `rl_duel build --armor-target N` force `Armor`+`FixedArmor` des a-units. C'est
le pendant manquant de `--hp-target` (qui les met à **0**, cf. fiche R8) :

* valeur **HAUTE** → régime (b) armé pour n'importe quel profil ;
* valeur **BASSE** → branche armure, dégât ENTIER = **régime témoin** non discriminant.

---

## 3. Mesure — `execute_normal_like`

**Montage** : `ultraInceptorSgt` caste `DeathFromAbove` (1003) ; chaque `ultraSmnInceptor` spawné
exécute son on-appearance `UseNormalAttackIfAble` = **6 coups Bolter (PiercingRatio 20)** routés par
`execute_normal_like`. Cible `necroWarden` (aucun effet de défense gaté, pas de `SwornProtector`).
`--crit 0,0 --block-target 0,0` : une seule variable bouge.

`summonDmg[50] × 180 %` = **997** → bornes brutes `[798, 1196]` → cellules **[159, 239]** (troncature)
vs **[160, 239]** (arrondi). La largeur du modulo change ⇒ **chaque** valeur tirée change.

| seed | live (6 coups) | troncature | arrondi |
|---|---|---|---|
| 777 | `[227,199,205,179,187,168]` | `[224,230,162,175,188,182]` | **= live** |
| 31337 | `[235,223,219,174,238,179]` | `[228,229,201,220,207,219]` | **= live** |
| 4242 | `[183,215,214,168,235,161]` | `[195,195,207,205,164,236]` | **= live** |
| 12345 | `[225,210,222,176,162,228]` | `[189,220,187,205,159,198]` | **= live** |
| 2024 | `[196,205,192,160,221,210]` | `[190,205,200,226,229,193]` | **= live** |

⇒ **live == arrondi 30/30 · live == troncature 0/30.**

**GÉNÉRALISATION — régime MIXTE (`--armor-target 800`)** : le bord BAS reste dans la branche
perçage (`798 − 800 < 159,6`) mais le bord HAUT bascule dans la branche armure
(`1196 − 800 = 396 > 239,2`), donc UNE cellule est fractionnaire et l'autre ENTIÈRE — forme de
régime différente, même verdict :

| seed | live | troncature | arrondi |
|---|---|---|---|
| 777 | `[216,378,226,188,381,321]` | `[168,242,394,180,180,223]` | **= live** |
| 31337 | `[184,200,343,383,196,373]` | `[354,386,286,395,279,250]` | **= live** |
| 4242 | `[352,220,220,314,339,165]` | `[246,276,369,337,334,376]` | **= live** |

⇒ **+18/18 arrondi, 0/18 troncature.**

**TÉMOIN (`--armor-target 300`, branche armure des DEUX côtés ⇒ valeurs ENTIÈRES, régime NON
discriminant)** : seeds 777 et 31337, `live == floor == round` **12/12**. Ce témoin **réfute** deux
hypothèses concurrentes : « l'arrondi collait par chance » et « c'est un additif oublié » (un
additif aurait fait diverger le témoin aussi).

**Bilan `normal_like`** : 60 coups confrontés, `live == arrondi` **60/60**, `live == troncature`
**12/60** (les 12 du seul régime témoin, où les deux lois coïncident par construction).

---

## 4. Mesure — `additional_hits`

**Montage** : `orksRuntherd` (passif `SquigHound` → effet 0x50c, **2 coups PREDEFINED
[minDmg,maxDmg]** profil `Physical` pierce 1) attaque au contact `ultraApothecary`
(**ni BigTarget ni Vehicle** ⇒ `BeastSlayer_ExtraDmg` du porteur reste inerte ⇒ condition (a) tenue ;
pas de `SwornProtector`), `--armor-target 6000`. Groupe = `[2660, 3988]` ⇒ cellules **[26, 39]**
(troncature) vs **[27, 40]** (arrondi).

⚠ **Un étage AMONT devait être neutralisé d'abord** (cf. §5) : le port résout ce canal en
**reduce-then-roll** alors que le natif fait **roll-then-reduce** pour un groupe `predefined`. La
mesure a donc été faite par **décomposition par étage** (`probe_r6 --case ah_matrix`, 4 combinaisons
ordre × matérialisation), l'ordre natif étant celui qui reproduit le live.

Coups reproduits par le modèle d'ordre natif (1ᵉʳ coup de chaque groupe — voir §5 pour le 2ᵉ) :

| seed | live | troncature | arrondi | discriminant ? |
|---|---|---|---|---|
| 12345 | **38** | 37 | **38** | **oui → arrondi** |
| 314159 | **27** | 26 | **27** | **oui → arrondi** |
| 88 (coup 1) | **30** | 29 | **30** | **oui → arrondi** |
| 88 (coup 2) | **37** | 36 | **37** | **oui → arrondi** |
| 777 | 32 | 32 | 32 | non |
| 31337 (2 coups) | 30, 34 | 30, 34 | 30, 34 | non |
| 4242 | 37 | 37 | 37 | non |
| 2024 | 27 | 27 | 27 | non |
| 999 (2 coups) | 39, 32 | 39, 32 | 39, 32 | non |
| 500 | 38 | 38 | 38 | non |
| 7 | 37 | 37 | 37 | non |

⇒ **live == arrondi 14/14 · live == troncature 10/14**, les **4** écarts tombant EXACTEMENT sur les
tirages à partie fractionnaire ≥ .5. C'est la **signature exacte** de la campagne HeavyGravCannon
(14/14 vs 12/14) : un additif oublié aurait donné un `+1` **systématique**, y compris sur les 10
tirages non discriminants.

---

## 5. Ce qui n'est PAS couvert (et le résidu NEUF que la mesure a révélé)

**RÉSIDU NEUF, chiffré — l'ORDRE du canal `additional_hits` pour un groupe `predefined`.**
`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` commence par
`IdunBattle.Core.HitDamage$$GetDamage` sur le struct de l'`AttackData` : pour un groupe dont le
descripteur porte `RandomAmount(ConfigVar(0xc), ConfigVar(0xd))`, ce struct est **NON dégénéré** ⇒
1 tirage BRUT, puis le resolve slot-8 sur une cellule dégénérée = 1 tirage **gaspillé** ⇒
**roll-then-reduce, 2 tirages/coup**. Le port fait **reduce-then-roll, 1 tirage/coup**
(`post_roll=None`). **MESURE** (`probe_r6 --case ah_matrix`, 11 seeds) : le **1ᵉʳ coup de chaque
groupe** est reproduit **11/11** par roll-then-reduce et **0/11** par reduce-then-roll.
C'est le résidu #202-B (« conso RNG discriminante, À CONFIRMER LIVE ») — **AMONT** (il décide QUEL
tirage sort) et **orthogonal** à la matérialisation (qui décide COMMENT il se matérialise). **Non
traité ici** (hors périmètre R6).

**Sous-résidu du même étage** : le **2ᵉ** coup du groupe n'est reproduit que **3/8** par
roll-then-reduce (777 : live 37 vs 38/39 ; 4242 : 34 vs 30 ; 2024 : 31 vs 35/36 ; 500 : 40 vs 36/37 ;
7 : 32 vs 33/34). Un tirage supplémentaire est donc consommé nativement **entre** deux coups d'un même
groupe dans une partie des cas. Piste non explorée : `IdunBattle.Operations.ADamageOperation$$
EvaluateAfterHitTriggers` tourne à la fin de **chaque** `ExecuteHit` — y compris ceux du groupe — et
le porteur `orksRuntherd` a le trait `GetStuckIn`, dont le behaviour est un `Maybe(chance)` ; le port
ne roule ce `Maybe` que sur les coups d'ARME d'index impair.

**Forme des bornes du canal `additional_hits` pour les groupes `amount`.** Mesuré au passage
(`tauCrisis`/`CyclicIonBlaster`, profil `Particle` p35, `--armor-target 6000`) : les coups d'arme sont
bit-exacts (`[153,211,163,144,200,174]` live == offline) mais les 3 coups du groupe valent live
`[267,277,243]` là où le port donne `[235,235,208]`/`[236,236,209]` — **au-dessus de la borne haute
du port** (`amount ± 20 %` = `[479,719] × 0,35` → cellules ≤ 252). Cohérent avec le résidu déjà nommé
dans la docstring de `CyclicIonBlasterAdditionalHitsEffect` (« face COMBAT (RandomAmount réel) non
confrontée ») : la face combat tire dans `[minDmg, maxDmg]`, pas dans `amount ± 20 %`. **Hors
périmètre R6** ; le patron de correction existe déjà (`InfernalPactsAdditionalHitsEffect` expose
`amount` **et** `min`/`max`).

**Non couvert par ailleurs** :
* le **fork** `_reduced` / `_reduced_bounds` demeure : ces deux façades restent des
  ré-implémentations partielles de `PredictAttackRaw` (plancher `One` quand `0 < v < 1`, `extraMax`,
  canal de coups, `hit_mult` cible non threadé dans `normal_like`) ;
* la face **PRÉDICTION** est inchangée (elle arrondissait déjà).

---

## 6. Reproduire

```
# 100 % offline : quels régimes discriminent ?
python probe_r6_round_materialize.py --case scan

# etat live (armures, effets, niveaux, multiplicateurs) avant de choisir la cible
python probe_r6_round_materialize.py --case explore --p-units ultraInceptorSgt --a-units necroWarden

# vecteur normal_like (discriminant, puis MIXTE, puis temoin)
python probe_r6_round_materialize.py --case normal_like --target necroWarden --a-units necroWarden \
    --seeds 777,31337,4242,12345,2024
python probe_r6_round_materialize.py --case normal_like --target necroWarden --a-units necroWarden \
    --extra "--armor-target 800" --seeds 777,31337,4242
python probe_r6_round_materialize.py --case normal_like --target necroWarden --a-units necroWarden \
    --extra "--armor-target 300" --seeds 777,31337
# (--caster/--ability permettent de rejouer le meme montage sur un AUTRE summoner)

# vecteur additional_hits : DECOMPOSITION PAR ETAGE (ordre x materialisation)
python probe_r6_round_materialize.py --case ah_matrix --carrier orksRuntherd \
    --target ultraApothecary --a-units ultraApothecary --extra "--armor-target 6000" \
    --seeds 777,31337,4242,12345,2024,999,500,314159,88,7
```

Gardes live : `tests/engine/runner/test_normal_like_bounds_rounding_live.py` et
`tests/engine/runner/test_additional_hits_rounding_live.py`. Fixture partagée du régime :
`tests/engine/runner/_pierce_floor_regime.py`.
