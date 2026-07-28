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

## #57g — RÉSOLU : tie-break d'énumération des cibles (12345 s15, MurderousSwing t83 vs t81)

**Miss** : s15 u89 worldExecutions, off = (1137, t81), natif = (1137, t83), NOTRE scoreur donnait
167.86 aux deux (étage `utility-logic`, « tie exact »).

**Discriminant (probe_57g_tie.py)** : le tie est RÉEL côté natif — `pairUtility` bit-identique
pour les deux paires à leur tuile argmax commune (1,6) : `172.8598932735622` les deux (u sans
Tile7 ; u_full décisionnel 167.8599 égal aussi, même tuile ⇒ même terme Tile7 −5). Donc pas un
terme manquant : un problème d'ORDRE au argmax.

**Mécanisme natif (décompilé)** :
- `ComparablePlaybook.EvaluateInternal @181408980` : à position FIXE, itère les cibles éligibles
  et ne remplace le best que sur `op_GreaterThan` STRICT → au tie, la PREMIÈRE cible énumérée gagne.
- L'ordre d'énumération = `BasePlaybook.GetEligibleTargetsEntities @18111ead0` ← `AttackQuery.
  GetValidTargetsWithCache @181056cd0` ← `TargetingQuery.GetValidTargets @1810be550` (OrderedSet.Add
  en itérant les possibles) ← `GetPossibleTargetsForOptions @1810bcea0` ← `GetUnitsInRange @1810be120`
  (slot 0x76) ← `BattleQuery.GetUnitsAtDistance @18106c9a0` (tuile→unité, ordre préservé) ←
  `GetTilesAtDistance @181069760` (filtre ring exact, ordre préservé) ← `TileQuery.
  IterateSurroundingTiles` (`d__6.MoveNext @1810ae1b0`).
