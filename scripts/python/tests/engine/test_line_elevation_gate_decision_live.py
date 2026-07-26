"""Gate d'ELEVATION de la ligne hex sur les DEUX faces DECISION (#124), confronte au LIVE.

`IdunBattle.Core.Services.BattleQuery$$GetTilesBehind` marche la ligne TUILE PAR TUILE et
s'arrete au premier echec de `IdunBattle.Core.Services.TileUtil$$IsTileValidForList` :

    if (tileComponent+0x41 != 0)          return false
    if (!checkWalkable)                   return tileComponent+0x40 == 0     # PAS de gate d'elevation
    if (!TileExtensions.IsWalkable(tile)) return false
    if (refTile != null)                  return |elev(ref) - elev(tile)| < 2

Le gate d'elevation vit DANS la branche walkable : `settings+0x10 = 1` l'active, `settings+0x11 = 1`
fait SUIVRE la tuile de reference. Les deux consommateurs testes ici sont a `1/1` (lu au decompile,
#117) et leur face DECISION passe par LA MEME fonction native que leur face COMBAT :
  * `IdunBattle.AI.Playbook.Loki.DarkTalonStrikePlaybook$$EvaluateNonComparable` appelle
    `DarkTalonStrikeAbility$$GetTilesInBestLine` puis `GetTilesInLine` (settings `0x101`) ;
  * `IdunBattle.AI.Playbook.Loki.ExcruciatingFrequenciesPlaybook$$MakeDamagePredictions` appelle
    `ExcruciatingFrequenciesAbility$$GetAttackTargets` -> `GetAffectedTiles` (settings `0x101`).

CE QUE CE TEST GARDE — que la DECISION offline colle au natif sur un etat ou la ligne franchit une
marche >= 2, ET que le gate est PORTANT (le meme moteur, feuille remise en RAYON DROIT sans gate,
rend une decision DIFFERENTE du natif). Sans cette 2e assertion le test serait incapable d'echouer
sur un port qui ignore `IsTileValidForList`.

  (a) DarkTalonStrike (1092, `darkaAzrael`), board `C4_02`, colonne a marche `1 -> 3` :
      caster / ennemi VISE / ennemi DERRIERE la marche.
        rayon droit  -> util 2 >= MIN_UTILITY(2) -> le port CASTE 1092 (le natif, non) ;
        rayon gate   -> util 1  -> pas de NonComparable -> fallback Comparable == natif.

  (b) ExcruciatingFrequencies (1197, `emperNoiseMarine`), board `C3_59`, falaise `0 -> 4` :
      le test DERIVE une fenetre AVEUGLE (P, t1, t2, t3) telle que le rayon droit depuis P franchit
      la marche et qu'AUCUNE position du voisinage-mouvement de P (BFS gate, profondeur 5) ne permet
      une ligne GATEE contenant t2/t3. Sans cette condition le natif CONTOURNE la marche par le
      flanc (mesure C4_02 : depuis (3,6) sa ligne `[(4,6),(5,7),(6,7)]` PASSE le gate) et le
      scenario cesse de discriminer.
        rayon droit  -> candidat 1197 (2 ennemis tuables) -> le port CASTE 1197 (le natif, non) ;
        rayon gate   -> AUCUN candidat 1197 -> attaque normale == natif.

ORACLE = l'IA NATIVE sur le MEME etat (`aiDryRunAllUnits` -> `CalculateNextActionForUnit`), jamais
`aiPredict` (preview d'attaque). On compare ABILITY + CIBLE ; la DESTINATION du move est l'axe
POSITIONNEMENT (proxy a plancher, cf. `test_playbook_live`) et n'entre pas dans le critere.

Lit l'etat LIVE, aucune tuile/RVA hardcodee (les fenetres d'elevation sont derivees du `boardGraph`).
ASCII only. Probe jumeau : `probe_124_line_elevation_decision.py`.
"""
from __future__ import annotations

from collections import deque

import pytest

import hexgeo
from engine import weights as W
from engine.playbook import scene as _scene
from engine_validate import engine_decide

BOARD_A = "C4_02"
BOARD_B = "C3_59"
BLIND_DEPTH = 5              # portee de deplacement observee (~3 hexes) + marge


# --------------------------------------------------------------------------- geometrie (offline)


def _move_ring(p, walk, elev):
    """Voisins de `p` atteignables par MOUVEMENT : walkable + porte `|Delta elev| < 2`
    (`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`) -- MEME porte
    que la ligne, donc un palier a +2 est inaccessible A PIED comme A LA LIGNE."""
    if elev.get(p) is None:
        return []
    return [n for n in hexgeo.neighbors(p[0], p[1])
            if walk.get(n) and elev.get(n) is not None and abs(elev[n] - elev[p]) < 2]


