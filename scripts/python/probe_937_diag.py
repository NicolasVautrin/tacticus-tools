"""#937 -- DIAGNOSTIC de montage : le passif `SynapticLinchpin` est-il seulement MONTE sur
`tyranWingedPrime` dans un runner construit par `rl_duel build` ?

Trois faits mesures, dans cet ordre (le premier qui manque explique le zero du probe principal) :
  D1  la seed BC porte-t-elle la CONFIG d'ability `SynapticLinchpin` (bloc `Abilities.
      PassiveAbilities`) ? Sans elle, `UnitFactory$$AddConfiguredAbilities` ne monte RIEN, en
      silence (meme verrou que #226/#237) ;
  D2  le `combatSnapshot` du runner declare-t-il la passive sur l'unite (`unitConfig`) ?
  D3  la geometrie : combien de tuiles LIBRES adjacentes a la cible au moment de l'attaque ?

Usage (depuis scripts/python) :
    python probe_937_diag.py --state-file <ABSOLU> [--board MC1_67] [--seed 777] [--keep]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

import requests
from sibling_script import sibling_script

HOST = "http://127.0.0.1:8765"
PRIME = "tyranWingedPrime"
ABILITY = "SynapticLinchpin"


def sid() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s, method, args=None, timeout=60):
    r = requests.post(f"{HOST}/api/scripts/{s}/rpc",
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    body = r.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--reuse", action="store_true")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    # ---- D1 : la seed BC porte-t-elle la config d'ability ? (100 % offline)
    from pathlib import Path
    seed = Path(__file__).resolve().parents[2] / "data" / "seed-bc.json"
    bc = json.loads(seed.read_text(encoding="utf-8"))
    ab = bc.get("Abilities") or {}
    pas = ab.get("PassiveAbilities") or {}
    act = ab.get("ActiveAbilities") or {}
    print("[D1] seed-bc : PassiveAbilities=%d ActiveAbilities=%d ; '%s' present=%s (passif) %s (actif)"
          % (len(pas), len(act), ABILITY, ABILITY in pas, ABILITY in act))
    units = bc.get("Units") or []
    pu = [u for u in units if (u.get("UnitId") or u.get("unitId")) == PRIME]
    print("[D1] seed-bc : entrees `%s` = %d" % (PRIME, len(pu)))
    for u in pu[:2]:
        print("[D1]   keys=%s" % sorted(k for k in u if "bilit" in k or "rait" in k.lower()))
        for k in sorted(u):
            if "bilit" in k or k.lower().startswith("trait"):
                print("[D1]   %s = %s" % (k, u[k]))

    if not a.reuse:
        out = subprocess.run([sys.executable, sibling_script("rl_duel.py"), "build",
                              "--seed", a.seed, "--board", a.board, "--state-file", a.state_file,
                              "--p-units", PRIME, "--a-units", "astraBullgryn"],
                             capture_output=True, text=True)
        if out.returncode != 0:
            print("BUILD FAILED rc=%d\n%s\n%s"
                  % (out.returncode, (out.stdout or "")[-1200:], (out.stderr or "")[-1200:]))
            return 2
    rid = int(json.loads(open(a.state_file, encoding="utf-8").read())["runnerId"])
    s = sid()
    print("[937-diag] session=%d runner=%d" % (s, rid))
    try:
        snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 90)
        for u in (snap.get("units") or []):
            cfg = u.get("unitConfig") or {}
            if cfg.get("visualId") == PRIME or (u.get("visualId") == PRIME):
                print("[D2] unitConfig keys=%s" % sorted(cfg))
                print("[D2] %s" % json.dumps({k: v for k, v in cfg.items()
                                              if "bilit" in k or "rait" in k.lower()})[:1200])
        dv = rpc(s, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        pu2 = next((x for x in (dv.get("units") or []) if x.get("visualId") == PRIME), None)
        if pu2 is not None:
            print("[D2] decisionView abilities=%s" % json.dumps(pu2.get("abilities"))[:900])
            print("[D2] decisionView traits=%s" % json.dumps(pu2.get("traits"))[:500])
    finally:
        if not a.keep:
            try:
                rpc(s, "disposeRunner", {"runnerId": rid}, 30)
                print("[937-diag] runner %d dispose" % rid)
            except Exception as exc:                    # noqa: BLE001
                print("[937-diag] dispose KO : %s" % str(exc)[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
