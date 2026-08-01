"""#403 (`#381-r2`) LIVE -- le FlyPathfinder n'a PAS le gate d'expansion de la MARCHE.

LA QUESTION BINAIRE
-------------------
« Une tuile block-entering (Swamp) est-elle un CUL-DE-SAC pour une unite VOLANTE ? »
Le natif repond NON. `IdunBattle.Entities.Pathfinding.BasePathfinder$$NodesInNextLevel` interroge
bien un slot virtuel (`vslot 10`) avant d'etendre la fill, mais le predicat #131 est produit par le
SEUL `IdunBattle.Entities.Pathfinding.WalkPathfinder$$GetTileBlockingReasons`, dont les XREFS sont
EXHAUSTIVES et toutes internes a la branche MARCHE (`WalkPathfinder$$IsValidContinuePathTile`,
`$$GetEffectiveDepth`, `$$WeightCost`, `IgnoreDoorPathfinder$$IsValidContinuePathTile`,
`WaveValidatorPathfinder$$IsValidContinuePathTile`). Or `FlyPathfinder` derive de `BasePathfinder`,
PAS de `WalkPathfinder`, et `IgnoreDoor`/`WaveValidator` sont les deux seules sous-classes de
`WalkPathfinder`.

CE QUE CES TESTS EXIGENT
------------------------
`aiMovableTiles` appelle LITTERALEMENT `MovementQuery$$GetMovableTilesFor` : egalite EXACTE, unite
par unite, sur les VOLANTES -- celles que `test_381r5_special_movement_live` ecartait justement au
titre de `#381-r2`. Le regime vise est la volante SANS mouvement special, donc apres expiration de
`TeleportStrike_TeleportingIn` (T+6 `endturn`).

AUTO-DISCRIMINANTS : chaque test exige qu'au moins une volante voie son pool CHANGER quand on
remet le gate marche sur la branche vol (la mutation `_walk_gate_on_fly` = l'arbre d'AVANT `#403`).
Sans ce changement, la geometrie ne prouve rien et le test ECHOUE -- jamais un vert vide.

MESURE D'OUVERTURE (`probe_403_c2_26_fly_gap.py`) : `C2_26`/38104, `overrideRange` 2, T+6 --
`bloodIntercessor` (Flying) natif **13**, port **12** ; la tuile manquante etait `(0,2)`, qui ne
pend que du Swamp `(1,2)`. Apres le fix : 13/13.

ASCII only (cp1252).
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest

SEED = "38104"
BUILD_POOL = ["--no-ai"]        # roster COMPLET du seed : autant de volantes confrontees
TURNS = 6                       # `TeleportStrike_TeleportingIn` expire -> regime FLY pur
RANGES = (2, 3, 4, 5)           # la portee est un levier de configuration : un goulot n'est
                                # discriminant que si le pool le DEPASSE


@contextmanager
def _walkable_edge_on_fly():
    """L'arbre d'AVANT `#403-r1` : l'arete FLY montee sur `board.walkable` au lieu de `!IsWall`.

    `FlyPathfinder$$IsValidPathNode` lit `TileComponent[+0x40] == 0 && [+0x41] == 0` ;
    `TileExtensions$$IsWalkable` lit `MovementComponent[+0x10] == 0 && TileComponent[+0x40] == 0`.
    Les deux different sur les tuiles `Block`/`Water` (`walkable=False`, `isWall=False`), que le
    vol TRAVERSE."""
    import engine.entities.pathfinding.fly_pathfinder as FP
    saved = FP.is_valid_path_node

    def _edge(board, from_id, to_id, occupants, moving_team):
        t = board.by_id.get(to_id)
        return t is not None and bool(t["walkable"])
    FP.is_valid_path_node = _edge
    try:
        yield
    finally:
        FP.is_valid_path_node = saved


@contextmanager
def _walk_gate_on_fly(can_continue):
    """L'arbre d'AVANT `#403` : la branche FLY recoit le gate d'expansion de la MARCHE.

    La mutation porte sur `fly_pathfinder.get_movable_positions`, que
    `pathfinders.find_reachable_tiles` re-importe a CHAQUE appel -- elle traverse donc le foyer
    complet (`GetPathfinderTypeForUnit` -> `GetReachableTiles`), ce n'est pas un calcul parallele."""
    import engine.entities.pathfinding.fly_pathfinder as FP
    from engine.entities.pathfinding.walk_pathfinder import get_movable_positions as _walk
    saved = FP.get_movable_positions

    def _muted(board, start_id, depth, occupants, moving_team):
        return _walk(board, start_id, depth, occupants, moving_team,
                     edge=FP.is_valid_path_node, can_continue=can_continue)
    FP.get_movable_positions = _muted
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
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    return load_state(dv, ob, snap, board=board), board, dv


