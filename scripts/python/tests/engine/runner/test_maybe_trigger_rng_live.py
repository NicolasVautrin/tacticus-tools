"""O4a — le gate `Maybe(chance)` consomme-t-il UN tirage, AU BON MOMENT dans le flux ?

`IdunBattle.Entities.Triggers.MaybeTrigger$$ShouldTrigger` :

    chance = <formule V @+0x20>.Calculate(entities)
    if (!IdunBattle.DSL.ANonDeterministicAbilityTrigger$$CanUseRandom(this)) return 99 < chance;
    return IdunBattle.Utils.PRNG.DisallowablePseudoRNG$$NextBool(this@+0x18, chance);

`CanUseRandom` = `state.IsRandomAllowed && rng.IsAllowed@+0x20` ; le flag `IsAllowed` vaut 1 depuis
`IdunBattle.Utils.PRNG.DisallowablePseudoRNG$$.ctor` et n'est abaisse que par
`IdunBattleLogic.Entities.DSLFactory$$SetDisallowRandom`, dont l'unique call-site est
`IdunBattle.AI.Playbook.BasePlaybook$$Evaluate` -> la branche deterministe `99 < chance` est celle
de la face DECISION/PREDICTION.

Ce que ces tests GARDENT (chacun serait ROUGE sur le port d'avant) :
  1. le noeud consomme exactement 1 `genrand_int32` et rend le meme verdict que `NextBool` ;
  2. sans PRNG (face prediction), il consomme 0 tirage et rend `99 < chance` ;
  3. `PileInAbility` (`IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateBehaviour` =
     `If(Maybe(chance), Spawn(...), Nothing())`) tire UN `next_bool` par grot candidat -- le port
     d'avant n'en tirait AUCUN (gate DETERMINISTE) ;
  4. `LetTheGalaxyBurnAbility` (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.
     LetTheGalaxyBurnAbility$$CreateTrigger` = `((On(5) & OwnerIsCaster) & Maybe(chance)) &
     !HasTileStatusEffect(Targets@0x190)`) tire AVANT le gate de tuile -- donc AUSSI quand la pose
     est impossible (`IdunBattle.DSL.MultipleAbilityTrigger$$ShouldTrigger` = gauche puis droite) ;
  5. LIVE, bit-exact : le compte de `genrand_int32` d'un `endturn` natif portant un PileIn eligible
     est reproduit par le port (mesure par re-simulation du MT via `dumpRng` avant/apres).

L'ancrage LIVE etendu (plusieurs seeds, dont le cas d'ECHEC du tirage) vit dans
`probe_o4a_maybe_trigger_rng.py`.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from engine.dsl.base import Const
from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.triggers import MaybeTrigger
from engine.runner.components import UnitComponent, OwnerComponent, HealthComponent
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.state import State

# Montage NOMME du scenario PileIn (naissance du grot, age, comptage MT) — source unique,
# partagee avec `test_pilein_owner_turns_live.py`.
from ._pilein_owner_turns import (BOARD, CARRIER, ENEMY, ESCORT, CountingRng as _CountingRng,
                                  count_genrand as _count_genrand, drive_and_attack as _drive_and_attack,
                                  pilein_units as _pilein_units)

PYDIR = Path(__file__).resolve().parents[3]
ROOT = PYDIR.parents[1]
MIN_AGE = 2                       # tours a laisser vieillir le grot (`OwnerHasFinishedMinTurns(2)`)


def _rng(seed: int) -> IntBasedMersenneTwister:
    r = IntBasedMersenneTwister()
    r.init_genrand(seed)
    return r


# ------------------------------------------------------------------ (1)(2) le noeud

@pytest.mark.parametrize("chance", [1, 25, 33, 75, 99, 100])
def test_maybe_trigger_consumes_exactly_one_roll(chance):
    """`MaybeTrigger` = `NextBool(chance)` : MEME verdict, MEME consommation qu'un `next_bool` seul."""
    r = _CountingRng(20260727)
    verdict = MaybeTrigger(r, Const(chance)).should_trigger(None)
    ref = _CountingRng(20260727)
    assert verdict == ref.next_bool(chance), "le verdict n'est pas celui de NextBool(chance)"
    assert r.rolls == ref.rolls >= 1, f"consommation MT divergente ({r.rolls} vs {ref.rolls})"


