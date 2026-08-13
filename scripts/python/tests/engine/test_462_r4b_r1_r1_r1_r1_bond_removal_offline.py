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
from engine.entities.selectors.tiles import Caster  # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                  # noqa: E402
from engine.runner.abilities.behaviours.effects import RemoveEffect  # noqa: E402
from engine.runner.operations.triggers.bond_removal import (                # noqa: E402
    BOND_REMOVAL_GATES, BondRemoveOnAdjacencyLost, BondRemoveOnBondedEntityDeath,
    BondRemoveOnRangeExceeded,
    bond_removal_tree, bond_removal_registry_entries, assert_pending_gate_consistency)
from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS  # noqa: E402

# La mesure, recopiee comme ATTENDU : `(classe native, a, b, c, IsExecutedIfOwnerDies)`.
# Rejeu : `python probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step declared` (a/b/c) et
# `--step pending` (le quatrieme virtuel, qui n'existe que sous `APendingAttackEffect`).
_MEASURED = {
    int(EffectType.Neuroparasite): (
        "IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect", True, None, False, None),
    int(EffectType.TunnelingHorror_PendingSummon): (
        "IdunBattle.Entities.Effects.Loki.TunnelingHorror_PendingSummonEffect",
        False, None, False, None),
    int(EffectType.HazeOfCorruption_DamageTransfer): (
        "IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect",
        True, None, False, None),
    # #462-r4b-r1-r1-r1-r1-c -- sous-famille `APendingAttackEffect` : le gate (a) y vaut
    # `NOT <klass+0x778> IsExecutedIfOwnerDies`. `--step valkyrielive` a CONFRONTE la valeur dans le
    # sens rare (bonde mort, effet ENCORE present).
    int(EffectType.ValkyrieStrike_Effect): (
        "IdunBattle.Entities.Effects.Loki.ValkyrieStrikeEffect", False, None, False, True),
    # #462-r4b-r1-r1-r1-r1-b -- le SEUL effet pose par le port qui arme (b) `get_Range`. Les DEUX
    # gates sont confrontes live : (b) par la geometrie du push, (a) par la mort du taunteur.
    int(EffectType.Taunted_OnlySpecificTargets): (
        "IdunBattle.Entities.Effects.TauntedEffect", True, 1, False, None),
    # Le SEUL effet de toute la famille qui arme (c) `get_Adjacent`, et il est POSE par le port
    # depuis que `HolyDuelAbility` (1050) est entree dans `ABILITY_CLASSES`. Mesure `--step
    # declared` du 2026-08-08 : `OWN=none` / `OWN=true` / `OWN=true`.
    int(EffectType.HolyDuel_Taunt): (
        "IdunBattle.Entities.Effects.Loki.HolyDuel_TauntEffect", True, None, True, None),
    # #552 -- le MIROIR du 27 : `MindControlAbility$$ExecuteBehaviour` pose 1367 sur l'ALLIE
    # taunteur, bonde a la CIBLE. §8.7 de la fiche #462-r4b classait cette classe << (b) arme a
    # `Nullable<int>(1)`, mais son `EffectType` n'est pas etabli et le port ne pose aucun de ces
    # effets >> : les deux verrous tombent avec le port de 1164 (l'`EffectType` vient du 2e
    # argument LITTERAL de l'`AddBondEffect`, `0x557`). Les trois virtuels RE-MESURES le
    # 2026-08-08 par `--step declared` : (a) true, (b) 1, (c) false.
    int(EffectType.MindControl_Taunter): (
        "Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.MindControl_TaunterEffect",
        True, 1, False, None),
    # #590-r3 -- l'effet 1209 pose par `AttemptedPossessionAbility$$ExecuteBehaviour` (1101,
    # `thousSorcerer`) ET repose par son PROPRE trigger de propagation
    # (`triggers/loki/attempted_possession.py`). `EffectType` etabli par le 2e argument LITTERAL de
    # l'`AddBondEffect` (`0x4b9`) apparie au NOM de la classe native, seule du binaire a le porter.
    # Les trois virtuels MESURES le 2026-08-13 par `--step declared` : `get_Range` OWN=none,
    # `get_Adjacent` OWN=false, `get_RemoveOnBondedEntityDeath` OWN=true. Un SEUL retrait s'arme.
    int(EffectType.AttemptedPossession_Possessed): (
        "IdunBattle.Entities.Effects.Loki.AttemptedPossession_PossessedEffect",
        True, None, False, None),
}


def test_table_matches_the_runtime_measurement():
    """Les virtuels, par effet. `native` est dans l'assertion : c'est le seul champ qui relie
    une valeur a la classe dont elle a ete lue, donc a la mesure re-jouable."""
    assert set(BOND_REMOVAL_GATES) == set(_MEASURED), "la table a change de PERIMETRE"
    for et, (native, a, b, c, owner_dies) in _MEASURED.items():
        g = BOND_REMOVAL_GATES[et]
        assert g.native == native, "effet %d : classe native" % et
        assert g.remove_on_bonded_entity_death is a, "effet %d : <+0x748> get_RemoveOnBondedEntityDeath" % et
        assert g.range == b, "effet %d : <+0x728> get_Range" % et
        assert g.adjacent is c, "effet %d : <+0x738> get_Adjacent" % et
        assert g.is_executed_if_owner_dies is owner_dies, (
            "effet %d : <+0x778> IsExecutedIfOwnerDies" % et)


