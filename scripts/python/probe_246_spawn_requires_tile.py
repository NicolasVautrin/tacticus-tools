#!/usr/bin/env python
"""probe_246_spawn_requires_tile -- LE SPAWN NAIT DE LA TUILE, jamais l'inverse.

CE QUE CE PROBE MESURE
----------------------
`IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute` (branche `SpawnUnitOptions+0x60 == 0`,
la branche par DEFAUT) est un `foreach` sur son tile-selecteur :

    tiles = tileSelector.Select(ctx);                    // *(behaviour+0x58)
    if (options.<+0x60> == 0)
        foreach (tile in tiles)
            e = AddUnitOperation.Execute(unitConfig, [tile.Id], playerId, 2, options);
            if (e != null) results.Add(e);
    else
        e = AddUnitOperation.Execute(unitConfig, GetTileIds(tiles), playerId, 2, options);

-> l'entite NAIT DE L'ITERATION. **Zero tuile iteree = zero entite**, donc zero `On(UnitAdded)` et
zero `TriggerSpawnedUnitBehaviours`. Le `count` d'une ability n'est PAS un compteur d'unites : il
vit dans le tile-selecteur (`First(<tri>, count)` rend **min(count, len(source))**).

Le port faisait l'inverse dans `SpawnUnitOperation.execute` / `.execute_self_replica` : `for _ in
range(count)` creait l'entite PUIS lui cherchait une place, et ne posait la `PositionComponent` que
`if tile is not None`. Cible encerclee -> summon FANTOME sans position (mesure #251 :
`spawned = [1, 2]`, un des deux hors plateau), que rien ne ramasse ensuite.

Le cas est devenu ATTEIGNABLE avec le masque de 1007 `ScarabHive` (`0x4020` =
`TargetHasFreeAdjacentTile | TargetIsEnemy`, cf. case-250-summon-targeting) : le bit 5 exige >= 1
voisine libre, mais **une seule suffit** alors que l'ability en spawne 2.

MONTAGE (drive, jamais subi)
----------------------------
Runner `--no-ai`, deux `necroSpyder` (un par mesure -- un cast consomme l'ability du caster) et
assez de CORPS pour saturer une couronne.

  * phase SATUREE  : cible = un ennemi dont la couronne libre vaut exactement 2 ; le caster en
    consomme UNE en venant au contact (`RANGE_ADJACENT`) -> il en reste **1** pour 2 summons ;
    saturation complementaire par `applyAction move` si le board n'offre pas ce cas d'emblee.
  * CONTRE-EPREUVE : cible = l'ennemi a la couronne libre la plus LARGE -> >= 2 restent apres le
    caster, les 2 summons doivent naitre, tous positionnes. Un correctif qui tuerait le fantome en
    tuant des spawns legitimes serait pire que le defaut.

Les deux faces sont mesurees : NATIF (`abilityReason` puis `applyAction {kind: ability}`, unites
apparues comptees par **DIFFERENCE D'IDS** de `decisionView` -- jamais par `visualId`, le visuel
d'un spawn n'est pas l'id gameconfig du summon, piege #248) et PORT (`load_state` de l'etat d'AVANT
le cast puis `SpawnUnitOperation.execute`, avec detection des entites creees SANS
`PositionComponent`).

Usage (depuis scripts/python, session Frida chaude) :
    python probe_246_spawn_requires_tile.py
    python probe_246_spawn_requires_tile.py --board C3_26 --seed 31337

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
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

import hexgeo                                                        # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.components import PositionComponent               # noqa: E402
from engine.runner.operations.spawn import SpawnUnitOperation        # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

SCARAB_HIVE = 1007
CASTER_VIS = "necroSpyder"
SUMMON_ABILITY = "ScarabHive"
SUMMON_COUNT = 2                  # nb d'invocations de ScarabHive (arg du `.ctor AActiveAbility`)
P_UNITS = "necroSpyder,necroSpyder,necroOverlord"
A_UNITS = "necroWarden,necroWarden,necroWarden"
_seq = itertools.count()


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _build(sid, seed: str, board: str):
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, qui est versionne)."""
    state = ROOT / "logs" / ("_probe246-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--p-units", P_UNITS, "--a-units", A_UNITS]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True)
        if state.exists():
            rid = json.loads(state.read_text()).get("runnerId")
            if rid:
                print("[build] runner %s (seed=%s board=%s)" % (rid, seed, board))
                return int(rid), state
        if time.time() > deadline:
            raise RuntimeError("build KO: %s / %s" % (p.stdout[-600:], p.stderr[-600:]))
        time.sleep(10)


