"""Résurrection d'unité — `IdunBattle.Operations.ResurrectUnitOperation$$Execute` (mutateur ECS IMPÉRATIF).

Frontière DSL : la feuille `IdunBattleLogic.Entities.DSLFactory$$Resurrect` (au-dessus, structurelle) APPELLE cette
Operation (en-dessous, impératif). Chaîne native : `IdunBattle.Entities.Behaviours.ResurrectBehaviour$$Execute` (zip units×tiles)
→ `ResurrectUnitMessage` → `Core.Services.OperationProcessor$$ResurrectUnit` → `IdunBattle.Operations.ResurrectUnitOperation$$Execute`. Ici on porte la MUTATION observable (le pipeline de file/stream = couche view non suivie) :

  * gardes `IsDefeated(unit)` (une unité vivante n'est pas ressuscitée) ;
  * repositionne l'unité sur la tuile du decoy ;
  * `IdunBattle.Operations.ResurrectUnitOperation$$KillSteppableUnits` : le decoy sur lequel on réapparaît est CRUSHÉ (`_kill_steppable_units`,
    G1) — c'est ce decoy MORT co-localisé qui alimente `DecoysAndMisdirection_BuffFriends` (G2, +582 + decoy) ;
  * flags natifs `Remove(6,0xf,8,0x1a,9)` puis `Add(2=alive, 0xe=UnitPostAbility)` → on pose `alive=True`
    + le flag one-shot `AMBUSH_CONSUMED (0xe)` (re-mourir ne re-ressuscite PAS) ;
  * `IdunBattle.Operations.ResurrectUnitOperation$$SetHealth` = PV pleins (le `StatAmount(unit, Health=5, mode=2)` passé par le behaviour) ;
  * si `takesImmediateTurn (param_7)` → `RemoveTurnFlags(unit,1,1)` → l'unité peut REJOUER immédiatement
    (l'exécution du tour = couche IA/contrôleur, pas cette Operation) ;
  * émet `On(UnitResurrected=0x2e=47)` → `unit_resurrected_triggers` → alimente G2 `BuffFriends` + G5 ré-arme.

⚠ NE PAS confondre avec la couche DÉCISION `RitesOfRestorationPlaybook` (`playbook/noncomparable/heals.py`,
`GetPossibleResurrectTargets`) qui SCORE l'évaluation IA — le runner n'avait PAS d'Operation resurrect ;
c'est un AJOUT net (piège check-own-port).
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import (UnitComponent, PositionComponent, HealthComponent, UnitFlagsComponent)


class ResurrectUnitOperation:
    """Mirror `IdunBattle.Operations.ResurrectUnitOperation$$Execute` (mutateur ECS). `dest_coord` = (col,row) de la
    tuile du decoy ; `hp` = PV à restaurer (PV pleins) ; `immediate_turn` = tour immédiat après résurrection."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, unit_id: int, dest_coord, hp,
                *, immediate_turn: bool) -> Optional[dict]:
        e = state.get_entity(unit_id)
        if e is None:
            return None
        uc = e.get_component(UnitComponent)
        if uc is None or uc.alive:            # IsDefeated : une unité vivante n'est pas ressuscitée
            return None
        # repositionne sur la tuile du decoy
        if dest_coord is not None:
            pc = e.get_component(PositionComponent)
            if pc is not None:
                pc.col, pc.row = int(dest_coord[0]), int(dest_coord[1])
        # IdunBattle.Operations.ResurrectUnitOperation$$KillSteppableUnits : crushe le decoy de la tuile d'arrivée (mover = l'unité ressuscitée,
        # non tuée elle-même). Le decoy MORT co-localisé -> source de G2 BuffFriends.
        crushed = []
        if dest_coord is not None:
            from .movement import _kill_steppable_units
            crushed = _kill_steppable_units(state, (int(dest_coord[0]), int(dest_coord[1])), unit_id)
        # revive : alive + PV pleins + flag one-shot 0xe (Ambush consommé)
        uc.alive = True
        hc = e.get_component(HealthComponent)
        if hc is not None and hp is not None:
            hc.hp = int(hp)                   # IdunBattle.Operations.ResurrectUnitOperation$$SetHealth
            # #60 : bras `On(UnitRevived=45) & OwnerIsTarget` du `SwarmAbility.CreateTrigger
            # IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateTrigger` — re-evalue le stat-mod EXTRA_HITS du trait Swarm au retour a la vie.
            from ..abilities.loki.swarm import on_group_unit_hp_changed
            on_group_unit_hp_changed(state, unit_id)
        fl = e.get_component(UnitFlagsComponent)
        if fl is None:
            fl = e.add_component(UnitFlagsComponent())
        # Remove(0x1a = Removed) : une unité RETIRÉE du plateau qui revient n'est plus « retirée »
        # (`RemoveUnitOperation` pose ce flag, cf. `operations/remove_unit.py`). Le natif l'appelle
        # dans la même rafale que Remove(6)/Remove(0xf)/Remove(8)/Remove(9).
        fl.remove(UnitFlagsComponent.REMOVED)
        fl.add(UnitFlagsComponent.AMBUSH_CONSUMED)      # Add(0xe) — one-shot
        # tour immédiat : RemoveTurnFlags(1,1) -> l'unité redevient actionnable (retire NoAction + turn-flags)
        if immediate_turn:
            fl.remove_turn_flags(include_no_action=True, new_activation=True)
        # émet On(UnitResurrected=46) -> G2 BuffFriends (+582 + decoy si GS Cult) + G5 ré-arme HeroicFusillade
        from .triggers.dispatch import unit_resurrected_triggers
        downstream = unit_resurrected_triggers(state, unit_id)
        return {"resurrected": int(unit_id), "tile": (int(dest_coord[0]), int(dest_coord[1])) if dest_coord else None,
                "hp": int(hp) if hp is not None else None, "crushed_decoy": crushed,
                "immediate_turn": bool(immediate_turn), "downstream": downstream}
