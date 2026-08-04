"""GARDE LIVE #448-r1-r1-r2-r1 -- le vecteur after-move sur un ETAT LIVE, bras par bras.

La garde OFFLINE (`test_448_r1_r1_r2_r1_dsl_after_move_offline.py`) tient la SEQUENCE et le
CABLAGE avec des vecteurs substitues. Elle ne tient PAS la chaine complete : que le passif greffe
soit vu par le collecteur, que `movementSteps` remonte de `MoveUnitOperation` jusqu'au trigger, et
que le vecteur parte bien depuis l'Operation sur un etat charge du runner. C'est ce que ce
fichier-ci garde.

DISCRIMINANT, ENONCE AVANT LA MESURE. Trois bras sur le MEME etat, la MEME unite, la MEME
destination :

  * bras **DSL** -- `MoveUnitOperation(..., pathfinder_type_override=Fly,
    arrive_at_final_tile=False)`, c'est-a-dire ce que pose la feuille `FlyUnit`
    (`IdunBattleLogic.Entities.DSLBehaviors$$FlyUnit` -> `MoveUnitBehaviour$$Execute` -> slot
    `MoveUnit`). AVANT cette tranche le port ne jouait AUCUN vecteur sur ce chemin : le trigger
    `FullThrottle` (`On(0x24)`) ne pouvait PAS fire. Il doit fire maintenant, et le flag
    `ArrivedAtFinalTile` doit rester ABSENT (octet `MoveUnitOptions+0x10` INVERSE a 1) ;
  * bras **TEMOIN** -- le mouvement ORDINAIRE (`MovementHandler.visit_MoveUnitMessage`, options
    entierement nulles). Il firait DEJA avant la tranche : c'est la NON-REGRESSION, et il pose,
    lui, le flag `ArrivedAtFinalTile` ;
  * bras **INVERSE** -- `emit_after_move=False`, c'est-a-dire les call-sites qui mirroitent
    `IdunBattle.Operations.SetUnitPositionOperation$$Execute` (push / pull / switch) ou rien du
    tout (flee). AUCUN vecteur : un port qui brancherait indistinctement declencherait l'overwatch
    sur des deplacements que le natif ignore.

CONFRONTATION LIVE, mesuree le 2026-08-04 avec `probe_448_r1_r1_r2_fly_override.py --seeds 777
--rounds 40 --want 3` : sur **7 vols `FlyUnit` a d >= 3, le natif a TUE Tjark 1 fois** (et 0 fois
sur les 2 vols a d < 3). Une mort EXIGE que le gate `MovementSteps() >= 3` ait ete evalue, donc que
le natif ait publie `On(0x24)` **sur un deplacement joue par une feuille DSL**. C'est la preuve
directe que le vecteur appartient a l'Operation, pas au handler de message. (Le taux, `Maybe(30)`,
n'est pas exerce ici : ce fichier garde le GATE, pas le tirage.)

Montage = la GREFFE deja etablie (`catalog_inject.graft_passive_ability`, `case-92` SS5bis) :
`orksNpc6Stormboy` est le seul porteur de `FullThrottle` et il est npc ; ni son `CreateTrigger` ni
son `CreateBehaviour` ne lisent stat, trait ou arme du caster. ASCII only.
"""
from __future__ import annotations

import pytest

import probe_448_r1_r1_full_throttle as P
from engine.entities.pathfinding import pathfinders as PF
from engine.entities.pathfinding.board import Board
from engine.runner.components import PositionComponent, UnitFlagsComponent
from engine.runner.events import EventBus
from engine.runner.operations.movement import MoveUnitOperation, MovementHandler
from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
from engine.runner.operations.triggers.loki.full_throttle import (FULL_THROTTLE_ID,
                                                                  FullThrottlePassiveAbility)

BOARD, SEED = "MC1_67", 777
FOES = ["tauCrisis"]
PAS = 2                      # 2 pas de marche -> `path.Count` = 3 -> gate `>= 3` VRAI


