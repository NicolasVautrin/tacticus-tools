"""GARDE LIVE #448-r1-r1-r1-r1 -- `_num_tiles_moved` d'un VOLANT, confronte au compteur NATIF.

Le test offline garde la LOI sur des boards synthetiques. Il ne garde PAS que la chaine tienne
sur une vraie bataille : que le trait `Flying` remonte jusqu'a `UnitContext.traits`, que les
QUATRE effets de mouvement special soient vus (`GetPathfinderTypeForUnit` les teste AVANT
`IsLikeFlying`), et que le compteur natif soit celui qu'on croit.

CE QU'ON MESURE, et c'est un SCALAIRE DIRECT, pas un gate probabiliste : le delta de
`ActorStatisticsComponent+0xf0` (`tilesMovedThisTurn`, RPC `actorStats`) encadrant un
`applyAction move`. C'est exactement ce qu'ecrit
`IdunBattle.Entities.UnitExtensions$$RecordTilesMoved(unit, GetNumTilesMoved(connectedPath))`.

LE DISCRIMINANT est le vol DETOURNE, et seul un MUR detourne un vol
(`FlyPathfinder$$IsValidPathNode` ne teste que `TileComponent+0x40` = fog et `+0x41` = `IsWall`).
Sur un vol DIRECT, « distance » et « pas de vol » COINCIDENT -- un accord obtenu la ne
prouverait rien. `C6_25` est le seul board mesure a offrir des trajets detournes a `d = 2`
(17 boards a murs balayes ; `C6_09` en a 16 et n'en produit AUCUN -- sa barriere deconnecte le
plateau). Voir `docs/rl/case-448-r1-r1-r1-flying-movement-steps.md`.

MESURE (natif, seed 777, `probe_448_r1_r1_r1_r1_flying_tiles_moved.py`) :

    bras                                          accord / mesures    livre   mutants
    FD   VOLANT d=2 direct        (MC1_67)             12 / 12          0 des.  beeline-native: 1
    FD3  VOLANT d=3 direct        (MC1_67)             12 / 12          0 des.  walk: (voir doc)
    W    MARCHEUR d=2             (MC1_67)             10 / 10          0 des.  --
    FX   VOLANT d=2 DETOURNE      (C6_25)              10 / 10          0 des.  walk: 1, teleport: 1

Sur `FX`, le natif rend **2, 3 OU 4** pour des couples tous a `d = 2` : 2 quand le porteur est en
`TeleportStrike` (`ATeleportPathfinder$$FindPath` = `[from, to]`), 3 ou 4 selon la longueur du
detour sinon. Aucune lecture constante ne peut produire ces trois valeurs. ASCII only.
"""
from __future__ import annotations

import pytest

import hexgeo
import probe_448_r1_r1_r1_flying_movement_steps as P
import probe_448_r1_r1_r1_r1_flying_tiles_moved as P4
from engine.entities.pathfinding import pathfinders as PF
from engine.entities.pathfinding.board import Board
from engine.entities.pathfinding.fly_pathfinder import is_like_flying
from engine.runner.components import PositionComponent, StatsComponent
from engine.runner.operations.movement import _num_tiles_moved
from engine.services.movement_query import get_pathfinder_type_for_unit, unit_has_effect_fn

SEED = 777
FOES = ["tauCrisis"]
FLY = P.FLY_GRAFTS
# `C6_25` : le SEUL board mesure a offrir des trajets de vol DETOURNES a d=2 (cf. l'en-tete).
# Il n'a que 3 spawns joueur -> equipe reduite, comme le probe le fait.
DETOUR_BOARD, DETOUR_UNITS = "C6_25", FLY[:3]


def _live(rpc, build_runner, board, units):
    built = build_runner(seed=str(SEED), board=board,
                         extra=["--rank", "17", "--no-ai",
                                "--p-units", ",".join(units),
                                "--a-units", ",".join(FOES)])
    rid = int(built["rid"])

    def _rpc(sid, method, args, timeout=120):
        return rpc(method, args, timeout)
    bg = rpc("boardGraph", {"runnerId": rid}, 90)
    brd = Board(bg["tiles"], adjacency="native_sym")
    state, dv, _ob = P._port_state(None, _rpc, rid, brd)
    return {"rid": rid, "sid": None, "rpc": _rpc, "board": brd, "state": state, "dv": dv,
            "units": list(units), "bg": bg}