def _confront(rpc, rid, board_name):
    """Balaie les portees de `RANGES` et confronte `get_movable_tiles_for` a `aiMovableTiles` pour
    chaque VOLANTE sans mouvement special. Rend les comptes + les divergences."""
    from engine.ai.state_bridge import _occupants
    from engine.entities.pathfinding.fly_pathfinder import is_like_flying
    from engine.entities.pathfinding.tile_blocking import make_can_continue
    from engine.entities.traits.unit_trait import unit_trait_names
    from engine.runner.components import OwnerComponent, PositionComponent, StatsComponent
    from engine.services.movement_query import get_movable_tiles_for, has_special_movement

    state, board, dv = _load(rpc, rid)
    occ = _occupants(state)
    out = {"board": board_name, "fly": 0, "fly_equal": 0, "discriminating": 0,
           "discriminating_edge": 0, "blocked_tiles": 0, "obstacle_tiles": 0,
           "rows": [], "bad": []}
    from engine.entities.pathfinding.tile_blocking import terrain_blocks_entering
    out["blocked_tiles"] = sum(1 for t in board.by_id if terrain_blocks_entering(board, t, []))
    # Tuiles `Block`/`Water` : NON walkable mais PAS des murs -> le vol les traverse (`#403-r1`).
    out["obstacle_tiles"] = sum(1 for t in board.by_id
                                if not board.walkable(t) and not board.is_wall(t))

    for rng in RANGES:
        nat = rpc("aiMovableTiles", {"runnerId": rid, "side": "all",
                                     "overrideRange": rng}, 120) or {}
        listed = {int(u.get("unitId")): {(int(t["col"]), int(t["row"]))
                                         for t in (u.get("tiles") or [])
                                         if t.get("col") is not None}
                  for u in (nat.get("units") or [])}
        assert listed, "aiMovableTiles n'a liste aucune unite sur %s (portee %d)" % (board_name,
                                                                                     rng)
        for uid, want in sorted(listed.items()):
            e = state.get_entity(uid)
            pc = e.get_component(PositionComponent) if e is not None else None
            oc = e.get_component(OwnerComponent) if e is not None else None
            sc = e.get_component(StatsComponent) if e is not None else None
            if pc is None or oc is None:
                continue
            vis = next((u.get("visualId") for u in (dv.get("units") or [])
                        if int(u.get("id")) == uid), None)
            if not is_like_flying(unit_trait_names(vis)):
                continue
            if has_special_movement(state, uid):
                continue                        # `#381-r5`, garde propre
            if not want:
                continue                        # garde FLAG non portee (`#381`)
            start = board.id_at(pc.col, pc.row)
            if start is None:
                continue
            traits = (sc.ctx.traits if (sc is not None and getattr(sc, "ctx", None) is not None)
                      else None) or []
            got = {board.coord(t) for t in get_movable_tiles_for(
                board, state, uid, start, rng, occ, oc.team)}
            cc = make_can_continue(getattr(state, "effects", None), traits, board=board)
            with _walk_gate_on_fly(cc):
                mute = {board.coord(t) for t in get_movable_tiles_for(
                    board, state, uid, start, rng, occ, oc.team)}
            with _walkable_edge_on_fly():
                mute_e = {board.coord(t) for t in get_movable_tiles_for(
                    board, state, uid, start, rng, occ, oc.team)}
            out["fly"] += 1
            out["fly_equal"] += int(got == want)
            out["discriminating"] += int(mute != got)
            out["discriminating_edge"] += int(mute_e != got)
            out["rows"].append((rng, uid, vis, len(want), len(got), len(mute), len(mute_e)))
            if got != want:
                out["bad"].append((rng, uid, vis, sorted(got - want)[:6], sorted(want - got)[:6]))
    return out


