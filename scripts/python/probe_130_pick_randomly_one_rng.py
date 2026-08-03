"""PROBE case-130 SS4 -- le helper `_pick_randomly` (n = 1) consomme-t-il un `genrand_int32` ?

RESIDU NOMME de #130 : la LOI est close (`PickRandomAmountSelector$$Select` tire
`min(len(pool), amount)` fois, AUCUN court-circuit « le pool tient »), mais le helper frere n = 1
(`operations/triggers/base.py`, `operations/spawn.py`) court-circuitait encore a `len(pool) == 1`.

MESURE DIRECTE (pas un fit de scalaire) : on compte le NOMBRE EXACT de `genrand_int32` consommes
LIVE par une attaque normale RANGED PSYCHIQUE d'un porteur du trait Psyker -- dont le splash
`PsykerExtraAttackAbility` resout sa cible par
`PickRandomly(Damageable(Enemies(caster, AdjacentUnits(target@0x178, 1, 3))), 1, 0, 0x7fffffff, false)`
-- et on le compare au nombre consomme par le PORT sur le MEME etat seede, sous DEUX modeles :
    M0 « court-circuit a pool == 1 »  (le port d'AVANT)
    M1 « min(len(pool), 1) tirage »   (le DECOMPILE / le port d'APRES)

Comptage LIVE : `dumpRng` AVANT/APRES rend l'etat complet du Mersenne Twister (`mt[624]`, `mti`) ;
on re-simule l'etat AVANT pas a pas jusqu'a retrouver l'etat APRES -> le nombre de pas EST le nombre
de tirages. Ce compteur voit TOUT (un comptage d'events sous-estimerait -- piege #125).

TROIS REGIMES -- k = nb d'ennemis adjacents a la cible primaire (= |pool| du pick) :
    k = 0 : le pick n'a AUCUN candidat -> le splash ne fire pas. BASELINE : isole ce que consomme
            l'attaque principale seule, donc tout ecart CONSTANT etranger au pick.
    k = 1 : M0 saute le tirage, M1 le consomme -> les deux modeles DIVERGENT de 1.
    k = 2 : M0 et M1 tirent tous les DEUX une fois (borne 2) -> CONTROLE, ils coincident.
Le discriminant est le DIFFERENTIEL k=1 vs k=2 : si le natif ne tirait pas quand le pool tient,
`live(k=1)` vaudrait `live(k=2) - 1`. Un seul regime ne separerait rien.

MESURE (build gqfc5mff6c) -- identique sur `seed 777 / MC1_67`, `seed 31337 / MC1_67` et
`seed 777 / C2_37`, avec des degats principaux differents a chaque fois (3336 / 2984 / 4278, donc de
vrais etats PRNG distincts) :

    k=0 : LIVE 1 | port corrige 1 | port court-circuite 1
    k=1 : LIVE 3 | port corrige 2 | port court-circuite 1
    k=2 : LIVE 3 | port corrige 2 | port court-circuite 2

`live(k=1) == live(k=2)` -> le natif tire autant avec un pool de 1 qu'avec un pool de 2 : le
court-circuit est REFUTE. Le port corrige reproduit ce contraste, pas le court-circuite.
A k=0 le port est EXACT -> l'ecart constant de 1 tirage des que le splash fire etait etranger au
pick : c'etait le resolve slot-8 (`DamagePrediction$$RandomlyResolveMinMaxDamage`, `Next(v, v+1)`
sans gate largeur-1) que `HitDamage.get_damage` court-circuite a `min == max`.

⚠ CE RESIDU EST FERME depuis `70dc9769` (#221, 2026-07-29), qui a porte le resolve sur la branche
reduce-then-roll de `_run_hits`, gate par la FAMILLE (`is_attack_damage_op` -- le smite est de la
famille ATTACK). MESURE du 2026-08-03, meme vecteur : delta live-port = **0** aux trois regimes.
Le contrat du test est donc l'EGALITE, plus un ecart fige (#462-r6).

Usage :  python probe_130_pick_randomly_one_rng.py [--seed 777] [--board MC1_67]
Depuis scripts/python. ASCII only. Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

CASTER_VIS = "astraPrimarisPsy"
# Meme cluster que `test_psyker_splash_live` (fixture validee bit-exact live/offline sur ce vecteur).
A_UNITS = "darkaCompanion,tyranWingedPrime,ultraInceptorSgt,spaceBlackmane,necroSpyder"
BOARD = "MC1_67"          # surchargeable par --board (generalisation : autre geometrie)


class Rpc:
    """Meme voie que la conftest : `rl_collect_batch._rpc(sid, method, [body], timeout_s)`."""

    def __init__(self):
        import rl_collect_batch as R
        self.R = R
        self.sid = R._resolve_session()

    def __call__(self, method, args=None, timeout=60):
        out = self.R._rpc(self.sid, method, [args] if args is not None else [], timeout=timeout)
        return out.get("result") if isinstance(out, dict) and "result" in out else out


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


# ------------------------------------------------------------------ comptage des genrand

def count_genrand(before, after, cap=400):
    """Nombre de `genrand_int32` entre deux etats (mt, mti) du MT natif -- par re-simulation."""
    from engine.runner.prng import IntBasedMersenneTwister
    r = IntBasedMersenneTwister()
    r.mt = list(before["mt"]); r.mti = int(before["mti"])
    tgt_mt, tgt_mti = list(after["mt"]), int(after["mti"])
    for n in range(cap + 1):
        if r.mti == tgt_mti and r.mt == tgt_mt:
            return n
        r.genrand_int32()
    return None


class CountingRng:
    """Compteur de `genrand_int32` cote PORT (cf. `probe_215_pick_randomly_rng.py`)."""

    def __init__(self, mt, mti):
        from engine.runner.prng import IntBasedMersenneTwister
        self.r = IntBasedMersenneTwister()
        self.r.mt = list(mt); self.r.mti = int(mti)
        self.n = 0

    def genrand_int32(self):
        self.n += 1
        return self.r.genrand_int32()

    def genrand_real2(self):
        self.n += 1
        return self.r.genrand_real2()

    def __getattr__(self, k):
        return getattr(self.r, k)

    def next_internal(self, lo, hi):
        from engine.runner.prng import _i32
        rng = hi - lo
        if (-rng & rng) == rng:
            return ((rng * (self.genrand_int32() >> 1)) >> 31) + lo
        while True:
            v0 = self.genrand_int32() >> 1
            v = v0 % rng
            if _i32((rng - 1) + (v0 - v)) >= 0:
                return v + lo

    def next(self, bound):
        return self.next_internal(0, bound)

    def next_bool(self, chance):
        return self.next_internal(1, 100) <= chance


def _legacy_pick_randomly(state, candidates):
    """Le helper d'AVANT (court-circuit `n == 1`) -- reproduit ICI pour le modele M0, jamais importe."""
    cands = sorted(candidates)
    n = len(cands)
    if n == 0:
        return None
    if n == 1 or state.rng is None:
        return cands[0]
    return cands[state.rng.next_internal(0, n)]


