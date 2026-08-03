"""#433-r4-r1-r4 -- la PORTE D'ELEVATION du substrat DSL, branchee sur le canal du board.

Ce que cette garde verrouille
-----------------------------
Le natif applique `|dElev| < 2` dans les DEUX foyers d'adjacence, et il n'a AUCUN etat
« elevation inconnue » (il deref le composant `tile->[0x20]` et LEVE s'il manque) :

  * `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, verbatim --
    l'elevation de la tuile SOURCE est lue une fois a l'init (`d__8+0x48`), celle du voisin par
    iteration, puis, APRES les filtres terrain (temporary `+0x40`, walkable `+0x42`,
    emptyOrSteppable `+0x44`) : `d = |src - voisin| ; if (d < 2) yield` ;
  * `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(tile1, tile2)` --
    `return (|dElev| < 2) & (tile1 == tile2 || ConnectivityComponent.IsNeighbour(tile1, tile2))` ;
  * et le meme entier alimente `IdunBattle.Entities.TileExtensions$$GetElevationDifference`, que
    lit `IdunBattle.Entities.Selectors.TilesOnSameElevationSelector$$Select`
    (`if (GetElevationDifference(tile, otherTile) <= this+0x28) keep`).

Cote port le canal EXISTAIT (`DslContext.elev_by_pos`) mais n'etait branche par AUCUN des
constructeurs du substrat runner -- degradation PERMISSIVE, silencieuse, partagee par tous les
noeuds concernes. Ces tests verrouillent les trois etages :

  1. le CANAL (`elevations_by_pos`, `DslContext.__post_init__`) et son TRI-ETAT ;
  2. les DEUX BRAS de `FilterTilesIfCanAttackTargetTileFromSelector$$Select`, dont la porte fait
     basculer le verdict dans les DEUX SENS (elle GARDE une tuile au premier bras, elle en REFUSE
     une au second) -- un fix qui ne serait que restrictif serait FAUX ;
  3. `UnitsDirectlyBehind` (`TilesOnSameElevationSelector`, maxDiff = 1), le second lecteur du
     canal, cable au splash de `PlasmaCannonAbility` cote COMBAT.

Plus le CABLAGE runner (`entities_from_state`) et la NON-REGRESSION sur un board sans elevation
captee. 100 % OFFLINE : aucun runner, aucune session.
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import hexgeo                                                                    # noqa: E402
from engine import battle_query as bq                                            # noqa: E402
from engine.dsl.base import DslContext                                           # noqa: E402
from engine.entities.pathfinding.board import Board, elevations_by_pos           # noqa: E402
from engine.entities.selectors import (Caster, FilterTilesIfCanAttackTargetTileFrom,  # noqa: E402
                                       FixedTileIds, Target, UnitsDirectlyBehind)

COLS, ROWS = 7, 7


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _board(elev=None, with_elevation: bool = True) -> Board:
    """Board 7x7 plein, voisinage even-q. `elev` = surcharges `{(col,row): elevation}` ; le reste
    a 0. `with_elevation=False` retire le CHAMP (board anterieur au capteur) -- c'est l'etat
    « canal absent », different d'une elevation nulle."""
    elev = elev or {}
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            t = {"id": _tid(col, row), "col": col, "row": row,
                 "walkable": True, "isWall": False, "neighbours": nb}
            if with_elevation:
                t["elevation"] = int(elev.get((col, row), 0))
            tiles.append(t)
    return Board(tiles, adjacency="evenq")


def _unit(uid, team, pos, alive=True, hp=100):
    return {"id": uid, "team": team, "alive": alive, "hp": hp,
            "pos": {"col": pos[0], "row": pos[1]}}


# ============================================================== 1. LE CANAL (`elevations_by_pos`)

def test_le_canal_rend_la_carte_du_board():
    b = _board({(1, 1): 3, (2, 2): -1})
    m = elevations_by_pos(b)
    assert m is not None
    assert len(m) == COLS * ROWS
    assert m[(1, 1)] == 3 and m[(2, 2)] == -1 and m[(0, 0)] == 0


def test_une_tuile_sans_elevation_est_OMISE_jamais_cotee_a_zero():
    """La difference decisive avec `walk_maps_by_pos` (qui rend `int(elevation or 0)`).

    Coter `0` une elevation NON MESUREE fabrique une donnee, et la porte deviendrait RESTRICTIVE :
    un voisin a 2 serait refuse contre une tuile « 0 » inventee. Un faux NEGATIF d'adjacence
    SUPPRIME des actions legales -- pire que la degradation permissive qu'on ferme."""
    b = _board({(1, 1): 3})
    b.by_id[_tid(0, 0)].pop("elevation")
    m = elevations_by_pos(b)
    assert (0, 0) not in m                                  # OMISE
    assert m[(1, 1)] == 3
    # et le repli de `is_adjacent` retient la paire dont une elevation est inconnue
    assert bq.is_adjacent((0, 0), (1, 0), m) is True
    # meme paire, elevation CONNUE et ecartee de 3 -> refusee
    assert bq.is_adjacent((1, 1), (1, 0), {(1, 1): 3, (1, 0): 0}) is False


