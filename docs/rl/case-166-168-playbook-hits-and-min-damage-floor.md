# Case #166/#167/#168 — bespoke playbook hits/profil + le PLANCHER 1-degat-par-coup manquant

**Statut** : #166/#167/#168 RESOLUS + VALIDES live (tous OK). #170 (plancher 1-degat/coup, decouvert ici) porte
+ valide (combat inchange). Confronte live gqfc5mff6c (session chaude, board MC1_67, cible ultraTitus armure 2312).

## Reframing : les descriptions de taches etaient PERIMEES

Les 3 taches ont ete filees pendant l'audit #165 avec des symptomes ("base moteur=0", "ENG_ZERO", "gap HITS
7 vs 1 + base") qui NE tiennent PLUS a la confrontation live fraiche (session chaude, predicteur rebuild). La
verite terrain (sweep vs `ultraTitus` armure 2312, `--board MC1_67`) :

| ability (id) | carrier | live | eng AVANT | hits l/e | vrai gap |
|---|---|---|---|---|---|
| Executioner (1066) | eldarFarseer | [9537,9537] (cap HP) | [1515,2273] | 7/1 | **staleness sweep** (turnsStarted) + profil |
| MultiThreatEliminator (1006) | necroDestroyer | [6,6] | [862,1292] | 6/1 | **hits** (1->6) + **pierce** (Gauss60->0) + **plancher 1/coup** |
| FragBomb (1017) | astraBullgryn | [6,6] | [900,1344] | 6/6 | **pierce** (Blast15->0) + **plancher 1/coup** |

## Base commune des 3 (et de #163 Harvester) = `ArcScourgeAbility.GetDamage @1811b3800`

`ArcScourgeAbility.GetDamage @1811b3800` = `AActiveAbility.MinMaxDamageAverage @180fb2cc0` = **avg(minDmg 0xc,
maxDmg 0xd)** = EXACTEMENT le generique `AActiveAbility.get_damage()` du port. Donc la base n'a JAMAIS ete a 0 :
les 3 configs ONT minDmg/maxDmg (FragBomb 728/1091, MTE 1164/1455, Executioner 582/2183 a lvl65). Le "base=0"
des taches etait un artefact de mesure perime. Aucun override de base requis.

## #166 Executioner (1066) — RESOLU + VALIDE (OK)

`ExecutionerPlaybook.GeneratePredictions @181130150` : base = `ArcScourgeAbility.GetDamage` (avg) ; hits =
`ExecutionerAbility.GetHits @1811da4a0` = `DSLFactory.RoundsStarted` (= stat 12 `turnsStarted` du CASTER,
snowball : +1/round) ; **profil = `Nullable(0xd=13=Psychic)`** (pierce 100 -> armure IGNOREE). `MakeDamage
Predictions @1811303b0` ajoute une 2e cible chainee si le Sum(degats) >= HP de l'autre cible (hors cible principale).

