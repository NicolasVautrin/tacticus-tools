"""CHIFFRAGE du gap ADJACENT decouvert en validant BrazierOfHolyFire : contre une cible portant
`Daemon_ExtraBlock` (1034, pose par le trait `Daemon` 0x3fb), le NATIF consomme UN tirage de plus que
le port au 1er coup d'une attaque d'ability -> desync RNG des le coup 2. Ce gap est dans l'ETAGE
PARTAGE `AttackDamageOperation` (il ne depend d'aucune ability en particulier).

MESURE (`probe_brazier_daemon_offset.py`, board MC1_67, seed 777, caster adeptCanoness) -- meme suite de
valeurs `v1..v8` produite par le rng dans les trois runs :
    necroWarden      (NON Daemon, 2 coups) : live = v1, v3            -> 2 tirages/coup, port == live
    worldEightbound  (Daemon,     4 coups) : live = v1, v4, v6, v8    -> +1 tirage APRES le 1er coup
    blackObliterator (Daemon,     4 coups) : live = v1, v4, v6, v8    -> idem

Ce probe LIT l'etat offline de la cible pour montrer POURQUOI le port ne tire pas : quelles sources de
block il voit (`defender_effect_block_sources` + le scalaire `GetStat(7/8)`). ASCII only.

Usage : python probe_daemon_extrablock_gap.py [--target worldEightbound]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import rl_collect_batch as R
from engine.entities.pathfinding.board import Board
from engine.entities.effects import defender_effect_block_sources
from engine.runner.components import StatsComponent
from engine.runner.snapshot import load_state

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="worldEightbound")
    ap.add_argument("--seed", default="777")
    a = ap.parse_args()
    sid = R._resolve_session()

    def rpc(m, b=None, t=90):
        return _unwrap(R._rpc(sid, m, [b] if b is not None else [], timeout=t))

    sf = ROOT / "logs" / "runners" / f"blockgap-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", a.seed, "--state-file", str(sf),
                    "--board", "MC1_67", "--roster", "1", "--p-units", "adeptCanoness",
                    "--a-units", a.target], cwd=str(PYDIR), capture_output=True, text=True)
    if not sf.exists():
        print("BUILD KO")
        return 1
    rid = int(json.loads(sf.read_text())["runnerId"])
    try:
        bd = Board(rpc("boardGraph", {"runnerId": rid}, 60)["tiles"], adjacency="native_sym")
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        tgt = next(u for u in dv["units"] if u.get("visualId") == a.target)
        tid = tgt["id"]
        print("cible %s u%s effets LIVE = %s"
              % (a.target, tid, [(e.get("effectType"), e.get("name")) for e in (tgt.get("effects") or [])]))
        st = load_state(dv, ob, snap, board=bd)
        sc = st.get_entity(tid).get_component(StatsComponent)
        ctx = sc.ctx
        print("PORT block scalaire : block_chance=%s block_damage=%s"
              % (getattr(ctx, "block_chance", None), getattr(ctx, "block_damage", None)))
        effs = st.effects.active_effects(tid) if st.effects is not None else []
        print("PORT effets ACTIFS offline : %s"
              % [(int(getattr(e, "effect_type", 0) or 0), getattr(e, "name", None)) for e in effs])
        srcs = defender_effect_block_sources(effs, {"owner_id": tid})
        print("PORT defender_effect_block_sources -> %s" % (srcs,))
        print("VERDICT : le port %s de source de block pour cette cible."
              % ("DISPOSE" if (srcs or (getattr(ctx, "block_chance", 0) or 0) > 0) else "NE DISPOSE PAS"))
        return 0
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        sf.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
