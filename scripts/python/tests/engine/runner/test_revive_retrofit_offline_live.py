"""#79 (retrofit case-66) -- ReanimationBeam + PhoenixGem : ports MIRROR valides OFFLINE.

Les deux carriers ne sont PAS montables en runner :
  * `necroReanimator` (ReanimationBeam, effet 1547) = **Machine of War hors pool** (les 8 MoW spawnables
    au rank 17 ne l'incluent pas) et les abilities castees par une MoW hors-plateau sont bloquees par le
    harnais headless ;
  * `PhoenixGem` (effet-marqueur 1451) est un **UniqueRelic**, pas une ability du kit d'`eldarAutarch`
    (`Loki_SwoopingHawk` / `PathOfCommand`) -> non posable via `rl_duel build`.
-> l'etat est capture LIVE (board/stats/traits REELS via load_state) et l'effet est INJECTE dans
`state.effects` (ce que ferait la pose native). Chaque discriminant du port est oppose a sa face negative.

Artefacts : `ReanimationBeam_ReviveEffect` ctor @180f67b90 / filter @180f67ac0 (base `ReviveEffect`
@180f46d80/@180f46a70) ; `PhoenixGem_ReviveAbility` CreateTrigger @1811117b0 / CreateBehaviour @181111610
enregistree par `PhoenixGem_CanReviveEffect.CreateHandleTriggerAbilitiesInternal @180f5e4a0`. ASCII only.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.operations.triggers import after_death_triggers
from engine.runner.operations.revive import reset_revive_gates, kill_unit_revive_gate
from engine.runner.components import (UnitComponent, HealthComponent, OwnerComponent,
                                      StatsComponent, PositionComponent)
from engine.runner.prng import IntBasedMersenneTwister
from engine.entities.pathfinding.board import Board
from engine.entities.effects.base import BaseEffect
from engine.entities.effects.magnitude import ability_var
from engine.runner.operations.triggers.loki.reanimation_beam import (
    REANIMATION_BEAM_EFFECT, NANOSCARAB_EFFECT)
from engine.runner.operations.triggers.loki.phoenix_gem import PHOENIX_GEM_CAN_REVIVE

BUILD = ["--p-units", "ultraTitus,bloodIntercessor", "--a-units", "worldKharn",
         "--rank", "17", "--board", "MC1_67"]
LEVEL, MULT = 50, 180        # niveau/multiplicateur de l'ability SOURCE, transportes par l'effet


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


@pytest.fixture(scope="module")
def env(live_session, rpc, build_runner):
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
    if getattr(load_state(dv, ob, snap, board=board), "effects", None) is None:
        pytest.skip("pas d'EffectsState")
    return {"dv": dv, "ob": ob, "snap": snap, "board": board}


def _fresh(env, seed=777):
    st = load_state(env["dv"], env["ob"], env["snap"], board=env["board"])
    st.rng = IntBasedMersenneTwister(seed)
    return st


def _two_allies(st):
    teams = {}
    for uid, e in st.entities.items():
        oc = e.get_component(OwnerComponent)
        if oc is not None:
            teams.setdefault(oc.team, []).append(uid)
    t = sorted(teams)[0]
    if len(teams[t]) < 2:
        pytest.skip("moins de 2 allies")
    return teams[t][0], teams[t][1]


def _add_effect(st, uid, etype, name, level=LEVEL, mult=MULT):
    e = BaseEffect(name=name, effect_type=etype, active_ability_level=level, ability_level=level,
                   ability_variables_multiplier=mult, source=uid, target=uid)
    st.effects.by_unit.setdefault(int(uid), []).append(e)
    return e


def _traits(st, uid, *add):
    sc = st.get_entity(uid).get_component(StatsComponent)
    sc.ctx.traits = list(getattr(sc.ctx, "traits", None) or []) + list(add)


def _kill(st, uid, killer, overkill=False):
    """`On(1)` PUIS la GARDE @0x180e76c9e (`kill_unit_revive_gate`) qui draine la `ReviveData` posee par
    la feuille `Revive` -- mirror de `KillUnitOperation.Execute @180e76470` (case-89 volet C)."""
    st.get_entity(uid).get_component(HealthComponent).hp = 0
    st.get_entity(uid).get_component(UnitComponent).alive = False
    out = after_death_triggers(st, dying_id=uid, killer_id=killer, overkill=overkill)
    kill_unit_revive_gate(st, uid)
    return out


def _alive(st, uid):
    return st.get_entity(uid).get_component(UnitComponent).alive


# ----------------------------------------------------------------- ReanimationBeam (effet 1547)
def _setup_beam(env, mechanical=True, nanoscarab=True):
    st = _fresh(env)
    beam, tgt = _two_allies(st)               # beam = porteur de l'effet 1547 (le Reanimator)
    _add_effect(st, beam, REANIMATION_BEAM_EFFECT, "ReanimationBeam_Revive")
    if mechanical:
        # HasTrait(target, Mechanical=5) SEUL. Le port pose desormais `heal_type = 1` (Repair), lu dans
        # methodPointers @0x31006a0 = @1802cca80 (`return 1`) -> `IsAffectedByHealType(1) @180ed77d0`
        # EXIGE une cible mecanique : plus besoin de la bequille `AffectedByHealAndRepair` (avec
        # l'ancien healType=0 code en dur, une cible Mechanical SANS ce trait etait REJETEE -> le revive
        # ReanimationBeam etait un NO-OP GARANTI, case-89 volet B1).
        _traits(st, tgt, "Mechanical")
    if nanoscarab:
        _add_effect(st, tgt, NANOSCARAB_EFFECT, "NanoscarabRepairProtocols")
    return st, beam, tgt


def test_beam_revives_mechanical_ally_with_nanoscarab(env):
    """Filtre @180f67ac0 rempli (ami + Mechanical + effet 1545) -> revive EN PLACE a min(reviveHP,maxPV)."""
    st, beam, tgt = _setup_beam(env)
    pc = st.get_entity(tgt).get_component(PositionComponent)
    pos0 = (pc.col, pc.row)
    maxhp = int(st.get_entity(tgt).get_component(HealthComponent).hp_max)
    exp = min(int(ability_var("ReanimationBeam", "hp", LEVEL, multiplier_pct=MULT)), maxhp)
    res = _kill(st, tgt, beam)
    assert _alive(st, tgt), "allie Mechanical nanoscarabe NON revive: %s" % res
    assert int(st.get_entity(tgt).get_component(HealthComponent).hp) == exp, "hp != min(reviveHP,maxPV)"
    assert (pc.col, pc.row) == pos0, "position CHANGEE (revive doit etre EN PLACE)"


def test_beam_requires_nanoscarab_effect(env):
    """`HasEffect(target, 1545)` : sans NanoscarabRepairProtocols -> PAS de revive."""
    st, beam, tgt = _setup_beam(env, nanoscarab=False)
    _kill(st, tgt, beam)
    assert not _alive(st, tgt), "revive sans l'effet 1545 (noeud HasEffect non respecte)"


def test_beam_requires_mechanical(env):
    """`HasTrait(target, Mechanical=5)` : une cible NON-Mechanical (meme avec 1545) -> PAS de revive.
    C'est l'INVERSE de Narthecium, qui exclut les Mechanical. DOUBLE barriere ici : le filtre
    @180f67ac0 ET `IsAffectedByHealType(healType=1)` @180ed77d0 (Repair -> mecaniques seulement)."""
    st, beam, tgt = _setup_beam(env, mechanical=False)
    _kill(st, tgt, beam)
    assert not _alive(st, tgt), "revive d'une cible non-Mechanical (filtre HasTrait non respecte)"


def test_beam_heal_type_is_repair(env):
    """Discriminant case-89/B1 : `get_HealType @vtable+0x748` de ReanimationBeam = **1** (Repair, lu dans
    methodPointers @0x31006a0 -> @1802cca80 `return 1`). Consequence OBSERVABLE : une cible MECHANICAL
    SANS le trait `AffectedByHealAndRepair` est revivable. Avec l'ancien healType=0 code en dur,
    `IsAffectedByHealType(0)` la rejetait -> le revive etait un NO-OP GARANTI.
    Face NEGATIVE opposee : avec healType=0 (celui de Narthecium/RitesOfMorkai), la MEME cible est
    rejetee -- on l'oppose directement via `is_affected_by_heal_type`."""
    from engine.runner.operations.triggers.revive_effect import is_affected_by_heal_type
    from engine.runner.abilities.behaviours import entities_from_state
    st, beam, tgt = _setup_beam(env)
    ent = entities_from_state(st, beam, tgt)
    assert is_affected_by_heal_type(ent.has_trait, ent.target, 1), "healType=1 rejette un Mechanical"
    assert not is_affected_by_heal_type(ent.has_trait, ent.target, 0), "healType=0 accepte un Mechanical"
    _kill(st, tgt, beam)
    assert _alive(st, tgt), "Mechanical sans AffectedByHealAndRepair NON revive (healType!=1)"


