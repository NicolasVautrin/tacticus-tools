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
    """`IdunBattle.DSL.CombinedBehaviour$$Execute` (factories `IdunBattle.DSL.AbilityBehaviour$$op_BitwiseAnd`
    et `IdunBattle.DSL.AbilityBehaviour$$op_Addition` allouent la MEME classe `CombinedBehaviour`, left@0x50 right@0x58) :
    sequence gauche->droite avec COURT-CIRCUIT. Exec left, `Combine` ; `if result.byte@+0x20 == 0`
    -> exec right, sinon STOP. Deux effets PURS -> flag 0 -> les deux s'executent (cf. le `op_Addition`
    de GetEmRuntz joignant `(Spawn & PerformAIAttack)` et `Foreach(Taunt)`).

    QUI peut poser le flag (N5) : SEULES les feuilles qui PROPAGENT le resultat de leur Operation --
    `IdunBattle.Entities.Behaviours.DiscardHitBehaviour$$Execute` recopie les 8 slots rendus par son
    operation dans son propre retour. Les feuilles qui JETTENT ce retour rendent un resultat
    zero-initialise et ne peuvent JAMAIS court-circuiter : c'est le cas d'`AddEffectBehaviour` (et
    d'`InformBehaviour`). Corollaire MESURE live : **un `AddEffect` REFUSE (immunite, cible morte,
    cible nulle) ou NO-OP (effet deja present) ne fait PAS tomber la suite de la chaine `&`** --
    `ExemplarOfHate` sur une cible `TerminatorArmour` execute son `Pinned`, l'override d'Attack,
    l'attaque libre et le retrait. (⚠ #208 : sur cette cible-la le `Pinned` n'est PAS refuse, il est
    POSE puis rendu INERTE par sa `CreateActiveCondition` -- l'exemple reste valable pour la chaine,
    ce n'etait juste pas un refus. Le refus, lui, reste atteignable par les autres branches du gate.)
    `Combine` OU-propage le flag
    (`IdunBattle.Core.OperationResult$$Combine` : `if (byte@+0x20 == 0) byte@+0x20 = other`)."""
    __slots__ = ("left", "right")

    def __init__(self, left: AbilityBehaviour, right: AbilityBehaviour):
        self.left, self.right = left, right

    def execute(self, entities, ectx):
        r = self.left.execute(entities, ectx)
        if r.stop:                                   # court-circuit natif (byte@+0x20 != 0)
            return r
        return r.combine(self.right.execute(entities, ectx))


