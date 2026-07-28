"""Probe #o10-a -- DECOMPOSITION PAR ETAGE des PV apres une attaque de CHARGE d'`astraBullgryn`.

QUESTION TRANCHEE ICI. Le rejeu offline de l'attaque de charge est bit-exact COUP PAR COUP avec le
live (`test_ischarging_extra_damage_live.py::test_charge_is_charging`), mais les PV de la cible
APRES l'attaque ne coincident pas. Deux etages possibles, et un seul est un ecart de port :

  (1) l'APPLICATION des coups differe (meme liste de degats, PV differents) -> vrai bug de port ;
  (2) la CASCADE live contient autre chose que les coups (soin declenche, reaction, effet de fin
      d'activation) que le port ne rejoue pas -> les PV ne sont PAS un etage propre de comparaison,
      la liste per-coup l'est.

On mesure donc, sur le MEME enregistrement : PV cible AVANT (snapshot pre-pas), PV cible APRES
(live `applyAction.units` et offline `HealthComponent`), la liste per-coup des deux cotes, et le
FLUX D'EVENEMENTS live complet de l'action (tags), ou un soin se verrait nommement.

REPONSE MESUREE (2026-07-28, seed 777 / `MC1_67` / `astraBullgryn` vs `necroOverlord,necroWarden`,
reproduit a l'identique sur deux runners) : c'est le cas (2), et `applyAction.units[].hp` est un
PIEGE DE MESURE.

    PV AVANT  : live 120000 | offline 120000
    per-coup  : live [3935, 3757, 3078, 3132] | offline IDEM (bit-exact)
    PV APRES  : live(units[].hp) 118098 | offline 106098      <- ecart apparent de 12000

Le flux d'evenements tranche : les quatre evenements de degat portent
`UnitStats_RemainingHealth` = 116065 / 112308 / 109230 / **106098** -- l'APPLICATION des coups est
donc EXACTE, au PV pres. L'ecart nait APRES : l'attaque etait la derniere action du caster, la meme
reponse porte donc la bascule de tour (`Match_PreviousPlayerId` 3 -> `Match_CurrentPlayerId` 4),
puis le groupe **`LivingMetalRepair`** de `necroOverlord` la remonte a 118098 (+12000 = 10 % des PV
max) et deux ripostes (`Passive_Ability_Type` 1045) repartent sur le caster.

CONTRE-EPREUVE (meme probe, `--seed 31337 --board C1_25 --a-units orksNob,tyranTyrantGuard`) : PV
APRES **live 109873 == offline 109873**, delta identique des deux cotes. Le confond est donc bien la
CASCADE de ce montage-la (le soin Necron), pas l'application des degats -- si le port appliquait mal,
l'ecart survivrait au changement de cibles.

CE QU'IL FAUT EN RETENIR : `applyAction.units[]` est l'etat de FIN DE CASCADE. Le confronter a un
rejeu offline qui n'a joue QUE l'attaque compare deux points differents du pipeline et fabrique un
faux « bug de port » chiffre (ici 12000 PV). L'etage PROPRE, celui que le port doit egaler, est le
`UnitStats_RemainingHealth` du DERNIER evenement de degat de l'attaque -- c'est ce que garde
desormais `test_ischarging_extra_damage_live.py::test_charge_bonus_is_not_vacuous`.

Usage (depuis scripts/python, session warmee) :
    python probe_o10a_charge_hp_stage.py [--seed 777] [--board MC1_67] [--a-units ...]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import rl_collect_batch as R
from engine.entities.pathfinding.board import Board
from engine.runner.components import HealthComponent

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))
from _charge_regime import CHARGE, ChargeRegimeHarness      # noqa: E402


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--a-units", default="necroOverlord,necroWarden")
    ap.add_argument("--state-file",
                    default=str(PYDIR.parents[1] / "logs" / "runners" / "probe-o10a-hp.json"))
    a = ap.parse_args(argv)

    sid = R._resolve_session()

    def rpc(method, body=None, timeout=90):
        r = R._rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r.get("result") if isinstance(r, dict) and "result" in r else r

    Path(a.state_file).parent.mkdir(parents=True, exist_ok=True)
    build = [sys.executable, "rl_duel.py", "build", "--seed", a.seed, "--board", a.board,
             "--state-file", a.state_file, "--p-units", "astraBullgryn",
             "--a-units", a.a_units, "--hp-target", "120000",
             "--hp-player", "120000", "--no-ai"]
    p = subprocess.run(build, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(a.state_file).exists():
        print("BUILD KO", (p.stderr or p.stdout)[-400:])
        return 1
    rid = json.loads(Path(a.state_file).read_text())["runnerId"]
    print("runner=%s seed=%s board=%s a_units=%s" % (rid, a.seed, a.board, a.a_units))
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            print("boardGraph KO")
            return 1
        h = ChargeRegimeHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        rec = h.run(caster_visual="astraBullgryn", regime=CHARGE)
        if rec is None or not rec.get("live_ok"):
            print("montage CHARGE non realisable (rec=%s)" % (rec is not None,))
            return 1
        tid = rec["target"]

        hp_before_dv = next((u.get("hp") for u in (rec["snapshot"]["dv"].get("units") or [])
                             if u.get("id") == tid), None)
        hp_before_ob = next((u.get("hp") for u in (rec["snapshot"]["ob"].get("units") or [])
                             if u.get("squadId") == tid), None)
        live_after = next((u.get("hp") for u in ((rec.get("live_raw") or {}).get("units") or [])
                           if u.get("squadId") == tid), None)

        off = h.replay_offline(rec)
        e = off["state"].get_entity(tid)
        off_after = e.get_component(HealthComponent).hp if e is not None else None
        st0 = h.offline_state(rec)
        e0 = st0.get_entity(tid)
        off_before = e0.get_component(HealthComponent).hp if e0 is not None else None

        print("target=%s" % tid)
        print("PV AVANT  : live(dv)=%s live(ob)=%s | offline(seede)=%s"
              % (hp_before_dv, hp_before_ob, off_before))
        print("per-coup  : live=%s | offline=%s" % (rec["live_per_hit"], off["per_hit"]))
        print("somme     : live=%s | offline=%s"
              % (sum(rec["live_per_hit"] or []), sum(off["per_hit"] or [])))
        print("PV APRES  : live=%s | offline=%s" % (live_after, off_after))
        if hp_before_dv is not None and live_after is not None:
            print("delta PV  : live=%s | offline=%s"
                  % (hp_before_dv - live_after,
                     (off_before - off_after) if None not in (off_before, off_after) else None))

        # FLUX D'EVENEMENTS live de l'action : c'est la qu'un soin/reaction se nomme.
        a0 = ((rec.get("live_raw") or {}).get("actions") or [{}])[0]
        evs = a0.get("events") or []
        print("\nevents live = %d" % len(evs))
        kinds = Counter()
        for i, ev in enumerate(evs):
            td = ev.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            kinds[str(ev.get("name") or ev.get("type") or ev.get("kind") or "?")] += 1
            meta = {k: v for k, v in ev.items() if k != "tags"}
            print("  [%02d] %s" % (i, meta))
            if td:
                print("       tags=%s" % (td,))
        print("\nnoms d'events :", dict(kinds))
        return 0
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
