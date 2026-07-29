#!/usr/bin/env python
"""probe #230 -- le SEED par `load_state` des deux champs d'ETAT DE TOUR du `UnitComponent`.

MESURE (ce probe ne garde rien -- le cliquet vit dans
`tests/engine/runner/test_load_state_turn_state_live.py`) :

  * `--case charge` : monte les regimes `CHARGE` et `STEP_ADJACENT` (fixture `_charge_regime`),
    capture MI-ACTIVATION (apres le pas, avant `FinishUnitTurn` -- le SEUL instant ou
    `UnitComponent.ChargedUnitIds@+0x190` est non vide) et compare TROIS colonnes :
       live                          = les degats du natif ;
       off(mid, seede)               = rejeu depuis la capture mi-activation AVEC le cablage #230 ;
       off(mid, NON seede)           = le meme rejeu avec les deux champs effaces = l'etat d'AVANT.
    Le regime `CHARGE` est le discriminant : sans le seed, l'offline OMET le +extraDmg
    (degradation RESTRICTIVE, `case-r32` SS 7).

  * `--case ghost` : `thousTerminator` (Toth). Lit `currentTurnStartTile` dans le
    `combatSnapshot` brut, verifie que `load_state` le pose, puis joue le PREMIER move offline
    et regarde sur quelle tuile atterrit le time-ghost (effet 1186) -- SANS rejouer de
    `StartTurnOperation` (le contournement que le cablage doit rendre inutile).

Usage (depuis scripts/python, session warmee) :
    python probe_230_load_state_turn_state.py --case charge
    python probe_230_load_state_turn_state.py --case ghost

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

HOST = "http://127.0.0.1:8765"
PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))


def _http(path, method="GET", body=None, timeout=120.0):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(HOST + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def session_id():
    return int((_http("/api/admin/status").get("session") or {}).get("id"))


def make_rpc(sid):
    def _call(method, body=None, timeout=60):
        out = _http("/api/scripts/%d/rpc" % sid, "POST",
                    {"method": method, "args": [body] if body is not None else [],
                     "timeout": int(timeout * 1000)}, timeout + 20)
        return out.get("result")
    return _call


def build(seed, board, extra):
    """`rl_duel build` dans un state-file PROPRE sous logs/ (jamais data/, qui est versionne)."""
    state = ROOT / "logs" / ("_probe230-%d.json" % os.getpid())
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", str(state), *extra]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise SystemExit("build KO: %s" % ((p.stderr or p.stdout or "")[-400:]))
    return int(json.loads(state.read_text())["runnerId"]), state


# --------------------------------------------------------------------------- case charge

def case_charge(rpc):
    from _charge_regime import ChargeRegimeHarness, CHARGE, STEP_ADJACENT
    from engine.entities.pathfinding.board import Board

    rid, state = build("777", "MC1_67",
                       ["--p-units", "astraBullgryn", "--a-units", "necroOverlord,necroWarden",
                        "--hp-target", "120000", "--hp-player", "120000", "--no-ai"])
    print("[build] runner=%d" % rid)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    h = ChargeRegimeHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
    try:
        for regime in (CHARGE, STEP_ADJACENT):
            rec = h.run(caster_visual="astraBullgryn", regime=regime, capture_mid=True)
            if rec is None:
                print("[%s] geometrie non realisable" % regime)
                continue
            caster, target = rec["caster"], rec["target"]
            raw = next((u for u in (rec["snapshot_mid"]["snap"].get("units") or [])
                        if u.get("entityId") == caster), {})
            print("\n=== %s (caster=%s target=%s) ===" % (regime, caster, target))
            print("  [hook mi-activation] chargedUnitIds=%s currentTurnStartTile=%s"
                  % (raw.get("chargedUnitIds"), raw.get("currentTurnStartTile")))
            off_pre = h.replay_offline(rec)                       # voie historique (rejeu du pas)
            off_mid = h.replay_offline_mid(rec, seeded=True)      # voie #230 (seed)
            off_old = h.replay_offline_mid(rec, seeded=False)     # etat d'AVANT #230
            print("  live                 = %s" % rec["live_per_hit"])
            print("  off(pre-pas, rejeu)  = %s  charged=%s" % (off_pre["per_hit"], off_pre["charged"]))
            print("  off(mid, seede)      = %s  charged=%s" % (off_mid["per_hit"], off_mid["charged"]))
            print("  off(mid, NON seede)  = %s  charged=%s" % (off_old["per_hit"], off_old["charged"]))
            d_new = [o - l for l, o in zip(rec["live_per_hit"], off_mid["per_hit"])]
            d_old = [o - l for l, o in zip(rec["live_per_hit"], off_old["per_hit"])]
            print("  delta/coup seede=%s  NON seede=%s" % (d_new, d_old))
            print("  VERDICT seede=%s  NON seede=%s"
                  % ("EXACT" if off_mid["per_hit"] == rec["live_per_hit"] else "DIVERGE",
                     "EXACT" if off_old["per_hit"] == rec["live_per_hit"] else "DIVERGE"))
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        state.unlink(missing_ok=True)


# --------------------------------------------------------------------------- case ghost

def case_ghost(rpc):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.components import UnitComponent, PositionComponent
    from engine.runner.events import EventBus
    from engine.runner.operations.movement import MoveUnitOperation
    from engine.runner.operations.triggers import after_move_triggers
    from engine.runner.operations.triggers.loki.ghost_revive import GHOST_EFFECT
    from engine.runner.prng import IntBasedMersenneTwister

    rid, state = build("31337", "MC1_67",
                       ["--p-units", "thousTerminator", "--a-units", "astraBullgryn,orksNob",
                        "--hp-player", "12000", "--no-ai"])
    print("[build] runner=%d" % rid)
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        tm = rpc("tileMeta", {"runnerId": rid}, 90)
        print("[live] currentPlayer=%s" % dv.get("currentPlayer"))
        for u in (snap.get("units") or []):
            print("  snap entity=%-5s startTile=%-6s charged=%s"
                  % (u.get("entityId"), u.get("currentTurnStartTile"), u.get("chargedUnitIds")))
        td = next((u for u in (dv.get("units") or []) if u.get("visualId") == "thousTerminator"), None)
        if td is None:
            raise SystemExit("Toth absent")
        tid = int(td["id"])
        st = load_state(dv, ob, snap, board=board, tiles=tm)
        st.rng = IntBasedMersenneTwister(12345)
        uc = st.get_entity(tid).get_component(UnitComponent)
        pc = st.get_entity(tid).get_component(PositionComponent)
        start = (int(pc.col), int(pc.row))          # LU AVANT le move (le composant est mute en place)
        here = board.id_at(*start)
        print("[port] toth=%s pos=(%s,%s) tile=%s current_turn_start_tile=%s (attendu %s)"
              % (tid, pc.col, pc.row, here, uc.current_turn_start_tile, here))
        # PREMIER move apres chargement, SANS rejouer de StartTurnOperation.
        occupied = {(e.get_component(PositionComponent).col, e.get_component(PositionComponent).row)
                    for k, e in st.entities.items()
                    if e.get_component(PositionComponent) is not None and k != tid}
        dest = None
        for n in board.neighbours(here):
            c = board.coord(n)
            if board.walkable(n) and (int(c[0]), int(c[1])) not in occupied:
                dest = (int(c[0]), int(c[1]))
                break
        if dest is None:
            raise SystemExit("aucune tuile voisine libre")
        MoveUnitOperation(tid, dest).execute(st, EventBus())
        after_move_triggers(st, tid)
        ghosts = sorted(int(t) for t, effs in st.effects.by_unit.items()
                        if int(t) in board.by_id
                        and any((not e.consumed) and e.effect_type == GHOST_EFFECT for e in effs))
        print("[port] move %s -> %s ; tuiles portant le ghost 1186 = %s (attendu [%s])"
              % (start, dest, ghosts, here))
        print("  VERDICT ghost = %s" % ("BONNE TUILE" if ghosts == [here] else "KO"))
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        state.unlink(missing_ok=True)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=("charge", "ghost"), required=True)
    a = ap.parse_args(argv)
    rpc = make_rpc(session_id())
    (case_charge if a.case == "charge" else case_ghost)(rpc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
