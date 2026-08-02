"""#433-r3-r1 -- GARDE offline des CINQ noeuds DSL dont le natif lit l'EMPREINTE.

Le live (`test_433_r3_r1_dsl_footprint_live.py`) confronte `IsAdjacent` sur le SEUL porteur
multi-hex confrontable du build. Les quatre autres axes n'ont pas de porteur equivalent -- ils sont
donc gardes ici, contre le decompile, avec une CONTRE-EPREUVE par axe (un test qui ne peut pas
rougir ne garde rien).

CE QUE CHAQUE AXE MIRRORE (symboles verbatim) :
  * `IsAdjacent`    -- `IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$ShouldTrigger` ->
                       `BattleQuery$$AreEntitiesAdjacent(entity1, entity2)` =
                       `AreTilesAdjacent(GetTiles(e1), GetTiles(e2))`.
  * `IsInRange`     -- `IdunBattle.Entities.Triggers.IsInRangeAbilityTrigger$$ShouldTrigger` =
                       `GetMinDistance(SelectTiles(a), SelectTiles(b)) <= range`.
  * `IsSurrounding` -- **LA MEME CLASSE NATIVE** : `DSLTriggers$$IsSurrounding` et
                       `DSLTriggers$$IsInRange` allouent le meme pointeur de classe et appellent le
                       meme `.ctor`, arguments dans le meme ordre.
  * `IsCharging`    -- `IdunBattle.Core.Services.BattleQuery$$IsCharging` =
                       `AreEntitiesAdjacent(caster, target) && ChargedUnitIds(caster).Contains(id)`.
  * `MinDistance`   -- `IdunBattle.Entities.Formulas.MinDistanceFormula$$Calculate` = MIN sur
                       `SelectTiles(a) x SelectTiles(b)`.

Le montage geometrique est le meme partout, et il est DISCRIMINANT PAR CONSTRUCTION : la cible
occupe `[(2,1), (2,2), (3,2)]` et l'observateur est en `(4,2)` -- distance **1** du pied `(3,2)`,
distance **2** de la main tile `(2,1)`. Un port qui collapse sur la main tile repond l'inverse du
natif sur CHAQUE axe.
ASCII only.
"""
from __future__ import annotations

import pytest

import hexgeo
from engine.dsl import nodes as dsl
from engine.dsl.base import Const, DslContext
from engine.entities.formulas import MIN_DISTANCE_EMPTY, MinDistance
from engine.entities.triggers import IsAdjacent, IsCharging, IsInRange, IsSurrounding
from engine.services.movement_query import get_min_distance

FEET = [(2, 1), (2, 2), (3, 2)]          # empreinte 3 tuiles ; `feet[0]` = la MAIN TILE
OBSERVER = (4, 2)                        # d=1 de (3,2), d=2 de (2,1) -> STRICTEMENT discriminant


def _multi(uid=1, team=1):
    return {"id": uid, "team": team, "hp": 100, "alive": True,
            "pos": {"col": FEET[0][0], "row": FEET[0][1]}, "feet": list(FEET)}


def _mono(uid=2, team=2, pos=OBSERVER):
    return {"id": uid, "team": team, "hp": 100, "alive": True,
            "pos": {"col": pos[0], "row": pos[1]}}


def _ctx(caster, target, **kw):
    return DslContext(units=[caster, target], caster=caster, target=target, **kw)


def test_the_montage_is_discriminant():
    """Sans ce cran, tous les tests du fichier passeraient sur un montage DEGENERE."""
    assert hexgeo.distance(OBSERVER, FEET[0]) == 2, "l'observateur touche la MAIN TILE"
    assert min(hexgeo.distance(OBSERVER, f) for f in FEET) == 1, "aucun pied n'est adjacent"


# ------------------------------------------------------------------------------- IsAdjacent

