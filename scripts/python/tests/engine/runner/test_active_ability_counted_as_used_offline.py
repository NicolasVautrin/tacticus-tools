"""SEUIL de `IsActiveAbilityCountedAsUsed` (#295) -- mirror OFFLINE pur, aucune session requise.

Verrouille le comparateur du volet `left` de
`IdunBattleLogic.Entities.DSLTriggers$$IsActiveAbilityCountedAsUsed(df, isPreAbilityTrigger=false)` :

    left = AmountIsGreater( amount = TotalActiveAbilityUsed(unit, ability),
                            minAmount = DSLFormulas@+0x20 = Direct(1) )
           & IsAbilityCountedOnlyOnce(ability)
    return !IsNormalAttackOrHealOrRepair(ability) & !left

La classe reellement instanciee est `IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger`
(famille **STRICTE**) -- etabli par le POINTEUR DE CLASSE charge avant `il2cpp_object_new`, jamais par
le nom du `.ctor` (corps trivial DEDUPLIQUE, cf. #293), et corrobore par l'encodage `setg` de son
`ShouldTrigger` contre le `setge` d'`AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger`. Son ctor
etant `(this, amount, minAmount)` avec `[this+0x18] = amount` / `[this+0x20] = minAmount`, et
`ShouldTrigger` rendant `minAmount < amount`, le predicat vaut **`used > 1`** -- et non `used >= 1`,
qui bloquait UNE utilisation trop tot (une ability << comptee une seule fois par bataille >> n'aurait
alors JAMAIS compte). Face native re-derivable :
`python scripts/python/probe_295_active_ability_counted_as_used.py`.

POURQUOI CE TEST EXISTE, ET POURQUOI IL EST LE SEUL : le canal est **INERTE** en bataille --
`State` n'expose aucun `total_active_ability_used` (absent de ses `__slots__`), donc
`_total_active_ability_used` rend TOUJOURS `None` et la comparaison de seuil n'est jamais atteinte.
AUCUN test live ne peut donc changer de couleur sur ce seuil : ce fichier est la seule garde qui
l'exerce, en INJECTANT le compteur par une sous-classe de `State`. Le jour ou le compteur sera cable,
c'est ce fichier qui empechera l'ecart de revenir en silence.

ASCII only (cp1252).
"""
from __future__ import annotations

from typing import Optional

from engine.runner.state import State
from engine.runner.operations.triggers.loki.fuelled_by_fury import (
    ABILITY_COUNTED_ONCE_PER_BATTLE, COUNTED_AS_USED_THRESHOLD,
    is_active_ability_counted_as_used)
from engine.runner.abilities.attack_type import (
    REGULAR_ATTACK_ABILITY_TYPES, is_normal_attack)

CASTER = 1
# Une des DEUX seules valeurs pour lesquelles `IsAbilityCountedOnlyOnce` est VRAI, donc les seules ou
# le volet `left` peut mordre (mirror du HashSet statique `StaticBattleRules.ActiveAbility@+0x58`).
COUNTED_ONCE = 0x45e            # 1118 DoctrinaImperatives
# Une ability quelconque HORS de ce set : `IsAbilityCountedOnlyOnce` FAUX -> `left` FAUX quel que
# soit le compteur.
NOT_COUNTED_ONCE = 0x4e3        # 1251 FuelledByFury (passif, hors du HashSet)
NORMAL_ATTACK = 0x011           # 17 NormalAttack -- le volet `!right`


class _StateWithCounter(State):
    """`State` + le canal `total_active_ability_used(unit, ability)` que le port lit par `getattr`.

    Le vrai `State` ne l'a PAS (il n'est pas dans ses `__slots__`) : c'est precisement ce qui rend le
    seuil inerte en bataille. On l'INJECTE ici pour exercer les deux cotes du seuil -- c'est la seule
    facon d'atteindre la branche."""
    __slots__ = ("_used",)

    def __init__(self, used: Optional[int]):
        super().__init__()
        self._used = used

    def total_active_ability_used(self, unit_id, ability_type):
        return self._used


