#!/usr/bin/env python
"""Probe du RESIDU NOMME de `docs/rl/case-o10-defork-damage-dealt.md` (SS 6) : les PV de la CIBLE
apres une attaque normale de `blackObliterator` (« Volk ») DIVERGENT live/offline.

ATTENTION AU VOCABULAIRE DU RAPPORT D'ORIGINE : `live_hp`/`off_hp` du helper
`tests/engine/runner/_on_hit_tile_effect_replay.py` sont les PV de la **CIBLE** (`tgt_id`), pas
ceux de Volk. « live 2668 / offline 1440 » signifie donc que l'OFFLINE SUR-INFLIGE ~1228 de degat.

MONTAGE = celui du test qui a leve le residu, VERBATIM
(`test_on_fire_damage_migration_live.py::test_on_fire_from_bonus_hit_group_agrees_with_live`) :
seed 777, board MC1_67, `--roster 2 --p-units blackObliterator,adeptHospitaller
--a-units necroWarden,necroWarden`.

CE QUE CE PROBE FAIT EN PLUS DU TEST : il DECOMPOSE PAR ETAGE. Pour chaque attaque confrontee il
imprime les entrees/sorties de chaque etage du vecteur normal
(`IdunBattle.Operations.AttackDamageOperation$$Execute` -> `ExecuteHits` -> `ExecuteHit`) telles que
le port les rend dans `AttackDamageOperation.execute` :

    base (stat ATTACK) | pierce | armor | hits (GetAttackHits) | clean_min/clean_max (bornes reduites
    x hits) | rolls (tirages MT bruts) | per_hit | additional_hits (canal #179) | effects actifs

... face aux memes grandeurs cote LIVE quand un capteur les expose. Le but est de trouver le PREMIER
etage ou natif != port -- JAMAIS un ratio.

Usage : python probe_o10_volk_hp_residual.py [--seed 777] [--board MC1_67] [--max-attacks 9]
ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc            # noqa: E402
from engine.entities.pathfinding.board import Board            # noqa: E402
from engine.runner.components import (HealthComponent, PositionComponent,   # noqa: E402
                                      StatsComponent)
from engine.runner.messages import AttackUnitMessage           # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister         # noqa: E402
from engine.runner.runner import Runner                        # noqa: E402
from engine.runner.snapshot import load_state                  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent / "tests" / "engine" / "runner"))
from _on_hit_tile_effect_replay import drive_to_firing_position   # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_o10_volk_hp_state.json"

CARRIER = "blackObliterator"
P_UNITS = "blackObliterator,adeptHospitaller"
A_UNITS = "necroWarden,necroWarden"


def _r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt, rng.mti = list(s["mt"]), s["mti"]
    return rng


def build(seed, board):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", board, "--roster", "2",
         "--p-units", P_UNITS, "--a-units", A_UNITS],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("[o10-volk] build KO: %s" % ((proc.stderr or proc.stdout or "")[-600:],))
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def _fmt_stage(tag, last):
    if not last:
        return "%s <aucun attack dict>" % tag
    ah = last.get("additional_hits")
    ahs = "None"
    if isinstance(ah, dict):
        ahs = ", ".join("%s=%r" % (k, v) for k, v in sorted(ah.items()) if k != "death")
    return ("%s base=%s pierce=%s armor=%s hits=%s clean=[%s,%s] total=%s per_hit=%s "
            "crits=%s block=%s rolls=%s addhits=(%s) profile=%s ranged=%s" % (
                tag, last.get("base"), last.get("pierce"), last.get("armor"), last.get("hits"),
                last.get("clean_min"), last.get("clean_max"), last.get("total"),
                last.get("per_hit"), last.get("crits"), last.get("did_block"),
                last.get("rolls"), ahs, last.get("profile"), last.get("ranged")))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--max-attacks", type=int, default=9)
    args = ap.parse_args(argv)

    sid = _resolve_session()
    rid = build(args.seed, args.board)
    rpc = lambda m, b, t=90: _r(sid, m, b, t)          # noqa: E731
    print("[o10-volk] sid=%s runner=%s seed=%s board=%s" % (sid, rid, args.seed, args.board))
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            print("[o10-volk] boardGraph KO"); return 2
        board = Board(bg["tiles"], adjacency="evenq")

        n_conf = 0
        for it in range(args.max_attacks):
            drive = drive_to_firing_position(rpc, rid, board, CARRIER)
            if drive is None:
                print("[o10-volk] plus de position de tir (it=%d)" % it)
                break
            me_id, tgt_id, norm_id = drive

            dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            ob = rpc("observeBattle", {"runnerId": rid}, 60)
            snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
            s1 = rpc("dumpRng", {"runnerId": rid}, 30)
            if not _ok(s1):
                print("[o10-volk] dumpRng KO"); break
            state = load_state(dv, ob, snap, board=board)
            state.rng = _seed_rng(s1)

            me = next((u for u in (dv.get("units") or []) if u.get("id") == me_id), {})
            tg = next((u for u in (dv.get("units") or []) if u.get("id") == tgt_id), {})
            pos_a = state.get_entity(me_id).get_component(PositionComponent)
            pos_t = state.get_entity(tgt_id).get_component(PositionComponent)
            sc_a = state.get_entity(me_id).get_component(StatsComponent)
            hp_t0 = state.get_entity(tgt_id).get_component(HealthComponent).hp
            print("\n[o10-volk] --- attaque %d : u%s(%s) -> u%s(%s)" % (
                it, me_id, me.get("visualId"), tgt_id, tg.get("visualId")))
            print("[o10-volk]   pos att=(%s,%s) tgt=(%s,%s) hp_tgt_avant=%s mti=%s" % (
                getattr(pos_a, "col", None), getattr(pos_a, "row", None),
                getattr(pos_t, "col", None), getattr(pos_t, "row", None), hp_t0, s1["mti"]))
            print("[o10-volk]   effets att LIVE=%s" % (
                [e.get("name") for e in (me.get("effects") or [])],))
            print("[o10-volk]   effets tgt LIVE=%s" % (
                [e.get("name") for e in (tg.get("effects") or [])],))

            rpc("hitTraceReset", {"runnerId": rid}, 20)
            rpc("hitTraceArm", {"runnerId": rid}, 30)
            res = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": me_id, "targetId": tgt_id,
                "abilityType": norm_id}}, 60)
            ht = rpc("hitTrace", {"runnerId": rid, "limit": 60}, 30)
            if not (_ok(res) and (res.get("actions") or [{}])[0].get("ok")):
                print("[o10-volk]   applyAction KO -> endturn")
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            live_hp = next((u.get("hp") for u in (res.get("units") or [])
                            if u.get("squadId") == tgt_id), None)
            s2 = rpc("dumpRng", {"runnerId": rid}, 30)
            live_mt = (list(s2["mt"]), s2["mti"]) if _ok(s2) else None
            if live_mt is not None and live_mt[1] == s1["mti"] and live_mt[0] == list(s1["mt"]):
                print("[o10-volk]   NOOP live (MT inchange) -> ignore")
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue

            runner = Runner(state).install_default_handlers(20)
            runner.apply(AttackUnitMessage(me_id, tgt_id))
            off_hp = state.get_entity(tgt_id).get_component(HealthComponent).hp
            last = runner.damage_handler.last or {}

            print("[o10-volk]   LIVE hp=%s (degat=%s) | OFFLINE hp=%s (degat=%s) | DELTA=%s" % (
                live_hp, (hp_t0 - live_hp) if live_hp is not None else None,
                off_hp, hp_t0 - off_hp,
                (off_hp - live_hp) if live_hp is not None else None))
            print("[o10-volk]   " + _fmt_stage("ETAGES OFF", last))
            # --- ETAGE `GetAttackHits` cote LIVE : la SEQUENCE de coups a la source
            # (`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`, hook hit-trace).
            lh = [h for h in (ht.get("hits") or [])] if isinstance(ht, dict) else []
            print("[o10-volk]   LIVE coups=%d (fires=%s) seq=%s" % (
                len(lh), (ht or {}).get("fires"),
                [(h.get("hitIndex"), h.get("profile")) for h in lh]))
            off_seq = ([(i, last.get("profile")) for i in range(last.get("hits") or 0)]
                       + [("ah", p) for p in
                          ((last.get("additional_hits") or {}).get("profiles") or [])])
            print("[o10-volk]   OFF  coups=%s (arme=%s + add=%s) profils=%s" % (
                (last.get("hits") or 0) + ((last.get("additional_hits") or {}).get("hits") or 0),
                last.get("hits"), (last.get("additional_hits") or {}).get("hits"), off_seq))
            # --- EVENTS live (degat par coup si le runner les expose)
            evs = res.get("events") or []
            dmg_ev = [e for e in evs if "amage" in str(e.get("type", ""))]
            print("[o10-volk]   LIVE events=%d dont degat=%d : %s" % (
                len(evs), len(dmg_ev), json.dumps(dmg_ev[:14])[:900]))
            print("[o10-volk]   mti off=%s live=%s mt_same=%s" % (
                state.rng.mti, live_mt[1] if live_mt else None,
                (list(state.rng.mt), state.rng.mti) == (live_mt[0], live_mt[1]) if live_mt else None))
            print("[o10-volk]   stat ATTACK off=%s ; effets OFF=%s" % (
                sc_a.ctx.stat(__import__("engine.entities.stats", fromlist=["StatType"]).StatType.ATTACK)
                if sc_a else None, last.get("effects")))
            n_conf += 1

            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

        print("\n[o10-volk] confrontations=%d" % n_conf)
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 15)
            print("[o10-volk] runner %s dispose" % rid)
        except Exception as e:
            print("[o10-volk] dispose KO: %s" % e)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
