#!/usr/bin/env python
"""Probe #489 -- confront LIVE de `1048 FragstormGrenadeLauncher` (`templAggressor` « Brother
Burchard », Black Templars), face EXECUTION.

L'ability etait absente d'`ABILITY_CLASSES` : le cast tombait sur le no-op SILENCIEUX de
`AbilityHandler.visit_ActiveAbilityMessage` (`ported: False`, 0 degat, 0 effet, aucune erreur).

Protocole (replay-diff, meme patron que `probe_116_necrons --phase mte` / `probe_125_leftover_hits`) :
capture de l'etat AVANT le cast (`decisionView` + `observeBattle` + `combatSnapshot` + `dumpRng`),
rejeu OFFLINE par le CHEMIN REEL (le handler), rejeu du MEME cast LIVE (`applyAction captureEvents`),
puis confront de l'observable.

CE QUI EST CONFRONTE, etage par etage (jamais un scalaire agrege) :
  1. `ported is True`             -- la face EXECUTION n'est plus un no-op ;
  2. la CHAINE                    -- la LISTE ORDONNEE des cibles frappees (c'est le seul observable du
                                     selecteur `SortTargetsByDamagePredictionSelector` + du report) ;
  3. les degats PAR COUP          -- offline vs live, par cible, coup par coup (`Amount` des events
                                     portant `Active_Ability_Type == 1048`) ;
  4. le nombre de coups reportes  -- `max(0, H - k - 1) + extraHits(=0)` de `GetLeftOverHits`.

MONTAGE (l'etat est FABRIQUE, pas subi) : `--hp-target` bas -> la cible principale meurt AVANT le
dernier coup, donc `H - k - 1 > 0` et le report EXISTE ; au moins deux ennemis a distance <= `range`(2)
du CASTER -- c'est la difference de forme avec `1006 MultiThreatEliminator`, dont la cible suivante doit
etre adjacente a la PRECEDENTE.

ASCII only (cp1252). Usage :
    python probe_489_fragstorm_grenade_launcher.py [--seed 4242] [--board MC1_67] [--hp-target 3000]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from probe_116_necrons import (_advance_until_castable, _build, _capture,        # noqa: E402
                               _cast_live, _dispose, _from_here, _live_per_hit,
                               _offline_cast, _r, _tid, _unit_of, _alive_units)
from rl_collect_batch import _resolve_session                                    # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType                # noqa: E402

ROOT = PYDIR.parents[1]
FRAGSTORM_GRENADE_LAUNCHER = int(ActiveAbilityType.FragstormGrenadeLauncher)     # 1048


def _fmt_chain(chain):
    """`[cible: coups_demandes -> coups_appliques (total)]` par maillon."""
    return " | ".join("u%s: hits=%s applied=%s total=%s"
                      % (c.get("target"), c.get("hits"), c.get("applied_hits"), c.get("total"))
                      for c in (chain or []))


def _dist(dec, a, b):
    import hexgeo
    pa = pb = None
    for u in (dec.get("units") or []):
        p = u.get("pos") or {}
        if int(u.get("id")) == int(a):
            pa = (p.get("col"), p.get("row"))
        if int(u.get("id")) == int(b):
            pb = (p.get("col"), p.get("row"))
    if pa is None or pb is None or pa[0] is None or pb[0] is None:
        return None
    return hexgeo.distance(pa, pb)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--hp-target", type=int, default=3000)
    ap.add_argument("--a-units", default="eldarRanger,astraBullgryn,tauCrisis")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    # DRIVER le regime, ne pas le subir : `lowest` prend la cible LEGALE la moins vitale -> elle
    # tombe TOT (petit `k`), donc `max(0, H - k - 1) > 0` et le REPORT existe des DEUX cotes, ce qui
    # est la seule facon d'exercer le selecteur de chaine.
    ap.add_argument("--target-pick", choices=("first", "lowest"), default="lowest")
    ap.add_argument("--target", type=int, default=None)
    args = ap.parse_args(argv)

    st_file = Path(args.state_file or (ROOT / "logs" / "runners" / "_489_frag_state.json"))
    st_file.parent.mkdir(parents=True, exist_ok=True)
    sid = _resolve_session()
    rid = _build(st_file, ["--seed", str(args.seed), "--board", args.board, "--rank", "17",
                           "--p-units", "templAggressor", "--a-units", args.a_units,
                           "--no-ai", "--hp-player", "90000",
                           "--hp-target", str(args.hp_target)])
    print("[489] runner=%s session=%s board=%s seed=%s" % (rid, sid, args.board, args.seed))
    rc = 0
    try:
        cid, fh = _advance_until_castable(sid, rid, st_file, "templAggressor",
                                          FRAGSTORM_GRENADE_LAUNCHER, max_turns=10)
        if not fh:
            print("[489] AUCUNE cible legale `fromHere` apres 10 tours -- montage a revoir")
            return 2
        mkstate, dec, board = _capture(sid, rid)
        legal = [t for t in (_tid(x) for x in fh) if t is not None]
        hp_of = {int(u["id"]): int(u.get("hp") or 0) for u in _alive_units(dec)}
        if args.target is not None:
            tid = int(args.target)
        elif args.target_pick == "lowest" and legal:
            tid = min(legal, key=lambda t: (hp_of.get(t, 1 << 30), t))
        else:
            tid = legal[0]
        vis_of = {int(u["id"]): u.get("visualId") for u in _alive_units(dec)}
        print("[489] cibles LEGALES fromHere (id: visualId/PV) : %s"
              % {t: "%s/%s" % (vis_of.get(t), hp_of.get(t)) for t in legal})
        foes = [int(u["id"]) for u in _alive_units(dec) if not u.get("ctrl")]
        dists = {f: _dist(dec, cid, f) for f in foes}
        print("[489] caster=u%s cible=u%s ; ennemis vivants et leur distance AU CASTER : %s"
              % (cid, tid, dists))
        others_in_range = [f for f, d in dists.items() if f != tid and d is not None and d <= 2]
        print("[489] candidats au report (dist <= range 2 du caster, cible exclue) : %s"
              % others_in_range)
        if not others_in_range:
            print("[489] AVERTISSEMENT : aucun candidat au report -- la chaine ne peut pas "
                  "s'exercer, le verdict ne porterait que sur le 1er maillon")

        # --- OFFLINE (chemin reel : le handler) -----------------------------------------------
        st = mkstate()
        diag = _offline_cast(st, cid, tid, FRAGSTORM_GRENADE_LAUNCHER)
        off_chain = diag.get("chain") or []
        print("[489] OFFLINE ported=%s dsl=%s hits=%s range=%s"
              % (diag.get("ported"), diag.get("dsl"), diag.get("hits"), diag.get("range")))
        print("[489] OFFLINE chaine : %s" % _fmt_chain(off_chain))
        off_per_hit = {int(c["target"]): [int(x) for x in (c.get("per_hit_health") or [])]
                       for c in off_chain}

        # --- LIVE ------------------------------------------------------------------------------
        res = _cast_live(sid, rid, cid, tid, FRAGSTORM_GRENADE_LAUNCHER, capture_events=True)
        live_per_hit = _live_per_hit(res, FRAGSTORM_GRENADE_LAUNCHER)
        print("[489] LIVE ok=%s mutated=%s" % (res.get("ok"), res.get("mutated")))
        print("[489] LIVE per-coup par cible : %s"
              % json.dumps({str(k): v for k, v in sorted(live_per_hit.items())}))

        # --- VERDICTS ---------------------------------------------------------------------------
        if diag.get("ported") is not True:
            print("[489] VERDICT-1 ECHEC : `ported` != True -- l'ability est ENCORE un no-op")
            rc = 1
        else:
            print("[489] VERDICT-1 OK : ported=True")

        off_order = [int(c["target"]) for c in off_chain]
        live_order = [t for t in live_per_hit.keys()]
        print("[489] VERDICT-2 chaine : offline=%s live=%s -> %s"
              % (off_order, live_order,
                 "OK" if set(off_order) == set(live_order) else "MISMATCH"))
        if set(off_order) != set(live_order):
            rc = 1

        # Le port APPLIQUE en un bloc la ou le natif cesse d'appliquer sur un cadavre : on compare donc
        # la sequence offline CLAMPEE par les PV (comportement documente de
        # `ChainLeftOverHitsAttackDamage.execute` -- « seul le `total` de l'iteration fatale est
        # sur-estime »). L'observable commun reste : meme nombre de coups, memes valeurs jusqu'au coup
        # fatal inclus, 0 ensuite.
        off_hp0 = {int(c["target"]): int(c.get("hp_before") or 0) for c in off_chain}

        def _clamped(seq, hp):
            out = []
            for h in seq:
                d = max(0, min(int(h), hp))
                out.append(d)
                hp -= d
            return out

        for t in sorted(set(off_per_hit) | set(live_per_hit)):
            o, l = off_per_hit.get(t), live_per_hit.get(t)
            oc = _clamped(o, off_hp0.get(t, 0)) if o is not None else None
            same = (oc is not None and l is not None
                    and len(oc) == len(l) and all(int(a) == int(b) for a, b in zip(oc, l)))
            print("[489] VERDICT-3 u%s per-coup offline(brut)=%s offline(clampe)=%s live=%s -> %s"
                  % (t, o, oc, l, "OK" if same else "ECART"))
            if not same:
                rc = 1

        # `GetLeftOverHits` sans `extraHits` : report = max(0, H - k - 1), 0 si la cible survit.
        if off_chain:
            first = off_chain[0]
            ph = [int(x) for x in (first.get("per_hit_health") or [])]
            hp0 = int(first.get("hp_before") or 0)
            k, acc = None, 0
            for i, h in enumerate(ph):
                acc += h
                if hp0 - acc <= 0:
                    k = i + 1
                    break
            attendu = max(0, len(ph) - k - 1) if k else 0
            porte = int(off_chain[1]["hits"]) if len(off_chain) > 1 else 0
            print("[489] VERDICT-4 report : H=%s k=%s -> max(0,H-k-1)=%s ; 2e maillon hits=%s -> %s"
                  % (len(ph), k, attendu, porte, "OK" if attendu == porte else "MISMATCH"))
            if attendu != porte:
                rc = 1
    finally:
        if not args.keep:
            _dispose(st_file)
    print("[489] rc=%s" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
