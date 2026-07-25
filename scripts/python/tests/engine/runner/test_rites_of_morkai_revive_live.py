"""#79 (retrofit case-66) -- RitesOfMorkai : self-revive ONE-SHOT de l'unite « Inspired ».

`RitesOfMorkaiEffect` (ctor @180f69c30 / filter @180f69c10) = sous-classe de `ReviveEffect`
(CreateTargetTrigger @180f46d80 / CreateTargetTriggerBehaviour @180f46a70) :
  * filtre = `get_OwnerIsTarget` -> le porteur de l'effet se revive LUI-MEME (aucun AreFriends/IsAdjacent :
    la portee a deja ete appliquee a la POSE de l'effet par l'active 1211 de Baldr) ;
  * ctor `removeEffect=TRUE` (champ 0x488) -> le 2e volet du behaviour est `GetRemoveEffectBehaviour` et
    NON `DeactivateEffect` => revive **one-shot DEFINITIF** (i2 : « The **first time** each inspired unit
    would be defeated ») -- contraste Narthecium/TaintedNarthecium (0x488=0 -> once-per-TURN) ;
  * `get_ReviveOnOverkill` non surcharge -> BASE @1802b15a0 `return 0` => « unless Overkilled » (i2 idem).

VOIE : `spaceWolfPriest` (Baldr) est un HERO **absent du pool runner** (`rl_duel.py build --list-pool`,
rank 17) -> l'effet 1502 n'est PAS posable en runner. Port MIRROR valide OFFLINE : l'etat est capture
LIVE (board/stats/traits reels via load_state) et l'effet 1502 est INJECTE dans `state.effects` (ce que
ferait la pose native). Les 3 discriminants du port (self-only, one-shot, unless-Overkilled) sont
opposes a leur face negative. ASCII only.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.operations.triggers import after_death_triggers
from engine.runner.operations.revive import reset_revive_gates
from engine.runner.components import (UnitComponent, HealthComponent, PositionComponent,
                                      StatsComponent)
from engine.runner.prng import IntBasedMersenneTwister
from engine.entities.pathfinding.board import Board
from engine.entities.effects.base import BaseEffect
from engine.entities.effects.magnitude import ability_var
from engine.runner.operations.triggers.loki.rites_of_morkai import RITES_OF_MORKAI_EFFECT

# Roster quelconque du pool : le porteur reel (spaceWolfPriest) est hors pool -> on INJECTE l'effet.
BUILD = ["--p-units", "ultraTitus,bloodIntercessor", "--a-units", "worldKharn",
         "--rank", "17", "--board", "MC1_67"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _first_player_unit(state):
    from engine.runner.components import OwnerComponent
    teams = {}
    for uid, e in state.entities.items():
        oc = e.get_component(OwnerComponent)
        if oc is not None:
            teams.setdefault(oc.team, []).append(uid)
    t = sorted(teams)[0]
    return teams[t][0], teams[t][1] if len(teams[t]) > 1 else None


@pytest.fixture(scope="module")
def rom_env(live_session, rpc, build_runner):
    rid = build_runner("31337", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        pytest.skip("capture live KO")
    st0 = load_state(dv, ob, snap, board=board)
    if getattr(st0, "effects", None) is None:
        pytest.skip("pas d'EffectsState (combatSnapshot partiel)")
    return {"dv": dv, "ob": ob, "snap": snap, "board": board}


def _fresh(env, seed=777):
    st = load_state(env["dv"], env["ob"], env["snap"], board=env["board"])
    st.rng = IntBasedMersenneTwister(seed)
    return st


POSER_LEVEL = 50          # niveau de l'ACTIVE RitesOfMorkai du poseur (Baldr) transporte par l'effet
POSER_MULT = 180          # AbilityVariablesMultiplierPercentage du poseur


def _inspire(st, uid, level=POSER_LEVEL, mult=POSER_MULT):
    """Pose l'effet 1502 « Inspired » sur `uid` -- mirror de ce que fait l'active 1211 de Baldr
    (`AddEffectOperation`), le porteur reel etant hors pool. L'effet TRANSPORTE le niveau/multiplicateur
    de l'ability du POSEUR (c'est l'`abilityState` que lit `GetReviveHP`)."""
    e = BaseEffect(name="RitesOfMorkai", effect_type=RITES_OF_MORKAI_EFFECT,
                   active_ability_level=level, ability_level=level,
                   ability_variables_multiplier=mult, source=uid, target=uid)
    st.effects.by_unit.setdefault(int(uid), []).append(e)
    return e


