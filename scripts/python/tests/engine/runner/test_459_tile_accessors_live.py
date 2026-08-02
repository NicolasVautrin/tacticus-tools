"""#459 -- CONFRONTATION des ACCESSEURS DE TUILE sur une empreinte multi-hex.

CRITERE : « un accesseur `CasterTile()` / `TargetTile()` / `OwnerTile()` rend-il l'EMPREINTE que
rend le natif, et l'anneau qu'il alimente exclut-il ce que le natif exclut ? »

CE QUE DIT LE DECOMPILE (`rnca9r7q6c`), et que ce fichier confronte :

  * `IdunBattle.Entities.Selectors.CasterTileSelector$$Select` =
        entities.CasterPosition.Tiles ?? entities.CasterTile.ToList() ?? GetTiles(entities.Caster)
    -- AUCUNE branche `GetMainTile`. Idem `TargetTilesSelector$$Select`. Les slots sont identifies
    par `IdunBattleLogic.Entities.DSLTriggers$$get_CasterIsCasterTile` (`AreEqual(+0x48, +0x50)`) et
    `$$get_OwnerIsTargetTile` (`AreEqual(+0x78, +0x30)`).
  * `IdunBattle.DSL.TargetsSelector$$SelectTile` (SINGULIER) rend la PREMIERE tuile / `GetMainTile`,
    et c'est ce que lisent les consommateurs scalaires (`MovableTilesInRangeSelector`,
    `TilesBehindInLineSelector`, le referent de `SortByDistanceSelector`).
  * `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` retranche `SelectTiles(origin)`
    -- l'EMPREINTE ENTIERE -- alors que `DSLSelectors$$SurroundingTiles(origin, includeCenter: 0)`
    ne retranche que `Tiles(origin)` = `UnitsMainTilesSelector` = UNE tuile. Les deux verdicts sont
    donc OPPOSES sur le meme montage, et c'est la contre-epreuve la plus forte du fichier.

TROIS ORACLES NATIFS, tous INDEPENDANTS du port :
  * `boardGraph.tiles[].occupantUnitId` -- la projection du `TileContentComponent` : l'EMPREINTE ;
  * `observeBattle.units[]`, UNE LIGNE PAR PIED, portant l'`entityId` du pied : la MAIN TILE est
    celle du plus PETIT `entityId`, parce que `IdunBattle.Operations.AddUnitOperation$$Execute` cree
    les pieds dans la boucle meme qui les ajoute (`PlayerIdGenerator.Next()` est monotone) donc
    `entityId` croissant == ordre d'`AddFoot` == ordre de `_feet`, et
    `IdunBattle.Entities.EntityExtensions$$GetMainTileId` prend `_feet[0]`.
    ⚠ `decisionView.units[].pos` n'est PAS cet oracle : `decisionView` DEDUPLIQUE la projection
    par-pied et rend le DERNIER pied (mesure #R30, re-confirmee ici par un cran dedie) ;
  * `boardGraph.tiles[].neighbours` -- la liste d'adjacence STOCKEE (`ConnectivityComponent`), celle
    qu'enumere `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles`, donc l'ANNEAU natif.

LE MONTAGE N'EST PAS FORKE : la fixture de `test_433_r3_r1a_occupancy_live.py` est REUTILISEE telle
quelle (`ultraDreadnought` caste `DutyEternal` 1158 -> `ultraSmnDreadnought` sur 3 tuiles, avec son
critere de discriminance `_pick_anchor`). Le forker, ce serait forker le critere.

Aucun hook neuf. ASCII only.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import hexgeo
import pytest

from engine.dsl.base import Const, DslContext
from engine.entities.selectors.accessors import (CasterTile, OwnerTile, SelectTile, TargetTile)
from engine.entities.selectors.tiles import AdjacentTiles
from engine.entities.selectors.units import AdjacentUnits, SurroundingUnits
from engine.runner.abilities.behaviours.context import entities_from_state


def _mount_module():
    """Le montage multi-hex de #433-r3-r1a, IMPORTE (pas recopie)."""
    src = Path(__file__).with_name("test_433_r3_r1a_occupancy_live.py")
    spec = importlib.util.spec_from_file_location("_occupancy_case_459", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def accessor_case(rpc, build_runner):
    """La MEME fixture que #433-r3-r1a, appelee par sa fonction sous-jacente, plus les deux canaux
    natifs propres a cette tranche (la main tile publiee, et le voisinage stocke)."""
    mod = _mount_module()
    case = mod.occupancy_case.__wrapped__(rpc, build_runner)
    rid = case["rid"]
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True})
    su = next((u for u in (dv.get("units") or []) if u.get("id") == case["summon_id"]), None)
    if su is None:
        pytest.fail("le Galatian a disparu de decisionView", pytrace=False)
    case["decision_view_pos"] = (su["pos"]["col"], su["pos"]["row"])
    ob = rpc("observeBattle", {"runnerId": rid}) or {}
    rows = sorted((int(u.get("entityId") or 0), (u["col"], u["row"]))
                  for u in (ob.get("units") or [])
                  if u.get("squadId") == case["summon_id"] and u.get("col") is not None)
    if len(rows) < 2:
        pytest.fail(f"observeBattle ne projette pas les pieds du Galatian : {rows}", pytrace=False)
    case["native_feet_by_entity_id"] = [p for _e, p in rows]
    case["native_main_tile"] = rows[0][1]              # `_feet[0]` = plus petit entityId
    bg = rpc("boardGraph", {"runnerId": rid}) or {}
    case["native_neighbours"] = {
        (t["col"], t["row"]): list(t.get("neighbours") or []) for t in (bg.get("tiles") or [])}
    case["native_coord_of"] = {int(t["id"]): (t["col"], t["row"]) for t in (bg.get("tiles") or [])}
    return case


