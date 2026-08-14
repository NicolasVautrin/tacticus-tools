"""#1015-r1 -- les TROIS feuilles DSL du `CreateBehaviour` du trait `InstinctiveBehaviour` :
`AddForcedAttackTarget`, `RemoveForcedAttackTarget`, `RefreshEffects`.

Frontiere DSL/imperatif (doctrine #149) : l'artefact natif est un `CreateBehaviour`
(`IdunBattleLogic.Entities.Abilities.Active.Loki.InstinctiveBehaviour_UpdateTargetAbility$$
CreateBehaviour`), donc la STRUCTURE est un arbre DSL ; les feuilles, elles, MUTENT le
`ForcedAttackTargetsComponent`, exactement comme `AddEffect` mute l'`EffectsState`.

LE STORE EST DEJA PORTE, ET IL AVAIT UN ECRIVAIN MANQUANT. `runner/components.py::
ForcedAttackTargetsComponent` recense QUATRE ecrivains natifs ; les voies 1/2 (`TauntedEffect$$
ApplyInternal` / `$$RevertInternal`) etaient portees, les voies 3/4 ne l'etaient pas :

    3. `IdunBattle.Entities.Behaviours.AddForcedAttackTargetBehaviour$$Execute` -- `Add` INCREMENTAL,
       dont l'UNIQUE constructeur est `InstinctiveBehaviour_UpdateTargetAbility$$CreateBehaviour` ;
    4. `IdunBattle.Entities.Behaviours.RemoveForcedAttackTargetBehaviour$$Execute` -- `Remove`.

C'est litteralement l'ecart que la docstring du composant nommait (« non porte », « aucun ecrivain
porte »). Il est ferme ici.
"""
from __future__ import annotations

from ....dsl.base import TargetsSelector, resolve_unit
from ....dsl.effects import AbilityBehaviour, OperationResult
from ...components import ForcedAttackTargetsComponent


def _targets_of(sel: TargetsSelector, entities) -> list:
    """`<behaviour+0x58>.Select(entities, 3)` -- NORMALISATION du selecteur, mirror du contrat natif
    (`IEnumerable` d'entites) : un selecteur MONO-ENTITE rend un DICT cote port, et l'iterer
    donnerait ses CLES. Meme piege et meme parade que `entities/behaviours.py::Foreach`."""
    raw = sel.evaluate(entities) if sel is not None else None
    if raw is None:
        return []
    return [raw] if isinstance(raw, dict) else list(raw)


def _component(state, unit_id: int) -> "ForcedAttackTargetsComponent | None":
    """`attacker.GetComponent<ForcedAttackTargetsComponent>()`, get-or-create.

    Le natif lit le composant sur l'entite ; cote port il n'existe que la ou une ecriture a eu lieu
    (`snapshot._seed_forced_attack_targets` ne le pose que pour un taunt capte). La voie `Add` doit
    donc pouvoir le CREER, sans quoi le premier `AddForcedAttackTarget` d'une bataille serait un
    no-op silencieux -- exactement le mode de panne que ce module ferme."""
    e = state.get_entity(int(unit_id)) if state is not None else None
    if e is None:
        return None
    c = e.get_component(ForcedAttackTargetsComponent)
    if c is None:
        c = e.add_component(ForcedAttackTargetsComponent())
    return c


