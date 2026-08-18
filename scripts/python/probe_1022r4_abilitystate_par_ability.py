"""#1022-r4 -- LE COUPLE (niveau, multiplicateur) EST-IL LE MEME POUR TOUTES LES ACTIVES D'UNE MoW ?

CRITERE. `IdunBattle.Entities.Behaviours.SpawnUnitOptions$$WithStatsFromConfig(config, abilityState,
ordinal, abilitiesLevel, variableMultiplierPercentage)` indexe les variables `summon*` sous
l'`abilityState` de l'ability CASTEE. Cote port, la feuille `Spawn` lit par defaut le SCALAIRE
`UnitContext.active_ability_level`, que `engine.runner.snapshot._machine_ability_state` remplit avec
la PREMIERE active de la MoW portant un etat. Les deux lectures coincident SSI toutes les actives
d'une meme MoW portent le meme couple.

Ce probe le MESURE, MoW par MoW : il monte un runner par MoW du pool et imprime, pour chacune, les
couples `(id, level, multiplier)` de `decisionView.mows[].abilities[]`. Sortie ASCII.

    python probe_1022r4_abilitystate_par_ability.py [--mow ultraDreadnought,...] [--board MC1_67]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

from rl_collect_batch import _rpc as rpc, _resolve_session

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

MOWS = ["ultraDreadnought", "tauBroadside", "orksRukkatrukk", "deathCrawler"]


def build(seed: str, board: str, mow: str):
    state = ROOT / "logs" / "runners" / ("st-1022r4-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
         "--state-file", str(state), "--no-ai",
         "--p-units", "ultraTigurius,ultraCalgar", "--a-units", "necroWarden,necroSpyder",
         "--p-mow", mow],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO (%s) : %s" % (mow, (p.stderr or p.stdout or "")[-400:]))
        return None
    return json.loads(state.read_text())["runnerId"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--mow", default=",".join(MOWS))
    a = ap.parse_args()
    sid = _resolve_session()

    divergents = 0
    mesurees = 0
    for mow in [m for m in a.mow.split(",") if m]:
        rid = build(a.seed, a.board, mow)
        if rid is None:
            continue
        try:
            v = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
            rows = [m for m in (v.get("mows") or []) if m.get("visualId") == mow]
            if not rows:
                # LEVER l'echec plutot que rendre un zero : `mows` peut etre vide (MoW non
                # deployee) OU porter un autre `visualId` (la ligne est la PLATEFORME).
                print("%-18s : ABSENTE de decisionView.mows -- NON MESURE ; brut=%s"
                      % (mow, json.dumps(v.get("mows"))[:400]))
                continue
            abs_ = [(x.get("id"), x.get("kind"), x.get("level"), x.get("multiplier"))
                    for x in (rows[0].get("abilities") or [])]
            etats = {(lv, mu) for _i, _k, lv, mu in abs_ if lv is not None or mu is not None}
            mesurees += 1
            divergents += int(len(etats) > 1)
            print("%-18s : %d ability(s) | etats distincts=%d | %s"
                  % (mow, len(abs_), len(etats), abs_))
        finally:
            try:
                rpc(sid, "disposeRunner", {"runnerId": rid}, timeout=30)
            except Exception as exc:                                     # noqa: BLE001
                print("  dispose KO : %s" % exc)

    print("")
    print("MoW MESUREES        : %d" % mesurees)
    print("MoW A >1 ETAT       : %d" % divergents)
    if mesurees == 0:
        print("NON MESURE : aucune MoW n'a pu etre montee -- ce zero n'est PAS un resultat")
        return 2
    if divergents == 0:
        print("VERDICT : sur ce runner, toutes les actives d'une meme MoW partagent leur couple")
        print("          (level, multiplier). Le scalaire du port et l'`AbilityState` par ability")
        print("          COINCIDENT donc ici -- aucun regime SEPARANT n'est constructible par cette")
        print("          voie, et le raffinement reste INVALIDABLE LIVE (residu).")
    else:
        print("VERDICT : au moins une MoW porte DEUX couples distincts -- regime SEPARANT trouve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
