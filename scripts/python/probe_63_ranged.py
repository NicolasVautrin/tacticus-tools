"""probe_63_ranged : reproduction RANGED (positions drivees) de la divergence armure #63.

Le prompt cite templHelbrecht BOLTER (arme RANGED p20) et necroDestroyer GAUSS. La mesure #63 vient
du port PsychicFortress ou l'attaquant tape a DISTANCE (applyAction ignore la portee). On place
l'attaquant a distance `dist` (defaut 2) de la cible, on cale son tour, on rejoue l'attaque normale
live+offline et on decompose par etage (arme choisie, pierce, armor, base range, per-hit).

Discipline : state-file ABSOLU unique ; dispose runner ; ASCII only.
Usage : python probe_63_ranged.py [ATT] [TGT] [DIST]
"""
from __future__ import annotations

import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tests", "engine", "runner"))

import rl_collect_batch as R                                    # noqa: E402
import hexgeo                                                   # noqa: E402
from engine.runner.snapshot import load_state                  # noqa: E402
from engine.runner.runner import Runner                        # noqa: E402
from engine.runner.messages import AttackUnitMessage           # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister         # noqa: E402
from engine.runner.components import HealthComponent, StatsComponent, PositionComponent  # noqa: E402
from engine.runner.damage_model import select_weapon_pierce, select_weapon, defender_fixed_armor  # noqa: E402

_SID = R._resolve_session()
_STATE = os.path.abspath(os.path.join(          # SORTIE -> logs/, jamais data/ (#349)
    os.path.dirname(__file__), "..", "..", "logs", "runners",
    "_probe63r_a5a63eef_state.json"))
_BOARD = "MC1_67"
_created = []


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _rpc(method, body=None, timeout=60):
    return _unwrap(R._rpc(_SID, method, [body] if body is not None else [], timeout=timeout))


def _seed_rng(s):
    rng = IntBasedMersenneTwister(); rng.mt = list(s["mt"]); rng.mti = s["mti"]; return rng


def _build(att, tgt, seed="777"):
    import subprocess
    pydir = os.path.dirname(os.path.abspath(__file__))
    extra = ["--roster", "1", "--p-units", att, "--a-units", tgt, "--board", _BOARD]
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", _STATE, *extra],
        cwd=pydir, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.exists(_STATE):
        raise RuntimeError(f"build KO: {(proc.stderr or proc.stdout or '')[-400:]}")
    st = json.loads(open(_STATE).read()); rid = st["runnerId"]; _created.append(rid)
    return rid


def _unit(dv, vid):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vid and u.get("alive")), None)


def _p(u):
    q = u.get("pos") or {}
    return (q.get("col"), q.get("row"))


