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
    l'element, ex. le `Func<entities,behaviour>` de `TauntWithNewChildrenWhoDidDamage`).

    NORMALISATION du selecteur (mirror du contrat natif `TargetsSelector` = IEnumerable) : un selecteur
    MONO-ENTITE (`Caster()`/`Target()`/`Subject()`, qui rend un DICT d'unite) compte pour UN element --
    sinon Python itererait les CLES du dict. Cas reel : `AddEffectOrIncreaseLevel @180de6860` construit
    `Foreach(self@0x148, ...)` sur un selecteur mono-entite."""
    __slots__ = ("selector", "body")

    def __init__(self, selector: TargetsSelector, body):
        self.selector, self.body = selector, body

    def execute(self, entities, ectx):
        res = OperationResult.ok()
        raw = self.selector.evaluate(entities)
        items = [] if raw is None else ([raw] if isinstance(raw, dict) else list(raw))
        for item in items:
            sub = replace(entities, subject=item)    # rebuild entities (subject swap), mirror Entity()
            node = self.body(sub) if callable(self.body) else self.body
            res = res.combine(node.execute(sub, ectx))
        return res


class If(AbilityBehaviour):
    """`DSLFactory.If(cond, then[, else]) @180df1960` (predicat LAZY + branches a EFFET) : execute `then`
    SSI `cond.evaluate` est vrai, sinon `otherwise` s'il existe. `cond` = noeud PREDICAT (`AbilityTrigger`,
    evaluate/should_trigger -> bool). La branche `else` est le 4e argument natif : ABSENTE (0) sur
    GetEmRuntz / `TauntWithNewChildrenWhoDidDamage` @1811e27a0 / la rotation FleshmetalGuns @18121f6e0,
    PRESENTE sur le lambda `AddEffectOrIncreaseLevel b__0 @180e25540`
    (`If(HasEffect, IncreaseEffectLevel, AddEffect)`)."""
    __slots__ = ("cond", "then", "otherwise")

    def __init__(self, cond: AbilityTrigger, then: AbilityBehaviour, otherwise: AbilityBehaviour = None):
        self.cond, self.then, self.otherwise = cond, then, otherwise

    def execute(self, entities, ectx):
        if self.cond.evaluate(entities):
            return self.then.execute(entities, ectx)
        if self.otherwise is not None:
            return self.otherwise.execute(entities, ectx)
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


class Inform(AbilityBehaviour):
    """`DSLFactory.Inform(messageType, entityId)` -> `InformBehaviour` : NOTIFIE les listeners d'un message
    (bus de messages natif). Le runner ne modelise PAS le bus -> NO-OP (aucune mutation d'etat) : l'ancien
    port de FireOfAbsolution (`Inform(0xb3, EntityId(target))` @18121f380) ne le modelisait pas et etait
    live-valide (les triggered-abilities fire via `EvaluateAbilities`/les vecteurs after-hit, PAS via un
    message Inform). Present pour le MIRROR STRUCTUREL de l'arbre (`Inform & splash & Maybe`). La charge utile
    (`EntityId(target)`) est DROPPEE (sans bus, sans effet observable). Emet 'Inform' (diag). PUR (stop=False)."""
    __slots__ = ("message_type",)

    def __init__(self, message_type: int):
        self.message_type = int(message_type)

    def execute(self, entities, ectx):
        ectx.emit("Inform", message_type=self.message_type)
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


class ChainBehaviour(AbilityBehaviour):
    """`DSLFactory.ChainBehaviour @180deb910` -> `Entities.Behaviours.ChainBehaviourBehaviour` : BOUCLE
    BORNEE qui REJOUE `body` au plus `times` fois, en RE-CONSTRUISANT a CHAQUE ITERATION le selecteur
    d'element (`next_selector`, natif `System.Func<>` sur une methode de la classe d'ability) et en le
    liant a **`ActiveTarget@0x180`** pour le corps. La boucle S'ARRETE des que le selecteur rend un
    ensemble VIDE.

    Unique consommateur porte : `IncursionAbility.ExecuteBehaviour @1811e9fe0` =
        `ChainBehaviour( Null@init, Func(GetNextSpawnTile), Direct(GetNumberConstant(0x3c)=maxSummons),
                         Spawn(caster@0x160, ActiveTarget@0x180, unitId, opts), <timeline> )`
    ou `IncursionAbility.GetNextSpawnTile @1811ea520` =
        `PickRandomly( CanAddUnit(AdjacentTiles(target@0x178)),
                       ConditionalAmount( (IsAlive(caster@0x160) & IsAlive(target@0x178))
                                          & IsInRange(caster, target, Direct(range)),
                                          1@dsl+0xc0, 0@dsl+0xb8 ) )`
    -> 1 tuile si (caster vivant ET cible vivante ET caster a portee), 0 sinon. C'est le MEME predicat que
    `IncursionAbility.GetContinueTrigger @1811ea420` (a l'identique, moins le PickRandomly) : la condition
    d'arret est RE-EVALUEE PAR ITERATION sur l'etat LIVE -- si les summons tuent la cible a leur apparition,
    `IsAlive(target)` devient faux et la chaine s'arrete AVANT d'avoir consomme ses `maxSummons`.

    `next_selector` = callable `(entities) -> TargetsSelector` (mirror du `Func<>` natif : une NOUVELLE
    instance de selecteur par iteration -> aucune memoisation entre tours, l'etat live est relu), ou un
    `TargetsSelector` fixe. `init` (natif `Null()`) = valeur initiale d'`ActiveTarget` avant la 1re
    iteration ; le `timeline` natif (`UnitTimelines.TypeToTimeline`) = ordonnancement VUE, non porte."""
    __slots__ = ("next_selector", "times", "body", "init")

    def __init__(self, next_selector, times, body: AbilityBehaviour, init=None):
        self.next_selector, self.times, self.body, self.init = next_selector, times, body, init

    def execute(self, entities, ectx):
        n = self.times.evaluate(entities) if isinstance(self.times, AAmountFormula) else int(self.times)
        res = OperationResult.ok()
        for _ in range(max(0, int(n))):
            sel = self.next_selector(entities) if callable(self.next_selector) else self.next_selector
            elems = sel.evaluate(entities)
            if elems is None:
                break
            if not isinstance(elems, list):
                elems = [elems]
            if not elems:                                  # selecteur vide -> fin de chaine (GetContinueTrigger)
                break
            sub = replace(entities, active_target=elems)   # bind ActiveTarget@0x180 = element(s) courant(s)
            r = self.body.execute(sub, ectx)
            res = res.combine(r)
            if r.stop:
                break
        return res


# Alias homonymes des factories natives (lecture des arbres 1:1 : `op_and`/`op_add` = `CombinedBehaviour`).
def op_and(left: AbilityBehaviour, right: AbilityBehaviour) -> Seq:
    """`AbilityBehaviour.op_BitwiseAnd @180ffaae0` -> `CombinedBehaviour` (cf. `Seq`)."""
    return Seq(left, right)


def op_add(left: AbilityBehaviour, right: AbilityBehaviour) -> Seq:
    """`AbilityBehaviour.op_Addition @180ffaa70` -> `CombinedBehaviour` (meme classe que `op_and`)."""
    return Seq(left, right)
