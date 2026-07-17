"""Noeuds EFFET du DSL = COMBINATEURS de la famille `AbilityBehaviour.Execute` (kind E) :
`Seq`/`Maybe`/`Foreach`/`If`/`Emit` (+ factories `op_and`/`op_add`).

Mirror du namespace natif `IdunBattle.Entities.Behaviours` (`CombinedBehaviour`/`MaybeBehaviour`/
`ForeachBehaviour`/...) : les concrets vivent ici, a cote de leurs freres `entities/{abilities,
selectors,triggers,formulas,effects}`. La BASE `AbilityBehaviour` + l'infra du walker (`OperationResult`/
`ExecutionContext`, = `IdunBattle.DSL`) restent dans `dsl/effects.py`. Les feuilles runner concretes
(`SpawnUnit`/`PerformAIAttack`/`AddBondEffect`) vivent dans `runner/abilities/behaviours.py` (couplees
aux Operations). Construits via la facade `DSLFactory` (`dsl/nodes.py`)."""
from __future__ import annotations

from dataclasses import replace
from typing import Callable

from ..dsl.base import AAmountFormula, AbilityTrigger, TargetsSelector
from ..dsl.effects import AbilityBehaviour, OperationResult


class Seq(AbilityBehaviour):
    """`CombinedBehaviour.Execute @180ffe730` (factories `AbilityBehaviour.op_BitwiseAnd @180ffaae0`
    et `op_Addition @180ffaa70` allouent la MEME classe `CombinedBehaviour`, left@0x50 right@0x58) :
    sequence gauche->droite avec COURT-CIRCUIT. Exec left, `Combine` ; `if result.byte@+0x20 == 0`
    -> exec right, sinon STOP. Deux effets PURS -> flag 0 -> les deux s'executent (cf. le `op_Addition`
    de GetEmRuntz joignant `(Spawn & PerformAIAttack)` et `Foreach(Taunt)`)."""
    __slots__ = ("left", "right")

    def __init__(self, left: AbilityBehaviour, right: AbilityBehaviour):
        self.left, self.right = left, right

    def execute(self, entities, ectx):
        r = self.left.execute(entities, ectx)
        if r.stop:                                   # court-circuit natif (byte@+0x20 != 0)
            return r
        return r.combine(self.right.execute(entities, ectx))


class Maybe(AbilityBehaviour):
    """`MaybeBehaviour.Execute @180fc9dc0` (`DSLFactory.Maybe @180df6470`, ctor @180fca430) : UN
    tirage `next_bool(chance)` AVANT le child ; child execute SSI vrai. `chance` = noeud VALEUR
    (`AAmountFormula`, evaluate/calculate -> int) ou int litteral. `ectx.rng` absent -> tirage non calable offline -> child NON execute
    (no-op documente ; caler `state.rng` pour exercer/valider). Un seul `next_bool` par instance
    (la variante Foreach = 1 tirage par cible se compose via `Foreach(sel, lambda t: Maybe(...))`)."""
    __slots__ = ("chance", "child")

    def __init__(self, chance, child: AbilityBehaviour):
        self.chance, self.child = chance, child

    def execute(self, entities, ectx):
        if ectx.rng is None:
            return OperationResult.ok()              # rng non cale -> no-op (documente)
        ch = self.chance.evaluate(entities) if isinstance(self.chance, AAmountFormula) else int(self.chance)
        if ectx.rng.next_bool(int(ch)):              # IntBasedMersenneTwister.NextBool @180e39720
            return self.child.execute(entities, ectx)
        return OperationResult.ok()


