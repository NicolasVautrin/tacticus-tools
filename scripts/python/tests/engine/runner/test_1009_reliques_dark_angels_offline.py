"""#1009 -- CLIQUET OFFLINE des deux reliques DARK ANGELS (aucun runner, aucun RPC).

Ce que le test LIVE ne peut pas garder : la FORME des deux arbres natifs, les ORDINAUX ecrits au
site (un mirror regenere apres renumerotage redeviendrait vert sans que la valeur ecrite ait
suivi -- cf. la doctrine `probe_313`), et le tri-etat du noeud DSL neuf `IsSpecialActiveAbility`,
dont le canal ne se peuple que sur la voie ABILITY.

ASCII only.
"""
from __future__ import annotations

import os
import sys

_PYDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PYDIR not in sys.path:
    sys.path.insert(0, _PYDIR)

# `DECLENCHEUR` (#486-r15) -- purement OFFLINE, donc aucun chemin de harnais live.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/loki/monster_slayer_of_caliban.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/triggers/loki/relic_power_fist.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/entities/behaviours.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/damage_profile_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/runner/abilities/attack_type.py",
    ),
    "build": False,
    "toujours": False,
    "raison": (
        "Cliquet OFFLINE de #1009 : forme des deux arbres natifs, ordinaux FIGES a la conversion, "
        "appartenance aux trois registres et tri-etat d'`IsSpecialActiveAbility`. Aucun runner."),
}

import pytest                                                               # noqa: E402

from engine.dsl.base import Const, DslContext                               # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                  # noqa: E402
from engine.entities.behaviours import Maybe, Seq                           # noqa: E402
from engine.entities.damage_profile_type import DamageProfileType           # noqa: E402
from engine.entities.effect_type import EffectType                          # noqa: E402
from engine.entities.formulas import ConditionalAmount, Double              # noqa: E402
from engine.entities.selectors.accessors import Owner, Target               # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                     # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType     # noqa: E402
from engine.entities.triggers import IsSpecialActiveAbility                 # noqa: E402
from engine.runner.abilities.attack_type import NORMAL_ATTACK_KIND          # noqa: E402
from engine.runner.abilities.behaviours.effects import AddEffect            # noqa: E402
import engine.entities.effects.loki.monster_slayer_of_caliban as MSC        # noqa: E402
import engine.runner.operations.triggers.loki.relic_power_fist as RPF       # noqa: E402


# ---------------------------------------------------------------------------------------------
# ETAGE 1 -- les ORDINAUX ECRITS AU SITE, figes a la conversion (#270-r1-r1-r3)
# ---------------------------------------------------------------------------------------------
def test_les_ordinaux_ecrits_au_site_sont_ceux_du_build():
    """`probe_313` compare le MIRROR au BUILD : il redevient vert des qu'on regenere le mirror
    apres un renumerotage, alors que la valeur ECRITE au site, elle, a change. Ce test-ci garde
    l'ordinal MESURE sur `rnca9r7q6c` au moment de la conversion."""
    assert int(TriggeredAbilityType.MonsterSlayerOfCaliban) == 0x5f7 == 1527
    assert int(TriggeredAbilityType.RelicPowerFist) == 0x5ba == 1466
    assert int(EffectType.MonsterSlayerOfCaliban_ExtraDmg) == 0x603 == 1539
    assert int(EffectType.MonsterSlayerOfCaliban_ExtraBlock) == 0x604 == 1540
    assert int(EffectType.Pinned) == 0x429 == 1065
    assert int(EffectType.Stunned) == 0x48a == 1162
    assert int(DamageProfileType.Power) == 0xe == 14
    assert int(EventTriggerType.Attack) == 9
    assert int(UnitTrait.Vehicle) == 0x405 == 1029
    assert int(UnitTrait.BigTarget) == 0x3f9 == 1017
    assert int(NORMAL_ATTACK_KIND) == 0x3f5 == 1013


def test_les_memes_ordinaux_nomment_autre_chose_ailleurs():
    """CONTROLE : la confusion d'enum serait SILENCIEUSE. 1539/1540 sont des membres VALIDES de
    `TriggeredAbilityType` et y nomment autre chose -- donc l'appariement doit venir du NOM.

    (Ce test s'assertionne lui-meme non vide : un ensemble vide passerait pour vert.)"""
    communs = {v: TriggeredAbilityType(v).name
               for v in (1539, 1540)
               if v in TriggeredAbilityType._value2member_map_}
    assert communs, "aucun ordinal commun -- ce controle ne prouve plus rien"
    for v, nom in communs.items():
        assert nom != EffectType(v).name, (v, nom)


