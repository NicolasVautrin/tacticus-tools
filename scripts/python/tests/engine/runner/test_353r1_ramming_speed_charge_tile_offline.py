"""CLIQUET #353-r1 (volet a) -- `RammingSpeedAbility$$GetTileToMoveTo` : les DEUX proprietes que
le port n'avait pas, et qui CHANGENT la tuile rendue. OFFLINE, deterministe, aucun runner.

Ce que le decompile de
`IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$GetTileToMoveTo` dit :

    First( SortTilesByUtility(
               MovableTilesInRange(caster@0x48, casterTile@0x50,
                                   Direct(GetNumberConstant(0x16 = range)), 0, 0)
               op_BitwiseAnd  CanAddUnit(AdjacentTiles(target@0x60)),
               caster@0x48,
               UtilityDefinition( UtilityBucket([ WeightedUtility(7 = Tile, null),
                                                  WeightedUtility(0x36 = 54
                                                      RammingSpeed_MostAdjacentEnemies, null) ],
                                                null) ),
               null),
           1 )

Les deux ecarts que ce fichier verrouille :

  (1) **le 2e terme du bucket EXISTE et TRANCHE.** Avant #353-r1, `UTILITY_BY_TYPE` n'avait pas 54
      et `sort_tiles_by_utility` ne savait exprimer qu'UN type -- le port ne pouvait rendre que le
      classement `Tile(7)` SEUL. Sur carte plate `Tile(7)` est CONSTANT, donc ce classement
      retombe integralement sur l'ordre du selecteur source : la tuile rendue etait la 1re du pool,
      quel que soit le voisinage ennemi. Cas A ci-dessous : le natif prend une tuile a DEUX ennemis
      adjacents, `Tile(7)` seul en prend une a UN.

  (2) **l'ORDRE des operandes de l'intersection.** `GetTileToMoveTo` n'appelle PAS
      `DSLSelectors$$TilesUnitCanMoveToChargeTarget` (le helper que Waaagh/BlackRage utilisent) : il
      assemble les deux memes noeuds A LA MAIN avec `MovableTilesInRange` a GAUCHE, la ou le helper
      met `CanAddUnit(AdjacentTiles(target))`. `TargetsSelector$$op_BitwiseAnd(left, right)` garde
      l'ordre de GAUCHE et l'`OrderBy` de `SortTilesByUtilitySelector$$Select` est STABLE : a utilite
      EGALE, les deux ordres designent des tuiles DIFFERENTES. Cas B ci-dessous.

Chaque test porte sa MUTATION ADVERSARIALE : on rejoue le meme etat avec le terme (ou l'ordre) mute
et on exige que le resultat CHANGE. Un test qui passerait aussi sur la version mutee ne prouverait
rien.

NON COUVERT ICI (dit explicitement) : la confrontation LIVE (`probe_353r1_ramming_speed_charge_tile.py`
compare cette tuile a la position d'arrivee du caster apres un cast natif de 1059) et le regime ou
`Tile(7)` n'est PAS constant (board a relief) -- ce montage est plat EXPRES, pour que le terme qui
tranche soit nommable.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _ramming_speed_charge_montage import build_charge_montage   # noqa: E402

from engine import weights as W                                  # noqa: E402
from engine.dsl.base import Const                                # noqa: E402
from engine.entities.selectors import (AdjacentTiles, CanAddUnit, Caster,   # noqa: E402
                                       CasterTile, MovableTilesInRange, Target, TileIntersect)
from engine.runner.abilities.behaviours import entities_from_state          # noqa: E402
from engine.runner.abilities.orks import (RAMMING_SPEED_CONST_RANGE,        # noqa: E402
                                          RAMMING_SPEED_TILE_UTILITY,
                                          ramming_speed_charge_tiles_selector,
                                          ramming_speed_tile_to_move_to)
from engine.utilities.decider import (UtilityBucket, UtilityDefinition,     # noqa: E402
                                      WeightedUtility)
from engine.utilities.ramming_speed import RAMMING_SPEED_MOST_ADJACENT_ENEMIES   # noqa: E402
from engine.utilities.tile import (UTILITY_BY_TYPE, first_tile_by_utility,  # noqa: E402
                                   runner_tile_leaf_ctx)
from engine.utilities.utility_type import UtilityType                       # noqa: E402

MOVE_RANGE = 5             # `abilities.RammingSpeed.constants.range` (GetNumberConstant(0x16))

TILE_ONLY = UtilityDefinition.from_utility_type(int(UtilityType.Tile))
"""MUTATION ADVERSARIALE (1) : le bucket AMPUTE de son 2e terme = ce que le port savait exprimer
avant #353-r1."""


# ---------------------------------------------------------------- la feuille 54 elle-meme

