#!/usr/bin/env python
"""probe_249_deathguard_targeting -- ARMEMENT du gate de cible des CINQ abilities du module
`deathguard` : 1037 RevitalizingMalignancy, 1040 SpawnPoxwalkers, 1042 FlailSwing,
1168 EntropyCannons et 1169 PlagueburstMortar (les deux dernieres = actives de la MACHINE OF WAR
`deathCrawler`).

CE QUE CE PROBE MESURE
----------------------
Les cinq entraient dans `ABILITY_CLASSES` SANS `TARGETING_OPTIONS` -> `get_invalid_target_reason`
commence par `options = getattr(ability, "TARGETING_OPTIONS", None)` et rend 0 immediatement : AUCUN
gate. Degradation PERMISSIVE (ni erreur ni crash), donc invisible en self-play.

LES MASQUES, LUS AU DECOMPILE (jamais generalises depuis une voisine)
---------------------------------------------------------------------
  1037 `...Loki.RevitalizingMalignancyAbility$$.ctor`   FLAGS DIRECTS  0x8500
       = 0x100 TargetIsHealable | 0x400 TargetIsFriendly | 0x8000 CasterIsPossibleTarget
       range = `TargetingRange statics+0x30` = RANGE_ADJACENT ; isSelfCasting = 1
  1040 `...Loki.SpawnPoxwalkersAbility$$.ctor`          FLAGS DIRECTS  0x8000000004
       = 0x4 CasterMatchesDynamicRule | 0x8000000000 TargetIsCaster
       range = `TargetingRange$$CustomRange(GetRange)` -> overrideRangeFunc pose (delegue NON
       resolu) ; isSelfCasting = 1
  1042 `...Loki.FlailSwingAbility$$.ctor`               PRESET STATIQUE COPIE (aucun ctor)
       masque effectif = `*(TargetingOptions statics+0x68)` = 0x4000 TargetIsEnemy
       range = RANGE_ADJACENT (le preset `statics+0x40`, le MEME que 1043 -- qui, lui, passe par la
       surcharge PRESET + FLAGS et vaut donc 0x10004000 : le preset ne suffit JAMAIS)
  1168 `...Active.EntropyCannonsAbility$$.ctor`         FLAGS DIRECTS  0x40004002
       = 0x2 TargetMatchesDynamicRule | 0x4000 TargetIsEnemy | 0x40000000 AllowNullCasterTile
       range = `TargetingRange statics+0x48` = RANGE_WHOLE_BOARD
  1169 `...Active.PlagueburstMortarAbility$$.ctor`      FLAGS DIRECTS  0x40000042
       = 0x2 TargetMatchesDynamicRule | 0x40 TargetIsTile | 0x40000000 AllowNullCasterTile
       range = RANGE_WHOLE_BOARD

L'ECART ATTENDU, NOMME D'AVANCE (pas une surprise a expliquer apres coup)
------------------------------------------------------------------------
1168 et 1169 posent `TargetMatchesDynamicRule` (0x2). Le port garde le defaut 0 de
`ActiveAbility.get_dynamic_invalid_target_reason` : pour 1168 la regle native
(`...EntropyCannonsAbility$$GetDynamicInvalidTargetReason`) accepte une cible sous aura Contagion
ALLIEE **ou** a FixedArmor negativement modifiee, et la branche AURA n'est pas materialisable
offline -> porter la seule branche ARMURE REFUSERAIT des cibles legales (degradation STRICTE). Toute
ligne ou le natif rend exactement `0x2` est donc comptee a part : c'est l'ecart PERMISSIF connu, pas
un desaccord de transcription. Le montage AURA (amener `deathTyphus` au contact) ferme cet ecart et
le probe le VERIFIE.

FERME PAR #245 : `TargetIsHealable` (bit 8, 0x100) etait le SECOND ecart attendu de 1037 -- l'allie
adjacent a PV pleins, que le natif refusait et que le port acceptait. La regle est desormais portee
(slot 0x11 d'`IAttackQuery` = `AttackQuery$$EntityCanBeHealed`), elle est sortie de `NON_PORTES` et
son bit est entre dans `_ported_bits` : la ligne est un ACCORD, et le contrefactuel
`sans_TargetIsHealable` la deplace.

ORACLE = le LIVE : `abilityReason(casterId, abilityType, targetId)` -> `TargetingQuery$$
GetInvalidTargetReason` natif. Le port rejoue le gate OFFLINE sur le MEME etat fige, en variantes :
  * APRES  = l'ability du registre ;
  * AVANT  = la MEME classe avec `TARGETING_OPTIONS = None` (l'etat de `master`) ;
  * un contrefactuel PAR BIT PORTE du masque, plus `sansRange` et `forceMeleeTrue`.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_249_deathguard_targeting.py
    python probe_249_deathguard_targeting.py --seed 31337 --board C4_09 --mow-board C1_09

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
import oracle_targeting as O                                         # noqa: E402
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

REVITALIZING, POXWALKERS, FLAIL = 1037, 1040, 1042
ENTROPY, MORTAR = 1168, 1169

# --- montage UNITES : les trois heros Death Guard porteurs, face a trois necrons -----------------
U_P_UNITS = "deathRotbone,deathBlightlord,deathBlightbringer"
U_A_UNITS = "necroWarden,necroWarden,necroWarden"
U_BOARD, U_SEED = "MC1_67", "777"
# --- montage MoW : le porteur de l'aura Contagion (deathTyphus) + la MoW deathCrawler ------------
M_P_UNITS = "deathTyphus,deathPutrifier"
M_A_UNITS = "ultraTitus,ultraTitus"
M_MOW = "deathCrawler"
M_BOARD, M_SEED = "C1_02", "4242"          # board MoW-capable (slot MachineOfWarPosition)

TOURS_DE_CHAUFFE = 6                # purge les `initialCooldownTurns` (sinon `ValidRequest` partout)
_seq = itertools.count()

# LES TROIS CODES QUE LA CASCADE PORTEE NE SAIT PAS RENDRE -- chacun est une regle NON PORTEE,
# inventoriee comme telle en tete d'`abilities/targeting.py`, et chacun degrade du cote PERMISSIF
# (le port rend 0). Une ligne natif == EXACTEMENT l'un d'eux ET port == 0 n'est pas un desaccord de
# transcription : elle est comptee SEPAREMENT et NOMMEE, jamais silencieusement absoute. Toute autre
# valeur -- y compris ces memes bits COMBINES a d'autres -- reste un MISMATCH.
NON_PORTES = {
    int(TR.TargetMatchesDynamicRule):
        "regle-delegue de l'ability (`<X>Ability$$GetDynamicInvalidTargetReason`) -- non portee : "
        "pour 1168 sa branche AURA n'est pas materialisable offline, porter la seule branche ARMURE "
        "REFUSERAIT des cibles legales",
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


def _build(seed: str, board: str, p_units: str, a_units: str, p_mow: str = ""):
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, versionne).
    ATTEND qu'un slot se libere si MAX_RUNNERS est sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe249-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--p-units", p_units, "--a-units", a_units]
    if p_mow:
        argv += ["--p-mow", p_mow]
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
              TR.TargetIsHealable, TR.TargetHasFreeAdjacentTile, TR.TargetTileIsFree,
              TR.TargetIsNotAdjacent, TR.TargetIsNotAdjacentToEnemy, TR.TargetIsCasterOrEnemy)
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


def _ability_targets(sid, rid, cid, aid):
    """`abilityTargets` -> `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` +
    la cascade COMPLETE. C'est l'oracle ENSEMBLISTE, et pour un caster MACHINE OF WAR en domaine
    UNITE c'est le SEUL exploitable : MESURE (diag de ce cas, runner 1221) -- `abilityReason` rend
    `0x1` sur une cible que `abilityTargets` declare pourtant LEGALE, parce que la surcharge 4
    arguments d'`IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` court-circuite sur
    `ActiveAbilityComponent.GetOrNull(<composant du caster>, abilityType) == null` et rend
    `GenericBrokenTargetingRule(1)` AVANT toute cascade -- les abilities d'une MoW ne vivent pas dans
    un `ActiveAbilityComponent` d'unite. Un « oracle » lu la ne mesurerait rien du masque."""
    at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": aid}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == cid), None)
    if row is None:
        return None
    for a in (row.get("abilities") or []):
        return {int(t["targetId"]) for t in (a.get("targets") or []) if t.get("targetId") is not None}
    return set()


