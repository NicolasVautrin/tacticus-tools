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
| ~~#391~~ | ~~**Trois `conftest.py`, aucun `__init__.py` : selon l'ordre de collecte l'un écrasait l'autre**~~ | **LIVRÉ (2026-08-01)** | `case-391-conftest-dir-identity.md`. **Le diagnostic d'origine était FAUX sur la cause** : `--import-mode=importlib` est dans `pytest.ini` depuis son commit d'origine, les trois conftest sont chargés sous des noms **distincts** (`tests.conftest`, `tests.engine.conftest`, `tests.engine.runner.conftest`) — **aucune collision `sys.modules`**. Le vrai mécanisme est un défaut pytest 9.1.1 en **trois étages**, tous lus dans le pytest installé : (1) `Session.collect` pose `handle_dupes = False` quand la dernière part est un FICHIER et **re-collecte le `Directory` PARENT**, recréant ses sous-`Directory` ; (2) `FixtureManager.pytest_make_collect_report` attache les fixtures d'un conftest via un `_pending_conftests.pop()` **destructif** — seul le PREMIER objet les reçoit ; (3) `_matchfactories` décide la visibilité par **identité d'objet** (`fixturedef.node in parent_nodes`), plus par préfixe de nodeid. Les deux objets portant le **même nodeid**, le défaut est invisible à toute inspection par chaîne (mesuré : `Dir(tests/engine/runner)#…420448` puis `#…345904`). Candidat `__init__.py` **réfuté par mesure** : les `Dir` deviennent des `Package` et le doublon persiste à l'identique. Correctif = `scripts/python/conftest.py` (canonisation des collecteurs `Directory`) — ne touche ni à la déduplication des fichiers, ni à l'ordre d'exécution, ni aux scopes. **Portée réelle plus large que le cas rapporté** : 3 couples `(D, S)` porteurs du motif, dont `tests ← tests/engine`, les trois rouges avant. Reproducteur `18 passed, 4 errors` → **`22 passed, 0 error`** ; échantillon 3 niveaux de conftest `54 passed, 4 errors` → **`58 passed, 0 error`**. Gardes : `probe_391_conftest_dir_identity.py` (rc 1 → 0) et `tests/test_391_conftest_dir_identity_offline.py` (1 failed → 1 passed). |
| ~~#380~~ | ~~**`refresh_ability_configs` écrasait en silence tout patch de seed BC — combien d'AUTRES fixtures ont mesuré du nominal ?**~~ | **LIVRÉ (2026-07-31)** | `case-380-recensement-patchs-seed-bc.md`. Recenseur `probe_380_seed_bc_patch_survival.py` (balayage AST + différentiel à **3 termes** custom/base/gameconfig — avec 2 on ne distingue pas la dérive de CAPTURE #254, légitime, du patch de FIXTURE + `--measure` qui PRODUIT réellement les 9 producteurs offline). **75 modules** touchent un seed BC, **69** n'écrivent que hors champ. Résultat : **0 patch de VALEUR écrasé** aujourd'hui (#369 est épinglée depuis #396) — mais **1 fixture cassée sur un axe que #375 n'avait pas nommé** : la 2ᵉ boucle du rattrapage **POSE** toute config qu'une entrée `Units` réclame au gameconfig, donc le bras A de `probe_226_seed_bc_ability_configs` (dont le POINT est l'ABSENCE de config) repartait du chargeur AVEC `SavageEchoes`+`RedRampage`. Mesuré live : A rendait `ok=True errors=[]`, **indiscernable de ses deux témoins** — un re-jeu se serait lu comme une RÉFUTATION de #226. Verdict #226 intact (mesuré 18 h AVANT le rattrapage) ; c'est la reproductibilité qui était perdue. Parade symétrique `withheldAbilityConfigs` (même sidecar, opt-in, **lève** si elle ne retient rien) ; après correctif, live : A `ok=False errors=['system error']` / B,C `ok=True hits=[3825, 3598, 3975, 3445]`. **Résidu nommé → `#380-r1`.** |
| #380-r1 | **`BC.Utilities` est écrasé EN ENTIER et n'a AUCUN mécanisme d'épinglage — piège armé, sans victime** | `[opus]` | `case-380-recensement-patchs-seed-bc.md` §1 (surface 2) et §5. `catalog_inject.refresh_ai_utilities` fait `bc["Utilities"] = new` sans condition dès que le gameconfig porte `aiUtilities` : **toute** fixture qui patcherait un poids d'utilité IA dans un seed BC custom mesurerait du nominal, exactement comme #369. **Mesuré : 0 fixture ne le fait aujourd'hui** (`bc["Utilities"] =` n'a que 2 sites, tous deux dans le rattrapage lui-même et dans le probe de garde) — c'est pourquoi rien n'est livré : un `pinnedUtilities` sans client serait du code spéculatif. Ce qui EXISTE déjà : `probe_380 --check <bc>` rougit sur ce cas (`utilities.state == "OVERWRITTEN"`) et `assert_survives()` lève. **À livrer le jour où une fixture en a besoin**, pas avant ; le montage est le même que #375 (clé nommée dans `<seed-bc>.pins.json`, lue par `_load_seed_bc`, orpheline ⇒ lève). |
| ~~#383~~ | ~~**`1059 RammingSpeed` : porter les batchs 3/4 (EXPLOSION) du playbook**~~ | **LIVRE (2026-07-31)** | `case-383-ramming-speed-explosion-port.md`. Le verrou de `#353-r1` volet (b) etait un ARTEFACT DE MONTAGE (#381) ; le PORT suit. Livre : la gate `!self.Any(p => p.Prediction.WillBeKill)` (mirror de `DamagePredictionResult$$get_WillBeKill` sur l'event du caster), `ExplodesAbility$$GetDamage` en arbre DSL, la tuile (`GetTileToMoveTo` sur substrat `Scene` -- MEME mirror que la face COMBAT), les deux selecteurs `Friends`/`Enemies(AdjacentUnits(tile,1,3))`, l'etage degat a **1 coup** (le slot `0x24` d'`IBattleQuery` est `GetAttackPrediction` = le 1er coup de `GetMultiHitAttackPrediction`) en profil `DirectDamage`, et `friendly` PAR BATCH. Trois pieces d'infra nees du fait que `make_damage_predictions` ne recoit que la `Scene` : `scene_tile_leaf_ctx` (3e jumeau), `SceneTileState`, `FixedTile`. **CONFRONTE 4/4 couples (board, seed)** -- `MC1_67`/38300 (dont un bras caster BLESSE 30/60), `C1_03`/38401, `C1_20`/38603, `MC1_63`/38704 -- 5 events == 5, event pour event ; **5 gardes adversariales ROUGES** (`no-explosion`, `friends-only`, `enemies-only`, `hp-current`, `tile-utility-only`). **BUG DE PORT TROUVE PAR LA GENERALISATION** : la base est le maxPV (`StatAmount(Owner, Health, part = 2)`) et le port lisait le COURANT -- `UnitContext.get_stat(5, 2)` retombe sur `StatComponent.get_CurrentValue` parce que `seed_unit_stats` seede `Health` en `StatComponent` GENERIQUE ; le canal du maxPV cote `Scene` est `hpmax_by_id`. L'axe etait INOBSERVABLE tant que `--hp-player` posait `Health` ET `RemainingHealth` (natif `[18,27]` contre port fautif `[9,15]`). **Rectification de `case-361` sec.7** : `DSLSelectors$$Friends`/`$$Enemies` allouent `UnitsByTeamSelector` (`IsFriend`), pas `UnitsFromFactionSelector` (`HasFaction`) -- les deux `.ctor` sont DEDUPLIQUES, le nom lu etait celui de l'autre classe ; le port etait deja juste. Gardes : `tests/engine/test_383_ramming_speed_explosion_offline.py` (14) et `..._live.py` (4), probe `probe_383_ramming_speed_explosion_port.py`. **Residu -> `#383-r1`** ; et `#381-r1` MORD (2e mesure independante, `case-383` sec.5). |
| ~~#383-r1~~ | ~~**La face COMBAT de `1059` reste hors `ABILITY_CLASSES` -- un noeud du `ExecuteBehaviour` n'est nomme nulle part**~~ | **LIVRE (2026-08-01, #389)** | `case-389-ramming-speed-combat.md`. `<DSLTriggers+0x20>` = **`IdunBattle.Entities.Triggers.OwnerIsAliveAbilityTrigger`** (la propriete DSL `OwnerIsAlive`, SANS operande), nomme par TROIS sources : gabarit de classe (taille 24, parent `AbilityTrigger` -> 23 candidates), **TYPE du champ** (`dsl.state` = MatchState, ce qui ecarte les 21 candidates allouees avec un SELECTEUR par un `DSLTriggers$$X` nomme et laisse exactement les DEUX qu'`InitializeShared` alloue -- l'appariement `<+0x18>` = BattleQuery = `IsMeleePositionAbilityTrigger` / `<+0x20>` = MatchState = `OwnerIsAliveAbilityTrigger` est FORCE), et le corps trivial `DSLTriggers$$IsRangedPosition = op_LogicalNot(<+0x18>)` qui nomme le JUMEAU independamment. 1059 entre au registre AVEC `TARGETING_OPTIONS` (`0x4002` + `RANGE_FROM_CONFIG` + `RangedBool.False`), `ABILITY_ATTACK_TYPE` (0 `DirectTargetAttack`) et l'override `GetDynamicInvalidTargetReason` (4 branches). CONFRONTE LIVE **5/5 bras** (MC1_67 x2, C1_20, MC1_63, C1_03) sur 5 observables dont les PV finaux, coups **bit-exacts** ; **7 gardes adversariales ROUGES**. Effet de bord : le meme noeud gatait deja `sky_strike_tree`, ou le port avait ecrit `IsAlive(caster) & IsAlive(target)` -- **conjoint INVENTE, corrige**. La branche VRAIE du `ConditionalAmount` d'`ExplodesAbility$$GetDamage` est desormais confrontee LIVE (bras lethal : le contrecoup tue le caster `Explodes`, la nova rend 75 % du maxPV = 25 + 50). Suite : `#389-r1`. |
| #389-r1 | **L'effet `1098 RammingSpeed_ExtraExplode` est POSE puis RETIRE dans le meme `applyAction` -- le port le laisse** | `[opus]` | `case-389-ramming-speed-combat.md` sec.5. MESURE (tags `captureEvents` du cast natif) : l'entite-effet est creee (`Effect_SourceActiveAbility = 1059`, `Effect_SourceId = <caster>`, `Effect_CurrentLevel = 1`) puis retiree avant la fin du meme `applyAction` -- apres le cast, `decisionView` canal `includeInactive` ne la liste plus. Le port la conserve (duree DEFAUT -> `remaining = 0` = PERMANENT, cf. `AddEffectOperation`). Le mecanisme de retrait n'est PAS RE : ce n'est ni la duree passee (options ZERO = aucun override, lu au decompile) ni un refus de pose (l'evenement de creation existe). Piste : `RammingSpeed_ExtraExplodeEffect$$.ctor` -> `BaseEffect..ctor(this, &abilityOrEffect, hasAutomaticActivation = 1)`, et le couple d'evenements `step 16` / `step 18` emis sur l'effet en fin de cast (le MEME couple que sur `PowerTrip_FullHealth`, qui lui SURVIT en `active: false`). INERTE sur les 5 bras joues (la nova lit l'effet AVANT le retrait) ; mord des qu'un consommateur lira 1098 apres le cast. ⚠ Piege de CANAL a re-lire avant toute mesure : `decisionView` par DEFAUT laisse tomber les effets INERTES, seul `snapshot.decision_view_seed_body` (`includeInactive`) est comparable a `State.effects.by_unit`. |
| ~~#377~~ | ~~**Un `runnerId` est-il RÉATTRIBUABLE ? Si oui, un agent peut polluer le runner d'un autre en silence**~~ | **FERMÉ SANS CORRECTIF (2026-07-31)** | `case-377-runnerid-monotone.md`. Réponse lue au **code d'allocation** (`frida/hooks/game/runner-registry.ts`), pas en live : `let counter = 0` + `runnerId: ++counter`, `disposeRunner` ne fait que `byId.delete` — **aucune free-list, aucun décrément, `byId` non exporté**. Le compteur est strictement monotone par session ⇒ un id disposé n'est **jamais** repris, et l'incident d'origine (4 `endturn`/`aiturn` sur `--runner 261` après dispose) est BÉNIN : ces tours ont été **refusés** (`runner 261 not found`), pas exécutés ailleurs. Refus franc = passage obligé : **31/31** sites de garde `runnerId` dans `frida/hooks/**` passent par `getRunner` (les 2 exceptions vident des buckets de TRACES, pas des runners). Live (session 3) : `145`, `146`, dispose(145), build → **`147`** ; `battleStatus(145)` → `{ok:false,"runner 145 not found"}`. Cliquet `probe_377_runnerid_reuse.py` (I1..I5) + `tests/test_377_runnerid_monotone_offline.py` (**6 mutations, 6 rouges**). **Résidu nommé → `#377-r1`.** |
| ~~#377-r1~~ | ~~**La monotonie vaut PAR SESSION : un state-file survit a un reinject, `counter` non**~~ | **FERME (#379)** | `case-379-state-file-session-stamp.md`. Le FICHIER est prive (`logs/` du worktree, chemin absolu = cle `owner`) ; c'est l'ESPACE D'IDS qui est PARTAGE -- un seul registre, dans le script injecte, commun a tous les appelants RPC. Une (re)injection remet son compteur a `0` pendant que les state-files survivent sur disque. `scripts/python/runner_state.py` estampe le triplet `/api/admin/status` (`id`+`pid`+`startedAt` -- l'id seul ne suffit pas : `nextSessionId` est un etat du HOST, qu'un restart remet a `1`) au `build` et le reconfronte au pilotage, **TRI-ETAT** : `MATCH` passe en silence / `MISMATCH` **REFUS rc 2** / `UNSTAMPED_STALE` (pas d'estampille mais mtime anterieur au `startedAt` -- l'anteriorite PROUVE la divergence) **REFUS rc 2** / `UNSTAMPED` **avertit sans bloquer** (un agent qui a build avant la garde puis rebase mi-run pilote un runner valide, et ce chemin porte tous les tests live). Cable en G1..G4 dans `rl_duel.py` (`_save_state` estampe / `_load_state` sort en rc 2 / le `disposeRunner` de `cmd_build` n'agit que sur verdict `.ok` / `cmd_attach` confronte son `--from`) ; cliquets `probe_379_state_file_session_stamp.py` + `test_379_state_file_session_stamp_offline.py` (6 mutations, plus « fichier introuvable => on le DIT »). **#377 citait le mauvais chiffre** (« 332, au-dela du 261 ») : ce sont les **PETITS** numeros le danger, les ids etant croissants -- `runnerId=2` est passe de libre a « appartient au pytest d'un autre agent » en moins de dix minutes, sur une **vraie fenetre de reinject traversee et mesuree** (`case-379` §7). **RESTENT OUVERTS, distincts** : aucun controle d'`owner` sur les RPC de pilotage (cross-drive volontaire), et le `--runner` litteral des probes ne passe par aucun state-file. |
| ~~#371~~ | ~~**#366-G1 — les 11 instances génériques `StaticStatModifierEffect` : l'enjeu est l'EXPIRATION, pas le calcul**~~ | **LIVRÉ (2026-07-31)** | `case-371-g1-static-stat-modifier.md`. Table RE complète des 11 (poseur, stat, montant, `turns`). **UN SEUL des onze porte un vrai timer** — `1171 SereneUnifierStormOfFire` (`SereneUnifierAbility$$CreateBehaviour` branche `k = 0` du cycle `Modulo(PlayerTurnsStarted, 3)`, `TurnsFromRounds(1)`), et c'est lui qui portait le bug de durée : sans inscription, le +extraDmg d'ATTACK **collait à vie**. Mesuré live sur `tauAunShi`, deux couples (seed, board) : ATTACK 2101 → **1304 live == 1304 moteur** (delta 797 = `extraDmg[L50]` 443 × 180 %, résidu opaque **0**) ; bras NON INSCRIT rejoué sur la MÊME capture : 2101 → **2101**. `1251/1256 UnbreakableDuty_*` (`templAncient`) sont **PERMANENTS** (`turns` NULL) : leur inscription ferme l'ATTRIBUTION, pas une durée — `statDelta` natif après cast = **1996** / **9970** == `extraDmg`/`extraHp[L50] × 180 %`, ce qui valide **non circulairement** l'index `ConfigVar(0x1e) = extraHp` tranché par élimination. **8 non inscrits, chacun avec sa raison** : `1004/1005/1006 MightOfHeroes_*` DEAD (ability absente du gameconfig → magnitude irrésoluble, un port serait inerte — garde `test_might_of_heroes_stays_dead`), `1103 KanOpener_ReduceArmor` 0 porteur (résidu nommé de `factory.py` FERMÉ : les deux noms y sont écrits avec la RE), `1351/1352/1507 EnvStatBoost_*` environnement **et** magnitude CONTEXTUELLE (`PercentageOf(StatAmount(<stat>, part 3), GetNumberConstant(<clé>))` = forme OVERRIDE), `31 StatModifier` **TRANCHÉ : PERSONNE ne le pose** — les 6 chemins de pose inventoriés par xrefs (les 2 non-littéraux éliminés : `APowerUpAbility` porte 0x473/0x475/0x477) ET, sur tout le binaire, `(void *)0x1f,` n'apparaît que dans **5 fonctions sur 65 000**, aucune n'étant une pose d'effet (`On(0x1f)` = TriggerEvent, `AtomicGroup(0x1f)` ×2, 2 classes d'effet de tuile) ; `&DAT_0000001f` = 0 occurrence ⇒ **registered-but-dead**, rien à porter. |
| ~~#366-r1-src~~ | ~~**Le niveau d'ability d'un effet est lu sur le PORTEUR, alors que le natif le BAKE depuis la SOURCE**~~ | **LIVRE (2026-07-31)** | `case-382-effect-source-ability-state.md`. Le BAKE est relu au desassemblage : `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultEffectBuilder(id, abilityState)` COPIE les **0x24 octets** de l'`AbilityStateReference` dans `EffectComponent[+0x18..+0x38]` **a la POSE** ; `AddNewEffect` n'y touche jamais (il ne pose que `SourceUnitId@+0x10`, `OwnerId@+0x14`, duree) ; `BaseEffect$$GetAbilityStateReference` et `AbilityStateFromEffectSelector$$Select` relisent ce MEME `+0x18`. Foyer du port : `engine.entities.effects_state.baked_ability_state`, alimente par les DEUX seams (COMBAT `runner/snapshot.py` passe 1 `abstate_by_id`, incluant les MoW par `_machine_ability_state` ; PREDICTION `playbook/scene.py::_effect_source_ability_states`). **Repli = le PORTEUR**, jamais un neutre -> le changement ne mord QUE si la source est resolvable ET differente : tous les appelants historiques de `EffectsState.seed` (forme a 3 arguments) gardent leur semantique. Mesure MC1_67/777, Ragnar `PassiveAbilityLevel=1` / Ulf 50 : natif n=4, port **n=4** (avant : n=6) ; instance 1224 `ability_level=1 multiplier=200` (avant `50`/`180`). Recensement : **81/138** entrees d'`EFFECT_CLASSES` sensibles au canal (`--scan`) ; balayage live de 6 rosters d'aura + 6 activations IA -> **83 instances, source renseignee 83/83, 2 cross-unite** (une AURA vit sur son porteur-source et projette par selecteur — ce n'est PAS un effet pose sur le beneficiaire). Gardes : `test_effect_source_ability_state_live.py` (8 tests ; sous mutation **6 failed / 2 passed**). NON COUVERT : decompile exhaustif des 135 `CreateBehaviour`, face CRIT en degat (couverte structurellement par le multiplicateur), `active_ability_level` du PORTEUR toujours `None` dans `seed`. **Second foyer, mesure par #405 (`1222`)** : `IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel` (foyer UNIQUE des quatre accesseurs) lit sur son argument `abilityState` **l'index** (`Level$$ToZeroBasedIndex`, `+0x0`) **ET le multiplicateur de rarete** (`Fix64(abilityState+0x4)/100`, `Round(AwayFromZero)`, pour `variablesAffectedByRarityBonus` = `config+0x28`) -- c'est ce qui rend le multiplicateur solidaire du bake, et non un attribut du porteur. |
| #366-r1 | **28 `EffectType` VIVANTS, porteur confrontable — 20 INSCRITS, 8 RESTANTS** (re-dérivé du code le 2026-08-01, après merge de #408→#421). ⚠ **Le critère est l'UNION des DEUX faces** : `EffectFactory.registry` (DÉCISION, par NOM — passer par `enum_maps.EFFECT_TYPE`) **OU** `EFFECT_TRIGGERS` (COMBAT, par id). Croiser le seul registre est **AVEUGLE** : témoins mesurés, `1284` (porté et confronté live par #410) et `1186 TimeFlux_Revive` (porté depuis #213) n'existent QUE dans `EFFECT_TRIGGERS` — l'ancien critère les comptait « restants ». ⚠ **Ne jamais recopier ce nombre, ni le re-dériver depuis un worktree** : deux PR livrées en parallèle écrivent chacune une valeur juste à SA base et fausse après merge — c'est arrivé DEUX fois (#372/#373, puis #404/#405), la seconde alors que les deux briefs portaient l'avertissement. Le seul point où il peut être juste est **APRÈS le merge, côté orchestrateur**. **Inscrits** : `1107` (#373), `1171`/`1251`/`1256` (#371), `1183` + jumeaux drone `1306`/`1307` (#372), `1345`/`1346`, puis par tâches filles `1181` (#404), `1222` (#405), `1224` (#406), `1110` (#408), `1175` (#409), `1284` (#410), `1115` (#411), `1116` (#414), `1215` (#416), `1014` (#418), `1111` (#417), `1435` (#420), `1174` (#421). **Restants, par porteur** : `thousAhriman` (`1216`), `eldarMauganRa` (`1117`), `ultraInceptorSgt` (`1000`), `templChampion` (`1255`) — **4 au pool** ; `tyranSmnWarrior` ×2 (`1108`, `1109`), `necroSmnDestroyer` (`1113`), `eldarSmnHarlequin` (`1227`) — **4 par voie SUMMON**. **Une tâche fille par ability**, jamais en lot. | `[opus]` | `case-366-gisement-96-effets.md` §3.3 (table : id, contribution de la classe, porteur, voie — ⚠ ses marques « PORTE » sont incomplètes, seul le croisement code fait foi). Inventaire des 96 : `python scripts/python/probe_366_inventaire_effets_forme_b.py --csv`. Résidu FERMÉ sans port : le `# KanOpener` de `entities/effects/factory.py` = `1102 KanOpener_IgnoreArmor` + `1103 KanOpener_ReduceArmor`, **0 porteur** sur les 5 voies (§4). |
| #366-r1-turnof | **Le nœud `IsTurnOf` du port agrège par `any`, le natif par `all`** — `IdunBattle.Entities.Triggers.IsTurnOfUnitTrigger$$ShouldTrigger` (branche « sélecteur d'unités ») itère les entités sélectionnées et sort **FAUX dès qu'UNE** n'appartient pas au joueur courant (set vide → VRAI) ; `engine/entities/triggers.py::IsTurnOf.should_trigger` fait `any(...)`. Sans effet sur les call-sites actuels (`Owner` / `Self` sont des singletons) ; l'écart s'ouvre dès qu'un sélecteur multi-entités est passé — le plus proche est `IdunBattle.Entities.Effects.FirstAidHealEffect$$CreateTargetTrigger` = `On(0x13) & IsTurnOf(Units(tile))`, dont la voie portée est impérative (`runner/operations/triggers/tiles.py`) et déjà per-occupant, donc non exposée. | `[opus]` | Trouvé en marge de `case-366-r1-fire-and-reposition-reduce-dmg.md` §7. Fermer = mirror `all(...)` + un montage à **deux** unités sélectionnées d'équipes différentes (une tuile FirstAid occupée par les deux camps, `board.py` : `FirstAid` sur 25 boards). |
| #366-r1-camo-seed | **Un effet CONDITION-GATED absent de la capture ne se matérialise jamais offline, même quand la sim entre dans sa condition** — mesuré sur `1014 CamoCloak_DmgReduction` : son gate est le COUVERT (`HasEffect(Owner, 1013 LightCover) \| IsEffectTarget(Owner, 1026 BigTarget_Adjacent)`), donc un porteur capté HORS couvert n'a **aucune** instance dans `decisionView.effects` (canal actif-only) ; s'il marche ensuite sur une `DryBush` en sim offline, le port reste muet là où le natif rallume. Le gate lui-même est porté et confronté (`is_active`, 6 mutations rouges) — c'est le SEED qui manque, et le mécanisme existe déjà (`factory.ABILITY_INIT_OWNER_EFFECTS` + `BaseEffect.seed_witness_effect` + `active_condition_ported = True`, cf. `ModifiedExoarmour_ExtraDmg`). Rien de mesuré ne l'exigeait ici : les trois régimes de couvert sont capturés APRÈS mise en place. **Portée > 1014** : tout effet dont la `CreateActiveCondition` dépend d'un état que la sim peut CHANGER est dans le même cas. | `[opus]` | `case-366-r1-camo-cloak-dmg-reduction.md` §8. Fermer = poser le témoin (`CamoCloak_DmgReduction` n'a pas d'effet FRÈRE — le témoin devrait être le kit passif, ce qui rouvre le piège #264/#322 « le kit dit ce que l'unité POSSÈDE, pas ce que l'ENTITÉ porte »), puis un montage où le porteur DÉMARRE hors couvert et y entre. |
| #366-r1-chaos-friendly-fire | **`1435 PsychicStalk_FriendlyChaosExtraDamage` n'a AUCUN gate sur la CIBLE — le bonus s'appliquerait à un TIR FRATRICIDE** — `IdunBattle.Entities.Effects.Loki.PsychicStalk_FriendlyChaosExtraDamageEffect$$CreateEffectDamageBonusForAttack` = `ForAddition(AreFriends(Owner@0x30, Caster@0x48) & HasTrait(Caster@0x48, 0x7ea = Chaos) & GetTargetIsOnFireTileCondition() & GetAttackHasValidDamageProfileCondition(), ConfigVar(8 = extraDmg))` : **aucun `AreEnemies(Target, Owner)`**, contrairement à son voisin `1215`. Seule la TUILE de la cible est lue. L'i2 (« **Affected** attacks from friendly Chaos units… ») suggère l'héritage du « to enemies » de la phrase précédente, mais aucun nœud ne l'implémente. Le quirk est PORTÉ tel quel (décompilé = vérité) et **NON CONFRONTÉ live** : le montage ne joue pas d'attaque sur un allié. | `[opus]` | `case-366-r1-psychic-stalk-friendly-chaos.md` §7. Fermer = un montage où une unité Chaos amie d'Ahriman tire sur un ALLIÉ posté sur un hex en feu (le harnais sait déjà poser le feu par `PsychicStalk_ApplyFireTile` ; il manque un vecteur d'attaque alliée — friendly fire non exposé par `applyAction`). Même famille de non-couverture : `comparisonType = 0` (CurrentPlayer, branche de `UnitExtensions$$IsFriend`) n'est pas discriminé de `1` (OriginalPlayer) faute d'unité mind-controlled au montage. |
| #366-r1-crit-multihit | **L'étage CRIT diverge dès le 3ᵉ coup d'une salve — INDÉPENDANT de toute ability** | `[fable]` | Mesuré le 2026-08-01 en portant `1115` (PR #411), sur un porteur SANS rapport : `necroDestroyer`, live `[1641, 742, 962, 757, 864, 769]` contre port `[1641, 742, 1551, 1825, 1457, 1856]` — les DEUX premiers coups s'accordent, la suite non. Se reproduit **aussi en mêlée**, où `IsRangedAttack` ferme `1115` : ce n'est donc pas le canal de `1115`. **L'étage de BASE est sain** (mêlée `--crit 0,700` bit-exacte sur 5 coups) — l'écart est dans le FLUX de tirages. Lecture proposée, à confirmer au décompilé : le natif consomme **deux** tirages pour les deux premiers coups puis **un seul**, là où le port en consomme deux partout. C'est ce qui a imposé à #411 de confronter sur une salve d'UN coup — donc toute garde multi-coups à crit non nul est aujourd'hui **non confrontable**. ⚠ Ne pas fitter un scalaire : décomposer par étage (nombre de tirages, puis valeur), et exiger un SECOND couple discriminant. | `case-366-r1-inescapable-accuracy-crit-chance.md` § résidus. Reproducteur : la salve `necroDestroyer` ci-dessus, `--crit` non nul, comparer live vs offline coup par coup. **BORNÉ par #366-r1/1117 (2026-08-01)** : le résidu ne touche **PAS la cardinalité**. Salve PLEINE de 6 coups à crit ouvert — le COMPTE s'accorde live/offline sur deux couples (board, seed) alors que les valeurs se décalent dès la 3ᵉ cellule ; salves pleines de 4 et 5 coups à crit NUL — **bit-exactes jusqu'à la valeur**, donc l'étage de base reste sain au-delà du 3ᵉ coup. ⇒ l'écart est bien dans le FLUX DE TIRAGES du crit, et toute garde qui n'observe que le nombre de coups reste confrontable en multi-coups (c'est ce qui a permis à #366-r1/1117 de se passer du contournement « salve d'un coup »). Détail : `case-366-r1-inescapable-accuracy-override-hits.md` §7.3. |
| #420-r1 | **L'axe DEGAT de `DefenderOfTheGreaterGood` (`1182` / jumeau drone `1306`) n'est retenu par AUCUN test** -- et PR #420 vient d'y REVEILLER un gate. En threadant `damage_profile` jusqu'aux modifiers ATTAQUANT (`damage_ops/ability.py`, `normal_like.py`), elle rend enfin lisible le `!DamageProfileIs(0xd = Psychic)` de `IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraDmgEffect$$CreateDamageModifier`, jusque-la aveugle sur ces vecteurs. Le changement est RESTRICTIF (cle absente -> le gate laissait passer ; valeur threadee -> il bloque sur Psychic), donc il CORRIGE une sur-application -- mais rien ne le garde : balayage des tests, les seules occurrences de `DefenderOfTheGreaterGood` sont l'axe COUPS (`1183`, `test_dotgg_extra_hits_live.py`) et deux mentions en commentaire. Fermer = un montage T'au avec Shadowsun en aura et un allie attaquant en profil Psychic vs non-Psychic, confronte live des deux cotes de la bascule. | `[opus]` | Trouve en validant #420 (2026-08-01). Foyer : `entities/effects/loki/extra_damage_aura.py::DefenderOfTheGreaterGoodExtraDmgEffect.create_aura_attack_damage_bonus_for_ally`. |
| ~~#366-r1b~~ | ~~**`1111 WireweaveNet_CounterAttack` (`eldarRanger` << Calandis >>) NON PORTEE -- residu NOMME et CHIFFRE de #366-r1**~~ | **PORTE + CONFRONTE LIVE (2026-08-01)** | `case-366-r1b-wireweave-net-counterattack.md`. Riposte PRE-HIT (`On(0x2a = PreUnitAbility)`) portee par un EFFET (`CounterAttackEffect : PlayerTurnEffect`), armee par le TOUR (`turnsEnabled = 1` -> tour ENNEMI ; `activationFrequency = 2`) et **consommee au premier coup** (`& DeactivateEffect(effect)`, gate = stub `return 1`). Gate `IsNormalAttack` -- **PAS** `IsDirectTargetAttack` comme le voisin `MartialSuperiority`, qui est strictement plus large. LIVE `MC1_67`/777 : riposte **[1272, 1599]** (2 coups Piercing, bornes RAW 1197-1795), port **bit-exact des DEUX cotes** ; contre-epreuve et contrefactuel de tour font DISPARAITRE la riposte ; montage a DEUX attaquants -> **aucune** 2e riposte dans le meme tour. **11 mutations, 11 rouges.** Face DECISION portee aussi (`UtilityType.WireweaveNet_FirstAttack` = 55, **-30** ssi filet ARME), et son conjoint d'adjacence natif est **DEGENERE** (les deux operandes d'`IsAdjacentTo` sortent du meme champ ; `AreTilesAdjacent` court-circuite `tile1 == tile2 -> true`) -> CORRIGE la sur-lecture de `docs/rl/playbook/architecture.md`. **DEUX correctifs trouves par adversarialite** : (a) `refresh_stat_modifier_effects` ECRASAIT `EffectComponent.IsActive @+0x5c` avec le DEFAUT de `is_active()`, la ou le natif RENVOIE le flag courant quand il ne re-evalue pas (`RefreshEffectsOperation$$ShouldBeActive`) -> riposte fantome au 2e coup ; (b) l'entree `ABILITY_INIT_OWNER_EFFECTS['WireweaveNet']` (posee par analogie) cassait les DEUX gardes MELEE du voisin (live 23633 vs port 21840) parce que le seed lit le KIT gameconfig et non la MESURE (piege #312) -> RETIREE, cliquet INVERSE pose. | `[opus]` | Residus NOMMES : face DECISION non confrontee live (il faudrait faire jouer l'IA du camp d'en face) ; regime capture-pendant-le-tour-du-porteur non couvert ; `spawn._seed_ability_owner_effects` lit le kit gameconfig pour ses 15 entrees. |
| ~~#372~~ (#366-G3a) | ~~**`1183 DefenderOfTheGreaterGood_ExtraHits` + jumeaux drone `1306`/`1307` non portés** — l'axe DÉGÂT (`1182`) l'était, pas l'axe COUPS : le dégât par coup juste, le nombre de coups faux, la somme fausse sans qu'aucun test ne proteste.~~ | **FERMÉ (2026-07-31)** | `case-372-dotgg-extra-hits.md`. Le canal AURA de la formule de coups (`aura_hits_bonus_for_attack` + hook `create_aura_hits_bonus_for_attack`), supprimé en #204 faute d'alimenteur, est RÉOUVERT : `DefenderOfTheGreaterGood_ExtraHitsEffect$$CreateEffectHitsBonusForAttack` est un `EffectBonus.ForAddition`, donc un terme de `AttackHitsWithModifiersFormula$$Calculate` — pas un groupe #179. **Une seule classe native par axe**, paramétrée `isDrone@this+0x480` : `1182`/`1306` et `1183`/`1307`. Garde : `test_dotgg_extra_hits_live.py` (montage `_dotgg_aura_regime.py`). **Résidu NOMMÉ** : le lien `ParentComponent` (summoner) n'est capté par aucun RPC → la chance du jumeau DRONE est lue sur SES tours au lieu de ceux de Shadowsun, donc SOUS-ESTIMÉE (fidélité-safe). Point d'ancrage à exposer : `ParentComponent` id @+0x10 dans `combatSnapshot.units[]`. |
| #366-r1-blockhits-purgeresponse | **Le SECOND implémenteur natif de `BaseEffect$$BlockHitsReduction` n'est pas porté, et son trigger n'a PAS `get_OwnerIsCaster`** — `IdunBattle.Entities.Effects.Loki.PurgeResponseEffect$$CreateBlockHitReductionTrigger` = `TriggeringAbilityIs(<AbilityOrEffect>)`, seul autre implémenteur du canal dans le binaire (l'autre étant `1117`, porté par #366-r1/1117). Côté port, `entities.effects.block_hits_reduction_from_effects` ne balaie que les effets de l'**ATTAQUANT** — rendu exact du `get_OwnerIsCaster` de `1117`, mais qui rendrait `PurgeResponse` **invisible**. Le porter exige donc d'**élargir le balayage** (cible + auras), pas seulement d'ajouter une classe : c'est écrit dans la docstring de l'agrégateur pour que l'élargissement soit un geste explicite et non un oubli. Porteurs de `PurgeResponse` (`EffectType 1538`) : `votanNpc2Steeljack` (**npc**) et `votanSmnSteeljack` (**SUMMON**) ⇒ confrontable par la voie summon, en spawnant son summoner. Ability associée non portée : `PurgeResponse_ActiveOverwatchAbility` (`…$$CreateBehaviour` / `…$$CreateTrigger`). | `[opus]` | `case-366-r1-inescapable-accuracy-override-hits.md` §7.2. Fermer = lire le littéral d'`AbilityOrEffect` du `TriggeringAbilityIs`, élargir l'agrégateur, puis un montage summon où la cible du Steeljack porte une réduction de coups (`Parry`/`Camouflage`) et où l'ability déclenchante est castée. |
| #366-r1-bcpatch-invisible | **Un patch de variable d'ability posé dans le seed BC ne modifie QUE le natif : le port lit `gameconfig`** — donc dès que l'effet visé est PORTÉ, la fixture cesse d'être une neutralisation et devient une **désynchronisation**, qui fait diverger à coup sûr. Mesuré en portant `1116` (2026-08-01) : le montage de `1115` posait `InescapableAccuracy.extraCritDmg = 0`, ce qui rendait le jumeau inerte des deux côtés tant qu'il n'était pas porté, et l'aurait rendu FAUX de `997` points le lendemain. Corrigé sur place (défaut inversé, `--zero-crit-dmg` conservé en diagnostic), mais la forme est **générique** : toute fixture `write_variable_patched_seed_bc` porte cette péremption, et rien ne la signale. `probe_380` recense les 75 modules qui touchent un seed BC — il vérifie la SURVIE du patch côté natif, pas sa VISIBILITÉ côté port. Fermer = croiser les variables patchées avec les `ability_var(<ability>, <var>, …)` du moteur et rougir sur l'intersection. | `[opus]` | `case-366-r1-inescapable-accuracy-crit-damage.md` §7.3. Foyer côté port : `engine/entities/effects/magnitude.py::ability_var` (lit `gameconfig`, jamais le BC). |
| #273-r | **Deux entrées gitignorées restent des chemins locaux : `frida/assets/raw/Bundles` (repli d'assets) et le `frida/data/*` du frontend** | `[opus]` | `case-273-entrees-gitignorees.md` §6. (a) `build_asset_manifest.RAW` est resolu par `host_inputs` dans `_bundle_dir`, mais la constante `RAW = ROOT / …` subsiste et les appelants se contentent d'un `[warn] missing` — outillage one-shot, **aucun consommateur de mesure**, donc admis au cliquet `probe_273._ALLOWED` : à rendre fail-loud le jour où un manifest amputé coûte. ⚠ Cette ligne citait `frida/assets/raw` : ce chemin n'existait pas — c'était un **fragment** fabriqué par le balayage AST, retiré par #319 (`case-273` §7). La constante réelle est `RAW = ROOT / "frida" / "assets" / "raw" / "Bundles"`. (b) `scripts/node/verify_portraits.mjs` lit `frida/assets/public/*.json` en chemin RELATIF au cwd — hors périmètre du balayage AST (`scripts/python/**`) et non traité. (c) **Aucun** consommateur ne DEMANDE au host où il écrit : `aiTraceStoreStatus()` (`frida/host/ai-trace-store.ts`) porte le `dir` absolu mais n'est exposé par aucune route — l'ajouter donnerait une résolution *mesurée* au lieu d'*inférée*, au prix d'un rebuild + restart du host (proscrit aux agents). |
| ~~#268-a~~ | ~~**Le décodeur du struct de prédiction lit des offsets PÉRIMÉS depuis la migration de build** — `aiPredict` et `aiPlaybookPredict` rendent du garbage sur `rnca9r7q6c` : `totalDmg [1,100]` pour TOUT couple, `mightCrit = 25` (un `bool`), `probability = 0`, bornes RAW `[0,0]`.~~ | **FERMÉ (2026-07-31)** | Le correctif de décodeur (#276/#279) est EN VIGUEUR dans le bundle injecté — la ligne décrivait un état d'AVANT. **Le critère d'acceptation de cette ligne a été re-joué tel qu'écrit** : `tests/engine/runner/test_prevent_overkill_decision_live.py` = **4 passed** (la ligne annonçait « 4 failed, CANAL MORT »). Deux mesures indépendantes : `case-333-arrondi-minmax-avg.md` §8 (event natif `healthDmg [4812, 7224]`, `mightCrit 0`, `probability 1`, `appliedHits 6`) et le re-jeu de validation de PR #344 (`test_overkill_decision_live` + `test_prevent_overkill_decision_live` + `test_finaljustice_live` = 11 passed). ⚠ Ce que la fermeture NE dit PAS : les champs `TotalDamage` / `Armor` / `Shield` / `AppliedHits` n'ont jamais été dérivés au décompilé — ils sont justes en pratique, pas attestés. Détail conservé ci-dessous. — `case-268-decodeur-prediction-perime.md` §2bis/§2ter. La RE est **faite pour les champs du chemin overkill** : `DamagePredictionResult` = **176 o** ; `CurrentHealth@0x00`, `HealthDamage` (`MinMaxDamage` 16 o) **@0x14** donc `Min@0x1c`/`Max@0x20` (étaient `0x60`/`0x64`), `ShieldDamage@0x24`, `MightCrit@0x8a` (était `0xb1`), `ForceOverkill@0x8b`, `PreventOverkill@0x8c`, `List`s `@0x38`/`@0x80`, `int` agrégé `@0x98`. **Reste à dériver** : `TotalDamage`, `Armor`, `Shield`, `AppliedHits` — `Add` montre trois `MinMaxDamage` non attribués (`0x40`, `0x50`, `0x60`) ; les nommer demande de lire `GetAllPredictions` / `CalculateProbabilisticDamage*`. **6 fichiers, ~25 sites** portent les anciens offsets : `ai-step/rpc-predict.ts`, `ai-step/playbook-predict.ts`, `ai-step/rpc-snapshot.ts`, `ai-step/state.ts`, `ai-step/projection.ts`, `features/scorer-damage-trace.ts`. Critère d'acceptation : `tests/engine/runner/test_prevent_overkill_decision_live.py` = **4 passed** (aujourd'hui 4 failed, message « CANAL MORT (#268) »), et les sentinelles `probe_178_overkill_gate.prediction_channel_health` / `probe_195_prevent_overkill_decision.event_channel_health` rendent `alive=True`. ⛔ Ne pas dispatcher à un agent qui n'a pas le droit de réinjecter. |
| #277-r1 | **Le raccourci `<Ability>().execute_behaviour(...)` dans les probes/tests est un point d'entrée FAUX dès que le caster consomme `On(0x2b)`** — ~136 call-sites directs dans **71 fichiers** de `scripts/python` (comptés le 2026-07-30 : `grep -c '\.execute_behaviour('`). Le natif n'a qu'UN point d'entrée de cast (`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`) et il émet `On(0x2b = PreUnitAbility)` **avant** la behaviour ; côté port ce vecteur vit dans `AbilityHandler.visit_ActiveAbilityMessage`, donc **au-dessus** d'`execute_behaviour`. Entrer par la behaviour saute le vecteur — et avec lui tout ce que ses consommateurs font : **du RNG** (`HazeOfCorruption_TargetFinder` : `min(\|pool\|, 2)` tirages), **un déplacement d'unité** (`SwornProtector*`), **un stat-mod de block** (`AnvilShield_FrozenAttackerAdvantage`). Dégradation SILENCIEUSE : ni erreur ni crash, et **invisible tant que la géométrie du montage rend le consommateur inerte** — c'est exactement ce qui a laissé passer +3,1 % de dégât sur `FlailSwing` (`case-277`). | `[opus]` | `case-277-flail-swing-ecart-degat.md` §5. Le fix est mécanique (router par `Runner.apply(ActiveAbilityMessage(...))`), le **tri** ne l'est pas : il ne faut le faire QUE là où le caster porte un consommateur non inerte, sinon on ajoute aux montages des vecteurs after-hit/turn-flow qu'ils n'avaient pas. Recette : croiser les call-sites × les porteurs (`gameconfig.units[].passiveAbilities` ∋ `HazeOfCorruption` / `SwornProtector`, effet 1201) puis re-jouer chaque montage touché. Garde de référence déjà écrite : `test_flail_swing_live.py::test_flail_swing_cast_entry_point_haze_pool_live` (exige `bonds >= 1` ET que le raccourci NE reproduise PAS le live). |
| #259-a | **Rétablir les 4 862 corps pleinement partagés dans la table de symboles** — passe Il2CppDumper v39 en complément de l'applier Frida | `[opus]`+fenêtre Ghidra dédiée | `case-259-couverture-gshared.md` §5.1. La RE est FAITE : la chaîne Frida ne peut PAS les produire (le `methodPointer` d'une **définition** générique est un thunk d'invocation vers `MethodInfo.invoker_method`, adresse distincte du corps — décompilé de `IdunBattle.AI.Playbook.TriggeredAbilityPlaybook`1$$Init`, structure identique sur `TriggeredAbilityNonOwnerPlaybook`1$$Init`). L'applier legacy est un **complément pur** (il ne renomme que les `FUN_*`), donc il ne peut pas écraser la couche Frida ; l'ordre est `GhidraApplyIl2CppSymbols` **puis** legacy. Étape 2 du protocole = garde d'arrêt gratuite (`grep -c __Il2CppFullySharedGeneric script.json` AVANT de toucher au projet). Critère d'acceptation : `probe_259_gshared_coverage.py` sort **0** et `probe_257` passe de `perdu=5` à `perdu=3`. **Débloque #257 → #258** (les deux cibles portent l'instrument de décomposition par étage : utilité totale par candidat, terme de tuile complet). ⛔ Exige une re-symbolisation : ne pas la jouer tant qu'un agent RE travaille sur le projet en place. |
| #259-b | **Le `MethodInfo` d'une instance INFLATÉE porte-t-il le corps pleinement partagé ?** — une mesure tranche (b) et (c) d'un coup | `[opus]`+réinjection | `case-259-couverture-gshared.md` §5.2. `class_get_parent` depuis une classe concrète de playbook → `ComparablePlaybook<TAbility>` inflatée → `findMethod(parent, "CalculateActionUtility")` → `mi.ptr`. **OUI** ⇒ #257 se résout en runtime (plus de RVA en dur, survit à chaque build) et la 2e passe de `dump-il2cpp-full.js` peut énumérer les méthodes des classes inflatées qu'elle atteint déjà. **NON** ⇒ #259-a est la seule voie. **Prérequis** : aucun des ~60 RPC d'introspection du bundle ne **retourne** un pointeur de méthode (ils impriment et rendent `{ok:true}`) — il faut ajouter le RPC, donc réinjecter. |
| ~~#27-r1~~ | ~~**`MassDriverAccelerator` (1222) — override `CalculateCustomUtility` NEUF du build `rnca9r7q6c`, non porté**~~ | **LIVRÉ (2026-07-30)** | `case-27-custom-utility.md` §TRANCHE 4g. **La formule annoncée par cette fiche était FAUSSE** : elle lisait `AbilityEntities(owner:caster, …)` alors que l'ordre des PARAMÈTRES du ctor est `(caster, actor, target, owner, …)` et que le call-site passe **9 zéros en positions 4..12** ⇒ `owner = null`. Le sélecteur `GetBuffTargets` = `Owner + AdjacentFriends(Owner, 1, 3)` est ancré sur `Owner` (`IdunBattle.Entities.Selectors.OwnerSelector$$Select` lit `entities+0x18` et rend une liste VIDE), donc `Count = 0` et `Max(0, -1) = 0` : **le terme est IDENTIQUEMENT NUL, le poids `MassDriverAccelerator_AdjacentFriendly = 5` n'est jamais appliqué**. Le même sélecteur MARCHE côté EXÉCUTION (`ExecuteBehaviour` → `AddStaticStatModifierEffect(0x606)`) — c'est un no-op de la seule face DÉCISION. Confronté live (`probe_27_r1_massdriver_custom.py`) : point de bascule natif identique à n=0/1/2 alliés adjacents dans une fenêtre de **0,4458 point d'utilité** (la formule héritée prédisait 10), sensibilité prouvée par mutation adversariale. Deux résidus NEUFS ouverts au passage : ~~**N14**~~ (terme de tuile `ModifiedExoarmourPlaybook`, non porté, RETOURNE la décision de Kimm) — **FERMÉ le 2026-07-30 par #304**, `case-304-modified-exoarmour-move.md` — et ~~**N15**~~ (`MassDriverAcceleratorPlaybook$$MakeDamagePredictions`), **FERMÉ le 2026-07-31 par #305**, `case-305-massdriver-splash-prediction.md`. |
| ~~#305~~ | ~~**Résidu N15 : `MassDriverAcceleratorPlaybook$$MakeDamagePredictions` — le splash par ennemi adjacent à la CIBLE, jamais chiffré**~~ | **LIVRÉ (2026-07-31)** | `case-305-massdriver-splash-prediction.md`. Le natif enchaîne DEUX batchs `GenerateMultiHitAttackPredictions` : la cible, puis **un event par ennemi du caster adjacent à la cible** (`GetAdjacentAttackTargets` = `Enemies(caster@0x48, AdjacentUnits(target@0x60, 1, 3), 3)`) avec `GetHits2`/`GetDamageProfile2`. **Trois lectures que le décompilé impose** : (1) chaque event porte sur SON ennemi — `param_5` est `DSLSelectors$$Entity(<entité itérée>)`, PAS le sélecteur `Target` du quirk `Stikkbomb`/`PlasmaGrenade` ; (2) le dégât du splash est celui du batch PRINCIPAL, `MinMaxDamage` évalué UNE fois dans une locale et repassé aux deux batchs — la face COMBAT, elle, appelle bien `MinMaxDamage2` (divergence natif/natif décision↔exécution, invisible sur cette config où `minDmg_2` = `minDmg`) ; (3) seuls coups et profil changent. **Le discriminant de valeur est le PROFIL**, pas les coups (`nrOfHits` = `nrOfHits_2` = 1) : `damageProfile_2` = `Physical` (**PiercingRatio 1**) contre `damageProfile` = `DirectDamage` (**PiercingRatio 100**). Confronté live à `aiPlaybookPredict` sur **3 montages** (MC1_67/909, C4_09/31337, régime `--splash-hp` où le cap PV mord) × 3 bras (0/1/2 ennemis adjacents), TOUS les events comparés par `targetId` : **MATCH partout** (principal `[5385,8078]`, splash `[3135,5828]` et `[54,81]` — armures leviers distinctes exprès, sans quoi un port visant la mauvaise entité passerait sur les valeurs). Deux mutations adversariales, chacune **débordant zéro** (bras n=0 laissé vert) : SET du splash vidé → ROUGE dès n=1 ; `aoe_overrides` retiré → ROUGE sur les VALEURS, donc la garde `damageProfile_2` discrimine. Port par le chemin GÉNÉRIQUE (`get_aoe_targets` + `aoe_overrides`), aucun `make_damage_predictions` propre. **Cause racine de harnais traitée au passage** : `MDA.build_fixture` lançait `rl_duel build` en `check=False` + `stdout=DEVNULL` — un build refusé ne levait RIEN et le state-file re-servait l'ANCIEN runner ; #322 avait durci son seul appelant, la fixture PARTAGÉE restait permissive. Elle exige désormais un runner NEUF et remonte la sortie du builder. NON COUVERT : caster portant `ExtraHits` (stat runtime, non posable par `--unit-stat`) et l'arbitrage `MinMaxDamage` vs `MinMaxDamage2` (structurellement invisible sur cette config). |
| ~~#304~~ | ~~**Résidu N14 : `ModifiedExoarmourPlaybook$$CalculateMovementUtilityInStepsInternal` non porté — il RETOURNE la décision de Kimm**~~ | **LIVRÉ (2026-07-30)** | `case-304-modified-exoarmour-move.md`. Terme = `ModifiedExoarmour_LikesMovingPerTile` (**5**, clé AJOUTÉE par `rnca9r7q6c`, absente de la capture) × `path.Count`, où `path` = `IPathfinders.GetPath(unit, GetMainTile(unit), tuile, null)` du **WalkPathfinder** (slot 3, type dérivé par `MovementQuery$$GetPathfinderTypeForUnit` — **pas** le type 1 littéral de `MinDistanceToClosestEnemy`) et `Count` compte des **NOEUDS, extrémités incluses** (`arêtes + 1`) ; rester sur place vaut **0** (`UtilityMovementCase$$StaysOnTile`), pas `5 × 1`. Le port a fallu ajouter la face **chemin exact pondéré** du `WalkPathfinder` (`GenerateBreadthFirstTree` + `WeightCost = (bloquée ? 10000 : 10) − élévation`), que le package annonçait non portée. Confronté live PAR ÉTAGE (prédiction prise au NATIF, un écart antérieur de `pairUtility(69)` masque toute comparaison de décision complète) sur **4 bras / 2 plateaux** : l'argmax reproduit le choix natif partout, son retrait le contredit (ROUGE), et l'intersection des contraintes donne **4.6130 < k < 5.0563** pour `k × |chemin|` (contient le poids lu, **5**) contre un intervalle **VIDE** pour un forfait — la proportionnalité est MESURÉE, grâce à **deux longueurs de chemin jouées** (4 et 3). Effet de bord fermé : `tile_leaf_ctx` UNIONNAIT le kit gameconfig à la lecture live du `TriggeredAbilityComponent` et réintroduisait un passif que la bataille n'a pas (mesuré, seed BC sans le passif : live `[1486]`, gameconfig `[1529]`, union `[1529,1486]`, natif `[1486]`) — la lecture live fait désormais AUTORITÉ ; dans le régime NORMAL elle est un **sur-ensemble** du gameconfig (`[1529,1486]` vs `[1529]`), donc remplacement == union et le gain de N13 (traits/reliques) est intact. |
| #27-r2 | **`ResurrectionOrb` (1009) — override `CalculateCustomUtility` NEUF, bloqué par la route non-attaque** | `[opus]` | `case-27-custom-utility.md` idem. `IdunBattle.AI.Playbook.Loki.ResurrectionOrbPlaybook$$CalculateCustomUtility` ; poids `ResurrectionOrb_LikesResurrection = 90` et `ResurrectionOrb_LikesSummoning = 10`. Porteur `necroOverlord` `Anuphet` [lineup, **présent au catalogue**] + 5 npc. **Verrou 2 de case-27** (pas de `damageProfile` ⇒ `state_bridge._is_attack_ability` ne route jamais l'ability vers `_best_attack`) — même famille que 1226/1053/1185/1212. Le poids `_LikesResurrection = 90` est le plus gros terme custom du jeu : à traiter dès que la route summon/non-attaque existe. |
| #271-r1 | **Face NON-OWNER de `KustomForceFieldReworked` : pas de confrontation à écart STRICTEMENT POSITIF** | `[opus]` | `case-271-kustom-force-field-reworked.md` §7.3. Les deux bascules mesurées (`necroWarden` +10, `orksNob` +20, natif == port ON) partent d'un **ex aequo** : un tie-break natif fixe pourrait produire le même résultat. Le miroir strict (même paire, aimant de l'autre côté) n'est pas montable au spawn (le Big Mek est derrière ses alliés). Deux voies : (a) un couple (board, seed, pas) où l'écart T1−T2 d'un allié tombe dans 1..25 **et** où la proposition native est un move PUR — le balayage `--nonowner --gap-min 1` sur `MC1_67`/`C4_09` × 777/31337 × pas 0..12 n'en a pas trouvé (tous en proposition d'ATTAQUE) ; (b) pré-positionner le Big Mek DEVANT ses alliés pour rendre le miroir montable. |
| #271-r2 | **Pré-gate `<slot 4>` de `TriggeredAbilitiesNonOwnerUtility.IterateAbilities` non porté** | `[opus]` | `case-271` §3+§7.1. `IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility$$IsInvalidEntityForPlaybook` = `!slot4 && !IsFriend` ; `slot4` est un prédicat sans argument dont le corps trivial est fondu par l'ICF (sans symbole). TRANSPARENT pour le seul playbook au registre (il re-teste `IsFriend` lui-même) ⇒ non porté, non deviné. **À lire avant d'enregistrer un playbook NonOwner sans auto-gate** — bloc `methodPointers` du PE (`probe_8889_methodptr_vtable.py`). |
| #271-r3 | **Régime SPAWN de la feuille `TriggeredAbilitiesNonOwner(4)`** | `[opus]` | `case-271` §7.2. `case.unit == null && case.parent != null` (call-site `SortTilesByUtilityForSummon`) : le natif itère avec le PARENT comme sujet et SANS exclusion de self ; le `ctx` de ce foyer rend `{"is_spawning": True}` seul ⇒ feuille à 0. Même résidu que les autres feuilles gatées sur le sujet (case-205) ; le fermer demande d'abord un `ctx` de spawn peuplé. |
| ~~#267-r1~~ | ~~**Les sites de la face PRÉDICTION relisent le kit gameconfig PAR `visualId` au lieu du substrat d'ENTITÉ**~~ — **RÉSOLU** : 12 sites basculés sur le foyer unique `prediction/_shared.py::_entity_traits` (pendant de `damage_model.target_trait_names`). | `[fait]` | `case-267-traits-prediction.md` §6bis. Gates dérivés par balayage exhaustif (`probe_267r1_gate_sweep.py`, 123 effets × 105 traits) : `BigTarget`/`Vehicle` (BeastSlayer +20 %), `Psyker` (CondemnorStake +30), `Summon` (MartialKatah **+100 %**), `Imperial`/`Xenos` (DespoiledGround +15 %). Écart mesuré LIVE : **6/6 lignes**, le kit brut ratait le pseudo-trait d'ALLIANCE — absent de **175/175** `gameconfig.unit().traits`, donc ces gates étaient structurellement MORTS. Garde : `tests/engine/test_prediction_trait_gates_live.py` (6 tests ; rouge provoqué 3F/3P câblage neutralisé ; oracle natif `(2118,3180)` écart **(0,0)**). |
| #271-r4 | **Les 24 autres playbooks `*NonOwnerPlaybook` du binaire restent non portés** | `[opus]` | `case-271` §7.5. Le binaire déclare 25 concrets (`FirstAmongTraitors`, `ShieldOfFaith`, `HaywireMine`, `NornCrown`, `IconOfObstinacy`, `MyWillBeDoneOverlord`, `PropheticSentinel`, `TimesplinterMantle`, …) ; un seul est au registre. L'absence == `LoadPlaybookNonOwner` rend null == la paire n'est jamais yieldée : **même dégradation que le natif**, pas un trou silencieux. À porter quand un case en montre un décisif — le socle (feuille 4 + registre + base) existe depuis #271. Attention au résidu #271-r2 pour tout playbook sans auto-gate `IsFriend`. |
| ~~#354-r1~~ | ~~**`MyWillBeDoneOverlord` n'est portée sur AUCUNE face**~~ — **LIVRÉ (face COMBAT)** | `[fait]` | `case-354-r1-my-will-be-done-overlord.md`. Port + garde **15 tests verts**, agreement live bit-exact (−259 / −242 sur deux activations) et préférence de groupe confrontée (`necroWarden` Necron+Hero ATK 400 élu contre `admecDominus` Hero ATK 3000). `persistent_data.py` **a bien un artefact natif** : `IdunBattle.Entities.Components.PersistentDataComponent` (+ `PersistDataList`/`ClearAllPersistentData`) et `AbilityOrEffect$$GetPersistentDataId` — le `List.Add` sans déduplication est LU au décompilé. **Les deux défauts trouvés étaient dans la VALIDATION, pas dans le port** : (a) le montage de la branche ELSE laissait le porteur SEUL de son camp, donc son `finish` faisait basculer le tour (`turn` 3→4) et un tick ramenait l'effet 1581 de 3 à 2 — le test masquait l'écart en comparant `set(...)`, donc les porteurs et jamais les durées ; avec un allié-tampon exilé, live et port rendent **3** ; (b) **trois contrefactuels sur quatre ne testaient rien** (`ascending` inerte tant qu'un groupe n'a qu'un membre, `notargets` tant que tous les alliés ont une cible, `nomechanical` tant qu'un Necron est éligible — ils sont TOUS `Mechanical`), d'où les montages **M5** (trois Necrons, dont `necroSpyder` — **seul Necron sans arme à `Range`** — placé hors de portée) et **M6** (aucun Necron allié). Résidus nommés : ~~effet 1581 posé sans classe d'effet~~ **fermé par #358**, ~~1582 jamais référencé~~ **fermé par #364** (inertie démontrée), `GetPersistentDataListAsEntities` non porté en sélecteur, terme `TriggeringAbilityIs(1557)` omis car tautologique sur `On(0x29)`. Face DÉCISION toujours ouverte dans `#271-r4`. |
| ~~#358~~ | ~~**L'effet `1581` est POSÉ, mais aucune classe d'effet ne le porte**~~ — **LIVRÉ** | `[fait]` | `case-354-r1-my-will-be-done-overlord.md` §5. Le consommateur de la magnitude **n'est pas dans la classe d'ability** (c'est pour ça que #354-r1 ne l'avait pas trouvé, et il a eu raison de ne rien inventer) : l'effet **n'a aucune classe native dédiée**, c'est une instance GÉNÉRIQUE `DynamicStatModifierEffect(AbilityType(1556), variableType 8 = extraDmg, isNegative = 0, canBeImmuneTo = 0)` construite par la lambda `IdunBattle.Core.Services.EffectsDatabase.<>c$$<InitializeEffects>b__14_574`, et sa magnitude sort du corps générique `IdunBattle.Entities.Effects.DynamicStatModifierEffect$$GetDynamicStatModificationAmount` = `ConfigVar(1556, EffectSource(Get(effect)), 8)`, nié si `isNegative`. **Le lien lambda ↔ `EffectType` est mécanique et vérifiable** : dans `EffectsDatabase$$InitializeEffects`, chaque enregistrement écrit le delegate au champ statique `<>9__14_N` (offset `8 × (N+1)`) juste avant `Add(dict, effectType, delegate)` — loi contrôlée sur les **607** enregistrements (chiffre CORRIGÉ par #364 — cette fiche a d'abord écrit 511, cf. la ligne #364 ci-dessous ; tous multiples de 8, 607 indices distincts, les 14 lambdas `DynamicStatModifierEffect` sur 14 `EffectType` distincts, compte re-dérivé et inchangé). Port : `entities/effects/loki/my_will_be_done_overlord.py` (canal EAGER `applied_stat_mods`/`reverted_stats`, même moule que le lot Votann). Confronté LIVE bit-exact sur **trois régimes** (L50×180 → **+898**, L50×100 → **+499**, L20×180 → **+85**, chaque fois `live == port == extraDmg[passif]×mult`), `statModSources(attack).residual = 0` et source = l'ENTITÉ-EFFET. Le régime `PassiveAbilityLevel=20` / `ActiveAbilityLevel=50` est le discriminant qui prouve que le niveau lu est le **passif**. Généralisation **M7** : la branche ELSE atteinte parce qu'un PRÉDICAT tombe (allié adjacent, avec cible, mais **non-`Mechanical`**) — voie d'entrée différente de M4, buff bit-identique. Garde : `test_my_will_be_done_overlord_live.py` passe de **15 à 21 tests**, tous verts. |
| ~~#364~~ | ~~**L'effet `1582` est mesuré NON ENREGISTRÉ dans `EffectsDatabase` — à trancher**~~ — **LIVRÉ** | `[fait]` | `case-354-r1-my-will-be-done-overlord.md` §6. **Réponse à la question binaire : OUI, `1582 MyWillBeDoneOverlord_FriendlyAttackedMarker` est réellement absent du dictionnaire de `InitializeEffects`** — mais la mesure héritée qui le disait était **sans valeur**, et c'est le vrai résultat du cas. Les deux balayages de #358 partageaient l'octet-clé `4c 8b c6` (`mov r8, rsi`) : leur accord (511 == 511) était un accord sur la **même cécité**. Relu au désassembleur : **607** enregistrements, pas 511. Les **96** manquants appellent `Dictionary<,>$$Add` **directement** et passent leur clé **par adresse** (`lea rdx, [slot]` + `mov dword ptr [slot], imm32` — clé `ValueType` du dictionnaire gshared) ; après `mov r8, rsi` l'octet suivant est `C7`, pas `BA`. **96 `EffectType` étaient donc rapportés « NON ENREGISTRÉ → aucune classe d'effet native »**, dont `5 Fire`, `17 Ice`, `31 StatModifier`, `1004 MightOfHeroes_ExtraHits`, `1099 Waaagh_ExtraMovement`, `1244 Contaminated` — tous vivants : le faux négatif était produit par notre propre outillage. Ce qui ferme l'inventaire n'est pas un 3ᵉ motif d'octets mais une **source indépendante** — les **607** fabriques `<>9__14_N` présentes en binaire doivent égaler les 607 `Add` (compter « enregistrés + orphelins == membres » n'aurait rien prouvé : l'égalité est vraie par construction, y compris avec 96 sites manquants). **Verdict 1582 = INERTIE DÉMONTRÉE, pas un port** : les trois voies de vie sont fermées — aucune fabrique ; **0** instruction `IdunBattle` chargeant l'immédiat (encodages **32 ET 16 bits** ; les 2 seules occurrences du binaire sont `I2.Loc.ArabicTable$$.ctor` et `System.Globalization.HebrewCalendar$$GetDayOfYear`) ; présence en DONNÉES **50** occurrences contre **70** pour 1581 et **47** pour 1583 — même ordre que ses voisins **vivants**, donc métadonnée IL2CPP (triplets `(index, valeur, 0xFFFFFFFF)`) et non tableau statique. Le gameconfig n'est pas une 4ᵉ voie (il ne nomme aucun `EffectType` créateur d'effet : 1581, vivant, n'y figure pas non plus). **Ce n'est pas une singularité** : **629** membres déclarés, **607** avec fabrique, **22** sans — sentinelles (`None`, `STRIPPED`), 7 emplacements morts nommés (`UNUSED_*`, `NotUsed`, `Unused`), 3 mocks, reliquats (`Duel_Taunt`, `Cursed`, `ArcaneShield`, `InfernalCannon`…) ; 1582 y est avec `1353 NotUsed` et `1373 UNUSED_13` le seul dont **aucune** fonction `IdunBattle` ne charge la valeur. **« Inerte » ≠ « impossible à poser »** : `EffectsDatabase$$GetEffect` ne lève pas sur clé absente — il logue `System.Enum$$ToString` et rend un `NoneEffect`. Porteur **confrontable et déjà confronté** : `necroOverlord`, HERO **au pool** rank 17 (5 autres porteurs npc, 0 MoW, 0 summon, 0 relique) — l'inertie n'est pas un défaut d'accès. Garde : `tests/engine/test_effect_1582_inertia_binary.py` (**7 tests, offline pure, ~2 s**), une voie par test + fermeture d'inventaire + typage des clés + anti-zéro-menteur + cohorte ; **4 mutations adversariales, 4 rouges** (cécité #358 → `96 appel(s) d'ajout sur 607 n'ont PAS de clé résolue`). `probe_364.registry` est désormais l'implémentation **unique** de la loi ; `probe_358` la consomme et sa garde de cohérence, devenue vide, est ré-armée. |
| ~~#354-r1 (énoncé d'origine)~~ | | | `case-354-martial-apotheosis-porteur-retire.md` §5. Le build a **remplacé** `MartialApotheosis` par elle sur le seul porteur ; le port de 1045 est donc tombé inerte (seule entrée orpheline des 29 de `ABILITY_TRIGGERS`) et **rien** ne couvre la mécanique qui l'a remplacée. Face COMBAT à porter — `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MyWillBeDoneOverlordAbility$$CreateTrigger` = `On(0x12 = TurnStart_EffectActivation) & AmountIsGreaterThanZero(GetPersistentDataListAsEntities)` **\|** `On(0x29 = UnitFinishedTurnNormally) & OwnerIsActor` ; `$$CreateBehaviour` se branche sur le `triggerType` : sur `0x12` c'est un `ClearAllPersistentData`, sinon `If(GetTargetFriend, AddTemporaryAttackOverrideEffect(cible, PercentageOfAttackCappedAtMax(var 0xd, var 0x4a)) & PerformAIAttackFromCurrentPosition(cible) & ResetTemporaryAttackOverrideEffect(cible) & AddToPersistentDataList(...), AddDynamicStatModifierEffectToOwner(0x62d, Sum(TurnsFromRounds(1), …)))` — l'Overlord fait **attaquer un allié** avec une attaque plafonnée, et mémorise qui a déjà servi (liste persistante purgée au tour suivant). ⚠ Deux points à ne pas présumer : la liste persistante est un **état inter-tours** (le port n'a pas d'équivalent connu de `PersistentDataList`), et `PerformAIAttackFromCurrentPosition` fait agir une unité qui n'est pas le porteur (même famille d'observation que les summons, cf. `case-291`). Face DÉCISION : `MyWillBeDoneOverlordPlaybook` / `MyWillBeDoneOverlordNonOwnerPlaybook`, déjà comptés dans `#271-r4`. Porteurs (gameconfig vivant) : `necroOverlord` [lineup, **au pool**] + `necroNpcOverlord`, `necroBossOverlord`, `necroBossOverlordLHE`, `necroBossOverlordLEG`, `necroBossC1Overlord` — confrontable sans injection. |
| ~~#354-r2~~ | ~~**`test_martial_apotheosis_live.py` cible une ability sans porteur** → converti en garde d'inertie~~ — **PRÉMISSE RÉFUTÉE, conversion ANNULÉE (#392)** | `[fait]` | `case-392`. L'ability **n'a jamais cessé d'être montée** : le natif énumère `UnitConfiguration.PassiveAbilities` (`UnitFactory$$AddConfiguredAbilities`), et `data/seed-bc.json` porte `necroOverlord.PassiveAbilities = [1045]`. Mesuré : `TriggeredAbilityComponent` réel = `['1045=MartialApotheosis']` (hiérarchie 2) ; LIVE **3702** sur l'ennemi anneau-1, **0** à d=2 (attribution établie, l'objection `case-354` §3 est levée) ; replay-diff offline **bit-exact**. Le silence était un **bug du port** (dérivation gameconfig), fermé par #366-r1. Les 3 vecteurs supprimés sont restaurés, (E) durci (attribution géométrique + dégât bit-exact), garde T0 réorientée sur le canal MESURÉ. **4 passed/1 failed → 7 passed.** |
| #418-r1 | **`IsEffectTarget` : le port lit une géométrie RE-DÉRIVÉE là où le natif lit une liste MATÉRIALISÉE, et il est spécialisé à UN effet** | `[opus]` | `case-392` §5 (RE d'attestation, rien n'est corrigé). `IsEffectTargetTrigger$$ShouldTrigger` invoque `IdunBattle.Core.Services.EffectsQuery$$IsEffectTarget` (slot d'interface de `<ctx DSLTriggers>+0x38`, `onlyActive=0`) — **pas** `EntityExtensions$$IsTargetOfEffectOfType`, dont l'unique appelant direct est `EntityExtensions$$HasEffectOfType` (la docstring de `is_target_of_adjacent_friend_aura` nomme donc le mauvais aval). Deux écarts : **(1)** le natif LIT `EffectComponent+0x48` (`GetEffectsWithTargets` la copie) et la maintient par `IdunBattle.Operations.RefreshEffectsOperation$$UpdateEffectTargets` (converge `desired` vs `current`, appelée par `RefreshEffect`/`DeactivateEffect`) — entre deux refresh, une unité qui vient d'entrer/sortir de l'anneau‑1 est déjà (ou n'est plus) comptée côté PORT ; **(2)** la primitive est GÉNÉRIQUE, le lecteur est SPÉCIALISÉ à l'effet `1026` : **5 des 6** fonctions natives consommatrices restent découvertes (`InstinctiveBehaviour_UpdateTargetAbility` ×3 call-sites, `PsykerExtraAttackAbility` ×4, `GuardianOrganismAbility`, `WayOfTheShortBlade_AttackAbility`), chacune avec SON sélecteur. JUSTES en revanche, et mesurés : la géométrie (`AdjacentUnits` = `AdjacentTiles` anneau‑1 **fixe** puis `op_Subtraction(origin)` = porteur exclu) et `onlyActive=0` (`EffectsState.has_effect` filtre `consumed`, pas `active`). |
| #392-r1 | **`MyWillBeDoneOverlord` est INERTE dans tout runner bâti sur le seed BC courant** | `[opus]`+arbitrage | `case-392` §3. Écart kit/BC SYMÉTRIQUE de `MartialApotheosis` : le kit gameconfig la nomme, `data/seed-bc.json` **ne la monte pas** (`necroOverlord.PassiveAbilities = [1045]` seul). Ses deux entrées de `ABILITY_TRIGGERS` (#354-r1, 15 tests verts) ne sont donc **jamais dispatchées** depuis ce seed — leur validation est passée par une greffe. Balayage `probe_392` étage 0 : ce sont, avec `Bounce` (`orksNpc7Squig`, non portée), les **seuls 3 écarts** kit/BC du seed. Se ferme avec **#254-bc** (re-dump du bloc `Units`), qui inverse en même temps le cas `MartialApotheosis`. |
| #270-a | **`enum_maps.GROUP_TYPE` : 66 ids sur 102 portent un nom FAUX** — une réattribution, pas une absence | `[opus]` | Trouvé par l'inventaire #270 (`case-270-active-ability-type-drift.md` §3). `IdunBattle.Streams.GroupType` a un membre **inséré en 36** (`Ability_Displace`) : à partir de là tout est décalé de +1 — `36` que le dépôt lit `Ability_Buff` vaut `Ability_Displace`, `44 Attack` vaut `ReviveUnit`, etc. **Ce n'est PAS la migration `rnca9r7q6c`** : `GroupType` est identique entre les deux builds versionnés (104 membres, 0 renuméroté) — la table dérive d'un dump ANTÉRIEUR à `gqfc5mff6c`. Consommateurs : `rl_collect_batch._group_name` (colonne `stream_group.group_name`, migration 014) et `frida/public/src/battle-log.js:44-58` (**même** liste, tableau indexé, même rupture à l'index 36). Corriger déplace le libellé de tout l'historique ingéré ⇒ décider aussi du backfill. Re-dériver : `probe_270_active_ability_type_drift.py` puis diff `enum_maps` × `data/symbols/<CURRENT>/frida/enums.tsv`. **RÉSOLU par #275** (`case-275-enum-maps-drift.md`) : les 66 ids sont corrigés, `battle-log.js` était en fait DÉJÀ juste (104 labels, 0 divergent), et le backfill de l'historique est tranché — **on ne rétro-corrige pas**, les noms stockés sont cohérents avec le build qui les a émis (§4). |
| #270-b | **Les deux générateurs de tables d'enum sont arrimés à `dump.cs`, supprimé le 2026-07-25** | `[opus]` | `case-270` §1. `rl_gen_ref_tables.py::resolve_dump_cs` et `rl_gen_enum_columns.py` lisent `data/dumps/<hash>/dump.cs` (artefact Il2CppDumper retiré par `8e591496`) et lèvent `SystemExit` avant d'écrire : **la dérive de `enum_maps.py` / `006` / `013` n'a plus de réparateur**. #270 a réparé le seul bloc `ActiveAbilityType` (via `regen_active_ability_tables.py`, source = `data/symbols/<CURRENT>/frida/enums.tsv`) ; restent `EFFECT_TYPE` (682 → 629, dont **2 faux** : 1563/1564 `DA_Hero6_Passive_*` → `SpecialIssueCombiMelta_*`), `PASSIVE_ABILITY_TYPE` (574 → 476), `DAMAGE_PROFILE_TYPE` (1 manquant), `ref_triggered_ability`, `ref_effect`. `UNIT_SPAWN_SOURCE` est sain (9/9). Le remède est le même partout : remplacer `resolve_dump_cs()` + `parse_enum(dump.cs)` par un lecteur d'`enums.tsv` (`symbols_layout.build_dir`). ⚠ `ref_*` sont des cibles de FK : ajouter est urgent (un id du build absent fait ÉCHOUER l'insert), retirer est inerte (les migrations sont idempotentes, elles ne suppriment rien). **#275 a livré `regen_enum_maps.py`** : les SIX blocs d'`enum_maps.py` sont régénérés et gardés (`probe_275` + `tests/test_enum_maps_ratchet_offline.py`). **Restent** `ref_triggered_ability` et `ref_effect` (`006`) plus leurs backfills (`013`) — même remède, source `enums.tsv`. NB : le « `DAMAGE_PROFILE_TYPE` (1 manquant) » de cette ligne est PÉRIMÉ — re-mesuré 24/24 en #275. |
| ~~#270-d~~ | ~~**`astarLysander` ne se déploie PAS — `initAndStart: system error`, famille #254**~~ | **LIVRÉ (2026-07-31)** | `case-270d-trait-hors-enum.md`. **La piste #254 est RÉFUTÉE** : `IconOfObstinacy` a bien `constants` absent, mais aucune classe du kit ne lit de constante à la construction — `IconOfObstinacy_AddArmourBuffAbility$$CreateTrigger` / `$$CreateBehaviour`, `IconOfObstinacy_AddDamageBuffAbility$$CreateBehaviour` et `AIconOfObstinacyAbility$$GetAffectedUnits` n'utilisent que des littéraux, et la seule lecture du kit (`TitanhammerSquadAbility$$GetCurrentlyAffectedFriends` → `GetNumberConstant(0x16 = AbilityConstantType.range)`) est **satisfaite** (`range: "2"`). La vraie cause est un **NOM DE TRAIT hors enum** : `catalog_inject._traits` posait `Subfaction: ImperialFists` dans `UnitConfiguration.Traits`, champ **typé** `List<IdunBattle.Entities.Enum.UnitTrait>` (`BattleConfigBuilder$$GetUnitConfiguration` recopie `UnitProperties+0x18` → `UnitConfiguration+0xd0` ; `UnitPropertiesExtensions$$GetPlayerFacingTraits` lit ce même `+0x18` et rend `List<UnitTrait>`). Au `step=deserialize BC` d'`initAndStart` : `StringEnumConverter$$ReadJson` → `EnumUtils$$ParseEnum` → `$$MatchName`/`$$FindIndexByName` vides → `System.ArgumentException` **levée** → « system error », qui emporte le **BC entier**. Déclencheur : le gameconfig est livré **en avance** sur le binaire (`releaseStatus` 2026-08-26 ; `UnitTrait` s'arrête à 4 sous-factions, 9000..9003). **Série = 1** sur les 669 unités du gameconfig, **0** sur les 175 entrées capturées — mais le gisement est alimenté par le JEU, d'où une garde. Correctif : `_traits` restreint au vocabulaire de l'enum du build, ce qui est écarté est **dit** (`dropped_traits`, report `--show`) ; `--validate` inchangé. Mesure LIVE : A (trait remis) → `[error] initAndStart: system error` / B → build OK, `abilities=[69, 1231]`, `toActivate=[85]`, `cooldown 1` conforme à `initialCooldownTurns` ; rejouée sur un second couple (seed 31337, board `C1_74`). **Contre-épreuve croisée** : `votanChampion` monte intact et **casse** dès qu'on lui pose le même nom — la faute est le TRAIT, pas le porteur. **`1231 TitanhammerSquad` est désormais confrontable** (son port reste à faire, hors périmètre) ; `probe_270_carriers_live.py` passe maintenant sur les **4** porteurs. Gardes : `tests/engine/test_270d_catalog_traits_enum.py` (3, offline) + `tests/engine/runner/test_270d_lysander_deploy_live.py` (5, live) + `probe_270d_lysander_deploy.py`. |
| #270-c | **`engine.entities.TriggeredAbilityType` : 107 ids morts, 9 manquants** — même patron que #254b-c | `[opus]` | Mesuré par #270 en passant (`probe_270` transposable : changer `CLE`). Le mirror porte 574 membres, `IdunBattle.Entities.Enum.TriggeredAbilityType` du build en porte **476**. **0 id renuméroté** entre le port et le build, donc a priori même verdict qu'#254b-c (code mort inerte + manquants qui dégradent), **mais à re-dériver membre par membre** : le contrôle croisé qui a rendu #254b-c concluant (classe `<Nom>Ability` dans `classes.tsv` + nom dans `gameconfig.units.abilities` + `dumpEnum` runtime) doit être rejoué sur CET enum, et les homonymes inter-enums re-listés. Le pendant hooks est DÉJÀ fait (#256, `triggered-ability-names.ts` 557 → 476). **Chiffré et dé-risqué par #275** (§7) : le contrôle croisé demandé est fait côté `enum_maps.PASSIVE_ABILITY_TYPE` (même enum, mêmes 107 absents / 9 manquants, **0 renuméroté**), et le risque de la suppression est mesuré à **zéro** — `0` usage `TriggeredAbilityType.<membre mort>` hors artefacts générés. Le mirror est mesuré par `probe_275_enum_maps_drift.py` étape 4. |
| ~~#275-a~~ | ~~**`engine.entities.EffectType` : 2 ids FAUX, 73 morts, 20 manquants** — même patron que #270-c~~ | **LIVRÉ (2026-07-31)** | `case-318-effect-utility-mirror-bijection.md`. Résorbé **avec** la dette jumelle `UtilityType` (15 manquants) : le registre de `probe_313` passe de **8 sous garde + 2 dettes** à **10 sous garde, 0 dette**, et `tests/test_enum_mirror_ratchet_offline.py` garde ce zéro (16 tests). `EffectType` 682 → **629** (0,0,0), `UtilityType` 68 → **83** (0,0,0) ; étape 3 inchangée à **total=1438, INTROUVABLES=0, MORTES=0**. **Les 2 renumérotés n'étaient PAS un renommage** : `1563`/`1564` disent `SpecialIssueCombiMelta_*` sur les **DEUX** builds versionnés (`DA_Hero6` : 0 occurrence dans les deux `enums.tsv`) — le port les tenait de `data/il2cpp_enums.tsv`, déjà périmé, comme les 1545/1548/1551 de #219. Sémantique confirmée par une seconde source : `…Effects.Loki.SpecialIssueCombiMelta_AdditionalHitsEffect$$CreateAdditionalHits` et `…_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` (passif 1545 de `darkaSternguard`). **0 site de code citait l'ancien nom** — `enum_maps` et `effect-type-names.ts` disaient déjà juste, le dépôt portait donc deux tables contradictoires du même enum et c'est celle que le code exécutable lit qui était fausse. Retrait des 73 morts dé-risqué par 4 contrôles à zéro (AST, textuel global, `EffectType(<littéral>)`, **les 124 clés de `EFFECT_CLASSES`** — ce dernier désormais gardé) + 305 modules `engine.*` importés sans échec. Réparateur corrigé au passage (il recollait `X = 28   # …` en `X = 28# …`). **Restent hors périmètre** : `scripts/sql/006`/`013` portent toujours l'ancienne table → #270-b. |
| ~~#254b-c~~ | ~~`engine.entities.ActiveAbilityType` n'est pas re-généré pour `rnca9r7q6c` : 4 membres ajoutés, 75 retirés~~ | **LIVRÉ (2026-07-30)** | `case-270-active-ability-type-drift.md`. **La prémisse était fausse sur un point décisif** : `rnca9r7q6c` n'a rien retiré — les 75 ids sont absents des **DEUX** dumps versionnés (celui de `gqfc5mff6c` a été généré le 2026-07-27, donc après ce build). Ils viennent de `data/il2cpp_enums.tsv`, table Il2CppDumper **supprimée le 2026-07-25** ; ce dossier est la moitié Python/SQL du ménage que #256 avait fait côté hooks. **Verdict : 75/75 = code mort**, corroboré par QUATRE sources indépendantes — `enums.tsv`, le RPC **`dumpEnum` au runtime** (261 noms / 260 valeurs, 0 divergence), `classes.tsv` (**0/75** ont une classe `<Nom>Ability`, contre **10/10** pour les ids bas survivants), et `gameconfig.json` (**0/75**). **0 réattribution** sur cet enum (le seul écart de nom est `0 None_`, échappement Python). Le sens de la dérive qui COÛTE est l'autre : `state_bridge._abilities_of` « ignore une active dont le nom n'est pas dans l'enum » ⇒ 4 abilities de HÉROS confrontables disparaissaient offline (1222 `votanChampion`, 1227 `thousSekhetar`, 1231 `astarLysander`, 1232 `eldarLhykhis`), et `ref_active_ability` — **cible de deux FK** — manquait **12** ids du build. Une citation franchement fausse trouvée en chemin : `013` disait `1228 = DA_Hero6_Active` là où le jeu dit `SternguardFocus` (corrigé au mirror en #219, jamais descendu au SQL). Livré : `regen_active_ability_tables.py` (le réparateur qui manquait, même discipline que #256), `probe_270_…py` (garde + inventaire, `--rev`/`--live`), les 4 artefacts à 260, et 5 citations hors tables corrigées. Résidus → #270-a/b/c. |
| #281-r1 | **Les 10 montages `A EXAMINER` du raccourci `execute_behaviour` ne sont pas confrontés live** | `[opus]` | `case-281-raccourci-execute-behaviour-inventaire.md` §7. Leur inertie est établie **par lecture du gate**, pas par mesure : `SwornProtector` exige `AbilityHasAttackType(0\|1)` (faux sur un buff — les 4 sites de `test_supreme_commander_live.py` + `probe_95r2` castent `SupremeCommander`), `AnvilShield` et `FuryFromTheDelve` exigent `IsNormalAttack` (faux sur tout cast — `test_foehammer_live.py:50`, `probe_226_hammer_foehammer.py:214/306`, `probe_121:241/244`, `test_prioritised_efficiency_live.py:223`, `test_votann_lot1_live.py:242`). Le raisonnement est solide sur le décompilé mais **aucun** de ces montages n'a été rejoué dans les deux voies pour le constater. ⛔ **Ne PAS les router par `Runner.apply` « pour être sûr »** : ça leur ajouterait des vecteurs after-hit / turn-flow qu'ils n'ont pas. Le geste juste est une MESURE (`probe_281 --step mesure` transposé), pas une correction. Re-dériver la liste : `python scripts/python/probe_281_pre_unit_ability_shortcut.py --step classify`. |
| #281-r2 | **7 call-sites `INDÉTERMINÉ` — montages qui ne nomment aucune unité** | `[opus]` | `case-281` §3/§7. `probe_231_charge_and_forcecrit.py:115/121`, `probe_61_ability_hits.py:145`, `test_fragstorm_migration_live.py:180`, `test_overwatch_single_shot_per_activation.py:140`, `test_stikkbomb_migration_live.py:148/186` : roster issu du seed BC ou caster passé en CLI ⇒ le tri statique ne peut rien conclure, et « aucun porteur cité » n'y est PAS une preuve. `probe_61_ability_hits.py` est le cas franc : il accepte n'importe quel caster en argument, donc il **est** faux dès qu'on lui passe un blightlord — sans que rien ne le signale. Piste : soit nommer le roster dans ces montages, soit leur faire refuser (ou router) un caster porteur d'une famille inconditionnelle. |
| ~~#281-r3~~ | ~~113 citations `On(0x2b)` / `PreUnitAbility = 0x2b` : l'ordinal est 42 = 0x2a~~ | **LIVRÉ (2026-07-30)** | `case-283-quatre-enums-renumerotes.md`. **Les deux moitiés de l'énoncé étaient fausses.** Le gisement ne fait pas 113 citations mais **728** sur les quatre enums renumérotés (681 portent la signature « ancien ordinal », re-dérivable) — et il n'est **PAS inerte** : trois sites l'exécutaient. (1) `frida/hooks/features/ai-utility-trace.ts::UTILITY_TYPE_NAMES`, 82 entrées figées sur `gqfc5mff6c` dont **37 fausses**, vivant INLINE dans un `features/` donc hors de la garde #252 — elle **pilote** `prePopulateKnownConfigs`, qui appelle `UtilitiesDatabase$$GetUtilityConfig(type, coll)` avec ces ordinaux : chaque config était étiquetée du libellé de sa **voisine** à partir de l'id 8, et `AttackTile` (inséré) n'était **jamais** interrogé. Rapatriée en `frida/hooks/data/utility-type-names.ts`, générée par `regen_hook_name_tables.py`, gardée par `probe_252`. (2) `probe_hazeord_blast_radius.py::DEATH_EVENTS[55]` = `UnitDefeated` (**54** depuis la MAJ) — table INTERSECTÉE avec `event_id`, donc les consommateurs d'`UnitDefeated` sortaient de l'inventaire : **19 → 21** (`AmbushSummonAbility`, `CosmicHorrorOnKillAbility`). (3) **5 ordinaux figés JUSTES aujourd'hui** (`TURN_END = 23`, `DAMAGE_DEALT = 16`, 3 asserts) — donc muets au prochain build, exactement comme `CAPTURE_POINT = 24` de #272. Prose : **298 citations réécrites** sur le seul critère prouvable (le nombre vaut EXACTEMENT l'ordinal du membre sur le build précédent), migration **prouvée inerte** — flux de tokens hors COMMENT/STRING identique sur **88/88** fichiers. L'interdit du `sed` est tenu par construction : le probe n'accepte jamais un nombre nu, seulement une co-occurrence avec le NOM d'un membre ⇒ **0 faux positif** sur les ~100 `extraHit`. Cliquet : `probe_283_enum_ordinal_sweep.py` + `tests/test_enum_ordinal_ratchet_offline.py`. Résidus → #283-r1/r2. |
| #283-r1 | **205 `On(<n>)` NUS ambigus — indécidables statiquement** | `[opus]` | `case-283` §4. 132 dans `scripts/python`, 73 dans `docs/`. L'ancre est sûre (`DSLFactory$$On(EventTriggerType, …)` : le nombre EST un `EventTriggerType`, aucun risque d'homonyme) mais le **verdict** ne l'est pas : sans le NOM accolé, rien ne dit de quel build vient la citation, et les deux cas existent — `probe_281_pre_unit_ability_shortcut.py` écrit `On(0x2a)` (**juste**), `engine/runner/abilities/handler.py` écrit `On(0x2b)` (**faux**), tous deux écrits APRÈS la MAJ. ⛔ **Le `git blame` ne tranche pas** — mesuré : sur les 7 sites ambigus postérieurs à la migration, **6 recopiaient l'ancienne valeur**. Une correction par « décalage » casserait donc la citation juste tout en réparant les six autres. Fermer un site = relire quel trigger natif il cite (RE par site, pas migration). Le geste utile est de rétablir la paire `On(<ordinal> = <Membre>)`, qui rend le site **gardé** par `probe_283 --step prose`. Re-dériver : `python scripts/python/probe_283_enum_ordinal_sweep.py --step on --racine <racine>`. |
| #283-r2 | **`docs/` non migré : 394 citations dérivées, 356 à signature « ancien ordinal »** | `[opus]` | `case-283` §7. Choix assumé, cohérent avec `case-272` §5 (« les lire comme des étiquettes historiques, se fier au nom jamais au nombre ») et `case-254b-b` §7 (on ne rétro-corrige pas un compte rendu produit par un autre build) : les case-docs sont **datées**. L'outil existe et le lot est jouable d'un coup — `python scripts/python/probe_283_enum_ordinal_sweep.py --step prose --racine docs --fix` — si on décide l'inverse. Décider AUSSI de l'estampille de build des docstrings (« RE décompilé ghidra, build `gqfc5mff6c` ») : plusieurs annoncent un build qui n'est plus installé, gisement distinct non traité. |
| #330-r1 | **`docs/` : 4580 VA absolues migrables, dont 4278 PÉRIMÉES AVÉRÉES** — et la migration naïve les rendrait toutes FAUSSES | `[opus]` | `case-330-va-et-estampilles-dans-la-prose.md` §2/§3. Chiffres re-dérivables : `python scripts/python/probe_330_prose_va_and_build_stamps.py`. **Le piège avant tout** : les 4278 résolvent, contre la table COURANTE, sur un symbole DIFFÉRENT de celui qu'elles désignaient — migrer via `ghidra_symbols.py whereis` produirait 4278 citations fausses mais d'apparence propre, strictement pire que l'état actuel. Toute migration doit lire la table du build **d'origine**. Gisement actionnable = les 1511 périmées des 32 fichiers de **RÉFÉRENCE** (`runner-engine.md` 201, `playbook/prediction.md` 177, `dsl-effect-nodes.md` 141, …) ; les case-docs sont datées (arbitrage `case-254b-b` §7 déjà rendu). 20 occurrences restent légitimement en VA (15 slots `methodPointers`, 5 `FUN_`), listées par `--list-placeholders`. |
| #330-r2 | **57 estampilles de build périmées dans des documents de RÉFÉRENCE** | `[opus]`+arbitrage | `case-330` §4. Chiffrage du gisement que #283-r2 avait nommé sans compter (208 estampilles au total, 5 builds distincts, 154 fichiers). `.claude/` est traité et le cliquet y est **armé et vert** (`probe_330 .claude --fail-on-header-stamp`). Reste à trancher pour `docs/` : une case-doc datée est exacte, un document de référence lu comme état courant ne l'est pas. **À arbitrer par l'orchestrateur** : `.claude/skills/tacticus/references/runner.md:124` (`!include`-é dans `CLAUDE.md`, donc hors périmètre d'un agent) — mesure datée à re-dériver, pas estampille à réécrire. |
| ~~#339-r1~~ | ~~`active_ability.py:110` : `MinMaxDamageAverage` TRONQUE~~ | **FERMÉ (#344)** | `case-344-deux-moyennes-de-prediction.md`. Le site n'avait pas UN artefact mais DEUX : le playbook passe soit `<X>Ability$$GetDamageAmountMain` (→ `MinMaxDamageAverage`, demi-vers-le-pair) soit `<X>Ability$$GetDamage` (→ `MinMaxDamage(isPrediction: false)` = `RandomAmount`, pris au slot 4 = `AAmountFormula$$CalculateAverage`, TRONCATURE). 18 abilities de chaque côté (xrefs des deux corps dédupliqués). Registre `_PREDICTION_MINMAX_AVERAGE` ; défaut = troncature (statu quo). Mesuré live des deux côtés. |
| ~~#339-r2~~ | ~~`votann.py:387` : `// 2` sur un `Half(Sum(...))`~~ | **FERMÉ (#344)** | `case-344` §3. `AncestralFortuneAbility$$GetAttackTarget` passe `MinMaxDamage(isPrediction: **true**)` = `Half(Sum(...), 0)`, et `SortUnitsByDamageUtilitySelector$$Select` l'évalue au **slot 1** (`Calculate`) → `DivideAmount$$Calculate` → demi-vers-le-pair. Corrigé. |
| ~~#339-r3~~ | ~~Trois moyennes à QUALIFIER~~ | **FERMÉ (#344)** | `case-344` §3. `darkangels.py:910` = `MinMaxDamage$$Avg` → demi-vers-le-pair (corrigé) ; `damage_hits.py:52` = `HitDamage$$GetDamage`, division entière C sans Fix64 → **la troncature est JUSTE** ; `unit_context.py:93` (`normal_base`) = aucun symbole, **zéro consommateur** → retirée. |
| ~~#344-r1~~ | ~~**~60 abilities dont la forme de moyenne de prédiction n'est PAS LUE**~~ | **FERMÉ (#350)** | `case-350`. Inventaire CLOS : la moyenne ne peut naître que de `AActiveAbility$$MinMaxDamage{,Average}` (xrefs énumérées) ou d'un `DSLFormulas$$Half`/`$$Divide` INLINE (2 playbooks). **+18** en forme (a) demi-vers-le-pair, réparties en 4 sous-chaînes tracées ; **+1** en (b) ; **7** abilities dont la base n'est PAS une moyenne, nommées dans `_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE`. Quatre corrections confrontées LIVE (ex. 1177 `LightOfSanguinius` : natif `(120,180,5)`, troncature `(115,175,5)`). Résidus ouverts : `#350-r1`, `#350-r2`, `#350-r3`. |
| ~~#350-r1~~ | ~~**`SorcerousFacade` (1100) : le natif émet DEUX events de dégât, le port UN**~~ | **FERMÉ (#351)** | `case-351-facade-event-count.md`. Ce n'était pas une mécanique native à découvrir mais un **fork de port** : le playbook Python reconstruisait les deux events à la main (juste), le chemin générique **substituait** l'attaque normale au batch là où `MakeDamagePredictions` fait `list = [normale]` puis `AddRange(batch)` — d'où 1 event contre 2, tous deux sur `sel`. Le nom `_PREDICT_VIA_NORMAL_ATTACK` était la cause racine (il disait « au lieu de », le natif dit « avant ») → `_PREPEND_NORMAL_ATTACK_EVENT` ; `_PLAYBOOK_PROFILE_OVERRIDE[1100] = "None"` posée et **plus inerte** ; le playbook DÉLÈGUE et ne garde que la substitution de cible. Confronté live (`thousTzaangor`/MC1_67) : natif `((3935,5903,1),(30,46,1))` sans armure et `((1623,3591,1),(1,1,1))` avec, **les deux chemins du port bit-exacts**, deux A/B causaux. `probe_344` sur 1100 n'est plus muet : `to_even` seule nulle sur les deux bras (troncature : `(30,44,1)` ✗) → l'inscription `(a4)` de #350 passe de **lue** à **confrontée**. ⚠ Réfute au passage `case-171` (« l'oracle ne remonte pas l'event #2, dedup aval ») : `count = 2`, aucun dedup. |
| ~~#350-r2~~ | ~~**Trois bases de prédiction qui ne sont PAS une moyenne, non corrigées**~~ | **FERMÉ (#352 + #353)** | Les trois sont portées et confrontées live, et **les trois lectures de #350 étaient inexactes**. `case-352` : **1098 PlasmaGrenade** = `Get(minDmg)` SEUL + hits `nrOfHits` **littéral** (le générique ajoutait `ExtraHits`) ; **1048 FragstormGrenadeLauncher** n'était pas « `maxDmg` seul » — son playbook n'appelle **pas** `GenerateMultiHitAttackPredictions` mais la surcharge « amount » de `IBattleQuery.GetAttackPrediction`, qui pose **`hits: 1` en dur** → **UN coup de `nrOfHits × maxDmg`** (`(12354,19534,1)` natif contre `(1938,7344,6)` avant). `case-353` : **1059 RammingSpeed** n'a pas pour formule `ExplodesAbility$$GetDamage` — ce corps n'alimente que ses batchs 3/4, **conditionnels** ; le batch principal prend `Get(minDmg)` + hits `0x2f` littéraux, plus un batch SELF (`hits 0x32`). Résidu ouvert : `#353-r1`. `_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE` est désormais **corrigée sur ses 7 entrées**. |
| #352-r1 | **Les volets secondaires de 1098 et 1048 sont MORTS — ne pas les « réparer »** | *fermé, à ne pas rouvrir* | `case-352` §3. Les deux playbooks bouclent bien sur `SelectUniqueUnits(<GetOtherTargets>, entities, 3)`, mais évaluent ce sélecteur sur un `AbilityEntities` **incomplet** (1098 : `caster: 0` ; 1048 : `memset(0)` complet), alors que les deux sets dépendent du caster → toujours vides. Mesuré sur la MÊME géométrie : natif **1051 = 3 events** (son set `AdjacentUnits(Target)` ne dépend que de la cible, volet VIVANT et porté), natif **1098 = 1** et **1048 = 1** (gate `WillBeKill` pourtant franchi). Le port, qui n'émet qu'un event, est FIDÈLE : y ajouter un volet le rendrait FAUX. |
| ~~#353-r1~~ | ~~**`RammingSpeed` (1059) : volet (a) FERME, volet (b) ouvert**~~ | **LES DEUX VOLETS FERMES (#381)** | `case-353` §5bis. **(a) Port — FAIT.** `RammingSpeedAbility$$GetTileToMoveTo` est porte (`orks.py::ramming_speed_tile_to_move_to`), avec les DEUX manques comples : l'utilite **54 `RammingSpeed_MostAdjacentEnemies`** (`engine/utilities/ramming_speed.py`, cle BC `RAMMINGSPEED_AdjacentEnemy` = 20 RESOLUE au litteral IL2CPP par `probe_212`, jamais devinee) et le **`UtilityBucket` a DEUX `WeightedUtility`** (`engine/utilities/decider.py` : mirrors de `WeightedUtility`/`UtilityBucket`/`UtilityDefinition`/`UtilityDecider.CalculateUtility` — somme PONDEREE, poids par defaut **1**, `minUtilityDifference` par defaut **0**). **Deux rectifications de l'enonce herite** : l'intersection a `MovableTilesInRange` a **GAUCHE** (`GetTileToMoveTo` n'appelle PAS `TilesUnitCanMoveToChargeTarget`) — et l'ordre est OBSERVABLE, le tri etant stable ; et la query de la feuille est `GetAdjacentEnemies(tuile CANDIDATE, case.unit, false)` — tranchee par l'**arite** (3 args), pas par un numero de slot recopie. **CONFRONTE LIVE 2/2 MATCH** (`probe_353r1_ramming_speed_charge_tile.py`, MC1_67, runners 57/58) et SANS capteur neuf : la tuile se lit dans la **position d'arrivee du caster apres un cast natif de 1059** (`ExecuteBehaviour` = `If(!IsAdjacent, MoveUnit(caster, GetTileToMoveTo()))`). Deux bras, chacun avec sa mutation DIVERGENTE : le terme 54 tranche (port (5,7) contre `Tile(7)` seul (3,7)) ; l'ordre tranche (port (3,7) contre operandes intervertis (4,8)). La **SOMME** est confirmee au passage : la tuile au `u54` MAXIMUM (une `Swamp`, `Tile(7) = -20`) n'est PAS celle que le natif choisit. Gardes : `tests/engine/runner/test_353r1_ramming_speed_charge_tile_offline.py` (10). **(b) Mesure — CAUSE ISOLEE (#372 + #361 + #365), maillon interne ouvert.** `case-361-explosion-batches-gate.md`. **Neuf causes tombees.** #372 : `CannotBeGuaranteedKilled` exclu par les xrefs (unique ecrivain `PredictNormalAttack`, la voie playbook passe par `GetMultiHitAttackPrediction` qui `memset(0xa0)`), borne par defaut exclue par la mesure, et **`blockScenarioCount = 0`** une fois le capteur deploye ⇒ **le PREDICAT de la gate est VRAI** (`willBeKill = true`, hp 60 <= 104). #361 en ecarte trois de plus, chacune par une mesure : **voisinage** (geometrie DRIVEE ou la tuile d'arrivee porte **1 ami + 2 ennemis** — attendu 5 events, natif **2**) ; **pool de tuiles** (le cast REEL pose le caster en (5,7) == la tuile du port ; et `GetDynamicInvalidTargetReason` evalue le MEME arbre dans un contexte ou seuls `+0x08/+0x10/+0x40` sont poses, **sous-ensemble** de celui de `GenerateAttackPredictions`) ; **lecture du flag** (`StormOfFlensingBladesPlaybook`, dont le compte ne depend QUE de `get_WillBeKill` : **2 events quand FAUX, 0 quand VRAI**). **Capteur DEPLOYE** (`frida/hooks/features/ai-step/playbook-gate-probe.ts` + flag `gateProbe` d'`aiPlaybookPredict`, intercepte `get_WillBeKill` le TEMPS d'une invocation, filtre par thread, detache en `finally` ; `_gate_verdict` verrouille par `tests/engine/test_361_gate_probe_tristate_offline.py`) : il rend **TRUE, 1 appel** ⇒ la gate OUVRE, la cause est en AVAL. #365 l'ISOLE, par exhaustion + deux mesures. **(i) Partition** : `DSLSelectors$$Friends`/`$$Enemies` allouent le MEME `UnitsFromFactionSelector` a un bit pres et PARTITIONNENT leur entree par `UnitExtensions$$HasFaction` ⇒ les deux batchs vides <=> `AdjacentUnits(GetTileToMoveTo(), 1, 3)` vide. **(ii) La composition est VIVANTE** — `probe_361_adjacent_units_selector.py`, **3/3 bras exacts** sur les deux SEULS autres appelants de `GenerateAttackPredictions` (xrefs) : `1004 MortisRound` (`Entity(target)`) rend 1 event ; `1170 ExplosivePresents` (`(Target@0x60 + AdjacentUnits(Target@0x60,1,3)) - Caster@0x48`) rend **3 events, cibles exactes**, caster LOIN puis caster POSE adjacent (retire par la soustraction). Garde adversariale `--mutate no-subtraction` : ROUGE `COMPTE DIFFERENT : 3 events pour 4 attendus`. **(iii) L'arbre rend VIDE, pas une tuile isolee** — `probe_361_ramming_speed_forced_tile.py` sature le ring de la cible : les 4 tuiles encore candidates portent CHACUNE 2 unites adjacentes, gate OUVERTE, natif **2 events** ; et le 2e tir, caster AYANT la main (`aiMovableTiles` = **13 tuiles**), donne encore **2** — l'explication de montage est refutee. **CAUSE** : `RammingSpeedAbility$$GetTileToMoveTo`, evalue dans le contexte de `ComparablePlaybook<T>$$GenerateAttackPredictions`, rend VIDE, alors que le MEME arbre rend la bonne tuile dans celui de `GetDynamicInvalidTargetReason` (cast reel MATCH 2/2). **Residu = le maillon INTERNE** (`case-361` §9) : les deux contextes ne different que par `+0x18`/`+0x38`/`+0x48`, un seul noeud change de branche (`CasterTileSelector` lit `ctx+0x48` en PRIORITE, nul au gate), et `MovableTilesInRangeSelector$$Select` est le SEUL retour vide silencieux de la chaine haute. **Capteur a poser** : `IdunBattle.Entities.Selectors.MovableTilesInRangeSelector$$Select` (unite / tuile de depart / taille du retour) — un seul hook separe les trois hypotheses. ⚠ **La derniere phrase de ce volet (« le natif n'emet aucun batch, c'est ETAYE ») est REFUTEE par #370 — voir `#361-r2`** : sur la geometrie EXACTE de `case-361` §1 et avec le build STRICTEMENT identique, le natif emet **5 events == 5 attendus** des que le montage change de chemin. Le vide etait un artefact de `probe_361`. **VOLET (b) FERME (#381), et sa CAUSE etait le MONTAGE, pas le natif** : `case-361` paragraphes 1-4. Tout le recit ci-dessus qui conclut « l'arbre `RammingSpeedAbility$$GetTileToMoveTo` rend VIDE dans le contexte de `ComparablePlaybook<T>$$GenerateAttackPredictions` » est **REFUTE**. Le natif emet ses batchs 3/4 et les emet JUSTES (5 events == 5 attendus, cibles exactes, cast reel MATCH) des que le caster A LA MAIN -- `IdunBattle.Core.Services.MovementQuery$$FindAnyOrAllMoveableTiles` rend aussitot, `OrderedSet` VIDE et sans erreur, quand `UnitFlagsComponent$$Has(unitFlags, 1)` est vrai et `ignoreUnitFlags == 0` (le litteral que le selecteur passe, MESURE par le capteur). Les deux mesures citees ci-dessus comme decisives portaient chacune un artefact : le bras principal laissait le caster hors de son tour (parade : `ensure_turn`, garde adversariale `--no-ensure-turn` -> 2 events pour 5) ; le bras (iii) « ring sature » lisait la portee NATURELLE de l'unite (13 tuiles) au lieu de celle du selecteur (23) et n'a jamais teste si une tuile de charge etait ATTEIGNABLE -- intersection VIDE, pathfinding bloque. **Les batchs 3/4 sont PORTES et confrontes 4/4 par #383** (`case-383`) ; reste ouvert : `#381-r1` (mordant) et `#383-r1` (la face COMBAT hors `ABILITY_CLASSES`). |
| ~~#361-r2~~ | ~~Le capteur du maillon interne de `GetTileToMoveTo` est LIVRE et INERTE~~ | **FERME (#381)** | `case-361-explosion-batches-gate.md`. Capteur `frida/hooks/features/ai-step/movable-tiles-probe.ts` + flag `tileProbe` d'`aiPlaybookPredict` : CHARGE (session 4) et EXPLOITE. Il lit la forme `OrderedSet`1` (correctif #374, reconnaissance par la chaine d'heritage IL2CPP jusqu'a `List`1`, stride interroge et non suppose) ; decodeur `_tile_verdict` a **11 etats deux a deux distincts**, garde `tests/engine/test_370_tile_probe_tristate_offline.py`. Le residu (3) -- « quel element du montage de `probe_361` vide le pool » -- est TRANCHE par #361-r3.
| ~~#361-r3~~ | ~~Le pool rend 51 entrees, la perte des batchs 3/4 est en AVAL~~ | **FERME (#381) -- la premisse etait INVERSE** | `case-361` §1-§4. **Les 51 tuiles etaient lues sur un bras SANS deficit** (les deux bras de `probe_361_movable_tiles_selector` emettaient 4==4 et 5==5) : il n'y avait aucune perte a expliquer, et le verdict `MAILLON TRANCHE ... la perte est en AVAL` etait un **faux vert** -- une phrase du decodeur, pas une mesure. Dans le SEUL regime deficitaire (`probe_361`, 2 events pour 5), le capteur rend `query-vide` : pool **0**, classe `OrderedSet`1` sur les 4 appels. La classe ecarte les deux early-returns du selecteur ⇒ `IBattleQuery.GetMovableTilesFor` a REPONDU, et vide. Donc `op_BitwiseAnd` / `SortTilesByUtility` / `First` operent sur un pool DEJA VIDE : **hors de cause**. **Foyer** : `IdunBattle.Core.Services.MovementQuery$$FindAnyOrAllMoveableTiles` ouvre sur `if ((UnitFlagsComponent$$Has(unitFlags,1) && ignoreUnitFlags==0) || !UnitExtensions$$CanMove(unit)) return;` -- l'`OrderedSet` alloue par `MovementQuery$$GetMovableTilesFor` repart VIDE, sans erreur. `_ignoreFlags = 0` est MESURE par le capteur. **Branche tranchee = le FLAG**, sans aucun nouveau hook : le RPC `aiMovableTiles` appelle la MEME surcharge, et avec `side="all"` + `overrideRange` il reproduit l'appel du selecteur. `probe_381_movable_tiles_query_gate.py` balaie les tours sur geometrie FIGEE -> pool **51/0/51/0** (caster (1,4), tuile (5,7), attendu 5) et **28/0/28/0/28/0** (caster (6,7), tuile (3,5), attendu 4), events 5/2 et 4/2, requete nue en accord 4/4 puis 6/6. **CONSEQUENCE : les batchs 3/4 SORTENT et sont EXACTS** -- `probe_361_ramming_speed_explosion_batches` passe au VERT sur SON montage (5 events == 5, cibles exactes, cast reel MATCH (5,7)) par l'ajout d'`ensure_turn` apres le drive. Garde adversariale `--no-ensure-turn` : meme build, meme seed, meme geometrie -> 2 events pour 5, `BRAS NON DISCRIMINANT`. **Deuxieme artefact, distinct** (`probe_361_ramming_speed_forced_tile`, ring sature) : `MovableTilesInRange` est un PATHFINDING, les 4 candidates sont a portee hexagonale mais l'intersection avec les 23 tuiles atteignables est **VIDE** -> les batchs manquent LEGITIMEMENT. Ce bras concluait « ARBRE VIDE » d'un compte d'events sans lire le pool, et sa garde de portee lisait la portee NATURELLE (13) au lieu de celle du selecteur (23) : corrige, il rend `BRAS NON DISCRIMINANT`. Gardes : `tests/engine/test_381_query_gate_offline.py` (12, offline, 7 etats distincts + le piege `side="friendly"` qui ferait mesurer la moitie qui marche) ; `probe_361_movable_tiles_selector` REFUSE desormais de conclure quand son bras B n'est pas deficitaire (`REGIME DEFICITAIRE NON REPRODUIT`, rc 1).
| ~~#381-r1~~ | ~~**Le port de `MovableTilesInRange` ignore le BLOCAGE par les unites**~~ | **FERME (2026-08-01)** | `case-381-r1-movable-tiles-pool.md`. La cause n'etait PAS le blocage par les unites : derriere l'intersection `CanAddUnit(...)` le filtre d'occupation est INOBSERVABLE. Le 4e argument du noeud n'est pas un `canReachOnly` mais **`ignoreFlags`** (il ne touche que la garde d'entree de `MovementQuery$$FindAnyOrAllMoveableTiles`), le 5e (`ignoreUnitsOnTiles`) vaut **0 sur les cinq call-sites lus**, et `MovementQuery$$AnyOrFillMoveableTiles` termine TOUJOURS par `RemoveAll(t => !IsMovableTile(unit, t, ignoreUnitsOnTiles))`. Ce qui mordait est le **gate d'expansion #131** (`BasePathfinder$$NodesInNextLevel` -> `IsValidContinuePathTile`), que le noeud DSL ne posait pas : sur `C1_74` (2,4) et (4,4) ne pendent que d'un Swamp (mesure offline : 35 tuiles sans le gate, 29 avec). Le noeud porte desormais les TROIS etages (stop-set, gate #131, dispatch `IsLikeFlying`) + l'occupation par EMPREINTE. Confronte a `aiMovableTiles` (le RPC appelle litteralement la meme fonction native) : `MC1_67` 9/9, `C2_26` 9/9, `PVP_desert_04` 9/9, `C1_74` 8/9 sur les WALK ; 2 gardes adversariales rouges. Sur la geometrie de `case-383` sec.5 le port designe desormais **(4,3)**, la tuile du natif. Probe `probe_381r1_movable_tiles_pool.py`, gardes `test_381r1_movable_tiles_pool_{live,offline}.py`. |
| #381-r2 | **`FlyPathfinder` : le port n'itere pas le bon voisinage** | `[opus]` | `case-381-r1` sec.5. `FlyPathfinder$$AddNeighbours` (d__7) itere `GetSurroundingTiles(tile, 1)` -- le voisinage **GEOMETRIQUE** (triple boucle cube de `TileQuery$$IterateSurroundingTiles`) -- la ou `BasePathfinder$$AddNeighbours` (d__19) itere la liste d'adjacence **STOCKEE sur la tuile**. Le port `entities/pathfinding/fly_pathfinder.py` reutilise le BFS commun, donc le second : il SOUS-ATTEINT des que le graphe capte a une arete manquante. MESURE (`probe_381r1_movable_tiles_pool.py`, `bloodIntercessor`) : natif 47 / port 27 (`MC1_67`), 46/44 (`C1_74`), 32/28 (`C2_26`), EGAL sur `PVP_desert_04`. Frappe AUSSI `ai/state_bridge._move_tiles`, jamais confronte sur une unite volante (`test_block_entering_tiles_live` ecarte explicitement les volantes). |
| #381-r3 | **Le voisinage du BFS : `adjacency="evenq"` contre le champ `neighbours` du boardGraph** | `[opus]` | `case-381-r1` sec.5. Sur `C1_74`, `tauAunShi` sur-atteint de 2 tuiles ((4,2) Swamp, (5,3)) -- et ce n'est PAS le noeud DSL : `ai/state_bridge._move_tiles` rend le MEME ecart bit a bit. Le `Board` des tests/probes est construit `adjacency="evenq"` (voisinage hexgeo RECALCULE) alors que le natif itere `tile.Neighbours` ; sur `C1_74` les deux vues different sur **32 tuiles**, et remplacer l'une par l'autre donne 32 tuiles la ou le natif en rend 34 -- donc le champ CAPTE est lui-meme incomplet. A trancher sur le CAPTEUR (`boardGraph`), pas sur le pathfinder. |
| #381-r4 | **Les collapses IMPERATIFS de `MovableTilesInRange` ne portent ni le gate #131 ni le dispatch fly** | `[opus]` | `case-381-r1` sec.5. Trois sites : `runner/abilities/genestealer._charge_candidate_tiles` (HeroicFusillade / VigilanceEternal), `runner/operations/triggers/loki/betrayer._betrayer_stop_tile`, `runner/operations/triggers/genestealer._hypersensory_move_dest` (portee 1 -> gate structurellement inerte). Ils appellent `walk_pathfinder.get_movable_positions` sans `can_continue` ni `IsLikeFlying` : meme sur-atteinte que celle fermee par #381-r1 sur le noeud DSL. Correctif = recopier celui de `entities/selectors/tiles.MovableTilesInRange`, avec re-jeu des tests live de chaque ability. Docstrings deja rectifiees. |
| ~~#350-r3~~ | ~~**Formes LUES mais NON confrontables par le gabarit `probe_344`** — murs (b) et (c)~~ | **FERMÉ (#350-r3bc)** | `case-350r3-porteur-mow-et-formule-triggered.md`. **(b)** Garde EXPLICITE et structurelle (`pool_regular = normalized - mow`), chemin MoW DÉJÀ câblé (`--p-mow`) : rien à assouplir. Le mur restant n'est pas le déploiement — avec la MoW pour caster, l'oracle rend `listNull` et `ai/context.py` ne construit **aucun** `ctx.me`. Confrontation par GREFFE : `1147` = `to_even` SEULE nulle sur les deux bras (natif `(324,492,6)` vs trunc `(324,480,6)`) ; `1148` en accord dans les **deux** régimes de feu — et un **bug de port fermé** au passage (zone froide : natif ∅, port `(81,123,3)` → `_MAKE_DMG_TARGET_GATE`). **(c)** Le playbook évalue `GetAbility(0x4ec)` = `TriggeredAbilityType.HeavyRailRifle_Attack = 1260`, pas 1160 : l'inscription ne manque **pas**, l'y poser serait faux d'enum ET d'objet. |
| ~~#350-r3a~~ | ~~**Face NonComparable : le « 0 event » est JUSTE, et l'oracle est ailleurs**~~ | **FERMÉ (#356)** | `case-350r3-oracle-noncomparable.md`. **L'énoncé « il manque un oracle » était à corriger sur son axe** : `aiPlaybookPredict` ne peut rien rendre pour un NonComparable, et c'est la RÉPONSE JUSTE — `ComparablePlaybook`1` et `NonComparablePlaybook`1` sont deux enfants **FRÈRES** de `Playbook`1`, et les **4** `Make*Predictions` ne sont déclarées que sur la branche Comparable (`NonComparablePlaybook`1` n'a que `EvaluateInternal` + 2 générateurs de bucket) ⇒ `makeArity 0` / `listNull`, pas un silence. **Portée** : **134** classes de parent direct `NonComparablePlaybook`1` contre **96** Comparable — le mur ne valait pas 4 abilities mais la moitié du catalogue. **Mais la prédiction EXISTE** : les deux surcharges « triplet » de `Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent` appellent `IBattleQuery` slot `0x28` puis `IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor` — un NC construit le MÊME event, il le CONSOMME au lieu de le RENDRE. D'où `ncPlaybookPredict` (`frida/hooks/features/ai-step/rpc-nc-predict.ts`), hook **fenêtré** sur ce ctor (attaché/détaché autour de l'invocation, jamais permanent : le ctor est chaud), décodé par le `readDamageEvent` EXISTANT — zéro layout neuf. Relevé au passage, **non intégré à #350** : le **slot** d'`IAmountFormula` n'est pas constant (1132/1202 = **4** `CalculateAverage`, 1111/1173 = **1** `Calculate`) et `AAmountFormula$$CalculateAverage` retombe sur `Calculate` selon le prédicat de vtable `+0x1c8` — la coïncidence des deux slots est une propriété du NŒUD, pas des slots. Garde : `probe_350r3_noncomparable_oracle.py`. **DÉPLOYÉ et CONFRONTÉ le 2026-07-31** (session Frida 2) : étapes 0 et 1 **VERTES**, et surtout **le verrou d'auto-validation du capteur PASSE** — sur `deathBlightlord`/`1042` (Comparable), `via=makeDamagePredictions` rend `capture=1 rendue=1 identiques=True`, donc le capteur lit la bonne struct (`ProbableDamageEvent` = `System.ValueType`, `args[0]` = base de struct). **Les 5 étapes sont VERTES depuis #356** (le rouge des étapes 2-3 accusait le MONTAGE, pas le port). |
| ~~#350-r3a-r1~~ | ~~**Le capteur est validé, mais la face NC ne produit AUCUN event**~~ | **FERMÉ (#356)** | Lecture **(a) MONTAGE**, prouvée. La précondition de `1202` est lue au décompilé dans `VigilanceEternalAbility$$GetDynamicInvalidTargetReason` (adjacence, **sinon** `DSLSelectors$$TilesUnitCanMoveToChargeTarget(..., GetNumberConstant(0x16))` non vide, **sinon** `0x8000000` = `TargetIsInRange`) ; aux tuiles de spawn de `MC1_67` le caster est à **10-11 hex**, donc bucket vide **JUSTE**. Positions PILOTÉES (3 rounds, runner `--no-ai`, les deux camps avancent) → `abilityReason` passe de `0x8000000` à `0x0`, et l'oracle rend `capture=1` : `tgt=79 healthDmg=[1938,2904] hits=3 prob=1`, `bucketUtil=25.3800189` ; `ncEvaluate` 17 positions / **16 scorées**. **L'oracle NC est OUVERT** (134 classes redeviennent observables). ⚠ `ncEvaluate.hvt` (`HasValidTargets`, slot 0x3f) valait **true 13/13** sur le montage à éligibilité VIDE — ce n'est PAS une preuve de régime. Le probe sépare désormais **trois** issues (régime non atteint = `NON CONFRONTÉ`, rc 2 ; `--max-rounds 1` l'exerce). `case-350r3-oracle-noncomparable.md` §6-7. |
| ~~#350-r3a-r2~~ | ~~**`probe_344` n'a pas d'oracle sur la face NonComparable**~~ | **FERMÉ (#356)** | `probe_344 --oracle auto` commute sur `ncPlaybookPredict` dès qu'un playbook NC est porté, et compare à `generate_multi_hit_attack_prediction` (chemin exact du playbook NC porté) ; même point de branchement patché (`AActiveAbility.get_damage`). L'anneau de `_place_ring` satisfait la précondition **par construction** et `_nc_regime` le VÉRIFIE. `custoKyrus`/`1202` : bras A (83 = 3 mod 4) natif `(99,147,3)` → seul `trunc` ; bras B (73 = 1 mod 4) natif `(87,129,3)` → `to_even`+`trunc` ⇒ intersection **`trunc`** = ce que `_PREDICTION_MINMAX_RANDOM_READ` prévoit ; le code LIVRÉ égale le natif sur les deux bras. Durcissement au passage : `probe_344` **refuse (rc 2)** une ability hors des deux registres d'arrondi — `--oracle auto` ouvrait des playbooks NC dont l'utilité n'est PAS un dégât (`DarkTalonStrikePlaybook` score `Fix64(GetAttackTargets(GetTilesInBestLine()).Count)`), où une capture nulle est LÉGITIME et où `expected` aurait été fabriqué. |
| ~~#350-r3b~~ | ~~La couche TRIGGERED a ses DEUX formes de moyenne, lues et non portées~~ | **FERMÉ (port livré)** | `case-350r3b-moyennes-triggered.md`. La forme sort de la **structure du nœud** × le **slot** invoqué, pas d'un helper : `BaseTriggeredAbility$$MinMaxDamage` rend `RandomAmount(mn,mx)` lu au **slot 4** (`AAmountFormula$$CalculateAverage` = troncature) ; `$$MinMaxDamageAverage` rend `Half(Sum(Direct(mn),Direct(mx)),0)` lu au **slot 1** (`DivideAmount$$Calculate` → `RoundFix64Result(.,0)` = demi-vers-le-pair). **6 call-sites / 4 playbooks** re-dérivés des xrefs — la prémisse « 2 vs 4 playbooks » était juste en nombre, fausse en attribution (4 SITES = 2 playbooks). Livré : `entities/abilities/triggered_ability.py` (registre `TRIGGERED_PREDICTION_AVERAGE_FORM` + foyer, call-site inconnu → `KeyError`), les 3 slots manquants d'`IAmountFormula` sur `AAmountFormula`, `RandomAmount$$CalculateMin/Max`, Fury recâblé. **Confrontation live : la face troncature est réconciliée (#32/#339) ; la face demi-vers-le-pair NE L'EST PAS** — ses 4 call-sites rendent une *utilité*. ⚠ **Deux points de cette fiche sont corrigés par #369** : (1) l'oracle N'EXIGE PAS de hooker `CalculateUtilityFromDamageEvent` — les 4 call-sites traversent le capteur `ProbableDamageEvent$$.ctor` DÉJÀ posé (3 directement, le 4ᵉ via ses délégations à `…ForMainTarget`/`…ForSecondaryTarget`), et la valeur demi-vers-le-pair y entre par l'argument `damage` de `GetAttackPrediction` ; (2) **`HeavyRailRiflePlaybook` n'est PAS un playbook triggered** — son parent est `NonComparablePlaybook`1` (`classes.tsv`), c'est un playbook ACTIF qui lit une ability triggered par `GetAbility<T>`. |
| **#369** | **`ncPlaybookPredict` indexé sur `ActiveAbilityType` : rend une valeur pour la MAUVAISE ability, jamais une erreur** | **CORRECTIF LIVRÉ, INERTE — fenêtre de reinject requise** | `case-369-oracle-triggered-playbook.md`. `PlaybookDatabase` porte **4** entrées à key-spaces distincts ; le harnais figeait `ActiveAbilityType`. Collision mesurée : **233** ids communs aux deux enums, dont **231** de nom différent (`rnca9r7q6c`) — re-mesuré live : `1103`→`SuperchargePlaybook`, `1054`→`CallRipperSwarmsPlaybook`, `1247`→`DefaultActiveAbilityPlaybook`. Livré : `triggered-predict.ts` (chargement par key-space + `UtilityAttackCase$$Base` + `CalculateAttackUtilityInSteps`), `abilityKind` ÉCHOÉ dans la réponse (c'est ce qui rend un vieux hook DÉTECTABLE), `allowDefault:false` par défaut (**vérifié : les 8 abilities des consommateurs existants sont toutes bespoke**), et le montage `patch_ability_variables` qui force `mn+mx == 3 mod 4`. Garde offline vue ROUGE sur **3** mutations. **CONFRONTÉ après reinject (2026-07-31, #375)** : routage vert pour les trois ; l'invocation gshared aboutit (le doute sur la résolution depuis la classe concrète est levé) ; les `captured` portent bien **972**. |
| ~~**#375**~~ | ~~**Le capteur `triggered-predict.ts` est ARMÉ mais MUET** : `capturedCount: 0` pour les trois abilities~~ | **FERMÉ (2026-07-31)** | `case-375-capteur-triggered-muet.md`. **Ni (a) capteur non armé, ni un trou de harnais : DEUX verrous, plus un troisième découvert en confrontant.** **(A)** `buildUtilityAttackCase` passait un `Nullable<AbilityOrEffect>` **zéro-rempli** ; `TriggeredAbilityPlaybook<T>$$IsRegularAttack` commence par `get_HasValue()` sur `case+0xf0` et refuse en tête des DEUX machines à états qui construisent un `ProbableDamageEvent` (`LightImUpPlaybook` teste `IsMeleeAttack` PUIS `IsRegularAttack` ; `MassiveScythingTalonsPlaybook` teste `IsRegularAttack` en 1ʳᵉ instruction) → `yield Fix64(0)` unique. `capturedCount: 0` était donc la réponse EXACTE du natif. (a) est RÉFUTÉ par mesure : même montage, même capteur, `via: attackUtilityForMainTarget` rend `capturedCount: 1`. `1247` est muet pour une raison DIFFÉRENTE — `FuryOfTheAncientsPlaybook` **ne surcharge pas** la voie attaque (corps de base = un 0) ; sa prédiction slot-4 vit sur la voie MOUVEMENT. **(B)** la fixture de #369 était **écrite mais jamais jouée** : `_load_seed_bc` re-synthétise `BC.Abilities` depuis le gameconfig vivant (rattrapage #254) et revertait `minDmg`/`maxDmg` EN SILENCE (mesuré : `20000` sur disque → `831` relu) — le couple joué était le nominal `831+1109 ≡ 0 mod 4`, non discriminant. Parade : sidecar `<seed-bc>.pins.json` opt-in et nommé, config re-synthétisée AVANT patch, épingle orpheline qui LÈVE. **(C)** l'écart de 1 n'est observable qu'à `--armor-target 0` : à l'armure nominale l'étage aval (profil × armure) l'écrase (971 et 972 → tous deux `healthDmgMin = 175`) et un verdict lu là serait **vert et vide** ; l'étape 4 exige donc `REF 971 != REF 972` avant de conclure. **Résultat : le natif joue 972** — `(1166,1748)` / `(1167,1749)` / `(1167,1749)`, reproduit sur un 2ᵉ couple discriminant (`700+1003` → 851/852) et un 2ᵉ couple (board, seed). **Résidu, INERTE en attente d'une fenêtre de reinject** : `attackAbility: <id> \| "normalAttack"` sur `ncPlaybookPredict` + écho `gates` — c'est ce qui dé-muselle `attackUtilityInSteps` et NOMME un zéro. |
| ~~#359~~ | ~~**Le volet AoE de `1147 HadesAutocannons` : natif 2 events, port 1** — écart AFFICHÉ, jamais gardé~~ | **FERMÉ (#359)** | `case-350r3-porteur-mow-et-formule-triggered.md`. Ce n'est **ni un second batch ni un sélecteur secondaire** : `HadesAutocannonsPlaybook$$MakeDamagePredictions` boucle sur `GetEntitiesFromSelector(HadesAutocannonsAbility$$GetAllTargets, …)` = `UnitsWithTrait(Friends(of: Target@0x60, SurroundingUnits(Target@0x60, ConfigConst(0x16 = range), includeCenter: 1)), 2 = Summon)` — les summons du camp de la **CIBLE**, cible incluse — et `AddRange` un `GenerateMultiHitAttackPredictions` par entité (base et coups évalués **hors** boucle). Le port n'avait aucun mirror : `AActiveAbility.get_aoe_targets` → `[]`. **Trois pièces**, dont une qui ne se devine pas : la classe d'ability porte le sélecteur ; `_MAKE_DMG_TARGET_GATE[1147]` (l'appartenance de la cible à son propre sélecteur se réduit EXACTEMENT au trait `Summon` + vivante) ; et `make_damage_predictions` **ne court-circuite plus** la boucle AoE quand la cible principale est refusée par un gate — mesuré, cible = le summoner NON-summon entouré de 3 `deathPoxwalker` : le natif rend **3** events, aucun sur elle. S'y ajoute le câblage `has_trait` du `DslContext` (sans lui `UnitsWithTrait` rend VIDE **par dégradation**, volet muet et silencieux). Mesures (natif / port AVANT / port APRÈS) : R0 sans summon `∅ / (6,6,6) / ∅` ; R1 `3 / 1 / 3` ; R2 porteur ennemi au contact `3 / 1 / 3` ; R3 cible non-summon `3 / 1 / 3` ; généralisation `MC1_15` + caster **allié** `3 / 1 / 3` avec dégâts ventilés (486/738 ×2, 324/492 ×1) reproduits. **5 mutations jouées, 5 rouges.** |
| ~~#359-r1~~ | ~~**Le pendant du volet AoE pour `1148 DaemonicOrdnance`**~~ | **FERMÉ (#359-r1)** | `case-350r3-porteur-mow-et-formule-triggered.md`. Écart **MESURÉ** (il ne l'avait jamais été) : cible sur tuile FROIDE, un autre ennemi brûlant dans son triangle → natif **1** event (sur l'AUTRE), port **∅** ; deux ennemis brûlants → natif **2**, port **1**. Le mirror de `DaemonicOrdnanceAbility$$GetAllDamageableTargets` (`Enemies(Caster, Units(Filter(GetTargetAreaTiles(), HasEffect(Tiles(Subject), 5 = Fire))))`) entre en `get_aoe_targets` et referme les deux. Il exigeait **trois canaux** au `DslContext` de `make_damage_predictions`, tous absents : `board` (sans lui les sélecteurs de tuiles rendent `[]`), `tile_has_effect` (branche TUILE de `HasEffect`, même substrat que le gate), et `Scene.machine_of_war_position` — sans ce dernier le prédicat `IsPositionMachineForCurrentPlayer(2)` est FAUX d'office et le triangle part dans la **mauvaise direction**, en silence. Gardes : `test_350r3_mow_carrier_live.py` (7) et (8), la seconde sur un board où `dir` **bascule** (les deux ensemble bornent les deux branches du `If`). 5 mutations jouées, toutes rouges. |
| #359-r2 | **L'ORDRE des events de `1147` : le natif trie, le port non** | `[opus]` | Ouvert et **mesuré** par #359 (`--step 5`) : natif `[113, 110, 116]`, port `[110, 113, 116]` — même ensemble, mêmes valeurs. Le sélecteur finit par `If(AreEqual(CurrentPlayer, Player(1)), SortByRow(Tiles(sel)), SortReverse(SortByRow(Tiles(sel))))`, non porté (la face COMBAT ne le porte pas non plus et le dit). **Sans effet tant que le consommateur SOMME** (`CalculateUtilityFromPredictions`) ; le jour où un chemin lit le PREMIER event, il faut porter le tri **et** l'ancre `IsTopPlayer`. La garde live compare donc des ENSEMBLES, et l'écart d'ordre est imprimé par le probe. |
| ~~#359-r3~~ | ~~**Le terme de PRÉDICTION de `1148` n'est pas branché sur sa route de DÉCISION**~~ | **FERMÉ (#359-r3)** | `case-350r3-porteur-mow-et-formule-triggered.md`. `DaemonicOrdnancePlaybook$$MakeDamagePredictions` **relu** : liste vide puis `AddRange(GenerateMultiHitAttackPredictions(…))` par entité de `GetEntitiesFromSelector(GetAllDamageableTargets, …)` — **aucune « cible principale »**, et c'est structurel : `<Target>` est une entité TUILE, qui ne prend aucun dégât. La forme « main + AoE » de `prediction.make_damage_predictions` mirrore le régime à cible UNITÉ (`aiPlaybookPredict`, #359-r1) ; sur la route de DÉCISION c'est la BOUCLE qui est le mirror → override dans le playbook, comme `PlagueburstMortarPlaybook`. `param_8 = null` **lu** dans `_PLAYBOOK_PROFILE_OVERRIDE[1148]`, jamais recopié. Canal `tile_has_effect` ajouté au `DslContext` de la route tuile (même foyer `_tile_has_effect_from_scene`, inerte pour 1169). Montage `--burning` : 1148 **sort du kit** après son cast (`abilities = [69]` seul) et le feu ne dure que 2 rounds → **deux porteurs** (un ALLUMEUR qui part en cooldown, un DÉCIDEUR mesuré au même tour) ; tuiles embrasées **mesurées** (3 nominales, 2 réelles). Résultat : natif `(1148, 49)`, port `(1148, 49)`, port d'AVANT `(1148, 52)` ; agreement sur marche entière **11/11** contre **10/11**. La garde `test_prediction_term_is_zero_because_the_area_is_not_burning` **ne tombe PAS** — le branchement ne change que le régime BRÛLANT ; seule sa docstring encodait l'ancienne attente. |
| ~~#359-r4~~ | ~~**Une tuile NON MARCHABLE du triangle de `1148` ne prend pas feu**~~ | **REQUALIFIÉ (#368)** — résidu **borné**, cause native non tranchée | `case-368-pose-daemonic-ordnance.md`. **L'énoncé confondait DEUX choses.** (a) L'amputation « 3 nominales → 2 réelles » qui avait coûté une passe de montage est le filtre d'**ÉLÉVATION** (`TilesOnSameElevationSelector$$Select` = `abs(TileComponent+0x18 − ancre) <= maxDiff`), **déjà porté** : le « nominal » comparé était la géométrie calculée à la main par `probe_302_3._burn_stage`. Mesuré natif == port sur les **deux** branches du `If` (bras A `MC1_67`/dir 1/MoW réelle — où la tuile amputée est **MARCHABLE** — et bras B `C1_15`/dir 4). (b) Un écart **réel** subsiste, plus étroit : une tuile de la zone **non marchable** n'est pas embrasée (3 mesures, 2 boards, 2 terrains `Water`/`Block`, dont une où les 3 élévations sont identiques). **Aucun étage de la chaîne de pose ne lit la marchabilité** (xrefs entrantes exhaustives d'`IsWalkable`/`IsWalkableTile`), et `tileMeta` **filtre les effets inactifs** sans exposer le drapeau : « non posé » et « posé-inactif » restent indiscernables → **aucun port spéculatif**. Écart **inerte** sur les deux faces (`CanAddUnit` exige `IsWalkable`) et **gardé borné** (`test_368_daemonic_ordnance_pose_live.py` : `port \ natif` == exactement les non marchables de la zone). |
| #368-r1 | **La cause native du refus d'embrasement sur tuile NON MARCHABLE** — capteur manquant | `[opus]`+prérequis | `case-368-pose-daemonic-ordnance.md` §3. Deux hypothèses restent ouvertes et **une seule mesure les sépare** : l'effet est-il *jamais soumis* (alors `StateExtensions$$GetTileAt` n'inscrirait pas ces tuiles dans `BoardComponent+0x18`, et c'est le substrat `board.id_at` du port qu'il faudrait corriger, pas 1148) ou *posé puis désactivé* (`RefreshEffectsOperation$$ShouldBeActive` → `ActiveCondition` de `BaseEffect`, slot `+0x518`, non lu) ? **Prérequis** : `tileMeta` accepte désormais `includeInactive` et publie `active` — **livré par #368, INERTE tant que le bundle n'est pas réinjecté**. Question **générale** (tout effet de tuile), pas propre à 1148. |
| #350-r3c | **`aiPlaybookPredict` ne sait pas prendre une MoW pour caster** — capteur à corriger, NON DÉPLOYÉ | `[opus]`+prérequis | `case-350r3-porteur-mow-et-formule-triggered.md` §(b). Mesuré : `count = -1`/`listNull` dès qu'un summon est en jeu (`rpc-predict.ts` substitue la `UnitPosition` de la cible pour un caster off-board), et `engine.ai.context.build` rend `ctx.me is None` pour une entité `Machine`. Tant que ces deux-là tiennent, toute ability de MoW se confronte par GREFFE, avec l'étage aval du greffon. Le volet `rpc-predict.ts` exige une fenêtre de reinject. |
| ~~#356-r1~~ | ~~**`1132 KillMaimBurn` : l'oracle NC répond, le PORT manque**~~ | **FERMÉ (#362)** | `case-350r3-oracle-noncomparable.md` §7.3 + §8. Le port existe (`engine/playbook/noncomparable/kill_maim_burn.py`) — **et la divergence inscrite ici n'en était pas une**. `(8536, 8536, 4)` n'était pas la prédiction de `1132` « bornée aux PV MAX » : c'était l'**attaque NORMALE** de `worldKharn`, construite par `IdunBattle.AI.Playbook.BasePlaybook$$WillNormalAttackKill` — première instruction du corps de boucle de `KillMaimBurnPlaybook$$EvaluateNonComparable`, qui prédit la normale, en fait un `ProbableDamageEvent` (donc **capté par l'oracle, ancré sur ce ctor**, avec le MÊME `targetId`) et n'en garde que `get_WillBeKill`. Les `4` coups sont `worldKharn.weapons[0].hits`, pas `nrOfHits` (= 1) ; les bornes sont **égales** parce que la normale sur-tue (cap per-coup à la santé restante). Aux PV du seed le gate mordait sur TOUTES les cibles ⇒ bucket VIDE, **aucune** prédiction d'ability construite. Le kit a bien trois profils, mais le playbook n'en lit **qu'un** (`GetDamageProfile`/`GetHitsFormula` = clés NON suffixées, `MinMaxDamage` = vars `0xc`/`0xd`) : les suffixes `_2`/`_3` appartiennent à la face COMBAT. Le chemin générique était donc **déjà exact**. Confronté : `probe_344 --oracle auto` sur 1132 (`--victim-hp`, bras 3/12) élit **`to_even`** seule sur les deux bras, code LIVRÉ == natif ; `probe_362_kill_maim_burn_nc.py` prouve les trois faits (l'event du gate == la normale du port ; gate ON ⇒ 1 event + bucket vide ; gate OFF ⇒ `[normale, ability]` bit-exact) **et** que le gate CHANGE la cible émise (survivant `u=14.0790614` natif == port, contre `44.28` pour le mourant que le port sans gate choisirait). **A/B d'agreement** (`engine_validate --steps 14`, seed 777/`MC1_67`, seul curseur = la présence de 1132 au registre) : au pas 7 le natif joue `ability(1132, tgt=79)` en `(3,3)` — le port l'égale, alors que sans le playbook le fallback Comparable trouvait l'ability mais **pas la cible** (`tgt=122`, position à 1 hex) ; marche entière **pos exact 11/13 et ability 9/10** contre 10/13 et 8/10. Durcissements : la face NC de `probe_344` compare la **SÉQUENCE** construite (`playbook.damage_predictions`, tag `WillNormalAttackKill`/`ability`) et rend **NON CONFRONTÉ (rc 2)** quand un gate prédictif a mordu. Résidus **non touchés** : `1173 ArcScourge` (porteur `admecBossBelisarius`, **npc** → greffe ou injection catalogue) et `1111 LivingBatteringRam` (**sans porteur** par les 5 voies de `unit_map.py`) — tous deux NC natifs ET dans un registre d'arrondi, donc ils reprennent le rôle de sujet du garde-fou « refuser une NC sans playbook porté ». |
| ~~#350-r3a-r3~~ | ~~**Par position, le natif score UNE cible là où le port en score DEUX (1202)**~~ | **FERMÉ** | `case-350r3-oracle-noncomparable.md` §9. **L'énoncé était faux sur son axe** : les DEUX côtés sont per-position et portent le MÊME prédicat — `BasePlaybook$$GetEligibleTargetsSelectable` → `AttackQuery$$GetValidTargets` par position ; `computeAttackPlans` → `AttackQuery$$GetBestTileToAttackFrom` → `AttackQuery$$GetInvalidTargetReason`. **Écart de prédicat mesuré = 0 position sur 33, à tous les rangs.** Le vrai écart est la **TRONCATURE** : `computeAttackPlans` plafonne à `maxRank` (`for (let r = 0; r < maxRank; r++)`), plafond absent du natif. Sur UN seul état (fixture `carte`, `probe_350r3a_r3_position_gate.py`) : `maxRank=32` → 0/33 position perdue, argmax identique ; `maxRank=8` (défaut `rl_duel._decision`) → **19/33**, argmax identique par coïncidence ; `maxRank=6` (défaut du RPC `decisionView`) → **21/33**, et **ARGMAX DIFFÉRENT — natif `(1,3)`, port `(0,3)`**. Le régime fautif est celui de production. Fix : `_PlanTargetPlaybook.eligible_positions` (7 sous-classes) lit `castFromTiles` — même prédicat sans troncature — avec repli NOMMÉ sur `ranked`. Garde `test_350r3a_r3_position_gate_live.py` : **9 passed** (2 failed / 4 passed avant ; 4 failed sous mutation). ⚠ RÉSIDU OUVERT : le fix ne détronque PAS `attackPlans` — tout autre consommateur de `ranked` reste exposé au plafond (défaut du **harnais**, correction ⇒ réinjection). Voir `#350-r3a-r4`. |
| #350-r3a-r4 | **`ranked` est TRONQUÉ à `maxRank` — 6 autres sites le lisent encore** | `[opus]` | Ouvert par `#350-r3a-r3` (`case-350r3-oracle-noncomparable.md` §9), qui a MESURÉ le mécanisme : `computeAttackPlans` plafonne (`for (let r = 0; r < maxRank; r++)`), plafond absent du natif ; à `maxRank=6` (défaut du RPC `decisionView`) **21 positions sur 33** disparaissent du plan, assez pour DÉPLACER un argmax. `_PlanTargetPlaybook` est corrigé ; **6 sites lisent encore `ranked`**, en trois régimes distincts — (a) **gate de position** : `ai/action_generators.py` tier COMPARABLE (`legal = {targetId: set(ranked)}`, couvre TOUTES les attaques, attaque normale incluse) et `playbook/noncomparable/_base.py::_num_attack_targets_in_position` (TheQuickening) ; (b) **source de dégât** : `noncomparable/hammer_of_wrath.py` et `noncomparable/holy_duel.py` (`dmgMin`/`kill` du top-`maxRank` seulement — une tuile écartée peut porter un dégât supérieur) ; (c) `playbook/loki_custom.py` (gate) et `runner/operations/summon_ai.py` (re-filtrage, face COMBAT). Le régime (a) est le plus large et le plus exposé. **Deux voies** : gater sur `castFromTiles` comme `_PlanTargetPlaybook.eligible_positions` (coût = 1 RPC/cible, sans réinjection), ou détronquer `computeAttackPlans` côté harnais (⇒ **réinjection**, donc fenêtre à planifier). Reproduction : `probe_350r3a_r3_position_gate.py --fixture carte` (le balayage de rangs se fait sur UN seul état). |
| ~~#344-r2~~ | ~~**`SortAttackersByDamagePredictionSelector` : le port bâtit UNE prédiction là où le natif en bâtit TROIS**~~ | **FERMÉ (#344-r2)** | `case-344` §7. Les trois prédictions sont portées (slots 2/4/3 re-dérivés du binaire) et appariées comme le natif — `WillBeKill` sur la borne MAX, `MightBeKill` sur la MIN. Réponse au critère : **aucun montage ne sépare les trois par la valeur** — le nœud de dégât de l'unique appelant est une `ASimpleAmountFormula`, dont `CalculateMin`/`Max` retombent sur `Calculate` (démontré, xrefs lues). Le bug réel était le CHAMP moyenné : `pred+0x60` = `TotalDamage`, pas `raw_health_damage` ; le port ne passait pas non plus le bouclier de la cible, et les deux écarts se compensaient sur la branche moyenne. Ils divergent sur la branche KILL (bouclier + cible fragile : l'ancien port élisait le plus FAIBLE). Non confronté live (host éteint). |
| #264-pv | **La Scene LIVE (`build_predictor`) reconstruit encore les traits** — asymétrie avec la Scene issue de `load_state` | `[opus]` | Résidu nommé de #264. `playbook/scene.py` : `ctx_by_id[eid] = UnitContext.from_snapshot(u, GC.unit(vis_id or ""), stat_types)` — la ligne `u` EST la ligne `combatSnapshot`, elle porte donc déjà `u["traits"]`, mais rien ne la consomme. Conséquence : pour le MÊME état, `Scene.from_state` (offline) rend l'ensemble MESURÉ et `Scene.from_predictor_sctx` (live) l'ensemble RECONSTRUIT — donc les deux faces de `_target_damage_limits` peuvent diverger sur `necroOverlord`. Le remède est une ligne (réutiliser la même conversion `trait_names_from_ids` + `traits_measured`), **mais** il déplace la face PRÉDICTION LIVE : à livrer avec son propre re-jeu d'agreement (`engine_validate`), pas « en passant ». |
| #264-r | **2 fichiers de test live rouges AVANT #264 (montage, non causés par lui)** | `[opus]` | Contrôle joué par `git stash` le 2026-07-30 (identiques avec et sans le correctif #264), sur `origin/master` @ `0231573`. ~~(1) `test_trait_gates_dynamic_live.py::test_in_battle_granted_trait_flips_the_capture_point_gate`~~ **FERMÉ par #272** (`case-272-capture-point-ordinal-perime.md`) : ni la feuille ni le poids n'étaient en cause — le test indexait `TILE_LEAVES` par l'ordinal **figé** `24`, exact à son écriture et périmé par `fe5b9245` (#252 : `AttackTile` inséré en 8, `CapturePoint` 24 → 25). L'index rendait `MoltenForm_TilesUtility`, muette sur ce `meta` ⇒ **0.0**. Avec le MEMBRE : **300 → −300**, la bascule de #225 retrouvée. L'hypothèse publiée ici (« c'est la feuille ou le poids qu'il faut re-dériver, pas le montage ») est **RÉFUTÉE**. (2) `test_overkill_gate_live.py` — 3 rouges + 5 skips « plage [1,100] trop large : dmax >= 2 x dmin, pas de PV rendant TOUTE la plage létale-sous-le-seuil ». (3) `test_prevent_overkill_decision_live.py::test_prevent_overkill_takes_two_distinct_values` — le canal ne rend que son défaut (`preventOverkill=0` des deux côtés) + 3 skips « régime létal-sous-le-seuil inatteignable : bornes [0,0] ». Les trois sentent la **migration de build** (bornes de dégât dégénérées) — même famille que `#254-tau`. |
| ~~#254b-b~~ | ~~`probe_202c_tutelaries.py` : 5 littéraux de `StepType` décalés de −1~~ | **LIVRÉ (2026-07-30)** | `case-254b-b-ordinaux-en-dur.md`. **Le verdict publié est CONFIRMÉ** : `probe_202c --seed 20203` rendait **FAIL** (`A1:effet, A2:no-spawn, A4:count, B:chain-count`) avec ses littéraux d'origine sur `rnca9r7q6c`, et rend **PASS** après correction — soit exactement le verdict de `case-202` §8, aux mêmes chiffres (Horror 3589, Screamer 4487, B 2 spawns == 2 attaques Psychic, C +0). Aucun des deux résultats publiés antérieurement n'était erroné ; le `FAIL` intermédiaire était l'artefact des ordinaux, pas une régression du port (aucun `engine/**` touché). **La dégradation était par SOUS-comptage** (les co-prédicats de tag ne matchent pas le pas voisin ⇒ 0 au lieu de N), à l'inverse du sur-comptage mesuré en `#254b-a` — on ne peut pas prédire le sens sans lire le site. **Balayage du dépôt** : 25 littéraux dans 12 fichiers + 4 tables de noms indexées par ordinal, toutes corrigées (`step_id`/`group_id` neuf). Décalés donc FAUX : `probe_217_thequickening` (ajout et retrait d'effet **intervertis**), `probe_217_blackrage`, `rl_collect_batch` + `rl_ingest_postgres` (colonne `stream_event.step_name` de la base RL décalée de +1 pour tout pas ≥ 7), `frida/public/src/battle-log.js` (labels décalés ET pions posés/retirés sur les mauvais events). **SECOND défaut, antérieur aux deux builds** : `enum_maps.GROUP_TYPE` est périmée (102/104, `Ability_Displace` et `EndTurn` manquants) — elle donnait `59 = NormalAttack_AtomicDamage` là où le jeu dit `ZingerAbility` (le vrai est **61**), si bien que le fallback « 015 » de l'ingest RL ne s'est **jamais** armé sur une attaque normale. Cliquet : `probe_274_step_ordinals_sweep.py` (PASS) + `tests/test_step_ordinal_ratchet_offline.py`. **Résidus** : `enum_maps.py` non régénéré (exige `dump.cs`, gitignoré) et ses 5 autres enums non vérifiés ; les batches DÉJÀ ingérés ne sont pas rétro-corrigés en base ; le changement `_ATTACK`/`_ACTOR` n'est pas confronté live. |
| ~~#264~~ | ~~`load_state` ne consomme pas `combatSnapshot.units[].traits`~~ | **LIVRÉ (2026-07-30)** | Le hook `0231573` (#233) publiait l'ensemble EFFECTIF des traits (invoke d'`IdunBattle.Entities.UnitExtensions$$HasTrait` par valeur d'enum ⇒ résultante de `BaseUnitComponent$$HasTrait`, veto `+0x50` compris) **sans consommateur** : le port RECONSTRUISAIT `UnitContext.traits` depuis `gameconfig.unit(vis).traits` + dérivation d'alliance. `snapshot._load_unit_traits` le seede désormais (tri-état : champ absent/`null` = **non mesuré** ⇒ reconstruction inchangée ; une LISTE, `[]` comprise = mesure), et `ctx.traits_measured` coupe la re-dérivation d'alliance par-dessus la mesure. **Le natif ne lit pas le gameconfig** : les traits de départ viennent de `BC.Units[].Traits`, et les deux blocs diffèrent **dans les deux sens** — mesure offline sur les 175 unités du seed BC : **5** en ont MOINS que leur kit (`necroOverlord` sans `Resilient`, `blackSmnBloodletter` sans `BlessingsOfKhorne`/`Summon`, …), **48** en ont PLUS (`custoAtlacoya` +`SistersSilence`, `astraDreir` +`DeathKorpsKrieg`, les npc +`Summon`/`NPC`). *Une* cause est déjà documentée et n'a rien d'une règle générale (cf. `#254-bc` : le bloc `Units` du seed BC date de `gqfc5mff6c`) — le remède ne dépend pas de la cause. **Trois forks de lecture supprimés au passage** : `targeting._unit_traits` (relisait le gameconfig alors que son docstring annonçait `UnitContext.traits` ⇒ aveugle à l'alliance ET aux `AddTrait`), `behaviours/context._unit_dict` (ré-unionnait l'alliance à la main), et les DEUX faces du cap de trait (`operations/damage.py::_target_limits` + `prediction/_shared.py::_target_damage_limits`) — ces deux dernières rendaient `necroOverlord` **impossible à tuer offline** (`ApplyResilientTraitDamageLimit` capait à `HP-1`) alors que le natif ne lui donne pas le trait. Mesures : `probe_264_load_state_traits.py` **7/7** (couverture d'enum 105/105 ; 3 montages ; non-vacuité 2 unités ratées par la reconstruction sur B **et** sur C) ; verrou `test_load_state_traits_live.py` **6 tests**. **Résidu nommé** : `Scene.build_predictor` (`playbook/scene.py`, `ctx_by_id[eid] = UnitContext.from_snapshot(u, …)`) ne consomme PAS `u["traits"]` — la Scene LIVE reconstruit donc encore, là où la Scene issue de `load_state` lit. Une ligne, mais elle change la face PRÉDICTION live ⇒ sa propre validation d'agreement. |
| ~~#230~~ | ~~`load_state` ne consomme pas `currentTurnStartTile` / `chargedUnitIds`~~ | **LIVRÉ (2026-07-29)** | `case-r32-ischarging-consumers.md` §7 + `case-66-revive-in-place` §8. Le hook `f790ff4` (#223) exposait les deux champs du `UnitComponent` (`+0x18c`, `+0x190`) sans consommateur ; `snapshot._load_unit_turn_state` les seede désormais au chargement (tri-état : champ absent/`null` = **non mesuré** ⇒ défaut du port inchangé). **Contrainte de mesure** : `chargedUnitIds` n'est non vide que **MI-ACTIVATION** (`FinishUnitTurnOperation$$Execute` la vide) — une capture entre deux tours la voit vide, et c'est **correct**. Chiffres (`probe_230_load_state_turn_state.py`, `MC1_67`/777, `astraBullgryn` vs `necroOverlord`) : régime `CHARGE` capture mi-activation `chargedUnitIds=[77]` → offline seedé `[3935, 3757, 3078, 3132]` = **live**, contre `[3336, 3158, 2479, 2533]` sans le seed (**−599/coup**) ; régime `STEP_ADJACENT` `chargedUnitIds=[]` → bit-exact **avec et sans** (le câblage n'accorde rien de plus). Face PRÉDICTION fermée par la ligne `B' SEED` de `probe_r32_ischarging_prediction.py` (natif **12032** = offline sur état RECHARGÉ, aucun pas rejoué ; bornes forcées 12032/9636). Time-ghost `thousTerminator` : le PREMIER move après `load_state` le pose sur la bonne tuile **sans** rejouer de `StartTurnOperation`. Verrou : `test_load_state_turn_state_live.py` (4 tests). |
| ~~#232~~ | ~~Le gate `IsAffectedByHealType` est ABSENT côté DÉCISION (6 gates de `heals.py`)~~ | **LIVRÉ (2026-07-29)** | `case-232-heal-type-gate.md`. Ferme le résidu `case-225` §5.2. Les 6 gates délèguent au mirror déjà porté `revive_effect.py::is_affected_by_heal_type` sur le substrat d'ENTITÉ (`entity_trait_names`, #225) : **deux** écarts fermés d'un coup — le disjunct `HasTrait(0x421 AffectedByHealAndRepair)`, **et** deux des trois traits d'`IsMechanical` (`LivingMetal` 1000, `Vehicle` 0x405) que le module ignorait. Littéraux de `healType` **relus site par site** : `0` pour `RitesOfRestorationAbility$$GetPossibleResurrectTargets` / `$$GetHealTargets` / `RevitalizingMalignancyAbility$$GetAllHealTargets`, **`1`** pour `DefendTheDivineWorkAbility$$GetDynamicInvalidTargetReason` ; `CombatRestorativesAbility$$HealTargets` n'a **AUCUN** wrapper `Healable` (fait du décompilé, pas un oubli). **Gisement STATIQUE mesuré VIDE** (`probe_232_heal_type_gate.py` : 126 `Mechanical` / 51 `LivingMetal` / 8 `Vehicle` / **0** `0x421` sur 669, et **aucune** unité `LivingMetal`\|`Vehicle` sans `Mechanical`) ⇒ neutre au bit près sans octroi. **La voie NATIVE d'octroi n'est PAS instanciable** : les 9 porteurs de la relique `R_Defensive_SupaCyborkBody` sont tous `kind=npc`, et aucun canal de `rl_duel build` n'équipe d'item (`itemSpecs` ne vit que dans `normalize-bc`, `excludeRelics: true` par défaut, zéro consommateur Python) — la validation confronte donc la **cohérence décision/combat sur le même état**, par le leaf porté `AddTrait` (montage #225). `test_heal_type_gate_decision_live.py` : **28 verts** (table de vérité 24 cas + verrou anti-tautologie + neutralité 8/8 unités sur bataille réelle + discrimination `util 2.0 -> 3.0` avec `admecManipulus` mécanique entrant dans `GetHealTargets` après octroi de 0x421). **Résidus** : les 5 autres disjuncts d'`AttackQuery$$EntityCanBeHealed` (dont `IsDamagedUnit`, non portable seul — `HasNegativeUnitEffect` le relâche) ; `DefendTheDivineWork` non discriminable live (son unique porteur `admecManipulus` est lui-même `Mechanical` ⇒ `self_repairable` toujours vrai). |
| ~~#231~~ | ~~Le `matches` de l'effet-trigger 1197 ne teste pas que l'effet source est ACTIF~~ | **LIVRÉ (2026-07-29)** | `case-231-master-tutelaries-active-gate.md`. Résidu de #229. **Le brief était à corriger sur un point** : 1197 (`EffectType.MasterOfTheTutelaries` — ni `ActiveAbilityType.ExcruciatingFrequencies` ni `TriggeredAbilityType.FeederTendrils`, homonymes) n'est PAS du rail TARGETS mais du rail **APPLY_REVERT**, et les deux ne se gatent pas pareil. Le conjoint `HasEffect` de `MasterOfTheTutelaries_SummonAbility$$CreateTrigger` passe `onlyActive=**0**` (sémantique du 4e argument lue dans `EntityExtensions$$IsOwnerOfEffect`, qui ne `continue` sur `IsActive@0x5c == 0` que si ce bool est vrai) : l'arbre ne teste QUE la présence. L'activité mord par un autre chemin — `RefreshEffectsOperation$$DeactivateEffect` écrit `+0x5c = 0` PUIS enchaîne `UpdateEffectTargets` avec une liste de cibles **VIDE** → `RemoveTargetsFromEffect` → `Revert` → `MasterOfTheTutelariesEffect$$RevertInternal` → `RemoveTriggeredAbility(0x495)`. Le gate est donc posé dans `matches` (présence + au moins une instance ACTIVE), **jamais dans la collecte** (le rail ArraySet doit pouvoir RÉ-ACTIVER). **Portée honnête** : le gate est **inerte aujourd'hui** — mesure live (Abraxas caste 1096, 3→8 unités, 1 Horror + **4 Screamers**, chaîne 1173 bien armée) mais **1197 n'est publié par AUCUN canal de capture** ⇒ aucun seed ne peut le faire naître inerte, et la pose offline le crée actif. Cliquet de fidélité, pas changement de nombre. Contre-épreuve : **1 failed / 4 passed** avant le fix sur `test_deactivating_the_marker_disarms_the_summon`, **5 passed** après ; `probe_229` 6→5 gaps. |
| #231-r | **1197 fire mais n'est publié par aucun canal de capture** — la PERSISTANCE du marqueur n'est confrontée par rien | `[opus]`+prérequis | `case-231` §7. Mesuré : après le cast de 1096 la triggered 1173 a bien fire (4 Screamers), pourtant l'effet 1197 est absent de `decisionView` par défaut **et** de `includeInactive`. `readEffectsByUnit` n'itère que `EffectsOwnedComponent.ActiveEffectIds @0x10` et ne droppe que `removed`/`!active` ⇒ l'entité-effet n'y est déjà plus. Deux lectures non tranchées : retrait très précoce (durée = dernier argument d'`AddEffect`, `ctx@0xc0`, non décodée), ou effet vivant hors de cette liste. Tant que ce n'est pas tranché, le port qui garde le trigger 1173 collecté tour après tour n'est confronté par rien. **Prérequis** : point d'ancrage natif à hooker (`RefreshEffectsOperation$$RefreshEffect` ou l'`AddEffect` de 1096) ⇒ demande une réinjection. |
| #229-r | **Les 4 effet-triggers du rail TARGETS dont le `matches` ne lit toujours pas `IsActive`** | `[opus]` | `case-231` §7 + `probe_229_effect_triggers_active.py` (cliquet, `EXPECTED_GAPS`, **4** entrées après les deux résorptions du 2026-07-29 : 1077 par la PR rail-TARGETS, 1197 par #231). Restent : **1186** `GhostEffectRevive`, **1201** `AnvilShieldFrozenAdvantageExpire`, **1502** `RitesOfMorkaiReviveTrigger`, **1547** `ReanimationBeamReviveTrigger`. ⚠ Ne PAS transposer la solution de #231 : ceux-ci sont du rail `CreateTargetTrigger`, où le gate natif est la **double lecture** d'`IsActive` par `EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` (à l'entrée, puis **RELUE PAR CIBLE** dans la boucle de drain — une désactivation en cours de drain stoppe les cibles suivantes), et non un couplage Apply/Revert. **Un item par tâche.** |
| #o10-c | **Cardinalité des groupes #179 de `blackObliterator`** — le live émet des coups que l'offline ne produit pas | `[fable]` | `case-o10-volk-moved-flag.md` §6.1. Montage seed 777 / `MC1_67` / `--p-units blackObliterator,adeptHospitaller --a-units necroWarden,necroWarden`, capteur `hitTraceArm` : attaque 2 (round `RuinousSalvo`) → live **9** coups (7 profil 19 + 2 profil 3) / offline **8** (6 + 2 Flame) = groupe `LetTheGalaxyBurn` manquant ; attaque 3 (round `WarpHail`) → live **9** (9 profil 19) / offline **6**, `additional_hits=None` = les DEUX groupes manquants. `mt_same=False` (1 puis 5 tirages d'écart) — donc bien une CARDINALITÉ, pas une magnitude. **Non reproduit** sur `C2_02`/`31337`, où les groupes Melta et Flame sortent normalement (`mt_same=True`, bit-exact) : le déclencheur n'est pas établi → `[fable]`. Ne pas confondre avec l'écart de magnitude du même montage, RÉSOLU (flag `Moved`). |
| ~~#o10-a~~ | ~~`test_avalanche_of_muscle_live.py` — 3 échecs PRÉ-EXISTANTS (gate `IsCharging` non discriminant)~~ | **LIVRÉ (2026-07-28)** | `case-r32-ischarging-consumers.md` §5. **C'était l'ATTENDU, pas le code.** Bisect : `64d875d` **3 PASSED** / `964dd15` (case-r32) **3 FAILED** — le commit qui a remplacé le proxy `has_moved` par `IdunBattle.Core.Services.BattleQuery$$IsCharging` n'a ni mis à jour ni retiré le test qui gatait par le proxy. Le fichier est **supprimé**, pas rafistolé : sa méthode (snapshot **APRÈS** le pas + charge **déclarée** par `set_moved_flag`) ne peut pas reproduire le 2e terme du prédicat — `UnitComponent.ChargedUnitIds@+0x190` n'était alors exposé par **aucun RPC**, donc `load_state` ne le seedait pas (*canal ouvert depuis `f790ff4`, consommé depuis #230 ; ce qui reste faux, c'est de **déclarer** la charge par un proxy au lieu de la **lire***) — et il n'exerçait que `CHARGE` et `NO_STEP`, les deux régimes où proxy et prédicat **coïncident** ; le régime discriminant (`STEP_ADJACENT`) n'y était pas exprimable. Verrou vivant de l'effet 1025 : `test_ischarging_extra_damage_live.py` (7 tests verts, 3 régimes, 2 couples board/seed), **renforcé** de `test_charge_bonus_is_not_vacuous` qui reprend les deux garanties propres du fichier retiré (non-vacuité de la magnitude `ConfigVar(8)`, matérialisation sur les PV). Piège de mesure levé au passage (`probe_o10a_charge_hp_stage.py`) : `applyAction.units[].hp` = état de **FIN DE CASCADE** (ici bascule de tour + `LivingMetalRepair` **+12000** + ripostes), à ne jamais confronter à un rejeu offline qui n'a joué que l'attaque — l'étage propre est le `UnitStats_RemainingHealth` du dernier événement de dégât. |
| #116-r | **AdaptiveStrategy (1005, `necroWarden`)** — reste du lot 1 Necrons | `[opus]`+prérequis | `case-116-necrons-lot1` §4 : RE COMPLÈTE (arbre + légalité + mapping du ctor `AddStatOverrideEffectBehaviour`). Prérequis restants : (1) **`RelentlessMarch` 1004** (passif `necroWarden`, `…RelentlessMarchAbility$$CreateBehaviour`) — sans lui la branche `If(ActorHasTriggeredAbility) TriggerAbility(…)` est un no-op structurel ; (3) nœuds `TriggerAbility` + `ActorHasTriggeredAbility`. ~~(2) sous-système OVERRIDE-ATTAQUE~~ **LEVÉ** : `AddStatOverrideEffect` existe (`abilities/behaviours/stats.py`), 2 users runner (#112 ExemplarOfHate `71dca97`, #114 InspiredToGreatness `d67b6ac`). `PerformAIAction` est déjà là. |
| #116-e | **Magnitude de `Chronometron_ExtraDamage` (1550)** — l'effet est posé mais INERTE | `[opus]` | `case-116-necrons-lot1` §2 : `…Chronometron_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` = `ForAddition(OwnerIsTarget & IsUnit(att) & AreFriends(att, EffectSource), If(IsMechanical(att), ConfigVar(9), ConfigVar(8)) × TimesEffectApplied)`. Manque, dans `attacker_ctx` du hook DÉFENSEUR (prédiction ET runner) : équipe de l'attaquant vs équipe de la SOURCE de l'effet, trait `Mechanical` de l'attaquant, compteur `TimesEffectApplied` par instance. Consommateur additionnel : `$$CreateRemoveEffectTrigger` = `On(9)` (effet CONSOMMÉ au 1er coup allié). |
| ~~#116-d~~ | ~~Séquencage RNG de `ChainLeftOverHitsAttackDamage` après un KILL~~ | **LIVRÉ (#125)** | `case-125-rng-wasted-hits` : ce n'était PAS un écart de flux `state.rng` (natif ET port roulent TOUS leurs coups — `AttackDamageOperation$$ExecuteHits` = `while (i < hits)` sans sortie sur la mort), c'était le **report** `GetLeftOverHits`, figé à `1 + extraHit` par #116 alors qu'il vaut `max(0, H - k - 1) + extraHit`. Corrigé + gardé (`test_chain_leftover_hits_live.py`, 2 seeds, contre-cas intégré). |
| #202 | Kit d'Abraxas (`thousInfernalMaster`) : WeaverOfFate + InfernalPacts + MasterOfTheTutelaries | `[opus]` | `case-202` : **tranches A, B et C LIVRÉES** (C : execute 1096 + effet 1197 + triggered 1173 Screamer-par-attaque-Psychic-du-SET-bonus-inclus + chaîne InfernalPacts + playbook NC slots 0x49/0x52/0x6b/0x72 — probe 202c PASS A1-A4/B/C, garde 31337 100 %). Résidu principal : face DÉCISION portée mais non confrontée oracle (`case-202` §8) — au premier walk Thousand Sons. |
| ~~#201~~ | ~~`VigilanceEternal` (1202) consomme un composite d'utilité que le port COLLAPSE~~ | **LIVRÉ (2026-07-28)** | `case-201-movement-suggestion-tiledistance.md`. Le littéral EST `MovementSuggestion(32)` et `UtilitiesDatabase$$InitializeUtilities` le compose bien en `[Tile(7), TileDistance(33)]` (tableau `[0]=7, [1]=0x21` relu au décompilé). `TileDistanceUtility` portée 1:1 (**aucun poids BC** — le facteur `−1/10` est en dur ; distance HEX ; signe négatif), composite enregistré dans `UTILITY_BY_TYPE`, `_vigilance_move_dest_tile` branché sur le foyer et son collapse « plus proche » + tie-break inventé par id SUPPRIMÉS. Le collapse n'était juste que dans le régime `Tile(7)` PLAT : **344 couples divergents / 847** sur `MC1_67`, **236 / 568** sur `C4_09`. 5 géométries jouées live, 2 boards, **les DEUX moitiés confrontées séparément** (3 réfutent le collapse, 2 réfutent `Tile(7)` seul) — natif 5/5 avec le composite. **Résidu nommé** : 5 autres call-sites passent `0x20` et gardent leur collapse (`TheBetrayer_TakeTurn` ×2, `BlackRage` 1163, `Waaagh` ×2 — littéraux relus un par un). ⚠ Ce résidu est **partiellement fermé par #206** : ne restent que les deux `TheBetrayer_TakeTurn`. |
| ~~#206~~ | ~~`BlackRage` (1163) et `Waaagh` (1058) : les deux call-sites `0x20` restés collapsés après #201~~ | **LIVRÉ (2026-07-28)** | `case-206-black-rage-waaagh-movement-suggestion.md`. Les deux ont **exactement** la forme de 1202 (`First(SortTilesByUtility(GetPossibleMovementTiles, caster@0x160, 0x20), 1)`, surcharge `int` -> `ownerSel` NUL). **Deux collapses différents** : Waaagh n'avait que le TRI collapsé, **BlackRage avait AUSSI son POOL** (`board.neighbours(cible)` = ring-1 NU, sans `MovableTilesInRange` ni `CanAddUnit` — la justification « reachability garantie par la DÉCISION » était fausse : le gate ne garantit que `Count(pool) > 0`). Portés : `black_rage_possible_movement_tiles_selector` + `_black_rage_move_range` (mirrors 1:1), `_black_rage_charge_tile` / `waaagh_charge_tile` branchés sur le foyer, et **`black_rage_tree` éclatée en 3 arbres** exécutés successivement — mirror des 3 `Execute`/`ExecuteAtomic` natifs, indispensable pour que `UnitMovementRangeWithBonus` voie l'effet 1342 déjà posé (sélecteurs natifs PARESSEUX). Gisement mesuré sur `MC1_67` : **314/712 couples divergents dont `Tile(7)` tranche** (Waaagh), **290 + 32 hors-pool / 702** (BlackRage). **19 géométries jouées live, 19 fois la tuile du composite, 0 contre-exemple** — dont une contre-épreuve où `TileDistance` SEUL départage deux tuiles à `Tile(7)=50`, et un cas où l'ancien collapse envoyait Lucien charger dans la Swamp (`TileEffects` −25). Piège de mesure documenté : **Waaagh SPAWNE avant de bouger**, le pool trié est le pool POST-SPAWN (un faux contre-exemple était né de la prédiction pré-cast). **Résidus** : les 2 `TheBetrayer_TakeTurn` (enveloppés d'un `SortByFormula(MinPathLength)`, cas différent) ; ~~`BlackRage` sans `TARGETING_OPTIONS`~~ **fermé par #210**. |
| ~~#210~~ | ~~`BlackRage` (1163) : masque de ciblage absent -> règle de ciblage dynamique INERTE~~ | **LIVRÉ (2026-07-28)** | `case-217-blackrage.md` §5. Masque RELU sur BlackRage (jamais hérité de Waaagh) : `BlackRageAbility$$.ctor` appelle l'overload **FLAGS DIRECTS** `TargetingOptions..ctor(&opts, 0, &<TargetingRange statics+0x48>, 1, 0x106004012, 0, 0, 0)` -> le littéral EST le masque effectif, aucun des deux pièges (ni preset+flags, ni recopie de champ statique) ; le ctor se trouve *a posteriori* byte-identique à celui de Waaagh. Quatre règles armées : `TargetMatchesDynamicRule` `CasterHasNotMoved` `TargetIsEnemy` `TargetIsNotAdjacent` ; `range = useWholeBoard` -> le volet PORTÉE générique ne teste RIEN, toute la distance vit dans la règle dynamique (`Count(GetPossibleMovementTiles.Evaluate(ents)) > 0 ? 0 : 0x8000000 TargetIsInRange`), qui consomme le sélecteur de pool livré par #206. **Mesure** (`probe_210_blackrage_targeting.py`, oracle `abilityReason`) : **6/6 d'accord natif/port, et 5 cas où le natif REFUSE alors que `master` rendait 0** (ennemi hors charge, cible amie, cible = le caster, cible au contact, caster ayant bougé) — cinq casts illégaux que le moteur acceptait. **Généralisation** (`--sweep`) : **48 points sur 2 boards/2 seeds, 0 désaccord**, avec le régime qui réfute tout collapse « distance <= N » — à **distance égale** (d=2) le natif accepte l'un et refuse l'autre, et le verdict n'est **pas monotone** (d=3 refusé / d=6 accepté). Cliquet : 1163 retiré de `SANS_TARGETING_OPTIONS`. |
| ~~#222-1~~ | ~~`ArmoriumCherub` (1014) : masque de ciblage absent -> aucun gate sur les casts de Vindicta~~ | **LIVRÉ (2026-07-29)** | `case-1014-armorium-cherub-targeting.md`. Forme de ctor = **PRESET STATIQUE COPIÉ** (la 3ᵉ, ni flags-directs ni preset+flags) : `ArmoriumCherubAbility$$.ctor` n'appelle **aucun** `TargetingOptions..ctor`, il recopie les 0x40 octets de `TargetingOptions statics+0x140` puis `AActiveAbility..ctor(this, &opts, 0, 0)` — le masque effectif est donc `*(statics+0x168)` = **`0x4002`**, lu dans `TargetingOptions$$.cctor` (`TargetMatchesDynamicRule` | `TargetIsEnemy` ; aucun corps propre de `GetDynamicInvalidTargetReason` -> défaut 0). Le **même preset** porte la PORTÉE : `TargetingRange statics+0x18` = `useRangeFromConfig` (`constants.range` = 2) **et** `forceMeleeTarget` (`<preset>+0x20`) = 0 = **`RangedBool.True`** -> clamp à 1 + `onlyAdjacent` dès qu'un ennemi est au contact. **Mesure** (`probe_222_armorium_cherub_targeting.py`, oracle `abilityReason`) : **6/6 d'accord natif/port, 4 cas où le natif REFUSE alors que `master` rendait 0** (cible amie, cible = le caster, ennemi hors portée, ennemi d=2 sous clamp mêlée). **Cas discriminant** : à **distance égale 2**, le natif ACCEPTE sans ennemi au contact et REFUSE avec — ce n'est pas la distance, c'est `forceMeleeTarget`. **Contrefactuels** sur le même état figé : `force_melee_target=False` -> `0x0` (faux accept), `range=None` -> `0x0` — les deux champs du preset sont porteurs. Généralisation : 2 couples board/seed (`MC1_67`/777, `C4_09`/31337) + sweep 24 points 0 désaccord. Cliquet : 1014 retiré de `SANS_TARGETING_OPTIONS` ; `ABILITY_ATTACK_TYPE[1014]` déjà posé et **confirmé** au décompilé (3ᵉ arg = 0 = `DirectTargetAttack`). |
| ~~#246~~ | ~~`ThunderousAssault` (1043) : masque de ciblage absent -> aucun gate sur les charges du Sword Brother~~ | **LIVRÉ (2026-07-29)** | `case-246-thunderous-assault-targeting.md`. Forme de ctor = **PRESET + FLAGS** (la 2ᵉ) : `ThunderousAssaultAbility$$.ctor` recopie `TargetingOptions statics+0x40` **puis** appelle `TargetingOptions..ctor(&opts, &preset, 0x10000000, 0)`, surcharge qui **OR-e** (`dst+0x28 = flags \| preset+0x28`) -> masque effectif `0x10000000 \| *(statics+0x68)` = `0x10000000 \| 0x4000` = **`0x10004000`** (`CasterCanMove` \| `TargetIsEnemy`) : ni le littéral visible ni le preset seul. Portée = `TargetingRange statics+0x30` = **`RANGE_ADJACENT`** (`onlyAdjacent`, `overrideRange=1`) -> la « charge » exige une cible **déjà au contact**. **Mesure** (`probe_246_thunderous_targeting.py`, oracle `abilityReason`) : **5/5 d'accord natif/port sur 2 couples board/seed** (`MC1_67`/777, `C4_09`/31337), **4 casts illégaux que `master` acceptait** (allié au contact, le caster lui-même, ennemi à d=2, ennemi à d=4) dont le **cas limite d=2**. Contrefactuels : sans `TargetIsEnemy` -> faux-accepte les 2 cibles amies ; sans `TargetingRange` -> faux-accepte les 2 hors contact. **Résidu nommé** : `CasterCanMove` (bit 28) est une règle du volet CASTER (`GetInvalidCasterReason`), **non portée** — son 2ᵉ volet `MovementComponent.IsAllowedToMove` (`movementBlockers.Count == 0`) n'est pas modélisé, et son 1ᵉʳ volet (`UnitTrait.Stationary`) n'a **aucun porteur confrontable** sur 1043 ; vérifié **inerte** (casterReason natif = 0 sur toutes les lignes) et **seul porteur du bit dans tout le registre**. Cliquet : 1043 retiré de `SANS_TARGETING_OPTIONS` ; `ABILITY_ATTACK_TYPE[1043]` déjà posé et **confirmé** (3ᵉ arg = 0 = `DirectTargetAttack`). |
| #27 | Résidus `CalculateCustomUtility` : **1 restant** (1004) | `[opus]` | `case-27` — inventaire **re-dérivé du BINAIRE** le 2026-07-30 (`probe_27_custom_utility_inventory.py --build rnca9r7q6c` : 96 classes portent le slot, **toutes à `+0x338`**, **29 corps = 26 nommés + 3 partagés**) : **17 portés/couverts** (1014, 1020, 1029, 1051, **1098**, 1100, 1119, 1177, 1185, 1199, 1212, 1226, 1227, 1230, 1009, **1169**, **1148**), 4 npc-only, 1 dead-code, 1 en cours (1222), **1 résidu**. ⚠ **1142 et 1053 SORTENT de la liste sans port** (#27-4g, correction d'inventaire) : 1142 n'a AUCUN corps propre — `StikkbombPlaybook$$.ctor` → `0x41b` = 1051 **seule**, le « playbook partagé 1051/1142 » est faux — et 1053 partage le corps de l'attaque normale. **1169 et 1148 sont PORTÉS** (`case-302` §6 et §8) : leur verrou n'était ni « MoW » ni un refus du natif mais le **domaine de cible TUILE** — et, pour 1169, un **cooldown initial non purgé** qui s'était lu comme un refus. **Résidu restant** : **1004 MortisRound** — `GetTargetUtilityDiffOnDisplace` (évaluateur d'utilité de DÉPLACEMENT), dont la **troncature vers `int`** explique le « terme mesuré nul » des tranches 1-2. |
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
| #haze-ord | ~~**Le port DRAINE la mort immédiatement, le natif l'ENQUEUE**~~ — **LIVRÉ (2026-07-29)** | `[opus]` | **CLOS — `case-haze-ord.md`.** `AttackDamageOperation._fire_death_if_killed` est désormais `IdunBattle.Operations.RecordKillOperation$$Execute` (flag `Overkilled`, `RecordDeathReason`, `On(3)`, **`_add_death`**) suivi de `_verify_deaths` = `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths`, boucle **NON RÉ-ENTRANTE** : une mort causée pendant une séquence de mort (death-nova, riposte `FinalJustice`, report 1077) est traitée APRÈS elle, jamais en son milieu. L'entrée de file transporte le **`killTrigger`** (3ᵉ argument de `MatchState$$AddDeath`), rejoué par `KillUnitOperation` dans l'`AbilityEntities+0x138` — sans lui, différer le drain aurait ré-ouvert le gate anti-chaîne de case-haze-bonded. **Second défaut, indépendant** : le **site (A)** d'`IdunBattle.Operations.ApplyDamageOperation$$Execute` (`HasFlag(target, 8)` → `AddLeftoverHit` puis **`return`**) n'était pas porté — le port émettait `On(0x10)` sur un cadavre overkillé, donc un `Maybe(25)` d'`OnToxicDamageAbility` **en trop**. Les deux ne se compensaient pas : **−3 / +1**. Résultat sur le montage de référence : **natif 14 == port 14**, dégât par unité **3/3**. GENERALISATION craftée : **9/9 bit-exacts** (3 seeds x PV 800/1200/2000), dont **4 montages à 13 tirages** où le relais meurt EN MILIEU de série (le 2ᵉ bond doit y lire **3** leftovers -- ni 4, ni 1). Rayon de souffle chiffré (dérivé du code, `probe_hazeord_blast_radius.py`) : 6 call-sites réels d'`_apply_damage_pipeline`, **83** classes de trigger, **21** consommateurs de mort, **8** dont le behaviour peut TUER (4 avec le vecteur dans le corps de classe) — hors de cette fenêtre le changement est un **no-op strict**. Gardes : `test_death_queue_ordering_live.py` (7 offline + 15 live) ; non-régression **161 tests verts** (45 Haze, 26 mort/revive/nova, 41 dégât/consommateurs, 49 revive-après-overkill) + `engine_validate` seed 31337 = **27/27** abilities, 96 % de positionnement exact (baseline). **Résidus nommés** : `uc.alive` posé à l'ENQUEUE et non au DRAIN (la machinerie `fire_on_death` du port en dépend) ; le flag `Overkilled` non posé sur les reports 2..4 ; la death-nova qui TUE n'est pas confrontée LIVE. |
| #17 | ~~Surveillance des 2 résidus `move`~~ + ~~`s18 MartialInspiration`~~ — **1 SEUL résidu restant, et il est irréductible** | `[opus]` | **RE-DÉRIVÉ le 2026-07-30 sur `rnca9r7q6c`** (`case-52` §#17-s18 et §#17-move). (1) **`s18 MartialInspiration` : PÉRIMÉ** — le libellé conflatait la face DÉCISION `2468 s18` (fermée par #64, re-mesurée **HIT**, ability 12/12) et la face PRÉDICTION `31337 s16` (fermée par #33, **feed = 0** sur 35 confrontations). Ce qui manquait était la GARDE du canal `actorStats` par-pas : **livrée** (`test_martial_inspiration_actorstats_live.py` + `probe_17_martial_inspiration.py`, port fresh == natif 3/3 tours, canal périmé DIVERGE 2/3). (2) **Résidus `move` : l'étiquette « 2 over-fire RNG » était fausse pour l'UN des deux.** `1357 s6` n'était pas un tirage mais le gate DÉTERMINISTE `HasFlag(unit, ActiveAbilityUsed=2)` en tête d'`ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` — **porté et gardé** (move GEN 61/65 → **62/65**, ability inchangée ; `test_active_ability_used_gate_live.py`, 2 couples board/seed, contre-épreuve gate neutralisé). **RESTE ouvert et le restera : `2468 s4`**, `SpawnPoxwalkersPlaybook$$GetUseProbability = TurnsStarted × 1/5` → p = 0.2 au tour 1, vrai tirage (`BasePlaybook$$ShouldEvaluate` : `p>=1` True, `p<=0` False, sinon `NextBool(p)`). ~~**Résidu NOMMÉ non traité** : le `+1` de #64 (`NormalAttackPlaybook.calculate_custom_utility`) n'est retenu par AUCUN test~~ — **FERMÉ le 2026-07-30 par `#308`**. Mesure de criticité REPRODUITE (`engine_agreement_stages --build --seeds 2468 --steps 20` : référence `[ability] 12/12`, `s18 u77 ab=69 [MATCH]` ; terme forcé à `0.0` → `11/12`, `s18 u77 native(ab=69) engine=ability(ab=1191) [MISS]`, classé `native-gate`). GARDE livrée : `probe_308_normal_attack_bonus.py` + `test_normal_attack_bonus_decision_live.py` — montage qui fabrique la fenêtre d'exactement UN point d'utilité (bisection au pas de 1 sur `Damage`), où le scorer natif de paire classe 1191 DEVANT la normale (gap `0.9955`) et où le natif joue quand même la normale ; mutation à `0.0` → 3 tests rouges, dont la garde. |
| ~~#308-r~~ | ~~**La prédiction portée de `MartialInspiration` (1191) ignore le modificateur de dégât porté par les TRAITS de la CIBLE**~~ (résidu `N16`) | **LIVRÉ (2026-07-31, #316)** | **Le cadrage était plus ÉTROIT que le défaut** : ni propre à 1191 ni à `base_override`. Le foyer est `generate_multi_hit_attack_prediction` — le per-cible de `ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions`, par où passent **toutes** les abilities à dégât — qui ne threadait pas `target_traits` vers `calculate_attacker_modifiers_for_prediction`, là où `make_normal_attack_predictions` le threadait. Défaut `None` = « cible inconnue » ⇒ aucun bonus : dégradation SILENCIEUSE, UNILATÉRALE, et **fork prédiction↔combat** (la face COMBAT du même vecteur threade déjà `target_traits`). RE : le natif n'a **qu'UN** `AbilityEntities` pour les deux chemins (`DamagePrediction$$PredictAttackRaw` → `AbilityEntities$$.ctor(target = request+0x50)`, `Target@+0x10`), et le slot 0xd ne reçoit aucun identifiant d'ability. **SIX** effets d'attaquant sont concernés. Validé live sur TROIS volets : (a) fixture synthétique 4 bras (`BC.Units[].Traits` = seul curseur) — natif `[1496,2244]` / `[1795,2692]` (`BigTarget` **et** `Vehicle`, ×1.1996) / `[2993,4488]` (`Summon`, ×2.0), **deux magnitudes distinctes** donc un facteur compensatoire constant tomberait ; (b) cibles RÉELLES sur `C3_01`/777 — le datapoint d'origine reproduit (`pairUtility` natif **21.2822** vs **21.9021**) ; (c) autre caster / autre ability / autre CANAL — `adeptCanoness`/`BrazierOfHolyFire` (RANGED) et `CondemnorStake_ExtraDmg` (`ForAddition`, pas `ForPercentIncrease`) : natif `[3286,7942]` → `[13258,17914]`. Rouge vu par mutation du correctif sur les trois volets, témoin (attaque normale) resté vert. Gardes : `tests/engine/test_ability_prediction_target_traits_live.py` (7 tests) ; probe : `probe_316_ability_prediction_target_traits.py`. Résidu NEUF nommé : **`N22`** (les 2 call-sites `psyker.py` / `fury_of_the_ancients.py`, mesurés INERTES, cliquet `--inert-call-sites`). ~~Énoncé d'origine :~~ MESURÉ le 2026-07-30 (`C3_01`/777, `custoBladeChampion` `Damage=1190`) : contre `tauCrisis` (trait `BigTarget`) le port rend pour 1191 `raw [1496, 2244]` — **identique** à ce qu'il rend contre `necroWarden`, qui n'a pas le trait — alors que l'attaque normale du MÊME caster sur la MÊME cible passe bien de `[1428, 2142]` à `[1713, 2571]` (**×1.2**). `pairUtility` natif `21.2822` vs porté `17.7352` (Δ **−3.547**, entièrement expliqué par le facteur manquant : `21.9021 × 8536/10542 = 17.7352`). Conséquence de DÉCISION : à `Damage=1187` le moteur joue `69` là où le natif joue `1191`. Étage isolé (prédiction, pas utilité) : le port est bit-exact sur `69` contre la MÊME cible, et bit-exact sur les DEUX abilities contre une cible sans le trait. Chercher pourquoi la branche `base_override` de `_martial_inspiration_inputs` court-circuite `DamageCalculations$$CalculateAttackerModifiersForPrediction`. Reproduction : `python probe_308_normal_attack_bonus.py --auto --board C3_01 --seed 777 --target tauCrisis` (V2 1/2 bras). |
| ~~#17-off~~ | ~~**`MinDist(16)` OFFLINE : `state_bridge` compte des ARÊTES là où le natif compte des NŒUDS**~~ | **LIVRÉ (2026-07-29)** | `case-52` §#17-s5.2 et §#17-s5.5 (réécrits). `_pathdist_to_enemies` porte désormais le couple natif COMPLET — `MovementActionGenerator.u003CFindClosestEnemyu003Ed__8$$MoveNext` (argmin `<` STRICT, filtre `d > 0`, premier-gagne) puis `MinDistanceToClosestEnemyUtility$$GetMinDistanceToEnemy` (`GetPath(...).Count` = **NŒUDS**, extrémités incluses). **Mesure : 131 tuiles sur deux couples, 0 divergence offline** (`12345/MC1_67` 44/44, `777/C4_09` 87/87 ; avant : 14/14 fausses d'un pas). Les TROIS écarts annoncés sont fermés, et un QUATRIÈME a été levé au passage : (1) le `d == null` rend la constante statique `BaseUtility` `statics+0x20`, que son `.cctor` recopie de `FixMath.NET.Fix64.MinValue` (`NO_PATH_UTILITY` = -2^31, tuile RÉDHIBITOIRE — le repli hex ne subsiste que quand `pathdist_by_pos` est VIDE, cas qui n'existe pas côté natif) ; (2) `PathfinderType = 1` est un littéral, plus de bascule fly ; (3) le ClosestEnemy FIGÉ remplace le min-sur-tous — **et il est DISCRIMINANT sur `777/C4_09`** (le `minTous` s'écarte du natif sur 6 tuiles), donc désormais confronté et non plus « non discriminant » ; (4) **le `PathfinderType = 1` n'est PAS le `WalkPathfinder`** mais `IdunBattle.Entities.Pathfinding.IgnoreTerrainPathfinder` — aucun test d'occupant (son `IsValidPathNode` n'a même pas de paramètre `unit`) et `WeightCost = 10 + IsFilled` (SANS élévation). Porter le `WeightCost` du Walk (`10 - elevation`) faisait diverger 18 des 87 tuiles de `C4_09`, d'un pas EN TROP : sur un board à relief le chemin le moins cher au sens Walk est plus LONG. Conséquence qui dépasse la feuille : **la distance de MOUVEMENT et la distance de SCORING ne sont pas la même métrique** — l'IA note une proximité qu'elle ne peut pas forcément parcourir. Gardes : `test_min_distance_move_leaf_live.py` (`::test_min_distance_leaf_offline_equals_native_pathdist` sur les 2 couples ; `::test_min_distance_path_traverses_units_live`, montage CRAFTÉ où le prédicat Walk se tromperait de 1 et 2 pas sur 2 tuiles et où la garde ÉCHOUE si le gate d'occupant n'est pas exercé). Probes : `probe_17_s5_mindist.py`, `probe_17_off_occupant_gate.py`. |
| ~~#226-r~~ | ~~**`SkyStrike` (1025) : le per-hit LIVE n'est PAS plat alors que le port émet une valeur FIXE**~~ | **LIVRÉ (2026-07-29)** | `case-226r-skystrike-weapon-spread.md`. **Oui, weapon-path — et le décompilé nomme le commutateur.** Le nœud `Sum(NormalAttackDamage(caster), Direct(extraDmg))` n'est pas ce qui décide : `DSLFactory$$NormalAttackDamage` est LA MÊME factory que celle de l'attaque NORMALE (`ALoki_NormalAttackAbility$$AttackAmount`, xrefs), et `StatAmountFormula` rend bien UNE valeur. Ce qui bascule le pipeline, c'est le **8ᵉ argument** d'`AttackWithAttackDamage` : `SkyStrikeAbility$$ExecuteBehaviour` construit son `Nullable<AttackDamageBehaviourOptions>` avec l'**octet +6 = 1** (`uStack_1e2 = 1`, seul octet non nul ; +4 = `alwaysOverkilled` FlailSwing, +5 = `alwaysCrit` TacticalPrecision) — le même octet que `ALoki_NormalAttackAbility$$GetAttackDamageBehaviour` renseigne **depuis un getter de l'ability** pour l'attaque normale, donc le drapeau « calcul de dégât d'ARME ». Il transite `AttackDamageBehaviour+0x9e` → `AttackDamageOperation$$ExecuteHit` (options+0x2f) → `AttackPredictionRequest+0x6a` → slot 4 `DamagePrediction$$PredictAttack`, où `GetBaseDamageFix64` étale les bornes de ±`DamageSpreadPercentage` autour de `V = Attack + extraDmg`, RÉDUIT, puis tire (1 tirage/coup). **Contraste mesuré** : le smite Psyker (`PsykerExtraAttackAbility$$CreateBehaviour`) passe ce même `Nullable` **VIDE** et n'a aucune variance (live) — la famille de factory ne suffisait donc pas à expliquer l'écart. Port : mode `amount` de la feuille (`Sum(StatAmount(Caster(), Attack), Const(extraDmg))`) + nouveau `amount_spread_pct=20` (défaut **0** ⇒ no-op pour Psyker/Haze/HeroicFusillade). **24 coups live BIT-EXACTS** (`probe_226r_skystrike_spread.py` : 4 seeds adjacent + 2 seeds armure 4000 + 2 seeds charge dist 2) ; contre-modèle dégénéré 0/24, contre-modèle roll-then-reduce 4/24 (et 0/6 en régime armuré). `test_skystrike_cast_live` **asserte désormais** l'égalité port↔live coup par coup. |
| ~~#PAI-c~~ | ~~Consommateurs de `PerformAIAction` restants : Waaagh 1058, SendInTheNextWave 1016, Incursion 1021, Poxwalkers 1040, + retrofit CultDemagogue 1179~~ | **LIVRÉ (`3f7b9d1`, 2026-07-25)** | « #94 consommateurs SPAWN/AI-CONTROL ». Les 5 ids sont dans `ABILITY_CLASSES` (`WaaaghAbility`, `SendInTheNextWaveAbility`, `IncursionAbility`, `SpawnPoxwalkersAbility`, `CultDemagogueAbility`). Résidu restant, DISTINCT : l'ORDRE intra-groupe de `PerformAIAction(asGroup=1)` (plus bas dans ce fichier). |
| ~~#PAI-k~~ | ~~`ListenUpMaggotsEffect` (0x426) + chaîne `SwornProtector`→spawn de Kell~~ | **LIVRÉ** | Chaîne portée + confrontée live de bout en bout (`case-perform-ai-action` §5.1 + §6 réécrits). Ground truth : Kell apparaît vivant porteur de l'effet 0x426, le cast 1028 spawne **3** gardes (2 sans Kell) et son rayon `PerformAIAction` vaut **3** (2 sans Kell). La face DÉCISION `SupremeCommanderPlaybook` est portée dans la foulée (gate `IsFriendlyKell` désormais atteignable). |
| ~~#119~~ | ~~Face DÉCISION de `SupremeCommanderPlaybook` (1028) jamais confrontée à l'IA native~~ | **LIVRÉ** | `case-perform-ai-action` §6 (réécrit). Le gate (2) lisait `u["parentId"]`, clé qu'AUCUN RPC ne publie → `should_evaluate` constamment `False` = playbook enregistré-mais-mort ; **désaccord mesuré** (le natif caste, le port attaque). Corrigé par la reconstruction offline `_kit_spawn_visual_ids` ; ACCORD sur 5 états craftés (dont le discriminant « deux Creed, un seul Kell adverse ») + 2 couples board/seed. Étage (3) RE-corrigé : `chance = 1/2 + hp%(caster)/2` (stat 5 = Health), déterministe à PV pleins (20/20), mesuré 31/40 à 32 % de PV. Garde : `tests/engine/test_supreme_commander_decision_live.py`. |
| #66-r2 | ~~**FuelledByFury** (`ultraTitus`)~~ **LIVRÉ (#88 A1, 2026-07-28)** — reste **GhostRevive/TimeFlux** (`thousTerminator`) | `[opus]` | `case-66-revive-in-place` §8. **A1 FERMÉ** : les 3 « blocages » étaient périmés ou faux. L'émetteur d'`On(PendingDeathAdded=3)` est `IdunBattle.Operations.RecordKillOperation$$Execute` (triplet `(killer, killer, dying)`, publié AVANT que `VerifyDeaths` ne draine → donc strictement avant `On(1)`) — il avait été déclaré introuvable parce que le scan ne couvrait qu'UNE des trois formes d'appel du publieur (`r9d` / 9ᵉ arg / slot d'interface INLINE) ; `TriggeringAbility` a désormais un foyer unique (`evaluate_trigger_operation`, mirror de `BaseTriggeredAbility$$Execute`) ; l'effet 1324 est CAPTÉ live (le jeu le pose à l'`AbilityInit`). Validé live sur 2 régimes (riposte létale → Titus vivant à **7477** PV sur sa tuile ; non létale → mort), 5 gardes. **Bug réel levé** : la riposte FinalJustice était un NO-OP silencieux offline (gate acteur-mort #133 vs le littéral `1` que `UseActiveAbilityBehaviour$$Execute` force dans ses `AbilityOptions`). **Résidus** : `FuelledByFury_BlockOverkill` (1354, mécanique distincte). **A2 `GhostRevive/TimeFlux` LIVRÉ (#213, 2026-07-29)** — le SEUL revive NON-IN-PLACE du binaire est porté et validé live sur **deux** couples (board, seed) avec un montage où la tuile de MORT et la tuile de REVIVE DIFFÈRENT : `MC1_67/31337` (mort en (3,2) → revive en (1,2)) et `C4_09/777` (mort en (4,3) → revive en (3,3)), `hp = 3290` bit-exact live ET port. Trois précisions de RE ajoutées au passage : la tuile du ghost est `CurrentTurnStartTile` = `UnitComponent+0x18c` (écrit par `StartTurnOperation$$Execute`), **pas** « the hex he moved from » de l'i2 ; `HasBeenRevivedByAbility` lit `ActorStatisticsComponent+0xe0`, un set alimenté par `ReviveUnitOperation` et **jamais** remis à zéro (⇒ once-per-BATAILLE) ; `GhostEffect` a DEUX instanciations (`TimeFluxRevive` 1186 et `EchoesFromTheWarp` 1284), ce qui explique le fork d'`amount`. **Piège de mesure documenté** : avec un seul adversaire le runner bascule de tour après le revive et la regen `TimeFlux` s'ajoute (4487 = 3290 + 1197) — confond de portée, pas de montant. **Résidus nommés** : ~~`On(UnitRemoved)` sans émetteur porté (`RemoveUnitOperation` non porté)~~ **CLOS (#227, 2026-07-29)** — l'Operation est portée et les DEUX sites de despawn du port passent par elle ; `TileHasTriggeredAbility(BrokenIce=29)` structurellement faux (table tile-ability dans les assets Unity) ; ~~`UnitComponent+0x18c` non capté par `combatSnapshot`~~ **CLOS (#223 hook `f790ff4` + #230 câblage)** — `combatSnapshot.units[].currentTurnStartTile` est seedé par `snapshot._load_unit_turn_state`, et le PREMIER move après un `load_state` frais pose le time-ghost sur la bonne tuile sans rejouer de `StartTurnOperation` (garde `test_load_state_turn_state_live.py`). **La branche `StatAmount` du fork d'amount (`EchoesFromTheWarp`, 1284) est FERMÉE sans port (#228, 2026-07-29) : NON PERTINENT** — cf. `case-66-revive-in-place` §8.4. |

| ~~#228~~ | ~~Branche `StatAmount(src, Health, max)` du fork d'`amount` de `GhostEffect` (`EchoesFromTheWarp`, effet 1284)~~ | **FERMÉ SANS PORT — NON PERTINENT (2026-07-29)** | `case-66-revive-in-place` §8.4. **Un seul porteur dans tout le parc**, `thousNpc4Terminator` (« Scarab Occult Terminator »), bucket **npc** : absent de `--list-pool` (rank 17, 97 rég. + 8 MoW), **aucun summoner** (0 des 559 abilities du gameconfig ne cite son id — ses 308 occurrences sont des `waves[].army` de campagne PvE). Le domaine de la branche est FERMÉ au décompilé : `GhostReviveAbility` a exactement **2** sous-classes (`TimeFluxReviveAbility` 1186 → branche `Direct('hp')` **portée** ; `EchoesFromTheWarpAbility` 1284 → cette branche), `GhostEffect` en a **0**. Les trois portes du gate de confrontabilité sont donc fermées ⇒ pas de port (invalidable = spéculatif). **Mesure qui vaut au-delà du cas — la voie `catalog_inject.py` ne débloque QUE le bucket `lineup`.** Injecté au catalogue `BC.Units`, `thousNpc4Terminator` est refusé par `IdunMetaLogic.Formulas.StatsFormula$$StatsUsingProgressionIndexFor` aux ranks 0,1,3,5,8,11,14,17,19,20 (`v2 patch: system error`) ; contre-épreuve : `thousDaemonPrince`, MÊME outil / MÊME seed BC, entre dans `normalized` (107 vs 106, skipped 69 vs 70). **Cause LUE, pas déduite** : l'exception ne vient PAS de la table de progression (la branche `ContainsIndex(progressionIndex)` retombe proprement sur `0`) mais du `Dictionary.get_Item(<cfg+0x40>+0x10, unitId)` qui suit — un lookup **par unitId**, `KeyNotFoundException` sur clé absente. Le hook ne passe à la formule que `(unitId, isMow, rank, progressionIndex, items)`, jamais le bloc `UnitConfiguration` ⇒ **aucun enrichissement du seed BC ne peut lever ce refus**. Généralisation mesurée (5 unités, même injection, rank 17) : `lineup` → **True** ; `npc` (`thousNpc4Terminator`, `necroNpc1Warrior`) → False ; `summons` (`ultraSmnInceptor`, `necroSmnSwarm`) → False. ⚠ **À ne pas confondre avec le `system error` de #226** (`AbilityConfiguration$$GetVariableForLevel` **au CAST**, config `BC.Abilities` manquante, réparable) : même libellé, appelant différent, diagnostic opposé — distinguer par l'APPELANT, jamais par le libellé. Re-dérivable : `probe_228_echoes_carriers.py [--seed-bc <bc>] [--ranks] [--buckets]`. |
| ~~#227~~ | ~~**`On(UnitRemoved = 0x25)` n'a AUCUN émetteur côté port** — `RemoveUnitOperation` non portée~~ | **LIVRÉ (2026-07-29)** | `case-227-unit-removed-emitter.md`. Verdict re-dérivé (pas hérité) : **1 écouteur, 0 émetteur** (`probe_227_unit_removed_blast_radius.py`, qui balaie les 4 registres et grep les appels). Chaîne portée : `DSLFactory$$RemoveUnit` → `RemoveUnitBehaviour$$Execute` (slot +6, args `(uid, 1, 0)`) → `OperationProcessor$$RemoveUnit` → **`RemoveUnitOperation$$Execute`** (nouveau `operations/remove_unit.py`) — gates (entité inconnue / pas une unité / **flag `Removed` déjà posé**), pose de `UnitFlagsComponent.REMOVED (26 = 0x1a)`, publication d'`On(0x25)` `(a=b=c=l'unité retirée)` **PUIS** `RemoveEffects` (l'ordre est load-bearing : les deux sites du port consommaient les effets sans jamais émettre). Les DEUX sites de despawn y passent (`behaviours/lifecycle.py::RemoveUnit`, `abilities/loki/mv71.py::_remove`) ; `resurrect.py` porte au passage le `Remove(0x1a)` que le natif fait avec `Remove(6)/Remove(0xf)/Remove(8)/Remove(9)` — le cycle pose/retrait est fermé. **Atteignabilité chiffrée du consommateur unique** (`GhostRemoveOnSourceRemoved`, effet 1186) : **0** — il exige que le poseur du ghost (Toth) soit retiré, or aucune des 5 abilities natives `RemoveUnit` ne le fait (MV71 → un drone ; `AggressiveOnslaught` → `Children(Owner)` ; `HunterOfSouls` → son propre porteur ; `NoHidingFromTheWatchers` npc/summon ; `PriorityReclamation` **0 porteur**). Ce foyer ferme donc une infidélité STRUCTURELLE, pas un comportement observable en partie. Gardes : `tests/engine/test_unit_removed_vector_live.py` (6 verts), **mordant prouvé par 2 mutations adversariales** (neutraliser l'émission → rouge ; retirer `fl.add(REMOVED)` → 2 rouges) et par la contre-épreuve embarquée (le despawn « à l'ancienne » laisse `ghosts=[21]`, le ghost étant porté par la TUILE). Non-régression : `probe_213_ghost_revive.py` OK (hp de revive live == port == 3290). **Résidu ouvert** : `alive=False` reste le collapse du retrait de tuiles — une unité retirée est indistinguable d'une morte pour les sélecteurs du port. |
| #BL-1029r | **`Drachnyen_ExtraAttackAbility` (triggered 1485)** — le 2ᵉ volet de dégât d'Abaddon, ~40 % du dégât observé au cast | `[opus]` | `case-bl-1029-1020` §5.1 : la face ACTIVE (1029) est portée et pose bien l'effet 1471 qui ARME cette triggered, mais la triggered elle-même n'existe pas offline → **10 coups live vs 5 offline** au cast (mesuré seed 777/MC1_67). RE **déjà faite, à recopier** (trigger + behaviour + validTargets cités in extenso dans le case doc) ; infra prête (`EFFECT_TRIGGERS[1471]`, patron `PsykerExtraAttackAbility`). **Seul nœud manquant : `SortUnitsByDamageUtility`** (précédent de collapse : `ExemplarOfHate`). Carrier `blackAbaddon` = HERO dans le pool ⇒ validable live. |
| #BL-1020r | **Magnitude de l'effet 1027 `HeraldOfTheApocalypse_ExtraDamage`** — posé mais INERTE | `[opus]` | `case-bl-1029-1020` §5.2 : `…$$CreateEffectDamageBonusForAttack` = `ForAddition(OwnerIsTarget & IsUnit(Caster@0x160), ConfigVar(8 = extraDmg), AbilityOrEffect(0x3fc))` ; consommation = `…$$CreateHandleTriggerAbilitiesInternal` = `Triggered(On(9) & OwnerIsTarget & IsUnit(Caster), GetRemoveEffectBehaviour())` (+extraDmg au PROCHAIN coup reçu, puis l'effet part). Patron identique aux `*_ExtraDamageEffect` déjà portés (`effects/loki/extra_damage.py`) → travail de recopie, pas de RE. |
| #120bis-spawn | **`SwornProtectorAbility$$GetSpawnTile` : `SortTilesByUtilityForSummon` non porté — résidu devenu OBSERVABLE** | `[opus]` | `case-120bis-flailswing-haze-confound.md`. Le port collapse `First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(tilesC)), TestUnitProvider(UtilityBucket[WeightedUtility(7), WeightedUtility(0x33)]), owner@0x148), 1)` en `First(CanAddUnit(AdjacentTiles(Caster())))` (résidu déclaré dans `triggers/loki/sworn_protector.py`). Il était **inobservable** ; il ne l'est plus depuis case-209 : la tuile de spawn décide de quel côté Creed se retrouve après le switch, donc s'il tombe dans `AdjacentEnemies(caster)` — c'est-à-dire s'il devient **relais `HazeOfCorruption`** et encaisse le report 1077. MESURE : le natif fait apparaître Kell du côté **OPPOSÉ** à l'attaquant (`d(caster, creed) == 2`) sur **3/3** montages live (`MC1_67`/777, `MC1_67`/31337, `C3_26`/777) ; le collapse offline, lui, rend `d == 1` sur **163 des 316** couples adjacents de `MC1_67`. Le bucket est `WeightedUtility(7)` + `WeightedUtility(0x33)` — les deux utilités sont à relire au décompilé avant tout port. |
| #254-bc | **Re-dump du seed BC après la migration de build** — le bloc `Units` reste celui de `gqfc5mff6c` | `[opus]`+arbitrage | `case-254-build-migration-blockers.md` §7. `_load_seed_bc` rafraîchit désormais `BC.Abilities` (le blocage), mais **pas** `BC.Units` : `necroOverlord` porte encore `PassiveAbilities [1045]` là où le gameconfig vivant dit `MyWillBeDoneOverlord` (1556), et ses `Traits` n'ont pas `Resilient`. Rafraîchir le bloc `Units` offline toucherait des champs d'ÉTAT JOUEUR (progression, relique équipée) que `catalog_inject.synthesize` ne connaît pas ⇒ la voie propre est `python dump_boards.py`. **À arbitrer, pas à faire en passant** : un re-dump change le pool spawnable ET les stats de référence de tous les tests live. ⚠ **Deux conséquences MESURÉES** (`case-392`) : il retirera `MartialApotheosis` du montage — `test_martial_apotheosis_live.py` rougira alors sur sa garde T0, qui dit quoi faire — et il rendra enfin `MyWillBeDoneOverlord` dispatchable (#392-r1). |
| #254-tau | **`test_tau_targeting_live.py` : 2 rouges de MONTAGE** (pré-existantes, non causées par #254) | `[opus]` | `case-254-build-migration-blockers.md` §7, contrôle joué par `git stash` (identiques avec et sans le correctif). `test_1082_inspired_to_greatness` : `cf_range == 0`, la mesure n'expose aucune cible alliée HORS contact, donc le volet PORTÉE du masque 0x402 n'est pas exercé. `test_dynamic_rules_bite_and_flip` : en T2 l'ennemi amené au contact n'inflige **aucun** dégât (`7530 -> 7530`), donc le disjunct `IsDamagedUnit` d'`EntityCanBeHealed` reste non exercé et le basculement testé n'a pas lieu. Les deux demandent de **driver les positions/dégâts**, pas de toucher au port. Même famille : `test_charge_tile_utility_live.py::test_forward_spotter_spawn_tile_follows_tile_utility` (« tuile de spawn introuvable dans les events du cast 1143 », rouge identique avant/après). |
| ~~#322-r1~~ | ~~**Face COMBAT de `ModifiedExoarmour_ExtraDmg` INERTE — le runner n'a aucun compteur de tuiles parcourues**~~ | **LIVRÉ (#335, 2026-07-31)** | `case-322-modified-exoarmour-extradmg.md` §6. Le compteur est posé AU FOYER, l'Operation de déplacement : `MoveUnitOperation` appelle `components.record_tiles_moved` (mirror de `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved` — `+=` sur `ActorStatisticsComponent +0xec` ET `+0xf0`, no-op si le compte est `< 1`) avec `GetNumTilesMoved(connectedPath) = Count − 1` du **WalkPathfinder** (foyer partagé `Board.walk_maps_by_pos`, le même que la face DÉCISION et que la face MOUVEMENT #304) ; `EndTurnOperation` le remet à zéro (`reset_tiles_moved_this_turn`, mirror de `ActorStatisticsComponent$$ResetThisTurn` : `+0xf0 = 0` **inconditionnel** sur `GetAllUnits`, `+0xf4 = +0xf0` pour le joueur qui finit) ; `attacker_modifiers` threade la clé. ⚠ **La branche RÉELLE d'`Execute` n'a PAS le gate `HasTriggeredAbility(0x5f9)||(0x4de)`** — ce gate n'existe que côté SIMULATION (`GetNumTilesMovedForSimulation`). Mesuré live, 2 plateaux × 2 longueurs de pas, bit-exact : `MC1_67/909` pas=1 `[3980,4303]`, pas=2 `[5500,5073]` ; `C1_25/31337` pas=1 `[5233,4301]`, **pas hex 3 → n = 4** `[7049,6124]` (détour de chemin : le port compte par le PATHFINDER, pas en distance hex). Contrefactuels : compteur forcé à 0 → −623/coup et −1247/coup ; forcé à 1 sur le bras n=2 → −624/coup. Gardes : `tests/engine/runner/test_tiles_moved_combat_live.py` (8), 2 mutations vues rouges. **Résidus nommés** : `DisplaceUnitOperation$$AddTilesMoved` non porté (sous-comptage sur un déplacement AMICAL) ; le lift-off de `TheQuickening` n'enregistre rien. |
| ~~#322-r2~~ | ~~**Terme RÉEL de `TilesMovedThisTurn` non capté — la prédiction sous-estime après un déplacement déjà joué**~~ | **LIVRÉ côté OFFLINE (#340, 2026-07-31)** | `case-340-tiles-moved-prediction.md`. ⚠ **Le classement « exige une réinjection » était FAUX pour la moitié qui compte** : la voie que la chaîne de décision emprunte (`Scene.from_state`) lit un ECS qui portait **déjà** le compteur depuis #335 — la face prédiction le reconstruisait à zéro (`real = 0` en dur). Même forme que #267 (traits) et #266 (flag `Moved`). Fix = `Scene.tiles_moved_by_id` + accesseur tri-état, lu par `prediction_tiles_moved_this_turn`. Le modèle à deux termes est ATTESTÉ : `SimulateEffectsOperation$$DoActionInSimulatedTile` **sauvegarde `+0xec`/`+0xf0` avant l'action simulée et les restaure après** (le pendant `$$DoActionInSimulatedOnSameTile` ne touche pas le composant), donc une prédiction depuis la tuile courante rend le compteur réel **tout nu**. Mesuré `MC1_67/909`, même tuile de part et d'autre du même pas (invariant NATIF(avant)==NATIF(après)) : pas 1 `[7672,10882]`, pas 2 `[8920,12130]`, **pas 2 hex avec rival bloquant → n=6** `[13910,17120]` — tous bit-exacts, contrefactuel `n=0` à `[6426,9636]` (**−1246 / −2494 / −7484**). Le rival donne le discriminant chemin-vs-hex (2 hex = 6 tuiles de chemin). **Argmax RENVERSÉ, mesuré : 11/35 points** changent l'action retenue (cible ET tuile). Gardes : `tests/engine/test_tiles_moved_prediction_live.py` (8), 2 mutations vues rouges. |
| ~~#340-r1~~ | ~~**Capteur `ActorStatisticsComponent+0xf0` non déployé — la voie live-capture de la prédiction reste au terme « pas simulé » seul**~~ | **LIVRÉ (2026-07-31)** | `case-340-tiles-moved-prediction.md` **§8**. Le capteur déployé est CONFRONTÉ, pas cru : on exige de `+0xf0` les DEUX transitions du composant (un pas → `RecordTilesMoved` ; `EndTurnOperation` → `ResetThisTurn` → 0). Les deux voies live sont bit-exactes sur **5** valeurs de `n` (1, 2, 3, 4, **6**) et **2** plateaux — `MC1_67/909` `[7672,10882]`/`[8920,12130]`/`[13910,17120]`, `C1_25/31337` `[10168,13378]`/`[11416,14626]` — contrefactuels −1246/−2494/−7484/−3742/−4990. Le bras RIVAL vaut discriminant CHEMIN-vs-HEX **sur le capteur** (2 hex bloqués = 6 tuiles de chemin, le capteur rend 6). Referme aussi le seed de `load_state` (`load_state(actor_stats=…)` + `snapshot._load_actor_statistics`, garde `< 0`). Gardes : `test_actorstats_sensor_live.py` 12 passed + 1 xfail (cliquet du reinject), **4 mutations vues rouges**. ⚠ **Le contrôle a trouvé un BUG au passage** — cf. `#340-r2` ci-dessous. |
| #340-r2 | **`actorStats.tilesMoved{ThisBattle,LastTurn}` lisent `comp - 1` — correctif livré, non déployé** | réinjection | `case-340-tiles-moved-prediction.md` §8.2. `getFieldOffset` rend **-1** sur un nom absent, et l'idiome `getFieldOffset(k,"X") || 0xec` ne teste que `0` — or **-1 est *truthy* en JS**, donc le repli décompilé n'était JAMAIS pris. MESURÉ : les deux champs rendent **-1201836032**, la MÊME valeur (signature d'une lecture à la même adresse), pendant que `TilesMovedThisTurn` — seul nom qui EXISTE dans les métadonnées — est exact. Ce n'était pas une erreur de RE : les trois offsets sont justes au décompilé. Correctif AU FOYER livré (`helpers.ts::fieldOffsetOr`, `off >= 0 ? off : fallback`) + les **14** call-sites du pattern (`rpc-snapshot` 8, `effects` 8, `projection` 1) : no-op quand le nom existe, mais c'est au prochain **changement de build** qu'il compte. Aucun lecteur porté ne dépend des deux champs faux, et le garde `< 0` de `_load_actor_statistics` empêche le garbage d'entrer dans l'ECS. ⛔ Exige une réinjection ; après elle, le xfail de `test_the_two_other_counters_are_measured_either_way` doit passer au VERT. |
| ~~#335-r1~~ | ~~**2 des 4 call-sites natifs de `RecordTilesMoved` non portés — sous-comptage sur déplacement AMICAL et sur revive**~~ | **LIVRÉ (#347, 2026-07-31)** | `case-347-tiles-moved-call-sites.md`. Les deux call-sites manquants comptent en **distance HEXAGONALE** (`MovementQuery$$GetDistance` = min de `CubeCoordinate.Distance`, aucun pathfinding), pas en longueur de chemin — l'inverse de `MoveUnitOperation$$Execute`. Portés : `displace.py::_add_tiles_moved` (+ `_is_enemy`) et le comptage de `revive.py::_set_revive_position` ; nouveau mirror `battle_query.py::get_distance`. **Le piège du double comptage n'existait pas** : balayage EXHAUSTIF des 8 feuilles qui construisent un `DisplaceUnitBehaviour` — seules `DSLBehaviors$$SwitchPosition` et `$$Teleport` posent `DisplaceUnitBehaviourOptions+0x1c` (le gate `options+0x10` d'`AddTilesMoved`), les six autres (dont TOUS les push) le laissent à 0 ⇒ un push n'enregistre rien, et le `record_tiles=False` de #335 était exact. Les deux moitiés d'un switch ne sont PAS symétriques : la moitié « caster » passe `target = caster`, donc son gate `!IsEnemy` est toujours passant. **NON CONFRONTÉ live** : le capteur `actorStats.tilesMovedThisTurn` de #340 n'est pas déployé, et aucun consommateur du compteur n'est atteignable par ces mécanismes (§6 du case-doc). Gardes offline : 12 tests, 2 mutations vues rouges. |
| #347-r1 | **Lift-off de `TheQuickening` : ce que le natif facture dépend de l'HISTORIQUE de mouvement du tour** | `[opus]`+réinjection | `case-347-tiles-moved-call-sites.md` §8. Le lift-off (`MoveUnit` vers une `UnitPosition` vide) **sort avant** `RecordTilesMoved` (branche `Count(position) == 0 && MoveUnitOptions+0x15`) ; c'est le **move-in** qui facture, avec `movementStartPosition = GetPreviousPositionThisTurn` (`UnitComponent+0x98`, écrit par `SetUnitPositionOperation$$SavePreviousPosition`). L'explication portée jusqu'à #347 (« `CalculatePaths` rend `[endTile, endTile]` sur le lift-off ») était **fausse** — corrigée dans `quickening.py`. Non mesurable sans le capteur `+0xf0`. |
| ~~#237~~ | ~~**Forcer une relique en bataille — le verrou de NIVEAU**~~ | **LIVRÉ (2026-07-31)** | `case-237-relique-forcee.md`. La condition exacte, nommée : **`BC.Units[].TertiaryAbilityLevel >= 1`** (`UnitConfiguration+0xc0`), lu par `IdunBattle.Entities.Factories.UnitFactory$$Build` → `AbilityState`, consommé par `IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel` (foyer UNIQUE des 4 accesseurs de variable), comparé à `0` dans `Idun.Shared.Level$$ToZeroBasedIndex` qui **lève `InvalidOperationException`**. ⚠ Ce n'est PAS le niveau du HÉROS : `UnitProgression$$ProgressionLevelNeededToUnlockTertiaryAbility` est côté META et n'est jamais emprunté quand on fabrique le BC. **Pas de borne haute** (le même foyer clampe `idx >= len` → `len − 1`, donc les 50 écrits par `buildNormalizedBC` rendent le palier 10). Montage livré en fixture : `rl_duel build --equip-relic "<unitId>:<Ability>[:level]"`, `catalog_inject.equip_relic` / `write_relic_seed_bc` / `--list-relics` / `--relic-state`. Trois écritures obligatoires, dont **deux échouent en silence** ; l'ORDRE compte (config avant normalisation, couple après). Ventilation re-dérivée : **4** équipées / **52** au catalogue sans relique / **9** hors catalogue. Ferme `#323-r1`, PAS `N317-a`. |
| ~~#357~~ | ~~**Résidu `N317-a` : le port ne LIT la relique équipée sur AUCUNE face**~~ | **LIVRÉ (2026-07-31)** | `case-357-rail-relique-equipee.md`. **CINQUIÈME chemin de registration**, mirror de la branche tertiaire d'`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` (`TriggeredAbilityComponent$$TryAdd(id, tertiaryAbilityState, **3**)`, le `3` = hiérarchie Tertiary) : canal **OPT-IN** `load_state(ability_states=…)` → `snapshot._load_tertiary_abilities` (RPC `unitAbilityStates`, entrées de hiérarchie 3) → `UnitContext.tertiary_ability{,_level,_variables_multiplier}` (mirror `UnitConfiguration+0xb0`/`+0xc0`/**`+0x78`**) → `collect_triggered_abilities`, avec **déduplication** (mirror du `TryAdd` sur `KeyedCollection`) quand un npc porte la même relique en dur. Magnitude : `triggers/base.py::triggered_ability_state` mirrore les **TROIS** `AbilityState` d'`UnitFactory$$Build` et rend le couple TERTIAIRE quand l'ability vient de l'item équipé. **Mesuré live** (`tauFarsight` injecté au catalogue ← `DawnBlade`, kill mêlée, même capture rejouée 3 fois) : niveau 8 → NATIF **+6745** == port ; niveau 3 → NATIF **+5423** == port ; **sans le canal 0** ; **niveau passif 7273** (le clamp) dans les deux cas. Deux régimes NÉGATIFS sur le même montage (kill à `d=2` → `IsDefeatedByMeleeAttack` ; PV pleins → `EntityCanBeRepaired`) : **0 des deux côtés** — le rail n'a pas rendu le port permissif. **Tranche l'écart « 200 vs 100 »** laissé ouvert par #237 : `+0x78` vaut 200 sur EXACTEMENT les 4 unités qui équipent une relique au seed (100 sur les 171 sans), et en bataille 100 (deux sources) contre 180 pour `+0x74`. Ferme **`N317-a`** et **`N317-e`** ; **`N317-d`** reste ouvert mais son régime discriminant est mesuré et le port y a raison. **Résidu** : ~~le canal n'a qu'UN producteur~~ **fermé par #363** (canal ON PAR DÉFAUT, coût mesuré 33 ms/bataille) ; reste **1 relique sur 32** portée (les 31 autres n'ont pas d'ability portée). |
| ~~#363~~ | ~~**Résidu `#357-r1` : le canal de la relique équipée est OPT-IN, un seul producteur**~~ | **LIVRÉ (2026-07-31)** | `case-363-canal-relique-par-defaut.md`. **Le coût a été mesuré AVANT d'être tranché** : `unitAbilityStates` = **33,4 ms** médians, **constants** de 4 à 10 unités, contre **312,2 ms** (2v2) / **1347,2 ms** (5v5) pour la capture déjà faite → **+10,7 %** puis **+2,5 %** ; c'est le RPC le moins cher des cinq et le seul qui ne scale pas avec l'effectif (`decisionView` passe de 178 à 1175 ms). Seed Python **< 0,3 ms**. Coût sur un batch **NUL**, et c'est MESURÉ, pas affirmé : balayage AST, **569** appels de `load_state` — **333** tests / **236** probes / **0** `engine/` / **0** outils. `load_state(ability_states=…)` devient un **TRI-ÉTAT** (payload / `None` = AUTO / `False` = refus) servi par un transport AMBIANT (`snapshot.bind_live_rpc`, lié par `conftest.live_session`) : les 333 appels des tests sont couverts **sans éditer un seul call-site**. **Cache par runner = déterminisme**, pas perf (rejouer la même capture doit rendre le même résultat) ; purgé au dispose (rid recyclé). `State.ability_states_seed` porte la TRACE tri-état (`auto`/`given`/`refused`/`no-transport`/`unavailable:<msg>`) — une panne du capteur ne se lit plus comme « aucune relique ». Mesuré live : les **4** porteurs du seed vus par le port == oracle NATIF (hiérarchie 3) == oracle CONFIG (`seed-bc.json`), `(ability, 50, 200)` chacun ; contre-épreuves `refused` = **{}** et `given` == `auto`. Gardes : `test_363_ability_states_default_live.py` (10), mutation `TACTICUS_NO_AMBIENT_RPC=1` → **3 rouges ciblés**. ⚠ La prémisse « `engine_validate`/`rl_collect_batch` ne passent pas le canal » était une **NON-QUESTION** : ils ne construisent aucun `State` (la face DÉCISION lit déjà ce RPC par `engine/ai/context.py::live_triggered_ability_ids`). |
| #BF-chance | **Chance de fuite `BattleFatigue` non sourçable offline** — bloque le dispatch de `TriggerAbility(0x401)` ET rend arbitraire le défaut de la voie trigger-sur-mort | `[opus]`+prérequis | `case-bl-1029-1020` §5.3 + `runner/operations/behaviour.py` : `BattleFatigueAbility$$GetFleeChance` = `ConditionalAmount(TargetIsOverkilled, Direct(GetNumberConstant(0x33)), Direct(GetNumberConstant(0x2a)))` sur une `AbilityConfiguration` **absente du gameconfig**. Deux défauts INCOHÉRENTS coexistent aujourd'hui : `behaviour.py` FUIT toujours (voie trigger), `TriggerAbility` ne dispatche pas (voie Herald). Prérequis = capter les 2 constantes (point d'ancrage : `AbilityConfiguration$$GetNumberConstant` sur la config 1025, ou un sweep live de fréquence de fuite) ; ensuite les DEUX voies partagent le même gate. |

## Résidus documentés (pas encore des tâches)

Remontés par les cases closes ; à promouvoir seulement si un miss d'agreement les fait surface.

- ~~**`#323-r1` — le harnais n'ÉQUIPE aucune relique, alors que la voie est ouverte.**~~ — **FAIT
  (#237, `case-237-relique-forcee.md`)**. Le montage existe : `rl_duel build --equip-relic
  "<unitId>:<Ability>[:level]"`, `catalog_inject.equip_relic` / `write_relic_seed_bc` /
  `--list-relics` / `--relic-state`. Le verrou qui n'avait pas de nom était le **NIVEAU DE
  L'ABILITY** (pas celui du héros) : `IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel`
  convertit par `Idun.Shared.Level$$ToZeroBasedIndex`, qui **lève `InvalidOperationException` sur
  `<= 0`** — et `0` est exactement ce que porte toute entrée `Units` sans relique (171 du seed) et
  ce que produit `catalog_inject.synthesize`. Pas de borne haute (le natif clampe). S'y ajoutent
  deux écritures obligatoires : `TertiaryAbility` lui-même (sans lui
  `UnitFactory$$AddConfiguredAbilities` ne monte rien, **sans erreur**) et la config d'ability
  (**29 des 32** absentes du seed → « system error »). Ventilation re-dérivée : **4** équipées /
  **52** au catalogue sans relique / **9** hors catalogue. ⚠ Ne referme PAS **N317-a** — le rail
  COMBAT du port ne lit toujours pas la relique équipée ; ce cas livre le MONTAGE, qui rend
  justement cet écart mesurable. **→ `N317-a` fermé depuis, par #357.**
- ~~**`#357-r1` — le canal `load_state(ability_states=…)` n'a qu'UN producteur.**~~ — **FERMÉ
  (#363, `case-363-canal-relique-par-defaut.md`)**. Le coût a été **mesuré avant** d'être tranché :
  `unitAbilityStates` = **33,4 ms** de médiane, **constants** de 4 à 10 unités, contre **312,2 ms**
  (2v2) et **1347,2 ms** (5v5) pour la capture que l'appelant fait déjà — soit **+10,7 %** puis
  **+2,5 %**. C'est le RPC le **moins cher des cinq**, et le seul qui ne scale pas avec l'effectif.
  Coût sur un batch : **NUL** — balayage AST (`probe_363 --volet scan`) : **569** appels de
  `load_state`, **333** dans les tests, **236** dans les probes, **0** dans `engine/` et **0** dans
  les outils, `rl_collect_batch` et `engine_validate` compris. Le canal est donc **ON PAR DÉFAUT**
  (tri-état `payload` / `None` = AUTO / `False` = refus explicite), servi par un transport ambiant
  que `conftest.live_session` lie pour toute la suite live, avec **un seul RPC par bataille** (cache
  par runner — condition de déterminisme du rejeu, pas optimisation).
- **`#287-r1` — `UnitFlag.NoActionAvailable` (4) n'est posé par AUCUNE voie du port.** Le natif le
  pose en queue de cast (`IdunBattle.Operations.MarkUnitAsNoActionAvailableOperation`, jamais
  portée). MESURÉ par `probe_287_facade_combat.py` (`combatSnapshot.units[].unitFlags` avant/après
  un cast) : le caster gagne `[1, 2, 3, 4]` côté natif, `[1, 2, 3]` côté port. Résidu **TRANSVERSE**
  au turn-flow (il vaut pour toute ability, pas seulement 1100) ; le test #287 l'ENCADRE au lieu de
  le taire (l'écart de flags doit valoir EXACTEMENT `{4}`, sinon rouge). À promouvoir si un
  consommateur du flag entre au port (`VerifyUnitTurnEnded` ré-ouvre l'activation quand l'unité
  regagne des options). Cf. `case-287-sorcerous-facade-combat.md` §7.
- **`#287-r2` — les branches `dead_caster` / `dead_target` de `SwitchPositionOperation` sont PORTÉES
  mais NON CONFRONTÉES.** `IdunBattle.Operations.DisplaceUnitOperation$$SwitchPosition` traite les
  deux moitiés INDÉPENDAMMENT (une unité morte ne bouge pas, l'autre va quand même sur sa tuile) —
  c'est lu au décompilé, pas mesuré. Le gate de cible de 1100 + le `IsAlive(Caster)` de la triggered
  1180 rendent l'état difficile à atteindre par un cast normal, mais le levier existe
  (`--dmg-target` pour tuer l'allié entre le cast et le switch). À crafter si un observable en
  dépend.
- **`#287-r3` — la garde `IsTemporary` du switch** (+ son slot d'interface 0x92) : le port n'a pas
  de tuile TEMPORAIRE (`board` est statique). Inerte tant qu'aucune mécanique de tuile temporaire
  n'entre au port.

- ~~**Le refresh de `BC.Utilities` DÉMASQUE 2 termes TRIGGERED que le moteur ne porte pas**~~ (ex
  `#27-r3`) — **LIVRÉ (#271)**, `case-271-kustom-force-field-reworked.md`. Les DEUX clés
  `KustomForceFieldReworked_*` (0→10) sont portées et **confrontées live** : le natif suit le terme,
  facteur ×2 compris. Résidus restants : `#271-r1` .. `#271-r4` ci-dessus.
  **`Lakrimae_LikesNonMechanicalEnemies` (0→5) reste NON PERTINENT** : ses porteurs sont **npc
  uniquement** (Typhus) — hors-jeu, jamais confrontable, à ne pas dispatcher (gate de
  confrontabilité du CLAUDE.md). Le mirror offline seul serait un port invalidable.
- ~~**⛔ ORACLE DE PRÉDICTION NATIF CASSÉ sur le build `rnca9r7q6c`**~~ — **CLOS (#276, `864906e5`)**,
  `case-268-decodeur-prediction-perime.md`. Le décodeur est refait en **un foyer unique**
  (`frida/hooks/game/damage-prediction.ts`, appelé par les 7 sites qui décodaient chacun de leur
  côté), chaque offset documenté par la XREF qui le nomme, sous garde en deux étages (taille de
  classe live + sentinelles de forme). Mesure de fermeture : `aiPredict` rendait `[1, 100]` pour
  **tout** couple, il rend `[2178, 3267]` sur un coup dont le dégât live vaut **2375** ; les deux
  tests cités ici et **six autres rouges nommés** sont tombés du même coup (18 verts, 0 skip).
  ⚠ **Les offsets que cette entrée donnait étaient FAUX, et instructifs** : le stride `0xd8` de
  `ProbableDamageEvent` valait en réalité **`0xB8`**. `classes.tsv` publie
  `il2cpp_class_instance_size`, soit la taille **BOXÉE** — header `0x10` de tout `ValueType` inclus.
  Sur un stride d'itération de `List<T>`, se tromper de 32 octets par élément suffit à rendre du
  garbage sur **tout événement après le premier**. Ne jamais citer un chiffre de `classes.tsv` sans
  retirer le header.
- **Le décodeur de prédiction résout ses champs PAR NOM** — **LIVRÉ (#279)**,
  `case-279-resolution-par-nom.md`. `frida/hooks/game/damage-prediction.ts` ne fige plus aucun
  offset : il demande `AccurateHealthDamage` / `DefaultScenario.Damage.HealthDamage` aux
  métadonnées IL2CPP, qui sont **en process** (pas dans un dump qu'un worktree n'aurait pas).
  Mesure de conformité, `classFields` sur `rnca9r7q6c` : **0 écart sur 24** chemins — le fichier ne
  mentait pas, ce qu'on ferme aussi. Ce qui change est la NATURE de la garde : un champ **déplacé**
  est désormais SUIVI et signalé (`predictionLayoutDrift`, non bloquant), seul un champ **renommé**
  invalide la mesure (`predictionLayoutError`). La liste exhaustive des 18 champs tranche trois
  « non identifiés » de #276 (`DamageProfile`, `Modifiers`, `DeniedDamage`, plus
  `CannotBeGuaranteedKilled@0x89`), prouve que **`CurrentArmor` n'existe pas** (absence PROUVÉE, pas
  absence de preuve) et corrige un commentaire faux : `ProbableHealEvent.HealPrediction` est un
  ValueType INLINE de 8 o, pas un pointeur. **Borne mesurée** : `class_get_fields` ne descend PAS
  dans un ValueType imbriqué — la chaîne se compose maillon par maillon via `field_get_type`, et le
  header `0x10` d'un ValueType reste une connaissance de FORME extérieure aux noms (d'où
  `class_is_valuetype` dans `helpers.ts`). ⚠ **NON CONFRONTÉ** : le fix vit dans `frida/hooks/**`,
  il n'entre en vigueur qu'après `build:hooks` **+ réinjection**. La garde adversariale
  (`frida/tools/probe-279-layout-by-name.ts`, 8/8, vue ROUGE par mutation du `throw`) éprouve la
  RÉSOLUTION hors process, pas les valeurs émises par le bundle injecté.
- ~~**Étage PATHFINDING : le port SUR-ATTEINT d'UNE tuile**~~ — **LIVRÉ (2026-07-30)**,
  `case-224-pathfinding-overreach.md`. Le gate #131 (`BasePathfinder$$NodesInNextLevel` ->
  `WalkPathfinder$$IsValidContinuePathTile`) **était porté et n'était jamais exécuté** :
  `make_can_continue` lit `State.effects`, que seul le canal **OPT-IN** `load_state(tiles=tileMeta)`
  alimente — et la quasi-totalité des call-sites (dont le probe qui a produit le constat) ne le passe
  pas. Étage confirmé par mesure discriminante (`aiMovableTiles` ré-interrogé à `overrideRange`
  croissant) : la tuile en écart entre dans l'ensemble natif à **`mv + 1`**, jamais à `mv` — donc un
  pas de FLOOD-FILL en trop, pas un filtre d'arrêt manquant. Les **4** cas cités pendaient tous d'un
  **Swamp**. Fix : `make_can_continue(..., board=)` gagne une seconde source SUBORDONNÉE, le repli
  TERRAIN (`TERRAIN_BLOCK_ENTERING = {"Swamp"}`, fondé sur
  `ThornsBlockMovementAbility$$CreateBehaviour` = `AddBlockEnteringUnitsEffect(0) & …`), utilisée
  UNIQUEMENT quand l'état ne porte aucun effet de tuile (`state_carries_tile_effects`). **Second
  trou trouvé en craftant le cas discriminant neuf** (`EMC2_02`/4242, 13 Swamp) : `GetTileBlockingReasons`
  ne teste **aucun EffectType** — il relit le registre du `MovementComponent` qu'alimente
  `BlockTileMovementEffect$$ApplyInternal`, et **six** classes s'y enregistrent (`0x00`
  BlockEnteringUnits, `0x05` Fire, `0x11` Ice, `0x3a` Darkness, `0x5e` LandMine, + la base
  paramétrée sans appelant nommé). Le port ne connaissait que `0x00` ⇒ les tuiles `Fire` n'étaient
  pas des culs-de-sac. Chiffres (`extra` = `offline \ natif`, **0 `missing` créé**) : `MC1_67`/777
  **3 → 0**, `C4_09`/31337 **1 → 0**, `EMC2_02`/4242 **15 → 6** non hydraté et **6 → 0** hydraté.
  Garde-fou du repli : correspondance Swamp(live) ↔ effet bloqueur mesurée **75/75 sur 13 boards**
  (`probe_pathfinding_overreach.py --audit`) — au passage, l'affirmation de
  `test_block_entering_tiles_live` selon laquelle « les Swamp de `PVP_desert_04` ne portent aucun
  `BlockEnteringUnits`, la pose est CONDITIONNELLE » est **rectifiée** : ce board n'a **aucune**
  tuile Swamp live (les 10 venaient du dump BC, pas du plateau déployé). Garde :
  `test_block_entering_gate_armed_without_tile_channel_live`. Résidus nommés dans le case doc §6
  (bloqueur de décor hors tile-def en régime non hydraté, bit 0x4 `blockerId != 0`, bit 0x2
  `GetEffectiveDepth`, gate d'activation `UnitFlags`).
- **`docs/rl/kit-coverage.md` et `docs/rl/passive-ability-coverage.md` sont PÉRIMÉS** — régénérés
  (`audit_kit_coverage.py` / `audit_passive_ability_coverage.py`), ils rendent **203 + 169** lignes de
  diff, dont l'essentiel n'est imputable à aucune PR en cours : les compteurs sautent de **123 à 127**
  unités lineup. À régénérer **d'un seul commit dédié**, jamais en marge d'un port (ça noierait
  l'apport). Constaté le 2026-07-30 (`case-224-cursed-plague-bell-extramove` §4).
- ~~**`SpawnUnitOperation.execute` crée une entité SANS `PositionComponent` quand il manque une
  tuile**~~ — **LIVRÉ (2026-07-29)**, `case-spawn-requires-tile.md` (dispatché sous l'étiquette
  `#246`, numéro déjà pris par `case-246-thunderous-assault-targeting.md`). Le natif ITÈRE son
  tile-sélecteur (`IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute`, branche
  `SpawnUnitOptions+0x60 == 0` = `foreach (tile in tiles) AddUnitOperation.Execute(unit, [tile], …)`)
  : **l'entité naît de l'itération**, et le `count` d'une ability n'est PAS un compteur d'unités — il
  vit dans le sélecteur, dont le `First(<tri>, count)` rend **`min(count, len(source))`**. Les cinq
  points d'entrée de `SpawnUnitOperation` créaient l'entité AVANT de savoir s'il restait une tuile
  (`execute`, `execute_self_replica`, plus `_spawn_config_grot` / `spawn_decoy` /
  `execute_pilein_replica` sur le `tinfo is None`). **Mesure** (`probe_spawn_requires_tile.py`,
  natif vs port, `MC1_67`/777 et
  `C3_26`/31337) : à **1 voisine libre** le natif spawne **1** summon et `master` en spawnait **2,
  dont 1 sans `PositionComponent`** ; à **0 libre** le natif REFUSE le cast (bit 5
  `TargetHasFreeAdjacentTile`) et `master` créait **2 fantômes**. Contre-épreuve à 2 libres : 2
  summons des deux côtés, **positions identiques au natif** dans les deux régimes. Branche MULTI-HEX
  (`+0x60 != 0`, `DutyEternal` 1158) intacte — elle passe par la feuille DSL `Spawn`, qui itérait
  déjà (20 tests verts). Garde : `test_spawn_requires_a_tile` (régimes 2/1/0 voisines libres),
  vérifiée ROUGE sans le fix. **Re-confronté sur `rnca9r7q6c`** (le jeu s'est mis à jour après la
  livraison) : structure native inchangée aux deux branches, 6/6 lignes du probe reproduites avec les
  **mêmes positions au hex près**, et la vague de tests différée par la migration rejouée — 75 tests
  live verts au total. Au passage, `execute` évalue désormais son tile-sélecteur **une seule fois**
  comme le natif (résidu fermé, positions bit-exactes inchangées). **Résidus restants** (§5 de la
  fiche) : `AddUnitOperation$$Execute` sur liste de tuiles VIDE produit nativement une unité sans
  pied (aucun call-site ne l'exerce) ; `execute_self_replica` boucle `count` fois sur un
  `PickRandomly(…, 1)` — inerte, `SpawnReplica` n'est construit qu'avec `count = 1`.
- **`TargetingQuery$$GetCasterNotAddedReason` non porté** (`case-250` §4) — rend 0 (permissif). Il
  concerne les abilities `isSelfCasting = 1` castées sur leur propre caster : le natif y évalue
  `GetValidTargets(...).AllTargets.Count == 0` et peut rendre `0x800 AddCasterIfAtLeastOneTarget`.
  Porteurs du registre : `GetEmRuntz` (1045), `ScarabSummon` (1047), `ResurrectionOrb` (1009),
  `Chronometron` (1226), `AncestralFortune` (1207). C'est aussi **le seul chemin par lequel
  `CasterHasFreeAdjacentTile` (bit 21) pourrait mordre** pour ses deux porteurs (1028, 1047). Le
  porter suppose de porter `TargetingQuery$$GetValidTargets`, qui énumère tout le plateau.
- **`CasterHasFreeAdjacentTile` (bit 21) — lu, situé, non porté** (`case-250` §4, compte corrigé par
  `case-249-tile-has-enemy-unit` §3). Jumelle exacte du bit 5 appliquée au CASTER (`slot 0x51` sur
  `param_2`), juste après elle dans le filtre statique. **DEUX porteurs au registre, pas un** :
  `SupremeCommander` (1028) et `ScarabSummon` (1047), masque `0x208000` identique — cette ligne
  écrivait « son seul porteur 1047 » pendant que `targeting.py` écrivait « son seul porteur 1028 » ;
  les deux étaient faux, et c'est le fait qu'ils se contredisaient qui aurait dû alerter. Elle est
  **inatteignable** par la cascade pour les DEUX (même paire `isSelfCasting = 1` + `RANGE_SELF` :
  self-cast -> branchement `GetCasterNotAddedReason` ; cible ≠ caster -> `RANGE_SELF` refuse
  `TargetIsInRange` avant). Port = code mort non invalidable tant que le résidu ci-dessus n'est pas
  fermé. **Ne pas citer un compte de porteurs de mémoire** : le re-dériver avec
  `scripts/python/probe_249_unported_rule_carriers.py`.
- **`TargetIsNotAnObject` (bit 33) — lu, situé, non porté**, **QUATRE** porteurs : 1029 `Drachnyen`,
  1113 `Stormcaller`, 1202 `VigilanceEternal`, 1214 `Hailstrike` (`case-254` écrivait « seul porteur
  du registre » pour 1113 — corrigé par `case-249-tile-has-enemy-unit`). Le natif refuse une cible
  portant le trait `0xd Object` ; aucun montage connu ne produit une telle cible, donc la règle reste
  **non confrontable** en l'état. Point d'ancrage pour la fermer : une cible-objet en bataille (décor
  destructible), ou l'oracle ensembliste `abilityTargets` sur un board qui en porte une.

- **Gisement « playbooks de MOUVEMENT » : 42 restants, dont 31 à porteur spawnable TEL QUEL**
  (`case-193c` §1 et §6, moins `CursedPlagueBell` 1071 porté par `case-211` — chiffres
  RE-DÉRIVABLES par `probe_193b_carrier_pool_crosscheck.py`, qui lit le pool en LIVE). Le rang A de
  `case-193` §5 reste la file la plus rentable (3 lignes + une entrée au registre par item) — mais
  **relire chaque `GetAdjacent*Utility` au décompilé** avant de le traiter comme un 3-lignes :
  `case-193c` §3 en distingue TROIS formes, et l'exception annoncée (`CursedPlagueBell`) a coûté une
  RE complète — deux gates, dont un qui lit le `WeaponsComponent` du voisin, et un trait qui
  n'existe dans AUCUN `traits` du gameconfig (`case-211` §1.3). Restent en tête de file
  `MedicusMinistorum` (15), `Deathwing` (10), `TaintedNarthecium`. `[opus]`.
- ~~**`SpiritualLeader` (1275) : clé BC EFFECTIVE non résolue**~~ — **FAIT** (`case-212`) : la clé est
  `SPIRITUALLDEADER_AdjacentDecoy` (=30), indevinable par préfixe (**faute de frappe du jeu**). Elle
  se LIT désormais — `probe_212_bc_key_literals.py <symbole>` résout n'importe quel string literal
  natif (slot de metadata usage -> `global-metadata.dat`). Playbook porté, **cap `vtbl+0x228` = 1**
  compris (le terme ne somme PAS les decoys). Trois résidus ouverts par ce cas, ci-dessous.
- **`ExplosiveMaladies` (1068) : clés RÉSOLUES, playbook non porté** (`case-212` §7.3).
  `EXPLOSIBEMALADIES_AdjacentRangedFriend` (=15) / `EXPLOSIBEMALADIES_AdjacentChoasMeleeFriend` (=15),
  gates `HasRangedWeapon` puis `HasTrait(0x7ea)` — ⚠ le nom dit « Melee » mais **aucune instruction ne
  teste `IsMelee`**. Pas de cap, pas de filtre. Porteur à qualifier. `[opus]`.
- ~~**`FabricatorClawArrayPlaybook` (1006) : cap `vtbl+0x228` = 1 non appliqué**~~ — **FAIT**
  (`case-242`) : le cap MORD et vaut 1. Mesuré `X_nat` **PLAT à 30 pour 1, 2 ET 3 amis retenus**
  (`MC1_67`/777, 18 tuiles) là où le port rendait jusqu'à **120**. Le montage manquant a été
  construit — `_drive_cluster` DÉPLACE les alliés sur des voisins distincts d'une tuile atteignable
  par le carrier, et le seed BC est dérivé sans `TertiaryAbility` (la relique `NetherRealmCasket` du
  carrier ajoutait un SECOND terme sur le même voisinage, cf. résidu ci-dessous). Deux résidus
  ouverts par ce cas.
  **Re-confronté après la MAJ `gqfc5mff6c` -> `rnca9r7q6c`** (`case-242` §7.2) : relevé
  `methodPointers` REFAIT au binaire du nouveau build (bloc **inchangé**, mêmes corps fondus aux
  mêmes positions), garde live **10/10**, contre-épreuve **rouge sur les DEUX montages**
  (`n = 4 -> 120`). Deux points restent ouverts : un second couple board/seed discriminant au NATIF
  (`C4_09`/31337 plafonne à UN allié blessé, re-mesuré), et `X_nat` lui-même — inaccessible sur
  `rnca9r7q6c` (cf. entrée « hooks `scorer-damage-trace` » ci-dessous). La voie « argmax sans hook »
  a été tentée et **ne conclut pas** (`case-242` §7.4) : ne pas la re-tenter.
- **Les hooks de `scorer-damage-trace` portent des RVA `gqfc5mff6c` — toute mesure `X_nat` est morte
  sur `rnca9r7q6c`.** `RVA_CALC_TILE_PRED`, `RVA_ELEVATION_LEAF`, `RVA_CALC_ACTION_UTILITY`,
  `RVA_COMPOSED_UTILITY` et la table `leafHooks` de `frida/hooks/features/scorer-damage-trace.ts`
  sont hardcodées (gshared / itérateurs, non résolubles par `findMethod`). Conséquence : la
  décomposition par étage `X = Tile(7) - Elevation - TileEffects` — l'instrument de `case-193c`,
  `case-211`, `case-212`, `case-242` — n'est plus disponible ; les probes concernés vérifient le
  hash et refusent de tourner (ils ne mesurent pas à côté). Les re-résoudre demande un rebuild du
  bundle **et une réinjection**. Point d'ancrage à traiter à la prochaine fenêtre d'inject.
- **`FabricatorClawArray` (1006) : le gate `CanBeRepaired` du filtre, NON porté** (`case-242` §6.1).
  `IdunBattle.AI.Playbook.Loki.FabricatorClawArrayPlaybook$$FilterAdjacentFriends` fait
  `HasTrait(u, 5) && IBattleQuery.<slot 0x2e = CanBeRepaired>(u, false)` : un ami Mechanical à PV
  PLEINS n'est PAS retenu (`IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired` ->
  `IsDamagedUnit` -> `HealthComponent.IsWounded`). Mesuré sur les DEUX couples board/seed :
  `nMech=1, nRep=0 -> X_nat = 0` alors que le port rend 30 — régime NORMAL en début de bataille.
  Porter demande `hp`/`hp_max` dans les `friend_units` du `tile_leaf_ctx` (deux clés dans
  `engine/utilities/tile.py::_adjacent_units`). ⚠ Qualifier d'abord la seconde branche du OU :
  `UnitExtensions.GetStat(u, 4, …) > 0` avec `StatType` 4 = `Armor`, ÉTEINTE par le montage
  (`--hp-*` met `Armor`/`FixedArmor` à 0) — hors de ce régime le gate peut être PLUS permissif que
  le simple `IsWounded` mesuré. `[opus]`.
- **`NetherRealmCasketPlaybook` (relique 1462) : playbook de MOUVEMENT non porté** (`case-242` §6.2).
  Structure entièrement RE-solue :
  `IdunBattle.AI.Playbook.Loki.NetherRealmCasketPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext`
  = `+5 x #amis Mechanical adjacents (self exclu)`, SANS cap ni gate, clé
  `NetherRealmCasket_LikesAdjacentFriendlyMechanicals` (=5 BC). S'applique à tout porteur de la
  relique. ⚠ **Chiffre corrigé (#323)** : « 4 unités au seed BC » confondait *quatre unités portent
  UNE relique* et *quatre portent CELLE-CI* — **une seule** unité porte `TertiaryAbility = 1462`
  (`necroSpyder`) ; les **3 héros éligibles** via `R_Booster_Crit_NetherRealmCasket.allowedUnits`
  (`necroWarden`, `necroSpyder`, `necroDestroyer`) sont **tous dans le pool**. Une face NonOwner
  existe aussi (`NetherRealmCasket_AdjacentMechanicals` = 5). `[opus]`.
- **`AttractMechanicalsUtility` (feuille 57) PORTÉE mais INERTE** (`case-242` §6.3) :
  `meta["attract_mechanicals_neighbor"]` n'est jamais posé par `apply_tile_attributes` -> +10 natif
  non rendu sur toute tuile voisine d'un porteur de `DoctrinaImperatives` (1118) quand le mover a le
  trait 5. Même nature que le résidu `case-212` §7.1 (gap de CONTEXTE, pas de feuille) — à traiter
  avec lui. `[opus]`.
- **Le défaut de la BASE pour les caps `vtbl+0x228`/`0x238` toujours non lu** (`case-242` §6.4) : le
  bloc `methodPointers` d'un CONCRET ne contient que ce qu'il DÉCLARE, et le corps du défaut
  appartient à la base générique `AdjacentUnitPreferenceTriggeredAbilityPlaybook<T>`, absente du
  dump. On sait seulement qu'il est `>= 3` (`GuardianOrganismPlaybook`, `case-36`). `MAX_ADJACENT_*`
  reste `None` quand le concret est muet.
- ~~**`meta.steppable` / `meta.decoy_gate` / `meta.decoy_friend_count` jamais posés**~~ — **FAIT**
  (`case-241-steppable-decoy-tile-leaves.md`). Le +25 constant tombe à **0** sur les 6 tuiles à
  occupant decoy des deux montages, et les 16 autres (déjà à 0) y restent. Il n'y avait **aucun**
  attribut natif à lire : les deux feuilles dérivent leur donnée de l'OCCUPANT de la tuile
  (`TileContentComponent` + `HasTrait(0x1b Steppable)`) et, pour la 64, de `GetAllAliveUnits`
  (slot 0x88) — sans filtre de position ni exclusion de self, deux faits MESURÉS via
  `probe_241_decoy_tile_leaves.py --carrier genesPrimus`. La RE a aussi ajouté **deux branches
  manquantes** à la feuille 19 (court-circuits `SpikySting` 77 / `LandMine` 114, clés absentes de
  la BC donc muettes, mais qui priment sur le trait `Decoy`).
  ⚠ Résidu de ce cas : `test_thrice_blessed_decision_live.py` (2 tests, chemin `HasFaction`)
  **NON re-joué** — le run est tombé dans la fenêtre d'arrêt du jeu (MAJ `gqfc5mff6c` →
  `rnca9r7q6c`). Changement value-preserving par construction ; à re-jouer après migration.
- **`darkaSmnWatcher` (porteur de `WatchedOver` 1524) : chemin d'octroi non établi** — aucune
  `units.abilities[*].constants.unitId` du gameconfig ne le cite (`case-193c` §1.2). Seul summon du
  gisement dans ce cas.

- **Identité du `ClosestEnemy` côté LIVE : champ `closestEnemyId` en attente de reinject** —
  `case-236` §6. Le champ **est** désormais posé dans `ctx.rpc.pathDistToEnemies`
  (`frida/hooks/features/ai-step/rpc-board.ts`) et **consommé** par `_mindist_case`, mais le bundle
  injecté en session 28 est antérieur : le probe le classe `PENDING`, jamais `OK`. **À la prochaine
  fenêtre de reinject** : `probe_236_mindist_gates.py` doit passer ce `PENDING` en `OK`. En
  attendant, le port retombe sur son verdict d'unanimité — le **gate 4** reste suspendu quand les
  candidats sont **panachés** sur `HasTrait(Impervious)`, et il est de toute façon
  *registered-but-dead* dans notre régime (§4). Résidu connexe, **non fermable par ce champ** : le
  hook n'énumère pas dans l'ordre natif, donc à égalité de distance-chemin l'id retenu peut
  différer de l'argmin de `MovementActionGenerator.<FindClosestEnemy>d__8`.
- ~~**`noTargetableEnemies` posé mais pas encore exercé**~~ — **CLOS le 2026-07-30**. Mesuré servi
  par le bundle de la session 28 ; le port a basculé sur le champ **seul**, et le littéral d'erreur
  ne sert plus qu'à détecter un bundle antérieur — auquel cas `_mindist_case` **lève** au lieu de
  rendre un `None` permissif silencieux.
- ~~**`GetStat(unit, CriticalChance)` non lisible sans `Scene`**~~ — **CLOS le 2026-07-30**. La stat
  est celle que le RPC `combatSnapshot` invoque déjà (`UnitExtensions$$GetStat(u, 9, Current,
  null)`) : elle est lisible dès que l'appelant fournit un predictor, et le port la lit alors
  exactement (`0` sur `ultraTitus`, == natif, sur les deux faces). Sans `Scene` la suspension
  `None` demeure — **et c'est la règle**, pas un trou : `0` ferait mordre le gate sur une donnée
  jamais lue. Bug corrigé au passage côté OFFLINE : `getattr(scene.ctx(uid), "crit_chance", 0)
  or 0` rendait `0` pour une unité **sans `UnitContext`**.

- ~~**Cycle de vie de `ContagionsOfNurgle_ArmorReduction1/2` (1071/1072)**~~ — **CLOS par
  `case-cvc-contagions-lifecycle.md`**. Les trois manques (aura qui grandit, unité qui sort, bascule
  1071 ↔ 1072) étaient **un seul mécanisme** : la fenêtre `[min, max]` de `CreateActiveCondition`,
  ré-évaluée à chaque `RefreshEffectsOperation`, sur **deux instances qui coexistent** (le collapse
  « une seule instance, l'active » est défait — le canal `decisionView { includeInactive: true }`
  montre 1071 ET 1072 sur chaque ennemi du porteur). Le flag `EffectComponent.IsActive @+0x5c` a
  désormais son **producteur** (`refresh_stat_modifier_effects`), et `ContagionsOfNurgleAmount` n'est
  plus collapsé : il délègue au mirror `BattleQuery$$GetInRangeAuraAmount` de case-224. La variante
  **−40 %** est **mesurée live** (deux porteurs dans le même roster adverse : `FixedArmor`
  2312 → 1387), sur deux boards. **Reste ouvert** : les branches `UnitResurrected(0x2f)` /
  `UnitRevived(0x2e)` du même trigger, non câblées ; les triggers de refresh `UnitsChanged(5)` /
  `UnitStateChanged(3)` (le port refresh sur move + start-turn + après dégât) ; la part
  MULTIPLICATIVE `part 9` du stat-layer, matérialisée en delta plat équivalent.
- **Résidus nommés de `case-224` (prédicat d'aura)** — `case-224-is-in-contagions-of-nurgle-range`
  §5. (a) ~~le comparateur **STRICT**, non mesuré live~~ — **CLOS, RENVERSÉ, puis ATTRIBUÉ (#293,
  2026-07-30)**. Porter `CursedPlagueBellAttackAbility` (1071) a donné au prédicat son premier
  consommateur MOTEUR, donc son premier montage confrontable, et le seuil natif mesuré vaut
  `GetCurrentRange(TurnsStarted)` **exactement**, à deux paliers
  (`case-224-cursed-plague-bell-attack.md` §3.2). #293 a **localisé** l'écart d'une unité : il est
  dans le COMPARATEUR, et la lecture « STRICT » venait du **nom du `.ctor`**, corps trivial
  DÉDUPLIQUÉ par IL2CPP. La classe réellement instanciée est
  `AmountIsEqualOrGreaterAbilityTrigger` (`minAmount <= amount`) — établi par le pointeur de classe,
  pas par le nom ; les deux autres modèles sont réfutés étage par étage. Le port était **juste**,
  aucun changement de comportement. Garde : `probe_293_aura_predicate_comparator.py`. (b)
  `SynapseEffect`, second
  `IAuraEffect`, n'est **pas** au registre `_AURA_EFFECTS` (aucun consommateur mirroré ne le
  demande) ; (c) `GetNextTurnRange` / `isNextTurn=true` est porté mais jamais exercé (ses
  consommateurs sont `CursedPlagueBellMovementAbility$$GetTargetsSelector` et
  `CursedPlagueBell_DangerZoneEffect`). `[opus]`.
- ~~**Seuil d'`IsActiveAbilityCountedAsUsed` décalé d'une unité (trouvé en marge de #293)**~~ —
  **CLOS le 2026-07-30 (#295), la lecture héritée CONFIRMÉE et désormais MESURÉE**
  (`case-295-active-ability-counted-as-used.md`).
  `IdunBattleLogic.Entities.DSLTriggers$$IsActiveAbilityCountedAsUsed(isPreAbilityTrigger)` construit
  `AmountIsGreater(amount = DSLFormulas.TotalActiveAbilityUsed(...), minAmount = <seuil>)` avec la
  classe de la famille **STRICTE** — établi par le **pointeur de classe** (le sujet charge le global
  STRICT et AUCUN global INCLUSIF), corroboré par l'encodage (`setg` contre `setge`) et par l'ordre du
  ctor (`(this, amount, minAmount)`, `ShouldTrigger` = `minAmount < amount`). Seuil **découvert**, pas
  supposé : la branche `isPreAbilityTrigger == 0` (celle du port — l'appelant passe le littéral `0`)
  lit `DSLFormulas+0x20 = Direct(1)`, l'autre `+0x18 = Direct(0)`. Le natif évalue donc **`used > 1`**
  ; le port écrivait `used >= 1` et bloquait **une utilisation trop tôt** — une ability « comptée une
  seule fois par bataille » n'aurait alors JAMAIS compté. Corrigé
  (`fuelled_by_fury.py::COUNTED_AS_USED_THRESHOLD` + comparateur strict). L'écart était **INERTE**
  (`State.total_active_ability_used` n'existe pas) : aucun test live ne pouvait le voir, il se serait
  activé en silence au câblage du compteur — d'où deux gardes qui n'attendent pas ce câblage,
  `probe_295_active_ability_counted_as_used.py` et
  `tests/engine/runner/test_active_ability_counted_as_used_offline.py`.
- **Résidus nommés de `case-224` item 5 (face ATTAQUE de `CursedPlagueBell`)** —
  `case-224-cursed-plague-bell-attack.md` §4. (a) le cas **`d = 1` à `range = 1`** n'a jamais pu être
  monté sur `C1_02` (aucune tuile libre à distance 1 du porteur aux paliers bas, il est entouré) :
  c'est le seul point où les mutations `registry` et `range1` se distingueraient, et c'est aussi le
  point le plus serré du seuil. Levier : un board à voisinage OUVERT autour du spawn adverse.
  (b) le gate `HasTrait(Actor, Psyker)` n'est exercé **qu'en positif** — balayage : **0 unité sur
  683** porte une arme de profil Psychic sans le trait, le contre-cas n'existe pas dans le jeu et
  exigerait de poser un trait en bataille. (c) la disjonction `OwnerIsTarget | OwnerIsAlive` n'est
  pas discriminée (l'owner est toujours vivant ; elle ne le devient que si l'attaque le TUE dans le
  même flot). ~~(d) `!CurrentAbilityIs(this)` est porté sur le canal `TriggeringAbility`~~ — **CLOS,
  et REFUTE** (`case-292-current-vs-triggering-ability.md`) : le port lit le BON champ. Le canal
  `State.triggering_ability` est posé AVANT `execute_behaviour` et restauré après — trait pour trait
  la sémantique de `CurrentAbility` (`AbilityEntities+0x60`), que
  `BaseTriggeredAbility$$Execute` écrit avant le behaviour ; le champ homonyme `TriggeringAbility`
  (`+0x98`) est écrit APRÈS, pour le seul `On(0xd = UnitTriggeredAbility)`, non porté. Seul le NOM du
  canal Python était faux (corrigé dans les 4 docstrings qui l'affirmaient). Régime discriminant
  EXERCE : le double déclenchement du smite `PsykerExtraAttack` (1013) — `--mutate persist`
  (restauration supprimée) fait tomber `bloodMephiston` de 4860/2 fires à 2430/1 fire, `--mutate
  nogate` (gate seul) rend 0 désaccord (il est REDONDANT avec `!CasterIsTarget`). `[opus]`.
- **Résidus nommés de `case-292` (les canaux `AbilityEntities`)** —
  `case-292-current-vs-triggering-ability.md` §5 et §7.3. ~~(a) le champ natif `TriggeringAbility`
  (`AbilityEntities+0x98`) n'est pas porté du tout~~ — **CLOS par #294** : le canal est
  `State.trigger_ability_type`, écrit APRÈS `execute_behaviour` puis `On(0xd)` émis, et le montage
  qui le SÉPARE de `+0x60` existe (`probe_294_trigger_ability_channels.py`, chaîne
  `A --On(0xd)--> B` : `+0x60 = B`, `+0x98 = A`). Ce qui reste ouvert est ailleurs, et c'est
  **N18/N19** de `port-residuals-inventory.md` : le champ a **quatre** écrivains natifs, le port
  en modélise désormais **trois** (#294 écrivain 4, #301 écrivain 2, #306 écrivain 3 avec
  l'asymétrie ADD/REMOVE — `case-292` §9) ; ne reste que l'écrivain 1
  (`OperationProcessor$$EvaluateAbilities`), sans conséquence tant qu'il écrit la MÊME ability dans
  les deux champs. Celui qui produisait une divergence réelle était
  `IdunBattle.Operations.KillUnitOperation$$Execute` (`+0x98 = KillUnitOptions+0x04`, `+0x60` à
  ZÉRO sur `On(0)/On(1)/On(2)`). Et `On(0xd)` n'a **aucun consommateur, ni porté ni natif** (trou
  déclaré : 4 `Env*Ability$$CreateTrigger` à liste d'events construite par
  `RuntimeHelpers.InitializeArray`, blob illisible depuis ghidra-mcp).
  (b) sur le vecteur MORT, `IdunBattle.Operations.RecordKillOperation$$Execute` ne relaie pas le
  `CurrentAbility` ambiant : il lit deux `Nullable<AbilityOrEffect>` du `KillUnitContext` —
  `selected = HasValue(+0x1c) ? +0x1c : +0x00` part dans `MatchState$$AddDeath`, tandis que
  l'événement `On(3)` est publié avec `+0x00` via
  `Core.Services.OperationProcessor$$EvaluateAbilities`, qui écrit la MÊME valeur dans `+0x60` ET
  `+0x98`. Les consommateurs portés (`FuelledByFury` ← `FinalJustice`, `haze_of_corruption`) lisent
  le canal unique ; sur `On(3)` aucun montage ne peut les séparer — **c'est structurel**, pas un
  manque de montage. (c) le gate `!CurrentAbilityIs(this)` de 1071 n'est jamais exercé SEUL
  (`!CasterIsTarget` le couvre — `--mutate nogate` = 0 désaccord) : sa face discriminante propre
  reste non mesurée. `[opus]`.
- **Face DANGER ZONE de `CursedPlagueBell` : `CursedPlagueBellDangerZoneAbility` +
  `CursedPlagueBell_DangerZoneEffect` (1084)** — la dernière des quatre pièces de `case-211` §5.
  Elle consomme la branche `isNextTurn = true` de `GetTargetsSelector` (résidu (c) ci-dessus) et
  `CreateRangeBonusForDangerZone` / `GetExtraMovementAmount`. Axe PRÉDICTION de zone de danger, pas
  un stat-mod : l'observable est `decisionView.dangerZone`, à qualifier avant de s'engager. `[opus]`.
- ~~**`deathBlightlord` : +2 `genrand` natifs à l'entrée d'une attaque mêlée**~~ — **CLOS**
  (`case-207-haze-of-corruption-target-finder.md`). Ce n'étaient ni les effets `1375`/`1147`
  (= `TerminatorArmour_Visual` / `_ReduceDmg`, purement défensifs) ni le spawn de Kell, mais
  `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility` :
  `On(0x2b) & get_OwnerIsCaster` → `PickRandomly(Damageable(AdjacentEnemies(Self) &
  AdjacentFriends(Target)), 2)`, soit `min(|pool|, 2)` tirages AVANT tout coup. Il y en a **deux**
  ici parce que `SwornProtector` fait ré-émettre `On(0x2b)` par la ré-entrée #120bis — **1 + 1**,
  pas un forfait. Port 5/5 sur 4 seeds, échelle `k = 0/1/2` → 3/4/5 natif == port.
- ~~**`HazeOfCorruption_DamageTransfer` (1077) : la charge utile, puis son flux RNG**~~ — **CLOS en
  deux temps.** Le DÉGÂT d'abord (`case-209-haze-of-corruption-damage-transfer.md`, bit-exact 6/6),
  puis le FLUX RNG (`case-haze-rng-flow.md`) : l'écart résiduel « natif 8 / port 6 » recouvrait
  **quatre** défauts, dont deux se compensaient en nombre mais pas en position — gate de
  `On(DamageDealt = 0x10)` lu comme celui de `On(0xf)` (le natif ne teste QUE `local_7e8 == 0`,
  c.-à-d. le dégât **DEMANDÉ** ≥ 1, donc il émet sur un cadavre), résolve slot-8 manquant sur la
  branche reduce-then-roll, `IsFirstHitInSeries` posé à VRAI sur chaque transfert alors que les N
  feuilles partagent UNE série, et `LeftOverDamage` de montant **0** filtrée alors qu'`AddLeftoverHit`
  n'a aucun gate de montant. Après correctif : **natif == port sur 5 régimes × 2 seeds**, avec un
  témoin indépendant du compte (la pose de `Contaminated`, prédite par la résolution du flux en
  `NextBool[1,99]`, concorde live == port **19/19**, bornes 25/26 exercées des deux côtés).

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

- ~~**`ChildComponent.ParentId` non publié par les RPC**~~ — **CODE LIVRÉ (#378), EN ATTENTE DE
  FENÊTRE** : `case-378-parent-link.md`. `combatSnapshot.units[]` porte désormais `parentId` +
  `parentMeasured` (lecteur UNIQUE `readParentLink`, partagé avec `decisionView`), et le port le
  consomme sur les DEUX faces (`snapshot._load_unit_parent`, `Scene.parent_by_id` →
  `normal_attack`) plus le gate `IsFriendlyKell`, qui LIT au lieu de dériver de la config. Deux
  faits **mesurés en passant, qui ne dépendaient pas de la fenêtre** : (a) l'ancrage hérité de #372
  (« `ParentComponent` id @+0x10 ») désignait l'AUTRE bout du lien — `ParentComponent+0x10` est
  `ChildrenIds`, une `List` ; (b) `ParentId == 0` vaut « pas de parent » et doit être normalisé —
  `MatchComponent$$NextId` pré-incrémente un champ zéroé, donc le premier id est `1` et `0` n'est
  jamais une entité (`dumpEntityComponents(0)` → `entity 0 not found`). Le hook courant publiait ce
  `0` brut. **Reste** : la fenêtre de reinject — `probe_378_parent_link.py` rend `NON CONFRONTÉ`
  (rc 7) en la nommant, et s'inversera seul. `[opus]`.

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
        `turn_defeated`, écrit depuis le même compteur ⇒ invariant par décalage. Le seed du compteur
        **PER-UNITÉ**, lui, est **FAIT** (`case-234-load-state-turns-finished.md`, résidu N11 fermé) :
        `+0x5c` n'est pas un `StatType`, donc le capteur INVOQUE
        `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished` et `_load_unit_turn_state` pose la
        valeur en tri-état. Mesure live 2 (seed, board) : à l'âge 1 du grot, port `load_state` seul
        **1/1** et **2/2** tirages (dont une réplique réellement spawnée sur `C4_09`/31337), là où
        l'état non seedé rendait **0** — verdict de gate opposé.
    - **Feuilles `Tile(7)` gatées sur l'unité, dans le tri de placement** — **RÉSOLU pour les
      call-sites dont `dc.units` est le CASTER** (`case-165b-tile7-unit-gated-leaf.md`) : le
      sélecteur est lu dans `SortTilesByUtilitySelector$$Select` (`dc.units = this.units.Select(…)`,
      posé à `UtilityMovementCase+0x10` par la surcharge « tile » du ctor), le foyer prend un
      `unit_id` et `runner_tile_leaf_ctx` en dérive le `ctx`. C'est ce terme
      (`GeminaeSuperiaPlaybook` = `10 × |CanAddUnit(AdjacentTiles(tuile))|`) qui fermait le résidu
      #165 §4. ~~Reste ouvert le seul call-site SUMMON~~ — **FAIT
      (`case-205-summon-sort-tiles-unit-null.md`)**, et la question posée n'était pas la bonne : le
      `dc.unit` de `SortTilesByUtilityForSummon` n'est **pas** une collection, il vaut **`null`**
      (`UtilityMovementCase$$get_IsSpawning` = `unit == null && parent != null`,
      `$$get_UnitOrParent` = `unit ?? parent`). Chaque feuille a sa dégradation NOMMÉE — 0 pour
      `TriggeredAbilities(2)`/`DespoiledGround(28)`/`HeroLikeDoorOpening(30)`, flag summon
      (`IsSpawning` inliné) pour `CapturePoint(24)`/`PowerUp(26)`/`SummonDislikeDoorOpening(29)`.
      Le foyer prend un `parent_id` ; 2 montages live (MC1_67 Swamp+élévation, C4_09 DryBush)
      confirment le port et RÉFUTENT « le sujet est un représentant de l'ensemble ». Ce qui reste,
      plus étroit :
      - les trois feuilles à `IsSpawning` sont JUSTES mais **dormantes** dans ce foyer (le `meta` du
        tri ne porte ni `is_territory`, ni `occupant_is_powerup`, ni `door` ; 0 tuile territoire sur
        les seeds arène) ;
      - `H_PARENT` n'est réfuté qu'au **décompilé** : aucun summoner du pool ne porte un passif
        enregistré dans `TRIGGERED_MOVE_PLAYBOOKS`, donc le live ne peut pas le séparer de `H_NULL` ;
      - `TileDistance(33)` sur `dc.parent` (branche `else if (c.owner != null)`) non portée : aucun
        call-site SUMMON ne passe `0x20 = MovementSuggestion` ;
      - `SteppableUnit(19)` en spawn : le natif passe `case.unit = null` à `UnitExtensions$$IsEnemy`
        sans garde ; valeur non tranchée, feuille muette des deux côtés.
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
- ~~**Resolve slot-8 non matérialisé dans `execute_normal_like`**~~ — **CLOS**
  (`case-haze-rng-flow.md` §2.2). `damage_hits.py::_one_hit`, branche `post_roll is None`, appelle
  désormais `next_internal(min, max+1)` **sans gate largeur-1** (mirror du slot 8
  `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage`, décompilé relu : son
  corps ne teste que le PRNG) au lieu d'`IdunBattle.Core.HitDamage$$GetDamage`, qui porte bien un
  `if (min == max) return min;` — mais qui est l'AUTRE étage (le jet dans les bornes BRUTES) et
  l'autre famille. Le gate est `is_attack_damage_op` = la **FAMILLE de factory**, comme l'exigeait
  la note : `AbilityDamageOperation$$ExecuteHits` appelle `HitDamage$$GetDamage` **directement**
  (xref) et garde son court-circuit → Stormcaller intact. **NO-OP dès que la cellule est large.**
  Contre-épreuve jouée dans les DEUX sens sur le montage d'origine
  (`probe_130_pick_randomly_one_rng.py`, splash Psyker) : ancien code `k=1 → live 3 / port 2` et
  `k=2 → live 3 / port 2` (le delta 1 annoncé) ; nouveau code **delta 0 aux trois régimes**, soit
  l'« attendu » que le probe imprimait sans l'atteindre.
- **Résidus NEUFS engendrés par la vague du 2026-07-26 (#67b / #224 / #127 / EnvFireTile)** — nommés
  dans les case docs, absents d'ici jusque-là. Détail, porteurs et fichiers :
  `port-residuals-inventory.md` §4 (N1-N6).
  - **N1** ciblage d'`ArcaneShield` sur un allié NON-Chaos (écart port/natif, `case-67` §6.5) `[opus]` ;
  - **N2** famille ATTACK en **bounds-mode** : cap SCALAIRE vs cap sur les CELLULES — le fix #67b est
    gaté sur `is_attack_damage_op`, cette face n'a pas été confrontée (`case-67` §6.5) `[opus]` ;
  - **N3** ordre réduction × bouclier sur `execute_normal_like` — indiscernable à `spread_pct = 0`,
    donc jamais mesuré (`case-67` §6.5) `[opus]` ;
  - ~~**N4**~~ **RÉSOLU (#208, 2026-07-28)** — il n'y a **jamais eu de refus** : le natif POSE
    `Pinned` sur un porteur `TerminatorArmour` et le laisse INERTE
    (`PinnedEffect$$CreateActiveCondition`, évaluée par `RefreshEffectsOperation$$ShouldBeActive`).
    Le collapse dans `entity_is_immune_to_effect` est DÉFAIT et le `unit_state` des
    `CreateActiveCondition` a désormais un constructeur UNIQUE
    (`runner.components.unit_state_for_effects` / `Scene.unit_state`).
    Cf. `case-224-effect-immunity-gate` §4/§5 ;
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
  - ~~**RÉSIDU `[fable]`**~~ **CLOS (#208, 2026-07-28)** : `TerminatorArmour` ne fait PAS échouer la
    pose de `Pinned` — la prémisse était fausse. `AddEffectOperation$$Execute` aboutit (retour non
    nul, mesuré #151), `EntityIsImmuneToEffect` y rend `false`, et le canal
    `decisionView { includeInactive: true }` publie l'effet 1065 avec `active: false`. La lecture
    « refus » venait d'une inférence : un effet INACTIF n'applique rien, donc n'émet aucun groupe
    d'événement, donc « pas de groupe » ne distingue pas « pas posé » de « posé et inerte ».
    Fix livré : collapse défait, `CreateActiveCondition` évaluée à la lecture avec un `unit_state`
    COMPLET (foyer unique). Cf. case-224 §4/§5.
  - ~~**RÉSIDU `[opus]`**~~ **CLOS** : chaîne `&` derrière un `AddEffect` REFUSÉ — elle **NE TOMBE
    PAS** (décompilé + live). Le confond est levé en DÉPLOYANT le camp joueur au contact : `Pinned`
    refusé ET override d'Attack + attaque libre exécutés (10038 → 7442 HP). Le port était conforme,
    le commentaire d'`operations/effects.py` était faux. Cf. `case-n5-chain-after-refused-addeffect.md`.
- ~~**`decisionView.effects` cache les effets INACTIFS**~~ **CLOS** — l'outil existe depuis `d9d0008`
  et n'avait jamais été utilisé : `decisionView { includeInactive: true }` publie les effets
  posés-mais-inactifs AVEC leur flag `active` (`readEffectsByUnit`, `frida/hooks/game/effects.ts`).
  C'est ce canal qui a tranché #208 (`probe_208_pinned_inactive.py`) — l'absence dans le canal par
  DÉFAUT n'est plus ambiguë : on lit les deux canaux et on les compare. **Rien à rebuilder.**
  Règle qui en découle : côté port, `by_unit` ≙ canal `includeInactive`, `active_effects` ≙ canal par
  défaut — comparer un port à `decisionView` par défaut, c'est comparer à `active_effects`.
  - ~~**`load_state` ne seede pas les effets INACTIFS**~~ **CLOS (#219, 2026-07-29)** —
    `snapshot.decision_view_seed_body(rid, …)` est la porte NOMMÉE du canal (à passer au RPC
    `decisionView` quand la capture alimente `load_state`), et `EffectFactory.create` lit désormais
    la clé `active` du capté (absente → `True` : canal par défaut ET pose offline). La vue NOMS
    (`EffectsOwnedComponent`, `_effect_names`) reste active-only → le choix du canal ne déplace
    aucun `diff`. **Coût du canal MESURÉ** : +909 o / +3,84 % / +6 entrées d'effet à t0 sur un 5v5,
    +435 o / +2,33 % / +3 après un tour d'IA — négligeable en VOLUME. Ce n'est donc pas le volume
    qui interdit un défaut global mais (i) la perte du canal actif-only comme référence lisible et
    (ii) le rayon de souffle des owner-effects passifs ajoutés à `by_unit` de toute bataille seedée
    (`Overwatch_AutoAttack` ×3, `GrimRetribution_CounterAttack`,
    `CalibaniteGreatswordStrike_Overwatching`, `PlasmaCannon_Visual`). D'où une PORTE explicite,
    pas un flag global. Détail + validation : `case-224-effect-immunity-gate.md` §7.
    - ~~**RÉSIDU `[opus]` : inventorier les effectTypes de `EFFECT_TRIGGERS` dont le `matches` lit
      réellement `e.active`**~~ **FAIT** (`case-229-effect-triggers-active-inventory.md`, re-dérivable
      par `probe_229_effect_triggers_active.py`). Le registre porte **15 clés / 28 classes**, et le
      critère n'est pas uniforme : `EvaluateEffectTriggerTargets` gate sur
      `EffectComponent.IsActive @+0x5c`, `EvaluateEffectTriggerEffectAbilities` n'y accède JAMAIS —
      gater le second rail (17 triggers) éteindrait les `ActivateEffect` qui rallument.
      - **1077 `HazeOfCorruption_DamageTransfer` — CLOS (#231)**, gate posé dans le `matches` du rail
        TARGETS (`case-231-haze-transfer-active-gate.md`). La même fiche **RÉFUTE** le rayon de
        souffle annoncé par #229 §3 : mesuré live, le bond 1077 n'est publié par `readEffectsByUnit`
        **ni** au canal par défaut **ni** sous `includeInactive` — il est HORS canal de seed, donc
        une bascule globale ne peut pas le seeder inerte. RÉSIDU NOMMÉ : pourquoi le bond échappe-t-il
        au canal (non inscrit dans `EffectsOwnedComponent.ActiveEffectIds`, ou non décodé par
        `indexEffects`) ? Trancher demande un hook `frida/hooks/game/effects.ts`.
      - **1197 `MasterOfTheTutelaries` — CLOS (#231)**, mais **PAS « sur le modèle de 1077 »** : il est
        du rail `ApplyInternal`/`RevertInternal`, où l'arbre passe `onlyActive=**0**` (il ne teste QUE
        la présence) et où l'activité mord via `DeactivateEffect` → `UpdateEffectTargets(cibles vides)`
        → `Revert` → `RemoveTriggeredAbility`. Transposer le remède TARGETS y aurait produit un gate
        au mauvais niveau. Même constat de canal que 1077, mesuré indépendamment : 1197 n'est publié
        **ni** par défaut **ni** sous `includeInactive`, alors même que la chaîne fire (4 Screamers) —
        le gate y est donc INERTE, cliquet de fidélité et non correction de nombre (`case-231` §4).
      - **1201 `AnvilShield_FrozenAttackerAdvantage` — CLOS (#231)**, rail TARGETS, gate
        `_frozen_advantage_flag_is_set` (`triggers/loki/anvil_shield.py`), même modèle que 1009.
        Détail : `case-231-effect-1201-active-gate.md`.
      - **1502 `RitesOfMorkai` — CLOS (2026-07-29)**, gate posé dans le `matches` de la seule classe
        1502 (`case-229-1502-rites-of-morkai-active-gate.md`). Apports de RE au-delà du gate : les
        DEUX lectures de `+0x5c` sont **désambiguïsées** (la 1re, sur le composant reçu, est un
        fast-path « actif mais 0 cible → return » qu'un effet INACTIF traverse ; **la 2e, par cible,
        sur le composant RE-FETCH depuis l'entité-effet, est LE gate** — et les deux portent sur
        l'effet SOURCE, jamais sur la cible), et
        `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` est **décompilé** (résidu
        #229 §5 / #231 comblé : `activation 1 → true`, `2 → false`, `0 → (drapeau +0x5e) puis
        virtuel 0xc sinon `IsActive` inchangé, sinon virtuel 0xb`).
        ⚠ **La fiche a d'abord conclu « porteur hors pool donc rayon de souffle non mesurable » —
        c'est FAUX, et corrigé par MESURE le 2026-07-29**
        (`case-229-1502-rites-of-morkai-live-confrontation.md`,
        `probe_1502_rites_of_morkai_live.py`) : `catalog_inject.write_augmented_seed_bc` fait entrer
        `spaceWolfPriest` au pool (97 → 98), Baldr se déploie, `RitesOfMorkai` (1211) **caste**, et
        `readEffectsByUnit` publie **3 instances 1502** (`active: true`) au canal par défaut ET sous
        `includeInactive` ; `load_state` les matérialise ; le revive natif d'une unité inspirée tuée
        sans overkill est en **AGRÉMENT** avec le port (`Min(GetReviveHP, StatAmount(Health,max))`
        saturé au hp_max). Le 3e montage (C3_01/999, `worldKharn`) a exercé l'**overkill en LIVE**
        (`Unit_WasOverkilled: 1` → pas de revive), en accord lui aussi.
        **RÉSIDU FERMÉ au passage** : l'écrivain de `EffectComponent+0x5e` est
        `IdunBattle.Operations.RemoveEffectOperation$$Execute` — il pose `+0x5c = 0` et `+0x5f = 1`
        (Removed) dans la MÊME opération, or le canal filtre `removed` inconditionnellement.
        Combiné au fait que le `CreateActiveCondition` de 1502 (slot vtable `+0x518`, **lu LIVE**,
        la classe étant désormais initialisée) est le trigger CONSTANT vrai du `DSLFactory` `+0xf8`
        — donc `RefreshEffectsOperation$$ShouldBeActive` rend toujours vrai —, **aucun vecteur de
        jeu ne peut rendre une instance 1502 inerte** : mesuré, elle passe de `active=true` à
        ABSENTE en un tour. Le gate est donc un **cliquet de FIDÉLITÉ**, jamais une correction de
        nombre. Effet de bord utile : la vtable de `RitesOfMorkaiEffect` se lit maintenant LIVE, ce
        qui confirme par une 2e source `revive_on_overkill = False` (`32 c0 c3`) et `heal_type = 0`
        (`33 c0 c3`), et écarte un piège — `ABondEffect$$CreateHandleTriggerAbilitiesInternal` lit
        les MÊMES slots `+0x728/+0x738/+0x748` avec une tout autre sémantique.
      - **1547 `ReanimationBeam_Revive` — CLOS** (`case-1547-reanimation-beam-active-gate.md`), le
        **jumeau strict de 1502** (même base `ReviveEffect`, même rail, même patron), traité en
        parallèle par une tâche distincte. Gate posé dans le `matches` de
        `ReanimationBeamReviveTrigger` — **sur la CLASSE, pas sur la base `ReviveEffectTrigger`**,
        exactement comme 1502 : c'est ce choix symétrique qui a permis aux deux de lander sans se
        marcher dessus. Même désambiguïsation des deux lectures de `+0x5c`, établie
        **indépendamment** et concordante. Validation : garde live +
        `probe_1547_reanimation_beam_active_gate.py` (3 boards × 3 seeds × 3 rosters, chemin de
        mort RÉEL via la file de morts, beam à 9–11 hex de la victime — le flag seul renverse
        l'issue, 3/3, 0 overkill).
        ⚠ **La fiche a d'abord conclu « porteur non confrontable » — c'est FAUX, et corrigé par
        MESURE** (`probe_1547_carrier_live.py`, écrit après `ca6f5dc`) : `catalog_inject.py`
        injecte `necroReanimator` (`Units` 175→176, +2 configs d'ability), la pool passe de **8 à
        9 MoW**, la MoW **se déploie** (`decisionView.mows`, pas `.units`) et **ses abilities
        CASTENT** — `1224 NanoscarabRepairProtocols` mute réellement (allié 9537→12196 PV, effets
        1545/1546 posés et relus). Tombe avec : l'affirmation #79 « les abilities d'une MoW
        hors-plateau sont bloquées par le harnais headless ». **RÉSIDU NOMMÉ, remplaçant
        l'ancien** : `1223 ReanimationBeam` a `ammoCost = 1` / `hasAmmo = false` — la jauge de
        munitions d'une MoW ne monte pas dans un runner, donc le cast est ACCEPTÉ mais **no-ope**
        (`mutated = false`) et aucune instance 1547 NATIVE n'existe. Débloquer la jauge rendrait
        mesurables à la fois la pose native et la ligne « rayon de souffle » de #229 §3. Second
        résidu observé au passage : `mows[].effects` est **vide** aux deux canaux, même après un
        cast qui a muté.
      - **RÉSIDU `[opus]`** — **1186** `GhostEffectRevive` est le SEUL écart restant : réel (rail
        TARGETS sans lecture du flag), mais porteur TUILE, donc **inatteignable par la bascule**
        (`tileMeta` appelle `readEffectsByTile` SANS options). Côté canal UNITÉ, les cinq écarts
        (1077, 1197, 1201, 1502, 1547) sont résorbés. ⚠ Chacun exigeait sa propre mesure du rayon
        de souffle, et le score des lignes « OUI » de #229 §3 confrontées est de **3 sur 6** : deux
        RÉFUTÉES par mesure (1077, 1197), **une CONFIRMÉE par mesure (1502 — l'effet EST publié,
        mais il n'a aucun état inerte à publier)**, une encore NON MESURÉE (1547, jauge de munitions
        de la MoW). ⚠⚠ Et **« absent du seed BC » n'est JAMAIS « non confrontable »** : les deux
        fiches qui l'avaient écrit (1502 et 1547) ont été démenties par `catalog_inject.py`.
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
- ~~**`UnitFlag.ArrivedAtFinalTile` (1) non posé par `MoveUnitOperation`**~~ — **PÉRIMÉ** (vérifié au
  code) : le port POSE le flag sur le chemin de move, dans `arrived_at_final_tile_triggers`
  (`runner/operations/triggers/dispatch/move_death.py`), appelée en queue d'`after_move_triggers` ;
  elle porte aussi le gate d'émission de l'event `On(0x1c)`, et `SpiritualLeader`/`ArcaneShield` en
  dépendent. Le site diffère du natif (dispatcher after-move au lieu de l'inline de
  `MoveUnitOperation$$Execute`), choix documenté sur place. Cf. `port-residuals-inventory` §5 (R21).
- ~~**Les `UnitFlags` ne sont exposés par AUCUN RPC**~~ — **PÉRIMÉ** : `combatSnapshot` publie
  `units[].unitFlags` (ids `UnitFlag` posés, lus en invoquant
  `IdunBattle.Entities.UnitExtensions$$HasFlag` une fois par valeur d'enum ; `null` = non mesuré,
  `[]` = mesuré sans flag) **plus** `unitFlagTypes` (mapping nom -> id lu au RUNTIME), sur les lignes
  `Unit` ET `Machine` ; `snapshot._load_unit_flags` les seede depuis `load_state`. Un état rechargé
  sait donc qu'une unité a bougé sans pose manuelle. Cf. `case-101 §6` et `case-o10-volk-moved-flag`.
  **Reste ouvert, et c'est un CÂBLAGE Python, plus un gap d'outillage** : la face PRÉDICTION lit
  encore le proxy positionnel `attack_pos != scene.pos(caster)` au lieu du flag (×1,25
  `HeavyWeapon_ExtraDmg` de trop sur tout caster ranged déjà déplacé, mesuré `case-61 §6`). `[opus]`.
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
  `case-217-thequickening` §7. **R31 FERMÉ (2026-07-31, `case-348-ai-approach`)** : `move_amount is
  None` ouvre désormais la plage de déplacement (`GenerateActionTiles(unit, true, null)`), le
  `MovementActionGenerator` est en queue quand `allowMoveAction`, et le `MoveUnitMessage` est APPLIQUÉ
  avant l'attaque. Confronté live sur 4 régimes (`ForwardSpotter` 1143) : approche+attaque, repli sur
  place, repositionnement au contact, déplacement pur — tuile et dégât identiques au natif
  (ex. spawn 15 → 35, −9667 des deux côtés).
- **Trait `Unstoppable` (1042), exemption movement-stop** (`case-205` — RE complet, verdict
  invalidable) : trait = membre de `NotBlockingMovementOfTraits @18155b370` {Mounted, Vehicle,
  Unstoppable} consommé par le WalkPathfinder pour les effets de tuile movement-ending
  (Fire/Ice/BlockEntering). À câbler **dans la tranche movement-stop #131/B4** quand le fondement
  (effets de tuile dans la reachability) sera porté — sinon code registered-but-dead. `[opus]`.
  ⚠ **Le fondement l'est désormais pour le bit 0x1** (2026-07-30, `case-224-pathfinding-overreach`) :
  `tile_blocks_entering` reconnaît les **cinq** EffectTypes bloquants (`0x00/0x05/0x11/0x3a/0x5e`) et
  applique déjà `not_blocking_movement_of_traits(effect_type)` — l'exemption Mounted/Vehicle/Unstoppable
  n'est donc plus du code mort sur ce chemin. **Ce qui reste ouvert ici est le bit 0x2** (`GetEffectiveDepth`
  = `Min(1, depth)`), c'est-à-dire le volet « l'hex FINIT le mouvement », toujours sans datapoint.
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
- **#45d, résidus** (`playbook/prediction.md` §9bis — tranche CLOSE : magnitude repair sourcée de
  l'ARME + utilité ramenée à UN terme, confrontée live) :
  - **Pas 17 du scénario 909 — choix de POSITION du repair.** Les **7** utilités de paire du pas sont
    bit-exactes (`pairUtility` natif == port, dont 3 swarms), mais le natif bouge en (5,3) pour réparer
    la cible à 1330 PV manquants (`U=59.9369`) et le moteur va en (3,5) pour celle à 1046 (`47.1384`) :
    l'écart est dans le **terme de tuile du sweep de position** (classé `enumeration`), pas dans la
    chaîne repair. `[opus]` si un miss d'agreement le refait surface.
  - **Dénominateur PV d'une cible BOSS** : `RepairedAmountUtility$$GetMaxHealth` passe par
    `FUN_180002590(0xaa, …)` (constante de config) au lieu de `GetStat(Health,Maximum)`. Non lue,
    non portée. ⚠ La fiche antérieure citait `0xa9` — le build courant dit **`0xaa`**.
  - **`WeaponHighestHits` vs arme normale** : le port passe `UnitContext.normal_weapon_hits` là où le
    natif lit `WeaponHighestHits(weapon de l'ability)`. Les 5 porteurs du trait `Mechanic` ont des armes
    homogènes (`[1,1]`, `[2,2]`, `[5]`, `[4]`, `[3]`) → **indiscriminable** en l'état.
    ⚠ **Le FACTEUR, lui, est désormais MESURÉ (#299)** : `necroSpyder` (arme à **5** coups) restaure
    live `10457` = `Attack 1205 × 5` + `4432` de `FabricatorClawArray` — un port qui aurait oublié le
    `× hits` rendrait `1205`. Ce qui reste indiscriminable est la SOURCE du nombre de coups (arme de
    l'ability vs arme normale), pas la présence du facteur.
- ~~**#298 — « le rail de DÉCISION de la réparation n'est jamais atteint »**~~ — **FERMÉ le
  2026-07-30 par MESURE : le rail EXISTE et l'IA propose la réparation**
  (`docs/rl/case-298-repair-decision-rail.md`). Rail = `ActiveAbilityActionGenerator` sur
  `_comparableAbilities` : l'ability est **dérivée du trait `Mechanic`**
  (`UnitFactory$$AddDerivedAbilities` ← `StaticBattleRules.Trait$$GetActiveAbility`) et entre dans
  `ActiveAbilityComponent.Abilities` — que `…$$GetUnitAbilitiesInOrder` itère **sans** le filtre
  `IsActiveAbility` de `GetActives` (d'où `kind="granted"` dans `abilityTargets`). Le seul gate est
  d'ÉTAT : `AttackQuery$$EntityCanBeRepaired` exige `IsDamagedUnit` **et**
  `IsAffectedByHealType(entity, 1)`. Mesuré, une variable à la fois : cible à 100 % → **0**
  prédiction ; cible blessée → **1119** proposé (`admecManipulus`) ou **28** (`admecDominus`) ;
  cible blessée non mécanique → **0**. Probe `probe_298_repair_rail.py`, fixture `repair_stage`,
  tests `tests/engine/runner/test_repair_decision_rail_live.py`.
  **RÉSIDUS — les DEUX sont FERMÉS le 2026-07-30 par #299**
  (`docs/rl/case-299-repair-execution.md`) :
  * ~~**`28 Repair` DÉCIDE sans EXÉCUTER**~~ — **FERMÉ**. `IdunBattle.Operations.RepairUnitOperation$$Execute`
    porté (`engine/runner/operations/repair.py`), `RepairAbility` au registre COMBAT. Confronté live :
    `admecDominus` **+5022 natif == +5022 port**.
  * ~~**`1119 Repair_GalvanicField` absent des DEUX registres**~~ — **FERMÉ**. Au registre COMBAT avec
    son masque `0x8002` et son `AbilityAttackType.Others` (le CLIQUET, posés dans le MÊME commit) ;
    volet attaque porté sur le patron `TheQuickening`. Confronté live : `admecManipulus`
    **+5024 natif == +5024 port**.
  * **Correction d'inventaire** : `port-residuals-inventory.md` classait `28 Repair` « dormant par
    construction, hors périmètre » ; c'est faux. Corollaire de méthode : **l'absence d'un id dans
    les `abilities` du gameconfig ne prouve pas qu'il est dormant** — balayer aussi les abilities
    dérivées de traits. *(Fait : la ligne d'inventaire est barrée, et la mention
    `RepairMachineOperation` — qui **n'existe pas** dans ce build — est signalée comme supposition.)*
  * ~~**RÉSIDU NEUF ouvert par #299 (N20)** : `FabricatorClawArray`, le passif du `necroSpyder`~~ —
    **FERMÉ le 2026-07-30 par #303** (`docs/rl/case-303-fabricator-claw-array.md`). La TRIGGERED
    `On(0x1c = ArrivedAtFinalTile) & OwnerIsActor & !AmountIsZero(GetTargetSelector())` est portée en
    ARBRE DSL (doctrine #149), avec les quatre nœuds qui manquaient au vocabulaire
    (`UnitsAffectedByHealType`, `Repairable`, `UnitsWithNegativeEffects`, `PickRandomly`) et
    l'accesseur de slot `Owner`. Le port rend désormais **+10457 == natif** (il rendait 6025), et le
    **MOVE SEUL** — sans aucun cast — est mesuré isolément à **+4432 des deux côtés**. Le « DEUX
    tirages PRNG par fire » (le trigger et le behaviour ont chacun leur `PickRandomly`) est
    DISCRIMINÉ live sur un pool de 2. Résidu résiduel nommé : le fallback `UnitsWithNegativeEffects`
    rend `[]` (la CATÉGORIE d'un effet n'est pas dans le canal de seed) — biais unilatéral, atteint
    seulement si aucun allié mécanique adjacent n'est réparable.
- ~~**#278 — le canal `repair_prediction` n'a jamais été confronté à une réparation MESURÉE**~~ —
  **FERMÉ le 2026-07-30 : le canal est CONFORME sur les VALEURS, pas seulement sur la forme**
  (`docs/rl/case-278-repair-prediction-values.md`). Le décodage était livré (`33292bc4` : deux
  `int32` dans RAX, miroir de `PredictHeal`) et sa forme établie par deux sources indépendantes,
  mais ni `classFields` ni le décompilé ne disent que le hook lit le bon registre. Le `Min` de
  `IdunBattle.Entities.Components.FillUpStatComponent$$MaxFillUp` donne **deux régimes**, et il faut
  les deux (chacun seul laisse passer l'erreur symétrique) : **SATURÉ** — cible `hpMax=8032` à
  `hp=8031`, montant **5024** → `totalHeal = 1 = hpMax−hp` ; **PLATEAU** — `hp=2000` puis `1000`
  (missing 6032 puis 7032) → `totalHeal = 5024` dans les deux cas ; **EXÉCUTION NATIVE**
  (`applyAction`) → hp **1000 → 6024, delta = 5024** = la prédiction. Généralisé au second membre de
  `StaticBattleRules.ActiveAbility$$IsRegularRepair` = {28, 1119} : `admecDominus` → 28, autre
  playbook, montant **5022**, delta natif **1000 → 6022**. Garde vue ROUGE par mutation `lo`↔`hi`.
  Probe `probe_278_repair_prediction_values.py`, tests
  `tests/engine/runner/test_repair_prediction_values_live.py`.
  **RÉSIDUS NOMMÉS, hors périmètre de cette fermeture** : l'étage `Fix64(bonus+amount)*Fix64(mult)`
  est traversé mais NEUTRE sur les deux porteurs mesurés ; branches `scope==1`
  (`GetGroupUnitHealLimit`) et `IsBoss(target)` jamais empruntées ; **`PredictArmorRestore` est MORT
  dans ce build** (`method not found`, `ArmorRestorePredictionResult` disparu) ; ~~la face EXÉCUTION
  côté **Python** reste non portée (résidu #299)~~ — **#299 l'a portée le 2026-07-30**
  (`case-299-repair-execution.md`) : `RepairUnitOperation$$Execute` + les abilities 28/1119 au
  registre COMBAT, confrontées live (`+5022` et `+5024`, natif == port). Les deux autres résidus de
  cette ligne se recoupent avec ce qui y a été mesuré : l'étage `Fix64(bonus+amount)*Fix64(mult)`
  reste NEUTRE sur les porteurs mesurés (le seul bonus de réparation rencontré, `FabricatorClawArray`,
  ne passe PAS par le `RepairModifier` mais par une TRIGGERED distincte, cf. N20), et les branches
  `scope==1` / `IsBoss(target)` restent inempruntées (`ForRepair` pose `scope = 0` ; `IsBoss` lit
  `UnitComponent+0x88`, hors substrat).
- **#276-r1 — décodeur hooks `decodeRepairDict` (CONFIRMÉ par lecture, exige un reinject)** ⚠ **canal
  DISTINCT de celui que #278 vient de fermer** — `ai-step/playbook-predict.ts`, pas
  `ai-trace/predictions.ts` ; l'un n'a pas corrigé l'autre : il lit
  **16 octets** d'une struct qui en fait **8**. `DamagePrediction$$PredictRepair` rend
  `CONCAT44(fill, currentHealth)` et `UtilityAttackCase$$ForRepairPrediction` stocke la valeur ENTIÈRE
  dans le pointer-size écrit à `case+0xdc`. Donc, dans `playbook-predict.ts` : `targetHpBefore`(+0x00)
  = `currentHealth` ✅ ; `targetArmorBefore`(+0x04) = en réalité le **`fillUp`** ; `hpFill`(+0x08) et
  `armorFill`(+0x0c) sont **hors struct**. Effet mesuré côté Python : l'étage UTILITÉ
  d'`engine_agreement_stages` (nourri par ce décodeur) rend `off=0.0` sur la famille repair alors que
  le générateur, qui calcule offline, est exact — d'où 2 miss classés `non-attack-oracle` qui sont des
  artefacts du décodeur, pas du port.
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
- **`CalculateCustomUtility`, 5 overrides non portés** (`case-27` — inventaire RE-DÉRIVÉ au slot de
  vtable, **BORNÉ depuis #218** : **27 corps ET 27 classes** (le « 28e », `AmuletOfTheVoidwyrmPlaybook`
  cru partageant le corps de `PlasmaGrenadePlaybook`, était un faux positif de lecture hors-vtable —
  `case-218-amulet-voidwyrm-custom-utility.md`) ; **13 portés** —
  1014/1177/1020/1029/1199/1230/1227/1226/1185/1212/1100/**1051** dans `loki_custom.py`, plus 1119
  hors module). Verrous restants — **1142** (1169, 1148, 1098 et 1053 sont sortis) :
  ~~**(1)** MoW non modélisées comme unités de DÉCISION (1169/1148/1142)~~ — **RÉFUTÉ pour 1169 et
  1148 (#302)** : le verrou n'était pas le PORTEUR (la greffe le lève, le natif charge le playbook
  PAR ABILITY) mais le **domaine de cible TUILE**, plus un **cooldown initial non purgé** qui se
  lisait comme un refus du natif. Les deux sont **PORTÉS et confrontés live**
  (`case-302` §6 et §8). Reste 1142, dont la face DÉCISION n'a toujours pas été confrontée ;
  ~~**(2)** `GenerateMultiHitAttackPredictions` sur un sous-set de cibles~~ — **LEVÉ (#27-4f)** :
  le sous-set est l'arbre DSL `AdjacentUnits(Target)` **déjà porté par la face COMBAT**, filtré par un
  `IsFriend` IMPÉRATIF, et chaque membre produit une prédiction sur la **CIBLE PRINCIPALE** (4ᵉ arg du
  `GenerateMultiHitAttackPredictions` lu à l'assembleur ; confirmé live : +8.0282 sur la paire de la
  cible, contre 0.5504 si l'event portait sur le voisin). **1051 est PORTÉ et validé live** (7 bras,
  linéarité prouvée par bras déséquilibrés, deux contre-épreuves). Restent, avec leur verrou PROPRE :
  **1142** (même playbook, porteur MoW → verrou 1) et **1098** (playbook distinct, summon SANS
  invocateur → greffe possible, non faite) ;
  **(3)** évaluateur manquant : composite `UtilityAttackCase.Base` pour 1004
  (~~`TilesInTriangleShape` pour 1148~~ — **LEVÉ (#302-3)** : l'évaluateur était DÉJÀ porté par la
  face COMBAT #90 ; ce qui manquait était la route tuile, plus la vraie source de
  `IsPositionMachineForCurrentPlayer` — le groupe de spawn du PLATEAU, pas une MoW déployée) ;
  ~~**(4)** route de ciblage ALLIÉ pour 1100~~ — **LEVÉ (#27-4e)** ;
  ~~**(5)** *(neuf, #27-4f)* les SUMMONS n'obtiennent jamais d'activation dans le harnais arène~~ —
  **TRANCHÉ (#291), ce n'était PAS un verrou de harnais mais le COMPORTEMENT NATIF**
  (`case-291-summon-activation.md`) : `SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` appelle
  `FinishUnitTurn(spawned, isTerminated: true)` (slot 0x23) sur toute unité qui apparaît pendant le
  tour de son propriétaire — sauf traits `Steppable`(27)/`Hero`(16) — et
  `FinishUnitTurnOperation$$Execute` enchaîne sur `MarkUnitAsNoActionAvailable` (slot 0x76), donc
  `HasActionLeft` = faux et `toActivate` (qui filtre exactement dessus) l'exclut. Le
  `FinishUnitTurnMessage` d'`aiDryRunAllUnits` est la réponse CORRECTE du natif. **La greffe n'est
  plus nécessaire pour la face COMBAT** : le summon agit avec SES stats par
  (a) le nœud DSL `PerformAIAction` de l'ability du summoner (events du cast — mesuré : les 2
  `orksOrkBoys` se déplacent de 4 tuiles et jouent `Stikkbomb`/attaque normale DANS le cast) et
  (b) `PlayAutomaticUnits` au turn-start suivant (mesuré : déplacement + 2623 PV infligés sans
  aucune action du joueur). Port livré + gardes ; RÉSIDU restant, plus étroit : l'oracle de
  **DÉCISION** per-unité d'un summon, qui demande un `aiDryRunAllUnits({resetTurnFlags:true})`
  (point d'ancrage nommé, `case-291` §5.5 — non implémenté : exige une réinjection Frida). Ce
  résidu est le seul qui reste devant **1098**. `[opus]`.
  ~~Verrou « routes d'ability non-attaque »~~ — **LEVÉ (#27-4b)** : `engine/playbook/nonattack.py`
  (mirror de `ComparablePlaybook<T>$$CalculateActionUtility` — le custom entre dans l'argument de
  `ShouldExecute`, dont le corps par DÉFAUT rend `true`, mesuré au slot de vtable `+0x328` sur 4
  playbooks). Premier membre validé live : **Chronometron (1226)**, A/B 4 bras, linéarité prouvée,
  route et terme montrés NÉCESSAIRES, ancrage entité vs tuile tranché par le natif. Restent derrière
  cette route, chacun avec son verrou PROPRE : ~~**1185**~~ (**PORTÉ #27-4c**),
  ~~**1212**~~ (**PORTÉ #27-4d**), ~~**1100**~~ (**PORTÉ #27-4e**, route ALLIÉE),
  **1053** (plus de corps propre sur ce build : partage `ALoki_NormalAttackPlaybook` = 1, item vide).
  Le verrou « porteur hors `--list-pool` » **n'existe plus** (`catalog_inject.py`). Chaque item nomme
  son débloqueur exact dans `case-27`. `[opus]` : porter UN sous-système débloque son groupe. Biais
  visible seulement en concurrence serrée d'actions du porteur → promouvoir si un miss le fait surface.
- ~~**Action FANTÔME `SorcerousFacade` (1100) sur cible ENNEMIE**~~ — **LIVRÉ (#217)**,
  `case-217-phantom-action-routing.md`. Le masque du `SorcerousFacadeAbility$$.ctor` (`0x402` =
  `TargetIsFriendly | TargetMatchesDynamicRule`) est RE-lu et VETO la route ennemie ; mesure
  avant/après dans le même état : `plans[1100]` `[(1100,79),(1100,81)]` → `[]`, exécution forcée
  `generic_attack` → `noop`. La couture LIVE, elle, était **déjà propre** (`attackPlans` porte ces
  évals à `rankCount = 0`, que `_best_attack` saute) — les termes ±45 de #27 tranche 3 venaient d'un
  probe qui n'avait pas filtré `rankCount`.
- **Divergence de DOMAINE : 7 abilities TILE-targeting routées vers des UNITÉS ennemies**
  (`case-217` §5) — 1017 FragBomb, 1026 BasiliskBarrage, 1116 RadBombardment, 1159
  MacroPlasmaIncinerator, 1188 DevastatingRefrain, 1201 SquigMine, 1213 DeathOnTheWind. Le natif
  énumère des TUILES (`TargetingQuery$$GetPossibleTargetsForOptions` → `GetTilesInRange` sous
  `get_IsTileTargeting`), `_ability_kind` rend `enemy`. Non corrigé délibérément : les playbooks NC
  déjà portés (`dark_talon_strike`, `heroic_fusillade`, …) consomment `ability_targets` sous la forme
  « unités ennemies » → bascule à faire **playbook par playbook**. `[opus]`.
- **Masques `TargetingOptions` non RE-lus : 15 ctors restants** (`case-217` §4) — MoW (1142, 1147,
  1148, 1160, 1161, 1168, 1169, 1209), boss NPC (1215, 1216, 1217), plus 1064 `Loki_SwoopingHawk` et
  1091 `SlashingDive` (corps délégué à `DiveAttackAbilityBase$$.ctor`). 42 des 57 ont été relus en
  #217, aucun `TargetIsFriendly`/`TargetIsCaster` supplémentaire. Recette (table des presets du
  `TargetingOptions$$.cctor`) dans `case-217` §4. `[opus]`, mécanique.
- **Sous-génération : 11 abilities à masque `TargetIsEnemy` jamais routées** (`case-217` §5) — pas de
  `constants.damageProfile`, donc invisibles de `_best_attack`. Le veto #217 est soustractif par
  construction ; les promouvoir demande de savoir leur produire une utilité. `[opus]`, à instruire.
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
  **`savage_echoes` : LEVÉ par #226** — le seed BC injecté porte désormais ses configs d'ability, le cast live
  passe et `len(live_hits) == nrOfHits` est asserté.

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

---

## Fiches PERIMEES ou REFUTEES — NE PAS re-dispatcher

Verdicts etablis par re-derivation depuis le code, **sans commit de fix associe** : leur seule trace
durable est ici. Chacun porte sa methode de re-verification — les re-derivier plutot que citer cette
liste si le doute revient.

- **PlagueWind (1035) + Doombolt (1102)** — PERIMES (2026-07-28, ripgrep sur
  `engine/runner/abilities/`) : 22 et 46 occurrences, deja portes, livres par PR #161. Le grep qui
  concluait « absents » utilisait un glob PowerShell `**` **non recursif** — d'ou le faux negatif.
- **HammerOfWrath (1153) + Foehammer (1097)** — PERIMES (meme mesure) : 41 et 36 occurrences, et
  `test_hammer_of_wrath_live` existe deja.
- **DestroyTheWitch + MartialSuperiority** — PERIMES (meme mesure) :
  `entities/effects/loki/destroy_the_witch.py` (19) et `runner/operations/triggers/loki/martial_superiority.py`
  (13) existent **et sont cables au registre**.
- **« Crit sur un coup de groupe »** — PERIME *et* **REFUTE** (2026-07-28). Le constat herite disait
  « `execute_additional_hits` passe `crit_chance=0, crit_enabled=False` pour TOUS les groupes ; le
  natif fait passer ces coups par le tirage ». Or : (1) `additional_hits.py` ne contient AUCUNE de ces
  deux affectations ; (2) l'unique mise a `(0, 0, False)` est dans `damage_ops/ability.py` et elle est
  **GATEE sur `if not is_attack_damage_op`** — famille ABILITY seulement ; (3) elle mirroire le
  decompile : `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit` n'a **aucun** chemin crit (pas de `RollCritical`,
  `AttackHit` construit `isCrit=0`, `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` est 0-RNG) ; (4) elle est
  MESUREE (`probe_45f --case scrit`, Njal Stormcaller force a `--crit 100,700`) : live `crits=[0,0,0]`
  et 1 tirage/coup, contre l'offline non-gate qui brulait 1 crit-roll/coup + ajoutait un crit flat.
  **Condition de reouverture** : un contre-exemple MESURE sur la famille ATTACK, pas une relecture.

- **`MinDist#76` du pas s5 (seed 12345), volet LIVE** — PERIME (2026-07-29). La fiche annoncait
  « natif -700, port -600 sur (1,4) ». **Re-mesure au TERME** (pas seulement a l'issue du pas) par
  `probe_17_s5_mindist.py --focus-step 5` : le port LIVE rend la valeur NATIVE sur **14/14 tuiles**
  du movable set, dont **-700 sur (0,4) ET (1,4)** -- le tie natif est reproduit a l'identique, et
  son departage est **premier-gagne dans l'ordre du movable set** ((0,4) idx 10 avant (1,4) idx 11),
  pas un aleatoire. Ferme par #57l (filtre `IsTargetable` du ClosestEnemy) + #26 (les 4 predicats).
  **Methode de re-verification** : `python probe_17_s5_mindist.py --state-file <ABSOLU>.json
  --seed 12345 --board MC1_67 --steps 6 --focus-step 5` -> colonne `verdict` = `live=OK` partout ;
  garde permanente `tests/engine/test_min_distance_move_leaf_live.py` (2 couples board/seed).
  ⚠ **Ne PAS lire ce verdict comme « MinDist est bon partout »** : la face OFFLINE porte encore
  l'ecart en entier (tache `#17-off`).

> **Lecon commune aux quatre.** Trois d'entre elles ont ete dispatchees ou allaient l'etre sur un
> constat que personne n'avait re-confronte. Le registre de taches decrit des **intentions
> horodatees**, pas l'etat du code. Toute fiche se re-derive AVANT dispatch — et le grep qui sert a
> le faire doit etre `rg`, jamais un glob PowerShell `**` (non recursif, faux negatifs silencieux).


## Residus ouverts par #321 (registre host des runners)

Detail complet : `docs/rl/case-321-runner-registry-authority.md`.

- **Le correctif #321 n'est PAS VERIFIE EN VOL.** `[opus]` Il vit entierement dans `frida/host/*`,
  donc il est INACTIF tant que le host n'a pas redemarre (`npm run dev` = sources TS via `tsx`, pas
  de hot-reload). Ce qui est verifie sans redemarrage : `tsc --noEmit` exit 0, la sonde
  `probe_321_runner_registry_drift.py` rend le diagnostic complet, aucun consommateur hors du front.
  Ce qui exige la fenetre : la purge a la dispose ferme la derive, le reconciliateur converge sans
  jamais purger sur mesure absente, `DELETE /api/runners/:id` rapporte toujours `removed:true`.
  Procedure et cliquet (`--max-drift 0`) : `case-321` §6. Les ~330 entrees heritees d'avant le
  correctif ne disparaissent pas d'elles-memes au redemarrage — le reconciliateur les purge en
  <= 60 s, ou `--sync` en une fois.

- **`RUNS_DIR` ecrit sous `frida/logs/runs/`, contre la regle enoncee par `frida/host/index.ts`.**
  `[opus]` `path.resolve(process.cwd(), "logs", "runs")` avec `process.cwd() = frida/`, alors que
  l'en-tete d'`index.ts` pose « les SORTIES du host vont sous `logs/` A LA RACINE DU DEPOT, pas sous
  `frida/` » — regle ecrite apres une mesure de 3 663 Mo accumules exactement la. Etat au
  2026-07-31 : 320 repertoires / 1 147 fichiers / **455 Mo**. Corriger le chemin ORPHELINERAIT
  l'existant (plus aucun `removeRunner` ne l'atteindrait) : la tache est le chemin **plus** sa
  migration, pas le chemin seul.

## Residus ouverts par #289 (`ResurrectionOrb` 1009, face DECISION portee)

Detail complet + arbres relus : `docs/rl/case-27-custom-utility.md`, section « TRANCHE 289 ».

- **Face COMBAT de 1009 : le port date de `gqfc5mff6c` et le natif a DRIFTE.** `[opus]`
  `IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$ExecuteBehaviour` du build
  `rnca9r7q6c` fait `SortByFormula(tiles, MinDistance(It, NormalUnits(Enemies(caster))), asc)` puis
  `SortTilesByUtilityForSummon(., 7, caster)` puis `First(., GetMaxSummonsFormula(), 0)` — un choix de
  tuiles DETERMINISTE, la ou `engine/runner/abilities/necrons.py::resurrection_orb_tree` a garde le
  `PickRandomly` de l'ancien build (donc consomme le RNG et ne pose pas les summons aux memes hex).
  Et il PRECEDE le spawn d'un `$$GetResurrectBehaviour(...)` — `DSLBehaviors$$Resurrect` d'un heros
  mecanique allie mort tire par `PickRandomly(1)`, PV =
  `PercentageOf(StatAmount(cible, Health, max), variable 0x26)` — **entierement absent du port**.
  Le verdict « SUMMON PUR, aucune resurrection » de la docstring etait juste sur `gqfc5mff6c` ; il est
  corrige sur place, mais le comportement, lui, n'est pas porte. Porteur confrontable :
  `necroOverlord` (pool rank 17). Noeuds DSL manquants pour ce port : `SortTilesByUtilityForSummon`,
  `MinDistance` en domaine tuile, `Resurrect`.

- **`DSLSelectors$$CanAddUnit` : le 4e argument d'`UnobscuredEntitiesSelector` n'est pas RE.** `[opus]`
  Le natif lui passe le CASTER (`selectors+0x88 -> +0x48`) ; le port `entities/selectors/tiles.py::
  CanAddUnit` compte comme occupee la tuile de TOUTE unite vivante, sans exception. `#289` contourne
  cote decision en deplacant le caster sur la tuile candidate dans son `DslContext` (mirror du
  `casterPosition`), ce qui rend le compte juste pour ce call-site — mais tout autre consommateur
  (`SavageEchoes`, `CultDemagogue`, `Spawn`) herite de l'approximation. Lire
  `IdunBattle.Entities.Selectors.UnobscuredEntitiesSelector$$Select` et trancher.

- **Deux corrections de `$$GetMaxSummonsFormula` non confrontees LIVE.** `[opus]` Elles sont relues au
  decompile du build courant (donc fiables), mais le montage de `probe_289_resurrection_orb.py` ne les
  DISCRIMINE pas :
  * `Filter(..., IsMechanical)` au lieu de `UnitsWithTrait(LivingMetal)` — il faudrait un allie mort
    `Mechanical` **sans** `LivingMetal` ; le pool rank 17 en offre 9 (`admecMarshall`, `admecDominus`,
    `adeptMorvenn`, `orksKillaKan`, `tauCrisis`, ...). Bras a ajouter au probe existant.
  * cap `ConfigConst(maxSummons) = 5` au lieu de `Direct(6)` — il faudrait
    `Count(morts mecaniques) + TURNS_STARTED >= 6`, hors de portee d'un montage a deux tours.
