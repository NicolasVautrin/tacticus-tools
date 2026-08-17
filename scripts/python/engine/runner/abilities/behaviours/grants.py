"""Feuilles DSL d'OCTROI a une unite : `AddTrait` (`AddTraitBehaviour`) et `AddTriggeredAbility`
(`AddTriggeredAbilityBehaviour`). Namespace natif `Entities.Behaviours.*`.

Les deux sont des mutateurs d'IDENTITE (ce que l'unite EST / ce qu'elle SAIT faire), par opposition
aux effets (`effects.py`, entites-effet a duree) et aux stats (`stats.py`). Le natif les construit
par `IdunBattleLogic.Entities.DSLBehaviors$$AddTrait` / `$$AddTriggeredAbility` ; leur premier
consommateur porte est le volet ON-APPEARANCE de `DutyEternalAbility$$ExecuteBehaviour`."""
from __future__ import annotations

from typing import Optional

from ....dsl.base import TargetsSelector, _units_of
from ....dsl.effects import AbilityBehaviour, OperationResult
from ....entities.traits.unit_trait import UnitTrait, trait_name
from ...components import StatsComponent, TriggeredAbilityComponent
# Forme B (module + acces attributaire, cf. CLAUDE.md) : foyer UNIQUE d'`AddTraitOperation$$Execute`,
# partage avec le canal `applied_traits` du cycle de vie des effets. Import de TETE (aucun cycle
# mesure : `operations.traits` ne tire que `..components`, `..state` et le mirror d'enum).
from ...operations import traits as _tr


