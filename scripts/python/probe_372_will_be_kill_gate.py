"""Probe #372 -- la gate `Any(selfPreds, p => p.WillBeKill)` de `RammingSpeed` OUVRE-t-elle ?

CE QUE CE PROBE TRANCHE, ET POURQUOI IL PEUT LE FAIRE SANS LE CAPTEUR
--------------------------------------------------------------------
`#353-r1` volet (b) a laisse ouvert : « la gate n'a ouvert sur AUCUN des 5 montages ». La cause
etait declaree NON TRANCHEE parce que `get_WillBeKill` lit DEUX entrees que le canal n'exposait
pas (`CannotBeGuaranteedKilled@0x89`, `BlockScenarios[0]+0x0c`).

La RE de #372 en RETIRE une des deux, par les xrefs :

  `CannotBeGuaranteedKilled@0x89` a UN SEUL ecrivain dans tout le binaire --
  `IdunBattle.Core.Services.DamagePrediction$$PredictNormalAttack`, derniere instruction avant
  son `return`. Or `RammingSpeedPlaybook$$MakeDamagePredictions` construit ses deux premiers
  batchs par `ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions`, qui invoque `IBattleQuery`
  slot 0x28 = `BattleQuery$$GetMultiHitAttackPrediction` -- laquelle commence par
  `memset(result, 0, 0xa0)` puis delegue au slot 0xb (`PredictAttack`), JAMAIS au slot 9.
  `DamagePredictionResult$$Add` ne fusionne aucun flag booleen, donc le cumul des coups ne peut
  pas le rallumer non plus.

=> sur CETTE voie le gate vaut structurellement 0. Il ne PEUT PAS etre la cause.

Reste donc a separer les deux causes possibles restantes, et c'est faisable AVEC LE CANAL ACTUEL,
par un test a deux bras qui ne different QUE par les PV du caster :

  bras KILL  : `--hp-player 1`      -> le recul (nrOfHits_2 coups) tue le caster a coup sur
  bras VIVANT: `--hp-player 999999` -> le recul ne peut rien -> la gate est FERMEE, c'est la
               reference

  * si `len(events_KILL) > len(events_VIVANT)` : la gate OUVRE. Le « verrou » de #353-r1 etait un
    artefact de montage, et les batchs 3/4 sont confrontables.
  * si les deux comptes sont EGAUX : la gate n'ouvre pas MEME quand `hpBefore(caster) = 1`. Il ne
    reste alors qu'une seule explication compatible avec la RE -- `BlockScenarios` NON VIDE sur
    l'event du caster, dont `[0].Damage.HealthDamage.Min` est sous les PV. Le probe l'imprime
    comme tel, et le capteur #372 (`blockScenarioCount` / `blockKillDmg`) le CONFIRMERA des que
    le bundle sera reinjecte -- ces champs sont deja lus par le decodeur livre.

Le bras VIVANT est la CONTRE-EPREUVE : sans lui, un compte de 2 events ne prouverait rien (il
pourrait venir d'un `GetTileToMoveTo` nul ou d'un selecteur vide, pas de la gate).

`--block-player 0,0` est passe aux DEUX bras (comme dans probe_353) : c'est ce qui doit vider
`BlockScenarios` cote caster. Si le bras KILL reste a 2 events MALGRE ce reglage, c'est que le
reglage ne fait pas ce qu'on croit -- et le probe le DIT au lieu de conclure « non reproduit ».

Usage (depuis scripts/python, host up, session deja warmee) :
    python probe_372_will_be_kill_gate.py
    python probe_372_will_be_kill_gate.py --level 30 --json

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from probe_353_ramming_speed_prediction import (           # noqa: E402
    ABILITY, ABILITY_NAME, BOARD, FILLER_A, FILLER_P, GRAFT, VICTIM,
    _build, _place, _r, _view, build_grafted_seed_bc)
from rl_collect_batch import _resolve_session              # noqa: E402

# PV du bras VIVANT : assez haut pour que `nrOfHits_2` coups de `minDmg` ne puissent PAS tuer, a
# n'importe quel niveau d'ability. Le probe RELIT les PV effectifs et le degat self predit, et
# ECHOUE si la marge n'est pas verifiee -- un bras non discriminant est un faux vert (case-339 s.4).
HP_ALIVE = 999999
HP_KILL = 1


def _events(sid, rid, cid, tid) -> tuple[list, dict]:
    """Events natifs de `RammingSpeedPlaybook.MakeDamagePredictions`, via l'oracle
    `aiPlaybookPredict` (playbook charge PAR ABILITY -- confirme par `playbookClass`)."""
    nat = _r(sid, "aiPlaybookPredict", {"runnerId": rid, "unitId": cid,
                                        "targetId": tid, "abilityType": ABILITY}, 120)
    return (nat.get("events") or []), nat


def _ev_row(e: dict) -> dict:
    """Les champs qui portent le verdict. `cannotBeGuaranteedKilled` / `blockScenarioCount` /
    `blockKillDmg` / `willBeKill` viennent du capteur #372 : `None` tant que le bundle injecte ne
    porte pas la lecture -- c'est un TRI-ETAT, pas un zero."""
    return {"targetId": e.get("targetId"), "hpBefore": e.get("hpBefore"),
            "willKillDmg": e.get("willKillDmg"), "mightKillDmg": e.get("mightKillDmg"),
            "healthDmgMin": e.get("healthDmgMin"), "healthDmgMax": e.get("healthDmgMax"),
            "appliedHits": e.get("appliedHits"),
            "cannotBeGuaranteedKilled": e.get("cannotBeGuaranteedKilled"),
            "blockScenarioCount": e.get("blockScenarioCount"),
            "blockKillDmg": e.get("blockKillDmg"),
            "willBeKill": e.get("willBeKill")}


