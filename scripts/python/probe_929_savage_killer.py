"""#929 -- MESURE du passif `SavageKiller` (`spaceWulfen` << Ulf >>, TriggeredAbilityType 1159).

Ce probe MESURE (il ne garde rien -- c'est `tests/engine/runner/test_929_savage_killer_live.py` qui
garde). Il monte le duel `spaceWulfen` vs `orksRuntherd`, pilote la distance, et rend l'etat LIVE
avant/apres l'action mesuree pour les TROIS regimes du passif :

  * `--regime actif`   : Runtherd ADJACENT caste `GetEmRuntz` (un ACTIF) -> face B, Ulf frappe le
                         CASTER avant que l'ability ne s'execute ;
  * `--regime normale` : Runtherd ADJACENT fait son attaque NORMALE -> AUCUNE reaction (le gate
                         `IsActiveAbilityCountedAsUsed` porte le << active ability >> de l'i2) ;
  * `--regime summon`  : Runtherd a DISTANCE 2 caste `GetEmRuntz` -> ses grots naissent sur les
                         tuiles libres adjacentes AU CASTER **et** adjacentes a un ENNEMI
                         (`GetEmRuntzAbility$$GetSpawnTileSelector`), donc ADJACENTES A ULF ->
                         face A, `On(UnitAdded)` -> Ulf frappe chaque grot.

Usage (depuis scripts/python, session warmee) :
    python probe_929_savage_killer.py --regime actif --state-file <ABSOLU>.json
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque

import rl_duel

ULF = "spaceWulfen"
RUNTHERD = "orksRuntherd"


_SID = None


def _rpc(method, body, timeout=60):
    """Deballe la reponse RPC du host (meme forme que la fixture `rpc` de la conftest)."""
    global _SID
    if _SID is None:
        _SID = rl_duel._resolve_session()
    r = rl_duel._rpc(_SID, method, [body], timeout=timeout)
    if isinstance(r, dict) and "result" in r:
        r = r["result"]
    if isinstance(r, dict) and "value" in r and set(r.keys()) <= {"value", "type"}:
        r = r["value"]
    return r


def _bfs(board_tiles, src):
    """Distance hex en pas depuis `src`, sur le graphe `boardGraph`."""
    adj = {int(t["id"]): [int(n) for n in (t.get("neighbours") or [])] for t in board_tiles}
    dist = {src: 0}
    q = deque([src])
    while q:
        x = q.popleft()
        for n in adj.get(x, ()):
            if n not in dist:
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def _alive(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _tile_of(board_tiles, u):
    p = u.get("pos") or {}
    for t in board_tiles:
        if t.get("col") == p.get("col") and t.get("row") == p.get("row"):
            return int(t["id"])
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regime", choices=("actif", "normale", "summon"), required=True)
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--hp-target", default="999999")
    args = ap.parse_args()

    want = 2 if args.regime == "summon" else 1
    argv = ["build", "--seed", args.seed, "--board", args.board,
            "--state-file", args.state_file, "--roster", "1",
            "--p-units", ULF, "--a-units", RUNTHERD,
            "--hp-player", "999999", "--hp-target", args.hp_target]
    rc = rl_duel.main(argv)
    if rc:
        print("KO build rc=%s" % rc)
        return 1
    rid = json.loads(open(args.state_file, encoding="utf-8").read())["runnerId"]

    bg = _rpc("boardGraph", {"runnerId": rid}, 60)
    tiles = bg["tiles"]

    def dv():
        return _rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)

    # --- pilotage : amener Ulf a `want` hexes de Runtherd -------------------------------------
    for _turn in range(30):
        d = dv()
        ulf, run = _alive(d, ULF), _alive(d, RUNTHERD)
        if ulf is None or run is None:
            print("KO unite manquante")
            return 1
        dist = _bfs(tiles, _tile_of(tiles, run))
        if dist.get(_tile_of(tiles, ulf)) == want:
            break
        if d.get("currentPlayer") != ulf.get("owner"):
            _rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        mt = _rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        row = next((x for x in (mt.get("units") or []) if x.get("unitId") == ulf["id"]), None)
        reach = {}
        for t in ((row or {}).get("tiles") or []):
            tid = next((int(z["id"]) for z in tiles
                        if z.get("col") == t["col"] and z.get("row") == t["row"]), None)
            if tid is not None:
                reach[tid] = (t["col"], t["row"])
        exact = [t for t in reach if dist.get(t) == want]
        pool = exact or [t for t in reach if t in dist]
        if not pool:
            _rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        best = exact[0] if exact else min(pool, key=lambda t: dist[t])
        col, r = reach[best]
        _rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": ulf["id"], "to": {"col": col, "row": r}}}, 40)
        if not exact:
            _rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

    # --- passer au tour ADVERSE ---------------------------------------------------------------
    for _ in range(4):
        d = dv()
        ulf = _alive(d, ULF)
        if ulf is not None and d.get("currentPlayer") != ulf.get("owner"):
            break
        _rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

    d = dv()
    ulf, run = _alive(d, ULF), _alive(d, RUNTHERD)
    got = _bfs(tiles, _tile_of(tiles, run)).get(_tile_of(tiles, ulf))
    print("[MONTAGE] regime=%s distance=%s (voulue %s) rid=%s" % (args.regime, got, want, rid))
    print("[MONTAGE] abilities Runtherd = %s"
          % [(a.get("kind"), a.get("id"), a.get("name")) for a in (run.get("abilities") or [])])
    before = {u["id"]: (u.get("visualId"), u.get("hp")) for u in (d.get("units") or [])}
    print("[AVANT] %s" % json.dumps(before))

    if args.regime == "normale":
        norm = next((a for a in (run.get("abilities") or []) if a.get("kind") == "normal"), None)
        act = {"kind": "ability", "casterId": run["id"], "targetId": ulf["id"],
               "abilityType": norm["id"]}
    else:
        active = next((a for a in (run.get("abilities") or []) if a.get("kind") == "active"), None)
        if active is None:
            print("KO aucune active sur Runtherd")
            return 1
        act = {"kind": "ability", "casterId": run["id"], "targetId": ulf["id"],
               "abilityType": active["id"]}
    print("[ACTION] %s" % json.dumps(act))
    res = _rpc("applyAction", {"runnerId": rid, "action": act}, 90)
    a0 = (res.get("actions") or [{}])[0]
    print("[LIVE] ok=%s events=%d" % (a0.get("ok"), len(a0.get("events") or [])))
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        keep = {k: v for k, v in td.items()
                if k in ("Caster_Id", "Target_Id", "Amount", "Passive_Ability_Type",
                         "Active_Ability_Type", "Unit_IsSummoned", "Attack_Weapon_DamageProfile")}
        if keep:
            print("   ev %-28s %s" % (e.get("group") or e.get("action") or "", json.dumps(keep)))
    d2 = dv()
    after = {u["id"]: (u.get("visualId"), u.get("hp"), u.get("alive"))
             for u in (d2.get("units") or [])}
    print("[APRES] %s" % json.dumps(after))
    return 0


if __name__ == "__main__":
    sys.exit(main())
