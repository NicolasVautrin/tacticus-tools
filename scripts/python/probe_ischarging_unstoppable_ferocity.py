#!/usr/bin/env python
"""probe N16 -- MESURE du canal COUPS gate `IsCharging` sur `UnstoppableFerocity_OwnerEffect` (1032).

Jumeau de `probe_ischarging_saga_hits.py`, mais le porteur n'est PAS un hero du pool : c'est le
SUMMON `blackSmnBloodletter`, amene en bataille par l'ACTIVE `Incursion` (1021) de son summoner
`blackPossession` <<Archimatos>> (lui, dans `rl_duel.py --list-pool`).

POSTURE : **on OBSERVE l'IA jouer le summon**, on ne le pilote pas -- un summon n'a pas d'activation
qu'on puisse declencher (`applyAction {kind:"ability"}` rend `mutated=False`). Le detail mesure de
ce blocage, les deux pieges de roster et la forme des `changes` vivent dans
`tests/engine/runner/_bloodletter_montage.py`. Ici on enchaine, PAR REGIME et sur un runner FRAIS :

  1. cast `Incursion` -> le Bloodletter apparait AU CONTACT de la cible et frappe on-appearance,
     SANS aucun `MoveUnitOperation` -> `IsCharging` FAUX. C'est le TEMOIN, et ses coups sont
     publies event par event (mesure exacte, pas une borne).
  2. on POSE la geometrie du regime, on SNAPSHOTe, puis `applyAction endturn` : l'IA auto-active le
     summon (il approche et frappe). On lit les `changes` : pas du caster + `hpDelta` de la cible.
  3. on REJOUE offline le meme pas puis la meme attaque, DEUX fois : avec l'effet 1032 et sans lui
     (`force_no_charge`). Le `hpDelta` live doit tomber dans la bande de l'UN et pas de l'AUTRE.

REGIMES :
  * `CHARGE`   -- caster pose a distance 2 ; c'est l'IA qui l'amene AU CONTACT -> `IsCharging` VRAI.
  * `ADJACENT` -- caster pose DEJA au contact, cible amenee EN DERNIER (donc c'est SA liste
                  `ChargedUnitIds` qui s'ecrit, pas celle du caster) -> `IsCharging` FAUX alors que
                  le caster a bel et bien BOUGE. REGIME DISCRIMINANT.

L'observable est le NOMBRE DE COUPS, DISCRET : l'arme du Bloodletter porte **1 coup**, donc
1 -> 2 est un doublement, hors de portee de tout bruit d'armure ou de percage.

Usage (depuis scripts/python, session warmee) :
    python probe_ischarging_unstoppable_ferocity.py [--seed 1357] [--board MC1_67]

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
    ap.add_argument("--seed", default="1357")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--a-units", default=None)
    ap.add_argument("--enemy", default=None, help="cible du cast Incursion")
    ap.add_argument("--regimes", default="CHARGE,ADJACENT")
    a = ap.parse_args()

    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from _bloodletter_montage import (EFFECT_NAME, SAFE_ENEMIES, SAFE_TARGET, SUMMONER, SUMMON_VIS,
                                      BloodletterHarness, on_appearance_hits,
                                      replay_attack_offline, summon_bloodletters)

    a_units = a.a_units or SAFE_ENEMIES
    enemy = a.enemy or SAFE_TARGET

    sid = R._resolve_session()
    w = _unwrap(R._rpc(sid, "autoBootExtraire", [{}], timeout=180))
    if not (isinstance(w, dict) and w.get("ok")):
        print("[probe] amorce KO : %s" % str(w)[:200])
        return 2

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    def build():
        fd, sf = tempfile.mkstemp(prefix="ischarging_unstopferoc_", suffix=".json")
        os.close(fd)
        Path(sf).unlink(missing_ok=True)
        argv = [sys.executable, "rl_duel.py", "build", "--seed", str(a.seed),
                "--state-file", sf, "--board", a.board,
                "--p-units", SUMMONER, "--a-units", a_units,
                "--hp-target", "120000", "--hp-player", "120000"]
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if not Path(sf).exists():
            return None, (p.stderr or p.stdout or "")[-400:]
        rid = json.loads(Path(sf).read_text())["runnerId"]
        Path(sf).unlink(missing_ok=True)
        return rid, None

    # UN RUNNER PAR REGIME (cf. `BloodletterHarness` : aucun FinishUnitTurn entre deux poses, et
    # `UpdateCharging` AJOUTE sans jamais vider).
    for regime in [x.strip().upper() for x in a.regimes.split(",") if x.strip()]:
        rid, err = build()
        if rid is None:
            print("[%s] build KO : %s" % (regime, err))
            continue
        print("[%s] runner %s (board %s seed %s enemies %s)"
              % (regime, rid, a.board, a.seed, a_units), flush=True)
        try:
            board = Board(rpc("boardGraph", {"runnerId": rid}, 60)["tiles"],
                          adjacency="native_sym")
            s, err = summon_bloodletters(rpc, rid, enemy)
            if err:
                print("[%s] MONTAGE SUMMON KO : %s" % (regime, err))
                continue
            h = BloodletterHarness(rpc, rid, board)
            smn = [u for u in s["new"] if u.get("visualId") == SUMMON_VIS]
            bid = smn[0]["id"]
            tid = s["target_id"]
            h.my_player = smn[0].get("owner")
            print("[%s] summon u%s effets=%s"
                  % (regime, bid,
                     json.dumps([e.get("name") for e in (smn[0].get("effects") or [])])),
                  flush=True)
            print("[%s] TEMOIN on-appearance (adjacent, AUCUN pas) : %s"
                  % (regime, on_appearance_hits(s["cast"], [bid], tid)), flush=True)

            plan = h.arrange_regime(bid, tid, regime)
            if plan is None:
                print("[%s] geometrie non realisable (summon vivant=%s) trace=%s"
                      % (regime, any(u["id"] == bid for u in h.alive()), h.trace[:10]))
                continue
            print("[%s] geo posee : caster=%s tgt=%s dist=%s | trace=%s"
                  % (regime, plan["caster_pos"], plan["target_pos"], plan["dist"], h.trace),
                  flush=True)
            snap = h.snapshot()
            obs = h.observe_endturn(bid, tid)
            print("[%s] endturn : caster %s -> %s (moved=%s) | cible hp %s -> %s (delta=%s)"
                  % (regime, obs["caster_from"], obs["caster_to"], obs["caster_moved"],
                     obs["target_hp_before"], obs["target_hp_after"], obs["target_delta"]),
                  flush=True)
            if not obs["target_delta"]:
                print("[%s] l'IA n'a pas attaque -- changes=%s"
                      % (regime, json.dumps(obs["changes"])[:400]))
                continue
            mv = obs["caster_to"] if obs["caster_moved"] else None
            with_eff = replay_attack_offline(snap, board, bid, tid, move_to=mv)
            without = replay_attack_offline(snap, board, bid, tid, move_to=mv,
                                            force_no_charge=True)
            print("[%s] OFFLINE effet %s present=%s charged=%s"
                  % (regime, EFFECT_NAME, with_eff["effect_present"], with_eff["charged"]),
                  flush=True)

            for lbl, o in (("off+1032", with_eff), ("off-1032", without)):
                print("[%s] %s : n=%d per_hit=%s total=%s"
                      % (regime, lbl, len(o["per_hit"]), o["per_hit"], o["total"]), flush=True)
            # Le MT est recale sur le dump PRE-`endturn` et le pas ne consomme pas de tirage :
            # la confrontation est BIT-EXACTE sur le total, pas seulement encadrante.
            d = obs["target_delta"]
            print("[%s] VERDICT live delta=%s | off+1032 total=%s (%s) | off-1032 total=%s (%s)"
                  % (regime, d, with_eff["total"],
                     "MATCH" if with_eff["total"] == d else "DIVERGE",
                     without["total"],
                     "MATCH" if without["total"] == d else "DIVERGE"), flush=True)
        finally:
            rpc("disposeRunner", {"runnerId": rid}, 20)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
