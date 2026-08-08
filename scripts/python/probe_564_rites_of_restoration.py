"""probe #564 -- `1039 RitesOfRestoration` (`adeptHospitaller` « Isabella ») : les DEUX faces, live.

CE QUE CE PROBE MESURE, et pourquoi ce n'est pas « le port ne crashe pas »

L'ability est un `op_BitwiseAnd(Heal, Resurrect)`. Les deux volets ont des observables DISJOINTS, et
le probe les separe :

  [A] GATE DE CASTER -- `RitesOfRestorationAbility$$GetDynamicInvalidCasterReason`, atteint par le bit
      `AddCasterIfMatchesDynamicRule` (0x8) du masque via `TargetingQuery$$GetCasterNotAddedReason`.
      Le natif rend « pas de cible » tant qu'il n'y a NI allie soignable NI (mort resurrectable ET
      hex libre). Observable natif : `abilityTargets(unitId=caster, abilityType=1039).fromHere`.
      DEUX REGIMES sur le MEME runner, a deux instants :
        t0 -- tour 1, personne n'est blesse, personne n'est mort  -> le natif rend 0 cible ;
        t1 -- apres un tour adverse qui TUE un allie Imperial      -> le natif rend le caster.
      Si les deux regimes ne different pas, le montage ne mesure rien et le probe le DIT au lieu de
      lire l'accord comme une preuve.

  [B] EXECUTION -- le cast lui-meme, a t1. Observables d'ETAT (`observeBattle` avant/apres) :
        * l'allie MORT redevient VIVANT, a `hp` PV (variable 0x1d, per-level x multiplier) ;
        * il reapparait sur un hex ADJACENT au caster (le zip `targets x tiles` du behaviour) ;
        * il ne peut PAS agir ce tour (`takesImmediateTurn = false` ->
          `MarkUnitAsNoActionAvailable`).
      Le PORT est joue sur un `State` mirroir de l'etat d'AVANT le cast, et son resultat est
      confronte etage par etage a ce que le natif a fait.

Usage :
    python probe_564_rites_of_restoration.py [--state-file <chemin ABSOLU>]
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import probe_27_3_live as L

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"

RITES = 1039
BOARD = "MC1_67"
SEED = 777

CASTER_VID = "adeptHospitaller"   # Isabella -- porteur de 1039, lineup, DANS le pool rank 17
ALLY_VID = "ultraCalgar"          # Marneus Calgar -- Hero, Imperial, NON mecanique : la cible du resurrect

# PV joueur bas + frappe adverse haute -> mort DETERMINISTE de l'appat au 1er tour adverse. Aucun
# scalaire du port n'est fitte : on choisit OU l'on mesure, pas ce que l'on mesure.
HP_PLAYER = 300
HP_TARGET = 22000
DMG_TARGET = 6000

ALLY_BAIT = "4,6"                 # au contact -> l'IA adverse le tue


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _rid(state: Path) -> int:
    return int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])


def _units(rid: int) -> dict:
    """{visualId: (id, (col,row), alive)} depuis `decisionView` -- aucun id hardcode."""
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = (u.get("id"), (p.get("col"), p.get("row")), bool(u.get("alive")))
    return out


def _from_here(rid: int, caster: int) -> list:
    """`abilityTargets(...).fromHere` pour 1039 = les cibles legales SANS bouger. C'est l'observable
    natif du gate de caster : quand `GetDynamicInvalidCasterReason` refuse, le caster n'est pas
    AJOUTE et l'ensemble est vide."""
    r = L._rpc("abilityTargets", [{"runnerId": rid, "unitId": caster,
                                   "abilityType": RITES, "allAbilities": True}])
    out = []
    for u in (r.get("units") or []):
        if int(u.get("unitId", -1)) != int(caster):
            continue
        for a in (u.get("abilities") or []):
            if int(a.get("abilityId", -1)) != RITES:
                continue
            out += [int(t.get("targetId")) for t in (a.get("fromHere") or [])
                    if t.get("targetId") is not None]
    return sorted(set(out))


def _capture(rid: int):
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
    ob = L._rpc("observeBattle", [{"runnerId": rid}])
    sn = L._rpc("combatSnapshot", [{"runnerId": rid}])
    return dv, ob, sn


