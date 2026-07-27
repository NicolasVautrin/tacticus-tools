#!/usr/bin/env python
"""Probe R1 -- la tuile d'ORIGINE dans les positions candidates d'ACTION.

QUESTION BINAIRE : pour une unite qui attaquerait sans bouger, le port propose-t-il la MEME
tuile d'action que le natif ?

Ce que la probe MESURE, par etage, sur une trajectoire NATIVE reelle (`aiStepDryRun` marche par
`engine_validate.run_agreement`) :

  (A) INVARIANT NATIF -- la falsification de la RE. La chaine native
      (`DefaultAiUnitTactic.<CalculateNextActionForUnit>d__5` -> `ABaseAiUnitTactic$$GenerateActionTiles`
      -> `IBattleQuery`+0xe = `BattleQuery$$GetCurrentAndMovablePositionsFor`) predit :
        * l'ensemble candidat = {position COURANTE} UNION movable -> la destination d'un chunk natif
          est TOUJOURS dans `{origine} + aiMovableTiles`, et un chunk SANS move (= reste sur place)
          est LEGAL meme quand le movable est NON vide ;
        * `aiMovableTiles` (= `GetMovableTilesFor` brut) ne contient JAMAIS la tuile courante --
          c'est l'union du natif qui l'ajoute.
      La sous-mesure `ability SANS move + movable non vide` REFUTE l'hypothese inverse (« le natif
      n'evalue l'origine que si tiles.Count == 0 ») : si elle est > 0, cette hypothese est FAUSSE.

  (B) EFFET DE L'ORDRE DE SWEEP -- pour chaque pas compare, l'argmax d'attaque du port est recalcule
      avec TROIS ordres de position, meme ensemble candidat :
        * `origin_first` = `ctx.action_tiles` (ordre NATIF livre : courante en tete) ;
        * `origin_last`  = tuiles de move puis origine (ce que produisait `_plans_for_unit`) ;
        * `rank_order`   = ordre `ranked` du plan (ce que balayait `_best_attack` cote LIVE).
      Le tie-break etant keep-first (`Bucket$$AddAction`, `>` strict), l'ordre decide a utilite EGALE.

  (C) CRITERE R1 -- « natif reste sur place, port aussi ? » : compte les chunks ou le natif n'emet
      AUCUN `MoveUnitMessage` et ou le port propose quand meme un deplacement (angle mort de
      `run_agreement`, qui ne compare la position QUE si le natif a bouge).

  (D) AGREEMENT -- les compteurs `run_agreement` (position exacte / <=1hex, ability) de la passe.

Runner : `--runner <id>` (existant, NON dispose) ou build dedie `--seed`/`--board` (dispose en fin).
ASCII only. Usage :
  python probe_r1_origin_action_tile.py --seed 777 --board MC1_67 --steps 24
  python probe_r1_origin_action_tile.py --runner 42 --steps 24
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
from engine.ai import context as _ai_ctx  # noqa: E402
from engine.ai.action_generators import ComparableAbilityGenerator  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(seed, board, extra):
    """Runner dedie -> (rid, state_path). (None, None) si le build echoue."""
    state = ROOT / "logs" / "runners" / f"probeR1-{uuid.uuid4().hex[:8]}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--board", board, "--state-file", str(state)] + list(extra or [])
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO:", (p.stderr or p.stdout or "")[-400:])
        return None, None
    return json.loads(state.read_text())["runnerId"], state


def _rank_order_tiles(ctx):
    """Tuiles `ranked` du plan de `ctx.uid`, dans l'ordre de premiere apparition = l'ordre que
    `_best_attack` balayait AVANT (rang `GetBestTileToAttackFrom` cote hook)."""
    out = []
    seen = set()
    for ev in ((ctx.plans.get(ctx.uid) or {}).get("evals") or []):
        for rk in (ev.get("ranked") or []):
            t = (rk.get("col"), rk.get("row"))
            if t[0] is not None and t not in seen:
                seen.add(t)
                out.append(t)
    return out


def _origin_last_tiles(ctx):
    """Tuiles de move puis ORIGINE en dernier = l'ordre produit par `_plans_for_unit` (offline)."""
    return [t for t in ctx.action_tiles if t != ctx.origin] + \
        ([ctx.origin] if ctx.origin is not None else [])


def _argmax_attack(ctx, tiles):
    """`ComparableAbilityGenerator._best_attack` evalue avec `tiles` comme positions candidates.
    Renvoie (u, u_action, target, ability, tile) ou None."""
    saved = ctx.action_tiles
    ctx.action_tiles = list(tiles)
    try:
        return ComparableAbilityGenerator()._best_attack(ctx)
    finally:
        ctx.action_tiles = saved


