"""GATE `ActiveAbilityUsed` de l'OVERWATCH (case-127) confronte au LIVE, DANS LES DEUX SENS.

`IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal` (DECOMPILE)
enregistre TROIS `Triggered()` qui pilotent l'etat `EffectComponent.IsActive @+0x5c` de l'effet
`Overwatch_AutoAttack` (1009) -- etat RELU par
`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` avant d'evaluer le
trigger de TIR (`RangedAutoAttackEffect$$CreateTargetTrigger`). Le 1er, celui qui (RE)ACTIVE :

    On(TurnStart_EffectActivation = 0x12)
      & NOT IsTurnOf(owner@0x148)                                            # df@0xa0
      & ( HasEffect(owner, IgnoreUsedAbilityInOverwatch = 0x516)
          | DoesNotHaveFlag(owner, UnitFlag.ActiveAbilityUsed = 2) )         # IdunBattleLogic.Entities.DSLTriggers$$DoesNotHaveFlag
      & AdditionalActivateTrigger()                                          # NOT HasEffect(owner, Pinned)
    -> ActivateEffect(effect@0x150)

`DoesNotHaveFlag` -> `IdunBattle.Entities.Conditions.HasFlagAbilityTrigger$$ShouldTrigger` =
`UnitFlagsComponent.Has(flag)` XOR 1 (le ctor recoit `expected = false`) : c'est bien une NEGATION.
Le flag 2 est pose par `IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution`
et purge par le `RemoveTurnFlags` de `IdunBattle.Operations.StartTurnOperation$$Execute`.

CE QUE CE FICHIER PROUVE
------------------------
(1) ORACLE LIVE, avec CONTROLE INTERNE dans la MEME bataille et le MEME tour -- deux overwatchers
    MIENS (trait `Overwatch` -> effet 1009) castent chacun une ability sur la meme cible :
      * `eldarRanger` / FireAndReposition (1063) : `SetsActiveAbilityUsedFlag` par DEFAUT -> flag POSE ;
      * `admecDestroyer` / SentinelDirectives (1139) : la classe OVERRIDE ce virtual (fold-winner
        `IdunBattleLogic.Entities.Abilities.Active.ArcScourgeAbility$$SetsActiveAbilityUsedFlag`,
        table `NO_ABILITY_USED_FLAG_ABILITY_TYPES`) -> flag NON pose. i2 le dit mot pour mot :
        « Using Sentinel Directives does not end Sy-Gex's turn and he can still enter Overwatch this
        turn, unless he performs a normal attack ».
    Apres `endturn` (le StartTurn adverse ouvre la fenetre `On(0x12)`), le canal
    `decisionView.units[].effects` -- qui DROPPE les effets `IsActive == 0` (case-160) -- montre
    1009 ABSENT sur le premier et PRESENT sur le second. Le seul discriminant est le FLAG.
    La branche « n'a pas caste » est le 1er tour du meme test (aucun cast -> 1009 sur les DEUX).
(2) PORT : sur un etat live ou 1009 est ACTIF, `OverwatchAutoAttack.matches` doit rendre le MEME
    verdict dans les deux hypotheses de flag -- tir bit-exact sans le flag (== live), NO-OP avec.
    C'est ce couple qui couvre le regime ou la divergence mord : un rollout OFFLINE multi-tours,
    ou le porteur caste offline (flag pose par `add_flags_after_ability_execution`) alors que
    l'entree d'effet 1009, seedee une fois, n'est jamais desactivee cote port.

POURQUOI (2) NE PEUT PAS ETRE UN REPLAY-DIFF PUR : l'etat « 1009 actif ET flag pose » n'existe PAS
live (l'effet est desactive pendant le tour de son porteur par le 2e `Triggered()`, et la
re-activation est justement ce que le flag bloque). L'oracle live prouve la REGLE ; le double
verdict offline prouve le PORT de la regle.

Drive les positions des DEUX camps (`applyAction` ne verifie pas la propriete). State-file UNIQUE en
chemin ABSOLU, runner dispose au teardown. ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import MoveUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import (HealthComponent, StatsComponent, UnitFlagsComponent)

PYDIR = Path(__file__).resolve().parents[3]
ROOT = PYDIR.parents[1]

OW_FLAG = "eldarRanger"        # trait Overwatch ; FireAndReposition (1063) POSE ActiveAbilityUsed
OW_NOFLAG = "admecDestroyer"   # trait Overwatch ; SentinelDirectives (1139) NE le pose PAS
MOVER = "necroOverlord"        # cible tanky vanille (survit aux tirs)
AB_FLAG = 1063
AB_NOFLAG = 1139
OVERWATCH = 1009               # EffectType.Overwatch_AutoAttack


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


def _build(rpc, p_units: str, tag: str, seed: str = "777", board: str = "MC1_67"):
    sf = ROOT / "logs" / "runners" / f"ow127-{tag}-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed, "--state-file", str(sf),
         "--board", board, "--roster", "1", "--p-units", p_units, "--a-units", MOVER,
         "--hp-target", "400000", "--hp-player", "400000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, None, (proc.stderr or proc.stdout or "")[-300:]
    return int(json.loads(sf.read_text())["runnerId"]), sf, None


def _find(dv, vis):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vis and u.get("alive")),
                None)


def _cr(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _effs(u):
    return sorted({e.get("effectType") for e in ((u or {}).get("effects") or [])})


def _mv(rpc, rid, uid, c):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 60)


def _endturn(rpc, rid):
    return rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)


def _dv(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)


def _goto_my_turn(rpc, rid, my):
    for _ in range(8):
        dv = _dv(rpc, rid)
        if dv.get("currentPlayer") == my:
            return dv
        _endturn(rpc, rid)
    return None


def _from_here(rpc, rid, cid, ab):
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ab}, 90)
    us = (at.get("units") or [{}])[0]
    a = next((x for x in (us.get("abilities") or []) if x.get("abilityId") == ab), {})
    return {x.get("targetId") for x in (a.get("fromHere") or [])}


def _place_mover(rpc, rid, board, dv, mover_id, anchors, lo=2, hi=3):
    """Place le mover sur une tuile libre a distance [lo,hi] de CHAQUE ancre (positions des
    overwatchers). Renvoie la coord posee, ou None."""
    occ = {_cr(u) for u in (dv.get("units") or []) if u.get("alive") and u.get("id") != mover_id}
    cands = [board.coord(t) for t in sorted(board.by_id)
             if board.walkable(t) and board.coord(t) not in occ
             and all(lo <= hexgeo.distance(board.coord(t), a) <= hi for a in anchors)]
    for c in cands[:10]:
        _mv(rpc, rid, mover_id, c)
        if _cr(_find(_dv(rpc, rid), MOVER)) == c:
            return c
    return None


# --------------------------------------------------------------------------- (1) ORACLE LIVE

def test_overwatch_reactivation_gated_by_active_ability_used_flag(live_session, rpc):
    """Les DEUX branches du gate, dans la meme bataille :
      * tour 1 sans aucun cast   -> 1009 ACTIF sur les deux overwatchers apres `endturn` ;
      * tour 2 avec un cast chacun -> 1009 ABSENT sur celui dont l'ability pose `ActiveAbilityUsed`,
        PRESENT sur celui dont la classe override `SetsActiveAbilityUsedFlag` (controle interne)."""
    rid, sf, err = _build(rpc, f"{OW_FLAG},{OW_NOFLAG}", "oracle")
    if rid is None:
        pytest.skip(f"build runner KO: {err}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="evenq")
        dv = _dv(rpc, rid)
        a, b, m = _find(dv, OW_FLAG), _find(dv, OW_NOFLAG), _find(dv, MOVER)
        if a is None or b is None or m is None:
            pytest.skip(f"unites absentes (a={bool(a)} b={bool(b)} m={bool(m)})")
        my = a["owner"]
        dv = _goto_my_turn(rpc, rid, my)
        if dv is None:
            pytest.skip("mon tour inatteignable")
        a, b, m = _find(dv, OW_FLAG), _find(dv, OW_NOFLAG), _find(dv, MOVER)
        spot = _place_mover(rpc, rid, board, dv, m["id"], (_cr(a), _cr(b)))
        if spot is None:
            pytest.skip("placement du mover infaisable (aucune tuile a portee des DEUX)")

        # --- branche A : AUCUN cast -> les deux doivent (re)activer leur overwatch --------------
        _endturn(rpc, rid)                                   # StartTurn adverse = fenetre On(0x12)
        dv_a = _dv(rpc, rid)
        ea0, eb0 = _effs(_find(dv_a, OW_FLAG)), _effs(_find(dv_a, OW_NOFLAG))
        print(f"\n[OW127-A no-cast] {OW_FLAG}={ea0} {OW_NOFLAG}={eb0}")
        assert OVERWATCH in ea0 and OVERWATCH in eb0, (
            f"branche 'n'a pas caste' : overwatch attendu ACTIF sur les deux "
            f"({OW_FLAG}={ea0}, {OW_NOFLAG}={eb0}) -- la fixture ne teste rien si 1009 n'est "
            f"jamais actif")

        # --- branche B : chacun caste -> seul le flag doit bloquer la re-activation -------------
        _endturn(rpc, rid)                                   # retour a MON tour (RemoveTurnFlags)
        dv_b = _goto_my_turn(rpc, rid, my)
        if dv_b is None:
            pytest.skip("retour a mon tour impossible")
        a, b, m = _find(dv_b, OW_FLAG), _find(dv_b, OW_NOFLAG), _find(dv_b, MOVER)
        if a is None or b is None or m is None:
            pytest.skip("unite morte pendant l'approche")
        cast_ok = {}
        for u, ab, nm in ((a, AB_FLAG, OW_FLAG), (b, AB_NOFLAG, OW_NOFLAG)):
            if m["id"] not in _from_here(rpc, rid, u["id"], ab):
                pytest.skip(f"cast {nm}/{ab} illegal depuis la position courante")
            r = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": u["id"], "targetId": m["id"],
                "abilityType": ab}}, 120)
            cast_ok[nm] = _ok(r)
        if not all(cast_ok.values()):
            pytest.skip(f"cast refuse par le moteur: {cast_ok}")
        _endturn(rpc, rid)                                   # fenetre On(0x12) suivante
        dv_c = _dv(rpc, rid)
        ea1, eb1 = _effs(_find(dv_c, OW_FLAG)), _effs(_find(dv_c, OW_NOFLAG))
        print(f"[OW127-B cast] {OW_FLAG}(flag pose)={ea1} {OW_NOFLAG}(pas de flag)={eb1}")
        assert OVERWATCH not in ea1, (
            f"{OW_FLAG} a caste {AB_FLAG} (SetsActiveAbilityUsedFlag par defaut = flag 2 pose) : "
            f"le natif ne doit PAS re-activer l'overwatch -- effets={ea1}")
        assert OVERWATCH in eb1, (
            f"{OW_NOFLAG} a caste {AB_NOFLAG}, dont la classe OVERRIDE SetsActiveAbilityUsedFlag "
            f"(pas de flag 2) : le natif DOIT re-activer l'overwatch -- effets={eb1}. Sans ce "
            f"controle, l'assertion precedente serait satisfaite par n'importe quel 'caster = "
            f"plus d'overwatch', et ne prouverait pas que le discriminant est LE FLAG")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        sf.unlink(missing_ok=True)


# --------------------------------------------------------------------------- (2) PORT, 2 HYPOTHESES

def _replay_move(dv, ob, snap, board, s0, mover_id, to, ow_id, ability_used: bool):
    """Rejoue le move offline depuis l'etat live capture, avec/sans `UnitFlag.ActiveAbilityUsed`
    sur l'overwatcher. Renvoie (pv du mover apres, resultats after-move)."""
    st = load_state(dv, ob, snap, board=board)
    if ability_used:
        e = st.get_entity(ow_id)
        fl = e.get_component(UnitFlagsComponent) or e.add_component(UnitFlagsComponent())
        fl.add(UnitFlagsComponent.ACTIVE_ABILITY_USED)   # AddFlagsAfterAbilityExecution
    st.rng = _seed_rng(s0)
    runner = Runner(st).install_default_handlers(20)
    runner.apply(MoveUnitMessage(mover_id, to))
    hp = st.get_entity(mover_id).get_component(HealthComponent).hp
    fired = [x for x in (runner.movement_handler.after_move or [])
             if x.get("effect") == "Overwatch_AutoAttack"]
    return hp, fired


