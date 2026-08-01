"""probe #366-r1-crit-multihit -- l'etage CRIT diverge des le 3e coup d'une salve.

CRITERE (binaire, pose AVANT toute methode) :
    le natif et le port consomment-ils le MEME NOMBRE de tirages par coup, sur toute la salve ?
    Si non : a partir de quel coup, et combien chacun ?

DECOMPOSITION PAR ETAGE (jamais un scalaire fitte) :
  (a) NOMBRE de tirages   -- `dumpRng` avant/apres : `mti` (index MT, +1 par genrand_int32) et
      `callCount` (`IntBasedMersenneTwister`+0x14). Cote port : le meme `mti` apres rejeu, plus
      le journal `SpyRng`. Deux modeles qui consomment le meme nombre de genrand finissent au
      MEME `mti` -- c'est un oracle EXACT, pas une reconstitution.
  (b) VALEUR de chaque tirage -- la suite `genrand_int32() >> 1` est REGENEREE offline depuis le
      `mt[624]`/`mti` dumpes AVANT l'attaque ; pour chaque coup live on cherche l'index `k` du
      tirage qui explique sa valeur (`lo + r_k % width`), bornes non-crit ET crit. On obtient la
      CARTE de consommation native, coup par coup.
  (c) APPLICATION -- per-coup live vs `per_hit` offline.

Montage : attaque NORMALE multi-coups, crit OUVERT, block/evasion neutralises.
Porteur par defaut `necroDestroyer` (6 coups) -- AUCUN rapport avec `InescapableAccuracy`, ce qui
est le point : le residu est independant de toute ability.

Usage (depuis scripts/python, ASCII only) :
    python probe_366r1_crit_multihit.py --state <ABSOLU>.json --seed 777 --board MC1_67
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo
from rl_collect_batch import _rpc, _resolve_session

PYDIR = Path(__file__).resolve().parent
LOGS = PYDIR.parent.parent / "logs"


def _unwrap(r):
    return r["result"] if isinstance(r, dict) and "result" in r else r


def rpc(sid, method, body=None, timeout=120):
    return _unwrap(_rpc(sid, method, [body] if body is not None else [], timeout=timeout))


# ---------------------------------------------------------------- RNG instrumente
_EVENTS: list = []


def _spy_rng_class():
    from engine.runner.prng import IntBasedMersenneTwister

    class SpyRng(IntBasedMersenneTwister):
        """Journalise chaque `genrand_int32` (le tirage BRUT) et chaque appel de haut niveau."""
        __slots__ = ()

        def genrand_int32(self):
            v = super().genrand_int32()
            _EVENTS.append(("g", v))
            return v

        def next_internal(self, lo, hi):
            _EVENTS.append(("ni<", lo, hi))
            v = super().next_internal(lo, hi)
            _EVENTS.append(("ni>", lo, hi, v))
            return v

    return SpyRng


# ---------------------------------------------------------------- helpers runner
def upos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def dview(sid, rid):
    return rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def find(d, vis, team=None):
    for u in (d.get("units") or []):
        if u.get("visualId") == vis and (team is None or u.get("team") == team):
            return u
    return None


def drive(sid, rid, unit_id, goal_id, want_dist, iters=24, verbose=False):
    """Rapproche `unit_id` a <= want_dist de `goal_id`. On DEPLACE les unites -- on ne subit
    jamais la geometrie de spawn."""
    for it in range(iters):
        d = dview(sid, rid)
        u = next((x for x in (d.get("units") or []) if x["id"] == unit_id), None)
        g = next((x for x in (d.get("units") or []) if x["id"] == goal_id), None)
        if u is None or g is None:
            return d
        dist = hexgeo.distance(upos(u), upos(g))
        if verbose:
            print("[drive] it=%d u@%s g@%s dist=%s" % (it, upos(u), upos(g), dist))
        if dist <= want_dist:
            return d
        mov = rpc(sid, "aiMovableTiles", {"runnerId": rid, "side": "all"}, 90)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == u["id"]), None)
        tiles = [(t["col"], t["row"]) for t in (mu or {}).get("tiles") or []
                 if t.get("col") is not None]
        if not tiles:
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            continue
        best = min(tiles, key=lambda t: (hexgeo.distance(t, upos(g)), t))
        if hexgeo.distance(best, upos(g)) >= dist:
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            continue
        rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": u["id"], "to": {"col": best[0], "row": best[1]}}}, 90)
    return dview(sid, rid)


def _snapshot(sid, rid):
    from engine.entities.pathfinding.board import Board
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 90)
    board = Board(bg["tiles"], adjacency="native_sym") if (bg or {}).get("tiles") else None
    return (dview(sid, rid), rpc(sid, "observeBattle", {"runnerId": rid}, 90),
            rpc(sid, "combatSnapshot", {"runnerId": rid}, 120),
            rpc(sid, "dumpRng", {"runnerId": rid}, 60), board)


def _offline_state(dv, ob, snap, rng0, board, spy=False):
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    st = load_state(dv, ob, snap, board=board)
    if isinstance(rng0, dict) and rng0.get("mt"):
        r = (_spy_rng_class() if spy else IntBasedMersenneTwister)()
        r.mt = list(rng0["mt"])
        r.mti = rng0["mti"]
        st.rng = r
    return st


def _live_amounts(atk, attacker_id):
    """Les `Amount` live de l'attaque normale de CET attaquant, dans l'ordre d'emission."""
    out = []
    for act in (atk.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else td
            if not td or "Amount" not in td:
                continue
            if td.get("Attacker_Id") != attacker_id:
                continue
            if td.get("Triggered_Ability_Type"):
                continue
            out.append(td["Amount"])
    return out


# ---------------------------------------------------------------- etage (b) : la carte
def _raw_stream(rng0, n):
    """Regenere les `n` premiers `genrand_int32() >> 1` depuis l'etat MT dumpe AVANT l'attaque."""
    from engine.runner.prng import IntBasedMersenneTwister
    r = IntBasedMersenneTwister()
    r.mt = list(rng0["mt"])
    r.mti = rng0["mti"]
    return [r.genrand_int32() >> 1 for _ in range(n)]


def _resolve(raw, lo, hi_excl):
    """Mirror `IntBasedMersenneTwister$$NextInternal(lo, hi_excl)` pour UN tirage brut deja
    consomme (pas de boucle de rejet : on ne teste que la branche non-rejetee)."""
    rng = hi_excl - lo
    if rng <= 0:
        return None
    if (-rng & rng) == rng:
        return ((rng * raw) >> 31) + lo
    return (raw % rng) + lo


def _map_hits(live, stream, cells_nc, cells_cr):
    """Pour chaque valeur live, l'index `k` du tirage brut qui l'explique, et si c'est un crit.
    `cells_*` = (lo, hi) inclusifs. Renvoie une liste de (k, is_crit) ou None."""
    out = []
    for v in live:
        hit = None
        for k, raw in enumerate(stream):
            if cells_nc and _resolve(raw, cells_nc[0], cells_nc[1] + 1) == v:
                hit = (k, False)
                break
            if cells_cr and _resolve(raw, cells_cr[0], cells_cr[1] + 1) == v:
                hit = (k, True)
                break
        out.append(hit)
    return out


# ---------------------------------------------------------------- build
def _build(state_file, seed, board, p_units, a_units, crit, block_target, extra=None):
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
           "--state-file", str(state_file), "--p-units", p_units, "--a-units", a_units,
           "--crit", crit, "--block-target", block_target]
    if extra:
        cmd += list(extra)
    r = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True, timeout=900)
    sys.stdout.write(r.stdout[-3000:])
    if r.returncode != 0:
        sys.stdout.write(r.stderr[-3000:])
        raise SystemExit("build KO rc=%d" % r.returncode)
    return json.loads(Path(state_file).read_text(encoding="utf-8"))["runnerId"]


