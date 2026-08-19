"""probe HeavyGravCannon (EffectType 1291, passif d'admecDestroyer <<Sy-Gex>>) -- deux mesures.

BUT 1 (`--case capture`) : verifier que l'effet 1291 est bien CAPTE live sur le caster
(`decisionView.effects[].name == "HeavyGravCannon"`) et lire le couple qui indexe son `ConfigVar`
(`unitConfig.passiveAbilityLevel` + `abilityVariablesMultiplier`).

BUT 2 (`--case band`) : choisir la CIBLE du 2e montage discriminant. Le canal PERCAGE de l'effet
(`...$$CreatePiercingBonusForAttack` = ForPiercing(cond, ConfigVar(0x3f=extraPierceRatio))) est INERTE
tant que la branche armure domine, car le percage natif est un PLANCHER :
    degat = max(0, d - armure, d * pierce%)
Avec `pierce_eff = PiercingRatio(Physical)=1 + extraPierceRatio`, la branche PERCAGE l'emporte ssi
    d * pierce_eff/100 > d - armure   <=>   d < armure / (1 - pierce_eff/100)
Le probe imprime, pour chaque cible candidate, son `FixedArmor` LIVE et le seuil de roll
correspondant, compare aux bornes config de SentinelDirectives -> on garde la cible dont la bande
couvre TOUT [minDmg, maxDmg] (percage garanti mordant, test non tributaire du tirage).

Discipline runner : state-file UNIQUE en chemin ABSOLU sous logs/, dispose en fin. ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
TAG = "phgc"
CASTER = "admecDestroyer"


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _mkrpc():
    import rl_collect_batch as R
    sid = R._resolve_session()
    _unwrap(R._rpc(sid, "autoBootExtraire", [{}], timeout=180))   # idempotent (no-op si chaud)

    def _call(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))
    return _call


def _build(seed, a_units, extra=None):
    sf = ROOT / "logs" / "runners" / f"{TAG}-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
            "--board", "MC1_67", "--roster", "1", "--p-units", CASTER, "--a-units", a_units,
            *(extra or [])]
    proc = subprocess.run(args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not sf.exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-400:])
        return None, None
    return int(json.loads(sf.read_text())["runnerId"]), sf


def _case_round(rpc, args):
    """ETAGE DE MATERIALISATION du vecteur ABILITY bounds-mode famille ATTACK (`execute_ability_attack`
    avec `is_attack_damage_op=True`) : le port TRONQUE (`op_Explicit` = `raw >> 32`) la sortie Fix64 de
    `apply_all_modifiers`, alors que `IdunBattle.Core.Services.DamageCalculations$$
    CalculateBaseDamageWithModifiers` intercale un `Fix64.Round(·, AwayFromZero)` (etage MULTIPLICATEUR,
    slot 0x10) AVANT. La difference n'est OBSERVABLE que si la valeur est FRACTIONNAIRE -- ce qui
    n'arrive, sur ce vecteur, que quand la branche PERCAGE du plancher gagne (sinon `d + flat - armure`
    est entier). Le montage HeavyGravCannon (cible `adeptMorvenn` armure 2411, pierce_eff 61 %) est
    justement ce regime : ce probe recolte N tirages et confronte, par coup, `live` a `floor(exact)` et
    `round(exact)`. Un ±1 CORRELE a la partie fractionnaire (>= .5 -> +1) tranche « arrondi » ;
    un +1 systematique tranche « additif oublie ». (Residu nomme dans `apply_all_modifiers`.)"""
    import gameconfig as GC
    import engine.services.fix64 as fx
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import set_moved_flag
    from engine.runner.damage_model import defender_fixed_armor, attacker_modifiers, defender_modifiers
    from engine.services.static_battle_rules import get_damage_with_piercing
    from engine.entities.effects.magnitude import ability_var
    import hexgeo
    from collections import deque

    rows = []
    for seed in [s for s in args.seeds.split(",") if s]:
        rid, sf = _build(seed, args.a_units, args.extra.split() if args.extra else None)
        if rid is None:
            continue
        try:
            bg = rpc("boardGraph", {"runnerId": rid}, 60)
            board = Board(bg["tiles"], adjacency="native_sym")
            tgt_vis = args.a_units.split(",")[0]
            rng_cfg = int(((GC.ability("SentinelDirectives") or {}).get("constants") or {}).get("range"))
            my, moves, cid, tid = None, 0, None, None
            for _ in range(25):
                dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
                units = dv.get("units") or []
                cst = next((u for u in units if u.get("visualId") == CASTER and u.get("alive")), None)
                tg = next((u for u in units if u.get("visualId") == tgt_vis and u.get("alive")), None)
                if cst is None or tg is None:
                    break
                if my is None:
                    my = cst.get("owner")
                if dv.get("currentPlayer") != my:
                    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60); continue
                at = rpc("abilityTargets", {"runnerId": rid, "unitId": cst["id"], "abilityType": 1139}, 90)
                ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                           if a.get("abilityId") == 1139), {})
                legal = [x.get("targetId") for x in (ab.get("fromHere") or ab.get("targets") or [])]
                cpos = (cst["pos"]["col"], cst["pos"]["row"])
                tpos = (tg["pos"]["col"], tg["pos"]["row"])
                if hexgeo.distance(cpos, tpos) <= rng_cfg and tg["id"] in legal:
                    cid, tid = cst["id"], tg["id"]; break
                dist = {board.id_at(*tpos): 0}; q = deque([board.id_at(*tpos)])
                while q:
                    x = q.popleft()
                    for n in board.neighbours(x):
                        if n not in dist and board.walkable(n):
                            dist[n] = dist[x] + 1; q.append(n)
                mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
                cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == cst["id"]), None)
                reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                         for t in ((cmt or {}).get("tiles") or [])}
                pool = [t for t in reach if t in dist and dist[t] >= 2]
                if not pool:
                    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60); continue
                best = min(pool, key=lambda t: dist[t]); col, row = reach[best]
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": cst["id"], "to": {"col": col, "row": row}}}, 60)
                moves += 1
            if cid is None:
                print(f"seed {seed}: drive KO"); continue
            dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
            ob = rpc("observeBattle", {"runnerId": rid}, 60)
            snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
            s0 = rpc("dumpRng", {"runnerId": rid}, 30)
            res = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": 1139},
                "captureEvents": True}, 120)
            live, dirty = [], False
            for act in (res.get("actions") or []):
                for e in (act.get("events") or []):
                    td = e.get("tags")
                    td = json.loads(td) if isinstance(td, str) else (td or {})
                    if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == 1139:
                        live.append(td.get("Amount"))
                        dirty = dirty or bool(td.get("Attack_DidCrit")) or bool(td.get("Attack_DidBlock")) \
                            or bool(td.get("Attack_DidEvade"))
            if not live or dirty:
                print(f"seed {seed}: coup non exploitable (live={live} dirty={dirty})"); continue
            # rejeu offline : on remonte le tirage BRUT + la valeur Fix64 EXACTE avant materialisation
            st = load_state(dv, ob, snap, board=board)
            if moves > 0:
                set_moved_flag(st, cid)
            r = IntBasedMersenneTwister(); r.mt = list(s0["mt"]); r.mti = s0["mti"]; st.rng = r
            runner = Runner(st).install_default_handlers(20)
            runner.apply(ActiveAbilityMessage(caster_id=cid, target_id=tid, ability_type=1139))
            atk = (runner.ability_handler.last or {}).get("attack") or {}
            off = atk.get("per_hit") or []
            st2 = load_state(dv, ob, snap, board=board)
            if moves > 0:
                set_moved_flag(st2, cid)
            armor = defender_fixed_armor(st2, tid)
            mods, _a = attacker_modifiers(st2, cid, None, target_id=tid, is_ranged=True,
                                          is_normal_attack=False,
                                          target_traits=__import__("engine.runner.damage_model",
                                                                   fromlist=["x"]).target_trait_names(st2, tid),
                                          trigger_ability_type=1139)
            dmods, _d = defender_modifiers(st2, tid, None, is_melee=False, damage_profile="Physical",
                                           attacker_id=cid, is_normal_attack=False)
            uc = next((su.get("unitConfig") or {} for su in (snap.get("units") or [])
                       if su.get("entityId") == cid), {})
            lvl, mult = uc.get("passiveAbilityLevel") or 0, uc.get("abilityVariablesMultiplier") or 100
            pe = 1 + int(ability_var("HeavyGravCannon", "extraPierceRatio", lvl, multiplier_pct=mult) or 0)
            flat = int(mods.additive or 0)
            # ROLL BRUT reconstruit : replay AVEC l'effet 1291 RETIRE -> pierce_eff retombe a 1 %, la
            # branche ARMURE gagne, la valeur est ENTIERE -> d = value + armure (aucune inference).
            st3 = load_state(dv, ob, snap, board=board)
            if moves > 0:
                set_moved_flag(st3, cid)
            st3.effects.by_unit[int(cid)] = [e for e in st3.effects.by_unit.get(int(cid), [])
                                             if e.name != "HeavyGravCannon"]
            r3 = IntBasedMersenneTwister(); r3.mt = list(s0["mt"]); r3.mti = s0["mti"]; st3.rng = r3
            run3 = Runner(st3).install_default_handlers(20)
            run3.apply(ActiveAbilityMessage(caster_id=cid, target_id=tid, ability_type=1139))
            bare = ((run3.ability_handler.last or {}).get("attack") or {}).get("per_hit") or []
            rows.append((seed, live, off, armor, pe, flat, bare))
            print(f"seed {seed}: live={live} off={off} bare={bare} armor={armor} "
                  f"pierce_eff={pe} flat={flat}")
            for b in bare:
                d = b + armor                                   # branche armure : b = d - armure
                v = get_damage_with_piercing(d + flat, pe, armor)
                exact = v.raw / 2 ** 32
                print(f"   d={d} -> exact={exact:.5f} floor={fx.to_int(v.raw)} "
                      f"round={fx.to_int(fx.round_raw(v.raw, 1))} live={live[0]} "
                      f"frac={exact - int(exact):.3f}")
        finally:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 20)
            except Exception:
                pass
            try:
                sf.unlink()
            except Exception:
                pass
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="capture", choices=("capture", "band", "round"))
    ap.add_argument("--seed", default="777")
    ap.add_argument("--seeds", default="777,31337,4242,12345,2024,999")
    ap.add_argument("--a-units", default="necroOverlord,necroWarden")
    ap.add_argument("--extra", default="", help="args rl_duel build supplementaires (espaces)")
    args = ap.parse_args()

    import gameconfig as GC
    rpc = _mkrpc()
    if args.case == "round":
        return _case_round(rpc, args)
    rid, sf = _build(args.seed, args.a_units, args.extra.split() if args.extra else None)
    if rid is None:
        return 1
    try:
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        units = dv.get("units") or []
        by_id = {u.get("id"): u for u in units}
        cast = next((u for u in units if u.get("visualId") == CASTER), None)
        if args.case == "capture":
            print(f"caster id={cast.get('id')} effects={[e.get('name') for e in (cast.get('effects') or [])]}")
            for e in (cast.get("effects") or []):
                print("  effect", e)
            for su in (snap.get("units") or []):
                if by_id.get(su.get("entityId"), {}).get("visualId") != CASTER:
                    continue
                uc = su.get("unitConfig") or {}
                print("  unitConfig passiveLvl=%s activeLvl=%s mult=%s"
                      % (uc.get("passiveAbilityLevel"), uc.get("activeAbilityLevel"),
                         uc.get("abilityVariablesMultiplier")))
            return 0

        # --case band : armure LIVE (foyer partage `defender_fixed_armor`) + seuil de roll du
        # plancher percage, pour chaque cible candidate.
        from engine.runner.snapshot import load_state
        from engine.runner.damage_model import defender_fixed_armor
        from engine.runner.abilities.base import ability_attack_params
        from engine.entities.effects.magnitude import ability_var
        st = load_state(dv, ob, snap)
        cid = cast.get("id")
        prof = ((GC.ability("SentinelDirectives") or {}).get("constants") or {}).get("damageProfile")
        bmin, bmax, base_pierce, hits = ability_attack_params(st, cid, "SentinelDirectives", prof,
                                                              ranged=True)
        uc = next((su.get("unitConfig") or {} for su in (snap.get("units") or [])
                   if su.get("entityId") == cid), {})
        lvl = uc.get("passiveAbilityLevel") or 0
        mult = uc.get("abilityVariablesMultiplier") or 100
        extra_pierce = ability_var("HeavyGravCannon", "extraPierceRatio", lvl, multiplier_pct=mult) or 0
        extra_dmg = ability_var("HeavyGravCannon", "extraDmg", lvl, multiplier_pct=mult) or 0
        pe = max(0, min(100, base_pierce + int(extra_pierce)))
        print(f"profil={prof} pierce_base={base_pierce} extraPierceRatio[{lvl}]={extra_pierce} "
              f"-> pierce_eff={pe}% | extraDmg[{lvl}]x{mult}%={extra_dmg} | bornes=[{bmin},{bmax}] hits={hits}")
        for u in units:
            vis = u.get("visualId")
            if vis == CASTER or vis is None or not u.get("alive"):
                continue
            armor = defender_fixed_armor(st, u.get("id"))
            from engine.runner.components import HealthComponent
            _e = st.get_entity(u.get("id"))
            _h = _e.get_component(HealthComponent) if _e is not None else None
            traits = (GC.unit(vis) or {}).get("traits") or []
            print(f"    hp={getattr(_h, 'hp', None)}")
            # le flat entre AVANT le percage (attacker_additive_pre) -> le roll effectif est d+extraDmg
            thr = (armor / (1 - pe / 100.0)) if (armor and pe < 100) else None
            lo, hi = bmin + extra_dmg, bmax + extra_dmg
            ok = "ALWAYS" if (thr is not None and thr > hi) else (
                "PARTIEL" if (thr is not None and thr > lo) else "JAMAIS")
            print(f"  {vis:22s} armor={armor} traits={traits} seuil_roll<{thr:.0f} -> percage {ok}"
                  if thr else f"  {vis:22s} armor={armor} traits={traits}")
        return 0
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
