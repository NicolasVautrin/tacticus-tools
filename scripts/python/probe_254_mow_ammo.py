#!/usr/bin/env python
"""#254 -- `DeathOnTheWind` (1213) rendait `ValidRequest` pour TOUTE cible : munitions ou masque ?

`AttackQuery$$GetInvalidTargetReason` sort EN AMONT du filtre de cible quand l'ability n'est pas
disponible (`0x1 ValidRequest`). `DeathOnTheWind` porte la constante `munitionsCost` = 1 et le seed
BC capture pose `MachineOfWarAmmo = 0` sur les trois joueurs : l'ability n'est jamais castable, donc
son masque n'est JAMAIS confronte. Ce probe mesure les deux regimes (ammo 0 vs ammo 5) sur le meme
montage que `test_targeting_masks_live.py::masks_da`.

ASCII only. Usage : python probe_254_mow_ammo.py [--ammo 5]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog_inject as C                                        # noqa: E402
from rl_collect_batch import _resolve_session, _rpc               # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
BOARD = "MC1_67"
MOW = "darkaStormSpeeder"
DA_UNITS = "darkaTerminator,darkaHellblaster,darkaAzrael,darkaAsmodai,darkaCompanion"
FOES = "orksWarboss,orksNob,tyranWingedPrime,ultraInceptorSgt,eldarRanger"


def rpc(sid, method, body=None, timeout=120):
    r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
    return r["result"] if isinstance(r, dict) and "result" in r else r


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ammo", type=int, default=5)
    a = ap.parse_args(argv)

    out = ROOT / "logs" / f"probe254-ammo{a.ammo}.json"
    C.write_augmented_seed_bc(out, [MOW])
    bc = json.loads(out.read_text(encoding="utf-8"))
    for p in ((bc.get("Player") or {}).get("Players") or {}).values():
        if isinstance(p, dict):
            p["MachineOfWarAmmo"] = a.ammo
    out.write_text(json.dumps(bc), encoding="utf-8")
    print(f"[bc] MachineOfWarAmmo = {a.ammo} sur tous les joueurs -> {out}")

    import subprocess
    state = ROOT / "logs" / f"probe254-state-ammo{a.ammo}.json"
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", "777",
                        "--board", BOARD, "--seed-bc", str(out),
                        "--p-units", DA_UNITS, "--p-mow", MOW, "--a-units", FOES,
                        "--no-ai", "--state-file", str(state)],
                       cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print((p.stderr or p.stdout)[-1500:])
        return 2
    rid = json.loads(state.read_text(encoding="utf-8"))["runnerId"]
    sid = _resolve_session()
    for _ in range(6):
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    caster = None
    for m in (dec.get("mows") or []):
        if m.get("visualId") == MOW:
            caster = m.get("casterId")
    print(f"[runner] rid={rid} casterId={caster}")
    alive = [u for u in (dec.get("units") or []) if u.get("alive")]
    for at in (1213, 1214):
        seen = {}
        for t in alive:
            r = rpc(sid, "abilityReason", {"runnerId": rid, "casterId": caster,
                                           "abilityType": at, "targetId": t["id"]}, 60) or {}
            tr = r.get("targetReason") or {}
            seen.setdefault(tr.get("hex"), []).append(t.get("visualId"))
        print(f"  ability {at}: " + json.dumps({k: v for k, v in seen.items()}))
    rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
