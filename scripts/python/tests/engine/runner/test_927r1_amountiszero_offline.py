"""#927-r1 -- `AmountIsZero` n'est PAS un `AmountIsGreater` : c'est une IDENTITE DE CLASSE, pas un
offset.

CE QUE LE RESIDU AFFIRMAIT, ET QUI EST REFUTE. « Deux call-sites lisent `<DSLFormulas + 0x20>` et
leurs comportements MESURES sont incompatibles -- l'un des deux offsets affiches par le pseudo-C est
faux. » Les DEUX offsets sont JUSTES, verifies a l'ASSEMBLEUR sur le build `t6dpr4k06g` :

    IdunBattleLogic.Entities.DSLFormulas$$.ctor        prologue `mov rdi,rcx`  (donc `rdi == this`)
        `xor edx,edx ; call <ctor> ; mov [rdi+0x18],rbx`   ->  `+0x18 = Direct(0)`
        `mov edx,1   ; call <ctor> ; mov [rdi+0x20],rbx`   ->  `+0x20 = Direct(1)`
    IdunBattleLogic.Entities.DSLTriggers$$AmountIsZero
        `mov rax,[rcx+0x10]`        -> le `dsl` (pose par `DSLTriggers$$.ctor`)
        `mov rax,[rax+0x80]`        -> `DSLFormulas` (PROUVE : `FuryOfTheAncientsAbility$$
                                       CreateBehaviour` appelle `DSLFormulas$$ConfigConst` sur CE
                                       champ du MEME `dsl`)
        `mov rdi,[rax+0x20]`        -> `minAmount = Direct(1)`

LA VRAIE CAUSE est le piege deja documente du depot : **`$$.ctor` n'est pas l'identite de classe**.
Le discriminant est l'`Il2CppClass*` passe a l'allocateur, jamais le nom du ctor -- lequel est un
corps TRIVIAL que l'ICF fond :

    DSLTriggers$$AmountIsZero            alloue <classe A>, minAmount = <formulas+0x20> = 1
    DSLTriggers$$AmountIsEqualOrGreater  alloue la MEME <classe A>
    DSLTriggers$$AmountIsGreaterThanZero alloue <classe B>, minAmount = <formulas+0x18> = 0
    DSLTriggers$$AmountIsGreater         alloue la MEME <classe B>

et les deux `ShouldTrigger` sont NOMMES et ne comparent PAS pareil :
`IdunBattle.Entities.Conditions.AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger` finit par
`return minAmount.Calculate() <= value;`, tandis que
`IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$ShouldTrigger` finit par `<`.

D'ou, verbatim : `AmountIsZero(x)` = `NOT (1 <= x)` = **`x == 0`** -- ce que son NOM dit, ce que
`probe_927 --solo` mesure (un seul ennemi adjacent suffit), et ce qui garde `FabricatorClawArray`
VIVANTE (son selecteur est un `PickRandomly(..., 1)`, donc `Count <= 1` toujours : la lecture
`AmountIsGreater` en aurait fait un gate `Count >= 2`, JAMAIS vrai).

CE QUE CE FICHIER GARDE, avec son CONTRE-CAS integre :
  (1) le noeud porte rend `x == 0` sur un cardinal, et la lecture REFUTEE (`NOT (1 < x)` = `x <= 1`)
      rend un verdict DIFFERENT sur `x == 1` -- c'est le point de mesure discriminant ;
  (2) `MAX_TARGETS` de `FuryOfTheAncients` vaut 1 (`<formulas+0x20>`, le MEME champ) ;
  (3) le gate `NOT AmountIsZero(count)` s'ouvre des UN element, et se ferme a zero.

ASCII only. OFFLINE : aucun runner, aucune session.
"""
from __future__ import annotations

