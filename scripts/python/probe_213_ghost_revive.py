"""Probe #213 -- preuve LIVE end-to-end du time-ghost de `thousTerminator` (<< Toth >>),
le SEUL revive NON-IN-PLACE du binaire (`GhostRevive` / `TimeFlux_Revive`, effet 1186).

i2 : << When Toth moves, he leaves a time ghost behind on the hex he moved from. If Toth is
defeated, he is revived on the hex of the time ghost. >>

CHAINE NATIVE (RE, case-66 §8.2 + #213) :
  Toth bouge -> `IdunBattle.Operations.MoveUnitOperation$$Execute` publie `On(0x1f = PreUnitMove)`
     AVANT toute mutation de position
  -> `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TimeFluxReviveAbility` (=
     `GhostReviveAbility(effectType = 0x4a2 = 1186)`) pose l'effet `GhostEffect` sur
     `CurrentTurnStartTile(self)` = `UnitComponent + 0x18c` (la tuile de DEBUT DE TOUR)
  -> Toth meurt ailleurs : `KillUnitOperation$$Execute` emet `On(1 = PreUnitDeath)`
  -> `IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateTargetTrigger` matche
     (`OnPreDeath(ignoreOverkill=1) & AreEqual(EffectSource, target)`) et son behaviour appelle
     `DSLFactory.Revive(src, src, hp, healType=2, 1186, **tiles = Owner@0x148**)`
  -> `ReviveBehaviour$$Execute` ecrit une `ReviveData` DONT le `Nullable<UnitPosition>` est
     renseigne (7e argument non nul) -> la garde de `KillUnitOperation` ECHOUE (mort ANNULEE) et
     `IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition` DEPLACE Toth sur la tuile du ghost.

DISCRIMINANT (le coeur du probe) : la tuile de MORT et la tuile de REVIVE doivent DIFFERER.
Le montage force donc `A != B` -- Toth demarre son tour en `A`, se deplace en `B`, y meurt, et
doit reapparaitre en **`A`**. Un port qui ressusciterait en place rendrait `B` : le montage
discrimine. Un revive in-place serait indetectable sur une geometrie ou A == B.

Usage : python probe_213_ghost_revive.py   (ASCII only, depuis scripts/python)
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
STATE = str(ROOT / "logs" / "_probe213_ghost_state.json")
HERO = "thousTerminator"          # Toth -- passif TimeFlux (regen + ghost-revive)
FOE = "astraBullgryn"             # melee, gros degat de charge -> tue Toth d'un coup
# 2e ennemi laisse A SON SPAWN, jamais pilote : il garde son action apres le coup fatal, ce qui
# EMPECHE la bascule automatique de tour. Sans lui, le runner enchaine `StartTurnOperation` du camp
# de Toth juste apres le revive et la REGEN `TimeFlux` (`On(TurnStart_Other)`, +hpToHeal) s'ajoute
# aux PV de resurrection -- MESURE : 4487 = 3290 (revive) + 1197 (regen), un CONFOND de portee de
# mesure, pas une divergence de montant.
FOE_IDLE = "orksNob"
BOARD = "MC1_67"
GHOST_EFFECT = 1186               # EffectType.TimeFlux_Revive
HP_PLAYER = 12000                 # > reviveHP (=round(TimeFlux.hp[L50] x mult)) -> pas de clamp maxHP
DMG_TARGET = 99999                # `--dmg-target` : le coup de l'ennemi est LETAL a coup sur


def rpc(sid, m, args, t=90):
    return (_rpc(sid, m, [args], timeout=t).get("result") or {})


def build(seed: int, board: str):
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
           "--p-units", HERO, "--a-units", "%s,%s" % (FOE, FOE_IDLE),
           "--hp-player", str(HP_PLAYER), "--dmg-target", str(DMG_TARGET),
           "--no-ai", "--board", board, "--state-file", STATE]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True)
    if p.returncode != 0:
        sys.stdout.write(p.stdout[-1500:])
        sys.stdout.write(p.stderr[-2000:])
        raise SystemExit("build KO")
    return json.loads(Path(STATE).read_text(encoding="utf-8"))["runnerId"]


def view(sid, rid):
    dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    out = {}
    for o in (ob.get("units") or []):
        out[o.get("visualId")] = {"id": o.get("id"), "col": o.get("col"), "row": o.get("row"),
                                  "hp": o.get("hp"), "hpMax": o.get("hpMax"),
                                  "isDead": o.get("isDead"), "effects": []}
    for u in (dv.get("units") or []):
        vid = u.get("visualId")
        p = u.get("pos") or {}
        cur = out.setdefault(vid, {})
        cur["id"] = u.get("id", cur.get("id"))
        if p.get("col") is not None:
            cur["col"], cur["row"] = p.get("col"), p.get("row")
        cur.setdefault("hp", u.get("hp"))
        cur["hasAction"] = u.get("hasAction")
        cur["effects"] = [e.get("name") for e in (u.get("effects") or [])]
    return dv, out


def act(sid, rid, action, t=90):
    return rpc(sid, "applyAction", {"runnerId": rid, "action": action}, t)


def movable(sid, rid, uid):
    r = rpc(sid, "aiMovableTiles", {"runnerId": rid, "unitId": uid}, 90)
    for u in (r.get("units") or []):
        if u.get("unitId") == uid:
            return [(t.get("col"), t.get("row")) for t in (u.get("tiles") or [])]
    return [(t.get("col"), t.get("row")) for t in (r.get("unionTiles") or [])]


def step_towards(sid, rid, uid, goal):
    tiles = movable(sid, rid, uid)
    if not tiles:
        return None
    tiles.sort(key=lambda t: hexgeo.distance(t, goal))
    act(sid, rid, {"kind": "move", "unitId": uid, "to": {"col": tiles[0][0], "row": tiles[0][1]}})
    return tiles[0]


def normal_attack_id(dv, caster_id, target_id):
    for p in (dv.get("attackPlans") or []):
        if p.get("unitId") == caster_id:
            for ev in (p.get("evals") or []):
                if ev.get("targetId") == target_id:
                    return ev.get("abilityId")
    return None


def ghost_tiles(sid, rid):
    """Tuiles (col,row) portant LIVE l'effet 1186 (`tileMeta.tiles[].effects[].effectType`)."""
    tm = rpc(sid, "tileMeta", {"runnerId": rid}, 90)
    rows = tm.get("tiles") if isinstance(tm, dict) else tm
    out = []
    for t in (rows or []):
        for e in (t.get("effects") or []):
            if int(e.get("effectType") or -1) == GHOST_EFFECT:
                out.append((t.get("col"), t.get("row"), int(e.get("remaining") or 0)))
    return out