def mirror(rid: int):
    """`State` mirroir de l'etat live -- AVEC le board.

    ⚠ Le `board` n'est PAS optionnel ici, et l'oublier ne leve RIEN : `AdjacentTiles` rend `[]`, donc
    `CanAddUnit(AdjacentTiles(CasterTile()))` rend `[]`, donc `GetDynamicInvalidCasterReason` refuse
    TOUJOURS -- un port faux qui aurait l'air d'accorder avec un natif qui, lui, refuse pour une
    AUTRE raison. Mesure du 2026-08-08 : c'est exactement l'etat dans lequel la premiere passe de ce
    probe se trouvait (`tileCount = 0` cote port, artefact du mirroir)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    dv, ob, sn = _capture(rid)
    bg = L._rpc("boardGraph", [{"runnerId": rid}])
    board = Board(bg["tiles"], adjacency="native_sym") if (bg or {}).get("tiles") else None
    if board is None:
        raise SystemExit("[564] boardGraph indispo -- NON MESURE (le mirroir sans board refuse tout)")
    return load_state(dv, ob, sn, board=board), dv, ob, sn


def _hp(rid: int) -> dict:
    """{squadId: (hp, hpMax, isDead)} -- `observeBattle.units[]` porte `squadId` (l'id que rend
    `decisionView`) ET `entityId` (celui du feet-holder) : les confondre rend `None` partout."""
    ob = L._rpc("observeBattle", [{"runnerId": rid}])
    out = {}
    for x in (ob.get("units") or []):
        i = x.get("squadId", x.get("entityId"))
        if i is None:
            continue
        out[int(i)] = (x.get("hp"), x.get("hpMax"), bool(x.get("isDead")))
    return out


def build(state: Path) -> int:
    _run(["build", "--seed", str(SEED), "--board", BOARD, "--rank", "17",
          "--p-units", "%s,%s" % (CASTER_VID, ALLY_VID),
          "--a-units", "tauCrisis,orksWarboss",
          "--hp-target", str(HP_TARGET), "--hp-player", str(HP_PLAYER),
          "--dmg-target", str(DMG_TARGET), "--state-file", str(state)])
    return _rid(state)


def mesure(state: Path) -> dict:
    """Monte le runner, joue les deux regimes, CASTE, et rend TOUT ce qui a ete releve.

    Le runner N'EST PAS dispose ici : c'est l'appelant qui en est proprietaire (fixture pytest ou
    `main`), pour que la mesure reste re-lisible en cas d'echec."""
    from engine.runner.abilities.targeting import get_caster_not_added_reason
    from engine.runner.abilities.sisterhood import RitesOfRestorationAbility
    from engine.runner.abilities import sisterhood as S
    from engine.runner.abilities.behaviours.context import entities_from_state

    rid = build(state)
    u = _units(rid)
    if CASTER_VID not in u or ALLY_VID not in u:
        raise SystemExit("[564] montage invalide : %s/%s absents du build" % (CASTER_VID, ALLY_VID))
    caster, ally = u[CASTER_VID][0], u[ALLY_VID][0]
    ab = RitesOfRestorationAbility()

    # --- [A] REGIME t0 : personne de blesse, personne de mort -----------------------------------
    st0, _d, _o, _s = mirror(rid)
    out = {"rid": rid, "caster": caster, "ally": ally,
           "t0_native": _from_here(rid, caster),
           "t0_port_reason": int(get_caster_not_added_reason(st0, caster, ab))}

    # --- montage : l'appat va au contact, on rend la main, l'IA adverse le tue -------------------
    _run(["act", "move", "--unit", str(ally), "--to", ALLY_BAIT,
          "--state-file", str(state), "--runner", str(rid)])
    _run(["act", "endturn", "--state-file", str(state), "--runner", str(rid)])
    _run(["aiturn", "--state-file", str(state), "--runner", str(rid)])
    u = _units(rid)
    out["ally_alive_after_ai_turn"] = u[ALLY_VID][2]
    if u[ALLY_VID][2]:
        return out                                   # montage rate -- l'appelant le DIT, pas de mesure

    # --- [A] REGIME t1 + [B] le port sur le mirroir d'AVANT le cast ------------------------------
    st, _d, _o, _s = mirror(rid)
    ent = entities_from_state(st, caster, caster)
    out["t1_native"] = _from_here(rid, caster)
    out["t1_port_reason"] = int(get_caster_not_added_reason(st, caster, ab))
    out["stages"] = {
        "heal": [x.get("id") for x in (S.rites_of_restoration_heal_targets().evaluate(ent) or [])],
        "resurrect": [x.get("id") for x in
                      (S.rites_of_restoration_possible_resurrect_targets().evaluate(ent) or [])],
        "heroes": [x.get("id") for x in
                   (S.rites_of_restoration_hero_targets().evaluate(ent) or [])],
        "summons": [x.get("id") for x in
                    (S.rites_of_restoration_summon_targets().evaluate(ent) or [])],
        "tiles": list(S.rites_of_restoration_resurrect_tiles().evaluate(ent) or []),
    }
    out["hp_before"] = _hp(rid)
    out["port"] = ab.execute_behaviour(st, caster, caster)

    # --- [B] le NATIF : le meme cast, en vrai ----------------------------------------------------
    _run(["act", "ability", "--caster", str(caster), "--ability", str(RITES),
          "--target", str(caster), "--state-file", str(state), "--runner", str(rid)])
    au = _units(rid)
    out["native_after"] = {"alive": au[ALLY_VID][2], "pos": au[ALLY_VID][1]}
    out["hp_after"] = _hp(rid)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", default=str(LOGS / "rs_564_rites.json"))
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    state = Path(args.state_file)
    state.parent.mkdir(parents=True, exist_ok=True)
    m = mesure(state)
    print("[564] runner=%s caster=%s appat=%s" % (m["rid"], m["caster"], m["ally"]))
    print("[564][A/t0] natif=%s port_reason=%s" % (m["t0_native"], m["t0_port_reason"]))
    if m.get("ally_alive_after_ai_turn"):
        print("[564] MONTAGE INVALIDE : l'appat est encore VIVANT -- aucune mesure du resurrect")
        return 2
    print("[564][A/t1] natif=%s port_reason=%s" % (m["t1_native"], m["t1_port_reason"]))
    print("[564][A/t1] etages port = %s" % json.dumps(m["stages"]))
    print("[564][B] port = %s" % json.dumps(m["port"]["resurrections"]))
    print("[564][B] natif apres cast = %s ; hp=%s"
          % (m["native_after"], m["hp_after"].get(m["ally"])))
    if not args.keep:
        try:
            L._rpc("disposeRunner", [{"runnerId": m["rid"]}])
        except Exception:                                    # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