def _measure_set(sid, rid, st, aid: int, cid: int, units, label_of, phase: str) -> dict:
    """Oracle ENSEMBLISTE : l'ensemble des cibles que le NATIF juge legales, contre l'ensemble que le
    port accepte (raison 0) sur le MEME etat fige. Employe pour 1168 (caster MoW, domaine unite)."""
    nat = _ability_targets(sid, rid, cid, aid)
    bits = _ported_bits(aid)
    rows = []
    for tid in units:
        row = {"label": label_of(tid), "targetId": tid,
               "nat_legal": (None if nat is None else (tid in nat)),
               "apres": int(get_invalid_target_reason(st, cid, tid, _variant(aid, "apres"))),
               "avant": int(get_invalid_target_reason(st, cid, tid, _variant(aid, "avant")))}
        for b in bits:
            row["sans_" + b.name] = int(get_invalid_target_reason(
                st, cid, tid, _variant(aid, "sansBit", b)))
        rows.append(row)
    return {"ability": aid, "caster": cid, "bits": [b.name for b in bits], "rows": rows,
            "phase": phase, "oracle": "abilityTargets", "nat_set": sorted(nat or [])}


def _report_set(res: dict) -> bool:
    """Verdict de l'oracle ENSEMBLISTE. Le port ne portant PAS la regle dynamique (bit 0x2), il ne
    peut qu'accepter un SUR-ENSEMBLE du natif : on exige donc (a) que le port n'accepte JAMAIS une
    cible que le natif refuse POUR UNE RAISON PORTEE (camp), et (b) qu'il accepte toutes celles que
    le natif accepte. Le sur-ensemble residuel est NOMME (regle dynamique) et compte a part."""
    aid, rows = res["ability"], res["rows"]
    opts = ABILITY_CLASSES[aid].TARGETING_OPTIONS
    print("\n=== ability %d [%s, oracle=abilityTargets]  masque 0x%x  range=%s"
          % (aid, res["phase"], int(opts.rules), opts.range))
    print("  cibles LEGALES natives : %s" % (res["nat_set"],))
    print("  %-30s %-6s %-14s %-12s %-12s" % ("cible", "id", "natif", "APRES", "AVANT"))
    n_strict = n_gain = n_over = 0
    for r in rows:
        port_ok = (r["apres"] == 0)
        avant_ok = (r["avant"] == 0)
        strict = port_ok and not r["nat_legal"]        # le port accepte ce que le natif refuse
        miss = (not port_ok) and r["nat_legal"]        # le port REFUSE une cible legale = FAUTE
        n_over += 1 if strict else 0
        n_strict += 1 if miss else 0
        gain = (not r["nat_legal"]) and avant_ok and not port_ok
        n_gain += 1 if gain else 0
        print("  %-30s %-6d %-14s %-12s %-12s %s%s"
              % (r["label"], r["targetId"], "LEGAL" if r["nat_legal"] else "refuse",
                 hex(r["apres"]), hex(r["avant"]),
                 "FAUX-REFUS" if miss else ("sur-ensemble(DYN)" if strict else "OK"),
                 "  <-GAIN" if gain else ""))
    for key in (["sans_" + b for b in res["bits"]]):
        n = sum(1 for r in rows if r[key] != r["apres"])
        print("      %-34s %2d  -> %s" % (key, n, "PORTEUR" if n else "INERTE dans ce montage"))
    print("  [bilan] faux-refus (port REFUSE une cible legale) : %d ; sur-ensemble permissif "
          "(regle dynamique non portee) : %d ; casts illegaux que master acceptait : %d"
          % (n_strict, n_over, n_gain))
    res["n_strict"], res["n_over"], res["n_gain"] = n_strict, n_over, n_gain
    return n_strict == 0