def test_is_adjacent_reads_the_footprint():
    obs, tgt = _mono(), _multi()
    assert IsAdjacent(dsl.Caster(), dsl.Target()).should_trigger(_ctx(obs, tgt)) is True


def test_is_adjacent_main_tile_collapse_says_no(monkeypatch):
    """CONTRE-EPREUVE : le collapse d'avant rend FAUX sur le meme etat."""
    import engine.entities.triggers as T
    monkeypatch.setattr(T, "_feet", lambda u: [(u["pos"]["col"], u["pos"]["row"])] if u else [])
    obs, tgt = _mono(), _multi()
    assert IsAdjacent(dsl.Caster(), dsl.Target()).should_trigger(_ctx(obs, tgt)) is False


def test_is_adjacent_stays_false_when_no_foot_touches():
    """Le quantificateur UNIVERSEL de #433-r3 n'est pas relache par l'empreinte."""
    obs, tgt = _mono(pos=(7, 7)), _multi()
    assert IsAdjacent(dsl.Caster(), dsl.Target()).should_trigger(_ctx(obs, tgt)) is False


# -------------------------------------------------------------------------------- IsInRange

def test_is_in_range_measures_from_the_whole_footprint():
    """`GetMinDistance` = MIN sur les paires de tuiles -> `range = 1` suffit par le pied (3,2)."""
    obs, tgt = _mono(), _multi()
    assert IsInRange(dsl.Caster(), dsl.Target(), Const(1)).should_trigger(_ctx(obs, tgt)) is True


def test_is_in_range_main_tile_collapse_says_no(monkeypatch):
    import engine.entities.triggers as T
    monkeypatch.setattr(T, "_feet", lambda u: [(u["pos"]["col"], u["pos"]["row"])] if u else [])
    obs, tgt = _mono(), _multi()
    assert IsInRange(dsl.Caster(), dsl.Target(), Const(1)).should_trigger(_ctx(obs, tgt)) is False


def test_is_in_range_is_true_on_an_empty_selector():
    """`GetMinDistance` rend **-1** quand aucune paire n'a ete evaluee (`best == int.MaxValue`),
    donc `-1 <= range` -> VRAI. Le port rendait FAUX (un `any` sur un produit vide).

    ⚠ Ce quirk mord meme sur des unites MONO-tuile : c'est le seul des trois ecarts de ce noeud
    qui n'exige pas de multi-hex."""
    obs = _mono()
    ctx = DslContext(units=[obs], caster=obs, target=None)
    assert IsInRange(dsl.Caster(), dsl.Target(), Const(1)).should_trigger(ctx) is True


def test_get_min_distance_sentinel_is_minus_one_not_int_max():
    """`BattleQuery$$GetMinDistance` et `MovementQuery$$GetDistance` ont deux sentinels DIFFERENTS
    -- les substituer l'un a l'autre inverse le verdict d'`IsInRange` sur le vide."""
    assert get_min_distance([], [(0, 0)]) == -1
    assert get_min_distance([(0, 0)], []) == -1
    assert get_min_distance([(0, 0)], [(0, 2)]) == 2


# ---------------------------------------------------------------------------- IsSurrounding

def test_is_surrounding_is_the_same_native_class_as_is_in_range():
    """`DSLTriggers$$IsSurrounding` et `DSLTriggers$$IsInRange` allouent le MEME pointeur de classe
    et appellent le MEME `.ctor` (arguments dans le meme ordre). Le port ne peut donc PAS avoir deux
    corps -- l'un HERITE de l'autre, ce qui rend toute divergence impossible par construction."""
    assert issubclass(IsSurrounding, IsInRange)
    assert IsSurrounding.should_trigger is IsInRange.should_trigger


def test_is_surrounding_measures_from_the_whole_footprint():
    obs, tgt = _mono(), _multi()
    assert IsSurrounding(dsl.Caster(), dsl.Target(), Const(1)).should_trigger(_ctx(obs, tgt)) is True


