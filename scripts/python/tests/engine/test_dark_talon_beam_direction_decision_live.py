"""DIRECTION du beam DarkTalonStrike (1092) sur la face DECISION (#126), confrontee au LIVE.

`IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$GetTilesInBestLine` ne DEDUIT
pas la direction du rayon, il la CHOISIT :

    ring    = AdjacentTiles(target@0x178)
    nearest = First( SortByDistance(AdjacentTiles(caster@0x160), target@0x178), 1 )
    angle   = AngleBetweenLines(caster@0x160, nearest, target@0x178, subject@0x180)
    count   = Count( Units( GetTilesInLine(subject@0x180) ) )
    best    = First( SortByFormula( SortByFormula(ring, angle, ASC), count, DESC ), 1 )
    return    target@0x178  op_Addition  GetTilesInLine(best)

`IdunBattle.Entities.Selectors.SortByFormulaSelector$$Select` delegue a `Enumerable.OrderBy` /
`OrderByDescending` (flag `+0x28` du ctor : 0 -> DESCENDING) : deux tris STABLES chaines -> cle
PRIMAIRE = nb d'ennemis alignes (DECROISSANT), tie-break = ecart ANGULAIRE a la direction d'approche.

CE QUE CE TEST GARDE — que la DECISION offline colle au natif sur un etat ou la meilleure direction
n'est PAS le prolongement `caster -> aim`, ET que l'argmax est PORTANT (le meme moteur, feuille
remise au PROLONGEMENT, rend une decision DIFFERENTE du natif). Sans cette 2e assertion le test
serait incapable d'echouer sur un port qui deduit la direction au lieu de la choisir.

Scenario DERIVE du board (aucune tuile hardcodee) : caster P, chaine d'ennemis E1 = P + d1,
E2 = E1 + d2, E3 = E1 + 2*d2 avec `d2` a 60 deg de `d1` -> `dist(P, E3) = 3`, hors de la portee de
cast ; toutes les tuiles au MEME palier d'elevation (le gate #124 reste inerte : on n'exerce QUE la
direction) et le prolongement `E1 + d1` existe et reste VIDE.
    prolongement -> util(E1) = 1 (la tuile visee seule) < MIN_UTILITY(2) -> aucun NonComparable ;
    argmax       -> util(E1) = 1 + 2 = 3 -> cast 1092 sur l'entite-tuile de E1, comme le natif.

ORACLE = l'IA NATIVE sur le MEME etat (`aiDryRunAllUnits` -> `CalculateNextActionForUnit`), jamais
`aiPredict` (preview d'attaque). On compare ABILITY + CIBLE.

Lit l'etat LIVE, aucune tuile/RVA hardcodee. ASCII only.
Probe jumeau : `probe_126_dark_talon_beam_direction.py`.
"""
from __future__ import annotations

from collections import deque

import pytest

import hexgeo
from engine import weights as W
from engine.playbook import scene as _scene
from engine_validate import engine_decide

BOARD = "MC1_67"


# --------------------------------------------------------------------------- geometrie (offline)


def _move_ring(p, walk, elev):
    """`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` : walkable +
    porte `|Delta elev| < 2` -- le graphe de MOUVEMENT natif (waypoints du driver de placement)."""
    if elev.get(p) is None:
        return []
    return [n for n in hexgeo.neighbors(p[0], p[1])
            if walk.get(n) and elev.get(n) is not None and abs(elev[n] - elev[p]) < 2]


def _gated_path(src, dst, walk, elev):
    """Chemin BFS sur le graphe de MOUVEMENT natif (la ligne hex droite ne suffit pas sur du relief)."""
    if src == dst:
        return [src]
    prev, q = {src: None}, deque([src])
    while q:
        cur = q.popleft()
        for n in _move_ring(cur, walk, elev):
            if n in prev:
                continue
            prev[n] = cur
            if n == dst:
                path, p = [], n
                while p is not None:
                    path.append(p)
                    p = prev[p]
                return list(reversed(path))
            q.append(n)
    return []


