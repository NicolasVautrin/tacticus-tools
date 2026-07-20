# Case #30 — Bornes RAW du DamagePredictionResult (raw @0x24/0x28 vs accurate @0x58)

Statut : **#30a (arrondi des bornes ±1-5) RÉSOLU 2026-07-19** — cause racine float64-vs-Fix64,
fix = émulation Fix64 exacte (`engine/services/fix64.py`), validé live 18/21 (voir §#30a).
**#30b (overshoot raw / porte overkill, tâche #40)** : RE structurel PROUVÉ (décompile + live
event-dumps), fix candidat identifié, validation live requise (sections suivantes).

Build : gqfc5mff6c. VAs absolues (RVA = VA − 0x180000000).

## #30a — RÉSOLU : bornes ±1-5 = float64 vs Fix64 (Q31.32), PAS un choix round-vs-floor

**Cause racine.** Le pipeline natif calcule TOUT en `FixMath.NET.Fix64` (long 64-bit, 32 bits de
fraction). Le port calculait en float64 → aux frontières ENTIÈRES (exactement là où kill/killSure
flippe) le bruit flottant traverse l'entier dans les DEUX sens. Preuve A/B (agreement seeds
777+31337 ×20 steps, 21 confrontations prédiction) : round(float) = 5 mismatch-logic ;
floor(float) = 8 (session précédente) ; floor(exact) = 13 ; **round(exact) = 3** — et les 3
restants sont d'AUTRES causes (voir plus bas). Ni round ni floor ne pouvait « réparer » le float.

**Sémantique Fix64 vérifiée au décompilé (2026-07-19)** — port : `engine/services/fix64.py` :
- `op_Multiply @181564280` = produit 128-bit puis TRONCATURE (`(a·b)>>32`, floor). Pas d'arrondi.
- `op_Division @181563e50` = ROUND-HALF-UP sur la magnitude (`(q+1)>>1` final), signe après.
- `op_Explicit @181564100` = `raw>>32` (floor) ; `Round @1815636e0` mode 0 = ToEven, mode 1 =
  AwayFromZero (frac==0.5 exact : négatif→floor, positif→+1).
- `GetMultiplierFromDamageBonus @181005210` = `One ± Div(FromInt(|pct|), FromInt(100))` —
  reconstructible EXACTEMENT depuis le float stocké (`round(mult×2^32)`, aucun cas ambigu pct
  entier) → format `pct_list` inchangé.

**L'ordre des ops est LOAD-BEARING** (`GetDamageWithPiercing @1815598b0`) : le natif fait
`pierceFrac = Div(pierce,100)` (arrondi : 0.15 → raw 644245094 = 0.1499999999767…) PUIS
`Mul(damage, pierceFrac)` (tronquant). Cas signature 777 s6 : natif `1850 × fix(0.15) =
277.4999998…` → 277 ; port float `1850×15/100 = 277.5` → round 278 (+1/coup, ×5 hits = le +5).

**Points de matérialisation int (verdicts, mélange décompile + empirique live) :**
- Bornes PRÉDICTION (`_materialize`, damage_prediction.py) : `Round(exact, mode 1)`. Empirique
  (13 vs 3 ci-dessus) ; `CalculateBaseDamageWithAllModifiers @18102d3f0` lu intégralement : AUCUN
  Round interne (renvoie du fractionnaire) ; les `op_Explicit` de PredictAttackRaw portent sur des
  Fix64 déjà intégraux → le Round vit en aval de CBDWAM, position exacte non localisée statiquement.
- `ApplyCappedModifiers @181000020` (port `apply_capped_modifiers`) : compose les entrées par muls
  TRONQUANTS sans arrondi intermédiaire (#98 u80 : ×1.5×1.5 → 3980.25 → 3980, un Round par entrée
  donnerait 3981) PUIS matérialise `Round(·, mode 1)` en fin d'appel si liste non vide (validé
  combat ThunderousAssault : live 6948 = Round(6947.x) — floor régressait à 6947). NB : le
  décompilé montre un Round+Clamp PAR entrée — la mesure u80 prouve que les multi-mults validés ne
  le traversent pas chacun (fold côté data) ; sémantique MESURÉE conservée.
