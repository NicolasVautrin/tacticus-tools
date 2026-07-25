"""Probe #115 -- forme de l'oracle natif `abilityReason` (raison structuree d'un cast invalide).

Monte un runner Waaagh (orksWarboss + allies vs 3 ennemis), amene le Warboss a portee de charge,
puis interroge `abilityReason` pour CHAQUE unite vivante et imprime la raison native (flags
`TargetingRule` en noms) a cote du verdict du moteur OFFLINE (`engine.runner.abilities.targeting`).

But : verifier que la raison NATIVE et le code de raison PORTE coincident, cible par cible -- pas
seulement le booleen accepte/refuse. Sortie ASCII.

Usage : python probe_115_ability_reason.py [--board MC1_67] [--seed 777]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import hexgeo
import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
WAAAGH = 1058
CASTER = "orksWarboss"


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _upos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    args = ap.parse_args()

    sid = R._resolve_session()
    state_file = ROOT / "data" / f"_probe115_{args.board}_{args.seed}.json"
    state_file.unlink(missing_ok=True)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", args.seed, "--board", args.board,
         "--p-units", f"{CASTER},orksNob,spaceHound",
         "--a-units", "darkaCompanion,tyranWingedPrime,ultraInceptorSgt",
         "--state-file", str(state_file)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("BUILD KO:", (p.stderr or p.stdout or "")[-400:])
        return 1
    rid = json.loads(state_file.read_text())["runnerId"]

    def rpc(m, b, t=90):
        return _unwrap(R._rpc(sid, m, [b], timeout=t))

    try:
        from engine.entities.pathfinding.board import Board
        from engine.runner.abilities.handler import ABILITY_CLASSES
        from engine.runner.abilities.targeting import is_invalid_target
        from engine.runner.snapshot import load_state

        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")

        def dv():
            return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)

        def find(d, vis):
            return next((u for u in (d.get("units") or []) if u.get("visualId") == vis), None)

        def offered(uid):
            at = rpc("abilityTargets", {"runnerId": rid, "unitId": uid, "allAbilities": True}, 90)
            return {t.get("targetId") for u in (at.get("units") or []) if u.get("unitId") == uid
                    for a in (u.get("abilities") or []) if a.get("abilityId") == WAAAGH
                    for t in (a.get("fromHere") or []) if t.get("kind") == "unit"}

        legal = set()
        for _ in range(14):
            d = dv()
            wb = find(d, CASTER)
            if wb is None or not wb.get("alive"):
                print("NO CASTER")
                return 1
            if d.get("currentPlayer") != wb.get("owner"):
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            legal = offered(wb["id"])
            if legal:
                break
            foes = [u for u in (d.get("units") or [])
                    if u.get("owner") != wb.get("owner") and u.get("alive")]
            if not foes:
                break
            goal = min(foes, key=lambda e: hexgeo.distance(_upos(wb), _upos(e)))
            mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == wb["id"]), None)
            tiles = [(t["col"], t["row"]) for t in ((mu or {}).get("tiles") or [])
                     if t.get("col") is not None]
            if tiles:
                best = min(tiles, key=lambda t: (hexgeo.distance(t, _upos(goal)), t))
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": wb["id"], "to": {"col": best[0], "row": best[1]}}}, 60)
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

        d0 = dv()
        ob0 = rpc("observeBattle", {"runnerId": rid}, 40)
        snap0 = rpc("combatSnapshot", {"runnerId": rid}, 60)
        wb = find(d0, CASTER)
        st = load_state(d0, ob0, snap0, board=board)
        print(f"board={args.board} seed={args.seed} rid={rid} caster={wb['id']} "
              f"legal_natif={sorted(legal)}")
        print("uid  team  natif_offre  natif_abilityReason                       port_reason")
        for u in (d0.get("units") or []):
            if not u.get("alive"):
                continue
            uid = u["id"]
            reason = rpc("abilityReason", {"runnerId": rid, "casterId": wb["id"],
                                           "abilityType": WAAAGH, "targetId": uid}, 60)
            port = is_invalid_target(st, int(wb["id"]), int(uid), ABILITY_CLASSES[WAAAGH]())
            print(f"{uid:<4} {u.get('owner')}     {str(uid in legal):<12} port={hex(port)}")
            print("      natif:", json.dumps(reason))

        # --- volet CASTER (hors perimetre #115, MESURE ici) : Waaagh pose le bit 0x10
        # `CasterHasNotMoved` dans ses TargetingOptions. On bouge le Warboss d'une tuile et on relit
        # `casterReason` pour la MEME cible legale -> confirme (ou infirme) que le natif refuse alors
        # le cast par une regle CASTER que le port n'implemente pas.
        if legal:
            tgt = sorted(legal)[0]
            before = rpc("abilityReason", {"runnerId": rid, "casterId": wb["id"],
                                           "abilityType": WAAAGH, "targetId": tgt}, 60)
            mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == wb["id"]), None)
            tiles = [(t["col"], t["row"]) for t in ((mu or {}).get("tiles") or [])
                     if t.get("col") is not None]
            if tiles:
                dst = min(tiles, key=lambda t: (hexgeo.distance(t, _upos(wb)), t))
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": wb["id"], "to": {"col": dst[0], "row": dst[1]}}}, 60)
                after = rpc("abilityReason", {"runnerId": rid, "casterId": wb["id"],
                                              "abilityType": WAAAGH, "targetId": tgt}, 60)
                print("--- volet CASTER (CasterHasNotMoved 0x10) ---")
                print("  avant move casterReason:",
                      json.dumps((before or {}).get("casterReason")))
                print("  apres move casterReason:",
                      json.dumps((after or {}).get("casterReason")))
                print("  apres move targetReason:",
                      json.dumps((after or {}).get("targetReason")))
    finally:
        try:
            R._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
        except Exception:
            pass
        state_file.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
