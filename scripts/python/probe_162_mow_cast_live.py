"""#162 -- probe de DIAGNOSTIC des suites MoW rouges : que rend REELLEMENT `applyAction`
quand une MACHINE OF WAR caste ?

Les deux suites `test_mow_effect_posers_live` / `test_mow_groups_bcd_live` lisent le retour du
cast natif par `(r.get("actions") or [{}])[0]` puis ne skippent que sur `act.get("error")`. Si le
host repond `{ok: false, error: ...}` SANS clef `actions`, l'erreur est AVALEE : le test continue,
lit une empreinte d'effets live VIDE et echoue sur `off != live` -- en donnant l'impression que le
PORT diverge alors que le cast natif n'a jamais eu lieu.

Ce probe imprime la reponse BRUTE : deploiement de la MoW (`decisionView.mows`), cibles legales
(`abilityTargets`), et le JSON complet de `applyAction`. ASCII-only.

    python probe_162_mow_cast_live.py --mow tauBroadside --ability 1160
    python probe_162_mow_cast_live.py --mow ultraDreadnought --ability 1159   # tile-target
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]


def _rpc(sid, method, body, timeout=90):
    r = R._rpc(sid, method, [body], timeout=timeout)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _footprint(sid, rid) -> dict:
    """MEME empreinte que les suites MoW : `{id unite|MoW|TUILE -> {effectType: remaining}}`.
    Unites/MoW par `decisionView` (cle MoW = `casterId`), tuiles par `tileMeta` (cle = entity id
    de la tuile, publie ici tel quel -- les suites la re-derivent via `board.id_at`)."""
    dec = _rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}) or {}
    tm = _rpc(sid, "tileMeta", {"runnerId": rid}, timeout=60) or {}
    out: dict = {}
    rows = [(u.get("id"), u) for u in (dec.get("units") or [])]
    rows += [(m.get("casterId"), m) for m in (dec.get("mows") or [])]
    for key, u in rows:
        if key is None:
            continue
        effs = {int(e["effectType"]): e.get("remaining") for e in (u.get("effects") or [])
                if e.get("effectType") is not None}
        if effs:
            out[int(key)] = effs
    for t in (tm.get("tiles") or []):
        effs = {int(e["effectType"]): e.get("remaining") for e in (t.get("effects") or [])
                if e.get("effectType") is not None}
        if effs:
            out[("tile", t["col"], t["row"])] = effs
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mow", default="tauBroadside")
    ap.add_argument("--ability", type=int, default=1160)
    ap.add_argument("--board", default="C1_02")
    ap.add_argument("--seed", default="4242")
    ap.add_argument("--p-units", default="necroDestroyer,necroWarden")
    ap.add_argument("--a-units", default="necroDestroyer,necroWarden")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner")
    ap.add_argument("--raw", action="store_true", help="dumper le JSON complet d'applyAction")
    args = ap.parse_args()

    sid = R._resolve_session()
    print(f"[ok] session {sid}")

    state_path = ROOT / "logs" / f"_probe162_{args.mow}_{args.ability}.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.unlink(missing_ok=True)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", args.seed, "--board", args.board,
         "--p-units", args.p_units, "--a-units", args.a_units,
         "--p-mow", args.mow, "--state-file", str(state_path)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_path.exists():
        print("[FAIL] build KO:\n" + (p.stderr or p.stdout or "")[-800:])
        return 2
    rid = json.loads(state_path.read_text())["runnerId"]
    print(f"[ok] runner {rid} board={args.board} mow={args.mow}")

    try:
        dec = _rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        mows = dec.get("mows") or []
        print(f"[mows] {[(m.get('visualId'), m.get('casterId'), m.get('id'), m.get('team'), m.get('owner'), m.get('slot')) for m in mows]}")
        m = next((x for x in mows if x.get("visualId") == args.mow), None)
        if m is None:
            print("[FAIL] MoW non deployee")
            return 3
        caster = m["casterId"]
        print(f"[mow] casterId={caster} abilities={[a.get('abilityType') for a in (m.get('abilities') or [])]}")

        at = _rpc(sid, "abilityTargets",
                  {"runnerId": rid, "unitId": caster, "abilityType": args.ability})
        row = next((u for u in ((at or {}).get("units") or []) if u.get("unitId") == caster), None)
        tgts = ((row.get("abilities") or [{}])[0].get("targets") or []) if row else []
        print(f"[targets] n={len(tgts)} kinds={sorted({t.get('kind') for t in tgts})}")
        if not tgts:
            print("[FAIL] aucune cible legale")
            return 4
        t0 = tgts[0]
        action = {"kind": "ability", "casterId": caster, "abilityType": args.ability}
        if t0.get("kind") == "unit":
            action["targetId"] = t0["targetId"]
        else:
            action["to"] = {"col": t0["tile"]["col"], "row": t0["tile"]["row"]}
        print(f"[cast] action={json.dumps(action)}")
        before = _footprint(sid, rid)
        raw = _rpc(sid, "applyAction", {"runnerId": rid, "action": action})
        ok = isinstance(raw, dict) and raw.get("ok")
        acts = (raw or {}).get("actions") or []
        print(f"[applyAction] ok={ok} nActions={len(acts)} "
              f"act0.ok={(acts[0] if acts else {}).get('ok')} "
              f"act0.error={(acts[0] if acts else {}).get('error')} "
              f"topError={(raw or {}).get('error')}")
        after = _footprint(sid, rid)
        print(f"[footprint AVANT] {before}")
        print(f"[footprint APRES] {after}")
        delta = {k: {et: rem for et, rem in v.items() if et not in (before.get(k) or {})}
                 for k, v in after.items()}
        print(f"[delta] { {k: v for k, v in delta.items() if v} }")
        if args.raw:
            print("[applyAction RAW] " + json.dumps(raw, indent=2)[:6000])
    finally:
        if not args.keep:
            try:
                _rpc(sid, "disposeRunner", {"runnerId": rid}, timeout=20)
                print(f"[ok] runner {rid} dispose")
            except Exception as e:                                  # noqa: BLE001
                print(f"[warn] dispose KO: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
