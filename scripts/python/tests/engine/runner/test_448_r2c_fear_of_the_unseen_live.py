"""GARDE LIVE #448-r2c tranche 2/4 -- `1238 FearOfTheUnseen_TeleportingIn` : le port et le NATIF,
sur le MEME etat de depart, sur le REGIME NUMERIQUE que 1238 est seul a porter.

    IdunBattle.Entities.Effects.Loki.FearOfTheUnseen_TeleportingInEffect$$GetAdditionalRemoveTriggers
        = AmountIsEqual( EffectRemainingTurns(EffectSelf), Direct(1) )

C'est la SEULE surcharge du vslot 0x738 dans ce build, et ce vslot conditionne les QUATRE
`Triggered()` d'`ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal` -- T4 (la pose du
marqueur `1241 FearOfTheUnseen_Moving`) COMPRIS.

MONTAGE, decouvert a la MESURE et non devine : `tyranDeathleaper` porte le trait `TeleportStrike`,
donc il ARRIVE sous `1035 TeleportStrike_TeleportingIn` -- et
`FearOfTheUnseenAbility$$GetDynamicInvalidCasterReason` = `IsTeleporting(caster) ? 4 : 0` fait
REFUSER le cast au natif tant qu'il descend. Il faut donc l'ATTERRIR d'abord, et **sans le faire
bouger** (son masque porte `CasterHasNotMoved`) : le seul geste qui convienne est `FinishUnitTurn`
(T3 de la tranche 1), suivi de deux `endturn` pour lui rendre la main.

CE QUI REGRESSERAIT SANS CETTE GARDE : collapser le vslot a `True` (le corps de BASE, celui des
trois soeurs) fait retirer 1238 par le `FinishUnitTurn` que
`ActiveAbilityOperation$$AddFlagsAfterAbilityExecution` enchaine DANS LA MEME TRANSACTION que le
cast. Le Deathleaper ne disparaitrait JAMAIS -- ni pour le tour adverse, ni pour son propre tour
suivant. Aucune erreur, aucun crash : degradation PERMISSIVE et muette. CHIFFRE de la
contre-epreuve (`probe_448_r2c_fear_of_the_unseen.py --mutate`, 2 couples) : le port mute rend
`remaining = {1239: 3}` la ou le natif rend `{1238: 3, 1239: 3}`.

⚠ CE QUE LA CONTRE-EPREUVE APPREND SUR CETTE GARDE, et qu'un mainteneur doit savoir : en collapsant
le vslot, **UN SEUL** des quatre tests de ce module rougit -- `test_the_cast_poses_1238_...`. Les
trois autres restent VERTS, et c'est STRUCTUREL : ils rechargent l'etat depuis le NATIF a chaque
etape, donc le port y HERITE d'un 1238 pose par le jeu et se contente de le decrementer ou de le
retirer a 1. Seul le test du cast rejoue la POSE et le RETRAIT dans la meme transaction.
=> **ne pas supprimer ni affaiblir ce test-la en croyant les autres redondants** : ils mesurent la
chronologie, lui seul mesure la survie. Le pendant OFFLINE
(`test_448_r2c_fear_of_the_unseen_offline.py`), lui, rougit sur 15 tests.

RE : `docs/rl/case-448-r2c-fear-of-the-unseen-teleporting-in.md`.
Confrontation complete (2 couples board/seed + contre-epreuve) :
`python scripts/python/probe_448_r2c_fear_of_the_unseen.py`. ASCII only.
"""
from __future__ import annotations

import pytest

from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.runner.components import UnitComponent, get_unit_feet
from engine.runner.events import EventBus
from engine.runner.messages import (ActiveAbilityMessage, EndTurnMessage,
                                    FinishUnitTurnMessage, MoveUnitMessage)
from engine.runner.operations.movement import MoveUnitOperation
from engine.runner.operations.triggers import after_move_triggers
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

