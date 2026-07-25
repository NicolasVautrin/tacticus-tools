"""Probe #90 lot B : MESURE LIVE des abilities MoW dont le behaviour natif est une POSE D'EFFET
(`AddEffect`/`AddBondEffect` seuls, aucune attaque au cast) -- lot A du classement (cf. rapport).

Ce que le probe capte, POUR CHAQUE (MoW, ability) :
  * `abilityTargets` : nb de cibles + KIND (unit / tile) ;
  * l'etat des effets AVANT/APRES le cast, sur les DEUX canaux :
      - `decisionView.units[].effects` + `decisionView.mows[].effects` (effets d'UNITE / de MoW) ;
      - `tileMeta.tiles[].effects` (effets de TUILE, `readEffectsByTile` -- le SEUL canal ou les
        marquages de tuiles type SquigMine_Tile / MacroPlasmaIncinerator_Tile sont visibles) ;
  * le delta exact (qui porte quoi, `remaining`/`level`, coordonnees des tuiles marquees).

C'est la VERITE-TERRAIN contre laquelle le port offline (`engine/runner/abilities/mow_effects.py`)
est confronte, sans aucune constante attendue en dur.

Usage (depuis scripts/python, ASCII only) :

    python probe_90b_mow_effects.py cast --mow tauBroadside --ability 1160 \
        --board C1_02 --state-file <chemin ABSOLU unique>
    python probe_90b_mow_effects.py sweep --state-file <chemin ABSOLU unique>
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rl_collect_batch import _rpc, _resolve_session  # noqa: E402

PYDIR = Path(__file__).resolve().parent

# (mow, abilityType, abilityName) du LOT porte -- behaviour natif = pose d'effet(s) seule.
LOT = [
    ("tauBroadside", 1160, "HeavyRailRifle"),
    ("ultraDreadnought", 1159, "MacroPlasmaIncinerator"),
    ("adeptExorcist", 1188, "DevastatingRefrain"),
    ("orksRukkatrukk", 1201, "SquigMine"),
    ("astraOrdnanceBattery", 1142, "MalleusRocketLauncher"),
]


def _r(sid: int, method: str, body: dict, timeout: int = 90):
    res = _rpc(sid, method, [body], timeout=timeout)
    return res.get("result") if isinstance(res, dict) and "result" in res else res


def build(mow: str, board: str, state_file: str, seed: int = 4242,
          p_units: str = "necroDestroyer,necroWarden",
          a_units: str = "necroDestroyer,necroWarden") -> int | None:
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
         "--p-units", p_units, "--a-units", a_units,
         "--p-mow", mow, "--state-file", state_file],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    p = Path(state_file)
    if not p.exists():
        print("  [build KO] %s" % ((proc.stderr or proc.stdout or "")[-600:]))
        return None
    return json.loads(p.read_text())["runnerId"]


def unit_effects(dec: dict) -> dict:
    """{id (unit) | 'mow<casterId>': [(name, effectType, remaining, level)]}"""
    out = {}
    for u in (dec.get("units") or []):
        out[u.get("id")] = sorted((e.get("name"), e.get("effectType"), e.get("remaining"),
                                   e.get("level")) for e in (u.get("effects") or []))
    for m in (dec.get("mows") or []):
        out["mow%s" % m.get("casterId")] = sorted(
            (e.get("name"), e.get("effectType"), e.get("remaining"), e.get("level"))
            for e in (m.get("effects") or []))
    return out


def tile_effects(tm: dict) -> dict:
    """{(col,row): [(name, effectType, source, remaining, level)]} -- tuiles PORTANT un effet."""
    out = {}
    for t in (tm.get("tiles") or []):
        effs = t.get("effects") or []
        if effs:
            out[(t.get("col"), t.get("row"))] = sorted(
                (e.get("name"), e.get("effectType"), e.get("source"), e.get("remaining"),
                 e.get("level")) for e in effs)
    return out


def _delta(before: dict, after: dict) -> dict:
    out = {}
    for k in sorted(set(before) | set(after), key=str):
        b, a = before.get(k), after.get(k)
        if b != a:
            out[str(k)] = {"before": b, "after": a}
    return out


def cast_one(sid: int, rid: int, mow: str, ability: int, target_pick: str = "auto") -> dict:
    dec = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    m = next((x for x in (dec.get("mows") or []) if x.get("visualId") == mow), None)
    if m is None:
        return {"error": "mow %s absent de decisionView.mows" % mow}
    caster = m["casterId"]
    at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": caster, "abilityType": ability},
            90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster), None)
    tgts = ((row.get("abilities") or [{}])[0].get("targets") or []) if row else []
    kinds = sorted({t.get("kind") for t in tgts})
    tm_b = _r(sid, "tileMeta", {"runnerId": rid}, 60) or {}
    e_b, t_b = unit_effects(dec), tile_effects(tm_b)
    pick = None
    if target_pick == "unit":
        pick = next((t for t in tgts if t.get("kind") == "unit"), None)
    elif target_pick == "tile":
        pick = next((t for t in tgts if t.get("kind") == "tile"), None)
    if pick is None:
        pick = (next((t for t in tgts if t.get("kind") == "unit"), None)
                or next((t for t in tgts if t.get("kind") == "tile"), None))
    action = {"kind": "ability", "casterId": caster, "abilityType": ability}
    if pick is None:
        return {"caster": caster, "nTargets": 0, "kinds": kinds, "error": "no legal target"}
    if pick.get("kind") == "unit":
        action["targetId"] = pick["targetId"]
        tgt_desc = {"kind": "unit", "id": pick["targetId"]}
    else:
        action["to"] = {"col": pick["tile"]["col"], "row": pick["tile"]["row"]}
        tgt_desc = {"kind": "tile", "col": pick["tile"]["col"], "row": pick["tile"]["row"]}
    res = _r(sid, "applyAction", {"runnerId": rid, "action": action}, 90) or {}
    act = (res.get("actions") or [{}])[0]
    dec_a = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    tm_a = _r(sid, "tileMeta", {"runnerId": rid}, 60) or {}
    e_a, t_a = unit_effects(dec_a), tile_effects(tm_a)
    return {
        "caster": caster, "slot": m.get("slot"),
        "nTargets": len(tgts), "kinds": kinds, "target": tgt_desc,
        "castOk": bool(act.get("ok")) and not act.get("error"),
        "mutated": act.get("mutated"), "error": act.get("error"),
        "unitEffDelta": _delta(e_b, e_a), "tileEffDelta": _delta(t_b, t_a),
        "abilityLevel": next((a.get("level") for a in (m.get("abilities") or [])
                              if a.get("id") == ability), None),
        "abilityMult": next((a.get("multiplier") for a in (m.get("abilities") or [])
                             if a.get("id") == ability), None),
        "allTargets": [({"kind": t.get("kind"), "id": t.get("targetId")}
                        if t.get("kind") == "unit"
                        else {"kind": "tile", "col": t["tile"]["col"], "row": t["tile"]["row"]})
                       for t in tgts],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["cast", "sweep"])
    ap.add_argument("--mow", default=None)
    ap.add_argument("--ability", type=int, default=None)
    ap.add_argument("--board", default="C1_02")
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--pick", default="auto", choices=["auto", "unit", "tile"])
    ap.add_argument("--state-file", required=True)
    a = ap.parse_args()
    sid = _resolve_session()
    todo = LOT if a.cmd == "sweep" else [(a.mow, a.ability, "?")]
    report = []
    for mow, ab, name in todo:
        print("=== %s / %s (%s) ===" % (mow, ab, name))
        rid = build(mow, a.board, a.state_file, seed=a.seed)
        if rid is None:
            report.append({"mow": mow, "ability": ab, "error": "build KO"})
            continue
        r = cast_one(sid, rid, mow, ab, a.pick)
        r.update({"mow": mow, "ability": ab, "name": name, "board": a.board, "runnerId": rid})
        report.append(r)
        print("  caster=%s slot=%s tgts=%d kinds=%s pick=%s cast=%s mut=%s err=%s"
              % (r.get("caster"), r.get("slot"), r.get("nTargets"), r.get("kinds"),
                 r.get("target"), r.get("castOk"), r.get("mutated"), r.get("error")))
        print("  unitEffDelta = %s" % json.dumps(r.get("unitEffDelta"), ensure_ascii=True))
        print("  tileEffDelta = %s" % json.dumps(r.get("tileEffDelta"), ensure_ascii=True)[:3000])
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
        except Exception:
            pass
    out = Path(a.state_file).with_suffix(".effects.json")
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("report -> %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
