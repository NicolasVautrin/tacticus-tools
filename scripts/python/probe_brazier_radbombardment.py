"""Probe de MESURE (avant/apres port) des faces COMBAT de BrazierOfHolyFire (1041, adeptCanoness)
et RadBombardment (1116, admecDominus).

OBJET : etablir, AVANT d'ecrire une ligne de port, ce que fait le moteur Python AUJOURD'HUI quand
l'ability est REELLEMENT lancee -- « NO-OP » dans l'audit veut dire « absent du registre COMBAT »,
PAS forcement « inerte » (contre-exemple avere : FrenziedFiring, classe NO-OP alors que ses coups
traversent la formule partagee). On monte donc le cast et on LIT :
  * live  : les evenements de degat (`applyAction captureEvents`) + les effets poses (`decisionView`) ;
  * port  : `AbilityHandler.last` (`ported`) + degat materialise + effets materialises.

Usage (depuis scripts/python, session Frida WARM) :
    python probe_brazier_radbombardment.py --ability brazier   [--target <visualId>] [--board MC1_67]
    python probe_brazier_radbombardment.py --ability radbomb   [--board MC1_67]

Sortie ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from collections import deque
from pathlib import Path

import hexgeo
import rl_collect_batch as R
from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

BRAZIER = 1041
RADBOMB = 1116


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _mk_rpc(sid):
    def _call(method, body=None, timeout=90):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))
    return _call


def _build(caster_vis, a_units, board, seed="777"):
    sf = ROOT / "logs" / "runners" / f"probe-brz-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
         "--board", board, "--roster", "1", "--p-units", caster_vis, "--a-units", a_units],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-500:])
        return None, None
    return int(json.loads(sf.read_text())["runnerId"]), sf


def _find(units, vis):
    return next((u for u in (units or []) if u.get("visualId") == vis and u.get("alive")), None)


def _cr(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _legal_targets(rpc, rid, cid, ability):
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ability}, 90)
    ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
               if a.get("abilityId") == ability), {})
    return ab, [x.get("targetId") for x in (ab.get("fromHere") or ab.get("targets") or [])]


def _approach(rpc, rid, board, caster_vis, target_vis, ability, rng_cfg):
    """Avance jusqu'a mon tour puis rapproche le caster a `rng_cfg` hex de la cible (cast legal)."""
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

    my, moves = None, 0
    for _ in range(25):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        units = dv.get("units") or []
        caster, tgt = _find(units, caster_vis), _find(units, target_vis)
        if caster is None or tgt is None:
            return None
        if my is None:
            my = caster.get("owner")
        if dv.get("currentPlayer") != my:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        cid = caster["id"]
        _ab, legal = _legal_targets(rpc, rid, cid, ability)
        if hexgeo.distance(_cr(caster), _cr(tgt)) <= rng_cfg and tgt["id"] in legal:
            return cid, tgt["id"], my, moves
        dist = bfs(tile_of(tgt))
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == cid), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dist and dist[t] >= 1]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        best = min(pool, key=lambda t: dist[t])
        col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cid, "to": {"col": col, "row": row}}}, 60)
        moves += 1
    return None


def _cast_live(rpc, rid, cid, tid, ability, aim_pos=None):
    action = {"kind": "ability", "casterId": cid, "abilityType": ability}
    if aim_pos is not None:                    # cast TILE-TARGET (RadBombardment) : `to` = l'aim
        action["to"] = {"col": aim_pos[0], "row": aim_pos[1]}
    else:
        action["targetId"] = tid
    res = rpc("applyAction", {"runnerId": rid, "action": action, "captureEvents": True}, 150)
    per_target = {}
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == ability:
                per_target.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
    return per_target, res


def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"])
    r.mti = s["mti"]
    return r


def _aim_positions(rpc, rid, cid, ability):
    """Positions (col,row) LEGALES du cast tile-target, SANS bouger (`fromHere`)."""
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ability}, 90)
    ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
               if a.get("abilityId") == ability), {})
    out = []
    for x in (ab.get("fromHere") or []):
        t = x.get("tile") or {}
        if t.get("col") is not None:
            out.append((t["col"], t["row"]))
    return out


