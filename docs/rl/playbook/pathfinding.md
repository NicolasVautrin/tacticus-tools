# Pathfinding & scoring de position

> État faithful ACTUEL du repositionnement de l'IA Tacticus : scoring d'une tuile de
> mouvement (`engine/move.py` + leaves `engine/utilities/tile.py`) et énumération des
> tuiles atteignables (`engine/entities/pathfinding/`). Source = RE ghidra (decompile =
> vérité), confirmée live.

## 1. Deux moteurs natifs DISTINCTS

L'IA et le scoring de move s'appuient sur deux mécanismes séparés ; **l'IA ne consomme que
le premier** (l'ensemble atteignable), le second ne sert qu'au tracé de chemin exact.

| moteur | rôle | chaîne native | porté ? |
|--------|------|---------------|---------|
| **Énumération (reachable set)** | tuiles où l'unité peut finir | `GetMovableTilesFor` @18109a330 -> `FindAnyOrAllMoveableTiles` @181098cb0 -> `BasePathfinder.GetMovablePositions` @180ee25d0 | OUI (`walk_pathfinder.py`) |
| **Chemin exact (A\*)** | longueur de chemin tuile->tuile | `GenerateBreadthFirstTree` @180ee21a0 + `WeightCost` @180f2f120 | NON (capté via RPC, pas réimplémenté) |

L'énumération est un **FLOOD-FILL PAR NIVEAUX, NON pondéré** : 1 pas = 1 niveau, `range`
niveaux (itér. @180f27840, `NodesInNextLevel`, profondeur −1/niveau, **aucun coût
accumulé**). L'A\* (`WeightCost` = (10 ou 10000 si bloquant) − élévation) ne sert qu'à
`GetPathTo` ; on capte sa sortie via RPC plutôt que de la réimplémenter.

## 2. Termes de scoring de position (`engine/move.py`)

RE des `IdunBattle.AI.Utilities.*Utility.<EvaluateMovementInSteps>` + `BaseUtility.
GetUtilityValue` (lit le poids nommé BC -> `Fix64.FromInt`). On compare l'**ARGMAX** (tuile
choisie), pas la valeur Fix64.

| terme (`*Utility`) | formule RE'd | poids BC (`Default.<cat>`) | statut |
|---|---|---|---|
| `MinDistanceToClosestEnemy` | `wMin × min_d(tile, enemies)` | `PerTileDistance −100` | **ACTIF, DOMINE** |
| `MaxDistanceToEnemies` | `Σ_e [ Wfar − (Wfar−Wclose)/max(d,1) ]` | `ClosestEnemy 10, FarthestEnemy 100` | proxy (hors composite) |
| `Elevation` | `Mult·elev (+Highest si max, +Lowest si min)` | `Mult 10, Highest 10, Lowest −5` | no-data (omis) |
| `RangedAdjacentEnemy` | `HasAdjacentEnemy` si tuile a ≥1 ennemi adjacent | `−50` (profil `MovementSuggestion`) | ACTIF (gaté ranged) |
| `MaxDistanceToUnitTile` | `Wfar − (Wfar−Wclose)/d_ref` | `ClosestTile 400, FarthestTile 700` | **GATÉ OFF** |

Forme commune des `MaxDistance*` : `f(d) = Wfar − (Wfar−Wclose)/max(d,1)` (f(1)=Wclose,
f(∞)→Wfar, rendements décroissants).

- **`MinDist` DOMINE** : `−100×d` vers l'ennemi le plus proche ; 2 gates (=0 si l'ennemi le
  plus proche est NonAttacking / non-damageable). RE `MinDistanceToClosestEnemyUtility.
  <d__2>.MoveNext` @1810fe690 + `GetMinDistanceToEnemy` @1810f04a0.
- **`RangedAdjacentEnemy`** : `RangedAdjacentEnemyUtility` pénalise (−50) une unité ranged
  qui finit adjacente à un ennemi. `ShouldApply` teste si l'**arme/ability** est ranged
  (`WeaponProfile.get_IsRanged` / RangedBool @0x3d), **PAS** le flag unité-classe
  `UnitExtensions.IsRanged` qu'expose `decisionView.ranged`. Le signal « ranged-pour-
  mouvement » est donc **DÉRIVÉ de gameconfig** par `visualId` (`arme Range≥2 OU active
  attackRangeType=='Ranged'`, env `ENGINE_RANGED_DEF`) — `move.py` reste pur.
