"""L'ATTAQUE DIFFEREE herite d'`IdunBattle.Entities.Effects.APendingAttackEffect` (#513).

C'est le FOYER du patron 2-PHASES : une ability ACTIVE pose un effet de bond derive
d'`APendingAttackEffect` (phase 1, deja portee pour six abilities), et le DEGAT appartient a une
ability TRIGGERED que cet effet declenche AU DEBUT DU TOUR SUIVANT DE L'UNITE ATTAQUANTE (phase 2).
Le foyer est commun aux **20** derivees -- recensement `probe_513_pending_attack_family.py`.

================================================================================================
1. LE TRIGGER, MIRROR 1:1
================================================================================================
`IdunBattle.Entities.Effects.APendingAttackEffect$$CreateHandleTriggerAbilitiesInternal` AJOUTE un
`Triggered()` a l'`ArraySet` que rend
`IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal` (les trois retraits
de bond, portes par `bond_removal.py`) :

    Triggered(
        On(0x15 = EventTriggerType.TurnStart_DelayedAttacks)
        & IsTurnOf( <klass+0x758>() ),                       # GetAttackingUnitSelector
        DSLBehaviors.TriggerAbility(
            entity  = <klass+0x758>(),                       # l'unite ATTAQUANTE
            abilityType = <klass+0x768>(),                   # GetTriggeredAbilityType
            actor   = <klass+0x758>(),
            caster  = <klass+0x758>(),
            target  = Owner@DSLSelectors+0x30,               # le PORTEUR de l'effet
            unitFeetTiles = null, selectionType = <pile>, ignoreUnitHavingAbility = <pile> )
        & DSLBehaviors.RemoveEffect( Effect@DSLSelectors+0x38 ) )

Les deux morceaux sont AUSSI exposes separement -- `APendingAttackEffect$$GetAttackTrigger` rend
`IsTurnOf(GetAttackingUnitSelector())`, `$$GetAttackBehaviour` rend le `TriggerAbility(...)` seul --
et le corps de `CreateHandleTriggerAbilitiesInternal` les INLINE : les trois lectures concordent.

`<klass+0x758> GetAttackingUnitSelector` = `ABondEffect$$BondedEntitySelector` =
`BondedEntityFromEffect(Effect@0x38)`, c'est-a-dire l'entite BONDEE, pas le porteur. Le corps est
DEDUPLIQUE (un simple `jmp`) et ghidra ne le publie que sous UN proprietaire arbitraire
(`IdunBattle.Entities.Effects.Loki.ValkyrieStrikeEffect$$GetAttackingUnitSelector`) -- c'est le
piege « l'absence dans les tables ne prouve rien », et le nom du proprietaire ne dit rien de
l'appelant.

⚠ CETTE LECTURE EST CONFRONTEE, PAS DEDUITE, et le discriminant est le TOUR OU LE MISSILE PART.
Sur `1069 SeekerMissileFrequencyLock`, l'effet 1123 est pose SUR LA CIBLE et bonde AU CASTER : les
deux candidats (`Owner` = la cible, `BondedEntity` = le caster) appartiennent a des JOUEURS
DIFFERENTS, donc `IsTurnOf` les separe d'un tour entier. MESURE (board `MC1_67`, seed 777, deux
`endturn` NUS -- aucune unite n'agit entre les bornes) :

    cast                          -> PV cible 12049, rng (callCount 0, mti 624)
    endturn #1 (tour ENNEMI)      -> PV cible 12049 INCHANGES, rng inchange
    endturn #2 (tour DU CASTER)   -> PV cible 8625 (-3424), rng (4, 2), 1123 et 1136 RETIRES

Le missile part au debut du tour du CASTER. `GetAttackingUnitSelector` = l'entite BONDEE, mesure.

================================================================================================
2. CE QUE LE PORT POSE, ET POURQUOI PAS PLUS
================================================================================================
La table ci-dessous ne contient que les `EffectType` que le port POSE **et** dont la phase 2 est
portee. Une entree sans phase 2 dispatchable ferait firer un `TriggerAbility` qui ne muterait rien :
le noeud le DIRAIT (`dispatched: False`), mais l'effet serait tout de meme RETIRE par le
`RemoveEffect(Effect)` du meme `Triggered()` -- donc un marqueur qui disparait sans que rien ne
frappe. C'est PIRE que le statu quo (un marqueur inerte qui reste), et c'est la raison pour laquelle
l'inscription est conditionnee a la phase 2, pas au seul fait que l'effet soit de la famille.

Les CINQ autres effets de la famille que le port pose (`ValkyrieStrike_Effect` 1022,
`MalleusRocketLauncher` 1308, `DevastatingRefrain_Target` 1402, `HeavyRailRifle_PendingAttack` 1333,
`OverwhelmingWrath_PendingAttack` 1300) restent donc HORS table tant que leur `CreateBehaviour` de
phase 2 n'est pas porte -- residus nommes, cf. la fiche.
"""
from __future__ import annotations

