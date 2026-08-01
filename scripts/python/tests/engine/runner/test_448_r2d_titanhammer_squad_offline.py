"""GARDE #448-r2d (OFFLINE PURE) -- `1573 TitanhammerSquad_TeleportingIn`, la SEULE des quatre
derivees d'`IdunBattle.Entities.Effects.Loki.ATeleportingEffect` a surcharger le vslot 0x748.

    IdunBattle.Entities.Effects.Loki.TitanhammerSquad_TeleportingInEffect$$GetCustomMovingEffectCondition
        = Contains(<Sel+0x78>, tgt) op_BitwiseOr IsAdjacentTiles(<Sel+0x78>, tgt)
          tgt = EffectTarget( EffectsFromUnitSource( EffectSource(EffectSelf@<Sel+0x38>),
                                                     0x623 = 1571 TitanhammerSquad_TargetTile ) )

CE QU'ELLE PROTEGE, et pourquoi chaque bloc peut regresser SILENCIEUSEMENT :

  1. **LES DEUX BRAS du OU.** Un port qui n'aurait garde que `Contains` raterait toute la couronne
     de la zone marquee ; un port qui n'aurait garde qu'`IsAdjacentTiles` raterait la tuile marquee
     elle-meme. Les deux sont exerces separement, et le bras NEGATIF (loin de la marque) avec.
  2. **La CHAINE de selecteurs**, pas seulement sa conclusion : une marque posee par une AUTRE
     source que celle de l'instance de 1573 ne doit RIEN valoir (`EffectSource(EffectSelf)` puis
     `EffectsFromUnitSource`). Sans ce maillon, deux escouades adverses partageraient leurs zones.
  3. **Le canal `dest_tile`** (`<Sel+0x78>` = TargetTiles, renseigne par
     `IdunBattle.Operations.MoveUnitOperation$$EvaluatePreMoveTriggers`) : absent -> les deux
     predicats natifs portent sur une liste VIDE, donc FAUX. Un port qui prendrait la position
     COURANTE a la place validerait la condition au mauvais moment.
  4. **Le substrat VIDE** : sans aucune tuile marquee (le cas par defaut du port, `1571` n'ayant
     AUCUN poseur -- l'active `1231` n'est pas portee), la condition doit rendre FAUX. C'est le
     regime dans lequel toute la couverture non montee tourne : il ne doit poser aucun marqueur.
  5. **`GetMovingEffectType` = `Nullable(0x626)`** et l'inscription des CINQ classes au registre.
  6. **`_TELEPORT_MOVE_EFFECTS`** (cliquet de NON-REGRESSION) :
     `IdunBattle.Entities.UnitExtensions$$SetMovedFlag` teste `0x40c`/`0x40b`/`0x4d9`/`0x4d6` et
     **PAS** `0x625`/`0x626` -- y ajouter cette famille poserait `UnitFlag.Teleported` sur un
     teleport que le natif ne compte pas (degradation PERMISSIVE, invisible).

Confrontation LIVE : `python scripts/python/probe_448_r2d_titanhammer_squad.py` (2 couples
board/seed, + contre-epreuve `--mutate` qui neutralise le vslot 0x748 et DOIT rougir).
RE : `docs/rl/case-448-r2-ateleporting-effect-family.md`. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import hexgeo                                                            # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType               # noqa: E402
from engine.entities import EffectsState                                 # noqa: E402
from engine.entities.effect_type import EffectType                       # noqa: E402
from engine.entities.effects import EffectFactory                        # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.components import _TELEPORT_MOVE_EFFECTS              # noqa: E402
from engine.runner.operations.effects import AddEffectOperation          # noqa: E402
from engine.runner.operations.triggers.base import TriggerEvent          # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS  # noqa: E402
from engine.runner.operations.triggers.loki.teleporting_in import (      # noqa: E402
    ATeleportingAddMovingOnPreMove,
    TeleportStrikeTeleportingInAddMovingOnPreMove,
    TitanhammerSquadMovingRemoveOnAfterMove,
    TitanhammerSquadTeleportingInAddMovingOnPreMove,
    TitanhammerSquadTeleportingInRemoveOnAfterMove,
    TitanhammerSquadTeleportingInRemoveOnPreUnitAbility,
    TitanhammerSquadTeleportingInRemoveOnUnitFinishedTurn,
    TITANHAMMER_SQUAD_MOVING, TITANHAMMER_SQUAD_TARGET_TILE,
    TITANHAMMER_SQUAD_TELEPORTING_IN)
from engine.runner.snapshot import load_state                            # noqa: E402

COLS, ROWS = 7, 7
CARRIER, OTHER_CASTER, FOE = 10, 40, 20
#: la tuile MARQUEE et trois destinations : elle-meme (bras `Contains`), une voisine (bras
#: `IsAdjacentTiles`) et une tuile a distance 3 (le bras NEGATIF).
MARK = (3, 3)
FAR = (0, 0)


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


@pytest.fixture
def stage():
    board = Board(_tiles(), adjacency="evenq")
    decision = {"currentPlayer": 1, "units": [
        {"id": CARRIER, "visualId": "deathBlightlord", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 1}, "effects": []},
        {"id": OTHER_CASTER, "visualId": "astarLysander", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 2}, "effects": []},
        {"id": FOE, "visualId": "ultraTitus", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 6, "row": 6}, "effects": []},
    ]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000}
                         for u in decision["units"]]}
    snapshot = {"units": [{"entityId": u["id"], "entityType": 1,
                           "stats": {"health": 1000, "movement": 3, "turnsStarted": 0},
                           "healthMax": 1000, "traits": [], "unitFlags": [],
                           "unitConfig": {"visualId": u["visualId"], "level": 50,
                                          "passiveAbilityLevel": 50, "activeAbilityLevel": 50,
                                          "abilityVariablesMultiplier": 100}}
                          for u in decision["units"]]}
    st = load_state(decision, observe, snapshot, board=board, ability_states=False)
    if st.effects is None:
        st.effects = EffectsState()
    return st, board


def _put_teleporting_in(st, uid: int, source: int) -> None:
    """`1573` sur `uid`, POSEE PAR `source` -- c'est ce `EffectComponent.SourceUnit` que
    `EffectSource(EffectSelf)` relit."""
    AddEffectOperation.execute(st, source=source, target=uid,
                               effect_type=TITANHAMMER_SQUAD_TELEPORTING_IN,
                               name=EffectType.TitanhammerSquad_TeleportingIn.name)


def _mark_tile(st, board, coord, source: int) -> None:
    """`1571` sur une TUILE. MEME chemin que le seed live (`snapshot._load_tile_effects` ->
    `EffectsState.add_effect(<id de tuile>, ...)`) : le natif pose l'effet sur l'entite-tuile via
    son `EffectsOwnedComponent`, ce que
    `IdunBattle.Entities.Pathfinding.TitanhammerSquadPathfinder$$IsValidTitanhammerSquadTargetTile`
    relit par `GetOwnedEffect(tile, state, 0x623)`."""
    st.effects.add_effect(int(board.id_at(coord[0], coord[1])), EffectFactory.create(
        {"name": EffectType.TitanhammerSquad_TargetTile.name,
         "effectType": TITANHAMMER_SQUAD_TARGET_TILE, "source": int(source), "remaining": 0}))


def _cond(st, dest, uid=CARRIER) -> bool:
    ev = TriggerEvent(int(EventTriggerType.PreUnitMove), uid, uid, ranged=False, profile=None,
                      dest_tile=(None if dest is None else tuple(dest)))
    return TitanhammerSquadTeleportingInAddMovingOnPreMove(uid)._custom_moving_condition(st, ev)


def _adjacent_to_mark(board):
    return board.coord(board.neighbours(board.id_at(MARK[0], MARK[1]))[0])


# ------------------------------------------------------------------ 1. LES DEUX BRAS + le negatif

def test_the_destination_ON_the_marked_tile_passes(stage):
    """Bras `Contains(<TargetTiles>, tgt)` -- la destination EST la tuile marquee."""
    st, board = stage
    _put_teleporting_in(st, CARRIER, OTHER_CASTER)
    _mark_tile(st, board, MARK, OTHER_CASTER)
    assert _cond(st, MARK) is True


def test_a_destination_ADJACENT_to_the_marked_tile_passes(stage):
    """Bras `IsAdjacentTiles(<TargetTiles>, tgt)` -- SANS lui, seule la tuile marquee elle-meme
    poserait le marqueur, alors que le pathfinder amene toute la couronne."""
    st, board = stage
    _put_teleporting_in(st, CARRIER, OTHER_CASTER)
    _mark_tile(st, board, MARK, OTHER_CASTER)
    adj = _adjacent_to_mark(board)
    assert adj != MARK
    assert _cond(st, adj) is True


def test_a_destination_far_from_every_mark_fails(stage):
    """Le bras NEGATIF : c'est LUI que la contre-epreuve `--mutate` du probe fait rougir. Un port
    qui collapserait le vslot 0x748 a `True` poserait `1574` sur un pas de marche quelconque."""
    st, board = stage
    _put_teleporting_in(st, CARRIER, OTHER_CASTER)
    _mark_tile(st, board, MARK, OTHER_CASTER)
    assert board.id_at(FAR[0], FAR[1]) not in \
        set(board.neighbours(board.id_at(MARK[0], MARK[1]))) | {board.id_at(MARK[0], MARK[1])}
    assert _cond(st, FAR) is False


# ------------------------------------------------------------------ 2. la CHAINE de selecteurs

def test_a_mark_posed_by_ANOTHER_source_does_not_count(stage):
    """`EffectSource(EffectSelf)` puis `EffectsFromUnitSource(<cette source>, 0x623)` : la marque
    doit venir de la MEME unite que celle qui a pose le `1573` porte. Sans ce maillon, la zone
    d'une escouade adverse (ou d'un second Lysander) vaudrait pour tout le monde."""
    st, board = stage
    _put_teleporting_in(st, CARRIER, OTHER_CASTER)
    _mark_tile(st, board, MARK, FOE)                 # marque posee par QUELQU'UN D'AUTRE
    assert _cond(st, MARK) is False


def test_without_any_mark_the_condition_is_false(stage):
    """LE REGIME PAR DEFAUT DU PORT : `1571` n'a AUCUN poseur (l'active `1231` n'est pas portee).
    La condition doit donc rendre FAUX partout -- et c'est bien pourquoi elle ne peut etre
    confrontee que sur un etat re-seede depuis le natif (cf. le probe)."""
    st, _board = stage
    _put_teleporting_in(st, CARRIER, OTHER_CASTER)
    assert _cond(st, MARK) is False
    assert _cond(st, FAR) is False


def test_without_the_teleporting_in_instance_the_condition_is_false(stage):
    """Pas d'instance de `1573` sur le porteur -> `EffectSource(EffectSelf)` ne resout rien."""
    st, board = stage
    _mark_tile(st, board, MARK, OTHER_CASTER)
    assert _cond(st, MARK) is False


