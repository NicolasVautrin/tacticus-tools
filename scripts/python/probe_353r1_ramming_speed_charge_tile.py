"""probe #353-r1 (volet a) -- la TUILE de charge de `RammingSpeed` (1059), confrontee au NATIF.

QUESTION BINAIRE : `IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$GetTileToMoveTo`
du port designe-t-il la MEME tuile que le natif ?

COMMENT ON L'OBSERVE (et pourquoi cette voie-la)
------------------------------------------------
Le batch EXPLOSION de `IdunBattle.AI.Playbook.Loki.RammingSpeedPlaybook$$MakeDamagePredictions` --
celui qui consomme `GetTileToMoveTo` -- est garde par `selfPreds.Any(p => p.WillBeKill)`, et #353 a
MESURE que cette gate n'ouvre sur aucun montage joue. La face PREDICTION n'expose donc pas la tuile.

La face COMBAT, elle, l'expose DIRECTEMENT :
`RammingSpeedAbility$$ExecuteBehaviour` = `If( !IsAdjacent(caster@0x48, target@0x60, 3),
MoveUnit(caster@0x48, GetTileToMoveTo(), <options nulles>) )` puis les deux `AttackWithAttackDamage`.
=> **la position d'ARRIVEE du caster APRES un cast natif de 1059 EST la tuile rendue par
`GetTileToMoveTo`**. Aucun capteur neuf, aucun hook : `applyAction` suffit.

Deux conditions de montage, toutes deux LUES au decompile :
  * le caster ne doit PAS etre adjacent a la cible (sinon le `If` court-circuite le MoveUnit) ;
  * il ne doit pas avoir bouge ce tour -- `RammingSpeedAbility$$GetDynamicInvalidTargetReason`
    ouvre sur `(DidMove(caster) || GetMainTile(caster) != casterTiles[0]) && !isAdjacent -> 0x10`.
    D'ou le `endturn` apres le drive.

GATE DE CONFRONTABILITE : 1059 a ZERO porteur au gameconfig (mesure #353, 4 citations = des
DEFINITIONS). Recours etabli = la GREFFE sur `orksKillaKan` (case-92 sec.5bis), avec la correction
#353 : `_load_seed_bc` ne re-synthetise QUE les configs deja referencees, et `RammingSpeed` est
absente des 131 entrees -> l'injection EXPLICITE de la config est obligatoire. On reutilise
`probe_353_ramming_speed_prediction.build_grafted_seed_bc`, foyer unique de cette greffe.

CE QUE LE PROBE TRANCHE, bras par bras (jamais un scalaire fitte) :
  * `bucket`    = le port LIVRE : `First(SortTilesByUtility(pool, caster, UtilityDefinition(
                  [WeightedUtility(7), WeightedUtility(54)])), 1)` ;
  * `tile7`     = le MEME calcul, bucket AMPUTE de son 2e terme = ce que le port savait exprimer
                  AVANT #353-r1 ;
  * `swapped`   = le MEME bucket, mais operandes de l'intersection INTERVERTIS (l'ordre du helper
                  `TilesUnitCanMoveToChargeTarget` que Waaagh utilise).
Un bras qui coincide avec `bucket` sur une geometrie donnee ne DISCRIMINE PAS : le probe le DIT
plutot que de compter la geometrie comme une validation.

ASCII only (cp1252). Usage (depuis scripts/python) :
    python probe_353r1_ramming_speed_charge_tile.py                 # 2 geometries craftees
    python probe_353r1_ramming_speed_charge_tile.py --json
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
sys.path.insert(0, str(PYDIR))
ROOT = PYDIR.parents[1]

from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402
from probe_353_ramming_speed_prediction import build_grafted_seed_bc  # noqa: E402

ABILITY = 1059
GRAFT = "orksKillaKan"          # greffon MELEE du pool rank 17 (cf. probe_353)
FILLER_P = "astraBullgryn"      # allie, garde LOIN : il ne doit toucher aucune candidate
VICTIM = "necroWarden"          # cible de la charge
ENEMY2 = "ultraTitus"           # 2e ennemi : c'est LUI qui rend la feuille 54 discriminante
BOARD = "MC1_67"
MOVE_RANGE = 5                  # `abilities.RammingSpeed.constants.range` (GetNumberConstant(0x16))


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, seed_bc: Path, seed: int, hp: int) -> int:
    """`--hp-player` GENEREUX : le 2e batch de l'ability est un RECUL qui frappe le CASTER
    (`nrOfHits_2` coups de sa propre base). Un caster mort ne serait plus sur une tuile, et la
    mesure -- sa POSITION d'arrivee -- disparaitrait."""
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", BOARD, "--rank", "17",
           "--seed-bc", str(seed_bc),
           "--p-units", "%s,%s" % (GRAFT, FILLER_P),
           "--a-units", "%s,%s" % (VICTIM, ENEMY2),
           "--hp-player", str(int(hp)), "--hp-target", str(int(hp)), "--no-ai"]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-1200:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _view(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)


