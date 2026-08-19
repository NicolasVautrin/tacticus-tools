#!/usr/bin/env python
"""probe_243_splash_range_clamp -- CONFRONTATION LIVE des trois masques `splash` poses sur RE seule
par #248 : `Stikkbomb` (1051), `Fragstorm` (1078), `PlasmaGrenade` (1098).

CE QUE CE PROBE MESURE, ET POURQUOI IL FALLAIT UN AUTRE MONTAGE QUE #247/#248
-----------------------------------------------------------------------------
Les trois portent le MEME `rules` (`0x2000000 | 0x4002` = `0x2004002`) et le MEME
`TargetingRange` (`RANGE_FROM_CONFIG` -> `constants.range` = 2). Ce qui les SEPARE est le seul
champ `<preset>+0x20` `forceMeleeTarget` :

  1051 / 1098  preset `TargetingOptions statics+0x140` -> `forceMeleeTarget = 0 = RangedBool.True`
               -> `IdunBattle.Core.Services.TargetingQuery$$GetRange` ARME son clamp :
                  `if (RangedBoolExtensions.IsTrue(options.ForceMeleeTarget, caster)
                       && attackQuery.ShouldApplyRangedInMelee(caster, casterTiles, true))
                     { v = Math.Min(1, v); onlyAdjacent = true; }`
  1078         preset `statics+0x180` -> `forceMeleeTarget = 1 = RangedBool.False` -> clamp DESARME.

=> le DISCRIMINANT est un ennemi non-Steppable AU CONTACT du caster + une cible a d = 2 : le natif
doit REFUSER (`TargetIsInRange`) pour 1051/1098 et ACCEPTER pour 1078. Une mesure qui n'exerce pas
ce montage ne valide pas le champ qui distingue les trois -- elle ne valide que `rules`, identique.

DEUX MONTAGES PAR ABILITY, sur la MEME bataille :
  * LIBRE : aucun ennemi a d = 1 du caster -> le clamp ne mord pour PERSONNE ; on encadre le seuil
    de portee des DEUX cotes (d = 2 accepte, d = 3 refuse `TargetIsInRange`) pour les TROIS ;
  * MELEE : un ennemi amene a d = 1 -> 1051/1098 basculent (la cible d = 2 devient refusee),
    1078 ne bouge PAS. C'est la ligne qui separe les presets.

CONFRONTABILITE DES PORTEURS (gate HERO/MoW/SUMMON, jamais npc)
---------------------------------------------------------------
  1051 `orksOrkBoys`       (summon d'`orksWarboss` via `Waaagh` 1058)
  1078 `templSmnAggressor` (summon -- seul poseur : le PowerUp `PowerUp_SummonSpawn_templSmnAggressor`,
                            castable par AUCUNE unite du pool)
  1098 `eldarSmnGuardian`  (summon -- AUCUN summoner au gameconfig)
Les trois sont des SUMMONS : hors `--list-pool` par construction. La voie « spawner le summoner » ne
couvre que 1051 et s'est revelee impraticable (#248 : `Waaagh` rend 0 cible legale apres montage du
spectre). On prend donc la voie DEJA MESUREE ET DOCUMENTEE de `case-245` : catalogue injecte
(`catalog_inject.augment` -> `Units` ET `Abilities`) + `initAndStart(playerUnits=[...])`, avec les
DEUX MEMES amenagements d'entree, et pas un de plus :

  * `Health` 0 -> 5000 : l'entree d'un summon porte 0 (ses PV viennent des `summonHp` du SUMMONER au
    spawn natif) ; spawne a la main il naitrait a 1 PV. Aucune regle du filtre statique ne lit les PV.
  * le trait `Summon` est RETIRE, parce qu'il rend l'unite AUTOMATIQUE. CAUSE ETABLIE par case-250
    (decompile + mesure) : `IdunBattle.Entities.UnitExtensions$$IsAutomatic` = `HasTrait(2 Summon) ||
    HasTrait(13 Object)`, et `IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute` joue
    lui-meme toute unite automatique du camp. Elle consomme sa charge d'active,
    `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` incremente `AmountOfTimesUsed`
    et re-evalue `IdunBattle.Entities.Abilities.AActiveAbility$$CanStillBeUsed`, qui rend alors
    `amountOfTimesAlreadyUsed == 0` = false. `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason`
    court-circuite ensuite a `0x1` SANS evaluer la cascade -- rien de mesurable. Ce n'est donc PAS
    un gate leve : c'est l'unite rendue CONTROLABLE, donc interrogeable avant qu'elle ait caste.

Le retrait du trait ne peut pas deplacer un verdict de la cascade POUR CES MASQUES, et ca se lit au
decompile : les seules regles du filtre statique qui consultent un trait portent sur la CIBLE
(`TargetIsSummon` 0x2000, `TargetIsHero` bit 50, `TargetIsNotAnObject` bit 33) et aucune n'est dans
`0x2004002` ; le trait du CASTER n'entre que par `RangedBoolExtensions$$IsTrue(IfRangedCaster /
IfNotRangedCaster)`, or ces presets posent `forceMeleeTarget` a une CONSTANTE (`RangedBool.True` ou
`.False`) et `onlyAdjacent` vient de `RANGE_FROM_CONFIG` (`RangedBool.False`, constante) -- aucun des
deux ne lit un trait. `ShouldApplyRangedInMelee` lit `HasTrait(0x1b Steppable)` sur les VOISINS de la
cible, pas sur le caster, et son gate `HasTrait(0xb Ranged)` est court-circuite par `ignoreTrait = 1`
au call-site de `GetRange`.

ORACLE = le LIVE : `abilityReason(casterId, abilityType, targetId)` rend le `TargetingRule` NATIF. Le
probe rejoue le gate OFFLINE sur le MEME etat fige, en CINQ versions :
  APRES / AVANT (`TARGETING_OPTIONS = None`, l'etat d'avant #248) / sansRules / sansRange / fmtFlip.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_243_splash_range_clamp.py
    python probe_243_splash_range_clamp.py --seed 31337 --board C4_09

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import copy
import itertools
import json
import os
import sys
from dataclasses import replace as _replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_inject as CI                                          # noqa: E402
import hexgeo                                                        # noqa: E402
import rl_duel as RD                                                 # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting import (RANGED_BOOL_FALSE,    # noqa: E402
                                               RANGED_BOOL_TRUE,
                                               get_invalid_caster_reason,
                                               get_invalid_target_reason)
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

# (visualId du porteur SUMMON, ActiveAbilityType). Les ids sont resolus par
# `catalog_inject.active_ability_id` (table d'enums per-build) et NON par comparaison de chaines --
# piege MESURE par #248 : `templAggressor` (au pool) porte `FragstormGrenadeLauncher` (1048), PAS
# `Fragstorm` (1078).
CARRIERS = [("orksOrkBoys", "Stikkbomb"),
            ("templSmnAggressor", "Fragstorm"),
            ("eldarSmnGuardian", "PlasmaGrenade")]
ENEMY = "necroWarden"
BOARD = "MC1_67"
SEED = 777
RANK = 17
CARRIER_HEALTH = 5000
TOURS_DE_CHAUFFE = 6               # purge les `initialCooldownTurns` (sinon `ValidRequest` partout)
N_ENEMIES = 4

_seq = itertools.count()


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)


def _act(sid, rid, action, timeout=90):
    return _r(sid, "applyAction", {"runnerId": rid, "action": action}, timeout)


def _pos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def _by_vis(dv, vis):
    for u in (dv.get("units") or []):
        if u.get("visualId") == vis and u.get("alive"):
            return u
    return None


def _spawn_visual(unit_id: str) -> str:
    """`UnitConfiguration.VisualId` de l'entree de catalogue = ce que `decisionView` expose, et il
    DIFFERE de l'`Id` gameconfig pour un summon : `eldarSmnGuardian` -> `eldarNpc1Guardian`,
    `orksOrkBoys` -> `orksNpc2OrkBoy`, `templSmnAggressor` -> `templNpc4Aggressor`. MESURE ici :
    chercher le porteur par son id gameconfig rend « porteur ABSENT » alors que le spawn a eu lieu
    (piege deja signale par #248 sur `AlphaWarrior`). Source = `catalog_inject.synthesize`, qui
    mirror `BattleConfigBuilder$$GetUnitConfiguration` : `VisualId <- gameconfig.visualId or Id`."""
    import gameconfig as _G
    return (_G.unit(unit_id) or {}).get("visualId") or unit_id


def _find_carrier(sid, rid, dv, unit_id, aid):
    """Le PORTEUR de l'ability sur le plateau : le `VisualId` de l'entree de catalogue d'abord,
    puis -- si le mapping surprenait -- le NATIF, en demandant qui rend `abilityState.usable` pour
    cet `abilityType` (`ActiveAbilityComponent.GetOrNull(caster, abilityType)` a resolu)."""
    u = _by_vis(dv, _spawn_visual(unit_id))
    if u is not None:
        return u
    for cand in sorted((x for x in (dv.get("units") or []) if x.get("alive")),
                       key=lambda x: int(x["id"])):
        st = ((_nat(sid, rid, int(cand["id"]), aid) or {}).get("abilityState") or {})
        if st.get("usable"):
            print("  [porteur] %d resolu sur u%s(%s) (id catalogue : %s)"
                  % (aid, cand["id"], cand.get("visualId"), unit_id))
            return cand
    return None


def _movable(sid, rid, uid):
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])
                    if t.get("col") is not None]
    return []


def _wait_movable(sid, rid, unit_id, maxit=4):
    """Tuiles de deplacement de `unit_id`, en enchainant les `endturn` jusqu'a ce que son camp ait la
    main. On ne COMPTE pas les `endturn` : quand toutes les unites d'un camp ont agi le moteur
    bascule DEJA seul, et un `endturn` de plus decalerait la parite."""
    for _ in range(maxit):
        t = _movable(sid, rid, unit_id)
        if t:
            return t
        _act(sid, rid, {"kind": "endturn"}, 60)
    return []


def _step_toward(sid, rid, unit_id, goal_pos, want):
    """Rapproche (ou eloigne) `unit_id` de `goal_pos` vers la distance `want`, dans la limite de son
    deplacement du tour. Rend la distance ATTEINTE (ou None si l'unite n'a pas pu bouger)."""
    tiles = _wait_movable(sid, rid, unit_id)
    if not tiles:
        return None
    best = min(tiles, key=lambda t: (abs(hexgeo.distance(t, goal_pos) - want), t))
    _act(sid, rid, {"kind": "move", "unitId": unit_id,
                    "to": {"col": best[0], "row": best[1]}}, 90)
    return hexgeo.distance(best, goal_pos)


def _give_turn_to(sid, rid, vis, maxit=8):
    """Rend la main au camp de `vis` (chaine d'`endturn`)."""
    for _ in range(maxit):
        d = _dv(sid, rid)
        u = _by_vis(d, vis)
        if u is not None and u.get("ctrl"):
            return d
        _act(sid, rid, {"kind": "endturn"}, 60)
    return _dv(sid, rid)


# --------------------------------------------------------------------------- build

def _build(sid, seed: int, board: str):
    """Runner isole ou les TROIS porteurs summon sont spawnes cote joueur, catalogue injecte.
    `owner` = un state-file PROPRE sous `logs/` (jamais `data/`, qui est versionne)."""
    state_file = ROOT / "logs" / ("_probe243-%d-%d.json" % (os.getpid(), next(_seq)))
    state_file.parent.mkdir(parents=True, exist_ok=True)
    vis_ids = [v for v, _ in CARRIERS]
    bc0, added, ab_added, _unres = CI.augment(RD._load_seed_bc(None), vis_ids + [ENEMY], rank=RANK)
    dump = RD._load_board_dump(board)
    template, _pool, _pool_mow = RD._normalize_and_extract_pool(sid, bc0, RANK, board_dump=dump)
    bc = copy.deepcopy(template)
    for vis in vis_ids:
        e = next((u for u in bc["Units"] if u.get("Id") == vis), None)
        if e is None:
            raise RuntimeError("%s absent du catalogue BC.Units apres augment" % vis)
        e["Health"] = CARRIER_HEALTH
        e["RemainingHealth"] = CARRIER_HEALTH
        # Le trait `Summon` (`UnitTrait` 2) rend l'unite AUTOMATIQUE (`UnitExtensions$$IsAutomatic`) :
        # `PlayAutomaticUnitsOperation$$Execute` la joue lui-meme, elle consomme sa charge et
        # `CanStillBeUsed` retombe a false par l'USAGE -> l'oracle court-circuiterait a `0x1`.
        # Le retirer rend l'unite CONTROLABLE ; ce n'est pas lever un gate (cf. case-250).
        e["Traits"] = [t for t in (e.get("Traits") or []) if t != "Summon"]
    RD._patch_predefined_units(bc, [ENEMY] * N_ENEMIES)
    spawns = RD._spawn_points_by_twpi(bc)
    pts = spawns.get(0) or []
    if len(pts) < len(vis_ids):
        raise RuntimeError("%d spawns joueur < %d porteurs sur %s" % (len(pts), len(vis_ids), board))
    pu = [{"unitId": vis_ids[i], "playerId": RD.PLAYER_ID_HUMAN,
           "col": int(pts[i][0]), "row": int(pts[i][1])} for i in range(len(vis_ids))]
    resp = _rpc(sid, "initAndStart",
                [{"configJson": json.dumps(bc), "seed": seed, "playerUnits": pu,
                  "owner": str(state_file.resolve())}], timeout=90)
    rid = ((resp or {}).get("result") or {}).get("runnerId")
    if rid is None:
        raise RuntimeError("initAndStart KO: %s" % json.dumps(resp)[:400])
    state_file.write_text(json.dumps({"runnerId": int(rid)}), encoding="utf-8")
    return int(rid), added, ab_added, state_file


# --------------------------------------------------------------------------- montages geometriques

def _foes(dv, caster_u):
    return sorted((u for u in (dv.get("units") or [])
                   if u.get("alive") and u.get("owner") != caster_u.get("owner")),
                  key=lambda u: int(u["id"]))


def _drive(sid, rid, caster_vis, wants, rounds=12):
    """Conduit les ennemis aux distances `wants` du caster (`wants[i]` = distance visee du i-eme
    ennemi, par id croissant). On DEPLACE les DEUX camps (`applyAction` ne verifie pas la propriete
    du `unitId`, runner.md §4) plutot que subir les spawns. Rend le decisionView final."""
    for it in range(rounds):
        d = _dv(sid, rid)
        cu = _by_vis(d, caster_vis)
        if cu is None:
            raise RuntimeError("caster %s absent ou mort" % caster_vis)
        cp = _pos(cu)
        foes = _foes(d, cu)
        got = [hexgeo.distance(cp, _pos(f)) for f in foes]
        print("  [drive %-18s %2d] caster@%s distances=%s (visees=%s)"
              % (caster_vis, it, cp, got, list(wants)))
        if all(got[i] == wants[i] for i in range(min(len(got), len(wants)))):
            return d
        moved = False
        for i, f in enumerate(foes[:len(wants)]):
            if got[i] != wants[i]:
                r = _step_toward(sid, rid, int(f["id"]), cp, wants[i])
                moved = moved or (r is not None)
        if not moved:
            _act(sid, rid, {"kind": "endturn"}, 60)
    print("  [drive] montage PARTIEL accepte (les distances REELLES sont mesurees, pas supposees)")
    return _dv(sid, rid)


# --------------------------------------------------------------------------- variantes du port

def _variant(aid, kind):
    """Les CINQ versions confrontees. Chaque contrefactuel neutralise UN champ des
    `TargetingOptions` et un seul : une ligne que le natif refuse et qu'un contrefactuel accepte
    (ou l'inverse) prouve que CE champ porte le verdict."""
    klass = ABILITY_CLASSES[aid]
    base = klass.TARGETING_OPTIONS
    if kind == "apres":
        return klass()
    opts = {
        "avant": None,
        "sansRules": _replace(base, rules=0),
        "sansRange": _replace(base, range=None),
        "fmtFlip": _replace(base, force_melee_target=(RANGED_BOOL_FALSE
                                                      if int(base.force_melee_target) == RANGED_BOOL_TRUE
                                                      else RANGED_BOOL_TRUE)),
    }[kind]

    class _V(klass):
        __slots__ = ()
        TARGETING_OPTIONS = opts
    return _V()


VARIANTS = ["apres", "avant", "sansRules", "sansRange", "fmtFlip"]


def _nat(sid, rid, cid, aid, tid=None):
    body = {"runnerId": rid, "casterId": cid, "abilityType": int(aid)}
    if tid is not None:
        body["targetId"] = int(tid)
    return _r(sid, "abilityReason", body, 60)


def _hexval(node):
    h = (node or {}).get("hex")
    if isinstance(h, str):
        return int(h, 16)
    return 0 if (node or {}).get("ruleClass") == "NoBrokenTargetingRule" else None


def _snapshot_state(sid, rid):
    dv = _dv(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 120)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indisponible")
    board = Board(bg["tiles"], adjacency="native_sym")
    return dv, load_state(dv, ob, snap, board=board)


def _measure(sid, rid, st, dv, caster_u, aid, montage):
    cid = int(caster_u["id"])
    rows = []
    for u in (dv.get("units") or []):
        if not u.get("alive"):
            continue
        tid = int(u["id"])
        # le camp se lit sur `owner`, JAMAIS sur `ctrl` (qui designe le joueur COURANT et s'inverse
        # des qu'on a pilote une unite adverse pour monter la geometrie)
        side = ("CASTER" if tid == cid else
                ("ALLIE" if u.get("owner") == caster_u.get("owner") else "ENNEMI"))
        nat = _nat(sid, rid, cid, aid, tid)
        tr = (nat or {}).get("targetReason") or {}
        row = {"montage": montage, "label": "%s %s" % (side, u.get("visualId")), "targetId": tid,
               "side": side, "dist": hexgeo.distance(_pos(caster_u), _pos(u)),
               "nat": _hexval(tr), "nat_reasons": tr.get("reasons") or [],
               "nat_caster": _hexval((nat or {}).get("casterReason") or {})}
        for v in VARIANTS:
            row[v] = int(get_invalid_target_reason(st, cid, tid, _variant(aid, v)))
        rows.append(row)
    return rows


def _print_rows(aid, caster_u, rows):
    opts = ABILITY_CLASSES[aid].TARGETING_OPTIONS
    print("\n=== ability %d  caster=u%s(%s)  masque=0x%x  fmt=%d (%s)"
          % (aid, caster_u["id"], caster_u.get("visualId"), int(opts.rules),
             int(opts.force_melee_target),
             "RangedBool.True -> clamp ARME" if int(opts.force_melee_target) == RANGED_BOOL_TRUE
             else "RangedBool.False -> clamp DESARME"))
    hdr = "  %-7s %-24s %-5s %-3s %-10s %-24s" % ("montage", "cible", "id", "d", "natif", "regle")
    for v in VARIANTS:
        hdr += " %-10s" % v
    print(hdr + " accord")
    for r in rows:
        line = "  %-7s %-24s %-5d %-3s %-10s %-24s" % (
            r["montage"], r["label"], r["targetId"], r["dist"],
            "-" if r["nat"] is None else hex(r["nat"]),
            ",".join(r["nat_reasons"])[:24] or "-")
        for v in VARIANTS:
            line += " %-10s" % hex(r[v])
        gain = (r["nat"] not in (None, 0)) and r["avant"] == 0
        print(line + (" OK" if r["nat"] == r["apres"] else " MISMATCH")
              + ("  <-GAIN" if gain else ""))


def _verdict(aid, rows):
    """Les cinq garde-fous du critere de decision, evalues sur les lignes ENNEMIES conduites."""
    n_agree = sum(1 for r in rows if r["nat"] == r["apres"])
    n_gain = sum(1 for r in rows if r["nat"] not in (None, 0) and r["avant"] == 0)
    foes = [r for r in rows if r["side"] == "ENNEMI"]
    libre = [r for r in foes if r["montage"] == "libre"]
    melee = [r for r in foes if r["montage"] == "melee"]
    fmt_armed = int(ABILITY_CLASSES[aid].TARGETING_OPTIONS.force_melee_target) == RANGED_BOOL_TRUE
    # encadrement du seuil, montage LIBRE (aucun clamp) : d <= 2 accepte, d = 3 refuse
    acc = [r for r in libre if r["dist"] <= 2 and r["nat"] == 0]
    ref = [r for r in libre if r["dist"] >= 3 and r["nat"] not in (None, 0)]
    # discriminant du clamp : une cible a d = 2 avec un ennemi au contact
    at2 = [r for r in melee if r["dist"] == 2]
    contact = any(r["dist"] == 1 for r in melee)
    if fmt_armed:
        disc = contact and bool(at2) and all(r["nat"] not in (None, 0) for r in at2)
    else:
        disc = contact and bool(at2) and all(r["nat"] == 0 for r in at2)
    # le contrefactuel `fmtFlip` DOIT diverger sur ces lignes-la (sinon le champ n'est pas mesure)
    n_fmt = sum(1 for r in rows if r["fmtFlip"] != r["apres"])
    cf = {v: sum(1 for r in rows if r[v] != r["apres"]) for v in VARIANTS if v != "apres"}
    ok = (n_agree == len(rows) and acc and ref and disc and n_gain > 0 and n_fmt > 0)
    print("  [bilan %d] accord natif/APRES %d/%d ; casts illegaux que master acceptait : %d"
          % (aid, n_agree, len(rows), n_gain))
    print("  [seuil %d] LIBRE : accepte a d<=2 : %d ligne(s) ; refuse a d>=3 : %d ligne(s)"
          % (aid, len(acc), len(ref)))
    print("  [clamp %d] MELEE : ennemi au contact=%s ; cibles d=2 : %d ; attendu=%s -> %s"
          % (aid, contact, len(at2), "REFUS" if fmt_armed else "ACCEPT",
             "OK" if disc else "NON EXERCE/KO"))
    print("  [contrefactuels %d] lignes divergentes : %s"
          % (aid, "  ".join("%s -> %d/%d" % (v, cf[v], len(rows)) for v in cf)))
    inertes = [v for v in cf if v != "avant" and cf[v] == 0]
    if inertes:
        print("  [NON VALIDE PAR LA MESURE %d] champs dont la neutralisation ne change RIEN : %s"
              % (aid, ",".join(inertes)))
    print("  [VERDICT %d] %s" % (aid, "PASS" if ok else "FAIL"))
    return ok, {"ability": aid, "agree": n_agree, "rows": len(rows), "gain": n_gain,
                "seuil_accept": len(acc), "seuil_refus": len(ref), "clamp_ok": bool(disc),
                "cf": cf, "inertes": inertes, "detail": rows}


def resolve_carriers(only=None):
    """[(unitId de catalogue, ActiveAbilityType, nom)] -- ids resolus par la table d'enums
    per-build, JAMAIS par comparaison de chaines."""
    out = [(v, CI.active_ability_id(n), n) for v, n in CARRIERS]
    if only:
        out = [c for c in out if only in (c[2], str(c[1]))]
    return out


def collect(sid, rid, carriers):
    """LE MONTAGE, factorise : pour chaque porteur, purge du cooldown initial, montage LIBRE puis
    MELEE, et les lignes natif+port des deux. Rend `{aid: {"caster", "rows", "state"}}`.

    C'est ce que le probe imprime ET ce que la garde pytest (`test_splash_range_clamp_live.py`)
    consomme -- une seule definition du montage, pas deux."""
    for _ in range(TOURS_DE_CHAUFFE):
        _act(sid, rid, {"kind": "endturn"}, 60)
    dv0 = _dv(sid, rid)
    print("[plateau] %s" % sorted(set((u.get("visualId"), u.get("owner"))
                                      for u in (dv0.get("units") or []) if u.get("alive"))))
    out = {}
    for vis, aid, name in carriers:
        spawn_vis = _spawn_visual(vis)
        cu = _find_carrier(sid, rid, dv0, vis, aid)
        if cu is None:
            out[aid] = {"error": "porteur %s ABSENT du plateau" % vis}
            continue
        nat0 = _nat(sid, rid, int(cu["id"]), aid)
        if not bool(((nat0 or {}).get("abilityState") or {}).get("usable")):
            out[aid] = {"error": "ability %d NON UTILISABLE par %s -> l'oracle court-circuite "
                                 "(`ValidRequest` 0x1)" % (aid, vis)}
            continue
        rows = []
        # MONTAGE LIBRE : 1er ennemi a d = 2, 2e a d = 3, les autres au large (d >= 5)
        d = _drive(sid, rid, spawn_vis, (2, 3, 5, 6))
        cu = _by_vis(d, spawn_vis) or cu
        dv, st = _snapshot_state(sid, rid)
        rows += _measure(sid, rid, st, dv, _by_vis(dv, spawn_vis) or cu, aid, "libre")
        # MONTAGE MELEE : on amene le 3e ennemi AU CONTACT ; le 1er reste a d = 2
        d = _drive(sid, rid, spawn_vis, (2, 3, 1, 6))
        dv, st = _snapshot_state(sid, rid)
        cu2 = _by_vis(dv, spawn_vis) or cu
        rows += _measure(sid, rid, st, dv, cu2, aid, "melee")
        out[aid] = {"caster": cu2, "rows": rows, "state": st, "name": name}
        dv0 = _dv(sid, rid)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--only", default=None, help="restreint a une ability (nom ou id)")
    a = ap.parse_args(argv)

    carriers = resolve_carriers(a.only)
    if not carriers:
        print("[error] --only %s ne matche aucun porteur" % a.only)
        return 2

    sid = _resolve_session()
    rid, added, ab_added, state_file = _build(sid, a.seed, a.board)
    print("[build] runner=%d board=%s seed=%d catalog_added=%s abilities_added=%s"
          % (rid, a.board, a.seed, added, ab_added))
    allok = True
    out = []
    try:
        got = collect(sid, rid, carriers)
        for _vis, aid, name in carriers:
            rec0 = got.get(aid) or {}
            if rec0.get("error"):
                print("\n=== ability %d (%s) : %s -> non mesure" % (aid, name, rec0["error"]))
                allok = False
                continue
            rows, cu2, st = rec0["rows"], rec0["caster"], rec0["state"]
            _print_rows(aid, cu2, rows)
            ok, rec = _verdict(aid, rows)
            pc = int(get_invalid_caster_reason(st, int(cu2["id"]), _variant(aid, "apres")))
            nc = sorted(set(r["nat_caster"] for r in rows if r["nat_caster"] is not None))
            print("  [volet CASTER %d] casterReason natif=%s port=%s" % (aid, nc, hex(pc)))
            ok = ok and (pc in nc if nc else True)
            rec["caster_nat"] = nc
            rec["caster_port"] = pc
            allok = allok and ok
            out.append(rec)

        print("\n[VERDICT GLOBAL] %s" % ("PASS" if allok else "FAIL"))
        print("[RAW] " + json.dumps(out))
        return 0 if allok else 1
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            state_file.unlink(missing_ok=True)
            print("[cleanup] runner %d dispose" % rid)
        except Exception as e:                                       # noqa: BLE001
            print("[cleanup] dispose KO: %s" % e)


if __name__ == "__main__":
    sys.exit(main())
