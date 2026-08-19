#!/usr/bin/env python
"""probe_254_loki_solo_targeting -- ARMEMENT du gate de cible des QUATRE abilities a MODULE UNIQUE :
1076 MV71SniperDroneSquadAttack, 1113 Stormcaller, 1118 DoctrinaImperatives, 1151 TheQuickening.

CE QUE CE PROBE MESURE
----------------------
Les quatre entraient dans `ABILITY_CLASSES` SANS `TARGETING_OPTIONS` -> `get_invalid_target_reason`
commence par `options = getattr(ability, "TARGETING_OPTIONS", None)` et rend 0 immediatement : AUCUN
gate. Degradation PERMISSIVE (ni erreur ni crash), donc invisible en self-play -- exactement
l'espace qu'un entrainement RL irait exploiter.

LES MASQUES, LUS AU DECOMPILE -- QUATRE ABILITIES, QUATRE FORMES DE CTOR
-----------------------------------------------------------------------
  1076 `...Triggered.Loki.MV71SniperDroneSquadAttackAbility$$.ctor`   FACTORY NOMMEE (forme 4)
       `TargetingOptions$$CustomLokiNormalAttackOptions(&opts, 2)` : recopie le preset
       `<TargetingOptions statics>+0x00` et COMBINE `Rules` -> `0x4002 | 2` = 0x4002
       = TargetMatchesDynamicRule | TargetIsEnemy.
       range = `TargetingRange statics+0x00` = RANGE_ADJACENT_IF_MELEE_CASTER ;
       forceMeleeTarget = 2 = RangedBool.IfRangedCaster.
       ⚠ NON CONFRONTABLE -- cf. `_probe_1076_carriers` ci-dessous.
  1113 `...Active.Loki.StormcallerAbility$$.ctor`                     PRESET + FLAGS (forme 2)
       preset `statics+0x180` + flags `0x200000000` -> `0x200000000 | 0x4002` = 0x200004002
       = TargetMatchesDynamicRule | TargetIsEnemy | TargetIsNotAnObject.
       range = `TargetingRange statics+0x18` = RANGE_FROM_CONFIG (`constants.range` = 3) ;
       forceMeleeTarget = 1 = RangedBool.False.
  1118 `...Active.Loki.DoctrinaImperativesAbility$$.ctor`              FLAGS DIRECTS (forme 1)
       `TargetingOptions..ctor(&opts, 1, &range, 1, 0x80, 0,0,0)` -> 0x80 = AddCaster SEUL.
       range = `TargetingRange statics+0x60` = RANGE_SELF (`overrideRange = 0`) ; isSelfCasting = 1.
       C'est la PORTEE, et non `rules`, qui porte tout le gate ici.
  1151 `...Active.Loki.TheQuickeningAbility$$.ctor`                    PRESET + FLAGS (forme 2)
       preset `statics+0x200` + flags `0x806000000` -> `0x806000000 | 0x42` = 0x806000042
       = TargetMatchesDynamicRule | TargetIsTile | AllowObscuredTargetByElevation |
         AllowObscuredTargetByWalls | CasterHas1Tiles.
       range = RANGE_FROM_CONFIG (`constants.range` = 2) ; forceMeleeTarget = RangedBool.False.

LES ECARTS ATTENDUS, NOMMES D'AVANCE (pas des surprises a expliquer apres coup)
------------------------------------------------------------------------------
Les trois abilities confrontables posent `TargetMatchesDynamicRule` (0x2), dont la regle-delegue
`<X>Ability$$GetDynamicInvalidTargetReason` n'est pas portee -> le port rend 0 la ou le natif peut
rendre 0x2. Ces lignes sont comptees SEPAREMENT et NOMMEES (`NON_PORTES`), jamais absoutes en
silence. Idem `TargetIsNotAnObject` (bit 33, 1113) : regle du filtre statique non portee.

ORACLE = le LIVE : `abilityReason(casterId, abilityType, targetId)` ->
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` natif. Le port rejoue le gate
OFFLINE sur le MEME etat fige, en variantes : APRES (registre), AVANT (`TARGETING_OPTIONS = None`,
l'etat de `master`), un contrefactuel PAR BIT PORTE, plus `sansRange` et `forceMeleeTrue`.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_254_loki_solo_targeting.py
    python probe_254_loki_solo_targeting.py --couple 2
    python probe_254_loki_solo_targeting.py --only units --seed 31337 --board C4_09

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

import gameconfig as GC                                              # noqa: E402
import hexgeo                                                        # noqa: E402
import unit_map as UM                                                # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting import (get_invalid_caster_reason,   # noqa: E402
                                               get_invalid_target_reason,
                                               RANGED_BOOL_TRUE)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

MV71, STORMCALLER, DOCTRINA, QUICKENING = 1076, 1113, 1118, 1151

# --- montage UNITES : les deux porteurs a cible-UNITE, face a des ennemis --------------------------
#     `admecMarshall` (1118, self-cast portee 0) et `spaceStormcaller` (1113, portee 3) dans la MEME
#     equipe : un seul montage suffit a exercer les deux, et l'allie de l'un est le caster de l'autre.
U_P_UNITS = "admecMarshall,spaceStormcaller"
U_A_UNITS = "necroWarden,necroWarden,necroWarden"
# --- montage TUILE : `bloodMephiston` (1151, cast TILE-TARGET, portee 2) --------------------------
T_P_UNITS = "bloodMephiston,bloodIntercessor"
T_A_UNITS = "necroWarden,necroWarden"
# --- montage 1076 : `tauMarksman` porte le PASSIF `MV71SniperDroneSquad` -- on VERIFIE live si le
#     drone summone expose 1076 (le gameconfig ne l'attache a aucun kit).
M_P_UNITS = "tauMarksman,tauShadowsun"
M_A_UNITS = "necroWarden,necroWarden"

# DEUX couples board/seed distincts (exigence de la campagne : l'accord doit tenir sur les deux).
COUPLES = [("MC1_67", "777"), ("C4_09", "31337")]

TOURS_DE_CHAUFFE = 6                # purge les `initialCooldownTurns` (sinon `ValidRequest` partout)
_seq = itertools.count()

# LES REGLES QUE LA CASCADE PORTEE NE SAIT PAS RENDRE -- chacune est inventoriee comme NON PORTEE en
# tete d'`abilities/targeting.py`, et chacune degrade du cote PERMISSIF (le port rend 0). Une ligne
# natif == EXACTEMENT l'un de ces codes ET port == 0 n'est pas un desaccord de transcription : elle
# est comptee a part et NOMMEE. Toute autre valeur -- y compris ces bits COMBINES -- reste un
# MISMATCH.
NON_PORTES = {
    int(TR.TargetMatchesDynamicRule):
        "regle-delegue de l'ability (`<X>Ability$$GetDynamicInvalidTargetReason`) -- non portee "
        "(point d'extension par ability, cf. `ActiveAbility.get_dynamic_invalid_target_reason`)",
    int(TR.TargetIsNotAnObject):
        "`TargetIsNotAnObject` (bit 33) -- regle du filtre statique NON PORTEE (elle refuse une "
        "cible portant le trait 0xd `Object`) ; seul porteur du registre : 1113",
    int(TR.AddCasterIfAtLeastOneTarget):
        "`IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason` -- non portee (elle "
        "depend de `TargetingQuery$$GetValidTargets`, qui ENUMERE tout le plateau)",
}


def _known_gap(nat, apres) -> int:
    """Le code non porte responsable de la ligne, ou 0. Exige `apres == 0` : un port qui rendrait
    autre chose que « pas de refus » ne serait pas dans la degradation permissive attendue."""
    return int(nat) if (nat in NON_PORTES and int(apres) == 0) else 0


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _build(seed: str, board: str, p_units: str, a_units: str):
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, versionne).
    ATTEND qu'un slot se libere si MAX_RUNNERS est sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe254-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--p-units", p_units, "--a-units", a_units]
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
    main. On ne COMPTE pas les endturn : quand toutes les unites d'un camp ont agi le moteur bascule
    deja seul, un endturn de plus cloturerait le tour de l'ADVERSAIRE et decalerait la parite."""
    for _ in range(maxit):
        t = _movable(sid, rid, unit_id)
        if t:
            return t
        _act(sid, rid, {"kind": "endturn"}, 60)
    return []


