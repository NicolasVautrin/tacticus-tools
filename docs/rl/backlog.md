# Backlog moteur RL — tâches ouvertes

> **Pourquoi ce fichier** : le tracker de tâches (outils `TaskCreate`/`TaskList`/…) vit côté
> compte, pas en local — il a disparu de la session le 2026-07-22 et rien n'en subsistait sur
> disque (aucun serveur MCP « task » déclaré dans les 4 portées de config, aucune base sous
> `~/.claude`). Ce fichier est le remplaçant **versionné** : il ne dépend d'aucune connexion.
> Les tâches TERMINÉES ne sont pas listées ici — elles ont leur `docs/rl/case-<n>-*.md`.

## Convention de tag modèle

Chaque tâche porte le modèle avec lequel la mener :

- **`[fable]`** — le cas a **déjà résisté** (divergence non localisée, verdicts contradictoires,
  flip-flop), le décompilé est **ambigu** (wrappers virtual-only, structure à trancher), ou il faut
  **concevoir des datapoints live discriminants**. En pratique : délégation à `fable-solver`
  (worktree isolé, livraison par PR).
- **`[opus]`** — l'artefact natif est **identifié** et la mécanique comprise (port 1:1, slice DSL,
  câblage d'un canal), **volume mécanique** (N overrides du même patron), ou orchestration /
  validation live / régression / doc / commit.

Tag mixte quand la tâche a deux temps (trancher la structure, puis porter) — l'annoter.

## Tâches ouvertes

| # | Tâche | Modèle | Point d'entrée |
|---|---|---|---|
| #202 | Kit d'Abraxas (`thousInfernalMaster`) : WeaverOfFate + InfernalPacts + MasterOfTheTutelaries | `[opus]` | `case-202` : **tranches A (WeaverOfFate) et B (aura InfernalPacts) LIVRÉES** (A : 98e0fbd ; B : effet bi-canal Average/RandomAmount + face COMBAT du canal #179 créée — prédiction 10/10, comptes 6/5/3, garde 100 %). Reste C (MasterOfTheTutelaries : summon cascade + décision NC). **EN COURS (orchestrateur).** |
| #203 | Trait `LivingMetal` : régen Necron (`LivingMetalRepair` 0x3f2) — 51 unités (6 lineup), face COMBAT (+ résidu NetherRealmCasket 1456) | `[opus]` | **DÉLÉGUÉ opus-solver (2026-07-23, en vol)** — livraison par PR. Points de départ : effet 1456 @180f5b650 (case-34), revives swarm observés (case-60). |
| #27 | Résidus `CalculateCustomUtility` : 4 sous-systèmes à porter (débloqueurs nommés) | `[opus]` | `case-27` : **2 portés** (ArmoriumCherub 1014, LightOfSanguinius 1177 — `loki_custom.py`, garde 31337 100%) + **20 résidus** classés par débloqueur (DSL-évaluateur / BattleQuery-token 0x44-0xb1 / multi-hit / utilité-déplacement / MoW off-board / `dp=False` / dead-code / sans-id). Reprise = porter un sous-système → débloque son groupe d'overlays (roadmap dans le doc). |
| #5 | Chantier `DslContext` live-state | `[opus]` | Architecture à poser, pas d'énigme à trancher. |
| #20 | Roadmap AdMec | `[opus]` | Planification + découpage en tranches de port. |
| #17 | Surveillance des 2 résidus `move` | `[opus]` | Nature RNG, non actionnable — veille seulement. |

## Résidus documentés (pas encore des tâches)

Remontés par les cases closes ; à promouvoir seulement si un miss d'agreement les fait surface.

- **Coups post-mortem / dérive du flux MT** (`case-67` §5) : le natif cesse d'émettre les coups
  après la mort de la cible, `_run_hits` continue de tirer → dérive du PRNG après un kill
  mi-attaque en sim multi-actions. `[fable]` si ça remonte (divergence cross-cutting, se localise mal).
- **Bouclier × limites sur la voie ability** (`case-67` §5) : le natif cape le reste POST-part-bouclier,
  le port cape avant le split. Identique tant que `shield = 0`. `[opus]`.
