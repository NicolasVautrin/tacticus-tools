"""PROBE #passifs-DA — LionHelm_ExtraDmg (1193) : +extraDmg aux attaques d'OVERWATCH des allies <=2 hexes.

`IdunBattle.Entities.Effects.Loki.LionHelm_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` gate son
additif sur `get_OwnerIsCaster & (HasEffect(Caster, Overwatch_AutoAttack) & IsOverwatchAttack | ...)` ;
son selecteur (vtable slot +0x538) est `SurroundingFriends(Azrael, range = 2)` — **sans filtre de
faction** (seul le volet blockChance porte `UnitsFromFaction(DarkAngels)`), donc TOUT allie compte.

RECETTE = celle, PROUVEE RNG-ALIGNEE, de `tests/engine/runner/test_overwatch_live.py` (approche
pas-a-pas du mover jusqu'a l'entree en portee, `dumpRng` juste avant le pas declencheur, replay
`MoveUnitMessage`). On y AJOUTE Azrael dans l'equipe de l'overwatcher, place :

  IN_RING   adjacent a l'overwatcher (<= range 2) -> aura ACTIVE   -> +extraDmg par coup
  OUT_RING  a l'autre bout du plateau (>= 3)      -> aura INACTIVE -> AUCUN bonus (cas NEGATIF)

Verdict = replay-diff bit-exact (`off_hp == live_hp`) DANS LES DEUX CAS.
ASCII only. Usage : python probe_lionhelm_overwatch.py
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from collections import deque
from pathlib import Path

BASE = "http://127.0.0.1:8765"
CARRIER = "darkaAzrael"           # LionHelm
OVERWATCHER = "eldarRanger"       # meme overwatcher que le test de reference (tir Energy, 1 coup)
MOVER = "necroOverlord"           # cible VANILLE tanky (effects=[], aucune reduction non portee)


def rpc(method, args=None, timeout=90000):
    body = json.dumps({"method": method, "args": args or {}, "timeout": timeout}).encode()
    req = urllib.request.Request(BASE + "/api/scripts/1/rpc", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        out = json.loads(r.read().decode())
    return out.get("result", out)


def build(state_file: Path) -> int:
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", "777", "--board", "MC1_67",
           "--roster", "1", "--p-units", MOVER, "--a-units", ",".join([OVERWATCHER, CARRIER]),
           "--state-file", str(state_file)]
    subprocess.run(cmd, cwd=str(Path(__file__).parent), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def _seed_rng(s):
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _bfs(board, src):
    dist = {src: 0}
    q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def place_azrael(rid, az_id, ow_pos, far: bool, board):
    """Pose Azrael a >=3 (far) ou <=2 (proche) hexes de l'overwatcher, en essayant des tuiles
    candidates jusqu'a ce que la distance VOULUE soit atteinte (un move vers une tuile occupee ou
    non jouable echoue silencieusement)."""
    import hexgeo
    cands = [(c, r) for c in range(0, 8) for r in range(0, 10)]
    cands.sort(key=lambda p: (-hexgeo.distance(p, ow_pos)) if far else hexgeo.distance(p, ow_pos))
    for c, r in cands[:40]:
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": az_id, "to": {"col": c, "row": r}}}, 40000)
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1})
        a = next((u for u in (dv.get("units") or []) if u["id"] == az_id), None)
        if a is None:
            continue
        d = hexgeo.distance(_pos(a), ow_pos)
        if (far and d >= 3) or ((not far) and 1 <= d <= 2):
            return d
    return None


def run(rid, label, az_far: bool):
    import hexgeo
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import MoveUnitMessage
    from engine.runner.components import HealthComponent
    import gameconfig as GC

    bg = rpc("boardGraph", {"runnerId": rid})
    board = Board(bg["tiles"], adjacency="evenq")

    def tof(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None

    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    units = dec.get("units") or []
    mover = next((u for u in units if u.get("visualId") == MOVER and u.get("alive")), None)
    ow = next((u for u in units if u.get("visualId") == OVERWATCHER and u.get("alive")), None)
    az = next((u for u in units if u.get("visualId") == CARRIER and u.get("alive")), None)
    if not (mover and ow and az):
        print("  SKIP %s : unite manquante" % label)
        return None
    mover_id, ow_id, az_id = mover["id"], ow["id"], az["id"]
    my_player = mover.get("owner")
    d0 = place_azrael(rid, az_id, _pos(ow), az_far, board)
    print("  ... %s : distance Azrael<->overwatcher = %s" % (label, d0))

    R = max([int(w.get("Range") or 0) for w in ((GC.unit(OVERWATCHER) or {}).get("weapons") or [])]
            or [0]) or 1
    for _turn in range(30):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        mv = next((u for u in (dec.get("units") or []) if u["id"] == mover_id and u.get("alive")), None)
        owl = next((u for u in (dec.get("units") or []) if u["id"] == ow_id and u.get("alive")), None)
        azl = next((u for u in (dec.get("units") or []) if u["id"] == az_id and u.get("alive")), None)
        if mv is None or owl is None or azl is None:
            print("  SKIP %s : unite disparue pendant l'approche" % label)
            return None
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40000)
            continue
        dgoal = _bfs(board, tof(owl))
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"})
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == mover_id), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        cur = tof(mv)
        out_pool = [t for t in reach if t in dgoal and dgoal[t] > R and dgoal[t] < dgoal.get(cur, 99)]
        if dgoal.get(cur, 99) > R and out_pool:
            best = min(out_pool, key=lambda t: dgoal[t])
            col, row = reach[best]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": mover_id, "to": {"col": col, "row": row}}}, 40000)
            dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1})
            if dv2.get("currentPlayer") == my_player:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40000)
            continue
        step_pool = [t for t in reach if t in dgoal and t in set(board.neighbours(cur))]
        if not step_pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40000)
            continue
        best = min(step_pool, key=lambda t: dgoal[t])
        col, row = reach[best]

        ob = rpc("observeBattle", {"runnerId": rid})
        snap = rpc("combatSnapshot", {"runnerId": rid})
        hp_before = next((u.get("hp") for u in (ob.get("units") or []) if u.get("squadId") == mover_id), None)
        s0 = rpc("dumpRng", {"runnerId": rid})
        state = load_state(dec, ob, snap, board=board)
        if not (isinstance(s0, dict) and "mt" in s0):
            print("  SKIP %s : dumpRng KO" % label)
            return None
        state.rng = _seed_rng(s0)
        d_az_ow = hexgeo.distance(_pos(azl), _pos(owl))

        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": mover_id, "to": {"col": col, "row": row}}}, 40000)
        ob2 = rpc("observeBattle", {"runnerId": rid})
        hp_after = next((u.get("hp") for u in (ob2.get("units") or []) if u.get("squadId") == mover_id), None)
        if hp_before is None or hp_after is None or hp_after >= hp_before:
            continue                                   # pas d'overwatch sur ce pas -> continuer

        runner = Runner(state).install_default_handlers(20)
        runner.apply(MoveUnitMessage(mover_id, (col, row)))
        am = runner.movement_handler.after_move
        off_hp = state.get_entity(mover_id).get_component(HealthComponent).hp
        res = ([a for a in (am or []) if a.get("effect") == "Overwatch_AutoAttack"]
               or [{}])[0].get("result") or {}
        ok = (off_hp == hp_after)
        print("  [%s] d(azrael,overwatcher)=%s | mover hp %s -> live %s (dmg %s) | offline %s (dmg %s)"
              % (label, d_az_ow, hp_before, hp_after, hp_before - hp_after, off_hp, hp_before - off_hp))
        print("      off per_hit=%s clean=[%s,%s] -> %s"
              % (res.get("per_hit"), res.get("clean_min"), res.get("clean_max"),
                 "OK bit-exact" if ok else "MISMATCH"))
        return {"label": label, "d_az_ow": d_az_ow, "live_dmg": hp_before - hp_after,
                "off_dmg": hp_before - off_hp,
                "clean": (res.get("clean_min"), res.get("clean_max")), "ok": ok}
    print("  SKIP %s : aucun overwatch declenche" % label)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()
    base = Path(a.state_file) if a.state_file else \
        Path(__file__).resolve().parents[2] / "logs" / "runners" / "probe_lh_ow.json"
    base.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for label, far in (("IN_RING", False), ("OUT_RING", True)):
        sf = base.with_name("%s_%s.json" % (base.stem, label.lower()))
        rid = build(sf)
        print("runner %s = %d" % (label, rid))
        rows.append(run(rid, label, far))
    ok = all(r is not None and r["ok"] for r in rows)
    if all(r is not None for r in rows):
        print("DELTA live (in-ring - out-ring) = %s | offline = %s | clean in=%s out=%s"
              % (rows[0]["live_dmg"] - rows[1]["live_dmg"], rows[0]["off_dmg"] - rows[1]["off_dmg"],
                 rows[0]["clean"], rows[1]["clean"]))
        if rows[0]["d_az_ow"] > 2 or rows[1]["d_az_ow"] < 3:
            print("  ATTENTION geometrie non discriminante (d_in=%s d_out=%s)"
                  % (rows[0]["d_az_ow"], rows[1]["d_az_ow"]))
            ok = False
    print("VERDICT:", "OK replay-diff bit-exact dans les 2 geometries" if ok
          else "MISMATCH / SKIP (cf. ci-dessus)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
