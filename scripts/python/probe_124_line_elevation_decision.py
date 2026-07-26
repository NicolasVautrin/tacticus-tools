#!/usr/bin/env python
"""Probe #124 -- le gate d'ELEVATION de la ligne hex sur les DEUX faces DECISION.

MESURE (le test `tests/engine/test_line_elevation_gate_decision_live.py` GARDE) : sur un board dont
la ligne de tir franchit une marche d'elevation >= 2, la face DECISION offline rend-elle la MEME
decision que l'IA NATIVE (`aiDryRunAllUnits` -> `CalculateNextActionForUnit`) ?

Pour chaque item on imprime TROIS decisions sur le MEME etat : natif, moteur GATE (post-#124),
moteur SANS gate (monkeypatch de la feuille = comportement pre-#124). Le scenario est
DISCRIMINANT ssi `sans gate != natif` ; il est CONFORME ssi `gate == natif`.

  (a) DarkTalonStrike (1092, `darkaAzrael`) -- `DarkTalonStrikePlaybook$$EvaluateNonComparable`.
      Board `C4_02`, colonne 5 rangees [5,6,7,8] elevations [1,1,3,3] : caster (5,5), ennemi (5,6)
      (= l'aim), ennemi (5,7) DERRIERE la marche, le reste parque loin.
        rayon droit SANS gate  -> util 2 (>= MIN_UTILITY 2) -> le port CASTE 1092 ;
        rayon GATE (1/1)       -> util 1 (< 2)              -> pas de NC -> fallback Comparable.

  (b) ExcruciatingFrequencies (1197, `emperNoiseMarine`) -- generateur bespoke
      `excruciating_frequencies_candidates`. Board `C4_41` (63 tuiles, UNE seule composante de
      mouvement -> tout est placable) : on derive LIVE une fenetre AVEUGLE (P, t1, t2, t3) telle que
        * le rayon droit `P -> t1 -> t2 -> t3` franchit une marche >= 2 entre t1 et t2 ;
        * AUCUNE position du voisinage-mouvement de P (BFS gate, profondeur = portee de deplacement)
          ne permet une ligne GATEE contenant t2 ou t3.
      Sans cette derniere condition le natif CONTOURNE la marche par le flanc et le scenario cesse
      de discriminer (mesure C4_02 : depuis (3,6) sa ligne `[(4,6),(5,7),(6,7)]` PASSE le gate).

Un runner DEDIE par item, dispose aussitot. ASCII only.
Usage : python probe_124_line_elevation_decision.py    (exit 0 = OK)
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine import weights as W  # noqa: E402
from engine.playbook import scene as _scene  # noqa: E402
from engine_validate import engine_decide  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
BOARD_A = "C4_02"          # marche 1->3 en colonne 5 (item a)
BOARD_B = "C3_59"          # falaise 0->4 AVEUGLE a 5 mouvements, board connexe (item b)
A_UNITS = "eldarRanger,eldarRanger,eldarRanger,eldarRanger,eldarRanger"
BLIND_DEPTH = 5            # profondeur du voisinage-mouvement teste pour l'aveuglement


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


# --------------------------------------------------------------------------- board / placement


def _board(sid, rid):
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    tiles = bg.get("tiles") or []
    elev = {(t["col"], t["row"]): t.get("elevation") for t in tiles}
    walk = {(t["col"], t["row"]): bool(t.get("walkable")) for t in tiles}
    tid = {(t["col"], t["row"]): t.get("id") for t in tiles}
    return elev, walk, tid


def _move_ring(p, walk, elev):
    """Voisins de `p` atteignables par MOUVEMENT : walkable + porte `|Delta elev| < 2`
    (`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`) -- MEME porte
    que la ligne, donc un palier a +2 est inaccessible A PIED comme A LA LIGNE."""
    out = []
    if elev.get(p) is None:
        return out
    for n in hexgeo.neighbors(p[0], p[1]):
        if walk.get(n) and elev.get(n) is not None and abs(elev[n] - elev[p]) < 2:
            out.append(n)
    return out


def _gated_line(P, aim, n, walk, elev):
    """Mirror OFFLINE de `BattleQuery$$GetTilesBehind(P, aim, checkWalkable=1, updateRef=1, n)`
    (sert au CHOIX de scenario ; le port teste, lui, vit dans engine.battle_query)."""
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
    ox, _oy, oz = hexgeo.to_cube(*P)
    ax, _ay, az = hexgeo.to_cube(*aim)
    dx, dz = ax - ox, az - oz
    if dx == 0 and dz == 0:
        return []
    return [hexgeo.from_cube(ox + dx * k, oz + dz * k) for k in range(1, n + 1)]


def _find_blind_window(elev, walk, n_tiles=3, depth=BLIND_DEPTH):
    """(P, t1, t2, t3) : le rayon DROIT de `n_tiles` depuis P franchit une marche >= 2 entre t1 et
    t2 (t2, t3 sur le meme palier) ET aucune position a <= `depth` mouvements de P ne permet une
    ligne GATEE contenant t2 ou t3."""
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
            blind = True
            for Q in seen:
                for aim in hexgeo.neighbors(Q[0], Q[1]):
                    if aim not in tiles:
                        continue
                    ln = _gated_line(Q, aim, n_tiles, walk, elev)
                    if t2 in ln or t3 in ln:
                        blind = False
                        break
                if not blind:
                    break
            if blind:
                return P, t1, t2, t3, len(seen)
    return None


def _find_break_window(elev, walk, need=4):
    """Colonne + `need` rangees consecutives walkables : marche `w0 -> w1` < 2 (caster -> aim) puis
    marche `w1 -> w2` >= 2 (IMMEDIATEMENT apres la tuile visee)."""
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


def _positions(sid, rid):
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    return dv, {u["id"]: (u["pos"]["col"], u["pos"]["row"])
                for u in (dv.get("units") or []) if u.get("alive") and u.get("pos")}


def _gated_path(src, dst, walk, elev):
    """Chemin BFS sur le graphe de MOUVEMENT natif. La ligne hex droite ne suffit PAS des que le
    trajet doit contourner une falaise -- c'est ce qui fait echouer un placement sur un relief."""
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


