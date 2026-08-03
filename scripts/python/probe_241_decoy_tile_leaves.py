#!/usr/bin/env python
"""probe_241 -- CONFRONTATION par TUILE des deux feuilles a OCCUPANT STEPPABLE, contre le NATIF.

QUESTION BINAIRE (posee AVANT la methode, en trois volets qui se mesurent separement) :

  A. REGIME -- le montage realise-t-il la condition que la mesure EXIGE ? Il faut au moins une
     candidate HOOKEE occupee par un summon steppable AMI (sinon les deux feuilles ne tirent nulle
     part) ET au moins une SANS occupant (sinon une pose TROP LARGE ne se verrait pas).
  B. ACCORD -- sur ces tuiles, `X_nat == X_port` ? C'est le coeur : les deux termes de #241 sont
     `SteppableUnitUtility` (`UtilityType.SteppableUnit`) et `AttractToDecoysUtility`
     (`UtilityType.DecoysAndMisdirection_AttractToDecoys`).
  C. PAS DE FILTRE DE POSITION -- la boucle de comptage de
     `IdunBattle.AI.Utilities.AttractToDecoysUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext`
     part de `GetAllAliveUnits` (slot 0x88), SANS filtre de distance. Le probe l'exerce en exigeant
     que les tuiles a occupant steppable soient a des distances DIFFERENTES des porteurs de 1304 et
     que la contribution des deux feuilles y soit CONSTANTE. Aucun voisinage R1/R2 ne produit ca.

Le SELF-COUNT (`IsFriend(u, case.unit)` est vrai pour `u == case.unit` : le mover se compte
lui-meme) est exerce en prenant `--carrier genesPrimus`, LE porteur de 1304 du roster : un port qui
excluait self rendrait 75 de moins, ce que le volet B verrait.

Decomposition par etage, sur les hooks EXISTANTS de `scorer-damage-trace` armes pour UN SEUL
`aiStepDryRun` puis desarmes -- AUCUNE reinjection :

    X_nat (tuile) = Tile(7) - Elevation - TileEffects       (scorerTileTermTrace / Elev / Leaf)
    X_port(tuile) = `x_port(feuilles du port)`, MEME retranchement (foyer unique #193c)

MONTAGE -- ON PILOTE LES POSITIONS. `_drive_carrier_toward` (de `probe_212_spiritual_leader_tile_
term.py`, meme patron que `_drive_cluster` de #242) rapproche le carrier d'un decoy pose par
`genesMagus`, en EVITANT de le fouler (un move DESSUS le crushe). Sans ce forcage le regime n'est
atteint que par la DUREE de la trajectoire native -- un echantillon SUBI. Mesure du 2026-08-03 sans
drive sur `MC1_67`/777 : regime atteint au pas 22, mais le verdict etait FAUX (3 tuiles rendues en
desaccord, de valeur exactement `-TileEffects`, parce que le retranchement de `X_port` etait perime).

Usage (ASCII only, depuis scripts/python) :
  python probe_241_decoy_tile_leaves.py --board MC1_67 --seed 777 --carrier genesPrimus --extra \\
      --hp-target 100000 --hp-player 100000 \\
      --p-units "genesMagus,genesPrimus,genesKelermorph,orksNob,spaceWulfen" \\
      --a-units "darkaHellblaster,eldarRanger,worldKharn,templChampion,tauMarksman"
  python probe_241_decoy_tile_leaves.py --no-drive ...      # regime SUBI (contre-epreuve)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hexgeo                                                     # noqa: E402
from build_pin import BuildPinRefused                             # noqa: E402
from rl_collect_batch import _resolve_session                      # noqa: E402
from probe_193c_move_playbook_terms import (_r, _build, _by_tile, _one, _port_leaves,  # noqa: E402
                                            _exiger_build_des_rva, x_port, x_excluded)
from probe_212_spiritual_leader_tile_term import walk_driven, carrier_id_of  # noqa: E402

ATTRACT_ABILITY = 1304              # TriggeredAbilityType.DecoysAndMisdirection
STEPPABLE_TRAIT = "Steppable"       # UnitTrait.Steppable = 0x1b = 27
DECOY_TRAIT = "Decoy"               # UnitTrait.Decoy    = 0x41d = 1053


def _leaf_ids():
    """Les deux feuilles de #241, par MEMBRE `UtilityType` -- jamais par un litteral (#254)."""
    from engine.utilities.utility_type import UtilityType
    return int(UtilityType.SteppableUnit), int(UtilityType.DecoysAndMisdirection_AttractToDecoys)


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
    """{pos: (etiquette, est_ennemi)} des occupants STEPPABLES vus par le port (amis et ennemis)."""
    out = {}
    for units, side, is_enemy in ((leaf_ctx.get("friend_units") or (), "ami", False),
                                  (leaf_ctx.get("enemy_units") or (), "ennemi", True)):
        for u in units:
            tr = u.get("traits") or ()
            if STEPPABLE_TRAIT in tr:
                out[tuple(u.get("pos"))] = ("%s %s%s" % (side, u.get("vis"),
                                                         "/Decoy" if DECOY_TRAIT in tr else ""),
                                            is_enemy)
    return out