def _step_toward(sid, rid, unit_id, goal_pos, want: int) -> bool:
    """Rapproche (ou eloigne) `unit_id` jusqu'a une distance `want` de `goal_pos`, dans la limite de
    SON deplacement du tour."""
    tiles = _wait_movable(sid, rid, unit_id)
    if not tiles:
        return False
    best = min(tiles, key=lambda t: (abs(hexgeo.distance(t, goal_pos) - want), t))
    _act(sid, rid, {"kind": "move", "unitId": unit_id,
                    "to": {"col": best[0], "row": best[1]}}, 90)
    return True


def _my_turn(sid, rid, vis, maxit=8):
    """Rend la main au camp de l'unite `vis` (chaine de `endturn`, runner `--no-ai`). On NOMME le
    camp voulu : tester `currentPlayer == <une unite ctrl>.owner` serait une tautologie, et ce probe
    pilote les DEUX camps pour monter sa geometrie."""
    for _ in range(maxit):
        d = _dv(sid, rid)
        me = _by_vis(d, vis)
        if me is not None and me.get("ctrl"):
            return d
        _act(sid, rid, {"kind": "endturn"}, 60)
    return _dv(sid, rid)


# --------------------------------------------------------------------------- variantes du port

def _variant(aid: int, kind: str, bit: int = 0):
    """Une instance d'ability du registre, eventuellement AMPUTEE d'un champ ou d'un bit.

    `avant` = l'etat de `master` (masque absent -> aucun gate). Les autres sont les CONTREFACTUELS
    PAR CHAMP exiges : un champ dont la neutralisation ne change RIEN n'est pas valide par la mesure,
    et le bilan le dit explicitement."""
    klass = ABILITY_CLASSES[aid]
    base = klass.TARGETING_OPTIONS
    if kind == "apres":
        return klass()
    if kind == "avant":
        opts = None
    elif kind == "sansBit":
        opts = _replace(base, rules=int(base.rules) & ~int(bit))
    elif kind == "sansRange":
        opts = _replace(base, range=None)
    elif kind == "forceMeleeTrue":
        opts = _replace(base, force_melee_target=RANGED_BOOL_TRUE)
    else:
        raise ValueError(kind)

    class _V(klass):                     # meme classe -> meme cascade, seul le masque change
        __slots__ = ()
        TARGETING_OPTIONS = opts
    return _V()