def _measure(sid, rid, st, dv, aid: int, cid: int, targets, label_of) -> dict:
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
    print("\n=== ability %d  masque 0x%x  self_cast=%s  range=%s  forceMelee=%d"
          % (aid, int(opts.rules), opts.self_cast, opts.range, opts.force_melee_target))
    hdr = "  %-30s %-6s %-12s %-26s %-12s %-12s" % ("cible", "id", "natif", "regle", "APRES", "AVANT")
    print(hdr)
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
        print("  %-30s %-6d %-12s %-26s %-12s %-12s %s%s"
              % (r["label"], r["targetId"], "-" if r["nat"] is None else hex(r["nat"]),
                 ",".join(r["nat_reasons"]) or "-", hex(r["apres"]), hex(r["avant"]),
                 "GAP-permissif" if gap else ("OK" if agree else "MISMATCH"),
                 "  <-GAIN" if gain else ""))
    for code, n in sorted(gaps.items()):
        print("      [GAP %s x%d] %s" % (hex(code), n, NON_PORTES[code]))
    # --- contrefactuels PAR CHAMP : un champ dont la neutralisation ne bouge RIEN est NON VALIDE
    refus = [r for r in rows if r["nat"] not in (None, 0)
             and not _known_gap(r["nat"], r["apres"])]
    cf = {}
    for key in (["sans_" + b for b in bits] + ["sansRange", "forceMeleeTrue"]):
        cf[key] = sum(1 for r in refus if r[key] != r["apres"])
    print("  [contrefactuels] refus natifs non-DYN = %d ; lignes DEPLACEES par la neutralisation :"
          % len(refus))
    for key, n in cf.items():
        verdict = "PORTEUR" if n else "INERTE dans ce montage (non valide par cette mesure)"
        print("      %-34s %2d  -> %s" % (key, n, verdict))
    print("  [bilan] accord natif/APRES : %d/%d (dont %d lignes GAP permissives, regles NON "
          "PORTEES nommees ci-dessus) ; casts illegaux que master acceptait : %d"
          % (n_ok, len(rows), n_gap, n_gain))
    res["n_ok"], res["n_rows"], res["n_gap"], res["n_gain"], res["cf"] = (
        n_ok, len(rows), n_gap, n_gain, cf)
    res["gaps"] = {hex(k): v for k, v in gaps.items()}
    return n_ok == len(rows) and n_gain > 0


