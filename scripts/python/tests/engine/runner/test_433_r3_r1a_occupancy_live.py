"""#433-r3-r1a -- CONFRONTATION de la RESOLUTION D'OCCUPANT sur une empreinte multi-hex.

CRITERE : « une tuile occupee par un pied NON-ANCRE resout-elle en son unite, comme le fait le
natif ? » -- et, corollaire, « les selecteurs DSL qui balaient l'occupation la voient-ils ? »

L'ORACLE NATIF EST DIRECT, sans cast d'ability. Il y en a DEUX, independants :

  * `boardGraph.tiles[].occupantUnitId` -- c'est la projection du `TileContentComponent` que
    `IdunBattle.Entities.UnitExtensions$$GetUnit` lit pour resoudre une tuile en unite. Si le natif
    remplit ce slot sur CHAQUE pied, alors « n'importe quel pied resout en l'unite » est mesure,
    pas deduit.
  * `aiMovableTiles` -- la meme donnee EN ACTION : `IdunBattle.Entities.Pathfinding.IgnoreEverythingPathfinder$$WeightCost`
    et `$$IgnoreTerrainPathfinder$$WeightCost` appellent `TileContentComponent$$IsFilled`, donc une
    tuile sous un pied secondaire doit etre INFRANCHISSABLE. Deux canaux natifs distincts qui
    doivent dire la meme chose.

LE MONTAGE DEGENERE, ET POURQUOI CELUI-CI NE L'EST PAS. A UN pied, l'index par main tile et l'index
par empreinte COINCIDENT : toute mesure sur une unite mono-tuile est INCAPABLE de les separer. On
reutilise donc le porteur multi-hex de #433-r3-r1 -- `ultraDreadnought` (MoW du pool) caste
`DutyEternal` (1158) et fait apparaitre `ultraSmnDreadnought` (Galatian) sur **3 tuiles** -- et son
helper `_pick_anchor`, qui porte le CRITERE de discriminance (attaquant a d=1 d'un pied, d>=2 de
`feet[0]` ET de `feet[-1]`). Le forker, ce serait forker le critere.

⚠ PIEGE DE HARNAIS herite de #433-r3-r1 : un refus par `decisionView.toActivate` a la signature
IDENTIQUE a une mesure (`ok: true, mutated: false`, `casterReason = NoBrokenTargetingRule`). Ce
fichier n'y est PAS expose : il ne caste rien apres le spawn -- il LIT deux canaux d'etat. La seule
action mutante est le cast de 1158, dont l'echec est explicitement fail-fast (`spawned`).

CE QUI N'EST PAS COUVERT ICI : la chaine END-TO-END « une AoE endommage une unite par son pied
secondaire ». Elle exige un porteur de splash deterministe dans le pool ET une geometrie ou le
splash passe par un pied non-ancre ; les deux porteurs `AdjacentEnemies(TargetTile())` purs du port
(PlasmaGrenade, Stikkbomb) sont npc/summon. Residu nomme dans la case-doc.

Aucun hook neuf : `decisionView`, `observeBattle`, `boardGraph`, `applyAction`, `aiMovableTiles`.
ASCII only.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import hexgeo
import pytest

from engine.dsl import nodes as dsl
from engine.dsl.base import DslContext, _occupants_by_tile, _pos
from engine.entities.selectors.accessors import FixedTileIds
from engine.entities.selectors.units import AdjacentUnits, Units
from engine.entities.triggers import HasUnit
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.runner.components import get_unit_feet
from engine.runner.snapshot import load_state

MOW = "ultraDreadnought"
SUMMON = "ultraSmnDreadnought"
ATTACKER = "custoKyrus"
DUTY_ETERNAL = 1158
MAX_ROUNDS = 8
BOARD = "MC1_67"


def _harness():
    """Helpers du montage multi-hex, IMPORTES de `test_multihex_dutyeternal_live.py` (pas recopies)."""
    src = Path(__file__).with_name("test_multihex_dutyeternal_live.py")
    spec = importlib.util.spec_from_file_location("_multihex_harness_r1a", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def occupancy_case(rpc, build_runner):
    """Fait apparaitre le Galatian 3-hex, puis CAPTURE les deux canaux natifs d'occupation."""
    H = _harness()
    bc = H._ammo_seed_bc()
    rid = build_runner("777", board=BOARD,
                       extra=["--seed-bc", str(bc), "--a-mow", MOW, "--no-ai",
                              "--p-units", f"{ATTACKER},ultraTitus",
                              "--a-units", "necroWarden,necroSpyder"])["rid"]

    view = rpc("decisionView", {"runnerId": rid, "allAbilities": True})
    mows = [m for m in (view.get("mows") or []) if m.get("visualId") == MOW]
    if not mows:
        pytest.fail(f"{MOW} absent de decisionView.mows -- la MoW n'est pas deployee", pytrace=False)
    caster_mow = mows[0]["casterId"]

    board = H._board(rpc, rid)
    occupied = set(H._occupants(rpc, rid))
    attacker = next((u for u in (view.get("units") or [])
                     if u.get("visualId") == ATTACKER and u.get("ctrl") and u.get("alive")), None)
    if attacker is None:
        pytest.fail(f"{ATTACKER} absent du roster controle", pytrace=False)
    here = (attacker["pos"]["col"], attacker["pos"]["row"])
    mv = rpc("aiMovableTiles", {"runnerId": rid}) or {}
    reach = [here] + [(t["col"], t["row"]) for e in (mv.get("units") or [])
                      if e.get("unitId") == attacker["id"] for t in (e.get("tiles") or [])]
    anchor, predicted, post, strict = H._pick_anchor(board, occupied, reach)
    if anchor is None:
        pytest.fail("aucune ancre ne porte d'aire 3-tuiles valide sur ce board", pytrace=False)
    if post is not None and post != here:
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": attacker["id"], "to": {"col": post[0], "row": post[1]}}})
        acts = r.get("actions") or []
        if not (acts and acts[0].get("ok") and acts[0].get("mutated")):
            pytest.fail(f"deplacement de l'attaquant vers {post} refuse : {json.dumps(r)[:300]}",
                        pytrace=False)

    # `DutyEternal` : cooldown initial 2 + il faut le TOUR du proprietaire de la MoW, sinon
    # `applyAction` rend un REFUS SILENCIEUX (`mutated: false, spawned: 0`).
    owner = mows[0].get("owner")
    for _ in range(2 * MAX_ROUNDS):
        v = rpc("decisionView", {"runnerId": rid, "allAbilities": True})
        ab = next((a for a in (v["mows"][0].get("abilities") or [])
                   if a.get("id") == DUTY_ETERNAL), None)
        if ab is None:
            pytest.fail("DutyEternal (1158) absente des abilities de la MoW", pytrace=False)
        if ab.get("usable") and ab.get("hasAmmo", True) and not (ab.get("cooldown") or 0) \
                and (owner is None or v.get("currentPlayer") == owner):
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}})
    else:
        pytest.fail(f"1158 jamais castable apres {2 * MAX_ROUNDS} fins de tour", pytrace=False)

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_mow, "abilityType": DUTY_ETERNAL,
        "to": {"col": anchor[0], "row": anchor[1]}}})
    a0 = (res.get("actions") or [{}])[0]
    if not (res.get("ok") and a0.get("ok") and a0.get("mutated") and a0.get("spawned")):
        pytest.fail(f"cast 1158 sans effet en {anchor} : {json.dumps(res)[:400]}", pytrace=False)

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True})
    summon = next((u for u in (dv.get("units") or []) if u.get("visualId") == SUMMON), None)
    if summon is None:
        pytest.fail(f"{SUMMON} absent apres le cast de 1158", pytrace=False)

    ob = rpc("observeBattle", {"runnerId": rid})
    state = load_state(dv, ob, board=board)
    feet = get_unit_feet(state, summon["id"])

    # CANAL NATIF 1 : le `TileContentComponent`, projete par `boardGraph`.
    native_occ = H._occupants(rpc, rid)
    # CANAL NATIF 2 : la MEME donnee en action (le pathfinder lit `IsFilled`).
    mv2 = rpc("aiMovableTiles", {"runnerId": rid}) or {}
    movable = {(t["col"], t["row"]) for e in (mv2.get("units") or [])
               if e.get("unitId") == attacker["id"] for t in (e.get("tiles") or [])}

    att = next((u for u in (dv.get("units") or []) if u.get("id") == attacker["id"]), None)
    att_pos = (att["pos"]["col"], att["pos"]["row"]) if att else None

    return {"rid": rid, "board": board, "anchor": anchor, "predicted": predicted, "strict": strict,
            "attacker_id": attacker["id"], "attacker_pos": att_pos, "summon_id": summon["id"],
            "state": state, "feet": feet, "native_occ": native_occ, "movable": movable}


