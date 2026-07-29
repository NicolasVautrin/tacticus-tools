"""case-haze-ord -- le port DRAINE la mort immediatement, le natif l'ENQUEUE.

QUESTION (binaire) : au regime OVERKILL, le port emet-il le MEME nombre de `genrand_int32` que le
natif ? Mesure de reference : natif 14, port 12 (`HazeOfCorruption` k = 2, seed 777, board MC1_67,
PV cible 1200).

ARTEFACTS NATIFS (decompile, build `gqfc5mff6c`) :

    IdunBattle.Operations.RecordKillOperation$$Execute
        -> IdunBattle.Core.MatchState$$AddDeath          # ENQUEUE (la file `MatchState+...`)
        -> On(PendingDeathAdded = 3)
    IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths
        RunPhase(0xc) -> <VerifyDeaths>b__0 -> Core.Services.OperationProcessor$$KillUnit
                      -> IdunBattle.Operations.KillUnitOperation$$Execute   # DRAINE
        RunPhase(0xd) -> IdunBattle.Operations.ReviveUnitOperation$$Execute

Le port COLLAPSE l'enqueue et le drain dans `AttackDamageOperation._fire_death_if_killed`, appelee a
CHAQUE `AttackDamage`. Les N `AttackDamage` d'un `Attack(...)` UNIQUE (ici les N reports de
`HazeOfCorruption_DamageTransferEffect$$CreateTargetTriggerBehaviour`) voient donc la mort de leur
cible AU MILIEU de la serie, alors que le natif les emet TOUS avant le drain.

Ce que ce probe rend, en plus de `probe_220_haze_bonded_chain.py` :
  * la VENTILATION des `genrand_int32` du port par call-site (quel etage tire, et combien) ;
  * la liste des `LeftOverDamage` de chaque relais au moment ou son bond est consomme.

CLI (depuis scripts/python) :
  python probe_hazeord_death_queue.py --seeds 777 --hp 1200
  python probe_hazeord_death_queue.py --seeds 777,5,21 --hp 1200,5000

Discipline runner : state-file ABSOLU sous logs/, board explicite, dispose en fin. ASCII only.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback

from probe_r6_round_materialize import _mkrpc, BOARD
from probe_159_ah_bounds import _board, _genrand_steps
from probe_207_haze_pool_ladder import EXTRAS, _drive_pool
from probe_220_haze_bonded_chain import _build, _units_map, _events, _dmg_rows, _bond_rows

# Frames a IGNORER quand on remonte la pile pour nommer le call-site d'un tirage : la couche RNG
# elle-meme et les enveloppes de dispatch qui ne DECIDENT rien.
_SKIP = ("prng.py", "probe_hazeord_death_queue.py")


def _site() -> str:
    """Le call-site LISIBLE du tirage courant : la premiere frame `engine/` sous la couche RNG,
    rendue `<fichier>:<fonction>`."""
    out = []
    for fr in reversed(traceback.extract_stack()[:-1]):
        fn = fr.filename.replace("\\", "/")
        if any(s in fn for s in _SKIP):
            continue
        if "/engine/" not in fn:
            continue
        out.append("%s:%s" % (fn.rsplit("/", 1)[-1], fr.name))
        if len(out) >= 3:
            break
    return " < ".join(out) if out else "?"


def _replay_traced(dv, ob, snap, board, rng0, cid, tid):
    """Rejoue l'attaque OFFLINE en VENTILANT chaque `genrand_int32` par call-site, et en tracant
    les `LeftOverDamage` lues par chaque consommation de bond 1077."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.operations import left_over_damage as _LOD
    from engine.runner.operations.triggers.loki import haze_of_corruption as _HZ

    st = load_state(dv, ob, snap, board=board)
    draws = []

    class _Tracing(IntBasedMersenneTwister):
        __slots__ = ()

        def genrand_int32(self):
            draws.append(_site())
            return IntBasedMersenneTwister.genrand_int32(self)

    rng = _Tracing()
    rng.mt = list(rng0["mt"])
    rng.mti = rng0["mti"]
    st.rng = rng

    reads, fires = [], []
    _orig_lod = _HZ.left_over_damages if hasattr(_HZ, "left_over_damages") else None

    _orig_exec = _HZ.HazeOfCorruptionDamageTransferTrigger.execute_behaviour

    def _spy_exec(self, state, ev, _o=_orig_exec):
        n0 = len(draws)
        reads.append({"relais": self.owner_id, "mort": ev.dying_id,
                      "leftover": [d.get("amount") for d in _LOD.left_over_damages(state, ev.dying_id)]})
        r = _o(self, state, ev)
        if r is not None:
            r = dict(r)
            r["draws"] = len(draws) - n0
            fires.append(r)
        return r

    _HZ.HazeOfCorruptionDamageTransferTrigger.execute_behaviour = _spy_exec
    try:
        runner = Runner(st).install_default_handlers(20)
        runner.apply(AttackUnitMessage(cid, tid))
    finally:
        _HZ.HazeOfCorruptionDamageTransferTrigger.execute_behaviour = _orig_exec
    ents = []
    for uid in list(st.entities.keys()):
        from engine.runner.components import HealthComponent, UnitComponent
        e = st.get_entity(uid)
        hc = e.get_component(HealthComponent)
        uc = e.get_component(UnitComponent)
        if hc is None:
            continue
        ents.append({"id": uid, "hp": hc.hp, "alive": (uc.alive if uc is not None else None),
                     "left_over": [d.get("amount") for d in _LOD.left_over_damages(st, uid)]})
    return {"n": len(draws), "draws": draws, "reads": reads, "fires": fires, "entities": ents}


