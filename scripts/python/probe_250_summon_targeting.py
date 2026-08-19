#!/usr/bin/env python
"""probe_250_summon_targeting -- ARMEMENT des gates de cible des CINQ abilities du module `summon`
(`engine/runner/abilities/loki/summon.py`) : 1007 ScarabHive, 1045 GetEmRuntz, 1047 ScarabSummon,
1096 MasterOfTheTutelaries, 1166 AberrantHypermorph.

CE QUE CE PROBE MESURE
----------------------
Les cinq entraient dans `ABILITY_CLASSES` SANS `TARGETING_OPTIONS`. `get_invalid_target_reason`
commence par `options = getattr(ability, "TARGETING_OPTIONS", None)` et rend 0 immediatement quand
c'est `None` : AUCUN gate. Degradation PERMISSIVE -- ni erreur ni crash, invisible en self-play.

LES TROIS FORMES DE CTOR SONT REPRESENTEES DANS CE SEUL MODULE, et rien ne se generalise :

  id    ctor                                                        masque      portee
  ----  ----------------------------------------------------------  ----------  ---------------
  1007  FLAGS DIRECTS  ..ctor(&opts,0,&TR30,1,0x4020,0,0,0)          0x4020      RANGE_ADJACENT
  1045  PRESET COPIE   TargetingOptions statics+0x280 (aucun ctor)   0x8004      RANGE_SELF
  1047  FLAGS DIRECTS  ..ctor(&opts,1,&TR60,1,0x208000,0,0,0)        0x208000    RANGE_SELF
  1096  FLAGS DIRECTS  ..ctor(&opts,0,&TR30,1,0x1040,0,0,0)          0x1040      RANGE_ADJACENT
  1166  FLAGS DIRECTS  ..ctor(&opts,0,&TR30,1,0x1040,0,0,0)          0x1040      RANGE_ADJACENT

(`TR30` / `TR60` = les `TargetingRange` STATIQUES +0x30 / +0x60 ecrits par
`IdunBattle.Core.Services.TargetingRange$$.cctor` = `RANGE_ADJACENT` / `RANGE_SELF`. 1007 et 1047
sont dans le MEME fichier, de la MEME forme, et n'ont NI le meme litteral NI le meme
`TargetingRange` -- generaliser depuis la voisine aurait produit deux masques faux.)

ORACLE = le LIVE : `abilityReason(casterId, abilityType, targetId)` rend le `TargetingRule` NATIF
(il appelle `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`). Le probe rejoue le
gate OFFLINE sur le MEME etat fige, en CINQ versions :
  * APRES         = l'ability du registre (masque pose par cette tranche) ;
  * AVANT         = la MEME classe avec `TARGETING_OPTIONS = None` -- l'etat de `master` ;
  * sansRules     = masque a `rules = 0` (les autres champs intacts) ;
  * sansRange     = `range = None` (le volet portee desarme) ;
  * flipForceMelee= `force_melee_target` bascule `RangedBool.False` -> `RangedBool.True`.
Les trois derniers sont les CONTREFACTUELS par champ : un champ dont la neutralisation ne change
AUCUN verdict n'est pas valide par cette mesure, et le bilan le DIT au lieu de le taire.

GEOMETRIE DRIVEE, jamais subie : on rapproche le caster au contact d'un ennemi (et, pour 1007, un
allie au contact du caster) et on garde au moins un ennemi hors contact -- sans quoi les lignes
`TargetIsEnemy` / `TargetIsInRange` n'existeraient pas dans l'etat mesure.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_250_summon_targeting.py --ability 1007
    python probe_250_summon_targeting.py --ability all --seed 31337 --board C3_26

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
                                               is_invalid_target)
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

SCARAB_HIVE = 1007
GETEMRUNTZ = 1045
SCARAB_SUMMON = 1047
MASTER_TUTELARIES = 1096
ABERRANT = 1166
ALL_IDS = (SCARAB_HIVE, GETEMRUNTZ, SCARAB_SUMMON, MASTER_TUTELARIES, ABERRANT)

# --- montage par ability -------------------------------------------------------------------------
# `caster` = le visualId du PORTEUR, `via` = l'ability a caster d'abord quand le porteur est un
# SUMMON (1047 : le necroSmnSwarm n'entre en bataille que spawne par ScarabHive).
SETUP = {
    SCARAB_HIVE:       {"caster": "necroSpyder", "ally": "necroOverlord",
                        "p": "necroSpyder,necroOverlord", "a": "necroWarden,necroWarden,necroWarden",
                        "domain": "unit", "via": None},
    GETEMRUNTZ:        {"caster": "orksRuntherd", "ally": "orksNob",
                        "p": "orksRuntherd,orksNob", "a": "necroWarden,necroWarden,necroWarden",
                        "domain": "unit", "via": None},
    SCARAB_SUMMON:     {"caster": "necroSmnSwarm", "ally": "necroOverlord",
                        "p": "necroSpyder,necroOverlord", "a": "necroWarden,necroWarden,necroWarden",
                        "domain": "unit", "via": (SCARAB_HIVE, "necroSpyder")},
    MASTER_TUTELARIES: {"caster": "thousInfernalMaster", "ally": "thousSorcerer",
                        "p": "thousInfernalMaster,thousSorcerer",
                        "a": "necroWarden,necroWarden,necroWarden",
                        "domain": "tile", "via": None},
    ABERRANT:          {"caster": "genesBiophagus", "ally": "genesPrimus",
                        "p": "genesBiophagus,genesPrimus",
                        "a": "necroWarden,necroWarden,necroWarden",
                        "domain": "tile", "via": None},
}

BOARD = "MC1_67"
SEED = "777"
TOURS_DE_CHAUFFE = 6               # purge les `initialCooldownTurns` (sinon `ValidRequest` partout)
MAX_TILES = 6                     # tuiles echantillonnees par regime (probe TILE-target)
_seq = itertools.count()


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _build(sid, seed: str, board: str, p_units: str, a_units: str):
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, qui est versionne).
    ATTEND qu'un slot se libere si MAX_RUNNERS est sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe247-%d-%d.json" % (os.getpid(), next(_seq)))
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
    main. On ne COMPTE pas les `endturn` : quand toutes les unites d'un camp ont agi le moteur
    bascule deja tout seul, et un `endturn` de plus decalerait la parite."""
    for _ in range(maxit):
        t = _movable(sid, rid, unit_id)
        if t:
            return t
        _act(sid, rid, {"kind": "endturn"}, 60)
    return []


