"""PROBE #130 / GAP #215 -- `PickRandomly` consomme-t-il du RNG quand le pool tient DEJA dans `n` ?

MESURE DIRECTE (pas un fit de scalaire) : on compte le NOMBRE EXACT de `genrand_int32` consommes
LIVE par un cast PlasmaCannon (1150, darkaTerminator), et on le compare au nombre consomme par le
PORT sur le MEME etat seede. La difference isole la consommation du selecteur
`IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select`.

Comptage LIVE : `dumpRng` AVANT/APRES le cast rend l'etat COMPLET du Mersenne Twister (`mt[624]`,
`mti`). On re-simule l'etat AVANT en avancant pas a pas jusqu'a retrouver l'etat APRES -> le nombre
de pas EST le nombre de `genrand_int32` consommes. Ce compteur voit TOUT (contraste le comptage
d'events, qui sous-estime : une sous-operation qui retourne tot n'emet rien -- piege #125).

DEUX REGIMES DISCRIMINANTS (le point de la mesure) -- k = nb d'unites directly-behind :
    k=1  et  k=2 , avec n = nrOfTargets du PickRandomly = 2 (donc pool <= n dans LES DEUX cas).
Modeles concurrents et leurs predictions de `delta = live_draws - port_draws(0-tirage)` :
    M0 « le natif ne roll pas quand le set tient » (port actuel) -> delta = 0 , 0
    M1 « min(k, n) tirages, bornes k, k-1, ... 1 »  (DECOMPILE)  -> delta = 1 , 2
    M2 « n tirages quoi qu'il arrive »                           -> delta = 2 , 2
    M3 « 1 tirage »                                              -> delta = 1 , 1
Un seul regime ne separerait rien (k=2 : M1==M2 ; k=1 : M1==M3). Il en faut DEUX.

Usage :  python probe_215_pick_randomly_rng.py [--seed 777]
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

CASTER_VIS = "darkaTerminator"
ABILITY = 1150
A_UNITS = "necroWarden,necroWarden,necroWarden,necroOverlord"


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


# ------------------------------------------------------------------ comptage LIVE des genrand

def count_genrand(before, after, cap=400):
    """Nombre de `genrand_int32` entre deux etats (mt, mti) du MT natif -- par re-simulation.
    Le port `IdunBattle.Utils.PRNG.MersenneTwister$$genrand_int32` est bit-exact, donc avancer
    l'etat AVANT reproduit exactement la trajectoire native. Renvoie None si non atteint sous `cap`
    (signe qu'autre chose a consomme un volume anormal)."""
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
    """Wrapper de comptage des `genrand_int32` du PORT (le compteur `call_count` natif melange
    genrand et Next -- inutilisable comme volume de tirages)."""

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
        # next_internal/next/next_bool passent par self.r mais appellent SON genrand -> on
        # re-route en recopiant la math sur ce wrapper (voir next_internal/next ci-dessous).
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


# ------------------------------------------------------------------ scenario live

def build(seed, state_file):
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(state_file),
         "--board", "MC1_67", "--roster", "1", "--p-units", CASTER_VIS, "--a-units", A_UNITS,
         "--hp-target", "90000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-400:])
        return None
    return json.loads(state_file.read_text())["runnerId"]


def run_regime(rpc, seed, k_behind):
    """Monte la geometrie PlasmaCannon avec EXACTEMENT `k_behind` unites directly-behind, caste LIVE,
    et rend {live per-hit par cible, rng avant/apres, ids, snapshots}."""
    import hexgeo
    from engine.entities.pathfinding.board import Board

    state_file = ROOT / "data" / "rl-state" / f"probe215-{uuid.uuid4().hex[:8]}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    rid = build(seed, state_file)
    if rid is None:
        return None
    out = {"rid": rid, "state_file": state_file, "k": k_behind}
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            print("boardGraph indispo"); return None
        tiles = bg["tiles"]
        elev = {(t["col"], t["row"]): t.get("elevation") for t in tiles}
        board = Board(tiles, adjacency="native_sym")

        def mv(uid, tid):
            c = board.coord(tid)
            return rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 60)

        def caster_of(dv):
            return next((u for u in (dv.get("units") or [])
                         if u.get("visualId") == CASTER_VIS and u.get("alive")), None)

        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        if not _ok(dv) or caster_of(dv) is None:
            print("caster absent"); return None
        myplayer = caster_of(dv).get("owner")
        landed = False
        for _ in range(6):
            dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
            c = caster_of(dv)
            if c is None:
                break
            tin = any("TeleportingIn" in (e.get("name") or "") for e in (c.get("effects") or []))
            if not tin and dv.get("currentPlayer") == myplayer:
                landed = True
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        if not landed:
            print("terminator non atterri"); return None

        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        caster = caster_of(dv)
        cid = caster["id"]
        cpos = (caster["pos"]["col"], caster["pos"]["row"])
        ctile = board.id_at(*cpos)
        eC = elev.get(cpos)
        enemies = [u for u in (dv.get("units") or []) if u.get("owner") != myplayer and u.get("alive")]
        if len(enemies) < 1 + k_behind:
            print("pas assez d'ennemis"); return None

        far = [t for t in sorted(board.by_id) if board.walkable(t)
               and hexgeo.distance(board.coord(t), cpos) > 6]
        for e, ft in zip(enemies, far):
            mv(e["id"], ft)

        cand = None
        for T in sorted(board.by_id):
            ct = board.coord(T)
            if not board.walkable(T) or T == ctile or hexgeo.distance(ct, cpos) != 2:
                continue
            if elev.get(ct) is None or eC is None or abs(elev.get(ct) - eC) > 1:
                continue
            nbrs = [n for n in board.neighbours(T) if board.walkable(n) and n != ctile]
            behind = [n for n in nbrs if hexgeo.distance(board.coord(n), cpos) == 3
                      and elev.get(board.coord(n)) is not None
                      and abs(elev.get(board.coord(n)) - elev.get(ct)) <= 1]
            if len(behind) >= 2:                      # MEME geometrie pour les 2 regimes
                mv(enemies[0]["id"], T)
                at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
                fh = [x.get("targetId") for x in
                      next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                            if a.get("abilityId") == ABILITY), {}).get("fromHere") or []]
                if enemies[0]["id"] in fh:
                    cand = (T, behind[:2])
                    break
                mv(enemies[0]["id"], far[0])
        if cand is None:
            print("geometrie directly-behind introuvable"); return None
        T, behind = cand
        target = enemies[0]
        # SEULES `k_behind` unites sont placees derriere ; les autres restent parquees LOIN.
        placed = []
        for i in range(k_behind):
            mv(enemies[1 + i]["id"], behind[i])
            placed.append(enemies[1 + i]["id"])

        at2 = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
        fh2 = [x.get("targetId") for x in
               next((a for a in ((at2.get("units") or [{}])[0].get("abilities") or [])
                     if a.get("abilityId") == ABILITY), {}).get("fromHere") or []]
        if target["id"] not in fh2:
            print("cast illegal apres placement"); return None

        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        rng_before = rpc("dumpRng", {"runnerId": rid}, 30)
        if not _ok(rng_before):
            print("dumpRng KO"); return None

        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": target["id"], "abilityType": ABILITY},
            "captureEvents": True}, 120)
        if not _ok(cast):
            print("cast KO", str(cast)[:200]); return None
        rng_after = rpc("dumpRng", {"runnerId": rid}, 30)

        live = {}
        for act in (cast.get("actions") or []):
            for e in (act.get("events") or []):
                td = e.get("tags")
                if not td:
                    continue
                td = json.loads(td) if isinstance(td, str) else td
                if "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
                    live.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))

        out.update({"board": board, "dv": dv2, "ob": ob2, "snap": snap2, "cid": cid,
                    "target": target["id"], "behind": placed, "live": live,
                    "rng_before": rng_before, "rng_after": rng_after})
        return out
    finally:
        pass