def _dist_profiles(occ, tiles, carr):
    """{tuile a occupant steppable AMI: profil de distances aux porteurs de 1304}.

    Le profil, et non la seule distance : `X_nat` doit etre le MEME sur des tuiles de profils
    DIFFERENTS pour que le volet C conclue (`GetAllAliveUnits` n'a aucun filtre de position)."""
    out = {}
    for t in tiles:
        if t in occ and not occ[t][1]:
            out[t] = tuple(sorted({hexgeo.distance(t, p) if p else -1 for _, p in carr}))
    return out


def wants_241(ctx, lc) -> bool:
    """Le regime que #241 exige, evalue sur les candidates d'un pas (predicat de `walk_driven`) :

      * au moins une tuile a occupant steppable AMI -- sans elle les deux feuilles ne tirent nulle
        part ;
      * au moins une tuile SANS occupant -- sans elle, une pose TROP LARGE rendrait la meme chose
        (c'est la contre-epreuve de #241 §4.4) ;
      * au moins DEUX profils de distance aux porteurs de 1304 parmi les premieres -- sans quoi le
        volet C ne conclut rien : un filtre de voisinage rendrait exactement la meme mesure.
    """
    tiles = ctx.action_tiles or []
    occ = _steppable_tiles(lc)
    if not any(t not in occ for t in tiles):
        return False
    prof = _dist_profiles(occ, tiles, _carriers_1304(lc))
    return len(prof) >= 1 and len(set(prof.values())) >= 2


def goals_241(ctx, lc, decoys):
    """Les tuiles que le drive de #241 vise : celles d'ou les decoys se voient a des DISTANCES
    VARIEES, tout en restant a portee.

    Viser « adjacent a un decoy » ne suffit PAS -- mesure du 2026-08-03 : le carrier se posait au
    contact d'un cluster serre, les deux candidates a occupant tombaient a la MEME distance de lui,
    et le volet C rendait « NON EXERCE ». On score donc une destination par le nombre de distances
    DISTINCTES auxquelles elle place les decoys accessibles, puis par leur nombre.
    `_drive_carrier_toward` prend le premier de la liste qu'il peut atteindre, d'ou le tri."""
    self_pos = lc.get("self_pos")
    reach = max((hexgeo.distance(self_pos, t) for t in (ctx.action_tiles or []) if self_pos),
                default=3) or 3               # rayon EFFECTIF du carrier, lu sur ses candidates
    bloque = set(decoys)
    score = {}
    for d in decoys:
        for t in hexgeo.neighbors(d[0], d[1]):
            if t in bloque:
                continue                       # fouler un decoy le CRUSHE : on ne s'y pose pas
            vus = [o for o in decoys if 1 <= hexgeo.distance(t, o) <= reach]
            score[t] = (len({hexgeo.distance(t, o) for o in vus}), len(vus))
    return [t for t, _ in sorted(score.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))]


