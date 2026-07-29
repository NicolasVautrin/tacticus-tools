#!/usr/bin/env python
"""probe_250_tau_targeting -- ARMEMENT des gates de cible des CINQ abilities du module `tau`.

CE QUE CE PROBE MESURE
----------------------
Les cinq entraient dans `ABILITY_CLASSES` SANS `TARGETING_OPTIONS` ->
`get_invalid_target_reason` / `get_invalid_caster_reason` commencent par
`options = getattr(ability, "TARGETING_OPTIONS", None)` et rendent 0 immediatement : AUCUN gate.
Degradation PERMISSIVE -- ni erreur ni crash, donc invisible en self-play.

LES MASQUES, LUS UN PAR UN AU DECOMPILE (jamais generalises depuis la voisine)

  id    ability                   forme de ctor            rules                 TargetingRange
  ----  ------------------------  -----------------------  --------------------  ----------------
  1077  EarlyWarningOverride      3 PRESET STATIQUE COPIE  0x8004                statics+0x60 SELF
  1081  FightingRetreat           1 FLAGS DIRECTS          0x802                 statics+0x30 ADJ
  1082  InspiredToGreatness       1 FLAGS DIRECTS          0x402                 statics+0x30 ADJ
  1160  HeavyRailRifle            1 FLAGS DIRECTS          0x10400040004000      statics+0x48 BOARD
  1161  TwinSmartMissileSystem    1 FLAGS DIRECTS          0x40004000            statics+0x48 BOARD

1077 n'appelle AUCUN `IdunBattle.Core.Services.TargetingOptions$$.ctor` : il recopie les 0x40 octets
du champ statique `TargetingOptions statics+0x280`, et le masque effectif est la constante ecrite
par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28` = `*(statics+0x2a8)`.
1160 et 1161 sont portees par la MEME MoW (`tauBroadside`), sortent de la MEME forme de ctor, ont le
MEME `TargetingRange` -- et DEUX masques distincts : 1160 porte en plus `TargetIsActor` (bit 46) et
`CasterHas2TurnsLeft` (bit 52). Contre-exemple intra-porteur : generaliser aurait produit un masque
FAUX.

CE QUI EST PORTE, ET CE QUI NE L'EST PAS (le probe le MESURE, il ne le suppose pas)
----------------------------------------------------------------------------------
PORTE : `TargetIsEnemy` (1160/1161), `TargetIsFriendly` (1082), et le VOLET PORTEE
(`RANGE_ADJACENT` -> branche `AreEntitiesAdjacent` pour 1081/1082 ; `RANGE_WHOLE_BOARD` -> aucun
test pour 1160/1161 ; `RANGE_SELF` pour 1077).
NON PORTE, donc PERMISSIF : le bit `TargetMatchesDynamicRule` (1081/1082) -- la classe d'ability ne
fournit pas encore de `get_dynamic_invalid_target_reason`, alors que le natif invoque
`...FightingRetreatAbility$$GetDynamicInvalidTargetReason` (rend 2) et
`...InspiredToGreatnessAbility$$GetDynamicInvalidTargetReason` (rend 1). Le probe SEPARE donc les
lignes « tranchees par un bit PORTE » des lignes « tranchees par la regle DYNAMIQUE », et exige
l'accord parfait sur les premieres.
Egalement non portes et mesures inertes ici : `CasterMatchesDynamicRule` (1077),
`AllowNullCasterTile` (1160/1161), `TargetIsActor` (1160), `CasterHas2TurnsLeft` (1160).

ORACLE = le LIVE : `abilityReason(casterId, abilityType, targetId)` (qui appelle
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` natif). Le probe rejoue le gate
OFFLINE sur le MEME etat fige, en plusieurs versions :
  * APRES     = l'ability du registre (masque pose par cette tranche) ;
  * AVANT     = la MEME classe avec `TARGETING_OPTIONS = None` (l'etat de `master`) ;
  * sansRules = masque a 0, `TargetingRange` conserve  -> isole le volet REGLES ;
  * sansRange = memes regles, `range = None`           -> isole le volet PORTEE ;
  * melee1    = `force_melee_target = RangedBool.True` -> montre si le champ est seulement LU.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_250_tau_targeting.py
    python probe_250_tau_targeting.py --seed 31337 --board C4_09

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
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

# (ability_type, visualId du porteur, nom court, {code natif: nom de la regle NON PORTEE})
# Les « residus » sont les refus que le NATIF prononce par une regle que le port ne modelise PAS :
# le port rend alors 0 (degradation PERMISSIVE, convention de tout `abilities/targeting.py`). Ils
# sont NOMMES ici pour que le probe les distingue d'un vrai desaccord -- une ligne residu doit avoir
# `port == 0`, sinon c'est un MISMATCH.
#   - 1081 : `FightingRetreatAbility$$GetDynamicInvalidTargetReason` rend 2 (== TargetMatchesDynamicRule)
#   - 1082 : `InspiredToGreatnessAbility$$GetDynamicInvalidTargetReason` rend 1 (le natif REUTILISE
#            le litteral `ValidRequest` comme code de refus)
CASES = [
    (1077, "tauCrisis", "EarlyWarningOverride", {}),
    (1081, "tauDarkstrider", "FightingRetreat", {0x2: "GetDynamicInvalidTargetReason"}),
    (1082, "tauAunShi", "InspiredToGreatness", {0x1: "GetDynamicInvalidTargetReason"}),
    (1160, "tauBroadside", "HeavyRailRifle", {}),
    (1161, "tauBroadside", "TwinSmartMissileSystem", {}),
]

P_UNITS = "tauCrisis,tauDarkstrider,tauAunShi"
P_MOW = "tauBroadside"
A_MOW = "ultraDreadnought"          # une MoW ENNEMIE : la seule cible qui separe 1160 de 1161
A_UNITS = "necroWarden,necroWarden,necroWarden"
BOARD = "C4_09"                     # MoW-capable (MachineOfWarPosition pose pour les DEUX camps)
SEED = "777"
WARMUP_ENDTURNS = 6               # purge les `initialCooldownTurns` (sinon `ValidRequest` partout)
HUB_VIS = "tauAunShi"             # l'ancre de la geometrie : c'est SON masque qui exige l'adjacence
_seq = itertools.count()


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _seed_bc_with_ammo(ammo: int = 9) -> Path:
    """Seed BC augmente, ecrit HORS `data/` (qui est VERSIONNE) : `Player.Players[*]
    .MachineOfWarAmmo = ammo`.

    POURQUOI C'EST OBLIGATOIRE POUR 1160. Le stock de munitions vit dans
    `IdunBattle.Entities.Components.PlayerComponent+0x6c`, pose UNE fois par
    `IdunBattle.Operations.AddPlayerOperation$$Execute` depuis `BC.Player.Players[].MachineOfWarAmmo`
    (= **0** dans le seed partage), et AUCUNE operation native ne l'incremente. Il gate
    `IdunBattle.Entities.Abilities.AActiveAbility$$get_CanCurrentlyBeUsed` -- or l'oracle
    `abilityReason` passe par `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason`
    (surcharge 4 arguments), dont la PREMIERE ligne est
    `if (ability == null || !ability.CanCurrentlyBeUsed || ability.<+0x44> == 0) return
    GenericBrokenTargetingRule(1);`. MESURE (#250, C4_09/777, seed partage) : 1160 (`ammoCost = 1`,
    `hasAmmo = false`) rend **0x1 sur TOUTES les lignes, casterReason compris** -- la cascade n'est
    JAMAIS evaluee, donc AUCUNE mesure de masque n'est possible. 1161 (`ammoCost = null`) n'est pas
    concernee et mesure normalement. Avec `MachineOfWarAmmo = 9` la cascade s'evalue."""
    import rl_collect_batch as R
    src = json.loads((R.ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    for p in ((src.get("Player") or {}).get("Players") or {}).values():
        p["MachineOfWarAmmo"] = int(ammo)
    out = ROOT / "logs" / ("_probe250-seedbc-%d.json" % os.getpid())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(src), encoding="utf-8")
    return out


def _build(sid, seed: str, board: str, seed_bc: Path):
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, qui est versionne).
    ATTEND qu'un slot se libere si MAX_RUNNERS est sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe250-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai", "--seed-bc", str(seed_bc),
            "--p-units", P_UNITS, "--p-mow", P_MOW, "--a-mow", A_MOW, "--a-units", A_UNITS]
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


