"""case-66 — TaintedNarthecium revive-EN-PLACE (deathRotbone, base ReviveEffect).

`TaintedNarthecium_ReviveEffect` (IdunBattle.Entities.Effects.Loki.TaintedNarthecium_ReviveEffect$$.ctor / filter IdunBattle.Entities.Effects.Loki.TaintedNarthecium_ReviveEffect$$CreateTargetFilter, base ReviveEffect
IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger / IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour) : un allie Chaos adjacent(2)
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
from engine.runner.operations.triggers.dispatch.move_death import after_death_triggers
from engine.runner.operations.revive import (reset_revive_gates, ReviveUnitOperation,
                                             post_pending_revive, kill_unit_revive_gate)
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
    """dr au centre (>=3 voisins), allie a DISTANCE HEX `dist`. Renvoie True si place.

    ⚠ La cible est la distance HEX, pas le nombre de PAS de graphe (les deux divergent des qu'un
    obstacle force un detour) : un BFS arrete au 2e pas peut atterrir a distance hex 1, ce qui
    rendrait le bras `dist=2` VACU."""
    import hexgeo
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
    dst = next((c for c in sorted(board.by_coord)
                if hexgeo.distance(center, c) == dist
                and board.walkable(board.id_at(*c))), None)
    if dst is None:
        return False
    _pc(st, ally_uid).col, _pc(st, ally_uid).row = dst
    return True


def _kill(env, st, ally_uid, overkill=False):
    """Mirror de la sequence de `IdunBattle.Operations.KillUnitOperation$$Execute` : `On(1)` @IdunBattle.Operations.KillUnitOperation$$Execute+0x7dc PUIS la
    GARDE @IdunBattle.Operations.KillUnitOperation$$Execute+0x82e (`kill_unit_revive_gate`) dont la branche `else` consomme la
    `ReviveData` posee par la feuille `Revive` -- DANS `KillUnitOperation$$Execute`, PAS dans une
    phase (#477-r24 : `RunPhase(PhaseType.ProcessRemovals /*0xd*/)` draine les RETRAITS).
    Sans la garde, la feuille ne fait que POSER : rien ne serait applique (RE case-89 volet C)."""
    _hc(st, ally_uid).hp = 0
    _uc(st, ally_uid).alive = False
    out = after_death_triggers(st, dying_id=ally_uid, killer_id=env["ids"]["dr"], overkill=overkill)
    kill_unit_revive_gate(st, ally_uid)
    return out


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


@pytest.mark.parametrize("dist", [2, 3])
def test_adjacency_is_strict(rev_env, dist):
    """`IsAdjacent(self, target, 2)` : le `2` est un `UnitSelectionType`, PAS un rayon
    (#462-r4b-r1-r1-r1-r1-b-r1) -- l'ADJACENCE EST STRICTE, un allie Chaos a distance 2 n'est
    DEJA plus revive.

    ⚠ Le bras `dist=2` est LE discriminant, et c'est celui qui manquait : l'ancien test ne jouait
    que `dist=3`, ou `distance <= 2` et `adjacence stricte` rendent la MEME reponse -- regime
    DEGENERE. Controle `dist=1` : `test_revive_base_hp_and_position`."""
    import hexgeo
    env = rev_env
    st = _fresh(env, _seed_bool(env["chance"], True))
    if not _place(env, st, env["ids"]["chaos"], dist):
        pytest.skip("pas de tuile a dist %d" % dist)
    pdr = (_pc(st, env["ids"]["dr"]).col, _pc(st, env["ids"]["dr"]).row)
    pch = (_pc(st, env["ids"]["chaos"]).col, _pc(st, env["ids"]["chaos"]).row)
    assert hexgeo.distance(pdr, pch) == dist, "placement a dist %d (attendu %d)" % (
        hexgeo.distance(pdr, pch), dist)
    _kill(env, st, env["ids"]["chaos"])
    assert not _uc(st, env["ids"]["chaos"]).alive, \
        "allie a dist %d revive : le `2` d'IsAdjacent a ete relu comme un rayon" % dist


def test_can_be_revived_mechanical(rev_env):
    """CanBeRevived : un allie Chaos Mechanical (toggle sur ctx.traits) -> PAS de revive
    (IsAffectedByHealType = HasTrait(AffectedByHealAndRepair) OR NOT IsMechanical)."""
    from engine.runner.abilities.behaviours.context import entities_from_state
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
    """SetHealth clamp : maxHP < reviveHP -> hp = maxHP (ReviveUnitOperation IdunBattle.Operations.ReviveUnitOperation$$SetHealth), in-place.
    Offline pur. La signature NATIVE est `Execute(operation, entity)` : le HP vient de la `ReviveData`
    posee sur `UnitComponent+0xa8` (`post_pending_revive`), pas d'un parametre."""
    from engine.runner.state import State
    st = State()
    e = st.add_entity()
    e.add_component(UnitComponent("x", False))
    e.add_component(HealthComponent(0, 1200))              # hp=0, hp_max=1200
    e.add_component(PositionComponent(3, 4))
    post_pending_revive(st, e.id, 4887)                    # reviveHP 4887 > maxHP 1200
    ReviveUnitOperation.execute(st, e.id)
    assert int(e.get_component(HealthComponent).hp) == 1200, "hp non clampe a maxHP"
    assert e.get_component(UnitComponent).alive, "non revive"
    assert (e.get_component(PositionComponent).col, e.get_component(PositionComponent).row) == (3, 4), "position changee"
    assert e.get_component(UnitComponent).pending_revive is None, "ReviveData non purgee (@IdunBattle.Operations.ReviveUnitOperation$$Execute+0xda7+)"


def test_pending_revive_cancels_the_kill_offline():
    """GARDE @IdunBattle.Operations.KillUnitOperation$$Execute+0x81c (case-89 volet C) : une `ReviveData` posee pendant `On(1)` fait ECHOUER la
    garde de `KillUnitOperation.Execute` -> `On(2)` / `On(0)` / `On(54 = UnitDefeated)` ne sont PAS emis.
    (`On(53 = PostUnitKill)`, lui, l'EST : il vit apres le `if/else` de la garde -- corrige en
    #462-r4b-r1-r1-r1-r1-c-r3-r1-r4, ou la pile d'accolades a remplace la profondeur comme critere.)
    Ici on verifie le contrat de `kill_unit_revive_gate` : rend un dict (mort ANNULEE) vs None."""
    from engine.runner.state import State
    st = State()
    e = st.add_entity()
    e.add_component(UnitComponent("x", False))
    e.add_component(HealthComponent(0, 1000))
    assert kill_unit_revive_gate(st, e.id) is None, "garde franchie a tort (aucun revive en attente)"
    post_pending_revive(st, e.id, 300)
    r = kill_unit_revive_gate(st, e.id)
    assert r is not None and r.get("revived") == e.id, "la garde n'a pas court-circuite la mort"
    assert e.get_component(UnitComponent).alive, "unite non revive par le drain de la garde"
    assert int(e.get_component(HealthComponent).hp) == 300


def test_is_preferred_revive_offline():
    """`IdunBattle.Entities.Behaviours.ReviveBehaviour$$IsPreferredRevive` : priorite d'abord, puis amount le plus GRAND.
    (PhoenixGem pose priority=-1000 -> tout autre revive lui est prefere.)"""
    from engine.runner.operations.revive import is_preferred_revive
    assert is_preferred_revive(None, {"priority": -1000, "amount": 1})
    assert is_preferred_revive({"priority": -1000, "amount": 9999}, {"priority": 0, "amount": 1})
    assert not is_preferred_revive({"priority": 0, "amount": 1}, {"priority": -1000, "amount": 9999})
    assert is_preferred_revive({"priority": 0, "amount": 100}, {"priority": 0, "amount": 200})
    assert not is_preferred_revive({"priority": 0, "amount": 200}, {"priority": 0, "amount": 100})
