"""PROBE #234 -- `load_state` consomme-t-il `turnsFinished` ? (gate `OwnerHasFinishedMinTurns`)

CRITERE (binaire) : apres `load_state` d'une capture ou une unite a termine N tours cote natif,
le gate `OwnerHasFinishedMinTurns` rend-il le MEME verdict que le natif ?

Le gate porte vit dans `engine/runner/operations/triggers/dispatch/turn.py`
(`PILEIN_MIN_OWNER_TURNS = 2`), et sa chaine native est :

    `IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateTrigger`
      -> `IdunBattleLogic.Entities.DSLTriggers$$OwnerHasFinishedMinTurns(2)`
      -> `IdunBattle.Entities.Triggers.UnitHasFinishedMinTurnsAbilityTrigger$$ShouldTrigger`
           = `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished(Self@0x148) >= 2`
    ECRITURE du compteur : boucle de `IdunBattle.Operations.EndTurnOperation$$Execute` sur
    `PlayerComponent.CurrentlyOwnedUnitIds` (`+0x5c += 1`), AVANT l'execution de `On(0x17)`.

DEUX PARTIES, la seconde seule est DISCRIMINANTE sur le GATE :

  A. SEED -- `combatSnapshot.units[].turnsFinished` (canal deja emis, #N11) est-il reporte sur
     `UnitComponent.turns_finished` par `load_state` ? Critere FORT : au moins DEUX valeurs
     distinctes coexistent dans le meme snapshot (le joueur qui a fini un tour de plus que
     l'autre suffit), et chaque unite du port porte EXACTEMENT la valeur live. Une egalite sur
     un snapshot ou tout le monde vaut 0 ne prouverait rien.

  B. GATE -- montage PileIn. On fait naitre UN grot (`orksNpc1Grot`, kind=summons, amene par son
     summoner `orksRuntherd` dont le passif `SquigHound` en spawne un par attaque), on le laisse
     vieillir, puis a la fin de tour d'AGE 1 on compte les `genrand_int32` consommes par :
       LIVE        : le `endturn` natif (re-simulation du MT entre deux `dumpRng`) ;
       PORT-APRES  : `EndTurnOperation.execute` sur un etat monte par `load_state` SEUL -- aucun
                     seed manuel de `turns_finished`, c'est tout l'objet du fix ;
       PORT-AVANT  : le MEME etat avec `turns_finished` force a 0 sur toutes les unites, soit
                     EXACTEMENT ce que `load_state` laissait avant le fix.
     Le seuil SEPARE a l'age 1 : le grot a `turnsFinished == 1`, le bump d'`EndTurnOperation` le
     porte a 2, `2 >= 2` -> gate OUVERT. Avec 0 en entree, le bump ne donne que 1 -> gate FERME.
     L'age 0 est joint comme TEMOIN (les trois regimes doivent y rendre 0 : gate ferme partout).

Usage : python probe_234_turnsfinished_seed.py [--seed 777] [--board MC1_67] [--part all|seed|gate]
ASCII only.
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

import rl_collect_batch as R                                       # noqa: E402
from engine.entities.pathfinding.board import Board                # noqa: E402
from engine.runner.components import UnitComponent                 # noqa: E402
from engine.runner.snapshot import load_state                      # noqa: E402
from tests.engine.runner._pilein_owner_turns import (              # noqa: E402
    BOARD, CARRIER, ENEMY, ESCORT, CountingRng, count_genrand, drive_and_attack,
    pilein_units, _hp_full)


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


# --------------------------------------------------------------------------- A. SEED

def part_seed(rpc, rid, endturns=5):
    """Joue `endturns` fins de tour puis confronte `combatSnapshot.units[].turnsFinished` a
    `UnitComponent.turns_finished` de l'etat monte par `load_state`. Rend (ok, detail)."""
    for _ in range(endturns):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym")

    live = {}
    for u in (snap.get("units") or []):
        live[u.get("entityId")] = u.get("turnsFinished")
    if None in live.values():
        n = sum(1 for v in live.values() if v is None)
        print("[A] ECHEC : turnsFinished vaut None sur %d unite(s) -- methode native non resolue" % n)
        return False, {}
    distinct = sorted(set(live.values()))
    print("[A] live turnsFinished, distribution : " + "  ".join(
        "tf=%s -> %d unite(s)" % (v, sum(1 for x in live.values() if x == v)) for v in distinct))
    if len(distinct) < 2:
        print("[A] NON DISCRIMINE : une seule valeur (%s). Le seed ne se distingue pas d'un no-op."
              % distinct[0])
        return False, {}

    st = load_state(dv, ob, snap, board=board)
    bad = []
    seen = 0
    for eid, tf in live.items():
        e = st.get_entity(eid)
        uc = e.get_component(UnitComponent) if e is not None else None
        if uc is None:
            continue
        seen += 1
        if int(uc.turns_finished or 0) != int(tf):
            bad.append((eid, tf, uc.turns_finished))
    print("[A] port apres load_state : %d/%d unites confrontees, %d ecart(s)" % (seen, len(live), len(bad)))
    for eid, tf, got in bad[:8]:
        print("    ECART unite %s : live=%s port=%s" % (eid, tf, got))
    ok = seen > 0 and not bad
    print("[A] %s" % ("OK : chaque unite porte EXACTEMENT son compteur natif." if ok
                     else "ECHEC : le seed ne reproduit pas le compteur natif."))
    return ok, live


