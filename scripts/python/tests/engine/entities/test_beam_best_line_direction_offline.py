"""Structure de `GetTilesInBestLine` (#126) — ce que le LIVE ne peut PAS distinguer.

La face DECISION n'observe du beam que son UTILITE (`Count(Enemies(Units(bestLine)))`), donc
l'ORDRE interne du choix de direction est invisible d'un agreement live : a comptes EGAUX, deux
directions differentes donnent la MEME utilite et donc la MEME action. Ce fichier garde ce que le
live laisse passer -- la structure du tri natif et les deux briques qu'il consomme :

  * `IdunBattle.Utils.Hex.EdgeExtensions$$GetAngleTo` (slot 0x71 `GetAngleBetweenVectors`) ;
  * `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` : le ring-1
    de `AdjacentTiles` n'est PAS le ring-1 geometrique (walkables + porte `|Delta elev| < 2`) ;
  * `IdunBattle.Entities.Selectors.SortByFormulaSelector$$Select` chaine `OrderBy(angle)` puis
    `OrderByDescending(count)` : tris STABLES -> cle PRIMAIRE = le compte, tie-break = l'angle.

La CONFORMITE de la decision, elle, est confrontee au natif par
`tests/engine/test_dark_talon_beam_direction_decision_live.py`. ASCII only.
"""
from __future__ import annotations

import hexgeo
from engine import battle_query as bq
from engine.playbook.noncomparable.dark_talon_strike import _best_line_direction, _beam_count

FLAT = {(c, r): 0 for c in range(9) for r in range(9)}
WALK = {p: True for p in FLAT}


def _acc(walk=None, elev=None):
    return bq.tiles_behind_accessors(walk if walk is not None else WALK,
                                     elev if elev is not None else FLAT)


def _step(p, k):
    """Voisin de `p` dans la direction d'arete `k` (0..5) -- inverse de `bq.connecting_edge`."""
    for n in hexgeo.neighbors(p[0], p[1]):
        if bq.connecting_edge(p, n) == k:
            return n
    raise AssertionError(f"pas de voisin d'arete {k} pour {p}")


def test_get_angle_to_is_the_minimal_hex_angle():
    """`d = |e1 - e2| ; a = d*60 ; if a > 120 : a = (6-d)*60` -> 0/60/120/180/120/60."""
    assert [bq.get_angle_between_vectors(0, k) for k in range(6)] == [0, 60, 120, 180, 120, 60]
    assert bq.get_angle_between_vectors(4, 1) == 180        # symetrique
    assert bq.get_vector((3, 3), (3, 3)) == 0               # meme tuile -> vecteur par defaut
    assert bq.get_vector((3, 3), (6, 6)) == 0               # delta non unitaire -> idem


def test_adjacent_tiles_ring_is_gated_by_walkability_and_elevation():
    """Le ring-1 natif retire les non-walkables ET les paliers a `|Delta elev| >= 2`."""
    center = (4, 4)
    ring = hexgeo.neighbors(*center)
    elev = dict(FLAT)
    elev[ring[0]] = 2                                       # marche >= 2 : hors ring natif
    walk = dict(WALK)
    walk[ring[1]] = False                                   # non walkable : hors ring natif
    wa, ea, te = _acc(walk, elev)
    got = bq.get_adjacent_tiles(center, walkable_at=wa, elevation_at=ea, tile_exists=te)
    assert set(got) == set(ring) - {ring[0], ring[1]}
    # bord de plateau : `GetTileEntityById == null` -> la tuile n'entre pas
    corner_ring = bq.get_adjacent_tiles((0, 0), walkable_at=wa, elevation_at=ea, tile_exists=te)
    assert all(p in FLAT for p in corner_ring)


def test_count_is_the_primary_key_and_angle_only_breaks_ties():
    """Cle PRIMAIRE = #ennemis alignes (le tri par count DESC est applique EN DERNIER, donc il
    domine) ; l'angle ne departage qu'a comptes egaux, et le prolongement (angle 0) gagne alors."""
    caster, aim = (4, 4), None
    d1 = 2                                                  # arete du rayon caster -> aim
    aim = _step(caster, d1)
    ahead = _step(aim, d1)                                  # prolongement : angle 0
    side = _step(aim, (d1 + 1) % 6)                         # coude a 60 deg
    behind_side = _step(side, (d1 + 1) % 6)
    wa, ea, te = _acc()

    # (a) comptes EGAUX (1 vs 1) -> l'angle tranche : le prolongement gagne.
    tie = {aim, ahead, side}
    assert _best_line_direction(caster, aim, tie, wa, ea, te) == ahead
    assert _beam_count(caster, aim, tie, WALK, FLAT) == 2    # la tuile visee + 1 aligne

    # (b) le coude aligne 2 ennemis -> la cle primaire l'emporte sur l'angle.
    win = {aim, ahead, side, behind_side}
    assert _best_line_direction(caster, aim, win, wa, ea, te) == side
    assert _beam_count(caster, aim, win, WALK, FLAT) == 3

    # (c) le prolongement SEUL ne touche personne dans cette configuration : c'est la BORNE
    #     INFERIEURE que #126 a levee (util 1 avant, 3 apres -- de part et d'autre de MIN_UTILITY).
    ox, _oy, oz = hexgeo.to_cube(*caster)
    ax, _ay, az = hexgeo.to_cube(*aim)
    prolong = hexgeo.from_cube(ax + (ax - ox), az + (az - oz))
    elbow = {aim, side, behind_side}
    assert prolong not in elbow
    assert _beam_count(caster, aim, elbow, WALK, FLAT) == 3   # argmax : le coude


def test_elevation_gate_still_truncates_the_chosen_line():
    """Le gate #124 vit SOUS l'argmax : la meilleure direction reste comptee tuile par tuile."""
    caster = (4, 4)
    d1 = 2
    aim = _step(caster, d1)
    side = _step(aim, (d1 + 1) % 6)
    behind_side = _step(side, (d1 + 1) % 6)
    elev = dict(FLAT)
    elev[behind_side] = 2                                   # marche >= 2 APRES le 1er aligne
    wa, ea, te = _acc(WALK, elev)
    enemies = {aim, side, behind_side}
    assert _best_line_direction(caster, aim, enemies, wa, ea, te) == side
    assert _beam_count(caster, aim, enemies, WALK, elev) == 2      # visee + `side`, pas au-dela
    assert _beam_count(caster, aim, enemies, WALK, FLAT) == 3      # sans la marche : 3