@pytest.mark.parametrize("seed,board", [("777", "MC1_67"), ("31337", "C2_02")])
def test_overwatch_offline_gate_both_hypotheses(live_session, rpc, seed, board):
    """Sur un etat LIVE ou 1009 est ACTIF : sans le flag, le port tire et reproduit les PV live
    BIT-EXACT ; avec le flag, il ne tire pas (et l'etat live, lui, TIRE -> les deux hypotheses sont
    bien discriminantes). Rejoue sur DEUX couples (board, seed) : le tir depend de la portee et donc
    de la geometrie, meme si le gate lui-meme est un booleen."""
    rid, sf, err = _build(rpc, OW_FLAG, "port", seed=seed, board=board)
    if rid is None:
        pytest.skip(f"build runner KO: {err}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="evenq")
        dv = _dv(rpc, rid)
        ow, m = _find(dv, OW_FLAG), _find(dv, MOVER)
        if ow is None or m is None:
            pytest.skip("unites absentes")
        my = ow["owner"]
        dv = _goto_my_turn(rpc, rid, my)
        if dv is None:
            pytest.skip("mon tour inatteignable")
        ow, m = _find(dv, OW_FLAG), _find(dv, MOVER)
        spot = _place_mover(rpc, rid, board, dv, m["id"], (_cr(ow),))
        if spot is None:
            pytest.skip("placement du mover infaisable")
        _endturn(rpc, rid)                                   # tour adverse : 1009 (re)active
        dv = _dv(rpc, rid)
        ow, m = _find(dv, OW_FLAG), _find(dv, MOVER)
        if OVERWATCH not in _effs(ow):
            pytest.skip(f"overwatch inactif sur l'overwatcher (effets={_effs(ow)})")

        # une tuile voisine, toujours a portee -> le move DOIT declencher un tir
        occ = {_cr(u) for u in (dv.get("units") or []) if u.get("alive") and u["id"] != m["id"]}
        to = next((board.coord(t) for t in board.neighbours(board.id_at(*_cr(m)))
                   if board.walkable(t) and board.coord(t) not in occ
                   and 1 <= hexgeo.distance(board.coord(t), _cr(ow)) <= 3), None)
        if to is None:
            pytest.skip("aucune tuile voisine a portee")

        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if snap is None or not _ok(s0):
            pytest.skip("combatSnapshot/dumpRng indispo")
        hp_before = next((u.get("hp") for u in (ob.get("units") or [])
                          if u.get("squadId") == m["id"]), None)
        st_probe = load_state(dv, ob, snap, board=board)
        if st_probe.get_entity(ow["id"]).get_component(StatsComponent) is None:
            pytest.skip("overwatcher sans StatsComponent offline")

        _mv(rpc, rid, m["id"], to)                           # move LIVE
        ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
        hp_live = next((u.get("hp") for u in (ob2.get("units") or [])
                        if u.get("squadId") == m["id"]), None)
        if hp_before is None or hp_live is None:
            pytest.skip("PV du mover illisibles")
        if hp_live >= hp_before:
            pytest.skip(f"aucun overwatch live sur ce move (hp {hp_before} -> {hp_live})")

        hp_no, fired_no = _replay_move(dv, ob, snap, board, s0, m["id"], to, ow["id"], False)
        hp_yes, fired_yes = _replay_move(dv, ob, snap, board, s0, m["id"], to, ow["id"], True)
        print(f"\n[OW127-PORT] live {hp_before} -> {hp_live} | offline sans flag={hp_no} "
              f"(tirs={len(fired_no)}) | offline avec flag={hp_yes} (tirs={len(fired_yes)})")
        assert fired_no and hp_no == hp_live, (
            f"hypothese VRAIE (pas de flag, comme le live) : offline {hp_no} != live {hp_live} "
            f"(tirs offline={len(fired_no)})")
        assert not fired_yes and hp_yes == hp_before, (
            f"hypothese 'a caste' : le gate DoesNotHaveFlag(owner, ActiveAbilityUsed) doit annuler "
            f"le tir (tirs={len(fired_yes)}, hp={hp_yes} au lieu de {hp_before})")
        assert hp_yes != hp_no, (
            "les deux hypotheses de flag donnent le meme PV : le scenario n'est PAS discriminant")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        sf.unlink(missing_ok=True)
