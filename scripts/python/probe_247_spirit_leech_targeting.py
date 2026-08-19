#!/usr/bin/env python
"""probe_247_spirit_leech_targeting -- ARMEMENT du gate de cible de SpiritLeech (1104,
`tyranNeurothrope` « Neurothrope », Tyranids).

CE QUE CE PROBE MESURE
----------------------
`SpiritLeechAbility` entrait dans `ABILITY_CLASSES` SANS `TARGETING_OPTIONS` ->
`get_invalid_target_reason` commence par `options = getattr(ability, "TARGETING_OPTIONS", None)` et
rend 0 immediatement : AUCUN gate. Degradation PERMISSIVE -- ni erreur ni crash, donc invisible en
self-play, et c'est exactement l'espace qu'un entrainement RL irait exploiter.

FORME DE CTOR = **PRESET STATIQUE COPIE** (la 3e des trois formes).
`IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$.ctor` n'appelle AUCUN
`IdunBattle.Core.Services.TargetingOptions$$.ctor` : il recopie les 0x40 octets du champ STATIQUE de
`TargetingOptions` a l'offset RELATIF +0x180 du bloc `<class>+0xb8`, puis :

    AActiveAbility..ctor(this, &opts, 0, 0)      # 3e arg = 0 = AbilityAttackType.DirectTargetAttack

Le masque EFFECTIF est donc la constante ecrite par
`IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28` = `*(statics+0x1a8)` =
**0x4002**, decompose EXHAUSTIVEMENT (aucun bit residuel) :

    0x2     (bit 1)  TargetMatchesDynamicRule -> la classe native ne fournit AUCUN corps
                     `SpiritLeechAbility$$GetDynamicInvalidTargetReason` -> defaut `AActiveAbility`
                     = 0. Bit POSE mais INERTE : ce probe le MESURE (contrefactuel `sansDynamic`).
    0x4000  (bit 14) TargetIsEnemy            -> PORTE (`UnitsCanAttackEachOther`).

Le MEME preset porte le volet PORTEE : `TargetingRange` <- `TargetingRange` statique +0x18
(`TargetingRange$$.cctor` : `useRangeFromConfig = true`) = `RANGE_FROM_CONFIG` ->
`AActiveAbility$$SetConfigValuesInTargetingOptions` pose `OverrideRange =
GetNumberConstant(0x16 range)` = `SpiritLeech.constants.range` = **3** ; et `forceMeleeTarget`
(`<preset>+0x20` = `*(statics+0x1a0)`) = **1** = `RangedBool.False`.

LA VOISINE MENT, ET CE PROBE LE PROUVE
--------------------------------------
`ArmoriumCherub` (1014) est dans le MEME module, de la MEME forme, avec le MEME masque 0x4002 et le
MEME `RANGE_FROM_CONFIG`. Son preset (+0x140) ne differe QUE par `forceMeleeTarget = 0 =
RangedBool.True`. Le contrefactuel `forceMeleeTrue` de ce probe rejoue exactement ce preset voisin :
il doit REFUSER des cibles que le natif ACCEPTE (clamp a 1 + `onlyAdjacent` des qu'un ennemi vivant
et ciblable est au contact du caster, via `AttackQuery$$ShouldApplyRangedInMelee`). Un champ n'est
« lu » que si on montre qu'une autre valeur donnerait un autre verdict.

COMMENT LA GEOMETRIE EST FORCEE (jamais subie)
----------------------------------------------
Il faut, DANS LE MEME etat fige : un ennemi AU CONTACT (d=1, arme `ShouldApplyRangedInMelee` -- sans
lui le contrefactuel `forceMeleeTrue` serait un no-op et ne prouverait rien), un ennemi a d=3 (LE
SEUIL de la portee de config : accepte), un ennemi a d>=4 (refuse `TargetIsInRange`), un ALLIE a
portee (seule ligne qui isole `TargetIsEnemy` du volet portee) et le CASTER lui-meme. On DEPLACE les
deux camps sur un runner `--no-ai`.

ORACLE = le LIVE : `abilityReason(casterId, abilityType, targetId)` rend le masque `TargetingRule`
NATIF (`TargetingQuery$$GetInvalidTargetReason`). Le probe rejoue le gate OFFLINE sur le MEME etat
fige, en CINQ versions :
  * APRES         = l'ability du registre (masque pose par cette tranche) ;
  * AVANT         = la MEME classe avec `TARGETING_OPTIONS = None` -- l'etat de `master` ;
  * sansEnemy     = masque prive du bit 14 -> doit faux-accepter allie + caster ;
  * sansRange     = memes regles mais `range = None` -> doit faux-accepter les cibles hors portee ;
  * forceMeleeTrue= le `forceMeleeTarget` du preset VOISIN (1014) -> doit faux-REFUSER d>1 ;
  * sansDynamic   = masque prive du bit 1 -> attendu SANS EFFET (bit inerte), et c'est un resultat.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_247_spirit_leech_targeting.py
    python probe_247_spirit_leech_targeting.py --seed 31337 --board C4_09

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

SPIRIT_LEECH = 1104
CASTER_VIS = "tyranNeurothrope"
ALLY_VIS = "tyranTyrantGuard"
FOE_VIS = "necroWarden"
P_UNITS = CASTER_VIS + "," + ALLY_VIS
A_UNITS = ",".join([FOE_VIS] * 3)
BOARD = "MC1_67"
SEED = "777"
CONFIG_RANGE = 3                  # `SpiritLeech.constants.range` -- le SEUIL a encadrer
TOURS_DE_CHAUFFE = 6               # purge les `initialCooldownTurns` (sinon `ValidRequest` partout)
_seq = itertools.count()


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _build(sid, seed: str, board: str):
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, qui est versionne).
    ATTEND qu'un slot se libere si MAX_RUNNERS est sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe247-%d-%d.json" % (os.getpid(), next(_seq)))
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
    """Rend la main au camp du CASTER (chaine d'`endturn`, runner `--no-ai`). On vise le camp du
    Neurothrope NOMMEMENT : tester `currentPlayer == <unite ctrl>.owner` serait une tautologie, et ce
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
    """Monte la geometrie DISCRIMINANTE et rend `(casterId, allyId, {label: unitId})`.

    Cibles de distance au caster : ennemi `contact` d=1, ennemi `seuil` d=CONFIG_RANGE (3),
    ennemi `hors` d=CONFIG_RANGE+1 (4) au moins, allie d<=CONFIG_RANGE.
    `applyAction` ne verifie pas la propriete du `unitId`, mais `aiMovableTiles` est calcule pour le
    JOUEUR COURANT -> on pilote MES unites pendant mon tour et les ENNEMIES pendant le leur (runner
    `--no-ai` : rien ne bouge tout seul)."""
    d = _dv(sid, rid)
    foes0 = sorted((u for u in (d.get("units") or []) if u.get("alive") and not u.get("ctrl")),
                   key=lambda u: u["id"])
    if len(foes0) < 3:
        raise RuntimeError("il faut >= 3 ennemis pour separer contact / seuil / hors-portee")
    want = {int(foes0[0]["id"]): 1, int(foes0[1]["id"]): CONFIG_RANGE,
            int(foes0[2]["id"]): CONFIG_RANGE + 1}      # `hors` = SEUIL+1, le cas limite serre
    labels = {int(foes0[0]["id"]): "contact", int(foes0[1]["id"]): "seuil",
              int(foes0[2]["id"]): "hors"}
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
        ok_foes = (cur[foes0[0]["id"]] == 1 and cur[foes0[1]["id"]] == CONFIG_RANGE
                   and cur[foes0[2]["id"]] > CONFIG_RANGE)
        if ok_foes and 1 <= d_ally <= CONFIG_RANGE:
            return int(caster["id"]), int(ally["id"]), {labels[i]: i for i in want}
        if d_ally > CONFIG_RANGE or d_ally == 0:
            _step_toward(sid, rid, int(ally["id"]), cp, 2)
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
    klass = ABILITY_CLASSES[SPIRIT_LEECH]
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
    if variant == "sansDynamic":
        class _NoDyn(klass):
            __slots__ = ()
            TARGETING_OPTIONS = _replace(
                opts, rules=int(opts.rules) & ~int(TR.TargetMatchesDynamicRule))
        return _NoDyn()
    if variant == "forceMeleeTrue":      # le champ du preset VOISIN (1014 ArmoriumCherub, +0x140)
        class _FM(klass):
            __slots__ = ()
            TARGETING_OPTIONS = _replace(opts, force_melee_target=RANGED_BOOL_TRUE)
        return _FM()

    class _NoRange(klass):
        __slots__ = ()
        TARGETING_OPTIONS = _replace(opts, range=None)
    return _NoRange()


VARIANTS = ("apres", "avant", "sansEnemy", "sansRange", "forceMeleeTrue", "sansDynamic")


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
                  {"runnerId": rid, "casterId": cid, "abilityType": SPIRIT_LEECH}, 60)
        usable = bool(((nat0 or {}).get("abilityState") or {}).get("usable"))
        caster_u = next(u for u in dv["units"] if u["id"] == cid)
        print("[state] caster=u%d(%s) pos=%s ctrl=%s usable=%s allie=u%d ennemis=%s"
              % (cid, caster_u.get("visualId"), _pos(caster_u), caster_u.get("ctrl"),
                 usable, ally_id, foes))
        if not usable:
            print("[FAIL] 1104 non utilisable -> l'oracle court-circuite (`ValidRequest`), "
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
                      "abilityType": SPIRIT_LEECH}, 60)
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
        mask = int(ABILITY_CLASSES[SPIRIT_LEECH].TARGETING_OPTIONS.rules)
        print("\n[reasons] caster=u%d ability=%d (masque 0x%x, range=config %d)"
              % (cid, SPIRIT_LEECH, mask, CONFIG_RANGE))
        head = ("  %-26s %-5s %-3s %-11s %-18s" % ("cible", "id", "d", "natif", "regle")
                + "".join("%-13s" % v for v in VARIANTS) + "accord")
        print(head)
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
        seuil = [r for r in rows if r["dist"] == CONFIG_RANGE and r["label"].startswith("ENNEMI")]
        sur = [r for r in rows if r["dist"] == CONFIG_RANGE + 1 and r["label"].startswith("ENNEMI")]
        for lbl, sel, att in (("d=%d (SEUIL, attendu ACCEPTE)" % CONFIG_RANGE, seuil, 0),
                              ("d=%d (SEUIL+1, attendu TargetIsInRange)" % (CONFIG_RANGE + 1),
                               sur, int(TR.TargetIsInRange))):
            print("[cas limite %s] %s"
                  % (lbl, "natif=%s port=%s -> %s"
                     % (hex(sel[0]["nat"]), hex(sel[0]["apres"]),
                        "OK" if sel[0]["nat"] == sel[0]["apres"] == att else "MISMATCH")
                     if sel else "ABSENT sur ce board (les lignes plus lointaines portent le "
                                 "verdict de refus)"))
        print("\n[bilan] accord natif/APRES : %d/%d ; lignes ou le natif REFUSE et AVANT rendait 0 "
              "(casts illegaux que master acceptait) : %d" % (n_agree, len(rows), n_gain))
        print("[garde] au moins une cible ACCEPTEE (0x0) : %s -> le court-circuit d'ability ne mord "
              "pas ; TargetIsEnemy observe : %s ; TargetIsInRange observe : %s"
              % ("OUI" if has_acc else "NON", "OUI" if has_enemy_ref else "NON",
                 "OUI" if has_range_ref else "NON"))
        print("[volet CASTER] casterReason natif = %s ; port = %s (le masque ne porte AUCUN bit du "
              "volet caster)" % (sorted(x for x in set(r["nat_caster"] for r in rows)
                                        if x is not None), hex(port_caster)))
        print("[contrefactuels] lignes en DESACCORD avec le natif quand on neutralise/inverse "
              "un champ :")
        for v in VARIANTS[1:]:
            note = ""
            if v == "sansDynamic":
                note = ("   <- ATTENDU 0 : bit pose mais INERTE (aucun corps "
                        "`SpiritLeechAbility$$GetDynamicInvalidTargetReason`)")
            if v == "forceMeleeTrue":
                note = "   <- le `forceMeleeTarget` du preset VOISIN 1014"
            print("    %-16s %d/%d%s" % (v, cf[v], len(rows), note))
        ok = (n_agree == len(rows) and has_acc and has_enemy_ref and has_range_ref
              and n_gain > 0 and cf["sansEnemy"] > 0 and cf["sansRange"] > 0
              and cf["forceMeleeTrue"] > 0 and cf["sansDynamic"] == 0 and port_caster == 0
              and bool(seuil) and seuil[0]["nat"] == 0)
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
