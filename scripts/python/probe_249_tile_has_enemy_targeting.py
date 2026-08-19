#!/usr/bin/env python
"""probe_249_tile_has_enemy_targeting -- CONFRONTATION de la regle `TargetTileHasEnemyUnit`
(bit 19, `0x80000`) portee par #249, sur ses porteurs Astra Militarum 1017 `FragBomb`
(`astraBullgryn`) et 1026 `BasiliskBarrage` (`astraOrdnance`).

⚠ ETAT : **NON CONFRONTE LIVE** au moment de son ecriture -- le jeu passait du build `gqfc5mff6c`
au build `rnca9r7q6c` et aucun runner n'etait montable. Le port lui-meme est lu au DECOMPILE de
`gqfc5mff6c` (ghidra-mcp + `data/symbols/gqfc5mff6c/`), coherent avec lui-meme ; ce probe est le
montage a REJOUER apres la migration de build. Ne PAS melanger une lecture du decompile
`gqfc5mff6c` avec une mesure prise sur `rnca9r7q6c` : re-lire d'abord.

CE QUE MESURE CE PROBE
----------------------
La clause native, VERBATIM de `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`
(surcharge 7 arguments), imbriquee dans la clause du bit 17 et juste avant `TargetIsNotAdjacent` :

    if ((rules & 0x80000) != 0
        && ( TileExtensions.IsEmptyOrSteppable(<cible resolue>, state)
             || !TargetingQuery.UnitsCanAttackEachOther(caster, GetUnit(target)) ))
       -> GenericBrokenTargetingRule(0x80000)

DEUX termes, DEUX resolutions de la cible qu'il ne faut pas confondre (le module a paye deux fois
cette erreur, #251/#254 sur `GetUnitFeetIds` et #250 sur `TargetTileIsFree`) :
  * 1er terme sur `GetMainTile(target)` (les 4 porteurs du bit sont `TargetIsTile`) ;
  * 2e terme sur `UnitExtensions$$GetUnit(target, state)`, qui resout une TUILE en son OCCUPANT.

MONTAGE DISCRIMINANT -- LA MEME TUILE, TROIS ETATS
--------------------------------------------------
Une seule tuile `T`, choisie ADJACENTE au caster de 1017 (`RANGE_ADJACENT`, sinon la portee
refuserait EN AMONT du bit 19 et masquerait la mesure) et walkable (sinon la branche `TargetIsTile`
rend `ValidRequest` avant). 1026 est `RANGE_WHOLE_BOARD` : la meme tuile lui convient.

    phase VIDE   -> T sans occupant                  ->  natif DOIT refuser 0x80000
    phase ALLIE  -> un allie du caster deplace sur T ->  natif DOIT refuser 0x80000
    phase ENNEMI -> un ennemi deplace sur T          ->  natif DOIT ACCEPTER (0)

Seule la 3e passe. C'est ce triplet qui separe les deux termes : la phase VIDE n'exerce QUE
`IsEmptyOrSteppable`, la phase ALLIE n'exerce QUE `UnitsCanAttackEachOther` (la tuile est occupee
par une unite non-Steppable, donc le 1er terme est faux).

`astraOrdnance` (1026) n'est JAMAIS deplace : son masque porte `CasterHasNotMoved` (0x10), et un
`move` ferait rendre `0x10` au volet CASTER pour toutes les cibles -- l'oracle ne dirait alors plus
rien du bit 19.

CONTREFACTUELS, COMPTES DANS LES DEUX SENS
-------------------------------------------
Cinq versions du port sur le MEME etat fige :
  * apres      = l'ability du registre ;
  * avant      = `TARGETING_OPTIONS = None` -- l'etat d'avant #115 (aucun gate) ;
  * sansBit19  = le masque MOINS le seul bit 19 -- LE contrefactuel qui isole cette regle ;
  * sansRules  = `rules = 0` (le volet PORTEE reste arme) ;
  * sansRange  = `range = None` (le masque reste arme).
Les desaccords sont comptes en faux-ACCEPT **et** en faux-REFUS : un champ dont la neutralisation
ne deplace AUCUN verdict est INERTE sur ce montage, et le rapport le dit tel quel plutot que de le
maquiller.

MODE `--offline-cascade` -- CE QUI A PU ETRE MESURE SANS LE JEU
---------------------------------------------------------------
Le meme triplet, joue sur une grille 5x5 synthetique et TROIS entites, contre la cascade PORTEE
seule (aucun oracle natif). Il ne prouve PAS l'accord avec le jeu -- il prouve que la clause portee
DECIDE bien les trois cas, et que le contrefactuel `sansBit19` DEPLACE des verdicts (la regle n'est
pas inerte). C'est la seule preuve exécutable pendant la migration de build ; elle ne dispense pas
du mode live.

Usage (depuis scripts/python) :
    python probe_249_tile_has_enemy_targeting.py --offline-cascade   # aucun jeu requis
    python probe_249_tile_has_enemy_targeting.py                     # LIVE, session Frida chaude
    python probe_249_tile_has_enemy_targeting.py --seed 31337 --board C1_02

Deux couples board/seed sont attendus pour conclure en live (le defaut MC1_67/777, puis
C1_02/31337). ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
import time
from dataclasses import replace as _replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                        # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting import (get_invalid_caster_reason,   # noqa: E402
                                               get_invalid_target_reason)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

FRAG_BOMB = 1017               # `astraBullgryn` -- RANGE_ADJACENT
BASILISK_BARRAGE = 1026        # `astraOrdnance` -- RANGE_WHOLE_BOARD + CasterHasNotMoved

BULL = "astraBullgryn"         # porteur 1017 (HERO, pool)
ORD_ = "astraOrdnance"         # porteur 1026 (HERO, pool)
FILLER = "astraCreed"          # 3e allie -- c'est LUI qu'on pose sur T en phase ALLIE
FOE_VIS = "necroWarden"

P_UNITS = ",".join([BULL, ORD_, FILLER])
A_UNITS = ",".join([FOE_VIS] * 3)
BOARD = "MC1_67"
SEED = "777"
TOURS_DE_CHAUFFE = 4
VARIANTS = ("apres", "avant", "sansBit19", "sansRules", "sansRange")
PHASES = ("VIDE", "ALLIE", "ENNEMI")
_seq = itertools.count()


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _build(sid, seed: str, board: str):
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, qui est versionne).
    ATTEND qu'un slot se libere si MAX_RUNNERS est sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe249-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--p-units", P_UNITS, "--a-units", A_UNITS]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"]), state
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out or time.time() >= deadline:
            raise RuntimeError("build KO : " + out[-500:])
        time.sleep(10)


def _dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _act(sid, rid, action, timeout=90):
    return _r(sid, "applyAction", {"runnerId": rid, "action": action}, timeout)


def _pos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def _by_vis(dec, vis):
    for u in (dec.get("units") or []):
        if u.get("visualId") == vis and u.get("alive"):
            return u
    return None


def _movable(sid, rid, uid):
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])
                    if t.get("col") is not None]
    return []


def _wait_movable(sid, rid, unit_id, maxit=6):
    """Tuiles de deplacement de `unit_id`, en enchainant les `endturn` jusqu'a ce que SON camp ait la
    main. On ne COMPTE surtout pas les `endturn` : quand toutes les unites d'un camp ont agi le
    moteur bascule DEJA seul, et un `endturn` de plus decalerait la parite."""
    for _ in range(maxit):
        t = _movable(sid, rid, unit_id)
        if t:
            return t
        _act(sid, rid, {"kind": "endturn"}, 60)
    return []


def _place_on(sid, rid, unit_id, goal, rounds=8) -> bool:
    """Amene `unit_id` EXACTEMENT sur `goal` (col,row), en plusieurs tours si le deplacement d'un
    seul ne suffit pas. On DEPLACE les unites pour obtenir la configuration voulue -- on ne subit
    jamais la geometrie de spawn."""
    for _ in range(rounds):
        d = _dv(sid, rid)
        u = next((x for x in (d.get("units") or [])
                  if int(x["id"]) == int(unit_id) and x.get("alive")), None)
        if u is None:
            return False
        if _pos(u) == tuple(goal):
            return True
        tiles = _wait_movable(sid, rid, int(unit_id))
        if not tiles:
            return False
        if tuple(goal) in tiles:
            _act(sid, rid, {"kind": "move", "unitId": int(unit_id),
                            "to": {"col": goal[0], "row": goal[1]}}, 90)
            continue
        best = min(tiles, key=lambda t: (hexgeo.distance(t, goal), t))
        if best == _pos(u):
            return False
        _act(sid, rid, {"kind": "move", "unitId": int(unit_id),
                        "to": {"col": best[0], "row": best[1]}}, 90)
    return False


def _vacate(sid, rid, unit_id, avoid, rounds=6) -> bool:
    """Eloigne `unit_id` d'au moins 2 hexes de `avoid` (pour LIBERER la tuile ciblee)."""
    for _ in range(rounds):
        d = _dv(sid, rid)
        u = next((x for x in (d.get("units") or [])
                  if int(x["id"]) == int(unit_id) and x.get("alive")), None)
        if u is None:
            return False
        if hexgeo.distance(_pos(u), avoid) >= 2:
            return True
        tiles = _wait_movable(sid, rid, int(unit_id))
        if not tiles:
            return False
        best = max(tiles, key=lambda t: (hexgeo.distance(t, avoid), t))
        _act(sid, rid, {"kind": "move", "unitId": int(unit_id),
                        "to": {"col": best[0], "row": best[1]}}, 90)
    return False


