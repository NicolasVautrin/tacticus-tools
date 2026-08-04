"""OFFLINE #433-r4-r2-r1-r2-r2 -- les DEUX gardes << ami >> du predicat de LIGNE DE VUE.

Ce que ce fichier GARDE, et qui ne se lit nulle part ailleurs : les deux gardes de
`TargetingQuery$$GetPossibleTargetsForOptions` / `$$GetTilesObscuringTerrain` ne lisent PAS la meme
chose, et leur ASYMETRIE est ce qu'un port naif recabler-ait de travers.

    b__1(target) = !IsFriend(target, caster, state) && GetTilesObscuringTerrain(...).Count > 0
    GetTilesObscuringTerrain : ... && !IsFriendOrHasFriendlyUnitOnIt(target, caster, state) && ...

  * `IdunBattle.Entities.UnitExtensions$$IsFriend` compare deux `GetCurrentPlayer`, chacun rabattu
    sur `0` faute de joueur. Or `IdunBattle.Entities.EntityExtensions$$GetCurrentPlayer` ne branche
    que sur `PlayerEntity`, `FootEntity` et `UnitEntity` avant de retomber sur un
    `TryGetComponent<OwnerComponent>` que la `TileEntity` NE PORTE PAS : sur une TUILE elle ne
    resout donc PAS l'occupant, et la garde vaut `TeamId(caster) == Environment(0)`.
  * `IdunBattle.Entities.UnitExtensions$$IsFriendOrHasFriendlyUnitOnIt` passe, elle, par
    `IdunBattle.Entities.UnitExtensions$$GetUnit`, qui TESTE `TileEntity` et RESOUT l'occupant.

Le pendant LIVE (`test_433_r4_r2_r1_r2_r2_friend_gates_live.py`) mesure la consequence sur le
natif ; ce fichier-ci garde la LECTURE et le CABLAGE, sans runner.
"""
from __future__ import annotations

import pytest

from engine.services import ability_range as ar
from engine.services import movement_query as MQ
from engine.services import targeting_query as TQ

# Un couloir a UNE tuile haute EN (1,0) -- l'INDICE 1 de la ligne, le seul teste contre l'elevation
# du DEPART (`#433-r4-r2-r1-r2` : seuls les indices `1` et `Count-2` sont testes, une tuile haute au
# MILIEU d'une longue ligne ne bloque RIEN). Une haute en (2,0) n'obscurcirait que la cible (3,0)
# -- verifie a la calibration, et c'est ce qui rend ce substrat non devinable.
_ELEV = {(c, 0): (4 if c == 1 else 0) for c in range(6)}
_BOARD = MQ.PositionBoard(_ELEV, {})
_CASTER = (0, 0)
_TARGET = (4, 0)
#: `1161 TwinSmartMissileSystem` : aucun `AllowObscuredTarget*` -> `ObscuringType == 6`.
_RULES_OBSCURING = 0


def test_the_two_guards_do_not_read_the_same_thing():
    """L'ASYMETRIE, qui est le resultat de RE de cette tranche.

    `IsFriend` ne depend QUE de l'equipe du caster (elle ne resout pas l'occupant d'une tuile) ;
    `IsFriendOrHasFriendlyUnitOnIt` ne depend QUE de l'egalite des deux equipes. Un port qui les
    aurait rendues symetriques -- l'erreur naturelle, et celle que la fiche precedente induisait --
    ferait mordre `IsFriend` sur l'occupant et exempterait des tuiles que le natif RETIRE."""
    for caster_team in (0, 1, 2, 3):
        for occ in (None, 0, 1, 2, 3):
            g1, g2 = TQ.friend_gates_for_tile_target(caster_team, occ)
            assert g1 is (caster_team == TQ.TEAM_ENVIRONMENT), (caster_team, occ)
            assert g2 is (occ is not None and occ == caster_team), (caster_team, occ)


def test_the_environment_team_is_zero_and_that_is_why_isfriend_is_inert_in_our_runners():
    """`IdunBattle.Core.TeamId.Environment == 0`, et c'est AUSSI la valeur de repli d'un
    `GetCurrentPlayer` qui ne resout rien -- la coincidence qui rend `IsFriend` piegeuse.

    Nos runners declarent `Players = {p1: TeamId 1, p2: TeamId 2, env: TeamId 0}` et l'equipe
    Environment n'y porte AUCUNE unite : la garde y est donc INERTE. Ce test fige le fait qu'elle
    ne l'est pas PAR NATURE -- un caster d'equipe Environment desactiverait tout l'etage."""
    assert TQ.TEAM_ENVIRONMENT == 0
    assert TQ.friend_gates_for_tile_target(0, None) == (True, False)
    assert TQ.friend_gates_for_tile_target(1, None) == (False, False)


def test_an_unknown_team_channel_keeps_the_previous_behaviour():
    """Canal muet -> `(False, False)`, le statu quo d'avant la tranche. La degradation est
    RESTRICTIVE (le port retire plus que le natif) et c'est ASSUME : inventer une amitie sur une
    equipe qu'on n'a pas lue ferait ELARGIR la zone sans preuve."""
    assert TQ.friend_gates_for_tile_target(None, 1) == (False, False)
    assert TQ.friend_gates_for_tile_target(None, None) == (False, False)