def _ported_bits(aid: int):
    """Les bits du masque que la cascade portee SAIT consommer -- ceux dont on peut exiger qu'un
    contrefactuel deplace un verdict. Les autres (declaratifs / volet caster / non portes) sont
    listes a part dans le bilan, sans exigence."""
    portes = (TR.TargetIsTile, TR.TargetIsCaster, TR.TargetIsFriendly, TR.TargetIsEnemy,
              TR.TargetHasFreeAdjacentTile, TR.TargetTileIsFree, TR.TargetIsNotAdjacent,
              TR.TargetIsNotAdjacentToEnemy, TR.TargetIsCasterOrEnemy)
    rules = int(ABILITY_CLASSES[aid].TARGETING_OPTIONS.rules)
    return [b for b in portes if rules & int(b)]


# --------------------------------------------------------------------------- mesure d'une ability

def _nat(sid, rid, cid, aid, tid=None):
    body = {"runnerId": rid, "casterId": cid, "abilityType": aid}
    if tid is not None:
        body["targetId"] = tid
    nat = _r(sid, "abilityReason", body, 60) or {}
    tr = nat.get("targetReason") or {}
    cr = nat.get("casterReason") or {}
    h = tr.get("hex")
    val = int(h, 16) if isinstance(h, str) else (
        0 if tr.get("ruleClass") == "NoBrokenTargetingRule" else None)
    ch = cr.get("hex")
    cval = int(ch, 16) if isinstance(ch, str) else (
        0 if cr.get("ruleClass") == "NoBrokenTargetingRule" else None)
    return val, (tr.get("reasons") or []), cval, nat


