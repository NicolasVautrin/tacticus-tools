"""#366-r1 -- `1255 MartialSuperiority_Visual`, le MARQUEUR « riposte armee » du passif
`MartialSuperiority` (1092) de `templChampion` (<< Brother Jaeger >>).

RE + residus : `engine/entities/effects/loki/martial_superiority.py`. Montage :
`scripts/python/probe_366_r1_martial_superiority_visual.py`.

POURQUOI CES GARDES-LA. Cet effet n'a AUCUNE contribution (ni degat, ni stat, ni coups, ni
evenement) : sa SEULE semantique native est sa condition,

    IdunBattle.Entities.Effects.Loki.MartialSuperiority_VisualEffect$$CreateActiveCondition
        = op_LogicalNot( <DSLTriggers+0x28> )        # = NOT IsTurnOf(Owner)

Un test « comportemental » serait donc VERT pour « effet present et inerte » comme pour « effet
ABSENT » -- exactement le faux positif que ce gisement paie. Ce fichier lit a la place la VALEUR DE
RETOUR de la condition la ou le natif la publie : le flag `EffectComponent.IsActive @+0x5c`, rendu
entree par entree par `readEffectsByUnit` (les entrees `false` n'etant publiees que sous
`includeInactive`), et il l'exige sur TROIS dates consecutives (porteur / adverse / porteur) pour
que « suit la condition » ne puisse pas etre confondu avec « fige a la capture ».

⚠ Le nom « Visual » n'est PAS un argument, et ne l'a jamais ete : la condition est un predicat REEL.
Ce qui rend l'effet sans effet de bord, c'est une mesure INDEPENDANTE -- aucun site du binaire ne
charge l'immediat 0x4e7 hors des sites d'ENREGISTREMENT, et aucun poids `MartialSuperiority*`
n'existe dans `BC.Utilities`. Le port est donc de FIDELITE : le flag de l'instance suit la condition
native au lieu de rester `True` inconditionnellement.

Lit l'etat LIVE (rien de hardcode). ASCII only.
"""
from __future__ import annotations

import pytest

from engine.entities.effect_type import EffectType
from engine.entities.effects.base import BaseEffect
from engine.entities.effects.factory import EFFECT_CLASSES
from engine.entities.effects.loki.martial_superiority import MartialSuperiorityVisualEffect
from engine.runner.components import unit_state_for_effects
from engine.runner.operations.refresh_effects import refresh_stat_modifier_effects
from engine.runner.snapshot import decision_view_seed_body, load_state

CARRIER = "templChampion"          # Brother Jaeger -- HERO au pool, porteur du passif 1092
FOE = "orksNob"
VISUAL = int(EffectType.MartialSuperiority_Visual)      # 0x4e7 = 1255


def _row(dv, uid):
    return next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)


