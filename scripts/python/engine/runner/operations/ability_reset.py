"""ETAT D'UTILISATION des abilities actives : predicat de reset + Operation de reset.

Deux artefacts natifs, portes 1:1 :

  * `IdunBattle.Core.Services.BattleQuery$$EntityCanHaveActiveAbilityReset(unit, ignoreTurnFlag)`
    -- le predicat consomme par le selecteur `UnitsThatCanHaveActiveAbilityReset`
    (`IdunBattle.Entities.Selectors.UnitsThatCanHaveActiveAbilityResetSelector$$Select`) ET par
    `IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$GetDynamicInvalidTargetReason`
    (3e branche de legalite du cast).
  * `IdunBattle.Operations.ResetActiveAbilityOperation$$Execute(unit, flag)` -- le MUTATEUR
    (`CanStillBeUsed = true`, cooldown remis a zero) declenche par la feuille DSL `ResetActiveAbility`.

Les deux operent sur `ActiveAbilitiesComponent` (mirror de `ActiveAbilityComponent`), seede depuis
`decisionView.units[].abilities` (cf. `snapshot._active_abilities`).
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import ActiveAbilitiesComponent, UnitFlagsComponent


def entity_can_have_active_ability_reset(state: State, unit_id: int,
                                         ignore_turn_flag: bool = False) -> Optional[bool]:
    """`IdunBattle.Core.Services.BattleQuery$$EntityCanHaveActiveAbilityReset` -- MIRROR du DECOMPILE :

        foreach ab in unit.ActiveAbilityComponent.Collection :
            if (!abilitiesDb[ab.AbilityName].<slot 0x12 = resettable>) continue
            if (!ab.IsInCooldown) {
                if (ab.CanStillBeUsed == 0) return true          # charge CONSOMMEE, hors cooldown
            } else if (ab.<+0x34> == 0) {
                if (ignoreTurnFlag)                    return true
                if (!UnitExtensions.HasFlag(unit, 3))  return true     # tour PAS termine
                if (ab.RemainingCooldownTurns > 1)     return true
            }
        return false

    Ce que ca dit : une ability est « resettable » si elle a ete CONSOMMEE (plus de charge) ou si elle
    est EN COOLDOWN (sous conditions de tour). C'est exactement le split de l'i2 d'InspiredToGreatness
    (« heals for 1091 » = allie qui A utilise son actif ; « if that unit has not used their active
    ability yet, then 4365 » = le complementaire).

    NON PORTE (residus documentes, fidelite-safe) :
      * le gate `abilitiesDb[type].<slot 0x12>` (l'ability est-elle marquee resettable dans la base) --
        approxime par « entree `kind` active/granted », le natif excluant de toute facon l'attaque
        normale (`IsRegularAttack`) que `_active_abilities` ne seede pas ;
      * `ab.<+0x34>` (booleen non nomme, entre `IsDisabled@0x35` et le Nullable de cooldown) -> lu
        comme 0 (branche PRISE), le cas contraire n'etant pas observable par le canal live.

    Rend `None` quand l'unite n'a AUCUN `ActiveAbilitiesComponent` (canal `allAbilities` non demande
    a `decisionView`) : le verdict est INCONNU, pas « faux » -- l'appelant doit propager l'ignorance
    plutot que de fabriquer un `False` qui basculerait silencieusement le split de heal."""
    e = state.get_entity(int(unit_id))
    if e is None:
        return None
    comp = e.get_component(ActiveAbilitiesComponent)
    if comp is None:
        return None                                   # canal absent -> verdict INCONNU (jamais False)
    fl = e.get_component(UnitFlagsComponent)
    turn_finished = bool(fl is not None and fl.has(UnitFlagsComponent.TURN_FINISHED))
    for ab in comp.abilities:
        if not ab.is_in_cooldown():
            if not ab.can_still_be_used:              # charge consommee, hors cooldown
                return True
        else:                                         # en cooldown (le champ +0x34 est lu comme 0)
            if ignore_turn_flag:
                return True
            if not turn_finished:                     # `!HasFlag(unit, 3 = TurnFinished)`
                return True
            if int(ab.remaining_cooldown or 0) > 1:
                return True
    return False


class ResetActiveAbilityOperation:
    """`IdunBattle.Operations.ResetActiveAbilityOperation$$Execute(unit, flag)` -- MIRROR du DECOMPILE :

        if (!BattleQuery.EntityCanHaveActiveAbilityReset(unit, flag)) return
        foreach ab in unit.ActiveAbilityComponent.Collection :
            if (StaticBattleRules.ActiveAbility.IsRegularAttack(ab.AbilityName)) continue
            if (!abilitiesDb[ab.AbilityName].<slot 0x12>)                        continue
            ab.<+0x18> = 0 ; ab.<+0x10> = 0 ; ab.CanStillBeUsed@0x28 = 1
            Events.Publish(0xe, unit, {0x12: type, 0x18/0x19: abilityState, 0x13: 1, 0x15: disabled})
            if (ab.IsInCooldown) proc.<slot 0x92>(unit, type, null, 1)      # remise a zero du cooldown

    Port : `can_still_be_used = True` + `remaining_cooldown = None` (le slot 0x92 remet le Nullable a
    « pas de cooldown » -- c'est l'observable `usable: true, cooldown: null` du canal live). Les slots
    `+0x10`/`+0x18` (compteurs d'usage internes non exposes par le canal) et l'event 0xe (vue) ne sont
    pas modelises. `IsRegularAttack` est deja assure par le seed (`kind` active/granted seulement)."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, unit_id: int, ignore_turn_flag: bool = False) -> dict:
        e = state.get_entity(int(unit_id))
        comp = e.get_component(ActiveAbilitiesComponent) if e is not None else None
        if comp is None:
            return {"unit": int(unit_id), "reset": [], "gate": None}
        gate = entity_can_have_active_ability_reset(state, unit_id, ignore_turn_flag)
        if not gate:                                  # gate natif EN TETE d'Execute
            return {"unit": int(unit_id), "reset": [], "gate": bool(gate)}
        done = []
        for ab in comp.abilities:
            ab.can_still_be_used = True
            ab.remaining_cooldown = None              # slot 0x92 : cooldown remis a zero
            done.append(int(ab.ability_type))
        return {"unit": int(unit_id), "reset": done, "gate": True}
