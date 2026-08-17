"""#225 -- GARDE : un trait ACCORDE EN BATAILLE est vu par les gates de trait de la couche DECISION.

CRITERE BINAIRE : un `HasTrait` de la couche decision rend-il le MEME verdict que le natif APRES
qu'un `AddTraitOperation` a accorde le trait en cours de bataille ?

Le chemin d'ECRITURE natif est `IdunBattleLogic.Entities.DSLBehaviors$$AddTrait` ->
`IdunBattle.Operations.AddTraitOperation$$AddTrait`, qui ecrit `BaseUnitComponent+0x40` (ajout
PERMANENT, `isTemporary == 0`) ou `+0x48` (temporaire) ; la LECTURE
`IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` est
`if (+0x50).Contains(t) -> false ; return (+0x40).Contains(t) || (+0x48).Contains(t)`.
Cote port, le leaf est deja porte (`engine/runner/abilities/behaviours/grants.py::AddTrait`) et
ecrit `StatsComponent.ctx.traits` -- c'est le levier utilise ici, exactement comme le verrou
structurel de `test_chain_after_refused_addeffect_live` accorde `Immune`.

MONTAGE DISCRIMINANT (exige par le critere) : le trait accorde doit etre ABSENT du gameconfig de
l'unite, sinon le cas STATIQUE et le cas DYNAMIQUE sont indiscernables et la mesure ne prouve rien.
On accorde `Summon` (`UnitTrait.Summon` = 2) a une unite qui ne l'a pas -- c'est la forme EXACTE du
chemin natif data-driven `EnhancementAddTrait:Summon` (constante d'ability `trait`, lue par
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnhancementAddTraitAbility$$CreateBehaviour`).
Le gate confronte est `IdunBattle.AI.Utilities.CapturePointTileUtility.
u003CEvaluateMovementInStepsu003Ed__3$$MoveNext` : `HasTrait(case.unit, 2) || HasTrait(case.unit,
0xd)` choisit `summons_dislike_capture_points` (negatif) au lieu de `heroes_on_capture_points`
(positif) -- un CHANGEMENT DE SIGNE, pas une nuance.

Deux etages, dans l'ordre de la doctrine :
  etage 1 -- NEUTRALITE : sans aucun octroi, le substrat d'ENTITE (`entity_trait_*`) est IDENTIQUE
             au substrat statique par visualId (`unit_trait_*`) pour TOUTES les unites de la
             bataille. C'est ce qui prouve que #225 ne deplace rien tant que rien n'est accorde.
  etage 2 -- DISCRIMINATION : apres l'octroi, le ctx des feuilles porte le trait et le gate BASCULE ;
             le substrat statique, lui, ne le voit TOUJOURS pas (c'est la mesure de l'angle mort).

ASCII only. Dispose SES runners (fabrique `build_runner`).
"""
from __future__ import annotations

import pytest

import gameconfig as GC
from engine import weights as W
from engine.dsl.effects import ExecutionContext
from engine.entities.pathfinding.board import Board
from engine.entities.selectors.accessors import Target
from engine.entities.traits.unit_trait import (UnitTrait, entity_trait_ids, entity_trait_names,
                                               unit_trait_ids, unit_trait_names)
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.runner.abilities.behaviours.grants import AddTrait
from engine.runner.components import StatsComponent, UnitComponent
from engine.runner.snapshot import load_state
from engine.utilities.tile import TILE_LEAVES, CapturePointTileUtility, runner_tile_leaf_ctx
from engine.utilities.utility_type import UtilityType

# #272 : MEMBRE d'enum, JAMAIS l'ordinal. Ce test naissait avec `CAPTURE_POINT = 24` -- exact a son
# ecriture, PERIME depuis `fe5b9245` (#252 : la MAJ de build insere `AttackTile` en 8 et decale 59
# membres de +1, `CapturePoint` 24 -> 25). `TILE_LEAVES` etant keye par MEMBRES depuis #254, l'index
# 24 rendait alors `MoltenForm_TilesUtility` -- une feuille gatee sur `unit_triggered_abilities`
# (1221), donc 0.0 quoi qu'on lui donne : le test mesurait une AUTRE feuille que celle qu'il nomme.
CAPTURE_POINT = UtilityType.CapturePoint
SUMMON = int(UnitTrait.Summon)           # 2


