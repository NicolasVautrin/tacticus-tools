"""Feuilles DSL de la famille PERSISTENT-DATA **LISTE** : `AddToPersistentDataList` et
`ClearAllPersistentData` (#354).

Le sac lui-meme est deja porte (`runner/components.py::PersistentDataComponent`, pose par
`LetTheGalaxyBurn` pour un FLAG scalaire) ; ce module ajoute la variante LISTE, que le natif range
sous la MEME cle et manipule par trois primitives :

| noeud `DSLBehaviors` / `DSLTriggers` / `DSLSelectors` | classe native |
|---|---|
| `IdunBattleLogic.Entities.DSLBehaviors$$AddToPersistentDataList`   | `Idun.Source.IdunBattle.Logic.Entities.Triggers.AddToPersistentDataListBehaviour$$Execute` |
| `IdunBattleLogic.Entities.DSLBehaviors$$ClearAllPersistentData`    | `IdunBattle.Entities.Behaviours.ClearPersistentDataBehaviour$$ExecuteClearAll` |
| `IdunBattleLogic.Entities.DSLTriggers$$IsInPersistentDataList`     | `Idun.Source.IdunBattle.Logic.Entities.Triggers.IsInPersistentDataListTrigger$$ShouldTrigger` (porte dans `entities/triggers.py`) |
| `IdunBattleLogic.Entities.DSLSelectors$$GetPersistentDataListAsEntities` | `IdunBattle.Entities.Selectors.EntitiesFromPersistentDataListSelector$$Select` (RESIDU, cf. plus bas) |

APPELANTS NATIFS (xrefs exhaustives, build `rnca9r7q6c`) : `MyWillBeDoneOverlordAbility` (porte, #354),
`PrimarchOfTheFirstLegionAbility` + `PrimarchOfTheFirstLegion_EndTurnAbility`,
`NoHidingFromTheWatchers_EndPhaseAbility`, `InstrumentsOfVengeance_AttackAbility`,
`RefusalToBeOutdone_ResetStatsAbility` -- aucune des quatre dernieres n'est portee : ces primitives
sont donc ecrites POUR le premier consommateur, pas specialisees pour lui.

RESIDU NOMME -- `GetPersistentDataListAsEntities` n'est PAS porte en SELECTEUR. Son unique usage
COMBAT porte est le gate `AmountIsGreaterThanZero(GetPersistentDataListAsEntities)` de
`MyWillBeDoneOverlordAbility$$CreateTrigger`, que le port collapse imperativement en
« la liste persistante de l'owner est non vide » (`my_will_be_done_overlord.py::_used_ids`). Le
selecteur natif fait DAVANTAGE -- il resout chaque id en ENTITE et jette celles qui ne passent pas
`MatchesUnitSelectionType(3)` --, ce qui ne change le VERDICT du gate que si toutes les entites
listees sont devenues non-selectionnables (mortes) dans le meme tour ; aucun montage porte ne
l'atteint. Le jour ou un consommateur a besoin des ENTITES, le selecteur entre ici.
"""
from __future__ import annotations

from ....dsl.base import TargetsSelector, _units_of
from ....dsl.effects import AbilityBehaviour, OperationResult


def _component(state, unit_id):
    """Get-or-create le `PersistentDataComponent` du porteur (mirror : le natif l'a d'office --
    `ClearPersistentDataBehaviour$$GetPersistentDataComponent` / le `GetComponent` de
    `AddToPersistentDataListBehaviour$$Execute`). None si l'entite n'existe pas."""
    from ...components import PersistentDataComponent
    e = state.get_entity(int(unit_id)) if unit_id is not None else None
    if e is None:
        return None
    c = e.get_component(PersistentDataComponent)
    if c is None:
        c = PersistentDataComponent()
        e.add_component(c)
    return c