# ---------------------------------------------------------------------------------------------
# ETAGE 2 -- l'appartenance aux REGISTRES, et l'ORDRE d'execution du `op_BitwiseAnd`
# ---------------------------------------------------------------------------------------------
def test_les_deux_effets_sont_au_registre_dans_l_ordre_d_execution():
    """`ABILITY_INIT_OWNER_EFFECTS["MonsterSlayerOfCaliban"]` = `[ExtraDmg, ExtraBlock]`.

    L'ORDRE EST L'INVERSE DE L'ORDRE DE CONSTRUCTION du pseudo-C : le natif CONSTRUIT
    `AddExtraBlockEffectToOwner` d'abord, mais compose `op_BitwiseAnd(AddEffect, AddExtraBlock)`,
    et `CombinedBehaviour` execute GAUCHE puis DROITE. C'est exactement la faute que
    `VolummsMasterArtifice` a payee (#1001) -- ici sans observable, mais ecrite parce que LUE."""
    from engine.entities.effects.factory import (ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES)
    assert ABILITY_INIT_OWNER_EFFECTS["MonsterSlayerOfCaliban"] == [
        EffectType.MonsterSlayerOfCaliban_ExtraDmg.name,
        EffectType.MonsterSlayerOfCaliban_ExtraBlock.name]
    assert EFFECT_CLASSES[EffectType.MonsterSlayerOfCaliban_ExtraDmg.name] is \
        MSC.MonsterSlayerOfCalibanExtraDmgEffect
    assert EFFECT_CLASSES[EffectType.MonsterSlayerOfCaliban_ExtraBlock.name] is \
        MSC.MonsterSlayerOfCalibanExtraBlockEffect


def test_relic_power_fist_est_au_registre_des_reliques_et_nulle_part_ailleurs():
    """`RELIC_ABILITY_TRIGGERS` est indexe par le NOM gameconfig de l'ability. 1466 est une
    `TriggeredAbilityType` : elle n'entre NI dans `ABILITY_CLASSES`, NI dans `TARGETING_OPTIONS`,
    NI dans `ABILITY_ATTACK_TYPE`."""
    from engine.runner.operations.triggers.dispatch.registry import (
        ABILITY_TRIGGERS, RELIC_ABILITY_TRIGGERS)
    assert RELIC_ABILITY_TRIGGERS["RelicPowerFist"] == [RPF.RelicPowerFistAbility]
    assert "RelicPowerFist" not in ABILITY_TRIGGERS
    assert "MonsterSlayerOfCaliban" not in ABILITY_TRIGGERS
    # `ABILITY_CLASSES` / `ABILITY_ATTACK_TYPE` sont indexes par ORDINAL d'`ActiveAbilityType` :
    # les deux ids de #1009 sont des `TriggeredAbilityType` et n'y ont donc rien a faire.
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE
    for oid in (int(TriggeredAbilityType.RelicPowerFist),
                int(TriggeredAbilityType.MonsterSlayerOfCaliban)):
        assert oid not in ABILITY_CLASSES, (
            "%d est une TriggeredAbilityType : elle n'a rien a faire dans ABILITY_CLASSES" % oid)
        assert oid not in ABILITY_ATTACK_TYPE, oid


def test_l_ability_declare_son_vecteur_et_son_id():
    assert RPF.RelicPowerFistAbility.event_id == int(EventTriggerType.Attack) == 9
    assert RPF.RelicPowerFistAbility.TRIGGERED_ABILITY_ID == int(
        TriggeredAbilityType.RelicPowerFist)


# ---------------------------------------------------------------------------------------------
# ETAGE 3 -- la FORME de l'arbre de `RelicPowerFist`
# ---------------------------------------------------------------------------------------------
def test_l_arbre_est_deux_maybe_pinned_puis_stunned():
    """`op_BitwiseAnd( Maybe(AddEffect(Pinned), aFinal), Maybe(AddEffect(Stunned), bFinal) )`.

    L'ORDRE porte un observable REEL, contrairement a celui de `MonsterSlayerOfCaliban` :
    `MaybeBehaviour$$Execute` tire AVANT son enfant et `CombinedBehaviour` execute gauche puis
    droite, donc c'est `Pinned` qui consomme le PREMIER tirage. L'inverser desynchroniserait le
    PRNG pour tout le reste de la bataille."""
    t = RPF.relic_power_fist_behaviour_tree(36, 41)
    assert isinstance(t, Seq)
    gauche, droite = t.left, t.right
    assert isinstance(gauche, Maybe) and isinstance(droite, Maybe)
    assert isinstance(gauche.child, AddEffect) and gauche.child.effect_type == int(EffectType.Pinned)
    assert isinstance(droite.child, AddEffect) and droite.child.effect_type == int(EffectType.Stunned)
    # `AddEffect(..., source = Owner@<DSLSelectors+0x30>, targets = Target@<+0x60>, options ZEROEE)`
    for feuille in (gauche.child, droite.child):
        assert isinstance(feuille.target_sel, Target)
        assert isinstance(feuille.source_ref, Owner)
        assert feuille.duration_rounds is None, (
            "options ZEROEE -> aucune duree explicite -> DefaultAmountOfRounds")