def _drive_to(sid, rid, walk, elev, wanted: dict, rounds: int = 14) -> bool:
    """Amene chaque unite de `wanted` ({unitId: (col,row)}) sur sa tuile : waypoints pris sur le
    CHEMIN de mouvement natif (le plus loin d'abord), `endturn` pour re-armer le deplacement."""
    for _ in range(rounds):
        _dv, pos = _positions(sid, rid)
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
                r = _r(sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": uid, "to": {"col": p[0], "row": p[1]}}}, 60)
                if _ok(r) and (r.get("actions") or [{}])[0].get("mutated"):
                    occupied.discard(cur)
                    occupied.add(p)
                    break
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    _dv, pos = _positions(sid, rid)
    return all(pos.get(u) == dest for u, dest in wanted.items())


def _spare_tiles(walk, elev, keep_away, n, min_sep=3):
    """`n` tuiles walkables LOIN des tuiles de scenario et MUTUELLEMENT eloignees (>= `min_sep`) --
    des ennemis parques alignes formeraient une ligne parasite."""
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


def _give_turn_back(sid, rid, myplayer):
    for _ in range(3):
        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        if dv.get("currentPlayer") == myplayer:
            return dv
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)


# --------------------------------------------------------------------------- confrontation


def _native(sid, rid, cid):
    dry = _r(sid, "aiDryRunAllUnits", {"runnerId": rid}, 150)
    nat = next((u for u in (dry.get("units") or []) if u.get("unitId") == cid), None)
    ab = tgt = to = None
    for m in ((nat or {}).get("proposed") or []):
        if m.get("cls") == "ActiveAbilityMessage" and ab is None:
            ab, tgt = m.get("abilityType"), m.get("targetId")
        if m.get("cls") == "MoveUnitMessage" and to is None:
            p = m.get("to") or {}
            to = (p.get("col"), p.get("row")) if p.get("col") is not None else None
    return {"ability": ab, "target": tgt, "to": to}


