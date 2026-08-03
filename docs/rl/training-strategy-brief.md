# Brief — Stratégie d'entraînement RL pour Tacticus

**Audience** : Codex / Gemini (consultés via `ai-bridge` MCP, mode agent read-only).
**But** : converger à 3 sur une stratégie d'entraînement avant de coder.
**Rédacteur** : Claude Code (Anthropic), à partir de l'état du repo au 2026-05-23.

---

## 1. Le jeu — résumé technique

**Warhammer 40K Tacticus** (Snowprint Studios). Build PC Windows :
- Unity 6 (6000.3.13f1 au 2026-08-04) — moteur natif IL2CPP AOT, binaire `GameAssembly.dll` (~60 MB)
- **Jeu tactique tour-par-tour** sur **grille 15×15** type X-COM / Fire Emblem
- 5 unités joueur vs N ennemis (typique 5v5 à 5v10 selon le mode)
- Chaque unité dispose : déplacement (range variable), abilities actives/passives, **overwatch** (réaction tir adverse), abilities ultimates
- **Aléa** présent : crit chance, block chance, miss chance, certaines abilities (% to apply debuff)
- État complet : positions + HP + AP + cooldowns + buffs/debuffs + tour. **Information parfaite** (les deux joueurs voient tout).

## 2. Infrastructure existante (chemins absolus)

