"""GARDE #366-r1 (OFFLINE PURE) -- le VECTEUR DE POSE de `TunnelingHorror` (active 1011).

CE QU'ELLE PROTEGE. Avant ce foyer, un cast de 1011 etait offline un **NO-OP SILENCIEUX** : l'effet
`TunnelingHorror_PendingSummon` (1113) etait porte, mais rien ne le POSAIT -- il n'arrivait dans
`State.effects` que par le chemin de CHARGEMENT (`snapshot._load_tile_effects`). Ce qui manquait
n'etait pas l'effet, c'etait l'ETAT que sa pose cree : **une UNITE sans position**. Cet etat
n'existait cote port que pour les MACHINES OF WAR (hors-plateau par construction) et pour le
chargement d'une capture ou `decisionView` rend `pos = null` ; aucun ECRIVAIN offline ne le
produisait.

Les trois choses que ces tests figent, et pourquoi chacune peut regresser SILENCIEUSEMENT :

  1. **L'ECRIVAIN**. `set_unit_feet(state, uid, [])` doit RETIRER la `PositionComponent` **et**
     materialiser `feet = []`. Les deux vont ensemble : `get_unit_feet` retombe sur la
     `PositionComponent` quand `feet is None`, donc un `feet = None` laisserait l'unite sur le
     plateau alors meme que l'operation a « reussi ». C'est exactement ce que faisait la version
     precedente de l'ecrivain (`if len(uc.feet) <= 1: uc.feet = None`), et rien ne l'aurait signale.
  2. **LE GATE DYNAMIQUE**. `TunnelingHorrorAbility$$GetDynamicInvalidTargetReason` refuse une tuile
     DEJA marquee. C'est le seul consommateur du marqueur cote ciblage, et le seul observable qui
     discrimine « l'effet est pose » de « l'effet est emis » : `AddBondEffect` emet son trace
     INCONDITIONNELLEMENT (meme quand `AddEffectOperation` abandonne faute d'`EffectsState`), donc
     lire la trace ne prouve RIEN. On lit `state.effects.by_unit`, et on exige le CONTRE-BRAS
     (temoin non marque -> 0).
  3. **LES DEUX LITTERAUX DU REGISTRE** (`TARGETING_OPTIONS`, `ABILITY_ATTACK_TYPE`), transcrits du
     `$$.ctor` -- forme DIRECTE a 6 arguments, donc le litteral EST le masque effectif.

Mesure live de bout en bout (pose / seed / lecture par le gate / persistance / retrait) :
`python scripts/python/probe_366_r1_tunneling_horror.py`.
RE : `docs/rl/case-366-r1-tunneling-horror-pending-summon.md`. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import hexgeo                                                            # noqa: E402
from engine.entities import EffectsState                                 # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType  # noqa: E402
from engine.runner.abilities.behaviours import entities_from_state       # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES              # noqa: E402
from engine.runner.abilities.necrons import TunnelingHorrorAbility       # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.components import (PositionComponent, UnitComponent, get_main_tile,  # noqa: E402
                                      get_unit_feet, set_unit_feet)
from engine.runner.operations.remove_unit_from_tiles import RemoveUnitFromTilesOperation  # noqa: E402
from engine.runner.snapshot import load_state, snapshot                  # noqa: E402

TUNNELING = 1011                 # ActiveAbilityType.TunnelingHorror
PENDING = 1113                   # EffectType.TunnelingHorror_PendingSummon (0x459)
# `TunnelingHorrorAbility$$.ctor` -> `TargetingOptions..ctor(&opts, 0, &range, 1,
# 0x8000000001042, 0, 0)` : forme DIRECTE a 6 arguments -> le litteral EST le masque.
NATIVE_MASK = 0x8000000001042
COLS, ROWS = 7, 7
CASTER, ALLY, FOE = 10, 40, 20


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
def state():
    """`State` runner minimal : deux allies Necrons + un ennemi, `EffectsState` materialise (sans
    lui `AddEffectOperation` abandonne -- et `AddBondEffect` emettrait quand meme sa trace)."""
    board = Board(_tiles(), adjacency="evenq")
    decision = {"currentPlayer": 1, "units": [
        {"id": CASTER, "visualId": "necroDestroyer", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 0, "row": 3}, "effects": []},
        {"id": ALLY, "visualId": "necroOverlord", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 3}, "effects": []},
        {"id": FOE, "visualId": "necroWarden", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 6, "row": 6}, "effects": []},
    ]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000}
                         for u in decision["units"]]}
    st = load_state(decision, observe, board=board)
    if st.effects is None:
        st.effects = EffectsState()
    return st


def _tile_effects(st, tile_id) -> list:
    return [e for e in (st.effects.by_unit.get(int(tile_id)) or [])
            if int(getattr(e, "effect_type", -1)) == PENDING]


# ------------------------------------------------------------------ 1. l'ECRIVAIN d'empreinte

def test_set_unit_feet_empty_removes_position_and_materialises_empty_feet(state):
    """Le geste de base. `feet = []` MATERIALISE (surtout pas `None`) + `PositionComponent` retiree :
    c'est le collapse de `RemoveUnitFromTilesOperation$$Execute` (le natif met a zero le `TileId` de
    chaque pied, et `IterateTiles` saute les pieds sans tuile)."""
    e = state.get_entity(CASTER)
    assert get_unit_feet(state, CASTER) == [(0, 3)]
    assert set_unit_feet(state, CASTER, []) == []
    assert e.get_component(UnitComponent).feet == []       # materialise, PAS None
    assert e.get_component(PositionComponent) is None
    assert get_unit_feet(state, CASTER) == []
    assert get_main_tile(state, CASTER) is None


def test_set_unit_feet_nonempty_is_unchanged(state):
    """CONTRE-BRAS de non-regression : le chemin NOMINAL (>=1 tuile) garde son comportement --
    `feet = None` pour un pied unique, `PositionComponent` recalee sur la main tile."""
    e = state.get_entity(CASTER)
    assert set_unit_feet(state, CASTER, [(2, 2)]) == [(2, 2)]
    assert e.get_component(UnitComponent).feet is None     # un pied = cas NOMINAL
    pc = e.get_component(PositionComponent)
    assert (pc.col, pc.row) == (2, 2)
    assert set_unit_feet(state, CASTER, [(3, 3), (3, 4), (4, 3)]) == [(3, 3), (3, 4), (4, 3)]
    assert e.get_component(UnitComponent).feet == [(3, 3), (3, 4), (4, 3)]
    assert get_main_tile(state, CASTER) == (3, 3)          # main tile = feet[0]


# ------------------------------------------------------------------ 2. l'OPERATION

def test_operation_removes_the_unit_from_the_board_without_killing_it(state):
    """`RemoveUnitFromTilesOperation$$Execute` : l'unite quitte le PLATEAU. Ni PV touches, ni
    `alive = False` -- c'est ce qui la distingue de `RemoveUnitOperation` (despawn) et de la mort."""
    e = state.get_entity(CASTER)
    res = RemoveUnitFromTilesOperation.execute(state, CASTER)
    assert res == {"unit": CASTER, "tiles": [(0, 3)], "applied": True,
                   "remove_tile_from_unit": True}
    assert get_unit_feet(state, CASTER) == []
    assert e.get_component(PositionComponent) is None
    assert e.get_component(UnitComponent).alive is True     # HORS PLATEAU, pas mort


