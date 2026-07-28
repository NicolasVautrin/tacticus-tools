#!/usr/bin/env python
"""Probe #204 (volet 2) -- D'OU vient la constante mesuree par `probe_204_ah_channel.py`, et le CAP
`ConfigVar(0xd = maxDmg)` des deux descripteurs MORD-il dans le regime mesure ?

Deux questions, deux mesures :
  1. la constante du coup de groupe == stat ATTACK de l'ATTAQUANT (armure de la cible mise a 0 par
     `--hp-target`) -> on lit `GetStat(Attack)` live ET la valeur portee offline ;
  2. `maxDmg` est une VARIABLE indexee sur le niveau d'ability du PORTEUR (65 paliers, 75 .. 5456) :
     on lit le niveau effectif du porteur dans le runner et la valeur de cap qui en decoule.

ASCII only. Usage : python probe_204_cap_and_stat.py --case astartes|master
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
LOGS = PYDIR.parent.parent / "logs"
SID = None
ATTACKER = "ultraApothecary"
TARGET = "bloodSanguinary"
CASES = {"astartes": ("templAncient", "AstartesBanner"),
         "master": ("admecDominus", "MasterAnnihilator")}


def rpc(method, body, timeout=90):
    r = _rpc(SID, method, body, timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def main():
    global SID
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=sorted(CASES), default="astartes")
    ap.add_argument("--seed", type=int, default=204100)
    args = ap.parse_args()
    carrier, ability = CASES[args.case]
    SID = _resolve_session()
    LOGS.mkdir(parents=True, exist_ok=True)
    state = LOGS / f"_probe204cap_{args.case}.json"

    out = subprocess.run([sys.executable, str(PYDIR / "rl_duel.py"), "build",
                          "--seed", str(args.seed), "--state-file", str(state),
                          "--p-units", f"{carrier},{ATTACKER}", "--a-units", TARGET,
                          "--board", "MC1_67", "--hp-target", "900000",
                          "--hp-player", "900000", "--crit", "0,0", "--block-target", "0,0"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    rid = None
    for ln in (out.stdout or "").splitlines():
        if "runnerId=" in ln:
            rid = int(ln.split("runnerId=")[1].split()[0])
    if rid is None:
        print("[build KO]", (out.stdout or "")[-400:])
        return

    try:
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
        for u in (dv.get("units") or []):
            if u.get("visualId") in (ATTACKER, carrier, TARGET):
                print(f"[dv] {u.get('visualId'):18s} id={u.get('id')} "
                      f"stats={u.get('stats')}")
        # etat porte : stat ATTACK + niveaux d'ability
        from engine.entities.pathfinding.board import Board
        from engine.runner.snapshot import load_state
        from engine.runner.components import UnitComponent, StatsComponent
        from engine.entities.stats import StatType
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        st = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
        for uid, e in st.entities.items():
            uc = e.get_component(UnitComponent)
            sc = e.get_component(StatsComponent)
            if uc is None or uc.visual_id not in (ATTACKER, carrier, TARGET):
                continue
            ctx = sc.ctx if sc is not None else None
            print(f"[port] {uc.visual_id:18s} id={uid} "
                  f"ATTACK={ctx.stat(StatType.ATTACK) if ctx else '?'} "
                  f"ARMOR={ctx.stat(StatType.ARMOR) if ctx else '?'} "
                  f"passive_lvl={getattr(ctx, 'passive_ability_level', None)} "
                  f"active_lvl={getattr(ctx, 'active_ability_level', None)} "
                  f"mult={getattr(ctx, 'ability_variables_multiplier', None)}")
        import gameconfig as GC
        from engine.entities.effects.magnitude import ability_var
        a = GC.ability(ability) or {}
        arr = (a.get("variables") or {}).get("maxDmg") or []
        print(f"\n[cfg] {ability}.maxDmg : {len(arr)} paliers, "
              f"min={arr[0] if arr else '-'} max={arr[-1] if arr else '-'}")
        carrier_ctx = next((e.get_component(StatsComponent).ctx for _u, e in st.entities.items()
                            if e.get_component(UnitComponent) is not None
                            and e.get_component(UnitComponent).visual_id == carrier
                            and e.get_component(StatsComponent) is not None), None)
        lvl = getattr(carrier_ctx, "passive_ability_level", None) if carrier_ctx else None
        mult = int(getattr(carrier_ctx, "ability_variables_multiplier", 100) or 100) \
            if carrier_ctx else 100
        cap = ability_var(ability, "maxDmg", level=lvl, multiplier_pct=mult)
        print(f"[cap] niveau passif du porteur = {lvl} ; multiplier = {mult} "
              f"-> ConfigVar(0xd=maxDmg) = {cap}")
    finally:
        subprocess.run([sys.executable, str(PYDIR / "rl_duel.py"), "dispose",
                        "--runner", str(rid), "--state-file", str(state)],
                       capture_output=True, text=True)


if __name__ == "__main__":
    main()
