"""#224 + #208 -- GATE D'IMMUNITE D'EFFET (`BaseEffect$$EntityIsImmuneToEffect` + `get_CanBeImmuneTo`)
et, DISTINCT, la `CreateActiveCondition` de `PinnedEffect`.

Ce sont DEUX etages natifs differents, et les confondre etait le bug de #224 :

  * IMMUNITE (gate de POSE) -- `IdunBattle.Operations.AddEffectOperation$$Execute` interroge
    `def.EntityIsImmuneToEffect(target)` (interface `IEffect` slot 40, le MEME appel qu'expose
    `IdunBattle.Core.Services.BattleQuery$$IsUnitImmuneTo`) : vrai -> `return 0`, ni entite-effet ni
    evenement. Predicat = `HasTrait(entity, 0x19 = Immune) && this.CanBeImmuneTo`.
  * ACTIVATION -- `IdunBattle.Entities.Effects.Loki.PinnedEffect$$CreateActiveCondition` =
    `Not(HasTrait(Self, 0x40f = TerminatorArmour))`, memoisee par
    `BaseEffect$$CreateActiveConditionAndCache` et EVALUEE par
    `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive`, qui ecrit
    `EffectComponent.IsActive @+0x5c`.

MESURE 2026-07-28 (`probe_208_pinned_inactive.py`, runner MC1_67, poseur INCONDITIONNEL
`SentinelDirectives` 1139 sur `admecDestroyer`) -- `TerminatorArmour` ne refuse RIEN :

    cible blackAbaddon (TerminatorArmour) : decisionView         -> pas de 1065
                                            includeInactive=true -> 1065 PRESENT, active=False
                                            exposureView reachDmgMax 1626 -> 1626   (ratio 1.0)
    cible blackPossession (controle)      : decisionView         -> 1065 PRESENT, active=True
                                            exposureView reachDmgMax 2895 -> 2026   (ratio 0.6998)

`decisionView` DROPPE par defaut les effets dont `IsActive` est faux (`readEffectsByUnit`,
`frida/hooks/game/effects.ts`) : c'est ce filtre qui faisait lire un « refus de pose ».

Ce que ces tests VERROUILLENT :
  (1) l'effet EST cree sur la cible `TerminatorArmour` -- `has_effect(1065)` vrai cote port ==
      canal `includeInactive` cote live ;
  (2) il ne change AUCUN nombre -- absent d'`active_effects` cote port == absent du canal
      `decisionView` par defaut cote live, et la plage de degat de la cible est INCHANGEE
      (aucun x0.70 de `PinnedEffect$$CreateEffectDamageBonusForAttack`) ;
  (3) CONTRE-CAS : meme ability, cible sans le trait -> effet ACTIF et x0.70 applique, live ET port ;
  (4) le gate d'IMMUNITE, lui, n'a pas bouge : un effet `CanBeImmuneTo` faux (Stunned) passe sur la
      MEME cible, et `Pinned` n'est refuse a la pose sur PERSONNE ici ;
  (5) canal declaratif : `EffectFactory.effect_def` rend le bon predicat par classe, et
      `Contaminated` n'a plus de liste de traits EN DUR dans `effect_triggers.py`.

ASCII only. Dispose SES runners.
"""
from __future__ import annotations

import pytest

import stream_events as SE
import probe_112_darkangels as PR
import probe_224_effect_immunity as IM
from engine.entities.effects.factory import EffectFactory
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.entities.traits.unit_trait import UnitTrait
from engine.runner.abilities.admec import SentinelDirectivesAbility
from engine.runner.abilities.darkangels import ExemplarOfHateAbility
from engine.runner.components import unit_state_for_effects
from engine.runner.damage_model import normal_attack_per_hit_range
from engine.runner.operations.effects import AddEffectOperation, entity_is_immune_to_effect
from engine.runner.snapshot import load_state

