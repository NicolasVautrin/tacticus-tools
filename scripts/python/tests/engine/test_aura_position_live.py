"""Agrement #67 : l'aura d'ATTAQUE-STAT (RitesOfBattle @181225340) en PREDICTION DISPLAY est bakee
a la POSITION REELLE de l'attaquant, IDENTIQUE sur TOUTES les tuiles candidates (elle ne se
re-evalue PAS par tuile candidate). Verite live (verdict re-expert #67) : GetAttackHitPrediction
@1811af4e0 lit GetStat(Attack, Current) SANS argument de position -> la valeur bakee (Initial + aura
a la vraie position) s'applique a chaque tuile candidate. Le bug #67 evaluait l'aura a la tuile
candidate -> aura absente sur les tuiles non-adjacentes au porteur (~24/28 du #49).

Setup craft (aura projetee de facon STABLE) : ultraCalgar (porteur RitesOfBattle Imperial) + un allie
Imperial melee (bloodDeathCompany, le u92 de #49) place hex-adjacent a Calgar OFFLINE. Assertions
GENERIQUES (aucune valeur hardcodee ; on lit Initial + aura live) et seed-independant :
  (1) attaquant adjacent au porteur : `meta['base']` CONSTANT sur toutes les tuiles candidates,
      == Initial + aura(position reelle) > Initial ;
  (2) attaquant eloigne du porteur : `meta['base']` CONSTANT == Initial bare (aura absente).
Skip propre si le roster ne deploie pas Calgar + l'allie, ou pas de tuile libre adjacente.
ASCII-only (cp1252)."""
from __future__ import annotations

import pytest

import gameconfig as GC
from engine.runner.snapshot import load_state
from engine.runner.components import UnitComponent, PositionComponent, OwnerComponent
from engine.playbook.scene import Scene
from engine.playbook import prediction
from engine.entities.effects import aura_attack_bonus_from_allies
from engine.entities.stats import StatType, StatPart
from engine.services.battle_query import are_tiles_adjacent
from engine.entities.pathfinding.board import Board

AURA_UNITS = "ultraCalgar,bloodDeathCompany"   # Calgar = RitesOfBattle Imperial ; bloodDeathCompany = allie Imperial melee (#49)


def _find(state, sub):
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc and sub.lower() in str(uc.visual_id).lower():
            return uid
    return None


def _carriers(scene, att_id):
    return [(uid, scene.pos(uid), scene.team(uid), scene.mult(uid), scene.ablvl_by_id.get(uid),
             (GC.unit(scene.vis_by_id.get(uid)) or {}).get("GrandAllianceId"),
             (GC.unit(scene.vis_by_id.get(uid)) or {}).get("FactionId"), scene.effects(uid))
            for uid in scene.pos_by_id if uid != att_id and (scene.hp(uid) or 0) > 0]


def _aura_at(scene, att_id, att_pos):
    agu = GC.unit(scene.vis_by_id.get(att_id)) or {}
    ctx = {"att_id": att_id, "att_pos": att_pos, "att_team": scene.team(att_id),
           "att_grand_alliance": agu.get("GrandAllianceId"), "att_faction": agu.get("FactionId"),
           "board": scene.board}
    return aura_attack_bonus_from_allies(_carriers(scene, att_id), ctx)


def _base(scene, att_id, tgt_id, attack_pos):
    _ev, meta = prediction.make_normal_attack_predictions(scene, att_id, tgt_id, attack_pos, meta=True)
    return meta["base"]


def test_attack_stat_aura_baked_at_real_position(rpc, build_runner):
    rid = build_runner(seed="777", extra=["--p-units", AURA_UNITS])["rid"]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    obs = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(dv, dict) and dv.get("units")):
        pytest.skip("decisionView vide")
    if not (isinstance(bg, dict) and bg.get("ok")):
        pytest.skip("boardGraph KO")

    state = load_state(dv, obs, snap)
    state.board = Board(bg["tiles"])          # native_sym (comme le runner)
    calgar = _find(state, "calgar")
    bdc = _find(state, "blooddeath")
    if calgar is None or bdc is None:
        pytest.skip("Calgar/bloodDeathCompany non deployes (pool/spawn)")

    bdc_team = state.get_entity(bdc).get_component(OwnerComponent).team
    scene0 = Scene.from_state(state)
    tgt = next((uid for uid, e in state.entities.items()
                if (oc := e.get_component(OwnerComponent)) is not None and oc.team != bdc_team
                and scene0.ctx(uid) is not None), None)
    if tgt is None:
        pytest.skip("aucune cible ennemie avec ctx")

    board = state.board
    cal_pos = scene0.pos(calgar)
    cal_tid = board.id_at(*cal_pos)
    occ = set(scene0.pos_by_id.values())
    adj_tile = next((board.coord(nid) for nid in board.neighbours(cal_tid)
                     if board.walkable(nid) and board.coord(nid) not in occ), None)
    if adj_tile is None:
        pytest.skip("aucune tuile libre adjacente a Calgar")

    # place l'allie hex-adjacent a Calgar (OFFLINE) -> aura projetee a sa position REELLE
    pc = state.get_entity(bdc).get_component(PositionComponent)
    pc.col, pc.row = adj_tile
    scene = Scene.from_state(state)
    assert are_tiles_adjacent(scene.pos(bdc), cal_pos, board) is True

    initial = scene.ctx(bdc).get_stat(StatType.ATTACK, StatPart.INITIAL)
    aura_real = _aura_at(scene, bdc, scene.pos(bdc))
    assert aura_real > 0, "RitesOfBattle ne projette pas sur un allie Imperial adjacent a Calgar"

    # une tuile candidate NON-adjacente a Calgar (la ou le bug #67 perdait l'aura)
    far_tid = max(board.by_id, key=lambda tid: abs(board.coord(tid)[0] - cal_pos[0])
                  + abs(board.coord(tid)[1] - cal_pos[1]))
    far_tile = board.coord(far_tid)
    assert are_tiles_adjacent(far_tile, cal_pos, board) is not True

    # (1) attaquant adjacent au porteur -> base CONSTANT = Initial + aura(REELLE) sur toutes les tuiles
    cands = [scene.pos(bdc), adj_tile, far_tile]
    bases = [_base(scene, bdc, tgt, ap) for ap in cands]
    assert len(set(bases)) == 1, f"base varie par tuile candidate {list(zip(cands, bases))} (#67 REGRESSE)"
    assert bases[0] == initial + aura_real, f"base {bases[0]} != Initial+aura {initial + aura_real}"

    # (2) attaquant eloigne du porteur -> base CONSTANT = Initial bare (aura absente) sur toutes les tuiles
    pc.col, pc.row = far_tile
    scene2 = Scene.from_state(state)
    assert are_tiles_adjacent(scene2.pos(bdc), cal_pos, board) is not True
    bases_far = [_base(scene2, bdc, tgt, ap) for ap in [far_tile, adj_tile, scene.pos(bdc)]]
    assert len(set(bases_far)) == 1 and bases_far[0] == initial, \
        f"attaquant eloigne : base attendue Initial bare {initial}, obtenu {bases_far}"
