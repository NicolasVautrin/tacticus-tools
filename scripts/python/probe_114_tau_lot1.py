"""Probe #114 -- montage LIVE des deux confrontations du lot Tau 1 (face COMBAT).

Sert a EXPLORER/mesurer avant d'ecrire les tests : monte un runner isole, DRIVE les positions pour
obtenir la configuration voulue, lit `abilityTargets(...).fromHere` (LEGALITE du cast depuis la
position courante -- #111 : une cible prise dans `targets` peut etre illegale sur place et rendre un
cast `mutated:false` trompeusement identique a « l'ability ne fait rien »), puis rejoue le MEME cast
OFFLINE (`_apply_active_ability`) et LIVE, et diffe l'empreinte d'effets.

Usage (depuis scripts/python) :
    python probe_114_tau_lot1.py fr        # FightingRetreat 1081 (tauDarkstrider)
    python probe_114_tau_lot1.py ewo       # EarlyWarningOverride 1077 (tauCrisis)

Sorties ASCII only (cp1252).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
PYDIR = Path(__file__).resolve().parent
DATA = PYDIR.parents[1] / "data"
AGENT = "aca3ce9d9a19ff4f9"


def _session() -> int:
    st = requests.get(f"{HOST}/api/admin/status", timeout=20).json()
    return int(st["session"]["id"])


def rpc(sid: int, method: str, body: dict, timeout: int = 90):
    r = requests.post(f"{HOST}/api/scripts/{sid}/rpc",
                      json={"method": method, "args": [body], "timeout": int(timeout * 1000)},
                      timeout=timeout + 5).json()
    return r.get("result", r)


def build(state_path: Path, args: list) -> str:
    proc = subprocess.run([sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)]
                          + args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_path.exists():
        print((proc.stderr or proc.stdout or "")[-1500:])
        raise SystemExit("build KO")
    return json.loads(state_path.read_text())["runnerId"]


def load(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    tiles = rpc(sid, "tileMeta", {"runnerId": rid}, 60)
    return load_state(dec, ob, snap, board=board, tiles=tiles), board, dec, ob


def footprint_live(sid, rid) -> dict:
    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    out = {}
    for u in (dec.get("units") or []):
        effs = {int(e["effectType"]): e.get("remaining") for e in (u.get("effects") or [])
                if e.get("effectType") is not None}
        out[int(u["id"])] = effs
    return out


def footprint_off(state) -> dict:
    out = {}
    for key, effs in (state.effects.by_unit if state.effects is not None else {}).items():
        out[int(key)] = {int(e.effect_type): (0 if e.remaining_turns is None else int(e.remaining_turns))
                         for e in effs if not e.consumed}
    return out


def delta(before, after) -> dict:
    out = {}
    for k, effs in after.items():
        new = {et: rem for et, rem in effs.items() if et not in (before.get(k) or {})}
        if new:
            out[int(k)] = new
    return out


def units_of(dec):
    return {int(u["id"]): u for u in (dec.get("units") or [])}


def from_here(sid, rid, caster, ability):
    """Cibles LEGALES DEPUIS LA POSITION COURANTE (`fromHere`) -- PAS `targets` (superset move-inclus)."""
    at = rpc(sid, "abilityTargets", {"runnerId": rid, "unitId": caster, "abilityType": ability}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster), None)
    ab = ((row or {}).get("abilities") or [{}])[0]
    return ab.get("fromHere") or [], ab.get("targets") or []


def show(sid, rid, tag=""):
    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    print(f"-- {tag} currentPlayer={dec.get('currentPlayer')}")
    for u in (dec.get("units") or []):
        p = u.get("pos") or {}
        effs = [e.get("name") for e in (u.get("effects") or [])]
        print(f"   u{u['id']:<4} {u.get('visualId'):<16} team={u.get('team')} "
              f"pos=({p.get('col')},{p.get('row')}) effects={effs}")
    return dec


def scenario_fr(sid):
    """FightingRetreat : rapproche Darkstrider d'un ork jusqu'a l'ADJACENCE, laisse l'ork engager,
    puis caste au tour SUIVANT (Darkstrider a DEMARRE adjacent -> RangedSpecialist DESACTIVE)."""
    import hexgeo
    state_path = DATA / f"_probe114_fr_{AGENT}.json"
    rid = build(state_path, ["--seed", "114001", "--board", "MC1_67",
                             "--p-units", "tauDarkstrider,tauCrisis",
                             "--a-units", "orksNob,orksNob", "--hp-player", "60000"])
    print("runnerId", rid)
    for it in range(6):
        dec = show(sid, rid, f"iter{it}")
        us = units_of(dec)
        mine = [u for u in us.values() if u.get("team") == 1]
        foes = [u for u in us.values() if u.get("team") != 1]
        ds = next((u for u in mine if u.get("visualId") == "tauDarkstrider"), None)
        if ds is None:
            break
        dpos = (ds["pos"]["col"], ds["pos"]["row"])
        dist = min(hexgeo.distance(dpos, (f["pos"]["col"], f["pos"]["row"])) for f in foes)
        fh, tg = from_here(sid, rid, ds["id"], 1081)
        print(f"   dist_min={dist} fromHere={len(fh)} targets={len(tg)}")
        if dist == 1 and fh:
            return rid, ds["id"]
        # avancer Darkstrider vers l'ork le plus proche (tuile de move la plus proche de lui)
        near = min(foes, key=lambda f: hexgeo.distance(dpos, (f["pos"]["col"], f["pos"]["row"])))
        npos = (near["pos"]["col"], near["pos"]["row"])
        mvs = rpc(sid, "aiMovableTiles", {"runnerId": rid}, 60) or {}
        row = next((u for u in (mvs.get("units") or []) if u.get("unitId") == ds["id"]), None)
        cands = [(t.get("col"), t.get("row")) for t in ((row or {}).get("tiles") or [])]
        if cands:
            best = min(cands, key=lambda q: hexgeo.distance(q, npos))
            print(f"   move u{ds['id']} -> {best}")
            rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": ds["id"], "to": {"col": best[0], "row": best[1]}}}, 90)
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    return rid, None


def confront(sid, rid, caster, ability):
    from engine.runner.operations.summon_ai import _apply_active_ability
    state, board, dec, ob = load(sid, rid)
    off_before = footprint_off(state)
    res = _apply_active_ability(state, caster, caster, ability)
    diag = (res or {}).get("diag") or {}
    off = delta(off_before, footprint_off(state))
    print("OFFLINE routed=", (res or {}).get("routed"), "ported=", diag.get("ported"))
    print("OFFLINE diag=", json.dumps({k: v for k, v in diag.items() if k != "flags"}, default=str)[:1200])
    print("OFFLINE delta=", off)
    live_before = footprint_live(sid, rid)
    r = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster, "abilityType": ability, "targetId": caster}}, 90) or {}
    act = (r.get("actions") or [{}])[0]
    print("LIVE act=", json.dumps({k: act.get(k) for k in
                                   ("ok", "mutated", "actionConsumed", "error", "events")})[:400])
    live = delta(live_before, footprint_live(sid, rid))
    print("LIVE delta=", live)
    print("MATCH" if off == live else "DIVERGENCE")
    return off, live, diag


def scenario_fr2(sid):
    """GENERALISATION FightingRetreat : Darkstrider NON adjacent a un ennemi, mais adjacent a un ALLIE
    (`tauCrisis`) dont le `RangedSpecialist` est DESACTIVE (il a demarre son tour au contact d'un ork).
    -> le cast reste LEGAL (`GetDynamicInvalidTargetReason` : branche `HasDeactivatedRangedSpecialist`),
    le 4e volet re-active le trait de L'ALLIE, et le 5e volet prend la branche `FinishTurn` (0 ennemi
    adjacent au caster)."""
    import hexgeo
    state_path = DATA / f"_probe114_fr2_{AGENT}.json"
    rid = build(state_path, ["--seed", "114003", "--board", "MC1_67", "--no-ai",
                             "--p-units", "tauCrisis,tauDarkstrider",
                             "--a-units", "orksNob,orksNob", "--hp-player", "60000"])
    print("runnerId", rid)
    for it in range(8):
        dec = show(sid, rid, f"iter{it}")
        us = units_of(dec)
        rv = next((u for u in us.values() if u.get("visualId") == "tauCrisis"), None)
        ds = next((u for u in us.values() if u.get("visualId") == "tauDarkstrider"), None)
        foes = [u for u in us.values() if u.get("team") != 1]
        if rv is None or ds is None or not foes:
            break
        rpos = (rv["pos"]["col"], rv["pos"]["row"])
        dpos = (ds["pos"]["col"], ds["pos"]["row"])
        near = min(foes, key=lambda f: hexgeo.distance(rpos, (f["pos"]["col"], f["pos"]["row"])))
        npos = (near["pos"]["col"], near["pos"]["row"])
        d_rv, d_ds = hexgeo.distance(rpos, npos), hexgeo.distance(dpos, npos)
        fh, tg = from_here(sid, rid, ds["id"], 1081)
        print(f"   d(rv,ork)={d_rv} d(ds,ork)={d_ds} d(ds,rv)={hexgeo.distance(dpos, rpos)} "
              f"fromHere={len(fh)}")
        if d_rv == 1 and d_ds >= 2 and hexgeo.distance(dpos, rpos) == 1 and fh:
            return rid, ds["id"], rv["id"]
        mvs = rpc(sid, "aiMovableTiles", {"runnerId": rid}, 60) or {}

        def _tiles(uid):
            row = next((u for u in (mvs.get("units") or []) if u.get("unitId") == uid), None)
            return [(t.get("col"), t.get("row")) for t in ((row or {}).get("tiles") or [])]

        # 1) Re'vas au CONTACT de l'ork ; 2) Darkstrider adjacent a Re'vas mais >=2 de l'ork.
        rv_c = _tiles(rv["id"])
        if rv_c:
            tgt = min(rv_c, key=lambda q: (abs(hexgeo.distance(q, npos) - 1), hexgeo.distance(q, npos)))
            rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": rv["id"], "to": {"col": tgt[0], "row": tgt[1]}}}, 90)
            rpos = tgt
        ds_c = _tiles(ds["id"])
        if ds_c:
            ok = [q for q in ds_c if hexgeo.distance(q, rpos) == 1 and hexgeo.distance(q, npos) >= 2]
            tgt = (ok[0] if ok else min(ds_c, key=lambda q: hexgeo.distance(q, rpos)))
            rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": ds["id"], "to": {"col": tgt[0], "row": tgt[1]}}}, 90)
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
    return rid, None, None


def scenario_itg(sid):
    """InspiredToGreatness : Re'vas ENDOMMAGEE (elle encaisse les orks) puis AYANT CONSOMME son actif
    (cast EWO) ; Aun'Shi adjacent la cible avec 1082 -> branche `canReset` (petit montant `hpToHeal`),
    REPAIR (Re'vas est Mechanical) + override de niveau + re-armement de l'actif."""
    import hexgeo
    state_path = DATA / f"_probe114_itg_{AGENT}.json"
    rid = build(state_path, ["--seed", "114004", "--board", "MC1_67",
                             "--p-units", "tauCrisis,tauAunShi",
                             "--a-units", "orksNob,orksNob", "--hp-player", "60000"])
    print("runnerId", rid)
    for it in range(8):
        dec = show(sid, rid, f"iter{it}")
        ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40) or {}
        hp = {u["squadId"]: (u["hp"], u["hpMax"]) for u in (ob.get("units") or [])}
        us = units_of(dec)
        rv = next((u for u in us.values() if u.get("visualId") == "tauCrisis"), None)
        au = next((u for u in us.values() if u.get("visualId") == "tauAunShi"), None)
        foes = [u for u in us.values() if u.get("team") != 1]
        if rv is None or au is None or not foes:
            break
        print("   hp", {k: v for k, v in hp.items()})
        if hp.get(rv["id"], (1, 1))[0] < hp.get(rv["id"], (1, 1))[1]:
            return rid, au["id"], rv["id"]
        rpos = (rv["pos"]["col"], rv["pos"]["row"])
        near = min(foes, key=lambda f: hexgeo.distance(rpos, (f["pos"]["col"], f["pos"]["row"])))
        npos = (near["pos"]["col"], near["pos"]["row"])
        mvs = rpc(sid, "aiMovableTiles", {"runnerId": rid}, 60) or {}

        def _tiles(uid):
            row = next((u for u in (mvs.get("units") or []) if u.get("unitId") == uid), None)
            return [(t.get("col"), t.get("row")) for t in ((row or {}).get("tiles") or [])]

        c = _tiles(rv["id"])
        if c:
            rpos = min(c, key=lambda q: hexgeo.distance(q, npos))
            rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": rv["id"], "to": {"col": rpos[0], "row": rpos[1]}}}, 90)
        c = _tiles(au["id"])
        if c:
            ok = [q for q in c if hexgeo.distance(q, rpos) == 1]
            t = ok[0] if ok else min(c, key=lambda q: hexgeo.distance(q, rpos))
            rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": au["id"], "to": {"col": t[0], "row": t[1]}}}, 90)
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
        # tour ADVERSE joue par l'IA NATIVE -> les orks chargent et FRAPPENT Re'vas (`applyAction
        # endturn` seul ne fait PAS jouer l'IA : il rend la main sans qu'elle agisse).
        print("   aiturn ->", rpc(sid, "aiPlayByUnit", {"runnerId": rid, "maxTurns": 1,
                                                        "maxActivations": 9999}, 180))
    return rid, None, None


def confront_itg(sid, rid, caster, target):
    from engine.runner.operations.summon_ai import _apply_active_ability
    from engine.runner.components import HealthComponent

    def hp_live():
        ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40) or {}
        return {u["squadId"]: u["hp"] for u in (ob.get("units") or [])}

    def hp_off(state):
        return {eid: e.get_component(HealthComponent).hp for eid, e in state.entities.items()
                if e.get_component(HealthComponent) is not None}

    # (1) Re'vas CONSOMME son actif -> `CanStillBeUsed = false` -> elle entre dans `canReset`.
    rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": target, "abilityType": 1077, "targetId": target}}, 90)
    fh = from_here(sid, rid, caster, 1082)[0]
    print("fromHere(1082) =", fh)
    state, board, dec, ob = load(sid, rid)
    off_hp_before, off_eff_before = hp_off(state), footprint_off(state)
    res = _apply_active_ability(state, caster, target, 1082)
    diag = (res or {}).get("diag") or {}
    print("OFFLINE diag=", json.dumps({k: v for k, v in diag.items() if k != "flags"}, default=str)[:1400])
    off_hp = {k: v - off_hp_before[k] for k, v in hp_off(state).items()
              if k in off_hp_before and v != off_hp_before[k]}
    off_eff = delta(off_eff_before, footprint_off(state))
    live_hp_before, live_eff_before = hp_live(), footprint_live(sid, rid)
    r = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster, "abilityType": 1082, "targetId": target}}, 90) or {}
    act = (r.get("actions") or [{}])[0]
    print("LIVE act=", json.dumps({k: act.get(k) for k in
                                   ("ok", "mutated", "actionConsumed", "error")}))
    live_hp = {k: v - live_hp_before[k] for k, v in hp_live().items()
               if k in live_hp_before and v != live_hp_before[k]}
    live_eff = delta(live_eff_before, footprint_live(sid, rid))
    print("OFFLINE dHP=", off_hp, " effets=", off_eff)
    print("LIVE    dHP=", live_hp, " effets=", live_eff)
    dec2 = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    for u in (dec2.get("units") or []):
        if u.get("id") == target:
            print("LIVE abilities cible =", json.dumps(u.get("abilities"))[:400])
    return diag


def scenario_ewo(sid):
    state_path = DATA / f"_probe114_ewo_{AGENT}.json"
    rid = build(state_path, ["--seed", "114002", "--board", "MC1_67",
                             "--p-units", "tauCrisis,tauDarkstrider",
                             "--a-units", "orksNob,orksNob"])
    print("runnerId", rid)
    dec = show(sid, rid, "start")
    us = units_of(dec)
    rv = next(u for u in us.values() if u.get("visualId") == "tauCrisis")
    fh, tg = from_here(sid, rid, rv["id"], 1077)
    print("   fromHere=", fh, " targets=", len(tg))
    return rid, rv["id"]


if __name__ == "__main__":
    sid = _session()
    what = sys.argv[1] if len(sys.argv) > 1 else "fr"
    if what == "fr":
        rid, caster = scenario_fr(sid)
        if caster is None:
            print("scenario NON atteint (pas d'adjacence)")
        else:
            confront(sid, rid, caster, 1081)
            show(sid, rid, "post-cast")
    elif what == "itg":
        rid, caster, target = scenario_itg(sid)
        if caster is None:
            print("scenario itg NON atteint (Re'vas jamais blessee)")
        else:
            confront_itg(sid, rid, caster, target)
    elif what == "fr2":
        rid, caster, ally = scenario_fr2(sid)
        if caster is None:
            print("scenario fr2 NON atteint")
        else:
            print(f"caster={caster} ally={ally}")
            confront(sid, rid, caster, 1081)
            show(sid, rid, "post-cast")
    else:
        rid, caster = scenario_ewo(sid)
        confront(sid, rid, caster, 1077)
        show(sid, rid, "post-cast")
    print("runner", rid, "-- disposer avec: rl_duel.py dispose --runner", rid)
