"""VECTEUR ATTAQUE — CrushingClaws (1105) migre en ARBRE DSL (#149 slice-4) : replay-diff LIVE.

Valide la migration DSL de `CrushingClawsAbility.execute_behaviour` (delegue a `crushing_claws_tree`,
mirror 1:1 de `IdunBattleLogic.Entities.Abilities.Active.Loki.CrushingClawsAbility$$ExecuteBehaviour` + lambda `<ExecuteBehaviour>b__0 IdunBattleLogic.Entities.Abilities.Active.Loki.CrushingClawsAbility.u003Cu003Ec__DisplayClass1_0$$u003CExecuteBehaviouru003Eb__0`) contre le
natif : cast LIVE de CrushingClaws (tyranTyrantGuard) sur une cible tanky vanille -> l'engine, en
rejouant le MEME message d'ability, doit reproduire
  (a) le degat PRINCIPAL de l'ARBRE == un appel main-only DIRECT (2x Piercing, `AttackWithAbilityDamage(
      Target())`) = FIDELITE MIGRATION (bit-exact vs baseline imperative ; les effets pin/taunt actifs par
      l'ordre natif ne changent PAS le degat, cf. A/B), et
  (b) les EFFETS poses sur la cible : Taunted(27, COMPOSITE 25/26/1237, `AddBondEffect`) + Pinned(1065,
      `AddEffect`, duree DEFAUT).

Le per-coup principal vs LIVE a un GAP CONNU PRE-EXISTANT (#205, pipeline Piercing/armure, ex. off
[1589,1469] vs live [1590,1490]) — INDEPENDANT de la migration (prouve A/B) donc NON asserte exact ici.

En 1v1 (caster vs cible), le SPLASH `And(AdjacentEnemies(caster), AdjacentEnemies(target))` est VIDE (le
seul ennemi = la cible, auto-exclue) -> AUCUN tirage rng splash -> le per-coup principal se confronte
propre (comme le test d'attaque normale / ThunderousAssault). Le SPLASH (geometrie 3-unites) reutilise
les MEMES noeuds deja valides (`AttackWithAbilityDamage` clés `_2` valide par l'imperatif, `AddEffect`,
`If(IsAlive)`, `Foreach`) + le selecteur pattern-Harvester (valide seed777) -> bit-exact BY CONSTRUCTION ;
son confront LIVE dedie = suite (deferrable).

Invariants harnais (comme crit/block/stun) : lit l'etat LIVE, aucune tuile/RVA hardcodee, seed = simple
generateur, drive les positions jusqu'au contact.
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import StatsComponent
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.abilities.base import ability_attack_params

CASTER_VIS = "tyranTyrantGuard"      # id 1105 CrushingClaws
TARGET_VIS = "necroOverlord"         # cible vanille tanky (hp~8536, effects=[] : survit + 0 reduction/block)
ABILITY = 1105
TAUNTED = 27                         # EffectType.Taunted_OnlySpecificTargets (composite 25/26/1237)
PINNED = 1065                        # EffectType.Pinned (« Suppressed »)
BUILD = ["--roster", "1", "--p-units", CASTER_VIS, "--a-units", TARGET_VIS]


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


def _has_eff(effs, et, name_prefix):
    return any((e.get("effectType") == et) or str(e.get("name") or "").startswith(name_prefix)
               for e in (effs or []))


def test_crushing_claws_dsl_main_bit_exact_and_effects(live_session, rpc, build_runner):
    """CrushingClaws DSL : degat principal per-coup bit-exact + Taunted(27)+Pinned(1065) poses (off==live)."""
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")

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
        if tile_of(caster) in board.neighbours(tile_of(tgt)):
            break
        dist = _bfs(board, tile_of(tgt))
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

    # --- capture AVANT + seed rng (replay de degat) ---
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    state = load_state(dv, ob, snap)
    if state.effects is None:
        pytest.skip("EffectsState non charge (combatSnapshot absent)")
    ae = state.get_entity(att)
    if ae is None or ae.get_component(StatsComponent) is None:
        pytest.skip("attaquant sans StatsComponent (stats non chargees)")
    t_before = (next((u for u in (dv.get("units") or []) if u.get("id") == tid), {}) or {}).get("effects")
    if _has_eff(t_before, PINNED, "Pinned") or _has_eff(t_before, TAUNTED, "Taunted"):
        pytest.skip("cible deja Taunted/Pinned avant le cast")
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")
    state.rng = _seed_rng(s0)

    # --- cast LIVE ---
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": ABILITY}}, 60)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        pytest.skip(f"cast KO: {str(res)[:160]}")
    live_ph, dc, db, de = [], False, False, False
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
            live_ph.append(td.get("Amount"))
            dc = dc or bool(td.get("Attack_DidCrit"))
            db = db or bool(td.get("Attack_DidBlock"))
            de = de or bool(td.get("Attack_DidEvade"))
    if dc or db or de:
        pytest.skip(f"coup non propre (crit/block/evade live) hors axe param-ability: c={dc} b={db} e={de}")
    if not live_ph:
        pytest.skip("aucun event de degat principal live (cible hors portee ?)")
    dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    t2 = next((u for u in (dv2.get("units") or []) if u.get("id") == tid), None)
    if not (t2 and t2.get("alive")):
        pytest.skip("cible morte au cast (choisir une cible plus tanky)")
    # effets LIVE poses par le natif :
    assert _has_eff(t2.get("effects"), PINNED, "Pinned"), \
        f"natif n'a PAS pose Pinned(1065) (effets={t2.get('effects')})"
    assert _has_eff(t2.get("effects"), TAUNTED, "Taunted"), \
        f"natif n'a PAS pose Taunted(27) (effets={t2.get('effects')})"

    # --- ABILITY-EXEC OFFLINE : l'engine DERIVE l'arbre DSL depuis le cast (crushing_claws_tree) ---
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=att, target_id=tid, ability_type=ABILITY))
    last = runner.ability_handler.last or {}
    assert last.get("ported"), f"ability {ABILITY} non routee par le wiring ability-exec: {last}"
    main = last.get("main_attack")
    assert main is not None, f"pas de main_attack offline: {last}"
    off_ph = main["per_hit"]
    assert len(off_ph) == main["hits"] == 2, \
        f"structure main CrushingClaws attendue hits=2: hits={main['hits']} per_hit={off_ph}"
    print(f"\n[CrushingClaws DSL] hits={main['hits']} base=[{main['base_min']},{main['base_max']}] "
          f"pierce={main['pierce']} armor={main['armor']} live_ph={live_ph} off_ph={off_ph}")

    # --- FIDELITE MIGRATION : le degat de l'ARBRE == un appel main-only DIRECT (mêmes profil/clés Piercing)
    # sur un state FRAIS re-seede -> prouve que la migration DSL reproduit BIT-EXACT la baseline imperative
    # (l'arbre ne change PAS le degat ; les effets pin/taunt actifs par l'ordre natif ne le modifient pas —
    # A/B probe cc_ab_probe : main-only == arbre). C'est LA validation du contrat slice-4 sur le degat.
    ref_state = load_state(dv, ob, snap); ref_state.rng = _seed_rng(s0)
    bmin, bmax, pierce, hits = ability_attack_params(ref_state, att, "CrushingClaws", "Piercing", ranged=False)
    ref = AttackDamageOperation.execute_ability_attack(ref_state, att, tid, bmin, bmax, pierce, hits,
                                                       damage_profile="Piercing", is_melee=True)
    assert off_ph == ref["per_hit"], \
        f"arbre {off_ph} != baseline main-only {ref['per_hit']} (migration DSL NON bit-exact vs imperatif)"

    # --- effets OFFLINE (arbre DSL) : Pinned(1065) + famille Taunted (27/25/26/1237) sur la cible ---
    off_ets = {e.effect_type for e in state.effects.active_effects(tid)}
    assert PINNED in off_ets, f"offline (DSL) n'a PAS pose Pinned(1065): {sorted(off_ets)}"
    assert any(et in off_ets for et in (TAUNTED, 25, 26, 1237)), \
        f"offline (DSL) n'a PAS pose la famille Taunted: {sorted(off_ets)}"

    # --- GAP CONNU #205 (PRE-EXISTANT, hors migration) : per-coup principal vs LIVE diverge legerement
    # (pipeline degat Piercing/armure haute — ex. off=[1589,1469] vs live=[1590,1490]). PROUVE independant
    # de la migration par A/B (main-only == arbre) -> NON asserte exact ici (l'ancien imperatif aurait
    # echoue a l'identique). Tracke #205 ; ce test valide la MIGRATION, pas le pipeline Piercing.
    if off_ph != live_ph:
        print(f"[#205 GAP CONNU pre-existant] per-coup principal off={off_ph} != live={live_ph} "
              f"(pipeline Piercing/armure, hors migration slice-4)")
    print(f"[CrushingClaws DSL] OK : main hits={main['hits']} == baseline main-only (migration bit-exact) ; "
          f"effets cible offline={sorted(off_ets & {PINNED, TAUNTED, 25, 26, 1237})} (Pinned+Taunted) "
          f"; live Pinned+Taunted confirmes ; splash 1v1 vide")