def measure(call, rid: int, attacker_vis: str, dist: int = 1, mutate: str = None,
            verbose: bool = False) -> dict:
    """LE MONTAGE, reutilisable : drive -> snapshot (dont `dumpRng`) -> attaque normale LIVE ->
    `dumpRng` -> rejeu OFFLINE sur le MEME etat et le MEME flux MT.

    `call(method, body, timeout)` = le transport RPC (le probe passe par la session, le cliquet
    pytest par sa fixture `rpc`) -- le montage ne connait ni l'un ni l'autre.

    `mutate='nogate'` ouvre `damage_hits.crit_gate_open` en grand = le port d'AVANT
    #366-r1-crit-multihit (un crit-roll a CHAQUE coup). C'est la CONTRE-EPREUVE : elle doit
    DIVERGER du live, sinon la mesure ne discrimine rien.

    Renvoie {live, port, crits, d_mti_live, d_mti_port, n_hits, carte, stream, ...}.
    """
    global _EVENTS
    d = call("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    a0 = find(d, attacker_vis, team=1)
    foe = next((u for u in (d.get("units") or []) if u.get("team") == 2), None)
    if a0 is None or foe is None:
        return {"error": "attaquant ou cible introuvable"}
    att_id, foe_id = a0["id"], foe["id"]
    _drive_rpc(call, rid, att_id, foe_id, dist, verbose=verbose)

    dv, ob, snap, rng0, board = _snapshot_rpc(call, rid)
    au = next((u for u in (dv.get("units") or []) if u["id"] == att_id), None)
    fu = next((u for u in (dv.get("units") or []) if u["id"] == foe_id), None)
    if au is None or fu is None:
        return {"error": "unite disparue apres drive"}
    real_dist = hexgeo.distance(upos(au), upos(fu))
    nid = next((a.get("id") for a in (au.get("abilities") or []) if a.get("kind") == "normal"),
               None)
    if nid is None:
        return {"error": "pas d'ability normale sur l'attaquant"}
    atk = call("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att_id, "targetId": foe_id, "abilityType": nid},
        "captureEvents": True}, 180)
    acts = atk.get("actions") or []
    if not acts or not acts[0].get("ok"):
        return {"error": "attaque live refusee: %s" % (str(atk)[:200],)}
    rng1 = call("dumpRng", {"runnerId": rid}, 60)
    live = _live_amounts(atk, att_id)
    d_mti_live = (rng1["mti"] - rng0["mti"]) % 624

    _EVENTS = []
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations import damage_hits as _dh
    st = _offline_state(dv, ob, snap, rng0, board, spy=True)
    _orig_gate = _dh.crit_gate_open
    if mutate == "nogate":
        _dh.crit_gate_open = lambda crit_allowed, is_attack_damage_op: True
    try:
        res = AttackDamageOperation.execute(st, att_id, foe_id) or {}
    finally:
        _dh.crit_gate_open = _orig_gate
    ev = list(_EVENTS)
    d_mti_port = (st.rng.mti - rng0["mti"]) % 624

    cells = sorted({(e[1], e[2] - 1) for e in ev if e[0] == "ni>" and (e[1], e[2]) != (1, 100)})
    stream = _raw_stream(rng0, max(24, len(live) * 3 + 6))
    carte = _map_hits(live, stream, cells[0] if cells else None,
                      cells[-1] if len(cells) > 1 else None) if cells else []
    return {"live": list(live), "port": list(res.get("per_hit") or []),
            "crits": list(res.get("crits") or []), "rolls": list(res.get("rolls") or []),
            "d_mti_live": d_mti_live, "d_mti_port": d_mti_port,
            "n_genrand_port": sum(1 for e in ev if e[0] == "g"),
            "dist": real_dist, "cells": cells, "carte": carte,
            "att_id": att_id, "foe_id": foe_id, "normal_id": nid,
            "d_callcount_live": rng1["callCount"] - rng0["callCount"]}


