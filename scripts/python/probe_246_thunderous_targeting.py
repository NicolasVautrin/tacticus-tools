#!/usr/bin/env python
"""probe_246_thunderous_targeting -- ARMEMENT du gate de cible de ThunderousAssault (1043,
`templSwordBrother` « Sword Brother » Black Templars).

CE QUE CE PROBE MESURE
----------------------
`ThunderousAssaultAbility` entrait dans `ABILITY_CLASSES` SANS `TARGETING_OPTIONS` ->
`get_invalid_target_reason` commence par `options = getattr(ability, "TARGETING_OPTIONS", None)` et
rend 0 immediatement : AUCUN gate. Degradation PERMISSIVE -- ni erreur ni crash, donc invisible en
self-play.

FORME DE CTOR = **PRESET + FLAGS** (la 2e des trois formes -- celle ou le litteral visible dans le
ctor n'est PAS le masque effectif).
`IdunBattleLogic.Entities.Abilities.Active.Loki.ThunderousAssaultAbility$$.ctor` recopie les 0x40
octets du preset STATIQUE de `TargetingOptions` (offset RELATIF +0x40 du bloc `<class>+0xb8`) puis :

    TargetingOptions..ctor(&opts, &preset, 0x10000000, 0)   # surcharge (dst, preset, flags)
    AActiveAbility..ctor(this, &opts, 0, 0)                 # 3e arg = 0 = DirectTargetAttack

La surcharge (dst, preset, flags) recopie le preset champ par champ SAUF `Rules`, qu'elle COMBINE :
`dst+0x28 = flags | preset+0x28`. Le preset +0x40 porte, par
`IdunBattle.Core.Services.TargetingOptions$$.cctor`, `*(statics+0x68) = 0x4000` -- d'ou le masque
EFFECTIF `0x10000000 | 0x4000` = **0x10004000**, decompose EXHAUSTIVEMENT (aucun bit residuel) :

    0x4000      (bit 14) TargetIsEnemy   -> PORTE (`UnitsCanAttackEachOther`)
    0x10000000  (bit 28) CasterCanMove   -> regle du volet CASTER (`GetInvalidCasterReason` :
                `if ((rules & 0x10000000) && !UnitExtensions.CanMove(caster)) -> broken`), NON
                PORTEE : son 2e volet `MovementComponent.IsAllowedToMove` = `movementBlockers.Count
                == 0` n'est pas modelise cote port. Ce probe MESURE que la regle est inerte sur le
                porteur (casterReason natif = 0 sur toutes les lignes) -- le non-port ne cree donc
                aucun desaccord ici.

Le MEME preset porte le volet PORTEE : `TargetingRange` <- `TargetingRange` statique +0x30
(`IdunBattle.Core.Services.TargetingRange$$.cctor` : onlyAdjacent = `RangedBool.True`,
overrideRange = `Nullable(1)`) = `RANGE_ADJACENT` ; `forceMeleeTarget` (`<preset>+0x20`) = 1 =
`RangedBool.False`. ATTENTION : `ArmoriumCherub` (1014) et `ValkyrieStrike` (1018) sont dans le MEME
module et n'ont NI la meme forme de ctor NI le meme preset (+0x140 -> 0x4002 ; +0x1c0 -> 0x6000040).
Les presets ne sont PAS interchangeables.

COMMENT LA GEOMETRIE EST FORCEE (jamais subie)
----------------------------------------------
`onlyAdjacent` fait prendre au filtre statique la branche `AreEntitiesAdjacent` : pour separer les
deux bits il faut, DANS LE MEME etat fige, un ennemi AU CONTACT (attendu : accepte), un ennemi LOIN
(attendu : `TargetIsInRange`) et un ALLIE AU CONTACT (attendu : `TargetIsEnemy` -- c'est la seule
ligne qui distingue le bit 14 du volet portee). On DEPLACE donc le Sword Brother au contact d'un
ennemi et un allie au contact du Sword Brother, sur un runner `--no-ai` (personne ne bouge pendant
le tour adverse).

ORACLE = le LIVE : `abilityReason(casterId, abilityType, targetId)` rend le masque `TargetingRule`
NATIF. Le probe rejoue ensuite le gate OFFLINE sur le MEME etat fige, en QUATRE versions :
  * APRES     = l'ability du registre (masque pose par cette tranche) ;
  * AVANT     = la MEME classe avec `TARGETING_OPTIONS = None` -- l'etat de `master` avant ;
  * sansEnemy = masque prive du bit 14 -> doit faux-accepter les cibles ALLIEES ;
  * sansRange = memes regles mais `range = None` -> doit faux-accepter les cibles HORS contact.
Critere : accord natif/APRES sur TOUTES les lignes, au moins une ligne ou le natif REFUSE alors
qu'AVANT rendait 0, et chacun des deux contrefactuels faux-accepte au moins une ligne refusee.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_246_thunderous_targeting.py
    python probe_246_thunderous_targeting.py --seed 31337 --board C4_09

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
from engine.runner.abilities.targeting import (get_invalid_caster_reason,   # noqa: E402
                                               get_invalid_target_reason)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

THUNDEROUS = 1043
CASTER_VIS = "templSwordBrother"
ALLY_VIS = "templChampion"
FOE_VIS = "necroWarden"
P_UNITS = CASTER_VIS + "," + ALLY_VIS
A_UNITS = FOE_VIS + "," + FOE_VIS + "," + FOE_VIS
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
    state = ROOT / "logs" / ("_probe246-%d-%d.json" % (os.getpid(), next(_seq)))
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


def _my_turn(sid, rid, maxit=8):
    """Rend la main au camp du CASTER (chaine de `endturn`, runner `--no-ai`).

    On vise explicitement le camp du Sword Brother : tester `currentPlayer == <une unite ctrl>.owner`
    serait une tautologie (`ctrl` DESIGNE le joueur courant), et ce probe pilote les DEUX camps pour
    monter sa geometrie -- il faut donc nommer le camp voulu."""
    for _ in range(maxit):
        d = _dv(sid, rid)
        me = _by_vis(d, CASTER_VIS)
        if me is not None and me.get("ctrl"):
            return d
        _act(sid, rid, {"kind": "endturn"}, 60)
    return _dv(sid, rid)


def _by_vis(dec, vis):
    for u in (dec.get("units") or []):
        if u.get("visualId") == vis and u.get("alive"):
            return u
    return None


# --------------------------------------------------------------------------- montage

def _wait_movable(sid, rid, unit_id, maxit=6):
    """Rend les tuiles de deplacement de `unit_id`, en enchainant les `endturn` jusqu'a ce que son
    camp AIT la main ET que son activation soit fraiche.

    On ne compte SURTOUT pas les `endturn` : quand toutes les unites d'un camp ont agi, le moteur
    bascule DEJA de lui-meme -- un `endturn` de plus cloturerait alors le tour de l'ADVERSAIRE et
    decalerait la parite (mesure : le montage restait fige a la meme tuile pendant 12 rounds)."""
    for _ in range(maxit):
        t = _movable(sid, rid, unit_id)
        if t:
            return t
        _act(sid, rid, {"kind": "endturn"}, 60)
    return []


def _step_toward(sid, rid, unit_id, goal_pos, want: int):
    """Rapproche (ou eloigne) `unit_id` jusqu'a une distance `want` de `goal_pos`, dans la limite de
    SON deplacement du tour. Rend True si un `move` a ete emis."""
    tiles = _wait_movable(sid, rid, unit_id)
    if not tiles:
        print("    [move] u%d : AUCUNE tuile disponible" % unit_id)
        return False
    best = min(tiles, key=lambda t: (abs(hexgeo.distance(t, goal_pos) - want), t))
    _act(sid, rid, {"kind": "move", "unitId": unit_id,
                    "to": {"col": best[0], "row": best[1]}}, 90)
    return True


def _drive_contact(sid, rid, rounds=12):
    """Monte la geometrie DISCRIMINANTE : le Sword Brother au contact d'un ennemi, l'allie au
    contact du Sword Brother, et AU MOINS un ennemi hors contact du Sword Brother.

    `applyAction` ne verifie pas la propriete du `unitId` (runner.md §4) mais le set de
    `aiMovableTiles` est calcule pour le JOUEUR COURANT -> on pilote MES unites pendant mon tour et
    les ENNEMIES pendant le leur (runner `--no-ai` : rien ne bouge tout seul). Deux `endturn` par
    round : `StartTurnOperation` purge le flag `Moved` du joueur entrant, donc chaque camp retrouve
    tout son deplacement au round suivant."""
    d = _dv(sid, rid)
    foes0 = sorted((u for u in (d.get("units") or []) if u.get("alive") and not u.get("ctrl")),
                   key=lambda u: u["id"])
    if len(foes0) < 2:
        raise RuntimeError("il faut >= 2 ennemis pour separer contact / hors-contact")
    near_id = int(foes0[0]["id"])
    for it in range(rounds):
        d = _dv(sid, rid)
        units = {int(u["id"]): u for u in (d.get("units") or []) if u.get("alive")}
        caster = _by_vis(d, CASTER_VIS)
        ally = _by_vis(d, ALLY_VIS)
        if caster is None or ally is None or near_id not in units:
            raise RuntimeError("montage impossible (mort ou absent) : caster=%s ally=%s near=%s"
                               % (caster is not None, ally is not None, near_id in units))
        cp = _pos(caster)
        d_near = hexgeo.distance(cp, _pos(units[near_id]))
        d_ally = hexgeo.distance(cp, _pos(ally))
        far = [i for i, u in units.items()
               if not u.get("ctrl") and hexgeo.distance(cp, _pos(u)) > 1]
        print("  [drive %d] caster=%s d(near)=%d d(ally)=%d ennemis_hors_contact=%s"
              % (it, cp, d_near, d_ally, far))
        if d_near == 1 and d_ally == 1 and far:
            return int(caster["id"]), int(ally["id"]), near_id, int(far[0])
        if d_near != 1:
            _step_toward(sid, rid, int(caster["id"]), _pos(units[near_id]), 1)
            d = _dv(sid, rid)
            caster = _by_vis(d, CASTER_VIS)
            units = {int(u["id"]): u for u in (d.get("units") or []) if u.get("alive")}
            if hexgeo.distance(_pos(caster), _pos(units[near_id])) != 1:
                _step_toward(sid, rid, near_id, _pos(caster), 1)      # l'ennemi vient aussi
        d = _dv(sid, rid)
        caster = _by_vis(d, CASTER_VIS)
        ally = _by_vis(d, ALLY_VIS)
        if hexgeo.distance(_pos(caster), _pos(ally)) != 1:
            _step_toward(sid, rid, int(ally["id"]), _pos(caster), 1)
        # aucun ennemi hors contact -> en ELOIGNER un, sinon la ligne `TargetIsInRange` n'existe pas
        d = _dv(sid, rid)
        caster = _by_vis(d, CASTER_VIS)
        units = {int(u["id"]): u for u in (d.get("units") or []) if u.get("alive")}
        others = [i for i, u in units.items()
                  if not u.get("ctrl") and i != near_id
                  and hexgeo.distance(_pos(caster), _pos(u)) <= 1]
        if others and len(units) > 3:
            _step_toward(sid, rid, others[0], _pos(caster), 4)
    raise RuntimeError("geometrie discriminante non atteinte apres %d rounds" % rounds)


# --------------------------------------------------------------------------- variantes du port

def _ability(variant: str):
    klass = ABILITY_CLASSES[THUNDEROUS]
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
                klass.TARGETING_OPTIONS,
                rules=int(klass.TARGETING_OPTIONS.rules) & ~int(TR.TargetIsEnemy))
        return _NoEnemy()

    class _NoRange(klass):
        __slots__ = ()
        TARGETING_OPTIONS = _replace(klass.TARGETING_OPTIONS, range=None)
    return _NoRange()


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
        cid, ally_id, near_id, far_id = _drive_contact(sid, rid)
        # CAS LIMITE : un ennemi a distance EXACTEMENT 2. `onlyAdjacent` doit le refuser -- c'est la
        # ligne qui separe « portee 1 » de « pas de portee du tout », et elle est adjacente au seuil.
        # Best effort : si la tuile n'existe pas sur ce board, les lignes d>2 suffisent au verdict.
        d0 = _dv(sid, rid)
        c0 = next(u for u in d0["units"] if int(u["id"]) == cid)
        if hexgeo.distance(_pos(c0), _pos(next(u for u in d0["units"]
                                               if int(u["id"]) == far_id))) != 2:
            _step_toward(sid, rid, far_id, _pos(c0), 2)
        dv = _my_turn(sid, rid)          # rendre la main au camp du caster avant de figer l'etat

        dv = _dv(sid, rid)
        nat0 = _r(sid, "abilityReason",
                  {"runnerId": rid, "casterId": cid, "abilityType": THUNDEROUS}, 60)
        usable = bool(((nat0 or {}).get("abilityState") or {}).get("usable"))
        caster_u = next(u for u in dv["units"] if u["id"] == cid)
        print("[state] caster=u%d(%s) pos=%s ctrl=%s usable=%s ally=u%d foe_contact=u%d foe_loin=u%d"
              % (cid, caster_u.get("visualId"), _pos(caster_u), caster_u.get("ctrl"),
                 usable, ally_id, near_id, far_id))
        if not usable:
            print("[FAIL] 1043 non utilisable -> l'oracle court-circuite (`ValidRequest`), "
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
                      "abilityType": THUNDEROUS}, 60)
            tr = (nat or {}).get("targetReason") or {}
            cr = (nat or {}).get("casterReason") or {}
            nat_hex = tr.get("hex")
            nat_val = int(nat_hex, 16) if isinstance(nat_hex, str) else None
            if nat_val is None and tr.get("ruleClass") == "NoBrokenTargetingRule":
                nat_val = 0
            cr_hex = cr.get("hex")
            cr_val = int(cr_hex, 16) if isinstance(cr_hex, str) else (
                0 if cr.get("ruleClass") == "NoBrokenTargetingRule" else None)
            rows.append({
                "label": "%s %s" % (side, u.get("visualId")), "targetId": tid, "dist": dist,
                "nat": nat_val, "nat_reasons": tr.get("reasons") or [],
                "nat_class": tr.get("ruleClass"), "nat_caster": cr_val,
                "apres": int(get_invalid_target_reason(st, cid, tid, _ability("apres"))),
                "avant": int(get_invalid_target_reason(st, cid, tid, _ability("avant"))),
                "sansEnemy": int(get_invalid_target_reason(st, cid, tid, _ability("sansEnemy"))),
                "sansRange": int(get_invalid_target_reason(st, cid, tid, _ability("sansRange"))),
            })

        port_caster = int(get_invalid_caster_reason(st, cid, _ability("apres")))
        print("\n[reasons] caster=u%d ability=%d (masque 0x%x)"
              % (cid, THUNDEROUS, int(ABILITY_CLASSES[THUNDEROUS].TARGETING_OPTIONS.rules)))
        print("  %-24s %-5s %-4s %-11s %-18s %-11s %-11s %-11s %-11s %s"
              % ("cible", "id", "d", "natif", "regle", "APRES", "AVANT", "sansEnemy",
                 "sansRange", "accord"))
        n_agree = n_gain = n_cf_e = n_cf_r = 0
        for r in rows:
            agree = (r["nat"] == r["apres"])
            n_agree += 1 if agree else 0
            gain = (r["nat"] not in (None, 0)) and r["avant"] == 0
            n_gain += 1 if gain else 0
            if r["nat"] not in (None, 0):
                n_cf_e += 1 if r["sansEnemy"] == 0 else 0
                n_cf_r += 1 if r["sansRange"] == 0 else 0
            print("  %-24s %-5d %-4s %-11s %-18s %-11s %-11s %-11s %-11s %s%s"
                  % (r["label"], r["targetId"], r["dist"],
                     "-" if r["nat"] is None else hex(r["nat"]),
                     ",".join(r["nat_reasons"]) or r["nat_class"] or "-",
                     hex(r["apres"]), hex(r["avant"]), hex(r["sansEnemy"]), hex(r["sansRange"]),
                     "OK" if agree else "MISMATCH", "  <-GAIN" if gain else ""))

        caster_nat = set(r["nat_caster"] for r in rows)
        has_acc = any(r["nat"] == 0 for r in rows)
        has_enemy_ref = any(r["nat"] == int(TR.TargetIsEnemy) for r in rows)
        has_range_ref = any(r["nat"] == int(TR.TargetIsInRange) for r in rows)
        d2 = [r for r in rows if r["dist"] == 2 and r["label"].startswith("ENNEMI")]
        print("[cas limite d=2] %s" % ("ennemi a distance 2 : natif=%s port=%s -> %s"
                                       % (hex(d2[0]["nat"]), hex(d2[0]["apres"]),
                                          "OK" if d2[0]["nat"] == d2[0]["apres"] else "MISMATCH")
                                       if d2 else "aucune tuile a distance 2 sur ce board "
                                                  "(les lignes d>2 portent le verdict)"))
        print("\n[bilan] accord natif/APRES : %d/%d ; lignes ou le natif REFUSE et AVANT rendait 0 "
              "(casts illegaux que master acceptait) : %d" % (n_agree, len(rows), n_gain))
        print("[garde] au moins une cible ACCEPTEE (0x0) : %s -> le court-circuit d'ability ne mord "
              "pas ; refus TargetIsEnemy observe : %s ; refus TargetIsInRange observe : %s"
              % ("OUI" if has_acc else "NON", "OUI" if has_enemy_ref else "NON",
                 "OUI" if has_range_ref else "NON"))
        print("[volet CASTER] casterReason natif = %s ; port `get_invalid_caster_reason` = %s "
              "-> `CasterCanMove` (bit 28) INERTE sur ce porteur, son non-port ne cree aucun "
              "desaccord" % (sorted(x for x in caster_nat if x is not None), hex(port_caster)))
        print("[contrefactuels] sans TargetIsEnemy : %d/%d faux-accepts ; sans TargetingRange : "
              "%d/%d faux-accepts -> les deux volets sont PORTEURS"
              % (n_cf_e, n_gain, n_cf_r, n_gain))
        ok = (n_agree == len(rows) and has_acc and has_enemy_ref and has_range_ref
              and n_gain > 0 and n_cf_e > 0 and n_cf_r > 0 and port_caster == 0)
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
