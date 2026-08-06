#!/usr/bin/env python
"""probe #462-r4b -- POURQUOI le port rend `Pinned` INACTIF sur une cible SANS `TerminatorArmour`.

Le test `tests/engine/runner/test_chain_after_refused_addeffect_live.py::
test_chain_survives_placed_addeffect` mesure des deux cotes et rougit sur le seul axe PORT :

    [blackPossession] live={'pinned': True, ...} port={'pinned': False, 'placed': True, ...}

soit : l'effet EST pose (`placed`) mais `EffectsState.active_effects` ne le rend pas. Ce probe
DECOMPOSE PAR ETAGE la cause, sur UN SEUL runner :

  etage A -- `AddEffect(Pinned)` SEUL (aucune chaine) : l'instance nait-elle active ?
  etage B -- l'arbre COMPLET d'`ExemplarOfHate`, `state.rng = None` (attaque libre = no-op)
  etage C -- l'arbre COMPLET avec le RNG DU RUNNER : l'attaque libre est RESOLUE (montage du test)
  etage D -- `--trace` : instance `Pinned` TRACANTE, pile d'appel de l'ecriture de `consumed`

Pour chaque etage on imprime, instance par instance : `consumed`, `expired`, `remaining_turns`,
le flag `active` (= `EffectComponent.IsActive @+0x5c`) et `is_active(unit_state)`
(= `<Effect>$$CreateActiveCondition`), plus les traits vus par le port. C'est la decomposition qui
distingue « la pose nait inerte » de « un etage ulterieur l'eteint ».

VERDICT MESURE (2026-08-03, build `rnca9r7q6c`) : etages A et B -> `Pinned` **ACTIF** sur
`blackPossession` ; etage C -> `consumed=True`, et l'etage D nomme le coupable --
`AttackDamageOperation` -> `_fire_death_if_killed` -> `_verify_deaths` -> `_kill_unit_operation`
-> `_kill_unit_remove_effects(PreUnitRemove)`. **L'attaque libre TUE la cible, des DEUX cotes** :

    PORT hp 8034 -> 0   alive=False
    LIVE hp 8034 -> 0   isDead=True     decisionView.effects POST-cast = []

Le natif fait de meme (`IdunBattle.Operations.KillUnitOperation$$RemoveEffects` ->
`IdunBattle.Operations.RemoveEffectsOperation$$Execute`). Il n'y a donc AUCUN gate fautif : le test
lisait un EVENEMENT (groupe emis a la pose) cote live et un ETAT FINAL cote port. Cf.
`docs/rl/case-462-r4b-pose-vs-etat-final.md`.

⚠ Le bras `immune` (`blackAbaddon`) expose un AUTRE ecart, celui-la REEL et non couvert :
PORT 10038 -> 2308 contre LIVE 10038 -> 7442 (le natif publie 2x `TerminatorArmour_ReduceDmg`).
Residu `#462-r4b-r1` au backlog -- ce probe est le canal qui le rend visible.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_462r4b_pinned_active_after_chain.py [control|immune|both] [--trace]

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import sys

import probe_112_darkangels as PR
import probe_n5_chain_after_refused_addeffect as N5
import rl_collect_batch as R
from engine.dsl.effects import ExecutionContext
from engine.entities.pathfinding.board import Board
from engine.entities.selectors.accessors import Target
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.runner.abilities.behaviours.effects import AddEffect
from engine.runner.abilities.darkangels import ExemplarOfHateAbility
from engine.runner.components import StatsComponent, unit_state_for_effects
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.snapshot import load_state

EXEMPLAR = 1140
PINNED = 1065


def _snapshot(sid, rid):
    bg = PR.rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = PR.rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    cs = PR.rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    return board, dv, ob, cs


def _hp(state, uid):
    from engine.runner.components import HealthComponent
    e = state.get_entity(int(uid))
    hc = e.get_component(HealthComponent) if e is not None else None
    return None if hc is None else hc.hp


def _alive(state, uid):
    from engine.runner.components import UnitComponent
    e = state.get_entity(int(uid))
    uc = e.get_component(UnitComponent) if e is not None else None
    return None if uc is None else uc.alive


def _dump(state, uid, label):
    us = unit_state_for_effects(state, uid)
    ent = state.get_entity(uid)
    sc = ent.get_component(StatsComponent) if ent is not None else None
    print("  %s traits=%s" % (label, sorted((sc.ctx.traits if sc is not None else []) or [])))
    for e in (state.effects.by_unit.get(int(uid), []) if state.effects else []):
        if int(e.effect_type or 0) != PINNED:
            continue
        print("    %-12s cls=%-16s consumed=%s expired=%s rem=%s active=%s is_active=%s"
              % (e.name, type(e).__name__, e.consumed, e.expired, e.remaining_turns,
                 e.active, e.is_active(us)))
    act = {x.effect_type for x in state.effects.active_effects(uid, us)} if state.effects else set()
    print("    -> PINNED in active_effects: %s" % (PINNED in act))


def run(sid, victim_visual, layout):
    rid = N5._build(sid, N5.P_UNITS, N5.A_UNITS, anchor=layout[victim_visual],
                    occupied=layout.values())
    try:
        board, dv, ob, cs = _snapshot(sid, rid)
        bv = PR.units_by_visual(dv)
        caster, tgt = bv["darkaAsmodai"]["id"], bv[victim_visual]["id"]

        print("[%s] u%s (caster u%s)" % (victim_visual, tgt, caster))

        # --- etage A : AddEffect(Pinned) SEUL
        st = load_state(dv, ob, cs, board=board)
        ectx = ExecutionContext(state=st, rng=None)
        AddEffect(PINNED, "Pinned", Target()).execute(
            entities_from_state(st, caster, tgt), ectx)
        print("  ETAGE A -- AddEffect(Pinned) seul")
        _dump(st, tgt, "cible")

        # --- etage B : arbre COMPLET d'ExemplarOfHate, SANS rng (attaque libre = no-op)
        st2 = load_state(dv, ob, cs, board=board)
        ExemplarOfHateAbility().execute_behaviour(st2, caster, tgt)
        print("  ETAGE B -- arbre complet ExemplarOfHate (rng=None)")
        _dump(st2, tgt, "cible")

        # --- etage C : arbre COMPLET avec le RNG DU RUNNER (l'attaque libre est RESOLUE) --
        # c'est le montage EXACT du test (`_seeded_state`), donc le seul qui puisse reproduire.
        rng = PR.rpc(sid, "dumpRng", {"runnerId": rid}, 30)
        st3 = load_state(dv, ob, cs, board=board)
        r = IntBasedMersenneTwister()
        r.mt = list(rng["mt"])
        r.mti = rng["mti"]
        st3.rng = r
        php0 = _hp(st3, tgt)
        ExemplarOfHateAbility().execute_behaviour(st3, caster, tgt)
        php1 = _hp(st3, tgt)
        print("  ETAGE C -- arbre complet ExemplarOfHate (rng du runner)")
        print("    PORT hp %s -> %s   alive=%s" % (php0, php1, _alive(st3, tgt)))
        _dump(st3, tgt, "cible")

        # --- confrontation LIVE sur le MEME etat (le cast natif, apres les mesures port)
        hp0 = PR.hp_of(sid, rid)
        res = PR.cast(sid, rid, caster, tgt, EXEMPLAR)
        hp1 = PR.hp_of(sid, rid)
        srcs = [e.get("source") for e in (res.get("events") or []) if e.get("kind") == "group"]
        ob2 = PR.rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        dead = [u for u in (ob2.get("units") or [])
                if u.get("isDead") and int(u.get("unitId") or u.get("entityId") or -1) == int(tgt)]
        dv2 = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 60)
        print("    LIVE hp %s -> %s   isDead=%s" % (hp0.get(tgt), hp1.get(tgt), bool(dead)))
        print("    LIVE groupes  :", srcs)
        print("    LIVE effets cible POST :", PR.eff_names(dv2, tgt))

        # --- etage D : MEME montage, instance `Pinned` TRACANTE -> qui ecrit `consumed` ?
        if "--trace" in sys.argv:
            import traceback

            from engine.entities.effects.factory import EffectFactory
            from engine.entities.effects.loki.status import PinnedEffect

            class _TracingPinned(PinnedEffect):
                def __setattr__(self, k, v):
                    if k == "consumed" and v:
                        print("    !! consumed=True pose ici :")
                        traceback.print_stack(limit=18)
                    object.__setattr__(self, k, v)

            prev = EffectFactory.registry.get("Pinned")
            EffectFactory.registry["Pinned"] = _TracingPinned
            try:
                rng2 = PR.rpc(sid, "dumpRng", {"runnerId": rid}, 30)
                st4 = load_state(dv, ob, cs, board=board)
                r2 = IntBasedMersenneTwister()
                r2.mt = list(rng2["mt"])
                r2.mti = rng2["mti"]
                st4.rng = r2
                print("  ETAGE D -- trace des ecritures de `consumed` sur Pinned")
                ExemplarOfHateAbility().execute_behaviour(st4, caster, tgt)
                _dump(st4, tgt, "cible")
            finally:
                if prev is not None:
                    EffectFactory.registry["Pinned"] = prev
    finally:
        PR.dispose(sid, rid)


def main():
    sid = R._resolve_session()
    only = sys.argv[1] if len(sys.argv) > 1 else "control"
    try:
        layout = N5.enemy_layout(sid)
        if only in ("control", "both"):
            run(sid, N5.CONTROL_VICTIM, layout)
        if only in ("immune", "both"):
            run(sid, N5.IMMUNE_VICTIM, layout)
    finally:
        for rid in list(PR._rids):
            PR.dispose(sid, rid)


if __name__ == "__main__":
    main()
