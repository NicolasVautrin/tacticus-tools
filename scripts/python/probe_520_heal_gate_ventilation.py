"""#520 -- VENTILATION du gate `IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed`.

MESURE, pas garde. Repond a la seule question qui compte apres avoir arme un gate dans une Operation
de mutation : **QUI ce gate refuse-t-il, et pourquoi ?** Un gate qui refuserait tout le monde rendrait
la categorie HEAL entierement INERTE -- c'est le risque exact de la tranche, et le seul moyen de
l'ecarter est de nommer les refuses et de lire le disjunct qui les refuse.

Le gate (mirror `abilities/attack_query.py::entity_can_be_healed`) :

    !IsMachine(target)
 && (IsDamagedUnit(target) || (removeEffects && HasNegativeUnitEffect(target))
                           || (caster != null && HasFlag(caster, 0x17 CanHealFullHealthUnits)))
 && !HasHealBlockers(target)
 && (scope == 0 || !IsAtGroupUnitHealLimit(target))
 && !HasTrait(target, 0xd Object)
 && IsAffectedByHealType(target, 0 NonMechanical)

Chaque unite est BLESSEE artificiellement (hp = hp_max - 1) avant l'interrogation : sans PV
manquants, `IsDamagedUnit` est faux pour TOUT LE MONDE et la ventilation serait degeneree -- un
accord en regime degenere ne prouve rien.

    python probe_520_heal_gate_ventilation.py [--seed 777] [--board MC1_67]
                                              [--p-units a,b] [--a-units c,d]
                                              [--state-file <abs>]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests
from sibling_script import sibling_script

from engine.runner.snapshot import load_state
from engine.runner.components import HealthComponent
from engine.runner.abilities.attack_query import (entity_can_be_healed, is_damaged_unit,
                                                  is_affected_by_heal_type, _has_trait,
                                                  HEAL_TYPE_NON_MECHANICAL)
from engine.runner.abilities.targeting import _is_machine, _unit_traits
from engine.entities.traits.unit_trait import UnitTrait


def _raison(state, uid) -> str:
    """Le PREMIER disjunct du gate qui refuse -- lu dans l'ORDRE du decompile.

    Rendre « refuse » sans dire LEQUEL laisserait le lecteur devant un verdict inverifiable ; et
    l'ordre compte, parce que plusieurs disjuncts peuvent etre faux ensemble."""
    if _is_machine(state, uid):
        return "IsMachine (MACHINE OF WAR)"
    if not is_damaged_unit(state, uid):
        return "!IsDamagedUnit (PV pleins, et aucun autre disjunct lisible)"
    if _has_trait(state, uid, int(UnitTrait.Object)):
        return "HasTrait(Object)"
    if not is_affected_by_heal_type(state, uid, HEAL_TYPE_NON_MECHANICAL):
        return "!IsAffectedByHealType(0) -- MECANIQUE sans AffectedByHealAndRepair"
    return "(accepte)"


def mesurer(state) -> dict:
    acceptees, refusees = [], []
    for uid, e in state.entities.items():
        hc = e.get_component(HealthComponent)
        if hc is None or hc.hp is None or hc.hp_max is None:
            continue
        garde = int(hc.hp)
        hc.hp = int(hc.hp_max) - 1                    # BLESSER : sinon regime degenere
        ok = entity_can_be_healed(state, uid, uid, scope=0, remove_effects=True)
        ligne = {"entity": int(uid),
                 "traits": sorted(_unit_traits(state, uid) or ()),
                 "raison": "(accepte)" if ok else _raison(state, uid)}
        hc.hp = garde
        (acceptees if ok else refusees).append(ligne)
    return {"acceptees": acceptees, "refusees": refusees,
            "n_acceptees": len(acceptees), "n_refusees": len(refusees)}


HOST = "http://127.0.0.1:8765"


def sid() -> int:
    return int(requests.get(HOST + "/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 90):
    r = requests.post("%s/api/scripts/%d/rpc" % (HOST, s),
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--p-units", default=None)
    ap.add_argument("--a-units", default=None)
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    argv = [sys.executable, sibling_script("rl_duel.py"), "build", "--seed", a.seed,
            "--board", a.board, "--state-file", a.state_file]
    for flag, val in (("--p-units", a.p_units), ("--a-units", a.a_units)):
        if val:
            argv += [flag, val]
    out = subprocess.run(argv, capture_output=True, text=True)
    if out.returncode != 0:
        print("BUILD FAILED rc=%d" % out.returncode)
        print((out.stdout or "")[-1200:])
        print((out.stderr or "")[-1200:])
        return 1
    rid = json.loads(Path(a.state_file).read_text(encoding="utf-8"))["runnerId"]
    s = sid()
    try:
        dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 90)
        ob = rpc(s, "observeBattle", {"runnerId": rid}, 40)
        snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 40)
        state = load_state(dv, ob, snap)
        out = mesurer(state)
    finally:
        if not a.keep:
            subprocess.run([sys.executable, sibling_script("rl_duel.py"), "dispose",
                            "--state-file", a.state_file], capture_output=True, text=True)

    print("GATE EntityCanBeHealed -- seed=%s board=%s" % (a.seed, a.board))
    print("  acceptees = %d" % out["n_acceptees"])
    print("  refusees  = %d" % out["n_refusees"])
    for l in out["refusees"]:
        print("    REFUS entity=%-5d %s | traits=%s"
              % (l["entity"], l["raison"], ",".join(l["traits"]) or "-"))
    if out["n_acceptees"] == 0:
        print("  !! AUCUNE unite acceptee : le gate rendrait la categorie HEAL inerte")
        return 1
    if out["n_refusees"] == 0:
        print("  (aucun refus sur ce montage -- temoin negatif absent, pas une preuve)")
    print(json.dumps({"n_acceptees": out["n_acceptees"], "n_refusees": out["n_refusees"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
