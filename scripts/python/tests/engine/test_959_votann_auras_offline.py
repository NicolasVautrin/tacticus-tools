"""#959 OFFLINE -- les deux passifs d'AURA Leagues of Votann : `GrimEfficiency` (1490,
`votanUthar`) et `PredictiveGuidance` (1525, `votanMemnyr`).

Ce fichier GARDE ce que le decompile a dit, sans session : les ordinaux ECRITS AUX SITES, le
cablage des registres, et le comportement des gates de chaque classe. La confrontation au natif
vit dans `tests/engine/runner/test_959_votann_auras_live.py` (via
`probe_959_grim_efficiency_predictive_guidance.py`).

Pourquoi FIGER les ordinaux ici alors que `probe_313` garde deja les mirrors : `probe_313` compare
le MIRROR au BUILD, donc il redevient vert des qu'on regenere le mirror apres un renumerotage --
alors que la valeur ECRITE au site, elle, a change. Meme cran que
`test_270r1r1r3_role_enum_offline.py` etage 1.
"""
from __future__ import annotations

#: Perimetre : le module porteur des cinq classes, les registres qui les font exister, l'accesseur
#: de magnitude, et TOUS les mirrors d'enum dont un ordinal est fige ci-dessous. `gameconfig.json`
#: entre au perimetre parce que les DEUX constantes `range` en sortent.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/loki/votann.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/entities/effects/aura_selectors.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/entities/unit_faction.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/entities/stats.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "data/symbols/*/gameconfig.json",
    ),
    "build": True,
    "toujours": False,
    "raison": "Offline : fige les ordinaux ECRITS AUX SITES (que `probe_313` ne voit pas -- il "
              "compare le mirror au build, pas le site), le cablage des DEUX registres, et les "
              "QUATRE ecarts mesures entre les trois moities de `PredictiveGuidance` (filtre "
              "`UnitFlag.Moved`, `extraDmg` vs `extraDmg_2`, `IsMechanical` absent d'ExtraHits, "
              "`ConfigConst` vs `ConfigVar`) -- une recopie d'une moitie sur l'autre les "
              "effacerait toutes. Il garde aussi que ces passifs ne sont PAS des "
              "`ABILITY_TRIGGERS` : s'y tromper donne un passif qui ne se pose jamais.",
}

import pytest        # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)

from engine.entities.ability_constant_type import AbilityConstantType        # noqa: E402
from engine.entities.effect_type import EffectType
from engine.entities.effects import factory as F
from engine.entities.effects.loki import votann as V
from engine.entities.stats import StatType
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.entities.unit_faction import UnitFaction


# --------------------------------------------------------------------------- 1. les ORDINAUX LUS
def test_ordinaux_lus_au_decompile():
    """Chaque littéral vient d'une LECTURE, citée dans `votann.py` :
    `.ctor` relus a l'assembleur, `CreateBehaviour` / `CreateActiveCondition` au pseudo-C."""
    assert int(TriggeredAbilityType.GrimEfficiency) == 0x5d2 == 1490
    assert int(TriggeredAbilityType.PredictiveGuidance) == 0x5f5 == 1525
    assert int(EffectType.GrimEfficiency_ExtraArmor) == 0x5cf == 1487
    assert int(EffectType.GrimEfficiency_ExtraPierce) == 0x5d0 == 1488
    assert int(EffectType.PredictiveGuidance_Melee) == 0x5ff == 1535
    assert int(EffectType.PredictiveGuidance_Ranged) == 0x600 == 1536
    assert int(EffectType.PredictiveGuidance_ExtraHits) == 0x601 == 1537
    # Les DEUX marqueurs de stance que lisent les `CreateActiveCondition` de GrimEfficiency.
    assert int(EffectType.PrioritisedEfficiency_HostileAcquisition_Stance) == 0x5c7 == 1479
    assert int(EffectType.PrioritisedEfficiency_FortifyTakeover_Stance) == 0x5c8 == 1480
    # `AddDynamicStatModifierEffectToOwner(..., statType = <ord>, ...)` -- du BEHAVIOUR.
    assert int(StatType.FIXED_ARMOR) == 0x10 == 16
    assert int(StatType.EXTRA_PIERCE) == 0x1a == 26
    # `ConfigConst(<ord>, config)` des selecteurs / du bonus de coups.
    assert int(AbilityConstantType.range) == 0x16 == 22
    assert int(AbilityConstantType.extraHits) == 0x64 == 100
    # `HasFaction(Caster, 0x14, 3)` / `IsMechanical(Caster, 0)`.
    assert int(UnitFaction.LeaguesOfVotann) == 0x14 == 20
    assert int(UnitTrait.Mechanical) == 5


