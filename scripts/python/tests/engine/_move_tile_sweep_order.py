"""Montage REUTILISABLE du SWEEP DE POSITION du tier Comparable (residu R1-b).

Pourquoi un module de montage et pas une fixture inline : l'ordre de sweep ne s'observe QUE sur
un pas ou DEUX tuiles candidates atteignent la MEME utilite d'action -- toute autre situation est
tranchee par l'utilite et ne dit RIEN de l'ordre. Fabriquer ce pas demande de marcher une
trajectoire NATIVE reelle jusqu'a lui, ce qui est cher : on le monte une fois, on l'expose.

Ce que le montage produit (`SweepOrderCase`) pour un couple (board, seed, pas) :
  * le `AiDecisionContext` de l'unite activee, A L'ETAT DE DECISION du pas (avant `applyAction`) ;
  * `action_tiles` = l'ordre NATIF des positions candidates -- `[origine] + aiMovableTiles` (cf.
    `engine.ai.action_generators.ComparableAbilityGenerator._sweep_tiles` pour la chaine native) ;
  * `ranked_union` = l'ordre du plan (`IdunBattle.Core.Services.AttackQuery$$GetBestTileToAttackFrom`,
    shrink-and-recall cote hook) -- l'ordre CONCURRENT, qui ne sert nulle part dans le generateur
    d'action natif ;
  * `tie_tiles` = les tuiles a utilite d'action MAXIMALE pour la paire (ability, cible) retenue :
    c'est LA situation ou l'ordre decide. `len(tie_tiles) <= 1` => le montage ne conclut rien.
  * la decision NATIVE du pas (ability, cible, tuile) -- pour le rapport ET, depuis N13, pour
    l'assertion d'AGREEMENT de tuile : c'est le seul confront LIVE du terme de tuile qui ne
    demande pas d'armer les hooks RVA de `scorer-damage-trace` ;
  * `tile_terms` = le composite Tile(7) du PORT par tuile candidate (`playbook.base.tile_utility`),
    ce qui rend la SEPARATION des tuiles lisible sans hook (residu N13 : le port EGALISAIT des
    tuiles que le natif separe).

ASCII only.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from engine import weights as W
from engine.ai import context as _ai_ctx
from engine.ai.action_generators import ComparableAbilityGenerator
from engine.playbook import noncomparable as playbooks
from engine.playbook import get_playbook_or_default
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK
from engine.playbook import scene as _scene


@dataclass
class SweepOrderCase:
    rid: int
    step: int
    uid: int
    visual_id: str | None
    origin: tuple | None
    ctx: object
    action_tiles: list
    ranked_union: list
    tie_tiles: list                # tuiles a utilite d'action MAX pour (ab, tgt) du best
    best: tuple | None             # (u, u_action, tgt, ab, tile) rendu par `_best_attack`
    native_tile: tuple | None
    native_ability: int | None
    native_target: int | None
    tile_terms: dict               # {(col,row): Tile(7) du PORT} sur `action_tiles` (N13)


def _walk_to(rpc, rid: int, step: int) -> None:
    """Avance de `step` chunks sur la trajectoire NATIVE (aiStepDryRun -> applyAction)."""
    for i in range(step):
        dry = rpc("aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            pytest.skip("trajectoire native epuisee au pas %d (%s)" % (i, dry.get("error")))
        for m in ((dry.get("action") or {}).get("messages") or []):
            cls = m.get("cls")
            if cls == "MoveUnitMessage":
                act = {"kind": "move", "unitId": m["unitId"],
                       "to": {"col": m["to"]["col"], "row": m["to"]["row"]}}
            elif cls == "ActiveAbilityMessage":
                act = {"kind": "ability", "casterId": m["casterId"],
                       "targetId": m.get("targetId"), "abilityType": m["abilityType"]}
            elif cls == "FinishUnitTurnMessage":
                act = {"kind": "finish", "unitId": m["unitId"]}
            else:
                continue
            rpc("applyAction", {"runnerId": rid, "action": act}, 90)


def _evals(ctx) -> list:
    out = []
    for ev in ((ctx.plans.get(ctx.uid) or {}).get("evals") or []):
        if not ev.get("rankCount") or not (ev.get("ranked") or []):
            continue
        if playbooks.is_noncomp(ev.get("abilityId")):
            continue
        out.append(ev)
    return out


def _tie_tiles(ctx, best) -> list:
    """Tuiles d'`action_tiles` atteignant l'utilite d'action MAX de la paire (ability, cible) du
    `best` -- l'ensemble sur lequel le keep-first natif tranche."""
    if best is None:
        return []
    _, u_action, tgt, ab, _ = best
    ev = next((e for e in _evals(ctx)
               if e.get("abilityId") == ab and e.get("targetId") == tgt), None)
    if ev is None:
        return []
    legal = {(rk.get("col"), rk.get("row")) for rk in (ev.get("ranked") or [])}
    gen = ComparableAbilityGenerator()
    pb = NORMAL_ATTACK_PLAYBOOK if ab in ctx.normal_ids else get_playbook_or_default(ab)
    hits = []
    for tile in (ctx.action_tiles or []):
        if tile not in legal:
            continue
        cand = gen._action_utility(ctx, pb, ab, tgt, tile)
        if cand is not None and abs(cand[0] - u_action) < 1e-9:
            hits.append(tile)
    return hits


