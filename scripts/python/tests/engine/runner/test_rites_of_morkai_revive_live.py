"""#79 (retrofit case-66) -- RitesOfMorkai : self-revive ONE-SHOT de l'unite « Inspired ».

`RitesOfMorkaiEffect` (IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect$$.ctor / filter IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect$$CreateTargetFilter) = sous-classe de `ReviveEffect`
(IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger / IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour) :
  * filtre = `get_OwnerIsTarget` -> le porteur de l'effet se revive LUI-MEME (aucun AreFriends/IsAdjacent :
    la portee a deja ete appliquee a la POSE de l'effet par l'active 1211 de Baldr) ;
  * ctor `removeEffect=TRUE` (champ 0x488) -> le 2e volet du behaviour est `GetRemoveEffectBehaviour` et
    NON `DeactivateEffect` => revive **one-shot DEFINITIF** (i2 : « The **first time** each inspired unit
    would be defeated ») -- contraste Narthecium/TaintedNarthecium (0x488=0 -> once-per-TURN) ;
  * `get_ReviveOnOverkill` non surcharge -> BASE GameCamera$$ShouldBlurBackground `return 0` => « unless Overkilled » (i2 idem).

VOIE : `spaceWolfPriest` (Baldr) est un HERO **absent du pool runner** (`rl_duel.py build --list-pool`,
rank 17 : les seuls `space*` spawnables sont Blackmane/Hound/Rockfist/Stormcaller/Wulfen, et il n'est
pas MoW ; SEUL porteur de l'active `RitesOfMorkai` cote gameconfig) -> l'effet 1502 n'est PAS posable
en runner. Port MIRROR valide OFFLINE : l'etat est capture LIVE (board/stats/traits reels via
load_state) et l'effet 1502 est INJECTE dans `state.effects` (ce que ferait la pose native). Les 3
discriminants du port (self-only, one-shot, unless-Overkilled) sont opposes a leur face negative.

4e discriminant depuis 2026-07-29 (residu #229) : le gate `EffectComponent.IsActive @+0x5c` que
`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` applique AVANT
d'evaluer le trigger de cible. Une instance 1502 seedee INERTE (canal
`decisionView { includeInactive: true }`, seede depuis #219) ne doit RIEN declencher.
ASCII only.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.operations.triggers import after_death_triggers
from engine.runner.operations.revive import reset_revive_gates, kill_unit_revive_gate
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
# Roster + board DIFFERENTS (autres factions, autres traits/PV, autre geometrie) : sert de
# generalisation au gate `IsActive` -- il ne doit dependre d'aucune particularite de BUILD.
# ⚠ Roster NON-MECHANICAL obligatoire : `get_HealType` de RitesOfMorkai vaut 0 (Heal), donc
# `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType` REFUSE les mecaniques -> un roster
# Necron/AdMec rendrait le controle POSITIF faux-negatif (mesure : `necroOverlord` ne revive pas,
# et c'est le comportement CORRECT -- i2 : « friendly NON-MECHANICAL units »).
BUILD_ALT = ["--p-units", "eldarFarseer,astraCreed", "--a-units", "orksNob",
             "--rank", "17", "--board", "C3_01"]


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


@pytest.fixture(scope="module")
def rom_alt_env(live_session, rpc, build_runner):
    """Second etat LIVE (autre roster, autre board, autre seed) pour la generalisation du gate."""
    rid = build_runner("4242", extra=BUILD_ALT)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo (alt)")
    board = Board(bg["tiles"], adjacency="evenq")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        pytest.skip("capture live KO (alt)")
    st0 = load_state(dv, ob, snap, board=board)
    if getattr(st0, "effects", None) is None:
        pytest.skip("pas d'EffectsState (combatSnapshot partiel, alt)")
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
    """`On(1)` PUIS la GARDE @IdunBattle.Operations.KillUnitOperation$$Execute+0x82e (`kill_unit_revive_gate`) qui draine la `ReviveData` posee par
    la feuille `Revive` -- mirror de `IdunBattle.Operations.KillUnitOperation$$Execute` (case-89 volet C)."""
    st.get_entity(uid).get_component(HealthComponent).hp = 0
    st.get_entity(uid).get_component(UnitComponent).alive = False
    out = after_death_triggers(st, dying_id=uid, killer_id=killer, overkill=overkill)
    kill_unit_revive_gate(st, uid)
    return out


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


# --- Gate `EffectComponent.IsActive @+0x5c` (residu #229) ------------------------------------------
# `EvaluateEffectTriggerTargets` relit le flag PAR CIBLE, sur l'`EffectComponent` recharge depuis
# l'entite-effet, AVANT `ShouldTrigger` : une instance INACTIVE n'est meme pas evaluee. Le rail
# oppose (`EvaluateEffectTriggerEffectAbilities`, `ArraySet`) n'a AUCUN gate -- 1502 n'y a rien.

def test_inactive_instance_does_not_revive(rom_env):
    """CONTRE-EPREUVE du gate : instance 1502 posee mais `active=False` -> AUCUN revive, et l'effet
    n'est PAS consomme (le natif n'evalue pas le trigger, donc n'execute pas non plus le
    `RemoveEffect` du 2e volet du behaviour). Ce test ECHOUE sur le port d'avant le gate."""
    st = _fresh(rom_env)
    uid, other = _first_player_unit(st)
    e = _inspire(st, uid)
    e.active = False                       # ce que seede `decisionView { includeInactive: true }`
    res = _kill(st, uid, other)
    assert not st.get_entity(uid).get_component(UnitComponent).alive, \
        "revive par une instance 1502 INACTIVE (gate IsActive @+0x5c absent)"
    assert not e.consumed, "effet 1502 consomme alors que le trigger n'a PAS ete evalue"
    assert not any(r.get("ability") == "RitesOfMorkai" for r in res), \
        "trigger 1502 execute malgre l'instance inactive: %s" % res