def _pos(dv, uid):
    for u in (dv.get("units") or []):
        if int(u.get("id")) == int(uid):
            p = u.get("pos") or {}
            return (p.get("col"), p.get("row"))
    return None


def _ids(dv) -> dict:
    out = {}
    for v in (GRAFT, FILLER_P, VICTIM, ENEMY2):
        u = next((x for x in (dv.get("units") or []) if x.get("visualId") == v and x.get("alive")),
                 None)
        if u is None:
            raise RuntimeError("unite absente du build : %s" % v)
        out[v] = int(u["id"])
    return out


def _endturn(sid, rid):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)


def _move(sid, rid, uid, col, row):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def drive_to(sid, rid, wanted: dict, max_turns: int = 20) -> bool:
    """Amene chaque unite sur SA position (pas-a-pas via `aiMovableTiles`), puis `endturn` -- ce
    qui RESET le flag `Moved` du caster, sans quoi `GetDynamicInvalidTargetReason` rend `0x10`."""
    for _ in range(max_turns):
        dv = _view(sid, rid)
        if all(_pos(dv, u) == p for u, p in wanted.items()):
            _endturn(sid, rid)
            return True
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60) or {}
        for mu in (mov.get("units") or []):
            uid = int(mu.get("unitId") or -1)
            if uid not in wanted:
                continue
            dest = tuple(wanted[uid])
            cur = ((mu.get("pos") or {}).get("col"), (mu.get("pos") or {}).get("row"))
            if cur == dest:
                continue
            reach = [(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])
                     if t.get("col") is not None]
            if not reach:
                continue
            step = min(reach, key=lambda p: (hexgeo.distance(p, dest), p))
            if step != cur:
                _move(sid, rid, uid, *step)
        _endturn(sid, rid)
    dv = _view(sid, rid)
    return all(_pos(dv, u) == p for u, p in wanted.items())


def _load(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dv = _view(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    return load_state(dv, ob, snap, board=board), board, dv


def _three_arms(state, board, caster, target):
    """Les trois bras, sur le MEME etat : port LIVRE / bucket ampute / operandes intervertis."""
    from engine.dsl.base import Const
    from engine.entities.selectors import (AdjacentTiles, CanAddUnit, Caster, CasterTile,
                                           MovableTilesInRange, Target, TileIntersect)
    from engine.runner.abilities.behaviours import entities_from_state
    from engine.runner.abilities.orks import (RAMMING_SPEED_TILE_UTILITY,
                                              ramming_speed_charge_tiles_selector,
                                              ramming_speed_tile_to_move_to)
    from engine.utilities.decider import UtilityDefinition
    from engine.utilities.tile import first_tile_by_utility
    from engine.utilities.utility_type import UtilityType

    ents = entities_from_state(state, caster, target)
    pool = ramming_speed_charge_tiles_selector(MOVE_RANGE).evaluate(ents)
    swapped_pool = TileIntersect(
        CanAddUnit(AdjacentTiles(Target())),
        MovableTilesInRange(Caster(), CasterTile(), Const(MOVE_RANGE),
                            can_reach_only=False)).evaluate(ents)
    only7 = UtilityDefinition.from_utility_type(int(UtilityType.Tile))

    def _first(tiles, definition):
        t = first_tile_by_utility(state, tiles, unit_id=caster, utility_definition=definition)
        return board.coord(t) if t is not None else None

    return {
        "pool": [board.coord(t) for t in pool],
        "pool_swapped": [board.coord(t) for t in swapped_pool],
        "bucket": ramming_speed_tile_to_move_to(state, caster, target, MOVE_RANGE),
        "tile7": _first(pool, only7),
        "swapped": _first(swapped_pool, RAMMING_SPEED_TILE_UTILITY),
    }


def _decompose(state, board, pool, caster):
    """Terme par terme sur le pool : `Tile(7)` d'un cote, la feuille 54 de l'autre. C'est ce qui
    rend un ecart ATTRIBUABLE au lieu d'etre constate."""
    from engine import weights as W
    from engine.utilities.ramming_speed import RAMMING_SPEED_MOST_ADJACENT_ENEMIES as U54
    from engine.utilities.tile import TILE_UTILITY, runner_tile_leaf_ctx
    wt = W.load()
    ctx = runner_tile_leaf_ctx(state, caster)
    out = {}
    for t in pool:
        p = board.coord(t)
        out[str(p)] = {"tile7": TILE_UTILITY.evaluate(p, {}, ctx, wt),
                       "u54": U54.evaluate(p, {}, ctx, wt)}
    return out


def _cast(sid, rid, caster, target, tries=6):
    """Caste 1059 et rend (action, position du caster APRES). La position est lue dans le retour
    d'`applyAction` (`units[].squadId/pos`) et pas via `decisionView` : si l'action termine la
    bataille, la vue de decision ne liste plus rien et on mesurerait `None`."""
    act0, res = {}, {}
    for _ in range(tries):
        res = _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": int(caster), "targetId": int(target),
            "abilityType": ABILITY}}, 120) or {}
        act0 = (res.get("actions") or [{}])[0]
        if not act0.get("error") and act0.get("mutated"):
            break
        _endturn(sid, rid)
    after = None
    for u in (res.get("units") or []):
        if int(u.get("squadId", -1)) == int(caster):
            p = u.get("pos") or {}
            after = (p.get("col"), p.get("row"))
            break
    return act0, after


