#!/usr/bin/env python
"""Probe #1013 (temoin) -- LE CRIT DU PIPELINE `AttackWithAttackDamage` EST-IL A MOI ?

`probe_1013_paragon_spear.py` mesure, sur un flux RNG PROUVE ALIGNE (meme `mti`, meme tableau MT
final) : PORT == NATIF **bit-exact** quand `CritChance = 0`, et PORT != NATIF des qu'un coup CRITE.
La question que ce temoin tranche est la seule qui compte pour attribuer l'ecart :

    est-ce le PORT DE PARAGONSPEAR qui diverge, ou le pipeline PARTAGE
    `AttackDamageOperation.execute_ability_attack` -> `damage_hits._run_hits` ?

TEMOIN : `MartialApotheosis` (`TriggeredAbilityType` 0x415 = 1045, passif de `necroOverlord`) --
MEME vecteur (`On(0x16 = TurnStart_Actions)`), MEME feuille (`AttackWithAttackDamage`, famille
`attack`), port DEJA valide bit-exact (#392, 3702 == 3702), et qui ne partage RIEN avec le mien
sinon ce pipeline. Il arrive en bataille par `BC.Units[].PassiveAbilities` -- aucune relique, donc
aucun des trois montages de #237 n'entre dans la mesure.

Verdict :
  * temoin DIVERGE aussi sous crit  -> l'ecart est dans le pipeline PARTAGE, pas dans mon port ;
  * temoin CONCORDE sous crit       -> l'ecart est a moi, et il faut le chercher dans ce que
                                       `ParagonSpearAbility` passe a la feuille.

    cd scripts/python
    python probe_1013_temoin_crit.py                 # crit 0 puis crit 100, les deux abilities

Sorties dans `logs/` (jamais `data/`). ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
_ROOT = _PYDIR.parents[1]

VICTIMS = "orksNob,orksRuntherd"
BOARD = "MC1_67"
SEED = "777"
HP_PLAYER = 500000

# (visualId du porteur, nom d'ability, arguments de montage SUPPLEMENTAIRES)
CASES = {
    "MartialApotheosis": ("necroOverlord", "MartialApotheosis", []),
    "ParagonSpear": ("custoKyrus", "ParagonSpear",
                     ["--equip-relic", "custoKyrus:ParagonSpear:1"]),
}


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _out_dir() -> Path:
    p = _ROOT / "logs" / ("probe_1013_temoin-%d" % os.getpid())
    p.mkdir(parents=True, exist_ok=True)
    return p


def _build(carrier: str, extra: list, crit: int | None) -> int:
    state = _out_dir() / "runner.json"
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--state-file", str(state),
            "--board", BOARD, "--p-units", VICTIMS, "--a-units", carrier,
            "--hp-player", str(HP_PLAYER), *extra]
    if crit is not None:
        argv += ["--unit-stat", "%s:CritChance=%d" % (carrier, crit)]
    p = subprocess.run(argv, cwd=str(_PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise RuntimeError("build KO: " + ((p.stderr or p.stdout or "")[-700:]))
    return json.loads(state.read_text())["runnerId"]


def mesure(rpc, case: str, crit: int | None, dist: int = 1) -> dict:
    """Monte, drive a `dist`, capture, rejoue le turn-start OFFLINE, puis `endturn` NATIF."""
    import hexgeo
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import HealthComponent, OwnerComponent, StatsComponent
    from engine.runner.operations.triggers.dispatch.turn import start_turn_triggers
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state

    carrier, ability, extra = CASES[case]
    out = {"case": case, "crit": crit, "ok": False, "why": None}
    rid = _build(carrier, extra, crit)
    out["rid"] = rid
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")
        dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
        ov = next((u for u in (dv0.get("units") or []) if u.get("visualId") == carrier), None)
        if ov is None:
            out["why"] = "%s absent du build" % carrier
            return out
        oid = ov["id"]
        if dv0.get("currentPlayer") == ov.get("owner"):
            out["why"] = "build demarre au tour du porteur"
            return out

        def live():
            return {u["squadId"]: u
                    for u in (rpc("observeBattle", {"runnerId": rid}, 40).get("units") or [])
                    if not u.get("isDead") and u.get("col") is not None}

        U = live()
        opos = (U[oid]["col"], U[oid]["row"])
        foes = sorted(s for s, u in U.items() if u.get("teamId") != U[oid].get("teamId"))
        occupied = {board.id_at(u["col"], u["row"]) for u in U.values()}
        for k, fid in enumerate(foes):
            want = dist if k == 0 else max(4, dist + 2)
            cands = [t for t in board.by_id
                     if board.walkable(t) and t not in occupied
                     and hexgeo.distance(opos, board.coord(t)) == want]
            if not cands:
                out["why"] = "pas de tuile libre a d=%d" % want
                return out
            tgt = sorted(cands)[0]
            c, r = board.coord(tgt)
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": fid, "to": {"col": c, "row": r}}}, 90)
            occupied.discard(board.id_at(U[fid]["col"], U[fid]["row"]))
            occupied.add(tgt)
        U = live()
        out["dists"] = {s: hexgeo.distance(opos, (U[s]["col"], U[s]["row"])) for s in foes if s in U}

        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
        uas = rpc("unitAbilityStates", {"runnerId": rid}, 60)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)

        state = load_state(dv, ob, snap, board=board, ability_states=uas)
        rng = IntBasedMersenneTwister()
        rng.mt, rng.mti = list(rng0["mt"]), rng0["mti"]
        state.rng = rng
        car = next((uid for uid, e in state.entities.items()
                    if (e.get_component(StatsComponent) is not None
                        and getattr(e.get_component(StatsComponent).ctx, "visual_id", None) == carrier)),
                   None)
        if car is None:
            out["why"] = "porteur absent offline"
            return out
        hp0p = {uid: (e.get_component(HealthComponent).hp if e.get_component(HealthComponent) else None)
                for uid, e in state.entities.items()}
        res = start_turn_triggers(state, int(state.get_entity(car)
                                             .get_component(OwnerComponent).player)) or []
        hp1p = {uid: (e.get_component(HealthComponent).hp if e.get_component(HealthComponent) else None)
                for uid, e in state.entities.items()}
        out["port_delta"] = int(sum(hp0p[k] - hp1p[k] for k in hp0p
                                    if hp0p[k] is not None and hp1p.get(k) is not None
                                    and hp1p[k] < hp0p[k]))
        ev = [e for e in res if isinstance(e, dict) and e.get("ability") == ability]
        atk = ((ev[0].get("attack") if ev else None) or {})
        out["port"] = {"events": len(ev), "total": atk.get("total"), "rolls": atk.get("rolls"),
                       "crits": atk.get("crits"), "per_hit": atk.get("per_hit")}
        out["port_mti"] = state.rng.mti
        out["port_mt"] = list(state.rng.mt)

        hp0 = {s: u["hp"] for s, u in U.items()}
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        post = {u["squadId"]: u for u in (rpc("observeBattle", {"runnerId": rid}, 40)
                                          .get("units") or [])}
        out["native_delta"] = int(sum(hp0[s] - post[s]["hp"] for s in hp0
                                      if s in post and post[s]["hp"] is not None
                                      and post[s]["hp"] < hp0[s]))
        rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
        out["mti_native"], out["mti_port"] = (rng1 or {}).get("mti"), out["port_mti"]
        out["mt_final_equal"] = bool(list((rng1 or {}).get("mt") or []) == out.pop("port_mt"))
        out["ok"] = True
        return out
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 40)
        except Exception:                                        # pragma: no cover - diagnostic
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="#1013 temoin -- le crit du pipeline partage")
    ap.add_argument("--case", choices=sorted(CASES), action="append")
    ap.add_argument("--crit", type=int, action="append")
    a = ap.parse_args()
    cases = a.case or sorted(CASES)
    crits = a.crit if a.crit is not None else [0, 100]

    import rl_collect_batch as R
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    rc = 0
    for case in cases:
        for crit in crits:
            r = mesure(rpc, case, crit)
            if not r.get("ok"):
                print("%-18s crit=%-4s NON MESURE : %s" % (case, crit, r.get("why")))
                rc = 1
                continue
            verdict = "ACCORD" if r["port_delta"] == r["native_delta"] else "ECART"
            print("%-18s crit=%-4s port=%-7s natif=%-7s %-7s | mti %s/%s MT_egal=%s | %s"
                  % (case, crit, r["port_delta"], r["native_delta"], verdict,
                     r["mti_port"], r["mti_native"], r["mt_final_equal"], r["port"]))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
