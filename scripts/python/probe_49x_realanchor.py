#!/usr/bin/env python
"""Probe #49x : DISCRIMINATEUR FINAL Gauntlets(1000) — regle 'ancre reelle' vs rivales.

Regle candidate (decompile, IdunBattle.AI.Playbook.Loki.GauntletsOfUltramarPlaybook$$EvaluateNonComparable) :
  util(T) = | ring1(T)  UNION  disk2(TUILE REELLE du caster) |
   - ring1(T)     = ennemis adjacents a la position BALAYEE T (CasterTile@+0x168 = tuile du
                    CONTEXTE AbilityEntities, porte elevation |dElev|<2 d'IterateAdjacentTiles)
   - disk2(real)  = ennemis a dist hex <= 2 de la tuile REELLE de l'ENTITE caster
                    (Caster@+0x160 -> GetMainTile(entite) dans IdunBattle.Entities.Selectors.SurroundingTilesSelector$$Select ; slot 0x65 flags: emptyOrSteppable=OFF, Unobscured depuis la
                    tuile reelle, filtre IsTileValidForList = murs/walkable seulement)
Rivales a departager :
  R1 (port actuel)  : util(T) = ring1(T) seul
  R2 (ancien port)  : util(T) = arc(T) = ring1(T) + ring2(T)
Crafts sur ZONE PLATE (elev 1, rows 7-8 MC1_67) -> l'echappatoire 'Unobscured/epsilon' est
morte par construction (aucun mid ne peut bloquer sur du plat).

Phase A (MC1_67, 1v3) :
  craft-P : real=(2,7)  e=(0,7),(1,6),(6,8)   -> mienne: NON-VIDE exactement a (5,8) util=3 ;
            R1: vide partout ; R2: vide partout.
  craft-N : real=(4,5)  e=(0,7),(1,8),(2,8)   -> mienne: VIDE partout ; R1: vide partout ;
            R2: NON-VIDE a (1,7) (util 3) [+(2,6),(2,7)].
Phase B (C1_25, repro E1, 1v2, floor=min(3,2)=2) :
  real=(3,3) e=(3,1),(1,3) (les 2 a dist 2 du reel) -> regle complete : util=2 PARTOUT
  (disk2(real) T-independant) MAIS gate d'eligibilite par-position (ennemi a dist<=2 de T,
  SANS porte d'elevation ring-1) -> mesure 2026-07-21 : 17 positions util=2 + 6 VIDES,
  port-vs-natif 23/23. R1: vide partout ; R2: util varierait par T.
Phase O (MC1_67, Unobscured elevation sur le terme REEL) :
  craft-O : eA dist-2 du reel DERRIERE crete elev 4 -> EXCLU (vide partout) ;
  craft-O2 : eA deplace VISIBLE -> non-vide (5,2)=3 (controle positif).

Usage: python probe_49x_realanchor.py [--phase A|B|O|all]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "_fs49x_state.json"
MAXMOVE = 3          # Calgar movement=3 ; pas de driving > 3 par bond
MAXROUNDS = 40


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int, board: str, p_units: str | None, a_units: str | None) -> int:
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(STATE), "--board", board]
    if p_units:
        cmd += ["--p-units", p_units]
    if a_units:
        cmd += ["--a-units", a_units]
    STATE.unlink(missing_ok=True)   # jamais de state PERIME (build KO -> runner d'avant)
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0 or not STATE.exists():
        print(f"[49x] build KO (rc={proc.returncode}): "
              f"{(proc.stderr or proc.stdout or '')[-400:]}", file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def positions(sid, rid) -> dict:
    dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
    out = {}
    for u in (dv.get("units") or []):
        if u.get("alive") is False:
            continue
        p = u.get("pos") or {}
        if p.get("col") is not None:
            out[u["id"]] = (p["col"], p["row"])
    return out


def try_move(sid, rid, uid, dest) -> bool:
    _r(sid, "applyAction", {"runnerId": rid, "actions": [
        {"kind": "move", "unitId": uid, "to": {"col": dest[0], "row": dest[1]}}]}, 60)
    return positions(sid, rid).get(uid) == tuple(dest)


def endturn(sid, rid):
    _r(sid, "applyAction", {"runnerId": rid, "actions": [{"kind": "endturn"}]}, 60)


def refresh_turn(sid, rid, uid) -> bool:
    """endturn jusqu'a ce que ce soit le tour du JOUEUR de `uid` avec action dispo (3 joueurs :
    p1/p2/p3=environnement -> nombre d'endturns variable). Necessaire pour que le sweep
    ncEvaluate couvre le movable set (unite deja bougee ce tour = sweep reduit a l'origine)."""
    for _ in range(9):
        dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        cur = dv.get("currentPlayer")
        for u in (dv.get("units") or []):
            if u.get("id") == uid:
                if u.get("owner") == cur and u.get("hasAction"):
                    return True
                break
        endturn(sid, rid)
    print("[49x] refresh_turn: pas reussi a rendre la main au caster", file=sys.stderr)
    return False


def drive(sid, rid, plan: dict, tiles: list) -> bool:
    """Amene chaque unite de `plan` {uid: dest} a destination (moves legaux, cycles de tour)."""
    for rnd in range(MAXROUNDS):
        pos = positions(sid, rid)
        pending = {u: d for u, d in plan.items() if pos.get(u) != tuple(d)}
        if not pending:
            return True
        progressed = False
        occupied = set(pos.values())
        for uid, dest in pending.items():
            cur = pos.get(uid)
            if cur is None:
                print(f"[49x] drive: u{uid} introuvable/mort", file=sys.stderr)
                return False
            # candidats: dest d'abord, puis pas intermediaires qui rapprochent
            cands = [tuple(dest)] if hexgeo.distance(cur, dest) <= MAXMOVE else []
            steps = [t for t in tiles
                     if t not in occupied and t != cur
                     and 0 < hexgeo.distance(cur, t) <= MAXMOVE
                     and hexgeo.distance(t, dest) < hexgeo.distance(cur, dest)]
            steps.sort(key=lambda t: (hexgeo.distance(t, dest), hexgeo.distance(cur, t)))
            for t in (cands + steps)[:6]:
                if t in occupied and t != tuple(dest):
                    continue
                if try_move(sid, rid, uid, t):
                    occupied.discard(cur)
                    occupied.add(t)
                    progressed = True
                    break
        if not progressed:
            endturn(sid, rid)   # personne n'a pu bouger -> tour suivant (reset move)
    print("[49x] drive: MAXROUNDS atteint sans converger", file=sys.stderr)
    return False


def measure(sid, rid, uid, tag, expect: dict) -> bool:
    """ncEvaluate sweep + comparaison aux attentes {pos: util | None(=vide)}. 'autres' = vide."""
    res = _r(sid, "ncEvaluate", {"runnerId": rid, "unitId": uid, "abilityType": 1000,
                                 "sweep": True}, 120)
    if not isinstance(res, dict) or res.get("ok") is False:
        print(f"[49x] {tag}: ncEvaluate KO -> {json.dumps(res, default=str)[:300]}")
        return False
    rows = res.get("positions") or []
    nonempty = {}
    for p in rows:
        if not isinstance(p, dict) or p.get("pos") is None:
            continue
        key = tuple(p["pos"])
        if p.get("bucket") == "empty" or (p.get("util") is None and p.get("action") is None):
            continue
        nonempty[key] = p.get("util")
    print(f"[49x] {tag}: {len(rows)} positions balayees, non-vides = "
          + (json.dumps({str(k): v for k, v in sorted(nonempty.items())}) if nonempty else "{}"))
    ok = True
    for pos_, want in expect.items():
        got = nonempty.get(tuple(pos_))
        if want is None:
            if tuple(pos_) in nonempty:
                print(f"[49x]   FAIL {pos_}: attendu VIDE, obtenu util={got}")
                ok = False
        else:
            if got is None:
                print(f"[49x]   FAIL {pos_}: attendu util={want}, obtenu VIDE")
                ok = False
            elif abs(got - want) > 1e-6:
                print(f"[49x]   FAIL {pos_}: attendu util={want}, obtenu {got}")
                ok = False
    extra = [k for k in nonempty if k not in {tuple(p) for p, w in expect.items() if w is not None}]
    if expect.get("__others_empty__", True) and extra:
        print(f"[49x]   NOTE positions non-vides hors attentes: {extra}")
    print(f"[49x] {tag}: {'PASS' if ok else 'FAIL'}")
    return ok


def board_tiles(board: str) -> list:
    b = json.loads((ROOT / "data" / "boards" / "global" / f"{board}.json").read_text())["board"]
    return [(c, r) for c in range(b["Width"]) for r in range(b["Height"])]


def phase_a(sid) -> bool:
    rid = build(31337, "MC1_67", "ultraCalgar", "bloodIntercessor,adeptRetributor,spaceHound")
    print(f"[49x] phase A runner={rid}")
    tiles = board_tiles("MC1_67")
    okA = True
    try:
        pos = positions(sid, rid)
        print(f"[49x] spawns: {pos}")
        ids = sorted(pos)
        calgar = None
        dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 60)
        teams = {}
        for u in (dv.get("units") or []):
            teams[u["id"]] = u.get("team")
            for a in (u.get("abilities") or []):
                if a.get("id") == 1000:
                    calgar = u["id"]
        enemies = [i for i in ids if calgar is not None and teams.get(i) != teams.get(calgar)]
        print(f"[49x] calgar=u{calgar} enemies={enemies}")
        if calgar is None or len(enemies) != 3:
            print("[49x] phase A: roster inattendu", file=sys.stderr)
            return False
        # affectation ennemis -> cibles craft-P par distance gloutonne
        targets = [(0, 7), (1, 6), (6, 8)]
        assign = {}
        left = set(enemies)
        for tgt in sorted(targets, key=lambda t: min(hexgeo.distance(pos[e], t) for e in left)):
            e = min(left, key=lambda e_: hexgeo.distance(pos[e_], tgt))
            assign[e] = tgt
            left.discard(e)
        plan = dict(assign)
        plan[calgar] = (2, 7)
        print(f"[49x] craft-P plan: {plan}")
        if not drive(sid, rid, plan, tiles):
            return False
        if not refresh_turn(sid, rid, calgar):
            return False
        print(f"[49x] craft-P positions: {positions(sid, rid)}")
        okA &= measure(sid, rid, calgar, "CRAFT-P (real=(2,7), e=(0,7),(1,6),(6,8))",
                       {(5, 8): 3.0, (2, 7): None, (4, 8): None, (3, 7): None, (3, 8): None})
        # craft-N : (0,7) reste ; (1,6)->(1,8) ; (6,8)->(2,8) ; calgar->(4,5)
        by_tgt = {tuple(t): e for e, t in assign.items()}
        planN = {calgar: (4, 5), by_tgt[(1, 6)]: (1, 8), by_tgt[(6, 8)]: (2, 8)}
        print(f"[49x] craft-N plan: {planN}")
        if not drive(sid, rid, planN, tiles):
            return False
        if not refresh_turn(sid, rid, calgar):
            return False
        print(f"[49x] craft-N positions: {positions(sid, rid)}")
        okA &= measure(sid, rid, calgar, "CRAFT-N (real=(4,5), e=(0,7),(1,8),(2,8))",
                       {(1, 7): None, (2, 6): None, (2, 7): None, (4, 5): None})
        return okA
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            print(f"[49x] runner {rid} dispose")
        except Exception:
            pass