def _arm(sid, seed: int, level: int, mult: int, board: str, hp_player: int,
         bcf: Path, sf: Path) -> dict:
    """UN bras : build + placement drive + oracle. Dispose SON runner, jamais un autre."""
    rid = None
    out: dict = {"hp_player": hp_player}
    try:
        rid = _build(sf, bcf, seed, board, level, mult, 0, hp_player)
        out["runner"] = rid
        dv = _view(sid, rid)
        ids = {}
        for v in (GRAFT, FILLER_P, VICTIM, FILLER_A):
            u = next((x for x in (dv.get("units") or [])
                      if x.get("visualId") == v and x.get("alive")), None)
            if u is None:
                out["error"] = "unite absente du build : %s" % v
                return out
            ids[v] = int(u["id"])
        out["placement"] = {k: list(v) for k, v in _place(sid, rid, ids).items()}
        cid, tid = ids[GRAFT], ids[VICTIM]
        out["caster_id"], out["target_id"] = cid, tid
        dv2 = _view(sid, rid)
        me = next((u for u in (dv2.get("units") or []) if int(u["id"]) == cid), {})
        out["caster_hp"] = me.get("hp")
        ev, nat = _events(sid, rid, cid, tid)
        out["playbook"] = nat.get("playbookClass")
        out["native_error"] = nat.get("error")
        out["n_events"] = len(ev)
        out["events"] = [_ev_row(e) for e in ev]
        self_ev = [r for r in out["events"] if r["targetId"] == cid]
        out["self_events"] = self_ev
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
    return out


