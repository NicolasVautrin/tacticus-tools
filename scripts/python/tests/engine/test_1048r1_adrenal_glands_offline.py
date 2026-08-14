"""#1048 (residu #1018-r1) -- GARDE OFFLINE d'`AdrenalGlands_Effect` (EffectType 0x419 = 1049) et
de toute la chaine `RangeBonus` du mouvement.

Le probe `probe_1048r1_adrenal_glands.py` MESURE contre le natif (`aiMovableTiles`) ; ce fichier
GARDE les proprietes qu'un rebase ou un refactor peuvent casser SANS qu'aucun test de mouvement
existant ne rougisse :

  1. le CABLAGE des deux registres (`EFFECT_CLASSES`, `ABILITY_INIT_OWNER_EFFECTS`) ;
  2. le RAYON DE SOUFFLE NUL -- une unite sans le passif rend `[]` de `get_range_bonus_for_unit`,
     donc `get_movable_tiles_for` est un no-op EXACT (c'est CE point qui rend l'ajout acceptable
     dans le foyer de tout le mouvement du moteur) ;
  3. `MovementRangeWithAppliedBonus` ne lit QUE `ReduceRange` -- un `ExtraRange` n'augmente JAMAIS
     la portee brute. Un port qui l'ajouterait serait vert sur presque tout, et FAUX ;
  4. `GetExtraReachableTiles` : la condition FILTRE, et les tuiles deja atteignables sont exclues ;
  5. la structure du bonus qu'`AdrenalGlandsEffect` produit, et sa degradation (contexte incomplet
     -> `None`, jamais un bonus INCONDITIONNEL, qui serait l'inverse exact du natif).

DECLENCHEUR : rejouer ce fichier pour toute tranche qui touche
`engine/services/movement_query.py`, `engine/services/range_bonus.py`,
`engine/entities/effects/base.py`, `engine/entities/effects/factory.py`,
`engine/entities/effects/loki/adrenal_glands.py`,
`engine/entities/pathfinding/{pathfinders,walk_pathfinder,tile_blocking,board}.py` ou
`engine/battle_query.py`.
"""
from __future__ import annotations

import hexgeo
from engine.entities.effects.base import BaseEffect
from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES
from engine.entities.effects.loki.adrenal_glands import AdrenalGlandsEffect
from engine.entities.effects.magnitude import ability_var
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.runner.state import State
from engine.services.movement_query import (get_extra_reachable_tiles,
                                            get_range_bonus_for_unit,
                                            movement_range_with_applied_bonus)
from engine.services.range_bonus import EffectRangeBonus, MovementBonusContext, RangeBonus


def _board(w=7, h=7, non_walkable=()):
    """Grille `w x h`, id = col * h + row, tout walkable sauf `non_walkable`.

    ⚠ `neighbours` est REMPLI : c'est la liste STOCKEE que lit `BasePathfinder$$AddNeighbours`
    (via `Board.base_add_neighbours`). Un board synthetique qui la laisse vide rend un pathfinding
    VIDE -- et un test bati dessus serait vert pour la mauvaise raison (mesure : la premiere
    version de ce fichier rendait `set()` et l'assertion l'a montre)."""
    def _id(c, r):
        return c * h + r
    tiles = []
    for c in range(w):
        for r in range(h):
            nb = [_id(nc, nr) for (nc, nr) in hexgeo.neighbors(c, r)
                  if 0 <= nc < w and 0 <= nr < h]
            tiles.append({"id": _id(c, r), "col": c, "row": r, "elevation": 0,
                          "walkable": (c, r) not in non_walkable, "isWall": False,
                          "neighbours": nb})
    return Board(tiles, adjacency="evenq")


def test_registres_cables():
    """Sans ces deux entrees le passif est MUET : l'instance seedee reste un dict inerte
    (`EFFECT_CLASSES`) et un porteur ne offline ne recoit rien (`ABILITY_INIT_OWNER_EFFECTS`)."""
    assert EFFECT_CLASSES.get("AdrenalGlands_Effect") is AdrenalGlandsEffect
    assert ABILITY_INIT_OWNER_EFFECTS.get("AdrenalGlands") == ["AdrenalGlands_Effect"]
    assert int(EffectType.AdrenalGlands_Effect) == 1049


def test_le_hook_est_None_par_defaut():
    """`BaseEffect.create_range_bonus_for_movement` -> `None` : c'est CE defaut qui rend le rayon
    de souffle nul. Un effet quelconque ne doit produire AUCUN bonus."""
    quelconque = BaseEffect("Pinned", effect_type=int(EffectType.Pinned))
    assert quelconque.create_range_bonus_for_movement(MovementBonusContext()) is None
    assert quelconque.range_bonus_for_movement(MovementBonusContext()) is None


def test_get_range_bonus_for_unit_sans_canal_rend_vide():
    """`state.effects` absent -> `[]`. Le consommateur (`get_movable_tiles_for`) est alors
    STRICTEMENT inchange -- exactement le regime natif quand `rangeBonuses` est vide."""
    st = State()
    assert get_range_bonus_for_unit(st, _board(), 1) == []