def test_utility_type_54_is_registered_and_named():
    """`UtilityType.RammingSpeed_MostAdjacentEnemies` est resolvable par la base d'utilites, et sa
    valeur est celle du BUILD (`enums.tsv`), pas un litteral recopie : #252/#283 ont renumerote
    quatre enums. Le test compare donc MEMBRE a MEMBRE."""
    ut = int(UtilityType.RammingSpeed_MostAdjacentEnemies)
    assert ut in UTILITY_BY_TYPE, (
        "UtilityType.RammingSpeed_MostAdjacentEnemies (=%d) absent de UTILITY_BY_TYPE -- "
        "`UtilityDecider.CalculateUtility` leverait sur le 2e terme du bucket de "
        "RammingSpeedAbility$$GetTileToMoveTo" % ut)
    assert UTILITY_BY_TYPE[ut] is RAMMING_SPEED_MOST_ADJACENT_ENEMIES
    assert RAMMING_SPEED_MOST_ADJACENT_ENEMIES.UTILITY_TYPE == ut


def test_leaf_54_counts_adjacent_enemies_times_bc_weight():
    """La feuille = `#ennemis adjacents a la tuile CANDIDATE` x
    `Utilities.Default.RammingSpeed_MostAdjacentEnemies.RAMMINGSPEED_AdjacentEnemy`.

    La cle est celle RESOLUE au litteral IL2CPP (`probe_212_bc_key_literals.py`), pas devinee au
    prefixe ; le poids est une DONNEE de BC, jamais une constante de code -- on le relit ici au lieu
    de figer 20 dans l'assertion."""
    m = build_charge_montage((4, 3), move_range=MOVE_RANGE)
    wt = W.load()
    w = wt.sub("RammingSpeed_MostAdjacentEnemies", "RAMMINGSPEED_AdjacentEnemy")
    assert w, ("poids BC RAMMINGSPEED_AdjacentEnemy absent -- la feuille serait muette et le 2e "
               "terme du bucket inerte")
    ctx = runner_tile_leaf_ctx(m.state, m.caster_id)
    got = {m.board.coord(t): RAMMING_SPEED_MOST_ADJACENT_ENEMIES.evaluate(
        m.board.coord(t), {}, ctx, wt) for t in m.candidates}
    # Toute candidate touche la CIBLE (elle sort de `CanAddUnit(AdjacentTiles(Target))`) -> >= 1 x w.
    # (3,4) et (4,2) touchent EN PLUS le 2e ennemi pose en (4,3) -> 2 x w.
    assert got == {(2, 2): w, (2, 3): w, (3, 2): w, (3, 4): 2 * w, (4, 2): 2 * w}, got


def test_leaf_54_is_silent_without_subject():
    """`case.unit == null` : le natif deref `unit` dans `GetAdjacentEnemies` et LEVE ; aucun
    call-site porte n'y mene. La degradation choisie est 0.0, et elle est verrouillee ici pour
    qu'elle reste EXPLICITE (et non un effet de bord d'un ctx vide)."""
    wt = W.load()
    assert RAMMING_SPEED_MOST_ADJACENT_ENEMIES.evaluate((0, 0), {}, {}, wt) == 0.0
    assert RAMMING_SPEED_MOST_ADJACENT_ENEMIES.evaluate((0, 0), {}, {"is_spawning": True}, wt) == 0.0


# ---------------------------------------------------------------- le bucket a DEUX termes

def test_bucket_has_two_weighted_utilities_with_default_weight_one():
    """`WeightedUtility$$.ctor` : un `Nullable<Fix64>` VIDE vaut `Fix64.FromInt(1)` ;
    `UtilityBucket$$.ctor` : une difference minimale absente vaut 0. Les deux termes de
    `GetTileToMoveTo` sont construits avec un Nullable vide -> somme NUE."""
    b = RAMMING_SPEED_TILE_UTILITY.bucket
    assert [(w.utility_type, w.weight) for w in b.utilities] == [
        (int(UtilityType.Tile), 1.0),
        (int(UtilityType.RammingSpeed_MostAdjacentEnemies), 1.0)]
    assert b.min_utility_difference == 0.0
    assert len(RAMMING_SPEED_TILE_UTILITY.buckets) == 1, (
        "`UtilityDefinition$$.ctor` alloue un tableau d'UN bucket, et "
        "`SortTilesByUtilitySelector$$Select` ne lit que `Buckets[0]`")


def test_second_term_changes_the_chosen_tile():
    """CAS A -- le 2e terme TRANCHE.

    Board PLAT : `Tile(7)` vaut 0 sur les 5 candidates, donc le classement `Tile(7)` SEUL retombe
    sur l'ordre source et rend la 1re tuile du pool. Avec le bucket complet, les deux tuiles a DEUX
    ennemis adjacents passent devant."""
    m = build_charge_montage((4, 3), move_range=MOVE_RANGE)
    assert [m.board.coord(t) for t in m.candidates] == [(2, 2), (2, 3), (3, 2), (3, 4), (4, 2)], (
        "pool inattendu -- le montage ne teste plus ce qu'il annonce")

    shipped = ramming_speed_tile_to_move_to(m.state, m.caster_id, m.target_id, MOVE_RANGE)
    muted = m.board.coord(first_tile_by_utility(m.state, m.candidates, unit_id=m.caster_id,
                                                utility_definition=TILE_ONLY))
    assert shipped == (3, 4), shipped
    assert muted == (2, 2), muted
    assert shipped != muted, (
        "MUTATION ADVERSARIALE INEFFICACE : amputer le bucket de son 2e terme ne change pas la "
        "tuile -> ce montage ne prouve pas que 54 est porte")