def _run(rpc, seed, hp, armor, k):
    rid, sf = _build(seed, hp, armor)
    if rid is None:
        return None
    try:
        board = _board(rpc, rid)
        cid, tid, aid, err = _drive_pool(rpc, rid, board, k)
        if cid is None:
            print("[hazeord] seed %s hp=%s : drive KO -- %s" % (seed, hp, err))
            return None
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        before = _units_map(dv, snap)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": aid},
            "captureEvents": True}, 120)
        rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
        evs = _events(res)
        import hexgeo
        cpos, tpos = before[cid]["pos"], before[tid]["pos"]
        relays = [uid for uid, u in before.items()
                  if u["vis"] in EXTRAS and u["pos"] and u["pos"][0] is not None
                  and hexgeo.distance(tuple(u["pos"]), tuple(cpos)) == 1
                  and hexgeo.distance(tuple(u["pos"]), tuple(tpos)) == 1]
        off = _replay_traced(dv, ob, snap, board, rng0, cid, tid)
        return {"seed": seed, "hp": hp, "cid": cid, "tid": tid, "relays": relays,
                "n_native": _genrand_steps(rng0, rng1), "off": off,
                "dmg": _dmg_rows(evs), "bonds": _bond_rows(evs), "before": before}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


def _report(r):
    off = r["off"]
    ok = r["n_native"] == off["n"]
    print("[hazeord] seed %s hp=%s : caster=%s cible=%s relais=%s  genrand natif=%s port=%s  %s"
          % (r["seed"], r["hp"], r["cid"], r["tid"], r["relays"], r["n_native"], off["n"],
             "OK" if ok else "DIVERGE"))
    print("      degats LIVE (cible, montant, effT) = %s"
          % json.dumps([[d[0], d[1], d[2]] for d in r["dmg"]]))
    agg = {}
    for i, s in enumerate(off["draws"]):
        agg.setdefault(s, []).append(i)
    for s, idx in agg.items():
        print("      x%-2d  %-3s  %s" % (len(idx), len(idx), s))
    for rd in off["reads"]:
        print("      BOND consomme : relais=%s mort=%s leftOver_lus=%s"
              % (rd["relais"], rd["mort"], json.dumps(rd["leftover"])))
    for f in off["fires"]:
        print("      REPORT : relais=%s source=%s bonded=%s transfere=%s tirages=%s"
              % (f.get("unit"), f.get("source"), f.get("bonded"),
                 json.dumps(f.get("transferred")), f.get("draws")))
    for e in off["entities"]:
        if e["id"] in [r["tid"]] + r["relays"]:
            live = sum(m for (t, m, _e, _a, _p) in r["dmg"] if t == e["id"])
            print("      id=%-4s hp=%-6s alive=%-5s PORT dmg=%-6s LIVE dmg=%-6s leftOver=%s  %s"
                  % (e["id"], e["hp"], e["alive"], int(r["hp"]) - int(e["hp"] or 0), live,
                     json.dumps(e["left_over"]),
                     "OK" if (int(r["hp"]) - int(e["hp"] or 0)) == live else "DIVERGE"))
            ok = ok and (int(r["hp"]) - int(e["hp"] or 0)) == live
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="777")
    ap.add_argument("--hp", default="1200")
    ap.add_argument("--armor", type=int, default=0)
    ap.add_argument("--k", type=int, default=2)
    args = ap.parse_args()
    rpc = _mkrpc()
    rows, oks = [], 0
    for seed in [s for s in args.seeds.split(",") if s.strip()]:
        for hp in [int(h) for h in str(args.hp).split(",") if h.strip()]:
            r = _run(rpc, seed, hp, args.armor, args.k)
            if r is None:
                continue
            rows.append(r)
            oks += 1 if _report(r) else 0
    if not rows:
        print("[hazeord] aucun montage exploitable")
        return 1
    print()
    print("[hazeord] BILAN %d montages : %d/%d bit-exacts (RNG + degat par unite)"
          % (len(rows), oks, len(rows)))
    return 0 if oks == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