def _gated_line(P, aim, n, walk, elev):
    """Mirror OFFLINE de `GetTilesBehind(P, aim, checkWalkable=1, updateRef=1, n)` -- sert au CHOIX
    du scenario (le port teste, lui, vit dans `engine.battle_query.get_tiles_behind`)."""
    ox, _oy, oz = hexgeo.to_cube(*P)
    ax, _ay, az = hexgeo.to_cube(*aim)
    dx, dz = ax - ox, az - oz
    out, ref = [], P
    for k in range(n):
        p = hexgeo.from_cube(ax + dx * k, az + dz * k)
        if not walk.get(p) or elev.get(p) is None or abs(elev[p] - elev[ref]) >= 2:
            break
        out.append(p)
        ref = p
    return out


def _straight_line(P, aim, n):
    """La geometrie PRE-#124 : rayon cube droit, sans aucun gate de tuile."""
    ox, _oy, oz = hexgeo.to_cube(*P)
    ax, _ay, az = hexgeo.to_cube(*aim)
    dx, dz = ax - ox, az - oz
    if dx == 0 and dz == 0:
        return []
    return [hexgeo.from_cube(ox + dx * k, oz + dz * k) for k in range(1, n + 1)]


def _find_break_window(elev, walk, need=4):
    """Colonne + `need` rangees consecutives walkables : marche `w0 -> w1` < 2 (caster -> tuile
    visee) puis marche `w1 -> w2` >= 2 (IMMEDIATEMENT apres la tuile visee)."""
    for col in sorted({c for (c, _r) in elev}):
        rows = sorted({r for (c, r) in elev if c == col})
        for i in range(len(rows) - need + 1):
            win = rows[i:i + need]
            if win != list(range(win[0], win[0] + need)):
                continue
            if any(not walk.get((col, r)) or elev.get((col, r)) is None for r in win):
                continue
            e = [elev[(col, r)] for r in win]
            if abs(e[1] - e[0]) < 2 and abs(e[2] - e[1]) >= 2:
                return col, win, e
    return None


def _find_blind_window(elev, walk, n_tiles=3, depth=BLIND_DEPTH):
    """(P, t1, t2, t3, |voisinage|) : le rayon DROIT de `n_tiles` depuis P franchit une marche >= 2
    entre t1 et t2 (t2, t3 sur le meme palier) ET aucune position a <= `depth` mouvements de P ne
    permet une ligne GATEE contenant t2 ou t3."""
    tiles = {p: e for p, e in elev.items() if walk.get(p) and e is not None}
    for P in sorted(tiles):
        for t1 in _move_ring(P, walk, elev):
            ox, _oy, oz = hexgeo.to_cube(*P)
            dx = hexgeo.to_cube(*t1)[0] - ox
            dz = hexgeo.to_cube(*t1)[2] - oz
            t2 = hexgeo.from_cube(ox + dx * 2, oz + dz * 2)
            t3 = hexgeo.from_cube(ox + dx * 3, oz + dz * 3)
            if t2 not in tiles or t3 not in tiles:
                continue
            if abs(tiles[t2] - tiles[t1]) < 2 or abs(tiles[t3] - tiles[t2]) >= 2:
                continue
            seen, q = {P}, deque([(P, 0)])
            while q:
                cur, d = q.popleft()
                if d >= depth:
                    continue
                for nb in _move_ring(cur, walk, elev):
                    if nb not in seen:
                        seen.add(nb)
                        q.append((nb, d + 1))
            if all(t2 not in _gated_line(Q, aim, n_tiles, walk, elev)
                   and t3 not in _gated_line(Q, aim, n_tiles, walk, elev)
                   for Q in seen for aim in hexgeo.neighbors(Q[0], Q[1]) if aim in tiles):
                return P, t1, t2, t3, len(seen)
    return None


def _gated_path(src, dst, walk, elev):
    """Chemin BFS sur le graphe de MOUVEMENT natif. La ligne hex droite ne suffit PAS des que le
    trajet doit contourner une falaise -- c'est ce qui fait echouer un placement sur du relief."""
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


# --------------------------------------------------------------------------- harnais live


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


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
    """DOCTRINE « drive positions, don't blame geometry » : amene chaque unite de `wanted` sur sa
    tuile, waypoints pris sur le CHEMIN de mouvement natif (le plus loin d'abord), `endturn` pour
    re-armer le deplacement."""
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
                if _ok(r) and (r.get("actions") or [{}])[0].get("mutated"):
                    occupied.discard(cur)
                    occupied.add(p)
                    break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    _dv, pos = _positions(rpc, rid)
    return all(pos.get(u) == dest for u, dest in wanted.items())