def run(sid, rid, carrier, max_steps, drive=True, max_arm=6):
    from engine import weights as W

    names = _leaf_names()
    id19, id64 = _leaf_ids()
    call = lambda m, b, t=90: _r(sid, m, b, t)                          # noqa: E731
    carrier_id = carrier_id_of(call, rid, carrier)
    if carrier_id is None:
        print("!! %s absent du runner -- roster/pool a re-etalonner" % carrier)
        return 2
    armed = 0
    for st in walk_driven(call, rid, carrier_id, wants_241, goals_241, max_steps, drive):
        occ = _steppable_tiles(st["lc"])
        hit = [t for t in (st["ctx"].action_tiles or []) if t in occ]
        print("pas %-3d activation #%d de %s (u%s) : REGIME realise -- candidates a occupant "
              "steppable = %s ; porteurs 1304 = %s ; %d decoy(s) allie(s)"
              % (st["step"], st["seen"], carrier, st["uid"], hit, _carriers_1304(st["lc"]),
                 len(st["decoys"])))
        if armed >= max_arm:
            break
        armed += 1
        got = _measure(sid, rid, st["ctx"], st["dv"], st["uid"], names, W.load(), occ, id19, id64)
        if got is not None and got["ami"] and got["sans"] and len(got["by_d"]) >= 2:
            return _verdict(got)
        print("        (regime non realise sur les tuiles HOOKEES -- on continue)")
    print("\n  A. ECHANTILLON NON CONFRONTABLE -- aucun pas ou les tuiles HOOKEES realisent le "
          "regime en %d pas (%d armement(s))" % (max_steps, armed))
    return 2


def _measure(sid, rid, ctx, dv, uid, names, wt, occ, id19, id64):
    """Arme les hooks pour UN dry-run, puis rend la table par tuile. Desarmement garanti."""
    _r(sid, "scorerDamageTraceOn", {}, 90)
    _r(sid, "scorerDamageTraceClear", {"runnerId": rid, "stacks": 0}, 60)
    try:
        _r(sid, "aiStepDryRun", {"runnerId": rid}, 90)
        tterm = _r(sid, "scorerTileTermTraceDump", {"runnerId": rid, "max": 4000}, 90)
        elev = _r(sid, "scorerElevTraceDump", {"runnerId": rid, "max": 4000}, 90)
        leaf = _r(sid, "scorerLeafTraceDump", {"runnerId": rid, "max": 4000}, 90)
    finally:
        _r(sid, "scorerDamageTraceOff", {}, 60)

    tt = _by_tile(tterm.get("entries") or [], "casterCol", "casterRow", "tileTerm")
    el = _by_tile(elev.get("entries") or [], "col", "row", "leaf")
    te = _by_tile([e for e in (leaf.get("entries") or []) if e.get("leaf") == "TileEffects"],
                  "col", "row", "value")
    if not tt:
        return None

    me = next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)
    mpos = ((me or {}).get("pos") or {})
    origin = (mpos.get("col"), mpos.get("row")) if mpos.get("col") is not None else None

    tiles = [t for t in (ctx.action_tiles or []) if t in tt]
    lc0 = _port_leaves(ctx, tiles[0])[1] if tiles else {}
    carr = _carriers_1304(lc0)
    print("\n===== u%s (%s) origin=%s ; %d tuiles hookees ====="
          % (uid, (me or {}).get("visualId"), origin, len(tiles)))
    print("  porteurs de 1304 (self inclus) : %s" % (carr,))
    print("\n  tuile      X_nat  X_port  DELTA  f19+f64  occupant steppable        d(porteurs 1304) "
          " feuilles NON NULLES du port")
    bad, rows, ami, sans, by_d = [], 0, {}, [], {}
    for t in tiles:
        vt, ve, vf = _one(tt, t), _one(el, t), _one(te, t, 0.0)
        leaves, leaf_ctx = _port_leaves(ctx, t)
        p_x = x_port(leaves)                     # foyer UNIQUE du retranchement (#254, cf. `x_port`)
        two = leaves.get(id19, 0.0) + leaves.get(id64, 0.0)
        x = (vt - ve - vf) if None not in (vt, ve, vf) else None
        d = (x - p_x) if x is not None else None
        dists = [hexgeo.distance(t, p) if p else -1 for _, p in carr]
        nz = ", ".join("%s=%g" % (names.get(k, k), v) for k, v in sorted(leaves.items())
                       if abs(v) > 1e-9 and k not in x_excluded())
        print("  %-10s %-6s %-7.4g %-6s %-8.4g %-25s %-16s %s"
              % (t, x, p_x, ("%.4g" % d) if d is not None else "?", two,
                 (occ.get(t) or ("-", False))[0], dists, nz or "-"))
        if x is None:
            continue
        rows += 1
        if abs(d) > 1e-6:
            bad.append((t, round(d, 4)))
        if t in occ and not occ[t][1]:
            # Volet C : `X_nat` PURGE des feuilles autres que 19/64 -- ce que le natif met sur la
            # tuile au titre des deux feuilles de #241, sans supposer le port sur ces deux-la.
            ami[t] = round(x - (p_x - two), 4)
            by_d.setdefault(tuple(sorted(set(dists))), []).append(t)
        elif t not in occ:
            sans.append(t)
    return {"tiles": len(tiles), "rows": rows, "bad": bad, "ami": ami, "sans": sans,
            "by_d": by_d, "carriers": carr}


