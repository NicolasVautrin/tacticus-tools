"""R28-1 -- GARDE de l'ORDRE dans lequel `PickRandomly` voit son pool.

CRITERE TRANCHE (decompile = verite). `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` :

    candidates = source.Select(entities).ToList()      # AUCUN tri
    while (i < amount) { if (candidates.Count < 1) return result
                         idx = rng.NextInternal(0, candidates.Count)
                         result.Add(candidates.ElementAt(idx)); candidates.RemoveAt(idx); i++ }

Le seul tri natif du chemin est l'`OrderBy` d'`IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`
(`if (Count > 1) targets.OrderBy(b__5_0).ToList()`), qui s'applique **APRES** la resolution du selecteur.
Le port id-triait le pool AVANT le tirage : a index de tirage EGAL il piquait une AUTRE unite des que
`|pool| > amount`.

L'ordre SOURCE d'un selecteur d'occupation est celui des TUILES (le natif itere le selecteur de tuiles et
resout l'occupant de chacune, `UnitsOnTilesSelector$$Select`), et il y a DEUX iterateurs natifs distincts :
  * `AdjacentTiles`    -> `TileQuery$$IterateAdjacentTiles`    = liste d'adjacence STOCKEE (champ brut
                          `boardGraph.neighbours`) -> `Board.neighbours_native`
  * `SurroundingTiles` -> `TileQuery$$IterateSurroundingTiles` = TRIPLE BOUCLE en coordonnees CUBE
                          (`for x { for y { for z { if (x+y+z==0) yield } } }`)

Ce que ces tests prouvent, et pourquoi ils rougiraient si la reponse etait l'autre :
  (1) `_tile_enum_rank(order='surrounding')` == une RE-IMPLEMENTATION INDEPENDANTE de la triple boucle
      cube transcrite du decompile (pas `hexgeo.disk` : sinon c'est une tautologie).
  (2) `_tile_enum_rank(order='adjacent')` == le champ BRUT `neighbours`, ET pas sa version triee.
  (3) OFFLINE, sur un board synthetique ou l'ordre des TUILES est l'INVERSE de l'ordre des ids :
      `AdjacentEnemies` rend l'ordre des tuiles. Rougit si quelqu'un remet un tri par id.
  (4) LIVE (BringerOfDespair 1022, `blackTerminator` -- hero au `--list-pool`) : geometrie CRAFTEE ou
      les deux modeles predisent des VICTIMES DIFFERENTES ; la victime live tranche. Le test EXIGE que
      le scenario soit discriminant, sinon il le dit au lieu de passer pour rien.

ASCII only.
"""
from __future__ import annotations

import pytest

import hexgeo
from engine.dsl.base import DslContext, _tile_enum_rank
from engine.entities.pathfinding.board import Board
from engine.entities.selectors import AdjacentEnemies, CasterTile
from engine.dsl.base import Const


# --------------------------------------------------------------------- oracles independants

def _native_surrounding_order(center, radius):
    """Transcription DIRECTE de `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` :
    triple boucle CUBE bornee a +-radius sur chaque axe, garde `x+y+z == 0`, emission en axial.
    Ecrite depuis le DECOMPILE, PAS depuis `hexgeo.disk` -- c'est ce qui en fait un oracle."""
    cx, cy, cz = hexgeo.to_cube(center[0], center[1])
    out = []
    for x in range(cx - radius, cx + radius + 1):
        for y in range(cy - radius, cy + radius + 1):
            for z in range(cz - radius, cz + radius + 1):
                if x + y + z == 0:
                    out.append(hexgeo.from_cube(x, z))
    return out


def _grid(w=5, h=5):
    """Board synthetique : champ BRUT `neighbours` pose EXPRES dans un ordre non trie (ordre inverse
    des ids) pour rendre le tri par id observable."""
    tiles = []
    tid = {}
    n = 0
    for col in range(w):
        for row in range(h):
            tid[(col, row)] = n
            n += 1
    for (col, row), i in tid.items():
        nb = [tid[p] for p in hexgeo.neighbors(col, row) if p in tid]
        tiles.append({"id": i, "col": col, "row": row, "elevation": 0, "walkable": True,
                      "isWall": False, "neighbours": list(reversed(sorted(nb)))})
    return Board(tiles, adjacency="native_sym"), tid


