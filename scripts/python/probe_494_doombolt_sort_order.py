"""Probe #494 -- `1102 Doombolt` : PAR QUOI le natif ordonne-t-il ses cibles, et a quel etage le
port en diverge ?

Ecart rapporte (case-487 §8, mesure du 2026-08-07, board `MC1_67`, seed 777) :

    LIVE {81: 1, 83: 1, 87: 1}      PORT {81: 1, 83: 1, 85: 1}

Les deux cotes repartissent bien `N = 3` sur `C = 4` (`r = 3` -> `[1, 1, 1, 0]`) : c'est l'ORDRE
rendu par `IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector$$Select` qui diverge, donc
QUI est la 4e (celle a 0 coup).

CE QUE CE PROBE MESURE, ETAGE PAR ETAGE (jamais un scalaire fitte) :
  0. le REGIME du montage -- PV, armure et `maxHp` de chaque cible. `rl_duel --hp-target` force
     `Health = RemainingHealth` ET met `Armor = FixedArmor` a **0** : si tous les etages d'entree de
     l'utilite sont EGAUX, l'utilite l'est aussi et le classement est entierement decide par le
     TIE-BREAK. Cet etage doit etre lu AVANT de conclure quoi que ce soit (c'est exactement ce qui a
     fait survivre le trou d'armure de #527-r1 a sa validation).
  1. l'ORDRE SOURCE du port = ce que rend `DoomboltAbility$$GetTargets` avant tout tri
     (`Damageable(Unobscured(SurroundingEnemies(...)))`), donc l'enumeration des TUILES par
     `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`.
  2. l'UTILITE du port par cible (`engine/runner/operations/damage_utility._target_utility`).
  3. l'ORDRE FINAL du port et sa repartition de coups.
  4. l'ORDRE FINAL du natif, LU dans la sequence d'evenements du cast live (le RNG avance dans
     l'ordre d'iteration, donc la sequence des `Amount` EST la permutation).

A/B DE POSITION -- les regimes `A` et `B` ne different QUE par la position d'UNE unite, a stats
identiques. Si la victime (la cible a 0 coup) BASCULE d'un regime a l'autre cote NATIF, l'ordre natif
depend de la GEOMETRIE, donc du tie-break d'enumeration, et non d'une stat de la cible.

Usage : python probe_494_doombolt_sort_order.py [--regime A|B|C] [--seed 777] [--board MC1_67]
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo
import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from engine.battle_query import iterate_surrounding_tiles_order_key   # noqa: E402
from engine.entities.pathfinding.board import Board                   # noqa: E402
from engine.runner.abilities.behaviours.context import entities_from_state   # noqa: E402
from engine.runner.abilities.thousandsons import (DOOMBOLT_ID, doombolt_targets_selector,
                                                  doombolt_hits_distribution)   # noqa: E402
from engine.runner.components import StatsComponent                   # noqa: E402
from engine.runner.messages import ActiveAbilityMessage               # noqa: E402
from engine.runner.operations.damage_utility import (_target_utility, damage_utility_weights)  # noqa: E402,E501
from engine.runner.prng import IntBasedMersenneTwister                # noqa: E402
from engine.runner.runner import Runner                               # noqa: E402
from engine.runner.snapshot import load_state                         # noqa: E402

DOOMBOLT = 1102
AHRIMAN = "thousAhriman"
A_UNITS = "orksNob,orksWarboss,orksBigMek,orksRuntherd"

# Les trois regimes ne different QUE par des POSITIONS -- memes unites, memes stats, meme seed.
#   A = la geometrie qui a EXHIBE l'ecart (case-487 §8 : `orksRuntherd` a 3,5).
#   B = A avec `orksBigMek` DEPLACE de (2,4) a (2,3) : meme distance au caster, rang d'enumeration
#       different -> si le natif tranche par l'enumeration, la victime doit BASCULER.
#   C = A avec `orksWarboss` DEPLACE de (4,4) a (4,3) : troisieme point, meme forme.
REGIMES = {
    "A": {"orksNob": (3, 4), "orksWarboss": (4, 4), "orksBigMek": (2, 4), "orksRuntherd": (3, 5)},
    "B": {"orksNob": (3, 4), "orksWarboss": (4, 4), "orksBigMek": (2, 3), "orksRuntherd": (3, 5)},
    "C": {"orksNob": (3, 4), "orksWarboss": (4, 3), "orksBigMek": (2, 4), "orksRuntherd": (3, 5)},
}
CASTER_POS = (3, 3)


def _rpc(sid, m, b=None, t=60):
    r = R._rpc(sid, m, [b] if b is not None else [], timeout=t)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _build(state_file, seed, board, extra):
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", state_file, *extra]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    sf = Path(state_file)
    if not sf.exists():
        return None, (p.stderr or p.stdout or "")[-1500:]
    return json.loads(sf.read_text())["runnerId"], None


def _live_hits(res, ability):
    """[(target_id, amount)] des coups de `ability` DANS L'ORDRE des evenements du cast."""
    out = []
    for a in (res.get("actions") or []):
        for e in (a.get("events") or []):
            td = e.get("tags")
            if isinstance(td, str):
                td = json.loads(td)
            if not td:
                continue
            if td.get("Active_Ability_Type") == ability and "Amount" in td:
                out.append((td["Target_Id"], td["Amount"]))
    return out