# --------------------------------------------------------------------------- montage UNITES

def _drive_units(sid, rid):
    """Geometrie DISCRIMINANTE du montage UNITES : `deathRotbone` au contact de `deathBlightlord`
    (allie) ET d'un necron (ennemi), `deathBlightbringer` HORS contact (allie loin), au moins un
    necron HORS contact. C'est le seul arrangement qui separe, pour 1037, le refus de CAMP
    (`TargetIsFriendly`, sur l'ennemi au contact) du refus de PORTEE (`TargetIsInRange`, sur l'allie
    loin) -- et symetriquement pour 1042.

    `applyAction` ne verifie pas la propriete du `unitId` mais `aiMovableTiles` est calcule pour le
    JOUEUR COURANT -> on pilote MES unites pendant mon tour et les ennemies pendant le leur (runner
    `--no-ai` : rien ne bouge tout seul)."""
    for it in range(14):
        d = _dv(sid, rid)
        rot = _by_vis(d, "deathRotbone")
        lord = _by_vis(d, "deathBlightlord")
        bring = _by_vis(d, "deathBlightbringer")
        if rot is None or lord is None or bring is None:
            raise RuntimeError("montage impossible : une unite du trio est morte/absente")
        foes = sorted((u for u in (d.get("units") or [])
                       if u.get("alive") and u.get("owner") != rot.get("owner")),
                      key=lambda u: int(u["id"]))
        if len(foes) < 2:
            raise RuntimeError("il faut >= 2 ennemis pour separer contact / hors-contact")
        rp = _pos(rot)
        near = foes[0]
        d_near = hexgeo.distance(rp, _pos(near))
        d_lord = hexgeo.distance(rp, _pos(lord))
        d_bring = hexgeo.distance(rp, _pos(bring))
        far = [u for u in foes[1:] if hexgeo.distance(rp, _pos(u)) > 1]
        print("  [drive %d] rotbone=%s d(necron)=%d d(lord)=%d d(bringer)=%d ennemis_loin=%d"
              % (it, rp, d_near, d_lord, d_bring, len(far)))
        if d_near == 1 and d_lord == 1 and d_bring > 1 and far:
            return (int(rot["id"]), int(lord["id"]), int(bring["id"]),
                    int(near["id"]), int(far[0]["id"]))
        if d_near != 1:
            if not _step_toward(sid, rid, int(rot["id"]), _pos(near), 1):
                _step_toward(sid, rid, int(near["id"]), rp, 1)
            d = _dv(sid, rid)
            rot = _by_vis(d, "deathRotbone")
            near = next((u for u in (d.get("units") or []) if int(u["id"]) == int(near["id"])), near)
            if hexgeo.distance(_pos(rot), _pos(near)) != 1:
                _step_toward(sid, rid, int(near["id"]), _pos(rot), 1)
        d = _dv(sid, rid)
        rot = _by_vis(d, "deathRotbone")
        if hexgeo.distance(_pos(rot), _pos(_by_vis(d, "deathBlightlord"))) != 1:
            _step_toward(sid, rid, int(_by_vis(d, "deathBlightlord")["id"]), _pos(rot), 1)
        d = _dv(sid, rid)
        rot = _by_vis(d, "deathRotbone")
        if hexgeo.distance(_pos(rot), _pos(_by_vis(d, "deathBlightbringer"))) <= 1:
            _step_toward(sid, rid, int(_by_vis(d, "deathBlightbringer")["id"]), _pos(rot), 4)
        d = _dv(sid, rid)
        rot = _by_vis(d, "deathRotbone")
        rp = _pos(rot)
        others = [u for u in (d.get("units") or [])
                  if u.get("alive") and u.get("owner") != rot.get("owner")
                  and int(u["id"]) != int(near["id"]) and hexgeo.distance(rp, _pos(u)) <= 1]
        for o in others:
            _step_toward(sid, rid, int(o["id"]), rp, 4)
    raise RuntimeError("geometrie discriminante non atteinte")


