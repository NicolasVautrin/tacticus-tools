#!/usr/bin/env python
"""probe_243_not_adjacent -- MONTAGE NOMME des deux regles d'adjacence du filtre statique de ciblage.

CE QUE CE PROBE MESURE
----------------------
Deux bits de `IdunBattle.Core.Services.TargetingRule` etaient DECLARES par des masques poses au
registre mais N'ETAIENT PAS portes par la cascade (`engine/runner/abilities/targeting.py`), donc ne
refusaient JAMAIS rien offline :

  * bit 32 `TargetIsNotAdjacent`        -- `battleQuery.<slot 0x61>(targetTiles, casterTiles)`
    porteurs : 1058 Waaagh (`orksWarboss`), 1153 HammerOfWrath (`bloodIntercessor`),
               1139 SentinelDirectives (`admecDestroyer`) -- trois HERO du pool.
  * bit 42 `TargetIsNotAdjacentToEnemy` -- `battleQuery.<slot 0x7f>(targetTiles, caster, false)`
    porteur  : 1145 SporeMineLauncher (`tyranBiovore`) -- MACHINE OF WAR du pool MoW.

ORACLE = le LIVE : `abilityReason(casterId, abilityType, targetId)` rend le masque `TargetingRule`
NATIF (`targetReason.hex` + noms). Le probe rejoue ensuite le gate OFFLINE (`is_invalid_target`) sur
le MEME etat fige, ability par ability et cible par cible.

COMMENT LA GEOMETRIE EST FORCEE (jamais subie)
----------------------------------------------
Pour que le bit 32 soit la PREMIERE regle rompue il faut une cible ENNEMIE **au contact** du caster.
On DEPLACE donc chaque hero au contact d'un ennemi distinct, puis on fait passer DEUX `endturn` :
`StartTurnOperation` purge les flags de tour DU JOUEUR ENTRANT, donc le flag `Moved` du hero
disparait alors que sa nouvelle position reste -- sans quoi `CasterHasNotMoved` (0x10, present dans
les masques de 1058 et 1153) sortirait du volet CASTER et MASQUERAIT le bit 32. Le runner est bati
`--no-ai` : personne ne bouge pendant le tour adverse.

Pour le bit 42 le caster est une MoW HORS PLATEAU (aucune tuile) et la cible est une TUILE : on
choisit une tuile LIBRE et marchable VOISINE d'un ennemi (bit 42 attendu) et une tuile LIBRE et
marchable dont AUCUNE voisine ne porte d'ennemi (attendu : accepte).

Usage (depuis scripts/python, session Frida chaude) :
    python probe_243_not_adjacent.py
    python probe_243_not_adjacent.py --seed 31337 --board MC1_67

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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                        # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting import is_invalid_target      # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

WAAAGH = 1058                     # orksWarboss
HAMMER = 1153                     # bloodIntercessor
SENTINEL = 1139                   # admecDestroyer
SPORE = 1145                      # tyranBiovore (MACHINE OF WAR)

# (abilityType, visualId du porteur) -- les trois porteurs du bit 32, tous HERO (`--list-pool`).
BIT32 = ((WAAAGH, "orksWarboss"), (HAMMER, "bloodIntercessor"), (SENTINEL, "admecDestroyer"))
P_UNITS = "orksWarboss,bloodIntercessor,admecDestroyer"
P_MOW = "tyranBiovore"
A_UNITS = "necroWarden,necroWarden,necroWarden"
BOARD = "MC1_67"
SEED = "777"
TOURS_DE_CHAUFFE = 6               # purge les `initialCooldownTurns` (sinon `ValidRequest` partout)
_seq = itertools.count()


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _build(sid, seed: str, board: str) -> int:
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, qui est versionne).
    ATTEND qu'un slot se libere si MAX_RUNNERS est sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe243-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--p-units", P_UNITS, "--p-mow", P_MOW, "--a-units", A_UNITS]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"])
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
    """Rend la main au joueur qui possede mes heros (chaine de `endturn`, runner `--no-ai`)."""
    for _ in range(maxit):
        d = _dv(sid, rid)
        mine = next((u for u in (d.get("units") or []) if u.get("ctrl")), None)
        if mine is not None and d.get("currentPlayer") == mine.get("owner"):
            return d
        _act(sid, rid, {"kind": "endturn"}, 60)
    return _dv(sid, rid)


# --------------------------------------------------------------------------- montage

def _drive_contact(sid, rid, rounds=10):
    """DEPLACE chaque hero du bit 32 au CONTACT d'un ennemi DISTINCT (un ennemi par hero, pour que
    chaque couple (caster, cible adjacente) existe simultanement sur le MEME etat fige).

    `applyAction` ne verifie pas la propriete du `unitId` (runner.md §4) mais le set de
    `aiMovableTiles` est calcule pour le JOUEUR COURANT -> on ne bouge que pendant son propre tour.
    Rend {visualId du hero : id de l'ennemi vise}."""
    pairing: dict = {}
    for _ in range(rounds):
        d = _my_turn(sid, rid)
        units = [u for u in (d.get("units") or []) if u.get("alive")]
        mine = {u.get("visualId"): u for u in units if u.get("ctrl")}
        foes = [u for u in units if not u.get("ctrl")]
        if not foes:
            raise RuntimeError("plus d'ennemi vivant")
        todo = []
        for i, (_at, vis) in enumerate(BIT32):
            hero = mine.get(vis)
            if hero is None:
                raise RuntimeError("hero %s absent du runner" % vis)
            foe = foes[i % len(foes)]
            pairing[vis] = foe["id"]
            if hexgeo.distance(_pos(hero), _pos(foe)) != 1:
                todo.append((hero, foe))
        if not todo:
            return pairing
        for hero, foe in todo:
            tiles = _movable(sid, rid, hero["id"])
            if not tiles:
                continue
            best = min(tiles, key=lambda t: (abs(hexgeo.distance(t, _pos(foe)) - 1), t))
            _act(sid, rid, {"kind": "move", "unitId": hero["id"],
                            "to": {"col": best[0], "row": best[1]}}, 90)
        # DEUX `endturn` : le tour repasse a l'adversaire puis revient -> `StartTurnOperation` purge
        # le flag `Moved` de MES unites (sinon `CasterHasNotMoved` masquerait le bit 32).
        _act(sid, rid, {"kind": "endturn"}, 60)
        _act(sid, rid, {"kind": "endturn"}, 60)
    return pairing


def _pick_tiles(board, dec):
    """TROIS tuiles pour le volet TUILE, choisies pour separer les regles qui se PRECEDENT dans la
    cascade native (`TargetTileIsFree` bit 12 AVANT `TargetIsNotAdjacentToEnemy` bit 42) :

      `far`      LIBRE + marchable, AUCUNE voisine ennemie      -> attendu ACCEPTE
      `near`     LIBRE + marchable, >=1 voisine ennemie         -> attendu bit 42
      `occupied` OCCUPEE, >=1 voisine ennemie                   -> attendu bit 12 (et PAS le bit 42 :
                                                                   c'est le test d'ORDRE)
    """
    occupied_by = {}
    my_owner = None
    for u in (dec.get("units") or []):
        if not u.get("alive"):
            continue
        if u.get("ctrl") and my_owner is None:
            my_owner = u.get("owner")
        p = _pos(u)
        if p[0] is not None:
            occupied_by[p] = u.get("owner")

    def foes_adj(tid):
        n = 0
        for nid in board.neighbours(tid):
            if abs(board.elevation(tid) - board.elevation(nid)) >= 2:
                continue
            if not board.walkable(nid):
                continue
            owner = occupied_by.get(board.coord(nid))
            if owner is not None and owner != my_owner:
                n += 1
        return n

    out = {"near": None, "far": None, "occupied": None}
    for tid, t in sorted(board.by_id.items()):
        p = (t["col"], t["row"])
        if not board.walkable(tid):
            continue
        busy = p in occupied_by
        n = foes_adj(tid)
        if busy:
            if n and out["occupied"] is None:
                out["occupied"] = tid
            continue
        if n and out["near"] is None:
            out["near"] = tid
        if n == 0 and out["far"] is None:
            out["far"] = tid
        if all(v is not None for v in out.values()):
            break
    return out


# Les QUATRE bits que cette tranche fait entrer dans la cascade. Les retirer d'un masque reproduit
# EXACTEMENT l'etat d'avant : une regle non portee ne refuse jamais, ce qui est indiscernable, pour
# `get_invalid_target_reason`, d'un bit absent du masque.
PORTED_HERE = (int(TR.TargetHasFreeAdjacentTile) | int(TR.TargetTileIsFree)
               | int(TR.TargetIsNotAdjacent) | int(TR.TargetIsNotAdjacentToEnemy))


def ability_before(ability_type: int):
    """L'ability TELLE QU'ELLE ETAIT sur `master` : meme classe, meme behaviour, meme regle
    dynamique, masque prive des quatre bits que cette tranche porte. Sous-classer plutot que patcher
    l'attribut garde le registre INTACT pour les autres appelants.

    Le 5e maillon de la tranche (branche `TargetIsTile` -> tuile non marchable, code `ValidRequest`)
    n'est PAS neutralise ici : il est arme par le bit 6, qu'on ne peut pas retirer sans changer toute
    la resolution de cible. Sans effet sur la mesure : `_pick_tiles` ne rend que des tuiles
    `board.walkable`, donc ce maillon ne peut pas mordre sur les trois cas tuile."""
    from dataclasses import replace
    base = ABILITY_CLASSES[ability_type]
    opts = base.TARGETING_OPTIONS
    return type("Avant" + base.__name__, (base,),
                {"TARGETING_OPTIONS": replace(opts, rules=int(opts.rules) & ~PORTED_HERE),
                 "__slots__": ()})()


def _reason(sid, rid, caster_id, ability_type, target_id):
    r = _r(sid, "abilityReason", {"runnerId": rid, "casterId": caster_id,
                                  "abilityType": ability_type, "targetId": target_id}, 90) or {}
    tr = r.get("targetReason") or {}
    cr = r.get("casterReason") or {}
    return {"target_hex": int(tr.get("hex") or "0x0", 16),
            "target_names": list(tr.get("reasons") or []),
            "caster_hex": int(cr.get("hex") or "0x0", 16),
            "caster_names": list(cr.get("reasons") or [])}


def run(seed: str = SEED, board_id: str = BOARD, sid=None, rid=None, keep: bool = False) -> dict:
    """Monte (ou reprend) le runner, force la geometrie, lit l'oracle natif et rejoue le gate
    OFFLINE. Rend un dict de MESURES ; c'est la porte unique de la fixture pytest."""
    sid = sid or _resolve_session()
    own = rid is None
    rid = rid if rid is not None else _build(sid, seed, board_id)
    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)
        pairing = _drive_contact(sid, rid)
        _my_turn(sid, rid)

        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            raise RuntimeError("boardGraph indisponible")
        # `native_sym` = mode CANONIQUE de production (cf. lot181) : c'est lui qui porte la
        # topologie que `MovementUtil$$AreTilesAdjacent` et `TileQuery$$IterateAdjacentTiles` lisent.
        board = Board(bg["tiles"], adjacency="native_sym")
        dec = _dv(sid, rid)
        ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)

        units = [u for u in (dec.get("units") or []) if u.get("alive")]
        mine = {u.get("visualId"): u for u in units if u.get("ctrl")}
        alive_ids = [u["id"] for u in units]
        mow = next((m for m in (dec.get("mows") or [])
                    if m.get("visualId") == P_MOW and m.get("casterId") is not None), None)

        def state():
            return load_state(dec, ob, snap, board=board)

        def port(ability_type, caster_id, target_id):
            return int(is_invalid_target(state(), int(caster_id), int(target_id),
                                         ABILITY_CLASSES[ability_type]()) or 0)

        def before(ability_type, caster_id, target_id):
            return int(is_invalid_target(state(), int(caster_id), int(target_id),
                                         ability_before(ability_type)) or 0)

        rows = []
        for at, vis in BIT32:
            hero = mine.get(vis)
            if hero is None:
                continue
            for uid in alive_ids:
                tgt = next(u for u in units if u["id"] == uid)
                d = hexgeo.distance(_pos(hero), _pos(tgt))
                nat = _reason(sid, rid, hero["id"], at, uid)
                rows.append({"bit": 32, "ability": at, "caster_vis": vis,
                             "caster_id": hero["id"], "target_id": uid,
                             "target_vis": tgt.get("visualId"), "dist": d,
                             "ctrl": bool(tgt.get("ctrl")), "native": nat,
                             "port": port(at, hero["id"], uid),
                             "before": before(at, hero["id"], uid)})

        tiles42 = {}
        if mow is not None:
            for label, tid in sorted(_pick_tiles(board, dec).items()):
                if tid is None:
                    continue
                nat = _reason(sid, rid, mow["casterId"], SPORE, tid)
                tiles42[label] = {"tile_id": tid, "coord": board.coord(tid), "native": nat,
                                  "port": port(SPORE, mow["casterId"], tid),
                                  "before": before(SPORE, mow["casterId"], tid)}

        return {"rid": rid, "sid": sid, "board": board, "dec": dec, "ob": ob, "snap": snap,
                "bg": bg, "pairing": pairing, "mow": mow, "rows": rows, "tiles42": tiles42,
                "alive_ids": alive_ids,
                "casters": {vis: mine[vis]["id"] for _at, vis in BIT32 if vis in mine}}
    finally:
        if own and not keep:
            try:
                _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            except Exception:
                pass


