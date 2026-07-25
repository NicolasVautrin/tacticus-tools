"""Probe #90 lot A — les 3 abilities MoW a PREDICAT DE CIBLAGE conditionnel.

Monte la scene qui REMPLIT le predicat natif de chaque ability, puis confronte le port a la cascade
native (`applyAction`) :

  * `SquigLaunchas` (1200, orksRukkatrukk) — `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$GetDynamicInvalidTargetReason` :
    >= 1 Ork allie-du-caster OU >= 2 allies adjacents a la cible. Le SUMMON a des seuils PLUS HAUTS
    (`IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$FulfillsSummonCriteria` : 2 Orks / 4 allies) -> scenario DISCRIMINANT en 2 temps.
  * `HadesAutocannons` (1147, blackForgefiend) — cible = **SUMMON ennemi** (TargetingOptions du IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$.ctor + `IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets` `UnitsWithTrait(2=Summon)`) -> on fait invoquer l'adversaire.
  * `EntropyCannons` (1168, deathCrawler) — `IdunBattleLogic.Entities.Abilities.Active.EntropyCannonsAbility$$GetDynamicInvalidTargetReason` : cible dans une
    aura Contagion ALLIEE (effet 1071) OU FixedArmor negativement modifiee.

Usage (depuis scripts/python) :
    python probe_mow_targeting_predicate.py squig|hades|entropy [--stage N]
ASCII only (cp1252). Discipline runner : state-file ABSOLU unique, dispose en fin de passe.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
HOST = "http://127.0.0.1:8765"
AGENT = "a24478d7"
STATE = ROOT / "data" / f"_solver90a_{AGENT}.json"


def _sid() -> int:
    with urllib.request.urlopen(f"{HOST}/api/admin/status", timeout=20) as r:
        return json.loads(r.read())["session"]["id"]


def rpc(method: str, arg=None, timeout: int = 90):
    body = json.dumps({"method": method, "args": [arg] if arg is not None else [],
                       "timeout": timeout * 1000}).encode()
    req = urllib.request.Request(f"{HOST}/api/scripts/{_sid()}/rpc", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout + 30) as r:
        out = json.loads(r.read())
    return out.get("result", out)


def build(p_units: str, a_units: str, board: str, seed: str = "4242",
          p_mow: str | None = None, a_mow: str | None = None) -> int:
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
           "--p-units", p_units, "--a-units", a_units, "--state-file", str(STATE)]
    if p_mow:
        cmd += ["--p-mow", p_mow]
    if a_mow:
        cmd += ["--a-mow", a_mow]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not STATE.exists():
        raise SystemExit(f"build KO: {(proc.stderr or proc.stdout)[-600:]}")
    return json.loads(STATE.read_text())["runnerId"]


def dispose(rid: int):
    try:
        rpc("disposeRunner", {"runnerId": rid}, 30)
    except Exception as exc:                                     # noqa: BLE001
        print("dispose KO:", exc)


def view(rid: int):
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    return dec, ob


def units_line(ob):
    return [(u.get("squadId"), u.get("visualId"), u.get("teamId"), (u.get("col"), u.get("row")),
             u.get("hp"), u.get("isDead")) for u in (ob.get("units") or [])]


def mow_of(dec, vid):
    return next((m for m in (dec.get("mows") or []) if m.get("visualId") == vid), None)


def targets_of(rid, caster, ability):
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": caster, "abilityType": ability}) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster), None)
    if row is None:
        return []
    for a in (row.get("abilities") or []):
        if a.get("abilityType") in (ability, None):
            return a.get("targets") or []
    return []


def move(rid, uid, col, row):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": col, "row": row}}})


def cast(rid, caster, ability, target_id=None, to=None):
    act = {"kind": "ability", "casterId": caster, "abilityType": ability}
    if target_id is not None:
        act["targetId"] = target_id
    if to is not None:
        act["to"] = {"col": to[0], "row": to[1]}
    return rpc("applyAction", {"runnerId": rid, "action": act})


# --------------------------------------------------------------------------- scenarios

def scenario_squig(args):
    """orksRukkatrukk (MoW joueur) + 2 Orks + 1 non-Ork vs 1 ennemi tanky."""
    rid = build("orksNob,orksBigMek,necroDestroyer", "ultraTitus", "C1_02",
                seed=args.seed, p_mow="orksRukkatrukk")
    print("runner", rid)
    try:
        dec, ob = view(rid)
        m = mow_of(dec, "orksRukkatrukk")
        print("mow", m and {k: m[k] for k in ("casterId", "team", "slot")})
        print("units", units_line(ob))
        cid = m["casterId"]
        print("targets@spawn 1200:", targets_of(rid, cid, 1200))
        enemy = next(u for u in ob["units"] if u["teamId"] != m["team"] and not u.get("isDead"))
        print("enemy", enemy["squadId"], enemy["visualId"], (enemy["col"], enemy["row"]))
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        tiles = {t["id"]: t for t in bg["tiles"]}
        byrc = {(t["col"], t["row"]): t for t in bg["tiles"]}
        occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")}
        # DRIVE POSITIONS : amener l'ennemi sur une tuile a >= 4 voisins LIBRES et marchables, sans quoi
        # le `CanAddUnit(AdjacentTiles(target))` du spawn est vide des que 2 Orks occupent les 2 voisins.
        best = max((t for t in bg["tiles"] if t.get("walkable", True)
                    and (t["col"], t["row"]) not in occ),
                   key=lambda t: sum(1 for n in t["neighbours"]
                                     if n in tiles and tiles[n].get("walkable", True)
                                     and (tiles[n]["col"], tiles[n]["row"]) not in occ))
        r = move(rid, enemy["squadId"], best["col"], best["row"])
        print("move enemy ->", (best["col"], best["row"]), (r.get("actions") or [{}])[0].get("error"))
        _dec, ob = view(rid)
        enemy = next(u for u in ob["units"] if u["squadId"] == enemy["squadId"])
        et = byrc[(enemy["col"], enemy["row"])]
        occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")}
        free_adj = [tiles[n] for n in et["neighbours"]
                    if n in tiles and (tiles[n]["col"], tiles[n]["row"]) not in occ
                    and tiles[n].get("walkable", True)]
        print("free adj to enemy:", [(t["col"], t["row"]) for t in free_adj])
        orks = [u for u in ob["units"] if u["visualId"] in ("orksNob", "orksBigMek")]
        for u, t in zip(orks[:args.n_orks], free_adj):
            r = move(rid, u["squadId"], t["col"], t["row"])
            print("move", u["visualId"], "->", (t["col"], t["row"]),
                  (r.get("actions") or [{}])[0].get("error"))
            _dec, ob2 = view(rid)
            print("  targets 1200 now:", [(x.get("targetId"), x.get("kind")) for x in targets_of(rid, cid, 1200)])
            ob = ob2
        print("units after moves", units_line(ob))
        if args.cast:
            before = {u["squadId"] for u in ob["units"]}
            r = cast(rid, cid, 1200, target_id=enemy["squadId"])
            print("cast 1200:", (r.get("actions") or [{}])[0].get("error"), "mutated=", r.get("mutated"))
            _dec, ob3 = view(rid)
            print("units after cast", units_line(ob3))
            new = [u for u in ob3["units"] if u["squadId"] not in before]
            print("NEW units:", [(u["squadId"], u["visualId"], u["teamId"], (u["col"], u["row"]), u["hp"])
                                 for u in new])
    finally:
        if not args.keep:
            dispose(rid)


def scenario_hades(args):
    """blackForgefiend (MoW joueur) vs summoners adverses (Poxwalkers + Scarab Hive = summons ennemis)."""
    rid = build("necroDestroyer", "deathBlightbringer,necroSpyder", "C1_02", seed=args.seed,
                p_mow="blackForgefiend")
    print("runner", rid)
    try:
        dec, ob = view(rid)
        m = mow_of(dec, "blackForgefiend")
        print("mow", m and {k: m[k] for k in ("casterId", "team", "slot")})
        print("units", units_line(ob))
        cid = m["casterId"]
        print("targets@spawn 1147:", targets_of(rid, cid, 1147))
        bb = next((u for u in ob["units"] if u["visualId"] == "deathBlightbringer"), None)
        sp = next((u for u in ob["units"] if u["visualId"] == "necroSpyder"), None)
        me = next(u for u in ob["units"] if u["teamId"] == m["team"] and not u.get("isDead"))
        # DRIVE POSITIONS : amener les summoners adverses AU CONTACT de ma unite (le ScarabHive spawn
        # adjacent a SA cible -> les 2 swarms seront groupes autour d'elle, donc <= 2 hex l'un de l'autre).
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        tiles = {t["id"]: t for t in bg["tiles"]}
        byrc = {(t["col"], t["row"]): t for t in bg["tiles"]}
        occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")}
        mt = byrc[(me["col"], me["row"])]
        free_adj = [tiles[n] for n in mt["neighbours"]
                    if n in tiles and (tiles[n]["col"], tiles[n]["row"]) not in occ
                    and tiles[n].get("walkable", True)]
        for u, t in zip([x for x in (sp, bb) if x is not None], free_adj):
            r = move(rid, u["squadId"], t["col"], t["row"])
            print("move", u["visualId"], "->", (t["col"], t["row"]),
                  (r.get("actions") or [{}])[0].get("error"))
        _dec, ob = view(rid)
        if bb is not None:
            r = cast(rid, bb["squadId"], 1040, target_id=bb["squadId"])
            print("poxwalkers cast:", (r.get("actions") or [{}])[0].get("error"))
        if sp is not None:
            r = cast(rid, sp["squadId"], 1007, target_id=me["squadId"])
            print("scarabhive cast:", (r.get("actions") or [{}])[0].get("error"))
        dec, ob = view(rid)
        print("units after summon", units_line(ob))
        tg = targets_of(rid, cid, 1147)
        print("targets 1147 after summon:", [(x.get("targetId"), x.get("kind")) for x in tg])
        if args.cast and tg:
            tid = tg[0]["targetId"]
            before = {u["squadId"]: u["hp"] for u in ob["units"]}
            r = cast(rid, cid, 1147, target_id=tid)
            print("cast 1147 on", tid, ":", (r.get("actions") or [{}])[0].get("error"))
            _dec, ob2 = view(rid)
            print("hp delta:", {u["squadId"]: (before.get(u["squadId"]), u["hp"])
                                for u in ob2["units"] if before.get(u["squadId"]) != u["hp"]})
            print("units after cast", units_line(ob2))
    finally:
        if not args.keep:
            dispose(rid)


def scenario_entropy(args):
    """deathCrawler (MoW joueur) + deathTyphus (aura ContagionsOfNurgle) vs 1 ennemi."""
    rid = build("deathTyphus,deathPutrifier", "ultraTitus", "C1_02", seed=args.seed,
                p_mow="deathCrawler")
    print("runner", rid)
    try:
        dec, ob = view(rid)
        m = mow_of(dec, "deathCrawler")
        print("mow", m and {k: m[k] for k in ("casterId", "team", "slot")})
        print("units", units_line(ob))
        cid = m["casterId"]
        print("targets@spawn 1168:", targets_of(rid, cid, 1168))
        enemy = next(u for u in ob["units"] if u["teamId"] != m["team"] and not u.get("isDead"))
        typhus = next(u for u in ob["units"] if u["visualId"] == "deathTyphus")
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        tiles = {t["id"]: t for t in bg["tiles"]}
        byrc = {(t["col"], t["row"]): t for t in bg["tiles"]}
        et = byrc[(enemy["col"], enemy["row"])]
        occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")}
        free_adj = [tiles[n] for n in et["neighbours"]
                    if n in tiles and (tiles[n]["col"], tiles[n]["row"]) not in occ
                    and tiles[n].get("walkable", True)]
        if free_adj:
            t = free_adj[0]
            r = move(rid, typhus["squadId"], t["col"], t["row"])
            print("move typhus ->", (t["col"], t["row"]), (r.get("actions") or [{}])[0].get("error"))
        dec, ob = view(rid)
        print("units", units_line(ob))
        print("targets 1168 after typhus adjacent:",
              [(x.get("targetId"), x.get("kind")) for x in targets_of(rid, cid, 1168)])
        eff = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}).get("effects")
        print("effects:", json.dumps(eff)[:600] if eff else None)
    finally:
        if not args.keep:
            dispose(rid)


def scenario_decomp(args):
    """DECOMPOSITION PAR ETAGE d'une divergence de degat MoW (jamais fitter un scalaire) : monte la
    scene (3 allies NON-Orks au contact d'astraBullgryn), rejoue le cast OFFLINE avec le RNG LIVE et
    imprime CHAQUE etage (bornes config, percage, armure, rolls bruts, valeur par coup), puis joue le
    cast LIVE et imprime le delta PV reel. Sert a localiser l'etage divergent."""
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import HealthComponent
    from engine.runner.operations.summon_ai import _apply_active_ability
    from engine.entities.pathfinding.board import Board
    rid = build("necroDestroyer,necroWarden,ultraTitus", "astraBullgryn", "C1_02",
                seed=args.seed, p_mow="orksRukkatrukk")
    print("runner", rid)
    try:
        dec, ob = view(rid)
        m = mow_of(dec, "orksRukkatrukk")
        cid = m["casterId"]
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        tiles = {t["id"]: t for t in bg["tiles"]}
        enemy = next(u for u in ob["units"] if u["teamId"] != m["team"] and not u.get("isDead"))
        occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")}
        best = max((t for t in bg["tiles"] if t.get("walkable", True)
                    and (t["col"], t["row"]) not in occ),
                   key=lambda t: sum(1 for n in t["neighbours"]
                                     if n in tiles and tiles[n].get("walkable", True)
                                     and (tiles[n]["col"], tiles[n]["row"]) not in occ))
        move(rid, enemy["squadId"], best["col"], best["row"])
        _dec, ob = view(rid)
        enemy = next(u for u in ob["units"] if u["squadId"] == enemy["squadId"])
        et = tiles[[t["id"] for t in bg["tiles"]
                    if (t["col"], t["row"]) == (enemy["col"], enemy["row"])][0]]
        occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")}
        free = [tiles[n] for n in et["neighbours"]
                if n in tiles and (tiles[n]["col"], tiles[n]["row"]) not in occ
                and tiles[n].get("walkable", True)]
        allies = [u for u in ob["units"] if u["teamId"] == m["team"] and not u.get("isDead")]
        for u, t in zip(allies, free):
            move(rid, u["squadId"], t["col"], t["row"])
        print("targets:", [(x.get("targetId"), x.get("kind")) for x in targets_of(rid, cid, 1200)])

        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        ob0 = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        board = Board(bg["tiles"], adjacency="evenq")
        state = load_state(dec, ob0, snap, board=board)
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        state.rng = rng
        hp0 = state.get_entity(enemy["squadId"]).get_component(HealthComponent).hp
        if args.stage:
            # ETAGE PAR ETAGE : on appelle l'Operation DIRECTEMENT (meme args que la feuille DSL) pour
            # voir bornes/percage/armure/rolls/valeur-par-coup au lieu du seul total.
            from engine.runner.abilities.base import ability_attack_params
            from engine.runner.operations.damage import AttackDamageOperation
            bmin, bmax, pierce, hits = ability_attack_params(
                state, cid, "SquigLaunchas", "Physical", ranged=True)
            print("STAGE bornes:", bmin, bmax, "pierce:", pierce, "hits:", hits)
            atk = AttackDamageOperation.execute_ability_attack(
                state, cid, enemy["squadId"], bmin, bmax, pierce, hits,
                damage_profile="Physical", is_melee=None, is_attack_damage_op=False,
                ability_type=1200)
            print("STAGE atk:", json.dumps({k: atk[k] for k in
                                            ("hits", "total", "pierce", "armor", "rolls", "per_hit",
                                             "crits", "did_block")}, default=str))
            diag = {"attacks": [{"target": enemy["squadId"], "total": atk["total"]}]}
        else:
            res = _apply_active_ability(state, cid, enemy["squadId"], 1200)
            diag = (res or {}).get("diag") or {}
        hp1 = state.get_entity(enemy["squadId"]).get_component(HealthComponent).hp
        print("OFFLINE diag:", json.dumps(diag, default=str)[:900])
        print("OFFLINE hp:", hp0, "->", hp1, "delta", hp0 - hp1)
        r = cast(rid, cid, 1200, target_id=enemy["squadId"])
        print("cast:", (r.get("actions") or [{}])[0].get("error"))
        _dec, ob1 = view(rid)
        lv = next(u for u in ob1["units"] if u["squadId"] == enemy["squadId"])
        print("LIVE hp:", enemy["hp"], "->", lv["hp"], "delta", enemy["hp"] - lv["hp"])
    finally:
        if not args.keep:
            dispose(rid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=["squig", "hades", "entropy", "decomp"])
    ap.add_argument("--seed", default="4242")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--n-orks", type=int, default=2, help="nb d'Orks amenes au contact (squig)")
    ap.add_argument("--cast", action="store_true", help="caster l'ability apres la mise en scene")
    ap.add_argument("--stage", action="store_true", help="decomposition par etage (decomp)")
    args = ap.parse_args()
    {"squig": scenario_squig, "hades": scenario_hades, "entropy": scenario_entropy,
     "decomp": scenario_decomp}[args.scenario](args)


if __name__ == "__main__":
    main()