def test_le_doublement_porte_sur_les_deux_chances():
    """`ConditionalAmount(IsSpecialActiveAbility, Double(chance), chance)`, construit DEUX fois sur
    le MEME noeud de condition. `Double(x) = x * 2`, SANS plafond a 100 (aucun `Min` dans l'arbre)."""
    t = RPF.relic_power_fist_behaviour_tree(36, 41)
    for maybe, attendu in ((t.left, 36), (t.right, 41)):
        f = maybe.chance
        assert isinstance(f, ConditionalAmount)
        assert isinstance(f.cond, IsSpecialActiveAbility)
        assert isinstance(f.a, Double) and isinstance(f.b, Const)
        assert f.b.evaluate(DslContext()) == attendu
        # voie NORMALE (canal vide) -> la branche FAUSSE ; voie ABILITY -> la branche VRAIE.
        assert f.evaluate(DslContext()) == attendu
        assert f.evaluate(DslContext(attack_ability_type=1234)) == attendu * 2
    # Pas de plafond : au palier 10 (`chance = 50`) une active porte 100 %.
    t50 = RPF.relic_power_fist_behaviour_tree(50, 50)
    assert t50.left.chance.evaluate(DslContext(attack_ability_type=1234)) == 100


def test_les_deux_variables_sont_lues_separement():
    """`chance` (0x3a) et `chance_2` (0x3b) sont DEUX `AbilityVariableType`. Le gameconfig leur
    donne aujourd'hui les memes dix paliers ; les fusionner marcherait par accident."""
    assert RPF.VAR_CHANCE == "chance" and RPF.VAR_CHANCE_2 == "chance_2"
    t = RPF.relic_power_fist_behaviour_tree(11, 22)
    assert t.left.chance.b.evaluate(DslContext()) == 11
    assert t.right.chance.b.evaluate(DslContext()) == 22


# ---------------------------------------------------------------------------------------------
# ETAGE 4 -- le noeud DSL NEUF `IsSpecialActiveAbility`, et son TRI-ETAT
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind,attendu", [
    (None, False),                       # canal VIDE -> `IsActiveAbilityTrigger` rend false
    (int(NORMAL_ATTACK_KIND), False),    # `& !<TypeB>(sel)` : l'attaque NORMALE n'est pas speciale
    (1234, True),                        # une active quelconque
])
def test_is_special_active_ability(kind, attendu):
    assert IsSpecialActiveAbility().should_trigger(DslContext(attack_ability_type=kind)) is attendu


# ---------------------------------------------------------------------------------------------
# ETAGE 5 -- le gate de trait de `MonsterSlayerOfCaliban_ExtraDmg`, hors capture
# ---------------------------------------------------------------------------------------------
def test_le_gate_de_trait_est_un_ou_des_deux_traits():
    """`HasTrait(Target, Vehicle) | HasTrait(Target, BigTarget)` -- et RIEN d'autre : ni
    `IsMeleeAttack`, ni `IsNormalAttack` (contraste `BeastSlayer_ExtraDmgEffect`, meme paire de
    traits)."""
    assert MSC.MONSTER_TARGET_TRAITS == frozenset({UnitTrait.Vehicle.name, UnitTrait.BigTarget.name})
    eff = MSC.MonsterSlayerOfCalibanExtraDmgEffect(
        name=EffectType.MonsterSlayerOfCaliban_ExtraDmg.name,
        effect_type=int(EffectType.MonsterSlayerOfCaliban_ExtraDmg), ability_level=3)
    for traits in (frozenset({"Vehicle"}), frozenset({"BigTarget"}),
                   frozenset({"Vehicle", "BigTarget"})):
        for ranged in (False, True, None):
            b = eff.create_effect_damage_bonus_for_attack(is_ranged=ranged, target_traits=traits)
            assert b is not None and b.kind == "Addition" and b.value == 543, (traits, ranged, b)
    assert eff.create_effect_damage_bonus_for_attack(is_ranged=False,
                                                     target_traits=frozenset({"Hero"})) is None
    assert eff.create_effect_damage_bonus_for_attack(is_ranged=False, target_traits=None) is None


