"""Harnais de validation DEV — pathfinding fidèle (engine/entities/pathfinding)
vs ORACLE live `aiMovableTiles` (= GetMovableTilesFor natif).

Approche A (capture live) : on capte le graphe de board une fois (`boardGraph`),
les positions/teams (`decisionView`), puis pour CHAQUE unité contrôlée on
reproduit son set de tuiles atteignables avec le flood-fill Python et on le
compare au set natif (`aiMovableTiles.units[].tiles`).

La PORTÉE de chaque unité est INFÉRÉE du natif (profondeur BFS max parmi les
tuiles natives) → on isole la correctness du MODÈLE de reachabilité (adjacence +
walkable + élévation≤1 + occupant + BFS par niveaux) du calcul de portée
(MovementRangeWithAppliedBonus, porté séparément). Match attendu = exact pour les
unités WALK ; les unités FLYING (FlyPathfinder, ignore élévation/blocage) sont des
exceptions connues tant que FlyPathfinder n'est pas porté.

On teste les 3 modes d'adjacence (native / native_sym / evenq) et on rapporte
lequel reproduit le mieux le natif.

Usage : python pathfind_validate.py [--seed 777] [--runner N] [--adjacency MODE]
Pré-requis : session Frida warmée (autoBootExtraire) — cf. CLAUDE.md.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import rl_collect_batch as R
from engine.entities.pathfinding.board import Board
from engine.entities.pathfinding.walk_pathfinder import get_movable_positions, get_reachable_levels

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "logs" / "runners" / "duel_state.json"
MODES = ["native", "native_sym", "evenq"]


def _res(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def rpc(sid, method, body=None, timeout=60):
    return _res(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def validate_unit(board, unit, occupants_by_team, team, move_range):
    """Compare le flood-fill Python (WalkPathfinder) au set natif pour une unité,
    à sa PORTÉE RÉELLE `move_range` (stat Movement de combatSnapshot). `team` =
    team de l'unité (ABSENT de aiMovableTiles.units → via decisionView).

    Détecte les unités NON-WALK : si le natif atteint des tuiles HORS de notre
    reachable WALK illimité, l'unité utilise un autre pathfinder (Fly/Teleport,
    ex. TeleportStrike) → le modèle Walk ne s'applique pas (exception attendue,
    pas un bug)."""
    pos = unit["pos"]
    start = board.id_at(pos["col"], pos["row"])
    if start is None:
        return {"ok": False, "err": f"start tile ({pos['col']},{pos['row']}) absente du board"}
    native = set()
    for t in unit.get("tiles", []):
        tid = board.id_at(t["col"], t["row"])
        if tid is not None:
            native.add(tid)
    if not native:
        return {"ok": True, "exact": True, "nNative": 0, "range": move_range,
                "missing": [], "extra": [], "nonWalk": False}

    occ = dict(occupants_by_team)
    occ.pop(start, None)

    # détection non-Walk : le natif atteint-il des tuiles PLUS LOIN que move_range
    # pas de marche ? (le board est connexe → "reachable illimité" ne discrimine pas ;
    # le vrai signal = portée effective >> stat Movement = Fly/Teleport ou range-bonus).
    levels = get_reachable_levels(board, start, occ, team, max_depth=None)
    max_native_lvl = max((levels.get(t, 999) for t in native), default=0)
    beyond = sorted(board.coord(t) for t in native if levels.get(t, 999) > move_range)
    non_walk = max_native_lvl > move_range

    _, pred = get_movable_positions(board, start, move_range, occ, team)
    missing = sorted(board.coord(t) for t in (native - pred))   # natif a, nous non
    extra = sorted(board.coord(t) for t in (pred - native))     # nous a, natif non
    return {
        "ok": True,
        "exact": not missing and not extra,
        "range": move_range,
        "nNative": len(native),
        "nPred": len(pred),
        "missing": missing,
        "extra": extra,
        "nonWalk": non_walk,
        "beyond": beyond,
        "maxNativeLvl": max_native_lvl,
    }


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--runner", type=int, default=None,
                    help="runnerId existant (sinon build via rl_duel)")
    ap.add_argument("--adjacency", choices=MODES, default=None,
                    help="ne tester qu'un mode (défaut : les 3)")
    a = ap.parse_args(argv)

    sid = R._resolve_session()
    if a.runner is not None:
        rid = a.runner
    else:
        print(f"[pathfind] session {sid} — build seed {a.seed}")
        subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", str(a.seed)],
                       cwd=str(Path(__file__).parent), check=True)
        st = json.loads(STATE.read_text())
        rid = st["runnerId"]
    print(f"[pathfind] session {sid} — runner {rid}")

    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    if not bg.get("ok"):
        print("boardGraph FAIL:", bg.get("error")); return 1
    tiles = bg["tiles"]
    amt = rpc(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    if not amt.get("ok"):
        print("aiMovableTiles FAIL:", amt.get("error")); return 1
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 90)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 40)
    # portée RÉELLE = stat Movement (combatSnapshot, keyé par entityId == unitId).
    move_by_id = {}
    for u in (snap.get("units") or []):
        uid = u.get("entityId")
        st = u.get("stats") or {}
        if uid is not None and st.get("movement") is not None:
            move_by_id[uid] = st["movement"]

    # team par unitId (aiMovableTiles.units N'A PAS de champ team → decisionView).
    team_by_id = {u["id"]: u.get("team") for u in (dv.get("units") or [])}
    # occupants : tile_id -> team de l'occupant. Source = boardGraph.occupantUnitId
    # (lu via UnitFoot → couvre les EMPREINTES MULTI-HEX, pas que la tuile principale).
    # Fallback : positions decisionView si la capture occupancy est absente (vieux hook).
    occupants = {}
    have_occ = any("occupantUnitId" in t for t in tiles)
    if have_occ:
        for t in tiles:
            oid = t.get("occupantUnitId")
            if oid is not None:
                occupants[t["id"]] = team_by_id.get(oid)
    else:
        board0 = Board(tiles, adjacency="native_sym")
        for u in (dv.get("units") or []):
            if not u.get("alive"):
                continue
            p = u.get("pos") or {}
            tid = board0.id_at(p.get("col"), p.get("row"))
            if tid is not None:
                occupants[tid] = u.get("team")

    print(f"[pathfind] {len(tiles)} tuiles · {len(occupants)} occupants · "
          f"{len(amt['units'])} unités à valider\n")

    modes = [a.adjacency] if a.adjacency else MODES
    for mode in modes:
        board = Board(tiles, adjacency=mode)
        exact = 0
        walk_total = 0
        nonwalk = 0
        print(f"=== mode adjacence: {mode} ===")
        for unit in amt["units"]:
            uid = unit["unitId"]
            mr = move_by_id.get(uid, 0)
            r = validate_unit(board, unit, occupants, team_by_id.get(uid), mr)
            if not r["ok"]:
                print(f"  ?? u{uid:<3} {unit['visualId']:<20} ERR {r['err']}")
                continue
            if r.get("nonWalk"):
                nonwalk += 1
                print(f"  ~~ u{uid:<3} {unit['visualId']:<20} NON-WALK (mv={mr}, "
                      f"nat={r['nNative']} reaches up to {r['maxNativeLvl']} steps > mv) "
                      f"-> Fly/Teleport/range-bonus, Walk model not applicable")
                continue
            walk_total += 1
            tag = "OK " if r["exact"] else "XX "
            if r["exact"]:
                exact += 1
            extra_s = f" extra={len(r['extra'])}" if r["extra"] else ""
            miss_s = f" missing={len(r['missing'])}" if r["missing"] else ""
            print(f"  {tag}u{uid:<3} {unit['visualId']:<20} "
                  f"mv={mr} nat={r['nNative']} pred={r['nPred']}{miss_s}{extra_s}")
            if not r["exact"]:
                if r["missing"]:
                    print(f"        missing(nat\\pred): {r['missing'][:12]}")
                if r["extra"]:
                    print(f"        extra(pred\\nat):   {r['extra'][:12]}")
        print(f"  --> WALK {exact}/{walk_total} exact · {nonwalk} non-Walk (exclues)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