def _measure(sid, rid, st, aid: int, cid: int, targets, label_of) -> dict:
    """Une ligne par cible : verdict NATIF vs port (APRES / AVANT / contrefactuels)."""
    bits = _ported_bits(aid)
    rows = []
    for tid in targets:
        nat_val, nat_reasons, nat_caster, _raw = _nat(sid, rid, cid, aid, tid)
        row = {
            "label": label_of(tid), "targetId": tid,
            "nat": nat_val, "nat_reasons": nat_reasons, "nat_caster": nat_caster,
            "apres": int(get_invalid_target_reason(st, cid, tid, _variant(aid, "apres"))),
            "avant": int(get_invalid_target_reason(st, cid, tid, _variant(aid, "avant"))),
            "sansRange": int(get_invalid_target_reason(st, cid, tid, _variant(aid, "sansRange"))),
            "forceMeleeTrue": int(get_invalid_target_reason(
                st, cid, tid, _variant(aid, "forceMeleeTrue"))),
        }
        for b in bits:
            row["sans_" + b.name] = int(get_invalid_target_reason(
                st, cid, tid, _variant(aid, "sansBit", b)))
        rows.append(row)
    return {"ability": aid, "caster": cid, "bits": [b.name for b in bits], "rows": rows}


def _report(res: dict) -> bool:
    aid, rows, bits = res["ability"], res["rows"], res["bits"]
    opts = ABILITY_CLASSES[aid].TARGETING_OPTIONS
    print("\n=== ability %d [%s]  masque 0x%x  self_cast=%s  range=%s  forceMelee=%d"
          % (aid, res.get("couple", "-"), int(opts.rules), opts.self_cast, opts.range,
             opts.force_melee_target))
    print("  %-34s %-6s %-12s %-26s %-12s %-12s"
          % ("cible", "id", "natif", "regle", "APRES", "AVANT"))
    n_ok = n_gap = n_gain = 0
    gaps = {}
    for r in rows:
        gap = _known_gap(r["nat"], r["apres"])
        agree = (r["nat"] == r["apres"])
        n_gap += 1 if gap else 0
        if gap:
            gaps[gap] = gaps.get(gap, 0) + 1
        n_ok += 1 if (agree or gap) else 0
        gain = (r["nat"] not in (None, 0)) and r["avant"] == 0 and not gap
        n_gain += 1 if gain else 0
        print("  %-34s %-6d %-12s %-26s %-12s %-12s %s%s"
              % (r["label"], r["targetId"], "-" if r["nat"] is None else hex(r["nat"]),
                 ",".join(r["nat_reasons"]) or "-", hex(r["apres"]), hex(r["avant"]),
                 "GAP-permissif" if gap else ("OK" if agree else "MISMATCH"),
                 "  <-GAIN" if gain else ""))
    for code, n in sorted(gaps.items()):
        print("      [GAP %s x%d] %s" % (hex(code), n, NON_PORTES[code]))
    # --- contrefactuels PAR CHAMP : un champ dont la neutralisation ne bouge RIEN est NON VALIDE.
    #     On compte les deplacements DANS LES DEUX SENS (une neutralisation peut faux-REFUSER, pas
    #     seulement faux-accepter) -> le comparatif porte sur TOUTES les lignes, pas les seuls refus.
    cf, cf_refus = {}, {}
    refus = [r for r in rows if r["nat"] not in (None, 0) and not _known_gap(r["nat"], r["apres"])]
    for key in (["sans_" + b for b in bits] + ["sansRange", "forceMeleeTrue"]):
        cf[key] = sum(1 for r in rows if r[key] != r["apres"])
        cf_refus[key] = sum(1 for r in refus if r[key] != r["apres"])
    print("  [contrefactuels] %d lignes, dont %d refus natifs non-GAP ; lignes DEPLACEES :"
          % (len(rows), len(refus)))
    for key, n in cf.items():
        verdict = "PORTEUR (%d sur des refus)" % cf_refus[key] if n \
            else "INERTE dans ce montage (non valide par cette mesure)"
        print("      %-34s %2d  -> %s" % (key, n, verdict))
    print("  [bilan] accord natif/APRES : %d/%d (dont %d lignes GAP permissives, regles NON "
          "PORTEES nommees ci-dessus) ; casts illegaux que master acceptait : %d"
          % (n_ok, len(rows), n_gap, n_gain))
    res["n_ok"], res["n_rows"], res["n_gap"], res["n_gain"] = n_ok, len(rows), n_gap, n_gain
    res["cf"], res["cf_refus"] = cf, cf_refus
    res["gaps"] = {hex(k): v for k, v in gaps.items()}
    return n_ok == len(rows) and n_gain > 0


