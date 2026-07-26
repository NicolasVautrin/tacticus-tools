"""UN SEUL TIR PAR ACTIVATION (overwatch) — confronte au LIVE, avec le CONTROLE de re-activation.

3e `Triggered()` de `IdunBattle.Entities.Effects.RangedAutoAttackEffect$$
CreateHandleTriggerAbilitiesInternal` (DECOMPILE) :

    On(AttackDamageAttack = 10, 1) & OwnerIsActor -> DeactivateEffect(effect@0x150)

`DeactivateEffect` = `IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` (`EffectComponent
.IsActive @+0x5c = 0`), et ce flag est le gate que
`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` applique AVANT le trigger
de TIR. Donc : le tir de l'overwatcher (une attaque NORMALE, `AttackDamageOperation`) CONSOMME son
propre overwatch. L'event 10 est emis par `IdunBattle.Operations.FinishAttackOperation$$Execute`, juste
apres `On(9)` et sous le gate `currentAttack@+0x2c` (pose par `AttackDamageOperation$$Execute`).

CE QUE CE FICHIER PROUVE, dans UNE bataille :
  (A) LIVE  : deux overwatchers armes ; un 1er mouvement ennemi dans la portee declenche la volee et
              fait DISPARAITRE 1009 des DEUX (le canal `decisionView.effects` droppe les `IsActive==0`) ;
              un SECOND mouvement ennemi, toujours dans la portee, ne fait RIEN (delta PV = 0).
  (B) PORT  : rejoue BIT-EXACT depuis l'etat live capte AVANT le 1er mouvement (RNG cale par `dumpRng`) —
              le 1er move tire et reproduit les PV live, le 2e ne tire PAS. AVANT ce port, l'offline
              re-tirait une volee complete a CHAQUE deplacement ennemi de la portee.
  (C) CONTROLE SYMETRIQUE : apres un aller-retour de tours, l'overwatch DOIT redevenir capable de tirer
              — live (1009 de retour sur les deux) ET offline (le meme etat, avance de deux
              `EndTurnOperation`, retrouve son flag `IsActive`). Un fix qui eteindrait l'overwatch
              DEFINITIVEMENT passerait (A)+(B) et echouerait ici.

Deux MOVERS distincts (plutot qu'un meme mover deplace deux fois) : le critere « une seule volee par
activation » ne doit rien devoir a une eventuelle limite de deplacement par activation.

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
from engine.runner.components import HealthComponent
from engine.runner.operations.turnflow import EndTurnOperation
from engine.runner.operations.triggers.effect_triggers import (
    _ranged_auto_attack_flag_is_set, _ranged_auto_attack_instances)

PYDIR = Path(__file__).resolve().parents[3]
ROOT = PYDIR.parents[1]

OW_A = "eldarRanger"        # trait Overwatch, arme portee 3
OW_B = "admecDestroyer"     # trait Overwatch, arme portee 3
MOVER_A = "necroOverlord"   # movers vanille (Hero/LivingMetal/Mechanical), tankys via --hp-target
MOVER_B = "necroWarden"
OVERWATCH = 1009            # EffectType.Overwatch_AutoAttack


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


def _build(rpc, tag: str, seed: str = "777", board: str = "MC1_67"):
    sf = ROOT / "logs" / "runners" / f"ow1shot-{tag}-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed, "--state-file", str(sf),
         "--board", board, "--roster", "1",
         "--p-units", f"{OW_A},{OW_B}", "--a-units", f"{MOVER_A},{MOVER_B}",
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


def _hp(ob, uid):
    return next((u.get("hp") for u in (ob.get("units") or []) if u.get("squadId") == uid), None)


def _goto_my_turn(rpc, rid, my):
    for _ in range(8):
        dv = _dv(rpc, rid)
        if dv.get("currentPlayer") == my:
            return dv
        _endturn(rpc, rid)
    return None


def _place(rpc, rid, board, unit_id, vis, anchors, occupied, lo=2, hi=3):
    """Pose `unit_id` sur une tuile libre a distance [lo,hi] de CHAQUE ancre (les overwatchers).
    Renvoie la coord posee, ou None."""
    for t in sorted(board.by_id):
        c = board.coord(t)
        if not board.walkable(t) or c in occupied:
            continue
        if not all(lo <= hexgeo.distance(c, a) <= hi for a in anchors):
            continue
        _mv(rpc, rid, unit_id, c)
        if _cr(_find(_dv(rpc, rid), vis)) == c:
            return c
    return None


def _step_in_range(board, frm, anchors, occupied, lo=1, hi=3):
    """Une tuile VOISINE de `frm`, libre, encore a portee [lo,hi] de CHAQUE ancre."""
    src = board.id_at(*frm)
    for t in board.neighbours(src):
        c = board.coord(t)
        if board.walkable(t) and c not in occupied \
                and all(lo <= hexgeo.distance(c, a) <= hi for a in anchors):
            return c
    return None


def _replay(dv, ob, snap, board, rng_state, moves):
    """Rejoue N moves offline depuis l'etat live capture. Renvoie (state, [tirs par move])."""
    st = load_state(dv, ob, snap, board=board)
    st.rng = _seed_rng(rng_state)
    runner = Runner(st).install_default_handlers(20)
    fired: list = []
    for uid, to in moves:
        runner.apply(MoveUnitMessage(uid, to))
        fired.append([x for x in (runner.movement_handler.after_move or [])
                      if x.get("effect") == "Overwatch_AutoAttack"])
    return st, fired


