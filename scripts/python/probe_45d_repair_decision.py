#!/usr/bin/env python
"""Probe #45d -- MAGNITUDE et UTILITE de la REPARATION generique `Repair` (28), confrontees LIVE.

Canal de confrontation = `pairUtility` (invoque
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`
et rend un Fix64 scalaire). Il NE traverse PAS le decodeur de `RepairPredictionResult` des hooks
(backlog #276-r1 : ce decodeur lit 16 octets d'une struct qui n'en fait que 8 -> totalHeal /
totalArmorRepair rendent du tas voisin). Le scalaire, lui, vient du natif.

Ce que le probe mesure, par (caster, cible) :
  U_nat  = pairUtility(caster, cible, 28)
  U_sat  = utilite du port AVANT #45d : magnitude non sourcee -> saturation `fill = missing`
  U_wpn  = utilite du port APRES #45d : `RepairAbility$$RepairAmount` =
           `Multiply(StatAmount(weapon), Max(WeaponHighestHits(weapon), 1))`
           = attack RESOLUE du caster x max(hits de son arme, 1), puis
           `FillUpStatComponent$$MaxFillUp` = min(amount, maxHP - curHP).

Le montage doit exposer les DEUX regimes :
  - repairAmount >= missing  -> U_sat == U_wpn (non discriminant)
  - repairAmount <  missing  -> U_sat  > U_wpn (DISCRIMINANT ; c'est le cas qui tranche)

Usage:
  python probe_45d_repair_decision.py --runner N [--json out.json]
Pre-requis : session warmee ; un runner ou une unite MECHANICAL alliee est BLESSEE et un
porteur du trait Mechanic (admecDominus / necroSpyder / orksBigMek / admecManipulus-sans-Galvanic)
peut la cibler (`abilityTargets abilityType=28`).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

HOST = "http://127.0.0.1:8765"
REPAIR_ID = 28


def _session() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=20).json()["session"]["id"])


def rpc(sid: int, method: str, body: dict, timeout: int = 90):
    r = requests.post(f"{HOST}/api/scripts/{sid}/rpc",
                      json={"method": method, "args": [body], "timeout": int(timeout * 1000)},
                      timeout=timeout + 5).json()
    return r.get("result", r)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, required=True)
    ap.add_argument("--json", type=str, default=None)
    args = ap.parse_args(argv)
    sid, rid = _session(), args.runner

    obs = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    at = rpc(sid, "abilityTargets", {"runnerId": rid, "abilityType": REPAIR_ID}, 60)

    ob_by_sq = {u.get("squadId"): u for u in (obs.get("units") or [])}
    sn_by_id = {u.get("entityId"): u for u in (snap.get("units") or [])}

    from engine.predict import predict_repair_effective, repair_amount_weapon
    from engine.utilities.repair import REPAIR_UTILITY

    rows = []
    for u in (at.get("units") or []):
        cid = u.get("unitId")
        for a in (u.get("abilities") or []):
            if a.get("abilityId") != REPAIR_ID:
                continue
            for t in (a.get("targets") or []):
                if t.get("kind") != "unit" or t.get("targetId") is None:
                    continue
                tid = t["targetId"]
                ob = ob_by_sq.get(tid) or {}
                hp_cur, hp_max = int(ob.get("hp") or 0), int(ob.get("hpMax") or 0)
                arm_cur, arm_max = int(ob.get("armor") or 0), int(ob.get("armorMax") or 0)
                missing = max(0, hp_max - hp_cur)

                sn = sn_by_id.get(cid) or {}
                attack = int(((sn.get("stats") or {}).get("attack")) or 0)
                hits = int((sn.get("normalAttack") or {}).get("hits") or 1)
                amt = repair_amount_weapon(attack, hits)

                u_nat = rpc(sid, "pairUtility", {"runnerId": rid, "unitId": cid,
                                                 "targetId": tid, "abilityType": REPAIR_ID}, 60)
                nat = u_nat.get("utility") if isinstance(u_nat, dict) else None

                # AVANT #45d : magnitude non sourcee (repair_amount_config -> None) -> saturation.
                u_sat = REPAIR_UTILITY.evaluate(missing, hp_max, False)
                # APRES #45d : magnitude = RepairAbility$$RepairAmount, puis MaxFillUp.
                rp = predict_repair_effective(amt, hp_cur, hp_max)
                u_wpn = REPAIR_UTILITY.evaluate(rp.fill_hp, hp_max, False)

                row = {"caster": cid, "casterVis": u.get("visualId"), "target": tid,
                       "targetVis": ob.get("visualId"), "hp": hp_cur, "hpMax": hp_max,
                       "armor": arm_cur, "armorMax": arm_max, "missing": missing,
                       "attack": attack, "hits": hits, "repairAmount": amt,
                       "fillHp": rp.fill_hp,
                       "U_nat": nat, "U_sat": u_sat, "U_wpn": u_wpn,
                       "discriminant": bool(amt < missing)}
                rows.append(row)
                print("caster u%-4s %-16s -> u%-4s %-16s hp=%d/%d miss=%d atk=%d hits=%d "
                      "amt=%d fill=%d | U_nat=%s U_sat=%.4f U_wpn=%.4f %s"
                      % (cid, row["casterVis"], tid, row["targetVis"], hp_cur, hp_max,
                         missing, attack, hits, amt, rp.fill_hp,
                         ("%.4f" % nat) if nat is not None else "?", u_sat, u_wpn,
                         "[DISCRIMINANT]" if row["discriminant"] else "[saturant]"))

    if not rows:
        print("[probe45d] aucune paire (caster Mechanic, cible Mechanical blessee) -- "
              "monter le scenario d'abord")
        return 2
    ok_wpn = sum(1 for r in rows if r["U_nat"] is not None and abs(r["U_nat"] - r["U_wpn"]) < 1e-3)
    ok_sat = sum(1 for r in rows if r["U_nat"] is not None and abs(r["U_nat"] - r["U_sat"]) < 1e-3)
    disc = sum(1 for r in rows if r["discriminant"])
    print("[probe45d] paires=%d discriminantes=%d | accord U_wpn=%d/%d  accord U_sat=%d/%d"
          % (len(rows), disc, ok_wpn, len(rows), ok_sat, len(rows)))
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return 0 if ok_wpn == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
