"""Capture de trace SCORER sur runner ISOLE — flux CORRECT encapsule (post-refacto multi-runner #43).

Ce helper existe parce que le flux de capture a TROIS gotchas non-obvious, decouverts a la dure et
eparpilles (state-file dans la coexistence, OriginBuffers dans #43, le cache nulle part). Il les masque
pour qu'on ne les re-derive JAMAIS : `capture(seed)` fait tout dans le bon ordre.

GOTCHAS encapsules (= la doc executable du flux) :
  1. state-file ROOT-ANCHORED : `--state-file data/X.json` s'ecrit dans <repo>/data/, et le `runnerId`
     se lit DANS le fichier JSON produit (PAS dans stdout, qui contient un resume lisible).
  2. traces = `OriginBuffers` PAR ORIGINE (refacto #43, purge au dispose) : il FAUT dumper avec
     `{runnerId: rid}`. Les RPC ai-step (`aiStepDryRun`/`decisionView`) posent `setTraceOrigin(runnerId)`
     pour attribuer les entrees ; sans le bon filtre le dump revient vide alors que les hooks ont fire.
  3. les hooks (`ProbableDamageEvent..ctor`, `CalculateBaseDamageWithAllModifiers`) ne firent que quand
     l'IA native SCORE vraiment un tour joue (`aiStepDryRun`, ou l'`endturn` d'un joueur IA) — PAS sur le
     `decisionView` d'affichage seul (chemin de prediction display + CachedDamagePrediction). =>
     `scorerDamageTraceOn` DOIT etre active AVANT que le scenario tourne (ici : avant le drive).
     ⚠ LIMITE OBSERVEE : un drive skewe la capture vers les attaques ENNEMIES (scorees pendant leurs
     endturn) ; capter l'attaque d'une unite AMIE precise (ex. u92) demande que l'IA CHOISISSE cette
     attaque — positionner pour que ce soit son meilleur coup (raffinement TODO du helper).

Usage (import) :
    from scorer_trace_capture import capture
    r = capture(seed="31337", want=lambda e: e.get("targetId") in (82, 84, 86))
    # r["events"]  = ProbableDamageEvent : {targetId, hits, healthMin, healthMax, curHealth, ...}
    # r["allmods"] = CalculateBaseDamageWithAllModifiers : {input(=base/coup), out, isCrit, isMelee, ...}
    # r["final"]   = dernier decisionView (positions/attackPlans) ; r["rid"] = runnerId (deja dispose)

Usage (CLI) : python scorer_trace_capture.py --seed 31337
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Callable

import rl_collect_batch as R
import predict_samples as PV

_PYDIR = Path(__file__).resolve().parent            # scripts/python
_REPO = _PYDIR.parents[1]                           # racine repo (state-file root-anchored)


def _res(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _rpc(sid: int, method: str, body=None, timeout: float = 90):
    return _res(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def _build(seed: str, state_rel: str) -> tuple[int, int]:
    """Build un runner ISOLE (state-file root-anchored, gotcha 1) ; runnerId lu DANS le fichier."""
    subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", state_rel],
        cwd=str(_PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    state_abs = _REPO / state_rel                   # gotcha 1 : root-anchored, PAS scripts/python/
    if not state_abs.exists():
        raise RuntimeError(f"build KO (rl_duel) : state-file absent {state_abs}")
    st = json.loads(state_abs.read_text())
    return st["runnerId"], st.get("myTeam", 1)


def capture(seed: str = "777", *, sid: int | None = None, max_turns: int = 6,
            state_rel: str = "data/_scorer_trace_capture.json",
            want: Callable[[dict], bool] | None = None) -> dict:
    """Capture la trace scorer d'un scenario ISOLE (build -> trace AVANT drive -> dump par origine ->
    dispose). Retourne `{rid, my_team, events, allmods, final, eventBufferSize, allModsBufferSize}`.
    `want(entry)->bool` filtre les `events` retournes (defaut : tous). `sid` auto-resolu si None.
    Pre-requis : session Frida DEJA warmee par l'orchestrateur (le helper ne amorce PAS)."""
    sid = sid if sid is not None else R._resolve_session()
    rid, my_team = _build(seed, state_rel)
    try:
        _rpc(sid, "scorerDamageTraceOn", {"runnerId": rid})      # gotcha 3 : AVANT le scoring
        _rpc(sid, "scorerDamageTraceClear", {"runnerId": rid})
        final = PV._drive_into_range(sid, rid, my_team, max_turns)   # scoring FRAIS -> ctor fire
        ev = _rpc(sid, "scorerDamageTraceDump", {"runnerId": rid, "max": 8000}) or {}   # gotcha 2
        am = _rpc(sid, "scorerAllModsTraceDump", {"runnerId": rid, "max": 8000}) or {}
        _rpc(sid, "scorerDamageTraceOff", {"runnerId": rid})
        events = ev.get("entries") or []
        if want is not None:
            events = [e for e in events if want(e)]
        return {"rid": rid, "my_team": my_team, "events": events,
                "allmods": am.get("entries") or [], "final": final,
                "eventBufferSize": ev.get("bufferSize"), "allModsBufferSize": am.get("bufferSize")}
    finally:
        _rpc(sid, "disposeRunner", {"runnerId": rid}, 20)         # #43 : purge les OriginBuffers du rid


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Capture trace scorer sur runner isole")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--max-turns", type=int, default=6)
    a = ap.parse_args()
    r = capture(a.seed, max_turns=a.max_turns)
    print(f"rid={r['rid']} my_team={r['my_team']} "
          f"events={len(r['events'])} (buffer {r['eventBufferSize']}) "
          f"allmods={len(r['allmods'])} (buffer {r['allModsBufferSize']})")
    seen: dict = {}
    for e in r["events"]:
        k = (e.get("targetId"), e.get("hits"))
        seen[k] = seen.get(k, 0) + 1
    print("ProbableDamageEvent (targetId, hits) x count :")
    for (tgt, hits), n in sorted(seen.items(), key=lambda kv: (kv[0][0] or 0, kv[0][1] or 0)):
        print(f"  tgt=u{tgt} hits={hits} x{n}")