def _ctx(case, target_id=None):
    """`AbilityEntities` du regime : caster = l'attaquant, target = le Galatian."""
    return entities_from_state(case["state"], case["attacker_id"],
                               target_id if target_id is not None else case["summon_id"])


def _secondary_feet(case) -> list:
    """Les pieds qu'un port mono-tuile ne verrait PAS : tout sauf `feet[0]` (la main tile)."""
    return [f for f in case["feet"][1:]]


def _collapse(monkeypatch):
    """CONTRE-EPREUVE : l'index par MAIN TILE que ce commit remplace. Patche `_feet` dans CHAQUE
    module qui l'a importe par nom -- n'en patcher qu'un rendrait la contre-epreuve verte pour rien."""
    import engine.dsl.base as B
    import engine.entities.selectors.units as U
    import engine.entities.triggers as T
    flat = lambda u: ([(u["pos"]["col"], u["pos"]["row"])] if u and u.get("pos") else [])  # noqa: E731
    for m in (B, U, T):
        monkeypatch.setattr(m, "_feet", flat)


def test_regime_is_strictly_discriminant(occupancy_case):
    """Sans ce cran, tout le fichier passerait sur un montage DEGENERE (unite a UN pied)."""
    case = occupancy_case
    assert len(case["feet"]) == 3, f"cible non multi-hex : feet={case['feet']}"
    assert len(set(case["feet"])) == 3, "pieds non distincts"
    att = case["attacker_pos"]
    dists = [hexgeo.distance(f, att) for f in case["feet"]]
    assert min(dists) == 1, f"attaquant non adjacent a un pied : {dists} depuis {att}"
    assert dists[0] >= 2, (f"attaquant adjacent a la MAIN TILE {case['feet'][0]} (d={dists[0]}) -- "
                           f"montage DEGENERE, les deux index coincident")