def test_overwatch_single_shot_per_activation_live(live_session, rpc):
    rid, sf, err = _build(rpc, "main")
    if rid is None:
        pytest.skip(f"build runner KO: {err}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="evenq")
        dv = _dv(rpc, rid)
        a, b = _find(dv, OW_A), _find(dv, OW_B)
        ma, mb = _find(dv, MOVER_A), _find(dv, MOVER_B)
        if not all((a, b, ma, mb)):
            pytest.skip(f"unites absentes (a={bool(a)} b={bool(b)} ma={bool(ma)} mb={bool(mb)})")
        my = a["owner"]
        dv = _goto_my_turn(rpc, rid, my)
        if dv is None:
            pytest.skip("mon tour inatteignable")
        a, b = _find(dv, OW_A), _find(dv, OW_B)
        anchors = (_cr(a), _cr(b))
        occ = {_cr(u) for u in (dv.get("units") or []) if u.get("alive")}
        pa = _place(rpc, rid, board, ma["id"], MOVER_A, anchors, occ - {_cr(ma)})
        if pa is None:
            pytest.skip("placement mover A infaisable")
        dv = _dv(rpc, rid)
        occ = {_cr(u) for u in (dv.get("units") or []) if u.get("alive")}
        pb = _place(rpc, rid, board, mb["id"], MOVER_B, anchors, occ - {_cr(mb)})
        if pb is None:
            pytest.skip("placement mover B infaisable")

        _endturn(rpc, rid)                       # tour ADVERSE : On(0x12) (re)active les deux overwatch
        dv = _dv(rpc, rid)
        a, b = _find(dv, OW_A), _find(dv, OW_B)
        ea0, eb0 = _effs(a), _effs(b)
        if OVERWATCH not in ea0 or OVERWATCH not in eb0:
            pytest.skip(f"overwatch inactif au depart ({OW_A}={ea0}, {OW_B}={eb0})")
        ma, mb = _find(dv, MOVER_A), _find(dv, MOVER_B)
        occ = {_cr(u) for u in (dv.get("units") or []) if u.get("alive")}
        to_a = _step_in_range(board, _cr(ma), anchors, occ - {_cr(ma)})
        to_b = _step_in_range(board, _cr(mb), anchors, occ - {_cr(mb)} | {to_a})
        if to_a is None or to_b is None:
            pytest.skip(f"pas de pas a portee (to_a={to_a}, to_b={to_b})")

        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if snap is None or not _ok(s0):
            pytest.skip("combatSnapshot/dumpRng indispo")
        hp_a0, hp_b0 = _hp(ob, ma["id"]), _hp(ob, mb["id"])
        if hp_a0 is None or hp_b0 is None:
            pytest.skip("PV des movers illisibles")

        # --- (A) LIVE : 1er move = volee ; 2e move = RIEN --------------------------------------
        _mv(rpc, rid, ma["id"], to_a)
        ob1 = rpc("observeBattle", {"runnerId": rid}, 40)
        dv1 = _dv(rpc, rid)
        hp_a1 = _hp(ob1, ma["id"])
        ea1, eb1 = _effs(_find(dv1, OW_A)), _effs(_find(dv1, OW_B))
        _mv(rpc, rid, mb["id"], to_b)
        ob2 = rpc("observeBattle", {"runnerId": rid}, 40)
        hp_b1 = _hp(ob2, mb["id"])
        print(f"\n[OW1SHOT-A live] moveA {hp_a0} -> {hp_a1} | effets apres: {OW_A}={ea1} {OW_B}={eb1}"
              f" | moveB {hp_b0} -> {hp_b1}")
        if hp_a1 is None or hp_b1 is None or hp_a1 >= hp_a0:
            pytest.skip(f"pas de volee live sur le 1er move (hp {hp_a0} -> {hp_a1})")
        assert OVERWATCH not in ea1 and OVERWATCH not in eb1, (
            f"apres leur tir, 1009 doit avoir disparu des DEUX overwatchers "
            f"({OW_A}={ea1}, {OW_B}={eb1}) -- c'est la lecture live du flag IsActive")
        assert hp_b1 == hp_b0, (
            f"le 2e mover a pris {hp_b0 - hp_b1} PV : le natif ne tire QU'UNE fois par activation "
            f"(3e Triggered() = On(10) & OwnerIsActor -> DeactivateEffect)")

        # --- (B) PORT : le meme enchainement, rejoue bit-exact -----------------------------------
        st, fired = _replay(dv, ob, snap, board, s0,
                            [(ma["id"], to_a), (mb["id"], to_b)])
        hp_a_off = st.get_entity(ma["id"]).get_component(HealthComponent).hp
        hp_b_off = st.get_entity(mb["id"]).get_component(HealthComponent).hp
        print(f"[OW1SHOT-B port] tirs move1={len(fired[0])} hp={hp_a_off} (live {hp_a1}) | "
              f"tirs move2={len(fired[1])} hp={hp_b_off} (live {hp_b1})")
        assert fired[0], "le port n'a tire AUCUN overwatch sur le 1er move (scenario non discriminant)"
        assert hp_a_off == hp_a1, (
            f"1er move : offline {hp_a_off} != live {hp_a1} (tirs={len(fired[0])})")
        assert not fired[1], (
            f"2e move : le port a re-tire {len(fired[1])} overwatch alors que les instances 1009 "
            f"ont ete desactivees par leur propre tir (3e Triggered())")
        assert hp_b_off == hp_b0, (
            f"2e move : PV du mover B {hp_b_off} au lieu de {hp_b0} (aucun tir attendu)")
        assert _ranged_auto_attack_flag_is_set(st, a["id"]) is False, (
            "le flag IsActive de l'overwatcher A doit etre tombe apres son tir")
        assert _ranged_auto_attack_flag_is_set(st, b["id"]) is False

        # --- (C) CONTROLE : re-activation, OFFLINE puis LIVE ------------------------------------
        # OFFLINE : deux tours passent (EndTurn -> ChangeTurn -> StartTurn -> On(0x12)) => (2) puis (1).
        rem = [e.remaining_turns for e in _ranged_auto_attack_instances(st, a["id"])]
        EndTurnOperation.execute(st, advance=True)          # -> tour des overwatchers
        EndTurnOperation.execute(st, advance=True)          # -> tour adverse : (1) re-active
        print(f"[OW1SHOT-C off] remaining(1009)={rem} flagA={_ranged_auto_attack_flag_is_set(st, a['id'])}"
              f" flagB={_ranged_auto_attack_flag_is_set(st, b['id'])}")
        assert _ranged_auto_attack_flag_is_set(st, a["id"]) is True, (
            "OFFLINE : apres un aller-retour de tours, l'overwatch de A n'est jamais revenu -- "
            "le port l'aurait eteint DEFINITIVEMENT")
        assert _ranged_auto_attack_flag_is_set(st, b["id"]) is True

        # LIVE : meme aller-retour, meme verdict attendu sur le canal `decisionView` -- qui DROPPE
        # les effets `IsActive == 0` (case-160), donc « 1009 present » == « IsActive pose » == l'etat
        # depuis lequel le natif tire.
        _endturn(rpc, rid)                                  # -> mon tour   ((2) desactive)
        _goto_my_turn(rpc, rid, my)
        _endturn(rpc, rid)                                  # -> tour adverse ((1) re-active)
        dv3 = _dv(rpc, rid)
        ea3, eb3 = _effs(_find(dv3, OW_A)), _effs(_find(dv3, OW_B))
        print(f"[OW1SHOT-C live] {OW_A}={ea3} {OW_B}={eb3}")
        assert OVERWATCH in ea3 and OVERWATCH in eb3, (
            f"LIVE : l'overwatch doit revenir au tour adverse suivant ({OW_A}={ea3}, {OW_B}={eb3}) "
            f"-- sans ce controle, 'plus jamais de tir' satisferait le critere principal")

        # ... et le PORT doit RE-tirer depuis cet etat live re-active. On le confronte OFFLINE
        # (capture fraiche) : les activations LIVE des movers sont deja consommees a ce stade (le
        # tour adverse a ete joue par l'IA native pendant l'aller-retour), donc un 3e move live
        # serait refuse -- et un move refuse ne prouverait rien du tout.
        ma3 = _find(dv3, MOVER_A)
        anchors3 = (_cr(_find(dv3, OW_A)), _cr(_find(dv3, OW_B)))
        occ3 = {_cr(u) for u in (dv3.get("units") or []) if u.get("alive")}
        to_a3 = _step_in_range(board, _cr(ma3), anchors3, occ3 - {_cr(ma3)})
        if to_a3 is None:
            pytest.skip("pas de 3e pas a portee (la re-activation live reste prouvee par 1009)")
        ob3 = rpc("observeBattle", {"runnerId": rid}, 40)
        snap3 = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s1 = rpc("dumpRng", {"runnerId": rid}, 30)
        if snap3 is None or not _ok(s1):
            pytest.skip("combatSnapshot/dumpRng indispo (phase C)")
        hp_a2 = _hp(ob3, ma3["id"])
        st3, fired3 = _replay(dv3, ob3, snap3, board, s1, [(ma3["id"], to_a3)])
        hp_a3 = st3.get_entity(ma3["id"]).get_component(HealthComponent).hp
        print(f"[OW1SHOT-C port] re-tir offline : tirs={len(fired3)}x{len(fired3[0])} "
              f"hp {hp_a2} -> {hp_a3}")
        assert fired3[0] and hp_a3 < hp_a2, (
            f"apres re-activation, le port doit RE-tirer (tirs={len(fired3[0])}, hp {hp_a2} -> "
            f"{hp_a3}) -- un fix qui eteindrait l'overwatch definitivement echoue ICI")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        sf.unlink(missing_ok=True)
