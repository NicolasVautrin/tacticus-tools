"""Operations de mouvement — `IdunBattle.Operations.MoveUnitOperation` IdunBattle.Operations.MoveUnitOperation$$Execute.

Tranche 1, INCRÉMENT 1a (POSITION) : écrit la position finale du mover dans son
`PositionComponent`. C'est le cœur observable du move (le natif fait aussi la
validation, CalculatePaths, AddMoveEvent/pas, charging…, mais l'EFFET d'ÉTAT sur
le mover = sa position finale).

G1 (gen-stealer) : `IdunBattle.Operations.MoveUnitOperation$$KillSteppableUnits` PORTÉ ici (`_kill_steppable_units`),
INLINE dans l'ordre natif (avant `EvaluateAfterMoveTriggers`) — un occupant Steppable
(decoy/spore-mine) de la tuile d'arrivée est crushé par le MÊME
`IdunBattle.Operations.KillUnitOperation$$Execute` que toute autre mort
(`_kill_steppable_kill_unit`, #462-r4b-r1-r1-r1-r1-c-r3-r1 + `-r1`/`-r2`) : `alive=False`, `hp=0`,
`RecordDeathReason(..., DamageReason.Steppable)`, puis `On(1)` / garde revive / `On(2)` / les trois
`RemoveEffects` / `On(0)` / `On(0x36)` / garde heal. Le 5e événement `On(0x35 = PostUnitKill)` reste
publié par `after_move_triggers` (écart d'ordre et de couverture nommé, préexistant).

INCRÉMENT 1b (à venir, validé vs la vérité-terrain probe = Maugan Ra 1174 sur le
mover) : `IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers → cascade OVERWATCH
(`Overwatch_AutoAttackEffect` → auto-attaque → dégât + consommation de l'effet).
`IdunBattle.Operations.MoveUnitOperation$$AddMoveEvent émet l'event UnitMoved(step 3) + tuiles du chemin sur le bus.
"""
from __future__ import annotations

from ..state import State
from ..events import EventBus
from ..components import (PositionComponent, UnitComponent, StatsComponent, HealthComponent,
                          OwnerComponent, set_moved_flag, update_charging, record_tiles_moved)
from .base import Operation
from ...entities.damage_reason import DamageReason
from ...entities.pathfinding import pathfinders as _pf
from ...entities.pathfinding.fly_pathfinder import is_like_flying
from ...entities.pathfinding.walk_pathfinder import get_path_node_counts_by_pos, get_path_by_pos
from ...entities.traits.unit_trait import UnitTrait, has_trait
from ...services.movement_query import get_connected_path_to, get_num_tiles_moved
# ⚠ FORME MODULE (B) POUR CES DEUX-LA, ET C'EST LOAD-BEARING -- pas un gout de style.
# `get_pathfinder_type_for_unit` est le SEUL point de dispatch entre la marche, le vol et les huit
# types DECORES ; c'est donc l'unique endroit qu'une contre-epreuve puisse neutraliser pour
# demontrer que le dispatch SERT (« le port d'AVANT rendait autre chose »). En liaison DIRECTE
# (`from ... import get_pathfinder_type_for_unit`), un `setattr` sur le module
# `engine.services.movement_query` NE MORD PAS : le nom est fige ici a l'import, et la contre-epreuve
# compare alors le port A LUI-MEME -- elle rend un ensemble VIDE, quel que soit le board, quels que
# soient les porteurs. C'est la cause EXACTE du rouge de `master` (`88471bcd`) sur
# `test_448_r1_r1_r1_r1_flying_tiles_moved_live::test_le_walkpathfinder_diverge_sur_letat_live` :
# montage SAIN (3 porteurs, dispatch mesure `Fly` et `TeleportStrikeFly x2`), patch INERTE.
# C'est le gisement « HISSER EN FORME A fait passer de MORD a NE MORD PAS » du CLAUDE.md, pris
# dans l'autre sens : on RE-DESCEND en forme B, ce qui ne peut que RE-ARMER un patch, jamais en
# desarmer un. Cout en cascade : NUL (`from pkg import mod` charge les memes modules).
from ...services import movement_query as _mq
from ...services.movement_query import unit_has_effect_fn
from .aura_stat_mods import refresh_aura_stat_modifiers
from .damage import AttackDamageOperation
from .refresh_effects import RefreshEffectTrigger, refresh_stat_modifier_effects
from ...entities.effects.aura_selectors import hex_distance
from ..components import save_previous_position
from ..components import set_unit_feet
# #448-r1-r1-r2-r2-r1 -- les substrats des SEPT gates amont : `UnitFlagsComponent.FLED` (le
# `HasFlag(unit, 9)` d'`UnitExtensions$$HasFled`) et l'empreinte courante (`GetUnitFeet`).
from ..components import UnitFlagsComponent
from ..components import get_unit_feet
from .. import components as _components   # FORME B (#590-r6-r2) : cf. `_is_unit_allowed_to_move`
# Branche `allowNullTargetPosition` (E8) : le slot 7 de l'`IOperationProcessor`.
from .remove_unit_from_tiles import RemoveUnitFromTilesOperation
from . import tile_reservation


def _blocking_positions(state: State, mover_id: int) -> set:
    """`IdunBattle.Entities.Pathfinding.WalkPathfinder$$UnitIsBlockedByEnemyUnit` : les positions
    portant un occupant ENNEMI VIVANT non `Steppable` -- un ami ne bloque pas le passage, et
    `UnitExtensions.HasTrait(occ, 0x1b = Steppable)` court-circuite le blocage.

    FOYER UNIQUE des deux consommateurs de `MoveUnitOperation` : `_num_tiles_moved`
    (`connectedPath`) et `_calculate_path` (`path`). Le natif interroge le MEME predicat depuis les
    deux -- `Pathfinders$$GetPath` et `BattleQuery$$GetConnectedPathTo` finissent tous deux dans
    `BasePathfinder$$GenerateBreadthFirstTree`, dont l'arete est
    `WalkPathfinder$$IsValidPathNode`."""
    me = state.get_entity(int(mover_id))
    moc = me.get_component(OwnerComponent) if me is not None else None
    team = moc.team if moc is not None else None
    blocking = set()
    for uid, e in state.entities.items():
        if uid == mover_id:
            continue
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None or uc is None or not uc.alive:
            continue
        oc = e.get_component(OwnerComponent)
        if team is not None and oc is not None and oc.team == team:
            continue
        sc = e.get_component(StatsComponent)
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        if has_trait(traits or [], UnitTrait.Steppable):
            continue
        blocking.add((pc.col, pc.row))
    return blocking


def _num_tiles_moved(state: State, mover_id: int, from_pos, to_pos) -> int:
    """`IdunBattle.Core.Services.BattleQuery$$GetNumTilesMoved(connectedPath)` applique au
    `connectedPath` que `IdunBattle.Operations.MoveUnitOperation$$CalculatePaths` produit pour CE
    pas -- c'est-a-dire le nombre d'ARETES du chemin, `path.Count - 1` :

        GetNumTilesMoved(path) = IsNullOrEmpty(path) ? 0 : path.Count - 1

    `connectedPath` vient de `IdunBattle.Core.Services.BattleQuery$$GetConnectedPathTo(unit,
    startTile, endTile)` -> `IdunBattle.Core.Services.MovementQuery$$GetConnectedPathTo`, qui
    appelle `IdunBattle.Entities.Pathfinding.Pathfinders$$GetPath(unit, from, to, maxRange)` --
    l'overload SANS type explicite, qui resout lui-meme
    `IdunBattle.Core.Services.MovementQuery$$GetPathfinderTypeForUnit(unit)`, donc **le meme
    pathfinder** que le `path` de `CalculatePaths`. Pour une unite ordinaire (ni volante, ni effet
    de mouvement special) c'est le **WalkPathfinder**, celui que porte
    `entities.pathfinding.walk_pathfinder.get_path_node_counts_by_pos` -- FOYER PARTAGE avec la
    face DECISION (`prediction/_shared.py::_walk_path_counts_from`) et avec la face MOUVEMENT du
    meme passif (#304). `Count` = NOEUDS, extremites incluses -> `- 1`.

    LA BRANCHE VOLANTE (`#448-r1-r1-r1-r1`, FERME) ne passe PAS par le WalkPathfinder.
    `MovementQuery$$GetConnectedPathTo` resout
    `IdunBattle.Core.Services.MovementQuery$$GetPathfinderTypeForUnit(unit)` =
    `IsLikeFlying(unit) ? 3 : 0`, et la route du vol est TROIS etages, pas un :

      1. `IdunBattle.Entities.Pathfinding.FlyPathfinder$$FindPath` = `BasePathfinder$$FindPath`
         (A* a cout UNIFORME -- son `WeightCost` est un corps trivial `return 10`, RE-DERIVE AU
         RUNTIME) **puis une SIMPLIFICATION EN WAYPOINTS** : seuls survivent les extremites, les
         tuiles de teleportation, et les virages ayant un MUR dans leur couronne ;
      2. `GetConnectedPathTo` RE-DENSIFIE chaque saut restant par une beeline
         (`PathfinderType.Beeline` = `IgnoreEverythingPathfinder`), qui **traverse tout, murs
         compris** (ses trois predicats sont des corps triviaux `return true`) ;
      3. `GetNumTilesMoved` = `Count - 1` sur ce chemin recousu.

    ⇒ pour un vol DIRECT le compte est la DISTANCE hex (et non les pas de marche) ; pour un vol
    DETOURNE, il vaut la somme des distances entre waypoints, donc il peut etre STRICTEMENT plus
    court que le chemin de vol reellement suivi. Avant #448-r1-r1-r1-r1 le port comptait des pas
    de MARCHE pour un volant -- mesure MC1_67 : `(1,1) -> (1,3)` vaut 3 pas de marche et 2 de vol.

    ⚠ ET CE N'EST PAS QUE LE VOL. `GetPathfinderTypeForUnit` teste QUATRE effets AVANT
    `IsLikeFlying` et rend alors un type DECORE (6..13), dont
    `IdunBattle.Entities.Pathfinding.ATeleportPathfinder$$FindPath` rend litteralement
    **`[from, to]`** -- aucun pathfinding. Le compte d'un porteur `TeleportStrike` vaut donc la
    DISTANCE quelle que soit la geometrie. Ce n'est pas un cas de bord : sur les 5 volants du pool
    retenus pour la mesure, **3** sont dans ce regime (`bloodDante`, `bloodIntercessor`,
    `eldarAutarch`). Le dispatch complet est donc porte, pas seulement le bras `IsLikeFlying`.

    RESIDUS, tous nommes (identiques a ceux de la face DECISION) :
      * `MovementQuery$$GetConnectedPathTo` DENSIFIE le chemin du pathfinder (re-insertion des
        tuiles intermediaires entre deux noeuds distants de plus de 1 -- teleporteurs/sauts). Sur
        un chemin de marche ordinaire les deux listes ont la MEME longueur.
      * `block_entering_positions` (tuiles a `GetTileBlockingReasons & 1`, facturees
        `10000 - elevation`) n'est pas derivable de l'ECS -> vide : un chemin peut etre plus COURT
        que celui du natif. Degradation PERMISSIVE, meme residu que #304.
      * `IsTemporary(to)` : aucune source offline.
    `from_pos`/`to_pos` egaux, absents, ou destination injoignable -> 0 (le natif rend 0 sur
    `IsNullOrEmpty(path)`).

    ⚠ CE QUE LA BRANCHE MARCHE NE CHANGE PAS. Elle garde son moteur en domaine POSITION
    (`get_path_node_counts_by_pos`), qui est un FOYER PARTAGE avec la face DECISION
    (`prediction/_shared.py::_walk_path_counts_from`, #304) -- le rebrancher sur
    `base_pathfinder.find_path` creerait deux implementations du meme natif, et la densification
    de `GetConnectedPathTo` y est de toute facon un NO-OP (deux noeuds consecutifs d'un chemin de
    `BasePathfinder$$FindPath` sont adjacents). RESIDU MARCHE, prealable et inchange : sur une
    destination injoignable le port rend `0` la ou le natif prend sa branche degeneree
    (`path == null` -> `[from, to]` -> `1`)."""
    if from_pos is None or to_pos is None or tuple(from_pos) == tuple(to_pos):
        return 0
    board = getattr(state, "board", None)
    if board is None:
        return 0
    me0 = state.get_entity(int(mover_id))
    sc0 = me0.get_component(StatsComponent) if me0 is not None else None
    traits0 = getattr(sc0.ctx, "traits", None) if sc0 is not None else None
    ptype = _mq.get_pathfinder_type_for_unit(unit_has_effect_fn(state, int(mover_id)), traits0 or [])
    # TOUT sauf `Walk` passe par le foyer CHEMIN : le vol (3), les huit types DECORES (6..13,
    # dont 6/8/10/12 qui ont pourtant une base MARCHE -- c'est `ATeleportPathfinder$$FindPath`
    # qui les detourne, pas leur base), et le `Beeline` (2), qu'aucun call-site ne produit ici.
    if ptype != int(_pf.PathfinderType.Walk):
        src = board.id_at(int(from_pos[0]), int(from_pos[1]))
        dst = board.id_at(int(to_pos[0]), int(to_pos[1]))
        if src is None or dst is None:
            return 0                              # hors board : aucune tuile a compter
        path = _pf.find_path(board, ptype, src, dst)
        return get_num_tiles_moved(get_connected_path_to(board, src, dst, path))
    neigh, walk, elev = board.walk_maps_by_pos()
    blocking = _blocking_positions(state, mover_id)
    counts = get_path_node_counts_by_pos((from_pos[0], from_pos[1]), neigh_by_pos=neigh,
                                         walkable_by_pos=walk, elev_by_pos=elev,
                                         blocking_positions=blocking)
    n = counts.get((to_pos[0], to_pos[1]))
    return int(n) - 1 if n else 0                    # `IsNullOrEmpty(path)` -> 0