@pytest.mark.parametrize("chance,expected", [(0, False), (33, False), (99, False),
                                             (100, True), (150, True)])
def test_maybe_trigger_without_rng_is_native_deterministic_branch(chance, expected):
    """Branche `!CanUseRandom` (face DECISION) : `return 99 < chance`, et AUCUN tirage.
    ROUGE sur le port d'avant, qui rendait `False` meme a `chance >= 100`."""
    assert MaybeTrigger(None, Const(chance)).should_trigger(None) is expected


# ------------------------------------------------------------------ (3) PileIn : 1 tirage / grot

def _state_with_grots(n_grots: int, player: int = 0, rng=None) -> State:
    """`State` minimal : `n_grots` porteurs de `PileIn` vivants, a PV PLEINS, du meme joueur.
    Pas de board -> `execute_pilein_replica` no-ope, ce qui ISOLE le cout RNG du seul GATE."""
    st = State()
    st.rng = rng
    st.current_player_id = player
    for i in range(n_grots):
        e = st.add_entity(100 + i)
        uc = UnitComponent(visual_id="orksNpc1Grot", alive=True)
        # `OwnerHasFinishedMinTurns(2)` = `GetTurnsFinished(owner) >= 2` (`BaseUnitComponent + 0x5c`),
        # PER-UNITE -- surtout pas le compteur JOUEUR `turn_counts` (cf. test_pilein_owner_turns_live).
        uc.turns_finished = 2
        e.add_component(uc)
        e.add_component(OwnerComponent(team=player, player=player))
        e.add_component(HealthComponent(hp=1000, hp_max=1000))
    return st


@pytest.mark.parametrize("n_grots", [1, 2, 3])
def test_pilein_gate_rolls_once_per_candidate(n_grots):
    """`If(Maybe(chance), Spawn, Nothing)` : UN `next_bool` par grot candidat.
    ROUGE sur le port d'avant (gate `Maybe` non modelise -> 0 tirage, fire deterministe)."""
    from engine.runner.operations.triggers.dispatch import end_turn_summon_triggers
    r = _CountingRng(4242)
    st = _state_with_grots(n_grots, rng=r)
    end_turn_summon_triggers(st, 0)
    assert r.rolls == n_grots, \
        f"{r.rolls} tirages pour {n_grots} candidats (attendu 1 `next_bool` chacun)"


def test_pilein_gate_verdict_matches_native_next_bool():
    """Le verdict du gate est celui de `NextBool(75 - 5*n)` sur le MEME etat MT -- pas une
    reimplementation approchee (`next_internal(0,100) <`, borne 100, en serait une)."""
    from engine.runner.operations.triggers.dispatch import end_turn_summon_triggers
    import gameconfig as GC
    consts = (GC.ability("PileIn") or {}).get("constants") or {}
    chance = int(consts.get("chance") or 75)        # n = 0 autre grot -> pas de decote
    for seed in (1, 2, 3, 5, 8, 13, 21, 34):
        st = _state_with_grots(1, rng=_rng(seed))
        out = end_turn_summon_triggers(st, 0)
        # sans board le spawn no-ope : ce qu'on lit ici est la CONSOMMATION du gate, pas le spawn.
        expected = _rng(seed).next_bool(chance)
        st2 = _state_with_grots(1, rng=_rng(seed))
        end_turn_summon_triggers(st2, 0)
        assert (st.rng.mt, st.rng.mti) == (st2.rng.mt, st2.rng.mti), "flux non deterministe"
        assert isinstance(out, list)
        # le gate a bien consomme le tirage correspondant a `expected` (l'etat MT le prouve)
        ref = _rng(seed)
        ref.next_bool(chance)
        assert (st.rng.mt, st.rng.mti) == (ref.mt, ref.mti), \
            f"seed {seed} : le gate n'a pas consomme exactement `NextBool({chance})`"
        assert expected in (True, False)