def test_a_friendly_occupant_cancels_the_obscuring_set():
    """`GetTilesObscuringTerrain` rend l'ensemble VIDE sur une cible amie -- donc AUCUNE
    obstruction, quelle que soit la geometrie. Le meme couple (caster, cible) est obscurci quand
    la tuile est vide : c'est la GARDE qui fait la difference, pas le terrain."""
    assert TQ.target_is_obscured(_BOARD, [_CASTER], _TARGET, _RULES_OBSCURING) is True
    assert TQ.target_is_obscured(_BOARD, [_CASTER], _TARGET, _RULES_OBSCURING,
                                 target_is_friend_or_has_friendly_unit=True) is False
    assert TQ.get_tiles_obscuring_terrain(_BOARD, [_CASTER], _TARGET, _RULES_OBSCURING,
                                          target_is_friend_or_has_friendly_unit=True) == set()


def test_the_isfriend_guard_short_circuits_before_the_geometry():
    """La garde de `b__1` est EN AMONT de `GetTilesObscuringTerrain` : elle rend `false` sans meme
    tracer les lignes."""
    assert TQ.target_is_obscured(_BOARD, [_CASTER], _TARGET, _RULES_OBSCURING,
                                 target_is_friend=True) is False


@pytest.mark.parametrize("caster_team,occupant_team,expect_obscured", [
    (1, 1, False),      # allie -> le natif GARDE la tuile
    (1, 2, True),       # ennemi -> le natif la RETIRE
    (2, 2, False),
    (2, 1, True),
    (1, None, True),    # tuile VIDE -> il la retire
    (0, None, False),   # caster ENVIRONMENT -> `IsFriend` court-circuite tout
])
def test_ability_range_wires_both_guards(caster_team, occupant_team, expect_obscured):
    """LE CABLAGE : `ability_range._obscured` doit passer les deux gardes, calculees depuis
    `caster_team` + `team_by_pos`. Sans lui, les parametres du mirror resteraient a leur defaut et
    l'ecart RESTRICTIF subsisterait -- exactement l'etat d'avant cette tranche."""
    tbp = {} if occupant_team is None else {_TARGET: occupant_team}
    got = ar._obscured(_BOARD, _CASTER, _TARGET, _RULES_OBSCURING, "necroWarden",
                       caster_team=caster_team, team_by_pos=tbp)
    assert got is expect_obscured


def test_is_tile_in_range_forwards_the_channel_to_both_terms():
    """Les DEUX termes de l'union (`AttackQuery$$GetAllTilesInAbilityRange`) doivent recevoir le
    canal : l'attaque NORMALE et chaque ability. `necroWarden` porte une arme de portee 3 et
    `1005 AdaptiveStrategy` de portee 1 -- a `d = 4` seule l'ability whole-board pourrait porter,
    donc on se place a `d = 2` ou l'arme SEULE decide, et on verifie que la garde la debloque."""
    tgt = (2, 0)                                   # d = 2, DANS la portee d'arme, et OBSCURCIE
    assert ar.is_tile_in_range_of_any_ability(
        _CASTER, tgt, "necroWarden", elev_by_pos=_ELEV, ability_ids=[]) is False
    assert ar.is_tile_in_range_of_any_ability(
        _CASTER, tgt, "necroWarden", elev_by_pos=_ELEV, ability_ids=[],
        caster_team=1, team_by_pos={tgt: 1}) is True
    # ... et un occupant ENNEMI ne debloque RIEN (ce n'est pas l'occupation qui exempte).
    assert ar.is_tile_in_range_of_any_ability(
        _CASTER, tgt, "necroWarden", elev_by_pos=_ELEV, ability_ids=[],
        caster_team=1, team_by_pos={tgt: 2}) is False


def test_the_occupant_map_filters_the_dead_and_keeps_the_living():
    """`occupant_team_by_pos` lit `observeBattle.units` -- et FILTRE les morts, parce que le natif
    passe par `TileContentComponent$$IsFilled` : une depouille ne remplit plus sa tuile. C'est
    aussi pourquoi la source n'est PAS `decisionView`, qui GARDE les morts."""
    from engine.playbook.noncomparable._base import NCContext, occupant_team_by_pos
    ctx = NCContext(uid=1, origin=None, reach_nc=[], epos=[], fpos=[], plan={}, hp_cur_by_id={},
                    obs_units=[
                        {"squadId": 1, "teamId": 1, "col": 0, "row": 0, "isDead": False},
                        {"squadId": 2, "teamId": 2, "col": 1, "row": 0, "isDead": True},
                        {"squadId": 3, "teamId": None, "col": 2, "row": 0, "isDead": False},
                        {"squadId": 4, "teamId": 2, "col": None, "row": None, "isDead": False},
                    ])
    assert occupant_team_by_pos(ctx) == {(0, 0): 1}
