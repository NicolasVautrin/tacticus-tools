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
    ap.add_argument("--step", default="read", choices=["read", "witness", "graft"])
    ap.add_argument("--ability", action="append", type=int, default=None)
    a = ap.parse_args()
    if a.step == "read":
        return step_read()
    sid = _resolve_session()
    if not sid:
        print("aucune session Frida")
        return 1
    return step_graft(sid, a.ability or (WITNESSES if a.step == "witness" else WITNESSES))


if __name__ == "__main__":
    sys.exit(main())