# --------------------------------------------------------------------------- generalisation

# Les AUTRES porteurs des deux regles ajoutees pour l'ORDRE (bits 5 et 12) : ce sont eux qui
# mesurent le RAYON D'IMPACT de la tranche au-dela de ses trois porteurs du bit 32.
#   bit 5  TargetHasFreeAdjacentTile : 1003 (deja garde par lot181), 1009, 1153
#   bit 12 TargetTileIsFree          : 1112, 1145, 1201, 1219
GEN_UNITS = "necroOverlord,tyranWingedPrime,ultraInceptorSgt"
GEN_MOW = "orksRukkatrukk"
GEN_FOES = "necroWarden,necroWarden,orksNob"
GEN_CASES = ((1009, "necroOverlord"), (1003, "ultraInceptorSgt"),
             (1112, "tyranWingedPrime"), (1201, GEN_MOW))
GEN_BOARD = "C3_30"
GEN_SEED = "31337"
GEN_TILE_SAMPLE = 24
GEN_ENDTURNS = 14                 # 1112/1201 restent `ValidRequest` a 6 (cooldown initial plus long)

# Raisons rendues EN AMONT de la cascade de ciblage par `AttackQuery$$GetInvalidTargetReason`
# (`ability == null || !CanCurrentlyBeUsed || level == 0` -> `ValidRequest` ; `IsAlreadyUsedThisTurn`
# -> `AlreadyUseThisTurn`). Ce ne sont PAS des `TargetingRule` de CIBLE : `is_invalid_target` porte le
# maillon SOUS cette porte (le port ne modelise ni cooldown ni munitions) -> HORS CONTRAT, meme
# exclusion que `tests/engine/runner/test_targeting_masks_live.py`.
REQUEST_LEVEL_REASONS = frozenset({int(TR.ValidRequest), int(TR.AlreadyUseThisTurn)})


