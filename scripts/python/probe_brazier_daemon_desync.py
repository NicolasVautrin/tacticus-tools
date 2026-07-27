"""Decomposition PAR ETAGE de la desynchronisation observee sur BrazierOfHolyFire (1041) contre une
cible DAEMON `blackObliterator` : coup 1 identique, coups 2..4 divergents (off [2702,2402,2617,2713]
vs live [2702,2593,2531,2867]).

Mesure : (a) TOUS les evenements live du cast (pas seulement ceux portant `Amount`), (b) la CONSO rng
live (`dumpRng` avant/apres -> delta de `mti`) confrontee a la conso du port. Un ecart de conso designe
l'etage qui tire en plus. ASCII only.

Usage : python probe_brazier_daemon_desync.py [--target blackObliterator]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from collections import deque
from pathlib import Path

import hexgeo
import rl_collect_batch as R
from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
ABILITY = 1041


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _cr(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _find(units, vis):
    return next((u for u in (units or []) if u.get("visualId") == vis and u.get("alive")), None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="blackObliterator")
    ap.add_argument("--seed", default="777")
    a = ap.parse_args()
    sid = R._resolve_session()

    def rpc(m, b=None, t=90):
        return _unwrap(R._rpc(sid, m, [b] if b is not None else [], timeout=t))

    sf = ROOT / "logs" / "runners" / f"desync-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", a.seed,
                        "--state-file", str(sf), "--board", "MC1_67", "--roster", "1",
                        "--p-units", "adeptCanoness", "--a-units", a.target],
                       cwd=str(PYDIR), capture_output=True, text=True)
    if not sf.exists():
        print("BUILD KO", (p.stderr or p.stdout or "")[-400:])
        return 1
    rid = int(json.loads(sf.read_text())["runnerId"])
    try:
        bd = Board(rpc("boardGraph", {"runnerId": rid}, 60)["tiles"], adjacency="native_sym")

        def bfs(src):
            dist, q = {src: 0}, deque([src])
            while q:
                x = q.popleft()
                for n in bd.neighbours(x):
                    if n not in dist and (n == src or bd.walkable(n)):
                        dist[n] = dist[x] + 1
                        q.append(n)
            return dist

        my, cid, tid = None, None, None
        for _ in range(25):
            dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
            caster, tgt = _find(dv["units"], "adeptCanoness"), _find(dv["units"], a.target)
            if caster is None or tgt is None:
                print("units KO")
                return 1
            my = my if my is not None else caster.get("owner")
            if dv.get("currentPlayer") != my:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            cid = caster["id"]
            at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
            ab = next((x for x in ((at.get("units") or [{}])[0].get("abilities") or [])
                       if x.get("abilityId") == ABILITY), {})
            legal = [x.get("targetId") for x in (ab.get("fromHere") or [])]
            if tgt["id"] in legal:
                tid = tgt["id"]
                break
            dist = bfs(bd.id_at(*_cr(tgt)))
            mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == cid), None)
            reach = {bd.id_at(t["col"], t["row"]): (t["col"], t["row"])
                     for t in ((cmt or {}).get("tiles") or [])}
            pool = [t for t in reach if t in dist and dist[t] >= 1]
            if not pool:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            c, r = reach[min(pool, key=lambda t: dist[t])]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": cid, "to": {"col": c, "row": r}}}, 60)
        if tid is None:
            print("APPROACH KO")
            return 1

        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        tgt_u = next(u for u in dv["units"] if u["id"] == tid)
        print("caster=%s target=%s(%s) pos c=%s t=%s effets_cible=%s"
              % (cid, tid, a.target, _cr(_find(dv["units"], "adeptCanoness")), _cr(tgt_u),
                 [e.get("effectType") for e in (tgt_u.get("effects") or [])]))
        print("rng AVANT: mti=%s" % s0.get("mti"))

        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ABILITY},
            "captureEvents": True}, 150)
        s1 = rpc("dumpRng", {"runnerId": rid}, 30)
        print("rng APRES: mti=%s" % s1.get("mti"))
        print("--- EVENEMENTS LIVE (tous, tags COMPLETS, ordre natif) ---")
        n = 0
        for act in (res.get("actions") or []):
            for e in (act.get("events") or []):
                td = e.get("tags")
                td = json.loads(td) if isinstance(td, str) else (td or {})
                if not td:
                    continue
                n += 1
                print("  #%03d %s | %s" % (n, json.dumps({k: v for k, v in e.items()
                                                          if k != "tags"})[:120],
                                           json.dumps(td)[:400]))

        st = load_state(dv, ob, snap, board=bd)
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        st.rng = rng
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=cid, target_id=tid, ability_type=ABILITY))
        last = runner.ability_handler.last or {}
        print("--- PORT ---")
        print("  per_hit=%s hits=%s" % ((last.get("attack") or {}).get("per_hit"), last.get("hits")))
        print("  rng APRES port: mti=%s (delta port=%s, delta live=%s)"
              % (st.rng.mti, st.rng.mti - s0["mti"], s1.get("mti") - s0["mti"]))
        return 0
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        sf.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