def _my_turn(sid, rid, vis, maxit=8):
    """Rend la main au camp de `vis`. Le camp est vise NOMMEMENT : tester
    `currentPlayer == <unite ctrl>.owner` serait une tautologie, et ce probe pilote les DEUX camps."""
    for _ in range(maxit):
        d = _dv(sid, rid)
        me = _by_vis(d, vis)
        if me is not None and me.get("ctrl"):
            return d
        _act(sid, rid, {"kind": "endturn"}, 60)
    return _dv(sid, rid)


# --------------------------------------------------------------------------- variantes du port

def _ability(aid: int, variant: str):
    klass = ABILITY_CLASSES[aid]
    opts = klass.TARGETING_OPTIONS
    if variant == "apres":
        return klass()
    if variant == "avant":
        class _NoMask(klass):            # meme classe, masque retire -> AUCUN gate
            __slots__ = ()
            TARGETING_OPTIONS = None
        return _NoMask()
    if variant == "sansBit19":
        class _NoBit19(klass):           # LE contrefactuel qui isole la regle de #249
            __slots__ = ()
            TARGETING_OPTIONS = _replace(
                opts, rules=int(opts.rules) & ~int(TR.TargetTileHasEnemyUnit))
        return _NoBit19()
    if variant == "sansRules":
        class _NoRules(klass):           # le volet PORTEE reste arme, le masque tombe a 0
            __slots__ = ()
            TARGETING_OPTIONS = _replace(opts, rules=0)
        return _NoRules()

    class _NoRange(klass):               # `TargetingRange` non lu -> aucun gate de portee
        __slots__ = ()
        TARGETING_OPTIONS = _replace(opts, range=None)
    return _NoRange()


