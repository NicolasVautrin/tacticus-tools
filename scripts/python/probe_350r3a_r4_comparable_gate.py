#!/usr/bin/env python
"""#350-r3a-r4 -- LE TEMOIN : le plafond `maxRank` deplace la decision du tier COMPARABLE.

`#350-r3a-r3` a mesure le plafond sur la face NonComparable et l'a ferme
(`_PlanTargetPlaybook.eligible_positions`). Le tier COMPARABLE, lui, gatait encore sur `ranked`
brut -- et il couvre TOUTES les attaques, attaque normale comprise. Ce probe l'EXERCE.

CE QU'IL MESURE, sur UN etat et deux valeurs de `maxRank` :

  1. `legal` par la voie `ranked` brut (le regime de `master`, obtenu par MUTATION du foyer) ;
  2. `legal` par le foyer `engine.ai.cast_positions` (le regime livre) ;
  3. l'ACTION rendue par `ComparableAbilityGenerator.generate` dans chacun des deux regimes.

Le montage est celui de `probe_350r3a_r3_position_gate.py` (fixture `carte`), REUTILISE et non
recopie : meme geometrie, memes helpers, donc les deux probes parlent du meme etat.

Un ecart de POSITIONS sans ecart d'ACTION reste un resultat -- il dit que la geometrie de ce
montage ne discrimine pas, pas que le plafond est inoffensif (cf. `case-350r3` §9 : a `maxRank=8`
l'argmax coincidait PAR CHANCE).

DISCIPLINE : ASCII strict, board CHOISI, state-file absolu sous `logs/`, runner dispose en
`finally`. Usage, depuis `scripts/python` :

    python probe_350r3a_r4_comparable_gate.py
    python probe_350r3a_r4_comparable_gate.py --ranks 32,8,6
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_350r3a_r3_position_gate as P3                                  # noqa: E402
from engine.ai import cast_positions as CP                                  # noqa: E402

LOGS = PYDIR.parents[1] / "logs"


def _legal_par_voie(ctx, ability: int, brut: bool) -> dict:
    """`{targetId: positions}` -- exactement ce que `_best_attack` consomme."""
    out = {}
    for ev in ((ctx.plans.get(ctx.uid) or {}).get("evals") or []):
        if ev.get("abilityId") != int(ability) or not ev.get("rankCount"):
            continue
        if brut:
            pos = CP.ranked_positions(ev)
        else:
            pos = CP.positions_castables(ev, getattr(ctx, "cast_from_tiles", None),
                                         ctx.uid, ev.get("targetId"), ability, ctx.origin)
        out[int(ev.get("targetId"))] = pos
    return out


def _action(ctx, brut: bool):
    """L'action du tier COMPARABLE. `brut=True` MUTE le foyer pour rejouer le regime de `master` --
    c'est la contre-epreuve : sans elle, un vert ne prouverait pas que le fix s'exerce."""
    from engine.ai import action_generators as AG
    vrai = CP.positions_castables
    if brut:
        CP.positions_castables = (lambda ev, *a, **k: CP.ranked_positions(ev))
    try:
        return AG.ComparableAbilityGenerator().generate(ctx)
    finally:
        CP.positions_castables = vrai


def run(ranks: tuple, rings: tuple | None = None) -> int:
    _resolve_session, rpc = P3._rpc_mod()
    sid = _resolve_session()
    state = LOGS / ("st_350r3a_r4_comparable_%s.json"
                    % ("-".join(str(x) for x in rings) if rings else "def"))
    LOGS.mkdir(parents=True, exist_ok=True)
    rid = None
    try:
        fx = _fixture(rings)
        print("[350-r3a-r4] session %s -- fixture %s, rangs %s" % (sid, fx["name"], list(ranks)))
        rid = P3._build(state, fx)
        st = P3._stage(rpc, sid, rid, fx, verbose=True)
        if not st.get("ok"):
            print("MONTAGE KO : %s" % st.get("error"))
            return 1
        cid, ability = int(st["casterId"]), int(fx["ability"])
        from engine import weights as W
        from engine.ai import context as AICTX
        from engine.playbook import scene as _scene
        print("== montage : caster u%d, ability %d, board %s ==" % (cid, ability, fx.get("board")))
        lignes = []
        for mr in ranks:
            dv = P3._view(rpc, sid, rid, mr)
            rpc2 = (lambda m, b, t=60: P3._r(rpc, sid, m, b, t))
            mov = P3._r(rpc, sid, "aiMovableTiles", {"runnerId": rid}, 60)
            mov_by_unit = {u.get("unitId"): u for u in ((mov or {}).get("units") or [])}
            ctx = AICTX.build(rpc2, rid, dv, mov_by_unit, cid, W.load(),
                              _scene.build_predictor(rpc2, rid))
            brut = _legal_par_voie(ctx, ability, brut=True)
            foyer = _legal_par_voie(ctx, ability, brut=False)
            gagnees = sum(len(foyer.get(t, set()) - brut.get(t, set())) for t in brut)
            perdues = sum(len(brut.get(t, set()) - foyer.get(t, set())) for t in brut)
            a_brut = _action(ctx, brut=True)
            a_foyer = _action(ctx, brut=False)
            meme = (a_brut or {}).get("to") == (a_foyer or {}).get("to") and \
                   (a_brut or {}).get("target") == (a_foyer or {}).get("target")
            lignes.append((mr, {t: len(v) for t, v in brut.items()},
                           {t: len(v) for t, v in foyer.items()}, gagnees, perdues,
                           a_brut, a_foyer, meme))
            print("maxRank=%-3d legal(ranked)=%s legal(foyer)=%s  POSITIONS GAGNEES=%d perdues=%d"
                  % (mr, {t: len(v) for t, v in brut.items()},
                     {t: len(v) for t, v in foyer.items()}, gagnees, perdues))
            print("            action(ranked brut) = %s" % _fmt(a_brut))
            print("            action(foyer)       = %s   -> %s"
                  % (_fmt(a_foyer), "IDENTIQUE" if meme else "**DIFFERENTE**"))
        print("")
        print("compteurs du foyer : %s" % CP.COMPTEURS)
        discriminant = any(l[3] > 0 for l in lignes)
        decisif = any(not l[7] for l in lignes)
        print("VERDICT : positions recuperees sur au moins un rang = %s ; "
              "action DEPLACEE = %s" % (discriminant, decisif))
        if not discriminant:
            print("  (montage NON DISCRIMINANT : aucun rang ne tronque ici -- ce n'est pas un vert)")
        return 0
    finally:
        if rid is not None:
            try:
                P3._r(rpc, sid, "disposeRunner", {"runnerId": rid}, 60)
            except Exception:                                       # noqa: BLE001
                pass


def _fmt(a) -> str:
    if not a:
        return "None"
    return "{target=%s ability=%s to=%s util=%s}" % (a.get("target"), a.get("ability"),
                                                     a.get("to"), a.get("util"))


def _fixture(rings: tuple | None = None) -> dict:
    """La fixture `carte` de `#350-r3a-r3`, LUE CHEZ ELLE -- jamais recopiee : les deux probes
    doivent parler du meme etat, sinon leurs chiffres ne se confrontent pas."""
    t = getattr(P3, "_FIXTURES", None)
    if not isinstance(t, dict) or "carte" not in t:
        raise RuntimeError("fixture `carte` introuvable dans probe_350r3a_r3_position_gate")
    fx = dict(t["carte"])
    fx["name"] = "r4_comparable"
    if rings:
        # PILOTER la geometrie, jamais la subir : le regime de troncature exige plus de tuiles
        # valides que `maxRank`, et le DEPLACEMENT d'argmax exige en plus que la meilleure
        # position soit HORS des premiers rangs (classes par utilite de MOUVEMENT).
        fx["rings"] = dict(zip(("necroWarden", "ultraTitus"), rings))
        fx["name"] = "r4_comparable_r%s" % "-".join(str(x) for x in rings)
        fx["seed"] = int(fx["seed"]) + sum(rings) * 7
    return fx


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ranks", default="32,6", help="valeurs de maxRank a balayer")
    ap.add_argument("--rings", default=None,
                    help="anneaux des deux ennemis, ex. '1,5' -- PILOTE la geometrie")
    a = ap.parse_args()
    rings = tuple(int(x) for x in a.rings.split(",")) if a.rings else None
    return run(tuple(int(x) for x in a.ranks.split(",") if x.strip()), rings)


if __name__ == "__main__":
    sys.exit(main())
