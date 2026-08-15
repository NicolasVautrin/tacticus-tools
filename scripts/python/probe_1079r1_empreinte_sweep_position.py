"""#1079-r1 -- MESURE : le sweep de position d'un caster MULTI-HEX ecartait-il les positions
que le natif n'aurait jamais produites ?

CE QUE LE NATIF FAIT, lu sur `t6dpr4k06g` (chaine complete, aucun maillon deduit) :

    IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor(unit, flags, options)
        set = new OrderedSet<UnitPosition>( EntityExtensions$$GetUnitPosition(unit) )
        set.UnionWith( <IMovementQuery slot> GetMovablePositionsFor(unit, flags, &options) )

    IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFor(unit, flags, options)
        if (UnitExtensions$$HasTrait(unit, 0x418)) return new OrderedSet<UnitPosition>();
        feetCount = UnitExtensions$$GetFeetCount(unit, state);
        movable   = GetMovableTilesFor(unit, flags, options);          // flood-fill MAIN TILES
        movable.AddRange( EntityExtensions$$IterateTiles(unit, state) );
        return GetMovablePositionsFromTiles(movable, feetCount);

    IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFromTiles(movable, feetCount)
        if (movable.Count == 0) return new OrderedSet<UnitPosition>();
        if (feetCount == 1)     return UnitPositionExtensions$$ToUnitPositionList(movable);
        foreach (combo in GetPossibleTileListsFromMovableTiles(movable, feetCount))
            if (IsValidUnitFeetList(feetCount, combo)) res.Add(new UnitPosition(combo));

    IdunBattle.Core.Services.MovementQuery$$GetPossibleTileListsFromMovableTiles(movable, numFeet)
        numFeet == 1 / 3 -> TExtensions$$GetKCombs(movable, 1 / 3)
        numFeet == 7     -> foreach t in movable:
                                adj = <IBattleQuery slot 0x4f> GetAdjacentTiles(t, 0, 1, 1)
                                if (CollectionExtensions$$ContainsAll(movable, adj))
                                    res.Add( OrderedSet{t} + adj )      // CENTRE en TETE
        autre            -> null

Le `ContainsAll` est le gate que #1079-r1 accuse : une `UnitPosition` a sept pieds n'existe pas si
un SEUL pied ne tient pas. `IsValidUnitFeetList` en rajoute un second, non nomme par la fiche :
l'ELEVATION doit etre HOMOGENE sur toute l'empreinte.

CE QUE CE PROBE MESURE : sur un plateau MONTE pour que la difference existe (murs + marche
d'elevation), il compare le sweep d'AVANT (flood-fill de main tiles, non filtre) a celui
d'APRES, et VENTILE chaque position ecartee par la CAUSE qui l'ecarte. Un ecart PERMISSIF est
invisible en self-play : il faut donc que le temoin soit NON DEGENERE -- la difference doit etre
non vide, et ce probe echoue si elle l'est.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

import hexgeo                                                              # noqa: E402
from engine.ai import state_bridge as SB                                   # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.components import (PositionComponent, UnitComponent,    # noqa: E402
                                      OwnerComponent, set_unit_feet, get_feet_count)
from engine.runner.state import State                                      # noqa: E402
from engine.services import movement_query as MQ                           # noqa: E402

COLS, ROWS = 11, 11


def board_plat(elev_overrides=None, unplayable=()) -> Board:
    """Plateau plat COLSxROWS, adjacence `evenq`, voisinage NATIF rempli.

    `unplayable` retire la MARCHABILITE, jamais l'arete -- le capteur `boardGraph` appelle
    `BattleQuery$$GetAdjacentTiles(tile, false, false, true)` (`requireWalkable = 0`)."""
    idof, tiles, tid = {}, [], 1
    for c in range(COLS):
        for r in range(ROWS):
            idof[(c, r)] = tid
            tid += 1
    for (c, r), i in idof.items():
        tiles.append({
            "id": i, "col": c, "row": r,
            "elevation": (elev_overrides or {}).get((c, r), 0),
            "tileDefId": "Grass", "isTemporary": False, "isWall": (c, r) in unplayable,
            "walkable": (c, r) not in unplayable, "occupantUnitId": None,
            "neighbours": [idof[n] for n in hexgeo.neighbors(c, r) if n in idof],
        })
    return Board(tiles, adjacency="evenq")


def monte(board, centre, movement=3, feet=True):
    """Un `State` avec UNE unite (7 pieds si `feet`), au centre donne. Movement pose en dur sur le
    gameconfig etant impossible ici, on passe par `override_range` du call-site."""
    st = State()
    st.board = board
    e = st.add_entity(7)
    e.add_component(UnitComponent(visual_id="deathBossMortarion", alive=True))
    e.add_component(OwnerComponent(team=0, player=0))
    e.add_component(PositionComponent(centre[0], centre[1]))
    if feet:
        ring = [board.coord(t) for t in board.neighbours_native(board.id_at(*centre))]
        set_unit_feet(st, 7, [centre] + ring)
    return st


def _flood_brut(st, board, centre, movement):
    """Le sweep d'AVANT #1079-r1 : le flood-fill de MAIN TILES, sans aucun etage d'empreinte.
    Recalcule ici a l'identique plutot que lu depuis un `_move_tiles` d'archive."""
    from engine.entities.pathfinding.pathfinders import movable_positions_for_unit
    from engine.entities.pathfinding.tile_blocking import make_can_continue
    from engine.services.movement_query import unit_has_effect_fn
    _cc = make_can_continue(st.effects, [], board=board)
    _, stop = movable_positions_for_unit(
        board, board.id_at(*centre), movement, SB._occupants(st), 0, traits=[],
        has_effect=unit_has_effect_fn(st, 7), can_continue=_cc)
    return [board.coord(t) for t in stop]


def _cause(board, pool, t) -> str:
    """POURQUOI le natif ecarte la position centree sur `t` -- ventilation par ETAGE, jamais un
    verdict global. `pool` = `movable U IterateTiles`, l'ensemble que le `ContainsAll` interroge."""
    adj = [board.coord(x) for x in MQ.adjacent_tile_ids(board, t)]
    if not adj:
        return "aucune voisine (GetAdjacentTiles vide)"
    dehors = [x for x in adj if x not in pool]
    if dehors:
        return "ContainsAll: %d voisine(s) hors du pool %s" % (len(dehors), sorted(dehors)[:3])
    if not MQ.is_valid_unit_feet_list(board, 7, [t] + adj):
        return "IsValidUnitFeetList: elevation heterogene ou empreinte != 7"
    return "??? (aucune cause identifiee -- LIRE le decompile)"