def _load_offline(sid, rid, adjacency="native_sym"):
    dv = _dv(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indisponible")
    board = Board(bg["tiles"], adjacency=adjacency)
    return load_state(dv, ob, snap, board=board), dv, board, bg


def _run_units(sid, seed, board_id):
    rid, sf = _build(seed, board_id, U_P_UNITS, U_A_UNITS)
    print("\n########## montage UNITES  runner=%d board=%s seed=%s" % (rid, board_id, seed))
    out = []
    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)
        rot, lord, bring, near, far = _drive_units(sid, rid)
        _my_turn(sid, rid, "deathRotbone")
        st, dv, _b, _bg = _load_offline(sid, rid)
        units = {int(u["id"]): u for u in (dv.get("units") or []) if u.get("alive")}
        own = units[rot].get("owner")

        def _label(cid):
            def f(tid):
                u = units.get(tid) or {}
                side = ("CASTER" if tid == cid
                        else ("ALLIE" if u.get("owner") == own else "ENNEMI"))
                dd = hexgeo.distance(_pos(units.get(cid)), _pos(u))
                return "%s %s d=%d" % (side, u.get("visualId"), dd)
            return f

        ids = sorted(units)
        for aid, cid in ((REVITALIZING, rot), (POXWALKERS, bring), (FLAIL, lord)):
            usable = bool(((_nat(sid, rid, cid, aid)[3] or {}).get("abilityState") or {})
                          .get("usable"))
            if not usable:
                print("\n=== ability %d : NON UTILISABLE sur ce montage -> l'oracle court-circuite "
                      "(`ValidRequest`), mesure IMPOSSIBLE" % aid)
                out.append({"ability": aid, "skipped": True})
                continue
            res = _measure(sid, rid, st, dv, aid, cid, ids, _label(cid))
            res["caster_port"] = int(get_invalid_caster_reason(st, cid, _variant(aid, "apres")))
            out.append(res)
        return out
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            sf.unlink(missing_ok=True)
            print("[cleanup] runner %d dispose" % rid)
        except Exception as e:                                       # noqa: BLE001
            print("[cleanup] dispose KO: %s" % e)


