#!/usr/bin/env python
"""probe_248_cord_claw_targeting -- ARMEMENT du gate de cible de CordClaw (1122,
`admecRuststalker` « Exitor-Rho », Adeptus Mechanicus).

CE QUE CE PROBE MESURE
----------------------
`CordClawAbility` entrait dans `ABILITY_CLASSES` SANS `TARGETING_OPTIONS` ->
`get_invalid_target_reason` commence par `options = getattr(ability, "TARGETING_OPTIONS", None)` et
rend 0 immediatement : AUCUN gate. Degradation PERMISSIVE -- ni erreur ni crash, donc invisible en
self-play.

FORME DE CTOR = **PRESET STATIQUE COPIE** (la 3e des trois formes).
`IdunBattleLogic.Entities.Abilities.Active.Loki.CordClawAbility$$.ctor` n'appelle AUCUN
`IdunBattle.Core.Services.TargetingOptions$$.ctor` : il recopie les 0x40 octets du champ STATIQUE de
`TargetingOptions` a l'offset RELATIF +0x40 du bloc `<class>+0xb8`, puis :

    AActiveAbility..ctor(this, &opts, 0, 0)      # 3e arg = 0 = AbilityAttackType.DirectTargetAttack

Masque EFFECTIF = la constante ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a
`<preset>+0x28` = `*(statics+0x68)` = **0x4000**, decompose EXHAUSTIVEMENT (un seul bit, aucun
residu) :

    0x4000  (bit 14) TargetIsEnemy  -> PORTE (`TargetingQuery$$UnitsCanAttackEachOther`).

`TargetMatchesDynamicRule` (0x2) est ABSENT : le natif ne consulte AUCUNE regle dynamique ici.
Le MEME preset porte le volet PORTEE : `TargetingRange` <- `TargetingRange` statique +0x30
(`TargetingRange$$.cctor` : `onlyAdjacent = 0 = RangedBool.True`, `overrideRange = Nullable(1)`) =
`RANGE_ADJACENT` -> branche `battleQuery.AreEntitiesAdjacent`, PAS un `dist <= N`. Et
`forceMeleeTarget` (`<preset>+0x20` = `*(statics+0x60)`) = **1** = `RangedBool.False`.

LE PIEGE ECARTE : `ThunderousAssault` (1043) RECOPIE LE MEME PRESET
------------------------------------------------------------------
1043 recopie aussi `TargetingOptions statics+0x40`, mais enchaine sur la surcharge « preset + flags »
(`TargetingOptions..ctor(&opts, &preset, 0x10000000, 0)`) qui COMBINE
(`dst+0x28 = flags | preset+0x28`) -> 0x10004000. CordClaw copie INTEGRALEMENT et s'arrete la : son
masque est le preset NU, **sans `CasterCanMove`**. Meme source statique, deux masques -- c'est la
FORME du ctor qui tranche, pas le preset. Consequence directe et VERIFIEE ici : le volet CASTER de
CordClaw est vide, `casterReason` natif doit valoir 0 sur toutes les lignes.

COMMENT LA GEOMETRIE EST FORCEE (jamais subie)
----------------------------------------------
`onlyAdjacent` fait tester l'ADJACENCE : le cas limite est d=2 (la premiere distance refusee), pas
une portee numerique. Il faut donc, DANS LE MEME etat fige : un ennemi a d=1 (accepte), un ennemi a
d=2 (attendu `TargetIsInRange` -- c'est LA ligne qui separe « adjacence » de « portee 2 »), un ennemi
plus loin, un ALLIE au contact (seule ligne qui isole `TargetIsEnemy` du volet portee) et le CASTER.
On DEPLACE les deux camps sur un runner `--no-ai`.

ORACLE = le LIVE : `abilityReason(casterId, abilityType, targetId)` rend le masque `TargetingRule`
NATIF. Le probe rejoue le gate OFFLINE sur le MEME etat fige, en CINQ versions :
  * APRES          = l'ability du registre ;
  * AVANT          = `TARGETING_OPTIONS = None` -- l'etat de `master` ;
  * sansEnemy      = masque prive du bit 14 -> doit faux-accepter allie + caster ;
  * sansRange      = `range = None` -> doit faux-accepter tout ce qui est hors contact ;
  * rangeDist2     = `custom_range(2)` (meme portee numerique, mais SANS `onlyAdjacent`) -> doit
                     faux-accepter la cible a d=2. C'est ce contrefactuel-la, et pas `sansRange`,
                     qui prouve que le champ lu est le REGIME `onlyAdjacent` et pas « une portee » ;
  * forceMeleeTrue = `forceMeleeTarget` inverse -> attendu SANS EFFET (la portee EST deja
                     l'adjacence, le clamp n'a rien a clamper), et c'est un resultat a dire.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_248_cord_claw_targeting.py
    python probe_248_cord_claw_targeting.py --seed 31337 --board C4_09

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
                                               custom_range,
                                               get_invalid_caster_reason,
                                               get_invalid_target_reason)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

CORD_CLAW = 1122
CASTER_VIS = "admecRuststalker"
ALLY_VIS = "admecMarshall"
FOE_VIS = "necroWarden"
P_UNITS = CASTER_VIS + "," + ALLY_VIS
A_UNITS = ",".join([FOE_VIS] * 3)
BOARD = "MC1_67"
SEED = "777"
TOURS_DE_CHAUFFE = 6               # purge les `initialCooldownTurns` (sinon `ValidRequest` partout)
_seq = itertools.count()


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _build(sid, seed: str, board: str):
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, qui est versionne).
    ATTEND qu'un slot se libere si MAX_RUNNERS est sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe248-%d-%d.json" % (os.getpid(), next(_seq)))
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
            raise RuntimeError("build KO : " + out[-400:])
        time.sleep(10)


def _dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


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


def _by_vis(dec, vis):
    for u in (dec.get("units") or []):
        if u.get("visualId") == vis and u.get("alive"):
            return u
    return None


def _my_turn(sid, rid, maxit=8):
    """Rend la main au camp du CASTER (chaine d'`endturn`, runner `--no-ai`). Le camp d'Exitor-Rho
    est vise NOMMEMENT : tester `currentPlayer == <unite ctrl>.owner` serait une tautologie, et ce
    probe pilote les DEUX camps pour monter sa geometrie."""
    for _ in range(maxit):
        d = _dv(sid, rid)
        me = _by_vis(d, CASTER_VIS)
        if me is not None and me.get("ctrl"):
            return d
        _act(sid, rid, {"kind": "endturn"}, 60)
    return _dv(sid, rid)


# --------------------------------------------------------------------------- montage

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


def _drive(sid, rid, rounds=14):
    """Monte la geometrie DISCRIMINANTE et rend `(casterId, allyId, {label: unitId})` :
    ennemi `contact` d=1, ennemi `seuil` d=2 (LE cas limite de l'adjacence), ennemi `loin` d=4,
    allie d=1."""
    d = _dv(sid, rid)
    foes0 = sorted((u for u in (d.get("units") or []) if u.get("alive") and not u.get("ctrl")),
                   key=lambda u: u["id"])
    if len(foes0) < 3:
        raise RuntimeError("il faut >= 3 ennemis pour separer contact / d=2 / loin")
    want = {int(foes0[0]["id"]): 1, int(foes0[1]["id"]): 2, int(foes0[2]["id"]): 4}
    labels = {int(foes0[0]["id"]): "contact", int(foes0[1]["id"]): "seuil",
              int(foes0[2]["id"]): "loin"}
    for it in range(rounds):
        d = _dv(sid, rid)
        units = {int(u["id"]): u for u in (d.get("units") or []) if u.get("alive")}
        caster = _by_vis(d, CASTER_VIS)
        ally = _by_vis(d, ALLY_VIS)
        if caster is None or ally is None or any(i not in units for i in want):
            raise RuntimeError("montage impossible (mort ou absent)")
        cp = _pos(caster)
        cur = {i: hexgeo.distance(cp, _pos(units[i])) for i in want}
        d_ally = hexgeo.distance(cp, _pos(ally))
        print("  [drive %d] caster=%s d(ennemis)=%s d(allie)=%d"
              % (it, cp, {labels[i]: v for i, v in cur.items()}, d_ally))
        if (cur[foes0[0]["id"]] == 1 and cur[foes0[1]["id"]] == 2
                and cur[foes0[2]["id"]] > 2 and d_ally == 1):
            return int(caster["id"]), int(ally["id"]), {labels[i]: i for i in want}
        if d_ally != 1:
            _step_toward(sid, rid, int(ally["id"]), cp, 1)
        for i, target_d in want.items():
            d2 = _dv(sid, rid)
            c2 = _by_vis(d2, CASTER_VIS)
            u2 = {int(u["id"]): u for u in (d2.get("units") or []) if u.get("alive")}
            if i not in u2 or c2 is None:
                continue
            if hexgeo.distance(_pos(c2), _pos(u2[i])) != target_d:
                _step_toward(sid, rid, i, _pos(c2), target_d)
    raise RuntimeError("geometrie discriminante non atteinte apres %d rounds" % rounds)


# --------------------------------------------------------------------------- variantes du port

def _ability(variant: str):
    klass = ABILITY_CLASSES[CORD_CLAW]
    opts = klass.TARGETING_OPTIONS
    if variant == "apres":
        return klass()
    if variant == "avant":
        class _NoMask(klass):            # meme classe, masque retire -> AUCUN gate (etat `master`)
            __slots__ = ()
            TARGETING_OPTIONS = None
        return _NoMask()
    if variant == "sansEnemy":
        class _NoEnemy(klass):
            __slots__ = ()
            TARGETING_OPTIONS = _replace(
                opts, rules=int(opts.rules) & ~int(TR.TargetIsEnemy))
        return _NoEnemy()
    if variant == "rangeDist2":          # meme portee NUMERIQUE, mais sans le regime `onlyAdjacent`
        class _D2(klass):
            __slots__ = ()
            TARGETING_OPTIONS = _replace(opts, range=custom_range(2))
        return _D2()
    if variant == "forceMeleeTrue":
        class _FM(klass):
            __slots__ = ()
            TARGETING_OPTIONS = _replace(opts, force_melee_target=RANGED_BOOL_TRUE)
        return _FM()

    class _NoRange(klass):
        __slots__ = ()
        TARGETING_OPTIONS = _replace(opts, range=None)
    return _NoRange()


VARIANTS = ("apres", "avant", "sansEnemy", "sansRange", "rangeDist2", "forceMeleeTrue")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    a = ap.parse_args(argv)

    sid = _resolve_session()
    rid, state_file = _build(sid, a.seed, a.board)
    print("[build] runner=%d board=%s seed=%s" % (rid, a.board, a.seed))
    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)
        cid, ally_id, foes = _drive(sid, rid)
        _my_turn(sid, rid)               # rendre la main au camp du caster avant de figer l'etat

        dv = _dv(sid, rid)
        nat0 = _r(sid, "abilityReason",
                  {"runnerId": rid, "casterId": cid, "abilityType": CORD_CLAW}, 60)
        usable = bool(((nat0 or {}).get("abilityState") or {}).get("usable"))
        caster_u = next(u for u in dv["units"] if u["id"] == cid)
        print("[state] caster=u%d(%s) pos=%s ctrl=%s usable=%s allie=u%d ennemis=%s"
              % (cid, caster_u.get("visualId"), _pos(caster_u), caster_u.get("ctrl"),
                 usable, ally_id, foes))
        if not usable:
            print("[FAIL] 1122 non utilisable -> l'oracle court-circuite (`ValidRequest`), "
                  "mesure impossible")
            return 2

        ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            print("[FAIL] boardGraph indisponible")
            return 2
        board = Board(bg["tiles"], adjacency="native_sym")
        st = load_state(dv, ob, snap, board=board)

        rows = []
        for u in (dv.get("units") or []):
            if not u.get("alive"):
                continue
            tid = int(u["id"])
            dist = hexgeo.distance(_pos(caster_u), _pos(u))
            # le camp se lit sur `owner`, JAMAIS sur `ctrl` (qui designe le joueur COURANT et
            # s'inverse des qu'on a pilote une unite adverse pour monter la geometrie)
            side = "CASTER" if tid == cid else (
                "ALLIE" if u.get("owner") == caster_u.get("owner") else "ENNEMI")
            nat = _r(sid, "abilityReason",
                     {"runnerId": rid, "casterId": cid, "targetId": tid,
                      "abilityType": CORD_CLAW}, 60)
            tr = (nat or {}).get("targetReason") or {}
            cr = (nat or {}).get("casterReason") or {}
            nat_hex = tr.get("hex")
            nat_val = int(nat_hex, 16) if isinstance(nat_hex, str) else None
            if nat_val is None and tr.get("ruleClass") == "NoBrokenTargetingRule":
                nat_val = 0
            cr_hex = cr.get("hex")
            cr_val = int(cr_hex, 16) if isinstance(cr_hex, str) else (
                0 if cr.get("ruleClass") == "NoBrokenTargetingRule" else None)
            row = {"label": "%s %s" % (side, u.get("visualId")), "targetId": tid, "dist": dist,
                   "nat": nat_val, "nat_reasons": tr.get("reasons") or [],
                   "nat_class": tr.get("ruleClass"), "nat_caster": cr_val}
            for v in VARIANTS:
                row[v] = int(get_invalid_target_reason(st, cid, tid, _ability(v)))
            rows.append(row)

        port_caster = int(get_invalid_caster_reason(st, cid, _ability("apres")))
        mask = int(ABILITY_CLASSES[CORD_CLAW].TARGETING_OPTIONS.rules)
        print("\n[reasons] caster=u%d ability=%d (masque 0x%x, range=ADJACENT)"
              % (cid, CORD_CLAW, mask))
        print("  %-26s %-5s %-3s %-11s %-18s" % ("cible", "id", "d", "natif", "regle")
              + "".join("%-13s" % v for v in VARIANTS) + "accord")
        n_agree = n_gain = 0
        cf = {v: 0 for v in VARIANTS}
        for r in rows:
            agree = (r["nat"] == r["apres"])
            n_agree += 1 if agree else 0
            gain = (r["nat"] not in (None, 0)) and r["avant"] == 0
            n_gain += 1 if gain else 0
            for v in VARIANTS:
                if r["nat"] not in (None, 0) and r[v] == 0:
                    cf[v] += 1                                   # faux-ACCEPT du contrefactuel
                if r["nat"] == 0 and r[v] != 0:
                    cf[v] += 1                                   # faux-REFUS du contrefactuel
            print("  %-26s %-5d %-3s %-11s %-18s%s%s%s"
                  % (r["label"], r["targetId"], r["dist"],
                     "-" if r["nat"] is None else hex(r["nat"]),
                     ",".join(r["nat_reasons"]) or r["nat_class"] or "-",
                     "".join("%-13s" % hex(r[v]) for v in VARIANTS),
                     "OK" if agree else "MISMATCH", "  <-GAIN" if gain else ""))

        has_acc = any(r["nat"] == 0 for r in rows)
        has_enemy_ref = any(r["nat"] == int(TR.TargetIsEnemy) for r in rows)
        has_range_ref = any(r["nat"] == int(TR.TargetIsInRange) for r in rows)
        d2 = [r for r in rows if r["dist"] == 2 and r["label"].startswith("ENNEMI")]
        print("[cas limite d=2 (1re distance HORS adjacence, attendu TargetIsInRange)] %s"
              % ("natif=%s port=%s -> %s"
                 % (hex(d2[0]["nat"]), hex(d2[0]["apres"]),
                    "OK" if d2[0]["nat"] == d2[0]["apres"] == int(TR.TargetIsInRange)
                    else "MISMATCH")
                 if d2 else "ABSENT (montage incomplet)"))
        print("\n[bilan] accord natif/APRES : %d/%d ; lignes ou le natif REFUSE et AVANT rendait 0 "
              "(casts illegaux que master acceptait) : %d" % (n_agree, len(rows), n_gain))
        print("[garde] au moins une cible ACCEPTEE (0x0) : %s -> le court-circuit d'ability ne mord "
              "pas ; TargetIsEnemy observe : %s ; TargetIsInRange observe : %s"
              % ("OUI" if has_acc else "NON", "OUI" if has_enemy_ref else "NON",
                 "OUI" if has_range_ref else "NON"))
        print("[volet CASTER] casterReason natif = %s ; port = %s -> le masque NU (0x4000) ne porte "
              "AUCUN bit du volet caster, contrairement a 1043 (0x10004000, `CasterCanMove`) qui "
              "recopie pourtant le MEME preset" % (sorted(x for x in set(r["nat_caster"]
                                                                        for r in rows)
                                                          if x is not None), hex(port_caster)))
        print("[contrefactuels] lignes en DESACCORD avec le natif quand on neutralise/inverse "
              "un champ :")
        for v in VARIANTS[1:]:
            note = ""
            if v == "rangeDist2":
                note = "   <- meme portee numerique SANS `onlyAdjacent` : prouve le REGIME"
            if v == "forceMeleeTrue":
                note = ("   <- ATTENDU 0 : la portee EST deja l'adjacence, le clamp melee n'a rien "
                        "a clamper")
            print("    %-16s %d/%d%s" % (v, cf[v], len(rows), note))
        ok = (n_agree == len(rows) and has_acc and has_enemy_ref and has_range_ref
              and n_gain > 0 and cf["sansEnemy"] > 0 and cf["sansRange"] > 0
              and cf["rangeDist2"] > 0 and cf["forceMeleeTrue"] == 0 and port_caster == 0
              and bool(d2) and d2[0]["nat"] == int(TR.TargetIsInRange))
        print("[VERDICT] %s" % ("PASS" if ok else "FAIL"))
        print("[RAW] " + json.dumps(rows))
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
