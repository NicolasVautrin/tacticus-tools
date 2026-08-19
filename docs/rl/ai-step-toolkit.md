# ai-step — toolkit pilotage/observation IA par-unité + réflexion features/mouvement

État au moment du compact (2026-06-14). Objectif projet : **IL d'abord** (imiter
l'IA du jeu), **RL ensuite**. Cette session = construire le pilotage de l'IA
**par unité, SANS `CheatRunAIMessage`**, + réfléchir à l'archi des features et à
l'influence du mouvement. **TOUT est non commité.**

## Ce qui est construit — `frida/hooks/features/ai-step.ts` (nouveau, câblé dans controller.ts)

RPCs (read-only sauf `aiPlayByUnit`/`aiPlayOrdered` qui appliquent) :

- **`aiStepDryRun({runnerId, maxPump})`** — pompe 1 pas de `CalculateNextActionForPlayer`,
  lit l'action proposée, NE COMMIT PAS (`mutated=false`).
- **`aiDryRunAllUnits({runnerId, maxPump})`** — pour chaque squad contrôlé+vivant,
  l'action proposée (read-only) + `visualId`/`pos`. = « intentions parallèles ».
- **`aiPlayByUnit({runnerId, maxTurns, maxActivations, maxPump, probeEachTurn})`** —
  joue l'IA par-unité, **ordre naturel** (re-crée l'énumérateur par pas), applique
  via **`ApplyAiMessage`**, `EndTurn` entre équipes. `probeEachTurn`=dry-run-all par
  tour. Retourne `finalStage`/demos/turnProbes.
- **`aiPlayOrdered({runnerId, order:"asc"|"desc"|number[]})`** — **force l'ordre**
  d'activation via `CalculateNextActionForUnit(unit)`. = intervention étape 1.
- **`aiMovableTiles({runnerId, side:"friendly"|"enemy"|"all", dangerZone, threat, extraRange, overrideRange})`**
  — tiles atteignables (`GetMovableTilesFor`) ; `threat`=move ∪ `GetAllTilesInAbilityRange` ;
  `union` = danger zone agrégée ; `extraRange`=buff de move (OverrideRangeBonus).
- **`aiAttackRank({runnerId, unitId?, targetId?, abilityType?, allAbilities?, maxRank?, overrideRange?})`**
  — **VALIDÉ (2026-06-14)** — RANKING des positions d'attaque par (unit, ability, target)
  via **shrink-and-recall** sur `AttackQuery.GetBestTileToAttackFrom(unit, set, target, ability)` :
  argmax de l'utilité IA → `set.Remove(tile)` → re-call → 2e, etc. **Autonome** : lit
  les abilities CONCRÈTES de chaque unit (`ActiveAbilityComponent.NormalAttackType` @0x28
  + `GetActives()` si `allAbilities`) et ajoute la **tile courante** (`EntityExtensions.GetMainTile`)
  au set candidat. Read-only (`mutated=False`, `removeWorks=True`). Donne le **fallback**
  quand 2 units se disputent une tile (rank 1+). Fidélité confirmée : le rank-1 = la
  décision réelle de l'IA (u95 attaque depuis sa tile courante → rank-1 = cette tile).