def _engine(sid, rid, cid, wt, predictor):
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    if predictor is not None:
        _scene.refresh_shields(predictor, lambda m, b, t: _r(sid, m, b, t), rid)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    e = engine_decide(sid, rid, dv, mbu, cid, wt, predictor)
    return {"ability": e.get("ability") if e.get("kind") == "ability" else None,
            "target": e.get("target"), "to": e.get("to"), "kind": e.get("kind")}


def _cmp(a, b):
    return a.get("ability") == b.get("ability") and a.get("target") == b.get("target")


def _report(label, nat, gated, free, fails):
    print(f"  [{label}] natif   ab={nat['ability']} tgt={nat['target']} to={nat['to']}")
    print(f"  [{label}] gate    ab={gated['ability']} tgt={gated['target']} to={gated['to']} "
          f"kind={gated['kind']}")
    print(f"  [{label}] no-gate ab={free['ability']} tgt={free['target']} to={free['to']} "
          f"kind={free['kind']}")
    conforme, discrim = _cmp(gated, nat), not _cmp(free, nat)
    print(f"  [{label}] conforme(gate==natif)={'OK' if conforme else 'X'} "
          f"discriminant(no-gate!=natif)={'OK' if discrim else 'X'}")
    if not conforme:
        fails.append(f"{label}: moteur GATE {gated} != natif {nat}")
    if not discrim:
        fails.append(f"{label}: scenario NON DISCRIMINANT (sans gate le moteur repond deja "
                     f"comme le natif) -- geometrie a re-crafter")


# --------------------------------------------------------------------------- items


def item_dark_talon(sid, rid, wt, predictor, elev, walk, tid, cid, allies, eids, fails):
    win = _find_break_window(elev, walk, 4)
    if win is None:
        fails.append(f"(a) board {BOARD_A} sans fenetre de marche")
        return
    col, rows, e = win
    print(f"(a) DarkTalonStrike (1092) -- colonne {col} rangees {rows} elevations {e}")
    caster_p, aim_p, behind_p = (col, rows[0]), (col, rows[1]), (col, rows[2])
    wanted = {cid: caster_p, eids[0]: aim_p, eids[1]: behind_p}
    for k, u in enumerate(list(allies) + eids[2:]):
        spares = _spare_tiles(walk, elev, [caster_p, aim_p, behind_p], len(allies) + len(eids))
        if k < len(spares):
            wanted[u] = spares[k]
    if not _drive_to(sid, rid, walk, elev, wanted):
        _dv, pos = _positions(sid, rid)
        fails.append(f"(a) placement incomplet: {[(u, pos.get(u), d) for u, d in wanted.items()]}")
        return
    _give_turn_back(sid, rid, _myplayer(sid, rid, cid))
    at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": 1092}, 90)
    ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
               if a.get("abilityId") == 1092), {})
    print("      fromHere(1092) =", [((x.get("tile") or {}).get("col"),
                                      (x.get("tile") or {}).get("row"))
                                     for x in (ab.get("fromHere") or [])])

    import engine.playbook.noncomparable.dark_talon_strike as DTS
    nat = _native(sid, rid, cid)
    gated = _engine(sid, rid, cid, wt, predictor)
    orig = DTS._beam_count
    DTS._beam_count = lambda o, a, es, wbp=None, ebp=None: orig(o, a, es)   # pre-#124 (sans gate)
    try:
        free = _engine(sid, rid, cid, wt, predictor)
    finally:
        DTS._beam_count = orig
    _report("a/DarkTalonStrike", nat, gated, free, fails)


