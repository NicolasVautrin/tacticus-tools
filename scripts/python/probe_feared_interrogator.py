"""PROBE #passifs-DA — FearedInterrogator (1235, darkaAsmodai) : offline == live, 3 cas discriminants.

Le marqueur `FearedInterrogator_Target` (1295) n'est JAMAIS materialise sur la cible (verifie live :
les DEUX effets sont chez Asmodai, aucun chez les ennemis) -> le port RE-EVALUE le selecteur. On
confronte donc l'attaque NORMALE d'Asmodai en replay-diff (RNG seede via `dumpRng`) dans 3 geometries :

  NEG      cible NI Pinned/Stunned NI adjacente a un autre Dark Angel ami -> AUCUN bonus
  POS_DMG  cible adjacente a `darkaCompanion` (ami Dark Angels)           -> +extraDmg, coups INCHANGES
  POS_HITS cible CHAOS adjacente au meme ami                              -> +extraDmg ET +extraHits

Les positions sont DRIVEES (`applyAction move` ignore la portee) — rien n'est laisse a la geometrie de
spawn. ASCII only. Usage : python probe_feared_interrogator.py
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8765"
ASMODAI = "darkaAsmodai"
DA_ALLY = "darkaCompanion"        # ami DARK ANGELS (le « another friendly Dark Angel » du selecteur)
FOE_XENOS = "necroOverlord"       # cible NON Chaos (defensivement vanille)
FOE_CHAOS = "thousTzaangor"       # cible CHAOS (gate `HasTrait(Target, 0x7ea)` du volet COUPS)
BOARD = "MC1_67"


def rpc(method, args=None, timeout=90000):
    body = json.dumps({"method": method, "args": args or {}, "timeout": timeout}).encode()
    req = urllib.request.Request(BASE + "/api/scripts/1/rpc", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        out = json.loads(r.read().decode())
    return out.get("result", out)


def build(state_file: Path) -> int:
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", "31337", "--board", BOARD,
           "--roster", "1", "--p-units", ",".join([ASMODAI, DA_ALLY]),
           "--a-units", ",".join([FOE_XENOS, FOE_CHAOS]),
           "--hp-target", "90000", "--no-ai", "--state-file", str(state_file)]
    subprocess.run(cmd, cwd=str(Path(__file__).parent), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def _seed_rng(s):
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _unit(dv, vid):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vid and u.get("alive")), None)


def move(rid, uid, col, row):
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": col, "row": row}}}, 40000)


def measure(rid, label, tgt_vis, a_pos, ally_pos, tgt_pos, other_pos):
    """Place tout le monde, cale le tour d'Asmodai, joue son attaque normale live + replay offline."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.components import HealthComponent
    from engine.runner.damage_model import attacker_modifiers, marked_effect_types_for_target

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    uA = _unit(dv, ASMODAI)
    if uA is None:
        print("  SKIP %s : Asmodai absent" % label)
        return None
    my_player = uA.get("owner")
    # Le tour d'Asmodai doit etre DISPONIBLE (les mesures s'enchainent sur le meme runner) : on boucle
    # les fins de tour jusqu'a le retrouver avec une action. `applyAction endturn` clot le tour de
    # l'equipe COURANTE et ne fait jamais jouer l'IA.
    for _ in range(8):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        uA = _unit(dv, ASMODAI)
        if uA is not None and dv.get("currentPlayer") == my_player and uA.get("hasAction"):
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40000)
    uF, uT = _unit(dv, DA_ALLY), _unit(dv, tgt_vis)
    uO = _unit(dv, FOE_CHAOS if tgt_vis == FOE_XENOS else FOE_XENOS)
    if not (uA and uF and uT and uO):
        print("  SKIP %s : unite manquante" % label)
        return None
    aid, fid, tid, oid = uA["id"], uF["id"], uT["id"], uO["id"]
    # On DEGAGE d'abord tous les figurants vers des tuiles de parking distinctes, PUIS on pose la
    # geometrie voulue : un `move` vers une tuile occupee echoue silencieusement.
    move(rid, oid, *other_pos)
    move(rid, fid, 0, 8)
    move(rid, aid, 1, 8)
    move(rid, tid, *tgt_pos)
    move(rid, fid, *ally_pos)
    move(rid, aid, *a_pos)

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    _p = {u["id"]: ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
          for u in (dv.get("units") or [])}
    print("  ... geometrie %s : asmodai=%s ami=%s cible=%s autre=%s"
          % (label, _p.get(aid), _p.get(fid), _p.get(tid), _p.get(oid)))
    ob = rpc("observeBattle", {"runnerId": rid})
    snap = rpc("combatSnapshot", {"runnerId": rid})
    bg = rpc("boardGraph", {"runnerId": rid})
    board = Board(bg["tiles"], adjacency="native_sym") if (bg or {}).get("tiles") else None
    state = load_state(dv, ob, snap, board=board)

    marked = marked_effect_types_for_target(state, aid, tid)
    he = state.get_entity(tid).get_component(HealthComponent)
    mods, _ = attacker_modifiers(state, aid, None, is_ranged=False, target_id=tid)

    a2 = next((u for u in (dv.get("units") or []) if u.get("id") == aid), None)
    norm = next((ab for ab in ((a2 or {}).get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        print("  SKIP %s : pas d'attaque normale" % label)
        return None
    s0 = rpc("dumpRng", {"runnerId": rid})
    if not (isinstance(s0, dict) and "mt" in s0):
        print("  SKIP %s : dumpRng indispo" % label)
        return None
    state.rng = _seed_rng(s0)
    runner = Runner(state).install_default_handlers(20)

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": aid, "targetId": tid, "abilityType": norm["id"]}}, 40000)
    a0 = (res.get("actions") or [{}])[0]
    if not a0.get("ok"):
        print("  SKIP %s : attaque live KO %s" % (label, str(res)[:160]))
        return None
    live_ph = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == norm["id"]:
            live_ph.append(td.get("Amount"))
    live_after = next((u.get("hp") for u in (res.get("units") or []) if u.get("squadId") == tid), None)

    runner.apply(AttackUnitMessage(aid, tid))
    rr = runner.damage_handler.last or {}
    off_after = state.get_entity(tid).get_component(HealthComponent).hp
    out = {"label": label, "target": tgt_vis, "marked": sorted(marked),
           "additive": getattr(mods, "additive", None),
           "live_hits": len(live_ph), "off_hits": len(rr.get("per_hit") or []),
           "live_ph": live_ph, "off_ph": rr.get("per_hit"),
           "live_after": live_after, "off_after": off_after,
           "hp_before": he.hp if he else None}
    print("  [%s] target=%s marked=%s additive=%s" % (label, tgt_vis, out["marked"], out["additive"]))
    print("      hits live=%s off=%s | per_hit live=%s off=%s | hp live=%s off=%s  -> %s" % (
        out["live_hits"], out["off_hits"], live_ph, rr.get("per_hit"), live_after, off_after,
        "OK" if (live_ph == rr.get("per_hit") and live_after == off_after) else "MISMATCH"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int)
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()
    sf = Path(a.state_file) if a.state_file else \
        Path(__file__).resolve().parents[2] / "logs" / "runners" / "probe_fi.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    rid = a.runner or build(sf)
    print("runner=%d board=%s" % (rid, BOARD))
    rows = []
    # NEG : ami Dark Angels LOIN de la cible (dist 4), cible NON Pinned/Stunned -> marqueur ABSENT.
    rows.append(measure(rid, "NEG", FOE_XENOS, a_pos=(3, 3), ally_pos=(0, 0),
                        tgt_pos=(3, 4), other_pos=(6, 0)))
    # POS_DMG : le MEME ami colle a la cible -> marqueur POSE, cible NON Chaos -> +extraDmg seul.
    rows.append(measure(rid, "POS_DMG", FOE_XENOS, a_pos=(3, 3), ally_pos=(3, 5),
                        tgt_pos=(3, 4), other_pos=(6, 0)))
    # POS_HITS : cible CHAOS collee au meme ami -> marqueur POSE + Chaos -> +extraDmg ET +extraHits.
    # (parking distinct : en POS_HITS c'est necroOverlord qui doit LIBERER (3,4), et thousTzaangor
    #  occupe deja (6,0) — deux tuiles de parking differentes, sinon les deux moves echouent.)
    rows.append(measure(rid, "POS_HITS", FOE_CHAOS, a_pos=(3, 3), ally_pos=(3, 5),
                        tgt_pos=(3, 4), other_pos=(6, 8)))
    ok = all(r is not None and r["live_ph"] == r["off_ph"] and r["live_after"] == r["off_after"]
             for r in rows)
    print("VERDICT:", "OK offline == live sur les 3 cas" if ok else "MISMATCH / SKIP (cf. ci-dessus)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
