"""Probe #38b — la population Skitarii REELLE du walk 38001 par TOUS les visualId candidats.

Hypothese : probe_38 comptait `admecSmnVanguard` (cle config = constants.unitId de ControlEdict)
alors que le summon LIVE porte `visualId == admecNpc1Vanguard` (cf. test_control_edict_live). Donc
mystere (b) = artefact d'observation (mauvais visualId) et cap SOUS-COMPTE. Ce probe compte, a
chaque step, TOUTES les unites obs_units par visualId (surtout admec*Vanguard*), alive+dead,
cumulatif -> mesure le vrai GetChildrenCount all-ever. Sortie JSON, console ASCII.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = Path(r"C:\Users\nicolasv\tacticus-tools")
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine import weights  # noqa: E402
import engine_validate as EV  # noqa: E402

STATE = ROOT / "logs" / "runners" / "_solver38b_summ_state.json"
OUT = ROOT / "logs" / "runners" / "_probe38b_summons.json"
TAN_VIS = "admecMarshall"
BUILD_EXTRA = ["--p-units", "admecMarshall,admecManipulus,admecRuststalker",
               "--a-units", "necroWarden,necroWarden",
               "--hp-target", "250000", "--hp-player", "120000",
               "--board", "MC1_67"]


def main() -> int:
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "38001",
         "--state-file", str(STATE), *BUILD_EXTRA],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("[38b-s] build KO:", (proc.stderr or proc.stdout or "")[-300:])
        return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    sid = _resolve_session()
    print(f"[38b-s] runner={rid}")

    def _r(method, body, t=60):
        return _rpc(sid, method, [body], timeout=t).get("result") or {}

    ever_by_vis: dict = {}
    rows: list = []
    wt = weights.load()

    def diag(step, uid, dv, mov_by_unit, nat, eng, predictor):
        obs = _r("observeBattle", {"runnerId": rid}, 60)
        tan = next((u for u in (obs.get("units") or []) if u.get("visualId") == TAN_VIS), None)
        tan_sq = tan.get("squadId") if tan else None
        # compter par visualId toutes les unites summon-like (vanguard) + tout ce qui n'est pas
        # le roster de base
        base = {"admecMarshall", "admecManipulus", "admecRuststalker", "necroWarden"}
        vis_now: dict = {}
        for u in (obs.get("units") or []):
            vis = u.get("visualId")
            if vis in base:
                continue
            key = (vis, u.get("squadId"))
            vis_now.setdefault(vis, set()).add(u.get("squadId"))
            ever_by_vis.setdefault(vis, set()).add(u.get("squadId"))
        nat_ab = (nat.get("ability") or {}).get("ability") if isinstance(nat, dict) else None
        # counts par visualId : now (alive+dead present dans obs), dead, ever
        summ = {}
        for vis, sqs in vis_now.items():
            dead = sum(1 for u in (obs.get("units") or [])
                       if u.get("visualId") == vis and u.get("isDead"))
            summ[vis] = {"now": len(sqs), "dead_present": dead}
        row = {"step": step, "uid": uid, "nat_ab": nat_ab,
               "tan_pos": ([tan.get("col"), tan.get("row")] if tan else None),
               "summ_now": summ,
               "ever": {v: len(s) for v, s in ever_by_vis.items()}}
        rows.append(row)
        if uid == tan_sq or nat_ab in (1118, 69) or summ:
            print(f"  s{step:02d} nat={nat_ab} tanpos={row['tan_pos']} now={summ} "
                  f"ever={row['ever']}")

    try:
        EV.run_agreement(sid, rid, 52, wt, log=lambda *a, **k: None, probe=diag)
    finally:
        _rpc(sid, "disposeRunner", {"runnerId": rid}, timeout=20)
        try:
            STATE.unlink()
        except OSError:
            pass
    OUT.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print(f"[38b-s] ever total: {[(v, len(s)) for v, s in ever_by_vis.items()]}")
    print(f"[38b-s] dump -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
