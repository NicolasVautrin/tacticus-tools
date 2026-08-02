"""#131 -- MATERIALISATION des bornes REDUITES de l'ATTAQUE NORMALE (garde LIVE discriminante).

Les cellules min/max d'un coup d'attaque normale ne sont PAS un calcul propre au combat : le
per-coup natif `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` appelle le slot 4
`IdunBattle.Core.Services.DamagePrediction$$PredictAttack` (cache ->
`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw`) puis resout la cellule par le slot 8
`IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` = `Next(min, max+1)`.
`PredictAttackRaw` est aussi la fonction de la PREDICTION -> MEME materialisation des bornes, et le
dernier etage de `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`
est le MULTIPLICATEUR (slot 0x10 ->
`IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers`) :

    v = Fix64.Mul(dmg, multiplier) ; v <= 0 -> 0 ; 0 < v < 1 -> 1 ;
    sinon `FixMath.NET.Fix64$$Round(v, AwayFromZero)`      <-- ARRONDI, pas troncature

CE QUE LA GARDE VERROUILLE (et qui la rendrait ROUGE si la loi etait l'autre) :
  1. le regime EST discriminant (les deux materialisations donnent des cellules DIFFERENTES) ;
  2. ARRONDI == live PER-COUP ;
  3. TRONCATURE != live -> une regression vers `op_Explicit` casse ici.

Montage : `darkaAzrael` (arme melee Power, PiercingRatio 40, 3 coups) contre `astraBullgryn`
(FixedArmor eleve) -> bornes brutes [2250,3376] reduites en [899,1350] (troncature) vs
[900,1350] (arrondi) : la LARGEUR du modulo change, donc la valeur tiree change. Crit et block
neutralises au build (`--crit 0,0`, `--block-target 0,0`) : un seul etage varie.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _combat_replay import _bfs, _ok, _seed_rng    # noqa: E402

ATTACKER = "darkaAzrael"
TARGET = "astraBullgryn"
MAX_TURNS = 20


def _models(dv, ob, snap, rng0, board, att, tgt):
    """Rejoue le MEME coup OFFLINE deux fois sur le MEME etat et le MEME flux RNG, en ne faisant
    varier QUE la materialisation finale des bornes reduites (`round_materialize`). Les deux sont
    FORCES : la garde reste discriminante quelle que soit la valeur par defaut du port."""
    from engine.runner.snapshot import load_state
    from engine.runner.operations.damage import AttackDamageOperation
    # #169 : `damage_ops` est un PACKAGE ; `execute` (attaque NORMALE) resout `apply_all_modifiers`
    # dans les globals de `damage_ops.normal`. Patcher le `__init__` du package serait un NO-OP
    # SILENCIEUX -- les deux modeles rendraient les MEMES cellules ; c'est l'assertion
    # `cells_f != cells_r` (garde de discrimination) qui l'attrape.
    from engine.runner.operations.damage_ops import normal as damage_ops_normal
    from engine.services import damage_prediction as _dp
    from engine.services import fix64 as _fx
    from engine.services.damage_modifiers import apply_all_modifiers as _aam
    from engine.services.damage_modifiers import (
        calculate_base_damage_with_modifiers as _cbdwm)

    # #446-r2 : la materialisation a DEUX porteurs cote port depuis que l'etage MULTIPLICATEUR est
    # mirrore la ou le natif le pose. `apply_pierce_and_modifiers` termine la face ATTAQUANT par
    # `CalculateBaseDamageWithModifiers` (arrondi INCONDITIONNEL, meme a multiplicateur neutre) ;
    # `apply_all_modifiers(round_materialize=...)` porte celle de la face DEFENSEUR. Neutraliser le
    # SEUL second ne produit plus aucun contraste (mesure : cellules identiques (2700, 4050), la
    # garde de discrimination l'a attrape) -- le bras TRONCATURE doit donc neutraliser les DEUX,
    # sinon il ne decrit plus le modele `op_Explicit` qu'il pretend opposer.
    def _mul_only(damage, multiplier=1.0):
        return _fx.Fix64(_fx.mul(_fx.from_number(damage), _fx.mult_raw_from_float(multiplier)))

    def _one(force):
        st = load_state(dv, ob, snap, board=board)
        st.rng = _seed_rng(rng0)
        damage_ops_normal.apply_all_modifiers = (
            lambda v, m, round_materialize=False, _f=force: _aam(v, m, round_materialize=_f))
        _dp.calculate_base_damage_with_modifiers = _cbdwm if force else _mul_only
        try:
            return AttackDamageOperation.execute(st, att, tgt) or {}
        finally:
            damage_ops_normal.apply_all_modifiers = _aam
            _dp.calculate_base_damage_with_modifiers = _cbdwm

    return _one(False), _one(True)


def _reach_melee(rpc, rid, board, attacker, target):
    """Amene l'attaquant au CONTACT hex de la cible (on DEPLACE les unites)."""
    def utile(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if "col" in p else None

    my_player = None
    for _turn in range(MAX_TURNS):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if not _ok(dec):
            return None, "decisionView KO"
        units = dec.get("units") or []
        champ = next((u for u in units if u.get("visualId") == attacker and u.get("alive")), None)
        tgt = next((u for u in units if u.get("visualId") == target and u.get("alive")), None)
        if champ is None or tgt is None:
            return None, "unite manquante"
        if my_player is None:
            my_player = champ.get("owner")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        ctile, ttile = utile(champ), utile(tgt)
        if ctile in board.neighbours(ttile):
            return (champ, tgt), None
        dist = _bfs(board, ttile)
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == champ["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        adj = [(tid, cr) for tid, cr in reach.items() if tid in board.neighbours(ttile)]
        if adj:
            _tid, (col, row) = adj[0]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": champ["id"], "to": {"col": col, "row": row}}}, 40)
            dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            champ = next((u for u in (dec.get("units") or []) if u.get("id") == champ["id"]), None)
            tgt = next((u for u in (dec.get("units") or []) if u.get("id") == tgt["id"]), None)
            return (champ, tgt), None
        pool = [tid for tid in reach if tid in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        best = min(pool, key=lambda t: dist[t])
        col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": champ["id"], "to": {"col": col, "row": row}}}, 40)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
    return None, f"{attacker} n'a pas atteint {target} en melee"


def test_normal_attack_reduced_bounds_are_rounded_live(live_session, rpc, build_runner):
    from engine.entities.pathfinding.board import Board

    b = build_runner("777", extra=["--roster", "1", "--p-units", ATTACKER,
                                   "--a-units", TARGET, "--crit", "0,0",
                                   "--block-target", "0,0"])
    rid = b["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    pair, why = _reach_melee(rpc, rid, board, ATTACKER, TARGET)
    if pair is None:
        pytest.skip(why)
    champ, tgt = pair
    att, tid = champ["id"], tgt["id"]
    norm = next((a for a in (champ.get("abilities") or []) if a.get("kind") == "normal"), None)
    if norm is None:
        pytest.skip("pas d'attaque normale")

    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (isinstance(rng0, dict) and rng0.get("mt")):
        pytest.skip("dumpRng indispo")
    hp_before = next((u.get("hp") for u in (dv.get("units") or []) if u.get("id") == tid), None)

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": norm["id"]}}, 60)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        pytest.skip(f"attaque live KO: {str(res)[:120]}")
    live_ph, dc, db, de = [], False, False, False
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tid and "Amount" in td \
                and td.get("Active_Ability_Type") == norm["id"]:
            live_ph.append(td.get("Amount"))
            dc = dc or bool(td.get("Attack_DidCrit"))
            db = db or bool(td.get("Attack_DidBlock"))
            de = de or bool(td.get("Attack_DidEvade"))
    if not live_ph:
        pytest.skip("aucun degat live attribue")
    if dc or db or de:
        pytest.skip(f"coup non propre (crit={dc} block={db} evade={de})")
    if hp_before is not None and sum(live_ph) >= hp_before:
        pytest.skip("coup letal : le dernier coup est ecrete aux PV restants, non discriminant")

    r_floor, r_round = _models(dv, ob, snap, rng0, board, att, tid)
    cells_f = (r_floor.get("clean_min"), r_floor.get("clean_max"))
    cells_r = (r_round.get("clean_min"), r_round.get("clean_max"))
    print(f"\n[#131] {ATTACKER}->{TARGET} base={r_round.get('base')} pierce={r_round.get('pierce')} "
          f"armure={r_round.get('armor')} hits={r_round.get('hits')}")
    print(f"[#131] cellules TRONQUEES={cells_f}  ARRONDIES={cells_r}")
    print(f"[#131] live={live_ph} floor={r_floor.get('per_hit')} round={r_round.get('per_hit')}")

    assert r_round.get("armor") and r_round.get("armor") > 0, (
        f"cible non armuree (armor={r_round.get('armor')}) : sans armure la branche percage "
        "ne mord pas -> bornes NON reduites -> test non discriminant")
    # (1) le regime DOIT etre discriminant, sinon la garde ne prouve rien.
    assert cells_f != cells_r, (
        f"regime NON discriminant (cellules identiques {cells_f}) : les deux materialisations "
        "coincident ici -- choisir un couple (base, PiercingRatio) dont la reduction tombe sur "
        "une fraction >= 0.5 (cf. probe_131_normal_attack_bounds.py --phase scan)")
    # (2) le natif ARRONDIT (Fix64$$Round AwayFromZero) : bit-exact PER-COUP.
    assert r_round.get("per_hit") == live_ph, (
        f"bornes ARRONDIES != live : off={r_round.get('per_hit')} live={live_ph} "
        f"(cellules={cells_r} pierce={r_round.get('pierce')} armure={r_round.get('armor')}) -- "
        "la materialisation des cellules de PredictAttackRaw a-t-elle change ?")
    # (3) DISCRIMINATION : la troncature (le port d'avant #131) doit ECHOUER ici.
    assert r_floor.get("per_hit") != live_ph, (
        f"la TRONCATURE reproduit aussi le live ({r_floor.get('per_hit')}) : la garde est AVEUGLE, "
        "le montage n'exerce plus l'etage de materialisation")
