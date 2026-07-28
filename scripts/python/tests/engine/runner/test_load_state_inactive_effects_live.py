"""#219 -- `load_state` SEEDE-T-IL les effets POSES mais INERTES ?

Residu nomme de #208 (`docs/rl/case-224-effect-immunity-gate.md` SS 6, « ce qui n'est PAS couvert »
(a)) : un `Pinned` inerte ne pouvait PAS arriver par `load_state`, parce que la capture
`decisionView` par DEFAUT droppe les effets dont `EffectComponent.IsActive @+0x5c` est faux
(`readEffectsByUnit`, `frida/hooks/game/effects.ts`). Seule la pose OFFLINE l'exercait -- donc tout
etat charge mi-bataille perdait ces entites-effet, alors que le natif les a.

Ce qui est livre et verrouille ici :

  * `snapshot.decision_view_seed_body(rid, ...)` -- la porte NOMMEE du canal `includeInactive`,
    a passer au RPC `decisionView` quand la capture alimente `load_state` ;
  * `EffectFactory.create` lit desormais la cle `active` du capte -> le flag natif atterrit sur
    l'instance `BaseEffect`. Cle absente (canal par defaut, pose offline) -> True, inchange.

CORRESPONDANCE PRESERVEE (la regle de #208, et le coeur de ces tests) :

    canal `decisionView` par DEFAUT      ==  port `EffectsState.active_effects`
    canal `decisionView includeInactive` ==  port `EffectsState.by_unit`

Autrement dit : seeder par le canal large fait ENTRER l'effet inerte dans `by_unit` (donc
`has_effect` le voit, et les `Triggered()` qui pilotent son flag ont une instance a re-activer) SANS
le faire remonter dans `active_effects` -- donc sans deplacer le moindre nombre. C'est cette derniere
moitie qui compte : si elle sautait, le x0.70 fantome de `PinnedEffect$$
CreateEffectDamageBonusForAttack` reviendrait.

MESURE 2026-07-28 (`probe_219_seed_inactive_effects.py`, runner MC1_67, poseur INCONDITIONNEL
`SentinelDirectives` 1139 sur `admecDestroyer`) :

    cible blackAbaddon (TerminatorArmour) : seed defaut    -> by_unit 1065 ABSENT
                                            seed inactive  -> by_unit 1065 PRESENT (active=False),
                                                              active_effects 1065 ABSENT
                                            plage d'attaque de la cible 1808 -> 1808 (identique)
    cible blackPossession (controle)      : 1065 PRESENT et ACTIF dans les DEUX seeds, plage 1351

COUT du canal (`--cost`) : +909 octets / +3,84 % / +6 entrees d'effet a t0 sur un 5v5 ;
+435 octets / +2,33 % / +3 entrees apres un tour d'IA.

ASCII only. Dispose SES runners.
"""
from __future__ import annotations

import pytest

import probe_112_darkangels as PR
import probe_224_effect_immunity as IM
from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.effect_type import EffectType
from engine.entities.effects import EffectFactory
from engine.entities.pathfinding.board import Board
from engine.runner.components import (OwnerComponent, PositionComponent, UnitComponent,
                                      unit_state_for_effects)
from engine.runner.damage_model import normal_attack_per_hit_range
from engine.runner.operations.triggers.base import TriggerEvent
from engine.runner.operations.triggers.dispatch.core import collect_effect_triggers
from engine.runner.operations.triggers.dispatch.turn import tile_tick_triggers
from engine.runner.snapshot import decision_view_seed_body, load_state, snapshot, snapshot_live, diff

SENTINEL = 1139
PINNED = int(EffectType.Pinned)
OVERWATCH = int(EffectType.Overwatch_AutoAttack)
PINNER = "admecDestroyer"
INERT_VICTIM, CONTROL_VICTIM = "blackAbaddon", "blackPossession"


# ------------------------------------------------------------------ helpers

def _dv(sid, rid, *, seed_channel: bool):
    body = (decision_view_seed_body(rid, allAbilities=True, maxRank=1) if seed_channel
            else {"runnerId": rid, "allAbilities": True, "maxRank": 1})
    return PR.rpc(sid, "decisionView", body, 90)