def item_excruciating(sid, rid, wt, predictor, elev, walk, tid, cid, allies, eids, fails):
    win = _find_blind_window(elev, walk)
    if win is None:
        fails.append(f"(b) board {BOARD_B} sans fenetre AVEUGLE")
        return
    P, t1, t2, t3, nseen = win
    print(f"(b) ExcruciatingFrequencies (1197) -- P={P}(e{elev[P]}) t1={t1}(e{elev[t1]}) "
          f"t2={t2}(e{elev[t2]}) t3={t3}(e{elev[t3]}) ; voisinage-mouvement aveugle = {nseen} tuiles")
    wanted = {cid: P, eids[0]: t2, eids[1]: t3}
    spares = _spare_tiles(walk, elev, [P, t1, t2, t3], len(allies) + len(eids))
    for k, u in enumerate(list(allies) + eids[2:]):
        if k < len(spares):
            wanted[u] = spares[k]
    if not _drive_to(sid, rid, walk, elev, wanted):
        _dv, pos = _positions(sid, rid)
        fails.append(f"(b) placement incomplet: {[(u, pos.get(u), d) for u, d in wanted.items()]}")
        return
    _give_turn_back(sid, rid, _myplayer(sid, rid, cid))

    import engine.playbook.excruciating_frequencies as EF
    nat = _native(sid, rid, cid)
    gated = _engine(sid, rid, cid, wt, predictor)
    orig = EF._line_tiles
    EF._line_tiles = lambda c, a, n, wbp=None, ebp=None: _straight_line(c, a, n)  # pre-#124
    try:
        free = _engine(sid, rid, cid, wt, predictor)
    finally:
        EF._line_tiles = orig
    _diag_ef(sid, rid, cid, wt, predictor, EF, orig)
    _report("b/ExcruciatingFrequencies", nat, gated, free, fails)


def _diag_ef(sid, rid, cid, wt, predictor, EF, gated_line):
    """Decomposition PAR ETAGE du generateur bespoke 1197 : candidats gate / rayon droit, et les
    couples (position, aim) ou les deux lignes different."""
    from engine.ai import context as _ai_ctx
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    ctx = _ai_ctx.build(lambda m, b, t: _r(sid, m, b, t), rid, dv, mbu, cid, wt, predictor)
    free_line = (lambda c, a, n, wbp=None, ebp=None: _straight_line(c, a, n))
    for tag, fn in (("gate", gated_line), ("droit", free_line)):
        EF._line_tiles = fn
        try:
            print(f"      candidats 1197 [{tag}] =", EF.excruciating_frequencies_candidates(ctx))
        finally:
            EF._line_tiles = gated_line
    # utilite du concurrent (attaque NORMALE) : c'est elle qui decide si le candidat 1197 sort.
    from engine.ai.action_generators import ComparableAbilityGenerator
    best = ComparableAbilityGenerator()._best_attack(ctx)
    if best:
        print(f"      meilleure ATTAQUE comparable : u={round(best[0], 3)} full={round(best[1], 3)} "
              f"tgt={best[2]} ab={best[3]} to={best[4]}")
    n = EF._n_tiles()
    epos = set(ctx.epos or [])
    ebp = {}
    for e in (ctx.enemies or []):
        p = e.get("pos")
        if p and p.get("col") is not None:
            ebp[(p["col"], p["row"])] = e.get("id")
    for Pp in (ctx.reach_nc or []):
        for aim in hexgeo.neighbors(Pp[0], Pp[1]):
            if ctx.tile_id_by_pos.get(aim) is None:
                continue
            lg = gated_line(Pp, aim, n, ctx.walkable_by_pos, ctx.elev_by_pos)
            lf = free_line(Pp, aim, n)
            eg = [ebp[t] for t in lg if t in epos and t in ebp]
            ef_ = [ebp[t] for t in lf if t in epos and t in ebp]
            if eg == ef_:
                continue
            sg = EF._score(ctx, Pp, eg) if eg else None
            sf = EF._score(ctx, Pp, ef_) if ef_ else None
            print(f"      DIFF P={Pp} aim={aim} gate={lg}->{eg} score={sg} | "
                  f"droit={lf}->{ef_} score={sf}")