class Foreach(AbilityBehaviour):
    """`ForeachBehaviour.Execute @180fc6210` (`DSLFactory.Foreach @180defcd0`, ctor @180fc69c0) :
    evalue `selector` (noeud SELECTEUR `TargetsSelector` -> liste), puis DANS L'ORDRE DU SELECTEUR (pas de tri) reconstruit
    `entities` (subject = element courant, `DSLFactory.Entity`) et execute `body`. `body` = un
    `AbilityBehaviour` STATIQUE, ou un Callable(entities_subject) -> AbilityBehaviour (corps dependant de
    l'element, ex. le `Func<entities,behaviour>` de `TauntWithNewChildrenWhoDidDamage`)."""
    __slots__ = ("selector", "body")

    def __init__(self, selector: TargetsSelector, body):
        self.selector, self.body = selector, body

    def execute(self, entities, ectx):
        res = OperationResult.ok()
        for item in (self.selector.evaluate(entities) or []):
            sub = replace(entities, subject=item)    # rebuild entities (subject swap), mirror Entity()
            node = self.body(sub) if callable(self.body) else self.body
            res = res.combine(node.execute(sub, ectx))
        return res


class If(AbilityBehaviour):
    """`If(cond, then)` natif (predicat LAZY + branche a EFFET) : execute `then` SSI `cond.evaluate`
    est vrai. `cond` = noeud PREDICAT (`AbilityTrigger`, evaluate/should_trigger -> bool). Sans branche
    `else` (les behaviours GetEmRuntz / `TauntWithNewChildrenWhoDidDamage` @1811e27a0 n'en ont pas)."""
    __slots__ = ("cond", "then")

    def __init__(self, cond: AbilityTrigger, then: AbilityBehaviour):
        self.cond, self.then = cond, then

    def execute(self, entities, ectx):
        if self.cond.evaluate(entities):
            return self.then.execute(entities, ectx)
        return OperationResult.ok()


class Emit(AbilityBehaviour):
    """Feuille GENERIQUE emettant UNE Operation : patron des feuilles concretes (`SpawnUnit`,
    `AddBondEffect`, `PerformAIAttack`, runner/abilities/behaviours.py) = wrappers MINCES au-dessus
    des Operations DEJA portees (runner/operations). `fn(entities, ectx) -> payload_dict | None` appelle
    l'Operation portee (mute `ectx.state`/`ectx.bus`) ; `name` = etiquette de l'Operation native
    (journalisee via `ectx.emit` pour le replay-diff). Toujours `stop=False` (effet pur)."""
    __slots__ = ("name", "fn")

    def __init__(self, name: str, fn: Callable):
        self.name, self.fn = name, fn

    def execute(self, entities, ectx):
        payload = self.fn(entities, ectx) or {}
        ectx.emit(self.name, **payload)
        return OperationResult.ok()


class AtomicGroup(AbilityBehaviour):
    """`DSLFactory.AtomicGroup @180de9490` (`proc.CreateAtomicGroup @180e073f0` → `AtomicGroupOperation.Execute
    @180e5e200`) : enveloppe un behaviour dans un GROUPE ATOMIQUE. RE #201 (docs/rl/runner-engine.md §1.5bis)
    a PROUVÉ que le groupe s'exécute **INLINE** (pas différé) : `AtomicGroupOperation.Execute` ouvre le groupe,
    **invoque le callback (= exécute le child ICI, synchrone)**, ferme, mini-drain local. Le port n'a pas de
    transaction ECS atomique (les Operations mutent `state` en direct) → le groupe = **pass-through
    d'exécution** (exécute `child` inline). Le nœud existe pour le MIRROR STRUCTUREL (l'arbre natif de
    GetEmRuntz = `ExecuteAtomic(Spawn)` = `AtomicGroup(Spawn)`) et pour marquer la frontière de groupe."""
    __slots__ = ("child",)

    def __init__(self, child: AbilityBehaviour):
        self.child = child

    def execute(self, entities, ectx):
        return self.child.execute(entities, ectx)   # inline (RE #201 : AtomicGroup PAS différé)


# Alias homonymes des factories natives (lecture des arbres 1:1 : `op_and`/`op_add` = `CombinedBehaviour`).
def op_and(left: AbilityBehaviour, right: AbilityBehaviour) -> Seq:
    """`AbilityBehaviour.op_BitwiseAnd @180ffaae0` -> `CombinedBehaviour` (cf. `Seq`)."""
    return Seq(left, right)


def op_add(left: AbilityBehaviour, right: AbilityBehaviour) -> Seq:
    """`AbilityBehaviour.op_Addition @180ffaa70` -> `CombinedBehaviour` (meme classe que `op_and`)."""
    return Seq(left, right)