def test_le_block_ne_lit_aucune_stat_du_defenseur():
    """`AddExtraBlockEffectToOwner(1540, Direct(blockChance), Direct(blockDmg), turns = null)` : les
    DEUX arguments sont des `Direct(<valeur de config>)`.

    Contraste LU, pas suppose : `BeastSlayer_ExtraBlock` a un `PercentageOf(FixedArmor)` et
    `Daemon_ExtraBlock` un `PercentageOf(Attack)` -- ce test garde que les deux parametres du port
    sont IGNORES ici."""
    eff = MSC.MonsterSlayerOfCalibanExtraBlockEffect(
        name=EffectType.MonsterSlayerOfCaliban_ExtraBlock.name,
        effect_type=int(EffectType.MonsterSlayerOfCaliban_ExtraBlock), ability_level=3)
    a = eff.create_effect_block_source_for_defense()
    b = eff.create_effect_block_source_for_defense(defender_fixed_armor=99999,
                                                   defender_attack=99999)
    assert a is not None and (a.chance, a.amount, a.block_id) == (10, 1629, 1540)
    assert (b.chance, b.amount, b.block_id) == (a.chance, a.amount, a.block_id)


def test_le_palier_de_relique_et_le_palier_clampe_different():
    """Le montage ne discrimine QUE si les deux paliers different -- ce test le VERIFIE au lieu de
    le supposer (le `blockChance`, lui, est CONSTANT sur les dix paliers, donc il ne discrimine
    rien et c'est dit)."""
    from engine.entities.effects.magnitude import ability_var
    for cle in ("extraDmg", "blockDmg"):
        v3 = ability_var("MonsterSlayerOfCaliban", cle, 3)
        v50 = ability_var("MonsterSlayerOfCaliban", cle, 50)      # clampe au dernier palier
        assert v3 != v50, (cle, v3, v50)
    assert ability_var("MonsterSlayerOfCaliban", "blockChance", 3) == \
        ability_var("MonsterSlayerOfCaliban", "blockChance", 50)
    for cle in ("chance", "chance_2"):
        assert ability_var("RelicPowerFist", cle, 3) != ability_var("RelicPowerFist", cle, 50)


# ---------------------------------------------------------------------------------------------
# ETAGE 6 -- le RE-BAKE du couple TERTIAIRE, et sa PORTEE STRICTE
# ---------------------------------------------------------------------------------------------
def test_le_rebake_ne_touche_que_les_effets_de_l_ability_tertiaire():
    """`snapshot._rebake_tertiary_owner_effects` (#1009) -- le mirror du bake natif
    (`AddEffectBehaviour$$DefaultEffectBuilder` copie l'`AbilityStateReference` dans
    `EffectComponent+0x18`).

    PORTEE : seuls les effets dont le NOM figure dans `ABILITY_INIT_OWNER_EFFECTS[<tertiaire de
    CETTE unite>]` sont reecrits. Un effet homonyme d'un autre canal, une unite sans relique, ou un
    `tertiary_ability_level` a 0 (= << verrouille >>) restent INTACTS."""
    from engine.entities.effects.factory import EffectFactory
    from engine.entities.effects_state import EffectsState
    from engine.entities.unit_context import UnitContext
    from engine.runner.components import StatsComponent
    from engine.runner.snapshot import _rebake_tertiary_owner_effects
    from engine.runner.state import State

    def _unite(state, uid, tert, lvl):
        ent = state.add_entity(uid)
        ctx = UnitContext(entity_id=uid, tertiary_ability=tert, tertiary_ability_level=lvl,
                          tertiary_ability_variables_multiplier=100, passive_ability_level=50)
        ent.add_component(StatsComponent(ctx=ctx))
        return ent

    def _effet(nom):
        e = EffectFactory.create({"name": nom, "effectType": int(EffectType[nom]), "remaining": 0},
                                 ability_variables_multiplier=180, ability_level=50)
        return e

    state = State()
    state.effects = EffectsState()
    _unite(state, 1, "MonsterSlayerOfCaliban", 3)      # relique EQUIPEE -> re-bake attendu
    _unite(state, 2, "MonsterSlayerOfCaliban", 0)      # niveau VERROUILLE -> intact
    _unite(state, 3, None, 0)                          # aucune relique -> intact
    for uid in (1, 2, 3):
        for nom in (EffectType.MonsterSlayerOfCaliban_ExtraDmg.name,
                    EffectType.MonsterSlayerOfCaliban_ExtraBlock.name,
                    EffectType.Pinned.name):
            state.effects.add_effect(uid, _effet(nom))

    n = _rebake_tertiary_owner_effects(state)
    assert n == 2, "le re-bake doit toucher EXACTEMENT les 2 owner-effets de l'unite 1 : %r" % n
    for eff in state.effects.by_unit[1]:
        if eff.name.startswith("MonsterSlayerOfCaliban"):
            assert (eff.ability_level, eff.ability_variables_multiplier) == (3, 100), eff.name
        else:                                          # `Pinned` n'est PAS de cette ability
            assert (eff.ability_level, eff.ability_variables_multiplier) == (50, 180), eff.name
    for uid in (2, 3):
        for eff in state.effects.by_unit[uid]:
            assert (eff.ability_level, eff.ability_variables_multiplier) == (50, 180), (uid, eff.name)
