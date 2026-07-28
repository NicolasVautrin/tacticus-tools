"""Re-derive le gisement [-D] : abilities dont la face DECISION est portee mais
dont la face COMBAT est un NO-OP (absente de `ABILITY_CLASSES`).

Croise les TROIS registres de decision :
  - `engine.playbook.base.REGISTRY`                       (Comparable, cle = id)
  - `engine.playbook.noncomparable.PLAYBOOKS`             (NonComparable, cle = id)
  - `engine.entities.abilities.active_ability._SPECIAL_ABILITY_CLASSES`
    (sous-classes `AActiveAbility` a formule de coups/AoE propre, cle = NOM ->
     re-mappee en id via `ActiveAbilityType`)

Croiser seulement les deux premiers rate des items (mesure de l'inventaire, §2.1).

Usage: python scripts/python/probe_decision_noop_gap.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from engine.runner.abilities.handler import ABILITY_CLASSES  # noqa: E402
from engine.playbook.base import REGISTRY  # noqa: E402
from engine.playbook.noncomparable import PLAYBOOKS  # noqa: E402
from engine.entities.abilities.active_ability import _SPECIAL_ABILITY_CLASSES  # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402


def _by_name(name):
    return int(getattr(ActiveAbilityType, name))


def main():
    exec_ids = {int(k) for k in ABILITY_CLASSES}
    dec_cmp = {int(k) for k in REGISTRY}
    dec_nc = {int(k) for k in PLAYBOOKS}
    dec_sp = {_by_name(n) for n in _SPECIAL_ABILITY_CLASSES}
    decision = dec_cmp | dec_nc | dec_sp

    gap = sorted(decision - exec_ids)

    print("exec (ABILITY_CLASSES)              = %d" % len(exec_ids))
    print("decision REGISTRY (Comparable)      = %d" % len(dec_cmp))
    print("decision PLAYBOOKS (NonComparable)  = %d" % len(dec_nc))
    print("decision _SPECIAL_ABILITY_CLASSES   = %d" % len(dec_sp))
    print("decision (union des 3)              = %d" % len(decision))
    print("DECIDENT sans EXECUTER              = %d" % len(gap))
    for aid in gap:
        try:
            nm = ActiveAbilityType(aid).name
        except Exception:
            nm = "?"
        src = []
        if aid in dec_cmp:
            src.append("REGISTRY")
        if aid in dec_nc:
            src.append("PLAYBOOKS")
        if aid in dec_sp:
            src.append("SPECIAL")
        print("  %-5d %-26s [%s]" % (aid, nm, "+".join(src)))

    two_only = sorted((dec_cmp | dec_nc) - exec_ids)
    missed = sorted(set(gap) - set(two_only))
    if missed:
        print("(croiser 2 registres seulement rendrait %d et manquerait %s)"
              % (len(two_only), missed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
