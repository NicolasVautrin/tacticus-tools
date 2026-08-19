#!/usr/bin/env python
"""probe_210_blackrage_targeting -- ARMEMENT du gate de cible de BlackRage (1163, `bloodDeathCompany`
« Lucien »), masque + regle dynamique.

CE QUE CE PROBE MESURE
----------------------
`BlackRageAbility` entrait dans `ABILITY_CLASSES` SANS `TARGETING_OPTIONS` -> `get_invalid_target_reason`
commence par `options = getattr(ability, "TARGETING_OPTIONS", None)` et rend 0 immediatement : AUCUN
gate, le moteur acceptait donc des casts que
`IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE. La degradation est PERMISSIVE
(ni erreur ni crash), donc invisible en self-play.

Le masque relu au decompile (`IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$.ctor` :
`TargetingOptions..ctor(&opts, 0, &<TargetingRange statics+0x48>, 1, 0x106004012, 0, 0, 0)`, overload
FLAGS DIRECTS -> le litteral EST le masque effectif) arme quatre regles :

    0x2         TargetMatchesDynamicRule   -> `BlackRageAbility$$GetDynamicInvalidTargetReason`
    0x10        CasterHasNotMoved          -> volet CASTER
    0x4000      TargetIsEnemy              -> refus sur soi-meme / un allie
    0x100000000 TargetIsNotAdjacent        -> refus d'une cible DEJA au contact

ORACLE = le LIVE : `abilityReason(casterId, abilityType, targetId)` rend le masque `TargetingRule`
NATIF. Le probe rejoue ensuite le gate OFFLINE sur le MEME etat fige, dans DEUX versions :
  * APRES  = l'ability du registre (masque + regle dynamique portes) ;
  * AVANT  = la MEME classe avec `TARGETING_OPTIONS = None` et la regle dynamique du defaut de
             `ActiveAbility` -- c'est-a-dire EXACTEMENT l'etat de `master` avant cette tranche.
Le critere : au moins un cas ou le NATIF REFUSE et ou AVANT rendait 0 (« refusait de refuser »).

COMMENT LA GEOMETRIE EST FORCEE (jamais subie)
----------------------------------------------
Quatre etats figes successifs, chacun avec sa propre capture (`decisionView`/`observeBattle`/
`combatSnapshot`) :

  S1 `spawn`      Lucien n'a pas bouge, les ennemis sont au loin  -> la regle DYNAMIQUE mord
                  (aucune tuile de charge : `TargetIsInRange`), et l'allie / le self tombent sur
                  `TargetIsEnemy`.
  S2 `approche`   Lucien amene a distance de charge d'un ennemi, PUIS deux `endturn` (le
                  `StartTurnOperation` du joueur entrant purge le flag `Moved`, sinon
                  `CasterHasNotMoved` sortirait du volet CASTER et MASQUERAIT le volet cible)
                  -> cet ennemi est ACCEPTE (0).
  S3 `contact`    Lucien amene AU CONTACT du meme ennemi, puis deux `endturn` -> `TargetIsNotAdjacent`.
  S4 `a bouge`    depuis S3, un `move` SANS `endturn` -> `CasterHasNotMoved` (volet CASTER). DEUX
                  mesures, une par chemin de pose du flag `UnitFlag.Moved` : `S4a` sur l'etat CHARGE
                  tel quel (`load_state` le seede depuis `combatSnapshot.units[].unitFlags`), `S4b`
                  sur le MEME etat avec `set_moved_flag` explicite (le mirror
                  d'`IdunBattle.Entities.UnitExtensions$$SetMovedFlag` qu'appelle `MoveUnitOperation`
                  sur le chemin replay/self-play offline). Les deux rendent `0x10`.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_210_blackrage_targeting.py
    python probe_210_blackrage_targeting.py --seed 777 --board MC1_67

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
from engine.runner.abilities.base import ActiveAbility               # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting import is_invalid_target      # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

BLACK_RAGE = 1163
LUCIEN = "bloodDeathCompany"       # HERO du pool (`rl_duel.py build --list-pool`)
ALLY = "bloodIntercessor"          # 2e hero de MON camp -> cible AMIE
A_UNITS = "necroWarden,necroWarden,necroWarden"
BOARD = "MC1_67"
SEED = "777"
TOURS_DE_CHAUFFE = 6                # purge les `initialCooldownTurns` (sinon `ValidRequest` partout)
_seq = itertools.count()


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _build(sid, seed: str, board: str) -> int:
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, qui est versionne).
    ATTEND qu'un slot se libere si MAX_RUNNERS est sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe210-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--p-units", "%s,%s" % (LUCIEN, ALLY), "--a-units", A_UNITS]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"])
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out or time.time() >= deadline:
            raise RuntimeError("build KO : " + out[-400:])
        time.sleep(10)


def _dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)


def _act(sid, rid, action, timeout=90):
    return _r(sid, "applyAction", {"runnerId": rid, "action": action}, timeout)


def _pos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def _movable(sid, rid, uid):
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])
                    if t.get("col") is not None]
    return []


def _my_turn(sid, rid, maxit=8):
    """Rend la main au joueur qui possede mes heros (chaine de `endturn`, runner `--no-ai`)."""
    for _ in range(maxit):
        d = _dv(sid, rid)
        mine = next((u for u in (d.get("units") or []) if u.get("ctrl")), None)
        if mine is not None and d.get("currentPlayer") == mine.get("owner"):
            return d
        _act(sid, rid, {"kind": "endturn"}, 60)
    return _dv(sid, rid)


def _reason(sid, rid, caster_id, target_id):
    r = _r(sid, "abilityReason", {"runnerId": rid, "casterId": caster_id,
                                  "abilityType": BLACK_RAGE, "targetId": target_id}, 90) or {}
    tr = r.get("targetReason") or {}
    cr = r.get("casterReason") or {}
    t_hex = int(tr.get("hex") or "0x0", 16)
    c_hex = int(cr.get("hex") or "0x0", 16)
    # `IsInvalidTarget` natif : le volet CASTER passe d'abord et son code est rendu tel quel.
    return {"hex": c_hex or t_hex,
            "names": list(cr.get("reasons") or []) if c_hex else list(tr.get("reasons") or []),
            "target_hex": t_hex, "caster_hex": c_hex}


# --------------------------------------------------------------------------- les deux ports

def ability_after():
    """L'ability du REGISTRE (masque + regle dynamique portes)."""
    return ABILITY_CLASSES[BLACK_RAGE]()