- `d__6.MoveNext` = triple boucle cube ASCENDANTE (x puis y puis z, filtre x+y+z==0) ⇒ ordre
  d'émission = **lexicographique (cube.x, cube.y) CROISSANT** des tuiles (le centre borne le disque,
  il ne change pas l'ordre relatif). Convention vérifiée : `CubeCoordinate.ToAxialCoordinate
  @180e30ab0` (field3==0) = inverse exact de `hexgeo.to_cube` (field0=x=col, field2=z,
  row=z+(x+(x&1))//2) ⇒ champs natifs (0,1,2) ≡ (x,y,z) hexgeo.

**Vérification sur le cas** : ring-1 autour de (1,6) en ordre natif = [(0,6),(0,5),(1,7),(1,5),
(2,6),(2,5)] ; t83 necroWarden @(2,6) cube (2,−7) index 4, t81 templAncient @(2,5) cube (2,−6)
index 5 → t83 énuméré AVANT t81 → au tie strict le natif garde t83. ✓ cohérent avec la décision.

**Port** : `bq.iterate_surrounding_tiles_order_key(pos)` (engine/battle_query.py, clé lex cube
(x,y)) + tie-break dans `ComparableAbilityGenerator._best_attack` (action_generators.py) : à clé
`(u_full, is_normal)` égale ET même ability ET même tuile d'attaque, la cible au plus petit rang
cube gagne. Périmètre : tie INTRA-position/intra-ability uniquement — tie inter-positions (ordre du
sweep de move-tiles natif) et inter-abilities (boucle générateur) NON LUS, comportement premier-
énuméré conservé (non exercés).

**Flags validator** : (a) cible multi-tuiles = rang de sa première tuile émise (non exercé) ;
(b) range>1 : l'empilement des rings d=1..R (ordre inter-distances de GetUnitsInRange slot 0x76)
non lu — le cas s15 est mêlée R=1 ; (c) tie inter-positions/inter-abilities hors périmètre (cf.
ci-dessus).

## #57h — REQUALIFIÉS : 12345 s14 + 2468 s16 = divergence de TERME DE TUILE (pas d'utilité de paire)

**Méthode** (probe_57h_gates.py, extension #57g) : l'étage UTILITÉ (100 %) ne confronte que la
paire NATIVE — le score de NOTRE choix engine n'avait jamais été confronté au scoreur natif.
Confrontation des 2 paires × toutes leurs tuiles ranked, OFF pleine précision vs `pairUtility` natif.

**Verdict** : dans les DEUX cas, `pairUtility` natif == notre u à l'epsilon Fix64 près, pour les
DEUX paires à TOUTES les tuiles (S14 : 22.662/16.997 ; S16 : 20.99/26.24). L'utilité de paire est
EXACTE des deux côtés ; **toute la divergence est dans u_full − u = le terme Tile(7)** :

| cas | paire native (tuile, notre T) | choix engine (tuile, notre T) | contrainte native déduite |
|---|---|---|---|
| 12345 s14 u87 | 69→t77 @(3,5), T=+20 | 69→t85 @(4,3), T=+30 | T(4,3)−T(3,5) < 5.665 |
| 2468 s16 u79 | 69→t89 @(3,4), T=+30 | 69→t91 @(4,2), T=+50 | T(3,4)−T(4,2) > 5.25 |

**Décomposition par feuille** (probe_57h2_tileterm.py) : nos termes = 100 % **Elevation(8)**
(modèle RE'd case-37 : 10×elev, +10 max board, −5 min ; elev2→20, elev3→30, elev4(max)→50).
Aucune courbe d'élévation monotone ne satisfait S16 (il faudrait E(3) > E(4)+5.25) ⇒ un terme
**NÉGATIF natif ≥ ~25 sur (4,2)** (et ≥ ~4.3 sur (4,3)/(3,4) au S14) manque offline. Les tuiles
suspectes SONT dans les aiMovableTiles du tour (vérifié) — pas un gate d'atteignabilité. L'ancienne
étiquette « native-gate » de S16 (nu_nat < nu_eng du classifieur) était un artefact de la
comparaison sans terme de tuile.

**Suspect principal** : feuille **TriggeredAbilitiesNonOwner(4)** (non portée, =0 offline) —
zones de danger émises par les triggered abilities ENNEMIES (famille `*NonOwnerPlaybook.
CalculateMovementUtilityInSteps`, ex. `AdjacentToOwnerNonOwnerPlaybook.<…>d__2.MoveNext
@18134f250` : IsAdjacent(porteur, tuile) → poids config profil `TriggeredAbilitiesNonOwner`).
→ mission #57i (re-expert). Confirmation décisive possible plus tard par diff L3 par-feuille
aux tuiles suspectes (L3 = session-globale, à faire en session CALME uniquement).

## #57j — SONDÉ : 54321 s8 nc-pair HammerOfWrath (natif t91, offline t93) — PAS un tie

Décomposition offline (probe_57j_hammer.py) : les 3 paires ne sont castables que depuis (5,8)
(position courante de u81 bloodIntercessor). Nos utilités NC : t89=95.76 (events 80.76 + disp 15),
t91 darkaAzrael=185.54 (events 65.54 + Overwatch +100 + disp 20), t93 bloodDeathCompany=207.66
(events 187.66 + disp 20). On émet t93 strictement > t91 → PAS un problème d'ordre (même position,
et l'ordre evals mettait déjà t91 avant t93). Le natif préfère t91 ⇒ divergence dans la Σ
CalculateUtilityFromDamageEvent INTERNE (nos events t93 sur-scorent d'au moins ~22, ou t91
sous-score) — suspects : prédiction primaire/secondaire de make_hammer_wrath_events sur t93
(bonus kill ? PV ?), set des adjacents secondaires. Utilités NC natives NON exposées par RPC
(dégât Hammer hors prédiction affichée, #109) → **résolution = diff L3 par-feuille/par-action en
session CALME** (même passe que #57h s14/s16 si #57i ne conclut pas).

### #57f — gates natifs d'offre (BlackRage 1163 / MartialInspiration 1191) — verdict re-expert

**BlackRage 1163 (54321 s12 u93) — RÉSOLU : gate RNG/HP dans ShouldEvaluate.**
`BlackRagePlaybook.EvaluateNonComparable @1811211f0` n'a pas de gate ; le gate d'offre est
`BasePlaybook.ShouldEvaluate @18111fb70` = `GetUseProbability @181121740` : prob `0.4`
(`Fix64.FromIntFraction(4,10)`) si HP_apres < PV courants, sinon `1.0` (`Fix64.One`,
statics+0x20 via cctor @181563a60). HP_apres = 50%·MaxHealth (`GetHealthPercentageAfterUse
@1811ba570` = ConfigVar(0x26) ; `GetSetHealthBehaviour @1811ba690` = ChangeStat(Health,
PercentageOf(MaxHealth,0x26)) ; i2 "set to 50% Health"). ShouldEvaluate : prob>=1->True,
prob<=0->False, sinon RNG. => offert DÉTERMINISTE ssi PV<=50%MaxHealth. LIVE : 31337 s12 u91
hp=1/9537 -> natif 6/6 ; 54321 s12 u93 hp=6040(>50%) -> flicker 1/5 (RNG 0.4). Port :
`BlackRagePlaybook.should_evaluate` (black_rage.py) = `hp <= 0.5*hpmax` (branche 1.0 seule ;
0.4-RNG conservativement non-offerte, moteur déterministe). VALIDÉ : 54321 s12 flip HIT
(ability 13->14/15, move 17/17, 0 régression) ; 31337 s12 u91 BlackRage HIT préservé
(ability 13/13). BlackRage n'apparaît QUE dans ces 2 records sur tous les dumps -> risque nul.
Flags validator : branche 0.4 non-offerte (un roll natif chanceux HP>50% serait manqué —
non-déterministe par nature) ; ConfigVar 0x26 codé 0.5 (i2+décompilé, non lu de la config).

**MartialInspiration 1191 (2468 s18 u77) — NON RÉSOLU : biais cross-générateur, PAS per-joueur.**
Le « gate per-joueur 1180 » (#39) est RÉFUTÉ pour 1191 : u79 (31337 s16) = custoBladeChampion
team 2 (même camp que u77) émet 1191 6/6 déterministe (move(4,3)+1191->87, réf HIT). PAS
CanUseAbility (depuis (4,3) : NoBrokenTargetingRule, usable). PAS cooldown/buff
(totalTurnsWithAttacksMade=1 identique)/kill (t91=12047, t87=4471 : aucun kill). Générateur
`<GenerateActions>d__7 @18119a3f0` : TOUS les gates passent pour 1191 depuis (4,3)
(IsAbilityBlocked, get_CanCurrentlyBeUsed @180f8fdb0, tactic IsValidAbilityType [u77=Default,
`GetUnitTacticForUnit @181054550`], ShouldEvaluate, HasValidTargets @181057540). Le natif DÉVIE
de son propre pairUtility : pairUtility(1191) > pairUtility(69) dans les 2 états (2468 Δ=0.75 ;
31337 Δ=4.97) mais n'émet 1191 qu'en 31337. Le biais vit dans la sélection cross-générateur
`DefaultAiUnitTactic.CalculateNextActionForUnit @1810f54e0` (merge attaque-normale +
`CalculateAbilityActionForUnit @1810f47f0` -> ActiveAbilityActionGenerator) — NON localisé
(même classe que le 1180 de case-31, mais MARGIN-DEPENDENT, pas per-joueur). Signature : le
natif préfère l'attaque normale à un actif marginalement supérieur (Δutil petit), émet quand
Δutil grand. Pas de fix sans seuil inventé -> à re-scoper (mission dédiée / fable-solver).


## #57i - feuille TriggeredAbilitiesNonOwner(4) investiguee ; le vrai trou = branche ENNEMIS de TriggeredAbilities(2)

**Symptome** (probes #57h/#57h2, `scripts/python/probe_57h_gates.py`/`probe_57h2_tileterm.py`) : 2 miss
CIBLE d'ability ou le pairUtility natif == offline BIT-PRES aux deux paires -> TOUTE la divergence vit
dans le terme Tile(7) du caster. 12345 s14 u87 necroOverlord : natif `69->t77 bloodSanguinary` depuis
(3,5) ; offline `69->t85 bloodDante` depuis (4,3). 2468 s16 u79 necroSpyder : natif `69->t89 orksWarboss`
depuis (3,4) ; offline `69->t91 deathPutrifier` depuis (4,2). Notre Tile(7) = 100% Elevation
((3,5)=+20 elev2, (4,3)/(3,4)=+30 elev3 ; (4,2)=+50 elev4 max).

### NonOwner(4) ECARTE (RE complete, ce N'EST PAS la source)

Arbre natif lu : feuille `TriggeredAbilitiesNonOwnerUtility` (ctor @1810f30b0 ; face move
`<EvaluateMovementInSteps>d__0.MoveNext @1810f91c0` ; enumerateur `<IterateAbilities>d__3.MoveNext
@181103860` = pour CHAQUE unite != self, `PlaybookDatabase.LoadPlaybookNonOwner @1810df9a0`, yield
`(playbook, entity)` si `AppliesToFriendly(interface slot 4) || UnitExtensions.IsFriend`). Famille
`AdjacentToOwnerNonOwnerPlaybook<T>.<CalculateMovementUtilityInSteps>d__2.MoveNext @18134f250` : si tuile
candidate ADJACENTE au porteur -> `GetUtilityValue @18150ec60` = lookup config `Default.
TriggeredAbilitiesNonOwner[<cle>]`. Profil = **25 cles = abilities LEGENDAIRES precises** (FirstAmong
Traitors/ShieldOfFaith/HaywireMine(-30/-50)/NornCrown/KustomForceFieldReworked/...). Recon des kits
ennemis des 2 seeds : AUCUN ne porte une de ces abilities (S14 : SanguinaryPriest/LordOfTheHost/Deathwing/
AstartesBanner/RelentlessMarch/ContagionsOfNurgle ; S16 : idem). => la feuille (4) yield **0** pour ces
seeds. Non porte (reste `TILE_LEAVES[4]=None`) ; a porter en feuille propre le jour ou un case montre une
unite PORTANT une ability NonOwner.

### Vrai trou : feuille (2) TriggeredAbilities - base `AdjacentUnitPreference` amputee de la branche ENNEMIS

`Default.TriggeredAbilities` (feuille 2, deja portee) contient `MARTIALAPOTHEOSIS_AdjacentEnemy=15`
(u87 necroOverlord passif MartialApotheosis 1045) et `FABRICATORCLAWARRAY_AdjacentFriend=30` (u79
necroSpyder passif FabricatorClawArray 1006). Notre base `AdjacentUnitPreferenceTriggeredAbilityPlaybook`
modelisait `amis R1 (adjacent) + amis R2 (surrounding)`. Or le corps natif
`<CalculateMovementUtilityInStepsInternal>d__1.MoveNext @18134eb30` a **DEUX branches, toutes deux a
DISTANCE 1** de la tuile candidate :

| branche | query natif | poids (vtbl) | filtre (vtbl) | cap (vtbl) |
|---|---|---|---|---|
| B1 amis R1 | `IBattleQuery.GetAdjacentFriends(tile, playerId)` MINUS self (slot 0x81) | `GetAdjacentFriendUtility` 0x208 | `FilterAdjacentFriends` 0x248 | 0x228 |
| B2 ennemis R1 | `IBattleQuery.GetAdjacentEnemies(tile, playerId, false)` (slot 0x7d) | `GetAdjacentEnemyUtility` 0x218 | `FilterAdjacentEnemies` 0x258 | 0x238 |

**Preuve que B2 = ennemis R1 (pas surrounding R2)** : comptage d'args de l'appel interface. `GetAdjacent
Friends`=this+2 params (entity, playerId) ; `GetAdjacentEnemies`=this+3 (entity, playerId, bool) ;
`GetSurrounding*`=this+4. B1 passe this+2 args -> GetAdjacentFriends. B2 passe this+3 (`...,uVar2,0,...`)
-> GetAdjacentEnemies. Les poids concrets IGNORENT l'unite (lookup config plat @1811689d0/@181165af0).
L'ancien modele (amis R1+R2) rendait EXACT pour GuardianOrganism(1181)/RitesOfBattle(1014) (poids
surrounding ET enemy = 0, donc B2 muette) mais RATAIT MartialApotheosis (qui n'override QUE la branche
ennemis). case-36 (GuardianOrganism 30/90) ne distinguait pas car ses tuiles n'avaient pas d'ennemi
adjacent -> la branche B2 n'etait jamais exercee.

### Config + signes + geometrie (live, board MC1_67)

| seed/step | mover | ability (id) | branche | poids BC | tuile natif | #adj (live) | terme | tuile offline | #adj | terme |
|---|---|---|---|---|---|---|---|---|---|---|
| 12345 s14 | u87 necroOverlord | MartialApotheosis 1045 | B2 ennemis | +15 | (3,5) | 3 ennemis | +45 | (4,3) | 0 ennemis | 0 |
| 2468 s16 | u79 necroSpyder | FabricatorClawArray 1006 | B1 amis(Mechanical) | +30 | (3,4) | 1 ami mecanique (admecRuststalker) | +30 | (4,2) | 0 | 0 |

Le miss n'etait donc PAS un terme NEGATIF sur (4,3)/(4,2) (hypothese #57h) mais un terme POSITIF sur la
tuile native (effet relatif identique). Total apres fix : S14 (3,5)=20+45=**65** > (4,3)=30, (3,4)=60 ->
argmax (3,5). S16 (3,4)=30+30=**60** > (4,2)=50 -> argmax (3,4). FabricatorClaw filtre les amis par trait
Mechanical (=5) : `FilterAdjacentFriends @181165830` (HasTrait 5).

### Port

- `scripts/python/engine/playbook/adjacent_unit_preference.py` : base reecrite (branches B1 amis + B2
  ennemis R1, hooks `get_adjacent_enemy_utility` vtbl+0x218 et `filter_adjacent_{friend,enemy}`
  vtbl+0x248/0x258 defaut identite ; suppression de la branche surrounding fantome). Ajout des classes
  `MartialApotheosisPlaybook` (@181168a30/@1811689d0) et `FabricatorClawArrayPlaybook`
  (@181165b50/@181165af0/@181165830, filtre Mechanical), enregistrees 1045/1006 dans
  `TRIGGERED_MOVE_PLAYBOOKS`.
- `scripts/python/engine/utilities/tile.py` : `tile_leaf_ctx` fournit `friend_units`/`enemy_units`
  ({pos,traits} vivants self-exclu, traits gameconfig pour les filtres) via helper `_adjacent_units`.
  Commentaire feuille (4) mis a jour (RE NonOwner consignee).

### Validation (stages, board MC1_67, sans L3)

| seed | avant (57g/57e_gen) | apres (57i) |
|---|---|---|
| 12345 | ability 9/10, pos exact 13/15 ; miss s14 ability(69->77)+move, s5 move-formula | **ability 10/10, pos exact 14/15 (near 15/15)** ; s14 FIXE ; reste s5 move-formula (pre-existant, non force) |
| 2468 | ability 10/12, pos exact 14/17 ; miss s16 ability(69->89)+move, s4/s15 move, s18 native-gate | **ability 11/12, pos exact 15/17 (near 16/17)** ; s16 FIXE ; reste s4 generator-overfire, s15 pos-downstream, s18 native-gate (tous pre-existants) |

Etages PREDICTION+UTILITE 100% aux 2 seeds. Zero regression (s15 12345 reste hit, tous les hits
preserves). Dumps : `data/stages_57i_12345.json`, `data/stages_57i_2468.json`.

### Flags validator

- **B2 = ennemis R1 tranche par comptage d'args interface** (this+2 GetAdjacentFriends vs this+3
  GetAdjacentEnemies), PAS lu directement du slot interface -> a re-confronter si une autre unite montre
  la branche.
- **Caps (vtbl+0x228/0x238) non repliques** (corps gshared) : suppose non-liants (<=6 voisins hex ;
  S14 (3,5)=3 ennemis compte a plein -> requis pour le flip). Un cap < #adjacents casserait.
- **Filtre B2 defaut = identite** (MartialApotheosis sans FilterAdjacentEnemies) ; le friend-check
  redondant de FilterAdjacentFriends est absorbe (friend_units deja cote allie). enemy_units ne portent
  pas de filtre trait aujourd'hui (aucun case).
- **s18 2468 (MartialInspiration 1191) et s5 12345 (move-formula) restent** : hors scope #57i
  (native-gate documente ci-dessus non-resolu ; move-formula = autre tranche).

## #57k — passe L3 solo (post-#57g/f/i) : s8 Hammer et s5 move DÉCODÉS

Probe : `probe_57k_l3.py` (L3 session-globale, lancé SOLO ; traces `frida/data/ai-traces/<sid>-*.jsonl`).

**54321 s8 HammerOfWrath — le gap est UN EVENT DE TROP (~+120) sur t93.** Les 8 `DamageUtility#73`
natifs de la fenêtre se regroupent par cible et matchent NOS sommes pour t89 et t91 : t89 =
48.90+21.63+10.23 = 80.77 (off 80.76 ✓), t91 = 33.43+9.01+23.10 = 65.54 (off 65.54 ✓ ; total
décision 185.54 avec Overwatch+100 et disp+20 == off ✓). MAIS t93 bloodDeathCompany = **2 events**
natifs (44.57+23.10 = 67.68, total ~87.7 avec disp 20) contre **3 events offline Σ=187.66** →
notre t93 sur-score de ~120 (event primaire gonflé ou secondaire en trop dans
`make_hammer_wrath_events`). Prochain pas : imprimer NOS 3 events t93 un à un, diff vs
[44.57, 23.10] — identifier l'event fautif (kill-flag ? adjacent illégitime ?), fix ciblé.

