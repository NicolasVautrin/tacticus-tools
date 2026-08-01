"""#381-r3 LIVE -- le VOISINAGE du BFS est un slot VIRTUEL : marche = liste STOCKEE, vol = GEOMETRIE.

LA QUESTION BINAIRE
-------------------
« Le BFS de mouvement doit-il enumerer la geometrie hex ou la liste d'adjacence portee par la
tuile ? » -- et la reponse native est : LES DEUX, selon le pathfinder.
`IdunBattle.Entities.Pathfinding.BasePathfinder$$GetValidNeighbours` appelle `AddNeighbours` par la
VTABLE (`vslot 0x238`, seules XREFS = des entrees de vtable), et les deux corps ne lisent pas la
meme source :

  * `BasePathfinder$$AddNeighbours` (`u003CAddNeighboursu003Ed__19$$MoveNext`) enumere la `List` du
    `ConnectivityComponent` de la tuile (`connectivity+0x10`) et resout chaque id sur l'etat ;
  * `FlyPathfinder$$AddNeighbours` (`u003CAddNeighboursu003Ed__7$$MoveNext`) OVERRIDE et interroge
    la requete de tuiles au rayon 1, puis ecarte le centre.

Le `Board` du port n'ayant qu'un `adjacency=`, un mode GLOBAL se trompait forcement d'un cote.

CE QUE CES TESTS EXIGENT
------------------------
`aiMovableTiles` appelle LITTERALEMENT `IdunBattle.Core.Services.MovementQuery$$GetMovableTilesFor`
: l'egalite attendue est EXACTE, unite par unite. Les tests sont AUTO-DISCRIMINANTS -- ils exigent
que la configuration SEPARE les deux vues (sinon ils ne prouveraient rien) et que chacune des deux
mutations, qui remet UNE des deux branches a son etat d'AVANT, fasse effectivement diverger le port.

`C1_74` est le board discriminant : ses deux vues divergent sur 74 aretes dirigees. 70 le sont par
la porte `|dElev| < 2` de `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles` (celle que
traverse le capteur `boardGraph`), INCONDITIONNELLE -- mais que `WalkPathfinder$$IsValidPathNode`
applique de toute facon, donc elles sont sans effet sur la marche. Les 4 autres sont a
`|dElev| = 1` et separent VRAIMENT les deux vues : le `ConnectivityComponent` ne relie pas les deux
`Bridge` a leur voisin de meme niveau ((1,5)-(2,4) et (4,4)-(5,5)).

ASCII only (cp1252).
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest

BOARD = "C1_74"
SEED = "3811"
PROBE_RANGE = 5
BUILD = ["--no-ai", "--rank", "17"]


@contextmanager
def _geometric_walk():
    """L'etat d'AVANT `#381-r3` cote MARCHE : le BFS relit la GEOMETRIE (ce que rendait
    `board.neighbours` sur un `Board` monte en `adjacency="evenq"` -- tous les probes)."""
    from engine.entities.pathfinding import walk_pathfinder as WP
    saved = WP.get_movable_positions

    def _mut(board, start_id, depth, occupants, moving_team, **kw):
        kw["neighbours"] = board.neighbours_geometric
        return saved(board, start_id, depth, occupants, moving_team, **kw)
    WP.get_movable_positions = _mut
    try:
        yield
    finally:
        WP.get_movable_positions = saved


@contextmanager
def _stored_fly():
    """L'etat d'AVANT `#381-r3` cote VOL : le BFS relit la liste STOCKEE (ce que rendait
    `board.neighbours` sur un `Board` monte en `adjacency="native_sym"` -- `playbook/scene.py`,
    le montage de PRODUCTION)."""
    from engine.entities.pathfinding import fly_pathfinder as FP
    from engine.entities.pathfinding.walk_pathfinder import get_movable_positions as _walk
    saved = FP.get_movable_positions

    def _mut(board, start_id, depth, occupants, moving_team):
        return _walk(board, start_id, depth, occupants, moving_team,
                     edge=FP.is_valid_path_node, neighbours=board.neighbours_native)
    FP.get_movable_positions = _mut
    try:
        yield
    finally:
        FP.get_movable_positions = saved


def _load(rpc, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    # `adjacency="evenq"` VOLONTAIREMENT : depuis `#381-r3` le mode ne doit plus rien changer au
    # pathfinding (chaque pathfinder passe SA source). Le monter dans l'ancien mode « fidele au
    # vol » est donc la contre-epreuve la plus severe pour la branche MARCHE.
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    tm = rpc("tileMeta", {"runnerId": rid}, 90)
    return load_state(dv, ob, snap, board=board, tiles=tm), board, dv


def _pools(rpc, rid):
    """`{unitId: (visualId, pathfinder, natif, port)}` -- le pool du noeud DSL `MovableTilesInRange`
    contre `aiMovableTiles`, sur TOUTES les unites listees (les deux camps)."""
    from engine.dsl.base import Const
    from engine.entities.pathfinding.fly_pathfinder import is_like_flying
    from engine.entities.selectors import Caster, CasterTile, MovableTilesInRange
    from engine.entities.traits.unit_trait import unit_trait_names
    from engine.runner.abilities.behaviours import entities_from_state

    state, board, _dv = _load(rpc, rid)
    nat = rpc("aiMovableTiles", {"runnerId": rid, "side": "all",
                                 "overrideRange": PROBE_RANGE}, 120) or {}
    listed = {int(u["unitId"]): {(int(t["col"]), int(t["row"]))
                                 for t in (u.get("tiles") or []) if t.get("col") is not None}
              for u in (nat.get("units") or [])}
    assert listed, "aiMovableTiles n'a liste aucune unite"

    def _measure():
        out = {}
        for uid, want in sorted(listed.items()):
            if not want:
                continue                    # garde FLAG (`#381`) non portee : pas un desaccord
            ents = entities_from_state(state, uid, uid)
            vis = (ents.caster or {}).get("visualId")
            sel = MovableTilesInRange(Caster(), CasterTile(), Const(PROBE_RANGE),
                                      ignore_flags=False, ignore_units_on_tiles=False)
            got = {board.coord(t) for t in sel.evaluate(ents)}
            kind = "fly" if is_like_flying(unit_trait_names(vis)) else "walk"
            out[uid] = (vis, kind, want, got)
        return out
    return board, _measure


def test_la_marche_enumere_la_liste_STOCKEE(rpc, build_runner):
    """`BasePathfinder$$AddNeighbours` = le `ConnectivityComponent`. Sous la geometrie, le port
    SUR-atteint : `tauAunShi` rend 36 tuiles contre 34 au natif -- (4,2) et (5,3), atteintes en
    franchissant l'arete (1,5)->(2,4) que la liste stockee ne porte pas."""
    rid = build_runner(SEED, extra=BUILD, board=BOARD)["rid"]
    _board, measure = _pools(rpc, rid)
    ref = measure()
    walk = {u: v for u, v in ref.items() if v[1] == "walk"}
    assert walk, "aucune unite WALK confrontable -- le test ne prouverait rien"
    bad = [(u, v[0], sorted(v[3] - v[2])[:6], sorted(v[2] - v[3])[:6])
           for u, v in walk.items() if v[2] != v[3]]
    print("\n[381-r3] %s/%s WALK : %d/%d == natif" % (BOARD, SEED, len(walk) - len(bad), len(walk)))
    assert not bad, "port != natif sur %d unite(s) WALK : %s" % (len(bad), bad[:4])

    with _geometric_walk():
        mut = measure()
    moved = [(u, len(mut[u][3]), len(ref[u][3])) for u in walk if mut[u][3] != ref[u][3]]
    print("[381-r3]   contre-epreuve geo-walk : %d unite(s) WALK changent de pool -- %s"
          % (len(moved), moved[:4]))
    assert moved, (
        "la MUTATION `geo-walk` ne change le pool d'AUCUNE unite WALK sur %s : la configuration "
        "ne separe pas les deux vues du graphe, le test ne prouve rien" % BOARD)
    assert any(mut[u][3] != mut[u][2] for u, _n, _r in moved), (
        "la mutation change le pool mais il reste EGAL au natif -- bras non discriminant")