def _load_offline(sid, rid, adjacency="native_sym"):
    dv = _dv(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indisponible")
    board = Board(bg["tiles"], adjacency=adjacency)
    return load_state(dv, ob, snap, board=board), dv, board, bg


# --------------------------------------------------------------------------- montage UNITES

def _drive_units(sid, rid, rng: int = 3):
    """Geometrie DISCRIMINANTE du montage UNITES : `spaceStormcaller` a distance EXACTE `rng` d'un
    ennemi (le SEUIL de sa portee de config, `constants.range` = 3) et EXACTEMENT `rng + 1` d'un
    autre -- l'encadrement SERRE du seuil. Un ennemi « quelque part au-dela » ne prouverait que
    « loin = refuse » ; c'est la marche d'UNE case qui distingue une portee 3 d'une portee 4.
    `admecMarshall` (1118, portee 0) est amene a distance 1 du Stormcaller : il sert d'ALLIE proche
    pour 1113 (refus de CAMP a portee) et de caster self-cast pour 1118, dont le seuil est alors
    encadre aussi serre que possible (d = 0 accepte, d = 1 refuse)."""
    for it in range(16):
        d = _dv(sid, rid)
        njal = _by_vis(d, "spaceStormcaller")
        marsh = _by_vis(d, "admecMarshall")
        if njal is None or marsh is None:
            raise RuntimeError("montage impossible : un porteur est mort/absent")
        np_ = _pos(njal)
        foes = sorted((u for u in (d.get("units") or [])
                       if u.get("alive") and u.get("owner") != njal.get("owner")),
                      key=lambda u: hexgeo.distance(np_, _pos(u)))
        if len(foes) < 2:
            raise RuntimeError("il faut >= 2 ennemis pour encadrer le seuil de portee")
        d_marsh = hexgeo.distance(np_, _pos(marsh))
        at_r = [u for u in foes if hexgeo.distance(np_, _pos(u)) == rng]
        at_r1 = [u for u in foes if hexgeo.distance(np_, _pos(u)) == rng + 1]
        print("  [drive %d] njal=%s d(marshall)=%d d(ennemis)=%s"
              % (it, np_, d_marsh, [hexgeo.distance(np_, _pos(u)) for u in foes]))
        if at_r and at_r1 and d_marsh <= rng:
            return (int(njal["id"]), int(marsh["id"]), int(at_r[0]["id"]), int(at_r1[0]["id"]))
        # 1) un ennemi a EXACTEMENT `rng`
        if not at_r:
            _step_toward(sid, rid, int(foes[0]["id"]), np_, rng)
        # 2) un AUTRE ennemi a EXACTEMENT `rng + 1` -- la marche d'une case qui fait la mesure
        d = _dv(sid, rid)
        njal = _by_vis(d, "spaceStormcaller")
        np_ = _pos(njal)
        near = [u for u in (d.get("units") or [])
                if u.get("alive") and u.get("owner") != njal.get("owner")
                and hexgeo.distance(np_, _pos(u)) == rng]
        rest = [u for u in (d.get("units") or [])
                if u.get("alive") and u.get("owner") != njal.get("owner")
                and (not near or int(u["id"]) != int(near[0]["id"]))
                and hexgeo.distance(np_, _pos(u)) != rng + 1]
        for u in rest:
            _step_toward(sid, rid, int(u["id"]), np_, rng + 1)
        # 3) le Marshall a portee du Stormcaller (allie DANS le disque range 3)
        d = _dv(sid, rid)
        njal = _by_vis(d, "spaceStormcaller")
        marsh = _by_vis(d, "admecMarshall")
        if hexgeo.distance(_pos(njal), _pos(marsh)) > rng:
            _step_toward(sid, rid, int(marsh["id"]), _pos(njal), 2)
    raise RuntimeError("geometrie discriminante non atteinte (montage UNITES)")


def _run_units(sid, seed, board_id, couple: str):
    rid, sf = _build(seed, board_id, U_P_UNITS, U_A_UNITS)
    print("\n########## montage UNITES  runner=%d board=%s seed=%s" % (rid, board_id, seed))
    out = []
    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)
        njal, marsh, foe3, foe4 = _drive_units(sid, rid)
        _my_turn(sid, rid, "spaceStormcaller")
        st, dv, _b, _bg = _load_offline(sid, rid)
        units = {int(u["id"]): u for u in (dv.get("units") or []) if u.get("alive")}
        own = units[njal].get("owner")

        def _label(cid):
            def f(tid):
                u = units.get(tid) or {}
                side = ("CASTER" if tid == cid
                        else ("ALLIE" if u.get("owner") == own else "ENNEMI"))
                dd = hexgeo.distance(_pos(units.get(cid)), _pos(u))
                return "%s %s d=%d" % (side, u.get("visualId"), dd)
            return f

        ids = sorted(units)
        for aid, cid in ((STORMCALLER, njal), (DOCTRINA, marsh)):
            usable = bool(((_nat(sid, rid, cid, aid)[3] or {}).get("abilityState") or {})
                          .get("usable"))
            if not usable:
                print("\n=== ability %d : NON UTILISABLE sur ce montage -> l'oracle court-circuite "
                      "(`ValidRequest`), mesure IMPOSSIBLE" % aid)
                out.append({"ability": aid, "skipped": True, "couple": couple})
                continue
            res = _measure(sid, rid, st, aid, cid, ids, _label(cid))
            res["caster_port"] = int(get_invalid_caster_reason(st, cid, _variant(aid, "apres")))
            res["couple"] = couple
            res["seuils"] = {"foe_at_3": foe3, "foe_at_ge4": foe4}
            out.append(res)
        return out
    finally:
        _dispose(sid, rid, sf)


