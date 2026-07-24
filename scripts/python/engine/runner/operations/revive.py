"""Revive-EN-PLACE d'unite -- `IdunBattle.Operations.ReviveUnitOperation.Execute @180e91bd0` (mutateur ECS
IMPERATIF). DISTINCT de `ResurrectUnitOperation` (ambush tile-choice, resurrect.py) : le REVIVE remet
l'unite VIVANTE a la MEME position (in-place) ; il n'y a PAS de tuile choisie ni de flag one-shot Ambush.

Frontiere DSL (#149) : la feuille DSL `Revive` (`DSLFactory.Revive @180dfa4f0` -> `ReviveBehaviour.Execute
@180fd1230`, structurelle, AU-DESSUS) APPELLE cette Operation (impurative, EN-DESSOUS). On NE fusionne PAS
le behaviour (Maybe/DeactivateEffect) et la mutation ECS (ici) : la feuille est dans les triggers, l'Operation
ici.

Chaine native (base `ReviveEffect`, partagee par Narthecium/TaintedNarthecium/ReanimationBeam/...) :
    ReviveEffect.CreateTargetTrigger        @180f46d80  OnPreDeath(target) & CanBeRevived(target) & filter
    ReviveEffect.CreateTargetTriggerBehaviour @180f46a70 Maybe(chance){ Revive(self, target,
                                                             Min(reviveHP, StatAmount(target,Health,max)),
                                                             tile, sourceId) ; DeactivateEffect }
    DSLFactory.Revive @180dfa4f0 -> ReviveBehaviour.Execute @180fd1230 -> ReviveUnitMessage
    -> OperationProcessor.ReviveUnit @180e0b510 -> ReviveUnitOperation.Execute @180e91bd0 (ICI) :
      * SetHealth @180e93450 : hp = Min(hp_arg, GetStat(unit, Health=5, MAX=3))     (re-clamp au maxHP)
      * flags @180e923b0 : Remove(0xf), Remove(8=overkill), Add(0x14)  -> l'unite redevient VIVANTE
        (retire les flags de mort/overkill ; PAS 0xe AmbushConsumed -- un revive-en-place N'EST PAS un
        ambush one-shot, il peut re-fire a un tour ulterieur)
      * SetRevivePosition @180e936e0 : repositionne sur la tuile de l'unite -> IN-PLACE (position inchangee
        pour un revive-sur-mort : l'unite est morte sur sa propre tuile, on l'y remet)
      * emet On(UnitRevived=46=0x2e) @FUN_180026490(0x4d,...) -> re-eval Swarm (bras `On(UnitRevived)` du
        `SwarmAbility.CreateTrigger @181225f50`, cf. resurrect.py) + downstream.

Ce port porte la MUTATION OBSERVABLE (le pipeline de file/stream = couche view non suivie) : alive=True,
hp = Min(hp_arg, hp_max), MEME position. Le HP_arg vient de la feuille (`Min(reviveHP, target.hp_max)`).
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import UnitComponent, HealthComponent


class ReviveUnitOperation:
    """Mirror `ReviveUnitOperation.Execute @180e91bd0` (mutateur ECS, revive-EN-PLACE). `unit_id` = l'unite
    a revive (param_2 natif = l'entite, PAS un param HP -- le HP est data-driven depuis le composant
    ReviveEffect) ; `hp` = PV a restaurer (deja `Min(reviveHP, maxHP)` calcule par la feuille). SetHealth
    re-clamp `Min(hp, hp_max)` (fidele @180e93450). Position INCHANGEE (in-place)."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, unit_id: int, hp) -> Optional[dict]:
        e = state.get_entity(unit_id)
        if e is None:
            return None
        uc = e.get_component(UnitComponent)
        if uc is None:
            return None
        hc = e.get_component(HealthComponent)
        # SetHealth @180e93450 : hp = Min(hp_arg, GetStat(unit, Health, MAX)). Sans HealthComponent/max
        # capte -> on pose hp_arg brut (fidelite-safe : le clamp natif est un Min, jamais un boost).
        set_hp = None
        if hc is not None and hp is not None:
            set_hp = int(hp)
            if hc.hp_max is not None:
                set_hp = min(set_hp, int(hc.hp_max))     # Min(hp_arg, maxHP)
            hc.hp = set_hp
        # flags @180e923b0 : Remove(0xf), Remove(8=overkill), Add(0x14) -> l'unite redevient VIVANTE.
        # Le port modelise l'etat de vie via `uc.alive` (les flags ECS 0xf/8/0x14 = internes non suivis).
        uc.alive = True
        # SetRevivePosition @180e936e0 : IN-PLACE -> position inchangee (aucune ecriture de PositionComponent).
        # #60 : re-eval du stat-mod EXTRA_HITS du trait Swarm au retour a la vie (bras On(UnitRevived=46) du
        # SwarmAbility.CreateTrigger @181225f50), comme ResurrectUnitOperation.
        if hc is not None and set_hp is not None:
            from ..abilities.loki.swarm import on_group_unit_hp_changed
            on_group_unit_hp_changed(state, unit_id)
        # emet On(UnitRevived=46=0x2e) -> downstream (Swarm deja re-eval ci-dessus ; pas d'autre consommateur
        # porte a ce jour). Le report est un diagnostic pour le replay-diff.
        return {"revived": int(unit_id), "hp": set_hp, "in_place": True}


def reset_revive_gates(state: State) -> None:
    """Debut de tour -> REACTIVE le passif revive (remet `revive_used_this_turn=False` pour TOUTES les
    unites). Mirror de la RE-ACTIVATION au turn-start de l'effet `ReviveEffect` desactive par `DeactivateEffect`
    apres un revive reussi (i2 « Can only be triggered once per turn »). Meme patron que `reset_times_attacked`
    (per-unite, per-tour). Appele par `start_turn_triggers`."""
    for e in state.entities.values():
        uc = e.get_component(UnitComponent)
        if uc is not None:
            uc.revive_used_this_turn = False
