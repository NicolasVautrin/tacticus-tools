# Scoring — la formule d'utilité, les poids, les composites

But : décrire l'état faithful ACTUEL du scoreur de l'IA playbook — comment une action
(attaque / heal / effet / repair / move) est convertie en un score Fix64 unique, quels
poids l'alimentent, et comment les composites s'assemblent. Frères :
[architecture](architecture.md) · [prediction](prediction.md) · [pathfinding](pathfinding.md) ·
[playbooks](playbooks.md) · [status](status.md).

---

## 1. Le scoreur unifié — `ComparablePlaybook.CalculateActionUtility` @181406ee0

Toute action comparable (attaque / heal / effet / bannière / move) est scorée par **UNE
seule** fonction, en **UNE seule devise** Fix64 :

```
U(action) = CalculateUtilityFromPredictions(action)          # Σ dégât + Σ heal + Σ effet + Σ repair
          + [si gate caster-pos +0x328] Weight[54].Eval(casterBase)   # terme POSITION du caster (secondaire)
          + CalculateUtilityFromTilePrediction(action)       # utilité de la TUILE d'arrivée (Weight[Tile=7])
```

- Eval **déterministe** : `BasePlaybook.Evaluate` enveloppe d'un `SetDisallowRandom`.
- `cfg` = config de la playbook (`playbook.<config>@0x20 -> .<UtilityWeights>@0xc0`), qui
  dérive de **`BattleConfiguration.Utilities`** (poids statiques, déjà dans les archives JSON).
- L'utilité CUSTOM par-ability existe via le virtuel `+0x338` (override par playbook),
  pondéré par `cfg+0x340` — c'est le canal des knobs `ActiveAbilities.<Name>` (cf. §3).

### `CalculateUtilityFromPredictions` @181407890

Somme, par famille de prédiction (les prédictions viennent du moteur natif
`DamagePredictionQuery.GetAllPredictions`, déjà exposé par le hook `aiPredict`) :

| Famille | terme |
|---|---|
| Dégât  | `Σ proba × Weight[Damage=34].Eval(UtilityAttackCase.ForDamagePrediction(ev))` |
| Heal   | `Σ Probability × Weight[Heal=44].Eval(ForHealPrediction(tgt, healPred))` |
| Effet  | `Σ proba × Weight[AddedTileEffects=45].Eval(ForEffect(0x2d))` (+ 2ᵉ passe `× proba`) |
| Repair | `Σ Weight[Repair=46].Eval(ForRepairPrediction(0x2e))` |

