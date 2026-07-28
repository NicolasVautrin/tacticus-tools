"""MESURE du canal `OnToxicDamageAbility` (1203) — pose on-hit de `Contaminated` (1244).

Deux mesures, sur un runner ISOLE (`genesBiophagus` « Hollan », arme MELEE `Toxic` 1 coup) :

 A. COMPTE ET ORIGINE DES TIRAGES — instrumente `IntBasedMersenneTwister.next_internal`/`next` et
    trace la pile de chaque tirage consomme par `_on_toxic_damage_ability`. ATTENDU : **UN SEUL**
    (`MaybeTrigger.should_trigger` -> `next_bool`), mirror de
    `IdunBattleLogic.Entities.Abilities.Damage.Loki.OnToxicDamageAbility$$CreateBehaviour` =
    `If(IsFirstHitInSeries() & Maybe(ConfigConst(0x4b3, Self@0x148, 0x2a = chance)), AddEffect(0x4dc))`
    ou le ET natif (`IdunBattle.DSL.MultipleAbilityTrigger$$ShouldTrigger`) COURT-CIRCUITE.
    NB : `rng.call_count` n'est PAS un compteur de tirages (il est incremente par `next_internal` ET
    par `genrand_int32` -> +2 par `NextBool`) ; l'oracle de consommation est l'ETAT MT (`mt`/`mti`).

 B. CONTRE-EPREUVE DU PORT — pour chaque attaque, on rejoue le MEME coup sur DEUX etats offline issus
    du MEME snapshot et du MEME etat MT : l'un avec le canal ARME (le port), l'autre avec le canal
    DESARME (== l'etat du depot AVANT ce port : `OnToxicDamage` sans handler). On confronte les deux
    au LIVE. ATTENDU : le canal ARME concorde avec le live ; le canal DESARME DIVERGE des que le
    natif contamine (c'est la mesure du gap que ce port ferme).

Usage : python probe_1203_toxic_contamination.py
Pre-requis : session Frida vivante et WARMEE (aucun (re)inject ici). ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import traceback
import uuid
from pathlib import Path

import requests

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
HOST = "http://127.0.0.1:8765"
CARRIER_VIS = "genesBiophagus"
ESCORT_VIS = "adeptHospitaller"
CONTAMINATED = 1244
MAX_ATTACKS = 12


def _sid():
    return requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"]


def _rpc(sid, method, body=None, timeout=180):
    r = requests.post(f"{HOST}/api/scripts/{sid}/rpc",
                      json={"method": method, "args": [body] if body is not None else []},
                      timeout=timeout).json()
    return r.get("result", r)


def _build(sid):
    sf = ROOT / "logs" / "runners" / f"toxprobe-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "777", "--state-file", str(sf),
         "--board", "MC1_67", "--roster", "2",
         "--p-units", f"{CARRIER_VIS},{ESCORT_VIS}", "--a-units", "necroWarden,necroWarden"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        print("[probe] build KO:", (p.stderr or p.stdout)[-400:])
        return None, sf
    return json.loads(sf.read_text())["runnerId"], sf


def _tiles_with(sid, rid, board, effect_type):
    tm = _rpc(sid, "tileMeta", {"runnerId": rid}, 60) or {}
    out = set()
    for t in (tm.get("tiles") or []):
        if any(e.get("effectType") == effect_type for e in (t.get("effects") or [])):
            tid = board.id_at(t["col"], t["row"])
            if tid is not None:
                out.add(tid)
    return out


def _drive_to_contact(sid, rid, board):
    """Amene le porteur au contact (meme patron que le test live) -> (uid, target, abilityType)."""
    from collections import deque

    def bfs(src):
        dist, q = {src: 0}, deque([src])
        while q:
            x = q.popleft()
            for n in board.neighbours(x):
                if n not in dist and (n == src or board.walkable(n)):
                    dist[n] = dist[x] + 1
                    q.append(n)
        return dist

    my = None
    for _ in range(12):
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        units = dv.get("units") or []
        me = next((u for u in units if u.get("visualId") == CARRIER_VIS and u.get("alive")), None)
        if me is None:
            return None
        if my is None:
            my = me.get("owner")
        if dv.get("currentPlayer") != my:
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        norm = next((a for a in (me.get("abilities") or []) if a.get("kind") == "normal"), None)
        if norm is None:
            return None
        plan = next((ap for ap in (dv.get("attackPlans") or []) if ap.get("unitId") == me["id"]), None)
        ev = next((e for e in ((plan or {}).get("evals") or [])
                   if e.get("targetId") is not None and (e.get("ranked") or [])), None)
        if ev is not None:
            rk = ev["ranked"][0]
            if rk.get("col") is not None:
                _rpc(sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": me["id"], "to": {"col": rk["col"], "row": rk["row"]}}}, 60)
            return me["id"], ev["targetId"], norm["id"]
        pos = me.get("pos") or {}
        enemies = [u for u in units if u.get("owner") != my and u.get("alive") and (u.get("pos") or {})]
        if pos.get("col") is None or not enemies:
            return None
        tgt_pos = min(((u["pos"]["col"], u["pos"]["row"]) for u in enemies),
                      key=lambda p: abs(p[0] - pos["col"]) + abs(p[1] - pos["row"]))
        dist = bfs(board.id_at(*tgt_pos))
        mt = _rpc(sid, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60) or {}
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == me["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dist]
        if pool:
            col, row = reach[min(pool, key=lambda t: dist[t])]
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": col, "row": row}}}, 60)
        _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None


def _mesure_a(sid, rid, board):
    """(A) compte + origine des tirages consommes par le canal, sur l'etat courant du runner."""
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import UnitComponent, OwnerComponent
    # DE-FORK : le canal 1203 n'est plus une fonction appelee imperativement, c'est un consommateur du
    # vecteur `On(DamageDealt = 0x10)` (registre `GLOBAL_TRIGGERS`). On l'exerce donc par son VECTEUR.
    from engine.runner.operations.triggers.dispatch import damage_dealt_triggers

    dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
    s0 = _rpc(sid, "dumpRng", {"runnerId": rid}, 30)
    st = load_state(dv, ob, snap, board=board)
    rng = IntBasedMersenneTwister()
    rng.mt = list(s0["mt"])
    rng.mti = s0["mti"]
    st.rng = rng
    att = next((eid for eid, e in st.entities.items()
                if (e.get_component(UnitComponent) or None) is not None
                and e.get_component(UnitComponent).visual_id == CARRIER_VIS), None)
    mine = st.get_entity(att).get_component(OwnerComponent)
    tgt = next((eid for eid, e in st.entities.items()
                if e.get_component(UnitComponent) is not None
                and e.get_component(UnitComponent).alive
                and e.get_component(OwnerComponent) is not None
                and e.get_component(OwnerComponent).team != mine.team), None)

    traces, origs = [], {n: getattr(IntBasedMersenneTwister, n) for n in ("next_internal", "next")}

    def _wrap(name, fn):
        def traced(self, *a, **kw):
            traces.append((name, "".join(traceback.format_stack(limit=16)[:-1])))
            return fn(self, *a, **kw)
        return traced

    for n, fn in origs.items():
        setattr(IntBasedMersenneTwister, n, _wrap(n, fn))
    mt_before = (list(st.rng.mt), st.rng.mti)
    out = [r for r in (damage_dealt_triggers(st, att, tgt, profile="Toxic", is_first_hit=True) or [])
           if r.get("placement") == "OnToxicDamage"]
    for n, fn in origs.items():
        setattr(IntBasedMersenneTwister, n, fn)

    ref = IntBasedMersenneTwister()
    ref.mt, ref.mti = list(mt_before[0]), mt_before[1]
    verdict = ref.next_bool(25)
    same = (list(st.rng.mt), st.rng.mti) == (list(ref.mt), ref.mti)
    print(f"[A] tirages traces={len(traces)} (attendu 1) ; MT == 1x next_bool ? {same} ; "
          f"verdict predit={verdict} ; pose={bool(out)}")
    for i, (name, t) in enumerate(traces):
        print(f"    roll {i} via {name} :")
        for line in t.splitlines():
            s = line.strip()
            if "engine" in s and ".py" in s:
                print("       ", s)


