"""Re-ATTACHEMENT d'une Machine of War a sa plateforme -- `IdunBattle.Operations.
ReAddMachineOperation$$Execute` (mutateur ECS IMPERATIF), le SYMETRIQUE exact de
`IdunBattle.Operations.RemoveMachineOperation$$Execute` (porte par la feuille `RemoveMachine`,
`abilities/behaviours/lifecycle.py`). #1078-r2.

Frontiere DSL (#149) : la feuille `IdunBattleLogic.Entities.DSLBehaviors$$ReAddMachine` (au-dessus,
structurelle) APPELLE cette Operation (en-dessous, imperative). Chaine native complete :

    IdunBattleLogic.Entities.DSLBehaviors$$ReAddMachine(unit, resetFlags)
      -> IdunBattle.Entities.Behaviours.ReAddMachineBehaviour$$Execute
           unit = <this+0x50>.<slot 9 = SelectSingle>(entities)     ; null -> resultat VIDE
           if (<this+0x58> != null)                                 ; `resetFlags` est un TRIGGER
               b = <this+0x58>.<slot 0 = ShouldTrigger>(entities)
               processor.<slot 10 = ReAddMachine>(unit, b)
      -> Core.Services.OperationProcessor$$ReAddMachine
      -> IdunBattle.Operations.ReAddMachineOperation$$Execute(machine, resetFlags)

⚠ **`resetFlags` N'EST PAS UN BOOLEEN AU NIVEAU DSL, C'EST UN PREDICAT**, et les deux call-sites du
build le prouvent : `HunterOfSoulsAbility$$CreateBehaviour` passe `<DSLTriggers+0x70>` (le
`YesTrigger` CONSTANT, donc toujours VRAI) et `HunterOfSouls_KilledAbility$$CreateBehaviour` passe
`NOT HasFlag(Owner@DSLSelectors+0x30, 0x3 = TurnFinished)`. Le booleen n'apparait qu'a la frontiere
de l'Operation, apres evaluation. Le lire comme un `bool` litteral au niveau de la feuille aurait
fige le second call-site sur une valeur arbitraire.

SEQUENCE de `ReAddMachineOperation$$Execute`, LUE au decompile (`operationCtx+0x18` = `MatchState`,
`+0x20` = `OperationProcessor`) :

  1. `machine == 0`                                      -> log d'erreur, RETURN (aucune mutation)
  2. `IdunBattle.Entities.EntityExtensions$$IsMachine`   -> faux : log d'erreur, RETURN
  3. **GATE d'anti-double-ajout** : pool `MatchState` slot 0x2f `(6)` -> collection ; si elle
     CONTIENT deja `machine` : log d'AVERTISSEMENT, RETURN (aucune mutation)
  4. `owner = MatchState` slot 0x29 `(machineComponent+0x10)` ; si non nul, sur son composant :
     `+0x74 = machine.Id` et `+0x78 = machine.Id`
  5. `slot = machineComponent+0x78` (le `MachineOfWarPosition`) ; balayage du pool
     `MatchState` slot 0x2f `(7)` (les PLATEFORMES) jusqu'a celle dont `+0x10 == slot` ->
     `+0x14 = Nullable<BEntityId>(machine.Id)` (`MachinePlatformComponent.MachineId`)
  6. AJOUT au pool 6 : `MatchState` slot 0x31 `(machine, <struct dont +0x20 = 6>)`
  7. si l'`AbilitiesComponent` porte >= 2 abilities (ou 1 qui n'est pas la cle 0) :
     `OperationProcessor` slot 0x54 `(machine)`
  8. si `resetFlags` : `IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags(
     flagsComponent, includeNoAction = 1, newActivation = 0)`
  9. `OperationProcessor` slot 0x5f `(machine)`
 10. events de match : type `0x3c` (payload `{0x77: owner.Id, 0x9a: owner.CurrentTeamId}`), puis
     `0xc` (tags d'etat complet), puis `0xc` (`{0x6f: !HasFlag(machine, 4)}`), puis un `0xd` par
     ability et par plateforme
 11. `OperationProcessor` slot 0x2f avec `{5, 0}` (meme appel de cloture qu'en fin de
     `IdunBattle.Operations.RemoveUnitOperation$$Execute` -- non porte, comme la-bas)

CE QUE LE PORT MATERIALISE, ET CE QU'IL NE MATERIALISE PAS. La regle est celle qu'a etablie
`RemoveMachine` (#91) : on porte le DETACHEMENT/RATTACHEMENT et rien d'autre, parce que tout le
reste serait une invention que la mesure REFUTE. Le port n'a ni pool d'entites, ni
`MachinePlatformComponent`, ni bus d'events de plateforme -- `MachineComponent.removed` EST, cote
port, le lien machine<->plateforme (cf. sa docstring). Donc :

  * etapes 1/2 -> gates portes tels quels (entite absente / non-Machine : aucune mutation) ;
  * etape 3   -> `removed is False` = << deja dans le pool >> : RETURN sans mutation. C'est le
                 pendant EXACT du gate natif, sur le seul substrat que le port possede ;
  * etape 6   -> `MachineComponent.removed = False`, le rattachement lui-meme ;
  * etape 8   -> `UnitFlagsComponent.remove_turn_flags(include_no_action=True,
                 new_activation=False)`. Les DEUX litteraux sont LUS (`RemoveTurnFlags(&ret, comp,
                 1, 0)` -- le `0` est le registre `lVar9` mis a zero juste avant l'appel), et ils
                 ne sont PAS interchangeables : `new_activation` retirerait `Moved`/`Teleported`/
                 `ArrivedAtFinalTile`, ce que ce site ne fait PAS ;
  * etapes 4/5/7/9/10/11 -> NON PORTEES (pool, plateformes, slots non identifies, bus d'events).
    Aucun consommateur porte ne les lit -- meme statut que les etapes 7/12 de `RemoveUnitOperation`.

⚠ **CE QUE L'OPERATION NE FAIT PAS, ET C'EST UNE LECTURE** : elle ne RESTAURE aucun effet. Le
retrait, lui, les CONSOMME (`RemoveMachineOperation$$RemoveEffects`). Un rattachement qui les
ressusciterait serait une invention pure.
"""
from __future__ import annotations

