#!/usr/bin/env python
"""Probe #128 -- arbitrage Comparable 1197 (ExcruciatingFrequencies) vs attaque normale (69).

MESURE : sur un etat ou le natif CASTE 1197, le moteur offline rend-il la meme action ? Et si non,
QUEL ETAGE de `ComparablePlaybook<T>.CalculateActionUtility` diverge ?

Decomposition par etage imprimee (jamais un total nu) :
  * candidats 1197 : `u` (Sigma CalculateUtilityFromDamageEvent) et `Tile(7)@P` separes ;
  * candidats attaque : `u` (degat) / `Tile(7)@tuile` / `CalculateCustomUtility` separes,
    POUR CHAQUE tuile candidate `ranked` (pas seulement l'argmax) ;
  * `Tile(7)` ventile par FEUILLE (Elevation(8), TileEffects(9), ...) sur les tuiles en litige.

Board `C4_02` (marche d'elevation), caster `emperNoiseMarine`. Ancrage = l'etat de #124 section 7.
Runner dedie, dispose en fin. ASCII only.

Usage :
  python probe_128_tile_elevation_arbitration.py [--board C4_02] [--a-units eldarRanger,astraBullgryn]
         [--hp-target 90000]
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hexgeo  # noqa: E402
import probe_124_line_elevation_decision as P124  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine import weights as W  # noqa: E402
from engine.playbook import scene as _scene  # noqa: E402
from engine.ai import context as _ai_ctx  # noqa: E402
from engine.utilities.tile import TILE_LEAF_IDS, TILE_LEAVES, tile_leaf_ctx, terrain_tile_effects  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _find_step_window(elev, walk):
    """(P, t1, t2, t3) : rayon DROIT de 3 tuiles depuis P franchissant une marche >= 2 entre t1 et t2
    (t2/t3 sur le meme palier). MEME critere que `_find_blind_window` de la probe #124, SANS la
    condition d'aveuglement -- c'est l'etat mesure en #124 section 7 sur C4_02."""
    tiles = {p: e for p, e in elev.items() if walk.get(p) and e is not None}
    for P in sorted(tiles):
        for t1 in P124._move_ring(P, walk, elev):
            ox, _oy, oz = hexgeo.to_cube(*P)
            dx = hexgeo.to_cube(*t1)[0] - ox
            dz = hexgeo.to_cube(*t1)[2] - oz
            t2 = hexgeo.from_cube(ox + dx * 2, oz + dz * 2)
            t3 = hexgeo.from_cube(ox + dx * 3, oz + dz * 3)
            if t2 not in tiles or t3 not in tiles:
                continue
            if abs(tiles[t2] - tiles[t1]) < 2 or abs(tiles[t3] - tiles[t2]) >= 2:
                continue
            return P, t1, t2, t3
    return None


def _tile_breakdown(ctx, wt, pos):
    """Ventilation du composite Tile(7) sur `pos` : (total, meta, [(nom, id, valeur)])."""
    from engine.playbook.base import tile_utility
    lctx = tile_leaf_ctx(ctx)
    meta: dict = {}
    e = ctx.elev_by_pos.get(pos)
    if e is not None:
        elevs = [x for x in ctx.elev_by_pos.values() if x is not None]
        meta = {"elevation": e, "elevation_max": max(elevs), "elevation_min": min(elevs)}
    if pos in ctx.is_temporary_by_pos:
        meta["is_temporary"] = ctx.is_temporary_by_pos[pos]
    effs = list(ctx.effects_by_pos.get(pos) or [])
    effs += terrain_tile_effects((getattr(ctx, "terrain_by_pos", None) or {}).get(pos), effs)
    if effs:
        meta["effects"] = effs
    parts = []
    for i in TILE_LEAF_IDS:
        name, leaf = TILE_LEAVES.get(i, (None, None))
        if leaf is None:
            continue
        v = leaf.evaluate(pos, meta, lctx, wt)
        if v:
            parts.append((name, i, v))
    return tile_utility(ctx, pos), meta, parts