def test_le_canal_est_TRI_ETAT_et_ne_rend_jamais_une_carte_vide():
    """`None` = rien mesure ; jamais `{}`, qui se lirait comme une mesure."""
    assert elevations_by_pos(None) is None
    assert elevations_by_pos(_board(with_elevation=False)) is None

    class _Sans:
        def id_at(self, col, row):
            return None

    assert elevations_by_pos(_Sans()) is None


def test_le_canal_lit_aussi_un_board_duck_type_par_by_coord():
    """`ctx.board` est DUCK-TYPE dans tout le DSL -- `Unobscured` lit deja `by_coord`."""
    class _ParCoord:
        by_coord = {(0, 0): {"elevation": 2}, (0, 1): {"elevation": 0},
                    (0, 2): {"tileId": "Grass"}}

    m = elevations_by_pos(_ParCoord())
    assert m == {(0, 0): 2, (0, 1): 0}


def test_le_canal_est_memoise_sur_l_instance():
    b = _board()
    assert b.elev_by_pos() is b.elev_by_pos()


# ============================================== 2. LA DERIVATION AUTOMATIQUE (`__post_init__`)

def test_un_contexte_avec_board_derive_son_elevation():
    b = _board({(1, 1): 3})
    ctx = DslContext(board=b)
    assert ctx.elev_by_pos is not None and ctx.elev_by_pos[(1, 1)] == 3


def test_un_contexte_sans_board_reste_inerte():
    """Arbre purement NUMERIQUE (`_hits_ctx`, `triggered_ability`) : aucune tuile a gater."""
    assert DslContext().elev_by_pos is None


def test_une_carte_fournie_n_est_jamais_ecrasee():
    b = _board({(1, 1): 3})
    forced = {(1, 1): 0}
    assert DslContext(board=b, elev_by_pos=forced).elev_by_pos is forced


def test_le_replace_du_Filter_preserve_la_carte():
    """`Filter`/`Foreach` refont un `dataclasses.replace(ctx, subject=...)` par element."""
    ctx = DslContext(board=_board({(1, 1): 3}))
    assert dataclasses.replace(ctx, subject={"id": 1}).elev_by_pos == ctx.elev_by_pos


# ================== 3. `FilterTilesIfCanAttackTargetTileFrom` -- la porte bascule DANS LES 2 SENS

CASTER = _unit(1, 1, (0, 0))
TARGET = _unit(2, 2, (5, 5))


def _kept(board, units, cands, elev_override=None, caster=CASTER, target=TARGET):
    ctx = DslContext(units=units, caster=caster, target=target, board=board,
                     elev_by_pos=elev_override)
    ids = [board.id_at(*p) for p in cands]
    out = FilterTilesIfCanAttackTargetTileFrom(Caster(), Target(), FixedTileIds(ids)).select(ctx)
    return [board.coord(t) for t in out]


def test_premier_bras_un_ennemi_hors_portee_d_elevation_ne_compte_PAS():
    """`GetAdjacentUnits(tile, null, enemyOf, false).Count == 0` -- le comptage passe par
    `IterateAdjacentTiles`, donc par la porte. Un ennemi pose 3 crans plus haut n'est PAS un voisin
    natif : la tuile reste attaquable et le premier bras la GARDE.

    Sens de la bascule : PLUS PERMISSIF. Un fix qui ne ferait que restreindre serait FAUX."""
    cand, ennemi = (1, 1), (1, 2)
    assert hexgeo.distance(cand, ennemi) == 1
    assert hexgeo.distance(cand, (5, 5)) > 1               # aucun rattrapage possible
    units = [CASTER, TARGET, _unit(10, 2, ennemi)]

    plat = _board()
    assert _kept(plat, units, [cand]) == []                # ennemi adjacent -> refusee

    relief = _board({ennemi: 3})
    assert _kept(relief, units, [cand]) == [cand]          # hors portee d'elevation -> gardee