# --------------------------------------------------- ORACLE NATIF 1 : le TileContentComponent

def test_native_marks_every_foot_tile_as_occupied(occupancy_case):
    """`boardGraph.tiles[].occupantUnitId` == la projection du `TileContentComponent` que
    `IdunBattle.Entities.UnitExtensions$$GetUnit` lit. Le natif le remplit sur les TROIS pieds --
    c'est la mesure qui fonde tout ce commit."""
    case = occupancy_case
    got = {f: case["native_occ"].get(f) for f in case["feet"]}
    assert all(v == case["summon_id"] for v in got.values()), (
        f"le natif ne resout pas tous les pieds en {case['summon_id']} : {got}")


def test_native_pathfinder_blocks_the_secondary_feet(occupancy_case):
    """MEME donnee, SECOND canal : `IgnoreEverythingPathfinder$$WeightCost` /
    `IgnoreTerrainPathfinder$$WeightCost` appellent `TileContentComponent$$IsFilled`, donc les
    tuiles des pieds NON-ANCRE sont infranchissables. Deux canaux natifs, un seul verdict."""
    case = occupancy_case
    blocked = [f for f in case["feet"] if f in case["movable"]]
    assert blocked == [], f"le natif laisse traverser des pieds du Galatian : {blocked}"


# ------------------------------------------------------ le FOYER du port, contre l'oracle natif

