#!/usr/bin/env python
"""Probe R1-b (etage NATIF) -- l'ORDRE d'evaluation des positions candidates, LU SUR LE NATIF.

QUESTION BINAIRE : dans quel ORDRE `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`
presente-t-il les positions candidates au `Bucket` (keep-first), et deux positions a utilite EGALE
cote PORT le sont-elles aussi cote NATIF ?

Sans cette mesure on ne peut PAS distinguer les deux diagnostics concurrents d'une divergence de
tuile a utilite portee egale :
  (1) ORDRE DE SWEEP faux  -- le natif evalue les tuiles dans un autre ordre ;
  (2) UTILITE PAR TUILE fausse -- le natif SEPARE strictement deux tuiles que le port egalise.
Fitter l'ordre pour couvrir (2) est exactement l'anti-pattern " ajuster un scalaire ".

CE QUE LA PROBE LIT (hooks EXISTANTS, aucune reinjection) :
  * `scorerUtilTraceDump` -> un event par appel de `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`,
    avec la TUILE CASTER decodee (`UnitPosition` param_4) et l'utilite rendue. La SEQUENCE de ces
    events EST l'ordre d'evaluation natif -- `EvaluateInternal` boucle les cibles a position fixe,
    donc la suite des tuiles DISTINCTES par premiere apparition = l'ordre de la liste `tiles`.
  * `scorerTileTermTraceDump` -> le terme de TUILE complet (composite Tile(7) via
    `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromTilePrediction`)
    par candidat : c'est LUI qui separe (ou non) deux tuiles a meme degat et meme elevation.

Les hooks RVA sont BUILD-SPECIFIQUES (gqfc5mff6c) : la probe verifie le hash avant d'armer, arme
pour UN SEUL `aiStepDryRun`, puis DESARME (`scorerDamageTraceOff`).

ASCII only. Usage :
  python probe_r1b_native_sweep_order.py --seed 999 --board C4_09 --step 14
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
BUILD_HASH = "gqfc5mff6c"          # hash pour lequel les RVA de scorer-damage-trace sont valides


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(seed, board, extra):
    state = ROOT / "logs" / "runners" / f"probeR1bN-{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--board", board, "--state-file", str(state)] + list(extra or [])
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO:", (p.stderr or p.stdout or "")[-400:])
        return None, None
    return json.loads(state.read_text())["runnerId"], state


def _apply_native(sid, rid, dry):
    acts = []
    for m in (dry["action"]["messages"]):
        if m.get("cls") == "MoveUnitMessage":
            acts.append({"kind": "move", "unitId": m["unitId"],
                         "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
        elif m.get("cls") == "ActiveAbilityMessage":
            acts.append({"kind": "ability", "casterId": m["casterId"],
                         "targetId": m.get("targetId"), "abilityType": m["abilityType"]})
        elif m.get("cls") == "FinishUnitTurnMessage":
            acts.append({"kind": "finish", "unitId": m["unitId"]})
    for a in acts:
        _r(sid, "applyAction", {"runnerId": rid, "action": a}, 90)
    return len(acts)


def _first_seen(seq_tiles):
    out, seen = [], set()
    for t in seq_tiles:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def run(sid, rid, target_step):
    # --- avance jusqu'au pas cible sur la trajectoire NATIVE -------------------
    uid = None
    for step in range(target_step):
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            print(f"native epuise au pas {step} ({dry.get('error')})")
            return 1
        _apply_native(sid, rid, dry)

    # --- etat de DECISION du pas cible ---------------------------------------
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    plans = {p.get("unitId"): p for p in (dv.get("attackPlans") or [])}

    # --- ARME les hooks RVA le temps d'UN SEUL dry-run ------------------------
    on = _r(sid, "scorerDamageTraceOn", {}, 90)
    print("scorerDamageTraceOn:", json.dumps(on)[:200])
    _r(sid, "scorerDamageTraceClear", {"runnerId": rid, "stacks": 0}, 60)
    try:
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 90)
        util = _r(sid, "scorerUtilTraceDump", {"runnerId": rid, "max": 4000}, 90)
        tterm = _r(sid, "scorerTileTermTraceDump", {"runnerId": rid, "max": 4000}, 90)
        elev = _r(sid, "scorerElevTraceDump", {"runnerId": rid, "max": 4000}, 90)
        leaf = _r(sid, "scorerLeafTraceDump", {"runnerId": rid, "max": 4000}, 90)
        comp = _r(sid, "scorerComposedDump", {}, 90)
    finally:
        _r(sid, "scorerDamageTraceOff", {}, 60)

    uid = dry.get("activatedUnitId")
    msgs = (dry.get("action") or {}).get("messages") or []
    nat_move = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)
    nat_ab = next((m for m in msgs if m.get("cls") == "ActiveAbilityMessage"), None)
    me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
    mpos = ((me or {}).get("pos") or {})
    origin = (mpos.get("col"), mpos.get("row")) if mpos.get("col") is not None else None
    nat_tile = ((nat_move["to"]["col"], nat_move["to"]["row"]) if nat_move else origin)

    print(f"\n===== PAS {target_step} : u{uid} ({(me or {}).get('visualId')}) origin={origin} =====")
    print(f"  natif : move={nat_tile if nat_move else None} "
          f"ability={(nat_ab or {}).get('abilityType')} tgt={(nat_ab or {}).get('targetId')}")

    move_tiles = [(t["col"], t["row"]) for t in ((mov_by_unit.get(uid) or {}).get("tiles") or [])]
    action_tiles = ([origin] if origin else []) + [t for t in move_tiles if t != origin]
    print(f"\n  action_tiles (PORT = [origine] + aiMovableTiles) :\n    {action_tiles}")

    seen, ranked_union = set(), []
    for ev in ((plans.get(uid) or {}).get("evals") or []):
        for rk in (ev.get("ranked") or []):
            t = (rk.get("col"), rk.get("row"))
            if t[0] is not None and t not in seen:
                seen.add(t)
                ranked_union.append(t)
    print(f"\n  ranked (union, ordre GetBestTileToAttackFrom) :\n    {ranked_union}")

    ents = util.get("entries") or []
    print(f"\n  scorerUtilTrace : utilInstalled={util.get('utilInstalled')} "
          f"bufferSize={util.get('bufferSize')} entries={len(ents)}")
    if not ents:
        print("  !! AUCUN event -- hook non arme / RVA fausse / pas de tier Comparable a ce pas")
        return 1
    seq_tiles = [(e.get("casterCol"), e.get("casterRow")) for e in ents]
    native_order = _first_seen([t for t in seq_tiles if t[0] is not None and t[0] >= 0])
    print(f"\n  ORDRE NATIF d'evaluation (1re apparition par tuile, {len(ents)} appels) :\n"
          f"    {native_order}")
    print(f"  == action_tiles ? {native_order == [t for t in action_tiles if t in set(native_order)]}")
    print(f"  == ranked ?      {native_order == [t for t in ranked_union if t in set(native_order)]}")

    print("\n  UTILITE NATIVE par appel (seq, tuile, cibles, utility) :")
    for e in ents:
        print(f"    #{e.get('seq'):<5} {(e.get('casterCol'), e.get('casterRow'))} "
              f"tgts={e.get('targets')} u={e.get('utility')}")

    tents = tterm.get("entries") or []
    print(f"\n  scorerTileTermTrace : tileTermInstalled={tterm.get('tileTermInstalled')} "
          f"entries={len(tents)}")
    for e in tents:
        print(f"    #{e.get('seq'):<5} {(e.get('casterCol'), e.get('casterRow'))} "
              f"tileTerm={e.get('tileTerm', e.get('value'))}")

    # --- DECOMPOSITION du terme de tuile : feuille Elevation + feuilles situationnelles -------
    eents = elev.get("entries") or []
    print(f"\n  scorerElevTrace : elevInstalled={elev.get('elevInstalled')} entries={len(eents)}")
    for e in eents[:40]:
        print(f"    #{e.get('seq'):<5} {e}")
    lents = leaf.get("entries") or []
    print(f"\n  scorerLeafTrace : leafInstalled={leaf.get('leafInstalled')} entries={len(lents)}")
    for e in lents[:60]:
        print(f"    #{e.get('seq'):<5} {e}")
    print(f"\n  scorerComposedDump : composedInstalled={comp.get('composedInstalled')}")
    for c in (comp.get("composites") or []):
        print(f"    ptr={c.get('ptr')} count={c.get('count')}")
        print(f"      children={c.get('children')}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--seed", default="999")
    ap.add_argument("--board", default="C4_09")
    ap.add_argument("--step", type=int, default=14)
    ap.add_argument("--extra", nargs=argparse.REMAINDER, default=[])
    args = ap.parse_args()
    games = Path("C:/Users/nicolasv/AppData/Local/tacticus/games")
    hashes = [p.name for p in games.iterdir()] if games.exists() else []
    if BUILD_HASH not in hashes:
        print(f"REFUS : hooks RVA valides pour {BUILD_HASH}, builds presents = {hashes}")
        return 2
    sid = _resolve_session()
    if args.runner is not None:
        print(f"runner {args.runner} (existant, non dispose)")
        return run(sid, args.runner, args.step)
    rid, state = _build(args.seed, args.board, args.extra)
    if rid is None:
        return 1
    print(f"runner {rid} seed={args.seed} board={args.board} step={args.step}")
    try:
        return run(sid, rid, args.step)
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        try:
            state.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
