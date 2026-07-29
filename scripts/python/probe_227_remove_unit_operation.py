"""Probe #227 -- CONFRONTATION de l'emetteur d'`On(UnitRemoved = 0x25)`
(`IdunBattle.Operations.RemoveUnitOperation$$Execute`, port `engine/runner/operations/remove_unit.py`).

DEUX faces, toutes deux montees sur un etat LIVE-capte (`load_state` d'un runner reel) :

  FACE A -- DISCRIMINANTE (le consommateur unique du vecteur).
    Le SEUL ecouteur porte d'`On(0x25)` est `GhostRemoveOnSourceRemoved` (effet 1186
    `TimeFlux_Revive`, 5e retrait de `IdunBattle.Entities.Effects.Loki.GhostEffect$$
    CreateHandleTriggerAbilitiesInternal` : `On(0x25) & AreEqual(EffectSource, target@0x178)`).
    Montage : Toth (`thousTerminator`) bouge -> le ghost se pose sur sa tuile de DEBUT DE TOUR ;
    on RETIRE Toth par l'Operation -> le ghost doit DISPARAITRE.
    CONTRE-EPREUVE dans le meme run : le MEME retrait rejoue << a l'ancienne >> (la mutation que
    les deux sites de despawn faisaient avant #227 : `alive=False` + consommation des effets
    PORTES par l'unite, sans event) laisse le ghost EN PLACE -- il est porte par la TUILE, pas
    par Toth. C'est le mordant : sans l'emetteur, le retrait est silencieusement inoperant.

  FACE B -- NON-REGRESSION du SEUL call-site de production
    (`MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour` -> `RemoveUnit`, porteur `tauMarksman`
    = Sho'syl, present au pool). Quatre casts consecutifs : le natif borne le nombre de drones a
    `maxSummons` (3) via `HasToManySummons` -> eviction. On verifie que le port evince, que
    l'evince porte desormais le flag `Removed (0x1a)`, et que le compte de drones vivants
    s'ACCORDE avec le LIVE (invariant natif <= maxSummons).

Usage : python probe_227_remove_unit_operation.py [--seed S] [--board B] [--face A|B|AB]
Sortie ASCII pure (console cp1252). A lancer depuis scripts/python.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import hexgeo  # noqa: E402

ROOT = PYDIR.parents[1]
STATE_A = str(ROOT / "logs" / "_probe227_faceA_state.json")
STATE_B = str(ROOT / "logs" / "_probe227_faceB_state.json")

GHOST_HERO = "thousTerminator"     # Toth -- pose le GhostEffect 1186 quand il bouge
GHOST_FOE = "orksNob"              # ennemi inerte (jamais pilote)
GHOST_EFFECT = 1186                # EffectType.TimeFlux_Revive

MV71_HERO = "tauMarksman"          # Sho'syl -- attaque normale 1076 = MV71SniperDroneSquadAttack
MV71_FOE = "astraBullgryn"         # cible encaissante (doit survivre a 4 casts)
DRONE = "tauSmnDroneSniper"        # le summon evince
MAX_SUMMONS = 3                    # `GetNumberConstant(cfg, 0x3c)` (relu du gameconfig au run)

BOARD = "MC1_67"


def rpc(sid, m, args, t=90):
    return (_rpc(sid, m, [args], timeout=t).get("result") or {})


def build(state_file, p_units, a_units, seed, board, extra=()):
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
           "--p-units", p_units, "--a-units", a_units,
           "--no-ai", "--board", board, "--state-file", state_file] + list(extra)
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True)
    if p.returncode != 0:
        sys.stdout.write(p.stdout[-1500:])
        sys.stdout.write(p.stderr[-2000:])
        raise SystemExit("build KO")
    return json.loads(Path(state_file).read_text(encoding="utf-8"))["runnerId"]


def view(sid, rid):
    """`decisionView` est la source d'IDENTITE (c'est elle qui alimente `load_state`) ;
    `observeBattle` apporte `isDead` et les positions des unites hors dv."""
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    by_id = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        by_id[u.get("id")] = {"id": u.get("id"), "visualId": u.get("visualId"),
                              "col": p.get("col"), "row": p.get("row"), "hp": u.get("hp"),
                              "hasAction": u.get("hasAction"), "isDead": False}
    for o in (ob.get("units") or []):
        row = by_id.setdefault(o.get("id"), {"id": o.get("id"), "visualId": o.get("visualId")})
        row["isDead"] = bool(o.get("isDead"))
        if row.get("col") is None:
            row["col"], row["row"] = o.get("col"), o.get("row")
        row.setdefault("hp", o.get("hp"))
    by_vid = {}
    for row in by_id.values():
        by_vid.setdefault(row.get("visualId"), []).append(row)
    return dv, by_vid


def wait_for_action(sid, rid, visual_id, tries=6):
    """Cloture des tours jusqu'a ce que `visual_id` ait une action. Effet de bord VOULU : chaque
    `endturn` fait tourner `StartTurnOperation`, seul ecrivain de `UnitComponent + 0x18c`."""
    for _ in range(tries):
        dv, uu = view(sid, rid)
        rows = uu.get(visual_id) or []
        if rows and rows[0].get("hasAction"):
            return dv, uu
        act(sid, rid, {"kind": "endturn"})
    return view(sid, rid)


def act(sid, rid, action, t=90):
    return rpc(sid, "applyAction", {"runnerId": rid, "action": action}, t)


def movable(sid, rid, uid):
    r = rpc(sid, "aiMovableTiles", {"runnerId": rid, "unitId": uid}, 90)
    for u in (r.get("units") or []):
        if u.get("unitId") == uid:
            return [(t.get("col"), t.get("row")) for t in (u.get("tiles") or [])]
    return [(t.get("col"), t.get("row")) for t in (r.get("unionTiles") or [])]


def load_port_state(sid, rid, dv):
    """Etat PORT reconstruit depuis le LIVE (positions/stats/effets reels)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    tm = rpc(sid, "tileMeta", {"runnerId": rid}, 90)
    board = Board(bg["tiles"], adjacency="evenq") if (bg or {}).get("tiles") else None
    st = load_state(dv, ob, snap, board=board, tiles=tm)
    st.rng = IntBasedMersenneTwister(12345)
    return st, board


