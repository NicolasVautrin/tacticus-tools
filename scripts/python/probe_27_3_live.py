"""probe #27-3 -- mesures LIVE de la tranche 3 de case-27.

Sous-commandes :
  runners            : listRunners (etat de l'atelier)
  facade <runner>    : cibles LEGALES de SorcerousFacade (1100) sur thousTzaangor
                       -- tranche le desaccord code/doc du commit #27-2
                       (l'ability cible-t-elle un ALLIE ou un ENNEMI ?)
  mow <runner>       : les Machines of War apparaissent-elles comme unites de
                       DECISION (decisionView.units / attackPlans / aiDryRun) ?
  view <runner>      : decisionView resume
  pair <runner> <u> <t> <ab> [col row] : pairUtility natif
  dryrun <runner>    : aiDryRunAllUnits (action proposee par unite)

ASCII only.
"""
from __future__ import annotations

import json
import sys

import probe_27_custom_utility_inventory as INV


def _rpc(method, args=None, timeout=120000):
    return INV.rpc(INV._session_id(), method, args, timeout)


def cmd_runners():
    print(json.dumps(_rpc("listRunners"), indent=1)[:3000])


def cmd_facade(runner: int):
    dv = _rpc("decisionView", [{"runnerId": runner, "allAbilities": True}])
    units = dv.get("units") or []
    tz = [u for u in units if "Tzaangor" in str(u.get("visualId"))
          or "thousTzaangor" in str(u.get("visualId"))]
    print("units:")
    for u in units:
        print("  id=%-5s team=%-2s vid=%-22s pos=%s,%s alive=%s"
              % (u.get("id"), u.get("team"), u.get("visualId"),
                 (u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"),
                 u.get("alive")))
    if not tz:
        print("PAS de thousTzaangor dans le runner")
        return
    uid = tz[0]["id"]
    at = _rpc("abilityTargets", [{"runnerId": runner, "unitId": uid,
                                 "allAbilities": True}])
    print("\nabilityTargets(unit=%s) :" % uid)
    print(json.dumps(at, indent=1)[:4000])


def cmd_mow(runner: int):
    obs = _rpc("observeBattle", [{"runnerId": runner}])
    print("observeBattle.byType=%s" % obs.get("byType"))
    print("mows=%s" % json.dumps(obs.get("mows"))[:600])
    dv = _rpc("decisionView", [{"runnerId": runner, "allAbilities": True}])
    ids = [(u.get("id"), u.get("visualId")) for u in (dv.get("units") or [])]
    print("decisionView.units=%s" % ids)
    print("attackPlans keys=%s" % list((dv.get("attackPlans") or {}).keys()))


def cmd_view(runner: int):
    dv = _rpc("decisionView", [{"runnerId": runner, "allAbilities": True}])
    print("meta=%s" % json.dumps(dv.get("meta"))[:400])
    for u in (dv.get("units") or []):
        print("  id=%-5s team=%-2s vid=%-22s pos=%s,%s hp=%s/%s abilities=%s"
              % (u.get("id"), u.get("team"), u.get("visualId"),
                 (u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"),
                 u.get("hp"), u.get("hpMax"),
                 [a.get("id") if isinstance(a, dict) else a
                  for a in (u.get("abilities") or [])]))


def cmd_pair(runner: int, uid: int, tgt: int, ab: int, col=None, row=None):
    a = {"runnerId": runner, "unitId": uid, "targetId": tgt, "abilityType": ab}
    if col is not None:
        a["col"] = int(col)
        a["row"] = int(row)
    print(json.dumps(_rpc("pairUtility", [a]), indent=1))


def cmd_dryrun(runner: int):
    r = _rpc("aiDryRunAllUnits", [{"runnerId": runner}])
    print(json.dumps(r, indent=1)[:6000])


def main() -> int:
    cmd = sys.argv[1]
    rest = sys.argv[2:]
    if cmd == "runners":
        cmd_runners()
    elif cmd == "facade":
        cmd_facade(int(rest[0]))
    elif cmd == "mow":
        cmd_mow(int(rest[0]))
    elif cmd == "view":
        cmd_view(int(rest[0]))
    elif cmd == "pair":
        cmd_pair(int(rest[0]), int(rest[1]), int(rest[2]), int(rest[3]),
                 *(rest[4:6] or []))
    elif cmd == "dryrun":
        cmd_dryrun(int(rest[0]))
    else:
        print("unknown cmd %s" % cmd)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
