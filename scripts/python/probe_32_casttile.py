#!/usr/bin/env python
"""Probe #32 : diagnostic cast-tile (miss pos-downstream-of-ability) — generique.

Pour un (seed, stop, uid) donne : walk natif jusqu'au pas stop, puis
  1. chunk natif au pas (move+ability+target attendus) ;
  2. sweep MOTEUR par-tuile : pour chaque (ability,target) des attackPlans, u/u_full a
     CHAQUE tuile ranked (mirror exact de _best_attack, sans argmax) ;
  3. pairUtility NATIF (= u sans Tile7) aux tuiles d'interet ;
  4. L3 utility_score natif filtre (unite, tuiles d'interet) -> par-feuille Tile7.

Usage: python probe_32_casttile.py --seed 31337 --stop 5 --uid 81 --tiles "3,5;3,6"
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("ENGINE_DEBUG", "1")   # AVANT import engine_validate (module-level _DEBUG)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import host_inputs  # noqa: E402  (#273 : entrees gitignorees, resolution tri-etat)
import engine_validate as EV  # noqa: E402
from engine.playbook import scene as scene_mod  # noqa: E402
from engine import weights as W  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_32ct_state.json"
# #273 : ecrites par le HOST dans SON arbre, et `frida/data/` est gitignore --
# `ROOT / "frida" / "data" / "ai-traces"` resolvait dans le vide en worktree, et
# `Path.glob` y rendait [] SANS lever (le probe accusait alors la capture L3).
TRACES = "frida/data/ai-traces"


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def _sweep_engine(ctx, tiles_of_interest) -> None:
    """Mirror de ComparableAbilityGenerator._best_attack SANS argmax : imprime chaque
    (ability, target, tile) -> (u, u_full). Marque les tuiles d'interet."""
    from engine.playbook import get_playbook_or_default
    from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK
    from engine.playbook import noncomparable as playbooks
    plan = ctx.plans.get(ctx.uid) or {}
    for ev in (plan.get("evals") or []):
        if not ev.get("rankCount"):
            continue
        ranked = ev.get("ranked") or []
        if not ranked:
            continue
        tgt, ab = ev.get("targetId"), ev.get("abilityId")
        if playbooks.is_noncomp(ab):
            print(f"[32] eng ab={ab} tgt={tgt}: NonComparable (skip tier Comparable)")
            continue
        pb = NORMAL_ATTACK_PLAYBOOK if ab in ctx.normal_ids else get_playbook_or_default(ab)
        rows = []
        for rk in ranked:
            tile = (rk.get("col"), rk.get("row"))
            if tile[0] is None:
                continue
            cand = pb.calculate_action_utility(ctx, tile, tgt, ab)
            if cand is None:
                rows.append((tile, None, None))
                continue
            rows.append((tile, round(cand["u"], 4), round(cand["u_full"], 4)))
        print(f"[32] eng ab={ab} tgt={tgt} normal={ab in ctx.normal_ids} "
              f"(ordre = ranked natif):")
        for tile, u, uf in rows:
            mark = " <== INTERET" if tile in tiles_of_interest else ""
            print(f"      tile={tile} u={u} u_full={uf}{mark}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", required=True)
    ap.add_argument("--stop", type=int, required=True)
    ap.add_argument("--uid", type=int, required=True)
    ap.add_argument("--tiles", default="", help='ex. "3,5;3,6"')
    ap.add_argument("--board", default="MC1_67")
    args = ap.parse_args()
    tiles = set()
    for part in (args.tiles.split(";") if args.tiles else []):
        c, r = part.split(",")
        tiles.add((int(c), int(r)))

    sid = _resolve_session()
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", args.seed,
         "--state-file", str(STATE), "--board", args.board],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[32] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        return 2
    rid = json.loads(STATE.read_text())["runnerId"]
    print(f"[32] runner={rid} seed={args.seed} -> walk s{args.stop}")
    try:
        rpc = lambda m, b, t=60: _r(sid, m, b, t)   # noqa: E731
        predictor = scene_mod.build_predictor(rpc, rid)   # COLD comme run_agreement
        wt = W.load()
        for step in range(args.stop):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[32] natif epuise au pas {step}")
                return 3
            acts = []
            for m in (dry["action"]["messages"] or []):
                if m.get("cls") == "MoveUnitMessage":
                    acts.append({"kind": "move", "unitId": m["unitId"],
                                 "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
                elif m.get("cls") == "ActiveAbilityMessage":
                    acts.append({"kind": "ability", "casterId": m["casterId"],
                                 "targetId": m.get("targetId"),
                                 "abilityType": m["abilityType"]})
                elif m.get("cls") == "FinishUnitTurnMessage":
                    acts.append({"kind": "finish", "unitId": m["unitId"]})
            if acts:
                _r(sid, "applyAction", {"runnerId": rid, "actions": acts}, 60)

        # 1. chunk natif au pas stop (dry, non applique)
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 90)
        chunk = EV.native_chunk(dry.get("action") or {})
        print(f"[32] NATIF s{args.stop}: {json.dumps(chunk, default=str)}")
        nat_ab = (chunk.get("ability") or {}).get("ability")
        nat_tgt = (chunk.get("ability") or {}).get("target")

        # 2. sweep moteur par-tuile
        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
        if predictor is not None:
            scene_mod.refresh_shields(predictor, rpc, rid)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        uname = next((u.get("name") for u in (dv.get("units") or [])
                      if u.get("id") == args.uid), None)
        print(f"[32] uid={args.uid} name={uname}")
        from engine.ai import context as _ai_ctx
        ctx = _ai_ctx.build(rpc, rid, dv, mov_by_unit, args.uid, wt, predictor, debug=False)
        _sweep_engine(ctx, tiles)
        eng = EV.engine_decide(sid, rid, dv, mov_by_unit, args.uid, wt, predictor)
        print(f"[32] engine_decide(u{args.uid}) -> {eng}")

        # 3. pairUtility natif aux tuiles d'interet (ability/target du chunk natif)
        if nat_ab is not None and nat_tgt is not None:
            for (c, r) in sorted(tiles):
                pu = _r(sid, "pairUtility", {"runnerId": rid, "unitId": args.uid,
                                             "targetId": nat_tgt, "abilityType": nat_ab,
                                             "col": c, "row": r}, 60)
                print(f"[32] NATIF pairUtility (ab={nat_ab},tgt={nat_tgt})@({c},{r}) "
                      f"= {pu.get('utility')}")

        # 4. L3 par-feuille sur les tuiles d'interet
        _rpc(sid, "aiTraceEnable", ["L3"], timeout=20)
        lo = (_rpc(sid, "aiTraceStatus", [], timeout=20).get("result") or {}).get("seq")
        _r(sid, "aiStepDryRun", {"runnerId": rid}, 90)
        hi = (_rpc(sid, "aiTraceStatus", [], timeout=20).get("result") or {}).get("seq")
        _rpc(sid, "aiTraceDisable", ["L3"], timeout=20)
        print(f"[32] fenetre L3 seq: ({lo}, {hi}]")
        try:
            files = sorted(host_inputs.find(TRACES, f"{sid}-*.jsonl"),
                           key=lambda p: p.stat().st_mtime)
        except host_inputs.HostInputUnavailable as e:
            # PAS MESURE -- distinct de « la capture L3 n'a rien emis » (rc 4).
            print("[32] repertoire de traces introuvable :\n" + str(e))
            return 5
        if not files:
            print(f"[32] MESURE et VIDE : aucun {sid}-*.jsonl dans "
                  f"{host_inputs.resolve(TRACES).label()} -- la capture L3 "
                  f"n'a rien ecrit pour cette session")
            return 4
        out: dict = {}
        with open(files[-1], encoding="utf-8") as f:
            for line in f:
                if '"utility_score"' not in line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                if e.get("evt") != "utility_score":
                    continue
                sq = e.get("seq")
                if sq is None or (hi is not None and sq > hi) or (lo is not None and sq <= lo):
                    continue
                eu = e.get("unit")
                eun = eu.get("name") if isinstance(eu, dict) else eu
                if uname and eun and eun != uname:
                    continue
                ct = e.get("caseTile") or {}
                t = (ct.get("col"), ct.get("row")) if isinstance(ct, dict) else tuple(ct or ())
                if tiles and t not in tiles:
                    continue
                extra = {k: v for k, v in e.items()
                         if k not in ("evt", "seq", "unit", "caseTile", "utility", "score")}
                out.setdefault(t, []).append((e.get("seq"), str(e.get("utility") or ""),
                                              e.get("score"), extra))
        for t in sorted(out):
            evs = out.get(t) or []
            nz = [x for x in evs if x[2]]
            print(f"[32] NATIF L3 tile {t}: {len(evs)} events, {len(nz)} non-zero:")
            for sq, leaf, score, extra in nz:
                print(f"      seq={sq} {leaf} = {score} extra={json.dumps(extra, default=str)[:140]}")
        return 0
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            print(f"[32] runner {rid} dispose")
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