def _port_predict(T, origin, epos, elev, floor):
    """Prediction du PORT (engine.battle_query) pour une position balayee T : util ou None(=vide)."""
    from engine import battle_query as bq
    if bq.eligible_targets_count(T, epos, elev) == 0:
        return None
    ring1 = {(p[0], p[1]) for p in epos if bq.is_adjacent(T, p, elev)}
    u = float(len(ring1 | bq.surrounding_enemies(origin, epos, elev)))
    return u if u >= floor else None


def measure_vs_port(sid, rid, uid, tag, origin, epos, elev, floor) -> bool:
    """ncEvaluate sweep : confronte CHAQUE position native au port (util exacte / vide)."""
    res = _r(sid, "ncEvaluate", {"runnerId": rid, "unitId": uid, "abilityType": 1000,
                                 "sweep": True}, 120)
    rows = res.get("positions") or []
    mism = []
    seen = 0
    for p in rows:
        if not isinstance(p, dict) or p.get("pos") is None:
            continue
        seen += 1
        T = tuple(p["pos"])
        native = None if p.get("bucket") == "empty" else p.get("util")
        port = _port_predict(T, origin, epos, elev, floor)
        if native != port:
            mism.append((T, native, port))
    ne = {}
    for p2 in rows:
        if isinstance(p2, dict) and p2.get("pos") is not None and p2.get("bucket") != "empty":
            ne[tuple(p2["pos"])] = p2.get("util")
    print(f"[49x] {tag}: natif non-vides = {sorted(ne.items()) if ne else 'AUCUNE'}")
    print(f"[49x] {tag}: {seen} positions, mismatches port-vs-natif = {mism if mism else 'AUCUN'}")
    print(f"[49x] {tag}: {'PASS' if seen and not mism else 'FAIL'}")
    return bool(seen and not mism)


