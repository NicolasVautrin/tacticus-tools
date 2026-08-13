"""#996-r1 -- `1015 PrecisionShot` : REACHABILITE d'abord, port ensuite.

`PrecisionShotAbility$$GetDynamicInvalidCasterReason` rend `0x2 TargetMatchesDynamicRule` tant que
le caster n'a PAS l'effet `1015 EffectType.PrecisionShot_Aim` -- et le SEUL poseur de cet effet est
`1012 PrecisionShot_AimAbility`, que le porteur ne declare PAS au gameconfig
(`activeAbilities: ["PrecisionShot"]`). Avant de porter quoi que ce soit, ce probe MESURE :

  * le kit ACTIF que la bataille monte reellement sur le Deathmark (1015 seule ? 1012 / 1013 aussi ?) ;
  * ce que l'oracle natif `abilityReason` rend pour 1015, 1012 et 1013 sur une cible legale.

C'est la seule facon de trancher si l'`ExecuteBehaviour` de 1015 est ATTEIGNABLE, ou si sa face
observable se reduit au GATE. Un port ecrit sans cette mesure serait speculatif.

Usage : python probe_996r1_precision_shot.py --state-file <ABSOLU propre>
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

import hexgeo

from engine.entities.active_ability_type import ActiveAbilityType

PYDIR = Path(__file__).resolve().parent
HOST = "http://127.0.0.1:8765"

PORTEUR = "necroNpc3Deathmark:45"
PORTEUR_VIS = "necroNpc3Deathmark"
ALLIE = "ultraTitus"
ENNEMIS = ("eldarRanger", "astraBullgryn", "darkaCompanion")
BOARD = "MC1_67"
SEED = "999"

IDS = (int(ActiveAbilityType.PrecisionShot),          # 1015
       int(ActiveAbilityType.PrecisionShot_Aim),      # 1012
       int(ActiveAbilityType.PrecisionShot_Attack))   # 1013


def _sid():
    return requests.get("%s/api/admin/status" % HOST, timeout=10).json()["session"]["id"]


def _rpc(sid, method, body=None, timeout=180):
    r = requests.post("%s/api/scripts/%s/rpc" % (HOST, sid),
                      json={"method": method, "args": [body] if body is not None else []},
                      timeout=timeout).json()
    return r.get("result", r)


def _build(sid, state_file: str) -> int:
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD, "--no-ai",
           "--state-file", state_file, "--explicit-stats", PORTEUR,
           "--p-units", "%s,%s" % (PORTEUR, ALLIE), "--a-units", ",".join(ENNEMIS),
           "--hp-target", "400000"]
    Path(state_file).parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0 or not Path(state_file).exists():
        raise RuntimeError("build KO rc=%d : %s" % (p.returncode, (p.stderr or p.stdout)[-1500:]))
    return int(json.loads(Path(state_file).read_text(encoding="utf-8"))["runnerId"])


def _hexi(h):
    try:
        return int(str(h), 16) if h else 0
    except ValueError:
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    a = ap.parse_args()
    sid = _sid()
    rid = _build(sid, a.state_file)
    try:
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        caster = next((u for u in units if (u.get("visualId") or "") == PORTEUR_VIS), None)
        print("[1015] caster id=%s vis=%s pos=%s" % (caster["id"], caster.get("visualId"),
                                                    caster.get("pos")))
        print("[1015] KIT ACTIF monte par la bataille : %r"
              % ([(x.get("id"), x.get("name")) for x in (caster.get("abilities") or [])],))
        ab = _rpc(sid, "unitAbilityStates", {"runnerId": rid}, 60)
        for e in (ab.get("units") or ab.get("states") or []):
            if int(e.get("id", e.get("unitId", -1))) == int(caster["id"]):
                print("[1015] unitAbilityStates : %s" % json.dumps(e)[:900])
        cibles = [u for u in units if u.get("team") != caster.get("team")]
        cibles.sort(key=lambda u: hexgeo.distance((caster["pos"]["col"], caster["pos"]["row"]),
                                                  (u["pos"]["col"], u["pos"]["row"])))
        for aid in IDS:
            for cible in (caster, cibles[0]):
                r = _rpc(sid, "abilityReason",
                         {"runnerId": rid, "casterId": int(caster["id"]),
                          "abilityType": int(aid), "targetId": int(cible["id"])}, 60)
                print("[1015] abilityReason ability=%-5s cible=%-4s casterReason=%s targetReason=%s"
                      % (aid, cible["id"],
                         hex(_hexi(((r or {}).get("casterReason") or {}).get("hex"))),
                         hex(_hexi(((r or {}).get("targetReason") or {}).get("hex")))))
        # Le CAST lui-meme : `ok:True` ne veut pas dire << execute >> (case-996) -- le discriminant
        # est `actionConsumed` + `changes`.
        for aid in IDS:
            res = _rpc(sid, "applyAction",
                       {"runnerId": rid,
                        "action": {"kind": "ability", "casterId": int(caster["id"]),
                                   "targetId": int(caster["id"] if aid != IDS[2]
                                                   else cibles[0]["id"]),
                                   "abilityType": int(aid)}}, 240)
            a0 = ((res or {}).get("actions") or [{}])[0]
            print("[1015] applyAction ability=%-5s ok=%r mutated=%r actionConsumed=%r n_changes=%s"
                  % (aid, a0.get("ok"), a0.get("mutated"), a0.get("actionConsumed"),
                     len(a0.get("changes") or [])))
    finally:
        _rpc(sid, "disposeRunner", {"runnerId": int(rid)}, 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
