"""#88 (residu A1) -- volet REVIVE de `FuelledByFury` (`ultraTitus` << Titus >>), GARDE.

i2 : << The first time each turn **he defeats an enemy with an attack triggered by Final Vengeance**
he is immediately revived with a maximum of {hp} Health. >>

Chaine native gardee ici (cf. `runner/operations/triggers/loki/fuelled_by_fury.py` pour les arbres) :
  `KillUnitOperation` de Titus -> `On(1)` -> riposte `FinalJusticeAbility` (`TriggeredAbilityType`
  1024) -> si elle TUE, `IdunBattle.Operations.RecordKillOperation$$Execute` publie
  `On(3 = PendingDeathAdded)` {caster = le TUEUR, target = la victime} en portant
  `TriggeringAbility = 1024` -> `FuelledByFury_ReviveAbility` pose une `ReviveData` sur Titus
  -> la garde `if (!pendingRevive.HasValue)` de `KillUnitOperation` ECHOUE -> mort ANNULEE.

GROUND TRUTH LIVE (`probe_88_fuelled_by_fury_revive.py`, 2 regimes, MEME geometrie et MEME coup
fatal, seule la PV des ennemis change) :
  * riposte LETALE      -> Titus **VIVANT** a **7477** PV, **sur sa propre tuile** ;
  * riposte NON letale  -> Titus **MORT** a 0 PV.
`7477 == round(FuelledByFury.hp[L50] = 4154 x 180 %)` = `ability_var('FuelledByFury', 'hp', ...)`.

Les tests montent une bataille LIVE (stats/PV/effets REELS) puis DRIVENT positions et PV offline pour
que la condition testee soit remplie ET stable ; la mort passe par le VRAI chokepoint
`AttackDamageOperation._fire_death_if_killed`. ASCII only ; ADJACENCE = evenq.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.triggers import TriggerEvent, evaluate_trigger_operation
from engine.runner.operations.triggers.dispatch import (pending_death_added_triggers,
                                                        tile_tick_triggers)
from engine.runner.operations.triggers.loki.fuelled_by_fury import (
    FUELLED_BY_FURY_CAN_REVIVE, FUELLED_BY_FURY_ABILITY, _can_revive_is_armed,
    _set_can_revive_active)
from engine.runner.components import (UnitComponent, HealthComponent, StatsComponent,
                                      OwnerComponent, PositionComponent)
from engine.runner.prng import IntBasedMersenneTwister
from engine.entities.effects.magnitude import ability_var
from engine.dsl.event_trigger_type import EventTriggerType

TITUS = "ultraTitus"
BUILD = ["--p-units", "ultraTitus", "--a-units", "astraBullgryn,orksNob"]
FINAL_JUSTICE = 1024


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _state(rpc, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    st = load_state(dec, ob, snap, board=board)
    st.rng = IntBasedMersenneTwister(12345)          # seed FIXE : le tirage de degat doit etre stable
    td = next((u for u in (dec.get("units") or []) if u.get("visualId") == TITUS), None)
    if td is None or st.get_entity(td.get("id")) is None:
        pytest.skip("Titus absent de l'etat capture")
    return st, int(td["id"])


def _drive(st, tid, foe_hp):
    """DRIVE : ennemis places AU CONTACT de Titus (le port ne doit jamais dependre de la geometrie de
    spawn) et PV des ennemis fixees pour rendre la riposte letale ou non. Renvoie la liste des ids."""
    board = st.board
    te = st.get_entity(tid)
    tpc = te.get_component(PositionComponent)
    toc = te.get_component(OwnerComponent)
    neigh = [n for n in board.neighbours(board.id_at(tpc.col, tpc.row)) if board.walkable(n)]
    foes = []
    for eid, e in sorted(st.entities.items()):
        if eid == tid:
            continue
        oc, uc = e.get_component(OwnerComponent), e.get_component(UnitComponent)
        if oc is None or (toc is not None and oc.team == toc.team):
            continue
        if uc is not None and not uc.alive:
            continue
        foes.append(eid)
    if len(foes) < 1 or not neigh:
        pytest.skip("aucun ennemi repositionnable au contact")
    for eid, tile in zip(foes, neigh):
        col, row = board.coord(tile)
        pc = st.get_entity(eid).get_component(PositionComponent)
        pc.col, pc.row = col, row
        hc = st.get_entity(eid).get_component(HealthComponent)
        hc.hp = int(foe_hp)
    return foes[:len(neigh)]


def _kill_titus(st, tid, killer_id):
    """Fait passer Titus par le VRAI chokepoint de mort (le meme que le pipeline de degat)."""
    e = st.get_entity(tid)
    hc = e.get_component(HealthComponent)
    hp_before = int(hc.hp)
    hc.hp = 0
    out = AttackDamageOperation._fire_death_if_killed(st, tid, killer_id, hp_before, 0, e,
                                                     damage=hp_before)
    return out or []


def _expected_revive_hp(st, tid):
    """`ConfigVar(0x1d='hp', abilityState)` du PASSIF, clampe par `ReviveUnitOperation.SetHealth`."""
    sc = st.get_entity(tid).get_component(StatsComponent)
    lvl = getattr(sc.ctx, "passive_ability_level", None)
    mult = getattr(sc.ctx, "ability_variables_multiplier", 100)
    hp = int(ability_var("FuelledByFury", "hp", lvl, multiplier_pct=mult))
    hc = st.get_entity(tid).get_component(HealthComponent)
    return min(hp, int(hc.hp_max)) if hc.hp_max else hp


def test_fuelled_by_fury_revive_cancels_own_death_live(live_session, rpc, build_runner):
    """FACE POSITIVE : la riposte FinalJustice TUE -> `On(3)` porte `TriggeringAbility = 1024`,
    `FuelledByFury_ReviveAbility` pose la `ReviveData`, la garde de `KillUnitOperation` annule la mort.
    Titus revient EN PLACE a `min(ConfigVar('hp'), maxPV)` -- 7477 sur le regime live mesure."""
    rid = build_runner("31337", extra=BUILD)["rid"]
    st, tid = _state(rpc, rid)
    e = st.get_entity(tid)
    pos0 = (e.get_component(PositionComponent).col, e.get_component(PositionComponent).row)
    assert _can_revive_is_armed(st, tid), "le marqueur 1324 doit etre capte ACTIF sur Titus"
    foes = _drive(st, tid, foe_hp=1)                      # riposte letale a coup sur
    out = _kill_titus(st, tid, foes[0])

    uc, hc = e.get_component(UnitComponent), e.get_component(HealthComponent)
    assert uc.alive, f"Titus aurait du etre revive (sorties={out})"
    assert int(hc.hp) == _expected_revive_hp(st, tid), \
        f"hp de revive {hc.hp} != min(ConfigVar('hp'), maxPV)={_expected_revive_hp(st, tid)}"
    pos1 = (e.get_component(PositionComponent).col, e.get_component(PositionComponent).row)
    assert pos0 == pos1, f"revive NON in-place {pos0} -> {pos1}"
    assert any("kill_cancelled_by_revive" in r for r in out), \
        f"la garde `!pendingRevive.HasValue` n'a pas annule la mort (sorties={out})"
    # le marqueur est CONSOMME (`On(0x2e) & CurrentAbilityIs(1251) -> DeactivateEffect`)
    assert not _can_revive_is_armed(st, tid), "le marqueur 1324 devait etre DESACTIVE apres le revive"


def test_fuelled_by_fury_revive_requires_a_kill_live(live_session, rpc, build_runner):
    """FACE NEGATIVE (le discriminant mesure live) : MEME etat, MEME mort, mais la riposte ne TUE PAS
    -> aucun `On(3)` de Titus-tueur -> aucun revive, Titus reste MORT.

    ⚠ CORRIGE PAR #389-r2. Ce test asserait auparavant que le marqueur 1324 restait ARME apres la
    mort -- ce qui mesurait l'ANCIEN port (qui ne retirait pas les effets d'un mort), pas le natif.
    Quand aucun revive n'est pose, la garde `!PendingRevive.HasValue` de
    `IdunBattle.Operations.KillUnitOperation$$Execute` PASSE, donc ses TROIS
    `RemoveEffects(killed, <KillUnitStep>)` tournent et vident TOUS les effets du mort, 1324 compris.
    MESURE LIVE DIRECTE (`probe_389r2_kill_unit_remove_effects.py --a-units necroWarden,ultraTitus
    --target-visual ultraTitus`) : Titus meurt en portant `[1324, 1354, 1516, 1517]`, le natif le
    laisse avec `[]`.

    Le marqueur est donc DESARME dans les deux faces, mais par DEUX mecanismes distincts, et c'est
    `consumed` qui les separe : face POSITIVE, la mort est ANNULEE (aucun `RemoveEffects` ne tourne)
    et le marqueur est seulement DESACTIVE (`On(0x2e) -> DeactivateEffect`, instance vivante) ; face
    NEGATIVE, l'instance est RETIREE avec son porteur."""
    rid = build_runner("31337", extra=BUILD)["rid"]
    st, tid = _state(rpc, rid)
    assert _can_revive_is_armed(st, tid), "le marqueur 1324 doit etre capte ACTIF sur Titus"
    foes = _drive(st, tid, foe_hp=10 ** 7)               # riposte non letale
    out = _kill_titus(st, tid, foes[0])
    e = st.get_entity(tid)
    assert not e.get_component(UnitComponent).alive, \
        f"Titus revive alors qu'aucun ennemi n'est mort (sorties={out})"
    assert not _can_revive_is_armed(st, tid), \
        "le marqueur 1324 doit partir avec son porteur mort (KillUnitOperation$$RemoveEffects)"
    assert all(e2.consumed for e2 in (st.effects.by_unit.get(tid) or [])), \
        f"le mort garde des effets non consommes : {[e2.effect_type for e2 in st.effects.by_unit.get(tid) or [] if not e2.consumed]}"