def _myplayer(sid, rid, cid):
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    u = next((x for x in (dv.get("units") or []) if x.get("id") == cid), {})
    return u.get("owner")


# --------------------------------------------------------------------------- main


def _build(state, board, p_units, a_units, hp_target="90000", cap_wait_s=900, poll_s=20):
    """Build avec ATTENTE du cap MAX_RUNNERS (session partagee entre agents : un refus de cap
    n'est pas un echec du scenario -- cf. runner.md §3)."""
    args = [sys.executable, "rl_duel.py", "build", "--seed", "41171",
            "--state-file", str(state), "--board", board,
            "--p-units", p_units, "--a-units", a_units,
            "--hp-target", hp_target, "--hp-player", "90000"]
    waited = 0.0
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(args, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return json.loads(state.read_text())["runnerId"]
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out or waited >= cap_wait_s:
            print("BUILD KO:", out[-500:])
            return None
        print(f"  cap sature, attente {poll_s}s ({waited:.0f}/{cap_wait_s})")
        time.sleep(poll_s)
        waited += poll_s


def _run_item(sid, fn, board, p_units, a_units, caster_vis, min_enemies, fails,
              hp_target="90000"):
    state = ROOT / "logs" / "runners" / f"probe124-{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    rid = _build(state, board, p_units, a_units, hp_target)
    if rid is None:
        fails.append(f"{caster_vis}: build KO")
        return
    print("runner", rid, "board", board)
    try:
        wt = W.load()
        predictor = _scene.build_predictor(lambda m, b, t: _r(sid, m, b, t), rid)
        elev, walk, tid = _board(sid, rid)
        dv, _pos = _positions(sid, rid)
        mine = [u for u in (dv.get("units") or []) if u.get("ctrl") and u.get("alive")]
        cid = next((u["id"] for u in mine if u.get("visualId") == caster_vis), None)
        myplayer = next((u.get("owner") for u in mine), None)
        allies = [u["id"] for u in mine if u.get("id") != cid]
        eids = [u["id"] for u in (dv.get("units") or [])
                if u.get("owner") != myplayer and u.get("alive")]
        print("caster", cid, "allies", allies, "ennemis", eids)
        if cid is None or len(eids) < min_enemies:
            fails.append(f"{caster_vis}: roster incomplet (caster={cid} ennemis={eids})")
            return
        fn(sid, rid, wt, predictor, elev, walk, tid, cid, allies, eids, fails)
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        try:
            state.unlink()
        except Exception:
            pass


def main() -> int:
    import os
    only = os.environ.get("ITEM", "")           # "a" / "b" / vide = les deux
    sid = _resolve_session()
    print("session", sid)
    fails: list = []
    if only in ("", "a"):
        _run_item(sid, item_dark_talon, BOARD_A, "darkaAzrael", A_UNITS, "darkaAzrael", 4, fails)
    if only in ("", "b"):
        # Deux ennemis de PROFILS DISTINCTS (Ranger fragile / Bullgryn tanky) : a profils EGAUX le
        # choix de cible de l'attaque normale est un TIE que le moteur et le natif tranchent par
        # des positions differentes (axe POSITIONNEMENT, plancher 45 % -- sans rapport avec #124).
        _run_item(sid, item_excruciating, BOARD_B, "emperNoiseMarine",
                  os.environ.get("B_AUNITS", "eldarRanger,astraBullgryn"),
                  "emperNoiseMarine", 2, fails, hp_target="600")
    print()
    if fails:
        print("FAILS:")
        for f in fails:
            print(" -", f)
        return 1
    print("OK -- les deux items sont CONFORMES et DISCRIMINANTS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
