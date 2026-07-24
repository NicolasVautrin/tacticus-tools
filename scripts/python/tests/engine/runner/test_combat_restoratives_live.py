"""TRANCHE ABILITY COMBAT (case-220 P0-HEAL) — CombatRestoratives (1002, ultraApothecary, Ultramarines).

`CombatRestorativesAbility.ExecuteBehaviour @1811cc590` (+ `HealTargets @1811cca50`, callback
`b__0 @1811e3e90`) : heal self + allies adjacents (hex 1), SPLIT par trait Imperial(0x1a) :
  - allie IMPERIAL     : `hpToHeal_2[level]` (var0x22)   -- le PLUS gros
  - allie NON-Imperial : `hpToHeal[level]`   (var0x20)
JUMEAU IMPERIAL du Chaos 1037 RevitalizingMalignancy, mais DEUX DIFFERENCES STRUCTURELLES lues au
decompile (pas devinees par symetrie) :
  (1) PAS DE CUMUL : var0x22 et var0x20 sont lues SEPAREMENT et utilisees SEPAREMENT (contraste 1037 ou
      le cote Chaos = var0x22 + var0x20). ANGLE VALIDATOR : montants = deux vars distinctes, pas un scalaire.
  (2) PAS D'EXCLUSION DE TRAIT : le set entier = Healable(self + allies adj) puis split Imperial/non-Imperial
      via op_Subtraction ; les allies Chaos ET Xenos sont soignes (var0x20), contraste 1037 qui EXCLUT
      Imperial du set (0 heal). Le trait d'ALLIANCE (Imperial/Chaos/Xenos) est ABSENT de gameconfig.unit()
      .traits : DERIVE de la GrandAlliance (`GrandAlliance.GetTrait @1815647a0`), porte par
      `_grand_alliance_trait` (context.py). Garde `Healable` (HP<max ET non-mechanical) cote mutation.

MESURE LIVE (rank 17, ultraApothecary level 50 mult 180 -> imperial 7477, sans 5983) confirmee sur runner :
CAST LIVE REEL confronte au port offline BIT-EXACT (applyAction ability, allie blesse via KillMaimBurn
ennemi) -> ultraApothecary[Imperial, blesse 8286>7477] +7477 == offline +7477 ; eldarRanger[Xenos, adj]
+3014 == offline +3014 ; allies pleins/hors-adjacence/mechanical 0 == 0. Les 5 unites : live_delta ==
offline_delta.

METHODE (mirror test_revitalizing_malignancy_live, DETERMINISTE) : etat REEL (board+stats via load_state),
positions controlees (caster central, allies adjacents), blessures posees en Python, on rejoue le MESSAGE
d'ability et on confronte les deltas HP aux montants RE-derives (lus du port, pas hardcodes). + un test
LIVE best-effort qui caste 1002 dans le runner natif (applyAction) et confronte les deltas au port. ASCII only.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.components import PositionComponent, HealthComponent, StatsComponent
from engine.runner.abilities.ultramarines import CombatRestorativesAbility, _heal_amounts
from engine.runner.abilities.behaviours import healable_heal_type_0, is_mechanical
from engine.entities.pathfinding.board import Board

CASTER = "ultraApothecary"       # 1002 CombatRestoratives (Ultramarines, GrandAlliance Imperial)
ALLY_IMP = "adeptHospitaller"    # Imperial alliance, non-mech -> imperial amount (hpToHeal_2)
ALLY_XENOS = "eldarRanger"       # Xenos alliance, non-mech -> sans amount (hpToHeal)
ALLY_CHAOS = "deathBlightbringer"  # Chaos alliance, non-mech -> sans amount (NON exclu, contraste 1037)
ALLY_MECH = "necroWarden"        # Xenos + LivingMetal (mechanical) -> EXCLU (Healable non-mechanical)
ROSTER = f"{CASTER},{ALLY_IMP},{ALLY_XENOS},{ALLY_CHAOS},{ALLY_MECH}"
ENEMIES = "worldKharn,ultraTitus"
BUILD = ["--p-units", ROSTER, "--a-units", ENEMIES, "--rank", "17", "--hp-player", "300000"]
ABILITY = 1002
KILL_MAIM_BURN = 1132            # active AoE de worldKharn (blessure LIVE deterministe-ish)


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
def combatrest_state(live_session, rpc, build_runner):
    """Build + load_state + board. Caster central (>=4 voisins), 4 allies sur ses voisins hex, blessures
    profondes (HP-20000) sur les 5 pour que le montant PLEIN soit observable. Skip si unites/board absents."""
    rid = build_runner("777", extra=BUILD)["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        pytest.skip("capture live KO")
    state = load_state(dv, ob, snap, board=board)
    ids = {k: _by_vis(state, v) for k, v in
           (("apo", CASTER), ("imp", ALLY_IMP), ("xen", ALLY_XENOS),
            ("cha", ALLY_CHAOS), ("mech", ALLY_MECH))}
    if any(v is None for v in ids.values()):
        pytest.skip("roster incomplet offline: %s" % ids)
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
    _pc(state, ids["apo"]).col, _pc(state, ids["apo"]).row = center
    neigh = [board.coord(n) for n in board.neighbours(board.id_at(*center)) if board.walkable(n)]
    for uid, c in zip((ids["imp"], ids["xen"], ids["cha"], ids["mech"]), neigh):
        _pc(state, uid).col, _pc(state, uid).row = c
    for uid in ids.values():
        h = _hc(state, uid)
        h.hp = int(h.hp_max) - 20000
    return {"state": state, "ids": ids}


def test_combatrest_split_amounts_and_exclusions(combatrest_state):
    """Confronte les deltas HP du cast aux montants RE-derives : caster + ally Imperial = imperial
    (hpToHeal_2) ; ally Xenos ET ally Chaos = sans (hpToHeal, Chaos NON exclu) ; ally mechanical = 0."""
    state, ids = combatrest_state["state"], combatrest_state["ids"]
    imperial, sans = _heal_amounts(state, ids["apo"])
    # ANGLE VALIDATOR : imperial et sans = DEUX vars distinctes (hpToHeal_2 vs hpToHeal), PAS de cumul.
    from engine.entities.effects.magnitude import ability_var
    sc = state.get_entity(ids["apo"]).get_component(StatsComponent)
    lvl, mult = sc.ctx.active_ability_level, sc.ctx.ability_variables_multiplier
    exp_imp = int(ability_var("CombatRestoratives", "hpToHeal_2", lvl, multiplier_pct=mult) or 0)
    exp_sans = int(ability_var("CombatRestoratives", "hpToHeal", lvl, multiplier_pct=mult) or 0)
    assert imperial == exp_imp, "imperial %d != hpToHeal_2 %d" % (imperial, exp_imp)
    assert sans == exp_sans, "sans %d != hpToHeal %d" % (sans, exp_sans)
    assert imperial != sans, "imperial==sans : mapping var0x22/var0x20 suspect (ou cumul mal porte)"
    assert imperial > sans > 0, "montants degeneres imperial=%d sans=%d" % (imperial, sans)

    pre = {k: int(_hc(state, uid).hp) for k, uid in ids.items()}
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=ids["apo"], target_id=ids["apo"], ability_type=ABILITY))
    last = runner.ability_handler.last or {}
    assert last.get("ported"), "CombatRestoratives non routee (ability-exec)"
    post = {k: int(_hc(state, uid).hp) for k, uid in ids.items()}
    d = {k: post[k] - pre[k] for k in ids}
    print("\n[COMBATREST] imperial=%d sans=%d deltas=%s" % (imperial, sans, d))

    assert d["apo"] == imperial, "caster (Imperial) heal %d != imperial %d" % (d["apo"], imperial)
    assert d["imp"] == imperial, "ally Imperial heal %d != imperial %d" % (d["imp"], imperial)
    assert d["xen"] == sans, "ally Xenos heal %d != sans %d" % (d["xen"], sans)
    assert d["cha"] == sans, "ally Chaos heal %d != sans %d (Chaos NE doit PAS etre exclu)" % (d["cha"], sans)
    assert d["mech"] == 0, "ally mechanical NON exclu (heal %d)" % d["mech"]


def test_combatrest_healable_guard_fullhp_and_mechanical(combatrest_state):
    """Garde Healable (pure) : un allie FULL-HP -> non soignable ; un allie mechanical -> non soignable
    (IsMechanical = Mechanical|LivingMetal|Vehicle)."""
    from engine.dsl.effects import ExecutionContext
    from engine.runner.abilities.behaviours import entities_from_state
    state, ids = combatrest_state["state"], combatrest_state["ids"]
    ectx = ExecutionContext(state=state, rng=state.rng)
    ent = entities_from_state(state, ids["apo"], ids["apo"])
    u_by_id = {u.get("id"): u for u in ent.units}

    umech = u_by_id[ids["mech"]]
    assert is_mechanical(ent.has_trait, umech), "necroWarden (LivingMetal) devrait etre IsMechanical"
    assert not healable_heal_type_0(ent, ectx, umech), "mechanical blesse devrait etre non-Healable"

    h = _hc(state, ids["xen"])
    h.hp = int(h.hp_max)
    uxen = u_by_id[ids["xen"]]
    assert not healable_heal_type_0(ent, ectx, uxen), "full-HP devrait etre non-Healable (HP<max faux)"
    h.hp = int(h.hp_max) - 1
    assert healable_heal_type_0(ent, ectx, uxen), "Xenos blesse non-mech devrait etre Healable"


# ------------------------------------------------------------------ CAST LIVE REEL (confront bit-exact)

def _live_units(rpc, rid):
    r = rpc("observeBattle", {"runnerId": rid}, 40)
    return {u["squadId"]: u for u in (r.get("units") or [])} if _ok(r) else {}


def _current_player(rpc, rid):
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
    return dv.get("currentPlayer") if isinstance(dv, dict) else None


def _flip_to(rpc, rid, want, maxtries=6):
    for _ in range(maxtries):
        if _current_player(rpc, rid) == want:
            return True
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    return _current_player(rpc, rid) == want


def test_combatrest_live_cast_confront(live_session, rpc, build_runner):
    """CAST LIVE REEL : on blesse le caster (Imperial) via l'AoE ennemie KillMaimBurn (tour ennemi), puis on
    CASTE 1002 dans le runner natif (applyAction) et on confronte les deltas HP LIVE au port OFFLINE tourne
    sur la MEME capture pre-cast. Best-effort : skip si la blessure/positionnement echoue (jamais un faux
    rouge). Assertion cle = live_delta == offline_delta pour CHAQUE unite (+ caster reellement soigne live)."""
    rid = build_runner("777", extra=BUILD)["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    U0 = _live_units(rpc, rid)
    apo = next((sq for sq, u in U0.items() if u.get("visualId") == CASTER), None)
    wk = next((sq for sq, u in U0.items() if u.get("visualId") == "worldKharn"), None)
    if apo is None or wk is None:
        pytest.skip("caster/worldKharn absents live")
    mine = _current_player(rpc, rid)
    if mine is None:
        pytest.skip("currentPlayer indispo")

    # tour ennemi : approcher worldKharn du caster puis KillMaimBurn dessus (AoE = blesse caster + voisins)
    if not _flip_to(rpc, rid, want=(4 if mine == 3 else 3)):
        pytest.skip("impossible de passer au tour ennemi")
    aq = U0[apo]
    at = board.id_at(aq["col"], aq["row"])
    occ = {board.id_at(u["col"], u["row"]) for u in _live_units(rpc, rid).values()}
    free_adj = next((n for n in board.neighbours(at)
                     if board.walkable(n) and n not in occ and n in board.by_id), None)
    if free_adj is not None:
        c, r = board.coord(free_adj)
        rpc("applyAction", {"runnerId": rid, "action":
             {"kind": "move", "unitId": wk, "to": {"col": c, "row": r}}}, 40)
    rpc("applyAction", {"runnerId": rid, "action":
         {"kind": "ability", "casterId": wk, "targetId": apo, "abilityType": KILL_MAIM_BURN}}, 60)
    Uw = _live_units(rpc, rid)
    if not Uw or apo not in Uw:
        pytest.skip("observe KO post-blessure")
    if Uw[apo].get("isDead") or Uw[apo]["hp"] >= U0[apo]["hp"]:
        pytest.skip("caster non blesse (KillMaimBurn hors portee) ou tue -> pas de cast confrontable")

    # retour a mon tour
    if not _flip_to(rpc, rid, want=mine):
        pytest.skip("impossible de revenir a mon tour")

    # CAPTURE pre-cast + port OFFLINE sur cette meme capture
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        pytest.skip("capture pre-cast KO")
    pre = {u["squadId"]: u["hp"] for u in ob["units"]}
    state = load_state(dv, ob, snap, board=board)
    cid = _by_vis(state, CASTER)
    if cid is None:
        pytest.skip("caster absent offline")
    # map squadId (live) -> entity id (offline) par visualId
    live_vis = {sq: u.get("visualId") for sq, u in _live_units(rpc, rid).items()}
    eid_by_vis = {getattr(state.get_entity(e).get_component(StatsComponent).ctx, "visual_id", None): e
                  for e in state.entities
                  if state.get_entity(e).get_component(StatsComponent) is not None}
    off_pre = {e: int(_hc(state, e).hp) for e in state.entities}
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=cid, target_id=cid, ability_type=ABILITY))
    last = runner.ability_handler.last or {}
    assert last.get("ported"), "CombatRestoratives non routee (ability-exec offline)"
    off_delta = {}
    for sq, vis in live_vis.items():
        e = eid_by_vis.get(vis)
        if e is not None and sq in pre:
            off_delta[sq] = int(_hc(state, e).hp) - off_pre[e]

    # CAST LIVE + deltas observes
    rpc("applyAction", {"runnerId": rid, "action":
         {"kind": "ability", "casterId": apo, "targetId": apo, "abilityType": ABILITY}}, 60)
    post = {u["squadId"]: u["hp"] for u in (rpc("observeBattle", {"runnerId": rid}, 40).get("units") or [])}
    live_delta = {sq: post[sq] - pre[sq] for sq in pre if sq in post}

    print("\n[COMBATREST/live] apo=%d pre_hp=%d" % (apo, pre.get(apo, -1)))
    common = [sq for sq in off_delta if sq in live_delta]
    assert common, "aucune unite commune live/offline"
    for sq in common:
        print("  sq%d %s live=%d off=%d" % (sq, live_vis.get(sq), live_delta[sq], off_delta[sq]))
        assert live_delta[sq] == off_delta[sq], \
            "sq%d (%s) live_delta %d != offline_delta %d" % (sq, live_vis.get(sq), live_delta[sq], off_delta[sq])
    assert live_delta.get(apo, 0) > 0, "le caster (Imperial, blesse) n'a pas ete soigne LIVE (delta=%d)" % live_delta.get(apo, 0)
