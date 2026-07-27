#!/usr/bin/env python
"""Probe N1 -- ArcaneShield (thousSorcerer/Thaumachus) : le VECTEUR d'activation et le CLASSEMENT de la
cible. MESURE chiffree du renversement, pas un argument.

CE QUE CE PROBE ETABLIT

1. VECTEUR. `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility$$CreateTrigger` =
   `On(0x1c=ArrivedAtFinalTile) & get_OwnerIsActor & get_OwnerIsCaster`. On execute les DEUX emetteurs
   natifs portes et on imprime ce qui sort de chacun :
     * `after_move_triggers` (mirror `IdunBattle.Operations.MoveUnitOperation$$Execute`) ;
     * `FinishUnitTurnOperation.execute` (mirror `IdunBattle.Operations.FinishUnitTurnOperation$$Execute`,
       branche `newly_arrived and not forced` = << l'unite n'a pas bouge >>).
   Chaque ligne dit QUI recoit, COMBIEN, et pour COMBIEN DE TOURS.

2. CLASSEMENT. `...$$CreateBehaviour` trie par `Sum($$Distance, $$Faction, $$Chaos, $$Owner)` ASCENDANT
   -- un SCORE ADDITIF ou la distance pese 3 par hex contre 1 pour la faction et 1 pour le trait Chaos.
   Le probe imprime, par configuration, le score DECOMPOSE de chaque candidat, la cible que rend le port
   courant, et la cible qu'aurait rendue le TRI LEXICOGRAPHIQUE `(palier_faction, distance, id)` du port
   HISTORIQUE (re-code ici sous `_legacy_target`, uniquement pour la comparaison). La configuration
   `non_chaos a d=1 / same_faction a d=2` est celle qui les SEPARE.

MONTAGE : `tests/engine/runner/_arcane_shield_stage.py` (roster mixte ThousandSons / autre Chaos /
non-Chaos, positions DRIVEES) -- le meme que la garde `test_arcaneshield_vector_live.py`, pour qu'une
mesure et sa garde ne puissent pas diverger.

ASCII only (cp1252). Usage: python probe_n1_arcane_shield_target.py [--seed 777] [--keep]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))

from rl_collect_batch import _resolve_session, _rpc                          # noqa: E402
from engine.entities.pathfinding.board import Board                          # noqa: E402
from engine.runner.abilities.base import convert_rounds_to_turns             # noqa: E402
from engine.runner.components import PositionComponent, ShieldComponent      # noqa: E402
from engine.runner.operations import triggers as T                           # noqa: E402
from engine.runner.operations.turnflow import FinishUnitTurnOperation        # noqa: E402
from engine.runner.operations.triggers.base import _hex_dist, _unit_tile, _faction_id   # noqa: E402
from engine.runner.operations.triggers.loki.arcane_shield import (           # noqa: E402
    _arcaneshield_candidates, _arcaneshield_score, _arcaneshield_target, _arcaneshield_range)
from engine.entities.effects.loki.dark_angels_passives import grand_alliance_of   # noqa: E402

import _arcane_shield_stage as ST                                            # noqa: E402

ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_n1_arcane_shield_state.json"

# Tri du port HISTORIQUE, re-code ICI et NULLE PART AILLEURS : il ne sert qu'a chiffrer l'ecart avec le
# natif. `prio = 0 (meme faction) / 1 (autre Chaos) / 2 (autre)`, puis distance, puis id -- un ordre
# LEXICOGRAPHIQUE, alors que le natif somme les termes.
_LEGACY_CHAOS_FACTIONS = frozenset({
    "BlackLegion", "DeathGuard", "ThousandSons", "WorldEaters", "EmperorsChildren"})


def _legacy_target(state, owner_id: int) -> int:
    board = state.board
    own_fac = _faction_id(state, owner_id)
    ot = _unit_tile(state, board, owner_id)
    rng = _arcaneshield_range()
    cands = []
    for d, eid in _arcaneshield_candidates(state, owner_id):
        if eid == owner_id:
            continue
        t = _unit_tile(state, board, eid)
        dd = _hex_dist(board, ot, t, rng)
        if dd is None:
            continue
        fac = _faction_id(state, eid)
        prio = 0 if (own_fac is not None and fac == own_fac) else (
            1 if fac in _LEGACY_CHAOS_FACTIONS else 2)
        cands.append((prio, dd, eid))
    return sorted(cands)[0][2] if cands else owner_id


def _role_of(stage, uid):
    return next((r for r, v in stage.ids.items() if v == uid), f"id={uid}")


def _shield(state, uid):
    e = state.get_entity(uid)
    shc = e.get_component(ShieldComponent) if e is not None else None
    return shc.get_total_shield() if shc is not None else 0


def _dump_scores(stage, state, rng):
    """Tableau DECOMPOSE du score de chaque candidat (mirror des quatre symboles natifs)."""
    ot = _unit_tile(state, stage.board, stage.owner_id)
    own_fac = _faction_id(state, stage.owner_id)
    rows = []
    for d, eid in _arcaneshield_candidates(state, stage.owner_id):
        role = _role_of(stage, eid)
        fac = _faction_id(state, eid)
        alliance = grand_alliance_of(state, eid)
        dist = 0 if eid == stage.owner_id else _hex_dist(stage.board, ot,
                                                         _unit_tile(state, stage.board, eid), rng)
        t_dist = 3 * (dist or 0)
        t_fac = 0 if (own_fac is not None and fac == own_fac) else 1
        t_chaos = 0 if alliance == "Chaos" else 1
        t_own = (rng * 3 + 4) if eid == stage.owner_id else 0
        total = _arcaneshield_score(state, stage.owner_id, eid, d, rng)
        rows.append((total, role, fac, alliance, dist, t_dist, t_fac, t_chaos, t_own))
    rows.sort()
    print("    %-14s %-16s %-9s %4s | %5s %4s %5s %5s | %5s"
          % ("role", "faction", "alliance", "dist", "3*d", "fac", "chaos", "owner", "TOTAL"))
    for total, role, fac, alliance, dist, t_dist, t_fac, t_chaos, t_own in rows:
        print("    %-14s %-16s %-9s %4s | %5s %4s %5s %5s | %5s"
              % (role, fac, alliance, dist, t_dist, t_fac, t_chaos, t_own, total))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=ST.SEED)
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner en fin de probe")
    args = ap.parse_args()

    sid = _resolve_session()
    import subprocess
    import json
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.unlink(missing_ok=True)
    proc = subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", str(args.seed),
                           "--state-file", str(STATE), *ST.BUILD_ARGS],
                          cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("[N1] build KO:", (proc.stderr or proc.stdout or "")[-400:], file=sys.stderr)
        return 2
    rid = json.loads(STATE.read_text())["runnerId"]
    print(f"[N1] runner {rid} | board {ST.BOARD} | seed {args.seed}")

    def _r(m, b, t=120):
        return (_rpc(sid, m, [b], timeout=t).get("result") or {})

    try:
        bg = _r("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="evenq")
        dec = _r("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob = _r("observeBattle", {"runnerId": rid}, 60)
        snap = _r("combatSnapshot", {"runnerId": rid}, 90)
        ids = {}
        for role, vis in ST.ROLE_VIS.items():
            u = next((x for x in (dec.get("units") or [])
                      if x.get("visualId") == vis and x.get("alive")), None)
            if u is None:
                print(f"[N1] {vis} ({role}) absent de l'etat capture", file=sys.stderr)
                return 3
            ids[role] = u["id"]
        stage = ST.ArcaneShieldStage(rid, board, dec, ob, snap, ids)
        rng = _arcaneshield_range()
        print(f"[N1] range (AbilityConstantType 0x16) = {rng} | penalite owner = {rng*3+4}")
        for role, uid in ids.items():
            print(f"      {role:<14} {ST.ROLE_VIS[role]:<16} id={uid}")

        # ---------------- 1. VECTEUR ---------------------------------------------------------
        print("\n[N1] VECTEUR On(0x1c=ArrivedAtFinalTile) -- les deux emetteurs natifs")
        st = stage.load()
        stage.place(st, {"same_faction": 1})
        exp_dur = convert_rounds_to_turns(st, 1)
        before = _shield(st, ids["same_faction"])
        res = FinishUnitTurnOperation.execute(st, stage.owner_id, forced=False)
        g = [x for x in (res.get("arrived_triggers") or []) if x.get("ability") == "ArcaneShield"]
        print(f"    FinishUnitTurnOperation (n'a PAS bouge) : newly_arrived={res.get('newly_arrived')}"
              f" -> {len(g)} pose(s)")
        for x in g:
            print(f"      cible={_role_of(stage, x['target'])} montant={x['amount']}"
                  f" tours={x['remaining']} (ConvertRoundsToTurns(1)={exp_dur})"
                  f" shield_total {before}->{_shield(st, x['target'])}")

        st2 = stage.load()
        stage.place(st2, {"same_faction": 1})
        b2 = _shield(st2, ids["same_faction"])
        gm = [x for x in T.after_move_triggers(st2, stage.owner_id)
              if x.get("ability") == "ArcaneShield"]
        after_move = _shield(st2, ids["same_faction"])
        res2 = FinishUnitTurnOperation.execute(st2, stage.owner_id, forced=False)
        g2 = [x for x in (res2.get("arrived_triggers") or []) if x.get("ability") == "ArcaneShield"]
        print(f"    after_move_triggers (a bouge)          : {len(gm)} pose(s),"
              f" shield {b2}->{after_move}")
        print(f"    puis FinishUnitTurnOperation           : newly_arrived={res2.get('newly_arrived')}"
              f" -> {len(g2)} pose(s), shield {after_move}->{_shield(st2, ids['same_faction'])}"
              f"   [attendu : AU PLUS UN fire par activation]")

        # ---------------- 2. CLASSEMENT --------------------------------------------------------
        layouts = [
            ({"non_chaos": 1, "same_faction": 2, "other_chaos": 2},
             "DISCRIMINANT : la distance (poids 3) domine la faction (poids 1)"),
            ({"non_chaos": 2, "same_faction": 2, "other_chaos": 2},
             "a distance egale, la faction reprend la main"),
            ({"other_chaos": 1, "non_chaos": 1, "same_faction": 2},
             "a distance egale hors meme-faction, le trait Chaos departage"),
            ({"non_chaos": 1},
             "un seul ami, non-Chaos : il bat quand meme le caster (penalite owner)"),
        ]
        print("\n[N1] CLASSEMENT -- score additif Sum(3*dist, faction, chaos, owner), tri ASCENDANT")
        diverged = 0
        for layout, why in layouts:
            s = stage.load()
            stage.place(s, layout)
            print(f"\n  layout={layout}  ({why})")
            _dump_scores(stage, s, rng)
            port = _arcaneshield_target(s, stage.owner_id)
            legacy = _legacy_target(s, stage.owner_id)
            mark = "IDENTIQUE" if port == legacy else "DIVERGE"
            if port != legacy:
                diverged += 1
            print(f"    -> port (score additif) = {_role_of(stage, port)}"
                  f" | tri lexicographique historique = {_role_of(stage, legacy)}   [{mark}]")
        print(f"\n[N1] {diverged}/{len(layouts)} configurations ou le port historique se trompait de cible.")
        return 0
    finally:
        if not args.keep:
            try:
                _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
            except Exception:
                pass
            STATE.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