def test_operation_gates_return_none_without_mutating(state):
    """Les deux gates : entite inconnue, et entite qui n'est pas une unite (le natif LEVE une NRE
    la ou le port rend un refus TRACE -- ecart nomme dans la docstring de module de l'Operation)."""
    assert RemoveUnitFromTilesOperation.execute(state, 99999) is None
    assert RemoveUnitFromTilesOperation.execute(state, None) is None
    tile_entity = state.add_entity(4242)                    # une entite SANS `UnitComponent`
    assert RemoveUnitFromTilesOperation.execute(state, tile_entity.id) is None
    assert get_unit_feet(state, CASTER) == [(0, 3)]         # rien n'a bouge


def test_operation_declares_the_unported_branch_instead_of_lying(state):
    """`remove_tile_from_unit=False` n'est PAS representable apres le collapse (« les tuiles sont
    liberees mais l'unite y reste »). Le port le DIT (`applied: False`) au lieu de muter a moitie.
    Cette garde interdit qu'un futur passage le fasse muter comme si de rien n'etait."""
    res = RemoveUnitFromTilesOperation.execute(state, CASTER, remove_tile_from_unit=False)
    assert res["applied"] is False and res["remove_tile_from_unit"] is False
    assert get_unit_feet(state, CASTER) == [(0, 3)]         # AUCUNE mutation
    assert state.get_entity(CASTER).get_component(PositionComponent) is not None


# ------------------------------------------------------------------ 3. le CAST complet