def phase_o(sid) -> bool:
    """Craft-O : Unobscured (elevation) sur le terme REEL, exercice POSITIF + controle.
    real=(2,2) MC1_67 ; eA=(1,4) dist-2 OBSCURED (mids (1,3)/(2,3) elev 4 vs from elev 2) ;
    eB=(2,1) dist-1 ; eC=(6,2) loin, T=(5,2) adjacent a eC.
      O  : mienne util(T)=|{eC} U {eB}|=2 <3 -> VIDE partout ; sans-obscured: {eA,eB} -> 3 NON-VIDE.
      O2 : eA -> (3,3) (dist-2 VISIBLE) -> mienne: NON-VIDE (T adj eC, util 3) — controle positif."""
    rid = build(31337, "MC1_67", "ultraCalgar", "bloodIntercessor,adeptRetributor,spaceHound")
    print(f"[49x] phase O runner={rid}")
    tiles = board_tiles("MC1_67")
    elev = {}
    b = json.loads((ROOT / "data" / "boards" / "global" / "MC1_67.json").read_text())["board"]
    for c in range(b["Width"]):
        for r_ in range(b["Height"]):
            elev[(c, r_)] = b["Tiles"][c]["Tile"][r_]["Elevation"]
    ok = True
    try:
        pos = positions(sid, rid)
        print(f"[49x] spawns: {pos}")
        dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 60)
        calgar, teams = None, {}
        for u in (dv.get("units") or []):
            teams[u["id"]] = u.get("team")
            for a in (u.get("abilities") or []):
                if a.get("id") == 1000:
                    calgar = u["id"]
        enemies = [i for i in pos if calgar is not None and teams.get(i) != teams.get(calgar)]
        if calgar is None or len(enemies) != 3:
            print("[49x] phase O: roster inattendu", file=sys.stderr)
            return False
        targets = [(1, 4), (2, 1), (6, 2)]
        assign = {}
        left = set(enemies)
        for tgt in sorted(targets, key=lambda t: min(hexgeo.distance(pos[e], t) for e in left)):
            e = min(left, key=lambda e_: hexgeo.distance(pos[e_], tgt))
            assign[e] = tgt
            left.discard(e)
        plan = dict(assign)
        plan[calgar] = (2, 2)
        print(f"[49x] craft-O plan: {plan}")
        if not drive(sid, rid, plan, tiles):
            return False
        if not refresh_turn(sid, rid, calgar):
            return False
        print(f"[49x] craft-O positions: {positions(sid, rid)}")
        epos = [(1, 4), (2, 1), (6, 2)]
        ok &= measure_vs_port(sid, rid, calgar,
                              "CRAFT-O (eA=(1,4) OBSCURED via crete elev4)",
                              (2, 2), epos, elev, 3)
        # O2 : eA -> (3,3) VISIBLE (controle positif : le floor est atteignable dans ce layout)
        by_tgt = {tuple(t): e for e, t in assign.items()}
        if not drive(sid, rid, {by_tgt[(1, 4)]: (3, 3)}, tiles):
            return False
        if not refresh_turn(sid, rid, calgar):
            return False
        print(f"[49x] craft-O2 positions: {positions(sid, rid)}")
        epos2 = [(3, 3), (2, 1), (6, 2)]
        ok &= measure_vs_port(sid, rid, calgar,
                              "CRAFT-O2 (eA=(3,3) VISIBLE, controle positif)",
                              (2, 2), epos2, elev, 3)
        return ok
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            print(f"[49x] runner {rid} dispose")
        except Exception:
            pass


