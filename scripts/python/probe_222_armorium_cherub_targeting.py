#!/usr/bin/env python
"""probe_222_armorium_cherub_targeting -- ARMEMENT du gate de cible d'ArmoriumCherub (1014,
`adeptRetributor` « Vindicta »).

CE QUE CE PROBE MESURE
----------------------
`ArmoriumCherubAbility` entrait dans `ABILITY_CLASSES` SANS `TARGETING_OPTIONS` ->
`get_invalid_target_reason` commence par `options = getattr(ability, "TARGETING_OPTIONS", None)` et
rend 0 immediatement : AUCUN gate. Le moteur acceptait donc des casts que
`IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE (sur un allie, sur soi-meme,
hors portee). Degradation PERMISSIVE -- ni erreur ni crash, invisible en self-play.

FORME DE CTOR = **PRESET STATIQUE COPIE** (la 3e des trois formes, pas la 1re ni la 2e).
`IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$.ctor` n'appelle AUCUN
`IdunBattle.Core.Services.TargetingOptions$$.ctor` : il recopie les 0x40 octets du champ STATIQUE de
`TargetingOptions` a l'offset +0x140 du bloc `<class>+0xb8`, puis
`AActiveAbility..ctor(this, &opts, 0, 0)`. Le masque EFFECTIF est donc la constante ecrite par
`IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28` = `*(statics+0x168)` = 0x4002 :

    0x2     TargetMatchesDynamicRule   -> aucun corps propre dans la classe (ses seules methodes sont
                                          `...$$.ctor`, `...$$ExecuteBehaviour` et le `...$$GetHits`
                                          gshared) -> defaut `AActiveAbility` = 0 = aucun refus
    0x4000  TargetIsEnemy              -> refus sur soi-meme / un allie

et le MEME preset porte le volet PORTEE (#241) :
    `TargetingRange` <- `TargetingRange` statique +0x18 (`useRangeFromConfig`)
        -> `SetConfigValuesInTargetingOptions` pose `OverrideRange` = `ArmoriumCherub.constants.range` = 2
    `forceMeleeTarget` (`<preset>+0x20`) = 0 = `RangedBool.True`
        -> `GetRange` clampe a 1 et pose `onlyAdjacent` des que `ShouldApplyRangedInMelee` (un ennemi
           vivant, ciblable et non-Steppable est AU CONTACT du caster).

ORACLE = le LIVE : `abilityReason(casterId, abilityType, targetId)` rend le masque `TargetingRule`
NATIF. Le probe rejoue ensuite le gate OFFLINE sur le MEME etat fige, dans DEUX versions :
  * APRES  = l'ability du registre (masque pose par cette tranche) ;
  * AVANT  = la MEME classe avec `TARGETING_OPTIONS = None` -- c'est-a-dire EXACTEMENT l'etat de
             `master` avant cette tranche.
Critere : au moins un cas ou le NATIF REFUSE et ou AVANT rendait 0 (« refusait de refuser »), et
accord natif/APRES sur TOUTES les lignes.

COMMENT LA GEOMETRIE EST FORCEE (jamais subie)
----------------------------------------------
Trois etats figes, chacun avec sa propre capture (`decisionView`/`observeBattle`/`combatSnapshot`) :

  S1 `spawn`    Vindicta n'a pas bouge, les ennemis sont au loin -> l'allie et le self tombent sur
                `TargetIsEnemy`, l'ennemi lointain sur `TargetIsInRange`.
  S2 `portee`   Vindicta AMENEE sur une tuile ou le plus proche ennemi est a EXACTEMENT 2 (aucun au
                contact) -> cet ennemi est ACCEPTE (0) : la portee de config (2) mord, le clamp melee
                NON.
  S3 `melee`    Vindicta AMENEE sur une tuile ou un ennemi est a 1 ET un autre a 2. C'est le cas
                DISCRIMINANT de `forceMeleeTarget = RangedBool.True` : `ShouldApplyRangedInMelee`
                devient vrai, `GetRange` clampe a 1, et l'ennemi a d=2 -- ACCEPTE en S2 -- devient
                REFUSE `TargetIsInRange`. Un port qui aurait recopie le masque en oubliant le champ
                `forceMeleeTarget` du preset passerait S1/S2 et se ferait prendre ICI.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_222_armorium_cherub_targeting.py
    python probe_222_armorium_cherub_targeting.py --seed 777 --board MC1_67
    python probe_222_armorium_cherub_targeting.py --sweep 8      # generalisation

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
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

ARMORIUM_CHERUB = 1014
VINDICTA = "adeptRetributor"       # HERO du pool (`rl_duel.py build --list-pool`, rank 17)
ALLY = "adeptCanoness"             # 2e hero de MON camp -> cible AMIE
A_UNITS = "necroWarden,necroWarden,necroWarden"
BOARD = "MC1_67"
SEED = "777"
TOURS_DE_CHAUFFE = 6                # purge les `initialCooldownTurns` (sinon `ValidRequest` partout)
_seq = itertools.count()


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _build(sid, seed: str, board: str) -> int:
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, qui est versionne).
    ATTEND qu'un slot se libere si MAX_RUNNERS est sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe222-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--p-units", "%s,%s" % (VINDICTA, ALLY), "--a-units", A_UNITS]
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
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)


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


def _reason(sid, rid, caster_id, target_id):
    r = _r(sid, "abilityReason", {"runnerId": rid, "casterId": caster_id,
                                  "abilityType": ARMORIUM_CHERUB, "targetId": target_id}, 90) or {}
    tr = r.get("targetReason") or {}
    cr = r.get("casterReason") or {}
    t_hex = int(tr.get("hex") or "0x0", 16)
    c_hex = int(cr.get("hex") or "0x0", 16)
    # `IsInvalidTarget` natif : le volet CASTER passe d'abord et son code est rendu tel quel.
    return {"hex": c_hex or t_hex,
            "names": list(cr.get("reasons") or []) if c_hex else list(tr.get("reasons") or []),
            "target_hex": t_hex, "caster_hex": c_hex}


# --------------------------------------------------------------------------- les deux ports

def ability_after():
    """L'ability du REGISTRE (masque pose par cette tranche)."""
    return ABILITY_CLASSES[ARMORIUM_CHERUB]()