def _dump_attack_stages(ctx, wt):
    """Toutes les tuiles `ranked` de chaque paire (ability, cible) avec u / Tile(7) / custom separes."""
    from engine.playbook import noncomparable as playbooks
    from engine.playbook import get_playbook_or_default
    from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK
    from engine.playbook.base import tile_utility
    plan = ctx.plans.get(ctx.uid) or {}
    rows = []
    for ev in (plan.get("evals") or []):
        if not ev.get("rankCount"):
            continue
        tgt, ab = ev.get("targetId"), ev.get("abilityId")
        if playbooks.is_noncomp(ab):
            continue
        pb = NORMAL_ATTACK_PLAYBOOK if ab in ctx.normal_ids else get_playbook_or_default(ab)
        for rk in (ev.get("ranked") or []):
            tile = (rk.get("col"), rk.get("row"))
            if tile[0] is None:
                continue
            cand = pb.calculate_action_utility(ctx, tile, tgt, ab)
            if cand is None:
                continue
            tl = tile_utility(ctx, tile)
            cu = pb.calculate_custom_utility(ctx, tile, tgt, ab)
            p = cand["pred"] or {}
            rows.append({"ab": ab, "tgt": tgt, "tile": tile, "u": cand["u"], "tile7": tl,
                         "custom": cu, "action": cand["u"] + tl + cu,
                         "engDmg": (p.get("healthDmgMin"), p.get("healthDmgMax")),
                         "natDmg": (rk.get("dmgMin"), rk.get("dmgMax")),
                         "hpBefore": p.get("hpBefore")})
    rows.sort(key=lambda r: -r["action"])
    return rows


def _dump_ef_stages(ctx):
    """Tous les couples (P, aim) de 1197 touchant un ennemi : u / Tile(7)@P / full."""
    import engine.playbook.excruciating_frequencies as EF
    from engine.playbook.base import tile_utility
    me = ctx.me
    ab = next((a for a in ((me or {}).get("abilities") or [])
               if a.get("id") == 1197 and a.get("usable") is not False), None)
    if ab is None or ctx.scene is None:
        return []
    n = EF._n_tiles()
    epos = set(ctx.epos or [])
    enemy_by_pos = {}
    for e in (ctx.enemies or []):
        p = e.get("pos")
        if p and p.get("col") is not None:
            enemy_by_pos[(p["col"], p["row"])] = e.get("id")
    rows = []
    for P in (ctx.reach_nc or []):
        for aim in hexgeo.neighbors(P[0], P[1]):
            aim_id = ctx.tile_id_by_pos.get(aim)
            if aim_id is None:
                continue
            line = EF._line_tiles(P, aim, n, ctx.walkable_by_pos, ctx.elev_by_pos)
            hits = [enemy_by_pos[t] for t in line if t in epos and t in enemy_by_pos]
            if not hits:
                continue
            sc = EF._score(ctx, P, hits)
            if sc is None:
                continue
            u, full = sc
            rows.append({"P": P, "aim": aim, "aimTile": aim_id, "hits": hits, "line": line,
                         "u": u, "tile7": tile_utility(ctx, P), "full": full})
    rows.sort(key=lambda r: -r["full"])
    return rows