def test_le_vol_interroge_la_GEOMETRIE(rpc, build_runner):
    """`FlyPathfinder$$AddNeighbours` OVERRIDE et interroge le rayon 1. Sous la liste stockee, le
    port SOUS-atteint : `bloodIntercessor` rend 45 tuiles contre 46 au natif -- (3,1) manque."""
    rid = build_runner(SEED, extra=BUILD, board=BOARD)["rid"]
    _board, measure = _pools(rpc, rid)
    ref = measure()
    fly = {u: v for u, v in ref.items() if v[1] == "fly"}
    assert fly, "aucune unite VOLANTE confrontable -- le test ne prouverait rien"
    bad = [(u, v[0], sorted(v[3] - v[2])[:6], sorted(v[2] - v[3])[:6])
           for u, v in fly.items() if v[2] != v[3]]
    print("\n[381-r3] %s/%s VOL : %d/%d == natif" % (BOARD, SEED, len(fly) - len(bad), len(fly)))
    assert not bad, "port != natif sur %d unite(s) VOLANTE(s) : %s" % (len(bad), bad[:4])

    with _stored_fly():
        mut = measure()
    moved = [(u, len(mut[u][3]), len(ref[u][3])) for u in fly if mut[u][3] != ref[u][3]]
    print("[381-r3]   contre-epreuve stored-fly : %d volante(s) changent de pool -- %s"
          % (len(moved), moved[:4]))
    assert moved, (
        "la MUTATION `stored-fly` ne change le pool d'AUCUNE volante sur %s : la configuration ne "
        "separe pas les deux vues du graphe, le test ne prouve rien" % BOARD)
    assert any(mut[u][3] != mut[u][2] for u, _n, _r in moved), (
        "la mutation change le pool mais il reste EGAL au natif -- bras non discriminant")