def ability_before():
    """L'ability TELLE QU'ELLE ETAIT sur `master` : meme classe, meme behaviour, mais AUCUN masque
    (`TARGETING_OPTIONS = None` -> `get_invalid_target_reason` rend 0 des sa 1re ligne). Sous-classer
    plutot que patcher l'attribut garde le registre INTACT pour les autres appelants."""
    base = ABILITY_CLASSES[ARMORIUM_CHERUB]
    return type("AvantArmoriumCherub", (base,), {
        "TARGETING_OPTIONS": None,
        "__slots__": (),
    })()


def ability_variant(name: str, **over):
    """CONTREFACTUEL -- la MEME ability avec UN champ du preset change. Sert a prouver qu'un champ
    lu au decompile est PORTEUR (il change un verdict) et pas decoratif : si le port rend le meme
    verdict avec et sans, la mesure n'aurait rien prouve sur ce champ."""
    from dataclasses import replace as _replace
    base = ABILITY_CLASSES[ARMORIUM_CHERUB]
    opts = _replace(base.TARGETING_OPTIONS, **over)
    return type(name, (base,), {"TARGETING_OPTIONS": opts, "__slots__": ()})()


# --------------------------------------------------------------------------- montage

def _capture(sid, rid, board):
    dec = _dv(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
    return dec, load_state(dec, ob, snap, board=board)


def _units(dec):
    units = [u for u in (dec.get("units") or []) if u.get("alive")]
    vin = next((u for u in units if u.get("visualId") == VINDICTA), None)
    ally = next((u for u in units if u.get("visualId") == ALLY), None)
    foes = [u for u in units if not u.get("ctrl")]
    return vin, ally, foes


def _dists(tile, foes):
    return sorted(hexgeo.distance(tile, _pos(f)) for f in foes)


def _score_range2(tile, foes):
    """S2 : le plus proche ennemi a EXACTEMENT 2 (donc aucun au contact). Score = 0 si atteint."""
    d = _dists(tile, foes)
    if not d:
        return 99
    return abs(d[0] - 2)


def _score_melee_split(tile, foes):
    """S3 : un ennemi a 1 ET un autre a 2. Score = 0 si atteint (le cas DISCRIMINANT du clamp)."""
    d = _dists(tile, foes)
    if len(d) < 2:
        return 99
    pen = abs(d[0] - 1)
    pen += 0 if any(x == 2 for x in d[1:]) else min(abs(x - 2) for x in d[1:])
    return pen


def _seek(sid, rid, uid, score, rounds=10):
    """DEPLACE l'unite `uid` jusqu'a MINIMISER `score(tile, foes)`, puis DEUX `endturn` (le tour
    repasse a l'adversaire puis revient -> `StartTurnOperation` purge le flag `Moved`). Rend le score
    atteint. Doctrine : on CONDUIT les positions, on ne subit jamais la geometrie de spawn."""
    best_seen = 99
    for _ in range(rounds):
        d = _my_turn(sid, rid)
        me = next((u for u in (d.get("units") or []) if u.get("id") == uid), None)
        _v, _a, foes = _units(d)
        if me is None or not foes:
            return best_seen
        cur = score(_pos(me), foes)
        best_seen = min(best_seen, cur)
        if cur == 0:
            _act(sid, rid, {"kind": "endturn"}, 60)
            _act(sid, rid, {"kind": "endturn"}, 60)
            return 0
        tiles = _movable(sid, rid, uid)
        if not tiles:
            return best_seen
        best = min(tiles, key=lambda t: (score(t, foes), t))
        if score(best, foes) >= cur:
            # aucune tuile atteignable n'ameliore : on avance vers l'ennemi le plus proche
            near = min(foes, key=lambda f: hexgeo.distance(_pos(me), _pos(f)))
            best = min(tiles, key=lambda t: (hexgeo.distance(t, _pos(near)), t))
        _act(sid, rid, {"kind": "move", "unitId": uid,
                        "to": {"col": best[0], "row": best[1]}}, 90)
        _act(sid, rid, {"kind": "endturn"}, 60)
        _act(sid, rid, {"kind": "endturn"}, 60)
    d = _my_turn(sid, rid)
    me = next((u for u in (d.get("units") or []) if u.get("id") == uid), None)
    _v, _a, foes = _units(d)
    return score(_pos(me), foes) if (me is not None and foes) else best_seen


def _row(sid, rid, state, caster_id, target_id, label):
    """UNE mesure : oracle natif, port APRES, port AVANT -- sur le MEME etat fige."""
    nat = _reason(sid, rid, caster_id, target_id)
    after = int(is_invalid_target(state, caster_id, target_id, ability_after()) or 0)
    before = int(is_invalid_target(state, caster_id, target_id, ability_before()) or 0)
    return {"case": label, "target": target_id, "native": nat["hex"], "names": nat["names"],
            "after": after, "before": before,
            "agree": after == nat["hex"],
            "regression_closed": nat["hex"] != 0 and before == 0}


# --------------------------------------------------------------------------- run

def run(seed: str = SEED, board_id: str = BOARD, sid=None, rid=None, keep: bool = False) -> dict:
    sid = sid or _resolve_session()
    own = rid is None
    rid = rid if rid is not None else _build(sid, seed, board_id)
    rows = []
    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)
        _my_turn(sid, rid)

        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            raise RuntimeError("boardGraph indisponible")
        # `native_sym` = mode CANONIQUE de production : la topologie que
        # `MovementUtil$$AreTilesAdjacent` et `TileQuery$$IterateAdjacentTiles` lisent.
        board = Board(bg["tiles"], adjacency="native_sym")

        # ---- S1 : spawn (Vindicta n'a pas bouge ; les ennemis sont au loin) -----------------
        dec, state = _capture(sid, rid, board)
        vin, ally, foes = _units(dec)
        if vin is None or ally is None or not foes:
            raise RuntimeError("roster incomplet au spawn")
        cid = vin["id"]
        far = max(foes, key=lambda f: hexgeo.distance(_pos(vin), _pos(f)))
        rows.append(_row(sid, rid, state, cid, ally["id"], "S1 cible AMIE"))
        rows.append(_row(sid, rid, state, cid, cid, "S1 cible = LE CASTER"))
        rows.append(_row(sid, rid, state, cid, far["id"],
                         "S1 ennemi LOIN d=%d (portee config 2)"
                         % hexgeo.distance(_pos(vin), _pos(far))))

        # ---- S2 : ennemi le plus proche a EXACTEMENT 2, aucun au contact -> ACCEPTE ---------
        s2 = _seek(sid, rid, cid, _score_range2)
        dec, state = _capture(sid, rid, board)
        vin, ally, foes = _units(dec)
        d2 = _dists(_pos(vin), foes)
        near = min(foes, key=lambda f: hexgeo.distance(_pos(vin), _pos(f)))
        rows.append(_row(sid, rid, state, cid, near["id"],
                         "S2 ennemi d=%d, aucun au contact (dists=%s)"
                         % (d2[0] if d2 else -1, d2)))

        # ---- S3 : DISCRIMINANT du clamp melee (un ennemi a 1, un autre a 2) ------------------
        s3 = _seek(sid, rid, cid, _score_melee_split)
        dec, state = _capture(sid, rid, board)
        vin, ally, foes = _units(dec)
        dd = [(hexgeo.distance(_pos(vin), _pos(f)), f) for f in foes]
        dd.sort(key=lambda x: x[0])
        adj = next((f for d, f in dd if d == 1), None)
        at2 = next((f for d, f in dd if d == 2), None)
        if adj is not None:
            rows.append(_row(sid, rid, state, cid, adj["id"],
                             "S3 ennemi AU CONTACT d=1 (dists=%s)" % [d for d, _f in dd]))
        cf = {}
        if at2 is not None:
            rows.append(_row(sid, rid, state, cid, at2["id"],
                             "S3 ennemi d=2 SOUS clamp melee (dists=%s)" % [d for d, _f in dd]))
            # CONTREFACTUELS sur le MEME etat fige : chacun retire UN champ lu au decompile.
            # `force_melee_target = RangedBool.False` -> plus de clamp -> le port ACCEPTERAIT a d=2,
            # la ou le natif REFUSE. `range = None` (TargetingRange non RE-lu) -> plus aucun gate de
            # portee. Les deux DOIVENT diverger du natif : c'est ce qui prouve que le preset
            # `TargetingOptions statics+0x140` a ete lu en ENTIER, pas seulement son masque `Rules`.
            from engine.runner.abilities.targeting import RANGED_BOOL_FALSE
            cf["no_force_melee"] = int(is_invalid_target(
                state, cid, at2["id"],
                ability_variant("CfNoForceMelee", force_melee_target=RANGED_BOOL_FALSE)) or 0)
            cf["no_range"] = int(is_invalid_target(
                state, cid, at2["id"], ability_variant("CfNoRange", range=None)) or 0)
            cf["native"] = _reason(sid, rid, cid, at2["id"])["hex"]
        rows.append({"case": "_meta", "target": None, "native": 0, "names": [],
                     "after": 0, "before": 0, "agree": True, "regression_closed": False,
                     "meta": {"s2_score": s2, "s3_score": s3,
                              "s3_has_adj": adj is not None, "s3_has_d2": at2 is not None,
                              "cf": cf}})
    finally:
        if own and not keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    return {"runner": rid, "rows": rows}


