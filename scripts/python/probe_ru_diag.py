#!/usr/bin/env python
"""Diag RealityUnbound : le probe live rend ZERO effet sur Yazaghor apres 3 coups Psychic sur
3 ennemis distincts. On instrumente chaque etage pour trouver le PREMIER qui diverge :
  1. les attaques infligent-elles vraiment du degat ? (HP des cibles avant/apres)
  2. le profil du coup est-il bien Psychic ? (observeBattle / events)
  3. des effets apparaissent-ils quelque part (n'importe quelle unite) ?
  4. Yazaghor porte-t-il bien le passif cote natif ? (decisionView / gameconfig)
ASCII only. Usage: python probe_ru_diag.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import hexgeo                                                            # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402

ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_ru_diag_state.json"
CARRIER, PSYKER, FOE, BOARD = "thousTzaangor", "thousSorcerer", "orksNob", "MC1_67"


def rpc(sid, m, args, t=90):
    return (_rpc(sid, m, [args], timeout=t).get("result") or {})


def main():
    sid = _resolve_session()
    STATE.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", "31337", "--rank", "17",
           "--p-units", f"{CARRIER},{PSYKER},{PSYKER},{PSYKER}", "--a-units", f"{FOE},{FOE},{FOE}",
           "--board", BOARD, "--state-file", str(STATE)]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not STATE.exists():
        print((p.stdout or "")[-800:], (p.stderr or "")[-800:]); return 2
    rid = json.loads(STATE.read_text(encoding="utf-8"))["runnerId"]
    print(f"[diag] runner={rid}")
    try:
        dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
        us = dv.get("units") or []
        print(f"[diag] units: " + ", ".join(
            f"u{u.get('id')}={u.get('visualId')}(team{u.get('team')})" for u in us))
        carrier = next((u for u in us if u.get("visualId") == CARRIER), None)
        print(f"[diag] carrier keys = {sorted((carrier or {}).keys())}")
        print(f"[diag] carrier passives (dv) = {json.dumps(carrier.get('passiveAbilities'))[:200]}")
        psykers = [u for u in us if u.get("visualId") == PSYKER]
        foes = [u for u in us if u.get("visualId") == FOE]

        ob0 = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
        hp0 = {u.get("id", u.get("entityId")): u.get("hp") for u in (ob0.get("units") or [])}
        print(f"[diag] HP avant = {hp0}")

        # une seule attaque, la plus simple : psyker[0] -> foe[0]
        pk, tgt = psykers[0], foes[0]
        pp = pk.get("pos") or {}
        tp = tgt.get("pos") or {}
        print(f"[diag] psyker u{pk['id']} @{pp} -> foe u{tgt['id']} @{tp} "
              f"dist={hexgeo.distance((pp.get('col'), pp.get('row')), (tp.get('col'), tp.get('row')))}")
        mv = rpc(sid, "aiMovableTiles", {"runnerId": rid, "unitId": pk["id"]}, 90)
        tiles = [(t.get("col"), t.get("row")) for t in (mv.get("unionTiles") or [])]
        for u in (mv.get("units") or []):
            if u.get("unitId") == pk["id"]:
                tiles = [(t.get("col"), t.get("row")) for t in (u.get("tiles") or [])]
        goal = (tp.get("col"), tp.get("row"))
        tiles.sort(key=lambda t: abs(hexgeo.distance(t, goal) - 2))
        if tiles:
            print(f"[diag] move -> {tiles[0]} (dist cible {hexgeo.distance(tiles[0], goal)})")
            rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": pk["id"],
                "to": {"col": tiles[0][0], "row": tiles[0][1]}}}, 90)

        dv2 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
        plans = [p for p in (dv2.get("attackPlans") or []) if p.get("unitId") == pk["id"]]
        print(f"[diag] attackPlans du psyker = {json.dumps(plans)[:600]}")
        aid = None
        for pl in plans:
            for ev in (pl.get("evals") or []):
                if ev.get("targetId") == tgt["id"]:
                    aid = ev.get("abilityId")
        print(f"[diag] normal_attack_id = {aid}")
        if aid is not None:
            r = rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": pk["id"], "targetId": tgt["id"],
                "abilityType": aid}}, 120)
            print(f"[diag] applyAction -> {json.dumps(r)[:700]}")

        ob1 = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
        hp1 = {u.get("id", u.get("entityId")): u.get("hp") for u in (ob1.get("units") or [])}
        print(f"[diag] HP apres = {hp1}")
        print(f"[diag] deltas = { {k: (hp0.get(k), v) for k, v in hp1.items() if hp0.get(k) != v} }")

        dv3 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
        for u in (dv3.get("units") or []):
            eff = u.get("effects") or []
            if eff:
                print(f"[diag] EFFETS u{u.get('id')}={u.get('visualId')} -> {json.dumps(eff)[:400]}")
        print("[diag] (aucune ligne EFFETS ci-dessus = aucune unite ne porte d'effet)")
        sm = rpc(sid, "statModSources", {"runnerId": rid}, 90)
        print(f"[diag] statModSources = {json.dumps(sm)[:900]}")
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 15)
        print(f"[diag] runner {rid} dispose")
    return 0


if __name__ == "__main__":
    sys.exit(main())
