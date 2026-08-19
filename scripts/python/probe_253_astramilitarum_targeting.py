#!/usr/bin/env python
"""probe_253_astramilitarum_targeting -- ARMEMENT du gate de cible des QUATRE abilities du module
`astramilitarum` : 1016 SendInTheNextWave (`astraYarrick`), 1028 SupremeCommander (`astraCreed`),
1142 MalleusRocketLauncher et 1143 ForwardSpotter (`astraOrdnanceBattery`, MACHINE OF WAR).

CE QUE CE PROBE MESURE
----------------------
Les quatre entraient dans `ABILITY_CLASSES` SANS `TARGETING_OPTIONS` -> `get_invalid_target_reason`
commence par `options = getattr(ability, "TARGETING_OPTIONS", None)` et rend 0 immediatement : AUCUN
gate. Degradation PERMISSIVE -- ni erreur ni crash, donc invisible en self-play.

FORME DE CTOR : les QUATRE sont en forme 1 « FLAGS DIRECTS » (surcharge 8 arguments de
`IdunBattle.Core.Services.TargetingOptions$$.ctor`, celle qui ecrit `+0x28 <- param_5` SANS OR) --
le litteral EST le masque. Ce qui les separe, c'est le PRESET DE PORTEE, et ils sont TOUS DIFFERENTS
(`IdunBattle.Core.Services.TargetingRange$$.cctor`, offsets relatifs du bloc de statiques) :

  id    ctor                                                  preset    masque
  1016  ..ctor(&opts, 0, &preset, 1, 0x4002,          0,0,0)  +0x00     TargetIsEnemy
                                                                       | TargetMatchesDynamicRule
  1028  ..ctor(&opts, 1, &preset, 1, 0x208000,        0,0,0)  +0x60     CasterHasFreeAdjacentTile
                                                                       | CasterIsPossibleTarget
  1142  ..ctor(&opts, 0, &preset, 1, 0x10000040000040,0,0,0)  +0x48     CasterHas2TurnsLeft
                                                                       | AllowNullCasterTile
                                                                       | TargetIsTile
  1143  ..ctor(&opts, 0, &preset, 1, 0x40000422,      0,0,0)  +0x48     AllowNullCasterTile
                                                                       | TargetIsFriendly
                                                                       | TargetHasFreeAdjacentTile
                                                                       | TargetMatchesDynamicRule

  +0x00 = RANGE_ADJACENT_IF_MELEE_CASTER   +0x48 = RANGE_WHOLE_BOARD   +0x60 = RANGE_SELF

et `forceMeleeTarget = 1 = RangedBool.False` pour les quatre (4e argument).

COMMENT LA GEOMETRIE EST FORCEE (jamais subie)
----------------------------------------------
Runner `--no-ai`, les DEUX camps pilotes. Yarrick porte une arme `Range = 2` -> `IsRanged` vrai ->
`onlyAdjacent = IfNotRangedCaster` retombe a FAUX et sa portee vaut 2 : le SEUIL est encadre DES
DEUX COTES (un ennemi a d=2 accepte, un ennemi a d=3 refuse `TargetIsInRange`). Creed a une portee
NULLE (`overrideRange = 0`) : le seuil y est d=0/d=1. Les deux abilities de la MoW n'ont AUCUN test
de portee (`useWholeBoard`), et leur caster n'a meme pas de tuile -- c'est `AllowNullCasterTile` qui
le permet.

ORACLE = le LIVE : `abilityReason(casterId, abilityType, targetId)` rend le masque `TargetingRule`
NATIF (`AttackQuery$$GetInvalidTargetReason` -> `TargetingQuery$$GetInvalidTargetReason`). Le probe
rejoue le gate OFFLINE sur le MEME etat fige, en CINQ versions :
  * apres        = l'ability du registre ;
  * avant        = `TARGETING_OPTIONS = None` -- l'etat de `master` (aucun gate) ;
  * sansRules    = `rules = 0` (le volet PORTEE reste arme) ;
  * sansRange    = `range = None` (le masque reste arme) ;
  * forceMeleeIn = `forceMeleeTarget` inverse (RangedBool.True).
Les desaccords sont comptes DANS LES DEUX SENS (faux-ACCEPT et faux-REFUS) : un champ dont la
neutralisation ne change RIEN est INERTE, et c'est dit tel quel.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_253_astramilitarum_targeting.py
    python probe_253_astramilitarum_targeting.py --seed 31337 --board C2_02

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
from dataclasses import replace as _replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                        # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting import (RANGED_BOOL_TRUE,     # noqa: E402
                                               get_invalid_caster_reason,
                                               get_invalid_target_reason)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

SEND_IN_THE_NEXT_WAVE = 1016
SUPREME_COMMANDER = 1028
MALLEUS_ROCKET_LAUNCHER = 1142
FORWARD_SPOTTER = 1143

YARRICK = "astraYarrick"          # porteur 1016 (HERO, pool)
CREED = "astraCreed"              # porteur 1028 (HERO, pool)
BATTERY = "astraOrdnanceBattery"  # porteur 1142 + 1143 (MACHINE OF WAR, pool MoW)
FOE_VIS = "necroWarden"

P_UNITS = YARRICK + "," + CREED
A_UNITS = ",".join([FOE_VIS] * 3)
BOARD = "C1_02"                   # board MoW-capable (slot MachineOfWarPosition des deux cotes)
SEED = "777"
TOURS_DE_CHAUFFE = 8               # purge les `initialCooldownTurns` (1142 = 1, 1143 = 2)
VARIANTS = ("apres", "avant", "sansRules", "sansRange", "forceMeleeIn")
_seq = itertools.count()


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _seed_bc_with_ammo(ammo: int) -> Path:
    """Seed BC patche HORS `data/` (qui est versionne et ne contient que des ENTREES) : on dote les
    joueurs non-`Environment` de `ammo` munitions de MoW. Le seed BC partage capture une bataille a
    `BC.Player.Players[*].MachineOfWarAmmo = 0` et AUCUNE operation native ne l'incremente
    (`docs/rl/case-mow-ammo-gauge.md`) -> `ActiveAbility$$get_CanCurrentlyBeUsed` est FAUX pour toute
    ability a `munitionsCost`, et `AttackQuery$$GetInvalidTargetReason` (surcharge 4 arguments)
    court-circuite alors en `broken(1)` AVANT d'entrer dans la cascade. 1142 porte
    `munitionsCost = 1` ; 1143 n'en porte pas. C'est le contrefactuel qui separe les deux."""
    src = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    bc = src.get("bc") if isinstance(src, dict) and "bc" in src else src
    for _pid, p in ((bc.get("Player") or {}).get("Players") or {}).items():
        if p.get("PlayerType") != 2:                  # 2 = Environment
            p["MachineOfWarAmmo"] = int(ammo)
    out = ROOT / "logs" / ("_probe253-seedbc-%d-ammo%d.json" % (os.getpid(), int(ammo)))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(src), encoding="utf-8")
    return out


def _build(sid, seed: str, board: str, seed_bc: Path | None = None):
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, qui est versionne).
    ATTEND qu'un slot se libere si MAX_RUNNERS est sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe253-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--p-units", P_UNITS, "--a-units", A_UNITS, "--p-mow", BATTERY]
    if seed_bc is not None:
        argv += ["--seed-bc", str(seed_bc)]
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


def _mow_by_vis(dec, vis):
    for m in (dec.get("mows") or []):
        if m.get("visualId") == vis:
            return m
    return None


def _movable(sid, rid, uid):
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])
                    if t.get("col") is not None]
    return []


def _wait_movable(sid, rid, unit_id, maxit=6):
    """Tuiles de deplacement de `unit_id`, en enchainant les `endturn` jusqu'a ce que son camp AIT la
    main. On ne COMPTE surtout pas les `endturn` : quand toutes les unites d'un camp ont agi le
    moteur bascule DEJA seul, et un `endturn` de plus decalerait la parite."""
    for _ in range(maxit):
        t = _movable(sid, rid, unit_id)
        if t:
            return t
        _act(sid, rid, {"kind": "endturn"}, 60)
    return []


def _step_toward(sid, rid, unit_id, goal_pos, want: int) -> bool:
    """Rapproche (ou eloigne) `unit_id` jusqu'a une distance `want` de `goal_pos`, dans la limite de
    SON deplacement du tour. Rend True si un `move` a ete emis."""
    tiles = _wait_movable(sid, rid, unit_id)
    if not tiles:
        return False
    best = min(tiles, key=lambda t: (abs(hexgeo.distance(t, goal_pos) - want), t))
    _act(sid, rid, {"kind": "move", "unitId": unit_id,
                    "to": {"col": best[0], "row": best[1]}}, 90)
    return True


def _my_turn(sid, rid, maxit=8):
    """Rend la main au camp de YARRICK (chaine d'`endturn`, runner `--no-ai`). Le camp est vise
    NOMMEMENT : tester `currentPlayer == <unite ctrl>.owner` serait une tautologie, et ce probe
    pilote les DEUX camps pour monter sa geometrie."""
    for _ in range(maxit):
        d = _dv(sid, rid)
        me = _by_vis(d, YARRICK)
        if me is not None and me.get("ctrl"):
            return d
        _act(sid, rid, {"kind": "endturn"}, 60)
    return _dv(sid, rid)


# --------------------------------------------------------------------------- montage

def _drive(sid, rid, rounds=16):
    """Monte la geometrie DISCRIMINANTE autour de YARRICK (portee 2, le seul des trois casters qui
    ait une portee NUMERIQUE) et rend `{label: unitId}` : ennemi `contact` d=1, ennemi `seuil` d=2
    (DERNIERE distance ACCEPTEE), ennemi `horsPortee` d=3 (PREMIERE distance REFUSEE) ; Creed
    (allie) amene a d<=2 pour que la ligne ALLIE soit DANS la portee -- c'est elle qui isole
    `TargetIsEnemy` du volet portee."""
    d = _dv(sid, rid)
    foes0 = sorted((u for u in (d.get("units") or []) if u.get("alive") and not u.get("ctrl")),
                   key=lambda u: u["id"])
    if len(foes0) < 3:
        raise RuntimeError("il faut >= 3 ennemis pour separer contact / seuil / horsPortee")
    want = {int(foes0[0]["id"]): 1, int(foes0[1]["id"]): 2, int(foes0[2]["id"]): 3}
    labels = {int(foes0[0]["id"]): "contact", int(foes0[1]["id"]): "seuil",
              int(foes0[2]["id"]): "horsPortee"}
    for it in range(rounds):
        d = _dv(sid, rid)
        units = {int(u["id"]): u for u in (d.get("units") or []) if u.get("alive")}
        yar = _by_vis(d, YARRICK)
        creed = _by_vis(d, CREED)
        if yar is None or creed is None or any(i not in units for i in want):
            raise RuntimeError("montage impossible (mort ou absent)")
        yp = _pos(yar)
        cur = {i: hexgeo.distance(yp, _pos(units[i])) for i in want}
        d_creed = hexgeo.distance(yp, _pos(creed))
        print("  [drive %d] yarrick=%s d(ennemis)=%s d(creed)=%d"
              % (it, yp, {labels[i]: v for i, v in cur.items()}, d_creed))
        if (cur[int(foes0[0]["id"])] == 1 and cur[int(foes0[1]["id"])] == 2
                and cur[int(foes0[2]["id"])] == 3 and 1 <= d_creed <= 2):
            return {labels[i]: i for i in want}
        if not (1 <= d_creed <= 2):
            _step_toward(sid, rid, int(creed["id"]), yp, 1)
        for i, target_d in want.items():
            d2 = _dv(sid, rid)
            y2 = _by_vis(d2, YARRICK)
            u2 = {int(u["id"]): u for u in (d2.get("units") or []) if u.get("alive")}
            if i not in u2 or y2 is None:
                continue
            if hexgeo.distance(_pos(y2), _pos(u2[i])) != target_d:
                _step_toward(sid, rid, i, _pos(y2), target_d)
    raise RuntimeError("geometrie discriminante non atteinte apres %d rounds" % rounds)


# --------------------------------------------------------------------------- variantes du port

def _ability(aid: int, variant: str):
    klass = ABILITY_CLASSES[aid]
    opts = klass.TARGETING_OPTIONS
    if variant == "apres":
        return klass()
    if variant == "avant":
        class _NoMask(klass):            # meme classe, masque retire -> AUCUN gate (etat `master`)
            __slots__ = ()
            TARGETING_OPTIONS = None
        return _NoMask()
    if variant == "sansRules":
        class _NoRules(klass):           # le volet PORTEE reste arme, le masque tombe a 0
            __slots__ = ()
            TARGETING_OPTIONS = _replace(opts, rules=0)
        return _NoRules()
    if variant == "forceMeleeIn":
        class _FM(klass):
            __slots__ = ()
            TARGETING_OPTIONS = _replace(opts, force_melee_target=RANGED_BOOL_TRUE)
        return _FM()

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

def _confront(sid, rid, st, aid, caster_id, targets, label_of, dist_of):
    """Une ligne par cible : natif vs les 5 variantes du port. Rend `(rows, stats)`."""
    rows = []
    for tid in targets:
        nat = _native(sid, rid, caster_id, aid, tid)
        row = {"targetId": tid, "label": label_of(tid), "dist": dist_of(tid),
               "nat": nat["val"], "nat_reasons": nat["reasons"], "nat_class": nat["cls"],
               "nat_caster": nat["caster"]}
        for v in VARIANTS:
            row[v] = int(get_invalid_target_reason(st, caster_id, tid, _ability(aid, v)))
        rows.append(row)
    return rows


def _report(aid, caster_id, rows, port_caster):
    opts = ABILITY_CLASSES[aid].TARGETING_OPTIONS
    print("\n[%d] caster=u%d masque=0x%x range=%s forceMelee=%d"
          % (aid, caster_id, int(opts.rules), opts.range, opts.force_melee_target))
    print("  %-30s %-6s %-4s %-16s %-30s" % ("cible", "id", "d", "natif", "regle")
          + "".join("%-16s" % v for v in VARIANTS) + "accord")
    n_agree = n_gain = 0
    cf = {v: {"acc": 0, "ref": 0} for v in VARIANTS}
    for r in rows:
        agree = (r["nat"] == r["apres"])
        n_agree += 1 if agree else 0
        gain = (r["nat"] not in (None, 0)) and r["avant"] == 0
        n_gain += 1 if gain else 0
        for v in VARIANTS:
            if r["nat"] not in (None, 0) and r[v] == 0:
                cf[v]["acc"] += 1                                 # faux-ACCEPT
            if r["nat"] == 0 and r[v] != 0:
                cf[v]["ref"] += 1                                 # faux-REFUS
        print("  %-30s %-6d %-4s %-16s %-30s%s%s%s"
              % (r["label"], r["targetId"], r["dist"],
                 "-" if r["nat"] is None else hex(r["nat"]),
                 ",".join(r["nat_reasons"]) or r["nat_class"] or "-",
                 "".join("%-16s" % hex(r[v]) for v in VARIANTS),
                 "OK" if agree else "MISMATCH", "  <-GAIN" if gain else ""))
    print("  [bilan %d] accord natif/APRES : %d/%d ; casts illegaux que master acceptait : %d ; "
          "casterReason natif=%s port=%s"
          % (aid, n_agree, len(rows), n_gain,
             sorted({r["nat_caster"] for r in rows if r["nat_caster"] is not None}),
             hex(port_caster)))
    print("  [contrefactuels %d] desaccords (faux-ACCEPT / faux-REFUS) :" % aid)
    for v in VARIANTS[1:]:
        tot = cf[v]["acc"] + cf[v]["ref"]
        print("    %-14s %d/%d  (acc=%d ref=%d)%s"
              % (v, tot, len(rows), cf[v]["acc"], cf[v]["ref"],
                 "   <- INERTE pour cette ability" if tot == 0 else ""))
    return {"agree": n_agree, "n": len(rows), "gain": n_gain, "cf": cf,
            "accepted": any(r["nat"] == 0 for r in rows)}


def _ensembliste(sid, rid, caster_id, aid, st, candidats):
    """ORACLE DE REPLI, ENSEMBLISTE : `abilityTargets` rend l'ENSEMBLE des cibles LEGALES du natif
    (unites ET tuiles), sans passer par le court-circuit `broken(1)` d'`AttackQuery`. On le confronte
    a l'ensemble que le PORT accepte (`get_invalid_target_reason == 0`) sur les MEMES candidats.
    Utilise quand `abilityReason` est court-circuite (cf. `_seed_bc_with_ammo`)."""
    at = _r(sid, "abilityTargets",
            {"runnerId": rid, "unitId": int(caster_id), "abilityType": int(aid)}, 120) or {}
    rows = ((at.get("units") or []) + (at.get("mows") or []))
    row = next((u for u in rows if u.get("unitId") == int(caster_id)
                or u.get("casterId") == int(caster_id)), None)
    tgts = ((row.get("abilities") or [{}])[0].get("targets") or []) if row else []
    nat_ids = set()
    board = st.board
    for t in tgts:
        if t.get("kind") == "unit" and t.get("targetId") is not None:
            nat_ids.add(int(t["targetId"]))
        elif t.get("kind") == "tile" and t.get("tile"):
            tid = board.id_at(t["tile"]["col"], t["tile"]["row"]) if board is not None else None
            if tid is not None:
                nat_ids.add(int(tid))
    port_ids = {int(c) for c in candidats
                if int(get_invalid_target_reason(st, caster_id, int(c),
                                                 _ability(aid, "apres"))) == 0}
    port_avant = {int(c) for c in candidats
                  if int(get_invalid_target_reason(st, caster_id, int(c),
                                                   _ability(aid, "avant"))) == 0}
    cand = {int(c) for c in candidats}
    nat_in = nat_ids & cand
    return {"nat": sorted(nat_in), "port": sorted(port_ids), "avant": sorted(port_avant),
            "manquants": sorted(nat_in - port_ids), "en_trop": sorted(port_ids - nat_in),
            "nat_total": len(nat_ids), "cand": sorted(cand)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--ammo", type=int, default=5,
                    help="MachineOfWarAmmo injecte dans un seed BC patche hors data/ (0 = seed BC "
                         "partage, non patche)")
    a = ap.parse_args(argv)

    sid = _resolve_session()
    seed_bc = _seed_bc_with_ammo(a.ammo) if a.ammo else None
    rid, state_file = _build(sid, a.seed, a.board, seed_bc=seed_bc)
    print("[build] runner=%d board=%s seed=%s ammo=%s" % (rid, a.board, a.seed, a.ammo))
    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)
        foes = _drive(sid, rid)
        _my_turn(sid, rid)               # rendre la main au camp du caster avant de figer l'etat

        dv = _dv(sid, rid)
        ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            print("[FAIL] boardGraph indisponible")
            return 2
        board = Board(bg["tiles"], adjacency="native_sym")
        st = load_state(dv, ob, snap, board=board)

        yar = _by_vis(dv, YARRICK)
        creed = _by_vis(dv, CREED)
        mow = _mow_by_vis(dv, BATTERY)
        if yar is None or creed is None or mow is None:
            print("[FAIL] porteur absent : yarrick=%s creed=%s mow=%s"
                  % (yar is not None, creed is not None, mow is not None))
            return 2
        yid, cid, mid = int(yar["id"]), int(creed["id"]), int(mow["casterId"])
        print("[state] yarrick=u%d%s creed=u%d%s mow=u%d(%s) ennemis=%s"
              % (yid, _pos(yar), cid, _pos(creed), mid, BATTERY, foes))

        alive = [u for u in (dv.get("units") or []) if u.get("alive")]
        by_id = {int(u["id"]): u for u in alive}
        owner_of = {int(u["id"]): u.get("owner") for u in alive}

        def _label(ref_id):
            def f(tid):
                u = by_id.get(int(tid))
                if u is None:
                    return "TUILE %s" % (board.coord(int(tid)),)
                side = ("CASTER" if int(tid) == int(ref_id)
                        else ("ALLIE" if owner_of.get(int(tid)) == owner_of.get(int(ref_id))
                              else "ENNEMI"))
                return "%s %s" % (side, u.get("visualId"))
            return f

        def _dist(ref_pos):
            def f(tid):
                u = by_id.get(int(tid))
                p = _pos(u) if u is not None else board.coord(int(tid))
                if ref_pos is None or p is None or p[0] is None:
                    return "-"
                return hexgeo.distance(ref_pos, p)
            return f

        unit_ids = sorted(by_id)
        # TUILES de confrontation pour 1142 (cast TILE-target) : une LIBRE walkable, une OCCUPEE,
        # une NON-WALKABLE si le board en porte une (c'est la seule qui exerce le bit TargetIsTile).
        occupied = {board.id_at(*_pos(u)) for u in alive if _pos(u)[0] is not None}
        free_t = [t for t in sorted(board.by_id) if board.walkable(t) and t not in occupied][:2]
        unwalk = [t for t in sorted(board.by_id) if not board.walkable(t)][:1]
        occ_t = [t for t in sorted(occupied) if t is not None][:1]
        tiles = free_t + occ_t + unwalk
        print("[tuiles] libres=%s occupee=%s nonWalkable=%s" % (free_t, occ_t, unwalk))

        out = {}
        cases = [
            (SEND_IN_THE_NEXT_WAVE, yid, unit_ids, _pos(yar)),
            (SUPREME_COMMANDER, cid, unit_ids, _pos(creed)),
            (MALLEUS_ROCKET_LAUNCHER, mid, tiles + unit_ids, None),
            (FORWARD_SPOTTER, mid, unit_ids + tiles, None),
        ]
        ens = {}
        for aid, caster, targets, ref_pos in cases:
            nat0 = _native(sid, rid, caster, aid)
            print("\n[%d] abilityState=%s casterReason=%s err=%s"
                  % (aid, nat0["state"], nat0["caster"], nat0["err"]))
            rows = _confront(sid, rid, st, aid, caster, targets,
                             _label(caster), _dist(ref_pos))
            port_caster = int(get_invalid_caster_reason(st, caster, _ability(aid, "apres")))
            out[aid] = _report(aid, caster, rows, port_caster)
            out[aid]["rows"] = rows
            # ORACLE DE REPLI : quand `abilityReason` rend `broken(1)` sur TOUTES les lignes, ce
            # n'est pas un desaccord de masque -- c'est `AttackQuery` qui court-circuite AVANT la
            # cascade (ability indisponible : `CanCurrentlyBeUsed` faux, ou `GetOrNull` null). On
            # bascule alors sur l'ensemble des cibles legales, qui ne passe pas par ce chemin.
            court_circuit = all(r["nat"] == int(TR.ValidRequest) for r in rows) and bool(rows)
            out[aid]["court_circuit"] = court_circuit
            if court_circuit:
                e = _ensembliste(sid, rid, caster, aid, st, [r["targetId"] for r in rows])
                ens[aid] = e
                print("  [ORACLE ENSEMBLISTE %d] `abilityReason` court-circuite (broken(1) sur "
                      "%d/%d lignes) -> confrontation d'ENSEMBLES `abilityTargets` :" % (aid, len(rows), len(rows)))
                print("    natif(candidats)=%s  port=%s  manquants=%s  en_trop=%s  (natif total=%d)"
                      % (e["nat"], e["port"], e["manquants"], e["en_trop"], e["nat_total"]))
                print("    port AVANT (masque None) = %s -> il acceptait %d cible(s) de plus"
                      % (e["avant"], len(set(e["avant"]) - set(e["port"]))))

        # --- SEUILS ENCADRES DES DEUX COTES ------------------------------------------------------
        seuil_ok = True
        r1016 = {r["targetId"]: r for r in out[SEND_IN_THE_NEXT_WAVE]["rows"]}
        for lab, tid in foes.items():
            r = r1016.get(int(tid))
            if r is None:
                seuil_ok = False
                continue
            attendu = 0 if lab in ("contact", "seuil") else int(TR.TargetIsInRange)
            ok = (r["nat"] == attendu and r["apres"] == attendu)
            seuil_ok = seuil_ok and ok
            print("[seuil 1016 %-11s d=%s] natif=%s port=%s attendu=%s -> %s"
                  % (lab, r["dist"], hex(r["nat"]) if r["nat"] is not None else "-",
                     hex(r["apres"]), hex(attendu), "OK" if ok else "MISMATCH"))

        # Une ability court-circuitee ne compte PAS dans l'accord par CODE (l'oracle n'a pas tourne) :
        # elle est jugee sur l'accord ENSEMBLISTE, et c'est dit.
        vivantes = {k: v for k, v in out.items() if not v.get("court_circuit")}
        agree = sum(o["agree"] for o in vivantes.values())
        total = sum(o["n"] for o in vivantes.values())
        gains = sum(o["gain"] for o in out.values())
        ens_ok = all(not e["manquants"] and not e["en_trop"] for e in ens.values())
        ok = (agree == total and total > 0 and gains > 0 and seuil_ok and ens_ok
              and all(o["accepted"] for o in vivantes.values()))
        print("\n[BILAN GLOBAL] accord natif/port PAR CODE : %d/%d (abilities %s) ; "
              "court-circuitees -> oracle ensembliste : %s (accord %s) ; "
              "casts illegaux fermes : %d ; seuils encadres : %s"
              % (agree, total, sorted(vivantes), sorted(ens) or "-",
                 "OK" if ens_ok else "KO", gains, "OK" if seuil_ok else "KO"))
        print("[VERDICT] %s" % ("PASS" if ok else "FAIL"))
        print("[RAW] " + json.dumps({"rows": {str(k): v["rows"] for k, v in out.items()},
                                     "ensembliste": {str(k): v for k, v in ens.items()}}))
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