> ⚠ Les `UtilityAttackCase.For*` (@181104fb0 / @181105420 / @181105260) **ne sont PAS les
> scoreurs** : ce sont des **constructeurs** (`memset 200o` + alloc + remplissage de champs)
> d'un objet `UtilityAttackCase` portant les inputs. Le score réel = `Weight_k.Evaluate(caseObj)`
> via les helpers gshared `FUN_180006940(…, playbook.weights@0x40, k)` (récupère le poids
> d'index `k`) puis `FUN_180003bd0(5, …)` (invoke `Evaluate`). `Weight_k` = une **config
> Utility nommée** de `BattleConfiguration.Utilities.Default`.

---

## 2. Mapping `UtilityType` -> indices de poids

Indices lus dans le décompilé :

| UtilityType | id | note |
|---|---|---|
| Tile | 7 | composite (29 él, cf. §4) |
| Damage | 34 | **composée** (13 él, cf. §4) |
| DamageDealt | 35 | magnitude dégât brut (cf. §3.1) |
| KillUnit | 36 | |
| OverkillUnit | 37 | |
| Heal | 44 | |
| AddedTileEffects | 45 | |
| Repair | 46 | |

`Damage(34)` étant composée, son `Eval` = somme de ses sous-utilités (dont KillUnit /
OverkillUnit configurées + DamageDealt magnitude).

---

## 3. Les poids — `BattleConfiguration.Utilities.{Default, MovementSuggestion}`

Config **NOMMÉE** (pas des offsets) → `engine/weights.py` la charge telle quelle depuis
`data/arena-battle-config-newtonsoft.json`. Deux profils : **`Default`** (~54-55 catégories,
toutes non-null) et **`MovementSuggestion`**.

Valeurs clés (Default) :

| Catégorie | valeurs |
|---|---|
| `KillUnit` | PossibleKill **50**, DefinitelyKill **100** |
| `OverkillUnit` | Possible **15**, Definite **40** |
| `AddedTileEffects` | SpiderWeb 10, Fire 10, Ice 5, Unit_on_* 15/15/0 |
| `AttackTargetWithEffect` | ArmourOfShriekingSouls 20 |
| `Elevation` | HighestElevation 10, LowestElevation −5, Multiplier 10 |
| `MinDistanceToClosestEnemy` | PerTileDistance −100 |
| `MaxDistanceToUnitTile` | ClosestTile 400, FarthestTile 700 |
| `MaxDistanceToEnemies` | ClosestEnemy 10, FarthestEnemy 100 |
| `DislikeBoss` | 80 · `DislikeObjects` 50 · `EnemyOnTerritoryTile` 10 |

Autres familles présentes : position (`MaxDistanceToEnemies`, `MinDistanceToClosestEnemy`,
`Elevation`, `DislikeStartingTilesUtility`…), effets (`TileEffects`,
`UnitEffectsAdjacent/Ranged/Surrounding`), ordre intra-tour (`UnitOrder` = poids de
`PickNextUnit`), triggers/overwatch (`TriggeredAbilities`, `TriggeredAbilitiesNonOwner` =
levier anti-overwatch-suicide), et les knobs custom par-ability `ActiveAbilities.<Name>`
(ex. `ArcScourge_AdjacentEnemies:20`, `TwistedScience_ExtraDamageUtility:100`,
`PlagueburstMortar_AdjacentEnemy:10`) que lisent les leaves NonComparable.

> Surcharge « par-poids » = patcher une clé de ce dict, 0 code. La validation Fix64 reste
> sur l'**argmax** (la décision), pas la valeur exacte.

### 3.1 Barème de dégât FIDÈLE (RE'd, pas un knob)

`DamageDealt` (UtilityType 35) = `IdunBattle.AI.Utilities.DamageUtility`. Son `.cctor`
(@1810cf2e0) pose 2 constantes statiques : **`W_damage = Fix64(0x50) = 80`**,
**`W_remaining = Fix64(0x14) = 20`**. Formule
(`<EvaluateAttackInSteps>d__2.MoveNext` @1810e2280) :

```
dmg         = Avg(healthMinMax) + Avg(shieldMinMax)            # dégât moyen prédit (santé + bouclier)
combinedMax = (target.MaxHealth + 1) + (target.Shield + 1)
u_damage    = Clamp(dmg / combinedMax, 0, 1) × 80             # FRACTION des PV max × 80
u_remaining = (1 − Clamp((remaining − dmg) / combinedMax, 0, 1)) × 20   # finir les blessés
u           = u_damage + u_remaining ;  ×(−1) si friendly-fire
```

⇒ le terme dégât est une **fraction [0,1] des PV max × 80** (≈ [0,100] pour une cible
pleine), **PAS des milliers bruts** — même ordre de grandeur que `KillUnit` (50/100). Un
kill DOMINE donc naturellement (KillUnit 100 + DamageDealt ≈ 100), sans facteur ad-hoc.

- `KillUnitUtility` @1810e1a90 : `+ (WillBeKill→DefinitelyKill 100 / MightBeKill→PossibleKill 50)`, ×(−1) friendly-fire.
- `OverkillUnitUtility` @1810e1ed0 : `+ DefinitelyOverkill 40 / PossibleOverkill 15` (ADDITIONNÉ).

> `Damage`, `DamageDealt`, `Heal`, `Tile`, `Repair` sont **ABSENTES** du dict BC : leur
> `IUtility` est un comportement hardcodé/par défaut (pas de courbe BC) — typiquement une
> magnitude (échelle ≈ PV/dégât brut).

---

## 4. Les composites — `_composedUtilityLookup` (`UtilitiesDatabase.InitializeUtilities` @1810C9390)

Deux dicts construits : `_composedUtilityLookup` (composites → tableau d'enfants `UtilityType`)
et `_utilitiesBuilder` (**70 builders** `UtilityType → classe *Utility`, registre complet).
Offset du dict = **88 = 0x58** (`Dictionary<UtilityType, UtilityType[]>`), lu en runtime via
le RPC `dumpComposedUtility` (`frida/hooks/features/dump-composed.ts`, capture via
`DefaultGroupOperator..ctor` arg[4]). Composition (ground truth runtime, session 8 seed 777) :

```
Damage(34) [13] = OnlyImperviousUnitIfCanBeDamaged(40) · DamageDealt(35) · KillUnit(36) · DislikeObjects(38)
                · DislikeBoss(43) · DislikeEnvironmentUnits(39) · OverkillUnit(37) · EnemyOnTerritoryTile(41)
                · TriggeredAbilities(2) · TriggeredAbilitiesNonOwner(4) · UnitSpecificBehaviours(3)
                · OptimizedGait_AdjacentFriends(59) · AttackTargetWithEffect(42)
Tile(7) [29]    = Elevation(8) · TemporaryTile(13) · TileEffects(9) · UnitEffectsAdjacent(10)
                · UnitEffectsSurrounding(11) · UnitEffectsRanged(12) · RangedAdjacentEnemy(15) · SteppableUnit(19)
                · CapturePoint(24) · TriggeredAbilities(2) · TriggeredAbilitiesNonOwner(4) · UnitSpecificBehaviours(3)
                · KustomForceField(20) · DefenderOfTheGreaterGood(21) · SaviorProtocols(22) · TilePendingBlockableSummon(14)
                · PowerUp(26) · DoctrinaImperatives(57) · Phantasm(60) · EchoesFromTheWarp(58) · Contaminated(25)
                · MoltenForm(23) · BioMinefield(61) · MasterOfTheTutelaries(62) · DecoysAndMisdirection(64)
                · DespoiledGround(28) · SummonDislikeDoorOpening(29) · HeroLikeDoorOpening(30) · EnvEndBombardment(31)
Repair(46) [3]  = RepairedAmount(47) · TriggeredAbilities(2) · TriggeredAbilitiesNonOwner(4)
Spawn(0) [2]    = Tile(7) · SingleAdjacency(1)
MovementSuggestion(32) [2] = Tile(7) · TileDistance(33)
UnitMovement(6) [2]        = Tile(7) · MinDistanceToClosestEnemy(16)
UnitMovementFromTemporary(5) [2] = UnitMovement(6) · MaxDistanceToUnitTile(17)
```

Décodage :

- **Damage** : dominants = `DamageDealt(80/20) + KillUnit(100/50) + OverkillUnit(40/15)` (§3.1) ;
  les 10 autres = modificateurs SITUATIONNELS (poids BC connus : DislikeBoss 80, DislikeObjects
  50, AttackTargetWithEffect 20, EnemyOnTerritoryTile 10, OnlyImpervious = gate, knobs traits
  Triggered/UnitSpecific) → 0 sur une attaque basique d'unité. Le barème « 3 feuilles » est
  donc une bonne 1ʳᵉ coupe.
- **Tile(7) ne contient AUCUNE distance.** Les distances sont des leaves séparées :
  `UnitMovement = Tile + MinDist(16)`, `UnitMovementFromTemporary = UnitMovement + MaxDistToUnitTile(17)`.
  **`MaxDistanceToEnemies(18)` n'est dans AUCUN composite** (leaf standalone). ⇒ le
  `MaxDistanceToUnitTile(17)` (400/700, gaté OFF dans `move.py`) n'est PAS dans
  `MovementSuggestion` — **le défaut `off` est CONFIRMÉ par ghidra**, pas un coup de chance A/B.

---

## 5. État du portage des leaf-utilities (`engine/utilities/`)

Une fonction par UtilityType, portée depuis son `*Utility.<Evaluate*InSteps>d__N.MoveNext`
ghidra + poids BC.

- **Damage(34) — PORTÉ + VALIDÉ (défaut)** : `engine/utilities/damage.py` =
  `DamageDealt(35, 80/20) + KillUnit(36, 100/50) + OverkillUnit(37, 40/15 additionné)`.
  `ENGINE_DAMAGE_MODEL=faithful` par défaut. maxHP cible via `observeBattle` (clé squadId).
  Parité legacy : seed 777 (60/80/100) + 2024 (45/65/100), zéro régression.
  > Résolu : `kill`/`killSure` (WillBeKill/MightBeKill) sont au niveau RÉSULTAT d'`aiPredict`,
  > pas dans `pred` → KillUnit ne voyait jamais le kill. Fix = ré-injecter dans `pred`.
- **Tile(7) — PORTÉ (formules)** : `engine/utilities/tile.py` (registry 29 feuilles). RE'd :
  `Elevation(8)` = `Multiplier(10)×elev + HighestElevation(10 si max) + LowestElevation(−5 si min)`
  (@1811019a0) ; `SteppableUnit(19)` = Enemy 50 / Friendly −50 / FriendlyDecoy −50 / EnemyDecoy 1
  (@1810f9850) ; `TileEffects(9)` partiel = Σ poids BC des effets de statut (@1810fbe50). Les 26
  autres = STUBS=0 (situationnels, =0 en bataille basique, fidèle).
- **Distances — RE'd, à porter dans `utilities/`** : `MaxDistanceToUnitTile(17, 700−300/d réf=tuile
  courante)`, `MinDist(16)`, `MaxDistEnemies(18)`, `RangedAdjacentEnemy(15, −50 si ranged+adjacent)`
  (actuellement dans `move.py`).
- **Plumbing élévation FAIT + VALIDÉ** : RPC `tileMeta` (`rpc-view.ts`) =
  `projectMatchState(state,{includeTiles:true}).tiles` → `[{col,row,elevation,isWall,isTemporary,
  isTerritory}]` (TileComponent). E2E seed-777 : u88 tuile élév=2 → 15 (`10×2−5`), élév=3 → 40
  (`10×3+10`). Elevation produit des valeurs différenciées par tuile.

---

## 6. BLOQUÉ / RESTE

- **Prédiction heal & effet à la SOURCE** : `aiPredict` = `GetAllPredictions` = query de DÉGÂT
  seulement (pas d'effets/heal). Scorer fidèlement offline une ability à EFFET (terme
  `AddedTileEffects=45`) ou à HEAL (terme `Heal=44`) est **bloqué à la source de prédiction**.
- **Dégât BOUCLIER** : `Avg(shieldMinMax)` de la formule DamageDealt n'est pas exposé par
  `aiPredict` (santé seule) — terme manquant dans `engine/utilities/damage.py`.
- **10 leaves situationnels du composite Damage(34)** : DislikeBoss/Objects/Env,
  AttackTargetWithEffect, OnlyImpervious, knobs Triggered/UnitSpecific — non portés (=0 en
  bataille basique, mais à porter pour fidélité complète).
- **26 leaves Tile(7) en STUB=0** : nécessitent une METADATA PAR TUILE
  (`{effects[], steppable, occupant, decoy}`) non encore exposée (`tileMeta` ne couvre que
  élévation/wall/territory) → plumbing RPC tuile à enrichir avant évaluation/validation.
- **Tableaux statiques `InitializeArray`** : les blobs `Tile(29)` / `Damage(13)` sont des
  `RuntimeHelpers.InitializeArray(arr, DAT)` ; `read_bytes(DAT)` rend un token de métadonnée,
  pas les ints. Composition désormais lue en runtime via `dumpComposedUtility` (cf. §4) — mais
  les **signes/poids `WeightedUtility.Weight` par feuille** des composites restent à extraire.
- **Décideur de move** : trancher `UnitMovement` (Tile+MinDist) vs `MovementSuggestion`
  (Tile+TileDistance) par l'agreement ; intégrer `tile_composite` au scoring de move et virer
  `MaxDistEnemies` (hors-composite). Gate `ENGINE_MOVE_VS_ATTACK` laissé OFF (utilise `best[0]`,
  pas le composite Damage, donc NON FIDÈLE).
- **Validation** = agreement sur l'**ARGMAX** (Fix64), pas sur la valeur exacte.
