"""Probe #94 — diagnostic du cast LIVE de Waaagh (1058, orksWarboss).

Monte un runner isole, amene le Warboss a portee, INSPECTE ce que le natif expose pour l'ability
(decisionView allAbilities + abilityTargets) puis caste et affiche la reponse brute d'applyAction.
Sert a etablir POURQUOI un cast live ne produit rien (portee, cible, charges) avant d'accuser le port.
ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import hexgeo
import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
# SORTIE de run -> `logs/` RELATIF au checkout (#314) : un chemin absolu ferait
# ecrire ce probe dans l'arbre principal depuis un worktree d'agent.
STATE = PYDIR.parents[1] / "logs" / "runners" / "_probe94_waaagh_state.json"


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def main(caster="orksWarboss", enemy="necroWarden", ability=1058, seed="777", maxd=3):
    ability, maxd = int(ability), int(maxd)
    sid = R._resolve_session()
    print("[probe] session", sid)
    _unwrap(R._rpc(sid, "autoBootExtraire", [{}], timeout=180))
    STATE.unlink(missing_ok=True)
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", seed,
                        "--state-file", str(STATE), "--board", "MC1_67",
                        "--p-units", caster, "--a-units", enemy],
                       cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if not STATE.exists():
        print("[probe] build KO:", (p.stderr or p.stdout or "")[-400:])
        return
    rid = json.loads(STATE.read_text())["runnerId"]
    print("[probe] runner", rid)

    def rpc(m, b, t=90):
        return _unwrap(R._rpc(sid, m, [b], timeout=t))

    def upos(u):
        q = u.get("pos") or {}
        return (q.get("col"), q.get("row"))

    try:
        for i in range(20):
            dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
            c = next((u for u in dv["units"] if u.get("visualId") == caster), None)
            e = next((u for u in dv["units"] if u.get("visualId") == enemy), None)
            if c is None or e is None:
                print("[probe] caster/enemy absent"); return
            if dv.get("currentPlayer") != c.get("owner"):
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            d = hexgeo.distance(upos(c), upos(e))
            at = rpc("abilityTargets", {"runnerId": rid}, 90)
            tg = []
            for u in (at.get("units") or []):
                if u.get("unitId") != c["id"]:
                    continue
                for a in (u.get("abilities") or []):
                    if a.get("abilityId") == int(ability):
                        tg = [(t.get("kind"), t.get("targetId")) for t in (a.get("targets") or [])]
            print(f"[probe] step{i} dist={d} caster={upos(c)} enemy={upos(e)} targets1058={tg}")
            if tg:
                break
            if d <= maxd:
                print("[probe] a portee mais AUCUNE cible legale -> geometrie de charge")
                break
            mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
            mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == c["id"]), None)
            best = None
            for t in (mu or {}).get("tiles") or []:
                if t.get("col") is None:
                    continue
                dd = hexgeo.distance((t["col"], t["row"]), upos(e))
                if best is None or dd < best[0]:
                    best = (dd, (t["col"], t["row"]))
            if best is None or best[0] >= d:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": c["id"], "to": {"col": best[1][0], "row": best[1][1]}}}, 60)
            if best[0] > maxd:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        c = next(u for u in dv["units"] if u.get("visualId") == caster)
        e = next(u for u in dv["units"] if u.get("visualId") == enemy)
        print("[probe] caster abilities:", json.dumps(c.get("abilities"))[:600])
        at = rpc("abilityTargets", {"runnerId": rid}, 90)
        for u in (at.get("units") or []):
            if u.get("unitId") != c["id"]:
                continue
            for a in (u.get("abilities") or []):
                print("[probe] abilityTargets", a.get("abilityId"),
                      [(t.get("kind"), t.get("targetId")) for t in (a.get("targets") or [])][:8])
        ids0 = {u["id"] for u in dv["units"]}
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": c["id"], "targetId": e["id"],
            "abilityType": ability}}, 120)
        print("[probe] applyAction ->", json.dumps(r)[:900])
        dv1 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        new = [u for u in dv1["units"] if u["id"] not in ids0]
        print("[probe] new units:", [(u["id"], u.get("visualId"), upos(u)) for u in new])
        c1 = next((u for u in dv1["units"] if u["id"] == c["id"]), None)
        print("[probe] caster after:", upos(c1),
              "effects:", [ef.get("name") for ef in (c1 or {}).get("effects") or []])
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 30)
        STATE.unlink(missing_ok=True)
        print("[probe] disposed", rid)


if __name__ == "__main__":
    args = sys.argv[1:]
    main(*(args if args else []))