def _aim_tile(rpc, rid, bd, caster_vis, target_vis, ability):
    """RadBombardment est TILE-TARGET (`.ctor` : `TargetingRange.CustomRange(1)`) : la cible du message
    est une TUILE ADJACENTE au caster = l'AIM (la direction de la ligne). On avance jusqu'a mon tour,
    on RAPPROCHE le caster de la cible, puis on choisit l'aim dont la LIGNE (mirror
    `battle_query.get_tiles_behind`) touche le plus d'ennemis."""
    from collections import deque
    from engine import battle_query as bq

    def bfs(src):
        dist = {src: 0}
        q = deque([src])
        while q:
            x = q.popleft()
            for n in bd.neighbours(x):
                if n not in dist and (n == src or bd.walkable(n)):
                    dist[n] = dist[x] + 1
                    q.append(n)
        return dist

    my = None
    for _ in range(25):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        units = dv.get("units") or []
        caster, tgt = _find(units, caster_vis), _find(units, target_vis)
        if caster is None or tgt is None:
            return None
        if my is None:
            my = caster.get("owner")
        if dv.get("currentPlayer") != my:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        cid, cpos, tpos = caster["id"], _cr(caster), _cr(tgt)
        epos = {_cr(u): u["id"] for u in units if u.get("owner") != my and _cr(u)}
        aims = _aim_positions(rpc, rid, cid, ability)
        best, bestn = None, 0
        wa, ea, te = bq.tiles_behind_accessors(None, None)
        for aim in aims:
            line = bq.get_tiles_behind(cpos, aim, max_count=8, check_walkable=False,
                                       update_reference=True, walkable_at=wa, elevation_at=ea,
                                       tile_exists=te)
            n = sum(1 for p in line if p in epos)
            if n > bestn:
                best, bestn = aim, n
        if best is not None:
            print("  caster@%s target@%s aim=%s (ennemis alignes=%d, aims=%d)"
                  % (cpos, tpos, best, bestn, len(aims)))
            return cid, bd.id_at(best[0], best[1]), my, best
        # pas encore d'alignement : approcher
        dist = bfs(bd.id_at(tpos[0], tpos[1]))
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == cid), None)
        reach = {bd.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dist and dist[t] >= 1]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        b = min(pool, key=lambda t: dist[t])
        col, row = reach[b]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cid, "to": {"col": col, "row": row}}}, 60)
    return None