SENTINEL, EXEMPLAR = 1139, 1140
PINNED, STUNNED = int(EffectType.Pinned), int(EffectType.Stunned)
IMMUNE_VICTIM, CONTROL_VICTIM = "blackAbaddon", "blackPossession"
PINNED_PCT = 0.70          # `Effect.PinnedDmgReductionPct` = 30 -> x0.70 (BC, pas un litteral porte)


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
    # `GroupType.Effect_Refresh` resolu PAR NOM (#254b-b) -- cf. test_darkangels_lot1_live.
    return [e.get("source") for e in (action.get("events") or [])
            if e.get("kind") == "group" and e.get("group") == SE.group_id("Effect_Refresh")]


def _effects_of(dv, uid) -> list:
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return list((u or {}).get("effects") or [])


def _pinned_entry(dv, uid):
    """L'entree 1065 de la cible dans CE canal `decisionView`, ou None."""
    for e in _effects_of(dv, uid):
        if int(e.get("effectType") or -1) == PINNED:
            return e
    return None


def _threat_dmg(sid, rid, victim_id, enemy_id):
    """`(dmgMin, dmgMax)` que `enemy_id` peut infliger a `victim_id` -- predicteur NATIF
    (`GetAllPredictions`), ATTAQUE NORMALE seule (`allAbilities=False`). La plage ne bouge donc que
    si un MODIFICATEUR DE DEGAT de l'attaquant change : c'est exactement le x0.70 cherche."""
    ev = PR.rpc(sid, "exposureView",
                {"runnerId": rid, "unitId": victim_id, "allAbilities": False}, 120)
    for u in (ev.get("units") or []):
        if u.get("unitId") != victim_id:
            continue
        for t in (u.get("threats") or []):
            if t.get("enemyId") == enemy_id:
                return t.get("dmgMin"), t.get("dmgMax")
    return None, None


def _port_carried(state, uid) -> set:
    """EffectTypes PORTES (entite-effet existante) -- mirror de la liste native possedee, PAS du
    canal `decisionView` par defaut."""
    effs = (state.effects.by_unit.get(int(uid)) if state.effects is not None else None) or []
    return {e.effect_type for e in effs if not e.consumed}


def _port_active(state, uid) -> set:
    """EffectTypes ACTIFS -- flag `EffectComponent.IsActive` + `CreateActiveCondition`. C'est le
    pendant EXACT du canal `decisionView` par defaut (qui droppe les inactifs)."""
    if state.effects is None:
        return set()
    return {e.effect_type
            for e in state.effects.active_effects(int(uid), unit_state_for_effects(state, int(uid)))}


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