def _geometry(board, kind: str):
    """Deux geometries CRAFTEES sur le board reel (positions DIRIGEES, jamais subies) :

      * `count`  : le 2e ennemi touche DEUX candidates qui ne sont PAS les premieres de l'ordre
                   source -> c'est la feuille 54 qui doit trancher ;
      * `order`  : le 2e ennemi cree DEUX candidates ex aequo au sommet -> a utilite egale, c'est
                   l'ORDRE du selecteur source qui tranche.

    Rend `(target_pos, enemy2_pos, caster_pos, ally_pos)` ou None si le board n'offre pas la
    configuration (le probe le DIT au lieu d'inventer une geometrie degradee)."""
    six = sorted(t for t in board.by_id
                 if board.walkable(t) and len(board.neighbours(t)) == 6
                 and all(board.walkable(n) for n in board.neighbours(t)))
    for tt in six:
        tp = board.coord(tt)
        ring = [board.coord(n) for n in board.neighbours_native(tt)]
        if len(ring) != 6:
            continue
        for e2 in ring:
            rest = [p for p in ring if p != e2]
            touched = [p for p in rest if hexgeo.distance(p, e2) == 1]
            if len(touched) != 2:
                continue
            # ordre source du port = ids de tuile CROISSANTS (cf. `MovableTilesInRange`)
            by_id = sorted(rest, key=lambda p: board.id_at(p[0], p[1]))
            first_is_touched = by_id[0] in touched
            if kind == "count" and first_is_touched:
                continue                     # le 1er du pool est deja au max -> non discriminant
            if kind == "order" and not first_is_touched:
                continue                     # les ex aequo ne sont pas departages par l'ordre
            if kind == "order":
                # les ex aequo doivent etre departages DIFFEREMMENT par les deux ordres, sinon la
                # geometrie ne peut rien prouver sur l'ordre des operandes
                first_by_ring = next(p for p in ring if p in touched)
                first_by_id = next(p for p in by_id if p in touched)
                if first_by_ring == first_by_id:
                    continue
            # caster ET allie : marchables, HORS ring, et l'allie assez LOIN pour ne toucher
            # aucune candidate (sinon il n'est pas neutre pour la feuille 54 -- qui ne compte que
            # les ennemis, mais il occuperait une tuile du pool).
            walk = sorted(board.coord(x) for x in board.by_id if board.walkable(x))
            free = [p for p in walk if p not in ring and p != tp]
            ally = next((p for p in reversed(free)
                         if all(hexgeo.distance(p, q) > 1 for q in ring + [tp])), None)
            if ally is None:
                continue
            cp = next((p for p in free
                       if p != ally and 2 <= hexgeo.distance(p, tp) <= MOVE_RANGE), None)
            if cp is None:
                continue
            return tp, e2, cp, ally
    return None