def _find_elbow(elev, walk):
    """(P, E1, E2, E3, prolongement) : coude a 60 deg -- cf. l'en-tete du module."""
    cube = {p: hexgeo.to_cube(p[0], p[1]) for p in elev}
    dirs = [(0, -1, 1), (1, -1, 0), (1, 0, -1), (0, 1, -1), (-1, 1, 0), (-1, 0, 1)]
    for P in sorted(elev):
        if not walk.get(P) or elev.get(P) is None:
            continue
        px, _py, pz = cube[P]
        for i, d1 in enumerate(dirs):
            for di in (-1, 1):
                d2 = dirs[(i + di) % 6]
                e1 = hexgeo.from_cube(px + d1[0], pz + d1[2])
                ext = hexgeo.from_cube(px + 2 * d1[0], pz + 2 * d1[2])
                if e1 not in cube or ext not in cube:
                    continue
                ex, _ey, ez = cube[e1]
                chain = [hexgeo.from_cube(ex + d2[0] * k, ez + d2[2] * k) for k in (1, 2)]
                tiles = [P, e1, ext] + chain
                if any(t not in cube or not walk.get(t) for t in tiles):
                    continue
                if len({elev[t] for t in tiles}) != 1:
                    continue                          # meme palier -> gate #124 inerte
                if hexgeo.distance(P, chain[1]) != 3:
                    continue                          # E3 hors portee de cast
                return P, e1, chain[0], chain[1], ext
    return None


def _prolongement(origin, aim, _enemy_set, _walkable_at, _elevation_at, _tile_exists):
    """La geometrie PRE-#126 : `best` = prolongement du rayon `caster -> aim`
    (`dir = cube(aim) - cube(origin)`), au lieu de l'argmax de `GetTilesInBestLine`."""
    ox, _oy, oz = hexgeo.to_cube(origin[0], origin[1])
    ax, _ay, az = hexgeo.to_cube(aim[0], aim[1])
    dx, dz = ax - ox, az - oz
    return None if (dx == 0 and dz == 0) else hexgeo.from_cube(ax + dx, az + dz)


# --------------------------------------------------------------------------- harnais live


def _board(rpc, rid):
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    tiles = bg.get("tiles") or []
    if not tiles:
        pytest.skip("boardGraph indispo")
    return ({(t["col"], t["row"]): t.get("elevation") for t in tiles},
            {(t["col"], t["row"]): bool(t.get("walkable")) for t in tiles})


def _positions(rpc, rid):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    return dv, {u["id"]: (u["pos"]["col"], u["pos"]["row"])
                for u in (dv.get("units") or []) if u.get("alive") and u.get("pos")}


def _drive_to(rpc, rid, walk, elev, wanted: dict, rounds: int = 14) -> bool:
    """DOCTRINE « drive positions, don't blame geometry » : waypoints pris sur le CHEMIN de
    mouvement natif (le plus loin d'abord), `endturn` pour re-armer le deplacement."""
    for _ in range(rounds):
        _dv, pos = _positions(rpc, rid)
        if all(pos.get(u) == dest for u, dest in wanted.items()):
            return True
        occupied = set(pos.values())
        for uid, dest in wanted.items():
            cur = pos.get(uid)
            if cur is None or cur == dest:
                continue
            for p in reversed(_gated_path(cur, dest, walk, elev)[1:]):
                if not walk.get(p) or (p in occupied and p != dest):
                    continue
                r = rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": uid, "to": {"col": p[0], "row": p[1]}}}, 60)
                if isinstance(r, dict) and r.get("ok") \
                        and (r.get("actions") or [{}])[0].get("mutated"):
                    occupied.discard(cur)
                    occupied.add(p)
                    break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    _dv, pos = _positions(rpc, rid)
    return all(pos.get(u) == dest for u, dest in wanted.items())


def _give_turn_back(rpc, rid, myplayer):
    for _ in range(3):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        if dv.get("currentPlayer") == myplayer:
            return
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)


def _native(rpc, rid, cid):
    """`aiDryRunAllUnits` = `CalculateNextActionForUnit` en LECTURE SEULE (jamais `aiPredict`)."""
    dry = rpc("aiDryRunAllUnits", {"runnerId": rid}, 150)
    nat = next((u for u in (dry.get("units") or []) if u.get("unitId") == cid), None)
    ab = tgt = None
    for m in ((nat or {}).get("proposed") or []):
        if m.get("cls") == "ActiveAbilityMessage" and ab is None:
            ab, tgt = m.get("abilityType"), m.get("targetId")
    return {"ability": ab, "target": tgt}


