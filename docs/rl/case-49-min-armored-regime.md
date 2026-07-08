# Case study #49 (min-side) : sous-prediction du MIN en regime lourdement blinde

Build `gqfc5mff6c`. Trouve le 2026-07-08 par validation adversariale (#54, Etape 2) : deux
seeds FRAIS via `test_predict_live` (PREDICT_SEED) ont RE-EXPOSE un residu que les tests
seed-777 + overkill 3/3 ne montraient pas. **#49 etait marque completed : son cote MIN ne
l'est PAS.** GREP ce fichier avant de re-investiguer #49.

## RESOLU 2026-07-09 (#67) : l'AURA etait evaluee a la TUILE CANDIDATE au lieu de la POSITION REELLE

**Le gap DOMINANT "aura sous-appliquee sur ~24/28 tuiles" est FERME** (verdict re-expert acf1a624 + fix + validation).

- **Root cause** : `make_normal_attack_predictions` (prediction.py) evaluait l'aura d'attaque-stat
  (RitesOfBattle @181225340 / PathOfCommand) a la **tuile candidate** `attack_pos` -> l'aura n'etait
  ajoutee que sur les tuiles candidates hex-adjacentes au porteur (Calgar) -> base 3011 (bare) sur les
  ~24 autres tuiles, 4309 sur ~4. C'EST le volume d'ecart du #49 (pas l'elevation, pas un plancher).
- **RE (decompile)** : `GetAttackHitPrediction @1811af4e0` lit `GetStat(Attack, Current)` **SANS argument
  de position**. L'aura est un `DynamicStatModifierEffect` **bake dans le StatComponent** du beneficiaire,
  refresh **event-driven** (`RefreshValueInternal @180f09220`, trigger deploiement + entree/sortie de ring
  sur move REEL) — **PAS re-teste a chaque GetStat**. Donc la valeur bakee a la **position REELLE** de
  l'attaquant s'applique **IDENTIQUEMENT a toutes les tuiles candidates** (la prediction "deplace"
  virtuellement l'attaquant pour la GEOMETRIE seule : elevation/distance/arme, jamais pour re-baker Attack).
- **Fix (1 ligne, prediction.py ~179)** : aura evaluee a `scene.pos(att_id)` (position reelle), **jamais**
  a `attack_pos`. Beneficie a PathOfCommand (meme funnel `aura_attack_bonus_from_allies`). Chemin combat
  (runner) intact (il lit deja `GetStat` reel). #64 (debuff stat-mod, branche CalculateModifiersFromStatModifications
  gatee off) non touche.
- **Validation** : `tests/engine/test_aura_position_live.py` (setup ultraCalgar + bloodDeathCompany=u92) —
  attaquant adjacent au porteur -> `base` CONSTANT = Initial+aura sur TOUTES les tuiles candidates (mesure
  live : **3011 + 1298 = 4309**, y compris la tuile far non-adjacente ou le bug donnait 3011) ; attaquant
  eloigne -> `base` CONSTANT = Initial bare (**3011**). No-reg : deep_strike + predict_live 3/3.
- **NON couvert par #67 (reste ouvert)** : le **residu (6,4) = 2256** (SEUL cas d'un x1.5 base-nue) =
  axe **elevation/selection d'arme** SEPARE, mecaniquement inexplique et **explicitement a NE PAS fitter**
  (cf. sections ci-dessous). #67 ferme l'aura, pas ce residu.

## MAJ 2026-07-08 (2e passe re-expert) : ELEVATION AUSSI REFUTEE = RED HERRING. Vrai gap = AURA #49

**DEUX hypotheses successives REFUTEES** : (1) plancher minDmg param_6/param_7 (refute 1re passe) ;
(2) elevation +50% dans le preview (refute 2e passe, ci-dessous). **NE PAS re-chasser ces deux.**

- **Elevation = RED HERRING** (experience controlee re-expert : aiPredict sur les 28 tuiles du movable
  set de u92, = chemin oracle DISPLAY `GetAllPredictions @181090f50` que le sample compare) : **11 tuiles
  en surplomb strict (attacker_elev > target_elev, board live) ne recoivent AUCUN bonus** ; une SEULE
  ((6,4)) a le ×1.5. u90-777 en surplomb -> PAS de ×1.5 (2048). => "surplomb -> +50%" refute par la donnee.
  Le revert de l'elevation hors preview (etat committe bef2cc1) est CORRECT ; le commentaire existant de
  prediction.py (elevation = combat only, pas preview) est CONFIRME. NE PAS re-ajouter.
- **Vrai gap DOMINANT = l'AURA #49 sous-appliquee** : sur les 28 tuiles, 24 donnent oracle 5397 (base
  4309), mais le port calcule base 3011 pour beaucoup -> l'oracle applique l'aura Attack +1298
  (RitesOfBattle/Calgar, 3011->4309) a ~20 tuiles ou le port ne la met PAS. Le VOLUME d'ecart est la
  (portee/placement de l'aura per-tuile), PAS l'elevation ni un plancher. -> rouvrir cote AURA (#49 range).
- **Residu (6,4) = 2256** (= base3011 ×1.875 post-pierce) : SEUL cas d'un ×1.5, mecaniquement INEXPLIQUE,
  non isolable (aucune autre tuile base-nue+×1.5 pour trianguler). **NE PAS le fitter.** Pour l'isoler :
  monter un attaquant SANS aucune aura a proximite + tuiles surplomb base-nue vs plates base-nue.
- DISPLAY (`GetAllPredictions`->`PredictAttack` idx0x26->`GetAttackHitPrediction @1811af4e0` lit GetStat(5))
  != SCORING (`PredictAttackRaw @181032fb0`) = DEUX chemins ; aiPredict (display) ne hooke PAS PredictAttackRaw.
  Le sample compare le DISPLAY.

---

## (SUPERSEDEE) MAJ 2026-07-08 (1re passe) : hypothese "plancher minDmg" REFUTEE -> ELEVATION (a son tour REFUTEE ci-dessus)

- **Le "plancher minDmg param_6/param_7" (section plus bas) est REFUTE** (re-expert #67, hook live) :
  param_6/param_7 = Nullable de config presque toujours ABSENTS (dispatch d'interface, pas un
  plancher) ; dans u92->u86 ils sont absents. Le vrai plancher (`GetDamageWithPiercing`) est deja
  porte fidele. => NE PAS chasser un plancher.
- **Cause reelle (PARTIELLE) = bonus d'ELEVATION (+50%) omis dans le PREVIEW de prediction** : hook
  live `CalculateBaseDamageWithAllModifiers` seed31337 u92->u86 -> out MIN=752=x1.875 (=1.25
  RapidAssault x 1.5 elevation) ; oracle 2256=752x3. u92 attaque depuis une tuile en surplomb.
- **MAIS la condition N'EST PAS "surplomb strict"** : re-add de l'elevation au preview FIXE u92-31337
  (2256) mais REGRESSE u90-777 (u90->u86=orksKillaKan : oracle 2048 SANS elevation, offline 3072 =
  x1.5 de trop). Le preview applique l'elevation pour u92 mais PAS u90 -> FACTEUR DISCRIMINANT
  manquant (is_ranged ? tuile ? donnee elev fausse ? le x1.5 de u92 est-il MEME l'elevation ?).
  On flip-flop depuis #45/#58/#50/#67 car on mesure des CORRELATIONS, jamais la CAUSATION isolee.
- **Etat port** : elevation RETIREE du preview (committe bef2cc1) -> u92 sous-predit (strict-surplomb
  ranged blinde), u90 correct. **NE PAS re-add sans la condition complete** (re-expert re-engage pour
  trancher : experience CONTROLEE isolant l'elevation + RE du gate natif du preview). La section
  "plancher" ci-dessous est CONSERVEE pour trace mais SUPERSEDEE.

## Faits mesures (offline vs oracle live decisionView dmgMin/dmgMax)

| seed  | attaquant->cible          | oracle       | offline      | MAX   | MIN delta |
|-------|---------------------------|--------------|--------------|-------|-----------|
| 31337 | u92 bloodDeathCompany->u86 astraPrimarisPsy | (2256, 5522) | (1503, 5522) | EXACT | 753 (gros)|
| 12345 | u88 bloodDante->u86 astraPrimarisPsy        | (1148, 1720) | (1144, 1720) | EXACT | 4 (arrondi)|

- Cas 31337 : base=3011 pierce=15 armor=2008 hits=3 mods=[1.25] effects=[RapidAssault_ExtraDamage].
- Cas 12345 : base=1707 pierce=30 armor=2312 hits=4 mods=[0.7] effects=None.
- Sur ces deux seeds, TOUS les autres echantillons clean passent (7/8 et 5/6). Le SEUL cible qui
  diverge = **u86 (armure ~2000-2300)**, les DEUX attaquants Blood Angels.

## Attribution (PROUVE par le pattern)

- **MAX exact partout + overkill exact 3/3** => l'AGGREGATION per-coup (le refactor `PredictAttackRaw`
  boucle, #54) est FIDELE. Le residu n'est PAS dans l'aggregation.
- Le MIN est sous-predit offline (native garde le MIN plus haut) **uniquement en regime lourdement
  blinde**. Magnitude = de l'arrondi (delta 4) au significatif (delta 753, amplifie par RapidAssault).
- Un simple decalage de BASE est exclu (il bougerait AUSSI le max ; or le max matche). => mecanisme
  **MIN-only**.

## Mecanisme natif (LU, @18102d3f0)

`DamagePrediction.CalculateBaseDamageWithAllModifiers @18102d3f0` : apres
`GetBaseDamageWithFixedPiercedArmor` (base+perce+armure), applique des **bornes optionnelles**
`Nullable` (param_6 = borne basse, param_7 = borne haute) via :
- `FUN_180031890(0x11, ...)` = op MAX / plancher (floor) avec la borne,
- `FUN_18000c030(0x10, ...)` = op MIN / plafond (cap) avec la borne.
C'est le "plancher minDmg + MathMax" des notes RE. Quand la borne basse (param_6) existe, elle
**releve le MIN** (plancher) apres reduction d'armure.

## Hypothese root-cause (A CONFIRMER, ne pas asserter)

Le port offline (`engine/services/damage_prediction.py`) N'APPLIQUE PAS ce plancher minDmg
(`param_6`) : en regime blinde le MIN reduit passe sous le plancher natif -> offline trop bas.
A confirmer :
1. Tracer l'ORIGINE de `param_6`/`param_7` (callers de `CalculateBaseDamageWithAllModifiers` ;
   `GetBaseDamageWithFixedPiercedArmor @181030d10`) = quelle est la valeur du plancher (config
   d'arme minDmg ? predefinedRange @param_3+0x58 ? reduction bornee ?).
2. Verifier pourquoi RapidAssault (mods 1.25) AMPLIFIE l'ecart (delta 753 vs 4) : le plancher
   est-il applique AVANT ou APRES le x1.25 ? (ordre plancher/scalaire).
3. Note re-expert #52 (mourante) : "#49 vit dans la BASE fed to PredictAttackRaw (context[+0x58],
   tile-dependant via GetStat(5))". context[+0x58] = predefinedRange (min,max). A reconcilier avec
   le pattern MIN-only (un predefinedRange dont seul le MIN differe expliquerait max-exact/min-off).

## Etat #54 (Etape 2 validation)

- Refactor per-coup (aggregation) : VALIDE. Max exact + overkill 3/3 + 16 tests cibles +
  7/8 & 5/6 samples clean sur 2 seeds neufs.
- Residu MIN-side (ce fichier) : OUVERT. Re-ouvre le cote MIN de #49. Tache dediee creee.
- Prochain pas : slice re-expert (tracer param_6/param_7 -> port du plancher -> re-valider sur
  seeds 31337 + 12345, cibles u92->u86 et u88->u86).