def _dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _act(sid, rid, action, timeout=120):
    return _r(sid, "applyAction", {"runnerId": rid, "action": action}, timeout)


def _pos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def _alive(dv):
    return [u for u in (dv.get("units") or []) if u.get("alive")]


def _ids(dv):
    return {int(u["id"]) for u in _alive(dv)}


def _by_id(dv, uid):
    for u in _alive(dv):
        if int(u["id"]) == int(uid):
            return u
    return None


def _movable(sid, rid, uid):
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    for m in (mov.get("units") or []):
        if int(m.get("unitId") or -1) == int(uid):
            return [(t["col"], t["row"]) for t in (m.get("tiles") or []) if t.get("col") is not None]
    return []


def _wait_movable(sid, rid, unit_id, maxit=6):
    """Tuiles de deplacement de `unit_id`, en enchainant les `endturn` jusqu'a ce que SON camp ait la
    main (runner `--no-ai` : rien ne bouge tout seul)."""
    for _ in range(maxit):
        t = _movable(sid, rid, unit_id)
        if t:
            return t
        _act(sid, rid, {"kind": "endturn"}, 60)
    return []


def _turn_of(sid, rid, uid, maxit=8):
    for _ in range(maxit):
        d = _dv(sid, rid)
        me = _by_id(d, uid)
        if me is not None and me.get("ctrl"):
            return d
        _act(sid, rid, {"kind": "endturn"}, 60)
    return _dv(sid, rid)


# --------------------------------------------------------------------------- geometrie

def _ring(board: Board, tile_id) -> list:
    """`CanAddUnit(AdjacentTiles(target))`, volet STATIQUE : le champ BRUT `neighbours` du
    `boardGraph` (l'ordre et la porte d'elevation `|dElev| < 2` sont deja ceux de
    `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles`), restreint aux tuiles WALKABLE."""
    if tile_id is None:
        return []
    return [t for t in board.neighbours_native(tile_id) if board.walkable(t)]


def _free_ring(board: Board, dv: dict, tile_id) -> list:
    occupied = set()
    for u in _alive(dv):
        c, r = _pos(u)
        if c is None:
            continue
        t = board.id_at(c, r)
        if t is not None:
            occupied.add(t)
    return [t for t in _ring(board, tile_id) if t not in occupied]


def _tile_of(board: Board, u: dict):
    c, r = _pos(u)
    return board.id_at(c, r) if c is not None else None


def _bring_adjacent(sid, rid, board, mover_id, goal_tile, rounds=12) -> bool:
    """DEPLACE `mover_id` jusqu'a occuper une voisine de `goal_tile`. On DEPLACE, on ne subit pas la
    geometrie : la cible de deplacement est la voisine LIBRE la plus proche, et on abandonne
    seulement quand deux tours consecutifs ne rapprochent plus."""
    stalled = 0
    for _ in range(rounds):
        dv = _dv(sid, rid)
        me = _by_id(dv, mover_id)
        if me is None:
            return False
        cur = _tile_of(board, me)
        ring = _ring(board, goal_tile)
        if cur in ring:
            return True
        free = _free_ring(board, dv, goal_tile)
        goals = [board.coord(t) for t in (free or ring)] or [board.coord(goal_tile)]
        tiles = _wait_movable(sid, rid, mover_id)
        if not tiles:
            return False
        here = _pos(me)
        d_here = min(hexgeo.distance(here, g) for g in goals)
        best = min(tiles, key=lambda t: (min(hexgeo.distance(t, g) for g in goals), t))
        d_best = min(hexgeo.distance(best, g) for g in goals)
        if d_best >= d_here:
            stalled += 1
            if stalled >= 2:
                return False
        else:
            stalled = 0
        _act(sid, rid, {"kind": "move", "unitId": int(mover_id),
                        "to": {"col": best[0], "row": best[1]}}, 90)
    dv = _dv(sid, rid)
    me = _by_id(dv, mover_id)
    return me is not None and _tile_of(board, me) in _ring(board, goal_tile)