def test_pending_gate_is_the_negation_of_the_fourth_virtual():
    """`APendingAttackEffect$$get_RemoveOnBondedEntityDeath` a pour corps `NOT <klass+0x778>()`.

    Les deux champs sont redondants EXPRES : sans ce garde, l'un pourrait deriver de l'autre au fil
    des editions et la table mentirait sans que rien ne rougisse. Le garde est joue ICI, et pas
    seulement a l'import, pour qu'une regression porte le nom d'un test."""
    assert_pending_gate_consistency()
    pend = [et for et, g in BOND_REMOVAL_GATES.items() if g.is_executed_if_owner_dies is not None]
    assert pend, "aucune entree de la sous-famille : le garde ne verifierait plus RIEN"
    for et in pend:
        g = BOND_REMOVAL_GATES[et]
        assert g.remove_on_bonded_entity_death is (not g.is_executed_if_owner_dies)


def test_pending_family_arms_neither_range_nor_adjacent():
    """`APendingAttackEffect` SURCHARGE `get_Range` (`Nullable` vide) et `get_Adjacent` (`false`)
    pour ses 20 derivees -- mesure `--step declared`, niveau `d1`. Ni (b) ni (c) n'y sont donc
    jamais armes, et une entree de la sous-famille qui en porterait un serait une valeur inventee."""
    for et, g in BOND_REMOVAL_GATES.items():
        if g.is_executed_if_owner_dies is None:
            continue
        assert g.range is None, "effet %d : (b) n'est arme sur AUCUNE derivee" % et
        assert g.adjacent is False, "effet %d : (c) n'est arme sur AUCUNE derivee" % et


def test_only_true_gates_are_wired():
    """Le cablage se DERIVE du gate. Un effet a `a=False` reste DOCUMENTE dans la table mais
    n'inscrit aucun trigger -- cote natif le `Triggered()` n'entre pas dans l'`ArraySet`."""
    wired = {et for et, cls in bond_removal_registry_entries()
             if cls is BondRemoveOnBondedEntityDeath}
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


# ================================================================================================
# #462-r4b-r1-r1-r1-r1-b -- (b) `get_Range`
# ================================================================================================
def test_range_trigger_listens_only_to_position_changed_2():
    """`On(0x1d = UnitPositionChanged_2)` est le SEUL `On()` de la conjonction (b) -- une classe qui
    ecouterait aussi les vecteurs de mort retirerait le bond pour la mauvaise raison, et le bras
    live ne le verrait pas (il tombe pour la bonne raison au meme moment)."""
    cls = BondRemoveOnRangeExceeded
    assert cls.event_id == int(EventTriggerType.UnitPositionChanged_2)
    assert not getattr(cls, "event_ids", ()), "(b) n'a qu'UN `On()`, pas d'`op_BitwiseOr`"


def test_range_trigger_is_wired_exactly_where_the_gate_has_a_value():
    """Deriver, pas ecrire : `range is not None` <=> le trigger (b) est inscrit. Un `Nullable` VIDE
    (`get_Range` de toutes les autres classes) ne construit AUCUN `Triggered()` cote natif."""
    wired = {et for et, cls in bond_removal_registry_entries()
             if cls is BondRemoveOnRangeExceeded}
    assert wired == {et for et, g in BOND_REMOVAL_GATES.items() if g.range is not None}
    assert wired, "aucune entree (b) : la garde ne verifierait plus RIEN"
    for et in wired:
        assert BondRemoveOnRangeExceeded in EFFECT_TRIGGERS.get(et, []), (
            "effet %d : (b) derive de la table mais absent d'EFFECT_TRIGGERS" % et)
    for et, g in BOND_REMOVAL_GATES.items():
        if g.range is None:
            assert BondRemoveOnRangeExceeded not in EFFECT_TRIGGERS.get(et, []), (
                "effet %d : (b) inscrit alors que `get_Range` est VIDE" % et)


def test_taunt_carries_both_triggers():
    """`Taunted_OnlySpecificTargets` arme (a) ET (b) : le natif ajoute alors DEUX `Triggered()`
    distincts a l'`ArraySet`, et le port doit inscrire les DEUX classes pour le meme effect_type."""
    et = int(EffectType.Taunted_OnlySpecificTargets)
    assert BOND_REMOVAL_GATES[et].remove_on_bonded_entity_death is True
    assert BOND_REMOVAL_GATES[et].range == 1
    inscrits = EFFECT_TRIGGERS.get(et, [])
    assert BondRemoveOnBondedEntityDeath in inscrits and BondRemoveOnRangeExceeded in inscrits