def _rest(sid, rid):
    bg = PR.rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    return (Board(bg["tiles"], adjacency="native_sym"),
            PR.rpc(sid, "observeBattle", {"runnerId": rid}, 40),
            PR.rpc(sid, "combatSnapshot", {"runnerId": rid}, 60))


def _entry(dv, uid, effect_type):
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    for e in ((u or {}).get("effects") or []):
        if int(e.get("effectType") or -1) == int(effect_type):
            return e
    return None


def _carried(state, uid) -> dict:
    """`{effectType: instance}` PORTES (entite-effet existante) -- pendant de `includeInactive`."""
    effs = (state.effects.by_unit.get(int(uid)) if state.effects is not None else None) or []
    return {int(e.effect_type): e for e in effs if not e.consumed and e.effect_type is not None}


def _active(state, uid) -> set:
    """EffectTypes ACTIFS -- pendant du canal `decisionView` par defaut."""
    if state.effects is None:
        return set()
    return {e.effect_type for e in
            state.effects.active_effects(int(uid), unit_state_for_effects(state, int(uid)))}


def _team_player(state, uid):
    e = state.get_entity(int(uid))
    oc = e.get_component(OwnerComponent) if e is not None else None
    return (None, None) if oc is None else (oc.team, oc.player)


def _enemy_player_of(state, uid):
    """L'id de JOUEUR d'un camp adverse a `uid` (le `player_id` que porte l'event turn-start)."""
    team, _ = _team_player(state, uid)
    for eid in state.entities:
        t, p = _team_player(state, eid)
        if t is not None and team is not None and t != team and p is not None:
            return int(p)
    return None


def _an_enemy_of(state, uid):
    team, _ = _team_player(state, uid)
    for eid, e in state.entities.items():
        t, _p = _team_player(state, eid)
        uc = e.get_component(UnitComponent)
        if (t is not None and team is not None and t != team and uc is not None and uc.alive
                and e.get_component(PositionComponent) is not None):
            return int(eid)
    return None


def _place_adjacent(state, mover, anchor, board) -> None:
    """DEPLACE `mover` sur une tuile voisine d'`anchor` (doctrine : on impose la geometrie du
    scenario, on ne la subit pas). No-op si l'ancre n'a pas de position ou si aucune voisine."""
    ae = state.get_entity(int(anchor))
    me = state.get_entity(int(mover))
    ap = ae.get_component(PositionComponent) if ae is not None else None
    mp = me.get_component(PositionComponent) if me is not None else None
    if ap is None or mp is None:
        return
    tid = board.id_at(ap.col, ap.row)
    for nb in (board.neighbours(tid) if tid is not None else []):
        t = board.by_id.get(nb) or {}
        if t.get("col") is not None:
            mp.col, mp.row = t["col"], t["row"]
            return


@pytest.fixture(scope="module")
def pinned_case(live_session):
    """UN seul runner pour tout le fichier : `admecDestroyer` pose `SentinelDirectives` (Pinned
    INCONDITIONNEL) sur la cible `TerminatorArmour`, PUIS on capture les deux canaux et on charge un
    etat par canal. Le cast est LIVE (l'inertie doit venir du JEU, pas d'une pose offline)."""
    sid = live_session
    rid = IM._build_custom(sid, [PINNER], [INERT_VICTIM, CONTROL_VICTIM])
    try:
        dv0 = _dv(sid, rid, seed_channel=False)
        bv = PR.units_by_visual(dv0)
        for v in (PINNER, INERT_VICTIM, CONTROL_VICTIM):
            if v not in bv:
                pytest.skip("roster incomplet: %s" % sorted(bv))
        caster = bv[PINNER]["id"]
        legal = PR.legal_from_here(sid, rid, caster, SENTINEL)
        tgts = {v: bv[v]["id"] for v in (INERT_VICTIM, CONTROL_VICTIM)}
        for v, uid in tgts.items():
            if uid not in legal:
                pytest.skip("cible %s hors portee depuis la position courante" % v)
            res = PR.cast(sid, rid, caster, uid, SENTINEL)
            assert res.get("ok"), "cast live KO sur %s: %s" % (v, str(res)[:200])
            # Le caster a consomme son activation ; on relit la legalite pour la cible suivante.
            legal = PR.legal_from_here(sid, rid, caster, SENTINEL)

        board, ob, cs = _rest(sid, rid)
        dv_def = _dv(sid, rid, seed_channel=False)
        dv_all = _dv(sid, rid, seed_channel=True)
        yield {"sid": sid, "rid": rid, "caster": caster, "tgt": tgts,
               "dv_def": dv_def, "dv_all": dv_all, "ob": ob, "cs": cs, "board": board,
               "st_def": load_state(dv_def, ob, cs, board=board),
               "st_all": load_state(dv_all, ob, cs, board=board)}
    finally:
        PR.dispose(sid, rid)


