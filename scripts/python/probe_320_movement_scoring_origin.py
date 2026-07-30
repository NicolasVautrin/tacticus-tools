#!/usr/bin/env python
"""probe_320_movement_scoring_origin -- MONTAGE NOMME de l'etage `scoring` du mouvement : la
TUILE COURANTE est-elle dans le candidate-set du port ?

QUESTION BINAIRE
----------------
Sur un pas ou le natif n'emet AUCUN `MoveUnitMessage` (il finit le tour, ou il caste sans bouger),
le port choisit-il la MEME tuile de destination que le natif -- c'est-a-dire la tuile COURANTE ?

CE QUE LE DECOMPILE DIT (build `rnca9r7q6c`, lu de premiere main)
----------------------------------------------------------------
1. `IdunBattle.AI.ActionGenerators.MovementActionGenerator$$GenerateActions(unit, startPosition,
   positions, overrideUtility)` range ses arguments dans l'iterateur :
   `d__6+0x38 = unit`, `+0x20 = startPosition`, `+0x40 = positions`, `+0x28 = overrideUtility`.
2. `...MovementActionGenerator.u003CGenerateActionsu003Ed__6$$MoveNext` construit UN
   `IdunBattle.AI.Utilities.UtilityMovementCase(unit, pos, closestEnemy, null, null, null)` PAR
   position de `+0x40`, puis appelle le chooser `<generator+0x28>` avec `(cases, utilityDefinition)`.
   `utilityDefinition` = `new UtilityDefinition(TileExtensions.IsTemporary(mainTile) ? 5 : 6)`.
3. `positions` vient de `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles`, qui appelle
   le slot `+0xe` de l'`IBattleQuery` = `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor` :

       var set = new OrderedSet<UnitPosition>(EntityExtensions.GetUnitPosition(unit, this._state));
       set.UnionWith(this._movementQuery.GetMovablePositionsFor(unit, ignoreUnitFlags, options));
       return set;

   => la position **COURANTE** est la GRAINE de l'`OrderedSet`, donc **le PREMIER element enumere**,
   et les tuiles de `GetMovableTilesFor` (qui, elles, l'excluent) viennent apres.
4. Le chooser est `IdunBattleLogic.AI.Utilities.UtilityDecider` (construit par
   `IdunBattle.AI.ActionGenerators.MovementActionGenerator$$.ctor` a `generator+0x28`). Son argmax
   est dans `IdunBattleLogic.AI.Utilities.UtilityDecider.u003CCalculateUtilitiesForCasesEnumeratedu003Ed__7u003Cobjectu003E$$MoveNext` :

       v = utilities[i] + leafResult;  utilities[i] = v;
       if (Fix64.op_GreaterThan(v, bestUtility)) { second = best; secondUtility = bestUtility;
                                                   best = case;  bestUtility = v; }
       else if (Fix64.op_GreaterThan(v, secondUtility)) { second = case; secondUtility = v; }

   `op_GreaterThan` est **STRICT** => **KEEP-FIRST a egalite**. Combine avec (3) : **a utilite
   EGALE, le natif RESTE SUR PLACE**, et il ne bouge que sur un gain STRICT.

CE QUE LE PORT FAISAIT
----------------------
`engine.ai.action_generators.MovementActionGenerator.generate` passait `ctx.move_tiles`
(= RPC `aiMovableTiles` = `GetMovableTilesFor`, qui EXCLUT la tuile courante) a
`engine.move.best_move_faithful`. Le candidate-set du port etait donc AMPUTE de la seule tuile que
le natif evalue en PREMIER -- « rester sur place » n'etait pas representable. Toutes les donnees
etaient pourtant deja la : `pathDistToEnemies` renvoie explicitement la tuile courante
(« Tuiles atteignables (GetMovableTilesFor) + tuile COURANTE »), `tileMeta` couvre le board entier.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_320_movement_scoring_origin.py                 # montage nomme, DEUX bras
    python probe_320_movement_scoring_origin.py --table         # table par FEUILLE sur le pas cible
    python probe_320_movement_scoring_origin.py --seed 4242     # second cas discriminant
    python probe_320_movement_scoring_origin.py --noreg         # non-regression par MUTATION
    python probe_320_movement_scoring_origin.py --scan 777,909  # choisir un montage, sur MESURE

ASCII only (cp1252). Sorties dans logs/ (chemin RELATIF). Dispose SES runners.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc            # noqa: E402

BOARD = "C1_12"
SEED = 12100
RANK = 17
STEPS = 12
TARGET_STEP = 8
TARGET_UID = 79


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, seed: int, board: str) -> int:
    """Runner ISOLE au roster tire par la SEED (pas de `--p-units`) : le montage nomme est le
    couple (board, seed), reproductible tel quel."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(state_file), "--board", board, "--rank", str(RANK)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-500:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _origin_of(dv, uid):
    row = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
    p = (row or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _native_chunk(action: dict) -> dict:
    import engine_validate as EV
    return EV.native_chunk(action or {})


def _apply_native(sid, rid, messages) -> None:
    acts = []
    for m in (messages or []):
        cls = m.get("cls")
        if cls == "MoveUnitMessage":
            acts.append({"kind": "move", "unitId": m["unitId"],
                         "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
        elif cls == "ActiveAbilityMessage":
            acts.append({"kind": "ability", "casterId": m["casterId"],
                         "targetId": m.get("targetId"), "abilityType": m["abilityType"]})
        elif cls == "FinishUnitTurnMessage":
            acts.append({"kind": "finish", "unitId": m["unitId"]})
    if acts:
        _r(sid, "applyAction", {"runnerId": rid, "actions": acts}, 40)


def leaf_table(ctx, positions) -> list:
    """DECOMPOSITION PAR FEUILLE du composite `UnitMovement(6) = Tile(7) + MinDistanceToClosestEnemy(17)`
    sur les positions donnees. Rend une ligne par tuile : chaque feuille de Tile(7) qui n'est pas
    muette, le terme MinDist, et le total. C'est la lecture qui permet de dire QUELLE feuille
    departage -- et donc de ne JAMAIS fitter un scalaire."""
    from engine.utilities.tile import (TILE_UTILITY, apply_tile_attributes, terrain_tile_effects,
                                       tile_leaf_ctx)
    from engine.utilities.move import MIN_DIST_UTILITY

    leaf_ctx = tile_leaf_ctx(ctx)
    board_elevs = [e for e in ctx.elev_by_pos.values() if e is not None]
    emax, emin = (max(board_elevs), min(board_elevs)) if board_elevs else (None, None)
    epos = ctx.tgt_epos or ctx.epos
    rows = []
    for c in positions:
        e = ctx.elev_by_pos.get(c)
        meta: dict = {"elevation": e, "elevation_max": emax, "elevation_min": emin} \
            if e is not None else {}
        if ctx.is_temporary_by_pos and c in ctx.is_temporary_by_pos:
            meta["is_temporary"] = ctx.is_temporary_by_pos[c]
        _effs = list((ctx.effects_by_pos or {}).get(c) or [])
        if ctx.terrain_by_pos:
            _effs += terrain_tile_effects(ctx.terrain_by_pos.get(c), _effs)
        if _effs:
            meta["effects"] = _effs
        apply_tile_attributes(meta, c, leaf_ctx)
        per_leaf = {}
        for child in TILE_UTILITY.children:
            v = child.evaluate(c, meta, leaf_ctx or {}, ctx.wt)
            if v:
                per_leaf[type(child).__name__] = round(float(v), 4)
        tile_u = float(sum(per_leaf.values()))
        md = MIN_DIST_UTILITY.evaluate_movement(c, epos, ctx.wt, ctx.pathdist_by_pos,
                                                case=ctx.mindist_case)
        rows.append({"pos": c, "leaves": per_leaf, "tile": round(tile_u, 4),
                     "mindist": round(float(md), 4), "total": round(tile_u + float(md), 4),
                     "pathdist": (ctx.pathdist_by_pos or {}).get(c)})
    return rows


def _build_ctx(sid, rid, dv, mov_by_unit, uid, wt, predictor):
    from engine.ai import context as _ai_ctx
    return _ai_ctx.build(lambda m, b, t: _r(sid, m, b, t), rid, dv, mov_by_unit, uid, wt, predictor)


_NEUTRAL = (lambda ctx: [{"col": t["col"], "row": t["row"]} for t in (ctx.move_tiles or [])])
"""CONTRE-EPREUVE : le candidate-set d'AVANT #320 -- `GetMovableTilesFor` SEUL, sans la tuile
courante. Sans ce bras, « le port reste sur place » pourrait venir de n'importe ou et la garde
serait VIDE."""


def _decide(sid, rid, dv, mov_by_unit, uid, wt, predictor, positions_fn):
    """Une decision du port avec le candidate-set `positions_fn`. `engine_decide` est PUR (RPC
    read-only, aucune mutation du runner) -> les DEUX bras se jouent sur le MEME etat, avec UN seul
    runner. C'est ce qui rend la comparaison exacte : deux runners « identiques » ne le sont qu'a la
    seed pres."""
    import engine_validate as EV
    from engine.ai import action_generators as AG
    orig = AG.movement_candidate_positions
    AG.movement_candidate_positions = positions_fn
    try:
        return EV.engine_decide(sid, rid, dv, mov_by_unit, uid, wt, predictor)
    finally:
        AG.movement_candidate_positions = orig


def walk(sid, rid, steps: int, verbose: bool = True, table_at: "int | None" = None) -> dict:
    """Marche la trajectoire NATIVE et confronte le CHOIX DE TUILE du port sur TOUS les pas ou le
    natif decide (qu'il bouge ou non), **dans les DEUX bras a la fois** (meme etat exact)."""
    from engine.ai import action_generators as AG
    from engine import weights
    from engine.playbook import scene as _scene
    import hexgeo

    wt = weights.load()
    predictor = _scene.build_predictor(lambda m, b, t: _r(sid, m, b, t), rid)
    cable_fn = AG.movement_candidate_positions
    rows: list = []
    tables: list = []
    for step in range(steps):
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 40)
        if not dry.get("ok") or not dry.get("hasNext"):
            break
        act = dry.get("action") or {}
        nat = _native_chunk(act)
        uid = dry.get("activatedUnitId") or nat.get("unit")
        if uid is not None and (nat["move"] or nat["ability"] or nat["finish"]):
            dv = _r(sid, "decisionView",
                    {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
            mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
            mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
            if predictor is not None:
                _scene.refresh_shields(predictor, lambda m, b, t: _r(sid, m, b, t), rid)
            origin = _origin_of(dv, uid)
            eng = _decide(sid, rid, dv, mov_by_unit, uid, wt, predictor, cable_fn)
            neu = _decide(sid, rid, dv, mov_by_unit, uid, wt, predictor, _NEUTRAL)
            # La tuile que le NATIF a retenue : celle du MoveUnitMessage s'il y en a un, sinon
            # -- `InputBuilder` n'emet rien pour une destination == tuile courante -- l'ORIGINE.
            nat_to = nat["move"]["to"] if nat["move"] else origin
            eng_to = eng.get("to") if eng.get("to") is not None else origin
            neu_to = neu.get("to") if neu.get("to") is not None else origin
            d = (hexgeo.distance(eng_to, nat_to)
                 if (eng_to is not None and nat_to is not None) else None)
            dn = (hexgeo.distance(neu_to, nat_to)
                  if (neu_to is not None and nat_to is not None) else None)
            row = {"step": step, "uid": uid, "origin": origin,
                   "nat_kind": ("move" if nat["move"] else
                                ("ability" if nat["ability"] else "finish")),
                   "nat_to": nat_to, "eng_kind": eng.get("kind"), "eng_to": eng_to,
                   "neu_kind": neu.get("kind"), "neu_to": neu_to,
                   "movable": len((mov_by_unit.get(uid) or {}).get("tiles") or []),
                   "same_tile": (d == 0), "neu_same_tile": (dn == 0), "dist": d,
                   "stay_native": (not nat["move"])}
            row["discriminant"] = row["same_tile"] != row["neu_same_tile"]
            # LE DEFAUT DE #320, NOMME : le natif ne bouge pas, et le port propose un DEPLACEMENT
            # REEL vers une autre tuile. C'est l'etage `scoring` -- il exclut l'etage `ability`
            # (le port caste), qui est un AUTRE defaut et doit rester visible ailleurs.
            row["scoring_miss"] = (row["stay_native"] and row["eng_kind"] == "move"
                                   and not row["same_tile"])
            row["neu_scoring_miss"] = (row["stay_native"] and row["neu_kind"] == "move"
                                       and not row["neu_same_tile"])
            rows.append(row)
            if verbose:
                print("  step %2d u%s: natif=%-7s to=%s | CABLE=%-7s to=%s [%s] | "
                      "NEUTRE=%-7s to=%s [%s] mov=%d%s"
                      % (step, uid, row["nat_kind"], nat_to, row["eng_kind"], eng_to,
                         "SAME" if row["same_tile"] else "DIFF", row["neu_kind"], neu_to,
                         "SAME" if row["neu_same_tile"] else "DIFF", row["movable"],
                         "  <== DISCRIMINANT" if row["discriminant"] else ""))
            if table_at is not None and step == table_at:
                ctx = _build_ctx(sid, rid, dv, mov_by_unit, uid, wt, predictor)
                pos = [(t["col"], t["row"]) for t in cable_fn(ctx)]
                tables.append({"step": step, "uid": uid, "origin": origin,
                               "rows": leaf_table(ctx, pos)})
        _apply_native(sid, rid, act.get("messages"))
    stay = [r for r in rows if r["stay_native"]]
    moved = [r for r in rows if not r["stay_native"]]
    # VENTILATION DES PAS DISCRIMINANTS. `fixed` = le correctif fait ce qu'il annonce ; `broken` =
    # il CASSE un pas que le port d'avant avait juste. Les deux comptes doivent etre lus : un lot ou
    # `fixed` et `broken` se compensent laisserait un total d'accord flatteur et un port PIRE.
    fixed = [r for r in rows if r["discriminant"] and r["same_tile"]]
    broken = [r for r in rows if r["discriminant"] and not r["same_tile"]]
    def _tag(r):
        return {"step": r["step"], "uid": r["uid"], "origin": r["origin"],
                "nat_to": r["nat_to"], "cable_to": r["eng_to"], "neutre_to": r["neu_to"]}
    return {"rows": rows, "tables": tables,
            "n": len(rows),
            "fixed": [_tag(r) for r in fixed], "broken": [_tag(r) for r in broken],
            "scoring_miss": [_tag(r) for r in rows if r["scoring_miss"]],
            "neu_scoring_miss": [_tag(r) for r in rows if r["neu_scoring_miss"]],
            "discriminant": [(r["step"], r["uid"], r["origin"], r["nat_to"], r["neu_to"])
                             for r in rows if r["discriminant"]],
            "stay": {"n": len(stay), "same": sum(1 for r in stay if r["same_tile"]),
                     "neu_same": sum(1 for r in stay if r["neu_same_tile"])},
            "moved": {"n": len(moved), "same": sum(1 for r in moved if r["same_tile"]),
                      "neu_same": sum(1 for r in moved if r["neu_same_tile"])}}


def noreg(sid, rid, steps: int, cable: bool, verbose: bool = True) -> dict:
    """NON-REGRESSION PAR MUTATION. Rejoue le walk d'agreement de reference
    (`engine_validate.run_agreement`) avec le candidate-set CABLE (origine incluse) puis NEUTRALISE.
    Les metriques `pos`/`ability`/`stay` sont rapportees telles quelles : ce bras dit ce que le
    correctif DEPLACE, il ne l'excuse pas."""
    import engine_validate as EV
    from engine.ai import action_generators as AG
    from engine import weights

    orig = AG.movement_candidate_positions
    if not cable:
        AG.movement_candidate_positions = (
            lambda ctx: [{"col": t["col"], "row": t["row"]} for t in (ctx.move_tiles or [])])
    try:
        res = EV.run_agreement(sid, rid, steps, weights.load(),
                               log=(print if verbose else (lambda *_a, **_k: None)))
    finally:
        AG.movement_candidate_positions = orig
    return {"pos": res["pos"], "ability": res["ability"], "stay": res["stay"]}


def run(seed: int = SEED, board: str = BOARD, steps: int = STEPS, keep: bool = False,
        verbose: bool = True, table_at=None) -> dict:
    """Monte UN runner, marche, mesure LES DEUX BRAS a chaque pas (meme etat exact)."""
    sid = _resolve_session()
    out: dict = {"seed": seed, "board": board, "steps": steps}
    rid = None
    try:
        rid = _build(ROOT / "logs" / ("probe_320_%s_%d.json" % (board, seed)), seed, board)
        if verbose:
            print("[320] runner=%d seed=%d board=%s -- CABLE (origine dans le candidate-set) "
                  "vs NEUTRE (le port d'AVANT)" % (rid, seed, board))
        out["walk"] = walk(sid, rid, steps, verbose=verbose, table_at=table_at)
        return out
    except RuntimeError as exc:
        return {"error": str(exc), "seed": seed, "board": board}
    finally:
        if rid is not None and not keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)


def run_noreg(seed: int = SEED, board: str = BOARD, steps: int = STEPS,
              keep: bool = False, verbose: bool = True) -> dict:
    sid = _resolve_session()
    rids: list = []
    try:
        a = _build(ROOT / "logs" / ("probe_320_nr_%s_%d_a.json" % (board, seed)), seed, board)
        rids.append(a)
        with_fix = noreg(sid, a, steps, cable=True, verbose=verbose)
        b = _build(ROOT / "logs" / ("probe_320_nr_%s_%d_b.json" % (board, seed)), seed, board)
        rids.append(b)
        without = noreg(sid, b, steps, cable=False, verbose=verbose)
        return {"seed": seed, "board": board, "steps": steps,
                "with_fix": with_fix, "without_fix": without}
    except RuntimeError as exc:
        return {"error": str(exc), "seed": seed, "board": board}
    finally:
        if not keep:
            for rid in rids:
                _r(sid, "disposeRunner", {"runnerId": rid}, 30)


def scan(seeds, board: str, steps: int, verbose: bool = True) -> list:
    """Balaie des couples (board, seed) et rend, pour chacun, le nombre de pas ou le natif NE BOUGE
    PAS et le nombre d'accords du port sur la tuile. Sert a CHOISIR un second cas discriminant sur
    MESURE (un lot ou les deux bras donnent le meme resultat ne conclut RIEN)."""
    sid = _resolve_session()
    out = []
    for seed in seeds:
        rid = None
        try:
            rid = _build(ROOT / "logs" / ("probe_320_scan_%s_%d.json" % (board, seed)), seed, board)
            w = walk(sid, rid, steps, verbose=False)
            row = {"board": board, "seed": seed, "n": w["n"],
                   "stay": w["stay"], "moved": w["moved"], "disc": w["discriminant"]}
            out.append(row)
            if verbose:
                print("  %-8s seed %-6d : pas=%d | natif SUR PLACE %s | natif BOUGE %s"
                      % (board, seed, row["n"], row["stay"], row["moved"]))
                print("      pas DISCRIMINANTS (cable != neutre) : %s" % (row["disc"] or "aucun"))
        except RuntimeError as exc:
            if verbose:
                print("  %-8s seed %-6d : MONTAGE KO (%s)" % (board, seed, exc))
        finally:
            if rid is not None:
                _r(sid, "disposeRunner", {"runnerId": rid}, 30)
    return out


def _print_table(t: dict) -> None:
    print("\n  --- TABLE PAR FEUILLE, step %d u%s (origine %s) ---" % (t["step"], t["uid"],
                                                                      t["origin"]))
    rows = sorted(t["rows"], key=lambda r: -r["total"])
    for i, r in enumerate(rows[:12]):
        mark = " <== ORIGINE" if r["pos"] == t["origin"] else ""
        print("   %2d. %-8s total=%10.2f  tile=%8.2f  mindist=%10.2f  pathdist=%s %s"
              % (i + 1, r["pos"], r["total"], r["tile"], r["mindist"], r["pathdist"], mark))
        if r["leaves"]:
            print("        feuilles: %s" % r["leaves"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--steps", type=int, default=STEPS)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--table", action="store_true",
                    help="table par FEUILLE sur le pas cible (--step)")
    ap.add_argument("--step", type=int, default=TARGET_STEP)
    ap.add_argument("--noreg", action="store_true", help="non-regression par MUTATION")
    ap.add_argument("--scan", help="liste de seeds separees par des virgules")
    a = ap.parse_args()
    if a.scan:
        rows = scan([int(s) for s in a.scan.split(",") if s.strip()], a.board, a.steps)
        cand = [r for r in rows if r["stay"]["n"] > 0]
        print("\n  montages exhibant le regime « natif NE BOUGE PAS » : %s"
              % ([(r["board"], r["seed"], r["stay"]["n"]) for r in cand] or "AUCUN"))
        return 0 if cand else 1
    if a.noreg:
        res = run_noreg(seed=a.seed, board=a.board, steps=a.steps, keep=a.keep)
        if "error" in res:
            print("[320] MONTAGE NON INSTALLE : %s" % res["error"], file=sys.stderr)
            return 2
        print("\n=== NON-REGRESSION (%s / seed %d, %d pas) ===" % (res["board"], res["seed"],
                                                                  res["steps"]))
        for k in ("pos", "ability", "stay"):
            print("  %-8s AVEC fix=%s | SANS=%s" % (k, res["with_fix"][k], res["without_fix"][k]))
        return 0
    res = run(seed=a.seed, board=a.board, steps=a.steps, keep=a.keep,
              table_at=(a.step if a.table else None))
    if "error" in res:
        print("[320] MONTAGE NON INSTALLE : %s" % res["error"], file=sys.stderr)
        return 2
    c = res["walk"]
    for t in c.get("tables") or []:
        _print_table(t)
    print("\n=== VERDICT (%s / seed %d, %d pas) ===" % (res["board"], res["seed"], res["steps"]))
    print("  pas decides     : %d" % c["n"])
    print("  natif SUR PLACE : %d | meme tuile : CABLE=%d NEUTRE=%d"
          % (c["stay"]["n"], c["stay"]["same"], c["stay"]["neu_same"]))
    print("  natif BOUGE     : %d | meme tuile : CABLE=%d NEUTRE=%d"
          % (c["moved"]["n"], c["moved"]["same"], c["moved"]["neu_same"]))
    print("  CORRIGES par le fix : %s" % (c["fixed"] or "aucun"))
    print("  CASSES  par le fix : %s" % (c["broken"] or "aucun"))
    print("  etage SCORING encore faux (CABLE) : %s" % (c["scoring_miss"] or "aucun"))
    print("  etage SCORING faux sans le fix (NEUTRE) : %s" % (c["neu_scoring_miss"] or "aucun"))
    if not c["stay"]["n"]:
        print("  AUCUN pas ou le natif reste sur place -- ce montage ne mesure RIEN, en changer")
        return 3
    if not c["discriminant"]:
        print("  MONTAGE NON DISCRIMINANT : les deux bras rendent le MEME resultat -- il ne "
              "conclut RIEN, en changer")
        return 3
    # Les pas ou les DEUX bras divergent identiquement relevent d'un AUTRE etage (sweep de position
    # d'une ability, gate d'ability) : ils ne sont ni corriges ni casses par #320, et les compter
    # ici masquerait le verdict de cette tranche derriere un defaut qui ne lui appartient pas.
    return 0 if (c["fixed"] and not c["broken"] and not c["scoring_miss"]) else 1


if __name__ == "__main__":
    sys.exit(main())
