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

### État après #57c-C (ExplosiveMaladies) + tranche 3b #56 (batchs `stages_57d_gen.json` / `stages_57d_ref.json`)

Gen 4 seeds : **prédiction 30/34 (88 %)** · **utilité 34/34 (100 %)** · **ability 40/50 (80 %)** ·
**move 56/65 (86 %)**. Diff paire-à-paire vs `stages_57c` : exactement **5 FIXED, 0 régression** —
1357 s7 u79 (ability **+ move**, ExcruciatingFrequencies 1197 cible-tuile 44 + position exacte),
1357 s9 u83 (SendInTheNextWave 1016), 1357 s11 u93 (Incursion 1021), 2468 s14 u89 (prédiction,
aura ExplosiveMaladies — 2468 passe à **8/8 prédiction**). Référence 777/909/31337 : **4×100 %
maintenu** (26/26 · 26/26 · 35/35 · 51/51). Restent gen : prédiction 4 (54321 s18/s19 composite+
×1.22, 1357 s16 swarm-composite/s18 ×2), ability 10 (4 utility-logic, 3 prediction-per-target,
2 native-gate, 1 nc-pair), move 9 (6 downstream, move-formula 12345 s5, 2 generator-overfire RNG).

### État après #57d + #57e (batchs `stages_57e_gen.json` / `stages_57e_ref.json`) — PRÉDICTION 100 %

Gen 4 seeds : **prédiction 34/34 (100 %)** · **utilité 34/34 (100 %)** · **ability 44/50 (88 %)** ·
**move 58/65 (89 %)**. Diff vs `stages_57d` : **+4 prédiction / +4 ability / +2 move, 0 régression**
(1357 s16 member-cap Swarm + s18 MartialKatah ; 54321 s18 GreatFrostAxe + s19 CyclicIonBlaster ;
ability : 54321 s5+s6 et 1357 s13+s15 basculés par ricochet des prédictions per-target corrigées —
le member-cap Swarm à lui seul a flippé 3 choix de cible ; move : 2 downstream 1357). Référence
777/909/31337 : **4×100 % maintenu**. **Les étages PRÉDICTION et UTILITÉ du batch de généralisation
sont fermés.** Restent : ability 6 (utility-logic 12345 s14/s15 + 54321 s12, native-gate 2468
s16/s18, nc-pair 54321 s8), move 7 (3 downstream des ability, move-formula 12345 s5, 2
generator-overfire RNG structurels). Caractérisation du reliquat : 12345 s14 et 2468 s16 = le natif
prend une paire MOINS bien notée par son propre pairUtility (cf.eng > cf.nat) → gate caché ou ordre
intra-tour ; 12345 s15 = tie exact 167.86 (MurderousSwing t83 vs t81) → tie-break d'énumération ;
54321 s12 = off offre BlackRage(1163)→t159 que le natif ne score même pas (cf null) → gate à
mirrorer ; 2468 s18 = MartialInspiration(1191) bloqué natif (CanUseAbility ?).

### #57e RÉSOLU : les 2 miss prédiction 54321 (s18 GreatFrostAxe + s19 CyclicIonBlaster)