P_UNITS = "tyranDeathleaper,tyranNeurothrope,tyranTyrantGuard"
TELEPORTING_IN = int(EffectType.FearOfTheUnseen_TeleportingIn)   # 1238
MOVING = int(EffectType.FearOfTheUnseen_Moving)                  # 1241
EXTRA_DAMAGE = int(EffectType.FearOfTheUnseen_ExtraDamage)       # 1239
TELEPORT_STRIKE_IN = int(EffectType.TeleportStrike_TeleportingIn)  # 1035 (l'aine, tranche 1)
FEAR_ABILITY = 1115                                              # ActiveAbilityType.FearOfTheUnseen

#: RESIDU TIERS, PRE-EXISTANT et hors perimetre : `1079 IgnoreBattleFatigue`, que le natif pose et
#: retire au fil des tours sur ce porteur (trait `Terrifying`) et dont le port ne connait pas le
#: poseur. Il apparait DES le preambule d'atterrissage, donc AVANT que 1238 n'existe. Son unique
#: consommateur natif LU est `BattleFatigueAbility$$CreateTrigger`
#: (`op_LogicalNot(HasEffect(<Sel+0x30>, 0x437, 0, 6))`).
THIRD_PARTY_RESIDUALS = frozenset(("IgnoreBattleFatigue",))


def _capture(rpc, rid) -> dict:
    return {"dec": rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 90),
            "ob": rpc("observeBattle", {"runnerId": rid}, 40),
            "snap": rpc("combatSnapshot", {"runnerId": rid}, 60),
            "tm": rpc("tileMeta", {"runnerId": rid}, 60),
            "bg": rpc("boardGraph", {"runnerId": rid}, 60)}


