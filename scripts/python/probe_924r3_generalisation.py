"""#924-r3 -- GENERALISATION des quatre ports de la tranche, hors du regime ou ils ont ete ecrits.

POURQUOI CE PROBE. Les quatre confrontations livrees (`test_924r1_*`, `test_924r2_*`,
`test_10007r1_*`, `test_1019r1_*`) pinnent chacune UN seed, UN board et UN couple d'unites. Un port
juste et un port SUR-AJUSTE y rendent le meme vert. Ce probe joue les deux regimes que ces fichiers
ne jouent PAS :

  CAS `profil`  -- `#10007-r1` : le MEME montage (Kimm attaque), mais avec un attaquant dont le
                   profil d'arme est **`Psychic`** (`astraPrimarisPsy`). Les deux gates
                   `!DamageProfileIs(GetDamageProfile(cfg))` / `...GetDamageProfile2(cfg)` doivent
                   alors FERMER, donc :
                     (a) l'offline reste bit-exact ;
                     (b) la contre-epreuve (slot 25 neutralise) ne change RIEN -- c'est la seule
                         forme sous laquelle << aucun ecart >> est un RESULTAT et pas un aveu.
                   Le cas `Physical` du fichier de test montre l'inverse (1249 points d'ecart) :
                   les deux ensemble etablissent que le gate DISCRIMINE.

  CAS `seed`    -- `#924-r2` : le tir d'overwatch d'Imospekh rejoue sur un AUTRE seed (donc un autre
                   flux PRNG, d'autres tuiles, d'autres tirages de crit). L'additif d'overwatch doit
                   rester bit-exact.

Sortie ASCII stricte (cp1252). Un runner a la fois, dispose en sortie.

    python probe_924r3_generalisation.py --state-file <ABSOLU> [--cas profil|seed|tous]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import deque
from pathlib import Path

#: `#10007-r1` -- le porteur HORS POOL du passif `ModifiedExoarmour` (effet 1543).
KIMM = "votanChampion"
#: attaquant du cas `profil` : ses DEUX armes sont `Psychic`, donc les deux gates de profil FERMENT.
PSY_ATTACKER = "astraPrimarisPsy"
#: `#924-r2` -- le porteur d'`InescapableDeath`, en OVERWATCHER (a-unit) ; le mover est a nous.
OVERWATCHER = "necroDestroyer"
MOVER = "necroOverlord"
MOVER_HP = 60000


def _rpc_factory():
    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=120):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r
    return sid, rpc, _rpc


def _build(state_file: str, extra: list) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--state-file", state_file] + list(extra)
    p = subprocess.run(argv, capture_output=True, text=True)
    if p.returncode != 0:
        sys.stdout.write((p.stdout or "")[-1200:])
        sys.stdout.write((p.stderr or "")[-1600:])
        raise SystemExit("build KO : %s" % (extra,))
    return int(json.loads(Path(state_file).read_text(encoding="utf-8"))["runnerId"])


def _seed_rng(s):
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _bfs(board, src):
    dist = {src: 0}; q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1; q.append(n)
    return dist


def cas_profil(rpc, state_file: str, board: str, seed: str) -> int:
    """Kimm attaque par un profil `Psychic` : les deux gates de profil doivent FERMER."""
    import catalog_inject as CI
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import HealthComponent
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.runner import Runner
    from engine.runner.snapshot import load_state

    bc = Path(state_file).with_suffix(".bc.json")
    p, ajoutees, _cfg = CI.write_augmented_seed_bc(str(bc), [KIMM])
    print("[924-r3/profil] injection %s -> %s" % (KIMM, ajoutees))
    rid = _build(state_file, ["--seed", seed, "--board", board, "--seed-bc", str(p),
                              "--p-units", PSY_ATTACKER, "--a-units", KIMM])
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="evenq")
        tof = lambda u: brd.id_at(u["pos"]["col"], u["pos"]["row"])          # noqa: E731
        import gameconfig as GC
        R = max([int(w.get("Range") or 0)
                 for w in ((GC.unit(PSY_ATTACKER) or {}).get("weapons") or [])] or [0]) or 1
        att_id = tgt_id = my_player = None
        for _turn in range(30):
            dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            us = {u.get("visualId"): u for u in (dec.get("units") or []) if u.get("alive")}
            if PSY_ATTACKER not in us or KIMM not in us:
                print("[924-r3/profil] NON MESURE : unite absente (%s)" % sorted(us)); return 3
            a, t = us[PSY_ATTACKER], us[KIMM]
            att_id, tgt_id = a["id"], t["id"]
            if my_player is None:
                my_player = a.get("owner")
            if dec.get("currentPlayer") != my_player:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
            dgoal, cur = _bfs(brd, tof(t)), tof(a)
            if dgoal.get(cur, 99) > R:
                mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
                cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == att_id), None)
                reach = {brd.id_at(x["col"], x["row"]): (x["col"], x["row"])
                         for x in ((cmt or {}).get("tiles") or [])}
                pool = [x for x in reach if x in dgoal and dgoal[x] < dgoal.get(cur, 99)]
                if pool:
                    best = min(pool, key=lambda x: dgoal[x]); col, row = reach[best]
                    rpc("applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": att_id, "to": {"col": col, "row": row}}}, 40)
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
                continue
            norm = next((ab for ab in (a.get("abilities") or []) if ab.get("kind") == "normal"), None)
            ob = rpc("observeBattle", {"runnerId": rid}, 40)
            snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
            s0 = rpc("dumpRng", {"runnerId": rid}, 30)
            hp0 = next((u.get("hp") for u in (ob.get("units") or []) if u.get("squadId") == tgt_id), None)
            res = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": att_id, "targetId": tgt_id,
                "abilityType": norm["id"]}}, 60)
            hp1 = next((u.get("hp") for u in (res.get("units") or []) if u.get("squadId") == tgt_id), None)
            if hp0 is None or hp1 is None:
                print("[924-r3/profil] NON MESURE : PV absents"); return 3

            def rejouer():
                st = load_state(dec, ob, snap, board=brd)
                st.rng = _seed_rng(s0)
                r = Runner(st).install_default_handlers()
                r.apply(AttackUnitMessage(att_id, tgt_id))
                return st.get_entity(tgt_id).get_component(HealthComponent).hp, r.damage_handler.last

            nominal, last = rejouer()
            from engine.entities.effects.loki import damage_reduction as DR
            garde = DR.ModifiedExoarmourPierceReductionEffect.create_piercing_malus_for_defense
            DR.ModifiedExoarmourPierceReductionEffect.create_piercing_malus_for_defense = (
                lambda self, damage_profile=None, is_melee=None, attacker_ctx=None: None)
            try:
                mutant, _ = rejouer()
            finally:
                DR.ModifiedExoarmourPierceReductionEffect.create_piercing_malus_for_defense = garde
            print("[924-r3/profil] profil=%s | Kimm %s -> live %s | offline %s | mutant %s"
                  % ((last or {}).get("profile"), hp0, hp1, nominal, mutant))
            ok = (nominal == hp1) and (nominal == mutant)
            print("[924-r3/profil] bit-exact=%s ; gate de profil FERME (mutant == nominal)=%s"
                  % (nominal == hp1, nominal == mutant))
            return 0 if ok else 1
        print("[924-r3/profil] NON MESURE : attaquant jamais amene a portee"); return 3
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 30)


def cas_seed(rpc, state_file: str, board: str, seed: str) -> int:
    """Le tir d'overwatch d'Imospekh, sur un AUTRE seed que celui du fichier de test."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import HealthComponent, StatsComponent
    from engine.runner.messages import MoveUnitMessage
    from engine.runner.runner import Runner
    from engine.runner.snapshot import load_state

    rid = _build(state_file, ["--seed", seed, "--board", board,
                              "--p-units", MOVER, "--a-units", OVERWATCHER,
                              "--unit-stat", "%s:Health=%d,RemainingHealth=%d"
                              % (MOVER, MOVER_HP, MOVER_HP)])
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        brd = Board(bg["tiles"], adjacency="evenq")
        tof = lambda u: brd.id_at(u["pos"]["col"], u["pos"]["row"])          # noqa: E731
        import gameconfig as GC
        R = max([int(w.get("Range") or 0)
                 for w in ((GC.unit(OVERWATCHER) or {}).get("weapons") or [])] or [0]) or 1
        my_player = None
        for _turn in range(30):
            dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            us = {u.get("visualId"): u for u in (dec.get("units") or []) if u.get("alive")}
            if MOVER not in us or OVERWATCHER not in us:
                print("[924-r3/seed] NON MESURE : unite absente (%s)" % sorted(us)); return 3
            mv, ow = us[MOVER], us[OVERWATCHER]
            if my_player is None:
                my_player = mv.get("owner")
            if dec.get("currentPlayer") != my_player:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
            dgoal, cur = _bfs(brd, tof(ow)), tof(mv)
            mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == mv["id"]), None)
            reach = {brd.id_at(x["col"], x["row"]): (x["col"], x["row"])
                     for x in ((cmt or {}).get("tiles") or [])}
            out_pool = [x for x in reach if x in dgoal and dgoal[x] > R and dgoal[x] < dgoal.get(cur, 99)]
            if dgoal.get(cur, 99) > R and out_pool:
                best = min(out_pool, key=lambda x: dgoal[x]); col, row = reach[best]
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": mv["id"], "to": {"col": col, "row": row}}}, 40)
                dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
                if dv2.get("currentPlayer") == my_player:
                    rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
                continue
            step = [x for x in reach if x in dgoal and x in set(brd.neighbours(cur))]
            if not step:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
            best = min(step, key=lambda x: dgoal[x]); col, row = reach[best]
            ob = rpc("observeBattle", {"runnerId": rid}, 40)
            snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
            s0 = rpc("dumpRng", {"runnerId": rid}, 30)
            hp0 = next((u.get("hp") for u in (ob.get("units") or []) if u.get("squadId") == mv["id"]), None)
            st = load_state(dec, ob, snap, board=brd)
            st.rng = _seed_rng(s0)
            mv_armor = next((u.get("stats", {}).get("fixedArmor")
                             for u in (snap.get("units") or []) if u.get("entityId") == mv["id"]), None)
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": mv["id"], "to": {"col": col, "row": row}}}, 40)
            ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
            hp1 = next((u.get("hp") for u in (ob2.get("units") or []) if u.get("squadId") == mv["id"]), None)
            if hp0 is None or hp1 is None or hp1 >= hp0:
                continue
            oe = st.get_entity(ow["id"])
            if oe is None or oe.get_component(StatsComponent) is None:
                print("[924-r3/seed] NON MESURE : overwatcher sans StatsComponent"); return 3
            r = Runner(st).install_default_handlers(20)
            r.apply(MoveUnitMessage(mv["id"], (col, row)))
            off = st.get_entity(mv["id"]).get_component(HealthComponent).hp
            print("[924-r3/seed] seed=%s board=%s | mover armure=%s | hp %s -> live %s | offline %s"
                  % (seed, board, mv_armor, hp0, hp1, off))
            print("[924-r3/seed] bit-exact=%s (ecart=%s)" % (off == hp1, hp1 - off))
            return 0 if off == hp1 else 1
        print("[924-r3/seed] NON MESURE : aucun overwatch declenche"); return 3
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 30)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU du state-file")
    ap.add_argument("--cas", default="tous", choices=("profil", "seed", "tous"))
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="31337")
    args = ap.parse_args()
    _sid, rpc, _raw = _rpc_factory()
    rcs = []
    if args.cas in ("profil", "tous"):
        rcs.append(cas_profil(rpc, args.state_file, args.board, args.seed))
    if args.cas in ("seed", "tous"):
        rcs.append(cas_seed(rpc, args.state_file, args.board, args.seed))
    rc = max(rcs) if rcs else 3
    print("[924-r3] VERDICT: %s (rc=%d)" % ("PASS" if rc == 0 else "FAIL/NON MESURE", rc))
    return rc


if __name__ == "__main__":
    sys.exit(main())