def live_ghost_tiles(sid, rid):
    tm = rpc(sid, "tileMeta", {"runnerId": rid}, 90)
    rows = tm.get("tiles") if isinstance(tm, dict) else tm
    return sorted((t.get("col"), t.get("row")) for t in (rows or [])
                  for e in (t.get("effects") or [])
                  if int(e.get("effectType") or -1) == GHOST_EFFECT)


def port_ghost_tiles(st):
    """Ids de tuile portant un GhostEffect 1186 NON consomme, cote port."""
    out = []
    for holder, effs in (st.effects.by_unit or {}).items():
        if any((not e.consumed) and int(e.effect_type) == GHOST_EFFECT for e in effs):
            out.append(int(holder))
    return sorted(out)


# --------------------------------------------------------------------------- FACE A
def face_a(sid, seed, board):
    """Toth pose un ghost, puis est RETIRE -> le ghost doit partir. Contre-epreuve incluse."""
    from engine.runner.components import OwnerComponent, UnitComponent, UnitFlagsComponent
    from engine.runner.operations.movement import MoveUnitOperation
    from engine.runner.operations.remove_unit import RemoveUnitOperation
    from engine.runner.operations.turnflow import StartTurnOperation
    from engine.runner.events import EventBus

    rid = build(STATE_A, GHOST_HERO, GHOST_FOE, seed, board)
    res = {"ok": False}
    try:
        dv, uu = wait_for_action(sid, rid, GHOST_HERO)
        if GHOST_HERO not in uu:
            print("  [A] %s absent du runner -- KO" % GHOST_HERO)
            return res, rid
        hid = uu[GHOST_HERO][0]["id"]
        A = (uu[GHOST_HERO][0]["col"], uu[GHOST_HERO][0]["row"])
        cand = [t for t in movable(sid, rid, hid) if t != A]
        if not cand:
            print("  [A] aucune tuile de destination -- KO")
            return res, rid
        cand.sort(key=lambda t: -hexgeo.distance(t, A))
        B = cand[0]

        # --- etat PORT capte AVANT le move ; on rejoue move puis retrait cote port
        st, board_obj = load_port_state(sid, rid, dv)
        pl = st.get_entity(hid).get_component(OwnerComponent).player
        StartTurnOperation.execute(st, pl)                 # seul ecrivain de `+0x18c`
        MoveUnitOperation(hid, B).execute(st, EventBus())  # `On(PreUnitMove)` -> pose du ghost
        ghosts_after_move = port_ghost_tiles(st)
        tile_A = board_obj.id_at(A[0], A[1]) if board_obj is not None else None
        print("  [A] A=%s B=%s | ghost porte par tuile(s) %s (tile(A)=%s)"
              % (A, B, ghosts_after_move, tile_A))
        if ghosts_after_move != [tile_A]:
            print("  [A] KO : le ghost n'est pas (uniquement) sur la tuile de debut de tour")
            return res, rid

        # --- CONTRE-EPREUVE d'abord, sur une COPIE d'etat fraiche : despawn << a l'ancienne >>
        st2, board2 = load_port_state(sid, rid, dv)
        StartTurnOperation.execute(st2, st2.get_entity(hid).get_component(OwnerComponent).player)
        MoveUnitOperation(hid, B).execute(st2, EventBus())
        e2 = st2.get_entity(hid)
        e2.get_component(UnitComponent).alive = False       # l'ancienne mutation, sans event
        for eff in (st2.effects.by_unit.get(int(hid), []) if st2.effects is not None else []):
            eff.consumed = True
        legacy_ghosts = port_ghost_tiles(st2)

        # --- l'Operation portee
        out = RemoveUnitOperation.execute(st, hid, remove_effects=True)
        ghosts_after_remove = port_ghost_tiles(st)
        fl = st.get_entity(hid).get_component(UnitFlagsComponent)
        uc = st.get_entity(hid).get_component(UnitComponent)
        removed_flag = bool(fl is not None and fl.has(UnitFlagsComponent.REMOVED))
        again = RemoveUnitOperation.execute(st, hid, remove_effects=True)   # gate anti-double

        print("  [A] apres RemoveUnitOperation : ghosts=%s | flag Removed=%s | alive=%s"
              % (ghosts_after_remove, removed_flag, uc.alive))
        print("  [A] CONTRE-EPREUVE (despawn sans event) : ghosts=%s" % legacy_ghosts)
        print("  [A] 2e appel (gate anti-double-retrait) -> %s" % ("None" if again is None else again))
        res = {"ok": True, "ghosts_after_move": ghosts_after_move,
               "ghosts_after_remove": ghosts_after_remove, "legacy_ghosts": legacy_ghosts,
               "removed_flag": removed_flag, "alive": bool(uc.alive), "tile_A": tile_A,
               "downstream": len(out.get("downstream") or []) if out else 0,
               "second_call_none": again is None}
        return res, rid
    except Exception as exc:                                # noqa: BLE001 (diagnostic de probe)
        import traceback
        print("  [A] EXC: %r" % (exc,))
        traceback.print_exc()
        return res, rid


