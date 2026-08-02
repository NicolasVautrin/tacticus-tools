"""#433-r3-r1a -- GARDE offline de la RESOLUTION D'OCCUPANT et de l'ORIGINE geometrique.

La tranche precedente (#433-r3-r1) a fait lire l'EMPREINTE aux cinq noeuds de GEOMETRIE
(`IsAdjacent`, `IsInRange`, `IsSurrounding`, `IsCharging`, `MinDistance`). Celle-ci ferme l'autre
moitie : les SELECTEURS, dont le foyer commun est « quelle unite occupe cette tuile ».

CE QUE CHAQUE AXE MIRRORE (symboles verbatim, lus sur `rnca9r7q6c`) :

  * OCCUPANT -- `IdunBattle.DSL.TargetsSelector$$SelectUnit(entity, selectionType)` (surcharge ENTITE) :
        if (EntityExtensions.IsUnitFoot(e) || EntityExtensions.IsTile(e))
            e = UnitExtensions.GetUnit(e, state);
        return (e != null && IsUnit(e) && MatchesUnitSelectionType(e, selectionType, state)) ? e : null;
    et `IdunBattle.Entities.UnitExtensions$$GetUnit` sur une TUILE lit son `TileContentComponent`
    (`IsFilled` -> `state.GetEntity(content)`) puis BOUCLE, parce que le contenu d'une tuile est
    l'entite-PIED (`IdunBattle.Entities.Blueprints$$UnitFoot` -> `IdunBattle.Core.FootEntity`) que la
    surcharge PIED re-resout en son unite. => n'importe quel pied resout en l'unite.
    Le consommateur DSL est `IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select` ->
    `IdunBattle.DSL.TargetsSelector$$SelectAllUnits` / `$$SelectUniqueUnits`.

  * ORIGINE -- `IdunBattle.Core.Services.BattleQuery.u003CIterateAdjacentTilesu003Ed__95$$MoveNext` et
    `...u003CIterateSurroundingTilesu003Ed__117$$MoveNext` ouvrent TOUTES DEUX par
        foreach (tile in EntityExtensions.IterateTiles(entity, state))
    => le voisinage/disque d'une entite multi-hex est l'UNION de celui de ses pieds.

  * EXCLUSION DU CENTRE -- `IdunBattleLogic.Entities.DSLSelectors$$SurroundingTiles`, branche
    `includeCenter == 0` : `SurroundingTiles(origin, 1, ...) op_Subtraction Tiles(origin)`, et
    `Tiles` = `IdunBattle.Entities.Selectors.UnitsMainTilesSelector$$Select` = `GetMainTile`.
    => on ne retranche QUE la main tile ; les pieds secondaires de l'origine RESTENT dans l'anneau.

  * OBSCURCISSEMENT -- `IdunBattle.Core.Services.TargetingQuery$$IsTargetUnitObscured` :
        foreach (tile in IterateTiles(target, state))
            if (!IsTargetTileObscured(from, tile, onlyWalls)) return false;
        return true;
    => obscurcie ssi TOUTES les tuiles le sont. Le referent `from`, lui, est un `GetMainTile`
    (`IdunBattle.Entities.Selectors.UnobscuredEntitiesSelector$$Select`) -- l'elargir serait une
    SECONDE erreur.

  * EFFET DE TUILE -- `IdunBattle.Entities.Triggers.IsUnitOnTileEffectTrigger$$ShouldTrigger` :
        foreach (tile in IterateTiles(unit, state)) if (HasOneOfEffects(tile, ...)) return true;
    => existentiel sur les pieds.

Chaque axe porte sa CONTRE-EPREUVE (le collapse d'avant, rejoue par monkeypatch de `_feet`, doit
INVERSER le verdict) : un test qui ne peut pas rougir ne garde rien.
ASCII only.
"""
from __future__ import annotations

import pytest

import hexgeo
from engine.dsl import nodes as dsl
from engine.dsl.base import (Const, DslContext, _main_tile, _occupants_by_tile, _origin_tiles,
                             _within)
from engine.entities.pathfinding.board import Board
from engine.entities.selectors.accessors import SurroundingTiles
from engine.entities.selectors.units import (AdjacentUnits, SurroundingUnits, Units,
                                             UnitsOnTilesWithEffect, Unobscured)