def _engine(rpc, sid, rid, cid, wt, predictor):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    if predictor is not None:
        _scene.refresh_shields(predictor, rpc, rid)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    e = engine_decide(sid, rid, dv, mbu, cid, wt, predictor)
    return {"ability": e.get("ability") if e.get("kind") == "ability" else None,
            "target": e.get("target"), "kind": e.get("kind")}


# --------------------------------------------------------------------------- le test


def test_dark_talon_beam_direction_decision_live(live_session, rpc, build_runner):
    """1092 : quand la meilleure direction n'est PAS le prolongement `caster -> aim`, le natif
    CASTE (il compte les ennemis de la MEILLEURE direction) ; le port argmax aussi. Le meme port
    au PROLONGEMENT ne caste pas -> l'argmax est PORTANT."""
    import engine.playbook.noncomparable.dark_talon_strike as DTS

    rid = build_runner("41171", ["--board", BOARD, "--p-units", "darkaAzrael",
                                 "--a-units", "eldarRanger,eldarRanger,eldarRanger",
                                 "--hp-target", "90000", "--hp-player", "90000"])["rid"]
    elev, walk = _board(rpc, rid)
    win = _find_elbow(elev, walk)
    if win is None:
        pytest.skip(f"board {BOARD} n'offre pas de configuration coude a 60 deg")
    P, e1, e2, e3, ext = win
    dv, _pos = _positions(rpc, rid)
    mine = [u for u in (dv.get("units") or []) if u.get("ctrl") and u.get("alive")]
    cid = next((u["id"] for u in mine if u.get("visualId") == "darkaAzrael"), None)
    if cid is None:
        pytest.skip("darkaAzrael absent (pool/spawn)")
    myplayer = next((u.get("owner") for u in mine), None)
    eids = [u["id"] for u in (dv.get("units") or [])
            if u.get("owner") != myplayer and u.get("alive")]
    if len(eids) < 3:
        pytest.skip("moins de 3 ennemis vivants")
    wanted = {cid: P, eids[0]: e1, eids[1]: e2, eids[2]: e3}
    if not _drive_to(rpc, rid, walk, elev, wanted):
        _dv, pos = _positions(rpc, rid)
        pytest.skip(f"placement incomplet (P={P} E1={e1} E2={e2} E3={e3}): "
                    f"{ {u: pos.get(u) for u in wanted} } != { wanted }")
    _give_turn_back(rpc, rid, myplayer)

    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)
    nat = _native(rpc, rid, cid)
    argmax = _engine(rpc, live_session, rid, cid, wt, predictor)
    orig = DTS._best_line_direction
    DTS._best_line_direction = _prolongement
    try:
        pre = _engine(rpc, live_session, rid, cid, wt, predictor)
    finally:
        DTS._best_line_direction = orig

    util_argmax = DTS._beam_count(P, e1, {e1, e2, e3}, walk, elev)
    ctx = (f"P={P} E1={e1} E2={e2} E3={e3} prolongement={ext} (palier {elev[P]}) ; "
           f"util(argmax, aim E1)={util_argmax} ; natif={nat} argmax={argmax} prolongement={pre}")
    assert nat["ability"] == 1092, (
        f"le natif ne CASTE PAS 1092 : le scenario n'exerce pas la direction du beam -- {ctx}")
    assert util_argmax >= 2, f"util argmax < MIN_UTILITY, scenario non exerce -- {ctx}"
    assert (argmax["ability"], argmax["target"]) == (nat["ability"], nat["target"]), (
        f"decision ARGMAX != natif -- {ctx}")
    assert (pre["ability"], pre["target"]) != (nat["ability"], nat["target"]), (
        f"l'argmax de direction n'est PAS portant : le prolongement rend deja la decision native, "
        f"le test serait incapable d'echouer sur un port qui DEDUIT la direction -- {ctx}")
    assert pre["ability"] != 1092, (
        f"avec le prolongement le moteur ne devrait pas caster 1092 (util 1 < MIN_UTILITY) -- {ctx}")