def _saturate(sid, rid, board, target_id, keep_free=1, rounds=6) -> int:
    """Amene des CORPS sur les voisines de la cible jusqu'a n'en laisser que `keep_free` libres.
    Rend le nombre de voisines libres atteint."""
    for _ in range(rounds):
        dv = _dv(sid, rid)
        tgt = _by_id(dv, target_id)
        if tgt is None:
            return -1
        ttile = _tile_of(board, tgt)
        free = _free_ring(board, dv, ttile)
        if len(free) <= keep_free:
            return len(free)
        others = [u for u in _alive(dv) if int(u["id"]) != int(target_id)
                  and _tile_of(board, u) not in _ring(board, ttile)]
        if not others:
            return len(free)
        others.sort(key=lambda u: hexgeo.distance(_pos(u), _pos(tgt)))
        moved = False
        for cand in others[:3]:
            if _bring_adjacent(sid, rid, board, int(cand["id"]), ttile, rounds=8):
                moved = True
                break
        if not moved:
            break
    dv = _dv(sid, rid)
    tgt = _by_id(dv, target_id)
    return len(_free_ring(board, dv, _tile_of(board, tgt))) if tgt is not None else -1


# --------------------------------------------------------------------------- mesure

def _offline_spawn(sid, rid, board, caster_id, target_id):
    """Rejoue `SpawnUnitOperation.execute` sur l'etat LIVE fige (l'etat d'AVANT le cast natif)."""
    dec = _dv(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 120)
    state = load_state(dec, ob, snap, board=board)
    if state.get_entity(caster_id) is None or state.get_entity(target_id) is None:
        return {"error": "caster/cible absents offline"}
    import gameconfig as GC
    vis = ((GC.ability(SUMMON_ABILITY) or {}).get("constants") or {}).get("unitId")
    before = set(state.entities)
    ids = SpawnUnitOperation.execute(state, caster_id, target_id, SUMMON_ABILITY, vis, SUMMON_COUNT)
    new = set(state.entities) - before
    ghosts = sorted(i for i in new
                    if state.get_entity(i).get_component(PositionComponent) is None)
    poses = []
    for i in ids:
        pc = state.get_entity(i).get_component(PositionComponent)
        poses.append((pc.col, pc.row) if pc is not None else None)
    return {"ids": list(ids), "positions": poses, "ghosts": ghosts, "n_new": len(new)}


def _native_cast(sid, rid, caster_id, target_id):
    """Cast NATIF de 1007 ; rend les ids APPARUS (diff d'ids, jamais le visualId -- piege #248)."""
    reason = _r(sid, "abilityReason", {"runnerId": rid, "casterId": int(caster_id),
                                       "abilityType": SCARAB_HIVE, "targetId": int(target_id)}, 60)
    before = _ids(_dv(sid, rid))
    res = _act(sid, rid, {"kind": "ability", "casterId": int(caster_id),
                          "abilityType": SCARAB_HIVE, "targetId": int(target_id)}, 180)
    dv = _dv(sid, rid)
    new = sorted(_ids(dv) - before)
    return {"reason": reason, "mutated": (res or {}).get("mutated"), "ids": new,
            "positions": [_pos(_by_id(dv, i)) for i in new]}


def _free_up(sid, rid, board, target_id, caster_id, want_free, rounds=4) -> int:
    """L'INVERSE de `_saturate` : ECARTE de la couronne les corps qui la bouchent (jamais le caster,
    jamais la cible) jusqu'a `want_free` voisines libres -- pour que la CONTRE-EPREUVE ait vraiment
    de quoi poser les 2 summons."""
    for _ in range(rounds):
        dv = _dv(sid, rid)
        tgt = _by_id(dv, target_id)
        if tgt is None:
            return -1
        ttile = _tile_of(board, tgt)
        ring = _ring(board, ttile)
        free = _free_ring(board, dv, ttile)
        if len(free) >= want_free:
            return len(free)
        blockers = [u for u in _alive(dv)
                    if int(u["id"]) not in (int(target_id), int(caster_id))
                    and _tile_of(board, u) in ring]
        if not blockers:
            return len(free)
        mover = int(blockers[0]["id"])
        tiles = _wait_movable(sid, rid, mover)
        away = [t for t in tiles if board.id_at(t[0], t[1]) not in ring]
        if not away:
            return len(_free_ring(board, _dv(sid, rid), ttile))
        best = max(away, key=lambda t: (hexgeo.distance(t, _pos(tgt)), t))
        _act(sid, rid, {"kind": "move", "unitId": mover,
                        "to": {"col": best[0], "row": best[1]}}, 90)
    dv = _dv(sid, rid)
    tgt = _by_id(dv, target_id)
    return len(_free_ring(board, dv, _tile_of(board, tgt))) if tgt is not None else -1


def _n_free(sid, rid, board, target_id) -> int:
    dv = _dv(sid, rid)
    tgt = _by_id(dv, target_id)
    return len(_free_ring(board, dv, _tile_of(board, tgt))) if tgt is not None else -1