def _is_like_flying(traits, pathfinder_type_override) -> bool:
    """`IdunBattle.Operations.MoveUnitOperation$$IsLikeFlying(unit, options)` -- MIRROR 1:1, LES
    DEUX BRAS (#448-r1-r1-r2). A ne pas confondre avec son homonyme
    `IdunBattle.Entities.UnitExtensions$$IsLikeFlying(unit)`, qui n'est QUE le premier bras.

        bool IsLikeFlying(IEntity unit, MoveUnitOptions options) {
            if (UnitExtensions.IsLikeFlying(unit)) return true;          // BRAS 1 -- les TRAITS
            var ov = options.<+0x8>;                                     // Nullable<PathfinderType>
            if (!ov.HasValue) return false;
            return ov.Value == PathfinderType.Fly;                       // BRAS 2 -- l'OVERRIDE
        }

    Le champ `MoveUnitOptions+0x8` est un `Nullable<PathfinderType>`, et ce n'est pas une deduction :
    `IdunBattle.Operations.MoveUnitOperation$$CalculatePaths` le relit deux lignes plus loin par
    `Nullable.get_HasValue` / `get_Value` pour ECRASER le type de pathfinder resolu par
    `IdunBattle.Core.Services.MovementQuery$$GetPathfinderTypeForUnit`. `PathfinderType.Fly` vaut
    `3` (dump d'enums du build : 0=Walk 1=IgnoreTerrain 2=Beeline **3=Fly** 4=IgnoreDoor
    5=WaveValidator 6..13 = les types decores).

    QUI POSE L'OVERRIDE -- les QUATRE producteurs du `Nullable<PathfinderType>` du binaire, obtenus
    par les XREFS du `MethodInfo*` de son `.ctor` (donc EXHAUSTIF, pas un echantillon) :

      1. `IdunBattleLogic.Entities.DSLBehaviors$$FlyUnit(unit, tiles)` -- il alloue un
         `MoveUnitBehaviourOptions` (0x40 octets ZERO) et n'y pose QUE `+0x08 = Nullable(3)`, puis
         `new MoveUnitBehaviour(unit, tiles, options)`. C'est LE chainon qui manquait : le residu
         de `behaviours/movement.py::FlyUnit` disait « le champ +0x08 n'a aucun lecteur lu au
         decompile » -- le lecteur, c'est CETTE fonction, et l'override de `CalculatePaths`.
      2. `IdunBattleLogic.Entities.Abilities.Active.Loki.TreasonOfTzeentchAbility$$ExecuteBehaviour`
         (via `DSLBehaviors$$MoveUnit` avec `options[+0x08] = Nullable(3)`).
      3. `IdunBattleLogic.Entities.Abilities.Triggered.Loki.NovaBoost_AttackAbility$$CreateBehaviour`
         (le SECOND `MoveUnit` -- l'atterrissage ; le premier a des options nulles a `+0x08`).
      4. `IdunBattle.Messages.InputMessageProcessor.u003Cu003Ec__DisplayClass40_0$$u003CVisitu003Eb__0`
         -- la lambda de `Visit(CheatMoveUnitMessage)`. Identifiee par les champs CAPTURES, pas par
         le nom : elle lit `+0x10` (le processeur), `+0x18` (l'unite), `+0x20` (la liste de tuiles),
         soit exactement les TROIS champs que pose `Visit(CheatMoveUnitMessage)`, tandis que
         `Visit(MoveUnitMessage)` en pose QUATRE (`+0x20 = message`, `+0x28 = List<TileEntity>`).
         ⇒ **le mouvement joueur ordinaire ne pose PAS d'override** -- ce qui est corrobore, par un
         chemin independant, par la non-regression MARCHEUR de `#448-r1-r1-r1-r1`.

    `traits` = ceux du mover (bras 1) ; `pathfinder_type_override` = `None` quand le `Nullable` est
    VIDE (le cas de tous les call-sites a options nulles)."""
    if is_like_flying(traits or []):                       # BRAS 1 : Flying (0x4) / Burrow (0x13)
        return True
    if pathfinder_type_override is None:                   # `!ov.HasValue`
        return False
    return int(pathfinder_type_override) == int(_pf.PathfinderType.Fly)      # BRAS 2 : `== 3`


def _calculate_path(state: State, mover_id: int, from_pos, to_pos,
                    pathfinder_type_override=None) -> "list | None":
    """`IdunBattle.Operations.MoveUnitOperation$$CalculatePaths` -- son **8e** out-param, `path`
    (#448-r1-r1-r2-r2). Le 9e, `connectedPath`, reste porte a part par `_num_tiles_moved` : ce sont
    DEUX listes distinctes, et le §5 de `docs/rl/case-448-r1-r1-r2-second-bras-islikeflying.md`
    etablit que les confondre serait INFIDELE (`connectedPath` ne voit PAS l'override).

    LE NATIF, remis en C# depuis le decompile :

        CalculatePaths(unit, movementStartPosition, previousPosition, startTile, endTile, options,
                       out path, out connectedPath) {
            if (movementStartPosition == null) throw;
            if (movementStartPosition.Count == 0) {           // unite HORS PLATEAU
                var l = new List<TileEntity>{ endTile, endTile };
                path = l; connectedPath = l; return;          // JAMAIS vide
            }
            int movement       = UnitExtensions.GetStat(unit, 1 = Movement);
            int pathfinderType = MovementQuery.GetPathfinderTypeForUnit(unit);
            bool likeFlying    = MoveUnitOperation.IsLikeFlying(unit, options);
            if (UnitPosition.IsEmpty(previousPosition)) pathfinderType = PathfinderType.Fly;   // 3
            if (options.<+0x8>.HasValue) pathfinderType = options.<+0x8>.Value;   // l'OVERRIDE
            Nullable<int> useTeleporter = null;
            if (likeFlying && BattleQuery.GetDistance(startTile, endTile) > movement)
                useTeleporter = movement;
            path          = Pathfinders.GetPath(pathfinderType, unit, startTile, endTile,
                                                useTeleporter);
            connectedPath = BattleQuery.GetConnectedPathTo(unit, startTile, endTile);
        }

    ⚠ L'ORDRE DES DEUX ECRASEMENTS EST LU, PAS DEDUIT : le forcage `Fly` de la position vide vient
    AVANT l'override, donc **l'override GAGNE** quand les deux s'appliquent.

    ⚠ `useTeleporter` : argument MORT sur les deux routes lues (`#448-r1-r1-r1-r1` §4), non
    re-verifie sur les autres pathfinders -- residu PREEXISTANT, inchange ici.

    TRI-ETAT DU RETOUR, et c'est LA donnee du gate d'abandon :
      * **`None`** = MESURE, et la destination est INJOIGNABLE -- le `path` vide/nul du natif, sur
        lequel `Execute` journalise puis `RemoveReservation ; return` SANS bouger l'unite ;
      * une **liste** de positions (extremites incluses) = le chemin ;
      * `[from, to]` = le repli PERMISSIF quand le substrat manque (pas de board, tuile hors board,
        id non resoluble). Non vide, donc le gate ne mord pas : on n'ABANDONNE jamais un mouvement
        faute d'avoir su mesurer. C'est la seule degradation, et elle va dans le sens d'AVANT.

    `from_pos is None` (unite hors plateau : spawn, ou retour apres `RemoveUnitFromItsTiles`) rend
    `[to, to]` : c'est litteralement la branche `movementStartPosition.Count == 0` du natif, y
    compris son doublon. C'est ce qui empeche le gate de mordre sur `GhostRevive`,
    `EchoesFromTheWarp` et `StormboyzStrike_Fallback`, dont le caster arrive de nulle part."""
    if to_pos is None:
        return None
    dst = (int(to_pos[0]), int(to_pos[1]))
    if from_pos is None:
        return [dst, dst]                       # `movementStartPosition.Count == 0`
    src = (int(from_pos[0]), int(from_pos[1]))
    board = getattr(state, "board", None)
    if board is None:
        return [src, dst]                       # substrat absent -> PERMISSIF
    e = state.get_entity(int(mover_id))
    sc = e.get_component(StatsComponent) if e is not None else None
    traits = getattr(sc.ctx, "traits", None) if sc is not None else None
    ptype = _mq.get_pathfinder_type_for_unit(unit_has_effect_fn(state, int(mover_id)), traits or [])
    if pathfinder_type_override is not None:
        ptype = int(pathfinder_type_override)    # `options.<+0x8>` ECRASE, y compris un forcage Fly
    if ptype != int(_pf.PathfinderType.Walk):
        sid = board.id_at(src[0], src[1])
        did = board.id_at(dst[0], dst[1])
        if sid is None or did is None:
            return [src, dst]                    # hors board : PERMISSIF
        ids = _pf.find_path(board, ptype, sid, did)
        if ids is None:
            return None                          # MESURE : injoignable
        out = []
        for t in ids:
            xy = board.coord(int(t))
            if xy is None:
                return [src, dst]                # id non resoluble : PERMISSIF
            out.append((int(xy[0]), int(xy[1])))
        return out or None
    # `Walk` : le port materialise la marche en domaine POSITION (FOYER PARTAGE #304), le meme
    # moteur que `_num_tiles_moved` -- `get_path_by_pos` et `get_path_node_counts_by_pos` sont deux
    # sorties d'un unique `_dijkstra_by_pos`, donc leurs longueurs coincident par construction.
    neigh, walk, elev = board.walk_maps_by_pos()
    return get_path_by_pos(src, dst, neigh_by_pos=neigh, walkable_by_pos=walk, elev_by_pos=elev,
                           blocking_positions=_blocking_positions(state, int(mover_id)))


def _tiles_are_empty(state: State, mover_id: int, dest_tile) -> bool:
    """`IdunBattle.Operations.MoveUnitOperation$$TilesAreEmpty(unit, feetTiles)` -- MIRROR 1:1 du
    decompile (#448-r1-r2). Le natif :

        foreach (var tile in feetTiles) {
            var content = tile.GetComponent<TileContentComponent>();
            if (!content.IsFilled())                                 continue;   // vide
            if (TileExtensions.HasSteppableUnit(tile, state))        continue;   // un Steppable
            if (TileExtensions.ContainsUnit(content, state, unit))   continue;   // c'est NOUS
            logger.Log(...);  return false;                                      // OCCUPEE
        }
        return true;

    ⚠ **C'EST LE SEUL GATE D'OCCUPATION DE TOUT `Execute`** -- et c'est ce que la lecture d'origine
    (`case-448-r1` §6.2 : « il mordrait si un trigger `PreUnitMove` faisait OCCUPER la tuile
    d'arrivee ») avait sous-estime. Les sept gates AMONT ne testent pas l'occupation :
    `IsAllowedToMove` (flags/effets), `UnitIsOnTiles` (« y suis-je deja ? »), `TilesAreWalkable`,
    `TilesMatchUnitFeetCount`, `IsDisallowedEmptyPosition`, `IsPositionReservedForOtherUnit` (la
    RESERVATION, pas l'occupant) et `IsPositionReservedForDrafting`. Le gate mord donc AUSSI quand
    la destination etait deja occupee AVANT le vecteur `On(0x1f)` -- un trigger n'est pas requis.

    Les trois exemptions sont chacune load-bearing cote port :
      * `HasSteppableUnit` : sinon un decoy/spore-mine bloquerait le mouvement que
        `KillSteppableUnits` est justement la pour ecraser (`_kill_steppable_units`) ;
      * `ContainsUnit(self)` : une unite multi-pieds qui glisse d'un pied ne se bloque pas ;
      * `!IsFilled` : le cas ordinaire.

    Le port ne materialise que la MAIN TILE (`UnitComponent.feet` collapse l'empreinte), donc la
    boucle se reduit a une tuile -- meme residu multi-pieds que partout ailleurs. Les MORTS ne
    remplissent pas : `TileContentComponent.IsFilled` suit le retrait du plateau, que le port
    collapse dans `UnitComponent.alive`."""
    if dest_tile is None:
        return True
    dt = (int(dest_tile[0]), int(dest_tile[1]))
    for uid, e in state.entities.items():
        if uid == mover_id:
            continue                             # `ContainsUnit(content, state, unit)`
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None or uc is None or not uc.alive:
            continue                             # `!IsFilled` (le retrait du plateau)
        if (pc.col, pc.row) != dt:
            continue
        sc = e.get_component(StatsComponent)
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        if has_trait(traits or [], UnitTrait.Steppable):
            continue                             # `HasSteppableUnit(tile, state)`
        return False
    return True


# ================================================================================================ #
# LES SEPT GATES AMONT d'`IdunBattle.Operations.MoveUnitOperation$$Execute` (#448-r1-r1-r2-r2-r1).
#
# Ils tombent AVANT tout : avant `IsLikeFlying`, avant `GetUnitPosition`, avant l'ecriture de la
# destination demandee, avant `SetReservation`. Lus verbatim en tete du decompile, DANS CET ORDRE et
# avec CES POLARITES (trois d'entre eux refusent quand ils rendent VRAI) :
#
#     if (!IsAllowedToMove(unit, options.<+0x13>))            return;   // G1
#     if ( UnitIsOnTiles(unit, position))                     return;   // G2
#     if (!TilesAreWalkable(unit, position))                  return;   // G3
#     if (!TilesMatchUnitFeetCount(unit, position))           return;   // G4
#     if ( IsDisallowedEmptyPosition(unit, position, options.<+0x15>))  return;   // G5
#     if ( IsPositionReservedForOtherUnit(unit, position))    return;   // G6
#     if ( IsPositionReservedForDrafting(unit, position))     return;   // G7
#
# AUCUN d'eux n'appelle `RemoveReservation` : ils sont AMONT de `SetReservation`, il n'y a rien a
# retirer. C'est ce qui les distingue des deux gates d'abandon deja portes (`TilesAreEmpty`, `path`
# vide), qui, eux, la retirent.
#
# `position` est la DESTINATION sous forme d'EMPREINTE (`UnitPosition` = une liste de tuiles) --
# `[]` quand `to is None` (le lift-off, cf. la branche `allowNullTargetPosition`), sinon `[to]`,
# le port ne materialisant que la main tile.
# ================================================================================================ #


def _is_allowed_to_move(state: State, mover_id: int, ignore_unit_movement_blockers: bool) -> bool:
    """G1 -- `IdunBattle.Operations.MoveUnitOperation$$IsAllowedToMove(unit, ignoreUnitMovementBlockers)`,
    MIRROR du decompile (il rend VRAI = « le mouvement est permis ») :

        if (!ignoreUnitMovementBlockers && !UnitExtensions.CanMove(unit)) { log; return false; }
        if (UnitExtensions.IsDead(unit, state))                          { log; return false; }
        if (UnitExtensions.HasFled(unit))                                { log; return false; }
        return true;

    `ignoreUnitMovementBlockers` = l'octet `MoveUnitOptions+0x13`, `False` a tous les call-sites du
    port (options nulles). Les trois etages sont portes :

      * `UnitExtensions$$CanMove` -> le FOYER existant `components.unit_extensions_can_move`
        (mirror deja ecrit et deja TRI-ETAT ; il vivait dans `turnflow` jusqu'a #590-r6-r2, ou il a
        demenage pour supprimer une arete d'import, cf. sa docstring). Un `None` (etage non lisible)
        est traite comme « pas de refus » -- on n'ABANDONNE jamais un mouvement faute d'avoir su
        mesurer, meme parti que le tri-etat de `_calculate_path` ;
      * `UnitExtensions$$IsDead(unit, state)` -> `UnitComponent.alive`, le collapse habituel ;
      * `UnitExtensions$$HasFled(unit)` = `HasFlag(unit, 9 = UnitFlag.Fled)`, LU au decompile (le
        corps entier de `HasFled` est ce seul appel) -> `UnitFlagsComponent.FLED`, que
        `FleeOperation` pose deja.
    """
    e = state.get_entity(int(mover_id))
    if e is None:
        return False
    if not ignore_unit_movement_blockers:
        # #590-r6-r2 : le differe qui vivait ici etait PORTEUR **envers `turnflow`** (`turnflow` ->
        # `abilities.handler` -> ... -> ce module). Le foyer ayant demenage vers `components`, il
        # devient GRATUIT et est HISSE en tete -- forme B (`from .. import components as
        # _components`), donc une substitution posee sur `components` mord toujours.
        if _components.unit_extensions_can_move(state, int(mover_id)) is False:
            return False                                  # `!UnitExtensions.CanMove(unit)`
    uc = e.get_component(UnitComponent)
    if uc is not None and not uc.alive:
        return False                                      # `UnitExtensions.IsDead(unit, state)`
    fl = e.get_component(UnitFlagsComponent)
    if fl is not None and fl.has(UnitFlagsComponent.FLED):
        return False                                      # `UnitExtensions.HasFled(unit)`
    return True


