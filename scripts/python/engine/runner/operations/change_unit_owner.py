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
    if (!state.<slot 11>)  RemoveEffects(this, target);        // PORTE (#982-r4), cf. plus bas
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

⚠ **`Execute` NE FAIT RIEN D'AUTRE DES EFFETS.** Relu en entier (#982-r4, build `rnca9r7q6c`) : le
seul geste sur les effets est l'appel a `RemoveEffects` **AVANT** la lecture du nouveau
proprietaire et l'ecriture du slot d'override. Il n'y a **aucun re-`Apply`** des effets CONSERVES
sur le nouveau proprietaire -- la question restait ouverte dans l'enonce de `#982-r4`, elle est
tranchee : rien a porter de ce cote.

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

        aRetirer = new List<int>()
        foreach (effectId in unit.GetComponent<EffectsComponent>().ActiveEffectIds) {
            effet  = state.Get(effectId)
            config = EffectsDatabase.GetEffect( effet.EffectComponent.Type@+0x58 )
            if (!config.<IEffect slot 3 = get_KeepOnChangeOwner>)  aRetirer.Add(effectId)
        }
        foreach (id in aRetirer)  processor.<slot 0x11 RemoveEffect>(state.Get(id))

    Donc : a la prise de controle, le natif PURGE les effets dont le getter rend **FAUX** -- noter
    le sens du test, c'est la seule chose qui distingue une purge d'une conservation.

    ⚠ **DEUX BOUCLES, ET C'EST LOAD-BEARING** : la liste est constituee AVANT le premier retrait.
    Le port materialise donc son domaine (`list(...)`) avant d'appeler
    `remove_effect_instance`, qui mute la liste du porteur (`ActiveEffectIds.Remove`) et peut en
    retirer d'autres par cascade (`RemoveSubEffects`). Filtrer a la volee ferait sauter des entrees.

    ⚠ **LE GATE PORTE SUR LA CONFIG DU TYPE, PAS SUR L'INSTANCE.** Cote port, l'instance EST celle
    de la classe d'effet du type (materialisee par `entities/effects/factory.py`), donc
    `eff.keep_on_change_owner` est le meme predicat. Un type NON PORTE retombe sur `BaseEffect`,
    dont le defaut est `True` (= le corps `b0 01 c3` de la base) : il est CONSERVE, ce qui est
    exactement ce que fait le natif pour toute classe qui n'a pas surcharge.

    #982-r4 -- CE QUI A CHANGE, et pourquoi la note d'avant etait FAUSSE. Elle disait << le NOM du
    predicat n'est pas lisible offline >> : il l'etait, et depuis longtemps.
    `data/symbols/<build>/metadata/interface_slots.tsv` porte `IEffect 3 get_KeepOnChangeOwner`.
    Restait la VALEUR par classe concrete, elle aussi derivable OFFLINE (declaration dans le
    `global-metadata.dat`, octets du corps dans le bloc `methodPointers`) --
    `probe_982r4_keep_on_change_owner.py` : **465** classes couvertes, **0 INCONNU**, **2** a FAUX
    (`IdunBattle.Entities.Effects.TauntedEffect` et
    `IdunBattle.Entities.Effects.Loki.HolyDuel_TauntEffect`). Le correctif tient donc en un predicat
    a deux classes, pas en une purge generale -- purger << tout >> aurait retire 463 effets que le
    natif garde."""
    # DIFFERE **PORTEUR**, et la classe est MESUREE (protocole du CLAUDE.md : charger la cible seule
    # dans un process frais et regarder si le module courant y atterrit) : charger
    # `engine.runner.operations.remove_effects` charge `engine.runner.operations.change_unit_owner`
    # -- hisser cet import fermerait donc un cycle. Le symetrique existe deja et pour la meme
    # raison : `remove_effects.remove_effect_instance` differe `ResetUnitOwnerOperation`.
    from .remove_effects import remove_effect_instance

    eff_state = getattr(state, "effects", None)
    if eff_state is None:
        return None
    uid = int(unit_id)
    # 1re boucle : le DOMAINE, fige avant tout retrait (cf. l'encadre ci-dessus).
    a_retirer = [e for e in list(eff_state.by_unit.get(uid, ()) or ())
                 if not getattr(e, "consumed", False)
                 and not getattr(e, "keep_on_change_owner", True)]
    # 2e boucle : `processor.<slot 0x11>` = `RemoveEffectOperation$$Execute`, deja porte -- donc
    # avec ses `On(0x3f)`/`On(0x40)`, ses reverts de stat-mods et sa cascade d'enfants.
    for e in a_retirer:
        remove_effect_instance(state, uid, e)
    return None