def _run(rpc, build_runner, board_name, expect_discriminating: bool = True,
         require_edge: bool = True):
    rid = build_runner(SEED, extra=BUILD_POOL, board=board_name)["rid"]
    for _ in range(TURNS):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
    r = _confront(rpc, rid, board_name)
    print("\n[403] %s/%s T+%d : VOLANTES %d/%d == natif sur %d portees ; DISCRIMINANT gate=%d "
          "arete=%d ; terrain : %d block-entering, %d obstacles non-mur"
          % (board_name, SEED, TURNS, r["fly_equal"], r["fly"], len(RANGES),
             r["discriminating"], r["discriminating_edge"], r["blocked_tiles"],
             r["obstacle_tiles"]))
    for (rng, uid, vis, n_nat, n_got, n_mute, n_mute_e) in r["rows"]:
        print("[403]   portee=%d u%-5s %-22s natif=%-3d port=%-3d gate-MARCHE=%-3d "
              "arete-walkable=%-3d%s"
              % (rng, uid, vis, n_nat, n_got, n_mute, n_mute_e,
                 "  <-- DISCRIMINANT" if (n_mute != n_got or n_mute_e != n_got) else ""))
    assert r["fly"], ("aucune volante SANS mouvement special n'est mobile sur %s -- le test ne "
                      "prouverait rien (le regime special expire au bout de ~5 tours)" % board_name)
    if expect_discriminating:
        assert r["discriminating"], (
            "le gate MARCHE ne change le pool d'AUCUNE des %d mesures volantes de %s -- la "
            "configuration ne discrimine pas `#403`" % (r["fly"], board_name))
        if require_edge:
            assert r["discriminating_edge"], (
                "l'arete `board.walkable` ne change le pool d'AUCUNE des %d mesures volantes de "
                "%s -- la configuration ne discrimine pas `#403-r1`" % (r["fly"], board_name))
    else:
        assert not r["discriminating"] and not r["discriminating_edge"], (
            "%s devait etre un CONTROLE NEGATIF (ni tuile block-entering ni obstacle non-mur) mais "
            "les mutations y changent %d/%d pool(s) -- le controle ne controle rien"
            % (board_name, r["discriminating"], r["discriminating_edge"]))
    # COHERENCE, toujours active : la mutation d'arete ne peut discriminer que s'il existe une
    # tuile NON walkable et NON mur (`Block`/`Water`). Zero obstacle et pourtant une divergence
    # signifierait que la mutation touche autre chose que ce qu'elle pretend.
    assert not (r["discriminating_edge"] and not r["obstacle_tiles"]), (
        "%s : la mutation d'arete discrimine (%d) alors que le board n'a AUCUN obstacle non-mur "
        "-- elle ne mesure pas ce qu'elle dit" % (board_name, r["discriminating_edge"]))
    assert not r["bad"], ("port != natif sur %d mesure(s) de %s : %s"
                          % (len(r["bad"]), board_name, r["bad"][:4]))
    return r


def test_fly_ignore_le_gate_dexpansion_c2_26(rpc, build_runner):
    """`C2_26` -- le board des DEUX datapoints, et le seul a discriminer les deux maillons :
    `bloodIntercessor` natif 13 / port 12 (gate, `#403`) et `tyranNeurothrope` natif 22 / port 21
    (arete, `#403-r1`). Terrain : 6 Swamp block-entering, 12 obstacles non-mur (6 `Block`,
    6 `Water`)."""
    _run(rpc, build_runner, "C2_26")


def test_fly_ignore_le_gate_dexpansion_mc1_67(rpc, build_runner):
    """`MC1_67` -- SECOND board (arene par defaut, 4 Swamp), pour que le resultat ne soit pas un
    artefact de la geometrie de `C2_26` (`#95`). Il discrimine le GATE (3 mesures sur 8), pas
    l'ARETE : il ne porte qu'UN obstacle non-mur, hors de tout goulot -- d'ou `require_edge=False`,
    qui n'affaiblit pas la garde (`C2_26` la porte) et evite un rouge de geometrie."""
    _run(rpc, build_runner, "MC1_67", require_edge=False)


def test_controle_negatif_sans_tuile_bloquante(rpc, build_runner):
    """`PVP_desert_04` -- CONTROLE NEGATIF : ce board n'a AUCUNE tuile block-entering (recense
    live par `probe_pathfinding_overreach --audit` : `Unplayable/Grass/Block/DryBush`, zero Swamp).
    AUCUNE des deux mutations ne doit donc rien changer, et le port doit rester exact -- c'est ce
    qui prouve que le fix retire un gate INDU et n'ouvre pas une vanne."""
    _run(rpc, build_runner, "PVP_desert_04", expect_discriminating=False)


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