# --------------------------------------------------------------------------- B. GATE

def _sweep_gate(rpc, rid, ages=(0, 1), max_turns=16):
    """Mesure, aux fins de tour d'age `ages` du MEME grot, les rolls LIVE / PORT-APRES / PORT-AVANT.

    PORT-APRES = `load_state` SEUL (le fix). PORT-AVANT = le meme etat avec `turns_finished`
    remis a 0 partout (ce que `load_state` laissait avant). Rend (records, why)."""
    from engine.runner.operations.turnflow import EndTurnOperation

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym")

    def dview():
        return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)

    dv = dview()
    me = next((u for u in (dv.get("units") or []) if u.get("visualId") == CARRIER), None)
    if me is None:
        return [], "%s absent du runner" % CARRIER
    mine = me["owner"]

    records, want, birth = [], sorted(set(int(a) for a in ages)), {}
    my_endturns, attacked = 0, False
    for _ in range(max_turns):
        dv = dview()
        if dv.get("currentPlayer") != mine:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        grots = pilein_units(dv, mine)
        if not grots and not attacked:
            attacked = drive_and_attack(rpc, rid, board, mine)
            dv = dview()
            grots = pilein_units(dv, mine)
        for uid in grots:
            birth.setdefault(uid, my_endturns)
        if not grots:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            my_endturns += 1
            continue
        first = min(grots, key=lambda u: (birth[u], u))
        age = my_endturns - birth[first]
        if age not in want:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            my_endturns += 1
            continue

        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
        full_hp = all(_hp_full(ob, g) for g in grots)
        snap_tf = {u.get("entityId"): u.get("turnsFinished") for u in (snap.get("units") or [])}

        def _replay(zero_out, rng_seed=None):
            """Un `EndTurn` du port sur un etat FRAIS monte par `load_state`. `zero_out=True` remet
            `turns_finished` a 0 partout (regime d'AVANT le fix). `rng_seed=None` -> le MEME etat MT
            que le live (confront) ; un entier -> un flux PRNG offline arbitraire (balayage)."""
            st = load_state(dv, ob, snap, board=board)
            if zero_out:
                for e in st.entities.values():
                    uc = e.get_component(UnitComponent)
                    if uc is not None:
                        uc.turns_finished = 0
            rr = CountingRng(rng_seed) if rng_seed is not None else CountingRng()
            if rng_seed is None:
                rr.mt = list(rng0["mt"])
                rr.mti = int(rng0["mti"])
            st.rng = rr
            res = EndTurnOperation.execute(st, advance=False)
            spawned = sum(len(o.get("spawned") or ()) for o in (res.get("pilein") or [])
                          if isinstance(o, dict) and "grot" in o)
            g = st.get_entity(first)
            guc = g.get_component(UnitComponent) if g is not None else None
            return rr.rolls, spawned, (guc.turns_finished if guc is not None else None)

        after_rolls, after_spawn, after_tf = _replay(False)
        before_rolls, before_spawn, _ = _replay(True)

        # OBSERVABLE DE CARDINALITE (plus fort qu'un compte de tirages) : sur un flux PRNG OFFLINE
        # ou le `Maybe` REUSSIT, l'etat seede spawne une replique -- une ENTITE de plus dans le
        # `State` -- la ou l'etat prive du seed n'en spawne aucune. On balaie des graines jusqu'a
        # en trouver une qui reussisse (le `Maybe` vaut 75% - 5 x #grots).
        card = None
        for k in range(64):
            a_rolls, a_sp, _ = _replay(False, rng_seed=k)
            if a_sp:
                b_rolls, b_sp, _ = _replay(True, rng_seed=k)
                card = {"seed": k, "after_spawn": a_sp, "before_spawn": b_sp,
                        "after_rolls": a_rolls, "before_rolls": b_rolls}
                break

        act = rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
        my_endturns += 1
        if not (isinstance(act, dict) and act.get("ok")):
            return records, "endturn refuse: %s" % str(act)[:160]
        rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
        live_rolls = count_genrand(rng0, rng1)
        live_spawn = len(pilein_units(dview(), mine) - grots)

        records.append({"age": age, "grot": first, "full_hp": full_hp,
                        "snap_tf": snap_tf.get(first), "port_tf_after_bump": after_tf,
                        "live_rolls": live_rolls, "after_rolls": after_rolls,
                        "before_rolls": before_rolls, "live_spawn": live_spawn,
                        "after_spawn": after_spawn, "before_spawn": before_spawn,
                        "card": card})
        want.remove(age)
        if not want:
            return records, ""
    return records, "ages non atteints en %d tours: %s" % (max_turns, want)


