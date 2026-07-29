"""Retrait d'unite du plateau -- `IdunBattle.Operations.RemoveUnitOperation$$Execute` (mutateur ECS
IMPERATIF). **Un DESPAWN, PAS une mort** : aucun vecteur on-death, aucune attribution de tueur,
les PV ne sont pas touches et le flag `Dead (6)` n'est PAS pose.

Frontiere DSL (#149) : la feuille `IdunBattleLogic.Entities.DSLFactory$$RemoveUnit` (au-dessus,
structurelle) APPELLE cette Operation (en-dessous, imperative). Chaine native complete :

    IdunBattleLogic.Entities.DSLFactory$$RemoveUnit(sel)
      -> IdunBattle.Entities.Behaviours.RemoveUnitBehaviour$$Execute
           resout le selecteur `+0x50` (groupType 3), puis PAR UNITE :
           slot +6 de l'interface `Core.Services.OperationProcessor` avec `(unitId, 1, 0)`
      -> Core.Services.OperationProcessor$$RemoveUnit           (gate `this+0x1f0 != 0`)
      -> IdunBattle.Operations.RemoveUnitOperation$$Execute(state, entity, removeEffects=1, param4=0)

SEQUENCE de `RemoveUnitOperation$$Execute`, LUE au decompile (`operationCtx+0x10` = `MatchState`,
`+0x18` = journal d'events de match, `+0x20` = logger, `+0x28` = `OperationProcessor`) :

  1. `entity == 0`                                     -> log d'erreur, RETURN (aucune mutation)
  2. `IdunBattle.Entities.EntityExtensions$$IsUnit`    -> faux : log d'erreur, RETURN
  3. **GATE** `IdunBattle.Entities.UnitExtensions$$HasFlag(entity, 0x1a)` vrai -> log, RETURN
     (`0x1a = 26 = UnitFlag.Removed`, dump d'enums -- anti-double-retrait)
  4. gate d'appartenance : `MatchState` slot 0x2f -> collection, slot 4 `(entity)` -> bool ;
     faux : log d'erreur, RETURN
  5. log << removing unit >>
  6. `OperationProcessor` slot 7 `(entity, false)`
  7. `PlayerComponent` du proprietaire (`MatchState` slot 0x29) :
     `List.Remove(unitId)` sur `+0x30` (units) puis `List.Add(unitId)` sur `+0x38` (unites RETIREES)
  8. `MatchState` slot 0x32 `(entity, options)` -- retrait des TUILES
  9. `IdunBattle.Entities.Components.UnitFlagsComponent$$Add(entity, 0x1a)` -- pose `Removed`
 10. sur le `BaseUnitComponent` : `+0x17c = TurnComponent$$GetAmountOfTurnsStartedByPlayer(...)`,
     `+0x180 = 1` (tour de retrait + booleen)
 11. si `param4 == 0` : `OperationProcessor` slot 0x55 `(entity, false)`
 12. event de MATCH : journal slot 2, type `0xc`, payload
     `{0x88: HasFlag(entity, 6=Dead), 0x89: HasFlag(entity, 8=Overkilled)}`
 13. **PUBLICATION `On(0x25 = 37 = UnitRemoved)`** : `OperationProcessor` slot 0x51 avec
     `(a = entity, b = entity, c = entity, eventType = 0x25, options)`
     -> **actor = caster = target = l'unite retiree**
 14. si `removeEffects != 0` : bloc INLINE identique a
     `IdunBattle.Operations.RemoveUnitOperation$$RemoveEffects` (`OperationProcessor` slot 0x5a)
 15. `OperationProcessor` slot 0x2f avec `{5, 0}` (meme appel de cloture qu'en fin de
     `IdunBattle.Operations.ResurrectUnitOperation$$Execute` -- non porte, comme la-bas)

ORDRE LOAD-BEARING : l'event `On(0x25)` part **APRES** la pose du flag `Removed` et le retrait des
tuiles, mais **AVANT** la consommation des effets portes (etape 14). Un port qui consommerait les
effets d'abord rendrait invisible, aux consommateurs de `On(0x25)`, tout effet porte par l'unite
retiree. Les deux sites de despawn du port faisaient exactement cela (et n'emettaient rien).

COLLAPSES ET RESIDUS NOMMES du port :
  * etape 8 (retrait des tuiles) -> `UnitComponent.alive = False`. C'est ce que les deux sites de
    despawn du port faisaient deja, et c'est ce qui LIBERE l'occupation (`_occupied` / `CanAddUnit`
    excluent les non-`alive`) -- indispensable au spawn qui suit l'eviction MV71. L'ecart avec le
    natif (qui ne touche NI les PV NI le flag `Dead`) est donc assume et INCHANGE par ce foyer ;
    la donnee fidele qui manquait est le flag `Removed`, desormais pose.
  * etapes 7, 10, 12 : ni `PlayerComponent.units`/`removedUnits`, ni le tour de retrait, ni l'event
    de match ne sont portes -- aucun consommateur porte ne les lit (cf.
    `playbook/noncomparable/doctrina_imperatives.py`, qui documente deja la liste `+0x30`).
  * etapes 6, 11, 15 : slots `OperationProcessor` non identifies, non portes (aucune autre Operation
    portee ne les porte non plus).
  * `IdunBattle.Operations.ResurrectUnitOperation$$Execute` retire le flag (`Remove(0x1a)`, avec
    6/0xf/8/9) -- porte dans `resurrect.py`, ce qui referme le cycle pose/retrait.
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import UnitComponent, UnitFlagsComponent


class RemoveUnitOperation:
    """Mirror `IdunBattle.Operations.RemoveUnitOperation$$Execute`.

    `remove_effects` = le `param_3` natif (`RemoveUnitBehaviour$$Execute` passe **1** a son unique
    call-site). Rend `None` quand un gate refuse (entite inconnue, pas une unite, deja retiree) --
    aucune mutation, aucun event ; sinon un dict de trace.
    """
    __slots__ = ()

    @staticmethod
    def execute(state: State, unit_id: Optional[int], *,
                remove_effects: bool = True) -> Optional[dict]:
        if unit_id is None:                                    # 1. entity == 0
            return None
        e = state.get_entity(int(unit_id))
        if e is None:                                          # 4. gate d'appartenance (collapse)
            return None
        uc = e.get_component(UnitComponent)
        if uc is None:                                         # 2. `EntityExtensions$$IsUnit`
            return None
        fl = e.get_component(UnitFlagsComponent)
        if fl is None:
            fl = e.add_component(UnitFlagsComponent())
        if fl.has(UnitFlagsComponent.REMOVED):                 # 3. GATE anti-double-retrait
            return None
        if not uc.alive:
            # Corollaire du collapse etape 8 : une unite deja hors-plateau cote port (morte OU
            # retiree par un site qui ne posait pas encore le flag) n'est pas re-retiree.
            return None
        uc.alive = False                                       # 8. retrait des TUILES (collapse)
        fl.add(UnitFlagsComponent.REMOVED)                     # 9. `UnitFlagsComponent.Add(0x1a)`
        # 13. `On(UnitRemoved = 0x25)` -- AVANT la consommation des effets (etape 14).
        from .triggers.dispatch import unit_removed_triggers
        downstream = unit_removed_triggers(state, int(unit_id))
        consumed = []
        if remove_effects and state.effects is not None:       # 14. `RemoveUnitOperation$$RemoveEffects`
            for eff in state.effects.by_unit.get(int(unit_id), []):
                if not eff.consumed:
                    eff.consumed = True
                    consumed.append(int(eff.effect_type))
        return {"removed": int(unit_id), "effects_consumed": consumed, "downstream": downstream}
