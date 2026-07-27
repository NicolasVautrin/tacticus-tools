"""Diagnostic d'ETAGE pour la mesure du bit 57 -- pourquoi `TargetIsInRange` domine.

Le probe `probe_targeting_masks_lot4.py --groups bit57` mesure `TargetIsInRange` (0x8000000) sur
TOUTES les cibles de Doombolt (1102, `thousAhriman`), Y COMPRIS le caster lui-meme a distance 0 et
un allie AMENE a distance 1. La distance n'est donc PAS le facteur : on remonte l'etage
(`abilityState` = l'ability est-elle seulement utilisable ? `abilityTargets` = existe-t-il une
position d'ou le cast est legal ? `castFromTiles` = laquelle ?) au lieu de conclure.

Usage : python probe_bit57_diag.py [--board MC1_67] [--seed 777]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
DOOMBOLT = 1102


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    args = ap.parse_args()
    sid = R._resolve_session()
    with tempfile.TemporaryDirectory(prefix="bit57diag_") as tmpdir:
        state_file = Path(tmpdir) / "state.json"
        p = subprocess.run(
            [sys.executable, "rl_duel.py", "build", "--seed", args.seed, "--board", args.board,
             "--p-units", "thousAhriman,necroOverlord", "--a-units", "eldarRanger,astraBullgryn",
             "--no-ai", "--state-file", str(state_file)],
            cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if not state_file.exists():
            print("BUILD KO:", (p.stderr or p.stdout or "")[-400:])
            return 1
        rid = json.loads(state_file.read_text())["runnerId"]

        def rpc(m, b, t=90):
            return _unwrap(R._rpc(sid, m, [b], timeout=t))

        try:
            dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            units = [u for u in (dec.get("units") or []) if u.get("alive")]
            ahr = next((u for u in units if u.get("visualId") == "thousAhriman"), None)
            if ahr is None:
                print("thousAhriman absent :", [u.get("visualId") for u in units])
                return 1
            print("caster u%d pos=%s owner=%s" % (ahr["id"], ahr.get("pos"), ahr.get("owner")))
            for u in units:
                print("  u%-4d %-18s owner=%s pos=%s" % (u["id"], u.get("visualId"),
                                                         u.get("owner"), u.get("pos")))
            # ETAGE 1 -- l'ability est-elle utilisable sur ce caster ?
            r = rpc("abilityReason", {"runnerId": rid, "casterId": ahr["id"],
                                      "abilityType": DOOMBOLT, "targetId": ahr["id"]}, 60)
            print("\n[etage1] abilityState =", json.dumps((r or {}).get("abilityState")))
            print("[etage1] casterReason  =", json.dumps((r or {}).get("casterReason")))
            print("[etage1] targetReason  =", json.dumps((r or {}).get("targetReason")))
            # ETAGE 2 -- le jeu propose-t-il des cibles pour 1102 ?
            at = rpc("abilityTargets", {"runnerId": rid, "unitId": ahr["id"],
                                        "abilityType": DOOMBOLT}, 90)
            for un in (at.get("units") or []):
                for ab in (un.get("abilities") or []):
                    print("[etage2] ability=%s usable=%s cooldown=%s disabled=%s "
                          "targets=%d fromHere=%d"
                          % (ab.get("abilityId"), ab.get("usable"), ab.get("cooldown"),
                             ab.get("disabled"), ab.get("targetCount"), ab.get("fromHereCount")))
                    for t in (ab.get("targets") or [])[:12]:
                        print("           target:", json.dumps(t))
            # ETAGE 3 -- existe-t-il une TUILE d'ou le cast sur un allie est legal ?
            ally = next((u for u in units
                         if u.get("owner") == ahr.get("owner") and u["id"] != ahr["id"]), None)
            foe = next((u for u in units if u.get("owner") != ahr.get("owner")), None)
            for label, tgt in (("allie", ally), ("ennemi", foe), ("self", ahr)):
                if tgt is None:
                    continue
                cf = rpc("castFromTiles", {"runnerId": rid, "casterId": ahr["id"],
                                           "targetId": tgt["id"], "abilityType": DOOMBOLT}, 90)
                print("[etage3] %-7s u%-4d currentValid=%s moveTiles=%d"
                      % (label, tgt["id"], (cf or {}).get("currentValid"),
                         len((cf or {}).get("moveTiles") or [])))
        finally:
            try:
                R._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