def test_zero_weight_on_second_term_is_equivalent_to_amputation():
    """CONTRE-EPREUVE de la composition : c'est bien une somme PONDEREE. Un poids 0 sur le 2e terme
    (au lieu du `?? 1` natif) doit rendre EXACTEMENT le classement `Tile(7)` seul."""
    m = build_charge_montage((4, 3), move_range=MOVE_RANGE)
    zeroed = UtilityDefinition(UtilityBucket([
        WeightedUtility(utility_type=int(UtilityType.Tile)),
        WeightedUtility(utility_type=int(UtilityType.RammingSpeed_MostAdjacentEnemies), weight=0.0),
    ]))
    got = m.board.coord(first_tile_by_utility(m.state, m.candidates, unit_id=m.caster_id,
                                              utility_definition=zeroed))
    assert got == (2, 2), got


def test_unknown_utility_type_raises_instead_of_scoring_zero():
    """`UtilityDecider.CalculateUtility` LEVE sur un type hors base, au lieu de le compter 0 --
    sinon un terme non porte disparaitrait du classement SANS BRUIT (exactement la degradation
    silencieuse que #353-r1 corrige)."""
    m = build_charge_montage((4, 3), move_range=MOVE_RANGE)
    bogus = UtilityDefinition(UtilityBucket([WeightedUtility(utility_type=99999)]))
    with pytest.raises(KeyError):
        first_tile_by_utility(m.state, m.candidates, unit_id=m.caster_id,
                              utility_definition=bogus)


# ---------------------------------------------------------------- l'ORDRE des operandes

def test_intersection_puts_movable_tiles_on_the_left():
    """Structure : `MovableTilesInRange op_BitwiseAnd CanAddUnit(AdjacentTiles(target))`. Le helper
    `TilesUnitCanMoveToChargeTarget` (Waaagh) a l'ordre INVERSE -- si un jour quelqu'un le
    reutilise ici « parce que c'est le meme ensemble », ce test rougit."""
    sel = ramming_speed_charge_tiles_selector(MOVE_RANGE)
    assert isinstance(sel, TileIntersect)
    assert isinstance(sel.left, MovableTilesInRange), type(sel.left).__name__
    assert isinstance(sel.right, CanAddUnit), type(sel.right).__name__
    assert RAMMING_SPEED_CONST_RANGE == 0x16      # AbilityConstantType.range


def test_operand_order_changes_the_chosen_tile_on_ties():
    """CAS B -- l'ORDRE TRANCHE, bucket COMPLET.

    Le 2e ennemi est pose en (2,3) : (2,2) et (3,4) touchent alors DEUX ennemis chacune et sont ex
    aequo au sommet. Le tri etant STABLE, c'est l'ordre du selecteur source qui les departage --
    et les deux ordres ne coincident pas."""
    m = build_charge_montage((2, 3), move_range=MOVE_RANGE)
    ents = entities_from_state(m.state, m.caster_id, m.target_id)
    swapped = TileIntersect(CanAddUnit(AdjacentTiles(Target())),
                            MovableTilesInRange(Caster(), CasterTile(), Const(MOVE_RANGE),
                                                ignore_flags=False,
                                                ignore_units_on_tiles=False)).evaluate(ents)

    assert sorted(swapped) == sorted(m.candidates), (
        "les deux ordres doivent porter le MEME ensemble -- sinon on mesure une difference de "
        "POOL, pas d'ORDRE")
    assert [m.board.coord(t) for t in m.candidates] != [m.board.coord(t) for t in swapped], (
        "les deux ordres coincident sur ce montage -> il ne peut rien prouver")

    shipped = ramming_speed_tile_to_move_to(m.state, m.caster_id, m.target_id, MOVE_RANGE)
    other = m.board.coord(first_tile_by_utility(m.state, swapped, unit_id=m.caster_id,
                                                utility_definition=RAMMING_SPEED_TILE_UTILITY))
    assert shipped == (2, 2), shipped
    assert other == (3, 4), other
    assert shipped != other, (
        "MUTATION ADVERSARIALE INEFFICACE : intervertir les operandes ne change pas la tuile -> "
        "ce montage ne prouve pas que l'ordre natif est porte")


def test_empty_intersection_yields_no_tile():
    """Intersection VIDE -> None : le `MoveUnit` natif est alors no-op et
    `RammingSpeedAbility$$GetDynamicInvalidTargetReason` refuse le cast (`0x8000000`). `move_range`
    0 -> aucune tuile atteignable hors celle du caster."""
    m = build_charge_montage((4, 3), move_range=MOVE_RANGE)
    assert ramming_speed_tile_to_move_to(m.state, m.caster_id, m.target_id, 0) is None
