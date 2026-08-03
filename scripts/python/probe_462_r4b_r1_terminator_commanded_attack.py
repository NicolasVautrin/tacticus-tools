#!/usr/bin/env python
"""probe #462-r4b-r1 -- la reduction `TerminatorArmour` sur l'attaque COMMANDEE par `UseActiveAbility`.

RESIDU laisse par #462-r4b (`docs/rl/case-462-r4b-pose-vs-etat-final.md` §7), qu'AUCUN test
n'assertionnait :

    blackAbaddon (trait TerminatorArmour)   PORT 10038 -> 2308   (7730 infliges)
                                            LIVE 10038 -> 7442   (2596 infliges)   facteur 2,98

Ce probe DECOMPOSE PAR ETAGE l'attaque libre de la chaine `ExemplarOfHate` (feuille
`UseActiveAbility` -> `AttackDamageOperation.execute`), sur le MEME etat que le cast natif :

  etage 1 -- l'effet 1147 `TerminatorArmour_ReduceDmg` est-il DANS l'etat charge, et ACTIF ?
  etage 2 -- que rend `defender_modifiers` PENDANT l'attaque libre (%-list, multiplicateur,
             additifs, `is_melee`, `damage_profile`) ? On instrumente le foyer, on ne devine pas.
  etage 3 -- le ledger PAR COUP des deux cotes (`per_hit` du port / tag `Amount` des events natifs)
             + le total et le delta de PV.

Le bras `control` (`blackPossession`, SANS le trait) est le temoin : #462-r4b a mesure que les deux
cotes y infligent le meme degat, donc l'ecart est porte par le TRAIT et non par le montage.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_462_r4b_r1_terminator_commanded_attack.py [immune|control|both]

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import json
import sys

import probe_112_darkangels as PR
import probe_n5_chain_after_refused_addeffect as N5
import rl_collect_batch as R

EXEMPLAR = 1140
TERMINATOR_REDUCE = 1147
TERMINATOR_VISUAL = 1375


def _snapshot(sid, rid):
    from engine.entities.pathfinding.board import Board
    bg = PR.rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = PR.rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    cs = PR.rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    return board, dv, ob, cs


def _seeded_state(sid, rid, board, dv, ob, cs):
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state
    rng = PR.rpc(sid, "dumpRng", {"runnerId": rid}, 30)
    st = load_state(dv, ob, cs, board=board)
    r = IntBasedMersenneTwister()
    r.mt = list(rng["mt"])
    r.mti = rng["mti"]
    st.rng = r
    return st


def _hp(state, uid):
    from engine.runner.components import HealthComponent
    e = state.get_entity(int(uid))
    hc = e.get_component(HealthComponent) if e is not None else None
    return None if hc is None else hc.hp


def dump_effects(state, uid, label):
    """ETAGE 1 -- toutes les instances d'effet portees par `uid`, avec leurs deux conjoints
    d'activite (`EffectComponent.IsActive @+0x5c` et `<Effect>$$CreateActiveCondition`)."""
    from engine.runner.components import StatsComponent, unit_state_for_effects
    us = unit_state_for_effects(state, int(uid))
    ent = state.get_entity(int(uid))
    sc = ent.get_component(StatsComponent) if ent is not None else None
    print("  [1] %s traits=%s" % (label, sorted((sc.ctx.traits if sc is not None else []) or [])))
    for e in (state.effects.by_unit.get(int(uid), []) if state.effects else []):
        print("      eff %-6s %-34s cls=%-34s consumed=%s active=%s is_active=%s"
              % (e.effect_type, e.name, type(e).__name__, e.consumed, e.active, e.is_active(us)))
    act = {x.effect_type for x in state.effects.active_effects(int(uid), us)} if state.effects else set()
    print("      -> 1147 dans active_effects: %s   (1375: %s)"
          % (TERMINATOR_REDUCE in act, TERMINATOR_VISUAL in act))
    return act


