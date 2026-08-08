"""OWNER-SWAP -- `IdunBattle.Operations.ChangeUnitOwnerOperation$$Execute` et son inverse
`IdunBattle.Operations.ResetUnitOwnerOperation$$Execute` (#590).

Couche IMPERATIVE (mutateur ECS), appelee par la part `ApplyInternal`/`RevertInternal` d'un effet --
JAMAIS par un noeud DSL directement : la frontiere est le `.Execute` de la feuille, et ici le natif
n'expose ces deux operations que par les slots `IOperationProcessor 127 ChangeUnitOwner/2` et
`128 ResetUnitOwner/1` (`data/symbols/<build>/metadata/ioperationprocessor_slots.tsv`), invoques
depuis `IdunBattle.Entities.Effects.Loki.AttemptedPossession_PossessedEffect$$ApplyInternal` /
`$$RevertInternal`.

UNIQUE consommateur porte a ce jour : l'effet `1209 AttemptedPossession_Possessed`.

STRUCTURE NATIVE LUE (build `rnca9r7q6c`), `ChangeUnitOwnerOperation$$Execute(target, referenceUnit)` :

    if (UnitExtensions.IsOwnerOverridden(target)) {            // deja possede
        Logger.Log("... already overridden ..."); return;      // NO-OP, aucune mutation
    }
    if (!state.<slot 11>)  RemoveEffects(this, target);        // cf. `_remove_effects_on_owner_change`
    newOwnerId = OwnerComponent(referenceUnit).CurrentPlayerEntityId
    oc         = OwnerComponent(target)
    oldOwnerId = oc.<+0x10 OwnerPlayerEntityId>
    oc.<+0x14 OverriddenPlayerEntityId> = newOwnerId           // <- LE SWAP
    state.Get(newOwnerId).PlayerComponent.<+0x48>.Add(targetId)
    state.Get(oldOwnerId).PlayerComponent.<+0x40>.Add(targetId)
    processor.<slot 0x7d>(...)                                 // invalidation de caches
    if (state.<slot 11>) return;                               // mode simulation : pas d'event
    processor.<slot 0x2f>({5, 0, 0})
    Events.Add(0x27, targetId, { 0x77: newOwnerId })

et `ResetUnitOwnerOperation$$Execute(target)`, symetrique terme a terme :

    if (!UnitExtensions.IsOwnerOverridden(target)) {           // rien a defaire
        Logger.Log("... not overridden ..."); return;          // NO-OP
    }
    oc = OwnerComponent(target)
    overriddenId = oc.CurrentPlayerEntityId                    // = le +0x14
    oc.<+0x14> = 0                                             // <- LE REVERT
    state.Get(overriddenId).PlayerComponent.<+0x48>.Remove(targetId)
    state.Get(oc.<+0x10>).PlayerComponent.<+0x40>.Remove(targetId)
    ... memes events

⚠ **LES DEUX GATES D'IDEMPOTENCE SONT LOAD-BEARING, ET ILS SONT ASYMETRIQUES.** `ChangeUnitOwner`
refuse une unite DEJA possedee (une 2e possession ne re-swappe pas, et surtout ne PERD pas l'owner
d'origine) ; `ResetUnitOwner` refuse une unite qui ne l'est PAS (un retrait en double ne fabrique
pas un owner). Sans eux, le double-cast de `1101` sur une cible deja possedee -- regime atteignable,
l'arbre pose puis retire dans le MEME cast mais le trigger `UnitAdded` de l'effet repose sur les
enfants -- laisserait une unite definitivement retournee.

⚠ **`state.<slot 11>` = le mode SIMULATION** (`IMatchState`, meme slot que celui lu par les autres
operations pour sauter leurs events). Le port n'a pas de mode simulation cote runner : la branche
`RemoveEffects` est donc TOUJOURS prise et les events ne sont pas emis (le port n'a pas ce bus).
ECART NOMME, sans observable ici.

⚠ **`PlayerComponent+0x40` / `+0x48` NE SONT PAS PORTES** : ce sont deux listes d'ids sur l'entite
PLAYER (celle du nouveau proprietaire recoit l'unite en `+0x48`, celle de l'ancien la recoit en
`+0x40` -- deux registres << gagnees >> / << cedees >>, lus par le decompte de fin de bataille et le
rendu). Le port n'a pas d'entite-player ; l'appartenance y est portee par `OwnerComponent.team`,
que ce module bascule. Residu `#590-r1`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ..components import OwnerComponent

if TYPE_CHECKING:
    from ..state import State


def is_owner_overridden(state: "State", unit_id: Optional[int]) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsOwnerOverridden(unit)` -- mirror : l'unite porte-t-elle
    un override de proprietaire actif (`OwnerComponent+0x14 != 0`) ?

    Cote port, le slot `+0x14` est materialise par `OwnerComponent.overridden_from` (le couple
    d'ORIGINE ; cf. la docstring du composant pour l'inversion assumee de qui porte le courant).
    Entite absente / sans `OwnerComponent` -> `False` : le natif deref le composant et n'a pas de
    branche pour son absence, donc toute reponse est une convention -- `False` est celle qui
    n'INVENTE pas une possession."""
    if unit_id is None:
        return False
    ent = state.get_entity(int(unit_id))
    oc = ent.get_component(OwnerComponent) if ent is not None else None
    return oc is not None and oc.overridden_from is not None


