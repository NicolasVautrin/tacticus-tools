# Move-guard — note de reprise (handoff post-compact)

> 🎯 **CONCLUSION SESSION 2026-06-21 (lire EN PREMIER) — « over-extension dominant » était
> en grande partie un BUG D'OUTILLAGE, pas un déficit de comportement.**
> Root cause trouvé (reproduction transcript + ground truth) : **`cmd_play` laissait
> `currentPlayer=ennemi` après le tour IA** (son endturn ne flippait pas — quirk H19 — donc
> `_ai_turn` jouait MA team = AI-as-me sur-avançait mes units), et l'agent, voyant cp=ennemi
> (+ note `loop.md` « aiturn manuel requis »), lançait un **`aiturn` manuel = 2ᵉ tour gratuit
> à l'IA** → carnage/abandon R1-R3 attribué à tort à l'over-extension + au « guard aveugle » (H40).
> **CORRIGÉ** : `cmd_play` ET `cmd_aiturn` font endturn-retry jusqu'au flip ennemi → l'IA joue
> l'ADVERSAIRE (jamais ma team), finit cp=moi, affiche « NE lance PAS aiturn ».
> **VALIDÉ** : vague propre post-fix (seeds 70057-70061) = **4/5 = 80 %** (vs 40 % pré-fix),
> 0 abandon, le seul L = timeout/bombardement (structurel, l'agent gagnait), over-extension
> **non-décisive** sur tous les W, et **70060 = guard validé en POSITIF** (il a flaggé
> Sarquael-forward=mort, l'agent a retraité, dive-punish → 0 perte héro). H40 = **mauvaise
> attribution, PURGÉE** de doctrine-learned.md + loop.md (loop.md reset à 57 lignes, process only).
> **Move-guard livré : per-turn, enemy-only 1-tour, fidèle (sim==live vérifié), `action_log`
> replay-to-state.** RIEN COMMITÉ (rl_duel.py + skill/workflow + doctrine).
> Reste honnête à creuser : n=5 (petit) ; le synthé sur-tague encore « over-extension » sur des W (cosmétique).

> But initial : gater l'**over-extension** au geste (pas par la doctrine). Diagnostic de
> départ : **savoir↑ ≠ comportement↑**. ⚠ RÉVISÉ ci-dessus : le « dominant » était gonflé par le bug `cmd_play`.

## ⭐ MODÈLE COURANT (verrouillé — lire CECI en premier ; l'historique ci-dessous = le chemin)

**1 sim = `[mes moves] → endturn → 1 tour IA ADVERSE (CheatRunAIMessage) → NET`. Jamais plus loin.**
- **L'IA ne joue JAMAIS ma team** dans la sim (elle sur-étend → biais). Ma team = mes moves explicites uniquement.
- **NET = leurs_pertes − mes_pertes sur CE tour.** NET<0 = l'IA me focus AVANT moi = **over-extension** ; NET≥0 = **focus-first**.
- **Gate PER-TURN** : appeler `guard` AVANT chaque `play` (T1 inclus). Le tour courant est reconstruit en **rejouant `action_log`** (mes vrais moves + tours IA adverses déterministes) sur un clone T1 (`_replay_log`) — l'over-extension se construit tour par tour, le danger n'est visible qu'au tour où l'IA peut atteindre, d'où le re-gate à chaque tour.
- `--climb` = pull-back des units mortes/≥50% jusqu'à focus-first (NET≥0) ou cap.

**Faits VÉRIFIÉS qui fondent le modèle** :
- Clone T1 (`initAndStart keepExisting`) == déploiement live, **0 mismatch** (la « discordance de déploiement » était un MISREAD des agents : positions post-move / bascule de perspective post-endturn, PAS un bug).
- Rollout IA **déterministe** (3 clones identiques) même avec `RandomizeAiInput=True`.
- `aiPlayByUnit` (driver live) == `CheatRunAIMessage` (driver sim), **0 diff** au tour de contact → le replay reconstruit l'état live à l'identique.
- `maxPump=2000` requis (sinon `totalActivations=0` = IA inerte = faux « propre » ; bug de probe à 12).

**Code** (`scripts/python/rl_duel.py`) : `_sim_turn`, `_replay_log`, `_enemy_turn` (retry endturn H19 + garde-fou « jamais l'IA sur ma team »), `_hill_climb` (pull-back, stop NET≥0), `_verdict_focus`, `cmd_guard` (per-turn), `cmd_play` (enregistre `action_log`). Validé end-to-end (70042 : guard T1 flag aggressive Mephiston MORT NET−4.58 ; play ; guard T2 via replay ; climb −4.58→−0.69).

**Abandonné** (ne pas y revenir sans raison) : le **2-ply `_sim_plan`** (myope : kill à T3-T4 hors fenêtre) ; le **rollout deux-côtés** (l'IA jouant ma team rescue/biaise — le delta isolé ne marchait pas) ; l'idée de gater **seulement** au tour décisif (T1 doit être gaté aussi — l'over-extension T1 existe, ex. 70042). Le tour décisif n'est PAS deviné : il se révèle là où le delta/NET explose.

---
*Ci-dessous : l'historique de la session (chemin parcouru, expériences, hypothèses dont certaines réfutées). Le MODÈLE COURANT ci-dessus prime.*

## OÙ ON EN EST
- Design du move-guard **validé par l'utilisateur** (ci-dessous).
- **ÉTAPE 1 TRANCHÉE (read-only, fini)** → **RPC natif `exposureView`, PAS Python-pur.**
  - Lecture faite : `rpc-view.ts`, `internals.ts`, `projection.ts` (`computeDangerZone` +
    `computeAttackPlans` + `projectUnitsFull`), `effects.ts`.
  - Ce que `decisionView` donne DÉJÀ : `dangerZone` (`computeDangerZone`, projection.ts:273) =
    géométrie de menace ennemie mais **union de tiles + counts par-ennemi SEULEMENT** (pas
    d'attribution par-ennemi, pas de magnitude) → répond « T menacé ? » en booléen, pas
    « T létal ? » ; `attackPlans` = MON dégât sur l'ennemi (**mauvais sens**) ; `units[].effects`
    = flag **overwatch armé** par ennemi (✅ réutilisable) ; hp/pos/alive/ctrl (✅).
  - **Raison du RPC** : la métrique repose sur la MAGNITUDE `reach_dmg = Σ dégât E→U`, et seul
    `DamagePredictionQuery.GetAllPredictions` donne un dégât fidèle (armure/pierce/traits/shield),
    invoqué avec l'ENNEMI comme attaquant = invoke IL2CPP natif **impossible depuis Python**
    (qui ne voit que le JSON). Python pur ne ferait qu'un grossier « U dans la danger zone » = le
    bruit à éviter (être menacé = normal ; le failure mode = portée LÉTALE + tuile sûre dispo).
  - **Zéro RE — primitives prouvées dans ai-step** : `exposureView` = `computeDangerZone` +
    `computeAttackPlans` INVERSÉS (ennemi=attaquant, MES units=cibles). Briques : `GetMovableTilesFor`
    ∪ `GetAllTilesInAbilityRange` (garder les tiles PAR-ENNEMI au lieu d'unionner) ; `GetAllPredictions(E,
    E_best_tile_vs_U, E_ability)` + `get_Item(U)` (offsets connus : hp@0, dmg Min@0x60/Max@0x64) ;
    `GetBestTileToAttackFrom(E, E_movable, U, ability)` ; overwatch armé via `readEffectsByUnit`.
  - **Sortie `exposureView({runnerId, unitId?, maxRank?})`** par MON unité contrôlée+vivante à sa tuile
    COURANTE (post-move, pré-endturn) : `{unitId, hp, threats:[{enemyId,vis,ability,dmgMin,dmgMax,
    overwatch}], reachDmgMin, reachDmgMax, lethalSure:(min>=hp), lethalPossible:(max>=hp),
    movableSafeTileCount, hasSafeTile:(movable ∖ dangerZone-union), exposed:(lethalPossible && hasSafeTile)}`.
    Pas de simulation de tuile hypothétique : U est déjà posé à T dans l'état live ; le « ∃ tuile sûre »
    se résout géométriquement (movable set ∖ danger zone).
  - **⚠ TIMING — NE PAS builder pendant une vague** : implémenter `exposureView` = éditer `frida/hooks/*`
    → rebuild → **reinject**, et le reinject DÉTRUIT les runners de la vague en cours. Attendre la fin de
    la vague `wf_5f189fed-724` avant d'implémenter. (Step 1 = décision read-only, faite ; Step 2 = code.)

## MAJ STEP 2 — exposureView LIVRÉ + DÉCOUVERTE turn-gating → design FAITHFUL clone+endturn
- **exposureView v1 LIVRÉ + testé en combat manuel** (hors workflow, runner build seed 4242 +advance 2) :
  `frida/hooks/features/ai-step/projection.ts` (`computeExposure`) + `rpc-view.ts` (`ctx.rpc.exposureView`).
  Marche : 83ms, read-only (mutated=False), dégât fidèle ennemi→U via GetBestTileToAttackFrom+GetAllPredictions.
  Refactoré : le natif ne fait QUE le dégât fidèle (champs danger retirés ; renvoie `lethalCount`).
- **DÉCOUVERTE DÉCISIVE — `GetMovableTilesFor` est TURN-GATED** : il ne calcule un set de déplacement QUE
  pour le **joueur courant**. Preuve : sur MON tour, `aiMovableTiles({side:"friendly"})` = mes units 17-22 tiles ;
  `({side:"enemy"})` = **0 partout**. CONSÉQUENCES : (a) le `dangerZone` natif (`computeDangerZone`) renvoie 0
  sur mon tour (= pourquoi `oracle.py` passe par une danger zone GÉOMÉTRIQUE Python) ; (b) **exposureView ne
  capture que la menace depuis la position COURANTE de l'ennemi** (computeExposure ajoute la main-tile de E à
  un set autrement vide) = notion **A** (« qui peut me toucher maintenant »), PAS la menace next-turn move-in
  (notion **B** = `reach_dmg` de ce doc).
- **PIVOT VALIDÉ (test destructif runner jetable)** : `endturn` flippe currentPlayer 3→4 (IA) → ALORS
  `aiMovableTiles({side:"friendly"})` (= désormais l'IA) renvoie des sets NON-VIDES (8-20 tiles). Donc
  **clone → endturn → les ennemis deviennent actifs → mouvement débloqué → danger/exposition faithful**.
- **ARCHI 2-COUCHES LOCKED** :
  - **exposureView (cheap, notion A)** = détecteur de CONTACT + GATE. Si mes units ont déjà reachDmg>0 (positions
    ennemies courantes) → au contact → NE PAS lancer la sim lourde. Si reachDmg≈0 partout → pré-contact → lancer.
  - **clone + endturn (faithful, notion B)** = la vraie mesure. Deux usages : **Capacité** (clone→endturn→PAS d'IA→
    exposure de MES units depuis ennemis actifs→jeter = `reach_dmg` sans estimation) ; **Outcome réel**
    (clone→endturn→`CheatRunAIMessage`→diff HP→jeter = « U meurt-il vraiment » = label ground-truth de calibration).
    NB `EndTurn` n'enchaîne PAS l'IA (message moteur passif) ; faire jouer l'IA = `CheatRunAIMessage` (1 tour
    d'équipe, hook `cheat.ts`) ou `aiPlayByUnit` (per-unité). Pour la Capacité, PAS besoin de faire jouer l'IA.
  - **NOTE impl** : après endturn sur le clone, le joueur courant = IA → `computeExposure` doit calculer pour les
    units NON-courantes (mes units) comme VICTIMES, attaquées par les courantes (IA) → ajouter un flag
    `victimNonCurrent` (swap du filtre ctrl). Sinon il calcule l'exposition des units IA (mauvais sens).
- **SCOPING (décidé)** : la sim clone+endturn ne tourne qu'à **T1 (+ T2 rare, si pré-contact)** — l'over-extension
  est une faute de PHASE D'APPROCHE ; une fois au contact (T3+) tout le monde trade, la question tuile-sûre-vs-létale
  a moins de sens. → **≤2 sims/combat** → coût (~798ms ×1-2) négligeable → faithful total = le bon choix.
- **CLONE T1 = TRIVIAL (le caveat MatchState.Copy est MOOT à T1)** : le clone du projet = reprendre la config +
  rejouer les messages (ReplayRunner). Or **à T1 le SEUL message antérieur à mon coup = le déploiement (`addUnits`)**,
  = exactement ce que `initAndStart(config, playerUnits)` fait. Donc **le clone T1 = un `initAndStart` frais** (même
  config + mêmes playerUnits → même déploiement déterministe, 0 RNG) **+ replay de MON spec candidat T1**. PAS de
  `MatchState.Copy`, PAS d'inner-runner, PAS de sim 798ms. Briques déjà là : `initAndStart` (clone — coexistence
  multi-runner par défaut depuis 2026-07-03), `applyAction`/`play --spec` (replay), `endturn`, `CheatRunAIMessage`
  (`cheat.ts`), `disposeRunner`. Seul ajout natif = flag `victimNonCurrent` dans `computeExposure`.
  - **Workflow guard T1** : plan spec → `initAndStart(config,playerUnits)` (clone) → replay spec →
    `endturn` (ennemis actifs) → `exposureView(victimNonCurrent)` [Capacité=reach_dmg] [+ option `CheatRunAIMessage`+diff
    HP = outcome réel « U meurt-il »] → `disposeRunner` → si U exposé réviser le spec, sinon commit sur le runner live.
  - **T2 (rare) = seul cas avec vrai replay** : rejouer mon T1 + le **tour IA T1** (messages IA), or `Replay.Messages`
    top-level only → l'histoire IA-inner peut manquer (cf. [[feedback_host_restart_kills_mirror]]). → v1 = **T1-only** ; T2 différé.
## MAJ — ÉVAL = run l'IA sur le clone (ground truth), pas exposureView-reverse
- **Décision design** : on ne mesure plus une *capacité* (exposureView victimTeam) mais l'**OUTCOME RÉEL** —
  clone T1 (initAndStart) → replay mon spec d'approche → endturn → **faire jouer l'IA**
  (`aiPlayByUnit`, capture cascade) → évaluer l'état résultant → dispose. Plus honnête (vraies décisions de focus
  de l'IA, zéro estimation) et rend `victimTeam`/exposure-reverse **inutile** (donc NE PAS l'ajouter). C'est un
  **lookahead 1-ply** (mon coup + meilleure réponse adverse).
- **FONCTION D'ÉVAL = SCORE CLASSANT (différentiel, POV moi)** — PAS « mes dégâts subis » (le bait qui punit un
  dive est BON ; les réactions/overwatch que l'IA déclenche en divant sont PENDANT son tour → déjà dans la cascade) :
  `NET = leurs_pertes − mes_pertes`, chaque perte = `hp_perdu + PÉNALITÉ_MORT × mort`, **pondéré valeur d'unité**
  (v1 = maxHP × multiplicateur de rôle + grosse pénalité mort ; upgrade = poids d'utilité IA `BattleConfiguration.Utilities`,
  déjà dispo, [[project_ai_weights_in_battle_config]]). + **exposition résiduelle** : survivant near-death ET encore
  atteignable = quasi-mort (re-passer exposureView capacité sur les survivants) ← seul usage restant d'exposureView.
  Score classant → compare N positions d'approche, garde le meilleur NET. Alarme = `(perte/quasi-perte) ET NET<0`.
  `worst_unit` = coupable de l'over-extension. Angle mort assumé : 1-ply capture le payoff RÉACTIF (overwatch) mais
  pas mon follow-up ACTIF au tour suivant (2-ply = faire jouer aussi mon IA, différé v2).
- **BUDGET (mesuré 2026-06-20)** : coût 1 sim ≈ **~1.5-2.5s** (tour IA mesuré **1235ms** server + clone/replay).
  **RNG combat DÉTERMINISTE** (2 builds même-seed + --advance 4 avec combat/kills → états BIT-IDENTIQUES, 15 units)
  → **M=1** (1 sim/candidat suffit) + **répond à la question ouverte loop.md** (counterfactual apparié = parfait).
  → **cap dur ~5 sims/décision T1** (hill-climb adaptatif : plan → variante protégeant worst_unit → early-stop dès
  NET≥0 sans perte high-value), × M=1, T1-only (+T2 rare) ≈ **~10s one-time/combat**. **Pas de cap silencieux** :
  best-of-N encore NET<0 → reporter, pas prendre le moins pire.
- **PHASE A LIVRÉE + VALIDÉE (2026-06-20)** : sous-commande `python rl_duel.py guard --spec '[...]'` dans
  `scripts/python/rl_duel.py` (cmd_guard + _snapshot/_apply_spec_to/_score_net/_print_guard_report ; build sauve
  désormais `playerUnits`). Flux : clone `initAndStart` (T1 frais) → replay spec (garde anti-no-op
  réutilisée) → endturn → `aiPlayByUnit` (1 tour IA) → diff snapshots → **NET** → dispose. Ne touche PAS le live.
  - **Score NET** = leurs_pertes − mes_pertes ; perte/unité = frac_maxHP_perdue + `DEATH_PENALTY`(=1.0)×mort ;
    pondération SIMPLE (pas de rôle). before@T1 = full HP = maxHP. worst_unit = ma perte max.
  - **Validé en combat manuel** (seed 4242 T1, runner jetable) : **discrimination MONOTONE** — conservateur NET
    **+0.00** / 2-units-row4 **−0.07** (u95) / ligne-entière-row4 **−0.74** (u99 47% = worst_unit). Ground truth
    (vraie réponse IA, vrais dégâts), déterministe, ~2s/sim. Plumbing end-to-end OK, live runner intact.
  - **À CALIBRER (Phase A, son but même)** : le seuil du LABEL verdict (« approche propre » s'affiche encore à
    −0.74 car u99 47% < seuil 0.5 et 0 mort) — le NET est le vrai signal, le label texte doit être réglé contre
    la vérité-terrain. + signal T1 mineur sur board large (gap grand → 1 move ne sur-étend que jusqu'à row 4) :
    l'over-extension forte est T2 ou via deep-strike (98003) ; le guard T1 catch surtout deep-strike + shove-row-4.
- **CALIBRATION PHASE A FAITE (2026-06-20)** : ajout d'un générateur de specs objectif `guard --auto
  hold|gentle|aggressive` (depuis les movable tiles, direction = centroïde ennemi, anti-collision) +
  `_auto_spec`. Sweep 4 seeds × 3 modes :
  | seed | hold | gentle | aggressive |
  |---|---|---|---|
  | 4242 | +0.00 | +0.00 | −0.34 (u99 17%) |
  | 1234 | −0.49 | −0.40 | −2.26 (mort) |
  | 5555 | +0.00 | −0.98 (u99 98%) | −2.33 (mort) |
  | 9009 | +0.00 | +0.00 | −2.66 (mort) |
  - **Discrimination MONOTONE sur les 4 matchups** (hold ≥ gentle ≥ aggressive) → généralise. Échelle NET :
    `0`=propre / `−0.1..−1.0`=chip / `≤−1.0` (souvent mort/≥50%)=over-extension. **Seuils LABEL réglés** dans
    `_print_guard_report` (3 niveaux : propre / exposition modérée / OVER-EXTENDED ; + trade/bait si perte mais NET≥0).
  - **INSIGHT MAJEUR — mesurer le DELTA, pas le NET absolu** : seed 1234 `hold` = −0.49 (board serré → exposé DÈS
    le déploiement, AUCUNE over-extension de ma part). Donc la vraie mesure d'over-extension = **`NET(plan) −
    NET(hold)`** (coût MARGINAL de l'agressivité) : sur 1234, aggressive −2.26 vs hold −0.49 → coût = −1.77. Le NET
    absolu confond « board dangereux » et « je me sur-étends » ; le delta les sépare.
- **PHASE 2 LIVRÉE + VALIDÉE (2026-06-20)** : `rl_duel.py guard` refait (sim factorisée `_sim_plan` +
  `_hill_climb` + `_unit_of` + `_sc_line`/`_print_losses`/`_verdict` ; `--climb` [`--rank` était pris par le
  niveau du build] + `--cap` [défaut 5 = budget total sims]).
  - **Part 1 — baseline hold + delta** : le guard sim TOUJOURS `hold` ([]) d'abord → reporte
    **delta = NET(plan) − NET(hold)** ; le **verdict est sur le delta** (isole l'over-extension de la danger-zone
    de déploiement). 3 niveaux : propre / exposition modérée / OVER-EXTENDED (delta≤−1.0 ou mort/≥50%).
  - **Part 2 — hill-climb** (`--climb`) : greedy = tant que delta mauvais, retire TOUTES les actions du `worst_unit`
    (le tient en arrière), re-sim, garde si NET s'améliore ; stop si delta≥−0.1 / pas d'amélioration / worst_unit
    hors-spec (exposé au déploiement) / budget. Le NET greedy ne protège QUE les units exposées sans contrepartie
    (retirer une unité qui trade bien baisse leurs_pertes → NET baisse → rejeté). **Sort le spec recommandé**.
  - **Part 3 — gate** : le rapport loud (delta + verdict + spec recommandé) EST le gate ; l'agent commit le spec
    recommandé sur le live. **Pas de cap silencieux** (si best reste OVER-EXTENDED après cap sims, le verdict le dit).
  - **VALIDÉ seed 9009** : plan aggressive NET −2.66 (u101 MORT + u103 71%) → hill-climb (4 sims) `pull u101` →
    −2.00 (u103 MORT) → `pull u103` → **+0.00 propre** ; spec recommandé = u95/u97/u99 avancent, u101+u103 en arrière.
    Le guard a transformé un plan perdant-2-unités en plan propre, automatiquement, sur ground truth.
- **INTÉGRÉ AU SKILL (2026-06-20)** : `.claude/skills/tacticus-battle/SKILL.md` §3 MON TOUR = step T1 OBLIGATOIRE
  (« avant de commit ton ouverture T1, `guard --climb`, joue le spec recommandé si OVER-EXTENDED ») + §8 référence.
  Les vagues workflow (qui lisent le skill) utiliseront donc le guard automatiquement.
- **VAGUE DE MESURE (12 seeds, --auto aggressive --climb, 2026-06-20)** : **8/12 ouvertures sur-étendues** (basePlan
  NET −0.34..−2.66, 4 avec une mort) → **toutes flaggées + corrigées** (NET moyen **+1.50**, **4 morts→0** dans 7/8) ;
  **1/8 (5810)** corrigée partiellement (best −0.94, cap 5 atteint → reporté, no silent cap) ; **4/12 bonnes avances**
  (NET≥0) → **laissées intactes** (2 sims). Sims/décision : **2 à 5, moyenne 3.75** (2 si propre, 4-5 si over-extension
  multi-unités). = preuve du levier comportemental sur ground truth, sans sur-correction.
- **PHASE 2.5 TESTÉE (2026-06-20) — gain MARGINAL, le bottleneck = l'adaptivité de l'IA.** Deux pistes pour
  « affiner plus vite » :
  - **exposureView-capacité** (idée d'origine) : flag `victimsOffTurn` AJOUTÉ à `computeExposure`/`exposureView`
    (sur clone post-endturn, joueur courant=IA → mes units=victimes hors-tour, attaquants=IA actifs avec movable
    débloqué). VALIDÉ (mes 5 units bien listées victimes, 5 IA attaquants). MAIS **~1.4s** (IA active = calcul de
    portée plein, aussi cher qu'un AI-run) **et SUR-APPROXIME** (capacité = tous focus chaque unité → over-pull).
    → **PAS rentable, PAS intégré au climb**. Capacité gardée pour un éventuel threat-preview.
  - **batch-sur-pertes-réelles** (implémenté dans `_hill_climb`) : retirer d'un coup TOUTES mes units mortes/≥50%
    du MÊME sim (ground truth via `_score_net.rows`, pas la capacité). **Pareto-positif** (jamais pire : même/meilleur
    NET — 5810 −0.94→−0.63 —, même/moins de sims — 9009 4→3) mais **gain marginal : avg 3.75 → 3.67 sims**.
  - **POURQUOI marginal (finding ground-truth)** : l'IA est ADAPTATIVE — reculer l'unité focusée la fait **re-focus la
    suivante** → les units deviennent dangereuses SÉQUENTIELLEMENT → la correction est intrinsèquement itérative ;
    le batch n'aide QUE sur le multi-heavy d'un même sim (9009). Pas de raccourci sans over-pull. Le guard est déjà
    efficace (~3.7 sims/T1, one-time/combat) → on n'investit pas plus dans la vitesse.
- **PROCHAINS PAS** : raffinements OPTIONNELS seulement : pull-back GENTLE (au lieu de hold total, garder l'unité
  utile) ; pondération valeur d'unité (utility IA) ; **multi-tour T2+** via reconstruction déterministe (rejouer mes
  coups + re-run l'IA déterministe — PAS de replay des messages IA). `victimTeam`-reverse-sur-live ABANDONNÉ ;
  `exposureView(victimsOffTurn)` existe mais hors du climb.

## VAGUE RÉELLE 70000-70004 (guard actif T1) + 2 FIXES (2026-06-20)
- **Vague `wknbqffdx` : 2 W / 5 = 40%** (70001 W, 70002 W ; 70003/70000/70004 L), runners_leaked=[] (clones guard
  OK sous parallélisme), synthese_failed=[]. 40% CONFONDU : 3/5 = hard-counters structurels.
- **Guard VALIDÉ en réel** : 70001 a flaggé Nicodemus (Healer-engine) advance = **94%-death OVER-EXTENDED** → agent a
  suivi la reco → engine survécu T1 → contribué au W ; 70002 a flaggé Ahriman 31% → pulled → engine survécu (W).
  doctrines_applied move-guard=yes sur les deux. Loop a PROMU le blind-spot en doctrine (doctrine-learned §7 H03 n≈33 :
  « move-guard propre at long range is blind to 2nd-turn contact focus → retreat fragiles by default »).
- **2 LIMITES trouvées en réel** → 2 FIXES :
  1. **Bug target-less (70000)** : `cmd_play`/`_apply_spec_to` faisaient `ac["target"]` en dur → **KeyError** sur
     summon/self-buff → guard abort. **FIX LIVRÉ + vérifié** : helper `_ability_action(ac, plan_ab)` robuste (ciblé /
     hex `to` / target-less / auto-plan), utilisé par les 2 sites. 5 cas testés OK.
  2. **Blind-spot 1-ply (70003 = la loss)** : AI T1 = avance 0-dmg → guard dit « propre » ; le focus-kill atterrit au
     **2e tour IA** (probe validé : AI T1=0 dmg, AI T2=6525+1 kill, même en HOLD). **FIX 2-PLY ADAPTATIF LIVRÉ + VÉRIFIÉ**
     dans `_sim_plan` : si 1er tour IA = avance (`_my_dmg < MIN_CONTACT=500` ET `finalStage == 1` Running) → endturn + 2e
     AI turn, NET sur la fenêtre complète. Note « 2-PLY actif » au rapport. Mécanique de tour : aiturn→finalPlayer revient
     à moi, 2e tour IA = endturn(hold)+aiturn (confirmé live 70003).
- **✅ Fix 2 VÉRIFIÉ (post-compact)** — **vraie cause racine** (re-dérivée du code, pas de l'hypothèse) : le résultat
  `aiPlayByUnit` expose DEUX champs (rpc-drive.ts:390-391) — `finalStage` (numérique, **1 = Running**, cf. `_advance`
  l.99) ET `finalStageName` (string `"Running"`). Le déclencheur 2-ply comparait le champ **numérique** à la **string**
  `ai.get("finalStage") == "Running"` → **toujours False** → le 2-ply ne firait JAMAIS (d'où hold 70003 = NET +0.00
  trompeur, pas de focus T2 vu). Corrigé en `ai.get("finalStage") == 1`. **Tests de confirmation** :
  - 70003 `guard --auto hold` : note « 2-PLY actif » imprimée, **NET −2.00** (vs +0.00 avant), `u95 astraOrdnance
    6525→0 MORT` = exactement le focus-kill T2 du probe manuel. VERDICT OVER-EXTENDED ✅
  - 1234 (contact immédiat, AI T1 inflige 38% à templHelbrecht ⇒ `_my_dmg ≥ 500`) : 2-ply **NE fire PAS** (note absente,
    reste 1-ply, NET −0.38). Gate `_my_dmg < MIN_CONTACT` correct **dans les deux sens**. ✅
  - Note : sur 70003 même le HOLD perd astraOrdnance ⇒ le vrai problème de ce board est le déploiement/positionnement,
    pas seulement l'over-extension marginale (delta hold↔plan = +0.00). Le verdict OVER-EXTENDED se déclenche via la
    branche `heavy` (une unit morte), ce qui est le bon filet de sécurité.
- État compile : rl_duel.py COMPILE OK. Hooks inchangés depuis sessionId=4 (exposureView+victimsOffTurn déjà injectés).
  Rien commité. **Les 2 fixes du wave sont livrés + vérifiés.**

## LE DESIGN (proposé + accepté)
Philosophie = celle de la garde anti-no-op : **surface + acknowledge, jamais forbid**. On gate
l'**exposition létale NON FORCÉE NON ASSUMÉE**, pas l'agressivité (bait/screen/trade délibéré passe
s'il est DÉCLARÉ — la déclaration EST la compétence procédurale).

Métrique par unité U sur sa tuile de fin de tour T :
```
reach_dmg(T) = Σ ennemis E pouvant move à portée d'attaque de T au prochain tour :
               dmg estimé E→U (armure/pierce/traits) + overwatch armé sur le chemin de U
lethal   = reach_dmg(T) ≥ U.hp
unforced = ∃ T' atteignable ce tour, reach_dmg(T') < U.hp, qui PROGRESSE quand même
EXPOSED  = lethal ∧ unforced
```
Où : dans `rl_duel.py cmd_play`, check **pré-endturn** (réutilise le pattern guard anti-no-op +
les données decisionView). Calcul d'abord **géométrique approché** (sur-approx OK → faux positifs =
expositions assumées).

Phases :
- **Phase 1 — RAPPORT (non bloquant, à livrer en 1er)** : à l'endturn, imprime
  `u<id>@T : reach=<X> vs hp=<Y> [EXPOSED] · tuile sûre: T'`. Pur Python sur decisionView.
- **Phase 2 — GATE** : EXPOSED + pas déclaré → **STOP avant endturn** (pas de tour gratis à l'IA) →
  l'agent met à l'abri OU ré-émet avec `"acceptExposure":[{"unit":id,"reason":"bait|screen|forced|value-trade"}]`.

Bonus : le guard **produit le chiffre** → KPI de comportement = « nb d'unités perdues en EXPOSED
(tuile sûre dispo) / combat », qui peut tendre vers 0 (remplace le tag-vibe `over-extension`).

## COMMENT ÉVALUER LE MOVE-GUARD (plan validé en discussion)
Piège à éviter = **évaluer au win-rate** : confondu (½ des L sont STRUCTURELS — reach-fail/hard-counter,
over-extension PAS décisive) + seeds différents = matchups différents → rien d'attribuable. Et le tag
`over-extension` est un vibe-tag (contaminé), pas une mesure.

**Métrique PRIMAIRE = comportementale, produite par le guard (ground-truth, pas un tag)** :
- **KPI = `morts-EXPOSED / combat`** = unités perdues en exposition LÉTALE non-forcée non-assumée (tuile
  sûre dispo + pas d'`acceptExposure`). Mesurable MÊME sur un L structurel → découple comportement / issue.
  Cible → ~0. C'est le chiffre qui REMPLACE le vibe-tag `over-extension`.

**Design = counterfactual APPARIÉ (mêmes seeds, ON vs OFF)** pour annuler le confond matchup (VALIDATE,
cf. §Modes loop.md). **Pré-requis à tester d'abord** : RNG de combat déterministe à seed+actions fixés ?
(replay 2× mêmes actions → identique ?) → si oui counterfactual propre ; sinon same-matchup bruité → ↑N.

**3 phases** :
- **A — Instrument-only (calibrer AVANT de gater)** : Phase 1 RAPPORTE sans bloquer. Valide
  *précision* (flag EXPOSED → l'unité meurt-elle vraiment ?), *recall* (mort over-extension du journal →
  était-elle flaggée ? faux négatifs = géométrie/dégât sous-estime), *faux positifs* (EXPOSED mais survit/
  trade correct). Sort le **KPI baseline** non-gardé = le chiffre à battre.
- **B — A/B apparié** : ~10-15 seeds (balancés + 2-3 structurels en contrôle), chacun 2× (gate-OFF=Phase A,
  gate-ON=Phase 2). Compare par seed : morts-EXPOSED (↓ ON), flip W/L (attendu SEULEMENT sur balancés),
  déclarations acceptExposure.
- **C — Décision** : guard « marche » si (1) **comportemental** morts-EXPOSED/combat chute (→~0 balancés) ;
  (2) **précision** FP bas → l'agent RETRAITE bien plus qu'il ne déclare, ET chaque acceptExposure
  **justifié post-hoc** (bait a livré ? trade favorable ?) ; (3) **issue** (sous-ensemble balancé seulement)
  win-rate ↑, structurels INCHANGÉS (si un L structurel flippe → suspecter la métrique).

**Failure mode à surveiller = le rubber-stamp** : agent qui déclare acceptExposure à CHAQUE flag pour
avancer → comportement inchangé. D'où critère (2) : mesurer ratio retraite/acceptExposure + AUDITER a
posteriori chaque acceptExposure (« bait » qui meurt pour rien = mauvaise déclaration). Contrepartie de
« acknowledge ≠ forbid » : la déclaration doit être REDEVABLE.

## CE QUI A DÉJÀ ÉTÉ FAIT CETTE SESSION (tout livré, vagues 95xxx→98xxx jouées)
Workflow `.claude/workflows/tacticus-loop-wave.js` :
- **Ordonnanceur à priorité** (budget global MAX≤15 ; synthese > verif > combat ; synthese=1 =
  single-writer SANS mutex ; jointure par combat via `st{pending,verdicts}` + compteur).
- **Modèles** : combat=opus (hérité), verif=**sonnet**, synthese=opus (hérité) ; `verifModel`
  override ; `model` global force tout.
- **Couche SYNERGIE** : recon pipeline réordonné `2 (kits) → 2bis (synergies RECALL+INFERENCE) →
  2ter (WINCON DÉRIVÉE des synergies, counter = la SOURCE pas la sortie amplifiée) → 3` ;
  `BATTLE_SCHEMA.synergies` ; synthese §6bis inscrit dans **wiki §5bis** (nouvelle section, registre
  de combos = arêtes). MARCHE (98003/98004 : wincon nomme synergie+source, inférence d'anti-synergie).
- **`GC_HELP`** (mode d'emploi gameconfig.py) injecté dans prompts combat+verif.

`scripts/python/rl_duel.py` :
- **Garde anti-no-op v2** : `cmd_play` abort sur `ok=False`/`error` (tous kinds) ; un **move**
  n'échoue que sans AUCUN effet = `mutated=False ET eventCount==0` (move dans `changes`/`mutated`,
  PAS dans `events`) ; ability/finish n'avortent QUE sur ok/error ; doc format `to:[col,row]` ;
  spec vide → stop. (`mutated = before.sig≠after.sig`, sig=`squadId:col,row:hp`.)

`scripts/python/gameconfig.py` :
- **Résolution par NOM d'affichage** (`Actus`→`admecManipulus`) + flag `--unit` + suggestions.
- **Tolérance au MODE** (`_auto_resolve`) : `--ability X` introuvable → cherche X en trait/effet/unité
  et le résout (`--ability TeleportStrike` → « c'est un TRAIT » + desc). « introuvable » = absent partout.

`docs/rl/toolfeedback.md` : TF08 (footgun format/no-op), TF09 (nom unité), TF10 (mode/catégorie).

### Vérifs lentes — 3 causes distinctes (toutes adressées)
1. **Nom** (TF09, Actus) : l'agent a le display-name, pas la clé → `gameconfig.py` résout le nom now.
2. **Mode/catégorie** (TF10, TeleportStrike) : bon nom, mauvais flag (`--ability` sur un TRAIT) →
   `gameconfig.py` tolérant au mode (`_auto_resolve`).
3. **Numérique/scaling** (verif 98001 `SquigHound Grot summon "pumped"`) : lookup OK en 5 appels, PUIS
   **35 appels de rabbit-hole** dans `data/*.json` pour trouver POURQUOI le summon est « pumped »
   (scaling rareté/niveau). gameconfig (texte de règles) ne peut PAS confirmer un NOMBRE live émergent.
   → **fix : verif prompt = règle STOP + budget** : portée = corroborer la RÈGLE DISCRÈTE, pas un nombre ;
   claim numérique/scaling → verdict **plausible** (chiffre confirmé en jeu) ; **≤5 appels gameconfig.py**,
   JAMAIS de spelunking `data/*.json` ; sinon conclure (plausible/contradicted) et ARRÊTER. → candidate **TF11**.

## ÉTAT INFRA (au moment du compact)
- Host UP, session Frida id=1 warmée (pid Tacticus 50496, build kqkbjqfb6c). Pas de reinject depuis.
- Vague `wf_5f189fed-724` (98000-98004, 5 combats opus / pool 15) **EN COURS** ; 98003 L (snowball 1v12),
  98004 W (3v0) déjà synthétisés ; 98000/98001/98002 en vol. Single-writer tient (entrées propres).
- Métriques loop.md ~10 W / 35 (lag : synthèses 98xxx pas toutes au step métriques).

## PROCHAINS PAS
1. Lire les 3 fichiers decisionView → trancher Python-pur vs RPC `exposureView`.
2. Construire **Phase 1 (rapport)** du move-guard dans `rl_duel.py`.
3. Lancer une vague de validation → vérifier que le KPI « unités EXPOSED perdues » est mesurable et baisse.