**12345 s5 u89 move-formula — TIE NATIF exact + notre pathdist diverge.** Par-feuille natif :
(0,4) ET (1,4) = Elevation +30 + `MinDistanceToClosestEnemyUtility#76` **−700 les DEUX** →
Composed −670 égalité parfaite ; le natif départage par l'ordre du movable set (premier-gagne,
(0,4) avant (1,4)). NOUS : MinDist(1,4) = −600 (pathdist 6) vs natif −700 (≙ 7) → UN PAS de
notre chemin (1,4)→ennemi le plus proche est compté 6 offline mais 7 nativement (pas illégal :
porte d'élévation/blocage à identifier sur ce chemin précis). NB : l'ancienne note « le natif
confirme pathdist (1,4)=6 via pathDistToEnemies » visait le RPC, pas la feuille — la feuille
MinDist n'égale donc PAS pathDistToEnemies×(−100) sur cette tuile : chercher la vraie source de
distance de la feuille (#76) avant de toucher au pathfinder. L'hypothèse « terme ≥+100 manquant
à (0,4) » est MORTE (c'était un déficit de NOTRE (1,4), pas un bonus natif de (0,4)).

## #57m — RÉSOLU : 54321 s8 Hammer = event secondaire sur un CADAVRE (filtre vivant manquant)

Le 3ᵉ event t93 de `make_hammer_wrath_events` était **u95, une unité MORTE** (isDead=True, hp=0,
cadavre resté à (3,5) hex-adjacent de la cible (2,4)) : hp=0 ⇒ `kill=True/killSure=True` ⇒
composite Damage **+119.995** — exactement le sur-score ~+120 mesuré en L3 (#57k). Preuve interne
supplémentaire : DEUX cadavres (u95 team 1, u140 team 2) partagent la tuile (3,5) — impossible
pour des unités sur board.

**Mécanisme natif (décompilé)** : `HammerOfWrathAbility.GetAdjacentTargets @1811e6150` =
`Enemies(AdjacentUnits(TARGET, r=1))` avec `DSLFactory.AdjacentUnits @180de8320` =
`Units(AdjacentTiles(target)) − target` : les unités sont résolues par **OCCUPATION DE TUILE**
→ un mort n'est plus sur le board, le filtre vivant est STRUCTUREL (pas un check isDead explicite).
Notre `scene.pos_by_id` (issu de decisionView) garde les cadavres (piège connu, cf.
decisionview-keeps-dead) → le mirror fidèle est le filtre explicite `(scene.hp(u) or 0) > 0`
(idiome déjà en place aux autres scans : prediction.py l.102/227/276).

**Fix** : `prediction.py make_hammer_wrath_events` (boucle adj) + docstring. **Validation** :
probe_57j → t93 = 2 events Σ=67.6679 (natif 67.68 ✓, 44.57+23.10), t89/t91 inchangés au bit
près, pick = (81, 1153, t91) == natif. Étage 54321 complet re-passé (voir dump stages_57m).

**Suite (tâche #25)** : audit de la même classe de trou sur les AUTRES scans sans filtre vivant —
`aura_sources` (prediction.py l.529), `board["pos_by_id"]`/`faction_by_id` bruts consommés par
GetStuckIn (orks adjacents), `bespoke.py:207`, `fury_of_the_ancients.py:122`, `foul_infusion.py:63`.
Vérifier le sélecteur natif de CHAQUE site avant de patcher (certains folds type-level sont
miroir-safe).

### Audit #25 (suite #57m) — tous les scans « unités sans filtre vivant » traités

Décompiles à l'appui (`GetBonusHitChance @180f83460` = compte via `AdjacentUnits` ;
`UnitsOnTilesSelector.Select @180f02450` = sélecteur de TUILES @+0x18 + mode d'occupation
main/steppable @+0x20 → résolveur board : les unités d'un sélecteur d'occupation viennent des
tuiles, un mort n'y est plus) :

**Trous réels corrigés (4)** :
1. `make_hammer_wrath_events` (le miss d'origine, cf. ci-dessus).
2. `prediction.py` board/`aura_sources` de la normale (l.523-537) : `pos_by_id`/`faction_by_id`/
   porteurs d'aura désormais vivants-only (`_alive_ids`) — GetStuckIn ne compte plus un ork mort,
   un cadavre ne porte plus BigTarget/AstartesBanner.
3. `runner/damage_model.py build_hits_board` : skip `uc.alive=False` (cible conservée) — même
   classe côté COMBAT.
4. Sélecteurs DSL d'occupation : filtre `_is_alive` au cœur `_within` (dsl/base.py — couvre
   SurroundingUnits/AdjacentUnits/AdjacentEnemies + les 3 rings l.290/302/314), `Units.select`,
   et le scan ring « behind » (selectors.py l.180). Les sélecteurs d'ENSEMBLE gardent leur choix
   propre (`AllUnits`=alive #202, `UnitsDefeatedByMeleeAttack`=morts exprès, `CanAddUnit` filtrait
   déjà).

**Sites audités SAINS (déjà filtrés ou keyés sur des ids de query native)** : bespoke CultDemagogue
(l.203 filtre alive ; l.207 lookup d'ids de plan) + BloodChalice (l.68) ; fury `_second_target`
(consomme `ctx.enemies` filtré) ; foul_infusion (ids d'abilityTargets) ; black_rage `_charge_tiles` ;
it_itches ; stormcaller ; the_quickening ; SpiritLeech heal (action_generators l.260) ; heals l.337
(lookup) ; ctx.enemies (`_enemies` filtre alive à la source).

**Validation** : stages 54321 (100 % ability 15/15 + move 17/17 + pred 10/10 + util 10/10) et 2468
(identique à l'officiel : seuls les 3 misses pré-existants s18/s4/s15) re-passés APRÈS les fixes ;
pytest live `test_runner_attack` + `test_getstuckin_combat` (5 passed) ; splash/AoE DSL
`stikkbomb`/`fire_of_absolution`/`plasma_grenade`/`psyker_splash` (4 passed) ; cascade de mort
`finaljustice`/`summon_trigger`/`ambush` (voir run).

**Flag (cas de bord non exercé)** : pendant une cascade de mort, notre port pose `alive=False`
AVANT `after_death_triggers` → le mourant sort désormais des sélecteurs d'occupation évalués par
ses propres triggers. Natif : PreUnitDeath fire avant le retrait du board — si un arbre de trigger
lisait le MOURANT via un ring (aucun cas connu : les arbres passent par `Target()`/rôles), il
faudrait un flag « dying encore sur board » dans le ctx DSL.


## #57l -- s5 move (12345) FERME : filtre IsTargetable du ClosestEnemy (deep-strike non-ciblable)

> NB doc : section redigee depuis un worktree base 0195b5d (case doc ancien) ; a placer apres #57k
> dans le case doc courant (master). Les VAs/chiffres sont contre le build gqfc5mff6c.

**Symptome** (ref `stages_57post_12345.json`) : step 5 u89 worldExecutions, move natif=(0,4), engine=(1,4)
-> pos 14/15 (la SEULE miss). Composite move `UnitMovement(6) = Tile(7) + MinDist(16)` : natif (0,4) et
(1,4) EGAUX a -670 (Elevation +30 + MinDist -700, d=7) -> tie resolu PREMIER-GAGNE dans l'ordre movable
((0,4) idx 10 avant (1,4) idx 11). Nous : MinDist(1,4) = -600 (pathdist 6) -> (1,4)=-570 > (0,4)=-670 -> BOUGE en (1,4).

**RE (decompile = verite).** Chaine du leaf MinDist(16) :
- `<GenerateActions>d__6.MoveNext @181199d50` construit, par tuile candidate, un `UtilityMovementCase(unit,
  tuile, ClosestEnemy)` ; `ClosestEnemy = FindClosestEnemy(unit, positionCourante)` (mesure depuis la tuile COURANTE).
- `<EvaluateMovementInSteps>d__2.MoveNext @1810fe690` (stub @1810f0430) : `U = wMin * d`, wMin =
  `PerTileDistance` = -100 ; `d = GetMinDistanceToEnemy(unit, tuile, ClosestEnemy)`.
- `GetMinDistanceToEnemy @1810f04a0` : MIN sur le FOOTPRINT du ClosestEnemy (UN ennemi fige) de
  `IPathfinders.GetPath(type=1, unit, tuile, tuileEnnemie, null).Count` (Count INCLUT la tuile de depart -> offset +1).
- **`MovementActionGenerator.<FindClosestEnemy>d__8.MoveNext @181197f10`** : argmin depuis la position
  courante, MAIS SUR LES ENNEMIS CIBLABLES uniquement -- filtres per-ennemi : `!CurrentOwnerIsEnvironment`,
  **`IsTargetable`**, `!IsIrrelevantObject`, `!IsDead`, puis `GetOnlyTargets` (Contains, taunt/forced-target).
  `UnitExtensions.IsTargetable @180ed8ff0 = !HasFlag(unit, 0x11)` (flag 0x11 = ne-peut-etre-cible).

**Cause mecanique (mesuree live + flood-fill OFFLINE prouve fidele 15/15 vs RPC).** u89 @ (0,0), 5 ennemis
lointains (bas-droite). L'ennemi le plus proche PAR CHEMIN **et** par hex depuis (0,0) = **bloodDante (e85)
@ (6,6)** (path 10, hex 9). MAIS Dante porte le trait **TeleportStrike** (Deep-Strike) : "cannot be targeted
until it has taken an action" -> a s5 (Dante ennemi n'a pas encore agi) flag 0x11 pose -> `IsTargetable(e85)=false`
-> **exclu du ClosestEnemy**. Le natif mesure donc vers le closest CIBLABLE = darka/templ/necroWarden (e79/e81/e83,
path 11) -> d(0,4)=7, d(1,4)=7 -> tie -670/-670 -> (0,4). Notre RPC `pathDistToEnemies` n'appliquait AUCUN filtre
de targetabilite -> incluait Dante -> closest=e85 -> d(1,4)=6 -> (1,4). (Note morte : "terme +100 manquant a (0,4)"
etait un deficit de NOTRE (1,4), pas un bonus de (0,4).)

**Fix (miroir 1:1).**
- LIVE : `frida/hooks/features/ai-step/rpc-board.ts` `pathDistToEnemies` -- filtre la boucle ennemie par
  `IsTargetable` (`internals.ts` `isTargetableMi = IsTargetable(1)`, guarde : non-resolu => pas de filtre).
  => rebuild `hooks.js` + reinject requis (orchestrateur).
- OFFLINE : `engine/ai/state_bridge.py` `build_from_state` -- seed de `_pathdist_to_enemies` = ennemis CIBLABLES
  (`_is_untargetable` deja present, effet `TeleportStrike_TeleportingIn` 1035). `enemies`/`epos` restent complets
  (occupance) ; seul le seed MinDist est filtre.
- Docstrings : `engine/utilities/move.py` (mecanisme complet + VAs).

**Validation OFFLINE** (`_probe_s5_fixcheck.py`, flood-fill fidele + `context.build` poids reels) : BUGGY best=(1,4)
util=-570 (MISS) ; FIX (closest targetable=e79) best=(0,4) util=-670 (HIT). Le live stages exige le reinject du RPC.

**Limites / a attaquer** : (1) `GetOnlyTargets` (taunt/forced-target, `@180ed1b10`) non porte -- OK ici (liste vide)
mais un scenario Taunt divergerait. (2) fallback HEX du leaf (`enemy_positions=ctx.epos` NON filtre en live) : approx
quand pathdist=None -- a filtrer si une tuile inatteignable apparait. (3) validation live (patched-RPC) non faite dans
le worktree (reinject interdit a l'agent) -- a confirmer par l'orchestrateur : pos 15/15 seed 12345, 0 regression 54321/777.

**VALIDATION LIVE #57l (post rebuild+reinject session 66, 2026-07-22)** : stages avec le RPC patché —
12345 **100 %** (ability 10/10, move 15/15, préd 9/9, util 9/9 — s5 = (0,4) natif ✓, preuve que
`IsTargetable` s'est résolu au runtime) ; zéro régression 54321 (15/15, 17/17, 10/10, 10/10) et
777 (16/16, 17/17, 12/12, 12/12). Dumps `data/stages_57l_{12345,54321,777}.json`. Miss s5 FERMÉ.

## #64 — MartialInspiration 1191 (2468 s18) RÉSOLU : bonus d'action +1 de l'attaque normale (CalculateCustomUtility)

**Le « biais cross-générateur » de #57f n'existe pas : c'est un TERME natif chiffré.** Passe L3 solo
(probe_57k_l3.py cas S18, niveaux **L1+L2+L3** — L3 seul ne dumpe PAS `playbook_action`, activation des
3 niveaux ajoutée au probe) sur 2468 s18 u77 custoBladeChampion, fenêtre du dry-run de décision
(`data/l3_57k_s18.jsonl`, 92 events) :

- `playbook_action` **MartialInspirationPlaybook** : u = **61.72794423531741** = 21.72794423531741 (pair)
  + 40 (tile : Elevation +30, TriggeredAbilities +10) + **0**.
- `playbook_action` **Loki_NormalAttackPlaybook** : u = **61.98099426366389** = 20.98099426366389 (pair)
  + 40 (tile, Composed identique) + **1.000 EXACT**.

Décomposition complète, zéro scalaire fitté : chaque terme est soit dumpé natif (pair, tile), soit lu du
décompilé. Le +1 = **`CalculateCustomUtility`**, hook virtuel ajouté PAR-DESSUS pair+tile dans l'assemblage
du `BucketAction.Utility` (il n'apparaît JAMAIS dans le pairUtility du scorer RPC — d'où l'étage UTILITÉ
100 % match des deux paires pendant que la décision divergeait) :

- base `ComparablePlaybook<T>.CalculateCustomUtility @181407840` = `Fix64.FromInt(0)` ;
- `ALoki_NormalAttackPlaybook<T> @1813726e0` (générique partagé de tous les `*_NormalAttackPlaybook`
  par-unité), `Idun.NormalAttackPlaybook<T> @18149ee60`, `Loki_NormalBossAttackPlaybook @1811497c0`
  = `Fix64.FromInt(1)` constant.

**Loi** : l'attaque normale bat tout actif Comparable tant que Δ(pair+tile) < 1. Vérifie les 2 datapoints :
2468 s18 Δpair=0.75 → 69 joué ✓ ; 31337 s16 Δpair=4.97 → 1191 émis ✓. Notre ancien tie-break empirique
« normale gagne au tie exact » (clé `(u_full, is_normal)`) était l'ombre de ce seuil plus large — exactement
le scénario anticipé par #64 (« seuil natif PLUS LARGE à chiffrer depuis le décompilé, jamais fitté »).

**Structure du merge (décompilé, précise la lecture #57f)** : `CalculateNextActionForUnit d__5.MoveNext
@1810f54e0` = **FIRST-WINS sur la liste ordonnée des générateurs** (tactic+0x60 ; `FUN_18000d910` évalue le
générateur courant, `if (result != 0) break`) — PAS une comparaison d'utilité inter-générateurs. 69 et 1191
vivent dans le MÊME `ActiveAbilityActionGenerator` (5 instances partitionnent les abilities — L2 `candidates` ;
G5 = bucket comparables NormalAttack/Heal/Repair/...). La décision 69-vs-1191 est donc INTRA-générateur, dans
le max des BucketAction — le +1 était le seul terme manquant. (`CalculateAbilityActionForUnit d__7 @1810f47f0`
= variante mono-ability : OrderedSet {abilityType} + générateur dédié, même boucle.)

**Port (miroir 1:1)** :
- `engine/playbook/base.py` : `ComparablePlaybook.calculate_custom_utility` = 0.0 (@181407840) ;
- `engine/playbook/common.py` : `NormalAttackPlaybook.calculate_custom_utility` = 1.0 (@1813726e0) ;
- `engine/ai/action_generators.py` `_best_attack` : clé argmax inter-ability = `u_action = u_full +
  pb.calculate_custom_utility(...)` (remplace `(u_full, is_normal)`) ; le candidat pousse `full = u_action`
  dans le `Bucket.ChooseAction` final (attaque vs soins — le natif y compare des BucketAction.Utility).

**Overrides natifs NON portés (quirks per-ability — 27 au total, catalogue)** : contextuels lus :
`MortisRoundPlaybook @18114d190` (GetTargetUtilityDiffOnDisplace), `DrachnyenPlaybook @18112dc60`
(count cibles >= 2 → GetUtilityValue), `HeraldOfTheApocalypsePlaybook @1811441b0` (0 si une cible normale
damageable, sinon GetUtilityValue), `ProperKilly_NormalAttackPlaybook @1811532a0` (melee : Health-stat,
sinon stat+1) ; + TwistedScience_Heal, PlagueburstMortar, LightOfSanguinius, ArmoriumCherub, Chronometron,
DaemonicOrdnance, DevoutPush, DoomSiren, ForwardObservers, HealingBalms_Heal, InstrumentsOfVengeance,
MartialExemplar, MortarionsPlagueWind, PlasmaGrenade, Repair_GalvanicField, SavageEchoes, SorcerousFacade,
Stikkbomb, TheLionsWrath. À porter à la demande (dès qu'un cas d'agreement les exerce) — tâche dédiée #27.

## #26 -- filtre FindClosestEnemy COMPLET dans pathDistToEnemies (4 predicats + GetOnlyTargets + tgt_epos)

Suite de #57l (qui n'avait mirrore que `IsTargetable`). Le natif `MovementActionGenerator.
<FindClosestEnemy>d__8.MoveNext @181197f10` applique, DANS CET ORDRE, sur chaque ennemi
(`GetAllEnemyUnitsOfUnit`) : skip si `EntityExtensions.CurrentOwnerIsEnvironment @180eb4d00`
(= `GetCurrentPlayer(e,state).Owner.Type == 2`, joueur Environment/neutre) ; skip si
`!UnitExtensions.IsTargetable @180ed8ff0` ; skip si `UnitExtensions.IsIrrelevantObject @180ed86d0`
(= trait 27, ou trait 13 avec stat0 <= 0 -- decor) ; skip si `IsDead`. Puis, si
`UnitExtensions.GetOnlyTargets @180ed1b10` (unite qui BOUGE) renvoie une liste NON vide
(`List<int>` d'ids au champ +0x50 du composant taunt ; liste vide si pas de composant ou si
`OwnerComponent.IsOverridden`), le candidat doit etre CONTENU (`List.Contains`) -- taunt/forced-target.

**Port (RPC `pathDistToEnemies`, rpc-board.ts)** : les 4 predicats sont invoques NATIFS (aucune
semantique portee), guardes null (methode non resolue => pas de filtre). Restriction GetOnlyTargets
par ids ; si elle VIDE le set (cible forcee morte/non-ciblable -- comportement natif aval non RE'd),
degradation sure = set non restreint + flag `onlyTargetsUnmatched`. La reponse porte aussi
`enemies:[{id,col,row}]` (cibles retenues) -> `ctx.tgt_epos` (context.py live ; state_bridge offline
reutilise son tgt_epos `_is_untargetable`), consomme par le generateur de move et le harness stages
comme seed du fallback HEX de MinDist(16) quand pathDist=-1 (le SET est fidele, hex reste une approx).

**Validation (2026-07-22, sessions 69-70)** :
- stages 12345 : 100% partout (10/10 ability, 15/15 move, 9/9 pred, 9/9 util) -- seed deep-strike,
  chemin modifie exerce de bout en bout ; dump `data/stages_26_12345.json`.
- stages 2468 : 12/12 ability, 15/17 move = exactement les 2 misses structurels connus (s4
  generator-overfire, s15 downstream) -- zero regression ; dump `data/stages_26_2468.json`.
- live taunt (runner TG+Sanguinary vs Bullgryn, MC1_67) : pre-taunt `enemies=[79,81]`,
  `onlyTargetsCount=0` ; post-`CrushingClaws(1105)` (effet `Taunted_OnlySpecificTargets`), au tour
  IA : `onlyTargetsCount=1`, `enemies=[79]` SEUL (u81 a egale distance exclu) ; post-expiration du
  taunt (1 round) : retombe a 0 -- le RPC lit la verite native aux trois moments.
- non testables en runner (pas de porteur spawnable) : Environment/IsIrrelevantObject -- mais ce
  sont des INVOCATIONS natives (pas des formules portees), le risque se limite au cablage, couvert
  par les tests ci-dessus (meme pattern de garde).

## #17-s5 -- VERDICT FINAL du residu `MinDist#76` : FERME cote LIVE, DEPLACE cote OFFLINE

Le residu ouvert par #57k (« 12345 s5 u89 : natif -700 sur (0,4) ET (1,4), nous -600 sur (1,4) »)
a ete **re-mesure au TERME**, pas seulement a l'issue du pas. Probe :
`scripts/python/probe_17_s5_mindist.py` (`--focus-step`). Garde :
`tests/engine/test_min_distance_move_leaf_live.py`.

### 1. Face LIVE (`engine.ai.context.build`) -- ECART FERME, 14/14 tuiles bit-exactes

Seed 12345 / MC1_67, pas 5 (u89), `wMin = MinDistanceToClosestEnemy.PerTileDistance = -100` :

| tuile | index movable | `pathDist` NATIF (RPC) | port LIVE | terme |
|---|---|---|---|---|
| (0,4) | 10 | 7 | 7 | **-700** |
| (1,4) | 11 | 7 | 7 | **-700** |

et 12 autres tuiles, **toutes egales** (11/11, 10/10, 9/9, 8/8...). `closestResolved=true` : la
selection d'ennemi a bien eu lieu. Les 3 ennemis retenus par les filtres natifs sont
`(77,6,8) (81,5,8) (83,4,8)` contre **5** ennemis au total -- les deux occupants de (6,6)/(6,7)
sont exclus : **c'est le fix #57l (`IsTargetable`) en action**, mesure et non suppose.

**Le « tie » de la fiche est un VRAI tie, et son departage n'a rien d'aleatoire** : les deux
tuiles valent -670 au composite (`Elevation +30` + `MinDist -700`), et le natif prend **(0,4),
index 10**, avant **(1,4), index 11**, dans l'ordre du movable set -> **premier-gagne**. La garde
`test_move_tie_is_broken_by_movable_set_order` le verifie LIVE et **echoue si aucun tie n'est
rencontre** (pas de vert vide).

### 2. Face OFFLINE (`state_bridge.build_from_state`) -- l'ecart -700/-600 SUBSISTE

Meme etat de decision, meme pas : le port OFFLINE rend **-600 sur (0,4) ET (1,4)**, et diverge sur
**14/14 tuiles**, toujours d'exactement **un pas** (-100 de terme).

Decomposition par etage (BFS mono-source par ennemi ciblable ; arete = walkable + porte
d'elevation) :

| tuile | `pathDist` NATIF | BFS(e81)+1 | BFS(e83)+1 | offline `state_bridge` |
|---|---|---|---|---|
| (0,4) | 7 | 7 | 7 | 6 |
| (1,4) | 7 | 7 | 7 | 6 |
| (1,0) | 11 | 11 | 11 | 10 |

`BFS+1 == d_natif` sur **les 14 tuiles**, pour e81 comme pour e83. **Cause unique** : le natif lit
`route+0x18` (= `List._size`) du `IPathfinders.GetPath(type=1, unit, tuile, tuileEnnemie, null)`
appele par `IdunBattle.AI.Utilities.MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy` --
un nombre de **NOEUDS**, extremites incluses, donc `aretes + 1`. `state_bridge
._pathdist_to_enemies` compte des **ARETES**. L'ecart est cet offset, rien d'autre : la seconde
divergence structurelle (min sur TOUS les ennemis vs ClosestEnemy FIGE) n'est **pas discriminante
ici** (e81 et e83 rendent la meme distance sur les 14 tuiles) -- elle reste ouverte, non confrontee.

⚠ **Piege de mesure** : `load_state(dv, obs, snap)` **sans `board=`** laisse `state.board is None`,
`_pathdist_to_enemies` rend `{}` et la feuille retombe sur le **fallback HEX** -- on mesure alors
autre chose que la face offline (l'ecart paraissait de 2 sur (4,0)/(4,1), et l'inventaire des
causes s'en trouvait fausse). Passer `board=Board(boardGraph["tiles"], adjacency="native_sym")`.

### 3. Ce que l'offset change -- et ce qu'il ne change PAS

`MovementActionGenerator.generate` est un **argmax pur sur les tuiles** : un offset UNIFORME de
-100 ne deplace aucun argmax. Sur ce datapoint l'ecart offline est donc **sans effet sur la
decision** -- c'est un ecart de VALEUR du terme, exactement le genre de trou qu'aucune statistique
d'agrement ne peut voir. Il devient liant des que l'uniformite tombe : une tuile sans `pathDist`
retombe sur le fallback hex (autre echelle) -- et le natif, lui, ne fait PAS de fallback hex (§4).

### 4. RE complementaire lue a cette occasion (feuille + selecteur d'ennemi)

`MinDistanceToClosestEnemyUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`, in extenso :

```
u = Fix64.FromInt(0)
if case.Unit == null                                -> yield 0
if UnitExtensions.IsNonAttacking(case.Unit)         -> yield 0
if case.ClosestEnemy == null
   or !UnitCanBeDamagedUtility.UnitCanBeDamaged(case.Unit, case.ClosestEnemy)   -> yield 0
d = GetMinDistanceToEnemy(this, case.Unit, case.Tile.MainTile, case.ClosestEnemy)  # Nullable<int>
u = d.HasValue ? Fix64.FromInt(d.Value) * GetUtilityValue(this, PerTileDistance)
               : <constante statique, statics+0x20 d'une classe non identifiee>
```

Deux ecarts de port DISTINCTS de l'offset, non fermes :
- **quand `d` n'a pas de valeur**, le natif rend une **constante statique**, pas une distance HEX ;
  notre fallback hex est une invention de port (utile, mais ce n'est pas le natif) ;
- `GetMinDistanceToEnemy` force **`PathfinderType = 1`** en litteral, y compris pour une unite
  VOLANTE, alors que `_pathdist_to_enemies` bascule sur `fly_is_valid_path_node` si le mover vole.

`MovementActionGenerator.u003CFindClosestEnemyu003Ed__8$$MoveNext`, structure confirmee :

```
best = null ; bestDist = int.MinValue
onlyTargets = UnitExtensions.GetOnlyTargets(unit)                  # une fois, a l'init
foreach e in StateExtensions.GetAllEnemyUnitsOfUnit(state, unit):
    if CurrentOwnerIsEnvironment(e) || !IsTargetable(e) || IsIrrelevantObject(e) || IsDead(e): continue
    if onlyTargets.Count >= 1 && !onlyTargets.Contains(e.id): continue
    d = GetDistanceToEnemy(this, unit, unitPosition, e)             # Nullable<int>
    if d.HasValue && d.Value > 0 && (best == null || d.Value < bestDist):   # STRICT -> premier-gagne
        best = e ; bestDist = d.Value
return best
```

Le filtre **`d > 0`** et le **`<` STRICT** (donc premier-gagne dans l'ordre de
`GetAllEnemyUnitsOfUnit`) n'etaient pas consignes. `GetDistanceToEnemy` a **deux branches** -- une
distance de service (`<IBattleQuery> +0xb` sur les `UnitPosition`) et une `GetPath(...).Count` --
choisies par un appel dont la source n'a pas ete identifiee : **non tranche**, et non discriminant
sur ce datapoint (e81 et e83 donnent le meme resultat). Le RPC `pathDistToEnemies` choisit le
ClosestEnemy par la distance de CHEMIN ; c'est une hypothese, pas une lecture.
