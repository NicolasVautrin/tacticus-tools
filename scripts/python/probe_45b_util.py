#!/usr/bin/env python
"""Probe #45b' : decomposition TERME-A-TERME d'un mismatch de l'etage UTILITE.

Rebuild une seed (rl_duel build, state-file DEDIE data/_45b_state.json), marche la
trajectoire NATIVE jusqu'au pas cible (aiStepDryRun -> applyAction, mirror
engine_validate), puis AVANT d'appliquer le pas cible mesure la paire (uid, ab, tgt) :
  - obs de la cible (hp/hpMax/shield/effects) ;
  - aiPlaybookPredict a la tuile d'attaque (events natifs -> champs composite) ;
  - pairUtility natif (CalculateUtilityFromPredictions @181407890) a la meme tuile ;
  - NOTRE breakdown : DamageDealt(35) (internals dmg/CM/remaining/u_dmg/u_rem),
    KillUnit(36), Overkill(37) -> somme vs natif ;
  - test d'HYPOTHESES sur le residu : diviseur combinedMax alternatif (hpBefore au
    lieu de hpMax : cape max-HP #43), terme plat de feuille (delta ~ poids BC).
Sortie ASCII + dump JSON data/_45b_util_<seed>_s<step>.json.

Usage:
  python probe_45b_util.py --seed 777 --stop-step 15 --uid 83 --ab 69 --tgt 87
  python probe_45b_util.py --seed 31337 --stop-step 18 --uid 89 --ab 69 --tgt 81
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
from engine import weights  # noqa: E402
from engine.utilities.damage import (DamageUtility, KillUnitUtility,  # noqa: E402
                                     OverkillUnitUtility, W_DAMAGE, W_REMAINING,
                                     _clamp01)
from engine_agreement_stages import _fields_from_native_event  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "data" / "_45b_state.json"


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def build(seed: int) -> int:
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), "--board", "MC1_67"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[45b] build KO: {(proc.stderr or proc.stdout or '')[-300:]}", file=sys.stderr)
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--stop-step", type=int, required=True)
    ap.add_argument("--uid", type=int, required=True)
    ap.add_argument("--ab", type=int, required=True)
    ap.add_argument("--tgt", type=int, required=True)
    args = ap.parse_args(argv)
    sid = _resolve_session()
    rid = build(args.seed)
    print(f"[45b] seed={args.seed} runner={rid} -> walk jusqu'au pas {args.stop_step}")

    stop_dry = None
    try:
        for step in range(args.stop_step + 1):
            dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
            if not dry.get("ok") or not dry.get("hasNext"):
                print(f"[45b] natif epuise au pas {step} ({dry.get('error')})")
                return 3
            nat = native_chunk(dry.get("action") or {})
            au = dry.get("activatedUnitId") or nat.get("unit")
            print(f"  step {step:2}: u{au} {nat.get('ability') or nat.get('move') or 'finish'}")
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
        if na.get("ability") != args.ab or na.get("target") != args.tgt:
            print(f"[45b] ATTENTION trajectoire differente : natif au pas cible = {nat}"
                  f" (attendu ab={args.ab} tgt={args.tgt}) -- mesures quand meme")
        tile = (nat.get("move") or {}).get("to")

        obs = _r(sid, "observeBattle", {"runnerId": rid}, 30)
        by_id = {u.get("squadId"): u for u in obs.get("units") or []}
        me, tg = by_id.get(args.uid), by_id.get(args.tgt)
        print(f"\n[45b] u{args.uid} {me.get('visualId')} hp={me.get('hp')}/{me.get('hpMax')}"
              f" -> u{args.tgt} {tg.get('visualId')} hp={tg.get('hp')}/{tg.get('hpMax')}"
              f" shield={tg.get('shield')} armor={tg.get('armor')}/{tg.get('armorMax')}")
        print(f"[45b] effets cible: {[e.get('name') for e in (tg.get('effects') or [])]}")
        print(f"[45b] effets acteur: {[e.get('name') for e in (me.get('effects') or [])]}")
        print(f"[45b] tuile d'attaque: {tile if tile else 'courante'}")

        body = {"runnerId": rid, "unitId": args.uid, "targetId": args.tgt,
                "abilityType": args.ab}
        if tile:
            body["col"], body["row"] = int(tile[0]), int(tile[1])
        pp = _r(sid, "aiPlaybookPredict", body, 60)
        pu = _r(sid, "pairUtility", body, 60)
        evs = pp.get("events") or []
        print(f"\n[45b] events natifs ({len(evs)}):")
        for ev in evs:
            print("   ", {k: ev.get(k) for k in ("targetId", "hpBefore", "shieldBefore",
                                                 "healthDmgMin", "healthDmgMax",
                                                 "willKillDmg", "mightKillDmg",
                                                 "shieldDmgMin", "shieldDmgMax",
                                                 "probability", "probMult",
                                                 "limitedByMinHp", "forceOverkill",
                                                 "appliedHits")})
        print(f"[45b] pairUtility NATIF = {pu.get('utility')} (pb={pu.get('playbookClass')}"
              f" posSrc={pu.get('posSrc')} err={pu.get('error')})")

        wt = weights.load()
        main_ev = next((e for e in evs if e.get("targetId") == args.tgt),
                       evs[0] if evs else None)
        out = {"seed": args.seed, "step": args.stop_step, "uid": args.uid,
               "ab": args.ab, "tgt": args.tgt, "tile": tile, "me": me, "tg": tg,
               "events": evs, "pairUtility": pu}
        if main_ev is not None:
            f = _fields_from_native_event(main_ev)
            hpmax = tg.get("hpMax") or 0
            dd, ku, ok_ = DamageUtility(), KillUnitUtility(), OverkillUnitUtility()
            u_dd = dd.evaluate(f, hpmax, wt)
            u_ku = ku.evaluate(f, hpmax, wt)
            u_ok = ok_.evaluate(f, hpmax, wt)
            # somme AVEC prob (mirror CalculateUtilityFromDamageEvent par event)
            tot = 0.0
            for ev in evs:
                ef = _fields_from_native_event(ev)
                et = by_id.get(ev.get("targetId")) or {}
                # camp : playerId d'observeBattle (le champ team n'existe pas dans l'obs)
                sign = -1.0 if (et.get("playerId") is not None
                                and et.get("playerId") == me.get("playerId")) else 1.0
                prob = (ev.get("probability") or 1.0) * (ev.get("probMult") or 1.0)
                tot += sign * prob * (dd.evaluate(ef, et.get("hpMax") or 0, wt)
                                      + ku.evaluate(ef, et.get("hpMax") or 0, wt)
                                      + ok_.evaluate(ef, et.get("hpMax") or 0, wt))
            nat_u = pu.get("utility")
            print(f"\n[45b] OFFLINE breakdown (main target, hpMax={hpmax}):")
            dmg = dd.get_health_damage(f) + dd.get_shield_damage(f)
            shield = f.get("shieldBefore") or 0
            cm = (hpmax + 1) + (shield + 1)
            rem = ((f.get("hpBefore") or 0) + 1) + (shield + 1)
            print(f"    dmg(avg h+s)={dmg}  CM=(maxHp+1)+(shield+1)={cm}  remaining={rem}")
            print(f"    DamageDealt={u_dd:.4f}  Kill={u_ku:.4f}  Overkill={u_ok:.4f}")
            print(f"    TOTAL offline (tous events, prob)={tot:.4f}  vs NATIF={nat_u}")
            resid = None if nat_u is None else nat_u - tot
            print(f"    RESIDU natif-offline = {resid}")
            # Hypotheses sur le residu :
            if resid is not None and abs(resid) > 0.01:
                hp_before = f.get("hpBefore") or 0
                for label, m2 in (("CM avec hpBefore (cape max-HP)", hp_before),
                                  ("CM avec max(hpMax, hpBefore)", max(hpmax, hp_before))):
                    cm2 = (m2 + 1) + (shield + 1)
                    u_dmg2 = _clamp01(dmg / cm2) * W_DAMAGE
                    u_rem2 = (1.0 - _clamp01((rem - dmg) / cm2)) * W_REMAINING
                    alt = u_dmg2 + u_rem2 + u_ku + u_ok
                    print(f"    HYP {label}: DamageDealt'={u_dmg2 + u_rem2:.4f}"
                          f" -> total'={alt:.4f} (delta vs natif "
                          f"{(nat_u - alt):+.4f})")
                # SOLVE CM : quel combinedMax X rend exactement le natif ?
                # u = dmg/X*80 + (1 - (rem-dmg)/X)*20 (clamps supposes non satures)
                # -> X = (80*dmg - 20*(rem-dmg)) / (nat - kill - overkill - 20)
                nat_dd = nat_u - u_ku - u_ok
                den = nat_dd - W_REMAINING
                if abs(den) > 1e-9:
                    x = (W_DAMAGE * dmg - W_REMAINING * (rem - dmg)) / den
                    print(f"    SOLVE CM (rem non sature): X={x:.1f} -> MaxHealth "
                          f"implicite={x - 2 - shield:.1f} (obs hpMax={hpmax}, "
                          f"delta mods={x - 2 - shield - hpmax:+.1f})")
                if nat_dd > 0:
                    x2 = W_DAMAGE * dmg / nat_dd
                    print(f"    SOLVE CM (rem sature=0): X={x2:.1f} -> MaxHealth "
                          f"implicite={x2 - 2 - shield:.1f}")
                print(f"    HYP terme plat manquant: delta={resid:+.4f} "
                      f"(comparer aux poids BC: 10/15/20/40/50...)")
            out["offline"] = {"total": tot, "dd": u_dd, "kill": u_ku, "overkill": u_ok,
                              "residual": resid}
        dump = ROOT / "data" / f"_45b_util_{args.seed}_s{args.stop_step}.json"
        dump.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        print(f"\n[45b] dump -> {dump}")
        return 0
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 20)
        print(f"[45b] runner {rid} dispose")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
