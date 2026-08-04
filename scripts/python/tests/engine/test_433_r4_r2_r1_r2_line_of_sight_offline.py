"""OFFLINE #433-r4-r2-r1-r2 -- le SECOND predicat de `GetPossibleTargetsForOptions` (LIGNE DE VUE).

Ce fichier GARDE le mirror : la composition du `ObscuringType` par le masque et le trait, la
GEOMETRIE (les deux tuiles de bout de ligne, le sens du seuil, la fat-line, le silence a distance 1),
le substrat `PositionBoard`, et les degradations NOMMEES (canal absent, masque non lu). Il ne
mesure rien -- l'oracle natif est dans le fichier LIVE homonyme.

ASCII only.
"""
from __future__ import annotations

import pytest

from engine.services import movement_query as MQ
from engine.services import targeting_query as TQ

ELEV = TQ.ALLOW_OBSCURED_TARGET_BY_ELEVATION
WALL = TQ.ALLOW_OBSCURED_TARGET_BY_WALLS


# ------------------------------------------------------------------------------------------------
# 1. `obscuring_type_for` -- la table de verite du decompile
# ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("rules,indirect,expected", [
    (0, False, TQ.OBSCURING_TYPE_ALL),          # ni bit ni trait -> elevation + murs
    (ELEV, False, TQ.OBSCURING_TYPE_WALL),      # elevation autorisee -> il reste les murs
    (WALL, False, TQ.OBSCURING_TYPE_ELEVATION),  # murs autorises -> il reste l'elevation
    (ELEV | WALL, False, TQ.OBSCURING_TYPE_NONE),
    (0, True, TQ.OBSCURING_TYPE_WALL),          # IndirectFire == le bit 25, PAS le bit 26
    (WALL, True, TQ.OBSCURING_TYPE_NONE),
])
def test_obscuring_type_truth_table(rules, indirect, expected):
    """`TargetingQuery$$GetTilesObscuringTerrain`, VERBATIM :

        flags = (HasTrait(caster, 0x3ed) || (rules & 0x2000000)) ? 0 : 2;
        r     = (rules & 0x4000000) ? flags : (flags | 4);

    Les deux volets sont INDEPENDANTS, et le trait `IndirectFire` n'exempte QUE l'elevation --
    un caster a tir indirect reste arrete par un mur. Confondre les deux ferait rendre `0` la ou
    le natif rend `4`, donc supprimerait tout le volet MURS pour ces casters."""
    assert TQ.obscuring_type_for(rules, indirect) == expected


def test_unread_mask_removes_nothing():
    """Masque NON RE-LU -> `OBSCURING_TYPE_NONE`, donc aucun retrait.

    C'est la convention permissive de toute la cascade de ciblage : inventer un obscurcissement
    sur un masque qu'on n'a pas lu retirerait des tuiles que le natif garde. `None` n'est PAS
    `0` -- un masque LU et nul vaut `OBSCURING_TYPE_ALL`, ce qui est l'oppose."""
    assert TQ.obscuring_type_for(None) == TQ.OBSCURING_TYPE_NONE
    assert TQ.obscuring_type_for(0) == TQ.OBSCURING_TYPE_ALL


# ------------------------------------------------------------------------------------------------
# 2. La GEOMETRIE -- une colonne droite, ou la ligne hex est la colonne elle-meme
# ------------------------------------------------------------------------------------------------
def _col_board(elev_overrides=None, walls=None):
    """Colonne `col = 0`, lignes 0..8, elevation 0 partout sauf surcharge."""
    elev = {(0, r): 0 for r in range(9)}
    elev.update(elev_overrides or {})
    return MQ.PositionBoard(elev, {p: True for p in (walls or ())})


def test_distance_one_is_never_obscured():
    """`if (2 < lineA.Count)` -- a distance 1 la ligne fait DEUX tuiles et AUCUN des deux volets
    ne tourne, pas meme les murs. C'est structurel, pas un gate d'adjacence ajoute."""
    b = _col_board({(0, 2): 9}, walls=[(0, 1), (0, 2)])
    assert TQ.target_is_obscured(b, [(0, 1)], (0, 2), 0) is False


def test_elevation_blocks_only_the_two_end_neighbours():
    """`DetermineBlockingTiles` n'est appele qu'a l'indice `1` et a `Count - 2`.

    Une tuile HAUTE au MILIEU d'une longue ligne ne bloque donc rien -- contre-intuitif, et c'est
    exactement ce qu'un modele « une tuile haute quelque part sur la ligne » aurait invente."""
    b = _col_board({(0, 2): 9})               # (0,2) = milieu strict de (0,0) -> (0,4)
    assert TQ.target_is_obscured(b, [(0, 0)], (0, 4), 0) is False
    # la MEME tuile, devenue voisine d'un bout, bloque
    assert TQ.target_is_obscured(b, [(0, 1)], (0, 3), 0) is True