from typing import NamedTuple, Optional

from ...abilities.behaviours.context import entities_from_state
from ...abilities.behaviours.effects import RemoveEffect
from ...abilities.behaviours.lifecycle import TriggerAbility
from ...components import OwnerComponent
from ...state import State
from ....dsl.effects import ExecutionContext
from ....dsl.event_trigger_type import EventTriggerType
from ....entities.behaviours import op_and
from ....entities.effect_type import EffectType
from ....entities.selectors.accessors import Target
from ....entities.selectors.tiles import Caster
from ....entities.triggered_ability_type import TriggeredAbilityType
from .base import EffectTrigger, TriggerEvent


class PendingAttackSpec(NamedTuple):
    """Ce que la classe d'effet NATIVE rend a ses deux virtuels, LU au decompile.

    `native` = le nom de la classe native VERBATIM : c'est lui qui rend la ligne re-verifiable, et
    la seule chose qui relie une valeur a sa lecture (meme discipline que `BondRemovalGates`).
    `triggered_ability` = `<klass+0x768> GetTriggeredAbilityType` -- un **`TriggeredAbilityType`**,
    jamais un `EffectType` : les deux enums partagent des centaines d'ordinaux (0x467 vaut
    `SeekerMissileFrequencyLock_Attack` ici et `AnnihilatorBeam_PendingAttack` la-bas)."""
    native: str
    triggered_ability: int


PENDING_ATTACK_EFFECTS: dict[int, PendingAttackSpec] = {
    # Pose par `IdunBattleLogic.Entities.Abilities.Active.Loki.SeekerMissileFrequencyLockAbility$$
    # ExecuteBehaviour` (1069, #491) : `AddBondEffect(0x463, CreateSnapshot(abilityState),
    # source = Caster, targets = Target, bondedEntity = Caster)`. La classe native est ETABLIE par
    # son propre `$$CreateHandleTriggerAbilitiesInternal`, qui appelle explicitement celui
    # d'`APendingAttackEffect` avant d'ajouter le sien.
    int(EffectType.SeekerMissileFrequencyLock_Target): PendingAttackSpec(
        "IdunBattle.Entities.Effects.Loki.SeekerMissileFrequencyLockTargetEffect",
        int(TriggeredAbilityType.SeekerMissileFrequencyLock_Attack)),
}


def pending_attack_tree(effect_type: int, triggered_ability: int):
    """Arbre du behaviour du `Triggered()` d'`APendingAttackEffect` -- rendu par une USINE et non
    construit inline, comme `bond_removal_tree` : c'est ce qui le rend INSPECTABLE par un garde
    offline.

        TriggerAbility( Caster(), <triggeredAbilityType> ) & RemoveEffect( <effet>, Target() )

    LA CORRESPONDANCE DE SLOTS, qui est tout l'enjeu de ce foyer. L'`AbilityEntities` que le port
    construit pour CE trigger pose :
        `Caster()` = l'unite ATTAQUANTE (`<klass+0x758>` = `BondedEntityFromEffect(Effect)`) ;
        `Target()` = le PORTEUR de l'effet (`Owner@DSLSelectors+0x30`).
    C'est exactement le couple que le natif passe a `DSLBehaviors.TriggerAbility` (`caster` =
    l'attaquant, `target` = l'owner), donc l'ability TRIGGERED de phase 2 lit `Caster@0x48` et
    `Target@0x60` sur les MEMES deux unites que le natif.

    ⚠ Les deux ne coincident PAS en general : sur 1069 l'attaquant est le CASTER du sort et le
    porteur est SA CIBLE. La convention `Owner == Caster` de `case-224` -- vraie sur une ACTIVE --
    est ici FAUSSE, et c'est le seul endroit du port ou les deux slots designent deux unites
    differentes de deux JOUEURS differents.

    `RemoveEffect(<effet>, Target())` mirrore `RemoveEffect(Effect@DSLSelectors+0x38)` : le natif
    tient l'entite-effet COURANTE, le port la retrouve par son type sur le PORTEUR -- meme collapse
    assume que `bond_removal_tree`, legitime par le gate << deja present >> d'`AddEffectOperation`
    qui garantit au plus UNE instance non consommee d'un effect_type par unite."""
    return op_and(TriggerAbility(Caster(), int(triggered_ability)),
                  RemoveEffect(int(effect_type), Target()))


def _pending_instance(state: State, owner_id: int):
    """L'instance NON CONSOMMEE, portee par `owner_id`, dont l'`effect_type` est dans la table.
    `None` sinon. Mirror du couple (`Effect@DSLSelectors+0x38`, `ABondEffect$$BondedEntityId`)."""
    eff = getattr(state, "effects", None)
    if eff is None:
        return None
    for e in eff.by_unit.get(int(owner_id), []):
        if e.consumed:
            continue
        if int(e.effect_type) in PENDING_ATTACK_EFFECTS:
            return e
    return None