def _ctx(case, caster_id=None, target_id=None):
    ents = entities_from_state(case["state"],
                               caster_id if caster_id is not None else case["attacker_id"],
                               target_id if target_id is not None else case["summon_id"])
    return DslContext(units=ents.units, caster=ents.caster, target=ents.target,
                      board=case["board"])


def test_regime_is_strictly_discriminant(accessor_case):
    """Sans ce cran, tout le fichier passerait sur un montage DEGENERE (unite a UN pied)."""
    case = accessor_case
    assert len(case["feet"]) == 3 and len(set(case["feet"])) == 3
    att = case["attacker_pos"]
    dists = [hexgeo.distance(f, att) for f in case["feet"]]
    assert min(dists) == 1 and dists[0] >= 2, (
        f"attaquant a {dists} des pieds {case['feet']} -- les deux index coincideraient")


# ------------------------------------------------ ORACLE 1 : l'empreinte, contre le TileContent

def test_target_tile_returns_exactly_the_native_footprint(accessor_case):
    """`TargetTilesSelector$$Select` -> `GetTiles(Target)`. L'oracle est
    `boardGraph.tiles[].occupantUnitId`, que le natif remplit sur les TROIS pieds."""
    case = accessor_case
    native = sorted(t for t, uid in case["native_occ"].items() if uid == case["summon_id"])
    got = sorted(TargetTile().evaluate(_ctx(case)))
    assert len(native) == 3, f"l'oracle natif ne voit pas 3 pieds : {native}"
    assert got == native, f"TargetTile() = {got}, natif = {native}"


def test_caster_and_owner_tile_return_the_footprint_of_their_carrier(accessor_case):
    """Les deux autres accesseurs, sur le MEME porteur multi-hex (le Galatian devient le caster)."""
    case = accessor_case
    native = sorted(t for t, uid in case["native_occ"].items() if uid == case["summon_id"])
    ctx = _ctx(case, caster_id=case["summon_id"])
    assert sorted(CasterTile().evaluate(ctx)) == native
    assert sorted(OwnerTile().evaluate(ctx)) == native


# --------------------------------------------- ORACLE 2 : la main tile, contre la PositionComponent

def test_select_tile_agrees_with_the_native_first_foot(accessor_case):
    """`TargetsSelector$$SelectTile` = `GetMainTile` = `_feet[0]`. L'oracle est la ligne
    `observeBattle` de plus petit `entityId` (monotonie du `PlayerIdGenerator`, cf. l'en-tete).
    C'est ce qui rend l'elargissement INERTE chez les consommateurs scalaires."""
    case = accessor_case
    assert SelectTile(TargetTile()).evaluate(_ctx(case)) == case["native_main_tile"]
    ctx = _ctx(case, caster_id=case["summon_id"])
    assert SelectTile(CasterTile()).evaluate(ctx) == case["native_main_tile"]
    assert TargetTile().evaluate(_ctx(case)) == case["native_feet_by_entity_id"], \
        "l'ORDRE des pieds doit etre celui d'`AddFoot`, pas un tri de position"


def test_decision_view_pos_is_not_the_main_tile(accessor_case):
    """Cran d'ORACLE : `decisionView` deduplique la projection par-pied et rend le DERNIER pied.
    S'en servir comme oracle de main tile ferait passer un port FAUX (mesure #R30, re-confirmee
    ici) -- et c'est exactement l'erreur que ce fichier a commise avant d'etre corrige."""
    case = accessor_case
    feet = case["native_feet_by_entity_id"]
    assert case["decision_view_pos"] == feet[-1] != feet[0], (
        f"decisionView.pos={case['decision_view_pos']} vs pieds {feet}")


def test_select_tile_preserves_the_pre_459_scalar_reading(accessor_case):
    """NON-REGRESSION : avant #459 les consommateurs scalaires lisaient `_pos(target)`.
    `snapshot._load_feet` recale la `PositionComponent` sur `feet[0]`, donc `SelectTile` rend
    EXACTEMENT la meme tuile -- l'elargissement ne deplace aucun consommateur scalaire."""
    case = accessor_case
    from engine.dsl.base import _pos
    ctx = _ctx(case)
    assert SelectTile(TargetTile()).evaluate(ctx) == _pos(ctx.target)


