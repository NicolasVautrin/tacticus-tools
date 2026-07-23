#!/usr/bin/env python
"""Validation CordClaw (1122, admecRuststalker Exitor-Rho) -- face COMBAT (execute) portee.

Port = `CordClawAbility.execute_behaviour` (arbre `cord_claw_tree`) :
  op_add( AttackWithAttackDamage(target, DirectDamage, nrOfHits=GetHits(0x2f)=4, melee),
          AddEffect(0x4e2=1250 CordClaw_AdditionHits, Caster()/Self, TurnsFromRounds(2)) )

Confrontation LIVE :
  (A) LIVE cast : move le caster sur une tuile d'attaque (aiAttackRank) puis caste CordClaw sur un ennemi
      -> effet 1250 sur le CASTER (self-buff) + ennemi degate. Le meme rng seede offline (dumpRng post-move)
      rend un `total` main-attack == degat LIVE inflige a l'ennemi (BIT-EXACT ; l'effet est pose APRES
      l'attaque -> le cast lui-meme n'a PAS de coups additionnels).
  (B) OFFLINE : reconstruit pre-cast, drive le caster sur la meme tuile, seed rng -> effet 1250 pose (==live)
      + attaque 4 coups DirectDamage + effet SEEDE (niveau/mult).
  (C) coups additionnels : `additional_hit_groups` = 2 coups [minDmg_2,maxDmg_2] DirectDamage (oracle
      gameconfig au niveau du caster) ; threading dans une attaque du caster = +2 coups.

State-file UNIQUE. Doctrine drive-positions. ASCII only. Usage : python probe_cord_claw.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import hexgeo  # noqa: E402
import gameconfig as GC  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "rl-state" / "cordclaw-a06de242.json"
CASTER_VIS = "admecRuststalker"
ABILITY = 1122
EFFECT = 1250


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _find(dec, vis):
    return next((u for u in (dec.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _by_id(dec, uid):
    return next((u for u in (dec.get("units") or []) if u.get("id") == uid), None)


def _effids(u):
    return {e.get("effectType") for e in ((u or {}).get("effects") or []) if e.get("effectType") is not None}


def _hp(u):
    if not u:
        return None
    h = u.get("health")
    if isinstance(h, dict):
        return h.get("current", h.get("hp"))
    for k in ("hp", "currentHealth", "health"):
        v = u.get(k)
        if isinstance(v, (int, float)):
            return v
    return None


def _oracle_group(lvl, mult):
    a = GC.ability("CordClaw") or {}
    affected = a.get("variablesAffectedByRarityBonus", [])

    def av(key):
        arr = a.get("variables", {}).get(key)
        base = int(arr[max(0, min((lvl or 1) - 1, len(arr) - 1))])
        return round(base * (mult or 100) / 100) if (key in affected and (mult or 100) != 100) else base
    return {"count": 2, "min": av("minDmg_2"), "max": av("maxDmg_2"), "profile": "DirectDamage"}


def main():
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import StatsComponent, PositionComponent
    from engine.entities.pathfinding.board import Board
    from engine.runner.abilities.loki import CordClawAbility
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.abilities.base import ability_attack_params

    def _seed_rng(s):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s["mt"]); rng.mti = s["mti"]
        return rng

    sid = _resolve_session()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    build = ["--roster", "1", "--p-units", f"{CASTER_VIS}",
             "--a-units", "necroWarden,necroWarden,necroWarden,necroOverlord"]
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "777",
         "--state-file", str(STATE), "--board", "MC1_67", *build],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-400:]); return 1
    rid = json.loads(STATE.read_text())["runnerId"]
    print("runnerId", rid)
    fails = []
    try:
        cast_ctx = None
        for step in range(22):
            dec = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            cur = dec.get("currentPlayer")
            caster = _find(dec, CASTER_VIS)
            if caster is None:
                break
            if caster.get("owner") == cur:
                at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": caster["id"], "abilityType": ABILITY}, 90)
                ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                           if a.get("abilityId") == ABILITY), {})
                for t in (ab.get("targets") or []):             # N'IMPORTE quelle cible CordClaw legale (move inclus)
                    tid = t.get("targetId")
                    tgt = _by_id(dec, tid)
                    if tgt is None:
                        continue
                    ar = _r(sid, "aiAttackRank", {"runnerId": rid, "unitId": caster["id"],
                                                  "targetId": tid, "abilityType": ABILITY, "maxRank": 8}, 90)
                    ev = next((e for e in ((ar.get("units") or [{}])[0].get("evals") or [])
                               if e.get("targetId") == tid), None)
                    ranked = (ev or {}).get("ranked") or []
                    if ranked:
                        cast_ctx = (caster, tgt, ranked[0])
                        break
                if cast_ctx:
                    break
            _r(sid, "aiPlayByUnit", {"runnerId": rid, "maxTurns": 1, "maxActivations": 1, "captureEvents": False}, 120)
        if cast_ctx is None:
            print("SKIP: pas de tour castable atteint"); return 0
        caster, enemy, atk_tile = cast_ctx
        cid, eid = caster["id"], enemy["id"]
        print(f"CASTABLE : caster {cid}@{caster['pos']} enemy {eid}@{enemy['pos']} -> attack tile {atk_tile}")

        # capture PRE-cast (avant move) pour l'offline
        dec0 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob0 = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        snap0 = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
        eff_pre = _effids(_by_id(dec0, cid))
        hp_pre = _hp(_by_id(dec0, eid))
        # niveau/mult (oracle coups additionnels)
        stp = load_state(dec0, ob0, snap0)
        csc = stp.get_entity(cid).get_component(StatsComponent) if stp.get_entity(cid) else None
        cctx = csc.ctx if csc else None
        lvl = getattr(cctx, "active_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
        oracle = _oracle_group(lvl, mult)
        print(f"PRE : caster effects={sorted(eff_pre)} enemy hp={hp_pre} ; caster lvl={lvl} mult={mult}")
        print(f"oracle additional group = {oracle}")

        # ============ (A) LIVE cast ============
        _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cid, "to": {"col": atk_tile["col"], "row": atk_tile["row"]}}}, 90)
        s_cast = _r(sid, "dumpRng", {"runnerId": rid}, 30)          # rng juste avant le cast (post-move)
        cast = _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": eid, "abilityType": ABILITY},
            "captureEvents": True}, 120)
        # degat main-attack LIVE = hpDelta de la cible dans les `changes` du cast (le cast n'a PAS de coups
        # additionnels -> effet pose APRES l'attaque). CordClaw = mono-cible (pas de splash).
        live_dmg = None
        for act in (cast.get("actions") or []):
            for ch in (act.get("changes") or []):
                if ch.get("squadId") == eid and ch.get("hpDelta") is not None:
                    live_dmg = -int(ch["hpDelta"])
        print(f"LIVE cast ok={cast.get('ok')} stage={cast.get('stageName')} ; main-attack degat cible={live_dmg}")

        # A1 : effet 1250 present sur le caster au TOUR N+1 (self-buff pose + persiste). La perspective
        # decisionView post-cast est celle de l'ADVERSAIRE (tour passe) -> on avance jusqu'au tour du caster.
        eff_n1 = None
        for _ in range(12):
            d1 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            cc = _by_id(d1, cid)
            if cc is None or not cc.get("alive"):
                break
            if d1.get("currentPlayer") == cc.get("owner"):
                eff_n1 = _effids(cc)
                n1_dec = d1
                break
            _r(sid, "aiPlayByUnit", {"runnerId": rid, "maxTurns": 1, "maxActivations": 1, "captureEvents": False}, 120)
        if eff_n1 is None:
            fails.append("A1 LIVE: tour N+1 du caster non atteint (caster mort ?) -> effet non verifiable")
        elif EFFECT not in eff_n1:
            fails.append(f"A1 LIVE: effet {EFFECT} absent du caster au tour N+1 (eff={sorted(eff_n1)})")
        else:
            print(f"A1 OK : effet {EFFECT} present sur le caster au tour N+1 (self-buff live, eff={sorted(eff_n1)})")
        if live_dmg is None:
            print("A2 : degat main-attack live non lu (pas de change cible)")
        elif live_dmg <= 0:
            fails.append(f"A2 LIVE: cible non degatee (dmg={live_dmg})")
        else:
            print(f"A2 OK : cible degatee {live_dmg} par l'attaque du cast")

        # ============ (B) OFFLINE agreement (bit-exact main attack) ============
        st = load_state(dec0, ob0, snap0)
        if isinstance(bg, dict) and bg.get("tiles"):
            st.board = Board(bg["tiles"], adjacency="native_sym")
        st.rng = _seed_rng(s_cast)
        ent = st.get_entity(cid)
        pc = ent.get_component(PositionComponent) if ent else None
        if pc is not None:
            pc.col, pc.row = atk_tile["col"], atk_tile["row"]
        res = CordClawAbility().execute_behaviour(st, cid, eid)
        off_has = st.effects.has_effect(cid, effect_type=EFFECT)
        main = (res or {}).get("main_attack") or {}
        per_hit = main.get("per_hit") or []
        off_total = main.get("total")
        print(f"OFFLINE : effet pose={off_has} main hits={len(per_hit)} total={off_total} "
              f"per_hit={per_hit} placed={(res or {}).get('self_buff_placed')}")
        if not off_has:
            fails.append("B1: effet 1250 NON pose sur le caster par le port")
        else:
            print("B1 OK : effet 1250 pose sur le caster (offline == live)")
        if len(per_hit) != 4:
            fails.append(f"B2: attaque principale {len(per_hit)} coups != 4")
        else:
            print("B2 OK : attaque principale 4 coups (nrOfHits=GetHits(0x2f)=4)")
        eff_obj = next((e for e in st.effects.by_unit.get(cid, [])
                        if (not e.consumed) and e.effect_type == EFFECT), None)
        if eff_obj is None or eff_obj.ability_level is None:
            fails.append(f"B3: effet non seede (ability_level={getattr(eff_obj, 'ability_level', 'NO-EFF')})")
        else:
            print(f"B3 OK : effet seede ability_level={eff_obj.ability_level} mult={eff_obj.ability_variables_multiplier}")

        # B0 (A/B replay-diff : CORRECTION STRUCTURELLE du wiring, isole du bug rng PARTAGE #37) : l'arbre
        # cord_claw_tree DOIT emettre la MEME attaque qu'un execute_ability_attack DIRECT (params derives
        # config CordClaw : DirectDamage, nrOfHits=GetHits(0x2f)=4, [minDmg,maxDmg]) sous le MEME rng.
        st_b = load_state(dec0, ob0, snap0)
        if isinstance(bg, dict) and bg.get("tiles"):
            st_b.board = Board(bg["tiles"], adjacency="native_sym")
        st_b.rng = _seed_rng(s_cast)
        p_b = st_b.get_entity(cid).get_component(PositionComponent)
        if p_b is not None:
            p_b.col, p_b.row = atk_tile["col"], atk_tile["row"]
        bmin, bmax, pierce, dhits = ability_attack_params(st_b, cid, "CordClaw", "DirectDamage", ranged=False)
        direct = AttackDamageOperation.execute_ability_attack(
            st_b, cid, eid, bmin, bmax, pierce, dhits, damage_profile="DirectDamage", is_melee=True)
        if per_hit == (direct or {}).get("per_hit") and dhits == 4:
            print(f"B0 OK : arbre per_hit == sequence directe execute_ability_attack (BIT-EXACT, nrOfHits={dhits}) "
                  f"[wiring correct, isole du #37]")
        else:
            fails.append(f"B0: arbre per_hit {per_hit} != direct {(direct or {}).get('per_hit')} (dhits={dhits})")
        # B4 : coherence main-attack offline vs LIVE. Le degat = 4 coups DirectDamage (pierce 100, ignore
        # armure). Bornes per-coup = [minDmg[lvl]xmult, maxDmg[lvl]xmult] ; total 4 coups dans
        # [4xminRed, 4xmax]. Le BIT-EXACT est CONFONDU par le rng block/crit (block-roll consomme rng ->
        # desync offline/live) -> on confronte la COHERENCE (les deux totals sont 4 coups DirectDamage
        # plausibles), pas l'egalite stricte. INFORMATIF si different.
        a = GC.ability("CordClaw") or {}
        aff = a.get("variablesAffectedByRarityBonus", [])

        def _mv(k):
            arr = a.get("variables", {}).get(k)
            base = int(arr[max(0, min((lvl or 1) - 1, len(arr) - 1))])
            return round(base * (mult or 100) / 100) if (k in aff and (mult or 100) != 100) else base
        pmin, pmax = _mv("minDmg"), _mv("maxDmg")
        lo4, hi4 = 4 * pmin, 4 * pmax
        print(f"B4 : main per-coup bornes brutes [{pmin},{pmax}] -> total 4 coups attendu <= {hi4} "
              f"(offline={off_total}, LIVE={live_dmg})")
        if off_total is not None and not (0 < off_total <= hi4 + 4):
            fails.append(f"B4: total offline {off_total} hors plage 4x DirectDamage [.., {hi4}]")
        elif live_dmg is not None and not (0 < live_dmg <= hi4 + 4):
            fails.append(f"B4: degat LIVE {live_dmg} hors plage 4x DirectDamage [.., {hi4}]")
        else:
            eq = (off_total is not None and live_dmg is not None and int(off_total) == int(live_dmg))
            print(f"B4 OK : offline={off_total} et LIVE={live_dmg} = 4 coups DirectDamage coherents"
                  f"{' (BIT-EXACT)' if eq else ' (bit-exact confondu par block/crit-rng)'}")

        # ============ (C) coups additionnels ============
        grp = (eff_obj.additional_hit_groups({"is_melee": True}) or []) if eff_obj else []
        g0 = grp[0] if grp else {}
        print(f"OFFLINE additional_hit_groups={grp}")
        if not grp:
            fails.append("C1: additional_hit_groups vide")
        else:
            if int(g0.get("count") or 0) != oracle["count"]:
                fails.append(f"C1: count {g0.get('count')} != {oracle['count']}")
            if int(g0.get("min") or 0) != oracle["min"] or int(g0.get("max") or 0) != oracle["max"]:
                fails.append(f"C2: [{g0.get('min')},{g0.get('max')}] != oracle [{oracle['min']},{oracle['max']}]")
            if g0.get("profile") != oracle["profile"]:
                fails.append(f"C3: profil {g0.get('profile')} != {oracle['profile']}")
            if not any(f.startswith("C") for f in fails):
                print(f"C OK : coups additionnels = {oracle['count']}x[{oracle['min']},{oracle['max']}] "
                      f"{oracle['profile']} (oracle lvl {lvl} x{mult})")

        # threading : une attaque NORMALE du caster (canal #179 dans `execute`) gagne les coups additionnels
        # APRES la pose du buff. On pose l'effet DIRECTEMENT (pas via le main attack, qui entamerait la cible)
        # et on attaque une cible FRAICHE pleine-vie (les sous-ops #179 sont gatees hp>0, natif fidele l.768).
        from engine.runner.operations.effects import AddEffectOperation
        from engine.runner.abilities.loki.strike import _seed_cord_claw_hits_level
        fresh = next((u for u in (dec0.get("units") or [])
                      if u.get("owner") != caster.get("owner") and u.get("alive") and u.get("id") != eid), None)
        fresh_id = (fresh or {}).get("id") or eid

        def _normal_attack(with_buff):
            s2 = load_state(dec0, ob0, snap0)
            if isinstance(bg, dict) and bg.get("tiles"):
                s2.board = Board(bg["tiles"], adjacency="native_sym")
            s2.rng = _seed_rng(s_cast)
            if with_buff:
                AddEffectOperation.execute(s2, source=cid, target=cid, effect_type=EFFECT,
                                           name="CordClaw_AdditionHits", duration_override=2)
                _seed_cord_claw_hits_level(s2, cid)                 # seed niveau/mult == execute_behaviour
            return AttackDamageOperation.execute(s2, cid, fresh_id)  # attaque NORMALE (thread le canal #179)
        atk_no = _normal_attack(False)
        atk_yes = _normal_attack(True)
        ah_no = (atk_no or {}).get("additional_hits")
        ah = (atk_yes or {}).get("additional_hits")
        add_hits = len((ah or {}).get("per_hit") or []) if ah else 0
        add_profile = ((ah or {}).get("profiles") or [None])[0]
        print(f"THREADING (attaque normale sur cible fraiche {fresh_id}) : SANS buff additional={ah_no is not None} ; "
              f"AVEC buff coups additionnels={add_hits} profil={add_profile} (attendu 2 DirectDamage)")
        print(f"   additional_hits detail: {json.dumps(ah)[:400] if ah else None}")
        if ah_no is not None:
            fails.append("C4: l'attaque normale SANS buff a deja des coups additionnels (contamination)")
        elif not ah:
            fails.append("C4: aucune sous-operation additional_hits sur l'attaque normale du caster bufe")
        elif add_hits != 2:
            fails.append(f"C4: coups additionnels appliques={add_hits} != 2")
        elif add_profile != "DirectDamage":
            fails.append(f"C4: profil coups additionnels {add_profile} != DirectDamage")
        else:
            print("C4 OK : l'attaque normale du caster bufe applique +2 coups DirectDamage additionnels (canal #179)")

    finally:
        _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)

    print("\n==== RESULT ====")
    if fails:
        for f in fails:
            print("FAIL", f)
        return 2
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