# ------------------------------------------------------------------ le CRITERE

def test_live_publishes_the_inert_effect_only_on_the_wide_channel(pinned_case):
    """PREMISSE (elle doit tenir, sinon les tests suivants ne mesurent rien) : le jeu POSE bien
    l'effet sur la cible `TerminatorArmour` et le laisse INERTE -- il n'apparait QUE sous
    `includeInactive`, avec `active: false`. Sur la cible de controle il est ACTIF dans les DEUX
    canaux : c'est ce contraste qui distingue « inerte » de « pas pose »."""
    c = pinned_case
    inert, ctrl = c["tgt"][INERT_VICTIM], c["tgt"][CONTROL_VICTIM]
    assert _entry(c["dv_def"], inert, PINNED) is None, "le canal par defaut publie un effet INERTE"
    e_all = _entry(c["dv_all"], inert, PINNED)
    assert e_all is not None, "1065 absent MEME du canal includeInactive (rien n'a ete pose)"
    assert e_all.get("active") is False
    assert _entry(c["dv_def"], ctrl, PINNED) is not None
    assert (_entry(c["dv_all"], ctrl, PINNED) or {}).get("active") is True


def test_load_state_seeds_the_inert_effect_with_its_flag(pinned_case):
    """LE CRITERE #219. Etat charge depuis le canal `includeInactive` : l'entite-effet 1065 EXISTE
    sur la cible (`by_unit`) et porte `active is False` -- le flag natif, pas une deduction."""
    c = pinned_case
    inert = c["tgt"][INERT_VICTIM]
    inst = _carried(c["st_all"], inert).get(PINNED)
    assert inst is not None, "seed(includeInactive): aucune entite-effet 1065 -- le canal n'a pas seede"
    assert inst.active is False, "seed(includeInactive): 1065 seede ACTIF -- le flag n'est pas lu"
    assert c["st_all"].effects.has_effect(inert, effect_type=PINNED) is True


def test_the_inert_effect_stays_out_of_active_effects(pinned_case):
    """LA MOITIE QUI COMPTE : entrer dans `by_unit` ne doit PAS faire entrer dans `active_effects`.
    Si cette assertion tombe, le x0.70 fantome de `PinnedEffect` est de retour."""
    c = pinned_case
    inert, ctrl = c["tgt"][INERT_VICTIM], c["tgt"][CONTROL_VICTIM]
    assert PINNED not in _active(c["st_all"], inert)
    # CONTRE-CAS : sur la cible sans `TerminatorArmour` le meme seed rend l'effet ACTIF.
    assert PINNED in _carried(c["st_all"], ctrl)
    assert _carried(c["st_all"], ctrl)[PINNED].active is True
    assert PINNED in _active(c["st_all"], ctrl)


def test_the_wide_channel_moves_no_number(pinned_case):
    """NON-REGRESSION CHIFFREE : le seed large ne deplace AUCUN nombre. La plage d'attaque normale
    des DEUX cibles est identique entre l'etat seede par le canal par defaut et celui seede par
    `includeInactive` -- y compris sur la cible de controle, ou le x0.70 est present des deux
    cotes (les deux canaux publient l'instance ACTIVE)."""
    c = pinned_case
    for v, uid in c["tgt"].items():
        a = normal_attack_per_hit_range(c["st_def"], uid) or {}
        b = normal_attack_per_hit_range(c["st_all"], uid) or {}
        assert (a.get("min"), a.get("max")) == (b.get("min"), b.get("max")), \
            "%s: plage %s -> %s selon le canal de seed" % (v, (a.get("min"), a.get("max")),
                                                           (b.get("min"), b.get("max")))


