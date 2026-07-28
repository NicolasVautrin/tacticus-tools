#!/usr/bin/env python
"""probe case-231 -- confront LIVE/OFFLINE de TacticalPrecision (1154) et MomentShackle (1184).

MESURE (ce probe ne garde rien -- le cliquet est dans `tests/engine/runner/test_case231_*_live.py`) :
  * `--case tp` : cast 1154 sur un runner DEJA positionne, offline d'abord (etat + rng dumpes), live
    ensuite, puis diff des degats PAR CIBLE. `--charge` declare quel volet on attend.
  * `--case ms` : cast 1184 (self-cast), diff du HEAL et des effets/stat-mods poses.

Usage (depuis scripts/python, session warmee, runner deja construit et positionne) :
    python probe_231_charge_and_forcecrit.py --runner <id> --case tp --caster <u> --target <u>
    python probe_231_charge_and_forcecrit.py --runner <id> --case ms --caster <u>

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request

HOST = "http://127.0.0.1:8765"


def _http(path, method="GET", body=None, timeout=90.0):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(HOST + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def session_id():
    st = _http("/api/admin/status")
    return int((st.get("session") or {}).get("id"))


def rpc(sid, method, args, timeout=90.0):
    out = _http("/api/scripts/%d/rpc" % sid, "POST",
                {"method": method, "args": args, "timeout": int(timeout * 1000)}, timeout + 10)
    return out.get("result")


def seed_rng(state, dump):
    from engine.runner.prng import IntBasedMersenneTwister
    if isinstance(dump, dict) and dump.get("mt"):
        r = IntBasedMersenneTwister()
        r.mt = list(dump["mt"])
        r.mti = dump["mti"]
        state.rng = r


def load(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc(sid, "boardGraph", [{"runnerId": rid}], 60)
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = rpc(sid, "decisionView", [{"runnerId": rid, "maxRank": 1, "allAbilities": True}], 90)
    ob = rpc(sid, "observeBattle", [{"runnerId": rid}], 40)
    snap = rpc(sid, "combatSnapshot", [{"runnerId": rid}], 60)
    rng0 = rpc(sid, "dumpRng", [{"runnerId": rid}], 30)
    st = load_state(dv, ob, snap, board=board)
    seed_rng(st, rng0)
    return st, dv, ob


def hp_map(ob):
    """PV live par id d'unite. `observeBattle.units` porte `squadId` (= l'id du decisionView, celui
    que le port utilise comme id d'entite) et `entityId` (l'entite ECS interne) -- on cle sur
    `squadId`, sinon aucune ligne ne se recoupe avec l'etat offline."""
    return {int(u["squadId"]): int(u.get("hp") or 0)
            for u in (ob.get("units") or []) if u.get("squadId") is not None}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, required=True)
    ap.add_argument("--case", choices=("tp", "ms"), required=True)
    ap.add_argument("--caster", type=int, required=True)
    ap.add_argument("--target", type=int, default=None)
    ap.add_argument("--pre-move", default=None, metavar="COL,ROW",
                    help="deplace le caster AVANT le cast, des DEUX cotes (live applyAction + "
                         "offline MoveUnitMessage) -- c'est ce move qui remplit ChargedUnitIds")
    a = ap.parse_args(argv)

    sid = session_id()
    rid = a.runner
    st, dv, ob = load(sid, rid)
    from engine.runner.components import UnitComponent
    before = hp_map(ob)

    if a.pre_move:
        # Le MOVE est joue des DEUX cotes : c'est LUI qui doit alimenter `ChargedUnitIds` offline
        # (mirror `MoveUnitOperation$$UpdateCharging`). Le declarer a la main court-circuiterait
        # justement le morceau de port qu'on veut confronter.
        col, row = (int(x) for x in a.pre_move.split(","))
        from engine.runner.runner import Runner
        from engine.runner.messages import MoveUnitMessage
        # `install_default_handlers()` est INDISPENSABLE : un `Runner` nu n'a AUCUN visiteur, donc
        # `apply` ne fait rien (piege vecu : `charged_unit_ids` restait vide et le port paraissait
        # faux alors que le move n'avait simplement pas eu lieu offline).
        Runner(st).install_default_handlers().apply(MoveUnitMessage(a.caster, (col, row)))
        lv = rpc(sid, "applyAction", [{"runnerId": rid, "action": {
            "kind": "move", "unitId": a.caster, "to": {"col": col, "row": row}}}], 40)
        print("[live move] ok=%s events=%s" % (lv.get("ok"), (lv.get("actions") or [{}])[0]
                                               .get("eventCount")))
        # RE-SEED apres le move : le flux MT live a pu bouger (cascade after-move) ; on repart du
        # MEME etat de PRNG des deux cotes pour que le CAST seul soit compare.
        seed_rng(st, rpc(sid, "dumpRng", [{"runnerId": rid}], 30))
        uc = st.get_entity(a.caster).get_component(UnitComponent)
        print("[off] charged_unit_ids apres move = %s" % sorted(uc.charged_unit_ids))

    if a.case == "tp":
        from engine.runner.abilities.ultramarines import TacticalPrecisionAbility
        off = TacticalPrecisionAbility().execute_behaviour(st, a.caster, a.target)
        print("[off] charging=%s crit=%s attacks=%s"
              % (off.get("charging"), off.get("crit_amount"), off.get("attacks")))
        act = {"kind": "ability", "casterId": a.caster, "targetId": a.target, "abilityType": 1154}
    else:
        from engine.runner.abilities.custodes import MomentShackleAbility
        off = MomentShackleAbility().execute_behaviour(st, a.caster, a.caster)
        print("[off] heal_amount=%s turns=%s heals=%s posed=%s"
              % (off.get("heal_amount"), off.get("turns"), off.get("heals"), off.get("posed")))
        act = {"kind": "ability", "casterId": a.caster, "targetId": a.caster, "abilityType": 1184}

    off_hp = {}
    for uid in before:
        e = st.get_entity(uid)
        from engine.runner.components import HealthComponent
        hc = e.get_component(HealthComponent) if e is not None else None
        off_hp[uid] = int(hc.hp or 0) if hc is not None else 0

    res = rpc(sid, "applyAction", [{"runnerId": rid, "action": act}], 60)
    print("[live] ok=%s mutated=%s" % (res.get("ok"), res.get("mutated")))
    ob2 = rpc(sid, "observeBattle", [{"runnerId": rid}], 40)
    after = hp_map(ob2)

    print("%-6s %-10s %-10s %-10s %-10s %s" % ("unit", "hp_before", "live_after", "off_after",
                                               "live_d", "off_d"))
    ok = True
    for uid in sorted(before):
        lv, of = after.get(uid, 0), off_hp.get(uid, 0)
        ld, od = lv - before[uid], of - before[uid]
        flag = "" if lv == of else "   <-- MISMATCH"
        ok = ok and lv == of
        print("%-6s %-10s %-10s %-10s %-10s %s%s" % (uid, before[uid], lv, of, ld, od, flag))
    print("VERDICT: %s" % ("MATCH" if ok else "MISMATCH"))

    # STAT-MODS du caster : le SEUL observable de MomentShackle a cote du heal (les deux
    # `DynamicStatModifierEffect` 1391/1392). `statModSources` rend le total PAR STAT et PAR SOURCE.
    sm = rpc(sid, "statModSources", [{"runnerId": rid}], 40)
    live_mods = {}
    for u in ((sm or {}).get("units") or []):
        if int(u.get("entityId") or -1) == int(a.caster):
            live_mods = {k: v.get("total") for k, v in (u.get("mods") or {}).items()}
    from engine.runner.components import StatsComponent
    ce = st.get_entity(a.caster)
    csc = ce.get_component(StatsComponent) if ce is not None else None
    off_mods = {}
    if csc is not None and getattr(csc.ctx, "stats", None) is not None:
        for name, stat in (("blockChance", 7), ("blockDamage", 8), ("critDamage", 10)):
            comp = csc.ctx.stats.components.get(stat)
            mod = getattr(comp, "modification", None) if comp is not None else None
            off_mods[name] = int(mod.total) if mod is not None and not callable(
                getattr(mod, "total", None)) else (int(mod.total()) if mod is not None else None)
    print("[mods] live blockChance=%s blockDamage=%s | off %s"
          % (live_mods.get("blockChance"), live_mods.get("blockDamage"), off_mods))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