def run_case(sid, kind: str, seed: int, hp: int, verbose: bool) -> dict:
    logs = ROOT / "logs"
    sf = logs / ("p353r1-%s.json" % uuid.uuid4().hex[:8])
    bcf = logs / ("p353r1-seed-bc-%s.json" % uuid.uuid4().hex[:8])
    out: dict = {"kind": kind, "seed": seed}
    out["graft"] = build_grafted_seed_bc(bcf)
    rid = None
    try:
        rid = _build(sf, bcf, seed, hp)
        out["runner"] = rid
        state, board, dv = _load(sid, rid)
        ids = _ids(dv)
        geo = _geometry(board, kind)
        if geo is None:
            out["error"] = "aucune geometrie %r sur le board %s" % (kind, BOARD)
            return out
        tp, e2, cp, ap = geo
        out["geometry"] = {"target": list(tp), "enemy2": list(e2), "caster": list(cp),
                           "ally": list(ap)}
        wanted = {ids[VICTIM]: tp, ids[ENEMY2]: e2, ids[GRAFT]: cp, ids[FILLER_P]: ap}
        if not drive_to(sid, rid, wanted):
            dv = _view(sid, rid)
            out["error"] = "drive KO : voulu %s obtenu %s" % (
                {k: list(v) for k, v in wanted.items()},
                {u: _pos(dv, u) for u in wanted})
            return out
        state, board, dv = _load(sid, rid)          # etat POST-drive = celui du cast
        caster, target = ids[GRAFT], ids[VICTIM]
        arms = _three_arms(state, board, caster, target)
        out.update(arms)
        out["decompose"] = _decompose(state, board,
                                      [board.id_at(*p) for p in arms["pool"]], caster)
        out["discriminant_count"] = arms["bucket"] != arms["tile7"]
        out["discriminant_order"] = arms["bucket"] != arms["swapped"]
        act0, after = _cast(sid, rid, caster, target)
        out["cast_error"] = act0.get("error")
        out["cast_mutated"] = bool(act0.get("mutated"))
        out["native"] = list(after) if after else None
        if not out["cast_mutated"]:
            out["error"] = "cast refuse : %s" % act0.get("error")
            return out
        out["match"] = (tuple(after) == tuple(arms["bucket"])) if (after and arms["bucket"]) else False
        out["ok"] = bool(out["match"]
                         and (out["discriminant_count"] if kind == "count"
                              else out["discriminant_order"]))
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        sf.unlink(missing_ok=True)
        bcf.unlink(missing_ok=True)
    if verbose:
        print("[353r1/%s] runner=%s geo=%s" % (kind, out.get("runner"),
                                               json.dumps(out.get("geometry"))))
        print("  pool (ordre NATIF RammingSpeed) = %s" % (out.get("pool"),))
        print("  pool (ordre du helper Waaagh)   = %s" % (out.get("pool_swapped"),))
        print("  decompose (Tile7 / u54)         = %s" % json.dumps(out.get("decompose")))
        print("  port LIVRE (bucket 7 + 54)      = %s" % (out.get("bucket"),))
        print("  bras Tile(7) SEUL               = %s%s"
              % (out.get("tile7"), "" if out.get("discriminant_count") else "   [NON DISCRIMINANT]"))
        print("  bras operandes INTERVERTIS      = %s%s"
              % (out.get("swapped"),
                 "" if out.get("discriminant_order") else "   [NON DISCRIMINANT]"))
        print("  NATIF atterrit                  = %s  -> %s"
              % (out.get("native"), "MATCH" if out.get("match") else "MISMATCH"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=353100)
    ap.add_argument("--hp", type=int, default=900000,
                    help="PV forces des DEUX camps : le recul du ram ne doit pas tuer le caster")
    ap.add_argument("--kind", choices=("count", "order", "both"), default="both")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    sid = _resolve_session()
    kinds = ("count", "order") if a.kind == "both" else (a.kind,)
    res = [run_case(sid, k, a.seed + i, a.hp, True) for i, k in enumerate(kinds)]
    if a.json:
        print(json.dumps(res, indent=1, default=str))
    ok = sum(1 for r in res if r.get("ok"))
    print("\n[353r1] BILAN : %d/%d cas OK" % (ok, len(res)))
    return 0 if ok == len(res) else 1


if __name__ == "__main__":
    raise SystemExit(main())
