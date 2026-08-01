"""La FILE DES TRIGGERED-ABILITIES DIFFEREES (#406) -- enfilement, drain, et re-declenchement
d'une ability par son `TriggeredAbilityType` avec `triggerType = Custom`.

## La question que ce module tranche : QUAND la file est-elle drainee ?

Elle l'est **APRES la cloture complete du message top-level**, hors de tout arbre d'operations.
Chaine LUE de bout en bout sur `rnca9r7q6c` :

    IdunBattle.Entities.Behaviours.TriggerAbilityDelayedBehaviour$$Execute
        selected = <entitySelector>.Select(entities, unitSelectionType)      # slot 6 du selecteur
        foreach e in selected:
            state.<slot 6>(e.Id, this.triggeredAbilityType, entities)
              = IdunBattle.Core.MatchState$$AddPendingTriggeredAbility
              -> System.Collections.Generic.Queue<T>.Enqueue  sur  MatchState+0x28

    IdunBattle.Messages.InputMessageProcessor$$ProcessPendingTriggeredAbilities
        q = state.<slot 5>()                       # la Queue @MatchState+0x28
        if q.Count > 0:
            items = new List<T>(q) ; q.Clear()     # SNAPSHOT puis CLEAR, avant toute execution
            foreach it in items:
                RunPhase(0xf, <b__0(it)>, isInternalPhase: 1, 0)

    IdunBattle.Messages.InputMessageProcessor.u003Cu003Ec__DisplayClass51_0$$u003CProcessPendingTriggeredAbilitiesu003Eb__0
        entity = state.<slot 0x29>(it.entityId)
        processor.<slot 0x56>(entity, it.abilityType, it.entities, previousResult = <memset 0>,
                              ignoreUnitHavingAbility = 0)
          = Core.Services.OperationProcessor$$TriggerAbility
          -> IdunBattle.Operations.TriggerTriggeredAbilityOperation$$Execute / $$TriggerAbility

Et les TROIS appelants de `$$ProcessPendingTriggeredAbilities` sont TOUS hors de l'arbre
d'operations -- deux dans `IdunBattle.Messages.InputMessageProcessor$$RunPhase`, un dans
`IdunBattle.Messages.InputMessageProcessor$$VerifyTurnEnd`. Corps de `RunPhase` (branche
`state != null`), dans l'ordre LU :

    action()                                   <- l'arbre d'operations du message
    VerifyDeaths ; ProcessDamageEvents
    processor.<0x1e>
    ProcessPendingTriggeredAbilities           <- DRAIN #1
    processor.<0x14>
    if (isInternalPhase == 0) {
        processor.<0x8e> ; processor.<0x94> ; VerifyDrafting ; processor.<0x21>
        processor.<0x20>(0, isManualTurnEnd)
        ProcessPendingTriggeredAbilities       <- DRAIN #2
        VerifyDeaths ; ProcessDamageEvents ; VerifyDrafting ; processor.<0x21>
    }
    state.<0x23>(type)                         <- EndPhase (le `phase_end_triggers` du port)

**REPONSE : le drain est strictement APRES le retour de `action()`** -- donc apres
`IdunBattle.Operations.FinishAttackOperation$$Execute`, donc apres `On(9 = Attack)` et
`On(10)`. Une ability enfilee pendant la resolution d'une attaque s'execute quand l'attaque
est TERMINEE, et son `MoveUnit` ne peut donc pas faire entrer `On(PreUnitMove)` /
`On(UnitAfterMove)` -- l'overwatch -- au milieu des coups.

## Ou le port pose ces deux bornes

  * ENFILEMENT : la feuille DSL `TriggerAbilityDelayed`
    (`runner/abilities/behaviours/lifecycle.py`) appelle `add_pending_triggered_ability`.
  * DRAIN : `Runner.apply`, en SORTIE des post-handlers et AVANT `phase_end_triggers`
    (`EndPhase`) -- exactement la position du DRAIN #1. Le DRAIN #2 (bloc de fin de tour) et
    celui de `VerifyTurnEnd` ne sont pas des points d'ancrage separes cote port : `apply` est
    la borne unique du message top-level, et un `EndTurnMessage` y passe comme les autres.
    RESIDU NOMME : deux drains natifs par phase non-interne, un seul cote port -- sans effet
    observable tant qu'aucun enfileur ne tourne DANS le bloc de fin de tour (aucun porte).

## Ce que le re-declenchement fait, et ne fait pas

`TriggerTriggeredAbilityOperation$$TriggerAbility(entity, abilityName, abilityEntities,
ignoreUnitHavingAbility)` recupere les triggered-abilities de type `abilityName` PORTEES par
l'entite (slot 1 du cache), garde celles dont le porteur est vivant (`IdunBattle.Entities.
UnitExtensions$$IsAlive`, saute pour une entite non-unite), puis appelle le slot 4 de l'ability
avec **`triggerType = 0x20`** -- le litteral est visible dans le dernier argument de l'appel.
C'est ce qui selectionne la branche `Custom` d'un `CreateBehaviour` qui fourche.
Puis, si le slot 9 rend vrai, `IdunBattle.Entities.Components.TriggeredAbilityComponent$$
MarkAsTriggered(abilityName)`.

`previousResult` est **memset a 0** par le closure du drain : l'ability differee repart d'un
`OperationResult` vierge, elle n'herite rien de l'operation qui l'a enfilee.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import UnitComponent
from ..base import TriggerEvent


def add_pending_triggered_ability(state: State, entity_id: Optional[int],
                                  ability_type: int, ev: TriggerEvent) -> bool:
    """`IdunBattle.Core.MatchState$$AddPendingTriggeredAbility(entity, triggeredAbilityType,
    entities)` -- un `Queue<T>.Enqueue` sur `MatchState+0x28`, RIEN d'autre.

    Le natif ENQUEUE sans aucun gate : ni « l'entite porte-t-elle l'ability », ni « est-elle
    vivante » (les deux verdicts sont rendus au DRAIN, par `TriggerTriggeredAbilityOperation`).
    Le seul refus du corps natif est `entity == null` (`FUN_1801f51f0` = throw).

    Le natif memorise l'`AbilityEntities` COMPLET (0x128 octets copies dans la file) ; le port
    memorise le `TriggerEvent`, dont le drain reconstruit un contexte identique."""
    if entity_id is None:
        return False
    state.pending_triggered_abilities.append((int(entity_id), int(ability_type), ev))
    return True


def trigger_triggered_ability(state: State, entity_id: int, ability_type: int,
                              ev: TriggerEvent) -> list[dict]:
    """`Core.Services.OperationProcessor$$TriggerAbility` -> `IdunBattle.Operations.
    TriggerTriggeredAbilityOperation$$Execute` -> `$$TriggerAbility`, collapse sur ce que le port
    modelise.

    Le natif : (1) `entity = state.GetEntity(id)` ; (2) `abilities = cache.Get(abilityName)` --
    les triggered-abilities de CE type portees par l'entite ; (3) par ability, gate
    `IsUnit(entity) => IsAlive(entity)` ; (4) `ability.<slot 4>(abilityState, entities,
    triggerType = 0x20 = Custom)` ; (5) `MarkAsTriggered`.

    Le port : le registre `CUSTOM_TRIGGERED_ABILITIES` (registry.py) est le mirror du (2) --
    il repond « quelles classes portent la branche `Custom` du `CreateBehaviour` de cette
    `TriggeredAbilityType` ». Le gate (3) est le meme `UnitComponent.alive` que
    `evaluate_trigger_operation`. Le (5) n'a pas de lecteur porte (le cap par phase du port est
    keye par type de classe, pas par `TriggeredAbilityType`) -- NON porte, nomme.

    `matches` n'est PAS rappele : le natif ne re-evalue AUCUN trigger ici (le declenchement est
    IMPERATIF, c'est tout l'objet de `TriggerAbilityDelayed`). Seul le gate d'existence/vie
    s'applique. Cote branche `Custom`, la condition qui restait -- `NOT IsAdjacent(...)` -- est
    DANS l'arbre du behaviour, pas dans le trigger : elle s'evalue donc a l'etat COURANT, ce que
    le port respecte en la portant comme noeud `If`."""
    from .registry import CUSTOM_TRIGGERED_ABILITIES
    out: list[dict] = []
    classes = CUSTOM_TRIGGERED_ABILITIES.get(int(ability_type), ())
    if not classes:
        return out
    e = state.get_entity(int(entity_id))
    if e is None:
        return out
    uc = e.get_component(UnitComponent)
    if uc is not None and not uc.alive:          # `IsUnit(entity) && !IsAlive(entity)` -> saute
        return out
    for cls in classes:
        entry = cls(int(entity_id))
        # `BaseTriggeredAbility$$Execute` ecrit `CurrentAbility` (`AbilityEntities+0x60`) AVANT le
        # behaviour -- meme geste (et meme sauvegarde/restauration) que `evaluate_trigger_operation`.
        prev_trig = getattr(state, "triggering_ability", None)
        if entry.TRIGGERED_ABILITY_ID is not None:
            state.triggering_ability = int(entry.TRIGGERED_ABILITY_ID)
        try:
            r = entry.execute_behaviour(state, ev)
        finally:
            state.triggering_ability = prev_trig
        if r is not None:
            out.append(r)
    return out


def process_pending_triggered_abilities(state: State) -> list[dict]:
    """`IdunBattle.Messages.InputMessageProcessor$$ProcessPendingTriggeredAbilities`.

    SNAPSHOT + CLEAR avant d'iterer, exactement comme le natif (`new List<T>(q)` puis
    `q.Clear()`) : une ability enfilee PENDANT le drain n'est pas vue par CETTE vague. Le natif
    la rattrape parce que chaque item tourne dans un `RunPhase(0xf, ..., isInternalPhase: 1)`
    qui RE-DRAINE la file en fin de course ; le port reproduit ce rattrapage par la boucle
    `while` ci-dessous (memes vagues, meme ordre).

    Le garde `draining_pending_abilities` est le pendant exact de `draining_deaths` : il empeche
    qu'un drain lance depuis l'interieur d'une vague (re-entrance) re-entre dans la boucle --
    le natif, lui, a la meme propriete par construction (la file est deja vide au moment ou la
    cascade interne re-appelle le drain, sauf si l'item a enfile, ce que la vague suivante prend).

    No-op silencieux si la file est vide (le natif teste `q.Count > 0` avant tout)."""
    out: list[dict] = []
    if state.draining_pending_abilities or not state.pending_triggered_abilities:
        return out
    state.draining_pending_abilities = True
    try:
        # Borne de securite sur le nombre de VAGUES. Le natif n'en a pas -- il s'appuie sur le cap
        # par phase de `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityTrigger`
        # (`GetTimesTriggeredThisPhase < 0x33`), qui ne couvre PAS ce chemin imperatif. Une ability
        # qui se ré-enfile elle-meme bouclerait donc a l'infini cote port comme cote natif ; la
        # borne rend la panne VISIBLE (liste tronquee) au lieu de figer le process. Aucun porteur
        # porte n'approche 2 vagues.
        for _ in range(64):
            items = list(state.pending_triggered_abilities)      # SNAPSHOT
            state.pending_triggered_abilities.clear()            # puis CLEAR -- dans CET ordre
            if not items:
                break
            for entity_id, ability_type, ev in items:
                out.extend(trigger_triggered_ability(state, entity_id, ability_type, ev))
    finally:
        state.draining_pending_abilities = False
    return out
