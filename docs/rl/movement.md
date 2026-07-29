# Mouvement special — Fly & Deep-strike (RE + port)

RE ghidra gqfc5mff6c. Deux mecaniques de mouvement hors-Walk : **Fly** (traverse
ignorant terrain/unites) et **Deep-strike / TeleportStrike** (deploiement differe :
l'unite teleporte-in, non-ciblable + auras off, puis atterrit).

## 1. FLY — FAIT + valide live

### Predicat « comme volante »
`UnitExtensions.IsLikeFlying @180ed88b0` :
```
IsLikeFlying(u) = BaseUnitComponent.HasTrait(4=Flying) OR HasTrait(0x13=19=Burrow)
```
(enum `UnitTrait` : 4=Flying, 19=Burrow ; les deux volent). Le port lit les NOMS de
trait gameconfig (`Flying`/`Burrow`).

### Pathfinder
Le natif choisit le pathfinder par unite via dispatch virtuel `MovementQuery.GetReachableTiles
@18109b380` (WalkPathfinder / **FlyPathfinder** / TeleportStrikePathfinder).

- `FlyPathfinder.IsValidPathNode @180f1b2e0` (TRAVERSE) : teste UNIQUEMENT deux flags
  intrinseques de la tuile (`tile[+0x40]==0 AND tile[+0x41]==0` = non-unplayable ET non-mur ;
  `+0x41`=mur confirme via `IsAnyAdjacentTileWall @180f1b010`). **AUCUN test d'elevation,
  AUCUN blocage par unite** (vs Walk = `IsWalkable + |Delta elev|<=1 + !BlockedByEnemy`).
  -> le vol ignore l'elevation ET traverse par-dessus allies ET ennemis ; ne peut pas entrer
  sur un mur/injouable (= `walkable=False` cote board capte).
- `FlyPathfinder.IsValidFinalTile @180f1b2a0` (ARRET) : `!IsTemporary AND IsWalkable` = tuile
  passable non-temporaire NON occupee. Meme regle d'arret que Walk (les tuiles visitees sont
  passables par construction -> « non occupee » suffit).
- PORTEE (nombre de tuiles) = stat Movement, IDENTIQUE a Walk (le vol change la TRAVERSEE,
  pas la portee).

