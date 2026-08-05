"""`AddUnitActiveAbilityModificationOperation` — mutateur ECS des MODIFICATIONS DE CONSTANTES D'ABILITY.

Chaine native (MIRROR 1:1) :

    IdunBattle.Operations.OperationProcessor$$AddUnitActiveAbilityModification(unit, key, delta)
      -> IdunBattle.Operations.AddUnitActiveAbilityModificationOperation$$Execute :
             comp = unit.GetComponent<ActiveAbilityModificationsComponent>()   ; null -> abandon
             comp.Add(key, delta)                                              (`Add` + clamp du cap)
             -> StreamHelper.<slot 5>(comp, key)   puis  Events.<...>(0x23, entityId, payload)

Le port ne materialise ni le stream ni l'event de vue (aucun observable moteur) : il porte la MUTATION
(`ActiveAbilityModificationsComponent.add`, deja portee dans `runner/components.py`) et le
get-or-create du composant (le natif l'obtient via `GetComponent`, le port le cree paresseusement —
une unite offline n'a le composant que si une source l'a alimentee).

APPELANTS NATIFS (xrefs exhaustives, build `gqfc5mff6c`) : `IdunBattle.Entities.Effects.Loki.
ListenUpMaggotsEffect$$ApplyInternal` (delta = `+GetNumberConstant`) et `$$RevertInternal` (meme appel
avec `-GetNumberConstant`) — AUCUN autre. C'est pour cela que le port ne cable cette Operation que
depuis le cycle de vie des effets (`AddEffectOperation` / retrait), et pas depuis une feuille DSL : le
natif n'expose AUCUN noeud `DSLFactory` vers cette Operation.
"""
from __future__ import annotations

from typing import Optional

from ..components import ActiveAbilityModificationsComponent
from ..state import State
from ..abilities.behaviours import entities_from_state


class AddUnitActiveAbilityModificationOperation:
    """`IdunBattle.Operations.AddUnitActiveAbilityModificationOperation$$Execute(unit, key, delta)`."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, unit_id: Optional[int], key: int, delta: int) -> Optional[int]:
        """Ajoute `delta` a la modification `key` de l'unite. Renvoie la nouvelle valeur, ou None si
        l'entite n'existe pas (mirror du `if (comp == null) return` natif, le port creant le composant
        a la demande — une unite sans modification n'a simplement pas encore de composant)."""
        if unit_id is None:
            return None
        e = state.get_entity(int(unit_id))
        if e is None:
            return None
        comp = e.get_component(ActiveAbilityModificationsComponent)
        if comp is None:
            comp = ActiveAbilityModificationsComponent()
            e.add_component(comp)
        return comp.add(key, int(delta))


def _modification_targets(state: State, holder_id: int, eff) -> list:
    """Cibles de `ApplyInternal`/`RevertInternal` = le `CreateTargetSelector` de l'effet, evalue avec
    `caster` = le PORTEUR (mirror `Self@0x148`). Selecteur absent -> le porteur lui-meme."""
    sel = eff.ability_modifications_target_selector()
    if sel is None:
        return [int(holder_id)]
    ctx = entities_from_state(state, int(holder_id))
    got = sel.evaluate(ctx)
    if got is None:
        return []
    items = [got] if isinstance(got, dict) else list(got)
    return [int(u["id"]) for u in items if isinstance(u, dict) and u.get("id") is not None]


def apply_ability_modifications(state: State, holder_id: int, eff) -> list:
    """`<Effect>.ApplyInternal` (part MODIFICATIONS D'ABILITY) : pour chaque cible du
    `CreateTargetSelector`, rejoue les `AddUnitActiveAbilityModification(target, key, +delta)` declares
    par l'effet, DANS L'ORDRE du decompile. Renvoie la liste `(target, key, delta)` reellement appliquee
    et la MEMORISE sur l'instance (`applied_ability_modifications`) — c'est elle que le revert nie, pour
    que le retrait annule EXACTEMENT ce qui avait ete pose (meme si le parent a change entre-temps).
    No-op si l'effet ne declare rien."""
    mods = eff.ability_modifications() or []
    if not mods:
        return []
    applied = []
    for tid in _modification_targets(state, holder_id, eff):
        for key, delta in mods:
            if not int(delta):
                continue
            AddUnitActiveAbilityModificationOperation.execute(state, tid, key, int(delta))
            applied.append((tid, key, int(delta)))
    eff.applied_ability_modifications = applied
    return applied


def revert_ability_modifications(state: State, eff) -> list:
    """`<Effect>.RevertInternal` : rejoue les MEMES appels en `-delta`
    (`IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect$$RevertInternal` = strictement
    `ApplyInternal` avec `-GetNumberConstant`). Consomme la liste memorisee a l'apply -> idempotent
    (un second retrait ne re-soustrait pas). No-op si l'effet n'avait rien pose."""
    applied = list(getattr(eff, "applied_ability_modifications", None) or [])
    if not applied:
        return []
    for tid, key, delta in applied:
        AddUnitActiveAbilityModificationOperation.execute(state, tid, key, -int(delta))
    eff.applied_ability_modifications = []
    return applied
