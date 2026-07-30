"""#303 -- `FabricatorClawArray`, le passif du `necroSpyder`, confronte au LIVE (residu N20 de #299).

CE QUE CES TESTS VERROUILLENT. #299 a porte la face COMBAT de la reparation REGULIERE et l'a
confrontee live. Sur le `necroSpyder`, et sur lui seul, il restait un ecart PARFAITEMENT
reproductible -- natif **10457**, port **6025** -- et cet ecart n'etait PAS dans la reparation : une
SECONDE reparation partait au meme tour, celle de ce passif. Le port SOUS-reparait, silencieusement.

CRITERE BINAIRE : quand le Spyder termine son activation a cote d'un allie mecanique BLESSE, cet
allie gagne-t-il `hpToRepair[niveau]` PV -- du MEME montant live et offline ?

CHAINE PORTEE (cf. `engine/runner/operations/triggers/loki/fabricator_claw_array.py`) :
    `FabricatorClawArrayAbility$$CreateTrigger`  -> `matches` (arbre DSL : `OwnerIsActor &
        !AmountIsZero(GetTargetSelector())`), sur le vecteur `On(0x1c = ArrivedAtFinalTile)`
    `...$$CreateBehaviour` -> feuille DSL `Repair` -> `IdunBattle.Operations.RepairUnitOperation$$Execute`

MONTAGE. La fixture NOMMEE `_repair_stage` (#298) avec `REPAIRER_VIS = necroSpyder`, en regime
NON SATURE (`--hp-player 300000` + `RemainingHealth=1`) : le manque (299999) depasse massivement le
montant, donc `FillUpStatComponent$$MaxFillUp` ne masque rien. Les positions sont CONDUITES a chaque
fois (jamais « bloque par la geometrie de spawn ») : c'est le DEPLACEMENT qui publie `On(0x1c)`.

ASCII only (console cp1252).
"""
from __future__ import annotations

import os
import sys

import pytest

from engine.entities.pathfinding.board import Board
from engine.runner.components import HealthComponent, StatsComponent, UnitFlagsComponent
from engine.runner.messages import MoveUnitMessage, FinishUnitTurnMessage
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

sys.path.insert(0, os.path.dirname(__file__))
import _repair_stage as S                                 # noqa: E402

REPAIRER = "necroSpyder"
HP_PLAYER = 300000          # PV MAX enormes -> aucun cap `MaxFillUp` ne masque le montant
DAMAGED = 1                 # `RemainingHealth=1` sur la cible -> manque MAXIMAL


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _board(rpc, rid):
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return None
    return Board(bg["tiles"], adjacency="native_sym")


def _by_vis(state, vis):
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc.ctx, "visual_id", None) == vis:
            return uid
    return None


def _live_units(rpc, rid):
    r = rpc("observeBattle", {"runnerId": rid}, 40)
    return {u["squadId"]: u for u in (r.get("units") or [])} if _ok(r) else {}


def _capture(rpc, rid, board):
    """Capture l'etat offline ET **CALE LE PRNG** sur l'etat MT live (`dumpRng`).

    Le calage n'est pas cosmetique : `PickRandomly` CONSOMME le PRNG (deux fois par fire, cf. le
    module porte). Sans lui, `_pick_randomly_n` retombe sur `pool[:n]` -- un choix DETERMINISTE qui
    coincide avec le natif quand le pool tient dans 1 element, et qui DIVERGE des qu'il y en a deux
    (mesure : natif `admecRuststalker`, port sans calage `necroWarden`)."""
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        return None
    state = load_state(dv, ob, snap, board=board)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if isinstance(s0, dict) and s0.get("mt"):
        from engine.runner.prng import IntBasedMersenneTwister
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        state.rng = rng
    return state


def _stage(rpc, build_runner, monkeypatch, *, repairee=None, damaged=DAMAGED,
           hp_player=HP_PLAYER):
    monkeypatch.setattr(S, "REPAIRER_VIS", REPAIRER)
    if repairee is not None:
        monkeypatch.setattr(S, "REPAIREE_VIS", repairee)
    return S.build_stage(rpc, build_runner=build_runner, hp_player=hp_player, advance=0,
                         damaged_repairee=damaged)


def _squads(rpc, rid, repairee):
    U = _live_units(rpc, rid)
    sq_c = next((sq for sq, u in U.items() if u.get("visualId") == REPAIRER), None)
    sq_t = next((sq for sq, u in U.items() if u.get("visualId") == repairee), None)
    return U, sq_c, sq_t


def _free_tiles_at_distance(board, occupied, target_tile, dmin, dmax, exclude=()):
    """Tuiles LIBRES et marchables dont la distance hex a `target_tile` est dans [dmin, dmax].
    Sert a CONDUIRE les positions (jamais a subir la geometrie de spawn)."""
    from engine.runner.operations.triggers.base import _hex_dist
    out = []
    for t in board.by_id:
        if t in occupied or t in exclude or not board.walkable(t):
            continue
        d = _hex_dist(board, target_tile, t, dmax)
        if d is not None and dmin <= d <= dmax:
            out.append((d, t))
    out.sort()
    return [t for _, t in out]


def _move_live(rpc, rid, sq, board, tile):
    """Applique un move LIVE et rend la tuile REELLEMENT occupee apres coup (None si l'unite a
    disparu). Le natif peut clamper la destination -- on relit toujours."""
    c, r = board.coord(tile)
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": sq, "to": {"col": c, "row": r}}}, 60)
    U = _live_units(rpc, rid)
    if sq not in U:
        return None
    return board.id_at(U[sq]["col"], U[sq]["row"])


def _hp(state, uid):
    return int(state.get_entity(uid).get_component(HealthComponent).hp)


def _expected_amount(state, cid):
    from engine.runner.operations.triggers.loki.fabricator_claw_array import hp_to_repair
    return hp_to_repair(state, cid)


# --------------------------------------------------------------------------------------------------
def test_move_alone_fires_the_passive_repair(build_runner, rpc, monkeypatch):
    """LE test du residu N20 : le DEPLACEMENT SEUL repare, du MEME montant live et offline.

    Aucun cast n'intervient -- c'est `IdunBattle.Operations.MoveUnitOperation$$Execute` qui pose
    `UnitFlag.ArrivedAtFinalTile` et publie `On(0x1c)`. Le montant attendu n'est PAS un scalaire
    hardcode : il est RE-DERIVE du port (`hp_to_repair` = `AbilityConfiguration.GetVariableForLevel(
    config, 0x24 = hpToRepair, abilityState, 0)`, multiplicateur de rarete INCLUS car `hpToRepair`
    est dans `variablesAffectedByRarityBonus`). Les trois valeurs doivent coincider :
    `live == offline == hpToRepair > 0`.

    ⚠ GARDE ROUGE VUE AVANT LE PORT (mutation adversariale : `ABILITY_TRIGGERS.pop(
    'FabricatorClawArray')`, l'etat `origin/master`) -- le port rendait `offline = 0` face a un
    `live = 4432`."""
    stage = _stage(rpc, build_runner, monkeypatch)
    rid = stage["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    U, sq_c, sq_t = _squads(rpc, rid, S.REPAIREE_VIS)
    if sq_c is None or sq_t is None:
        pytest.skip("repareur/cible absents live")
    occupied = {board.id_at(u["col"], u["row"]) for u in U.values()}
    t_tile = board.id_at(U[sq_t]["col"], U[sq_t]["row"])
    c_tile = board.id_at(U[sq_c]["col"], U[sq_c]["row"])
    dests = _free_tiles_at_distance(board, occupied, t_tile, 1, 1, exclude=(c_tile,))
    assert dests, "aucune tuile libre adjacente a la cible -- le montage doit CONDUIRE les positions"

    state = _capture(rpc, rid, board)
    if state is None:
        pytest.skip("capture pre-move KO")
    cid, tid = _by_vis(state, REPAIRER), _by_vis(state, S.REPAIREE_VIS)
    if cid is None or tid is None:
        pytest.skip("roster incomplet offline (%s / %s)" % (cid, tid))
    hc = state.get_entity(tid).get_component(HealthComponent)
    assert int(hc.hp) < int(hc.hp_max), "le montage doit livrer une cible BLESSEE"
    assert int(hc.hp_max) - int(hc.hp) > 3 * _expected_amount(state, cid), (
        "le manque doit DEPASSER largement le montant, sinon MaxFillUp sature et masque l'ecart")
    amount = _expected_amount(state, cid)
    assert amount > 0, "hpToRepair illisible (niveau/gameconfig)"

    dcol, drow = board.coord(dests[0])
    off_pre = _hp(state, tid)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(MoveUnitMessage(unit_id=cid, to=(dcol, drow)))
    off_delta = _hp(state, tid) - off_pre

    live_pre = _live_units(rpc, rid)[sq_t]["hp"]
    assert _move_live(rpc, rid, sq_c, board, dests[0]) is not None, "le move live a echoue"
    live_delta = _live_units(rpc, rid)[sq_t]["hp"] - live_pre

    print("\n[FCA/move] hpToRepair=%d live=%d offline=%d" % (amount, live_delta, off_delta))
    assert live_delta > 0, (
        "le natif n'a RIEN repare (delta=%d) -- montage invalide, pas un verdict de port" % live_delta)
    assert off_delta == amount, "offline %d != hpToRepair %d" % (off_delta, amount)
    assert live_delta == off_delta, "live %d != offline %d" % (live_delta, off_delta)


def test_passive_fires_at_most_once_per_activation(build_runner, rpc, monkeypatch):
    """CONTROLE -- `On(0x1c)` fire AU PLUS UNE FOIS par activation.

    Les deux emetteurs natifs (`MoveUnitOperation$$Execute`, `FinishUnitTurnOperation$$Execute`)
    publient l'evenement SSI `UnitFlagsComponent.Add(ArrivedAtFinalTile)` a rendu TRUE, donc SSI le
    flag venait d'etre pose. Un SECOND deplacement dans le meme tour ne doit donc RIEN reparer.
    Sans ce test, le precedent ne prouve rien : « ca repare » et « ca repare a chaque pas » rendent
    le meme vert -- et un Spyder a 4 pas de mouvement multiplierait la reparation par 4."""
    stage = _stage(rpc, build_runner, monkeypatch)
    rid = stage["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    U, sq_c, sq_t = _squads(rpc, rid, S.REPAIREE_VIS)
    if sq_c is None or sq_t is None:
        pytest.skip("repareur/cible absents live")
    occupied = {board.id_at(u["col"], u["row"]) for u in U.values()}
    t_tile = board.id_at(U[sq_t]["col"], U[sq_t]["row"])
    c_tile = board.id_at(U[sq_c]["col"], U[sq_c]["row"])
    dests = _free_tiles_at_distance(board, occupied, t_tile, 1, 1, exclude=(c_tile,))
    if len(dests) < 2:
        pytest.skip("moins de 2 tuiles libres adjacentes -- controle non jouable")

    state = _capture(rpc, rid, board)
    if state is None:
        pytest.skip("capture pre-move KO")
    cid, tid = _by_vis(state, REPAIRER), _by_vis(state, S.REPAIREE_VIS)
    if cid is None or tid is None:
        pytest.skip("roster incomplet offline")

    runner = Runner(state).install_default_handlers(20)
    runner.apply(MoveUnitMessage(unit_id=cid, to=board.coord(dests[0])))
    first = _hp(state, tid)
    runner.apply(MoveUnitMessage(unit_id=cid, to=board.coord(dests[1])))
    off_second = _hp(state, tid) - first

    _move_live(rpc, rid, sq_c, board, dests[0])
    live_mid = _live_units(rpc, rid)[sq_t]["hp"]
    _move_live(rpc, rid, sq_c, board, dests[1])
    live_second = _live_units(rpc, rid)[sq_t]["hp"] - live_mid

    fl = state.get_entity(cid).get_component(UnitFlagsComponent)
    print("\n[FCA/once] 2e move : live=%d offline=%d (flag pose=%s)"
          % (live_second, off_second, fl is not None
             and fl.has(UnitFlagsComponent.ARRIVED_AT_FINAL_TILE)))
    assert off_second == 0, "le port a re-repare au 2e move (%d)" % off_second
    assert live_second == 0, "le natif a re-repare au 2e move (%d) -- lecture du gate a revoir" % live_second


def test_no_adjacent_ally_no_repair(build_runner, rpc, monkeypatch):
    """GENERALISATION DISCRIMINANTE -- la geometrie du selecteur `AdjacentFriends(Owner, 1, 3)`.

    Le Spyder termine son deplacement LOIN de son allie blesse (distance hex >= 2). `On(0x1c)` est
    publie APRES le move, donc le selecteur est evalue sur la position D'ARRIVEE : plus aucun allie
    adjacent -> `AmountIsZero` -> aucune reparation. Un port qui aurait lu « tous les allies
    mecaniques » (au lieu des seuls ADJACENTS) reparerait ici a distance, et aucun autre test du
    lot ne le verrait.

    Les positions sont CONDUITES : on choisit explicitement une tuile libre a distance >= 2."""
    stage = _stage(rpc, build_runner, monkeypatch)
    rid = stage["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    U, sq_c, sq_t = _squads(rpc, rid, S.REPAIREE_VIS)
    if sq_c is None or sq_t is None:
        pytest.skip("repareur/cible absents live")
    occupied = {board.id_at(u["col"], u["row"]) for u in U.values()}
    t_tile = board.id_at(U[sq_t]["col"], U[sq_t]["row"])
    c_tile = board.id_at(U[sq_c]["col"], U[sq_c]["row"])
    far = _free_tiles_at_distance(board, occupied, t_tile, 2, 3, exclude=(c_tile,))
    if not far:
        pytest.skip("aucune tuile libre a distance >= 2 de la cible")

    state = _capture(rpc, rid, board)
    if state is None:
        pytest.skip("capture pre-move KO")
    cid, tid = _by_vis(state, REPAIRER), _by_vis(state, S.REPAIREE_VIS)
    if cid is None or tid is None:
        pytest.skip("roster incomplet offline")

    # On prend la 1re tuile lointaine que le NATIF accepte reellement (portee de mouvement).
    live_pre = _live_units(rpc, rid)[sq_t]["hp"]
    landed = None
    from engine.runner.operations.triggers.base import _hex_dist
    for t in far:
        got = _move_live(rpc, rid, sq_c, board, t)
        if got is not None and (_hex_dist(board, t_tile, got, 3) or 0) >= 2:
            landed = got
            break
    if landed is None:
        pytest.skip("le natif n'a pas laisse le Spyder s'eloigner a >= 2 hex")
    live_delta = _live_units(rpc, rid)[sq_t]["hp"] - live_pre

    off_pre = _hp(state, tid)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(MoveUnitMessage(unit_id=cid, to=board.coord(landed)))
    off_delta = _hp(state, tid) - off_pre

    print("\n[FCA/far] arrivee a dist %s : live=%d offline=%d"
          % (_hex_dist(board, t_tile, landed, 3), live_delta, off_delta))
    assert live_delta == 0, "le natif a repare a distance (%d) -- lecture du selecteur a revoir" % live_delta
    assert off_delta == 0, "le port a repare a distance (%d)" % off_delta


def test_full_health_ally_is_not_repaired(build_runner, rpc, monkeypatch):
    """CONTROLE -- l'etage `Repairable` (`AttackQuery$$EntityCanBeRepaired`, surcharge 3 args).

    Meme montage, une SEULE variable change : l'allie n'est PAS blesse (`--hp-player` seul ecrit
    `Health` ET `RemainingHealth`, donc l'unite reste a 100 %). `IsDamagedUnit` est faux, aucun
    disjunct de remplacement n'est porte -> le selecteur est vide -> `AmountIsZero` -> rien.
    C'est ce test qui separe « le passif cible les allies adjacents » de « le passif cible les
    allies adjacents REPARABLES »."""
    stage = _stage(rpc, build_runner, monkeypatch, damaged=None, hp_player=HP_PLAYER)
    rid = stage["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    U, sq_c, sq_t = _squads(rpc, rid, S.REPAIREE_VIS)
    if sq_c is None or sq_t is None:
        pytest.skip("repareur/cible absents live")
    occupied = {board.id_at(u["col"], u["row"]) for u in U.values()}
    t_tile = board.id_at(U[sq_t]["col"], U[sq_t]["row"])
    c_tile = board.id_at(U[sq_c]["col"], U[sq_c]["row"])
    dests = _free_tiles_at_distance(board, occupied, t_tile, 1, 1, exclude=(c_tile,))
    if not dests:
        pytest.skip("aucune tuile libre adjacente a la cible")

    state = _capture(rpc, rid, board)
    if state is None:
        pytest.skip("capture pre-move KO")
    cid, tid = _by_vis(state, REPAIRER), _by_vis(state, S.REPAIREE_VIS)
    if cid is None or tid is None:
        pytest.skip("roster incomplet offline")
    hc = state.get_entity(tid).get_component(HealthComponent)
    if int(hc.hp) < int(hc.hp_max):
        pytest.skip("le montage n'a pas livre une cible a PLEINS PV (hp=%d max=%d)"
                    % (int(hc.hp), int(hc.hp_max)))

    off_pre = _hp(state, tid)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(MoveUnitMessage(unit_id=cid, to=board.coord(dests[0])))
    off_delta = _hp(state, tid) - off_pre

    live_pre = _live_units(rpc, rid)[sq_t]["hp"]
    _move_live(rpc, rid, sq_c, board, dests[0])
    live_delta = _live_units(rpc, rid)[sq_t]["hp"] - live_pre

    print("\n[FCA/full] allie a 100%% : live=%d offline=%d" % (live_delta, off_delta))
    assert live_delta == 0, "le natif a repare une cible pleine (%d)" % live_delta
    assert off_delta == 0, "le port a repare une cible pleine (%d)" % off_delta


# Roster de GENERALISATION -- allie BLESSE mais NON MECANIQUE. `ultraApothecary` : Imperial, non
# mecanique, SOIGNABLE (heal-type 0) mais PAS reparable (heal-type 1). C'est le discriminant exact de
# l'etage `UnitsAffectedByHealType(., 1)`, et il ne peut pas se jouer sur `_repair_stage` (mesure :
# `orksWarboss` ET `orksKillaKan` portent eux aussi le trait `Mechanical`).
NON_MECH_ALLY = "ultraApothecary"


def test_non_mechanical_ally_is_not_repaired(build_runner, rpc, monkeypatch):
    """CONTROLE -- l'etage `UnitsAffectedByHealType(source, 1 = Mechanical)`.

    L'allie adjacent est BLESSE et le Spyder termine son deplacement a son contact, mais il n'est
    pas mecanique : `IsAffectedByHealType(unit, 1)` est faux (`HasTrait(0x421
    AffectedByHealAndRepair)` absent, `IsMechanical` faux) -> il sort du selecteur AVANT meme le
    filtre `Repairable`. Sans ce test, le passif deviendrait un soin universel.

    GENERALISATION : roster different du montage principal ; le seul point commun est le passif."""
    stage = _stage(rpc, build_runner, monkeypatch, repairee=NON_MECH_ALLY)
    rid = stage["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    U, sq_c, sq_t = _squads(rpc, rid, NON_MECH_ALLY)
    if sq_c is None or sq_t is None:
        pytest.skip("repareur/cible absents live")
    occupied = {board.id_at(u["col"], u["row"]) for u in U.values()}
    t_tile = board.id_at(U[sq_t]["col"], U[sq_t]["row"])
    c_tile = board.id_at(U[sq_c]["col"], U[sq_c]["row"])
    dests = _free_tiles_at_distance(board, occupied, t_tile, 1, 1, exclude=(c_tile,))
    if not dests:
        pytest.skip("aucune tuile libre adjacente a la cible")

    state = _capture(rpc, rid, board)
    if state is None:
        pytest.skip("capture pre-move KO")
    cid, tid = _by_vis(state, REPAIRER), _by_vis(state, NON_MECH_ALLY)
    if cid is None or tid is None:
        pytest.skip("roster incomplet offline")
    from engine.runner.abilities.attack_query import is_affected_by_heal_type
    hc = state.get_entity(tid).get_component(HealthComponent)
    assert int(hc.hp) < int(hc.hp_max), "la cible de controle doit etre BLESSEE"
    assert not is_affected_by_heal_type(state, tid, 1), (
        "%s ne doit PAS etre affecte par le heal-type 1 (Mechanical)" % NON_MECH_ALLY)
    assert is_affected_by_heal_type(state, tid, 0), (
        "%s doit etre affecte par le heal-type 0 -- c'est le discriminant heal/repair" % NON_MECH_ALLY)

    off_pre = _hp(state, tid)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(MoveUnitMessage(unit_id=cid, to=board.coord(dests[0])))
    off_delta = _hp(state, tid) - off_pre

    live_pre = _live_units(rpc, rid)[sq_t]["hp"]
    _move_live(rpc, rid, sq_c, board, dests[0])
    live_delta = _live_units(rpc, rid)[sq_t]["hp"] - live_pre

    print("\n[FCA/non-mech] allie non mecanique blesse : live=%d offline=%d"
          % (live_delta, off_delta))
    assert live_delta == 0, "le natif a REPARE une unite non mecanique (%d)" % live_delta
    assert off_delta == 0, "le port a repare une unite non mecanique (%d)" % off_delta


def test_finish_turn_without_moving_also_fires(build_runner, rpc, monkeypatch):
    """GENERALISATION -- le SECOND emetteur natif d'`On(0x1c)`.

    `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` pose lui aussi
    `UnitFlag.ArrivedAtFinalTile` et publie `On(0x1c)` ssi le flag venait d'etre ajoute ET que la fin
    de tour n'est pas FORCEE. Un Spyder qui NE BOUGE PAS et cloture son tour doit donc reparer
    exactement pareil. Ce chemin est COTE PORT UNIQUEMENT (le harnais live n'a pas d'action
    « finir le tour de cette unite sans rien faire » qui n'entraine pas la suite du tour) -- il est
    verrouille par la CONTINUITE avec le test live du move : MEME montant, MEME cible, MEME capture,
    seul le vecteur change."""
    stage = _stage(rpc, build_runner, monkeypatch)
    rid = stage["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    state = _capture(rpc, rid, board)
    if state is None:
        pytest.skip("capture KO")
    cid, tid = _by_vis(state, REPAIRER), _by_vis(state, S.REPAIREE_VIS)
    if cid is None or tid is None:
        pytest.skip("roster incomplet offline")
    from engine.runner.operations.triggers.base import _hex_dist
    from engine.runner.components import PositionComponent
    cp = state.get_entity(cid).get_component(PositionComponent)
    tp = state.get_entity(tid).get_component(PositionComponent)
    d = _hex_dist(board, board.id_at(cp.col, cp.row), board.id_at(tp.col, tp.row), 3)
    if d != 1:
        pytest.skip("le Spyder n'est pas deja adjacent au spawn (dist=%s) -- ce test ne bouge PAS" % d)
    amount = _expected_amount(state, cid)
    assert amount > 0

    off_pre = _hp(state, tid)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(FinishUnitTurnMessage(unit_id=cid))
    off_delta = _hp(state, tid) - off_pre
    print("\n[FCA/finish] fin de tour SANS bouger : offline=%d (hpToRepair=%d)" % (off_delta, amount))
    assert off_delta == amount, (
        "la cloture de tour doit publier On(0x1c) et reparer %d (obtenu %d)" % (amount, off_delta))


# Roster de GENERALISATION -- DEUX allies mecaniques blesses, pour que `PickRandomly(., 1)` ait un
# VRAI choix. C'est le scenario le plus discriminant du lot : il exerce a la fois l'ORDRE du pool
# (`AdjacentFriends` = ordre d'enumeration natif des tuiles) et le NOMBRE de tirages PRNG.
TWO_ALLIES = ("admecRuststalker", "necroWarden")
TWO_ALLIES_BUILD = ["--p-units", "%s,%s,%s" % (REPAIRER, TWO_ALLIES[0], TWO_ALLIES[1]),
                    "--a-units", "orksWarboss,orksKillaKan",
                    "--board", "MC1_67",
                    "--hp-player", str(HP_PLAYER),
                    "--unit-stat", "%s:RemainingHealth=1;%s:RemainingHealth=1" % TWO_ALLIES,
                    "--advance", "0"]


def test_pick_randomly_picks_the_same_target_as_native(build_runner, rpc):
    """GENERALISATION LA PLUS DISCRIMINANTE -- `PickRandomly(., 1)` sur un pool de DEUX.

    Le Spyder termine son deplacement sur une tuile adjacente aux DEUX allies mecaniques blesses. Le
    selecteur rend donc 2 candidats et le natif en TIRE un. Deux choses seulement peuvent faire
    diverger le port, et ce test les exerce ENSEMBLE :

      1. l'ORDRE du pool -- `PickRandomAmountSelector$$Select` tire par `ElementAt(idx)` dans
         `source.Select(entities).ToList()`, SANS aucun tri : l'ordre source decide QUI est pique ;
      2. le NOMBRE de tirages -- `CreateTrigger` et `CreateBehaviour` appellent CHACUN
         `GetTargetSelector()`, donc chacun a SON `PickRandomly` : deux tirages par fire.

    CONTRE-EPREUVE MESUREE (elle est ce qui rend ce test discriminant, et pas seulement vert) : sur
    l'etat MT capture, `next_internal(0, 2)` rend la sequence `[0, 1, ...]` -- les deux premiers
    tirages DIFFERENT. Le port choisit `pool[1]`, comme le natif ; un port qui ne consommerait qu'UN
    tirage prendrait `pool[0]`, c'est-a-dire l'AUTRE allie. Le test verifie donc aussi cette
    non-degenerescence, pour ne jamais devenir un vert de facade si la sequence changeait."""
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.operations.triggers.base import _hex_dist
    rid = build_runner("777", extra=TWO_ALLIES_BUILD)["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    U = _live_units(rpc, rid)
    sq = {u.get("visualId"): s for s, u in U.items()}
    sq_c = sq.get(REPAIRER)
    sq_a = [sq.get(a) for a in TWO_ALLIES]
    if sq_c is None or any(s is None for s in sq_a):
        pytest.skip("roster incomplet live")
    occupied = {board.id_at(u["col"], u["row"]) for u in U.values()}
    tiles_a = [board.id_at(U[s]["col"], U[s]["row"]) for s in sq_a]
    dest = next((t for t in board.by_id
                 if t not in occupied and board.walkable(t)
                 and all(_hex_dist(board, t, ta, 1) == 1 for ta in tiles_a)), None)
    if dest is None:
        pytest.skip("aucune tuile libre adjacente aux DEUX allies -- scenario non montable")

    state = _capture(rpc, rid, board)
    if state is None:
        pytest.skip("capture pre-move KO")
    assert state.rng is not None, (
        "le PRNG n'a pas ete cale (dumpRng) -- sans lui `PickRandomly` degenere en pool[:1] et ce "
        "test ne mesure plus rien")
    by = {}
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None:
            by[getattr(sc.ctx, "visual_id", None)] = uid
    cid = by.get(REPAIRER)
    aids = [by.get(a) for a in TWO_ALLIES]
    if cid is None or any(i is None for i in aids):
        pytest.skip("roster incomplet offline")

    # NON-DEGENERESCENCE : les deux premiers tirages doivent DIFFERER, sinon le scenario ne separe
    # plus « un tirage » de « deux tirages » et le vert ne prouverait rien.
    peek = IntBasedMersenneTwister()
    peek.mt = list(state.rng.mt)
    peek.mti = state.rng.mti
    draws = [peek.next_internal(0, 2), peek.next_internal(0, 2)]
    if draws[0] == draws[1]:
        pytest.skip("sequence PRNG degeneree (%s) -- le scenario ne discrimine pas ici" % draws)

    pre_off = {a: _hp(state, i) for a, i in zip(TWO_ALLIES, aids)}
    runner = Runner(state).install_default_handlers(20)
    runner.apply(MoveUnitMessage(unit_id=cid, to=board.coord(dest)))
    off = {a: _hp(state, i) - pre_off[a] for a, i in zip(TWO_ALLIES, aids)}

    pre_live = {a: U[sq[a]]["hp"] for a in TWO_ALLIES}
    _move_live(rpc, rid, sq_c, board, dest)
    U2 = _live_units(rpc, rid)
    live = {a: U2[sq[a]]["hp"] - pre_live[a] for a in TWO_ALLIES}

    print("\n[FCA/pool2] tirages=%s live=%s offline=%s" % (draws, live, off))
    assert sum(live.values()) > 0, (
        "le natif n'a repare AUCUN des deux allies -- montage invalide, pas un verdict de port")
    assert sum(1 for v in live.values() if v > 0) == 1, (
        "le natif a repare %d allies : `PickRandomly(., 1)` doit n'en choisir qu'UN (live=%s)"
        % (sum(1 for v in live.values() if v > 0), live))
    assert off == live, (
        "le port n'a pas choisi la MEME cible que le natif : live=%s offline=%s (tirages=%s)"
        % (live, off, draws))


def test_fabricator_claw_array_is_registered():
    """GARDE DE NON-REGRESSION -- le passif est au registre, sur le BON vecteur et avec le BON id.

    C'est le cliquet qui a manque a #299 : l'ability existait au decompile, le vecteur `On(0x1c)`
    existait cote port, et pourtant RIEN ne les reliait. Un `pop` de cette entree est exactement la
    mutation adversariale qui rend le lot rouge."""
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    from engine.runner.operations.triggers.loki.fabricator_claw_array import (
        FabricatorClawArrayAbility)
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    assert FabricatorClawArrayAbility in ABILITY_TRIGGERS.get("FabricatorClawArray", ()), (
        "passif `FabricatorClawArray` absent d'ABILITY_TRIGGERS -- c'est le residu N20")
    assert FabricatorClawArrayAbility.event_id == int(EventTriggerType.ArrivedAtFinalTile), (
        "vecteur != On(0x1c = ArrivedAtFinalTile)")
    assert (FabricatorClawArrayAbility.TRIGGERED_ABILITY_ID
            == int(TriggeredAbilityType.FabricatorClawArray) == 1006)
    # Le porteur : `necroSpyder.passiveAbilities` DOIT contenir l'ability, sinon
    # `collect_triggered_abilities` (qui resout par gameconfig) ne l'instancie jamais.
    import gameconfig as GC
    assert "FabricatorClawArray" in ((GC.unit(REPAIRER) or {}).get("passiveAbilities") or [])
