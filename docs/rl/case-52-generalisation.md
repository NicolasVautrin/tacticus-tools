# Case #52 — généralisation du batch : 4 seeds frais (MC1_67)

**Contexte** : après le 100 % des 4 étages sur 777/909/31337 (case-32), test de généralisation
sur 4 seeds jamais confrontés — **12345, 54321, 2468, 1357** — mêmes rosters, board MC1_67,
20 steps/seed (`engine_agreement_stages.py --build`). Résultats : `data/stages_ext_seeds.json`.

**Verdict : le 100 % ne généralise pas.** Les seeds frais exercent des kits jamais confrontés
(cooldowns plus profonds, summons actifs) :

| étage | référence (777/909/31337) | seeds frais |
|---|---|---|
| prédiction (paires confrontées) | 26/26 | 17/34 (50 %) — 12 mismatch-logic |
| utilité (pairUtility) | 26/26 | 29/34 (85 %) — 5 mismatch, tous famille damage |
| ability | 35/35 | 22/50 (44 %) |
| move | 51/51 | 54/65 (83 %) — dont 9 pos-downstream-of-ability |

## Tri des 28 misses ability par cause

### 1. `non-attack-oracle` (13) — playbooks/oracles non-damage jamais portés

Chaque ability = un playbook à porter (roadmap `dsl-vocabulary-catalog.md`) :

**✅ Tranche 1 RÉSOLUE (#56, verdict re-expert + port)** — deux NC natifs
(`EvaluateNonComparable`, jamais de `Make*Predictions`) :
- **ScarabHive (1007)** `@181158ab0` (necroSpyder) : summon 2 scarabs adjacents à la
  cible ; utilité CONSTANTE 1.0 par cible éligible, gate `#tuiles-libres-adj(cible) >= 2`
  (= N scarabs, `ScarabHiveAbility..ctor @181205170` : `+0xf0=2` ; slot 0x4e =
  `GetAdjacentTiles(target,1,1,1) @18105b660`). Port : `noncomparable/scarab_hive.py`.
- **CordClaw (1122)** `@181126670` (admecRuststalker) : utilité = **# ennemis adjacents
  à la TUILE D'ATTAQUE du caster** (slot 0x7e `GetAdjacentEnemies @18105af60` sur la
  position balayée — PAS la cible ; le compte inclut les non-éligibles, ex. décoy),
  MIN_UTILITY=1 (cctor `@181126af0`) ; cible = 1er ennemi ÉLIGIBLE adjacent à la position
  gagnante en ordre voisins natif FORWARD (hypothèse 2-cas, à durcir par validator).
  Port : `noncomparable/cord_claw.py`.
- Validé `data/stages_56_fix.json` : les 4 misses → HIT (positions EXACT), 0 cast
  parasite, 0 régression. Flags validator : ordre FORWARD, multi-cibles ScarabHive
  (générateur cible-first vs natif position-first — non départagé sur les cas connus),
  gate N=2 à exactement 2 tuiles libres.

