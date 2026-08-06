#!/usr/bin/env python
"""Probe R20 : COMPTAGE des tirages MT consommes par l'on-appearance de ScarabSummon (1047).

Rabattre la feuille `SpawnReplica` sur le corps unique
`IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute` change la CONSOMMATION RNG.
Cette sonde la CHIFFRE dans les deux regimes, au lieu de l'argumenter :

  * HORS PORTEE : le double apparait a >= 2 hex du premier ennemi (son arme est une MELEE de portee 1,
    cf. `IdunBattle.Core.Services.TargetingQuery$$GetRange`). Le corps unique ne produit AUCUNE attaque
    -> seul le `PickRandomly(CanAddUnit(AdjacentTiles(self@0x160)), 1)` du placement tire (loi #130 :
    1 tirage meme a pool de taille 1). L'ancien fork, lui, roulait un degat COMPLET pour une attaque
    que le natif n'execute jamais -> ses tirages en trop desynchronisaient le flux.
  * AU CONTACT : le double frappe -> placement + rolls de degat + le vecteur after-hit
    (`On(0x26)`/`On(8)`/`On(9)`), que l'ancien fork sautait entierement.

Le compteur est `IntBasedMersenneTwister` : nombre de `genrand_int32` observes (sous-classe locale,
aucune modification du moteur).

MESURE (seed 31337, board MC1_67) :
    regime            AVANT (fork)                          APRES (corps unique)
    hors portee       1 attaque, 4860 degats, 6 tirages  ->  0 attaque, 1 tirage
    au contact        1 attaque, 4860 degats, 6 tirages,     1 attaque, 4860 degats (IDENTIQUES),
                      after_hit=False                        12 tirages, after_hit=True
6 = 1 placement (`PickRandomly`) + 5 coups de l'arme du swarm. Hors portee les 5 rolls disparaissent
(degat roule pour une attaque que le natif n'execute jamais) ; au contact les 6 tirages en plus sont
ceux du vecteur after-hit (`On(9)` -> reaction Hypersensory de Judh). Le total de degat ne bouge PAS :
l'etage degat est intact, tout le delta MT est attribuable aux deux proprietes portees.

Usage: python probe_r20_replica_rng_flow.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_r20_rng_state.json"
SPYDER = "necroSpyder"
ALLY = "bloodIntercessor"
JUDH = "genesKelermorph"
FILLER = "necroWarden"


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def _counting_rng(seed_state):
    """MT cale sur l'etat live, instrumente : `.draws` = nombre de genrand_int32."""
    from engine.runner.prng import IntBasedMersenneTwister

    class _Counting(IntBasedMersenneTwister):
        def __init__(self):
            super().__init__()
            self.draws = 0

        def genrand_int32(self):
            self.draws += 1
            return super().genrand_int32()

    rng = _Counting()
    rng.mt = list(seed_state["mt"])
    rng.mti = seed_state["mti"]
    return rng


def _load(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 40)
    s0 = _r(sid, "dumpRng", {"runnerId": rid}, 30)
    state = load_state(dv, ob, snap, board=board)
    state.rng = _counting_rng(s0)
    return state, board, dv


def _pick(dv, vis, taken):
    u = next((x for x in (dv.get("units") or [])
              if x.get("visualId") == vis and x.get("alive") and x["id"] not in taken), None)
    if u is not None:
        taken.add(u["id"])
    return u


def _put(state, board, uid, tile):
    from engine.runner.components import PositionComponent
    pc = state.get_entity(uid).get_component(PositionComponent)
    pc.col, pc.row = board.coord(tile)


def _make_scarab(state, spyder_id):
    import gameconfig as GC
    from engine.runner.components import PositionComponent
    from engine.runner.operations.spawn import SpawnUnitOperation
    vid = ((GC.ability("ScarabHive") or {}).get("constants") or {}).get("unitId")
    ids = SpawnUnitOperation.execute(state, spyder_id, spyder_id, "ScarabHive", vid, 1)
    if not ids:
        return None
    return ids[0] if state.get_entity(ids[0]).get_component(PositionComponent) is not None else None


def _run_replica(state, scarab_id):
    from engine.dsl.effects import ExecutionContext
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.runner.abilities.loki import scarab_summon_tree
    ectx = ExecutionContext(state=state, rng=state.rng)
    scarab_summon_tree().execute(entities_from_state(state, scarab_id), ectx)
    return [p for n, p in ectx.emitted if n == "ReplicaOnAppearance"]


def _far(board, anchors, mind):
    from collections import deque
    banned = set()
    for a in anchors:
        seen, q = {a: 0}, deque([a])
        while q:
            x = q.popleft()
            if seen[x] >= mind - 1:
                continue
            for n in board.neighbours(x):
                if n not in seen:
                    seen[n] = seen[x] + 1
                    q.append(n)
        banned |= set(seen)
    return next((t for t in sorted(board.by_id) if board.walkable(t) and t not in banned), None)