def run(sid, board, a_units, hp_target, p_units="emperNoiseMarine"):
    state = ROOT / "logs" / "runners" / f"probe128-{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    rid = P124._build(state, board, p_units, a_units, hp_target)
    if rid is None:
        print("BUILD KO")
        return 1
    print("runner", rid, "board", board, "a_units", a_units, "hp", hp_target)
    try:
        wt = W.load()
        rpc_l = lambda m, b, t: _r(sid, m, b, t)   # noqa: E731
        predictor = _scene.build_predictor(rpc_l, rid)
        elev, walk, tid = P124._board(sid, rid)
        elevs = [e for e in elev.values() if e is not None]
        print(f"board elevations: min={min(elevs)} max={max(elevs)} tiles={len(elev)}")
        win = _find_step_window(elev, walk)
        if win is None:
            print(f"pas de fenetre de marche sur {board}")
            return 1
        P, t1, t2, t3 = win
        print(f"fenetre: P={P}(e{elev[P]}) t1={t1}(e{elev[t1]}) t2={t2}(e{elev[t2]}) t3={t3}(e{elev[t3]})")
        dv, _pos = P124._positions(sid, rid)
        mine = [u for u in (dv.get("units") or []) if u.get("ctrl") and u.get("alive")]
        cid = next((u["id"] for u in mine if u.get("visualId") == "emperNoiseMarine"), None)
        myplayer = next((u.get("owner") for u in mine), None)
        allies = [u["id"] for u in mine if u.get("id") != cid]
        eids = [u["id"] for u in (dv.get("units") or [])
                if u.get("owner") != myplayer and u.get("alive")]
        print("caster", cid, "allies", allies, "ennemis", eids)
        if cid is None or len(eids) < 2:
            print("roster incomplet")
            return 1
        wanted = {cid: P, eids[0]: t2, eids[1]: t3}
        # 1er allie POSE PRES DE L'ACTION (t1) : c'est le temoin SANS 1197 dont le choix de tuile
        # d'attaque normale discrimine directement le terme Elevation. Les autres, parques loin.
        rest = list(allies)
        if rest:
            wanted[rest.pop(0)] = t1
        spares = P124._spare_tiles(walk, elev, [P, t1, t2, t3], len(rest) + len(eids))
        for k, u in enumerate(rest + eids[2:]):
            if k < len(spares):
                wanted[u] = spares[k]
        if not P124._drive_to(sid, rid, walk, elev, wanted):
            _dv, pos = P124._positions(sid, rid)
            print("placement incomplet:", [(u, pos.get(u), d) for u, d in wanted.items()])
            return 1
        P124._give_turn_back(sid, rid, myplayer)
        rc = _measure(sid, rid, cid, wt, predictor, elev, walk, (P, t1, t2, t3), "S1")
        # S1b : les AUTRES unites controlees (sans 1197) -- leur CHOIX DE TUILE d'attaque normale
        # discrimine directement le terme Elevation : a degat NATIF egal, le natif monte-t-il ?
        for other in allies:
            _measure(sid, rid, other, wt, predictor, elev, walk, (P, t1, t2, t3), f"S1b-u{other}")

        # S3 -- MESURE ISOLEE DU TERME Tile(7) : on CONSOMME 1197 (le natif joue son action, la
        # special part en cooldown), on repose l'etat, et il ne reste que l'attaque NORMALE. A
        # degat NATIF egal depuis des tuiles d'elevations DIFFERENTES, la tuile choisie par le
        # natif dit si le terme Elevation entre dans l'utilite d'ACTION (30 vs 20) ou non.
        print("\n===== S3 : 1197 consomme -> arbitrage de TUILE de l'attaque normale seule =====")
        _apply_native_action(sid, rid, cid)
        for _ in range(2):
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        if P124._drive_to(sid, rid, walk, elev, wanted):
            P124._give_turn_back(sid, rid, myplayer)
            _measure(sid, rid, cid, wt, predictor, elev, walk, (P, t1, t2, t3), "S3")
        else:
            _dv, pos = P124._positions(sid, rid)
            print("  placement S3 incomplet:", [(u, pos.get(u), d) for u, d in wanted.items()])
        # S2 : le MEME etat, caster demarre sur la tuile HAUTE (t1, elev max du voisinage) --
        # si le natif descend quand meme pour caster 1197, le terme d'elevation ne pese pas.
        for hi in _high_tiles(elev, walk, P):
            wanted2 = dict(wanted)
            wanted2[cid] = hi
            print(f"\n===== S2 : caster force sur {hi} (e{elev[hi]}) =====")
            if not P124._drive_to(sid, rid, walk, elev, wanted2):
                _dv, pos = P124._positions(sid, rid)
                print("  placement S2 incomplet:", [(u, pos.get(u), d) for u, d in wanted2.items()])
                continue
            P124._give_turn_back(sid, rid, myplayer)
            _measure(sid, rid, cid, wt, predictor, elev, walk, (P, t1, t2, t3), "S2")
            break
        return rc
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        try:
            state.unlink()
        except Exception:
            pass