Le port avait DEJA `ExecutionerAbility.get_special_hits = turnsStarted` (mig #122). Le hits=1 du sweep etait un
**bug de MESURE** : `predict_sweep.build_rows` construisait le `build_predictor` AVANT le drive (turnsStarted~0
fige), sans jamais le reconstruire -> l'oracle lit l'etat live (round 8) mais le moteur lit t=0. **Prouve**
(probe166) : un `build_predictor` FRAIS post-drive capture `eldarFarseer stat(TURNS_STARTED)=8` correctement
(combatSnapshot expose bien `turnsStarted`, statTypes le mappe a 12).

FIX (2 volets) :
1. `predict_sweep.py::build_rows` : deplacer `build_predictor` APRES le drive+cycle -> stats dynamiques
   (turnsStarted, actorStats) COURANTES a la comparaison. (Benefice general : toute ability snowball —
   MartialInspiration TotalAttacksMade, DakkaDakkaDakka TimesRepaired — etait mal mesuree pareil.)
2. `_PLAYBOOK_PROFILE_OVERRIDE[1066] = "Psychic"` (mirror param_8=Nullable(0xd)). Le profil derive par defaut
   ne garantissait pas Psychic.
-> sweep : Executioner **OK=2** (eng == oracle [9537,9537], hits 8/8).

## #167 MTE (1006) — hits + profil portes ; reste le plancher

`MultiThreatEliminatorPlaybook.MakeDamagePredictions @18114d530` : base = `ArcScourgeAbility.GetDamage` (avg) ;
**hits = champ STATIQUE = 6** (`MultiThreatEliminatorAbility.cctor @1811f5cb0` : `**(class+0xb8) = 6`, PAS de
config — l'ability n'a AUCUN nrOfHits, juste extraHit=1 consomme par le COMBAT `GetExtraHits @1811f5b60`) ;
**param_8 = null** -> profil None (pierce 0).
FIX : sous-classe `MultiThreatEliminatorAbility.get_special_hits -> 6` (registre) + `_PLAYBOOK_PROFILE_OVERRIDE
[1006]="None"`. Le generique rendait 1 coup (config nrOfHits absent) + Gauss pierce 60.

## #168 FragBomb (1017) — profil porte ; reste le plancher

`FragBombPlaybook.MakeDamagePredictions @18113c9a0` : base = `ArcScourgeAbility.GetDamage` (avg) ; main hits =
`ArmoriumCherubAbility.GetHits @180fb16c0` = config `0x2f`(nrOfHits)=**6** (le generique le lit deja -> hits 6/6
OK) ; **param_8 = null** -> profil None (Blast15 -> pierce 0). + cibles bonus (`FragBombAbility.GetAdjacentTargets`,
hits = `BringerOfDespairAbility.GetHitsToBonusTarget @180fb1690` = config `0x32` = nrOfHits_2=3) = volet AoE
splash NON porte (comme #39, hors cible principale).
FIX : `_PLAYBOOK_PROFILE_OVERRIDE[1017]="None"`.

## #170 : plancher natif "1 degat de sante par coup" MANQUANT au port (decouvert ici, PORTE + VALIDE)

Apres les fixes profil+hits, MTE et FragBomb rendaient **eng=[0,0]** (hits corrects 6/6) la ou l'oracle rend
**[6,6]**. Cause : quand `base±20% - armure < 0` (pierce 0 vs cible blindee), le NATIF planche chaque coup a
**1 degat de sante** ; le port planchait a **0**.

RE (re-expert #170, VERDICT PROUVE) :
- Le plancher vit dans **`PredictAttackRaw` @VA `0x181035682`** : `MinMaxDamageFix64.MathMax(&dmg, Fix64.One)`
  (`MathMax @181052130` remonte min ET max a 1), APRES `CalculateBaseDamageWithAllModifiers`+`ApplyCap`
  (percage+armure+%-mods+defenseur), AVANT `ApplyTraitDamageLimitsToDamage`.
- **Valeur = literal 1** (Fix64.One = static `DAT_183239470+0xb8 +0x20` = 0x100000000). Le `+0x28`=Fix64.Zero
  est le plancher 0 que lit `GetDamageWithPiercing @1815598b0` (d'ou le max(0,...) du port). PAS un stat/config.
- **PER-COUP** (GenerateMultiHitAttackPredictions @181409da0 boucle par coup) -> 6 coups x1 = [6,6].
- **PREDICTION SEULE** : le COMBAT `CalculateAbilityDamage @18102cb50` planche a **0** (`Fix64.Max(base,0)`),
  PAS de Fix64.One. => NE PAS toucher le helper partage `get_damage_with_piercing` (casserait le combat).
- **GATE** : coup CONNECTE et non entierement absorbe par le BOUCLIER (Nullable bouclier sans valeur).

FIX (port, PREDICTION SEULE) : `engine/services/damage_prediction.py::predict_attack_raw`, apres capped_reductions
(GuardianOrganism) et AVANT target_limits (mirror ordre natif) : `if rem_lo: lo = max(lo, 1)` / `if rem_hi: hi =
max(hi, 1)`. Le gate `rem>0` = base non entierement shield-bloquee (rem = mm - blk) : coup absorbe par l'ARMURE
(rem>0, lo=0) -> 1 ; entierement absorbe par le BOUCLIER (rem=0 -> lo=0) -> reste 0. Sur cible non blindee le
degat > 1 -> max(.,1) no-op (n'affecte QUE le cas pierce-0/armure-lourde). `predict_attack_raw` est
PREDICTION-ONLY dans le port (seuls `get_multi_hit_attack_prediction` l'appelle ; le combat passe par
`apply_pierce_and_modifiers`/`get_base_damage_fix64` direct) -> combat intact.

VALIDATION LIVE : MTE [6,6]/[6,6] OK, FragBomb [6,6]/[6,6] OK, Executioner OK (pierce 100, plancher no-op),
normales OK (degat>1, no-op). GARDE COMBAT : `test_damage_normal_armored_live` + `test_damage_roll_live` 3/3
PASS (combat planche toujours a 0). GARDE PREDICTION : `test_predict_live` 2/2 PASS (pas de regression).

**MAJ 2026-07-20 (#42) — gate RAFFINE** : le mapping `rem>0` etait une approximation valide UNIQUEMENT
sans bouclier. Mesure discriminante 777 s11 u95 ab1150 -> u81 (bouclier 3989) coup 3 PARTIELLEMENT
absorbe (rem = 1117-639 = 478 > 0) : le natif n'applique PAS le plancher (healthDmgMin reste 0).
Lecture fidele du gate natif « Nullable bouclier sans valeur » : des que la CIBLE a un bouclier, le
HitDamage porte une valeur de block (meme partielle) -> plancher JAMAIS applique. Port : `if
target_shield <= 0:` autour des `max(.,1)` (le sous-gate `rem>0` reste pour le cas base nulle).
Detail : case-30-raw-bounds.md §MAJ #42.

**REVELATION #164** : CrushingClaws "[2,2] bit-exact" (case-164) etait en fait **eng=[0,0] vs live=[2,2]**, classe
OK par la TOLERANCE `TOL=3` du sweep (2 coups -> ecart 2 <= 3). Le port n'avait JAMAIS eu le plancher 1/coup ; il
etait juste masque a faible nombre de coups. A 6 coups (MTE/FragBomb) l'ecart (6 vs 0) depasse TOL -> ENG_ZERO
visible. Le fix #170 rend CrushingClaws VRAIMENT [2,2] (confirme live : eng [2,2] == live [2,2], hits 2/2). Le fix
profil de #164 reste correct (pierce 0 requis) ; seule sa VALIDATION etait masquee par la tolerance.

## Lecon

Une divergence "hits" ou "base=0" a la confrontation peut cacher (a) un bug de MESURE du harnais (predicteur
stale — turnsStarted #166), (b) un gap GENERAL sous-jacent masque par la tolerance (plancher 1/coup, visible
seulement a fort nombre de coups). Toujours reconfronter live FRAIS avant de porter, et dumper les VALEURS
(pas seulement le statut OK/MAJOR) — un OK peut etre un [0,0]-dans-la-tolerance.