@pytest.fixture(scope="module")
def state_and_units(rpc, build_runner):
    """Un `State` charge depuis une bataille LIVE (aucune valeur en dur) + la liste de ses unites."""
    rid = build_runner("777", board="MC1_67")["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    cs = rpc("combatSnapshot", {"runnerId": rid}, 60)
    state = load_state(dv, ob, cs, board=board)
    ids = [eid for eid, e in state.entities.items()
           if e.get_component(StatsComponent) is not None
           and e.get_component(UnitComponent) is not None]
    if len(ids) < 2:
        pytest.skip("moins de 2 unites a StatsComponent dans l'etat charge")
    return state, ids


# ------------------------------------------------------------------ etage 1 : NEUTRALITE


def test_entity_substrate_equals_static_substrate_before_any_grant(state_and_units):
    """Sans octroi, `entity_trait_names/ids(ctx, vis)` == `unit_trait_names/ids(vis)` pour TOUTES
    les unites. C'est la preuve que le passage au substrat d'ENTITE (#225) est neutre au bit pres
    tant que rien n'a ete accorde en bataille -- et donc que toute difference observee a l'etage 2
    vient de l'octroi, pas du changement d'accesseur."""
    state, ids = state_and_units
    checked = 0
    for uid in ids:
        e = state.get_entity(uid)
        sc = e.get_component(StatsComponent)
        vis = e.get_component(UnitComponent).visual_id
        got_n, want_n = entity_trait_names(sc.ctx, vis), unit_trait_names(vis)
        got_i, want_i = entity_trait_ids(sc.ctx, vis), unit_trait_ids(vis)
        assert got_n == want_n, ("u%s %s : substrat entite %s != substrat statique %s"
                                 % (uid, vis, sorted(got_n), sorted(want_n)))
        assert got_i == want_i, "u%s %s : ids %s != %s" % (uid, vis, got_i, want_i)
        checked += 1
    print("[#225 neutralite] %d unites : substrat entite == substrat statique" % checked)
    assert checked >= 2, "moins de 2 unites confrontees (%d)" % checked


def test_leaf_ctx_traits_equal_static_before_any_grant(state_and_units):
    """Meme neutralite, mais au niveau du `ctx` REELLEMENT servi aux feuilles Tile(7)
    (`runner_tile_leaf_ctx`) : `unit_traits` (sujet) ET les `traits` des voisins."""
    state, ids = state_and_units
    for uid in ids:
        vis = state.get_entity(uid).get_component(UnitComponent).visual_id
        lc = runner_tile_leaf_ctx(state, uid)
        assert tuple(lc.get("unit_traits") or ()) == unit_trait_ids(vis), (
            "u%s %s : ctx.unit_traits=%s attendu %s"
            % (uid, vis, lc.get("unit_traits"), unit_trait_ids(vis)))
        for rec in list(lc.get("friend_units") or ()) + list(lc.get("enemy_units") or ()):
            assert rec["traits"] == unit_trait_names(rec["vis"]), (
                "voisin %s : traits %s != %s" % (rec["vis"], sorted(rec["traits"]),
                                                 sorted(unit_trait_names(rec["vis"]))))
    print("[#225 neutralite ctx] %d sujets + voisins : identiques au substrat statique" % len(ids))


# ------------------------------------------------------------------ etage 2 : DISCRIMINATION


def _grant(state, uid, trait):
    """Mirror du chemin d'ECRITURE natif : le leaf DSL porte `AddTrait` sur l'unite `uid`."""
    ectx = ExecutionContext(state=state, rng=None)
    AddTrait(Target(), trait).execute(entities_from_state(state, uid, uid), ectx)
    return [p for n, p in ectx.emitted if n == "AddTrait"]


def test_in_battle_granted_trait_flips_the_capture_point_gate(state_and_units):
    """MESURE DISCRIMINANTE. Une unite dont le gameconfig N'A PAS `Summon` recoit `Summon` en
    bataille (`AddTrait`). Avant : la feuille `CapturePointTileUtility` prend la branche
    `heroes_on_capture_points` ; apres : `summons_dislike_capture_points`. Le substrat STATIQUE par
    visualId, lui, ne bouge pas -- c'est exactement l'angle mort mesure par #225."""
    state, ids = state_and_units
    wt = W.load()
    w_heroes = wt.sub("CapturePoint", "heroes_on_capture_points")
    w_summons = wt.sub("CapturePoint", "summons_dislike_capture_points")
    assert w_heroes != w_summons, ("poids BC CapturePoint identiques (%s) -- le gate ne serait pas "
                                   "discriminant" % w_heroes)

    subject = next((u for u in ids
                    if SUMMON not in unit_trait_ids(
                        state.get_entity(u).get_component(UnitComponent).visual_id)), None)
    assert subject is not None, "aucune unite SANS le trait Summon -- montage non discriminant"
    vis = state.get_entity(subject).get_component(UnitComponent).visual_id
    kit = sorted((GC.unit(vis) or {}).get("traits") or ())
    assert "Summon" not in kit, ("le trait accorde est DEJA dans le gameconfig de %s (%s) : le cas "
                                 "statique et le cas dynamique seraient indiscernables" % (vis, kit))

    # GARDE D'IDENTITE (#272) : la feuille confrontee doit etre CELLE QUE LE TEST NOMME. Sans ce
    # controle, un ordinal perime rend une AUTRE feuille du registre -- qui vaut 0.0 sur ce `meta`,
    # donc un rouge qui accuse le gate de trait alors que la feuille n'a jamais ete atteinte.
    leaf_name, leaf = TILE_LEAVES[CAPTURE_POINT]
    assert leaf_name == "CapturePoint" and isinstance(leaf, CapturePointTileUtility), (
        "TILE_LEAVES[%r] rend %r (%s) au lieu de CapturePointTileUtility"
        % (int(CAPTURE_POINT), leaf_name, type(leaf).__name__))
    assert leaf.UTILITY_TYPE == int(UtilityType.CapturePoint)
    meta = {"is_territory": True}
    tile = (0, 0)                      # la feuille ne lit que `meta`/`ctx` -- la tuile est un jeton
    before = runner_tile_leaf_ctx(state, subject)
    v_before = leaf.evaluate(tile, meta, before, wt)
    assert SUMMON not in (before.get("unit_traits") or ()), (
        "u%s %s porte deja le trait 2 avant l'octroi : %s" % (subject, vis, before.get("unit_traits")))
    assert v_before == w_heroes, ("branche AVANT = %s, attendu heroes_on_capture_points (%s)"
                                  % (v_before, w_heroes))

    emitted = _grant(state, subject, UnitTrait.Summon)
    assert emitted, "le leaf AddTrait n'a rien emis -- l'octroi n'a pas eu lieu"

    after = runner_tile_leaf_ctx(state, subject)
    v_after = leaf.evaluate(tile, meta, after, wt)
    print("[#225 gate] u%s %s kit=%s | unit_traits %s -> %s | CapturePoint %s -> %s (BC %s / %s)"
          % (subject, vis, kit, before.get("unit_traits"), after.get("unit_traits"),
             v_before, v_after, w_heroes, w_summons))
    assert SUMMON in (after.get("unit_traits") or ()), (
        "le trait accorde EN BATAILLE n'atteint pas le ctx des feuilles : unit_traits=%s -- le gate "
        "lit encore un substrat STATIQUE (angle mort #225)" % (after.get("unit_traits"),))
    assert v_after == w_summons, ("branche APRES = %s, attendu summons_dislike_capture_points (%s)"
                                  % (v_after, w_summons))
    assert (v_before > 0) != (v_after > 0), (
        "le gate n'a pas change de SIGNE (%s -> %s) : la mesure ne discrimine rien"
        % (v_before, v_after))

    # Le substrat STATIQUE reste aveugle : c'est CE fork que #225 supprime cote decision.
    assert SUMMON not in unit_trait_ids(vis), (
        "le substrat statique par visualId a bouge -- il ne doit PAS (il est cache par visualId, "
        "et deux entites du meme visualId n'ont pas forcement les memes traits)")


def test_in_battle_granted_trait_is_visible_to_the_neighbours_gates(state_and_units):
    """Face VOISIN : les recs `friend_units`/`enemy_units` (que lisent les filtres
    `FilterAdjacent*` de `AdjacentUnitPreferenceTriggeredAbilityPlaybook`, ex.
    `IdunBattle.AI.Playbook.Loki.FabricatorClawArrayPlaybook$$FilterAdjacentFriends` sur
    `HasTrait(Mechanical)`) portent eux aussi le trait accorde en bataille."""
    state, ids = state_and_units

    def _free(u):
        """Sujet ENCORE vierge de `Summon` -- l'`State` du montage est de portee MODULE, donc le
        test precedent a deja pu accorder le trait a UNE unite ; on en prend une autre plutot que
        de rejouer un octroi deja fait (ce qui ne prouverait plus rien)."""
        e = state.get_entity(u)
        vis = e.get_component(UnitComponent).visual_id
        sc = e.get_component(StatsComponent)
        return SUMMON not in entity_trait_ids(sc.ctx if sc is not None else None, vis)

    subject = next((u for u in ids if _free(u)), None)
    other = next((u for u in ids if u != subject), None)
    assert subject is not None and other is not None, (
        "aucune unite encore vierge du trait Summon dans le montage")

    def _rec_for(observer, target):
        lc = runner_tile_leaf_ctx(state, observer)
        tpos = None
        te = state.get_entity(target)
        from engine.runner.components import PositionComponent
        pc = te.get_component(PositionComponent)
        if pc is not None:
            tpos = (pc.col, pc.row)
        for rec in list(lc.get("friend_units") or ()) + list(lc.get("enemy_units") or ()):
            if rec["pos"] == tpos:
                return rec
        return None

    rec_before = _rec_for(other, subject)
    assert rec_before is not None, "l'unite sujet n'apparait pas dans les voisins de u%s" % other
    assert "Summon" not in rec_before["traits"], "le sujet porte deja Summon cote voisin"

    _grant(state, subject, UnitTrait.Summon)
    rec_after = _rec_for(other, subject)
    print("[#225 voisin] u%s vu par u%s : %s -> %s"
          % (subject, other, sorted(rec_before["traits"]), sorted(rec_after["traits"])))
    assert "Summon" in rec_after["traits"], (
        "le trait accorde en bataille n'atteint pas les recs de voisinage -> tout filtre "
        "`FilterAdjacent*` porte contre `HasTrait` reste aveugle (angle mort #225)")
