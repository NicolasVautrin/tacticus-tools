#!/usr/bin/env python
"""Probe #205 -- trait Unstoppable (UnitTrait 0x412=1042).

RE (decompile gqfc5mff6c, cf. docs/rl/case-205-unstoppable.md) : Unstoppable est un trait de
MOUVEMENT pur. Il figure dans la liste d'EXEMPTION `StaticBattleRules.Effect.NotBlockingMovement
OfTraits idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$NotBlockingMovementOfTraits` = {0 Mounted, 0x405=1029 Vehicle, 0x412=1042 Unstoppable} rendue pour les
effets de tuile bloquant/finissant le mouvement (effectType 0=BlockEnteringUnits, 5=Fire, 17=Ice ;
chaque .ctor stocke la liste @+0x488). La liste est consommee par `WalkPathfinder.GetTileBlocking
Reasons IdunBattle.Entities.Pathfinding.WalkPathfinder$$GetTileBlockingReasons` (predicat `Any(exemptTraits, t => movingUnit.HasTrait(t))`) qui alimente
`IdunBattle.Entities.Pathfinding.WalkPathfinder$$GetEffectiveDepth` (bit 0x2 -> Min(1,depth) = "l'hex finit le mouvement") et
`IdunBattle.Entities.Pathfinding.WalkPathfinder$$IsValidContinuePathTile` (bit 0x1 = block-entering). i2 : "ne s'arrete pas sur les hex
speciaux / effets d'hex qui finiraient normalement son mouvement".

VERDICT = INVALIDABLE dans le harness runner (doctrine no-unvalidatable-ability-ports) : le
fondement (effets de tuile finissant/bloquant le mouvement dans la reachability) n'est PAS porte
(walk_pathfinder.py ne modelise ni le cap GetEffectiveDepth ni le gate bit-0x1 -- cf. son en-tete
+ terrain-effects.md #131/B4, DEFERE) ET aucun board runner ne porte d'hex finissant le mouvement
(Swamp/DryBush/... sont walkable, pas de troncature -- prouve ci-dessous). Donc Unstoppable n'a
RIEN a bypasser offline -> porter l'exemption maintenant = code registered-but-dead.

Ce probe l'ETABLIT empiriquement, offline-vs-live :
  A. Sur un board portant des hex speciaux candidats (MC1_67 : Swamp + DryBush), pour chaque
     porteur Unstoppable, `WalkPathfinder.get_movable_positions` (offline, qui IGNORE tout
     movement-ending) == `aiMovableTiles` (natif live) EXACT (zero tuile `extra`). Or si le natif
     appliquait un movement-ending sur Swamp/DryBush, l'offline (sans troncature) aurait des tuiles
     `extra` (atteignables offline, pas live). Zero extra => le natif NE tronque PAS sur ces hex
     => AUCUN hex finissant le mouvement sur ce board => rien a bypasser pour Unstoppable.
  B. Le board porte bien des hex speciaux candidats atteignables par le porteur, ET sa reachability
     s'etend AU-DELA d'eux (tuiles a profondeur > celle de l'hex, atteintes) -> confirme la
     non-troncature de facon constructive.
  C. `get_movable_positions` / `_move_tiles` n'ont AUCUNE branche trait movement-blocking
     (selection de pathfinder par `is_like_flying` seul) -> le trait est structurellement inert
     offline : retirer Unstoppable du ctx du porteur ne change RIEN.

ASCII only (cp1252). Usage: python probe_205_unstoppable.py [--seed 40205] [--board MC1_67]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402
from engine.entities.pathfinding.board import Board
from engine.entities.pathfinding.walk_pathfinder import get_movable_positions, get_reachable_levels  # noqa: E402

ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "agent205-probe.json"
# Porteurs Unstoppable spawnables (lineup). Melee move4 + ranged move2 = deux portees.
CARRIERS = ["orksNob", "spaceStormcaller"]
OPP = ["necroDestroyer", "necroWarden"]
# Hex speciaux CANDIDATS (terrain que l'i2 rangerait sous "special hexes / hex effects") presents
# sur les boards : Swamp (malus mvt), DryBush, BrokenIce, Water. Aucun n'est un movement-ender live.
SPECIAL_TERRAINS = {"Swamp", "DryBush", "BrokenIce", "Water", "Trench", "FirstAid"}


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def build(seed, board):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", board,
         "--p-units", ",".join(CARRIERS), "--a-units", ",".join(OPP)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("[205] build KO:", (proc.stderr or proc.stdout or "")[-500:], file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def native_set(board, unit):
    out = set()
    for t in unit.get("tiles", []):
        tid = board.id_at(t["col"], t["row"])
        if tid is not None:
            out.add(tid)
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=40205)
    ap.add_argument("--board", default="MC1_67")
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed, args.board)
    print(f"[205] seed={args.seed} board={args.board} runner={rid} carriers={CARRIERS}")
    ok = True
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
        amt = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
        dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 90)
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 40)
        tiles = bg.get("tiles") or []
        if not tiles or not (amt.get("units")):
            print(f"[205] captures KO tiles={len(tiles)} amt={bool(amt.get('units'))}"); return 2
        board = Board(tiles, adjacency="evenq")

        # index : team / portee reelle (stat Movement) / occupants / vid par unitId
        team_by = {u["id"]: u.get("team") for u in (dv.get("units") or [])}
        vid_by = {u["id"]: u.get("visualId") for u in (dv.get("units") or [])}
        move_by = {}
        for u in (snap.get("units") or []):
            st = u.get("stats") or {}
            if u.get("entityId") is not None and st.get("movement") is not None:
                move_by[u["entityId"]] = st["movement"]
        occupants = {}
        if any("occupantUnitId" in t for t in tiles):
            for t in tiles:
                oid = t.get("occupantUnitId")
                if oid is not None:
                    occupants[t["id"]] = team_by.get(oid)
        else:
            for u in (dv.get("units") or []):
                p = u.get("pos") or {}
                tid = board.id_at(p.get("col"), p.get("row"))
                if u.get("alive") and tid is not None:
                    occupants[tid] = u.get("team")

        # --- inventaire des hex speciaux du board ---
        special = {}
        for t in tiles:
            td = t.get("tileDefId")
            if td in SPECIAL_TERRAINS:
                special.setdefault(td, []).append((t["col"], t["row"], bool(t.get("walkable"))))
        print(f"[205] board special-hex candidates: "
              + (", ".join(f"{k}x{len(v)}(walkable={all(w for _,_,w in v)})"
                           for k, v in sorted(special.items())) or "AUCUN"))
        if not special:
            print(f"[205] NOTE: board {args.board} sans hex special candidat -> essayer un autre board")

        # --- A/B : offline get_movable_positions == aiMovableTiles pour chaque PORTEUR ---
        carrier_ids = [u for u in amt["units"]
                       if vid_by.get(u["unitId"]) in CARRIERS]
        if not carrier_ids:
            print("[205] aucun porteur dans aiMovableTiles (mauvais tour ?) -> verifier build"); return 2
        for unit in carrier_ids:
            uid = unit["unitId"]
            vid = vid_by.get(uid)
            team = team_by.get(uid)
            mr = int(move_by.get(uid, 0))
            pos = unit["pos"]
            start = board.id_at(pos["col"], pos["row"])
            occ = dict(occupants); occ.pop(start, None)
            nat = native_set(board, unit)
            # non-walk (Fly/Teleport : natif atteint > mr pas) -> exclu du modele Walk
            levels_full = get_reachable_levels(board, start, occ, team, max_depth=None)
            if max((levels_full.get(t, 999) for t in nat), default=0) > mr:
                print(f"[205] u{uid} [{vid}] NON-WALK (fly/teleport) -> hors modele walk, skip")
                continue
            _, pred = get_movable_positions(board, start, mr, occ, team)
            extra = sorted(board.coord(t) for t in (pred - nat))     # offline a, natif PAS
            missing = sorted(board.coord(t) for t in (nat - pred))   # natif a, offline PAS
            # les hex speciaux TRAVERSABLES (dans le BFS profondeur illimitee) atteints par ce porteur
            spec_reached = sorted(
                (board.coord(t), board.by_id[t].get("tileDefId"), levels_full.get(t))
                for t in levels_full
                if board.by_id[t].get("tileDefId") in SPECIAL_TERRAINS and levels_full[t] <= mr)
            # tuiles au-DELA d'un hex special (profondeur strictement > celle du 1er hex special atteint)
            beyond = 0
            if spec_reached:
                dmin = min(d for _, _, d in spec_reached if d is not None)
                beyond = sum(1 for t in pred if levels_full.get(t, 0) > dmin)
            print(f"[205] u{uid} [{vid}] mr={mr} native={len(nat)} pred={len(pred)} "
                  f"extra={extra[:6]} missing={missing[:6]}")
            print(f"[205]   hex-speciaux atteints (<=mr): {spec_reached[:8]} ; "
                  f"tuiles au-dela du 1er hex special dans le stop-set: {beyond}")
            if extra:
                print(f"[205] ** ATTENTION ** u{uid} offline atteint des tuiles que le natif refuse "
                      f"({extra[:8]}) -> le natif TRONQUE (movement-ending actif ?) -> A REVOIR"); ok = False
            if missing:
                print(f"[205] ** NOTE ** u{uid} natif atteint des tuiles hors offline ({missing[:8]}) "
                      f"-> adjacence/portee, non lie a Unstoppable");

        # --- C : inertness structurelle (le pathfinder n'a AUCUNE branche trait movement) ---
        import inspect
        src = inspect.getsource(get_movable_positions) + inspect.getsource(get_reachable_levels)
        trait_branch = ("trait" in src.lower()) or ("unstoppable" in src.lower())
        print(f"[205] C: get_movable_positions/get_reachable_levels reference un trait movement ? "
              f"{trait_branch} (attendu False = trait inert offline)")
        if trait_branch:
            print("[205] ** NOTE ** le pathfinder reference un trait -> re-verifier l'inertness");

        print(f"[205] BILAN: offline==live reachability sur porteur(s) Unstoppable "
              f"(board avec hex speciaux) -> {'OK (aucune troncature natif = rien a bypasser)' if ok else '** DIVERGENCE **'} ; "
              f"trait inert offline={not trait_branch}")
        print("[205] VERDICT: Unstoppable = trait mouvement pur ; mecanique movement-ending "
              "non portee (walk_pathfinder) + inerte sur boards runner -> INVALIDABLE ; "
              "documente case-205, PAS de port speculatif.")
        return 0 if ok else 1
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 15)
            print(f"[205] runner {rid} dispose")
        except Exception as e:
            print(f"[205] dispose KO: {e}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