def offline_draws(reg, extra_bounds):
    """Rejoue le cast OFFLINE (main puis splash id-trie) en BRULANT `extra_bounds` tirages entre les
    deux volets (== le PickRandomly), et rend (nb de genrand consommes, per-hit par cible)."""
    from engine.runner.snapshot import load_state
    from engine.runner.abilities.base import ability_attack_params
    from engine.runner.operations.damage import AttackDamageOperation
    st = load_state(reg["dv"], reg["ob"], reg["snap"], board=reg["board"])
    rng = CountingRng(reg["rng_before"]["mt"], reg["rng_before"]["mti"])
    st.rng = rng
    bmin, bmax, pierce, hits = ability_attack_params(st, reg["cid"], "PlasmaCannon", "Plasma", ranged=True)
    per = {}
    main = AttackDamageOperation.execute_ability_attack(
        st, reg["cid"], reg["target"], bmin, bmax, pierce, hits,
        damage_profile="Plasma", is_melee=False, is_attack_damage_op=True)
    per[reg["target"]] = (main or {}).get("per_hit")
    for b in extra_bounds:                       # PickRandomly : `NextInternal(0, b)` par tirage
        rng.next_internal(0, b)
    for t in sorted(reg["behind"]):              # OrderBy natif (AttackBehaviour.Execute) = id
        a = AttackDamageOperation.execute_ability_attack(
            st, reg["cid"], t, bmin, bmax, pierce, hits,
            damage_profile="Plasma", is_melee=False, is_attack_damage_op=True)
        per[t] = (a or {}).get("per_hit")
    return rng.n, per