from engine.entities.triggers import HasUnit

COLS, ROWS = 9, 9

# Empreinte 3 tuiles ; `feet[0]` EST la main tile (mirror `GetMainTile` = 1er pied).
FEET = [(2, 1), (2, 2), (3, 2)]
# d=1 du pied (3,2), d=2 de la main tile (2,1) -> STRICTEMENT discriminant.
OBSERVER = (4, 2)


def _flat_board() -> Board:
    tiles, tid, idof = [], 1, {}
    for c in range(COLS):
        for r in range(ROWS):
            idof[(c, r)] = tid
            tid += 1
    for (c, r), i in idof.items():
        tiles.append({"id": i, "col": c, "row": r, "elevation": 0, "tileDefId": "Grass",
                      "isTemporary": False, "isWall": False, "walkable": True,
                      "neighbours": [], "occupantUnitId": None})
    return Board(tiles, adjacency="evenq")


def _multi(uid=1, team=1, feet=None):
    fs = list(feet or FEET)
    return {"id": uid, "team": team, "hp": 100, "alive": True,
            "pos": {"col": fs[0][0], "row": fs[0][1]}, "feet": fs}


def _mono(uid=2, team=2, pos=OBSERVER):
    return {"id": uid, "team": team, "hp": 100, "alive": True,
            "pos": {"col": pos[0], "row": pos[1]}}


def _collapse_to_main_tile(monkeypatch):
    """CONTRE-EPREUVE : rejoue l'indexation par MAIN TILE que ce commit remplace.

    Patche `_feet` dans CHAQUE module qui l'a importe par nom (`from ...dsl.base import _feet`) --
    patcher le seul `engine.dsl.base` laisserait `units.py` sur l'ancienne reference et rendrait la
    contre-epreuve VERTE pour rien (mesure : 1 faux vert sur 2 axes au premier jet)."""
    import engine.dsl.base as B
    import engine.entities.selectors.units as U
    import engine.entities.triggers as T
    flat = lambda u: ([(u["pos"]["col"], u["pos"]["row"])] if u and u.get("pos") else [])  # noqa: E731
    for m in (B, U, T):
        monkeypatch.setattr(m, "_feet", flat)


def test_the_montage_is_discriminant():
    """Sans ce cran, tout le fichier passerait sur un montage DEGENERE."""
    assert hexgeo.distance(OBSERVER, FEET[0]) == 2, "l'observateur touche la MAIN TILE"
    assert min(hexgeo.distance(OBSERVER, f) for f in FEET) == 1, "aucun pied n'est adjacent"
    b = _flat_board()
    assert b.id_at(*OBSERVER) is not None and all(b.id_at(*f) is not None for f in FEET)


# ------------------------------------------------------------------- le foyer, en tant que tel

def test_occupants_index_maps_every_foot_to_the_unit():
    """`TileContentComponent` est rempli sur CHAQUE pied ; `GetUnit` re-resout le pied en l'unite."""
    u = _multi()
    occ = _occupants_by_tile([u])
    assert set(occ) == set(FEET)
    assert all(occ[f] is u for f in FEET)


def test_occupants_index_keeps_the_alive_filter():
    """#57m : un mort n'est plus DEBOUT sur ses tuiles (`KillUnit` les libere)."""
    dead = _multi()
    dead["alive"] = False
    assert _occupants_by_tile([dead]) == {}


def test_origin_tiles_is_the_footprint_and_main_tile_is_the_first_foot():
    """Mirror `EntityExtensions$$IterateTiles` / `$$GetMainTile`, plus le domaine MIXTE natif."""
    u = _multi()
    assert _origin_tiles(u) == FEET
    assert _main_tile(u) == FEET[0]
    assert _origin_tiles(OBSERVER) == [OBSERVER]          # position
    assert _origin_tiles([FEET[0], FEET[1], FEET[0]]) == [FEET[0], FEET[1]]   # liste, dedoublonnee
    assert _origin_tiles(None) == [] and _origin_tiles(True) == []


def test_origin_tiles_resolves_a_tile_id_through_the_board():
    b = _flat_board()
    tid = b.id_at(*OBSERVER)
    assert _origin_tiles(tid, b) == [OBSERVER]
    assert _origin_tiles(999999, b) == []


