# Agreement décomposé par étage — harnais Étape 1 (réconciliation live/offline)

> **Outil** : `scripts/python/engine_agreement_stages.py` (sonde branchée sur
> `engine_validate.run_agreement(probe=...)`). **Créé 2026-07-19** (session Étape 1).
> Dumps de référence : `data/stages_agreement.json` (777), `data/stages_batch_default.json`
> (909+31337), `data/stages_admech.json` (AdMech 3v3) — gitignorés, régénérables.

## 1. Pourquoi

Le % d'agreement d'`engine_validate` est OPAQUE : un miss peut venir de la **prédiction**
(dégât estimé divergent), de l'**utilité** (formule/termes), de l'**énumération** (paire
native absente de notre candidat-set = feed), du **gate** (playbook offline refuse), du
**move-scoring**, ou d'une **cascade** (position en aval d'un mauvais choix d'ability).
Ce harnais classe chaque hit/miss par étage et sépare **feed** (couture RPC/staleness)
de **logic** (formule du port).

## 2. Mécanique (v1)

- **Étage PRÉDICTION** : confrontation par paire (ability, cible) **à LA MÊME TUILE**
  (la tuile d'attaque du chunk natif : move-to si composé, sinon courante) :
  natif = RPC `aiPlaybookPredict` **étendu col/row** (UnitPosition à la tuile candidate via
  `GetUnitPositionAtTile @180eb6dc0` — ce que le sweep de décision natif évalue) ;
  offline = `playbook.make_damage_predictions(ctx, tile, ...)`. Tourne AUSSI sur les hits
  → métrique de fidélité prédiction globale.
  - Mismatch → re-test avec un prédicteur **rebuildé frais** au pas :
    fresh == natif → `feed` (staleness du prédicteur cold) ; sinon → `logic` (formule).
- **CONTREFACTUEL** : utilité offline recalculée avec les **prédictions natives injectées**
  (`damage_composite` sur les events natifs, négation friendly mirror). Si la paire native
  repasse devant le choix moteur → miss classé `prediction` ; sinon `utility-logic`.
- **Étage MOVE** (move pur des deux côtés) : `move-enumeration` (tuile native hors set légal),
  `move-tie-break` (u égales), `move-formula` (offline classe autrement), avec breakdown
  Tile7/MinDist/pathdist par tuile.
- **Décodeur natif enrichi** (playbook-predict.ts) : `shieldDmgMin/Max`@struct+0x80/0x84,
  `limitedByMinHp`@+0xB0, `forceOverkill`@+0xB2 (le contrefactuel consomme les 4).

### ⚠ Piège de mesure résolu (à ne PAS réintroduire)

Confronter à la **tuile COURANTE** donne des faux mismatches massifs `nat=0` : pour un chunk
composé move+attack, le natif rend 0 (cible hors d'atteinte depuis la tuile pré-move, légalité
respectée) là où l'offline calcule le dégât hypothétique. Mesuré seed 777 : fidélité 27 %
(faux) → **72 %** une fois la confrontation faite à la tuile d'attaque du chunk (`col/row`
d'`aiPlaybookPredict`). Toute confrontation prédiction doit être **à-position-égale**.

## 3. Résultats de référence (gqfc5mff6c, 2026-07-19, board MC1_67, rosters défaut)

| run | agreement pos (exact/≤1hex) | ability | fidélité prédiction | misses par étage |
|---|---|---|---|---|
| seed 777 (20 pas) | 16/17, 17/17 | 15/16 | **8/11 (72 %)** — 3 logic | 1 utility-logic, 1 move-tie-break |
| seed 909 (20 pas) | 10/16, 12/16 | 4/6 | (agrégé ci-dessous) | 1 utility-logic, 1 non-attack-oracle, **3 move-formula**, 3 pos-downstream |
| seed 31337 (20 pas) | 12/18, 13/18 | 6/13 → **7/13 (#33)** | agrégé 909+31337 : **8/14 (57 %)**, 1 feed→**0 (#33)**, 5 logic | **2 prediction**, 2 utility-logic, 3 non-attack-oracle, 1 generator-overfire, 5 pos-downstream |
| AdMech 3v3 (Marshall+Manipulus+Ruststalker vs 2 Warden, fini pas 9) | 6/8 | 4/5 | 1/3 | 1 utility-logic (1118), 1 generator-overfire (1118) |

Lecture : **la position est très majoritairement une CASCADE du choix d'ability**
(pos-downstream 8/12 misses de move sur 909+31337) — corriger l'étage ability corrige
mécaniquement l'essentiel du positioning.

## 4. Leads chiffrés (chaque ligne = un levier actionnable)

1. **✅ RÉSOLU (#29, 2026-07-19) — Sous-estimation ×2 + killSure raté** — 31337 s18, u89 ab=69
   tgt=81 : off 1926-2892, nat 5274 (=hp, killSure). CAUSE = **LordOfTempests** (passif Njal
   spaceStormcaller) : +`extraDmg[ablvl]×mult` (=400) PAR HEX GLACÉ du ring-1 de la POSITION
   D'ATTAQUE, additif per-hit (`CreateEffectDamageBonusForAttack @180f569a0` = ForAddition(
   OwnerIsCaster, Multiply(ConfigVar 8=extraDmg, Count(SurroundingTiles(0,1) with Ice))) ; centre
   EXCLU). Porté `LordOfTempestsExtraDamageEffect` (extra_damage.py) + plumbing `att_ctx`
   positionnel (Scene.tile_effects_by_pos = tileMeta FRAIS par pas — la glace s'accumule).
   VALIDÉ BIT-EXACT aux 2 tuiles ((3,3) 1 hex : 3126-4092 ; (2,4) 3 hexes : 5526-6492) ;
   s18 → HIT. Face RUNNER (pose de glace AddIce) = tâche dédiée.
2. **✅ RÉSOLU (#29, 2026-07-19) — Sur-estimation ×5.9** — 777 s15, u83 ab=69 tgt=87 : off
   1286-2570, nat 219-437 (×0.17). CAUSE = **DEUX réductions manquantes composées** (×0.8
   MartialKatah déjà porté × **0.5 Stunned** × **0.34 VexillaMagnifica** = 0.136 pré-MK,
   bit-exact) : (a) `Stunned_DamageModifierEffect @180f6f770` = ForPercentDecrease(
   **OwnerIsActor**, EffectConfig(2)=BC `Effect.StunnedDmgReductionPct`=50) — le dégât SORTANT
   du porteur stunné, hébergé sur le slot défense mais gaté acteur → boucle ATTAQUANT du port
   (`StunnedDamageModifierEffect`, status.py) ; (b) `VexillaMagnifica_DmgReductionEffect
   @180f76510` = ForPercentDecrease(OwnerIsTarget SEUL, ConfigVar 0x46=dmgReductionPct=66,
   non rarity-scalé) — TOUT dégât reçu par le porteur (damage_reduction.py). + accesseur
   `bc_effect_config` (magnitude.py, table BC Effect). VALIDÉ BIT-EXACT (219-437) ; le miss
   d'ACTION s15 reste (utility-logic : notre REPAIR 28→83 u=50.1 bat l'attaque → **modèle
   repair suspect**, le natif a préféré l'attaque faible au repair — cf. tâche #34).
   POST-FIX (777+31337, 20 pas) : ability 22/29 (75 %), prédiction 15/21 (71 %), garde
   test_effect_stun_live PASS. NB : `CreateEffectDamageBonusForAttack` = famille de **30+
   overrides** natifs (ExtraDamage/Pct/ReduceDmg…) — le harnais les fera émerger un par un.
3. **✅ RÉSOLU (#33, 2026-07-19) — Staleness prédicteur** — 31337 s16, u79 ab=1191 tgt=87 :
   off 598-898, nat 994-1976, **fresh == natif (`feed=True`)** ; cf_nat=56.2 > eng=51.2 → le
   miss flippe. CAUSE ISOLÉE (mesure cold-vs-fresh table par table) = **`actorstats_by_id`
   (`TotalAttacksMade`) périmé** : le cold de `build_predictor` capte le compteur au pas 0 (=0) ;
   l'attaquant u79 avait fait **2 attaques** → sa prédiction MartialInspiration (+33 %/attaque)
   sous-estimait ×1.66. FIX = re-capturer `actorStats` PAR-PAS dans `scene.refresh_shields` (le
   seul canal dynamique manquant : `ctx` INITIAL est stable, les drifts d'`ATTACK` CURRENT/MOD
   observés — aura Calgar +1298 sur la CIBLE s07/s08 — sont INERTES car la prédiction lit INITIAL
   + recalcule l'aura par adjacence live). VALIDÉ : s16 `cold==fresh==natif`, `feed=0` global.
   POST-FIX (777+31337, 20 pas) : prédiction 16/21 (76 %), ability 23/29 (79 %), 0 régression
   (garde `test_playbook_live` 3/3). NB : le seul autre canal cold-dynamique (aura CURRENT) reste
   inerte pour la prédiction — l'Étape 2 « resync per-step » est donc CLOSE pour le feed prouvé.
4. **Bornes ±1-5 qui flippent le kill-flag — ✅ RÉSOLU 2026-07-19 (#30a)** : cause racine =
   float64 vs Fix64 (Q31.32), fix = émulation Fix64 exacte (`engine/services/fix64.py`) +
   matérialisation Round(mode 1) des bornes — 777 s06 et 31337 s05 corrigés, prédiction
   16/21 → 18/21 (85 %), 0 régression (11 tests combat verts). Détail complet :
   `docs/rl/case-30-raw-bounds.md` §#30a. **Résidu s08 ✅ RÉSOLU 2026-07-20 (#40)** : ni porte
   overkill ni mod manquant — le port threadait la déplétion santé `prev` PER-BORNE là où le natif
   déplète les 2 bornes par UN SEUL scalaire (`BlockScenario.healthDmg@+0x08` = raw MIN cumulé,
   `get_DefaultBlockScenario @18102bcd0` + rem unique @181034087). Fix `BlockScenario.health`
   (damage_prediction.py) → s08 bit-exact (1498,1949), prédiction 18/21 → **19/21 (90 %)**,
   0 régression (7/7 tests ciblés). Détail : `case-30-raw-bounds.md` §« ✅ #40 RÉSOLU ».
5. **killSure fantôme (raw sur-évalué) — ✅ RÉSOLU 2026-07-20 (#41)** : PAS un mod défenseur —
   le ×0.611 = 1408/2306 = le PORT sur-appliquait l'aura RitesOfBattle Basic +898 de Calgar
   (u87, adjacent à la tuile candidate (2,3)) sur l'attaque MÊLÉE de u93. Loi native mesurée
   (2 canaux concordants) : aura-stat re-évaluée à la tuile CANDIDATE pour le RANGED (#153, gain
   inclus), mais PAS de gain non-matérialisé pour la MÊLÉE ; + tuile candidate BlockEnteringUnits
   → aura perdue même matérialisée. Fix : gate matérialisation (mêlée) + guard tuile bloquée dans
   `make_normal_attack_predictions`/`aura_attack_bonus_from_allies` → s13 bit-exact (2704,4056),
   prédiction 19/21 → **20/21 (95 %)**, 0 régression. Détail : `case-49-min-armored-regime.md`
   §MAJ #41. Résidu indépendant découvert au passage : accurate MAX non capé HP (u91, pré-existant
   prouvé par stash-run) → tâche #43.
5bis. **Split bouclier ab1150 (777 s11, shieldDmgMin 3351 vs 2873) — ✅ RÉSOLU 2026-07-20 (#42)** :
   le rem bouclier de `PredictAttackRaw` est un scalaire UNIQUE = bouclier − cumul MAX absorbé,
   consommé par les 2 bornes (mirror du #40 côté santé, où le rem HP unique = cumul MIN). L'ancienne
   déplétion par-piste ne divergeait que quand la piste MAX épuise le bouclier en cours de rafale.
   Raffinement #170 au passage : plancher 1-dégât gated sur cible SANS bouclier (`target_shield<=0`),
   plus sur `rem>0`. Fix `predict_attack_raw` (2 lignes) → s11 bit-exact 2 events, prédiction
   20/21 → **21/21 (100 %) — étage prédiction CLOS**, 0 régression (`test_predict_live` 2/2).
   Détail : `case-30-raw-bounds.md` §MAJ #42.
6. **NC overfire (gates trop lâches)** — famille : AdMech 1118 self-cast émis là où le natif
   bouge/attaque (2 occurrences AdMech + 31337 s17 : nat 69→87 u_off=192.7 pourtant le moteur
   sort 1118→77 par ORDRE de tier NC) ; 909 s10 : 1180 HeroicFusillade émise, natif attaque
   (pred quasi égales 1362 vs 1365, cf_nat=90.1). Le playbook NC natif GATE là où le nôtre émet.
7. **Move pur : le natif ne maximise PAS Tile7+MinDist** — 909, 3/3 move-formula au MÊME
   pathdist (MinDist IDENTIQUE des deux côtés) : s04 nat(3,2) tile=15 vs eng(0,3) tile=50 ;
   s05 nat(5,5) 20 vs eng(6,4) 40 ; s19 nat(4,3) 30 vs eng(4,2) 50 — le natif choisit
   SYSTÉMATIQUEMENT la tuile de Tile(7) INFÉRIEUR à MinDist égal.
   **❌ Hypothèse « mauvaise feuille distance (TileDistance 33) » RÉFUTÉE par décompilé (2026-07-19)** :
   `MovementActionGenerator.<GenerateActions>d__6.MoveNext @181199d50` construit
   `UtilityDefinition((IsTemporary(mainTile)^1)+5)` = **6 = UnitMovement(6) = [Tile(7),
   MinDistanceToClosestEnemy(16)]** pour une tuile normale (5=UnitMovementFromTemporary si temp),
   passé au décideur `FUN_1800051a0`. La feuille distance du move-action est BIEN MinDist(16) —
   notre port est correct. `MovementSuggestion(32)`/`TileDistance(33)` est un AUTRE consommateur
   (`GetUtility(32)` d'`IdunRunner.Initialize`), PAS le décideur de move-action → ne pas swapper.
   **✅ RÉSOLU (2026-07-19) via capture L3 `ai-trace` (utility_score par tuile) — c'est le MinDist,
   pas l'Elevation.** Scores NATIFS par tuile (seed 909) : s5 (5,5) Elev=20/MinDist=**−300** total −280
   (natif) vs (6,4) Elev=30/MinDist=**−400** total −370 ; s19 (4,3) Elev=30/**−400** −370 (natif) vs
   (4,2) Elev=50/**−500** −450. Le natif MAXIMISE bien Elev+MinDist — mais son **MinDist DIFFÈRE par
   tuile** (distances 3/4/5) là où **notre `pathdist_by_pos` les dit toutes = 3** → tiebreak écrasé,
   on retombe sur l'Elevation. CAUSE RACINE (décompilé `GetMinDistanceToEnemy @1810f04a0`) : le natif
   `IterateTiles(param_4)` sur **UN SEUL ennemi** = le `ClosestEnemy` du case (précalculé par
   `MovementActionGenerator.FindClosestEnemy` depuis la position COURANTE de l'unité), min sur les
   tuiles de CET ennemi ; gates `IsNonAttacking(me)`→0 et `UnitCanBeDamaged(me, closestEnemy)`. Notre
   RPC `pathDistToEnemies` (rpc-board.ts:524-531) fait **min sur TOUS les ennemis vivants** → sous-
   estime quand un autre ennemi est plus proche de la tuile candidate. FIX = aligner le RPC sur le
   natif (distance au ClosestEnemy unique, pas min-sur-tous) → rebuild + reinject. Détail 2ndaire :
   Elevation native n'applique PAS la pénalité `LowestElevation −5` que nous mettons (native (3,2)=20=
   10×2, nous 15) — min-référence native sur un set plus large que nos move-tiles. NB : le tool L3
   (`ai-trace/utilities.ts installL3`, hooke les 41 `*Utility.<EvaluateMovementInSteps>d__N.MoveNext`,
   capture le Fix64 yieldé + `UtilityMovementCase` tuile) était DÉJÀ déployé, juste `L3=off` par défaut
   → activé au runtime via RPC `aiTraceEnable("L3")`, events NDJSON dans `frida/data/ai-traces/`, ZÉRO reinject.
   **FIX PARTIEL (2026-07-19)** : le RPC `pathDistToEnemies` corrigé (ClosestEnemy unique) a **flippé s5**
   (move-formula 3→2). MAIS la capture L3 des utilités COMPLÈTES révèle un 3ᵉ terme : le composite move
   `ComposedUtility` = Elevation + TileEffects + **`TriggeredAbilitiesUtility(2)`** + MinDist. On DROP
   `TriggeredAbilities` à 0 (tile.py:486) alors qu'elle score PAR TUILE et DÉCIDE : s4 (3,2)=Elev20+
   TileEffects9+**TrigAb30**+MinDist−700=−641 bat (0,3)=Elev50+MinDist−700=−650 ; s19 (4,3)=Elev30+
   **TrigAb90**+MinDist−400=−280 bat (4,2)=Elev50+TrigAb30+MinDist−500=−420. → **tâche #36** (porter
   TriggeredAbilitiesUtility comme terme de tuile). NB s19 : notre ClosestEnemy sélectionne encore le
   mauvais ennemi (nous 3/3 vs natif −400/−500=darkaAsmodai) → raffiner la métrique/filtre de sélection
   (hex vs chemin ? `IsTargetable`/`GetOnlyTargets` ?) ; avec le bon MinDist seul, s19 flippe déjà.
8. **Angle mort heal/buff (`non-attack-oracle`)** — 4 paires (1121, 1113, 1163, 1151) + 1202.
   **⚠ REFRAME 2026-07-20 (#34, case-34-nonattack-oracle.md §MAJ)** : ces 5 abilities sont des
   playbooks **NC natifs** (`EvaluateNonComparable`, AUCUN `Make*Predictions`) — le stage était
   un double mal-classement (registre NC offline ignorant + conjecture heal/buff). Déblocage =
   **porter les 5 évaluateurs NC** (tâche #44, comme 1179/1180/1118). Le décodeur
   Probable{Heal,Effect}Event est FAIT + validé (partie A #34 : `aiPlaybookPredict` renvoie
   `healEvents`/`effectEvents` ; HealPlaybook ab 18 validé live) — il sert les familles
   Comparable (heal 18, SpiritLeech…) ; scoreur heal offline + branchement = tâche #45.
   **PORTAGE FAIT (#44, case-44-noncomparable-lead8.md)** : 1113/1121/1163/1202 portés + enregistrés
   → l'étape `non-attack-oracle` disparaît ; **1113 devient un hit** (31337 s11) et l'ability passe
   **24/29 → 25/29** (move 31/35, prédiction 21/21 inchangés). **Cible 1163 FIXÉE (#47)** : la
   prédiction de la charge s'évalue **au contact** (tuile adjacente à la cible, mirror
   `TilesUnitCanMoveToChargeTarget`), pas depuis la tuile de cast — 31337 s12 devient un hit,
   ability **25/29 → 26/29 (89 %)** (move 31/35, prédiction 21/21 inchangés). L'hypothèse « bonus
   +728 » est RÉFUTÉE (effet posé à l'exécution seulement, cf. case-44 §3). Restent : 1121/1202 non
   confrontés live faute de porteur sur ces seeds ; **1151 porté mais PAS enregistré** — porte de
   décision native non résolue (le natif décline 1151 là où le décompilé dit qu'il devrait tirer :
   sur-tir mesuré → tâche #46).

## 5. Usage

```bash
# runner existant
python engine_agreement_stages.py --runner N --steps 20
# batch : build/walk/dispose un runner isolé par seed (state-file DÉDIÉ _stages_duel_state.json)
python engine_agreement_stages.py --build --seeds 777,909 --steps 20 [--json out.json] [-- <args rl_duel build>]
```

Pré-requis : session warmee ; hooks ≥ 2026-07-19 (aiPlaybookPredict col/row + champs
shieldDmg/forceOverkill du décodeur). La sonde est READ-ONLY côté état (aiPlaybookPredict) ;
le walk applique les actions natives (runner isolé recommandé).

## 6. Suites (plan réconciliation acté)

- **Étape 2 — fermer le feed** : ✅ resync prédicteur PER-STEP FAIT (#33) — audit cold-vs-fresh
  table par table sur toute la marche 31337/777 : le SEUL canal dynamique manquant était
  `actorstats_by_id` (`TotalAttacksMade`, MartialInspiration), re-capturé par-pas dans
  `refresh_shields`. Tout le reste est soit statique (`ctx` INITIAL, board, mult/ablvl), soit
  recalculé live à la décision (aura d'adjacence, positions, hp, effets) → `feed=0` sur les
  paires confrontées. Reste ouvert : l'audit du read-set peut resurfacer un canal cold si un
  nouveau modificateur indexé par un compteur mid-bataille apparaît (le harnais le classera `feed`).
- **Étape 3 — endgame** : runner offline complet + replay-diff (supprime la couture RPC),
  chantier `runner_engine`.
