#!/usr/bin/env python
"""Probe #27 (residu 1212) -- HealingBalms_Heal : MAGNITUDE du soin + terme CUSTOM du playbook.

Deux etages, deux canaux, mesures separement (jamais un scalaire fitte) :

  E1 MAGNITUDE  -- canal `pairUtility` (invoque
     `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`
     et rend un Fix64 SCALAIRE). Il ne traverse AUCUN decodeur de struct des hooks -- ni celui de
     `RepairPredictionResult` (backlog #276-r1 : 16 octets lus pour une struct de 8), ni celui des
     healEvents, dont la struct `ProbableHealEvent` a exactement la meme forme
     (`CONCAT44(fill, current)`).
     Le natif compare a DEUX hypotheses de magnitude :
       U_wpn  = `IdunBattleLogic.Entities.Abilities.Active.Common.HealAbility$$HealAmount`
                = `Multiply(StatAmount(weapon), Max(WeaponHighestHits(weapon), Get(1)))`
                = attack RESOLUE du caster x hits d'arme, puis `FillUpStatComponent$$MaxFillUp`.
       U_cfg  = la variable de config `hpToHeal` (ce que le port faisait pour 1212 : la cle derivee
                "HealingBalms_Heal" -> "HealingBalms" pointe sur la config du PASSIF, dont le
                `hpToHeal` alimente le soin RETARDE de l'effet, pas l'action).

  E2 CUSTOM     -- canal CHOIX NATIF (`aiDryRunAllUnits`, read-only). Le terme custom
     (`IdunBattle.AI.Playbook.Loki.HealingBalms_HealPlaybook$$CalculateCustomUtility`
      = `Fix64.Half * Sum(CalculateUtilityFromHealEvent)` si la cible n'a PAS l'effet
      `EffectType.HealingBalms_ExtraCritDamage` (0x5df), 0 sinon) n'apparait PAS dans `pairUtility`
     (le natif l'ajoute dans `CalculateActionUtility`, au-dessus). On l'encadre donc par le CHOIX :
     deux cibles soignables depuis la MEME tuile (le terme de tuile s'annule), dont une seule
     porte l'effet -> l'ordre du natif borne le facteur.

Usage :
  python probe_27_1212_healingbalms.py --runner N [--caster 81] [--json out.json]
  python probe_27_1212_healingbalms.py --runner N --choice          # + choix natif de u81
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
HEALING_BALMS_HEAL = 1212
# `EffectType.HealingBalms_ExtraCritDamage` (0x5df) : le gate lu par
# `...HealingBalms_HealPlaybook$$CalculateCustomUtility` via `EntityExtensions$$HasEffect`.
EFFECT_GATE_NAME = "HealingBalms_ExtraCritDamage"


def _session() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=20).json()["session"]["id"])


def rpc(sid: int, method: str, body: dict, timeout: int = 90):
    r = requests.post(f"{HOST}/api/scripts/{sid}/rpc",
                      json={"method": method, "args": [body], "timeout": int(timeout * 1000)},
                      timeout=timeout + 10).json()
    return r.get("result", r)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, required=True)
    ap.add_argument("--caster", type=int, default=None, help="entityId du porteur (defaut: auto)")
    ap.add_argument("--choice", action="store_true", help="ajoute le CHOIX natif (aiDryRunAllUnits)")
    ap.add_argument("--json", type=str, default=None)
    args = ap.parse_args(argv)
    sid, rid = _session(), args.runner

    obs = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 2}, 180)
    at = rpc(sid, "abilityTargets", {"runnerId": rid, "abilityType": HEALING_BALMS_HEAL}, 60)

    ob_by_sq = {u.get("squadId"): u for u in (obs.get("units") or [])}
    sn_by_id = {u.get("entityId"): u for u in (snap.get("units") or [])}
    dv_by_id = {u.get("id"): u for u in (dv.get("units") or [])}

    from engine.predict import heal_amount_weapon, heal_amount_config, predict_heal_effective
    from engine.utilities.heal import HEAL_UTILITY

    rows = []
    for u in (at.get("units") or []):
        cid = u.get("unitId")
        if args.caster is not None and cid != args.caster:
            continue
        sn = sn_by_id.get(cid) or {}
        attack = int(((sn.get("stats") or {}).get("attack")) or 0)
        hits = int((sn.get("normalAttack") or {}).get("hits") or 1)
        amt_wpn = heal_amount_weapon(attack, hits)
        cfg = (sn.get("unitConfig") or {})
        amt_cfg = heal_amount_config("HealingBalms_Heal",
                                     int(cfg.get("activeAbilityLevel") or 0),
                                     int(cfg.get("passiveAbilityLevel") or 0),
                                     int(cfg.get("abilityVariablesMultiplier") or 100))
        for a in (u.get("abilities") or []):
            if a.get("abilityId") != HEALING_BALMS_HEAL:
                continue
            for t in (a.get("targets") or []):
                if t.get("kind") != "unit" or t.get("targetId") is None:
                    continue
                tid = t["targetId"]
                ob = ob_by_sq.get(tid) or {}
                hp_cur, hp_max = int(ob.get("hp") or 0), int(ob.get("hpMax") or 0)
                effs = [e.get("name") for e in ((dv_by_id.get(tid) or {}).get("effects") or [])]
                gated = EFFECT_GATE_NAME in effs

                pu = rpc(sid, "pairUtility", {"runnerId": rid, "unitId": cid,
                                              "targetId": tid,
                                              "abilityType": HEALING_BALMS_HEAL}, 60)
                nat = pu.get("utility") if isinstance(pu, dict) else None

                is_friend = True    # 1212 ne cible que des allies (masque de ciblage)
                u_wpn = HEAL_UTILITY.evaluate(
                    predict_heal_effective(amt_wpn, hp_cur, hp_max), hp_max, is_friend, False)
                u_cfg = (None if amt_cfg is None else HEAL_UTILITY.evaluate(
                    predict_heal_effective(amt_cfg, hp_cur, hp_max), hp_max, is_friend, False))

                # `CalculateActionUtility` : u = custom + CalculateUtilityFromPredictions,
                # custom = 0 si la cible porte l'effet, sinon Half * (la MEME somme de heal).
                u_action = nat if (nat is None or gated) else nat * 1.5
                row = {"caster": cid, "target": tid, "targetVis": ob.get("visualId"),
                       "hp": hp_cur, "hpMax": hp_max, "missing": max(0, hp_max - hp_cur),
                       "attack": attack, "hits": hits,
                       "amtWpn": amt_wpn, "amtCfg": amt_cfg, "gated": gated,
                       "U_nat_pair": nat, "U_wpn": u_wpn, "U_cfg": u_cfg,
                       "u_action_pred": u_action}
                rows.append(row)
                print("caster u%-3s -> u%-3s %-16s hp=%6d/%-6d miss=%6d | amtWpn=%5d amtCfg=%s "
                      "gate1503=%s | U_nat=%s U_wpn=%.6f U_cfg=%s | u_action(pred)=%s"
                      % (cid, tid, row["targetVis"], hp_cur, hp_max, row["missing"],
                         amt_wpn, ("%d" % amt_cfg) if amt_cfg is not None else "-",
                         "OUI" if gated else "non",
                         ("%.8f" % nat) if nat is not None else "?", u_wpn,
                         ("%.6f" % u_cfg) if u_cfg is not None else "-",
                         ("%.6f" % u_action) if u_action is not None else "?"))

    if not rows:
        print("[1212] aucune paire (porteur HealingBalms + cible soignable) -- monter le scenario")
        return 2

    ok_wpn = sum(1 for r in rows if r["U_nat_pair"] is not None
                 and abs(r["U_nat_pair"] - r["U_wpn"]) < 1e-6)
    ok_cfg = sum(1 for r in rows if r["U_nat_pair"] is not None and r["U_cfg"] is not None
                 and abs(r["U_nat_pair"] - r["U_cfg"]) < 1e-6)
    print("[1212] E1 magnitude : paires=%d | accord U_wpn=%d/%d  accord U_cfg=%d/%d"
          % (len(rows), ok_wpn, len(rows), ok_cfg, len(rows)))

    out = {"runner": rid, "rows": rows}
    if args.choice:
        dry = rpc(sid, "aiDryRunAllUnits", {"runnerId": rid}, 180)
        picks = []
        for p in (dry.get("units") or dry.get("plans") or []):
            picks.append({k: p.get(k) for k in ("unitId", "abilityType", "targetId", "to", "score")
                          if k in p})
        out["nativeChoice"] = picks or dry
        print("[1212] E2 choix natif : %s" % json.dumps(picks or dry)[:900])

    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0 if ok_wpn == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