@pytest.fixture(scope="module")
def flat(rpc, build_runner):
    """Board SANS mur : les vols y sont directs. Montage KO => ECHEC, jamais skip (#455)."""
    return _live(rpc, build_runner, "MC1_67", FLY)


@pytest.fixture(scope="module")
def detour(rpc, build_runner):
    """Board a MURS : le seul regime ou « distance » et « pas de vol » divergent."""
    return _live(rpc, build_runner, DETOUR_BOARD, DETOUR_UNITS)


def _carriers(live):
    return sorted(P._carriers(live["dv"], live["units"]))


def _fresh_turn(live):
    """Termine le tour courant et RE-CAPTURE l'etat live.

    La fixture est `scope="module"` : son `state` est celui du SETUP, donc PERIME des qu'un test
    a bouge une unite -- et les unites deja jouees n'ont plus de destination legale, ce qui rend
    un `0 mesure` qui ressemble a un montage casse. Chaque test qui joue des mouvements repart
    donc d'un tour NEUF.

    ⚠ On BOUCLE, et le critere est « un porteur peut ENCORE BOUGER », pas « un porteur est dans
    `toActivate` ». Deux pieges distincts, tous deux vus au premier jet : un `endturn` donne la
    main a l'equipe ADVERSE (un tour sur deux n'a aucun porteur), et une unite qui a deja bouge
    reste dans `toActivate` (elle peut encore attaquer) alors que ses `aiMovableTiles` sont
    vides. Les deux rendaient « aucune mesure » -- un faux negatif de MONTAGE, pas un desaccord."""
    for _ in range(6):
        st, dv, _ob = P._port_state(live["sid"], live["rpc"], live["rid"], live["board"])
        live["state"], live["dv"] = st, dv
        to_act = {int(u) for u in (dv.get("toActivate") or [])}
        for uid in sorted(to_act & set(P._carriers(dv, live["units"]))):
            if P._legal_moves(live["sid"], live["rpc"], live["rid"], uid):
                return st
        live["rpc"](live["sid"], "applyAction",
                    {"runnerId": live["rid"], "action": {"kind": "endturn"}}, 120)
    raise AssertionError("aucun porteur mobile en 6 endturn -- montage a revoir")


# ─────────────────────────────────────────────────────────────────────────────────────────────
# MONTAGE -- ce qui casserait en SILENCE et rendrait tout le fichier vert pour rien
# ─────────────────────────────────────────────────────────────────────────────────────────────
def test_les_porteurs_sont_volants(flat):
    """Si `Flying` n'arrivait pas jusqu'a `UnitContext.traits`, tout le fichier exercerait la
    branche MARCHEUSE en croyant mesurer la volante -- et passerait au vert."""
    st = flat["state"]
    carriers = _carriers(flat)
    assert carriers, "aucun porteur dans decisionView -- montage KO"
    for uid in carriers:
        sc = st.get_entity(uid).get_component(StatsComponent)
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        assert is_like_flying(traits or []), "u%s n'est pas IsLikeFlying (traits=%s)" % (uid,
                                                                                         traits)


def test_le_capteur_publie_le_compteur(flat):
    """`actorStats.tilesMovedThisTurn` DOIT etre present et non nul-typed : sur un bundle qui ne
    le publie pas, la cle est absente -> `None`, et toutes les mesures deviendraient des
    « NON MESURE » silencieux. Tri-etat, jamais un 0 par defaut."""
    ast = P4._actor_stats(flat["sid"], flat["rpc"], flat["rid"])
    vals = {int(u["entityId"]): u.get("tilesMovedThisTurn")
            for u in ((ast or {}).get("units") or []) if u.get("entityId") is not None}
    assert vals, "actorStats ne publie AUCUNE unite"
    assert any(v is not None for v in vals.values()), (
        "actorStats publie des unites mais AUCUN `tilesMovedThisTurn` -- capteur non deploye")
    for uid in _carriers(flat):
        assert uid in vals, ("u%s absent d'actorStats : la numerotation d'actorStats n'est plus "
                             "celle de decisionView.units[].id" % uid)