from typing import Optional

from ..components import MachineComponent, UnitFlagsComponent, is_machine_of_war


class ReAddMachineOperation:
    """`IdunBattle.Operations.ReAddMachineOperation$$Execute(machine, resetFlags)` -- cf. l'en-tete."""

    @staticmethod
    def execute(state, machine_id: int, reset_flags: bool = False) -> Optional[dict]:
        """Rend `None` quand un gate natif REFUSE (aucune mutation), sinon le journal de ce qui a
        ete mute. Les trois refus sont ceux du natif, dans son ordre : entite absente, entite
        non-Machine, machine deja rattachee."""
        if state is None or machine_id is None:
            return None                                  # 1. `machine == 0` -> log d'erreur, RETURN
        e = state.get_entity(int(machine_id))
        if not is_machine_of_war(e):                     # 2. `EntityExtensions$$IsMachine`
            return None
        mc = e.get_component(MachineComponent)
        if not mc.removed:
            # 3. la machine est DEJA dans le pool 6 : le natif log un AVERTISSEMENT et sort sans
            #    rien muter. Ne pas confondre avec un echec : c'est un no-op volontaire, et c'est
            #    ce qui rend l'operation idempotente sur un double `ReAddMachine`.
            return None
        mc.removed = False                               # 6. AJOUT au pool 6 (le rattachement)
        flags_cleared: list = []
        if reset_flags:                                  # 8. `RemoveTurnFlags(comp, 1, 0)`
            fl = e.get_component(UnitFlagsComponent)
            if fl is not None:
                flags_cleared = sorted(fl.remove_turn_flags(include_no_action=True,
                                                            new_activation=False))
        return {"machine": int(machine_id), "reset_flags": bool(reset_flags),
                "flags_cleared": flags_cleared}
