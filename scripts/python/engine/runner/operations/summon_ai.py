"""Passe AI-control du turn-start — joue les unites `ai_controlled` (summons) via le PLAYBOOK COMPLET. #65.

Mirror de `IdunBattle.View.Game.IdunGameViews.QueueComputerActions @1804d90d0` (+ `IsPlayerAiControlled`
@1804d7b10) : au DEBUT du tour d'une team, les unites AI-controlees (summons — meme sur une team joueur)
sont jouees par l'IA AVANT que le controleur agisse (verite-terrain live : les Cadiens de Yarrick bougent
seuls au turn-start de leur team). Ce N'EST PAS un triggered ability (le trigger-trace ne capte aucun
trigger turn-start summon) : c'est une passe AI-control du runner.

DECISION = le playbook complet porte (`DefaultAiUnitTactic.calculate_next_action` via le bridge offline
`engine.ai.state_bridge.build_from_state`) — la routine de candidats native = `PerformAIAbilityUnitBehaviour
.Execute @180fcb070` (enumere cibles -> per-cible move+attaque -> utility-argmax). APPLY = les Operations
runner (move + attaque normale/ability), au niveau `state` (comme `_betrayer_take_turn` du vecteur turn-start).

Ordre intra-team = `PickNextUnit` (utility) cote natif ; ici ordre d'id (1re approx documentee ; raffinement).
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import UnitComponent, OwnerComponent, PositionComponent

NORMAL_ATTACK_ID = 17    # ActiveAbilityType.NormalAttack — id synthetique du bridge (cf. state_bridge)


def collect_ai_controlled(state: State, player: int) -> list:
    """Ids des unites `ai_controlled` VIVANTES du `player` courant (= les summons de sa team). Triees par id
    (ordre `PickNextUnit` = raffinement). `player` = OwnerComponent.player (3/4), pas la team."""
    out: list = []
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        if uc is None or oc is None:
            continue
        if not uc.alive or not getattr(uc, "ai_controlled", False):
            continue
        if oc.player != player:
            continue
        out.append(eid)
    return sorted(out)


def run_ai_control_pass(state: State, player: int) -> list:
    """Joue chaque summon `ai_controlled` du `player` (decision playbook -> apply). Renvoie la liste des
    resultats (diagnostic). No-op (liste vide) si la team n'a aucun summon (cas normal des batailles sans
    invocation) -> aucune regression sur le turn-flow existant."""
    results: list = []
    for uid in collect_ai_controlled(state, player):
        e = state.get_entity(uid)                      # re-check : une action precedente (overwatch) a pu tuer
        uc = e.get_component(UnitComponent) if e is not None else None
        if uc is None or not uc.alive:
            continue
        results.append(decide_and_apply(state, uid))
    return results


def decide_and_apply(state: State, uid: int) -> dict:
    """Bridge `State -> AiDecisionContext` (offline) -> decision playbook -> apply. Capture les exceptions du
    bridge/spine en un resultat diagnostic (ne casse pas le turn-flow)."""
    from engine.ai.state_bridge import build_from_state
    from engine.ai.tactic import DefaultAiUnitTactic
    try:
        ctx = build_from_state(state, uid)
        action = DefaultAiUnitTactic().calculate_next_action(ctx)
    except Exception as ex:                             # pragma: no cover (diagnostic)
        return {"uid": uid, "error": repr(ex)}
    return apply_action(state, uid, action)


def apply_action(state: State, uid: int, action: dict) -> dict:
    """Applique l'action decidee (`{kind, to, target, ability}`) via les Operations runner, au niveau `state` :
      1. si `to` != origine -> `MoveUnitOperation` + vecteur after-move (overwatch sur le move du summon) ;
      2. attaque normale (ability == 17) -> `AttackDamageOperation.execute` + vecteur after-hit (mirror
         exact du handler `visit_AttackUnitMessage`) ; ability ACTIVE -> handler (SLICE 2 ; 4 abilities portees).
    Re-check `alive` apres le move (l'overwatch peut tuer le summon avant qu'il n'attaque)."""
    from ..events import EventBus
    from .movement import MoveUnitOperation
    from .damage import AttackDamageOperation
    from .triggers import after_move_triggers, after_hit_normal_attack

    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    origin = (pc.col, pc.row) if pc is not None else None
    to = action.get("to")
    res: dict = {"uid": uid, "kind": action.get("kind"), "to": to,
                 "target": action.get("target"), "ability": action.get("ability"),
                 "moved": None, "attack": None}
    # 1. composante MOVE
    if to is not None and tuple(to) != origin:
        MoveUnitOperation(uid, tuple(to)).execute(state, EventBus())
        res["moved"] = tuple(to)
        res["after_move"] = after_move_triggers(state, uid)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None or not uc.alive:                     # tue par l'overwatch pendant le move
        return res
    # 2. composante ATTAQUE / ABILITY
    if action.get("kind") == "ability":
        ability = action.get("ability")
        target = action.get("target")
        if ability == NORMAL_ATTACK_ID and target is not None:
            r = AttackDamageOperation.execute(state, uid, target)
            res["attack"] = r
            if r is not None:                          # vecteur after-hit (mirror visit_AttackUnitMessage)
                res["after_hit"] = after_hit_normal_attack(
                    state, uid, target, bool(r.get("ranged")), r.get("profile"),
                    is_crit=bool(r.get("did_crit")))
        elif target is not None or ability is not None:
            from ..abilities.handler import AbilityHandler
            from ..messages import ActiveAbilityMessage
            AbilityHandler(state).visit_ActiveAbilityMessage(
                ActiveAbilityMessage(uid, target, ability))
            res["attack"] = {"ability": ability, "target": target, "routed": "handler"}
    return res