def _actors(dec):
    """TOUTES les entites-ACTEUR du plateau, unites ET machines of war, sous une forme commune.

    Une MoW n'est PAS dans `decisionView.units` : elle vit dans `decisionView.mows`, dont la cle ECS
    est `casterId` (== `machineId`, l'entite **Machine**) -- c'est l'id qu'attendent
    `applyAction{kind:"ability", casterId}` et `abilityReason`. Le champ `id` de la ligne est la
    PLATEFORME, pas l'acteur. Elle n'a NI position NI PV (hors-plateau, cf.
    `engine/runner/snapshot.py` `_load_machines`), d'ou `pos = (None, None)`."""
    out = []
    for u in (dec.get("units") or []):
        if u.get("alive"):
            out.append({"id": int(u["id"]), "visualId": u.get("visualId"), "owner": u.get("owner"),
                        "pos": _pos(u), "machine": False})
    for m in (dec.get("mows") or []):
        if m.get("alive") and m.get("casterId") is not None:
            out.append({"id": int(m["casterId"]), "visualId": m.get("visualId"),
                        "owner": m.get("owner"), "pos": (None, None), "machine": True})
    return out


def _by_vis(dec, vis):
    for a in _actors(dec):
        if a["visualId"] == vis:
            return a
    return None


def _dist(a, b):
    """Distance hex, ou None des qu'un des deux acteurs est HORS-PLATEAU (MoW)."""
    if None in a["pos"] or None in b["pos"]:
        return None
    return hexgeo.distance(a["pos"], b["pos"])