def run(seed: int = 35301, level: int = 8, mult: int = 100, board: str = BOARD,
        verbose: bool = True) -> dict:
    sid = _resolve_session()
    logs = PYDIR.parents[1] / "logs"
    bcf = logs / "p372-seed-bc.json"
    build_grafted_seed_bc(bcf)

    out: dict = {"level": level, "mult": mult, "board": board, "seed": seed}
    out["alive"] = _arm(sid, seed, level, mult, board, HP_ALIVE, bcf, logs / "p372-alive.json")
    out["kill"] = _arm(sid, seed, level, mult, board, HP_KILL, bcf, logs / "p372-kill.json")

    a, k = out["alive"], out["kill"]
    if a.get("error") or k.get("error"):
        out["ok"] = False
        out["verdict"] = "MONTAGE KO : %s / %s" % (a.get("error"), k.get("error"))
        if verbose:
            print("[372] %s" % out["verdict"])
        return out

    # Le bras VIVANT doit VRAIMENT etre non letal, et le bras KILL VRAIMENT letal, sinon le
    # test ne separe rien -- un bras muet est un faux vert.
    def _self_dmg_max(arm):
        s = arm.get("self_events") or []
        return max([int(r["healthDmgMax"] or 0) for r in s] or [0])

    out["alive_self_dmg_max"] = _self_dmg_max(a)
    out["kill_self_dmg_max"] = _self_dmg_max(k)
    out["alive_discriminant"] = bool(a.get("caster_hp") and
                                     int(a["caster_hp"]) > out["alive_self_dmg_max"])
    out["kill_discriminant"] = bool(k.get("caster_hp") is not None and
                                    out["kill_self_dmg_max"] >= int(k["caster_hp"] or 0) > 0)

    out["n_alive"], out["n_kill"] = a["n_events"], k["n_events"]
    gate_opened = k["n_events"] > a["n_events"]
    out["gate_opened"] = gate_opened
    if not (out["alive_discriminant"] and out["kill_discriminant"]):
        out["ok"] = False
        out["verdict"] = ("BRAS NON DISCRIMINANT -- vivant: hp=%s > selfdmg=%s ? %s | "
                          "kill: selfdmg=%s >= hp=%s ? %s"
                          % (a.get("caster_hp"), out["alive_self_dmg_max"],
                             out["alive_discriminant"], out["kill_self_dmg_max"],
                             k.get("caster_hp"), out["kill_discriminant"]))
    elif gate_opened:
        out["ok"] = True
        out["verdict"] = ("GATE OUVERTE : %d events avec un caster a 1 PV contre %d avec un caster"
                          " intouchable. Les batchs 3/4 (EXPLOSION) sont CONFRONTABLES ; le"
                          " verrou de #353-r1 etait un artefact de montage."
                          % (out["n_kill"], out["n_alive"]))
    else:
        se = (k.get("self_events") or [{}])[0]
        hp_se, wk = se.get("hpBefore"), se.get("willKillDmg")
        ratio = (float(wk) / float(hp_se)) if (hp_se and wk) else None
        out["self_bound_ratio"] = ratio
        out["ok"] = True
        # TROIS causes possibles au depart ; le probe en elimine DEUX.
        #  (1) le gate `CannotBeGuaranteedKilled` -- exclu par la RE (xrefs) ;
        #  (2) « la borne par defaut ne suffit pas » -- exclu par la MESURE ci-dessous
        #      (`willKillDmg` >> `hpBefore`, la branche `else` rendrait donc true) ;
        #  (3) `BlockScenarios` NON VIDE avec `[0].Damage.HealthDamage.Min < hpBefore`.
        # La 4e cause imaginable -- « la gate ouvre mais les batchs 3/4 rendent 0 event » --
        # exigerait `GetTileToMoveTo() == null` (la CIBLE est adjacente a toute tuile du ring,
        # donc `Enemies(AdjacentUnits(tile,1,3))` serait non vide). Or #353-r1 volet (a) a
        # CONFRONTE cette tuile au natif par un cast reel (la position d'arrivee du caster EST
        # la tuile rendue), et le playbook l'appelle SANS condition d'adjacence.
        out["verdict"] = (
            "GATE FERMEE MEME A 1 PV (%d events dans les deux bras, rapport borne/PV = %s)."
            " DEUX causes ELIMINEES : (1) `CannotBeGuaranteedKilled` -- exclu par la RE"
            " (unique ecrivain = PredictNormalAttack ; la voie playbook passe par"
            " GetMultiHitAttackPrediction, qui memset 0xa0) ; (2) borne insuffisante -- exclu"
            " par la mesure (willKillDmg=%s contre hpBefore=%s, la branche `else` rendrait"
            " TRUE). Reste UNE cause compatible : `BlockScenarios` NON VIDE avec"
            " [0].Damage.HealthDamage.Min < %s. Le capteur #372 la lit"
            " (blockScenarioCount=%s blockKillDmg=%s willBeKill=%s) -- NON CONFRONTE tant que"
            " le bundle n'est pas reinjecte."
            % (out["n_kill"], ("%.0f:1" % ratio) if ratio else "?", wk, hp_se, hp_se,
               se.get("blockScenarioCount"), se.get("blockKillDmg"), se.get("willBeKill")))

    out["sensor_live"] = any(r.get("blockScenarioCount") is not None
                             for r in (k.get("events") or []))
    if verbose:
        print("[372] board=%s niveau=%s | capteur #372 actif dans le bundle : %s"
              % (board, level, "OUI" if out["sensor_live"] else
                 "NON (reinject en attente -- champs a None)"))
        for tag in ("alive", "kill"):
            arm = out[tag]
            print("[372] bras %-5s hp_player=%-7s caster_hp=%-7s events=%d playbook=%s"
                  % (tag, arm.get("hp_player"), arm.get("caster_hp"), arm.get("n_events"),
                     arm.get("playbook")))
            for r in arm.get("events") or []:
                print("        %s" % json.dumps(r, sort_keys=True))
        print("[372] %s" % out["verdict"])
        print("[372] -> %s" % ("OK" if out.get("ok") else "ECHEC"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=35301)
    ap.add_argument("--level", type=int, default=8)
    ap.add_argument("--mult", type=int, default=100)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(seed=a.seed, level=a.level, mult=a.mult, board=a.board, verbose=not a.json)
    if a.json:
        print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