def _tune_free(sid, rid, board, target_id, caster_id, want: int, rounds=3) -> int:
    """CONVERGE la couronne libre de la cible vers `want`, dans les DEUX sens (saturer / ecarter).
    Le cas le plus discriminant (`want == 1` pour un `count` de 2) est fragile : trop de corps et le
    natif REFUSE le cast (bit 5), pas assez et la mesure ne discrimine plus rien."""
    for _ in range(rounds):
        n = _n_free(sid, rid, board, target_id)
        if n == want or n < 0:
            return n
        if n > want:
            _saturate(sid, rid, board, target_id, keep_free=want)
        else:
            _free_up(sid, rid, board, target_id, caster_id, want)
    return _n_free(sid, rid, board, target_id)


def _phase(sid, rid, board, caster_id, target_id, label, want_free):
    """Place le caster au contact, ajuste la couronne, mesure PORT puis NATIF."""
    dv = _dv(sid, rid)
    tgt = _by_id(dv, target_id)
    if tgt is None:
        return {"error": "cible absente"}
    # le caster doit POUVOIR venir au contact : on lui degage une voisine s'il n'en reste plus.
    _free_up(sid, rid, board, target_id, caster_id, 1)
    if not _bring_adjacent(sid, rid, board, caster_id, _tile_of(board, tgt)):
        return {"error": "caster pas amene au contact"}
    # `want_free` = la couronne libre VISEE **apres** que le caster en ait consomme une.
    _tune_free(sid, rid, board, target_id, caster_id,
               want_free if want_free is not None else SUMMON_COUNT)
    dv = _dv(sid, rid)
    tgt = _by_id(dv, target_id)
    n_free = len(_free_ring(board, dv, _tile_of(board, tgt)))
    print("  [%s] caster u%s au contact de u%s : voisines libres = %d"
          % (label, caster_id, target_id, n_free))
    port = _offline_spawn(sid, rid, board, caster_id, target_id)
    _turn_of(sid, rid, caster_id)
    nat = _native_cast(sid, rid, caster_id, target_id)
    print("  [%s] NATIF reason=%s ids=%s pos=%s" % (label, nat["reason"], nat["ids"], nat["positions"]))
    print("  [%s] PORT  ids=%s pos=%s fantomes=%s"
          % (label, port.get("ids"), port.get("positions"), port.get("ghosts")))
    return {"n_free": n_free, "native": nat, "port": port}


def _setup(sid, rid):
    """Board + casters + ennemis d'un runner fraichement bati."""
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = _dv(sid, rid)
    casters = [u for u in _alive(dv) if u.get("visualId") == CASTER_VIS]
    if not casters:
        raise RuntimeError("aucun %s sur le plateau" % CASTER_VIS)
    own = casters[0].get("owner")
    foes = [u for u in _alive(dv) if u.get("owner") != own]
    if not foes:
        raise RuntimeError("aucun ennemi")
    return board, dv, casters, own, foes


def _run_saturee(sid, seed, board_name) -> dict:
    """Runner DEDIE : plateau vierge, on vise la couronne la plus etroite encore castable.
    Un runner par phase -- les summons de l'autre phase bouchent la geometrie et rendent le
    montage non reproductible (mesure : la phase saturee echouait 1 fois sur 2 en runner partage)."""
    rid, statefile = _build(sid, seed, board_name)
    out = {}
    try:
        board, dv, casters, own, foes = _setup(sid, rid)
        scored = sorted(foes, key=lambda u: len(_free_ring(board, dv, _tile_of(board, u))))
        cands = [u for u in scored if len(_free_ring(board, dv, _tile_of(board, u))) >= 1]
        print("[saturee] cibles candidates : %s"
              % [(u["id"], len(_free_ring(board, dv, _tile_of(board, u)))) for u in cands])
        res = {"error": "aucune cible tenable"}
        for cand in cands:
            res = _phase(sid, rid, board, int(casters[0]["id"]), int(cand["id"]),
                         "saturee", want_free=1)
            if not res.get("error"):
                break
        out["saturee"] = res
        # ENCERCLEE (offline seul) : zero voisine libre -> le natif REFUSE le cast (bit 5
        # `TargetHasFreeAdjacentTile`), `SpawnUnitBehaviour$$Execute` n'est jamais atteint.
        # L'Operation portee, elle, DOIT rendre [] sans creer la moindre entite -- le fantome
        # d'origine dans sa forme pure.
        dv = _dv(sid, rid)
        walled = [u for u in _alive(dv) if u.get("owner") != own
                  and not _free_ring(board, dv, _tile_of(board, u))]
        if walled:
            wid = int(walled[0]["id"])
            reason = _r(sid, "abilityReason",
                        {"runnerId": rid, "casterId": int(casters[0]["id"]),
                         "abilityType": SCARAB_HIVE, "targetId": wid}, 60)
            port = _offline_spawn(sid, rid, board, int(casters[0]["id"]), wid)
            print("  [encerclee] cible u%s : NATIF refuse=%s | PORT ids=%s entites_creees=%s"
                  % (wid, ((reason or {}).get("targetReason") or {}).get("hex"),
                     port.get("ids"), port.get("n_new")))
            out["encerclee"] = {"n_free": 0, "native_reason": reason, "port": port}
        return out
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
        Path(statefile).unlink(missing_ok=True)
        print("[cleanup] runner %s dispose" % rid)