def ability_before():
    """L'ability TELLE QU'ELLE ETAIT sur `master` : meme classe, meme behaviour, mais AUCUN masque
    (`TARGETING_OPTIONS = None` -> `get_invalid_target_reason` rend 0 des sa 1re ligne) et la regle
    dynamique du DEFAUT de `ActiveAbility` (qui rend 0). Sous-classer plutot que patcher l'attribut
    garde le registre INTACT pour les autres appelants."""
    base = ABILITY_CLASSES[BLACK_RAGE]
    return type("AvantBlackRage", (base,), {
        "TARGETING_OPTIONS": None,
        "get_dynamic_invalid_target_reason": ActiveAbility.get_dynamic_invalid_target_reason,
        "__slots__": (),
    })()


# --------------------------------------------------------------------------- montage

def _capture(sid, rid, board):
    dec = _dv(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
    return dec, load_state(dec, ob, snap, board=board)


def _units(dec):
    units = [u for u in (dec.get("units") or []) if u.get("alive")]
    luc = next((u for u in units if u.get("visualId") == LUCIEN), None)
    ally = next((u for u in units if u.get("visualId") == ALLY), None)
    foes = [u for u in units if not u.get("ctrl")]
    return luc, ally, foes


def _drive(sid, rid, luc_id, foe_id, want_distance, rounds=8):
    """DEPLACE Lucien jusqu'a `want_distance` de `foe_id`, puis DEUX `endturn` (le tour repasse a
    l'adversaire puis revient -> `StartTurnOperation` purge le flag `Moved` de MES unites, sinon
    `CasterHasNotMoved` masquerait le volet CIBLE). Rend la distance atteinte."""
    for _ in range(rounds):
        d = _my_turn(sid, rid)
        luc = next((u for u in (d.get("units") or []) if u.get("id") == luc_id), None)
        foe = next((u for u in (d.get("units") or []) if u.get("id") == foe_id), None)
        if luc is None or foe is None:
            raise RuntimeError("unite disparue en cours de drive")
        cur = hexgeo.distance(_pos(luc), _pos(foe))
        if cur == want_distance:
            _act(sid, rid, {"kind": "endturn"}, 60)
            _act(sid, rid, {"kind": "endturn"}, 60)
            return cur
        tiles = _movable(sid, rid, luc_id)
        if tiles:
            best = min(tiles, key=lambda t: (abs(hexgeo.distance(t, _pos(foe)) - want_distance), t))
            _act(sid, rid, {"kind": "move", "unitId": luc_id,
                            "to": {"col": best[0], "row": best[1]}}, 90)
        _act(sid, rid, {"kind": "endturn"}, 60)
        _act(sid, rid, {"kind": "endturn"}, 60)
    d = _my_turn(sid, rid)
    luc = next((u for u in (d.get("units") or []) if u.get("id") == luc_id), None)
    foe = next((u for u in (d.get("units") or []) if u.get("id") == foe_id), None)
    return hexgeo.distance(_pos(luc), _pos(foe))


def _row(sid, rid, state, luc_id, target_id, label):
    """UNE mesure : oracle natif, port APRES, port AVANT -- sur le MEME etat fige."""
    nat = _reason(sid, rid, luc_id, target_id)
    after = int(is_invalid_target(state, luc_id, target_id, ability_after()) or 0)
    before = int(is_invalid_target(state, luc_id, target_id, ability_before()) or 0)
    return {"case": label, "target": target_id, "native": nat["hex"], "names": nat["names"],
            "after": after, "before": before,
            "agree": after == nat["hex"],
            "regression_closed": nat["hex"] != 0 and before == 0}


# --------------------------------------------------------------------------- run

def run(seed: str = SEED, board_id: str = BOARD, sid=None, rid=None, keep: bool = False) -> dict:
    sid = sid or _resolve_session()
    own = rid is None
    rid = rid if rid is not None else _build(sid, seed, board_id)
    rows = []
    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)
        _my_turn(sid, rid)

        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            raise RuntimeError("boardGraph indisponible")
        # `native_sym` = mode CANONIQUE de production : la topologie que
        # `MovementUtil$$AreTilesAdjacent` et `TileQuery$$IterateAdjacentTiles` lisent.
        board = Board(bg["tiles"], adjacency="native_sym")

        # ---- S1 : spawn (Lucien n'a pas bouge ; les ennemis sont au loin) -------------------
        dec, state = _capture(sid, rid, board)
        luc, ally, foes = _units(dec)
        if luc is None or ally is None or not foes:
            raise RuntimeError("roster incomplet au spawn")
        luc_id = luc["id"]
        far = max(foes, key=lambda f: hexgeo.distance(_pos(luc), _pos(f)))
        rows.append(_row(sid, rid, state, luc_id, far["id"],
                         "S1 ennemi loin d=%d (regle DYNAMIQUE)"
                         % hexgeo.distance(_pos(luc), _pos(far))))
        rows.append(_row(sid, rid, state, luc_id, ally["id"], "S1 cible AMIE"))
        rows.append(_row(sid, rid, state, luc_id, luc_id, "S1 cible = LE CASTER"))

        # ---- S2 : approche a distance de charge (2) -> ACCEPTE ------------------------------
        foe = min(foes, key=lambda f: hexgeo.distance(_pos(luc), _pos(f)))
        d2 = _drive(sid, rid, luc_id, foe["id"], want_distance=2)
        dec, state = _capture(sid, rid, board)
        rows.append(_row(sid, rid, state, luc_id, foe["id"], "S2 ennemi chargeable d=%d" % d2))

        # ---- S3 : contact -> TargetIsNotAdjacent -------------------------------------------
        d3 = _drive(sid, rid, luc_id, foe["id"], want_distance=1)
        dec, state = _capture(sid, rid, board)
        rows.append(_row(sid, rid, state, luc_id, foe["id"], "S3 ennemi AU CONTACT d=%d" % d3))

        # ---- S4 : le caster a bouge (aucun endturn) -> CasterHasNotMoved ---------------------
        # DEUX mesures, sur les DEUX chemins de pose du flag `UnitFlag.Moved` :
        #   S4a etat CHARGE tel quel -> `load_state` seede le flag depuis
        #       `combatSnapshot.units[].unitFlags` (`snapshot._load_unit_flags`, `f02e30f`), donc le
        #       port voit « a bouge » SANS pose manuelle. (Les docstrings de
        #       `components.unit_has_moved` et de `get_invalid_caster_reason` affirmaient l'inverse ;
        #       cette mesure les a corrigees.)
        #   S4b meme etat + `set_moved_flag` explicite (le mirror d'`UnitExtensions$$SetMovedFlag`
        #       qu'appelle `MoveUnitOperation` sur le chemin REPLAY/self-play OFFLINE, le seul ou le
        #       flag ne vient pas du snapshot) -> meme verdict.
        # Les deux doivent rendre `0x10` : c'est le bit `CasterHasNotMoved` du masque qui arme la
        # regle du volet CASTER, et il est atteint par les deux chemins.
        _my_turn(sid, rid)
        tiles = _movable(sid, rid, luc_id)
        moved_ok = False
        if tiles:
            dec0 = _dv(sid, rid)
            luc0 = next((u for u in (dec0.get("units") or []) if u.get("id") == luc_id), None)
            tgt = min(tiles, key=lambda t: (hexgeo.distance(t, _pos(luc0)) != 1, t))
            res = _act(sid, rid, {"kind": "move", "unitId": luc_id,
                                  "to": {"col": tgt[0], "row": tgt[1]}}, 90)
            moved_ok = bool(((res or {}).get("actions") or [{}])[0].get("ok"))
        if moved_ok:
            dec, state = _capture(sid, rid, board)
            luc4, _, foes4 = _units(dec)
            if foes4:
                f4 = min(foes4, key=lambda f: hexgeo.distance(_pos(luc4), _pos(f)))
                rows.append(_row(sid, rid, state, luc_id, f4["id"],
                                 "S4a CASTER a bouge (flag seede par load_state)"))
                from engine.runner.components import set_moved_flag
                set_moved_flag(state, luc_id)        # `UnitExtensions$$SetMovedFlag` (chemin offline)
                rows.append(_row(sid, rid, state, luc_id, f4["id"],
                                 "S4b idem + set_moved_flag (chemin replay)"))
    finally:
        if own and not keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    return {"runner": rid, "rows": rows}