def _sentinel_case(sid, rid, victim_visual, expect_active):
    """Joue `SentinelDirectives` sur `victim_visual` et confronte LIVE et PORT sur les DEUX canaux.

    `expect_active` = l'effet 1065 doit-il etre ACTIF sur cette cible ? Il est POSE dans les deux
    cas (c'est le point du cas) ; seule l'activation depend du trait `TerminatorArmour`."""
    board, dv, ob, cs = _snapshot(sid, rid)
    bv = PR.units_by_visual(dv)
    if "admecDestroyer" not in bv or victim_visual not in bv:
        pytest.skip("roster incomplet: %s" % sorted(bv))
    caster, tgt = bv["admecDestroyer"]["id"], bv[victim_visual]["id"]
    if tgt not in PR.legal_from_here(sid, rid, caster, SENTINEL):
        pytest.skip("cible %s hors portee depuis la position courante" % victim_visual)

    # Degat NATIF que la cible peut infliger, AVANT la pose (reference du volet « aucun nombre ne
    # change »). La cible est un ENNEMI, donc c'est une MENACE sur mon caster.
    pre_min, pre_max = _threat_dmg(sid, rid, caster, tgt)

    st = load_state(dv, ob, cs, board=board)
    port_pre = normal_attack_per_hit_range(st, tgt)
    off = SentinelDirectivesAbility().execute_behaviour(st, caster, tgt)
    assert off is not None and off.get("dsl") is True
    port_post = normal_attack_per_hit_range(st, tgt)

    res = PR.cast(sid, rid, caster, tgt, SENTINEL)
    assert res.get("ok"), "cast live KO: %s" % str(res)[:200]
    dv_def = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 90)
    dv_all = PR.rpc(sid, "decisionView",
                    {"runnerId": rid, "allAbilities": True, "includeInactive": True}, 90)
    post_min, post_max = _threat_dmg(sid, rid, caster, tgt)

    live_def = _pinned_entry(dv_def, tgt) is not None
    live_all = _pinned_entry(dv_all, tgt)
    port_placed = bool(off.get("pinned_placed"))
    port_carried = PINNED in _port_carried(st, tgt)
    port_act = PINNED in _port_active(st, tgt)
    print("\n[sentinel %s] live def=%s all=%s(active=%s) | port placed=%s carried=%s active=%s"
          " | dmg live %s->%s port %s->%s (attendu actif=%s)"
          % (victim_visual, live_def, live_all is not None,
             None if live_all is None else live_all.get("active"),
             port_placed, port_carried, port_act, pre_max, post_max,
             (port_pre or {}).get("max"), (port_post or {}).get("max"), expect_active))

    # (1) l'effet EXISTE des deux cotes -- c'est ce que #224 avait rate.
    assert live_all is not None, "LIVE: 1065 absent MEME du canal includeInactive"
    assert port_placed is True, "PORT: la pose a ete abandonnee (gate d'immunite fantome ?)"
    assert port_carried is True, "PORT: aucune entite-effet 1065 sur la cible"
    # (2)/(3) ACTIVATION : port == live, canal par canal.
    assert bool(live_all.get("active")) is expect_active
    assert live_def is expect_active, "LIVE (canal actif-only): 1065=%s" % live_def
    assert port_act is expect_active, "PORT (active_effects): 1065=%s" % port_act
    # Volet CHIFFRE : x0.70 si actif, RIEN sinon -- live (predicteur natif) ET port.
    if pre_max and post_max is not None:
        exp = pre_max * PINNED_PCT if expect_active else pre_max
        assert abs(post_max - exp) <= max(1, 0.01 * exp), \
            "LIVE: degat de la cible %s -> %s (attendu ~%s)" % (pre_max, post_max, exp)
    if port_pre and port_post and port_pre.get("max"):
        exp = port_pre["max"] * PINNED_PCT if expect_active else port_pre["max"]
        assert abs(port_post["max"] - exp) <= max(1, 0.01 * exp), \
            "PORT: degat de la cible %s -> %s (attendu ~%s)" % (port_pre["max"], port_post["max"], exp)
    return st, tgt


# ------------------------------------------------------------------ (1)(2) pose inerte / active

def test_sentinel_pinned_inert_on_terminator_armour(sentinel_runner):
    """CRITERE DU CAS #208. Poseur INCONDITIONNEL sur une cible `TerminatorArmour` : l'effet EST
    cree (natif ET port) et ne change AUCUN nombre. La `CreateActiveCondition` le rend inerte ;
    le gate d'immunite, lui, n'a rien refuse."""
    sid, rid = sentinel_runner
    _sentinel_case(sid, rid, IMMUNE_VICTIM, expect_active=False)


def test_sentinel_pinned_active_without_terminator_armour(sentinel_runner):
    """CONTRE-CAS SYMETRIQUE (ce qui distingue une desactivation d'un no-op) : meme ability, cible
    SANS le trait -> effet ACTIF et x0.70 applique, live ET port."""
    sid, rid = sentinel_runner
    _sentinel_case(sid, rid, CONTROL_VICTIM, expect_active=True)


# ------------------------------------------------------------------ (3) montage de la MESURE #112

