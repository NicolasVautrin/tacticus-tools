"""Probe DEBLOQUEUR : cast d'ability par une Machine of War (MoW) hors-plateau.

Mesure, POUR CHAQUE MoW du pool spawnable et CHAQUE ability de son kit, ce qui se
passe reellement quand on tente le cast dans un runner headless :

  * les cibles legales rendues par `abilityTargets` (le MoW EST un caster reconnu :
    `rpc-targeting.ts` scanne `EntityType.Machine` en plus de `EntityType.Unit`) ;
  * le resultat de `applyAction {kind:"ability", casterId=machineId, ...}` ;
  * la cascade d'events natifs + le delta observable (HP ennemis, spawns, effets).

Et, cote OFFLINE, si le caster MoW existe dans l'etat charge par
`engine.runner.snapshot.load_state` (verrou : `load_state` n'itere que
`decisionView.units`, les MoW vivent dans `decisionView.mows`).

Usage (depuis scripts/python, ASCII only) :

    python probe_mow_cast.py runners
    python probe_mow_cast.py rpc <method> '<json-args>'
    python probe_mow_cast.py sweep --mow tauBroadside,ultraDreadnought \
        --board C1_02 --state-file <chemin ABSOLU unique>
    python probe_mow_cast.py offline --state-file <chemin ABSOLU du state-file>
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

POOL_MOW = ["adeptExorcist", "astraOrdnanceBattery", "blackForgefiend", "deathCrawler",
            "orksRukkatrukk", "tauBroadside", "tyranBiovore", "ultraDreadnought"]


def _r(sid: int, method: str, body: dict, timeout: int = 90):
    res = _rpc(sid, method, [body], timeout=timeout)
    return res.get("result") if isinstance(res, dict) and "result" in res else res


# ------------------------------------------------------------------ sweep live

def _build(mow: str, board: str, state_file: str, seed: int = 4242) -> int | None:
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
         "--p-units", "necroDestroyer,necroWarden", "--a-units", "necroDestroyer,necroWarden",
         "--p-mow", mow, "--state-file", state_file],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    p = Path(state_file)
    if not p.exists():
        print("  [build KO] %s" % ((proc.stderr or proc.stdout or "")[-400:]))
        return None
    return json.loads(p.read_text())["runnerId"]


def _obs_digest(ob: dict) -> dict:
    return {
        "units": {u.get("squadId"): (u.get("visualId"), u.get("hp"), u.get("teamId"),
                                     bool(u.get("isDead")))
                  for u in (ob.get("units") or [])},
    }


def _effects_digest(dec: dict) -> dict:
    out = {}
    for u in (dec.get("units") or []):
        out[u.get("id")] = sorted(e.get("name") for e in (u.get("effects") or []) if e.get("name"))
    for m in (dec.get("mows") or []):
        out["mow%s" % m.get("casterId")] = sorted(
            e.get("name") for e in (m.get("effects") or []) if e.get("name"))
    return out


def _count_steps(res: dict) -> int:
    n = 0
    def walk(node):
        nonlocal n
        if isinstance(node, dict):
            if node.get("kind") == "step" or "fields" in node:
                n += 1
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(res)
    return n


def sweep(mows: list[str], board: str, state_file: str) -> int:
    sid = _resolve_session()
    report: list[dict] = []
    for mow in mows:
        print("=== %s ===" % mow)
        rid = _build(mow, board, state_file)
        if rid is None:
            report.append({"mow": mow, "error": "build KO"})
            continue
        dec = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        m = next((x for x in (dec.get("mows") or []) if x.get("visualId") == mow), None)
        if m is None:
            print("  MoW ABSENT de decisionView.mows -> non deploye")
            report.append({"mow": mow, "error": "not deployed"})
            continue
        caster = m["casterId"]
        print("  casterId=%s slot=%s pos=%s hp=%s abilities=%s"
              % (caster, m.get("slot"), m.get("pos"), m.get("hp"),
                 [(a["id"], a["name"]) for a in (m.get("abilities") or [])]))
        entry = {"mow": mow, "casterId": caster, "slot": m.get("slot"),
                 "pos": m.get("pos"), "hp": m.get("hp"), "abilities": []}
        for i, ab in enumerate(m.get("abilities") or []):
            if i > 0:
                # rendre l'action au MoW : cloture du tour team1 puis du tour team2
                for _ in range(2):
                    _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            abid = ab["id"]
            at = _r(sid, "abilityTargets",
                    {"runnerId": rid, "unitId": caster, "abilityType": abid}, 90) or {}
            row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster), None)
            tgts = ((row.get("abilities") or [{}])[0].get("targets") or []) if row else []
            fromhere = ((row.get("abilities") or [{}])[0].get("fromHere") or []) if row else []
            dec_b = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
            mb = next((x for x in (dec_b.get("mows") or []) if x.get("casterId") == caster), None)
            ab_live = next((a for a in ((mb or {}).get("abilities") or [])
                            if a.get("id") == abid), {})
            ob_b = _r(sid, "observeBattle", {"runnerId": rid}, 40) or {}
            pick = next((t for t in tgts if t.get("kind") == "unit"), None) \
                or next((t for t in tgts if t.get("kind") == "tile"), None)
            action = {"kind": "ability", "casterId": caster, "abilityType": abid}
            if pick is None:
                res = {"actions": [{"error": "no legal target"}]}
            else:
                if pick.get("kind") == "unit":
                    action["targetId"] = pick["targetId"]
                else:
                    action["to"] = {"col": pick["tile"]["col"], "row": pick["tile"]["row"]}
                res = _r(sid, "applyAction", {"runnerId": rid, "action": action}, 90) or {}
            act = (res.get("actions") or [{}])[0]
            ob_a = _r(sid, "observeBattle", {"runnerId": rid}, 40) or {}
            dec_a = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
            d_b, d_a = _obs_digest(ob_b), _obs_digest(ob_a)
            hp_delta = {k: (d_b["units"][k][1], v[1]) for k, v in d_a["units"].items()
                        if k in d_b["units"] and d_b["units"][k][1] != v[1]}
            new_units = {k: v for k, v in d_a["units"].items() if k not in d_b["units"]}
            e_b, e_a = _effects_digest(dec_b), _effects_digest(dec_a)
            eff_delta = {k: (e_b.get(k), v) for k, v in e_a.items() if e_b.get(k) != v}
            ok = bool(act.get("ok")) and not act.get("error")
            r = {"id": abid, "name": ab["name"],
                 "usable": ab_live.get("usable"), "cooldown": ab_live.get("cooldown"),
                 "hasAmmo": ab_live.get("hasAmmo"), "disabled": ab_live.get("disabled"),
                 "level": ab_live.get("level"), "mult": ab_live.get("multiplier"),
                 "nTargets": len(tgts), "nFromHere": len(fromhere),
                 "targetKinds": sorted({t.get("kind") for t in tgts}),
                 "picked": (pick or {}).get("kind"),
                 "castOk": ok, "error": act.get("error"),
                 "mutated": act.get("mutated"),
                 "steps": _count_steps(act),
                 "hpDelta": hp_delta, "newUnits": new_units, "effDelta": eff_delta}
            entry["abilities"].append(r)
            print("  ab %-5s %-30s tgts=%-3d fromHere=%-3d cast=%-5s err=%s steps=%d "
                  "hpDelta=%s new=%s eff=%s"
                  % (abid, r["name"], r["nTargets"], r["nFromHere"], ok, r["error"],
                     r["steps"], hp_delta, list(new_units.values()), list(eff_delta)[:4]))
        report.append(entry)
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
        except Exception:
            pass
    out = Path(state_file).with_suffix(".sweep.json")
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("report -> %s" % out)
    return 0


# ------------------------------------------------------------------ offline check

def offline(state_file: str) -> int:
    sid = _resolve_session()
    rid = json.loads(Path(state_file).read_text())["runnerId"]
    dec = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    state = load_state(dec, ob, snap, board=board)
    mow_ids = [m.get("casterId") for m in (dec.get("mows") or [])]
    print("entities offline = %s" % sorted(state.entities))
    print("MoW casterIds    = %s" % mow_ids)
    from engine.runner.components import StatsComponent
    for c in mow_ids:
        e = state.get_entity(c)
        comps = sorted(t.__name__ for t in e._components) if e else None  # noqa: SLF001
        print("  caster %s present=%s components=%s" % (c, e is not None, comps))
        sc = e.get_component(StatsComponent) if e else None
        if sc is not None:
            print("    ctx visual=%s level=%s mult=%s traits=%s faction=%s attack=%s health=%s"
                  % (sc.ctx.visual_id, sc.ctx.active_ability_level,
                     sc.ctx.ability_variables_multiplier, sc.ctx.traits, sc.ctx.faction,
                     sc.ctx.attack, sc.ctx.health))
    # cross-check du diff canonique (snapshot(state) vs snapshot_live) : doit etre VIDE
    from engine.runner.snapshot import snapshot as snap_state, snapshot_live, diff
    d = diff(snapshot_live(dec, ob), snap_state(state))
    print("diff(snapshot_live, snapshot(state)) = %s" % (d or "[] (OK)"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["runners", "rpc", "sweep", "offline"])
    ap.add_argument("rest", nargs="*")
    ap.add_argument("--mow", default=",".join(POOL_MOW))
    ap.add_argument("--board", default="C1_02")
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()
    if a.cmd == "runners":
        sid = _resolve_session()
        print("sid=%s runners=%s"
              % (sid, json.dumps(_rpc(sid, "listRunners", [], timeout=15).get("result") or [])))
        return 0
    if a.cmd == "rpc":
        sid = _resolve_session()
        args = json.loads(a.rest[1]) if len(a.rest) > 1 else []
        print(json.dumps(_rpc(sid, a.rest[0], args, timeout=90), ensure_ascii=True)[:12000])
        return 0
    if not a.state_file:
        print("--state-file (ABSOLU, unique) requis")
        return 2
    if a.cmd == "sweep":
        return sweep([m for m in a.mow.split(",") if m], a.board, a.state_file)
    return offline(a.state_file)


if __name__ == "__main__":
    raise SystemExit(main())