def test_le_dispatch_lit_les_effets_de_mouvement_special(flat):
    """`MovementQuery$$GetPathfinderTypeForUnit` teste QUATRE effets AVANT `IsLikeFlying`. Sur ce
    montage, une partie des volants du pool porte `TeleportStrike` et sort donc en type DECORE --
    ce qui change le pathfinder, pas seulement une option. Si le port ne lisait que
    `IsLikeFlying`, il rendrait 3 pour tout le monde et le test ci-dessous ne mesurerait rien."""
    st = flat["state"]
    types = {}
    for uid in _carriers(flat):
        sc = st.get_entity(uid).get_component(StatsComponent)
        tr = getattr(sc.ctx, "traits", None) if sc is not None else None
        types[uid] = get_pathfinder_type_for_unit(unit_has_effect_fn(st, uid), tr or [])
    assert types, "aucun porteur"
    assert all(t != int(PF.PathfinderType.Walk) for t in types.values()), (
        "un volant est resolu en `Walk` : le dispatch ne voit pas `Flying` (%s)" % types)
    assert any(PF.is_teleport_type(t) for t in types.values()), (
        "aucun porteur en type DECORE (%s) -- le bras teleport de ce fichier ne mesure rien, "
        "le montage a change" % types)


# ─────────────────────────────────────────────────────────────────────────────────────────────
# ACCORD NATIF <-> PORT
# ─────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("d", [2, 3])
def test_accord_sur_un_vol_direct(flat, d):
    """Un mouvement REEL par porteur, a distance `d`. Le natif enregistre ce que le port calcule.

    ⚠ La garde `reset` n'est pas facultative : le move de la DERNIERE unite activable fait
    basculer le tour, et `ActorStatisticsComponent$$ResetThisTurn` remet `+0xf0` a zero -- la
    mesure devient un `0` qui MENT. On la rend NON MESUREE, pas verte."""
    st = _fresh_turn(flat)
    rpc_, rid, brd = flat["rpc"], flat["rid"], flat["board"]
    mesures = 0
    for uid in _carriers(flat):
        legal = P._legal_moves(flat["sid"], rpc_, rid, uid)
        st, _, _ = P._port_state(flat["sid"], rpc_, rid, brd)
        got = P._pick(st, brd, uid, legal, "fly", d)
        if got is None:
            continue
        dest, info = got
        nat, port, reset = P4.measure_move(flat["sid"], rpc_, rid, uid, st, info["src"], dest)
        if reset or nat is None:
            continue
        assert nat == port, ("u%s %s->%s (d=%d) : NATIF=%s PORT=%s"
                             % (uid, info["src"], dest, d, nat, port))
        assert nat == d, ("u%s %s->%s : un vol DIRECT doit compter la distance (%d), pas %s"
                          % (uid, info["src"], dest, d, nat))
        mesures += 1
    assert mesures > 0, ("aucune mesure a d=%d -- montage a revoir, surtout PAS un skip vert" % d)


