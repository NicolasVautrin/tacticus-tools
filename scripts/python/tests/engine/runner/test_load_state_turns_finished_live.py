"""CLIQUET #234 -- `load_state` CONSOMME `turnsFinished`, et le gate en depend REELLEMENT.

`combatSnapshot.units[].turnsFinished` (capteur #N11 : invoke de
`IdunBattle.Entities.UnitExtensions$$GetTurnsFinished(unit) -> Int32`) etait emis mais NON consomme :
`UnitComponent.turns_finished` restait a 0 sur tout etat monte par `load_state`. Le gate
`OwnerHasFinishedMinTurns` rendait donc FAUX sur une unite ayant pourtant fini N tours cote natif --
degradation RESTRICTIVE et silencieuse (le trigger ne fire jamais offline, aucune erreur).

CHAINE NATIVE (decompile = verite)
  `IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateTrigger`
    -> `IdunBattleLogic.Entities.DSLTriggers$$OwnerHasFinishedMinTurns(2)`
    -> `IdunBattle.Entities.Triggers.UnitHasFinishedMinTurnsAbilityTrigger$$ShouldTrigger`
         = `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished(Self@0x148) >= 2`
  ECRITURE du compteur : boucle de `IdunBattle.Operations.EndTurnOperation$$Execute` sur
  `PlayerComponent.CurrentlyOwnedUnitIds` (`+0x5c += 1`), AVANT le vecteur `On(0x17 = TurnEnd)`.

DEUX FACES, la seconde seule est discriminante SUR LE GATE :

  * SEED -- chaque unite du `State` doit porter EXACTEMENT le compteur natif. Garde de NON-VACUITE
    incluse : on exige au moins DEUX valeurs distinctes dans le meme snapshot (le joueur qui a fini
    un tour de plus que l'autre suffit), sinon l'egalite « tout le monde a 0 » passerait a vide.
  * GATE -- a la fin de tour d'AGE 1 d'un grot (`turnsFinished == 1`, le bump d'`EndTurnOperation` le
    porte a 2, `2 >= 2` -> gate OUVERT) le natif consomme >= 1 `genrand_int32` (le `Maybe`). Le port
    monte par `load_state` SEUL doit consommer AUTANT ; le MEME etat avec `turns_finished` remis a 0
    (l'etat d'AVANT ce fix) doit en consommer ZERO. C'est la contre-epreuve : si le seed disparait,
    ce test tombe.

Le grot (`orksNpc1Grot`, kind=summons, hors `--list-pool`) est amene par son summoner `orksRuntherd`
(passif `SquigHound` : 1 grot par attaque) -- seule voie d'entree en bataille d'un porteur de PileIn.

ASCII only (console cp1252).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))          # helpers siblings
from _pilein_owner_turns import (BOARD, CARRIER, ENEMY, ESCORT,        # noqa: E402
                                 CountingRng, count_genrand, drive_and_attack,
                                 pilein_units, _hp_full)

from engine.entities.pathfinding.board import Board                    # noqa: E402
from engine.runner.components import UnitComponent                     # noqa: E402
from engine.runner.operations.turnflow import EndTurnOperation         # noqa: E402
from engine.runner.snapshot import load_state                          # noqa: E402

PYDIR = Path(__file__).resolve().parents[3]
ROOT = PYDIR.parents[1]


def _grot_runner(rpc):
    """Runner PileIn (summoner + escorte vs deux ennemis gonfles, IA neutralisee). Rend `rid`."""
    sf = ROOT / "logs" / "runners" / ("turnsfinished-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "777", "--state-file", str(sf),
         "--board", BOARD, "--roster", "1", "--p-units", "%s,%s" % (CARRIER, ESCORT),
         "--a-units", "%s,%s" % (ENEMY, ENEMY), "--hp-target", "90000", "--hp-player", "90000",
         "--no-ai"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        pytest.skip("build KO: " + (proc.stderr or proc.stdout or "")[-300:])
    rid = json.loads(sf.read_text())["runnerId"]
    sf.unlink(missing_ok=True)
    return rid


def test_turns_finished_is_seeded_per_unit_from_the_live_counter(rpc):
    """FACE SEED -- apres quelques fins de tour, chaque unite du `State` porte EXACTEMENT le
    `turnsFinished` natif, et le snapshot en porte au moins DEUX valeurs distinctes (non-vacuite)."""
    rid = _grot_runner(rpc)
    try:
        for _ in range(5):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")

        live = {u.get("entityId"): u.get("turnsFinished") for u in (snap.get("units") or [])}
        assert live and None not in live.values(), (
            "le capteur doit rendre un ENTIER par unite (None = `GetTurnsFinished` non resolue) : %s"
            % live)
        assert len(set(live.values())) >= 2, (
            "scenario NON DISCRIMINANT : une seule valeur de turnsFinished (%s) -- l'egalite "
            "live/port passerait a vide" % sorted(set(live.values())))

        st = load_state(dv, ob, snap, board=board)
        got = {}
        for eid in live:
            e = st.get_entity(eid)
            uc = e.get_component(UnitComponent) if e is not None else None
            if uc is not None:
                got[eid] = int(uc.turns_finished or 0)
        assert got, "aucune unite du snapshot n'a de UnitComponent dans l'etat charge"
        assert got == {k: int(v) for k, v in live.items() if k in got}, (
            "`load_state` ne reporte pas turnsFinished -- live=%s port=%s"
            % ({k: live[k] for k in got}, got))
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)


def test_pilein_gate_verdict_follows_the_seed_live(rpc):
    """FACE GATE -- a l'age 1 du grot, le port monte par `load_state` SEUL accorde au natif, et le
    MEME etat prive du seed (`turns_finished` remis a 0) rend le verdict OPPOSE.

    L'age 0 est joint comme TEMOIN : le gate y est ferme dans les trois regimes, donc il ne SEPARE
    pas -- c'est l'age 1 qui porte la preuve."""
    rid = _grot_runner(rpc)
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")

        def dview():
            return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)

        dv = dview()
        me = next((u for u in (dv.get("units") or []) if u.get("visualId") == CARRIER), None)
        if me is None:
            pytest.skip("%s absent du runner" % CARRIER)
        mine = me["owner"]

        found = None
        birth, my_endturns, attacked = {}, 0, False
        for _ in range(16):
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
            if my_endturns - birth[first] != 1:            # seul l'age 1 SEPARE
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
                my_endturns += 1
                continue

            ob = rpc("observeBattle", {"runnerId": rid}, 60)
            snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
            rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
            assert all(_hp_full(ob, g) for g in grots), (
                "co-gate `IsUnitWithStatAmount(Health Cur==Max)` NON satisfait : un 0 tirage ne "
                "prouverait rien (il viendrait du co-gate, pas du gate d'age)")
            snap_tf = next((u.get("turnsFinished") for u in (snap.get("units") or [])
                            if u.get("entityId") == first), None)
            assert snap_tf == 1, (
                "le grot d'age 1 doit porter turnsFinished == 1 cote natif, obtenu %s" % snap_tf)

            def _replay(zero_out):
                st = load_state(dv, ob, snap, board=board)
                if zero_out:
                    for e in st.entities.values():
                        uc = e.get_component(UnitComponent)
                        if uc is not None:
                            uc.turns_finished = 0
                rr = CountingRng()
                rr.mt = list(rng0["mt"])
                rr.mti = int(rng0["mti"])
                st.rng = rr
                EndTurnOperation.execute(st, advance=False)
                return rr.rolls

            after, before = _replay(False), _replay(True)
            act = rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            assert isinstance(act, dict) and act.get("ok"), "endturn refuse: %s" % str(act)[:160]
            rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
            found = (count_genrand(rng0, rng1), after, before)
            break

        if found is None:
            pytest.skip("age 1 du grot non atteint en 16 tours")
        live, after, before = found
        assert live is not None and live >= 1, (
            "montage NON DISCRIMINANT : le natif n'a consomme aucun tirage a l'age 1 (live=%s) -- "
            "le gate y est cense etre OUVERT" % (live,))
        assert before == 0, (
            "contre-epreuve mal montee : sans le seed le gate devait rester FERME (0 tirage), "
            "obtenu %d" % before)
        assert after == live, (
            "`load_state` seul doit rendre le MEME verdict que le natif : live=%d port=%d "
            "(sans-seed=%d)" % (live, after, before))
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
