#!/usr/bin/env python
"""Probe R1-b -- ORDRE des tuiles dans le SWEEP DE POSITION du tier Comparable.

QUESTION BINAIRE : quand deux positions candidates rendent la MEME utilite d'action, laquelle le
natif garde-t-il ? Autrement dit : quelle est la STRUCTURE DE BOUCLES qui produit l'ordre de
presentation au `Bucket` (keep-first), et le port la reproduit-il ?

CHAINE NATIVE (decompilee, build gqfc5mff6c) -- trois boucles IMBRIQUEES :

  `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`
      foreach ability in `...ActiveAbilityActionGenerator$$GetUnitAbilitiesInOrder`      <- MAJEURE
          playbook = `IdunBattle.AI.PlaybookDatabase$$LoadPlaybook`(ability)
          foreach position in `tiles`                                                  <- MEDIANE
              bucketOfTile = playbook.Evaluate(unit, position, ctx)
              `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$Merge`(bucket, bucketOfTile)

  `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$EvaluateInternal`
      foreach target in `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsEntities`  <- MINEURE
          if (utility > best) best = action                                            (`>` STRICT)

  `...Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction` : seede le 1er, remplace sur `>`
  STRICT => KEEP-FIRST a utilite EGALE, a CHAQUE etage.

  `tiles` = `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles` -> `IBattleQuery`+0xe =
  `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor` :
      set = new OrderedSet<UnitPosition>(GetUnitPosition(unit));   // COURANTE, en TETE
      set.UnionWith(MovementQuery.GetMovablePositionsFor(unit, flag, default));
  et `IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFor` :
      tiles = GetMovableTilesFor(unit, flag, options);   // OrderedSet<Tile>, ordre d'INSERTION
      tiles.UnionWith(EntityExtensions.IterateTiles(unit));
      return GetMovablePositionsFromTiles(tiles, feetCount);
  `...$$GetMovablePositionsFromTiles` a feetCount == 1 = `IdunBattle.Core.UnitPositionExtensions$$ToUnitPositionList`
  = boucle `for i in 0..Count-1` sur la LISTE de l'OrderedSet => ORDRE PRESERVE.
  `idun.shared.collections.OrderedSetu003C__Il2CppFullySharedGenericTypeu003E` EST une `List<T>`
  (+ `HashSet<T>` @+0x28) : `$$Add` fait `hashSet.Add` puis `List.Add` (insertion), `$$UnionWith`
  -> `$$SyncListWithSet` APPEND les manquants dans l'ordre de la source.
  ==> l'ordre natif des positions candidates est EXACTEMENT `[origine] + aiMovableTiles`
  (le RPC `aiMovableTiles` appelle le MEME `GetMovableTilesFor` et lit la MEME `List<T>`).

CE QUE LA PROBE MESURE, par etage, sur une trajectoire NATIVE reelle :

  (A) ORDRE-SOURCE : `ranked` (rang `GetBestTileToAttackFrom`) est-il l'ordre `action_tiles` ?
      Compte les pas ou les deux listes divergent -> si 0, l'ordre ne peut RIEN changer et le
      montage ne conclut rien (il faut alors un autre couple).

  (B) TROIS STRUCTURES DE SWEEP, meme ensemble candidat, meme utilite par candidat :
        * `pair_rank`   = pair-major (ability,cible) puis tuiles dans l'ordre `ranked`  [PORT AVANT]
        * `pair_action` = pair-major puis tuiles dans l'ordre `action_tiles`            [l'essai REGRESSIF herite]
        * `ab_tile_tgt` = ability-major -> tuile (`action_tiles`) -> cible              [MIRROR NATIF]
      et, pour chacune, l'accord avec le natif sur (ability, cible, tuile).

  (C) TIES : pour chaque pas, le nombre de tuiles atteignant l'utilite MAXIMALE de l'ability
      gagnante -- c'est la seule situation ou l'ordre decide. Un lot sans tie ne conclut RIEN.

Runner : `--runner <id>` (existant, NON dispose) ou build dedie `--seed`/`--board` (dispose en fin).
ASCII only. Usage :
  python probe_r1b_move_tile_order.py --seed 999 --board C4_09 --steps 26
  python probe_r1b_move_tile_order.py --runner 42 --steps 24
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import engine_validate as EV  # noqa: E402
from engine import weights as W  # noqa: E402
from engine import battle_query as bq  # noqa: E402
from engine.ai import context as _ai_ctx  # noqa: E402
from engine.ai import action_generators as AG  # noqa: E402
from engine.playbook import noncomparable as playbooks  # noqa: E402
from engine.playbook import get_playbook_or_default  # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(seed, board, extra):
    state = ROOT / "logs" / "runners" / f"probeR1b-{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--board", board, "--state-file", str(state)] + list(extra or [])
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO:", (p.stderr or p.stdout or "")[-400:])
        return None, None
    return json.loads(state.read_text())["runnerId"], state


# ---------------------------------------------------------------- utilitaires


def _evals(ctx):
    """Paires (ability, cible) EVALUABLES par le tier Comparable, dans l'ordre du plan
    (ability-major -> cible, cf. `projection.ts::computeAttackPlans`). Une NonComparable est
    rangee par `IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists` dans le tier
    NonComparable SEUL -> jamais evaluee ici (#15)."""
    out = []
    for ev in ((ctx.plans.get(ctx.uid) or {}).get("evals") or []):
        if not ev.get("rankCount") or not (ev.get("ranked") or []):
            continue
        if playbooks.is_noncomp(ev.get("abilityId")):
            continue
        out.append(ev)
    return out


def _rk_tiles(ev):
    return [(rk.get("col"), rk.get("row")) for rk in (ev.get("ranked") or [])
            if rk.get("col") is not None]


def _pb(ctx, ab):
    return NORMAL_ATTACK_PLAYBOOK if ab in ctx.normal_ids else get_playbook_or_default(ab)


def _tgt_pos(ctx):
    return {e.get("id"): (e["pos"]["col"], e["pos"]["row"])
            for e in (ctx.enemies or [])
            if isinstance(e, dict) and (e.get("pos") or {}).get("col") is not None}


def _fmt(b):
    """(u, u_action, tgt, ab, tile) -> (ab, tgt, tile, u_action arrondi)."""
    return None if b is None else (b[3], b[2], b[4], round(b[1], 4))


# ------------------------------------------------------- structures de sweep


def _sweep_pair(ctx, gen, tile_order_fn):
    """PAIR-MAJOR : pour chaque paire (ability, cible), argmax sur les tuiles ; puis argmax
    inter-paires (keep-first) + tie-break #57g (meme ability + meme tuile -> cible de plus petit
    rang cube). C'est la forme du port AVANT ce cas ; `tile_order_fn(ev)` fournit l'ordre balaye."""
    tgt_pos_by_id = _tgt_pos(ctx)
    best = best_key = best_rank = None
    for ev in _evals(ctx):
        ab, tgt = ev.get("abilityId"), ev.get("targetId")
        pb = _pb(ctx, ab)
        pair_best = None
        for tile in tile_order_fn(ev):
            cand = gen._action_utility(ctx, pb, ab, tgt, tile)
            if cand is None:
                continue
            if pair_best is None or cand[0] > pair_best[0]:
                pair_best = (cand[0], cand[1], cand[2], tile)
        if pair_best is None:
            continue
        key = pair_best[0]
        rank = (bq.iterate_surrounding_tiles_order_key(tgt_pos_by_id[tgt])
                if tgt in tgt_pos_by_id else None)
        if best_key is None or key > best_key:
            best = (pair_best[2], key, tgt, ab, pair_best[3])
            best_key, best_rank = key, rank
        elif (key == best_key and best is not None and ab == best[3] and pair_best[3] == best[4]
              and rank is not None and best_rank is not None and rank < best_rank):
            best = (pair_best[2], key, tgt, ab, pair_best[3])
            best_rank = rank
    return best


def _rank_order(ev):
    return _rk_tiles(ev)


def _action_order_for(ctx):
    """`action_tiles` filtre sur les tuiles LEGALES de l'eval (les autres n'existent pas pour
    cette paire), + les `ranked` absentes d'`action_tiles` en queue (ne doit pas arriver)."""
    at = list(ctx.action_tiles or [])

    def f(ev):
        legal = set(_rk_tiles(ev))
        out = [t for t in at if t in legal]
        out += [t for t in _rk_tiles(ev) if t not in at]
        return out
    return f


def _sweep_ab_tile_tgt(ctx, gen):
    """MIRROR NATIF : ability-major -> tuile (`action_tiles`) -> cible. Keep-first partout."""
    tgt_pos_by_id = _tgt_pos(ctx)
    by_ab, ab_order = {}, []
    for ev in _evals(ctx):
        ab = ev.get("abilityId")
        if ab not in by_ab:
            by_ab[ab] = []
            ab_order.append(ab)
        by_ab[ab].append(ev)
    at = list(ctx.action_tiles or [])
    best = best_key = None
    for ab in ab_order:
        evs = by_ab[ab]
        pb = _pb(ctx, ab)
        # cibles dans l'ordre d'enumeration de `GetEligibleTargetsEntities` (cube-lex, #57g)
        evs = sorted(evs, key=lambda ev: (
            0 if ev.get("targetId") in tgt_pos_by_id else 1,
            bq.iterate_surrounding_tiles_order_key(tgt_pos_by_id[ev["targetId"]])
            if ev.get("targetId") in tgt_pos_by_id else 0))
        legal = {ev.get("targetId"): set(_rk_tiles(ev)) for ev in evs}
        tiles = at + [t for ev in evs for t in _rk_tiles(ev) if t not in at]
        seen = set()
        for tile in tiles:
            if tile in seen:
                continue
            seen.add(tile)
            tile_best = None                      # EvaluateInternal : argmax CIBLE, keep-first
            for ev in evs:
                tgt = ev.get("targetId")
                if tile not in legal[tgt]:
                    continue
                cand = gen._action_utility(ctx, pb, ab, tgt, tile)
                if cand is None:
                    continue
                if tile_best is None or cand[0] > tile_best[0]:
                    tile_best = (cand[0], cand[2], tgt)
            if tile_best is None:
                continue
            if best_key is None or tile_best[0] > best_key:   # Bucket.Merge -> AddAction
                best = (tile_best[1], tile_best[0], tile_best[2], ab, tile)
                best_key = tile_best[0]
    return best


def _tie_width(ctx, gen, best):
    """Nombre de tuiles d'`action_tiles` atteignant l'utilite d'action MAXIMALE, pour l'ability
    et la cible retenues. > 1 => l'ordre DECIDE."""
    if best is None:
        return 0, None
    _, u_action, tgt, ab, _ = best
    pb = _pb(ctx, ab)
    ev = next((e for e in _evals(ctx)
               if e.get("abilityId") == ab and e.get("targetId") == tgt), None)
    if ev is None:
        return 0, None
    legal = set(_rk_tiles(ev))
    hits = []
    for tile in (ctx.action_tiles or []):
        if tile not in legal:
            continue
        cand = gen._action_utility(ctx, pb, ab, tgt, tile)
        if cand is not None and abs(cand[0] - u_action) < 1e-9:
            hits.append(tile)
    return len(hits), hits


def _decompose(ctx, gen, ab, tgt):
    """DECOMPOSITION PAR ETAGE d'une paire (ability, cible) : pour CHAQUE tuile candidate, ce que
    le NATIF en dit (`ranked` = `IdunBattle.Core.Services.AttackQuery$$GetBestTileToAttackFrom` +
    oracle playbook `MakeDamagePredictions`, rang COMPRIS) face a ce que le PORT en calcule. C'est
    la seule facon de distinguer " ordre de sweep " de " utilite par tuile fausse "."""
    ev = next((e for e in _evals(ctx)
               if e.get("abilityId") == ab and e.get("targetId") == tgt), None)
    if ev is None:
        return []
    pb = _pb(ctx, ab)
    out = []
    for rank, rk in enumerate(ev.get("ranked") or []):
        tile = (rk.get("col"), rk.get("row"))
        if tile[0] is None:
            continue
        cand = gen._action_utility(ctx, pb, ab, tgt, tile)
        pred = (cand[3] or {}) if cand else {}
        out.append({
            "tile": tile, "natRank": rank,
            "natDmgMin": rk.get("dmgMin"), "natDmgMax": rk.get("dmgMax"),
            "natKillSure": rk.get("killSure"), "natKill": rk.get("kill"),
            "elev": (ctx.elev_by_pos or {}).get(tile),
            "portU": None if cand is None else round(cand[2], 4),
            "portUfull": None if cand is None else round(cand[1], 4),
            "portUact": None if cand is None else round(cand[0], 4),
            "portDmgMin": pred.get("healthDmgMin"), "portDmgMax": pred.get("healthDmgMax"),
        })
    return out


# ------------------------------------------------------------------- run


def run(sid, rid, steps):
    wt = W.load()
    rows = []
    gen = AG.ComparableAbilityGenerator()

    def probe(step, uid, dv, mov_by_unit, nat, eng, predictor):
        ctx = _ai_ctx.build(lambda m, b, t: _r(sid, m, b, t), rid, dv, mov_by_unit,
                            uid, wt, predictor)
        order_action = _action_order_for(ctx)
        s_rank = _sweep_pair(ctx, gen, _rank_order)
        s_pair_act = _sweep_pair(ctx, gen, order_action)
        s_native = _sweep_ab_tile_tgt(ctx, gen)
        nat_tile = nat["move"]["to"] if nat["move"] else ctx.origin
        if isinstance(nat_tile, dict):
            nat_tile = (nat_tile.get("col"), nat_tile.get("row"))
        nw, nhits = _tie_width(ctx, gen, s_native)
        # decomposition par etage : sur les pas ou l'ordre POURRAIT decider (tie) ou ou les
        # structures divergent, on veut le detail natif/port par tuile.
        deco = None
        if nw > 1 or len({str(s_rank), str(s_pair_act), str(s_native)}) > 1:
            ref = s_native or s_rank
            if ref is not None:
                deco = _decompose(ctx, gen, ref[3], ref[2])
        # divergence d'ORDRE-SOURCE : ranked (union, 1re apparition) vs action_tiles
        seen, ranked_union = set(), []
        for ev in _evals(ctx):
            for t in _rk_tiles(ev):
                if t not in seen:
                    seen.add(t)
                    ranked_union.append(t)
        at_restricted = [t for t in (ctx.action_tiles or []) if t in seen]
        rows.append({
            "step": step, "uid": uid, "origin": ctx.origin,
            "nMov": len(ctx.move_tiles or []),
            "natTile": nat_tile,
            "natAb": (nat["ability"]["ability"], nat["ability"]["target"]) if nat["ability"] else None,
            "natMoved": bool(nat["move"]),
            "orderDiffers": at_restricted != ranked_union,
            "actionTiles": list(ctx.action_tiles or [])[:14],
            "rankedUnion": ranked_union[:14],
            "pair_rank": _fmt(s_rank),
            "pair_action": _fmt(s_pair_act),
            "ab_tile_tgt": _fmt(s_native),
            "tieWidth": nw, "tieTiles": nhits, "deco": deco,
        })

    res = EV.run_agreement(sid, rid, steps, wt, probe=probe)

    print("\n===== (A) ORDRE-SOURCE : `ranked` vs `action_tiles` =====")
    diff = [r for r in rows if r["orderDiffers"]]
    print(f"  pas sondes : {len(rows)} | ordre `ranked` != ordre `action_tiles` : {len(diff)}")
    if not diff:
        print("  !! AUCUNE divergence d'ordre sur ce couple -> IL NE CONCLUT RIEN, refaire le montage")

    print("\n===== (B) TROIS STRUCTURES DE SWEEP vs NATIF =====")
    with_ab = [r for r in rows if r["natAb"]]

    def _agree(r, k):
        b = r[k]
        if b is None or r["natAb"] is None:
            return False
        return (b[0], b[1]) == (r["natAb"][0], r["natAb"][1]) and b[2] == r["natTile"]
    for k in ("pair_rank", "pair_action", "ab_tile_tgt"):
        n = sum(1 for r in with_ab if _agree(r, k))
        print(f"  {k:12} : (ability,cible,tuile) == natif sur {n}/{len(with_ab)} chunks d'ability")
    disc = [r for r in rows if len({str(r["pair_rank"]), str(r["pair_action"]),
                                    str(r["ab_tile_tgt"])}) > 1]
    print(f"  pas ou les 3 structures DIVERGENT entre elles : {len(disc)}")
    for r in disc:
        print(f"    step {r['step']:2} u{r['uid']} origin={r['origin']} nMov={r['nMov']} "
              f"natAb={r['natAb']} natTile={r['natTile']} (moved={r['natMoved']})")
        print(f"      pair_rank   = {r['pair_rank']}")
        print(f"      pair_action = {r['pair_action']}")
        print(f"      ab_tile_tgt = {r['ab_tile_tgt']}")
        print(f"      action_tiles[:14] = {r['actionTiles']}")
        print(f"      rankedUnion[:14]  = {r['rankedUnion']}")

    print("\n===== (C) TIES (structure MIRROR) =====")
    ties = [r for r in rows if r["tieWidth"] > 1]
    print(f"  pas avec >1 tuile a l'utilite MAX : {len(ties)}/{len(rows)}")
    for r in ties:
        print(f"    step {r['step']:2} u{r['uid']} ab_tile_tgt={r['ab_tile_tgt']} "
              f"tuiles a egalite={r['tieTiles']} natTile={r['natTile']}")
    if not ties:
        print("  !! AUCUN tie -> ce couple ne DEPARTAGE pas les ordres, refaire le montage")

    print("\n===== (C2) DECOMPOSITION PAR ETAGE (natif `ranked` vs port, par tuile) =====")
    for r in rows:
        if not r["deco"]:
            continue
        print(f"  step {r['step']:2} u{r['uid']} natTile={r['natTile']} natAb={r['natAb']} "
              f"origin={r['origin']}")
        print("    tile      natRank natDmg[min,max] K! K? elev | portU     portUfull portUact  "
              "portDmg[min,max]")
        for d in r["deco"]:
            print(f"    {str(d['tile']):9} {d['natRank']:^7} "
                  f"[{d['natDmgMin']},{d['natDmgMax']}] "
                  f"{int(bool(d['natKillSure']))}  {int(bool(d['natKill']))}  "
                  f"{d['elev']} | {str(d['portU']):9} {str(d['portUfull']):9} "
                  f"{str(d['portUact']):9} [{d['portDmgMin']},{d['portDmgMax']}]")

    print("\n===== (D) AGREEMENT (harnais standard) =====")
    p, a = res["pos"], res["ability"]
    if p["n"]:
        print(f"  positioning : exact {p['exact']}/{p['n']} | <=1hex {p['near']}/{p['n']}")
    if a["n"]:
        print(f"  ability     : {a['match']}/{a['n']}")
    st = res.get("stay") or {}
    if st.get("n"):
        print(f"  stay        : {st['match']}/{st['n']}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--seed", default="999")
    ap.add_argument("--board", default="C4_09")
    ap.add_argument("--steps", type=int, default=26)
    ap.add_argument("--extra", nargs=argparse.REMAINDER, default=[])
    args = ap.parse_args()
    sid = _resolve_session()
    if args.runner is not None:
        print(f"runner {args.runner} (existant, non dispose)")
        return run(sid, args.runner, args.steps)
    rid, state = _build(args.seed, args.board, args.extra)
    if rid is None:
        return 1
    print(f"runner {rid} seed={args.seed} board={args.board} steps={args.steps}")
    try:
        return run(sid, rid, args.steps)
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        try:
            state.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
