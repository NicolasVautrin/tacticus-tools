"""#1025 -- PROBE de mesure (pas un test) : pourquoi le PORT pose-t-il, ou non,
`ElectrochaffBackups_DamageReductionPct` (1446) quand une attaque RANGED touche un ennemi de la MoW
`tauBroadside` portant la mythique ?

Il DECOMPOSE PAR ETAGE, dans l'ordre ou le port les traverse :
  0. la MoW est-elle une entite ECS, et porte-t-elle un `OwnerComponent` ? (elle est HORS-PLATEAU)
  1. `collect_triggered_abilities` l'inscrit-elle ? (canal `UnitContext.tertiary_ability`)
  2. le vecteur `damage_taken_triggers` est-il EMIS par `Runner.Apply(AttackUnitMessage)` ?
  3. le `matches` de la branche B rend-il vrai, et sur quel conjoint echoue-t-il sinon ?
  4. l'`execute_behaviour` pose-t-il, et avec quelle duree ?

Usage : python probe_1025_electrochaff_port.py --state-file <chemin ABSOLU>
(le state-file d'un `rl_duel build --p-mow tauBroadside --equip-mythic tauBroadside`).
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import rl_collect_batch as R                                               # noqa: E402


def _unwrap(res):
    if isinstance(res, dict) and "result" in res and isinstance(res["result"], dict):
        return res["result"]
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    args = ap.parse_args()
    rid = int(json.loads(Path(args.state_file).read_text())["runnerId"])
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        b = {**(body or {}), "runnerId": rid}
        return _unwrap(R._rpc(sid, method, [b], timeout=timeout))

    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state, bind_live_rpc
    from engine.runner.components import OwnerComponent, StatsComponent
    from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
    from engine.runner.operations.triggers.loki.electrochaff_backups import (
        ElectrochaffBackupsOnRangedDamageAbility, ELECTROCHAFF_EFFECT)

    bind_live_rpc(lambda m, b, t=90: _unwrap(R._rpc(sid, m, [b], timeout=t)))
    bg = rpc("boardGraph", {}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"allAbilities": True}, 120)
    ob = rpc("observeBattle", {}, 60)
    snap = rpc("combatSnapshot", {}, 90)
    st = load_state(dv, ob, snap, board=board)
    # Le RNG est OBLIGATOIRE des qu'on rejoue une attaque normale (`normal.py` LEVE sans lui).
    from engine.runner.prng import IntBasedMersenneTwister
    s = rpc("dumpRng", {}, 30)
    if isinstance(s, dict) and s.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s["mt"]); rng.mti = s["mti"]
        st.rng = rng

    mows = [m for m in (dv.get("mows") or []) if m.get("casterId") is not None]
    print("ETAGE 0 -- mows publiees :", [(m.get("casterId"), m.get("visualId")) for m in mows])
    for m in mows:
        ent = st.get_entity(int(m["casterId"]))
        oc = ent.get_component(OwnerComponent) if ent is not None else None
        sc = ent.get_component(StatsComponent) if ent is not None else None
        print(f"  mow {m.get('casterId')} entite={ent is not None} owner={oc.team if oc else None} "
              f"tertiary={getattr(getattr(sc, 'ctx', None), 'tertiary_ability', None)}")

    inscrits = [a for a in collect_triggered_abilities(st)
                if isinstance(a, ElectrochaffBackupsOnRangedDamageAbility)]
    print("ETAGE 1 -- inscrits branche B :", [a.owner_id for a in inscrits])

    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    tireur = next((u for u in units if u.get("team") == 1), None)
    # La victime doit etre ATTEIGNABLE : sinon `AttackUnitMessage` ne produit aucun degat, donc
    # aucun `On(0x0f)`, et l'etage 4 mesurerait une portee, pas un trigger.
    import hexgeo as _hg
    def _cr(u):
        p = u.get("pos") or {}
        return (p.get("col"), p.get("row"))
    ennemis = [u for u in units if u.get("team") == 2 and (u.get("pos") or {}).get("col") is not None]
    victime = (min(ennemis, key=lambda u: _hg.distance(_cr(tireur), _cr(u)))
               if (tireur and ennemis) else None)
    print(f"ETAGE 2 -- tireur={tireur and tireur['id']} victime={victime and victime['id']}")
    if tireur is None or victime is None or not inscrits:
        return 1

    from engine.runner.operations.triggers.base import TriggerEvent, _is_ranged_attack
    from engine.dsl.event_trigger_type import EventTriggerType
    ab = inscrits[0]
    ev = TriggerEvent(int(EventTriggerType.DamageTaken), tireur["id"], victime["id"],
                      ranged=False, profile=None)
    print("ETAGE 3 -- _common =", ab._common(st, ev),
          "| _is_ranged_attack =", _is_ranged_attack(st, None, tireur["id"], victime["id"]),
          "| matches =", ab.matches(st, ev))

    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.components import HealthComponent
    from engine.runner.operations.triggers.dispatch import attack as attack_dispatch
    vus = []
    vrai = attack_dispatch.damage_taken_triggers

    def _espion(state, source_id, target_id, profile=None):
        vus.append((source_id, target_id, profile))
        return vrai(state, source_id, target_id, profile=profile)

    attack_dispatch.damage_taken_triggers = _espion     # FORME MODULE : l'appelant relit l'attribut
    try:
        hc = st.get_entity(int(victime["id"])).get_component(HealthComponent)
        hp0 = hc.hp if hc else None
        Runner(st).install_default_handlers(20).apply(AttackUnitMessage(tireur["id"], victime["id"]))
        hp1 = hc.hp if hc else None
    finally:
        attack_dispatch.damage_taken_triggers = vrai
    inst = [e for e in st.effects.by_unit.get(int(victime["id"]), [])
            if e.effect_type == ELECTROCHAFF_EFFECT and not e.consumed]
    print(f"ETAGE 4 -- hp {hp0} -> {hp1} | On(0x0f) emis {len(vus)} fois {vus[:3]}")
    print("ETAGE 4 -- pose apres AttackUnitMessage :", len(inst),
          "| turns =", [e.remaining_turns for e in inst])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