def phase_b(sid) -> bool:
    rid = build(777, "C1_25", "ultraCalgar", "bloodIntercessor,adeptRetributor")
    print(f"[49x] phase B runner={rid}")
    tiles = board_tiles("C1_25")
    try:
        pos = positions(sid, rid)
        print(f"[49x] spawns: {pos}")
        dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 60)
        calgar = None
        teams = {}
        for u in (dv.get("units") or []):
            teams[u["id"]] = u.get("team")
            for a in (u.get("abilities") or []):
                if a.get("id") == 1000:
                    calgar = u["id"]
        enemies = [i for i in pos if calgar is not None and teams.get(i) != teams.get(calgar)]
        print(f"[49x] calgar=u{calgar} enemies={enemies}")
        if calgar is None or len(enemies) != 2:
            print("[49x] phase B: roster inattendu", file=sys.stderr)
            return False
        targets = [(3, 1), (1, 3)]
        e0, e1 = enemies
        # affectation par cout total minimal
        c1 = hexgeo.distance(pos[e0], targets[0]) + hexgeo.distance(pos[e1], targets[1])
        c2 = hexgeo.distance(pos[e0], targets[1]) + hexgeo.distance(pos[e1], targets[0])
        assign = {e0: targets[0], e1: targets[1]} if c1 <= c2 else {e0: targets[1], e1: targets[0]}
        plan = dict(assign)
        plan[calgar] = (3, 3)
        print(f"[49x] E1-repro plan: {plan}")
        if not drive(sid, rid, plan, tiles):
            return False
        if not refresh_turn(sid, rid, calgar):
            return False
        print(f"[49x] E1-repro positions: {positions(sid, rid)}")
        # regle COMPLETE (case-49x) : util(T) = |ring1(T) U disque2(reel)| = 2 partout ici,
        # MAIS gate d'eligibilite par-position (ennemi a dist<=2 de T requis) -> les positions
        # loin des 2 ennemis sont VIDES. Comparaison port-vs-natif PAR POSITION (mesure de
        # reference 2026-07-21 : 23 positions, 17 util=2 / 6 vides, 23/23 avec le port).
        elevB = {}
        bB = json.loads((ROOT / "data" / "boards" / "global" / "C1_25.json").read_text())["board"]
        for cB in range(bB["Width"]):
            for rB in range(bB["Height"]):
                elevB[(cB, rB)] = bB["Tiles"][cB]["Tile"][rB]["Elevation"]
        ok = True
        for attempt in range(4):
            ok = measure_vs_port(sid, rid, calgar, f"E1-REPRO (tentative {attempt})",
                                 (3, 3), [(3, 1), (1, 3)], elevB, 2)
            res = _r(sid, "ncEvaluate", {"runnerId": rid, "unitId": calgar,
                                         "abilityType": 1000, "sweep": True}, 120)
            if len(res.get("positions") or []) > 1:
                break
            endturn(sid, rid)
            if not refresh_turn(sid, rid, calgar):
                break
        return bool(ok)
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            print(f"[49x] runner {rid} dispose")
        except Exception:
            pass


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="all", choices=["A", "B", "O", "all"])
    args = ap.parse_args(argv)
    sid = _resolve_session()
    print(f"[49x] session {sid}")
    ok = True
    if args.phase in ("A", "all"):
        ok &= phase_a(sid)
    if args.phase in ("B", "all"):
        ok &= phase_b(sid)
    if args.phase in ("O", "all"):
        ok &= phase_o(sid)
    print(f"[49x] === VERDICT GLOBAL: {'PASS' if ok else 'FAIL'} ===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