def _kill(st, uid, killer, overkill=False):
    st.get_entity(uid).get_component(HealthComponent).hp = 0
    st.get_entity(uid).get_component(UnitComponent).alive = False
    return after_death_triggers(st, dying_id=uid, killer_id=killer, overkill=overkill)


def test_self_revive_in_place(rom_env):
    """L'unite INSPIREE qui meurt (sans overkill) est revive EN PLACE a min(reviveHP, maxPV)."""
    st = _fresh(rom_env)
    uid, other = _first_player_unit(st)
    _inspire(st, uid)
    pc = st.get_entity(uid).get_component(PositionComponent)
    pos0 = (pc.col, pc.row)
    maxhp = int(st.get_entity(uid).get_component(HealthComponent).hp_max)
    # `GetReviveHP` lit l'abilityState PORTE PAR L'EFFET (niveau/mult du POSEUR), pas ceux du porteur.
    rhp = ability_var("RitesOfMorkai", "hp", POSER_LEVEL, multiplier_pct=POSER_MULT)
    res = _kill(st, uid, other)
    assert st.get_entity(uid).get_component(UnitComponent).alive, \
        "unite inspiree NON revive: %s" % res
    hp = int(st.get_entity(uid).get_component(HealthComponent).hp)
    assert hp > 0 and hp <= maxhp, "hp revive invalide: %d (maxPV=%d)" % (hp, maxhp)
    if rhp is not None:
        assert hp == min(int(rhp), maxhp), "hp %d != min(reviveHP=%s, maxPV=%d)" % (hp, rhp, maxhp)
    assert (pc.col, pc.row) == pos0, "position CHANGEE (revive doit etre EN PLACE)"
    assert any(r.get("ability") == "RitesOfMorkai" for r in res), "trigger absent: %s" % res


def test_one_shot_definitive(rom_env):
    """`removeEffect`(0x488)=TRUE -> RemoveEffect : le revive est one-shot DEFINITIF. Une 2e mort ne
    revive plus, MEME apres `reset_revive_gates` (qui ne rearme QUE le once-per-turn de Narthecium)."""
    st = _fresh(rom_env)
    uid, other = _first_player_unit(st)
    _inspire(st, uid)
    _kill(st, uid, other)
    assert st.get_entity(uid).get_component(UnitComponent).alive, "revive #1 attendu"
    assert all(e.consumed for e in st.effects.by_unit[int(uid)]
               if e.effect_type == RITES_OF_MORKAI_EFFECT), "effet 1502 non RETIRE apres le revive"
    reset_revive_gates(st)                       # turn-start : ne doit PAS rearmer un RemoveEffect
    _kill(st, uid, other)
    assert not st.get_entity(uid).get_component(UnitComponent).alive, \
        "2e revive apres reset (one-shot DEFINITIF non respecte)"


def test_unless_overkilled(rom_env):
    """`get_ReviveOnOverkill` herite de la base = 0 -> mort en OVERKILL : PAS de revive (i2 « unless
    Overkilled »)."""
    st = _fresh(rom_env)
    uid, other = _first_player_unit(st)
    _inspire(st, uid)
    _kill(st, uid, other, overkill=True)
    assert not st.get_entity(uid).get_component(UnitComponent).alive, \
        "revive malgre l'overkill (RitesOfMorkai = unless Overkilled)"
    assert all(not e.consumed for e in st.effects.by_unit[int(uid)]
               if e.effect_type == RITES_OF_MORKAI_EFFECT), \
        "effet consomme alors que le trigger n'a pas matche"


def test_owner_is_target_only(rom_env):
    """`get_OwnerIsTarget` : l'effet ne revive QUE son porteur -- la mort d'une AUTRE unite (meme
    adjacente, meme alliee) ne le declenche pas (contraste Narthecium, qui revive un ALLIE)."""
    st = _fresh(rom_env)
    uid, other = _first_player_unit(st)
    if other is None:
        pytest.skip("pas de 2e unite alliee")
    _inspire(st, uid)                             # l'effet est sur `uid`, on tue `other`
    _kill(st, other, uid)
    assert not st.get_entity(other).get_component(UnitComponent).alive, \
        "une AUTRE unite a ete revive (OwnerIsTarget non respecte)"
    assert st.get_entity(uid).get_component(UnitComponent).alive, "le porteur ne devait pas mourir"


def test_no_effect_no_revive(rom_env):
    """Sans l'effet 1502 pose, aucune revive (garde anti-faux-positif du rail EFFECT_TRIGGERS)."""
    st = _fresh(rom_env)
    uid, other = _first_player_unit(st)
    _kill(st, uid, other)
    assert not st.get_entity(uid).get_component(UnitComponent).alive, \
        "revive sans effet RitesOfMorkai pose"