def test_name_view_and_diff_are_channel_independent(pinned_case):
    """La vue NOMS (`EffectsOwnedComponent`) reste ACTIVE-ONLY quel que soit le canal -> un
    `diff(snapshot_live(...), snapshot(state))` dont les deux cotes n'ont pas ete captes par le MEME
    canal ne signale AUCUN ecart fantome. C'est ce qui rend la porte de seed utilisable partout."""
    c = pinned_case
    s_def, s_all = snapshot(c["st_def"]), snapshot(c["st_all"])
    assert {u: r["effects"] for u, r in s_def["units"].items()} \
        == {u: r["effects"] for u, r in s_all["units"].items()}
    # croise : live capte par le canal LARGE vs etat seede par le canal PAR DEFAUT, et l'inverse.
    assert diff(snapshot_live(c["dv_all"], c["ob"]), s_def) == []
    assert diff(snapshot_live(c["dv_def"], c["ob"]), s_all) == []


# ------------------------------------------------------------------ le mecanisme, pur

# ------------------------------------------------------------------ GENERALISATION : 2e famille

@pytest.fixture(scope="module")
def overwatch_case(live_session):
    """SECONDE famille d'effet, SECOND observable, AUCUN cast : sur une bataille 5v5 FRAICHE, les
    unites du camp COURANT portent `Overwatch_AutoAttack` (1009) DESACTIVE -- c'est le 2e
    `Triggered()` de `IdunBattle.Entities.Effects.RangedAutoAttackEffect$$
    CreateHandleTriggerAbilitiesInternal` (`On(0x12) & IsTurnOf(owner) -> DeactivateEffect`). Le
    canal par defaut les droppe, donc l'etat charge n'a AUCUNE instance a re-activer."""
    sid = live_session
    rid = PR.build(sid)
    try:
        board, ob, cs = _rest(sid, rid)
        dv_def, dv_all = _dv(sid, rid, seed_channel=False), _dv(sid, rid, seed_channel=True)
        owners = [u["id"] for u in (dv_all.get("units") or [])
                  if any(int(e.get("effectType") or -1) == OVERWATCH and e.get("active") is False
                         for e in (u.get("effects") or []))]
        if not owners:
            pytest.skip("aucun overwatch INACTIF dans cette bataille")
        yield {"sid": sid, "rid": rid, "owners": owners, "dv_def": dv_def, "dv_all": dv_all,
               "st_def": load_state(dv_def, ob, cs, board=board),
               "st_all": load_state(dv_all, ob, cs, board=board), "board": board}
    finally:
        PR.dispose(sid, rid)


def test_inactive_overwatch_is_seeded_only_by_the_wide_channel(overwatch_case):
    """Meme dichotomie que `Pinned`, sur un effet que PERSONNE n'a caste : l'instance 1009 desactivee
    existe cote natif, elle n'entre dans `by_unit` que par le canal large."""
    c = overwatch_case
    for uid in c["owners"]:
        assert OVERWATCH not in _carried(c["st_def"], uid), \
            "u%s: le canal par defaut a seede un overwatch INACTIF" % uid
        inst = _carried(c["st_all"], uid).get(OVERWATCH)
        assert inst is not None and inst.active is False
        # LA CORRESPONDANCE, sur un effet dont l'activite est PUREMENT le FLAG (1009 n'a pas de
        # `CreateActiveCondition` : contrairement a `Pinned`, rien d'autre ne peut le rattraper).
        # `by_unit` le porte, `active_effects` l'exclut -- exactement les deux canaux live.
        assert OVERWATCH not in _active(c["st_all"], uid), \
            "u%s: overwatch INACTIF remonte dans active_effects (le flag n'est pas lu)" % uid


