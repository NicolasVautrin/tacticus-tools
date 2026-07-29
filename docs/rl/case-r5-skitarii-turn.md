# case-R5 — `test_skitarii_turn_live::test_skitarii_played_by_generic_ai_pass` : la passe IA générique choisissait une tuile de déplacement ILLÉGALE

**Statut : FERMÉ (2026-07-27).** Une seule cause pour les deux anomalies mesurées ; la troisième
(« `ability: 17` ») est **réfutée** comme cause.

## 1. Le rouge

Reproduit à l'identique sur 4 commits (`e972c99`, `1930824`, `018fee1`, `5da0c31`) :

    res = {'moved': (6,5), 'kind': 'ability', 'ability': 17, 'target': 79}
    d_bfs 3 -> 3
    hp 8536 -> 8536
    atk(ranged=True, hits=3)

Trois anomalies apparentes : (1) le move ne réduit pas la distance BFS, (2) 3 coups infligent 0
dégât, (3) l'ability est le `NormalAttack` ABSTRAIT (17) et non l'id concret par unité.

## 2. L'oracle natif (ce qui manquait au dossier)

Le test spawne le Vanguard **offline** (`_spawn_config_grot`) : aucun oracle natif n'existait pour sa
DÉCISION. `probe_r5b_vanguard_native.py` en fabrique un — le Vanguard REEL est amené dans le runner
LIVE en faisant attaquer son summoner (`admecMarshall`, passif `ControlEdict` sous
`ProtectorImperative`), puis on reproduit la géométrie EXACTE du test (Vanguard (3,7), ennemis
intacts (6,8) et (6,7), tous deux à hex 3) et on rend la main : au **turn-start de ma team** le trait
`Summon` fait jouer l'unité toute seule.

| | tuile choisie | cible |
|---|---|---|
| **NATIF** (turn-start, runner live) | **(4,7)** | **77** (celui de `_pick_enemy`), −1734 PV |
| **PORT** (avant fix) | (6,5) | 79 |

⇒ **le TEST avait raison** : la cible attendue est bien celle qu'il mesure. Ce n'était ni un test
sur-spécifié, ni un flake.

## 3. Décomposition par étage

`probe_r5c_tile_stage.py` décompose sur un porteur ÉQUIVALENT et interrogeable (`admecMarshall` :
même `move=3`, même jeu d'armes melee Physical + Toxic r2 ; le summon, lui, joue TOUT SEUL au
turn-start et ne peut donc jamais être interrogé avec son action disponible).

**Étage 1 — tuiles de déplacement** (`aiMovableTiles` = `MovementQuery.GetMovableTilesFor`), board
`MC1_67`, origine (3,7), portée forcée 1/2/3 :

| portée | natif | port AVANT | tuiles en trop |
|---|---|---|---|
| 1 | 6 | 6 | — |
| 2 | 16 | 17 | (5,6) |
| 3 | 25 | **27** | (0,5), (6,5) |

**(6,5) est exactement la tuile que la passe IA choisissait.** Elle n'est à portée d'attaque QUE de
l'ennemi 79 → d'où le changement de cible, d'où « l'ennemi mesuré ne perd pas de PV ».

