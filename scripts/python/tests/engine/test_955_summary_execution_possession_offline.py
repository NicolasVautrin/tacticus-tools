"""#955 -- cliquet OFFLINE des deux passifs `SummaryExecution` (`astraYarrick`) et `Possession`
(`blackPossession`).

Il FIGE ce que la RE a lu au decompile du build `rnca9r7q6c` et ce que le live a mesure :
la STRUCTURE des deux arbres, les registres d'inscription, les enums cites au site, et les
magnitudes. Un test qui rougit ici dit qu'un des deux ports a change de forme sans que la RE
ait ete refaite. Detail : `docs/rl/case-955-summary-execution-et-possession.md`.
"""
from __future__ import annotations

import pytest

#: #486-r15 -- perimetre = exactement les foyers que ce fichier lit (aucun runner ; le gameconfig
#: du build est lu pour les magnitudes et les deux `unitId` -> `build: True`).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        # Entre dans la fermeture par la CASCADE DES CONFTEST depuis #951-r2. Ce chemin n'existait
        # pas quand ce fichier a ete ecrit : c'est l'INTERACTION de deux PR mergees le meme jour
        # qui l'a fait apparaitre, et `probe_486r15` l'a vu -- un declencheur trop etroit est un
        # FAUX VERT (le fichier ne se rejoue pas quand ce qu'il garde a bouge).
        "scripts/python/coverage_attestations.py",
        # #979 : `audit_kit_coverage` lit desormais le foyer `decision_face_voies` au lieu de sa
        # propre liste blanche de registres -- il entre donc dans la meme cascade, par la meme voie.
        "scripts/python/decision_face_voies.py",
        # les deux ports et leurs registres
        "scripts/python/engine/entities/effects/loki/summary_execution.py",
        "scripts/python/engine/runner/operations/triggers/loki/summary_execution.py",
        "scripts/python/engine/runner/operations/triggers/loki/possession.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/move_death.py",
        "scripts/python/engine/runner/operations/behaviour.py",
        # les feuilles DSL et les selecteurs que les deux arbres montent
        "scripts/python/engine/runner/abilities/behaviours/summon.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/lifecycle.py",
        "scripts/python/engine/runner/operations/spawn.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/tiles.py",
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        # les enums CITES au site, et le socle des effets
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/entities/stats.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
        "scripts/python/audit_kit_coverage.py",
        "scripts/python/audit_combat_ability_coverage.py",   # tire par l'import d'`audit_kit_coverage`
        "scripts/python/gameconfig.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Offline : fige les LITTERAUX lus au bloc `methodPointers` (les deux EffectType, le "
              "trait, les deux AbilityConstantType, les deux AbilityVariableType, les deux "
              "TriggeringAbilityIs), la STRUCTURE des deux arbres, le SELECTEUR PARTAGE par 1031 "
              "et 1043 (fondu par l'ICF -- la face cachee du lot), le couplage ordinal <-> "
              "constante de `Possession`, et l'etage amont `On(PreUnitFled)` que cette tranche a "
              "du ajouter a `FleeOperation`. Aucun runner : tout est lisible du code et du "
              "gameconfig.",
}


# ---------------------------------------------------------------- [1] les ENUMS cites au site
def test_ids_et_enums_du_lot():
    """Les cinq identifiants que les deux ports ecrivent, tous LUS au decompile."""
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.entities.effect_type import EffectType
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.entities.ability_constant_type import AbilityConstantType
    from engine.entities.ability_variable_type import AbilityVariableType
    from engine.entities.stats import StatType

    assert int(TriggeredAbilityType.SummaryExecution) == 0x409
    assert int(TriggeredAbilityType.Possession) == 0x40A
    assert int(TriggeredAbilityType.BattleFatigue) == 0x401        # `TriggeringAbilityIs` de 1033
    assert int(TriggeredAbilityType.ItsGonnaBlow) == 0x438         # `NOT TriggeringAbilityIs` de 1034
    assert int(EffectType.SummaryExecution_Effect) == 0x407
    assert int(EffectType.SummaryExecution_BaseEffect) == 0x413
    assert int(EffectType.IgnoreBattleFatigue) == 0x437            # le sous-effet d'`ApplyInternal`
    assert int(UnitTrait.BattleFatigue) == 0x3F7                   # le gate du selecteur partage
    assert int(EventTriggerType.PreUnitFled) == 0x33
    assert int(EventTriggerType.PostUnitKill) == 0x35
    assert int(AbilityConstantType.unitId) == 0 and int(AbilityConstantType.unitId_2) == 4
    assert int(AbilityVariableType.extraDmg) == 8
    assert int(AbilityVariableType.extraDmg_2) == 9
    assert int(StatType.ATTACK) == 0                               # le `statType` des deux behaviours
    # `AttemptedPossession` est une ACTIVE d'une AUTRE unite (`thousSorcerer`) : le brief du lot
    # l'attribuait au passif `Possession`, la lecture du bloc `methodPointers` l'a refute.
    assert int(ActiveAbilityType.AttemptedPossession) == 1101
    assert getattr(TriggeredAbilityType, "AttemptedPossession", None) is None