def sweep(seed: str = SEED, board_id: str = BOARD, steps: int = 8, sid=None,
          rid=None, keep: bool = False) -> dict:
    """GENERALISATION -- chasse au sur-ajustement « distance <= 2 » tout court.

    Le verdict de portee d'ArmoriumCherub n'est PAS « hexDistance <= 2 » : il depend AUSSI de
    `ShouldApplyRangedInMelee` (`forceMeleeTarget = RangedBool.True` du preset). A distance EGALE 2,
    le natif ACCEPTE si aucun ennemi n'est au contact du caster et REFUSE sinon. Le sweep deplace
    Vindicta de proche en proche et confronte natif/port sur CHAQUE ennemi vivant ; le rapport isole
    les distances ou le verdict natif DIFFERE a distance EGALE -- exactement le regime ou un port
    « distance seule » se separerait du natif."""
    sid = sid or _resolve_session()
    own = rid is None
    rid = rid if rid is not None else _build(sid, seed, board_id)
    pts = []
    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)
        _my_turn(sid, rid)
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="native_sym")
        for step in range(steps):
            dec, state = _capture(sid, rid, board)
            vin, _ally, foes = _units(dec)
            if vin is None or not foes:
                break
            dmin = min(hexgeo.distance(_pos(vin), _pos(f)) for f in foes)
            for f in foes:
                d = hexgeo.distance(_pos(vin), _pos(f))
                row = _row(sid, rid, state, vin["id"], f["id"],
                           "sweep step=%d d=%d dmin=%d" % (step, d, dmin))
                row["d"] = d
                row["dmin"] = dmin
                pts.append(row)
            near = min(foes, key=lambda f: hexgeo.distance(_pos(vin), _pos(f)))
            tiles = _movable(sid, rid, vin["id"])
            if not tiles:
                break
            best = min(tiles, key=lambda t: (hexgeo.distance(t, _pos(near)), t))
            _act(sid, rid, {"kind": "move", "unitId": vin["id"],
                            "to": {"col": best[0], "row": best[1]}}, 90)
            _act(sid, rid, {"kind": "endturn"}, 60)
            _act(sid, rid, {"kind": "endturn"}, 60)
            _my_turn(sid, rid)
    finally:
        if own and not keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    return {"runner": rid, "points": pts}


