"""Probe #133-B -- RIPOSTE `MartialSuperiority` (templChampion << Brother Jaeger >>, triggered 1092).

Scenario CRAFTE (le runner est un bac a sable : on pilote les DEUX camps) :
  1. build 1v1 Jaeger (moi) vs un attaquant adverse ;
  2. on DEPLACE Jaeger au contact (jamais « bloque par la geometrie de spawn ») ;
  3. `endturn` -> c'est le tour ADVERSE (gate natif `NOT IsTurnOf(Owner@0x148)`) ;
  4. l'attaquant frappe Jaeger -> le natif doit d'abord jouer la RIPOSTE (2 coups Power sur
     l'attaquant) puis l'attaque entrante ;
  5. REPLAY-DIFF : meme etat + meme RNG rejoues offline -> PV finaux identiques des DEUX cotes.

Cas NEGATIFS craftes :
  --neg-turn   : c'est MON tour et JAEGER attaque -> aucune riposte (Jaeger n'est pas la CIBLE).
  --neg-owner-turn : DISCRIMINANT PUR du gate `NOT IsTurnOf(Owner@0x148)` -- MEME geometrie, MEME
                 attaquant, MEME cible que le cas positif, SEUL le joueur courant change (on force
                 l'attaque de l'ennemi PENDANT MON tour ; `applyAction` ne verifie pas la propriete
                 du casterId, cf. runner.md §4). Aucune riposte attendue.
  --neg-ranged : l'attaquant tire a DISTANCE (>=2 hexes) -> aucune riposte (gate `IsMeleeAttack`,
                 POSITIONNEL cote natif).

Usage :  python probe_133_martial_superiority.py [--attacker <unitId>] [--neg-turn|--neg-ranged]
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import deque
from pathlib import Path

import rl_collect_batch as R
from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent
from engine.entities.pathfinding.board import Board

PYDIR = Path(__file__).resolve().parent
LOGS = PYDIR.parents[1] / "logs" / "runners"
JAEGER = "templChampion"


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def rpc(sid, m, body=None, timeout=60):
    return _unwrap(R._rpc(sid, m, [body] if body is not None else [], timeout=timeout))


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def build(tag, attacker, hp_target="999999", extra=None):
    LOGS.mkdir(parents=True, exist_ok=True)
    state = LOGS / ("ms_%s.json" % tag)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", "777",
            "--state-file", str(state), "--board", "MC1_67",
            "--roster", "1", "--p-units", JAEGER, "--a-units", attacker,
            "--hp-player", "999999", "--hp-target", hp_target, *(extra or [])]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO: %s" % (p.stderr or p.stdout or "")[-600:])
        return None, None
    return json.loads(state.read_text())["runnerId"], state


def _bfs(board, src):
    dist = {src: 0}
    q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1
                q.append(n)
    return dist


def _units(dv, vis):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vis and u.get("alive")),
                None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attacker", default="orksNob")
    ap.add_argument("--neg-turn", action="store_true")
    ap.add_argument("--neg-owner-turn", action="store_true")
    ap.add_argument("--neg-ranged", action="store_true")
    ap.add_argument("--lethal", action="store_true",
                    help="attaquant a PV bas : la riposte le TUE -> l'attaque entrante doit etre "
                         "ANNULEE (gate acteur-mort POST-On(0x2a = PreUnitAbility) d'ActiveAbilityOperation).")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    tag = ("negturn" if args.neg_turn else "negownerturn" if args.neg_owner_turn
           else "negranged" if args.neg_ranged else "lethal" if args.lethal else "pos")
    # `--neg-owner-turn` : l'ATTAQUANT reste l'ennemi (comme le cas positif), mais on reste sur MON
    # tour -> seul le conjoint `NOT IsTurnOf(Owner)` differe.
    mine_turn = bool(args.neg_turn or args.neg_owner_turn)
    want_dist = 2 if args.neg_ranged else 1        # 1 = adjacent (melee) ; 2 = tir hors melee
    sid = R._resolve_session()
    rid, state_file = build(tag, args.attacker, hp_target="2500" if args.lethal else "999999")
    if rid is None:
        return
    try:
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")

        def tile(u):
            p = u.get("pos") or {}
            return board.id_at(p.get("col"), p.get("row"))

        # --- 1. amener JAEGER a la distance voulue de l'attaquant (je pilote MON camp) ---------
        for _turn in range(30):
            dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            jae, att = _units(dv, JAEGER), _units(dv, args.attacker)
            if jae is None or att is None:
                print("unite manquante"); return
            at = tile(att)
            dist = _bfs(board, at)
            if dist.get(tile(jae)) == want_dist:
                break
            if dv.get("currentPlayer") != jae.get("owner"):
                rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
                continue
            mt = rpc(sid, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            row = next((x for x in (mt.get("units") or []) if x.get("unitId") == jae["id"]), None)
            reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                     for t in ((row or {}).get("tiles") or [])}
            exact = [t for t in reach if dist.get(t) == want_dist]
            pool = exact or [t for t in reach if t in dist]
            if not pool:
                rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
                continue
            best = exact[0] if exact else min(pool, key=lambda t: dist[t])
            col, r = reach[best]
            rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": jae["id"], "to": {"col": col, "row": r}}}, 40)
            if not exact:
                rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        # --- 2. positionner le TOUR ------------------------------------------------------------
        for _ in range(4):
            dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            jae = _units(dv, JAEGER)
            mine = (dv.get("currentPlayer") == jae.get("owner"))
            if mine == mine_turn:
                break
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        jae, att = _units(dv, JAEGER), _units(dv, args.attacker)
        d = _bfs(board, tile(att)).get(tile(jae))
        caster, target = (jae, att) if args.neg_turn else (att, jae)
        print("[state] jaeger u%s @%s | %s u%s @%s | dist=%s | current=%s (jaeger=%s) | caster=u%s"
              % (jae["id"], jae["pos"], args.attacker, att["id"], att["pos"], d,
                 dv.get("currentPlayer"), jae.get("owner"), caster["id"]))
        norm = next((a for a in (caster.get("abilities") or []) if a.get("kind") == "normal"), None)
        if norm is None:
            print("pas d'attaque normale sur le caster"); return
        # --- 3. etat offline + RNG cale (board PASSE : les gates positionnels en dependent) -----
        ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 40)
        st = load_state(dv, ob, snap, board=board)
        hp_before = {}
        for u in (jae, att):
            e = st.get_entity(u["id"])
            hc = e.get_component(HealthComponent) if e is not None else None
            hp_before[u["id"]] = hc.hp if hc is not None else None
        s0 = rpc(sid, "dumpRng", {"runnerId": rid}, 30)
        st.rng = _seed_rng(s0)
        runner = Runner(st).install_default_handlers(20)
        # --- 4. LIVE ---------------------------------------------------------------------------
        res = rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster["id"], "targetId": target["id"],
            "abilityType": norm["id"]}}, 60)
        a0 = (res.get("actions") or [{}])[0]
        if not (res.get("ok") and a0.get("ok")):
            print("[live] applyAction KO: %s" % json.dumps(res, default=str)[:1000])
        live_hp = {u.get("squadId"): u.get("hp") for u in (res.get("units") or [])}
        per_target = {}
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Target_Id") is not None:
                per_target.setdefault(td["Target_Id"], []).append(td.get("Amount"))
        print("[live] amounts per target: %s" % per_target)
        print("[live] hp jaeger=%s attaquant=%s (avant %s)"
              % (live_hp.get(jae["id"]), live_hp.get(att["id"]), hp_before))
        # --- 5. OFFLINE ------------------------------------------------------------------------
        runner.apply(AttackUnitMessage(caster["id"], target["id"]))
        off_hp = {}
        for u in (jae, att):
            e = st.get_entity(u["id"])
            hc = e.get_component(HealthComponent) if e is not None else None
            off_hp[u["id"]] = hc.hp if hc is not None else None
        print("[off ] hp jaeger=%s attaquant=%s" % (off_hp.get(jae["id"]), off_hp.get(att["id"])))
        ok = (off_hp.get(jae["id"]) == live_hp.get(jae["id"])
              and off_hp.get(att["id"]) == live_hp.get(att["id"]))
        riposte_live = (live_hp.get(att["id"]) or 0) < (hp_before.get(att["id"]) or 0) \
            if not args.neg_turn else None
        print("[VERDICT %s] %s | riposte_live=%s" % (tag, "MATCH" if ok else "DIVERGENCE",
                                                     riposte_live))
    finally:
        if not args.keep:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
            state_file.unlink(missing_ok=True)
            print("[dispose] %s" % rid)


if __name__ == "__main__":
    main()