**✅ Tranche 2 RÉSOLUE (#56-t2, verdict re-expert + port)** — trois NC natifs :
- **Poxwalkers (1040)** `EvaluateNonComparable @18115c6f0` (deathBlightbringer) : summon
  SELF-CAST, utilité CONSTANTE 1.5 (`Fix64.FromIntFraction(3,2)`), MIN=1 (cctor
  `@18115ca90`), cible = SOI, cast en place (keep-first). `GetUseProbability @18115ca00
  = TurnsStarted*0.2` = porte RNG per-appel NON modélisée (comme BlackRage/ItItches) →
  `should_evaluate=True`. Port : `noncomparable/poxwalkers.py`.
- **FoulInfusion (1038)** `@18113c670` (deathPutrifier) : buff SELF-CAST, utilité =
  `#amis-éligibles-adjacents(pos, self exclu)` + `(count>=2 && adjEnemies(pos)>0)`,
  MIN=2 (cctor `@18113c8f0`) ; amis = trait Nurgle 0x7ea via `abilityTargets` (pas de
  trait en dur). Réconcilié LIVE 7/7 positions (2468 s12). Port :
  `noncomparable/foul_infusion.py`.
- **HolyDuel (1050)** `@181144b00` (templChampion) : défi, utilité = `Attack(cible)`
  (`GetStat(cible,0)`), cible = argmax Attack parmi ennemis éligibles, MIN=0 (pas de
  cctor) ; gate `ShouldEvaluate @181144db0 = !EnemyMightBeKilledWithNormalAttack`
  (killSure=0, `MightBeKill` — DISTINCT du `WillBeKill` de Hammer/Stormcaller). Port :
  `noncomparable/holy_duel.py`.
- Validé (smoke agent session 60 + repro orchestrateur `data/stages_56t2_gen.json`) :
  les 3 misses → HIT, tranche 1 intacte. **1 régression move structurelle connue :
  2468 s4 u87 `generator-overfire`** — échange 1-pour-1 imposé par la porte RNG
  Poxwalkers (natif : False@s4 → move, True@s5 → cast ; même prob non-déterministe).
  Flags validator : range=1 FoulInfusion (hypothèse 7/7, constant CustomRange non
  décodé), bonus ennemi-adjacent non exercé, tie max-Attack HolyDuel, gate MightBeKill
  sensible à predOptimistic (faux SKIP), cascade over-fire Poxwalkers multi-tours.

**✅ Tranche 3a RÉSOLUE (#56-t3a, verdict re-expert + port)** — les 3 NC du seed 54321 :
- **GrapnelLauncher (1090)** `EvaluateNonComparable @18113f300` (spaceHound à s13) : utilité
  CONSTANTE 1, MIN=1 (cctor `@18113f600`), aucun gate ; cible = 1er ennemi éligible fromHere,
  cast en place (keep-first). Port : `noncomparable/grapnel_launcher.py`.
- **EarlyWarningOverride (1077)** `@18112e880` (tauCrisis) : self-cast POSITIONNEL, util(P) =
  `Σ_E [ +50 si P hors de portée de E (slot 0xc4) − 10×dist(P,E) ]`, gate nearest-enemy < 9,
  MIN=1 ; réconcilié AU BIT 12/12 positions (s9 : natif MOVE→(3,7)=argmax puis cast). Port :
  `noncomparable/early_warning_override.py` (approx portée-arme-max — flags validator).
- **DarkTalonStrike (1092)** `@1811299a0` (darkaAzrael) : cible = TILE (aim du beam ; tgt 43 =
  entité-tuile (3,4)), util = #ennemis CONTINUS sur le rayon droit depuis le caster (`_beam_count`
  cube-line, AU BIT 5/1/1), MIN=2 (cctor `@181129e10`). Port : `noncomparable/dark_talon_strike.py`
  (flags : variante beam coudé + aim post-move non modélisés).
- Smoke agent 54321 : s9/s11/s13 → HIT, 28/32 records identiques, misses hors-périmètre inchangés,
  zéro cast parasite (2468/1357).

Restants (3 misses, tranche 3b) :
| SendInTheNextWave | 1016 | 1357 s9 |
| Incursion | 1021 | 1357 s11 |
| ExcruciatingFrequencies | 1197 | 1357 s7 |

### 2. `gate` (5) — **les SUMMONS n'attaquent JAMAIS chez nous — ✅ RÉSOLU (#53)**

54321 s14 u159, s15 u161 · 1357 s15 u135, s16 u139, s17 u150 : le natif caste **69**
(attaque normale) avec un summon, notre moteur émettait un move pur.

**Cause racine (probe_53_summon.py, live 1357 s15)** : `build_predictor` est COLD
(1×/runner au pas 0) → un summon spawné mid-bataille (u135 tyranNpc2RipperSwarm) est
présent dans le decisionView frais (visualId OK), le combatSnapshot frais et les
attackPlans natifs rankés, mais ABSENT de `ctx_by_id`/`vis_by_id` → `scene.ctx(summon)
= None` → `make_normal_attack_predictions = None` → toutes tuiles refusées (« gated »)
→ move pur. `refresh_shields` ne rafraîchissait que les tables DYNAMIQUES.

**Fix (`engine/playbook/scene.py`)** : extraction du bloc per-unit statique de
`build_predictor` en `_hydrate_static_unit` (ctx/vis/mult/ablvl/abstate) + hydratation
dans `refresh_shields` des entityIds inconnus du snapshot frais (decisionView LAZY,
1 RPC uniquement quand un nouvel id apparaît). Le natif lit l'ECS live par décision —
l'hydratation retire la staleness de NOTRE seam, elle n'invente rien.

**Validation (re-run 1357+54321, `data/stages_53_fix.json`)** : bucket `gate` = 0
(était 5) ; u159/u161/u135/u150 attaquent, positions EXACT ; net −5 misses, zéro
régression sur les autres étages.

### 3. `prediction` (4) — fidélité per-target (même ability, mauvaise cible)

- 54321 s5 u83 : 69→t93 vs t95 · 54321 s18 u85 : GreatFrostAxe(1089)→t93 vs t87
- 54321 s6 u85 : natif 69→t95, nous GreatFrostAxe(1089)→t95
- 1357 s13 u91 : MightFromBelow(1165)→t153 vs t135

### 4. `utility-logic` (3)

- 12345 s14 u87 : 69→t77 vs t85 · 12345 s15 u89 : MurderousSwing(1137)→t83 vs t81
- 54321 s12 u93 : natif 69→t83, nous BlackRage(1163)→t161

### 5. `native-gate` (2) — le scorer natif préfère NOTRE paire (gate/éligibilité non mirroré)

- 2468 s16 u79 : 69→t89 vs 69→t91 · 2468 s18 u77 : natif 69→t91, nous MartialInspiration(1191)→t91

### 6. `nc-pair` (1) : 54321 s8 u81 HammerOfWrath(1153)→t91 vs t93

## Étage UTILITÉ — 5 mismatches à deltas PLATS — ✅ RÉSOLU (#54, verdict re-expert + port)

Deux causes distinctes, toutes deux élucidées au décompilé et réconciliées à l'exact :

**+50 (2×, cibles daemon) — BLOCK-SCENARIOS de la prédiction, PORTÉ (#54A)** :
`get_WillBeKill @18102bef0` lit `list[0]@0x50` (scénario « tous les coups bloqués »,
créé par `CalculateDamagePredictionScenario @18102ed00`, mergé par index dans
`Add @18102a710`) quand la liste est non-vide — WillBeKill = « kill garanti MÊME si la
cible bloque ». Cible blackSmnBloodletter (trait **Daemon** : 25 % chance, block = 50 %
de SA stat Attack courante = 1097) : list[0].rawMin = 5388 − 3×1097 = 2097 < 3888 →
PossibleKill(50), pas DefinitelyKill(100). `MightBeKill @18102be30` reste scalaire rawMax.
`WillBeOverkill @18102ba40` lit aussi list[0]. **Port** : `DamagePredictionResult.
block_raw_min` + `defender_block_amount` dans la boucle multi-hit (`damage_prediction.py`),
`DaemonExtraBlockEffect` (factory `Daemon_ExtraBlock` 1034, `loki/hits.py`), helper
`defender_prediction_block_amount` (`prediction.py`, scalaire 7/8 + sources d'effets),
killSure/DefinitelyOverkill block-aware (`probable_damage_event.py`, `utilities/damage.py`),
harnais recompute (`_fields_from_native_event(block_amount)`). Validé `stages_54a_fix.json` :
étage utilité 16/17, les deux +50 fermés à ±0.

**−40 (u81 bloodIntercessor) — ✅ RÉSOLU (#58, re-expert)** : feuille attack
`TriggeredAbilitiesUtility` = AggressiveOnslaught (1248). Chaîne RE complète : le délégué
per-summon = `TriggeredAbilityPlaybook.GetUtilityValue @181510570` = **lookup config plat**
`Utilities.Default.TriggeredAbilities.AggressiveOnslaught_PerFreeTileAfterCharge = 40` (BC —
le 40 ÉMERGE de la config, zéro hardcode). Corps `d__3.MoveNext @181173e70` : GATE 1 =
CasterTile adjacent à la cible ; GATE 2 = `IsTargetInAttackRangeForSummon @1810700d0` ;
valeur = `min(#tuiles-libres-adjacentes(cible), GetMaxSummon−1) × weight`, avec
`GetMaxSummon @180e156c0` = `constants.nrOfSummons` (=2). Port :
`engine/playbook/aggressive_onslaught.py` + registre `TRIGGERED_ATTACK_PLAYBOOKS` (psyker.py).
Smoke agent : les 3 paires −40 → delta 0.0000, contrôles 1357 (non-adjacent → gate 0) intacts.
Flags validateur : cap min() exercé seulement à 1 (nrOfSummons=2) ; GATE 2 partiel (élévation
non modélisée) ; `allowTemporary` divergent (sur-comptage possible hors MC1_67). Finding
structurel inchangé : ~60 triggered ont un corps attack non-trivial → complétion agreement-driven.

**⚠ Méthodologie (2026-07-21)** : les trajectoires natives batch sont DÉTERMINISTES par seed
et **stables à travers les relances du jeu** (vérifié : 50/50 clés seed/step/uid identiques
entre instances). En revanche, **ne JAMAIS éditer `engine/**` pendant qu'un batch tourne**
(imports Python lazy → module lu à moitié écrit → walks corrompus, inventaire rétréci —
c'était la cause du batch anormal à 19 confrontations). Batch rétréci = contaminé → rejeter
et relancer.

**Erreur compensatoire DÉMASQUÉE par le port (bucket #57) — ✅ RÉSOLU (#57a)** :
1357 s15 u135 était un HIT par annulation de deux erreurs (notre raw gonflé 6580/9865 vs
natif 5388/8079 = ×1.221 SUR L'ATTAQUANT SUMMON ripper swarm, ET killSure gonflé). Ground
truth (probe_57a_summonatk.py + probe_57a2_swarm.py, 1357 s15) : le +22 % était en réalité
**DEUX gaps qui se composaient** :

1. **Hits 5 off vs 3 nat — trait Swarm, gap de FEED.** u135 = tyranNpc2RipperSwarm (5
   membres, hp 2576 → 3 vivants). `SwarmAbility.CreateBehaviour @181225e20` (arbre DSL) poste
   un stat-mod **EXTRA_HITS = −Min(Difference(StatAmount(Owner,NumberOfMembers,INITIAL), …),
   StatAmount(Owner,NumberOfMembers,MISSING))** via `AddOrUpdateStaticStatModifierEffect`
   (effectType 0x3fd = 1021 `Swarm_HitReduction`, vérifié live : `statDelta.extraHits = −2`,
   `numberOfMembers 5→3`). Notre ctx (hydraté au SPAWN, #53) figeait extraHits=0. **Fix** :
   canal per-pas `extra_hits_cur_by_id` (build_predictor + refresh_shields, scene.py) +
   accesseur `scene.extra_hits_current` consommé au call-site hits de `prediction.py`.
2. **Base 2742 (INITIAL) off vs 2245+400=... nat — mods NON-positionnels exclus à tort.**
   INITIAL(u135)=1096, CURRENT=1496 : le natif prédit per-hit = 1.2/1.8 × **1496** (CURRENT).
   La modification +400 = **`SummaryExecution_BaseEffect` (1043), entité-effet 116, source
   u83** — le fameux « résidu +400 » de #153, enfin identifié : PAS une aura positionnelle
   (sélecteur `Friends(Owner, UnitsWithTrait(0x3f7))` sans nœud d'adjacence, décompilé
   `CreateTargetSelector @180f6f8a0` ; magnitude `ConfigVar(1033)` via EffectSource) ; buff
   present aussi sur u139/u150 ; **invisible de decisionView.effects** (ValueModification
   keyée par l'entité-effet — cf. memoire aura-unexplained-stat-delta). **Fix (modèle de
   base #57a, prediction.py)** : `base = attack_current(pas) − aura_modèle(pos réelle) +
   aura_modèle(tuile candidate)` — algébriquement INITIAL + mods-non-aura + auras
   ré-évaluées (#153) ; identique à l'ancien modèle quand aucun mod non-aura (zéro
   régression attendue). Validé : confrontation off==nat EXACTE champ par champ
   (5388/8079, hits 3, blockRawMin 2097, kill/killSure).

## Étage PRÉDICTION — champs divergents

rawHealthDmgMin/Max (11), healthDmgMin (5), killSure (2), healthDmgMax (2), kill (2),
healAmount (1).

### État après pile #57a + #57b(Pinned) + #58 (batchs `stages_58_gen.json` / `stages_58_ref.json`)

Gen 4 seeds : **prédiction 25/34 (73 %)** · **utilité 34/34 (100 %** — les 3 ×−40 fermées par
#58**)** · ability 34/50 (68 %) · move 55/65 (85 %). Diff paire-à-paire vs pré-fix :
FIXED = les 4 ×0.70 Pinned (1357 s13, 54321 s12/s14/s16), **0 REGRESSED**. Référence
777/909/31337 : **4×100 % maintenu** (26/26 · 26/26 · 35/35 · 51/51).
Restent 9 mismatch-logic prédiction : coups additionnels ~4488/~2245 (12345 s18, 54321 s7,
2468 s14/s15) · ×2 exact (1357 s18) · ×1.22 (54321 s19) · composites (54321 s6/s18, 1357 s16).

⚠ CAVEAT mesure : `stages_58_gen` tournait DÉJÀ avec les 3 fichiers tranche-2 #56-t2
(déposés par l'agent dans l'arbre principal en cours de session) → ses chiffres
ability/move incluent tranche 2. Les étages prédiction/utilité (confrontés sur les
paires NATIVES) n'en dépendent pas — les claims 25/34 et 34/34 de la pile #57/#58
restent purs.

### État après pile #57c (3 effets dégât) + tranche 3a #56 (batchs `stages_57c_gen.json` / `stages_57c_ref.json`)

Gen 4 seeds : **prédiction 29/34 (85 %)** · **utilité 34/34 (100 %)** · **ability 37/50 (74 %)** ·
move 55/65 (85 %). Diff paire-à-paire vs `stages_56t2` : prédiction **+4 FIXED** (12345 s18
LordOfTheHost, 54321 s7 Doom, 2468 s15 CordClaw, **+ 54321 s6 u85 composite** — la part Doom le
fermait), **0 nouveau miss** ; ability **+3** (54321 s9/s11/s13, tranche 3a), **0 perte** ; move
**liste identique** (10 misses pré-existants). Référence 777/909/31337 : **4×100 % maintenu**.
Restent **5 mismatch-logic prédiction** : 54321 s18 u85 (composite), 54321 s19 u77 (×1.22),
2468 s14 u89 (**fold LightImUp**, mécanisme identifié, site à RE), 1357 s16 u139 (swarm
composite), 1357 s18 u81 (×2 exact).

### État après tranche 2 #56-t2 (batchs `stages_56t2_gen.json` / `stages_56t2_ref.json`, validé orchestrateur)

Gen 4 seeds : prédiction 25/34 · utilité 34/34 · **ability 34/50** · move 55/65 —
identique à `stages_58` (qui incluait déjà tranche 2, cf. caveat). Diff vs la vraie
baseline pré-tranche-2 (`stages_57a_gen`, 08:43) : **ability +3** (2468 s5 u87
Poxwalkers, 2468 s12 u91 FoulInfusion, 1357 s12 u87 HolyDuel → HIT) ; **move −1**
(2468 s4 u87 = generator-overfire RNG Poxwalkers, structurel) et **move +1** (54321
s18 u85 fixé par #57b) — net 0. Référence 777/909/31337 : **4×100 % maintenu**
(26/26 · 26/26 · 35/35 · 51/51).

### Triage post-#57a (batch `stages_57a_gen.json`, 4 seeds, 2026-07-21)

Diff vs batch précédent : **2 paires fermées** (1357 s15 u135, s17 u150 — les 2 swarms),
**0 régression**. Restent **13 mismatch-logic**, par famille (ratios nat/off EXACTS sur
min ET max sauf mention) :

| Famille | Cas | Signature | Piste |
|---|---|---|---|
| **×0.70 = ATTAQUANT `Pinned` — ✅ RÉSOLU (#57b)** | 54321 s12 u93, s14 u159, s16 u81 ; 1357 s13 u91 | nat = off × 0.700 | PAS Terrifying (déjà porté #152), PAS le défenseur : probe 54321 s16 → attaquant u81 bloodIntercessor porte `Pinned`, défenseur u89 admecRuststalker zéro stat-mod. `PinnedEffect.CreateEffectDamageBonusForAttack @180f5e8e0` = `ForPercentIncrease(OwnerIsCaster, −EffectConfig(0))` ; EffectConfig(0) = BC `Effect.PinnedDmgReductionPct` = 30 (mapping ordinal↔champ DTO prouvé par `InitEffectConfig @18106e9c0`, recoupé Stunned ordinal 2 bit-exact). Port : `PinnedEffect.create_effect_damage_bonus_for_attack` (status.py, canal attaquant, modèle Stunned). Validé : off == nat EXACT (2192/3288, probe_57b_x070.py). Fausse piste écartée : `Camouflage_HitReductionEffect @181107180` = malus de HITS ranged (DSL ConditionalAmount −const[0x4d]/[0x4b]/[0x2c], min 1) — hits égaux des deux côtés ici, mais **gap distinct à porter** (non enregistré factory). |
| **coup(s) additionnel(s) ~4488/~2245 — 🔎 IDENTIFIÉS (#57c, probe_57c_flathits.py, mécanismes décompilés)** | 4 mécanismes DISTINCTS : (1) 12345 s18 u77 bloodSanguinary→t95 : **aura Dante `LordOfTheHost_ExtraDamageEffect` `CreateEffectDamageBonusForAttack @180f56e30`** = `ForAddition(IsMeleeAttack & OwnerIsCaster, ConfigVar(8=extraDmg))` — amis ≤2 hexes du porteur avec RapidAssault/Flying, additif PRÉ-perçage PAR COUP, ré-évalué à la tuile candidate (u77 réel dist-3 de Dante : AUCUN effet posé live, bonus quand même — modèle RitesOfBattle #49) ; a=extraDmg[50]×1.8=898.2, ×1.25 RapidAssault, ×4 coups = +4488 EXACT min&max. (2) 54321 s7 u79 genesPatriarch→t95 : **aura Farseer `Doom_extraDmgEffect @180f3f780`** = `ForAddition(OwnerIsTarget & AreFriends(att, source) & !AreEqual(att, source) & (Aeldari\|IsNormalAttack), ConditionalAmount(Aeldari→extraDmg_2, extraDmg))` — cible ennemie à EXACTEMENT range 2 du porteur (Shadowsun dist-2 d'Eldryon ✓, aucun effet posé sur elle non plus) ; a=898 pré-perçage, l'armure 1806 mange la moitié bloquée : 5060/6470 EXACT. (3) 2468 s14 u89 orksWarboss→t177 (RANGED dist 3, notre arme Projectile 1-hit CORRECTE) : follow-up **LightImUp** (passif : 2e attaque 3×Projectile) foldé par le natif = groupe [0.8,1.2]×3×minDmg[50]×1.8=1495.8 → +3591/+5385 EXACT — site de fold à RE (`AddAdditionalHitsToPrediction @180faff30` via ALoki_NormalAttackAbility.PredictAttack ; provider LightImUp à localiser). (4) 2468 s15 u83 admecRuststalker : **`CordClaw_AdditionalHitsEffect.CreateAdditionalHits @180f3a900`** = groupe `{OwnerIsActor, count=GetNumberConstant(0x32)=nrOfHits_2=2, minmax=GetMinMaxDamage2=vars minDmg_2/maxDmg_2, profile=DirectDamage}` : per-hit [886,1330]=[443,665]×2.0 EXACT (canal #179, moule SquigHound). | flats = additive pré-perçage ; groupes = #179 | **PORTÉS + VALIDÉS BIT-EXACT (probe_57c ×3)** : `LordOfTheHostExtraDamageEffect` + `DoomExtraDmgEffect` (extra_damage.py, canal `create_aura_attack_damage_bonus_for_ally` étendu ctx cible : tgt_id/t_pos/tgt_team/att_faction/is_normal_attack dans `_apply_ally_attack_dmg_bonus`) ; `CordClawAdditionalHitsEffect` (hits.py, canal #179). Selectors décompilés : LordOfTheHost `@180f56fb0` = Unique(UnitsWithTrait(SurroundingFriends(range 2), RapidAssault 0x413) + (…, Flying 4)) ; Doom `@180f3fa80` = SurroundingEnemies(r) − SurroundingEnemies(r−1) (ring exact). Magnitudes : extraDmg[ablvl 50 porteur]×mult 180 = 898.2/coup pré-perçage (Dante 1378 / Eldryon 1114 captés ACTIFS sur les porteurs). RESTE : **C = fold LightImUp** (RE du provider dans `AddAdditionalHitsToPrediction @180faff30`) + `LordOfTheHost_ExtraHit` (1377, +1 hit mêlée amis ≤50 % HP — non exercé, non porté). |
| **×2 exact** | 1357 s18 u81 | nat = 2 × off | multiplicateur ×2 côté cible (MkXGravis-like) ou double-dégât attaquant non porté. |
| **×1.22** | 54321 s19 u77 | nat = off × 1.22 | base attack : buff non modélisé (vérifier statModSources au pas). |
| **composites** | 54321 s6 u85, s18 u85 ; 1357 s16 u139 | ratios mixtes | à sonder individuellement (s16 u139 = swarm : vérifier hits + cap membres). |

**healAmount ×3 — ✅ RÉSOLU (#55)** : 12345 s13, u91 = **adeptHospitaller** (⚠ les entityIds
varient PAR SEED — pas le Biophagus), `Heal(18)` granted, self. Natif 6024 = attack 2008 ×
**WeaponHighestHits(arme) = 3** (Bolter 3 hits) : le `× Max(WeaponHighestHits,1)` de l'arbre
DSL `HealAbility.HealAmount @180e345b0` (décompilé #45c) est RÉEL — le port le bridait à ×1
faute de datapoint multi-hit (tous les soins confrontés avant #52 étaient à arme 1-hit).
Probe : `probe_55_heal.py`. Fix : `heal_amount_weapon(attack, weapon_highest_hits)`
(`engine/predict.py`) + 2 call-sites (`action_generators.py`, `_confront_nonattack` du
harnais). Validé : `data/stages_55_fix2.json`, healAmount hors des champs divergents,
étage utilité 12345 = 9/9. NB : la branche repair (`hpToRepair` = arme synthétique 1 coup)
n'est PAS concernée (docstring précisée).

## Move résiduels (hors downstream)

- `move-formula` 12345 s5 u89 : natif (0,4) [tile 30, mindist −700, pathdist 7] vs nous
  (1,4) [tile 30, mindist −600, pathdist 6]. **Sondé (#57a, probe_57_move.py)** :
  u89 = worldExecutions (TrophyTaker passif, MurderousSwing actif) ; le natif CONFIRME
  nos pathdist ((0,4)=7, (1,4)=6 via `pathDistToEnemies`) et les deux tuiles sont
  movable ⇒ le flip vient d'un TERME de tuile ≥ +100 à (0,4) non modélisé, PAS du
  pathfinding. Éliminé : TrophyTaker (aucun playbook IA — passif crit pur, symbols
  ghidra) ; `MaxDistanceToEnemiesUtility @1810f02a0` (formule décompilée
  `Σ_E [W1 − (W1−W2)/pathlen(tuile,E)]`, W1=FarthestEnemy=100) = écart ~10-15 pts
  entre les 2 tuiles, insuffisant seul. **Prochain pas : breakdown L3 par-feuille aux
  2 tuiles** (attendre une session calme — L3 est session-globale, 3 agents en vol).
- `generator-overfire` 1357 s6 u85 : nous castons, le natif bouge (3,2).

## Priorisation (proposée)

1. **A — summons n'attaquent pas** (gate ×5, racine unique probable, quick win).
2. **B — termes flat pairUtility** (+50 summon-cible / −40) : diff config, réconciliation exacte.
3. **C — heal ×3** (2008 vs 6024, magnitude).
4. **D — backlog 11 playbooks non-attack** (roadmap vocabulary, prioriser ScarabHive/CordClaw ×2).
5. **E — prediction per-target (4), native-gate (2), move-formula pathdist (1)** : cas à sonder.
