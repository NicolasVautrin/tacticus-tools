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
| #202 | Kit d'Abraxas (`thousInfernalMaster`) : WeaverOfFate + InfernalPacts + MasterOfTheTutelaries | `[opus]` | `case-202` : **tranches A, B et C LIVRÉES** (C : execute 1096 + effet 1197 + triggered 1173 Screamer-par-attaque-Psychic-du-SET-bonus-inclus + chaîne InfernalPacts + playbook NC slots 0x49/0x52/0x6b/0x72 — probe 202c PASS A1-A4/B/C, garde 31337 100 %). Résidu principal : face DÉCISION portée mais non confrontée oracle (`case-202` §8) — au premier walk Thousand Sons. |
| #27 | Résidus `CalculateCustomUtility` : 4 sous-systèmes à porter (débloqueurs nommés) | `[opus]` | `case-27` : **2 portés** (ArmoriumCherub 1014, LightOfSanguinius 1177 — `loki_custom.py`, garde 31337 100%) + **20 résidus** classés par débloqueur (DSL-évaluateur / BattleQuery-token 0x44-0xb1 / multi-hit / utilité-déplacement / MoW off-board / `dp=False` / dead-code / sans-id). Reprise = porter un sous-système → débloque son groupe d'overlays (roadmap dans le doc). |
| #217 | P0 DÉCIDER≠EXÉCUTER : porter le combat des **27 actives `[-D]`** (décision portée, exécution NO-OP) | `[opus]` (Stormcaller `[fable]`) | `port-roadmap.md` §3 — commencer par P0-WALK (1113/1163/1151/1153/1191, castées dans le walk de garde 31337). |
| #20 | Port des kits par faction (ex-« Roadmap AdMec », généralisée à TOUTES les factions) | `[opus]` | `port-roadmap.md` §5 + `kit-coverage.md` (119 kits, 249 items ; piocher par faction, exceptions dures en §5.2). Audits régénérables : `audit_kit_coverage.py` / `audit_combat_ability_coverage.py`. |
| #5 | Chantier `DslContext` live-state | `[opus]` | Architecture à poser, pas d'énigme à trancher. |
| #17 | Surveillance des 2 résidus `move` | `[opus]` | Nature RNG, non actionnable — veille seulement. |
| #66-r | Retrofit des autres consommateurs de la base `ReviveEffect` (revive-en-place) | `[opus]` | `case-66-revive-in-place` §6 : la base + `ReviveUnitOperation` sont PORTEES/VALIDEES (TaintedNarthecium). Ne restent que FILTRE + vars + gate overkill/HealType par sous-classe, chacune EXIGE un carrier spawnable validable : **Narthecium** (ultraApothecary Imperial, `@180f5ae20/@180f5acf0`, non-Mechanical + **unless Overkilled** byte 0x738=0 + chance=100) ; **RitesOfMorkai/FuelledByFury** (spaceWolfPriest 1211, `@180f4ab10`/`@180f810c0/@180f81250`) ; **GhostRevive/TimeFlux** (thousTerminator, `@180f83600/@180f83800`) ; **PhoenixGem_CanReviveEffect** (`@180f5e680/@180f5e4a0`, ability `@181111610/@1811117b0`) ; **ReanimationBeam** (`@180f67b90/@180f67ac0`, carrier a identifier). NB : Narthecium = ajouter le gate `NOT ev.overkill` (contraste TaintedNarthecium). |

## Résidus documentés (pas encore des tâches)

Remontés par les cases closes ; à promouvoir seulement si un miss d'agreement les fait surface.

- **BlackRage décision : seuil `should_evaluate` hp<=50% vs `hpPct` per-level (30→50%)** (`case-217-
  blackrage`, candidat remonté par PR #12) : le playbook décision gate à 0.5 fixe alors que la RE combat
  montre un hpPct par niveau — correct seulement au niveau max. N'affecte pas le guard (Lucien caste à
  hp=1). À corriger si un walk à niveau intermédiaire l'exerce. `[opus]`.
- **Étage d'ARRONDI `Fix64.Round` du multiplicateur, non matérialisé quand la %-list est VIDE**
  (`case-death-nova-explodes-putridexplosion` §3.1) : `CalculateBaseDamageWithAllModifiers @18102d3f0`
  applique **inconditionnellement** `Fix64.Round(Mul(v, multiplier), AwayFromZero)` (slot 0x10 ->
  `CalculateBaseDamageWithModifiers @1810021c0`, `Round` @181002308) dès qu'un
  `Nullable<DamageModifiers>` HasValue ; le port ne le matérialise que dans `apply_capped_modifiers`
  **quand la %-list est non vide**, sinon le caller TRONQUE (`op_Explicit` @181564100). Divergence de
  ±1 quand le produit du perçage tombe juste sous un entier (MESURÉ live : base 200 -> natif 140 vs
  port 139 ; base 201 -> 141 vs 140). **Corrigé UNIQUEMENT pour la famille ABILITY amount-mode**
  (`apply_all_modifiers(..., round_materialize=True)` depuis la feuille `AttackWithAbilityDamage`).
  Reste à mesurer/généraliser : bornes d'attaque NORMALE (`damage_ops:177/179`), ability bounds-mode
  (`:353`), normal-like (`:472`), additional-hits — tous live-validés bit-exact AVEC la troncature,
  donc chacun exige sa propre campagne de datapoints discriminants. `[fable]`.