class AddForcedAttackTarget(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$AddForcedAttackTarget(attacker, target)` ->
    `IdunBattle.Entities.Behaviours.AddForcedAttackTargetBehaviour$$Execute`, MIRROR du decompile :

        attacker = <entities+0x50>.SelectSingle(entities, 3)
        if (attacker == null)                                  return this        # rien
        comp = attacker.GetComponent<ForcedAttackTargetsComponent>()
        foreach (t in <entities+0x58>.Select(entities, 3))
            if (!comp.<+0x50>.Contains(t.Id)) comp.<+0x50>.Add(t.Id)

    L'ajout est **IDEMPOTENT** (`Contains` avant `Add`, LU) et **INCREMENTAL** : il ne remplace
    JAMAIS la liste, contrairement a `TauntedEffect$$ApplyInternal` (voie 1). `ForcedAttackTargets
    Component.add` porte deja exactement ce contrat.

    PUR (`stop=False`) : `Execute` rend son `this` zero-initialise, il ne peut pas court-circuiter
    une chaine `&` (meme regime qu'`AddEffectBehaviour`, cf. `entities/behaviours.py::Seq`)."""
    __slots__ = ("attacker_sel", "target_sel")

    def __init__(self, attacker_sel: TargetsSelector, target_sel: TargetsSelector):
        self.attacker_sel, self.target_sel = attacker_sel, target_sel

    def execute(self, entities, ectx):
        a = resolve_unit(self.attacker_sel, entities)          # `SelectSingle(attacker)`
        aid = (a or {}).get("id")
        if aid is None or ectx.state is None:
            ectx.emit("AddForcedAttackTarget", attacker=None, added=[])
            return OperationResult.ok()
        comp = _component(ectx.state, int(aid))
        if comp is None:
            ectx.emit("AddForcedAttackTarget", attacker=int(aid), added=[])
            return OperationResult.ok()
        added = []
        for t in _targets_of(self.target_sel, entities):
            tid = t.get("id") if isinstance(t, dict) else None
            if tid is None:
                continue
            if comp.add(int(tid)):                             # `if (!Contains) Add`
                added.append(int(tid))
        ectx.emit("AddForcedAttackTarget", attacker=int(aid), added=added)
        return OperationResult.ok()


class RemoveForcedAttackTarget(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$RemoveForcedAttackTarget(attacker, target)` ->
    `IdunBattle.Entities.Behaviours.RemoveForcedAttackTargetBehaviour$$Execute` -- MEME corps que
    son jumeau ci-dessus, au dernier appel pres :

        foreach (t in <entities+0x58>.Select(entities, 3))  comp.<+0x50>.Remove(t.Id)

    ⚠ **AUCUN `Contains` prealable ici** (LU : le `Remove` est appele sans garde), la ou l'`Add` en
    a un. `List<int>.Remove` sur un absent est un no-op qui rend `false` -- observable identique,
    mais l'asymetrie est celle du natif et on la transcrit.

    A NE PAS CONFONDRE avec `DSLBehaviors$$RemoveAllForcedAttackTargets`, factory DISTINCTE (le port
    l'expose deja par `ForcedAttackTargetsComponent.clear`, qui DELIE en plus l'ecrivain-effet)."""
    __slots__ = ("attacker_sel", "target_sel")

    def __init__(self, attacker_sel: TargetsSelector, target_sel: TargetsSelector):
        self.attacker_sel, self.target_sel = attacker_sel, target_sel

    def execute(self, entities, ectx):
        a = resolve_unit(self.attacker_sel, entities)
        aid = (a or {}).get("id")
        if aid is None or ectx.state is None:
            ectx.emit("RemoveForcedAttackTarget", attacker=None, removed=[])
            return OperationResult.ok()
        comp = _component(ectx.state, int(aid))
        if comp is None:
            ectx.emit("RemoveForcedAttackTarget", attacker=int(aid), removed=[])
            return OperationResult.ok()
        removed = []
        for t in _targets_of(self.target_sel, entities):
            tid = t.get("id") if isinstance(t, dict) else None
            if tid is None:
                continue
            if comp.remove(int(tid)):                          # `Remove`, SANS `Contains`
                removed.append(int(tid))
        ectx.emit("RemoveForcedAttackTarget", attacker=int(aid), removed=removed)
        return OperationResult.ok()


class RefreshEffects(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$RefreshEffects(refreshEffectTrigger)` ->
    `IdunBattle.Operations.RefreshEffectsOperation`. Le seul litteral porte est
    `RefreshEffectTrigger.UnitStateChanged = 3` (`enums.tsv` : `0=Forced, 1=Simulation, 2=Custom,
    3=UnitStateChanged, ...`), celui du `CreateBehaviour` d'`InstinctiveBehaviour_UpdateTargetAbility`.

    CE QUE LE PORT FAIT, ET CE QU'IL NE FAIT PAS. Le refresh natif recalcule les
    `CreateActiveCondition` et joue `ActivateEffect`/`DeactivateEffect` -> `ApplyInternal` /
    `RevertInternal`. Cote port, `EffectsState.active_effects` REEVALUE `is_active` **a chaque
    lecture** : le volet ACTIVATION est donc structurellement a jour sans operation, et rejouer un
    refresh n'y changerait rien. Le volet STAT-MODIFIER, lui, est materialise (pose eager) et a
    son propre foyer -- c'est `runner/operations/refresh_effects.refresh_stat_modifier_effects`,
    que cette feuille APPELLE avec le trigger LU.

    Le pas de flux et les `UpdateEffectTargets` (liste `EffectComponent.Targets @+0x48`) ne sont pas
    portes : le port re-derive `IsEffectTarget` A LA LECTURE (`entities/effect_targets.py`), donc il
    n'a aucune liste materialisee a mettre a jour."""
    __slots__ = ("refresh_trigger",)

    def __init__(self, refresh_trigger: int):
        self.refresh_trigger = int(refresh_trigger)

    def execute(self, entities, ectx):
        from ...operations.refresh_effects import refresh_stat_modifier_effects
        if ectx.state is None:
            ectx.emit("RefreshEffects", trigger=self.refresh_trigger, rewritten=None)
            return OperationResult.ok()
        rewritten = refresh_stat_modifier_effects(ectx.state, refresh_trigger=self.refresh_trigger)
        ectx.emit("RefreshEffects", trigger=self.refresh_trigger, rewritten=rewritten)
        return OperationResult.ok()
