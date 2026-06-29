"""VECTEUR ATTAQUE — matérialisation d'effet (replay-diff LIVE vs cœur porté).

Valide `AddEffectOperation` (engine/runner/operations/effects.py) contre le moteur natif : une
attaque active qui pose un Stun (templSwordBrother / ThunderousAssault id 1043 — DSL RE'd :
`AttackWithAttackDamage & AddEffect(0x48a=1162 Stunned, durée=TurnsFromRounds(1 round))`) doit
matérialiser sur la cible le MÊME effet que celui que mon `AddEffectOperation` produit offline.

Protocole (mêmes invariants que les tests crit/block : lit l'état LIVE, pas de tuile/RVA hardcodée,
seed = simple générateur) :
  1. build 1v1 isolé templSwordBrother vs tyranTyrantGuard (tanky + BigTarget non-déplaçable ⇒
     survit + le push de l'ability est no-op) ; positionne le caster au contact hex.
  2. capture l'état AVANT (decisionView/observe/combatSnapshot) → `load_state` (EffectsState seedé).
  3. caste ThunderousAssault LIVE (applyAction) → lit les effets de la cible APRÈS.
  4. rejoue OFFLINE la matérialisation : `AddEffectOperation.execute(state, source, target, 1162)`.
  5. CONFRONTE : le natif pose Stunned (1162) sur la cible avec `remaining` = R ; mon op doit poser
     un effet effect_type=1162 de `remaining_turns` == R. + `default_amount_of_rounds(1162)` == R.

NB : Stunned natif est COMPOSITE (parent 1162 + enfants 1165/1166/1167 via ParentEffect) — ce test
valide le PARENT (ce que le cœur porte aujourd'hui) ; le spawn des enfants = sous-étape suivante
(documentée). On n'asserte donc PAS l'égalité de l'ensemble complet, mais la pose fidèle du parent.
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.operations.effects import default_amount_of_rounds

CASTER_VIS = "templSwordBrother"
TARGET_VIS = "tyranTyrantGuard"
ABILITY = 1043          # ThunderousAssault
STUNNED = 1162          # EffectType.Stunned (0x48a)
BUILD = ["--roster", "1", "--p-units", CASTER_VIS, "--a-units", TARGET_VIS]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _board(rpc, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return None
    return Board(bg["tiles"], adjacency="native_sym")


def _bfs(board, src):
    dist = {src: 0}; q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1; q.append(n)
    return dist


def _stun_of(effs):
    return next((e for e in (effs or [])
                 if e.get("effectType") == STUNNED or e.get("name") == "Stunned"), None)


def test_thunderous_assault_materializes_stun(live_session, rpc, build_runner):
    """ThunderousAssault pose Stunned(1162) sur la cible ; `AddEffectOperation` reproduit le parent."""
    rid = build_runner("777", extra=BUILD)["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")

    def tile_of(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None

    # --- positionner le caster au contact hex de la cible ---
    my_player = None
    caster = tgt = None
    for _turn in range(25):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if not _ok(dec):
            pytest.skip("decisionView KO")
        units = dec.get("units") or []
        caster = next((u for u in units if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
        tgt = next((u for u in units if u.get("visualId") == TARGET_VIS and u.get("alive")), None)
        if caster is None or tgt is None:
            pytest.skip(f"unite manquante (caster={bool(caster)} tgt={bool(tgt)})")
        if my_player is None:
            my_player = caster.get("owner")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        ct, tt = tile_of(caster), tile_of(tgt)
        if ct in board.neighbours(tt):
            break
        dist = _bfs(board, tt)
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == caster["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        best = min(pool, key=lambda t: dist[t]); col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": caster["id"], "to": {"col": col, "row": row}}}, 40)
    else:
        pytest.skip("caster n'a pas atteint la cible en 25 tours")

    att, tid = caster["id"], tgt["id"]

    # --- capture l'état AVANT (offline) ---
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv, ob, snap)
    if state.effects is None:
        pytest.skip("EffectsState non chargé (combatSnapshot absent)")
    before_live = _stun_of((next((u for u in (dv.get("units") or []) if u.get("id") == tid), {}) or {})
                           .get("effects"))
    assert before_live is None, f"cible deja Stunned avant le cast: {before_live}"

    # --- cast LIVE ---
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": ABILITY}}, 60)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        pytest.skip(f"cast KO: {str(res)[:160]}")
    dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    t2 = next((u for u in (dv2.get("units") or []) if u.get("id") == tid), None)
    if not (t2 and t2.get("alive")):
        pytest.skip("cible morte au cast (choisir une cible plus tanky)")
    live_stun = _stun_of(t2.get("effects"))
    assert live_stun is not None, f"natif n'a PAS posé Stunned (effets={t2.get('effects')})"
    live_remaining = live_stun.get("remaining")
    assert default_amount_of_rounds(STUNNED) == live_remaining, (
        f"default_amount_of_rounds(1162)={default_amount_of_rounds(STUNNED)} != live remaining={live_remaining}")

    # --- ABILITY-EXEC OFFLINE : l'engine DÉRIVE l'effet depuis le cast (mirror ExecuteBehaviour) ---
    # PAS d'appel direct à AddEffectOperation : on applique le MÊME message d'ability que le live.
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=att, target_id=tid, ability_type=ABILITY))
    assert runner.ability_handler.last and runner.ability_handler.last.get("ported"), \
        f"ability {ABILITY} non routée par le wiring ability-exec"
    off_parent = next((e for e in state.effects.active_effects(tid) if e.effect_type == STUNNED), None)
    assert off_parent is not None, "le wiring ability-exec n'a pas dérivé Stunned depuis le cast"

    # --- CONFRONTE la FAMILLE Stun complète (parent 1162 + enfants 1165/1166/1167) ---
    # famille = types apparus APRÈS le cast (delta vs avant) côté live, restreint au composite Stun.
    FAMILY = {STUNNED, 1165, 1166, 1167}
    before_types = {e.get("effectType") for e in
                    ((next((u for u in (dv.get("units") or []) if u.get("id") == tid), {}) or {}).get("effects") or [])}
    live_by = {e.get("effectType"): e.get("remaining") for e in (t2.get("effects") or [])
               if e.get("effectType") in FAMILY and e.get("effectType") not in before_types}
    off_by = {e.effect_type: e.remaining_turns for e in state.effects.active_effects(tid)
              if e.effect_type in FAMILY}
    assert set(off_by) == set(live_by), (
        f"famille Stun matérialisée diverge: offline={sorted(off_by)} live={sorted(live_by)}")
    # durée : live rem (0 = permanent) <-> mon remaining_turns (None = permanent) ; rem>0 == egal.
    for et, live_rem in live_by.items():
        exp = None if (live_rem in (0, None)) else live_rem
        assert off_by[et] == exp, (
            f"effet {et}: remaining offline={off_by[et]} != live={live_rem} (map 0->None)")
    print(f"\n[STUN composite] live={sorted(live_by.items())} "
          f"off={sorted((k, v) for k, v in off_by.items())} OK (parent 1162 + enfants 1165/1166/1167)")

    # --- CYCLE DE VIE des enfants : à l'expiration du parent, TOUTE la famille part ENSEMBLE ---
    # OFFLINE : un tick de fin-de-tour de la cible (parent rem 1->0) doit cascader le retrait des
    # enfants permanents (1166/1167 via RevertInternal) + l'enfant same-turns (1165). Famille vide.
    state.effects.on_turn_end(tid, attacked=False)
    off_after = {e.effect_type for e in state.effects.active_effects(tid) if e.effect_type in FAMILY}
    assert off_after == set(), f"offline: famille Stun pas entierement retiree apres tour-fin: {off_after}"

    # LIVE : drive les tours ; INVARIANT « famille ensemble » (jamais d'enfant orphelin sans le parent)
    # + la famille DOIT disparaitre (cycle de vie effectif). Borne basse pour rester rapide.
    seen_empty = False
    for _step in range(6):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        dvN = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        tN = next((u for u in (dvN.get("units") or []) if u.get("id") == tid), None)
        if tN is None or not tN.get("alive"):
            seen_empty = True; break
        famN = {e.get("effectType") for e in (tN.get("effects") or []) if e.get("effectType") in FAMILY}
        # invariant : si le parent est parti, AUCUN enfant ne subsiste (pas d'orphelin)
        if STUNNED not in famN:
            assert famN == set(), f"enfants Stun ORPHELINS (parent parti, enfants restants): {famN}"
            seen_empty = True; break
    assert seen_empty, "la famille Stun n'a pas expire live dans la fenetre de tours"
    print("[STUN lifecycle] OK : parent expire -> famille entiere retiree (offline cascade == live)")