def test_adjacent_trigger_is_wired_for_every_effect_that_arms_it():
    """(c) `get_Adjacent`, l'INVERSE de ce que ce test gardait avant le port de 1050.

    L'ancien garde tenait un invariant CONDITIONNEL (« tant qu'aucun effet POSE ne l'arme, ne pas
    ecrire la classe ») et il a fait exactement son travail : il est tombe au moment ou
    `HolyDuelAbility` est entree dans `ABILITY_CLASSES`. La condition est levee, l'invariant se
    retourne : tout effet a `adjacent=True` DOIT etre cable, et il doit y en avoir AU MOINS UN
    (sinon ce test serait vacuement vert, le vice qu'il denoncait).

    Le cablage reste DERIVE de la table, jamais ecrit a la main."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    armes = [et for et, g in BOND_REMOVAL_GATES.items() if g.adjacent]
    assert armes, "aucun effet n'arme (c) : ce garde ne verifierait plus RIEN"
    assert int(EffectType.HolyDuel_Taunt) in armes
    # Le seul poseur de 1091 est l'ability 1050 : si elle sortait du registre, le trigger
    # redeviendrait vacuement vrai -- c'est l'autre sens de l'ancien garde, conserve.
    assert 1050 in ABILITY_CLASSES, (
        "`HolyDuelAbility` n'est plus dans `ABILITY_CLASSES` : plus rien ne pose 1091, donc "
        "`BondRemoveOnAdjacencyLost` redevient du code qu'aucun etat ne peut atteindre")
    wired = {et for et, cls in bond_removal_registry_entries()
             if cls is BondRemoveOnAdjacencyLost}
    assert wired == set(armes), "le cablage de (c) n'est pas derive de la table"
    for et in armes:
        assert BondRemoveOnAdjacencyLost in EFFECT_TRIGGERS.get(et, [])


# ================================================================================================
# La CASCADE de sous-effets -- `RemoveEffectOperation$$RemoveSubEffects`
# ================================================================================================
def _state_with_taunt():
    """Etat MINIMAL portant le composite 27 et ses trois enfants, lies par `parent_type`."""
    from engine.runner.state import State
    from engine.entities.effects_state import EffectsState
    from engine.entities.effects.factory import EffectFactory
    st = State()
    st.effects = EffectsState()
    st.effects.by_unit[7] = []
    parent = EffectFactory.create({"name": "Taunted_OnlySpecificTargets",
                                   "effectType": int(EffectType.Taunted_OnlySpecificTargets),
                                   "level": None, "remaining": 2, "source": 9})
    parent.target = 7
    st.effects.by_unit[7].append(parent)
    for spec in parent.sub_effects_on_apply():
        child = EffectFactory.create({"name": spec.name, "effectType": int(spec.effect_type),
                                      "level": None, "remaining": 2, "source": 9})
        child.target = 7
        child.parent_type = int(parent.effect_type)
        st.effects.by_unit[7].append(child)
    return st, parent


def test_removing_the_parent_removes_its_sub_effects():
    """`RemoveEffectOperation$$Execute` appelle `RemoveSubEffects` -- le retrait ANTICIPE d'un
    composite emporte ses enfants, exactement comme son expiration par le timer.

    MESURE qui l'a impose (2026-08-05) : le trigger (b) retirait le 27 et laissait `[25, 26, 1237]`
    sur la cible, la ou le natif rend une liste VIDE."""
    from engine.runner.operations.remove_effects import remove_effect_instance
    st, parent = _state_with_taunt()
    vivants = [e for e in st.effects.by_unit[7] if not e.consumed]
    assert len(vivants) == 4, "montage : le composite et ses trois enfants"
    assert remove_effect_instance(st, 7, parent) is True
    restants = sorted(int(e.effect_type) for e in st.effects.by_unit[7] if not e.consumed)
    assert restants == [], "les sous-effets ont survecu au retrait du parent : %s" % restants


def test_hydration_rebuilds_the_parent_link():
    """`snapshot._load_effect_parent_links` : sur un etat RECHARGE, les enfants arrivent orphelins
    (`parent_type` n'est ecrit que par la voie de pose) et les DEUX consommateurs du lien -- la
    cascade d'expiration et `RemoveSubEffects` -- deviennent muets. La reconstruction repart de la
    meme part DATA que la pose : `sub_effects_on_apply()`."""
    from engine.runner.snapshot import _load_effect_parent_links
    from engine.runner.operations.remove_effects import remove_effect_instance
    st, parent = _state_with_taunt()
    for e in st.effects.by_unit[7]:
        e.parent_type = None                    # etat << comme hydrate >> : aucun lien
    _load_effect_parent_links(st)
    liens = {int(e.effect_type): e.parent_type for e in st.effects.by_unit[7]}
    assert liens[int(EffectType.Taunted_OnlySpecificTargets)] is None, "le parent n'a pas de parent"
    for spec in parent.sub_effects_on_apply():
        assert liens[int(spec.effect_type)] == int(EffectType.Taunted_OnlySpecificTargets)
    remove_effect_instance(st, 7, parent)
    assert not [e for e in st.effects.by_unit[7] if not e.consumed]