def test_the_seeded_instance_is_what_the_turn_start_trigger_reactivates(overwatch_case):
    """L'OBSERVABLE qui change. `RangedAutoAttackActivateOnTurnStart` (1er `Triggered()` de
    l'`ArraySet`) n'agit que sur une INSTANCE : sans seed, `collect_effect_triggers` n'en instancie
    AUCUNE pour 1009 et l'overwatch d'une unite capturee desarmee ne peut PLUS JAMAIS s'armer dans
    l'etat charge. Avec le seed, le tick `On(0x12)` du tour ADVERSE le re-arme, comme le natif."""
    c = overwatch_case
    uid = c["owners"][0]
    enemy_player = _enemy_player_of(c["st_all"], uid)
    if enemy_player is None:
        pytest.skip("aucun joueur adverse identifiable")

    # AVANT : rien a re-activer cote seed par defaut -- meme pas un trigger dans le registre.
    assert not [t for t in collect_effect_triggers(c["st_def"])
                if t.effect_type == OVERWATCH and int(t.owner_id) == int(uid)]
    assert [t for t in collect_effect_triggers(c["st_all"])
            if t.effect_type == OVERWATCH and int(t.owner_id) == int(uid)]

    for st in (c["st_def"], c["st_all"]):
        st.current_player_id = enemy_player          # le tour passe a l'ADVERSAIRE -> On(0x12) arme
        tile_tick_triggers(st)
    assert OVERWATCH not in _carried(c["st_def"], uid)                 # toujours rien
    assert _carried(c["st_all"], uid)[OVERWATCH].active is True, \
        "l'instance seedee n'a pas ete re-activee par le tick de tour adverse"
    assert OVERWATCH in _active(c["st_all"], uid)      # ... et elle remonte MAINTENANT dans les actifs


def test_the_reactivated_overwatch_actually_gates_a_shot(overwatch_case):
    """Bout de chaine : une fois re-arme, le trigger de TIR MATCHE sur un ennemi qui vient de bouger
    a portee -- la ou l'etat seede par le canal par defaut n'a AUCUN trigger a evaluer. On DEPLACE
    l'ennemi au contact (on ne subit pas la geometrie de spawn)."""
    c = overwatch_case
    uid = c["owners"][0]
    enemy_player = _enemy_player_of(c["st_all"], uid)
    if enemy_player is None:
        pytest.skip("aucun joueur adverse identifiable")
    mover = _an_enemy_of(c["st_all"], uid)
    if mover is None:
        pytest.skip("aucun ennemi vivant a deplacer")

    for st in (c["st_def"], c["st_all"]):
        st.current_player_id = enemy_player
        tile_tick_triggers(st)
        _place_adjacent(st, mover, uid, c["board"])

    ev = TriggerEvent(int(EventTriggerType.UnitAfterMove), mover, uid, ranged=False, profile=None)
    fired_all = [t for t in collect_effect_triggers(c["st_all"])
                 if t.effect_type == OVERWATCH and int(t.owner_id) == int(uid)
                 and t.event_id == ev.event_id and t.matches(c["st_all"], ev)]
    fired_def = [t for t in collect_effect_triggers(c["st_def"])
                 if t.effect_type == OVERWATCH and int(t.owner_id) == int(uid)
                 and t.event_id == ev.event_id and t.matches(c["st_def"], ev)]
    assert fired_all, "overwatch re-arme mais le trigger de tir ne matche pas"
    assert not fired_def, "l'etat seede par le canal par defaut ne devrait avoir AUCUN trigger 1009"


# ------------------------------------------------------------------ le mecanisme, pur

def test_effect_factory_reads_the_active_flag():
    """`EffectFactory.create` -- foyer UNIQUE de materialisation (unites, MoW, tuiles, pose offline).
    Cle `active` absente -> True (canal par defaut : « present == actif » ; et pose offline, ou le
    natif cree l'entite-effet ACTIVE et delegue l'inertie a `CreateActiveCondition`)."""
    cap = {"name": "Pinned", "effectType": PINNED, "level": 1, "remaining": 0, "source": 1}
    assert EffectFactory.create(cap).active is True
    assert EffectFactory.create({**cap, "active": True}).active is True
    assert EffectFactory.create({**cap, "active": False}).active is False


def test_seed_body_is_the_named_door():
    """La porte est NOMMEE et greppable : elle pose `includeInactive` et laisse passer le reste."""
    b = decision_view_seed_body(42, allAbilities=True, maxRank=3)
    assert b == {"runnerId": 42, "includeInactive": True, "allAbilities": True, "maxRank": 3}
