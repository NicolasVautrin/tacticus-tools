#!/usr/bin/env python
"""rl_probe_step — valide le pilotage per-unité de l'IA sur UN runner isolé.

Monte UNE battle via le pipeline PROUVÉ (réutilise les helpers de
rl_collect_batch : normalize → sample roster → patch → initAndStart), puis
appelle le RPC `aiStepDryRun` (1 MoveNext de CalculateNextActionForPlayer, sans
appliquer) pour confirmer que :
  - le pilotage manuel de l'énumérateur marche sur le runner isolé ;
  - 1 MoveNext = l'action d'1 unité (unité choisie par l'IA + tile cible) ;
  - le dry-run ne mute pas le runner.

Lancer avec `python` (pas `py`) — l'import de rl_collect_batch touche psycopg3.

Usage:
    python scripts/python/rl_probe_step.py [--rank 17] [--roster 5] [--seed 777]
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import (  # noqa: E402
    _resolve_session, _ensure_ai_trace, _load_seed_bc, _load_unspawnable,
    _normalize_and_extract_pool, _spawn_points_by_twpi,
    _patch_predefined_units, _patch_predefined_machines, _rpc,
    PLAYER_ID_HUMAN,
)


def _fmt_action(msgs: list) -> str:
    if not msgs:
        return "none"
    parts = []
    for m in msgs:
        c = m.get("cls", "")
        if c == "MoveUnitMessage":
            t = m.get("to") or {}
            parts.append(f"Move({t.get('col')},{t.get('row')})")
        elif c == "ActiveAbilityMessage":
            parts.append(f"Ability {m.get('abilityType')}->{m.get('targetId')}")
        else:
            parts.append(c)
    return ", ".join(parts)


def _print_apply(label: str, res: dict, my_ids=None, raw: bool = False) -> str | None:
    """Affiche le résultat d'un applyAction : diff d'état (a) + cascade
    StreamDispatcher décodée (c) + flag overwatch. my_ids = mes squadId (pour
    distinguer dégât SUBI / infligé). raw=True → dump brut des events.

    Rend la raison d'un ÉCHEC DE DÉCODAGE de la cascade (déjà imprimée), sinon None.

    ⚠ CETTE FONCTION NE DOIT JAMAIS PROPAGER — `applyAction` a DÉJÀ muté le runner quand
    on arrive ici. Une exception de décodage remontait jusqu'à `cmd_act`, court-circuitant
    l'append `action_log` + `_save_state` : l'appelant lisait « erreur » sur une action
    APPLIQUÉE, la rejouait, et la jouait deux fois. Mesuré le 2026-07-30 (#254b-a) : un
    worktree frais levait `KeyError: StepType.UnitDamaged` ICI, après le RPC. Le décodage
    est de l'AFFICHAGE ; il rend compte de sa propre panne, il n'annule pas l'action."""
    import stream_events  # noqa: E402
    if not res.get("ok") and not res.get("actions"):
        print(f"  [{label}] ÉCHEC: {res.get('error')}")
        return None
    echec: str | None = None
    for act in (res.get("actions") or []):
        print(f"  [{label}] kind={act.get('kind')} ok={act.get('ok')} "
              f"mutated={act.get('mutated')} stage={act.get('stage')} "
              f"player={act.get('currentPlayer')}"
              + (f" ERR={act.get('error')}" if act.get('error') else ""))
        for ch in (act.get("changes") or []):
            sid_ = ch.get("squadId")
            if ch.get("killed"):
                print(f"        u{sid_} TUÉ (hp {ch.get('hpBefore')}→0)")
            elif ch.get("moved"):
                fr = ch.get("from") or {}
                to = ch.get("to") or {}
                extra = (f" · hp {ch.get('hpBefore')}→{ch.get('hpAfter')}"
                         if ch.get("hpDelta") else "")
                print(f"        u{sid_} déplacé "
                      f"({fr.get('col')},{fr.get('row')})→"
                      f"({to.get('col')},{to.get('row')}){extra}")
            elif ch.get("hpDelta"):
                print(f"        u{sid_} hp {ch.get('hpBefore')}→"
                      f"{ch.get('hpAfter')} ({ch.get('hpDelta'):+d})")
            elif ch.get("appeared"):
                print(f"        u{sid_} apparu")
        evs = act.get("events") or []
        if not evs:
            continue
        # Résumé (c) UNIFORME : dégâts SUBIS / INFLIGÉS / morts. L'overwatch
        # n'est PAS un cas spécial — c'est un dégât subi labellisé [overwatch]
        # (comme [dot]), au même titre que counter/aura.
        try:
            an = stream_events.analyze(evs, my_ids)
        except Exception as e:                     # decodage seul -> jamais fatal
            echec = "%s: %s" % (type(e).__name__, e)
            print("        /!\\ CASCADE NON DECODEE (%d events) -- %s" % (len(evs), echec))
            print("        /!\\ L'ACTION A DEJA ETE APPLIQUEE cote runner : l'etat A BOUGE.")
            print("        /!\\ NE PAS LA REJOUER -- corriger le decodage, puis relire l'etat"
                  " par `rl_duel.py view`.")
            continue
        for d in an["received"]:
            crit = " CRIT" if d["crit"] else ""
            kill = " → TUÉ" if d["killed"] else ""
            eff = f" [{d['effect']}]" if d.get("effect") else ""
            print(f"        SUBI : u{d['attacker']}→u{d['target']} "
                  f"{d['amount']}{crit}{eff}{kill}")
        for d in an["dealt"]:
            crit = " CRIT" if d["crit"] else ""
            kill = " → TUÉ" if d["killed"] else ""
            eff = f" [{d['effect']}]" if d.get("effect") else ""
            print(f"        INFLIGÉ : u{d['attacker']}→u{d['target']} "
                  f"{d['amount']}{crit}{eff}{kill} (ability {d['ability']})")
        # Cascade décodée (lisible) ou brut.
        print(f"        cascade ({act.get('eventCount')} events) :")
        if raw:
            for ev in evs[:60]:
                print(f"          {ev}")
        else:
            for ln in stream_events.decode_lines(evs):
                print("          " + ln)
    return echec


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rank", type=int, default=17)
    ap.add_argument("--roster", type=int, default=5)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--maxpump", type=int, default=2000)
    ap.add_argument("--maxact", type=int, default=6)
    ap.add_argument("--maxturns", type=int, default=2)
    ap.add_argument("--mode",
                    choices=["play", "ordered", "dryall", "full", "deepstrike",
                             "tiles", "danger", "buff", "buffcond", "rank", "view",
                             "predict", "card", "apply", "owatch"],
                    default="play")
    ap.add_argument("--ability", type=int, default=None)  # forcer une ability (sinon auto-découverte)
    ap.add_argument("--target", type=int, default=None)  # squadId ennemi ciblé (None=tous)
    ap.add_argument("--unit", type=int, default=None)    # squadId joueur (None=tous)
    ap.add_argument("--maxrank", type=int, default=8)    # tiles rankées max / (unit,target)
    ap.add_argument("--advance", type=int, default=0)    # joue N tours avant de rank (rapprocher les camps)
    ap.add_argument("--override", type=int, default=None)  # OverrideRange move (diag: portée géante)
    ap.add_argument("--allabilities", action="store_true")  # rank aussi les spéciales
    ap.add_argument("--tilecol", type=int, default=None)  # tile attaquante (predict)
    ap.add_argument("--tilerow", type=int, default=None)
    ap.add_argument("--moveonly", action="store_true")  # apply: move seul (test overwatch)
    ap.add_argument("--buff", type=int, default=3)  # +N move bonus
    ap.add_argument("--order", default="desc")  # asc | desc
    ap.add_argument("--deepstrike", default="worldTerminator")
    ap.add_argument("--dssrc", type=int, default=4)  # SpawnSource (Drafting=4)
    ap.add_argument("--chunk", type=int, default=2)   # tours/appel (anti-freeze)
    ap.add_argument("--fullchunks", type=int, default=40)
    a = ap.parse_args(argv)

    sid = _resolve_session()
    print(f"[ok] sid={sid}")
    _ensure_ai_trace(sid)

    seed_bc = _load_seed_bc()
    template_bc, pool, pool_mow = _normalize_and_extract_pool(
        sid, seed_bc, a.rank)
    bad_u, _bad_m = _load_unspawnable(a.rank)
    pool = [u for u in pool if u not in bad_u]
    print(f"[ok] normalized rank {a.rank} — pool {len(pool)} regular units")
    if len(pool) < a.roster:
        print(f"[error] pool too small ({len(pool)} < {a.roster})",
              file=sys.stderr)
        return 2

    rng = random.Random(a.seed)
    p_units = rng.sample(pool, a.roster)
    a_units = rng.sample(pool, a.roster)
    print(f"[ok] roster player={p_units}")
    print(f"[ok] roster ai    ={a_units}")

    bc = copy.deepcopy(template_bc)
    _patch_predefined_units(bc, a_units)
    _patch_predefined_machines(bc, None, None)  # pas de MoW (validation pure)

    spawns = _spawn_points_by_twpi(bc)
    player_pts = spawns.get(0) or []
    if len(player_pts) < a.roster:
        print(f"[error] only {len(player_pts)} player spawn points "
              f"(need {a.roster})", file=sys.stderr)
        return 2
    player_units = [
        {"unitId": p_units[i], "playerId": PLAYER_ID_HUMAN,
         "col": int(player_pts[i][0]), "row": int(player_pts[i][1])}
        for i in range(a.roster)
    ]

    init = (_rpc(sid, "initAndStart",
                 [{"configJson": json.dumps(bc), "seed": a.seed,
                   "playerUnits": player_units}], timeout=40)
            .get("result") or {})
    rid = init.get("runnerId")
    if rid is None:
        print(f"[error] initAndStart failed: {init}", file=sys.stderr)
        return 2
    print(f"[ok] runnerId={rid} addUnits={len(init.get('addUnits') or [])}")

    try:
        obs = (_rpc(sid, "observeBattle", [{"runnerId": rid}], timeout=10)
               .get("result") or {})
        print(f"[obs] stage={obs.get('stage')} byType={obs.get('byType')}")

        dry = (_rpc(sid, "aiStepDryRun",
                    [{"runnerId": rid, "maxPump": a.maxpump}], timeout=120)
               .get("result") or {})
        print("[dryRun] =====================================================")
        print(f"  ok={dry.get('ok')} player={dry.get('playerId')} "
              f"strat={dry.get('strategySrc')} hasNext={dry.get('hasNext')} "
              f"moveNextCalls={dry.get('moveNextCalls')} "
              f"emptyYields={dry.get('emptyYields')} "
              f"mutated={dry.get('mutated')}")
        act = dry.get("action") or {}
        print(f"  activatedUnit={dry.get('activatedUnitId')} "
              f"actionMsgs={act.get('count')}")
        for m in (act.get("messages") or []):
            print(f"    - {json.dumps(m)}")
        if not dry.get("ok"):
            print(f"  ERROR: {dry.get('error')}")

        # card : CARTE DÉCISION unifiée (Phase 4 merge) = decisionView + board.py
        # (terrain/hex, depuis la BC) + gameconfig (kits) + danger zone géométrique.
        if a.mode == "card":
            if a.advance > 0:
                played = 0
                while played < a.advance:
                    chunk = min(2, a.advance - played)
                    r = (_rpc(sid, "aiPlayByUnit",
                              [{"runnerId": rid, "maxTurns": chunk,
                                "maxActivations": 9999, "maxPump": a.maxpump}],
                              timeout=180).get("result") or {})
                    if not r.get("ok"):
                        print(f"  [advance] ERROR: {r.get('error')}"); break
                    played += r.get("turnsPlayed") or 0
                    if r.get("finalStage") != 1:
                        break
            req = {"runnerId": rid, "maxRank": a.maxrank}
            if a.allabilities:
                req["allAbilities"] = True
            res = (_rpc(sid, "decisionView", [req], timeout=300).get("result") or {})
            if not res.get("ok"):
                print(f"  decisionView ERROR: {res.get('error')}")
                return 0
            import oracle  # noqa: E402
            from board import Board  # noqa: E402
            print(oracle.build_card(res, Board(bc)))
            return 0
        # predict : probe DamagePrediction (GetAllPredictions + get_Item) pour
        # (unit, target) depuis une tile choisie. Valide la chaîne d'invoke.
        if a.mode == "predict":
            if a.advance > 0:
                played = 0
                while played < a.advance:
                    chunk = min(2, a.advance - played)
                    r = (_rpc(sid, "aiPlayByUnit",
                              [{"runnerId": rid, "maxTurns": chunk,
                                "maxActivations": 9999, "maxPump": a.maxpump}],
                              timeout=180).get("result") or {})
                    if not r.get("ok"):
                        print(f"  [advance] ERROR: {r.get('error')}"); break
                    played += r.get("turnsPlayed") or 0
                    print(f"  [advance] +{r.get('turnsPlayed')}t "
                          f"stage={r.get('finalStageName')} player={r.get('finalPlayer')}")
                    if r.get("finalStage") != 1:
                        break
            req = {"runnerId": rid, "unitId": a.unit, "targetId": a.target}
            if a.ability is not None:
                req["abilityType"] = a.ability
            if a.tilecol is not None:
                req["col"] = a.tilecol
            if a.tilerow is not None:
                req["row"] = a.tilerow
            resp = _rpc(sid, "aiPredict", [req], timeout=60)
            print("[aiPredict raw] ============================================")
            print(json.dumps(resp, indent=2)[:2000])
            return 0
        # decisionView : LA vue décision-ready en un appel (méta + units +
        # toActivate + attackPlans + dangerZone). Couche dynamique de l'oracle.
        if a.mode == "view":
            if a.advance > 0:
                played = 0
                while played < a.advance:
                    chunk = min(2, a.advance - played)
                    r = (_rpc(sid, "aiPlayByUnit",
                              [{"runnerId": rid, "maxTurns": chunk,
                                "maxActivations": 9999, "maxPump": a.maxpump}],
                              timeout=180).get("result") or {})
                    if not r.get("ok"):
                        print(f"  [advance] ERROR: {r.get('error')}"); break
                    played += r.get("turnsPlayed") or 0
                    print(f"  [advance] +{r.get('turnsPlayed')}t "
                          f"stage={r.get('finalStageName')} player={r.get('finalPlayer')}")
                    if r.get("finalStage") != 1:
                        break
            req = {"runnerId": rid, "maxRank": a.maxrank}
            if a.allabilities:
                req["allAbilities"] = True
            res = (_rpc(sid, "decisionView", [req], timeout=300).get("result") or {})
            print("[decisionView] =============================================")
            print(f"  ok={res.get('ok')} stage={res.get('stageName')} "
                  f"turn={res.get('turn')} player={res.get('currentPlayer')} "
                  f"mutated={res.get('mutated')} removeWorks={res.get('removeWorks')} "
                  f"ms={res.get('ms')} units={res.get('unitCount')}")
            if not res.get("ok"):
                print(f"  ERROR: {res.get('error')}")
                return 0
            print(f"  toActivate({res.get('toActivateCount')}): {res.get('toActivate')}")
            print("  -- units (flags: C=ctrl A=action R=ranged/m=melee x=dead) --")
            for u in (res.get("units") or []):
                ab = "/".join(x.get("name") for x in (u.get("abilities") or []))
                pos = u.get("pos") or {}
                fl = ("C" if u.get("ctrl") else "-") + ("A" if u.get("hasAction") else "-") \
                    + ("R" if u.get("ranged") else "m") + ("x" if not u.get("alive") else "-")
                print(f"    u{u.get('id')} [{u.get('visualId')}] "
                      f"@({pos.get('col')},{pos.get('row')}) hp={u.get('hp')} "
                      f"t{u.get('team')} {fl} ab=[{ab}]")
            dz = res.get("dangerZone") or {}
            tiles = sorted((t["col"], t["row"]) for t in (dz.get("tiles") or []))
            print(f"  -- dangerZone: {dz.get('tileCount')} tiles menacées --")
            print("     " + " ".join(f"({c},{r})" for c, r in tiles))
            print("  -- attackPlans (joueur courant) --")
            for p in (res.get("attackPlans") or []):
                pos = p.get("pos") or {}
                print(f"    u{p.get('unitId')} [{p.get('visualId')}] "
                      f"@({pos.get('col')},{pos.get('row')}):")
                for ev in (p.get("evals") or []):
                    ranked = ev.get("ranked") or []
                    tlist = " > ".join(
                        f"({t['col']},{t['row']})" + (
                            f"[{t.get('dmgMin')}-{t.get('dmgMax')}"
                            f"{'K' if t.get('kill') else ''}"
                            f"{'*' if t.get('mightCrit') else ''}]"
                            if t.get('dmgMax') is not None else "")
                        for t in ranked) or "(aucune)"
                    print(f"      [{ev.get('ability')}] vs u{ev.get('targetId')} "
                          f"rank={ev.get('rankCount')}: {tlist}")
            return 0
        # apply : PHASE 5 — joue MON coup en 2 TEMPS (move PUIS ability) via le
        # RPC applyAction, en observant le diff RÉEL après chaque étape. Coup
        # auto-sélectionné depuis la carte (killSure > kill > dmg max) ; override
        # possible via --unit/--target/--ability/--tilecol/--tilerow.
        if a.mode == "apply":
            if a.advance > 0:
                played = 0
                while played < a.advance:
                    chunk = min(2, a.advance - played)
                    r = (_rpc(sid, "aiPlayByUnit",
                              [{"runnerId": rid, "maxTurns": chunk,
                                "maxActivations": 9999, "maxPump": a.maxpump}],
                              timeout=180).get("result") or {})
                    if not r.get("ok"):
                        print(f"  [advance] ERROR: {r.get('error')}"); break
                    played += r.get("turnsPlayed") or 0
                    if r.get("finalStage") != 1:
                        break
            req = {"runnerId": rid, "maxRank": a.maxrank}
            res = (_rpc(sid, "decisionView", [req], timeout=300).get("result") or {})
            if not res.get("ok"):
                print(f"  decisionView ERROR: {res.get('error')}"); return 0
            import oracle  # noqa: E402
            from board import Board  # noqa: E402
            print(oracle.build_card(res, Board(bc)))

            units_by_id = {u["id"]: u for u in (res.get("units") or [])}
            my_ids = [u["id"] for u in (res.get("units") or []) if u.get("ctrl")]

            # --moveonly : test OVERWATCH — bouge SEULEMENT --unit vers
            # (--tilecol,--tilerow) et lit les events du move (le flag overwatch
            # fire si un ennemi frappe l'unité pendant son déplacement).
            if a.moveonly:
                if a.unit is None or a.tilecol is None or a.tilerow is None:
                    print("  [moveonly] besoin de --unit --tilecol --tilerow")
                    return 0
                mv = (_rpc(sid, "applyAction",
                           [{"runnerId": rid,
                             "action": {"kind": "move", "unitId": a.unit,
                                        "to": {"col": a.tilecol,
                                               "row": a.tilerow}}}],
                           timeout=60).get("result") or {})
                _print_apply("MOVE-ONLY", mv, my_ids)
                return 0

            caster, target, ability = a.unit, a.target, a.ability
            tile = (a.tilecol, a.tilerow) if a.tilecol is not None else None
            if None in (caster, target, ability) or tile is None:
                best = None  # (priorité, plan, eval, tile)
                for p in (res.get("attackPlans") or []):
                    for ev in (p.get("evals") or []):
                        for t in (ev.get("ranked") or []):
                            if t.get("dmgMax") is None:
                                continue
                            pr = (2 if t.get("killSure")
                                  else 1 if t.get("kill") else 0,
                                  t.get("dmgMax") or 0)
                            if best is None or pr > best[0]:
                                best = (pr, p, ev, t)
                if best is None:
                    print("  [apply] aucun plan d'attaque exploitable"); return 0
                _, p, ev, t = best
                caster, target = p["unitId"], ev["targetId"]
                ability = ev["abilityId"]
                tile = (t["col"], t["row"])
            print(f"\n  >>> COUP CHOISI : u{caster} -> ({tile[0]},{tile[1]}) "
                  f"puis ability {ability} sur u{target}\n")

            # Étape 1 — MOVE (sauf si déjà sur la tile cible).
            cur = units_by_id.get(caster, {}).get("pos") or {}
            if (cur.get("col"), cur.get("row")) != tile:
                mv = (_rpc(sid, "applyAction",
                           [{"runnerId": rid,
                             "action": {"kind": "move", "unitId": caster,
                                        "to": {"col": tile[0], "row": tile[1]}}}],
                           timeout=60).get("result") or {})
                _print_apply("ÉTAPE 1 · MOVE", mv, my_ids)
            else:
                print("  [ÉTAPE 1 · MOVE] déjà sur la tile — pas de move")

            # Étape 2 — ABILITY (observée séparément → décomposition 2 temps).
            ab = (_rpc(sid, "applyAction",
                       [{"runnerId": rid,
                         "action": {"kind": "ability", "casterId": caster,
                                    "targetId": target, "abilityType": ability}}],
                       timeout=60).get("result") or {})
            _print_apply("ÉTAPE 2 · ABILITY", ab, my_ids)
            return 0
        # owatch : joue N tours d'IA avec capture de TOUTE la cascade, et la
        # décode UNIFORMÉMENT. L'overwatch n'est PAS un cas spécial — c'est un
        # UnitDamaged labellisé [overwatch] (Effect_Type=1009) parmi les autres
        # effets (counter, aura, dot, direct). N = --advance (défaut 16).
        if a.mode == "owatch":
            import stream_events  # noqa: E402
            from collections import Counter
            n = a.advance if a.advance > 0 else 16
            r = (_rpc(sid, "aiPlayByUnit",
                      [{"runnerId": rid, "maxTurns": n, "maxActivations": 9999,
                        "maxPump": a.maxpump, "captureEvents": True}],
                      timeout=400).get("result") or {})
            print(f"  [owatch] ok={r.get('ok')} turnsPlayed={r.get('turnsPlayed')} "
                  f"stop={r.get('stopReason')} events={r.get('cascadeCount')}")
            cascade = r.get("cascade") or []
            an = stream_events.analyze(cascade, [])  # pas de 'moi' → tout = damage
            dmg = an["damage"]
            if not dmg:
                print("  (aucun dégât dans la cascade)")
                return 0
            byeff = Counter(d.get("effect") or "direct" for d in dmg)
            print(f"  {len(dmg)} coups, par effet: {dict(byeff)} "
                  f"(overwatch = 1 effet parmi d'autres)")
            for d in dmg:
                crit = " CRIT" if d["crit"] else ""
                kill = " → TUÉ" if d["killed"] else ""
                eff = f" [{d['effect']}]" if d.get("effect") else ""
                print(f"    u{d['attacker']}->u{d['target']} "
                      f"{d['amount']}{crit}{eff}{kill}")
            return 0
        # RANKING des tiles d'attaque par (unit, target) — shrink-and-recall sur
        # GetBestTileToAttackFrom. Donne, par ennemi ciblable, les positions
        # d'attaque rankées par l'utilité IA (rank 0 = ce que l'IA choisirait,
        # rank 1+ = fallbacks si la tile est prise par une autre unité).
        if a.mode == "rank":
            # Optionnel : avance le combat de N tours (chunks de 2, anti-freeze)
            # pour rapprocher les camps — au tour 1 personne n'est à portée.
            if a.advance > 0:
                played = 0
                while played < a.advance:
                    chunk = min(2, a.advance - played)
                    r = (_rpc(sid, "aiPlayByUnit",
                              [{"runnerId": rid, "maxTurns": chunk,
                                "maxActivations": 9999, "maxPump": a.maxpump}],
                              timeout=180).get("result") or {})
                    if not r.get("ok"):
                        print(f"  [advance] ERROR: {r.get('error')}")
                        break
                    played += r.get("turnsPlayed") or 0
                    print(f"  [advance] +{r.get('turnsPlayed')}t "
                          f"stage={r.get('finalStageName')} "
                          f"player={r.get('finalPlayer')}")
                    if r.get("finalStage") != 1:
                        print("  [advance] battle finie avant rank")
                        break
            # RPC AUTONOME : il lit lui-même les abilities concrètes de chaque
            # unit (NormalAttackType + actives si --allabilities) et ajoute la
            # tile courante au set candidat. --ability/--unit/--target forcent.
            req = {"runnerId": rid, "maxRank": a.maxrank}
            if a.unit is not None:
                req["unitId"] = a.unit
            if a.target is not None:
                req["targetId"] = a.target
            if a.ability is not None:
                req["abilityType"] = a.ability
            if a.override is not None:
                req["overrideRange"] = a.override
            if a.allabilities:
                req["allAbilities"] = True
            res = (_rpc(sid, "aiAttackRank", [req], timeout=300)
                   .get("result") or {})
            print("[attack-rank (autonome — GetBestTileToAttackFrom shrink-and-recall)]")
            print(f"  ok={res.get('ok')} player={res.get('playerId')} "
                  f"abilityMode={res.get('abilityMode')} maxRank={res.get('maxRank')} "
                  f"mutated={res.get('mutated')} removeWorks={res.get('removeWorks')} "
                  f"units={res.get('unitCount')} enemies={res.get('enemyCount')} "
                  f"ms={res.get('ms')}")
            if not res.get("ok"):
                print(f"  ERROR: {res.get('error')}")
                return 0
            for u in (res.get("units") or []):
                vis = u.get("visualId") or "?"
                pos = u.get("pos") or {}
                ct = u.get("currentTile") or {}
                abils = ", ".join(
                    f"{ab.get('name')}({ab.get('id')}/{ab.get('kind')})"
                    for ab in (u.get("abilities") or [])) or "(aucune)"
                print(f"  u{u.get('unitId')} [{vis}] @({pos.get('col')},"
                      f"{pos.get('row')}) tileCourante=({ct.get('col')},"
                      f"{ct.get('row')}) abilities=[{abils}]")
                for ev in (u.get("evals") or []):
                    ranked = ev.get("ranked") or []
                    tlist = " > ".join(f"({t.get('col')},{t.get('row')})"
                                       for t in ranked) or "(aucune)"
                    err = f"  ERR={ev.get('err')}" if ev.get("err") else ""
                    tp = ev.get("targetPos") or {}
                    print(f"    [{ev.get('ability')}] vs u{ev.get('targetId')} "
                          f"[{ev.get('targetVis')}] @({tp.get('col')},"
                          f"{tp.get('row')}) movable={ev.get('movableCount')} "
                          f"rank={ev.get('rankCount')}: {tlist}{err}")
            return 0
        # Buff CONDITIONNEL : +N appliqué seulement aux units adjacentes au
        # buffeur au début du tour (ce que fait réellement Warboss/Sibyll via
        # ExtraRangeCondition). Combine 2 sweeps (base + buffé) + filtre adjacence.
        if a.mode == "buffcond":
            base = (_rpc(sid, "aiMovableTiles",
                         [{"runnerId": rid, "side": "friendly", "extraRange": 0}],
                         timeout=150).get("result") or {})
            buf = (_rpc(sid, "aiMovableTiles",
                        [{"runnerId": rid, "side": "friendly",
                          "extraRange": a.buff}], timeout=150).get("result") or {})
            bb = {u["unitId"]: u for u in (base.get("units") or [])}
            bf = {u["unitId"]: u for u in (buf.get("units") or [])}
            if not bb:
                print(f"  ERROR: {base.get('error')}")
                return 0
            # Buffeur = 1re unité (stand-in Warboss) ; aura aux adjacents (dist<=1).
            buffer_id = next(iter(bb))
            bpos = bb[buffer_id].get("pos") or {}
            print(f"[buff conditionnel +{a.buff}] buffeur = u{buffer_id} "
                  f"[{bb[buffer_id].get('visualId')}] @({bpos.get('col')},"
                  f"{bpos.get('row')}) — aura aux units adjacentes (dist<=1)")
            for uid, ub in bb.items():
                pos = ub.get("pos") or {}
                dist = (max(abs(pos.get("col", 0) - bpos.get("col", 0)),
                            abs(pos.get("row", 0) - bpos.get("row", 0)))
                        if pos and bpos else 99)
                adj = dist <= 1
                eff = bf.get(uid, ub) if adj else ub
                tag = "BUFFÉ " if adj else "base  "
                print(f"    u{uid} [{ub.get('visualId')}] @({pos.get('col')},"
                      f"{pos.get('row')}) dist={dist} {tag} "
                      f"tiles={eff.get('tileCount')} (base {ub.get('tileCount')})")
            return 0
        # Buff de move range : compare les tiles atteignables base vs +N
        # (OverrideRangeBonus.ExtraRange = ce que pose le Warboss/Sibyll).
        if a.mode == "buff":
            base = {}
            for er in (0, 2, 4):
                res = (_rpc(sid, "aiMovableTiles",
                            [{"runnerId": rid, "side": "friendly",
                              "extraRange": er}], timeout=150).get("result") or {})
                if not res.get("ok"):
                    print(f"  extraRange={er} ERROR: {res.get('error')}")
                    break
                print(f"[move tiles · extraRange=+{er}] mutated={res.get('mutated')}")
                for u in (res.get("units") or []):
                    vis = u.get("visualId") or "?"
                    pos = u.get("pos") or {}
                    tiles = u.get("tiles") or []
                    rad = 0
                    for t in tiles:
                        if pos:
                            rad = max(rad, abs(t.get("col", 0) - pos.get("col", 0)),
                                      abs(t.get("row", 0) - pos.get("row", 0)))
                    b = base.get(u.get("unitId"))
                    delta = f" (+{u.get('tileCount') - b})" if b is not None else ""
                    if er == 0:
                        base[u.get("unitId")] = u.get("tileCount")
                    print(f"    u{u.get('unitId')} [{vis}] tiles={u.get('tileCount')}"
                          f"{delta} maxRadius={rad}")
            return 0
        # Danger zone = menace ennemie (move ∪ portée d'attaque). Par unité +
        # union agrégée. Read-only.
        if a.mode == "danger":
            res = (_rpc(sid, "aiMovableTiles",
                        [{"runnerId": rid, "side": "enemy", "threat": True}],
                        timeout=150).get("result") or {})
            print("[danger zone (enemy threat = move + hit)] ==================")
            print(f"  ok={res.get('ok')} mutated={res.get('mutated')} "
                  f"enemies={res.get('unitCount')} "
                  f"UNION dangerTiles={res.get('unionTileCount')}")
            if not res.get("ok"):
                print(f"  ERROR: {res.get('error')}")
            for u in (res.get("units") or []):
                vis = u.get("visualId") or "?"
                pos = u.get("pos") or {}
                err = f" ERR={u.get('err')}" if u.get("err") else ""
                print(f"    u{u.get('unitId')} [{vis}] @({pos.get('col')},"
                      f"{pos.get('row')}) move={u.get('tileCount')} "
                      f"threat={u.get('threatCount')}{err}")
            uni = sorted((t["col"], t["row"]) for t in (res.get("unionTiles") or []))
            print("  UNION danger tiles: " + " ".join(f"({c},{r})" for c, r in uni))
            return 0
        # Tiles atteignables en dry-run (y compris deep-strike = portée étendue).
        if a.mode == "tiles":
            if a.advance > 0:
                played = 0
                while played < a.advance:
                    chunk = min(2, a.advance - played)
                    r = (_rpc(sid, "aiPlayByUnit",
                              [{"runnerId": rid, "maxTurns": chunk,
                                "maxActivations": 9999, "maxPump": a.maxpump}],
                              timeout=180).get("result") or {})
                    if not r.get("ok"):
                        print(f"  [advance] ERROR: {r.get('error')}"); break
                    played += r.get("turnsPlayed") or 0
                    if r.get("finalStage") != 1:
                        break
            res = (_rpc(sid, "aiMovableTiles", [{"runnerId": rid}], timeout=120)
                   .get("result") or {})
            print("[movableTiles dry-run] ======================================")
            print(f"  ok={res.get('ok')} player={res.get('playerId')} "
                  f"mutated={res.get('mutated')} units={res.get('unitCount')}")
            if not res.get("ok"):
                print(f"  ERROR: {res.get('error')}")
            for u in (res.get("units") or []):
                vis = u.get("visualId") or "?"
                pos = u.get("pos") or {}
                tag = " <== DEEP STRIKE" if "erminator" in vis else ""
                tiles = u.get("tiles") or []
                # rayon max (Chebyshev) depuis la position courante
                rad = 0
                for t in tiles:
                    if pos:
                        rad = max(rad, abs(t.get("col", 0) - pos.get("col", 0)),
                                  abs(t.get("row", 0) - pos.get("row", 0)))
                err = f" ERR={u.get('err')}" if u.get("err") else ""
                # détecte doublons + tiles invalides (-1)
                coords = [(t.get("col"), t.get("row")) for t in tiles]
                ninv = sum(1 for c in coords if c[0] == -1 or c[1] == -1)
                ndup = len(coords) - len(set(coords))
                tlist = " ".join(f"({c},{r})" for c, r in sorted(set(coords)))
                print(f"    u{u.get('unitId')} [{vis}] @({pos.get('col')},"
                      f"{pos.get('row')}) tiles={u.get('tileCount')} "
                      f"distinct={len(set(coords))} dup={ndup} invalid={ninv} "
                      f"maxRadius={rad}{tag}{err}")
                print(f"        {tlist}")
            return 0
        # Deep-strike = trait TeleportStrike (ex. Terminators). On dry-run
        # toutes les units et on regarde l'action proposée + la DISTANCE du
        # déplacement (un deep-strike téléporte loin vs un move normal adjacent).
        if a.mode == "deepstrike":
            res = (_rpc(sid, "aiDryRunAllUnits",
                        [{"runnerId": rid, "maxPump": a.maxpump}],
                        timeout=150).get("result") or {})
            print("[dryAll + traits] ===========================================")
            print(f"  ok={res.get('ok')} mutated={res.get('mutated')} "
                  f"units={res.get('unitCount')} pumps={res.get('totalPumps')}")
            if not res.get("ok"):
                print(f"  ERROR: {res.get('error')}")
            for u in (res.get("units") or []):
                vis = u.get("visualId") or "?"
                pos = u.get("pos") or {}
                # distance de Chebyshev (hex/grid) entre pos courante et cible
                dist = None
                for m in (u.get("proposed") or []):
                    if m.get("cls") == "MoveUnitMessage" and m.get("to") and pos:
                        to = m["to"]
                        dist = max(abs(to.get("col", 0) - pos.get("col", 0)),
                                   abs(to.get("row", 0) - pos.get("row", 0)))
                tag = " <== DEEP STRIKE (Terminator)" if "erminator" in vis else ""
                acts = "; ".join(json.dumps(m) for m in (u.get("proposed") or [])) or "(none)"
                dstr = f" dist={dist}" if dist is not None else ""
                print(f"    u{u.get('unitId')} [{vis}] @({pos.get('col')},{pos.get('row')})"
                      f"{dstr} -> {acts}{tag}")
            return 0
        # Combat ENTIER en chunks (anti-freeze) + dry-run-all par tour.
        if a.mode == "full":
            all_probes: list = []
            all_demos: list = []
            turn_offset = 0
            final = {}
            for it in range(a.fullchunks):
                r = (_rpc(sid, "aiPlayByUnit",
                          [{"runnerId": rid, "maxTurns": a.chunk,
                            "maxActivations": 9999, "maxPump": a.maxpump,
                            "probeEachTurn": True}], timeout=180).get("result") or {})
                if not r.get("ok"):
                    print(f"  chunk {it} ERROR: {r.get('error')}")
                    break
                for tp in (r.get("turnProbes") or []):
                    tp["turnIndex"] += turn_offset
                    all_probes.append(tp)
                for d in (r.get("demos") or []):
                    d["turnIndex"] += turn_offset
                    all_demos.append(d)
                turn_offset += r.get("turnsPlayed") or 0
                final = r
                stage = r.get("finalStage")
                print(f"  [chunk {it}] +{r.get('turnsPlayed')}t "
                      f"stage={r.get('finalStageName')}({stage}) "
                      f"pumps={r.get('totalPumps')} ms={r.get('ms')}")
                if stage != 1:  # battle finie
                    break
            print("[full battle] ==============================================")
            print(f"  turns={turn_offset} probes={len(all_probes)} "
                  f"demos={len(all_demos)} final={final.get('finalStageName')} "
                  f"winnerPlayer={final.get('finalPlayer')}")
            for tp in all_probes:
                ti, pl = tp.get("turnIndex"), tp.get("player")
                played = [d for d in all_demos
                          if d.get("turnIndex") == ti and d.get("player") == pl]
                print(f"  TURN {ti} P{pl}:")
                for u in (tp.get("proposals") or []):
                    print(f"    propose u{u.get('unitId')}: "
                          f"{_fmt_action(u.get('proposed'))}")
                for d in played:
                    t = (d.get("move") or {}).get("to") or {}
                    print(f"    PLAYED   u{d.get('activatedUnitId')}: "
                          f"Move({t.get('col')},{t.get('row')})")
            return 0
        if a.mode == "dryall":
            res = (_rpc(sid, "aiDryRunAllUnits",
                        [{"runnerId": rid, "maxPump": a.maxpump}],
                        timeout=120).get("result") or {})
            print("[dryAllUnits] ================================================")
            print(f"  ok={res.get('ok')} player={res.get('playerId')} "
                  f"mutated={res.get('mutated')} pumps={res.get('totalPumps')} "
                  f"ms={res.get('ms')} units={res.get('unitCount')}")
            if not res.get("ok"):
                print(f"  ERROR: {res.get('error')}")
            for u in (res.get("units") or []):
                acts = "; ".join(json.dumps(m) for m in (u.get("proposed") or [])) or "(none)"
                print(f"    unit={u.get('unitId')} hasAction={u.get('hasActionLeft')} "
                      f"pumps={u.get('pumps')} -> {acts}")
            return 0  # dryall n'a rien mué : on s'arrête là
        if a.mode == "ordered":
            play = (_rpc(sid, "aiPlayOrdered",
                         [{"runnerId": rid, "order": a.order,
                           "maxActivations": a.maxact, "maxTurns": a.maxturns,
                           "maxPump": a.maxpump}], timeout=240).get("result") or {})
            print(f"[playOrdered order={a.order}] =========================")
        else:
            play = (_rpc(sid, "aiPlayByUnit",
                         [{"runnerId": rid, "maxActivations": a.maxact,
                           "maxTurns": a.maxturns, "maxPump": a.maxpump}],
                         timeout=240).get("result") or {})
            print("[playByUnit] =================================================")
        print(f"  ok={play.get('ok')} turnsPlayed={play.get('turnsPlayed')} "
              f"activations={play.get('totalActivations')} "
              f"pumps={play.get('totalPumps')} ms={play.get('ms')} "
              f"stop={play.get('stopReason')!r}")
        if not play.get("ok"):
            print(f"  ERROR: {play.get('error')}")
        for to in (play.get("turnOrders") or []):
            print(f"    [order] t{to.get('turnIndex')} P{to.get('player')}: "
                  f"{to.get('order')}")
        for d in (play.get("demos") or []):
            print(f"    t{d.get('turnIndex')} P{d.get('player')} "
                  f"unit={d.get('activatedUnitId')} "
                  f"-> {d.get('move', {}).get('to')} "
                  f"(toActivate={len(d.get('toActivate') or [])})")
    finally:
        _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=5)
        print("[ok] runner disposed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
