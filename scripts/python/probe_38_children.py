"""Probe #38 — diagnostic du compte d'enfants ReachedSummonCap (case-38).

Reproduit le walk RUN B (seed 38001, roster admec vs wardens, HP gonfles) avec une sonde
par step qui trace la POPULATION Skitarii (admecSmnVanguard) vue par nos sources offline :

  - obs_units (observeBattle)  : squadIds presents, isDead, teamId  -> compte COURANT du port ;
  - decisionView.units         : ids presents (dv garde-t-il les summons disparus ?) ;
  - union cumulative des squadIds Skitarii jamais vus (proxy du GetChildrenCount natif
    all-ever, la liste ParentComponent n'etant pas purgee — cf. case-38 §1).

But : departager, aux steps ou le natif emet 1118 (32/44/50 de RUN B) et ou le moteur a
misse, (i) sous-compte offline (Skitarii morts/retires sortis d'obs_units) vs (ii) branche
adj/count divergente. Dump JSON -> data/_probe38_diag.json (ASCII console only).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine import weights  # noqa: E402
from engine.ai import context as _ai_ctx  # noqa: E402
from engine.playbook.noncomparable import _base as ncbase  # noqa: E402
from engine.playbook.noncomparable.doctrina_imperatives import (  # noqa: E402
    DoctrinaImperativesPlaybook)
import engine_validate as EV  # noqa: E402

STATE = ROOT / "data" / "_probe38_duel_state.json"
OUT = ROOT / "data" / "_probe38_diag.json"
VID = "admecSmnVanguard"
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
        print("[probe38] build KO:", (proc.stderr or proc.stdout or "")[-300:])
        return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    sid = _resolve_session()
    print(f"[probe38] runner={rid}")

    def _r(method: str, body: dict, t: float = 60) -> dict:
        """Enveloppe RPC host : params = LISTE [body], payload sous .result."""
        return _rpc(sid, method, [body], timeout=t).get("result") or {}

    snap = _r("combatSnapshot", {"runnerId": rid}, 120)
    tan_cfg = None
    for u in (snap.get("units") or []):
        if u.get("visualId") == TAN_VIS or u.get("entityId") == 81:
            cfg = u.get("unitConfig") or {}
            tan_cfg = {"entityId": u.get("entityId"), "visualId": u.get("visualId"),
                       "active": cfg.get("activeAbilityLevel"),
                       "passive": cfg.get("passiveAbilityLevel"),
                       "mult": cfg.get("abilityVariablesMultiplier")}
            break
    print("[probe38] tan cfg:", json.dumps(tan_cfg))

    ever: set = set()
    rows: list = []

    def diag(step, uid, dv, mov_by_unit, nat, eng, predictor):
        obs = _r("observeBattle", {"runnerId": rid}, 60)
        sk = [{"sq": u.get("squadId"), "dead": u.get("isDead"), "team": u.get("teamId"),
               "pos": [u.get("col"), u.get("row")]}
              for u in (obs.get("units") or []) if u.get("visualId") == VID]
        # dedup par squad (obs = 1 ligne par UnitFoot)
        by_sq = {}
        for s in sk:
            by_sq.setdefault(s["sq"], s)
        for q in by_sq:
            ever.add(q)
        tan = next((u for u in (obs.get("units") or [])
                    if u.get("visualId") == TAN_VIS), None)
        dv_ids = [u.get("id") for u in ((dv.get("units")) or [])]
        dv_sk = [i for i in dv_ids if i in ever]
        nat_ab = (nat.get("ability") or {}).get("ability") if isinstance(nat, dict) else None
        row = {"step": step, "uid": uid, "nat_ab": nat_ab,
               "sk_now": sorted(by_sq), "sk_dead": sorted(q for q, s in by_sq.items() if s["dead"]),
               "sk_ever": sorted(ever), "dv_sk": sorted(dv_sk),
               "tan_pos": ([tan.get("col"), tan.get("row")] if tan else None)}
        # -- Instrumentation du GATE 1118 (aux steps de Tan) : memes materiaux que le moteur --
        if uid == (tan.get("squadId") if tan else None) or nat_ab == 1118:
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
                hv = ncbase._has_valid_targets(nc, uid)
                adj = pb._free_adjacent_tiles(nc)   # #38b : slot 0x51 = GetFreeAdjacentTiles
                conq = pb._is_conqueror(nc)
                cap = pb._reached_summon_cap(nc)
                emit = pb._should_emit(nc)
                usable = pb._usable(nc)
                me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
                effs = [(e if isinstance(e, str) else (e.get("name") if isinstance(e, dict)
                                                       else None))
                        for e in ((me or {}).get("effects") or [])]
                ring = sorted(set((nc.neigh_by_pos or {}).get(nc.origin) or [])
                              & (set(nc.epos or []) | set(nc.fpos or [])))
                row["gate"] = {"hv": hv, "adj": adj, "ring": ring, "conq": conq,
                               "cap": cap, "emit": emit, "usable": usable,
                               "effs": effs, "eng": eng}
                print(f"  s{step:02d} nat_ab={nat_ab} org={nc.origin} hv={hv} adj={adj} "
                      f"ring={ring} conq={conq} cap={cap} usable={usable} emit={emit} "
                      f"effs={effs} now={len(by_sq)} ever={len(ever)}")
            except Exception as ex:                        # jamais propager (walk prime)
                print(f"  s{step:02d} gate-diag KO: {ex!r}")
        rows.append(row)

    wt = weights.load()
    try:
        EV.run_agreement(sid, rid, 52, wt, log=lambda *a, **k: None, probe=diag)
    finally:
        _rpc(sid, "disposeRunner", {"runnerId": rid}, timeout=20)
        try:
            STATE.unlink()
        except OSError:
            pass
    OUT.write_text(json.dumps({"tan_cfg": tan_cfg, "rows": rows}, indent=1),
                   encoding="utf-8")
    print(f"[probe38] dump -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