def _unit_is_on_tiles(state: State, mover_id: int, position: list) -> bool:
    """G2 -- `IdunBattle.Operations.MoveUnitOperation$$UnitIsOnTiles(unit, feetTiles)`, MIRROR du
    decompile (il rend VRAI = « l'unite y est DEJA », et `Execute` REFUSE alors le mouvement) :

        var feet = UnitExtensions.GetUnitFeet(unit, state);              // les PIEDS de l'unite
        if (feet.Count != feetTiles.Count)                  return false;
        if (feet.Count == 0 && feetTiles.Count == 0)        return true;
        foreach (var foot in feet) {
            var tile = EntityExtensions.GetMainTile(foot, state);
            if (tile == null)                               return false;
            if (!feetTiles.Contains(tile))                  return false;
        }
        return true;

    C'est le gate « mouvement NUL » : bouger vers l'empreinte qu'on occupe deja est un no-op, et le
    natif le coupe AVANT d'emettre `On(0x1f = PreUnitMove)`. Le port, lui, jouait le vecteur pre-move,
    posait `Moved`, rejouait le vecteur after-move et pouvait declencher un OVERWATCH sur un
    deplacement de zero tuile.

    ⚠ LE BRAS `feet.Count == 0 && feetTiles.Count == 0` EST LU, pas deduit : une unite HORS PLATEAU
    a qui l'on demande une destination VIDE « y est deja ». C'est ce qui fait qu'un lift-off repete
    ne rejoue pas le vecteur after-move."""
    feet = get_unit_feet(state, int(mover_id))
    if len(feet) != len(position):
        return False
    if not feet and not position:
        return True                                       # les DEUX vides -> deja en place
    dest = set(position)
    for t in feet:
        if t not in dest:
            return False
    return True


def _tiles_are_walkable(state: State, position: list) -> bool:
    """G3 -- `IdunBattle.Operations.MoveUnitOperation$$TilesAreWalkable(unit, feetTiles)` :

        foreach (var tile in feetTiles) {
            if (tile == null)                                     { log; return false; }
            if (!BattleQuery.<slot 0xa1>(tile))                   { log; return false; }
        }
        return true;

    Le slot `0xa1` d'`IBattleQuery` est `IdunBattle.Core.Services.BattleQuery$$IsWalkableTile`, dont
    le corps est `tile != null && EntityExtensions.IsTile(tile) && tile.<TileComponent>.<+0x10> == 0`
    -- le champ que le capteur `boardGraph` publie comme `walkable` et que porte
    `Board.walkable(tileId)`.

    ⚠ **CE GATE EST DEJA CE QUI REFUSE LES ILOTS.** Mesure #448-r1-r1-r2-r2 : les composantes
    deconnectees des dumps `data/boards/` ressortent NON walkable dans le `boardGraph` live
    (`C4_09` : 37 tuiles walkable live contre 62 offline). Un mouvement vers une telle tuile est donc
    refuse ICI, en amont, et n'atteint jamais le gate `path` vide.

    Pas de board -> `True` (PERMISSIF) : on ne refuse pas un mouvement faute de substrat, meme parti
    que le tri-etat de `_calculate_path`."""
    board = getattr(state, "board", None)
    if board is None:
        return True
    for t in position:
        if t is None:
            return False
        tid = board.id_at(int(t[0]), int(t[1]))
        if tid is None:
            return False                                  # hors board = pas une tuile (`IsTile`)
        if not board.walkable(tid):
            return False
    return True


def _tiles_match_unit_feet_count(state: State, mover_id: int, position: list) -> bool:
    """G4 -- `IdunBattle.Operations.MoveUnitOperation$$TilesMatchUnitFeetCount(unit, tilesToMoveTo)` :

        if (tilesToMoveTo.Count == 0)                        return true;   // le LIFT-OFF passe
        var feet = UnitExtensions.GetUnitFeet(unit, state);
        if (feet.Count == tilesToMoveTo.Count)               return true;
        log;  return false;

    ⚠ **LE BRAS `Count == 0` EST CE QUI LAISSE PASSER LE LIFT-OFF** : sans lui, une destination vide
    serait refusee ici avant meme d'atteindre `IsDisallowedEmptyPosition`. Lu, pas deduit.

    ⚠ **ET SOUS LE COLLAPSE MONO-HEX DU PORT, CE GATE NE PEUT PAS REFUSER — c'est un fait, pas une
    commodite.** `MoveUnitOperation` prend UNE main tile, donc l'empreinte de destination qu'il
    materialise a toujours exactement 1 element ; et `get_unit_feet` rend l'empreinte COURANTE, qui
    vaut 1 pour toute unite mono-hex. Il ne refuserait donc que sur une unite MULTI-HEX, a qui le
    port demande de bouger vers une seule tuile -- et le refuser la serait une regression INVENTEE
    (le natif, lui, recevrait une empreinte de meme cardinalite). Le gate est donc porte au rang
    natif et rendu INERTE sur le multi-hex, explicitement, plutot que tu, ou joue a tort.
    Meme residu multi-pieds que `_tiles_are_empty` et `KillSteppableUnits`."""
    if not position:
        return True                                       # `tilesToMoveTo.Count == 0`
    feet = get_unit_feet(state, int(mover_id))
    if len(feet) == len(position):
        return True
    # COLLAPSE assume : le port ne materialise qu'une main tile de destination, donc une unite
    # multi-hex tomberait ici alors que le natif recevrait `position.Count == feet.Count`.
    return len(position) == 1


def _is_disallowed_empty_position(position: list, allow_null_target_position: bool) -> bool:
    """G5 -- `IdunBattle.Operations.MoveUnitOperation$$IsDisallowedEmptyPosition(unit, position,
    allowNullTargetPosition)`, MIRROR du decompile (il rend VRAI = REFUS) :

        if (position.Count != 0 || allowNullTargetPosition)  return false;
        log;  return true;

    `allowNullTargetPosition` = l'octet `MoveUnitOptions+0x15`. C'est le SEUL gardien de la branche
    LIFT-OFF : une destination vide passe si et seulement si le call-site l'a demandee."""
    return (not position) and (not allow_null_target_position)


def _is_position_reserved_for_other_unit(state: State, mover_id: int, position: list) -> bool:
    """G6 -- `IdunBattle.Operations.MoveUnitOperation$$IsPositionReservedForOtherUnit(unit, position)`
    = `BattleQuery.<slot 0xa5>(position, unit)`, c'est-a-dire la surcharge LISTE d'
    `IdunBattle.Core.Services.BattleQuery$$IsTileReservedForAnotherUnit` (le corps du gate est cet
    appel, plus un log). Porte par `operations/tile_reservation.py` (#550-r1) :

        foreach (tile in position)
            if (IsTileReserved(tile) && !IsTileReservedForUnit(tile, unit)) return true;
        return false;

    ⚠ **NE PAS CONFONDRE avec `TileExtensions$$IsTileReservedForOtherUnit`**, l'homonyme que lit
    `CanAddUnitFromAbility` : sur une tuile NON reservee, celui-la rend VRAI et celui-ci FAUX. Les
    deux polarites sont opposees et les deux sont LUES (cf. l'en-tete de `tile_reservation.py`)."""
    if not position:
        return False
    return tile_reservation.is_tile_reserved_for_another_unit(state, position, int(mover_id))


def _is_position_reserved_for_drafting(state: State, position: list) -> bool:
    """G7 -- `IdunBattle.Operations.MoveUnitOperation$$IsPositionReservedForDrafting(unit, position)` :

        foreach (var tile in position)
            if (TileExtensions.IsTilePendingDrafting(tile, state, null)) { log; return true; }
        return false;

    **NON PORTE, ET LA DIRECTION EST DITE.** `IdunBattle.Entities.TileExtensions$$IsTilePendingDrafting`
    balaie les entites-JOUEUR de l'etat et lit, pour chacune,
    `DraftingComponent.<+0x28>.<+0x2c>` (la tuile ou ce joueur est en train de POSER une unite),
    en s'exemptant lui-meme par `playerComponent.<+0x10> != allowedDraftingPlayerId` (`null` ici,
    donc aucune exemption). C'est l'etat de la phase de DRAFTING -- que le runner n'a pas : aucune
    seed BC ne le publie, aucune Operation portee ne l'ecrit, et
    `IdunBattle.Operations.StartTurnOperation$$Execute` (dont le port ne joue ni le
    `DraftingComponent$$BlockDrafting` ni le `$$EnableDrafting`) en est le seul pilote.

    Rend donc TOUJOURS `False` : le port est PERMISSIF sur cet axe (il laisse passer un mouvement
    vers une tuile que le natif refuserait pendant qu'un adversaire y drafte). Fabriquer un substrat
    depuis autre chose serait une hypothese deguisee en mirror. MEME residu, meme direction, que le
    `IsTilePendingDrafting` deja nomme par `entities/selectors/tiles.py::CanAddUnit`."""
    return False


def _set_position_feet_count_mismatch(state: State, mover_id: int, position: list) -> bool:
    """S1 -- le PREMIER gate propre d'`IdunBattle.Operations.SetUnitPositionOperation$$Execute`
    (#550-r4). Il rend VRAI = REFUS. LU verbatim en tete du corps :

        feet = UnitExtensions.GetUnitFeet(unit, state);
        if (feet == null || position == null)         throw;
        if (feet.Count != position.Count)             { log; return; }

    ⚠ **CE N'EST PAS G4.** `MoveUnitOperation$$TilesMatchUnitFeetCount` porte un bras
    `tilesToMoveTo.Count == 0 -> true` qui laisse passer le LIFT-OFF ; celui-ci ne l'a PAS, donc une
    `UnitPosition` VIDE y est refusee des que l'unite a au moins un pied. Les deux natifs sont des
    Operations DISTINCTES (slots `MoveUnit` et `SetUnitPosition` de l'`IOperationProcessor`,
    respectivement 4 et 3 arguments) : le port utilise la premiere comme STAND-IN de la seconde a
    quatre call-sites, qui doivent donc jouer CE gate-ci et pas les sept autres.

    ⚠ **MEME COLLAPSE ASSUME que `_tiles_match_unit_feet_count`, et pour la meme raison** : le port
    ne materialise qu'une main tile de destination, donc `position` vaut toujours 0 ou 1 element,
    alors que le natif recevrait une empreinte de meme cardinalite que `feet`. Refuser un multi-hex
    ici serait une regression INVENTEE -- le gate est donc porte au rang natif et rendu INERTE sur le
    multi-hex, explicitement."""
    feet = get_unit_feet(state, int(mover_id))
    if len(feet) == len(position):
        return False                                      # `feet.Count == position.Count`
    if len(position) == 1:
        return False                                      # COLLAPSE mono-hex assume (cf. docstring)
    return True


def _set_position_unit_is_dead(state: State, mover_id: int) -> bool:
    """S2 -- le SECOND gate propre d'`IdunBattle.Operations.SetUnitPositionOperation$$Execute`
    (#550-r4). Il rend VRAI = REFUS. LU verbatim, juste apres S1 :

        if (UnitExtensions.HasFlag(unit, 6)) { log; return; }

    `6` est `IdunBattle.Entities.Enum.UnitFlag.Dead`, LU dans `data/symbols/<build>/frida/enums.tsv`
    (`0=Moved, 1=ArrivedAtFinalTile, 2=ActiveAbilityUsed, 3=TurnFinished, 4=NoActionAvailable,
    5=Automatic, 6=Dead, 8=Overkilled, 9=Fled, ...`) -- pas deduit du nom de la fonction. C'est le
    MEME flag que teste `IdunBattle.Operations.DisplaceUnitOperation$$SwitchPosition` en tete
    (`deadCaster` / `deadTarget`), qui est donc gate DEUX FOIS cote natif.

    Offline le flag natif n'est pas trace ; le predicat equivalent est
    `IdunBattle.Entities.UnitExtensions$$IsDead`, deja mirrore -- exactement le collapse que
    `SwitchPositionOperation` ecrit deja pour ses deux `HasFlag(u, 6)`."""
    e = state.get_entity(int(mover_id))
    if e is None:
        return False
    uc = e.get_component(UnitComponent)
    return uc is not None and not uc.alive


def _movement_start_position(state: State, mover_id: int) -> list:
    """E1 -- le `movementStartPosition` d'`IdunBattle.Operations.MoveUnitOperation$$Execute`, LU :

        currentPosition       = EntityExtensions.GetUnitPosition(unit, state);
        previousThisTurn      = EntityExtensions.GetPreviousPositionThisTurn(unit, state);
        movementStartPosition = currentPosition;
        if (UnitPosition.IsEmpty(currentPosition) && previousThisTurn.HasValue
            && !UnitPosition.IsEmpty(previousThisTurn.Value))
            movementStartPosition = previousThisTurn.Value;

    C'est l'entree de `CalculatePaths` (son `startTile` = `movementStartPosition[0]`), et c'est ce
    qui distingue « unite hors plateau SANS passe » (branche degeneree `[endTile, endTile]`) de
    « unite hors plateau QUI VIENT DE QUITTER une tuile ce tour » (vrai chemin depuis cette tuile,
    avec `pathfinderType` force a `Fly` parce que `previousPosition` -- le 4e argument, la position
    COURANTE -- est vide).

    **LE SECOND BRAS EST DESORMAIS ATTEIGNABLE** (#1082, ferme `#462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r2`).
    `IdunBattle.Entities.EntityExtensions$$GetPreviousPositionThisTurn` lit le slot `+0x98`, le
    JUMEAU de `+0x88` (celui que porte `PositionComponent.previous`). Les deux sont ecrits ensemble
    et avec la MEME valeur par `SetUnitPositionOperation$$SavePreviousPosition` et par
    `RemoveUnitFromTilesOperation$$Execute`, mais ils ne sont PAS remis a zero ensemble :
    `IdunBattle.Operations.StartTurnOperation$$Execute` efface `+0x98` (et lui seul, en deux
    `undefined8` -- c'est un `Nullable` de 16 octets), tandis que `+0x88` ne l'est que par
    `IdunBattle.Entities.Behaviours.ResetPreviousPositionBehaviour$$Execute` (unique call-site :
    `SwornProtector_ProtectAbility`).

    Ce qui bloquait n'etait PAS le decompile mais l'EMPLACEMENT du champ porte : le port n'avait que
    `+0x88`, sur la `PositionComponent`, que `set_unit_feet(uid, [])` SUPPRIME au retrait du
    plateau -- donc `previous` avec elle, dans le regime meme que ce bras adresse. `+0x98` est donc
    porte par `UnitComponent.previous_position_this_turn`, qui survit au retrait, comme le natif
    conserve son `MovementComponent` (`RemoveUnitFromTilesOperation$$Execute` ne met a zero que les
    `TileId` des `UnitFootComponent`, jamais la position precedente).

    Rend l'empreinte (liste de `(col,row)`), `[]` si l'unite n'occupe aucune tuile."""
    feet = get_unit_feet(state, int(mover_id))
    if feet:
        return feet                                  # `!IsEmpty(currentPosition)` -> on s'arrete la
    e = state.get_entity(int(mover_id))
    # `GetPreviousPositionThisTurn` lit `<+0x98>`, porte par `UnitComponent.previous_position_this
    # _turn` (#1082) -- et non par `PositionComponent.previous` (`<+0x88>`), qui est un AUTRE slot.
    # Il vit sur le `UnitComponent` PRECISEMENT pour survivre au `set_unit_feet(uid, [])` qui
    # supprime la `PositionComponent` : c'est ce qui rend ce second bras ATTEIGNABLE.
    uc = e.get_component(UnitComponent) if e is not None else None
    prev = list(getattr(uc, "previous_position_this_turn", None) or ()) if uc is not None else []
    return prev