def test_accord_sur_un_vol_detourne(detour):
    """LE DISCRIMINANT. Sur `C6_25`, des couples a `d = 2` dont le chemin de VOL fait 3 ou 4 pas.
    Trois lectures y divergent -- distance (2), pas de vol (3 ou 4), pas de marche -- et le natif
    prend l'une OU l'autre selon le pathfinder de l'unite. Le port doit suivre cette bascule.

    On assertionne AUSSI que la mesure n'est pas degeneree : il faut au moins DEUX valeurs
    natives distinctes, sinon un port constant passerait."""
    st, rpc_, rid, brd = detour["state"], detour["rpc"], detour["rid"], detour["board"]
    pairs = P._detour_pairs(brd, 2)
    assert pairs, "aucun trajet DETOURNE sur %s -- le board a change" % DETOUR_BOARD
    vus, mesures = set(), 0
    for _turn in range(8):
        st, dv, _ob = P._port_state(detour["sid"], rpc_, rid, brd)
        to_act = [int(u) for u in (dv.get("toActivate") or [])]
        if not to_act:
            break
        carriers = P._carriers(dv, detour["units"])
        for uid in to_act:
            if uid not in carriers:
                continue
            legal = P._legal_moves(detour["sid"], rpc_, rid, uid)
            st, _, _ = P._port_state(detour["sid"], rpc_, rid, brd)
            got = P._pick(st, brd, uid, legal, "flyd", 2)
            if got is None:
                e = st.get_entity(int(uid))
                pc = e.get_component(PositionComponent) if e is not None else None
                step = (P._approach(brd, (pc.col, pc.row), legal, sorted(pairs))
                        if pc is not None else None)
                if step is not None:
                    rpc_(detour["sid"], "applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": int(uid),
                        "to": {"col": int(step[0]), "row": int(step[1])}}}, 120)
                continue
            dest, info = got
            nat, port, reset = P4.measure_move(detour["sid"], rpc_, rid, uid, st, info["src"],
                                               dest)
            if reset or nat is None:
                continue
            assert nat == port, (
                "u%s %s->%s : d=2, chemin de vol %s pas -- NATIF=%s PORT=%s"
                % (uid, info["src"], dest, info.get("fly_steps"), nat, port))
            vus.add(nat)
            mesures += 1
        rpc_(detour["sid"], "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
    assert mesures > 0, "aucun vol detourne mesure -- montage a revoir, surtout PAS un skip vert"
    assert len(vus) >= 2, (
        "toutes les mesures rendent la MEME valeur %s : le bras est DEGENERE, un port constant "
        "y passerait" % vus)


# ─────────────────────────────────────────────────────────────────────────────────────────────
# CONTRE-EPREUVES -- sur l'etat LIVE, sans re-jouer : le fix DOIT changer le resultat
# ─────────────────────────────────────────────────────────────────────────────────────────────
def test_le_walkpathfinder_diverge_sur_letat_live(flat):
    """Le port d'AVANT #448-r1-r1-r1-r1 (WalkPathfinder INCONDITIONNEL) doit rendre AUTRE CHOSE
    sur au moins un trajet reel. Sans cette contre-epreuve, tous les accords ci-dessus seraient
    compatibles avec « le fix ne sert a rien ».

    On ne rejoue rien : on evalue les deux lectures sur le MEME etat, en neutralisant le seul
    dispatch (`get_pathfinder_type_for_unit -> Walk`)."""
    import engine.services.movement_query as MQ
    st, brd = flat["state"], flat["board"]
    orig = MQ.get_pathfinder_type_for_unit
    diffs = []
    try:
        for uid in _carriers(flat):
            pc = st.get_entity(uid).get_component(PositionComponent)
            if pc is None:
                continue
            src = (pc.col, pc.row)
            for c, r in sorted(brd.by_coord):
                if hexgeo.distance(src, (c, r)) != 2 or not brd.walkable(brd.id_at(c, r)):
                    continue
                MQ.get_pathfinder_type_for_unit = orig
                fixed = _num_tiles_moved(st, uid, src, (c, r))
                MQ.get_pathfinder_type_for_unit = lambda *a, **k: 0
                avant = _num_tiles_moved(st, uid, src, (c, r))
                if fixed != avant:
                    diffs.append((uid, src, (c, r), fixed, avant))
    finally:
        MQ.get_pathfinder_type_for_unit = orig
    assert diffs, ("le port livre et le port d'AVANT rendent la MEME chose sur TOUS les trajets "
                   "a d=2 de ce board : ce fichier ne mesure rien")


def test_la_beeline_sur_le_champ_capte_diverge(flat):
    """Le SUBSTRAT de la beeline est un choix MESURE, pas une commodite. Le champ `neighbours`
    du `boardGraph` n'est pas le `ConnectivityComponent` : le capteur passe par
    `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles`, dont la porte `|delta elev| < 2`
    est INCONDITIONNELLE. Sur `MC1_67` il ampute **18 aretes dirigees**, toutes des marches
    `2 <-> 4` -- et avec elles le port rendait 3 la ou le natif enregistre 2.

    Ce test garde les DEUX faces : que le trou existe encore (sinon le choix de substrat serait
    devenu sans objet et devrait etre re-arbitre), et qu'il change bien un compte."""
    from engine.entities.pathfinding import base_pathfinder as BP
    from engine.entities.pathfinding import beeline_pathfinder as BL
    brd = flat["board"]
    manquantes = [(t["id"], g) for t in flat["bg"]["tiles"]
                  for g in brd.neighbours_geometric(t["id"])
                  if g not in set(brd.neighbours_native(t["id"]))]
    assert manquantes, ("le champ `neighbours` ne perd plus aucune arete geometrique sur ce "
                        "board : le choix de substrat de `beeline_pathfinder` est a re-arbitrer")
    diff = 0
    for a, b in ((brd.coord(x), brd.coord(y)) for x, y in manquantes[:40]):
        sa, sb = brd.id_at(*a), brd.id_at(*b)
        geo = BL.find_path(brd, sa, sb)
        nat = BP.find_path(brd, sa, sb, edge=BL.is_valid_path_node,
                           neighbours=brd.neighbours_native,
                           weight_cost=lambda tid: BL.weight_cost(False),
                           is_valid_final_tile=lambda tid: True)
        if geo is not None and nat is not None and len(geo) != len(nat):
            diff += 1
    assert diff > 0, ("le champ capte et la geometrie rendent des beelines de MEME longueur "
                      "partout : la contre-epreuve ne mesure rien")
