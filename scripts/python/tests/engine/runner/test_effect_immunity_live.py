"""#224 GATE D'IMMUNITE D'EFFET -- `BaseEffect.EntityIsImmuneToEffect` + `get_CanBeImmuneTo`.

Le gate vit dans `IdunBattle.Operations.AddEffectOperation$$Execute` (interface `IEffect` slot 40, le
MEME appel qu'expose `IdunBattle.Core.Services.BattleQuery$$IsUnitImmuneTo`) : vrai -> la pose est
ABANDONNEE avant toute materialisation. Le predicat est DECLARATIF, porte par la classe d'effet.

Ce que ces tests PROUVENT -- les DEUX branches, c'est ce qui distingue un GATE d'une DESACTIVATION :
  (1) `SentinelDirectives` (1139, admecDestroyer) sur `blackAbaddon` (trait `TerminatorArmour`, i2
      « This unit cannot be Suppressed ») : le natif ne pose PAS `Pinned` (aucun groupe `AddEffect`,
      effet absent de `decisionView`) -- et le PORT non plus. Poseur INCONDITIONNEL (aucune branche,
      aucune election d'attaquant) -> discriminant PUR du gate.
  (2) MEME ability, MEME runner, cible `blackPossession` (Chaos SANS `TerminatorArmour`) : natif ET
      port posent `Pinned`. Sans ce contre-cas, un gate et une desactivation globale sont
      indiscernables.
  (3) `ExemplarOfHate` (1140) -- le montage de la MESURE #112 : meme dichotomie sur les deux cibles.
  (4) NON-SUR-IMMUNITE offline : sur la MEME cible `TerminatorArmour`, un effet dont
      `CanBeImmuneTo` est FAUX (`Stunned` 1162) passe ; et sur une cible sans le trait, `Pinned` passe.
  (5) Canal declaratif : `EffectFactory.effect_def` (mirror `EffectsDatabase.Get`) rend le bon predicat
      par classe -- et `Contaminated` n'a plus de liste de traits EN DUR dans `effect_triggers.py`.

ASCII only. Dispose SES runners.
"""
from __future__ import annotations

import pytest

import probe_112_darkangels as PR
import probe_224_effect_immunity as IM
from engine.entities.effects import EffectFactory
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.entities.traits import UnitTrait
from engine.runner.abilities.admec import SentinelDirectivesAbility
from engine.runner.abilities.darkangels import ExemplarOfHateAbility
from engine.runner.operations.effects import AddEffectOperation, entity_is_immune_to_effect
from engine.runner.snapshot import load_state

SENTINEL, EXEMPLAR = 1139, 1140
PINNED, STUNNED = int(EffectType.Pinned), int(EffectType.Stunned)
IMMUNE_VICTIM, CONTROL_VICTIM = "blackAbaddon", "blackPossession"


# ------------------------------------------------------------------ helpers

def _snapshot(sid, rid):
    bg = PR.rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = PR.rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    cs = PR.rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    return board, dv, ob, cs


def _effect_groups(action: dict) -> list:
    return [e.get("source") for e in (action.get("events") or [])
            if e.get("kind") == "group" and e.get("group") == 22]


def _effect_types(dv, uid) -> set:
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return {e.get("effectType") for e in ((u or {}).get("effects") or [])}


def _port_effect_types(state, uid) -> set:
    effs = (state.effects.by_unit.get(int(uid)) if state.effects is not None else None) or []
    return {e.effect_type for e in effs if not e.consumed}


@pytest.fixture
def sentinel_runner(live_session):
    """Runner FRAIS : `admecDestroyer` (poseur de Pinned inconditionnel) face aux DEUX cibles --
    `blackAbaddon` (TerminatorArmour) et `blackPossession` (Chaos sans le trait)."""
    sid = live_session
    rid = IM._build_custom(sid, ["admecDestroyer"], [IMMUNE_VICTIM, CONTROL_VICTIM])
    try:
        yield sid, rid
    finally:
        PR.dispose(sid, rid)


@pytest.fixture
def da_runner(live_session):
    sid = live_session
    rid = PR.build(sid)
    try:
        yield sid, rid
    finally:
        PR.dispose(sid, rid)


