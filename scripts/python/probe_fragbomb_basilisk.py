"""Probe CONFRONTATION LIVE/OFFLINE de #1017 FragBomb et #1026 BasiliskBarrage (Astra Militarum).

Monte un runner isole, DRIVE la geometrie (applyAction ignore propriete + portee), capture l'etat +
le MT (`dumpRng`) juste avant le cast, joue le cast LIVE, puis rejoue le MEME cast dans le moteur
Python (`Runner.apply(ActiveAbilityMessage)`) depuis l'etat capture et le MEME MT -> compare
per-cible : nombre de coups ET valeur de chaque coup.

Usage (scripts/python, session Frida warmee) :
    python probe_fragbomb_basilisk.py --ability fragbomb --seed 777
    python probe_fragbomb_basilisk.py --ability basilisk --seed 777 [--turns 2]

`--turns N` (basilisk) : N cycles de fin de tour avant le cast -> fait monter `TurnsStarted` du
caster, donc le nombre d'obus GARANTIS sur la tuile cible.
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
from engine.entities.pathfinding.board import Board
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

PYDIR = Path(__file__).resolve().parent
FRAGBOMB = 1017
BASILISK = 1026


def rpc(sid, m, b=None, t=60):
    r = R._rpc(sid, m, [b] if b is not None else [], timeout=t)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def build(state_file, seed, board, extra):
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", state_file, *extra]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    sf = Path(state_file)
    if not sf.exists():
        print("BUILD KO:", (p.stderr or p.stdout or "")[-900:])
        raise SystemExit(2)
    return json.loads(sf.read_text())["runnerId"]


def seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def live_hits(res, ability):
    """[(target_id, amount)] dans l'ordre live + les tuiles vides touchees."""
    seq, empty = [], []
    for a in (res.get("actions") or []):
        for e in (a.get("events") or []):
            td = e.get("tags")
            if isinstance(td, str):
                td = json.loads(td)
            if not td:
                continue
            if "Damage_Empty_Target_Tile_Id" in td:
                empty.append(td["Damage_Empty_Target_Tile_Id"])
            elif td.get("Active_Ability_Type") == ability and "Amount" in td:
                seq.append((td["Target_Id"], td["Amount"]))
    return seq, empty


def off_hits(diag, ability):
    """[(target_id, amount)] du diagnostic moteur, dans l'ordre d'execution de l'arbre."""
    out = []
    if ability == FRAGBOMB:
        main = diag.get("main_attack") or {}
        for a in (main.get("per_hit") or []):
            out.append((diag.get("target"), a))
        for s in (diag.get("splash") or []):
            for a in ((s.get("attack") or {}).get("per_hit") or []):
                out.append((s["target"], a))
    else:
        for s in (diag.get("attacks") or []):
            for a in ((s.get("attack") or {}).get("per_hit") or []):
                out.append((s["target"], a))
    return out


