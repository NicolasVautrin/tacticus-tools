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
    #: [(pas, visualId, motif)] des pas ECARTES par la recherche (#506-r1). Vide = le pas etait
    #: EPINGLE (ou trouve du premier coup) -- la trace, pas un signal.
    searched: list = None


def _apply_native(rpc, rid: int, dry: dict) -> None:
    """Applique l'action NATIVE deja obtenue (`aiStepDryRun` ne mute pas) -> avance d'un chunk."""
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


def _walk_to(rpc, rid: int, step: int) -> None:
    """Avance de `step` chunks sur la trajectoire NATIVE (aiStepDryRun -> applyAction)."""
    for i in range(step):
        dry = rpc("aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            pytest.skip("trajectoire native epuisee au pas %d (%s)" % (i, dry.get("error")))
        _apply_native(rpc, rid, dry)


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


def _visual_of(rpc, rid: int, uid) -> str | None:
    """`visualId` de l'unite activee -- lecture LEGERE (`maxRank=1`, pas d'`allAbilities`).

    Sert de PRE-FILTRE a la recherche de pas : construire le `AiDecisionContext` complet a chaque
    pas coute un `decisionView` a 32 rangs + `aiMovableTiles` + le predicteur ; ce filtre-ci en
    ecarte la quasi-totalite pour un seul RPC leger."""
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 90) or {}
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return (u or {}).get("visualId")


def build_sweep_order_case(rpc, build_runner, seed: str, board: str, step: int,
                           extra: list | None = None, *, carrier: str | None = None,
                           accept=None, search: int = 0) -> SweepOrderCase:
    """Monte la bataille, marche jusqu'au pas voulu, et rend son etat de decision.

    `search == 0` : comportement HISTORIQUE -- `step` est EPINGLE, on rend le pas `step` tel quel.

    `search > 0` : `step` devient un point de DEPART et le montage **CHERCHE** son pas dans
    `[step, step + search]`, en avancant d'un chunk NATIF entre deux essais. Deux filtres, du plus
    leger au plus lourd :

      * `carrier` -- le `visualId` que le pas doit activer (pre-filtre, un RPC leger) ;
      * `accept(case)` -- le predicat sur le `SweepOrderCase` COMPLET (le tie, le kit declenche...).

    POURQUOI (#506-r1). Un pas EPINGLE est structurellement fragile : la trajectoire est marchee
    par le natif, donc **toute tranche qui change une stat globale la deplace**. La bascule
    « equiper » de #419-r6 a ainsi decale les trois montages de ce module -- au pas 14 de
    `C4_09`/999 c'est `astraCreed` qui est desormais activee et non `templAncient`, et le pas 22 de
    `C4_09`/31337 n'existe plus (la bataille finit avant). Les assertions, elles, n'ont pas bouge :
    ce qui a peri, c'est la PREMISSE que le montage installait. La chercher au lieu de l'epingler
    rend le montage robuste au prochain re-etalonnage global -- et il y en aura d'autres.

    ⚠ **ECHEC NOMME, JAMAIS UN SKIP.** Si la fenetre est epuisee sans satisfaire les filtres, on
    LEVE en disant ce qui a ete essaye. Un `skip` ferait exactement ce que #455 documente : un
    fichier vert au `rc` qui n'evalue plus rien."""
    rid = build_runner(seed, extra=list(extra or []), board=board)["rid"]
    _walk_to(rpc, rid, step)

    essais: list = []
    for k in range(int(search) + 1):
        cur = step + k
        dry = rpc("aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            if not essais:
                pytest.skip("pas %d non atteint (%s)" % (cur, dry.get("error")))
            raise AssertionError(
                "montage %s/%s : la fenetre de recherche [%d, %d] est epuisee (trajectoire finie "
                "au pas %d : %s). Essais : %r"
                % (board, seed, step, step + search, cur, dry.get("error"), essais))
        uid = dry.get("activatedUnitId")
        if carrier is not None:
            vis = _visual_of(rpc, rid, uid)
            if vis != carrier:
                essais.append((cur, vis, "porteur"))
                _apply_native(rpc, rid, dry)
                continue
        c = _case_at(rpc, rid, cur, dry, uid, strict=(search == 0))
        if c is None:
            # Pas sans unite activee lisible (fin de tour, unite hors `decisionView`). En regime
            # EPINGLE `_case_at` a deja skippe ; en regime RECHERCHE c'est un pas a ECARTER, pas
            # une raison d'abandonner -- sinon le premier pas muet de la fenetre eteint toute la
            # recherche (mesure : 6 skipped / 0 passed).
            essais.append((cur, None, "sans unite activee"))
            _apply_native(rpc, rid, dry)
            continue
        if accept is None or accept(c):
            c.searched = essais
            return c
        essais.append((cur, c.visual_id, "accept"))
        _apply_native(rpc, rid, dry)
    raise AssertionError(
        "montage %s/%s : aucun pas de [%d, %d] ne satisfait les filtres (carrier=%r, accept=%s). "
        "Essais : %r" % (board, seed, step, step + search, carrier,
                         getattr(accept, "__name__", accept), essais))


def _case_at(rpc, rid: int, step: int, dry: dict, uid, *, strict: bool = True):
    """L'etat de decision du pas COURANT (le runner n'a pas ete mute : `aiStepDryRun` est pur).

    `strict` = regime EPINGLE : un pas dont l'unite activee n'est pas lisible SKIPPE (comportement
    historique). En regime RECHERCHE on rend `None` et l'appelant ECARTE le pas."""
    msgs = (dry.get("action") or {}).get("messages") or []
    nat_move = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)
    nat_ab = next((m for m in msgs if m.get("cls") == "ActiveAbilityMessage"), None)

    # aiStepDryRun ne MUTE PAS : l'etat runner est encore celui de la decision.
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
    if me is None:
        if strict:
            pytest.skip("unite activee u%s absente de decisionView" % uid)
        return None
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