def counts(seq):
    out = {}
    for tid, _a in seq:
        out[tid] = out.get(tid, 0) + 1
    return out


def _first_seen(seq):
    """L'ordre des cibles tel que le natif les a JOUEES (premiere apparition)."""
    out = []
    for tid, _a in seq:
        if tid not in out:
            out.append(tid)
    return out


def _stat(state, uid, name):
    e = state.get_entity(uid)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return None
    return getattr(sc, name, None)


def run(regime: str = "A", seed: str = "777", board_id: str = "MC1_67",
        state_file: str | None = None, keep: bool = False, verbose: bool = False) -> dict:
    places = REGIMES[regime]
    sf = state_file or str(Path(__file__).resolve().parents[2] / "logs" / "runners"
                           / ("probe-494-doombolt-%s.json" % regime))
    Path(sf).parent.mkdir(parents=True, exist_ok=True)
    sid = R._resolve_session()
    extra = ["--p-units", AHRIMAN, "--a-units", A_UNITS,
             "--place", "%s:%d,%d" % (AHRIMAN, CASTER_POS[0], CASTER_POS[1])]
    for vid, p in places.items():
        extra += ["--a-place", "%s:%d,%d" % (vid, p[0], p[1])]
    # `--hp-target/--hp-player` EGALISENT les PV **et mettent Armor/FixedArmor a 0** (cf. rl_duel) :
    # c'est ce qui rend le regime lisible -- aucune stat de cible ne peut alors discriminer.
    extra += ["--hp-target", "400000", "--hp-player", "400000", "--no-ai"]
    rid, err = _build(sf, seed, board_id, extra)
    if rid is None:
        return {"error": "build KO: " + str(err)}
    out: dict = {"rid": rid, "regime": regime, "seed": seed, "board": board_id, "places": places}
    try:
        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            return {"error": "boardGraph indispo"}
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        ahri = next((u for u in units if u.get("visualId") == AHRIMAN), None)
        if ahri is None:
            return {"error": "Ahriman absent du build"}
        ens = [u for u in units if u.get("owner") != ahri.get("owner")]
        if len(ens) < 4:
            return {"error": "moins de 4 ennemis vivants"}
        ap = (ahri["pos"]["col"], ahri["pos"]["row"])
        for u in ens:
            if hexgeo.distance((u["pos"]["col"], u["pos"]["row"]), ap) > 2:
                return {"error": "ennemi u%s hors portee (d>2) -- geometrie non montee" % u["id"]}
        # cible du message = la plus proche du caster (comme probe_487)
        target = sorted(ens, key=lambda u: (hexgeo.distance((u["pos"]["col"], u["pos"]["row"]), ap),
                                            u["id"]))[0]

        ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 40)
        s0 = _rpc(sid, "dumpRng", {"runnerId": rid}, 30)
        if not (isinstance(s0, dict) and s0.get("ok")):
            return {"error": "dumpRng KO: " + str(s0)[:200]}

        # --- LIVE ---------------------------------------------------------------------------------
        res = _rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": ahri["id"], "targetId": target["id"],
            "abilityType": DOOMBOLT}}, 90)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        if not (isinstance(res, dict) and res.get("ok") and a0.get("ok")):
            return {"error": "cast Doombolt KO: " + str(res)[:250]}
        live = _live_hits(res, DOOMBOLT)

        # --- OFFLINE : meme etat, meme MT -----------------------------------------------------------
        st = load_state(dv, ob, snap, board=board)
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        st.rng = rng
        # etage 1 : l'ORDRE SOURCE du selecteur, AVANT tout tri
        ents = entities_from_state(st, ahri["id"], target["id"])
        cand = [u for u in (doombolt_targets_selector().evaluate(ents) or [])
                if isinstance(u, dict) and u.get("id") is not None]
        source_order = [int(u["id"]) for u in cand]
        # etage 0 : le REGIME
        regime_rows = []
        for u in ens:
            p = (u["pos"]["col"], u["pos"]["row"])
            regime_rows.append({
                "id": u["id"], "visualId": u.get("visualId"), "pos": p,
                "d": hexgeo.distance(p, ap), "cube_key": iterate_surrounding_tiles_order_key(p),
                "hp": u.get("hp"), "maxHp": u.get("maxHp"),
                "armor": _stat(st, u["id"], "armor"),
                "fixed_armor": _stat(st, u["id"], "fixed_armor")})
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=ahri["id"], target_id=target["id"],
                                          ability_type=DOOMBOLT))
        diag = runner.ability_handler.last or {}
        off = []
        for a in (diag.get("attacks") or []):
            off += [(a["target"], h) for h in ((a.get("attack") or {}).get("per_hit") or [])]
        # etage 2 : l'utilite portee par cible (memes arguments que le tri)
        wt = damage_utility_weights()
        st2 = load_state(dv, ob, snap, board=board)
        dmin = None
        for a in (diag.get("attacks") or []):
            pass
        util = {}
        try:
            from engine.entities.effects.magnitude import ability_var
            from engine.runner.abilities.thousandsons import _ability_state
            level, mult = _ability_state(st2, ahri["id"])
            dmin = int(ability_var(DOOMBOLT_ID, "minDmg", level, multiplier_pct=mult) or 0)
            util = {int(u["id"]): _target_utility(st2, int(u["id"]), dmin, dmin, wt) for u in ens}
        except Exception as exc:                                   # pragma: no cover - diagnostic
            util = {"error": str(exc)}
        out.update(caster=ahri["id"], caster_pos=ap, target=target["id"], regime_rows=regime_rows,
                   source_order=source_order, util=util, dmin=dmin,
                   port_order=diag.get("targets"), port_hits=diag.get("hits"),
                   total_hits=diag.get("total_hits"),
                   live=live, off=off, live_counts=counts(live), off_counts=counts(off),
                   live_order=_first_seen(live), off_order=_first_seen(off))
        if verbose:
            _print(out)
        return out
    finally:
        if not keep:
            subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", sf],
                           cwd=str(PYDIR), capture_output=True, text=True)