def _state(cap):
    board = Board(cap["bg"]["tiles"], adjacency="evenq")
    return load_state(cap["dec"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"]), board


def _find(st, sub):
    for uid, e in st.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and sub.lower() in str(uc.visual_id).lower():
            return int(uid)
    return None


def _effects(st, uid) -> list:
    """Les noms d'effet NON consommes, MOINS les residus tiers nommes ci-dessus. On retire une liste
    EXPLICITE, jamais un filtre large : un effet inattendu doit rester visible."""
    return sorted((getattr(x, "name", None) or str(getattr(x, "effect_type", "?")))
                  for x in (st.effects.by_unit.get(int(uid)) or [])
                  if not x.consumed
                  and (getattr(x, "name", None) not in THIRD_PARTY_RESIDUALS))


def _remaining(st, uid) -> dict:
    return {int(x.effect_type): x.remaining_turns
            for x in (st.effects.by_unit.get(int(uid)) or [])
            if not x.consumed and int(x.effect_type) in (TELEPORTING_IN, MOVING, EXTRA_DAMAGE)}


def _act(rpc, rid, action, before_player=None) -> dict:
    """`applyAction` + le controle que le geste a MORDU : un geste illegal est un NO-OP SILENCIEUX
    (`ok=true, mutated=false`, H55), et sans controle un montage rate se lirait comme un desaccord
    de PORT.

    ⚠ Le TEMOIN depend du geste, et chacun est une MESURE, pas une convention :
      * `move` -> `mutated`, qui ne se leve que pour ce qui touche `changes` (position, HP) ;
      * `ability` -> `actionConsumed`. `FearOfTheUnseen` ne fait AUCUN degat et ne deplace
        personne (c'est un POSEUR D'EFFETS pur), donc un cast parfaitement mordu revient
        `mutated: false` / `changes: []` avec 25 events, dont
        `Effect_SourceActiveAbility: 1115, Effect_RemainingTurns: 3` ;
      * `finish` -> `eventCount`. Un `finish` qui a mordu revient `mutated: false` avec
        `changes: []`, mais ses `events` portent le `LoseEffect`/`DeactivateEffect` de 1035 et
        `UnitStats_TurnFinished = 1` ;
      * `endturn` -> le CHANGEMENT de `currentPlayer`. Mesure : un `endturn` sain revient
        `mutated: false`, `changes: []` ET `eventCount: 0` -- seul le passage de main le temoigne.
    Exiger `mutated` partout ferait echouer des montages SAINS (constate sur les trois derniers)."""
    r = rpc("applyAction", {"runnerId": rid, "action": action}, 60) or {}
    a = (r.get("actions") or [{}])[0]
    kind = action.get("kind")
    assert a.get("ok") is True and not a.get("error"), \
        "action %r REFUSEE (MONTAGE) : %r" % (kind, r)
    if kind == "move":
        assert a.get("mutated") is True, "action %r n'a RIEN mute (MONTAGE) : %r" % (kind, r)
    elif kind == "ability":
        assert a.get("actionConsumed") is True and int(a.get("eventCount") or 0) > 0, \
            "le cast n'a pas ete CONSOMME (MONTAGE) : %r" % (r,)
    elif kind == "endturn":
        assert before_player is not None and r.get("currentPlayer") != before_player, \
            "endturn n'a PAS passe la main (avant=%r apres=%r) -- MONTAGE" \
            % (before_player, r.get("currentPlayer"))
    else:
        assert int(a.get("eventCount") or 0) > 0, \
            "action %r n'a produit AUCUN event (MONTAGE) : %r" % (kind, r)
    return r


@pytest.fixture(scope="module")
def stage(rpc, build_runner):
    """Monte le runner ET joue le preambule d'atterrissage + le cast, une seule fois. Chaque geste
    du preambule est CONFRONTE au passage (port rejoue / natif applique)."""
    rid = build_runner(seed="777", extra=["--p-units", P_UNITS, "--no-ai"])["rid"]
    st, _b = _state(_capture(rpc, rid))
    caster = _find(st, "tyranDeathleaper")
    if caster is None:
        pytest.skip("tyranDeathleaper non deploye (pool/spawn)")
    if not st.effects.has_effect(caster, effect_type=TELEPORT_STRIKE_IN):
        pytest.skip("le Deathleaper n'arrive pas en teleport-in : preambule inapplicable")

    # --- ATTERRISSAGE : finish (T3 de 1035) + 2 endturn, confrontes a chaque pas.
    for msg, args, action in ((FinishUnitTurnMessage, (caster,),
                               {"kind": "finish", "unitId": caster}),
                              (EndTurnMessage, (), {"kind": "endturn"}),
                              (EndTurnMessage, (), {"kind": "endturn"})):
        cap = _capture(rpc, rid)
        stp, _bp = _state(cap)
        Runner(stp).install_default_handlers(20).apply(msg(*args))
        port_eff = _effects(stp, caster)
        _act(rpc, rid, action, before_player=cap["dec"].get("currentPlayer"))
        st2, _b2 = _state(_capture(rpc, rid))
        assert port_eff == _effects(st2, caster), \
            "preambule %s : port=%r != natif=%r" % (action["kind"], port_eff,
                                                    _effects(st2, caster))
    st3, _b3 = _state(_capture(rpc, rid))
    if st3.effects.has_effect(caster, effect_type=TELEPORT_STRIKE_IN):
        pytest.skip("1035 n'est pas parti : le cast resterait refuse (montage)")
    return {"rid": rid, "caster": caster}


def test_the_cast_poses_1238_for_three_turns_and_it_survives_the_cast_turn(rpc, stage):
    """LE VOLET DISCRIMINANT. Le cast pose 1238, et le `FinishUnitTurn` que
    `ActiveAbilityOperation$$AddFlagsAfterAbilityExecution` enchaine DANS LA MEME TRANSACTION ne le
    retire PAS -- parce que `remaining` vaut 3, pas 1.

    Le 3 est lui-meme une mesure : `FearOfTheUnseenAbility$$ExecuteBehaviour` passe
    `Sum(TurnsFromRounds(1), Direct(1))`, soit 2 + 1 a deux joueurs. Si le natif posait 1, la
    surcharge du vslot serait vraie tout de suite et plus rien ne se separerait."""
    rid, caster = stage["rid"], stage["caster"]
    st, _b = _state(_capture(rpc, rid))
    assert not st.effects.has_effect(caster, effect_type=TELEPORTING_IN), \
        "1238 deja present avant le cast (montage)"

    Runner(st).install_default_handlers(20).apply(
        ActiveAbilityMessage(caster_id=caster, target_id=caster, ability_type=FEAR_ABILITY))
    port_eff, port_rem = _effects(st, caster), _remaining(st, caster)

    # `ability` attend `casterId` (pas `unitId`) + `targetId` + `abilityType`. `FearOfTheUnseen` est
    # self-castante (`isSelfCasting = 1`, `range = RANGE_SELF`), d'ou `targetId == casterId`.
    _act(rpc, rid, {"kind": "ability", "casterId": caster, "abilityType": FEAR_ABILITY,
                    "targetId": caster})
    st2, _b2 = _state(_capture(rpc, rid))
    native_eff, native_rem = _effects(st2, caster), _remaining(st2, caster)

    assert native_rem.get(TELEPORTING_IN) == 3, (
        "le natif pose 1238 pour %r tours (attendu 3 = TurnsFromRounds(1) + 1) -- le regime mesure "
        "n'est plus celui qu'on croit" % native_rem.get(TELEPORTING_IN))
    assert port_eff == native_eff, "port=%r != natif=%r" % (port_eff, native_eff)
    assert port_rem == native_rem, "remaining port=%r != natif=%r" % (port_rem, native_rem)


def test_the_effect_walks_down_three_two_one_across_two_end_turns(rpc, stage):
    """La CHRONOLOGIE, confrontee a chaque `endturn` : 3 -> 2 -> 1, et 1238 VIVANT tout du long.
    C'est ce qui donne au Deathleaper son tour adverse d'invisibilite."""
    rid, caster = stage["rid"], stage["caster"]
    st0, _b0 = _state(_capture(rpc, rid))
    assert _remaining(st0, caster).get(TELEPORTING_IN) == 3, \
        "entree du test a remaining=%r (le test du cast doit passer d'abord)" \
        % _remaining(st0, caster).get(TELEPORTING_IN)

    for expected in (2, 1):
        cap = _capture(rpc, rid)
        stp, _bp = _state(cap)
        Runner(stp).install_default_handlers(20).apply(EndTurnMessage())
        port_rem, port_eff = _remaining(stp, caster), _effects(stp, caster)
        _act(rpc, rid, {"kind": "endturn"}, before_player=cap["dec"].get("currentPlayer"))
        st2, _b2 = _state(_capture(rpc, rid))
        native_rem, native_eff = _remaining(st2, caster), _effects(st2, caster)
        assert native_rem.get(TELEPORTING_IN) == expected, \
            "natif a remaining=%r (attendu %d)" % (native_rem.get(TELEPORTING_IN), expected)
        assert port_rem == native_rem, "remaining port=%r != natif=%r" % (port_rem, native_rem)
        assert port_eff == native_eff, "effects port=%r != natif=%r" % (port_eff, native_eff)


def test_at_remaining_one_the_step_poses_1241_then_lands_the_carrier(rpc, stage):
    """T4 puis T1, DANS LE MEME PAS, et cette fois le vslot est OUVERT (`remaining == 1`). Le port
    est decoupe en deux (l'Operation, puis le vecteur after-move) pour observer le marqueur
    `1241 FearOfTheUnseen_Moving` a l'etat intermediaire -- cote natif il n'est PAS observable dans
    un etat, il nait et meurt dans la MEME cascade d'events."""
    rid, caster = stage["rid"], stage["caster"]
    st, _b = _state(_capture(rpc, rid))
    assert _remaining(st, caster).get(TELEPORTING_IN) == 1, \
        "entree du test a remaining=%r (attendu 1)" % _remaining(st, caster).get(TELEPORTING_IN)

    mv = (rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}).get("units") or []
    here = next(iter(get_unit_feet(st, caster)), None)
    legal = sorted({(t.get("col"), t.get("row")) for u in mv if u.get("unitId") == caster
                    for t in (u.get("tiles") or [])} - {here})
    if not legal:
        pytest.skip("aucune tuile legale pour le Deathleaper (montage)")
    dest = legal[0]

    # --- PORT, en deux temps.
    MoveUnitOperation(caster, tuple(dest)).execute(st, EventBus())
    mid = sorted(int(e.effect_type) for e in st.effects.by_unit.get(caster, []) if not e.consumed)
    assert MOVING in mid, "T4 n'a pas pose 1241 pendant le pas : %r" % (mid,)
    assert TELEPORTING_IN in mid, "1238 deja retire pendant le pas : T1 fire trop tot"
    after_move_triggers(st, caster)
    port_eff, port_rem = _effects(st, caster), _remaining(st, caster)
    assert MOVING not in [int(e.effect_type) for e in st.effects.by_unit.get(caster, [])
                          if not e.consumed], "1241 survit au pas"

    # --- NATIF : le MEME pas, puis rechargement.
    _act(rpc, rid, {"kind": "move", "unitId": caster,
                    "to": {"col": int(dest[0]), "row": int(dest[1])}})
    st2, _b2 = _state(_capture(rpc, rid))
    assert not st2.effects.has_effect(caster, effect_type=TELEPORTING_IN), \
        "le natif GARDE 1238 apres le pas a remaining=1 -- la mesure ne discrimine rien"
    assert _effects(st2, caster) == port_eff, \
        "port=%r != natif=%r" % (port_eff, _effects(st2, caster))
    assert _remaining(st2, caster) == port_rem, \
        "remaining port=%r != natif=%r" % (port_rem, _remaining(st2, caster))
    assert get_unit_feet(st2, caster) == [tuple(dest)]


def test_a_second_step_no_longer_poses_the_moving_marker(rpc, stage):
    """INVARIANT COMPLEMENTAIRE, par la voie COMPLETE (`Runner.apply(MoveUnitMessage)`, le chemin de
    production) : une fois 1238 parti, un nouveau pas ne doit PLUS poser 1241 -- il n'y a plus
    d'instance porteuse, donc plus de T4 du tout.

    ⚠ Ce test est un REJEU OFFLINE PUR, et il le dit : la destination est prise dans le VOISINAGE
    du board, pas dans `aiMovableTiles`. Apres le pas live du test precedent le Deathleaper n'a plus
    de mouvement, donc `aiMovableTiles` est VIDE pour lui -- s'en servir ici ne produirait qu'un
    `pytest.skip`, c'est a dire un VERT qui ment sur une garde qui n'a rien exerce. Il n'y a rien a
    confronter au natif ici (le natif REFUSERAIT le pas) : on verifie une propriete du PORT seul."""
    rid, caster = stage["rid"], stage["caster"]
    st, board = _state(_capture(rpc, rid))
    assert not st.effects.has_effect(caster, effect_type=TELEPORTING_IN), \
        "1238 encore present : le test du pas doit passer d'abord"
    here = next(iter(get_unit_feet(st, caster)), None)
    assert here is not None, "le Deathleaper n'a pas de position (montage)"
    taken = {p for u in st.entities for p in get_unit_feet(st, u)}
    dest = next((board.coord(t) for t in board.neighbours(board.id_at(here[0], here[1]))
                 if board.coord(t) not in taken and board.walkable(t)), None)
    assert dest is not None, "aucune tuile voisine libre (montage)"
    Runner(st).install_default_handlers(20).apply(MoveUnitMessage(caster, tuple(dest)))
    alive = [int(e.effect_type) for e in st.effects.by_unit.get(caster, []) if not e.consumed]
    assert MOVING not in alive, "1241 pose sans porteur 1238 : %r" % (alive,)
    assert TELEPORTING_IN not in alive, alive
    assert get_unit_feet(st, caster) == [tuple(dest)]
