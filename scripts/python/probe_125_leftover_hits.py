"""#125 -- flux `state.rng` et REPORT de coups apres un KILL (`ChainLeftOverHitsAttackDamage`).

Ce que le probe MESURE (il ne conclut rien tout seul) :

  1. `--mode sweep` : la chaine MultiThreatEliminator (1006) est rejouee OFFLINE en FORCANT le report
     (`GetLeftOverHits`) a une valeur imposee maillon par maillon, et chaque tuple est confronte au
     per-coup LIVE. C'est le seul moyen de LIRE le report du natif : les coups tombes sur un cadavre
     OVERKILL n'emettent aucun event (`ApplyDamageOperation$$Execute` retourne au premier test
     `HasFlag(target, UnitFlag.Overkilled = 8)`), donc COMPTER LES EVENTS SOUS-ESTIME les coups.
     Le tuple qui reproduit le per-coup LIVE du DERNIER maillon donne le report reellement applique.

  2. `--mode rng` : compte les tirages `state.rng` consommes par un maillon (mirror `IntBasedMersenneTwister`)
     pour confronter le modele « le natif roule tous ses coups meme apres la mort ».

Usage :
  python probe_125_leftover_hits.py --mode sweep --seed 4242 --hp-target 2500 --hp-player 60000 \
      --state-file <ABSOLU unique>
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from probe_116_necrons import (_advance_until_castable, _build, _capture,   # noqa: E402
                               _cast_live, _dispose, _live_per_hit, _offline_cast,
                               _resolve_session, _tid, MULTI_THREAT)
from engine.runner.abilities.behaviours.combat import ChainLeftOverHitsAttackDamage  # noqa: E402
from engine.runner.components import HealthComponent                        # noqa: E402

ROOT = PYDIR.parents[1]


def _chain_of(diag):
    return diag.get("chain") or []


def _force_leftover(seq):
    """Remplace `GetLeftOverHits` par la suite imposee `seq` (index = numero de maillon, 0-based).
    Rend la fonction de restauration."""
    keep = ChainLeftOverHitsAttackDamage.__dict__["_left_over_hits"]
    box = {"i": 0}

    def stub(atk, extra):
        i = box["i"]
        box["i"] += 1
        return int(seq[i]) if i < len(seq) else 0

    ChainLeftOverHitsAttackDamage._left_over_hits = staticmethod(stub)

    def restore():
        ChainLeftOverHitsAttackDamage._left_over_hits = keep
    return restore, box


def _fmt_chain(chain):
    return " | ".join(f"u{c['target']} base={c['hits']} applied={c['applied_hits']} "
                      f"per_hit={c['per_hit']}" for c in chain)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["sweep", "rng"], default="sweep")
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--hp-target", type=int, default=2500)
    ap.add_argument("--hp-player", type=int, default=60000)
    ap.add_argument("--a-units", default="eldarRanger,astraBullgryn,tauMarksman")
    ap.add_argument("--max-leftover", type=int, default=8)
    ap.add_argument("--depth", type=int, default=3)   # nb de maillons dont le report est balaye
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)

    st_file = Path(args.state_file or (ROOT / "data" / "_125_mte_state.json"))
    sid = _resolve_session()
    rid = _build(st_file, ["--seed", str(args.seed), "--board", "MC1_67", "--rank", "17",
                           "--p-units", "necroDestroyer", "--a-units", args.a_units,
                           "--hp-target", str(args.hp_target), "--crit", "0,0",
                           "--hp-player", str(args.hp_player)])
    print(f"[125] runner={rid} session={sid} seed={args.seed} hp_target={args.hp_target}")
    try:
        cid, fh = _advance_until_castable(sid, rid, st_file, "necroDestroyer", MULTI_THREAT)
        if not fh:
            print("[125] pas de cible legale sans bouger")
            return 3
        mkstate, dec, board = _capture(sid, rid)
        tid = _tid(fh[0])
        hp0 = {int(eid): (e.get_component(HealthComponent).hp
                          if e.get_component(HealthComponent) else None)
               for eid, e in mkstate().entities.items()}
        base = _chain_of(_offline_cast(mkstate(), cid, tid, MULTI_THREAT))
        pos = {int(u["id"]): ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
               for u in (dec.get("units") or []) if (u.get("pos") or {}).get("col") is not None}
        print(f"[125] caster=u{cid} target=u{tid} hp={hp0} pos={pos}")
        print(f"[125] PORT (formule courante) : {_fmt_chain(base)}")

        res = _cast_live(sid, rid, cid, tid, MULTI_THREAT, capture_events=True)
        live = _live_per_hit(res, MULTI_THREAT)
        print(f"[125] LIVE per-coup (events, coups OVERKILL absents) = {live}")

        if args.mode == "rng":
            # tirages consommes par un maillon : on compare la position du MT avant/apres.
            st = mkstate()
            before = (st.rng.mti, list(st.rng.mt))
            diag = _offline_cast(st, cid, tid, MULTI_THREAT)
            print(f"[125] rng mti {before[0]} -> {st.rng.mti} ; chain={_fmt_chain(_chain_of(diag))}")
            return 0

        # SWEEP : le report du maillon i est impose ; on cherche le tuple qui reproduit le LIVE.
        # PROFONDEUR FIXE (`--depth`), JAMAIS derivee de la chaine du port : si le port sous-estime le
        # report, sa chaine est plus COURTE que celle du natif et un sweep dimensionne dessus ne peut
        # pas atteindre les maillons manquants (piege verifie : depth=1 arretait la chaine au 2e maillon).
        n = int(args.depth)
        grid = range(0, args.max_leftover + 1)
        hits = []
        same = []
        for seq in itertools.product(grid, repeat=max(1, n - 1)):
            restore, _box = _force_leftover(list(seq))
            try:
                ch = _chain_of(_offline_cast(mkstate(), cid, tid, MULTI_THREAT))
            finally:
                restore()
            # DISCRIMINANT = le(s) maillon(s) dont la cible SURVIT au LIVE (aucun event a 0 ET somme
            # des events < PV de depart) : la, le per-coup LIVE n'est ni clampe par les PV ni tronque
            # par la suppression d'event des coups OVERKILL -> il se confronte EXACTEMENT au port.
            surv = [t for t, lv in live.items()
                    if all(lv) and hp0.get(t) is not None and sum(lv) < hp0[t]]
            got = {int(c["target"]): list(c["per_hit"]) for c in ch}
            if set(got) == set(live):
                same.append((seq, ch))
            if surv and all(got.get(t) == list(live[t]) for t in surv):
                hits.append((seq, ch))
        print(f"[125] maillons DISCRIMINANTS (cible survivante) = "
              f"{[t for t, lv in live.items() if all(lv) and hp0.get(t) is not None and sum(lv) < hp0[t]]}")
        print(f"[125] SWEEP {len(hits)} tuple(s) de report compatibles avec le LIVE :")
        for seq, ch in hits[:30]:
            print(f"   report={list(seq)} -> {_fmt_chain(ch)}")
        if not hits:
            print("[125] AUCUN tuple compatible -- l'ecart n'est PAS (que) le report de coups")
        print(f"[125] tuples atteignant le MEME set de cibles que le LIVE ({len(same)}) :")
        for seq, ch in same[:30]:
            print(f"   report={list(seq)} -> {_fmt_chain(ch)}")
        print("[125] TABLE report du 1er maillon (les suivants forces a 2) :")
        for l1 in grid:
            seq = [l1] + [2] * max(0, n - 2)
            restore, _box = _force_leftover(seq)
            try:
                ch = _chain_of(_offline_cast(mkstate(), cid, tid, MULTI_THREAT))
            finally:
                restore()
            print(f"   L1={l1} -> {_fmt_chain(ch)}")
    finally:
        if not args.keep:
            _dispose(st_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