- **`Impervious` (28)` / cap boss `0x5d4`** (`case-67` §5) : no-op documentés, porteurs = boss non
  spawnables en runner → **invalidables**, non portés (doctrine `feedback_no_unvalidatable_ability_ports`).
- **FireOfAbsolution, volet feu-sur-cible** (`case-67` §5) : vecteur after-hit probabiliste non
  modélisé par `execute()`. `[opus]`.
- **Flag=1 des caps heal/repair** (`case-60` §5) : aucun chemin natif identifié à ce jour ; la
  plomberie `group_limit` est en place, gatée OFF. `[opus]` si une ability « ne peut pas réveiller » apparaît.
- **MV71 (1076), résidus** (`case-61bis` §6/§8/§9 — case CLOS, tranches 1-3 livrées) : mods
  attaquant-effets présumés droppés dans la prédiction drone (widget zéroé — aucun datapoint
  caster-buffé) ; datapoint `ExtraHits>0` (délégué m860) jamais mesuré ; LoS non portée dans
  PickTile (boards à obstacles) ; retrait Markerlight au heal/repair non porté. `[opus]` si un miss
  d'agreement les fait surface.
- **Per-player 1180, résidus** (`case-31` §A refermé par PR #4, mergée — « Non couvert ») : mécanisme
  du saut d'incrément `turnsStarted` sur la cible d'un 1202 (mesuré, non RE'd — port immunisé via
  lecture live) ; miss s20 u77/`1140` (hors périmètre historique) ; dash-off `to=None` de 1180.
  `[opus]` si un miss les fait surface.
- **ReachedSummonCap, résidus** (`case-38` §4 — port livré ; #38b RÉSOLU par PR #5 mergée : slot
  0x51 = `GetFreeAdjacentTiles @181061650`, cap par `visualId` live) : branche `IsActive`
  de `ReachedSummonCap @181070f60` non mirrorée (aucun caller connu avec une active) ; approx
  identité offline (2 Marshals même camp poolent leurs comptes ; summon `RemoveUnit`-ed sort
  d'obs_units → sous-compte) ; branche `free==0` (Tan encerclé → emit inconditionnel) confirmée
  au désassemblage mais non craftée live (surround AI-gated) — risque = un MISS rare, jamais un
  overfire. `[opus]` si un miss les fait surface.
- **LordOfTempests AddIce, résidus** (`case-35` §4 — case CLOS) : branche 2 (glace sur la victime
  du smite Psyker) non exercée live (câblée + unit-testée) ; `is_normal_attack` face attaquant
  toujours True au foyer combat (snowball s'appliquerait aux abilities de Njal — inerte,
  Stormcaller non porté) ; `load_state` sans hydratation des effets de TUILE mi-bataille ;
  Stormcaller (1113) runner-face non porté (zone `GetAddIceTiles @18120cf70` + 3× AoE + stun
  Flying) ; blocage mouvement / crit-bonus ICE toujours GATE (#131, terrain-effects §2). `[opus]`
  si un miss d'agreement les fait surface.
- **`CalculateCustomUtility`, 20 overlays non portés** (`case-27` — 2 portés `loki_custom.py`) :
  bloqués par 4 sous-systèmes (évaluateur DSL de forme/chain ; méthodes `BattleQuery` à token
  0x44/0x77/0x7c/0x7d/0x7f/0xb1 ; réutilisation `GenerateMultiHitAttackPredictions` ; utilité de
  déplacement `UtilityMovementCase`/`GetTargetUtilityDiffOnDisplace`), ou par une limite de harnais
  (porteur MoW hors-plateau en arène : PlagueburstMortar/DaemonicOrdnance/Malleus), ou non-modélisation
  (`dp=False` : Chronometron/DevoutPush/ForwardObservers/HealingBalms), dead-code (ProperKilly/
  Repair_GalvanicField) ou sans id `ActiveAbilityType` (SavageEchoes). Chaque item nomme son débloqueur
  exact dans `case-27`. `[opus]` : porter UN sous-système débloque son groupe d'overlays. Biais visible
  seulement en concurrence serrée d'actions du porteur → promouvoir si un miss le fait surface.