- **Garde `@0x180e76c9e` de `KillUnitOperation$$Execute` entre `On(1)` et `On(2)`**
  (`case-death-nova-explodes-putridexplosion` §2.1) : `On(PreUnitDeath=1)` est émis AVANT la garde,
  `On(2)`/`On(0)`/`On(55)`/`On(54)` DEDANS. Sémantique du lookup (`entities+0xa8` indexé par une clé du
  singleton de bataille) NON résolue -> savoir si un REVIVE déclenché sur `On(1)` court-circuite
  `On(2)`/`On(55)` reste OUVERT. Le port émet les trois inconditionnellement (== comportement déjà en
  place pour `On(55)`). À trancher avec **#66-r** (retrofit REVIVE). `[fable]`.
- **Migration du DoT de tuile `EnvFireTile` vers la route `AbilityDamageOperation`**
  (`case-death-nova-explodes-putridexplosion` §3) : `DSLFactory.AttackWithAbilityDamage @180de9e50`
  construit `AbilityDamageBehaviour` + `AttackBehaviour` -> `AbilityDamageOperation`, alors que le port
  du feu route encore sur `execute_direct` (perçage/armure SEULS : ni mods défenseur, ni block, ni
  bouclier, ni cap Resilient). Numériquement équivalent pour une source TUILE dans les mesures
  existantes, mais latent. `[opus]`.
- **Fork de port `PerformAIAttackFromCurrentPosition`** (`case-217-thequickening` §5, finding
  relecture au merge PR #11) : 2 mirrors du même nœud natif (`loki/summon.py` #202-C avec dispatch
  after-hit vs `quickening.py::_free_melee_attack` #217 sans) → unifier en une feuille unique
  contexte-aware (ForcedInMelee → domaine adjacent) + dispatch after-hit. `[opus]`. **PROMU
  sous-système P1 par la campagne T-RE `case-219` §7** : le nœud cousin `PerformAIAction` est le
  débloqueur commun de Waaagh (1058), SupremeCommander (1028), de l'act-again BlackRage (event
  0x16) et du refactor CultDemagogue — cf. `port-roadmap.md` §4.
- **Trait `Unstoppable` (1042), exemption movement-stop** (`case-205` — RE complet, verdict
  invalidable) : trait = membre de `NotBlockingMovementOfTraits @18155b370` {Mounted, Vehicle,
  Unstoppable} consommé par le WalkPathfinder pour les effets de tuile movement-ending
  (Fire/Ice/BlockEntering). À câbler **dans la tranche movement-stop #131/B4** quand le fondement
  (effets de tuile dans la reachability) sera porté — sinon code registered-but-dead. `[opus]`.
- **Push : arc arrière NON-dégénéré (pousseur non-adjacent)** (`case-push-distance` §5, #68 CLOS —
  distance 1 hex tranchée RE+live) : `FindTileToPush @180e695e0` sélectionne dans l'arc arrière
  distance-1 `GetMinimumTiles180Behind @181064f98` ; pour un pousseur **non axis-aligné** l'arc rend
  2-3 tuiles et le natif **random-pick** parmi les valides → la DIRECTION peut différer du straight-back
  du port. **Sans objet** pour `PushUnit(caster,target)` mêlée (pousseur toujours adjacent → arc = 1
  tuile straight-back déterministe). À porter (slice-21b) seulement si un push d'un pousseur
  non-adjacent (AoE/ranged) apparaît. `[opus]`.
- **Coups post-mortem / dérive du flux MT** (`case-67` §5) : le natif cesse d'émettre les coups
  après la mort de la cible, `_run_hits` continue de tirer → dérive du PRNG après un kill
  mi-attaque en sim multi-actions. `[fable]` si ça remonte (divergence cross-cutting, se localise mal).
