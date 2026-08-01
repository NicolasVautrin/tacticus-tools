#!/usr/bin/env python
"""probe #407-r1 (LIVE) -- le natif DESCEND-IL au block apres l'etage esquive ?

CE QUI EST CONFRONTABLE, ET CE QUI NE L'EST PAS. L'ordre porte par #407-r1 est une SEQUENCE :
`IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation` appelle le slot 3
`ApplyRandomEvasion`, puis le slot 2 `ApplyRandomBlockDamage` **si et seulement si l'esquive a
echoue** (`if (piVar28[1] == 0)`). Cette sequence a deux faces :

  * « l'esquive est evaluee AVANT le block » -- NON CONFRONTABLE : `CalculateEvasionChance` =
    `GetStat(unit, 0xf)` et AUCUNE unite n'arrive en bataille avec cette stat non nulle (5 voies,
    `probe_407r1_evasion_carriers.py`). A chance nulle l'esquive ne consomme rien et ne change
    rien -> les deux ordres coincident BIT-A-BIT. Aucun montage ne peut les separer.
  * « le block est ATTEINT quand l'esquive n'a pas eu lieu » -- CONFRONTABLE, et c'est ce que ce
    probe mesure. Le contrefactuel `xor` (`block_runs_after_evasion` rendu toujours `False`)
    supprime tout block : il consomme MOINS de tirages et decale tout le flux. Il doit diverger
    du live sur toute cible portant une source de block.

MONTAGE (le meme que #407, pour reutiliser un regime deja mesure) : `orksRuntherd` attaque au
CONTACT `ultraApothecary` en regime PERCAGE-DOMINANT (`--armor-target 6000`), cible porteuse d'une
source de block de BASE (`--block-target 25,40` : chance assez haute pour que le block MORDE
quelque part dans la fenetre) et `--crit 0,0` (aucun crit-roll : la seule variable du flux est le
block).

L'observable est la FENETRE de coups, jamais un point (piege mesure de #407 : le tirage en trop/en
moins est consomme APRES le resolve du coup courant, donc c'est le coup SUIVANT qui bouge).

Discipline runner : state-file UNIQUE en chemin ABSOLU sous logs/, `--board` explicite, dispose en
fin. ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import sys

from probe_r6_round_materialize import (_build, _drive_normal, _live_amounts,   # noqa: F401
                                        _mkrpc)

CARRIER = "orksRuntherd"
TARGET = "ultraApothecary"
BOARD = "MC1_67"


def replay_evasion_gate(dv, ob, snap, board, rng0, caster_id, target_id, moved):
    """Rejoue le MEME coup offline DEUX FOIS -- meme etat, meme flux RNG -- en ne faisant varier
    QUE le chainage `esquive -> block` (`engine.services.damage_combat.block_runs_after_evasion`).

    Rend `{"shipped": [...], "xor": [...], "arme_shipped": [...], "arme_xor": [...]}` :
      * `shipped` = le port TEL QU'IL EST LIVRE (aucune substitution) -- c'est LUI le cliquet ;
      * `xor`     = le contrefactuel, block plus jamais atteint apres l'etage esquive.
    Les per-coup rendus separent les coups d'ARME (`arme_*`, lus sur `damage_handler.last`) des
    coups des GROUPES additionnels (`shipped`/`xor`, captures sur `execute_additional_hits`), parce
    que le flux d'events live porte aussi ce qui SUIT l'attaque (spawn de SquigHound...)."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import set_moved_flag
    from engine.runner.operations import additional_hits as _ah_mod
    from engine.runner.operations.damage_ops import normal as _dnormal
    from engine.runner.operations.damage_ops import ability as _dability
    from engine.services import damage_combat as _dc

    def _one(mutate: bool):
        st = load_state(dv, ob, snap, board=board)
        if moved:
            set_moved_flag(st, caster_id)
        rng = IntBasedMersenneTwister()
        rng.mt = list(rng0["mt"])
        rng.mti = rng0["mti"]
        st.rng = rng
        per_hit: list = []
        arme: list = []
        o_gate = _dc.block_runs_after_evasion
        o_ah = _ah_mod.execute_additional_hits
        o_n, o_a = _dnormal.execute_additional_hits, _dability.execute_additional_hits

        def _rec(*a, **kw):
            out = o_ah(*a, **kw)
            if out:
                per_hit.extend(out.get("per_hit") or [])
            return out

        if mutate:
            _dc.block_runs_after_evasion = lambda _did_evade: False
        _ah_mod.execute_additional_hits = _rec
        _dnormal.execute_additional_hits = _rec
        _dability.execute_additional_hits = _rec
        try:
            runner = Runner(st).install_default_handlers(20)
            runner.apply(AttackUnitMessage(caster_id, target_id))
            last = getattr(getattr(runner, "damage_handler", None), "last", None)
            if isinstance(last, dict):
                arme.extend(last.get("per_hit") or [])
            return per_hit, arme
        finally:
            _dc.block_runs_after_evasion = o_gate
            _ah_mod.execute_additional_hits = o_ah
            _dnormal.execute_additional_hits = o_n
            _dability.execute_additional_hits = o_a

    ship, xor = _one(False), _one(True)
    return {"shipped": ship[0], "arme_shipped": ship[1],
            "xor": xor[0], "arme_xor": xor[1]}