def test_fuelled_by_fury_revive_requires_armed_marker_live(live_session, rpc, build_runner):
    """`HasEffect(self, 0x52c, **1**, 6)` : le marqueur doit etre ACTIF. Marqueur desactive (= revive
    deja consomme ce tour) -> la riposte tue toujours, mais Titus reste MORT (once-per-TURN)."""
    rid = build_runner("31337", extra=BUILD)["rid"]
    st, tid = _state(rpc, rid)
    foes = _drive(st, tid, foe_hp=1)
    assert _set_can_revive_active(st, tid, False), "le marqueur devait etre actif avant desarmement"
    out = _kill_titus(st, tid, foes[0])
    e = st.get_entity(tid)
    assert not e.get_component(UnitComponent).alive, \
        f"Titus revive avec un marqueur DESACTIVE (sorties={out})"
    # ... et la riposte, elle, a bien tue (c'est donc bien le marqueur qui discrimine)
    assert any(not st.get_entity(f).get_component(UnitComponent).alive for f in foes), \
        "la riposte FinalJustice aurait du tuer un ennemi"


def test_fuelled_by_fury_revive_requires_triggering_ability_live(live_session, rpc, build_runner):
    """`TriggeringAbilityIs(0x400 = FinalJustice)` : un kill de Titus qui ne vient PAS de FinalJustice
    (donc `AbilityEntities.TriggeringAbility` absent) n'arme AUCUN revive. On dispatche `On(3)` a la
    main avec le MEME couple {tueur, victime}, une fois avec 1024 et une fois sans."""
    rid = build_runner("31337", extra=BUILD)["rid"]
    st, tid = _state(rpc, rid)
    foes = _drive(st, tid, foe_hp=1)
    e = st.get_entity(tid)
    e.get_component(HealthComponent).hp = 0              # Titus en mort-pendante (comme le natif)
    e.get_component(UnitComponent).alive = False
    victim = foes[0]
    st.get_entity(victim).get_component(HealthComponent).hp = 0
    st.get_entity(victim).get_component(UnitComponent).alive = False

    ev_no = TriggerEvent(EventTriggerType.PendingDeathAdded, tid, victim, ranged=False, profile=None,
                         killer_id=tid, dying_id=victim, triggering_ability=None)
    assert evaluate_trigger_operation(st, ev_no) == [], "revive arme SANS TriggeringAbility"
    assert e.get_component(UnitComponent).pending_revive is None

    ev_yes = TriggerEvent(EventTriggerType.PendingDeathAdded, tid, victim, ranged=False, profile=None,
                          killer_id=tid, dying_id=victim, triggering_ability=FINAL_JUSTICE)
    res = evaluate_trigger_operation(st, ev_yes)
    assert any(r.get("ability") == "FuelledByFury" for r in res), f"revive non arme avec 1024 : {res}"
    data = e.get_component(UnitComponent).pending_revive
    assert data is not None and int(data["source"]) == FUELLED_BY_FURY_ABILITY, \
        f"`sourceId` du Revive != 1251 : {data}"