def port_real(reg):
    """Rejoue le cast par le PORT REEL (`PlasmaCannonAbility.execute_behaviour` -> arbre DSL ->
    `_pick_randomly_n`), et rend (nb genrand, per-hit par cible) -- confronte la CHAINE COMPLETE,
    pas seulement le modele de tirages."""
    from engine.runner.snapshot import load_state
    from engine.runner.abilities.darkangels import PlasmaCannonAbility
    st = load_state(reg["dv"], reg["ob"], reg["snap"], board=reg["board"])
    rng = CountingRng(reg["rng_before"]["mt"], reg["rng_before"]["mti"])
    st.rng = rng
    res = PlasmaCannonAbility().execute_behaviour(st, reg["cid"], reg["target"])
    per = {reg["target"]: ((res or {}).get("main_attack") or {}).get("per_hit")}
    for s in ((res or {}).get("splash") or []):
        per[s["target"]] = (s.get("attack") or {}).get("per_hit")
    return rng.n, per


def spread(xs):
    return (max(xs) - min(xs)) if xs else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    args = ap.parse_args()
    rpc = Rpc()
    print(f"session={rpc.sid} seed={args.seed}")

    results = []
    for k in (1, 2):
        reg = run_regime(rpc, args.seed, k)
        if reg is None:
            print(f"REGIME k={k} : setup KO")
            continue
        try:
            live_n = count_genrand(reg["rng_before"], reg["rng_after"])
            # modeles de bornes du PickRandomly (pool k, amount n=2)
            models = {
                "M0 no-draw":      [],
                "M1 min(k,n)":     [k - i for i in range(min(k, 2))],     # k, k-1, ...
                "M2 n draws":      [2, 1],
                "M3 one draw":     [k],
            }
            print(f"\n=== REGIME k={k} (pool={sorted(reg['behind'])} target={reg['target']}) ===")
            print(f"  LIVE genrand consommes par le cast : {live_n}")
            base_n, _ = offline_draws(reg, [])
            print(f"  PORT (M0, 0 tirage de pick)        : {base_n}   -> delta live-port = "
                  f"{None if live_n is None else live_n - base_n}")
            live_main = reg["live"].get(reg["target"]) or []
            for name, bounds in models.items():
                n, per = offline_draws(reg, bounds)
                rs, ok = {}, True
                for tid, ph in per.items():
                    lp = reg["live"].get(tid) or []
                    if not ph or len(lp) != len(ph):
                        ok = False
                        continue
                    rs[tid] = [a / b for a, b in zip(lp, ph)]
                allr = [x for v in rs.values() for x in v]
                print(f"  {name:<12} bounds={bounds!s:<10} genrand={n:<4} "
                      f"spread(ratio live/off, TOUTES cibles)={spread(allr):.5f}"
                      + ("" if ok else "  [per-hit incomparable]"))
                for tid, v in sorted(rs.items()):
                    tag = "MAIN " if tid == reg["target"] else "splash"
                    print(f"      {tag} {tid}: ratios={[round(x, 4) for x in v]}")
            pn, pper = port_real(reg)
            prs = {}
            for tid, ph in pper.items():
                lp = reg["live"].get(tid) or []
                if ph and len(lp) == len(ph):
                    prs[tid] = [a / b for a, b in zip(lp, ph)]
            allp = [x for v in prs.values() for x in v]
            print(f"  PORT REEL (PlasmaCannonAbility) genrand={pn} "
                  f"spread(ratio live/port)={spread(allp):.5f} "
                  f"bit-exact={'OUI' if allp and max(abs(x - 1.0) for x in allp) < 1e-9 else 'NON'}")
            for tid, v in sorted(prs.items()):
                print(f"      {'MAIN ' if tid == reg['target'] else 'splash'} {tid}: "
                      f"ratios={[round(x, 4) for x in v]}")
            results.append({"k": k, "live_n": live_n, "port_n": base_n,
                            "delta": (None if live_n is None else live_n - base_n),
                            "real_n": pn,
                            "real_exact": bool(allp) and max(abs(x - 1.0) for x in allp) < 1e-9})
        finally:
            try:
                rpc("disposeRunner", {"runnerId": reg["rid"]}, 20)
            except Exception:
                pass
            try:
                reg["state_file"].unlink()
            except Exception:
                pass

    print("\n=== VERDICT (delta = tirages LIVE - tirages PORT sans pick) ===")
    for r in results:
        print(f"  k={r['k']} : live={r['live_n']} port(sans pick)={r['port_n']} delta={r['delta']} "
              f"| PORT REEL genrand={r['real_n']} bit-exact={r['real_exact']}")
    print("  predictions : M0 (0,0) | M1 (1,2) | M2 (2,2) | M3 (1,1)")


if __name__ == "__main__":
    main()
