"""TRANCHE ABILITY COMBAT (case-220 P0-HEAL) — RevitalizingMalignancy (1037, deathRotbone, Death Guard).

`RevitalizingMalignancyAbility.ExecuteBehaviour @181200eb0` (+ `GetAllHealTargets @181201150`,
`GetChaosHealTargets @181201230`, `GetRegularHealTargets @181201280`, callback b__0 @181218d00) : heal
self + allies adjacents (hex 1) NON-Imperial, SPLIT par trait Chaos(0x7ea) :
  - non-Chaos : `hpToHeal[level]` (var0x20)
  - Chaos     : `hpToHeal[level] + hpToHeal_2[level]` (var0x22 + var0x20, CUMUL de DEUX vars lues
                separement -- ANGLE VALIDATOR : PAS un scalaire fitte).
Garde `Healable` (HP<max ET non-mechanical) cote mutation. Jumeau heal de 1002 CombatRestoratives.

Le trait d'ALLIANCE (Imperial/Chaos/Xenos) est ABSENT de gameconfig.unit().traits (0 unite le porte) :
DERIVE de la GrandAlliance (`GrandAlliance.GetTrait @1815647a0` : Imperial->26, Xenos->1006, Chaos->2026),
porte cote runner par `_grand_alliance_trait` (context.py). IsMechanical = Mechanical|LivingMetal|Vehicle
(`UnitExtensions.IsMechanical @180ed8a30`).

MESURE LIVE (rank 17, deathRotbone level 50 mult 180 -> regular 3490, chaos 6980) confirmee sur runner :
deathBlightbringer[Chaos] +6980, eldarRanger[Xenos] +3490, adeptHospitaller[Imperial] +0,
necroWarden[mech=LivingMetal, blesse] +0.

METHODE (mirror test_the_quickening_live, DETERMINISTE) : etat REEL (board+stats via load_state),
positions controlees (caster central, allies adjacents), blessures posees en Python, on rejoue le
MESSAGE d'ability et on confronte les deltas HP aux montants RE-derives (lus du port, pas hardcodes).
ASCII only.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.components import PositionComponent, HealthComponent, StatsComponent
from engine.runner.abilities.deathguard import (RevitalizingMalignancyAbility, _heal_amounts,
                                                _healable_heal_type_0, _is_mechanical)
from engine.entities.pathfinding.board import Board

CASTER = "deathRotbone"          # 1037 RevitalizingMalignancy (Death Guard, GrandAlliance Chaos)
ALLY_CHAOS = "deathBlightbringer"  # Chaos alliance, non-mech -> chaos amount
ALLY_XENOS = "eldarRanger"         # Xenos alliance, non-mech -> regular amount
ALLY_IMP = "adeptHospitaller"      # Imperial alliance -> EXCLU (WithoutTrait Imperial)
ALLY_MECH = "necroWarden"          # Xenos + LivingMetal (mechanical) -> EXCLU (Healable non-mechanical)
ROSTER = f"{CASTER},{ALLY_CHAOS},{ALLY_XENOS},{ALLY_IMP},{ALLY_MECH}"
BUILD = ["--p-units", ROSTER, "--a-units", "worldKharn,ultraTitus", "--rank", "17",
         "--hp-player", "300000"]   # hp 300k -> blessure profonde possible sans passer < 0
ABILITY = 1037


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _board(rpc, rid):
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return None
    return Board(bg["tiles"], adjacency="native_sym")


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


@pytest.fixture(scope="module")
def revmalig_state(live_session, rpc, build_runner):
    """Build + load_state + board. Positionne le caster au centre, 4 allies sur ses voisins hex,
    blesse le caster + les 4 allies (HP-20000, reste > 0 avec hp 300k). Skip si unites/board absents."""
    rid = build_runner("777", extra=BUILD)["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        pytest.skip("capture live KO")
    state = load_state(dv, ob, snap)
    state.board = board
    ids = {k: _by_vis(state, v) for k, v in
           (("dr", CASTER), ("chaos", ALLY_CHAOS), ("xenos", ALLY_XENOS),
            ("imp", ALLY_IMP), ("mech", ALLY_MECH))}
    if any(v is None for v in ids.values()):
        pytest.skip("roster incomplet offline: %s" % ids)
    # caster central (>=4 voisins), allies sur 4 voisins hex
    center = None
    for uid, e in state.entities.items():
        pc = e.get_component(PositionComponent)
        if pc is None:
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None and len([n for n in board.neighbours(t) if board.walkable(n)]) >= 4:
            center = board.coord(t)
            break
    if center is None:
        pytest.skip("aucune tuile centrale >=4 voisins")
    _pc(state, ids["dr"]).col, _pc(state, ids["dr"]).row = center
    neigh = [board.coord(n) for n in board.neighbours(board.id_at(*center)) if board.walkable(n)]
    for uid, c in zip((ids["chaos"], ids["xenos"], ids["imp"], ids["mech"]), neigh):
        _pc(state, uid).col, _pc(state, uid).row = c
    # blessures profondes (heal ne cape pas) sur les 5
    for uid in ids.values():
        h = _hc(state, uid)
        h.hp = int(h.hp_max) - 20000
    return {"state": state, "ids": ids}


def test_revmalig_split_amounts_and_exclusions(revmalig_state):
    """Confronte les deltas HP du cast aux montants RE-derives : caster+ally Chaos = chaos (CUMUL),
    ally Xenos = regular, ally Imperial = 0 (exclu), ally mechanical = 0 (Healable non-mech)."""
    state, ids = revmalig_state["state"], revmalig_state["ids"]
    regular, chaos = _heal_amounts(state, ids["dr"])
    # ANGLE VALIDATOR : chaos = regular + hpToHeal_2 (SOMME de 2 vars), pas un scalaire isole.
    from engine.entities.effects.magnitude import ability_var
    sc = state.get_entity(ids["dr"]).get_component(StatsComponent)
    lvl, mult = sc.ctx.active_ability_level, sc.ctx.ability_variables_multiplier
    bonus = int(ability_var("RevitalizingMalignancy", "hpToHeal_2", lvl, multiplier_pct=mult) or 0)
    assert chaos == regular + bonus, "chaos %d != regular %d + hpToHeal_2 %d (CUMUL)" % (chaos, regular, bonus)
    assert chaos > regular > 0, "montants degeneres regular=%d chaos=%d" % (regular, chaos)

    pre = {k: int(_hc(state, uid).hp) for k, uid in ids.items()}
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=ids["dr"], target_id=ids["dr"], ability_type=ABILITY))
    last = runner.ability_handler.last or {}
    assert last.get("ported"), "RevitalizingMalignancy non routee (ability-exec)"
    post = {k: int(_hc(state, uid).hp) for k, uid in ids.items()}
    d = {k: post[k] - pre[k] for k in ids}
    print("\n[REVMALIG] regular=%d chaos=%d deltas=%s" % (regular, chaos, d))

    assert d["dr"] == chaos, "caster (Chaos) heal %d != chaos %d" % (d["dr"], chaos)
    assert d["chaos"] == chaos, "ally Chaos heal %d != chaos %d" % (d["chaos"], chaos)
    assert d["xenos"] == regular, "ally Xenos heal %d != regular %d" % (d["xenos"], regular)
    assert d["imp"] == 0, "ally Imperial NON exclu (heal %d)" % d["imp"]
    assert d["mech"] == 0, "ally mechanical NON exclu (heal %d)" % d["mech"]


def test_revmalig_healable_guard_fullhp_and_mechanical(revmalig_state):
    """Garde Healable (pure) : un allie FULL-HP -> non soignable ; un allie mechanical -> non soignable
    (IsMechanical = Mechanical|LivingMetal|Vehicle)."""
    from engine.dsl.effects import ExecutionContext
    from engine.runner.abilities.behaviours import entities_from_state
    state, ids = revmalig_state["state"], revmalig_state["ids"]
    ectx = ExecutionContext(state=state, rng=state.rng)
    ent = entities_from_state(state, ids["dr"], ids["dr"])
    u_by_id = {u.get("id"): u for u in ent.units}

    # mechanical (necroWarden = LivingMetal) : IsMechanical True -> guard False (blesse)
    umech = u_by_id[ids["mech"]]
    assert _is_mechanical(ent.has_trait, umech), "necroWarden (LivingMetal) devrait etre IsMechanical"
    assert not _healable_heal_type_0(ent, ectx, umech), "mechanical blesse devrait etre non-Healable"

    # full-HP : un Xenos non-mech remis a max -> guard False (HP<max faux)
    h = _hc(state, ids["xenos"])
    h.hp = int(h.hp_max)
    uxen = u_by_id[ids["xenos"]]
    assert not _healable_heal_type_0(ent, ectx, uxen), "full-HP devrait etre non-Healable (HP<max faux)"
    # une fois blesse d'1 PV -> Healable True (Xenos non-mech, non-Imperial)
    h.hp = int(h.hp_max) - 1
    assert _healable_heal_type_0(ent, ectx, uxen), "Xenos blesse non-mech devrait etre Healable"