def test_les_deux_vues_du_graphe_divergent_sur_ce_board(rpc, build_runner):
    """GARDE DU SUBSTRAT. Les deux tests ci-dessus ne valent que parce que `C1_74` SEPARE les deux
    vues ; ce test le CHIFFRE, et distingue les deux causes de la divergence -- pour qu'un
    changement du capteur `boardGraph` se lise ici et pas en silence.

    Attendu : le champ `neighbours` est strictement INCLUS dans la geometrie (aucune arete stockee
    hors geometrie, donc aucun teleporteur sur ce board -- cf.
    `BasePathfinder$$AddTeleportationTiles`, non porte), et parmi les aretes geometriques absentes
    du champ, certaines sont a `|dElev| <= 1` : celles-la seules separent la MARCHE, les autres
    etant de toute facon refusees par `WalkPathfinder$$IsValidPathNode`."""
    rid = build_runner(SEED, extra=BUILD, board=BOARD)["rid"]
    _state, board, _dv = _load(rpc, rid)
    geo = {(a, x) for a in board.by_id for x in board.neighbours_geometric(a)}
    sto = {(a, x) for a in board.by_id for x in board.neighbours_native(a)}
    only_geo = geo - sto
    only_sto = sto - geo
    flat = [(a, x) for a, x in only_geo
            if abs(board.elevation(a) - board.elevation(x)) <= 1]
    print("\n[381-r3] %s : geo=%d aretes, stockee=%d ; geo-seules=%d (dont %d a |dElev|<=1), "
          "stockee-seules=%d" % (BOARD, len(geo), len(sto), len(only_geo), len(flat),
                                 len(only_sto)))
    print("[381-r3]   les aretes qui separent la MARCHE : %s"
          % sorted((board.coord(a), board.coord(x)) for a, x in flat))
    assert only_geo, "les deux vues COINCIDENT sur %s : il n'est plus discriminant" % BOARD
    assert flat, (
        "toutes les aretes geo-seules de %s sont a |dElev| >= 2 -- `IsValidPathNode` les refuse de "
        "toute facon, donc les deux vues sont indiscernables POUR LA MARCHE et les tests "
        "ci-dessus ne prouvent rien" % BOARD)
    assert not only_sto, (
        "%d arete(s) STOCKEE(s) hors geometrie sur %s : ce board porte des liaisons que le port "
        "ne modelise pas -- relire `BasePathfinder$$AddTeleportationTiles` avant de conclure"
        % (len(only_sto), BOARD))


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