# ------------------------------------------------------------------ 3. le canal `dest_tile`

def test_an_unthreaded_destination_is_false_not_the_current_position(stage):
    """`<Sel+0x78>` NON renseigne : le natif evaluerait `Contains`/`IsAdjacentTiles` sur une liste
    VIDE, donc FAUX. Le piege serait de retomber sur la position COURANTE -- ici le porteur est en
    (1,1), la marque en (3,3) : le test resterait vert. On le pose donc AVEC le porteur SUR la
    marque, ou la confusion se verrait."""
    st, board = stage
    _put_teleporting_in(st, CARRIER, OTHER_CASTER)
    _mark_tile(st, board, MARK, OTHER_CASTER)
    from engine.runner.components import set_unit_feet
    set_unit_feet(st, CARRIER, [MARK])
    assert _cond(st, None) is False, "le port lit la position COURANTE au lieu de la DESTINATION"


# ------------------------------------------------------------------ 4. registre et non-regression

def test_the_registry_holds_the_five_classes():
    got = [c.__name__ for c in EFFECT_TRIGGERS.get(TITANHAMMER_SQUAD_TELEPORTING_IN, [])]
    assert got == ["TitanhammerSquadTeleportingInRemoveOnAfterMove",
                   "TitanhammerSquadTeleportingInRemoveOnPreUnitAbility",
                   "TitanhammerSquadTeleportingInRemoveOnUnitFinishedTurn",
                   "TitanhammerSquadTeleportingInAddMovingOnPreMove"], got
    assert [c.event_id for c in EFFECT_TRIGGERS[TITANHAMMER_SQUAD_TELEPORTING_IN]] == [
        int(EventTriggerType.UnitAfterMove),        # On(0x04 = UnitAfterMove)
        int(EventTriggerType.PreUnitAbility),       # On(0x2a = PreUnitAbility)
        int(EventTriggerType.UnitFinishedTurn),     # On(0x28 = UnitFinishedTurn)
        int(EventTriggerType.PreUnitMove)]          # On(0x1f = PreUnitMove)
    assert [c.__name__ for c in EFFECT_TRIGGERS.get(TITANHAMMER_SQUAD_MOVING, [])] == \
        ["TitanhammerSquadMovingRemoveOnAfterMove"]
    assert TitanhammerSquadMovingRemoveOnAfterMove.effect_type == TITANHAMMER_SQUAD_MOVING
    for cls in (TitanhammerSquadTeleportingInRemoveOnAfterMove,
                TitanhammerSquadTeleportingInRemoveOnPreUnitAbility,
                TitanhammerSquadTeleportingInRemoveOnUnitFinishedTurn,
                TitanhammerSquadTeleportingInAddMovingOnPreMove):
        assert cls.effect_type == TITANHAMMER_SQUAD_TELEPORTING_IN