def _movement_steps(state: State, mover_id: int, from_pos, to_pos,
                    pathfinder_type_override=None, num_tiles_moved: "int | None" = None) -> int:
    """Le `movementSteps` que `IdunBattle.Operations.MoveUnitOperation$$Execute` passe a
    `IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers` -- l'entree UNIQUE de la
    formule `IdunBattleLogic.Entities.DSLFormulas$$MovementSteps()`
    (`AbilityEntities+0x11c`, cf. `TriggerEvent.movement_steps`).

    LE NATIF, lu au site d'appel de fin de mouvement :

        movementSteps = IsLikeFlying ? <IBattleQuery slot itf 0x6c>(path.First(), path.Last())
                                     : path.Count

    ⚠ **`path.Count`, PAS le nombre de pas** -- et l'ecart d'UN est structurel, pas une coquille :
    `path[0]` est la tuile de DEPART (la boucle `IdunBattle.Operations.MoveUnitOperation$$
    AddMoveEvent` demarre a `i = 1`), et le helper que le jeu utilise ailleurs pour compter les
    tuiles PARCOURUES est `IdunBattle.Core.Services.BattleQuery$$GetNumTilesMoved(path)` =
    `path.Count - 1`. Le gate de `FullThrottle` (`>= movement = 3`) mord donc des **2 pas
    parcourus**, pas des 3. C'est exactement le genre de constante qu'on ne DEDUIT pas du nom :
    confronte live (cf. `docs/rl/case-448-r1-r1-full-throttle-gate.md`).

    LA BRANCHE VOLANTE (#448-r1-r1-r1) rend une **DISTANCE**, qui n'a pas ce `+1` et qui **ne
    depend pas du chemin**. Le slot d'interface `0x6c` est RE-DERIVE AU RUNTIME
    (`probe_27_4g_battlequery_slots.py` : index de vtable `0x70`, ancres `+4` confirmees) et
    resout la chaine :

        `IdunBattle.Core.Services.BattleQuery$$GetDistance(tileA, tileB)`
          -> `IdunBattle.Core.Services.MovementQuery$$GetDistance(origin, destination)`
          -> min sur GetTiles(origin) x GetTiles(destination) de
             `IdunBattle.Utils.Hex.CubeCoordinate$$Distance` = max(|dx|, |dy|, |dz|)

    -- soit exactement `hexgeo.distance`. Corroboration STRUCTURELLE independante :
    `IdunBattle.Operations.MoveUnitOperation$$CalculatePaths` appelle **le meme slot** avec
    `(startTile, endTile)` et compare son retour au stat `Movement` (`GetStat(unit, 1)`), ce qui
    n'a de sens que pour une distance en hexes.

    ⚠ L'ECART ENTRE LES DEUX BRANCHES N'EST PAS CONSTANT : il vaut `pas_de_marche + 1 - distance`,
    donc `1` seulement quand le chemin de marche est DIRECT. Mesure sur MC1_67 : une destination a
    `d = 2` peut couter 3 pas de marche (relief) -> volant 2, marcheur 4.

    CONFRONTE LIVE (greffe de `FullThrottle` sur 5 volants du pool ; detail et contre-epreuves
    dans `docs/rl/case-448-r1-r1-r1-flying-movement-steps.md`) : a `d = 2` le natif ne tue
    **jamais** un volant (0 / 20) la ou il tue un marcheur a la MEME distance (3 / 8), et il tue
    le volant a `d = 3` (4 / 13). Le discriminant fin -- 14 mouvements a `d = 2` dont le chemin de
    VOL fait 3 ou 4 pas (murs de C6_25), 0 mort -- exclut la lecture `path.Count - 1`, qui
    coincide avec la distance sur tout vol direct.

    LES DEUX BRAS D'`IdunBattle.Operations.MoveUnitOperation$$IsLikeFlying(unit, options)` sont
    desormais portes (#448-r1-r1-r2, cf. `_is_like_flying` juste au-dessus) : le premier lit les
    TRAITS (`HasTrait(0x4 = Flying) || HasTrait(0x13 = Burrow)`), le second l'OVERRIDE
    `options.<+0x8> == PathfinderType.Fly`, que pose la feuille DSL `FlyUnit`.

    ⚠ C'EST LE SEUL LECTEUR D'ETAT DU SECOND BRAS, et c'est ce qui rend `_num_tiles_moved`
    (`tilesMovedThisTurn`) STRUCTURELLEMENT AVEUGLE a l'override -- point de fidelite
    contre-intuitif, LU et non deduit. `MoveUnitOperation$$Execute` produit DEUX listes par
    `CalculatePaths` : `path` (8e out-param), calcule par
    `Pathfinders$$GetPath(pathfinderType, unit, from, to, useTeleporter)` ou `pathfinderType` PORTE
    l'override ; et `connectedPath` (9e out-param), qui vient de
    `IdunBattle.Core.Services.BattleQuery$$GetConnectedPathTo(entity, from, to)` -- **TROIS
    arguments, ni options ni pathfinderType**, donc il re-resout `GetPathfinderTypeForUnit(unit)`
    tout seul. Or `RecordTilesMoved` compte `connectedPath`, et `movementSteps` derive de `path`.
    ⇒ un port qui propagerait l'override jusqu'a `_num_tiles_moved` serait INFIDELE.

    L'override a par ailleurs un second effet, sur `path` lui-meme (il change le pathfinder, donc la
    trajectoire, donc la garde `path vide -> mouvement ABANDONNE`). Ce `path` est materialise depuis
    #448-r1-r1-r2-r2 (`_calculate_path`), et l'override y est PROPAGE. Il ne se compose pas avec le
    bras 2 sur `movementSteps` : des que l'override vaut `Fly`, `IsLikeFlying` est vrai, donc c'est
    la DISTANCE qui est prise et `path.Count` n'est plus lu.
    Meme statut pour le troisieme forceur de `Fly` de `CalculatePaths`
    (`if (previousPosition.IsEmpty()) pathfinderType = 3`) : il n'entre PAS dans `IsLikeFlying`, il
    ne touche que `path`.

    `num_tiles_moved` (#448-r1-r1-r3) -- LE COMPTE DEJA MESURE, quand l'appelant l'a. Le natif
    n'appelle `CalculatePaths` **qu'une fois** et consomme ses DEUX out-params bien plus bas ; le
    port, lui, appelait `_num_tiles_moved` DEUX FOIS, a deux MOMENTS differents (ici, avant la
    mutation ; puis sous `RecordTilesMoved`, apres). Passer le compte deja pris est ce qui replie
    les deux lectures sur un seul point de mesure, au rang natif. `None` = « pas de mesure
    fournie », et la fonction retombe sur son propre appel -- c'est ce que font les probes qui
    l'invoquent hors `Execute`.

    ⚠ CE `movementSteps` RESTE DERIVE de `_num_tiles_moved`, PAS de `_calculate_path`, et c'est
    VOULU. Les deux listes natives sont distinctes (`path` = 8e out-param, `connectedPath` = 9e),
    et la valeur rendue ici est CONFRONTEE LIVE (#448-r1-r1-r1 : 70 vols, la greffe de
    `FullThrottle` sur 5 volants). Les rebrancher sur `_calculate_path` ne changerait aucune valeur
    -- les deux passent par le meme `_dijkstra_by_pos` sur un chemin de marche -- mais ferait
    reposer une mesure validee sur un etage neuf, sans rien gagner. RESIDU herite, inchange : le
    port ne materialise pas la DENSIFICATION de
    `IdunBattle.Core.Services.MovementQuery$$GetConnectedPathTo`, la ou les deux listes divergent
    (teleporteurs/sauts)."""
    e = state.get_entity(int(mover_id))
    sc = e.get_component(StatsComponent) if e is not None else None
    traits = getattr(sc.ctx, "traits", None) if sc is not None else None
    if _is_like_flying(traits, pathfinder_type_override):
        d = hex_distance(from_pos, to_pos) if (from_pos is not None and to_pos is not None) else None
        return int(d) if d is not None else 0
    n = (_num_tiles_moved(state, mover_id, from_pos, to_pos) if num_tiles_moved is None
         else int(num_tiles_moved))
    # `path.Count` : `_num_tiles_moved` rend deja `Count - 1`. Destination injoignable / pas de
    # board -> il rend 0, et le natif serait sur `IsNullOrEmpty(path)` : on rend 0 aussi (le `+1`
    # ne s'applique qu'a un chemin REEL, sinon on fabriquerait un pas qui n'existe pas).
    return n + 1 if n > 0 else 0