# --------------------------------------------------------------------------- montage TUILE (1151)

def _run_tiles(sid, seed, board_id, couple: str):
    """1151 TheQuickening : cast TILE-TARGET (`TargetIsTile`), portee de config 2. On interroge des
    TUILES a distance 0/1/2 (dans la portee) et 3/4 (hors portee) du caster, plus des tuiles NON
    MARCHABLES -- le natif rend alors le litteral `1` `ValidRequest` (aucun
    `AllowUnwalkableTargetTile` dans le masque)."""
    rid, sf = _build(seed, board_id, T_P_UNITS, T_A_UNITS)
    print("\n########## montage TUILES  runner=%d board=%s seed=%s" % (rid, board_id, seed))
    out = []
    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)
        _my_turn(sid, rid, "bloodMephiston")
        st, dv, _b, bg = _load_offline(sid, rid, adjacency="evenq")
        meph = _by_vis(dv, "bloodMephiston")
        if meph is None:
            raise RuntimeError("bloodMephiston absent/mort")
        cid = int(meph["id"])
        cpos = _pos(meph)
        occ = {_pos(u) for u in (dv.get("units") or []) if u.get("alive")}

        # ECHANTILLON encadrant le SEUIL des DEUX COTES : d=2 (accepte) et d=3 (refuse).
        par_d, nowalk = {}, []
        for t in bg["tiles"]:
            rc = (t["col"], t["row"])
            dd = hexgeo.distance(cpos, rc)
            if not t.get("walkable", True):
                nowalk.append((int(t["id"]), dd))
                continue
            if rc in occ:
                continue
            par_d.setdefault(dd, []).append(int(t["id"]))
        sample, labels = [], {}
        for dd in (1, 2, 3, 4):
            for tid in sorted(par_d.get(dd, []))[:2]:
                sample.append(tid)
                labels[tid] = "TUILE walk d=%d" % dd
        for tid, dd in sorted(nowalk)[:3]:
            sample.append(tid)
            labels[tid] = "TUILE NOWALK d=%d" % dd
        print("  [1151] caster=%s tuiles interrogees : %d (dont %d non marchables ; distances "
              "presentes : %s)" % (cpos, len(sample), min(3, len(nowalk)),
                                   sorted(d for d in par_d if d <= 4)))
        if not any(labels[t].startswith("TUILE walk d=2") for t in sample) or \
           not any(labels[t].startswith("TUILE walk d=3") for t in sample):
            print("  [1151] ⚠ le seuil 2/3 n'est PAS encadre des deux cotes sur ce board")

        usable = bool(((_nat(sid, rid, cid, QUICKENING)[3] or {}).get("abilityState") or {})
                      .get("usable"))
        if not usable:
            print("\n=== ability %d : NON UTILISABLE -> mesure IMPOSSIBLE" % QUICKENING)
            out.append({"ability": QUICKENING, "skipped": True, "couple": couple})
            return out
        res = _measure(sid, rid, st, QUICKENING, cid, sample, lambda t: labels[t])
        res["caster_port"] = int(get_invalid_caster_reason(st, cid, _variant(QUICKENING, "apres")))
        res["couple"] = couple
        res["n_nowalk"] = len(nowalk)
        out.append(res)
        return out
    finally:
        _dispose(sid, rid, sf)