# --------------------------------------------------------------------- (1)(2) l'ordre d'enumeration

@pytest.mark.parametrize("radius", [1, 2, 3])
def test_surrounding_rank_matches_native_cube_loop(radius):
    """(1) L'ordre 'surrounding' du port == la triple boucle cube du decompile, re-implementee ici."""
    board, tid = _grid(7, 7)
    center = (3, 3)
    rank = _tile_enum_rank(board, center, radius, "surrounding")
    want = [p for p in _native_surrounding_order(center, radius) if p in tid]
    got = [p for p, _ in sorted(rank.items(), key=lambda kv: kv[1]) if p in tid]
    # `_tile_enum_rank` indexe TOUTES les positions du disque (hors board incluses) : on compare la
    # sous-suite des positions REELLES du board, dans l'ordre des rangs.
    assert got == want, f"ordre 'surrounding' {got[:12]} != triple boucle cube native {want[:12]}"


def test_adjacent_rank_is_the_raw_neighbours_field_not_sorted():
    """(2) L'ordre 'adjacent' == le champ BRUT `neighbours`, PAS sa version triee/symetrisee."""
    board, tid = _grid()
    center = (2, 2)
    ctile = board.id_at(*center)
    raw = board.neighbours_native(ctile)
    assert raw != sorted(raw), "board de test non discriminant (champ brut deja trie)"
    assert raw != board.neighbours(ctile), "`neighbours_native` doit differer de `neighbours` (trie)"
    rank = _tile_enum_rank(board, center, 1, "adjacent")
    got = [p for p, _ in sorted(rank.items(), key=lambda kv: kv[1])]
    assert got == [board.coord(t) for t in raw], f"ordre 'adjacent' {got} != champ brut {raw}"


# --------------------------------------------------------------------- (3) le selecteur d'occupation

def test_adjacent_enemies_yields_tile_order_not_id_order():
    """(3) `AdjacentEnemies(CasterTile())` = `Units(AdjacentTiles(caster))` : ordre des TUILES.
    Board craft ou l'ordre des tuiles est l'INVERSE de l'ordre des ids d'unite -> rougit si un tri
    par id revient (c'est exactement ce que faisait le port avant R28-1)."""
    board, tid = _grid()
    center = (2, 2)
    ctile = board.id_at(*center)
    raw = board.neighbours_native(ctile)
    assert len(raw) >= 3, "ring trop petit"
    caster = {"id": 1, "team": 1, "pos": {"col": center[0], "row": center[1]}, "hp": 10, "alive": True}
    # id CROISSANT sur des tuiles d'ordre brut DECROISSANT -> les deux ordres sont opposes
    units = [caster]
    for k, t in enumerate(raw[:3]):
        c = board.coord(t)
        units.append({"id": 100 + (3 - k), "team": 2, "pos": {"col": c[0], "row": c[1]},
                      "hp": 10, "alive": True})
    ctx = DslContext(units=units, caster=caster, board=board)
    got = [u["id"] for u in AdjacentEnemies(CasterTile(), Const(1)).select(ctx)]
    want = [103, 102, 101]
    assert got == want, f"ordre rendu {got} != ordre des TUILES {want} (tri par id = {sorted(want)})"
    assert got != sorted(got), "setup non discriminant : ordre des tuiles == ordre des ids"


# --------------------------------------------------------------------- (4) live discriminant

