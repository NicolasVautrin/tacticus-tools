# Case #62b — Crit dans la PREDICTION : le no-op est FIDELE (aucun edit)

**Statut** : RE fait (decompile `PredictAttackRaw @181032fb0` lu integralement) + CONFIRME LIVE
(re-expert 2026-07-13). **VERDICT : la premisse de #62b est FAUSSE.** Le crit n'est PAS replie dans le
`min/max` rapporte (`AccurateHealthDamage`), NI dans l'utilite d'attaque de l'IA. Le `might_crit` =
flag inerte du port est **FIDELE au natif**. L'activer DIVERGERAIT. AUCUN edit moteur.

## Trois representations distinctes du degat dans DamagePredictionResult

1. **`AccurateHealthDamage` @struct+0x58** (= `healthDmgMin/Max` rapporte, ce que le port mirror
   bit-exact) = scenario de BASE NON-CRIT, produit par le `CalculateDamagePredictionScenario` FINAL
   (@181035fc2). Crit-EXCLUSIF.
2. **`Scenarios` list @struct+0x50** = cascade crit par-hit. `local_9d8` = liste per-hit
   `{lo32=hitDmg, hi32=critChance%}` (Count@+0x18), rebuilt @181035b60 via
   `FUN_1800053f0(0, IDamageCalculations DAT_183287db8, ...)` = **SLOT #0 de l'interface**
   (c'est le "service source non resolu" laisse ouvert par le plan damage_prediction). Cascade
   `p_i = w*critChance/100 ; w *= (1-p_i)`.
3. **`CalculateProbabilisticDamage @18102b7b0`** (scalaire crit-INCLUSIF) =
   `Min(HP+shield, round((probMin+probMax)/2))`, `CalculateProbabilisticDamagePart @18102b380` =
   `Sum prob_i * selector(bounds_i)` sur `[baseScenario] + Scenarios`.

## Qui lit quoi (le point decisif)

- Prediction rapportee + `aiPlaybookPredict` = figure #1 (crit-EXCLUSIF).
- **Utilite d'attaque IA** = figure #1 : `DamageUtility.GetHealthDamage @1810cec60` =
  `MinMaxDamage.Avg(this+0xb = +0x58)` = `Avg(AccurateHealthDamage)`. AUCUN appel probabiliste.
- Figure #3 (crit-inclusif) = UNIQUEMENT `BattleQuery.SelectBestDamageWeapon @181071c12/c23`
  (choix d'arme) + HUD (`IdunUnitHud.ShowPrediction`). PAS l'utilite par-cible.
- `MightCrit @+0xB1` = flag d'AFFICHAGE (slot #7 @181036998), ne gate PAS le degat.

## Feuilles crit (deja portees, pour reference)

`GetCritChance @181031aa0` = `clamp(0,100, GetStat(9)+GetCritChanceBonusFromEffects)` ;
`GetCritDamage @181032450` = `Max(0, GetStat(10)+effects)` ; `CalculateCriticalDamage @18102da90`.
La couche stat offline expose deja GetStat(9)/(10) (unit_context.py:122/127) + lecteurs d'effet
(effects/__init__.py:289/302). Aucune dependance manquante -> mais RIEN a cabler (le crit ne doit
PAS bouger le degat rapporte).

## Confirmation live

Build MC1_67 seed 62062, Maugan Ra (InescapableAccuracy extraCritChance=15) vs ultraTitus.
Loki_NormalAttack oracle vs moteur : u81->u79 [1450,2175]h5 EXACT crit=0 ; u83->u77/u79 [3856,5784]
EXACT. mightCrit=0 partout. Le crit ne bouge pas le degat rapporte meme pour un porteur de crit.

## A garder a l'oeil (validator)

Le pivot du verdict = l'offset `DamageUtility.GetHealthDamage @1810cec60` (`this+0xb`=0x58=
AccurateHealthDamage). Si cet offset pointait sur Scenarios/probabilistic, le verdict s'inverserait.
Confirmer mightCrit=0 + ratio 1.0 sur d'autres porteurs (WarHowl 36%, EuphoricStrikes 30%).

## Gap HORS-SCOPE decouvert (tache separee) : HarvesterOfSouls x2.0

`HarvesterOfSouls` (1067) : oracle [3702,5553]h3 vs moteur [1851,2778]h3 (x2.000, meme level/mult/hits,
mightCrit=0 -> PAS du crit). Cause identifiee : `HarvesterOfSoulsPlaybook.MakeDamagePredictions
@1811428b0` alimente la base via l'OVERRIDE `ArcScourgeAbility.GetDamage`, pas l'`avg(minDmg,maxDmg)
xmult` generique. NB initial : x2.000 a CONFRONTER avec le bug RangedInMelee (#161).

**RESOLU (#163, 2026-07-13) : c'ETAIT le bug RangedInMelee (#161), PAS un base override.** Maugan Ra est
un caster HYBRIDE ranged (5hmp40/6hR3p55, sans le trait Ranged=11) tirant HarvesterOfSouls (ranged) en
melee -> le port appliquait x0.5 a tort. Apres le fix #161, HarvesterOfSouls = BIT-EXACT (predict_sweep
OK, meme roster Maugan Ra vs ultraTitus). L'override ArcScourgeAbility.GetDamage n'est PAS necessaire (la
base generique matche l'oracle). La RE ArcScourge etait un red herring (ou ArcScourge.GetDamage ==
generique). #163 clos.