### Port
`engine/entities/pathfinding/fly_pathfinder.py` : `is_like_flying(traits)`,
`is_valid_path_node` (arete fly = `board.walkable(to)`), `get_movable_positions` (BFS partage
de walk_pathfinder avec l'arete fly). `walk_pathfinder.get_reachable_levels/get_movable_positions`
parametres par un predicat `edge` (defaut = walk) -> mirror natif `BasePathfinder` (BFS generique,
chaque pathfinder override `IsValidPathNode`). Selection fly/walk par trait dans
`state_bridge._move_tiles` (mirror du dispatch `GetReachableTiles`).

⚠ `_pathdist_to_enemies` ne fait PLUS partie de ce dispatch (`#17-off`, 2026-07-29) : la distance de
SCORING de `MinDistanceToClosestEnemy(16)` passe par `IPathfinders.GetPath(1, ...)` avec **`1` en
LITTERAL**, meme pour un flyer -- et l'entree `1` du dictionnaire de `Pathfinders$$.ctor` n'est ni le
Walk ni le Fly, mais `IdunBattle.Entities.Pathfinding.IgnoreTerrainPathfinder` (aucun test
d'occupant, `WeightCost = 10 + IsFilled`, PAS d'elevation dans le cout). Port :
`engine/entities/pathfinding/ignore_terrain_pathfinder.py`. **Distance de MOUVEMENT (ce que l'unite
peut parcourir) != distance de SCORING (ce que l'IA note)** : l'IA score une proximite qu'elle ne
peut pas forcement atteindre. Detail + mesures : `case-52-generalisation.md` §#17-s5.5.

### Validation live (test_fly_pathfinder_live.py, non commite)
Roster Flying explicite (`blackHaarken,thousAhriman,tyranWingedPrime`) sur board a CLIFF
(`C3_59`, |Delta elev|>=2). Cas DISCRIMINANT obtenu : `u88 blackHaarken` natif=17, **fly=17
EXACT**, walk=15 (le walk rate 2 tuiles bloquees par le cliff que le fly/natif atteignent).
Agrement fly==natif sur les 3 flyers ; garde de discrimination (>=1 flyer avec fly!=walk).
Aucune regression walk (test_pathfinding_live 3/3).

## 2. DEEP-STRIKE / TeleportStrike — FAIT (runner-engine) + valide live

### Trait + ability
- Trait `TeleportStrike` (enum UnitTrait **2020**) = marque l'unite deep-striker.
- Ability `TeleportStrike` (AbilityOrEffect **1037** = 0x40d), triggered/passive.

### Cycle de vie (RE)
- `TeleportStrikeAbility.CreateTrigger @180e3db30` : fire sur `OnOwnerSpecificAbilityInit(1037)
  AND UnitTurnsStarted == [const +0xb8] AND NOT HasFlag AND NOT IsSpawnedByRoomReveal`
  (= a l'init, avant que l'unite ait joue son tour).
- `TeleportStrikeAbility.CreateBehaviour @180e3daa0` : `AddEffect(0x40b=1035
  =TeleportStrike_TeleportingIn, duree=TurnsFromRounds(1)=1 round)`.
- `TeleportStrike_TeleportingInEffect` (@180f70f30) **herite de `BlockUnitMovementEffect`**
  (bloque le move). `GetMovingEffectType` -> 0x40c=1036 (TeleportStrike_Moving).

### Non-ciblable
`UnitExtensions.IsTargetable @180ed8ff0` = `!HasFlag(0x11=17)` (flag UnitFlagsComponent).
`UntargetableEffect.ApplyInternal @180f47fd0` = `UnitFlagsComponent.Add(0x11)`. Le
`BlockUnitMovementEffect.ApplyInternal @180f35e30` ne pose PAS ce flag -> le « non-ciblable »
du deep-strike vient d'un flag 0x11 pose separement (pas par le block-move seul).

### GROUND TRUTH live (probe eldarAutarch + eldarRanger, runner)
- L'unite deep-strike est **POSEE ON-BOARD** avec position (Autarch @(1,0), Ranger @(0,0)) —
  PAS absente.
- Elle porte **`TeleportStrike_TeleportingIn` (effectType 1035) `remaining:2`** (2 tours = 1 round).
  (un Terminator ennemi darkaTerminator l'avait aussi.)
- **Ses passifs/auras ne sont PAS appliques pendant le teleport-in** : l'Autarch n'a QUE
  TeleportingIn -> **AUCUN effet PathOfCommand (1112/1107)**. Les passives s'initialisent a
  l'ATTERRISSAGE (quand TeleportingIn expire). => aura off = automatique cote offline (aucun
  effet d'aura present a lire).

### GROUND TRUTH du LANDING (probe ds_landing, tour par tour)
Timing PRECIS : le deep-strike atterrit a la FIN de son 1er tour d'equipe (evenement DISCRET,
PAS un tick de duree — malgre `remaining:2`) :
| etape | Autarch | Ranger (allie Aeldari adj.) Attack |
|---|---|---|
| INIT (tour Autarch actif) | `TeleportingIn` rem:2, AUCUN PathOfCommand, non-ciblable | 4518 |
| fin du 1er tour (endturn) | TeleportingIn PARTI + `PathOfCommand_ExtraDmg/ExtraCrit` AJOUTES | **5217 (+699)** |
Le +699 = aura PathOfCommand (meme faction Aeldari = extraDmg+extraDmg_2) -> valide AUSSI la
magnitude PathOfCommand ExtraDmg (#63).

**FIX PathOfCommand `IsSameFaction` (gate extraDmg_2) = FACTION, PAS grande-alliance** : discriminateur
live Autarch + allie Aeldari (Ranger) + allie Orks (Nob), TOUS dist=1 : Ranger (Aeldari) delta=**699**
(extraDmg+extraDmg_2), Nob (Orks=Xenos MAIS pas Aeldari) delta=**400** (extraDmg SEUL). Donc l'Ork,
meme grande-alliance (Xenos), NE recoit PAS extraDmg_2 -> `IsSameFaction`=FactionId (cf. `HasFaction
@180ed6450`), PAS GrandAllianceId. Le port utilisait a tort la grande-alliance -> CORRIGE (loki.py
`owner_faction==att_faction` ; carrier 8-tuple threade la FactionId ; prediction.py/effects/__init__.py).
Offline post-fix == live EXACT (Ranger 699, Nob 400). (⚠ DIFFERENT de RitesOfBattle = grande-alliance
Imperial, inchange.)

### Port (runner-engine) — FAIT
- **Ciblage** : `state_bridge._is_untargetable(state,uid)` = `state.effects.has_effect(uid, 1035)`
  (signal deep-strike ; mirror `IsTargetable=!HasFlag(0x11)`). Exclut les teleporting-in de
  `ability_targets_offline` (enemy/ally) + des plans d'attaque (`tgt_enemies`). `enemies` reste
  complet pour le POSITIONNEMENT (l'unite occupe le board). (Portee NARROW = deep-strike ; les
  autres sources d'untargetable = flag natif via hooks, non porte -> follow-up.)
- **Landing** (`turnflow.EndTurnOperation`) : les unites TeleportStrike du joueur FINISSANT
  atterrissent -> `spawn.land_deep_strike(state,uid)` : consomme `TeleportStrike_TeleportingIn`
  + `InitializeActorAbilities` (owner-effects des abilities+traits = init des passives deferrees :
  `_seed_ability_owner_effects` via `ABILITY_INIT_OWNER_EFFECTS["PathOfCommand"]=["PathOfCommand_ExtraDmg"]`
  + `_seed_trait_owner_effects` + derived). -> ciblable + aura projette.
- **Init** : les unites initiales sont seedees depuis capture (`snapshot.load_state`) -> heritent
  TeleportingIn + passives deferrees (correct, aucun code from-scratch requis).
- **Aura off** pendant teleport-in : automatique (aucun effet d'aura present tant que non-atterri).
- ExtraCrit (1107, axe crit) NON porte (canal aura-crit dedie = TODO).

### Validation OFFLINE vs LIVE (test_deep_strike_live.py, non commite)
`load_state`(capture teleport-in) -> pre-landing: untargetable=True, aura Ranger=0 ; apres
`EndTurnOperation`: untargetable=False, `PathOfCommand_ExtraDmg` pose, **aura Ranger offline = 699
== delta d'Attack live across l'endturn**. EXACT. Guards verts (turnflow/summon/pathfinding/playbook).
