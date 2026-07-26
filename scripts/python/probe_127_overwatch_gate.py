"""Probe #127 — MESURE live du gate d'activation de l'overwatch (`Overwatch_AutoAttack` 1009).

Deux phases (`--phase`), toutes deux montees depuis une seed BC sur disque (runner isole, dispose
en fin de phase). Doc : `docs/rl/case-127-overwatch-active-condition.md`.

  * `gate`     — le flag `UnitFlag.ActiveAbilityUsed` bloque-t-il la RE-ACTIVATION au tour adverse ?
                 Deux overwatchers MIENS castent, meme tour, meme cible :
                   `eldarRanger`    / FireAndReposition (1063) : SetsActiveAbilityUsedFlag DEFAUT
                   `admecDestroyer` / SentinelDirectives (1139): la classe OVERRIDE ce virtual
                 Apres `endturn` (fenetre `On(0x12)`), on relit `decisionView.units[].effects` — le
                 canal DROPPE les effets `IsActive == 0` (case-160). Attendu : 1009 absent sur le
                 premier, present sur le second. (Ce que verrouille
                 `tests/engine/runner/test_overwatch_active_ability_gate_live.py`.)

  * `residual` — RESIDU inventorie en `case-127` §6.1 : le 3e `Triggered()` de
                 `RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal`
                 (`On(AttackDamageAttack=10,1) & OwnerIsActor -> DeactivateEffect`). Sans aucun
                 cast, on fait bouger DEUX fois le mover dans la portee : le 1er move tire, le 2e
                 ne tire plus et 1009 a disparu. NON PORTE offline (aucun test ne le garde) — ce
                 probe est l'artefact de mesure.

ASCII only, `python` (pas `py`), depuis `scripts/python`.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import hexgeo
import rl_collect_batch as R
from engine.entities.pathfinding.board import Board

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

OW_FLAG = "eldarRanger"        # trait Overwatch ; 1063 POSE ActiveAbilityUsed
OW_NOFLAG = "admecDestroyer"   # trait Overwatch ; 1139 NE le pose PAS (override)
MOVER = "necroOverlord"
AB_FLAG = 1063
AB_NOFLAG = 1139
OVERWATCH = 1009


def _rpc(sid, m, b=None, t=60):
    r = R._rpc(sid, m, [b] if b is not None else [], timeout=t)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _build(seed, board):
    sf = ROOT / "data" / "rl-state" / f"probe127-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed, "--state-file", str(sf),
         "--board", board, "--roster", "1", "--p-units", f"{OW_FLAG},{OW_NOFLAG}",
         "--a-units", MOVER, "--hp-target", "400000", "--hp-player", "400000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        print("BUILD KO:", (p.stderr or p.stdout or "")[-500:])
        return None, None
    return int(json.loads(sf.read_text())["runnerId"]), sf


def _find(dv, vis):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vis and u.get("alive")),
                None)


def _cr(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _effs(u):
    return sorted({e.get("effectType") for e in ((u or {}).get("effects") or [])})


def _dv(sid, rid):
    return _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 120)


def _mv(sid, rid, uid, c):
    return _rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 60)


def _endturn(sid, rid):
    return _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)


def _hp(sid, rid, uid):
    ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    return next((u.get("hp") for u in (ob.get("units") or []) if u.get("squadId") == uid), None)


def _from_here(sid, rid, cid, ab):
    at = _rpc(sid, "abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ab}, 90)
    us = (at.get("units") or [{}])[0]
    a = next((x for x in (us.get("abilities") or []) if x.get("abilityId") == ab), {})
    return {x.get("targetId") for x in (a.get("fromHere") or [])}


def _setup(sid, rid, board):
    """Amene a MON tour et place le mover a distance 2-3 des DEUX overwatchers."""
    dv = _dv(sid, rid)
    a = _find(dv, OW_FLAG)
    if a is None:
        return None
    my = a["owner"]
    for _ in range(8):
        dv = _dv(sid, rid)
        if dv.get("currentPlayer") == my:
            break
        _endturn(sid, rid)
    dv = _dv(sid, rid)
    a, b, m = _find(dv, OW_FLAG), _find(dv, OW_NOFLAG), _find(dv, MOVER)
    if a is None or b is None or m is None:
        return None
    ca, cb = _cr(a), _cr(b)
    occ = {_cr(u) for u in (dv.get("units") or []) if u.get("alive") and u.get("id") != m["id"]}
    for c in [board.coord(t) for t in sorted(board.by_id)
              if board.walkable(t) and board.coord(t) not in occ
              and 2 <= hexgeo.distance(board.coord(t), ca) <= 3
              and 2 <= hexgeo.distance(board.coord(t), cb) <= 3][:10]:
        _mv(sid, rid, m["id"], c)
        if _cr(_find(_dv(sid, rid), MOVER)) == c:
            return {"a": a, "b": b, "m": m, "my": my, "spot": c, "ca": ca, "cb": cb}
    return None


def phase_gate(sid, rid, board):
    st = _setup(sid, rid, board)
    if st is None:
        print("SETUP KO")
        return
    a, b, m = st["a"], st["b"], st["m"]
    for u, ab, nm in ((a, AB_FLAG, OW_FLAG), (b, AB_NOFLAG, OW_NOFLAG)):
        legal = m["id"] in _from_here(sid, rid, u["id"], ab)
        r = _rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": u["id"], "targetId": m["id"], "abilityType": ab}}, 120)
        print(f"  cast {nm} ability={ab} legal={legal} ok={isinstance(r, dict) and r.get('ok')}")
    _endturn(sid, rid)
    dv = _dv(sid, rid)
    ea, eb = _effs(_find(dv, OW_FLAG)), _effs(_find(dv, OW_NOFLAG))
    print(f"[gate] tour adverse (cp={dv.get('currentPlayer')}) -- fenetre On(0x12) passee")
    print(f"  {OW_FLAG:16s} flag POSE      effects={ea} overwatch={OVERWATCH in ea}")
    print(f"  {OW_NOFLAG:16s} flag NON pose  effects={eb} overwatch={OVERWATCH in eb}")


def phase_residual(sid, rid, board):
    st = _setup(sid, rid, board)
    if st is None:
        print("SETUP KO")
        return
    m, ca, cb, spot = st["m"], st["ca"], st["cb"], st["spot"]
    _endturn(sid, rid)                                   # aucun cast -> les 2 (re)activent
    dv = _dv(sid, rid)
    print(f"[residual] controle sans cast : {OW_FLAG}={_effs(_find(dv, OW_FLAG))} "
          f"{OW_NOFLAG}={_effs(_find(dv, OW_NOFLAG))}")
    occ = {_cr(u) for u in (dv.get("units") or []) if u.get("alive") and u.get("id") != m["id"]}
    cur, prev, hp = spot, None, _hp(sid, rid, m["id"])
    for step in (1, 2):
        nxt = next((board.coord(t) for t in board.neighbours(board.id_at(*cur))
                    if board.walkable(t) and board.coord(t) not in occ and board.coord(t) != prev
                    and 1 <= hexgeo.distance(board.coord(t), ca) <= 3
                    and 1 <= hexgeo.distance(board.coord(t), cb) <= 3), None)
        if nxt is None:
            print(f"  move-{step} : aucune tuile voisine a portee")
            return
        _mv(sid, rid, m["id"], nxt)
        h2 = _hp(sid, rid, m["id"])
        dv = _dv(sid, rid)
        print(f"  move-{step} {cur} -> {nxt} : hp {hp} -> {h2} (delta {hp - h2}) | "
              f"{OW_FLAG}={_effs(_find(dv, OW_FLAG))} {OW_NOFLAG}={_effs(_find(dv, OW_NOFLAG))}")
        prev, cur, hp = cur, nxt, h2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=("gate", "residual"), default="gate")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()
    sid = R._resolve_session()
    rid, sf = _build(a.seed, a.board)
    if rid is None:
        return 1
    print(f"runner {rid} (seed={a.seed} board={a.board})")
    try:
        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")
        (phase_gate if a.phase == "gate" else phase_residual)(sid, rid, board)
    finally:
        _rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
        sf.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