def approach(sid, rid, uu):
    """DRIVE la geometrie : l'ennemi au CONTACT de Toth (les deux camps sont pilotables)."""
    for _ in range(12):
        _, uu = view(sid, rid)
        hpos = (uu[HERO]["col"], uu[HERO]["row"])
        fpos = (uu[FOE]["col"], uu[FOE]["row"])
        if hexgeo.distance(fpos, hpos) <= 1:
            return uu
        step_towards(sid, rid, uu[HERO]["id"], fpos)
        act(sid, rid, {"kind": "endturn"})
        _, uu = view(sid, rid)
        step_towards(sid, rid, uu[FOE]["id"], (uu[HERO]["col"], uu[HERO]["row"]))
        act(sid, rid, {"kind": "endturn"})
    _, uu = view(sid, rid)
    return uu


def wait_for_hero_action(sid, rid):
    """Cloture des tours jusqu'a ce que Toth ait une action DISPONIBLE. Effet de bord VOULU :
    chaque `endturn` fait tourner le `StartTurnOperation` natif, qui (re)ecrit
    `UnitComponent + 0x18c` = la tuile de debut de tour -- le champ que lit `CurrentTurnStartTile`."""
    for _ in range(6):
        dv, uu = view(sid, rid)
        if uu.get(HERO, {}).get("hasAction"):
            return dv, uu
        act(sid, rid, {"kind": "endturn"})
    return view(sid, rid)


