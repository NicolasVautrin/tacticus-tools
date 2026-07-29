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
| #haze-ord | ~~**Le port DRAINE la mort immédiatement, le natif l'ENQUEUE**~~ — **LIVRÉ (2026-07-29)** | `[opus]` | **CLOS — `case-haze-ord.md`.** `AttackDamageOperation._fire_death_if_killed` est désormais `IdunBattle.Operations.RecordKillOperation$$Execute` (flag `Overkilled`, `RecordDeathReason`, `On(3)`, **`_add_death`**) suivi de `_verify_deaths` = `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths`, boucle **NON RÉ-ENTRANTE** : une mort causée pendant une séquence de mort (death-nova, riposte `FinalJustice`, report 1077) est traitée APRÈS elle, jamais en son milieu. L'entrée de file transporte le **`killTrigger`** (3ᵉ argument de `MatchState$$AddDeath`), rejoué par `KillUnitOperation` dans l'`AbilityEntities+0x138` — sans lui, différer le drain aurait ré-ouvert le gate anti-chaîne de case-haze-bonded. **Second défaut, indépendant** : le **site (A)** d'`IdunBattle.Operations.ApplyDamageOperation$$Execute` (`HasFlag(target, 8)` → `AddLeftoverHit` puis **`return`**) n'était pas porté — le port émettait `On(0x10)` sur un cadavre overkillé, donc un `Maybe(25)` d'`OnToxicDamageAbility` **en trop**. Les deux ne se compensaient pas : **−3 / +1**. Résultat sur le montage de référence : **natif 14 == port 14**, dégât par unité **3/3**. GENERALISATION craftée : **9/9 bit-exacts** (3 seeds x PV 800/1200/2000), dont **4 montages à 13 tirages** où le relais meurt EN MILIEU de série (le 2ᵉ bond doit y lire **3** leftovers -- ni 4, ni 1). Rayon de souffle chiffré (dérivé du code, `probe_hazeord_blast_radius.py`) : 6 call-sites réels d'`_apply_damage_pipeline`, **83** classes de trigger, **21** consommateurs de mort, **8** dont le behaviour peut TUER (4 avec le vecteur dans le corps de classe) — hors de cette fenêtre le changement est un **no-op strict**. Gardes : `test_death_queue_ordering_live.py` (7 offline + 15 live) ; non-régression **161 tests verts** (45 Haze, 26 mort/revive/nova, 41 dégât/consommateurs, 49 revive-après-overkill) + `engine_validate` seed 31337 = **27/27** abilities, 96 % de positionnement exact (baseline). **Résidus nommés** : `uc.alive` posé à l'ENQUEUE et non au DRAIN (la machinerie `fire_on_death` du port en dépend) ; le flag `Overkilled` non posé sur les reports 2..4 ; la death-nova qui TUE n'est pas confrontée LIVE. |
| #17 | Surveillance des 2 résidus `move` | `[opus]` | Nature RNG (`generator-overfire`), non actionnable — veille seulement. ⚠ Le troisième item que cette fiche portait, le **`MinDist#76` du pas s5 (12345)**, en est SORTI le 2026-07-29 : **fermé côté LIVE** (mesuré 14/14 tuiles bit-exactes, cf. `case-52` §#17-s5 et la garde `test_min_distance_move_leaf_live.py`), et sa moitié OFFLINE, promue en tâche propre `#17-off`, est **LIVRÉE le 2026-07-29** (ligne suivante). |
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
| #BF-chance | **Chance de fuite `BattleFatigue` non sourçable offline** — bloque le dispatch de `TriggerAbility(0x401)` ET rend arbitraire le défaut de la voie trigger-sur-mort | `[opus]`+prérequis | `case-bl-1029-1020` §5.3 + `runner/operations/behaviour.py` : `BattleFatigueAbility$$GetFleeChance` = `ConditionalAmount(TargetIsOverkilled, Direct(GetNumberConstant(0x33)), Direct(GetNumberConstant(0x2a)))` sur une `AbilityConfiguration` **absente du gameconfig**. Deux défauts INCOHÉRENTS coexistent aujourd'hui : `behaviour.py` FUIT toujours (voie trigger), `TriggerAbility` ne dispatche pas (voie Herald). Prérequis = capter les 2 constantes (point d'ancrage : `AbilityConfiguration$$GetNumberConstant` sur la config 1025, ou un sweep live de fréquence de fuite) ; ensuite les DEUX voies partagent le même gate. |

## Résidus documentés (pas encore des tâches)

Remontés par les cases closes ; à promouvoir seulement si un miss d'agreement les fait surface.