def test_the_main_tile_is_strictly_inside_the_footprint(accessor_case):
    """Cran de non-degenerescence des deux oracles : ils ne disent PAS la meme chose."""
    case = accessor_case
    native = {t for t, uid in case["native_occ"].items() if uid == case["summon_id"]}
    assert case["native_main_tile"] in native and len(native) > 1


# ------------------------------------- ORACLE 3 : l'anneau, contre la liste d'adjacence STOCKEE

def test_adjacent_tiles_node_agrees_with_the_stored_neighbourhood(accessor_case):
    """`AdjacentTilesSelector$$Select` = union de `GetAdjacentTiles(t)` sur `SelectTiles(origin)`,
    MOINS `SelectTiles(origin)`. L'oracle est `boardGraph.tiles[].neighbours` -- la liste stockee
    qu'enumere `TileQuery$$IterateAdjacentTiles`, jamais une couronne recalculee."""
    case = accessor_case
    feet = [t for t, uid in case["native_occ"].items() if uid == case["summon_id"]]
    coord = case["native_coord_of"]
    expected = set()
    for f in feet:
        for nid in case["native_neighbours"].get(f, []):
            if int(nid) in coord:
                expected.add(coord[int(nid)])
    expected -= set(feet)
    got = {case["board"].coord(t) for t in AdjacentTiles(TargetTile()).evaluate(_ctx(case))}
    assert expected, "l'oracle natif rend un voisinage vide -- montage non concluant"
    assert got == expected, f"anneau du port {sorted(got)} != natif {sorted(expected)}"


def test_adjacent_tiles_node_drops_every_foot(accessor_case):
    """Le `if (!tiles.Contains(a))` du natif : les pieds sont voisins entre eux et sortent donc de
    l'anneau. C'est INOBSERVABLE hors multi-hex."""
    case = accessor_case
    got = {case["board"].coord(t) for t in AdjacentTiles(TargetTile()).evaluate(_ctx(case))}
    assert not (got & set(case["feet"])), f"des pieds restent dans l'anneau : {got & set(case['feet'])}"
    # ... et ils y SERAIENT sans l'exclusion : au moins un pied est voisin stocke d'un autre
    coord = case["native_coord_of"]
    linked = [(a, b) for a in case["feet"] for b in case["feet"] if a != b
              and b in {coord[int(n)] for n in case["native_neighbours"].get(a, [])
                        if int(n) in coord}]
    assert linked, "les pieds ne sont pas voisins stockes -- l'exclusion serait indiscernable"


# ------------------------------ LES DEUX EXCLUSIONS, RECIPROQUES sur le MEME etat et le MEME rayon

def test_adjacent_units_excludes_the_multihex_origin_itself(accessor_case):
    """`AdjacentUnits(TargetTile())` centre sur le Galatian : il ne peut PAS s'y trouver -- ses
    trois pieds sont retranches par `AdjacentTilesSelector`."""
    case = accessor_case
    got = [u["id"] for u in AdjacentUnits(TargetTile(), Const(1)).select(_ctx(case))]
    assert case["summon_id"] not in got, f"l'origine multi-hex ressort de son propre anneau : {got}"


def test_surrounding_units_keeps_the_multihex_origin(accessor_case):
    """RECIPROQUE, MEME etat, MEME rayon : `- Tiles(origin)` = `GetMainTile` par ENTITE, donc UNE
    seule tuile est retranchee et l'origine multi-hex SE selectionne par un pied secondaire.
    Retrancher toute l'empreinte ici serait une seconde erreur, pas une correction."""
    case = accessor_case
    got = [u["id"] for u in SurroundingUnits(TargetTile(), Const(1)).select(_ctx(case))]
    assert case["summon_id"] in got, (
        f"le Galatian devrait se selectionner lui-meme sous SurroundingUnits : {got}")


def test_adjacent_units_takes_the_attacker_through_a_secondary_foot(accessor_case):
    """Le correctif d'ORIGINE mord enfin sur un centre venu de `TargetTile()` : l'attaquant est a
    d=1 d'un pied NON-ANCRE et d>=2 de la main tile."""
    case = accessor_case
    got = [u["id"] for u in AdjacentUnits(TargetTile(), Const(1)).select(_ctx(case))]
    assert case["attacker_id"] in got, (
        f"attaquant@{case['attacker_pos']} absent de AdjacentUnits(TargetTile()) "
        f"pour feet={case['feet']} : {got}")


def test_collapsed_accessor_would_lose_the_attacker_and_gain_the_target(accessor_case,
                                                                       monkeypatch):
    """CONTRE-EPREUVE de l'axe precedent : l'accesseur SCALAIRE d'avant #459 rate l'attaquant ET
    ramene la cible (son pied secondaire touche sa propre main tile). Les DEUX symptomes."""
    case = accessor_case
    import engine.entities.selectors.accessors as A
    monkeypatch.setattr(A.TargetTile, "select",
                        lambda self, ctx: [case["native_main_tile"]], raising=True)
    got = [u["id"] for u in AdjacentUnits(TargetTile(), Const(1)).select(_ctx(case))]
    assert case["attacker_id"] not in got, "le collapse devrait PERDRE l'attaquant"
    assert case["summon_id"] in got, "le collapse devrait ramener la cible elle-meme"
