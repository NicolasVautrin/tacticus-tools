#!/usr/bin/env python
"""Probe `#381-r4` -- COMBIEN les collapses IMPERATIFS de `MovableTilesInRange` sur-atteignaient.

CE QU'IL MESURE
---------------
Trois call-sites du port collapsent le noeud `IdunBattleLogic.Entities.DSLSelectors$$
MovableTilesInRange` en appel direct au pathfinder, la ou le noeud DSL homonyme
(`entities/selectors/tiles.MovableTilesInRange`) porte, depuis `#381-r1`, les DEUX etages
manquants : le gate d'expansion `BasePathfinder$$NodesInNextLevel` -> `IsValidContinuePathTile`
(#131) et le dispatch `MovementQuery$$GetPathfinderTypeForUnit` -> `UnitExtensions$$IsLikeFlying`.

  * `charge`       -- `abilities/genestealer._charge_candidate_tiles` (`HeroicFusilladeAbility$$
                      ExecuteBehaviour` et `VigilanceEternalAbility$$GetPossibleMovementTiles`) ;
  * `betrayer`     -- `operations/triggers/loki/betrayer._betrayer_stop_tile`
                      (`TheBetrayer_TakeTurnAbility$$CreateBehaviour`) ;
  * `hypersensory` -- `operations/triggers/genestealer._hypersensory_move_dest`
                      (`HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateBehaviour`), portee 1.

Le probe BALAYE, sur un board REEL de `data/boards/`, tous les couples (caster, cible) a distance
2..4 entre tuiles marchables, avec le PORTEUR REEL de chaque ability, et compte les configurations
ou la SORTIE du site (pool de charge / tuile d'arret / destination) differe entre le port LIVRE et
le port MUTE. Deux mutations, chacune remettant une lecture a son etat FAUTIF :

    --mutate no-gate   `tile_blocking.make_can_continue` -> None       (l'etat d'AVANT `#381-r4`)
    --mutate no-fly    `fly_pathfinder.is_like_flying`   -> False

Un bras dont la mutation NE CHANGE RIEN ne prouve rien, et le probe le DIT (`ok=False` en mode
mutation quand rien ne bouge ; `ok=False` en mode `none` quand le board n'est pas discriminant).

100 % OFFLINE : aucun host, aucune session, aucun runner -- le board vient du dump versionne et
l'etat est monte par `load_state`. Le pendant LIVE (atterrissage confronte au jeu) est
`tests/engine/runner/test_381r4_imperative_collapses_live.py`.

ASCII only (cp1252). Usage (depuis scripts/python) :
    python probe_381r4_imperative_collapses.py --board C2_26
    python probe_381r4_imperative_collapses.py --board EMC2_02 --site betrayer
    python probe_381r4_imperative_collapses.py --board C2_26 --mutate no-gate    # DOIT diverger
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import hexgeo                                                              # noqa: E402
import board as B                                                          # noqa: E402
import rl_collect_batch as R                                               # noqa: E402
from engine.entities.pathfinding.board import Board as EngineBoard         # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402

SITES = ("charge", "betrayer", "hypersensory")
MUTATIONS = ("none", "no-gate", "no-fly")
DEFAULT_BOARD = "C2_26"

CASTER_ID, TARGET_ID = 90101, 90202
#: porteurs REELS, lus par `unit_map.py find --ability <X>` (rank courant) :
#: HeroicFusillade + HypersensoryAbilities -> Judh `genesKelermorph` ; VigilanceEternal ->
#: Tyrith `custoKyrus` ; TheBetrayer -> Kharn `worldKharn`. AUCUN n'est `IsLikeFlying`, et aucun
#: ne porte un trait de `StaticBattleRules.Effect$$NotBlockingMovementOfTraits` (Mounted / Vehicle
#: / Unstoppable) -- le gate #131 mord donc sur les trois.
CARRIERS = {"charge": "genesKelermorph", "betrayer": "worldKharn",
            "hypersensory": "genesKelermorph"}
CHARGE_RANGE = 2          # `HeroicFusillade.constants.range` == `VigilanceEternal` GetNumberConstant(0x16)
HYPERSENSORY_ATTACKER_RANGE = 2      # `cfg_range` de `GetTilePriority` (prio 0 = dist == range)


def _engine_board(dump) -> EngineBoard:
    """`EngineBoard` depuis un dump `data/boards/` (`board.Tiles` = liste de COLONNES).

    Le dump BC ne porte NI ids de tuile NI liste d'adjacence -> ids synthetiques (col*H+row) et
    adjacence `evenq`, comme `probe_165_charge_tile_utility._engine_board`. C'est le TERRAIN
    (`tileDefId`) qui compte ici : c'est lui qui arme le repli de `terrain_blocks_entering`."""
    cols = dump["board"].get("Tiles") or []
    height = dump["board"].get("Height") or max(
        (len((c or {}).get("Tile") or []) for c in cols), default=0)
    tiles = []
    for c, col in enumerate(cols):
        for r, t in enumerate((col or {}).get("Tile") or []):
            if t is None:
                continue
            tiles.append({"id": c * height + r, "col": c, "row": r,
                          "elevation": B._effective_elevation(t.get("TileId"), t.get("Elevation", 0)),
                          "walkable": not bool(t.get("ForceUnplayable", False)),
                          "tileDefId": t.get("TileId")})
    return EngineBoard(tiles, adjacency="evenq")


