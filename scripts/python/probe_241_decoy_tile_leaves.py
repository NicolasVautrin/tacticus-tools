#!/usr/bin/env python
"""probe_241 -- CONFRONTATION par TUILE des deux feuilles a OCCUPANT STEPPABLE, contre le NATIF.

QUESTION BINAIRE : sur une tuile candidate occupee par un summon steppable, le port met-il dans son
`Tile(7)` exactement ce que le natif y met -- et notamment les DEUX termes de #241 :
`SteppableUnitUtility`(19) et `AttractToDecoysUtility`(64) ?

Meme squelette de mesure que `probe_212_spiritual_leader_tile_term.py` (dont il REUTILISE la
machinerie de `probe_193c` : build, marche NATIVE, hooks EXISTANTS de `scorer-damage-trace` armes
pour UN SEUL `aiStepDryRun` puis desarmes -- AUCUNE reinjection) :

    X_nat (tuile) = Tile(7) - Elevation - TileEffects        (scorerTileTermTrace / Elev / Leaf)
    X_port(tuile) = somme des feuilles du port, MEME retranchement

CE QU'IL AJOUTE a probe_212 : le CARRIER est parametrable, et le pas discriminant est cherche sur
« au moins une candidate porte un occupant steppable » au lieu de « le terme du playbook 1275 varie ».
Cela permet d'exercer les deux faits RE que le montage de #212 ne peut PAS exercer, parce que son
mover (`genesMagus`) ne porte pas `DecoysAndMisdirection` :

  * SELF-COUNT -- la boucle native de
    `IdunBattle.AI.Utilities.AttractToDecoysUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext`
    n'exclut PAS `case.unit` (`IsFriend(u, case.unit)` est vrai pour u == case.unit). Avec
    `--carrier genesPrimus` (LE porteur de 1304), le mover compte pour lui-meme : le terme doit valoir
    75 x (1 + autres porteurs). Un port qui excluerait self rendrait 75 de moins.
  * PAS DE FILTRE DE POSITION -- la boucle part de `GetAllAliveUnits` (slot 0x88). Le probe imprime
    la distance hex entre chaque porteur de 1304 et la tuile evaluee : si elle depasse 1 (ou 2) et
    que `X_nat` inclut quand meme le terme, aucun voisinage ne peut expliquer la mesure.

Usage (ASCII only, depuis scripts/python) :
  python probe_241_decoy_tile_leaves.py --board MC1_67 --seed 777 --carrier genesPrimus \\
      --max-steps 60 --extra --hp-target 100000 --hp-player 100000 \\
      --p-units "genesMagus,genesPrimus,genesKelermorph,orksNob,spaceWulfen" \\
      --a-units "darkaHellblaster,eldarRanger,worldKharn,templChampion,tauMarksman"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_pin import BuildPinRefused                             # noqa: E402
from rl_collect_batch import _resolve_session                      # noqa: E402
from probe_193c_move_playbook_terms import (_r, _build, _apply_native, _visual_map, _by_tile,  # noqa: E402
                                            _one, _port_leaves, _exiger_build_des_rva)

ATTRACT_ABILITY = 1304              # TriggeredAbilityType.DecoysAndMisdirection
STEPPABLE_TRAIT = "Steppable"       # UnitTrait.Steppable = 0x1b = 27
DECOY_TRAIT = "Decoy"               # UnitTrait.Decoy    = 0x41d = 1053


def _leaf_names():
    from engine.utilities.tile import TILE_UTILITY
    return {int(c.UTILITY_TYPE): type(c).__name__ for c in TILE_UTILITY.children}


def _carriers_1304(leaf_ctx):
    """Porteurs de 1304 vus par le port : le MOVER (self) + les amis. `(etiquette, pos|None)`."""
    out = []
    if ATTRACT_ABILITY in (leaf_ctx.get("unit_triggered_abilities") or ()):
        out.append(("SELF", leaf_ctx.get("self_pos")))
    for u in (leaf_ctx.get("friend_units") or ()):
        if ATTRACT_ABILITY in (u.get("triggered") or ()):
            out.append((str(u.get("vis")), u.get("pos")))
    return out


def _steppable_tiles(leaf_ctx):
    """{pos: etiquette} des occupants STEPPABLES vus par le port (amis et ennemis)."""
    out = {}
    for units, side in ((leaf_ctx.get("friend_units") or (), "ami"),
                        (leaf_ctx.get("enemy_units") or (), "ennemi")):
        for u in units:
            tr = u.get("traits") or ()
            if STEPPABLE_TRAIT in tr:
                out[u.get("pos")] = "%s %s%s" % (side, u.get("vis"),
                                                 "/Decoy" if DECOY_TRAIT in tr else "")
    return out


def run(sid, rid, carrier, max_steps, max_arm=6):
    import hexgeo
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene

    names = _leaf_names()
    vmap = _visual_map(sid, rid)
    step, seen, armed = 0, 0, 0
    dv = ctx = tterm = elev = leaf = None
    while True:
        dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            print("trajectoire native epuisee au pas %d (%s)" % (step, dry.get("error")))
            return 1
        uid = dry.get("activatedUnitId")
        if vmap.get(uid) == carrier:
            seen += 1
            dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
            mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
            mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
            wt0 = W.load()
            pred0 = _scene.build_predictor(lambda m, b, t: _r(sid, m, b, t), rid)
            ctx = _ai_ctx.build(lambda m, b, t: _r(sid, m, b, t), rid, dv, mov_by_unit, uid, wt0, pred0)
            lc = _port_leaves(ctx, (ctx.action_tiles or [(0, 0)])[0])[1]
            occ = _steppable_tiles(lc)
            hit = [t for t in (ctx.action_tiles or []) if t in occ]
            print("pas %-3d activation #%d de %s (u%s) : candidates a occupant steppable = %s ; "
                  "porteurs 1304 = %s" % (step, seen, carrier, uid, hit, _carriers_1304(lc)))
            if hit and armed < max_arm:
                armed += 1
                _r(sid, "scorerDamageTraceOn", {}, 90)
                _r(sid, "scorerDamageTraceClear", {"runnerId": rid, "stacks": 0}, 60)
                try:
                    dry = _r(sid, "aiStepDryRun", {"runnerId": rid}, 90)
                    tterm = _r(sid, "scorerTileTermTraceDump", {"runnerId": rid, "max": 4000}, 90)
                    elev = _r(sid, "scorerElevTraceDump", {"runnerId": rid, "max": 4000}, 90)
                    leaf = _r(sid, "scorerLeafTraceDump", {"runnerId": rid, "max": 4000}, 90)
                finally:
                    _r(sid, "scorerDamageTraceOff", {}, 60)
                hooked = {(e.get("casterCol"), e.get("casterRow"))
                          for e in (tterm.get("entries") or []) if (e.get("casterCol") or -1) >= 0}
                hh = [t for t in hit if t in hooked]
                print("        tuiles HOOKEES=%d, dont a occupant steppable = %s" % (len(hooked), hh))
                if hh:
                    break
        if step >= max_steps:
            print("aucun pas DISCRIMINANT en %d pas (%d activations, %d armements)"
                  % (max_steps, seen, armed))
            return 1
        _apply_native(sid, rid, dry)
        step += 1

    uid = dry.get("activatedUnitId")
    me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
    mpos = ((me or {}).get("pos") or {})
    origin = (mpos.get("col"), mpos.get("row")) if mpos.get("col") is not None else None

    tt = _by_tile(tterm.get("entries") or [], "casterCol", "casterRow", "tileTerm")
    el = _by_tile(elev.get("entries") or [], "col", "row", "leaf")
    te = _by_tile([e for e in (leaf.get("entries") or []) if e.get("leaf") == "TileEffects"],
                  "col", "row", "value")
    if not tt:
        print("!! AUCUN event tileTerm -- pas de tier Comparable a ce pas")
        return 1

    wt = ctx.wt
    tiles = [t for t in (ctx.action_tiles or []) if t in tt]
    lc0 = _port_leaves(ctx, tiles[0])[1]
    occ = _steppable_tiles(lc0)
    carr = _carriers_1304(lc0)
    print("\n===== u%s (%s) origin=%s =====" % (uid, (me or {}).get("visualId"), origin))
    print("  porteurs de 1304 (self inclus) : %s" % (carr,))
    print("\n  tuile      X_nat  X_port  DELTA  occupant steppable        d(porteurs 1304)  "
          "feuilles NON NULLES du port")
    bad, seen_occ = 0, 0
    for t in tiles:
        vt, ve, vf = _one(tt, t), _one(el, t), _one(te, t, 0.0)
        leaves, leaf_ctx = _port_leaves(ctx, t)
        p_x = sum(leaves.values()) - leaves.get(8, 0.0) - leaves.get(9, 0.0)
        x = (vt - ve - vf) if None not in (vt, ve, vf) else None
        d = (x - p_x) if x is not None else None
        if d is not None and abs(d) > 1e-6:
            bad += 1
        if t in occ:
            seen_occ += 1
        dists = [hexgeo.distance(t, p) if p else -1 for _, p in carr]
        nz = ", ".join("%s=%g" % (names.get(k, k), v) for k, v in sorted(leaves.items())
                       if abs(v) > 1e-9 and k not in (8, 9))
        print("  %-10s %-6s %-7.4g %-6s %-25s %-17s %s"
              % (t, x, p_x, ("%.4g" % d) if d is not None else "?", occ.get(t, "-"), dists, nz or "-"))

    print("\n  tuiles a occupant steppable exercees : %d" % seen_occ)
    print("  ==> tuiles en DESACCORD X_nat vs X_port : %d / %d" % (bad, len(tiles)))
    if seen_occ == 0:
        print("  !! aucune tuile a occupant steppable HOOKEE -- la mesure ne dit rien de #241")
    return 0 if (bad == 0 and seen_occ > 0) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--carrier", default="genesPrimus")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--max-steps", type=int, default=60)
    ap.add_argument("--extra", nargs=argparse.REMAINDER, default=[])
    a = ap.parse_args()
    try:
        _exiger_build_des_rva()            # #431 : le pin des RVA du hook passe par `build_pin`
    except BuildPinRefused as exc:
        print(str(exc))
        return 2
    sid = _resolve_session()
    if a.runner is not None:
        return run(sid, a.runner, a.carrier, a.max_steps)
    rid, state = _build(a.seed, a.board, a.extra)
    if rid is None:
        return 1
    print("runner %d seed=%s board=%s carrier=%s" % (rid, a.seed, a.board, a.carrier))
    try:
        return run(sid, rid, a.carrier, a.max_steps)
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        try:
            state.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