def _step_toward(sid, rid, unit_id, goal_pos, want: int):
    tiles = _wait_movable(sid, rid, unit_id)
    if not tiles:
        return False
    best = min(tiles, key=lambda t: (abs(hexgeo.distance(t, goal_pos) - want), t))
    _act(sid, rid, {"kind": "move", "unitId": unit_id,
                    "to": {"col": best[0], "row": best[1]}}, 90)
    return True


def _turn_of(sid, rid, vis, maxit=8):
    """Rend la main au camp de l'unite `vis` (runner `--no-ai` : rien ne bouge tout seul)."""
    for _ in range(maxit):
        d = _dv(sid, rid)
        me = _by_vis(d, vis)
        if me is not None and me.get("ctrl"):
            return d
        _act(sid, rid, {"kind": "endturn"}, 60)
    return _dv(sid, rid)


# --------------------------------------------------------------------------- montage geometrique

def _drive(sid, rid, caster_vis, ally_vis, rounds=10):
    """Monte la geometrie DISCRIMINANTE : caster AU CONTACT d'un ennemi, allie AU CONTACT du caster,
    et au moins un ennemi HORS contact.

    `applyAction` ne verifie pas la propriete du `unitId` mais `aiMovableTiles` est calcule pour le
    JOUEUR COURANT -> on pilote MES unites pendant mon tour et les ENNEMIES pendant le leur."""
    d = _dv(sid, rid)
    caster0 = _by_vis(d, caster_vis)
    if caster0 is None:
        raise RuntimeError("caster %s absent du plateau" % caster_vis)
    foes0 = sorted((u for u in (d.get("units") or [])
                    if u.get("alive") and u.get("owner") != caster0.get("owner")),
                   key=lambda u: u["id"])
    if len(foes0) < 2:
        raise RuntimeError("il faut >= 2 ennemis pour separer contact / hors-contact")
    near_id = int(foes0[0]["id"])
    for it in range(rounds):
        d = _dv(sid, rid)
        units = {int(u["id"]): u for u in (d.get("units") or []) if u.get("alive")}
        caster = _by_vis(d, caster_vis)
        ally = _by_vis(d, ally_vis)
        if caster is None or near_id not in units:
            raise RuntimeError("montage impossible : caster=%s near=%s"
                               % (caster is not None, near_id in units))
        cp = _pos(caster)
        own = caster.get("owner")
        d_near = hexgeo.distance(cp, _pos(units[near_id]))
        d_ally = hexgeo.distance(cp, _pos(ally)) if ally is not None else 99
        far = [i for i, u in units.items()
               if u.get("owner") != own and hexgeo.distance(cp, _pos(u)) > 1]
        print("  [drive %d] caster=%s d(near)=%d d(ally)=%d hors_contact=%s"
              % (it, cp, d_near, d_ally, far))
        if d_near == 1 and (ally is None or d_ally == 1) and far:
            return int(caster["id"]), (int(ally["id"]) if ally is not None else None), \
                near_id, int(far[0])
        if d_near != 1:
            _step_toward(sid, rid, int(caster["id"]), _pos(units[near_id]), 1)
            d = _dv(sid, rid)
            caster = _by_vis(d, caster_vis)
            units = {int(u["id"]): u for u in (d.get("units") or []) if u.get("alive")}
            if hexgeo.distance(_pos(caster), _pos(units[near_id])) != 1:
                _step_toward(sid, rid, near_id, _pos(caster), 1)
        d = _dv(sid, rid)
        caster = _by_vis(d, caster_vis)
        ally = _by_vis(d, ally_vis)
        if ally is not None and hexgeo.distance(_pos(caster), _pos(ally)) != 1:
            _step_toward(sid, rid, int(ally["id"]), _pos(caster), 1)
        d = _dv(sid, rid)
        caster = _by_vis(d, caster_vis)
        units = {int(u["id"]): u for u in (d.get("units") or []) if u.get("alive")}
        own = caster.get("owner")
        others = [i for i, u in units.items()
                  if u.get("owner") != own and i != near_id
                  and hexgeo.distance(_pos(caster), _pos(u)) <= 1]
        if others and len(units) > 3:
            _step_toward(sid, rid, others[0], _pos(caster), 4)
    raise RuntimeError("geometrie discriminante non atteinte apres %d rounds" % rounds)