def load_board(board_id: str):
    for kind in ("global", "pvp", "syncPvp"):
        p = R.BOARDS_DIR / kind / ("%s.json" % board_id)
        if p.exists():
            return _engine_board(json.loads(p.read_text(encoding="utf-8")))
    raise SystemExit("board introuvable dans data/boards/ : %s" % board_id)


def _state(board, cpos, tpos, caster_vis: str):
    units = [{"id": CASTER_ID, "visualId": caster_vis, "alive": True, "team": 1, "owner": 1,
              "pos": {"col": cpos[0], "row": cpos[1]}, "effects": []},
             {"id": TARGET_ID, "visualId": "necroWarden", "alive": True, "team": 2, "owner": 2,
              "pos": {"col": tpos[0], "row": tpos[1]}, "effects": []}]
    dv = {"currentPlayer": 1, "units": units}
    ob = {"units": [{"squadId": u["id"], "hp": 100000, "hpMax": 100000} for u in units]}
    return load_state(dv, ob, board=board)


def _apply_mutation(mutate: str):
    """Remet une lecture a son etat FAUTIF. Rend le restaurateur.

    ⚠ CE QUE CETTE MUTATION EXIGE DU FOYER, ET QUI A DEJA CEDE UNE FOIS (#10031). Patcher
    `TB.make_can_continue` / `FP.is_like_flying` ne mord QUE si le foyer consommateur
    (`services/movement_query`) resout ces noms A L'APPEL -- donc en liaison de MODULE (forme B) ou
    par un import fonction-local (forme C). Les deux y etaient en forme C a l'origine de `#381-r4` ;
    `492c722f` (« hisser 624 imports differes d'engine/ au niveau module ») les a passes en FORME A,
    et ce probe a rendu `0 sortie changee / rc 1` pendant 13 jours -- un rouge qui accusait le BOARD
    (« le bras NE DISCRIMINE PAS ») alors que c'etait la LIAISON. Mesure au retablissement en forme
    B : `no-gate` 0 -> 483 sur C2_26. Le foyer est desormais en forme B et un cliquet garde la
    MORSURE elle-meme : `tests/engine/services/test_10031_morsure_des_mutations_offline.py`."""
    from engine.entities.pathfinding import fly_pathfinder as FP
    from engine.entities.pathfinding import tile_blocking as TB
    saved = {"make_can_continue": TB.make_can_continue, "is_like_flying": FP.is_like_flying}

    def _restore():
        TB.make_can_continue = saved["make_can_continue"]
        FP.is_like_flying = saved["is_like_flying"]

    if mutate == "no-gate":
        TB.make_can_continue = lambda *a, **k: None
    elif mutate == "no-fly":
        FP.is_like_flying = lambda traits: False
    elif mutate != "none":
        raise SystemExit("mutation inconnue : %r" % mutate)
    return _restore


def _site_outputs(site: str, state, board):
    """Sortie(s) OBSERVABLE(s) du site, en (col,row) -- ce que le behaviour consomme reellement."""
    if site == "charge":
        from engine.runner.abilities.genestealer import (VIGIL_SURROUND_RADIUS, SURROUND_RADIUS,
                                                         _charge_candidate_tiles,
                                                         _hf_move_dest_tile,
                                                         _vigilance_move_dest_tile)
        pool = _charge_candidate_tiles(state, CASTER_ID, TARGET_ID, SURROUND_RADIUS, CHARGE_RANGE)
        return {"pool": tuple(board.coord(t) for t in pool),
                "dest_heroic_fusillade": _hf_move_dest_tile(state, CASTER_ID, TARGET_ID,
                                                            SURROUND_RADIUS, CHARGE_RANGE),
                "dest_vigilance_eternal": _vigilance_move_dest_tile(state, CASTER_ID, TARGET_ID,
                                                                    CHARGE_RANGE)}
    if site == "betrayer":
        from engine.runner.operations.triggers.loki.betrayer import _betrayer_stop_tile
        return {"stop_tile": _betrayer_stop_tile(state, CASTER_ID, TARGET_ID)}
    if site == "hypersensory":
        from engine.runner.operations.triggers.genestealer import _hypersensory_move_dest
        return {"move_dest": _hypersensory_move_dest(state, CASTER_ID, TARGET_ID,
                                                     HYPERSENSORY_ATTACKER_RANGE)}
    raise SystemExit("site inconnu : %r" % site)