- **Gisement « playbooks de MOUVEMENT » : 42 restants, dont 31 à porteur spawnable TEL QUEL**
  (`case-193c` §1 et §6, moins `CursedPlagueBell` 1071 porté par `case-211` — chiffres
  RE-DÉRIVABLES par `probe_193b_carrier_pool_crosscheck.py`, qui lit le pool en LIVE). Le rang A de
  `case-193` §5 reste la file la plus rentable (3 lignes + une entrée au registre par item) — mais
  **relire chaque `GetAdjacent*Utility` au décompilé** avant de le traiter comme un 3-lignes :
  `case-193c` §3 en distingue TROIS formes, et l'exception annoncée (`CursedPlagueBell`) a coûté une
  RE complète — deux gates, dont un qui lit le `WeaponsComponent` du voisin, et un trait qui
  n'existe dans AUCUN `traits` du gameconfig (`case-211` §1.3). Restent en tête de file
  `MedicusMinistorum` (15), `Deathwing` (10), `TaintedNarthecium`. `[opus]`.
- **`SpiritualLeader` (1275) et `ExplosiveMaladies` (1068) : clé BC EFFECTIVE non résolue**
  (`case-193c` §7). Leur structure est tranchée au décompilé (filtre `HasTrait(0x41d)` + lookup plat
  pour la 1ʳᵉ ; deux clés gatées `HasRangedWeapon` / `HasTrait(0x7ea)` pour la 2ᵈᵉ), mais **aucune clé
  de `Utilities.Default.TriggeredAbilities` ne matche leur préfixe** : soit le terme vaut 0, soit la
  clé ne suit pas la convention de nommage. Résoudre les littéraux `DAT_*` avant de conclure.
- **`darkaSmnWatcher` (porteur de `WatchedOver` 1524) : chemin d'octroi non établi** — aucune
  `units.abilities[*].constants.unitId` du gameconfig ne le cite (`case-193c` §1.2). Seul summon du
  gisement dans ce cas.

- **Identité du `ClosestEnemy` non exposée côté LIVE** — `case-236` §5/§6. Le RPC
  `pathDistToEnemies` rejoue `FindClosestEnemy` mais ne renvoie que `closestResolved` + la liste des
  candidats, pas l'id retenu. Conséquence bornée : le **gate 4** de `MinDist(16)`
  (`UnitCanBeDamaged`) est SUSPENDU quand plusieurs candidats sont **panachés** sur
  `HasTrait(Impervious)` — unanimes, le verdict est exact sans l'argmin, et le gate 4 est de toute
  façon *registered-but-dead* dans notre régime (§4). Point d'ancrage : renvoyer l'`id` du
  `closestTile` dans `ctx.rpc.pathDistToEnemies` (`frida/hooks/features/ai-step/rpc-board.ts`) —
  exige un reinject.
- **`noTargetableEnemies` posé mais pas encore exercé** — `case-236` §6. Le champ structuré est
  dans `rpc-board.ts` ; la session Frida en cours ayant été injectée avant, la voie ACTIVE et
  testée live reste le littéral d'erreur du même `return`. À re-confronter au prochain inject
  (`probe_236_mindist_gates.py --runner <rid>` doit rester à 0 non-conforme).
- **`GetStat(unit, CriticalChance)` non lisible sans `Scene`** — `case-236` §5. `_mindist_case`
  laisse alors `unit_crit_chance = None` -> gate 4 SUSPENDU (permissif) plutôt que `0`, qui le
  ferait mordre sur une donnée jamais lue.

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
        virtuel 0xc sinon `IsActive` inchangé, sinon virtuel 0xb`). Le porteur `spaceWolfPriest`
        étant HORS pool, le rayon de souffle n'est PAS mesurable pour 1502.
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
        de souffle, et AUCUNE des lignes « OUI » de #229 §3 confrontée n'a tenu : deux RÉFUTÉES par
        mesure (1077, 1197), deux NON MESURABLES faute de porteur spawnable (1502, 1547).
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
- **`CalculateCustomUtility`, 10 overrides non portés** (`case-27` — inventaire RE-DÉRIVÉ au slot de
  vtable en tranche 3 : **27 corps mais 28 classes**, `AmuletOfTheVoidwyrmPlaybook` partageant le corps
  de `PlasmaGrenadePlaybook` était invisible des tables ; **7 portés** dans `loki_custom.py` —
  1014/1177/1020/1029/1199/**1230**, plus 1119 hors module). Les 10 résidus tiennent à **4 verrous** :
  MoW non modélisées comme unités de DÉCISION (1169/1148/1142 — le débloqueur `case-mow-offboard-cast`
  ne lève que la face COMBAT) ; routes d'ability non-attaque (`dp=False` : 1226/1053/1185/1212, plus
  1100 dont la cible native est un ALLIÉ) ; `GenerateMultiHitAttackPredictions` sur un sous-set de
  cibles (1051/1142, 1098, AmuletOfTheVoidwyrm) ; évaluateurs manquants (composite
  `UtilityAttackCase.Base` pour 1004, `TilesInTriangleShape` pour 1148, sélecteur DSL pour 1226).
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