def _print(r):
    print("runner %s | regime %s | board %s | seed %s" % (r["rid"], r["regime"], r["board"],
                                                          r["seed"]))
    print("caster u%s @%s | cible du message u%s" % (r["caster"], r["caster_pos"], r["target"]))
    print("\n--- etage 0 : REGIME (ce que l'utilite peut voir) ---")
    print("%-6s %-16s %-8s %-3s %-10s %-8s %-8s %-7s %-7s"
          % ("id", "visualId", "pos", "d", "cube_key", "hp", "maxHp", "armor", "fixArm"))
    for w in r["regime_rows"]:
        print("%-6s %-16s %-8s %-3s %-10s %-8s %-8s %-7s %-7s"
              % (w["id"], w["visualId"], "%d,%d" % w["pos"], w["d"], "%d,%d" % w["cube_key"],
                 w["hp"], w["maxHp"], w["armor"], w["fixed_armor"]))
    vals = {w["id"]: (w["hp"], w["maxHp"], w["armor"], w["fixed_armor"]) for w in r["regime_rows"]}
    print("REGIME EGALISE (hp/maxHp/armor/fixedArmor identiques) : %s"
          % ("OUI" if len(set(vals.values())) == 1 else "NON -- %s" % sorted(set(vals.values()))))
    print("\n--- etage 1 : ORDRE SOURCE du port (GetTargets, avant tri) ---")
    print("  %s" % r["source_order"])
    print("--- etage 2 : UTILITE portee par cible (dmin=dmax=%s) ---" % r["dmin"])
    if isinstance(r["util"], dict) and "error" not in r["util"]:
        for k in sorted(r["util"]):
            print("  u%-4s %.10f" % (k, r["util"][k]))
        print("  TOUTES EGALES : %s" % ("OUI" if len(set("%.12f" % v for v in r["util"].values()))
                                        == 1 else "NON"))
    else:
        print("  %s" % r["util"])
    print("--- etage 3 : ORDRE FINAL du PORT ---")
    print("  ordre  = %s" % r["port_order"])
    print("  coups  = %s (N=%s)" % (r["port_hits"], r["total_hits"]))
    print("  frappe = %s" % r["off_counts"])
    print("--- etage 4 : ORDRE FINAL du NATIF (sequence d'evenements live) ---")
    print("  ordre joue = %s" % r["live_order"])
    print("  frappe     = %s" % r["live_counts"])
    print("  per-coup   = %s" % r["live"])
    live_zero = [w["id"] for w in r["regime_rows"] if w["id"] not in r["live_counts"]]
    off_zero = [w["id"] for w in r["regime_rows"] if w["id"] not in r["off_counts"]]
    print("\nVICTIME (0 coup) : NATIF %s | PORT %s -- %s"
          % (live_zero, off_zero, "ACCORD" if live_zero == off_zero else "DIVERGENCE"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regime", default="A", choices=sorted(REGIMES))
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    r = run(regime=a.regime, seed=a.seed, board_id=a.board, state_file=a.state_file,
            keep=a.keep, verbose=True)
    if "error" in r:
        print("ERREUR:", r["error"])
        raise SystemExit(2)
    live_zero = [w["id"] for w in r["regime_rows"] if w["id"] not in r["live_counts"]]
    off_zero = [w["id"] for w in r["regime_rows"] if w["id"] not in r["off_counts"]]
    raise SystemExit(0 if live_zero == off_zero else 1)


if __name__ == "__main__":
    main()