def _mesure_b(sid, rid, board):
    """(B) contre-epreuve : canal ARME vs DESARME, confrontes au LIVE, attaque par attaque."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import PositionComponent
    # DE-FORK : le canal 1203 est desormais une entree du registre GLOBAL. Le « desarmer » = le RETIRER
    # de `GLOBAL_TRIGGERS` (le dict/liste est re-exporte PAR VALEUR, donc une mutation porte), au lieu
    # de neutraliser un symbole dans `dispatch.attack`.
    from engine.runner.operations.triggers.dispatch import registry as REG
    from engine.runner.operations.triggers.loki import OnToxicDamageAbility

    armed_ok = disarmed_ok = placements = compared = 0
    for attempt in range(MAX_ATTACKS):
        drive = _drive_to_contact(sid, rid, board)
        if drive is None:
            break
        uid, tgt, ability = drive
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
        s0 = _rpc(sid, "dumpRng", {"runnerId": rid}, 30)

        def _fresh():
            st = load_state(dv, ob, snap, board=board)
            r = IntBasedMersenneTwister()
            r.mt = list(s0["mt"])
            r.mti = s0["mti"]
            st.rng = r
            return st

        st_ref = _fresh()
        pc = st_ref.get_entity(tgt).get_component(PositionComponent)
        tile = board.id_at(pc.col, pc.row) if pc is not None else None
        if tile is None or tile in _tiles_with(sid, rid, board, CONTAMINATED):
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue

        res = _rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": uid, "targetId": tgt, "abilityType": ability}}, 60)
        if not (isinstance(res, dict) and res.get("ok")):
            _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        live = tile in _tiles_with(sid, rid, board, CONTAMINATED)

        st_a = _fresh()
        Runner(st_a).install_default_handlers(20).apply(AttackUnitMessage(uid, tgt))
        armed = st_a.effects.has_effect(tile, effect_type=CONTAMINATED)

        # canal DESARME = l'etat du depot AVANT ce port (aucun handler pour 1203) : on RETIRE l'entree
        # du registre GLOBAL, que `core.collect_global_triggers` relit a chaque dispatch.
        saved = list(REG.GLOBAL_TRIGGERS)
        REG.GLOBAL_TRIGGERS[:] = [c for c in saved if c is not OnToxicDamageAbility]
        st_d = _fresh()
        try:
            Runner(st_d).install_default_handlers(20).apply(AttackUnitMessage(uid, tgt))
        finally:
            REG.GLOBAL_TRIGGERS[:] = saved
        disarmed = st_d.effects.has_effect(tile, effect_type=CONTAMINATED)

        compared += 1
        placements += int(live)
        armed_ok += int(armed == live)
        disarmed_ok += int(disarmed == live)
        print(f"[B] attaque #{attempt} tuile={tile} live={live} arme={armed} desarme={disarmed}")
        if live:
            break
        _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    print(f"[B] confrontees={compared} poses_live={placements} "
          f"accord_canal_ARME={armed_ok}/{compared} accord_canal_DESARME={disarmed_ok}/{compared}")


def main() -> int:
    sid = _sid()
    rid, sf = _build(sid)
    if rid is None:
        return 1
    try:
        from engine.entities.pathfinding.board import Board
        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")
        _mesure_a(sid, rid, board)
        _mesure_b(sid, rid, board)
        return 0
    finally:
        _rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
        sf.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
