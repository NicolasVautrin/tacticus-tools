#!/usr/bin/env python
"""probe case-ischarging-hits -- MESURE du canal COUPS gate `IsCharging` : `SagaOfTheWarriorBorn_Owner` (1223).

Ce probe ne GARDE rien (le cliquet est `tests/engine/runner/test_ischarging_saga_hits_live.py`).
Il MESURE, regime par regime, le NOMBRE DE COUPS que `spaceBlackmane` <<Ragnar>> porte a sa cible,
live et en rejeu offline :

  * `CHARGE`        -- part a distance 2, arrive AU CONTACT -> `IsCharging` VRAI
                       -> `EffectBonus.ForAddition(OwnerIsCaster & IsCharging, ConfigVar(0x13 =
                          extraHits))` de `IdunBattle.Entities.Effects.Loki.
                          SagaOfTheWarriorBorn_OwnerEffect$$CreateEffectHitsBonusForAttack`.
  * `STEP_ADJACENT` -- part DEJA au contact et se decale -> `IsCharging` FAUX (le flag `Moved` est
                       pourtant VRAI). REGIME DISCRIMINANT : les deux modeles y divergent.
  * `NO_STEP`       -- aucun pas -> TEMOIN, les deux modeles coincident.

Le nombre de coups est l'observable DIRECTE (`len(per_hit)`), pas un scalaire de degat : il est
DISCRET, donc un ecart ne peut pas etre absorbe par du bruit d'armure ou de percage.

Usage (depuis scripts/python, session warmee) :
    python probe_ischarging_saga_hits.py [--seed 777] [--board MC1_67] [--regimes CHARGE,STEP_ADJACENT]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--p-units", default="spaceBlackmane")
    ap.add_argument("--a-units", default="necroOverlord,necroWarden")
    ap.add_argument("--caster", default="spaceBlackmane")
    ap.add_argument("--regimes", default="CHARGE,STEP_ADJACENT,NO_STEP")
    ap.add_argument("--runner", type=int, default=None,
                    help="runnerId deja construit (sinon on en construit un et on le dispose)")
    a = ap.parse_args()

    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness

    sid = R._resolve_session()
    w = _unwrap(R._rpc(sid, "autoBootExtraire", [{}], timeout=180))
    if not (isinstance(w, dict) and w.get("ok")):
        print("[probe] amorce KO : %s" % str(w)[:200])
        return 2

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    owned = False
    rid = a.runner
    state_file = None
    if rid is None:
        fd, state_file = tempfile.mkstemp(prefix="ischarging_saga_", suffix=".json")
        os.close(fd)
        Path(state_file).unlink(missing_ok=True)
        argv = [sys.executable, "rl_duel.py", "build", "--seed", str(a.seed),
                "--state-file", state_file, "--board", a.board,
                "--p-units", a.p_units, "--a-units", a.a_units,
                "--hp-target", "120000", "--hp-player", "120000", "--no-ai"]
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if not Path(state_file).exists():
            print("[probe] build KO : %s" % ((p.stderr or p.stdout or "")[-400:]))
            return 2
        rid = json.loads(Path(state_file).read_text())["runnerId"]
        owned = True
    print("[probe] runner %s (board %s seed %s)" % (rid, a.board, a.seed))

    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        h = ChargeRegimeHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))

        dv = h.dview()
        me = h.by_visual(a.caster, dv)
        if me is None:
            print("[probe] %s absent du build" % a.caster)
            return 2
        print("[probe] caster u%s effets = %s"
              % (me.get("id"), json.dumps(me.get("effects") or [])[:800]))
        print("[probe] caster abilities = %s"
              % json.dumps([(x.get("id"), x.get("kind")) for x in (me.get("abilities") or [])]))

        for regime in [x.strip() for x in a.regimes.split(",") if x.strip()]:
            rec = h.run(caster_visual=a.caster, regime=regime)
            if rec is None:
                print("[%s] geometrie non realisable" % regime)
                continue
            if not rec["live_ok"] or not rec["live_per_hit"]:
                print("[%s] attaque live refusee/vide : %s"
                      % (regime, json.dumps(rec.get("live_raw"))[:300]))
                continue
            off = h.replay_offline(rec)
            # GEOMETRIE : le montage est bati en HEX PUR (`hexgeo.distance == 1`). Le natif, lui,
            # itere `IterateAdjacentTiles` = le champ BRUT `boardGraph.neighbours` (case-r28).
            # Les deux peuvent diverger (connectivite, elevation) -> on DUMPE les deux, sinon une
            # divergence de coups se lit a tort comme un ecart de gate.
            b = h.board
            def _tid(p):
                return b.id_at(p[0], p[1]) if p is not None else None
            def _fmt(label, p):
                t = _tid(p)
                if t is None:
                    return "%s=%s(tid?)" % (label, p)
                return "%s=%s tid=%s elev=%s" % (label, p, t, b.elevation(t))
            t_pos = None
            for u in h.alive():
                if u.get("id") == rec["target"]:
                    pp = u.get("pos") or {}
                    t_pos = (pp.get("col"), pp.get("row"))
            print("[%s] GEO %s | %s | %s" % (regime, _fmt("start", rec["start"]),
                                             _fmt("step_to", rec["step_to"]), _fmt("tgt", t_pos)))
            tt = _tid(t_pos)
            for lbl, p in (("start", rec["start"]), ("step_to", rec["step_to"])):
                s = _tid(p)
                if s is None or tt is None:
                    continue
                print("[%s] GEO %s: native_nb_has_tgt=%s sym_nb_has_tgt=%s"
                      % (regime, lbl, tt in b.neighbours_native(s), tt in b.neighbours(s)))
            print("[%s] endturns=%s trace=%s" % (regime, rec.get("endturns"), rec.get("trace")))
            print("[%s] charged=%s target=%s" % (regime, off["charged"], rec["target"]))
            print("[%s] LIVE    n=%d per_hit=%s" % (regime, len(rec["live_per_hit"]),
                                                    rec["live_per_hit"]))
            print("[%s] OFFLINE n=%d per_hit=%s" % (regime, len(off["per_hit"]), off["per_hit"]))
            print("[%s] VERDICT hits %s | per_hit %s"
                  % (regime,
                     "OK" if len(off["per_hit"]) == len(rec["live_per_hit"]) else "DIVERGE",
                     "OK" if off["per_hit"] == rec["live_per_hit"] else "DIVERGE"))
    finally:
        if owned:
            rpc("disposeRunner", {"runnerId": rid}, 20)
            if state_file:
                Path(state_file).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