@pytest.fixture(scope="module")
def live(rpc, build_runner):
    """Un runner GREFFE, partage par le module (un seul build), via les fixtures du harnais (elles
    isolent le state-file par PID et LIBERENT le runner au teardown).

    ⚠ Montage KO => ECHEC, jamais skip (#455) : un skip vert dirait « rien a valider »."""
    import json
    import uuid
    import catalog_inject as CI
    P.LOGSDIR.mkdir(parents=True, exist_ok=True)
    bcp = P.LOGSDIR / ("seedbc-test-r2r1-%s.json" % uuid.uuid4().hex[:8])
    bc = json.loads((P.ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    for uid in P.GRAFTS:
        CI.graft_passive_ability(bc, uid, P.ABILITY)
    bcp.write_text(json.dumps(bc), encoding="utf-8")

    built = build_runner(seed=str(SEED), board=BOARD,
                         extra=["--rank", "17", "--no-ai", "--seed-bc", str(bcp),
                                "--p-units", ",".join(P.GRAFTS),
                                "--a-units", ",".join(FOES)])
    rid = int(built["rid"])

    def _rpc(sid, method, args, timeout=120):
        return rpc(method, args, timeout)

    bg = rpc("boardGraph", {"runnerId": rid}, 90)
    brd = Board(bg["tiles"], adjacency="native_sym")
    st0, dv, _ob = P._port_state(None, _rpc, rid, brd)
    carriers = sorted(P._carriers(dv))
    assert carriers, "aucun porteur greffe dans decisionView -- montage KO"
    trigs = [t for t in collect_triggered_abilities(st0)
             if isinstance(t, FullThrottlePassiveAbility)]
    assert len(trigs) == len(carriers), (
        "le collecteur voit %d passif(s) greffe(s) pour %d porteur(s) -- canal "
        "`unitAbilityStates` casse, le montage serait INERTE en silence"
        % (len(trigs), len(carriers)))
    # UN porteur, DEUX destinations :
    #   * `dest_walk` = LEGALE au natif (`aiMovableTiles`) et longue de `PAS` pas de marche -> le
    #     temoin porte `path.Count = PAS + 1 = 3` et le gate mord ;
    #   * `dest_fly`  = a DISTANCE hex >= 3, walkable et LIBRE -> le vol porte `movementSteps = d`
    #     (la feuille `FlyUnit` ignore la portee de mouvement : elle ne passe pas par les gates de
    #     legalite du repositionnement joueur).
    from engine.entities.effects.aura_selectors import hex_distance
    occupied = {(e.get_component(PositionComponent).col, e.get_component(PositionComponent).row)
                for e in st0.entities.values()
                if e.get_component(PositionComponent) is not None}
    chosen = None
    for uid in carriers:
        legal = P._legal_moves(None, _rpc, rid, uid)
        dest_walk = P._pick_dest(st0, uid, legal, PAS)
        if dest_walk is None:
            continue
        pc = st0.get_entity(uid).get_component(PositionComponent)
        src = (pc.col, pc.row)
        fly = sorted(((hex_distance(src, brd.coord(t)), brd.coord(t)) for t in brd.by_id
                      if brd.walkable(t) and brd.coord(t) not in occupied
                      and hex_distance(src, brd.coord(t)) >= 3))
        if not fly:
            continue
        chosen = (uid, dest_walk, fly[0][1])
        break
    assert chosen is not None, ("aucun porteur greffe n'a a la fois une destination legale a %d "
                               "pas et une tuile libre a d >= 3 -- montage a revoir, surtout PAS "
                               "un skip vert" % PAS)
    yield {"rid": rid, "rpc": _rpc, "board": brd, "uid": chosen[0],
           "dest_walk": chosen[1], "dest_fly": chosen[2],
           "reload": lambda: P._port_state(None, _rpc, rid, brd)[0]}


def _fired(rows) -> bool:
    return any(isinstance(r, dict) and r.get("ability") == FULL_THROTTLE_ID for r in (rows or []))


def _has_arrived_flag(st, uid) -> bool:
    fl = st.get_entity(uid).get_component(UnitFlagsComponent)
    return bool(fl is not None and fl.has(UnitFlagsComponent.ARRIVED_AT_FINAL_TILE))


def test_bras_dsl_le_vecteur_part_de_l_operation(live):
    """LE POINT DE LA TRANCHE. Un deplacement pose par une feuille DSL (`FlyUnit`) declenche le
    vecteur after-move -- il ne declenchait RIEN avant #448-r1-r1-r2-r1.

    `pathfinder_type_override=Fly` : le `movementSteps` devient la DISTANCE hex (#448-r1-r1-r2).
    La destination est choisie a `d >= 3` pour que le gate morde."""
    st, uid, dest = live["reload"](), live["uid"], live["dest_fly"]
    pc = st.get_entity(uid).get_component(PositionComponent)
    src = (pc.col, pc.row)
    from engine.entities.effects.aura_selectors import hex_distance
    d = hex_distance(src, dest)
    assert d >= 3, "montage : la destination de vol doit etre a d >= 3 (got %d)" % d
    op = MoveUnitOperation(uid, dest, pathfinder_type_override=int(PF.PathfinderType.Fly),
                           arrive_at_final_tile=False)
    op.execute(st, EventBus())
    assert op.last_movement_steps == d, (
        "vol %s -> %s : movement_steps=%s (attendu la DISTANCE %d)"
        % (src, dest, op.last_movement_steps, d))
    assert _fired(op.last_after_move), (
        "le vecteur after-move n'a PAS fire sur un move DSL (d=%d) -- c'est l'etat d'AVANT "
        "la tranche" % d)
    assert not _has_arrived_flag(st, uid), (
        "une feuille DSL ne pose PAS `ArrivedAtFinalTile` (octet `MoveUnitOptions+0x10` inverse "
        "a 1 depuis un selecteur a defaut FAUX)")


def test_bras_temoin_mouvement_ordinaire_inchange(live):
    """NON-REGRESSION. Le mouvement JOUEUR (options entierement nulles) firait deja : il doit
    continuer, EXACTEMENT UNE fois, et poser `ArrivedAtFinalTile`."""
    st, uid, dest = live["reload"](), live["uid"], live["dest_walk"]

    class _Msg:
        unit_id, to = uid, dest

    h = MovementHandler(st, EventBus())
    h.visit_MoveUnitMessage(_Msg())
    hits = [r for r in (h.after_move or [])
            if isinstance(r, dict) and r.get("ability") == FULL_THROTTLE_ID]
    assert len(hits) == 1, (
        "le mouvement ordinaire doit declencher `FullThrottle` UNE seule fois (got %d) -- 0 = le "
        "handler ne republie plus rien, 2 = double emission handler + Operation" % len(hits))
    assert _has_arrived_flag(st, uid), "le mouvement JOUEUR pose `ArrivedAtFinalTile`"


def test_bras_inverse_setunitposition_ne_joue_rien(live):
    """FACE INVERSE. `emit_after_move=False` = push / pull / switch (slot `SetUnitPosition`,
    `SetUnitPositionOperation$$Execute` n'emet AUCUN event) et flee (le natif ne deplace pas).
    Meme unite, meme destination, meme distance : seul le drapeau change."""
    st, uid, dest = live["reload"](), live["uid"], live["dest_walk"]
    op = MoveUnitOperation(uid, dest, emit_after_move=False)
    op.execute(st, EventBus())
    assert op.last_after_move == []
    assert not _fired(op.last_after_move)
    pc = st.get_entity(uid).get_component(PositionComponent)
    assert (pc.col, pc.row) == tuple(dest), "la POSITION, elle, est bien ecrite"