# ------------------------------------------------------- `Units` : l'occupant par n'importe quel pied

def test_units_resolves_a_secondary_foot_tile():
    """`Units(<tuile sous un pied secondaire>)` rend l'unite -- le natif lit le TileContentComponent."""
    b = _flat_board()
    tgt, obs = _multi(), _mono()
    ctx = DslContext(units=[tgt, obs], caster=obs, target=tgt, board=b)
    from engine.entities.selectors.accessors import FixedTileIds
    sel = Units(FixedTileIds([b.id_at(*FEET[2])]))         # (3,2) = PIED NON-ANCRE
    assert [u["id"] for u in sel.select(ctx)] == [tgt["id"]]


def test_units_main_tile_collapse_sees_the_secondary_foot_empty(monkeypatch):
    b = _flat_board()
    tgt, obs = _multi(), _mono()
    ctx = DslContext(units=[tgt, obs], caster=obs, target=tgt, board=b)
    from engine.entities.selectors.accessors import FixedTileIds
    sel = Units(FixedTileIds([b.id_at(*FEET[2])]))
    _collapse_to_main_tile(monkeypatch)
    assert sel.select(ctx) == []


def test_units_dedups_a_unit_spanning_two_selected_tiles():
    """`SelectUniqueUnits` (ArraySet) : deux pieds selectionnes -> UNE entree.

    ⚠ Residu `#433-r3-r1a-r1` : le natif a AUSSI un regime `unique == 0` (`SelectAllUnits`, sans
    dedoublonnage) que le port ne modelise pas -- il n'etait pas atteignable avant ce commit."""
    b = _flat_board()
    tgt = _multi()
    ctx = DslContext(units=[tgt], caster=None, target=tgt, board=b)
    from engine.entities.selectors.accessors import FixedTileIds
    sel = Units(FixedTileIds([b.id_at(*FEET[1]), b.id_at(*FEET[2])]))
    assert [u["id"] for u in sel.select(ctx)] == [tgt["id"]]


def test_has_unit_sees_a_secondary_foot_tile():
    """`HasUnit` passe par le meme foyer (`_units_on` -> `_occupants_by_tile`)."""
    b = _flat_board()
    tgt = _multi()
    ctx = DslContext(units=[tgt], caster=None, target=tgt, board=b)
    from engine.entities.selectors.accessors import FixedTileIds
    assert HasUnit(FixedTileIds([b.id_at(*FEET[2])])).should_trigger(ctx) is True
    assert HasUnit(FixedTileIds([b.id_at(7, 7)])).should_trigger(ctx) is False


def test_has_unit_main_tile_collapse_says_no(monkeypatch):
    b = _flat_board()
    tgt = _multi()
    ctx = DslContext(units=[tgt], caster=None, target=tgt, board=b)
    from engine.entities.selectors.accessors import FixedTileIds
    node = HasUnit(FixedTileIds([b.id_at(*FEET[2])]))
    _collapse_to_main_tile(monkeypatch)
    assert node.should_trigger(ctx) is False


# ----------------------------------------------- `_within` : les DEUX bouts lisent les pieds

def test_within_takes_a_unit_whose_secondary_foot_is_in_range():
    """OBSERVATEUR mono a (4,2) : d=1 du pied (3,2), d=2 de la main tile."""
    tgt, obs = _multi(), _mono()
    got = _within([tgt], obs, 1)
    assert [u["id"] for u in got] == [tgt["id"]]


def test_within_main_tile_collapse_drops_it(monkeypatch):
    tgt, obs = _multi(), _mono()
    _collapse_to_main_tile(monkeypatch)
    assert _within([tgt], obs, 1) == []


def test_within_expands_a_multi_hex_CENTER_over_all_its_feet():
    """L'autre bout : le CENTRE est multi-hex, l'unite balayee est mono."""
    ctr, obs = _multi(), _mono()
    assert [u["id"] for u in _within([obs], ctr, 1)] == [obs["id"]]


def test_within_center_exclusion_removes_only_the_main_tile():
    """`- Tiles(origin)` = `UnitsMainTilesSelector` : les pieds SECONDAIRES du centre restent dans
    l'anneau, donc un centre multi-hex se SELECTIONNE LUI-MEME. Retrancher toute l'empreinte serait
    une seconde erreur (piege nomme par la fiche #433-r3-r1 Sec.7)."""
    ctr = _multi()
    assert [u["id"] for u in _within([ctr], ctr, 1)] == [ctr["id"]]