def _mods_repr(m):
    """Vue ASCII des DEUX canaux de `DamageModifiers` (#462-r4a) : la LISTE `@0x18` et le
    `Multiplier@0x30`, plus les additifs/soustractions plates."""
    if m is None:
        return "None"
    out = {}
    for k in ("pct_list", "pct_list_defender", "multiplicative", "multiplicative_defender",
              "additive", "flat_reductions", "extra_pierce", "override"):
        v = getattr(m, k, None)
        if v:
            out[k] = v if not isinstance(v, list) else [str(x) for x in v]
    return json.dumps(out, default=str)


def instrument_defender_modifiers():
    """ETAGE 2 -- enregistre CHAQUE appel du foyer `defender_modifiers` (le builder partage
    `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction`).
    Rend `(calls, restore)`."""
    from engine.runner import damage_model as DM
    calls = []
    orig = DM.defender_modifiers

    def _wrapped(state, unit_id, hp, is_melee=None, damage_profile=None,
                 attacker_id=None, is_normal_attack=None):
        mods, active = orig(state, unit_id, hp, is_melee=is_melee, damage_profile=damage_profile,
                            attacker_id=attacker_id, is_normal_attack=is_normal_attack)
        calls.append({"unit": unit_id, "is_melee": is_melee, "profile": damage_profile,
                      "attacker": attacker_id, "is_normal_attack": is_normal_attack,
                      "active": [getattr(e, "name", None) for e in (active or [])],
                      "mods": _mods_repr(mods)})
        return mods, active

    DM.defender_modifiers = _wrapped
    # Les modules d'operation importent le symbole DIRECTEMENT (`from ...damage_model import
    # defender_modifiers`) : re-lier le module seul ne suffirait pas, on patche chaque porteur.
    import engine.runner.operations.damage_ops.ability as _AB
    import engine.runner.operations.damage_ops.normal as _NO
    import engine.runner.operations.damage_ops.normal_like as _NL
    holders = [_NO, _NL, _AB]
    prev = [(h, getattr(h, "defender_modifiers", None)) for h in holders]
    for h in holders:
        if getattr(h, "defender_modifiers", None) is not None:
            h.defender_modifiers = _wrapped

    def restore():
        DM.defender_modifiers = orig
        for h, p in prev:
            if p is not None:
                h.defender_modifiers = p

    return calls, restore


def instrument_bounds():
    """ETAGE 2bis -- enregistre les DEUX etages que `_reduced_bounds` enchaine :
    `apply_pierce_and_modifiers(valeur, pierce, armure, mods_attaquant)` (percage + les DEUX
    %-list + les DEUX `Multiplier@0x30`) puis `apply_all_modifiers(., def_mods)` (ce qui RESTE
    dans l'accumulateur DEFENSEUR apres `_apply_defender_flat_reductions`). C'est le couple qui
    dit OU un terme atterrit. Rend `(rows, restore)`."""
    import engine.runner.operations.damage_ops.normal as _NO
    rows = []
    o_pierce, o_all = _NO.apply_pierce_and_modifiers, _NO.apply_all_modifiers
    pending = {}

    def _pierce(value, pierce_pct=100, armor=0, mods=None, hit_mult=1, attacker_additive_pre=False):
        out = o_pierce(value, pierce_pct, armor, mods, hit_mult, attacker_additive_pre)
        pending.clear()
        pending.update({"value": value, "pierce": pierce_pct, "armor": armor,
                        "att_additive": getattr(mods, "additive", None),
                        "att_pct": [str(x) for x in (getattr(mods, "pct_list", None) or [])],
                        "def_pct_moved": [str(x) for x in (getattr(mods, "pct_list_defender", None) or [])],
                        "att_mult": getattr(mods, "multiplicative", None),
                        "def_mult_moved": getattr(mods, "multiplicative_defender", None),
                        "att_details": [(e.kind, e.value, e.owner_is_caster)
                                        for e in (getattr(mods, "details", None) or [])],
                        "after_pierce_mods": out})
        return out

    def _all(value, mods, round_materialize=False):
        out = o_all(value, mods, round_materialize)
        row = dict(pending)
        row.update({"def_additive_left": getattr(mods, "additive", None),
                    "def_pct_left": [str(x) for x in (getattr(mods, "pct_list", None) or [])],
                    "def_details": [(e.kind, e.value, e.owner_is_caster)
                                    for e in (getattr(mods, "details", None) or [])],
                    "final": out})
        rows.append(row)
        return out

    _NO.apply_pierce_and_modifiers = _pierce
    _NO.apply_all_modifiers = _all

    def restore():
        _NO.apply_pierce_and_modifiers = o_pierce
        _NO.apply_all_modifiers = o_all

    return rows, restore