def _native(sid, rid, caster_id, aid, target_id=None):
    body = {"runnerId": rid, "casterId": int(caster_id), "abilityType": int(aid)}
    if target_id is not None:
        body["targetId"] = int(target_id)
    nat = _r(sid, "abilityReason", body, 60) or {}
    tr = nat.get("targetReason") or {}
    cr = nat.get("casterReason") or {}

    def _val(d):
        h = d.get("hex")
        if isinstance(h, str):
            return int(h, 16)
        return 0 if d.get("ruleClass") == "NoBrokenTargetingRule" else None
    return {"val": _val(tr), "reasons": tr.get("reasons") or [],
            "cls": tr.get("ruleClass"), "caster": _val(cr),
            "state": nat.get("abilityState"), "err": nat.get("error")}


# --------------------------------------------------------------------------- confrontation

def _freeze(sid, rid):
    dv = _dv(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indisponible")
    board = Board(bg["tiles"], adjacency="native_sym")
    return dv, load_state(dv, ob, snap, board=board), board


def _confront(sid, rid, st, aid, caster_id, targets, label_of):
    rows = []
    for tid in targets:
        nat = _native(sid, rid, caster_id, aid, tid)
        row = {"targetId": int(tid), "label": label_of(int(tid)),
               "nat": nat["val"], "nat_reasons": nat["reasons"], "nat_class": nat["cls"],
               "nat_caster": nat["caster"]}
        for v in VARIANTS:
            row[v] = int(get_invalid_target_reason(st, caster_id, int(tid), _ability(aid, v)))
        rows.append(row)
    return rows


def _report(phase, aid, caster_id, rows, port_caster):
    opts = ABILITY_CLASSES[aid].TARGETING_OPTIONS
    print("\n[%s / %d] caster=u%d masque=0x%x range=%s"
          % (phase, aid, caster_id, int(opts.rules), opts.range))
    print("  %-28s %-6s %-14s %-26s" % ("cible", "id", "natif", "regle")
          + "".join("%-14s" % v for v in VARIANTS) + "accord")
    n_agree = 0
    cf = {v: {"acc": 0, "ref": 0} for v in VARIANTS}
    for r in rows:
        agree = (r["nat"] == r["apres"])
        n_agree += 1 if agree else 0
        for v in VARIANTS:
            if r["nat"] not in (None, 0) and r[v] == 0:
                cf[v]["acc"] += 1                                 # faux-ACCEPT
            if r["nat"] == 0 and r[v] != 0:
                cf[v]["ref"] += 1                                 # faux-REFUS
        print("  %-28s %-6d %-14s %-26s%s%s"
              % (r["label"], r["targetId"],
                 "-" if r["nat"] is None else hex(r["nat"]),
                 ",".join(r["nat_reasons"]) or r["nat_class"] or "-",
                 "".join("%-14s" % hex(r[v]) for v in VARIANTS),
                 "OK" if agree else "MISMATCH"))
    print("  [bilan %s/%d] accord natif/APRES : %d/%d ; casterReason natif=%s port=%s"
          % (phase, aid, n_agree, len(rows),
             sorted({r["nat_caster"] for r in rows if r["nat_caster"] is not None}),
             hex(port_caster)))
    print("  [contrefactuels %s/%d] desaccords (faux-ACCEPT / faux-REFUS) :" % (phase, aid))
    for v in VARIANTS[1:]:
        tot = cf[v]["acc"] + cf[v]["ref"]
        print("    %-12s %d/%d  (acc=%d ref=%d)%s"
              % (v, tot, len(rows), cf[v]["acc"], cf[v]["ref"],
                 "   <- INERTE sur ce montage" if tot == 0 else ""))
    return {"agree": n_agree, "n": len(rows), "cf": cf, "rows": rows}


def _pick_tile(board, dv, caster_pos):
    """Une tuile T walkable, ADJACENTE au caster de 1017 et LIBRE, avec le plus de voisins walkables
    (pour que les `move` des phases ALLIE/ENNEMI aient de la place)."""
    occupied = {(_pos(u)) for u in (dv.get("units") or []) if u.get("alive")}
    best = None
    cpos = tuple(caster_pos)
    for tid in sorted(board.by_id):
        c = board.coord(tid)
        if c in occupied or not board.walkable(tid):
            continue
        if hexgeo.distance(c, cpos) != 1:
            continue
        n_ok = sum(1 for n in board.neighbours(tid) if board.walkable(n))
        if best is None or n_ok > best[0]:
            best = (n_ok, tid, c)
    return None if best is None else (best[1], best[2])


# --------------------------------------------------------------------------- mode OFFLINE

def _synthetic_board(n: int = 5):
    """Grille `n x n` evenq, toutes marchables, elevation 0. La clause du bit 19 ne lit NI elevation
    NI mur : seulement l'OCCUPATION de la main tile et le camp de son occupant. Une topologie plus
    riche n'ajouterait aucun degre de liberte a CE test."""
    tiles = []
    tid = 1
    for col in range(n):
        for row in range(n):
            tiles.append({"id": tid, "col": col, "row": row, "walkable": True, "elevation": 0})
            tid += 1
    return Board(tiles, adjacency="evenq")


def _synthetic_state(occupant: str | None):
    """Caster + (selon `occupant`) une unite sur la tuile T, ADJACENTE au caster (1017 est
    `RANGE_ADJACENT` : hors adjacence, la portee refuserait EN AMONT et masquerait le bit 19)."""
    from engine.runner.components import (OwnerComponent, PositionComponent,   # noqa: PLC0415
                                          UnitComponent)
    from engine.runner.state import State                                       # noqa: PLC0415
    board = _synthetic_board()
    st = State()
    st.board = board
    caster_t = next(t for t in sorted(board.by_id)
                    if sum(1 for n in board.neighbours(t) if board.walkable(n)) >= 3)
    cpos = board.coord(caster_t)
    ttile = next(n for n in board.neighbours(caster_t) if board.walkable(n))
    tpos = board.coord(ttile)

    def mk(eid, vis, team, pos):
        e = st.add_entity(eid)
        e.add_component(UnitComponent(visual_id=vis, alive=True))
        e.add_component(OwnerComponent(team=team, player=team))
        e.add_component(PositionComponent(col=pos[0], row=pos[1]))
        return eid

    mk(101, BULL, 1, cpos)
    occ = None
    if occupant == "ALLIE":
        occ = mk(102, FILLER, 1, tpos)
    elif occupant == "ENNEMI":
        occ = mk(103, FOE_VIS, 2, tpos)
    return st, 101, ttile, occ


def _offline_cascade() -> int:
    print("[offline] cascade PORTEE seule -- AUCUN oracle natif (build en migration).")
    print("[offline] bit 19 = 0x%x %s" % (int(TR.TargetTileHasEnemyUnit),
                                          TR.TargetTileHasEnemyUnit.name))
    ok = True
    moved = 0
    for phase in PHASES:
        st, caster, ttile, occ = _synthetic_state(None if phase == "VIDE" else phase)
        attendu = 0 if phase == "ENNEMI" else int(TR.TargetTileHasEnemyUnit)
        line = []
        for aid in (FRAG_BOMB, BASILISK_BARRAGE):
            with_bit = int(get_invalid_target_reason(st, caster, ttile, _ability(aid, "apres")))
            without = int(get_invalid_target_reason(st, caster, ttile, _ability(aid, "sansBit19")))
            good = (with_bit == attendu)
            ok = ok and good
            moved += 1 if with_bit != without else 0
            line.append("%d: avec=%s sans=%s %s"
                        % (aid, hex(with_bit), hex(without), "OK" if good else "MISMATCH"))
        print("  T %-7s occupant=%-5s attendu=%-10s | %s"
              % (phase, "-" if occ is None else "u%d" % occ, hex(attendu), " | ".join(line)))
    # cible = une UNITE (et non la tuile) : le natif resout `GetMainTile(unite)`, donc le CASTER et
    # un ALLIE rompent, un ENNEMI passe. C'est la face que `test_targeting_masks_live.py` interroge.
    st, caster, _t, occ_foe = _synthetic_state("ENNEMI")
    r_caster = int(get_invalid_target_reason(st, caster, caster, _ability(FRAG_BOMB, "apres")))
    r_foe = int(get_invalid_target_reason(st, caster, occ_foe, _ability(FRAG_BOMB, "apres")))
    st2, caster2, _t2, occ_ally = _synthetic_state("ALLIE")
    r_ally = int(get_invalid_target_reason(st2, caster2, occ_ally, _ability(FRAG_BOMB, "apres")))
    exp = (int(TR.TargetTileHasEnemyUnit), 0, int(TR.TargetTileHasEnemyUnit))
    got = (r_caster, r_foe, r_ally)
    ok = ok and got == exp
    print("  cible=UNITE (1017) : caster=%s ennemi=%s allie=%s (attendu %s) -> %s"
          % (hex(r_caster), hex(r_foe), hex(r_ally), tuple(hex(x) for x in exp),
             "OK" if got == exp else "MISMATCH"))
    print("  verdicts que le bit 19 DEPLACE (contrefactuel sansBit19) : %d" % moved)
    if moved == 0:
        print("  [NOTE] regle INERTE sur ce montage -- montage non discriminant, pas un succes.")
    print("[offline] %s -- NE VAUT PAS confrontation live (a rejouer sans --offline-cascade "
          "apres la migration de build)" % ("PASS" if ok and moved else "FAIL"))
    return 0 if (ok and moved) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--offline-cascade", action="store_true",
                    help="joue le triplet contre la cascade PORTEE seule, sans session Frida")
    a = ap.parse_args(argv)
    if a.offline_cascade:
        return _offline_cascade()

    sid = _resolve_session()
    rid, state_file = _build(sid, a.seed, a.board)
    print("[build] runner=%d board=%s seed=%s" % (rid, a.board, a.seed))
    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)
        _my_turn(sid, rid, BULL)
        dv, _st, board = _freeze(sid, rid)
        bull, ordn, fill = _by_vis(dv, BULL), _by_vis(dv, ORD_), _by_vis(dv, FILLER)
        if bull is None or ordn is None or fill is None:
            print("[FAIL] porteur absent : bull=%s ord=%s filler=%s"
                  % (bull is not None, ordn is not None, fill is not None))
            return 2
        picked = _pick_tile(board, dv, _pos(bull))
        if picked is None:
            print("[FAIL] aucune tuile libre walkable adjacente a %s" % BULL)
            return 2
        ttile, tcoord = picked
        foes = [u for u in (dv.get("units") or [])
                if u.get("alive") and u.get("owner") != bull.get("owner")]
        if not foes:
            print("[FAIL] aucun ennemi vivant")
            return 2
        foe = foes[0]
        print("[state] bull=u%d%s ord=u%d%s filler=u%d ennemi=u%d ; T=tile%d%s"
              % (int(bull["id"]), _pos(bull), int(ordn["id"]), _pos(ordn),
                 int(fill["id"]), int(foe["id"]), ttile, tcoord))

        out = {}
        for phase in PHASES:
            if phase == "ALLIE":
                if not _place_on(sid, rid, int(fill["id"]), tcoord):
                    print("[FAIL] impossible de poser l'ALLIE sur T -- montage non atteint")
                    return 2
            elif phase == "ENNEMI":
                if not _vacate(sid, rid, int(fill["id"]), tcoord):
                    print("[FAIL] impossible de LIBERER T de l'allie")
                    return 2
                if not _place_on(sid, rid, int(foe["id"]), tcoord):
                    print("[FAIL] impossible de poser l'ENNEMI sur T -- montage non atteint")
                    return 2
            _my_turn(sid, rid, BULL)
            dv, st, board = _freeze(sid, rid)
            b2, o2 = _by_vis(dv, BULL), _by_vis(dv, ORD_)
            if b2 is None or o2 is None:
                print("[FAIL] un porteur est mort pendant le montage")
                return 2
            occ = next((u for u in (dv.get("units") or [])
                        if u.get("alive") and _pos(u) == tcoord), None)
            print("\n=== PHASE %s : T=tile%d%s occupant=%s ==="
                  % (phase, ttile, tcoord,
                     ("u%d/%s" % (int(occ["id"]), occ.get("visualId"))) if occ else "-"))

            def _label(ref):
                own = ref.get("owner")

                def f(tid):
                    u = next((x for x in (dv.get("units") or [])
                              if x.get("alive") and int(x["id"]) == int(tid)), None)
                    if u is None:
                        return "TUILE %s" % (board.coord(int(tid)),)
                    side = ("CASTER" if int(tid) == int(ref["id"])
                            else ("ALLIE" if u.get("owner") == own else "ENNEMI"))
                    return "%s %s" % (side, u.get("visualId"))
                return f

            unit_ids = sorted(int(u["id"]) for u in (dv.get("units") or []) if u.get("alive"))
            for aid, caster in ((FRAG_BOMB, int(b2["id"])), (BASILISK_BARRAGE, int(o2["id"]))):
                rows = _confront(sid, rid, st, aid, caster, [ttile] + unit_ids, _label(b2))
                pc = int(get_invalid_caster_reason(st, caster, _ability(aid, "apres")))
                out[(phase, aid)] = _report(phase, aid, caster, rows, pc)

        # --- LE TRIPLET DISCRIMINANT : la MEME tuile T, trois etats ---------------------------
        print("\n[TRIPLET T=tile%d] verdict NATIF et PORT sur la MEME tuile, par phase :" % ttile)
        triplet_ok = True
        for aid in (FRAG_BOMB, BASILISK_BARRAGE):
            for phase in PHASES:
                r = next((x for x in out[(phase, aid)]["rows"] if x["targetId"] == ttile), None)
                if r is None:
                    triplet_ok = False
                    continue
                attendu = 0 if phase == "ENNEMI" else int(TR.TargetTileHasEnemyUnit)
                ok = (r["nat"] == attendu and r["apres"] == attendu)
                triplet_ok = triplet_ok and ok
                print("  %-4d %-7s natif=%-12s port=%-12s attendu=%-12s -> %s"
                      % (aid, phase, hex(r["nat"]) if r["nat"] is not None else "-",
                         hex(r["apres"]), hex(attendu), "OK" if ok else "MISMATCH"))

        agree = sum(o["agree"] for o in out.values())
        total = sum(o["n"] for o in out.values())
        # le bit 19 doit DEPLACER un verdict : sans lui, au moins un faux-ACCEPT doit apparaitre.
        bit19_bites = sum(o["cf"]["sansBit19"]["acc"] + o["cf"]["sansBit19"]["ref"]
                          for o in out.values())
        ok = (agree == total and total > 0 and triplet_ok and bit19_bites > 0)
        print("\n[BILAN] accord natif/port : %d/%d ; triplet T : %s ; "
              "verdicts que le bit 19 DEPLACE (contrefactuel sansBit19) : %d"
              % (agree, total, "OK" if triplet_ok else "KO", bit19_bites))
        if bit19_bites == 0:
            print("[NOTE] le bit 19 est INERTE sur ce montage -- ce n'est pas un succes, "
                  "c'est un montage non discriminant : le dire, pas le maquiller.")
        print("[VERDICT] %s" % ("PASS" if ok else "FAIL"))
        print("[RAW] " + json.dumps({("%s/%d" % k): v["rows"] for k, v in out.items()}))
        return 0 if ok else 1
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            state_file.unlink(missing_ok=True)
            print("[cleanup] runner %d dispose" % rid)
        except Exception as e:                                       # noqa: BLE001
            print("[cleanup] dispose KO: %s" % e)


if __name__ == "__main__":
    sys.exit(main())