class OverrideMovementTargetOperation:
    """Mirror `IdunBattle.Operations.OverrideMovementTargetOperation$$Execute` (#448-r1) --
    l'Operation IMPERATIVE qui DEVIE le mouvement en cours vers d'autres tuiles.

    Le natif, remis en C# depuis le decompile (les trois arguments arrivent decales d'un cran dans
    la sortie ghidra -- le 1er registre est le buffer de retour de la struct) :

        Execute(unit, tiles) {
            if (!EntityExtensions.IsUnit(unit)) return;                 // gate 1
            comp = unit.GetComponent<...>();                            // MEME paire de caches que
                                                                        // MoveUnitOperation$$Execute
            comp.<+0xa8> = new Nullable<UnitPositionId>(new UnitPositionId(tiles));
            dict = new Dictionary<int, int>();
            if (tiles.Count > 0) dict.Add(0x79, tiles[0].Id);
            if (tiles.Count > 1) dict.Add(0x7a, tiles[1].Id);
            if (tiles.Count > 2) dict.Add(0x7b, tiles[2].Id);
            processor.<step 0x25>(unit.Id, dict);                       // canal de VUE
        }

    CE QUE LE PORT FAIT. Il pose le champ (`UnitComponent.movement_target_override`), qui est LU et
    CONSOMME par `MoveUnitOperation.execute` -- c'est toute la face observable. Les trois clefs
    `0x79/0x7a/0x7b` et le step `0x25` sont le canal de VUE que
    `IdunBattle.View.AbilityConfigs.Loki.StormboyzStrikeVisuals$$GetFinalTile` lit ; le runner n'a
    pas de flux de vue -> non porte, comme partout ailleurs dans `operations/` (le meme `0x79` est
    deja DROPPE par la feuille `Inform`).

    `UnitPositionId` natif porte JUSQU'A TROIS tuiles (une unite multi-pieds) ; le port ne
    materialise que la MAIN TILE (`tiles[0]`), exactement comme le reste du moteur collapse
    l'empreinte (cf. `UnitComponent.feet`). RESIDU NOMME : un override de destination sur une unite
    a 3 pieds ne deplacerait que sa main tile. Aucun call-site du build n'est dans ce cas -- le seul
    (`StormboyzStrike_MissAbility`) devie un `orksNpc6Stormboy`, mono-pied.

    Rend `None` quand un gate refuse (entite inconnue, entite sans `UnitComponent` = le
    `!IsUnit` natif, liste de tuiles VIDE), sinon un dict de trace. La liste VIDE est un cas
    supplementaire du port : le natif construirait un `UnitPositionId` vide et le champ aurait
    `HasValue == true` avec une position vide, ce que `ToUnitPosition` puis
    `UnitPosition$$op_Inequality` traiteraient comme « different de la destination » -> une
    RECURSION vers du vide. La feuille appelante (`OverrideUnitMovementTarget`) gate deja sur
    `Count > 0` -- c'est le gate NATIF, lu dans `OverrideUnitMovementTargetBehaviour$$Execute` --
    donc ce chemin n'est pas atteint ; le refus ici est une ceinture, pas une invention."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, unit_id, tiles) -> dict | None:
        if state is None or unit_id is None:
            return None
        e = state.get_entity(int(unit_id))
        if e is None or e.get_component(UnitComponent) is None:
            return None                       # gate `EntityExtensions.IsUnit(unit)`
        pos = list(tiles or [])
        if not pos:
            return None                       # cf. docstring : ceinture, le gate natif est amont
        main = (int(pos[0][0]), int(pos[0][1]))
        e.get_component(UnitComponent).movement_target_override = main
        return {"unit": int(unit_id), "target": main, "tiles": [tuple(p) for p in pos]}


def _kill_steppable_kill_unit(state: State, dead_id: int, killer_id) -> list:
    """LE CRUSH EST UNE MORT ORDINAIRE : mirror de l'appel `processor.KillUnit(matchState, killer,
    entity, ForSteppable)` que les quatre `*$$KillSteppableUnits` natifs font
    (#462-r4b-r1-r1-r1-r1-c-r3-r1 pour le RETRAIT, `-r1` / `-r2` pour l'EMISSION et la RAISON).

    `IdunBattle.Operations.MoveUnitOperation$$KillSteppableUnits` construit INLINE la struct
    d'options que `IdunBattle.Operations.KillUnitOperationOptions$$ForSteppable` rend -- lu au
    decompile du build `rnca9r7q6c`, les DEUX ecritures non nulles etant `local_68 = 2` (`+0x00`) et
    `local_28 = 0x10100000000` (les octets `+0x40..+0x47`, donc `+0x44 = +0x45 = 1`, `+0x46 = 0`) --
    puis appelle le slot `KillUnit` de l'`IOperationProcessor`, c'est-a-dire
    `IdunBattle.Operations.KillUnitOperation$$Execute`, **le meme corps que pour une mort par degat**
    (`IdunBattle.Operations.AddUnitOperation$$KillSteppableUnits` y arrive par un chemin plus long --
    un `DamageAppliedResult` portant le meme `DamageReason` -> enqueue -> drain -> le meme `Execute`).

    LES QUATRE TESTS SUR `options` DE `Execute`, ET CE QU'ILS DONNENT SOUS `ForSteppable` :

    | octet  | ce qu'il gate                                             | valeur | effet ici |
    |--------|-----------------------------------------------------------|--------|-----------|
    | `+0x45`| court-circuite `UnitExtensions$$IsSteppable(killed)` (flag `0xd`) | 1 | non porte (le port collapse les flags de mort dans `UnitComponent.alive`) |
    | `+0x44`| `RecordDeathReason(killer, killed, uc, deathReason = options+0x00)` | 1 | **PORTE** (`-r2`) : `death_source = (mover, DamageReason.Steppable, None)` |
    | `+0x46`| le flag `UnitFlag.Overkilled` sous `CanBeOverkilled`       | 0      | `overkill=False` |
    | `+0x44`| une emission ANALYTICS (`Dictionary` + slot `0x19`)        | 1      | non porte (hors moteur) |

    Aucun autre bloc d'`Execute` ne lit `options` : les CINQ evenements de mort, les TROIS
    `RemoveEffects` et les deux gardes sont donc joues **a l'identique** pour un crush. Le seul
    endroit ou `Steppable` change quelque chose est `ActorStatisticsComponent$$RegisterDefeatedUnit`
    (saute quand `IsSteppable(killed)`), non porte.

    SEQUENCE (offsets = adresses de RETOUR relatives a `KillUnitOperation$$Execute`) -- le corps
    entier vit dans `damage.py::_kill_unit_operation`, FOYER PARTAGE avec la mort par degat :

        +0x505  health.hp = 0                              <- pose par l'appelant (`_kill_steppable_units`)
        (+0x44) RecordDeathReason(killer, killed, uc, DamageReason.Steppable)
        +0x7cc  On(PreUnitDeath = 1)
        +0x81c  GARDE REVIVE, puis On(2) / RemoveEffects(0) / RemoveEffects(1) / On(0) / On(0x36)
        +0xf35  GARDE HEAL, puis RemoveEffects(2)
        +0x10ac On(PostUnitKill = 0x35), HORS de la garde revive (cf. `_kill_unit_operation`)

    LES DEUX CANAUX D'ABILITY SONT **VIDES** SUR TOUT LE VECTEUR, et c'est LU deux fois :
    `Execute` fait `memset(&entities, 0, 0x128)` (donc `CurrentAbility` @+0x60 reste nul) puis recopie
    `KillUnitOptions+0x04..+0x20` dans `TriggeringAbility` @+0x98 -- or `ForSteppable` laisse ces
    0x1c octets a ZERO (`uStack_60 = local_58 = ... = 0` dans `KillSteppableUnits`). Le port force
    donc les deux canaux a `None` le temps de la sequence et les restaure ensuite, exactement comme
    `damage.py::_verify_deaths` le fait pour le drain (#301) : sans ca, un crush declenche DANS le
    behaviour d'une triggered-ability (feuille DSL `MoveUnit`, `spiritual_leader`) laisserait fuiter
    l'ambiant de l'appelant dans les gates `CurrentAbilityIs` / `TriggeringAbilityIs` du vecteur mort.

    `On(0x35 = PostUnitKill)`, 5e et dernier evenement, part DESORMAIS d'ici aussi
    (#462-r4b-r1-r1-r1-r1-c-r3-r1-r4) : il vit dans `_kill_unit_operation`, a son rang natif. Il
    etait publie par `move_death.py::post_unit_kill_triggers_for_move`, donc APRES
    `UpdateCharging`/`SetMovedFlag` et pour le SEUL crush-par-move -- double ecart, d'ORDRE et de
    COUVERTURE, ferme ici pour les QUATRE `*$$KillSteppableUnits` (move, revive, resurrect,
    spiritual_leader) comme pour la mort par degat.

    Renvoie la trace de `_kill_unit_operation` (liste de dicts : vecteurs joues + retraits par step)."""
    # `+0x44 != 0` -> `RecordDeathReason(this, killer, killed, uc, options+0x00)`. Le natif l'appelle
    # DANS `Execute`, AVANT `On(PreUnitDeath)` -- c'est la seule raison pour laquelle
    # `HasDeathReasonTrigger` peut matcher sur ce vecteur (`HaywireMineSteppableAbility` teste
    # `HasDeathReason(Owner, DamageReason.Steppable)`). `source_ability = None` : le natif ne remplit
    # l'`AbilityOrEffect` de la `DamageSource` que depuis un `DamageAppliedResult` de coup, qu'un
    # crush n'a pas.
    AttackDamageOperation._record_death_reason(state, int(dead_id),
                                               None if killer_id is None else int(killer_id),
                                               None, damage_reason=int(DamageReason.Steppable))
    prev_current = state.triggering_ability
    prev_trigger = state.trigger_ability_type
    state.triggering_ability = None            # memset 0x128 -> `CurrentAbility` @+0x60 VIDE
    state.trigger_ability_type = None          # `KillUnitOptions+0x04` = 0 -> `TriggeringAbility` VIDE
    try:
        # `+0x46 = 0` -> le flag `Overkilled` n'est jamais pose : `overkill=False` sur tout le vecteur.
        # `+0x45 = 1` -> `prevent_revive_option=True` : le natif pose `UnitFlag.PreventRevive` (0xd)
        # SANS CONDITION sur un crushe, AVANT `On(1 = PreUnitDeath)`. Son lecteur est le 3e etage de
        # `IdunBattle.Core.Services.BattleQuery$$CanBeRevived` -- c'est ce qui rend un crushe
        # DEFINITIVEMENT irrevivable, et c'est ce que le port ne jouait pas
        # (#462-r4b-r1-r1-r1-r1-c-r3-r1-r6 : la fiche `-r1` §6 annonce l'inverse, « un apothicaire
        # adjacent PEUT annuler un crush », en sautant cet etage de `CanBeRevived`).
        return AttackDamageOperation._kill_unit_operation(
            state, int(dead_id), None if killer_id is None else int(killer_id), False,
            prevent_revive_option=True) or []
    finally:
        state.triggering_ability = prev_current
        state.trigger_ability_type = prev_trigger


def _kill_steppable_units(state: State, dest_tile: tuple[int, int], mover_id: int,
                          trace: list | None = None) -> list:
    """`MoveUnitOperation$$IdunBattle.Operations.MoveUnitOperation$$KillSteppableUnits` — étape INLINE du move pipeline (avant
    `EvaluateAfterMoveTriggers`). Quand une unité MOVE sur `dest_tile`, tout occupant `Steppable`
    (`IdunBattle.Entities.UnitExtensions$$IsSteppable` = `HasTrait(0x1b=27)`) VIVANT y est détruit par un kill
    (`KillUnitOperationOptions$$IdunBattle.Operations.KillUnitOperationOptions$$ForSteppable`, type=2 flags 0x0101) : `alive=False` (hp 0),
    puis la SEQUENCE DE MORT COMPLETE (`_kill_steppable_kill_unit` -> `KillUnitOperation$$Execute`) --
    `RecordDeathReason(..., DamageReason.Steppable)`, `On(1)`, garde revive, `On(2)`, les trois
    `RemoveEffects`, `On(0)`, `On(0x36)`, garde heal, `On(0x35)`. `mover_id` est exclu (une unité ne
    se crushe pas elle-même). Renvoie les ids crushés. Ordre natif : `AddMoveEvent` →
    **KillSteppableUnits** → `EvaluateAfterMoveTriggers` (d'où le decoy déjà mort quand
    DecoysAndMisdirection lit `GetValidDeadDecoys`, G2).

    ⚠ La garantie que `post_unit_kill_triggers_for_move` tenait par CO-LOCALISATION avant
    #462-r4b-r1-r1-r1-r1-c-r3-r1-r4 -- « ne jamais émettre les events de mort pour un mort que le
    natif n'a pas tué » -- est tenue ici PAR CONSTRUCTION, et par DEUX gates DISTINCTS, mesurés
    séparément (une matrice de mutants les avait d'abord confondus) :
      * `not uc.alive` ci-dessous écarte le cadavre DU RUN (il a son ctx et ses traits `Steppable`,
        donc rien d'autre ne le refuserait) -- c'est le régime du 2e pas d'un chemin, où un
        steppable crushé au pas N est encore sur sa tuile au pas N+1 ;
      * l'absence de `StatsComponent` écarte le cadavre AU CHARGEMENT plus bas, par un substrat de
        traits VIDE (`has_trait([], Steppable)` faux) -- le gate `uc.alive` ne le voit même pas.
    Les deux sont exercés par `test_ctx_traits_substrat_ventilation_offline.py`, un régime chacun.

    `trace` (#462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r3) : liste OPTIONNELLE que cette fonction APPEND, une
    entrée par crushé — `{"unit": <id du crushé>, "killer": <mover>, "reason": DamageReason.Steppable,
    "vectors": <la trace de `_kill_unit_operation`>}`. Le retour reste les IDS (aucun appelant ne
    change de contrat) ; la trace est un canal SUPPLEMENTAIRE, parce que `KillUnitOperation$$Execute`
    joue CINQ vecteurs par crushé et que le retour `void` du natif ne permettait de les observer
    qu'a la SOURCE. Aucun effet sur l'etat : c'est de l'OBSERVABILITE, pas du comportement."""
    killed: list = []
    for uid, e in list(state.entities.items()):
        if uid == mover_id:
            continue
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None or uc is None or not uc.alive:
            continue
        if (pc.col, pc.row) != dest_tile:
            continue
        sc = e.get_component(StatsComponent)
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        if not has_trait(traits or [], UnitTrait.Steppable):
            continue
        # `KillUnitOperation$$Execute+0x505` : `savedHp = health.hp ; health.hp = 0`, AVANT tout
        # evenement. Le port y collapse aussi le retrait du plateau (`UnitComponent.alive`), que le
        # natif fait plus loin (`processor.<slot 6>` entre les deux premiers `RemoveEffects`) -- meme
        # collapse que la mort par degat (`_fire_death_if_killed` pose `alive=False` avant l'enqueue).
        uc.alive = False
        hc = e.get_component(HealthComponent)
        if hc is not None:
            hc.hp = 0
        # Le natif boucle sur les `Steppable` de la tuile et joue `KillUnit` **ENTIEREMENT** pour
        # chacun : les evenements de mort et le retrait des effets du crushe N precedent donc le
        # crush du N+1, ce que reproduit cet appel dans la boucle.
        vectors = _kill_steppable_kill_unit(state, uid, mover_id)
        if trace is not None:
            trace.append({"unit": int(uid), "killer": int(mover_id),
                          "reason": int(DamageReason.Steppable), "vectors": vectors})
        killed.append(uid)
    return killed


class MoveUnitOperation(Operation):
    """IdunBattle.Operations.MoveUnitOperation$$Execute (1a) — pose la position finale du mover. `to` = (col,row).

    `set_moved` = mirror de l'octet `+0x11` du `MoveUnitOptions` natif (5e argument d'`Execute`,
    struct passee par valeur) : le decompile fait
    `if (*(options + 0x11) == 0) UnitExtensions.SetMovedFlag(unit);`. Il vaut donc `True` (flag pose)
    pour TOUS les call-sites qui passent des options nulles -- c'est-a-dire tous ceux du port SAUF
    `SwitchPositionOperation`, dont le `DisplaceUnitOperation$$SwitchPosition` natif passe un
    `MoveUnitOptions` NON nul.
    MESURE qui tranche (probe_287, `combatSnapshot.units[].unitFlags` AVANT/APRES le cast de 1100) :
    le caster TELEPORTE par le switch gagne `[ArrivedAtFinalTile, ActiveAbilityUsed, TurnFinished,
    NoActionAvailable]` et **PAS `Moved`**. Un port qui poserait `Moved` ici fermerait a tort la
    regle `CasterHasNotMoved` (0x10) de tout cast ulterieur du meme tour.

    `record_tiles` = mirror de l'octet `+0x16` du MEME `MoveUnitOptions` (case-322-r1) : le
    decompile fait `if (*(options + 0x16) == 0) { n = GetNumTilesMoved(connectedPath);
    RecordTilesMoved(unit, n, state); }`, sur les DEUX branches d'`Execute` (simulation et reelle).
    Il vaut donc `True` pour tous les call-sites a options nulles -- c'est-a-dire tout MOUVEMENT
    reel. Les call-sites de DEPLACEMENT FORCE le passent a `False`, et ce n'est pas une commodite :
    `IdunBattle.Operations.DisplaceUnitOperation$$Execute` appelle `processor.MoveUnit(...)` PUIS
    `IdunBattle.Operations.DisplaceUnitOperation$$AddTilesMoved`, qui refait lui-meme le
    `RecordTilesMoved` avec SES gates (`options+0x10` et `!IsEnemy(caster, target)` -- seul un
    deplacement AMICAL compte comme du mouvement). Si `MoveUnitOperation` enregistrait aussi, le
    natif compterait DEUX FOIS : l'octet +0x16 est precisement ce qui l'en empeche.

    `pathfinder_type_override` = mirror du `Nullable<PathfinderType>` `MoveUnitOptions+0x8`
    (#448-r1-r1-r2). `None` = le `Nullable` VIDE, ce que passent TOUS les call-sites du port sauf
    la feuille DSL `FlyUnit`, qui pose `PathfinderType.Fly`. Il n'a qu'UN lecteur, le SECOND BRAS
    d'`IdunBattle.Operations.MoveUnitOperation$$IsLikeFlying` (cf. `_is_like_flying`), donc il
    change `movementSteps` et RIEN d'autre -- surtout pas `record_tiles`/`_num_tiles_moved`, dont la
    liste (`connectedPath`) est produite par un appel a TROIS arguments qui ne voit pas les options.

    LE VECTEUR AFTER-MOVE EST JOUE ICI (#448-r1-r1-r2-r1), plus par l'appelant. Le natif l'appelle
    DANS `Execute` -- `EvaluateAfterMoveTriggers` n'a QUE DEUX xrefs dans tout le binaire, toutes
    deux dans `IdunBattle.Operations.MoveUnitOperation$$Execute` (la branche « position VIDE +
    `allowNullTargetPosition` », qui le joue avec `movementSteps = 0`, et la branche REELLE). Le
    replier dans l'Operation est donc le mirror, et c'est ce qui fait EMERGER le vecteur pour toute
    feuille DSL de mouvement au lieu de l'enumerer a la main (frontiere #149 : le vecteur est joue
    par l'Operation, en-dessous du `.Execute` de la feuille).

    `is_interim_step` = mirror de `MoveUnitOptions+0x14` -- le 6e argument d'`EvaluateAfterMoveTriggers`.
    `arrive_at_final_tile` = mirror INVERSE de `MoveUnitOptions+0x10`. Semantique des deux :
    cf. `triggers/dispatch/move_death.py::after_move_triggers`.

    `emit_after_move` N'EST PAS un octet d'options : c'est le fait, PORT-LEVEL, que le call-site
    mirroite `IdunBattle.Operations.SetUnitPositionOperation$$Execute` (le slot `SetUnitPosition` de
    l'`IOperationProcessor`) et NON `MoveUnitOperation$$Execute`. Les deux slots sont DISTINCTS et
    c'est LU : `MoveUnitBehaviour$$Execute` et la lambda de `Visit(CheatMoveUnitMessage)` prennent le
    slot `MoveUnit` (4 arguments : unit, position, triggeringAbilityOrEffect, options), tandis que
    `IdunBattle.Operations.DisplaceUnitOperation$$Execute`, `$$SwitchPosition` et
    `IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition` prennent le slot `SetUnitPosition`
    (3 arguments : unit, position, un OCTET qui gate `ResetPreviousTile`). `SetUnitPositionOperation`
    ecrit les tuiles et la « position precedente du tour », et **n'emet AUCUN event** : ni pre-move,
    ni `KillSteppableUnits`, ni `SetMovedFlag`, ni vecteur after-move. Le port utilise
    `MoveUnitOperation` comme STAND-IN a ces trois sites -- ecart PREEXISTANT et non touche par cette
    tranche ; `emit_after_move=False` empeche seulement d'y AJOUTER un vecteur que le natif n'y joue
    pas (push/pull/switch emettent le leur via `DisplaceUnitOperation$$EventAndAbilitiesAndEffects`,
    porte par `displace_triggers`).
    ⚠ Ceci CORRIGE une justification fausse portee jusqu'ici : `record_tiles=False` au push et
    `set_moved=False` au switch etaient attribues aux octets `+0x16`/`+0x11` d'un `MoveUnitOptions`
    que ces call-sites NE PASSENT PAS. Les valeurs restent JUSTES (le natif n'y fait ni l'un ni
    l'autre), la raison etait mal nommee.

    LES GATES D'ABANDON, et pourquoi `enforce_native_gates` n'est PAS `emit_after_move`
    ------------------------------------------------------------------------------------
    `MoveUnitOperation$$Execute` peut REFUSER de bouger l'unite, par DEUX gates que le port ne
    jouait pas (#448-r1-r2 et #448-r1-r1-r2-r2) :

      * `if (!TilesAreEmpty(unit, position)) { RemoveReservation ; return }` -- le SEUL gate
        d'OCCUPATION de tout `Execute` (cf. `_tiles_are_empty`), joue DANS le bloc
        `!skipPreMoveTriggers` ;
      * `if (path == null || path.Count == 0) { log ; RemoveReservation ; return }` -- la
        destination est INJOIGNABLE pour le pathfinder resolu (cf. `_calculate_path`).

    Les deux sont PERMISSIFS quand ils manquent : le port bougeait toujours, donc rien ne cassait
    et rien ne se voyait. `enforce_native_gates=False` les eteint, et il y a **deux** familles de
    call-sites qui l'exigent -- ce qui interdit de reutiliser `emit_after_move` comme
    discriminant, alors qu'il code deja « ce call-site mirroite `SetUnitPositionOperation` » :

      1. les STAND-INS de `SetUnitPositionOperation$$Execute` (push / pull / switch de
         `displace.py`, la fuite de `behaviour.py`) -- ce natif n'a NI `CalculatePaths` NI
         `TilesAreEmpty` : lui appliquer les gates inventerait un refus. Ils portent deja
         `emit_after_move=False`, mais ce n'est PAS pour cette raison-la ;
      2. `TheQuickening` (`abilities/loki/quickening.py`), qui porte `emit_after_move` a sa valeur
         par DEFAUT (le natif y joue bien le vecteur : `GetMoveInBehaviour` / `GetMoveOutBehaviour`
         sont deux des 30 call-sites de `DSLBehaviors$$MoveUnit`) et qui, POURTANT, ne peut pas
         jouer `TilesAreEmpty` : le natif fait un LIFT-OFF (`MoveUnit` vers une `UnitPosition`
         VIDE) puis un MOVE-IN, la ou le port COLLAPSE l'echange en deux mouvements directs.
         Pendant cet echange direct le caster entre sur une tuile encore occupee par l'unite
         echangee -- une geometrie que le natif ne rencontre jamais. Le collapse etait deja assume
         et ecrit (« MoveUnitOperation pose la position sans check d'occupation -> l'echange direct
         rend l'etat NET identique ») : il DEPEND de l'absence du gate. `emit_after_move` y vaut
         `True` ⇒ un gate branche dessus CASSERAIT `TheQuickening`, en silence.

    LES DEUX GATES PROPRES DE `SetUnitPositionOperation$$Execute` (#550-r4)
    ----------------------------------------------------------------------
    `enforce_native_gates=False` dit « ce call-site ne mirroite PAS `MoveUnitOperation` », ce qui est
    la bonne raison d'eteindre les SEPT gates ci-dessus -- mais ca ne dit RIEN de ce que l'autre
    natif, lui, exige. `IdunBattle.Operations.SetUnitPositionOperation$$Execute` ouvre sur DEUX gates
    a lui (cf. `_set_position_feet_count_mismatch` / `_set_position_unit_is_dead`), qu'aucun stand-in
    ne jouait. `set_unit_position_gates=True` les arme, et il faut un TROISIEME parametre parce que
    les deux familles ne coincident pas : `TheQuickening` porte `enforce_native_gates=False` sans
    mirroiter `SetUnitPositionOperation` (il mirroite bien `MoveUnitOperation`, avec un COLLAPSE), et
    `FleeOperation` ne mirroite AUCUN des deux -- son deplacement est une approximation port-level,
    le natif n'appelle ni le slot `MoveUnit` ni le slot `SetUnitPosition`. Les armer la
    inventerait un refus.

    ⚠ **CE N'EST PAS REDONDANT AVEC LE GATE `alive` DE TETE des Operations de `displace.py`**, et
    c'est le RANG qui fait la difference. Ces gates-la sont lus une fois, EN TETE ; le natif, lui,
    re-teste `HasFlag(unit, 6)` au moment de l'ECRITURE de la position. Entre les deux, le port joue
    des choses qui TUENT : le knockback de denivele (`ApplyKnockbackTo`, pull et Direct), le crush du
    steppable, et -- pour `SwitchPosition` -- le vecteur `On(UnitDisplaced)` de la PREMIERE moitie,
    qui peut tuer le caster avant la SECONDE. Dans cette fenetre, le port deplacait un cadavre que le
    natif refuse de bouger."""
    __slots__ = ("unit_id", "to", "set_moved", "record_tiles", "skip_pre_move_triggers",
                 "last_movement_steps", "pathfinder_type_override", "is_interim_step",
                 "arrive_at_final_tile", "emit_after_move", "last_after_move",
                 "last_crushed", "last_path", "last_abandoned", "enforce_native_gates",
                 "ignore_unit_movement_blockers", "allow_null_target_position",
                 "set_unit_position_gates")

    def __init__(self, unit_id: int, to: "tuple[int, int] | None", set_moved: bool = True,
                 record_tiles: bool = True, skip_pre_move_triggers: bool = False,
                 pathfinder_type_override: int | None = None,
                 is_interim_step: bool = False, arrive_at_final_tile: bool = True,
                 emit_after_move: bool = True, enforce_native_gates: bool = True,
                 ignore_unit_movement_blockers: bool = False,
                 allow_null_target_position: bool = False,
                 set_unit_position_gates: bool = False):
        self.unit_id = unit_id
        # `to is None` = la `UnitPosition` VIDE du natif (`position.Count == 0`), c'est-a-dire le
        # LIFT-OFF : l'unite QUITTE le plateau sans destination. Gardee par `allow_null_target_position`
        # (`MoveUnitOptions+0x15`), sans quoi le gate G5 `IsDisallowedEmptyPosition` refuse.
        self.to = to
        # `MoveUnitOptions+0x13` -- 3e argument d'`IdunBattle.Operations.MoveUnitOperation$$
        # IsAllowedToMove`, qui court-circuite le seul `UnitExtensions$$CanMove` (PAS `IsDead`, PAS
        # `HasFled`). `False` a tous les call-sites du port (options nulles).
        self.ignore_unit_movement_blockers = bool(ignore_unit_movement_blockers)
        # `MoveUnitOptions+0x15` -- lu DEUX FOIS par `Execute` : par le gate G5
        # `IsDisallowedEmptyPosition` (qui refuse une destination vide sans lui) et par la branche
        # `position.Count == 0`, qui RETIRE l'unite du plateau puis joue `EvaluateAfterMoveTriggers`
        # avec `movementSteps = 0`. C'est le LIFT-OFF de `TheQuickening`.
        self.allow_null_target_position = bool(allow_null_target_position)
        # Cf. le bloc « LES GATES D'ABANDON » du docstring de classe. `True` = cette instance
        # mirroite `MoveUnitOperation$$Execute` et joue donc ses DEUX gates d'abandon.
        self.enforce_native_gates = bool(enforce_native_gates)
        # Cf. le bloc « LES DEUX GATES PROPRES DE `SetUnitPositionOperation$$Execute` » (#550-r4).
        # `True` = cette instance est un STAND-IN de ce natif-la (push / pull / switch / Direct), et
        # joue donc SES deux gates. ORTHOGONAL a `enforce_native_gates` : les deux familles de
        # call-sites ne coincident pas.
        self.set_unit_position_gates = bool(set_unit_position_gates)
        self.pathfinder_type_override = (None if pathfinder_type_override is None
                                         else int(pathfinder_type_override))
        self.is_interim_step = bool(is_interim_step)
        self.arrive_at_final_tile = bool(arrive_at_final_tile)
        self.emit_after_move = bool(emit_after_move)
        # Resultat du vecteur after-move de CE mouvement (vide si aucun trigger ne matche, si le
        # mouvement n'a pas eu lieu, ou si `emit_after_move` est faux). Publie pour les appelants qui
        # le remontent dans leur payload de trace (`MovementHandler.after_move`, feuilles DSL).
        self.last_after_move: list = []
        # Trace des CRUSH joues par ce mouvement (`KillSteppableUnits`), une entree par steppable
        # ecrase — cf. `_kill_steppable_units(trace=...)`. VIDE si le mouvement n'a pas eu lieu.
        self.last_crushed: list = []
        # `path` (8e out-param de `IdunBattle.Operations.MoveUnitOperation$$CalculatePaths`),
        # materialise depuis #448-r1-r1-r2-r2 : la liste de POSITIONS, extremites incluses. `None`
        # = pas de mouvement joue par cette instance. Cf. `_calculate_path`.
        self.last_path: list | None = None
        # Le mouvement a-t-il ete ABANDONNE par un gate natif (`path` vide, `TilesAreEmpty` faux) ?
        # `None` = pas evalue (aucune tentative), sinon la RAISON du refus, ou `""` si le mouvement
        # est alle au bout. Publie pour les appelants et les tests ; le natif, lui, `return`-ait sec.
        self.last_abandoned: str | None = None
        # Le `movementSteps` que le natif passe a `IdunBattle.Operations.MoveUnitOperation$$
        # EvaluateAfterMoveTriggers` (cf. `_movement_steps`). Publie ICI parce que sa seule entree,
        # la position de DEPART, n'existe plus une fois `execute` termine -- et que le vecteur
        # after-move est joue par l'APPELANT (`MovementHandler`), comme au natif ou les deux sont
        # dans le meme `Execute`. `None` = aucun mouvement n'a ete joue par cette instance (gate
        # refuse, entite inconnue, ou destination deviee -> c'est l'operation RELANCEE qui le
        # porte) ; l'appelant threade alors un `Nullable` VIDE, ce que fait aussi le natif.
        self.last_movement_steps: int | None = None
        self.set_moved = bool(set_moved)
        self.record_tiles = bool(record_tiles)
        # mirror de l'octet `+0x12` du `MoveUnitOptions` natif -- cf. `execute` (bloc OVERRIDE).
        # `False` a TOUS les call-sites du port, comme au natif : le SEUL site qui le pose a `true`
        # est la RELANCE d'`Execute` par elle-meme apres un override de destination.
        self.skip_pre_move_triggers = bool(skip_pre_move_triggers)

    def _remove_reservation(self, state: State, position: list) -> None:
        """`IdunBattle.Operations.MoveUnitOperation$$RemoveReservation(unit, position)` :

            foreach (var tile in position) TileExtensions.RemoveReserveForUnit(tile, unit);

        Le gate d'identite est DANS `RemoveReserveForUnit` (une unite ne libere que SA propre
        reservation) -- cf. `operations/tile_reservation.py`.

        ⚠ **TROIS instructions d'appel dans le binaire, CINQ chemins logiques** -- et le compte
        « quatre call-sites » porte ici jusqu'a #448-r1-r2-r1 en OUBLIAIT un, celui de la RELANCE,
        que le port jouait pourtant deja. Les xrefs de
        `IdunBattle.Operations.MoveUnitOperation$$RemoveReservation` rendent exactement trois
        `UNCONDITIONAL_CALL`, toutes dans `IdunBattle.Operations.MoveUnitOperation$$Execute` :

          1. le LABEL D'ABANDON PARTAGE, ou convergent TROIS tests distincts du decompile --
             `TilesAreEmpty` faux, `!ovr.HasValue || IsDead(unit)`, et `path == null ||
             path.Count == 0` (ce dernier apres son log) ;
          2. la RELANCE : juste avant `options+0x12 = 1` et l'appel recursif d'`Execute` sur la
             destination deviee ;
          3. le chemin NOMINAL, apres `SetMovedFlag` / `Add(ArrivedAtFinalTile)` / le bloc
             `Nullable<AbilityOrEffect>` et AVANT le calcul de `movementSteps`.

        Le port a bien ses cinq sites (les quatre abandons + le nominal) : c'etait l'ENONCE qui
        etait faux, pas le code."""
        for t in position:
            tile_reservation.remove_reserve_for_unit(state, t, self.unit_id)

    def execute(self, state: State, bus: EventBus) -> None:
        e = state.get_entity(self.unit_id)
        if e is None:
            return
        # `position` = la `UnitPosition` de DESTINATION (une EMPREINTE, pas une tuile). Le port ne
        # materialise que la main tile ; `to is None` est la position VIDE du natif.
        position = [] if self.to is None else [(int(self.to[0]), int(self.to[1]))]
        # ── LES SEPT GATES AMONT (#448-r1-r1-r2-r2-r1) ────────────────────────────────────────────
        # Rang natif EXACT : ils tombent AVANT `IsLikeFlying`, avant `GetUnitPosition`, avant
        # l'ecriture de la destination demandee, avant `SetReservation` -- donc avant TOUTE mutation
        # et avant le vecteur `On(0x1f)`. Trois d'entre eux refusent quand ils rendent VRAI ; les
        # polarites sont celles du decompile (cf. le bloc de commentaire au-dessus des helpers).
        # Aucun n'appelle `RemoveReservation` : il n'y a encore rien de reserve.
        # Meme discriminant que les deux gates d'abandon : un call-site qui mirroite
        # `SetUnitPositionOperation$$Execute` (push/pull/switch/fuite) n'a PAS ces gates cote natif,
        # les lui appliquer inventerait un refus.
        if self.enforce_native_gates:
            if not _is_allowed_to_move(state, self.unit_id, self.ignore_unit_movement_blockers):
                self.last_abandoned = "not-allowed-to-move"                          # G1
                return
            if _unit_is_on_tiles(state, self.unit_id, position):
                self.last_abandoned = "unit-is-on-tiles"                             # G2
                return
            if not _tiles_are_walkable(state, position):
                self.last_abandoned = "tiles-not-walkable"                           # G3
                return
            if not _tiles_match_unit_feet_count(state, self.unit_id, position):
                self.last_abandoned = "feet-count-mismatch"                          # G4
                return
            if _is_disallowed_empty_position(position, self.allow_null_target_position):
                self.last_abandoned = "disallowed-empty-position"                    # G5
                return
            if _is_position_reserved_for_other_unit(state, self.unit_id, position):
                self.last_abandoned = "position-reserved"                            # G6
                return
            if _is_position_reserved_for_drafting(state, position):
                self.last_abandoned = "position-reserved-drafting"                   # G7 (inerte)
                return
        # ── LES DEUX GATES PROPRES DE `SetUnitPositionOperation$$Execute` (#550-r4) ───────────────
        # Rang natif : ils sont les DEUX PREMIERS tests de ce corps-la, avant `GetUnitPosition` et
        # avant toute reecriture de pied. Armes UNIQUEMENT par les call-sites qui mirroitent CE
        # natif (cf. le bloc de docstring) -- jamais par `enforce_native_gates`, qui code une AUTRE
        # question.
        if self.set_unit_position_gates:
            if _set_position_feet_count_mismatch(state, self.unit_id, position):
                self.last_abandoned = "set-position-feet-count-mismatch"             # S1
                return
            if _set_position_unit_is_dead(state, self.unit_id):
                self.last_abandoned = "set-position-unit-dead"                       # S2
                return
        # `On(PreUnitMove = 0x1f = 31)` — EMIS EN TETE, avant TOUTE mutation. Place native lue au
        # decompile d'`IdunBattle.Operations.MoveUnitOperation$$Execute` : le corps
        # d'`EvaluatePreMoveTriggers` y est INLINE juste apres `SetReservation` et **avant**
        # `CalculatePaths`/`MoveUnit`/`AddMoveEvent`/`KillSteppableUnits`/`UpdateCharging`/
        # `SetMovedFlag`/`EvaluateAfterMoveTriggers` -> l'unite est ENCORE sur sa tuile de depart.
        # Consommateurs : `GhostReviveAbility` (pose du time-ghost) + le 1er retrait de `GhostEffect`
        # (le poseur rebouge) + `HatefulAssaultAbility` (attaque d'opportunite). No-op si aucun
        # trigger ne matche.
        # `self.to` = la DESTINATION, passee au vecteur : le ctor nomme d'`AbilityEntities` la met a
        # la fois en `casterTiles` et en `targetTiles`, et `HatefulAssaultAbility$$CreateTrigger` la
        # compare a la tuile COURANTE de l'acteur (`NOT AreEqual(Tiles(Actor), <@+0x78>)`).
        #
        # OVERRIDE DE DESTINATION (#448-r1) -- mirror des trois etapes que
        # `IdunBattle.Operations.MoveUnitOperation$$Execute` intercale ICI, autour du vecteur :
        #   (a) AVANT les triggers, le natif pose lui-meme `comp.<+0xa8> = Nullable(
        #       UnitPositionId(position))` -- la destination DEMANDEE ;
        #   (b) le vecteur `On(0x1f)` s'execute, et un trigger PEUT ecraser ce champ via
        #       `OverrideMovementTargetOperation$$Execute` (seul ecrivain externe) ;
        #   (c) apres le vecteur, le natif RELIT le champ, le REMET A ZERO, et si la valeur relue
        #       DIFFERE de la destination demandee il RELANCE `Execute` sur la nouvelle position
        #       avec `options.skipPreMoveTriggers = true` (l'octet `+0x12`, pose juste avant
        #       l'appel recursif) -- ce qui borne la recursion a UN niveau par trigger deviant.
        # Le gate `if (!TilesAreEmpty(unit, position)) { RemoveReservation ; return }` que le natif
        # place entre (b) et (c) est PORTE depuis #448-r1-r2 (cf. `_tiles_are_empty`), sous
        # `enforce_native_gates`.
        # LA RESERVATION EST PORTEE DEPUIS #550-r1 (`operations/tile_reservation.py`) :
        # `IdunBattle.Operations.MoveUnitOperation$$SetReservation(unit, position)` pose la
        # reservation de CHAQUE tuile de la destination sur le mover, et `$$RemoveReservation` la
        # retire -- sur les TROIS chemins d'abandon du decompile (`TilesAreEmpty` faux, override
        # consomme invalide/mort, `path` vide) ET sur le chemin nominal, ou le natif la retire APRES
        # `SetMovedFlag` et AVANT le calcul de `movementSteps`. Ses lecteurs portes : le gate amont
        # G6 (`IsPositionReservedForOtherUnit`, ci-dessus) -- qui mord des qu'un trigger
        # `PreUnitMove` lance lui-meme un mouvement vers la meme tuile -- et les noeuds DSL
        # `Reserve`/`RemoveReservation` (`abilities/behaviours/movement.py`).
        # ⚠ `()` N'EST PAS `None` ICI, et la distinction est LUE. Le natif pose
        # `Nullable(UnitPositionId(position))` : sur une position VIDE le `Nullable` a quand meme
        # une VALEUR (un `UnitPositionId` d'empreinte vide), donc `ovr.HasValue` est VRAI et le gate
        # (c) `if (!ovr.HasValue || IsDead) return` ne mord PAS. Le port code donc « override pose,
        # empreinte vide » par le tuple VIDE et « aucun override » (le `Nullable` vide, que seule la
        # consommation en (c) produit) par `None`. Les confondre ferait retomber tout LIFT-OFF sur le
        # bras `ovr is None` -> `return`, c'est-a-dire un refus silencieux.
        uc0 = e.get_component(UnitComponent)
        if uc0 is not None:
            uc0.movement_target_override = (() if self.to is None
                                            else (int(self.to[0]), int(self.to[1])))   # (a)
        for _t in position:                                                            # SetReservation
            tile_reservation.reserve_for_unit(state, _t, self.unit_id)
        if not self.skip_pre_move_triggers:
            # PORTEUR (cycle `operations` <-> `triggers`) ET forme MODULE : l'attribut est relu
            # a l'appel, donc une substitution posee sur `move_death` mord quelle que soit la
            # forme finale de cet import. Cf. `probe_485r1r1_formes_dimport.py` -- un
            # `from ... import pre_move_triggers` hisse deviendrait INERTE, en silence.
            from .triggers.dispatch import move_death
            move_death.pre_move_triggers(state, self.unit_id,
                                         dest_tile=(None if self.to is None
                                                    else tuple(self.to)))         # (b)
            # `if (!TilesAreEmpty(unit, position)) { RemoveReservation ; return }` -- RANG NATIF
            # EXACT : DANS le bloc `!skipPreMoveTriggers`, donc la RELANCE apres deviation ne le
            # rejoue PAS (le natif y pose `options+0x12 = 1`). C'est LU, pas choisi : le gate est
            # a l'interieur des accolades du `if`, comme `On(0x1f)`.
            # Sur une position VIDE la boucle native ne tourne pas -> `true` (`_tiles_are_empty`
            # rend `True` sur `dest_tile is None`, deja son comportement).
            if self.enforce_native_gates and not _tiles_are_empty(state, self.unit_id, self.to):
                self.last_abandoned = "tiles-not-empty"
                self._remove_reservation(state, position)
                return
        if uc0 is not None:                                                        # (c)
            ovr = uc0.movement_target_override
            uc0.movement_target_override = None                # CONSOMME (le natif remet a zero)
            # `if (!ovr.HasValue || UnitExtensions.IsDead(unit)) { RemoveReservation ; return }` --
            # les DEUX bras du gate natif. Le second n'est pas theorique : un trigger `PreUnitMove`
            # peut TUER le mover (`...StormboyzStrike_MissAbility` -> `TriggerAbility(FullThrottle)`
            # -> `If(Maybe(chance), Kill(Caster))`), et le natif annule alors le mouvement.
            if ovr is None or not uc0.alive:
                self._remove_reservation(state, position)
                return
            # `if (ToUnitPosition(ovr) != position)` -- comparaison d'EMPREINTES, pas de tuiles :
            # `()` (le lift-off) egale `[]`, et un `(col,row)` egale `[(col,row)]`.
            ovr_position = [] if len(ovr) == 0 else [(int(ovr[0]), int(ovr[1]))]
            if ovr_position != position:
                self._remove_reservation(state, position)
                # Le natif RECOPIE la struct `options` telle quelle dans l'appel recursif (il n'y
                # touche que pour poser `+0x12 = 1`), donc l'override de pathfinder SURVIT a la
                # deviation -- comme `set_moved` et `record_tiles`.
                sub = MoveUnitOperation(self.unit_id, (int(ovr[0]), int(ovr[1])),
                                        set_moved=self.set_moved, record_tiles=self.record_tiles,
                                        skip_pre_move_triggers=True,
                                        pathfinder_type_override=self.pathfinder_type_override,
                                        is_interim_step=self.is_interim_step,
                                        arrive_at_final_tile=self.arrive_at_final_tile,
                                        emit_after_move=self.emit_after_move,
                                        enforce_native_gates=self.enforce_native_gates,
                                        ignore_unit_movement_blockers=self.ignore_unit_movement_blockers,
                                        allow_null_target_position=self.allow_null_target_position)
                sub.execute(state, bus)
                # Le natif RELANCE `Execute` sur la nouvelle destination et c'est CET appel-la qui
                # calcule son `movementSteps` et joue le vecteur after-move : on remonte donc la
                # valeur de la relance, jamais celle du mouvement abandonne.
                self.last_movement_steps = sub.last_movement_steps
                self.last_after_move = sub.last_after_move
                self.last_crushed = sub.last_crushed
                self.last_path = sub.last_path
                self.last_abandoned = sub.last_abandoned
                return
        # ── E8 : LA BRANCHE `allowNullTargetPosition` (#448-r1-r1-r2-r2-r1) ───────────────────────
        # RANG NATIF EXACT : APRES le bloc override, AVANT `CalculatePaths`. Lu verbatim :
        #
        #     if (position.Count == 0) {
        #         if (!options.<+0x15>) throw;                        // G5 l'a deja refuse
        #         processor.<slot 7>(unit, removeTileFromUnit: true); // = RemoveUnitFromTiles
        #         // ⚠ ce qui suit N'EST PAS la resolution du slot 7 : `EvaluateAfterMoveTriggers`
        #         // est une methode de `MoveUnitOperation` LUI-MEME, pas un slot du processor.
        #         EvaluateAfterMoveTriggers(unit, position, previousPosition, movementSteps: 0,
        #                                   isInterimStep: options.<+0x14>, triggeringAbilityOrEffect);
        #         return;
        #     }
        #
        # Le slot **7** de l'`IOperationProcessor` est celui de `RemoveUnitFromTiles(unit, bool)` --
        # LU par recoupement : `IdunBattle.Entities.Behaviours.RemoveUnitFromItsTilesBehaviour$$Execute`
        # appelle le MEME slot avec la MEME signature `(unit, <bool>)`, et le port en a deja le mirror
        # (`operations/remove_unit_from_tiles.py`).
        #
        # C'EST LE LIFT-OFF : l'unite quitte le plateau, sans mourir, sans `SetMovedFlag`, sans
        # `KillSteppableUnits`, sans `UpdateCharging`, sans `RecordTilesMoved`, sans `RefreshEffects`
        # -- rien de la sequence nominale, SAUF le vecteur after-move, joue avec `movementSteps = 0`.
        # C'est la premiere moitie de `TheQuickening` (`MoveUnit(caster, <position vide>)` puis
        # `MoveIn`), que le port COLLAPSE aujourd'hui en deux mouvements directs
        # (`abilities/loki/quickening.py`, `enforce_native_gates=False`).
        if not position:
            self.last_abandoned = ""
            self.last_path = None                    # aucun `CalculatePaths` sur cette branche
            self.last_movement_steps = 0             # le litteral du call-site natif
            RemoveUnitFromTilesOperation.execute(state, self.unit_id,
                                                 remove_tile_from_unit=True)
            if self.emit_after_move:
                from .triggers.dispatch import move_death
                self.last_after_move = move_death.after_move_triggers(
                    state, self.unit_id, movement_steps=0,
                    is_interim_step=self.is_interim_step,
                    arrive_at_final_tile=self.arrive_at_final_tile)
            # Pas de `RemoveReservation` ici : `position` est VIDE, `SetReservation` n'a rien pose.
            return
        pc = e.get_component(PositionComponent)
        old_pos = (pc.col, pc.row) if pc is not None else None
        # `CalculatePaths(...)` puis le GATE D'ABANDON, au RANG NATIF : le natif les place APRES le
        # bloc override et AVANT `processor.SetUnitPosition` -- donc avant toute mutation. Lu
        # verbatim (`IdunBattle.Operations.MoveUnitOperation$$Execute`) :
        #
        #     CalculatePaths(this, unit, movementStartPosition, previousPosition, startTile,
        #                    endTile, options, out path, out connectedPath);
        #     if (path == null || path.Count == 0) {
        #         logger.Log(<StackDict unitName/startTile/endTile>, 0x17, 4);
        #         RemoveReservation(unit, position);
        #         return;                          // <- L'UNITE NE BOUGE PAS
        #     }
        #
        # Le log natif (`AOperation.get_Logger` + un `StackDict` a trois entrees) n'est pas porte :
        # le runner n'a pas de canal de journal, comme partout ailleurs dans `operations/`. La
        # RAISON est publiee a la place (`last_abandoned`).
        self.last_path = _calculate_path(state, self.unit_id, old_pos, self.to,
                                         self.pathfinder_type_override)
        if self.enforce_native_gates and not self.last_path:
            self.last_abandoned = "path-empty"
            self._remove_reservation(state, position)
            return
        self.last_abandoned = ""
        # ── `connectedPath` : LE SECOND OUT-PARAM, MESURE ICI ET UNE SEULE FOIS (#448-r1-r1-r3) ───
        # RANG NATIF EXACT. `CalculatePaths` produit `path` ET `connectedPath` **dans le meme
        # appel**, avant que quoi que ce soit n'ait bouge ; `Execute` ne les CONSOMME que bien plus
        # bas (`movementSteps` puis `RecordTilesMoved`), mais sur des listes deja FIGEES. Le port
        # appelait `_num_tiles_moved` DEUX FOIS -- ici, puis sous `record_tiles_moved`, APRES
        # `SetUnitPosition`, `KillSteppableUnits` et toute la cascade de mort du crush.
        #
        # ⚠ CE N'ETAIT PAS QU'UN COUT. `_num_tiles_moved` est pure EN SES ARGUMENTS mais LIT
        # `state` : `_blocking_positions` derive des occupants ENNEMIS VIVANTS. Si la cascade de
        # mort tue, ressuscite ou deplace un bloqueur -- le blast radius de
        # `#462-r4b-r1-r1-r1-r1-c-r3-r1-r6`, quatre classes reelles -- la seconde lecture rend un
        # AUTRE compte que celui que le natif a fige. MESURE (`probe_448r1r1r3_double_parcours.py`,
        # `C4_09`, `(0,0) -> (0,2)` avec un bloqueur en `(0,1)`) : le port enregistrait
        # `tiles_moved = 2` la ou le natif ecrit `10`, pendant que `movement_steps` restait a `11`
        # -- c'est ce dernier, INCHANGE, qui etablit que la cause est le RANG et non la geometrie.
        #
        # ⚠ ON NE DESCEND PAS SOUS **DEUX** parcours, et c'est LU : `CalculatePaths` appelle
        # `Pathfinders.<slot 4>(pathfinderType, unit, from, to, useTeleporter)` PUIS
        # `BattleQuery.<slot 0x15>(unit, from, to)` -- deux parcours natifs distincts, dont le
        # second ne voit NI les options NI l'override. Deriver le compte de `self.last_path`
        # ferait passer l'override dans `connectedPath` : INFIDELE (cf. `_movement_steps`).
        #
        # Le calcul est saute quand AUCUN lecteur n'en a besoin -- condition etablie AVANT toute
        # mutation, donc insensible a ce que la cascade fera : `record_tiles` est un octet
        # d'options, et la branche VOLANTE de `movementSteps` rend une DISTANCE sans lire ce compte.
        _sc_ms = e.get_component(StatsComponent)
        _traits_ms = getattr(_sc_ms.ctx, "traits", None) if _sc_ms is not None else None
        _lit_le_compte = self.record_tiles or not _is_like_flying(_traits_ms,
                                                                  self.pathfinder_type_override)
        num_tiles = (_num_tiles_moved(state, self.unit_id, old_pos, self.to)
                     if _lit_le_compte else 0)
        # `movementSteps` -- calcule AVANT la mutation de position (`old_pos` est son entree), comme
        # le natif qui derive `path` de `CalculatePaths(startTile = position.MainTile, ...)` avant
        # de bouger l'unite.
        self.last_movement_steps = _movement_steps(state, self.unit_id, old_pos, self.to,
                                                   self.pathfinder_type_override,
                                                   num_tiles_moved=num_tiles)
        if pc is None:
            # Unite SANS position : soit un spawn, soit -- depuis #448-r1 -- une unite qui REVIENT
            # sur le plateau (`RemoveUnitFromItsTiles` lui avait pose `feet = []`, cf.
            # `set_unit_feet`). Passer par l'ECRIVAIN UNIQUE de l'empreinte au lieu d'ajouter la
            # seule `PositionComponent` : une liste d'UN element repose `feet = None` (= « un pied,
            # a la PositionComponent ») et recale la position. Sans ca l'unite atterrit avec
            # `feet == []` et reste INVISIBLE a l'occupation (`CanAddUnit`, `_occupied`), qui lisent
            # l'empreinte. Strictement equivalent a l'ancien `add_component` quand `feet` etait
            # deja `None` (le cas du spawn) -- c'est un sur-ensemble, pas un changement de chemin.
            set_unit_feet(state, self.unit_id, [(int(self.to[0]), int(self.to[1]))])
        else:
            # `IdunBattle.Operations.SetUnitPositionOperation$$SavePreviousPosition(unit,
            # previousPosition)` -- l'EMPREINTE QUITTEE est memorisee dans
            # `PositionComponent.previous` (`+0x88`) AVANT l'ecriture de la nouvelle position.
            # C'est ce que lit le selecteur `PreviousTile`, et le seul poseur de mine du binaire
            # (`HaywireMineAbility`) en depend entierement.
            # POSE ICI, et pas dans une operation dediee : le port utilise `MoveUnitOperation` comme
            # STAND-IN d'`IdunBattle.Operations.SetUnitPositionOperation$$Execute` (cf. le bloc
            # `emit_after_move` du ctor), donc son ECRITURE DE POSITION est le foyer unique -- il n'y
            # a pas d'autre endroit ou la position d'une unite change.
            # ⚠ Le gate natif est `previousPosition.Count >= 1` : une empreinte VIDE n'ecrit RIEN
            # (il est porte dans `save_previous_position`), et l'unite SANS position (branche
            # ci-dessus, spawn ou retour sur le plateau) n'en a pas -> `previous` reste vide, ce qui
            # est exactement le `Nullable` VIDE du natif.
            uc_prev = e.get_component(UnitComponent)
            feet_prev = list(getattr(uc_prev, "feet", None) or ()) if uc_prev is not None else []
            save_previous_position(state, self.unit_id, feet_prev or [old_pos])
            pc.col, pc.row = self.to
        # #198 : materialisation DYNAMIQUE du stat-mod DEFENSE de tuile (Thorns/famille). En quittant/
        # entrant une tuile a stat-mod DEFENSE, l'occupant non-Immune gagne/perd la modification (mirror
        # ThornsDefenseReductionEffect apply-on-enter/revert-on-leave). No-op hors terrain a stat-mod /
        # sans board / Immune. On saute un ajout d'entite (pc None = spawn, pas un move de tuile-a-tuile).
        if old_pos is not None:
            from .triggers.tiles import apply_tile_defense_on_move
            apply_tile_defense_on_move(state, self.unit_id, old_pos, self.to)
        # G1 (gen-stealer) `IdunBattle.Operations.MoveUnitOperation$$KillSteppableUnits` : INLINE ici, dans l'ordre natif (AddMoveEvent ->
        # **KillSteppableUnits** -> EvaluateAfterMoveTriggers). Un occupant Steppable (decoy, spore-mine) de la
        # tuile d'arrivée est crushé (kill propre, pas de death-trigger) AVANT que le vecteur after-move
        # (visit_MoveUnitMessage -> after_move_triggers) ne s'exécute -> le decoy est déjà mort pour G2.
        # `last_crushed` (#462-r4b-r1-r1-r1-r1-c-r3-r1-r4-r3) : le natif rend `void` et sa trace ne
        # s'observait qu'a la SOURCE de l'ability consommatrice ; on la PUBLIE ici. Ecart
        # d'OBSERVABILITE uniquement -- l'etat produit est identique.
        self.last_crushed = []
        _kill_steppable_units(state, self.to, self.unit_id, trace=self.last_crushed)
        # `IdunBattle.Operations.MoveUnitOperation$$UpdateCharging` — RANG NATIF EXACT (le decompile
        # d'`IdunBattle.Operations.MoveUnitOperation$$Execute` l'appelle entre `KillSteppableUnits` et
        # `SetMovedFlag`). Enregistre sur le mover les unites NOUVELLEMENT adjacentes apres ce pas :
        # c'est la moitie runtime du predicat `BattleQuery$$IsCharging` (TacticalPrecision, case-231).
        # `old_pos is None` (unite sans position avant : spawn) -> mirror du `MainTile == null` natif.
        update_charging(state, self.unit_id, old_pos, self.to)
        # #101 : `SetMovedFlag(unit)` — le natif pose ici le `UnitFlag.Moved` (+ `Teleported` si le move
        # est un teleport-strike). POSITION NATIVE lue au decompile d'`IdunBattle.Operations.
        # MoveUnitOperation$$Execute` : AddMoveEvent(s) -> KillSteppableUnits -> UpdateCharging ->
        # **SetMovedFlag** (gate par l'option `MoveUnitOptions` @+0x8, nulle a tous les call-sites du
        # port -> flag TOUJOURS pose) -> Add(ArrivedAtFinalTile=1) [non porte] -> after-move triggers.
        # C'est LE store unique du fait "a bouge ce tour" (lu par `unit_has_moved`), purge par le
        # `RemoveTurnFlags` du StartTurnOperation. (#60 posait un set `state.moved_this_turn` PARALLELE
        # au composant natif -> fork de port : deux representations du meme flag, l'une jamais posee par
        # le move, l'autre jamais lue par le gate no-move.)
        # ⚠ Le gate `MoveUnitOptions+0x11` du natif est desormais MODELISE (`set_moved`, cf. le ctor) :
        # le seul call-site qui le pose est `SwitchPositionOperation` (mesure live #287).
        if self.set_moved:
            set_moved_flag(state, self.unit_id)
        # `RemoveReservation(unit, position)` du chemin NOMINAL -- RANG NATIF EXACT : le decompile
        # l'appelle APRES `SetMovedFlag` / `Add(UnitFlag.ArrivedAtFinalTile)` / le bloc
        # `Nullable<AbilityOrEffect>` et AVANT le calcul de `movementSteps` et `RecordTilesMoved`.
        # Le rang compte : entre `SetReservation` et ici, tout trigger `PreUnitMove` qui tenterait de
        # bouger une autre unite vers la MEME tuile est refuse par le gate G6.
        self._remove_reservation(state, position)
        # case-322-r1 : `RecordTilesMoved(unit, GetNumTilesMoved(connectedPath), state)`. RANG NATIF
        # EXACT, lu au decompile d'`IdunBattle.Operations.MoveUnitOperation$$Execute` : le bloc
        # tombe APRES `SetMovedFlag` / `Add(ArrivedAtFinalTile)` / `RemoveReservation` et AVANT le
        # `RefreshEffects(RefreshTrigger.UnitPositionChanged = 7)` -- c'est-a-dire avant les deux
        # rafraichissements ci-dessous, ce qui est necessaire : la `CreateActiveCondition` de
        # `ModifiedExoarmour_ExtraDmg` (`AmountIsGreaterThanZero(TilesMovedThisTurn)`) est
        # justement l'une des conditions que ce refresh reevalue.
        # ⚠ La branche REELLE n'a PAS le gate `HasTriggeredAbility(0x5f9)||(0x4de)` de
        # `MoveUnitOperation$$GetNumTilesMovedForSimulation` : ce gate n'existe QUE cote SIMULATION
        # (economie de pathfinding). Un mouvement JOUE compte ses tuiles pour TOUTE unite.
        # `RecordTilesMoved` fait `+=` sur `+0xec` ET `+0xf0`, et no-op si le compte est < 1.
        # ⚠ LE COMPTE EST CELUI DE `num_tiles`, PRIS AU RANG DE `CalculatePaths` (#448-r1-r1-r3) --
        # PAS un recalcul. Le natif lit ici un `connectedPath` produit avant `SetUnitPosition` ; le
        # re-deriver a ce rang-ci le ferait porter sur un plateau que `KillSteppableUnits` et sa
        # cascade de mort ont deja change. Cf. le bloc de mesure au-dessus de `_calculate_path`.
        if self.record_tiles:
            record_tiles_moved(state, self.unit_id, num_tiles)
        # AURA stat-mod PROJETEE — `UpdateEffectTargets` : le selecteur d'un `AStatModifierEffect` a
        # projection est purement GEOMETRIQUE, donc un move le change. Le natif re-evalue et
        # applique/reverte la `ValueModification` chez les cibles. GROUND TRUTH live (statModSources,
        # LionHelm) : l'allie eloigne PERD ses +797 blockDamage, il les RETROUVE en revenant.
        # No-op strict sans porteur d'aura stat-mod (le mover ET les cibles du porteur sont re-evalues,
        # d'ou l'appel non scope : bouger le PORTEUR change l'ensemble de ses cibles).
        refresh_aura_stat_modifiers(state)
        # `RefreshEffectTrigger.UnitPositionChanged` (= 7, dump d'enums du build : 0=Forced
        # 1=Simulation 2=Custom 3=UnitStateChanged 4=EffectsChanged 5=UnitsChanged 6=TurnChanged
        # **7=UnitPositionChanged** 8=MatchStart) -> `IdunBattle.Operations.RefreshEffectsOperation
        # $$Execute` avec un `effectEntity` NUL, c'est-a-dire sur TOUS les effets de la bataille :
        # chacun voit sa `CreateActiveCondition` reevaluee par
        # `RefreshEffectsOperation$$ShouldBeActive`, et bascule ACTIVE <-> INERTE avec
        # `ApplyModification`/`RevertModification` a la cle.
        # C'est le volet PORTEUR de la meme donnee que `refresh_aura_stat_modifiers` juste au-dessus
        # (celui-la couvre les stat-mods PROJETES, dont le selecteur est geometrique ; celui-ci les
        # stat-mods poses SUR une unite dont la CONDITION est geometrique). Cas porte :
        # `ContagionsOfNurgle_ArmorReduction1/2` — un pas qui fait entrer/sortir du disque d'aura
        # ennemi fait entrer/sortir le -20 %/-40 % de `FixedArmor`.
        # Non-scope (pas de `unit_id`) POUR LA MEME RAISON que la ligne precedente : bouger le
        # PORTEUR d'aura change la condition des AUTRES unites, pas la sienne. Idempotent partout
        # ailleurs (`Modify` = replace par-source, cf. `refresh_effects.py`).
        # ⚠ Le declencheur n'est plus seulement en COMMENTAIRE : depuis #477-r21-r2 volet A il est
        # PASSE, et `RefreshEffectsOperation$$ShouldBeActive` le consomme (via
        # `BaseEffect$$ShouldRefreshForTrigger`) pour choisir entre re-evaluer la
        # `CreateActiveCondition` et re-emettre le flag courant.
        refresh_stat_modifier_effects(state, refresh_trigger=RefreshEffectTrigger.UnitPositionChanged)
        # `EvaluateAfterMoveTriggers(unit, position, previousPosition, movementSteps, isInterimStep,
        # triggeringAbilityOrEffect)` -- RANG NATIF EXACT, lu au decompile d'`IdunBattle.Operations.
        # MoveUnitOperation$$Execute` : il tombe ENTRE les deux `RefreshEffects({7, null})`, apres
        # `RecordTilesMoved` et `Add(UnitFlag.ArrivedAtFinalTile)`. Ses DEUX seuls call-sites du
        # binaire sont dans cet `Execute` -> replier le vecteur ICI est le mirror, et c'est ce qui
        # le fait EMERGER pour toute feuille DSL de mouvement (`FlyUnit`, `MoveUnit`) au lieu de
        # l'enumerer a la main chez chaque appelant (#448-r1-r1-r2-r1).
        # `On(0x1c = ArrivedAtFinalTile)` est en QUEUE du vecteur porte (le natif le publie apres
        # `EvaluateAfterMoveTriggers`, gate par le `bool` qu'a rendu `UnitFlagsComponent.Add(1)`).
        if self.emit_after_move:
            # forme MODULE, meme raison qu'en (b) : l'attribut est relu a l'appel.
            from .triggers.dispatch import move_death
            self.last_after_move = move_death.after_move_triggers(
                state, self.unit_id, movement_steps=self.last_movement_steps,
                is_interim_step=self.is_interim_step,
                arrive_at_final_tile=self.arrive_at_final_tile)
            refresh_effects_after_move_triggers(state)   # 2e `RefreshEffects({7, null})` natif
        # `AddMoveEvent` par pas : NON PORTE, et ce n'etait PAS a porter (#448-r1-r1-r2-r2). Le
        # decompile d'`IdunBattle.Operations.MoveUnitOperation$$AddMoveEvent` ne touche AUCUN
        # composant ECS : il construit un `Dictionary<int,int>` (`0x79` pathTile, `0x80` isLastTile,
        # `0x7a..0x7f` les pieds 1..6) et le pousse dans `AOperation.get_Events()` par
        # `AddStep(3, unit.Id, dict)`. Ses seules autres operations sont des LECTURES
        # (`HasTrait(unit, 0x13 = Burrow)`, `IsTeleportationTile`). Canal de VUE, comme le step
        # `0x25` d'`OverrideMovementTargetOperation` et le `Inform{0x79}` du Miss.