### Hooking & runtime
- (file:///C:/Users/nicolasv/tacticus-tools/CLAUDE.md) — règles projet, pièges connus
- (file:///C:/Users/nicolasv/tacticus-tools/STATUS.md) — état "vivant" du projet, layouts validés
- (file:///C:/Users/nicolasv/tacticus-tools/frida/hooks/main.ts) — entry point Frida injecté
- (file:///C:/Users/nicolasv/tacticus-tools/frida/host/) — serveur Node Express + WS qui pilote l'injection
- (file:///C:/Users/nicolasv/tacticus-tools/frida/public/) — frontend browser de pilotage

### Pipelines RL validées end-to-end
- (file:///C:/Users/nicolasv/tacticus-tools/frida/hooks/features/normalize-bc.ts) — normalisation `BattleConfiguration` live (autoBiS items, auto-spawn, formula `IStatsFormula.StatsUsingProgressionIndexFor` direct)
- (file:///C:/Users/nicolasv/tacticus-tools/frida/hooks/features/normalize-bc/) — submodules : `formula.ts`, `live-bc.ts`, `items-catalog.ts`, `json-build.ts`, `debug-rpcs.ts`
- (file:///C:/Users/nicolasv/tacticus-tools/frida/hooks/features/sim.ts) + (file:///C:/Users/nicolasv/tacticus-tools/frida/hooks/features/sim-engine.ts) — runner isolé via `buildPatchedRunner`, sim sans toucher la game UI
- (file:///C:/Users/nicolasv/tacticus-tools/frida/hooks/features/ai-utility-trace.ts) — **capture playbook AI scriptée du jeu + utility scoring → JSONL** (commit `c406520`). C'est de la donnée expert prête à l'emploi.
- (file:///C:/Users/nicolasv/tacticus-tools/frida/hooks/features/cheat.ts) — `runner.Apply(CheatRunAIMessage)` permet de faire jouer l'AI scriptée à la place du joueur
- (file:///C:/Users/nicolasv/tacticus-tools/docs/normalize-bc-pipeline.md) — snapshot validation

### Embryon RL existant
- (file:///C:/Users/nicolasv/tacticus-tools/frida/hooks/features/rl/bridge.ts) — RPC `rlGetObservation(unitId?)` → tenseur 15×15×6
- (file:///C:/Users/nicolasv/tacticus-tools/frida/hooks/features/rl/tensorizer.ts) — projection `MatchState` → tenseur (HP friendly/enemy, status, elevation, overwatch, legal_moves via `Pathfinders.FindReachableTiles`)
- (file:///C:/Users/nicolasv/tacticus-tools/frida/hooks/features/rl/normalizer.ts) — **legacy** : table hardcodée D3 baseline stats. À supprimer (remplacé par `normalize-bc`)

### Décompilation & dumps (lecture humaine, NE PAS hardcoder)
- (file:///C:/Users/nicolasv/tacticus-tools/sources_win/) — Ghidra decompile de `GameAssembly.dll` (gitignored)
- (file:///C:/Users/nicolasv/tacticus-tools/data/dumps/) — Il2CppDumper tables (gitignored, per-hash)

## 3. Capacités mesurées

| Capacité | Métrique mesurée | Source |
|----------|------------------|--------|
| Round-trip "inner-sim + commit turn-1" | **798 ms** | memory: `project_sim_and_commit_turn1` |
| Build runner isolé + observe | OK, full combat 7 tours validé | conv résumé compact |
| Faire jouer l'AI à la place du joueur | OK via `CheatRunAIMessage` | memory: `project_ai_plays_player` |
| Replay sim isolée via `ReplayRunner` | OK ctor, `InitializeBattle` nécessite init inner runner d'abord | memory: `project_replay_sim` |
| MatchState deep copy | `Copy()` produit un vrai clone, MAIS 67 services tiennent leur propre `_state` ref → swap `runner._state` seul = no-op | memory: `project_matchstate_copy` |

## 4. Contraintes & pièges identifiés

### Latence (le problème #1)
- **800 ms par commit turn-1**. Pour un MCTS 1000 sims/décision → 13 min par coup. Rédhibitoire pur AlphaZero tel quel.
- Le moteur natif IL2CPP est *the* bottleneck. Atténuations possibles :
  - N runners isolés en parallèle (cf. memory `project_sim_and_commit_turn1`)
  - **Sim hors-moteur** réimplémenté en TS/Rust (très gros chantier, mais 1000× speedup)
  - Budget MCTS très réduit (50-100) + policy net précise

### Pièges Frida à NE PAS réintroduire (cf. (file:///C:/Users/nicolasv/tacticus-tools/CLAUDE.md))
- Heap scans auto → UnityFreezeDetector kill le process
- Broad-hooks sur méthodes UI hot (Get*/Has*/Compute*/Try*) → cctor cascade crash
- Hook permanent sur property getters Newtonsoft → 27 000 appels/s → frame >960 ms → crash
- Toute RVA hardcodée → invalide au prochain build hash, hook fire sur du code aléatoire

### Faiblesses connues de l'AI scriptée
- **Suicide overwatch** : l'AI ne détecte pas les zones d'overwatch ennemies (Re'vas, Maugan Ra, Forcas, Calandis). Memory: `project_overwatch_blindspot`. Si on fait de l'IL pur sur ses trajectoires, on hérite de ce blind spot.
- Poids AI scoring lisibles dans `BattleConfiguration.Utilities` (memory: `project_ai_weights_in_battle_config`) — pourrait servir de prior interprétable.

### Branching factor
- ~5-10 unités actives par côté × ~50-200 tiles légales par unité × ~3-5 actions (move/abilities/targets/end-turn)
- Estimation : **10³–10⁴ actions par demi-coup unité**. Plus proche de Hex/StarCraft (BF 10³-10⁴) que de Go (BF ~250).

### Aléa
- Crit/block/miss probabilités → AlphaZero pur suppose déterminisme. Variantes possibles : Stochastic MuZero, chance nodes à la TD-Gammon.

## 5. Question structurante

> **Quelle stratégie d'entraînement RL est la plus pertinente pour Tacticus, étant donné l'infrastructure existante, les contraintes mesurées (latence 800 ms/turn, branching factor 10³-10⁴, info parfaite, aléa local) et le compute solo dispo (1 station de travail Windows + GPU consumer) ?**

### Approches déjà discutées entre Claude et l'utilisateur

| Approche | Statut discussion |
|----------|-------------------|
| **A. AlphaZero (MCTS + policy/value net + self-play)** | Théoriquement optimal pour la classe de problème (turn-based info parfaite), MAIS latence 800 ms × MCTS budget = mort prématurée. Nécessite sim hors-moteur (gros chantier). |
| **B. Imitation Learning + RL fine-tune (AlphaStar-like)** | Très aligné avec l'existant (`ai-utility-trace` = data expert prête, `cheat.ts` = générateur AI vs AI). Plafond IL = AI scriptée (avec ses blind spots), fine-tune RL ensuite. **Approche privilégiée à ce stade.** |
| **C. PPO from scratch + obs tensor + action mask** | Baseline minimaliste, sert de validation infra et de policy prior. Aucune garantie de plafond. |
| **D. MuZero / Stochastic MuZero** | Modélise l'aléa, évite le sim moteur (modèle latent). Complexité R&D élevée pour solo. |

### Format de réponse attendu de chaque agent

1. **Recommandation principale** (1 approche, ou hybride explicite) + justification en 5-10 lignes
2. **Étapes concrètes ordonnées** : 4 à 8 étapes, chaque étape = output testable
3. **Risques principaux** (3 max) que la recommandation devrait adresser
4. **Désaccords éventuels** avec les approches A-D ci-dessus, argumentés
5. **Points sur lesquels tu veux explorer le code avant de répondre** : liste les fichiers que tu as réellement lus (la `Read` tool t'es ouverte en mode plan)

### Ce qu'on cherche

Pas une réponse de manuel. **Une décision actionnable cette semaine**, ancrée dans le code et les contraintes mesurées du repo, qui débloque la première itération de pipeline RL. Si tu vois un piège dans ce brief lui-même, dis-le explicitement.

---

*Fin du brief. Réponds sous forme structurée. Cite les fichiers que tu as lus.*