def _spare_tiles(walk, elev, keep_away, n, min_sep=3):
    """`n` tuiles walkables LOIN des tuiles de scenario et MUTUELLEMENT eloignees : des ennemis
    parques alignes formeraient une ligne parasite."""
    out = []
    for p in sorted(walk):
        if not walk[p] or elev.get(p) is None:
            continue
        if any(hexgeo.distance(p, k) <= 3 for k in keep_away):
            continue
        if all(hexgeo.distance(p, q) >= min_sep for q in out):
            out.append(p)
        if len(out) >= n:
            break
    return out


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
    ab = tgt = to = None
    for m in ((nat or {}).get("proposed") or []):
        if m.get("cls") == "ActiveAbilityMessage" and ab is None:
            ab, tgt = m.get("abilityType"), m.get("targetId")
        if m.get("cls") == "MoveUnitMessage" and to is None:
            p = m.get("to") or {}
            to = (p.get("col"), p.get("row")) if p.get("col") is not None else None
    return {"ability": ab, "target": tgt, "to": to}


def _engine(rpc, sid, rid, cid, wt, predictor):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    if predictor is not None:
        _scene.refresh_shields(predictor, rpc, rid)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    e = engine_decide(sid, rid, dv, mbu, cid, wt, predictor)
    return {"ability": e.get("ability") if e.get("kind") == "ability" else None,
            "target": e.get("target"), "to": e.get("to"), "kind": e.get("kind")}


def _roster(rpc, rid, caster_vis):
    dv, _pos = _positions(rpc, rid)
    mine = [u for u in (dv.get("units") or []) if u.get("ctrl") and u.get("alive")]
    cid = next((u["id"] for u in mine if u.get("visualId") == caster_vis), None)
    if cid is None:
        pytest.skip(f"{caster_vis} absent (pool/spawn)")
    myplayer = next((u.get("owner") for u in mine), None)
    allies = [u["id"] for u in mine if u.get("id") != cid]
    eids = [u["id"] for u in (dv.get("units") or [])
            if u.get("owner") != myplayer and u.get("alive")]
    return cid, myplayer, allies, eids


# --------------------------------------------------------------------------- (a) DarkTalonStrike


def test_dark_talon_strike_decision_elevation_gate_live(live_session, rpc, build_runner):
    """(a) 1092 : derriere une marche >= 2, le natif NE caste PAS DarkTalonStrike (util 1 < 2) ;
    le port gate non plus. Le meme port en RAYON DROIT le caste -> le gate est PORTANT."""
    import engine.playbook.noncomparable.dark_talon_strike as DTS

    rid = build_runner("41171", ["--board", BOARD_A, "--p-units", "darkaAzrael",
                                 "--a-units", "eldarRanger," * 4 + "eldarRanger",
                                 "--hp-target", "90000", "--hp-player", "90000"])["rid"]
    elev, walk = _board(rpc, rid)
    win = _find_break_window(elev, walk, 4)
    if win is None:
        pytest.skip(f"board {BOARD_A} n'offre pas de fenetre de marche >= 2")
    col, rows, e = win
    cid, myplayer, allies, eids = _roster(rpc, rid, "darkaAzrael")
    if len(eids) < 2:
        pytest.skip("moins de 2 ennemis vivants")
    caster_p, aim_p, behind_p = (col, rows[0]), (col, rows[1]), (col, rows[2])
    wanted = {cid: caster_p, eids[0]: aim_p, eids[1]: behind_p}
    spares = _spare_tiles(walk, elev, [caster_p, aim_p, behind_p], len(allies) + len(eids))
    for k, u in enumerate(list(allies) + eids[2:]):
        if k < len(spares):
            wanted[u] = spares[k]
    if not _drive_to(rpc, rid, walk, elev, wanted):
        _dv, pos = _positions(rpc, rid)
        pytest.skip(f"placement incomplet (col {col}, rows {rows}): "
                    f"{ {u: pos.get(u) for u in wanted} } != { wanted }")
    _give_turn_back(rpc, rid, myplayer)

    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)
    nat = _native(rpc, rid, cid)
    gated = _engine(rpc, live_session, rid, cid, wt, predictor)
    orig = DTS._beam_count
    DTS._beam_count = lambda o, a, es, wbp=None, ebp=None: orig(o, a, es)   # geometrie PRE-#124
    try:
        free = _engine(rpc, live_session, rid, cid, wt, predictor)
    finally:
        DTS._beam_count = orig

    ctx = (f"colonne {col} rangees {rows} elevations {e} ; natif={nat} gate={gated} "
           f"rayon-droit={free}")
    assert nat["ability"] != 1092, (
        f"[a] le natif CASTE 1092 : la marche ne coupe pas le beam, scenario non exerce -- {ctx}")
    assert (gated["ability"], gated["target"]) == (nat["ability"], nat["target"]), (
        f"[a] decision GATEE != natif -- {ctx}")
    assert (free["ability"], free["target"]) != (nat["ability"], nat["target"]), (
        f"[a] le gate d'elevation n'est PAS portant : le rayon droit rend deja la decision native, "
        f"le test serait incapable d'echouer sur un port qui ignore `IsTileValidForList` -- {ctx}")
    assert free["ability"] == 1092, (
        f"[a] sans gate le moteur devrait caster 1092 (util 2 >= MIN_UTILITY) -- {ctx}")