def _print_sweep(out):
    pts = out["points"]
    bad = [p for p in pts if not p["agree"]]
    by_d = {}
    by_pair = {}
    for p in pts:
        by_d.setdefault(p["d"], set()).add(p["native"])
        by_pair.setdefault((p["d"], p.get("dmin")), set()).add(p["native"])
    split = sorted(d for d, v in by_d.items() if len(v) > 1)
    print("[222] SWEEP generalisation : %d points, %d desaccords natif/port" % (len(pts), len(bad)))
    for d in sorted(by_d):
        print("   d=%-3d verdicts natifs = %s" % (d, ",".join("0x%x" % v for v in sorted(by_d[d]))))
    # (d, dmin) : `dmin` = distance au PLUS PROCHE ennemi, donc `dmin == 1` == regime de clamp
    # `ShouldApplyRangedInMelee`. C'est LA variable qui separe deux verdicts a `d` egal.
    print("   croisement (d, dmin=plus proche ennemi) -> verdict natif :")
    for k in sorted(by_pair):
        print("     d=%-3d dmin=%-3d -> %s"
              % (k[0], k[1], ",".join("0x%x" % v for v in sorted(by_pair[k]))))
    if split:
        print("   distances ou le verdict natif DIFFERE a distance EGALE : %s"
              % ",".join(str(d) for d in split))
        print("   -> le verdict n'est PAS la seule distance (clamp melee), et le port suit")
    else:
        print("   aucune distance ne separe deux verdicts sur ce montage (regime non atteint)")
    for p in bad:
        print("   DIFF %s natif=0x%x port=0x%x" % (p["case"], p["native"], p["after"]))
    return len(bad) == 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--sweep", type=int, default=0,
                    help="au lieu des cas nommes : N pas de generalisation")
    a = ap.parse_args(argv)
    if a.sweep:
        out = sweep(seed=a.seed, board_id=a.board, steps=a.sweep, keep=a.keep)
        return 0 if _print_sweep(out) else 1
    out = run(seed=a.seed, board_id=a.board, keep=a.keep)
    print("[222] ArmoriumCherub 1014 -- gate de cible : natif vs port APRES vs port AVANT (master)")
    print("%-46s %14s %12s %12s %6s %6s" % ("cas", "natif", "apres", "avant", "==", "gap"))
    n_agree = n_closed = n_rows = 0
    meta = {}
    for r in out["rows"]:
        if r["case"] == "_meta":
            meta = r.get("meta") or {}
            continue
        n_rows += 1
        print("%-46s %14s %12s %12s %6s %6s" % (
            r["case"][:46], "0x%x" % r["native"], "0x%x" % r["after"], "0x%x" % r["before"],
            "OK" if r["agree"] else "DIFF", "YES" if r["regression_closed"] else "-"))
        if r["names"]:
            print("      natif: %s" % ",".join(r["names"]))
        n_agree += 1 if r["agree"] else 0
        n_closed += 1 if r["regression_closed"] else 0
    print("montage: s2_score=%s s3_score=%s s3_adj=%s s3_d2=%s"
          % (meta.get("s2_score"), meta.get("s3_score"),
             meta.get("s3_has_adj"), meta.get("s3_has_d2")))
    cf = meta.get("cf") or {}
    cf_ok = True
    if cf:
        print("contrefactuels sur la ligne S3 d=2 (natif=0x%x) : "
              "force_melee_target=False -> 0x%x ; range=None -> 0x%x"
              % (cf.get("native", 0), cf.get("no_force_melee", 0), cf.get("no_range", 0)))
        cf_ok = (cf.get("native") not in (None, 0)
                 and cf.get("no_force_melee") != cf.get("native")
                 and cf.get("no_range") != cf.get("native"))
        print("   -> les DEUX champs du preset sont PORTEURS : %s" % ("OUI" if cf_ok else "NON"))
    print("accord natif/port : %d/%d ; cas ou le natif REFUSE et ou master rendait 0 : %d"
          % (n_agree, n_rows, n_closed))
    ok = n_agree == n_rows and n_closed > 0 and cf_ok
    print("PROBE OK" if ok else "PROBE KO")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