def test_qualification_des_enums_le_meme_ordinal_nomme_autre_chose():
    """Le discriminant est l'ACCESSEUR, jamais l'ordinal -- et le contrôle assertionne son propre
    NON-VIDE (un ensemble vide passerait pour vert)."""
    from engine.entities.active_ability_type import ActiveAbilityType
    collisions = []
    for ord_, tri in ((1490, "GrimEfficiency"), (1525, "PredictiveGuidance")):
        autre = EffectType(ord_).name if ord_ in EffectType._value2member_map_ else None
        if autre is not None and autre != tri:
            collisions.append((ord_, tri, "EffectType", autre))
        act = (ActiveAbilityType(ord_).name
               if ord_ in ActiveAbilityType._value2member_map_ else None)
        if act is not None and act != tri:
            collisions.append((ord_, tri, "ActiveAbilityType", act))
    assert collisions, ("aucune collision trouvee -- ce controle ne mesure alors RIEN "
                        "et son vert serait un artefact")


# ------------------------------------------------------------------- 2. le CABLAGE des registres
def test_registres_les_cinq_effets_et_les_deux_poses_a_l_init():
    assert F.EFFECT_CLASSES["GrimEfficiency_ExtraArmor"] is V.GrimEfficiencyExtraArmorEffect
    assert F.EFFECT_CLASSES["GrimEfficiency_ExtraPierce"] is V.GrimEfficiencyExtraPierceEffect
    assert F.EFFECT_CLASSES["PredictiveGuidance_Melee"] is V.PredictiveGuidanceMeleeEffect
    assert F.EFFECT_CLASSES["PredictiveGuidance_Ranged"] is V.PredictiveGuidanceRangedEffect
    assert F.EFFECT_CLASSES["PredictiveGuidance_ExtraHits"] is V.PredictiveGuidanceExtraHitsEffect
    # ORDRE = celui des `op_BitwiseAnd` du `CreateBehaviour` natif.
    assert F.ABILITY_INIT_OWNER_EFFECTS["GrimEfficiency"] == [
        "GrimEfficiency_ExtraArmor", "GrimEfficiency_ExtraPierce"]
    assert F.ABILITY_INIT_OWNER_EFFECTS["PredictiveGuidance"] == [
        "PredictiveGuidance_Melee", "PredictiveGuidance_Ranged", "PredictiveGuidance_ExtraHits"]


def test_ces_passifs_ne_sont_PAS_des_ABILITY_TRIGGERS():
    """Leur `CreateTrigger` (corps ICF partage avec `WayOfTheShortBlade_InitAbility`) est
    `OnOwnerSpecificAbilityInit` : un passif d'INIT. L'inscrire en `ABILITY_TRIGGERS` donnerait
    un passif qui ne se pose JAMAIS."""
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    assert "GrimEfficiency" not in ABILITY_TRIGGERS
    assert "PredictiveGuidance" not in ABILITY_TRIGGERS


# --------------------------------------------------- 3. GrimEfficiency : constantes et condition
def test_grim_efficiency_les_trois_constantes_de_chaque_classe():
    a, p = V.GrimEfficiencyExtraArmorEffect, V.GrimEfficiencyExtraPierceEffect
    assert (a._VAR, a._STAT, a._STANCE) == (
        "extraArmor", int(StatType.FIXED_ARMOR),
        int(EffectType.PrioritisedEfficiency_HostileAcquisition_Stance))
    assert (p._VAR, p._STAT, p._STANCE) == (
        "extraPierceRatio", int(StatType.EXTRA_PIERCE),
        int(EffectType.PrioritisedEfficiency_FortifyTakeover_Stance))
    # Les deux moities different sur les TROIS axes : rien n'a ete recopie de l'une sur l'autre.
    assert a._VAR != p._VAR and a._STAT != p._STAT and a._STANCE != p._STANCE
    # Sans ce drapeau, l'instance SEEDEE de la stance NON courante contribuerait aussi.
    assert a.active_condition_ported is True and p.active_condition_ported is True


