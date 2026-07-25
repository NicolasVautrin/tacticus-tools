#!/usr/bin/env python
"""Probe #84c -- verification OFFLINE end-to-end du maillon LetTheGalaxyBurn (1058 -> 1482 -> 1477) :
la POSE (`On(PreAttack=5)` -> `SetPersistentData`) est-elle atteinte, et le canal de coups la LIT-il ?

Charge l'etat d'un runner LIVE, rejoue N attaques normales OFFLINE, et compte les coups par attaque.
Attendu : base OU base+1, avec une frequence de base+1 ~= 33 % (`LetTheGalaxyBurnChancePct`), et
`persistent_data` VIDE apres chaque attaque (le Reset `On(9)` IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour efface).

ASCII only. Usage: python probe_84_offline.py --runner <rid> [--n 200]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.entities.pathfinding.board import Board  # noqa: E402
from engine.runner.snapshot import load_state  # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister  # noqa: E402
from engine.runner.runner import Runner  # noqa: E402
from engine.runner.messages import AttackUnitMessage  # noqa: E402
from engine.runner.components import (UnitComponent, PositionComponent, HealthComponent,
                                      PersistentDataComponent)  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, required=True)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--attacker-vis", default="blackTerminator")
    args = ap.parse_args()
    sid = _resolve_session()

    def rpc(m, b, t=90):
        r = _rpc(sid, m, b, t)
        return r.get("result") if isinstance(r, dict) and "result" in r else r

    rid = args.runner
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)

    st = load_state(dv, ob, snap, board=board)
    aid = tid = None
    for uid, e in st.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is None or not uc.alive:
            continue
        if uc.visual_id == args.attacker_vis:
            aid = uid
        else:
            tid = uid if tid is None else tid
    print(f"[offline] attaquant u{aid} ({args.attacker_vis}) / cible u{tid}")
    effs = [e.name for e in (st.effects.by_unit.get(aid) or [])] if st.effects else []
    print(f"[offline] effets attaquant = {effs}")
    from engine.runner.components import StatsComponent
    sc = st.entities[aid].get_component(StatsComponent)
    print(f"[offline] traits attaquant = {sc.ctx.traits}")

    # colle l'attaquant a la cible (melee)
    tp = st.entities[tid].get_component(PositionComponent)
    nb = [board.coord(t) for t in board.neighbours(board.id_at(tp.col, tp.row)) if board.walkable(t)]
    ap_ = st.entities[aid].get_component(PositionComponent)
    ap_.col, ap_.row = nb[0]

    st.rng = IntBasedMersenneTwister(); st.rng.init_genrand(12345)
    hits_seq, leaked = [], 0
    thc = st.entities[tid].get_component(HealthComponent)
    # CHEMIN DE PRODUCTION : `Runner.apply(AttackUnitMessage)` -- c'est le handler qui emet le vecteur
    # after-hit `On(9=Attack)` (le CLEAR du flag), pas `AttackDamageOperation.execute` seul.
    runner = Runner(st).install_default_handlers(20)
    for _ in range(args.n):
        thc.hp = 10 ** 9                          # cible immortelle : on ne mesure que le nb de coups
        runner.apply(AttackUnitMessage(attacker_id=aid, target_id=tid))
        r = runner.damage_handler.last
        if r is None:
            break
        hits_seq.append(r["hits"])
        pdc = st.entities[aid].get_component(PersistentDataComponent)
        if pdc is not None and pdc.data:
            leaked += 1
    base = min(hits_seq) if hits_seq else 0
    k = sum(1 for h in hits_seq if h > base)
    print(f"[offline] n={len(hits_seq)} base={base} distinct={sorted(set(hits_seq))} "
          f"base+1={k} -> {100.0*k/max(1,len(hits_seq)):.1f}%")
    print(f"[offline] flags NON effaces apres attaque = {leaked} (attendu 0)")


if __name__ == "__main__":
    main()