# ------------------------------------------------------------------ scenario live

def build(seed, state_file):
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(state_file),
         "--board", BOARD, "--roster", "1", "--p-units", CASTER_VIS, "--a-units", A_UNITS,
         "--hp-target", "90000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-500:])
        return None
    return json.loads(state_file.read_text())["runnerId"]


def run_regime(rpc, seed, k_adj):
    """Monte la geometrie « cible primaire RANGED avec EXACTEMENT k_adj ennemis adjacents », caste
    LIVE l'attaque normale, et rend l'etat AVANT + les compteurs."""
    import hexgeo
    from engine.entities.pathfinding.board import Board

    state_file = ROOT / "logs" / "runners" / f"probe130b-{uuid.uuid4().hex[:8]}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    rid = build(seed, state_file)
    if rid is None:
        return None
    out = {"rid": rid, "state_file": state_file, "k": k_adj}
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        print("boardGraph indispo"); return out
    tiles = bg["tiles"]
    elev = {(t["col"], t["row"]): t.get("elevation") for t in tiles}
    board = Board(tiles, adjacency="evenq")      # adjacence FIDELE (cf. test_psyker_splash_live)

    def mv(uid, tid):
        c = board.coord(tid)
        return rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 60)

    def psy_of(dv):
        return next((u for u in (dv.get("units") or [])
                     if u.get("visualId") == CASTER_VIS and u.get("alive")), None)

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    if not _ok(dv) or psy_of(dv) is None:
        print("psyker absent"); return out
    myplayer = psy_of(dv).get("owner")
    for _ in range(6):                            # attendre notre tour (et l'atterrissage eventuel)
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        if dv.get("currentPlayer") == myplayer:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    psy = psy_of(dv)
    if psy is None or dv.get("currentPlayer") != myplayer:
        print("pas notre tour / psyker absent"); return out
    cid = psy["id"]
    norm = next((ab for ab in (psy.get("abilities") or []) if ab.get("kind") == "normal"), None)
    if norm is None:
        print("ability normale introuvable"); return out
    norm_id = norm.get("id")
    cpos = (psy["pos"]["col"], psy["pos"]["row"])
    ctile = board.id_at(*cpos)
    eC = elev.get(cpos)

    enemies = [u for u in (dv.get("units") or []) if u.get("owner") != myplayer and u.get("alive")]
    if len(enemies) < 1 + k_adj:
        print("pas assez d'ennemis"); return out

    # 1) parquer TOUS les ennemis LOIN (>6 hexes) -> aucun voisin parasite de la cible.
    far = [t for t in sorted(board.by_id) if board.walkable(t)
           and hexgeo.distance(board.coord(t), cpos) > 6]
    for e, ft in zip(enemies, far):
        mv(e["id"], ft)

    # 2) chercher une tuile T a d=2 du psyker (RANGED : d<2 = arme melee, pas de trigger) avec
    #    assez de voisins libres pour y poser k ennemis, et ou le cast est LEGAL (fromHere).
    def from_here(unit_id, ability_id):
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": unit_id,
                                    "abilityType": ability_id}, 90)
        ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                   if a.get("abilityId") == ability_id), {})
        return [x.get("targetId") for x in (ab.get("fromHere") or [])]

    target = enemies[0]
    extras = enemies[1:1 + k_adj]
    cand = None
    for T in sorted(board.by_id):
        cT = board.coord(T)
        if not board.walkable(T) or T == ctile or hexgeo.distance(cT, cpos) != 2:
            continue
        if elev.get(cT) is None or eC is None or abs(elev.get(cT) - eC) > 1:
            continue
        nbrs = [n for n in board.neighbours(T)
                if board.walkable(n) and n != ctile
                and hexgeo.distance(board.coord(n), cpos) >= 2]
        if len(nbrs) < k_adj:
            continue
        mv(target["id"], T)
        if target["id"] in from_here(cid, norm_id):
            cand = (T, nbrs[:k_adj])
            break
        mv(target["id"], far[0])
    if cand is None:
        print("geometrie (cible d=2 + voisins libres) introuvable"); return out
    T, slots = cand
    for e, tid in zip(extras, slots):
        mv(e["id"], tid)

    # 3) le pool du pick DOIT valoir exactement k_adj (verifie sur l'etat charge)
    dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    if target["id"] not in from_here(cid, norm_id):
        print("cast illegal apres placement"); return out
    rng_before = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(rng_before):
        print("dumpRng KO"); return out

    cast = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": target["id"], "abilityType": norm_id},
        "captureEvents": True}, 120)
    if not _ok(cast):
        print("cast KO", str(cast)[:200]); return out
    rng_after = rpc("dumpRng", {"runnerId": rid}, 30)

    live = {}
    for act in (cast.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Target_Id") is not None:
                live.setdefault(td["Target_Id"], []).append(td["Amount"])

    out.update({"board": board, "dv": dv2, "ob": ob2, "snap": snap2, "cid": cid,
                "norm_id": norm_id, "target": target["id"],
                "extras": [e["id"] for e in extras], "live": live,
                "rng_before": rng_before, "rng_after": rng_after})
    return out


def port_draws(reg, legacy: bool):
    """Rejoue l'attaque normale par le PORT REEL, en modele M1 (helper courant) ou M0 (helper
    court-circuite, monkeypatche sur le SEUL consommateur psyker), et rend
    (nb genrand, per-hit par cible, pool du pick)."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.operations.triggers.loki import psyker as PS
    from engine.runner.operations.triggers.base import _adjacent_damageable_enemies

    st = load_state(reg["dv"], reg["ob"], reg["snap"], board=reg["board"])
    rng = CountingRng(reg["rng_before"]["mt"], reg["rng_before"]["mti"])
    st.rng = rng
    pool = _adjacent_damageable_enemies(st, reg["cid"], reg["target"])
    saved = PS._pick_randomly
    if legacy:
        PS._pick_randomly = _legacy_pick_randomly
    try:
        runner = Runner(st).install_default_handlers(20)
        runner.apply(AttackUnitMessage(reg["cid"], reg["target"]))
        dh = runner.damage_handler
        per = {reg["target"]: (dh.last or {}).get("per_hit")}
        for a in (dh.after_hit or []):
            if a.get("trait") == "Psyker":
                per[a["target"]] = (a.get("result") or {}).get("per_hit")
        return rng.n, per, pool
    finally:
        PS._pick_randomly = saved


def main():
    global BOARD
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default=BOARD)
    args = ap.parse_args()
    BOARD = args.board
    rpc = Rpc()
    print("session=%s seed=%s" % (rpc.sid, args.seed))

    results = []
    for k in (0, 1, 2):
        reg = run_regime(rpc, args.seed, k)
        if reg is None:
            print("REGIME k=%d : build KO" % k)
            continue
        try:
            if "rng_after" not in reg:
                print("REGIME k=%d : setup KO" % k)
                continue
            live_n = count_genrand(reg["rng_before"], reg["rng_after"])
            n1, per1, pool = port_draws(reg, legacy=False)
            n0, per0, _ = port_draws(reg, legacy=True)
            print("\n=== REGIME k=%d (target=%s extras=%s pool_offline=%s) ==="
                  % (k, reg["target"], reg["extras"], pool))
            print("  LIVE genrand consommes par l'attaque : %s" % live_n)
            print("  PORT M1 (min(k,1) tirage, DECOMPILE) : %-4s  delta live-port = %s"
                  % (n1, None if live_n is None else live_n - n1))
            print("  PORT M0 (court-circuit a k==1)       : %-4s  delta live-port = %s"
                  % (n0, None if live_n is None else live_n - n0))
            for tag, per in (("M1", per1), ("M0", per0)):
                for tid, ph in sorted(per.items()):
                    lp = reg["live"].get(tid)
                    role = "MAIN  " if tid == reg["target"] else "splash"
                    print("      %s %s %s: live=%s off=%s %s"
                          % (tag, role, tid, lp, ph, "OK" if lp == ph else "MISMATCH"))
            results.append({"k": k, "live": live_n, "m1": n1, "m0": n0, "pool": len(pool)})
        finally:
            try:
                rpc("disposeRunner", {"runnerId": reg["rid"]}, 20)
            except Exception:
                pass
            try:
                reg["state_file"].unlink()
            except Exception:
                pass

    print("\n=== VERDICT ===")
    for r in results:
        print("  k=%d |pool|=%d : live=%s  M1=%s (delta %s)  M0=%s (delta %s)"
              % (r["k"], r["pool"], r["live"], r["m1"],
                 None if r["live"] is None else r["live"] - r["m1"], r["m0"],
                 None if r["live"] is None else r["live"] - r["m0"]))
    print("  attendu : k=1 -> delta M1 = 0 et delta M0 = 1 ; k=2 -> delta M1 = delta M0 = 0")


if __name__ == "__main__":
    main()