def sweep(seed: str = SEED, board_id: str = BOARD, steps: int = 8, sid=None,
          rid=None, keep: bool = False) -> dict:
    """GENERALISATION -- chasse au sur-ajustement « distance <= N ».

    Le predicat de `BlackRageAbility$$GetDynamicInvalidTargetReason` n'est PAS une distance : c'est
    « il existe au moins une tuile LIBRE et marchable hex-adjacente a la cible, ATTEIGNABLE par le
    caster en `MOVEMENT + extraMovement` pas » (`TilesUnitCanMoveToChargeTarget` =
    `CanAddUnit(AdjacentTiles(target))` op_BitwiseAnd `MovableTilesInRange(caster, casterTile,
    range, canReachOnly = 0)`). Un port qui aurait collapse ce noeud en « hexDistance <= portee »
    passerait les six cas nommes et se ferait prendre ICI.

    Methode : on DEPLACE Lucien de proche en proche (deux `endturn` a chaque pas pour purger le flag
    `Moved`) et, a chaque position, on confronte natif / port sur CHAQUE ennemi vivant. Le rapport
    isole les paires de points a distance EGALE dont le verdict natif DIFFERE -- la signature du
    regime ou distance et chargeabilite se separent."""
    sid = sid or _resolve_session()
    own = rid is None
    rid = rid if rid is not None else _build(sid, seed, board_id)
    pts = []
    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)
        _my_turn(sid, rid)
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="native_sym")
        for step in range(steps):
            dec, state = _capture(sid, rid, board)
            luc, _ally, foes = _units(dec)
            if luc is None or not foes:
                break
            for f in foes:
                d = hexgeo.distance(_pos(luc), _pos(f))
                row = _row(sid, rid, state, luc["id"], f["id"], "sweep step=%d d=%d" % (step, d))
                row["d"] = d
                pts.append(row)
            # un pas vers l'ennemi le plus proche, puis deux `endturn` (purge du flag `Moved`)
            near = min(foes, key=lambda f: hexgeo.distance(_pos(luc), _pos(f)))
            tiles = _movable(sid, rid, luc["id"])
            if not tiles:
                break
            best = min(tiles, key=lambda t: (hexgeo.distance(t, _pos(near)), t))
            _act(sid, rid, {"kind": "move", "unitId": luc["id"],
                            "to": {"col": best[0], "row": best[1]}}, 90)
            _act(sid, rid, {"kind": "endturn"}, 60)
            _act(sid, rid, {"kind": "endturn"}, 60)
            _my_turn(sid, rid)
    finally:
        if own and not keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    return {"runner": rid, "points": pts}