@pytest.mark.parametrize("klass,stance_presente,attendu", [
    (V.GrimEfficiencyExtraArmorEffect, 1479, True),
    (V.GrimEfficiencyExtraArmorEffect, 1480, False),
    (V.GrimEfficiencyExtraPierceEffect, 1480, True),
    (V.GrimEfficiencyExtraPierceEffect, 1479, False),
])
def test_grim_efficiency_is_active_lit_la_stance_de_la_SOURCE(klass, stance_presente, attendu):
    """`HasEffect(EffectSource(Effect), <stance>, onlyActive = false, Both)` -- les deux auras
    PARTITIONNENT les stances : jamais actives ensemble."""
    eff = klass(name=klass.__name__, effect_type=None)
    eff.source = 42
    us = {"owner_id": 42,
          "has_effect_on": lambda uid, et: uid == 42 and et == stance_presente}
    assert eff.is_active(us) is attendu


def test_grim_efficiency_is_active_degrade_en_VRAI_sans_la_cle():
    """Tri-etat : cle absente = donnee non threadee -> « present == actif », jamais un FAUX
    (le canal live actif-only ne publie deja que l'aura de la stance courante)."""
    eff = V.GrimEfficiencyExtraArmorEffect(name="x", effect_type=None)
    assert eff.is_active(None) is True
    assert eff.is_active({}) is True


def test_grim_efficiency_magnitude_sans_ability_state_rend_None():
    """`ConfigVar` sans `AbilityState` -> None (« present != applique »), jamais 0."""
    eff = V.GrimEfficiencyExtraArmorEffect(name="x", effect_type=None)
    eff.ability_level = None
    assert eff.aura_stat_modification_amount() is None


def test_grim_efficiency_range_vient_de_la_CONSTANTE():
    assert V.grim_efficiency_range() == 2


# ----------------------------------------------- 4. PredictiveGuidance : les quatre ECARTS mesures
def test_predictive_guidance_les_quatre_ecarts_entre_les_trois_moities():
    m, r = V.PredictiveGuidanceMeleeEffect, V.PredictiveGuidanceRangedEffect
    h = V.PredictiveGuidanceExtraHitsEffect
    # (1) le filtre `UnitFlag.Moved` : ABSENT / PRESENT / INVERSE.
    assert m._REQUIRE_MOVED is False and r._REQUIRE_MOVED is True
    assert not hasattr(h, "_REQUIRE_MOVED")
    # (2) DEUX cles de config distinctes -- pas la meme, meme si les valeurs coincident aujourd'hui.
    assert m._VAR == "extraDmg" and r._VAR == "extraDmg_2" and m._VAR != r._VAR
    # (3) melee/ranged sont gates sur la NATURE du coup, en sens INVERSE.
    assert m._IS_MELEE is True and r._IS_MELEE is False
    # (4) ExtraHits lit une CONSTANTE, les deux autres une VARIABLE de niveau.
    assert h._CONST is AbilityConstantType.extraHits
    # La face native est celle du SLOT (`CreateEffectDamageBonusForAttack`), pas celle du porteur.
    assert m.AURA_DEFENSE_MALUS_NATIVE_FACE == "attacker"
    assert r.AURA_DEFENSE_MALUS_NATIVE_FACE == "attacker"


def _ctx(**kw):
    base = {"owner_id": 1, "owner_team": 10, "owner_pos": (0, 0),
            "tgt_id": 2, "tgt_team": 20, "t_pos": (0, 2), "tgt_has_moved": False,
            "att_id": 3, "att_team": 10, "att_faction": "LeaguesOfVotann",
            "att_traits": (), "is_melee": True}
    base.update(kw)
    return base


