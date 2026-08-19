#!/usr/bin/env python
"""probe_444_obscured_targeting -- la LIGNE DE VUE (`TargetIsUnobscured`, bit 24).

CE QUE CE PROBE MESURE
----------------------
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (surcharge 7 arguments) evalue,
DANS le bloc `if (!ignoreRangeChecks)` et juste APRES le volet portee :

    tiles = this.GetTilesObscuringTerrain(caster, casterTiles, pcVar12, options);
    if (0 < tiles.Count) return <box ObscuredTerrainBrokenTargetingRule(tiles)>;   // get_Type = 0x1000000

AUCUN BIT NE L'ARME (mesure #429 : elle tourne pour les **103** masques lisibles). Les bits 25/26 ne
font que la DESARMER, et trois desarmements leur sont ANTERIEURS :
`TargetingConfiguration.EnableObscuringTerrain`, une cible AMIE
(`UnitExtensions$$IsFriendOrHasFriendlyUnitOnIt`), et le trait 1005 `IndirectFire` du caster (qui ne
retire QUE le volet elevation).

DEUX AXES, ET LE SECOND EST LE PLUS DANGEREUX ICI
-------------------------------------------------
  * PERMISSIF   -- sans la regle le port ACCEPTE ce que le natif REFUSE. Lignes `natif=0x1000000`.
  * RESTRICTIF  -- un port TROP strict casserait des casts legitimes sur 103 masques. Lignes
                   `natif=0` : elles sont la MAJORITE de la mesure, et c'est VOULU.
Le probe compte les DEUX et n'accepte un verdict PASS que si les deux sont non vides.

⚠ LE CANAL DE MESURE MENT SI ON LE LIT NAIVEMENT. Le hook `decodeRule` ne sait extraire le flag que
d'un `GenericBrokenTargetingRule` ; pour toute autre classe il publie `hex: "0x0"`. Un refus de
ligne de vue se lit donc « CIBLE VALIDE » via `int(payload["hex"], 16)`. Le decodage passe par
`targeting_reason.native_target_reason`, qui retombe sur la CLASSE (`ObscuredTerrainBrokenTargetingRule`
-> `0x1000000`). Tant que le port ne portait pas la regle, les deux cotes rendaient `0` : accord
parfait, faux des deux cotes.

⚠ ET IL Y A UNE SECONDE CLASSE DANS CE CAS, MESUREE PAR #287-r10 :
`IdunBattle.Core.Services.InFogOfWarBrokenTargetingRule`, boxee par le TOUT PREMIER etage de
`TargetingQuery$$GetInvalidTargetReason` (une tuile de la cible porte `TileComponent+0x40`
`IsInFogOfWar`), AVANT le moindre test de masque -- donc avant le volet portee et avant la ligne de
vue. Elle sort elle aussi en `hex: "0x0"` ; son `Type` vaut `1`. `RULE_CLASS_CODES` la porte
desormais. Le montage de CE probe (`C1_09`) est mono-salle, donc hors de ce regime : le brouillard
n'existe que sur les 15 boards `C6_*`, seuls a porter plusieurs `RoomID` et des `Doors`
(`probe_287r10_fog_capteur_live.py`).

LE MONTAGE
----------
Board `C1_09` -- choisi par un balayage OFFLINE des 779 boards versionnes : c'est celui dont la plus
grande part des paires (from, to) a distance 2..4 entre tuiles marchables est coupee par l'elevation
(203 / 973, 20,9 %). La geometrie n'est donc jamais une excuse : le materiel discriminant est dans
le terrain.

Casters cote joueur : `genesKelermorph` (porte `HeroicFusillade` 1180, masque `0x6004002`) et
`custoKyrus` (porte `VigilanceEternal` 1202, masque `0x206004002`). Les DEUX posent les bits 25 ET
26, donc la ligne de vue est DESARMEE pour ces abilities et ARMEE pour leur attaque normale
(`0x4002`). C'est le contraste CENTRAL du probe : meme caster, meme cible, meme geometrie, deux
masques -- seule la permission change, donc seule elle peut expliquer le basculement.

QUATRE ETAGES
-------------
  A. GEOMETRIE (offline) -- le port enumere les paires (caster, cible) dont il PREDIT l'obstruction,
     et le probe DEPLACE les unites pour en realiser au moins une a portee. Jamais « bloque par la
     geometrie de spawn ».
  B. ACCORD natif/port, cible par cible, sur l'attaque normale ET sur l'ability desarmee.
  C. CONTREFACTUEL DU CHAMP -- la meme classe avec `AllowObscuredTarget` (0x6000000) OR-e sur son
     masque : le port doit ACCEPTER ce qu'il refusait. C'est aussi l'etat de `master` (regle non
     portee), donc la mesure de la DEGRADATION fermee.
  D. DESARMEMENT CONFRONTE AU NATIF -- le contraste attaque normale vs ability 1180/1202 sur la
     MEME paire : le natif doit refuser l'une et pas l'autre.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_444_obscured_targeting.py
    python probe_444_obscured_targeting.py --seed 31337 --board C1_05      # generalisation

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
from targeting_reason import native_target_reason                    # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting import (                      # noqa: E402
    NORMAL_ATTACK_TARGETING_OPTIONS, _NormalAttackTargeting, get_invalid_target_reason,
    get_tiles_obscuring_terrain)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
_seq = itertools.count()

NORMAL_ATTACK = 69                      # `Loki_NormalAttack` -- l'id CONCRET, jamais l'abstrait 17
UNOBSCURED = int(TR.TargetIsUnobscured)

# Les DEUX casters du montage et leur ability a ligne de vue DESARMEE (bits 25+26 poses au ctor).
DISARMED_BY = {"genesKelermorph": 1180, "custoKyrus": 1202}
P_UNITS = ["genesKelermorph", "custoKyrus"]
A_UNITS = "necroWarden,necroWarden,necroWarden,necroWarden"
TOURS_DE_CHAUFFE = 6                     # purge les `initialCooldownTurns`


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


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


def _nat(sid, rid, cid, aid, tid=None):
    body = {"runnerId": rid, "casterId": int(cid), "abilityType": int(aid)}
    if tid is not None:
        body["targetId"] = int(tid)
    return _r(sid, "abilityReason", body, 60)


def _build(sid, seed, board, p_units, a_units, unit_stat=None):
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, qui est versionne).
    ATTEND qu'un slot se libere si MAX_RUNNERS est sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe444-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--p-units", ",".join(p_units), "--a-units", a_units]
    if unit_stat:
        argv += ["--unit-stat", unit_stat]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"]), state
        out = (p.stderr or p.stdout or "")
        if ("runner cap reached" not in out and "runner creation paused" not in out) \
                or time.time() >= deadline:
            raise RuntimeError("build KO : " + out[-500:])
        time.sleep(10)


def _capture(sid, rid):
    dv = _dv(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indisponible")
    board = Board(bg["tiles"], adjacency="native_sym")
    return dv, load_state(dv, ob, snap, board=board), board


def _movable(sid, rid, uid):
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])
                    if t.get("col") is not None]
    return []


# --------------------------------------------------------------------------- etage A : geometrie

def _plan_triplet(board, occupied, want_d=2):
    """Etage A -- LE CRAFT. Cherche un TRIPLET de positions `(pc, p_bloquee, p_libre)` tel que :

        d(pc, p_bloquee) == d(pc, p_libre) == want_d       (la MEME distance des deux cotes)
        la ligne de vue pc -> p_bloquee est COUPEE par le terrain
        la ligne de vue pc -> p_libre   est LIBRE

    Les deux cibles sont a la MEME distance : c'est ce qui rend la paire discriminante. Un refus qui
    ne tomberait que sur la plus lointaine accuserait la PORTEE, pas la ligne de vue -- et la portee
    PRECEDE la ligne de vue dans la cascade, donc l'erreur serait invisible.

    `want_d = 2` parce que la ligne de vue ne mord qu'a partir de d >= 2 (`2 < lineA.Count`) et que
    l'attaque normale des casters du montage porte a 2. Les trois tuiles sont marchables, non
    occupees, et aucune n'est adjacente a une autre (pas de clamp melee du caster ranged :
    `TargetingOptions.forceMeleeTarget = IfRangedCaster`).

    C'est le « DEPLACE les unites pour forcer la configuration » : on ne se plaint pas de la
    geometrie de spawn, on la CHOISIT."""
    walk = [(t["col"], t["row"]) for t in board.by_id.values()
            if t.get("walkable") and (t["col"], t["row"]) not in occupied]
    ws = set(walk)
    for pc in sorted(walk):
        ring = [p for p in hexgeo.ring(pc[0], pc[1], want_d) if p in ws]
        blocked = [p for p in ring if get_tiles_obscuring_terrain_pos(board, pc, p)]
        free = [p for p in ring if not get_tiles_obscuring_terrain_pos(board, pc, p)]
        for pb in blocked:
            for pf in free:
                if hexgeo.distance(pb, pf) >= 2:
                    return pc, pb, pf
    return None


def get_tiles_obscuring_terrain_pos(board, frm, to):
    """Le predicat du port en domaine POSITION (masque `All` = elevation | murs, seuil 2), pour la
    PLANIFICATION seule. La MESURE, elle, passe par la cascade complete."""
    from engine.services.movement_query import get_tiles_obscuring_terrain as _g
    return _g(board, frm, to, 6, 2)


# --------------------------------------------------------------------------- etages B/C/D

def _variant(klass_or_inst, rules_or):
    """La MEME ability avec des bits OR-es sur son masque -- contrefactuel du CHAMP, jamais du code."""
    klass = klass_or_inst if isinstance(klass_or_inst, type) else type(klass_or_inst)
    base = klass.TARGETING_OPTIONS

    class _V(klass):                                                  # type: ignore[misc, valid-type]
        __slots__ = ()
        TARGETING_OPTIONS = _replace(base, rules=int(base.rules) | int(rules_or))
    return _V()


def _measure(sid, rid, state, dv, caster_u, aid, ability_obj, disarmed_obj):
    """Etages B + C, une ligne par cible vivante. Rend la liste des lignes."""
    rows = []
    cid = int(caster_u["id"])
    for t in sorted((u for u in (dv.get("units") or []) if u.get("alive")),
                    key=lambda x: int(x["id"])):
        tid = int(t["id"])
        if tid == cid:
            continue
        nat = native_target_reason(((_nat(sid, rid, cid, aid, tid) or {}).get("targetReason")))
        port = int(get_invalid_target_reason(state, cid, tid, ability_obj) or 0)
        port_off = int(get_invalid_target_reason(state, cid, tid, disarmed_obj) or 0)
        rows.append({
            "caster": cid, "caster_vis": caster_u.get("visualId"), "ability": aid,
            "target": tid, "target_vis": t.get("visualId"),
            "d": hexgeo.distance(_pos(caster_u), _pos(t)),
            "ally": t.get("owner") == caster_u.get("owner"),
            "nat": nat, "port": port, "port_disarmed": port_off,
            "obscuring": sorted(get_tiles_obscuring_terrain(
                state, cid, tid, ability_obj.TARGETING_OPTIONS)),
        })
    return rows


def _print_rows(title, rows):
    print("\n--- %s" % title)
    print("  %-8s %-18s %-3s %-5s %-12s %-12s %-12s %s"
          % ("cible", "visual", "d", "ami", "natif", "port", "port(desarme)", "tuiles"))
    for r in rows:
        def _h(v):
            return "None" if v is None else hex(v)
        print("  u%-7d %-18s %-3s %-5s %-12s %-12s %-12s %s"
              % (r["target"], (r["target_vis"] or "")[:18], r["d"], "oui" if r["ally"] else "non",
                 _h(r["nat"]), _h(r["port"]), _h(r["port_disarmed"]),
                 ",".join("%d/%d" % p for p in r["obscuring"]) or "-"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="C1_09")
    ap.add_argument("--p-units", default=",".join(P_UNITS))
    ap.add_argument("--a-units", default=A_UNITS)
    ap.add_argument("--movement", type=int, default=20,
                    help="Movement force sur les acteurs du craft (atteindre le triplet en 1 tour)")
    ap.add_argument("--json", default=None, help="ecrit le detail des lignes dans ce fichier")
    a = ap.parse_args(argv)

    sid = _resolve_session()
    p_units = [x for x in a.p_units.split(",") if x]
    # MOUVEMENT MONTE sur les trois acteurs du craft : c'est ce qui rend n'importe quelle tuile du
    # board atteignable en UN tour, donc le triplet de positions REALISABLE. Aucun effet sur la
    # regle mesuree -- la ligne de vue ne lit ni stats ni deplacement, uniquement le TERRAIN.
    stats = ";".join("%s:Movement=%d" % (v, a.movement) for v in (p_units + ["necroWarden"]))
    rid, state_file = _build(sid, a.seed, a.board, p_units, a.a_units, unit_stat=stats)
    print("[build] runner=%d board=%s seed=%s p_units=%s a_units=%s"
          % (rid, a.board, a.seed, ",".join(p_units), a.a_units))
    all_rows = []
    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)

        dv, state, board = _capture(sid, rid)

        # ETAGE A -- le CRAFT. Un triplet de positions calcule OFFLINE, puis realise en DEPLACANT
        # les unites (le mouvement est monte a `--unit-stat Movement=...` pour que n'importe quelle
        # tuile soit atteignable en un tour, cf. `main`).
        plan = _plan_triplet(board, occupied=set(), want_d=2)
        if plan is None:
            print("[FAIL] aucun triplet (caster, cible obscurcie, cible libre) a d=2 sur ce board")
            return 2
        pc, pb, pf = plan
        print("[craft] caster -> %s ; cible OBSCURCIE -> %s ; cible LIBRE -> %s (d=2 des deux)"
              % (pc, pb, pf))

        caster_vis = p_units[0]
        cu = _by_vis(dv, caster_vis)
        foes = [f for f in (dv.get("units") or [])
                if f.get("alive") and f.get("owner") != cu.get("owner")]
        if cu is None or len(foes) < 2:
            print("[FAIL] caster ou cibles absents")
            return 2
        moves = [(int(cu["id"]), pc, cu.get("owner")),
                 (int(foes[0]["id"]), pb, foes[0].get("owner")),
                 (int(foes[1]["id"]), pf, foes[1].get("owner"))]
        for uid, dest, owner in moves:
            for _ in range(6):
                d0 = _dv(sid, rid)
                u0 = next((x for x in (d0.get("units") or []) if int(x["id"]) == uid), None)
                if u0 is None or tuple(_pos(u0)) == tuple(dest):
                    break
                if not u0.get("ctrl"):
                    _act(sid, rid, {"kind": "endturn"}, 60)
                    continue
                tiles = _movable(sid, rid, uid)
                if tuple(dest) in [tuple(t) for t in tiles]:
                    _act(sid, rid, {"kind": "move", "unitId": uid,
                                    "to": {"col": dest[0], "row": dest[1]}}, 90)
                    break
                if not tiles:
                    _act(sid, rid, {"kind": "endturn"}, 60)
                    continue
                best = min(tiles, key=lambda t: (hexgeo.distance(t, dest), t))
                _act(sid, rid, {"kind": "move", "unitId": uid,
                                "to": {"col": best[0], "row": best[1]}}, 90)
        dv, state, board = _capture(sid, rid)
        for uid, dest, _o in moves:
            u0 = next((x for x in (dv.get("units") or []) if int(x["id"]) == uid), None)
            print("  [place] u%d -> %s (voulu %s)%s"
                  % (uid, _pos(u0), dest, "" if tuple(_pos(u0)) == tuple(dest) else "  MANQUE"))

        # ETAGES B + C + D
        for vis in p_units:
            u = _by_vis(dv, vis)
            if u is None:
                print("[skip] %s absent du plateau" % vis)
                continue
            aid_disarmed = DISARMED_BY.get(vis)
            targets = [(NORMAL_ATTACK, _NormalAttackTargeting())]
            if aid_disarmed in ABILITY_CLASSES:
                targets.append((aid_disarmed, ABILITY_CLASSES[aid_disarmed]()))
            for aid, obj in targets:
                disarmed = _variant(obj, TR.AllowObscuredTarget)
                rows = _measure(sid, rid, state, dv, u, aid, obj, disarmed)
                all_rows.extend(rows)
                _print_rows("%s (u%s) / ability %d  masque=%s"
                            % (vis, u["id"], aid, hex(int(obj.TARGETING_OPTIONS.rules))), rows)

        # ------------------------------------------------------------------ VERDICT
        cmp_rows = [r for r in all_rows if r["nat"] is not None]
        acc = [r for r in cmp_rows if r["nat"] == r["port"]]
        mismatch = [r for r in cmp_rows if r["nat"] != r["port"]]
        refus_los = [r for r in cmp_rows if r["nat"] == UNOBSCURED]
        accepte = [r for r in cmp_rows if r["nat"] == 0]
        # Etage C : parmi les refus LOS, ceux que le contrefactuel du champ leve.
        leve = [r for r in refus_los if r["port"] == UNOBSCURED and r["port_disarmed"] != UNOBSCURED]
        # Etage D : le natif lui-meme desarme -- meme (caster, cible), l'ability 1180/1202 accepte
        # la ou l'attaque normale refuse pour ligne de vue.
        by_pair = {}
        for r in cmp_rows:
            by_pair.setdefault((r["caster"], r["target"]), {})[r["ability"]] = r
        contraste = [(k, v) for k, v in by_pair.items()
                     if len(v) > 1
                     and any(x["nat"] == UNOBSCURED for x in v.values())
                     and any(x["nat"] != UNOBSCURED for x in v.values())]

        print("\n=== VERDICT ==========================================================")
        print("  lignes comparables      : %d" % len(cmp_rows))
        print("  accord natif/port       : %d / %d" % (len(acc), len(cmp_rows)))
        print("  natif REFUSE (ligne de vue, 0x1000000) : %d" % len(refus_los))
        print("  natif ACCEPTE (0x0)                    : %d" % len(accepte))
        print("  etage C -- refus LEVE par AllowObscuredTarget : %d / %d"
              % (len(leve), len(refus_los)))
        print("  etage D -- paires ou le NATIF desarme selon le masque : %d" % len(contraste))
        # IMPUTABILITE. Tout desaccord dont l'un des deux cotes vaut `TargetIsUnobscured` est de
        # CETTE tranche -- c'est le seul critere qui ne depende pas du code mesure.
        #
        # ⚠ LE PREMIER JET UTILISAIT `nat == port_disarmed`, ET C'ETAIT UN TROU MESURE : neutraliser
        # la regle dans le port rend `port == port_disarmed == 0` face a `nat == 0x1000000`, donc
        # `nat != port_disarmed`, donc le desaccord se classait « PREEXISTANT » et le probe rendait
        # PASS. Deux lecteurs qui partagent le meme code mute s'accordent toujours.
        mine = [r for r in mismatch
                if UNOBSCURED in (r["nat"], r["port"]) or r["nat"] == r["port_disarmed"]]
        preexist = [r for r in mismatch if r not in mine]
        for label, group in (("DESACCORD (cette tranche)", mine),
                             ("desaccord PREEXISTANT (survit au desarmement)", preexist)):
            for r in group:
                print("  [%s] caster=u%d ability=%d cible=u%d d=%d natif=%s port=%s "
                      "port(desarme)=%s tuiles=%s"
                      % (label, r["caster"], r["ability"], r["target"], r["d"],
                         hex(r["nat"]), hex(r["port"]), hex(r["port_disarmed"]),
                         ",".join("%d/%d" % p for p in r["obscuring"]) or "-"))
        ok = (not mine) and refus_los and accepte
        print("  VERDICT : %s" % ("PASS" if ok else "FAIL"))
        # Ligne machine, consommee par `tests/engine/runner/test_obscured_targeting_live.py` : le
        # probe MESURE, le test GARDE, et les deux partagent le MEME montage (aucun second runner).
        print("[RAW] " + json.dumps({"rows": all_rows, "craft": {"caster": list(pc),
                                                                 "blocked": list(pb),
                                                                 "free": list(pf)}}))
        if a.json:
            Path(a.json).write_text(json.dumps(all_rows, indent=1), encoding="utf-8")
        return 0 if ok else 1
    finally:
        try:
            _r(sid, "disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass
        state_file.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