@pytest.fixture(scope="module")
def bod(live_session, rpc):
    """Cast LIVE de BringerOfDespair avec 2 candidats bonus dont l'ordre TUILE et l'ordre ID sont
    opposes. Runner DISPOSE des la mesure capturee."""
    import probe_r28_pick_order as P
    reg = P.setup(rpc, "777", "MC1_67")
    if reg is None or "live" not in reg:
        pytest.skip("scenario live BringerOfDespair non montable")
    try:
        src = P.port_victim(reg, id_sorted=False)
        idm = P.port_victim(reg, id_sorted=True)
        return {"live": sorted(t for t in reg["live"] if t != reg["target"]),
                "src": src["victims"], "id": idm["victims"],
                "target": reg["target"], "pool_hint": (reg["hi"], reg["lo"])}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": reg["rid"]}, 20)
        except Exception:
            pass
        try:
            reg["state_file"].unlink()
        except Exception:
            pass


@pytest.fixture(scope="module")
def plasma(live_session, rpc):
    """Cast LIVE de PlasmaCannon (1150, `darkaTerminator`) avec **3** unites directly-behind
    (amount=2 -> |pool| > amount) et des ids assignes a CONTRE-SENS du rang CUBE : c'est le 2e
    iterateur natif (`SurroundingTiles` -> `IterateSurroundingTiles`) qui est mis a l'epreuve."""
    import probe_r28_pick_order as P
    reg = P.setup_plasma(rpc, "777", "MC1_67")
    if reg is None or "live" not in reg:
        pytest.skip("scenario live PlasmaCannon 3-behind non montable")
    try:
        src = P.port_victims_plasma(reg, id_sorted=False)
        idm = P.port_victims_plasma(reg, id_sorted=True)
        live_n = P.P215.count_genrand(reg["rng_before"], reg["rng_after"])
        rs = []
        for tid, ph in src["per"].items():
            lp = reg["live"].get(tid) or []
            if ph and len(lp) == len(ph):
                rs += [a / b for a, b in zip(lp, ph)]
        return {"live": sorted(t for t in reg["live"] if t != reg["target"]),
                "src": src["victims"], "id": idm["victims"],
                "live_n": live_n, "src_n": src["n"], "id_n": idm["n"], "ratios": rs}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": reg["rid"]}, 20)
        except Exception:
            pass
        try:
            reg["state_file"].unlink()
        except Exception:
            pass


def test_live_plasma_splash_follows_cube_order(plasma):
    """(4bis) 2e iterateur : avec 3 candidats derriere la cible et `amount=2`, les 2 splashes LIVE sont
    ceux que predit l'ordre CUBE, pas ceux que predit l'ordre des ids -- et le port est bit-exact."""
    assert plasma["src"] != plasma["id"], (
        f"scenario NON discriminant (les deux modeles predisent {plasma['src']})")
    assert set(plasma["live"]) == set(plasma["src"]), (
        f"splash live {plasma['live']} != prediction ordre CUBE {plasma['src']} "
        f"(ordre id predisait {plasma['id']})")
    assert plasma["src_n"] == plasma["live_n"], (
        f"le port consomme {plasma['src_n']} genrand vs {plasma['live_n']} LIVE -- flux desaligne")
    assert plasma["ratios"] and max(abs(x - 1.0) for x in plasma["ratios"]) < 1e-9, (
        f"port non bit-exact per-coup (ratios={[round(x, 4) for x in plasma['ratios']]})")


def test_live_bonus_victim_follows_source_order(bod):
    """(4) La victime BONUS live est celle que predit l'ordre SOURCE, PAS celle que predit l'ordre des
    ids. Le test exige d'abord que le scenario SEPARE les deux modeles."""
    assert bod["src"] != bod["id"], (
        f"scenario NON discriminant (les deux modeles predisent {bod['src']}) -- re-crafter la "
        f"geometrie, ce test ne garde rien en l'etat")
    assert set(bod["live"]) == set(bod["src"]), (
        f"victime bonus live {bod['live']} != prediction ordre SOURCE {bod['src']} "
        f"(ordre id predisait {bod['id']})")
    assert set(bod["live"]) != set(bod["id"]), (
        f"victime bonus live {bod['live']} == prediction ordre ID {bod['id']} -> le natif trierait "
        f"son pool avant le tirage (contredit `PickRandomAmountSelector$$Select`)")
