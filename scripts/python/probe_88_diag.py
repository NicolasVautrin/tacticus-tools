"""Diagnostic PAR ETAGE du volet revive `FuelledByFury` (#88 A1) -- decompose la chaine offline pour
localiser le PREMIER etage ou le port diverge du live (doctrine : jamais fitter un scalaire).

Etages mesures, dans l'ordre de la chaine native :
  1. le marqueur `FuelledByFury_CanRevive` (1324) est-il dans `state.effects` du porteur, et ACTIF ?
  2. `FinalJusticeAbility` matche-t-elle sur `On(1)` et sa riposte TUE-t-elle ?
  3. `On(3 = PendingDeathAdded)` est-il emis, avec `triggering_ability = 1024` et `killer = Titus` ?
  4. `FuelledByFuryReviveAbility.matches` -- lequel de ses 4 noeuds refuse ?
  5. la `ReviveData` est-elle posee, et la garde `kill_unit_revive_gate` annule-t-elle la mort ?

Usage : python probe_88_diag.py   (ASCII only)
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session  # noqa: E402
import probe_88_fuelled_by_fury_revive as P    # noqa: E402


def main() -> int:
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import UnitComponent, HealthComponent
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.runner.operations.triggers.dispatch.core import (
        collect_effect_triggers, collect_triggered_abilities, evaluate_trigger_operation
    )
    from engine.runner.operations.triggers.loki.fuelled_by_fury import (
        FUELLED_BY_FURY_CAN_REVIVE, _can_revive_is_armed, FuelledByFuryReviveAbility)
    from engine.dsl.event_trigger_type import EventTriggerType

    sid = _resolve_session()
    dmg_on_hero, dmg_by_hero = P.calibrate(sid)
    print("calibrage: killer->Titus=%s  Titus->ennemi=%s" % (dmg_on_hero, dmg_by_hero))
    hp_player = int(dmg_on_hero * 0.85)
    hp_kill = max(1, int(dmg_by_hero * 0.50))
    rid, dv, uu = P.setup(sid, hp_player, hp_kill)
    try:
        snap = P.rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
        ob = P.rpc(sid, "observeBattle", {"runnerId": rid}, 60)
        bg = P.rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq") if (bg or {}).get("tiles") else None
        st = load_state(dv, ob, snap, board=board)
        st.rng = IntBasedMersenneTwister(12345)
        hid, kid = uu[P.HERO]["id"], uu[P.FOE_KILLER]["id"]

        # --- etage 1 : le marqueur 1324
        effs = (st.effects.by_unit.get(int(hid)) or []) if st.effects is not None else []
        print("1) effets de Titus offline : %s"
              % [(e.effect_type, getattr(e, "name", None), e.active, e.consumed) for e in effs])
        print("   marqueur 1324 present=%s arme=%s"
              % (any(e.effect_type == FUELLED_BY_FURY_CAN_REVIVE for e in effs),
                 _can_revive_is_armed(st, hid)))
        trig = [type(t).__name__ for t in collect_effect_triggers(st)]
        ab = [type(t).__name__ for t in collect_triggered_abilities(st)]
        print("   effect-triggers collectes : %s" % [t for t in trig if "FuelledByFury" in t])
        print("   ability-triggers collectes: %s" % [t for t in ab if
                                                     ("FuelledByFury" in t or "FinalJustice" in t)])

        # --- etage 2 : FinalJustice
        e = st.get_entity(hid)
        hc = e.get_component(HealthComponent)
        uc = e.get_component(UnitComponent)
        hp_before = int(hc.hp)
        foes = {}
        for vis in (P.FOE_KILLER, P.FOE_VICTIM):
            fe = st.get_entity(uu[vis]["id"])
            foes[vis] = (int(fe.get_component(HealthComponent).hp),
                         bool(fe.get_component(UnitComponent).alive))
        print("2) PV: Titus=%s  ennemis=%s" % (hp_before, foes))

        # --- etages 2->5 : le VRAI chokepoint
        hc.hp = 0
        out = AttackDamageOperation._fire_death_if_killed(st, hid, kid, hp_before, 0, e,
                                                          damage=hp_before)
        print("3) sorties du pipeline de mort :")
        for r in (out or []):
            print("     %s" % str(r)[:300])
        foes_after = {}
        for vis in (P.FOE_KILLER, P.FOE_VICTIM):
            fe = st.get_entity(uu[vis]["id"])
            foes_after[vis] = (int(fe.get_component(HealthComponent).hp),
                               bool(fe.get_component(UnitComponent).alive))
        print("   ennemis apres riposte : %s" % foes_after)
        print("4) Titus alive=%s hp=%s pending_revive=%s"
              % (uc.alive, hc.hp, uc.pending_revive))

        # --- etage 3 bis : re-emission MANUELLE d'On(3) avec le contexte attendu
        st2 = load_state(dv, ob, snap, board=board)
        st2.rng = IntBasedMersenneTwister(12345)
        st2.get_entity(hid).get_component(HealthComponent).hp = 0
        st2.get_entity(hid).get_component(UnitComponent).alive = False
        victim = uu[P.FOE_VICTIM]["id"]
        st2.get_entity(victim).get_component(HealthComponent).hp = 0
        st2.get_entity(victim).get_component(UnitComponent).alive = False
        st2.triggering_ability = 1024
        ability = FuelledByFuryReviveAbility(hid)
        ev = TriggerEvent(EventTriggerType.PendingDeathAdded, hid, victim, ranged=False,
                          profile=None, killer_id=hid, dying_id=victim, triggering_ability=1024)
        print("5) matches() force = %s" % ability.matches(st2, ev))
        res = evaluate_trigger_operation(st2, ev)
        print("   dispatch On(3) force -> %s" % [str(r)[:200] for r in res])
        return 0
    finally:
        P.rpc(sid, "disposeRunner", {"runnerId": rid}, 60)


if __name__ == "__main__":
    sys.exit(main())