def run(att, tgt, dist=2):
    rid = _build(att, tgt)
    bg = _rpc("boardGraph", {"runnerId": rid}, 60)
    dv = _rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ua, ut = _unit(dv, att), _unit(dv, tgt)
    if not (ua and ut):
        print("  SKIP: unite manquante"); return
    aid, tid = ua["id"], ut["id"]
    a_owner = ua.get("owner")
    # place la cible a une position centrale, l'attaquant a distance `dist`
    tcol, trow = 3, 4
    _rpc("applyAction", {"runnerId": rid, "action": {"kind": "move", "unitId": tid,
                                                     "to": {"col": tcol, "row": trow}}}, 40)
    # choisir une case a distance hex `dist` de la cible
    dest = None
    for col in range(0, 12):
        for row in range(0, 12):
            if hexgeo.distance((col, row), (tcol, trow)) == dist:
                dest = (col, row); break
        if dest:
            break
    _rpc("applyAction", {"runnerId": rid, "action": {"kind": "move", "unitId": aid,
                                                     "to": {"col": dest[0], "row": dest[1]}}}, 40)
    for _ in range(4):
        dv = _rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if dv.get("currentPlayer") == a_owner:
            break
        _rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

    dv = _rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ua, ut = _unit(dv, att), _unit(dv, tgt)
    if not (ua and ut):
        print("  SKIP: unite manquante post-move"); return
    aid, tid = ua["id"], ut["id"]
    d_at = hexgeo.distance(_p(ua), _p(ut))
    ob = _rpc("observeBattle", {"runnerId": rid}, 40)
    snap = _rpc("combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv, ob, snap)
    # TEST DECISIF #63 : charger le board dans state (load_state ne le fait PAS -> apply_elevation_bonus
    # no-op). Sous LOAD_BOARD=1, on cale state.board depuis boardGraph et on dumpe les elevations.
    if os.environ.get("LOAD_BOARD") == "1":
        from engine.entities.pathfinding.board import Board
        state.board = Board(bg["tiles"], adjacency="native_sym")
        ta = state.board.tile_at(*_p(ua)); tt = state.board.tile_at(*_p(ut))
        print("  BOARD LOADED elev att=", (ta or {}).get("elevation"),
              "elev tgt=", (tt or {}).get("elevation"))
    ae = state.get_entity(aid); te = state.get_entity(tid)
    if ae is None or ae.get_component(StatsComponent) is None:
        print("  SKIP: attaquant sans stats offline"); return
    hc = te.get_component(HealthComponent) if te else None
    if hc is None or hc.hp is None:
        print("  SKIP: cible sans HP offline"); return
    ctx = ae.get_component(StatsComponent).ctx
    # etage: arme/pierce selon distance (le combat calcule adj via are_tiles_adjacent -> ici dist>=2)
    from engine.entities.stats import StatType
    pierce, ranged, whits = select_weapon_pierce(ctx, d_at)
    w = select_weapon(ctx, d_at)
    armor = defender_fixed_armor(state, tid)
    base = ctx.stat(StatType.ATTACK)
    norm = next((ab for ab in (ua.get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        print("  SKIP: pas d'attaque normale"); return
    s0 = _rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(s0, dict) and "mt" in s0):
        print("  SKIP: dumpRng KO"); return
    state.rng = _seed_rng(s0)
    runner = Runner(state).install_default_handlers(20)
    res = _rpc("applyAction", {"runnerId": rid, "action": {"kind": "ability", "casterId": aid,
                                                          "targetId": tid, "abilityType": norm["id"]}}, 40)
    a0 = (res.get("actions") or [{}])[0]
    if not a0.get("ok"):
        print(f"  SKIP: attaque live KO: {str(res)[:160]}"); return
    live_ph = []; dc = db = de = False
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == norm["id"]:
            live_ph.append(td.get("Amount"))
            dc = dc or bool(td.get("Attack_DidCrit")); db = db or bool(td.get("Attack_DidBlock"))
            de = de or bool(td.get("Attack_DidEvade"))
    runner.apply(AttackUnitMessage(aid, tid))
    rr = runner.damage_handler.last or {}
    off_ph = rr.get("per_hit")
    print(f"ATT {att} TGT {tgt} dist={d_at} weaponProfile={w.get('DamageProfile') if w else None} "
          f"ranged={ranged} whits={whits} pierce={pierce} armor={armor} base={base}")
    print("  crit/block/evade=", dc, db, de)
    print("  live_ph=", live_ph)
    print("  off_ph =", off_ph, "hits=", rr.get("hits"), "off_pierce=", rr.get("pierce"),
          "off_armor=", rr.get("armor"), "off_profile=", rr.get("profile"))
    lo = sum(off_ph or [0]); li = sum(live_ph or [0])
    if li:
        print("  ratio off/live =", round(lo / li, 4), "(sum off", lo, "sum live", li, ")")


def main():
    att = sys.argv[1] if len(sys.argv) > 1 else "templHelbrecht"
    tgt = sys.argv[2] if len(sys.argv) > 2 else "ultraApothecary"
    dist = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    w = _unwrap(R._rpc(_SID, "autoBootExtraire", [{}], timeout=180))
    print("amorce ok=", isinstance(w, dict) and w.get("ok"))
    try:
        run(att, tgt, dist)
    finally:
        for rid in _created:
            try:
                R._rpc(_SID, "disposeRunner", [{"runnerId": rid}], timeout=20)
            except Exception:
                pass


if __name__ == "__main__":
    main()
