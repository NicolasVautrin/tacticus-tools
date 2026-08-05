"""#287-r1 -- GENERALISATION : la voie `UnitFlag.NoActionAvailable` (4) est-elle TRANSVERSE ?

CE QUE CE PROBE AJOUTE A `probe_287_facade_combat.py`. Celui-la mesure l'accord des flags sur UN
cast d'UNE ability (1100 SorcerousFacade) sur UN board (MC1_67). Le residu, lui, etait annonce
TRANSVERSE au turn-flow : `FinishUnitTurnOperation$$Execute` pose le flag pour TOUTE activation
qui se termine, quelle que soit l'ability. Un port qui n'aurait ferme l'ecart QUE sur le chemin de
1100 passerait le test #287 et resterait faux partout ailleurs.

DEUX BRAS, ET ILS SONT OPPOSES -- c'est ce qui interdit de conclure d'un accord trivial :

  * `attaque` -- une ATTAQUE NORMALE commandee, sur un AUTRE board et un AUTRE roster. Chemin
    natif : `ActiveAbilityMessage(NormalAttackType)` -> `ActiveAbilityOperation$$ExecuteInternal`
    -> `AddFlagsAfterAbilityExecution(skipEndTurn = false)` -> `FinishUnitTurn` -> slot 0x76.
    ATTENDU : le flag 4 apparait des DEUX cotes.
  * `sans_fin_de_tour` -- une AUTRE unite du meme camp, qui se contente de SE DEPLACER
    (`MoveUnitMessage`) : ce chemin ne traverse PAS `AddFlagsAfterAbilityExecution`.
    ATTENDU : le flag 4 n'apparait NI live NI port. C'est le bras ou un port qui poserait le flag
    « au cas ou » (hors du gate `skipEndTurn`) se verrait -- l'accord du 1er bras seul ne le
    montrerait pas, puisque les deux cotes y posent.

⚠ L'ATTAQUE NORMALE N'EST PAS un `kind` d'`applyAction` : c'est une ABILITY dont le type est
PER-UNIT (`ActiveAbilityComponent.NormalAttackType@0x28`, jamais le 17 de la FAMILLE). L'id est LU
dans `decisionView.units[].abilities[kind == "normal"].id` -- le hook LEVE (HTTP 500) sur
`{kind: "attack"}`, et cette levee est volontaire (#263).

Usage :
    python scripts/python/probe_287r1_flags_transverse.py
    python scripts/python/probe_287r1_flags_transverse.py --board C1_74 --seed 34117 --keep
ASCII only ; exit 0 = les deux bras conformes.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo
import probe_27_custom_utility_inventory as INV
from engine.entities.pathfinding.board import Board
from engine.entities.unit_flag import UnitFlag
from engine.runner.messages import AttackUnitMessage, MoveUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.snapshot import load_state

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"

# Board et seed DIFFERENTS de `probe_287_facade_combat` (MC1_67 / 28701) : c'est le point.
BOARD = "C1_74"
SEED = 34117
P_UNITS = "ultraTitus,ultraCalgar"
A_UNITS = "thousTzaangor,thousSorcerer"
CASTER_VID = "ultraTitus"        # bras `attaque`   : porte l'attaque normale
WALKER_VID = "ultraCalgar"       # bras `sans_fin_de_tour` : se contente de bouger
FOE_VID = "thousTzaangor"


def _rpc(method, args=None, timeout=90000):
    return INV.rpc(INV._session_id(), method, args, timeout)


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _dview(rid):
    return _rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])


def _units(dv):
    return {u.get("visualId"): u for u in (dv.get("units") or []) if u.get("alive")}


def _flags_by_id(rid):
    cs = _rpc("combatSnapshot", [{"runnerId": rid}], 60000)
    return ({u.get("entityId"): sorted(u.get("unitFlags") or []) for u in (cs.get("units") or [])},
            cs)


def _normal_ability_id(dv, uid):
    """L'id CONCRET de l'attaque normale de l'unite (`NormalAttackType@0x28`, PER-UNIT -- jamais
    le 17 de la famille). Lu dans `decisionView.units[].abilities[kind == "normal"].id`."""
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    if u is None:
        return None
    ab = next((a for a in (u.get("abilities") or []) if a.get("kind") == "normal"), None)
    return None if ab is None else ab.get("id")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _free_at(board, center, radius, occupied):
    for t in sorted(board.by_id):
        c = board.coord(t)
        if board.walkable(t) and hexgeo.distance(center, c) == radius and c not in occupied:
            return c
    return None


def _port_flags(snap, board, uid, jouer):
    """Rejoue OFFLINE sur le MEME etat (et le meme `state.rng`) et rend les flags du port."""
    from engine.runner.components import UnitFlagsComponent
    from engine.runner.runner import Runner
    st = load_state(snap["dv"], snap["ob"], snap["snap"], board=board)
    if isinstance(snap["rng"], dict) and snap["rng"].get("mt"):
        st.rng = _seed_rng(snap["rng"])
    runner = Runner(st).install_default_handlers(20)
    jouer(runner, st)
    e = st.get_entity(uid)
    fc = e.get_component(UnitFlagsComponent) if e is not None else None
    return sorted(fc.flags) if fc is not None else []


def run(keep: bool = False, seed: int = SEED, board_name: str = BOARD,
        state_name: str = "rs_287r1_transverse.json") -> dict:
    state = LOGS / state_name
    _run(["build", "--seed", str(seed), "--board", board_name, "--rank", "17",
          "--p-units", P_UNITS, "--a-units", A_UNITS, "--state-file", str(state)])
    if not state.exists():
        return {"error": "build KO (state-file absent)"}
    rid = int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])
    out: dict = {"runner": rid, "board": board_name, "seed": seed}
    try:
        bg = _rpc("boardGraph", [{"runnerId": rid}])
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = _dview(rid)
        U = _units(dv)
        missing = [v for v in (CASTER_VID, WALKER_VID, FOE_VID) if v not in U]
        if missing:
            return dict(out, error="unites absentes du build : %s" % missing)
        caster, foe = U[CASTER_VID], U[FOE_VID]

        def move_rpc(uid, to):
            _rpc("applyAction", [{"runnerId": rid, "action": {
                "kind": "move", "unitId": uid, "to": {"col": int(to[0]), "row": int(to[1])}}}],
                40000)

        # GEOMETRIE : on AMENE l'ennemi au contact du caster (jamais << bloque par le spawn >>).
        c_pos = _pos(caster)
        occ = {_pos(u) for u in U.values()} - {c_pos}
        foe_to = _free_at(board, c_pos, 1, occ)
        if foe_to is None:
            return dict(out, error="aucune tuile libre adjacente au caster")
        move_rpc(foe["id"], foe_to)

        # Le caster doit avoir un tour NEUF (aucun flag consomme) -> on rend la main et on revient.
        my_player = caster.get("owner")
        for _ in range(8):
            if _dview(rid).get("currentPlayer") == my_player:
                break
            _rpc("applyAction", [{"runnerId": rid, "action": {"kind": "endturn"}}], 40000)

        dv = _dview(rid)
        U = _units(dv)
        ids = {v: U[v]["id"] for v in U}
        cid, wid, fid = ids[CASTER_VID], ids[WALKER_VID], ids[FOE_VID]
        normal_id = _normal_ability_id(dv, cid)
        if normal_id is None:
            return dict(out, error="attaque normale introuvable pour %s (NormalAttackType@0x28)"
                                   % CASTER_VID)
        out["normal_ability"] = int(normal_id)

        # ---------- BRAS 1 : SANS fin de tour -- une AUTRE unite se contente de BOUGER ----------
        flags_pre, cs_pre = _flags_by_id(rid)
        snap_move = {"dv": dv, "ob": _rpc("observeBattle", [{"runnerId": rid}], 40000),
                     "snap": cs_pre, "rng": _rpc("dumpRng", [{"runnerId": rid}], 30000)}
        occ = {_pos(u) for u in U.values()}
        step = _free_at(board, _pos(U[WALKER_VID]), 1, occ)
        if step is None:
            return dict(out, error="aucune tuile libre adjacente pour le pas de %s" % WALKER_VID)
        move_rpc(wid, step)
        flags_mid, _ = _flags_by_id(rid)
        live_move = sorted(set(flags_mid.get(wid) or []) - set(flags_pre.get(wid) or []))
        port_move = _port_flags(
            snap_move, board, wid,
            lambda r, st: r.apply(MoveUnitMessage(unit_id=wid, to=(int(step[0]), int(step[1])))))
        out["sans_fin_de_tour"] = {"unit": WALKER_VID, "live_added": live_move,
                                   "port_flags": port_move,
                                   "to": [int(step[0]), int(step[1])]}

        # ---------- BRAS 2 : ATTAQUE NORMALE (le chemin `AddFlagsAfterAbilityExecution`) --------
        dv2 = _dview(rid)
        flags_pre2, cs_pre2 = _flags_by_id(rid)
        snap_atk = {"dv": dv2, "ob": _rpc("observeBattle", [{"runnerId": rid}], 40000),
                    "snap": cs_pre2, "rng": _rpc("dumpRng", [{"runnerId": rid}], 30000)}
        res = _rpc("applyAction", [{"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": fid,
            "abilityType": int(normal_id)}}], 60000)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        flags_post2, _ = _flags_by_id(rid)
        live_atk = sorted(set(flags_post2.get(cid) or []) - set(flags_pre2.get(cid) or []))
        port_atk = _port_flags(
            snap_atk, board, cid,
            lambda r, st: r.apply(AttackUnitMessage(attacker_id=cid, target_id=fid)))
        port_atk_added = sorted(set(port_atk) - set(flags_pre2.get(cid) or []))
        out["attaque"] = {"unit": CASTER_VID, "ok": bool(a0.get("ok")), "live_added": live_atk,
                          "port_flags": port_atk, "port_added": port_atk_added,
                          "flags_pre": flags_pre2.get(cid)}
        return out
    finally:
        if not keep:
            _run(["dispose", "--state-file", str(state)])


def main() -> int:
    ap = argparse.ArgumentParser(description="#287-r1 : la voie du flag 4 est-elle transverse ?")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--state-file", default="rs_287r1_transverse.json")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    r = run(keep=a.keep, seed=a.seed, board_name=a.board, state_name=a.state_file)
    print(json.dumps(r, indent=1, sort_keys=True))
    if r.get("error"):
        print("[287r1-t] PAS MESURE : %s" % r["error"])
        return 2
    NA = int(UnitFlag.NoActionAvailable)
    ok = True
    m = r["sans_fin_de_tour"]
    if NA in (m["live_added"] or []) or NA in (m["port_flags"] or []):
        print("[287r1-t] ECHEC bras `sans_fin_de_tour` : le flag %d apparait apres un simple "
              "deplacement (live=%s port=%s)" % (NA, m["live_added"], m["port_flags"]))
        ok = False
    a2 = r["attaque"]
    if NA not in (a2["live_added"] or []):
        print("[287r1-t] REGIME TEMOIN casse : le NATIF ne pose pas le flag %d apres une attaque "
              "normale (live=%s) -- le bras ne mesure rien" % (NA, a2["live_added"]))
        ok = False
    ecart = set(a2["live_added"] or []) - set(a2["port_added"] or [])
    trop = set(a2["port_added"] or []) - set(a2["live_added"] or [])
    if ecart or trop:
        print("[287r1-t] ECHEC bras `attaque` : live=%s port=%s (manquants=%s en_trop=%s)"
              % (a2["live_added"], a2["port_added"], sorted(ecart), sorted(trop)))
        ok = False
    print("[287r1-t] board=%s seed=%s : deplacement live=%s port=%s | attaque live=%s port=%s"
          % (r["board"], r["seed"], m["live_added"], m["port_flags"],
             a2["live_added"], a2["port_added"]))
    print("[287r1-t] %s" % ("PROBE OK" if ok else "PROBE ECHEC"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