def _verdict(got) -> int:
    """rc 0 seulement si les TROIS volets concluent, sur un echantillon qui les exerce."""
    rc = 0
    if not got["ami"] or not got["sans"]:
        print("\n  A. ECHANTILLON NON CONFRONTABLE -- %d tuile(s) HOOKEE(s) a occupant steppable "
              "ami, %d sans occupant ; il en faut des DEUX (le DRIVE a-t-il echoue ?)"
              % (len(got["ami"]), len(got["sans"])))
        return 2
    print("\n  A. REGIME : OK -- %d tuile(s) a occupant steppable ami, %d sans occupant."
          % (len(got["ami"]), len(got["sans"])))
    if got["bad"]:
        print("  B. ACCORD : ECHEC -- %d/%d tuiles en desaccord `X_nat != X_port` (tuile, DELTA) : %r"
              % (len(got["bad"]), got["rows"], got["bad"]))
        rc |= 1
    else:
        print("  B. ACCORD : OK -- `X_nat == X_port` sur les %d tuiles hookees." % got["rows"])
    vals = sorted(set(got["ami"].values()))
    if len(got["by_d"]) < 2:
        print("  C. PAS DE FILTRE DE POSITION : NON EXERCE -- toutes les tuiles a occupant ami sont "
              "a la MEME distance des porteurs de 1304 (%r). Un filtre de voisinage rendrait la "
              "meme chose : ce volet ne conclut rien." % sorted(got["by_d"]))
        rc |= 1
    elif len(vals) != 1:
        print("  C. PAS DE FILTRE DE POSITION : ECHEC -- la contribution des feuilles 19+64 VARIE "
              "avec la distance : %r pour les distances %r" % (vals, sorted(got["by_d"])))
        rc |= 1
    else:
        print("  C. PAS DE FILTRE DE POSITION : OK -- contribution native constante (%g) sur des "
              "tuiles a distances %r des porteurs de 1304." % (vals[0], sorted(got["by_d"])))
    if not any(lbl == "SELF" for lbl, _ in got["carriers"]):
        print("  SELF-COUNT : NON EXERCE -- le mover ne porte pas 1304 (prendre `--carrier "
              "genesPrimus`, LE porteur du roster).")
    else:
        print("  SELF-COUNT : exerce -- le mover porte 1304, il se compte lui-meme.")
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--carrier", default="genesPrimus")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--max-steps", type=int, default=120)
    ap.add_argument("--max-arm", type=int, default=6)
    ap.add_argument("--no-drive", action="store_true",
                    help="ne PILOTE pas les positions : regime SUBI (contre-epreuve du montage)")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner en fin de passe")
    ap.add_argument("--extra", nargs=argparse.REMAINDER, default=[])
    a = ap.parse_args()
    try:
        _exiger_build_des_rva()            # #431 : le pin des RVA du hook passe par `build_pin`
    except BuildPinRefused as exc:
        print(str(exc))
        return 2
    sid = _resolve_session()
    if a.runner is not None:
        return run(sid, a.runner, a.carrier, a.max_steps, drive=not a.no_drive, max_arm=a.max_arm)
    rid, state = _build(a.seed, a.board, a.extra)
    if rid is None:
        return 2
    print("runner %d seed=%s board=%s carrier=%s drive=%s"
          % (rid, a.seed, a.board, a.carrier, not a.no_drive))
    try:
        return run(sid, rid, a.carrier, a.max_steps, drive=not a.no_drive, max_arm=a.max_arm)
    finally:
        if not a.keep:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
            try:
                state.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
