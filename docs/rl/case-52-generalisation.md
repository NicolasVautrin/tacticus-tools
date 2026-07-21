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

Restants (9 misses) :
| SendInTheNextWave | 1016 | 1357 s9 |
| Incursion | 1021 | 1357 s11 |
| FoulInfusion | 1038 | 2468 s12 |
| Poxwalkers | 1040 | 2468 s5 |
| HolyDuel | 1050 | 1357 s12 |
| EarlyWarningOverride | 1077 | 54321 s9 |
| GrapnelLauncher | 1090 | 54321 s13 |
| DarkTalonStrike | 1092 | 54321 s11 |
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

**−40 (u81 bloodIntercessor) — feuille attack `TriggeredAbilitiesUtility` = AggressiveOnslaught
(1248), → tâche #58** : L3 = Damage 21.1402 + Kill 100 + Overkill 40 + **TriggeredAbilities 40**
= 201.140154… exact. `AggressiveOnslaughtPlaybook.CalculateAttackUtilityInStepsInternal
@1811638d0` : gates [caster adjacent cible] ∧ [≥ nrOfSummons(2) hex plaçables], valeur =
(maxSummon−1) × délégué per-summon (=40 mesuré, corps generic-shared NON décompilé — ne PAS
coder 40 en dur). Finding structurel : `TRIGGERED_ATTACK_PLAYBOOKS` ne contient que Psyker
1013 alors que ~60 triggered ont un corps attack non-trivial → complétion agreement-driven.

**Erreur compensatoire DÉMASQUÉE par le port (nouveau gap prédiction, bucket #57)** :
1357 s15 u135 était un HIT par annulation de deux erreurs (notre raw gonflé 6580/9865 vs
natif 5388/8079 = ×1.221 SUR L'ATTAQUANT SUMMON ripper swarm, ET killSure gonflé). Le port
block corrige killSure → notre argmax choisit t191 (dont notre prédiction est aussi gonflée :
cf.eng=89.91 avec les prédictions natives injectées). Vrai résiduel = **la prédiction de
dégât d'un attaquant SUMMON est ~+22 % au-dessus du natif** (feed=False, fresh identique →
logic). Décomposition base-par-coup : raw_min = 0.8×base×3 → base_off = 6580/2.4 = 2742 vs
base_nat = 5388/2.4 = 2245 — piste : notre base = `GetStat(ATTACK, INITIAL)` + auras
re-évaluées (#153), qui EXCLUT toute modification NÉGATIVE courante non-aura (malus type
BattleFatigue/stack sur le summon) ; le natif serait à l'Attack CURRENT (2245 ?). À sonder :
comparer INITIAL vs attack_cur_by_id de u135 au s15 (canal attack_current, cf. #45-s18).

## Étage PRÉDICTION — champs divergents

rawHealthDmgMin/Max (11), healthDmgMin (5), killSure (2), healthDmgMax (2), kill (2),
healAmount (1).

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
