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
| — | **Substrat MULTI-HEX** (une unité occupant N tuiles) | `[opus]` | `case-mow-offboard-cast` §6 : MESURÉ — `DutyEternal` (1158) spawn `ultraSmnDreadnought` sur **3 hexes** (1 squad, 3 `UnitFoot`) ; le moteur offline modélise 1 `PositionComponent` par unité. Bloque `DutyEternal` (et probablement `AetherStride`). Chantier = N pieds par squad (occupation / adjacence / ciblage / blocage pathfinding). |
| — | **Stats résolues des MoW non captables** (spec `frida/hooks`) | `[opus]` | `case-mow-offboard-cast` §8 : `combatSnapshot.allUnits` **et** `statModSources.targetUnits` filtrent `ty === EntityType.Unit` → aucune stat de MoW lisible (elle a pourtant Attack/Crit*/ExtraHits/ExtraPierce*). Base = 0 (gameconfig) donc le seed offline est exact à l'init ; seule une **stat-mod posée en cours de combat sur la MoW** échapperait. Fix = élargir les deux filtres à `EntityType.Machine` (`GetStat` est déjà générique) → **exige rebuild+reinject**, à programmer quand l'atelier est vide. |
| — | **Face DÉCISION des MoW** (plans d'attaque) | `[opus]` | `case-mow-offboard-cast` §8 : le débloqueur MoW est côté COMBAT. `state_bridge._plans_for_unit` ne feede toujours pas l'attaque d'une MoW à `_best_attack` (`origin=None`) → c'est le blocage nommé par `case-27` pour les 3 overlays `CalculateCustomUtility` à porteur MoW (PlagueburstMortar / DaemonicOrdnance / Malleus). Mirrorer le chemin natif dédié (`aiPlaybookPredict` caster Machine, `case-172`), PAS faire passer une entité sans position pour une unité. |
| #17 | Surveillance des 2 résidus `move` | `[opus]` | Nature RNG, non actionnable — veille seulement. |
| #PAI-c | Consommateurs de `PerformAIAction` restants (socle LIVRÉ) : **Waaagh 1058**, **SendInTheNextWave 1016**, **Incursion 1021**, **Poxwalkers 1040**, + retrofit **CultDemagogue 1179** (`PerformAINeophyteTurn` bespoke → nœud générique, cycle flags manquant) | `[opus]` | `case-perform-ai-action` §7 (par consommateur : ce qui manque exactement). Waaagh site-2 déjà lu (`@18122c260`, `asGroup=1/reset=1`) → manque `UnitsWithVisualId` / `VisualUnitIdFromUnitId` / `Get`. |
| #PAI-k | `ListenUpMaggotsEffect` (0x426) + chaîne `SwornProtector`→spawn de Kell : SEULE source de `ActiveAbilityModificationsComponent` ; débloque le chemin NON-NUL de `GetAbilityStatModification` **et** la face DÉCISION `SupremeCommanderPlaybook` (gate « un enfant du caster existe ») | `[opus]` | `case-perform-ai-action` §5.1 + §6 (VAs : `@180f56590`/`@180f56740`, ability `@181221cc0`/`@181221d20` ; playbook `@181162890`/`@181162410`/`@181162720`). Tant que Kell n'est pas porté, porter le playbook = code enregistré-mais-mort. |
| #66-r2 | Les 2 derniers consommateurs de `DSLFactory.Revive` : **FuelledByFury** (`ultraTitus`) et **GhostRevive/TimeFlux** (`thousTerminator`) | `[opus]` | Retrofit #79 + fermeture #88/#89 LIVRÉS (`case-66-revive-in-place` §6-§7 : les 5 `ReviveEffect` + les 3 hypothèses fermées PAR LECTURE + la garde `KillUnitOperation`). Restent 2 chantiers PROPRES (arbres entièrement RE, cf. §8) : **FuelledByFury** — bloqué sur 3 points nommés, dont l'**émetteur de `On(PendingDeathAdded=3)` non localisé** (ancrage à hooker : `MatchState.AddDeath @181009f90`, xrefs DATA only) + le contexte `TriggeringAbilityIs(FinalJustice)` non threadé + la pose de l'effet 1324 ; **GhostRevive/TimeFlux** — exige un vecteur `On(PreUnitMove=31)`, un effet portant une TUILE (le ghost) et un revive **NON in-place** (`SetRevivePosition @180e936e0` paramétrée). Les DEUX carriers sont des heros DANS le pool ⇒ validables LIVE le jour du port. |

## Résidus documentés (pas encore des tâches)

Remontés par les cases closes ; à promouvoir seulement si un miss d'agreement les fait surface.

- **Ordre intra-groupe de `PerformAIAction(asGroup=1)`** (`case-perform-ai-action` §5.2, RE avancée
  par `case-95-waaagh-contributions` §6) : natif = argmax d'utilité du picker
  `IdunBattle.AI.OperationalDeciders.DefaultGroupOperator$$PickNextUnit` (slot 1 de `operator+0x28`,
  picker `operator+0x30`) ; port = ordre du sélecteur. Live observé : les 2 gardes de SupremeCommander
  agissent dans l'ORDRE INVERSE de leur spawn. **Ce qui est établi** :
  `IdunBattle.AI.OperationalDeciders.DefaultGroupOperator$$.ctor` construit le picker comme un tableau
  de 8 `IdunBattleLogic.AI.Utilities.UtilityBucket` — ids `0x4a`(poids Fix64 1) · `0x44`(1) · `0x45`(1)
  · `0x4c`(poids NUL, flag +0x18=1) · `0x4b` · `0x49` · `0x47` · `0x48` (poids nuls).
  **Ce qui manque** : la sémantique des 8 ids (aucun dump d'enum `UtilityBucket`) + le scoreur
  par-unité derrière le slot 1. Sans incidence tant que les unités du groupe sont interchangeables
  (Ork Boyz clones, gardes de Creed). `[opus]`.
- **`test_skitarii_turn_live::test_skitarii_played_by_generic_ai_pass` échoue au commit `9cf5e40`**
  (`BFS 3->3` : le Vanguard bouge mais ne se rapproche pas ; attaque ranged 3 hits pour 0 dégât).
  Reproduit sur base propre (patch stashé) → **pré-existant**, pas une régression. `[opus]`.

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
  port 139 ; base 201 -> 141 vs 140). **Corrigé pour TOUTE la famille ABILITY** — amount-mode
  (`AttackWithAbilityDamage`, mesure nova) **ET mode bornes** (#90 lot A : `execute_ability_attack`
  active `round_materialize` dès que `is_attack_damage_op=False`, car `CalculateAbilityDamage
  @18102cb50` construit TOUJOURS le `Nullable` défenseur slot 0xf → l'arrondi passe toujours pour ce
  vecteur ; MESURÉ live SquigLaunchas 1200, 4 seeds, écart variant dans [0, hits] = signature d'arrondi,
  4/4 bit-exact après fix — cf. `case-mow-targeting-predicates` §4).
  Reste à mesurer/généraliser : bornes d'attaque NORMALE (`damage_ops:177/179`), normal-like (`:472`),
  additional-hits — tous live-validés bit-exact AVEC la troncature (famille ATTACK), donc chacun exige
  sa propre campagne de datapoints discriminants. `[fable]`.
- ~~**`test_harvester_live::test_harvester_live_moved_bitexact_and_native_factory` (seeds 777 et
  31337)**~~ — **RÉSOLU (#101)**, avec `test_sentinel_directives_live` (même cause). Le fait « a bougé
  ce tour » avait **deux** représentations dans le port (le set `State.moved_this_turn` de #60, lu par
  le gate no-move ; le flag natif `UnitFlag.Moved` du `UnitFlagsComponent`, lu par
  `HarvesterOfSouls$$GetHits`) et **aucune** n'était posée par le move + lue par le gate → `+25%`
  HeavyWeapon fantôme sur tout état rechargé (`load_state`). Fix = **un seul store**, celui du natif
  (`set_moved_flag` / `unit_has_moved`). Détail + décomposition par étage + généralisation bit-exact
  dans les DEUX sens : `case-101-moved-flag`.
- **`HeavyGravCannon` (1291) non porté** (`case-220 §6.17`, chiffré par `case-101 §3.2`) :
  `HeavyGravCannonEffect$$CreateEffectDamageBonusForAttack` = `ForAddition(cond, ConfigVar(8=extraDmg))`
  + `...$$CreatePiercingBonusForAttack` = `ForPiercing(cond, ConfigVar(0x3f=extraPierceRatio))`, cond =
  `OwnerIsActor & IsRangedAttack & (HasTrait(target, 5=Mechanical) | 1013 MkXGravis | 1039
  TerminatorArmour)`. MESURÉ live : `+443` flat (Sy-Gex -> necroOverlord Mechanical, seed 777) — seul
  confond restant de `test_sentinel_directives_live` (qui asserte donc `live >= offline`). `[opus]`.
- **`UnitFlag.ArrivedAtFinalTile` (1) non posé par `MoveUnitOperation`** (`case-101 §6`) : le natif
  l'ajoute juste après `SetMovedFlag` (gaté par l'option `MoveUnitOptions` @+0x0). Aucun consommateur
  porté n'en dépend aujourd'hui ; à câbler avec le reste des `MoveUnitOptions`. `[opus]`.
- **Les `UnitFlags` ne sont exposés par AUCUN RPC** (`case-101 §6`) : un état rechargé par `load_state`
  ne peut pas savoir qu'une unité a bougé / a fini son tour ; seules les fixtures qui *pilotent* le
  déplacement re-posent le flag. Point d'ancrage natif à capter dans `combatSnapshot` :
  `IdunBattle.Entities.Components.UnitFlagsComponent` (`OrderedSet<int>` @+0x10) par unité. `[opus]`.
- ~~**Garde `@0x180e76c9e` de `KillUnitOperation$$Execute` entre `On(1)` et `On(2)`**~~ — **RÉSOLU
  (#88/#89, 2026-07-25)**. Le lookup n'est pas un dictionnaire mais le `hasValue` du
  **`Nullable<ReviveData>` @`UnitComponent + 0xa8`** (même champ que celui qu'écrit
  `ReviveBehaviour.Execute @180fd1230` et que lit+purge `ReviveUnitOperation.Execute @180e91bd0`).
  ⇒ **un REVIVE posé sur `On(1)` COURT-CIRCUITE `On(2)`, `On(0)`, `On(55)`, `On(54)`** (+ flags de mort,
  `RemoveEffects`, `RegisterDefeatedUnit`). Le port applique la garde (`kill_unit_revive_gate`), validée
  live par `test_revive_cancels_death_events_live.py`. Détail : `case-66-revive-in-place` §7.
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
  0x51 = `GetFreeAdjacentTiles @181061650`, cap par `visualId` live ; **#38c** : seuil natif mesuré
  point par point, « morts inclus » et branche `free==0` confrontées live, garde committée
  `tests/engine/test_doctrina_gate_cap_live.py`) : reste la branche `IsActive` de
  `ReachedSummonCap @181070f60` non mirrorée (aucun caller connu avec une active) ; approx identité
  offline (2 Marshals même camp poolent leurs comptes — configuration de harnais uniquement ; summon
  `RemoveUnit`-ed — pas seulement mort — sortirait d'obs_units, aucun chemin connu). `[opus]` si un
  miss les fait surface.
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
  (porteur MoW hors-plateau en arène : PlagueburstMortar/DaemonicOrdnance/Malleus — **face DÉCISION
  toujours bloquée** ; le débloqueur `case-mow-offboard-cast` ne lève que la face COMBAT), ou non-modélisation
  (`dp=False` : Chronometron/DevoutPush/ForwardObservers/HealingBalms), dead-code (ProperKilly/
  Repair_GalvanicField) ou sans id `ActiveAbilityType` (SavageEchoes). Chaque item nomme son débloqueur
  exact dans `case-27`. `[opus]` : porter UN sous-système débloque son groupe d'overlays. Biais visible
  seulement en concurrence serrée d'actions du porteur → promouvoir si un miss le fait surface.
- **Canal de coups des abilities, résidus** (`case-61-ability-hits-channel` §6 — canal COMBAT LIVRÉ,
  base géométrique de `FrenziedFiring` LIVRÉE) : (a) **volet AoE de `FrenziedFiring`** — le playbook natif
  émet un 2e batch sur `FrenziedFiringAbility$$GetTargets` (ennemis adjacents à la cible, `hits = 1`
  littéral) que le port n'émet pas, axe `get_aoe_targets` ; (b) **`On(PreAttack=5)` absent du vecteur
  ability** (fidèle : le natif l'émet depuis `ALoki_NormalAttackAbility$$ExecuteNormalAttack`) → sur ce
  vecteur `LetTheGalaxyBurn` ne s'arme que par `TargetHasTileEffect`, jamais par le flag persistant 33 % ;
  (c) **per-coup non bit-exact contre `templChampion`** (même nb de coups, dégât différent — axe DÉGÂT,
  effets `MartialSuperiority`/`RapidAssault_ExtraDamage` de la cible ; le témoin `necroWarden` est
  bit-exact). `[opus]`, à promouvoir si un miss d'agreement les fait surface.
- **Constantes de gameplay FIGÉES dans les tests, sans oracle** (#96, inventaire — 3 tests corrigés :
  `test_summon_trait_effects_live` Diminutive + ShadowInTheWarp, `test_lightcover_gate_live`). Le patron
  reste présent dans **~35 assertions sur ~18 fichiers** de `tests/engine/runner/` : un scalaire écrit en
  dur alors que le jeu le porte dans une clé de config re-équilibrable — le message d'assertion NOMME
  souvent la clé, ce qui rend le tri mécanique. Familles vues au scan
  (`assert … == <litt> … (nrOfHits|pierce|chance|Pct|range|config)`) : `nrOfHits`/`nrOfHits_2`
  (cord_claw, flail_swing, great_frost_axe, fragstorm, jakhal_stimms, martial_apotheosis, plasma_cannon,
  savage_echoes, sanctorum_missile, sentinel_directives, stikkbomb, summon_ability_ports, harvester,
  harbinger, destroyer_hive) ; `PiercingRatio` de profil (40 Power, 55 HeavyRound, 30 Energy, 100
  DirectDamage, 1 Physical, 10 Las) ; constantes globales (`getStuckInChance == 30`,
  `firstAidRecovery == 35`, `parryHitReduction` via `base_cfg - 1` dans
  `test_ability_hits_channel_live`) ; plage figée `30 <= hpPct <= 50` (hypersensory).

  **LE CRITÈRE EST BINAIRE — quel oracle pour cette assertion ?**
  - la valeur est **CALCULÉE** (le moteur la dérive par une formule : coups appliqués après
    réductions, dégât résolu) → **l'oracle est le LIVE**. On interroge le moteur natif et on
    confronte le port à SA réponse. Figer un nombre ici, c'est geler le résultat de la formule
    qu'on prétend valider ;
  - la valeur est **BRUTE** (constante de config lue telle quelle : `nrOfHits` d'une ability, ratio
    de profil, variable de trait) → **l'oracle est la CONFIG** :
    `gameconfig.ability(id).constants/variables`, `gameconfig.trait(t).variables`,
    `gameconfig.global_value(k)`, profils de dégât.

  Le **décompilé sert à TRANCHER** entre les deux (valeur prise telle quelle dans un `ConfigConst`
  = brute ; formule = calculée) — pas à produire de la docstring. Deux pièges, un par branche :
  côté **brut**, vérifier qu'on lit LA BONNE clé (des clés voisines partagent slot *et* valeur —
  `parryHitReduction` / `camouflageHitReduction_1` / `diminutiveHitReduction` valent 1 et occupent
  0x2c ; le moyen simple est de décaler la clé et d'exiger que le port suive) ; côté **calculé**,
  vérifier que le setup DISCRIMINE (un plancher natif peut absorber la valeur — `min=Direct(1)`
  saturait sur 3 coups et rendait un test incapable d'échouer).

  **À NE PAS confondre** avec les invariants STRUCTURELS (`len(spawned) == 1`, `distance == 1`,
  `hp == 0`) : ils décrivent une forme, pas un réglage, et restent légitimement littéraux. Test
  d'appartenance : « un patch d'équilibrage peut-il changer ce nombre ? »

  `[opus]`, par lots de quelques fichiers — l'exécution live domine le coût, pas l'édition.
- **Nature du coup, résidus** (`case-106-ismeleeattack-fork` §7 — fork CLOS, `execute_normal_like`
  threade désormais la nature et le prédicat a un foyer unique) : (a) **le mode `AttackRangeType.Both`
  (3) n'est pas modélisé** — le port déclare la nature (`is_melee` du behaviour) là où
  `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` la calcule par `AreUnitsInMelee(attPos, tgtPos)`
  pour ce mode ; les deux coïncident sur tout ce qui a été mesuré (coups hors-mêlée), un coup `Both`
  résolu AU CONTACT ferait diverger ; (b) **famille ABILITY d'`execute_ability_attack`** — la mesure
  #45f dit que `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` reçoit des modifiers
  ATTAQUANT **vides** ; le port ne les vide pas, il se contente de ne pas threader la nature, donc les
  bonus SANS gate de nature (`DecoysAndMisdirection`, `RapidAssault`) y passent encore. `[opus]`.
- **`WaaaghAbility` (1058) : face COMBAT inerte dans le runner isolé** (`case-106` §7, mesuré session 78) :
  `applyAction ability` sur le Warboss rend `ok:true, mutated:false, events:[group 12 Waaagh, finish]` et
  ne pose AUCUN des 3 buffs (1099/1100/1101) — ni sur le caster, ni sur l'allié adjacent — y compris au
  tour suivant sans déplacement préalable et en ciblant une tuile. Bloque toute confrontation live des
  contributions Waaagh (#95) et le contre-cas mêlée-only de `case-106`. Cause non élucidée. `[opus]`,
  à traiter avec `#PAI-c` (Waaagh est déjà son 1er consommateur nommé).