def test_threshold_literal_is_the_cached_direct_one():
    """`minAmount` = le noeud constant `DSLFormulas@+0x20` = `Direct(1)` (branche
    `isPreAbilityTrigger = false`, la SEULE mirroree). L'autre branche (`+0x18 = Direct(0)`) n'est pas
    portee : aucun appelant du port ne la demande."""
    assert COUNTED_AS_USED_THRESHOLD == 1, (
        "seuil natif = DSLFormulas@+0x20 = Direct(1) (branche isPreAbilityTrigger=false)")


def test_used_one_still_counts_strict_comparator():
    """CENTRE DU CAS -- `used = 1` : `1 > 1` est FAUX -> `left` FAUX -> l'ability COMPTE.

    C'est le cote du seuil qu'un comparateur INCLUSIF (`>= 1`) inverserait : il refuserait des la
    PREMIERE utilisation, et une ability << comptee une seule fois par bataille >> ne compterait
    alors jamais."""
    st = _StateWithCounter(1)
    assert is_active_ability_counted_as_used(st, CASTER, COUNTED_ONCE) is True, (
        "used=1 : le comparateur natif est STRICT (minAmount < amount) -> l'ability compte encore")


def test_used_two_no_longer_counts():
    """AUTRE COTE DU SEUIL -- `used = 2` : `1 < 2` -> `left` VRAI -> l'ability NE compte PLUS.
    Sans cette assertion, un port qui ne comparerait rien du tout passerait le test precedent."""
    st = _StateWithCounter(2)
    assert is_active_ability_counted_as_used(st, CASTER, COUNTED_ONCE) is False, (
        "used=2 : depasse le seuil Direct(1) -> deja comptee, ne recompte pas")


def test_used_zero_counts_and_high_counter_does_not():
    """Monotonie de part et d'autre : 0 compte, 3 ne compte pas."""
    assert is_active_ability_counted_as_used(_StateWithCounter(0), CASTER, COUNTED_ONCE) is True
    assert is_active_ability_counted_as_used(_StateWithCounter(3), CASTER, COUNTED_ONCE) is False


def test_second_factor_gates_the_whole_left():
    """`IsAbilityCountedOnlyOnce(ability)` est le SECOND facteur du `left` : hors du HashSet statique,
    le compteur n'a aucun effet, si haut soit-il."""
    assert NOT_COUNTED_ONCE not in ABILITY_COUNTED_ONCE_PER_BATTLE
    st = _StateWithCounter(99)
    assert is_active_ability_counted_as_used(st, CASTER, NOT_COUNTED_ONCE) is True, (
        "hors du HashSet ActiveAbility@+0x58 : IsAbilityCountedOnlyOnce FAUX -> left FAUX")


def test_counter_absent_degrades_to_counting():
    """CANAL INERTE : un `State` NU n'a pas de `total_active_ability_used` -> `None` ->
    degradation nommee << l'ability COMPTE >>. C'est l'etat de TOUTE bataille aujourd'hui, et c'est
    pourquoi aucun test live ne couvre le seuil."""
    assert not hasattr(State(), "total_active_ability_used"), (
        "si State expose ce canal, le seuil n'est plus inerte : cabler le compteur pour de vrai")
    assert is_active_ability_counted_as_used(State(), CASTER, COUNTED_ONCE) is True


def test_normal_attack_never_counts():
    """`!right` : l'attaque NORMALE est une active ability cote natif et emet `On(0xe)` comme les
    autres -- c'est ce volet qui l'ecarte, independamment du compteur."""
    assert NORMAL_ATTACK in REGULAR_ATTACK_ABILITY_TYPES and is_normal_attack(NORMAL_ATTACK)
    assert is_active_ability_counted_as_used(_StateWithCounter(0), CASTER, NORMAL_ATTACK) is False


def test_no_triggering_ability_resolves_to_false():
    """Aucune ability declenchante : aucun noeud du DSL ne resout -> le gate refuse."""
    assert is_active_ability_counted_as_used(_StateWithCounter(0), CASTER, None) is False