# --------------------------------------------------------------------------- 1076 : confrontabilite

def _run_mv71(sid, seed, board_id, couple: str):
    """1076 -- LE PORTEUR NE SE LIT PAS DANS LE GAMECONFIG, ET C'EST LE LIVE QUI TRANCHE.

    Le balayage des 669 kits par ID d'ability ne rend RIEN pour 1076 (`GC.unit_abilities` n'attache
    l'id a aucun kit ; `tauMarksman` n'y porte que le PASSIF `MV71SniperDroneSquad`). Conclure
    « aucun porteur, non confrontable » sur cette seule base aurait ete FAUX : `decisionView
    (allAbilities=true)` montre `tauMarksman` exposant bel et bien 1076, et `abilityReason` traverse
    la cascade pour lui.

    ⚠ Cette ability est une `...Abilities.Triggered.` : son `abilityState` est **null** (pas
    d'`ActiveAbilityComponent`). Le cas RESSEMBLE au piege MoW de #249 -- mais il en DIFFERE, et la
    mesure le montre : ici `AttackQuery$$GetInvalidTargetReason` ne court-circuite PAS sur `0x1`,
    il rend les vraies regles rompues (`TargetIsEnemy` sur le caster/l'allie, `TargetIsInRange` sur
    l'ennemi hors portee d'arme). L'oracle `abilityReason` est donc exploitable ; on NE se rabat pas
    sur l'oracle ensembliste (que le court-circuit d'`abilityState` viderait, `targetCount = 0`).

    Geometrie DRIVEE : `tauMarksman` porte une arme `Range = 3` et `RANGE_ADJACENT_IF_MELEE_CASTER`
    laisse `onlyAdjacent = IfNotRangedCaster` -> FAUX pour lui, donc la portee EST celle de l'arme.
    On encadre ce seuil des deux cotes (un ennemi a d = R, un autre a d > R)."""
    offline = []
    for k in UM.all_kits():
        ab = GC.unit_abilities(k.get("id")) or {}
        if any(a.get("id") == MV71 for grp in ab.values() for a in (grp or [])):
            offline.append((k.get("id"), k.get("kind")))
    print("\n########## montage 1076 (tauMarksman)")
    print("  [offline] kits du gameconfig portant l'ID %d : %s" % (MV71, offline or "AUCUN"))

    rid, sf = _build(seed, board_id, M_P_UNITS, M_A_UNITS)
    out = []
    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)
        d = _dv(sid, rid)
        vus = {int(u["id"]): u.get("visualId") for u in (d.get("units") or [])
               for a in (u.get("abilities") or [])
               if int(a.get("id") or a.get("abilityId") or 0) == MV71}
        print("  [live] unites exposant l'ability %d : %s" % (MV71, vus or "AUCUNE"))
        if not vus:
            print("  [live] 1076 n'est exposee par personne -> NON CONFRONTABLE sur ce montage")
            return [{"ability": MV71, "skipped": True, "couple": couple}]
        cid = int(sorted(vus)[0])
        rng = _weapon_range(d, cid)
        print("  [1076] caster=%d (%s) portee d'arme attendue = %s" % (cid, vus[cid], rng))
        _drive_mv71(sid, rid, cid, rng)
        _my_turn(sid, rid, vus[cid])
        st, dv, _b, _bg = _load_offline(sid, rid)
        units = {int(u["id"]): u for u in (dv.get("units") or []) if u.get("alive")}
        own = units[cid].get("owner")

        def _label(tid):
            u = units.get(tid) or {}
            side = ("CASTER" if tid == cid
                    else ("ALLIE" if u.get("owner") == own else "ENNEMI"))
            return "%s %s d=%d" % (side, u.get("visualId"),
                                   hexgeo.distance(_pos(units.get(cid)), _pos(u)))

        res = _measure(sid, rid, st, MV71, cid, sorted(units), _label)
        res["caster_port"] = int(get_invalid_caster_reason(st, cid, _variant(MV71, "apres")))
        res["couple"] = couple
        res["offline_carriers"] = offline
        out.append(res)
        return out
    finally:
        _dispose(sid, rid, sf)