# ---------------------------------------------------------------- [2] les REGISTRES
def test_les_deux_passifs_sont_inscrits_ou_il_faut():
    """`SummaryExecution` a DEUX faces dans DEUX registres distincts, et s'y tromper donne un
    passif qui ne se pose jamais (arbitrage #948/#952) ; `Possession` n'a qu'un trigger."""
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES
    from engine.runner.operations.triggers.loki.summary_execution import SummaryExecutionAbility
    from engine.runner.operations.triggers.loki.possession import PossessionSummonOnKillAbility
    from engine.entities.effects.loki.summary_execution import (SummaryExecutionBaseEffect,
                                                                SummaryExecutionEffect)
    from engine.dsl.event_trigger_type import EventTriggerType

    assert ABILITY_TRIGGERS.get("SummaryExecution") == [SummaryExecutionAbility]
    assert ABILITY_TRIGGERS.get("Possession") == [PossessionSummonOnKillAbility]
    # la face AURA PERMANENTE : trigger d'INIT partage -> `ABILITY_INIT_OWNER_EFFECTS`
    assert ABILITY_INIT_OWNER_EFFECTS.get("SummaryExecution") == ["SummaryExecution_BaseEffect"]
    assert EFFECT_CLASSES.get("SummaryExecution_BaseEffect") is SummaryExecutionBaseEffect
    assert EFFECT_CLASSES.get("SummaryExecution_Effect") is SummaryExecutionEffect
    # l'effet 1031 est pose DYNAMIQUEMENT : il ne doit PAS etre dans le registre d'init
    assert "SummaryExecution_Effect" not in (ABILITY_INIT_OWNER_EFFECTS.get("SummaryExecution") or [])
    assert SummaryExecutionAbility.event_id == int(EventTriggerType.PreUnitFled)
    assert PossessionSummonOnKillAbility.event_id == int(EventTriggerType.PostUnitKill)


def test_le_passif_est_vu_couvert_par_l_audit():
    from audit_kit_coverage import _passive_covered
    assert _passive_covered("SummaryExecution") is True
    assert _passive_covered("Possession") is True


# ---------------------------------------------------------------- [3] SummaryExecution : la face AURA
def test_les_deux_effets_partagent_le_meme_selecteur():
    """LA FACE CACHEE du lot : `SummaryExecutionEffect` n'a PAS de `CreateTargetSelector` propre --
    son slot du bloc `methodPointers` pointe sur le corps de `SummaryExecution_AlwaysEffectEffect`
    (fondu par l'ICF). Les deux classes doivent donc monter le MEME arbre."""
    from engine.entities.effects.loki.summary_execution import (summary_execution_target_selector,
                                                                _ASummaryExecutionAuraEffect,
                                                                SummaryExecutionBaseEffect,
                                                                SummaryExecutionEffect)
    from engine.entities.selectors.units import Friends, UnitsWithTrait
    from engine.entities.selectors.tiles import AllAliveUnits
    from engine.entities.selectors.accessors import Owner
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.entities.unit_selection_type import UnitSelectionType

    # les DEUX classes heritent LA MEME implementation du selecteur (un seul corps natif)
    assert (SummaryExecutionBaseEffect.aura_stat_modification_targets
            is _ASummaryExecutionAuraEffect.aura_stat_modification_targets)
    assert (SummaryExecutionEffect.aura_stat_modification_targets
            is _ASummaryExecutionAuraEffect.aura_stat_modification_targets)

    sel = summary_execution_target_selector()
    assert isinstance(sel, Friends)
    assert isinstance(sel.reference, Owner)                    # `Friends(of = Owner@+0x30, ...)`
    assert int(sel.selection_type) == int(UnitSelectionType.OnlyAliveAndTargetable)
    assert isinstance(sel.inner, UnitsWithTrait)
    assert int(sel.inner.trait) == int(UnitTrait.BattleFatigue)
    assert int(sel.inner.selection_type) == int(UnitSelectionType.OnlyAliveAndTargetable)
    assert isinstance(sel.inner.source, AllAliveUnits)         # `<DSLSelectors+0x20>`


