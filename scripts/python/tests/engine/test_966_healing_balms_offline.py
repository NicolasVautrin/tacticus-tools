"""#966 -- garde OFFLINE de la face COMBAT de `HealingBalms` (`spaceWolfPriest`).

Cinq etages, chacun gardant une decision de RE que le decompile a tranchee et qu'un port distrait
aurait rendue autrement. Chaque etage assertionne son PROPRE NON-VIDE avant de conclure : une
population vide rendrait un vert qui ment (cf. #941-r3).

ASCII only.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                  # scripts/python
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

HEAL_ABILITY = 1212
EXTRA_CRIT_DMG = 1503
EXTRA_CRIT_CHANCE = 1504
HEALING_BALMS_EFFECT = 1508


def test_ordinaux_figes_au_site():
    """ETAGE 1 -- les ordinaux ECRITS AU SITE, figes a la valeur MESUREE sur `rnca9r7q6c`.

    `probe_313` compare le MIRROR au BUILD : il redevient vert des qu'on regenere le mirror apres
    un renumerotage, alors que la valeur ecrite au site, elle, a change. Ce cran-ci garde l'autre
    moitie. Ordinaux lus dans `data/symbols/rnca9r7q6c/frida/enums.tsv`."""
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.entities.effect_type import EffectType
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.entities.stats import StatType
    from engine.entities.ability_constant_type import AbilityConstantType
    from engine.entities.ability_variable_type import AbilityVariableType
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.entities.unit_flag import UnitFlag

    assert int(ActiveAbilityType.HealingBalms_Heal) == HEAL_ABILITY          # 0x4bc
    assert int(ActiveAbilityType.Heal) == 18                                 # 0x12
    assert int(TriggeredAbilityType.HealingBalms) == 1502                    # 0x5de
    assert int(EffectType.HealingBalms_ExtraCritDamage) == EXTRA_CRIT_DMG    # 0x5df
    assert int(EffectType.HealingBalms_ExtraCritChance) == EXTRA_CRIT_CHANCE  # 0x5e0
    assert int(EffectType.HealingBalms) == HEALING_BALMS_EFFECT              # 0x5e4
    assert int(StatType.CRIT_CHANCE) == 9 and int(StatType.CRIT_DAMAGE) == 10
    assert int(AbilityConstantType.nrOfRounds) == 0x45
    assert int(AbilityVariableType.hpToHeal) == 0x20
    assert int(EventTriggerType.TurnStart_Other) == 0x13
    assert int(UnitFlag.CanHealFullHealthUnits) == 0x17
    # ⚠ COLLISION D'ORDINAL entre enums : `EffectType.RitesOfMorkai` porte le MEME 1502 que
    # `TriggeredAbilityType.HealingBalms`. La qualification par NOM est ce qui les separe.
    assert int(EffectType.RitesOfMorkai) == int(TriggeredAbilityType.HealingBalms)


def test_registres_compagnons_dans_le_meme_commit():
    """ETAGE 2 -- 1212 entre au registre AVEC son masque ET son attack-type (doctrine)."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
    from engine.runner.abilities.targeting_rule import TargetingRule as TR

    assert len(ABILITY_CLASSES) > 100, "population du registre vide/tronquee -> verdict sans objet"
    cls = ABILITY_CLASSES.get(HEAL_ABILITY)
    assert cls is not None, "1212 absent d'ABILITY_CLASSES"
    opts = getattr(cls, "TARGETING_OPTIONS", None)
    assert opts is not None, "1212 sans TARGETING_OPTIONS -> gate PERMISSIF silencieux"
    # `TargetingOptions..ctor(&opts, 0, &<TargetingRange statics+0x00>, 2, 0x8402, 0, 0)` -- FORME
    # SEPT ARGUMENTS, `rules` ecrit TEL QUEL. Seconde source : case-302-4/tile-target-population.tsv.
    assert int(opts.rules) == 0x8402
    assert int(opts.rules) == int(TR.TargetMatchesDynamicRule | TR.TargetIsFriendly
                                  | TR.CasterIsPossibleTarget)
    assert opts.self_cast is False
    assert int(opts.force_melee_target) == 2                 # RangedBool.IfRangedCaster
    assert int(opts.range.only_adjacent) == 3                # IfNotRangedCaster
    # `AActiveAbility..ctor(this, &opts, 2)` -> 3e argument = 2 = Others.
    assert int(ABILITY_ATTACK_TYPE.get(HEAL_ABILITY)) == int(AbilityAttackType.Others)
    # `ABILITY_ID = None` : 1212 n'a AUCUNE entree `units.abilities` (elle est SUBSTITUEE au 18).
    assert cls.ABILITY_ID is None


