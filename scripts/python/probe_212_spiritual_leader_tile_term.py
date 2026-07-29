#!/usr/bin/env python
"""probe_212 -- DECOMPOSITION PAR ETAGE du terme de `SpiritualLeaderPlaybook` (1275), contre le natif.

QUESTION BINAIRE : le terme que le port met dans son `Tile(7)` pour l'ability 1275 est-il, TUILE PAR
TUILE, celui du natif -- et si non, a quel ETAGE ca diverge ?

Meme squelette de mesure que `probe_193c_move_playbook_terms.py` (dont il REUTILISE la machinerie :
build, marche jusqu'au pas discriminant, hooks EXISTANTS de `scorer-damage-trace` armes pour UN SEUL
`aiStepDryRun` puis desarmes -- AUCUNE reinjection), mais il ne s'arrete pas au scalaire :

    X_natif(tuile) = Tile(7) - Elevation - TileEffects
    X_port (tuile) = somme des feuilles du port, MEME retranchement
    ... et il OUVRE les deux cotes : chaque feuille NON NULLE du port est affichee par son nom, avec
    a cote le VOISINAGE qualifiant (amis a distance 1 portant le trait `Decoy`) et l'OCCUPANT de la
    tuile candidate. C'est ce qui permet d'attribuer un residu a une feuille plutot qu'a un facteur.

Sortie : une ligne par tuile + un recapitulatif `n_decoys -> {X_nat}` qui repond directement a la
question du CAP (`vtbl+0x228` du corps commun `AdjacentUnitPreferenceTriggeredAbilityPlaybook.
u003CCalculateMovementUtilityInStepsInternalu003Ed__1u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext` :
`n1 = Min(count(filtre vtbl+0x248), cap vtbl+0x238)`) : si `X_nat` est le meme pour 1, 2 et 3 decoys
adjacents, le cap MORD, et un port qui somme `30 x n` est faux.

Usage (ASCII only, depuis scripts/python) :
  python probe_212_spiritual_leader_tile_term.py --board MC1_67 --seed 777 --max-steps 60 --extra \
      --hp-target 100000 --hp-player 100000 \
      --p-units "genesMagus,genesPrimus,genesKelermorph,orksNob,spaceWulfen" \
      --a-units "darkaHellblaster,eldarRanger,worldKharn,templChampion,tauMarksman"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rl_collect_batch import _resolve_session                      # noqa: E402
from probe_193c_move_playbook_terms import (_r, _build, _apply_native, _visual_map, _by_tile,  # noqa: E402
                                            _one, _port_leaves, BUILD_HASH)

ABILITY = 1275                      # TriggeredAbilityType.SpiritualLeader
CARRIER = "genesMagus"              # HERO du pool ; seul passif = SpiritualLeader (gameconfig)
DECOY_TRAIT = "Decoy"               # UnitTrait.Decoy = 0x41d = 1053


def _leaf_names():
    """`UTILITY_TYPE` -> nom de classe, pour nommer les feuilles du composite Tile(7) du port."""
    from engine.utilities.tile import TILE_UTILITY
    return {int(c.UTILITY_TYPE): type(c).__name__ for c in TILE_UTILITY.children}


def _decoys_adjacent(leaf_ctx, tile):
    import hexgeo
    return [u for u in (leaf_ctx.get("friend_units") or ())
            if hexgeo.distance(tile, u["pos"]) == 1 and DECOY_TRAIT in (u.get("traits") or ())]


def run(sid, rid, max_steps, max_arm=6):
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene
    from engine.playbook.adjacent_unit_preference import load_playbook

    pb = load_playbook(ABILITY)
    if pb is None:
        print("!! ability %d absente de TRIGGERED_MOVE_PLAYBOOKS -- rien a confronter" % ABILITY)
        return 1
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
        if vmap.get(uid) == CARRIER:
            seen += 1
            dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
            mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
            mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
            wt0 = W.load()
            pred0 = _scene.build_predictor(lambda m, b, t: _r(sid, m, b, t), rid)
            ctx = _ai_ctx.build(lambda m, b, t: _r(sid, m, b, t), rid, dv, mov_by_unit, uid, wt0, pred0)
            counts = {len(_decoys_adjacent(_port_leaves(ctx, t)[1], t)) for t in (ctx.action_tiles or [])}
            print("pas %-3d activation #%d de %s (u%s) : #decoys adjacents sur les candidates = %s"
                  % (step, seen, CARRIER, uid, sorted(counts)))
            if len(counts) > 1 and armed < max_arm:
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
                hc = {len(_decoys_adjacent(_port_leaves(ctx, t)[1], t))
                      for t in (ctx.action_tiles or []) if t in hooked}
                print("        tuiles HOOKEES=%d, #decoys sur ces tuiles = %s" % (len(hooked), sorted(hc)))
                if len(hc) > 1:
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
    msgs = (dry.get("action") or {}).get("messages") or []
    nat_move = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)
    nat_tile = (nat_move["to"]["col"], nat_move["to"]["row"]) if nat_move else origin

    tt = _by_tile(tterm.get("entries") or [], "casterCol", "casterRow", "tileTerm")
    el = _by_tile(elev.get("entries") or [], "col", "row", "leaf")
    te = _by_tile([e for e in (leaf.get("entries") or []) if e.get("leaf") == "TileEffects"],
                  "col", "row", "value")
    if not tt:
        print("!! AUCUN event tileTerm -- pas de tier Comparable a ce pas")
        return 1
    occupant = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        if u.get("alive") and p.get("col") is not None:
            occupant[(p["col"], p["row"])] = "%s%s" % (u.get("visualId"), "" if u.get("ctrl") else "(E)")

    wt = ctx.wt
    tiles = [t for t in (ctx.action_tiles or []) if t in tt]
    print("\n===== u%s (%s) origin=%s natif joue %s =====" % (uid, (me or {}).get("visualId"),
                                                              origin, nat_tile))
    print("\n  tuile      X_nat  X_port  DELTA  terme_pb  nDecoy  occupant           feuilles NON NULLES du port")
    by_n, by_delta = {}, {}
    for t in tiles:
        vt, ve, vf = _one(tt, t), _one(el, t), _one(te, t, 0.0)
        leaves, leaf_ctx = _port_leaves(ctx, t)
        p_x = sum(leaves.values()) - leaves.get(8, 0.0) - leaves.get(9, 0.0)
        term = pb.calculate_movement_utility_in_steps(t, leaf_ctx, wt)
        n = len(_decoys_adjacent(leaf_ctx, t))
        x = (vt - ve - vf) if None not in (vt, ve, vf) else None
        d = (x - p_x) if x is not None else None
        nz = ", ".join("%s=%g" % (names.get(k, k), v) for k, v in sorted(leaves.items())
                       if abs(v) > 1e-9 and k not in (8, 9))
        occ = occupant.get(t, "-")
        print("  %-10s %-6s %-7.4g %-6s %-9.4g %-7d %-18s %s"
              % (t, x, p_x, ("%.4g" % d) if d is not None else "?", term, n, occ, nz or "-"))
        if x is not None:
            by_n.setdefault(n, set()).add(round(x, 4))
            by_delta.setdefault(("decoy" if occ.startswith("genesSmnDecoy") else "autre"),
                                set()).add(round(d, 4))

    print("\n  RECAP 1  #decoys adjacents -> {X_nat observes}")
    for n in sorted(by_n):
        print("    n=%d -> %s" % (n, sorted(by_n[n])))
    print("  (X_nat qui ne CROIT PAS avec n => le cap `vtbl+0x228` mord : le terme est borne.)")
    print("\n  RECAP 2  occupant de la tuile candidate -> {DELTA = X_nat - X_port}")
    for k in sorted(by_delta):
        print("    occupant=%-6s -> %s" % (k, sorted(by_delta[k])))
    print("  (DELTA=0 hors tuiles occupees par un decoy => le TERME 1275 est exact ; le residu")
    print("   constant sur les tuiles a occupant decoy est une AUTRE feuille, non portee.)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--max-steps", type=int, default=60)
    ap.add_argument("--extra", nargs=argparse.REMAINDER, default=[])
    a = ap.parse_args()
    games = Path("C:/Users/nicolasv/AppData/Local/tacticus/games")
    hashes = [p.name for p in games.iterdir()] if games.exists() else []
    if BUILD_HASH not in hashes:
        print("REFUS : hooks RVA valides pour %s, builds presents = %s" % (BUILD_HASH, hashes))
        return 2
    sid = _resolve_session()
    if a.runner is not None:
        return run(sid, a.runner, a.max_steps)
    rid, state = _build(a.seed, a.board, a.extra)
    if rid is None:
        return 1
    print("runner %d seed=%s board=%s carrier=%s" % (rid, a.seed, a.board, CARRIER))
    try:
        return run(sid, rid, a.max_steps)
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        try:
            state.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
