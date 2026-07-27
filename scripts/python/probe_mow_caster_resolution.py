"""Diagnostic d'ETAGE -- pourquoi le gate #115 refuse TOUTES les cibles d'une ability de MoW.

Symptome MESURE (`probe_targeting_masks_lot4.py --groups mow`) : avec `TARGETING_OPTIONS` pose sur
SquigLaunchas (1200, `orksRukkatrukk`), le port rend `TargetIsEnemy` (0x4000) pour TOUTE cible --
ENNEMIS COMPRIS -- alors que le natif accepte. Un refus uniforme = le predicat ne discrimine pas :
`TargetingQuery$$UnitsCanAttackEachOther` commence par `if (!IsActor(a) || !IsActor(b)) return
false`, donc un CASTER non resolu cote port refuse tout.

On remonte l'etage : quel id porte la MoW dans `decisionView`, sous quel id `load_state` la
materialise (`_load_machines`), et que rendent `is_actor` / `units_are_friendly` /
`units_can_attack_each_other` sur ce caster.

Usage : python probe_mow_caster_resolution.py [--board MC1_67] [--seed 777]
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


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    args = ap.parse_args()
    sid = R._resolve_session()
    with tempfile.TemporaryDirectory(prefix="mowres_") as tmpdir:
        state_file = Path(tmpdir) / "state.json"
        p = subprocess.run(
            [sys.executable, "rl_duel.py", "build", "--seed", args.seed, "--board", args.board,
             "--p-units", "necroOverlord,necroDestroyer", "--a-units", "eldarRanger,astraBullgryn",
             "--p-mow", "orksRukkatrukk", "--no-ai", "--state-file", str(state_file)],
            cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if not state_file.exists():
            print("BUILD KO:", (p.stderr or p.stdout or "")[-400:])
            return 1
        rid = json.loads(state_file.read_text())["runnerId"]

        def rpc(m, b, t=90):
            return _unwrap(R._rpc(sid, m, [b], timeout=t))

        try:
            from engine.entities.pathfinding.board import Board
            from engine.runner.abilities.targeting import (is_actor, units_are_friendly,
                                                           units_can_attack_each_other)
            from engine.runner.components import MachineComponent, OwnerComponent, UnitComponent
            from engine.runner.snapshot import load_state

            bg = rpc("boardGraph", {"runnerId": rid}, 60)
            board = Board(bg["tiles"], adjacency="evenq")
            dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            ob = rpc("observeBattle", {"runnerId": rid}, 40)
            snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
            st = load_state(dec, ob, snap, board=board)

            print("--- decisionView : cles disponibles ---")
            print("top-level keys:", sorted(dec.keys()))
            for key in ("mows", "machines", "mow"):
                rows = dec.get(key)
                if rows:
                    print("  dec[%r] = %d entree(s)" % (key, len(rows)))
                    for m in rows:
                        print("    keys=%s" % sorted(m.keys()))
                        print("    casterId=%s id=%s visualId=%s team=%s owner=%s"
                              % (m.get("casterId"), m.get("id"), m.get("visualId"),
                                 m.get("team"), m.get("owner")))
            print("\n--- state (offline) : entites portant un MachineComponent ---")
            found = False
            for eid, e in st.entities.items():
                if e.get_component(MachineComponent) is not None:
                    found = True
                    uc = e.get_component(UnitComponent)
                    oc = e.get_component(OwnerComponent)
                    print("  eid=%s visual=%s team=%s player=%s"
                          % (eid, getattr(uc, "visual_id", None),
                             getattr(oc, "team", None), getattr(oc, "player", None)))
            if not found:
                print("  AUCUNE -- la MoW n'est PAS materialisee offline")
            print("\n--- predicats du gate, caster = chaque candidat ---")
            cands = []
            for key in ("mows", "machines"):
                for m in (dec.get(key) or []):
                    for k in ("casterId", "id"):
                        if m.get(k) is not None:
                            cands.append((k, int(m[k])))
            units = [u for u in (dec.get("units") or []) if u.get("alive")]
            for label, cid in cands:
                ent = st.get_entity(cid)
                oc = ent.get_component(OwnerComponent) if ent is not None else None
                print("  caster via %-9s id=%-4d present_offline=%s team=%s is_actor=%s"
                      % (label, cid, ent is not None, getattr(oc, "team", None),
                         is_actor(st, cid)))
                for u in units:
                    uid = int(u["id"])
                    print("      vs u%-4d %-16s friendly=%-5s can_attack=%s"
                          % (uid, str(u.get("visualId"))[:16],
                             units_are_friendly(st, cid, uid),
                             units_can_attack_each_other(st, cid, uid)))
        finally:
            try:
                R._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