# Declencheur (#486-r15) : fichier PUREMENT offline et structurel. Il evalue un noeud DSL sur des
# constantes et lit une constante de module ; il n'ouvre AUCUN chemin (`open`, `read_text`, `Path`,
# `rglob` : zero occurrence) et ne lit ni le binaire ni `data/symbols/**`. Sa fermeture d'imports
# tient dans la cascade derivee de ses foyers, qu'il ne faut PAS re-declarer (#531).
DECLENCHEUR = {
    "chemins": (),
    "build": False,
    "toujours": False,
    "raison": (
        "Fichier PUREMENT offline : il evalue `entities/triggers.py::AmountIsZero` sur des "
        "constantes et lit `MAX_TARGETS`. Aucun chemin ouvert, aucune entree de build lue. "
        "`chemins` vide est le resultat, pas un aveu."
    ),
}

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import pytest                                                              # noqa: E402

from engine.dsl.base import Const                                          # noqa: E402
from engine.entities.triggers import AmountIsEqualOrGreater, AmountIsZero, Not  # noqa: E402
from engine.runner.operations.triggers.loki import fury_of_the_ancients as FA   # noqa: E402


#: Les deux constantes de `DSLFormulas`, LUES a l'assembleur (cf. l'en-tete). Elles sont ECRITES ici
#: parce que c'est la valeur MESUREE a la conversion : `probe_313` compare un mirror au build, il ne
#: peut pas voir qu'un offset a change de constante.
FORMULAS_0X18 = 0        # `Direct(0)` -- ce que lit `AmountIsGreaterThanZero`
FORMULAS_0X20 = 1        # `Direct(1)` -- ce que lisent `AmountIsZero` ET `maxTargets` de 1247


@pytest.mark.parametrize("count, attendu", [(0, True), (1, False), (2, False), (7, False)])
def test_AmountIsZero_est_NOT_EqualOrGreater_UN_donc_count_EGAL_ZERO(count, attendu):
    """`op_LogicalNot( AmountIsEqualOrGreater(x, Direct(1)) )` = `NOT (1 <= x)` = `x == 0`."""
    assert AmountIsZero(Const(count)).should_trigger(None) is attendu
    # La MEME expression, ecrite avec les deux noeuds natifs separes : elle DOIT coincider.
    compose = Not(AmountIsEqualOrGreater(Const(count), Const(FORMULAS_0X20)))
    assert bool(compose.should_trigger(None)) is attendu


def test_CONTRE_CAS_la_lecture_REFUTEE_rend_un_verdict_DIFFERENT_sur_UN():
    """Sans ce cran, le test ci-dessus ne mesurerait rien : il faut que la lecture ECARTEE
    (`AmountIsGreaterAbilityTrigger`, comparateur `<`, donc `AmountIsZero` = `NOT (1 < x)` =
    `x <= 1`) donne un AUTRE verdict. Elle le donne, et exactement sur `x == 1` -- le regime meme
    que `probe_927 --solo` a mesure sur le natif."""
    refutee = {c: not (FORMULAS_0X20 < c) for c in (0, 1, 2)}          # `NOT (1 < x)` = `x <= 1`
    portee = {c: AmountIsZero(Const(c)).should_trigger(None) for c in (0, 1, 2)}
    assert refutee[1] != portee[1], (refutee, portee)
    assert refutee[0] == portee[0] and refutee[2] == portee[2], (
        "l'ecart doit etre ISOLE sur x == 1, sinon la mesure ne designe pas le comparateur")


def test_le_gate_de_1247_s_ouvre_des_UN_ennemi_adjacent():
    """`FuryOfTheAncientsAbility$$CreateTrigger` = `... & op_LogicalNot( AmountIsZero(sel) )`.
    Avec `AmountIsZero` = `count == 0`, le gate est `count >= 1` -- ce que le natif fait
    (`probe_927 --solo` : tuile adjacente a EXACTEMENT un ennemi, le natif FRAPPE)."""
    gate = lambda c: bool(Not(AmountIsZero(Const(c))).should_trigger(None))   # noqa: E731
    assert gate(0) is False
    assert gate(1) is True and gate(3) is True


def test_MAX_TARGETS_lit_le_MEME_champ_et_vaut_UN():
    """`ChainAttackDamage(maxTargets = <DSLFormulas+0x20>)` -- MEME champ que le `minAmount`
    d'`AmountIsZero`, et il vaut 1 des deux cotes. C'est ce que le residu croyait impossible."""
    assert FA.MAX_TARGETS == FORMULAS_0X20 == 1