def test_reactivated_instance_revives(rom_env):
    """Face POSITIVE du meme gate : le flag remis a True (ce que fait `RefreshEffectsOperation$$
    ActivateEffect`, `+0x5c = 1`) rend le trigger evaluable -> revive normal. Prouve que le gate lit
    bien le FLAG et pas autre chose (l'etat est par ailleurs identique au test negatif)."""
    st = _fresh(rom_env)
    uid, other = _first_player_unit(st)
    e = _inspire(st, uid)
    e.active = False
    e.active = True                        # re-activation avant la mort
    res = _kill(st, uid, other)
    assert st.get_entity(uid).get_component(UnitComponent).alive, \
        "instance re-activee non revive: %s" % res
    assert e.consumed, "effet 1502 non retire apres un revive reussi"


def test_gate_is_per_instance(rom_env):
    """Le flag est PORTE PAR L'INSTANCE (`EffectComponent`), pas par le type ni par l'unite : deux
    unites inspirees, l'une avec une instance active, l'autre inerte -> seule la 1re est revive."""
    st = _fresh(rom_env)
    uid, other = _first_player_unit(st)
    if other is None:
        pytest.skip("pas de 2e unite alliee")
    e_live = _inspire(st, uid)             # instance ACTIVE
    e_dead = _inspire(st, other)           # instance INERTE
    e_dead.active = False
    third = next((u for u in st.entities if u not in (uid, other)), None)
    if third is None:
        pytest.skip("pas de 3e unite pour porter le coup")
    _kill(st, uid, third)
    _kill(st, other, third)
    assert st.get_entity(uid).get_component(UnitComponent).alive, "porteur ACTIF non revive"
    assert e_live.consumed, "instance active non consommee par son revive"
    assert not st.get_entity(other).get_component(UnitComponent).alive, \
        "porteur INERTE revive (le gate a fuite d'une instance a l'autre)"
    assert not e_dead.consumed, "instance inerte consommee"


def test_inactive_instance_does_not_revive_alt_board(rom_alt_env):
    """GENERALISATION : meme verdict sur un AUTRE roster (autre faction, autres traits/PV) et un
    AUTRE board -- le gate ne depend d'aucune particularite de l'etat de `rom_env`."""
    st = _fresh(rom_alt_env)
    uid, other = _first_player_unit(st)
    e = _inspire(st, uid)
    e.active = False
    _kill(st, uid, other)
    assert not st.get_entity(uid).get_component(UnitComponent).alive, \
        "revive par une instance 1502 INACTIVE (autre roster/board)"
    assert not e.consumed, "effet 1502 consomme alors que le trigger n'a PAS ete evalue"
    # controle positif dans le MEME etat : l'instance active revive bien.
    st2 = _fresh(rom_alt_env)
    uid2, other2 = _first_player_unit(st2)
    _inspire(st2, uid2)
    _kill(st2, uid2, other2)
    assert st2.get_entity(uid2).get_component(UnitComponent).alive, \
        "instance ACTIVE non revive sur l'autre roster/board (controle positif)"
