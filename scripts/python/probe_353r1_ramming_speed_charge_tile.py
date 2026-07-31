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


def controlled_by_current_player(sid, rid) -> set:
    """Les `unitId` que le joueur COURANT controle (#381) -- foyer unique de cette lecture.

    Pourquoi elle compte, mesure le 2026-07-31 : `MovableTilesInRangeSelector` interroge
    `IdunBattle.Core.Services.MovementQuery$$GetMovableTilesFor` avec `ignoreUnitFlags = false`
    (champ `_ignoreFlags = 0`, lu par le capteur #370), et
    `IdunBattle.Core.Services.MovementQuery$$FindAnyOrAllMoveableTiles` sort AUSSITOT --
    en laissant l'`OrderedSet` deja alloue VIDE, sans erreur -- des que
    `UnitFlagsComponent$$Has(unitFlags, 1)` est vrai. Une unite qui n'a pas la main n'a donc
    AUCUNE tuile de mouvement, et tout arbre DSL qui part de `MovableTilesInRange` rend vide.
    Un montage qui laisse le caster hors de son tour mesure ce vide-la, pas une propriete de
    l'arbre : c'est exactement le faux verrou de `#361` (2 events pour 5 attendus).

    On lit le predicat NATIF (`IsControlledByCurrentPlayer`, le filtre `side="friendly"` du RPC
    `aiMovableTiles`) plutot que de le reconstruire depuis un numero d'equipe suppose. Rend un
    ensemble VIDE si le RPC ne repond pas -- l'appelant doit traiter ce cas comme « non lu »,
    jamais comme « aucune unite »."""
    res = _r(sid, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 90)
    if not res or res.get("ok") is False:
        return set()
    return {int(u["unitId"]) for u in (res.get("units") or []) if u.get("unitId") is not None}


def ensure_turn(sid, rid, unit_id: int, max_turns: int = 4) -> bool:
    """Rend la main a `unit_id` (`endturn` jusqu'a ce que son camp joue), sans deplacer personne.

    A appeler APRES `drive_to` par tout montage qui mesure un arbre partant de
    `MovableTilesInRange` : `drive_to` termine sur un `endturn`, donc la PARITE du nombre de
    tours consommes decide qui a la main -- et deux montages qui posent la MEME geometrie par des
    chemins de drive differents ne la laissent pas au meme camp. C'est la difference, longtemps
    non identifiee, entre les deux montages de `#361` (cf. `controlled_by_current_player`).

    Rend `True` si la main est au camp de l'unite, `False` sinon (l'appelant doit alors declarer
    son bras NON DISCRIMINANT -- jamais conclure du natif)."""
    for _ in range(max(0, int(max_turns)) + 1):
        ctrl = controlled_by_current_player(sid, rid)
        if not ctrl:
            return False           # RPC muet : « non lu », surtout pas « aucune unite »
        if int(unit_id) in ctrl:
            return True
        _endturn(sid, rid)
    return int(unit_id) in controlled_by_current_player(sid, rid)