def _free_adjacent(board, dv, pos):
    """Tuiles LIBRES reellement adjacentes a `pos` au sens natif (`MovementUtil$$AreTilesAdjacent` :
    voisinage du graphe **et** `|dElevation| < 2`) -- c'est le predicat que la branche `onlyAdjacent`
    du volet portee applique, et il n'est PAS « distance hex == 1 »."""
    occupied = {_pos(u) for u in (dv.get("units") or []) if u.get("alive")}
    tid = board.id_at(pos[0], pos[1])
    if tid is None:
        return []
    elev = board.elevation(tid)
    out = []
    for nid in board.neighbours(tid):
        if abs(elev - board.elevation(nid)) >= 2 or not board.walkable(nid):
            continue
        if board.coord(nid) in occupied:
            continue
        out.append(board.coord(nid))
    return out


def _ensure_free_adjacent(sid, rid, caster_vis, tries=4):
    """DEPLACE le caster jusqu'a ce qu'il ait au moins une tuile LIBRE ADJACENTE (au sens natif).

    Sans ca, une ability TILE-TARGET `RANGE_ADJACENT` n'a AUCUNE cible acceptable dans l'etat fige :
    toutes les lignes rendent un refus, et la garde « au moins une cible acceptee » -- celle qui
    prouve que l'ability n'est pas court-circuitee -- ne peut pas tomber. MESURE : sur `C3_26`/31337
    le caster finissait sur une tuile dont les 6 voisines etaient soit occupees soit separees de 2
    niveaux d'elevation (`tile-adjLIBRE (5,5)` a d=1 refusee `TargetIsInRange` par le natif ET par le
    port -- accord parfait, mais montage sterile). On DEPLACE, on ne subit pas la geometrie."""
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    board = Board(bg["tiles"], adjacency="native_sym")
    for _ in range(tries):
        dv = _dv(sid, rid)
        me = _by_vis(dv, caster_vis)
        if me is None:
            return False
        if _free_adjacent(board, dv, _pos(me)):
            return True
        tiles = _wait_movable(sid, rid, int(me["id"]))
        dv = _dv(sid, rid)
        cand = [t for t in tiles if _free_adjacent(board, dv, t)]
        if not cand:
            return False
        # la plus proche de la position courante : on garde le contact avec l'ennemi si possible
        best = min(cand, key=lambda t: (hexgeo.distance(t, _pos(me)), t))
        _act(sid, rid, {"kind": "move", "unitId": int(me["id"]),
                        "to": {"col": best[0], "row": best[1]}}, 90)
        print("  [free-adj] caster deplace en %s (tuiles libres adjacentes : %d)"
              % (best, len(_free_adjacent(board, _dv(sid, rid), best))))
    return bool(_free_adjacent(board, _dv(sid, rid), _pos(_by_vis(_dv(sid, rid), caster_vis))))


