"""#133 -- `DestroyTheWitch` (passif `templHelbrecht`, TriggeredAbilityType 0x443 = 1091).

RE + residus : `engine/entities/effects/loki/destroy_the_witch.py`.

Deux volets, quatre scenarios CRAFTES (positions PILOTEES) :

 A. PRESENCE (volet MOVE + gate partage) -- les DEUX owner-effects (1088 `_ExtraMove`,
    1089 `_ExtraDamage`) ne sont poses QUE s'il existe un Psyker **ENNEMI** vivant. Confronte sur
    TROIS configurations (ennemi Psyker / aucun Psyker / Psyker ALLIE) : le port doit rendre le
    MEME verdict que la capture live, y compris sur le discriminant « allie » qui separe
    `Enemies(Owner, UnitsWithTrait(AllUnits, Psyker))` d'un simple `UnitsWithTrait(Psyker)`.

 B. DEGAT (volet aura) -- REPLAY-DIFF RNG-seede sur quatre pattes :
      self      : HELBRECHT frappe un Psyker en melee            -> +extraDmg ENGAGE
      none      : HELBRECHT frappe un NON-Psyker                 -> bonus NUL (gate HasTrait cible)
      aura      : un ALLIE HEX-ADJACENT frappe le Psyker         -> +extraDmg ENGAGE
      aura-far  : LE MEME allie, MEME cible, Helbrecht LOIN      -> bonus NUL (gate geometrique
                  `SurroundingFriends(Owner, 1)`)
    `aura` et `aura-far` sont le couple discriminant : seule la distance Helbrecht<->allie change.

L'ALLIE est choisi SANS modificateur de degat propre (`ultraApothecary` : traits {Healer, Hero},
passif `Narthecium` = trigger de revive). `templSwordBrother` (voisin naturel) et `astraBullgryn`
ont ete ecartes -- cf. l'en-tete de `probe_133_dtw_damage.py` (pieges de HARNAIS documentes).

Lit l'etat LIVE (rien de hardcode : la magnitude attendue est relue de gameconfig). ASCII only.
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, PositionComponent, OwnerComponent
from engine.runner.damage_model import target_trait_names
from engine.entities.pathfinding.board import Board
from engine.entities.effects.magnitude import ability_var
from engine.runner.operations.refresh_effects import _enemy_psykers_alive
from engine.entities.effects.factory import EFFECT_CLASSES

HELBRECHT = "templHelbrecht"
FRIEND = "ultraApothecary"       # allie MELEE sans modificateur de degat propre (cf. en-tete)
PSYKER = "astraPrimarisPsy"      # trait Psyker
NONPSY = "orksNob"               # sans trait Psyker
EXTRA_MOVE = "DestroyTheWitch_ExtraMove"      # EffectType 1088
EXTRA_DMG = "DestroyTheWitch_ExtraDamage"     # EffectType 1089


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _bfs(board, src):
    dist = {src: 0}; q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1; q.append(n)
    return dist


def _alive(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _eff_names(u):
    return {e.get("name") for e in ((u or {}).get("effects") or [])}


# =================================================================================================
# A. PRESENCE / gate `Enemies(Owner, UnitsWithTrait(AllUnits, Psyker)) >= 1`
# =================================================================================================
def _presence_case(rpc, build_runner, p_units, a_units):
    b = build_runner("777", extra=["--roster", "2", "--p-units", p_units, "--a-units", a_units])
    dv = rpc("decisionView", {"runnerId": b["rid"], "maxRank": 1, "allAbilities": True}, 90)
    if not _ok(dv):
        return None
    ob = rpc("observeBattle", {"runnerId": b["rid"]}, 40)
    snap = rpc("combatSnapshot", {"runnerId": b["rid"]}, 40)
    state = load_state(dv, ob, snap)
    hel = _alive(dv, HELBRECHT)
    if hel is None:
        return None
    return {"live": _eff_names(hel), "n_enemy_psykers": _enemy_psykers_alive(state, hel["id"])}


@pytest.mark.parametrize("tag,p_units,a_units,expect_effects,expect_n", [
    ("psyker ENNEMI", f"{HELBRECHT},{FRIEND}", f"{PSYKER},{NONPSY}", True, 1),
    ("AUCUN psyker", f"{HELBRECHT},{FRIEND}", f"{NONPSY},orksRuntherd", False, 0),
    # DISCRIMINANT : un Psyker ALLIE ne compte PAS (`Enemies(Owner, ...)`), la ou un simple
    # `UnitsWithTrait(AllUnits, Psyker)` l'aurait compte.
    ("psyker ALLIE", f"{HELBRECHT},{PSYKER}", f"{NONPSY},orksRuntherd", False, 0),
])
def test_destroy_the_witch_presence_gate(live_session, rpc, build_runner,
                                         tag, p_units, a_units, expect_effects, expect_n):
    """Les DEUX owner-effets de `DestroyTheWitchAbility$$CreateBehaviour` sont poses ssi il existe
    >= 1 Psyker ENNEMI vivant -- et le predicat porte du port (`_enemy_psykers_alive`, mirror du
    corps natif FONDU `CreateActiveCondition`) rend le MEME verdict que la capture live."""
    c = _presence_case(rpc, build_runner, p_units, a_units)
    if c is None:
        pytest.skip("build/decisionView KO")
    assert c["n_enemy_psykers"] == expect_n, (
        f"[{tag}] `_enemy_psykers_alive` = {c['n_enemy_psykers']}, attendu {expect_n}")
    for name in (EXTRA_MOVE, EXTRA_DMG):
        assert (name in c["live"]) is expect_effects, (
            f"[{tag}] {name} {'absent' if expect_effects else 'present'} live "
            f"(effets={sorted(c['live'])}) -- le gate mesure n'est pas celui du port")
    # Les deux effets sont PORTES (sinon la presence live ci-dessus serait inerte offline).
    assert EXTRA_MOVE in EFFECT_CLASSES and EXTRA_DMG in EFFECT_CLASSES


# =================================================================================================
# B. DEGAT / aura `Unique(SurroundingFriends(Owner,1) + Owner)` x `HasTrait(Target, Psyker)`
# =================================================================================================
def _walk_to(rpc, rid, board, mover_vis, anchor_vis, want, turns=30):
    """Rapproche `mover_vis` a `want` hexes de `anchor_vis` (je pilote MON camp)."""
    def tile(u):
        p = (u or {}).get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if u else None

    for _ in range(turns):
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        mv, anch = _alive(dv, mover_vis), _alive(dv, anchor_vis)
        if mv is None or anch is None:
            return dv
        dist = _bfs(board, tile(anch))
        if dist.get(tile(mv)) == want:
            return dv
        if dv.get("currentPlayer") != mv.get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        row = next((x for x in (mt.get("units") or []) if x.get("unitId") == mv["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((row or {}).get("tiles") or [])}
        exact = [t for t in reach if dist.get(t) == want]
        pool = exact or [t for t in reach if t in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        best = exact[0] if exact else min(pool, key=lambda t: dist[t])
        col, r = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": mv["id"], "to": {"col": col, "row": r}}}, 40)
        if not exact:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)


def _damage_case(rpc, build_runner, leg):
    att_vis = FRIEND if leg.startswith("aura") else HELBRECHT
    tgt_vis = NONPSY if leg == "none" else PSYKER
    b = build_runner("777", extra=[
        "--roster", "2", "--p-units", f"{HELBRECHT},{FRIEND}",
        "--a-units", f"{PSYKER},{NONPSY}", "--hp-player", "999999", "--hp-target", "999999"])
    rid = b["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        return {"ok": False, "reason": "boardGraph indispo"}
    board = Board(bg["tiles"], adjacency="native_sym")
    _walk_to(rpc, rid, board, att_vis, tgt_vis, 1)
    if leg == "aura":                      # Helbrecht DOIT etre hex-adjacent a l'attaquant
        _walk_to(rpc, rid, board, HELBRECHT, att_vis, 1)
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    att, tgt, hel = _alive(dv, att_vis), _alive(dv, tgt_vis), _alive(dv, HELBRECHT)
    if att is None or tgt is None or hel is None:
        return {"ok": False, "reason": "unite manquante"}
    for _ in range(4):
        if dv.get("currentPlayer") == att.get("owner"):
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        att, tgt, hel = _alive(dv, att_vis), _alive(dv, tgt_vis), _alive(dv, HELBRECHT)
        if att is None or tgt is None or hel is None:
            return {"ok": False, "reason": "unite manquante post-endturn"}
    norm = next((a for a in (att.get("abilities") or []) if a.get("kind") == "normal"), None)
    if norm is None:
        return {"ok": False, "reason": "pas d'attaque normale"}
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv, ob, snap, board=board)
    he = state.get_entity(hel["id"])
    hhc = he.get_component(HealthComponent) if he is not None else None
    heff = (state.effects.active_effects(hel["id"], {"hp": hhc.hp if hhc else None})
            if state.effects is not None else [])
    dtw = next((e for e in heff if getattr(e, "name", None) == EXTRA_DMG), None)
    if dtw is None:
        return {"ok": False, "reason": f"{EXTRA_DMG} non seede sur Helbrecht"}
    tgt_traits = target_trait_names(state, tgt["id"])
    import hexgeo
    hpc, apc = he.get_component(PositionComponent), \
        state.get_entity(att["id"]).get_component(PositionComponent)
    hoc, aoc = he.get_component(OwnerComponent), \
        state.get_entity(att["id"]).get_component(OwnerComponent)
    d_ha = hexgeo.distance((hpc.col, hpc.row), (apc.col, apc.row))
    if leg.startswith("aura"):
        bonus = dtw.create_aura_attack_damage_bonus_for_ally({
            "att_id": att["id"], "att_pos": (apc.col, apc.row), "att_team": aoc.team,
            "owner_id": hel["id"], "owner_pos": (hpc.col, hpc.row), "owner_team": hoc.team,
            "is_melee": True, "tgt_traits": tgt_traits})
    else:
        bonus = dtw.create_effect_damage_bonus_for_attack(is_ranged=False,
                                                          target_traits=tgt_traits)
    expected = ability_var("DestroyTheWitch", "extraDmg", dtw.ability_level,
                           multiplier_pct=dtw.ability_variables_multiplier)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        return {"ok": False, "reason": "dumpRng KO"}
    state.rng = _seed_rng(s0)
    runner = Runner(state).install_default_handlers(20)
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att["id"], "targetId": tgt["id"],
        "abilityType": norm["id"]}}, 60)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        return {"ok": False, "reason": f"attaque live KO: {str(res)[:150]}"}
    live_ph, evade = [], False
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tgt["id"] and "Amount" in td \
                and td.get("Active_Ability_Type") == norm["id"]:
            live_ph.append(td.get("Amount"))
            evade = evade or bool(td.get("Attack_DidEvade"))
    live_after = next((u.get("hp") for u in (res.get("units") or [])
                       if u.get("squadId") == tgt["id"]), None)
    runner.apply(AttackUnitMessage(att["id"], tgt["id"]))
    rr = runner.damage_handler.last
    off_after = state.get_entity(tgt["id"]).get_component(HealthComponent).hp
    return {"ok": True, "reason": None, "bonus": bonus, "expected": expected,
            "tgt_traits": tgt_traits, "dist_helb_att": d_ha, "evade": evade,
            "live_ph": live_ph, "off_ph": (rr or {}).get("per_hit"),
            "live_after": live_after, "off_after": off_after}


@pytest.mark.parametrize("leg,engaged", [
    ("self", True),        # patte SELF du selecteur (`op_Addition Owner@0x148`)
    ("none", False),       # gate `HasTrait(Target@0x178, Psyker)`
    ("aura", True),        # patte AURA (`SurroundingFriends(Owner, 1)`)
    ("aura-far", False),   # MEME allie/cible, Helbrecht hors du rayon 1
])
def test_destroy_the_witch_extra_damage(live_session, rpc, build_runner, leg, engaged):
    """Le bonus +extraDmg est ENGAGE exactement quand les gates natifs le disent, et l'attaque
    rejouee RNG-seede rend le MEME per-hit et les MEMES PV que le live (le bonus est donc applique
    a l'identique du natif, pas seulement « present »)."""
    c = _damage_case(rpc, build_runner, leg)
    if not c["ok"]:
        pytest.skip(c["reason"])
    if c["evade"]:
        pytest.skip("coup avec evade live (hors slice)")
    if leg == "aura":
        assert c["dist_helb_att"] == 1, f"[{leg}] Helbrecht a {c['dist_helb_att']} hexes de l'allie"
    if leg == "aura-far":
        assert c["dist_helb_att"] > 1, f"[{leg}] Helbrecht encore dans le rayon 1 (scenario nul)"
    if leg == "none":
        assert "Psyker" not in c["tgt_traits"], f"[{leg}] la cible est Psyker : scenario nul"
    else:
        assert "Psyker" in c["tgt_traits"], f"[{leg}] la cible n'est pas Psyker : scenario nul"
    if engaged:
        assert c["expected"], "extraDmg introuvable en gameconfig"
        assert getattr(c["bonus"], "kind", None) == "Addition" \
            and getattr(c["bonus"], "value", None) == c["expected"], (
            f"[{leg}] bonus attendu Addition {c['expected']}, obtenu {c['bonus']}")
    else:
        assert c["bonus"] is None, f"[{leg}] bonus NON nul ({c['bonus']}) : gate casse"
    assert c["off_ph"] == c["live_ph"], (
        f"[{leg}] per-hit offline {c['off_ph']} != live {c['live_ph']}")
    assert c["off_after"] == c["live_after"], (
        f"[{leg}] PV cible offline {c['off_after']} != live {c['live_after']}")