def part_gate(rpc, rid):
    records, why = _sweep_gate(rpc, rid, ages=(0, 1))
    if why:
        print("[B] NOTE:", why)
    print("")
    print("  age | PV pleins | snap tf | LIVE | PORT-APRES | PORT-AVANT | spawn live/apres/avant")
    print("  ----+-----------+---------+------+------------+------------+-----------------------")
    for rec in sorted(records, key=lambda r: r["age"]):
        print("   %2d |    %-5s  |   %3s   | %4s |    %4d    |    %4d    |     %d / %d / %d"
              % (rec["age"], "OUI" if rec["full_hp"] else "NON", rec["snap_tf"],
                 rec["live_rolls"], rec["after_rolls"], rec["before_rolls"],
                 rec["live_spawn"], rec["after_spawn"], rec["before_spawn"]))
    print("")
    by = {r["age"]: r for r in records}
    if 1 not in by:
        print("[B] INDETERMINE : l'age 1 (le seul point ou le seuil SEPARE) n'a pas ete atteint.")
        return False
    a1 = by[1]
    if not a1["full_hp"]:
        print("[B] INDETERMINE : co-gate PV pleins NON satisfait a l'age 1 -- un 0 ne prouverait rien.")
        return False
    sep = a1["live_rolls"] >= 1 and a1["before_rolls"] == 0
    acc = a1["after_rolls"] == a1["live_rolls"]
    print("[B] age 1 -- le seuil SEPARE : %s (live=%s, port-AVANT=%d)"
          % (sep, a1["live_rolls"], a1["before_rolls"]))
    print("[B] age 1 -- PORT-APRES accorde au natif : %s (%d vs %s)"
          % (acc, a1["after_rolls"], a1["live_rolls"]))
    if 0 in by:
        a0 = by[0]
        print("[B] age 0 (temoin) -- les trois regimes rendent 0 : %s (%s/%d/%d)"
              % (a0["live_rolls"] == 0 and a0["after_rolls"] == 0 and a0["before_rolls"] == 0,
                 a0["live_rolls"], a0["after_rolls"], a0["before_rolls"]))
    card = a1.get("card")
    if card is None:
        print("[B] CARDINALITE : aucune graine sur 64 n'a fait REUSSIR le `Maybe` -- observable de"
              " spawn non exerce (le compte de tirages reste, lui, discriminant).")
    else:
        print("[B] CARDINALITE (flux PRNG offline, graine %d) -- avec seed : %d replique(s) spawnee(s)"
              " / sans seed : %d ; rolls %d vs %d"
              % (card["seed"], card["after_spawn"], card["before_spawn"],
                 card["after_rolls"], card["before_rolls"]))
        print("[B] le seed change le RESULTAT OBSERVABLE (entites), pas seulement le flux : %s"
              % (card["after_spawn"] >= 1 and card["before_spawn"] == 0))
    ok = sep and acc
    print("[B] %s" % ("OK : le gate rend le MEME verdict que le natif sur etat charge."
                     if ok else "ECHEC : verdict du gate non conforme."))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--part", choices=("all", "seed", "gate"), default="all")
    args = ap.parse_args()

    sid = R._resolve_session()
    w = _unwrap(R._rpc(sid, "warmupGameSingletons", [{}], timeout=180))
    if not (isinstance(w, dict) and w.get("ok")):
        print("warmup KO:", str(w)[:200])
        return 2
    print("session %s warmup=%s" % (sid, w.get("skipped") or "done"))

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    ok = True
    for part in (("seed", "gate") if args.part == "all" else (args.part,)):
        sf = ROOT / "logs" / "runners" / ("probe-234-%s-%s.json" % (part, uuid.uuid4().hex[:8]))
        sf.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [sys.executable, "rl_duel.py", "build", "--seed", str(args.seed),
             "--state-file", str(sf), "--board", args.board, "--roster", "1",
             "--p-units", "%s,%s" % (CARRIER, ESCORT), "--a-units", "%s,%s" % (ENEMY, ENEMY),
             "--hp-target", "90000", "--hp-player", "90000", "--no-ai"],
            cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if not sf.exists():
            print("build KO (%s):" % part, (proc.stderr or proc.stdout or "")[-400:])
            return 2
        rid = json.loads(sf.read_text())["runnerId"]
        print("runner %d (seed %s, board %s, partie %s)" % (rid, args.seed, args.board, part))
        try:
            ok &= (part_seed(rpc, rid)[0] if part == "seed" else part_gate(rpc, rid))
        finally:
            rpc("disposeRunner", {"runnerId": rid}, 20)
            sf.unlink(missing_ok=True)
    print("VERDICT : " + ("OK" if ok else "INCOMPLET"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