# ------------------------------------------------------------------------------- IsCharging

def test_is_charging_reads_the_footprint():
    """Le terme geometrique est `AreEntitiesAdjacent(caster, target)` -- donc l'empreinte."""
    obs, tgt = _mono(), _multi()
    ctx = _ctx(obs, tgt, charged_units=lambda u: {tgt["id"]})
    assert IsCharging(dsl.Caster(), dsl.Target()).should_trigger(ctx) is True


def test_is_charging_main_tile_collapse_says_no(monkeypatch):
    import engine.entities.triggers as T
    monkeypatch.setattr(T, "_feet", lambda u: [(u["pos"]["col"], u["pos"]["row"])] if u else [])
    obs, tgt = _mono(), _multi()
    ctx = _ctx(obs, tgt, charged_units=lambda u: {tgt["id"]})
    assert IsCharging(dsl.Caster(), dsl.Target()).should_trigger(ctx) is False


def test_is_charging_keeps_the_identity_short_circuit():
    """`are_tiles_adjacent` court-circuite `tile1 == tile2` (#433-r1) : le port ecrivait ici
    `hexgeo.distance(pa, pb) != 1`, qui rend FAUX sur une paire identique. Ce noeud n'avait JAMAIS
    recu la correction #433-r1 -- il la recoit avec l'empreinte, par le meme foyer."""
    a = _mono(uid=1, team=1, pos=(3, 3))
    ctx = _ctx(a, a, charged_units=lambda u: {a["id"]})
    assert IsCharging(dsl.Caster(), dsl.Target()).should_trigger(ctx) is True


def test_is_charging_needs_the_charged_list():
    """Le 2e terme reste requis : adjacent NE SUFFIT PAS."""
    obs, tgt = _mono(), _multi()
    assert IsCharging(dsl.Caster(), dsl.Target()).should_trigger(_ctx(obs, tgt)) is False


# ------------------------------------------------------------------------------ MinDistance

def test_min_distance_reads_the_footprint():
    """`MinDistanceFormula$$Calculate` boucle sur `SelectTiles` -> l'element enumere est une TUILE
    (c'est ce que l'ancienne docstring du noeud lisait comme « une position par ENTITE »)."""
    obs, tgt = _mono(), _multi()
    assert MinDistance(dsl.Caster(), dsl.Target()).calculate(_ctx(obs, tgt)) == 1


def test_min_distance_main_tile_collapse_says_two(monkeypatch):
    import engine.entities.formulas as F
    monkeypatch.setattr(F, "_feet", lambda u: [(u["pos"]["col"], u["pos"]["row"])] if u else [])
    obs, tgt = _mono(), _multi()
    assert MinDistance(dsl.Caster(), dsl.Target()).calculate(_ctx(obs, tgt)) == 2


def test_min_distance_keeps_its_int_max_sentinel():
    """`MinDistanceFormula` rend `int.MaxValue` sur le vide -- PAS `-1` (qui est le sentinel de
    `BattleQuery$$GetMinDistance`). Deux fonctions natives, deux sentinels."""
    obs = _mono()
    ctx = DslContext(units=[obs], caster=obs, target=None)
    assert MinDistance(dsl.Caster(), dsl.Target()).calculate(ctx) == MIN_DISTANCE_EMPTY


# ------------------------------------------------------------------ le helper `_feet` lui-meme

def test_feet_falls_back_to_the_main_tile_and_says_so():
    """DEGRADATION NOMMEE : un dict sans `feet` (face DECISION, contexte de test) vaut la main tile
    seule. Exact pour toute unite mono-tuile, divergent au-dela -- c'est le residu du port, pas un
    mirror."""
    from engine.dsl.base import _feet
    assert _feet(_multi()) == FEET
    assert _feet(_mono()) == [OBSERVER]
    assert _feet({"id": 9}) == []
    assert _feet(None) == []