def _live_hits(action, tgt):
    """Ledger natif PAR COUP : tag `Amount` des events de l'action, filtre sur la cible."""
    hits = []
    for ev in (action.get("events") or []):
        td = ev.get("tags")
        td = json.loads(td) if isinstance(td, str) else (td or {})
        if "Amount" in td and int(td.get("Target_Id", td.get("TargetId", tgt)) or tgt) == int(tgt):
            hits.append(int(td["Amount"]))
    return hits


def run(sid, victim_visual, layout):
    from engine.runner.abilities.darkangels import ExemplarOfHateAbility
    rid = N5._build(sid, N5.P_UNITS, N5.A_UNITS, anchor=layout[victim_visual],
                    occupied=layout.values())
    try:
        board, dv, ob, cs = _snapshot(sid, rid)
        bv = PR.units_by_visual(dv)
        caster, tgt = bv["darkaAsmodai"]["id"], bv[victim_visual]["id"]
        print("[%s] cible u%s (caster u%s)" % (victim_visual, tgt, caster))
        print("  LIVE decisionView effets PRE :", PR.eff_names(dv, tgt))

        st = _seeded_state(sid, rid, board, dv, ob, cs)
        dump_effects(st, tgt, "cible")

        calls, restore = instrument_defender_modifiers()
        rows, restore_b = instrument_bounds()
        try:
            php0 = _hp(st, tgt)
            port = ExemplarOfHateAbility().execute_behaviour(st, caster, tgt)
            php1 = _hp(st, tgt)
        finally:
            restore_b()
            restore()
        for row in rows:
            print("  [2bis] %s" % json.dumps(row, default=str))
        for c in calls:
            print("  [2] defender_modifiers u%s melee=%s profil=%s att=%s normal=%s"
                  % (c["unit"], c["is_melee"], c["profile"], c["attacker"], c["is_normal_attack"]))
            print("      active=%s" % (c["active"],))
            print("      mods=%s" % (c["mods"],))
        atk = (port or {}).get("attack") or {}
        print("  [3] PORT hp %s -> %s  (inflige %s)" % (php0, php1, (php0 or 0) - (php1 or 0)))
        print("      PORT attack total=%s per_hit=%s profil=%s hits=%s"
              % (atk.get("total"), atk.get("per_hit"), atk.get("profile"), atk.get("hits")))
        print("      PORT attack effets vus=%s" % (atk.get("effects"),))
        print("      PORT override=%s attaquant=%s" % (port.get("attack_override"), port.get("attacker")))

        hp0 = PR.hp_of(sid, rid)
        res = PR.act(sid, rid, {"kind": "ability", "casterId": caster, "targetId": tgt,
                                "abilityType": EXEMPLAR})
        hp1 = PR.hp_of(sid, rid)
        srcs = [e.get("source") for e in (res.get("events") or []) if e.get("kind") == "group"]
        print("  [3] LIVE hp %s -> %s  (inflige %s)"
              % (hp0.get(tgt), hp1.get(tgt),
                 (hp0.get(tgt) or (0,))[0] - (hp1.get(tgt) or (0,))[0]))
        print("      LIVE per_hit=%s" % (_live_hits(res, tgt),))
        print("      LIVE groupes=%s" % (srcs,))
        dv2 = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 60)
        print("      LIVE effets cible POST=%s" % (PR.eff_names(dv2, tgt),))
    finally:
        PR.dispose(sid, rid)


def main():
    sid = R._resolve_session()
    only = sys.argv[1] if len(sys.argv) > 1 else "immune"
    try:
        layout = N5.enemy_layout(sid)
        if only in ("immune", "both"):
            run(sid, N5.IMMUNE_VICTIM, layout)
        if only in ("control", "both"):
            run(sid, N5.CONTROL_VICTIM, layout)
    finally:
        for rid in list(PR._rids):
            PR.dispose(sid, rid)


if __name__ == "__main__":
    main()