def _run_contre(sid, seed, board_name) -> dict:
    """Runner DEDIE : la couronne la plus LARGE, aucune saturation -> les 2 summons doivent naitre."""
    rid, statefile = _build(sid, seed, board_name)
    try:
        board, dv, casters, own, foes = _setup(sid, rid)
        wide = max(foes, key=lambda u: len(_free_ring(board, dv, _tile_of(board, u))))
        print("[contre] cible u%s (libres=%d)"
              % (wide["id"], len(_free_ring(board, dv, _tile_of(board, wide)))))
        return {"contre": _phase(sid, rid, board, int(casters[0]["id"]), int(wide["id"]),
                                 "contre", want_free=None)}
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
        Path(statefile).unlink(missing_ok=True)
        print("[cleanup] runner %s dispose" % rid)


def run_one(sid, seed: str, board_name: str, only: str = "all") -> dict:
    out = {"seed": seed, "board": board_name}
    if only in ("all", "saturee"):
        out.update(_run_saturee(sid, seed, board_name))
    if only in ("all", "contre"):
        out.update(_run_contre(sid, seed, board_name))
    return out


def _verdict(res: dict) -> list:
    """`min(count, libres)` des DEUX cotes, et ZERO entite sans position cote port."""
    lines = []
    for phase in ("contre", "saturee"):
        if phase not in res:
            continue                                    # phase non jouee (`--only`)
        d = res.get(phase) or {}
        if d.get("error"):
            lines.append("  [%s] ECHEC MONTAGE : %s" % (phase, d["error"]))
            continue
        nat, port = d.get("native") or {}, d.get("port") or {}
        n_free = d.get("n_free")
        n_nat, n_port = len(nat.get("ids") or []), len(port.get("ids") or [])
        ghosts = port.get("ghosts") or []
        want = min(SUMMON_COUNT, n_free or 0)
        discr = " (NON DISCRIMINANT : libres >= count)" if (phase == "saturee"
                                                            and (n_free or 0) >= SUMMON_COUNT) else ""
        ok = (n_nat == n_port == want) and not ghosts
        lines.append("  [%s] libres=%s attendu=min(%d,%s)=%d natif=%d port=%d fantomes=%d -> %s%s"
                     % (phase, n_free, SUMMON_COUNT, n_free, want, n_nat, n_port,
                        len(ghosts), "OK" if ok else "KO", discr))
    enc = res.get("encerclee")
    if enc:
        port = enc.get("port") or {}
        hexr = ((enc.get("native_reason") or {}).get("targetReason") or {}).get("hex")
        ok = (not port.get("ids")) and not port.get("n_new")
        lines.append("  [encerclee] libres=0 natif_refuse=%s port_ids=%d entites_creees=%d -> %s"
                     % (hexr, len(port.get("ids") or []), port.get("n_new") or 0,
                        "OK" if ok else "KO"))
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=None, help="un seul board (defaut : les deux couples)")
    ap.add_argument("--seed", default=None)
    ap.add_argument("--only", default="all", choices=("all", "saturee", "contre"),
                    help="ne jouer qu'une phase (chaque phase = un runner dedie)")
    a = ap.parse_args(argv)
    couples = ([(a.seed or "777", a.board)] if a.board
               else [("777", "MC1_67"), ("31337", "C3_26")])
    sid = _resolve_session()
    print("[session] %s" % sid)
    results = []
    for seed, board in couples:
        print("\n=== %s / seed %s ===" % (board, seed))
        try:
            results.append(run_one(sid, seed, board, only=a.only))
        except Exception as exc:                                   # noqa: BLE001
            print("  ECHEC : %s" % exc)
            results.append({"seed": seed, "board": board, "error": str(exc)})
    print("\n=== BILAN ===")
    for res in results:
        print(" %s / %s" % (res.get("board"), res.get("seed")))
        if res.get("error"):
            print("  ERREUR : %s" % res["error"])
            continue
        for line in _verdict(res):
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
