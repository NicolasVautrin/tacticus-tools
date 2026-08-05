"""probe #433-r4-r2-r4 -- ATTRIBUER le rouge du test d'adjacence : quel CANAL porte quoi.

POURQUOI CE PROBE EXISTE. `test_433_r4_r2_adjacency_foyer_live.py` construisait sa contre-epreuve
par UNE mutation, `elev_by_pos = None`, en la nommant « l'etat d'AVANT #433-r4-r2 ». Cette mutation
a cesse d'etre CHIRURGICALE, pour deux raisons INDEPENDANTES, toutes deux posterieures au test :

  1. `elev_by_pos` n'est plus le SEUL canal de la porte d'adjacence. Depuis
     `fix(#433-r4-r1-r4-r2)`, `battle_query.is_adjacent` enumere d'abord `neigh_by_pos` -- la liste
     STOCKEE du `ConnectivityComponent` telle que
     `IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles(t, 0, 0, 1)` la rend, donc DEJA
     traversee par la porte d'elevation de
     `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`. Neutraliser
     `elev_by_pos` seul ne rend donc PLUS l'arete que la porte retire : le voisinage capte l'a deja
     retiree. La porte du port est IDEMPOTENTE sur ce substrat -- c'est ecrit dans la docstring
     d'`is_adjacent`, et c'est exactement ce qui vide la contre-epreuve.

  2. `elev_by_pos` a acquis un SECOND role, sans rapport avec l'adjacence : depuis
     `feat(#433-r4-r2-r1-r2)` il est le substrat de la LIGNE DE VUE de
     `IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange` (branche A). Le neutraliser
     ELARGIT donc la zone d'ability de l'ennemi en meme temps qu'il est cense « retirer la porte
     d'adjacence » : deux mecanismes bougent d'un coup, et le bras `off` ne mesure plus une cause.

CE QUE LE PROBE MESURE, sur UN SEUL montage (celui de `--step couple`), pour ATTRIBUER :

  * `--step canaux` : `adjacent_at_origin` sous les QUATRE combinaisons (elev on/off) x (neigh
    on/off). Si `neigh` seul suffit a exclure l'ennemi, le bras `elev=None` du test est mort.
  * `--step biais` : `utility_at` avec les canaux COMPLETS (ce que `generate_candidates` passe
    reellement) contre les canaux VIDES (ce que le probe historique passait a `rows`). L'ecart
    mesure ici est un ARTEFACT DE MESURE, pas un residu du port.
  * `--step avant` : la vraie contre-epreuve -- le port d'AVANT #433-r4-r2, c'est-a-dire le
    partage A/B tranche par `hexgeo.distance(origine, E) == 1` (ce que le port faisait alors),
    TOUS LES AUTRES CANAUX INTACTS. C'est la seule mutation qui isole le foyer d'adjacence.

Usage (ASCII only, depuis scripts/python) :
  python probe_433_r4_r2_r4_canaux_adjacence.py --step all
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                     # noqa: E402
import probe_433_r4_r2_adjacency_foyer as P                       # noqa: E402
from rl_collect_batch import _resolve_session                     # noqa: E402


def _montage(pick_idx=0):
    """Le MEME montage que `--step couple` : O porte un voisin hex a `|dElev| >= 2`, le caster a
    `Movement = 4` pour que le sweep atteigne `d = 4..5` (la zone ou les branches different).

    `pick_idx` selectionne la N-ieme paire `(O, voisin haut)` du board au lieu de la premiere : une
    conclusion tiree d'UN SEUL relief ne se generalise pas (le couple, lui, est fige sur la
    premiere paire pour rester deterministe)."""
    sid = _resolve_session()
    if not sid:
        return None, {"error": "aucune session Frida"}
    rid, err = P._build()
    if rid is None:
        return None, {"error": "build KO : %s" % err}
    try:
        elev, native_nb = P._board_maps(sid, rid)
    finally:
        P._dispose(sid, rid)
    paires = []
    for O in sorted(elev):
        if elev[O] is None:
            continue
        hi = [q for q in hexgeo.neighbors(O[0], O[1])
              if elev.get(q) is not None and abs(elev[q] - elev[O]) >= 2]
        if hi:
            paires.append((O, hi[0]))
    if not paires:
        return None, {"error": "aucune paire (O, voisin a |dElev| >= 2) sur %s" % P.BOARD}
    if pick_idx >= len(paires):
        return None, {"error": "paire %d demandee, %d disponibles sur %s"
                               % (pick_idx, len(paires), P.BOARD)}
    O, Y = paires[pick_idx]

    sid = _resolve_session()
    rid, err = P._build(["--unit-stat", "%s:Movement=4" % P.CASTER])
    if rid is None:
        return None, {"error": "build KO (montage) : %s" % err}
    _dv, c, e = P._units(sid, rid)
    if c is None or e is None:
        P._dispose(sid, rid)
        return None, {"error": "caster/ennemi absent"}
    if not P._place(sid, rid, c["id"], e["id"], O, Y):
        P._dispose(sid, rid)
        return None, {"error": "montage non installe"}
    dv, c, e = P._units(sid, rid)
    posn = {u["id"]: (u["pos"]["col"], u["pos"]["row"])
            for u in (dv.get("units") or []) if u.get("pos")}
    if posn.get(c["id"]) != O or posn.get(e["id"]) != Y:
        P._dispose(sid, rid)
        return None, {"error": "positions non atteintes : %r" % posn}
    nat = P._r(sid, "ncEvaluate", {"runnerId": rid, "unitId": c["id"],
                                   "abilityType": P.ABILITY, "sweep": True}, 180)
    native = {tuple(p["pos"]): p.get("util") for p in (nat.get("positions") or [])}
    ctx = P._nc_context(sid, rid, dv, c["id"])
    return (sid, rid, O, Y, elev, native_nb, ctx, native), None


def run(verbose=True, pick_idx=0) -> dict:
    m, err = _montage(pick_idx)
    if err:
        return err
    sid, rid, O, Y, elev, native_nb, ctx, native = m
    try:
        from engine.playbook.noncomparable._base import occupant_team_by_pos
        from engine.playbook.noncomparable.early_warning_override import \
            EarlyWarningOverridePlaybook
        pb = EarlyWarningOverridePlaybook()
        # Le foyer de la mutation « port d'AVANT #433-r4-r2 » vit dans le probe principal : le
        # dupliquer ici en ferait deux definitions divergentes de la meme contre-epreuve.
        pb_avant = P.EarlyWarningOverrideAvant433r4r2()
        enemies = pb.enemies_of(ctx)

        # --- (1) CANAUX : les quatre combinaisons du foyer d'adjacence -------------------------
        combos = {}
        for tag, kw in (("elev+neigh", {}),
                        ("neigh seul", {"elev_by_pos": None}),
                        ("elev seul", {"neigh_by_pos": None}),
                        ("aucun", {"elev_by_pos": None, "neigh_by_pos": None})):
            c2 = dataclasses.replace(ctx, **kw) if kw else ctx
            combos[tag] = sorted(pb.adjacent_at_origin(c2, enemies))

        # --- (2) BIAIS : `utility_at` canaux COMPLETS vs canaux VIDES --------------------------
        team_by_pos = occupant_team_by_pos(ctx)
        adj = pb.adjacent_at_origin(ctx, enemies)
        rows = []
        for Pp in sorted(native):
            plein = pb.utility_at(Pp, enemies, adj, ctx.elev_by_pos,
                                  getattr(ctx, "is_wall_by_pos", None), team_by_pos,
                                  getattr(ctx, "walkable_by_pos", None),
                                  getattr(ctx, "is_in_fog_by_pos", None))
            nu = pb.utility_at(Pp, enemies, adj)          # exactement ce que `rows` passait
            rows.append({"pos": Pp, "d": hexgeo.distance(Pp, Y), "natif": native[Pp],
                         "plein": plein, "nu": nu})
        diff_plein = [r for r in rows if r["natif"] != r["plein"]]
        diff_nu = [r for r in rows if r["natif"] != r["nu"]]

        # --- (3) AVANT : la contre-epreuve qui isole le foyer d'adjacence ----------------------
        adj_avant = pb_avant.adjacent_at_origin(ctx, enemies)
        rows_avant = []
        for Pp in sorted(native):
            rows_avant.append({"pos": Pp, "d": hexgeo.distance(Pp, Y), "natif": native[Pp],
                               "avant": pb_avant.utility_at(
                                   Pp, enemies, adj_avant, ctx.elev_by_pos,
                                   getattr(ctx, "is_wall_by_pos", None), team_by_pos,
                                   getattr(ctx, "walkable_by_pos", None),
                                   getattr(ctx, "is_in_fog_by_pos", None))})
        diff_avant = [r for r in rows_avant if r["natif"] != r["avant"]]

        out = {
            "O": O, "Y": Y, "elev_O": elev[O], "elev_Y": elev[Y],
            "Y_dans_liste_native_de_O": Y in native_nb.get(O, set()),
            "n": len(rows), "d_max": max(r["d"] for r in rows) if rows else None,
            "combos": combos,
            "adj_courant": sorted(adj), "adj_avant": sorted(adj_avant),
            "diff_plein": diff_plein, "diff_nu": diff_nu, "diff_avant": diff_avant,
            "cand_courant": pb.generate_candidates(ctx),
            "cand_avant": pb_avant.generate_candidates(ctx),
            "cand_elev_none": pb.generate_candidates(dataclasses.replace(ctx, elev_by_pos=None)),
            "native_best": max((v for v in native.values() if v is not None), default=None),
        }
        if verbose:
            print("[canaux] O=%s(elev %s) Y=%s(elev %s) |dElev|=%d ; sweep n=%d d_max=%d"
                  % (O, elev[O], Y, elev[Y], abs(elev[Y] - elev[O]), out["n"], out["d_max"]))
            print("[canaux] Y dans la liste d'adjacence NATIVE de O : %s"
                  % out["Y_dans_liste_native_de_O"])
            for tag in ("elev+neigh", "neigh seul", "elev seul", "aucun"):
                print("[canaux] adjacent_at_origin  %-11s -> %r" % (tag, combos[tag]))
            print("[biais]  port CANAUX COMPLETS != natif : %d/%d"
                  % (len(diff_plein), out["n"]))
            print("[biais]  port CANAUX VIDES    != natif : %d/%d  (ce que `rows` mesurait)"
                  % (len(diff_nu), out["n"]))
            for r in diff_nu[:4]:
                print("[biais]    %r d=%d natif=%r plein=%r nu=%r"
                      % (r["pos"], r["d"], r["natif"], r["plein"], r["nu"]))
            print("[avant]  adjacence COURANTE=%r  AVANT #433-r4-r2=%r"
                  % (out["adj_courant"], out["adj_avant"]))
            print("[avant]  port AVANT != natif : %d/%d" % (len(diff_avant), out["n"]))
            for r in diff_avant[:6]:
                print("[avant]    %r d=%d natif=%r avant=%r" % (r["pos"], r["d"], r["natif"],
                                                                r["avant"]))
            print("[action] COURANT %r" % (out["cand_courant"],))
            print("[action] AVANT   %r" % (out["cand_avant"],))
            print("[action] elev=None (l'ancienne mutation) %r" % (out["cand_elev_none"],))
            print("[action] utilite MAXIMALE du natif sur le sweep : %r" % (out["native_best"],))
        return out
    finally:
        P._dispose(sid, rid)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="all", choices=["all"])
    ap.add_argument("--pick", type=int, default=0,
                    help="N-ieme paire (O, voisin a |dElev| >= 2) du board -- generalisation")
    ap.add_argument("--board", default=None,
                    help="board a monter (defaut : celui du couple, %s)" % P.BOARD)
    a = ap.parse_args()
    if a.board:
        P.BOARD = a.board          # le montage de `P._build` lit cette globale
    res = run(pick_idx=a.pick)
    if "error" in res:
        print("[canaux] REFUS : %s" % res["error"])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