def main() -> int:
    print("=" * 96)
    print("#1079-r1 -- ETAGE EMPREINTE du sweep de position (caster MULTI-HEX)")
    print("=" * 96)

    # MONTAGE : deux causes d'ecart, posees SEPAREMENT pour qu'elles se ventilent.
    #  * un mur en (7,5) -> ses voisines perdent leur `ContainsAll` par la MARCHABILITE ;
    #  * une marche d'elevation en (3,5) -> `GetAdjacentTiles` la retire du ring-1 (|dElev| >= 2)
    #    ET `IsValidUnitFeetList` refuse une empreinte a elevation heterogene.
    murs = {(7, 5)}
    elev = {(3, 5): 3}
    board = board_plat(elev_overrides=elev, unplayable=murs)
    centre = (5, 5)
    movement = 3
    st = monte(board, centre, movement)

    print("\n[MONTAGE] board %dx%d ; caster 7 pieds au centre %s ; Movement=%d"
          % (COLS, ROWS, centre, movement))
    print("[MONTAGE] murs = %s ; marches d'elevation = %s" % (sorted(murs), sorted(elev.items())))
    print("[MONTAGE] GetFeetCount(caster) = %d" % get_feet_count(st, 7))
    if get_feet_count(st, 7) != 7:
        print("ECHEC : le montage ne pose pas 7 pieds -- le probe ne mesure pas ce qu'il croit")
        return 1

    avant = sorted(_flood_brut(st, board, centre, movement))
    apres = sorted((t["col"], t["row"]) for t in
                   SB._move_tiles(st, 7, "deathBossMortarion", 0, centre,
                                  override_range=movement))
    pool = list(avant)
    for f in MQ.get_unit_feet(st, 7):
        if f not in pool:
            pool.append(f)

    print("\n[MESURE] sweep AVANT (flood-fill de main tiles, non filtre) : %d position(s)"
          % len(avant))
    print("[MESURE] sweep APRES (etage empreinte applique)             : %d position(s)"
          % len(apres))
    ecartees = [t for t in avant if t not in apres and t != centre]
    ajoutees = [t for t in apres if t not in avant]
    print("[MESURE] ECARTEES : %d   AJOUTEES : %d" % (len(ecartees), len(ajoutees)))

    if ajoutees:
        print("ECHEC : l'etage est PERMISSIF (il ajoute %s) -- le natif ne peut que RESTREINDRE"
              % sorted(ajoutees)[:5])
        return 1

    print("\n[VENTILATION] cause d'ecart, position par position :")
    for t in ecartees:
        print("  %-8s -> %s" % (str(t), _cause(board, pool, t)))

    # TEMOIN NON DEGENERE : sans difference, l'accord ne prouverait RIEN.
    if not ecartees:
        print("\nECHEC : aucune position ecartee -- TEMOIN DEGENERE. Le montage n'exerce pas la "
              "branche ; un accord dans ce regime ne montre rien.")
        return 1

    # CONTRE-EPREUVE 1 : une unite a UN pied ne change strictement PAS de comportement.
    st1 = monte(board, centre, movement, feet=False)
    a1 = sorted(_flood_brut(st1, board, centre, movement))
    b1 = sorted((t["col"], t["row"]) for t in
                SB._move_tiles(st1, 7, "u1", 0, centre, override_range=movement))
    print("\n[CONTRE-EPREUVE 1] caster MONO-hex : avant=%d apres=%d  identiques=%s"
          % (len(a1), len(b1), a1 == b1))
    if a1 != b1:
        print("ECHEC : le cas nominal (1 pied) a bouge -- `GetMovablePositionsFromTiles` le traite "
              "par `ToUnitPositionList`, sans aucun filtre")
        return 1

    # CONTRE-EPREUVE 2 : CARACTERISATION GEOMETRIQUE INDEPENDANTE, sur un plateau SANS obstacle.
    #
    # ⚠ Le critere du natif est << interieur du POOL >>, PAS << interieur du BOARD >> : `ContainsAll`
    # interroge `movableTiles`, c.-a-d. le flood-fill lui-meme. Une position au BORD DE LA PORTEE a
    # donc des pieds a `movement + 1` du centre, hors du pool -- elle est ecartee, en plein plateau.
    # Ce n'est pas du sur-filtrage, c'est la regle : un caster 7-hex ne peut pas s'arreter la ou son
    # anneau depasserait ce qu'il peut atteindre.
    #
    # Sur un plateau plat, `movableTiles` EST le disque hexagonal de rayon `movement`, donc
    # `ring1(t) SUBSET disque(movement)` <=> `dist(centre, t) <= movement - 1`. La prediction est
    # donc EXACTE et derivee de la GEOMETRIE, sans relire l'implementation qu'elle juge.
    plat = board_plat()
    st2 = monte(plat, centre, movement)
    a2 = sorted(_flood_brut(st2, plat, centre, movement))
    b2 = sorted((t["col"], t["row"]) for t in
                SB._move_tiles(st2, 7, "deathBossMortarion", 0, centre, override_range=movement))
    attendu = sorted(t for t in a2 if hexgeo.distance(centre, t) <= movement - 1)
    print("[CONTRE-EPREUVE 2] plateau SANS obstacle : avant=%d (disque rayon %d prive du centre) ; "
          "apres=%d ; attendu geometrique (disque rayon %d prive du centre)=%d"
          % (len(a2), movement, len(b2), movement - 1, len(attendu)))
    if b2 != attendu:
        print("ECHEC : le sweep filtre n'est PAS le disque de rayon movement-1.")
        print("   en trop : %s" % sorted(set(b2) - set(attendu))[:8])
        print("   manquant: %s" % sorted(set(attendu) - set(b2))[:8])
        return 1

    # CONTRE-EPREUVE 3 : la MEME caracterisation doit DEPENDRE de la portee -- sinon un fix qui
    # rendrait une constante passerait la precedente. Deux portees, deux disques distincts.
    for mv in (2, 4):
        st3 = monte(plat, centre, mv)
        a3 = _flood_brut(st3, plat, centre, mv)
        b3 = sorted((t["col"], t["row"]) for t in
                    SB._move_tiles(st3, 7, "deathBossMortarion", 0, centre, override_range=mv))
        att3 = sorted(t for t in a3 if hexgeo.distance(centre, t) <= mv - 1)
        print("[CONTRE-EPREUVE 3] Movement=%d : apres=%d attendu=%d %s"
              % (mv, len(b3), len(att3), "OK" if b3 == att3 else "DIVERGE"))
        if b3 != att3:
            return 1

    print("\nOK -- l'etage empreinte est RESTRICTIF, ventile par cause, inerte a 1 pied, et sur un "
          "plateau plat il rend EXACTEMENT le disque de rayon Movement-1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