def refresh_effects_after_move_triggers(state: State) -> list:
    """SECOND `RefreshEffects(RefreshEffectTrigger.UnitPositionChanged = 7)` d'
    `IdunBattle.Operations.MoveUnitOperation$$Execute` (case-366-r1-camo-seed).

    Le natif appelle **DEUX FOIS** le slot `RefreshEffects` de l'`OperationProcessor`
    (`Core.Services.OperationProcessor$$RefreshEffects(refreshOptions)`) autour du vecteur
    after-move, avec la MEME valeur `{trigger = 7, effectEntity = null}` -- lu au desassemblage,
    les deux `FUN_180028040(0x2f, .., processor, &{7,0})` ENCADRENT l'appel a
    `MoveUnitOperation$$EvaluateAfterMoveTriggers` :

        ... RecordTilesMoved
        RefreshEffects({7, null})              <- #1 : porte par `MoveUnitOperation.execute`
        EvaluateAfterMoveTriggers(...)         <- porte par les appelants (`after_move_triggers`)
        [ On(0x1c = ArrivedAtFinalTile) ]
        RefreshEffects({7, null})              <- #2 : CETTE fonction

    POURQUOI LE SECOND N'EST PAS REDONDANT. `EvaluateAfterMoveTriggers` emet `On(0x24 =
    UnitPositionChanged_1)`, et c'est LUI qui fait poser les effets d'ARRIVEE -- au premier chef
    `1013 LightCover` par `IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility`
    (`triggers/tiles.py::light_cover_on_enter`). Or `1013` est justement l'ENTREE que lit la
    `CreateActiveCondition` d'un autre effet : `IdunBattle.Entities.Effects.Loki.
    CamoCloak_DmgReductionEffect$$CreateActiveCondition` = `HasEffect(Owner, 0x3f5)
    | IsEffectTarget(Owner, 0x402)`. Au refresh #1 le couvert n'est PAS encore pose : la condition
    est FAUSSE. Sans le refresh #2, le flag `EffectComponent.IsActive @+0x5c` reste a 0 pour tout
    le reste du pas, et `EffectsState.active_effects` (qui exige `e.active` ET `is_active`) tait
    l'effet -- alors que le natif, lui, vient de le RALLUMER.

    MESURE (`probe_366_r1_camo_seed.py`, `C4_09`/4242, Certus capte HORS couvert puis DEPLACE
    dessus) : apres le pas, port `cond_is_active = True` mais `flag_active = False` ->
    `in_active_effects = False`, la ou le canal ACTIF-ONLY du natif publie `1014` avec
    `active: true`. Degat live 31907 contre port 32655.

    Le corps est le MEME driver que le refresh #1 (`refresh_stat_modifier_effects`, le producteur
    porte du flag) : `Modify` etant un replace par-source, un second passage est un NO-OP exact
    partout ou rien n'a change entre les deux -- y compris aux sites qui n'ont PAS de vecteur
    after-move (`DisplaceUnitOperation`, `TheQuickening`, genestealer), qu'on laisse donc
    inchanges."""
    return refresh_stat_modifier_effects(
        state, refresh_trigger=RefreshEffectTrigger.UnitPositionChanged)


