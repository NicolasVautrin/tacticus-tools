"""Feuilles DSL du canal DRAPEAU : `AddFlag` (`AddFlagBehaviour`) et `RemoveFlag`
(`RemoveFlagBehaviour`). Namespace natif `Entities.Behaviours.*`.

RE : decompile ghidra, build `rnca9r7q6c`.

Le PENDANT EXACT de `grants.py` (`AddTrait` / `AddTriggeredAbility`) sur l'autre canal d'identite :
un `UnitFlag` au lieu d'un trait. Le natif les construit par

    `IdunBattleLogic.Entities.DSLBehaviors$$AddFlag(dsl, targets, flag)`    -> `AddFlagBehaviour(targets, flag)`
    `IdunBattleLogic.Entities.DSLBehaviors$$RemoveFlag(dsl, targets, flag)` -> `RemoveFlagBehaviour(targets, flag)`

(les DEUX factories sont des corps de TROIS lignes -- `new <Behaviour>(targets, (uint)flag)` -- et le
`RemoveFlag` porte dans les tables le nom d'un ctor HOMONYME (`RemoveTriggeredAbilityBehaviour$$.ctor`)
par deduplication ICF : c'est la CLASSE ALLOUEE, lue au litteral de classe, qui tranche, jamais le nom
affiche du ctor.)

CORPS DES DEUX `$$Execute`, LUS VERBATIM
---------------------------------------
Meme squelette, un seul mot differe :

    foreach (u in (<+0x50> = targets).Select(entities)) {
        var f = u.GetComponent<UnitFlagsComponent>();
        // AddFlag    : if (!UnitFlagsComponent.Has(f, <+0x58>)) UnitFlagsComponent.Add(f, <+0x58>);
        // RemoveFlag :                                          UnitFlagsComponent.Remove(f, <+0x58>);
    }

  * `AddFlagBehaviour$$Execute` teste l'appartenance AVANT d'ajouter (le `Contains` puis le `Add`
    sont deux appels distincts au meme `OrderedSet`) -- donc IDEMPOTENT, et c'est lisible dans le
    decompile, pas suppose. `UnitFlagsComponent.add` du port l'est aussi (set), donc le mirror est
    exact sans ecrire le test.
  * `RemoveFlagBehaviour$$Execute` appelle `IdunBattle.Entities.Components.UnitFlagsComponent$$Remove`
    SANS test prealable -- retirer un drapeau absent est un no-op cote natif comme cote port.
  * Les deux ITERENT le selecteur (`GetEnumerator`/`MoveNext`/`Current` sur son retour) : c'est
    `Select`, pas `SelectFirst`. Aucun des deux ne trie.

⚠ **CE QUE LE PORT NE PEUT PAS FAIRE, ET IL LE DIT** : le natif prend le composant par
`Entity$$GetComponent<UnitFlagsComponent>()`, qui LEVE si l'entite n'en a pas -- toute entite-unite
native en porte un d'office. Cote port le composant est OPTIONNEL (les etats seedes depuis une
capture n'en ont pas toujours), donc `AddFlag` le CREE quand il manque (meme geste que
`spawn.py::_add_owner_flag_on_ability_init`, le canal IMPERATIF du meme mutateur) et `RemoveFlag`
NO-OPE quand il manque (retirer d'un ensemble absent = retirer d'un ensemble vide).

CONSOMMATEURS PORTES
--------------------
* `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WayOfTheShortBlade_AttackAbility$$CreateBehaviour`
  (#1019-r2) : `AddFlag(Caster, 0x15 = ForceRangedAttack) & UseNormalAttackIfAble(...) &
  RemoveFlag(Caster, 0x15)` -- la parenthese POSE/RETIRE autour d'un sous-cast, le patron pour
  lequel ces deux feuilles existent.
"""
from __future__ import annotations

from ....dsl.base import TargetsSelector, _units_of
from ....dsl.effects import AbilityBehaviour, OperationResult
from ....entities.unit_flag import UnitFlag
from ...components import UnitFlagsComponent


def _flag_name(flag) -> str:
    """Nom de MEMBRE du drapeau pour l'event emis (`UnitFlag` est un `IntEnum` re-derivable du
    build). Un ordinal hors enum sort en decimal plutot que de lever : ces feuilles n'ont pas a
    arbitrer la fraicheur du mirror, `probe_313` le fait."""
    try:
        return UnitFlag(int(flag)).name
    except ValueError:
        return str(int(flag))


class AddFlag(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$AddFlag(dsl, targets, flag)` ->
    `IdunBattle.Entities.Behaviours.AddFlagBehaviour$$Execute` : POSE `flag` sur chaque unite du
    selecteur. Idempotent (`OrderedSet` natif ; `set` cote port).

    Emet `'AddFlag'` par unite, avec `added` = le booleen du `Add` natif (`False` = drapeau DEJA
    porte, ce que le natif observe par son `Contains` prealable). Effet PUR (stop=False)."""
    __slots__ = ("units_sel", "flag")

    def __init__(self, units_sel: TargetsSelector, flag):
        self.units_sel = units_sel
        self.flag = int(flag)

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        for u in _units_of(self.units_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None:
                continue
            e = state.get_entity(int(uid))
            if e is None:
                continue
            c = e.get_component(UnitFlagsComponent)
            if c is None:
                # Le natif ne rencontre jamais ce cas (`GetComponent` leve) ; cote port le composant
                # est optionnel -> on le cree, comme le canal imperatif du meme mutateur
                # (`operations/spawn.py::_add_owner_flag_on_ability_init`).
                c = UnitFlagsComponent()
                e.add_component(c)
            added = not c.has(self.flag)
            c.add(self.flag)
            ectx.emit("AddFlag", unit=int(uid), flag=_flag_name(self.flag), added=bool(added))
        return OperationResult.ok()


class RemoveFlag(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$RemoveFlag(dsl, targets, flag)` ->
    `IdunBattle.Entities.Behaviours.RemoveFlagBehaviour$$Execute` : RETIRE `flag` de chaque unite du
    selecteur, SANS test prealable (le natif appelle `UnitFlagsComponent$$Remove` directement).

    Emet `'RemoveFlag'` par unite, avec `removed` = le drapeau etait-il present. Effet PUR."""
    __slots__ = ("units_sel", "flag")

    def __init__(self, units_sel: TargetsSelector, flag):
        self.units_sel = units_sel
        self.flag = int(flag)

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        for u in _units_of(self.units_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None:
                continue
            e = state.get_entity(int(uid))
            if e is None:
                continue
            c = e.get_component(UnitFlagsComponent)
            if c is None:
                continue                      # ensemble absent == ensemble vide : retrait no-op
            removed = c.has(self.flag)
            c.remove(self.flag)
            ectx.emit("RemoveFlag", unit=int(uid), flag=_flag_name(self.flag),
                      removed=bool(removed))
        return OperationResult.ok()


__all__ = ["AddFlag", "RemoveFlag"]
