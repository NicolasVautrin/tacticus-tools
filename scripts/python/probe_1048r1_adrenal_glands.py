#!/usr/bin/env python
"""probe_1048r1_adrenal_glands -- `AdrenalGlands_Effect` (EffectType 0x419 = 1049), passif du
summon `tyranSmnHormagaunt` et des CINQ npc Hormagaunt. Residu `#1018-r1`, ferme par #1048.

LA QUESTION BINAIRE
-------------------
L'ensemble des tuiles ou le porteur peut S'ARRETER, cote port, est-il EXACTEMENT celui du natif --
sur une geometrie ou le bonus CHANGE cet ensemble ?

CE QUE LE DECOMPILE DIT (build `rnca9r7q6c`)
--------------------------------------------
`AdrenalGlandsEffect$$CreateRangeBonusForMovement` = `{Trigger: null, ExtraRange:
GetNumberConstant(0xe = extraMovement), ExtraRangeCondition: tile => IsValidExtraMove(owner, tile),
ReduceRange: null}`. `ReduceRange` etant nul, `MovementQuery$$MovementRangeWithAppliedBonus`
n'augmente RIEN : tout passe par `GetExtraReachableTiles`, une tuile a la fois, chacune devant
satisfaire `IsValidExtraMove` -- << la destination amene au contact d'un ennemi qui ne l'etait PAS,
et par l'une de ses tuiles les plus proches >>. RE complete : `entities/effects/loki/adrenal_glands.py`.

POURQUOI CETTE GEOMETRIE-LA, ET PAS UNE AUTRE
----------------------------------------------
⚠ Un accord en regime DEGENERE ne prouve rien, et c'est MESURE ici : sur le premier montage essaye
(Hormagaunt @(2,2), ennemi @(2,5)), natif et port rendaient les MEMES 26 tuiles... et le bonus
n'ajoutait **RIEN** -- les tuiles au contact etaient deja atteignables en 3 pas. Le montage retenu
place l'ennemi a `(3,7)`, choisi parce qu'AUCUN de ses voisins n'est a <= 3 pas du porteur et
qu'un seul, `(3,6)`, est a exactement 4 : le bonus AJOUTE donc une tuile et une seule, et c'est
elle qui separe les deux hypotheses.

TROIS VOLETS
------------
  A. ACCORD    -- `aiMovableTiles` (natif) vs `get_movable_tiles_for` (port), sur le PORTEUR et sur
                  les DEUX unites SANS le passif (rayon de souffle : elles doivent rester egales).
  B. MORSURE   -- le meme calcul port avec le canal de bonus DESARME : l'ensemble doit PERDRE
                  exactement la ou les tuiles extra. Sans ce volet, le volet A serait vert meme si
                  le bonus etait un no-op.
  C. CONDITION -- le meme calcul port avec `ExtraRangeCondition` REMPLACEE par `True` : l'ensemble
                  doit GONFLER. C'est ce qui prouve que `IsValidExtraMove` FILTRE, et pas seulement
                  qu'`ExtraRange` s'applique.

PIEGE DE MONTAGE (mesure #1018) : les Hormagaunts portent `InstinctiveBehaviour_BlockMovement`
(<< si une cible est a portee, cette unite ne bouge pas >>) -- le porteur est donc pose HORS PORTEE
de tout ennemi, sinon le trait masquerait l'effet mesure.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc                        # noqa: E402

from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.entities.pathfinding.pathfinders import movable_positions_for_unit  # noqa: E402
from engine.entities.pathfinding.tile_blocking import make_can_continue    # noqa: E402
from engine.entities.stats import StatType                                 # noqa: E402
from engine.runner.components import (OwnerComponent, PositionComponent,   # noqa: E402
                                      StatsComponent, UnitComponent)
from engine.runner.snapshot import load_state                              # noqa: E402
from engine.services.movement_query import (get_extra_reachable_tiles,     # noqa: E402
                                            get_movable_tiles_for,
                                            get_range_bonus_for_unit,
                                            synapse_tiles_for,
                                            titanhammer_target_tiles_for,
                                            unit_has_effect_fn)

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
_seq = itertools.count()

CARRIER = "tyranNpc1Hormagaunt"     # npc porteur (npc-registry.tsv), monte par --explicit-stats
SEED = "777"
BOARD = "MC1_67"
CARRIER_POS = (2, 2)
#: choisi par balayage du board : AUCUN voisin a <= 3 pas du porteur, UN SEUL a exactement 4.
FOE_POS = (3, 7)
EXTRA_ATTENDUE = {(3, 6)}


def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout) or {}
    return out.get("result", out) if isinstance(out, dict) else out


def _build(sid) -> "tuple[int, Path]":
    state = ROOT / "logs" / ("_probe1048r1-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD, "--no-ai",
            "--state-file", str(state),
            "--p-units", "%s,ultraTitus,ultraApothecary" % CARRIER,
            "--explicit-stats", CARRIER,
            "--a-units", "ultraTitus,ultraApothecary,ultraCalgar",
            "--place", "%s:%d,%d" % (CARRIER, CARRIER_POS[0], CARRIER_POS[1]),
            "--place", "ultraTitus:0,0", "--place", "ultraApothecary:1,0",
            "--a-place", "ultraTitus:%d,%d" % (FOE_POS[0], FOE_POS[1]),
            "--a-place", "ultraApothecary:6,8", "--a-place", "ultraCalgar:5,8"]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"]), state
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out and "runner creation paused" not in out:
            raise RuntimeError("build KO : " + out[-400:])
        if time.time() >= deadline:
            raise RuntimeError("build KO (cap/drain jamais libere) : " + out[-400:])
        time.sleep(10)


def _occupants(state, board, skip: int) -> dict:
    out = {}
    for uid, e in state.entities.items():
        if int(uid) == int(skip):
            continue
        uc, pc, oc = (e.get_component(UnitComponent), e.get_component(PositionComponent),
                      e.get_component(OwnerComponent))
        if uc is None or not uc.alive or pc is None:
            continue
        cell = board.by_coord.get((pc.col, pc.row))
        if cell is not None:
            out[int(cell["id"])] = oc.team if oc is not None else None
    return out


def _port_sets(state, board, uid: int) -> "tuple[set, set, set]":
    """`(avec bonus, sans bonus, sans CONDITION)` en POSITIONS -- les trois volets."""
    e = state.get_entity(int(uid))
    pc, oc, sc = (e.get_component(PositionComponent), e.get_component(OwnerComponent),
                  e.get_component(StatsComponent))
    team = oc.team if oc is not None else None
    occ = _occupants(state, board, uid)
    tid = int(board.by_coord[(pc.col, pc.row)]["id"])
    mv = int(sc.ctx.stat(StatType.MOVEMENT)) if (sc is not None and sc.ctx is not None) else 0
    traits = (sc.ctx.traits if (sc is not None and sc.ctx is not None) else None) or []
    hef = unit_has_effect_fn(state, uid)
    cc = make_can_continue(getattr(state, "effects", None), traits, board=board)
    avec = {board.coord(int(t)) for t in
            get_movable_tiles_for(board, state, int(uid), tid, mv, occ, team)}
    # --- B : le MEME calcul sans le canal de bonus (mirror de `rangeBonuses == []`)
    visited, stop = movable_positions_for_unit(
        board, tid, mv, occ, team, traits=traits, has_effect=hef, can_continue=cc,
        teleport_target_tiles=titanhammer_target_tiles_for(state, board, team),
        synapse_tiles=synapse_tiles_for(state, board, team))
    sans = {board.coord(int(t)) for t in stop}
    # --- C : le MEME calcul avec `ExtraRangeCondition` neutralisee (tout passe)
    bonuses = get_range_bonus_for_unit(state, board, int(uid), occ, team)
    libre = set(sans)
    reach = set(visited)
    for b in bonuses:
        nu = type(b)(extra_range=b.extra_range, extra_range_condition=None,
                     reduce_range=b.reduce_range)
        extra = get_extra_reachable_tiles(board, reach, int(uid), nu, occ, team, traits, hef,
                                          can_continue=cc)
        reach |= extra
        libre |= {board.coord(int(t)) for t in extra}
    return avec, sans, libre


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner")
    args = ap.parse_args()
    sid = _resolve_session()
    print("[probe_1048r1] session %s" % sid)
    rid, state_file = _build(sid)
    ko = 0
    try:
        dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
        ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        sn = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="native_sym") if (bg or {}).get("tiles") else None
        if board is None:
            print("[probe_1048r1] KO : boardGraph vide")
            return 1
        state = load_state(dv, ob, sn, board=board)
        vis = {int(u["id"]): u.get("visualId") for u in (dv.get("units") or [])}
        natif = {int(m["unitId"]): {(t.get("col"), t.get("row")) for t in (m.get("tiles") or [])}
                 for m in (mov.get("units") or []) if m.get("unitId") is not None}
        if not natif:
            print("[probe_1048r1] KO : aiMovableTiles vide (%s)" % (mov.get("error") or mov))
            return 1
        for uid in sorted(natif):
            avec, sans, libre = _port_sets(state, board, uid)
            ajout = avec - sans
            porteur = vis.get(uid) == CARRIER
            ok = (avec == natif[uid])
            ko |= 0 if ok else 1
            print("[A] %s u%-4d [%-22s] natif=%-3d port=%-3d %s"
                  % ("OK " if ok else "KO ", uid, vis.get(uid), len(natif[uid]), len(avec),
                     "" if ok else "DIFF natif\\port=%s port\\natif=%s"
                     % (sorted(natif[uid] - avec), sorted(avec - natif[uid]))))
            if porteur:
                okb = (ajout == EXTRA_ATTENDUE)
                ko |= 0 if okb else 1
                print("[B] %s PORTEUR : le bonus AJOUTE %s (attendu %s) -- sans lui n=%d"
                      % ("OK " if okb else "KO ", sorted(ajout), sorted(EXTRA_ATTENDUE), len(sans)))
                okc = (libre - sans) > ajout
                ko |= 0 if okc else 1
                print("[C] %s CONDITION : sans elle le bonus ajouterait %d tuiles (%s), avec elle %d"
                      % ("OK " if okc else "KO ", len(libre - sans), sorted(libre - sans),
                         len(ajout)))
            elif ajout:
                ko |= 1
                print("[B] KO  u%d n'a PAS le passif et recoit pourtant %s" % (uid, sorted(ajout)))
    finally:
        if not args.keep:
            subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file",
                            str(state_file)], cwd=str(PYDIR), capture_output=True, text=True)
    print("[probe_1048r1] %s" % ("KO" if ko else "OK"))
    return ko


if __name__ == "__main__":
    raise SystemExit(main())
