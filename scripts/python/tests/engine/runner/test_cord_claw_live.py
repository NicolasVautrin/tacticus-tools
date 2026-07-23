"""CordClaw (1122, admecRuststalker « Exitor-Rho », AdMech) -- face COMBAT (execute) portee, confrontee au LIVE.

`CordClawAbility.ExecuteBehaviour @1811ccbf0` (DECOMPILE) =
    Execute( op_Addition(
        AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(minDmg 0xc/maxDmg 0xd),
                               GetDamageProfile=DirectDamage, nrOfHits=GetHits=GetNumberConstant(0x2f)=4),
        AddEffect(0x4e2=1250 CordClaw_AdditionHits, source=AbilityStateReference, target=Self@0x148,
                  TurnsFromRounds(2)) ) )
JUMEAU d'ArmoriumCherub (`GetHits` = corps PARTAGE, Ghidra mislabel `ArmoriumCherubAbility$$GetHits`, lit la
config CORDCLAW). Le 2e volet = `AddEffect` SELF (au lieu de l'`EvaluateAbilities` d'ArmoriumCherub) : pose sur
le caster l'effet 0x4e2 (DEJA porte `hits.py:CordClawAdditionalHitsEffect`, canal #179) 2 rounds -> les attaques
SUIVANTES du caster gagnent +nrOfHits_2=2 coups [minDmg_2,maxDmg_2] DirectDamage (i2 : « All of Exitor-Rho's
further attacks ... deal an additional 2x 582-873 Direct Damage »). L'attaque DU CAST ne les gagne PAS (effet
pose APRES l'attaque dans op_add).

CONFRONTATION LIVE (state-file UNIQUE ; doctrine drive-positions : on avance la bataille jusqu'a un tour ou le
caster peut atteindre une tuile d'attaque, on move+cast) :
  A. LIVE cast -> effet 1250 sur le CASTER present au tour N+1 (self-buff pose + persiste) + cible degatee.
  B. OFFLINE agreement (port `CordClawAbility.execute_behaviour`) : effet 1250 pose (==live) + seede (niveau/
     mult) + attaque 4 coups DirectDamage, total coherent avec le degat LIVE (4x DirectDamage pierce 100).
  C. coups additionnels : l'effet resout `additional_hit_groups` = 2x[minDmg_2,maxDmg_2] DirectDamage (oracle
     gameconfig au niveau du caster) ; une attaque NORMALE du caster bufe applique +2 coups DirectDamage.

Bit-exactness du main-attack (offline vs live) = CONFONDUE par le rng block/crit -> on confronte la COHERENCE
(4 coups DirectDamage plausibles), pas l'egalite stricte (la machinerie `execute_ability_attack` est deja
bit-exact validee ailleurs, ex. ThunderousAssault). Lit l'etat LIVE. ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import gameconfig as GC
from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import StatsComponent, PositionComponent
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.loki import CordClawAbility
from engine.runner.abilities.loki.strike import _seed_cord_claw_hits_level
from engine.runner.abilities.base import ability_attack_params
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.effects import AddEffectOperation

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                      # racine repo
CASTER_VIS = "admecRuststalker"
ABILITY = 1122
EFFECT = 1250                                                # CordClaw_AdditionHits (0x4e2)
# ennemis multiples -> la bataille ne se termine PAS au 1er kill (on peut observer le tour N+1).
A_UNITS = "necroWarden,necroWarden,necroWarden,necroOverlord"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _by_id(dec, uid):
    return next((u for u in (dec.get("units") or []) if u.get("id") == uid), None)


def _find(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _effids(u):
    return {e.get("effectType") for e in ((u or {}).get("effects") or []) if e.get("effectType") is not None}


def _hp(u):
    if not u:
        return None
    h = u.get("health")
    if isinstance(h, dict):
        return h.get("current", h.get("hp"))
    return h if isinstance(h, (int, float)) else None


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _mv(key, lvl, mult):
    a = GC.ability("CordClaw") or {}
    arr = a.get("variables", {}).get(key)
    base = int(arr[max(0, min((lvl or 1) - 1, len(arr) - 1))])
    aff = a.get("variablesAffectedByRarityBonus", [])
    return round(base * (mult or 100) / 100) if (key in aff and (mult or 100) != 100) else base


def test_cord_claw_execute_live(live_session, rpc):
    """Confronte le port CordClaw au LIVE : cast -> effet self au tour N+1 (A) ; agreement offline du behaviour
    (B) ; coups additionnels DirectDamage au tour suivant (C). State-file UNIQUE -> dispose au teardown."""
    state_file = ROOT / "data" / "rl-state" / f"cordclaw-test-{uuid.uuid4().hex[:8]}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "777", "--state-file", str(state_file),
         "--board", "MC1_67", "--roster", "1", "--p-units", CASTER_VIS, "--a-units", A_UNITS],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        pytest.skip(f"build runner KO: {(proc.stderr or proc.stdout or '')[-300:]}")
    rid = json.loads(state_file.read_text())["runnerId"]
    try:
        # --- avance jusqu'a un MON-tour ou CordClaw atteint une tuile d'attaque (move inclus) ---
        cast_ctx = None
        for _ in range(22):
            dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            if not _ok(dec):
                pytest.skip("decisionView KO")
            caster = _find(dec, CASTER_VIS)
            if caster is None:
                break
            if caster.get("owner") == dec.get("currentPlayer"):
                at = rpc("abilityTargets", {"runnerId": rid, "unitId": caster["id"], "abilityType": ABILITY}, 90)
                ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                           if a.get("abilityId") == ABILITY), {})
                for t in (ab.get("targets") or []):
                    tid = t.get("targetId")
                    if _by_id(dec, tid) is None:
                        continue
                    ar = rpc("aiAttackRank", {"runnerId": rid, "unitId": caster["id"],
                                              "targetId": tid, "abilityType": ABILITY, "maxRank": 8}, 90)
                    ev = next((e for e in ((ar.get("units") or [{}])[0].get("evals") or [])
                               if e.get("targetId") == tid), None)
                    ranked = (ev or {}).get("ranked") or []
                    if ranked:
                        cast_ctx = (caster, _by_id(dec, tid), ranked[0])
                        break
                if cast_ctx:
                    break
            adv = rpc("aiPlayByUnit", {"runnerId": rid, "maxTurns": 1, "maxActivations": 1}, 120)
            if not _ok(adv):
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        if cast_ctx is None:
            pytest.skip("aucun tour castable atteint (geometrie/tour)")
        caster, target, atk_tile = cast_ctx
        cid, eid = caster["id"], target["id"]

        # capture PRE-cast (avant move) + niveau/mult du caster
        dec0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob0 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap0 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if snap0 is None or not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("combatSnapshot/boardGraph indispo")
        hp_pre = _hp(_by_id(dec0, eid))
        stp = load_state(dec0, ob0, snap0)
        csc = stp.get_entity(cid).get_component(StatsComponent) if stp.get_entity(cid) else None
        cctx = csc.ctx if csc else None
        lvl = getattr(cctx, "active_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)

        # ============ (A) LIVE cast ============
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cid, "to": {"col": atk_tile["col"], "row": atk_tile["row"]}}}, 90)
        s_cast = rpc("dumpRng", {"runnerId": rid}, 30)          # rng juste avant le cast (post-move)
        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": eid, "abilityType": ABILITY},
            "captureEvents": True}, 120)
        assert _ok(cast), f"cast CordClaw non applique: {str(cast)[:200]}"
        live_dmg = None
        for act in (cast.get("actions") or []):
            for ch in (act.get("changes") or []):
                if ch.get("squadId") == eid and ch.get("hpDelta") is not None:
                    live_dmg = -int(ch["hpDelta"])
        # A2 : la cible a subi les degats de l'attaque principale
        assert live_dmg is not None and live_dmg > 0, f"cible non degatee par le cast (dmg={live_dmg})"

        # A1 : effet 1250 sur le caster au TOUR N+1 (perspective adverse post-cast -> avancer jusqu'au caster)
        eff_n1 = None
        for _ in range(12):
            d1 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            cc = _by_id(d1, cid)
            if cc is None or not cc.get("alive"):
                break
            if d1.get("currentPlayer") == cc.get("owner"):
                eff_n1 = _effids(cc)
                break
            rpc("aiPlayByUnit", {"runnerId": rid, "maxTurns": 1, "maxActivations": 1}, 120)
        assert eff_n1 is not None, "tour N+1 du caster non atteint (caster mort ?)"
        assert EFFECT in eff_n1, f"effet {EFFECT} (CordClaw self-buff) absent au tour N+1 (eff={sorted(eff_n1)})"

        # ============ (B) OFFLINE agreement (port execute_behaviour) ============
        st = load_state(dec0, ob0, snap0)
        st.board = Board(bg["tiles"], adjacency="native_sym")
        st.rng = _seed_rng(s_cast)
        pc = st.get_entity(cid).get_component(PositionComponent)
        pc.col, pc.row = atk_tile["col"], atk_tile["row"]           # DRIVE meme tuile que le live
        res = CordClawAbility().execute_behaviour(st, cid, eid)
        assert res is not None and res.get("dsl") is True, f"behaviour non execute: {res}"
        # B1 : effet 1250 pose sur le CASTER (self-buff, == live)
        assert st.effects.has_effect(cid, effect_type=EFFECT), "effet 1250 NON pose sur le caster par le port"
        # B2 : attaque principale 4 coups (nrOfHits=GetHits(0x2f)=4)
        main = (res or {}).get("main_attack") or {}
        per_hit = main.get("per_hit") or []
        assert len(per_hit) == 4, f"attaque principale {len(per_hit)} coups != 4 (nrOfHits/GetHits)"
        assert (main.get("profile") in (None, "DirectDamage")), f"profil main {main.get('profile')} != DirectDamage"
        # B3 : effet seede (niveau/mult) -> ses vars ne resolvent PAS au niveau 1
        eff_obj = next((e for e in st.effects.by_unit.get(cid, [])
                        if (not e.consumed) and e.effect_type == EFFECT), None)
        assert eff_obj is not None and eff_obj.ability_level is not None, \
            f"effet non seede (ability_level={getattr(eff_obj, 'ability_level', 'NO-EFF')})"
        # B0 (A/B replay-diff : CORRECTION STRUCTURELLE du wiring, isole du bug rng PARTAGE #37) :
        # l'arbre `cord_claw_tree` (feuille AttackWithAttackDamage) DOIT emettre la MEME attaque qu'un appel
        # DIRECT `execute_ability_attack` avec les params DERIVES de la config CordClaw (DirectDamage, nrOfHits
        # =GetHits(0x2f)=4, [minDmg,maxDmg]). Sous le MEME rng seede -> BIT-IDENTIQUE (prouve que la feuille lit
        # la bonne config/profil, sans dependre du live-vs-offline confondu par #37/block).
        st_b = load_state(dec0, ob0, snap0)
        st_b.board = Board(bg["tiles"], adjacency="native_sym")
        st_b.rng = _seed_rng(s_cast)
        st_b.get_entity(cid).get_component(PositionComponent).col = atk_tile["col"]
        st_b.get_entity(cid).get_component(PositionComponent).row = atk_tile["row"]
        bmin, bmax, pierce, dhits = ability_attack_params(st_b, cid, "CordClaw", "DirectDamage", ranged=False)
        assert dhits == 4, f"ability_attack_params nrOfHits {dhits} != 4 (GetHits 0x2f)"
        assert bmin == _mv("minDmg", lvl, mult) and bmax == _mv("maxDmg", lvl, mult), \
            f"bornes config [{bmin},{bmax}] != gameconfig [{_mv('minDmg', lvl, mult)},{_mv('maxDmg', lvl, mult)}]"
        direct = AttackDamageOperation.execute_ability_attack(
            st_b, cid, eid, bmin, bmax, pierce, dhits, damage_profile="DirectDamage", is_melee=True)
        assert per_hit == (direct or {}).get("per_hit"), \
            f"arbre per_hit {per_hit} != sequence directe execute_ability_attack {(direct or {}).get('per_hit')}"
        # B4 : coherence LIVE. Le degat = 4x DirectDamage (pierce 100). Le BIT-EXACT offline-vs-live est CONFONDU
        # par le rng crit/block multi-coups (bug PARTAGE #37 : crit-roll skip cc=0, coups>=2 divergent ~1% ;
        # + block-roll live) -> on confronte la COHERENCE (both = 4 coups DirectDamage plausibles), pas l'egalite.
        pmax = _mv("maxDmg", lvl, mult)
        off_total = main.get("total")
        assert off_total is not None and 0 < off_total <= 4 * pmax + 4, \
            f"total offline {off_total} hors plage 4x DirectDamage [.., {4 * pmax}]"
        assert 0 < live_dmg <= 4 * pmax + 4, f"degat LIVE {live_dmg} hors plage 4x DirectDamage [.., {4 * pmax}]"

        # ============ (C) coups additionnels ============
        oracle = {"count": 2, "min": _mv("minDmg_2", lvl, mult), "max": _mv("maxDmg_2", lvl, mult),
                  "profile": "DirectDamage"}
        grp = eff_obj.additional_hit_groups({"is_melee": True}) or []
        assert grp, "additional_hit_groups vide (effet seede ne resout pas ses coups)"
        g0 = grp[0]
        assert int(g0.get("count")) == oracle["count"], f"count {g0.get('count')} != {oracle['count']}"
        assert int(g0.get("min")) == oracle["min"] and int(g0.get("max")) == oracle["max"], \
            f"[{g0.get('min')},{g0.get('max')}] != oracle [{oracle['min']},{oracle['max']}] (lvl {lvl} x{mult})"
        assert g0.get("profile") == oracle["profile"], f"profil {g0.get('profile')} != {oracle['profile']}"

        # C4 : une attaque NORMALE du caster bufe applique +2 coups DirectDamage (canal #179 dans `execute`).
        # On pose l'effet DIRECTEMENT + attaque une cible FRAICHE pleine-vie (les sous-ops #179 sont gatees
        # hp>0 -- natif fidele : cible morte pendant la phase d'arme -> sous-ops non emises).
        fresh = next((u for u in (dec0.get("units") or [])
                      if u.get("owner") != caster.get("owner") and u.get("alive") and u.get("id") != eid), None)
        fresh_id = (fresh or {}).get("id") or eid

        def _normal(with_buff):
            s2 = load_state(dec0, ob0, snap0)
            s2.board = Board(bg["tiles"], adjacency="native_sym")
            s2.rng = _seed_rng(s_cast)
            if with_buff:
                AddEffectOperation.execute(s2, source=cid, target=cid, effect_type=EFFECT,
                                           name="CordClaw_AdditionHits", duration_override=2)
                _seed_cord_claw_hits_level(s2, cid)
            return AttackDamageOperation.execute(s2, cid, fresh_id)
        ah_no = (_normal(False) or {}).get("additional_hits")
        ah = (_normal(True) or {}).get("additional_hits")
        assert ah_no is None, "attaque normale SANS buff a deja des coups additionnels (contamination)"
        assert ah is not None, "aucune sous-operation #179 sur l'attaque normale du caster bufe"
        assert len(ah.get("per_hit") or []) == 2, f"coups additionnels {len(ah.get('per_hit') or [])} != 2"
        assert (ah.get("profiles") or [None])[0] == "DirectDamage", \
            f"profil coups additionnels {(ah.get('profiles') or [None])[0]} != DirectDamage"
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            state_file.unlink()
        except Exception:
            pass
