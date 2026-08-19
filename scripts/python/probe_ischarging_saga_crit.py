#!/usr/bin/env python
"""probe case-ischarging-crit-channel -- MESURE du canal CRIT gate `IsCharging` (residu `N14`).

Ce probe ne GARDE rien (le cliquet est `tests/engine/runner/test_ischarging_saga_crit_live.py`).
Il MESURE, regime par regime, le degat PER-COUP que `spaceBlackmane` <<Ragnar>> inflige, en LIVE et
en rejeu offline, avec le crit FORCE (`--crit 100,700`) pour rendre la face CRIT observable :

  * `CHARGE`        -- part a distance 2, arrive AU CONTACT -> `IsCharging` VRAI -> le natif ajoute
                       `ConfigVar(0x42 = extraCritDmg)` au `GetStat(10)` du coup
                       (`IdunBattle.Entities.Effects.Loki.SagaOfTheWarriorBorn_OwnerEffect$$CreateCritDamageBonus`).
  * `STEP_ADJACENT` -- part DEJA au contact et se decale -> `IsCharging` FAUX alors que le flag
                       `UnitFlag.Moved` est VRAI. REGIME DISCRIMINANT du gate.
  * `NO_STEP`       -- aucun pas -> TEMOIN.

QUATRE COLONNES, pas deux. `shipped` seul ne prouverait rien : un match pourrait signifier « le
canal est eteint des deux cotes ». Les deux bornes FORCEES tranchent :

  * `off`    -- la face CRIT desactivee (= l'etat PRE-FIX) ;
  * `always` -- le gate court-circuite (bonus INCONDITIONNEL = la regression que `N14` redoutait).

Le probe COMPTE aussi les appels reels de la face (parade au « canal branche, jamais emprunte »).

Usage (depuis scripts/python, session DEJA warmee) :
    python probe_ischarging_saga_crit.py [--seed 777] [--board MC1_67] [--regimes CHARGE,NO_STEP]
    python probe_ischarging_saga_crit.py --amorce      # si (et seulement si) la session est FROIDE

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


@contextmanager
def _crit_face(mode):
    """Court-circuite le GATE de la face CRIT de 1223 -- et RIEN d'autre (ni magnitude, ni canal).
    `off` = jamais de contribution (etat PRE-FIX) ; `always` = contribution inconditionnelle ;
    `count` = livre, mais on TRACE chaque appel `(is_charging_recu, contribution)`."""
    from engine.entities.effects.loki.hits import SagaOfTheWarriorBornOwnerEffect as C
    orig = C.create_effect_crit_damage_bonus_for_attack
    calls = []
    if mode == "off":
        def patched(self, att_ctx=None):
            return None
    elif mode == "always":
        def patched(self, att_ctx=None):
            return orig(self, {"is_charging": True})
    else:
        def patched(self, att_ctx=None):
            out = orig(self, att_ctx)
            calls.append(((att_ctx or {}).get("is_charging"), out))
            return out
    C.create_effect_crit_damage_bonus_for_attack = patched
    try:
        yield calls
    finally:
        C.create_effect_crit_damage_bonus_for_attack = orig


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--p-units", default="spaceBlackmane")
    ap.add_argument("--a-units", default="necroOverlord,necroWarden")
    ap.add_argument("--caster", default="spaceBlackmane")
    ap.add_argument("--crit", default="100,700",
                    help="CritChance,CritDamage forces sur les p-units (le crit d'un heros vient "
                         "de ses items I_Crit, absents d'un build frais)")
    ap.add_argument("--regimes", default="CHARGE,STEP_ADJACENT,NO_STEP")
    ap.add_argument("--amorce", action="store_true",
                    help="amorce la session AVANT (a n'utiliser que si elle est FROIDE : "
                         "un `already-ready` est un STOP, pas un re-amorce)")
    ap.add_argument("--runner", type=int, default=None,
                    help="runnerId deja construit (sinon on en construit un et on le dispose)")
    a = ap.parse_args()

    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness

    sid = R._resolve_session()
    if a.amorce:
        w = _unwrap(R._rpc(sid, "autoBootExtraire", [{"force": True}], timeout=180))
        if not (isinstance(w, dict) and w.get("ok")):
            print("[probe] amorce KO : %s" % str(w)[:200])
            return 2

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    owned = False
    rid = a.runner
    state_file = None
    if rid is None:
        fd, state_file = tempfile.mkstemp(prefix="ischarging_sagacrit_", suffix=".json")
        os.close(fd)
        Path(state_file).unlink(missing_ok=True)
        argv = [sys.executable, "rl_duel.py", "build", "--seed", str(a.seed),
                "--state-file", state_file, "--board", a.board,
                "--p-units", a.p_units, "--a-units", a.a_units,
                "--hp-target", "120000", "--hp-player", "120000", "--no-ai",
                "--crit", a.crit]
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if not Path(state_file).exists():
            print("[probe] build KO : %s" % ((p.stderr or p.stdout or "")[-400:]))
            return 2
        rid = json.loads(Path(state_file).read_text())["runnerId"]
        owned = True
    print("[probe] runner %s (board %s seed %s crit %s)" % (rid, a.board, a.seed, a.crit))

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

        for regime in [x.strip() for x in a.regimes.split(",") if x.strip()]:
            rec = h.run(caster_visual=a.caster, regime=regime)
            if rec is None:
                print("[%s] geometrie non realisable" % regime)
                continue
            if not rec["live_ok"] or not rec["live_per_hit"]:
                print("[%s] attaque live refusee/vide : %s"
                      % (regime, json.dumps(rec.get("live_raw"))[:300]))
                continue
            with _crit_face("count") as calls:
                shipped = h.replay_offline(rec)
            with _crit_face("off"):
                off = h.replay_offline(rec)
            with _crit_face("always"):
                always = h.replay_offline(rec)
            print("[%s] trace=%s charged=%s target=%s"
                  % (regime, rec.get("trace"), shipped["charged"], rec["target"]))
            print("[%s] face CRIT : %d appel(s) %s"
                  % (regime, len(calls), calls if calls else "-- CANAL MORT"))
            print("[%s] live     n=%d %s" % (regime, len(rec["live_per_hit"]), rec["live_per_hit"]))
            for lbl, res in (("shipped ", shipped), ("off     ", off), ("always  ", always)):
                print("[%s] %s n=%d %s  %s"
                      % (regime, lbl, len(res["per_hit"]), res["per_hit"],
                         "OK" if res["per_hit"] == rec["live_per_hit"] else "MISMATCH"))
            disc = (off["per_hit"] != rec["live_per_hit"]) or (always["per_hit"] != rec["live_per_hit"])
            print("[%s] VERDICT shipped=%s (discriminant: %s)"
                  % (regime, "OK" if shipped["per_hit"] == rec["live_per_hit"] else "MISMATCH",
                     "oui" if disc else "NON -- le montage ne prouve rien"))
    finally:
        if owned:
            rpc("disposeRunner", {"runnerId": rid}, 20)
            if state_file:
                Path(state_file).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