def test_cast_removes_caster_and_bonds_the_targeted_tile_only(state):
    """Les TROIS `Execute` de `TunnelingHorrorAbility$$ExecuteBehaviour`, par leur OBSERVABLE :
    le caster quitte le plateau, et l'effet 1113 se pose sur la SEULE tuile visee, avec
    `source == bondedEntity == caster` et une duree PERMANENTE (options ZERO -> aucun
    `TurnsFromRounds`, `remaining = 0` cote live)."""
    dest, witness = _tid(4, 4), _tid(4, 5)
    res = TunnelingHorrorAbility().execute_behaviour(state, CASTER, dest)
    assert res["tile"] == dest and res["removed_from_tiles"]["tiles"] == [(0, 3)]
    e = state.get_entity(CASTER)
    assert get_unit_feet(state, CASTER) == [] and e.get_component(PositionComponent) is None
    assert e.get_component(UnitComponent).alive is True
    posed = _tile_effects(state, dest)
    assert len(posed) == 1
    assert posed[0].source == CASTER and posed[0].bonded == CASTER
    assert posed[0].remaining_turns in (0, None)            # PERMANENT
    assert _tile_effects(state, witness) == []              # une seule tuile marquee


def test_cast_without_a_resolvable_tile_poses_nothing(state):
    """Cast TILE-TARGET : sans tuile du board, ni retrait ni bond (le natif n'y arrive pas -- son
    masque porte `TargetIsTile`, le gate statique a deja refuse)."""
    res = TunnelingHorrorAbility().execute_behaviour(state, CASTER, None)
    assert res["tile"] is None and res["posed"] == []
    assert get_unit_feet(state, CASTER) == [(0, 3)]


def test_engine_survives_a_unit_with_no_position(state):
    """L'etat que la pose CREE doit rester lisible par le moteur : contexte DSL, snapshot et les
    deux accesseurs d'empreinte. C'est le foyer que ~150 call-sites `get_component(
    PositionComponent)` lisent -- ils gardent tous le `None`, et cette garde le verifie de bout en
    bout plutot que site par site."""
    TunnelingHorrorAbility().execute_behaviour(state, CASTER, _tid(4, 4))
    ctx = entities_from_state(state, ALLY, FOE)             # un AUTRE caster continue de jouer
    under = [u for u in ctx.units if u.get("id") == CASTER]
    assert len(under) == 1 and under[0].get("pos") is None and under[0].get("feet") == []
    snap = snapshot(state)["units"][CASTER]
    assert snap["pos"] is None and snap["alive"] is True


# ------------------------------------------------------------------ 4. le GATE DYNAMIQUE

def test_dynamic_gate_refuses_an_already_marked_tile_and_only_it(state):
    """LE DISCRIMINANT. `GetDynamicInvalidTargetReason` = `HasEffect(Get(target), 0x459)` -> la tuile
    marquee devient INVALIDE. Mesure live correspondante (E3) : sur 58 cibles legales du second
    porteur, la marquee est la seule exclue et le temoin adjacent reste legal."""
    dest, witness = _tid(4, 4), _tid(4, 5)
    ab = TunnelingHorrorAbility()
    assert ab.get_dynamic_invalid_target_reason(state, CASTER, dest) == 0      # avant la pose
    ab.execute_behaviour(state, CASTER, dest)
    assert ab.get_dynamic_invalid_target_reason(state, ALLY, dest) == int(TR.TargetMatchesDynamicRule)
    assert ab.get_dynamic_invalid_target_reason(state, ALLY, witness) == 0     # CONTRE-BRAS
    assert ab.get_dynamic_invalid_target_reason(state, ALLY, None) == 0


def test_dynamic_gate_is_wired_to_the_mask_bit():
    """Le gate n'est consulte QUE sous le bit `TargetMatchesDynamicRule` -- le port doit donc le
    poser, sinon la surcharge ci-dessus ne serait jamais appelee."""
    assert TunnelingHorrorAbility.TARGETING_OPTIONS.has(TR.TargetMatchesDynamicRule)


# ------------------------------------------------------------------ 5. les LITTERAUX du registre

def test_registry_entry_and_the_two_ctor_literals():
    """Les deux donnees obligatoires du registre, transcrites du `$$.ctor` (forme DIRECTE)."""
    assert ABILITY_CLASSES.get(TUNNELING) is TunnelingHorrorAbility
    opts = TunnelingHorrorAbility.TARGETING_OPTIONS
    assert int(opts.rules) == NATIVE_MASK
    # La somme est EXACTE : aucun bit residuel hors des quatre regles lues.
    assert int(opts.rules) == int(TR.TargetMatchesDynamicRule | TR.TargetIsTile
                                  | TR.TargetTileIsFree | TR.TargetIsNotSteppable)
    # `range` = `TargetingRange` statique `useWholeBoard` (copie de 0x18 octets par le ctor).
    assert opts.range is not None and opts.range.use_whole_board is True
    assert opts.self_cast is False
    # `AActiveAbility..ctor(this, &opts, 2)` -> AbilityAttackType.Others.
    assert ABILITY_ATTACK_TYPE.get(TUNNELING) == AbilityAttackType.Others