def _sentinel_case(sid, rid, victim_visual, expect_pinned):
    board, dv, ob, cs = _snapshot(sid, rid)
    bv = PR.units_by_visual(dv)
    if "admecDestroyer" not in bv or victim_visual not in bv:
        pytest.skip("roster incomplet: %s" % sorted(bv))
    caster, tgt = bv["admecDestroyer"]["id"], bv[victim_visual]["id"]
    if tgt not in PR.legal_from_here(sid, rid, caster, SENTINEL):
        pytest.skip("cible %s hors portee depuis la position courante" % victim_visual)

    st = load_state(dv, ob, cs, board=board)
    off = SentinelDirectivesAbility().execute_behaviour(st, caster, tgt)
    assert off is not None and off.get("dsl") is True
    res = PR.cast(sid, rid, caster, tgt, SENTINEL)
    assert res.get("ok"), "cast live KO: %s" % str(res)[:200]
    dv2 = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 90)

    live_group = "Pinned" in _effect_groups(res)
    live_eff = PINNED in _effect_types(dv2, tgt)
    port_placed = bool(off.get("pinned_placed"))
    port_eff = PINNED in _port_effect_types(st, tgt)
    print("\n[sentinel %s] live group=%s effect=%s | port placed=%s effect=%s (attendu=%s)"
          % (victim_visual, live_group, live_eff, port_placed, port_eff, expect_pinned))
    assert live_group is expect_pinned, "LIVE: groupe Pinned=%s, attendu %s" % (live_group, expect_pinned)
    assert live_eff is expect_pinned, "LIVE: effet Pinned=%s, attendu %s" % (live_eff, expect_pinned)
    assert port_placed is expect_pinned, "PORT: pinned_placed=%s, attendu %s" % (port_placed, expect_pinned)
    assert port_eff is expect_pinned, "PORT: effet Pinned=%s, attendu %s" % (port_eff, expect_pinned)
    return st, tgt


# ------------------------------------------------------------------ (1)(2) branche immunisee / non

def test_sentinel_pinned_refused_on_terminator_armour(sentinel_runner):
    """Poseur INCONDITIONNEL sur une cible `TerminatorArmour` : ni le natif ni le port ne posent
    `Pinned`. C'est le critere du cas #224."""
    sid, rid = sentinel_runner
    _sentinel_case(sid, rid, IMMUNE_VICTIM, expect_pinned=False)


def test_sentinel_pinned_placed_without_terminator_armour(sentinel_runner):
    """CONTRE-CAS SYMETRIQUE (ce qui distingue un gate d'une desactivation) : meme ability, cible SANS
    le trait -> natif ET port posent `Pinned`."""
    sid, rid = sentinel_runner
    _sentinel_case(sid, rid, CONTROL_VICTIM, expect_pinned=True)


# ------------------------------------------------------------------ (3) montage de la MESURE #112

@pytest.mark.parametrize("victim,expect", [(IMMUNE_VICTIM, False), (CONTROL_VICTIM, True)])
def test_exemplar_of_hate_pinned_branch(da_runner, victim, expect):
    """`ExemplarOfHate` (1140) = le montage de la MESURE #112. Assertion BORNEE au volet `Pinned` : la
    suite de la branche Chaos (override d'Attack + attaque libre) depend d'une election d'attaquant
    DarkAngels a portee, non controlee ici -> confond documente (case-224 §6), non asserte."""
    sid, rid = da_runner
    board, dv, ob, cs = _snapshot(sid, rid)
    bv = PR.units_by_visual(dv)
    if "darkaAsmodai" not in bv or victim not in bv:
        pytest.skip("roster incomplet: %s" % sorted(bv))
    caster, tgt = bv["darkaAsmodai"]["id"], bv[victim]["id"]
    if tgt not in PR.legal_from_here(sid, rid, caster, EXEMPLAR):
        pytest.skip("cible %s non legale depuis la position courante" % victim)

    st = load_state(dv, ob, cs, board=board)
    off = ExemplarOfHateAbility().execute_behaviour(st, caster, tgt)
    res = PR.cast(sid, rid, caster, tgt, EXEMPLAR)
    assert res.get("ok"), "cast live KO: %s" % str(res)[:200]
    dv2 = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 90)

    live = "Pinned" in _effect_groups(res) and PINNED in _effect_types(dv2, tgt)
    port = PINNED in (off.get("effects") or [])
    print("\n[exemplar %s] live=%s port=%s (attendu=%s)" % (victim, live, port, expect))
    assert live is expect, "LIVE: Pinned=%s, attendu %s" % (live, expect)
    assert port is expect, "PORT: Pinned=%s, attendu %s" % (port, expect)


# ------------------------------------------------------------------ (4) non-sur-immunite (offline)