def build_sweep_order_case(rpc, build_runner, seed: str, board: str, step: int,
                           extra: list | None = None) -> SweepOrderCase:
    """Monte la bataille, marche `step` chunks NATIFS, et rend l'etat de decision du pas `step`."""
    rid = build_runner(seed, extra=list(extra or []), board=board)["rid"]
    _walk_to(rpc, rid, step)

    dry = rpc("aiStepDryRun", {"runnerId": rid}, 60)
    if not dry.get("ok") or not dry.get("hasNext"):
        pytest.skip("pas %d non atteint (%s)" % (step, dry.get("error")))
    uid = dry.get("activatedUnitId")
    msgs = (dry.get("action") or {}).get("messages") or []
    nat_move = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)
    nat_ab = next((m for m in msgs if m.get("cls") == "ActiveAbilityMessage"), None)

    # aiStepDryRun ne MUTE PAS : l'etat runner est encore celui de la decision.
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
    if me is None:
        pytest.skip("unite activee u%s absente de decisionView" % uid)
    mpos = me.get("pos") or {}
    origin = (mpos["col"], mpos["row"]) if mpos.get("col") is not None else None

    wt = W.load()
    predictor = _scene.build_predictor(lambda m, b, t: rpc(m, b, t), rid)
    ctx = _ai_ctx.build(lambda m, b, t: rpc(m, b, t), rid, dv, mov_by_unit, uid, wt, predictor)

    seen, ranked_union = set(), []
    for ev in _evals(ctx):
        for rk in (ev.get("ranked") or []):
            t = (rk.get("col"), rk.get("row"))
            if t[0] is not None and t not in seen:
                seen.add(t)
                ranked_union.append(t)

    best = ComparableAbilityGenerator()._best_attack(ctx)
    # Composite Tile(7) du PORT par tuile candidate : MEME fonction que celle qu'appelle
    # `_action_utility` (`playbook.base.tile_utility` = `ComparablePlaybook<T>$$
    # CalculateUtilityFromTilePrediction`), donc ce que le port SEPARE (ou EGALISE) reellement.
    from engine.playbook.base import tile_utility as _tile_u
    tile_terms = {t: _tile_u(ctx, t) for t in (ctx.action_tiles or [])}
    return SweepOrderCase(
        rid=rid, step=step, uid=uid, visual_id=me.get("visualId"), origin=origin, ctx=ctx,
        action_tiles=list(ctx.action_tiles or []), ranked_union=ranked_union,
        tie_tiles=_tie_tiles(ctx, best), best=best,
        native_tile=((nat_move["to"]["col"], nat_move["to"]["row"]) if nat_move else origin),
        native_ability=(nat_ab or {}).get("abilityType"),
        native_target=(nat_ab or {}).get("targetId"),
        tile_terms=tile_terms)