def _spawn_tiles(board, dv, pos, owner):
    """Tuiles de spawn de `IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$GetSpawnTileSelector`,
    recalculees ICI depuis la GEOMETRIE LIVE (boardGraph + decisionView) et non depuis le port -- ce
    serait circulaire de placer l'unite avec le predicat qu'on cherche a valider. Definition native :
    tuile LIBRE (walkable, inoccupee) adjacente au caster **ET** adjacente a un ennemi vivant."""
    free = _free_adjacent(board, dv, pos)
    foes = [_pos(u) for u in (dv.get("units") or [])
            if u.get("alive") and u.get("owner") != owner]
    out = []
    for t in free:
        tid = board.id_at(t[0], t[1])
        elev = board.elevation(tid)
        neigh = {board.coord(n) for n in board.neighbours(tid)
                 if abs(elev - board.elevation(n)) < 2}
        if any(f in neigh for f in foes):
            out.append(t)
    return out


def _ensure_spawn_tile(sid, rid, caster_vis, tries=4):
    """DEPLACE le Runtherd jusqu'a ce qu'il ait au moins UNE tuile de spawn valide -- sinon
    `GetDynamicInvalidCasterReason` refuse TOUT (mesure : `C3_26`/31337, natif `0x2` sur les 5
    lignes), aucune cible n'est acceptee et la garde anti-court-circuit ne peut pas tomber."""
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    board = Board(bg["tiles"], adjacency="native_sym")
    for _ in range(tries):
        dv = _dv(sid, rid)
        me = _by_vis(dv, caster_vis)
        if me is None:
            return False, board
        if _spawn_tiles(board, dv, _pos(me), me.get("owner")):
            return True, board
        tiles = _wait_movable(sid, rid, int(me["id"]))
        dv = _dv(sid, rid)
        cand = [t for t in tiles if _spawn_tiles(board, dv, t, me.get("owner"))]
        if not cand:
            return False, board
        best = min(cand, key=lambda t: (hexgeo.distance(t, _pos(me)), t))
        _act(sid, rid, {"kind": "move", "unitId": int(me["id"]),
                        "to": {"col": best[0], "row": best[1]}}, 90)
        print("  [spawn-tile] caster deplace en %s" % (best,))
    return False, board


