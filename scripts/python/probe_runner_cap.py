#!/usr/bin/env python
"""probe_runner_cap.py — verifie le cap dur MAX_RUNNERS des builds runner.

Depuis 2026-07-03 la coexistence est le DEFAUT (initAndStart ne dispose plus
jamais les runners freres ; --keep/keepExisting supprimes). Le cap dur
MAX_RUNNERS prend le relais : au cap, initAndStart doit REFUSER explicitement
(message "runner cap reached" + liste des runnerIds actifs), jamais nuker ni
reussir.

Ce que ce probe verifie n'a PAS change ; sa justification, si. Le cap valait 10
parce qu'il etait derive d'un budget de handles suppose (« ~900 »). Ce budget a
ete MESURE et REFUTE le 2026-07-26 (probe_132_gcroot_budget.py : 3 handles par
bataille, build reussi a 5004 handles epingles, latence plate a 10 runners) ; le
cap est passe a 50, borne desormais par la MEMOIRE (~3,6 Mo de tas manage par
runner vivant), pas par les handles. Le contrat teste ici — refus explicite au
cap, zero nuke — reste identique.

Ce probe (parametrable, reutilisable — assertions generiques, pas de valeurs
figees autres que le cap attendu) :
  1. lit l'etat courant du registry (listRunners) ;
  2. enchaine des initAndStart (BC + playerUnits + seed relus d'un state-file
     rl_duel existant) jusqu'au REFUS, avec une borne de securite ;
  3. verifie que le refus survient exactement a len(listRunners) == cap et
     que le message d'erreur est explicite ;
  4. DISPOSE tous les runners qu'il a crees (jamais ceux des autres acteurs).

Usage :
  python probe_runner_cap.py --state-file data/_coex_A.json [--expected-cap 50]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rl_collect_batch import _rpc  # noqa: E402
import rl_duel as RD  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _list_runners(sid: int) -> list[dict]:
    return _rpc(sid, "listRunners", [], timeout=10).get("result") or []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True,
                    help="state-file rl_duel existant (bc+playerUnits+seed) ; "
                         "chemin relatif = ancre racine repo")
    ap.add_argument("--expected-cap", type=int, default=50,
                    help="valeur attendue de MAX_RUNNERS (runner-registry.ts)")
    ap.add_argument("--max-builds", type=int, default=None,
                    help="borne de securite (defaut: expected-cap + 2)")
    a = ap.parse_args(argv)

    sf = Path(a.state_file)
    if not sf.is_absolute():
        sf = ROOT / sf
    st = json.loads(sf.read_text(encoding="utf-8"))
    bc, pu, seed = st["bc"], st["playerUnits"], st.get("seed")

    sid = RD._resolve_session()
    pre = _list_runners(sid)
    pre_ids = {r["runnerId"] for r in pre}
    print(f"[cap] session={sid} runners preexistants={sorted(pre_ids)} "
          f"cap attendu={a.expected_cap}")

    max_builds = a.max_builds or (a.expected_cap + 2)
    created: list[int] = []
    refusal = None
    try:
        for i in range(max_builds):
            resp = _rpc(sid, "initAndStart",
                        [{"configJson": json.dumps(bc), "seed": seed,
                          "playerUnits": pu}], timeout=40)
            res = resp.get("result") or {}
            rid = res.get("runnerId")
            if rid is not None:
                created.append(rid)
                print(f"[cap] build #{i+1} OK runnerId={rid} "
                      f"(total={len(pre_ids) + len(created)})")
                continue
            refusal = str(resp.get("error") or resp)
            print(f"[cap] build #{i+1} REFUSE: {refusal}")
            break

        # ---- verdicts (generiques : bases sur l'etat relu, pas des ids figes)
        total_at_refusal = len(_list_runners(sid))
        ok = True
        if refusal is None:
            print(f"[FAIL] aucune refusal apres {max_builds} builds "
                  f"(total={total_at_refusal}) — cap absent ?")
            ok = False
        else:
            if "runner cap reached" not in refusal:
                print(f"[FAIL] message de refus non explicite: {refusal}")
                ok = False
            if total_at_refusal != a.expected_cap:
                print(f"[FAIL] refus a total={total_at_refusal}, "
                      f"attendu {a.expected_cap}")
                ok = False
            # le refus ne doit avoir nuke PERSONNE : les preexistants vivent
            post_ids = {r["runnerId"] for r in _list_runners(sid)}
            missing = pre_ids - post_ids
            if missing:
                print(f"[FAIL] runners preexistants disparus: {sorted(missing)}")
                ok = False
        if ok:
            print(f"[OK] cap={a.expected_cap} respecte, refus explicite, "
                  f"zero nuke (preexistants intacts: {sorted(pre_ids)})")
    finally:
        # dispose UNIQUEMENT les runners crees par ce probe
        for rid in created:
            try:
                _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=15)
            except Exception:
                pass
        print(f"[cap] {len(created)} runner(s) du probe dispose(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