def run_live(sid, seed, board):
    """Scenario LIVE complet. Rend le dict de mesure (ou None si la geometrie n'a pas pu etre montee)."""
    rid = build(seed, board)
    try:
        _, uu = view(sid, rid)
        for k in (HERO, FOE):
            if k not in uu:
                print("  MISSING %s" % k)
                return None, rid
        uu = approach(sid, rid, uu)
        dv, uu = wait_for_hero_action(sid, rid)
        if not uu.get(HERO, {}).get("hasAction"):
            print("  Toth sans action apres 6 endturn -- scenario KO")
            return None, rid
        hid, fid = uu[HERO]["id"], uu[FOE]["id"]
        A = (uu[HERO]["col"], uu[HERO]["row"])           # tuile de DEBUT DE TOUR (= +0x18c)
        fpos = (uu[FOE]["col"], uu[FOE]["row"])
        ghosts_before = ghost_tiles(sid, rid)
        # --- choix de B : une tuile ATTEIGNABLE, != A, et ADJACENTE a l'ennemi (pour qu'il puisse
        #     frapper sans bouger -- son chemin ne traversera donc jamais A et ne dissipera pas le ghost).
        cand = [t for t in movable(sid, rid, hid)
                if t != A and hexgeo.distance(t, fpos) <= 1]
        if not cand:
            print("  aucune tuile B (!= A, adjacente a l'ennemi) atteignable -- scenario KO")
            return None, rid
        cand.sort(key=lambda t: -hexgeo.distance(t, A))   # la plus ELOIGNEE de A -> discriminant net
        B = cand[0]
        act(sid, rid, {"kind": "move", "unitId": hid, "to": {"col": B[0], "row": B[1]}})
        _, uu = view(sid, rid)
        pos_after_move = (uu[HERO]["col"], uu[HERO]["row"])
        ghosts_after = ghost_tiles(sid, rid)
        print("  A (turn-start) = %s | B (apres move) = %s | dist = %d" % (
            A, pos_after_move, hexgeo.distance(A, pos_after_move)))
        print("  ghost 1186 : avant move = %s | apres move = %s" % (ghosts_before, ghosts_after))
        # --- tour adverse : l'ennemi (deja au contact de B) porte le coup FATAL --------------------
        act(sid, rid, {"kind": "endturn"})
        dv, uu = view(sid, rid)
        nid = normal_attack_id(dv, fid, hid)
        if nid is None:
            print("  pas de plan d'attaque ennemi -> Toth -- scenario KO")
            return None, rid
        hp0 = int(uu[HERO]["hp"])
        act(sid, rid, {"kind": "ability", "casterId": fid, "targetId": hid, "abilityType": nid})
        _, uu2 = view(sid, rid)
        h = uu2[HERO]
        res = {"A": A, "B": pos_after_move, "pos_after_death": (h["col"], h["row"]),
               "hp_before": hp0, "hp_after": h.get("hp"), "hp_max": h.get("hpMax"),
               "isDead": h.get("isDead"),
               "ghosts_before_move": ghosts_before, "ghosts_after_move": ghosts_after,
               "ghosts_after_death": ghost_tiles(sid, rid)}
        print("  Toth hp %s -> %s  isDead=%s  pos %s -> %s" % (
            hp0, h.get("hp"), h.get("isDead"), pos_after_move, res["pos_after_death"]))
        return res, rid
    except Exception as exc:                              # noqa: BLE001 (diagnostic de probe)
        print("  EXC live: %r" % (exc,))
        return None, rid