def _cast_via(sid, rid, summoner_vis, ability_id, target_id):
    """Cast prealable qui AMENE le porteur SUMMON en bataille (1047 : le necroSmnSwarm n'existe que
    spawne par `ScarabHive`). Rend la liste des ids presents APRES le cast."""
    _turn_of(sid, rid, summoner_vis)
    d = _dv(sid, rid)
    s = _by_vis(d, summoner_vis)
    res = _act(sid, rid, {"kind": "ability", "casterId": int(s["id"]),
                          "abilityType": int(ability_id), "targetId": int(target_id)}, 120)
    print("  [via] %s cast %d sur u%s -> mutated=%s"
          % (summoner_vis, ability_id, target_id, (res or {}).get("mutated")))
    d = _dv(sid, rid)
    print("  [via] unites presentes : %s"
          % sorted({u.get("visualId") for u in (d.get("units") or []) if u.get("alive")}))
    return d


# --------------------------------------------------------------------------- variantes du port

def _ability(aid: int, variant: str):
    klass = ABILITY_CLASSES[aid]
    base = klass.TARGETING_OPTIONS
    if variant == "apres":
        return klass()
    if variant == "avant":
        class _NoMask(klass):            # meme classe, masque retire -> AUCUN gate (etat `master`)
            __slots__ = ()
            TARGETING_OPTIONS = None
        return _NoMask()
    if variant == "sansRules":
        class _NoRules(klass):
            __slots__ = ()
            TARGETING_OPTIONS = _replace(base, rules=0)
        return _NoRules()
    if variant == "sansRange":
        class _NoRange(klass):
            __slots__ = ()
            TARGETING_OPTIONS = _replace(base, range=None)
        return _NoRange()

    class _FlipMelee(klass):             # RangedBool.False -> RangedBool.True (clamp melee arme)
        __slots__ = ()
        TARGETING_OPTIONS = _replace(base, force_melee_target=RANGED_BOOL_TRUE)
    return _FlipMelee()


VARIANTS = ("apres", "avant", "sansRules", "sansRange", "flipForceMelee")


# --------------------------------------------------------------------------- mesure

def _native(sid, rid, cid, aid, tid=None):
    body = {"runnerId": rid, "casterId": cid, "abilityType": int(aid)}
    if tid is not None:
        body["targetId"] = int(tid)
    nat = _r(sid, "abilityReason", body, 60)
    tr = (nat or {}).get("targetReason") or {}
    cr = (nat or {}).get("casterReason") or {}

    def _v(blob):
        h = blob.get("hex")
        if isinstance(h, str):
            return int(h, 16)
        return 0 if blob.get("ruleClass") == "NoBrokenTargetingRule" else None
    return _v(tr), (tr.get("reasons") or []), tr.get("ruleClass"), _v(cr), nat


def _rows_units(sid, rid, cid, aid, dv, caster_u):
    rows = []
    for u in (dv.get("units") or []):
        if not u.get("alive"):
            continue
        tid = int(u["id"])
        side = "CASTER" if tid == cid else (
            "ALLIE" if u.get("owner") == caster_u.get("owner") else "ENNEMI")
        natv, reasons, klass, crv, _ = _native(sid, rid, cid, aid, tid)
        rows.append({"label": "%s %s" % (side, u.get("visualId")), "target": tid,
                     "dist": hexgeo.distance(_pos(caster_u), _pos(u)), "kind": "unit",
                     "nat": natv, "reasons": reasons, "class": klass, "caster": crv})
    return rows