def _sweep(board, site: str, mutate: str, max_examples: int = 6) -> dict:
    """Compare, config par config, le port LIVRE au port MUTE. `hypersensory` (portee 1) balaie
    jusqu'a distance 3 : c'est la portee utile de son `GetTilePriority`."""
    vis = CARRIERS[site]
    walk = [t for t in sorted(board.by_id) if board.walkable(t)]
    dmin, dmax = (1, 3) if site == "hypersensory" else (2, 4)
    keys, diffs, n = None, {}, 0
    examples = []
    for ct in walk:
        cpos = board.coord(ct)
        for tt in walk:
            if tt == ct:
                continue
            tpos = board.coord(tt)
            if not dmin <= hexgeo.distance(cpos, tpos) <= dmax:
                continue
            n += 1
            base = _site_outputs(site, _state(board, cpos, tpos, vis), board)
            restore = _apply_mutation(mutate)
            try:
                mut = _site_outputs(site, _state(board, cpos, tpos, vis), board)
            finally:
                restore()
            keys = keys or sorted(base)
            changed = [k for k in keys if base[k] != mut[k]]
            for k in changed:
                diffs[k] = diffs.get(k, 0) + 1
            if changed and len(examples) < max_examples:
                examples.append({"caster": list(cpos), "target": list(tpos),
                                 "livre": {k: base[k] for k in changed},
                                 "mute": {k: mut[k] for k in changed}})
    return {"n_configs": n, "n_diff_by_output": {k: diffs.get(k, 0) for k in (keys or [])},
            "examples": examples}


def run(board_id: str = DEFAULT_BOARD, sites=SITES, mutate: str = "none",
        verbose: bool = True) -> dict:
    from engine.entities.pathfinding.tile_blocking import terrain_blocks_entering
    board = load_board(board_id)
    blocking = sorted(list(board.coord(t)) for t in board.by_id
                      if terrain_blocks_entering(board, t, ()))
    out = {"board": board_id, "n_tiles": len(board.by_id),
           "block_entering_tiles": blocking, "mutation": mutate, "sites": {}}
    ref = "no-gate" if mutate == "none" else mutate
    for s in sites:
        out["sites"][s] = _sweep(board, s, ref)
    # --- VERDICT DERIVE DES CHAMPS -------------------------------------------------------------
    # En mode `none` le probe MESURE ce que le gate a retire (reference = `no-gate`, l'etat
    # d'AVANT `#381-r4`). En mode mutation il exige que la mutation DISCRIMINE.
    tot = sum(sum(v["n_diff_by_output"].values()) for v in out["sites"].values())
    if not blocking:
        out["ok"] = False
        out["verdict"] = ("NON CONCLUANT : %s ne porte AUCUNE tuile block-entering -- le gate #131 "
                          "y est inerte par construction." % board_id)
    elif mutate == "no-fly":
        # AUCUN porteur des 4 abilities n'est `IsLikeFlying` -> ce bras est attendu INERTE, et
        # c'est un RESULTAT, pas un echec : il dit que le dispatch fly n'est pas confrontable ici.
        out["ok"] = True
        out["verdict"] = ("DISPATCH FLY : %d sortie(s) changee(s) sur %s -- attendu 0 (aucun "
                          "porteur de ces abilities ne porte Flying/Burrow ; l'etage est porte "
                          "par fidelite, non confrontable sur ces carriers)."
                          % (tot, board_id))
    else:
        out["ok"] = tot > 0
        out["verdict"] = ("%s : %d sortie(s) de site changee(s) par le gate #131 sur %s (%d tuile(s) "
                          "block-entering). %s"
                          % ("SUR-ATTEINTE MESUREE" if mutate == "none" else "MUTATION no-gate",
                             tot, board_id, len(blocking),
                             "" if tot else "Le bras NE DISCRIMINE PAS -- il ne prouve rien."))
    out["n_diff_total"] = tot
    if verbose:
        print("[%s mutate=%s] %s" % (board_id, mutate, out["verdict"]))
        for s, v in out["sites"].items():
            print("  site=%-13s configs=%-5d  %s" % (s, v["n_configs"], v["n_diff_by_output"]))
            for ex in v["examples"][:2]:
                print("      c=%s t=%s livre=%s mute=%s"
                      % (ex["caster"], ex["target"], ex["livre"], ex["mute"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", default=DEFAULT_BOARD, help="id d'un board de data/boards/")
    ap.add_argument("--site", choices=SITES + ("all",), default="all")
    ap.add_argument("--mutate", choices=MUTATIONS, default="none")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    sites = SITES if a.site == "all" else (a.site,)
    out = run(board_id=a.board, sites=sites, mutate=a.mutate, verbose=not a.json)
    if a.json:
        print(json.dumps(out, indent=1))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