def run_port(sid, seed, board):
    """MEME scenario, rejoue par le PORT sur l'etat LIVE-capte (positions REELLES, stats/traits/effets
    captes) : on charge l'etat JUSTE AVANT le move, on rejoue le move par `MoveUnitOperation` puis la
    mort par le VRAI chokepoint `_fire_death_if_killed`."""
    from engine.runner.operations.movement import MoveUnitOperation
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.components import UnitComponent, HealthComponent, PositionComponent
    from engine.runner.snapshot import load_state
    from engine.runner.operations.turnflow import StartTurnOperation
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.events import EventBus
    from engine.entities.pathfinding.board import Board
    rid = build(seed, board)
    try:
        _, uu = view(sid, rid)
        uu = approach(sid, rid, uu)
        dv, uu = wait_for_hero_action(sid, rid)
        hid, fid = uu[HERO]["id"], uu[FOE]["id"]
        A = (uu[HERO]["col"], uu[HERO]["row"])
        fpos = (uu[FOE]["col"], uu[FOE]["row"])
        cand = [t for t in movable(sid, rid, hid) if t != A and hexgeo.distance(t, fpos) <= 1]
        if not cand:
            print("  [port] aucune tuile B -- scenario KO")
            return None, rid
        cand.sort(key=lambda t: -hexgeo.distance(t, A))
        B = cand[0]
        snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
        ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        tm = rpc(sid, "tileMeta", {"runnerId": rid}, 90)
        board_obj = Board(bg["tiles"], adjacency="evenq") if (bg or {}).get("tiles") else None
        st = load_state(dv, ob, snap, board=board_obj, tiles=tm)
        st.rng = IntBasedMersenneTwister(12345)
        # `StartTurnOperation` du joueur de Toth, seul ecrivain natif de `UnitComponent + 0x18c` --
        # rejoue ici pour reproduire le debut de tour COMPLET (flags, compteurs, triggers), pas
        # seulement la tuile : celle-ci est desormais CAPTEE (`combatSnapshot.currentTurnStartTile`,
        # `f790ff4`) et SEEDEE par `load_state` (#230).
        from engine.runner.components import OwnerComponent
        pl = st.get_entity(hid).get_component(OwnerComponent).player
        StartTurnOperation.execute(st, pl)
        uc = st.get_entity(hid).get_component(UnitComponent)
        print("  [port] current_turn_start_tile = %s (tuile de A=%s -> %s)" % (
            uc.current_turn_start_tile, A, board_obj.id_at(A[0], A[1])))
        # --- MOVE : `MoveUnitOperation.execute` -> `On(PreUnitMove)` -> pose du ghost ---------------
        MoveUnitOperation(hid, B).execute(st, EventBus())
        ghost_port = sorted([(int(t), [e.effect_type for e in effs if not e.consumed])
                             for t, effs in (st.effects.by_unit or {}).items()
                             if int(t) in (board_obj.by_id or {})
                             and any((not e.consumed) and e.effect_type == GHOST_EFFECT for e in effs)])
        print("  [port] tuiles portant 1186 apres move : %s (attendu tile(A) = %s)"
              % ([t for t, _ in ghost_port], board_obj.id_at(A[0], A[1])))
        # --- MORT en B : le VRAI chokepoint ---------------------------------------------------------
        e = st.get_entity(hid)
        hc = e.get_component(HealthComponent)
        hp_before = int(hc.hp)
        hc.hp = 0
        out = AttackDamageOperation._fire_death_if_killed(st, hid, fid, hp_before, 0, e,
                                                          damage=hp_before)
        pc = e.get_component(PositionComponent)
        res = {"A": A, "B": B, "alive": bool(uc.alive), "hp": hc.hp,
               "pos_after_death": (pc.col, pc.row),
               "ghost_tiles_after_move": [t for t, _ in ghost_port],
               "tile_of_A": board_obj.id_at(A[0], A[1]),
               "revived_by": sorted(uc.revived_by_abilities)}
        for r in (out or []):
            if isinstance(r, dict) and ("kill_cancelled_by_revive" in r or r.get("ability") == "TimeFlux"):
                print("     %s" % json.dumps(r, default=str)[:260])
        print("  [port] alive=%s hp=%s pos %s -> %s" % (res["alive"], res["hp"], B,
                                                        res["pos_after_death"]))
        return res, rid
    except Exception as exc:                              # noqa: BLE001
        import traceback
        print("  EXC port: %r" % (exc,))
        traceback.print_exc()
        return None, rid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=31337)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--live-only", action="store_true")
    ap.add_argument("--port-only", action="store_true")
    a = ap.parse_args()
    sid = _resolve_session()
    print("[probe213] GhostRevive / TimeFlux_Revive (thousTerminator) -- revive NON in-place")
    print("[probe213] seed=%s board=%s hp_player=%d dmg_target=%d" % (
        a.seed, a.board, HP_PLAYER, DMG_TARGET))
    ok = True
    live = port = None
    if not a.port_only:
        print("[probe213] --- LIVE ---")
        live, rid = run_live(sid, a.seed, a.board)
        rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        print("  runner %s dispose" % rid)
    if not a.live_only:
        print("[probe213] --- PORT (meme etat live-capte) ---")
        port, rid2 = run_port(sid, a.seed, a.board)
        rpc(sid, "disposeRunner", {"runnerId": rid2}, 60)
        print("  runner %s dispose" % rid2)

    print("[probe213] ---- SYNTHESE ----")
    if live is not None:
        same = live["A"] == live["B"]
        print("  LIVE : A=%s B=%s (A==B ? %s) -> pos apres mort = %s | isDead=%s | hp=%s"
              % (live["A"], live["B"], same, live["pos_after_death"], live["isDead"],
                 live["hp_after"]))
        print("  LIVE : ghost apres move = %s | apres mort = %s"
              % (live["ghosts_after_move"], live["ghosts_after_death"]))
        if same:
            print("  KO LIVE : A == B -> le montage NE DISCRIMINE PAS (revive in-place indetectable)")
            ok = False
        if live["isDead"]:
            print("  KO LIVE : Toth est MORT -- pas de ghost-revive")
            ok = False
        elif tuple(live["pos_after_death"]) != tuple(live["A"]):
            print("  KO LIVE : revive sur %s, attendu la tuile du ghost %s"
                  % (live["pos_after_death"], live["A"]))
            ok = False
    if port is not None:
        print("  PORT : A=%s B=%s -> alive=%s pos=%s hp=%s | ghost sur tuiles %s (tile(A)=%s)"
              % (port["A"], port["B"], port["alive"], port["pos_after_death"], port["hp"],
                 port["ghost_tiles_after_move"], port["tile_of_A"]))
        if port["ghost_tiles_after_move"] != [port["tile_of_A"]]:
            print("  KO PORT : le ghost n'est pas (uniquement) sur la tuile de debut de tour")
            ok = False
        if not port["alive"]:
            print("  KO PORT : Toth est mort -- le ghost n'a pas ressuscite")
            ok = False
        elif tuple(port["pos_after_death"]) != tuple(port["A"]):
            print("  KO PORT : revive sur %s, attendu %s" % (port["pos_after_death"], port["A"]))
            ok = False
    if live is not None and port is not None:
        if (not live["isDead"]) and port["alive"]:
            if int(live["hp_after"]) != int(port["hp"]):
                print("  KO : hp de revive live=%s port=%s" % (live["hp_after"], port["hp"]))
                ok = False
            else:
                print("  OK : hp de revive IDENTIQUE live/port = %s" % port["hp"])
            if tuple(live["pos_after_death"]) != tuple(port["pos_after_death"]):
                print("  KO : position de revive live=%s port=%s"
                      % (live["pos_after_death"], port["pos_after_death"]))
                ok = False
    if live is None and port is None:
        ok = False
    print("[probe213] VERDICT: %s" % ("OK" if ok else "KO"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