def _rows_tiles(sid, rid, cid, aid, dv, caster_u, bg, board, limit=MAX_TILES):
    """Pour une ability TILE-TARGET, on exerce les regimes que le masque 0x1040 distingue :
    ADJACENTE-LIBRE (attendu 0x0), ADJACENTE-OCCUPEE (0x1000 `TargetTileIsFree`), LOIN (0x8000000
    `TargetIsInRange`), NON MARCHABLE (le natif rend le LITTERAL 0x1). Les tuiles sont choisies dans
    l'etat FIGE, jamais hardcodees."""
    cpos = _pos(caster_u)
    occupied = {(_pos(u)) for u in (dv.get("units") or []) if u.get("alive")}
    buckets = {"adjLIBRE": [], "adjOCCUPEE": [], "d2": [], "LOIN": [], "NOWALK": []}
    for t in (bg.get("tiles") or []):
        c, r = t.get("col"), t.get("row")
        if c is None:
            continue
        d = hexgeo.distance(cpos, (c, r))
        if not t.get("walkable"):
            buckets["NOWALK"].append(t)
        elif d == 1 and (c, r) in occupied:
            buckets["adjOCCUPEE"].append(t)
        elif d == 1:
            buckets["adjLIBRE"].append(t)
        elif d == 2:
            buckets["d2"].append(t)
        elif d > 2:
            buckets["LOIN"].append(t)
    rows = []
    for name, lst in buckets.items():
        step = max(1, len(lst) // limit)
        for t in lst[::step][:limit]:
            tid = int(t["id"])
            natv, reasons, klass, crv, _ = _native(sid, rid, cid, aid, tid)
            rows.append({"label": "tile-%s (%d,%d)" % (name, t["col"], t["row"]), "target": tid,
                         "dist": hexgeo.distance(cpos, (t["col"], t["row"])), "kind": "tile",
                         "nat": natv, "reasons": reasons, "class": klass, "caster": crv})
    return rows


def _mesure_caster_dyn(sid, rid, aid, caster_vis):
    """2e ETAT, propre a 1045 : on ELOIGNE le Runtherd de tous les ennemis pour que
    `GetEmRuntzAbility$$GetSpawnTileSelector` rende une liste VIDE, et on confronte le volet CASTER
    (`CasterMatchesDynamicRule`, bit 2) natif au port. C'est LA mesure qui valide ce port : dans
    l'etat principal la regle ne mord pas (par construction du montage), donc elle n'y prouve rien.

    Rend `(natif, port, d_min_ennemi)` ou `None` si le deplacement n'a pas suffi."""
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    board = Board(bg["tiles"], adjacency="native_sym")
    for _ in range(3):
        _turn_of(sid, rid, caster_vis)
        dv = _dv(sid, rid)
        me = _by_vis(dv, caster_vis)
        if me is None:
            return None
        own = me.get("owner")
        foes = [u for u in (dv.get("units") or []) if u.get("alive") and u.get("owner") != own]
        if not _spawn_tiles(board, dv, _pos(me), own):
            break
        far = max(foes, key=lambda u: hexgeo.distance(_pos(me), _pos(u)))
        _step_toward(sid, rid, int(me["id"]), _pos(far), 9)
    _turn_of(sid, rid, caster_vis)
    dv = _dv(sid, rid)
    me = _by_vis(dv, caster_vis)
    if me is None or _spawn_tiles(board, dv, _pos(me), me.get("owner")):
        return None
    cid = int(me["id"])
    _n, _r2, _k, crv, _raw = _native(sid, rid, cid, aid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    st = load_state(dv, ob, snap, board=board)
    port = int(get_invalid_caster_reason(st, cid, _ability(aid, "apres")))
    foes = [u for u in (dv.get("units") or [])
            if u.get("alive") and u.get("owner") != me.get("owner")]
    dmin = min(hexgeo.distance(_pos(me), _pos(u)) for u in foes) if foes else None
    return crv, port, dmin


def run_one(sid, aid: int, seed: str, board_name: str) -> dict:
    cfg = SETUP[aid]
    rid, state_file = _build(sid, seed, board_name, cfg["p"], cfg["a"])
    print("[build] ability=%d runner=%d board=%s seed=%s" % (aid, rid, board_name, seed))
    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)

        via = cfg["via"]
        drive_vis = via[1] if via else cfg["caster"]
        cid0, ally_id, near_id, far_id = _drive(sid, rid, drive_vis, cfg["ally"])
        if via:
            # le porteur est un SUMMON : on le fait naitre en castant l'ability du summoner sur
            # l'ennemi au contact (ScarabHive pose 2 necroSmnSwarm autour de la cible).
            _cast_via(sid, rid, via[1], via[0], near_id)
        if cfg["domain"] == "tile":
            _turn_of(sid, rid, cfg["caster"])
            _ensure_free_adjacent(sid, rid, cfg["caster"])
        if aid == GETEMRUNTZ:
            _turn_of(sid, rid, cfg["caster"])
            _ensure_spawn_tile(sid, rid, cfg["caster"])
        dv = _turn_of(sid, rid, cfg["caster"])

        dv = _dv(sid, rid)
        caster_u = _by_vis(dv, cfg["caster"])
        if caster_u is None:
            raise RuntimeError("porteur %s absent apres montage" % cfg["caster"])
        cid = int(caster_u["id"])
        _n, _rr, _k, _cr, nat0 = _native(sid, rid, cid, aid)
        usable = bool(((nat0 or {}).get("abilityState") or {}).get("usable"))
        print("[state] caster=u%d(%s) pos=%s ctrl=%s usable=%s"
              % (cid, caster_u.get("visualId"), _pos(caster_u), caster_u.get("ctrl"), usable))
        if not usable:
            raise RuntimeError("ability %d non utilisable -> l'oracle court-circuite "
                               "(`CanCurrentlyBeUsed`), aucune mesure possible" % aid)

        ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            raise RuntimeError("boardGraph indisponible")
        brd = Board(bg["tiles"], adjacency="native_sym")
        st = load_state(dv, ob, snap, board=brd)

        rows = _rows_units(sid, rid, cid, aid, dv, caster_u)
        if cfg["domain"] == "tile":
            rows += _rows_tiles(sid, rid, cid, aid, dv, caster_u, bg, brd)
        # Le port se lit par `is_invalid_target` = l'overload 5 arguments de
        # `TargetingQuery$$GetInvalidTargetReason` : volet CASTER d'abord, volet CIBLE ensuite. C'est
        # le MEME point d'entree que l'oracle -- le natif rend la raison CASTER TELLE QUELLE dans
        # `targetReason` quand elle est rompue (mesure #250 : GetEmRuntz sans tuile de spawn rend
        # `0x2` sur les 5 lignes). Comparer avec `get_invalid_target_reason` seul raterait ce cas.
        for row in rows:
            for v in VARIANTS:
                row[v] = int(is_invalid_target(st, cid, row["target"], _ability(aid, v)))

        port_caster = int(get_invalid_caster_reason(st, cid, _ability(aid, "apres")))
        opts = ABILITY_CLASSES[aid].TARGETING_OPTIONS
        print("\n[reasons] ability=%d caster=u%d masque=0x%x self_cast=%s range=%s"
              % (aid, cid, int(opts.rules), opts.self_cast, opts.range))
        print("  %-30s %-6s %-3s %-11s %-26s %-11s %-11s %-11s %-11s %-11s %s"
              % ("cible", "id", "d", "natif", "regle", "APRES", "AVANT", "sansRules",
                 "sansRange", "flipFM", "accord"))
        n_agree = n_gain = 0
        cf = {"sansRules": 0, "sansRange": 0, "flipForceMelee": 0}
        for r in rows:
            agree = (r["nat"] == r["apres"])
            n_agree += 1 if agree else 0
            gain = (r["nat"] not in (None, 0)) and r["avant"] == 0
            n_gain += 1 if gain else 0
            for k in cf:
                if r["nat"] not in (None, 0) and r[k] != r["apres"]:
                    cf[k] += 1
            print("  %-30s %-6d %-3s %-11s %-26s %-11s %-11s %-11s %-11s %-11s %s%s"
                  % (r["label"], r["target"], r["dist"],
                     "-" if r["nat"] is None else hex(r["nat"]),
                     ",".join(r["reasons"]) or r["class"] or "-",
                     hex(r["apres"]), hex(r["avant"]), hex(r["sansRules"]),
                     hex(r["sansRange"]), hex(r["flipForceMelee"]),
                     "OK" if agree else "MISMATCH", "  <-GAIN" if gain else ""))

        caster_nat = sorted({r["caster"] for r in rows if r["caster"] is not None})
        has_acc = any(r["nat"] == 0 for r in rows)
        dyn = _mesure_caster_dyn(sid, rid, aid, cfg["caster"]) if aid == GETEMRUNTZ else None
        if aid == GETEMRUNTZ:
            print("[volet CASTER dynamique] 2e etat (Runtherd eloigne, aucune tuile de spawn) : %s"
                  % ("natif=%s port=%s d_min_ennemi=%s -> %s"
                     % (hex(dyn[0]), hex(dyn[1]), dyn[2],
                        "OK" if dyn[0] == dyn[1] else "MISMATCH")
                     if dyn else "NON ATTEINT (le caster garde une tuile de spawn) -- "
                                 "`CasterMatchesDynamicRule` non exerce dans ce run"))
        print("\n[bilan %d] accord natif/APRES : %d/%d ; lignes ou le natif REFUSE et AVANT rendait 0 "
              "(casts illegaux que master acceptait) : %d" % (aid, n_agree, len(rows), n_gain))
        # GARDE ANTI-COURT-CIRCUIT. Le risque nomme est `AttackQuery$$GetInvalidTargetReason`, qui
        # rend `0x1 ValidRequest` SANS jamais evaluer la cascade quand l'ability n'est pas utilisable
        # (`CanCurrentlyBeUsed`) : les refus ne prouveraient alors rien. Deux lectures INDEPENDANTES
        # l'excluent -- `abilityState.usable` (deja verifie plus haut, sinon on leve) et l'absence de
        # `0x1` parmi les codes rendus. `has_acc` (une cible acceptee) est la 3e, la plus forte, mais
        # elle n'est pas toujours ATTEIGNABLE : un etat ou le volet CASTER refuse TOUT (GetEmRuntz
        # sans tuile de spawn) est un etat legitime et discriminant, et l'exiger reviendrait a jeter
        # la mesure la plus interessante du lot.
        amb = [r["label"] for r in rows if r["nat"] == 1]
        print("[garde] au moins une cible ACCEPTEE (0x0) : %s ; lignes au code ambigu 0x1 : %s"
              % ("OUI" if has_acc else "NON", amb or "aucune"))
        print("[volet CASTER] casterReason natif = %s ; port = %s"
              % ([hex(x) for x in caster_nat], hex(port_caster)))
        print("[contrefactuels] lignes dont le verdict CHANGE quand on neutralise le champ : "
              "rules=%d  range=%d  forceMeleeTarget(flip)=%d"
              % (cf["sansRules"], cf["sansRange"], cf["flipForceMelee"]))
        for k, v in cf.items():
            if v == 0:
                print("  [note] `%s` : aucune ligne ne change -> ce champ n'est PAS valide par cette "
                      "mesure (il est pose parce qu'il est LU au decompile, pas parce qu'il mord)"
                      % k)
        ok = (n_agree == len(rows) and (has_acc or not amb) and n_gain > 0
              and all(c == port_caster for c in caster_nat)
              and (dyn is None or dyn[0] == dyn[1]))
        print("[VERDICT %d] %s" % (aid, "PASS" if ok else "FAIL"))
        return {"ability": aid, "ok": ok, "rows": rows, "agree": n_agree, "total": len(rows),
                "gain": n_gain, "cf": cf, "caster_nat": caster_nat, "port_caster": port_caster,
                "dyn": dyn, "has_acc": has_acc, "ambigus": amb,
                "board": board_name, "seed": seed}
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            state_file.unlink(missing_ok=True)
            print("[cleanup] runner dispose")
        except Exception as e:                                       # noqa: BLE001
            print("[cleanup] dispose KO: %s" % e)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ability", default="all")
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    a = ap.parse_args(argv)
    ids = ALL_IDS if a.ability == "all" else tuple(int(x) for x in a.ability.split(","))

    sid = _resolve_session()
    out = []
    for aid in ids:
        try:
            out.append(run_one(sid, aid, a.seed, a.board))
        except Exception as e:                                       # noqa: BLE001
            print("[ERREUR %d] %s" % (aid, e))
            out.append({"ability": aid, "ok": False, "error": str(e)})
    print("\n[RESUME] " + " ; ".join(
        "%d=%s" % (o["ability"], "PASS" if o.get("ok") else "FAIL") for o in out))
    print("[RAW] " + json.dumps([{k: v for k, v in o.items() if k != "rows"} for o in out]))
    return 0 if all(o.get("ok") for o in out) else 1


if __name__ == "__main__":
    sys.exit(main())