def test_les_trois_effets_ont_leur_canal():
    """ETAGE 3 -- 1503/1504 sont des STAT-MODS (`EFFECT_CLASSES`), 1508 est un TRIGGER
    (`EFFECT_TRIGGERS`). Les ranger dans le mauvais registre ne leverait AUCUNE erreur."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    from engine.entities.effects.loki.healing_balms import (HealingBalmsExtraCritDamageEffect,
                                                            HealingBalmsExtraCritChanceEffect)
    from engine.runner.operations.triggers.loki.healing_balms import HealingBalmsDelayedHeal
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.entities.stats import StatType

    assert len(EFFECT_CLASSES) > 200 and len(EFFECT_TRIGGERS) > 20, "registres vides"
    assert EFFECT_CLASSES.get("HealingBalms_ExtraCritDamage") is HealingBalmsExtraCritDamageEffect
    assert EFFECT_CLASSES.get("HealingBalms_ExtraCritChance") is HealingBalmsExtraCritChanceEffect
    assert "HealingBalms" not in EFFECT_CLASSES, "1508 n'est PAS un stat-mod, c'est un trigger"
    assert HealingBalmsDelayedHeal in (EFFECT_TRIGGERS.get(HEALING_BALMS_EFFECT) or [])
    assert HealingBalmsDelayedHeal.effect_type == HEALING_BALMS_EFFECT
    assert HealingBalmsDelayedHeal.event_id == int(EventTriggerType.TurnStart_Other)
    # ⚠ APPARIEMENT effectType <-> statType, LU au call-site : 1503 porte CriticalDamage(10),
    # 1504 porte CriticalChance(9). Les intervertir ne leverait AUCUNE erreur.
    dmg = HealingBalmsExtraCritDamageEffect("HealingBalms_ExtraCritDamage")
    chc = HealingBalmsExtraCritChanceEffect("HealingBalms_ExtraCritChance")
    assert dmg.reverted_stats() == [StatType.CRIT_DAMAGE]
    assert chc.reverted_stats() == [StatType.CRIT_CHANCE]
    # La MAGNITUDE se lit dans la config du PASSIF (l'active 1212 n'a AUCUNE entree gameconfig) et
    # le SIGNE est POSITIF -- inference NOMMEE, cf. residu #966-r1.
    mods_dmg = dmg.applied_stat_mods(None)
    mods_chc = chc.applied_stat_mods(None)
    assert mods_dmg and mods_chc, "magnitude nulle des deux cotes -> verdict sans objet"
    assert mods_dmg[0][0] == int(StatType.CRIT_DAMAGE) and mods_dmg[0][1] > 0
    assert mods_chc[0][0] == int(StatType.CRIT_CHANCE) and mods_chc[0][1] > 0


def test_gate_dynamique_ne_teste_QUE_le_heal_type():
    """ETAGE 4 -- le corps de `$$GetDynamicInvalidTargetReason` s'arrete a
    `IsAffectedByHealType` : AUCUN appel a `EntityCanBeHealed`.

    C'est LA difference avec le voisin de forme `TwistedScience_HealAbility`, et c'est ce qui
    realise le << can heal friendly units even if they are at full Health >> de l'i2. Le garde est
    STRUCTUREL (AST du corps de la methode), pas comportemental : un test de valeur exigerait un
    `State` monte, et surtout ne verrait PAS un appel ajoute dans une branche non exercee."""
    src = (PYDIR / "engine" / "runner" / "abilities" / "loki" / "healing_balms.py").read_text(
        encoding="utf-8")
    tree = ast.parse(src)
    fns = [n for n in ast.walk(tree)
           if isinstance(n, ast.FunctionDef) and n.name == "get_dynamic_invalid_target_reason"]
    assert len(fns) == 1, "population vide/multiple -> verdict sans objet"
    called = {n.func.id for n in ast.walk(fns[0])
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    called |= {n.func.attr for n in ast.walk(fns[0])
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert called, "aucun appel trouve -> le detecteur ne voit rien, verdict sans objet"
    assert "is_affected_by_heal_type" in called
    assert "entity_can_be_healed" not in called, (
        "le natif NE consulte PAS EntityCanBeHealed : l'ajouter fermerait le ciblage a PV pleins, "
        "exactement le cas que 1212 existe pour ouvrir")


def test_l_arbre_porte_ses_six_feuilles_dans_l_ordre_natif():
    """ETAGE 5 -- `healing_balms_heal_tree` construit SIX feuilles, et le `RemoveEffect` PRECEDE
    les deux `AddDynamicStatModifierEffect`.

    L'ordre n'est pas cosmetique : sans la purge en tete, un re-soin EMPILE deux instances au lieu
    de RE-ARMER -- ecart SILENCIEUX de magnitude. Garde STRUCTUREL sur l'arbre construit (aucun
    `State` requis : les feuilles sont des objets)."""
    from engine.runner.abilities.loki.healing_balms import healing_balms_heal_tree

    class _NoState:
        def get_entity(self, _uid):
            return None

    tree = healing_balms_heal_tree(_NoState(), 1)
    # L'arbre est une cascade d'`op_add` : on aplatit par parcours des attributs de noeud.
    seen = []

    def _walk(node, depth=0):
        if depth > 40:
            return
        seen.append(type(node).__name__)
        for attr in ("left", "right", "a", "b", "children", "nodes", "items"):
            v = getattr(node, attr, None)
            if v is None:
                continue
            for c in (v if isinstance(v, (list, tuple)) else [v]):
                if hasattr(c, "execute"):
                    _walk(c, depth + 1)

    _walk(tree)
    assert len(seen) > 3, "l'aplatissement n'a rien trouve -> verdict sans objet"
    assert seen.count("RemoveEffect") == 2, seen
    assert seen.count("AddDynamicStatModifierEffect") == 2, seen
    assert seen.count("AddEffect") == 1, seen
    assert seen.count("Heal") == 1, seen
    # Le `If` de `TwistedScience_HealAbility` n'existe PAS ici : l'arbre natif est PLAT.
    assert "IfBehaviour" not in seen and "If" not in seen, (
        "l'arbre natif de 1212 ne contient AUCUN `If` -- les buffs partent meme sur un self-cast")
    # ORDRE : les deux purges avant les deux stat-mods.
    assert seen.index("RemoveEffect") < seen.index("AddDynamicStatModifierEffect"), seen


if __name__ == "__main__":                                   # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