- **`MaxDistanceToUnitTile` GATÉ OFF — confirmé ghidra, pas seulement A/B** :
  `UtilitiesDatabase.InitializeUtilities._composedUtilityLookup` montre que ce terme n'est
  PAS dans `MovementSuggestion(32)` ni `UnitMovement(6)` ; il n'apparaît que dans
  `UnitMovementFromTemporary(5) = [UnitMovement(6), MaxDistanceToUnitTile(17)]` (moves
  depuis une tuile temporaire uniquement). La formule (`MaxDistanceToUnitTileUtility.
  <d__2>.MoveNext` @1810fdeb0, réf = tuile COURANTE) est CORRECTE mais hors-périmètre du
  move pur. Gardé GATÉ (`ENGINE_UNITTILE_MODE` : `off`/`far`/`near`).
- **`Elevation` no-data** : pas de données d'élévation de tuile dans `decisionView` pour le
  scoring proxy (l'élévation arrive via `tileMeta` côté faithful).

## 3. Le décideur de move (`MovementActionGenerator`)

`MovementActionGenerator.<GenerateActions>d__6.MoveNext` @181199d50 construit son décideur :
`utilDef = new UtilityDefinition((TileExtensions.IsTemporary(mainTile) ^ 1) + 5)`.

- tuile NORMALE (isTemp=0) -> `(0^1)+5 = 6` = **UnitMovement(6) = Tile(7) + MinDist(16)**.
- tuile TEMPORAIRE -> `(1^1)+5 = 5` = **UnitMovementFromTemporary(5) = UnitMovement +
  MaxDistanceToUnitTile(17)**.

**CONFIRME : le move pur = `Tile(7) + MinDist` — `MaxDistanceToEnemies(18)` n'y est PAS**
(c'était un proxy coïncidentel). `TileDistanceUtility(33)` (`DistanceTo(case, tuile-réf)`)
appartient à `MovementSuggestion(32)`, mécanisme différent non pertinent ici.

### La VRAIE divergence : distance CHEMIN vs distance hex

`GetMinDistanceToEnemy` = `IterateTiles(target)` × **PATHFINDER** (`path.Length@0x18`), min
sur les tuiles occupées par l'ennemi -> c'est une **distance de CHEMIN** (contourne murs/
obstacles), PAS la distance hex. Le coefficient `−100` et la forme `−100×d` sont corrects ;
seule la MÉTRIQUE était fausse (hex au lieu de chemin). Quand le chemin se courbe, l'argmax
diverge — c'était la pièce manquante du move pur.

### RPC `pathDistToEnemies` — le fidèle DÉPASSE le proxy

RPC (`rpc-view.ts`) : pour `unitId`, distance de CHEMIN MIN de chaque tuile atteignable vers
une tuile ennemie. Implémentation = `Pathfinders.GetPath(type=1, unit, from, to,
Nullable<UseTeleporter>=null)` (overload 5-param @180f20190) -> `List<IEntity>`,
`Count@0x18` = longueur. Accès via `runner.<Pathfinders>k__BackingField` (PAS `_pathfinders`
= le Dict interne). `best_move_faithful` consomme `pathdist_by_pos` (sinon fallback hex).

A/B (path remplace hex, ability 100 % partout) :

| seed | proxy (hex) | unitmovement hex | **unitmovement PATH (défaut)** |
|---|---|---|---|
| 777  | 60 / 80 | 55 / 75 | **65 / 80** |
| 2024 | 45 / 65 | — | **55 / 75** |

## 4. Leaves Tile(7) (`engine/utilities/tile.py`)

Mécanisme commun : `u=Fix64(0)` ; gate (effet/trait/ability/flag-tuile) ; si gate passe
`u += GetUtilityValue(<clé BC>)` × constante éventuelle. Clés = `Utilities.Default.<EnumName>`
lues dans `data/arena-battle-config-newtonsoft.json` (les string-keys vivent dans
`global-metadata.dat`, non résolvables depuis la DLL -> prises dans la BC).

| leaf (id) | gate (ids hex/déc) | formule + poids BC |
|---|---|---|
| TemporaryTile(13) | tuile `isTemporary` | **−10000** (constante) — **ACTIVE** |
| CapturePoint(24) | territoire (tile+0x2e) + flag trait 2/13 | `summons_dislike_capture_points`(−300) / `heroes_on_capture_points`(+300) |
| PowerUp(26) | occupant `IsPowerUp` + flag trait 2/13 | `summons_dislike_tiles_with_powerups`(−300) |
| Contaminated(25) | tile-effect 1244(0x4dc) + non-exclu | `AffectedUnit`(−25) |
| MoltenForm(23) | trigger 1221(0x4c5) + effet tuile 5/10 | `MoltenForm_ResistFireTiles`(+25) / `MoltenForm_AvoidHealingTiles`(−25) |
| TilePendingBlockableSummon(14) | summon en attente 1094(0x446) | `EnemySummon`(+25)/`FriendlySummon`(−25) par entrée |
| EnvEndBombardment(31) | effet 1359(0x54f)/1360(0x550) | `EnvEndBombardment_TileToAvoid`(−30), ×2 si 1360 |
| DespoiledGround(28) | tile-effect 1476(0x5c4) + trait 2026 / 26\|1006 | `ChaosAffectedUnit`(−5) / `ImperialAndXenosAffectedUnit`(−25) |
| SummonDislikeDoorOpening(29) | affected + porte fermée | `Dislike`(−50) |
| HeroLikeDoorOpening(30) | hero (trait 16/0x10) | hardcodé −50 si porte fermée (A) ; (10−coûtChemin)×10 (B) |
| Phantasm(60) | effet 1279(0x4ff) + phantasme ami adj | `Phantasm_AvoidFriendlyPhantasm`(−40) |
| EchoesFromTheWarp(58) | effet 1284(0x504) + ghost ami adj | `GhostTile`(+10) |
| DoctrinaImperatives/AttractMechanicals(57) | trait 5 + voisin ability 1118(0x45e) | `Marshal_AttractMechanicals`(+10) |
| DecoysAndMisdirection(64) | faction 15(0xf) + steppable(trait27) non-ennemi | `..._FriendlyGSCLikeDecoys`(+75) par ami trigger 1304(0x518) |
| KustomForceField(20) | `ATriggeredAbilityUtility` (count×poids) | +20 × count(amis adj R1 ability 1102/0x44e) |
| DefenderOfTheGreaterGood(21) | unité arme-à-distance | +25 × count(amis R1, R2 si faction9, ability 1155/0x483) |
| SaviorProtocols(22) | faction9 & !ability1120 | +20 × count(amis adj R1 ability 1120/0x460) |
| BioMinefield(61) | cible ability/effet 1315(0x523) | **−100 × hexdist**(candidate, cible) |
| MasterOfTheTutelaries(62) | cible 1096(0x448), trait 2026\|1019 | **−20 × hexdist**(candidate, cible) |
| UnitEffects Adjacent/Surrounding/Ranged(10/11/12) | amis R1/R1/R2 | Σ poids[`EffectType.ToString()`] (clés dynamiques) |
| RangedAdjacentEnemy(15) | — | =0 dans Default (clé `HasAdjacentEnemy` absente) |
| TriggeredAbilities(2)/NonOwner(4)/UnitSpecificBehaviours(3) | — | **dispatchers** -> `LoadPlaybook(...)` (moteur Playbook séparé, voir `playbooks.md`) |

**Statut** : 26/26 formules validées OFFLINE = valeurs BC attendues. Les leaves sont
**DORMANTES** (rendent 0) tant que la metadata par-tuile/trait n'est pas plombée — c'est la
dégradation native exacte (régression nulle prouvée : seed-777 a 0 tuile temporaire/
territoire -> seul TemporaryTile actif, inerte, scoring byte-identique).

## 5. Énumération des tuiles atteignables (pathfinding natif)

Flood-fill par niveaux (cf. §1). Prédicat d'arête `WalkPathfinder.IsValidPathNode`
@180f2ee50 (entrer sur `to` depuis `from`) :

- `IsWalkable(to)` (@180ec6fc0) ;
- `|elev(to)−elev(from)| ≤ 1` (`IsReachableElevationDifference` @180f2ed80 = `abs<2`,
  **symétrique** ; exception paires de téléporteurs) ;
- `!UnitIsBlockedByEnemyUnit(to, unit)` (@180f2ef50) : un **ENNEMI** bloque le passage ;
  un **ALLIÉ laisse passer** (traversable, pas d'arrêt) ; ennemi avec trait `0x1b` laisse
  passer.

**Tuile d'ARRÊT** = `GetTileBlockingReasons==0` (`IsValidContinuePathTile` @180f2ee30) =
NON occupée (ni allié ni ennemi). La tuile courante (start) est exclue du set.

- **Portée** `MovementRangeWithAppliedBonus` @18109cdc0 = stat Movement
  (`StatComponent.CurrentValue`) `+ GetRangeBonusForUnit − Σ réductions`, plancher 0 ;
  **0 si enraciné** (trait `0x418` / triggered `0x4b8`).
- **Type pathfinder** `GetPathfinderTypeForUnit` @18109a7b0 : `Walk(0)` défaut, `Fly(3)` si
  `IsLikeFlying`, 6–13 = blink/téléport (effets `0x40b/0x474/0x4d6/9999`). Cas IA normal =
  Walk.
- `GetEffectiveDepth` (hazard -> `Min(1,depth)`, @180f2e920) = non plombé (pas de hazard
  board basique).

## 6. Capture live — RPC `boardGraph` + validation

RPC `boardGraph` (`rpc-view.ts`, read-only) dumpe par tuile `{id,col,row,elevation,isWall,
walkable,neighbours[],occupantUnitId}` :

- `walkable` = `BattleQuery.IsWalkableTile(tile)` (≠ isWall : une tuile walkable=False
  isWall=False observée -> walkable natif = le vrai signal, pas isWall) ;
- `neighbours` = `BattleQuery.GetAdjacentTiles(tile,true,true,true)` (cf.
  `GetFreeAdjacentTiles` @181061650) ;
- élévation = PositionComponent@0x18 (`GetCoordinates` @180ec4e40 : col@0x10,row@0x14,
  elev@0x18) ; occupance via `UnitFootComponent` (UnitId@0x10, TileId@0x14).

**Résultat de validation** (`pathfind_validate.py` vs `aiMovableTiles`, seed 777, 7×9=63
tuiles) :

- **L'adjacence native `GetAdjacentTiles` est LOSSY** : asymétrique (~18 arêtes one-way),
  (0,0) renvoie 0 voisin -> modes `native`/`native_sym` échouent (1–2/5).
- **L'adjacence hex EVEN-Q est fidèle** (parité par COLONNE, VÉRIFIÉE sur les tuiles à 6
  voisins : col pair -> `(-1,0)(-1,1)(0,-1)(0,1)(1,0)(1,1)` ; col impair ->
  `(-1,-1)(-1,0)(0,-1)(0,1)(1,-1)(1,0)`). -> **WalkPathfinder 4/4 EXACT** sur toutes les
  unités WALK (u88/u90/u92/u94) à leur **stat Movement réelle** (3/3/3/4 via
  combatSnapshot). Les murs sont une propriété de tuile (walkable), PAS une arête manquante.
- **u96 (darkaTerminator) = non-Walk, détecté (pas un bug)** : stat Movement 2 mais atteint
  47 tuiles -> impossible en Walk. `TeleportStrike_TeleportingIn` actif ->
  `GetPathfinderTypeForUnit` renvoie un type téléport. Le harnais le détecte (portée
  effective en pas de marche > stat Movement => Fly/Teleport/range-bonus, exclu du score
  Walk). `aiMovableTiles` (défaut) = RAW `GetMovableTilesFor` (pas de filtre danger-zone).

## BLOQUÉ / RESTE

- **A\* (chemin exact) non réimplémenté** (`WeightCost` @180f2f120) — capté via RPC
  `pathDistToEnemies`, pas porté en Python pur.
- **Fly / ATeleportPathfinder non portés** (u96-like) ; mapper l'id d'effet TeleportStrike
  ↔ type pathfinder reste à faire.
- **`MovementRangeWithAppliedBonus`** : bonus / réductions / enraciné non plombés (portée =
  stat Movement brute pour l'instant).
- **`Elevation` no-data** dans `decisionView` (scoring proxy) ; faithful via `tileMeta`.
- **`MaxDistanceToUnitTile`** : terme GATÉ OFF, et la **tuile de référence** réelle du
  décideur `UnitMovementFromTemporary(5)` n'est pas encore RE'd / câblée.
- **Leaves Tile(7) DORMANTES** : plumbing par-tuile/trait à exposer (is_territory /
  tile-effect-type-ids / occupant / door / pending-summons / voisinages-amis + traits /
  abilities / faction).
- **`GetEffectiveDepth` (hazard)** non plombé.
- **Câblage moteur playbook** : les dispatchers Tile(7) (TriggeredAbilities / NonOwner /
  UnitSpecificBehaviours) renvoient vers un moteur Playbook séparé (voir `playbooks.md`).

## Liens

- `architecture.md` — vue d'ensemble du moteur playbook (couches select/utility/leaves).
- `scoring.md` — termes d'utilité d'attaque & sélection d'action.
- `prediction.md` — prédiction de dégât consommée par le scoring.
- `playbooks.md` — playbooks par-ability (dispatchers Tile(7)).
- `status.md` — état d'avancement & agreement live.