def _apply_native_action(sid, rid, uid):
    """Joue REELLEMENT l'action proposee par le natif pour `uid` (move + ability + finish) --
    sert a CONSOMMER une special (cooldown) pour isoler l'arbitrage suivant."""
    dry = _r(sid, "aiDryRunAllUnits", {"runnerId": rid}, 150)
    nat = next((u for u in (dry.get("units") or []) if u.get("unitId") == uid), None)
    acts = []
    for m in ((nat or {}).get("proposed") or []):
        if m.get("cls") == "MoveUnitMessage":
            acts.append({"kind": "move", "unitId": m["unitId"],
                         "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
        elif m.get("cls") == "ActiveAbilityMessage":
            acts.append({"kind": "ability", "casterId": m["casterId"],
                         "targetId": m.get("targetId"), "abilityType": m["abilityType"]})
        elif m.get("cls") == "FinishUnitTurnMessage":
            acts.append({"kind": "finish", "unitId": m["unitId"]})
    print("  S3 apply:", acts)
    if acts:
        r = _r(sid, "applyAction", {"runnerId": rid, "actions": acts}, 90)
        print("  S3 apply ok=", r.get("ok"),
              [a.get("mutated") for a in (r.get("actions") or [])])


def _high_tiles(elev, walk, P, k=1):
    """Tuiles walkables d'elevation MAXIMALE atteignables (BFS gate) depuis `P`, les plus hautes
    d'abord -- pour forcer le caster sur un palier ou le terme Elevation est maximal."""
    from collections import deque
    seen, q = {P}, deque([P])
    while q:
        cur = q.popleft()
        for n in P124._move_ring(cur, walk, elev):
            if n not in seen:
                seen.add(n)
                q.append(n)
    ordered = sorted((p for p in seen if elev.get(p) is not None),
                     key=lambda p: (-elev[p], p))
    return ordered[:k]


def _measure(sid, rid, cid, wt, predictor, elev, walk, win, label):
    P, t1, t2, t3 = win
    nat = P124._native(sid, rid, cid)
    eng = P124._engine(sid, rid, cid, wt, predictor)
    print(f"[{label}] NATIF  ab={nat['ability']} tgt={nat['target']} to={nat['to']}")
    print(f"[{label}] MOTEUR ab={eng['ability']} tgt={eng['target']} to={eng['to']} kind={eng['kind']}")
    rpc_l = lambda m, b, t: _r(sid, m, b, t)   # noqa: E731
    if True:
        dvv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
        mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
        _scene.refresh_shields(predictor, rpc_l, rid)
        ctx = _ai_ctx.build(rpc_l, rid, dvv, mbu, cid, wt, predictor)
        print(f"origine caster = {ctx.origin} (e{elev.get(ctx.origin)}) ; "
              f"reach_nc={len(ctx.reach_nc or [])} tuiles")

        print("\n-- candidats 1197 (u = Sigma damage-event ; tile7 = Tile(7)@P) --")
        for r0 in _dump_ef_stages(ctx)[:12]:
            print(f"   P={r0['P']}(e{elev.get(r0['P'])}) aim={r0['aim']} tile={r0['aimTile']} "
                  f"hits={r0['hits']} line={r0['line']} u={r0['u']:.3f} tile7={r0['tile7']:.3f} "
                  f"full={r0['full']:.3f}")

        epos_by_id = {e.get("id"): ((e.get("pos") or {}).get("col"), (e.get("pos") or {}).get("row"))
                      for e in (ctx.enemies or [])}
        print("\n-- ennemis (position/elevation au moment de la mesure) --")
        for eid, ep in sorted(epos_by_id.items()):
            print(f"   u{eid} @ {ep} elev={elev.get(ep)}")

        print("\n-- candidats ATTAQUE (u ; tile7 ; custom ; dElev = |elev(tuile)-elev(cible)|) --")
        rows_atk = _dump_attack_stages(ctx, wt)
        for r0 in rows_atk[:18]:
            de = None
            tp = epos_by_id.get(r0["tgt"])
            if tp is not None and elev.get(tp) is not None and elev.get(r0["tile"]) is not None:
                de = abs(elev[r0["tile"]] - elev[tp])
            print(f"   ab={r0['ab']} tgt={r0['tgt']} tile={r0['tile']}(e{elev.get(r0['tile'])}) "
                  f"dElev={de} u={r0['u']:.3f} tile7={r0['tile7']:.3f} custom={r0['custom']:.3f} "
                  f"action={r0['action']:.3f} nat={r0['natDmg']} eng={r0['engDmg']}")

        # Verdict par ETAGE : que rend l'argmax du port si on RETIRE, une a une, les hypotheses
        # candidates (tuile d'origine, tuiles a dElev >= 2) ? Comparaison directe avec le natif.
        efr = _dump_ef_stages(ctx)
        def _best(rows, ef_rows):
            a = max(rows, key=lambda r: r["action"], default=None)
            b = max(ef_rows, key=lambda r: r["full"], default=None)
            if a is None and b is None:
                return None
            if b is None or (a is not None and a["action"] >= b["full"]):
                return f"ab={a['ab']} tgt={a['tgt']} to={a['tile']} u_act={a['action']:.3f}"
            return f"ab=1197 tile={b['aimTile']} to={b['P']} u_act={b['full']:.3f}"
        no_org = [r0 for r0 in rows_atk if r0["tile"] != ctx.origin]
        no_hi = [r0 for r0 in rows_atk
                 if (epos_by_id.get(r0["tgt"]) is not None
                     and elev.get(r0["tile"]) is not None
                     and elev.get(epos_by_id[r0["tgt"]]) is not None
                     and abs(elev[r0["tile"]] - elev[epos_by_id[r0["tgt"]]]) < 2)]
        print("\n-- argmax du port sous variantes d'ensemble-candidat --")
        print(f"   tel quel                : {_best(rows_atk, efr)}")
        print(f"   sans la tuile d'origine : {_best(no_org, efr)}")
        print(f"   dElev(tuile,cible) < 2  : {_best(no_hi, efr)}")

        mvt = (mbu.get(cid) or {}).get("tiles") or []
        mvp = sorted((t["col"], t["row"]) for t in mvt)
        print(f"\n-- aiMovableTiles u{cid} : {len(mvp)} tuiles ; origine incluse="
              f"{ctx.origin in mvp} --")
        by_e = {}
        for p0 in mvp:
            by_e.setdefault(elev.get(p0), []).append(p0)
        for e0 in sorted(by_e, key=lambda x: (x is None, x)):
            print(f"   elev {e0}: {by_e[e0]}")

        for aid in (69, 1197):
            at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": aid}, 90)
            for u0 in (at.get("units") or []):
                for a0 in (u0.get("abilities") or []):
                    if a0.get("abilityId") != aid:
                        continue
                    fh = [((x.get("tile") or {}).get("col"), (x.get("tile") or {}).get("row"))
                          for x in (a0.get("fromHere") or [])]
                    tg = [(t.get("kind"), t.get("targetId"),
                           (t.get("tile") or {}).get("col"), (t.get("tile") or {}).get("row"))
                          for t in (a0.get("targets") or [])]
                    print(f"\n-- abilityTargets ab={aid} : fromHere={fh}")
                    print(f"   targets={tg[:12]}")

        interest = sorted({P, t1, t2, t3, ctx.origin}
                          | {r0["tile"] for r0 in _dump_attack_stages(ctx, wt)[:4]}
                          | {r0["P"] for r0 in _dump_ef_stages(ctx)[:4]})
        print("\n-- ventilation Tile(7) par FEUILLE --")
        for pos in interest:
            if pos is None:
                continue
            tot, meta, parts = _tile_breakdown(ctx, wt, pos)
            ps = " ".join(f"{n}({i})={v:+.3f}" for n, i, v in parts)
            print(f"   {pos} elev={meta.get('elevation')} total={tot:+.3f} | {ps}")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="C4_02")
    ap.add_argument("--a-units", default="eldarRanger,astraBullgryn")
    ap.add_argument("--p-units", default="emperNoiseMarine")
    ap.add_argument("--hp-target", default="90000")
    a = ap.parse_args()
    sid = _resolve_session()
    print("session", sid)
    return run(sid, a.board, a.a_units, a.hp_target, a.p_units)


if __name__ == "__main__":
    sys.exit(main())