def test_les_deux_magnitudes_et_leur_stat():
    """`ConfigVar(SummaryExecution, EffectSource(Get(effet)), 8 | 9)`, indexe sur l'`AbilityState`
    de la SOURCE. Valeurs FIGEES a la mesure live (Yarrick niveau 50, multiplier 180) : le natif
    ecrit +400 sur un Guardsman (`statModSources`, source = l'entite-effet)."""
    from engine.entities.effects.loki.summary_execution import (SummaryExecutionBaseEffect,
                                                                SummaryExecutionEffect)
    from engine.entities.stats import StatType

    base = SummaryExecutionBaseEffect(name="SummaryExecution_BaseEffect", effect_type=1043,
                                      ability_level=50, ability_variables_multiplier=180)
    exec_ = SummaryExecutionEffect(name="SummaryExecution_Effect", effect_type=1031,
                                   ability_level=50, ability_variables_multiplier=180)
    assert base.aura_stat_modification_stat() == int(StatType.ATTACK)
    assert exec_.aura_stat_modification_stat() == int(StatType.ATTACK)
    assert base.aura_stat_modification_amount() == 400          # extraDmg[50] x 1.8   (MESURE LIVE)
    assert exec_.aura_stat_modification_amount() == 202         # extraDmg_2[50] x 1.8
    # les DEUX variables sont dans `variablesAffectedByRarityBonus` -> sans multiplier, la valeur
    # brute du gameconfig
    brut = SummaryExecutionBaseEffect(name="x", effect_type=1043, ability_level=50,
                                      ability_variables_multiplier=100)
    assert brut.aura_stat_modification_amount() == 222
    # niveau inconnu -> AUCUNE magnitude devinee
    assert SummaryExecutionBaseEffect(name="x", effect_type=1043).aura_stat_modification_amount() is None


def test_les_deux_variables_ne_sont_PAS_le_meme_tableau():
    """Contre-epreuve de la confusion `extraDmg` / `extraDmg_2` : contrairement au kit
    `HuntersBeyondDeath` (#952), ou les deux variables portaient le MEME tableau et ou aucune
    mesure numerique ne pouvait les separer, ici elles DIFFERENT -- donc un test de magnitude
    seul suffit a mordre sur l'echange."""
    import gameconfig as GC
    v = (GC.ability("SummaryExecution") or {}).get("variables") or {}
    assert v.get("extraDmg") and v.get("extraDmg_2")
    assert v["extraDmg"] != v["extraDmg_2"]
    assert v["extraDmg"][-1] == 291 and v["extraDmg_2"][-1] == 146     # les deux chiffres de l'i2