# --------------------------------------------------------------------------- montage MoW

def _free_neighbours(bg, dv, pos):
    tiles = {t["id"]: t for t in bg["tiles"]}
    byrc = {(t["col"], t["row"]): t for t in bg["tiles"]}
    occ = {_pos(u) for u in (dv.get("units") or []) if u.get("alive")}
    t0 = byrc.get(pos)
    if t0 is None:
        return []
    return [tiles[n] for n in t0["neighbours"]
            if n in tiles and (tiles[n]["col"], tiles[n]["row"]) not in occ
            and tiles[n].get("walkable", True)]


def _run_mow(sid, seed, board_id):
    """1168 et 1169, portees par la MoW `deathCrawler` (caster HORS PLATEAU -- d'ou le bit
    `AllowNullCasterTile`). Deux phases pour 1168 : AVANT le montage de l'aura (le natif refuse tous
    les ennemis par `TargetMatchesDynamicRule`, l'ecart permissif attendu) puis APRES avoir amene
    `deathTyphus` au contact d'un ennemi (le natif accepte -> l'accord doit devenir PLEIN)."""
    rid, sf = _build(seed, board_id, M_P_UNITS, M_A_UNITS, M_MOW)
    print("\n########## montage MoW  runner=%d board=%s seed=%s" % (rid, board_id, seed))
    out = []
    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)
        dv = _dv(sid, rid)
        mow = next((m for m in (dv.get("mows") or []) if m.get("visualId") == M_MOW), None)
        if mow is None:
            print("[skip] MoW %s absente de decisionView.mows (non deployee)" % M_MOW)
            return out
        cid = int(mow["casterId"])

        # --- monter l'aura Contagion : deathTyphus au contact d'un ennemi -----------------------
        typ = _by_vis(dv, "deathTyphus")
        foe = next((u for u in (dv.get("units") or [])
                    if u.get("alive") and u.get("owner") != (typ or {}).get("owner")), None)
        st0, dv0, _b0, bg0 = _load_offline(sid, rid, adjacency="evenq")
        units0 = {int(u["id"]): u for u in (dv0.get("units") or []) if u.get("alive")}
        own0 = (typ or {}).get("owner")

        def _lab0(tid):
            u = units0.get(tid) or {}
            return "%s %s" % ("ALLIE" if u.get("owner") == own0 else "ENNEMI", u.get("visualId"))

        # PHASE 1 -- AUCUNE aura : la regle dynamique native refuse TOUS les ennemis. Le port, qui ne
        # la porte pas, les accepte : c'est le sur-ensemble PERMISSIF, mesure ici et pas suppose.
        out.append(_measure_set(sid, rid, st0, ENTROPY, cid, sorted(units0), _lab0, "avant-aura"))

        # PHASE 2 -- aura montee (deathTyphus, porteur du trait ContagionsOfNurgle, amene au contact
        # d'un ennemi) : le natif accepte alors CET ennemi, et l'accord doit devenir EXACT.
        if typ is not None and foe is not None:
            free = _free_neighbours(bg0, dv0, _pos(foe))
            if free:
                _my_turn(sid, rid, "deathTyphus")
                _act(sid, rid, {"kind": "move", "unitId": int(typ["id"]),
                                "to": {"col": free[0]["col"], "row": free[0]["row"]}}, 90)
                print("  [aura] deathTyphus amene au contact de %s" % foe.get("visualId"))

        # --- LE CRAN (#287-r10) : l'oracle `abilityReason` est-il PASSANT pour 1169 ? -----------
        # MESURE : `1169 PlagueburstMortar` porte `initialCooldownTurns = 1`, donc au tour 1
        # `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` court-circuite en
        # `GenericBrokenTargetingRule(ValidRequest)` pour TOUTE cible, AVANT la cascade de ciblage
        # -- confronter le port a ce regime compare deux fonctions natives differentes. Les
        # `TOURS_DE_CHAUFFE` ci-dessus SUFFISENT en fait (re-jeu #287-r10), mais compter des tours
        # n'est pas mesurer : ce foyer MESURE `casterReason` et rend une PHRASE s'il ne tombe pas.
        # ⚠ `jouer_adverse=False` est OBLIGATOIRE ici : le montage est GEOMETRIQUE (l'aura Contagion
        # vient d'etre montee a la main), et faire jouer l'IA adverse la detruirait.
        empeche = O.debloquer_oracle(lambda m, b, t=60000: _r(sid, m, b, max(30, int(t) // 1000)),
                                     rid, cid, MORTAR, jouer_adverse=False)
        if empeche:
            print("\n=== ability %d : ORACLE COURT-CIRCUITE, mesure IMPOSSIBLE -- %s"
                  % (MORTAR, empeche))
            out.append({"ability": MORTAR, "skipped": True, "pourquoi": empeche})
            return out

        st, dv, board, bg = _load_offline(sid, rid, adjacency="evenq")
        units = {int(u["id"]): u for u in (dv.get("units") or []) if u.get("alive")}
        own = (_by_vis(dv, "deathTyphus") or {}).get("owner")

        def _lab(tid):
            u = units.get(tid) or {}
            return "%s %s" % ("ALLIE" if u.get("owner") == own else "ENNEMI", u.get("visualId"))

        res = _measure_set(sid, rid, st, ENTROPY, cid, sorted(units), _lab, "apres-aura")
        res["caster_port"] = int(get_invalid_caster_reason(st, cid, _variant(ENTROPY, "apres")))
        out.append(res)

        # --- 1169 : domaine TUILE (`TargetIsTile`) -- il FAUT des tuiles marchables ET non ------
        occ = {_pos(u) for u in units.values()}
        walk, nowalk = [], []
        for t in bg["tiles"]:
            if (t["col"], t["row"]) in occ:
                continue
            (walk if t.get("walkable", True) else nowalk).append(int(t["id"]))
        sample = sorted(walk)[:6] + sorted(nowalk)[:6]
        print("\n  [1169] tuiles interrogees : %d marchables + %d NON marchables (sur %d)"
              % (min(6, len(walk)), min(6, len(nowalk)), len(bg["tiles"])))

        def _lab_tile(tid):
            return "TUILE %s" % ("walk" if tid in walk else "NOWALK")
        if not nowalk:
            print("  [1169] aucune tuile non marchable sur ce board -> `TargetIsTile` ne peut pas "
                  "etre exerce ici (le second couple board/seed doit en fournir)")
        res2 = _measure(sid, rid, st, dv, MORTAR, cid, sample, _lab_tile)
        res2["n_nowalk"] = len(nowalk)
        res2["caster_port"] = int(get_invalid_caster_reason(st, cid, _variant(MORTAR, "apres")))
        out.append(res2)
        return out
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            sf.unlink(missing_ok=True)
            print("[cleanup] runner %d dispose" % rid)
        except Exception as e:                                       # noqa: BLE001
            print("[cleanup] dispose KO: %s" % e)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=U_SEED)
    ap.add_argument("--board", default=U_BOARD)
    ap.add_argument("--mow-seed", default=M_SEED)
    ap.add_argument("--mow-board", default=M_BOARD)
    ap.add_argument("--only", default="", help="units|mow (defaut : les deux)")
    a = ap.parse_args(argv)

    sid = _resolve_session()
    results = []
    if a.only in ("", "units"):
        results += _run_units(sid, a.seed, a.board)
    if a.only in ("", "mow"):
        results += _run_mow(sid, a.mow_seed, a.mow_board)

    ok = True
    print("\n================================ BILAN ================================")
    for res in results:
        if res.get("skipped"):
            print("  ability %d : NON MESUREE -- %s"
                  % (res["ability"], res.get("pourquoi") or "ability non utilisable"))
            ok = False
            continue
        good = _report_set(res) if res.get("oracle") == "abilityTargets" else _report(res)
        ok = ok and good
    print("\n[VERDICT] %s" % ("PASS" if ok else "FAIL"))
    print("[RAW] " + json.dumps(results))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