def _build(sid, p_units, a_units):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.unlink(missing_ok=True)
    subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", "31337",
                    "--state-file", str(STATE), "--board", "MC1_67", "--roster", "1",
                    "--p-units", p_units, "--a-units", a_units,
                    "--hp-target", "300000", "--hp-player", "300000"],
                   cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
                   errors="replace")
    if not STATE.exists():
        return None
    return json.loads(STATE.read_text())["runnerId"]


def _regime_out_of_range(sid):
    """Le double apparait loin de tout ennemi -> AUCUNE attaque attendue (gate de portee)."""
    rid = _build(sid, f"{SPYDER},{ALLY}", f"{FILLER},{FILLER}")
    if rid is None:
        return None
    try:
        state, board, dv = _load(sid, rid)
        taken = set()
        spyder, ally = _pick(dv, SPYDER, taken), _pick(dv, ALLY, taken)
        e1, e2 = _pick(dv, FILLER, taken), _pick(dv, FILLER, taken)
        if not all((spyder, ally, e1, e2)):
            return None
        c_tile = ez = None
        for cand in sorted(board.by_id):
            if not (board.walkable(cand) and sum(1 for n in board.neighbours(cand)
                                                 if board.walkable(n)) >= 2):
                continue
            ez = next((z for z in (_far(board, [cand], m) for m in (8, 7, 6, 5, 4))
                       if z is not None), None)
            if ez is not None:
                c_tile = cand
                break
        if c_tile is None:
            return None
        park = _far(board, [c_tile, ez], 3)
        for uid, t in ((e1["id"], ez), (e2["id"], ez), (ally["id"], ez), (spyder["id"], park)):
            _put(state, board, uid, t)
        scarab = _make_scarab(state, spyder["id"])
        if scarab is None:
            return None
        _put(state, board, scarab, c_tile)
        d0 = state.rng.draws
        attacks = _run_replica(state, scarab)
        return {"draws": state.rng.draws - d0, "attacks": len(attacks)}
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)


def _regime_in_contact(sid):
    """Le double apparait AU CONTACT de Judh -> attaque + vecteur after-hit."""
    rid = _build(sid, f"{SPYDER},{ALLY},{ALLY},{ALLY},{ALLY}", f"{JUDH},{FILLER}")
    if rid is None:
        return None
    try:
        state, board, dv = _load(sid, rid)
        taken = set()
        spyder = _pick(dv, SPYDER, taken)
        allies = [_pick(dv, ALLY, taken) for _ in range(4)]
        judh, filler = _pick(dv, JUDH, taken), _pick(dv, FILLER, taken)
        if not (spyder and judh and filler and all(allies)):
            return None
        blockers = [spyder["id"]] + [a["id"] for a in allies]
        trio = None
        for c in sorted(board.by_id):
            if not board.walkable(c):
                continue
            nb = [n for n in board.neighbours(c) if board.walkable(n)]
            if not (2 <= len(nb) <= len(blockers) + 1):
                continue
            for p in nb:
                js = [j for j in board.neighbours(p)
                      if board.walkable(j) and j != c and j not in nb]
                if js:
                    trio = (c, p, js[0], [n for n in nb if n != p])
                    break
            if trio:
                break
        if trio is None:
            return None
        c_tile, p_tile, j_tile, block_tiles = trio
        park = _far(board, [c_tile, p_tile, j_tile], 4)
        for uid in [spyder["id"]] + [a["id"] for a in allies] + [filler["id"]]:
            _put(state, board, uid, park)
        _put(state, board, judh["id"], j_tile)
        scarab = _make_scarab(state, spyder["id"])
        if scarab is None:
            return None
        _put(state, board, scarab, c_tile)
        for tile, uid in zip(block_tiles, blockers):
            _put(state, board, uid, tile)
        d0 = state.rng.draws
        attacks = _run_replica(state, scarab)
        return {"draws": state.rng.draws - d0, "attacks": len(attacks),
                "total": (attacks[0].get("total") if attacks else None),
                "after_hit": bool(attacks and attacks[0].get("after_hit"))}
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)


def main() -> int:
    sid = _resolve_session()
    out = _regime_out_of_range(sid)
    print(f"[R20/rng] HORS PORTEE  -> {out}")
    inc = _regime_in_contact(sid)
    print(f"[R20/rng] AU CONTACT   -> {inc}")
    print("[R20/rng] attendu apres de-fork : hors portee = 1 tirage (PickRandomly seul, 0 attaque) ; "
          "au contact = placement + rolls de degat + after-hit (1 attaque)")
    return 0 if (out and inc) else 1


if __name__ == "__main__":
    sys.exit(main())