def _movable(sid, rid, uid):
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])
                    if t.get("col") is not None]
    return []


def _wait_movable(sid, rid, unit_id, maxit=4):
    """Tuiles de deplacement de `unit_id`, en enchainant les `endturn` jusqu'a ce que son camp AIT la
    main. On ne COMPTE pas les `endturn` : quand toutes les unites d'un camp ont agi le moteur
    bascule DEJA de lui-meme, et un `endturn` de plus decalerait la parite."""
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


def _hand_to(sid, rid, vis, maxit=8):
    """Rend la main au camp de l'unite `vis` (chaine de `endturn`, runner `--no-ai`).
    On NOMME le camp voulu : tester `currentPlayer == <une unite ctrl>.owner` serait une tautologie
    (`ctrl` DESIGNE le joueur courant), et ce probe pilote les DEUX camps."""
    for _ in range(maxit):
        d = _dv(sid, rid)
        me = _by_vis(d, vis)
        if me is not None and d.get("currentPlayer") == me["owner"]:
            return d
        _act(sid, rid, {"kind": "endturn"}, 60)
    return _dv(sid, rid)


# --------------------------------------------------------------------------- montage geometrique

def _drive_cluster(sid, rid, rounds=10):
    """Monte la geometrie DISCRIMINANTE, en DEPLACANT les unites (jamais en subissant les spawns) :

      * `tauDarkstrider` (ALLIE) AU CONTACT de `tauAunShi`  -> ligne « allie adjacent »   (1082 : 0)
      * un ennemi AU CONTACT de `tauAunShi`                 -> ligne « ennemi adjacent »  (1082 : 0x400)
      * `tauCrisis` (ALLIE) HORS contact de `tauAunShi`     -> ligne « allie loin »       (1082 : portee)
      * un ennemi HORS contact                              -> ligne « ennemi loin »

    `applyAction` ne verifie pas la propriete du `unitId` (runner.md §4) mais `aiMovableTiles` est
    calcule pour le JOUEUR COURANT -> on pilote MES unites pendant mon tour et les ENNEMIES pendant
    le leur (runner `--no-ai` : rien ne bouge tout seul)."""
    def _snap():
        d = _dv(sid, rid)
        hub = _by_vis(d, HUB_VIS)
        if hub is None:
            raise RuntimeError("montage impossible : %s absent du plateau" % HUB_VIS)
        board_foes = sorted((a for a in _actors(d)
                             if a["owner"] != hub["owner"] and None not in a["pos"]),
                            key=lambda a: (_dist(hub, a), a["id"]))
        return d, hub, board_foes

    for it in range(rounds):
        d, hub, foes = _snap()
        ally = _by_vis(d, "tauDarkstrider")
        far_ally = _by_vis(d, "tauCrisis")
        if ally is None:
            raise RuntimeError("montage impossible : tauDarkstrider absent")
        if len(foes) < 2:
            raise RuntimeError("il faut >= 2 ennemis SUR LE PLATEAU pour separer contact/hors-contact")
        d_ally = _dist(hub, ally)
        d_near = _dist(hub, foes[0])
        d_far = _dist(hub, foes[-1])
        d_falone = _dist(hub, far_ally) if far_ally is not None else 9
        print("  [drive %d] hub=%s d(allie)=%s d(ennemi_proche)=%s d(ennemi_loin)=%s d(allie_loin)=%s"
              % (it, hub["pos"], d_ally, d_near, d_far, d_falone))
        if d_ally == 1 and d_near == 1 and d_far >= 2 and d_falone >= 2:
            return
        if d_ally != 1:
            _step_toward(sid, rid, ally["id"], hub["pos"], 1)
        if d_falone < 2 and far_ally is not None:
            _step_toward(sid, rid, far_ally["id"], hub["pos"], 3)
        d, hub, foes = _snap()
        if _dist(hub, foes[0]) != 1:
            _step_toward(sid, rid, foes[0]["id"], hub["pos"], 1)
        if _dist(hub, foes[-1]) < 2:
            _step_toward(sid, rid, foes[-1]["id"], hub["pos"], 4)
    print("  [drive] geometrie cible non atteinte -- on mesure la geometrie OBTENUE "
          "(les distances reelles sont imprimees dans chaque table)")


