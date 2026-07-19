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
| seed 31337 (20 pas) | 12/18, 13/18 | 6/13 | agrégé 909+31337 : **8/14 (57 %)**, 1 feed, 5 logic | **2 prediction**, 2 utility-logic, 3 non-attack-oracle, 1 generator-overfire, 5 pos-downstream |
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
3. **Staleness prédicteur PROUVÉE** — 31337 s16, u79 ab=1191 tgt=87 : off 598-898,
   nat 994-1976, **fresh == natif (`feed=True`)** ; cf_nat=56.2 > eng=51.2 → le miss flippe.
   → justifie l'Étape 2 (resync prédicteur per-step, pas seulement les boucliers).
4. **Bornes ±1-5 qui flippent le kill-flag** — 777 s06 (min 1390 vs 1385), 31337 s05
   (3006 vs 3009), 31337 s08 : max 1498 vs 1499 **→ kill off=False nat=True** (cap à hp-1) ;
   même run raw max 1498 vs 1949 (overshoot natif non modélisé). Un ±1 à la frontière hp
   = grand écart d'utilité (leaves kill). Chercher un arrondi/roll-min systématique.
5. **killSure fantôme (raw sur-évalué)** — 31337 s13, u93 ab=69 tgt=83 : accurate min OK
   (2783 vs 2704) mais raw off 4428-6640 vs nat 2704-4056 → **killSure off=True nat=False**.
   L'overshoot raw offline est trop haut (mécanisme distinct du lead 4 : sens inverse).
6. **NC overfire (gates trop lâches)** — famille : AdMech 1118 self-cast émis là où le natif
   bouge/attaque (2 occurrences AdMech + 31337 s17 : nat 69→87 u_off=192.7 pourtant le moteur
   sort 1118→77 par ORDRE de tier NC) ; 909 s10 : 1180 HeroicFusillade émise, natif attaque
   (pred quasi égales 1362 vs 1365, cf_nat=90.1). Le playbook NC natif GATE là où le nôtre émet.
7. **Move pur : le natif ne maximise PAS Tile7+MinDist** — 909, 3/3 move-formula au MÊME
   pathdist : s04 nat(3,2) tile=15 vs eng(0,3) tile=50 ; s05 nat(5,5) 20 vs eng(6,4) 40 ;
   s19 nat(4,3) 30 vs eng(4,2) 50. À pathdist égale le natif choisit systématiquement une
   tuile de tile_composite INFÉRIEUR → soit la feuille distance diffère (MovementSuggestion(32)
   = [Tile(7), **TileDistance(33)**], pas MinDistanceToClosestEnemy(16) d'UnitMovement(6)),
   soit le terme Tile est sur-pondéré chez nous. RE ciblé requis (`move.py` porte UnitMovement(6)).
8. **Angle mort heal/buff (`non-attack-oracle`)** — 4 paires (1121, 1113, 1163, 1151) + 1202
   inconfrontables : `aiPlaybookPredict` ne décode que les ProbableDamageEvent. Étendre le
   décodeur aux Probable{Heal,Effect}Event (@181135820/@1811359a0, strides différents).

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

- **Étape 2 — fermer le feed** : resync prédicteur PER-STEP (lead 3 le prouve) + audit du
  read-set natif de l'IA (décompilé) pour garantir l'identité des entrées.
- **Étape 3 — endgame** : runner offline complet + replay-diff (supprime la couture RPC),
  chantier `runner_engine`.