def _weapon_range(dec, uid) -> int:
    """La portee d'ARME du caster telle que `TargetingQuery$$GetRange` la calcule quand
    `onlyAdjacent` est faux : `max(weapons[].Range) + GetStat(ExtraRange)` (cf. `unit_weapon_range`).
    Lue ici pour SAVOIR ou placer le seuil, jamais pour le supposer."""
    u = next((x for x in (dec.get("units") or []) if int(x["id"]) == int(uid)), None)
    weapons = ((GC.unit((u or {}).get("visualId") or "") or {}).get("weapons")) or []
    ranged = [int(w.get("Range") or 0) for w in weapons if w.get("Range")]
    return max(ranged) if ranged else 1


def _drive_mv71(sid, rid, cid, rng: int):
    """Encadre le seuil de portee d'arme SERRE : UN ennemi a distance EXACTE `rng` (doit etre
    ACCEPTE) et un autre a EXACTEMENT `rng + 1` (doit rompre `TargetIsInRange`). Sans les deux, le
    volet portee n'est pas mesure -- et un ennemi « quelque part au-dela » ne distinguerait pas une
    portee 3 d'une portee 8."""
    for it in range(12):
        d = _dv(sid, rid)
        me = next((u for u in (d.get("units") or []) if int(u["id"]) == cid), None)
        if me is None:
            raise RuntimeError("le caster 1076 est mort/absent")
        mp = _pos(me)
        foes = sorted((u for u in (d.get("units") or [])
                       if u.get("alive") and u.get("owner") != me.get("owner")),
                      key=lambda u: hexgeo.distance(mp, _pos(u)))
        dists = [hexgeo.distance(mp, _pos(u)) for u in foes]
        print("  [drive %d] caster=%s d(ennemis)=%s" % (it, mp, dists))
        if any(x == rng for x in dists) and any(x == rng + 1 for x in dists):
            return
        if not any(x == rng for x in dists):
            _step_toward(sid, rid, int(foes[0]["id"]), mp, rng)
        d = _dv(sid, rid)
        me = next((u for u in (d.get("units") or []) if int(u["id"]) == cid), None)
        mp = _pos(me)
        at_r = [u for u in (d.get("units") or [])
                if u.get("alive") and u.get("owner") != me.get("owner")
                and hexgeo.distance(mp, _pos(u)) == rng]
        for u in (d.get("units") or []):
            if not u.get("alive") or u.get("owner") == me.get("owner"):
                continue
            if at_r and int(u["id"]) == int(at_r[0]["id"]):
                continue
            if hexgeo.distance(mp, _pos(u)) != rng + 1:
                _step_toward(sid, rid, int(u["id"]), mp, rng + 1)
    raise RuntimeError("seuil de portee non encadre (montage 1076)")


def _dispose(sid, rid, sf):
    try:
        _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
        sf.unlink(missing_ok=True)
        print("[cleanup] runner %d dispose" % rid)
    except Exception as e:                                           # noqa: BLE001
        print("[cleanup] dispose KO: %s" % e)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--couple", type=int, default=0,
                    help="1 ou 2 (defaut 0 = les DEUX couples board/seed)")
    ap.add_argument("--board", default="")
    ap.add_argument("--seed", default="")
    ap.add_argument("--only", default="", help="units|tiles|mv71 (defaut : tout)")
    a = ap.parse_args(argv)

    if a.board and a.seed:
        couples = [(a.board, a.seed)]
    elif a.couple in (1, 2):
        couples = [COUPLES[a.couple - 1]]
    else:
        couples = list(COUPLES)

    sid = _resolve_session()
    results = []
    for i, (board_id, seed) in enumerate(couples, 1):
        tag = "couple%d %s/%s" % (i, board_id, seed)
        if a.only in ("", "units"):
            results += _run_units(sid, seed, board_id, tag)
        if a.only in ("", "tiles"):
            results += _run_tiles(sid, seed, board_id, tag)
        if a.only in ("", "mv71"):
            results += _run_mv71(sid, seed, board_id, tag)

    ok = True
    print("\n================================ BILAN ================================")
    for res in results:
        if res.get("skipped"):
            print("  ability %d [%s] : NON MESUREE (ability non utilisable)"
                  % (res["ability"], res.get("couple")))
            ok = False
            continue
        ok = _report(res) and ok
    print("\n[VERDICT] %s" % ("PASS" if ok else "FAIL"))
    print("[RAW] " + json.dumps({"rows": results}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
