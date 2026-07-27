# Backlog moteur RL — tâches ouvertes

> **Pourquoi ce fichier** : le tracker de tâches (outils `TaskCreate`/`TaskList`/…) vit côté
> compte, pas en local — il a disparu de la session le 2026-07-22 et rien n'en subsistait sur
> disque (aucun serveur MCP « task » déclaré dans les 4 portées de config, aucune base sous
> `~/.claude`). Ce fichier est le remplaçant **versionné** : il ne dépend d'aucune connexion.
> Les tâches TERMINÉES ne sont pas listées ici — elles ont leur `docs/rl/case-<n>-*.md`.
>
> ⚠ **Ce fichier décrit des INTENTIONS HORODATÉES, pas l'état du code.** Avant de dispatcher sur
> une entrée, la confronter au commit courant. L'état confronté au 2026-07-26 (commit `7f47c29`) —
> avec les comptes re-dérivés, les verdicts de confrontabilité et la liste des entrées PÉRIMÉES —
> vit dans **`docs/rl/port-residuals-inventory.md`**.

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
| #116-r | **AdaptiveStrategy (1005, `necroWarden`)** — reste du lot 1 Necrons | `[opus]`+prérequis | `case-116-necrons-lot1` §4 : RE COMPLÈTE (arbre + légalité + mapping du ctor `AddStatOverrideEffectBehaviour`). Prérequis restants : (1) **`RelentlessMarch` 1004** (passif `necroWarden`, `…RelentlessMarchAbility$$CreateBehaviour`) — sans lui la branche `If(ActorHasTriggeredAbility) TriggerAbility(…)` est un no-op structurel ; (3) nœuds `TriggerAbility` + `ActorHasTriggeredAbility`. ~~(2) sous-système OVERRIDE-ATTAQUE~~ **LEVÉ** : `AddStatOverrideEffect` existe (`abilities/behaviours/stats.py`), 2 users runner (#112 ExemplarOfHate `71dca97`, #114 InspiredToGreatness `d67b6ac`). `PerformAIAction` est déjà là. |
| #116-e | **Magnitude de `Chronometron_ExtraDamage` (1550)** — l'effet est posé mais INERTE | `[opus]` | `case-116-necrons-lot1` §2 : `…Chronometron_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` = `ForAddition(OwnerIsTarget & IsUnit(att) & AreFriends(att, EffectSource), If(IsMechanical(att), ConfigVar(9), ConfigVar(8)) × TimesEffectApplied)`. Manque, dans `attacker_ctx` du hook DÉFENSEUR (prédiction ET runner) : équipe de l'attaquant vs équipe de la SOURCE de l'effet, trait `Mechanical` de l'attaquant, compteur `TimesEffectApplied` par instance. Consommateur additionnel : `$$CreateRemoveEffectTrigger` = `On(9)` (effet CONSOMMÉ au 1er coup allié). |
| ~~#116-d~~ | ~~Séquencage RNG de `ChainLeftOverHitsAttackDamage` après un KILL~~ | **LIVRÉ (#125)** | `case-125-rng-wasted-hits` : ce n'était PAS un écart de flux `state.rng` (natif ET port roulent TOUS leurs coups — `AttackDamageOperation$$ExecuteHits` = `while (i < hits)` sans sortie sur la mort), c'était le **report** `GetLeftOverHits`, figé à `1 + extraHit` par #116 alors qu'il vaut `max(0, H - k - 1) + extraHit`. Corrigé + gardé (`test_chain_leftover_hits_live.py`, 2 seeds, contre-cas intégré). |
| #202 | Kit d'Abraxas (`thousInfernalMaster`) : WeaverOfFate + InfernalPacts + MasterOfTheTutelaries | `[opus]` | `case-202` : **tranches A, B et C LIVRÉES** (C : execute 1096 + effet 1197 + triggered 1173 Screamer-par-attaque-Psychic-du-SET-bonus-inclus + chaîne InfernalPacts + playbook NC slots 0x49/0x52/0x6b/0x72 — probe 202c PASS A1-A4/B/C, garde 31337 100 %). Résidu principal : face DÉCISION portée mais non confrontée oracle (`case-202` §8) — au premier walk Thousand Sons. |
| #27 | Résidus `CalculateCustomUtility` : 4 sous-systèmes à porter (débloqueurs nommés) | `[opus]` | `case-27` : ~~2 portés~~ **6 portés au 2026-07-26** (1014 ArmoriumCherub, 1177 LightOfSanguinius, + 1020 HeraldOfTheApocalypse, 1029 Drachnyen, 1100 SorcerousFacade, 1199 DoomSiren — `playbook.REGISTRY` = 7 avec `Repair`) + ~~20~~ **16 résidus** classés par débloqueur (DSL-évaluateur / BattleQuery-token 0x44-0xb1 / multi-hit / utilité-déplacement / `dp=False` / dead-code / sans-id). ⚠ deux débloqueurs cités par `case-27` sont PÉRIMÉS : « MoW off-board » (levé côté COMBAT, `a9714a4`) et « porteur hors pool » (levé, `ab98129` catalog_inject) — le blocage MoW restant est la face DÉCISION seule. Les 4 overlays portés ont créé 4 nouveaux `[-D]` (décision portée, combat NO-OP). |
| #217 | P0 DÉCIDER≠EXÉCUTER : porter le combat des actives `[-D]` (décision portée, exécution NO-OP) — ~~27~~ **20 au 2026-07-26, dont 18 à porteur confrontable** | `[opus]` (Stormcaller `[fable]`) | **Liste à jour + symboles + confrontabilité : `port-residuals-inventory.md` §2.** (`port-roadmap.md` §3 est PÉRIMÉ : 1113/1163/1151 sont portées ; restent 1153/1191 du sous-groupe P0-WALK.) ⚠ `audit_kit_coverage.py` SOUS-COMPTE ce gisement (2 registres de décision lus sur 3) — cf. inventaire §2 et R23. |
| #20 | Port des kits par faction (ex-« Roadmap AdMec », généralisée à TOUTES les factions) | `[opus]` | `port-roadmap.md` §5 + `kit-coverage.md` (119 kits, 249 items ; piocher par faction, exceptions dures en §5.2). Audits régénérables : `audit_kit_coverage.py` / `audit_combat_ability_coverage.py`. |
| #5 | Chantier `DslContext` live-state | `[opus]` | Architecture à poser, pas d'énigme à trancher. |
| — | **Substrat MULTI-HEX** (une unité occupant N tuiles) | `[opus]` | `case-mow-offboard-cast` §6 : MESURÉ — `DutyEternal` (1158) spawn `ultraSmnDreadnought` sur **3 hexes** (1 squad, 3 `UnitFoot`) ; le moteur offline modélise 1 `PositionComponent` par unité. Bloque `DutyEternal` (et probablement `AetherStride`). Chantier = N pieds par squad (occupation / adjacence / ciblage / blocage pathfinding). |
| — | **Stats résolues des MoW non captables** (spec `frida/hooks`) | `[opus]` | `case-mow-offboard-cast` §8 : `combatSnapshot.allUnits` **et** `statModSources.targetUnits` filtrent `ty === EntityType.Unit` → aucune stat de MoW lisible (elle a pourtant Attack/Crit*/ExtraHits/ExtraPierce*). Base = 0 (gameconfig) donc le seed offline est exact à l'init ; seule une **stat-mod posée en cours de combat sur la MoW** échapperait. Fix = élargir les deux filtres à `EntityType.Machine` (`GetStat` est déjà générique) → **exige rebuild+reinject**, à programmer quand l'atelier est vide. |
| ~~R14~~ | ~~**Face DÉCISION des MoW** (plans d'attaque **ET** générateur NonComparable)~~ | **LIVRÉ (2026-07-27)** | `case-r14-mow-decision.md`. Le chemin natif dédié est `IdunBattle.AI.Tactics.DefaultMachineTactic` (routé par `AiQuery$$GetUnitTacticForUnit` sur `IsMachine`), PAS `aiPlaybookPredict` : **pas de `MovementActionGenerator`**, caster à `UnitPosition.NullPosition`, tuiles candidates VIDES (branche `Count == 0` d'`ActiveAbilityActionGenerator.<GenerateActions>d__7`), émission par `DefaultMachineTactic$$GenerateInputMessagesFromUnitAction`. Reachability PROUVÉE : `DefaultGroupOperator$$CalculateNextActionForPlayer` ajoute `PlayerComponent+0x78` (l'id de machine) aux entités du joueur. Porté : `DefaultMachineTactic` + `context.build_machine` + routage dans `engine_decide` + le gate `ActiveAbility$$get_CanCurrentlyBeUsed` (cooldown **et** MUNITIONS — les 8 MoW ont une ability à `munitionsCost=1` `hasAmmo:false` au seed BC). Sweep 8/8 MoW sans violation ; coïncidence mesurée sur 1187. **Aucune origine inventée, aucune MoW dans `dv.units`.** |
| ~~#221~~ | ~~**`Daemon_ExtraBlock` (1034) inerte côté COMBAT** — 1 tirage RNG manquant par attaque contre TOUTE unité Daemon~~ | **LIVRÉ (2026-07-27)** | `case-221-daemon-extrablock-rng.md`. `AttackDamageOperation._block_sources` thread l'`Attack` COURANTE du défenseur (`ctx.attack` = `GetStat(ATTACK, Current)` = le `StatAmount(Self@0x148, 0, 0)` de `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonAbility$$GetBlockDamage`). Deux mirrors complétés dans la foulée, même fonction native `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances` : le failed-id est le **`BEntityId`** de la source (0 pour l'entrée par défaut de `MultiValueStatComponent$$GetAllValues`, l'entité-effet sinon), pas la chance ; et la liste est **triée décroissant par amount** (`<>c.<CalculateBlockChances>b__15_0` = `b.blockDamage - a.blockDamage`). Validé live sur les DEUX vecteurs (ability `probe_brazier_daemon_offset.py`, normale `probe_221_daemon_normal_attack.py`), gardes `test_daemon_extra_block_live.py` + `test_block_chances_order_offline.py`, et le bridage `compare_hits=1` de `test_brazier_of_holy_fire_live.py` est levé (4 coups confrontés). |
| ~~—~~ | ~~**`OnToxicDamageAbility` (1203) non porté** — 1 tirage RNG manquant par CIBLE d'une attaque de profil `Toxic`~~ | **LIVRÉ (2026-07-27)** | `case-1203-on-toxic-damage.md`. Porté en arbre DSL (`triggers/loki/on_toxic_damage.py`) : `If(IsFirstHitInSeries() & Maybe(ConfigConst(1203, ·, 0x2a = chance)), AddEffect(0x4dc Contaminated, Tiles(target), source = la TUILE))`, `chance = 25` lue en config (`globalValues.toxicDamageContaminationChance`, ancrée sur la constante BC). Câblé sur les DEUX vecteurs d'attaque (normale + ability), UN `next_bool` par série de coups — le ET natif COURT-CIRCUITE, donc le `Maybe` n'est évalué qu'au coup d'index 0. Effet mesuré : la confrontation per-coup de `test_rad_bombardment_live` n'est plus bornée à la 1re cible (le retard d'un tirage a disparu) ; contre-épreuve `probe_1203_toxic_contamination.py` (canal armé 1/1 vs désarmé 0/1 face au live). **Deuxième moitié du même étage RNG que #221** : les deux canaux ont été re-confrontés ensemble après rebase. |
| #17 | Surveillance des 2 résidus `move` | `[opus]` | Nature RNG, non actionnable — veille seulement. |
| ~~#PAI-c~~ | ~~Consommateurs de `PerformAIAction` restants : Waaagh 1058, SendInTheNextWave 1016, Incursion 1021, Poxwalkers 1040, + retrofit CultDemagogue 1179~~ | **LIVRÉ (`3f7b9d1`, 2026-07-25)** | « #94 consommateurs SPAWN/AI-CONTROL ». Les 5 ids sont dans `ABILITY_CLASSES` (`WaaaghAbility`, `SendInTheNextWaveAbility`, `IncursionAbility`, `SpawnPoxwalkersAbility`, `CultDemagogueAbility`). Résidu restant, DISTINCT : l'ORDRE intra-groupe de `PerformAIAction(asGroup=1)` (plus bas dans ce fichier). |
| ~~#PAI-k~~ | ~~`ListenUpMaggotsEffect` (0x426) + chaîne `SwornProtector`→spawn de Kell~~ | **LIVRÉ** | Chaîne portée + confrontée live de bout en bout (`case-perform-ai-action` §5.1 + §6 réécrits). Ground truth : Kell apparaît vivant porteur de l'effet 0x426, le cast 1028 spawne **3** gardes (2 sans Kell) et son rayon `PerformAIAction` vaut **3** (2 sans Kell). La face DÉCISION `SupremeCommanderPlaybook` est portée dans la foulée (gate `IsFriendlyKell` désormais atteignable). |
| ~~#119~~ | ~~Face DÉCISION de `SupremeCommanderPlaybook` (1028) jamais confrontée à l'IA native~~ | **LIVRÉ** | `case-perform-ai-action` §6 (réécrit). Le gate (2) lisait `u["parentId"]`, clé qu'AUCUN RPC ne publie → `should_evaluate` constamment `False` = playbook enregistré-mais-mort ; **désaccord mesuré** (le natif caste, le port attaque). Corrigé par la reconstruction offline `_kit_spawn_visual_ids` ; ACCORD sur 5 états craftés (dont le discriminant « deux Creed, un seul Kell adverse ») + 2 couples board/seed. Étage (3) RE-corrigé : `chance = 1/2 + hp%(caster)/2` (stat 5 = Health), déterministe à PV pleins (20/20), mesuré 31/40 à 32 % de PV. Garde : `tests/engine/test_supreme_commander_decision_live.py`. |
| #66-r2 | Les 2 derniers consommateurs de `DSLFactory.Revive` : **FuelledByFury** (`ultraTitus`) et **GhostRevive/TimeFlux** (`thousTerminator`) | `[opus]` | Retrofit #79 + fermeture #88/#89 LIVRÉS (`case-66-revive-in-place` §6-§7 : les 5 `ReviveEffect` + les 3 hypothèses fermées PAR LECTURE + la garde `KillUnitOperation`). Restent 2 chantiers PROPRES (arbres entièrement RE, cf. §8) : **FuelledByFury** — bloqué sur 3 points nommés, dont l'**émetteur de `On(PendingDeathAdded=3)` non localisé** (ancrage à hooker : `MatchState.AddDeath @181009f90`, xrefs DATA only) + le contexte `TriggeringAbilityIs(FinalJustice)` non threadé + la pose de l'effet 1324 ; **GhostRevive/TimeFlux** — exige un vecteur `On(PreUnitMove=31)`, un effet portant une TUILE (le ghost) et un revive **NON in-place** (`SetRevivePosition @180e936e0` paramétrée). Les DEUX carriers sont des heros DANS le pool ⇒ validables LIVE le jour du port. |

## Résidus documentés (pas encore des tâches)

Remontés par les cases closes ; à promouvoir seulement si un miss d'agreement les fait surface.

- **Le tier `get_Priority` n'est encore *observable* sur aucun porteur** (`case-170-get-priority` §6).
  22 abilities ont un tier ≠ 0 (`engine.playbook.noncomparable.NATIVE_PRIORITY`), 3 sont portées
  (NovaBoost 1192 = 1000, ThriceBlessedConflagration 1187 = 100, NovaShield 1194 = -1000), mais
  **aucune unité ne porte deux NonComparable PORTÉES de tiers différents** — l'ordre inter-tier
  n'est donc gardé que par un test à playbooks stub, pas par un agrément live. Le débloqueur est
  nommé : porter **`DevastatingRefrain` 1188** (NonComparable, tier 0 mesuré), la seconde active de
  `adeptExorcist` qui porte déjà 1187 au tier 100 — le couple devient alors le scénario d'agrément
  naturel du tier (à cible disponible pour les deux, le natif doit émettre 1187 quelle que soit
  l'utilité de 1188). Les 19 autres abilities de la table ne sont pas portées. `[opus]`.

- **Le VERDICT du `Maybe` de `LetTheGalaxyBurn` diverge natif/port** (`case-61` §6, mesuré par
  `probe_61d_frenzy_aoe_combat.py`). Depuis que `On(PreAttack=5)` est émis sur le vecteur ability, le
  *tirage* est consommé des DEUX côtés — l'alignement `state.rng` est préservé — mais le prédicat ne
  rend pas toujours le même booléen : mesuré K=1, natif **6** coups sur la cible (non armé) vs port
  **7** (armé), **les 6 premiers coups restant bit-exacts**. Ce n'est donc pas un décalage de flux
  mais un écart de **seuil** : port `LetTheGalaxyBurnArmAbility.matches` →
  `state.rng.next_internal(0, 100) < LetTheGalaxyBurnChancePct` vs natif
  `IdunBattleLogic.Entities.DSLFactory$$Maybe` → `IdunBattle.Entities.Behaviours.MaybeBehaviour$$Execute`
  (bornes / comparaison / générateur à LIRE). Impact : ±1 coup par attaque pour les 5 porteurs
  `LetTheGalaxyBurn` (Black Legion) ; `test_ability_hits_channel_live.py` borne l'écart à 1. `[opus]`.

- **Conso RNG du canal #179 non bit-exacte sur le vecteur ability** (`case-61` §4ter ; le résidu
  `case-202` §7 « à confirmer live » est désormais CHIFFRÉ). Sur un cast de `FrenziedFiring` (caster
  `blackObliterator`, porteur permanent d'un effet du cycle `FleshmetalGuns`), les coups d'ARME sont
  bit-exacts (K=0, 2 seeds) mais les 2 coups additionnels du canal #179 diffèrent en valeur : port
  `[2735, 2553]` vs natif `[2481, 2754]`. Comme ces coups s'exécutent **après** chaque attaque, tout
  ce qui suit la première attaque est désaligné (2ᵉ, 3ᵉ… cible d'un volet AoE). Pistes à trancher
  au décompilé : l'ordre relatif de
  `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType` vs
  `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` (le port place le canal AVANT
  les after-hit), et le nombre de tirages par coup additionnel. `[opus]`.

- **Les vecteurs COMBAT autres que l'attaque normale TRONQUENT encore leurs bornes réduites**
  (`case-131-normal-attack-bounds-materialization` §5, remonté par le fix #131). Les cellules
  min/max d'un coup viennent de `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` (slot 4
  `…$$PredictAttack`, caché), dont le dernier étage
  (`IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers`) **arrondit**
  (`Fix64$$Round`, AwayFromZero) dès qu'un `Nullable<DamageModifiers>` HasValue. #131 a corrigé
  `damage_ops.execute::_reduced_bounds` (mesuré live : arrondi 6/6 puis 17/18 coups, troncature 1/6
  puis 0/18). **Restent tronquants**, sur le MÊME chemin natif : `execute_ability_attack::_reduce`
  quand `is_attack_damage_op=True` (famille ATTACK `DSLFactory$$AttackWithAttackDamage` ; la famille
  ABILITY arrondit déjà depuis #90), `execute_normal_like` (splash Psyker), `additional_hits`
  (#179/#202-B). Chacun exige son propre montage discriminant — `probe_131_normal_attack_bounds.py
  --phase scan` énumère les régimes où floor ≠ round (28 sur 6 bases × 10 ratios : c'est fréquent).
  Deux sous-résidus du même fork, LUS mais non mesurés : le **plancher 1** de
  `CalculateBaseDamageWithModifiers` (`0 < v < 1 → Fix64.One`, jumeau du `MinMaxDamageFix64$$MathMax`
  porté côté prédiction sous #170) absent du combat, et le fait que `_reduced_bounds` reste une
  **re-implémentation partielle** de `PredictAttackRaw` (extraMax, split bouclier per-coup, cap PV,
  trait-limits traités ailleurs) — dé-forker réellement les deux faces est un chantier à part. `[opus]`.

- **La tuile d'ORIGINE est dans les candidats d'ability du port, pas dans ceux du natif** — remonté
  et CHIFFRÉ par `case-128-tile-elevation-utility` §5 (RE + live). `ABaseAiUnitTactic$$
  GenerateActionTiles` = `IBattleQuery.slot+0xe` (tuiles de MOUVEMENT, `GetMovableTilesFor` **exclut**
  la tuile courante) ; `ActiveAbilityActionGenerator.<GenerateActions>d__7` ne tire la branche
  `NullPosition` (= sur place) **que si la liste est vide**. Notre hook, lui, ajoute EXPRÈS l'origine
  à `attackPlans.ranked`, et `_best_attack` la consomme sans filtre `movable`. Mesure S3 (`C4_02`,
  `emperNoiseMarine`) : natif `69 tgt=77 to=(3,3)` = **exactement** l'argmax du port une fois le seul
  candidat « origine » retiré (39.961) ; le port rend `69 tgt=79 to=(2,2)` (41.886). ⚠ tranche à part
  entière : le changement touche TOUTE unité qui attaquerait sans bouger → exige une passe d'agreement
  complète (`test_playbook_live` + batch multi-seed), pas un smoke. `[opus]`.

- **Arbitrage Comparable `ExcruciatingFrequencies` (1197) vs attaque NORMALE — RÉSIDU RÉDUIT**
  (`case-128-tile-elevation-utility` §6, qui a clos l'hypothèse « terme d'élévation » de
  `case-124` §7). Le terme `Tile(7)`/`Elevation` est un **mirror exact** (gate `get_IgnoreTileUtility`
  = `xor al,al ; ret`, `MakeFinalTilePrediction` = identité, membership 29 feuilles lue dans la carte
  de composition `UtilitiesDatabase+0x58`, BC `{Multiplier 10, Highest 10, Lowest -5}`) et le natif le
  paie (mesure S3). L'étage dégât est **bit-exact** 18/18. Reste : sur l'état où 1197 est disponible,
  natif = `1197@(4,1)` (port 27.977) contre `69@(3,3)` (port 37.05, origine déjà retirée) → il
  faudrait `u(1197) > 17.05` soit 2.1× la valeur du port. Seul étage non lu ligne à ligne :
  `Bucket<T>.Merge` / `ChooseAction` (arbre `SortedList<Key, sous-Bucket>` + admission
  `FUN_18004cc80(bucket, action)` appelée dans `EvaluateInternal`). `[fable]`.

- ~~**DIRECTION du beam `DarkTalonStrike` côté DÉCISION**~~ — **LIVRÉ (#126, merge `bf89224`)**.
  `_beam_count` modélisait `best` par le prolongement du rayon `caster -> aim` ; le natif le CHOISIT
  parmi les 6 `AdjacentTiles(target@0x178)` via `SortByFormula(AngleBetweenLines, ASC)` puis
  `SortByFormula(Count(Units(GetTilesInLine)), DESC)` + `First(1)` (tris STABLES → clé primaire =
  #ennemis alignés). Le port avait promu le **tie-break en règle** : l'angle 0 *est* le prolongement,
  donc les deux coïncidaient tant qu'aucune direction d'angle non nul n'alignait plus d'ennemis.
  Détail : `case-126-beam-direction`.

- **Stat-mods EAGER (`applied_stat_mods`) présents AU SEED : appliqués mais non revertables**
  (`case-118-seeded-statmod-revert` §5). Le volet DÉCLARATIF (`get_stat_modification_stat/amount`)
  est fermé — clé unique par instance (`effect_stat_mod_key`) lue par les trois consommateurs du
  retrait. Reste la famille EAGER : `ActOfFaith_Effect` (1017), `ProtectorImperative` /
  `ConquerorImperative` (1247/1248). Leur magnitude se calcule depuis le `StatsComponent.ctx` du
  porteur, or l'attribution du seed est calculée **avant** que le `UnitStats` n'existe
  (`UnitContext.from_snapshot` : `attributed` précède `seed_unit_stats`) — et ActOfFaith lit
  justement `StatPart.INITIAL` du crit-damage : dépendance circulaire à démêler. Symptôme : un stack
  seedé retiré offline (reset ActOfFaith au crit, toggle Doctrina) ne re-baisse pas la stat.
  Débloqueur alternatif, plus fidèle : exposer `StatModificationComponent` (+0x10 StatType /
  +0x14 montant) de l'entité-effet dans `frida/hooks/game/effects.ts` → plus aucune magnitude
  re-dérivée offline. **Exige rebuild + reinject.** `[opus]`.

- **`ChildComponent.ParentId` non publié par les RPC** (`case-perform-ai-action` §6.2, mesuré #119) :
  ni `projectUnitsFull` (decisionView), ni `observeBattle`, ni `combatSnapshot` n'émettent le lien
  enfant→parent (`BEntityId` @+0x10, offset confirmé live). Conséquence : tout gate natif de la forme
  « u est un enfant de X » doit être reconstruit depuis la config (`_kit_spawn_visual_ids`), exact tant
  qu'une équipe ne porte pas deux summoners du même summon. **Fix** = ajouter `parentId` à
  `projectUnitsFull` (le port a déjà la clé, `engine/entities/selectors.py::Parent`) — **exige
  rebuild+reinject** : même fenêtre « atelier vide » que le résidu `StatModificationComponent`
  ci-dessus et que « stats des MoW non captables ». `[opus]`.

- **Résidus de `PickRandomly` après #130** (`case-130-pick-randomly-rng.md`). La **loi de
  consommation** est close : le sélecteur tire `min(len(pool), amount)` fois, bornes décroissantes,
  **même quand le pool tient dans `amount`** (`_pick_randomly_n` mirror 1:1 ; comptage direct des
  `genrand_int32` sur deux régimes, port bit-exact live sur PlasmaCannon). Le **helper frère `n = 1`**
  suit désormais la même loi : ses six appelants ont été démêlés un par un au décompilé (case-130 §4),
  les deux `PickRandomly(., 1)` (ScarabSummon, MasterOfTheTutelaries) passés à `_pick_randomly_one`, les
  quatre `First(…)` laissés sur un helper distinct ; mesuré live sur le splash Psyker, trois régimes,
  trois configurations seed/board. Restent :
  - **Ordre d'énumération du pool quand `len(pool) > amount`** : le natif tire dans l'ordre du sélecteur
    source (ECS, non trié), le port id-trie → **QUI** est piqué peut différer (Fragstorm, PlasmaCannon
    >2 derrière, BringerOfDespair >1 adjacent, Harbinger, Supercharge, SquigMine). `[opus]`.
  - **Fragstorm tire des HEXES, pas des occupants** : `PickRandomly(AdjacentTiles(target) −
    Tiles(Friends(caster)), 4)` inclut les tuiles VIDES (coup gaspillé) → le CARDINAL du pool diffère,
    donc le nombre de tirages aussi. Exige de porter le sélecteur en tuiles. `[opus]`.
  - **`AddForcedTargetsAndUpdateCandidates` non porté** : `ignoreForcedTargets` (`+0x38`) est FAUX pour
    toutes les factories `PickRandomly` → le natif pré-remplit le résultat avec
    `IdunBattle.Entities.UnitExtensions$$GetOnlyTargets(caster)` (non vide sous contrainte de ciblage
    type Taunt) et les retire des candidats, ce qui **réduit le nombre de tirages**. `[opus]`.
  - ~~Le TRI natif des quatre sites de placement `First(…)`~~ — **FAIT (case-130 SS5)** : les quatre
    nœuds sont portés (`SortByDistance`, `SortTilesByUtilityForSummon`, `Randomize` + `SortByFormula`,
    `First`), le tirage parasite retiré, l'ordre SOURCE natif (`boardGraph.neighbours`) branché ;
    comptage ET tuile mesurés live (9/9 tuiles, comptage exact hors résidus nommés). Ce qui reste,
    plus étroit :
    - **`MaybeTrigger` non porté** (`IdunBattle.Entities.Triggers.MaybeTrigger$$ShouldTrigger` =
      `rng.NextBool(chance)` quand `ANonDeterministicAbilityTrigger$$CanUseRandom`, donc **1 tirage**) :
      le bloc PileIn de `operations/triggers/dispatch.py` traite `Maybe(…)` comme DÉTERMINISTE. Tant
      qu'il manque, le comptage live de PileIn n'est pas confrontable (le tirage manquant précède le
      placement). Touche tout gate `Maybe`/`chance` du DSL. `[opus]`.
    - **Feuilles `Tile(7)` gatées sur l'unité, dans le tri de placement** : le sélecteur `unit` du
      `UtilityMovementCase` construit par `DSLFactory$$SortTilesByUtilityForSummon` n'est pas
      identifiable au décompilé (ctor replié par le linker), donc le port n'alimente que les feuilles
      PURE-TUILE. Aucun scénario mesuré ne réveille les autres — à rouvrir sur un cas où l'une décide.
    - **`Swamp -> Thorns_DefenseReduction` (−25) porté en local** (`spawn.py::_PLACEMENT_TERRAIN_EFFECTS`)
      au lieu de `utilities/tile.py::TERRAIN_TILE_EFFECTS` : la table partagée alimente aussi le
      contexte de DÉGÂT (`runner/damage_model.py::tile_effects_context`) et le scoring de MOUVEMENT.
      Unifier exige de valider ces deux fronts. `[opus]`.
    - **On-appearance `PerformAIAttackFromCurrentPosition` du grot SquigHound non portée** : écart
      CONSTANT de 4 `genrand_int32` mesuré sur ce vecteur (MC1_67/777 et C2_37/31337), étranger au
      placement. `[opus]`.
- **Resolve slot-8 non matérialisé dans `execute_normal_like`** (`operations/damage_ops.py` →
  `damage_hits.py::HitDamage.get_damage`, MESURÉ par `probe_130_pick_randomly_one_rng.py`) :
  `get_damage` court-circuite à `min == max` et ne tire rien, alors que
  `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` appelle `Next(v, v+1)`
  **sans gate largeur-1** — le port ne matérialise ce resolve que dans la branche ability bounds-mode
  (`is_attack_damage_op`, cf. le commentaire de `_run_hits`). GROUND TRUTH : sur le splash Psyker
  (montant plat `PercentageOf(StatAmount(Attack), psykerExtraDmg)`, bornes dégénérées), le live consomme
  **1 `genrand_int32` de plus que le port par volet splash** — constant, mesuré sur les régimes pool=1 et
  pool=2, absent quand le splash ne fire pas. Invisible sur le dégât du coup lui-même (montant plat) mais
  **désynchronise tout ce qui consomme après**. Touche tout vecteur `StatAmount`/`PercentageOf` routé par
  `execute_normal_like`. Attention : le porter inconditionnellement casserait les vecteurs
  `AbilityDamageOperation` (Stormcaller 3-hit bit-exact SANS resolve, cf. `probe_217`) — la condition est
  la FAMILLE de factory native, pas la largeur des bornes. `[opus]`.
- **Résidus NEUFS engendrés par la vague du 2026-07-26 (#67b / #224 / #127 / EnvFireTile)** — nommés
  dans les case docs, absents d'ici jusque-là. Détail, porteurs et fichiers :
  `port-residuals-inventory.md` §4 (N1-N6).
  - **N1** ciblage d'`ArcaneShield` sur un allié NON-Chaos (écart port/natif, `case-67` §6.5) `[opus]` ;
  - **N2** famille ATTACK en **bounds-mode** : cap SCALAIRE vs cap sur les CELLULES — le fix #67b est
    gaté sur `is_attack_damage_op`, cette face n'a pas été confrontée (`case-67` §6.5) `[opus]` ;
  - **N3** ordre réduction × bouclier sur `execute_normal_like` — indiscernable à `spread_pct = 0`,
    donc jamais mesuré (`case-67` §6.5) `[opus]` ;
  - **N4** le STADE natif du refus `TerminatorArmour`/`Pinned` n'est pas identifié : `PinnedEffect`
    n'override PAS `EntityIsImmuneToEffect` et la base ne teste que le trait `Immune`, qu'aucune unité
    ne porte → **collapse assumé** par #224 (`case-224-effect-immunity-gate` §5). `[fable]` ;
  - **N5** chaîne `&` derrière un `AddEffect` REFUSÉ : quand la pose est abandonnée par le gate
    d'immunité, la suite de l'`op_and` s'exécute-t-elle ? Confond non éliminé (`case-224` §5) `[opus]` ;
  - **N6** `test_hailstrike_phase2_live` **rouge** — échec PRÉ-EXISTANT vérifié par stash, signalé
    INDÉPENDAMMENT par `7c412b8` et `ad5692e` (donc pas un artefact de branche). `[opus]`.
- **(RÉSOLU #224) Gate d'IMMUNITÉ d'effet** — canal déclaratif (`BaseEffect.can_be_immune_to` +
  `entity_is_immune_to_effect`, surcharges `PinnedEffect`/`ContaminatedEffect`), résolution d'effet-DEF
  (`EffectFactory.effect_def`, mirror `EffectsDatabase.Get`), gate au stade natif exact dans
  `AddEffectOperation.execute`, et migration du portage EN DUR de Contaminated. Validé live sur les
  DEUX branches. Détail, inventaire des 7 classes `CanBeImmuneTo` et résidus :
  `docs/rl/case-224-effect-immunity-gate.md`.
  - **RÉSIDU `[fable]`** : le STADE natif par lequel `TerminatorArmour` fait ÉCHOUER la pose de
    `Pinned` n'est pas identifié — `PinnedEffect` n'override PAS `EntityIsImmuneToEffect` (vtable
    runtime), la base ne teste que `UnitTrait.Immune` (qu'aucune unité du roster ne porte) et le seul
    artefact qui nomme le couple est `PinnedEffect$$CreateActiveCondition = Not(HasTrait(0x40f))` — or
    une ActiveCondition désactive, elle n'empêche pas la pose, alors que la mesure montre un REFUS
    (aucun groupe `AddEffect`). Le port COLLAPSE l'ActiveCondition dans le gate. Point d'ancrage pour
    trancher : hook sur la valeur de retour du slot 40 d'`IEffect` dans `AddEffectOperation$$Execute`,
    ou sur `BaseUnitComponent$$HasTrait` (arg + résultat). Cf. case-224 §4/§5.1.
  - **RÉSIDU `[opus]`** : chaîne `&` derrière un `AddEffect` REFUSÉ — live, la branche Chaos entière
    d'`ExemplarOfHate` tombe avec le `Pinned` refusé (`mutated=False`), le port la poursuit. CONFOND
    non éliminé (élection d'attaquant DarkAngels à portée non forçable sur ce board). Cf. case-224 §5.2.
- **`decisionView.effects` cache les effets INACTIFS** (`frida/hooks/game/effects.ts`,
  `readEffectsByUnit` : `if (!info.active || info.removed) continue`) : impossible de confirmer live
  qu'un `AddEffect` a réellement posé un effet dont l'`ActiveCondition` n'est pas encore satisfaite —
  l'absence dans `decisionView` est ambiguë (non-posé vs posé-inactif). Rencontré sur
  `CalibaniteGreatsword` (effets 0x591/0x3f1 du toggle Strike). Fix = exposer
  `EffectComponent.IsActive @+0x5c` dans la charge utile (exige rebuild + reinject → à programmer
  quand l'atelier est vide). `[opus]`.
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
- **`test_skitarii_turn_live::test_skitarii_played_by_generic_ai_pass` échoue** — **RE-REPRODUIT au
  commit `7f47c29` (2026-07-26, 1 failed / 2 passed)** : `res={'moved': (6,5), 'kind': 'ability',
  'ability': 17, 'target': 79}`, `d_bfs 3->3`, `hp 8536->8536`, `atk(ranged=True, hits=3)`. Deux
  anomalies dans la MÊME trace : le move ne réduit pas la distance BFS, **et** 3 coups infligent 0
  dégât. Indice non exploité : `ability: 17` est le `NormalAttack` ABSTRAIT alors que l'attaque
  normale est un `ActiveAbilityType` CONCRET par unité (`NormalAttackType` @0x28). Pré-existant, pas
  une régression. `[opus]`.

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
- ~~**`HeavyGravCannon` (1291) non porté**~~ — **RÉSOLU (2026-07-26)**. `HeavyGravCannonEffect`
  (`entities/effects/loki/extra_damage.py`) porte les DEUX canaux (`ForAddition(cond,
  ConfigVar(8=extraDmg))` + `ForPiercing(cond, ConfigVar(0x3f=extraPierceRatio))`, `cond` = la MÊME
  `...$$DamageCondition` pour les deux). Prérequis levé au passage : `execute_ability_attack` ne
  threadait pas `target_traits` — tout bonus attaquant target-conditionnel était mort sur la voie
  ability. `test_sentinel_directives_live` asserte désormais l'**égalité bit-exacte** (off == live ==
  3510, l'ancien `+443`) ; le canal perçage, inerte face à `necroOverlord` (armure 1909, la branche
  `d − armure` du plancher domine), est confronté sur une cible à armure haute par
  `test_heavy_grav_cannon_live` (4 hypothèses : deux canaux / flat seul / perçage seul / aucun).
- **`execute_normal_like` ne threade pas `target_traits`** (jumeau du prérequis levé pour
  `execute_ability_attack`, 2026-07-26) : la voie `StatAmount`/`PercentageOf` (splash Psyker, montants
  mono-valeur) passe encore `target_traits=None` à `attacker_modifiers` → `BeastSlayer_ExtraDmg`,
  `MartialKatah_DmgBonus`, `CondemnorStake_ExtraDmg` et `HeavyGravCannon` y restent muets. Le natif n'a
  qu'UN collecteur (`IdunBattle.Entities.Effects.BaseEffect$$DamageBonusForAttack`), donc c'est bien un
  gap ; non corrigé faute de mesure live sur CE vecteur (aucun porteur de ces effets n'a d'attaque
  `normal_like` confrontée). Même remarque pour `additional_hits`. `[opus]`.
- **Matérialisation finale : `execute_normal_like` et `additional_hits` restent TRONQUANTS**
  (`apply_all_modifiers`, résidu nommé). Le 3ᵉ larron de la liste, `execute_ability_attack` famille
  ATTACK, a été **basculé sur `Round(AwayFromZero)`** le 2026-07-26 sur mesure (`probe_hgc_1291
  --case round`, 14 casts / 2 régimes d'armure : live == arrondi 14/14, == troncature 12/14, les 2
  écarts tombant exactement sur les tirages à partie fractionnaire ≥ .5 → réfute l'hypothèse « additif
  oublié »). Les deux autres vecteurs attendent la même campagne : le régime discriminant exige que les
  DEUX %-list soient vides ET que la branche perçage du plancher l'emporte (armure haute + perçage
  élevé). `[opus]`.
- **`rl_duel build --hp-target` remet le `FixedArmor` des a-units à 0** (mesuré 2026-07-26,
  `probe_hgc_1291 --case band` : `adeptMorvenn` 2411 → 0 et `necroWarden` 2008 → 0, seule variable entre
  les deux runs). **VÉRIFIÉ 2026-07-26 : c'est VOULU côté code** (`rl_duel.py`, branche `hp_target` :
  « PV bas ET armure nulle → un allié one-shot pour un kill DÉTERMINISTE ») — le résidu réel est
  DOCUMENTAIRE : `runner.md` présente `--hp-target` comme « force `Health` ET `RemainingHealth` », sans
  mentionner `Armor`/`FixedArmor = 0`. Piège de mesure : tout test qui force les PV pour garantir la
  survie de la cible supprime SILENCIEUSEMENT l'étage armure — donc aussi tout régime où la branche
  perçage du plancher pourrait mordre. Fix = 1 ligne dans `runner.md`. `[opus]`.
- **`tests/conftest.py` écrit ses state-files dans `data/`** (`STATE_PREFIX = ROOT/"data"/
  "_pytest_duel_state"`) alors que `data/` est VERSIONNÉ depuis le 2026-07-26 (`data/` = ce qu'on LIT,
  `logs/` = ce qu'on ÉCRIT). Les fichiers sont unlinkés au teardown, donc invisibles la plupart du
  temps — mais une passe interrompue les laisse dans `git status`. Contournement en attendant :
  `TACTICUS_PYTEST_STATE_PREFIX=<worktree>/logs/runners/...`. `[opus]` (une ligne).
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
- ~~**Migration du DoT de tuile `EnvFireTile` vers la route `AbilityDamageOperation`**~~ — **RÉSOLU
  (2026-07-26)**, cf. `case-envfire-tile-ability-route.md`. Le résidu n'était PAS latent : la route
  `execute_direct` ignorait les mods défenseur (tick natif sur `darkaTerminator` **25000** vs 100000
  portés, 4× trop) et l'étage limites (tick natif sur `astraYarrick` Resilient = **hp−1**, l'unité
  survit à 1 PV là où le port la **tuait**). Deux bugs de la slice-19 fermés au passage : le caster
  **tuile** laissait `entities.caster = None` → le DoT de tuile était un **no-op silencieux** ; et
  `StatAmount(x, HEALTH, Maximum)` rendait la PV **courante** (`HEALTH` est une stat *fill-up*, à
  router sur le `HealthComponent` comme `NUMBER_OF_MEMBERS`). **Reste ouvert** : généraliser
  l'arrondi `AwayFromZero` aux autres vecteurs COMBAT (chantier séparé, cf. ci-dessous) — et le
  demi-entier du DoT de tuile n'a pas pu être exercé live (`--hp-target` force l'armure à 0).
- ~~**Fork de port `PerformAIAttackFromCurrentPosition`**~~ — **RÉSOLU (2026-07-26)**. Il n'existe
  plus qu'**UN** corps du nœud (`abilities/loki/summon.py::perform_ai_attack_from_current_position`) ;
  la feuille DSL `PerformAIAttack` et `quickening.py::_free_melee_attack` y délèguent. Le décompilé a
  tranché les deux différences : (a) le dispatch after-hit est **inconditionnel** (aucun champ du
  `PerformAIAbilityUnitBehaviour` ne le gate — l'IA exécute une vraie ability d'attaque), les deux
  mirrors sans after-hit étaient donc FAUX ; (b) le domaine adjacent de TheQuickening **n'est pas un
  choix de code** mais `TargetingQuery$$GetRange` qui fait `Math.Min(1, range)` si l'unité porte
  `ForcedInMelee (0x529)` — le port pose désormais réellement l'effet. Détail : `case-217-thequickening`
  §5. RESTE OUVERT (distinct) : le nœud cousin `PerformAIAction` — débloqueur commun de Waaagh (1058),
  SupremeCommander (1028), act-again BlackRage (event 0x16), refactor CultDemagogue, cf.
  `port-roadmap.md` §4.
- **Nœud `DSLFactory$$PerformAIAttack(unit, …, amountNode, …)` : un corps câblé à la main subsiste**
  (finding du de-fork ci-dessus). Ce nœud est le MÊME `PerformAIAbilityUnitBehaviour` que
  `PerformAIAttackFromCurrentPosition`, à un seul champ près : `+0x78` (l'option `Nullable<int>` de
  l'appel IA) y est **fourni par l'appelant** au lieu d'être épinglé à `factory+0xb8 = Direct(0)` — c'est
  le budget de déplacement, d'où « FromCurrentPosition » = 0. ForwardSpotter (1143) passe déjà par la
  feuille commune, mais **`SpawnReplica` (ScarabSummon 1047, on-appearance `PerformAIAttack(1)`)
  ré-implémente `_nearest_enemy` + `AttackDamageOperation.execute` à la main, SANS gate de portée ni
  dispatch after-hit** (`behaviours/summon.py`). À rabattre sur le corps unique une fois la sémantique
  du budget de déplacement portée (aujourd'hui aucun étage du port ne fait bouger un summon avant son
  attaque, donc l'amount est inerte — mais le gate et l'after-hit manquent). `[opus]`.
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
- ~~**Bouclier × limites sur la voie ability**~~ — **LIVRÉ (#67b)** : `case-67` §6. `CalculateAbilityDamage`
  retire `min(dmg, shield)` **avant** modificateurs ET limites, puis le ré-additionne → ce que le bouclier
  absorbe échappe aux caps. Porté sous le gate `is_attack_damage_op == False` (la famille ATTACK, dont les
  caps portent sur les cellules en amont de `CalculateDamageOperation`, garde l'ordre inverse). Confronté
  live sur les 3 régimes (`shield = 0` bit-exact, `shield ≥ dmg`, `0 < shield < dmg`) —
  `test_shield_ability_limits_live.py`, `probe_67b_shield_ability_limits.py`.
- **`Impervious` (28)` / cap boss `0x5d4`** (`case-67` §5) : no-op documentés, porteurs = boss non
  spawnables en runner → **invalidables**, non portés (doctrine `feedback_no_unvalidatable_ability_ports`).
- ~~**FireOfAbsolution, volet feu-sur-cible**~~ — **PÉRIMÉ (`ac1144f`, 2026-07-17 ; fix friendly-fire
  `8b34e7f`)**. L'arbre DSL complet est porté (`operations/triggers/loki/fire.py::
  fire_of_absolution_tree` = `Inform & splash 3x Flame & Foreach(AdjacentTiles(Target()),
  Maybe(30 %, SetOnFire(Fire)))`, mirror de `IdunBattleLogic.Entities.Abilities.Active.Loki.
  FireOfAbsolutionAbility$$CreateBehaviour`) et dispatché par
  `triggers/dispatch.py::_fire_of_absolution_after_attack` sur `On(AttackInAtomicGroup)`.
  Résidu SUBSISTANT et distinct (flaggé dans le port) : le **timing RNG** du passif vs les coups
  primaires.
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
  désormais confrontées live) : l'hydratation des effets de TUILE mi-bataille est **RÉSOLUE**
  (`case-102-tile-effect-seeding`, `load_state(..., tiles=tileMeta)` — le test snowball consomme le
  vecteur au lieu de re-poser la glace à la main, bit-exact) ; blocage mouvement / crit-bonus ICE
  toujours GATE (#131, terrain-effects §2). `[opus]` si un miss d'agreement les fait surface.
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
  base géométrique de `FrenziedFiring` LIVRÉE, **volet AoE de `FrenziedFiring` LIVRÉ** : 2e batch
  `FrenziedFiringAbility$$GetTargets` à `hits = 1` littéral, bit-exact live sur 0/1/2/3 voisins
  ennemis, cf. §4bis) : (b) **`On(PreAttack=5)` absent du vecteur
  ability** (fidèle : le natif l'émet depuis `ALoki_NormalAttackAbility$$ExecuteNormalAttack`) → sur ce
  vecteur `LetTheGalaxyBurn` ne s'arme que par `TargetHasTileEffect`, jamais par le flag persistant 33 % ;
  (c) **per-coup non bit-exact contre `templChampion`** (même nb de coups, dégât différent — axe DÉGÂT,
  effets `MartialSuperiority`/`RapidAssault_ExtraDamage` de la cible ; le témoin `necroWarden` est
  bit-exact) ; (d) **flag `Moved` absent de la face PRÉDICTION** (résidu `case-101` §6 re-mesuré sur
  1036 : ×1,25 uniforme `HeavyWeapon_ExtraDmg` sur tout caster ranged déjà déplacé — débloqueur =
  exposer `UnitFlagsComponent` dans `combatSnapshot`). `[opus]`, à promouvoir si un miss d'agreement
  les fait surface.
- **Constantes de gameplay FIGÉES dans les tests, sans oracle** (#96, inventaire — corrigés à ce jour :
  `test_summon_trait_effects_live` Diminutive + ShadowInTheWarp, `test_lightcover_gate_live` ; **LOT A
  `nrOfHits`/`nrOfHits_2` LIVRÉ** : `test_cord_claw_live`, `test_flail_swing_live`,
  `test_great_frost_axe_live`, `test_fragstorm_migration_live`, `test_jakhal_stimms_live` ; **LOTS B, C
  et D LIVRÉS** : `test_martial_apotheosis_live`, `test_plasma_cannon_live`, `test_savage_echoes_live`,
  `test_sanctorum_missile_live`, `test_sentinel_directives_live`, `test_stikkbomb_migration_live`,
  `test_summon_ability_ports_live`, `test_harvester_live`, `test_harbinger_of_destruction_live`,
  `test_destroyer_hive_live` — détaillés plus bas). Le patron reste présent dans les fichiers
  ci-dessous : un scalaire écrit en
  dur alors que le jeu le porte dans une clé de config re-équilibrable — le message d'assertion NOMME
  souvent la clé, ce qui rend le tri mécanique.

  Familles restantes (scan `assert … == <litt> … (nrOfHits|pierce|chance|Pct|range|config)`) :
  la famille `nrOfHits`/`nrOfHits_2` de l'inventaire d'origine (15 fichiers) est **CLOSE** par les lots
  A/B/C ; la famille `PiercingRatio` de profil, les constantes globales (`getStuckInChance`,
  `firstAidRecovery`), `parryHitReduction` et la plage `hpPct` sont **CLOSES** par le lot D.
  RESTENT : **un résidu HORS inventaire** trouvé au scan post-lot-C —
  `test_damage_crushingclaws_live` (`main["hits"] == 2` = `nrOfHits` de CrushingClaws) ; et deux
  résidus NOMMÉS par le lot A dans ses propres fichiers : `nrOfTargets` du `PickRandomly`
  Fragstorm (= `GetNumberConstant(cfg, 0x11)`, cap 4 écrit en dur) et `hpPct` du self-loss JakhalStimms
  (25 % écrit en dur dans `exp_loss`).
  La famille `PiercingRatio`, les constantes globales et la plage `hpPct` sont CLOSES (lot D).

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

  **LOT B LIVRÉ** (`martial_apotheosis`, `plasma_cannon` (+ `plasma_cannon_lateral` : RAS, aucun scalaire),
  `savage_echoes`, `sanctorum_missile`, `sentinel_directives`) : tous les `nrOfHits`/`nrOfHits_2` + les
  `PiercingRatio` (Energy 30, Physical 1) + `healthPct` (SavageEchoes) + `range` (SentinelDirectives)
  dérivent maintenant de `gameconfig`. Le décompilé tranche BRUT : `GetNumberConstant`/`ConfigConst(0x2f)`
  partent DIRECTEMENT en argument de `DSLFactory$$AttackWithAttackDamage` (aucune formule) et
  `AbilityConfiguration$$GetNumberConstant` = `GetStringConstant` + `Int32.Parse`. **Trou de
  discrimination trouvé et fermé** : `test_sentinel_directives_live` ne comptait JAMAIS les coups live —
  décaler `nrOfHits` (1→2) ne le faisait pas rougir ; une assertion `len(live_ph) == nrOfHits` a été
  ajoutée. **Résidus de confrontation** (documentés en tête des fichiers, aucun scalaire figé pour autant) :
  `martial_apotheosis` (vecteur turn-start — `applyAction endturn` + `captureEvents` rend 1 action / **0
  event**, aucun per-coup observable ; il faudrait hooker `AttackDamageOperation$$ExecuteHit`) et
  `savage_echoes` (cast live = résidu out-of-pool pré-existant) ne confrontent le compte qu'au PORT.

  **LOT C — ce que la RE a tranché** (décompilé lu sur `gqfc5mff6c`, indices résolus sur
  `IdunBattle.Configuration.AbilityConstantType` : 0x2f=`nrOfHits`, 0x32=`nrOfHits_2`, 0x2b=`extraHit`,
  0x16=`range` ; 0x13=`HeavyRound` sur `DamageProfileType`) :
  - **BRUT → oracle CONFIG** : `StikkbombAbility$$ExecuteBehaviour`, `PlasmaGrenadeAbility$$ExecuteBehaviour`,
    `HarbingerOfDestructionAbility$$ExecuteBehaviour` et `DestroyerHiveAbility$$CreateBehaviour` passent
    `GetNumberConstant(0x2f/0x32)` et `GetDamageProfile(config, 0)` **tels quels** aux nœuds DSL ;
    `HarbingerOfDestructionAbility$$GetAdditionalTargets` et `HarvesterOfSoulsAbility$$ExecuteBehaviour`
    font de même avec `GetNumberConstant(0x16)` (`range`). Aucune formule entre la config et le nœud.
  - **CALCULÉ → oracle LIVE / dérivation** : le nb de coups d'Harvester est
    `If(HasFlag(Moved), ConfigConst(0x2f), Sum(ConfigConst(0x2f), ConfigConst(0x2b)))` — la FORMULE est
    testée, ses deux opérandes viennent de la config, et le compte réel est confronté au live
    (`len(live_main)`). Idem le dégât : confronté au live ou à une séquence directe rejouée sous le même rng.
  - **Piège « clé voisine / repli de même valeur » FERMÉ par dérivation** : `nrOfHits` (Harbinger,
    DestroyerHive), `nrOfHits_2` (PlasmaGrenade) valent **1** — exactement le repli de `ability_var(…) or 1` ;
    `range` d'Harvester vaut **3** — exactement le repli `or 3` du port. Une clé mal nommée rendrait donc la
    bonne valeur. Ces quatre lectures sont désormais prouvées DÉRIVÉES : le test décale l'oracle
    (monkeypatch de `gameconfig.ability`) et exige que le port suive. **Mesure** : port muté (clé remplacée
    par un nom absent) → seul le test de dérivation rougit, l'égalité statique reste verte — la
    démonstration que le contrôle n'est pas rituel.
  - Le percage effectif étant `clamp(0,100, PiercingRatio + ExtraPierce…)`, chaque test qui l'assert exige
    d'abord des ExtraPierce nuls : sans ça l'égalité testerait la somme, pas le choix du PROFIL.
  - Le rayon des scénarios Harbinger/Harvester est désormais **piloté par `constants.range`** (la frontière
    testée est `range` vs `range+1`), au lieu d'un 2/3 écrit en dur dans la géométrie du setup.
  **LOT D LIVRÉ (#110)** — oracles centralisés dans `tests/engine/runner/_config_oracle.py` (une clé
  absente y ÉCHOUE, jamais de repli sur 0 qui rendrait l'assertion vacue ; gardes offline dédiées dans
  `test_config_oracle_offline.py`) :
  - `PiercingRatio` de profil (Power, HeavyRound, DirectDamage ×2, Physical, Las ; Energy/Physical de
    `martial_apotheosis`/`sentinel_directives` étaient déjà faits par le lot B) →
    `damageProfiles.<P>.PiercingRatio`. `StaticBattleRules.Damage$$GetPiercingRatio` lit
    `DamageProfile.PiercingDamageRatio` (+0x14) TEL QUEL ⇒ BRUTE. Là où le behaviour natif appelle
    `AbilityConfiguration$$GetDamageProfile` (FlailSwing, HarbingerOfDestruction, DestroyerHive), le NOM
    du profil est vérifié en plus contre `constants.damageProfile` ; `HarvesterOfSouls` passe un littéral
    `Nullable<DamageProfileType>(0x13)` ⇒ le nom y reste structurel. Le fichier LasCannon dérive
    désormais `base` et `base + bonus` (`W_LASCANNON_PIERCE_BONUS`, constante du cctor natif) au lieu de
    figer 10/60, et ses contrefactuels comparent au `PiercingRatio` du profil RENDU par le sélecteur.
  - `getStuckInChance` → `traitVariables.getStuckInChance`, avec garde `!= getStuckInChance_2` (sinon
    l'assertion ne distingue plus la branche `GetStuckInAbility$$GetBonusHitChance` prise) ;
    `firstAidRecovery` → `globalValues.firstAidRecovery`.
  - `parryHitReduction` : `ParryEffect$$CreateEffectHitsBonusForAttack` =
    `ForAdditionWithMinimum(OwnerIsTarget & IsMeleeAttack, Direct(-GetNumberConstant(0x2c)), Direct(1))`
    ⇒ l'amplitude est BRUTE (config), le plancher `Direct(1)` est un littéral NATIF et reste littéral.
    Garde de discrimination ajoutée : `base - reduction > 1`, sinon le plancher absorberait la valeur et
    l'assertion serait verte moteur cassé.
  - plage `30 <= hpPct <= 50` (hypersensory) → appartenance au tableau per-niveau
    `abilities.HypersensoryAbilities.variables.hpPct` (les deux bornes en sont le min/max).

  `[opus]`, par lots de quelques fichiers — l'exécution live domine le coût, pas l'édition.
- ~~**`getstuckin_combat_chance` code les DEUX chances en dur**~~ — **RÉSOLU** (commit `886335f`).
  `engine/runner/damage_model.py` lit désormais les deux clés du gameconfig
  (`trait_var("GetStuckIn", "getStuckInChance_2" | "getStuckInChance")` = `ConfigConst(0x33)` /
  `ConfigConst(0x2a)` de
  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$GetBonusHitChance`), avec
  assertion sur clé absente. Les littéraux `100`/`30` ont disparu.
- **Nature du coup, résidus** (`case-106-ismeleeattack-fork` §7 — fork CLOS, `execute_normal_like`
  threade désormais la nature et le prédicat a un foyer unique) : (a) **le mode `AttackRangeType.Both`
  (3) n'est pas modélisé** — le port déclare la nature (`is_melee` du behaviour) là où
  `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` la calcule par `AreUnitsInMelee(attPos, tgtPos)`
  pour ce mode ; les deux coïncident sur tout ce qui a été mesuré (coups hors-mêlée), un coup `Both`
  résolu AU CONTACT ferait diverger ; (b) **famille ABILITY d'`execute_ability_attack`** — la mesure
  #45f dit que `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` reçoit des modifiers
  ATTAQUANT **vides** ; le port ne les vide pas, il se contente de ne pas threader la nature, donc les
  bonus SANS gate de nature (`DecoysAndMisdirection`, `RapidAssault`) y passent encore. `[opus]`.
- **Gate de CIBLE : maillon générique LIVRÉ (#115), reste l'INSTANCIATION par ability**
  (`case-115-ability-target-gate`). `AbilityHandler.visit_ActiveAbilityMessage` mirror désormais
  `IsInvalidTarget` : filtre statique piloté par les `TargetingOptions` du ctor + point d'extension
  `ActiveAbility.get_dynamic_invalid_target_reason` (1ʳᵉ instanciation : Waaagh 1058). Ce qui reste :
  (a) **renseigner `TARGETING_OPTIONS` sur les ~~60~~ 75 autres abilities du registre** (le registre a
  76 entrées, **1 seule** porte le masque — le gisement GROSSIT à chaque port ; 1 ligne par ability,
  lue au ctor décompilé — attention à l'overload « preset + flags » dont le littéral n'est PAS le
  masque effectif) et instancier leur `GetDynamicInvalidTargetReason` quand le bit `0x2` est posé ;
  (b) porter les règles du filtre statique laissées permissives (inventaire exhaustif et motif de
  chaque non-port en tête de `engine/runner/abilities/targeting.py`). La **portée**
  (`TargetingQuery$$GetRange`) est FERMÉE depuis #241 (`case-241-range-gate.md`) ; restent le
  **domaine TILE** (le gros morceau) et la **ligne de vue** (`GetTilesObscuringTerrain`), testée au
  même endroit de la cascade ;
  (c) `IsValidCaster`, `IsAbilityBlocked`, cooldown, mode atomique et
  `IsDeadUnitAndNotAllowedByAbility` restent non portés. `[opus]`.
- **Rider OVERKILL de `ThrillSeekers`** (`case-thrillseekers` §Résidus 1) — trait PORTÉ et validé live
  (branches + refresh + expiration), mais son second volet i2 (« if it defeats an enemy with a Crit,
  that enemy is always overkilled ») est une face **PRÉDICTION** non portée :
  `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` force son `allow_flag` à 1 quand
  l'attaquant `HasTrait(0x420)` ET `HasEffect(0x59a)` ET (`default_flag` OU le flag de crit) —
  cf. `case-30-raw-bounds` §« Acquis RE COMPLÉMENTAIRES ». Le port passe `allow_flag=0` en dur
  (`services/trait_damage_limits.py::compute_prediction_overkill`). Débloqueur : RE de
  `PredictAttackRaw` + threader `has_trait`/`has_effect` de l'ATTAQUANT jusqu'à `trait_damage_limits`.
  Biais unilatéral : le port SOUS-estime l'overkill des porteurs *Thrilled* qui critent (donc
  l'utilité `OverkillUnitUtility`), jamais l'inverse. `[opus]`.
- **Stat-mods d'effets SEEDÉS non revertables à l'expiration** (`case-thrillseekers` §Résidus 2) —
  angle mort **GÉNÉRIQUE**, mis en évidence (pas causé) par le port ThrillSeekers. Un effet à timer
  matérialisé par un behaviour puis CAPTÉ dans un snapshot porte un montant **déjà cuit dans les
  stats** et n'a aucune `ValueModification` côté port : son expiration offline ne le retire pas. Le
  retrait par timer des effets posés EN JEU est désormais couvert
  (`runner/operations/effects.py::revert_stat_mods_of_removed_effects`, mirror
  `IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification`) ; fermer le cas SEED =
  attribuer les stat-mods du seed par `statmod_source_key` ET faire skipper
  `refresh_stat_modifier_effects` sur les instances à `stat_mod_source`. Transverse (ActOfFaith,
  DoctrinaImperatives, AnvilShield…) → à promouvoir si un miss d'agreement le fait surface. `[opus]`.