def test_beam_unless_overkilled_and_one_shot(env):
    """get_ReviveOnOverkill herite de la base = 0 -> overkill bloque ; et `removeEffect`=TRUE -> one-shot
    DEFINITIF (l'effet 1547 est retire, `reset_revive_gates` ne le rearme pas)."""
    st, beam, tgt = _setup_beam(env)
    _kill(st, tgt, beam, overkill=True)
    assert not _alive(st, tgt), "revive malgre l'overkill"
    st2, beam2, tgt2 = _setup_beam(env)
    _kill(st2, tgt2, beam2)
    assert _alive(st2, tgt2), "revive #1 attendu"
    assert all(e.consumed for e in st2.effects.by_unit[int(beam2)]
               if e.effect_type == REANIMATION_BEAM_EFFECT), "effet 1547 non RETIRE"
    reset_revive_gates(st2)
    _kill(st2, tgt2, beam2)
    assert not _alive(st2, tgt2), "2e revive apres reset (one-shot DEFINITIF non respecte)"


# ----------------------------------------------------------------- PhoenixGem (marqueur 1451)
def test_phoenix_self_revive_even_if_overkilled(env):
    """`OnPreDeath(ignoreOverkill=TRUE)` (constante LITTERALE du call @1811117b0) : le porteur du marqueur
    1451 est revive MEME en overkill, EN PLACE, sans `Maybe` (inconditionnel)."""
    st = _fresh(env)
    uid, other = _two_allies(st)
    _add_effect(st, uid, PHOENIX_GEM_CAN_REVIVE, "PhoenixGem_CanRevive")
    pc = st.get_entity(uid).get_component(PositionComponent)
    pos0 = (pc.col, pc.row)
    maxhp = int(st.get_entity(uid).get_component(HealthComponent).hp_max)
    exp = min(int(ability_var("PhoenixGem", "hp", LEVEL, multiplier_pct=MULT)), maxhp)
    res = _kill(st, uid, other, overkill=True)
    assert _alive(st, uid), "PhoenixGem n'a pas revive en overkill (even-if-Overkilled): %s" % res
    assert int(st.get_entity(uid).get_component(HealthComponent).hp) == exp, "hp != min(hp, maxPV)"
    assert (pc.col, pc.row) == pos0, "position CHANGEE"