def _melee(level=50):
    e = V.PredictiveGuidanceMeleeEffect(name="PredictiveGuidance_Melee", effect_type=None)
    e.ability_level = level
    return e


def test_predictive_guidance_melee_le_cas_NOMINAL_mord():
    assert _melee().create_aura_defense_damage_malus_for_ally(_ctx()) is not None


@pytest.mark.parametrize("patch,pourquoi", [
    ({"att_id": 1}, "!AreEqual(EffectSource, Caster) -- la SOURCE ne se buffe pas"),
    ({"att_faction": "Ultramarines"}, "HasFaction(LeaguesOfVotann) faux et pas Mechanical"),
    ({"tgt_has_moved": True}, "UnitsWithoutFlag(Moved) : la cible a bouge"),
    ({"tgt_has_moved": None}, "flag non mesure -> gate FERME (degradation restrictive)"),
    ({"is_melee": False}, "IsMeleeAttack faux"),
    ({"is_melee": None}, "nature non declaree -> les DEUX predicats natifs sont faux"),
    ({"t_pos": (0, 5)}, "hors du rayon `SurroundingEnemies(range)`"),
    ({"tgt_team": 10}, "`SurroundingEnemies` : meme equipe que le porteur"),
    ({"att_faction": None}, "faction inconnue -> le membre se tait"),
])
def test_predictive_guidance_melee_chaque_conjoint_MORD(patch, pourquoi):
    assert _melee().create_aura_defense_damage_malus_for_ally(_ctx(**patch)) is None, pourquoi


def test_predictive_guidance_melee_le_membre_MECHANICAL_suffit_seul():
    """`IsMechanical(Caster, Any) | HasFaction(Caster, LoV, 3)` -- un attaquant Mechanical NON
    Leagues of Votann recoit le bonus de DEGAT."""
    c = _ctx(att_faction="AdeptusMechanicus", att_traits=(UnitTrait.Mechanical.name,))
    assert _melee().create_aura_defense_damage_malus_for_ally(c) is not None


def test_predictive_guidance_ranged_lit_l_AUTRE_cle_et_l_AUTRE_flag():
    e = V.PredictiveGuidanceRangedEffect(name="PredictiveGuidance_Ranged", effect_type=None)
    e.ability_level = 50
    assert e.create_aura_defense_damage_malus_for_ally(
        _ctx(is_melee=False, tgt_has_moved=True)) is not None
    # cible IMMOBILE -> `UnitsWithFlag(Moved)` ne la selectionne pas
    assert e.create_aura_defense_damage_malus_for_ally(
        _ctx(is_melee=False, tgt_has_moved=False)) is None


def test_predictive_guidance_extrahits_n_a_PAS_le_membre_MECHANICAL():
    """LE piege de la tranche : `ExtraHits` exige `HasFaction(LoV)` SEUL. Un Mechanical non-LoV
    recoit le bonus de DEGAT (test ci-dessus) mais PAS le coup supplementaire."""
    h = V.PredictiveGuidanceExtraHitsEffect(name="PredictiveGuidance_ExtraHits", effect_type=None)
    mech = _ctx(att_faction="AdeptusMechanicus", att_traits=(UnitTrait.Mechanical.name,))
    assert h.create_aura_hits_malus_for_defense(mech) is None
    lov = h.create_aura_hits_malus_for_defense(_ctx())
    assert lov is not None and lov.kind == "Addition" and lov.value == 1


def test_predictive_guidance_extrahits_ignore_le_flag_Moved():
    """Son selecteur est l'aura NUE : aucun `UnitsWith[out]Flag`. Les DEUX etats doivent mordre --
    y compris `None`, qui ferme les deux autres."""
    h = V.PredictiveGuidanceExtraHitsEffect(name="PredictiveGuidance_ExtraHits", effect_type=None)
    for moved in (False, True, None):
        assert h.create_aura_hits_malus_for_defense(_ctx(tgt_has_moved=moved)) is not None


def test_predictive_guidance_range_vient_de_la_CONSTANTE():
    assert V.predictive_guidance_range() == 2
