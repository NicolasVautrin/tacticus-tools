"""PROBE -- `OwnerHasFinishedMinTurns(2)` de PileIn : PER-UNITE (`turnsFinished`) ou per-JOUEUR ?

CRITERE (binaire) : aux fins de tour d'AGE 0 puis d'AGE 1 du MEME grot, le natif consomme-t-il
0 puis >= 1 `genrand_int32` (gate lu sur `BaseUnitComponent + 0x5c` = compteur de l'UNITE), ou
consomme-t-il aux DEUX (gate lu sur `TurnComponent + 0x38` = compteur du JOUEUR, deja >= 2) ?

C'est le seul couple de points ou les deux hypotheses divergent : a l'age 0 le grot vient de
naitre (`turnsFinished` = 1 apres le bump d'`EndTurnOperation`) alors que son joueur a deja
plusieurs tours finis.

CHAINE NATIVE (decompile = verite)
  `IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateTrigger`
    -> `IdunBattleLogic.Entities.DSLTriggers$$OwnerHasFinishedMinTurns(2)`
    -> `IdunBattle.Entities.Triggers.UnitHasFinishedMinTurnsAbilityTrigger$$ShouldTrigger`
         = `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished(Self@0x148) >= 2`
  ECRITURE du compteur : boucle de `IdunBattle.Operations.EndTurnOperation$$Execute` sur
  `PlayerComponent.CurrentlyOwnedUnitIds` (`+0x5c += 1`), AVANT l'execution de `On(0x17)`.

COLONNES
  LIVE        : `genrand_int32` consommes par le `endturn` natif (mesure par re-simulation du MT).
  M1          : le port d'APRES -- gate `UnitComponent.turns_finished >= 2`, seede depuis l'AGE
                observe (seed MANUEL : il ecrase celui de `load_state` pour que les trois regimes
                ne different QUE par cette valeur, et pour atteindre des ages arbitraires).
  M0-joueur   : le port d'AVANT quand le joueur a >= 2 tours finis -> gate VACUANT.
  M0-snapshot : le port d'AVANT sur un etat `load_state` (`turn_counts == {}`) -> gate TOUJOURS FAUX.

CANAL DU COMPTEUR (#234) : `combatSnapshot.units[].turnsFinished` porte `BaseUnitComponent + 0x5c`
via un INVOKE de `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished` -- ce n'est pas un `StatType`
(l'enum va de 0 a 26), donc `GetStat` ne peut pas l'atteindre. `load_state` le consomme depuis #234
(`snapshot._load_unit_turn_state`) ; confront dedie : `probe_234_turnsfinished_seed.py`.

Usage : python probe_pilein_owner_turns.py [--seed 777] [--board MC1_67]
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import rl_collect_batch as R                                   # noqa: E402
from tests.engine.runner._pilein_owner_turns import (          # noqa: E402
    BOARD, CARRIER, ENEMY, ESCORT, measure_grot_age_sweep)


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default=BOARD)
    args = ap.parse_args()

    sid = R._resolve_session()
    w = _unwrap(R._rpc(sid, "autoBootExtraire", [{}], timeout=180))
    if not (isinstance(w, dict) and w.get("ok")):
        print("amorce KO:", str(w)[:200])
        return 2
    print("session %s amorce=%s" % (sid, w.get("skipped") or "done"))

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    sf = ROOT / "logs" / "runners" / ("probe-pilein-owner-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(args.seed), "--state-file", str(sf),
         "--board", args.board, "--roster", "1", "--p-units", "%s,%s" % (CARRIER, ESCORT),
         "--a-units", "%s,%s" % (ENEMY, ENEMY), "--hp-target", "90000", "--hp-player", "90000",
         "--no-ai"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        print("build KO:", (proc.stderr or proc.stdout or "")[-400:])
        return 2
    rid = json.loads(sf.read_text())["runnerId"]
    print("runner %d (seed %s, board %s)" % (rid, args.seed, args.board))
    try:
        records, why = measure_grot_age_sweep(rpc, rid, ages=(0, 1))
        if why:
            print("NOTE:", why)
        print("")
        print("  age | PV pleins | LIVE | M1 (per-unite) | M0-joueur | M0-snapshot | spawn live/M1")
        print("  ----+-----------+------+----------------+-----------+-------------+--------------")
        for rec in sorted(records, key=lambda r: r["age"]):
            print("   %2d |    %-5s  | %4s |      %4d      |   %4d    |    %4d     |    %d / %d"
                  % (rec["age"], "OUI" if rec["full_hp"] else "NON", rec["live_rolls"],
                     rec["port_rolls"], rec["m0_player_rolls"], rec["m0_snapshot_rolls"],
                     rec["live_spawn"], rec["port_spawn"]))
        print("")
        by = {r["age"]: r for r in records}
        if 0 in by and 1 in by:
            ok = (by[0]["live_rolls"] == 0 and by[1]["live_rolls"] >= 1)
            print("VERDICT : gate %s" % ("PER-UNITE (turnsFinished)" if ok else "NON TRANCHE"))
            print("  M1 accorde aux 2 ages : %s"
                  % all(r["port_rolls"] == r["live_rolls"] for r in records))
            print("  M0-joueur   diverge a l'age 0 : %s (%d vs %d)"
                  % (by[0]["m0_player_rolls"] != by[0]["live_rolls"],
                     by[0]["m0_player_rolls"], by[0]["live_rolls"]))
            print("  M0-snapshot diverge a l'age 1 : %s (%d vs %d)"
                  % (by[1]["m0_snapshot_rolls"] != by[1]["live_rolls"],
                     by[1]["m0_snapshot_rolls"], by[1]["live_rolls"]))
        return 0
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        sf.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