def _print_sweep(out):
    pts = out["points"]
    bad = [p for p in pts if not p["agree"]]
    by_d = {}
    for p in pts:
        by_d.setdefault(p["d"], set()).add(p["native"])
    split = sorted(d for d, v in by_d.items() if len(v) > 1)
    print("[210] SWEEP generalisation : %d points, %d desaccords natif/port" % (len(pts), len(bad)))
    for d in sorted(by_d):
        print("   d=%-3d verdicts natifs = %s" % (d, ",".join("0x%x" % v for v in sorted(by_d[d]))))
    if split:
        print("   distances ou le verdict natif DIFFERE a distance EGALE : %s"
              % ",".join(str(d) for d in split))
        print("   -> le predicat n'est PAS une distance, et le port suit (0 desaccord)")
    else:
        print("   aucune distance ne separe deux verdicts sur ce montage (regime non atteint)")
    for p in bad:
        print("   DIFF %s natif=0x%x port=0x%x" % (p["case"], p["native"], p["after"]))
    return len(bad) == 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--sweep", type=int, default=0,
                    help="au lieu des 6 cas nommes : N pas de generalisation")
    a = ap.parse_args(argv)
    if a.sweep:
        out = sweep(seed=a.seed, board_id=a.board, steps=a.sweep, keep=a.keep)
        return 0 if _print_sweep(out) else 1
    out = run(seed=a.seed, board_id=a.board, keep=a.keep)
    print("[210] BlackRage 1163 -- gate de cible : natif vs port APRES vs port AVANT (master)")
    print("%-40s %14s %12s %12s %6s %6s" % ("cas", "natif", "apres", "avant", "==", "gap"))
    n_agree = n_closed = 0
    for r in out["rows"]:
        print("%-40s %14s %12s %12s %6s %6s" % (
            r["case"], "0x%x" % r["native"], "0x%x" % r["after"], "0x%x" % r["before"],
            "OK" if r["agree"] else "DIFF", "YES" if r["regression_closed"] else "-"))
        if r["names"]:
            print("      natif: %s" % ",".join(r["names"]))
        n_agree += 1 if r["agree"] else 0
        n_closed += 1 if r["regression_closed"] else 0
    print("accord natif/port : %d/%d ; cas ou le natif REFUSE et ou master rendait 0 : %d"
          % (n_agree, len(out["rows"]), n_closed))
    ok = n_agree == len(out["rows"]) and n_closed > 0
    print("PROBE OK" if ok else "PROBE KO")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