**Étage 2 — dégât prédit par tuile** : `aiPredict(col,row)` rend 1968–2953 pour le Marshall, le port
rend 1968–2953 sur les tuiles plates ⇒ **aucun écart** sur cet étage. (⚠ `aiPredict` n'est PAS
sensible à la position — il rend la même valeur depuis une tuile hors portée — donc il ne décompose
PAS le bonus d'élévation.)

## 4. Cause racine (décompile)

`IdunBattle.Entities.Pathfinding.BasePathfinder$$NodesInNextLevel` commence par :

    if (currentTile != startTile && !vslot0x1d8(this, unit, currentTile))
        return <liste vide>;                       // aucun voisin -> CUL-DE-SAC

`vslot0x1d8` = `IdunBattle.Entities.Pathfinding.WalkPathfinder$$IsValidContinuePathTile` =
`GetTileBlockingReasons(tile, unit) == 0`. Le masque de
`IdunBattle.Entities.Pathfinding.WalkPathfinder$$GetTileBlockingReasons` :

- **bit 0x1** : une ENTITÉ d'effet de tuile de kind 0 (`BlockEnteringUnitsTileEffect`), sauf si
  l'unité porte un trait de
  `idun.…StaticBattleRules.StaticBattleRules.Effect$$NotBlockingMovementOfTraits` — lu verbatim :
  `{0, 5, 0x11} -> [0 Mounted, 0x405 Vehicle, 0x412 Unstoppable]` ; `0x3a -> [0x1d NightVision]` ;
- **bit 0x4** : occupant ENNEMI (déjà porté par `is_valid_path_node`) ;
- **bit 0x2** : « l'hex FINIT le mouvement » (`WalkPathfinder$$GetEffectiveDepth` → `Min(1, depth)`).

Le prédicat d'ARÊTE `WalkPathfinder$$IsValidPathNode` (walkable + `|Δelev| < 2` + `!ennemi`) **ne
regarde PAS l'effet** — c'est pourquoi une tuile block-entering **reste un STOP légal** (vérifié
live : les Swamp de `MC1_67` sont dans `aiMovableTiles`), mais **la flood-fill ne s'étend pas depuis
elle**.

Mesure live `tileMeta` (`MC1_67`) : les tuiles **Swamp** portent
`{name: BlockEnteringUnits, effectType: 0}` **et** `{Thorns_DefenseReduction, 0xb}` dès la
construction du runner (posés par `ThornsBlockMovementAbility$$CreateBehaviour` =
`AddBlockEnteringUnitsEffect & AddStaticStatModifierEffectToOwner(DEFENSE)`).

Sur la géométrie du test, (0,5) et (6,5) ne pendent QUE d'un Swamp : (6,5) n'a qu'un prédécesseur de
niveau 2, (5,6), lui-même atteint uniquement via le Swamp (4,6) ; (0,5) pend du Swamp (1,6).

**⚠ Ce N'EST PAS un blocage de TERRAIN.** La pose de l'effet est CONDITIONNELLE : mesuré le même
jour, `PVP_desert_04` n'a aucune tuile block-entering live. Un port gaté sur `tileDefId == 'Swamp'`
sur-bloquerait ; le port est donc gaté sur l'EFFET.

## 5. Le fix

| fichier | rôle |
|---|---|
| `engine/entities/pathfinding/walk_pathfinder.py` | paramètre `can_continue` sur `get_reachable_levels`/`get_movable_positions` = mirror du gate de `NodesInNextLevel` (le start en est exempt) |
| `engine/entities/pathfinding/tile_blocking.py` (NEUF) | `tile_blocks_entering` / `make_can_continue` = mirror du bit 0x1 de `GetTileBlockingReasons`, lu dans `State.effects.by_unit[tile_entity_id]` |
| `engine/services/static_battle_rules.py` | `not_blocking_movement_of_traits` (mirror verbatim) + `BLOCK_ENTERING_UNITS_EFFECT_TYPE` |
| `engine/entities/pathfinding/fly_pathfinder.py` | thread du paramètre (le gate vit dans `BasePathfinder`, donc partagé ; **quel** `IsValidContinuePathTile` le FlyPathfinder résout n'est PAS établi — l'absence du symbole ne prouve rien, cf. § 8 R5-f) |
| `engine/ai/state_bridge.py` (`_move_tiles`, **3 lignes**) | câblage : la passe IA offline pose le gate |
| `tests/…/test_skitarii_turn_live.py` (`_load`) | passe `tiles=tileMeta` à `load_state` — **sans ce canal `State.effects` ne porte AUCUN effet de TUILE et le gate est un no-op silencieux** |

## 6. Validation

**Agrément par board** (`probe_r5c_tile_stage.py`, `admecMarshall` move 3, portées 1/2/3) :

| board | natif | port AVANT | port APRÈS |
|---|---|---|---|
| `MC1_67` | 6 / 16 / 25 | 6 / 17 / 27 | **6 / 16 / 25** |
| `MC1_64` | 6 / 17 / 34 | 6 / 18 / 35 | **6 / 17 / 34** |
| `C2_26` | 5 / 15 / 29 | 5 / 17 / 33 | **5 / 15 / 29** |
| `C1_47` | 4 / 10 / 24 | 4 / 10 / 28 | **4 / 10 / 24** |
| `PVP_desert_04` | 6 / 18 / 19 | 6 / 18 / 19 | **6 / 18 / 19** (aucune tuile block-entering ⇒ gate inerte) |

Zéro écart dans les DEUX sens, sur les 5 boards.

**Garde** : `tests/engine/entities/pathfinding/test_block_entering_tiles_live.py` — conduit une unité
WALK jusqu'à une origine DISCRIMINANTE (découverte automatiquement), exige `_move_tiles ==
aiMovableTiles` EXACT **et** que la variante sans gate soit strictement plus large (sinon la
géométrie ne prouve rien → échec). Paramétré `MC1_67` / `C2_26` / `PVP_desert_04` (contrôle négatif :
le gate ne doit RIEN retirer). **Vu ROUGE** avant le fix (`port-only=[(2,3)]`).

**Cible** : `test_skitarii_turn_live` 3/3 vert. Nouvelle trace :

    res = {'moved': (6,6), 'kind': 'ability', 'ability': 17, 'target': 77}
    d_bfs 3 -> 2      hp 8536 -> 6057      atk(ranged=True, hits=3)

## 7. Verdict sur la 3ᵉ anomalie (`ability: 17`) — RÉFUTÉE comme cause

Mesuré live : le `NormalAttackType` concret d'`admecMarshall` **et** d'`admecSmnVanguard` vaut
**69 (`Loki_NormalAttack`)** — lu dans la cascade de `ControlEdict`
(`UnitStats_ActiveAbility_Id=69` sur l'entité summon fraîche) et dans `decisionView`
(`abilities[].kind == "normal"`). Le bridge offline utilise l'id SYNTHÉTIQUE 17
(`state_bridge.NORMAL_ATTACK_ID`, convention documentée en tête du module) de bout en bout :
`_attack_abilities` lui donne la portée MAX des armes, `ctx.normal_ids` route vers
`NORMAL_ATTACK_PLAYBOOK`, et `summon_ai.apply_action` teste `ability == 17` pour partir sur
`AttackDamageOperation.execute` (qui n'a pas besoin d'id). **Aucun étage ne consomme l'id concret sur
cette voie**, et le fix des anomalies 1-2 n'a rien changé à cet axe. Résidu associé : § 8.

## 8. Résidus nommés (mesurés, NON traités ici)

- **R5-a — arbitrage de TUILE après fix.** Sur la géométrie de l'oracle, le port choisit désormais la
  bonne CIBLE (77) mais la tuile **(6,6)** là où le natif prend **(4,7)**. (6,6) est élévation 2 : le
  port lui accorde ×1.5 de dégât prédit (1956-2934 vs 1305-1956) **et** +15 d'utilité de tuile
  (20 vs 5). Contre-mesure du même jour : sur une autre géométrie (cible en (2,7), tuile élevée (3,6)
  NON adjacente à un second ennemi) **port et natif choisissent la MÊME tuile (3,6)**. La seule
  différence structurelle entre les deux cas est que (6,6) est ADJACENTE à un second ennemi
  → suspecter un terme de menace/danger dans `CalculateUtilityFromTilePrediction` non porté. Axe
  `engine/utilities/tile.py` + élévation (cf. case-124/128), **hors périmètre R5**.
- **R5-b — le gate n'est câblé QUE dans `state_bridge._move_tiles`.** Les autres appelants de
  `get_movable_positions` (`runner/operations/behaviour.py`, `entities/selectors/tiles.py`,
  `runner/abilities/genestealer.py`, `runner/operations/triggers/genestealer.py`,
  `…/triggers/loki/betrayer.py`) l'ignorent encore. ⚠ **`_pathdist_to_enemies` en est SORTI** le
  2026-07-29 (`#17-off`) : ce n'est pas un oubli de câblage, c'est un **hors-sujet**. Ce chemin ne
  passe pas par `GetMovablePositions`/`NodesInNextLevel` mais par `IPathfinders.GetPath(1, ...)` →
  `BasePathfinder$$FindPath` → `GenerateBreadthFirstTree` → `GetValidNeighbours`, qui n'appelle
  JAMAIS `IsValidContinuePathTile` ; et le pathfinder du type 1 n'est même pas le `WalkPathfinder`
  (cf. `case-52` §#17-s5.5). Une tuile block-entering reste donc TRAVERSABLE par un chemin — elle
  n'est un cul-de-sac que pour l'ÉNUMÉRATION des tuiles atteignables.
- **R5-c — dépendance au canal `tiles=tileMeta`.** `make_can_continue` rend `None` si
  `State.effects` ne porte pas d'effets de tuile ; c'est la dégradation SÛRE (comportement d'avant),
  mais elle est SILENCIEUSE. Le seed vit dans `load_state` (`snapshot.py`) : un `load_state` sans
  `tiles=` reste sur-atteignant.
- **R5-d — bit 0x2 de `GetTileBlockingReasons`** (`GetEffectiveDepth` → `Min(1, depth)` = « l'hex
  finit le mouvement ») non porté : la condition qui pose ce bit n'a aucun datapoint.
- **R5-e — `snapshot.load_state` ne pose jamais `ai_controlled`.** Un état chargé d'un runner LIVE
  rend `UnitComponent.ai_controlled = False` même pour un summon réel (mesuré : le Vanguard
  live u104 → `collect_ai_controlled(player) == []`). Conséquence : `run_ai_control_pass` est un
  **no-op silencieux sur tout état chargé du live** ; seul le spawn offline
  (`_spawn_config_grot`) pose le flag. Fichier `engine/runner/snapshot.py`.
- **R5-f — le prédicat `IsValidContinuePathTile` du FlyPathfinder n'est PAS établi.** Le gate vit
  dans `BasePathfinder$$NodesInNextLevel` (donc partagé), mais le slot virtuel résolu par
  `FlyPathfinder` n'est pas lisible dans la table de symboles — et **l'absence d'un symbole ne
  prouve rien** (dédup IL2CPP des corps triviaux, cf. CLAUDE.md). Le port thread le paramètre et
  `_move_tiles` passe le MÊME prédicat qu'en marche ; le trancher demande d'invoquer le slot de
  vtable sur une instance de `FlyPathfinder`.
- **`probe_205_unstoppable.py` — sa conclusion A est FAUSSE.** Elle affirme « sur `MC1_67`,
  `get_movable_positions` == `aiMovableTiles` EXACT (zéro tuile extra) ⇒ aucun hex ne tronque le
  mouvement ». C'est vrai depuis les positions de SPAWN seulement : depuis (3,7) l'écart mesuré est
  de 2 tuiles. Le fondement d'`Unstoppable` (l'exemption de trait) est désormais PORTÉ
  (`not_blocking_movement_of_traits`) — le trait n'est donc plus structurellement inerte.