def run_generalise(seed: str = GEN_SEED, board_id: str = GEN_BOARD, sid=None) -> dict:
    """SECOND montage, AUTRE board et AUTRE seed : balaye les autres porteurs des bits 5 et 12
    (les deux regles que la tranche a du porter pour l'ORDRE) contre TOUTES les unites vivantes ET
    un echantillon de TUILES, et confronte chaque verdict a `abilityReason`.

    C'est la mesure du RAYON D'IMPACT : ces abilities-la ne portent PAS les bits 32/42, donc toute
    divergence qui apparaitrait ici viendrait des deux regles ajoutees (`tile_can_add_unit` /
    `get_free_adjacent_tiles`), pas du coeur de la tranche."""
    sid = sid or _resolve_session()
    rid = _build_gen(sid, seed, board_id)
    try:
        for _ in range(GEN_ENDTURNS):
            _act(sid, rid, {"kind": "endturn"}, 60)
        _my_turn(sid, rid)
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            raise RuntimeError("boardGraph indisponible")
        board = Board(bg["tiles"], adjacency="native_sym")
        dec = _dv(sid, rid)
        ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
        units = [u for u in (dec.get("units") or []) if u.get("alive")]
        by_vis = {u.get("visualId"): u for u in units if u.get("ctrl")}
        for m in (dec.get("mows") or []):
            if m.get("casterId") is not None:
                by_vis.setdefault(m.get("visualId"), {"id": m["casterId"]})
        tiles = sorted(board.by_id)[::max(1, len(board.by_id) // GEN_TILE_SAMPLE)]

        def port(at, cid, tid_):
            st = load_state(dec, ob, snap, board=board)
            return int(is_invalid_target(st, int(cid), int(tid_),
                                         ABILITY_CLASSES[at]()) or 0)

        rows = []
        for at, vis in GEN_CASES:
            caster = by_vis.get(vis)
            if caster is None:
                continue
            targets = [u["id"] for u in units]
            if int(ABILITY_CLASSES[at].TARGETING_OPTIONS.rules) & int(TR.TargetIsTile):
                targets = targets + list(tiles)
            for tid_ in targets:
                nat = _reason(sid, rid, caster["id"], at, tid_)
                rows.append({"ability": at, "caster_vis": vis, "caster_id": caster["id"],
                             "target_id": tid_, "native": nat,
                             "port": port(at, caster["id"], tid_)})
        return {"rid": rid, "board_id": board_id, "seed": seed, "rows": rows,
                "casters": sorted(by_vis)}
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass


def in_contract(rows) -> list:
    """Les couples sur lesquels le contrat de fidelite s'applique.

    Le filtre ne peut PAS se contenter d'exclure la valeur `0x1` : le natif la rend AUSSI depuis la
    cascade elle-meme, pour « tuile-cible non marchable » (branche `TargetIsTile`, litteral 1 ;
    cf. `targeting.py`). Le discriminant est la DEPENDANCE A LA CIBLE : les raisons de
    DISPONIBILITE (`ValidRequest` faute de cooldown/munitions, `AlreadyUseThisTurn`) sortent AVANT
    que la cible ne soit regardee, donc elles valent pour TOUTES les cibles du couple
    (ability, caster). On n'exclut donc un couple que si TOUTES ses lignes portent la meme raison de
    ce jeu -- sinon `0x1` est un verdict PAR CIBLE et reste dans le contrat."""
    by_caster: dict = {}
    for r in rows:
        by_caster.setdefault((r["ability"], r["caster_id"]), []).append(r)
    out = []
    for group in by_caster.values():
        hexes = {r["native"]["target_hex"] for r in group}
        if len(hexes) == 1 and next(iter(hexes)) in REQUEST_LEVEL_REASONS:
            continue                          # ability indisponible : la cascade n'a jamais tourne
        out.extend(group)
    return out


def _build_gen(sid, seed: str, board: str) -> int:
    state = ROOT / "logs" / ("_probe243gen-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--p-units", GEN_UNITS, "--p-mow", GEN_MOW, "--a-units", GEN_FOES]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"])
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out or time.time() >= deadline:
            raise RuntimeError("build KO : " + out[-400:])
        time.sleep(10)


# --------------------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--case", default="main", choices=("main", "generalise"))
    args = ap.parse_args()
    if args.case == "generalise":
        g = run_generalise()
        rows = in_contract(g["rows"])
        wrong = [r for r in rows if r["port"] not in (0, r["native"]["target_hex"])]
        invented = [r for r in rows if r["native"]["target_hex"] == 0 and r["port"] != 0]
        exact = [r for r in rows
                 if r["native"]["target_hex"] and r["port"] == r["native"]["target_hex"]]
        print("[243gen] runner=%s board=%s seed=%s couples=%d (dont %d hors contrat) casters=%s"
              % (g["rid"], g["board_id"], g["seed"], len(rows),
                 len(g["rows"]) - len(rows), g["casters"]))
        print("[243gen] refus INVENTES (natif accepte, port refuse) : %d" % len(invented))
        for r in invented[:10]:
            print("   ", r["ability"], r["caster_vis"], r["target_id"], hex(r["port"]))
        print("[243gen] refus pour une MAUVAISE raison : %d" % len(wrong))
        for r in wrong[:10]:
            print("   ", r["ability"], r["caster_vis"], r["target_id"],
                  hex(r["port"]), hex(r["native"]["target_hex"]), r["native"]["target_names"])
        print("[243gen] refus reproduits a l'identique : %d" % len(exact))
        return
    res = run(args.seed, args.board)
    print("[243] runner=%s pairing=%s" % (res["rid"], res["pairing"]))
    print("")
    print("BIT 32 TargetIsNotAdjacent -- (ability, caster, cible, dist) natif vs port")
    print("%-6s %-18s %-16s %4s %4s  %-34s %-14s %s"
          % ("abil", "caster", "cible", "d", "ami", "natif", "avant", "apres"))
    for r in res["rows"]:
        print("%-6s %-18s %-16s %4s %4s  %-34s %-14s %#x"
              % (r["ability"], r["caster_vis"], r["target_vis"], r["dist"],
                 "oui" if r["ctrl"] else "non",
                 ("%#x %s" % (r["native"]["target_hex"], ",".join(r["native"]["target_names"])))[:34],
                 hex(r["before"]), r["port"]))
    print("")
    print("BITS 12/42 -- SporeMineLauncher (tyranBiovore, cible TUILE)")
    if not res["tiles42"]:
        print("  (MoW absente du runner : rien a mesurer)")
    for label, t in sorted(res["tiles42"].items()):
        print("  %-9s tile=%-4s %-8s natif=%-14s %s avant=%-14s apres=%#x"
              % (label, t["tile_id"], t["coord"], hex(t["native"]["target_hex"]),
                 (",".join(t["native"]["target_names"]) or "-").ljust(28),
                 hex(t["before"]), t["port"]))
    print("")
    bad = [r for r in res["rows"]
           if r["port"] not in (0, r["native"]["target_hex"])]
    print("[243] refus pour une MAUVAISE raison : %d" % len(bad))
    for r in bad:
        print("   ", r)
    print("[243] TargetIsNotAdjacent natif observe : %d fois"
          % sum(1 for r in res["rows"] if r["native"]["target_hex"] == int(TR.TargetIsNotAdjacent)))
    red = [r for r in res["rows"]
           if r["native"]["target_hex"] and r["before"] == 0 and r["port"] == r["native"]["target_hex"]]
    print("[243] ROUGE AVANT ferme par cette tranche (unites) : %d" % len(red))


if __name__ == "__main__":
    main()