class AddTrait(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$AddTrait(factory, sel, traitId, flag)` ->
    `IdunBattle.Entities.Behaviours.AddTraitBehaviour` : ACCORDE le trait `trait_id` a chaque unite
    du selecteur.

    Cote natif le trait atterrit dans la collection « traits ACCORDES en bataille » du
    `BaseUnitComponent` (`+0x48`), interrogee par `IdunBattle.Entities.Components.
    BaseUnitComponent$$HasTrait` au meme titre que les traits de BASE (`+0x40`). Cote port, le set
    de traits d'une unite est `StatsComponent.ctx.traits` (liste de NOMS gameconfig, cf.
    `entities/traits/unit_trait.py`) : on y ajoute le NOM du trait, ce qui le rend visible de tous
    les lecteurs (`has_trait`, `ctx.has_trait` du DSL, `_unit_traits` du ciblage) d'un seul coup.
    Idempotent (le natif ajoute a un set).

    CALL-SITE PORTE : `IdunBattleLogic.Entities.Abilities.Active.Loki.DutyEternalAbility$$
    ExecuteBehaviour` -> `AddTrait(ActiveTarget@0x180, 0x418)` = `UnitTrait.Stationary` (1048) sur
    le summon fraichement pose -- c'est le « **stationary** unit » de l'i2, et le gate
    `HasTrait(0x418)` de `IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFor` (qui rend
    un ensemble VIDE de positions de mouvement) en est le consommateur natif.

    Emet 'AddTrait' par unite (`added` = le booleen du `coll.Add` natif : `False` = trait DEJA
    porte, donc le natif s'arrete la). Effet PUR (stop=False).

    ⚠ DELEGUE a `operations/traits.py::AddTraitOperation` -- le mirror de
    `IdunBattle.Operations.AddTraitOperation$$Execute`, que le natif atteint AUSSI par une autre
    voie : le `<Effect>.ApplyInternal` d'un effet a trait, qui appelle l'Operation DIRECTEMENT par
    le slot `0x26` de l'`IOperationProcessor` sans passer par aucun noeud DSL
    (`WarHowl_ExtraDamage_UnstoppableEffect`). Une seconde ecriture de `ctx.traits` ici aurait ete
    un fork de port entre les deux voies."""
    __slots__ = ("units_sel", "trait_id")

    def __init__(self, units_sel: TargetsSelector, trait_id):
        self.units_sel = units_sel
        self.trait_id = trait_id

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        name = trait_name(self.trait_id)         # louder-on-bug : un id hors enum LEVE
        for u in _units_of(self.units_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None:
                continue
            # `isTemporary` : la feuille `AddTraitBehaviour` porte le flag `param_4` du
            # `IdunBattleLogic.Entities.DSLBehaviors$$AddTrait`, que le seul call-site porte (`DutyEternalAbility`) laisse a
            # sa valeur PERMANENTE. Cote port les deux collections natives sont fondues en un
            # ensemble unique de NOMS (cf. `operations/traits.py`), donc le flag n'a pas
            # d'observable distinct -- on garde le comportement HISTORIQUE de cette feuille.
            added = _tr.AddTraitOperation.execute(state, int(uid), self.trait_id,
                                                  is_temporary=False)
            ectx.emit("AddTrait", unit=int(uid), trait=name, added=bool(added))
        return OperationResult.ok()


class AddTriggeredAbility(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$AddTriggeredAbility(factory, sel, abilityId, levelInfo)`
    -> `IdunBattle.Entities.Behaviours.AddTriggeredAbilityBehaviour` -> l'operation
    `IdunBattle.Operations.AddTriggeredAbilityOperation$$Execute`, qui enregistre l'ability dans le
    `TriggeredAbilityComponent` de l'unite (`TryAdd` sur la `KeyedCollection` @+0x18).

    CALL-SITE PORTE -- `DutyEternalAbility$$ExecuteBehaviour`, branche CONDITIONNELLE :

        if (caster.GetComponent<TriggeredAbilityComponent>().<coll @+0x18>.Count > 0) {
            a = Enumerable.First(coll);
            onAppearance &= AddTriggeredAbility(ActiveTarget@0x180, a.Id, {a@0x20, a@0x28});
        }

    = « la PREMIERE triggered ability du Galatian MoW suit le dreadnought sur le terrain ». Dans le
    kit courant, le seul candidat est la MYTHIC `WisdomOfTheAncients` (aura -20 % de degats aux
    Mythic amis adjacents a Galatian -- une aura qui n'a de sens QUE si Galatian est sur le
    plateau, donc apres ce cast). Un `ultraDreadnought` de rang courant n'en a pas : la collection
    est vide et le natif comme le port ne transferent rien. Branche « non vide » NON CONFRONTEE
    LIVE (residu nomme, cf. docs/rl/case-91-duty-eternal.md §7).

    Le natif tranche la condition A LA CONSTRUCTION de l'arbre (`if (Count > 0)` precede le `&`),
    pas a l'execution : le port fait de meme -- l'appelant lit `first_triggered_ability_of(caster)`
    et n'assemble ce noeud QUE s'il obtient une ability. `ability_id = None` -> no-op de securite.

    Emet 'AddTriggeredAbility' par unite. Effet PUR (stop=False)."""
    __slots__ = ("units_sel", "ability_id")

    def __init__(self, units_sel: TargetsSelector, ability_id):
        self.units_sel = units_sel
        self.ability_id = ability_id

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        aid = self.ability_id
        if aid is None:
            return OperationResult.ok()
        for u in _units_of(self.units_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None:
                continue
            e = state.get_entity(int(uid))
            if e is None:
                continue
            tc = e.get_component(TriggeredAbilityComponent)
            if tc is None:
                tc = e.add_component(TriggeredAbilityComponent())
            tc.try_add(aid)                      # `TriggeredAbilityComponent$$TryAdd` (idempotent)
            ectx.emit("AddTriggeredAbility", unit=int(uid), ability=aid)
        return OperationResult.ok()


def first_triggered_ability_of(state, unit_id: Optional[int]):
    """`Enumerable.First(caster.GetComponent<TriggeredAbilityComponent>().<coll @+0x18>)` -- la
    PREMIERE entree du registre de triggered abilities de `unit_id`, ou `None` si l'unite n'en a
    aucune (le natif teste `Count > 0` AVANT de prendre le `First`, donc l'absence est une branche
    normale, pas une degradation). Cote port la cle du dict EST l'ability-type ; `dict` conserve
    l'ordre d'insertion, comme la `KeyedCollection` native."""
    e = state.get_entity(int(unit_id)) if (state is not None and unit_id is not None) else None
    tc = e.get_component(TriggeredAbilityComponent) if e is not None else None
    if tc is None or not tc.entries:
        return None
    return next(iter(tc.entries))


__all__ = ["AddTrait", "AddTriggeredAbility", "first_triggered_ability_of", "UnitTrait"]