def test_second_bras_une_cible_hors_portee_d_elevation_ne_RATTRAPE_pas():
    """`|| TileExtensions.IsAdjacentTo(tile, targetTile)` -> `MovementUtil$$AreTilesAdjacent`, ou
    la porte est FOLDEE dans le `&` final. Sens de la bascule : PLUS RESTRICTIF."""
    cand, ennemi, tgt = (5, 4), (5, 3), (5, 5)
    assert hexgeo.distance(cand, tgt) == 1 and hexgeo.distance(cand, ennemi) == 1
    units = [CASTER, TARGET, _unit(10, 2, ennemi)]

    plat = _board()
    assert _kept(plat, units, [cand]) == [cand]            # rattrapee par l'adjacence a la cible

    relief = _board({tgt: 3})
    assert _kept(relief, units, [cand]) == []              # plus adjacente -> plus de rattrapage


def test_l_identite_survit_a_la_porte():
    """`tile1 == tile2` -> `b = 1` ET `dElev = 0 < 2` : le natif rend VRAI inconditionnellement,
    quelle que soit l'elevation de la tuile (#433-r1)."""
    tgt = (5, 5)
    relief = _board({tgt: 4})
    units = [CASTER, TARGET, _unit(10, 2, (5, 4))]         # un ennemi adjacent -> bras 1 faux
    assert _kept(relief, units, [tgt]) == [tgt]
    assert bq.are_entities_adjacent(tgt, tgt, elevations_by_pos(relief)) is True


# ========================== 4. `UnitsDirectlyBehind` -- le SECOND lecteur du canal (maxDiff = 1)

def test_units_directly_behind_exclut_un_candidat_hors_tolerance_d_elevation():
    """`TilesOnSameElevationSelector` garde si `GetElevationDifference(cand, targetTile) <= 1`.

    C'est le pool de splash de `PlasmaCannonAbility$$ExecuteBehaviour`
    (`PickRandomly(UnitsDirectlyBehind(caster, target), 2)`) : un ennemi derriere la cible mais 3
    crans plus haut n'y entre PAS. Cote runner ce gate etait INERTE."""
    cas, tgt = (0, 3), (3, 3)
    haut, plat_pos = (4, 3), (4, 2)                        # les deux « derriere » (d_caster 4 > 3)
    for p in (haut, plat_pos):
        assert hexgeo.distance(cas, p) > hexgeo.distance(cas, tgt)
        assert hexgeo.distance(p, tgt) == 1
    units = [_unit(1, 1, cas), _unit(2, 2, tgt), _unit(10, 2, haut), _unit(11, 2, plat_pos)]
    caster, target = units[0], units[1]

    def _behind(board):
        ctx = DslContext(units=units, caster=caster, target=target, board=board)
        return sorted(u["id"] for u in UnitsDirectlyBehind().select(ctx))

    assert _behind(_board()) == [10, 11]                   # board plat : les deux
    assert _behind(_board({haut: 3})) == [11]              # relief : le haut sort du pool
    assert _behind(_board({haut: 1})) == [10, 11]          # tolerance +-1 : 1 cran passe


# ============================ 4bis. LE MEME MONTAGE, SUR UN BOARD REEL (entree VERSIONNEE)

def _board_from_bc(board_id: str, pool: str = "global") -> Board:
    """`Board` bati depuis un board VERSIONNE (`data/boards/<pool>/<id>.json`, forme BC), voisinage
    even-q. L'elevation passe par `board._effective_elevation` (Trench = champ BC - 1, #195), le
    MEME calcul que ce que le `boardGraph` live baked."""
    import json
    from board import _effective_elevation
    p = PYDIR.parents[1] / "data" / "boards" / pool / (board_id + ".json")
    raw = json.loads(p.read_text(encoding="utf-8"))
    b = raw.get("board") or raw.get("Board") or {}
    cells = {}
    for c, col in enumerate(b.get("Tiles") or []):
        for r, t in enumerate((col or {}).get("Tile") or []):
            if t is None or bool(t.get("ForceUnplayable")):
                continue
            cells[(c, r)] = _effective_elevation(t.get("TileId"), t.get("Elevation", 0))
    ids = {p_: i + 1 for i, p_ in enumerate(sorted(cells))}
    tiles = [{"id": ids[p_], "col": p_[0], "row": p_[1], "elevation": e, "walkable": True,
              "isWall": False,
              "neighbours": [ids[q] for q in hexgeo.neighbors(p_[0], p_[1]) if q in ids]}
             for p_, e in cells.items()]
    return Board(tiles, adjacency="evenq")


