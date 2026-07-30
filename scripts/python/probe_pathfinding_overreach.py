#!/usr/bin/env python
"""Probe -- residu PATHFINDING << le port SUR-ATTEINT d'UNE tuile >> (case-224 SS4).

Confronte, tuile par tuile, l'ensemble d'ARRET natif `aiMovableTiles`
(`IdunBattle.Core.Services.MovementQuery$$GetMovableTilesFor`) au pendant offline
`engine/ai/state_bridge._move_tiles`, dans les DEUX regimes de chargement d'etat :

    A. NON HYDRATE : `load_state(dec, ob, snap, board=board)`      -- canal `tiles=` ABSENT
    B. HYDRATE     : `load_state(..., tiles=tileMeta)`             -- canal `tiles=` FOURNI

C'est ce couple qui identifie le residu : le gate d'expansion
`IdunBattle.Entities.Pathfinding.BasePathfinder$$NodesInNextLevel` ->
`IdunBattle.Entities.Pathfinding.WalkPathfinder$$IsValidContinuePathTile` (#131) est porte
(`engine/entities/pathfinding/tile_blocking.make_can_continue`) mais il ne s'ARME que si
`State.effects` porte les effets de TUILE -- donc seulement en regime B. En regime A il
degrade EN SILENCE et la flood-fill s'etend DEPUIS une tuile block-entering : elle atteint
UNE tuile de plus, celle qui ne pend que d'un Swamp.

Chaine native (RE build rnca9r7q6c, lue en entier) :

    MovementQuery$$GetMovableTilesFor -> $$FindAnyOrAllMoveableTiles -> $$AnyOrFillMoveableTiles
      reach = $$GetReachableTiles -> Pathfinders$$FindReachableTiles -> <pf>$$FindReachableTiles
              -> BasePathfinder$$IterateReachableTiles
                 depth = GetEffectiveDepth(start, unit, depth)          [vtable +0x208]
                 + BasePathfinder$$GetMovablePositions (BFS PAR NIVEAUX, non pondere)
                    -> NodesInNextLevel : (node != start && !IsValidContinuePathTile) => AUCUN voisin
                    -> GetValidNeighbours -> AddNeighbours (voisins `ConnectivityComponent`
                       + IsValidPathNode [vtable +0x1e8]) + AddTeleportationTiles + AddShadewalkerTiles
      reach.RemoveAll(t => !MovementQuery$$IsMovableTile(unit, t, ignoreUnitsOnTiles))

    WalkPathfinder$$IsValidContinuePathTile = `GetTileBlockingReasons(tile, unit) == 0`
    WalkPathfinder$$GetTileBlockingReasons   : parcourt les EFFETS de la tuile ; un effet
      `BlockEnteringUnitsTileEffect` (EffectType 0) pose le bit 0x1 sauf si l'unite porte un trait de
      `StaticBattleRules.Effect$$NotBlockingMovementOfTraits` (Mounted/Vehicle/Unstoppable).
    `IdunBattleLogic.Entities.Abilities.Tiles.ThornsBlockMovementAbility$$CreateBehaviour`
      (ability hebergee par le tile-def **Swamp**) = `AddBlockEnteringUnitsEffect(0) &
      AddStaticStatModifierEffectToOwner(0xb, 3, Direct(GetNumberConstant(0x14)))` -> c'est elle qui
      pose l'effet sur chaque Swamp AU SETUP de la bataille.

Ce que le probe imprime pour CHAQUE tuile en ecart (`offline \\ natif` ou l'inverse) :
  - ses proprietes statiques (elevation, walkable, isWall, isTemporary, tileDefId, effets tileMeta) ;
  - son niveau BFS offline et ses parents possibles (voisins au niveau-1), avec le TERRAIN du parent
    et le fait qu'il porte, ou non, `BlockEnteringUnits` ;
  - la distance NATIVE de la tuile, mesuree en re-interrogeant `aiMovableTiles` a portee croissante
    (`overrideRange`) : c'est ce qui distingue un ecart de FLOOD-FILL (la tuile entre a mv+1) d'un
    ecart de FILTRE D'ARRET (elle n'entre jamais).

Aucune mutation d'etat (que des RPC de lecture ; le build est dispose sauf `--keep`).
ASCII only (cp1252). Usage :
    python probe_pathfinding_overreach.py --seed 777   --board MC1_67
    python probe_pathfinding_overreach.py --seed 31337 --board C4_09
    python probe_pathfinding_overreach.py --runner <id> [--dist]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

# Montage par defaut = celui de case-224 (c'est la que les 4 sur-atteintes ont ete mesurees).
P_UNITS = "deathBlightbringer,worldJakhal,blackAbaddon,astraBullgryn"
A_UNITS = "necroWarden,necroWarden"


def _r(sid, m, b, t=180):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def build(seed: str, board: str, state_file: Path,
          p_units: str = P_UNITS, a_units: str = A_UNITS) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(state_file), "--board", board,
         "--p-units", p_units, "--a-units", a_units,
         "--hp-target", "300000", "--hp-player", "300000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[build] KO: %s" % ((proc.stderr or proc.stdout or "")[-800:],))
        sys.exit(2)
    return int(json.loads(state_file.read_text())["runnerId"])


def _off_tiles(state, board, uid: int):
    """Pendant OFFLINE de `aiMovableTiles` = le VRAI chemin de production
    (`engine/ai/state_bridge._move_tiles`), en ids de tuile."""
    from engine.ai.state_bridge import _move_tiles
    from engine.runner.components import OwnerComponent, PositionComponent, UnitComponent
    ent = state.get_entity(uid)
    if ent is None:
        return None
    pc, oc, uc = (ent.get_component(PositionComponent), ent.get_component(OwnerComponent),
                  ent.get_component(UnitComponent))
    if pc is None or oc is None or uc is None:
        return None
    out = set()
    for t in _move_tiles(state, int(uid), uc.visual_id, int(oc.team), (pc.col, pc.row)):
        tid = board.id_at(t["col"], t["row"])
        if tid is not None:
            out.add(tid)
    return out


def _native_dist(sid, rid, uids, maxr=12):
    """{uid: {tile_id: portee MINIMALE a laquelle le natif la rend}} via `overrideRange` croissant.
    Isole l'etage : une tuile qui entre a `mv+1` est un ecart de FLOOD-FILL (un pas de trop cote
    port) ; une tuile qui n'entre JAMAIS est un ecart de FILTRE D'ARRET (`IsMovableTile`)."""
    out = {u: {} for u in uids}
    for rng in range(1, maxr + 1):
        res = _r(sid, "aiMovableTiles", {"runnerId": rid, "side": "all", "overrideRange": rng}, 240)
        for u in (res.get("units") or []):
            uid = u["unitId"]
            if uid not in out:
                continue
            for t in (u.get("tiles") or []):
                out[uid].setdefault((t["col"], t["row"]), rng)
    return out


def audit(board_ids) -> int:
    """GARDE-FOU du repli terrain : sur chaque board, {tuiles au tile-def bloquant} doit etre
    EXACTEMENT {tuiles portant un effet bloqueur neutre}. Un ecart d'un cote = repli SUR-BLOQUANT
    (le port refuserait une expansion que le natif autorise) ; de l'autre = repli incomplet.

    ⚠ Le terrain se lit LIVE (`boardGraph.tileDefId`), JAMAIS le dump BC : sur `PVP_desert_04` la BC
    annonce 10 `Swamp` et le board deploye n'en a AUCUN (`Unplayable/Grass/Block/DryBush`). C'est
    cette confusion qui avait fait ecrire, dans `test_block_entering_tiles_live`, que la pose etait
    << conditionnelle >> et qu'un gate terrain serait sur-bloquant."""
    from engine.entities.pathfinding import Board
    from engine.entities.pathfinding.tile_blocking import (TERRAIN_BLOCK_ENTERING,
                                                           TILE_MOVEMENT_BLOCKING_EFFECT_TYPES)
    sid = _resolve_session()
    bad = 0
    for bid in board_ids:
        sf = ROOT / "logs" / "runners" / ("pf_audit_%s.json" % bid)
        # roster MINIMAL : l'audit ne lit que le BOARD, et certains boards n'ont que 3 spawns/camp.
        rid = build("777", bid, sf, p_units="worldJakhal", a_units="necroWarden")
        try:
            bg = _r(sid, "boardGraph", {"runnerId": rid}, 120)
            tm = _r(sid, "tileMeta", {"runnerId": rid}, 120)
            if not bg.get("ok"):
                print("[audit] %-24s boardGraph KO" % bid); bad += 1; continue
            board = Board(bg["tiles"], adjacency="native_sym")
            by_terrain = {t["id"] for t in bg["tiles"]
                          if (t.get("tileDefId") or "") in TERRAIN_BLOCK_ENTERING}
            by_effect = set()
            for t in (tm.get("tiles") or []):
                tid = board.id_at(t["col"], t["row"])
                for e in (t.get("effects") or []):
                    et = e.get("effectType")
                    if et is None or int(et) not in TILE_MOVEMENT_BLOCKING_EFFECT_TYPES:
                        continue
                    if e.get("source") is not None and int(e["source"]) != int(tid or -1):
                        continue
                    by_effect.add(tid)
            # le repli ne pretend couvrir QUE les bloqueurs heberges par le tile-def : un bloqueur
            # de decor pose sur un autre terrain (Fire sur Grass) est hors de sa portee, et
            # n'est PAS un ecart du repli -- seul `by_terrain \ by_effect` (SUR-blocage) l'est.
            over = by_terrain - by_effect
            under = by_effect - by_terrain
            tag = "OK  " if not over else "SUR-BLOQUE"
            print("[audit] %-26s %s terrain=%-3d effet=%-3d over=%s under=%s"
                  % (bid, tag, len(by_terrain), len(by_effect),
                     sorted(board.coord(t) for t in over),
                     sorted(board.coord(t) for t in under)))
            if over:
                bad += 1
        finally:
            try:
                _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=60)
            except Exception:
                pass
    print("[audit] %d board(s) en SUR-BLOCAGE" % bad)
    return 1 if bad else 0


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--dist", action="store_true",
                    help="mesure aussi la DISTANCE native de chaque tuile en ecart (12 RPC de plus)")
    ap.add_argument("--mutate", choices=["terrain-fallback"], default=None,
                    help="terrain-fallback : VIDE `TERRAIN_BLOCK_ENTERING` avant de mesurer "
                         "(= l'arbre AVANT ce fix) -- contre-epreuve")
    ap.add_argument("--place", default=None,
                    help="DRIVE des positions avant de mesurer : 'uid:col,row;uid:col,row'. Chaque "
                         "unite est deplacee (`applyAction move`), puis DEUX `endturn` rendent la "
                         "main au camp courant avec les activations rechargees (le natif refuse de "
                         "rendre des tuiles a une unite deja activee). Sert a CRAFTER une geometrie "
                         "ou le gate mord fort, au lieu d'attendre qu'elle se presente.")
    ap.add_argument("--audit", default=None,
                    help="AUDIT du repli terrain : 'b1,b2,...'. Pour chaque board, construit un "
                         "runner et confronte {tuiles dont `boardGraph.tileDefId` est dans "
                         "`TERRAIN_BLOCK_ENTERING`} a {tuiles dont `tileMeta` porte un effet "
                         "BLOQUEUR neutre}. Le repli n'est legitime que si les deux coincident "
                         "EXACTEMENT : un Swamp sans effet ferait SUR-BLOQUER le port.")
    a = ap.parse_args(argv)

    from engine.entities.pathfinding import Board
    from engine.runner.snapshot import load_state
    if a.audit:
        return audit(a.audit.split(","))
    if a.mutate == "terrain-fallback":
        import engine.entities.pathfinding.tile_blocking as _TB
        _TB.TERRAIN_BLOCK_ENTERING = frozenset()
        print("[mut] TERRAIN_BLOCK_ENTERING VIDE -- repli terrain desarme (arbre d'AVANT le fix)")

    sid = _resolve_session()
    own = False
    if a.runner is not None:
        rid = a.runner
    else:
        sf = Path(a.state_file) if a.state_file else (
            ROOT / "logs" / "runners" / ("pf_overreach_%s_%s.json" % (a.board, a.seed)))
        rid = build(a.seed, a.board, sf)
        own = True
    print("[probe] session %s runner %s board %s seed %s" % (sid, rid, a.board, a.seed))

    rc = 0
    try:
        if a.place:
            for spec in a.place.split(";"):
                uid, _, cr = spec.partition(":")
                c, _, r = cr.partition(",")
                res = _r(sid, "applyAction",
                         {"runnerId": rid, "captureEvents": False,
                          "action": {"kind": "move", "unit": int(uid),
                                     "col": int(c), "row": int(r)}}, 120)
                print("[place] u%s -> (%s,%s) ok=%s mutated=%s"
                      % (uid, c, r, res.get("ok"), res.get("mutated")))
            for _ in range(2):     # rend la main au camp courant, activations rechargees
                _r(sid, "applyAction",
                   {"runnerId": rid, "action": {"kind": "endturn"}, "captureEvents": False}, 120)
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 120)
        if not bg.get("ok"):
            print("boardGraph KO: %s" % bg.get("error")); return 2
        board = Board(bg["tiles"], adjacency="native_sym")
        tm = _r(sid, "tileMeta", {"runnerId": rid}, 120)
        tmeta = {(t["col"], t["row"]): t for t in (tm.get("tiles") or [])}
        amt = _r(sid, "aiMovableTiles", {"runnerId": rid, "side": "all"}, 180)
        if not amt.get("ok"):
            print("aiMovableTiles KO: %s" % amt.get("error")); return 2
        dec = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 180)
        ob = _r(sid, "observeBattle", {"runnerId": rid}, 120)
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 120)

        blocked = {board.id_at(c, r) for (c, r), t in tmeta.items()
                   for e in (t.get("effects") or [])
                   if int(e.get("effectType") if e.get("effectType") is not None else -1) == 0}
        blocked.discard(None)
        terr = {}
        for t in bg["tiles"]:
            terr.setdefault(t.get("tileDefId"), []).append(t["id"])
        print("[probe] %d tuiles ; terrains=%s ; block-entering (tileMeta)=%s"
              % (len(bg["tiles"]), {k: len(v) for k, v in sorted(terr.items(), key=lambda x: str(x[0]))},
                 sorted(board.coord(t) for t in blocked)))

        states = {"A_non_hydrate": load_state(dec, ob, snap, board=board),
                  "B_hydrate": load_state(dec, ob, snap, board=board, tiles=tm)}
        for label, st in states.items():
            n = sum(1 for tid in (st.effects.by_unit if st.effects else {})
                    if tid in board.by_id)
            print("[probe] etat %s : %d entites-tuile porteuses d'effets dans State.effects"
                  % (label, n))

        nat = {}
        for u in (amt.get("units") or []):
            s = set()
            for t in (u.get("tiles") or []):
                tid = board.id_at(t["col"], t["row"])
                if tid is not None:
                    s.add(tid)
            nat[u["unitId"]] = (u, s)

        totals = {k: [0, 0] for k in states}          # label -> [extra, missing]
        detail_units = []
        for uid, (u, native) in sorted(nat.items()):
            if not native:
                # `MovementQuery$$FindAnyOrAllMoveableTiles` rend VIDE quand
                # `UnitFlagsComponent.Has(1)` (unite deja activee ce tour) ou `!UnitExtensions$$CanMove`.
                # `_move_tiles` ne modelise pas ce gate d'ACTIVATION -> ecart d'un AUTRE etage, hors
                # perimetre de la sur-atteinte de flood-fill. Signale, jamais compte.
                print("  u%-3d %-22s nat=0 -> unite deja activee / immobile (gate UnitFlags, "
                      "hors perimetre)" % (uid, u.get("visualId")))
                continue
            row = ["u%-3d %-22s nat=%-3d" % (uid, u.get("visualId"), len(native))]
            worst = None
            for label, st in states.items():
                off = _off_tiles(st, board, uid)
                if off is None:
                    row.append("%s: n/a" % label)
                    continue
                extra, missing = off - native, native - off
                totals[label][0] += len(extra)
                totals[label][1] += len(missing)
                row.append("%s off=%-3d extra=%d missing=%d" % (label, len(off), len(extra), len(missing)))
                if extra or missing:
                    detail_units.append((label, uid, u, native, extra, missing))
            print("  " + " | ".join(row))

        for label in states:
            print("[probe] TOTAL %-14s extra=%d missing=%d"
                  % (label, totals[label][0], totals[label][1]))
        if totals["B_hydrate"] != [0, 0]:
            rc = 1

        if detail_units:
            print("--- diagnostic des ecarts, PAR REGIME ---")
            nd = _native_dist(sid, rid, sorted({d[1] for d in detail_units})) if a.dist else {}
            from engine.entities.pathfinding import get_reachable_levels
            from engine.runner.components import PositionComponent, OwnerComponent
            stA = states["A_non_hydrate"]
            occ = {}
            for t in bg["tiles"]:
                oid = t.get("occupantUnitId")
                if oid is not None:
                    e = stA.get_entity(oid)
                    oc = e.get_component(OwnerComponent) if e is not None else None
                    occ[t["id"]] = oc.team if oc is not None else None
            for label, uid, u, native, extra, missing in detail_units:
                e = stA.get_entity(uid)
                pc = e.get_component(PositionComponent)
                start = board.id_at(pc.col, pc.row)
                o = dict(occ); o.pop(start, None)
                lv = get_reachable_levels(board, start, o, occ.get(start), max_depth=None)
                for tid in sorted(extra | missing, key=lambda t: board.coord(t)):
                    c, r = board.coord(tid)
                    t = board.by_id[tid]
                    meta = tmeta.get((c, r)) or {}
                    kind = "EXTRA(offline\\natif)" if tid in extra else "MISSING(natif\\offline)"
                    dist = nd.get(uid, {}).get((c, r))
                    print("  [%s] u%-3d %s (%d,%d) id=%d lvl_off=%s dist_nat=%s terrain=%s elev=%s "
                          "walk=%s isWall=%s isTemp=%s effects=%s"
                          % (label, uid, kind, c, r, tid, lv.get(tid), dist, t.get("tileDefId"),
                             t.get("elevation"), t.get("walkable"), t.get("isWall"),
                             t.get("isTemporary"),
                             [(x.get("name"), x.get("effectType")) for x in (meta.get("effects") or [])]))
                    for p in board.neighbours(tid):
                        if lv.get(p) == (lv.get(tid) or 0) - 1:
                            pc2 = board.coord(p)
                            pm = tmeta.get(board.coord(p)) or {}
                            print("        parent (%d,%d) id=%-3d terrain=%-8s elev=%s "
                                  "block-entering=%s effects=%s"
                                  % (pc2[0], pc2[1], p, board.by_id[p].get("tileDefId"),
                                     board.by_id[p].get("elevation"), p in blocked,
                                     [(x.get("name"), x.get("effectType"))
                                      for x in (pm.get("effects") or [])]))
    finally:
        if own and not a.keep:
            try:
                _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=60)
            except Exception:
                pass
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
