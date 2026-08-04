"""probe #433-r4-r2-r1-r2 -- le SECOND predicat de `GetPossibleTargetsForOptions` : la LIGNE DE VUE.

LE CRITERE BINAIRE. Le port reproduit-il `b__1`, ou laisse-t-il passer des tuiles que le natif
refuse pour cause d'obscurcissement (elevation / murs) ?

CE QUE LA LECTURE A DONNE, et qui rend la mesure PREDICTIBLE :

    b__1(target) = !IsFriend(target, caster) && GetTilesObscuringTerrain(...).Count > 0

`b__1` n'est gate par AUCUN bit -- il tourne TOUJOURS. Les deux bits
`AllowObscuredTargetByElevation` (25) / `ByWalls` (26) ne decident pas SI il tourne, mais ce qu'il
REGARDE : `IdunBattle.Core.Services.TargetingQuery$$GetTilesObscuringTerrain` en compose un
`ObscuringType`, et rend l'ensemble VIDE quand celui-ci est nul.

    flags = (IndirectFire(0x3ed) || rules & 0x2000000) ? 0 : Elevation(2)
    r     = (rules & 0x4000000) ? flags : (flags | Wall(4))

D'ou la PREDICTION, posee AVANT toute mesure : `r == 0` <=> aucune obstruction possible, quelle que
soit la geometrie. `--step read` la confronte aux DIX mesures deja au dossier (#568), sans monter
un seul runner -- c'est une contre-epreuve gratuite, et elle est falsifiable : une seule ability a
`r == 0` mesuree en dessous de 40/40, ou une seule a `r == 6` mesuree a 40/40, la refute.

LA GEOMETRIE, et pourquoi la question etait piegee. `MovementQuery$$GetTilesObscuringTerrain`
n'interroge NI le `ConnectivityComponent`, NI le champ `neighbours` du `boardGraph` (celui que la
porte `|srcElev - Elevation| < 2` de `TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`
ampute de 18 aretes sur `MC1_67`). Il TRACE deux lignes de COORDONNEES
(`MovementUtil$$DrawLineBetweenCoordinates`, nudge +/-(1e-6, 2e-6, -3e-6)) et interroge chacune par
`StateExtensions$$GetTileAt`. Aucune arete n'est lue : le graphe d'adjacence est hors sujet ici,
dans ses deux versions.

LE MONTAGE est celui de #568, importe TEL QUEL (`probe_433_r4_r2_r1_r1_a_whole_board_gates.sweep`)
-- ability greffee SEULE sur un porteur a arme de MELEE seule, sweep de 40 positions `d = 2..10`,
un seul ennemi vivant, et la GARDE anti-degenerescence qui refuse un greffon dont l'arme porterait
plus loin. Un seul ajout : la carte `isWall` du `boardGraph`, second volet du predicat.

Usage (ASCII only, depuis scripts/python) :
  python probe_433_r4_r2_r1_r2_line_of_sight.py --step read
  python probe_433_r4_r2_r1_r2_line_of_sight.py --step witness
  python probe_433_r4_r2_r1_r2_line_of_sight.py --step graft --ability 1011
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from probe_433_r4_r2_r1_r1_a_whole_board_gates import (  # noqa: E402
    GRAFT_HOST, _grafted_seed, _print, sweep)
from rl_collect_batch import _resolve_session                           # noqa: E402

#: Les DEUX temoins que #568 a isoles, et le discriminant qu'ils portent.
#:   `1161` -- AUCUN gate dynamique (`rules & 2 == 0`) et AUCUN bit `AllowObscured*` : les 5 memes
#:            refus que les abilities a gate. Un ecart qu'une ability SANS gate reproduit ne peut
#:            pas etre impute au gate -- c'est ce qui a attribue le residu au 2e predicat.
#:   `1147` -- pas de gate non plus, mais les DEUX bits : 40/40.
WITNESSES = [1161, 1147]

#: Les mesures LIVE deja au dossier (#568, meme montage, meme board, meme sweep de 40) :
#: `{ability: (natif_en_portee, faux_positifs_du_port_AVANT_cette_tranche)}`. Elles servent de
#: CONTRE-EPREUVE OFFLINE au modele de masque -- pas de verite a elles seules.
MEASURED_568 = {
    1100: (2, 38),      # porteur NATIF `thousTzaangor` (2/40 = sa portee d'arme), pas une greffe
    1143: (0, 0),
    1145: (40, 0),
    1201: (40, 0),
    1025: (40, 0),
    1011: (35, 5),
    1168: (34, 6),
    1200: (34, 6),
    1213: (34, 6),
    1161: (35, 5),
    1147: (40, 0),
    1140: (40, 0),      # `ExemplarOfHate`, mesuree par la tranche #558 sur `darkaAsmodai`
}

#: Les abilities dont la zone est VIDE en AMONT (court-circuit `TargetIsFriendly && !TargetIsEnemy`
#: de `GetPossibleTargetTiles`) : leur mesure ne dit RIEN de la ligne de vue.
ZONE_EMPTY_UPSTREAM = {1100, 1143}


def step_read() -> int:
    """La PREDICTION du masque, confrontee aux mesures du dossier. Aucun runner."""
    from engine.services import targeting_query as TQ, ability_range as ar
    from engine.runner.abilities.targeting import (NORMAL_ATTACK_TARGETING_OPTIONS,
                                                   targeting_options_for)
    from engine.entities.active_ability_type import ActiveAbilityType

    print("ObscuringType predit par le masque, contre la mesure LIVE au dossier (#568) :")
    print("  %-6s %-30s %-13s %-4s %-8s %-8s %s"
          % ("id", "name", "rules", "OT", "natif/40", "FP avant", "verdict"))
    bad = 0
    for aid in sorted(MEASURED_568):
        opts = targeting_options_for(aid)
        rules = getattr(opts, "rules", None)
        ot = TQ.obscuring_type_for(rules)
        natif, fp = MEASURED_568[aid]
        try:
            nm = ActiveAbilityType(aid).name
        except ValueError:                                            # pragma: no cover
            nm = "?"
        if aid in ZONE_EMPTY_UPSTREAM:
            verdict = "n/a (zone vide en amont)"
        elif ot == TQ.OBSCURING_TYPE_NONE:
            verdict = "OK" if fp == 0 else "REFUTE (OT=0 mais le port sur-attribuait)"
        else:
            verdict = "OK" if fp >= 5 else "REFUTE (OT!=0 mais aucun ecart mesure)"
        if verdict.startswith("REFUTE"):
            bad += 1
        print("  %-6d %-30s %-13s %-4d %-8d %-8d %s"
              % (aid, nm, hex(int(rules)) if rules is not None else "NON LU", ot, natif, fp,
                 verdict))
    print("")
    na_rules = int(NORMAL_ATTACK_TARGETING_OPTIONS.rules)
    print("attaque NORMALE : rules=%s -> OT=%d (elle passe par le MEME GetPossibleTargetsForOptions)"
          % (hex(na_rules), TQ.obscuring_type_for(na_rules)))
    print("IndirectFire(%d) sur le caster : OT(0x0) %d -> %d (le volet MUR SUBSISTE)"
          % (TQ.INDIRECT_FIRE_TRAIT, TQ.obscuring_type_for(0),
             TQ.obscuring_type_for(0, caster_has_indirect_fire=True)))
    print("greffon %s porte IndirectFire ? %s" % (GRAFT_HOST, ar._has_indirect_fire(GRAFT_HOST)))
    print("")
    print("REFUTATIONS : %d" % bad)
    return 1 if bad else 0


# ------------------------------------------------------------------------------------------------
# --step normal : la GENERALISATION -- l'ATTAQUE NORMALE et le trait `IndirectFire`
#
# Les deux temoins de #568 sont des abilities `UseWholeBoard` GREFFEES. Ils ne disent RIEN de
# l'autre terme de l'union de `AttackQuery$$GetAllTilesInAbilityRange` -- l'attaque NORMALE, dont
# le preset (`0x4002`) ne porte aucun `AllowObscuredTarget*` et qui concerne TOUTE unite a distance
# du jeu, pas un greffon. C'est le vrai rayon de souffle de cette tranche, et il se confronte sur
# des kits NATIFS, sans greffe.
#
#   `necroWarden`   arme 3 (OBSCURCIE) + `1005 AdaptiveStrategy` portee 1, `ObscuringType == 0`
#                   -> tout ce qui depasse `d = 1` vient de l'arme : le predicat neuf y est SEUL
#                      responsable de la forme de la zone.
#   `astraOrdnance` arme 3 + `1026 BasiliskBarrage` `UseWholeBoard` sans gate, mais le porteur a
#                   le trait `IndirectFire` -> `flags = 0` et `r = 4` : le volet ELEVATION tombe,
#                   le volet MURS SUBSISTE. Un port qui aurait rabattu le trait sur « aucune
#                   obstruction » passerait quand meme ; un port qui l'aurait OUBLIE retrecirait la
#                   zone de tout le relief du plateau -- c'est ce second cas que ce montage refute.
# ------------------------------------------------------------------------------------------------
def set_board(board_id: str) -> None:
    """Change le board du montage PARTAGE (#568) et invalide sa memoisation de cartes.

    Necessaire pour confronter le volet MURS : `MC1_67` n'en porte AUCUN (mesure : 0 tuile
    `isWall`), et les 17 boards qui en portent sont les `C6_*` (`HulkWall` dans la BC)."""
    import probe_433_r4_r2_r1_r1_a_whole_board_gates as P568
    P568.BOARD = board_id
    P568._BOARD_CACHE.clear()


NORMAL_ATTACK_HOSTS = ["necroWarden", "astraOrdnance"]
NORMAL_ATTACK_DIST = 3      # O et Y NON adjacents -> branche A pure, mais assez proches pour que
#                             le sweep couvre abondamment le disque d'arme (`d <= 3`)
NORMAL_ATTACK_MOVEMENT = 6  # `--unit-stat Movement` du caster : le sweep est son disque de MOUVEMENT


def _pick_discriminant(elev, walk, wall, dist, movement, rules, indirect):
    """Choisit `(O, Y)` a distance `dist` de facon a MAXIMISER le nombre de positions du sweep ou
    le predicat de ligne de vue MORD -- au lieu de prendre la premiere paire venue.

    POURQUOI. Un montage ou aucun mur ni aucun relief ne se trouve entre l'ennemi et les positions
    balayees rend un accord DEGENERE : le port et le modele concurrent (« zone = disque ») y
    disent la meme chose. Mesure sur `C6_17` avec la paire par defaut `(0,0)/(0,3)` : **zero**
    obstruction sur 36 positions. La doctrine est de DEPLACER les unites pour obtenir la
    configuration voulue, pas de conclure « la geometrie de spawn ne le permet pas ».

    ⚠ Le port ne sert ici qu'a CHOISIR le montage. Il ne juge rien : le verdict reste la partition
    NATIVE, et le port est confronte a elle apres coup. Un montage choisi par le port ne peut pas
    fabriquer un accord -- au pire il choisit un terrain ou le port se trompera davantage."""
    import hexgeo
    from engine.services import movement_query as MQ
    from engine.services import targeting_query as TQ
    board = MQ.PositionBoard(elev, wall)
    cands = sorted(p for p in walk if walk[p] and elev.get(p) is not None)
    best, best_n = (None, None), -1
    for O in cands:
        disk = [p for p in cands if hexgeo.distance(O, p) <= movement]
        for Y in cands:
            if hexgeo.distance(O, Y) != dist:
                continue
            n = sum(1 for P in disk
                    if TQ.target_is_obscured(board, [Y], P, rules,
                                             caster_has_indirect_fire=indirect))
            if n > best_n:                     # `>` strict : premiere paix en ordre trie a egalite
                best, best_n = (O, Y), n
    return best[0], best[1], best_n


def sweep_normal_attack(sid, enemy, dist=NORMAL_ATTACK_DIST):
    """La MESURE de l'axe ATTAQUE NORMALE -- meme isolant que #568, montage RAPPROCHE.

    GARDE ANTI-DEGENERESCENCE, et elle est l'INVERSE de celle de #568 : ici l'arme DOIT porter au
    dela de l'adjacence (sinon le disque d'arme ne rencontre jamais la ligne de vue, qui est muette
    a `d = 1`), et le natif doit REFUSER au moins une tuile DANS le disque de portee -- sans quoi
    un modele « zone = disque » rendrait le meme resultat et la mesure ne prouverait rien."""
    import hexgeo
    import probe_433_r4_r2_r1_r1_a_whole_board_gates as P568
    from engine.services import ability_range as ar
    from engine.runner.abilities.targeting import unit_weapon_range
    from probe_433_r4_r2_r1_r1_a_whole_board_gates import (
        _board_maps, _build, _dispose, _entity_actives, _nc_partition, _pick_far, _place, _units)

    wr = unit_weapon_range(enemy, None)
    if wr is None or int(wr) < 2:
        return {"error": "anti-degenerescence : %s a une arme de portee %s -- la ligne de vue est "
                         "MUETTE a d = 1, ce montage ne mesurerait rien" % (enemy, wr)}
    elev, walk, wall = _board_maps(sid, enemy)
    from engine.runner.abilities.targeting import NORMAL_ATTACK_TARGETING_OPTIONS
    indirect = ar._has_indirect_fire(enemy)
    O, Y, n_pred = _pick_discriminant(elev, walk, wall, dist, NORMAL_ATTACK_MOVEMENT,
                                      int(NORMAL_ATTACK_TARGETING_OPTIONS.rules), indirect)
    if O is None:
        return {"error": "aucune paire walkable a distance %d" % dist}
    rid, err = _build(enemy)
    if rid is None:
        return {"error": "build KO -- %s" % err}
    try:
        _dv, c, e = _units(sid, rid, enemy)
        if c is None or e is None:
            return {"error": "caster ou ennemi absent du decisionView"}
        if not _place(sid, rid, c["id"], e["id"], O, Y):
            return {"error": "montage non installe (pas de tuile candidate)"}
        dv, c, e = _units(sid, rid, enemy)
        posn = {u["id"]: (u["pos"]["col"], u["pos"]["row"])
                for u in (dv.get("units") or []) if u.get("pos")}
        if posn.get(c["id"]) != O or posn.get(e["id"]) != Y:
            return {"error": "positions non atteintes %r" % (posn,)}
        foes = [(u.get("visualId"), (u["pos"]["col"], u["pos"]["row"]))
                for u in (dv.get("units") or [])
                if u.get("pos") and u.get("alive") and not u.get("ctrl")]
        if len(foes) != 1:
            return {"error": "montage IMPUR, %d ennemis vivants %r" % (len(foes), foes)}
        aids = _entity_actives(e)
        in_range, out_range = _nc_partition(sid, rid, c["id"], [Y])
        allp = sorted(in_range | out_range)

        def _model(**kw):
            return {P for P in allp
                    if ar.is_tile_in_range_of_any_ability(Y, P, enemy, ability_ids=aids,
                                                          elev_by_pos=elev, **kw)}

        modeled = _model(is_wall_by_pos=wall)
        # CONTREFACTUELS -- ils chiffrent ce que chaque volet du modele APPORTE. Un accord dont
        # aucun contrefactuel ne differe est un accord en regime DEGENERE : il ne prouve rien.
        sans_los = _model(is_wall_by_pos=wall) if not elev else {
            P for P in allp
            if ar.is_tile_in_range_of_any_ability(Y, P, enemy, ability_ids=aids, elev_by_pos=None)}
        _orig = ar._has_indirect_fire
        try:                                   # « et si le port avait OUBLIE le trait ? »
            ar._has_indirect_fire = lambda _vid: False
            sans_trait = _model(is_wall_by_pos=wall)
        finally:
            ar._has_indirect_fire = _orig
        sans_murs = _model(is_wall_by_pos=None)
        reach = ar.unit_threat_reach(enemy, aids)
        # Ce qu'un modele « zone = DISQUE de rayon reach » rendrait -- le concurrent a battre.
        disk = {P for P in allp if hexgeo.distance(P, Y) <= reach}
        by_d = {}
        for P in allp:
            by_d.setdefault(hexgeo.distance(P, Y), []).append(P in in_range)
        return {"enemy": enemy, "entity_abilities": aids, "note": None, "O": O, "Y": Y,
                "indirect_fire": indirect, "n_obstructions_prevues": n_pred,
                "board": P568.BOARD, "weapon": int(wr), "reach": reach, "n_sweep": len(allp),
                "n_walls_board": sum(1 for v in wall.values() if v),
                "natif_in_range": sorted(in_range),
                "refus_dans_le_disque": sorted(disk - in_range),
                "delta_sans_los": sorted(sans_los - modeled),
                "delta_sans_trait": sorted(modeled - sans_trait),
                "delta_sans_murs": sorted(sans_murs - modeled),
                "par_distance": {d: (sum(1 for x in v if x), len(v)) for d, v in sorted(by_d.items())},
                "faux_positifs": sorted(modeled - in_range),
                "faux_negatifs": sorted(in_range - modeled),
                "exact": modeled == in_range}
    finally:
        _dispose(sid, rid)


def step_normal(sid, hosts) -> int:
    rc = 0
    for enemy in hosts:
        print("")
        print("=== ATTAQUE NORMALE -- kit NATIF %s (aucune greffe) ===" % enemy)
        res = sweep_normal_attack(sid, enemy)
        if "error" in res:
            print("  REFUS : %s" % res["error"])
            rc |= 1
            continue
        print("  board=%s arme=%d reach porte=%s entite.abilities=%r sweep=%d murs sur le board=%d"
              % (res["board"], res["weapon"], res["reach"], res["entity_abilities"],
                 res["n_sweep"], res["n_walls_board"]))
        print("  O(caster)=%r  Y(ennemi)=%r  IndirectFire=%s  obstructions prevues au choix du "
              "montage=%d" % (res["O"], res["Y"], res["indirect_fire"],
                              res["n_obstructions_prevues"]))
        line = "  natif en portee par distance :"
        for d, (n, tot) in sorted(res["par_distance"].items()):
            line += "  d%d=%d/%d" % (d, n, tot)
        print(line)
        print("  refus DANS le disque de rayon %s : %d %r"
              % (res["reach"], len(res["refus_dans_le_disque"]), res["refus_dans_le_disque"][:8]))
        print("  ce que chaque volet APPORTE (contrefactuels) : sans ligne de vue +%d | trait "
              "IndirectFire ignore -%d | carte des murs absente +%d"
              % (len(res["delta_sans_los"]), len(res["delta_sans_trait"]),
                 len(res["delta_sans_murs"])))
        print("  port : FP=%d FN=%d -> %s"
              % (len(res["faux_positifs"]), len(res["faux_negatifs"]),
                 "EXACT" if res["exact"] else "DIVERGE"))
        if res["faux_positifs"]:
            print("  faux positifs : %r" % (res["faux_positifs"][:10],))
        if res["faux_negatifs"]:
            print("  faux negatifs : %r" % (res["faux_negatifs"][:10],))
        rc |= 0 if res["exact"] else 1
    return rc


def step_graft(sid, abilities) -> int:
    from engine.entities.active_ability_type import ActiveAbilityType
    rc = 0
    for aid in abilities:
        try:
            nm = ActiveAbilityType(int(aid)).name
        except ValueError:                                            # pragma: no cover
            nm = "?"
        print("")
        print("=== %d %s  greffee sur %s ===" % (int(aid), nm, GRAFT_HOST))
        seed, reports = _grafted_seed(aid)
        print("  seed BC greffe : %s" % (reports,))
        rc |= _print(sweep(sid, GRAFT_HOST, seed, [int(aid)]), "graft %d" % int(aid))
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="read", choices=["read", "witness", "graft", "normal"])
    ap.add_argument("--ability", action="append", type=int, default=None)
    ap.add_argument("--enemy", action="append", default=None)
    ap.add_argument("--board", default=None,
                    help="board du montage (defaut MC1_67, celui de #568). Les 17 boards `C6_*` "
                         "portent des tuiles `HulkWall` -- seul substrat ou le volet MURS mord.")
    a = ap.parse_args()
    if a.board:
        set_board(a.board)
    if a.step == "read":
        return step_read()
    sid = _resolve_session()
    if not sid:
        print("aucune session Frida")
        return 1
    if a.step == "normal":
        return step_normal(sid, a.enemy or NORMAL_ATTACK_HOSTS)
    return step_graft(sid, a.ability or WITNESSES)


if __name__ == "__main__":
    sys.exit(main())
