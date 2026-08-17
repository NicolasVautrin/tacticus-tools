"""#79 (retrofit case-66) -- Narthecium revive-EN-PLACE (ultraApothecary, base ReviveEffect).

`Narthecium_ReviveEffect` (IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$.ctor / filter IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$CreateTargetFilter, base ReviveEffect IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger / IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour) : un allie adjacent(2) non-Mechanical vaincu est
revive-EN-PLACE a min(reviveHP[level], maxPV), **unless Overkilled**, once-per-turn, chance=100.
i2 : « When an adjacent friendly non-Mechanical unit is defeated, it is immediately revived with a maximum
of {hp} Health, unless Overkilled. Can only be triggered once per turn. »

DISCRIMINANT vs TaintedNarthecium (le point le plus facile a rater) : `get_ReviveOnOverkill @vtable+0x738`
= GameCamera$$ShouldBlurBackground `return 0` pour Narthecium (et la base) vs GameCamera$$get_ShouldDisableRenderingWhenBehindSomething `return 1` pour TaintedNarthecium (lu
LIVE, `probe_79_revive_vtable.py`). Byte==0 -> `IdunBattleLogic.Entities.DSLTriggers$$OnDeathEvent` AJOUTE `NOT(HasFlag(dying,
8=overkill))`. Les tests `test_overkill_blocks_revive` / `test_no_overkill_revives` opposent les deux faces.

METHODE (mirror test_tainted_narthecium_revive_live, DETERMINISTE) : etat REEL (board+stats via load_state),
positions DRIVEES, mort simulee via after_death_triggers (event 1). chance=100 -> le Maybe reussit toujours
(pas de seeding requis, mais on seede quand meme pour la reproductibilite). ASCII only ; adjacence evenq.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.operations.triggers.dispatch.move_death import after_death_triggers
from engine.runner.operations.revive import reset_revive_gates, kill_unit_revive_gate
from engine.runner.components import (UnitComponent, HealthComponent,
                                      PositionComponent, StatsComponent)
from engine.runner.prng import IntBasedMersenneTwister
from engine.entities.pathfinding.board import Board
from engine.entities.effects.magnitude import ability_var

CASTER = "ultraApothecary"        # passif Narthecium (Ultramarines / Imperial)
ALLY = "bloodIntercessor"         # allie non-Mechanical -> revivable
ALLY2 = "eldarRanger"             # 2e allie (aucun filtre d'alliance chez Narthecium -> revivable aussi)
BUILD = ["--p-units", f"{CASTER},{ALLY},{ALLY2}", "--a-units", "worldKharn,deathBlightbringer",
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


@pytest.fixture(scope="module")
def nar_env(live_session, rpc, build_runner):
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
    ids = {"ap": _by_vis(st0, CASTER), "ally": _by_vis(st0, ALLY), "ally2": _by_vis(st0, ALLY2)}
    if any(v is None for v in ids.values()):
        pytest.skip("roster incomplet offline: %s" % ids)
    sc = st0.get_entity(ids["ap"]).get_component(StatsComponent)
    plvl = getattr(sc.ctx, "passive_ability_level", None)
    mult = getattr(sc.ctx, "ability_variables_multiplier", 100)
    return {"dv": dv, "ob": ob, "snap": snap, "board": board, "ids": ids,
            "revive_hp": ability_var("Narthecium", "hp", plvl, multiplier_pct=mult),
            "chance": int(ability_var("Narthecium", "chance", is_constant=True))}


def _fresh(env, seed=777):
    st = load_state(env["dv"], env["ob"], env["snap"], board=env["board"])
    st.rng = IntBasedMersenneTwister(seed)
    return st


def _place(env, st, ally_uid, dist):
    """apothecary au centre (>=3 voisins), allie a DISTANCE HEX `dist`. True si place.

    ⚠ La cible est la distance HEX (`hexgeo.distance`), pas le nombre de PAS de graphe : les deux
    divergent des qu'un obstacle force un detour (pas de graphe >= distance hex), et un BFS qui
    s'arrete << au 2e pas >> peut atterrir sur une tuile a distance hex 1 -- ce qui rendrait le bras
    `dist=2` VACU (il mesurerait de l'adjacence). On balaie donc les tuiles par leur distance hex."""
    import hexgeo
    board = env["board"]
    center = None
    for uid, e in st.entities.items():
        pc = e.get_component(PositionComponent)
        if pc is None:
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None and len([n for n in board.neighbours(t) if board.walkable(n)]) >= 3:
            center = board.coord(t)
            break
    if center is None:
        return False
    _pc(st, env["ids"]["ap"]).col, _pc(st, env["ids"]["ap"]).row = center
    dst = next((c for c in sorted(board.by_coord)
                if hexgeo.distance(center, c) == dist
                and board.walkable(board.id_at(*c))), None)
    if dst is None:
        return False
    _pc(st, ally_uid).col, _pc(st, ally_uid).row = dst
    return True


def _kill(env, st, ally_uid, overkill=False):
    """`On(1)` @IdunBattle.Operations.KillUnitOperation$$Execute+0x7dc PUIS la GARDE @IdunBattle.Operations.KillUnitOperation$$Execute+0x82e (`kill_unit_revive_gate`) qui draine la
    `ReviveData` posee par la feuille `Revive` -- mirror de `KillUnitOperation.Execute` (case-89 volet C)."""
    _hc(st, ally_uid).hp = 0
    _uc(st, ally_uid).alive = False
    out = after_death_triggers(st, dying_id=ally_uid, killer_id=env["ids"]["ap"], overkill=overkill)
    kill_unit_revive_gate(st, ally_uid)
    return out


def test_revive_base_hp_and_position(nar_env):
    """chance=100 : allie adjacent tue (sans overkill) -> alive, hp=min(reviveHP,maxHP), MEME position."""
    env = nar_env
    st = _fresh(env)
    assert _place(env, st, env["ids"]["ally"], 1), "placement adjacent KO"
    pos0 = (_pc(st, env["ids"]["ally"]).col, _pc(st, env["ids"]["ally"]).row)
    maxhp = int(_hc(st, env["ids"]["ally"]).hp_max)
    exp = min(int(env["revive_hp"]), maxhp)
    res = _kill(env, st, env["ids"]["ally"])
    assert _uc(st, env["ids"]["ally"]).alive, "allie non revive (chance=100)"
    assert int(_hc(st, env["ids"]["ally"]).hp) == exp, "hp %d != min(reviveHP,maxHP)=%d" % (
        int(_hc(st, env["ids"]["ally"]).hp), exp)
    assert (_pc(st, env["ids"]["ally"]).col, _pc(st, env["ids"]["ally"]).row) == pos0, \
        "position CHANGEE (pas in-place)"
    assert any(r.get("ability") == "Narthecium" for r in res), "trigger Narthecium absent: %s" % res


def test_overkill_blocks_revive(nar_env):
    """**unless Overkilled** (get_ReviveOnOverkill GameCamera$$ShouldBlurBackground = 0) : mort en OVERKILL -> PAS de revive."""
    env = nar_env
    st = _fresh(env)
    assert _place(env, st, env["ids"]["ally"], 1)
    _kill(env, st, env["ids"]["ally"], overkill=True)
    assert not _uc(st, env["ids"]["ally"]).alive, \
        "revive malgre l'overkill (Narthecium = unless Overkilled)"
    assert not _uc(st, env["ids"]["ap"]).revive_used_this_turn, \
        "gate once-per-turn consomme alors que le trigger n'a pas du matcher"


def test_no_overkill_revives(nar_env):
    """Face opposee du meme scenario : MEME position, MEME mort, overkill=False -> revive.
    Le SEUL facteur qui change est le flag overkill."""
    env = nar_env
    st = _fresh(env)
    assert _place(env, st, env["ids"]["ally"], 1)
    _kill(env, st, env["ids"]["ally"], overkill=False)
    assert _uc(st, env["ids"]["ally"]).alive, "pas de revive sans overkill (attendu: revive)"


def test_once_per_turn(nar_env):
    """once-per-turn : revive #1 consomme le gate ; 2e mort MEME tour -> PAS de revive ;
    apres reset_revive_gates (turn-start) -> revive de nouveau."""
    env = nar_env
    st = _fresh(env)
    _place(env, st, env["ids"]["ally"], 1)
    _kill(env, st, env["ids"]["ally"])
    assert _uc(st, env["ids"]["ally"]).alive, "revive #1 attendu"
    assert _uc(st, env["ids"]["ap"]).revive_used_this_turn, "gate non consomme apres revive"
    _kill(env, st, env["ids"]["ally"])                     # 2e mort meme tour
    assert not _uc(st, env["ids"]["ally"]).alive, "2e revive MEME tour (gate non respecte)"
    reset_revive_gates(st)                                 # turn-start -> reactive
    _kill(env, st, env["ids"]["ally"])
    assert _uc(st, env["ids"]["ally"]).alive, "pas de revive apres reset (once-per-turn mal reactive)"


def test_no_alliance_filter(nar_env):
    """Narthecium n'a PAS de HasTrait dans son filtre (IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$CreateTargetFilter) : un allie d'une AUTRE grande alliance
    (Xenos) adjacent est revive -- contraste TaintedNarthecium (IdunBattle.Entities.Effects.Loki.TaintedNarthecium_ReviveEffect$$CreateTargetFilter, Chaos-only)."""
    env = nar_env
    st = _fresh(env)
    assert _place(env, st, env["ids"]["ally2"], 1)
    _kill(env, st, env["ids"]["ally2"])
    assert _uc(st, env["ids"]["ally2"]).alive, "allie Xenos non revive (Narthecium n'a pas de filtre trait)"


@pytest.mark.parametrize("dist", [2, 3])
def test_adjacency_is_strict(nar_env, dist):
    """`IsAdjacent(self, target, 2)` : le `2` est un `UnitSelectionType`, PAS un rayon
    (#462-r4b-r1-r1-r1-r1-b-r1) -- donc l'ADJACENCE EST STRICTE et un allie a distance 2 n'est
    DEJA plus revive.

    ⚠ Le bras `dist=2` est LE discriminant, et c'est celui qui manquait : l'ancien test ne jouait
    que `dist=3`, ou le modele `distance <= 2` et le modele `adjacence stricte` rendent la MEME
    reponse -- un regime DEGENERE, qui ne prouvait rien du 3e argument. Le controle `dist=1` vit
    dans `test_revive_base_hp_and_position`.
    Chaine lue (rnca9r7q6c) : `IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent(a, b, selectionType)`
    -> `IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$.ctor` (`(int)selectionType` en
    `+0x18`) -> `$$ShouldTrigger`, ou `+0x18` ne sert QU'aux deux `Select` et le predicat de paire
    est `query.AreEntitiesAdjacent(x, y)` (slot 0x60), sans rayon."""
    import hexgeo
    env = nar_env
    st = _fresh(env)
    if not _place(env, st, env["ids"]["ally"], dist):
        pytest.skip("pas de tuile a dist %d" % dist)
    pap = (_pc(st, env["ids"]["ap"]).col, _pc(st, env["ids"]["ap"]).row)
    pal = (_pc(st, env["ids"]["ally"]).col, _pc(st, env["ids"]["ally"]).row)
    assert hexgeo.distance(pap, pal) == dist, "placement a dist %d (attendu %d)" % (
        hexgeo.distance(pap, pal), dist)
    _kill(env, st, env["ids"]["ally"])
    assert not _uc(st, env["ids"]["ally"]).alive, \
        "allie a dist %d revive : le `2` d'IsAdjacent a ete relu comme un rayon" % dist


def test_can_be_revived_mechanical(nar_env):
    """CanBeRevived : un allie Mechanical (toggle sur ctx.traits) -> PAS de revive -- c'est de LA que vient
    le « non-Mechanical » de l'i2 (le filtre IdunBattle.Entities.Effects.Loki.Narthecium_ReviveEffect$$CreateTargetFilter ne le contient pas)."""
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.runner.abilities.behaviours.stats import is_mechanical
    env = nar_env
    st = _fresh(env)
    _place(env, st, env["ids"]["ally"], 1)
    sc = st.get_entity(env["ids"]["ally"]).get_component(StatsComponent)
    sc.ctx.traits = list(getattr(sc.ctx, "traits", None) or []) + ["Mechanical"]
    ent = entities_from_state(st, env["ids"]["ap"], env["ids"]["ally"])
    assert is_mechanical(ent.has_trait, ent.target), "toggle Mechanical non vu par has_trait"
    _kill(env, st, env["ids"]["ally"])
    assert not _uc(st, env["ids"]["ally"]).alive, "allie Mechanical revive (CanBeRevived non respecte)"


def test_enemy_death_not_revived(nar_env):
    """AreFriends(self,target) : la mort d'un ENNEMI adjacent ne declenche pas le revive."""
    env = nar_env
    st = _fresh(env)
    from engine.runner.components import OwnerComponent
    ap_team = st.get_entity(env["ids"]["ap"]).get_component(OwnerComponent).team
    foe = None
    for uid, e in st.entities.items():
        oc = e.get_component(OwnerComponent)
        if oc is not None and oc.team != ap_team:
            foe = uid
            break
    if foe is None:
        pytest.skip("pas d'ennemi dans l'etat")
    assert _place(env, st, foe, 1), "placement ennemi adjacent KO"
    _kill(env, st, foe)
    assert not _uc(st, foe).alive, "ennemi revive (AreFriends non respecte)"