# ---------------------------------------------------------------- [4] SummaryExecution : le TRIGGER
def test_l_arbre_du_behaviour_de_summary_execution():
    """`AddDynamicStatModifierEffectToOwner(0x407, statType = 0, null, false)` puis
    `Kill(Owner@+0x30, Actor@+0x40, ForDirectKill)` -- l'ORDRE est celui du decompile."""
    from engine.runner.operations.triggers.loki import summary_execution as SE
    from engine.runner.abilities.behaviours.effects import AddDynamicStatModifierEffect, AddEffect
    from engine.runner.abilities.behaviours.lifecycle import Kill
    from engine.entities.selectors.accessors import Actor, Owner
    from engine.entities.effect_type import EffectType
    from engine.entities.stats import StatType

    add = SE.summary_execution_behaviour_tree()
    assert isinstance(add, AddDynamicStatModifierEffect)
    assert add.effect_type == int(EffectType.SummaryExecution_Effect)
    assert add.stat_type == int(StatType.ATTACK)
    assert isinstance(add.target_sel, Owner) and isinstance(add.source_sel, Owner)
    assert add.duration_rounds is None and add.duration_turns is None      # `turns = null`

    kill = SE.summary_execution_kill_tree()
    assert isinstance(kill, Kill)
    assert isinstance(kill.subject_sel, Owner)      # le TUEUR impute = le porteur
    assert isinstance(kill.units_sel, Actor)        # la victime = l'ACTEUR de `PreUnitFled`

    # `SummaryExecutionEffect$$ApplyInternal` -- le sous-effet ne vit PLUS dans un arbre du trigger
    # (#955-r3) : il est DECLARE par l'effet et joue PAR CIBLE par le driver d'aura, a chacun de ses
    # reveils, comme `RefreshEffectsOperation$$ApplyEffectsForTargets` le fait cote natif.
    from engine.entities.effects.loki.summary_execution import SummaryExecutionEffect
    from engine.entities.effects.base import SubEffectSpec
    specs = SummaryExecutionEffect(name="SummaryExecution_Effect").aura_sub_effects_on_apply()
    assert len(specs) == 1 and isinstance(specs[0], SubEffectSpec)
    assert specs[0].effect_type == int(EffectType.IgnoreBattleFatigue)
    assert specs[0].turns is None                                  # `turns = null`
    assert not hasattr(SE, "summary_execution_ignore_fatigue_tree"), (
        "le poseur bespoke du trigger est revenu -- il y aurait DEUX foyers de pose pour le meme "
        "`ApplyInternal`, et celui-ci ne joue qu'une fois (#955-r3)")
    # ... et l'AUTRE aura du kit n'en pose AUCUN : le natif ne surcharge `ApplyInternal` que sur
    # 1031. Un `aura_sub_effects_on_apply` herite donnerait l'immunite des le chargement.
    from engine.entities.effects.loki.summary_execution import SummaryExecutionBaseEffect
    assert getattr(SummaryExecutionBaseEffect(name="SummaryExecution_BaseEffect"),
                   "aura_sub_effects_on_apply", None) is None


def test_le_verrou_one_shot_est_la_PRESENCE_de_l_effet():
    """`NOT HasEffect(Owner, 0x407, false, 6)` -- et l'effet teste est EXACTEMENT celui que le
    behaviour pose. Si les deux divergeaient, le passif firerait a chaque fuite."""
    from engine.runner.operations.triggers.loki import summary_execution as SE
    assert (SE.SUMMARY_EXECUTION_EFFECT
            == SE.summary_execution_behaviour_tree().effect_type)


# ---------------------------------------------------------------- [5] Possession
def test_l_arbre_de_possession_bifurque_sur_l_ordinal_ET_la_constante():
    """`If(NOT IsDefeatedByMeleeAttack(Target), Spawn(unitId_2, ordinal 2), Spawn(unitId, ordinal 1))`.
    Les DEUX axes changent ensemble -- un port qui n'en changerait qu'un donnerait le bon summon
    avec les stats de l'autre."""
    from engine.runner.operations.triggers.loki.possession import possession_spawn_tree
    from engine.runner.abilities.behaviours.summon import Spawn
    from engine.entities.selectors.geometry import Otherwise
    from engine.entities.selectors.tiles import AdjacentTiles, CanAddUnit
    from engine.entities.selectors.units import Tiles

    melee = possession_spawn_tree((50, 180), ranged_kill=False)
    ranged = possession_spawn_tree((50, 180), ranged_kill=True)
    for t in (melee, ranged):
        assert isinstance(t, Spawn)
        assert t.summon_ability == "Possession"
        assert t.pick_n == 1                        # `PickRandomly(., amount = 1)`
        assert t.ability_state == (50, 180)         # `WithStatsFromConfig(config, abilityState)`
        # `FreeTilesOrAdjacentFreeTiles(tiles)` = `Otherwise(CanAddUnit(tiles, isSteppable),
        #                                                    CanAddUnit(AdjacentTiles(tiles), .))`
        assert isinstance(t.tile_selector, Otherwise)
        a, b = t.tile_selector.primary, t.tile_selector.fallback
        assert isinstance(a, CanAddUnit) and a.allow_steppable is True
        assert isinstance(b, CanAddUnit) and b.allow_steppable is True
        assert isinstance(a.source, Tiles) and a.source.as_ids is True
        assert isinstance(b.source, AdjacentTiles)
    assert (melee.unit_id_constant, melee.stat_key_suffix) == ("unitId", "")
    assert (ranged.unit_id_constant, ranged.stat_key_suffix) == ("unitId_2", "_2")


