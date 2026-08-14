"""#1080 -- confrontation LIVE des deux passives `BattleFocus` (1172/1199) et
`CallInReinforcements` (1029), portees dans cette tranche.

Les DEUX porteurs arrivent par le CHEMIN DE STATS EXPLICITE (`--explicit-stats <npc>:45`), leur
jumeau summon n'ayant aucun invocateur atteignable (cf. les en-tetes des deux modules portes).

Volet `CallInReinforcements` : le Vox-caster CLOT son activation -> le natif spawne un
`astraSmnGuardsman` sur une tuile de BORD libre, qui joue immediatement son tour. On compare
l'EXISTENCE, la TUILE et le camp, live vs port, AVEC et SANS l'entree au registre (contre-epreuve
par MUTATION).

Volet `BattleFocus` : le Guardian attaque (ou est attaque) -> le natif le DEPLACE d'un hex vers la
tuile la plus eloignee des ennemis. On compare la POSITION FINALE, live vs port, avec et sans.

⚠ **TEMOIN NON DEGENERE.** Les deux voletsONT un regime ou le port SANS le passif rend un resultat
DIFFERENT (pas de summon / pas de deplacement) : le bras `sans` est donc discriminant par
construction. C'est le point que case-1052 a du apprendre a la dure (`port_avec == port_sans` au
palier 3 sur un plancher de percage).

Usage (depuis `scripts/python`, session Frida warmee) :
    python probe_1080_battle_focus_call_in_reinforcements.py --volet tous --state-file <ABSOLU>
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from rl_collect_batch import _rpc, _resolve_session          # noqa: E402

SEED = "777"
BOARD = "MC1_67"
#: PALIER 45 = `units.npc[].stats[44]`, le DERNIER. Ici le palier n'est PAS une condition
#: d'observabilite (aucun plancher de percage en jeu) mais il rend le porteur SURVIVABLE : au palier
#: 3 le Vox-caster (28 PV) meurt au premier coup et ne clot jamais son activation.
VOX = "astraNpc3Voxcaster:45"
VOX_VIS = "astraNpc3Voxcaster"
GUARDIAN = "eldarNpc1Guardian:45"
GUARDIAN_VIS = "eldarNpc1Guardian"
#: `constants.unitId` de `CallInReinforcements` = `astraSmnGuardsman`, dont le `visualId` (la clef
#: que `decisionView` rend) est `astraNpc1Guardsman` -- LU au gameconfig
#: (`units.summons.astraSmnGuardsman.visualId`), jamais suppose egal a l unitId.
GUARDSMAN_VIS = "astraNpc1Guardsman"
#: Adversaires : deux corps a corps ordinaires, sans aura qui changerait le nombre de coups ou la
#: geometrie (le piege `astraBullgryn`/`BigTarget` de case-1052).
ENEMIS = "orksNob,darkaAsmodai"


def _build(state_file: str, extra: list) -> dict:
    """`rl_duel build` en sous-processus, `--state-file` ABSOLU (discipline runner.md Sec.3)."""
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
           "--state-file", state_file, *extra]
    r = subprocess.run(cmd, cwd=str(_HERE), capture_output=True, text=True, timeout=600)
    out = {"rc": r.returncode, "stdout": r.stdout[-3000:], "stderr": r.stderr[-1500:]}
    try:
        out["rid"] = json.loads(Path(state_file).read_text(encoding="utf-8")).get("runnerId")
    except Exception as exc:                                  # noqa: BLE001
        out["rid"] = None
        out["why"] = "state-file illisible : %s" % exc
    return out


def _dispose(sid, rid):
    if rid is not None:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
        except Exception:                                     # noqa: BLE001
            pass


def _res(sid, method, args, timeout=60):
    return (_rpc(sid, method, [args], timeout=timeout) or {}).get("result") or {}


def _board_of(sid, rid):
    from engine.entities.pathfinding.board import Board
    bg = (_rpc(sid, "boardGraph", [{"runnerId": rid}], timeout=60) or {}).get("result") or {}
    if not bg.get("tiles"):
        return None
    return Board(bg["tiles"], adjacency="native_sym")


def _alive(dv):
    return [u for u in (dv.get("units") or []) if u.get("alive")]


def _by_vis(dv, vis):
    return next((u for u in _alive(dv) if u.get("visualId") == vis), None)


def _pos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _normal_attack_type(dv, uid):
    for u in (dv.get("units") or []):
        if int(u.get("id", -1)) == int(uid):
            for ab in (u.get("abilities") or []):
                if ab.get("kind") == "normal" and ab.get("id") is not None:
                    return int(ab["id"])
    return None


def _snapshot(sid, rid):
    return {
        "dv": _res(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120),
        "ob": _res(sid, "observeBattle", {"runnerId": rid}, 60),
        "snap": _res(sid, "combatSnapshot", {"runnerId": rid}, 90),
        "rng": _res(sid, "dumpRng", {"runnerId": rid}, 30),
    }


def _offline_state(s, board):
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state
    st = load_state(s["dv"], s["ob"], s["snap"], board=board)
    r = s.get("rng") or {}
    if r.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(r["mt"])
        rng.mti = r["mti"]
        st.rng = rng
    return st


def _place(sid, rid, uid, coord):
    return _res(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid),
        "to": {"col": int(coord[0]), "row": int(coord[1])}}}, 40)


# ================================================================== volet CallInReinforcements

def volet_call_in_reinforcements(sid, state_file, vox_pos: str = "") -> dict:
    """Le Vox-caster CLOT son activation -> `On(0x29 = UnitFinishedTurnNormally) & OwnerIsActor`.

    `vox_pos` (`col,row`) place le porteur sur une TUILE EXACTE : c est ce qui rend la mesure
    DISCRIMINANTE, la tuile de spawn etant l argmax de `-distance/10` a la main tile du porteur.
    Vide = spawn points du board."""
    out = {"volet": "callinreinforcements", "vox_pos_demandee": vox_pos or None, "ok": False}
    extra = ["--p-units", VOX, "--a-units", ENEMIS,
             "--explicit-stats", VOX, "--roster", "1", "--no-ai"]
    if vox_pos:
        extra += ["--place", "%s:%s" % (VOX, vox_pos)]
    b = _build(state_file, extra)
    out["build_rc"] = b["rc"]
    rid = b.get("rid")
    out["rid"] = rid
    if rid is None:
        out["why"] = "build KO : %s" % (b.get("stderr") or b.get("stdout"))[-800:]
        return out
    board = _board_of(sid, rid)
    if board is None:
        out["why"] = "boardGraph indispo"
        _dispose(sid, rid)
        return out

    dv = _res(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    vox = _by_vis(dv, VOX_VIS)
    if vox is None:
        out["why"] = "porteur absent : %s" % sorted({u.get("visualId") for u in _alive(dv)})
        _dispose(sid, rid)
        return out
    out["vox_id"] = int(vox["id"])
    out["vox_pos"] = _pos(vox)
    out["avant_units"] = sorted({u.get("visualId") for u in _alive(dv)})

    # ETAT AVANT, fige : c'est LUI que le port rejoue.
    s0 = _snapshot(sid, rid)

    # LIVE : le Vox-caster clot son activation. `finishturn` sur l'unite = le vecteur natif
    # `FinishUnitTurnOperation$$Execute` -> `On(0x28)` puis, si !isTerminated, `On(0x29)`.
    act = _res(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "finish", "unitId": int(vox["id"])}}, 120)
    a0 = (act.get("actions") or [{}])[0]
    out["act_ok"] = bool(a0.get("ok"))
    if not out["act_ok"]:
        out["act_raw"] = str(act)[:600]
    # ⚠ LA POSITION FINALE DU SUMMON N EST PAS SA TUILE DE SPAWN : le on-appearance
    # `PerformAIAttack(ActiveTarget, allowOnlyMove = 1, moveAmount = null)` lui fait jouer un TOUR
    # COMPLET, donc il S APPROCHE avant de frapper (#348). La tuile de SPAWN se lit dans les
    # EVENEMENTS de l action, pas dans le `decisionView` d apres.
    evs = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        evs.append({k: td.get(k) for k in td if td.get(k) is not None})
    # La tuile de SPAWN = le `Unit_Foot_Tile_Id_1` du PREMIER evenement porteur de
    # `Unit_IsSummoned` ; les `Unit_Foot_Tile_Id_1` suivants (avec `Is_Last_Tile`) sont les PAS du
    # deplacement que le on-appearance lui fait faire.
    spawn_tid = next((e.get("Unit_Foot_Tile_Id_1") for e in evs
                      if e.get("Unit_IsSummoned") and e.get("Unit_Foot_Tile_Id_1") is not None),
                     None)
    out["live_spawn_tile_id"] = spawn_tid
    out["live_spawn_tile"] = board.coord(int(spawn_tid)) if spawn_tid is not None else None
    out["live_pas"] = [e.get("Unit_Foot_Tile_Id_1") for e in evs
                       if e.get("Is_Last_Tile") is not None]
    out["events_bruts"] = evs[:6]
    dv2 = _res(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    smn = _by_vis(dv2, GUARDSMAN_VIS)
    out["live_summon"] = _pos(smn)
    out["live_summon_id"] = int(smn["id"]) if smn else None
    out["apres_units"] = sorted({u.get("visualId") for u in _alive(dv2)})

    # PORT, deux regimes : AVEC l'entree au registre, puis SANS (mutation).
    import engine.runner.operations.triggers.dispatch.registry as R
    from engine.runner.operations.triggers.loki.call_in_reinforcements import (
        CALL_IN_REINFORCEMENTS_KEY, CallInReinforcementsAbility)
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.dsl.event_trigger_type import EventTriggerType

    def _port(avec: bool):
        st = _offline_state(s0, board)
        ab = CallInReinforcementsAbility(int(vox["id"]))
        ev = TriggerEvent(int(EventTriggerType.UnitFinishedTurnNormally),
                          int(vox["id"]), int(vox["id"]), ranged=False, profile=None)
        garde = R.ABILITY_TRIGGERS.get(CALL_IN_REINFORCEMENTS_KEY)
        if not avec:
            # MUTATION : le passif quitte le registre -> `collect_triggered_abilities` ne le monte
            # plus, donc rien ne fire. On mirrore ce regime en n'appelant tout simplement pas.
            R.ABILITY_TRIGGERS.pop(CALL_IN_REINFORCEMENTS_KEY, None)
        try:
            if not avec or CALL_IN_REINFORCEMENTS_KEY not in R.ABILITY_TRIGGERS:
                return {"fired": False, "tiles": [], "spawned": []}
            if not ab.matches(st, ev):
                return {"fired": False, "tiles": [], "spawned": []}
            r = ab.execute_behaviour(st, ev) or {}
            tiles = [board.coord(t) for t in (r.get("tiles") or []) if t is not None]
            return {"fired": True, "tiles": tiles, "spawned": r.get("spawned") or [],
                    "ai_actions": r.get("ai_actions")}
        finally:
            if garde is not None:
                R.ABILITY_TRIGGERS[CALL_IN_REINFORCEMENTS_KEY] = garde

    out["port_avec"] = _port(True)
    out["port_sans"] = _port(False)
    # CRITERE : la TUILE DE SPAWN, pas la position finale (cf. le bloc ci-dessus).
    out["ok"] = (out["live_spawn_tile"] is not None
                 and out["port_avec"]["fired"]
                 and out["port_avec"]["tiles"][:1] == [out["live_spawn_tile"]]
                 and not out["port_sans"]["fired"])
    _dispose(sid, rid)
    return out


# ============================================================================ volet BattleFocus

def volet_battle_focus(sid, state_file, geo: str = "sud") -> dict:
    """Le Guardian attaque -> `On(0xb = UnitAbility)` -> `TriggerAbilityDelayed(1172)` -> il se
    DEPLACE d'un hex, le plus loin possible des ennemis."""
    # DEUX geometries, pour que l accord ne tienne pas a UNE configuration : dans `sud` les ennemis
    # sont EN DESSOUS du porteur (il doit fuir vers le HAUT), dans `nord` AU-DESSUS (il doit fuir
    # vers le BAS). Une reponse constante ne peut pas satisfaire les deux.
    GEOS = {"sud": (("3,4"), ("3,6"), ("4,6")), "nord": (("3,4"), ("3,2"), ("4,2"))}
    g_pos, e1, e2 = GEOS[geo]
    out = {"volet": "battlefocus", "geo": geo, "ok": False}
    # GEOMETRIE PILOTEE (jamais subie) : le Guardian a une arme de portee 2 ; sans placement
    # explicite, les spawn points de MC1_67 le laissent a ~8 hex de sa cible et l attaque est un
    # NO-OP -- l accord obtenu ne dirait alors rien. Les deux ennemis sont poses a distance 2 et 4
    # du porteur, du MEME cote, pour que la tuile la plus SURE au sens de `SafestTiles` soit du cote
    # OPPOSE et donc DISCRIMINANTE.
    b = _build(state_file, ["--p-units", GUARDIAN, "--a-units", ENEMIS,
                            "--explicit-stats", GUARDIAN, "--roster", "1", "--no-ai",
                            "--crit", "0,0", "--block-target", "0,0",
                            "--place", "%s:%s" % (GUARDIAN, g_pos),
                            "--a-place", "orksNob:%s" % e1,
                            "--a-place", "darkaAsmodai:%s" % e2])
    out["build_rc"] = b["rc"]
    rid = b.get("rid")
    out["rid"] = rid
    if rid is None:
        out["why"] = "build KO : %s" % (b.get("stderr") or b.get("stdout"))[-800:]
        return out
    board = _board_of(sid, rid)
    if board is None:
        out["why"] = "boardGraph indispo"
        _dispose(sid, rid)
        return out

    dv = _res(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    g = _by_vis(dv, GUARDIAN_VIS)
    if g is None:
        out["why"] = "porteur absent : %s" % sorted({u.get("visualId") for u in _alive(dv)})
        _dispose(sid, rid)
        return out
    out["porteur_id"] = int(g["id"])
    out["effets_porteur"] = [e.get("name") for e in (g.get("effects") or [])]
    cibles = [u for u in _alive(dv) if int(u["id"]) != int(g["id"])]
    if not cibles:
        out["why"] = "aucune cible"
        _dispose(sid, rid)
        return out
    cible = cibles[0]
    out["cible_id"] = int(cible["id"])
    out["pos_avant"] = _pos(g)
    out["cible_pos"] = _pos(cible)

    s0 = _snapshot(sid, rid)
    nat = _normal_attack_type(dv, int(g["id"]))
    out["normal_attack"] = nat
    if nat is None:
        out["why"] = "attaque normale introuvable"
        _dispose(sid, rid)
        return out

    act = _res(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(g["id"]), "targetId": int(cible["id"]),
        "abilityType": int(nat)}}, 120)
    out["act_ok"] = bool((act.get("actions") or [{}])[0].get("ok"))
    dv2 = _res(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    g2 = next((u for u in _alive(dv2) if int(u["id"]) == int(g["id"])), None)
    out["pos_apres_live"] = _pos(g2)
    out["live_a_bouge"] = (out["pos_apres_live"] != out["pos_avant"])

    # PORT : on rejoue le vecteur `On(0xb)` sur l'etat AVANT, avec et sans le trigger d'effet.
    from engine.runner.operations.triggers.loki.battle_focus import (
        BattleFocusEffectTrigger, BattleFocusMoveAbility)
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.components import PositionComponent

    def _port(avec: bool):
        st = _offline_state(s0, board)
        # `ability_type = 1013` : sur la VOIE NORMALE le port thread le marqueur
        # attaque-normale (`dispatch/attack.py` : `unit_ability_triggers(..., ability_type=1013)`),
        # pas l id CONCRET de l arme -- c est ce que lit `AbilityHasAttackType(CurrentAbility, 0)`.
        ev = TriggerEvent(int(EventTriggerType.UnitAbility), int(g["id"]), int(cible["id"]),
                          ranged=True, profile=None, ability_type=1013)
        trg = BattleFocusEffectTrigger(int(g["id"]))
        fired = bool(trg.matches(st, ev))
        moved = None
        if fired and avec:
            trg.execute_behaviour(st, ev)
            mv = BattleFocusMoveAbility(int(g["id"]))
            mv.execute_behaviour(st, TriggerEvent(int(EventTriggerType.Custom),
                                                  int(g["id"]), int(g["id"]),
                                                  ranged=False, profile=None))
            e = st.get_entity(int(g["id"]))
            pc = e.get_component(PositionComponent) if e is not None else None
            moved = (pc.col, pc.row) if pc is not None else None
        elif fired:
            e = st.get_entity(int(g["id"]))
            pc = e.get_component(PositionComponent) if e is not None else None
            moved = (pc.col, pc.row) if pc is not None else None
        return {"fired": fired, "pos": moved}

    out["port_avec"] = _port(True)
    out["port_sans"] = _port(False)
    out["ok"] = (out["port_avec"]["fired"]
                 and out["port_avec"]["pos"] != out["port_sans"]["pos"])
    _dispose(sid, rid)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--volet", choices=["battlefocus", "callinreinforcements", "tous"],
                    default="tous")
    ap.add_argument("--state-file", required=True)
    a = ap.parse_args()
    sid = _resolve_session()
    res = []
    if a.volet in ("callinreinforcements", "tous"):
        res.append(volet_call_in_reinforcements(sid, a.state_file, ""))
        res.append(volet_call_in_reinforcements(sid, a.state_file, "5,5"))
    if a.volet in ("battlefocus", "tous"):
        res.append(volet_battle_focus(sid, a.state_file, "sud"))
        res.append(volet_battle_focus(sid, a.state_file, "nord"))
    print(json.dumps(res, indent=1, default=str))
    return 0 if all(r.get("ok") for r in res) else 1


if __name__ == "__main__":
    raise SystemExit(main())
