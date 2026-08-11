"""#937 -- le noeud E `Repeat` (`IdunBattleLogic.Entities.DSLBehaviors$$Repeat` ->
`IdunBattle.Entities.Behaviours.RepeatBehaviour$$Execute`), grave HORS de tout regime d'ability.

POURQUOI CE FICHIER EXISTE. Le harnais adversarial de `SynapticLinchpin`
(`probe_937_mutants.py`, mutant **M10**) mute `Repeat` en « UNE iteration quel que soit `times` »
et reste **INERTE** : son unique consommateur porte lit `GetNumberConstant(nrOfSummons) == 1`, donc
la boucle native ne fait jamais qu'un tour dans ce regime. Un mutant inerte n'est pas un mutant
reussi -- il dit que l'observable n'est garde NULLE PART. On le DEPLACE donc ici, ou il mord :
le noeud est confronte a son decompile, pas a l'ability qui l'emploie.

Corps natif LU en entier (build `rnca9r7q6c` ; ghidra etiquette le ctor
`IdunBattle.DSL.CombinedBehaviour$$.ctor` -- fold ICF, la STRUCTURE est lue, jamais le nom) :

    result = default(OperationResult)                  // memset 0x40 en tete
    n = this.<+0x58 times>.Calculate(entities)          // slot 1 d'`IAmountFormula`, UNE fois
    for (i = 0; i < n; i++)                             // `if (0 < iVar15)` puis boucle
        result.Combine( this.<+0x50 behaviour>.Execute(entities, processor) )   // slot 0
    return result

Trois faits, chacun garde par un cas :
  1. **n executions** -- pas une, pas `n+1` ;
  2. **`times` evalue UNE SEULE FOIS**, AVANT la boucle (le `Calculate` precede le `for`) : un corps
     qui fait bouger la grandeur lue par la formule ne change PAS le nombre de tours ;
  3. **AUCUN court-circuit** : la boucle ne teste pas `OperationResult.<+0x20>` (contraste
     `CombinedBehaviour`, qui le teste) -- un corps qui rend `stop` n'interrompt pas les tours
     suivants, `Combine` se contente d'OU-propager le drapeau.
Plus le bord : `n <= 0` -> zero tour.

100 % offline : aucun runner, aucun RPC. Les corps sont des `AbilityBehaviour` jouets.
"""
from __future__ import annotations

from engine.dsl.base import AAmountFormula, Const
from engine.dsl.effects import AbilityBehaviour, ExecutionContext, OperationResult
from engine.entities.behaviours import Repeat

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/behaviours.py",
        "scripts/python/engine/dsl/effects.py",
        "scripts/python/engine/dsl/base.py",
    ),
    "build": False,
    "toujours": False,
    "raison": ("Le noeud `Repeat` (`RepeatBehaviour$$Execute`) : nombre EXACT de tours, evaluation "
               "UNIQUE de `times` avant la boucle, et ABSENCE de court-circuit sur `stop`. Ces "
               "trois faits sont INOBSERVABLES depuis son unique consommateur porte "
               "(`SynapticLinchpin`, dont `nrOfSummons` vaut 1) -- c'est ici qu'ils sont gardes."),
}


class _Counter(AbilityBehaviour):
    """Corps jouet : compte ses executions et rend `stop` selon `stop_at`."""

    def __init__(self, stop_at=None):
        self.calls = 0
        self.seen = []
        self.stop_at = stop_at

    def execute(self, entities, ectx):
        self.calls += 1
        self.seen.append(entities)
        if self.stop_at is not None and self.calls >= self.stop_at:
            return OperationResult(stop=True)
        return OperationResult.ok()


class _MutableAmount(AAmountFormula):
    """Formule dont la valeur SUIT un compteur externe -- sert a prouver que `times` est lu UNE
    fois : si le noeud la relisait a chaque tour, le nombre de tours changerait."""

    def __init__(self, box):
        self.box = box

    def calculate(self, ctx):
        self.box["reads"] += 1
        return self.box["value"]


def _ectx():
    return ExecutionContext(state=None, rng=None)


def test_repeat_executes_exactly_n_times():
    """`for (i = 0; i < n; i++)` : EXACTEMENT `n` executions du corps."""
    for n in (1, 2, 3, 7):
        body = _Counter()
        Repeat(body, Const(n)).execute({"tag": "e"}, _ectx())
        assert body.calls == n, f"Repeat(times={n}) a execute {body.calls} fois"


def test_repeat_is_a_no_op_for_non_positive_times():
    """`if (0 < iVar15)` : `n <= 0` -> ZERO tour, et un resultat VIDE (`stop` faux)."""
    for n in (0, -1, -5):
        body = _Counter(stop_at=1)
        res = Repeat(body, Const(n)).execute({"tag": "e"}, _ectx())
        assert body.calls == 0, f"Repeat(times={n}) a execute {body.calls} fois"
        assert res.stop is False, f"Repeat(times={n}) rend stop={res.stop}"


def test_repeat_evaluates_times_once_before_the_loop():
    """Le `Calculate` PRECEDE le `for` : la formule est lue UNE fois, et une valeur qui bouge
    PENDANT la boucle ne change pas le nombre de tours."""
    box = {"value": 3, "reads": 0}

    class _Bumper(_Counter):
        def execute(self, entities, ectx):
            box["value"] += 10           # si `times` etait relu, la boucle s'emballerait
            return super().execute(entities, ectx)

    body = _Bumper()
    Repeat(body, _MutableAmount(box)).execute({"tag": "e"}, _ectx())
    assert body.calls == 3, f"{body.calls} tours au lieu de 3 -- `times` a ete relu dans la boucle"
    assert box["reads"] == 1, f"`times` lu {box['reads']} fois au lieu d'UNE"


def test_repeat_does_not_short_circuit_on_stop():
    """La boucle ne teste PAS `OperationResult.<+0x20>` : un corps qui rend `stop` des le 1er tour
    est quand meme rejoue, et le drapeau est OU-propage par `Combine`.

    ⚠ C'est la difference LUE avec `CombinedBehaviour` (le `Seq` du port), qui, lui, court-circuite.
    Le cas garde donc les DEUX comportements a la fois : celui de `Repeat` et sa distinction."""
    body = _Counter(stop_at=1)           # rend `stop=True` a CHAQUE tour
    res = Repeat(body, Const(4)).execute({"tag": "e"}, _ectx())
    assert body.calls == 4, \
        f"Repeat s'est arrete apres {body.calls} tour(s) : il a court-circuite sur `stop`"
    assert res.stop is True, "le drapeau `stop` du corps doit remonter par `Combine`"

    # contre-epreuve : `Seq`, lui, COURT-CIRCUITE -- sinon ce cas ne prouverait pas une difference
    from engine.entities.behaviours import Seq
    left, right = _Counter(stop_at=1), _Counter()
    Seq(left, right).execute({"tag": "e"}, _ectx())
    assert left.calls == 1 and right.calls == 0, \
        "`Seq` ne court-circuite plus -> le contraste avec `Repeat` n'est plus mesure"


def test_repeat_passes_the_same_entities_to_every_iteration():
    """Le noeud ne LIE rien (ni `subject`, ni `active_target`, ni un index) : chaque tour recoit le
    MEME `entities`. C'est ce qui le distingue de `Foreach` et de `ChainBehaviour`."""
    body = _Counter()
    ents = {"tag": "e"}
    Repeat(body, Const(3)).execute(ents, _ectx())
    assert body.calls == 3
    assert all(x is ents for x in body.seen), \
        "Repeat a reconstruit le contexte entre deux tours (il ne doit RIEN lier)"