def run(sid, rid, steps):
    wt = W.load()
    rows = []

    def probe(step, uid, dv, mov_by_unit, nat, eng, predictor):
        mov = (mov_by_unit.get(uid) or {}).get("tiles") or []
        movset = {(t["col"], t["row"]) for t in mov}
        me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
        mpos = ((me or {}).get("pos") or {})
        origin = (mpos["col"], mpos["row"]) if mpos.get("col") is not None else None
        ctx = _ai_ctx.build(lambda m, b, t: _r(sid, m, b, t), rid, dv, mov_by_unit,
                            uid, wt, predictor)

        def _fmt(b):
            return None if b is None else (b[3], b[2], b[4], round(b[1], 3))
        rows.append({
            "step": step, "uid": uid, "origin": origin,
            "nMov": len(movset), "originInMov": origin in movset,
            "natMove": nat["move"]["to"] if nat["move"] else None,
            "natAb": (nat["ability"]["ability"], nat["ability"]["target"]) if nat["ability"] else None,
            "natMoveInMov": (nat["move"]["to"] in movset) if nat["move"] else None,
            "engKind": eng.get("kind"), "engTo": eng.get("to"),
            "origin_first": _fmt(_argmax_attack(ctx, ctx.action_tiles)),
            "origin_last": _fmt(_argmax_attack(ctx, _origin_last_tiles(ctx))),
            "rank_order": _fmt(_argmax_attack(ctx, _rank_order_tiles(ctx))),
        })

    res = EV.run_agreement(sid, rid, steps, wt, probe=probe)

    print("\n===== (A) INVARIANT NATIF =====")
    ab_only = [r for r in rows if r["natAb"] and not r["natMove"]]
    stay_with_moves = [r for r in ab_only if r["nMov"] > 0]
    moved = [r for r in rows if r["natMove"]]
    bad_dest = [r for r in moved if not r["natMoveInMov"]]
    origin_in_mov = [r for r in rows if r["originInMov"]]
    print(f"  chunks natifs ability SANS move : {len(ab_only)} "
          f"-> dont movable NON vide : {len(stay_with_moves)}")
    for r in stay_with_moves:
        print(f"    step {r['step']:2} u{r['uid']} origin={r['origin']} nMov={r['nMov']} "
              f"natAb={r['natAb']}")
    print(f"  chunks natifs AVEC move        : {len(moved)} "
          f"-> destination hors movable (violation) : {len(bad_dest)}")
    for r in bad_dest:
        print(f"    step {r['step']:2} u{r['uid']} natMove={r['natMove']} nMov={r['nMov']}")
    print(f"  origine PRESENTE dans aiMovableTiles : {len(origin_in_mov)}/{len(rows)} "
          f"(attendu 0 -- GetMovableTilesFor exclut la tuile courante ; c'est l'UNION"
          f" de GetCurrentAndMovablePositionsFor qui la remet)")
    print(f"  => hypothese « origine candidate SEULEMENT si tiles.Count == 0 » : "
          f"{'REFUTEE (' + str(len(stay_with_moves)) + ' contre-exemples)' if stay_with_moves else 'non refutee ici'}")
    print(f"  => destination natale toujours dans {{origine}} + movable : "
          f"{'OK' if not bad_dest else 'VIOLE'}")

    print("\n===== (B) EFFET DE L'ORDRE DE SWEEP (meme ensemble, 3 ordres) =====")
    d_last = [r for r in rows if r["origin_first"] != r["origin_last"]]
    d_rank = [r for r in rows if r["origin_first"] != r["rank_order"]]
    print(f"  pas compares : {len(rows)}")
    print(f"  origin_first != origin_last : {len(d_last)}   (l'ordre offline `_plans_for_unit`)")
    print(f"  origin_first != rank_order  : {len(d_rank)}   (l'ordre LIVE `ranked` d'avant)")
    for r in sorted({id(x): x for x in (d_last + d_rank)}.values(), key=lambda x: x["step"]):
        print(f"    step {r['step']:2} u{r['uid']} origin={r['origin']} nMov={r['nMov']}")
        print(f"      origin_first (ab,tgt,tile,u) = {r['origin_first']}")
        print(f"      origin_last                  = {r['origin_last']}")
        print(f"      rank_order                   = {r['rank_order']}")
        print(f"      natif move={r['natMove']} ability={r['natAb']} | "
              f"engine {r['engKind']} to={r['engTo']}")

    print("\n===== (C) CRITERE R1 : natif reste sur place, port aussi ? =====")
    bad_stay = [r for r in ab_only if r["engTo"] is not None and r["engTo"] != r["origin"]]
    print(f"  chunks natifs SANS move : {len(ab_only)} | port propose quand meme un move : "
          f"{len(bad_stay)}")
    for r in bad_stay:
        print(f"    step {r['step']:2} u{r['uid']} origin={r['origin']} engTo={r['engTo']} "
              f"natAb={r['natAb']} engKind={r['engKind']}")
    print(f"  VERDICT (C) : {'OK' if not bad_stay else 'DIVERGENT'}")

    print("\n===== (D) AGREEMENT =====")
    p, a = res["pos"], res["ability"]
    if p["n"]:
        print(f"  positioning : exact {p['exact']}/{p['n']} ({100 * p['exact'] // p['n']}%) "
              f"| <=1hex {p['near']}/{p['n']} ({100 * p['near'] // p['n']}%)")
    else:
        print("  positioning : aucun move compare")
    if a["n"]:
        print(f"  ability     : {a['match']}/{a['n']} ({100 * a['match'] // a['n']}%)")
    else:
        print("  ability     : aucun cast compare")
    st = res.get("stay") or {}
    if st.get("n"):
        print(f"  stay        : {st['match']}/{st['n']} ({100 * st['match'] // st['n']}%) "
              f"(natif sur place -> port sur place)")
    return 0 if not (bad_dest or origin_in_mov or bad_stay) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--steps", type=int, default=24)
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
