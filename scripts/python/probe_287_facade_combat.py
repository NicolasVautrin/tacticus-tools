"""probe #287 -- face COMBAT de SorcerousFacade (1100), LIVE vs OFFLINE.

CE QUE CE PROBE MESURE, et pourquoi chaque point est DISCRIMINANT

`IdunBattleLogic.Entities.Abilities.Active.Loki.SorcerousFacadeAbility$$ExecuteBehaviour` a QUATRE
termes, et chacun a un observable PROPRE. Un port qui n'en porterait que trois passerait n'importe
quel test global d'accord de position : il faut les separer.

  [1] `AddEffect(0x4b4 = 1204 SorcerousFacade_AdditionalHits -> Caster + Target, TurnsFromRounds(1))`
      -> observable : `decisionView.units[].effects[].name` sur LES DEUX unites.
  [2] `UseActiveAbility(Caster, sel, UnitNormalAttackType)` ou `sel` = l'ENNEMI le plus proche
      attaquable a l'attaque normale -- **PAS la cible du cast**, qui est l'allie.
      -> observable : les PV de l'ENNEMI baissent, ceux de l'ALLIE ne bougent pas.
  [3] `KillDeadUnits(Caster, sel)` : structurel (la mort est finalisee inline cote port).
  [4] `TriggerAbilityDelayed(Owner, 0x49c = 1180 SorcerousFacade_Switch, 3)` -> `SwitchPosition`
      -> observable : caster et allie ECHANGENT leurs tuiles.

LE POINT LE PLUS IMPORTANT est le [4] : le natif PLANIFIE ce declenchement (service de triggers
differes). Le port le COLLAPSE inline en queue d'arbre. Ce probe TRANCHE la question « le switch
a-t-il lieu DANS le cast, ou au tour suivant ? » par la mesure -- si les positions n'avaient pas
change juste apres `applyAction`, le collapse serait FAUX et le port devrait planifier.

MONTAGE (board MC1_67) : caster `thousTzaangor`, allie Psyker `thousSorcerer` place LOIN (le switch
doit etre visible), ennemi `ultraTitus` colle au caster (pour que `sel` existe ET que la regle
dynamique `SorcerousFacadeAbility$$GetDynamicInvalidTargetReason` -- qui exige que le caster puisse
porter son attaque normale -- soit satisfaite), 2e ennemi `ultraCalgar` relegue au loin.

Usage :
    python probe_287_facade_combat.py            # build + mesure LIVE + replay OFFLINE
    python probe_287_facade_combat.py --keep     # ne dispose pas le runner
ASCII only ; exit 0 = tout conforme.
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
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.snapshot import load_state

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
BOARD = "MC1_67"
SEED = 28701
FACADE = 1100

P_UNITS = "thousTzaangor,thousSorcerer"
A_UNITS = "ultraTitus,ultraCalgar"
CASTER_VID = "thousTzaangor"
ALLY_VID = "thousSorcerer"
FOE_VID = "ultraTitus"
FAR_VID = "ultraCalgar"
EFFECT_NAME = "SorcerousFacade_AdditionalHits"


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


def _effects(dv, uid):
    for u in (dv.get("units") or []):
        if u.get("id") == uid:
            return sorted(e.get("name") for e in (u.get("effects") or []))
    return []


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _free_at(board, center, radius, occupied):
    """1re tuile MARCHABLE a distance hex EXACTEMENT `radius` de `center`, libre. Deterministe."""
    for t in sorted(board.by_id):
        c = board.coord(t)
        if board.walkable(t) and hexgeo.distance(center, c) == radius and c not in occupied:
            return c
    return None


def run(keep: bool = False, swap_foes: bool = False, state_name: str = "rs_287_facade.json",
        seed: int = SEED, board: str = BOARD, far_foes: bool = False) -> dict:
    """`swap_foes` ECHANGE les deux ennemis : celui qui est colle au caster (d=1) devient l'AUTRE.
    C'est le bras DISCRIMINANT du selecteur `First(SortByDistance(ValidNormalAttackTargets, Caster))`
    -- un port qui prendrait « le premier ennemi enumere » au lieu du PLUS PROCHE frapperait la meme
    unite dans les deux bras.

    `far_foes` eloigne LES DEUX ennemis (aucun a portee d'attaque normale) : `sel` est alors VIDE.
    C'est le bras qui mesure ce que devient le cast quand le terme [2] n'a pas de cible -- et donc
    si la regle dynamique NON PORTEE (`GetDynamicInvalidTargetReason`, qui exige que le caster
    puisse porter son attaque normale) REFUSE le cast cote natif."""
    FOE, FAR = (FAR_VID, FOE_VID) if swap_foes else (FOE_VID, FAR_VID)
    return _run_case(keep, FOE, FAR, state_name, seed, board, far_foes)


def _run_case(keep, FOE_VID, FAR_VID, state_name, SEED, BOARD, far_foes=False) -> dict:
    state = LOGS / state_name
    _run(["build", "--seed", str(SEED), "--board", BOARD, "--rank", "17",
          "--p-units", P_UNITS, "--a-units", A_UNITS, "--state-file", str(state)])
    if not state.exists():
        return {"error": "build KO (state-file absent)"}
    rid = int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])
    bg = _rpc("boardGraph", [{"runnerId": rid}])
    board = Board(bg["tiles"], adjacency="native_sym")

    dv = _dview(rid)
    U = _units(dv)
    missing = [v for v in (CASTER_VID, ALLY_VID, FOE_VID, FAR_VID) if v not in U]
    if missing:
        return {"error": "unites absentes du build : %s" % missing}
    caster, ally, foe, far = (U[CASTER_VID], U[ALLY_VID], U[FOE_VID], U[FAR_VID])

    def move(uid, to):
        _rpc("applyAction", [{"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": int(to[0]), "row": int(to[1])}}}], 40000)

    # --- GEOMETRIE : ennemi ADJACENT au caster, allie LOIN, 2e ennemi relegue ---------------------
    c_pos = _pos(caster)
    occ = {_pos(u) for u in U.values()} - {c_pos}
    foe_to = _free_at(board, c_pos, 7 if far_foes else 1, occ)
    if foe_to is None:
        return {"error": "aucune tuile libre a distance %d du caster" % (7 if far_foes else 1)}
    move(foe["id"], foe_to)
    occ = {_pos(u) for u in _units(_dview(rid)).values()}
    ally_to = _free_at(board, c_pos, 5, occ)
    if ally_to is None:
        ally_to = _free_at(board, c_pos, 4, occ)
    if ally_to is None:
        return {"error": "aucune tuile libre a distance pour l'allie"}
    move(ally["id"], ally_to)
    occ = {_pos(u) for u in _units(_dview(rid)).values()}
    far_to = _free_at(board, c_pos, 6, occ)
    if far_to is not None:
        move(far["id"], far_to)

    # Le caster doit avoir un TOUR NEUF (aucun move consomme) : on rend la main puis on revient.
    my_player = caster.get("owner")
    for _ in range(8):
        dv = _dview(rid)
        if dv.get("currentPlayer") == my_player:
            break
        _rpc("applyAction", [{"runnerId": rid, "action": {"kind": "endturn"}}], 40000)

    dv = _dview(rid)
    U = _units(dv)
    WATCH = (CASTER_VID, ALLY_VID, FOE_VID, FAR_VID)
    pre = {v: _pos(U[v]) for v in WATCH if v in U}
    pre_hp = {v: U[v].get("hp") for v in WATCH if v in U}
    ids = {v: U[v]["id"] for v in U}

    # --- cibles LEGALES natives de 1100 (garde le rail ALLIE) ------------------------------------
    at = _rpc("abilityTargets", [{"runnerId": rid, "unitId": ids[CASTER_VID],
                                  "allAbilities": True}])
    legal = []
    for u in (at.get("units") or []):
        for row in (u.get("abilities") or []):
            if int(row.get("abilityId") or -1) == FACADE:
                legal = [t.get("targetId") for t in (row.get("targets") or [])]
    # --- snapshot PRE-cast (le pont vers l'offline) ----------------------------------------------
    snap = {"dv": dv,
            "ob": _rpc("observeBattle", [{"runnerId": rid}], 40000),
            "snap": _rpc("combatSnapshot", [{"runnerId": rid}], 60000),
            "rng": _rpc("dumpRng", [{"runnerId": rid}], 30000)}
    # Flags de tour AVANT le cast (`combatSnapshot.units[].unitFlags`, cle `entityId`) : c'est le
    # SEUL moyen d'attribuer un flag au SWITCH plutot qu'a un `move` anterieur.
    flags_pre = {u.get("entityId"): sorted(u.get("unitFlags") or [])
                 for u in (snap["snap"].get("units") or [])}

    # --- CAST LIVE --------------------------------------------------------------------------------
    res = _rpc("applyAction", [{"runnerId": rid, "action": {
        "kind": "ability", "casterId": ids[CASTER_VID], "targetId": ids[ALLY_VID],
        "abilityType": FACADE}}], 60000)
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    dv2 = _dview(rid)
    U2 = _units(dv2)
    post = {v: (_pos(U2[v]) if v in U2 else None) for v in WATCH}
    post_hp = {v: (U2[v].get("hp") if v in U2 else 0) for v in WATCH}
    live = {
        "ok": bool(a0.get("ok")), "foe": FOE_VID, "far": FAR_VID,
        "pre": pre, "post": post, "pre_hp": pre_hp, "post_hp": post_hp,
        "legal_targets": legal,
        "effects_caster": _effects(dv2, ids[CASTER_VID]),
        "effects_ally": _effects(dv2, ids[ALLY_VID]),
    }
    # Flags de tour APRES le cast -> le DELTA (pre -> post) attribue au cast ce que le switch pose.
    cs2 = _rpc("combatSnapshot", [{"runnerId": rid}], 60000)
    flags_post = {u.get("entityId"): sorted(u.get("unitFlags") or [])
                  for u in (cs2.get("units") or [])}
    live["flags_pre"] = {v: flags_pre.get(ids[v]) for v in (CASTER_VID, ALLY_VID)}
    live["flags_post"] = {v: flags_post.get(ids[v]) for v in (CASTER_VID, ALLY_VID)}
    live["flags_added"] = {v: sorted(set(flags_post.get(ids[v]) or [])
                                     - set(flags_pre.get(ids[v]) or []))
                           for v in (CASTER_VID, ALLY_VID)}

    # --- REPLAY OFFLINE ---------------------------------------------------------------------------
    st = load_state(snap["dv"], snap["ob"], snap["snap"], board=board)
    if isinstance(snap["rng"], dict) and snap["rng"].get("mt"):
        st.rng = _seed_rng(snap["rng"])
    from engine.runner.components import PositionComponent, HealthComponent

    def opos(uid):
        e = st.get_entity(uid)
        pc = e.get_component(PositionComponent) if e is not None else None
        return (pc.col, pc.row) if pc is not None else None

    def ohp(uid):
        e = st.get_entity(uid)
        hc = e.get_component(HealthComponent) if e is not None else None
        return hc.hp if hc is not None else None

    o_pre = {v: opos(ids[v]) for v in WATCH}
    o_pre_hp = {v: ohp(ids[v]) for v in WATCH}
    from engine.runner.runner import Runner
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=ids[CASTER_VID], target_id=ids[ALLY_VID],
                                      ability_type=FACADE))
    ah = runner.ability_handler
    diag = ah.last
    o_post = {v: opos(ids[v]) for v in WATCH}
    o_post_hp = {v: ohp(ids[v]) for v in WATCH}
    o_eff = {}
    if st.effects is not None:
        for v in (CASTER_VID, ALLY_VID):
            o_eff[v] = sorted(e.name for e in st.effects.by_unit.get(ids[v], []) if not e.consumed)
    o_flags = {}
    from engine.runner.components import UnitFlagsComponent
    for v in (CASTER_VID, ALLY_VID):
        e = st.get_entity(ids[v])
        fc = e.get_component(UnitFlagsComponent) if e is not None else None
        o_flags[v] = sorted(fc.flags) if fc is not None else None
    offline = {"pre": o_pre, "post": o_post, "pre_hp": o_pre_hp, "post_hp": o_post_hp,
               "effects": o_eff, "diag": diag, "flags_post": o_flags,
               "unported": sorted(getattr(ah, "unported", set()) or [])}

    # --- A/B CAUSAL : le MEME etat rejoue avec 1100 RETIRE du registre COMBAT --------------------
    # C'est le controle qui interdit d'attribuer l'accord ci-dessus a autre chose que ce port : sans
    # l'entree de registre, `AbilityHandler` tombe sur son no-op (`ported: False`) et RIEN ne bouge.
    from engine.runner.abilities.handler import ABILITY_CLASSES
    st2 = load_state(snap["dv"], snap["ob"], snap["snap"], board=board)
    if isinstance(snap["rng"], dict) and snap["rng"].get("mt"):
        st2.rng = _seed_rng(snap["rng"])
    saved = ABILITY_CLASSES.pop(FACADE, None)
    try:
        r2 = Runner(st2).install_default_handlers(20)
        r2.apply(ActiveAbilityMessage(caster_id=ids[CASTER_VID], target_id=ids[ALLY_VID],
                                      ability_type=FACADE))

        def opos2(uid):
            e = st2.get_entity(uid)
            pc = e.get_component(PositionComponent) if e is not None else None
            return (pc.col, pc.row) if pc is not None else None

        def ohp2(uid):
            e = st2.get_entity(uid)
            hc = e.get_component(HealthComponent) if e is not None else None
            return hc.hp if hc is not None else None

        noport = {"post": {v: opos2(ids[v]) for v in WATCH},
                  "post_hp": {v: ohp2(ids[v]) for v in WATCH}}
    finally:
        if saved is not None:
            ABILITY_CLASSES[FACADE] = saved

    out = {"runner": rid, "ids": ids, "live": live, "offline": offline, "noport": noport}
    if not keep:
        _rpc("disposeRunner", [{"runnerId": rid}], 20000)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--swap-foes", action="store_true",
                    help="bras discriminant du selecteur : l'AUTRE ennemi est colle au caster")
    ap.add_argument("--far-foes", action="store_true",
                    help="bras `sel` VIDE : les deux ennemis hors de portee d'attaque normale")
    a = ap.parse_args()
    name = ("rs_287_facade_far.json" if a.far_foes else
            "rs_287_facade_swap.json" if a.swap_foes else "rs_287_facade.json")
    r = run(keep=a.keep, swap_foes=a.swap_foes, far_foes=a.far_foes, state_name=name,
            seed=SEED + (2 if a.far_foes else 1 if a.swap_foes else 0))
    print(json.dumps(r, indent=1, default=str)[:8000])
    return 1 if r.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
