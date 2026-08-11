"""Le SOCLE COMMUN des ripostes portees par un EFFET -- pendant RUNNER du foyer
`engine/entities/effects/loki/counter_attack.py` (la famille
`IdunBattle.Entities.Effects.CounterAttackEffect`).

Ce module ne porte AUCUN comportement propre : il tient les quatre lectures/ecritures que les TROIS
membres portes de la famille (`WireweaveNet` 1111, `GrimRetribution` 1213, `UnwaveringSentinel` 1439)
font a l'IDENTIQUE, parce que ce sont celles de leur BASE `PlayerTurnEffect` -- pas celles d'un
membre. Elles sont donc parametrees par `effect_type` et par rien d'autre.

Cree au TROISIEME site (#946) : les quatre fonctions vivaient en dur dans `wireweave_net.py`, cle sur
son seul `EffectType`. Les recopier deux fois de plus aurait fabrique trois definitions de
<< l'instance est-elle armee ? >>, exactement le fork que la doctrine interdit au 2e site.

Correspondance native, pour chacune :

  * `instances(state, owner, effect_type)` -- les entites-EFFET de ce type portees par `owner` et non
    consommees. Le natif raisonne PAR ENTITE-EFFET ; en pratique `AddEffectOperation` no-ope sur un
    meme-type deja present, donc il y en a 0 ou 1.
  * `flag_is_set(...)`  -- `EffectComponent.IsActive @+0x5c`, le PREMIER test
    d'`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets`, applique AVANT
    toute evaluation du trigger de cible. Aucune instance -> `True` (degradation PERMISSIVE : on ne
    fabrique pas un refus ; si l'effet est reellement absent, `collect_effect_triggers` n'aura
    instancie aucun trigger).
  * `set_active(...)` -- `IdunBattle.Operations.RefreshEffectsOperation$$ActivateEffect` (`+0x5c = 1`)
    / `$$DeactivateEffect` (`+0x5c = 0`, precede du gate << deja inactif -> no-op >>). Rend `True`
    si un flag a CHANGE, ce qui permet de n'emettre aucun evenement quand l'ecriture est un no-op,
    comme le natif.
  * `is_turn_of_owner(...)` -- `<DSLTriggers+0x28>` = `IsTurnOf(Owner@<DSLSelectors+0x30>)`. Le joueur
    courant est `state.current_player_id` ; sur les vecteurs de tour (`On(0x12)` / `On(0x17)`) le port
    threade en plus `ev.player_id` -- on le prefere quand il est renseigne, c'est le joueur que le
    natif a dans `MatchState` a l'instant de l'evenement. `None` = indeterminable (aucun tour
    courant), et les appelants comparent donc a `is True` / `is not False`, jamais par truthiness.
"""
from __future__ import annotations

from typing import Optional

from ....components import OwnerComponent
from ....state import State
from ..base import TriggerEvent


def instances(state: State, owner_id: int, effect_type: int) -> list:
    """Les instances `effect_type` NON consommees portees par `owner_id` (cf. l'en-tete)."""
    if state.effects is None:
        return []
    return [e for e in state.effects.by_unit.get(int(owner_id), [])
            if not e.consumed and e.effect_type == int(effect_type)]


def flag_is_set(state: State, owner_id: int, effect_type: int) -> bool:
    """`EffectComponent.IsActive @+0x5c` de l'instance (cf. l'en-tete : aucune instance -> True)."""
    insts = instances(state, owner_id, effect_type)
    return (not insts) or any(e.active for e in insts)


def set_active(state: State, owner_id: int, effect_type: int, value: bool) -> bool:
    """Ecrit `EffectComponent.IsActive @+0x5c` ; rend True si un flag a CHANGE (cf. l'en-tete)."""
    changed = False
    for e in instances(state, owner_id, effect_type):
        if bool(e.active) != bool(value):
            e.active = bool(value)
            changed = True
    return changed


def is_turn_of_owner(state: State, owner_id: int,
                     ev: Optional[TriggerEvent] = None) -> Optional[bool]:
    """`<DSLTriggers+0x28>` = `IsTurnOf(Owner@<DSLSelectors+0x30>)` (cf. l'en-tete)."""
    pid = None
    if ev is not None and getattr(ev, "player_id", None) is not None:
        pid = int(ev.player_id)
    elif state.current_player_id is not None:
        pid = int(state.current_player_id)
    if pid is None:
        return None
    ow = state.get_entity(owner_id)
    oc = ow.get_component(OwnerComponent) if ow is not None else None
    if oc is None or oc.player is None:
        return None
    return int(oc.player) == pid