- Dégât TIRÉ combat (`apply_all_modifiers` fin de chaîne) : `op_Explicit` = floor
  (`CalculateAbilityDamage @18102cb50`), inchangé — désormais floor du raw EXACT.

**Résultat live** : corrige 777 s6 u85 (±5 roll-min, le cas #30a nominal) et 31337 s5 u81 (−3).
Les 3 mismatches restants = causes distinctes déjà trackées : 777 s11 u95 (shieldDmgMin, bouclier),
31337 s8 u83 (**#30b** overkill, tâche #40), 31337 s13 u93 (killSure fantôme raw defender-mod,
lead 5 — voir §Lead 5). Tests combat ciblés : 11/11 verts (roll/attack/crit/block/armored/decomp/
ability dont ThunderousAssault bit-exact).

## Symptômes (agreement-stages.md leads 4-5, seed 31337, event-dumps capturés live)

Champs natifs de l'event `aiPlaybookPredict` (= `MakeDamagePredictions`) :
`willKillDmg`=raw min @0x24, `mightKillDmg`=raw max @0x28, `healthDmgMin/Max`=accurate (capé HP),
`totalDmgMin/Max`=total, `appliedHits`=nb coups.

Observation clé (5 event-dumps, seed 31337) : **`willKillDmg == totalDmgMin` ET `mightKillDmg ==
totalDmgMax`** dans TOUS les cas → le raw @0x24/0x28 EST le `totalDmg` (dégât total NON capé HP).

| step | u→tgt | ab | hpBefore | appliedHits | willKill/mightKill (raw) | healthMin/Max (accurate) |
|------|-------|----|----------|-------------|--------------------------|--------------------------|
| 8    | 83→91 | 69 | 1499     | 3           | 1498 / **1949**          | 1498 / 1499 (capé HP)    |
| 13   | 93→83 | 69 | 2783     | 4           | 2704 / **4056**          | 2704 / 2783 (capé HP)    |
| 6    | 85→95 | 1027| 2708    | 1           | 2792 / 4188              | 2708 / 2708              |
| 17   | 77→87 | 69 | 322      | 1           | 1378 / 2067              | 322 / 322                |
| 18   | 89→81 | 69 | 5274     | 2           | 5526 / 6492              | 5274 / 5274              |

Notre port (offline) à ces steps :
- s08 : raw off=(1498, **1498**) vs nat (1498, 1949) → `kill` off=False nat=True (raw max écrasé).
- s13 : raw off=(**4428**, **6640**) vs nat (2704, 4056) → `killSure` off=True nat=False (raw sur-évalué).

## Structure native (décompile)

### DamagePredictionResult (offsets via getters)
- `get_HealthDamage @18102be20` : renvoie `{@0x1c(min), @0x24}` (MinMax bytes).
- `get_WillBeKill @18102bef0` : `HP@0x00 <= raw@0x24(min)` → raw min sert le kill-sûr.
- `get_MightBeKill @18102be30` : `HP@0x00 <= raw@0x28(max)` → raw max sert le kill-possible.
- **@0x24 = raw MIN, @0x28 = raw MAX, @0x00 = HP cible. accurate = @0x58 (get_HealthDamageWithBlock lit
  0x1c..0x28 pour le split block ; l'accurate capé HP vit à @0x58).**

### `PredictAttackRaw @181032fb0` (par coup)
Ordre des écritures relativement à `ApplyTraitDamageLimitsToDamage @18102c650` :
1. `local_8b8`/`uStack_8b0` = bornes lo/hi (Fix64) posées BRUTES (@0x1810355a8, avant cap).
2. `ApplyTraitDamageLimitsToDamage(param_2, 1, &local_8b8, &uStack_8b0)` (@0x1810359c7) — **cape lo/hi
   EN PLACE** (member-cap, Resilient hp-1, Impervious, boss). AUCUNE sauvegarde des bornes brutes n'est
   lue entre la pose (2157) et ce call (2295) : tout l'aval consomme les bornes capées-trait.
3. `CalculateDamagePredictionScenario @18102ed00` reçoit ces bornes (via `param_6`).

### `CalculateDamagePredictionScenario @18102ed00` (struct de sortie)
Produit une struct où :
- champ **accurate** (0x04/0x08/0x0c/0x10) = `Max(0, eff − shieldAbs)` PUIS
  `FillUpStatComponent.MaxReduceByMinimum @180f9b800/900` appliqué à min ET max ;
- champ **raw** (0x24/0x2c) = `{op_Explicit(param_6+0x10), op_Explicit(param_6+0x18)}` = **les bornes
  ENTRANTES `param_6`**, SANS le cap FillUpStat, SANS re-soustraction shieldAbs.

`MaxReduceByMinimum` (les 2 surcharges) : `cap = CurrentValue(+0x18) − Min(CurrentValue, reservedMin
(+0x1c Nullable))` ; **NO-OP** si pas de Nullable minimum (héros normal → accurate = raw par coup). La
surcharge @180f9b800 écrit aussi le flag `limitedByMinHp` (`résultat != entrée`).

### `Add @18102a710` (agrégation multi-coups)
Somme SÉPARÉMENT chaque MinMaxDamage du résultat, chacun suivi d'`ApplyCap` (normalisation min≤max,
PAS un cap HP) :
- raw @0x24/0x28 : `param_1+0x24 += param_2[4].hi ; param_1+0x28 += param_2[5].lo ; ApplyCap(+0x1c)`.
- accurate @0x58 : `param_1+0x60 += param_2[0xc] ; ApplyCap(+0x58)` (chaîne santé).

→ **raw agrégé = Σ des raw par coup ; accurate agrégé = Σ des accurate par coup.** Aucun re-cap HP
sur le total raw. C'est pourquoi `mightKillDmg` (1949, 4056) dépasse `hpBefore` alors que
`healthDmgMax` est plafonné à HP.

## Porte overkill (Resilient hp-1) — RE confirmé fidèle

- `IsOverkill @181032bc0` (entrée service) : `CanBeOverkilled(tgt)` → `maxHP=GetStat(tgt,5,0)` →
  délègue `IsOverkill @181032db0(maxHP, dmg, …, allow=*(cfg+0x30), threshold=*(cfg+0x34))`.
- `ApplyTraitDamageLimitsToDamage` calcule le flag UNE fois depuis la borne MIN
  (`accum = (param_11−param_9) + param_12 + minDmg`, base pct = param_11=maxHP), l'applique aux 2
  bornes via `ApplyResilientTraitDamageLimit @18102c3a0` (cap `current_health−1` ssi trait Resilient
  0x3f1 && maxHealth>1 && current_health>0 && !overkill).
- **Le port `compute_prediction_overkill`/`is_overkill`/`apply_resilient_trait_damage_limit`
  (trait_damage_limits.py) est FIDÈLE en structure.** Le seul paramètre NON PROUVÉ = le threshold
  `*(cfg+0x34)` (config DI, asset-driven) ; le port suppose `overkillDmgPctOfHealth`=100 (HYPOTHÈSE).

## ⚠ RÉVISION 2026-07-19 (#40) : la porte OVERKILL n'est PAS le bug du lead 4 — FIT ARITHMÉTIQUE

Le fit entier des per-hit natifs s8 (3 coups, tgt 1499 HP) reproduit LES DEUX totaux natifs avec la
formule DU PORT (rem déplété + caps Resilient ACTIFS + overkill=False) :
per-hit **(min 698, max 1047)** (ratio 1047/698 = 1.5 = spread 20 % exact) →
h1 rem=1499 cap 1498 : (698,1047) intacts ; h2 rem=801 cap 800 : max→800 ; h3 rem=103 cap **102** :
min ET max →102. **rawMin = 698+698+102 = 1498 ✓ ; rawMax = 1047+800+102 = 1949 ✓.**
⇒ le natif APPLIQUE les caps Resilient sur s8 ; le vrai écart = les **bornes per-hit** (natif
698/1047 vs port ≈500/650) = une divergence de DÉGÂT sous-jacente (mod attaquant/défenseur manquant
sur eldarAutarch u83 → bloodDeathCompany u91), même famille que le lead 5 (s13). Le kill-flip n'est
qu'un symptôme. NB : 698/1047 ⇔ base efficace 872.5 (0.8×872.5=698, 1.2×872.5=1047) — une base
DEMI-ENTIÈRE (chemin avg(minDmg,maxDmg) d'arme ? mod ×1.x sur base int ? à élucider par recon du
kit u83 au pas s8).

**[⚠ FALSIFIÉ à son tour — cf. « ✅ #40 RÉSOLU » plus bas : il n'y a AUCUN mod manquant ni base
demi-entière. Le fit (698,1047) était un artefact du MAUVAIS modèle de chaîne de caps ; la vraie
cause = le threading `prev` santé PER-BORNE du port là où le natif déplète par UN SEUL scalaire
(raw MIN cumulé). Base 1408 inchangée → (1498,1949) bit-exact.]**

Acquis RE COMPLÉMENTAIRES (mécanique flags, décompile 2026-07-19, tous confirmés) :
- `ApplyTraitDamageLimitsToDamage @18102c650` appelle l'IMPL `IsOverkill @181032db0` directement :
  baseHP=param_11(maxHP), accum=op_Explicit(FromInt(maxHP−curHP)+FromInt(p12)+*param_3(minBound
  Fix64 FRACTIONNAIRE)), default_flag=son param_8, allow_flag=son param_13, suppress=HasFlag(0x13),
  cond=*(cfg+0x30) byte, threshold=*(cfg+0x34) int, 8e arg Nullable (min-HP ≥1 → return 0 direct —
  le floor HypersensoryAbilities coupe l'overkill). Le doc historique « allow=*(cfg+0x30) »
  mélangait cond et allow.
- PredictAttackRaw pose allow_flag (stack+0x60) = byte @args+0x68, **forcé à 1 si l'ATTAQUANT
  HasTrait(0x420=ThrillSeekers) ET HasEffect(0x59a=ThrillSeekers) ET (byte@+0x69 OU byte@0xb8)**
  (@L2279 du décompilé) ; default_flag (stack+0x38) = byte @args+0x69 ; p12 = Nullable @args+0x7c
  (=0 chemin attaque normale, PredictNormalAttack zère le struct). param_9 (curHP) = local_914 =
  rem_HP DÉPLÉTÉ @181034087 (le port fait pareil ✓).
- La confirmation live u78 (modéré → capé HP−1, massif PV=10 → bypass) reste VALIDE : default=0,
  allow=0, threshold=100 pour une attaque normale sans ThrillSeekers.

## Diagnostic du bug (port) — CAUSE RACINE = la porte OVERKILL sur cible Resilient
**[SECTION HISTORIQUE — falsifiée par la révision ci-dessus ; conservée pour les acquis RE]**

Faits vérifiés :
- `DamagePredictionResult.add` (damage_prediction.py L71-93) est CORRECT et fidèle à `Add @18102a710`
  (raw sommé séparément de l'accurate, chacun `apply_cap` = normalisation min≤max). **Le bug n'est PAS
  dans l'agrégation.**
- **tgt=91 (bloodDeathCompany, lead 4) A le trait Resilient** (gameconfig : `['Hero','RapidAssault',
  'Resilient','Unstoppable']`). Donc `target_has_resilient=True` est CORRECT. tgt=83 (eldarAutarch,
  lead 5) ne l'a PAS.
- Lead 4 natif : raw=(1498, **1949**) ; accurate=(1498, **1499**=HP exact, PAS hp-1=1498). ⇒ **le natif
  n'applique PAS le cap Resilient hp-1** (ni au raw ni à l'accurate) : l'accurate est simplement capé à
  HP. La seule lecture cohérente : **côté natif overkill=TRUE** (le coup tue la cible Resilient → le cap
  hp-1 est BYPASSÉ, cf. `ApplyResilientTraitDamageLimit @18102c3a0` : cap ssi `!overkill`).
- Notre port : `compute_prediction_overkill` retourne **False** (threshold=100 + évalué par coup sur
  `dmg_min` d'un coup ~500 < curHP) → on applique le cap Resilient hp-1 → raw écrasé à (1498,1498).

**CAUSE RACINE : notre porte overkill diverge du natif → cap Resilient appliqué à tort.** Trois
paramètres config-DI NON PROUVÉS entrent en jeu (à valider live) :
1. **threshold** `*(cfg+0x34)` — port suppose 100. S'il est bas, `IsOverkill @181032db0` renvoie 1 dès
   `curHP ≤ dmg` via la branche ratio.
2. **allow_flag** `*(cfg+0x30)` (param_4 d'IsOverkill) — port suppose 0. **Si =1**, `IsOverkill` renvoie
   1 dès `param_1 ≤ param_2` (curHP ≤ dmg) SANS condition de ratio → overkill dès que le coup tue.
3. **granularité** : le port évalue l'overkill par coup sur `dmg_min` d'UN coup ; il se peut que le
   natif l'évalue sur le dégât CUMULÉ/total (1949 ≥ curHP 1499). À vérifier : le `accum` d'ATL utilise
   `(param_11−param_9)+param_12+minDmg` par coup, mais `param_9`/`param_11` (curHP/maxHP) sont peut-être
   les valeurs INITIALES (non déplétées) → un coup unique suffit si base non déplétée.

- **Lead 5 (s13, tgt=83 NON Resilient) = problème SÉPARÉ** : `accurate min` diverge déjà (2704 nat vs
  2783 off) ⇒ écart de CALCUL du dégât brut (defender-modifier sur eldarAutarch non modélisé) propagé au
  raw ; le `killSure` fantôme en est la conséquence, pas un défaut de la logique raw. Ne PAS le confondre
  avec le lead 4.

## Fix candidat (à valider live)

Le raw et l'accurate sont déjà séparés correctement (add + predict_attack_raw). Le fix porte sur la
PORTE OVERKILL de `predict_attack_raw`/`compute_prediction_overkill` :
- déterminer les vraies valeurs `allow_flag` (cfg+0x30) et `threshold` (cfg+0x34) via un probe live
  (hook `IsOverkill @181032db0` args, OU tracer `apply_trait_damage_limits_to_damage` sur une cible
  Resilient et observer la bascule cap/no-cap) ;
- l'hypothèse la plus probable : `allow_flag=1` (overkill dès `dmg ≥ curHP`) — ce qui, pour lead 4,
  déclencherait overkill sur le coup qui tue → bypass du cap Resilient → raw (et accurate) non plafonnés
  à hp-1 → raw=(1498,1949), accurate capé HP=1499, kill=True. À CONFIRMER LIVE.

## Ce que le validator doit attaquer en priorité
1. La granularité + les 2 flags config-DI de la porte overkill (le point faible : 3 hypothèses non
   prouvées se combinent). Un hook `IsOverkill @181032db0` capturant `param_4`(allow)/`param_7`(threshold)
   sur une cible Resilient tranche net.
2. Ne PAS régler lead 5 par le même fix (defender-mod distinct) — vérifier qu'il ne régresse pas.

## Validation

Session Frida tombée pendant l'investigation (jeu fermé → `session:null`). Les event-dumps ci-dessus
ont été capturés AVANT la chute (seed 31337, 20 pas). Re-tester le fix : re-inject + warmup, puis
`walk_dump_raw` (mon dumper scratchpad) sur seeds 31337 + 777, cible s08 (raw doit passer à
(1498,1949), kill→True) et s13 (traiter séparément le defender-mod).

## ✅ #40 RÉSOLU (2026-07-20) : `BlockScenario.healthDmg` = UN SEUL int (raw MIN cumulé), pas per-borne

**CAUSE RACINE du lead 4 (s8) — et clôture de toute la chaîne #30.** Ni porte overkill (falsifiée le
19), ni mod manquant / base demi-entière (falsifiés le 20) : le port threadait la déplétion santé
**PER-BORNE** (`prev.health_min` pour lo, `prev.health_max` pour hi) là où le natif déplète les DEUX
bornes par **UN SEUL scalaire**.

RE décompilé (lecture intégrale, VAs) :
- `get_DefaultBlockScenario @18102bcd0` : copie champ-à-champ `result@0x18..0x48` → BlockScenario ;
  **`BS.healthDmg@+0x08 = result@+0x20 = raw health MIN cumulé`**. Layout du struct résultat
  RE-CONFIRMÉ : raw MinMax **@0x18** `{cap@0x18, Min@0x20, Max@0x24}` (l'ancienne note
  « min@0x24/max@0x28 » était décalée de 4) ; preuve croisée : `get_WillBeKill @18102bef0` =
  `[0] <= [9]` = `CurrentHealth <= raw MAX@0x24` (cohérent avec kill natif=true à rawMax≥HP).
- `PredictAttackRaw` consomme le Nullable prev (@param_3+0x84) en 4 lectures : santé
  **`local_914 = Max(0, HP − BS@+0x08)` @181034087** (UNIQUE — sert les 2 bornes : trait-limits ET
  cap FillUpStat), armure `@181034130` (BS@+0x18), bouclier min/max `@1810341d5`/`@18103427a`
  (BS@+0x28/+0x2c — bouclier PER-BORNE, le port était déjà fidèle là-dessus).

**Pourquoi ça produit 1949 > HP−1** : la borne max de chaque coup est capée contre le rem du
scénario MINIMUM garanti (h1 (901,1352) intacts ; rem 1499−901=598 → cap Resilient 597 → h2
(597,597) ; rem 1 → cap 0 → h3 (0,0)) ⇒ raw = (1498, **1949**) avec base 1408 INCHANGÉE — bit-exact
natif. Le port per-borne saturait hi à 1352+146+0 = 1498. Idem u81→u91 : (1003, min(1505,1498)) +
(495,495) + (0,0) = (1498, **1993**) bit-exact (base 1003, ×1.25 RapidAssault, pierce 100).

**Fix (damage_prediction.py)** : `BlockScenario.health` (un champ, = `raw_health_damage.min` du
cumul), `_rem` unique dans les trait-limits + le cap santé du scénario. L'accurate max cumulé peut
alors dépasser HP par coup — renormalisé par le cap HP de l'accurate dans `Add` (1499 ✓).

**Validation** : agreement 777+31337 ×20 → prédiction **19/21 (90 %)** (s8 réglé, zéro régression) ;
tests ciblés `test_predict_live` + `test_damage_roll_live` + `test_runner_attack_live` +
`test_finaljustice_live` = 7/7. Restants (dossiers DISTINCTS) : 777 s11 u95 ab1150 (split bouclier,
shieldDmgMin 3351 vs 2873, tâche #42) ; 31337 s13 u93→u83 — **✅ RÉSOLU 2026-07-20 (#41)** : le
« mod défenseur ×0.611 » n'existait pas — ×0.611 = 1408/2306, le PORT sur-appliquait l'aura
RitesOfBattle Basic +898 (Calgar adjacent à la tuile candidate) sur une attaque MÊLÉE ; loi native
= aura per-candidate RANGED seulement (pas de gain mêlée non-matérialisé) + drop sur tuile bloquée.
Détail : `case-49-min-armored-regime.md` §MAJ #41.

**Leçon de méthode** : le fit arithmétique du 19 (base 872.5 « demi-entière ») collait parfaitement…
dans le mauvais modèle de chaîne. Avant de chasser un « mod manquant », REJOUER les bornes natives
dans le pipeline EXACT du port (fit exhaustif par énumération — `fit40_exhaustive.py`) : ici aucune
base/mod ne pouvait produire 1949, ce qui pointait la STRUCTURE (discipline « check own port »,
le commentaire du port documentait déjà `healthDmg@+0x08` SINGULIER que le dataclass violait).