- **Crit-roll NON tiré à cc=0 sur la voie ABILITY multi-hit → desync spread** (#220 VigilanceEternal,
  ROOT CAUSE MESURÉE) : pour une attaque d'ability à `crit_chance=0`, le natif tire quand même 1 crit-roll
  (`RollCritical` NextBool) PAR COUP en plus du spread (mesuré : 3-hit → **6 tirages** rng côté jeu, mti
  624→6), mais `_run_hits` @`operations/damage.py:585` `roll_critical(...) if crit_enabled` SKIP le crit-roll
  à cc=0 → le port ne tire que **3** (1 spread/coup). Les spreads du port consomment g1,g2,g3 au lieu de
  g1,g3,g5 → per-coup désaligné dès le coup 2 (VigilanceEternal port [762,829,716]=2307 vs live [763,716,802]
  =2281, ~1 %). CONTREDIT la note damage.py:463 (« cc=0 ⇒ 0 tirage, validé 18/18 » — validation probablement
  sur la voie NORMAL-attack ou single-hit). Fix = tirer le crit-roll (et/ou block-roll) même à 0-chance sur le
  chemin ABILITY multi-hit, avec re-validation croisée NORMAL-vs-ABILITY (decompile `RollCritical
  @181004fb0` / `ApplyRandomBlockDamage`) — n'affecte QUE le magnitude multi-coups cc=0, la structure DSL de
  1202 est live-exacte (gate dist==1, landing tile, mono-cible confirmés). `[fable]` (contredit une
  validation documentée + blast radius = toutes les attaques d'ability multi-hit cc=0).
- **Bouclier × limites sur la voie ability** (`case-67` §5) : le natif cape le reste POST-part-bouclier,
  le port cape avant le split. Identique tant que `shield = 0`. `[opus]`.
- **`Impervious` (28)` / cap boss `0x5d4`** (`case-67` §5) : no-op documentés, porteurs = boss non
  spawnables en runner → **invalidables**, non portés (doctrine `feedback_no_unvalidatable_ability_ports`).
- **FireOfAbsolution, volet feu-sur-cible** (`case-67` §5) : vecteur after-hit probabiliste non
  modélisé par `execute()`. `[opus]`.
- **Flag=1 des caps heal/repair** (`case-60` §5) : **chemin natif IDENTIFIÉ par #203** — `RepairBehaviourOptions.
  ForRegenerate @180fce8c0` (repair « NO-WAKE ») cape le montant au `get_group_unit_heal_limit @1810325e0`,
  contrairement à `ForRepair @180fce920` (WAKE, réveille des membres). LivingMetal = NO-WAKE (câblé, cf. case-203).
- **LivingMetal swarm « no-wake top-off » (INVALIDÉ live)** (`case-203` §5) : pour un swarm à HP **non-frontière**
  (membre partiel, ex. 700/2218) le port complète le membre vivant (mirror `get_group_unit_heal_limit`), mais le
  member-cap (#57d) maintient les swarms **toujours aux frontières** → chemin jamais atteint en combat normal
  (LivingMetal est de fait INERTE sur `necroSmnSwarm` : 10 % du maxHP < 1 membre). Revalider si un dégât Blast
  non-member-capé pose un membre partiel. `[opus]`.
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
- **LordOfTempests AddIce, résidus** (`case-35` §4 — case CLOS, les DEUX branches du trigger
  désormais confrontées live) : reste `load_state` sans hydratation des effets de TUILE
  mi-bataille (gap de HARNAIS, pas de port : en walk complet c'est notre trigger qui pose la
  glace) ; blocage mouvement / crit-bonus ICE toujours GATE (#131, terrain-effects §2). `[opus]`
  si un miss d'agreement les fait surface.
  *Fermés* : branche 2 (glace sur la victime du smite Psyker) — **exercée live** par
  `test_lord_of_tempests_addice_smite_branch` (géométrie placée : Njal d=2 de T, E2 voisin de T ;
  live glace {T, E2} == offline) ; `is_normal_attack` face attaquant et Stormcaller (1113)
  runner-face — **résolus par #217** (`case-217-stormcaller`).
- **`CalculateCustomUtility`, 20 overlays non portés** (`case-27` — 2 portés `loki_custom.py`) :
  bloqués par 4 sous-systèmes (évaluateur DSL de forme/chain ; méthodes `BattleQuery` à token
  0x44/0x77/0x7c/0x7d/0x7f/0xb1 ; réutilisation `GenerateMultiHitAttackPredictions` ; utilité de
  déplacement `UtilityMovementCase`/`GetTargetUtilityDiffOnDisplace`), ou par une limite de harnais
  (porteur MoW hors-plateau en arène : PlagueburstMortar/DaemonicOrdnance/Malleus), ou non-modélisation
  (`dp=False` : Chronometron/DevoutPush/ForwardObservers/HealingBalms), dead-code (ProperKilly/
  Repair_GalvanicField) ou sans id `ActiveAbilityType` (SavageEchoes). Chaque item nomme son débloqueur
  exact dans `case-27`. `[opus]` : porter UN sous-système débloque son groupe d'overlays. Biais visible
  seulement en concurrence serrée d'actions du porteur → promouvoir si un miss le fait surface.