def test_threshold_is_signed_and_one_way():
    """`(elev(mid) - elevationToCompare) >= 2` -- SIGNE. Une tuile plus BASSE n'obscurcit jamais,
    et l'ecart doit atteindre 2 (un ecart de 1 passe)."""
    assert TQ.target_is_obscured(_col_board({(0, 2): 1}), [(0, 1)], (0, 3), 0) is False
    assert TQ.target_is_obscured(_col_board({(0, 2): 2}), [(0, 1)], (0, 3), 0) is True
    assert TQ.target_is_obscured(_col_board({(0, 2): -5}), [(0, 1)], (0, 3), 0) is False


def test_reference_is_the_nearest_endpoint_of_each_side():
    """L'indice `1` se compare a l'elevation du DEPART, l'indice `Count-2` a celle de l'ARRIVEE.

    Ici la ligne `(0,0) -> (0,3)` a quatre tuiles : l'indice 1 est `(0,1)` (contre `elev(0,0)`) et
    l'indice 2 est `(0,2)` (contre `elev(0,3)`). Un caster PERCHE voit par-dessus la premiere, mais
    la seconde reste jugee depuis la cible, restee en bas."""
    b = _col_board({(0, 0): 5, (0, 1): 5, (0, 2): 5, (0, 3): 0})
    assert TQ.target_is_obscured(b, [(0, 0)], (0, 3), 0) is True    # (0,2) - elev(0,3) = 5 >= 2
    b2 = _col_board({(0, 0): 5, (0, 1): 5, (0, 2): 0, (0, 3): 0})
    assert TQ.target_is_obscured(b2, [(0, 0)], (0, 3), 0) is False  # (0,1)-5 = 0, (0,2)-0 = 0


def test_walls_block_over_the_whole_line_endpoints_included():
    """`DetermineBlockingWalls` parcourt TOUS les indices, bornes comprises -- contraste avec
    l'elevation, qui n'en teste que deux. Un mur au MILIEU bloque donc, la ou une hauteur ne
    bloquerait pas."""
    b = _col_board(walls=[(0, 2)])
    assert TQ.target_is_obscured(b, [(0, 0)], (0, 4), 0) is True
    # ... et le bit `AllowObscuredTargetByWalls` le leve, sans toucher a l'elevation
    assert TQ.target_is_obscured(b, [(0, 0)], (0, 4), WALL) is False


def test_indirect_fire_does_not_see_through_walls():
    """Le piege du trait : `IndirectFire` ne pose que `flags = 0`, et `r = flags | 4` garde le
    volet MURS. Un port qui traiterait le trait comme « aucune obstruction » rendrait `False` ici."""
    b = _col_board(walls=[(0, 2)])
    assert TQ.target_is_obscured(b, [(0, 0)], (0, 4), 0, caster_has_indirect_fire=True) is True


# ------------------------------------------------------------------------------------------------
# 3. Les gardes de `TargetingQuery$$GetTilesObscuringTerrain` et de la lambda `b__1`
# ------------------------------------------------------------------------------------------------
def test_config_flag_disables_the_whole_stage():
    """`BC.Targeting.EnableObscuringTerrain` (le champ `+0x10` du service `config` de
    `TargetingQuery$$Init`) est la PREMIERE garde -- il court-circuite avant tout calcul."""
    b = _col_board({(0, 2): 9})
    assert TQ.target_is_obscured(b, [(0, 1)], (0, 3), 0, enable_obscuring_terrain=False) is False


def test_friend_guards_short_circuit():
    """Les DEUX gardes « ami » : celle de la lambda (`IsFriend(target, caster)`) et celle de
    `GetTilesObscuringTerrain` (`IsFriendOrHasFriendlyUnitOnIt`). Une cible amie n'est jamais
    retiree par ce predicat."""
    b = _col_board({(0, 2): 9})
    assert TQ.target_is_obscured(b, [(0, 1)], (0, 3), 0, target_is_friend=True) is False
    assert TQ.target_is_obscured(b, [(0, 1)], (0, 3), 0,
                                 target_is_friend_or_has_friendly_unit=True) is False


def test_absent_channel_degrades_permissively():
    """Aucun canal d'elevation -> `board is None` -> aucun retrait. La degradation ne peut
    qu'ELARGIR la zone, jamais la retrecir : un faux NEGATIF declarerait une unite inoffensive."""
    assert TQ.target_is_obscured(None, [(0, 1)], (0, 3), 0) is False


def test_missing_tile_is_not_blocking():
    """`StateExtensions$$GetTileAt` nul -> la tuile n'existe pas -> elle ne bloque pas (le natif
    ne l'ajoute pas au set). Ici le trou est CREUSE au milieu de la colonne."""
    elev = {(0, r): 0 for r in range(9)}
    elev[(0, 2)] = 9
    del elev[(0, 2)]                              # plus de tuile a (0,2)
    b = MQ.PositionBoard(elev)
    assert TQ.target_is_obscured(b, [(0, 1)], (0, 3), 0) is False