# --------------------------------------------------------------------------- FACE B
def _live_drone_count(uu):
    return len([d for d in (uu.get(DRONE) or []) if not d.get("isDead")])


def _port_drones(st, team, visual_id):
    from engine.runner.components import UnitComponent, OwnerComponent
    out = []
    for uid, e in st.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        if uc is None or oc is None or uc.visual_id != visual_id or oc.team != team:
            continue
        out.append((int(uid), bool(uc.alive)))
    return sorted(out)


def face_b(sid, seed, board, casts=4):
    """Quatre casts de l'attaque normale de Sho'syl -> eviction au cap. PORT + compte LIVE."""
    import gameconfig as GC
    from engine.runner.components import (UnitComponent, OwnerComponent, UnitFlagsComponent)
    from engine.runner.abilities.loki.mv71 import MV71SniperDroneSquadAttackAbility

    max_summons = int(((GC.ability("MV71SniperDroneSquad") or {}).get("constants")
                       or {}).get("maxSummons") or MAX_SUMMONS)
    rid = build(STATE_B, MV71_HERO, MV71_FOE, seed, board, extra=["--hp-target", "999999"])
    res = {"ok": False}
    try:
        dv, uu = view(sid, rid)
        if MV71_HERO not in uu or MV71_FOE not in uu:
            print("  [B] roster incomplet -- KO")
            return res, rid
        cid = uu[MV71_HERO][0]["id"]
        tid = uu[MV71_FOE][0]["id"]
        st, _ = load_port_state(sid, rid, dv)
        team = st.get_entity(cid).get_component(OwnerComponent).team
        ability = MV71SniperDroneSquadAttackAbility()
        evicted_all, spawned_all = [], []
        for i in range(casts):
            out = ability.execute_behaviour(st, cid, tid)
            if out is None:
                print("  [B] cast %d : no-op (PickTile null ?)" % (i + 1))
                continue
            evicted_all += list(out.get("evicted") or [])
            spawned_all += list(out.get("spawned") or [])
            print("  [B] cast %d : spawned=%s evicted=%s" % (i + 1, out.get("spawned"),
                                                             out.get("evicted")))
        drones = _port_drones(st, team, DRONE)
        alive = [d for d, a in drones if a]
        flags_ok = True
        for uid in evicted_all:
            fl = st.get_entity(int(uid)).get_component(UnitFlagsComponent)
            has = bool(fl is not None and fl.has(UnitFlagsComponent.REMOVED))
            flags_ok = flags_ok and has
            print("  [B] evince %s : flag Removed=%s alive=%s"
                  % (uid, has, st.get_entity(int(uid)).get_component(UnitComponent).alive))
        print("  [B] PORT : %d drones crees, %d evinces, %d vivants (cap natif %d)"
              % (len(spawned_all), len(evicted_all), len(alive), max_summons))
        res = {"ok": True, "spawned": len(spawned_all), "evicted": len(evicted_all),
               "alive": len(alive), "max_summons": max_summons, "flags_ok": flags_ok}
        return res, rid
    except Exception as exc:                                # noqa: BLE001
        import traceback
        print("  [B] EXC: %r" % (exc,))
        traceback.print_exc()
        return res, rid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=31337)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--face", default="AB", choices=["A", "B", "AB"])
    a = ap.parse_args()
    sid = _resolve_session()
    print("[probe227] emetteur d'On(UnitRemoved = 0x25) -- RemoveUnitOperation")
    print("[probe227] seed=%s board=%s" % (a.seed, a.board))
    ok = True

    ra = rb = None
    if "A" in a.face:
        print("[probe227] --- FACE A : GhostEffect 1186 (consommateur unique) ---")
        ra, rid = face_a(sid, a.seed, a.board)
        rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        print("  runner %s dispose" % rid)
        if not ra.get("ok"):
            ok = False
        else:
            if ra["ghosts_after_remove"]:
                print("  KO [A] : le ghost SURVIT au retrait de son poseur (%s)"
                      % ra["ghosts_after_remove"])
                ok = False
            if ra["legacy_ghosts"] != ra["ghosts_after_move"]:
                print("  KO [A] : la contre-epreuve ne mord pas -- le despawn << a l'ancienne >>"
                      " retirait deja le ghost (%s)" % ra["legacy_ghosts"])
                ok = False
            if not ra["removed_flag"]:
                print("  KO [A] : le flag `Removed (0x1a)` n'est pas pose")
                ok = False
            if not ra["second_call_none"]:
                print("  KO [A] : le gate anti-double-retrait ne mord pas")
                ok = False

    if "B" in a.face:
        print("[probe227] --- FACE B : MV71 (seul call-site de production) ---")
        rb, rid = face_b(sid, a.seed, a.board)
        rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        print("  runner %s dispose" % rid)
        if not rb.get("ok"):
            ok = False
        else:
            if rb["evicted"] < 1:
                print("  KO [B] : aucune eviction en 4 casts (le call-site n'est pas exerce)")
                ok = False
            if rb["alive"] > rb["max_summons"]:
                print("  KO [B] : %d drones vivants > cap natif %d"
                      % (rb["alive"], rb["max_summons"]))
                ok = False
            if not rb["flags_ok"]:
                print("  KO [B] : un evince ne porte pas le flag `Removed`")
                ok = False

    print("[probe227] VERDICT: %s" % ("OK" if ok else "KO"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