def run(ability, caster_vis, a_units, target_vis, board, rng_cfg, seed):
    sid = R._resolve_session()
    rpc = _mk_rpc(sid)
    rid, sf = _build(caster_vis, a_units, board, seed)
    if rid is None:
        return 1
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        bd = Board(bg["tiles"], adjacency="native_sym")
        if ability == RADBOMB:
            placed = _aim_tile(rpc, rid, bd, caster_vis, target_vis, ability)
        else:
            placed = _approach(rpc, rid, bd, caster_vis, target_vis, ability, rng_cfg)
        if placed is None:
            print("APPROACH KO")
            return 1
        cid, tid, my, moves = placed
        aim = moves if ability == RADBOMB else None      # radbomb : `moves` porte l'aim (col,row)
        print("ability=%d caster=%s tid=%s aim=%s" % (ability, cid, tid, aim))
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        hp_pre = {u["id"]: u.get("hp") for u in (dv.get("units") or [])}
        eff_pre = {u["id"]: [e.get("effectType") for e in (u.get("effects") or [])]
                   for u in (dv.get("units") or [])}

        tm_pre = rpc("tileMeta", {"runnerId": rid}, 60) or {}
        tfx_pre = {(t["col"], t["row"]): sorted(e.get("effectType") for e in (t.get("effects") or []))
                   for t in (tm_pre.get("tiles") or [])}
        live, res = _cast_live(rpc, rid, cid, tid, ability, aim)
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        hp_post = {u["id"]: u.get("hp") for u in (dv2.get("units") or [])}
        eff_post = {u["id"]: [e.get("effectType") for e in (u.get("effects") or [])]
                    for u in (dv2.get("units") or [])}
        print("LIVE per_target hits:", json.dumps(live))
        for uid in sorted(hp_pre):
            d = (hp_pre.get(uid) or 0) - (hp_post.get(uid) or 0)
            if d:
                print("  LIVE hp delta u%s = -%s (hp %s -> %s)"
                      % (uid, d, hp_pre.get(uid), hp_post.get(uid)))
        for uid in sorted(eff_post):
            new = [e for e in eff_post[uid] if e not in (eff_pre.get(uid) or [])]
            if new:
                print("  LIVE effets NOUVEAUX sur u%s : %s" % (uid, new))
        tm_post = rpc("tileMeta", {"runnerId": rid}, 60) or {}
        for t in (tm_post.get("tiles") or []):
            pos = (t["col"], t["row"])
            cur = sorted(e.get("effectType") for e in (t.get("effects") or []))
            new = [e for e in cur if e not in (tfx_pre.get(pos) or [])]
            if new:
                print("  LIVE effets NOUVEAUX sur TUILE %s %s : %s" % (bd.id_at(*pos), pos, new))

        st = load_state(dv, ob, snap, board=bd)
        print("PORT state.effects:", "present" if st.effects is not None else "ABSENT")
        if st.effects is not None:
            _pre_tiles = {t: sorted({int(getattr(f, "effect_type", 0) or 0)
                                     for f in (st.effects.active_effects(t) or [])})
                          for t in list(bd.by_id)}
            _pre_tiles = {t: v for t, v in _pre_tiles.items() if v}
            print("PORT effets de TUILE pre-cast:", json.dumps(_pre_tiles))
        st.rng = _seed_rng(s0)
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=cid, target_id=tid, ability_type=ability))
        last = runner.ability_handler.last or {}
        print("PORT last:", json.dumps({k: v for k, v in last.items()
                                        if k in ("ability_type", "ported", "caster", "target",
                                                 "invalid_target", "actor_dead", "hits", "n_tiles",
                                                 "tiles", "aim", "profile", "range_2")}))
        _atk = last.get("attack") or {}
        if _atk:
            print("PORT attack per_hit:", _atk.get("per_hit"), "total", _atk.get("total"))
        for a in (last.get("attacks") or []):
            print("PORT attack u%s per_hit=%s total=%s"
                  % (a.get("target"), (a.get("attack") or {}).get("per_hit"), a.get("total")))
        for k in ("fire", "marked", "pinned", "contaminated"):
            if last.get(k):
                print("PORT %s: %s" % (k, json.dumps(last[k])))
        print("PORT unported set:", sorted(runner.ability_handler.unported))
        for uid in sorted(hp_pre):
            e = st.get_entity(uid)
            if e is None:
                continue
            from engine.runner.components import HealthComponent
            hc = e.get_component(HealthComponent)
            if hc is None:
                continue
            d = (hp_pre.get(uid) or 0) - hc.hp
            if d:
                print("  PORT hp delta u%s = -%s" % (uid, d))
        if st.effects is not None:
            for uid in sorted(hp_pre):
                fx = st.effects.active_effects(uid) or []
                ids = sorted({int(getattr(f, "effect_type", 0) or 0) for f in fx})
                new = [i for i in ids if i not in (eff_pre.get(uid) or [])]
                if new:
                    print("  PORT effets NOUVEAUX sur u%s : %s" % (uid, new))
            for t in list(bd.by_id):
                fx = st.effects.active_effects(t) or []
                ids = sorted({int(getattr(f, "effect_type", 0) or 0) for f in fx})
                if ids:
                    print("  PORT effets sur TUILE %s %s : %s (sources %s)"
                          % (t, bd.coord(t), ids,
                             sorted({getattr(f, "source", None) for f in fx})))
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ability", choices=("brazier", "radbomb"), required=True)
    ap.add_argument("--target", default=None)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    a = ap.parse_args()
    if a.ability == "brazier":
        tgt = a.target or "necroWarden"
        return run(BRAZIER, "adeptCanoness", tgt + ",necroOverlord", tgt, a.board, 2, a.seed)
    tgt = a.target or "necroWarden"
    return run(RADBOMB, "admecDominus", tgt + ",necroOverlord", tgt, a.board, 1, a.seed)


if __name__ == "__main__":
    sys.exit(main())