# ------------------------------------------------------------------------------------------------
# 4. `PositionBoard` -- le substrat, et ce qu'il ne promet PAS
# ------------------------------------------------------------------------------------------------
def test_position_board_identity_and_bounds():
    """`id_at` rend la POSITION elle-meme : le natif compare des ENTITES-tuile (`tA == tB`), et
    deux coordonnees egales designent la meme entite. Le rectangle de `IsPositionInside` est le
    rectangle ENGLOBANT des tuiles publiees (`max + 1` sur chaque axe)."""
    b = MQ.PositionBoard({(0, 0): 1, (2, 3): 4}, {(2, 3): True})
    assert b.id_at(2, 3) == (2, 3) and b.id_at(1, 1) is None
    assert b.elevation((2, 3)) == 4 and b.elevation((9, 9)) is None
    assert b.is_wall((2, 3)) is True and b.is_wall((0, 0)) is False
    assert MQ.board_is_position_inside(b, (0, 0)) and MQ.board_is_position_inside(b, (2, 3))
    assert not MQ.board_is_position_inside(b, (3, 0)) and not MQ.board_is_position_inside(b, (0, 4))
    assert not MQ.board_is_position_inside(b, (-1, 0))


def test_absent_wall_map_sees_no_wall():
    """`is_wall_by_pos` ABSENT n'est pas « aucun mur » : c'est « le canal ne le dit pas ». Le port
    rend `False`, ce qui ELARGIT -- et c'est le seul sens de degradation admissible."""
    b = MQ.PositionBoard({(0, r): 0 for r in range(9)})
    assert b.is_wall((0, 2)) is False
    assert TQ.target_is_obscured(b, [(0, 0)], (0, 4), 0) is False


# ------------------------------------------------------------------------------------------------
# 5. Le CABLAGE -- l'attaque normale passe par le meme predicat
# ------------------------------------------------------------------------------------------------
def test_normal_attack_mask_carries_no_allow_bit():
    """Le preset de l'attaque normale vaut `0x4002` : ni bit 25 ni bit 26. Elle est donc soumise
    a l'obscurcissement comme n'importe quelle ability -- c'est ce qui justifie de poser le
    predicat AUSSI sur la branche `unit_weapon_range` d'`is_tile_in_range_of_any_ability`."""
    from engine.runner.abilities.targeting import NORMAL_ATTACK_TARGETING_OPTIONS
    rules = int(NORMAL_ATTACK_TARGETING_OPTIONS.rules)
    assert not rules & ELEV and not rules & WALL
    assert TQ.obscuring_type_for(rules) == TQ.OBSCURING_TYPE_ALL


def test_mask_predicts_the_two_witnesses_of_568():
    """La CONTRE-EPREUVE du modele, sur les deux temoins que #568 a isoles : `1161` (aucun bit,
    5 refus mesures) et `1147` (les deux bits, 40/40). Le masque doit les separer -- si les deux
    rendaient le meme `ObscuringType`, le port ne pourrait pas reproduire la mesure."""
    from engine.runner.abilities.targeting import targeting_options_for
    ot = {aid: TQ.obscuring_type_for(getattr(targeting_options_for(aid), "rules", None))
          for aid in (1161, 1147)}
    assert ot[1161] == TQ.OBSCURING_TYPE_ALL
    assert ot[1147] == TQ.OBSCURING_TYPE_NONE


def test_is_tile_in_range_applies_the_predicate_on_both_union_terms():
    """`AttackQuery$$GetAllTilesInAbilityRange(unit, positions, includeNormalAttack: true)` est
    l'UNION de l'attaque normale et des abilities, et les DEUX passent par
    `GetPossibleTargetsForOptions`. Sur une colonne ou la voisine du caster est haute de 2,
    `tauMarksman` (arme 3) ne doit plus atteindre `(0,3)` par son arme.

    On force le kit a l'ability SEULE puis a AUCUNE ability pour separer les deux termes."""
    from engine.services import ability_range as ar
    elev = {(0, r): 0 for r in range(9)}
    elev[(0, 1)] = 5                                  # voisine du caster, haute
    # arme seule (aucune ability) : la cible a d = 3 est OBSCURCIE -> hors zone
    assert ar.is_tile_in_range_of_any_ability((0, 0), (0, 3), "tauMarksman", ability_ids=[],
                                              elev_by_pos=elev) is False
    # sans canal d'elevation, le port ne retire rien (degradation NOMMEE)
    assert ar.is_tile_in_range_of_any_ability((0, 0), (0, 3), "tauMarksman", ability_ids=[],
                                              elev_by_pos=None) is True