def test_les_deux_summons_de_possession_sont_ceux_du_gameconfig():
    """Les deux `GetStringConstant(cfg, 0 | 4)`, et les DEUX jeux de stats qu'ils lisent."""
    import gameconfig as GC
    cfg = GC.ability("Possession") or {}
    consts, var = cfg.get("constants") or {}, cfg.get("variables") or {}
    assert consts.get("unitId") == "blackSmnBloodletter"        # kill MELEE   (MESURE LIVE)
    assert consts.get("unitId_2") == "thousSmnBlueHorror"       # kill RANGED  (MESURE LIVE)
    for k in ("summonHp", "summonDmg", "summonHp_2", "summonDmg_2"):
        assert var.get(k), "variable %s absente du gameconfig de Possession" % k
    # l'ordinal SEPARE bien deux jeux de stats -- sinon `stat_key_suffix` serait inerte
    assert var["summonHp"] != var["summonHp_2"]
    assert var["summonDmg"] != var["summonDmg_2"]


def test_spawn_porte_l_ordinal_de_WithStatsFromConfig():
    """Le parametre ajoute par cette tranche (`stat_key_suffix`) doit ARRIVER a
    `build_summon_context`, sinon les deux summons prendraient les MEMES stats en silence."""
    import inspect
    from engine.runner.abilities.behaviours.summon import Spawn
    from engine.runner.operations.spawn import _spawn_config_grot, build_summon_context

    assert "stat_key_suffix" in inspect.signature(Spawn.__init__).parameters
    assert "key_suffix" in inspect.signature(_spawn_config_grot).parameters
    assert "key_suffix" in inspect.signature(build_summon_context).parameters
    src = inspect.getsource(Spawn.execute)
    assert "key_suffix=self.stat_key_suffix" in src, \
        "`Spawn.execute` ne transmet PAS son `stat_key_suffix` : le parametre serait INERTE"
    # defaut inchange = ordinal 1 (les huit call-sites anterieurs)
    assert Spawn(None, "X").stat_key_suffix == ""


# ---------------------------------------------------------------- [6] l'etage amont PreUnitFled
def test_le_vecteur_pre_unit_fled_existe_et_est_emis_par_flee():
    """`EventTriggerType.PreUnitFled` n'avait AUCUN emetteur dans `engine/**` avant cette tranche.
    Le natif l'emet en TOUT PREMIER dans `FleeOperation$$Execute`, puis ABANDONNE la fuite si
    l'unite est morte -- c'est CE couple qui porte le « executed instead » de l'i2."""
    import inspect
    from engine.runner.operations.triggers.dispatch import move_death
    from engine.runner.operations import behaviour as BEH
    from engine.dsl.event_trigger_type import EventTriggerType

    assert callable(getattr(move_death, "pre_unit_fled_triggers", None))
    src = inspect.getsource(BEH.FleeOperation.execute)
    assert "pre_unit_fled_triggers" in src, "FleeOperation n'emet pas `On(PreUnitFled)`"
    assert "cancelled_by_death" in src, "FleeOperation n'ABANDONNE pas la fuite sur `IsDead`"
    # l'ordre compte : l'emission PRECEDE le retrait du plateau
    assert src.index("pre_unit_fled_triggers") < src.index("RemoveUnitOperation.execute")
    # le canal `triggering_ability` est seede par l'unique appelant porte
    bf = inspect.getsource(BEH.BattleFatigueAbility.execute_behaviour)
    assert "triggering_ability=int(TriggeredAbilityType.BattleFatigue)" in bf
    assert int(EventTriggerType.PreUnitFled) == 51


@pytest.mark.parametrize("mod", [
    "engine.runner.operations.triggers.loki.possession",
    "engine.runner.operations.triggers.loki.summary_execution",
    "engine.entities.effects.loki.summary_execution",
])
def test_les_modules_neufs_s_importent_SEULS(mod):
    """L'invariant `430/430` : chaque module de `engine/**` s'importe seul en process FRAIS."""
    import subprocess
    import sys
    from pathlib import Path
    r = subprocess.run([sys.executable, "-c", "import %s" % mod],
                       cwd=str(Path(__file__).resolve().parents[2]),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, "import isole KO : %s" % (r.stderr or "")[-600:]