def counts(seq):
    d = {}
    for tid, _ in seq:
        d[tid] = d.get(tid, 0) + 1
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ability", choices=("fragbomb", "basilisk"), required=True)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--turns", type=int, default=0)
    ap.add_argument("--a-units", default="necroOverlord,necroWarden,necroDestroyer,necroSpyder")
    ap.add_argument("--geometry", choices=("crowded", "alone"), default="crowded")
    ap.add_argument("--decomp", action="store_true",
                    help="imprime la decomposition per-cible (etages du degat + stat-mods live)")
    ap.add_argument("--state-file",
                    default=str(Path(__file__).resolve().parents[2] /
                                "logs" / "runners" / "probe-fb-bb.json"))
    args = ap.parse_args()
    sid = R._resolve_session()
    Path(args.state_file).parent.mkdir(parents=True, exist_ok=True)
    frag = args.ability == "fragbomb"
    ability = FRAGBOMB if frag else BASILISK
    p_units = "astraBullgryn,astraCreed" if frag else "astraOrdnance,astraCreed"
    rid = build(args.state_file, args.seed, args.board,
                ["--p-units", p_units,
                 "--a-units", args.a_units,
                 "--hp-target", "120000", "--hp-player", "120000", "--no-ai"])
    print("runner", rid, "ability", ability)
    try:
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        byid = {t["id"]: t for t in bg["tiles"]}
        bypos = {(t["col"], t["row"]): t["id"] for t in bg["tiles"]}
        board = Board(bg["tiles"], adjacency="native_sym")

        def dview():
            return rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1,
                                             "allAbilities": True}, 90)

        def move(uid, tid):
            c = byid[tid]
            return rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": uid, "to": {"col": c["col"], "row": c["row"]}}}, 40)

        dv = dview()
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        vid = "astraBullgryn" if frag else "astraOrdnance"
        me = next(u for u in units if u.get("visualId") == vid)
        ally = next(u for u in units if u.get("visualId") == "astraCreed")
        myp = me.get("owner")
        ens = [u for u in units if u.get("owner") != myp]

        def nb_ids(tid):
            return [n for n in (byid[tid].get("neighbours") or []) if n in byid]
        # tuile a 6 voisins TOUS marchables (sinon un `move` echoue et la geometrie voulue n'est
        # pas atteinte -- cf. C3_01, 14 tuiles walkable=false)
        cands = sorted(t for t in byid if len(nb_ids(t)) == 6 and byid[t].get("walkable")
                       and all(byid[n].get("walkable") for n in nb_ids(t)))
        centre = cands[len(cands) // 2]
        ring = nb_ids(centre)
        tgt = ens[0]
        if args.geometry == "alone":
            # cible ISOLEE : personne d'autre a <=1 hex d'elle (splash VIDE attendu, hors caster)
            far = [t for t in cands
                   if hexgeo.distance((byid[t]["col"], byid[t]["row"]),
                                      (byid[centre]["col"], byid[centre]["row"])) >= 4]
            place = [(tgt["id"], centre)] + [(u["id"], far[i % len(far)])
                                             for i, u in enumerate([ally] + ens[1:])]
        else:
            # cible au centre ; caster + allie + 2 ennemis autour (FragBomb = melee -> caster adjacent)
            place = [(tgt["id"], centre), (ally["id"], ring[1]), (ens[1]["id"], ring[2]),
                     (ens[2]["id"], ring[3]), (ens[3]["id"], ring[5])]
        # FragBomb = MELEE -> le caster doit etre adjacent. BasiliskBarrage = portee ILLIMITEE et son
        # carrier porte `HeavyWeapon` (« si Thaddeus n'a pas bouge ») -> on ne le DEPLACE PAS.
        if frag:
            place.append((me["id"], ring[0]))
        for uid, tid in place:
            move(uid, tid)

        for _ in range(max(0, args.turns)):                # fait monter TurnsStarted du caster
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

        dv = dview()
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        posu = {u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in units}
        tp = posu[tgt["id"]]
        print("cible u%d %s tile=%d voisins natifs=%s" % (tgt["id"], tp, bypos[tp],
                                                          nb_ids(bypos[tp])))
        for u in units:
            print("  u%-3d %-16s %s tile=%-4s d=%d %s" %
                  (u["id"], u.get("visualId"), posu[u["id"]], bypos.get(posu[u["id"]]),
                   hexgeo.distance(tp, posu[u["id"]]),
                   "MINE" if u.get("owner") == myp else "ENEMY"))

        ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 40)
        s0 = rpc(sid, "dumpRng", {"runnerId": rid}, 30)
        res = rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": me["id"], "targetId": tgt["id"],
            "abilityType": ability}}, 90)
        a0 = (res.get("actions") or [{}])[0]
        if not (res.get("ok") and a0.get("ok")):
            print("CAST KO:", str(res)[:300]); return
        lseq, lempty = live_hits(res, ability)

        st = load_state(dv, ob, snap, board=board)
        st.rng = seed_rng(s0)
        runner = Runner(st).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=me["id"], target_id=tgt["id"],
                                          ability_type=ability))
        diag = runner.ability_handler.last or {}
        print("ported:", diag.get("ported"))
        if not diag.get("ported"):
            print("DIAG:", json.dumps(diag)[:400]); return
        oseq = off_hits(diag, ability)
        print("shells:", diag.get("shells"), "tiles:", diag.get("tiles"),
              "empty off:", diag.get("empty"), "empty live:", lempty)
        print("order:", diag.get("order"))
        print("LIVE  coups:", counts(lseq))
        print("OFF   coups:", counts(oseq))
        print("LIVE  seq  :", lseq)
        print("OFF   seq  :", oseq)
        print("MATCH exact:", lseq == oseq)
        if args.decomp:
            atks = ([{"target": diag.get("target"), "attack": diag.get("main_attack")}]
                    + list(diag.get("splash") or [])) if frag else list(diag.get("attacks") or [])
            for a in atks:
                at = a.get("attack") or {}
                print("  DECOMP u%-3d %s" % (a.get("target"),
                                             json.dumps({k: v for k, v in at.items()
                                                         if k not in ("per_hit_health",)})[:900]))
            for a in atks:
                tid = a.get("target")
                sm = rpc(sid, "statModSources", {"runnerId": rid, "unitId": tid}, 40)
                print("  STATMOD u%-3d %s" % (tid, json.dumps(sm)[:700]))
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 20)


if __name__ == "__main__":
    main()
