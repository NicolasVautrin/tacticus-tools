"""Probe #912 -- le montage de `test_path_of_command_crit_aura_live` produit-il ENCORE un allie a
`CritChance == 0` ?

Le test exige qu'un allie A PORTEE mais SANS chance de crit ne recoive RIEN du volet CRIT de
`PathOfCommand` (le noeud `UnitsWithStatBiggerThan(..., CritChance, Current, Constant(0),
excludingEffect)`). Il prend `eldarFarseer` pour cet allie, sur la premisse ecrite au montage :
« chance de crit 0 (la normalisation la met a 0) ».

⚠ CETTE PREMISSE EST UNE PROPRIETE DU HARNAIS, PAS DU JEU. Depuis #419-r5/#419-r6,
`_normalize_and_extract_pool` EQUIPE par defaut chaque unite de ses items Best-In-Slot, et les
quatre stats crit/block ne vivent QUE dans les items : la mesure inscrite dans sa docstring donne
`could_crit` **0/106 -> 98/106**. Ce probe LIT la stat, il ne la deduit pas.

TROIS bras, sur le MEME montage que le test (`--seed 31337`, `--board MC1_67`, `--no-ai`) :

  A  regime COURANT (items BiS equipes -- le defaut)
  B  `TACTICUS_BIS_ITEMS=0` -- le TEMOIN du regime d'avant #419-r5
  C  regime COURANT + `--unit-stat eldarFarseer:CritChance=0` -- le porteur RECONSTRUIT

La mesure est prise AVANT l'atterrissage de l'Autarch (deep-strike : ses passives sont deferrees),
donc avant toute pose de l'aura : c'est la chance de crit de BASE qui est en cause.

Usage :
    python probe_912_crit_zero_porteur.py [--bras A,B,C]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from rl_collect_batch import _rpc, _resolve_session

PYDIR = Path(__file__).resolve().parent
LOGS = PYDIR.parent.parent / "logs" / "runners"

CARRIER = "eldarAutarch"
ALLY_CRIT = "eldarRanger"
ALLY_NOCRIT = "eldarFarseer"
FOE = "necroWarden"
CRIT_SEED = 20
#: Les args EXACTS du montage de `test_path_of_command_crit_aura_live.BUILD`.
BUILD = ["--p-units", f"{CARRIER},{ALLY_CRIT},{ALLY_NOCRIT}", "--a-units", f"{FOE},{FOE},{FOE}",
         "--no-ai",
         "--unit-stat", f"{ALLY_CRIT}:CritChance={CRIT_SEED}",
         "--unit-stat", f"{FOE}:CritChance={CRIT_SEED}"]


def _unwrap(r):
    return r["result"] if isinstance(r, dict) and "result" in r else r


def rpc(sid, method, body=None, timeout=120):
    return _unwrap(_rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def _build(state_file: Path, extra=(), env_bis=None) -> int:
    env = dict(os.environ)
    if env_bis is not None:
        env["TACTICUS_BIS_ITEMS"] = str(env_bis)
    state_file.unlink(missing_ok=True)
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", "31337",
                        "--board", "MC1_67", "--state-file", str(state_file), *BUILD, *extra],
                       cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    if not state_file.is_file():
        raise SystemExit("build KO : %s" % ((p.stderr or p.stdout or "")[-600:],))
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def _stats(sid, rid, dv):
    """`critChance` de BASE (et son delta) par visualId, AVANT toute pose d'aura."""
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    par_id = {u["id"]: u.get("visualId") for u in (dv.get("units") or []) if u.get("id") is not None}
    out = {}
    for u in (snap.get("units") or []):
        vis = par_id.get(u.get("entityId"))
        if vis is None:
            continue
        st, dl = (u.get("stats") or {}), (u.get("statDelta") or {})
        out.setdefault(vis, []).append({"cc": int(st.get("critChance") or 0),
                                        "d_cc": int(dl.get("critChance") or 0),
                                        "cd": int(st.get("critDamage") or 0),
                                        "att": int(st.get("attack") or 0)})
    return out


def _bras(sid, nom: str, extra=(), env_bis=None) -> dict:
    sf = LOGS / ("p912_%s_%d.json" % (nom, os.getpid()))
    sf.parent.mkdir(parents=True, exist_ok=True)
    rid = _build(sf, extra=extra, env_bis=env_bis)
    try:
        dv = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        mesure = _stats(sid, rid, dv)
        teleport = any((e.get("name") or "") == "TeleportStrike_TeleportingIn"
                       for u in (dv.get("units") or []) if u.get("visualId") == CARRIER
                       for e in (u.get("effects") or []))
        print("[912][%s] runner %d -- Autarch en teleport-in : %s" % (nom, rid, teleport))
        for vis in (CARRIER, ALLY_CRIT, ALLY_NOCRIT, FOE):
            print("[912][%s]   %-16s %s" % (nom, vis, json.dumps(mesure.get(vis))))
        return mesure
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass
        sf.unlink(missing_ok=True)


def mesure(args) -> int:
    sid = _resolve_session()
    veut = [b.strip().upper() for b in (args.bras or "A,B,C").split(",") if b.strip()]
    res = {}
    if "A" in veut:
        res["A"] = _bras(sid, "A")
    if "B" in veut:
        res["B"] = _bras(sid, "B", env_bis=0)
    if "C" in veut:
        res["C"] = _bras(sid, "C", extra=["--unit-stat", f"{ALLY_NOCRIT}:CritChance=0"])

    print("[912] --- VERDICT ---")
    for nom, m in res.items():
        cc = (m.get(ALLY_NOCRIT) or [{}])[0].get("cc")
        print("[912] bras %s : %s.critChance de BASE = %s -> premisse « allie SANS crit » %s"
              % (nom, ALLY_NOCRIT, cc, "TENUE" if cc == 0 else "FAUSSE"))
    ok = any((m.get(ALLY_NOCRIT) or [{}])[0].get("cc") == 0 for m in res.values())
    return 0 if ok else 1


def _parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bras", default="A,B,C")
    return ap


if __name__ == "__main__":
    sys.exit(mesure(_parser().parse_args()))