class PendingAttackOnAttackersTurn(EffectTrigger):
    """Le `Triggered()` d'`IdunBattle.Entities.Effects.APendingAttackEffect$$
    CreateHandleTriggerAbilitiesInternal` -- l'attaque DIFFEREE qui part au debut du tour de l'unite
    attaquante.

        Triggered( On(0x15 = TurnStart_DelayedAttacks) & IsTurnOf(GetAttackingUnitSelector()),
                   TriggerAbility(...) & RemoveEffect(Effect) )

    UNE SEULE classe pour tous les `effect_type`, comme le natif : c'est `APendingAttackEffect` --
    la BASE -- qui construit ce `Triggered()` pour ses 20 derivees. L'attribut declaratif
    `effect_type` reste donc a `-1` ; le dispatch (`dispatch/core.py`) fait son lookup sur
    l'`effect_type` de l'INSTANCE, jamais sur celui de la classe de trigger. Meme forme que
    `BondRemoveOnBondedEntityDeath`.

    `IsTurnOf(selector)` -> `IdunBattle.Entities.Triggers.IsTurnOfUnitTrigger$$ShouldTrigger` : le
    joueur dont c'est le tour possede-t-il l'unite selectionnee ? Le vecteur
    (`dispatch/turn.py::delayed_attack_triggers`) threade `ev.player_id`, comme les quatre autres
    events de `IdunBattle.Operations.StartTurnOperation$$Execute`.

    ⚠ LE GATE PORTE SUR LE BONDE, PAS SUR LE PORTEUR -- et c'est ce qui rend le trigger atteignable
    alors que le porteur appartient au camp ADVERSE (cas de 1069). Le porteur, lui, n'est soumis a
    aucun gate d'owner sur cette face : `IdunBattle.Operations.EvaluateTriggerOperation$$
    CanGetEffectTrigger` a pour corps entier `mov al,1 ; ret` (cf. `dispatch/core.py`)."""
    event_id = int(EventTriggerType.TurnStart_DelayedAttacks)     # `On(0x15)`
    # `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` ecrit l'`AbilityOrEffect` de
    # l'ability declenchee dans `CurrentAbility` (`AbilityEntities+0x60`) AVANT le behaviour. Ici
    # l'ability declenchee est celle de la PHASE 2, resolue par instance -- pas une constante de
    # classe : le champ reste `None` et l'id est pose par le `TriggerAbility` du dispatch, la ou le
    # natif le pose (`TriggerTriggeredAbilityOperation`).
    TRIGGERED_ABILITY_ID: Optional[int] = None

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        inst = _pending_instance(state, int(self.owner_id))
        if inst is None:
            return False
        bonded = getattr(inst, "bonded", None)
        if bonded is None:
            # `BondedEntityFromEffect` rend une liste VIDE quand le composant de bond n'a pas d'id
            # (`SelectBondedEntityFromEffectSelector$$Select`), donc `IsTurnOf` sur un ensemble vide
            # est FAUX (`IsTurnOfUnitTrigger` fait un `all` sur les selectionnes, cf.
            # `entities/triggers.py::IsTurnOf`). Le port le DIT plutot que de retomber sur le
            # porteur -- ce serait exactement l'erreur d'attribution que la mesure du §1 refute.
            return False
        e = state.get_entity(int(bonded))
        oc = e.get_component(OwnerComponent) if e is not None else None
        if oc is None or ev.player_id is None:
            return False
        return int(oc.player) == int(ev.player_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        inst = _pending_instance(state, int(self.owner_id))
        if inst is None:
            return None
        bonded = getattr(inst, "bonded", None)
        if bonded is None:
            return None
        et = int(inst.effect_type)
        spec = PENDING_ATTACK_EFFECTS[et]
        # `Caster()` = l'attaquant (le BONDE) ; `Target()` = le porteur de l'effet. Cf.
        # `pending_attack_tree` pour la correspondance de slots.
        entities = entities_from_state(state, int(bonded), int(self.owner_id),
                                       actor_id=int(bonded))
        ectx = ExecutionContext(state=state, rng=state.rng)
        pending_attack_tree(et, spec.triggered_ability).execute(entities, ectx)
        fired = [p for n, p in ectx.emitted if n == "TriggerAbility"]
        removed = sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")
        return {"effect": et, "owner": int(self.owner_id), "attacker": int(bonded),
                "triggered": int(spec.triggered_ability), "fired": fired, "removed": removed,
                "native": spec.native}


def pending_attack_registry_entries() -> list[tuple[int, type[EffectTrigger]]]:
    """`(effect_type, classe)` a inscrire dans `EFFECT_TRIGGERS`, DERIVE de la table -- jamais ecrit
    a la main (meme discipline que `bond_removal_registry_entries`)."""
    return [(et, PendingAttackOnAttackersTurn) for et in sorted(PENDING_ATTACK_EFFECTS)]