- `applyAddUnitSrc` (launch.ts) — détour deep-strike (AddUnit + SpawnSource arbitraire),
  **inutile/à virer** (deep-strike n'est PAS du drafting, cf. plus bas).

Probe : `scripts/python/rl_probe_step.py` — modes `play|ordered|dryall|full|deepstrike|tiles|danger|buff|buffcond`.
Réutilise les helpers de `rl_collect_batch.py` (`buildNormalizedBC`→`initAndStart`).
**Lancer avec `python`** (psycopg3). Build prouvé : `buildNormalizedBC → initAndStart → [play]`.

## Findings RE (build kqkbjqfb6c — ghidra-mcp + data/dumps/kqkbjqfb6c/dump.cs)

- **`CalculateNextActionForPlayer(player)`** → `IEnumerator<List<IInputMessage>>` :
  yield **1 PAS** (1 liste = souvent 1 message) puis se termine. Le `d__16`
  (`CalculateAndApplyAllComputerActions`) le **re-crée à chaque pas** (`while IsPlayersTurn`).
  `PickNextUnit` (utility `_defaultUnitPickerDefinition`) choisit l'unité — **pas d'initiative**.
- Pomper `MoveNext` en boucle serrée **MARCHE** (pas bloqué, juste **lent** : ~784
  MoveNext/décision = le scoring d'utilité étalé). Pas besoin de frames ni CheatRunAIMessage.
- **Appliquer via `ApplyAiMessage`** (→ `_inputProcessor`), PAS `runner.Apply` direct —
  sinon l'action n'est pas consommée côté tour, le tour s'épuise après 1 unité.
- **Tours par ÉQUIPE complète** (A joue toutes ses units → `EndTurn` → B). États
  intra-tour = **on-distribution** pour l'IL.
- **Deep Strike = TRAIT** `UnitTrait.TeleportStrike = 2020` (PAS du drafting/réserve —
  fausse piste). `CalculateNextActionForUnit` le traite comme les autres, juste un
  `MoveUnitMessage` vers une tile **plus loin** (GetMovableTilesFor renvoie + de tiles).
- **Queries (instances sur le runner)** : `MovementQuery` @ `runner+0xF0`
  (`<MovementQuery>k__BackingField`), `AttackQuery` @ `runner+0xD0`.
  - `MovementQuery.GetMovableTilesFor(unit, ignoreUnitFlags, MovementOptions)` →
    `IOrderedSet<IEntity>` (tiles). 3-param overload (slot 4).
  - **`MovementOptions` = 0x30 octets** (pas 24 !) : IgnoreSpecialMovement@0,
    IgnoreUnitsOnTiles@1, IsDangerZone@2, OverrideRange(Nullable<int>)@4 (has@4,val@8),
    OverrideRangeBonus(Nullable<RangeBonus>)@0x10 → has@0x10, `RangeBonus.ExtraRange@0x18`,
    ExtraRangeCondition(Func)@0x20, ReduceRange(Nullable<int>)@0x28.
  - `AttackQuery.GetAllTilesInAbilityRange(unit, possibleTiles:IOrderedSet<IEntity>, includeNormalAttack)`
    → tiles menacées. **Danger zone = move ∪ ça, union sur ennemis.**
  - `AttackQuery.GetValidTargets(unit, from:UnitPosition, ability)` → cibles valides
    (rule-exact : LoS, règles de ciblage). + overload multi-positions + `GetValidTargetsInSteps` (coroutine).
  - `UnitPosition` = struct `{ Tiles:IList<IEntity> @0 }`, `MainTile` prop ; ctors
    `.ctor(IEntity tile)` / `.ctor(IList<IEntity>)` → **emballer une tile choisie = trivial**.
- **Move-range buff** (Sibyll/Makothep passifs, Warboss actif) = `OverrideRangeBonus.ExtraRange=+N`,
  **CONDITIONNEL** via `ExtraRangeCondition` (= unité adjacente au buffeur **au début du tour**).
  Validé : +N agrandit le rayon (base+N) ; modélisé conditionnel (adjacence dist≤1).
- **`UnitExtensions`** (IdunBattle.Entities) helpers statiques invocables : `HasActionLeft(unit)`,
  `IsAlive(unit,state)`, `IsControlledByCurrentPlayer(unit,state)`, `IsRanged`, `HasFlag(unit,UnitFlag)`.
  → set « à activer » = ctrl+alive+hasActionLeft (gère **kills** dynamiquement).

## Décisions de design (la réflexion)

1. **Archi features = capture compacte + dérivation OFFLINE.** Le runner est
   déterministe (seed+log) → tout état est rejouable. On ne stocke PAS les features
   par sample : on **capture compact** (seed + log de messages, déjà via
   `simDumpReplay`/bundles) et on **dérive les features hors-ligne** en rejouant +
   les RPCs read-only. 3 couches : capture / features dérivées / tenseurs IL.
   Commencer minimal (board + movable tiles de l'unité activée + le move), ajouter
   au fur et à mesure SANS re-collecter.
2. **Influence du mouvement (intervention étape 2)** :
   - **Niveau dur (RL)** : construire `MoveUnitMessage(BEntityId unitId, List<Position> feet, bool skipFlags)`
     vers une tile **choisie (légale)** + `ApplyAiMessage`. Construire la `List<Position>` :
     soit fresh (générique fermé), soit **muter le move proposé par l'IA** (mono-tile, simple).
     `skipFlags=false` si tile dans l'ensemble légal (`aiMovableTiles`). Ctor confirmé.
   - **Niveau doux** : `AiControl.ExecuteMovementFor(unit, overrideRange, overrideTileUtility)`
     — biaiser l'IA avec notre `UtilityDefinition`.
3. **Évaluer un move** : **A** (`GetValidTargets` BATCHÉ multi-positions +
   `GetBestTileToAttackFrom`) **>> B** (`GetAllTilesInAbilityRange` ∩ positions ennemies).
   A = rule-exact + fidèle à l'IA (elle utilise GetValidTargets). B = géométrique,
   **sur-compte** (ignore LoS/règles), **perd le mapping destination→cibles**. B
   seulement comme overlay coarse. Pas de loop naïf par-tile (N×M invokes) → overloads batchés.
4. **Redondance des 3 méthodes attack-range** : `GetAllTilesInNormalAttackRange` ⊂
   `GetAllTilesInAbilityRange` (sous-cas) ; `GetValidTargets` = sortie différente
   (unités vs tiles). → **2 primitives utiles** : AbilityRange (tiles/danger zone) +
   GetValidTargets (cibles/décision).
5. **« depuis position choisie » SANS bouger** : `UnitPosition(tile)` +
   `GetValidTargets`/`GetAllTilesInNormalAttackRange(unit, UnitPosition)` — read-only.
   → permet de scorer chaque destination par sa valeur offensive avant de commit.

## Carte des primitives AttackQuery (décompile confirmée — kqkbjqfb6c)

4 corps distincts décompilés via ghidra-mcp (RVAs ci-dessous, base `0x180000000`) :

| # | Méthode (RVA) | Entrée | Sortie | Usage |
|---|---------------|--------|--------|-------|
| 1 | `GetValidTargets(unit, UnitPosition, int ability)` `@1810e2430` | **1 position** | `ValidTargets` | **atomique** — score « depuis tile T ». Rule-exact : résout l'ability via `ActiveAbilityComponent`, `IsAlreadyUsedThisTurn`, dispatch `AActiveAbility.GetValidTargets` (LoS/règles de ciblage). 1 invoke. |
| 2 | `GetValidTargets(unit, IEnumerable<UnitPosition>, ability)` `@1810e22f0` | N positions | `ValidTargets` **fusionné (union)** | pilote la state-machine d__18 en boucle serrée synchrone. **Perd le mapping tile→cibles**. = « peut-il toucher qqch depuis son movable set ». 1 invoke. |
| 3 | `GetValidTargetsInSteps(…)` `@1810e1fb0` (→ `d__18.MoveNext @18110bf00`) | N positions | coroutine → ValidTargets fusionné | **CONFIRMÉ** : itère les positions **1 par 1**, appelle #1 sur chacune, `Merge` dans un accumulateur, yield `null` par pas (frame-budget), yield le ValidTargets fusionné **1× à la fin**. = #2 étalé sur frames, **même résultat**. **En dry-run #2 le remplace** (pas de pump). |
| 4 | **`GetBestTileToAttackFrom(unit, tiles, ability, nullable)`** `@1810e1660` | N tiles | **tile argmax (IEntity)** | **sous-décision mouvement de l'IA** : pour chaque tile → `UnitPosition(tile)` → `GetInvalidTargetReason`/`IsInvalid` (skip si illégale) → score `UtilityMovementCase` contre la utility-def de l'IA (`this+0x28`) → garde le **max** (score = `TimeSpan`). **Argmax interne, 1 invoke, vrais poids de l'IA.** Morceau décomposé de `CalculateNextActionForUnit`. |

`GetInvalidTargetReason` + `IBrokenTargetingRuleExtensions.IsInvalid` = primitive de validité
par-position (plus légère que #1 si on veut juste un booléen « attaquable depuis T »).

**Correction design (raffine §3)** : pour scorer **par-destination** (feature IL « valeur
de bouger en T »), la #2 est **mauvaise** (fusionne/union → perd le mapping tile→cibles).
→ soit **#1 par tile** (N invokes, garde le mapping, rule-exact), soit **#4** (argmax
direct, fidèle à l'IA, 1 invoke). #4 = candidat fort pour la dérivation features IL ET
comme probe read-only « quelle tile l'IA choisirait pour attaquer ».

## RPC Phase 3-4 (vue décision) + merge Python

- **`decisionView({runnerId, maxRank?=6, allAbilities?})`** — LA vue dynamique en UN appel
  (~240 ms, read-only) : méta + TOUTES les units (pos hex/HP/team/alive/ctrl/hasAction/ranged/
  abilities) + `toActivate` + `attackPlans` rankés (par unit×ability×target) AVEC **dmg+kill
  prédits par tile** + `dangerZone` (RPC =0 car ennemis TurnFinished → calculée en Python).
  Helpers partagés : `computeAttackPlans`, `projectUnitsFull`, `computeDangerZone`, `resolveDpq`.
- **`aiPredict({runnerId, unitId, targetId, abilityType?, col?, row?})`** — probe DamagePrediction.
- **Merge `scripts/python/oracle.py`** : `build_card(decisionView, Board(bc))` = carte hex
  (board.py) + overlay units (MAJ=moi/min=ennemi) + **danger zone géométrique** (positions
  ennemies × Movement × portée via gameconfig+hexgeo ; conservatrice, ignore LoS/obstacles) +
  kits (gameconfig) + plans dmg/kill. Probe : `rl_probe_step.py --mode card`. Outils Python :
  `hexgeo.py` (hex odd-q), `board.py` (BC→terrain), `gameconfig.py` (kits du gameconfig du jeu).

## DamagePrediction (validé 2026-06-14)

Prédiction de dégâts/kill **read-only** (« conséquences sans simulation »). Chaîne :
`runner.<Services>@0xC8 → EntityServices → <DamagePredictionQuery>@0x88`, puis
`GetAllPredictions(IEntity attacker, IEntity selectedAttackerTile, ActiveAbilityType)`
→ `IDictionary<IEntity, DamagePredictionResult>` (cibles atteignables depuis cette tile)
→ `dict.get_Item(target)` → struct boxée (lire à `boxed+0x10`).

**Offsets `DamagePredictionResult` (build kqkbjqfb6c)** — ⚠️ DIFFÈRENT du commentaire
`ai-trace/state.ts:readDamagePredictionAt` (qui dit TotalDamage@0x90 = PÉRIMÉ → garbage) :
`CurrentHealth@0 · CurrentArmor@4 · CurrentShield@8 · AccurateHealthDamage(MinMax)@0x58`
`(Min@0x60,Max@0x64) · TotalDamage(MinMax)@0x88 (Min@0x90,Max@0x94) · MightCrit@0xB1 ·`
`ForceOverkill@0xB2 · AppliedHits@0xBC`. MinMaxDamage = 16o {_cap@0, Min@8, Max@0xC}.
kill ≈ `AccurateHealthDamage.Max >= CurrentHealth`. Properties `WillBeKill`/`MightBeKill`
existent (getters, plus précis si besoin).

Validé : `aiPredict` RPC (probe) — u95→u85 depuis (3,6) = 1715-3346 dmg, pas de kill (HP 7029).
Reste : intégrer dans `computeAttackPlans` (chaque tile rankée → dmg+kill). `EntityServices`
porte aussi `<DamagePrediction>@0x50, <Attack>@0x68, <Movement>@0x60, <Targeting>@0x80,
<AIControl>@0x20` — container god-object des services.

## Modèle d'abilities (clé — découvert 2026-06-14)

**L'attaque normale n'est PAS l'abstrait `ActiveAbilityType.NormalAttack=17`.** C'est un
id **CONCRET par unité** (ex. `Loki_NormalAttack=69`, `TemplarInitiateNormalAttack=1046`,
`RogalDorn_NormalAttack=1126`…). L'abstrait
17 n'est dans le component d'**aucune** unité → `GetOrNull(component, 17)` renvoie null →
`GetBestTileToAttackFrom`/`GetValidTargets`/`GetInvalidTargetReason` rejettent toutes les
tiles → résultat vide. **Il FAUT passer l'id concret.**

`ActiveAbilityComponent` (BattleLogicAssembly, `IdunBattle.Entities.Components`) :
- champ **`NormalAttackType` @0x28** (ActiveAbilityType) = id concret de l'attaque normale.
- `Abilities` @0x20 (`ActiveAbilityKeyedCollection : KeyedCollection<ActiveAbilityType, ActiveAbility>`).
- méthodes : `GetNormalAttack()`, `GetActives() → List<ActiveAbility>`, `GetOrNull(type)`,
  `GetActive(type)`, `GetUsedAbilities()`.
- `Components.ActiveAbility.AbilityName` @0x44 = son ActiveAbilityType ; `get_CanCurrentlyBeUsed`.

→ énumérer les abilities d'une unité = lire `NormalAttackType` (+ `GetActives()` → `.AbilityName`).
**Passer l'attaque normale ne BLOQUE pas les attaques normales** — au contraire, c'est
ainsi qu'on les rank (l'attaque normale EST une ability, juste typée par unité).

`EntityExtensions.GetMainTile(IEntity entity, IMatchState state)` → tile courante (à
ajouter au set candidat ; `GetMovableTilesFor` exclut la tile d'origine). C'est exactement ce que fait
le TACTIC natif : `ABaseAiUnitTactic$$GenerateActionTiles` passe par `IBattleQuery`+0xe =
`IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor`, qui SEEDE son `OrderedSet`
avec `GetUnitPosition(unit)` avant l'union — l'ajout du hook n'est donc PAS une sur-génération, et la
position courante est la PREMIÈRE de l'énumération (tie-break keep-first, cf.
`docs/rl/case-r1-origin-action-tile.md`).

## En cours / next

- **(FAIT)** décompile `GetValidTargetsInSteps`/d__18 → cf. carte ci-dessus (#3 = coroutine
  de #2, même résultat ; #1 = primitive mono-position ; #4 `GetBestTileToAttackFrom` = argmax IA).
- **(FAIT)** `aiAttackRank` autonome validé — shrink-and-recall, abilities concrètes
  auto-découvertes, tile courante incluse, fidèle à la décision IA. Cf. carte RPC.
- Next concret au choix :
  1. valider `GetValidTargets` depuis une tile choisie (`UnitPosition(T)`), read-only ;
  2. intervention étape 2 : construire+appliquer `MoveUnitMessage` vers tile choisie,
     observer l'atterrissage (pos post-move) ;
  3. figer le **format de capture minimal** d'une battle + 1ʳᵉ pass features offline (IL) ;
  4. impact de l'ordre : winrate ordre naturel vs forcé (même seed, 2 runners).

## Légalité ability + RAISON structurée + couche Playbook (investigation ghidra 2026-06-23)

Investigation pour combler 2 trous : **(H55)** no-op silencieux d'un play d'ability
(`mutated=false, 0 event` → on devinait la cause) ; **complétude** des abilities
**non-attaque** (buff/summon/hex absentes des `attackPlans`). Net-new vs la carte
AttackQuery #1-#4 ci-dessus :

### a) Énumération SANS position (toute-le-tour) — le vrai analogue de `aiMovableTiles`
`IBattleQuery` (= `EntityServices.<Battle>@0x70`) :
- **`GetAllValidTargetsFromAllPossibleMovementTiles(IEntity unit, ActiveAbilityType ability, bool ignoreMovementFlag)`** `@1810e8d50` → `ValidTargets`. Calcule en interne tous les
  tiles de move ET toutes les cibles légales depuis ceux-ci. **Aucune `UnitPosition` à
  construire** (contrairement à #1/#2). = « ce que l'unité peut caster/toucher CE TOUR ».
- `GetAbilityTargetingOptions(ActiveAbilityType ability)` `@1810e5c10` → `TargetingOptions`
  (struct 0x40) = mapper interne ability→options. **On n'a pas à l'appeler** : `GetValidTargets`
  le fait. Confirme que **toutes** ces méthodes ne prennent qu'un `ActiveAbilityType` (id
  concret, cf. §« Modèle d'abilities ») et dérivent les options seules.

`ValidTargets` (class, TypeDefIndex 12479) : `OrderedSet<IEntity> AllTargets @0x10` (set plat) ·
`Dictionary<UnitPosition, OrderedSet<IEntity>> TargetsByPosition @0x18` (cibles par position du
caster). Cache jeu : `ValidTargetsKey = (BEntityId attacker, UnitPosition from, ActiveAbilityType)`
→ overloads `GetValidTargetsWithCache(…, Dictionary<ValidTargetsKey,ValidTargets>)`.

### b) RAISON structurée du rejet — `GetInvalidTargetReason` → `TargetingRule` ([Flags] 64-bit)
La carte note `GetInvalidTargetReason` comme **bool** via `IsInvalid`. En fait son retour
`IBrokenTargetingRule.Type` est un **flag `TargetingRule`** décodable en raison précise
(remplace la devinette H55). Body `@1810e1cd0` confirmé : ability pas castable →
`ValidRequest`(0x1) ; déjà utilisée → **`AlreadyUseThisTurn`(0x40000000000000)** ; sinon →
vraie règle cassée par cible. Bits utiles (enum complet : `dump.cs` @423198) :

| Flag | Sens |
|---|---|
| `TargetIsAtRange`/`TargetIsInRange` | hors portée |
| `AlreadyUseThisTurn` | déjà utilisée ce tour |
| `ValidRequest`(1) | ability pas castable (null / `!CanCurrentlyBeUsed` / name==0) |
| `AbilityIsNotDisabledByConfigModification` | ability désactivée |
| `TargetIsUnobscured` | ligne de vue bloquée |
| `TargetIsEnemy`/`Friendly`/`Healable`/`Repairable` | mauvais type de cible |
| `TargetTileIsFree` | tuile de summon occupée |
| `CasterHasNotMoved`/`CasterHasCompletedOneTurn` | état caster invalide |

`GetInvalidCasterReason(attacker, attackerTile, ability)` = pourquoi le caster ne peut pas
caster du tout. Overloads `GetInvalidTargetReason` : `(…, IEntity tile, …)`,
`(…, UnitPosition, …)`, `(…, IList<IEntity> tiles, …)`. `NoBrokenTargetingRule` = valide.

### c) L'IA (Playbook) consomme EXACTEMENT cette query — parité
`IdunBattle.AI.Playbook`, 2 couches :
- **`BasePlaybook`** = légalité générique : `GetEligibleTargetsSelectable(unit, ability, fromTiles)`
  `@18119fa20` construit un `UnitPosition` → appelle (slot **0x43**) `GetValidTargets(unit,
  UnitPosition, ability)` → lit `AllTargets@0x10` → filtre via `ShouldEvaluateTarget` ;
  `GetAllValidTargetsFromAllPossibleMovementTiles(unit, ability)` `@18119f1e0` → slot **0x46**
  de BattleQuery. + `GetEligibleTargetsEntities`, `GetAllNormalAttackTargets`.
- **`<Ability>Playbook`** = policy/scoring par-ability (au-dessus des weights `Utilities`) :
  `Calculate*Utility`/`GetTargetUtility`/`Get*Selector`. Non-attaque : `CrusadeOfWrath.
  GetBuffTargetsSelector` (buff), `IdunBattle.AI.Playbook.Common.RepairPlaybook` /
  `IdunBattle.AI.Playbook.Loki.NanoscarabRepairProtocolsPlaybook` (repair — l'exemple
  `BattleTinkererRepair.FindHighestAttackEnemyWithTarget` cité ici jusqu'au 2026-07-30 a été
  RETIRÉ du jeu, cf. #270 : ni la classe ni l'ability n'existent plus),
  `DeathFromAbove`/`ResurrectionOrb.GetNumPossibleSpawnTilesForTarget` (summon),
  `NobleCharge.GetPushableTargetOnHighestUtilityTile` (displacement). cf. mémoire
  `reference_playbook_ai_policy`. → la **légalité** est ce qu'on expose ; la **policy** est de la
  doctrine lisible si on veut comprendre les choix de l'IA.

### d) RPC `abilityTargets` — IMPLÉMENTÉ + VALIDÉ (2026-06-23)
`ctx.rpc.abilityTargets` (rpc-view.ts) + offset `battleInServicesOff` (internals.ts) +
commande `rl_duel abilities [--unit U] [--ability A]`. Par (unit ctrl+vivante × ability
concrète : normal+actives via `unitAbilityTypes`) : `battleQuery` (= `runner.<Services>` →
`+battleInServicesOff` = EntityServices.`<Battle>`) → `GetAllValidTargetsFromAllPossible
MovementTiles(unit, ability, ignoreMovementFlag=false)` (résolu lazy via
`battleQuery.readPointer()`, 3-param unique → pas d'ambiguïté) → `ValidTargets.AllTargets@0x10`
→ `extractTilePtrs` → cibles : ptr résolu via carte `forEachEntity` (Unit → squadId/visualId/pos
projection ; sinon → tile coord `readTileCoord`). Read-only (`mutated=false`), aucune RVA.

**Validé live** (seed 80000, runner mid-combat, **32 ms**, `mutated=False`) : `Foehammer`
(attaque) → 5 units ; `RadBombardment`/`UnstoppableMomentum` (tile-targeting) → 19/23
**tiles** ; `FoulInfusion` (self-buff) → self ; `InspiredToGreatness` (buff sans cible) → ∅ ;
normal attack range-exact. Empty au déploiement (équipes à ~8 rangs) **corroboré par
`aiAttackRank`** (0 position) ⇒ correct, pas un bug. Les abilities non-attaque (tiles/self),
absentes des `attackPlans`, sont désormais surfacées — trou de complétude comblé.

DEUX listes par ability (depuis 2026-06-23, refinement 1 fait) : `targets` = « ce tour, MOVE
inclus » (superset, via BattleQuery) ; **`fromHere`** = castable **SANS bouger** depuis la tuile
courante (légalité EXACTE du cast immédiat). ∉ des deux ⇒ no-op certain ; ∈ targets mais ∉ fromHere
⇒ « bouger d'abord ». Champ `fromHereResolved` au top-level.

**`fromHere` — comment c'est fait** : `AttackQuery.GetValidTargets(unit, UnitPosition from,
ActiveAbilityType)`. Deux pièges réglés : (a) overload de MÊME arité (l'autre prend
`IOrderedSet<UnitPosition>`) → nouveau helper réutilisable `findMethodByParamClasses(klass, name,
[null,"UnitPosition",null])` (via `il2cpp_method_get_param` → class name) dans helpers.ts ;
(b) le struct `UnitPosition` by-value fabriqué SANS son ctor ambigu : `EntityExtensions.GetTiles(
unit, state)` → `IList<IEntity>` puis buffer 8 octets `{Tiles}` (gcRoot tant qu'utilisé). Le call
per-position est read-only (`mutated=false` confirmé live). Validé seed 80000 mid-combat (58 ms) :
Foehammer `now:∅ +move[5]` ; UnstoppableMomentum `now[3] +move[20]` ; FoulInfusion self-buff
`now[1]=self` ; `targets = fromHere ∪ move_only` cohérent.

**Branché dans la carte oracle** (2026-06-23) : `rl_duel view` (`_show_card`) appelle aussi
`abilityTargets` et passe le résultat à `oracle.build_card(view, bd, abil=…)`. La section
**MES ACTIFS** affiche désormais, par actif, l'état live + la légalité `now`/`+move`
(`u91 RadBombardment(1116) [prêt] →now[3]:(1,9),(2,8),(3,9) · +move[16]:…`) ; `→∅(no-op
certain)` quand l'actif n'a aucune cible. Comble les actifs NON-attaque (buff/summon/hex,
absents des PLANS D'ATTAQUE) là où l'oracle choisit. helpers `_tgt_key`/`_tgt_compact`/
`_abil_targets_summary` (oracle.py) ; `build_card(abil=None)` rétro-compatible.

**MoW FAIT** (2026-06-23, refinement 3) : `abilityTargets` scanne aussi les casters
`EntityType.Machine` (6) ctrl+vivants → `mowAbilityTypes` (Primary/Secondary + actives) +
mêmes queries `GetAllValidTargets…`/`GetValidTargets` (elles gèrent les machines : la décompile
de `GetInvalidTargetReason` a une branche `IsMachinePrimaryAbilityType`). Entrées taggées
`isMow:true`, identité via `projectMowsFull` (casterId=machineId). Carte : la section MoW affiche
now/+move par ability (abil_idx indexe aussi `(casterId, abilityId)`). Validé seed 80000 +
`--mow` : adeptExorcist `ThriceBlessedConflagration(1187)→now[4]` (= 4 alliés, gameconfig
confirme « Targets a friendly unit » → invisible des attackPlans), `DevastatingRefrain(1188)→
now[52] tiles` ; MoW ENNEMI listé sans cibles (≠ joueur courant). `fromHere` marche aussi sur les
Machine (GetTiles+UnitPosition). Reste : `pos/hp` MoW = None à certains états (quirk projection
préexistant, hors scope).

**Raison structurée FAIT** (2026-06-23, refinement 2) : RPC `abilityReason({runnerId, casterId,
abilityType, targetId?})` → `AttackQuery.GetInvalidTargetReason(caster, casterTile, target, ability)`
+ `GetInvalidCasterReason` (overloads 4-/3-param désambiguïsés par tile="IEntity" via
`findMethodByParamClasses`) → `IBrokenTargetingRule` BOXÉ. **Piège résolu** : NoBroken/Generic
BrokenTargetingRule sont des **struct** ; `get_Type()` sur struct boxée veut `this=obj+0x10` —
appeler avec `this=obj` lisait le champ@0x0 = **pointeur de klass** (d'où un faux masque
identique pour 2 abilities). Fix : lire le champ `<Type>@0x0` DIRECT à `obj+0x10` (Generic
BrokenTargetingRule), garder par `class_get_name` (NoBroken=valide). Décodé en noms via
`data/targeting-rule-names.ts` (bit→nom, dump-généré comme ability-names). Renvoie **1 flag
unique** = la 1ʳᵉ règle cassée (l'ordre d'éval du jeu). Validé : vs untargetable (deep-strike)
→ `TargetIsTargetable` ; vs loin → `TargetIsInRange` ; en portée → `NoBrokenTargetingRule`
(valide). **Câblé `rl_duel`** : commande `reason` + filet réactif `_action_failed` (eventCount==0)
+ **pré-validation proactive** `_ability_prevalidate` dans `cmd_play` (abort AVANT applyAction sur
cast ciblé illégal — capte le no-op « event émis, 0 effet » hors-portée que le réactif rate).

Adresses RE = build **kqkbjqfb6c** (lecture humaine) ; le hook résout tout **par nom en
runtime** (CLAUDE.md). **Tous les refinements (1 fromHere, oracle view, 3 MoW, 2 raison) FAITS.**

## Infra / rappels

- Host `:8765`, build **kqkbjqfb6c**, PG TACTICUS:5433. ghidra-mcp sur :13337.
- **Réinject hooks-only** via `POST /api/admin/inject` (body `{}`) — PAS de restart host.
  `autoBootExtraire({force:true})` est **AUTONOME** (pilote la nav UI seul) — à
  appeler après chaque (re)inject, jamais demander un clic à l'utilisateur.
- **Le pump driver bloque le main thread** → CHUNKER (≤ ~2-4 tours/appel) sinon
  `UnityFreezeDetector` tue le jeu ; combat entier = boucle Python de chunks (Unity
  pompe ses frames entre les appels). Session courante ~17.
- Perf : ~784 pumps/décision (~0.5 ms/pump) ; 1res décisions chères puis ça tombe.
  Combat entier ≈ 15 s. Read-only confirmé (`mutated=false`) sur toutes les queries.
