"""#965 -- garde OFFLINE de l'ability `WhisperingWeb` (1554, `eldarLhykhis`).

Ce fichier garde la POSE (ce que la tranche livre) ET l'ABSENCE de la magnitude (ce qu'elle ne
livre pas, residu #965-r2). Le second point compte autant que le premier : sans lui, un relecteur
ne peut pas distinguer « pas encore porte » de « porte et nul ».

RE : `docs/rl/case-965-whispering-web-refusal-to-be-outdone.md`.
"""
from __future__ import annotations

import pytest

from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.ability_variable_type import AbilityVariableType
from engine.entities.effect_type import EffectType
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.runner.operations.triggers.loki import whispering_web as WW

#: Ce que ce fichier GARDE. Large exprès : l'etage 4 surveille une ABSENCE (l'effet 1579 non
#: porte), donc il doit se rejouer des que le registre d'effets bouge -- c'est precisement par la
#: qu'arriverait la magnitude qui perimerait ce garde.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/operations/triggers/loki/whispering_web.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        # l'etage 4 (a) : le jour ou "WhisperingWeb" entre ici, ce fichier DOIT rougir.
        "scripts/python/engine/entities/effects/factory.py",
        # le foyer du blocage #965-r2 : si `hit_index` y est threade, la magnitude devient portable.
        "scripts/python/engine/runner/damage_model.py",
        # les mirrors d'enum dont l'etage 0 fige les ordinaux ECRITS AU SITE.
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
    ),
    "build": False,
    "toujours": False,
    "raison": (
        "Deux chemins sortent de la fermeture d'imports de ce fichier et sont declares EXPRES : "
        "`effects/factory.py` et `runner/damage_model.py`. L'etage 4 garde une ABSENCE (l'effet "
        "1579 non porte, residu #965-r2) -- or une absence ne se perime pas par ce que le fichier "
        "IMPORTE, mais par ce qu'une AUTRE tranche AJOUTE : l'entree `WhisperingWeb` au registre "
        "d'effets, ou le threading de `hit_index` dans le pipeline de degat qui leverait le "
        "blocage. Un declencheur derive des seuls imports serait ici un FAUX VERT exemplaire. "
        "Pas de `build` : les ordinaux sont figes en dur, sans lecture du dump."),
}


def test_etage0_ordinaux_du_site():
    """Les ordinaux ECRITS AU SITE (cf. l'etage 0 du garde jumeau : `probe_313` compare le mirror
    au build, pas la valeur que le port ecrit)."""
    assert int(TriggeredAbilityType.WhisperingWeb) == 1554        # 0x62a -- l'ABILITY
    assert int(EffectType.WhisperingWeb) == 1579                  # 0x62b -- l'EFFET
    assert WW.WHISPERING_WEB == 1554 and WW.WEB_EFFECT == 1579
    # Les deux ids sont VOISINS et de DEUX enums differents : les confondre serait silencieux.
    assert WW.WHISPERING_WEB != WW.WEB_EFFECT
    assert int(AbilityVariableType.extraDmg) == 8                 # la variable de la magnitude
    assert int(EventTriggerType.NormalAttack) == 38               # 0x26


def test_etage1_le_vecteur_et_ses_predicats():
    assert WW.WhisperingWebAbility.event_id == int(EventTriggerType.NormalAttack)
    assert WW.WhisperingWebAbility.TRIGGERED_ABILITY_ID == WW.WHISPERING_WEB
    src = (WW.WhisperingWebAbility.matches.__doc__ or "") + (WW.__doc__ or "")
    # Les trois conjoints du trigger doivent rester ECRITS : c'est ce qui empeche de « simplifier »
    # le predicat `IsRangedAttack`, dont l'absence ferait poser la toile en melee.
    for lu in ("IsRangedAttack", "get_OwnerIsCaster", "AreEnemies"):
        assert lu in src


def test_etage2_le_selecteur_de_retrait_filtre_par_SOURCE():
    """`OwnerOfEffect(EffectsFromUnitSource(Owner, 0x62b))` -- le filtre par source est LU.

    Un substrat minimal suffit : ce qui est teste est que `webs_placed_by` ne rende QUE les
    porteurs dont l'instance a pour source le poseur demande. Sans ce filtre, Lhykhis retirerait
    la toile d'un AUTRE poseur (miroir, duel)."""
    class _E:
        def __init__(self, et, src):
            self.effect_type, self.source = et, src

    class _Effects:
        by_unit = {10: [_E(1579, 7)], 11: [_E(1579, 8)], 12: [_E(1234, 7)]}

    class _State:
        effects = _Effects()

    assert WW.webs_placed_by(_State(), 7) == [10]      # ni 11 (autre source) ni 12 (autre effet)
    assert WW.webs_placed_by(_State(), 8) == [11]
    assert WW.webs_placed_by(_State(), 99) == []


def test_etage2_substrat_sans_effets_rend_vide_sans_lever():
    class _State:
        effects = None
    assert WW.webs_placed_by(_State(), 7) == []


def test_etage3_registre():
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    classes = ABILITY_TRIGGERS.get("WhisperingWeb")
    assert classes == [WW.WhisperingWebAbility]


def test_etage4_la_magnitude_n_est_PAS_portee_et_le_module_le_DIT():
    """Residu #965-r2 : l'effet 1579 n'a AUCUNE classe portee, donc aucun bonus de degat.

    Le garde exige les DEUX faces :
      (a) le registre d'effets ne connait pas 1579 -- sinon la magnitude serait arrivee sans que
          ce test soit mis a jour, et l'ecart RESTRICTIF documente serait devenu faux ;
      (b) le module ECRIT pourquoi, en nommant le blocage. Une absence non documentee se relit
          comme un oubli."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    assert EffectType.WhisperingWeb.name not in EFFECT_CLASSES, (
        "1579 est desormais porte -> mettre a jour #965-r2 et ce garde")
    doc = WW.__doc__ or ""
    assert "CurrentHitIndex" in doc and "#965-r2" in doc
    assert "defender_modifiers" in doc, "le foyer du blocage doit rester NOMME"


if __name__ == "__main__":                      # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