@pytest.mark.parametrize("victim,expect", [(IMMUNE_VICTIM, False), (CONTROL_VICTIM, True)])
def test_exemplar_of_hate_pinned_branch(da_runner, victim, expect):
    """`ExemplarOfHate` (1140) = le montage de la MESURE #112. Assertion BORNEE au volet `Pinned`,
    sur le canal ACTIF-ONLY des deux cotes (`decisionView` par defaut / `active_effects`) : la suite
    de la branche Chaos (override d'Attack + attaque libre) depend d'une election d'attaquant
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
    ExemplarOfHateAbility().execute_behaviour(st, caster, tgt)
    res = PR.cast(sid, rid, caster, tgt, EXEMPLAR)
    assert res.get("ok"), "cast live KO: %s" % str(res)[:200]
    dv2 = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 90)

    live = "Pinned" in _effect_groups(res) and _pinned_entry(dv2, tgt) is not None
    port = PINNED in _port_active(st, tgt)
    print("\n[exemplar %s] live=%s port=%s (attendu=%s)" % (victim, live, port, expect))
    assert live is expect, "LIVE: Pinned actif=%s, attendu %s" % (live, expect)
    assert port is expect, "PORT: Pinned actif=%s, attendu %s" % (port, expect)


# ------------------------------------------------------------------ (4) le gate d'immunite (offline)

def test_immunity_gate_is_the_immune_trait_only(sentinel_runner):
    """Le gate de POSE ne connait QUE `HasTrait(Immune) && CanBeImmuneTo`. Sur la cible
    `TerminatorArmour` (qui n'a PAS le trait `Immune`) il ne refuse RIEN -- ni `Pinned` ni
    `Stunned` -- et la pose aboutit dans les deux cas. C'est la MESURE 2026-07-28
    (`BaseEffect$$EntityIsImmuneToEffect` rend `false`, `HasTrait(cible, 0x19)` faux) : ces trois
    lignes verrouillaient AVANT #208 une approximation (le collapse de la `CreateActiveCondition`
    dans le gate d'immunite), elles verrouillent maintenant le mecanisme.
    Purement offline (aucun cast live) sur l'etat charge du runner -> zero effet de bord."""
    sid, rid = sentinel_runner
    board, dv, ob, cs = _snapshot(sid, rid)
    bv = PR.units_by_visual(dv)
    if IMMUNE_VICTIM not in bv or CONTROL_VICTIM not in bv:
        pytest.skip("roster incomplet: %s" % sorted(bv))
    immune, control = bv[IMMUNE_VICTIM]["id"], bv[CONTROL_VICTIM]["id"]
    st = load_state(dv, ob, cs, board=board)
    src = bv["admecDestroyer"]["id"]

    assert entity_is_immune_to_effect(st, immune, PINNED, name="Pinned") is False
    assert entity_is_immune_to_effect(st, immune, STUNNED, name="Stunned") is False
    assert entity_is_immune_to_effect(st, control, PINNED, name="Pinned") is False

    assert AddEffectOperation.execute(st, src, immune, PINNED, name="Pinned") is not None, \
        "IMMUNITE FANTOME : Pinned refuse sur une cible qui n'a PAS le trait Immune"
    assert AddEffectOperation.execute(st, src, immune, STUNNED, name="Stunned") is not None, \
        "SUR-IMMUNITE : Stunned refuse alors que CanBeImmuneTo est faux pour cet effet"
    assert AddEffectOperation.execute(st, src, control, PINNED, name="Pinned") is not None, \
        "SUR-IMMUNITE : Pinned refuse sur une cible sans TerminatorArmour"
    # ... et le Pinned pose sur la cible TerminatorArmour est INERTE (le point du cas).
    assert PINNED in _port_carried(st, immune)
    assert PINNED not in _port_active(st, immune)
    assert PINNED in _port_active(st, control)


# ------------------------------------------------------------------ (5) canal declaratif (pur)

def test_effect_def_channel_is_declarative():
    """`EffectFactory.effect_def` = mirror d'`EffectsDatabase.Get(effectType)` : le predicat vient de la
    CLASSE d'effet, jamais d'une liste de traits recablee par appelant.

      * base `BaseEffect$$EntityIsImmuneToEffect` = `HasTrait(Immune) && CanBeImmuneTo` ;
      * `get_CanBeImmuneTo` par defaut FAUX -> un effet non porte n'invente aucune immunite ;
      * `ContaminatedEffect$$EntityIsImmuneToEffect` = ContagionsOfNurgle | Mechanical | base ;
      * `PinnedEffect` n'a AUCUNE surcharge (`search_symbols_by_name EntityIsImmuneToEffect` = 2
        corps dans tout le binaire) -> `TerminatorArmour` ne l'immunise PAS ; c'est sa
        `CreateActiveCondition` (`is_active`) qui porte le « cannot be Suppressed »."""
    pinned = EffectFactory.effect_def(PINNED, "Pinned")
    contam = EffectFactory.effect_def(int(EffectType.Contaminated), EffectType.Contaminated.name)
    stunned = EffectFactory.effect_def(STUNNED, "Stunned")
    unknown = EffectFactory.effect_def(999999, "PasDeClassePortee")

    assert pinned.can_be_immune_to is True and contam.can_be_immune_to is True
    assert stunned.can_be_immune_to is False and unknown.can_be_immune_to is False

    tn = lambda *t: [UnitTrait(x).name for x in t]                                  # noqa: E731
    assert pinned.entity_is_immune_to_effect(tn(UnitTrait.TerminatorArmour)) is False
    assert pinned.entity_is_immune_to_effect(tn(UnitTrait.Immune)) is True
    assert pinned.entity_is_immune_to_effect(tn(UnitTrait.Chaos)) is False
    assert pinned.entity_is_immune_to_effect(None) is False                          # tuile / inconnu
    # `CreateActiveCondition` -- l'AUTRE etage, celui qui porte TerminatorArmour.
    assert pinned.is_active({"traits": tn(UnitTrait.TerminatorArmour)}) is False
    assert pinned.is_active({"traits": tn(UnitTrait.Chaos)}) is True

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


def test_active_effects_callers_pass_the_full_unit_state():
    """GARDE DE NON-REGRESSION #208 -- le trou qui obligeait au collapse.

    `BaseEffect.is_active(unit_state)` degrade en VRAI toute cle ABSENTE : un appelant qui construit
    un `{"hp": ...}` ad hoc rend ACTIF un effet dont la condition est FAUSSE (ici : le x0.70 de
    `Pinned` sur un porteur `TerminatorArmour`). Le contexte a donc UN SEUL constructeur --
    `runner.components.unit_state_for_effects` cote runner, `Scene.unit_state` cote prediction.
    Aucun appelant d'`active_effects` dans `engine/` ne doit passer autre chose."""
    import pathlib
    import re
    import engine
    root = pathlib.Path(engine.__file__).resolve().parent
    assert root.is_dir(), "arborescence engine/ introuvable: %s" % root
    # `[^)]*?` ne franchit pas une parenthese fermante : un appel qui DELEGUE
    # (`active_effects(uid, unit_state_for_effects(state, uid))`) ne matche pas ; seul un dict
    # LITTERAL en argument matche.
    call = re.compile(r"active_effects\(\s*[^)]*?\{", re.S)
    bad = []
    for p in sorted(root.rglob("*.py")):
        txt = p.read_text(encoding="utf-8")
        for m in call.finditer(txt):
            bad.append("%s: %s" % (p.name, txt[m.start():m.start() + 110].replace("\n", " ")))
    assert not bad, "unit_state ad hoc (dict litteral) passe a active_effects :\n" + "\n".join(bad)
