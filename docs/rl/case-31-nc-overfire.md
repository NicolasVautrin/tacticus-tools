# Case-31 — NonComparable overfire : gates 1180 HeroicFusillade + 1118 DoctrinaImperatives trop lâches

**Statut : 1118 RÉSOLU+VALIDÉ ; 1180 RÉSOLU+REFERMÉ (2026-07-22, #39 fable-solver) — le « gate
per-JOUEUR » était un ARTEFACT expérimental (confond camp ↔ numéro de tour) ; mécanisme natif réel =
slot-4 `turnsStarted > 1` @18111af90 (#46), player-blind — cf. §A.4.** Build `gqfc5mff6c`. Les
générateurs NC passent AVANT le fallback Comparable
(`InitAbilityTypeLists @1810ed540`) → une NC qui « sort » écrase l'attaque par l'ordre des générateurs ;
une NC émise à tort = miss d'agreement (ability + position en aval).

---

## Demi-partie B — 1118 DoctrinaImperatives (Tan Gi'da) — **RÉSOLU + VALIDÉ**

Notre port émettait 1118 (self-cast toggle Protector↔Conqueror) **inconditionnellement dès que `usable`**.
Gate natif `DoctrinaImperativesPlaybook.EvaluateNonComparable @18112c8d0` (verdict re-expert, slots
`0x51`=`GetAdjacentUnits`, `0xc9`=`ReachedSummonCap @181070f60` ; `1248`=Conqueror, `1200`=ControlEdict) :
```
count = fromHereCount(caster, NormalAttack)        # cibles d'attaque normale SANS bouger
if count == 0:  emit ssi HasEffect(caster, ConquerorImperative 1248)   # en Conqueror & rien a taper -> rebascule Protector
else:           adj = GetAdjacentUnits(caster)     # TOUT CAMP
                emit ssi (adj>0 ? ReachedSummonCap(caster, ControlEdict 1200) : True)
```
**Port** (`doctrina_imperatives.py` `_should_emit`) : `_has_valid_targets` (=`HasValidTargets`, fromHereCount>0)
pour count ; `me.effects` contient `"ConquerorImperative"` (fallback `scene.eff_state.has_effect(1248)`) pour
Conqueror ; `neigh_by_pos[origin] ∩ (epos∪fpos)` pour adj. `ReachedSummonCap` = **champ offline manquant**
(pas de lien summoner→summons) → conservateur `False` (cf. task #38).

**Validé (31337, roster `admecMarshall,admecManipulus,admecRuststalker` vs `necroWarden×2`)** — A/B décisif :
- AVANT (émit inconditionnel) : ability **3/4 (75%)** — step 1 u81 `generator-overfire`, step 7 u81
  `engine=1118 vs native ab=69` [MISS].
- APRÈS (gate) : ability **4/4 (100%)**, move **7/7**, zéro overfire 1118. Gate exercé (prouvé par l'A/B).

NB : Tan Gi'da était côté **p-units** dans ces walks → le gate 3-branches est bien la sémantique du côté
émetteur ; il n'est PAS un épiphénomène du gate per-joueur de la demi-partie A.

---

## Demi-partie A — 1180 HeroicFusillade (Judh) — **REFERMÉ : « per-JOUEUR » = artefact ; mécanisme = turnsStarted>1**

> **RÉVISION 2026-07-22 (#39 fable-solver).** Le verdict A.1 ci-dessous est CONSERVÉ comme archive
> mais sa CONCLUSION (« c'est le JOUEUR ») est **RÉFUTÉE** : dans les 4 expériences, le camp de Judh
> était CONFONDU avec son numéro de tour (`turnsStarted`). Les mesures « a-units » étaient TOUTES au
> 1er tour de Judh (ts=1) ; les émissions « p-units » toutes au tour >= 2 (ts=2). Le mécanisme réel
> est le slot-4 `ShouldEvaluate(unit)` foldé @18111af90 = `GetStat(unit, 0xc=TurnsStarted) > 1`
> (découvert en #46, APRÈS le verdict). Contre-exemple direct mesuré (`probe_39c_crafted.py`,
> MC1_67 seed 4242, Judh SEUL a-units vs 2 necroWarden p-units tenus adjacents) : au tour 2 de Judh
> (ts=2), **le natif émet `move+1180→79` DEPUIS LE CAMP A-UNITS**. Détails : §A.4.

### A.1 — Le verdict INITIAL (4 expériences live, session 2026-07-19) — conclusion révisée, cf. encadré

**Observation brute (exacte) : le natif n'a émis 1180 dans aucune de ces mesures côté a-units, et
l'a émis côté p-units.** L'INFÉRENCE « c'est le JOUEUR » était fausse (variable confondue : ts) :

| # | setup | mesure | résultat |
|---|---|---|---|
| 1 | 909 default (Judh u85 = **a-units**), walk 10 pas | état 1180 à s10 : `usable=true cooldown=null disabled=false hasAmmo=true`, 1ʳᵉ action de Judh de la bataille, aucun effet bloquant ; `targets={91,93,95}` ; `castFromTiles` = 9 tuiles VALIDES (pipeline complet, règle dynamique incl.) | natif = `move(6,3)+ab69→93`. **PAS de 1180** |
| 2 | idem, u85 **forcé adjacent** au Patriarch (move (4,4)) ; `fromHere=[91,93,95]` (la query per-position du playbook voit tout) | dryRun | natif = `ab69→93`. **PAS de 1180** |
| 3 | MÊME seed/board/rosters, camps **échangés** (Judh = p-units team 1), walk piloté (approche sur 2 tours) | step 15 | natif émet **1180→81 (Patriarch) SPONTANÉMENT** |
| 4 | 31337 `--p-units genesKelermorph,admecManipulus,admecRuststalker --a-units necroWarden×2` (re-vérifié ce jour) | step 6 | natif = `1180→79` (notre moteur MATCHE déjà ce cas) |

**L'asymétrie n'est PAS « l'IA n'utilise pas les NC »** : le camp a-units émet d'autres actives ET des NC
bespoke (mesuré : 1117 DefendTheDivineWork, 1122, 1123 en 31337 swappée). Elle est spécifique à 1180
(périmètre exact non délimité — cf. A.4).

### A.2 — Croyances antérieures INVALIDÉES (ne pas re-dériver)

- ✗ « root cause = slot 0x44 superset vs 0x41+GetDynamicInvalidTargetReason » : **faux**.
  `GetDynamicInvalidTargetReason @1811e9430` n'est PAS dans le chemin playbook — il n'est appelé que par
  `AttackQuery.GetInvalidTargetReason @181056960` (single-target : usability + règles statiques + callback
  dynamique ; c'est le chemin de `castFromTiles`/`abilityReason`). Le Remove de `GetEligibleTargetsSelectable`
  = `!ShouldEvaluateTarget` (@18111fb10 : filtre Environment/IrrelevantObject), corps foldé b__54_0 @18111ff90.
- ✗ « la reachability du free-hex discrimine » : jamais le discriminant (les 3 modèles offline d'Opus
  échouaient parce qu'ils cherchaient une règle géométrique qui n'existe pas).
- ✗ « once-per-battle consommée » : 1180 était FRAÎCHE à 909 s10 (1ʳᵉ action de Judh, usable/hasAmmo verts).
  (Le once-per-battle est réel — texte i2 « can be used again when resurrected » — mais pas en cause ici.
  Rappel : `AttackQuery.GetValidTargets @1810570c0` ne gate PAS `CanCurrentlyBeUsed`, seulement
  `IsAlreadyUsedThisTurn` → le RPC `targets` resterait non-vide après consommation ; `HasValidTargets
  @181057540` et `GetInvalidTargetReason` gatent le getter composite `get_CanCurrentlyBeUsed`, eux.)

### A.3 — Chaîne de décision native (décompilée, VAs — la carte est ACQUISE)

- **Positions** : `DefaultAiUnitTactic.<CalculateNextActionForUnit>d__5 @1810f54e0` → positions =
  `ABaseAiUnitTactic.GenerateActionTiles @1810ede70` = `IBattleQuery.slot 0xe` =
  **`GetCurrentAndMovablePositionsFor`** (courante + movable, AUCUN élagage) + hook par-playbook
  `FilterMovementTiles` (IPlaybook slot 1 ; overrides connus : RunsAround/RunsAway/SaviorProtocols).
- **Générateur** `ActiveAbilityActionGenerator.<GenerateActions>d__7 @18119a3f0` — par ability :
  gates `IsAbilityBlocked` (@180ed75f0, blocks par effets) / `get_CanCurrentlyBeUsed` (composite) /
  `CanStillBeUsed@0x28` / `!IsDisabled@0x35` / registry ; `LoadPlaybook(type, create=1)` ; `ShouldEvaluate`
  (base = probabilité 1 → déterministe pour 1180) ; puis **boucle PER-POSITION** : gate playbook slot 6 +
  `IBattleQuery.slot 0x3f HasValidTargets(unit, pos, type)` (@181057540) → `Evaluate @18111df40`
  (SetDisallowRandom autour) → `EvaluateInternal` (thunk vtbl+0x318) → `EvaluateNonComparable(unit, sweptPos)` ;
  `NullPosition` en fallback ; Merge dans UN bucket ; `ChooseAction` à l'épuisement des abilities.
- **HeroicFusillade `EvaluateNonComparable @181144510`** : appelle l'overload **@18111ed80** (single-pos —
  PAS @18111f510 tiles-list) : `GetEligibleTargetsEntities(unit, pos)` = slot **0x41**
  `GetValidTargets(unit, pos, 1180)` − Remove(`!ShouldEvaluateTarget`) ; par cible : gate1
  `HasTrait(cible, Hero 0x10)`, gate2 ∃ ennemi-du-caster ∈ `GetSurroundingUnits(GetTiles(cible), r=1)`
  (slot 0x76) ; émission `GenerateAction(util=Fix64(1))`, position = sweptPos. Struct item : +0x10 cible,
  +0x30/0x38 mainTile/tiles(cible), +0x40 pos.MainTile, +0x48 pos.
- **Routage stratégies** : `AiControl.GetAi @180ffc270` / `RunComputerActionsForPlayer @180ffcf20` routent par
  **PlayerType** (2=Environment→+0x30 ; **4**→paire#2 (+0x28/+0x68) ; sinon paire#1 (+0x20/+0x60) ;
  `+0x70`=RandomizeAiInput sélectionne la variante WithSomeRandomness). Seed BC : player=0, enemy_1=1, Env=2
  → **les deux joueurs du duel routent vers la MÊME paire #1** (l'asymétrie n'est PAS le routage GetAi).
- `AiQuery @181054600` = 5 tactiques ; `GetUnitTacticForUnit @181054550` : steppable/useless→SkipTurn,
  machine→DefaultMachine, boss→LokiBoss, nonattacking→OnlyMove, sinon Default (ou SkipActiveAbility si flag
  ctor — `IsValidAbilityType = !IsActiveAbility` exclurait TOUTES les actives : pas notre cas, cf. 1117).
- `IdunRunner.Initialize @180e35400` crée **2 PlaybookDatabase** (mêmes builders `InitializePlaybookBuilders
  @1810d02b0` ; seule diff = PRNG bataille vs MersenneTwister wall-clock) pour les 2 paires. `LoadPlaybook
  @1810e0090` : builder manquant + create → **DefaultActiveAbilityPlaybook (Comparable)** (⇒ une ability sans
  builder serait classée Comparable par `InitAbilityTypeLists`).

### A.4 — RÉSOLU (#39, 2026-07-22) : mécanisme = slot-4 `turnsStarted > 1` ; « per-joueur » = confond

**1. La chaîne native est INTÉGRALEMENT player-blind (relue de bout en bout, VAs).** Les trois
candidats de l'ancienne §A.4 sont ÉLIMINÉS :
- (c) Utilities per-player : la seed BC n'a qu'UN bloc `Utilities` partagé (`Default`/
  `MovementSuggestion`), aucune clé per-player, aucune entrée HeroicFusillade ;
- (b) gate PlayerComponent dans tactic/générateur : `RunComputerActionsOperation.Execute @180e93e80`
  (cheat ET tour naturel convergent : `RunComputerActionsForPlayer(currentPlayerId)`) →
  `AiControl.GetAi @180ffc270` (PlayerType 0 ET 1 → MÊME instance +0x20 ; `Init @180ffc460` : la
  paire #2 (+0x28/+0x68) est réservée à PlayerType 4) → `DefaultPlayerStrategy.<CalculateNextAction
  ForUnit>d__7 @1810c0c10` : la SEULE référence absolue au camp de toute la chaîne est le bool
  `GetCurrentTeamId(unit) != 1` passé à `AILog.AIActions..ctor` — un flag d'ÉCRAN DEBUG (AILogScreen),
  pas un gate → `DefaultAiUnitTactic..ctor @1810eebc0` / `GetDefaultActiveAbilityActionGenerators
  @1810ed0c0` (générateurs ordonnés : NC dict{1000,100,0,-100,-1000}@+0x40 → comparable@+0x38 →
  movement ; premier yield non-nul gagne, `<CalculateNextActionForUnit>d__5 @1810f54e0`) →
  `<GenerateActions>d__7 @18119a3f0` (gates per-ability tous unit-scoped : HasFlag(unit,2=
  ActiveAbilityUsed), Contains liste NC, IsAbilityBlocked, get_CanCurrentlyBeUsed @180f8fdb0
  (+0x28 canStillBeUsed && !+0x35 && cooldown+0x2c && ammo+0x38/+0x40), IPlaybook slot4/5/6/7) —
  rien de per-player ; les gates du playbook @181144510 sont RELATIFS (IsEnemy(surrounding, caster)) ;
- (a) corps générique bucket : `Bucket.Merge @1813fc790` / `ChooseAction @1813fc0d0` déterministes,
  sans état joueur (et `ShouldRandomizeOrder @181182dd0` ne shuffle que pour {1134,1135,1136,1218}).

**2. Le discriminant réel = slot-4 `ShouldEvaluate(unit)` de 1180** (corps foldé @18111af90, #46) :
`GetStat(unit, 0xc=TurnsStarted) > 1`. Dans les 4 expériences A.1, camp ↔ tour étaient confondus
(le camp a-units joue 2e → son 2e tour arrive ~2x plus loin dans le walk ; toutes les mesures
a-units étaient à ts=1). Cohérent avec 1191 MartialInspiration (même famille NC, PAS de slot-4
turnsStarted) qui émet côté team 2 (case-52 #57f) — l'asymétrie n'affectait QUE 1180.

**3. Preuves live (#39, probes versionnés) :**
- `probe_39b_tscounter.py` (909/MC1_67, walk natif, dump ts par pas) : à s10 ts(Judh)=1 → bloqué ;
  au tour 2 les autres a-units passent ts 1→2 (compteur symétrique : `StartTurnOperation.Execute
  @180ea3fb0` ++ `UnitComponent.turnsStarted@+0x58` sur les `CurrentlyOwnedUnitIds` du joueur
  courant) mais ts(Judh) RESTE 1 — effet de bord du 1202 VigilanceEternal casté SUR Judh (u95
  s17) → bloqué au tour 2 AUSSI sur ce seed (c'est pourquoi même un walk long 909 ne montrait
  jamais l'émission a-units).
- `probe_39c_crafted.py` (MC1_67 seed 4242, Judh SEUL a-units, 2 necroWarden p-units SCRIPTÉS
  adjacents/immobiles, zéro 1202) : tour 2, ts=2, cibles {79,81} légales, gate2 vrai → **natif =
  `move+1180→79` côté TEAM 2** ; H_perplayer réfutée par contre-exemple direct.

**Latéral (hors périmètre, à creuser si besoin)** : le saut d'incrément ts sur la cible d'un 1202
(mesuré, non RE'd) ; le port est immunisé (il lit le compteur live par pas). NB outillage : le
bucket-audit (frida/hooks/features/bucket-audit.ts) résout ses cibles via la générique OUVERTE
`Bucket\`1` (findBucketMethod) → methodEntry ne pointe pas les corps gshared exécutés
(@1813fbcc0/@1813fbb60/@1813fc0d0/@1813fc660) → diag=0 STRUCTUREL ; inutilisable sans rebuild.

### A.5 — Port (mirror du mécanisme natif, plus de gate camp)

`heroic_fusillade.py` : le gate `_is_player_side` (team 1) est **SUPPRIMÉ** (#39). Gates restants,
tous natifs : slot-4 `turnsStarted > 1` (`_turns_started_gate`, lecture live stat 12 par pas) +
gate1 Hero + gate2 adjacent-enemy + éligibilité `targets`. Validation #39 (4 walks ciblés) :
- crafted a-units (runner gelé à l'état de décision du probe_39c) : engine `1180→79` = natif
  **MATCH** — le cas que l'ancien port MANQUAIT par construction ;
- 909/MC1_67 22 pas : pos 17/17, ability 7/8 — s10 `69→93` HIT (bloqué par ts, sans gate camp) ;
  le seul miss (s20 u77 `1140` vs eng `69→152`) est HORS périmètre (u77 sans 1180, tronçon jamais
  couvert par la référence historique qui s'arrête à s18) ;
- 909 suite (tour 2 Judh, ts collé à 1 par 1202) : `69→93` HIT — pas d'overfire, le port suit le
  compteur live ;
- 31337-genes 9 pas : ability 5/5 — s6 `1180→79` MATCH préservé (émission p-units).

## VAs
`HeroicFusilladePlaybook.EvaluateNonComparable @181144510` · `GetEligibleTargetsSelectable @18111ed80`
(single-pos ; overloads @18111f0d0/@18111f510) · `GetEligibleTargetsEntities @18111ebd0` ·
`ShouldEvaluateTarget @18111fb10` (b__54_0 @18111ff90) · `AActiveAbility.GetValidTargets @180fb1ee0` ·
`AttackQuery.GetValidTargets @1810570c0` / `HasValidTargets @181057540` / `GetInvalidTargetReason @181056960`
/ `CanUseAbility @181054ec0` · `HeroicFusilladeAbility.GetDynamicInvalidTargetReason @1811e9430` (+ closure
b__0 @1811fd730, const idx 0x16=2, pathfinder ability+0x38 slot 0xd maxDist=2) ·
`DamagePredictionQuery.GetAllValidTargetsFromAllPossibleMovementTiles @1810917c0` (+ d__29 @1810acc50 :
movableTiles+current → AttackQuery.GetValidTargets, PAS de filtre dynamique) ·
`ActiveAbilityActionGenerator.<GenerateActions>d__7 @18119a3f0` · `DefaultAiUnitTactic
<CalculateNextActionForUnit>d__5 @1810f54e0` / `<CalculateAbilityActionForUnit>d__7 @1810f47f0` ·
`ABaseAiUnitTactic.GenerateActionTiles @1810ede70` (slot 0xe = GetCurrentAndMovablePositionsFor) ·
`ABaseAiActorTactic.InitAbilityTypeLists @1810ed540` · `PlaybookDatabase.LoadPlaybook @1810e0090` /
`InitializePlaybookBuilders @1810d02b0` · `AiControl.Init @180ffc460` / `GetAi @180ffc270` /
`RunComputerActionsForPlayer @180ffcf20` · `AiQuery..ctor @181054600` / `GetUnitTacticForUnit @181054550` ·
`SkipActiveAbilityUnitTactic.IsValidAbilityType @1811366a0` · `StaticBattleRules.ActiveAbility.IsActiveAbility
@181555670` · `UnitExtensions.IsAbilityBlocked @180ed75f0` · `BasePlaybook.Evaluate @18111df40` /
`ShouldEvaluate @18111fb70/@18111fc70/@18111fe70` / `GetUseProbability @18111f9b0` · slot-4 1180 foldé
@18111af90 (turnsStarted>1) · `StartTurnOperation.Execute @180ea3fb0` (++ `UnitComponent.turnsStarted
@+0x58`) · `UnitTurnsStartedFormula.Calculate @180f2d6c0` · `RunComputerActionsOperation.Execute
@180e93e80` · `DefaultPlayerStrategy.<CalculateNextActionForPlayer>d__6 @1810c0760` /
`<CalculateNextActionForUnit>d__7 @1810c0c10` (flag log `teamId != 1` → AILog) · `DefaultAiUnitTactic..ctor
@1810eebc0` · `ABaseAiActorTactic..ctor @1810edcd0` / `GetDefaultActiveAbilityActionGenerators @1810ed0c0` ·
`ActiveAbilityActionGenerator..ctor @181183050` / `GetUnitAbilitiesInOrder @181182a40` / `ShouldRandomizeOrder
@181182dd0` · `Bucket.Merge @1813fc790` / `ChooseAction @1813fc0d0` · `ActiveAbility..ctor @180f8fba0` /
`get_CanCurrentlyBeUsed @180f8fdb0` ·
`DoctrinaImperativesPlaybook.EvaluateNonComparable @18112c8d0` · `ReachedSummonCap @181070f60` · slots
IBattleQuery 0xe/0x3f/0x41/0x44/0x51/0x6e (distance hex)/0x76/0xbb/0xc9.
