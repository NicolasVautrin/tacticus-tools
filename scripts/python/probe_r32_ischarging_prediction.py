"""Probe case-r32 -- face PREDICTION du gate `IsCharging` (AvalancheOfMuscle 1025, `astraBullgryn`).

QUESTION TRANCHEE ICI (le COMBAT est verrouille par
`tests/engine/runner/test_ischarging_extra_damage_live.py`) : sur quoi la chaine de PREDICTION
native evalue-t-elle `IdunBattle.Core.Services.BattleQuery$$IsCharging` ? Le decompile ne suffit
pas -- `RecordedSimulationRequestsBattleQuery$$IsCharging` enveloppe l'appel dans
`RunWithoutSimulation<T>`, ce qui SUGGERE une lecture hors-simulation, mais rien ne dit que la
chaine display passe par CETTE query. On mesure les deux termes separement.

TROIS CAS, un `aiPlaybookPredict(col,row)` chacun (= l'oracle de DECISION,
`<Ability>Playbook.MakeDamagePredictions` -- PAS le preview `aiPredict`) :

  A CHARGE_CANDIDAT  caster a distance 2, tour NEUF (donc `ChargedUnitIds` VIDE) ; on predit depuis
                     une tuile ADJACENTE a la cible. Seul un pas SIMULE peut rendre `IsCharging` vrai.
  B CHARGE_ACQUISE   le caster JOUE ce pas ; on predit depuis sa tuile COURANTE (aucun pas
                     supplementaire). Seule la liste REELLE peut rendre `IsCharging` vrai. L'offline
                     est reconstruit du snapshot PRE-pas puis REJOUE le pas (`MoveUnitMessage`), donc
                     sa liste est celle du moteur -- jamais declaree a la main.
  C ADJ_NOCHG        caster DEJA adjacent, tour NEUF ; on predit depuis une AUTRE tuile adjacente a
                     la MEME cible. La cible n'est jamais « nouvellement adjacente » -> pas de charge,
                     alors que le proxy `has_moved` disait VRAI. C'est le cas discriminant.

Chaque ligne imprime aussi `off+chg` / `off-chg` (gate force) : le MATCH n'est probant que si les
deux bornes DIFFERENT, sinon il serait trivial (« aucun bonus des deux cotes »).

Usage (depuis scripts/python, session warmee) :
    python probe_r32_ischarging_prediction.py [--seed 777] [--board MC1_67]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo
import rl_collect_batch as R
from engine.entities.effects.magnitude import ability_var
from engine.entities.pathfinding.board import Board
from engine.playbook.scene import Scene
from engine.runner.messages import MoveUnitMessage
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

PYDIR = Path(__file__).resolve().parent


def rpc(sid, m, b=None, t=90):
    r = R._rpc(sid, m, [b] if b is not None else [], timeout=t)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def native_damage(sid, rid, uid, tgt, ab, tile):
    """`healthDmgMin` (= `AccurateHealthDamage.min`, cf. `engine_agreement_stages.
    _fields_from_native_event`) de l'event DAMAGE d'`aiPlaybookPredict` depuis `tile`.
    None = le natif ne rend pas la paire depuis cette tuile."""
    body = {"runnerId": rid, "unitId": uid, "targetId": tgt, "abilityType": int(ab)}
    if tile is not None:
        body["col"], body["row"] = int(tile[0]), int(tile[1])
    resp = rpc(sid, "aiPlaybookPredict", body, 60)
    if not (isinstance(resp, dict) and resp.get("ok")):
        return None
    evs = [e for e in (resp.get("events") or []) if e.get("targetId") in (None, tgt)]
    return int(evs[0].get("healthDmgMin") or 0) if evs else None


def offline_damage(state_factory, uid, tgt, tile, force_charge=None):
    """Prediction OFFLINE de l'attaque normale depuis `tile`. `state_factory()` rend un `State` NEUF
    (rejouable). `force_charge` (DIAG SEULEMENT) force le gate `IsCharging` -> borne A/B qui rend la
    contribution +extraDmg visible."""
    import engine.playbook.prediction.normal_attack as _na
    from engine.playbook.prediction import _shared
    from engine.playbook.prediction.normal_attack import make_normal_attack_predictions
    saved = _shared._prediction_is_charging
    if force_charge is not None:
        forced = (lambda *a, **k: bool(force_charge))
        _shared._prediction_is_charging = forced
        _na._prediction_is_charging = forced
    try:
        ev = make_normal_attack_predictions(Scene.from_state(state_factory()), uid, tgt,
                                            attack_pos=tile)
    finally:
        _shared._prediction_is_charging = saved
        _na._prediction_is_charging = saved
    pred = getattr(ev, "prediction", None) if ev is not None else None
    hd = getattr(pred, "accurate_health_damage", None) if pred is not None else None
    return int(getattr(hd, "min", 0) or 0) if hd is not None else None


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file",
                    default=str(Path(__file__).resolve().parents[2] /
                                "logs" / "runners" / "probe-r32-pred.json"))
    a = ap.parse_args(argv)

    sid = R._resolve_session()
    Path(a.state_file).parent.mkdir(parents=True, exist_ok=True)
    build = [sys.executable, "rl_duel.py", "build", "--seed", a.seed, "--board", a.board,
             "--state-file", a.state_file, "--p-units", "astraBullgryn",
             "--a-units", "necroOverlord,necroWarden", "--hp-target", "120000",
             "--hp-player", "120000", "--no-ai"]
    p = subprocess.run(build, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(a.state_file).exists():
        print("BUILD KO", (p.stderr or p.stdout)[-400:])
        return 1
    rid = json.loads(Path(a.state_file).read_text())["runnerId"]
    print("runner", rid)
    try:
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")

        def dview():
            return rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)

        def alive(dv=None):
            dv = dv if dv is not None else dview()
            return [u for u in (dv.get("units") or []) if u.get("alive")]

        def place(uid, c):
            rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": uid, "to": {"col": int(c[0]), "row": int(c[1])}}}, 40)
            u = next((x for x in alive() if x.get("id") == uid), None)
            return u is not None and _upos(u) == (int(c[0]), int(c[1]))

        def my_turn(player, tries=8):
            for _ in range(tries):
                if dview().get("currentPlayer") == player:
                    return True
                rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            return dview().get("currentPlayer") == player

        def snap3():
            return (dview(), rpc(sid, "observeBattle", {"runnerId": rid}, 40),
                    rpc(sid, "combatSnapshot", {"runnerId": rid}, 60))

        dv = dview()
        me = next(u for u in alive(dv) if u.get("visualId") == "astraBullgryn")
        myp = me.get("owner")
        ens = [u for u in alive(dv) if u.get("owner") != myp]
        tgt = ens[0]
        ab = next((x.get("id") for u in (dv.get("units") or []) if u.get("id") == me["id"]
                   for x in (u.get("abilities") or []) if x.get("kind") == "normal"), None)

        walk = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]

        def ring(c, r):
            return [q for q in walk if hexgeo.distance(c, q) == r]

        anchor = next((c for c in walk if len(ring(c, 1)) >= 3 and len(ring(c, 2)) >= 3), None)
        if anchor is None or not place(tgt["id"], anchor):
            print("ANCRE KO")
            return 1
        for other in ens[1:]:
            far = [q for q in ring(anchor, 4) if q != anchor]
            if far:
                place(other["id"], far[0])
        occ = {_upos(u) for u in alive() if u.get("id") != me["id"]}
        r1 = [q for q in ring(anchor, 1) if q not in occ]
        r2 = [q for q in ring(anchor, 2) if q not in occ]

        lvl = mult = bonus = None
        rows = []
        print("%-11s %-16s %-9s %-9s %-9s %-9s %s"
              % ("regime", "tuile", "natif", "off", "off+chg", "off-chg", "verdict"))

        def line(regime, tile, factory):
            nat = native_damage(sid, rid, me["id"], tgt["id"], ab, tile)
            off = offline_damage(factory, me["id"], tgt["id"], tile)
            on = offline_damage(factory, me["id"], tgt["id"], tile, force_charge=True)
            noc = offline_damage(factory, me["id"], tgt["id"], tile, force_charge=False)
            verdict = "MATCH" if nat == off else "DIFF"
            if on == noc:
                verdict += " (NON PROBANT: bornes egales)"
            rows.append((regime, tile, nat, off, on, noc))
            print("%-11s %-16s %-9s %-9s %-9s %-9s %s"
                  % (regime, str(tile), nat, off, on, noc, verdict))

        # --- A : CHARGE_CANDIDAT (depart a distance 2, tour NEUF, tuile candidate adjacente) -------
        start2 = next((s for s in r2 if any(hexgeo.distance(s, q) == 1 for q in r1)), None)
        cand = next((q for q in r1 if start2 and hexgeo.distance(start2, q) == 1), None)
        if start2 is None or cand is None or not place(me["id"], start2) or not my_turn(myp):
            print("cas A non montable")
        else:
            dvA, obA, snA = snap3()
            e0 = load_state(dvA, obA, snA, board=board).get_entity(me["id"])
            from engine.runner.components import StatsComponent
            c0 = e0.get_component(StatsComponent).ctx if e0 is not None else None
            lvl = getattr(c0, "passive_ability_level", None)
            mult = int(getattr(c0, "ability_variables_multiplier", 100) or 100)
            bonus = ability_var("AvalancheOfMuscle", "extraDmg", lvl, multiplier_pct=mult)
            print("caster=%s cible=%s@%s ability=%s | extraDmg[%s]x%s%% = %s (par coup)"
                  % (me["id"], tgt["id"], anchor, ab, lvl, mult, bonus))
            line("A CHARGE", cand, lambda: load_state(dvA, obA, snA, board=board))

            # --- B : CHARGE_ACQUISE (on JOUE le pas ; prediction depuis la tuile courante) --------
            if place(me["id"], cand):
                def _acquired():
                    st = load_state(dvA, obA, snA, board=board)     # snapshot PRE-pas
                    Runner(st).install_default_handlers().apply(
                        MoveUnitMessage(me["id"], tuple(cand)))      # le pas, REJOUE par le moteur
                    return st
                line("B ACQUISE", cand, _acquired)

        # --- C : ADJ_NOCHG (caster deja adjacent, tour NEUF, decalage vers une AUTRE tuile r1) -----
        pair = next(((s, q) for s in r1 for q in r1 if s != q and hexgeo.distance(s, q) == 1), None)
        # `endturn` INCONDITIONNEL avant de re-viser mon tour : c'est le
        # `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` qui VIDE `ChargedUnitIds`. Sans lui,
        # un `place` sur la tuile DEJA occupee par le caster ne consomme aucune activation, aucun cycle
        # n'a lieu, et la charge du cas B reste acquise -> le cas C mesurerait le cas B (piege vecu).
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        if pair is None or not place(me["id"], pair[0]) or not my_turn(myp):
            print("cas C non montable")
        else:
            dvC, obC, snC = snap3()
            if _upos(next(u for u in alive(dvC) if u["id"] == me["id"])) == pair[0]:
                # C1 -- tuile COURANTE : adjacent a la cible mais AUCUNE charge (tour neuf). C'est le
                # contre-cas de B : meme geometrie d'attaque, liste `ChargedUnitIds` vide -> le natif
                # doit rendre la valeur SANS le +extraDmg. C'est ce que l'ancien proxy `has_moved`
                # ne savait pas produire des lors que le caster avait bouge.
                line("C1 NOCHG", pair[0], lambda: load_state(dvC, obC, snC, board=board))
                # C2 -- decalage vers une AUTRE tuile adjacente a la MEME cible : la cible n'est
                # jamais « nouvellement adjacente ». Le natif n'enumere pas toujours cette paire
                # depuis cette tuile (natif=None) -> ligne informative.
                line("C2 ADJ_NOCHG", pair[1], lambda: load_state(dvC, obC, snC, board=board))

        print("bonus par coup = %s ; lignes = %s" % (bonus, [(r[0], r[2], r[3]) for r in rows]))
        return 0 if all(r[2] == r[3] for r in rows if r[2] is not None) else 1
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 20)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