def test_movement_range_ne_lit_QUE_reduce_range():
    """`MovementQuery$$MovementRangeWithAppliedBonus` : la boucle ne touche que `ReduceRange`, et
    clampe a 0 (`Math.Max(0, range - v)`). Un `ExtraRange` n'a AUCUN effet ici -- c'est ce qui fait
    d'`AdrenalGlands` un ajout de TUILES et non un `+1 Mouvement`."""
    assert movement_range_with_applied_bonus(3, []) == 3
    assert movement_range_with_applied_bonus(3, None) == 3
    assert movement_range_with_applied_bonus(3, [RangeBonus(extra_range=1)]) == 3
    assert movement_range_with_applied_bonus(3, [RangeBonus(extra_range=9, reduce_range=1)]) == 2
    assert movement_range_with_applied_bonus(3, [RangeBonus(reduce_range=1),
                                                 RangeBonus(reduce_range=1)]) == 1
    assert movement_range_with_applied_bonus(1, [RangeBonus(reduce_range=5)]) == 0   # clamp


def test_range_bonus_for_movement_applique_le_gate_trigger():
    """`BaseEffect$$RangeBonusForMovement` : `Trigger != null` et qui ne passe pas -> `null`.
    INERTE sur le build (le seul implementeur rend `Trigger = null`), porte par fidelite -- un port
    qui l'omettrait laisserait passer un bonus conditionnel le jour ou il apparait, en silence."""
    class _Faux(BaseEffect):
        def __init__(self, trg):
            BaseEffect.__init__(self, "X", effect_type=1)
            self._trg = trg

        def create_range_bonus_for_movement(self, mctx):
            return EffectRangeBonus(trigger=self._trg, extra_range=2, reduce_range=3)

    assert _Faux(None).range_bonus_for_movement(None) == RangeBonus(extra_range=2, reduce_range=3)
    assert _Faux(lambda _m: False).range_bonus_for_movement(None) is None
    assert _Faux(lambda _m: True).range_bonus_for_movement(None).extra_range == 2


def test_get_extra_reachable_tiles_filtre_et_exclut_le_deja_atteignable():
    """`GetExtraReachableTiles` : (a) `extra_range <= 0` -> rien ; (b) les tuiles DEJA dans
    `defaultReachableTiles` sont exclues ; (c) la condition FILTRE. On part d'une seule tuile de
    base pour que le compte soit lisible."""
    b = _board()
    base = {b.id_at(3, 3)}
    rien = get_extra_reachable_tiles(b, base, 1, RangeBonus(extra_range=0), {}, None, [], None)
    assert rien == set()
    tout = get_extra_reachable_tiles(b, base, 1, RangeBonus(extra_range=1), {}, None, [], None)
    assert tout, "un ring-1 non vide est attendu sur une grille 7x7 pleine"
    assert b.id_at(3, 3) not in tout, "la tuile de base ne doit pas etre re-ajoutee"
    # (c) la MEME requete, condition = une seule position acceptee
    cible = b.coord(sorted(tout)[0])
    un = get_extra_reachable_tiles(b, base, 1,
                                   RangeBonus(extra_range=1,
                                              extra_range_condition=lambda p: p == cible),
                                   {}, None, [], None)
    assert un == {b.id_at(*cible)}
    assert len(un) < len(tout), "la condition doit RETRECIR l'ensemble, sinon elle ne filtre rien"


def test_le_bonus_produit_par_adrenal_glands():
    """`CreateRangeBonusForMovement` : `ExtraRange = extraMovement`, `ReduceRange = null`,
    `Trigger = null`, et une CONDITION non nulle (c'est elle, toute la mecanique)."""
    eff = AdrenalGlandsEffect("AdrenalGlands_Effect",
                              effect_type=int(EffectType.AdrenalGlands_Effect))
    st = State()
    b = _board()
    mctx = MovementBonusContext(state=st, board=b, unit_id=1)
    bonus = eff.create_range_bonus_for_movement(mctx)
    assert bonus is not None
    assert bonus.extra_range == int(ability_var("AdrenalGlands", "extraMovement",
                                                is_constant=True)) == 1
    assert bonus.reduce_range is None and bonus.trigger is None
    assert callable(bonus.extra_range_condition)


def test_degradation_contexte_incomplet():
    """Contexte sans board / sans state / sans unite -> `None`. Rendre un bonus SANS condition
    serait un `+extraMovement` INCONDITIONNEL, c'est-a-dire l'inverse exact du natif : on prefere
    ne rien rendre."""
    eff = AdrenalGlandsEffect("AdrenalGlands_Effect",
                              effect_type=int(EffectType.AdrenalGlands_Effect))
    st, b = State(), _board()
    assert eff.create_range_bonus_for_movement(None) is None
    assert eff.create_range_bonus_for_movement(MovementBonusContext()) is None
    assert eff.create_range_bonus_for_movement(
        MovementBonusContext(state=st, board=None, unit_id=1)) is None
    assert eff.create_range_bonus_for_movement(
        MovementBonusContext(state=st, board=b, unit_id=None)) is None