class MovementHandler:
    """Visiteur des messages de mouvement (mirror du handler natif qui lance
    MoveUnitOperation). Lié à l'état/bus du runner. `after_move` = résultats du vecteur after-move
    (effet-triggers ; ex. Overwatch) du dernier move."""
    __slots__ = ("state", "bus", "after_move")

    def __init__(self, state: State, bus: EventBus):
        self.state = state
        self.bus = bus
        self.after_move: list = []          # cascade after-move (overwatch…) du dernier move

    def visit_MoveUnitMessage(self, msg) -> None:
        # Le mouvement JOUEUR passe des `MoveUnitOptions` entierement NULLES (lu : la lambda de
        # `Visit(CheatMoveUnitMessage)` n'y pose que le `Nullable<PathfinderType>` de `+0x08`, et le
        # bras MARCHEUR de #448-r1-r1-r1-r1 corrobore que le move ordinaire n'a AUCUN override)
        # -> tous les defauts du ctor. Le vecteur after-move est desormais joue PAR L'OPERATION, au
        # rang natif (#448-r1-r1-r2-r1) ; ce handler ne fait plus que republier son resultat, que
        # lisent les probes (`probe_lionhelm_overwatch`, `probe_366_r1_blockhits_purgeresponse`).
        op = MoveUnitOperation(msg.unit_id, msg.to)
        op.execute(self.state, self.bus)
        self.after_move = op.last_after_move