def run_case(rpc, seed, block, armor):
    """Un montage complet : build -> drive -> attaque -> rejeu double. Rend un dict de mesure."""
    from engine.entities.pathfinding.board import Board
    rid, sf = _build(seed, CARRIER, TARGET,
                     extra=["--crit", "0,0", "--block-target", block,
                            "--armor-target", str(armor)])
    if rid is None:
        return {"seed": seed, "skip": "build KO"}
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            return {"seed": seed, "skip": "boardGraph indispo"}
        board = Board(bg["tiles"], adjacency="native_sym")
        cid, tid, moved = _drive_normal(rpc, rid, board, CARRIER, TARGET)
        if cid is None:
            return {"seed": seed, "skip": "pas de contact"}
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if not (isinstance(rng0, dict) and rng0.get("mt")):
            return {"seed": seed, "skip": "dumpRng indispo"}
        cu = next((u for u in (dv.get("units") or []) if u.get("id") == cid), {})
        nrm = next((a for a in (cu.get("abilities") or []) if a.get("kind") == "normal"), None)
        if nrm is None:
            return {"seed": seed, "skip": "pas d'attaque normale"}
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid,
            "abilityType": nrm["id"]}, "captureEvents": True}, 120)
        if not (isinstance(res, dict) and res.get("ok")):
            return {"seed": seed, "skip": "attaque KO %s" % str(res)[:100]}
        live, dirty = _live_amounts(res, tid)
        # L'esquive N'EST PAS attendue : `Attack_DidEvade` (TagKey 140) est le canal live qui le
        # dirait. On le remonte pour que la mesure DISE que le regime observe est bien `ev == 0`,
        # au lieu de le supposer.
        evaded = _any_evade(res, tid)
        off = replay_evasion_gate(dv, ob, snap, board, rng0, cid, tid, moved)
        return {"seed": seed, "live": live, "dirty": dirty, "evaded": evaded, **off}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass


def _any_evade(res, target_id) -> bool:
    """`Attack_DidEvade` (`IdunBattle.Streams.TagKey` 140) sur un event vise la cible : le canal
    LIVE d'observation d'une esquive. Il existe deja et ne demande AUCUN capteur neuf."""
    import json
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if td.get("Target_Id") == target_id and td.get("Attack_DidEvade"):
                return True
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", default="12345,314159,88,777,31337")
    ap.add_argument("--block", default="25,40",
                    help="BlockChance,BlockDamage forces sur la cible")
    ap.add_argument("--armor", type=int, default=6000)
    a = ap.parse_args()
    rpc = _mkrpc()
    n_disc = n_ship = n_xor = n_evade = 0
    n_cases = 0
    for seed in [s for s in a.seeds.split(",") if s]:
        m = run_case(rpc, seed, a.block, a.armor)
        if m.get("skip"):
            print("[%s] SKIP %s" % (seed, m["skip"]))
            continue
        n_cases += 1
        n_evade += int(bool(m["evaded"]))
        live, arme = m["live"], m["arme_shipped"]
        n = len(arme)
        print("[%s] live=%s arme_livre=%s arme_xor=%s dirty=%s evade_live=%s"
              % (seed, live, arme, m["arme_xor"], m["dirty"], m["evaded"]))
        print("      groupe: livre=%s xor=%s" % (m["shipped"], m["xor"]))
        # FENETRE COMPLETE = coups d'arme + groupe : c'est l'ensemble ou le tirage de block
        # manquant du contrefactuel decale le flux.
        win_ship = arme + m["shipped"]
        win_xor = m["arme_xor"] + m["xor"]
        w = len(win_ship)
        disc = win_ship != win_xor
        ok_ship = live[:w] == win_ship
        ok_xor = live[:w] == win_xor
        n_disc += int(disc)
        n_ship += int(ok_ship)
        n_xor += int(ok_xor)
        print("      fenetre live=%s | DISCRIMINANT=%s livre_ok=%s xor_ok=%s"
              % (live[:w], disc, ok_ship, ok_xor))
    print("TOTAL cas=%d discriminants=%d livre_ok=%d xor_ok=%d | esquives LIVE observees=%d"
          % (n_cases, n_disc, n_ship, n_xor, n_evade))
    print("ATTENDU : discriminants = cas, livre_ok = cas, xor_ok = 0, esquives = 0")
    print("  (esquives = 0 EST la mesure qui etablit `evasionChance == 0` en bataille reelle,")
    print("   via le canal `Attack_DidEvade` -- pas une supposition.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
