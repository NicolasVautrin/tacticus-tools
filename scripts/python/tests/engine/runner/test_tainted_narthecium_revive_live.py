"""case-66 — TaintedNarthecium revive-EN-PLACE (deathRotbone, base ReviveEffect).

`TaintedNarthecium_ReviveEffect` (ctor @180f70a90 / filter @180f709b0, base ReviveEffect
CreateTargetTrigger @180f46d80 / CreateTargetTriggerBehaviour @180f46a70) : un allie Chaos adjacent(2)
vaincu a 75% de chance d'etre revive-EN-PLACE a min(reviveHP[level], maxPV), even-if-Overkilled,
once-per-turn. i2 : « An adjacent friendly Chaos unit that is defeated has a {chance}% chance to be
revived with a maximum of {hp} Health, even if Overkilled. Can only be triggered once per turn. »

METHODE (mirror test_finaljustice/test_revitalizing_malignancy, DETERMINISTE) : etat REEL (board+stats via
load_state), positions DRIVEES (allie Chaos adjacent au caster), mort simulee via after_death_triggers
(event 1), RNG SEEDEE (patron etat_avec/etat_flip). Frontiere #149 : trigger DSL au-dessus, ReviveUnitOperation
imperative en-dessous. ASCII only ; adjacence evenq.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.operations.triggers import after_death_triggers
from engine.runner.operations.revive import reset_revive_gates, ReviveUnitOperation
from engine.runner.components import (UnitComponent, HealthComponent, OwnerComponent,
                                      PositionComponent, StatsComponent)
from engine.runner.prng import IntBasedMersenneTwister
from engine.entities.pathfinding.board import Board
from engine.entities.effects.magnitude import ability_var
from engine.entities.traits.unit_trait import UnitTrait

CASTER = "deathRotbone"          # passif TaintedNarthecium (Death Guard, GrandAlliance Chaos)
ALLY_CHAOS = "deathBlightbringer"  # Chaos alliance -> revivable
ALLY_XENOS = "eldarRanger"         # Xenos alliance -> EXCLU (HasTrait Chaos)
BUILD = ["--p-units", f"{CASTER},{ALLY_CHAOS},{ALLY_XENOS}", "--a-units", "worldKharn,ultraTitus",
         "--rank", "17", "--hp-player", "300000"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _by_vis(state, vis):
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
            return uid
    return None


def _pc(state, uid):
    return state.get_entity(uid).get_component(PositionComponent)


def _hc(state, uid):
    return state.get_entity(uid).get_component(HealthComponent)


def _uc(state, uid):
    return state.get_entity(uid).get_component(UnitComponent)


def _rng(seed):
    return IntBasedMersenneTwister(seed)


def _seed_bool(chance, want):
    """1er seed dont next_bool(chance) == want."""
    for s in range(1, 5000):
        if IntBasedMersenneTwister(s).next_bool(chance) == want:
            return s
    return None


@pytest.fixture(scope="module")
def rev_env(live_session, rpc, build_runner):
    rid = build_runner("777", extra=BUILD)["rid"]
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
    ids = {"dr": _by_vis(st0, CASTER), "chaos": _by_vis(st0, ALLY_CHAOS), "xenos": _by_vis(st0, ALLY_XENOS)}
    if any(v is None for v in ids.values()):
        pytest.skip("roster incomplet offline: %s" % ids)
    sc = st0.get_entity(ids["dr"]).get_component(StatsComponent)
    plvl = getattr(sc.ctx, "passive_ability_level", None)
    mult = getattr(sc.ctx, "ability_variables_multiplier", 100)
    return {"dv": dv, "ob": ob, "snap": snap, "board": board, "ids": ids,
            "revive_hp": ability_var("TaintedNarthecium", "hp", plvl, multiplier_pct=mult),
            "chance": int(ability_var("TaintedNarthecium", "chance", is_constant=True))}


def _fresh(env, seed=None):
    st = load_state(env["dv"], env["ob"], env["snap"], board=env["board"])
    if seed is not None:
        st.rng = _rng(seed)
    return st


def _place(env, st, ally_uid, dist):
    """dr au centre (>=3 voisins), allie a distance hex `dist`. Renvoie True si place."""
    board = env["board"]
    center = None
    for uid, e in st.entities.items():
        pc = e.get_component(PositionComponent)
        if pc is None:
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None and len([n for n in board.neighbours(t) if board.walkable(n)]) >= 3:
            center = board.coord(t); break
    if center is None:
        return False
    _pc(st, env["ids"]["dr"]).col, _pc(st, env["ids"]["dr"]).row = center
    ctile = board.id_at(*center)
    if dist == 1:
        dst = next((board.coord(n) for n in board.neighbours(ctile) if board.walkable(n)), None)
    else:
        from collections import deque
        seen = {ctile: 0}; q = deque([ctile]); dst = None
        while q:
            x = q.popleft()
            if seen[x] == dist and board.walkable(x):
                dst = board.coord(x); break
            for n in board.neighbours(x):
                if n not in seen:
                    seen[n] = seen[x] + 1; q.append(n)
    if dst is None:
        return False
    _pc(st, ally_uid).col, _pc(st, ally_uid).row = dst
    return True


def _kill(env, st, ally_uid, overkill=False):
    _hc(st, ally_uid).hp = 0
    _uc(st, ally_uid).alive = False
    return after_death_triggers(st, dying_id=ally_uid, killer_id=env["ids"]["dr"], overkill=overkill)


def test_revive_base_hp_and_position(rev_env):
    """RNG True : allie Chaos adjacent tue -> alive, hp=min(reviveHP,maxHP), MEME position."""
    env = rev_env
    st = _fresh(env, _seed_bool(env["chance"], True))
    assert _place(env, st, env["ids"]["chaos"], 1), "placement adjacent KO"
    pos0 = (_pc(st, env["ids"]["chaos"]).col, _pc(st, env["ids"]["chaos"]).row)
    maxhp = int(_hc(st, env["ids"]["chaos"]).hp_max)
    exp = min(int(env["revive_hp"]), maxhp)
    res = _kill(env, st, env["ids"]["chaos"])
    assert _uc(st, env["ids"]["chaos"]).alive, "allie Chaos non revive (RNG True)"
    assert int(_hc(st, env["ids"]["chaos"]).hp) == exp, "hp %d != min(reviveHP,maxHP)=%d" % (
        int(_hc(st, env["ids"]["chaos"]).hp), exp)
    assert (_pc(st, env["ids"]["chaos"]).col, _pc(st, env["ids"]["chaos"]).row) == pos0, "position CHANGEE (pas in-place)"
    assert any(r.get("ability") == "TaintedNarthecium" for r in res), "trigger TaintedNarthecium absent: %s" % res


def test_revive_rng_false_no_revive(rev_env):
    """RNG False : le roll rate -> PAS de revive."""
    env = rev_env
    st = _fresh(env, _seed_bool(env["chance"], False))
    _place(env, st, env["ids"]["chaos"], 1)
    _kill(env, st, env["ids"]["chaos"])
    assert not _uc(st, env["ids"]["chaos"]).alive, "revive alors que RNG False"


def test_revive_probability_75(rev_env):
    """Maybe(75%) : ~75% de revives sur N morts avec RNG frais (Maybe next_bool(75))."""
    env = rev_env
    N, rev = 150, 0
    for s in range(1, N + 1):
        st = _fresh(env, s)
        _place(env, st, env["ids"]["chaos"], 1)
        _kill(env, st, env["ids"]["chaos"])
        if _uc(st, env["ids"]["chaos"]).alive:
            rev += 1
    pct = 100.0 * rev / N
    assert 68.0 <= pct <= 82.0, "proba %.1f%% hors bande ~75%% (%d/%d)" % (pct, rev, N)


def test_once_per_turn(rev_env):
    """once-per-turn : revive #1 consomme le gate ; 2e mort MEME tour -> PAS de revive ;
    apres reset_revive_gates (turn-start) -> revive de nouveau."""
    env = rev_env
    s = _seed_bool(env["chance"], True)
    st = _fresh(env, s)
    _place(env, st, env["ids"]["chaos"], 1)
    _kill(env, st, env["ids"]["chaos"])
    assert _uc(st, env["ids"]["chaos"]).alive, "revive #1 attendu"
    assert _uc(st, env["ids"]["dr"]).revive_used_this_turn, "gate non consomme apres revive"
    _kill(env, st, env["ids"]["chaos"])                     # 2e mort meme tour
    assert not _uc(st, env["ids"]["chaos"]).alive, "2e revive MEME tour (gate non respecte)"
    reset_revive_gates(st)                                  # turn-start -> reactive
    st.rng = _rng(s)
    _kill(env, st, env["ids"]["chaos"])
    assert _uc(st, env["ids"]["chaos"]).alive, "pas de revive apres reset (once-per-turn mal reactive)"


def test_even_if_overkilled(rev_env):
    """even-if-Overkilled : mort overkill=True -> revive quand meme (aucun gate overkill, byte 0x738 non-nul)."""
    env = rev_env
    st = _fresh(env, _seed_bool(env["chance"], True))
    _place(env, st, env["ids"]["chaos"], 1)
    _kill(env, st, env["ids"]["chaos"], overkill=True)
    assert _uc(st, env["ids"]["chaos"]).alive, "overkill a bloque le revive (TaintedNarthecium = even-if-Overkilled)"


def test_chaos_only(rev_env):
    """HasTrait(target, Chaos) : un allie NON-Chaos (Xenos) adjacent tue -> PAS de revive."""
    env = rev_env
    st = _fresh(env, _seed_bool(env["chance"], True))
    _place(env, st, env["ids"]["xenos"], 1)
    _kill(env, st, env["ids"]["xenos"])
    assert not _uc(st, env["ids"]["xenos"]).alive, "allie Xenos revive (filtre Chaos non respecte)"


def test_adjacency_range_2(rev_env):
    """IsAdjacent(self,target,2) : un allie Chaos a distance hex 3 -> PAS de revive."""
    import hexgeo
    env = rev_env
    st = _fresh(env, _seed_bool(env["chance"], True))
    if not _place(env, st, env["ids"]["chaos"], 3):
        pytest.skip("pas de tuile a dist 3")
    pdr = (_pc(st, env["ids"]["dr"]).col, _pc(st, env["ids"]["dr"]).row)
    pch = (_pc(st, env["ids"]["chaos"]).col, _pc(st, env["ids"]["chaos"]).row)
    if hexgeo.distance(pdr, pch) <= 2:
        pytest.skip("placement a dist<=2 (board coin)")
    _kill(env, st, env["ids"]["chaos"])
    assert not _uc(st, env["ids"]["chaos"]).alive, "allie a dist>2 revive (adjacence non respectee)"


def test_can_be_revived_mechanical(rev_env):
    """CanBeRevived : un allie Chaos Mechanical (toggle sur ctx.traits) -> PAS de revive
    (IsAffectedByHealType = HasTrait(AffectedByHealAndRepair) OR NOT IsMechanical)."""
    from engine.runner.abilities.behaviours import entities_from_state
    from engine.runner.abilities.behaviours.stats import is_mechanical
    env = rev_env
    st = _fresh(env, _seed_bool(env["chance"], True))
    _place(env, st, env["ids"]["chaos"], 1)
    sc = st.get_entity(env["ids"]["chaos"]).get_component(StatsComponent)
    sc.ctx.traits = list(getattr(sc.ctx, "traits", None) or []) + ["Mechanical"]
    ent = entities_from_state(st, env["ids"]["dr"], env["ids"]["chaos"])
    assert is_mechanical(ent.has_trait, ent.target), "toggle Mechanical non vu par has_trait"
    _kill(env, st, env["ids"]["chaos"])
    assert not _uc(st, env["ids"]["chaos"]).alive, "allie Mechanical revive (CanBeRevived non respecte)"


def test_clamp_maxhp_below_revivehp_offline():
    """SetHealth clamp : maxHP < reviveHP -> hp = maxHP (ReviveUnitOperation @180e93450), in-place. Offline pur."""
    from engine.runner.state import State
    st = State()
    e = st.add_entity()
    e.add_component(UnitComponent("x", False))
    e.add_component(HealthComponent(0, 1200))              # hp=0, hp_max=1200
    e.add_component(PositionComponent(3, 4))
    ReviveUnitOperation.execute(st, e.id, 4887)            # reviveHP 4887 > maxHP 1200
    assert int(e.get_component(HealthComponent).hp) == 1200, "hp non clampe a maxHP"
    assert e.get_component(UnitComponent).alive, "non revive"
    assert (e.get_component(PositionComponent).col, e.get_component(PositionComponent).row) == (3, 4), "position changee"
