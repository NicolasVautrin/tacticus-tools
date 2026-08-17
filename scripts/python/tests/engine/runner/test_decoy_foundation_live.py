"""Gen-stealer G1 (FONDATION decoy) -- MECANISME sur substrat runner LIVE.

Deux primitives partagees du chantier gen-stealer (cf. docs/rl/genestealer-cults.md) :
  1. `spawn_decoy` = `DSLFactory$$IdunBattleLogic.IdunBattleLogic.Entities.DSLBehaviors$$Spawn(genesSmnDecoy, ForSteppable)` -> `AddUnitOperation.Execute`
     (socle spawn.py). Options `SpawnUnitOptions$$IdunBattle.Entities.Behaviours.SpawnUnitOptions$$ForSteppable` : level 1, owner=caster,
     `ai_controlled=False`, AUCUNE on-appearance -> token INERTE (traits Steppable+Decoy, aucune arme).
  2. crush-on-step = `MoveUnitOperation$$IdunBattle.Operations.MoveUnitOperation$$KillSteppableUnits` : un occupant Steppable de la tuile
     d'arrivee est detruit (kill PROPRE, sans death-trigger de combat) INLINE dans le move pipeline, AVANT
     `EvaluateAfterMoveTriggers`.

G1 est une FONDATION : aucune ability native ne place encore de decoy en autonome (c'est CultDemagogue G4 /
Hypersensory G6). La confrontation live-oracle de la CHAINE COMPLETE (natif pose le decoy -> ennemi marche
dessus -> crush + Blast DecoysAndMisdirection) vient donc a G2/G4. ICI on valide le MECANISME du port dans le
VRAI pipeline runner (board + state live), pas un diff contre un decoy natif (inexistant en isole).

Property-based, independant version/seed. ASCII-only. Skip si pas de session.
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import MoveUnitMessage
from engine.runner.components import PositionComponent, OwnerComponent, UnitComponent, HealthComponent, StatsComponent
from engine.runner.operations.spawn import spawn_decoy, build_decoy_context
from engine.runner.operations.movement import _kill_steppable_units
from engine.entities.traits.unit_trait import UnitTrait, has_trait


def _state_with_board(rpc, build_runner):
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777")["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    if not (dec.get("units")):
        pytest.skip("decisionView vide")
    state = load_state(dec, ob, snap, board=board)
    return state, board


def _occupied_tiles(state, board):
    occ = set()
    for e in state.entities.values():
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None:
            continue
        if uc is not None and not uc.alive:
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None:
            occ.add(t)
    return occ


def _pick_mover_and_free_neighbour(state, board):
    """Un mover VIVANT + une tuile voisine marchable LIBRE (pour y poser un decoy et l'y faire marcher)."""
    occ = _occupied_tiles(state, board)
    for uid, e in state.entities.items():
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        if pc is None or uc is None or not uc.alive or oc is None:
            continue
        mtile = board.id_at(pc.col, pc.row)
        if mtile is None:
            continue
        for t in sorted(board.neighbours(mtile)):
            if board.walkable(t) and t not in occ:
                return uid, mtile, t
    return None, None, None


def test_spawn_decoy_is_faithful_inert_token(rpc, build_runner):
    """`spawn_decoy` = token genesSmnDecoy : owner=caster (team+player), traits Steppable+Decoy, AUCUNE arme,
    `ai_controlled=False` (INERTE, ne joue jamais), pose sur la tuile demandee."""
    state, board = _state_with_board(rpc, build_runner)
    mover, _mtile, free = _pick_mover_and_free_neighbour(state, board)
    if mover is None:
        pytest.skip("pas de mover + tuile libre voisine")
    coc = state.get_entity(mover).get_component(OwnerComponent)

    did = spawn_decoy(state, free, mover)
    assert did is not None, "spawn_decoy a renvoye None"
    d = state.get_entity(did)
    uc = d.get_component(UnitComponent)
    oc = d.get_component(OwnerComponent)
    pc = d.get_component(PositionComponent)
    sc = d.get_component(StatsComponent)

    assert uc.visual_id == "genesSmnDecoy", f"visual_id={uc.visual_id}"
    assert uc.alive is True and uc.ai_controlled is False, "le decoy doit etre vivant ET inerte (ai_controlled=False)"
    assert oc.team == coc.team and oc.player == coc.player, "owner du decoy != caster (CopyOwner viole)"
    assert pc is not None and board.id_at(pc.col, pc.row) == free, "decoy pas pose sur la tuile demandee"
    traits = list(getattr(sc.ctx, "traits", None) or [])
    assert has_trait(traits, UnitTrait.Steppable) and has_trait(traits, UnitTrait.Decoy), f"traits={traits}"
    assert getattr(sc.ctx, "range", 0) == 0 and getattr(sc.ctx, "normal_profile", None) is None, "decoy ne doit avoir AUCUNE arme"


def test_move_onto_decoy_crushes_it(rpc, build_runner):
    """crush-on-step : une unite qui MOVE sur la tuile d'un decoy le detruit (Steppable) -- le decoy passe
    alive=False (hp 0). Le mover, lui, survit (exclu du crush)."""
    state, board = _state_with_board(rpc, build_runner)
    mover, _mtile, free = _pick_mover_and_free_neighbour(state, board)
    if mover is None:
        pytest.skip("pas de mover + tuile libre voisine")

    did = spawn_decoy(state, free, mover)
    assert did is not None
    tinfo = board.by_id.get(free)
    dest = (tinfo["col"], tinfo["row"])

    runner = Runner(state).install_default_handlers()
    runner.apply(MoveUnitMessage(mover, dest))

    d = state.get_entity(did)
    duc = d.get_component(UnitComponent)
    dhc = d.get_component(HealthComponent)
    assert duc.alive is False, "le decoy n'a PAS ete crushe par le move-onto"
    assert dhc is None or dhc.hp == 0, "decoy crushe mais hp != 0"

    m = state.get_entity(mover)
    muc = m.get_component(UnitComponent)
    mpc = m.get_component(PositionComponent)
    assert muc.alive is True, "le mover a ete crushe a tort (il doit etre exclu)"
    assert (mpc.col, mpc.row) == dest, "le mover n'est pas arrive sur la tuile"


def test_crush_is_clean_and_scoped(rpc, build_runner):
    """`_kill_steppable_units` : (a) cible UNIQUEMENT les occupants Steppable de la tuile dest ; (b) ne touche
    PAS une tuile sans Steppable ; (c) exclut le mover. Kill PROPRE (alive=False direct, pas de death-trigger)."""
    state, board = _state_with_board(rpc, build_runner)
    mover, _mtile, free = _pick_mover_and_free_neighbour(state, board)
    if mover is None:
        pytest.skip("pas de mover + tuile libre voisine")
    tinfo = board.by_id.get(free)
    dest = (tinfo["col"], tinfo["row"])

    # (b) tuile libre SANS decoy -> aucun crush
    assert _kill_steppable_units(state, dest, mover) == [], "crush sur une tuile sans Steppable"

    # (a) decoy pose -> crush cible exactement le decoy
    did = spawn_decoy(state, free, mover)
    killed = _kill_steppable_units(state, dest, mover)
    assert killed == [did], f"crush attendu [{did}], obtenu {killed}"

    # (c) re-appel : deja mort -> plus rien a crush (kill propre, idempotent en pratique)
    assert _kill_steppable_units(state, dest, mover) == [], "decoy deja mort re-crushe"