# ------------------------------------------------------------------ (4) LetTheGalaxyBurn : l'ORDRE

@pytest.mark.parametrize("tile_effects,expected_match", [([], True), (["Fire"], False)])
def test_ltgb_rolls_before_the_tile_gate(monkeypatch, tile_effects, expected_match):
    """Le `Maybe` precede `!HasTileStatusEffect` dans la conjonction native : le tirage est consomme
    SUR LES DEUX BRANCHES. ROUGE sur le port d'avant, qui evaluait le gate de tuile d'abord et ne
    consommait RIEN quand la pose etait impossible."""
    import engine.runner.operations.triggers.loki.let_the_galaxy_burn as LTGB
    from engine.runner.operations.triggers.base import TriggerEvent

    monkeypatch.setattr(LTGB, "_target_tile_effects", lambda st, tid: list(tile_effects))
    r = _CountingRng(31337)
    st = State()
    st.rng = r
    st.current_player_id = 0
    for eid, team in ((1, 0), (2, 1)):
        e = st.add_entity(eid)
        e.add_component(UnitComponent(visual_id="blackTerminator" if eid == 1 else ENEMY, alive=True))
        e.add_component(OwnerComponent(team=team, player=team))
        e.add_component(HealthComponent(hp=1000, hp_max=1000))
    ab = LTGB.LetTheGalaxyBurnArmAbility.__new__(LTGB.LetTheGalaxyBurnArmAbility)
    ab.owner_id = 1
    ev = TriggerEvent(EventTriggerType.PreAttack, 1, 2, ranged=False, profile=None)
    got = ab.matches(st, ev)
    assert r.rolls == 1, f"{r.rolls} tirages (attendu 1 sur les DEUX branches du gate de tuile)"
    if expected_match:
        # tuile nue : le verdict EST celui du tirage
        ref = _CountingRng(31337)
        from engine.entities.effects.magnitude import trait_var
        pct = int(trait_var("LetTheGalaxyBurn", "LetTheGalaxyBurnChancePct") or 0)
        assert got is ref.next_bool(pct)
    else:
        assert got is False                          # tuile a effet : pose impossible malgre le roll


@pytest.mark.parametrize("seed", [1, 7, 11, 13, 14, 15, 16, 18, 19, 21])
def test_ltgb_uses_the_native_next_bool_primitive(monkeypatch, seed):
    """La primitive EST `NextBool(chance)` = `next_internal(1, 100) <= chance` (borne **99**), pas
    `next_internal(0, 100) < chance` (borne 100) : sur un MEME etat MT les deux verdicts DIVERGENT
    (mesure : 90 graines sur 199 a chance=33, `r % 99` et `r % 100` etant decorreles) -- ce n'est
    donc pas un ecart seulement statistique. Les graines listees sont precisement des divergences."""
    import engine.runner.operations.triggers.loki.let_the_galaxy_burn as LTGB
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.entities.effects.magnitude import trait_var

    monkeypatch.setattr(LTGB, "_target_tile_effects", lambda st, tid: [])
    pct = int(trait_var("LetTheGalaxyBurn", "LetTheGalaxyBurnChancePct") or 0)
    st = State()
    st.rng = _rng(seed)
    st.current_player_id = 0
    for eid, team in ((1, 0), (2, 1)):
        e = st.add_entity(eid)
        e.add_component(UnitComponent(visual_id="blackTerminator" if eid == 1 else ENEMY, alive=True))
        e.add_component(OwnerComponent(team=team, player=team))
        e.add_component(HealthComponent(hp=1000, hp_max=1000))
    ab = LTGB.LetTheGalaxyBurnArmAbility.__new__(LTGB.LetTheGalaxyBurnArmAbility)
    ab.owner_id = 1
    got = ab.matches(st, TriggerEvent(EventTriggerType.PreAttack, 1, 2, ranged=False, profile=None))
    assert got is _rng(seed).next_bool(pct), \
        f"seed {seed} : verdict {got} != NextBool({pct}) (primitive non native)"


# ------------------------------------------------------------------ (5) LIVE : le compte bit-exact
# (`_count_genrand` / `_pilein_units` / `_drive_and_attack` viennent de `_pilein_owner_turns`.)