# --------------------------------------------------------------- (b) ExcruciatingFrequencies


def test_excruciating_frequencies_decision_elevation_gate_live(live_session, rpc, build_runner):
    """(b) 1197 : derriere une falaise AVEUGLE, le natif NE caste PAS ExcruciatingFrequencies ; le
    generateur bespoke gate ne produit AUCUN candidat. Le meme generateur en RAYON DROIT en produit
    un (2 ennemis tuables) et le moteur caste 1197 -> le gate est PORTANT."""
    import engine.playbook.excruciating_frequencies as EF

    rid = build_runner("41171", ["--board", BOARD_B, "--p-units", "emperNoiseMarine",
                                 # profils DISTINCTS : a profils egaux le choix de cible de
                                 # l'attaque normale est un TIE tranche par la POSITION (axe
                                 # proxy, cf. test_playbook_live) et brouillerait le critere.
                                 "--a-units", "eldarRanger,astraBullgryn",
                                 "--hp-target", "600", "--hp-player", "90000"])["rid"]
    elev, walk = _board(rpc, rid)
    win = _find_blind_window(elev, walk)
    if win is None:
        pytest.skip(f"board {BOARD_B} n'offre pas de fenetre AVEUGLE")
    P, t1, t2, t3, nseen = win
    cid, myplayer, allies, eids = _roster(rpc, rid, "emperNoiseMarine")
    if len(eids) < 2:
        pytest.skip("moins de 2 ennemis vivants")
    wanted = {cid: P, eids[0]: t2, eids[1]: t3}
    spares = _spare_tiles(walk, elev, [P, t1, t2, t3], len(allies) + len(eids))
    for k, u in enumerate(list(allies) + eids[2:]):
        if k < len(spares):
            wanted[u] = spares[k]
    if not _drive_to(rpc, rid, walk, elev, wanted):
        _dv, pos = _positions(rpc, rid)
        pytest.skip(f"placement incomplet (P={P} t2={t2} t3={t3}): "
                    f"{ {u: pos.get(u) for u in wanted} } != { wanted }")
    _give_turn_back(rpc, rid, myplayer)

    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)
    nat = _native(rpc, rid, cid)
    gated = _engine(rpc, live_session, rid, cid, wt, predictor)
    orig = EF._line_tiles
    EF._line_tiles = lambda c, a, n, wbp=None, ebp=None: _straight_line(c, a, n)   # PRE-#124
    try:
        free = _engine(rpc, live_session, rid, cid, wt, predictor)
    finally:
        EF._line_tiles = orig

    # Niveau FEUILLE : le generateur bespoke lui-meme (le seul artefact que #124 change ici).
    from engine.ai import context as _ai_ctx
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    ectx = _ai_ctx.build(rpc, rid, dv, mbu, cid, wt, predictor)
    cands_gated = EF.excruciating_frequencies_candidates(ectx)
    EF._line_tiles = lambda c, a, n, wbp=None, ebp=None: _straight_line(c, a, n)
    try:
        cands_free = EF.excruciating_frequencies_candidates(ectx)
    finally:
        EF._line_tiles = orig

    ctx = (f"P={P}(e{elev[P]}) t1={t1}(e{elev[t1]}) t2={t2}(e{elev[t2]}) t3={t3}(e{elev[t3]}) ; "
           f"voisinage aveugle={nseen} tuiles ; natif={nat} gate={gated} rayon-droit={free}")
    assert nat["ability"] != 1197, (
        f"[b] le natif CASTE 1197 : la falaise n'aveugle pas la ligne, scenario non exerce -- {ctx}")
    assert cands_gated == [], (
        f"[b] le generateur GATE produit {cands_gated} alors que le natif refuse 1197 -- {ctx}")
    assert cands_free, (
        f"[b] le rayon droit ne produit AUCUN candidat 1197 : le gate n'est pas exerce, le test "
        f"serait incapable d'echouer sur un port qui ignore `IsTileValidForList` -- {ctx}")
    assert (gated["ability"], gated["target"]) == (nat["ability"], nat["target"]), (
        f"[b] decision GATEE != natif -- {ctx}")
    assert free["ability"] == 1197, (
        f"[b] sans gate le moteur devrait caster 1197 (2 ennemis derriere la falaise) -- {ctx}")