def _alive(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _eff(u, etype):
    return next((e for e in ((u or {}).get("effects") or []) if e.get("effectType") == etype), None)


@pytest.fixture(scope="module")
def ms_visual(build_runner, rpc):
    """Duel 1v1 Jaeger vs `orksNob`. Echantillonne le NATIF sur TROIS dates (tour du porteur, tour
    adverse, retour au porteur) sur les DEUX canaux, puis charge l'etat pour le PORT.

    Un echec de MONTAGE ASSERTE (jamais un skip vert) : sans Jaeger ou sans instance 1255, il n'y a
    rien a confronter et le taire rendrait le fichier decoratif."""
    b = build_runner("777", extra=["--roster", "1", "--p-units", CARRIER, "--a-units", FOE,
                                   "--hp-player", "999999", "--hp-target", "999999"])
    rid = b["rid"]

    def dview(inactive):
        return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                                    "includeInactive": bool(inactive)}, 120)

    dv0 = dview(True)
    j = _alive(dv0, CARRIER)
    assert j is not None, f"{CARRIER} absent du runner -- montage KO"
    jid, owner = j["id"], j.get("owner")
    assert _eff(_row(dv0, jid), VISUAL) is not None, (
        "aucune instance 1255 sur le porteur : le poseur `MartialSuperiorityAddEffectAbility` "
        "n'aurait rien pose -- montage (ou reachability) KO, rien a confronter")

    def endturn():
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)

    def goto(want_owner_turn):
        for _ in range(8):
            dv = dview(True)
            if (dv.get("currentPlayer") == owner) is bool(want_owner_turn):
                return
            endturn()
        raise AssertionError("impossible d'atteindre la date voulue en 8 fins de tour")

    def sample():
        dvi, dvd = dview(True), dview(False)
        e = _eff(_row(dvi, jid), VISUAL)
        assert e is not None, "l'instance 1255 a disparu du canal includeInactive en cours de mesure"
        return {"active": bool(e.get("active")),
                "in_default": _eff(_row(dvd, jid), VISUAL) is not None}

    goto(True)
    own = sample()
    goto(False)
    foe = sample()
    goto(True)
    back = sample()

    goto(True)
    dvs = rpc("decisionView", decision_view_seed_body(rid, maxRank=1, allAbilities=True), 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    foes = sorted(o for o in {u.get("owner") for u in (dvs.get("units") or [])}
                  if o is not None and o != owner)
    assert foes, "aucun autre joueur dans la capture -- montage KO"
    return {"rid": rid, "jid": jid, "owner": owner, "foe_player": foes[0],
            "own": own, "foe": foe, "back": back,
            "dv": dvs, "ob": ob, "snap": snap}


def _port_state(c):
    st = load_state(c["dv"], c["ob"], c["snap"])
    inst = next((e for e in (st.effects.by_unit.get(c["jid"]) or [])
                 if int(e.effect_type or 0) == VISUAL), None)
    return st, inst


def _port_at(st, inst, jid, player):
    """Le port a la date « c'est le tour de `player` ». `refresh_stat_modifier_effects` est
    LITTERALEMENT la ligne que `runner/operations/turnflow.py` joue au StartTurn pour
    `RefreshEffectTrigger.TurnChanged` -> `IdunBattle.Operations.RefreshEffectsOperation$$Execute`
    avec `effectEntity` NUL : c'est le producteur du flag offline."""
    st.current_player_id = player
    cond = bool(inst.is_active(unit_state_for_effects(st, jid)))
    refresh_stat_modifier_effects(st)
    us = unit_state_for_effects(st, jid)
    return {"cond": cond, "active": bool(inst.active),
            "in_default": VISUAL in [int(e.effect_type or 0)
                                     for e in st.effects.active_effects(jid, us)]}


def test_visual_marker_is_posed_and_routed_to_the_ported_class(ms_visual):
    """REACHABILITY + ROUTAGE. Le poseur `MartialSuperiorityAddEffectAbility` n'a AUCUNE ligne dans
    les deux tables de symboles (dedup par adresse) : que l'instance existe en bataille est une
    MESURE, pas une deduction. Et le registre doit la router sur la classe PORTEE, sinon
    `BaseEffect.is_active` rend `True` inconditionnellement."""
    _st, inst = _port_state(ms_visual)
    assert inst is not None, "le port n'a charge aucune instance 1255 depuis la capture live"
    assert isinstance(inst, MartialSuperiorityVisualEffect), (
        f"instance routee sur {type(inst).__name__} -- `EFFECT_CLASSES` ne connait pas "
        "`MartialSuperiority_Visual`")
    assert EFFECT_CLASSES.get("MartialSuperiority_Visual") is MartialSuperiorityVisualEffect


def test_native_flag_follows_not_is_turn_of_owner(ms_visual):
    """NATIF, trois dates. `active` doit valoir FAUX / VRAI / FAUX -- le retour au FAUX est ce qui
    separe « suit la condition » de « fige a la capture ». Et le canal par DEFAUT (actifs seuls) doit
    suivre : l'entree y est ABSENTE pendant le tour du porteur, PRESENTE pendant le tour adverse."""
    c = ms_visual
    assert c["own"]["active"] is False, (
        "1255 est ACTIF pendant le tour de son porteur -- la condition ne serait pas "
        "`NOT IsTurnOf(Owner)`")
    assert c["foe"]["active"] is True, "1255 est INACTIF pendant le tour adverse"
    assert c["back"]["active"] is False, (
        "1255 reste ACTIF apres retour au tour du porteur -- le flag serait fige, pas re-evalue")
    assert c["own"]["in_default"] is False and c["back"]["in_default"] is False, (
        "le canal par DEFAUT publie 1255 pendant le tour du porteur alors que son flag est faux")
    assert c["foe"]["in_default"] is True, (
        "le canal par DEFAUT ne publie pas 1255 pendant le tour adverse alors que son flag est vrai")


def test_port_reproduces_the_native_on_the_three_dates(ms_visual):
    """PORT vs NATIF sur la MEME capture : condition, flag ECRIT par le driver de refresh, et
    publication dans `EffectsState.active_effects` (le pendant exact du canal par defaut)."""
    c = ms_visual
    st, inst = _port_state(c)
    assert inst is not None, "aucune instance 1255 chargee"
    got = [_port_at(st, inst, c["jid"], c["owner"]),
           _port_at(st, inst, c["jid"], c["foe_player"]),
           _port_at(st, inst, c["jid"], c["owner"])]
    want = [c["own"], c["foe"], c["back"]]
    for lbl, g, w in zip(("porteur", "adverse", "retour porteur"), got, want):
        assert g["active"] is w["active"], (
            f"[{lbl}] flag port={g['active']} != live={w['active']}")
        assert g["in_default"] is w["in_default"], (
            f"[{lbl}] publication port={g['in_default']} != live={w['in_default']}")
    assert [g["cond"] for g in got] == [False, True, False], (
        "`is_active` ne mirrore pas `NOT IsTurnOf(Owner)` sur les trois dates")


def test_unported_class_would_publish_the_halo_during_the_owner_turn(ms_visual):
    """CONTRE-EPREUVE -- le regime MORD. Le MEME effet capte, route sur `BaseEffect` (l'etat du port
    AVANT ce cas) : `BaseEffect.is_active` rend `True` INCONDITIONNELLEMENT, donc le halo « riposte
    armee » serait publie pendant le tour de Jaeger, la ou le natif l'eteint. Sans cette garde, le
    test precedent pourrait passer pour une raison qui n'a rien a voir avec le port."""
    c = ms_visual
    st, _inst = _port_state(c)
    st.current_player_id = c["owner"]
    us = unit_state_for_effects(st, c["jid"])
    naked = BaseEffect(name="MartialSuperiority_Visual", effect_type=VISUAL, active=True)
    assert naked.is_active(us) is True, (
        "`BaseEffect.is_active` ne rend plus le defaut True -- la contre-epreuve ne mesure plus rien")
    assert MartialSuperiorityVisualEffect(
        name="MartialSuperiority_Visual", effect_type=VISUAL, active=True).is_active(us) is False


def test_missing_turn_key_degrades_to_active_offline():
    """DEGRADATION FIDELE (offline pur) : `is_turn_of_owner` ABSENT du `unit_state` = « non mesure »
    -> la condition rend VRAI. On ne masque pas l'effet a tort -- meme regime que les autres
    `CreateActiveCondition` portees (`AnvilShield`, `VisionsOfHeresy`, `PowerTrip`...)."""
    e = MartialSuperiorityVisualEffect(name="MartialSuperiority_Visual", effect_type=VISUAL)
    assert e.is_active({}) is True
    assert e.is_active(None) is True
    assert e.is_active({"is_turn_of_owner": None}) is True
    assert e.is_active({"is_turn_of_owner": True}) is False
    assert e.is_active({"is_turn_of_owner": False}) is True