@pytest.mark.parametrize("seed", ["777"])
def test_pilein_endturn_roll_count_matches_live(rpc, seed):
    """LIVE, bit-exact. Un `endturn` natif portant UN grot PileIn eligible consomme un nombre de
    `genrand_int32` que le port reproduit EXACTEMENT (1 `next_bool` de gate, puis les tirages du
    `Randomize` de placement UNIQUEMENT si le gate a reussi).

    Le port d'avant divergeait des deux cotes : -1 tirage quand le gate reussit (pas de `next_bool`),
    +3 et un grot FANTOME quand il echoue (`Randomize` paye + spawn deterministe)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.operations.triggers.dispatch import end_turn_summon_triggers

    sf = ROOT / "logs" / "runners" / ("o4a-pilein-test-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
         "--board", BOARD, "--roster", "1", "--p-units", f"{CARRIER},{ESCORT}",
         "--a-units", f"{ENEMY},{ENEMY}", "--hp-target", "90000", "--hp-player", "90000", "--no-ai"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        pytest.skip("build KO: " + (proc.stderr or proc.stdout or "")[-300:])
    rid = json.loads(sf.read_text())["runnerId"]
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")

        def dview():
            return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)

        dv = dview()
        me = next((u for u in (dv.get("units") or []) if u.get("visualId") == CARRIER), None)
        if me is None:
            pytest.skip(f"{CARRIER} absent")
        mine = me["owner"]
        birth, my_turns, measured = {}, 0, None
        for _ in range(12):
            dv = dview()
            if dv.get("currentPlayer") != mine:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                continue
            grots = _pilein_units(dv, mine)
            for uid in grots:
                birth.setdefault(uid, my_turns)
            if not grots:
                _drive_and_attack(rpc, rid, board, mine)
                dv = dview()
                grots = _pilein_units(dv, mine)
                for uid in grots:
                    birth.setdefault(uid, my_turns)
            ages = [my_turns - birth[u] for u in grots]
            if len(grots) != 1 or min(ages, default=0) < MIN_AGE:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                my_turns += 1
                continue
            ob = rpc("observeBattle", {"runnerId": rid}, 60)
            snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
            rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
            act = rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            assert isinstance(act, dict) and act.get("ok"), f"endturn KO: {str(act)[:200]}"
            my_turns += 1
            rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
            live_n = _count_genrand(rng0, rng1)
            live_spawn = len(_pilein_units(dview(), mine) - grots)

            st = load_state(dv, ob, snap, board=board)
            # SEED MANUEL de `turnsFinished` (`BaseUnitComponent + 0x5c`) : aucun RPC ne l'expose
            # (ce n'est PAS un `StatType`), donc `load_state` part a 0 -> gate FERME a tort. La
            # valeur posee est l'age OBSERVE du grot + 1 : le natif bumpe le compteur AVANT
            # d'executer `On(0x17)`, et ce test appelle le VECTEUR seul (pas `EndTurnOperation`).
            for g in grots:
                ge = st.get_entity(g)
                guc = ge.get_component(UnitComponent) if ge is not None else None
                if guc is not None:
                    guc.turns_finished = my_turns - birth[g] + 1
            r = _CountingRng()
            r.mt = list(rng0["mt"])
            r.mti = int(rng0["mti"])
            st.rng = r
            out = end_turn_summon_triggers(st, int(mine))
            port_spawn = sum(len(o.get("spawned") or ()) for o in out
                             if isinstance(o, dict) and "grot" in o)
            measured = (live_n, live_spawn, r.rolls, port_spawn)
            break
        if measured is None:
            pytest.skip("aucun endturn avec exactement 1 porteur PileIn eligible en 12 tours")
        live_n, live_spawn, port_n, port_spawn = measured
        assert port_n == live_n, \
            f"compte de tirages: port={port_n} live={live_n} (le gate `Maybe` doit valoir 1 tirage)"
        assert port_spawn == live_spawn, \
            f"spawns: port={port_spawn} live={live_spawn} (verdict du gate divergent)"
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        sf.unlink(missing_ok=True)