def test_phoenix_once_per_battle(env):
    """Le marqueur 1451 est RETIRE apres le revive (mirror des 2 triggers RemoveEffect @180f5e4a0)
    -> « the FIRST TIME each BATTLE » : la 2e mort n'est pas revive, meme apres un turn-start."""
    st = _fresh(env)
    uid, other = _two_allies(st)
    _add_effect(st, uid, PHOENIX_GEM_CAN_REVIVE, "PhoenixGem_CanRevive")
    _kill(st, uid, other)
    assert _alive(st, uid), "revive #1 attendu"
    assert all(e.consumed for e in st.effects.by_unit[int(uid)]
               if e.effect_type == PHOENIX_GEM_CAN_REVIVE), "marqueur 1451 non retire"
    reset_revive_gates(st)
    _kill(st, uid, other)
    assert not _alive(st, uid), "2e revive (once-per-BATTLE non respecte)"


def test_phoenix_owner_is_target(env):
    """`get_OwnerIsTarget` : la mort d'une AUTRE unite ne declenche pas le revive du porteur."""
    st = _fresh(env)
    uid, other = _two_allies(st)
    _add_effect(st, uid, PHOENIX_GEM_CAN_REVIVE, "PhoenixGem_CanRevive")
    _kill(st, other, uid)
    assert not _alive(st, other), "une AUTRE unite a ete revive (OwnerIsTarget non respecte)"


def test_phoenix_no_marker_no_revive(env):
    """Garde anti-faux-positif : sans le marqueur 1451, aucune revive."""
    st = _fresh(env)
    uid, other = _two_allies(st)
    _kill(st, uid, other)
    assert not _alive(st, uid), "revive sans marqueur PhoenixGem"


def test_phoenix_marker_survives_a_foreign_revive(env):
    """Discriminant case-89/B3 : le retrait du marqueur 1451 est un trigger SEPARE
    (`PhoenixGem_CanReviveEffect.CreateHandleTriggerAbilitiesInternal @180f5e4a0`) gate par
    `CurrentAbilityIs(AbilityOrEffect(0x5b2=1458))`. Un revive venu d'AILLEURS (ici une `ReviveData`
    posee directement, sourceId != PhoenixGem) emet bien `On(0x2e)` mais NE consomme PAS le marqueur.
    L'ancien port chainait le `RemoveEffect` en dur au behaviour -> ce discriminant etait inexprimable."""
    from engine.runner.operations.revive import post_pending_revive, kill_unit_revive_gate as _gate
    st = _fresh(env)
    uid, other = _two_allies(st)
    _add_effect(st, uid, PHOENIX_GEM_CAN_REVIVE, "PhoenixGem_CanRevive")
    st.get_entity(uid).get_component(HealthComponent).hp = 0
    st.get_entity(uid).get_component(UnitComponent).alive = False
    post_pending_revive(st, uid, 500, heal_type=0, source=9999)   # sourceId ETRANGER
    assert _gate(st, uid) is not None, "revive etranger non applique"
    assert _alive(st, uid)
    assert not any(e.consumed for e in st.effects.by_unit[int(uid)]
                   if e.effect_type == PHOENIX_GEM_CAN_REVIVE), \
        "marqueur 1451 consomme par un revive ETRANGER (CurrentAbilityIs non respecte)"
