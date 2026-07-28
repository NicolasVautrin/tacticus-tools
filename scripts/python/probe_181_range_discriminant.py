"""probe #181 -- LE champ `range` est-il le bon ? Discriminant PAR LA DISTANCE.

`rules` se verifie facilement (ami/ennemi). `range`, lui, se trompe SILENCIEUSEMENT : un
`RANGE_ADJACENT` (portee 1) mis a la place d'une portee d'ARME (3) refuse des casts LEGAUX -- le
seul sens qui casse vraiment. Ce probe approche le caster de sa cible pas a pas et lit
`abilityReason` NATIF a chaque distance : la distance ou `TargetIsInRange` DISPARAIT est la portee
effective, et elle doit egaler celle que le port calcule (`get_range`).

Cas mesures :
  * 1003 DeathFromAbove (`ultraInceptorSgt`, arme RANGED r3) -- masque lu = RANGE_ADJACENT
    (`TargetingRange` statics+0x30, override_range=1). Si le natif acceptait a distance 2 ou 3, le
    masque serait FAUX.
  * 1004 MortisRound (`ultraEliminatorSgt`, arme RANGED r3) -- masque lu =
    RANGE_ADJACENT_IF_MELEE_CASTER (override_range=None -> portee d'ARME). Contre-epreuve : ici le
    natif DOIT accepter a distance 3.

ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import hexgeo

HOST = "http://127.0.0.1:8765"
BOARD = "MC1_67"


def _sid() -> int:
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=10) as r:
        return json.loads(r.read())["session"]["id"]


def rpc(sid, method, body, timeout=90):
    payload = json.dumps({"method": method, "args": [body]}).encode()
    req = urllib.request.Request(HOST + "/api/scripts/%d/rpc" % sid, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    return out.get("result", out)


def upos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def run_case(sid, caster_vis, ability, label, attendu):
    state_file = Path(__file__).with_name("_probe181_range_%d.json" % ability)
    state_file.unlink(missing_ok=True)
    subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", "777",
                    "--state-file", str(state_file), "--board", BOARD,
                    "--p-units", caster_vis, "--a-units", "orksWarboss,orksNob"],
                   cwd=str(Path(__file__).parent), capture_output=True, text=True)
    if not state_file.exists():
        print("[%s] build KO" % label)
        return
    rid = json.loads(state_file.read_text())["runnerId"]
    print("\n=== %s (ability %d, runner %d) -- portee attendue: %s ==="
          % (label, ability, rid, attendu))

    seen = {}
    for _ in range(16):
        d = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        me = next((u for u in (d.get("units") or [])
                   if u.get("visualId") == caster_vis and u.get("alive")), None)
        if me is None:
            break
        if d.get("currentPlayer") != me.get("owner"):
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        foes = [u for u in (d.get("units") or [])
                if u.get("alive") and u.get("owner") != me.get("owner")]
        if not foes:
            break
        goal = min(foes, key=lambda e: hexgeo.distance(upos(me), upos(e)))
        dist = hexgeo.distance(upos(me), upos(goal))
        r = rpc(sid, "abilityReason", {"runnerId": rid, "casterId": me["id"],
                                       "abilityType": ability, "targetId": goal["id"]}, 60) or {}
        tr = (r.get("targetReason") or {})
        if dist not in seen:
            seen[dist] = (tr.get("hex"), tr.get("reasons"))
            print("  dist=%-2d  natif=%s %s" % (dist, tr.get("hex"), tr.get("reasons")))
        if dist <= 1:
            break
        mov = rpc(sid, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == me["id"]), None)
        tiles = [(t["col"], t["row"]) for t in ((mu or {}).get("tiles") or [])
                 if t.get("col") is not None]
        if not tiles:
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        best = min(tiles, key=lambda t: (hexgeo.distance(t, upos(goal)), t))
        if hexgeo.distance(best, upos(goal)) >= dist:
            print("  (approche bloquee a dist=%d)" % dist)
            break
        rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": me["id"], "to": {"col": best[0], "row": best[1]}}}, 60)
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

    # portee effective = la plus GRANDE distance ou le natif ne rend PAS TargetIsInRange
    ok = [dd for dd, (hx, _n) in seen.items() if hx is not None and int(hx, 16) == 0]
    print("  -> distances ACCEPTEES par le natif : %s" % (sorted(ok) or "aucune"))
    print("  -> portee effective observee        : %s" % (max(ok) if ok else "< min mesuree"))
    rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
    state_file.unlink(missing_ok=True)


def main() -> int:
    sid = _sid()
    run_case(sid, "ultraInceptorSgt", 1003, "DeathFromAbove / RANGE_ADJACENT", "1 (adjacence)")
    run_case(sid, "ultraEliminatorSgt", 1004, "MortisRound / portee d'ARME", "3 (arme ranged)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