def _move(sid, rid, uid, col, row):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def drive_to(sid, rid, wanted: dict, max_turns: int = 40) -> bool:
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
                            ignore_flags=False, ignore_units_on_tiles=False)).evaluate(ents)
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
    rend un ecart ATTRIBUABLE au lieu d'etre constate.

    ⚠ Le `meta` par tuile est reconstruit EXACTEMENT comme dans `sort_tiles_by_utility` (elevation
    de la tuile + min/max du BOARD ENTIER + effets, canal dynamique puis `terrain_tile_effects`).
    Un `meta` vide ferait rendre 0 a `ElevationUtility`/`TileEffectsUtility` et afficherait un
    `Tile(7)` PLAT qui n'existe pas -- c'est exactement le faux diagnostic a ne pas produire."""
    from engine import weights as W
    from engine.utilities.ramming_speed import RAMMING_SPEED_MOST_ADJACENT_ENEMIES as U54
    from engine.utilities.tile import TILE_UTILITY, runner_tile_leaf_ctx, terrain_tile_effects
    wt = W.load()
    ctx = runner_tile_leaf_ctx(state, caster)
    elevs = [t.get("elevation") for t in board.by_id.values() if t.get("elevation") is not None]
    emax, emin = (max(elevs), min(elevs)) if elevs else (None, None)
    fx = getattr(state, "effects", None)
    out = {}
    for t in pool:
        p = board.coord(t)
        info = board.by_id.get(t) or {}
        effs = []
        if fx is not None:
            effs += [e.name for e in fx.by_unit.get(int(t), []) if not e.consumed and e.name]
        effs += terrain_tile_effects(board.tile_def_id(t), effs)
        meta = {"elevation": info.get("elevation"), "elevation_max": emax, "elevation_min": emin,
                "effects": effs}
        out[str(p)] = {"tile7": TILE_UTILITY.evaluate(p, meta, ctx, wt),
                       "u54": U54.evaluate(p, meta, ctx, wt),
                       "elev": info.get("elevation"), "terrain": board.tile_def_id(t)}
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


def _scan_geometry(state, board, ids, kind: str, max_targets: int = 24):
    """Cherche une geometrie DISCRIMINANTE en MUTANT l'etat OFFLINE, puis en TESTANT les trois bras
    -- jamais en PREDISANT la discrimination depuis une hypothese de terrain.

    C'est la lecon du 1er jet de ce probe : il choisissait la geometrie en supposant `Tile(7)` PLAT
    (« la 1re du pool gagne a utilite egale »). Sur un board REEL, `Tile(7)` porte l'elevation et les
    effets de terrain, il n'est PAS plat, et l'axe ORDRE tombait sur une geometrie non discriminante.
    On mesure donc, sur le board reel, ce que les bras rendent.

      * `count`  : le bras `Tile(7)` SEUL doit designer une AUTRE tuile que le bucket complet
                   -> c'est la feuille 54 qui tranche ;
      * `order`  : le bras OPERANDES INTERVERTIS doit designer une AUTRE tuile
                   -> c'est l'ordre du selecteur source qui tranche.

    Rend `(target_pos, enemy2_pos, caster_pos, ally_pos)` ou None -- auquel cas le probe le DIT au
    lieu de jouer une geometrie qui ne prouverait rien. Positions restaurees a la sortie."""
    from engine.runner.components import PositionComponent
    pcs = {v: state.get_entity(ids[v]).get_component(PositionComponent)
           for v in (GRAFT, FILLER_P, VICTIM, ENEMY2)}
    keep = {v: (pc.col, pc.row) for v, pc in pcs.items()}
    walk = sorted(board.coord(t) for t in board.by_id if board.walkable(t))
    # PROXIMITE AUX SPAWNS : chaque tuile de deplacement est un tour de drive, et un drive long
    # derive l'etat (fatigue, effets de tour). On balaie donc les cibles les plus proches d'abord.
    six = sorted((t for t in board.by_id
                  if board.walkable(t) and len(board.neighbours(t)) == 6
                  and all(board.walkable(n) for n in board.neighbours(t))),
                 key=lambda t: (hexgeo.distance(board.coord(t), keep[VICTIM]), t))
    try:
        for tt in six[:max_targets]:
            tp = board.coord(tt)
            ring = [board.coord(n) for n in board.neighbours_native(tt)]
            if len(ring) != 6:
                continue
            ally = next((p for p in reversed(walk)
                         if all(hexgeo.distance(p, q) > 1 for q in ring + [tp])), None)
            if ally is None:
                continue
            pcs[VICTIM].col, pcs[VICTIM].row = tp
            pcs[FILLER_P].col, pcs[FILLER_P].row = ally
            casters = sorted((p for p in walk
                              if p != ally and p not in ring
                              and 2 <= hexgeo.distance(p, tp) <= MOVE_RANGE),
                             key=lambda p: (hexgeo.distance(p, keep[GRAFT]), p))
            for e2 in sorted(ring, key=lambda p: hexgeo.distance(p, keep[ENEMY2])):
                pcs[ENEMY2].col, pcs[ENEMY2].row = e2
                for cp in casters[:8]:
                    pcs[GRAFT].col, pcs[GRAFT].row = cp
                    arms = _three_arms(state, board, ids[GRAFT], ids[VICTIM])
                    if arms["bucket"] is None or len(arms["pool"]) < 2:
                        continue
                    if kind == "count" and arms["bucket"] == arms["tile7"]:
                        continue
                    if kind == "order" and arms["bucket"] == arms["swapped"]:
                        continue
                    return tp, e2, cp, ally
    finally:
        for v, pc in pcs.items():
            pc.col, pc.row = keep[v]
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
        geo = _scan_geometry(state, board, ids, kind)
        if geo is None:
            out["error"] = ("aucune geometrie DISCRIMINANTE %r sur le board %s -- rien n'est joue "
                            "(une geometrie non discriminante ne validerait rien)" % (kind, BOARD))
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
