"""#448-r1-r1-r2 -- GARDE du SECOND BRAS de `IdunBattle.Operations.MoveUnitOperation$$IsLikeFlying`.

    bool IsLikeFlying(IEntity unit, MoveUnitOptions options) {
        if (UnitExtensions.IsLikeFlying(unit)) return true;      // BRAS 1 -- HasTrait(Flying|Burrow)
        var ov = options.<+0x8>;                                 // Nullable<PathfinderType>
        if (!ov.HasValue) return false;
        return ov.Value == PathfinderType.Fly;                   // BRAS 2 -- l'OVERRIDE d'OPTIONS
    }

Le probe (`probe_448_r1_r1_r2_fly_override.py`) MESURE ; ce fichier GARDE. Il verrouille les trois
choses qui peuvent deriver en silence :

  1. la table de verite des DEUX bras -- dont le `== 3` STRICT (un type DECORE comme
     `TeleportStrikeFly = 7` ne compte PAS comme volant ici) ;
  2. le fait que la feuille DSL `FlyUnit` pose l'override et que `MoveUnit` ne le pose PAS ;
  3. **la GARDE DE FIDELITE ANTI-PROPAGATION** : `_num_tiles_moved` ne doit JAMAIS accepter
     l'override. `RecordTilesMoved` compte `connectedPath`, produit par
     `IdunBattle.Core.Services.BattleQuery$$GetConnectedPathTo(entity, from, to)` -- TROIS
     arguments, ni options ni pathfinderType -- donc `tilesMovedThisTurn` est STRUCTURELLEMENT
     aveugle a l'override. « Propager par symetrie » serait une INFIDELITE, pas une amelioration.
"""
from __future__ import annotations

import inspect
import pathlib

import pytest

from engine.runner.operations import movement as MV
from engine.entities.pathfinding import pathfinders as PF
import engine.runner.abilities.behaviours.movement as BM


FLY = int(PF.PathfinderType.Fly)


@pytest.mark.parametrize("traits,override,expect", [
    # BRAS 1 seul -- les traits que lit `UnitExtensions$$IsLikeFlying`.
    (["Flying"], None, True),
    (["Burrow"], None, True),
    (["Hero", "Infiltrate", "Terrifying"], None, False),      # le kit REEL de `spaceHound` (Tjark)
    # BRAS 2 -- l'override d'options, sur une unite SANS trait de vol.
    (["Hero"], FLY, True),
    (["Hero"], int(PF.PathfinderType.Walk), False),
    (["Hero"], int(PF.PathfinderType.Beeline), False),
    # `TeleportStrikeFly = 7` : le natif compare `== 3` STRICTEMENT. Un type DECORE, meme « Fly »
    # par son nom, ne passe PAS ce test -- c'est ce que dit le decompile, pas une interpretation.
    (["Hero"], 7, False),
    (["Hero"], 13, False),
    # Les deux bras ensemble : le premier court-circuite.
    (["Flying"], FLY, True),
    (["Flying"], int(PF.PathfinderType.Walk), True),
])
def test_is_like_flying_table(traits, override, expect):
    assert bool(MV._is_like_flying(traits, override)) is expect


def test_operation_porte_le_champ_et_son_defaut_est_le_nullable_vide():
    """`None` = le `Nullable<PathfinderType>` VIDE, ce que passent tous les call-sites a options
    nulles (c'est-a-dire tout le port sauf la feuille `FlyUnit`)."""
    assert MV.MoveUnitOperation(1, (0, 0)).pathfinder_type_override is None
    assert MV.MoveUnitOperation(1, (0, 0), pathfinder_type_override=FLY
                                ).pathfinder_type_override == FLY


def test_seule_la_feuille_flyunit_pose_l_override():
    """`IdunBattleLogic.Entities.DSLBehaviors$$FlyUnit` alloue un `MoveUnitBehaviourOptions` de
    0x40 octets ZERO et n'y ecrit QUE `+0x08 = Nullable(3)` ; `DSLBehaviors$$MoveUnit` recoit les
    options de son appelant et les recopie telles quelles -- aucun call-site PORTE ne les pose."""
    src = pathlib.Path(BM.__file__).read_text(encoding="utf-8")
    assert "pathfinder_type_override=int(_pf.PathfinderType.Fly)" in src
    assert "pathfinder_type_override" not in src.split("class MoveUnit(")[-1]


def test_num_tiles_moved_n_accepte_PAS_l_override():
    """GARDE ANTI-PROPAGATION. `connectedPath` vient d'un appel a TROIS arguments
    (`BattleQuery$$GetConnectedPathTo(entity, from, to)`), donc `tilesMovedThisTurn` NE VOIT PAS
    l'override -- alors que `movementSteps`, tire de `path`, le voit. Les deux ne doivent pas etre
    alignes « pour faire propre »."""
    assert not any("override" in p for p in inspect.signature(MV._num_tiles_moved).parameters)
    assert any("override" in p for p in inspect.signature(MV._movement_steps).parameters)


def test_l_override_survit_a_la_relance_apres_deviation():
    """Le natif RECOPIE la struct `options` dans son appel recursif (il n'y touche que pour poser
    `+0x12 = 1` = `skipPreMoveTriggers`), donc l'override survit a un
    `OverrideMovementTargetOperation`. Lu dans la SOURCE : le rail de relance est un chemin
    d'exception que l'unitaire ne traverse pas sans monter un trigger deviant complet."""
    src = pathlib.Path(MV.__file__).read_text(encoding="utf-8")
    # Fenetre TEXTUELLE (l'appel porte des parentheses imbriquees, un split sur `)` couperait au
    # premier `int(ovr[0]`). La garde vise l'oubli du kwarg dans la relance, pas la semantique --
    # celle-la est couverte par la table de verite et par le volet live du probe.
    i = src.index("sub = MoveUnitOperation(")
    assert "pathfinder_type_override=self.pathfinder_type_override" in src[i:i + 400]
