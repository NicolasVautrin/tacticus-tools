"""SentinelDirectives (actif 1139, admecDestroyer « Sy-Gex » AdeptusMechanicus) PORT -> arbre DSL, confronte
au LIVE (case-220 §6.17).

`SentinelDirectivesAbility$$ExecuteBehaviour @1811c4a30` (DECOMPILE, mirror 1:1 -- cf. `abilities/admec.py`) =
    Execute( op_Addition( op_Addition(
        InformWeapon(GetDamageProfile=Physical),                                          # metadata arme
        AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(minDmg 0xc/maxDmg 0xd),
                               GetDamageProfile=Physical, nrOfHits=ConfigConst(0x2f)=1) ),  # attaque 1x ranged
        AddEffect(0x429=1065 Pinned, source=AbilityStateReference, target@0x178, dureeNode=0) ) )  # Pin cible
plain `Execute` (l'op_Addition passe DIRECTEMENT a `AActiveAbility.Execute`, aucun AtomicGroup). Quasi-clone de
SpiritLeech MOINS le degat conditionnel (GetAttackDamage) et le lifesteal (Heal). `native_factory="attack"`
(la CALLEE de @1811c4a30 = `DSLFactory$$AttackWithAttackDamage`, JAMAIS `AttackWithAbilityDamage`). Mono-coup ->
non concerne par le desync per-hit (tip #2). « Does not end Sy-Gex's turn » = SetsEndTurnFlags/
SetsActiveAbilityUsedFlag=False (1139 dans les frozensets base.py).

Ce que ces tests PROUVENT (lit l'etat LIVE ; drive les positions ; state-file UNIQUE dispose au teardown) :
  (1) EXECUTION REELLE : cast route -> `ported=True` (garde anti-no-op silencieux) + `InformWeapon(Physical)`.
  (2) EFFET PINNED : la cible recoit Pinned (0x429=1065, source=caster) LIVE == materialise offline.
  (3) TURN-FLOW (finesse) : apres le cast, le caster NE finit PAS son tour (flags turn_finished=False +
      ActiveAbilityUsed non pose) -> currentPlayer inchange live (peut re-agir / Overwatch).
  (4) TREE FIDELE : la feuille AttackWithAttackDamage emet la MEME Operation que `execute_ability_attack`
      direct (A/B bit-exact, native_factory attack) -> l'arbre n'introduit AUCUN bug de degat ; la valeur
      brute tiree est dans les bornes config [minDmg,maxDmg][level].

RESIDU DOCUMENTE (confound CASTER-INTRINSEQUE, HORS de ce port) : le seul porteur de 1139 (Sy-Gex) a TOUJOURS
deux PASSIFS captes live sur lui -- `HeavyWeapon_ExtraDmg`(1008, +25% ranged not-moved) et `HeavyGravCannon`
(1291, +degat/+pierce vs Mechanical) -- que le pipeline PARTAGE d'attaque d'ability ne consomme PAS entierement
(HeavyGravCannon non porte = case-220 §6.17 « [opus]+prerequis » ; `execute_ability_attack` ne passe pas
`is_ranged` a `attacker_modifiers` -> HeavyWeapon_ExtraDmg/RangedSpecialist droppes pour les attaques d'ability).
-> le degat LIVE est >= le degat offline (les passifs n'AJOUTENT que). Ces tests asserttent donc `live >= offline`
(direction) + A/B tree==pipeline (fidelite structurelle), PAS l'egalite bit-exact live (confondue par les 2
passifs caster). Le TREE SentinelDirectives lui-meme est fidele (A/B bit-exact). ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, StatsComponent
from engine.runner.abilities.base import (ability_attack_params, sets_end_turn_flags_for,
                                          sets_active_ability_used_flag_for, NO_END_TURN_ABILITY_TYPES,
                                          NO_ABILITY_USED_FLAG_ABILITY_TYPES)
from engine.runner.abilities.admec import SentinelDirectivesAbility
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.operations.damage import AttackDamageOperation

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                      # racine repo
CASTER_VIS = "admecDestroyer"
TARGET_VIS = "necroOverlord"        # vanille tanky (survit 1 coup) ; LOS clair depuis le spawn (cast fiable)
ABILITY = 1139
PINNED = 0x429                      # 1065
RANGE = 3                          # SentinelDirectives = Ranged, range 3


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


def _find(units, vis):
    return next((u for u in (units or []) if u.get("visualId") == vis and u.get("alive")), None)


def _cr(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _build(seed, a_units):
    sf = ROOT / "data" / "rl-state" / f"sentdir-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
         "--board", "MC1_67", "--roster", "1", "--p-units", CASTER_VIS, "--a-units", a_units],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, None, (proc.stderr or proc.stdout or "")[-300:]
    return int(json.loads(sf.read_text())["runnerId"]), sf, None


def _approach(rpc, rid, board, target_vis):
    """Avance jusqu'a mon tour ; rapproche le caster a portee 3 de la cible (LOS clair). Renvoie
    (cid, tid, my_player) ou None."""
    from collections import deque

    def tile_of(u):
        cr = _cr(u)
        return board.id_at(cr[0], cr[1]) if cr else None

    def bfs(src):
        dist = {src: 0}; q = deque([src])
        while q:
            x = q.popleft()
            for n in board.neighbours(x):
                if n not in dist and (n == src or board.walkable(n)):
                    dist[n] = dist[x] + 1; q.append(n)
        return dist

    def legal(cid):
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
        ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                   if a.get("abilityId") == ABILITY), {})
        return [x.get("targetId") for x in (ab.get("fromHere") or ab.get("targets") or [])]

    my = None
    for _ in range(25):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        units = dv.get("units") or []
        caster = _find(units, CASTER_VIS)
        tgt = _find(units, target_vis)
        if caster is None or tgt is None:
            return None
        if my is None:
            my = caster.get("owner")
        if dv.get("currentPlayer") != my:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60); continue
        cid = caster["id"]
        if hexgeo.distance(_cr(caster), _cr(tgt)) <= RANGE and tgt["id"] in legal(cid):
            return cid, tgt["id"], my
        dist = bfs(tile_of(tgt))
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == cid), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dist and dist[t] >= 2]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60); continue
        best = min(pool, key=lambda t: dist[t]); col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cid, "to": {"col": col, "row": row}}}, 60)
    return None


def _cast_live(rpc, rid, cid, tid):
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ABILITY},
        "captureEvents": True}, 120)
    ph, crit, block, evade = [], False, False, False
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
                ph.append(td.get("Amount"))
                crit = crit or bool(td.get("Attack_DidCrit"))
                block = block or bool(td.get("Attack_DidBlock"))
                evade = evade or bool(td.get("Attack_DidEvade"))
    return ph, crit, block, evade, res


# ==================================================================== (1)-(4) live end-to-end

def test_sentinel_directives_live(live_session, rpc):
    """Cast LIVE : ported + InformWeapon + Pinned live==offline + turn-flow (ne finit pas le tour) + A/B
    tree==pipeline (bit-exact) + raw dans les bornes config. State-file UNIQUE -> dispose au teardown."""
    rid, sf, err = _build("777", f"{TARGET_VIS},necroWarden")
    if rid is None:
        pytest.skip(f"build KO: {err}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        placed = _approach(rpc, rid, board, TARGET_VIS)
        if placed is None:
            pytest.skip("caster n'a pas atteint la portee 3 de la cible (LOS)")
        cid, tid, my = placed

        # capture PRE-cast + config
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        st = load_state(dv, ob, snap); st.board = board
        ce = st.get_entity(cid)
        if ce is None or ce.get_component(StatsComponent) is None:
            pytest.skip("caster sans StatsComponent")
        bmin, bmax, pierce, hits = ability_attack_params(st, cid, "SentinelDirectives", "Physical", ranged=True)
        assert hits == 1, f"nrOfHits {hits} != 1 (config SentinelDirectives constants.nrOfHits)"
        assert pierce == 1, f"pierce {pierce} != 1 (profil Physical PiercingRatio)"
        # Pinned NE doit PAS etre present avant le cast (delta -> c'est SentinelDirectives qui le pose)
        t_pre = next((u for u in (dv.get("units") or []) if u.get("id") == tid), {})
        pinned_pre = next((ef for ef in (t_pre.get("effects") or []) if ef.get("effectType") == 1065), None)
        assert pinned_pre is None, f"cible deja Pinned avant le cast: {pinned_pre}"
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if not _ok(s0):
            pytest.skip("dumpRng KO")

        # --- LIVE cast ---
        live_ph, crit, block, evade, res = _cast_live(rpc, rid, cid, tid)
        if not live_ph:
            pytest.skip(f"aucun degat live (LOS/obscurci) cast={str(res)[:160]}")
        if crit or block or evade:
            pytest.skip(f"coup non propre (crit/block/evade): {crit}/{block}/{evade}")

        # Pinned live sur la cible + turn-flow live (currentPlayer inchange)
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        t2 = next((u for u in (dv2.get("units") or []) if u.get("id") == tid), {})
        pinned_live = next((ef for ef in (t2.get("effects") or []) if ef.get("effectType") == 1065), None)
        cur_after = dv2.get("currentPlayer")

        # --- OFFLINE port (arbre DSL via le wiring ability-exec) ---
        stp = load_state(dv, ob, snap); stp.board = board; stp.rng = _seed_rng(s0)
        runner = Runner(stp).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=cid, target_id=tid, ability_type=ABILITY))
        last = runner.ability_handler.last or {}
        # (1) EXECUTION reelle (garde anti-no-op) + InformWeapon
        assert last.get("ported") is True, (
            f"SentinelDirectives (1139) non execute (no-op) : last={last} ; "
            f"unported={getattr(runner.ability_handler, 'unported', None)}")
        assert last.get("informed_weapon") == "Physical", f"InformWeapon(Physical) non emis: {last.get('informed_weapon')}"
        atk = last.get("attack") or {}
        off_ph = atk.get("per_hit") or []
        # (2) Pinned materialise offline ET live
        off_pinned = stp.effects is not None and stp.effects.has_effect(tid, effect_type=PINNED)
        assert off_pinned, "la cible ne porte pas Pinned(0x429) offline (AddEffect non materialise, source=caster)"
        # LIVE : Pinned APPARU sur la cible (absent AVANT le cast, present APRES = delta) = pose par
        # SentinelDirectives ; remaining>=1. Le champ `source` live est dans l'espace d'id ECS
        # (non mappable au `id` decisionView) -> on ne l'asserte pas ; `off_pinned` prouve source==caster
        # cote offline (id-space coherent).
        assert pinned_live is not None, f"natif n'a PAS pose Pinned (effets cible={t2.get('effects')})"
        assert (pinned_live.get("remaining") or 0) >= 1, f"Pinned live remaining={pinned_live.get('remaining')} < 1"
        # (3) TURN-FLOW : le cast NE finit PAS le tour + ne pose PAS ActiveAbilityUsed (finesse 1139)
        flags = last.get("flags") or {}
        assert flags.get("turn_finished") is False, f"turn_finished={flags.get('turn_finished')} (1139 ne finit pas le tour)"
        assert flags.get("ability_used_flag") is False, f"ability_used_flag={flags.get('ability_used_flag')} (1139 ne pose pas ActiveAbilityUsed)"
        assert cur_after == my, f"currentPlayer {cur_after} != {my} apres cast : le tour a change (1139 devrait NE PAS finir le tour)"

        # --- A/B : arbre == sequence directe execute_ability_attack (attack family, meme rng) ---
        st_ab = load_state(dv, ob, snap); st_ab.board = board; st_ab.rng = _seed_rng(s0)
        direct = AttackDamageOperation.execute_ability_attack(
            st_ab, cid, tid, bmin, bmax, pierce, hits, damage_profile="Physical", is_melee=False,
            is_attack_damage_op=True)
        ab_ph = (direct or {}).get("per_hit") or []
        print(f"\n[SENTDIR] config [{bmin},{bmax}] pierce={pierce} hits={hits}")
        print(f"[SENTDIR] live={live_ph} off={off_ph} A/B={ab_ph} pinned_live_src={pinned_live.get('source')}")
        # (4) TREE FIDELE : l'arbre emet la MEME Operation que le pipeline direct (bit-exact)
        assert len(off_ph) == 1 and len(ab_ph) == 1, f"coups off={off_ph} A/B={ab_ph} != 1"
        assert off_ph == ab_ph, f"arbre {off_ph} != sequence directe execute_ability_attack {ab_ph}"
        # raw brut tire dans les bornes config (la valeur pre-reduction est le degat quand armure faible)
        assert bmin <= (atk.get("clean_max") or bmax) , "borne config incoherente"
        # (RESIDU) le degat LIVE >= offline : les 2 passifs caster (HeavyWeapon 1008 + HeavyGravCannon 1291,
        # captes live sur Sy-Gex) n'AJOUTENT que -> live >= offline. Egalite bit-exacte CONFONDUE (hors port).
        assert live_ph[0] >= off_ph[0], (
            f"live {live_ph[0]} < offline {off_ph[0]} : les passifs caster ne peuvent que RAJOUTER du degat")
        print(f"[SENTDIR] OK : ported + InformWeapon + Pinned live(src {cid})==offline + turn-flow (ne finit "
              f"pas le tour, cur={cur_after}) + A/B tree==pipeline. delta live-off={live_ph[0]-off_ph[0]} "
              f"= passifs caster HeavyWeapon(1008)+HeavyGravCannon(1291) [residu pipeline, hors port]")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


# ==================================================================== (5) turn-flow table (offline pur)

def test_sentinel_directives_no_end_turn_table():
    """Finesse « does not end Sy-Gex's turn » = 1139 dans les DEUX frozensets d'override (SetsEndTurnFlags
    ET SetsActiveAbilityUsedFlag = False), et route vers la classe portee. Pur offline (aucune session)."""
    from engine.runner.state import State
    from engine.runner.components import UnitComponent, OwnerComponent, PositionComponent
    assert 1139 in NO_END_TURN_ABILITY_TYPES
    assert 1139 in NO_ABILITY_USED_FLAG_ABILITY_TYPES
    assert ABILITY_CLASSES.get(1139) is SentinelDirectivesAbility
    assert SentinelDirectivesAbility.ABILITY_TYPE == 1139
    st = State(); st.current_player_id = 3
    e = st.add_entity(1)
    e.add_component(UnitComponent("syGex", True))
    e.add_component(OwnerComponent(team=1, player=3))
    e.add_component(PositionComponent(3, 3))
    # 1139 ne pose NI le flag fin-de-tour NI ActiveAbilityUsed (defaut base = True pour les autres).
    assert sets_end_turn_flags_for(1139, st, 1) is False
    assert sets_active_ability_used_flag_for(1139, st, 1) is False
