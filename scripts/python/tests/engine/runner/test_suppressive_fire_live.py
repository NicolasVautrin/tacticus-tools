"""#74 : trait `SuppressiveFire` (1010) -> triggered `SuppressiveFireAbility` (1044) qui pose Pinned/
« Suppressed » (0x429=1065) sur la cible d'une attaque RANGED du porteur — face RUNNER confrontee au LIVE.

Port : `engine/runner/operations/triggers/loki/suppressive_fire.py`
(arbre DSL `AddEffect(Pinned=1065, Target())`, trigger `On(NormalAttack) & IsRangedAttack POSITION-based
& OwnerIsActor & AreEnemies`, RE IdunBattleLogic.Entities.Abilities.Active.Loki.SuppressiveFireAbility$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Active.Loki.SuppressiveFireAbility$$CreateBehaviour). L'effet Pinned lui-meme = `PinnedEffect`
(status.py, deja porte+valide live).

DRIVE POSITIONS (doctrine) : `_approach` avance jusqu'a mon tour (endturn adverse -> cible stationnaire)
puis rapproche le porteur a la distance hex voulue de la cible. Quatre discriminants :
  1. RANGED (d==2, la cible est NON-adjacente = IsRangedAttack) -> Pinned pose LIVE == offline.
  2. MELEE  (d==1, la cible est ADJACENTE = position melee) -> AUCUN Pinned LIVE == offline (gate ranged).
  3. NON-CARRIER (offline, structurel) : un attaquant SANS le trait -> AUCUN Pinned (gate trait/registre).
  4. CIBLE `TerminatorArmour` (#208) : l'effet EST pose, et il est INACTIF -- generalisation du cas
     `PinnedEffect$$CreateActiveCondition` a un AUTRE POSEUR que `SentinelDirectives` (ici un trigger
     de trait). Les deux canaux se correspondent : `decisionView` par defaut == `active_effects`
     (absent), `decisionView includeInactive` == `by_unit` (present).

Cible = astraYarrick (Resilient, durable, non-Terminator, non-carrier) `--hp-target 200000` : survit ->
lecture propre de decisionView.effects (le Pinned apparait comme delta pre/post attaque). ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from collections import deque
from pathlib import Path

import pytest

import hexgeo

CARRIER = "tauDarkstrider"          # Tau sniper : arme Pulse (Range 2), trait SuppressiveFire
TARGET = "astraYarrick"            # Resilient (durable), non-Terminator (Pinnable), non-carrier
TERMINATOR_TARGET = "blackAbaddon"  # TerminatorArmour -> Pinned POSE mais INERTE (#208, cas 4)
PINNED = 1065                      # EffectType.Pinned (0x429) — UI « Suppressed »
RANGE = 2                          # portee de l'arme Pulse -> ranged a d==2, melee a d==1
PYDIR = Path(__file__).resolve().parents[3]            # scripts/python
ROOT = PYDIR.parents[1]                                # racine repo


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _find(units, vis):
    return next((u for u in (units or []) if u.get("visualId") == vis and u.get("alive")), None)


def _cr(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _pinned_of(units, uid):
    u = next((x for x in (units or []) if x.get("id") == uid), {})
    return next((ef for ef in (u.get("effects") or []) if ef.get("effectType") == PINNED), None)


def _build(seed, p_units, a_units):
    sf = ROOT / "logs" / "runners" / f"suppfire-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
         "--board", "MC1_67", "--roster", "1", "--p-units", p_units, "--a-units", a_units,
         "--hp-target", "200000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, None, (proc.stderr or proc.stdout or "")[-300:]
    return int(json.loads(sf.read_text())["runnerId"]), sf, None


def _normal_id(caster):
    n = next((ab for ab in (caster.get("abilities") or []) if ab.get("kind") == "normal"), None)
    return n["id"] if n else None


def _approach(rpc, rid, board, lo, hi, max_iter=30, target_vis=None):
    """Amene le porteur a distance hex [lo..hi] de la cible (endturn adverse = cible immobile).
    Renvoie (caster_id, target_id, normal_ability_id, my_player) ou None.
    `target_vis` = visualId de la cible (defaut `TARGET`) — parametre pour le discriminant (4)."""
    target_vis = target_vis or TARGET
    def tile_of(u):
        cr = _cr(u)
        return board.id_at(cr[0], cr[1]) if cr else None

    def bfs(src):
        dist = {src: 0}
        q = deque([src])
        while q:
            x = q.popleft()
            for n in board.neighbours(x):
                if n not in dist and (n == src or board.walkable(n)):
                    dist[n] = dist[x] + 1
                    q.append(n)
        return dist

    def legal(cid, nid):
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": nid}, 90)
        ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                   if a.get("abilityId") == nid), {})
        return [x.get("targetId") for x in (ab.get("fromHere") or ab.get("targets") or [])]

    my = None
    for _ in range(max_iter):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        units = dv.get("units") or []
        caster = _find(units, CARRIER)
        tgt = _find(units, target_vis)
        if caster is None or tgt is None:
            return None
        if my is None:
            my = caster.get("owner")
        if dv.get("currentPlayer") != my:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        cid = caster["id"]
        nid = _normal_id(caster)
        if nid is None:
            return None
        d = hexgeo.distance(_cr(caster), _cr(tgt))
        if lo <= d <= hi and tgt["id"] in legal(cid, nid):
            return cid, tgt["id"], nid, my
        dist = bfs(tile_of(tgt))
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == cid), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or []) if t.get("col") is not None}
        cand = [t for t in reach if t in dist]
        if not cand:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        # prefere une tuile DANS la bande [lo..hi] ; sinon celle qui rapproche le plus de hi.
        best = min(cand, key=lambda t: (0 if lo <= dist[t] <= hi else 1, abs(dist[t] - hi), dist[t]))
        col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cid, "to": {"col": col, "row": row}}}, 60)
    return None


def _cast_normal(rpc, rid, cid, tid, nid):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": nid},
        "captureEvents": True}, 120)


def _cast_ok(res):
    if not _ok(res):
        return False
    a0 = (res.get("actions") or [{}])[0]
    return bool(a0.get("ok")) and bool(a0.get("mutated"))


def _offline_state(rpc, rid, board):
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    s = rpc("dumpRng", {"runnerId": rid}, 30)
    st = load_state(dv, ob, snap, board=board)
    if _ok(s):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s["mt"]); rng.mti = s["mti"]
        st.rng = rng
    return st, dv


def _off_pinned(state, tid):
    if state.effects is None:
        return None
    for e in state.effects.by_unit.get(int(tid), []):
        if e.effect_type == PINNED and not e.consumed:
            return e
    return None


# ============================================================ (1) RANGED : Pinned live == offline

def test_suppressive_fire_ranged_pins_live_offline(live_session, rpc):
    """Attaque NORMALE RANGED (d==2) du porteur -> la cible recoit Pinned/Suppressed (1065) LIVE ET
    offline (meme etat pre-attaque). Agreement present/present + remaining>=1."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage

    rid, sf, err = _build("777", CARRIER, f"{TARGET},necroWarden")
    if rid is None:
        pytest.skip(f"build KO: {err}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="evenq")
        placed = _approach(rpc, rid, board, lo=2, hi=RANGE)
        if placed is None:
            pytest.skip("porteur pas amene a distance ranged (2) de la cible (LOS/geometrie)")
        cid, tid, nid, my = placed

        # PRE : la cible ne doit PAS deja porter Pinned (delta = c'est l'attaque qui le pose)
        st_pre, dv_pre = _offline_state(rpc, rid, board)
        if st_pre.get_entity(cid) is None or st_pre.rng is None or st_pre.effects is None:
            pytest.skip("etat offline pre-attaque incomplet")
        assert _pinned_of(dv_pre.get("units"), tid) is None, "cible deja Pinned avant l'attaque (live)"
        assert _off_pinned(st_pre, tid) is None, "cible deja Pinned avant l'attaque (offline)"

        # LIVE : attaque normale ranged
        res = _cast_normal(rpc, rid, cid, tid, nid)
        assert _cast_ok(res), f"attaque live KO: {str(res)[:250]}"
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        pinned_live = _pinned_of(dv2.get("units"), tid)

        # OFFLINE : meme etat pre-attaque -> AttackUnitMessage (vecteur after_hit_normal_attack)
        runner = Runner(st_pre).install_default_handlers(20)
        runner.apply(AttackUnitMessage(cid, tid))
        pinned_off = _off_pinned(st_pre, tid)

        assert pinned_live is not None, (
            f"LIVE : le natif n'a PAS pose Pinned sur la cible (effets={[e for e in (next((u for u in dv2.get('units') or [] if u.get('id')==tid), {}) or {}).get('effects') or []]})")
        assert (pinned_live.get("remaining") or 0) >= 1, f"Pinned live remaining={pinned_live.get('remaining')} < 1"
        assert pinned_off is not None, (
            "OFFLINE : le port n'a PAS pose Pinned (SuppressiveFire trigger non fire / AddEffect no-op)")
        assert (getattr(pinned_off, "remaining_turns", 0) or 0) >= 1, (
            f"Pinned offline remaining_turns={getattr(pinned_off, 'remaining_turns', None)} < 1")
        assert pinned_off.source == cid, (
            f"Pinned offline source={pinned_off.source} != carrier {cid} (AbilityStateReference=owner)")
        print(f"[SF ranged] d=2 : Pinned live(rem={pinned_live.get('remaining')}) == "
              f"offline(rem_turns={pinned_off.remaining_turns}, src={pinned_off.source}) sur cible {tid}")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


# ============================================================ (2) MELEE : AUCUN Pinned live == offline

def test_suppressive_fire_melee_no_pin_live_offline(live_session, rpc):
    """Attaque NORMALE MELEE (d==1, cible adjacente = position melee) du MEME porteur -> AUCUN Pinned
    LIVE ET offline (mirror `IsRangedAttack` POSITION-based). Discriminant de position."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage

    rid, sf, err = _build("777", CARRIER, f"{TARGET},necroWarden")
    if rid is None:
        pytest.skip(f"build KO: {err}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="evenq")
        placed = _approach(rpc, rid, board, lo=1, hi=1)
        if placed is None:
            pytest.skip("porteur pas amene au contact (d=1) de la cible")
        cid, tid, nid, my = placed

        st_pre, dv_pre = _offline_state(rpc, rid, board)
        if st_pre.get_entity(cid) is None or st_pre.rng is None or st_pre.effects is None:
            pytest.skip("etat offline pre-attaque incomplet")
        assert _pinned_of(dv_pre.get("units"), tid) is None, "cible deja Pinned avant l'attaque (live)"

        res = _cast_normal(rpc, rid, cid, tid, nid)
        assert _cast_ok(res), f"attaque melee live KO: {str(res)[:250]}"
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        pinned_live = _pinned_of(dv2.get("units"), tid)

        runner = Runner(st_pre).install_default_handlers(20)
        runner.apply(AttackUnitMessage(cid, tid))
        pinned_off = _off_pinned(st_pre, tid)

        assert pinned_live is None, (
            f"LIVE : Pinned pose sur attaque MELEE (d=1) alors qu'IsRangedAttack=False attendu : {pinned_live}")
        assert pinned_off is None, (
            f"OFFLINE : Pinned pose sur attaque MELEE (le gate _is_ranged_position a fail) : {pinned_off}")
        print(f"[SF melee] d=1 : AUCUN Pinned live/offline (position melee, gate ranged OK) cible {tid}")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


# ============================================================ (3) NON-CARRIER : gate trait (offline)

def test_suppressive_fire_non_carrier_no_pin_offline(live_session, rpc):
    """Discriminant du GATE TRAIT (structurel, offline) : un attaquant SANS le trait SuppressiveFire
    (astraYarrick, ranged) attaquant un ennemi NE pose PAS Pinned — le porteur du trait, lui, le pose.
    Charge un etat live reel, drive les positions OFFLINE (deterministe)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.components import PositionComponent
    from engine.runner.operations.triggers.dispatch import TRAIT_TRIGGERS

    # garde-fou structurel : le trait accorde bien le trigger SuppressiveFire (et lui seul ne se declenche
    # QUE pour un porteur du trait via collect_triggered_abilities).
    assert [c.__name__ for c in TRAIT_TRIGGERS.get("SuppressiveFire", [])] == ["SuppressiveFireAddEffectAbility"]

    rid, sf, err = _build("777", CARRIER, f"{TARGET},necroWarden")
    if rid is None:
        pytest.skip(f"build KO: {err}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="evenq")
        st, dv = _offline_state(rpc, rid, board)
        if st.rng is None or st.effects is None:
            pytest.skip("etat offline incomplet")
        # ids ECS via decisionView (carrier team1, target team2)
        carrier = _find(dv.get("units"), CARRIER)
        target = _find(dv.get("units"), TARGET)
        if carrier is None or target is None:
            pytest.skip("carrier/target absent du build")
        cid, tid = carrier["id"], target["id"]

        def _set(uid, col, row):
            e = st.get_entity(uid)
            pc = e.get_component(PositionComponent) if e is not None else None
            if pc is not None:
                pc.col, pc.row = int(col), int(row)

        # tuiles marchables non-adjacentes : place attaquant/cible a d==2 (ranged position).
        walk = [t for t in board.by_id if board.walkable(t)]
        anchor = walk[0]
        aco = board.coord(anchor)
        ranged_tile = next((t for t in walk if hexgeo.distance(board.coord(t), aco) == 2), None)
        if ranged_tile is None:
            pytest.skip("pas de tuile a d==2 pour le placement offline")
        rco = board.coord(ranged_tile)

        # (A) NON-CARRIER (astraYarrick) attaque le porteur en RANGED -> AUCUN Pinned (gate trait).
        _set(tid, aco[0], aco[1]); _set(cid, rco[0], rco[1])
        assert hexgeo.distance(board.coord(anchor), board.coord(ranged_tile)) == 2
        r1 = Runner(st).install_default_handlers(20)
        r1.apply(AttackUnitMessage(tid, cid))                       # astraYarrick (non-carrier) -> tauDarkstrider
        assert _off_pinned(st, cid) is None, (
            "un attaquant SANS SuppressiveFire a pose Pinned (le trigger fire pour un non-porteur !)")

        # (B) CONTROLE POSITIF meme geometrie : le PORTEUR (tauDarkstrider) attaque en RANGED -> Pinned.
        st2, dv2 = _offline_state(rpc, rid, board)
        st2.rng = st.rng
        # place carrier a l'anchor, cible a la tuile ranged (d==2)
        ec = st2.get_entity(cid).get_component(PositionComponent); ec.col, ec.row = aco[0], aco[1]
        et = st2.get_entity(tid).get_component(PositionComponent); et.col, et.row = rco[0], rco[1]
        r2 = Runner(st2).install_default_handlers(20)
        r2.apply(AttackUnitMessage(cid, tid))                       # tauDarkstrider (carrier) -> astraYarrick
        assert _off_pinned(st2, tid) is not None, (
            "controle positif KO : le porteur SuppressiveFire n'a pas pose Pinned en ranged offline")
        print("[SF non-carrier] gate trait OK : non-porteur -> pas de Pinned ; porteur -> Pinned (meme geometrie d=2)")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


# ====================================================== (4) cible TerminatorArmour : POSE mais INERTE

def test_suppressive_fire_terminator_armour_pins_but_inert(live_session, rpc):
    """GENERALISATION #208 par un AUTRE POSEUR que `SentinelDirectives` (ici un TRIGGER de trait, pas
    un cast d'active) : sur une cible `TerminatorArmour`, l'effet 1065 est bel et bien CREE, et il est
    INACTIF -- `PinnedEffect$$CreateActiveCondition` = `Not(HasTrait(Self, 0x40f))`, evaluee par
    `RefreshEffectsOperation$$ShouldBeActive` (flag `EffectComponent.IsActive @+0x5c`).

    Les deux canaux, des deux cotes :
      live `decisionView` par defaut (DROPPE les inactifs) == port `active_effects` -> ABSENT ;
      live `decisionView includeInactive` (publie tout)    == port `by_unit`        -> PRESENT.
    C'est le mecanisme, pas un refus de pose : le gate d'immunite ne connait que le trait `Immune`."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.components import unit_state_for_effects

    rid, sf, err = _build("777", CARRIER, f"{TERMINATOR_TARGET},necroWarden")
    if rid is None:
        pytest.skip(f"build KO: {err}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="evenq")
        placed = _approach(rpc, rid, board, lo=2, hi=RANGE, target_vis=TERMINATOR_TARGET)
        if placed is None:
            pytest.skip("porteur pas amene a distance ranged (2) de la cible TerminatorArmour")
        cid, tid, nid, my = placed

        st_pre, dv_pre = _offline_state(rpc, rid, board)
        if st_pre.get_entity(cid) is None or st_pre.rng is None or st_pre.effects is None:
            pytest.skip("etat offline pre-attaque incomplet")
        assert _pinned_of(dv_pre.get("units"), tid) is None, "cible deja Pinned avant l'attaque (live)"

        res = _cast_normal(rpc, rid, cid, tid, nid)
        assert _cast_ok(res), f"attaque live KO: {str(res)[:250]}"
        dv_def = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        dv_all = rpc("decisionView",
                     {"runnerId": rid, "allAbilities": True, "includeInactive": True}, 120)
        live_def = _pinned_of(dv_def.get("units"), tid)
        live_all = _pinned_of(dv_all.get("units"), tid)

        runner = Runner(st_pre).install_default_handlers(20)
        runner.apply(AttackUnitMessage(cid, tid))
        off_carried = _off_pinned(st_pre, tid)
        off_active = [e for e in st_pre.effects.active_effects(
            int(tid), unit_state_for_effects(st_pre, int(tid))) if e.effect_type == PINNED]

        print(f"[SF terminator] live def={live_def is not None} all={live_all is not None}"
              f"(active={None if live_all is None else live_all.get('active')}) | "
              f"port carried={off_carried is not None} active={len(off_active)}")
        assert live_all is not None, "LIVE : 1065 absent MEME du canal includeInactive (pas de pose)"
        assert bool(live_all.get("active")) is False, "LIVE : 1065 ACTIF sur un porteur TerminatorArmour"
        assert live_def is None, "LIVE : 1065 publie par le canal actif-only"
        assert off_carried is not None, "PORT : aucune entite-effet 1065 (pose abandonnee a tort)"
        assert not off_active, "PORT : 1065 ACTIF sur un porteur TerminatorArmour (x0.70 fantome)"
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass
