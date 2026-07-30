"""#299 -- la face EXECUTION de la REPARATION REGULIERE, confrontee au LIVE.

CE QUE CES TESTS VERROUILLENT. #298 a etabli que le rail de DECISION fonctionne de bout en bout :
l'ability est dans `ActiveAbilityComponent.Abilities`, le ciblage l'accepte, `PredictRepair` la
predit, l'IA la PROPOSE. Et pourtant, cote COMBAT, il ne se passait RIEN : ni `28 Repair` ni
`1119 Repair_GalvanicField` n'etaient dans `ABILITY_CLASSES`, donc `AbilityHandler` rendait
`ported: False`, posait les flags de tour et NE MUTAIT AUCUN PV. Cast accepte, tour consomme, zero
soin. Ni erreur ni crash -- la pire forme de degradation, et celle qu'un entrainement RL apprend a
exploiter (« reparer » gratuitement).

CRITERE BINAIRE : apres le cast, les PV de la cible AUGMENTENT-ils du montant attendu, et le port
rend-il le MEME delta que le natif ?

CHAINE PORTEE (cf. `engine/runner/operations/repair.py` et `engine/runner/abilities/repair.py`) :
    `RepairAbility$$CreateBehaviour` -> feuille `DSLBehaviors$$Repair`
      -> `Core.Services.OperationProcessor$$RepairUnit`
      -> `IdunBattle.Operations.RepairUnitOperation$$Execute`
           gate `AttackQuery$$EntityCanBeRepaired` + `DamagePrediction$$PredictRepair`
           + `FillUpStatComponent$$FillUp`  <-- la mutation

Le MONTAGE est la fixture NOMMEE `_repair_stage` (#298, PR #309), reutilisee TELLE QUELLE : un
repareur trait `Mechanic` + un ami MECANIQUE BLESSE (`--unit-stat <cible>:RemainingHealth=2000`,
JAMAIS `--hp-player`, qui ecrit `Health` ET `RemainingHealth` et laisse donc la cible a 100 %),
`advance=0`.

ASCII only (console cp1252).
"""
from __future__ import annotations

import os
import sys

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.components import HealthComponent, StatsComponent
from engine.runner.abilities.repair import REGULAR_REPAIR_IDS, repair_amount
from engine.runner.operations.repair import RepairUnitOperation
from engine.entities.pathfinding.board import Board

sys.path.insert(0, os.path.dirname(__file__))
import _repair_stage as S                                 # noqa: E402

# Les DEUX membres de `idun...StaticBattleRules.ActiveAbility$$IsRegularRepair`, avec leur porteur.
# `admecDominus` = trait `Mechanic` SEUL -> `Repair` (28) ; `admecManipulus` porte en plus le passif
# `GalvanicField`, qui specialise le slot `RepairType` -> `Repair_GalvanicField` (1119).
#
# `necroSpyder` est le TROISIEME porteur, et il a son test dedie plus bas : son passif
# `FabricatorClawArray` ajoute une SECONDE reparation au meme instant (porte par #303), donc le delta
# HP brut s'y decompose en DEUX termes (cf. `test_necro_spyder_hits_factor_and_fabricator_claw` ici,
# et le lot ISOLE `test_fabricator_claw_array_live.py`).
PORTERS = [("admecDominus", 28), ("admecManipulus", 1119)]


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


def _hc(state, uid):
    return state.get_entity(uid).get_component(HealthComponent)


def _live_units(rpc, rid):
    r = rpc("observeBattle", {"runnerId": rid}, 40)
    return {u["squadId"]: u for u in (r.get("units") or [])} if _ok(r) else {}


def _stage(rpc, build_runner, monkeypatch, repairer):
    """Montage #298 avec le repareur voulu (l'id d'ability derive du PORTEUR, pas d'un argument)."""
    monkeypatch.setattr(S, "REPAIRER_VIS", repairer)
    return S.build_stage(rpc, build_runner=build_runner,
                         hp_player=None, advance=0, damaged_repairee=2000)


def _approach(rpc, rid, board, sq_caster, sq_target):
    """DEPLACE le repareur jusqu'a une tuile LIBRE adjacente a la cible si besoin.

    `RepairAbility$$.ctor` pose `RANGE_ADJACENT` (`TargetingRange` statics+0x30) : le cast n'est
    legal qu'au CONTACT. Un roster dont les spawns ne sont pas voisins ne doit PAS produire un skip
    (« bloque par la geometrie ») -- on conduit les positions. Le masque `0x8002` ne pose PAS
    `CasterHasNotMoved` (0x10), donc bouger AVANT de caster reste legal.

    Rend True si les deux sont adjacents a la sortie."""
    U = _live_units(rpc, rid)
    if sq_caster not in U or sq_target not in U:
        return False
    ct = board.id_at(U[sq_caster]["col"], U[sq_caster]["row"])
    tt = board.id_at(U[sq_target]["col"], U[sq_target]["row"])
    if ct is None or tt is None:
        return False
    if ct in board.neighbours(tt):
        return True
    occ = {board.id_at(u["col"], u["row"]) for u in U.values()}
    # tuiles libres adjacentes a la cible, les plus proches du repareur d'abord
    cands = [n for n in board.neighbours(tt)
             if n in board.by_id and board.walkable(n) and n not in occ]
    cands.sort(key=lambda n: abs(board.coord(n)[0] - U[sq_caster]["col"])
               + abs(board.coord(n)[1] - U[sq_caster]["row"]))
    for n in cands:
        c, r = board.coord(n)
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": sq_caster, "to": {"col": c, "row": r}}}, 40)
        U2 = _live_units(rpc, rid)
        ct2 = board.id_at(U2[sq_caster]["col"], U2[sq_caster]["row"]) if sq_caster in U2 else None
        if ct2 is not None and ct2 in board.neighbours(tt):
            return True
    return False


def _capture(rpc, rid, board):
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not (_ok(dv) and _ok(ob) and _ok(snap)):
        return None, None
    return load_state(dv, ob, snap, board=board), ob


@pytest.mark.parametrize("repairer,ability_id", PORTERS)
def test_repair_restores_health_live_and_offline(build_runner, rpc, monkeypatch,
                                                 repairer, ability_id):
    """LE test du residu : le cast REPARE, du MEME montant live et offline.

    Le montant attendu n'est PAS un scalaire hardcode : il est RE-DERIVE du port
    (`repair_amount` = `RepairAbility$$RepairAmount` = `Attack(caster) x Max(WeaponHighestHits, 1)`)
    puis cape par ce qui manque a la cible (`FillUpStatComponent$$MaxFillUp`). Les trois valeurs
    doivent coincider : `live_delta == offline_delta == expected > 0`."""
    stage = _stage(rpc, build_runner, monkeypatch, repairer)
    rid = stage["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    # 1) POSITIONS D'ABORD : on amene le repareur au contact (RANGE_ADJACENT) AVANT toute capture,
    #    pour que l'etat offline soit bien celui du cast et non celui du spawn.
    U0 = _live_units(rpc, rid)
    sq_c = next((sq for sq, u in U0.items() if u.get("visualId") == repairer), None)
    sq_t = next((sq for sq, u in U0.items() if u.get("visualId") == S.REPAIREE_VIS), None)
    if sq_c is None or sq_t is None:
        pytest.skip("repareur/cible absents live")
    assert _approach(rpc, rid, board, sq_c, sq_t), (
        "impossible d'amener %s au contact de %s -- le montage doit CONDUIRE les positions"
        % (repairer, S.REPAIREE_VIS))
    # 2) capture PRE-cast (positions finales)
    state, ob = _capture(rpc, rid, board)
    if state is None:
        pytest.skip("capture pre-cast KO")
    cid = _by_vis(state, repairer)
    tid = _by_vis(state, S.REPAIREE_VIS)
    if cid is None or tid is None:
        pytest.skip("roster incomplet offline (%s / %s)" % (cid, tid))

    hc = _hc(state, tid)
    assert int(hc.hp) < int(hc.hp_max), (
        "le montage doit livrer une cible BLESSEE (--unit-stat RemainingHealth) ; hp=%d max=%d"
        % (int(hc.hp), int(hc.hp_max)))
    amount = repair_amount(state, cid)
    expected = min(int(amount), int(hc.hp_max) - int(hc.hp))
    assert expected > 0, "montant de reparation degenere (amount=%d)" % amount

    # --- OFFLINE : le port sur la capture PRE-cast -------------------------------------------------
    off_pre = int(hc.hp)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=cid, target_id=tid, ability_type=ability_id))
    last = runner.ability_handler.last or {}
    assert last.get("ported"), (
        "ability %d NON routee cote combat (%s) -- c'est EXACTEMENT le residu #299" % (ability_id, last))
    off_delta = int(_hc(state, tid).hp) - off_pre

    # --- LIVE : le meme cast dans le runner natif --------------------------------------------------
    U = _live_units(rpc, rid)
    live_pre = U[sq_t]["hp"]
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": sq_c, "targetId": sq_t, "abilityType": ability_id}}, 60)
    U2 = _live_units(rpc, rid)
    if sq_t not in U2:
        pytest.skip("observe post-cast KO")
    live_delta = U2[sq_t]["hp"] - live_pre

    print("\n[REPAIR/%s id=%d] amount=%d expected=%d live=%d offline=%d"
          % (repairer, ability_id, amount, expected, live_delta, off_delta))
    assert live_delta > 0, (
        "le natif n'a RIEN repare (delta=%d) -- montage invalide, pas un verdict de port" % live_delta)
    assert off_delta == expected, "offline %d != attendu %d" % (off_delta, expected)
    assert live_delta == off_delta, "live %d != offline %d" % (live_delta, off_delta)


def test_necro_spyder_hits_factor_and_fabricator_claw(build_runner, rpc, monkeypatch):
    """GENERALISATION la plus DISCRIMINANTE du lot -- et c'est elle qui a trouve le residu N20.

    `necroSpyder` est le SEUL porteur du trait `Mechanic` dont l'arme a **5 coups**
    (`gameconfig.unit("necroSpyder").weapons[0].hits`) ; les deux AdMec en ont 1, donc chez eux le
    facteur `Max(WeaponHighestHits, 1)` de `RepairAbility$$RepairAmount` est INVISIBLE (x1). Ici il
    vaut x5 : un port qui l'aurait oublie rendrait `Attack` (1205) au lieu de `Attack x 5` (6025).

    Le montage est celui de la MESURE, pas du confort : `--hp-player 300000` + `RemainingHealth=1`
    donnent un manque de 299999, tres au-dessus du montant -- sans quoi `FillUpStatComponent$$MaxFillUp`
    sature et le montant BRUT reste invisible (piege MESURE : avec le montage standard,
    `manque = 6032` masquait deja tout ecart au-dela de 6032).

    DEUX REPARATIONS, UN SEUL TOUR (residu N20, DECOUVERT ICI par #299, PORTE par #303) -- le passif
    `FabricatorClawArray` du Spyder :

        IdunBattleLogic.Entities.Abilities.Active.Loki.FabricatorClawArrayAbility$$CreateTrigger
            = On(0x1c = ArrivedAtFinalTile) & OwnerIsActor & !AmountIsZero(GetTargetSelector())
        ...$$CreateBehaviour
            = Repair(Owner, GetTargetSelector(), Direct(ConfigVar(0x24 = hpToRepair)), ForRepair)

    Le cast de `Repair` TERMINE le tour (`AddFlagsAfterAbilityExecution` -> `FinishUnitTurnOperation`
    -> `UnitFlags.Add(ArrivedAtFinalTile = 1)`), ce qui reveille aussitot ce trigger. AVANT #303 le
    port ne portait QUE la voie active : natif 10457 contre port 6025.

    L'assertion est une EGALITE EXACTE des DEUX cotes, et elle se DECOMPOSE explicitement selon le
    vecteur qui a publie `On(0x1c)` -- car `_approach` peut avoir DEPLACE le Spyder :
      * s'il n'a PAS bouge (deja au contact au spawn), le flag n'est pas encore pose a la capture :
        le cast le pose, le passif tire APRES, donc `delta == RepairAmount + hpToRepair` ;
      * s'il a bouge, `MoveUnitOperation` a deja publie `On(0x1c)` AVANT la capture (le passif a
        deja repare, et `combatSnapshot.unitFlags` porte le flag) : le cast ne le re-publie pas,
        donc `delta == RepairAmount`.
    Dans les deux cas `live == offline`. Le test verrouille du meme coup le facteur x5 (sans lui
    l'egalite tombe de 4820) et le montant du passif. Le passif a par ailleurs ses propres tests
    ISOLES (`test_fabricator_claw_array_live.py`, ou le deplacement seul l'exerce sans aucun cast)."""
    from engine.entities.effects.magnitude import ability_var
    from engine.runner.components import UnitFlagsComponent
    monkeypatch.setattr(S, "REPAIRER_VIS", "necroSpyder")
    stage = S.build_stage(rpc, build_runner=build_runner, hp_player=300000, advance=0,
                          damaged_repairee=1)
    rid = stage["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    U0 = _live_units(rpc, rid)
    sq_c = next((sq for sq, u in U0.items() if u.get("visualId") == "necroSpyder"), None)
    sq_t = next((sq for sq, u in U0.items() if u.get("visualId") == S.REPAIREE_VIS), None)
    if sq_c is None or sq_t is None:
        pytest.skip("repareur/cible absents live")
    assert _approach(rpc, rid, board, sq_c, sq_t), "impossible d'amener le Spyder au contact"
    state, _ = _capture(rpc, rid, board)
    if state is None:
        pytest.skip("capture pre-cast KO")
    cid, tid = _by_vis(state, "necroSpyder"), _by_vis(state, S.REPAIREE_VIS)
    if cid is None or tid is None:
        pytest.skip("roster incomplet offline")

    sc = state.get_entity(cid).get_component(StatsComponent)
    ctx = sc.ctx
    from engine.entities.stats import StatType
    atk, hits = int(ctx.stat(StatType.ATTACK)), int(ctx.normal_weapon_hits)
    amount = repair_amount(state, cid)
    assert hits == 5, "le montage perd son pouvoir discriminant si hits != 5 (hits=%d)" % hits
    assert amount == atk * hits, "RepairAmount %d != Attack %d x hits %d" % (amount, atk, hits)

    hc = _hc(state, tid)
    assert int(hc.hp_max) - int(hc.hp) > amount * 3, (
        "le manque doit DEPASSER largement le montant, sinon MaxFillUp sature et masque l'ecart")
    # Le flag est-il DEJA pose a la capture ? (= `_approach` a deplace le Spyder, donc
    # `MoveUnitOperation$$Execute` a deja publie `On(0x1c)` et le passif a deja tire.)
    cfl = state.get_entity(cid).get_component(UnitFlagsComponent)
    already_arrived = bool(cfl is not None
                           and cfl.has(UnitFlagsComponent.ARRIVED_AT_FINAL_TILE))
    off_pre = int(hc.hp)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=cid, target_id=tid, ability_type=28))
    assert (runner.ability_handler.last or {}).get("ported")
    off_delta = int(_hc(state, tid).hp) - off_pre

    live_pre = _live_units(rpc, rid)[sq_t]["hp"]
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": sq_c, "targetId": sq_t, "abilityType": 28}}, 60)
    live_delta = _live_units(rpc, rid)[sq_t]["hp"] - live_pre

    lvl = getattr(ctx, "passive_ability_level", None) or getattr(ctx, "active_ability_level", None)
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
    bonus = ability_var("FabricatorClawArray", "hpToRepair", lvl, multiplier_pct=mult)
    assert bonus, "hpToRepair de FabricatorClawArray illisible (lvl=%s)" % lvl
    expected = amount + (0 if already_arrived else int(bonus))
    print("\n[REPAIR/necroSpyder] attack=%d hits=%d amount=%d offline=%d live=%d "
          "FabricatorClawArray(lvl=%s mult=%d)=%s already_arrived=%s attendu=%d"
          % (atk, hits, amount, off_delta, live_delta, lvl, mult, bonus, already_arrived, expected))
    assert off_delta == expected, (
        "offline %d != RepairAmount %d + FabricatorClawArray %d (already_arrived=%s)"
        % (off_delta, amount, 0 if already_arrived else int(bonus), already_arrived))
    assert live_delta == off_delta, (
        "live %d != offline %d -- l'ecart n'est plus explique par le passif (porte par #303)"
        % (live_delta, off_delta))


def test_repair_is_capped_by_what_is_missing(repair_stage, build_runner, rpc):
    """GENERALISATION DISCRIMINANTE -- `FillUpStatComponent$$MaxFillUp` capé par le MANQUE.

    Le test principal blesse la cible a fond (`RemainingHealth=2000`) : le manque y depasse
    largement le montant, donc `Min(amount, max - current)` rend `amount` et le CAP N'EST PAS
    EXERCE. Ici on inverse : la cible ne perd que 100 PV, tres en dessous du montant (~5000). Le
    natif ne doit restaurer QUE 100 -- un port sans le `Min` ferait deborder les PV au-dela du
    maximum, et aucun des autres tests ne le verrait.

    Le `hp_max` n'est pas devinable avant le build : on le LIT sur le montage deja monte
    (`repair_stage`), puis on remonte un runner avec `RemainingHealth = hp_max - 100`."""
    board0 = _board(rpc, repair_stage["rid"])
    if board0 is None:
        pytest.skip("boardGraph indispo")
    st0, _ = _capture(rpc, repair_stage["rid"], board0)
    if st0 is None:
        pytest.skip("capture KO")
    t0 = _by_vis(st0, S.REPAIREE_VIS)
    if t0 is None:
        pytest.skip("cible absente offline")
    hp_max = int(_hc(st0, t0).hp_max)
    missing = 100

    stage = S.build_stage(rpc, build_runner=build_runner, hp_player=None, advance=0,
                          damaged_repairee=hp_max - missing)
    rid = stage["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    U0 = _live_units(rpc, rid)
    sq_c = next((sq for sq, u in U0.items() if u.get("visualId") == S.REPAIRER_VIS), None)
    sq_t = next((sq for sq, u in U0.items() if u.get("visualId") == S.REPAIREE_VIS), None)
    if sq_c is None or sq_t is None:
        pytest.skip("repareur/cible absents live")
    assert _approach(rpc, rid, board, sq_c, sq_t), "impossible d'amener le repareur au contact"
    state, _ = _capture(rpc, rid, board)
    if state is None:
        pytest.skip("capture pre-cast KO")
    cid, tid = _by_vis(state, S.REPAIRER_VIS), _by_vis(state, S.REPAIREE_VIS)
    if cid is None or tid is None:
        pytest.skip("roster incomplet offline")
    hc = _hc(state, tid)
    real_missing = int(hc.hp_max) - int(hc.hp)
    amount = repair_amount(state, cid)
    if real_missing <= 0 or real_missing >= amount:
        pytest.skip("le montage n'exerce pas le cap (manque=%d amount=%d)" % (real_missing, amount))

    off_pre = int(hc.hp)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=cid, target_id=tid,
                                      ability_type=REGULAR_REPAIR_IDS[1]))
    assert (runner.ability_handler.last or {}).get("ported")
    off_delta = int(_hc(state, tid).hp) - off_pre
    assert int(_hc(state, tid).hp) <= int(hc.hp_max), "les PV ont DEBORDE le maximum"

    live_pre = _live_units(rpc, rid)[sq_t]["hp"]
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": sq_c, "targetId": sq_t,
        "abilityType": REGULAR_REPAIR_IDS[1]}}, 60)
    live_delta = _live_units(rpc, rid)[sq_t]["hp"] - live_pre
    print("\n[REPAIR/cap] manque=%d amount=%d live=%d offline=%d"
          % (real_missing, amount, live_delta, off_delta))
    assert off_delta == real_missing, "offline %d != manque %d (cap MaxFillUp)" % (off_delta, real_missing)
    assert live_delta == off_delta, "live %d != offline %d" % (live_delta, off_delta)


def test_repair_is_a_noop_on_a_full_health_target(repair_stage, rpc):
    """CONTROLE -- une cible a 100 % : le gate `AttackQuery$$EntityCanBeRepaired` refuse.

    Sans ce test, le precedent ne prouve rien : « ca repare » et « ca repare toujours, meme quand il
    ne faut pas » rendent le meme vert. On remet la cible a PLEINS PV dans l'etat OFFLINE (une seule
    variable change) et on verifie que l'Operation rend 0 -- `IsDamagedUnit` faux, aucun disjunct de
    remplacement porte."""
    rid = repair_stage["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    state, _ = _capture(rpc, rid, board)
    if state is None:
        pytest.skip("capture KO")
    cid = _by_vis(state, S.REPAIRER_VIS)
    tid = _by_vis(state, S.REPAIREE_VIS)
    if cid is None or tid is None:
        pytest.skip("roster incomplet offline")
    hc = _hc(state, tid)
    hc.hp = int(hc.hp_max)                                  # SEULE variable modifiee
    assert RepairUnitOperation.execute(state, cid, tid, 9999) == 0, (
        "une cible a 100 %% de PV n'est pas reparable (IsDamagedUnit faux)")
    assert int(hc.hp) == int(hc.hp_max), "l'Operation refusee ne doit RIEN muter"


# Roster de GENERALISATION -- il n'existe AUCUNE unite non mecanique dans le montage `_repair_stage`
# (mesure : `orksWarboss` ET `orksKillaKan` portent le trait `Mechanical`, comme les deux AdMec), donc
# le controle « cible non mecanique » ne peut pas s'y jouer. On monte un roster DEDIE plutot que de
# toucher a la fixture partagee (#278 la lit en parallele). `ultraApothecary` : Imperial, non
# mecanique, soignable mais PAS reparable -- c'est exactement le discriminant heal/repair.
NON_MECH_ALLY = "ultraApothecary"
NON_MECH_BUILD = ["--p-units", "admecDominus,%s" % NON_MECH_ALLY,
                  "--a-units", "orksWarboss",
                  "--board", "MC1_67",
                  "--unit-stat", "%s:RemainingHealth=2000" % NON_MECH_ALLY]


def test_repair_refuses_a_non_mechanical_target(build_runner, rpc):
    """CONTROLE -- `IsAffectedByHealType(target, 1 Mechanical)` : une cible NON mecanique BLESSEE
    n'est pas reparable, meme amie et adjacente. C'est le conjoint qui distingue REPARATION et SOIN
    (`AttackQuery$$EntityCanBeHealed` exige le type 0, son complementaire) -- sans lui, la reparation
    deviendrait un soin universel.

    GENERALISATION : roster, board et blessure differents du test principal ; le seul point commun
    est l'Operation."""
    rid = build_runner("777", extra=NON_MECH_BUILD)["rid"]
    board = _board(rpc, rid)
    if board is None:
        pytest.skip("boardGraph indispo")
    state, _ = _capture(rpc, rid, board)
    if state is None:
        pytest.skip("capture KO")
    cid = _by_vis(state, "admecDominus")
    vid = _by_vis(state, NON_MECH_ALLY)
    if cid is None or vid is None:
        pytest.skip("roster incomplet offline (%s / %s)" % (cid, vid))
    from engine.runner.abilities.attack_query import (entity_can_be_healed,
                                                      is_affected_by_heal_type)
    hv = _hc(state, vid)
    assert int(hv.hp) < int(hv.hp_max), "la cible de controle doit etre BLESSEE"
    assert not is_affected_by_heal_type(state, vid, 1), (
        "%s ne doit PAS etre affecte par le heal-type 1 (Mechanical)" % NON_MECH_ALLY)
    assert is_affected_by_heal_type(state, vid, 0), (
        "%s doit etre affecte par le heal-type 0 -- c'est le discriminant heal/repair" % NON_MECH_ALLY)
    assert entity_can_be_healed(state, cid, vid, scope=0, remove_effects=True), (
        "la meme cible DOIT etre soignable : sans ca le controle ne separe rien")
    pre = int(hv.hp)
    assert RepairUnitOperation.execute(state, cid, vid, 9999) == 0, (
        "une unite non mecanique ne se REPARE pas (IsAffectedByHealType(.,1) faux)")
    assert int(hv.hp) == pre, "l'Operation refusee ne doit RIEN muter"


def test_regular_repair_ids_are_both_in_the_combat_registry():
    """GARDE DE NON-REGRESSION -- les DEUX ids de `IsRegularRepair` sont au registre COMBAT, avec
    leur masque de ciblage ET leur `AbilityAttackType` (le CLIQUET du CLAUDE.md : une ability qui
    entre dans `ABILITY_CLASSES` pose les deux DANS LE MEME COMMIT)."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    for aid in REGULAR_REPAIR_IDS:
        assert aid in ABILITY_CLASSES, "ability %d absente d'ABILITY_CLASSES" % aid
        opts = getattr(ABILITY_CLASSES[aid], "TARGETING_OPTIONS", None)
        assert opts is not None, "ability %d sans TARGETING_OPTIONS" % aid
        # `RepairAbility$$.ctor` : `TargetingOptions..ctor(&opts, 0, &<TargetingRange>+0x30, 2,
        # 0x8002, 0, 0)` -- forme « flags directs », le litteral EST le masque.
        assert opts.rules == 0x8002, "ability %d masque 0x%x != 0x8002" % (aid, opts.rules)
        assert ABILITY_ATTACK_TYPE.get(aid) == AbilityAttackType.Others, (
            "ability %d sans AbilityAttackType.Others (litteral du ctor)" % aid)