**54321 s18 u85 (spaceWulfen ab 1089 GreatFrostAxe → t93, nat = off ×0.889 uniforme)** =
**base minDmg SEUL** : `GreatFrostAxePlaybook.MakeDamagePredictions @18113fbd0` passe
`Get(GetVariableForLevel(0xc=minDmg, state))` à `GenerateMultiHitAttackPredictions` — PAS l'avg
(minDmg+maxDmg)/2 du chemin générique (hits = const 0x2f = 4 et profil = config Piercing 80,
identiques au générique). Signature qui a tranché : centres per-hit off 1256.4 vs nat 1117.5, ratio
= (1+1.25)/2 = exactement le maxDmg/minDmg config. Port : handler registry
`_great_frost_axe_inputs` (`base_override`, même mold que HellfireShells #173), id 1089 dans
`_MAKE_DMG_INPUT_OVERRIDES`. Validé harnais seed 54321 : s18 pred match, **et s6 u85
(ability:prediction) bascule à hit par ricochet** (per-target GreatFrostAxe corrigée → choix de
cible natif retrouvé).

**54321 s19 u77 (Tau, attaque normale 69 → t93, nat [1098,1644] vs off [630,942], 9 hits vs 6)** =
**effet `CyclicIonBlaster_AdditionalHits` (1148) non porté** (canal #179). Natif :
`CyclicIonBlaster_AdditionalHitsEffect.CreateAdditionalHits @180e1dd70` (classe
`Abilities.Triggered.Loki`) = `EffectAdditionalHits.Create{trigger = OwnerIsCaster (toutes
attaques), amount = ConditionalAmount(HasEffect(target, 0x462=1122 Markerlight) | HasTrait(target,
5=Mechanical), RandomAmount(Sum(minDmg,extraDmg), Sum(maxDmg,extraDmg)), RandomAmount(minDmg,
maxDmg)), count = nrOfHits = 3, profile = Particle p35}`. **varTrace décisif (leçon #57c-C
appliquée)** : 2 résolutions var 0xc (minDmg) état {50,180} → 599, JAMAIS 0xd/8 → le display
n'évalue que le nœud MIN et le pipeline étale : 599 ±20 % × %-mods attaquant (1.33
RangedSpecialist × 0.7 Pinned) × pierce 35 = [156,234]/coup ×3 — arithmétique EXACTE
(1098−630=468=3×156 ; 1644−942=702=3×234). Multiplier GLOBAL (mult 180 dans l'état varTrace — pas
le per-ability #68). Port : `CyclicIonBlasterAdditionalHitsEffect` (hits.py, forme « amount » comme
FoulInfusion) + ctx #179 enrichi (`tgt_traits`/`tgt_effect_names` pour la ConditionalAmount cible).
**Bit-exact** probe_57e_54321.py S19 : OFF = NAT = [1098,1644], healthDmg [1098,1291], 9 hits, kill.

Flags validator #57e : branche +extraDmg (cible Markerlight/Mechanical) non exercée ; face COMBAT
du CyclicIonBlaster (RandomAmount réel min..max au runner) non confrontée ; les descripteurs #179
ne sont foldés que sur le chemin ATTAQUE NORMALE offline (le natif les applique à toute PredictAttack
slot 0x27 — un Tau castant une speciale devrait aussi les folder) ; GreatFrostAxe : « Crit Damage
bonus of the Ice already applied » (i2) supposé baké dans les valeurs config, non contre-vérifié.

### #57d RÉSOLU : les 2 miss prédiction 1357 (s18 « ×2 exact » + s16 « swarm-composite »)

**1357 s18 u81 (custoBladeChampion → t168 Bloodletter, nat = off ×2 EXACT min&max)** =
**trait MartialKatah, face ATTAQUE** : `MartialKatah_DmgBonusEffect.CreateEffectDamageBonusForAttack
@180f58930` = `EffectBonus.ForPercentIncrease(OwnerIsCaster & HasTrait(target, Summon=2),
Direct(GetNumberConstant cfg 0xf = martialKatahExtraDmgPct = 100))` — **+100 % vs Summons**, AUCUN
gate mêlée/ranged/normal (i2 « all attacks against Summons »), appliqué en prédiction display.
Décomposition per-hit qui a identifié le mod : per-hit = 2529/3792 (base 2107 ±20 % ×1.5) ; OFF ×1.5,
NAT[real (3,5)] ×2.0 (pas bougé → pas de RapidAssault, ×2 Summon seul), NAT[cand (2,4)] ×3.0 = 1.5×2
(multiplicatif). Port : `MartialKatahDmgBonusEffect` (extra_damage.py, moule BeastSlayer target_traits),
factory `MartialKatah_DmgBonus` (l'ex no-op « hors gap » #105). **Bit-exact** probe_57d_1357.py S18 :
OFF = NAT = [15174, 22752], blockRawMin 11883 compris.

**1357 s16 u139 (RipperSwarm 5×[1197,1795] → t191 necroSmnSwarm, nat [2971,3569])** =
**member-cap Swarm de la prédiction, jamais câblé** (`_target_damage_limits` passait `member_count: 1`
TODO). Natif : `DamagePrediction.ApplyGroupUnitDamageLimit @18102bfe0` (appelé per-hit et per-borne par
`ApplyTraitDamageLimitsToDamage @18102c650`) — si la cible a un GroupUnit (memberCount>1) et que le
profil DU COUP n'a pas `DamageTrait.HitsMultipleMembers` (2, = Blast) : `dmg = min(dmg, hp_now −
GetGroupUnitMaxHealthWithRemainingMembers(maxHP, count, remaining−1))` avec `remaining =
GetGroupUnitRemainingMemberCount(maxHP, count, hp_now) @181005120` ; **PAS de cap si remaining == 1**
(le dernier membre prend le roll plein — d'où min&max qui diffèrent du roll seulement sur le dernier
coup). Répartition membre : `maxHP/count`, +1 pour les `maxHP%count` premiers (`GetGroupUnitMemberHealth
@1810050f0`, i2 : « Each incoming hit can deal Damage only to one member », « Does not apply to Blast »).
Vérification analytique u191 (maxHP 2220, 5 membres de 444, hp 2218) : caps 442,444,444,444 puis 5ᵉ coup
non cappé → min 1774+1197=2971 ✓, max 1774+1795=3569 ✓ (les 2 bornes capées contre le MÊME hp min-track,
règle #40 déjà portée). Câblage : `member_count = nrOfMembers` gameconfig (5 pour les 2 swarms) +
`damage_profile` threadé aux 4 call-sites de `_target_damage_limits` + flag per-GROUPE pour les coups
additionnels (le natif passe le profil du coup courant — un coup Blast additionnel skippe le cap).
**Bit-exact** probe_57d_1357.py S16 : OFF = NAT = [2971, 3569]. Le service `trait_damage_limits.py`
était déjà fidèle (aucune modif) — c'était un pur trou de NOURRISSAGE.

Flags validator #57d : gate attaquant-Swarm NON porté (« 1 fewer hit per member defeated » — u139
avait ses 5 membres, hits arme 5 == nrOfMembers, non exercé ; consommateur natif à localiser via
`BattleQuery.GetGroupUnitRemainingMemberCount @181061cb0`) ; heal-limit Swarm
(`DamagePrediction.GetGroupUnitHealLimit @1810325e0`) non porté ; member-cap du chemin DirectDamage
(`CalculateDirectDamage @18102f212` appelle aussi @18102bfe0) non vérifié offline ; MartialKatah_DmgBonus
sur le canal COMBAT (damage_model) non confronté (prédiction seule mesurée).

### #57c-C RÉSOLU : 2468 s14 u89 = aura ExplosiveMaladies (PAS un « fold LightImUp »)

Le miss prédiction 2468 s14 (u89 orksWarboss → t177, ranged, delta [3591, 5385]) est fermé
**bit-exact** (probe_57c_flathits.py C : OFF = NAT = [6722, 10082], appliedHits 2/2). Le vrai
mécanisme : **`ExplosiveMaladies_Extra{Ranged,Melee}AttackEffect`** (passif Pestillian/deathPutrifier,
effets-AURA hostés SUR le porteur u91) — `CreateAdditionalHits @180f43cc0` (ranged) / `@180f43a40`
(melee) = descripteur `{trigger = OwnerIsCaster & Is(Ranged|Melee)Attack, amount = ConfigVar(8=extraDmg,
GetAbilityState(effet)), count = GetNumberConstant(0x2f=nrOfHits=1), profile =
GetAffectedDamageProfile = Blast p15}` ; sélecteur `@180f43ef0` = `UnitsWithRangedWeapons(
AdjacentFriends(owner, 1))` (i2 : melee = amis **Chaos** seulement). Adjacence **ré-évaluée à la
tuile candidate** (modèle #49) : u89 à (2,3) adjacent de u91 (3,3) → +1 coup de extraDmg[50]×1.8
= **2992**, roll ±20 % **puis ×1.5 CrushingStrike** (les %-mods attaquant S'APPLIQUENT au coup
foldé) = [3591, 5385] ; à (0,3) non adjacent → rien.

**Méthodologie (2 fausses pistes évitées de justesse, à retenir)** :
1. « fold LightImUp » (hypothèse initiale) : coïncidence numérique — LightImUp.minDmg[50] =
   Waaagh.summonArmor[50] = 831 et 3×1496 ≈ 1×2992×1.5±20 % ont le même total. Le mold
   `Boltstorm_NormalAttackAbility.PredictAttack @1811bd950` (base + `GetAdditionalDamagePrediction
   @1811bd170` sur scénario vierge, gate `!IsMelee`) et son symétrique
   `ProperKilly_NormalAttackAbility.PredictAttack @1811fc690` (klaw = n coups de
   `PercentageOf(MaxHealth(cible), dmgPct)` `@1811fb760`, gate `!IsRanged`, Ghazghkull) sont RÉELS
   et restent portés (prediction.py, ProperKilly seul dispatché, non exercé) — mais u89 ne passe PAS par là.
2. « FoulInfusion display-true » : les 3 effets `FoulInfusion_ExtraHits` (u91/u162/u166, dmg[50]
   ×1.8 = 2792 ≠ 1496) ne contribuent PAS — leur trigger `IsMeleeAttack & OwnerIsCaster` est
   **ÉVALUÉ** en prédiction (attaque ranged → False). Aucun trigger « court-circuité TRUE » ici.
3. **L'outil qui a tranché** : `varTraceInstall` étendu (Interceptor temporaire sur
   `GetVariableForLevel @181576fb0`, backtrace RVA + **valeur retournée**) : UNE résolution
   varType 8 (extraDmg) state {50,180} → **2992** = ExplosiveMaladies.extraDmg[50]×1.8, pile dans
   `GetAdditionalHitsFromEffectsInternal @180e59150` (énumération GLOBALE des effets, descripteurs
   filtrés par leur trigger/sélecteur). Leçon : ne JAMAIS identifier une magnitude par
   valeur-matching seul — tracer la résolution native (config + valeur).

Ports (commit à venir) : `ExplosiveMaladiesExtra{Ranged,Melee}AttackEffect` (hits.py, nouveau canal
`create_aura_additional_hits_for_ally` + agrégateur `aura_additional_hits_from_allies`),
`FoulInfusionExtraHitsEffect` (canal #179 porteur, gate is_melee threadé — non exercé),
groupes « amount » (spread ±20 % pipeline) dans get_multi_hit_attack_prediction. Flags validator :
gate Chaos du sélecteur melee mirror i2 (non décompilé) ; ordre aura-groups vs owner-groups dans la
chaîne prev (invisible à armure 0) ; flag « always overkilled » non porté.

### État après pile #57c (3 effets dégât) + tranche 3a #56 (batchs `stages_57c_gen.json` / `stages_57c_ref.json`)

Gen 4 seeds : **prédiction 29/34 (85 %)** · **utilité 34/34 (100 %)** · **ability 37/50 (74 %)** ·
move 55/65 (85 %). Diff paire-à-paire vs `stages_56t2` : prédiction **+4 FIXED** (12345 s18
LordOfTheHost, 54321 s7 Doom, 2468 s15 CordClaw, **+ 54321 s6 u85 composite** — la part Doom le
fermait), **0 nouveau miss** ; ability **+3** (54321 s9/s11/s13, tranche 3a), **0 perte** ; move
**liste identique** (10 misses pré-existants). Référence 777/909/31337 : **4×100 % maintenu**.
Restent **5 mismatch-logic prédiction** : 54321 s18 u85 (composite), 54321 s19 u77 (×1.22),
2468 s14 u89 (~~fold LightImUp~~ → **RÉSOLU** aura ExplosiveMaladies, cf. section dédiée
ci-dessus), 1357 s16 u139 (swarm composite), 1357 s18 u81 (×2 exact).

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
