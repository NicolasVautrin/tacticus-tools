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
| #o10-c | **Cardinalité des groupes #179 de `blackObliterator`** — le live émet des coups que l'offline ne produit pas | `[fable]` | `case-o10-volk-moved-flag.md` §6.1. Montage seed 777 / `MC1_67` / `--p-units blackObliterator,adeptHospitaller --a-units necroWarden,necroWarden`, capteur `hitTraceArm` : attaque 2 (round `RuinousSalvo`) → live **9** coups (7 profil 19 + 2 profil 3) / offline **8** (6 + 2 Flame) = groupe `LetTheGalaxyBurn` manquant ; attaque 3 (round `WarpHail`) → live **9** (9 profil 19) / offline **6**, `additional_hits=None` = les DEUX groupes manquants. `mt_same=False` (1 puis 5 tirages d'écart) — donc bien une CARDINALITÉ, pas une magnitude. **Non reproduit** sur `C2_02`/`31337`, où les groupes Melta et Flame sortent normalement (`mt_same=True`, bit-exact) : le déclencheur n'est pas établi → `[fable]`. Ne pas confondre avec l'écart de magnitude du même montage, RÉSOLU (flag `Moved`). |
| #o10-a | **`test_avalanche_of_muscle_live.py` — 3 échecs PRÉ-EXISTANTS** (gate `IsCharging` non discriminant) | `[opus]` | Mesuré le 2026-07-28, identique avec et sans le fix `UnitFlag.Moved` (vérifié en remisant le fix et en rejouant) : `aucun delta positif charge vs no-charge [0, 0, 0, 0]` avec `diag={'al': 50, 'lvl': 1, 'mult': 180, 'bonus_per_hit': 599}` — le bonus `AvalancheOfMuscle` (ConfigVar 8) est résolu à 599 mais les contrefactuels charge/no-charge rendent la MÊME chose, donc `battle_query_is_charging` ne discrimine plus sur ce montage (`ChargedUnitIds@+0x190`, rempli par `MoveUnitOperation$$UpdateCharging`, vidé par `FinishUnitTurnOperation$$Execute`). 3 tests rouges sur `origin/master`. |
| #116-r | **AdaptiveStrategy (1005, `necroWarden`)** — reste du lot 1 Necrons | `[opus]`+prérequis | `case-116-necrons-lot1` §4 : RE COMPLÈTE (arbre + légalité + mapping du ctor `AddStatOverrideEffectBehaviour`). Prérequis restants : (1) **`RelentlessMarch` 1004** (passif `necroWarden`, `…RelentlessMarchAbility$$CreateBehaviour`) — sans lui la branche `If(ActorHasTriggeredAbility) TriggerAbility(…)` est un no-op structurel ; (3) nœuds `TriggerAbility` + `ActorHasTriggeredAbility`. ~~(2) sous-système OVERRIDE-ATTAQUE~~ **LEVÉ** : `AddStatOverrideEffect` existe (`abilities/behaviours/stats.py`), 2 users runner (#112 ExemplarOfHate `71dca97`, #114 InspiredToGreatness `d67b6ac`). `PerformAIAction` est déjà là. |
| #116-e | **Magnitude de `Chronometron_ExtraDamage` (1550)** — l'effet est posé mais INERTE | `[opus]` | `case-116-necrons-lot1` §2 : `…Chronometron_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` = `ForAddition(OwnerIsTarget & IsUnit(att) & AreFriends(att, EffectSource), If(IsMechanical(att), ConfigVar(9), ConfigVar(8)) × TimesEffectApplied)`. Manque, dans `attacker_ctx` du hook DÉFENSEUR (prédiction ET runner) : équipe de l'attaquant vs équipe de la SOURCE de l'effet, trait `Mechanical` de l'attaquant, compteur `TimesEffectApplied` par instance. Consommateur additionnel : `$$CreateRemoveEffectTrigger` = `On(9)` (effet CONSOMMÉ au 1er coup allié). |
| ~~#116-d~~ | ~~Séquencage RNG de `ChainLeftOverHitsAttackDamage` après un KILL~~ | **LIVRÉ (#125)** | `case-125-rng-wasted-hits` : ce n'était PAS un écart de flux `state.rng` (natif ET port roulent TOUS leurs coups — `AttackDamageOperation$$ExecuteHits` = `while (i < hits)` sans sortie sur la mort), c'était le **report** `GetLeftOverHits`, figé à `1 + extraHit` par #116 alors qu'il vaut `max(0, H - k - 1) + extraHit`. Corrigé + gardé (`test_chain_leftover_hits_live.py`, 2 seeds, contre-cas intégré). |
| #202 | Kit d'Abraxas (`thousInfernalMaster`) : WeaverOfFate + InfernalPacts + MasterOfTheTutelaries | `[opus]` | `case-202` : **tranches A, B et C LIVRÉES** (C : execute 1096 + effet 1197 + triggered 1173 Screamer-par-attaque-Psychic-du-SET-bonus-inclus + chaîne InfernalPacts + playbook NC slots 0x49/0x52/0x6b/0x72 — probe 202c PASS A1-A4/B/C, garde 31337 100 %). Résidu principal : face DÉCISION portée mais non confrontée oracle (`case-202` §8) — au premier walk Thousand Sons. |
| ~~#201~~ | ~~`VigilanceEternal` (1202) consomme un composite d'utilité que le port COLLAPSE~~ | **LIVRÉ (2026-07-28)** | `case-201-movement-suggestion-tiledistance.md`. Le littéral EST `MovementSuggestion(32)` et `UtilitiesDatabase$$InitializeUtilities` le compose bien en `[Tile(7), TileDistance(33)]` (tableau `[0]=7, [1]=0x21` relu au décompilé). `TileDistanceUtility` portée 1:1 (**aucun poids BC** — le facteur `−1/10` est en dur ; distance HEX ; signe négatif), composite enregistré dans `UTILITY_BY_TYPE`, `_vigilance_move_dest_tile` branché sur le foyer et son collapse « plus proche » + tie-break inventé par id SUPPRIMÉS. Le collapse n'était juste que dans le régime `Tile(7)` PLAT : **344 couples divergents / 847** sur `MC1_67`, **236 / 568** sur `C4_09`. 5 géométries jouées live, 2 boards, **les DEUX moitiés confrontées séparément** (3 réfutent le collapse, 2 réfutent `Tile(7)` seul) — natif 5/5 avec le composite. **Résidu nommé** : 5 autres call-sites passent `0x20` et gardent leur collapse (`TheBetrayer_TakeTurn` ×2, `BlackRage` 1163, `Waaagh` ×2 — littéraux relus un par un). ⚠ Ce résidu est **partiellement fermé par #206** : ne restent que les deux `TheBetrayer_TakeTurn`. |
| ~~#206~~ | ~~`BlackRage` (1163) et `Waaagh` (1058) : les deux call-sites `0x20` restés collapsés après #201~~ | **LIVRÉ (2026-07-28)** | `case-206-black-rage-waaagh-movement-suggestion.md`. Les deux ont **exactement** la forme de 1202 (`First(SortTilesByUtility(GetPossibleMovementTiles, caster@0x160, 0x20), 1)`, surcharge `int` -> `ownerSel` NUL). **Deux collapses différents** : Waaagh n'avait que le TRI collapsé, **BlackRage avait AUSSI son POOL** (`board.neighbours(cible)` = ring-1 NU, sans `MovableTilesInRange` ni `CanAddUnit` — la justification « reachability garantie par la DÉCISION » était fausse : le gate ne garantit que `Count(pool) > 0`). Portés : `black_rage_possible_movement_tiles_selector` + `_black_rage_move_range` (mirrors 1:1), `_black_rage_charge_tile` / `waaagh_charge_tile` branchés sur le foyer, et **`black_rage_tree` éclatée en 3 arbres** exécutés successivement — mirror des 3 `Execute`/`ExecuteAtomic` natifs, indispensable pour que `UnitMovementRangeWithBonus` voie l'effet 1342 déjà posé (sélecteurs natifs PARESSEUX). Gisement mesuré sur `MC1_67` : **314/712 couples divergents dont `Tile(7)` tranche** (Waaagh), **290 + 32 hors-pool / 702** (BlackRage). **19 géométries jouées live, 19 fois la tuile du composite, 0 contre-exemple** — dont une contre-épreuve où `TileDistance` SEUL départage deux tuiles à `Tile(7)=50`, et un cas où l'ancien collapse envoyait Lucien charger dans la Swamp (`TileEffects` −25). Piège de mesure documenté : **Waaagh SPAWNE avant de bouger**, le pool trié est le pool POST-SPAWN (un faux contre-exemple était né de la prédiction pré-cast). **Résidus** : les 2 `TheBetrayer_TakeTurn` (enveloppés d'un `SortByFormula(MinPathLength)`, cas différent) ; `BlackRage` sans `TARGETING_OPTIONS` — son `get_dynamic_invalid_target_reason` est le jumeau EXACT de celui de Waaagh et le sélecteur de pool est désormais disponible, mais poser la règle dynamique sans le masque serait inerte : **à livrer ensemble**. |
| #27 | Résidus `CalculateCustomUtility` : 4 sous-systèmes à porter (débloqueurs nommés) | `[opus]` | `case-27` : ~~2 portés~~ **6 portés au 2026-07-26** (1014 ArmoriumCherub, 1177 LightOfSanguinius, + 1020 HeraldOfTheApocalypse, 1029 Drachnyen, 1100 SorcerousFacade, 1199 DoomSiren — `playbook.REGISTRY` = 7 avec `Repair`) + ~~20~~ **16 résidus** classés par débloqueur (DSL-évaluateur / BattleQuery-token 0x44-0xb1 / multi-hit / utilité-déplacement / `dp=False` / dead-code / sans-id). ⚠ deux débloqueurs cités par `case-27` sont PÉRIMÉS : « MoW off-board » (levé côté COMBAT, `a9714a4`) et « porteur hors pool » (levé, `ab98129` catalog_inject) — le blocage MoW restant est la face DÉCISION seule. Les 4 overlays portés ont créé 4 nouveaux `[-D]` (décision portée, combat NO-OP). |
| #217 | P0 DÉCIDER≠EXÉCUTER : porter le combat des actives `[-D]` (décision portée, exécution NO-OP) — ~~27~~ **20 au 2026-07-26, dont 18 à porteur confrontable** | `[opus]` (Stormcaller `[fable]`) | **Liste à jour + symboles + confrontabilité : `port-residuals-inventory.md` §2.** (`port-roadmap.md` §3 est PÉRIMÉ : 1113/1163/1151 sont portées ; restent 1153/1191 du sous-groupe P0-WALK.) ⚠ `audit_kit_coverage.py` SOUS-COMPTE ce gisement (2 registres de décision lus sur 3) — cf. inventaire §2 et R23. |
| #20 | Port des kits par faction (ex-« Roadmap AdMec », généralisée à TOUTES les factions) | `[opus]` | `port-roadmap.md` §5 + `kit-coverage.md` (119 kits, 249 items ; piocher par faction, exceptions dures en §5.2). Audits régénérables : `audit_kit_coverage.py` / `audit_combat_ability_coverage.py`. |
| #5 | Chantier `DslContext` live-state | `[opus]` | Architecture à poser, pas d'énigme à trancher. |
| ~~—~~ | ~~**Substrat MULTI-HEX** (une unité occupant N tuiles)~~ | **LIVRÉ (2026-07-28)** | `case-91-duty-eternal.md`. Le SUBSTRAT était déjà porté et confronté live depuis `94b7118` (`case-R30`) ; ce qui manquait était le **PRODUCTEUR**, et il tenait en trois points lus au décompilé : (1) `SpawnUnitOptions+0x60`, le flag qui fait basculer `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute` de « une unité PAR tuile » à « **UNE** unité sur `GetTileIds(tiles)` » — le SEUL producteur d'empreinte multi-hex du binaire ; (2) le **nœud DSL** `ThreeTileUnitSpawnShape` (R30 l'avait porté comme *fonction*, donc inconsommable par un arbre) ; (3) **`RemoveMachine`**, sans rapport avec le multi-hex. `DutyEternal` (1158) est portée, au registre avec ses DEUX littéraux (`TARGETING_OPTIONS = 0x20000040000042` forme flags-directs, `ABILITY_ATTACK_TYPE = Others`), et confrontée live : 20 tests, 6 vues rouges, 2 scénarios de généralisation. Ferme au passage 2 résidus `case-R30` §6 (gate `HasTrait(0x418)` de `GetMovablePositionsFor` ; occupance par pied de `CanAddUnit`). **`AetherStride` (1208) n'a plus d'obstacle de substrat** — seulement un porteur hors seed BC (voie `catalog_inject`). |
| — | **Stats résolues des MoW non captables** (spec `frida/hooks`) | `[opus]` | `case-mow-offboard-cast` §8 : `combatSnapshot.allUnits` **et** `statModSources.targetUnits` filtrent `ty === EntityType.Unit` → aucune stat de MoW lisible (elle a pourtant Attack/Crit*/ExtraHits/ExtraPierce*). Base = 0 (gameconfig) donc le seed offline est exact à l'init ; seule une **stat-mod posée en cours de combat sur la MoW** échapperait. Fix = élargir les deux filtres à `EntityType.Machine` (`GetStat` est déjà générique) → **exige rebuild+reinject**, à programmer quand l'atelier est vide. |
| ~~R14~~ | ~~**Face DÉCISION des MoW** (plans d'attaque **ET** générateur NonComparable)~~ | **LIVRÉ (2026-07-27)** | `case-r14-mow-decision.md`. Le chemin natif dédié est `IdunBattle.AI.Tactics.DefaultMachineTactic` (routé par `AiQuery$$GetUnitTacticForUnit` sur `IsMachine`), PAS `aiPlaybookPredict` : **pas de `MovementActionGenerator`**, caster à `UnitPosition.NullPosition`, tuiles candidates VIDES (branche `Count == 0` d'`ActiveAbilityActionGenerator.<GenerateActions>d__7`), émission par `DefaultMachineTactic$$GenerateInputMessagesFromUnitAction`. Reachability PROUVÉE : `DefaultGroupOperator$$CalculateNextActionForPlayer` ajoute `PlayerComponent+0x78` (l'id de machine) aux entités du joueur. Porté : `DefaultMachineTactic` + `context.build_machine` + routage dans `engine_decide` + le gate `ActiveAbility$$get_CanCurrentlyBeUsed` (cooldown **et** MUNITIONS — les 8 MoW ont une ability à `munitionsCost=1` `hasAmmo:false` au seed BC). Sweep 8/8 MoW sans violation ; coïncidence mesurée sur 1187. **Aucune origine inventée, aucune MoW dans `dv.units`.** |
| ~~#221~~ | ~~**`Daemon_ExtraBlock` (1034) inerte côté COMBAT** — 1 tirage RNG manquant par attaque contre TOUTE unité Daemon~~ | **LIVRÉ (2026-07-27)** | `case-221-daemon-extrablock-rng.md`. `AttackDamageOperation._block_sources` thread l'`Attack` COURANTE du défenseur (`ctx.attack` = `GetStat(ATTACK, Current)` = le `StatAmount(Self@0x148, 0, 0)` de `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonAbility$$GetBlockDamage`). Deux mirrors complétés dans la foulée, même fonction native `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances` : le failed-id est le **`BEntityId`** de la source (0 pour l'entrée par défaut de `MultiValueStatComponent$$GetAllValues`, l'entité-effet sinon), pas la chance ; et la liste est **triée décroissant par amount** (`<>c.<CalculateBlockChances>b__15_0` = `b.blockDamage - a.blockDamage`). Validé live sur les DEUX vecteurs (ability `probe_brazier_daemon_offset.py`, normale `probe_221_daemon_normal_attack.py`), gardes `test_daemon_extra_block_live.py` + `test_block_chances_order_offline.py`, et le bridage `compare_hits=1` de `test_brazier_of_holy_fire_live.py` est levé (4 coups confrontés). |
| ~~—~~ | ~~**`OnToxicDamageAbility` (1203) non porté** — 1 tirage RNG manquant par CIBLE d'une attaque de profil `Toxic`~~ | **LIVRÉ (2026-07-27)** | `case-1203-on-toxic-damage.md`. Porté en arbre DSL (`triggers/loki/on_toxic_damage.py`) : `If(IsFirstHitInSeries() & Maybe(ConfigConst(1203, ·, 0x2a = chance)), AddEffect(0x4dc Contaminated, Tiles(target), source = la TUILE))`, `chance = 25` lue en config (`globalValues.toxicDamageContaminationChance`, ancrée sur la constante BC). Câblé sur les DEUX vecteurs d'attaque (normale + ability), UN `next_bool` par série de coups — le ET natif COURT-CIRCUITE, donc le `Maybe` n'est évalué qu'au coup d'index 0. Effet mesuré : la confrontation per-coup de `test_rad_bombardment_live` n'est plus bornée à la 1re cible (le retard d'un tirage a disparu) ; contre-épreuve `probe_1203_toxic_contamination.py` (canal armé 1/1 vs désarmé 0/1 face au live). **Deuxième moitié du même étage RNG que #221** : les deux canaux ont été re-confrontés ensemble après rebase. |
| #175-r | **Metadata par-tuile des 5 feuilles Tile(7) encore muettes** (leur ctx de TRAIT est désormais peuplé) | `[opus]` | `case-175-tile-unit-traits` §4 : `ctx["unit_traits"]` est livré et `meta.is_territory` / `meta.tile_effect_type_ids` sont câblés (DespoiledGround 28 validé live). Ce qui manque est la metadata PAR TUILE, qu'aucun RPC ne remonte : `door` (le `roomTileType` 0/1/2 est DÉJÀ projeté par `projectMatchState` mais absent de `tileMeta` ; manquent l'état ouvert/fermé et `BC.Board.Doors`, présent dans 15 des 779 dumps) → `SummonDislikeDoorOpening(29)` -50 + `HeroLikeDoorOpening(30)` ; `occupant_is_powerup` → `PowerUp(26)` -300 ; `attract_mechanicals_neighbor` → `AttractMechanicals(57)` ; `movetowards_hexdist` (dérivable OFFLINE des positions, sans RPC) → `MasterOfTheTutelaries(62)`. Et `CapturePoint(24)` (+/-300) est câblé mais **jamais vrai** : la seed BC est `RuleSet: null` / `GameMode: Campaign`, le territoire est un attribut du ruleset `TerritoriesRulesetBattleConfig` — 0 tuile territoire mesurée. |
| #175-e | **Test d'EXCLUSION de `DespoiledGround`/`Contaminated` non porté** | `[opus]` | `case-175-tile-unit-traits` §5 : `DespoiledGroundUtility.<d__5>` et `ContaminatedUtility.<d__4>` commencent par `cfg = TryGetValue(this+0x60, <EffectType>) ; if (Contains(cfg, unit)) return 0`. Le port ne modélise cette exclusion que côté Contaminated (`ctx.contaminated_excluded`, jamais peuplé) et pas du tout côté DespoiledGround → sur-pénalise une unité exclue. Le contenu de `this+0x60` reste à RE. |
| #17 | Surveillance des 2 résidus `move` | `[opus]` | Nature RNG, non actionnable — veille seulement. |
| ~~#PAI-c~~ | ~~Consommateurs de `PerformAIAction` restants : Waaagh 1058, SendInTheNextWave 1016, Incursion 1021, Poxwalkers 1040, + retrofit CultDemagogue 1179~~ | **LIVRÉ (`3f7b9d1`, 2026-07-25)** | « #94 consommateurs SPAWN/AI-CONTROL ». Les 5 ids sont dans `ABILITY_CLASSES` (`WaaaghAbility`, `SendInTheNextWaveAbility`, `IncursionAbility`, `SpawnPoxwalkersAbility`, `CultDemagogueAbility`). Résidu restant, DISTINCT : l'ORDRE intra-groupe de `PerformAIAction(asGroup=1)` (plus bas dans ce fichier). |
| ~~#PAI-k~~ | ~~`ListenUpMaggotsEffect` (0x426) + chaîne `SwornProtector`→spawn de Kell~~ | **LIVRÉ** | Chaîne portée + confrontée live de bout en bout (`case-perform-ai-action` §5.1 + §6 réécrits). Ground truth : Kell apparaît vivant porteur de l'effet 0x426, le cast 1028 spawne **3** gardes (2 sans Kell) et son rayon `PerformAIAction` vaut **3** (2 sans Kell). La face DÉCISION `SupremeCommanderPlaybook` est portée dans la foulée (gate `IsFriendlyKell` désormais atteignable). |
| ~~#119~~ | ~~Face DÉCISION de `SupremeCommanderPlaybook` (1028) jamais confrontée à l'IA native~~ | **LIVRÉ** | `case-perform-ai-action` §6 (réécrit). Le gate (2) lisait `u["parentId"]`, clé qu'AUCUN RPC ne publie → `should_evaluate` constamment `False` = playbook enregistré-mais-mort ; **désaccord mesuré** (le natif caste, le port attaque). Corrigé par la reconstruction offline `_kit_spawn_visual_ids` ; ACCORD sur 5 états craftés (dont le discriminant « deux Creed, un seul Kell adverse ») + 2 couples board/seed. Étage (3) RE-corrigé : `chance = 1/2 + hp%(caster)/2` (stat 5 = Health), déterministe à PV pleins (20/20), mesuré 31/40 à 32 % de PV. Garde : `tests/engine/test_supreme_commander_decision_live.py`. |
| #66-r2 | Les 2 derniers consommateurs de `DSLFactory.Revive` : **FuelledByFury** (`ultraTitus`) et **GhostRevive/TimeFlux** (`thousTerminator`) | `[opus]` | Retrofit #79 + fermeture #88/#89 LIVRÉS (`case-66-revive-in-place` §6-§7 : les 5 `ReviveEffect` + les 3 hypothèses fermées PAR LECTURE + la garde `KillUnitOperation`). Restent 2 chantiers PROPRES (arbres entièrement RE, cf. §8) : **FuelledByFury** — bloqué sur 3 points nommés, dont l'**émetteur de `On(PendingDeathAdded=3)` non localisé** (ancrage à hooker : `MatchState.AddDeath @181009f90`, xrefs DATA only) + le contexte `TriggeringAbilityIs(FinalJustice)` non threadé + la pose de l'effet 1324 ; **GhostRevive/TimeFlux** — exige un vecteur `On(PreUnitMove=31)`, un effet portant une TUILE (le ghost) et un revive **NON in-place** (`SetRevivePosition @180e936e0` paramétrée). Les DEUX carriers sont des heros DANS le pool ⇒ validables LIVE le jour du port. |

| #BL-1029r | **`Drachnyen_ExtraAttackAbility` (triggered 1485)** — le 2ᵉ volet de dégât d'Abaddon, ~40 % du dégât observé au cast | `[opus]` | `case-bl-1029-1020` §5.1 : la face ACTIVE (1029) est portée et pose bien l'effet 1471 qui ARME cette triggered, mais la triggered elle-même n'existe pas offline → **10 coups live vs 5 offline** au cast (mesuré seed 777/MC1_67). RE **déjà faite, à recopier** (trigger + behaviour + validTargets cités in extenso dans le case doc) ; infra prête (`EFFECT_TRIGGERS[1471]`, patron `PsykerExtraAttackAbility`). **Seul nœud manquant : `SortUnitsByDamageUtility`** (précédent de collapse : `ExemplarOfHate`). Carrier `blackAbaddon` = HERO dans le pool ⇒ validable live. |
| #BL-1020r | **Magnitude de l'effet 1027 `HeraldOfTheApocalypse_ExtraDamage`** — posé mais INERTE | `[opus]` | `case-bl-1029-1020` §5.2 : `…$$CreateEffectDamageBonusForAttack` = `ForAddition(OwnerIsTarget & IsUnit(Caster@0x160), ConfigVar(8 = extraDmg), AbilityOrEffect(0x3fc))` ; consommation = `…$$CreateHandleTriggerAbilitiesInternal` = `Triggered(On(9) & OwnerIsTarget & IsUnit(Caster), GetRemoveEffectBehaviour())` (+extraDmg au PROCHAIN coup reçu, puis l'effet part). Patron identique aux `*_ExtraDamageEffect` déjà portés (`effects/loki/extra_damage.py`) → travail de recopie, pas de RE. |
| #BF-chance | **Chance de fuite `BattleFatigue` non sourçable offline** — bloque le dispatch de `TriggerAbility(0x401)` ET rend arbitraire le défaut de la voie trigger-sur-mort | `[opus]`+prérequis | `case-bl-1029-1020` §5.3 + `runner/operations/behaviour.py` : `BattleFatigueAbility$$GetFleeChance` = `ConditionalAmount(TargetIsOverkilled, Direct(GetNumberConstant(0x33)), Direct(GetNumberConstant(0x2a)))` sur une `AbilityConfiguration` **absente du gameconfig**. Deux défauts INCOHÉRENTS coexistent aujourd'hui : `behaviour.py` FUIT toujours (voie trigger), `TriggerAbility` ne dispatche pas (voie Herald). Prérequis = capter les 2 constantes (point d'ancrage : `AbilityConfiguration$$GetNumberConstant` sur la config 1025, ou un sweep live de fréquence de fuite) ; ensuite les DEUX voies partagent le même gate. |

## Résidus documentés (pas encore des tâches)

Remontés par les cases closes ; à promouvoir seulement si un miss d'agreement les fait surface.

- **Cycle de vie de `ContagionsOfNurgle_ArmorReduction1/2` (1071/1072)** — `case-dpw` §5/§7. Le
  vecteur `On(UnitAdded)` est porté (une unité qui APPARAÎT dans une aura Contagion ennemie prend
  le −20 %), mais l'effet n'est **ni re-évalué quand l'aura grandit** (`CalculateRange` = 1/2/3
  selon `TurnsStarted`), **ni retiré quand l'unité en sort**, **ni basculé 1071 ↔ 1072**. Le natif
  tient ce cycle par `CreateActiveCondition` (fenêtre `[min, max]` sur le nombre d'auras), que le
  port ne matérialise pas (pas de flag `IsActive`). La variante **−40 % (2 auras ou plus) n'a
  aucun montage live**. Les branches `UnitResurrected(0x2f)` / `UnitRevived(0x2e)` du même trigger
  ne sont pas câblées.
- ~~**`deathBlightlord` : +2 `genrand` natifs à l'entrée d'une attaque mêlée**~~ — **CLOS**
  (`case-207-haze-of-corruption-target-finder.md`). Ce n'étaient ni les effets `1375`/`1147`
  (= `TerminatorArmour_Visual` / `_ReduceDmg`, purement défensifs) ni le spawn de Kell, mais
  `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility` :
  `On(0x2b) & get_OwnerIsCaster` → `PickRandomly(Damageable(AdjacentEnemies(Self) &
  AdjacentFriends(Target)), 2)`, soit `min(|pool|, 2)` tirages AVANT tout coup. Il y en a **deux**
  ici parce que `SwornProtector` fait ré-émettre `On(0x2b)` par la ré-entrée #120bis — **1 + 1**,
  pas un forfait. Port 5/5 sur 4 seeds, échelle `k = 0/1/2` → 3/4/5 natif == port.
- **`HazeOfCorruption_DamageTransfer` (1077) : le bond est POSÉ, sa charge utile ne l'est pas** —
  `case-207` §5. `IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$GetLeftOverDamages`
  / `$$CreateTargetTriggerBehaviour` (report du dégât excédentaire + 1 coup Toxic `extraDmg` sur le
  relais quand la cible est défaite) n'a **aucun consommateur** côté port : quand `deathBlightlord`
  DÉFAIT sa cible, le port ne reporte rien. Hors du flux RNG (le tirage est tout entier dans le
  target-finder), donc invisible sur les comptes de `genrand` — il faut un montage où la cible MEURT
  sous le coup pour le chiffrer. `[opus]`.

- **`AvalancheOfMuscle_ExtraDamage` (1025, passif `astraBullgryn`) — gate `IsCharging` non porté**
  (`case-astramilitarum-fragbomb-basilisk` §4). MESURÉ (`probe_avalanche_charge_gate.py`) : quand le
  porteur A BOUGÉ pendant le tour, le natif ajoute `+extraDmg[niveau passif] × multiplicateur` FLAT par
  coup sur les ennemis **adjacents au caster** — au niveau 50 / 180 % = **+599 par coup**, sur l'attaque
  NORMALE comme sur FragBomb (1017). Sans charge : bit-exact 4/4 et 18/18. Même gate, même canal
  (modifier EAGER) que les résidus déjà nommés `BlackRage_ExtraDamage` / `FeederTendrils_ExtraDamage` —
  le débloqueur est COMMUN : exprimer « l'unité est entrée au contact ce tour » dans le contexte
  d'attaque per-coup. Magnitude NON négligeable ici (+599 sur ~1300 = +45 %). `[opus]`.

- **Le tier `get_Priority` n'est encore *observable* sur aucun porteur** (`case-170-get-priority` §6).
  22 abilities ont un tier ≠ 0 (`engine.playbook.noncomparable.NATIVE_PRIORITY`), 3 sont portées
  (NovaBoost 1192 = 1000, ThriceBlessedConflagration 1187 = 100, NovaShield 1194 = -1000), mais
  **aucune unité ne porte deux NonComparable PORTÉES de tiers différents** — l'ordre inter-tier
  n'est donc gardé que par un test à playbooks stub, pas par un agrément live. Le débloqueur est
  nommé : porter **`DevastatingRefrain` 1188** (NonComparable, tier 0 mesuré), la seconde active de
  `adeptExorcist` qui porte déjà 1187 au tier 100 — le couple devient alors le scénario d'agrément
  naturel du tier (à cible disponible pour les deux, le natif doit émettre 1187 quelle que soit
  l'utilité de 1188). Les 19 autres abilities de la table ne sont pas portées. `[opus]`.

- ~~**Le VERDICT du `Maybe` de `LetTheGalaxyBurn` diverge natif/port**~~ — **CONSTAT PÉRIMÉ, RÉFUTÉ
  PAR LA MESURE (#159 (b))**. Le diagnostic décrivait un arbre qui n'existe plus : `case-o4a` avait
  déjà remplacé `next_internal(0,100) < pct` (borne 100) par la primitive native `NextBool(chance)`
  (`next_internal(1,100) <= chance`, borne 99). Re-mesuré à flux RNG calé sur 6 montages
  (`blackObliterator` vs `necroWarden`, MC1_67) : **le verdict est IDENTIQUE 6/6** — 4 seeds où les
  deux côtés arment, 2 où aucun n'arme — et le budget de tirages le confirme (1 tirage de `Maybe`
  des deux côtés). Détail : `docs/rl/case-159-rng-canal179-et-maybe-ltgb.md` §3.1.

  **RÉSIDU NEUF qui le remplace, localisé ET chiffré : `LetTheGalaxyBurn` est porté dans le MAUVAIS
  CANAL.** `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits` (lu
  verbatim) en fait un **groupe du canal #179** — `count = 1` (nœud NULL), `profile = -1`, dégât =
  `FirstHitInCurrentAttackDamageRange()` sur les DEUX nœuds — alors que le port l'implémente en
  `create_effect_hits_bonus_for_attack`, c.-à-d. un coup d'**ARME** de plus. Conséquence MESURÉE :
  le coup surnuméraire natif est une **constante déterministe** = `round((cellule.min +
  cellule.max)/2)` (cellule d'arme réduite `(906,1359)` → **1133** sur 4 seeds ; cellule `(725,1087)`
  → **906**), là où le port tire une valeur aléatoire dans cette cellule. Le nombre de tirages, lui,
  est le bon (1) — l'erreur est **purement de valeur, bornée à un coup par attaque**, et le flux
  aval reste aligné. Correction = déplacer le +1 de la formule de coups vers le canal #179 **sur les
  DEUX faces** (la prédiction native le reçoit aussi comme groupe, via
  `AActiveAbility$$GetAdditionalHitsFromEffectsForPrediction`) → touche `attack_hits_formula`,
  `hits_bonus_from_effects` et `playbook/prediction/normal_attack.py`. Porteurs : les 5 héros Black
  Legion du trait 1058. `[opus]`.

- ~~**Conso RNG du canal #179 non bit-exacte sur le vecteur ability**~~ — **RÉSOLU (#159 (a))**, mais
  l'étage fautif n'était **aucune** des deux pistes de la fiche : ni l'ordre relatif
  `ExecuteAdditionalHitsWithoutDamageProfileType` / `EvaluateAfterHitTriggers` (tranché depuis par
  `R6-b''` : l'émetteur after-hit est la **dernière instruction de chaque `ExecuteHit`**, donc en
  amont du canal), ni le nombre de tirages par coup (juste depuis `R6-b`) — c'était **les BORNES**.
  Un descripteur porte **DEUX** nœuds de dégât et `IdunBattle.Entities.Effects.BaseEffect$$
  AdditionalHits(this, entities, useDisplay)` choisit : nœud ROLL (`amountNode` slots 2/3) en
  COMBAT, nœud DISPLAY (`minNode` slot 4, dégénéré) en PRÉDICTION —
  `AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType` met l'octet
  **explicitement à zéro**. Le port ne rendait que le nœud DISPLAY pour `FleshmetalGuns`
  (`amount = Average`) et étalait ±20 % en combat, au lieu de tirer dans `[minDmg, maxDmg]`.
  **PORTÉ + garde live** (`test_additional_hits_amount_bounds_live.py`) : groupe live reproduit
  **8/8** par le nœud ROLL et **0/8** par le contrefactuel, sur deux variantes du cycle (WarpHail
  asymétrique, largeur 399 vs 359 ; Melta quasi symétrique, 500 vs 499), 8/8 discriminants.
  Les chiffres hérités (`[2735, 2553]` vs `[2481, 2754]`) étaient caducs — mesurés avant `R6-b`.

  **Résidu jumeau restant = R6-c** (§4.a de `port-residuals-inventory.md`) : les descripteurs
  `amount` dont le nœud ROLL n'est pas encore câblé. La RE est **lue et écrite** dans
  `case-159-…` §4 — `CyclicIonBlaster` (bornes COMBAT = `[minDmg(+extraDmg), maxDmg(+extraDmg)]`,
  le port étale ±20 % **autour du minimum** : `[479,719]` au lieu de `[599,898]` à mult 180, ce qui
  EST la signature « groupe live au-dessus de la borne haute du port » mesurée sur `tauCrisis`) ;
  `FoulInfusion` et `ExplosiveMaladies` (nœud ROLL **scalaire** → bornes dégénérées, donc un
  changement de **consommation** aussi). Non portés : aucun montage live monté sur leur porteur.
  `[opus]`.

  **2ᵉ datapoint (2026-07-28) qui BORNE les DEUX résidus ci-dessus** (`case-bl-1029-1020` §5.4) :
  `HeraldOfTheApocalypse` (1020, `blackHaarken`) est **bit-exact offline == live dans les DEUX
  régimes du `Maybe`** — `MC1_67` où le trait ARME (3 coups/cible, `{77:[1738,1979,1846],
  79:[1805,1632,1536]}`) comme `C3_01` où il n'arme pas (2 coups/cible). Ni l'écart de seuil du
  `Maybe`, ni le désalignement du canal #179 ne se manifestent sur ce porteur.
  Ce datapoint disait que le vecteur ability est aligné **quand le canal #179 n'est pas sollicité**,
  donc que le suspect était bien le canal et non le vecteur : **#159 l'a confirmé** en localisant
  l'étage BORNES du descripteur. Garde INCONDITIONNELLE en place
  (`test_black_legion_1029_1020_live.py`), plus de gate conditionnel.

  ⚠ **TENSION À LEVER AVANT DE PORTER le résidu (b)** : `blackHaarken` porte lui aussi le trait 1058,
  et `case-bl-1029-1020` §5.4 le rapporte **bit-exact per-coup dans le régime où le `Maybe` ARME**
  (`{77:[1738,1979,1846]}`) — sur le vecteur **ABILITY**, donc avec le modèle « +1 coup d'ARME » du
  port. #159 mesure l'inverse sur le vecteur **NORMAL** (`blackObliterator`) : coup surnuméraire
  **déterministe**. Les deux mesures ne sont donc pas contradictoires *a priori* (les deux vecteurs
  ne passent pas la même `HitDamage` au premier coup : dégénérée pour l'attaque normale, non
  dégénérée pour l'ability bounds-mode — et `FirstHitInCurrentAttackDamageRange` en dépend
  directement), mais **le porteur du fix devra trancher lequel des deux régimes s'applique où**,
  et re-jouer les DEUX gardes. Ne pas porter (b) sans ce montage croisé.

- **Caps PAR-EFFET de la formule de coups** (`case-psychic-aoe` §3, remonté par le port Doombolt).
  `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` ne plancher **jamais** à 1 : il termine
  par `System.Math.Max(hits, 0)`, et le « minimum 1 coup » observé (LightCover/Parry) vient du clamp
  `hits = Math.Max(hits, Math.Min(base, cap))` posé **par effet**. Le port approxime encore ce clamp
  par un `max(1, …)` global dans `services/attack_hits_formula.py`. Le seul régime où l'approximation
  était FAUSSE — base de coups **0** — est corrigé (plancher borné par la base, mesuré live sur
  Doombolt `db-4`). **Reste faux** : une base ≥ 1 ramenée sous 1 par un malus **sans** cap rendrait 1
  côté port là où le natif rendrait 0. Non mesuré, aucun consommateur actuel ne l'atteint. Le fix =
  porter le `cap` par effet dans `hits_malus_from_defender_effects`/`hits_bonus_from_effects` (RE des
  caps natifs) plutôt qu'un plancher global.
- **Canal CASTER-dynamique du gate de ciblage** (`case-psychic-aoe` §5.1). `abilities/targeting.py`
  porte le bit `0x2` (`TargetMatchesDynamicRule`, méthode `get_dynamic_invalid_target_reason`) mais
  PAS le bit `0x4` (`CasterMatchesDynamicRule`, slot vtable `this+0x470`). 1er consommateur repéré :
  `IdunBattleLogic.Entities.Abilities.Active.Loki.DoomboltAbility$$GetDynamicInvalidCasterReason`
  (refuse le cast quand `GetTargets()` est vide → `actionConsumed = false`). Observable perdue = le
  turn-flag d'un cast sans cible, jamais le dégât.
- **`PsychicStalk`** (passif `thousAhriman`, effets 1215/1216/1435 ; triggered 1179) absent du
  registre `runner/operations/triggers/dispatch/registry.py` (`case-psychic-aoe` §5.3). Inerte tant
  qu'aucun hex ne brûle ; par ricochet, le terme `Count(hexes en Feu)` du nombre de coups de Doombolt
  n'a pas pu être confronté live à une valeur ≠ 0.

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

- ~~**La tuile d'ORIGINE est dans les candidats d'ability du port, pas dans ceux du natif**~~ —
  **PRÉMISSE RÉFUTÉE + ORDRE PORTÉ** (`case-r1-origin-action-tile.md`). Le slot +0xe n'est PAS
  `GetMovableTilesFor` mais **`IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor`**
  (seul des trois candidats à ne PAS déréférencer son 3e argument, que le call site passe à `0` ; et
  seul à rendre des `UnitPosition`, le type qu'énumère `FilterMovementTilesForMaxMovement`). Son
  `OrderedSet` est SEEDÉ avec `GetUnitPosition(unit)` puis `UnionWith(movable)` : **l'origine EST
  candidate, et PREMIÈRE**. Réfutation live indépendante : 10 chunks natifs « caste sans bouger » avec
  un movable NON vide sur 3 couples. Ce qui divergeait réellement = l'**ORDRE** (`Bucket$$AddAction`
  keep-first ⇒ à utilité ÉGALE le natif reste sur place, le port bougeait). Porté : origine en tête de
  `reach_nc`/`action_tiles`/`_plans_for_unit` et du sweep `_best_attack`. Mesure : +1 `stay` sur
  `C3_01`/31337 et sur le scénario crafté `C4_02`/4242 (Njal), 0 régression sur 4 couples.
  **RESTE OUVERT** : R1-b (ordre RELATIF des tuiles de move — l'imposer est mesuré régressif) et la
  divergence S3 de `case-128` §5, dont l'explication est tombée avec la prémisse.

- **Arbitrage Comparable `ExcruciatingFrequencies` (1197) vs attaque NORMALE — RÉSIDU RÉDUIT**
  (`case-128-tile-elevation-utility` §6, qui a clos l'hypothèse « terme d'élévation » de
  `case-124` §7). Le terme `Tile(7)`/`Elevation` est un **mirror exact** (gate `get_IgnoreTileUtility`
  = `xor al,al ; ret`, `MakeFinalTilePrediction` = identité, membership 29 feuilles lue dans la carte
  de composition `UtilitiesDatabase+0x58`, BC `{Multiplier 10, Highest 10, Lowest -5}`) et le natif le
  paie (mesure S3). L'étage dégât est **bit-exact** 18/18. ⚠ le sous-cas « origine retirée » de ce
  raisonnement s'appuyait sur une prémisse depuis RÉFUTÉE (cf. l'entrée R1 ci-dessus : l'origine EST
  candidate côté natif) — le chiffre 37.05 reste, sa justification non. Reste : sur l'état où 1197 est
  disponible, natif = `1197@(4,1)` (port 27.977) contre `69@(3,3)` (port 37.05) → il
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
    - ~~**`MaybeTrigger` non porté**~~ — **FAIT (`case-o4a-maybe-trigger-rng.md`)** : le gate PileIn
      est câblé sur le nœud `MaybeTrigger` (1 `next_bool` par grot candidat, `Randomize` de placement
      SEULEMENT sur succès, mirror de `If(Maybe(chance), Spawn, Nothing)`), et la branche
      `!CanUseRandom` (`99 < chance`) est portée. Comptage live bit-exact : **4/4 datapoints**
      (le port d'avant : 0/4, et il créait un grot FANTÔME quand le tirage échouait).
      Les deux gaps découverts par cette mesure sont **TRANCHÉS**
      (`case-n8-owner-has-finished-min-turns.md`) :
      - ~~**`OwnerHasFinishedMinTurns` est PER-UNITÉ, pas per-JOUEUR**~~ — **FAIT** : le gate est
        `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished(Self) >= 2`, soit
        `BaseUnitComponent + 0x5c`, écrit par la boucle d'`IdunBattle.Operations.EndTurnOperation$$
        Execute` sur `PlayerComponent.CurrentlyOwnedUnitIds` AVANT `On(0x17)`. Port :
        `UnitComponent.turns_finished` + `turnflow._bump_turns_finished`. Mesure live 4
        (seed, board) : âge 0 → **0** tirage natif (gate FERMÉ alors que le joueur a fini ≥ 2 tours),
        âge 1 → **1** ou **5** ; port 8/8.
      - ~~**`load_state` ne seede pas `state.turn_counts`**~~ — **REQUALIFIÉ, sans consommateur** :
        l'unique lecteur restant (`EnvAmbushResurrectAbility`) en prend une DIFFÉRENCE avec
        `turn_defeated`, écrit depuis le même compteur ⇒ invariant par décalage. Ce qui reste est le
        seed du compteur **PER-UNITÉ** : gap de **hooks** (résidu **N11** de
        `port-residuals-inventory.md`) — `+0x5c` n'est pas un `StatType`, `combatSnapshot` ne peut
        donc pas l'atteindre ⇒ capteur à écrire, **rebuild + reinject requis**.
    - **Feuilles `Tile(7)` gatées sur l'unité, dans le tri de placement** — **RÉSOLU pour les
      call-sites dont `dc.units` est le CASTER** (`case-165b-tile7-unit-gated-leaf.md`) : le
      sélecteur est lu dans `SortTilesByUtilitySelector$$Select` (`dc.units = this.units.Select(…)`,
      posé à `UtilityMovementCase+0x10` par la surcharge « tile » du ctor), le foyer prend un
      `unit_id` et `runner_tile_leaf_ctx` en dérive le `ctx`. C'est ce terme
      (`GeminaeSuperiaPlaybook` = `10 × |CanAddUnit(AdjacentTiles(tuile))|`) qui fermait le résidu
      #165 §4. **Reste ouvert le seul call-site SUMMON** (`SortTilesByUtilityForSummon`) : son
      `dc.units` est `AllAliveMachinesSelector`, un ENSEMBLE d'unités — porter sa résolution
      (le `case.unit` natif y est une collection) est le résidu restant.
    - ~~**`Swamp -> Thorns_DefenseReduction` (−25) porté en local** (`spawn.py::_PLACEMENT_TERRAIN_EFFECTS`)~~
      — **FAIT (`case-155-swamp-fork-maybetrigger.md`)** : le fork est fermé par la RE des DEUX boucles
      de `TileEffectsUtility`. Le −25 n'est pas un « terrain-effect » comme le +9 DryBush : c'est un
      effet que `ThornsBlockMovementAbility$$CreateBehaviour` pose **sur la tuile** (donc **Loop1**,
      canal dynamique), là où LightCover est une ability **hébergée** (**Loop2**). Le foyer unique vit
      dans `utilities/tile.py` (`TERRAIN_HOSTED_ABILITIES` = Loop2, `TERRAIN_TILE_OWNED_EFFECTS` =
      repli Loop1 dédupliqué contre le canal dynamique) ; les 8 call-sites l'appellent, la table de
      placement parallèle a disparu et le site de placement lit désormais `state.effects`. Mesuré
      live : régimes hydraté et non hydraté CONVERGENT (même tri, même tuile, tous deux = live) ;
      témoin sans le −25 → le port place sur la Swamp.
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
  - ~~**N5**~~ **RÉFUTÉ** (2026-07-27, `case-n5-chain-after-refused-addeffect.md`) : la chaîne **ne
    tombe pas**. `AddEffectBehaviour$$Execute` jette le retour de l'opération et rend un
    `OperationResult` zéro-initialisé ⇒ `CombinedBehaviour$$Execute` ne court-circuite jamais sur une
    pose d'effet. Le port était déjà conforme ; le « ground truth » était un confond (aucun DarkAngels
    à portée). Doc corrigée + garde live ;
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
  - ~~**RÉSIDU `[opus]`**~~ **CLOS** : chaîne `&` derrière un `AddEffect` REFUSÉ — elle **NE TOMBE
    PAS** (décompilé + live). Le confond est levé en DÉPLOYANT le camp joueur au contact : `Pinned`
    refusé ET override d'Attack + attaque libre exécutés (10038 → 7442 HP). Le port était conforme,
    le commentaire d'`operations/effects.py` était faux. Cf. `case-n5-chain-after-refused-addeffect.md`.
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
- ~~**`test_skitarii_turn_live::test_skitarii_played_by_generic_ai_pass` echoue**~~ -> **FERME le
  2026-07-27** (`case-r5-skitarii-turn.md`). Cause racine UNIQUE pour les deux anomalies : le gate
  d'expansion `IdunBattle.Entities.Pathfinding.BasePathfinder$$NodesInNextLevel` ->
  `IdunBattle.Entities.Pathfinding.WalkPathfinder$$IsValidContinuePathTile` (bit 0x1 = effet de tuile
  `BlockEnteringUnitsTileEffect`, pose sur les Swamp) n'etait pas porte : la flood-fill offline
  traversait les marecages et la passe IA choisissait une tuile de deplacement ILLEGALE ((6,5)), a
  portee du SEUL ennemi 79 -- d'ou `d_bfs 3->3` ET `hp 8536->8536` sur l'ennemi mesure. Oracle natif
  fabrique pour l'occasion (Vanguard REEL invoque live par `ControlEdict`, joue seul au turn-start) :
  natif = move (4,7), cible 77 -- **le test avait raison**. L'indice `ability: 17` est REFUTE comme
  cause (l'id concret est 69 `Loki_NormalAttack` pour le Marshall ET le Vanguard, mais aucun etage de
  la voie normale offline ne le consomme). Agrement `aiMovableTiles` sur 5 boards, 0 ecart.
- **`snapshot.load_state` ne pose JAMAIS `ai_controlled` -> `run_ai_control_pass` est un no-op
  silencieux sur tout etat charge du LIVE** (mesure 2026-07-27, `probe_r5b_vanguard_native.py`) : un
  Skitarii Vanguard REEL (invoque live par `ControlEdict`, entite u104, trait `Summon`) recharge par
  `load_state` rend `UnitComponent.ai_controlled = False` et `collect_ai_controlled(player) == []`.
  Seul le spawn OFFLINE (`operations/spawn._spawn_config_grot`) pose le flag -- donc la passe
  AI-control ne s'exerce QUE sur des summons fabriques offline, jamais sur ceux d'une bataille
  chargee. Source du flag cote natif : trait `Summon` (2) / `Unit_IsSummoned` de la cascade de spawn.
  Fichier : `engine/runner/snapshot.py`. `[opus]`.
- **Arbitrage de TUILE de la passe IA : elevation sur-valorisee quand la tuile est ADJACENTE a un
  second ennemi** (residu R5-a, `case-r5-skitarii-turn.md` §8) : geometrie MC1_67, Vanguard (3,7),
  ennemis (6,8)+(6,7) -> natif choisit (4,7) (plat, u_full port 24.10), le port choisit (6,6)
  (elevation 2 : degat predit x1.5 ET +15 d'utilite de tuile, u_full 48.64). CONTRE-MESURE le meme
  jour : sur une geometrie ou la tuile elevee n'est PAS adjacente a un second ennemi, port et natif
  choisissent la MEME tuile (3,6) -> suspecter un terme de MENACE dans
  `CalculateUtilityFromTilePrediction`, pas le bonus d'elevation lui-meme. `[opus]`.

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
  gap ; non corrigé faute de mesure live sur CE vecteur. **VERROU RE-VÉRIFIÉ 2026-07-28 : RÉEL** — les
  effets gatés `target_traits` sont **5** (les 4 ci-dessus + `DestroyTheWitch`) ; `execute_normal_like`
  n'a que 2 routes live (splash Psyker / on-appearance d'un summon) et **aucun `lineup` n'est à la fois
  Psyker et porteur d'un des 5**, ni aucun summon du pool (un summon ne porte que SES propres traits
  dérivés). Le porter serait spéculatif. ⚠ **La phrase « Même remarque pour `additional_hits` » était
  FAUSSE** : `execute_additional_hits` ne construit pas de mods, il reçoit ceux de
  `execute`/`execute_ability_attack`, qui threadent tous deux `target_traits`. `[opus]`.
- ~~**Matérialisation finale : `execute_normal_like` et `additional_hits` restent TRONQUANTS**~~
  **FERMÉ 2026-07-28 (R6)** — les deux vecteurs ARRONDISSENT désormais, comme les deux autres. Ce
  n'étaient pas trois lois mais UNE : les deux voies natives de coups additionnels et
  `execute_normal_like` retombent toutes sur `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`,
  donc sur le slot 0x10 `CalculateBaseDamageWithModifiers` = `Round(AwayFromZero)`. Mesures :
  `normal_like` **30/30** arrondi (0/30 troncature) + témoin branche-armure 12/12 ; `additional_hits`
  **14/14** arrondi (10/14 troncature). Le prérequis « branche perçage gagnante » a exigé un levier
  NEUF, `rl_duel build --armor-target`. Détail :
  `docs/rl/case-r6-materialisation-normal-like-additional-hits.md`.
  - **RÉSIDUS NEUFS chiffrés par cette mesure**, tous deux hors périmètre R6 :
    **R6-b** ordre du canal `additional_hits` pour un groupe `predefined` (natif =
    roll-then-reduce 2 tirages/coup, port = reduce-then-roll 1 tirage/coup ; 1ᵉʳ coup reproduit
    **11/11** par l'ordre natif et **0/11** par le port) — c'est #202-B, désormais chiffré ; et
    **R6-c** bornes COMBAT des groupes `amount` (natif = `RandomAmount(minDmg,maxDmg)`, port =
    `amount ± 20 %` ; groupe live `[267,277,243]` **au-dessus** de la borne haute du port, mesuré sur
    `tauCrisis`/`CyclicIonBlaster`). Cf. `port-residuals-inventory.md` §4.a. `[opus]`.
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
- ~~**Nœud `DSLFactory$$PerformAIAttack` : un corps câblé à la main subsiste**~~ — **RÉSOLU
  (2026-07-27)**. `SpawnReplica` (ScarabSummon 1047) délègue au corps unique, désormais nommé
  `perform_ai_ability_unit_behaviour` (homonyme de `PerformAIAbilityUnitBehaviour$$Execute`) et atteint
  par les DEUX constructeurs `DSLFactory` (`perform_ai_attack_from_current_position` /
  `perform_ai_attack`). **Correction de RE** au passage : les deux nœuds diffèrent sur DEUX champs, pas
  un — `+0x70 allowMoveAction` (0 vs 1) et `+0x78 moveAmount` (`Direct(0)` vs **`null`**) ; le littéral
  `1` de `PerformAIAttack(1)` est le BOOL, pas un budget de 1. La feuille DSL `PerformAIAttack` porte
  désormais les deux champs, ce qui a révélé un **second** call-site mal routé, corrigé au passage :
  `ForwardSpotter` (1143) mirrore le nœud `PerformAIAttack`, pas `...FromCurrentPosition` (delta
  observable nul, fix de label). Mesuré (`probe_r20_replica_rng_flow.py`) :
  hors portée 1 attaque / 4860 dégâts / 6 tirages MT → **0 attaque / 1 tirage** ; au contact
  `after_hit=False` / 6 tirages → **`after_hit=True` / 12 tirages, dégât identique 4860**. Détail :
  `case-217-thequickening` §7. **RESTE OUVERT (résidu nommé)** : `move_amount is None` ne fait pas
  bouger l'acteur — ni `ABaseAiUnitTactic$$GenerateActionTiles` ni le `MovementActionGenerator`
  (`DefaultAiUnitTactic$$.ctor`, `tactic+0x58`) ne sont portés, donc un double hors portée ne fait RIEN
  là où le natif l'aurait fait avancer puis frapper (i2 « takes a turn »). Manque-à-agir, jamais une
  attaque illégale. `[opus]`.
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

- **Deplacement MULTI-HEX non confrontable** (`case-R30-multihex-substrate.md` SS6.4) — le substrat
  d'empreinte est pose et valide live (empreinte, ancre, occupance, portee), et les POSITIONS
  legales d'une unite a N pieds sont portees
  (`engine/services/movement_query.py::get_movable_positions_from_tiles`, mirror de
  `IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFromTiles` + `$$IsValidUnitFeetList`).
  Mais `MoveUnitOperation` ne deplace toujours qu'UNE tuile, et le seul porteur multi-hex du build
  (`ultraSmnDreadnought`, spawne par `DutyEternal`/`AetherStride`) a `Movement = 0` — donc AUCUN
  scenario live ne peut confronter le move a N pieds. Le canal existe pourtant deja cote hooks
  (`MoveUnitMessage.UnitFeetPositions`, `buildMoveMsg` accepte un footprint). A rouvrir des qu'un
  porteur multi-hex MOBILE apparait ; d'ici la, porter le move serait speculatif. `[opus]`.
- ~~**#175 — `test_storm_speeder_live` (2 tests) ROUGE — HARNAIS-1, pas le moteur**~~ — **PERIME,
  re-mesure du 2026-07-28 : 2 passed / 13,0 s, sans AUCUNE modification.** Ces deux tests
  snapshottaient bien le runner de MESURE et etaient donc rouges par le poison lui-meme ; le
  correctif #175 (`c6ccd44` — la Machine en CIBLE de `GetNormalAttackPrediction`) les a liberes
  **sans que personne les rejoue**. Le remede que cette entree recommandait (la parade jumelle
  `_twin_snapshot`) a au contraire ete **RETIRE** de ses quatre porteurs, la cause native etant
  fermee : `case-162-mow-red-suites.md` §7.
- **Trois suites ecrivent encore leurs state-files sous `data/` (VERSIONNE)** —
  `test_alpha_warrior_live`, `test_harbinger_of_destruction_live`, `test_martial_apotheosis_live` :
  chaque passe laisse une entree `??` dans `git status`, ce qui neutralise le garde-fou « rien de
  produit par un run ne va dans `data/` ». Migration `ROOT / "data"` -> `ROOT / "logs"` (une ligne
  par fichier), deja faite pour les cinq suites MoW (#162, #174). `[opus]`.
- **Empreinte a 7 pieds = code MORT dans `gqfc5mff6c`** (`case-R30-multihex-substrate.md` SS6.2) —
  l'enum `TargetingRule` declare `CasterHas7Tiles`/`TargetHas7Tiles`, et `IsValidUnitFeetList` /
  `GetPossibleTileListsFromMovableTiles` / `DislikeStartingTilesUtility` portent tous une branche 7,
  mais les XREFS de `DSLFactory$$ThreeTileUnitSpawnShape` sont EXHAUSTIVES (DutyEternal +
  AetherStride) et il n'existe AUCUN producteur d'empreinte a 7. Les branches sont portees fidele
  mais inexercables ; le seul point non resolu est le resolveur de CENTRE
  (`<IBattleQuery slot 0x5d>(tiles)`, symbole non nomme) — le port applique la definition
  geometrique que la branche impose ensuite. A rouvrir si un build introduit un porteur 7. `[opus]`.
