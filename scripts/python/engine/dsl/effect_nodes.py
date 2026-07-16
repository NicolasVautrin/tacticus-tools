"""Socle DSL d'EFFET-NOEUDS EXECUTABLES (#149 slice-2) — la couche `execute(ctx) -> mutations + events`
a cote du DSL LAZY `evaluate(ctx) -> valeur` de `base.py`.

Cap #149 (docs/rl/dsl-effect-nodes.md) : le runner porte les behaviours d'ability IMPERATIVEMENT
(`execute_*` dans runner/abilities|operations) au lieu des ARBRES DSL natifs. Ce module ajoute les
EFFET-NOEUDS pour reconstruire les behaviours = les arbres EXACTS du decompile, composes par les
combinateurs natifs, chaque feuille emettant les Operations DEJA portees (couche MINCE au-dessus de
l'Apply pipeline + cascade). RE (re-expert, PROUVE gqfc5mff6c) consignee dans dsl-effect-nodes.md
(section "Verdict RE #149 slice-2").

Contrat du walker natif (lu sur `CombinedBehaviour.Execute @180ffe730`, `ForeachBehaviour.Execute
@180fc6210`, `MaybeBehaviour.Execute @180fc9dc0`) :
    OperationResult Execute(this, AbilityEntities entities /*0x50, by-value*/, IProcessor* proc)
  - `entities` = le contexte lu par tous les noeuds (caster/owner/actor, target, casterPosition,
    abilityType, level, subject courant) = homologue de `DslContext` ; reconstruit par `Foreach`
    (subject = cible courante, `DSLFactory.Entity`).
  - `proc` (IProcessor*, classe DAT_1831d3468) = LE COLLECTEUR d'Operations, threade identiquement a
    travers TOUTE la recursion. Chaque feuille emet son Operation via un slot vtable de `proc`.
    -> cote port = `ExecutionContext` (state + rng + bus).
  - retour `OperationResult` (byte@+0x20 = flag succes/court-circuit), combine en remontant
    (`OperationResult.Combine`). Operations appliquees via `IdunRunner.Apply @180e34bf0` (cascade
    LIFO inline / FIFO deferred, deja portee).

LAZY vs EFFET = split STRUCTUREL : les `TargetsSelector`/valeurs (`AdjacentTiles`, `Enemies`, ...) =
noeuds `Node.evaluate -> valeur/liste` (base.py/selectors.py) ; les `*Behaviour` (`Spawn`, `Foreach`,
`Maybe`, `Combined`, `PerformAIAbility`, `AddBondEffect`) = `EffectNode.execute -> OperationResult +
Operations emises`. Un `Foreach`/`Maybe` APPELLE un selector lazy pour ses cibles puis execute son
child a effet.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, List

from .base import Node, DslContext


@dataclass
class OperationResult:
    """Retour de tout `*Behaviour.Execute` natif (8 slots ; byte@+0x20 = flag succes/COURT-CIRCUIT) ;
    `Combine` en remontant. Ici on ne modelise que `stop` (le flag de court-circuit exploite par
    `CombinedBehaviour`) : pour des effets PURS (Spawn/AddEffect) `stop` reste False -> les deux
    branches d'un `&`/`+` s'executent. Les Operations emises N'atterrissent PAS dans l'OperationResult
    mais dans le collecteur `proc` (= `ExecutionContext.emitted`), fidele au natif."""
    stop: bool = False

    def combine(self, other: "OperationResult") -> "OperationResult":
        # `OperationResult.Combine` : `stop` propage (OR) ; les Operations vivent dans `proc`.
        return OperationResult(stop=self.stop or other.stop)

    @staticmethod
    def ok() -> "OperationResult":
        return OperationResult(False)


class ExecutionContext:
    """`IProcessor* proc` natif (classe DAT_1831d3468) threade a travers TOUTE la recursion des
    `*Behaviour.Execute` = LE COLLECTEUR d'Operations. Cote port : porte `state` (ECS mute par les
    Operations portees), `rng` (tirages `Maybe`, cf. `prng.next_bool @180e39720`), `bus` (cascade
    LIFO/FIFO deja portee, runner/events.py). `emitted` = journal des Operations emises (etiquette +
    payload) pour le replay-diff DSL<->imperatif<->live ; sans equivalent natif (le `proc` natif
    applique directement)."""
    __slots__ = ("state", "rng", "bus", "emitted")

    def __init__(self, state=None, rng=None, bus=None):
        self.state = state
        self.rng = rng
        if bus is None:
            from ..runner.events import EventBus
            bus = EventBus()
        self.bus = bus
        self.emitted: List = []

    def emit(self, name: str, **payload) -> None:
        """Journalise une Operation emise par une feuille (etiquette natif + payload)."""
        self.emitted.append((name, payload))


class EffectNode:
    """Noeud a EFFET (mirror d'un `*Behaviour` natif). `execute(entities, ectx) -> OperationResult`
    (contrat du walker, cf. en-tete module). `entities` = `DslContext` (contexte lu, reconstruit par
    `Foreach`) ; `ectx` = `ExecutionContext` (le collecteur `proc`). A DISTINGUER de `Node.evaluate`
    (LAZY, valeur/cible). Chaque sous-classe cite la VA du `*Behaviour` qu'elle mirror."""
    __slots__ = ()

    def execute(self, entities: DslContext, ectx: ExecutionContext) -> OperationResult:  # pragma: no cover
        raise NotImplementedError(
            f"{type(self).__name__}.execute non porte (cf. #149 slice DSL-effet)")


class Seq(EffectNode):
    """`CombinedBehaviour.Execute @180ffe730` (factories `AbilityBehaviour.op_BitwiseAnd @180ffaae0`
    et `op_Addition @180ffaa70` allouent la MEME classe `CombinedBehaviour`, left@0x50 right@0x58) :
    sequence gauche->droite avec COURT-CIRCUIT. Exec left, `Combine` ; `if result.byte@+0x20 == 0`
    -> exec right, sinon STOP. Deux effets PURS -> flag 0 -> les deux s'executent (cf. le `op_Addition`
    de GetEmRuntz joignant `(Spawn & PerformAIAttack)` et `Foreach(Taunt)`)."""
    __slots__ = ("left", "right")

    def __init__(self, left: EffectNode, right: EffectNode):
        self.left, self.right = left, right

    def execute(self, entities, ectx):
        r = self.left.execute(entities, ectx)
        if r.stop:                                   # court-circuit natif (byte@+0x20 != 0)
            return r
        return r.combine(self.right.execute(entities, ectx))


class Maybe(EffectNode):
    """`MaybeBehaviour.Execute @180fc9dc0` (`DSLFactory.Maybe @180df6470`, ctor @180fca430) : UN
    tirage `next_bool(chance)` AVANT le child ; child execute SSI vrai. `chance` = `Node` (evaluate
    -> int) ou int litteral. `ectx.rng` absent -> tirage non calable offline -> child NON execute
    (no-op documente ; caler `state.rng` pour exercer/valider). Un seul `next_bool` par instance
    (la variante Foreach = 1 tirage par cible se compose via `Foreach(sel, lambda t: Maybe(...))`)."""
    __slots__ = ("chance", "child")

    def __init__(self, chance, child: EffectNode):
        self.chance, self.child = chance, child

    def execute(self, entities, ectx):
        if ectx.rng is None:
            return OperationResult.ok()              # rng non cale -> no-op (documente)
        ch = self.chance.evaluate(entities) if isinstance(self.chance, Node) else int(self.chance)
        if ectx.rng.next_bool(int(ch)):              # IntBasedMersenneTwister.NextBool @180e39720
            return self.child.execute(entities, ectx)
        return OperationResult.ok()


class Foreach(EffectNode):
    """`ForeachBehaviour.Execute @180fc6210` (`DSLFactory.Foreach @180defcd0`, ctor @180fc69c0) :
    evalue `selector` (Node LAZY -> liste), puis DANS L'ORDRE DU SELECTEUR (pas de tri) reconstruit
    `entities` (subject = element courant, `DSLFactory.Entity`) et execute `body`. `body` = un
    `EffectNode` STATIQUE, ou un Callable(entities_subject) -> EffectNode (corps dependant de
    l'element, ex. le `Func<entities,behaviour>` de `TauntWithNewChildrenWhoDidDamage`)."""
    __slots__ = ("selector", "body")

    def __init__(self, selector: Node, body):
        self.selector, self.body = selector, body

    def execute(self, entities, ectx):
        res = OperationResult.ok()
        for item in (self.selector.evaluate(entities) or []):
            sub = replace(entities, subject=item)    # rebuild entities (subject swap), mirror Entity()
            node = self.body(sub) if callable(self.body) else self.body
            res = res.combine(node.execute(sub, ectx))
        return res


class If(EffectNode):
    """`If(cond, then)` natif (predicat LAZY + branche a EFFET) : execute `then` SSI `cond.evaluate`
    est vrai. `cond` = `Node` (evaluate -> bool). Sans branche `else` (les behaviours GetEmRuntz /
    `TauntWithNewChildrenWhoDidDamage` @1811e27a0 n'en ont pas)."""
    __slots__ = ("cond", "then")

    def __init__(self, cond: Node, then: EffectNode):
        self.cond, self.then = cond, then

    def execute(self, entities, ectx):
        if self.cond.evaluate(entities):
            return self.then.execute(entities, ectx)
        return OperationResult.ok()


class Emit(EffectNode):
    """Feuille GENERIQUE emettant UNE Operation : patron des feuilles concretes (`SpawnUnit`,
    `AddBondEffect`, `PerformAIAttack`) = wrappers MINCES au-dessus des Operations DEJA portees
    (runner/operations). `fn(entities, ectx) -> payload_dict | None` appelle l'Operation portee (mute
    `ectx.state`/`ectx.bus`) ; `name` = etiquette de l'Operation native (journalisee via `ectx.emit`
    pour le replay-diff). Toujours `stop=False` (effet pur)."""
    __slots__ = ("name", "fn")

    def __init__(self, name: str, fn: Callable):
        self.name, self.fn = name, fn

    def execute(self, entities, ectx):
        payload = self.fn(entities, ectx) or {}
        ectx.emit(self.name, **payload)
        return OperationResult.ok()


# Alias homonymes des factories natives (lecture des arbres 1:1 : `op_and`/`op_add` = `CombinedBehaviour`).
def op_and(left: EffectNode, right: EffectNode) -> Seq:
    """`AbilityBehaviour.op_BitwiseAnd @180ffaae0` -> `CombinedBehaviour` (cf. `Seq`)."""
    return Seq(left, right)


def op_add(left: EffectNode, right: EffectNode) -> Seq:
    """`AbilityBehaviour.op_Addition @180ffaa70` -> `CombinedBehaviour` (meme classe que `op_and`)."""
    return Seq(left, right)