def test_within_is_unchanged_on_mono_hex_units():
    """NON-REGRESSION du cas nominal : formule identique terme a terme hors multi-hex."""
    a, b_, c = _mono(uid=1, pos=(4, 4)), _mono(uid=2, pos=(4, 5)), _mono(uid=3, pos=(7, 7))
    got = [u["id"] for u in _within([a, b_, c], a, 1)]
    assert got == [b_["id"]]                                     # centre exclu, hors-portee exclu
    got_inc = [u["id"] for u in _within([a, b_, c], a, 1, include_center=True)]
    assert sorted(got_inc) == [a["id"], b_["id"]]


def test_adjacent_units_node_reads_the_footprint():
    """Le noeud complet (`AdjacentUnits`), pas seulement son helper."""
    b = _flat_board()
    tgt, obs = _multi(), _mono()
    ctx = DslContext(units=[tgt, obs], caster=obs, target=tgt, board=b)
    got = AdjacentUnits(dsl.Caster(), Const(1)).select(ctx)
    assert [u["id"] for u in got] == [tgt["id"]]


def test_surrounding_units_node_reads_the_footprint():
    b = _flat_board()
    tgt, obs = _multi(), _mono()
    ctx = DslContext(units=[tgt, obs], caster=obs, target=tgt, board=b)
    got = SurroundingUnits(dsl.Caster(), Const(1)).select(ctx)
    assert [u["id"] for u in got] == [tgt["id"]]


# ----------------------------------------------- `SurroundingTiles` : origine + exclusion du centre

def test_surrounding_tiles_unions_the_disks_of_every_foot():
    b = _flat_board()
    tgt = _multi()
    ctx = DslContext(units=[tgt], caster=None, target=tgt, board=b)
    got = set(SurroundingTiles(dsl.Target(), Const(1), include_center=True).select(ctx))
    expect = set()
    for f in FEET:
        for p in hexgeo.disk(f[0], f[1], 1):
            t = b.id_at(*p)
            if t is not None:
                expect.add(t)
    assert got == expect


def test_surrounding_tiles_excludes_only_the_main_tile():
    b = _flat_board()
    tgt = _multi()
    ctx = DslContext(units=[tgt], caster=None, target=tgt, board=b)
    got = set(SurroundingTiles(dsl.Target(), Const(1)).select(ctx))
    assert b.id_at(*FEET[0]) not in got, "la main tile DOIT sortir"
    assert b.id_at(*FEET[1]) in got and b.id_at(*FEET[2]) in got, \
        "les pieds SECONDAIRES restent : `- Tiles(origin)` ne retranche qu'UNE tuile"


def test_surrounding_tiles_main_tile_collapse_loses_the_other_disks(monkeypatch):
    b = _flat_board()
    tgt = _multi()
    ctx = DslContext(units=[tgt], caster=None, target=tgt, board=b)
    node = SurroundingTiles(dsl.Target(), Const(1), include_center=True)
    full = set(node.select(ctx))
    _collapse_to_main_tile(monkeypatch)
    assert set(node.select(ctx)) < full


# ------------------------------------------------------------------- `UnitsOnTilesWithEffect`

def test_units_on_tiles_with_effect_is_existential_over_feet():
    b = _flat_board()
    tgt = _multi()
    iced = b.id_at(*FEET[2])                                  # UNE seule tuile porte l'effet
    ctx = DslContext(units=[tgt], caster=None, target=tgt, board=b,
                     tile_has_effect=lambda tid, et: tid == iced and et == 0x11)
    got = UnitsOnTilesWithEffect(dsl.Target(), 0x11).select(ctx)
    assert [u["id"] for u in got] == [tgt["id"]]


def test_units_on_tiles_with_effect_main_tile_collapse_says_no(monkeypatch):
    b = _flat_board()
    tgt = _multi()
    iced = b.id_at(*FEET[2])
    ctx = DslContext(units=[tgt], caster=None, target=tgt, board=b,
                     tile_has_effect=lambda tid, et: tid == iced and et == 0x11)
    node = UnitsOnTilesWithEffect(dsl.Target(), 0x11)
    _collapse_to_main_tile(monkeypatch)
    assert node.select(ctx) == []


