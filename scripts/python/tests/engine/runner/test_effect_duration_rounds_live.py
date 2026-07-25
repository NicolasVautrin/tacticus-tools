"""DUREE D'EFFET : conversion ROUNDS -> TOURS (#98) — CONFRONT LIVE.

`IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` = `count(joueurs du `BC.Player.TurnOrder` dont
`PlayerComponent+0x20 != 2` = Environment exclu) * rounds`. DEUX voies natives y passent :

  * le noeud DSL `TurnsFromRounds(n)` (`IdunBattle.Entities.Formulas.TurnsFromRoundsFormula$$Calculate` -> slot 0x1b
    de `BattleQuery`) — ex. `IdunBattleLogic.Entities.Abilities.Active.Loki.ThunderousAssaultAbility$$ExecuteBehaviour` :
    `AddEffect(0x48a Stunned, stateRef, target@0x178, TurnsFromRounds(1))` ;
  * la duree PAR DEFAUT dans `IdunBattle.Operations.AddEffectOperation$$Execute`, branche « pas d'override » :
    `ConvertRoundsToTurns(DefaultAmountOfRounds(type).Value)` — ex. `Pinned 1065` (1 round).

Une duree passee en `Nullable<int>(n)` / `Direct(n)@0xc0` par l'appelant est DEJA en TOURS et n'est
**PAS** convertie (le natif la met telle quelle dans `param_6`) — c'est le canal `duration_turns` du
port (Waaagh IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour, WeaverOfFate IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility$$CreateBehaviour, Decoys IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_BuffFriendsAbility$$CreateBehaviour, Hypersensory IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateBehaviour).

PIEGE DE MESURE (la raison pour laquelle ce bug a survecu) : en 1v1 STRICT, le cast est l'action de
la SEULE unite du camp -> `AddFlagsAfterAbilityExecution` -> `FinishUnitTurn` -> le moteur CLOT le
tour -> `EndTurnOperation` -> `IdunBattle.Operations.EndTurnOperation$$RefreshEffects` decremente TOUS les timers AVANT qu'on
relise `decisionView`. La valeur lue est alors `duree_posee - 1`, ce qui MIME l'identite rounds=turns.
Ces tests montent donc TOUJOURS >= 2 unites cote joueur et castent avec une unite qui en laisse une
autre activable : la lecture est PRE-tick (verifie explicitement par `currentPlayer` inchange).

Aucune constante de duree en dur : tout est confronte au `remaining` natif (`decisionView.effects`).
ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import hexgeo
from engine.runner.snapshot import load_state
from engine.runner.state import State
from engine.runner.abilities.base import convert_rounds_to_turns
from engine.runner.operations.effects import AddEffectOperation, default_amount_of_rounds

STUNNED = 1162          # 0x48a — pose par ThunderousAssault avec TurnsFromRounds(1)
PINNED = 1065           # 0x429 — pose par SuppressiveFire SANS noeud duree (DefaultAmountOfRounds=1)
THUNDEROUS = 1043
NORMAL_ATTACK = 69      # ActiveAbilityType par defaut (BC.DefaultActiveAbility)

# 2 unites cote joueur = lecture PRE-tick garantie (cf. en-tete). `templSwordBrother` porte
# ThunderousAssault (Stunned/TurnsFromRounds(1)), `emperNoiseMarine` porte SuppressiveFire
# (Pinned on-hit ranged, duree PAR DEFAUT). Cibles `necroWarden` : aucune immunite d'effet.
# `--hp-target` INCREVABLE : une cible qui MEURT au cast ne porte plus d'effet -> le datapoint
# de duree disparait (skip). On CRAFTE donc la survie au lieu de la subir.
BUILD = ["--p-units", "templSwordBrother,emperNoiseMarine",
         "--a-units", "necroWarden,necroWarden", "--hp-target", "999999"]


def _dv(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "maxRank": 99, "allAbilities": True}, 120)


def _act(rpc, rid, action):
    return rpc("applyAction", {"runnerId": rid, "action": action, "captureEvents": False}, 120)


def _alive(dec, vis):
    return [u for u in (dec.get("units") or [])
            if u.get("visualId") == vis and u.get("alive")]


def _by_id(dec, uid):
    return next((u for u in (dec.get("units") or []) if u.get("id") == uid), None)


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _rem(u, effect_type):
    for e in ((u or {}).get("effects") or []):
        if e.get("effectType") == effect_type:
            return e.get("remaining")
    return None


def _movable(rpc, rid, uid):
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])]
    return []


def _drive_to(rpc, rid, uid, anchor, want):
    """DRIVE des DEUX camps (`applyAction` ne verifie pas la propriete) : place `uid` a la distance
    hex `want` de `anchor`. On ne SUBIT jamais la geometrie de spawn."""
    tiles = _movable(rpc, rid, uid)
    if not tiles:
        return None
    best = min(tiles, key=lambda t: abs(hexgeo.distance(t, anchor) - want))
    _act(rpc, rid, {"kind": "move", "unitId": uid, "to": {"col": best[0], "row": best[1]}})
    return hexgeo.distance(best, anchor)


def _setup(rpc, rid, caster_vis, want_range, max_rounds=14):
    """Amene `caster_vis` a `want_range` d'un ennemi vivant, en pilotant les DEUX camps.
    Renvoie `(decision, caster, target)` au tour du joueur, ou `(None, None, None)`."""
    for _ in range(max_rounds):
        dec = _dv(rpc, rid)
        me = _alive(dec, caster_vis)
        ens = _alive(dec, "necroWarden")
        if not me or not ens:
            return None, None, None
        caster = me[0]
        if dec.get("currentPlayer") != caster.get("owner"):
            # tour ADVERSE : on rapproche NOUS-MEMES une cible du caster puis on rend la main
            _drive_to(rpc, rid, ens[0]["id"], _pos(caster), want_range)
            _act(rpc, rid, {"kind": "endturn"})
            continue
        cand = [e for e in ens if hexgeo.distance(_pos(e), _pos(caster)) <= want_range]
        if cand:
            return dec, caster, min(cand, key=lambda e: hexgeo.distance(_pos(e), _pos(caster)))
        tgt = min(ens, key=lambda e: hexgeo.distance(_pos(e), _pos(caster)))
        if _drive_to(rpc, rid, caster["id"], _pos(tgt), want_range) is None:
            _act(rpc, rid, {"kind": "endturn"})
            continue
        dec = _dv(rpc, rid)
        caster = (_alive(dec, caster_vis) or [None])[0]
        tgt = _by_id(dec, tgt["id"])
        if caster is None or tgt is None:
            return None, None, None
        if hexgeo.distance(_pos(tgt), _pos(caster)) <= want_range:
            return dec, caster, tgt
        _act(rpc, rid, {"kind": "endturn"})
    return None, None, None


def _factor(rpc, rid):
    """FACTEUR de conversion tel que le port le derive du live (`load_state`)."""
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    st = load_state(_dv(rpc, rid), ob)
    return st.turn_order_player_count, ob


def test_rounds_to_turns_factor_seeded_from_live(live_session, rpc, build_runner):
    """Le facteur est LU de la bataille (pas fige) : `count(joueurs non-Environment)`.

    Garde : si le seed du canal disparait (`load_state` qui n'alimente plus
    `turn_order_player_count`), `convert_rounds_to_turns` retomberait silencieusement sur l'identite
    -> TOUTES les durees en rounds seraient divisees par le facteur, sans erreur.
    """
    rid = build_runner("777", extra=BUILD)["rid"]
    n, ob = _factor(rpc, rid)
    players = (ob.get("counts") or {}).get("player")
    assert players, f"observeBattle.counts.player absent: {ob.get('counts')}"
    assert n == int(players) - 1, (
        f"facteur seede {n} != counts.player-1 {int(players) - 1} "
        f"(mirror: TurnOrder moins l'unique joueur Environment)")
    assert n and n >= 1, f"facteur non seede ({n}) -> convert_rounds_to_turns degrade en identite"
    print(f"\n[DUREE facteur] counts.player={players} -> count(non-Env)={n} "
          f"-> convert(1)={convert_rounds_to_turns(load_state(_dv(rpc, rid), ob), 1)}")


def test_turns_from_rounds_duration_matches_live(live_session, rpc, build_runner):
    """VOIE 1 (`TurnsFromRounds(1)` explicite) : le `remaining` natif du Stun pose par
    ThunderousAssault IdunBattleLogic.Entities.Abilities.Active.Loki.ThunderousAssaultAbility$$ExecuteBehaviour doit valoir `convert_rounds_to_turns(state, 1)` — PAS 1.

    Le cast est fait par `templSwordBrother` alors qu'`emperNoiseMarine` n'a PAS agi -> le tour ne
    bascule pas -> lecture PRE-tick (assertion explicite sur `currentPlayer`).
    """
    rid = build_runner("777", extra=BUILD)["rid"]
    dec, caster, tgt = _setup(rpc, rid, "templSwordBrother", 1)
    if caster is None:
        pytest.skip("scenario non montable (roster/geometrie)")
    assert _rem(tgt, STUNNED) is None, f"cible deja Stunned avant le cast: {tgt.get('effects')}"

    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    state = load_state(dec, ob)
    player_before = dec.get("currentPlayer")

    res = _act(rpc, rid, {"kind": "ability", "casterId": caster["id"],
                          "targetId": tgt["id"], "abilityType": THUNDEROUS})
    if not (isinstance(res, dict) and res.get("ok")):
        pytest.skip(f"cast KO: {str(res)[:160]}")
    dec2 = _dv(rpc, rid)
    t2 = _by_id(dec2, tgt["id"])
    if not (t2 and t2.get("alive")):
        pytest.skip("cible morte au cast")
    assert dec2.get("currentPlayer") == player_before, (
        "le tour a bascule pendant le cast -> lecture POST-tick (RefreshEffects), "
        "mesure non comparable : il faut une 2e unite activable dans le camp")

    live = _rem(t2, STUNNED)
    assert live is not None, f"le natif n'a PAS pose Stunned: {t2.get('effects')}"
    expected = convert_rounds_to_turns(state, 1)          # TurnsFromRounds(1) du decompile
    assert live == expected, (
        f"Stunned remaining live={live} != convert_rounds_to_turns(1)={expected} "
        f"(facteur={state.turn_order_player_count})")
    # l'identite historique (rounds==turns) doit etre REFUTEE par la mesure, sinon ce test ne garde rien
    assert live != 1 or state.turn_order_player_count == 1, (
        "mesure degeneree : le facteur vaut 1, ce test ne discrimine pas la conversion")
    print(f"\n[DUREE TurnsFromRounds] Stunned live={live} == convert(1)={expected} "
          f"(facteur={state.turn_order_player_count})")


def test_default_amount_of_rounds_duration_matches_live(live_session, rpc, build_runner):
    """VOIE 2 (duree PAR DEFAUT) : `Pinned 1065` pose par SuppressiveFire n'a AUCUN noeud duree ->
    le natif prend `ConvertRoundsToTurns(DefaultAmountOfRounds(1065))`. On confronte le `remaining`
    natif a ce que `AddEffectOperation` produit OFFLINE depuis la MEME capture d'etat.
    """
    rid = build_runner("777", extra=BUILD)["rid"]
    dec, caster, tgt = _setup(rpc, rid, "emperNoiseMarine", 3)
    if caster is None:
        pytest.skip("scenario non montable (roster/geometrie)")
    # tir RANGED obligatoire (SuppressiveFire est on-hit ranged) : distance >= 2
    for _ in range(6):
        if hexgeo.distance(_pos(tgt), _pos(caster)) >= 2:
            break
        _drive_to(rpc, rid, tgt["id"], _pos(caster), 3)
        dec = _dv(rpc, rid)
        caster = (_alive(dec, "emperNoiseMarine") or [None])[0]
        tgt = _by_id(dec, tgt["id"])
        if caster is None or tgt is None:
            pytest.skip("cible perdue")
    if hexgeo.distance(_pos(tgt), _pos(caster)) < 2:
        pytest.skip("impossible de placer un tir RANGED (cible collee)")
    if _rem(tgt, PINNED) is not None:
        pytest.skip("cible deja Pinned")

    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    state = load_state(dec, ob, rpc("combatSnapshot", {"runnerId": rid}, 60))
    if state.effects is None:
        pytest.skip("EffectsState non charge (combatSnapshot absent)")
    player_before = dec.get("currentPlayer")

    res = _act(rpc, rid, {"kind": "ability", "casterId": caster["id"],
                          "targetId": tgt["id"], "abilityType": NORMAL_ATTACK})
    if not (isinstance(res, dict) and res.get("ok")):
        pytest.skip(f"tir KO: {str(res)[:160]}")
    dec2 = _dv(rpc, rid)
    t2 = _by_id(dec2, tgt["id"])
    if not (t2 and t2.get("alive")):
        pytest.skip("cible morte au tir")
    live = _rem(t2, PINNED)
    if live is None:
        pytest.skip("le natif n'a pas pose Pinned sur ce tir (block/miss) -> pas de datapoint")
    assert dec2.get("currentPlayer") == player_before, (
        "le tour a bascule pendant le tir -> lecture POST-tick, mesure non comparable")

    # OFFLINE : la MEME feuille de pose, sans override de duree (== l'arbre SuppressiveFire).
    eff = AddEffectOperation.execute(state, source=caster["id"], target=tgt["id"],
                                     effect_type=PINNED, name="Pinned")
    assert eff is not None, "AddEffectOperation offline n'a pas materialise Pinned"
    assert eff.remaining_turns == live, (
        f"Pinned remaining offline={eff.remaining_turns} != live={live} "
        f"(DefaultAmountOfRounds={default_amount_of_rounds(PINNED)}, "
        f"facteur={state.turn_order_player_count})")
    assert live == convert_rounds_to_turns(state, default_amount_of_rounds(PINNED)), (
        f"live={live} != ConvertRoundsToTurns(DefaultAmountOfRounds(1065))")
    print(f"\n[DUREE DefaultAmountOfRounds] Pinned live={live} == offline={eff.remaining_turns} "
          f"(rounds={default_amount_of_rounds(PINNED)}, facteur={state.turn_order_player_count})")


def test_duration_turns_channel_is_not_converted():
    """GARDE DE NON-REGRESSION du canal `duration_turns` (OFFLINE, pas de live requis).

    Les call-sites dont le natif passe un `Direct(n)@0xc0` / `Nullable<int>(n)` (Waaagh IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour,
    MasterOfTheTutelaries IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$ExecuteBehaviour, WeaverOfFate IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility$$CreateBehaviour, Decoys IdunBattleLogic.Entities.Abilities.Triggered.Loki.DecoysAndMisdirection_BuffFriendsAbility$$CreateBehaviour, Hypersensory
    IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateBehaviour) sont DEJA en TOURS : les convertir les DOUBLERAIT. Ce test fige la separation des
    deux canaux — c'est le risque #1 d'une reconciliation faite en aveugle.
    """
    from engine.runner.abilities.behaviours.effects import _resolve_duration
    st = State()
    st.turn_order_player_count = 2
    assert _resolve_duration(st, 1, None) == 2, "duration_rounds=1 doit passer par ConvertRoundsToTurns"
    assert _resolve_duration(st, 2, None) == 4, "duration_rounds=2 -> 2 x facteur"
    assert _resolve_duration(st, None, 1) == 1, "duration_turns=1 est DEJA en tours : aucune conversion"
    assert _resolve_duration(st, 1, 1) == 1, "duration_turns est PRIORITAIRE sur duration_rounds"
    assert _resolve_duration(st, None, None) is None, "aucune duree -> pas d'override (duree DEFAUT)"
    assert _resolve_duration(st, 0, None) == 0, "0 round reste 0 (= permanent)"
    # etat sans canal (tests unitaires purs) -> identite, aucun changement de comportement
    assert _resolve_duration(State(), 2, None) == 2


def test_default_rounds_conversion_offline():
    """`AddEffectOperation` convertit la duree PAR DEFAUT (branche 2 du decompile IdunBattle.Operations.AddEffectOperation$$Execute) et
    laisse l'override intact (branche 1, deja en TOURS). Garde OFFLINE de la cascade."""
    from engine.entities.effects_state import EffectsState
    for et in (PINNED, 17):                     # 1065 (1 round) et Ice 0x11 (2 rounds)
        rounds = default_amount_of_rounds(et)
        assert rounds, f"DefaultAmountOfRounds({et}) absent de la table portee"
        st = State()
        st.effects = EffectsState()
        st.turn_order_player_count = 2
        st.add_entity(1)
        eff = AddEffectOperation.execute(st, source=None, target=1, effect_type=et, name=f"E{et}")
        assert eff is not None and eff.remaining_turns == rounds * 2, (
            f"effet {et}: remaining={None if eff is None else eff.remaining_turns} "
            f"!= DefaultAmountOfRounds({rounds}) x facteur 2")
        # override = deja en TOURS -> pas de conversion
        st2 = State()
        st2.effects = EffectsState()
        st2.turn_order_player_count = 2
        st2.add_entity(1)
        eff2 = AddEffectOperation.execute(st2, source=None, target=1, effect_type=et,
                                          name=f"E{et}", duration_override=3)
        assert eff2 is not None and eff2.remaining_turns == 3, (
            "duration_override (param_6 natif) ne doit JAMAIS etre converti")
