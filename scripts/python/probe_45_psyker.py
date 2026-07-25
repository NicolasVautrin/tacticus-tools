#!/usr/bin/env python
"""Probe #45-s18 : VALIDATION NUMERIQUE du port de la feuille splash Psyker AVANT ecriture.

Mirror de `PsykerPlaybook.<CalculateAttackUtilityInStepsInternal>d__2 IdunBattle.AI.Playbook.Loki.PsykerPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext` (feuille
TriggeredAbilities(2) face ATTACK IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateAttackInStepsInternalu003Ed__3$$MoveNext), calcule OFFLINE au pas cible et confronte :
  - au score natif par-feuille capture L3 (31337 s18 : TriggeredAbilitiesUtility#0
    = 17.85381752299145) ;
  - au residu pairUtility de l'etage UTILITE (off 164.2269 + feuille == nat 182.0807).

Chaine offline (chaque terme = mirror nomme) :
  amount  = PercentageOf(attack, psykerExtraDmg=50) -> _round_fix64(Fraction(pct*atk,100))
  targets = Damageable(Enemies(caster, AdjacentUnits(CIBLE,1))) -> hexdist==1, team!=, alive
  pred    = GetAttackPrediction slot 0x23 (predefined amount, hits=1, Psychic pierce 100,
            SANS spread ±20% ni mods attaquant) -> get_attack_prediction(spread_pct=0)
  u       = MEAN_U( CalculateUtilityFromDamageEvent(ProbableDamageEvent(U, pred)) )

Usage: python probe_45_psyker.py --seed 31337 --stop-step 18 --uid 89 --ab 69 --tgt 81
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine_validate import native_chunk  # noqa: E402
import gameconfig as GC  # noqa: E402
import hexgeo  # noqa: E402
from engine import weights  # noqa: E402
from engine.playbook import scene as scene_mod  # noqa: E402
from engine.playbook.prediction import (_PROFILE_INDEX, _target_damage_limits)  # noqa: E402
from engine.playbook.probable_damage_event import (ProbableDamageEvent,  # noqa: E402
                                                   calculate_utility_from_damage_event)
from engine.services.damage_prediction import get_attack_prediction  # noqa: E402
from engine.services.battle_query import select_weapon_pierce  # noqa: E402
from engine.entities.formulas import _round_fix64  # noqa: E402
from fractions import Fraction  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "_45psy_state.json"

L3_EXPECTED = 17.85381752299145      # capture L3 31337 s18 (TriggeredAbilitiesUtility#0)


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int) -> int:
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[45psy] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=31337)
    ap.add_argument("--stop-step", type=int, default=18)
    ap.add_argument("--uid", type=int, default=89)
    ap.add_argument("--ab", type=int, default=69)
    ap.add_argument("--tgt", type=int, default=81)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed)
    rpc = lambda m, b, t=60: _r(sid, m, b, t)   # noqa: E731
    print(f"[45psy] seed={args.seed} runner={rid} -> walk jusqu'au pas {args.stop_step}")

    try:
        stop_dry = None
        for step in range(args.stop_step + 1):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[45psy] natif epuise au pas {step} ({dry.get('error')})")
                return 3
            nat = native_chunk(dry.get("action") or {})
            if step == args.stop_step:
                stop_dry = dry
                break
            acts = []
            for m in (dry["action"]["messages"] or []):
                if m.get("cls") == "MoveUnitMessage":
                    acts.append({"kind": "move", "unitId": m["unitId"],
                                 "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
                elif m.get("cls") == "ActiveAbilityMessage":
                    acts.append({"kind": "ability", "casterId": m["casterId"],
                                 "targetId": m.get("targetId"),
                                 "abilityType": m["abilityType"]})
                elif m.get("cls") == "FinishUnitTurnMessage":
                    acts.append({"kind": "finish", "unitId": m["unitId"]})
            if acts:
                _r(sid, "applyAction", {"runnerId": rid, "actions": acts}, 60)

        nat = native_chunk(stop_dry.get("action") or {})
        na = nat.get("ability") or {}
        tile = (nat.get("move") or {}).get("to")
        print(f"[45psy] pas cible natif: {na} move-to={tile}")

        # ---- etat du pas : Scene (predictor froid rebuilde ICI = frais) + decisionView ----
        predictor = scene_mod.build_predictor(rpc, rid)
        if predictor is None:
            print("[45psy] combatSnapshot KO")
            return 4
        dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        sctx = scene_mod.step_context(predictor, dv)
        sctx["hpmax_by_id"] = predictor.get("hpmax_eff_by_id") or {}
        tm = _r(sid, "tileMeta", {"runnerId": rid}, 40)
        tfx = {(t["col"], t["row"]): [e.get("name") for e in (t.get("effects") or [])]
               for t in (tm.get("tiles") or []) if t.get("effects")}
        sc = scene_mod.Scene.from_predictor_sctx(predictor, sctx, tile_effects_by_pos=tfx)
        wt = weights.load()

        uid, tgt = args.uid, args.tgt
        atile = tuple(tile) if tile else sc.pos(uid)

        # hpmax EFFECTIF (mirror ctx.hpmax_by_id des stages : obs base + overlay part-2)
        obs = _r(sid, "observeBattle", {"runnerId": rid}, 30)
        hpmax_by_id = {u.get("squadId"): int(u.get("hpMax") or 0)
                       for u in (obs.get("units") or [])}
        hpmax_by_id.update(predictor.get("hpmax_eff_by_id") or {})

        # ---- LA FEUILLE PORTEE (engine/utilities/tile.py -> engine/playbook/psyker.py) ----
        from types import SimpleNamespace
        from engine.utilities.tile import triggered_abilities_attack_utility
        mctx = SimpleNamespace(scene=sc, wt=wt, hpmax_by_id=hpmax_by_id,
                               normal_ids={args.ab}, uid=uid)
        leaf = triggered_abilities_attack_utility(mctx, uid, args.ab, tgt, atile)

        # contexte de reference (montant/targets, pour le rapport) — MEME canal que la feuille
        # (attack_current = stat DU PAS, #45-s18 : le cold ctx.attack rate l'aura RitesOfBattle)
        pct = int((GC.trait("Psyker") or {}).get("variables", {}).get("psykerExtraDmg") or 0)
        attack = sc.attack_current(uid)
        amount = _round_fix64(Fraction(pct * int(attack), 100), 0)
        from engine.playbook.psyker import PsykerPlaybook
        targets = PsykerPlaybook().possible_targets(sc, uid, tgt)
        print(f"[45psy] attack={attack} pct={pct} -> amount={amount} ; "
              f"splash targets={targets}")

        print(f"\n[45psy] FEUILLE PORTEE = {leaf!r}")
        print(f"[45psy] L3 natif attendu = {L3_EXPECTED!r}")
        print(f"[45psy] delta = {leaf - L3_EXPECTED:+.10f} "
              f"({'MATCH' if abs(leaf - L3_EXPECTED) <= 1e-4 else 'MISMATCH'})")

        # residu pairUtility (controle bout-en-bout au meme tile)
        body = {"runnerId": rid, "unitId": uid, "targetId": tgt, "abilityType": args.ab}
        if tile:
            body["col"], body["row"] = int(tile[0]), int(tile[1])
        pu = _r(sid, "pairUtility", body, 60)
        print(f"[45psy] pairUtility natif = {pu.get('utility')}")

        # ---- GROUND TRUTH stat Attack u89 : snapshot brut + statModSources + effets ----
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 40)
        su = next((u for u in (snap.get("units") or []) if u.get("entityId") == uid), {})
        print(f"\n[45psy] snapshot u{uid}: stats={su.get('stats')}")
        print(f"[45psy] statDelta u{uid}: {su.get('statDelta')}")
        print(f"[45psy] normalAttack u{uid}: {su.get('normalAttack')}")
        sms = _r(sid, "statModSources", {"runnerId": rid, "unitId": uid,
                                         "stats": ["attack"]}, 40)
        print(f"[45psy] statModSources u{uid} attack: "
              f"{json.dumps(sms.get('units') or sms, default=str)[:500]}")
        dv_u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), {})
        print(f"[45psy] effets u{uid}: "
              f"{[e.get('name') for e in (dv_u.get('effects') or [])]}")

        # ---- contexte fin : identites/effets cibles, glace, abilityState 1194 ----
        print(f"[45psy] abilityStates u{uid}: {su.get('abilityStates')}")
        for xid in sorted(set(targets + [tgt])):
            xu = next((x for x in (dv.get("units") or []) if x.get("id") == xid), {})
            hme = (predictor.get("hpmax_eff_by_id") or {}).get(xid)
            print(f"[45psy] u{xid} {xu.get('visualId')} team={xu.get('team')} "
                  f"hp={xu.get('hp')} hpmaxEff={hme} "
                  f"effets={[e.get('name') for e in (xu.get('effects') or [])]}")
        tm = _r(sid, "tileMeta", {"runnerId": rid}, 40)
        ice = [(t.get("col"), t.get("row"),
                [e.get("name") for e in (t.get("effects") or [])])
               for t in (tm.get("tiles") or [])
               if any("ice" in str(e.get("name") or "").lower()
                      for e in (t.get("effects") or []))]
        print(f"[45psy] tuiles GLACE: {ice}")
        for center, lbl in ((tuple(tile) if tile else sc.pos(uid), "case-tile"),
                            (sc.pos(uid), "pos-courante")):
            n = sum(1 for (c, r, _e) in ice if hexgeo.distance(center, (c, r)) == 1)
            print(f"[45psy] N_ice ring-1 autour {lbl} {center} = {n}")

        # ---- EXECUTION : appliquer le pas 18 et lire le degat splash reel (trace) ----
        acts = []
        for m in (stop_dry["action"]["messages"] or []):
            if m.get("cls") == "MoveUnitMessage":
                acts.append({"kind": "move", "unitId": m["unitId"],
                             "to": {"col": m["to"]["col"], "row": m["to"]["row"]}})
            elif m.get("cls") == "ActiveAbilityMessage":
                acts.append({"kind": "ability", "casterId": m["casterId"],
                             "targetId": m.get("targetId"),
                             "abilityType": m["abilityType"]})
            elif m.get("cls") == "FinishUnitTurnMessage":
                acts.append({"kind": "finish", "unitId": m["unitId"]})
        hp_before = {u_id: sc.hp(u_id) for u_id in targets}
        if acts:
            _r(sid, "applyAction", {"runnerId": rid, "actions": acts}, 60)
        obs2 = _r(sid, "observeBattle", {"runnerId": rid}, 30)
        for u in (obs2.get("units") or []):
            if u.get("squadId") in targets:
                b = hp_before.get(u.get("squadId"))
                print(f"[45psy] EXECUTE: u{u.get('squadId')} hp {b} -> {u.get('hp')} "
                      f"(splash reel = {b - (u.get('hp') or 0)})")
        return 0
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 20)
        print(f"[45psy] runner {rid} dispose")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
