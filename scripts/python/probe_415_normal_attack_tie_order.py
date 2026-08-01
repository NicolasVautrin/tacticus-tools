#!/usr/bin/env python
"""Probe #415 -- QUI tranche le choix de CIBLE de l'attaque normale quand les deux cibles ont la
MEME utilite de paire, et le port est-il d'accord avec le natif ?

CONTEXTE. `tests/engine/test_line_elevation_gate_decision_live.py::test_excruciating_frequencies_...`
echoue sur sa DERNIERE assertion (`decision GATEE != natif`) avec `(69, 79) != (69, 77)` : MEME
ability (attaque normale), CIBLE differente. Les trois assertions qui gardent le gate d'elevation
de #124 passent (`nat != 1197`, `cands_gated == []`, `cands_free` non vide) -- le gate n'est donc
PAS en cause. Ce probe mesure l'etage reellement en desaccord.

CE QU'IL IMPRIME, sur le MEME montage que l'item (b) de #124 (board `C3_59`, fenetre AVEUGLE
derivee du `boardGraph`, ennemis sur t2/t3, `--hp-target 600`) :

  1. l'identite des deux cibles (id, visualId, position, PV) et leur RANG CUBE
     (`engine.battle_query.iterate_surrounding_tiles_order_key` = l'ordre d'enumeration natif de
     `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`, triple
     boucle cube ascendante -> lex (x,y)) ;
  2. la LEGALITE native par (cible, tuile) telle que le port la lit (`ev["ranked"]` des attackPlans) ;
  3. pour CHAQUE tuile d'action et CHAQUE cible : l'utilite d'ACTION du port
     (`ComparableAbilityGenerator._action_utility` = `u_full + CalculateCustomUtility`), donc le
     detail que la trace `ENGINE_DEBUG` resume a un seul gagnant par tuile ;
  4. la decision NATIVE (`aiDryRunAllUnits` -> `CalculateNextActionForUnit`) et celle du port.

Le point de decision est : `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$EvaluateInternal`
compare les cibles en `op_GreaterThan` STRICT dans l'ordre de
`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsEntities` -> la PREMIERE enumeree gagne un
tie. Un desaccord de cible A TUILE EGALE accuse donc soit cet ORDRE, soit la LEGALITE, soit
l'utilite de paire ; un desaccord de TUILE seul accuse l'axe POSITIONNEMENT (proxy a plancher).

ASCII only. Usage : python probe_415_normal_attack_tie_order.py    (exit 0 = mesure faite)
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hexgeo  # noqa: E402
import probe_124_line_elevation_decision as P124  # noqa: E402  (montage NOMME, reutilise tel quel)
from engine import battle_query as bq  # noqa: E402
from engine.utilities import wireweave_net as wwn_mod  # noqa: E402
from engine import weights as W  # noqa: E402
from engine.playbook import scene as _scene  # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK  # noqa: E402
from engine.ai import context as _ai_ctx  # noqa: E402
from engine.ai.action_generators import ComparableAbilityGenerator  # noqa: E402
from rl_collect_batch import _resolve_session  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]


def _build(state, board: str, a_units: str, hp_target: str, extra: list | None = None):
    """`rl_duel build` du montage, avec args SUPPLEMENTAIRES (le bras DESARME en pose un).
    Meme attente du cap MAX_RUNNERS que `probe_124._build` (session partagee)."""
    import json
    import subprocess
    import time
    args = [sys.executable, "rl_duel.py", "build", "--seed", "41171",
            "--state-file", str(state), "--board", board,
            "--p-units", "emperNoiseMarine", "--a-units", a_units,
            "--hp-target", hp_target, "--hp-player", "90000", *(extra or [])]
    waited = 0.0
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(args, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return json.loads(state.read_text())["runnerId"]
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out or waited >= 900:
            print("BUILD KO:", out[-500:])
            return None
        print(f"  cap sature, attente 20s ({waited:.0f}/900)")
        time.sleep(20)
        waited += 20


def run(board: str = P124.BOARD_B, a_units: str = "eldarRanger,astraBullgryn",
        hp_target: str = "600", verbose: bool = True, disarm: bool = False) -> dict:
    """`disarm=True` = bras DESARME de l'A/B : MEME unite, MEMES stats, MEME position, mais le
    passif `WireweaveNet` retire du BC (`--unit-stat "eldarRanger:PassiveAbilities=[]"`, le montage
    anti-bruit de case-366-r1) -> aucune entite-effet 1111, donc terme `WireweaveNet_FirstAttack`
    NUL des deux cotes. Le seul etage qui change entre les deux bras est celui-la."""
    sid = _resolve_session()
    state = ROOT / "logs" / "runners" / f"probe415-{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    extra = ["--unit-stat", "eldarRanger:PassiveAbilities=[]"] if disarm else []
    rid = _build(state, board, a_units, hp_target, extra)
    if rid is None:
        return {"error": "build KO"}
    try:
        r = _measure(sid, rid, board, verbose)
        r["disarm"] = disarm
        return r
    finally:
        P124._r(sid, "disposeRunner", {"runnerId": rid}, 30)
        try:
            state.unlink()
        except Exception:
            pass


def _measure(sid: int, rid: int, board: str, verbose: bool) -> dict:
    rpc = lambda m, b, t=90: P124._r(sid, m, b, t)          # noqa: E731
    elev, walk, _tid = P124._board(sid, rid)
    win = P124._find_blind_window(elev, walk)
    if win is None:
        return {"error": f"board {board} sans fenetre aveugle"}
    P, t1, t2, t3, nseen = win
    dv, _pos = P124._positions(sid, rid)
    mine = [u for u in (dv.get("units") or []) if u.get("ctrl") and u.get("alive")]
    cid = next((u["id"] for u in mine if u.get("visualId") == "emperNoiseMarine"), None)
    myplayer = next((u.get("owner") for u in mine), None)
    allies = [u["id"] for u in mine if u.get("id") != cid]
    eids = [u["id"] for u in (dv.get("units") or [])
            if u.get("owner") != myplayer and u.get("alive")]
    if cid is None or len(eids) < 2:
        return {"error": f"roster incomplet (caster={cid} ennemis={eids})"}
    wanted = {cid: P, eids[0]: t2, eids[1]: t3}
    spares = P124._spare_tiles(walk, elev, [P, t1, t2, t3], len(allies) + len(eids))
    for k, u in enumerate(list(allies) + eids[2:]):
        if k < len(spares):
            wanted[u] = spares[k]
    if not P124._drive_to(sid, rid, walk, elev, wanted):
        _dv, pos = P124._positions(sid, rid)
        return {"error": f"placement incomplet : {[(u, pos.get(u)) for u in wanted]} != {wanted}"}
    P124._give_turn_back(sid, rid, myplayer)

    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)
    nat = P124._native(sid, rid, cid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    ctx = _ai_ctx.build(rpc, rid, dv, mbu, cid, wt, predictor)
    obs = rpc("observeBattle", {"runnerId": rid}, 90)
    hp_by_sq = {u.get("squadId"): (u.get("hp"), u.get("hpMax")) for u in (obs.get("units") or [])}
    u_by_id = {u.get("id"): u for u in (dv.get("units") or [])}

    targets = []
    for eid in eids[:2]:
        u = u_by_id.get(eid) or {}
        pos = (u.get("pos") or {})
        pt = (pos.get("col"), pos.get("row"))
        targets.append({"id": eid, "visualId": u.get("visualId"), "pos": pt,
                        "cube_rank": bq.iterate_surrounding_tiles_order_key(pt),
                        "hp": hp_by_sq.get(eid)})

    # Effets 1111 ARMES portes par chaque cible -- le predicat EXACT de la face DECISION
    # (`GetOwnedEffects(target, state, 0x457).Any(e => e.IsActive)`, cf. `utilities/wireweave_net.py`).
    # Le canal NATIF des effets, en regard de ce que le PORT croit : `decisionView` (actifs seuls,
    # puis `includeInactive`) contre `Scene.effects` / `EffectsState`. Un 1111 present cote port et
    # ABSENT des deux canaux natifs serait un effet FABRIQUE par le seed du port (piege #312).
    dv_eff = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    dv_eff_inc = rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                      "includeInactive": True}, 150)

    def _eff_of(view, uid):
        u = next((x for x in (view.get("units") or []) if x.get("id") == uid), {})
        return [(e.get("effectType"), e.get("active")) for e in (u.get("effects") or [])]

    for t in targets:
        t["wwn_armed"] = wwn_mod.target_has_active_wireweave_net(ctx, t["id"])
        t["wwn_term"] = round(wwn_mod.wireweave_net_first_attack_utility(ctx, P, t["id"]), 4)
        t["dist_from_native_to"] = (None if nat.get("to") is None
                                    else hexgeo.distance(nat["to"], t["pos"]))
        t["dv_effects"] = _eff_of(dv_eff, t["id"])
        t["dv_effects_inactive"] = _eff_of(dv_eff_inc, t["id"])
        sc = getattr(ctx, "scene", None)
        t["scene_effects"] = ([] if sc is None else
                              sorted({e.effect_type for e in sc.effects(int(t["id"]))}))
        t["dv_has_1111"] = any(e[0] == wwn_mod.WIREWEAVE_NET_COUNTER_ATTACK
                               for e in t["dv_effects"])
        t["dv_inactive_has_1111"] = any(e[0] == wwn_mod.WIREWEAVE_NET_COUNTER_ATTACK
                                        for e in t["dv_effects_inactive"])

    plan = ctx.plans.get(cid) or {}
    evals = [ev for ev in (plan.get("evals") or [])
             if ev.get("rankCount") and (ev.get("ranked") or [])]
    legal = {ev.get("targetId"): [(rk.get("col"), rk.get("row")) for rk in (ev.get("ranked") or [])]
             for ev in evals if ev.get("abilityId") in ctx.normal_ids}
    # Portee EFFECTIVE lue de la legalite native : max des distances tuile-legale -> cible.
    reach = {tgt: max((hexgeo.distance(tl, next(t["pos"] for t in targets if t["id"] == tgt))
                       for tl in tiles), default=None)
             for tgt, tiles in legal.items() if any(t["id"] == tgt for t in targets)}
    gen = ComparableAbilityGenerator()

    def _grid_and_best():
        grid, best, best_key = [], None, None
        for tile in (ctx.action_tiles or []):
            if not tile or tile[0] is None:
                continue
            row = {"tile": tile, "cands": []}
            tile_best = None
            for ev in sorted(evals, key=lambda e: bq.iterate_surrounding_tiles_order_key(
                    next((t["pos"] for t in targets if t["id"] == e.get("targetId")), (0, 0)))):
                ab, tgt = ev.get("abilityId"), ev.get("targetId")
                if ab not in ctx.normal_ids:
                    continue
                in_legal = tile in legal.get(tgt, [])
                cand = gen._action_utility(ctx, NORMAL_ATTACK_PLAYBOOK, ab, tgt, tile)
                row["cands"].append({"target": tgt, "legal": in_legal,
                                     "u_action": None if cand is None else round(cand[0], 4),
                                     "u_full": None if cand is None else round(cand[1], 4),
                                     "pair": None if cand is None else round(cand[2], 4)})
                if in_legal and cand is not None and (tile_best is None or cand[0] > tile_best[0]):
                    tile_best = (cand[0], tgt)
            grid.append(row)
            if tile_best is not None and (best_key is None or tile_best[0] > best_key):
                best, best_key = {"target": tile_best[1], "to": tile, "u": round(tile_best[0], 4)}, \
                    tile_best[0]
        return grid, best

    # ORACLE NATIF du terme `pair` (`ComparablePlaybook<T>$$CalculateUtilityFromPredictions`),
    # par (cible, tuile) : c'est le SEUL autre terme cible-dependant de `CalculateActionUtility`
    # (Tile(7) et la tuile-prediction ne dependent que de la TUILE). S'il est EGAL entre les deux
    # cibles, le seul discriminant natif qui reste EST le terme `WireweaveNet_FirstAttack`.
    pair_native = []
    seen_tiles = []
    for tile in [P, nat.get("to"), (2, 6)]:
        if tile is None or tile in seen_tiles:
            continue
        seen_tiles.append(tile)
        for t in targets:
            pu = rpc("pairUtility", {"runnerId": rid, "unitId": cid, "targetId": t["id"],
                                     "abilityType": nat.get("ability"),
                                     "col": tile[0], "row": tile[1]}, 90)
            pair_native.append({"tile": tile, "target": t["id"],
                                "native": (pu or {}).get("utility", pu)})

    grid, best_with = _grid_and_best()
    port = gen.generate(ctx)
    # CONTRE-EPREUVE d'ATTRIBUTION : le MEME moteur, terme `WireweaveNet_FirstAttack` NEUTRALISE.
    # (mutation ciblee du seul etage suspect -- tout le reste de l'etat est identique)
    import engine.playbook.base as _pb
    orig = _pb.wireweave_net_first_attack_utility if hasattr(_pb, "wireweave_net_first_attack_utility") \
        else None
    saved = wwn_mod.wireweave_net_first_attack_utility
    wwn_mod.wireweave_net_first_attack_utility = lambda c, t, u: 0.0
    try:
        grid_off, best_without = _grid_and_best()
        port_without = gen.generate(ctx)
    finally:
        wwn_mod.wireweave_net_first_attack_utility = saved
    del orig, grid_off

    res = {"rid": rid, "board": board, "caster": cid, "P": P, "t1": t1, "t2": t2, "t3": t3,
           "blind": nseen, "targets": targets, "legal": legal, "reach": reach, "grid": grid,
           "pair_native": pair_native,
           "native": nat, "port": port, "best_with_wwn": best_with,
           "best_without_wwn": best_without, "port_without_wwn": port_without}
    if verbose:
        _report(res)
    return res


def _report(r: dict) -> None:
    print(f"runner {r['rid']} board {r['board']} caster {r['caster']}")
    print(f"  P={r['P']} t1={r['t1']} t2={r['t2']} t3={r['t3']} voisinage_aveugle={r['blind']}")
    print("  CIBLES (rang cube = ordre natif d'enumeration, croissant) :")
    for t in r["targets"]:
        print(f"    id={t['id']} vis={t['visualId']} pos={t['pos']} cube_rank={t['cube_rank']} "
              f"hp={t['hp']} filet_1111_arme={t['wwn_armed']} terme_wwn={t['wwn_term']} "
              f"dist(natif_to)={t['dist_from_native_to']}")
        print(f"      canal NATIF : dv_1111={t['dv_has_1111']} "
              f"dv_inactive_1111={t['dv_inactive_has_1111']} dv_effects={t['dv_effects']}")
        print(f"      canal PORT  : scene_effects={t['scene_effects']}")
    print("  LEGALITE native (tuiles `ranked` par cible) + portee effective :")
    for tgt, tiles in r["legal"].items():
        print(f"    cible {tgt} : portee_max={r['reach'].get(tgt)} {sorted(tiles)}")
    print("  GRILLE (tuile -> par cible : u_action / u_full / pair, L=legal) :")
    for row in r["grid"]:
        cs = " | ".join(
            f"t{c['target']}{'L' if c['legal'] else '-'} ua={c['u_action']} uf={c['u_full']} "
            f"p={c['pair']}" for c in row["cands"])
        print(f"    {row['tile']}: {cs}")
    print("  pairUtility NATIF (oracle `CalculateUtilityFromPredictions`) par (tuile, cible) :")
    for e in r["pair_native"]:
        print(f"    tuile {e['tile']} cible {e['target']} -> {e['native']}")
    print(f"  NATIF                        : {r['native']}")
    print(f"  PORT (terme wwn ACTIF)       : {r['port']}")
    print(f"  PORT (terme wwn NEUTRALISE)  : {r['port_without_wwn']}")
    print(f"  best sweep avec wwn    : {r['best_with_wwn']}")
    print(f"  best sweep sans wwn    : {r['best_without_wwn']}")
    same_w = (r["port"] or {}).get("target") == r["native"].get("target")
    same_wo = (r["port_without_wwn"] or {}).get("target") == r["native"].get("target")
    print(f"  ATTRIBUTION : cible_port==cible_natif  avec_wwn={same_w}  sans_wwn={same_wo}")


def main() -> int:
    """A/B d'ATTRIBUTION : bras ARME (filet 1111 actif) contre bras DESARME (meme unite, passif
    retire). Le NATIF est l'oracle : s'il choisit la MEME cible dans les deux bras, le terme
    `WireweaveNet_FirstAttack` ne mord PAS sur cette face ; s'il change, il mord."""
    import os
    only = os.environ.get("BRAS", "")            # "arme" / "desarme" / vide = les deux
    out = {}
    for bras, disarm in (("arme", False), ("desarme", True)):
        if only and only != bras:
            continue
        print(f"===== BRAS {bras.upper()} =====")
        r = run(disarm=disarm)
        if "error" in r:
            print("ERREUR:", r["error"])
            return 1
        out[bras] = r
        print()
    if len(out) == 2:
        na, nd = out["arme"]["native"], out["desarme"]["native"]
        pa, pd = out["arme"]["port"], out["desarme"]["port"]
        print("===== A/B =====")
        print(f"  natif ARME   : ability={na.get('ability')} cible={na.get('target')} "
              f"to={na.get('to')}")
        print(f"  natif DESARME: ability={nd.get('ability')} cible={nd.get('target')} "
              f"to={nd.get('to')}")
        print(f"  port  ARME   : cible={(pa or {}).get('target')} to={(pa or {}).get('to')}")
        print(f"  port  DESARME: cible={(pd or {}).get('target')} to={(pd or {}).get('to')}")
        vis = {t["id"]: t["visualId"] for r in out.values() for t in r["targets"]}
        print(f"  visualId par cible : {vis}")
        print("  VERDICT : le natif " + ("CHANGE" if na.get("target") != nd.get("target")
                                         else "NE CHANGE PAS")
              + " de cible quand le filet disparait -> le terme "
              + ("MORD" if na.get("target") != nd.get("target") else "NE MORD PAS")
              + " sur la face DECISION.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