class AddToPersistentDataList(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$AddToPersistentDataList(abilityOrEffect, unit,
    dataKeyFormula, valueFormula)` -> `Idun.Source.IdunBattle.Logic.Entities.Triggers.
    AddToPersistentDataListBehaviour$$Execute` — MIRROR du decompile :

        entity = <selecteur @+0x68>.SelectSingle(entities)      # null -> return (no-op)
        key    = <formule @+0x78 (repli @+0x70)>.Calculate(entities)
        value  = <formule @+0x80>.Calculate(entities)
        comp   = entity.GetComponent<PersistentDataComponent>()
        list   = comp.TryGetPersistDataList(GetPersistentDataId(abilityOrEffect@+0x50), key)
                 ?? new List<T>()
        list.Add(value)                                          # append, AUCUNE deduplication
        comp.PersistDataList(id, key, list)

    ⚠ `List.Add` INCONDITIONNEL : le natif ne deduplique pas. C'est le PREDICAT
    `IsInPersistentDataList` (cote trigger) qui empeche le doublon en amont ; la feuille, elle,
    empile. Le port empile pareil -- dedupliquer ici serait une divergence silencieuse.

    Effet PUR (`stop=False`). Emet 'AddToPersistentDataList'."""
    __slots__ = ("ability_or_effect", "unit_sel", "data_key", "value")

    def __init__(self, ability_or_effect: int, unit_sel: TargetsSelector, data_key, value):
        self.ability_or_effect = int(ability_or_effect)
        self.unit_sel, self.data_key, self.value = unit_sel, data_key, value

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        key = self.data_key.evaluate(entities) if hasattr(self.data_key, "evaluate") \
            else self.data_key
        val = self.value.evaluate(entities) if hasattr(self.value, "evaluate") else self.value
        if val is None:                            # `valueFormula` sans sujet -> rien a ranger
            return OperationResult.ok()
        ck = (self.ability_or_effect, key)
        added: list = []
        for u in _units_of(self.unit_sel, entities):
            c = _component(state, (u or {}).get("id"))
            if c is None:
                continue
            lst = list(c.try_get_persist_data_list(ck) or ())
            lst.append(val)                        # `List.Add` -- pas de dedup (cf. docstring)
            c.persist_data_list(ck, lst)
            added.append({"unit": int(u["id"]), "value": val, "size": len(lst)})
        ectx.emit("AddToPersistentDataList", ability=self.ability_or_effect, key=key, added=added)
        return OperationResult.ok()


class AddPersistentData(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$AddPersistentData(abilityOrEffect, unit, dataKey,
    valueFormula)` -> `IdunBattle.Entities.Triggers.AddPersistentDataBehavior$$Execute` -- la
    variante SCALAIRE de la famille (l'autre, LISTE, est `AddToPersistentDataList` ci-dessus).

        entity = <selecteur unit>.SelectSingle(entities)          # null -> no-op
        key    = <formule dataKey>.Calculate(entities)
        value  = <formule valeur>.Calculate(entities)
        entity.GetComponent<PersistentDataComponent>()
              .PersistData(GetPersistentDataId(abilityOrEffect), key, value)

    `PersistData` **ECRASE** (`Dictionary[key] = value`), il n'empile pas : c'est toute la
    difference avec `AddToPersistentDataList`, dont le `List.Add` est inconditionnel. Un second
    appel dans le meme tour ne fait donc rien de plus.

    ⚠ DEUX SURCHARGES natives de ce noeud (`180e9f360` / `180e9f400`) : elles ne different que par
    la fabrication de la `dataKey` -- la seconde ENVELOPPE une chaine litterale dans une formule
    constante avant de construire le MEME `AddPersistentDataBehavior`. Le port n'en porte qu'UNE :
    `data_key` accepte indifferemment un noeud (`.evaluate`) ou un scalaire, ce qui couvre les deux.

    CONSOMMATEUR PORTE : `HaywireMineAbility$$CreateBehaviour`, ou la valeur est la formule
    partagee `DSLFormulas+0x20` = `Direct(1)` (le `.ctor` de `DSLFormulas` alloue `+0x18`=0,
    `+0x20`=1, `+0x28`=2, `+0x30`=100, `+0x38`=-1). Effet PUR (`stop=False`).
    Emet 'AddPersistentData'."""
    __slots__ = ("ability_or_effect", "unit_sel", "data_key", "value")

    def __init__(self, ability_or_effect: int, unit_sel: TargetsSelector, data_key, value):
        self.ability_or_effect = int(ability_or_effect)
        self.unit_sel, self.data_key, self.value = unit_sel, data_key, value

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        key = self.data_key.evaluate(entities) if hasattr(self.data_key, "evaluate") \
            else self.data_key
        val = self.value.evaluate(entities) if hasattr(self.value, "evaluate") else self.value
        if val is None:
            return OperationResult.ok()
        ck = (self.ability_or_effect, key)
        posees: list = []
        for u in _units_of(self.unit_sel, entities):
            c = _component(state, (u or {}).get("id"))
            if c is None:
                continue
            c.persist_data(ck, val)                  # `PersistData` ECRASE (pas d'empilement)
            posees.append({"unit": int(u["id"]), "value": val})
        ectx.emit("AddPersistentData", ability=self.ability_or_effect, key=key, posees=posees)
        return OperationResult.ok()


class ClearPersistentData(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$ClearPersistentData(abilityOrEffect, unit, dataKey)`
    -> `IdunBattle.Entities.Behaviours.ClearPersistentDataBehaviour$$Execute` : retire UNE cle
    (`Dictionary.Remove`), a la difference de `ClearAllPersistentData` qui emporte toutes les
    dataKeys de l'ability.

    ⚠ QUATRE surcharges natives du noeud (`180ea2080` / `180ea21a0` / `180ea22a0` / `180ea2330`) --
    meme motif que `AddPersistentData` : elles se distinguent par le TYPE de l'`abilityOrEffect`
    (int converti par `op_Implicit`, ou struct deja formee) et par l'enveloppement de la `dataKey`.
    Toutes construisent le MEME `ClearPersistentDataBehaviour` ; le port n'en porte qu'un.

    CONSOMMATEUR PORTE : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HaywireMine_ResetAbility
    $$CreateBehaviour` -- `On(0x28 = UnitFinishedTurn) & OwnerIsActor` -> `ClearPersistentData`. Il
    partage l'`AbilityOrEffect` (donc l'id de sac) ET la `dataKey` avec l'`AddPersistentData` de
    `HaywireMineAbility` : c'est ce qui RE-ARME la pose de fin de tour, et la mesure live le
    confirme (une mine par tour, cf. `docs/rl/case-462-...-r5-pose-mine-haywire.md`).

    Effet PUR (`stop=False`). Emet 'ClearPersistentData'."""
    __slots__ = ("ability_or_effect", "unit_sel", "data_key")

    def __init__(self, ability_or_effect: int, unit_sel: TargetsSelector, data_key):
        self.ability_or_effect = int(ability_or_effect)
        self.unit_sel, self.data_key = unit_sel, data_key

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        key = self.data_key.evaluate(entities) if hasattr(self.data_key, "evaluate") \
            else self.data_key
        ck = (self.ability_or_effect, key)
        vides: list = []
        for u in _units_of(self.unit_sel, entities):
            c = _component(state, (u or {}).get("id"))
            if c is None:
                continue
            avait = c.try_get_persist_data(ck) is not None
            c.clear_persistent_data(ck)              # `Dictionary.Remove` (no-op si absente)
            vides.append({"unit": int(u["id"]), "avait": avait})
        ectx.emit("ClearPersistentData", ability=self.ability_or_effect, key=key, vides=vides)
        return OperationResult.ok()


class ClearAllPersistentData(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$ClearAllPersistentData(abilityOrEffect, unit)` ->
    `IdunBattle.Entities.Behaviours.ClearPersistentDataBehaviour$$ExecuteClearAll` — MIRROR :

        comp = GetPersistentDataComponent(unit)                 # null -> return 0 (no-op)
        comp.ClearAllPersistentData(GetPersistentDataId(abilityOrEffect@+0x50))

    L'overload de composant retenu est celui A UN ARGUMENT
    (`PersistentDataComponent$$ClearAllPersistentData(this, abilityId)` = `Dictionary.Remove(
    abilityId)`) : il emporte TOUTES les dataKeys de CETTE ability, et rien des autres. Le port
    aplatit le dict natif a deux niveaux en cle composite -> il balaie les cles de premier membre
    `abilityOrEffect` (cf. `PersistentDataComponent.clear_all_persistent_data`).

    Effet PUR (`stop=False`). Emet 'ClearAllPersistentData'."""
    __slots__ = ("ability_or_effect", "unit_sel")

    def __init__(self, ability_or_effect: int, unit_sel: TargetsSelector):
        self.ability_or_effect = int(ability_or_effect)
        self.unit_sel = unit_sel

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        cleared: list = []
        for u in _units_of(self.unit_sel, entities):
            c = _component(state, (u or {}).get("id"))
            if c is None:
                continue
            before = sum(1 for k in c.data
                         if isinstance(k, tuple) and k and k[0] == self.ability_or_effect)
            c.clear_all_persistent_data(self.ability_or_effect)
            cleared.append({"unit": int(u["id"]), "keys": before})
        ectx.emit("ClearAllPersistentData", ability=self.ability_or_effect, cleared=cleared)
        return OperationResult.ok()