def test_port_occupancy_index_agrees_with_the_native_on_every_foot(occupancy_case):
    """`dsl.base._occupants_by_tile` = mirror de `TargetsSelector$$SelectUnit` -> `GetUnit`."""
    case = occupancy_case
    ents = _ctx(case)
    occ = _occupants_by_tile(ents.units)
    got = {f: (occ.get(f) or {}).get("id") for f in case["feet"]}
    assert all(v == case["summon_id"] for v in got.values()), \
        f"le port ne resout pas tous les pieds : {got}"


def test_port_occupancy_index_collapse_misses_the_secondary_feet(occupancy_case, monkeypatch):
    """CONTRE-EPREUVE : l'index d'AVANT ne voit que `feet[0]` -- la correction MORD."""
    case = occupancy_case
    ents = _ctx(case)
    _collapse(monkeypatch)
    occ = _occupants_by_tile(ents.units)
    seen = [f for f in case["feet"] if (occ.get(f) or {}).get("id") == case["summon_id"]]
    assert seen == [case["feet"][0]], \
        f"le collapse main tile devrait ne voir QUE feet[0], il voit {seen}"


# ------------------------------------------------------------- les NOEUDS DSL sur le meme etat

def test_units_node_resolves_a_secondary_foot_tile(occupancy_case):
    """`Units(<tuile d'un pied non-ancre>)` = `UnitsOnTilesSelector$$Select` -> `SelectUnit`."""
    case = occupancy_case
    board, ents = case["board"], _ctx(case)
    ctx = DslContext(units=ents.units, caster=ents.caster, target=ents.target, board=board)
    for f in _secondary_feet(case):
        tid = board.id_at(f[0], f[1])
        assert tid is not None, f"pied {f} hors board"
        got = Units(FixedTileIds([tid])).select(ctx)
        assert [u["id"] for u in got] == [case["summon_id"]], f"Units({f}) = {got}"


def test_units_node_collapse_sees_the_secondary_feet_empty(occupancy_case, monkeypatch):
    case = occupancy_case
    board, ents = case["board"], _ctx(case)
    ctx = DslContext(units=ents.units, caster=ents.caster, target=ents.target, board=board)
    tids = [board.id_at(f[0], f[1]) for f in _secondary_feet(case)]
    node = Units(FixedTileIds([t for t in tids if t is not None]))
    _collapse(monkeypatch)
    assert node.select(ctx) == []


def test_has_unit_node_sees_a_secondary_foot_tile(occupancy_case):
    """Meme foyer par l'autre helper (`entities/triggers.py::_units_on`)."""
    case = occupancy_case
    board, ents = case["board"], _ctx(case)
    ctx = DslContext(units=ents.units, caster=ents.caster, target=ents.target, board=board)
    tids = [board.id_at(f[0], f[1]) for f in _secondary_feet(case)]
    assert HasUnit(FixedTileIds([t for t in tids if t is not None])).should_trigger(ctx) is True


def test_adjacent_units_node_takes_the_summon_through_a_non_anchor_foot(occupancy_case):
    """Le selecteur COMPLET : l'attaquant est a d=1 d'un pied non-ancre et d>=2 de la main tile ;
    `AdjacentUnits(Caster())` doit donc contenir le Galatian."""
    case = occupancy_case
    board, ents = case["board"], _ctx(case)
    ctx = DslContext(units=ents.units, caster=ents.caster, target=ents.target, board=board)
    got = [u["id"] for u in AdjacentUnits(dsl.Caster(), dsl.Const(1)).select(ctx)]
    assert case["summon_id"] in got, (
        f"le Galatian {case['summon_id']} (feet={case['feet']}) absent de "
        f"AdjacentUnits(caster@{case['attacker_pos']}) = {got}")


def test_adjacent_units_node_collapse_drops_the_summon(occupancy_case, monkeypatch):
    """CONTRE-EPREUVE du selecteur complet."""
    case = occupancy_case
    board, ents = case["board"], _ctx(case)
    ctx = DslContext(units=ents.units, caster=ents.caster, target=ents.target, board=board)
    node = AdjacentUnits(dsl.Caster(), dsl.Const(1))
    _collapse(monkeypatch)
    got = [u["id"] for u in node.select(ctx)]
    assert case["summon_id"] not in got, \
        "le collapse main tile devrait PERDRE le Galatian -- la correction ne mord pas"