# --------------------------------------------------------------------------- variantes du port

def _ability(aid: int, variant: str):
    klass = ABILITY_CLASSES[aid]
    base = klass.TARGETING_OPTIONS
    if variant == "apres":
        return klass()
    over = {"avant": None,
            "sansRules": _replace(base, rules=0),
            "sansRange": _replace(base, range=None),
            "melee1": _replace(base, force_melee_target=RANGED_BOOL_TRUE)}[variant]

    class _V(klass):
        __slots__ = ()
        TARGETING_OPTIONS = over
    return _V()


VARIANTS = ("apres", "avant", "sansRules", "sansRange", "melee1")


def _nat(sid, rid, cid, aid, tid=None):
    body = {"runnerId": rid, "casterId": cid, "abilityType": aid}
    if tid is not None:
        body["targetId"] = tid
    out = _r(sid, "abilityReason", body, 60) or {}
    tr = out.get("targetReason") or {}
    cr = out.get("casterReason") or {}

    def _v(blk):
        h = blk.get("hex")
        if isinstance(h, str):
            return int(h, 16)
        return 0 if blk.get("ruleClass") == "NoBrokenTargetingRule" else None
    return _v(tr), (tr.get("reasons") or []), tr.get("ruleClass"), _v(cr), out


def _measure(sid, rid, st, dv, aid, caster_vis, residuals):
    """Une table par ability : chaque unite VIVANTE du plateau comme cible."""
    caster = _by_vis(dv, caster_vis)
    if caster is None:
        print("[%d] porteur %s ABSENT du plateau -- ability non mesuree" % (aid, caster_vis))
        return None
    cid = caster["id"]
    _, _, _, _, raw0 = _nat(sid, rid, cid, aid)
    usable = bool(((raw0 or {}).get("abilityState") or {}).get("usable"))
    mask = int(ABILITY_CLASSES[aid].TARGETING_OPTIONS.rules)
    rows = []
    for u in _actors(dv):
        tid = u["id"]
        dist = _dist(caster, u)
        side = "CASTER" if tid == cid else (
            "ALLIE" if u["owner"] == caster["owner"] else "ENNEMI")
        if u["machine"] and tid != cid:
            side += "/MoW"
        nv, reasons, rclass, cv, _ = _nat(sid, rid, cid, aid, tid)
        row = {"label": "%s %s" % (side, u["visualId"]), "targetId": tid, "dist": dist,
               "nat": nv, "nat_reasons": reasons, "nat_class": rclass, "nat_caster": cv}
        for v in VARIANTS:
            row[v] = int(get_invalid_target_reason(st, cid, tid, _ability(aid, v)))
        rows.append(row)

    print("\n[%d %s] caster=u%d(%s) pos=%s usable=%s masque=0x%x range=%s melee=%s"
          % (aid, caster_vis, cid, caster["visualId"], caster["pos"], usable, mask,
             ABILITY_CLASSES[aid].TARGETING_OPTIONS.range,
             ABILITY_CLASSES[aid].TARGETING_OPTIONS.force_melee_target))
    print("  %-22s %-5s %-3s %-13s %-24s %-13s %-9s %-11s %-11s %-9s %s"
          % ("cible", "id", "d", "natif", "regle", "APRES", "AVANT", "sansRules",
             "sansRange", "melee1", "verdict"))
    stats = {"agree": 0, "dyn": 0, "gain": 0, "cf_rules": 0, "cf_range": 0, "cf_melee": 0,
             "n": len(rows), "accept": 0, "refuse": 0, "residus": {},
             "residus_codes": dict(residuals)}
    for r in rows:
        dyn_line = (r["nat"] in residuals and r["apres"] == 0)
        agree = (r["nat"] == r["apres"])
        if agree:
            stats["agree"] += 1
        elif dyn_line:
            stats["dyn"] += 1
            k = residuals[r["nat"]]
            stats["residus"][k] = stats["residus"].get(k, 0) + 1
        if r["nat"] == 0:
            stats["accept"] += 1
        elif r["nat"] is not None:
            stats["refuse"] += 1
        gain = agree and r["nat"] not in (None, 0) and r["avant"] == 0
        if gain:
            stats["gain"] += 1
            stats["cf_rules"] += 1 if r["sansRules"] == 0 else 0
            stats["cf_range"] += 1 if r["sansRange"] == 0 else 0
        if r["melee1"] != r["apres"]:
            stats["cf_melee"] += 1
        verdict = "OK" if agree else ("RESIDU" if dyn_line else "MISMATCH")
        print("  %-22s %-5d %-3s %-13s %-24s %-13s %-9s %-11s %-11s %-9s %s%s"
              % (r["label"], r["targetId"], "-" if r["dist"] is None else r["dist"],
                 "-" if r["nat"] is None else hex(r["nat"]),
                 ",".join(r["nat_reasons"]) or r["nat_class"] or "-",
                 hex(r["apres"]), hex(r["avant"]), hex(r["sansRules"]), hex(r["sansRange"]),
                 hex(r["melee1"]), verdict, "  <-GAIN" if gain else ""))
    port_caster = int(get_invalid_caster_reason(st, cid, _ability(aid, "apres")))
    nat_caster = sorted(set(x for x in (r["nat_caster"] for r in rows) if x is not None))
    print("  [volet CASTER] natif=%s port=%s" % (nat_caster, hex(port_caster)))
    print("  [bilan] accord %d/%d ; lignes tranchees par une regle NON PORTEE (residus %s) : %d ; "
          "casts illegaux que master acceptait : %d"
          % (stats["agree"], stats["n"], stats["residus"] or "-", stats["dyn"], stats["gain"]))
    print("  [contrefactuels sur les %d lignes GAIN] sansRules faux-accepte %d ; sansRange "
          "faux-accepte %d ; force_melee_target flippe change %d ligne(s)"
          % (stats["gain"], stats["cf_rules"], stats["cf_range"], stats["cf_melee"]))
    stats.update({"aid": aid, "caster": cid, "usable": usable, "port_caster": port_caster,
                  "nat_caster": nat_caster, "rows": rows})
    return stats