# ------------------------------------------------------------------------------- `Unobscured`

def _elev_board(high) -> Board:
    tiles, tid, idof = [], 1, {}
    for c in range(COLS):
        for r in range(ROWS):
            idof[(c, r)] = tid
            tid += 1
    for (c, r), i in idof.items():
        tiles.append({"id": i, "col": c, "row": r, "elevation": (4 if (c, r) in high else 0),
                      "tileDefId": "Grass", "isTemporary": False, "isWall": False,
                      "walkable": True, "neighbours": [], "occupantUnitId": None})
    return Board(tiles, adjacency="evenq")


FROM = (0, 1)                      # tireur
HIDDEN_FOOT, CLEAR_FOOT = (0, 3), (1, 3)   # les DEUX a distance 2 du tireur, adjacents entre eux
RIDGE_HALF = {(0, 2)}              # crete qui ne couvre QUE le pied-ancre
RIDGE_FULL = {(0, 2), (1, 2)}      # crete qui couvre les DEUX pieds


def test_unobscured_montage_is_discriminant():
    """Les deux pieds sont a distance EXACTEMENT 2 (le seul regime que la v1 du port modelise) --
    sans ce cran, `test_unobscured_keeps_a_unit_with_one_clear_foot` passerait pour la mauvaise
    raison (`is_target_tile_obscured` rend False hors dist 2, y compris a dist 3)."""
    assert hexgeo.distance(FROM, HIDDEN_FOOT) == 2 and hexgeo.distance(FROM, CLEAR_FOOT) == 2
    assert hexgeo.distance(HIDDEN_FOOT, CLEAR_FOOT) == 1


def test_unobscured_keeps_a_unit_with_one_clear_foot():
    """`IsTargetUnitObscured` = ET sur TOUTES les tuiles -> `return false` au premier degagement.

    Montage : le tireur est en (0,1) ; la cible occupe (0,3) [ANCRE] et (1,3). La crete (0,2) est la
    tuile intermediaire de (0,3) seule, donc l'ancre est cachee et (1,3) reste vu (ses DEUX mids
    (0,2)/(1,2) ne passent pas ensemble le seuil) -> le natif GARDE la cible."""
    b = _elev_board(RIDGE_HALF)
    caster = _mono(uid=9, team=1, pos=FROM)
    tgt = _multi(uid=1, team=2, feet=[HIDDEN_FOOT, CLEAR_FOOT])
    ctx = DslContext(units=[caster, tgt], caster=caster, target=tgt, board=b)
    from engine.battle_query import is_target_tile_obscured
    elev = {k: t.get("elevation", 0) for k, t in b.by_coord.items()}
    assert is_target_tile_obscured(FROM, HIDDEN_FOOT, elev) is True, "montage : l'ancre DOIT etre cachee"
    assert is_target_tile_obscured(FROM, CLEAR_FOOT, elev) is False, "montage : (1,3) DOIT etre vu"
    got = Unobscured(dsl.UnitSet([tgt]), dsl.Caster()).select(ctx)
    assert [u["id"] for u in got] == [tgt["id"]]


def test_unobscured_main_tile_collapse_drops_it(monkeypatch):
    b = _elev_board(RIDGE_HALF)
    caster = _mono(uid=9, team=1, pos=FROM)
    tgt = _multi(uid=1, team=2, feet=[HIDDEN_FOOT, CLEAR_FOOT])
    ctx = DslContext(units=[caster, tgt], caster=caster, target=tgt, board=b)
    node = Unobscured(dsl.UnitSet([tgt]), dsl.Caster())
    _collapse_to_main_tile(monkeypatch)
    assert node.select(ctx) == []


def test_unobscured_still_excludes_a_fully_hidden_unit():
    """Le filtre n'est pas relache : TOUTES les tuiles cachees -> exclue."""
    b = _elev_board(RIDGE_FULL)
    caster = _mono(uid=9, team=1, pos=FROM)
    tgt = _multi(uid=1, team=2, feet=[HIDDEN_FOOT, CLEAR_FOOT])
    ctx = DslContext(units=[caster, tgt], caster=caster, target=tgt, board=b)
    assert Unobscured(dsl.UnitSet([tgt]), dsl.Caster()).select(ctx) == []
