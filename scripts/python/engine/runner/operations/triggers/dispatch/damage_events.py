"""La file des DAMAGE-EVENTS et son drain -- l'emetteur d'`On(0x11 = PostDamageTaken)`. #443-r2-b2.

C'est le **second** des deux mecanismes DIFFERES du pipeline natif (l'autre etant
`state.pending_triggered_abilities`, `dispatch/pending.py`), et il suit EXACTEMENT le meme patron :
une file remplie pendant l'arbre d'operations, drainee a la borne du message top-level, par VAGUES.

================================================================================================
LA CHAINE NATIVE, LUE DE BOUT EN BOUT
================================================================================================

**ENFILEMENT** -- `IMatchState` slot **8** = `AddDamageEvent(source, caster, target)` ->
`IdunBattle.Core.MatchState$$AddDamageEvent`, dont le corps ENTIER est un `Enqueue` d'un struct :

    item = { source : AbilityOrEffect  @+0x00..+0x1b   (recopie des 0x1c octets de `source`)
             casterId : BEntityId      @+0x1c          (`caster.Id`, si `caster != null`)
             targetId : BEntityId      @+0x20 }        (`target.Id`, si `target != null`)

⚠ **UN SEUL ENFILEUR DANS TOUT LE BINAIRE**, et c'est une MESURE, pas une lecture partielle :
balayage LITTERAL du slot 8 d'`IMatchState` sur l'ensemble du decompile -> **1 site**,
`IdunBattle.Operations.ApplyDamageOperation$$Execute`. Il y appelle `AddDamageEvent` **juste
apres** avoir publie `On(0xf = DamageTaken)`, **dans le meme bloc garde** -- le gate le plus
interne etant le parametre `skipDamageEventTrigger` de l'operation, qui couvre les DEUX gestes
ENSEMBLE. `source` y vient du `damageResult`, `caster`/`target` sont les parametres de l'operation.

**DRAIN** -- `IdunBattle.Messages.InputMessageProcessor$$ProcessDamageEvents` :

    q = matchState.<slot 7 = GetDamageEvents>()
    if (q.Count > 0)                                        // GATE : rien si la file est vide
        RunPhase(PhaseType 0xe, <ProcessDamageEvents>b__0, isInternalPhase: 1)

et `InputMessageProcessor.<>c__DisplayClass52_0$$<ProcessDamageEvents>b__0` :

    snapshot = new List<T>(q) ; q.Clear()                   // SNAPSHOT puis CLEAR, dans CET ordre
    foreach (item in snapshot) {
        caster = matchState.<slot 0x29 = GetEntity>(item.casterId)
        target = matchState.<slot 0x29 = GetEntity>(item.targetId)
        processor.<slot 0x47 = 71 = ProcessPostDamageEvent>(&item.source, caster, target)
    }

et `IdunBattle.Operations.ProcessPostDamageEventOperation$$Execute(source, caster, target)`, dont
le corps ENTIER est UN appel :

    processor.<slot 0x51 = 81 = EvaluateAbilities>(caster, caster, target, **0x11**, source)

-> donc `actor == caster == le CASTER du degat`, `target == la VICTIME`, `eventType = 0x11`.

**RANG** -- `IdunBattle.Messages.InputMessageProcessor$$RunPhase`, relu VERBATIM :

    matchState.<0x22 = StartPhase>(type)
    action()                                     <- l'arbre d'operations du message
    VerifyDeaths()
    ProcessDamageEvents()                        <- ICI, **AVANT** le drain des differees
    processor.<0x1e>()
    ProcessPendingTriggeredAbilities()
    processor.<0x14>()
    if (!isInternalPhase) { ... ProcessPendingTriggeredAbilities() ; VerifyDeaths() ;
                            ProcessDamageEvents() ; ... }                 <- 2e passe
    matchState.<0x23 = EndPhase>(type)

⇒ Cote port, `Runner.apply` EST la borne du message top-level : le drain va donc **avant**
`process_pending_triggered_abilities`. Le SECOND couple (bloc de fin de tour) n'est pas porte --
MEME residu, deja nomme, que le second drain des triggered-abilities differees.

================================================================================================
CE QUE LE PORT MODELISE, ET CE QU'IL NE MODELISE PAS
================================================================================================
  * la file, son SNAPSHOT-puis-CLEAR et ses VAGUES : portes, meme forme que `pending.py` ;
  * `GetEntity(casterId)` / `GetEntity(targetId)` : le port memorise les IDS et les re-resout au
    drain, comme le natif -- une entite disparue entre l'enfilement et le drain est donc traitee
    comme le natif la traite (le vecteur part quand meme, `evaluate_trigger_operation` gere) ;
  * le `RunPhase(0xe, isInternalPhase: 1)` autour de chaque vague : NON porte comme phase, mais sa
    consequence observable -- la RE-ENTREE du drain -- l'est, par la boucle de vagues ;
  * `StartPhase`/`EndPhase` et les slots `0x1e`/`0x14` : non portes (aucun consommateur porte).

CONSOMMATEURS PORTES d'`On(0x11)` -- **TROIS**, et les trois l'ecoutaient DEJA en declarant
`event_ids = (UnitDeath, PostDamageTaken)` alors qu'aucun vecteur ne l'emettait. Le compte est
DERIVE du registre, pas recopie d'une fiche (celle de `#443-r2-b2` n'en nommait qu'un) : ce sont
les trois sous-classes d'`AReactivateOverwatchHitReductionPurge` --
`EarlyWarningOverrideHitReductionPurge` (effet 1145 -> retire 1146),
`InescapableDeathHitReductionPurge` (1018 -> 1019) et `FiringPositionHitReductionPurge` (1150).
C'est exactement la moitie dormante du vecteur de purge que `#443-r2-b2` nomme.

⚠ **CE QUE CE VECTEUR NE REVEILLE PAS** : les trois consommateurs portent le MEME gate
`NOT HasEffect(Owner, 0x3f1 = 1009 Overwatch_AutoAttack, onlyActive: 1)` et le MEME behaviour
(`RemoveEffect(Owner, <hitReduction>)`), donc leur SEUL effet est de retirer un effet de reduction
de coups qui n'a plus lieu d'etre. Un porteur qui n'a AUCUN des trois effets ne voit rien --
`evaluate_trigger_operation` n'instancie que les classes inscrites sous un effet REELLEMENT porte.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggerEvent
from .core import evaluate_trigger_operation

#: `EvaluateAbilities(..., 0x11, ...)` -- le litteral que passe
#: `ProcessPostDamageEventOperation$$Execute`.
_ON_POST_DAMAGE_TAKEN = int(EventTriggerType.PostDamageTaken)          # 0x11 = 17

#: Borne de securite sur le nombre de VAGUES -- meme raison et meme valeur que
#: `process_pending_triggered_abilities` : le natif n'en a pas, il s'appuie sur le cap par phase
#: d'`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityTrigger`. Un consommateur qui
#: re-infligerait du degat depuis `On(0x11)` bouclerait des DEUX cotes ; la borne rend la panne
#: VISIBLE (liste tronquee) au lieu de figer le process. Aucun consommateur porte n'approche 2.
_MAX_VAGUES = 64


def add_damage_event(state: State, source_ability: Optional[int],
                     caster_id: Optional[int], target_id: Optional[int]) -> None:
    """`IMatchState` slot 8 = `AddDamageEvent(source, caster, target)` ->
    `IdunBattle.Core.MatchState$$AddDamageEvent` -- MIRROR de l'ENQUEUE.

    Le natif enfile un struct `{source, casterId, targetId}`. Ses DEUX gardes sont LUS et portes :
    `caster == null` laisse `casterId` a ZERO (le champ est pre-mis a 0 et n'est ecrit que sous
    `if (caster != 0)`), tandis que **`target == null` fait SAUTER l'`Enqueue` entierement** --
    l'appel a `Queue$$Enqueue` est DANS le bloc `if (target != 0)`. Le port refuse donc sur cible
    absente et accepte un caster nul, exactement comme lui."""
    if state is None or target_id is None:
        return                            # `if (target != null) { ... Enqueue ... }` -- LU
    state.pending_damage_events.append(
        (None if source_ability is None else int(source_ability),
         None if caster_id is None else int(caster_id),
         int(target_id)))


def process_damage_events(state: State) -> list[dict]:
    """`IdunBattle.Messages.InputMessageProcessor$$ProcessDamageEvents` + son lambda -- cf. l'en-tete.

    SNAPSHOT + CLEAR avant d'iterer, exactement comme le natif (`new List<T>(q)` puis `q.Clear()`) :
    un event enfile PENDANT le drain n'est pas vu par CETTE vague. Le natif le rattrape parce que
    chaque vague tourne dans un `RunPhase(PhaseType 0xe, ..., isInternalPhase: 1)` qui RE-DRAINE la
    file en fin de course ; le port reproduit ce rattrapage par la boucle `while` (memes vagues,
    meme ordre).

    Le garde `draining_damage_events` est le pendant exact de `draining_pending_abilities`.

    No-op silencieux si la file est vide (le natif teste `q.Count > 0` avant meme d'ouvrir la
    phase -- c'est un GATE, pas une optimisation : sans lui il ouvrirait une phase par message)."""
    out: list[dict] = []
    if state.draining_damage_events or not state.pending_damage_events:
        return out
    state.draining_damage_events = True
    try:
        for _ in range(_MAX_VAGUES):
            items = list(state.pending_damage_events)        # SNAPSHOT
            state.pending_damage_events.clear()              # puis CLEAR -- dans CET ordre
            if not items:
                break
            for source_ability, caster_id, target_id in items:
                # `EvaluateAbilities(caster, caster, target, 0x11, source)` : `actor` ET `caster`
                # sont LE MEME argument cote natif (`ProcessPostDamageEventOperation$$Execute`
                # passe `caster` DEUX fois) -- ce n'est pas un repli du port.
                # Le 5e argument (`source`) est le meme canal que celui deja threade par
                # `damage_taken_triggers` sous le nom `source_ability` : `AbilityEntities+0x60`
                # (`CurrentAbility`), c.-a-d. `ev.ability_type` cote port.
                ev = TriggerEvent(_ON_POST_DAMAGE_TAKEN,
                                  caster_id if caster_id is not None else target_id,
                                  target_id, ranged=False, profile=None,
                                  ability_type=source_ability)
                out.extend(evaluate_trigger_operation(state, ev))
    finally:
        state.draining_damage_events = False
    return out