def measure_all(sid, seed=SEED, board=BOARD):
    """Monte le runner, DRIVE la geometrie, fige l'etat, mesure les CINQ abilities.

    Rend `({ability_type: stats}, dispose)` -- `dispose()` est a appeler par l'appelant (le probe le
    fait dans son `finally`, le test de garde dans le teardown de sa fixture). MEME implementation
    pour le probe (qui MESURE) et le test (qui GARDE) : aucune divergence possible entre les deux."""
    seed_bc = _seed_bc_with_ammo()
    rid, state_file = _build(sid, seed, board, seed_bc)
    print("[build] runner=%d board=%s seed=%s seed-bc=%s (MachineOfWarAmmo patche)"
          % (rid, board, seed, seed_bc.name))

    def _dispose():
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            print("[cleanup] runner %d dispose" % rid)
        except Exception as e:                                       # noqa: BLE001
            print("[cleanup] dispose KO: %s" % e)
        finally:
            state_file.unlink(missing_ok=True)
            seed_bc.unlink(missing_ok=True)

    try:
        for _ in range(WARMUP_ENDTURNS):
            _act(sid, rid, {"kind": "endturn"}, 60)
        _drive_cluster(sid, rid)
        _hand_to(sid, rid, HUB_VIS)

        dv = _dv(sid, rid)
        ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            raise RuntimeError("boardGraph indisponible")
        st = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
        out = {}
        for aid, vis, _name, res in CASES:
            s = _measure(sid, rid, st, dv, aid, vis, res)
            if s is not None:
                out[aid] = s
        return out, _dispose
    except BaseException:
        _dispose()
        raise


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    a = ap.parse_args(argv)

    sid = _resolve_session()
    stats, dispose = measure_all(sid, a.seed, a.board)
    try:
        print("\n================ SYNTHESE (board=%s seed=%s) ================" % (a.board, a.seed))
        ok = len(stats) == len(CASES)
        for s in stats.values():
            reste = s["n"] - s["agree"] - s["dyn"]
            print("  %d : accord %d/%d, residus %d %s, mismatch %d, gains %d, accept/refus natif "
                  "%d/%d, usable=%s" % (s["aid"], s["agree"], s["n"], s["dyn"], s["residus"] or "",
                                        reste, s["gain"], s["accept"], s["refuse"], s["usable"]))
            if reste:
                ok = False
        print("[VERDICT] %s" % ("PASS" if ok else "FAIL"))
        print("[RAW] " + json.dumps(list(stats.values())))
        return 0 if ok else 1
    finally:
        dispose()


if __name__ == "__main__":
    sys.exit(main())