class Maybe(AbilityBehaviour):
    """`IdunBattle.Entities.Behaviours.MaybeBehaviour$$Execute` (`IdunBattleLogic.Entities.DSLBehaviors$$Maybe`, IdunBattle.Entities.Behaviours.MaybeBehaviour$$.ctor) : UN
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
        if ectx.rng.next_bool(int(ch)):              # IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextBool
            return self.child.execute(entities, ectx)
        return OperationResult.ok()


class Foreach(AbilityBehaviour):
    """`IdunBattle.Entities.Behaviours.ForeachBehaviour$$Execute` (`IdunBattleLogic.Entities.DSLBehaviors$$Foreach`, IdunBattle.Entities.Behaviours.ForeachBehaviour$$.ctor) :
    evalue `selector` (noeud SELECTEUR `TargetsSelector` -> liste), puis DANS L'ORDRE DU SELECTEUR (pas de tri) reconstruit
    `entities` (subject = element courant, `DSLFactory.Entity`) et execute `body`. `body` = un
    `AbilityBehaviour` STATIQUE, ou un Callable(entities_subject) -> AbilityBehaviour (corps dependant de
    l'element, ex. le `Func<entities,behaviour>` de `TauntWithNewChildrenWhoDidDamage`).

    NORMALISATION du selecteur (mirror du contrat natif `TargetsSelector` = IEnumerable) : un selecteur
    MONO-ENTITE (`Caster()`/`Target()`/`Subject()`, qui rend un DICT d'unite) compte pour UN element --
    sinon Python itererait les CLES du dict. Cas reel : `IdunBattleLogic.Entities.DSLBehaviors$$AddEffectOrIncreaseLevel` construit
    `Foreach(self@0x148, ...)` sur un selecteur mono-entite.

    LIAISON DE L'ELEMENT COURANT — le natif ecrit dans DEUX endroits selon la forme du corps
    (`IdunBattle.Entities.Behaviours.ForeachBehaviour$$Execute`, lu au decompile) :
      * corps = `Func<entity, behaviour>` (champ +0x68) -> il enveloppe l'element dans
        `IdunBattleLogic.Entities.DSLSelectors$$Entity(elem)` et le passe au lambda (== `Subject()` cote port) ;
      * corps = behaviour STATIQUE (champ +0x60) -> il ecrit `entities[slot 4] = elem` AVANT d'executer,
        c.-a-d. le slot que le selecteur cache `factory+0x180` (**ActiveTarget**, `It`) relit.
    Le port lie donc les DEUX (`subject` ET `active_target`) : les corps existants qui lisent `Subject()`
    sont inchanges, et un corps qui lit `ActiveTarget()`/`It@0x180` (ex.
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ChronometronAbility$$ExecuteBehaviour`) resout enfin.
    Purement ADDITIF : hors `Foreach`, `active_target` n'etait pose que par le sous-behaviour on-appearance
    d'un `Spawn` et par `ChainBehaviour` — aucun de ces deux corps n'est un `Foreach`."""
    __slots__ = ("selector", "body")

    def __init__(self, selector: TargetsSelector, body):
        self.selector, self.body = selector, body

    def execute(self, entities, ectx):
        res = OperationResult.ok()
        raw = self.selector.evaluate(entities)
        items = [] if raw is None else ([raw] if isinstance(raw, dict) else list(raw))
        for item in items:
            # `subject` = branche lambda (`Entity(elem)`) ; `active_target` = branche behaviour statique
            # (`entities[slot 4] = elem`, relu par `ActiveTarget@0x180`). cf. docstring.
            sub = replace(entities, subject=item, active_target=item)
            node = self.body(sub) if callable(self.body) else self.body
            res = res.combine(node.execute(sub, ectx))
        return res


class If(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$If(cond, then[, else])` (predicat LAZY + branches a EFFET) : execute `then`
    SSI `cond.evaluate` est vrai, sinon `otherwise` s'il existe. `cond` = noeud PREDICAT (`AbilityTrigger`,
    evaluate/should_trigger -> bool). La branche `else` est le 4e argument natif : ABSENTE (0) sur
    GetEmRuntz / `IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$TauntWithNewChildrenWhoDidDamage / la rotation FleshmetalGuns IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGunsAbility$$CreateBehaviour,
    PRESENTE sur le lambda `AddEffectOrIncreaseLevel b__0 IdunBattleLogic.Entities.DSLFactory.u003Cu003Ec__DisplayClass569_0$$u003CAddEffectOrIncreaseLevelu003Eb__0`
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


class Repeat(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$Repeat(behaviour, times)` ->
    `IdunBattle.Entities.Behaviours.RepeatBehaviour$$Execute`, dont le corps est LU en entier
    (build `rnca9r7q6c`, ghidra nomme le ctor `IdunBattle.DSL.CombinedBehaviour$$.ctor` -- fold
    ICF, la STRUCTURE est lue, jamais le nom) :

        result = default(OperationResult)                 // memset 0x40 en tete
        n = this.<+0x58 times>.Calculate(entities)         // slot 1 d'`IAmountFormula`
        for (i = 0; i < n; i++)
            result.Combine( this.<+0x50 behaviour>.Execute(entities, processor) )   // slot 0
        return result

    TROIS points LUS, et chacun compte :
      * **AUCUN court-circuit** -- la boucle ne teste PAS `OperationResult.<+0x20>` (contraste
        `Seq`, qui le teste). Un corps qui rend `stop` n'arrete pas les iterations suivantes ;
        `Combine` se contente d'OU-propager le flag vers le resultat agrege.
      * **`times` est evalue UNE SEULE FOIS**, AVANT la boucle (le `Calculate` precede le
        `for`). Un corps qui ferait bouger la grandeur que la formule lit ne change pas le
        nombre d'iterations.
      * **le MEME `entities` est passe a chaque iteration** : le noeud ne LIE rien (ni `subject`,
        ni `active_target`, ni un index d'iteration) -- c'est ce qui le distingue de `Foreach`
        et de `ChainBehaviour`. Toute progression entre deux iterations passe donc par l'ETAT
        (le `DslContext` du port partage ses listes par reference), pas par le contexte.

    `n <= 0` -> zero iteration, resultat vide (le `if (0 < iVar15)` du decompile).
    Premier consommateur porte : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SynapticLinchpinAbility$$CreateBehaviour`
    (`Repeat(If(<cap non atteint>, Spawn(...)), Direct(nrOfSummons))`)."""
    __slots__ = ("body", "times")

    def __init__(self, body: AbilityBehaviour, times):
        self.body, self.times = body, times

    def execute(self, entities, ectx):
        # `times.Calculate(entities)` -- UNE fois, avant la boucle (cf. docstring).
        n = self.times.evaluate(entities) if isinstance(self.times, AAmountFormula) else int(self.times)
        res = OperationResult.ok()
        for _ in range(max(0, int(n))):
            res = res.combine(self.body.execute(entities, ectx))   # PAS de court-circuit (natif)
        return res


class SetCache(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$SetCache(node)` (3 overloads -> MEME classe `SetCacheBehaviour`,
    DAT_18320e858 ; les ctors affiches `RefreshDynamicStatModifierValueBehaviour`/`ActivateEffectBehaviour`
    sont des folds gshared MISLABELES) -> `IdunBattle.Entities.Behaviours.SetCacheBehaviour$$Execute` : EVALUE le noeud cache
    (slot +0x60 pour un PREDICAT, +0x50 selecteur / +0x58 formule) et rend un resultat VIDE — **aucune
    mutation d'etat, aucun court-circuit**. Son SEUL effet est de PLACER le noeud `Cache` dans le temps :
    tout consommateur AVAL du meme `Cache` relira le verdict fige ICI.

    Consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$ExecuteBehaviour`
    (`(SetCache(cond) + attack) + If(cond, spawn)` : le critere de summon est evalue AVANT l'attaque).
    Deterministe, 0 tirage -> n'altere PAS l'ordre `state.rng` de l'attaque qui le suit. PUR (stop=False)."""
    __slots__ = ("node",)

    def __init__(self, node):
        self.node = node

    def execute(self, entities, ectx):
        self.node.evaluate(entities)                 # force la 1re eval -> remplit le cache
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
    port de FireOfAbsolution (`Inform(0xb3, EntityId(target))` IdunBattleLogic.Entities.Abilities.Active.Loki.FireOfAbsolutionAbility$$CreateBehaviour) ne le modelisait pas et etait
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
    """`IdunBattleLogic.Entities.DSLBehaviors$$AtomicGroup` (`Core.Services.OperationProcessor$$CreateAtomicGroup` → `IdunBattle.Operations.AtomicGroupOperation$$Execute`) : enveloppe un behaviour dans un GROUPE ATOMIQUE. RE #201 (docs/rl/runner-engine.md §1.5bis)
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


class Group(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$Group(child, targetsSelector, groupId)` ->
    `IdunBattle.Entities.Behaviours.GroupBehaviour$$Execute` — MIRROR du decompile :

        targets = (+0x68).Select(entities)              # selecteur de cibles du groupe (VUE)
        (+0x70).<slot 0>(groupId@+0x60, targets, ...)   # OUVRE le groupe de presentation
        if (+0x50) : (+0x50).Execute(entities)          # <- le CHILD, execute INLINE
        if (+0x58) : <callback de fermeture>
        return <resultat VIDE>                          # jamais de court-circuit

    => cote ETAT, c'est un PASS-THROUGH strict (aucune mutation propre, aucun `stop`) : le groupe
    n'existe que pour la couche VUE/timeline (meme statut que `AtomicGroup` cote port, cf. #201).
    Le noeud est porte pour le MIRROR STRUCTUREL des arbres qui l'utilisent -- 3 bandes de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.PlagueWindAbility$$ExecuteBehaviour`
    (`Group(bande1, Target, 0x4b) & Group(bande2, Target, 0x4c) & Group(bande3, Target, 0x4d)`) et
    3 bandes de `IdunBattleLogic.Entities.Abilities.Active.Loki.KillMaimBurnAbility$$ExecuteBehaviour`
    (`Group(bande_i, <cible de la bande i>, 0x20)`).
    `group_id` reste une METADONNEE ; `targets_sel`, lui, est EVALUE (cf. `execute` ci-dessous)."""
    __slots__ = ("child", "group_id", "targets_sel")

    def __init__(self, child: AbilityBehaviour, group_id: int = 0, targets_sel=None):
        self.child, self.group_id, self.targets_sel = child, int(group_id), targets_sel

    def execute(self, entities, ectx):
        # `targets = (+0x68).Select(entities)` -- le natif EVALUE le selecteur de groupe AVANT le
        # child, et cette evaluation n'est PAS gratuite : #504 l'a MESUREE. Sur `KillMaimBurn`
        # (1132) le selecteur de groupe d'une bande est le noeud de re-ciblage `GetNextTarget`,
        # dont le `SortUnitsByDamageUtility` consomme un tirage `RandomAmount(minDmg_2, maxDmg_2)`
        # sur le PRNG de bataille. Sans cette ligne le port consommait 20 tirages la ou le natif en
        # consomme 24, et TOUTE la sequence de degat aval divergeait (le TOTAL, lui, restait juste
        # quand les cibles etaient surtuees -- un critere sur le total serait reste VERT).
        #
        # ⚠ La ligne qui vivait ici disait « jamais evalues : l'evaluer offline ajouterait un effet
        # de bord de `Cache` inexistant cote etat ». C'etait faux dans les deux sens : le natif
        # EVALUE (son propre decompile, transcrit dans la docstring ci-dessus, le montre), et
        # amorcer un `Cache` a l'ouverture du groupe est precisement ce que le natif fait. Les deux
        # consommateurs anterieurs ne changent pas de valeur pour autant -- PlagueWind passe
        # `Cache(Target())` (memo amorce sur la cible du message, meme valeur, aucun tirage) et
        # SilentDeath passe `Null()` (ensemble vide).
        if self.targets_sel is not None:
            self.targets_sel.evaluate(entities)
        return self.child.execute(entities, ectx)    # `if (+0x50) : (+0x50).Execute(entities)`


class ChainBehaviour(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$ChainBehaviour` -> `Entities.Behaviours.ChainBehaviourBehaviour` : BOUCLE
    BORNEE qui REJOUE `body` au plus `times` fois, en RE-CONSTRUISANT a CHAQUE ITERATION le selecteur
    d'element (`next_selector`, natif `System.Func<>` sur une methode de la classe d'ability) et en le
    liant a **`ActiveTarget@0x180`** pour le corps. La boucle S'ARRETE des que le selecteur rend un
    ensemble VIDE.

    Unique consommateur porte : `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$ExecuteBehaviour` =
        `ChainBehaviour( Null@init, Func(GetNextSpawnTile), Direct(GetNumberConstant(0x3c)=maxSummons),
                         Spawn(caster@0x160, ActiveTarget@0x180, unitId, opts), <timeline> )`
    ou `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$GetNextSpawnTile` =
        `PickRandomly( CanAddUnit(AdjacentTiles(target@0x178)),
                       ConditionalAmount( (IsAlive(caster@0x160) & IsAlive(target@0x178))
                                          & IsInRange(caster, target, Direct(range)),
                                          1@dsl+0xc0, 0@dsl+0xb8 ) )`
    -> 1 tuile si (caster vivant ET cible vivante ET caster a portee), 0 sinon. C'est le MEME predicat que
    `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$GetContinueTrigger` (a l'identique, moins le PickRandomly) : la condition
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
    """`IdunBattle.DSL.AbilityBehaviour$$op_BitwiseAnd` -> `CombinedBehaviour` (cf. `Seq`)."""
    return Seq(left, right)


def op_add(left: AbilityBehaviour, right: AbilityBehaviour) -> Seq:
    """`IdunBattle.DSL.AbilityBehaviour$$op_Addition` -> `CombinedBehaviour` (meme classe que `op_and`)."""
    return Seq(left, right)
