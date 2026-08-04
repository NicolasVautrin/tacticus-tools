"""#462-r4b-r1-r1-r1-r1 -- gardes OFFLINE du retrait herite d'`ABondEffect`.

Ce que ces gardes tiennent, et que le live ne tient PAS :

  * la TABLE `BOND_REMOVAL_GATES` -- ses trois valeurs par effet, telles que
    `probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step declared` les a mesurees. Une valeur qui
    derive silencieusement (ou un effet qu'on ajoute << par ressemblance de nom >>) casse le port
    de facon PERMISSIVE : un bond qui ne se retire plus, ou un bond qui se retire a tort ;
  * le CABLAGE derive -- seuls les effets a `remove_on_bonded_entity_death=True` entrent dans
    `EFFECT_TRIGGERS`, et `TunnelingHorror_PendingSummon` (a=False) N'Y ENTRE PAS. C'est le sens
    meme du virtuel : le Destroyer s'enfouit (`RemoveUnitFromItsTiles(Caster, true)` -> son bonde
    est RETIRE dans le cast qui pose le marqueur), et si le trigger etait construit le kit
    s'auto-detruirait ;
  * l'ARBRE du behaviour -- `bond_removal_tree` est une USINE justement pour etre inspectable
    comme OBJET. La lecon de #556 §3 : un garde qui lit le TEXTE d'`execute_behaviour` matche ses
    propres commentaires et ne peut pas rougir.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine.entities.effect_type import EffectType                          # noqa: E402
from engine.entities.selectors import Caster                                # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                  # noqa: E402
from engine.runner.abilities.behaviours import RemoveEffect                 # noqa: E402
from engine.runner.operations.triggers.bond_removal import (                # noqa: E402
    BOND_REMOVAL_GATES, BondRemoveOnBondedEntityDeath, bond_removal_tree,
    bond_removal_registry_entries)
from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS  # noqa: E402

# La mesure, recopiee comme ATTENDU : `(classe native, a, b, c)`.
# Rejeu : `python probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step declared`.
_MEASURED = {
    int(EffectType.Neuroparasite): (
        "IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect", True, None, False),
    int(EffectType.TunnelingHorror_PendingSummon): (
        "IdunBattle.Entities.Effects.Loki.TunnelingHorror_PendingSummonEffect", False, None, False),
    int(EffectType.HazeOfCorruption_DamageTransfer): (
        "IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect", True, None, False),
}


def test_table_matches_the_runtime_measurement():
    """Les trois virtuels, par effet. `native` est dans l'assertion : c'est le seul champ qui relie
    une valeur a la classe dont elle a ete lue, donc a la mesure re-jouable."""
    assert set(BOND_REMOVAL_GATES) == set(_MEASURED), "la table a change de PERIMETRE"
    for et, (native, a, b, c) in _MEASURED.items():
        g = BOND_REMOVAL_GATES[et]
        assert g.native == native, "effet %d : classe native" % et
        assert g.remove_on_bonded_entity_death is a, "effet %d : <+0x748> get_RemoveOnBondedEntityDeath" % et
        assert g.range == b, "effet %d : <+0x728> get_Range" % et
        assert g.adjacent is c, "effet %d : <+0x738> get_Adjacent" % et


def test_only_true_gates_are_wired():
    """Le cablage se DERIVE du gate. Un effet a `a=False` reste DOCUMENTE dans la table mais
    n'inscrit aucun trigger -- cote natif le `Triggered()` n'entre pas dans l'`ArraySet`."""
    wired = {et for et, _ in bond_removal_registry_entries()}
    assert wired == {et for et, g in BOND_REMOVAL_GATES.items()
                     if g.remove_on_bonded_entity_death}
    tunnel = int(EffectType.TunnelingHorror_PendingSummon)
    assert tunnel not in wired, "TunnelingHorror_PendingSummon ne DOIT PAS etre cable"
    assert BondRemoveOnBondedEntityDeath not in EFFECT_TRIGGERS.get(tunnel, []), (
        "le marqueur d'enfouissement serait detruit par le cast qui le pose")
    for et, g in BOND_REMOVAL_GATES.items():
        if g.remove_on_bonded_entity_death:
            assert BondRemoveOnBondedEntityDeath in EFFECT_TRIGGERS.get(et, []), (
                "effet %d cable dans la table mais absent d'EFFECT_TRIGGERS" % et)


def test_trigger_listens_to_both_death_vectors():
    """`On(2 = PreUnitDeath_2) | On(0x25 = UnitRemoved)` -- l'`op_BitwiseOr` natif de deux `On()`.
    Perdre `UnitRemoved` rendrait le port aveugle a tout despawn SANS mort (le cas exact de
    `TunnelingHorror`, et de toute eviction de plateau)."""
    cls = BondRemoveOnBondedEntityDeath
    assert cls.event_id == int(EventTriggerType.PreUnitDeath_2)
    assert set(cls.event_ids) == {int(EventTriggerType.PreUnitDeath_2),
                                  int(EventTriggerType.UnitRemoved)}


@pytest.mark.parametrize("et", sorted(BOND_REMOVAL_GATES))
def test_behaviour_tree_is_a_removeeffect_on_the_carrier(et):
    """`RemoveEffect(Effect@DSLSelectors+0x38)` -- feuille DSL au-dessus de l'Operation
    `RemoveEffectOperation`. Inspecte comme OBJET (usine), jamais par le texte du source."""
    tree = bond_removal_tree(et)
    assert isinstance(tree, RemoveEffect)
    assert tree.effect_type == et
    assert isinstance(tree.target_sel, Caster), (
        "le selecteur doit designer le PORTEUR de l'effet, pas le bonde")