def test_fuelled_by_fury_marker_rearms_on_turn_tick_live(live_session, rpc, build_runner):
    """2e `Triggered()` de l'`ArraySet` du marqueur : `On(0x12 = TurnStart_EffectActivation) ->
    ActivateEffect`, SANS aucun predicat d'owner -> le << first time each TURN >> se re-arme a chaque
    tick de tour. Et le vecteur `pending_death_added_triggers` est bien celui qui porte `On(3)`."""
    rid = build_runner("31337", extra=BUILD)["rid"]
    st, tid = _state(rpc, rid)
    foes = _drive(st, tid, foe_hp=1)
    assert _set_can_revive_active(st, tid, False)
    assert not _can_revive_is_armed(st, tid)
    tile_tick_triggers(st)                                # On(0x12) puis On(0x14)
    assert _can_revive_is_armed(st, tid), "le tick de tour n'a pas re-arme le marqueur 1324"

    # le vecteur `On(3)` du port porte bien `state.triggering_ability`
    e = st.get_entity(tid)
    e.get_component(HealthComponent).hp = 0
    e.get_component(UnitComponent).alive = False
    victim = foes[0]
    st.get_entity(victim).get_component(HealthComponent).hp = 0
    st.get_entity(victim).get_component(UnitComponent).alive = False
    st.triggering_ability = FINAL_JUSTICE
    res = pending_death_added_triggers(st, victim, tid)
    assert any(r.get("ability") == "FuelledByFury" for r in res), \
        f"`pending_death_added_triggers` ne threade pas le TriggeringAbility : {res}"
    assert _ok is not None and FUELLED_BY_FURY_CAN_REVIVE == 1324
