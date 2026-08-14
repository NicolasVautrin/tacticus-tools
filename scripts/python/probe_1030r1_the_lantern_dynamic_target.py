"""MESURE #1030-r1 (leve dans la tranche #287-r11) -- le gate dynamique CIBLE de `1094 TheLantern`.

CE QUE CE PROBE ETABLIT : la GEOMETRIE que rend le mirror, tuile par tuile, autour d'un caster
SEPT-HEX. C'est la mesure qui a permis d'ecrire les attendus du test de garde -- ils ne sont pas
supposes.

LE POINT QUI ETAIT OUVERT, et comment il est TRANCHE : le corps natif est

    A = battleQuery.<IBattleQuery 81 GetAdjacentTiles>(casterTiles, 0, 1, 1)
    B = battleQuery.<IBattleQuery 79 GetAdjacentTiles>(targetTile,  0, 1, 1)
    A.<ISet<T> slot 1>(B) ; return (A.Count == 1) ? 0 : 2

et le SLOT 1 d'`ISet<T>` n'etait pas mesure -- `ExceptWith` et `IntersectWith` donnent des
ensembles opposes. Deux sources INDEPENDANTES le tranchent :

  * REFUTATION GEOMETRIQUE -- `|A \\ B| >= |A| - |B|`, `|B| <= 6` (voisinage d'UNE tuile), et
    `A` contient au minimum l'empreinte 7-hex du caster. Au regime nominal `|A| = 19`, donc
    `|A \\ B| >= 13` : avec `ExceptWith` la regle refuserait TOUT cast, or l'ability est castee
    en jeu (effets 1194/1195 poses, phase 2 observee). `ExceptWith` est IMPOSSIBLE.
  * TEXTE i2 -- `Abilities/TheLantern_CurrentLevelDescription` : << in **one of six directions** >>.
    C'est exactement ce que rend `|A inter B| == 1`, et ce probe le VERIFIE (il compte les tuiles
    acceptees et leur position).

ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import os
import sys

PYDIR = os.path.dirname(os.path.abspath(__file__))
if PYDIR not in sys.path:
    sys.path.insert(0, PYDIR)

import hexgeo                                                            # noqa: E402
from engine.entities.effects_state import EffectsState                   # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.abilities.deathguard import TheLanternAbility         # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.components import set_unit_feet                       # noqa: E402
from engine.runner.snapshot import load_state                            # noqa: E402

COLS, ROWS = 13, 13
CENTRE = (6, 6)
CASTER, FOE = 10, 20


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles() -> list:
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return out


def empreinte_7() -> list:
    """Le centre + sa couronne = les SEPT tuiles de Mortarion (`CasterHas7Tiles`)."""
    return [CENTRE] + list(hexgeo.neighbors(*CENTRE))


def monter():
    board = Board(_tiles(), adjacency="evenq")
    decision = {"currentPlayer": 1, "units": [
        {"id": CASTER, "visualId": "deathBossMortarion", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": CENTRE[0], "row": CENTRE[1]}, "effects": []},
        {"id": FOE, "visualId": "ultraTitus", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 0, "row": 0}, "effects": []},
    ]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000}
                         for u in decision["units"]]}
    st = load_state(decision, observe, board=board)
    if st.effects is None:
        st.effects = EffectsState()
    set_unit_feet(st, CASTER, empreinte_7())
    return st, board


def main() -> int:
    st, board = monter()
    ab = TheLanternAbility()
    emp = {(int(c), int(r)) for c, r in empreinte_7()}
    acceptees, par_distance = [], {}
    for col in range(COLS):
        for row in range(ROWS):
            tid = board.id_at(col, row)
            if tid is None:
                continue
            r = ab.get_dynamic_invalid_target_reason(st, CASTER, tid)
            d = min(hexgeo.distance((col, row), (c, rr)) for c, rr in emp)
            par_distance.setdefault(d, [0, 0])
            par_distance[d][0 if r == 0 else 1] += 1
            if r == 0:
                acceptees.append((col, row, d))
    print("== #1030-r1 : geometrie du gate dynamique de 1094 TheLantern ==")
    print("caster SEPT-HEX centre en %r ; plateau %dx%d entierement marchable" % (CENTRE, COLS, ROWS))
    print("distance a l'EMPREINTE | acceptees | refusees")
    for d in sorted(par_distance):
        a, refus = par_distance[d]
        print("  d=%-2d                  | %-9d | %d" % (d, a, refus))
    print()
    print("tuiles ACCEPTEES (%d) : %r" % (len(acceptees), [(c, r) for c, r, _ in acceptees]))
    dcentre = sorted({hexgeo.distance((c, r), CENTRE) for c, r, _ in acceptees})
    print("leurs distances au CENTRE de l'empreinte : %r" % (dcentre,))
    rouges = 0
    if len(acceptees) != 6:
        print("[FAIL] l'i2 dit << one of six directions >> -- %d tuiles acceptees" % len(acceptees))
        rouges += 1
    if dcentre != [3]:
        print("[FAIL] les six directions doivent etre a distance 3 du CENTRE : %r" % (dcentre,))
        rouges += 1
    # CONTRE-BRAS : une tuile du disque interieur et une tuile lointaine doivent REFUSER.
    for coord, libelle in (((CENTRE[0], CENTRE[1] + 2), "ring-2 (dans A)"),
                           ((CENTRE[0], CENTRE[1] + 5), "hors de portee de A")):
        tid = board.id_at(*coord)
        got = ab.get_dynamic_invalid_target_reason(st, CASTER, tid)
        ok = (got == int(TR.TargetMatchesDynamicRule))
        rouges += 0 if ok else 1
        print("  contre-bras %-22s %r -> 0x%x %s" % (libelle, coord, got, "OK" if ok else "MISMATCH"))
    print()
    print("[1030-r1] %s -- %d ecart(s)" % ("OK" if rouges == 0 else "FAIL", rouges))
    return 0 if rouges == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
