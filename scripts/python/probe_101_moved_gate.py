"""probe #101 -- DECOMPOSITION PAR ETAGE des 2 divergences de degat (harvester / sentinel-directives).

But : mesurer, etage par etage, d'ou vient l'ecart offline-vs-live sur les deux tests LIVE en echec :
  - test_harvester_live (seeds 777/31337) : MAIN offline == 1.25 x LIVE (ratio EXACT sur 2 seeds).
  - test_sentinel_directives_live : live 3510 < offline 3834 (ratio 1.0923, PAS 1.25).

Ce que le probe imprime (ASCII only) :
  * si le caster a BOUGE ce tour (nombre de moves emis par le drive),
  * les mods ATTAQUANT collectes offline (pct_list + details nommes) sous plusieurs hypotheses de
    `has_moved`, et le degat resultant,
  * le roll BRUT tire offline + le degat live, pour discriminer "modificateur en trop" vs
    "rng desaligne" (on rejoue les k premiers tirages du rng seede).

Discipline runner : state-file UNIQUE en chemin ABSOLU, --runner explicite, dispose en fin.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import hexgeo

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
TAG = "p101"


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _mkrpc():
    import rl_collect_batch as R
    sid = R._resolve_session()
    _unwrap(R._rpc(sid, "autoBootExtraire", [{}], timeout=180))

    def _call(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))
    return _call


def _build(seed, p_units, a_units, extra=None):
    sf = ROOT / "logs" / "runners" / f"{TAG}-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
            "--board", "MC1_67", "--p-units", p_units, "--a-units", a_units, *(extra or [])]
    proc = subprocess.run(args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not sf.exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-400:])
        return None, None
    return int(json.loads(sf.read_text())["runnerId"]), sf


def _mk_rng(s):
    from engine.runner.prng import IntBasedMersenneTwister
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


def _find(units, vis):
    return next((u for u in (units or []) if u.get("visualId") == vis and u.get("alive")), None)


def _cr(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _dump_mods(state, cid, tid, is_ranged, has_moved_override, ability_type, damage_profile):
    """Collecte les mods ATTAQUANT en forcant le flag natif `UnitFlag.Moved` du caster."""
    from engine.runner.damage_model import attacker_modifiers
    from engine.runner.components import HealthComponent, UnitFlagsComponent, set_moved_flag
    e = state.get_entity(cid)
    fl = e.get_component(UnitFlagsComponent)
    saved = set(fl.flags) if fl is not None else None
    if has_moved_override is True:
        set_moved_flag(state, cid)
    elif has_moved_override is False and fl is not None:
        fl.remove(UnitFlagsComponent.MOVED)
    ahc = e.get_component(HealthComponent)
    mods, active = attacker_modifiers(state, cid, ahc.hp if ahc else None, target_id=tid,
                                      is_ranged=is_ranged, is_normal_attack=False,
                                      trigger_ability_type=ability_type,
                                      damage_profile=damage_profile)
    fl2 = e.get_component(UnitFlagsComponent)
    if fl2 is not None:
        fl2.flags = set(saved) if saved is not None else set()
    det = [(getattr(d, "kind", "?"), getattr(d, "value", None), getattr(d, "source", None))
           for d in (mods.details or [])]
    return {"pct_list": list(mods.pct_list), "additive": mods.additive,
            "extra_pierce": mods.extra_pierce, "details": det,
            "effects": [getattr(e, "name", None) for e in (active or [])]}


# ----------------------------------------------------------------- case sentinel-directives
CASTER_SD = "admecDestroyer"
TARGET_SD = "necroOverlord"
AB_SD = 1139
RANGE_SD = 3


def _approach_sd(rpc, rid, board):
    """Copie du _approach du test (compte les moves du caster)."""
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
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": AB_SD}, 90)
        ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                   if a.get("abilityId") == AB_SD), {})
        return [x.get("targetId") for x in (ab.get("fromHere") or ab.get("targets") or [])]

    my = None
    moves = 0
    for _ in range(25):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        units = dv.get("units") or []
        caster = _find(units, CASTER_SD); tgt = _find(units, TARGET_SD)
        if caster is None or tgt is None:
            return None
        if my is None:
            my = caster.get("owner")
        if dv.get("currentPlayer") != my:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60); continue
        cid = caster["id"]
        if hexgeo.distance(_cr(caster), _cr(tgt)) <= RANGE_SD and tgt["id"] in legal(cid):
            return cid, tgt["id"], my, moves
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
        moves += 1
    return None


def case_sentdir(rpc, seed):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.abilities.base import ability_attack_params
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.damage_model import defender_fixed_armor

    rid, sf = _build(seed, CASTER_SD, f"{TARGET_SD},necroWarden", extra=["--roster", "1"])
    if rid is None:
        return
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")
        placed = _approach_sd(rpc, rid, board)
        if placed is None:
            print("SKIP: approche KO"); return
        cid, tid, my, moves = placed
        print(f"[SD seed={seed}] caster={cid} target={tid} MOVES_EMIS={moves}")

        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        st = load_state(dv, ob, snap, board=board)
        bmin, bmax, pierce, hits = ability_attack_params(st, cid, "SentinelDirectives", "Physical",
                                                         ranged=True)
        armor = defender_fixed_armor(st, tid)
        print(f"[SD] config [{bmin},{bmax}] pierce={pierce} hits={hits} armor={armor}")
        for hm in (False, True):
            m = _dump_mods(st, cid, tid, True, hm, AB_SD, "Physical")
            print(f"[SD] mods has_moved={hm}: pct={m['pct_list']} add={m['additive']} "
                  f"xp={m['extra_pierce']} det={m['details']}")
        print(f"[SD] effets attaquant actifs: {m['effects']}")
        # RESIDU non porte : HeavyGravCannon (`IdunBattle.Entities.Effects.Loki.HeavyGravCannonEffect$$
        # CreateEffectDamageBonusForAttack` = ForAddition(cond, ConfigVar(8=extraDmg)) + `...$$
        # CreatePiercingBonusForAttack` = ForPiercing(cond, ConfigVar(0x3f=extraPierceRatio)), cond =
        # OwnerIsActor & IsRangedAttack & (HasTrait(target,5=Mechanical)|1013 MkXGravis|1039 TerminatorArmour)).
        # On imprime niveau/multiplier capte + la magnitude que le natif appliquerait -> l'ecart live-off
        # residuel doit s'expliquer par ce FLAT (le +pierce est inerte tant que after_armor > dmg*pierce%).
        from engine.entities.effects.magnitude import ability_var
        for e in (st.effects.active_effects(cid, {}) if st.effects is not None else []):
            if getattr(e, "name", None) != "HeavyGravCannon":
                continue
            lvl = (e.active_ability_level if e.active_ability_level is not None
                   else (e.ability_level if e.ability_level is not None else e.level))
            print(f"[SD] HeavyGravCannon lvl={lvl} (level={e.level} ab={e.ability_level} "
                  f"act={e.active_ability_level}) mult={e.ability_variables_multiplier} "
                  f"extraDmg={ability_var('HeavyGravCannon', 'extraDmg', lvl, multiplier_pct=e.ability_variables_multiplier)} "
                  f"extraPierce={ability_var('HeavyGravCannon', 'extraPierceRatio', lvl)}")

        # LIVE cast
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": AB_SD},
            "captureEvents": True}, 120)
        live = []
        for act in (res.get("actions") or []):
            for e in (act.get("events") or []):
                td = e.get("tags")
                if not td:
                    continue
                td = json.loads(td) if isinstance(td, str) else td
                if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == AB_SD:
                    live.append((td.get("Amount"), td.get("Attack_DidCrit"), td.get("Attack_DidBlock"),
                                 td.get("Attack_DidEvade")))
        s1 = rpc("dumpRng", {"runnerId": rid}, 30)
        print(f"[SD] LIVE per_hit={live}")
        print(f"[SD] rng mti avant={s0.get('mti')} apres={s1.get('mti')}")

        # OFFLINE variantes
        from engine.runner.components import set_moved_flag
        for hm in (False, True):
            st2 = load_state(dv, ob, snap, board=board); st2.rng = _mk_rng(s0)
            if hm:
                set_moved_flag(st2, cid)
            out = AttackDamageOperation.execute_ability_attack(
                st2, cid, tid, bmin, bmax, pierce, hits, damage_profile="Physical",
                is_melee=False, is_attack_damage_op=True)
            print(f"[SD] OFFLINE has_moved={hm}: per_hit={(out or {}).get('per_hit')} "
                  f"rolls={(out or {}).get('rolls')}")
        # rolls bruts candidats du rng (roll-then-reduce : 1 resolve gaspille + 1 tirage/coup)
        r = _mk_rng(s0)
        draws = [r.next_internal(bmin, bmax + 1) for _ in range(6)]
        print(f"[SD] 6 premiers tirages [min,max] = {draws}")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


# ----------------------------------------------------------------- case harvester
CASTER_HV = "eldarMauganRa"
AB_HV = 1067
RANGE_HV = 3


def _drive_moved_hv(rpc, rid, board):
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    me = next((u for u in (dv.get("units") or []) if u.get("visualId") == CASTER_HV and u.get("alive")), None)
    if me is None:
        return None
    myp = me.get("owner"); cid = me["id"]
    ens = [u for u in (dv.get("units") or []) if u.get("owner") != myp and u.get("alive")]
    T = next((t for t in sorted(board.by_id)
              if board.walkable(t) and sum(1 for n in board.neighbours(t) if board.walkable(n)) >= 3), None)
    if T is None or len(ens) < 2:
        return None
    tc = board.coord(T)
    nb = [board.coord(n) for n in board.neighbours(T) if board.walkable(n)]
    tgt, e1 = ens[0], ens[1]
    far = [board.coord(t) for t in sorted(board.by_id)
           if board.walkable(t) and hexgeo.distance(board.coord(t), tc) > 6]

    def mv(uid, c):
        return rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 60)
    for i, e in enumerate(ens[2:]):
        if i < len(far):
            mv(e["id"], far[i])
    mv(tgt["id"], tc)
    for ci, c in enumerate(nb):
        mv(cid, c)
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": AB_HV}, 90)
        a = next((x for x in ((at.get("units") or [{}])[0].get("abilities") or [])
                  if x.get("abilityId") == AB_HV), {})
        if tgt["id"] not in set(x.get("targetId") for x in (a.get("fromHere") or [])):
            continue
        sc = next((s for j, s in enumerate(nb) if j != ci and hexgeo.distance(s, c) <= RANGE_HV), None)
        if sc is None:
            continue
        mv(e1["id"], sc)
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        return dv, cid, tgt["id"], e1["id"]
    return None


def case_harv(rpc, seed):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.abilities.base import ability_attack_params
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.damage_model import defender_fixed_armor

    rid, sf = _build(seed, CASTER_HV, "necroWarden,necroDestroyer,necroOverlord",
                     extra=["--hp-target", "300000"])
    if rid is None:
        return
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")
        drv = _drive_moved_hv(rpc, rid, board)
        if drv is None:
            print("SKIP: drive KO"); return
        dv, cid, tid, sid_splash = drv
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        st = load_state(dv, ob, snap, board=board)
        bmin, bmax, pierce, hits = ability_attack_params(st, cid, "HarvesterOfSouls", "HeavyRound",
                                                         ranged=True)
        armor = defender_fixed_armor(st, tid)
        print(f"[HV seed={seed}] caster={cid} target={tid} config [{bmin},{bmax}] "
              f"pierce={pierce} armor={armor}")
        for hm in (False, True):
            m = _dump_mods(st, cid, tid, True, hm, AB_HV, "HeavyRound")
            print(f"[HV] mods has_moved={hm}: pct={m['pct_list']} add={m['additive']} det={m['details']}")
        print(f"[HV] effets attaquant: {m['effects']}")

        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": AB_HV},
            "captureEvents": True}, 120)
        live = {}
        for a in (cast.get("actions") or []):
            for e in (a.get("events") or []):
                td = e.get("tags")
                if not td:
                    continue
                td = json.loads(td) if isinstance(td, str) else td
                if "Amount" in td and td.get("Active_Ability_Type") == AB_HV:
                    live.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
        print(f"[HV] LIVE main={live.get(tid)} splash={live.get(sid_splash)}")

        from engine.runner.components import set_moved_flag
        for hm in (False, True):
            st2 = load_state(dv, ob, snap, board=board); st2.rng = _mk_rng(s0)
            if hm:
                set_moved_flag(st2, cid)             # le caster LIVE a bouge -> flag natif UnitFlag.Moved
            out = AttackDamageOperation.execute_ability_attack(
                st2, cid, tid, bmin, bmax, pierce, 2, damage_profile="HeavyRound",
                is_melee=False, is_attack_damage_op=True)
            print(f"[HV] OFFLINE moved_set={hm}: per_hit={(out or {}).get('per_hit')}")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True, choices=["sentdir", "harv"])
    ap.add_argument("--seed", default="777")
    a = ap.parse_args()
    rpc = _mkrpc()
    if a.case == "sentdir":
        case_sentdir(rpc, a.seed)
    else:
        case_harv(rpc, a.seed)


if __name__ == "__main__":
    main()