def test_le_gate_mord_sur_un_board_REEL_MC1_67():
    """Le montage EXACT que la confrontation live jouerait, rejoue offline sur l'entree versionnee.

    `MC1_67` porte 5 niveaux d'elevation et **18 paires voisines sur 316** ou `|dElev| >= 2`
    (`probe_433r4r1r4_elevation_gate_perimeter.py --step flips`). Un test sur board PLAT serait vert
    pour la mauvaise raison : ici la porte mord sur des coordonnees reelles."""
    board = _board_from_bc("MC1_67")
    cas, tgt, haut, plat_pos = (0, 0), (1, 2), (1, 3), (2, 2)
    elev = board.elev_by_pos()
    assert elev[tgt] == 2 and elev[haut] == 4 and elev[plat_pos] == 2
    dct = hexgeo.distance(cas, tgt)
    for p in (haut, plat_pos):
        assert hexgeo.distance(p, tgt) == 1
        assert hexgeo.distance(cas, p) > dct                # « derriere » au sens STRICT (#48)

    units = [_unit(1, 1, cas), _unit(2, 2, tgt), _unit(10, 2, haut), _unit(11, 2, plat_pos)]
    ctx = DslContext(units=units, caster=units[0], target=units[1], board=board)
    assert sorted(u["id"] for u in UnitsDirectlyBehind().select(ctx)) == [11]

    # le port d'AVANT (canal non branche) rendait les DEUX -- c'est la divergence qu'on ferme
    ctx_avant = DslContext(units=units, caster=units[0], target=units[1], board=board,
                           elev_by_pos={})
    assert sorted(u["id"] for u in UnitsDirectlyBehind().select(ctx_avant)) == [10, 11]


# ================================================== 5. LE CABLAGE RUNNER (`entities_from_state`)

def _state(board, units):
    from engine.runner.snapshot import load_state
    decision = {"currentPlayer": 1, "units": [
        {"id": u["id"], "visualId": "astarLysander", "alive": True, "team": u["team"],
         "owner": u["team"], "pos": u["pos"], "effects": []} for u in units]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000} for u in units]}
    snapshot = {"units": [{"entityId": u["id"], "entityType": 1,
                           "stats": {"health": 1000, "movement": 3, "turnsStarted": 0},
                           "healthMax": 1000, "traits": [], "unitFlags": [],
                           "unitConfig": {"visualId": "astarLysander", "level": 50,
                                          "passiveAbilityLevel": 50, "activeAbilityLevel": 50,
                                          "abilityVariablesMultiplier": 100}}
                          for u in units]}
    return load_state(decision, observe, snapshot, board=board, ability_states=False)


def test_entities_from_state_pose_desormais_le_canal():
    """Le constructeur de contexte de TOUT behaviour runner. C'est LUI qui laissait la porte
    inerte pour l'ensemble du substrat."""
    from engine.runner.abilities.behaviours.context import entities_from_state
    board = _board({(1, 1): 3})
    st = _state(board, [_unit(1, 1, (0, 0)), _unit(2, 2, (5, 5))])
    ctx = entities_from_state(st, 1, 2)
    assert ctx.elev_by_pos is not None
    assert ctx.elev_by_pos[(1, 1)] == 3 and ctx.elev_by_pos[(0, 0)] == 0


def test_le_verdict_runner_de_MV71_bascule_avec_l_elevation():
    """Face RUNNER du dernier maillon de `MV71SniperDroneSquadAttackAbility$$PickTile` :
    `_filter_can_attack_target_tile_from` rend l'id de tuile, ou None (-> cast NO-OP)."""
    from engine.runner.abilities.loki.mv71 import _filter_can_attack_target_tile_from as f
    cand, ennemi, tgt, cas = (1, 1), (1, 2), (5, 5), (0, 0)
    units = [_unit(1, 1, cas), _unit(2, 2, tgt), _unit(10, 2, ennemi)]

    plat = _board()
    assert f(_state(plat, units), 1, 2, plat.id_at(*cand)) is None
    relief = _board({ennemi: 3})
    assert f(_state(relief, units), 1, 2, relief.id_at(*cand)) == relief.id_at(*cand)


# ============================================================ 6. NON-REGRESSION (canal absent)

def test_un_board_sans_canal_d_elevation_se_comporte_comme_avant():
    """`boardGraph` anterieur au capteur / board bati a la main : la porte reste inerte et le
    moteur garde EXACTEMENT le comportement permissif d'avant -- aucun faux negatif introduit."""
    cand, ennemi = (1, 1), (1, 2)
    units = [CASTER, TARGET, _unit(10, 2, ennemi)]
    sans = _board(with_elevation=False)
    assert DslContext(board=sans).elev_by_pos is None
    assert _kept(sans, units, [cand]) == []                # verdict d'avant, a l'identique
