"""Probe de validation case-66 : TaintedNarthecium revive-EN-PLACE (deathRotbone, base ReviveEffect).

Confronte le port au LIVE : build runner (deathRotbone + allie Chaos + allie Xenos), capture l'etat REEL
(board/stats/traits via load_state), DRIVE les positions (allie Chaos adjacent), simule la mort de l'allie
via `after_death_triggers` (event 1), et verifie CHAQUE gate du port :
  1. base : allie Chaos adjacent tue (RNG True) -> revive alive, hp=min(reviveHP,maxHP), MEME position
  2. proba ~75% : N morts avec RNG frais -> ~75% revives (Maybe next_bool(75))
  3. once-per-turn : 2e mort MEME tour -> PAS de revive ; apres reset_revive_gates -> revive de nouveau
  4. even-if-overkill : mort overkill=True -> revive quand meme (pas de gate overkill)
  5. Chaos-only : allie NON-Chaos (Xenos) tue -> PAS de revive (HasTrait Chaos)
  6. adjacence : allie Chaos a dist>2 -> PAS de revive (IsAdjacent 2)
  7. CanBeRevived : allie Chaos Mechanical / PermaDeath -> PAS de revive (toggle offline)

Discipline : state-file UNIQUE, dispose le runner, ASCII only. Lance depuis scripts/python (python, pas py).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_66_revive_state.json"

import rl_collect_batch as R
from engine.runner.snapshot import load_state
from engine.runner.operations.triggers.dispatch.move_death import after_death_triggers
from engine.runner.operations.revive import reset_revive_gates, kill_unit_revive_gate
from engine.runner.components import (UnitComponent, HealthComponent, OwnerComponent,
                                      PositionComponent, StatsComponent)
from engine.runner.prng import IntBasedMersenneTwister
from engine.entities.pathfinding.board import Board
from engine.entities.effects.magnitude import ability_var
from engine.entities.traits.unit_trait import UnitTrait

CASTER = "deathRotbone"
CASTER_ABILITY = "TaintedNarthecium"
ALLY_CHAOS = "deathBlightbringer"
ALLY_XENOS = "eldarRanger"
BUILD = ["--p-units", f"{CASTER},{ALLY_CHAOS},{ALLY_XENOS}", "--a-units", "worldKharn,ultraTitus",
         "--rank", "17", "--hp-player", "300000"]
SEED = "777"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng_state(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _by_vis(state, vis):
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
            return uid
    return None


def _pc(state, uid):
    return state.get_entity(uid).get_component(PositionComponent)


def _hc(state, uid):
    return state.get_entity(uid).get_component(HealthComponent)


def _uc(state, uid):
    return state.get_entity(uid).get_component(UnitComponent)


def _rng_true_seed(chance=75):
    """Trouve un seed IntBasedMersenneTwister dont le 1er next_bool(chance) == True (et un == False)."""
    t = f_ = None
    for s in range(1, 5000):
        rng = IntBasedMersenneTwister(s)
        b = rng.next_bool(chance)
        if b and t is None:
            t = s
        if (not b) and f_ is None:
            f_ = s
        if t is not None and f_ is not None:
            break
    return t, f_


def _fresh_rng(seed_int):
    return IntBasedMersenneTwister(seed_int)


def main():
    sid = R._resolve_session()
    w = R._rpc(sid, "autoBootExtraire", [{}], timeout=180)
    w = w.get("result") if isinstance(w, dict) and "result" in w else w
    if not (isinstance(w, dict) and w.get("ok")):
        print("SKIP: amorce KO", str(w)[:150]); return

    def rpc(method, body, t=90):
        r = R._rpc(sid, method, [body], timeout=t)
        return r.get("result") if isinstance(r, dict) and "result" in r else r

    # attente bornee d'un slot libre (MAX_RUNNERS partages ; je ne dispose JAMAIS ceux des autres)
    import time
    deadline = time.time() + 600
    rid = None
    while time.time() < deadline:
        lr = rpc("listRunners", {}, 30)
        n = len(lr) if isinstance(lr, list) else 99
        if n < 10:
            proc = subprocess.run(
                [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--state-file", str(STATE),
                 "--board", "MC1_67", *BUILD],
                cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
            if STATE.exists():
                try:
                    rid = json.loads(STATE.read_text())["runnerId"]
                    break
                except Exception:
                    pass
            err = (proc.stderr or proc.stdout or "")[-200:]
            if "cap reached" not in err:
                print("SKIP: build KO", err); return
        time.sleep(15)
    if rid is None:
        print("SKIP: aucun slot runner libre apres 600s (10 runners tiers actifs)"); return
    print("runnerId=", rid)

    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            print("SKIP: boardGraph indispo"); return
        board = Board(bg["tiles"], adjacency="evenq")
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
        if not (_ok(dv) and _ok(ob) and _ok(snap)):
            print("SKIP: capture KO"); return

        def fresh_state(rng_seed_int=None):
            st = load_state(dv, ob, snap, board=board)
            if rng_seed_int is not None:
                st.rng = _fresh_rng(rng_seed_int)
            return st

        st0 = fresh_state()
        ids = {"dr": _by_vis(st0, CASTER), "chaos": _by_vis(st0, ALLY_CHAOS),
               "xenos": _by_vis(st0, ALLY_XENOS)}
        if any(v is None for v in ids.values()):
            print("SKIP: roster incomplet offline", ids); return
        # niveau/mult passif du porteur (pour reviveHP attendu)
        sc = st0.get_entity(ids["dr"]).get_component(StatsComponent)
        plvl = getattr(sc.ctx, "passive_ability_level", None)
        mult = getattr(sc.ctx, "ability_variables_multiplier", 100)
        revive_hp = ability_var(CASTER_ABILITY, "hp", plvl, multiplier_pct=mult)
        chance = ability_var(CASTER_ABILITY, "chance", is_constant=True)
        print("passive_level=%s mult=%s reviveHP=%s chance=%s" % (plvl, mult, revive_hp, chance))
        s_true, s_false = _rng_true_seed(int(chance))
        print("rng seed(next_bool True)=%s (False)=%s" % (s_true, s_false))

        def place_adjacent(st, ally_uid, dist_from_dr=1):
            """Place dr au centre, l'allie a distance <= dist voulue (drive positions)."""
            # centre = tuile a >=4 voisins walkable
            center = None
            for uid, e in st.entities.items():
                pc = e.get_component(PositionComponent)
                if pc is None:
                    continue
                t = board.id_at(pc.col, pc.row)
                if t is not None and len([n for n in board.neighbours(t) if board.walkable(n)]) >= 3:
                    center = board.coord(t); break
            if center is None:
                return False
            _pc(st, ids["dr"]).col, _pc(st, ids["dr"]).row = center
            ctile = board.id_at(*center)
            if dist_from_dr == 1:
                dst = next((board.coord(n) for n in board.neighbours(ctile) if board.walkable(n)), None)
            else:
                # BFS pour une tuile a distance exacte dist_from_dr
                from collections import deque
                seen = {ctile: 0}; q = deque([ctile]); dst = None
                while q:
                    x = q.popleft()
                    if seen[x] == dist_from_dr and board.walkable(x):
                        dst = board.coord(x); break
                    for n in board.neighbours(x):
                        if n not in seen:
                            seen[n] = seen[x] + 1; q.append(n)
            if dst is None:
                return False
            _pc(st, ally_uid).col, _pc(st, ally_uid).row = dst
            return True

        def kill_and_fire(st, ally_uid, overkill=False):
            """Simule `IdunBattle.Operations.KillUnitOperation$$Execute` : hp=0/alive=False, `On(1)`
            (`after_death_triggers`) PUIS la GARDE @IdunBattle.Operations.KillUnitOperation$$Execute+0x82e (`kill_unit_revive_gate` : draine la
            `ReviveData` posee par la feuille `Revive` -> phase 0xd de `VerifyDeaths`)."""
            hc = _hc(st, ally_uid); hc.hp = 0
            _uc(st, ally_uid).alive = False
            out = after_death_triggers(st, dying_id=ally_uid, killer_id=ids["dr"], overkill=overkill)
            kill_unit_revive_gate(st, ally_uid)
            return out

        results = []

        # === 1. base : Chaos adjacent, RNG True -> revive alive, hp=min(reviveHP,maxHP), MEME pos ===
        st = fresh_state(s_true)
        assert place_adjacent(st, ids["chaos"], 1), "placement adjacent KO"
        pos_before = (_pc(st, ids["chaos"]).col, _pc(st, ids["chaos"]).row)
        maxhp = int(_hc(st, ids["chaos"]).hp_max)
        exp_hp = min(int(revive_hp), maxhp)
        res = kill_and_fire(st, ids["chaos"], overkill=False)
        alive = _uc(st, ids["chaos"]).alive
        hp = int(_hc(st, ids["chaos"]).hp)
        pos_after = (_pc(st, ids["chaos"]).col, _pc(st, ids["chaos"]).row)
        ok1 = alive and hp == exp_hp and pos_after == pos_before
        results.append(("1.base_revive(RNG True)", ok1,
                        "alive=%s hp=%d exp=%d pos %s->%s res=%s" % (alive, hp, exp_hp, pos_before, pos_after,
                                                                     [r.get("ability") for r in res])))

        # === 1b. RNG False -> PAS de revive ===
        st = fresh_state(s_false)
        place_adjacent(st, ids["chaos"], 1)
        kill_and_fire(st, ids["chaos"], overkill=False)
        ok1b = (not _uc(st, ids["chaos"]).alive) and int(_hc(st, ids["chaos"]).hp) == 0
        results.append(("1b.no_revive(RNG False)", ok1b, "alive=%s" % _uc(st, ids["chaos"]).alive))

        # === 2. proba ~75% sur N morts avec RNG frais ===
        N = 400; revived = 0
        for s in range(1, N + 1):
            st = fresh_state(s)
            place_adjacent(st, ids["chaos"], 1)
            kill_and_fire(st, ids["chaos"], overkill=False)
            if _uc(st, ids["chaos"]).alive:
                revived += 1
        pct = 100.0 * revived / N
        ok2 = 70.0 <= pct <= 80.0
        results.append(("2.proba~75%%", ok2, "revived %d/%d = %.1f%%" % (revived, N, pct)))

        # === 3. once-per-turn : 2e mort MEME tour -> PAS de revive ; apres reset -> revive ===
        st = fresh_state(s_true)
        place_adjacent(st, ids["chaos"], 1)
        kill_and_fire(st, ids["chaos"], overkill=False)          # revive #1 (consomme le gate)
        alive1 = _uc(st, ids["chaos"]).alive
        used = _uc(st, ids["dr"]).revive_used_this_turn
        kill_and_fire(st, ids["chaos"], overkill=False)          # 2e mort MEME tour -> gate ferme (aucun roll)
        alive2 = _uc(st, ids["chaos"]).alive
        reset_revive_gates(st)                                   # turn-start -> reactive le passif
        st.rng = _fresh_rng(s_true)                              # re-seed (isole le roll #3 du roll #1)
        kill_and_fire(st, ids["chaos"], overkill=False)          # 3e mort apres reset -> revive
        alive3 = _uc(st, ids["chaos"]).alive
        ok3 = alive1 and used and (not alive2) and alive3
        results.append(("3.once_per_turn", ok3,
                        "revive1=%s gate=%s revive2=%s(attendu False) reset->revive3=%s" %
                        (alive1, used, alive2, alive3)))

        # === 4. even-if-overkill : mort overkill=True -> revive quand meme ===
        st = fresh_state(s_true)
        place_adjacent(st, ids["chaos"], 1)
        kill_and_fire(st, ids["chaos"], overkill=True)
        ok4 = _uc(st, ids["chaos"]).alive
        results.append(("4.even_if_overkill", ok4, "alive=%s (overkill=True)" % ok4))

        # === 5. Chaos-only : allie NON-Chaos (Xenos) -> PAS de revive ===
        st = fresh_state(s_true)
        place_adjacent(st, ids["xenos"], 1)
        kill_and_fire(st, ids["xenos"], overkill=False)
        ok5 = not _uc(st, ids["xenos"]).alive
        results.append(("5.chaos_only(xenos no revive)", ok5, "alive=%s" % _uc(st, ids["xenos"]).alive))

        # === 6. adjacence : Chaos a dist 3 -> PAS de revive ===
        st = fresh_state(s_true)
        placed = place_adjacent(st, ids["chaos"], 3)
        if placed:
            d = None
            from engine.dsl.base import _pos as _p
            import hexgeo
            pdr = (_pc(st, ids["dr"]).col, _pc(st, ids["dr"]).row)
            pch = (_pc(st, ids["chaos"]).col, _pc(st, ids["chaos"]).row)
            d = hexgeo.distance(pdr, pch)
            kill_and_fire(st, ids["chaos"], overkill=False)
            ok6 = (d > 2) and (not _uc(st, ids["chaos"]).alive)
            results.append(("6.adjacency(dist>2 no revive)", ok6, "dist=%s alive=%s" % (d, _uc(st, ids["chaos"]).alive)))
        else:
            results.append(("6.adjacency", None, "SKIP: pas de tuile a dist 3"))

        # === 7. CanBeRevived : Chaos Mechanical -> PAS de revive (toggle offline sur sc.ctx.traits) ===
        # has_trait matche par NOM (`"Mechanical" in traits`) -> on ajoute le nom au ctx.traits de l'allie.
        st = fresh_state(s_true)
        place_adjacent(st, ids["chaos"], 1)
        sc_ch = st.get_entity(ids["chaos"]).get_component(StatsComponent)
        sc_ch.ctx.traits = list(getattr(sc_ch.ctx, "traits", None) or []) + ["Mechanical"]
        # sanity : le port doit voir Mechanical (via ctx.has_trait) -> CanBeRevived False
        from engine.runner.abilities.behaviours.context import entities_from_state
        from engine.runner.abilities.behaviours.stats import is_mechanical as _ismech
        ent7 = entities_from_state(st, ids["dr"], ids["chaos"])
        mech_seen = _ismech(ent7.has_trait, ent7.target)
        kill_and_fire(st, ids["chaos"], overkill=False)
        ok7 = mech_seen and (not _uc(st, ids["chaos"]).alive)
        results.append(("7.canberevived(mechanical no revive)", ok7,
                        "mech_seen=%s alive=%s" % (mech_seen, _uc(st, ids["chaos"]).alive)))

        # === report ===
        print("\n=== VALIDATION case-66 TaintedNarthecium ===")
        allok = True
        for name, ok, detail in results:
            tag = "OK " if ok else ("SKIP" if ok is None else "FAIL")
            if ok is False:
                allok = False
            print("[%s] %-34s %s" % (tag, name, detail))
        print("\nRESULT:", "ALL OK" if allok else "SOME FAIL")
    finally:
        try:
            R._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
        except Exception:
            pass


if __name__ == "__main__":
    main()