class ChangeUnitOwnerOperation:
    """`IdunBattle.Operations.ChangeUnitOwnerOperation$$Execute(target, referenceUnit)`."""
    __slots__ = ()

    @staticmethod
    def execute(state: "State", target_id: Optional[int],
                reference_unit_id: Optional[int]) -> bool:
        """Bascule `target` sous le proprietaire de `referenceUnit`. Rend `True` si le swap a eu
        lieu, `False` si un gate l'a refuse (deja possedee, entite/composant absent).

        Ordre du decompile : gate `IsOwnerOverridden` -> `RemoveEffects` -> lecture du nouveau
        proprietaire -> ecriture du slot d'override."""
        if target_id is None or reference_unit_id is None:
            return False
        tent = state.get_entity(int(target_id))
        rent = state.get_entity(int(reference_unit_id))
        toc = tent.get_component(OwnerComponent) if tent is not None else None
        roc = rent.get_component(OwnerComponent) if rent is not None else None
        if toc is None or roc is None:
            return False
        if toc.overridden_from is not None:
            return False                       # gate `IsOwnerOverridden` -> log + return
        _remove_effects_on_owner_change(state, int(target_id))
        toc.overridden_from = (toc.team, toc.player)     # `+0x10` conserve l'ORIGINE
        toc.team = roc.team                              # `+0x14 = referenceUnit.CurrentPlayer...`
        toc.player = roc.player
        return True


class ResetUnitOwnerOperation:
    """`IdunBattle.Operations.ResetUnitOwnerOperation$$Execute(target)`."""
    __slots__ = ()

    @staticmethod
    def execute(state: "State", target_id: Optional[int]) -> bool:
        """Rend `target` a son proprietaire d'origine. `True` si le revert a eu lieu, `False` si le
        gate `!IsOwnerOverridden` l'a refuse."""
        if target_id is None:
            return False
        ent = state.get_entity(int(target_id))
        oc = ent.get_component(OwnerComponent) if ent is not None else None
        if oc is None or oc.overridden_from is None:
            return False                       # gate `!IsOwnerOverridden` -> log + return
        oc.team, oc.player = oc.overridden_from
        oc.overridden_from = None                        # `+0x14 = 0`
        return True


def _remove_effects_on_owner_change(state: "State", unit_id: int) -> None:
    """`IdunBattle.Operations.ChangeUnitOwnerOperation$$RemoveEffects(unit)` -- MIRROR, terme a terme :

        garder = new List<int>()
        foreach (effectId in unit.GetComponent<EffectsComponent>().ActiveEffectIds) {
            effet  = state.Get(effectId)
            config = EffectsDatabase.GetEffect( effet.EffectComponent.Type@+0x58 )
            if (!config.<slot 3>)  garder.Add(effectId)     // <- NOTE : le sens du test
        }
        foreach (id in garder)  processor.RemoveEffect(state.Get(id))

    Donc : a la prise de controle, le natif PURGE les effets portes par l'unite dont la config
    repond FAUX au slot 3 de l'interface d'effet -- pratiquement, tout ce qui ne survit pas a un
    changement de camp (les taunts, les marquages de ciblage, les buffs lies a l'ancien
    proprietaire).

    ⚠ **CE FILTRE N'EST PAS PORTE, ET LE PORT NE PURGE DONC RIEN.** Le discriminant est le slot 3
    de l'interface de CONFIGURATION d'effet (`DAT_18334e8f0`), qui n'est dans aucune des deux
    tables de slots versionnees (`interface_slots.tsv` couvre `IEffect`, pas cette interface-la) :
    le NOM du predicat n'est pas lisible offline, et le port ne devine pas quels effets tombent.
    Purger << tout >> serait strictement pire (on retirerait des effets que le natif garde), ne
    rien purger est la degradation CONSERVATRICE.

    Portee reelle de l'ecart pour `1101`, mesuree sur la duree de vie de la possession : l'arbre
    pose et retire l'effet DANS LE MEME CAST, donc les effets non purges vivent une fenetre qui ne
    contient qu'une action IA. Residu `#590-r2` (`BLOCAGE: capteur` -- trancher le predicat demande
    d'enumerer les methodes d'une interface de config a l'execution)."""
    return None
