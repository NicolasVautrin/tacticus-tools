"""Probe #38b — bisection du gate 1118 (DoctrinaImperatives) par ORACLE NATIF ncEvaluate.

Rejoue le walk RUN B (seed 38001) et, a chaque step de Tan (u81), confronte :
  - la leaf NATIVE `Evaluate(unit, curPos)` du playbook 1118 (RPC ncEvaluate, bucket vide/plein) ;
  - le modele v1 du port (count=_has_valid_targets ; adj=unites adjacentes ; cap) ;
  - le modele v2 re-RE (count=GetValidTargets slot 0x41 ; adj=|GetFreeAdjacentTiles| slot 0x51
    = mirror `adjacent_addable_count` ; cap) — slot 0x51 resolu LIVE (probe_38b_vtable.py) :
    `GetFreeAdjacentTiles @181061650` = GetAdjacentTiles(unit,1,1,1) filtre CanAddUnit(tile,1,0,0).
Dump aussi les abilities dv de Tan (ids/kind/usable/fromHereCount) — piste « attaque normale
dependante de la stance ». Sortie JSON data/_probe38b_gate.json, console ASCII only.
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
from engine.ai import context as _ai_ctx  # noqa: E402
from engine.playbook.noncomparable import _base as ncbase  # noqa: E402
from engine.playbook.noncomparable.doctrina_imperatives import (  # noqa: E402
    DoctrinaImperativesPlaybook)
from engine import battle_query as bq  # noqa: E402
import engine_validate as EV  # noqa: E402

STATE = ROOT / "data" / "_solver38b_gate_state.json"
OUT = ROOT / "data" / "_probe38b_gate.json"
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
        print("[38b] build KO:", (proc.stderr or proc.stdout or "")[-300:])
        return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    sid = _resolve_session()
    print(f"[38b] runner={rid}")

    def _r(method: str, body: dict, t: float = 60) -> dict:
        return _rpc(sid, method, [body], timeout=t).get("result") or {}

    rows: list = []
    wt = weights.load()

    def diag(step, uid, dv, mov_by_unit, nat, eng, predictor):
        obs = _r("observeBattle", {"runnerId": rid}, 60)
        tan = next((u for u in (obs.get("units") or [])
                    if u.get("visualId") == TAN_VIS), None)
        tan_sq = tan.get("squadId") if tan else None
        nat_ab = (nat.get("ability") or {}).get("ability") if isinstance(nat, dict) else None
        if uid != tan_sq and nat_ab != 1118:
            return
        try:
            ctx = _ai_ctx.build(lambda m, b, t=60: _r(m, b, t), rid, dv, mov_by_unit,
                                uid, wt, predictor)
            nc = ncbase.NCContext(
                uid=ctx.uid, origin=ctx.origin, reach_nc=ctx.reach_nc, epos=ctx.epos,
                fpos=ctx.fpos, enemies=ctx.enemies, neigh_by_pos=ctx.neigh_by_pos,
                walkable_by_pos=ctx.walkable_by_pos, plan=ctx.plans.get(ctx.uid) or {},
                plans=ctx.plans, hp_cur_by_id=ctx.hp_cur_by_id, elev_by_pos=ctx.elev_by_pos,
                ability_targets=ctx.ability_targets, wt=ctx.wt,
                is_temporary_by_pos=ctx.is_temporary_by_pos,
                effects_by_pos=ctx.effects_by_pos, obs_units=ctx.obs_units,
                tile_id_by_pos=ctx.tile_id_by_pos, active_levels=ctx.active_ability_levels,
                ability_config=ctx.heal_config, units=ctx.units,
                cast_from_tiles=ctx.cast_from_tiles, scene=ctx.scene, debug=False)
            pb = DoctrinaImperativesPlaybook()
            # --- modele v1 (port actuel) ---
            hv = ncbase._has_valid_targets(nc, uid)
            adj_units = pb._free_adjacent_tiles(nc)   # #38b : slot 0x51 = GetFreeAdjacentTiles
            conq = pb._is_conqueror(nc)
            cap = pb._reached_summon_cap(nc)
            emit_v1 = pb._should_emit(nc)
            # --- modele v2 (re-RE) : freeAdj = adjacent_addable_count(origin) ---
            occ_live = {(u.get("col"), u.get("row")) for u in (obs.get("units") or [])
                        if not u.get("isDead") and u.get("col") is not None
                        and u.get("squadId") != uid}
            free_adj = bq.adjacent_addable_count(
                nc.origin, nc.neigh_by_pos, nc.walkable_by_pos, occ_live, nc.elev_by_pos)
            emit_v2 = (conq if not hv
                       else (cap if free_adj > 0 else True))
            # --- oracle natif : leaf 1118 a la position courante ---
            nc_ev = _r("ncEvaluate", {"runnerId": rid, "unitId": int(uid),
                                      "abilityType": 1118, "sweep": False}, 60)
            pos0 = (nc_ev.get("positions") or [{}])[0]
            native_emit = bool(pos0.get("action")) and pos0.get("util") is not None
            # --- abilities dv de Tan (stance-swap ?) ---
            me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
            abil = [{"id": a.get("id"), "kind": a.get("kind"), "usable": a.get("usable")}
                    for a in ((me or {}).get("abilities") or [])]
            effs = [(e if isinstance(e, str) else (e.get("name") if isinstance(e, dict)
                                                   else None))
                    for e in ((me or {}).get("effects") or [])]
            # fromHereCount de l'attaque normale (RPC natif, proxy du count slot 0x41)
            na = next((a for a in ((me or {}).get("abilities") or [])
                       if a.get("kind") == "normal" and a.get("id") is not None), None)
            fh = None
            if na is not None:
                at = nc.ability_targets(uid, na["id"]) or {}
                for uu in (at.get("units") or []):
                    if uu.get("unitId") != uid:
                        continue
                    for a in (uu.get("abilities") or []):
                        if a.get("abilityId") == na["id"]:
                            fh = {"usable": a.get("usable"),
                                  "fromHereCount": a.get("fromHereCount"),
                                  "targets": len(a.get("targets") or [])}
            row = {"step": step, "uid": uid, "nat_ab": nat_ab,
                   "origin": list(nc.origin) if nc.origin else None,
                   "native_leaf": {"emit": native_emit, "raw": pos0},
                   "v1": {"hv": hv, "adj_units": adj_units, "conq": conq, "cap": cap,
                          "emit": emit_v1},
                   "v2": {"free_adj": free_adj, "emit": emit_v2},
                   "na": (na or {}).get("id"), "fh": fh,
                   "abil": abil, "effs": effs,
                   "eng": eng}
            rows.append(row)
            print(f"  s{step:02d} nat={nat_ab} org={nc.origin} leaf_emit={native_emit} "
                  f"util={pos0.get('util')} | v1: hv={hv} adjU={adj_units} conq={conq} "
                  f"cap={cap} emit={emit_v1} | v2: freeAdj={free_adj} emit={emit_v2} "
                  f"| na={(na or {}).get('id')} fh={fh}")
        except Exception as ex:
            print(f"  s{step:02d} diag KO: {ex!r}")
            rows.append({"step": step, "uid": uid, "nat_ab": nat_ab, "error": repr(ex)})

    try:
        EV.run_agreement(sid, rid, 52, wt, log=lambda *a, **k: None, probe=diag)
    finally:
        _rpc(sid, "disposeRunner", {"runnerId": rid}, timeout=20)
        try:
            STATE.unlink()
        except OSError:
            pass
    OUT.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print(f"[38b] dump -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