def test_gate_does_not_over_immunise(sentinel_runner):
    """Un gate, PAS une desactivation. Sur la MEME cible `TerminatorArmour` :
      * `Stunned` (1162, `CanBeImmuneTo` FAUX au natif) PASSE ;
      * `Pinned` (1065) est refuse ;
      * sur la cible SANS le trait, `Pinned` PASSE.
    Purement offline (aucun cast live) sur l'etat charge du runner -> zero effet de bord."""
    sid, rid = sentinel_runner
    board, dv, ob, cs = _snapshot(sid, rid)
    bv = PR.units_by_visual(dv)
    if IMMUNE_VICTIM not in bv or CONTROL_VICTIM not in bv:
        pytest.skip("roster incomplet: %s" % sorted(bv))
    immune, control = bv[IMMUNE_VICTIM]["id"], bv[CONTROL_VICTIM]["id"]
    st = load_state(dv, ob, cs, board=board)
    src = bv["admecDestroyer"]["id"]

    # ATTENTION -- les 2 assertions `immune x PINNED` ci-dessous verrouillent une APPROXIMATION, pas
    # le natif. MESURE 2026-07-28 : le natif POSE l'effet (`AddEffectOperation$$Execute` rend une
    # entite NON nulle) et `EntityIsImmuneToEffect` y rend FALSE ; c'est l'`ActiveCondition`
    # (`RefreshEffectsOperation$$ShouldBeActive`) qui le rend inerte. Quand le chantier de
    # case-224 §5.1 defera le collapse, ces 2 lignes DOIVENT passer a False / `is not None` -- ce
    # n'est pas un test a contourner, c'est l'attendu qui change avec le cablage.
    assert entity_is_immune_to_effect(st, immune, PINNED, name="Pinned") is True
    assert entity_is_immune_to_effect(st, immune, STUNNED, name="Stunned") is False
    assert entity_is_immune_to_effect(st, control, PINNED, name="Pinned") is False

    assert AddEffectOperation.execute(st, src, immune, PINNED, name="Pinned") is None, \
        "Pinned pose sur une cible TerminatorArmour"
    assert AddEffectOperation.execute(st, src, immune, STUNNED, name="Stunned") is not None, \
        "SUR-IMMUNITE : Stunned refuse alors que CanBeImmuneTo est faux pour cet effet"
    assert AddEffectOperation.execute(st, src, control, PINNED, name="Pinned") is not None, \
        "SUR-IMMUNITE : Pinned refuse sur une cible sans TerminatorArmour"


# ------------------------------------------------------------------ (5) canal declaratif (pur)

def test_effect_def_channel_is_declarative():
    """`EffectFactory.effect_def` = mirror d'`EffectsDatabase.Get(effectType)` : le predicat vient de la
    CLASSE d'effet, jamais d'une liste de traits recablee par appelant.

      * base `BaseEffect$$EntityIsImmuneToEffect` = `HasTrait(Immune) && CanBeImmuneTo` ;
      * `get_CanBeImmuneTo` par defaut FAUX -> un effet non porte n'invente aucune immunite ;
      * `ContaminatedEffect$$EntityIsImmuneToEffect` = ContagionsOfNurgle | Mechanical | base."""
    pinned = EffectFactory.effect_def(PINNED, "Pinned")
    contam = EffectFactory.effect_def(int(EffectType.Contaminated), EffectType.Contaminated.name)
    stunned = EffectFactory.effect_def(STUNNED, "Stunned")
    unknown = EffectFactory.effect_def(999999, "PasDeClassePortee")

    assert pinned.can_be_immune_to is True and contam.can_be_immune_to is True
    assert stunned.can_be_immune_to is False and unknown.can_be_immune_to is False

    tn = lambda *t: [UnitTrait(x).name for x in t]                                  # noqa: E731
    assert pinned.entity_is_immune_to_effect(tn(UnitTrait.TerminatorArmour)) is True
    assert pinned.entity_is_immune_to_effect(tn(UnitTrait.Immune)) is True
    assert pinned.entity_is_immune_to_effect(tn(UnitTrait.Chaos)) is False
    assert pinned.entity_is_immune_to_effect(None) is False                          # tuile / inconnu

    assert contam.entity_is_immune_to_effect(tn(UnitTrait.ContagionsOfNurgle)) is True
    assert contam.entity_is_immune_to_effect(tn(UnitTrait.Mechanical)) is True
    assert contam.entity_is_immune_to_effect(tn(UnitTrait.Immune)) is True
    assert contam.entity_is_immune_to_effect(tn(UnitTrait.TerminatorArmour)) is False

    # un effet sans surcharge n'est immunisable QUE via le trait generique, et seulement si le drapeau
    # `CanBeImmuneTo` est vrai -> ici faux -> jamais immune.
    assert stunned.entity_is_immune_to_effect(tn(UnitTrait.Immune)) is False
    assert unknown.entity_is_immune_to_effect(tn(UnitTrait.Immune)) is False


def test_contaminated_immunity_has_no_hardcoded_trait_list():
    """MIGRATION (anti-fork `check-own-port`) : `_is_immune_to_contaminated` DELEGUE au canal declaratif
    -- il ne doit plus exister deux portes offline pour le meme noeud natif."""
    from engine.runner.operations.triggers import effect_triggers as ET
    import inspect
    src = inspect.getsource(ET._is_immune_to_contaminated)
    assert "entity_is_immune_to_effect" in src, "la delegation a disparu"
    assert "has_any_trait" not in src, "liste de traits EN DUR re-introduite (fork 1 natif -> 2 portes)"
