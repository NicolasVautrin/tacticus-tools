#!/usr/bin/env python
"""Probe `#381-r1` -- le POOL de `MovableTilesInRange` confronte, ETAGE PAR ETAGE, a `aiMovableTiles`.

CE QU'IL MESURE, ET POURQUOI CE CAPTEUR-LA
------------------------------------------
Le RPC `aiMovableTiles` appelle **litteralement** `IdunBattle.Core.Services.MovementQuery$$
GetMovableTilesFor(unit, ignoreUnitFlags: false, options)` -- c'est-a-dire la MEME fonction native
que le noeud DSL : `MovableTilesInRangeSelector$$Select` passe par `BattleQuery$$GetMovableTilesFor`
(qui `ToList(fromTile)` puis delegue au meme slot). Confronter le pool du noeud a ce RPC est donc
une egalite EXACTE attendue, pas une approximation -- et c'est le seul etage que `#381-r1` touche.

Les deux faces de `probe_383` (POOL / TRI / SELECTEURS) mesuraient cet etage a travers
`RammingSpeed` : un ecart y arrivait mele au tri d'utilite et aux selecteurs des batchs. Ici il est
NU.

TROIS ETAGES du natif, et le port ne portait AUCUN des trois dans ce noeud (alors que
`ai/state_bridge._move_tiles` -- le mirror deja confronte du MEME RPC -- les porte tous) :

  1. `RemoveAll(t => !IsMovableTile(unit, t, ignoreUnitsOnTiles))` de
     `MovementQuery$$AnyOrFillMoveableTiles` -> le pool est le STOP-SET, pas le `visited` ;
  2. `BasePathfinder$$NodesInNextLevel` -> `IsValidContinuePathTile` (#131) -> une tuile
     block-entering est un CUL-DE-SAC ;
  3. `MovementQuery$$GetPathfinderTypeForUnit` -> `UnitExtensions$$IsLikeFlying` -> un volant
     traverse tout et ignore l'elevation.

LE TRI-ETAT QUI EMPECHE LE FAUX VERT
------------------------------------
La garde d'entree `UnitFlagsComponent$$Has(unitFlags, 1) && ignoreUnitFlags == 0` (#381) fait
repartir le natif sur un `OrderedSet` VIDE pour toute unite qui a deja joue -- et le port ne la
porte pas (`unitFlags` n'a aucun substrat offline). Une unite dont le natif rend VIDE n'est donc
**pas** un desaccord : elle est ECARTEE, comptee, et nommee. Si TOUTES le sont, le probe rend
`NON CONCLUANT` au lieu d'un accord vide.

GARDES ADVERSARIALES (`--mutate`) : chacune remet une des lectures a son etat FAUTIF et DOIT faire
diverger le port. Un bras dont la mutation ne change rien ne prouve rien, et le probe le DIT.
⚠ `no-fly` n'est PAS discriminant sur `MC1_67` a T0, et ce n'est pas un defaut du port : la
mutation eteint `is_like_flying`, donc elle change AUSSI la ventilation du probe (la volante
compte alors en WALK), et a T0 les unites sont sous mouvement special -- le pool de teleport est
board-wide, identique quelle que soit la base. Mesure : `WALK 10/10, VOLANTES 0/0`, rc 1, a
l'IDENTIQUE avant et apres `#381-r3`. Le bras qui discrimine le dispatch fly est
`tests/engine/entities/pathfinding/test_381r5_special_movement_live.py`.

QUATRIEME ETAGE, ajoute par `#381-r3` : le VOISINAGE. `AddNeighbours` est un slot VIRTUEL, et les
deux corps ne lisent pas la meme source -- `BasePathfinder$$AddNeighbours` enumere la liste STOCKEE
du `ConnectivityComponent` (la MARCHE), `FlyPathfinder$$AddNeighbours` interroge la requete de
tuiles au rayon 1 (le VOL, GEOMETRIE). Le `Board` du port n'a qu'un `adjacency=`, donc un mode
global se trompait forcement d'un cote : sur `C1_74` les deux vues divergent sur 74 aretes
dirigees, et `tauAunShi` sur-atteignait de 2 tuiles sous `evenq`. Les mutations `geo-walk` et
`stored-fly` remettent chacune UNE des deux branches a son etat fautif.

ASCII only (cp1252). Usage (depuis scripts/python, host up, session deja warmee) :
    python probe_381r1_movable_tiles_pool.py --board MC1_67
    python probe_381r1_movable_tiles_pool.py --board C1_74 --range 5
    python probe_381r1_movable_tiles_pool.py --board MC1_67 --mutate visited     # DOIT rougir
    python probe_381r1_movable_tiles_pool.py --board C1_74 --mutate geo-walk     # DOIT rougir
    python probe_381r1_movable_tiles_pool.py --board C1_74 --mutate stored-fly   # DOIT rougir
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
ROOT = PYDIR.parents[1]

from rl_collect_batch import _resolve_session, _rpc            # noqa: E402

MUTATIONS = ("none", "visited", "no-gate", "no-fly", "geo-walk", "stored-fly")
DEFAULT_BOARD = "MC1_67"
DEFAULT_RANGE = 5


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, seed: int, board: str, p_units: str, a_units: str) -> int:
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board, "--rank", "17", "--no-ai"]
    if p_units:
        cmd += ["--p-units", p_units]
    if a_units:
        cmd += ["--a-units", a_units]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-1200:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _load(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
    tm = _r(sid, "tileMeta", {"runnerId": rid}, 90)
    return load_state(dv, ob, snap, board=board, tiles=tm), board, dv


def _native(sid, rid, override_range: int) -> dict:
    """`{unitId: set((col,row))}` -- le pool NATIF, unite par unite. `side='all'` couvre les deux
    camps (le noeud DSL, lui, n'est pas restreint au joueur courant)."""
    res = _r(sid, "aiMovableTiles",
             {"runnerId": rid, "side": "all", "overrideRange": int(override_range)}, 120)
    if not res or res.get("ok") is False:
        return {}
    out = {}
    for u in (res.get("units") or []):
        uid = int(u.get("unitId") or -1)
        out[uid] = {(int(t["col"]), int(t["row"])) for t in (u.get("tiles") or [])
                    if t.get("col") is not None}
    return out


def _port_pool(state, board, uid: int, override_range: int) -> set:
    """Le pool du NOEUD DSL pour `uid`, en (col,row). `Caster()`/`CasterTile()` sont les DEUX
    selecteurs que tous les call-sites natifs lui passent (`factory+0x48` / `+0x50`)."""
    from engine.dsl.base import Const
    from engine.entities.selectors import Caster, CasterTile, MovableTilesInRange
    from engine.runner.abilities.behaviours import entities_from_state
    ents = entities_from_state(state, int(uid), int(uid))
    sel = MovableTilesInRange(Caster(), CasterTile(), Const(int(override_range)),
                              ignore_flags=False, ignore_units_on_tiles=False)
    return {board.coord(t) for t in sel.evaluate(ents)}


def _apply_mutation(mutate: str):
    """Remet une lecture a son etat FAUTIF, sur le MODULE du noeud. Rend le restaurateur."""
    from engine.entities.selectors import tiles as T
    saved = {"_movement_can_continue": T._movement_can_continue}

    def _restore():
        for k, v in saved.items():
            setattr(T, k, v)
        T.MovableTilesInRange.select = _sel0

    _sel0 = T.MovableTilesInRange.select
    if mutate == "none":
        return _restore
    if mutate == "visited":
        # L'ETAT D'AVANT ce correctif : le 4e argument lu comme un `canReachOnly` -> `visited`.
        def _visited(self, ctx):
            self.ignore_units_on_tiles = True
            try:
                return _sel0(self, ctx)
            finally:
                self.ignore_units_on_tiles = False
        T.MovableTilesInRange.select = _visited
    elif mutate == "no-gate":
        # Gate d'EXPANSION #131 desarme : la flood-fill s'etend DEPUIS une tuile block-entering.
        T._movement_can_continue = lambda ctx, board, traits: None
    elif mutate == "no-fly":
        # `GetPathfinderTypeForUnit` fige au WalkPathfinder : un volant redevient pieton.
        from engine.entities.pathfinding import fly_pathfinder as FP
        saved["is_like_flying"] = FP.is_like_flying
        FP.is_like_flying = lambda traits: False

        def _restore2():
            FP.is_like_flying = saved["is_like_flying"]
            T._movement_can_continue = saved["_movement_can_continue"]
            T.MovableTilesInRange.select = _sel0
        return _restore2
    elif mutate == "geo-walk":
        # #381-r3 : la MARCHE relit la GEOMETRIE au lieu du `ConnectivityComponent` -- l'etat
        # d'AVANT ce correctif quand le `Board` est monte en `adjacency="evenq"` (tous les probes).
        from engine.entities.pathfinding import walk_pathfinder as WP
        saved["walk_gmp"] = WP.get_movable_positions
        _wgmp = WP.get_movable_positions

        def _geo_walk(board, start_id, depth, occupants, moving_team, **kw):
            kw["neighbours"] = board.neighbours_geometric
            return _wgmp(board, start_id, depth, occupants, moving_team, **kw)
        WP.get_movable_positions = _geo_walk

        def _restore3():
            WP.get_movable_positions = saved["walk_gmp"]
            T._movement_can_continue = saved["_movement_can_continue"]
            T.MovableTilesInRange.select = _sel0
        return _restore3
    elif mutate == "stored-fly":
        # #381-r3, symetrique : le VOL relit la liste STOCKEE au lieu de la geometrie -- l'etat
        # d'AVANT ce correctif quand le `Board` est monte en `native_sym` (`playbook/scene.py`,
        # le montage de PRODUCTION).
        from engine.entities.pathfinding import fly_pathfinder as FP2
        saved["fly_gmp"] = FP2.get_movable_positions

        def _stored_fly(board, start_id, depth, occupants, moving_team):
            from engine.entities.pathfinding.walk_pathfinder import get_movable_positions as _g
            return _g(board, start_id, depth, occupants, moving_team,
                      edge=FP2.is_valid_path_node, neighbours=board.neighbours_native)
        FP2.get_movable_positions = _stored_fly

        def _restore4():
            FP2.get_movable_positions = saved["fly_gmp"]
            T._movement_can_continue = saved["_movement_can_continue"]
            T.MovableTilesInRange.select = _sel0
        return _restore4
    else:
        raise SystemExit("mutation inconnue : %r" % mutate)
    return _restore


def run(board: str = DEFAULT_BOARD, seed: int = 3811, override_range: int = DEFAULT_RANGE,
        p_units: str = "", a_units: str = "", mutate: str = "none",
        verbose: bool = True) -> dict:
    sid = _resolve_session()
    logs = ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    sf = logs / ("p381r1-%s.json" % uuid.uuid4().hex[:8])
    out: dict = {"board": board, "seed": seed, "range": override_range, "mutation": mutate}
    rid = None
    try:
        rid = _build(sf, seed, board, p_units, a_units)
        out["runner"] = rid
        state, brd, dv = _load(sid, rid)
        out["n_tiles"] = len(brd.by_id)
        blocking = sorted(list(t) for t in (
            {brd.coord(t) for t in brd.by_id
             if __import__("engine.entities.pathfinding.tile_blocking", fromlist=["x"])
             .terrain_blocks_entering(brd, t, ())}))
        out["block_entering_tiles"] = blocking
        nat = _native(sid, rid, override_range)
        out["n_units_listed"] = len(nat)
        restore = _apply_mutation(mutate)
        rows, skipped = [], []
        try:
            from engine.entities.pathfinding.fly_pathfinder import is_like_flying
            from engine.entities.traits.unit_trait import unit_trait_names
            from engine.runner.abilities.behaviours import entities_from_state
            for uid in sorted(nat):
                n = nat[uid]
                if not n:
                    # Garde FLAG (#381) NON PORTEE : un set natif VIDE n'est pas un desaccord.
                    skipped.append(uid)
                    continue
                vis = (entities_from_state(state, uid, uid).caster or {}).get("visualId")
                p = _port_pool(state, brd, uid, override_range)
                rows.append({"unitId": uid, "visualId": vis,
                             "pathfinder": "fly" if is_like_flying(unit_trait_names(vis))
                                           else "walk",
                             "n_native": len(n), "n_port": len(p), "equal": (p == n),
                             "port_extra": sorted(list(x) for x in (p - n))[:12],
                             "port_missing": sorted(list(x) for x in (n - p))[:12]})
        finally:
            restore()
        out["units"] = rows
        out["skipped_empty_native"] = skipped
        # VENTILATION PAR PATHFINDER -- le verdict porte sur les unites WALK, seules dont le foyer
        # (`walk_pathfinder`) est celui que `#381-r1` corrige. Les VOLANTES relevent d'un residu
        # DISTINCT et PREEXISTANT (`#381-r2`, cf. l'en-tete) : `FlyPathfinder$$AddNeighbours` itere
        # `GetSurroundingTiles(tile, 1)` (voisinage GEOMETRIQUE) la ou `BasePathfinder$$AddNeighbours`
        # itere la liste d'adjacence STOCKEE sur la tuile ; le port de `fly_pathfinder` reutilise la
        # seconde, donc il SOUS-ATTEINT des que le boardGraph a une arete manquante. Le meme ecart
        # frappe `ai/state_bridge._move_tiles`, qui n'a jamais ete confronte sur une unite volante.
        walk = [r for r in rows if r["pathfinder"] == "walk"]
        fly = [r for r in rows if r["pathfinder"] == "fly"]
        out["n_compared"] = len(walk)
        out["n_equal"] = sum(1 for r in walk if r["equal"])
        out["fly"] = {"n": len(fly), "n_equal": sum(1 for r in fly if r["equal"]),
                      "units": [r["unitId"] for r in fly if not r["equal"]]}
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        sf.unlink(missing_ok=True)

    # --- VERDICT DERIVE DES CHAMPS
    if out.get("n_compared", 0) == 0:
        out["ok"] = False
        out["verdict"] = (
            "NON CONCLUANT : aucune unite WALK confrontable sur %d listees (pool natif VIDE -- garde "
            "FLAG `UnitFlagsComponent$$Has(unitFlags, 1)` de "
            "`MovementQuery$$FindAnyOrAllMoveableTiles`, residu #381 NON PORTE -- ou unites toutes "
            "VOLANTES, residu #381-r2)." % out.get("n_units_listed", 0))
    elif mutate != "none":
        # Une mutation DISCRIMINE des qu'elle fait diverger une unite, WALK **ou** VOLANTE : les
        # deux mutations de voisinage (#381-r3) frappent chacune UNE seule des deux branches, et
        # ne regarder que les WALK ferait passer `stored-fly` pour NON DISCRIMINANTE.
        flym = out.get("fly") or {}
        out["ok"] = (out["n_equal"] < out["n_compared"]
                     or flym.get("n_equal", 0) < flym.get("n", 0))
        out["verdict"] = (
            "MUTATION %r : WALK %d/%d et VOLANTES %d/%d s'accordent encore -- le bras %s cet etage."
            % (mutate, out["n_equal"], out["n_compared"],
               flym.get("n_equal", 0), flym.get("n", 0),
               "DISCRIMINE" if out["ok"] else "NE DISCRIMINE PAS"))
    else:
        out["ok"] = (out["n_equal"] == out["n_compared"])
        fly = out.get("fly") or {}
        out["verdict"] = (
            "PORT %s NATIF sur les WALK : %d/%d (pool `MovableTilesInRange` == `aiMovableTiles`), "
            "%d ecartees (pool natif vide, garde FLAG non portee), %d tuile(s) block-entering ; "
            "VOLANTES %d/%d (residu #381-r2, `FlyPathfinder$$AddNeighbours`)."
            % ("==" if out["ok"] else "!=", out["n_equal"], out["n_compared"],
               len(out.get("skipped_empty_native") or []), len(blocking),
               fly.get("n_equal", 0), fly.get("n", 0)))
    if verbose:
        print("[%s/%s range=%d mutate=%s] %s"
              % (board, seed, override_range, mutate, out["verdict"]))
        for r in out.get("units", []):
            if not r["equal"]:
                print("   unit %s (%s, %s) : natif=%d port=%d  EN TROP=%s  MANQUANTES=%s"
                      % (r["unitId"], r.get("visualId"), r.get("pathfinder"),
                         r["n_native"], r["n_port"], r["port_extra"], r["port_missing"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", default=DEFAULT_BOARD, help="board CHOISI (runner.md sec.2)")
    ap.add_argument("--seed", type=int, default=3811)
    ap.add_argument("--range", dest="override_range", type=int, default=DEFAULT_RANGE)
    ap.add_argument("--p-units", default="")
    ap.add_argument("--a-units", default="")
    ap.add_argument("--mutate", choices=MUTATIONS, default="none",
                    help="GARDE ADVERSARIALE : le port est volontairement FAUX, il DOIT rougir")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(board=a.board, seed=a.seed, override_range=a.override_range,
              p_units=a.p_units, a_units=a.a_units, mutate=a.mutate, verbose=not a.json)
    if a.json:
        print(json.dumps(out, indent=1))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