def _drive_rpc(call, rid, unit_id, goal_id, want_dist, iters=24, verbose=False):
    """`drive` sur un transport RPC injecte (cf. `measure`)."""
    for it in range(iters):
        d = call("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        u = next((x for x in (d.get("units") or []) if x["id"] == unit_id), None)
        g = next((x for x in (d.get("units") or []) if x["id"] == goal_id), None)
        if u is None or g is None:
            return d
        dist = hexgeo.distance(upos(u), upos(g))
        if verbose:
            print("[drive] it=%d u@%s g@%s dist=%s" % (it, upos(u), upos(g), dist))
        if dist <= want_dist:
            return d
        mov = call("aiMovableTiles", {"runnerId": rid, "side": "all"}, 90)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == u["id"]), None)
        tiles = [(t["col"], t["row"]) for t in (mu or {}).get("tiles") or []
                 if t.get("col") is not None]
        if not tiles:
            call("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            continue
        best = min(tiles, key=lambda t: (hexgeo.distance(t, upos(g)), t))
        if hexgeo.distance(best, upos(g)) >= dist:
            call("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            continue
        call("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": u["id"], "to": {"col": best[0], "row": best[1]}}}, 90)
    return call("decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def _snapshot_rpc(call, rid):
    from engine.entities.pathfinding.board import Board
    bg = call("boardGraph", {"runnerId": rid}, 90)
    board = Board(bg["tiles"], adjacency="native_sym") if (bg or {}).get("tiles") else None
    return (call("decisionView", {"runnerId": rid, "allAbilities": True}, 150),
            call("observeBattle", {"runnerId": rid}, 90),
            call("combatSnapshot", {"runnerId": rid}, 120),
            call("dumpRng", {"runnerId": rid}, 60), board)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=str(LOGS / "probe_366r1_crit_multihit.json"))
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--attacker", default="necroDestroyer")
    ap.add_argument("--p-units", default="necroDestroyer,ultraApothecary")
    ap.add_argument("--a-units", default="necroWarden,necroOverlord")
    ap.add_argument("--crit", default="50,700")
    ap.add_argument("--block-target", default="0,0")
    ap.add_argument("--dist", type=int, default=1)
    ap.add_argument("--reuse", action="store_true", help="reutilise le runner du state-file")
    ap.add_argument("--mutate", choices=["nogate"], default=None,
                    help="contre-epreuve : desarme le gate `isCriticalDamageAllowed` (= le port "
                         "d'AVANT ce cas, qui roule un crit a CHAQUE coup). Doit DIVERGER.")
    args = ap.parse_args()

    sid = _resolve_session()
    Path(args.state).parent.mkdir(parents=True, exist_ok=True)
    if args.reuse:
        rid = json.loads(Path(args.state).read_text(encoding="utf-8"))["runnerId"]
    else:
        rid = _build(args.state, args.seed, args.board, args.p_units, args.a_units,
                     args.crit, args.block_target)
    print("[probe] runner=%d seed=%d board=%s" % (rid, args.seed, args.board))

    def call(method, body=None, timeout=120):
        return rpc(sid, method, body, timeout)

    m = measure(call, rid, args.attacker, args.dist, mutate=args.mutate, verbose=True)
    if m.get("error"):
        raise SystemExit(m["error"])
    print("[probe] dist=%s  LIVE per-coup = %s  (n=%d)" % (m["dist"], m["live"], len(m["live"])))
    print("[probe] PORT per-coup = %s" % (m["port"],))
    print("[probe]   crits=%s rolls=%s" % (m["crits"], m["rolls"]))
    print("[probe]   genrand consommes (port) = %d ; d_callCount natif = %d"
          % (m["n_genrand_port"], m["d_callcount_live"]))
    print("[probe]   ETAGE (a) : natif d_mti=%d  port d_mti=%d  -> %s"
          % (m["d_mti_live"], m["d_mti_port"],
             "ACCORD" if m["d_mti_live"] == m["d_mti_port"] else "DIVERGENT"))
    print("[probe]   cellules offline distinctes = %s" % (m["cells"],))
    if m["carte"]:
        print("[probe]   ETAGE (b) carte LIVE :")
        for i, (v, h) in enumerate(zip(m["live"], m["carte"])):
            print("[probe]     coup %d = %-6d <- tirage #%s%s" % (
                i, v, h[0] if h else "?", " (CRIT)" if h and h[1] else ""))
        idx = [h[0] for h in m["carte"] if h]
        if len(idx) >= 2:
            print("[probe]   pas entre tirages consommes (natif) = %s"
                  % ([b - a for a, b in zip(idx, idx[1:])],))
    print("[probe] VERDICT per-coup : %s"
          % ("BIT-EXACT" if m["port"] == m["live"] else "DIVERGENT"))


if __name__ == "__main__":
    main()