def test_the_moving_effect_type_is_the_1574_nullable():
    """`GetMovingEffectType` = `Nullable<EffectType>(0x626)` -- lu a l'octet
    (`local_res18[0] = 0x626` puis le ctor du `Nullable`)."""
    assert TitanhammerSquadTeleportingInAddMovingOnPreMove.MOVING_EFFECT_TYPE == 1574
    assert TitanhammerSquadTeleportingInAddMovingOnPreMove.MOVING_EFFECT_NAME == \
        EffectType.TitanhammerSquad_Moving.name


def test_only_TitanhammerSquad_overrides_the_0x748_vslot():
    """L'inventaire dit `TitanhammerSquad_TeleportingInEffect` SEULE. La base et la tranche 1
    doivent donc garder le conjonct NEUTRE."""
    base = ATeleportingAddMovingOnPreMove._custom_moving_condition
    assert TitanhammerSquadTeleportingInAddMovingOnPreMove._custom_moving_condition is not base
    assert TeleportStrikeTeleportingInAddMovingOnPreMove._custom_moving_condition is base


def test_the_titanhammer_family_stays_out_of_the_teleported_flag_test():
    """CLIQUET. `IdunBattle.Entities.UnitExtensions$$SetMovedFlag` teste `IsOwnerOfEffect` /
    `IsTargetOfEffect` sur `0x40c`, `0x40b`, `0x4d9` et `0x4d6` -- et RIEN d'autre. Ajouter
    0x625/0x626 « par symetrie » poserait `UnitFlag.Teleported` sur un teleport que le natif ne
    compte pas : degradation PERMISSIVE, sans erreur ni crash."""
    assert sorted(int(x) for x in _TELEPORT_MOVE_EFFECTS) == [1035, 1036, 1238, 1241]
