#!/usr/bin/env python3
"""
Generate Java Loki effect classes from decompiled C files.

Reads each .c file in the decompiled Loki effects directory, identifies
the methods present, determines the parent class, and generates the
corresponding Java class.

ENTREE `data/decompiled_tacticus/` : artefact du pipeline Ghidra hors-ligne, ni
versionne ni produit ici -> resolu par `host_inputs` (tri-etat #273). Sans lui,
un listing du repertoire absent rendait ZERO fichier SANS lever, et ce
generateur se terminait « 0 classe generee » comme s'il n'y avait rien a faire.

SORTIE `app/` : RELATIVE au checkout (#314) -- un chemin absolu ferait ecrire ce
script dans l'arbre principal depuis n'importe quel worktree d'agent.
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import host_inputs

_REPO = Path(__file__).resolve().parents[2]
_JAVA = _REPO / "app" / "src" / "main" / "java" / "tacticus" / "idunbattle" / "entities" / "effects"

DECOMPILED_DIR = str(host_inputs.require(
    "data/decompiled_tacticus/IdunBattle/Entities/Effects/Loki"))
OUTPUT_DIR = str(_JAVA / "loki")
EFFECTS_BASE_DIR = str(_JAVA)

PACKAGE = "tacticus.idunbattle.entities.effects.loki"
BASE_PACKAGE = "tacticus.idunbattle.entities.effects"

# Method name extraction pattern (MULTILINE so ^ matches each line start)
METHOD_RE = re.compile(r'^// === IdunBattle\.Entities\.Effects\.Loki\.(\w+)\.(\w+)', re.MULTILINE)

# Parent class detection patterns
PARENT_CTOR_PATTERNS = [
    (r'StaticStatModifierEffect__ctor', 'StaticStatModifierEffect'),
    (r'ADynamicStatModifierEffect__ctor', 'ADynamicStatModifierEffect'),
    (r'AMutantStatModifierEffect__ctor', 'AMutantStatModifierEffect'),
    (r'AStatModifierEffect__ctor', 'AStatModifierEffect'),
    (r'APendingAttackEffect__ctor', 'APendingAttackEffect'),
    (r'ABondEffect__ctor|ABondEffect\.\.ctor', 'ABondEffect'),
    (r'AReactivateOverwatchEffect__ctor', 'AReactivateOverwatchEffect'),
    (r'CounterAttackEffect__ctor', 'CounterAttackEffect'),
    (r'ReviveEffect__ctor', 'ReviveEffect'),
    (r'HealBlockingEffect__ctor', 'HealBlockingEffect'),
    (r'MultiValueStatEntryEffect__ctor', 'MultiValueStatEntryEffect'),
    (r'DamageModifierAbilityEffect\.\.ctor', 'DamageModifierAbilityEffect'),
    (r'PlayerTurnEffect__ctor', 'PlayerTurnEffect'),
    (r'BaseEffect\.\.ctor', 'BaseEffect'),
]

# Known abstract parent classes in the Loki package itself
LOKI_ABSTRACT_CLASSES = {
    'ADaemonicPatronsEffect',
    'ALegendaryCommander_BaseEffect',
    'APsychicStalkEffect',
    'AStructuralAnalyserEffect',
    'ATeleportingEffect',
    'ATemptingTrap_DamageReductionEffect',
    'AWayOfTheShortBladeEffect',
    'BaseFleshmetalGunsEffect',
    'TzeentchsFirestormBaseEffect',
}

# Known Loki inheritance (child -> parent within Loki)
LOKI_PARENTS = {
    'DaemonicPatrons_DmgReductionEffect': 'ADaemonicPatronsEffect',
    'DaemonicPatrons_ExtraDamageEffect': 'ADaemonicPatronsEffect',
    'LegendaryCommander_ExtraDamageEffect': 'ALegendaryCommander_BaseEffect',
    'LegendaryCommander_ExtraHitsEffect': 'ALegendaryCommander_BaseEffect',
    'PsychicStalk_ExtraAttackDamageEffect': 'APsychicStalkEffect',
    'PsychicStalk_FriendlyChaosExtraDamageEffect': 'APsychicStalkEffect',
    'PsychicStalk_VisualEffectEffect': 'APsychicStalkEffect',
    'StructuralAnalyserAdjacentEffect': 'AStructuralAnalyserEffect',
    'StructuralAnalyser_VisualEffect': 'AStructuralAnalyserEffect',
    'StormboyzStrike_TeleportingInEffect': 'ATeleportingEffect',
    'TeleportStrike_TeleportingInEffect': 'ATeleportingEffect',
    'FearOfTheUnseen_TeleportingInEffect': 'ATeleportingEffect',
    'LivingLightning_MovingEffect': 'ATeleportingEffect',
    'TeleportStrike_MovingEffect': 'ATeleportingEffect',
    'FearOfTheUnseen_MovingEffect': 'ATeleportingEffect',
    'FleshmetalGunsFocusedMaliceEffect': 'BaseFleshmetalGunsEffect',
    'FleshmetalGunsRuinousSalvoEffect': 'BaseFleshmetalGunsEffect',
    'FleshmetalGunsWarpHailEffect': 'BaseFleshmetalGunsEffect',
    'TzeentchsFirestormFirstCircleEffect': 'TzeentchsFirestormBaseEffect',
    'TzeentchsFirestormSecondCircleEffect': 'TzeentchsFirestormBaseEffect',
    'TzeentchsFirestormThirdCircleEffect': 'TzeentchsFirestormBaseEffect',
    'WayOfTheShortBladeEffect': 'AWayOfTheShortBladeEffect',
    'WayOfTheShortBlade_AdditionalAttackMarkerEffect': 'AWayOfTheShortBladeEffect',
}


def parse_c_file(filepath):
    """Parse a decompiled C file and extract method info."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Get class name from header
    header_match = re.search(r'// Decompiled: IdunBattle\.Entities\.Effects\.Loki\.(\w+)', content)
    if not header_match:
        return None
    class_name = header_match.group(1)

    # Get method count
    method_count_match = re.search(r'// Methods: (\d+)', content)
    method_count = int(method_count_match.group(1)) if method_count_match else 0

    # Extract method names
    methods = []
    for m in METHOD_RE.finditer(content):
        methods.append(m.group(2))

    # Determine parent class
    parent = 'BaseEffect'  # default

    # Check if it's a known Loki-internal child
    if class_name in LOKI_PARENTS:
        parent = LOKI_PARENTS[class_name]

    # Check for constructor calls to base classes
    for pattern, parent_name in PARENT_CTOR_PATTERNS:
        if re.search(pattern, content):
            # Don't override Loki-internal parents
            if class_name not in LOKI_PARENTS:
                parent = parent_name
            break

    # Check for specific method patterns to infer parent
    if class_name not in LOKI_PARENTS:
        if 'DamageModifierAbilityEffect' in content and parent == 'BaseEffect':
            if 'CreateDamageDefenseModifier' in content:
                parent = 'ADamageDefenseModifierAbilityEffect'

    # Effects with GetDynamicStatModificationAmount should extend ADynamicStatModifierEffect
    if class_name not in LOKI_PARENTS and parent == 'BaseEffect':
        if 'GetDynamicStatModificationAmount' in content:
            parent = 'ADynamicStatModifierEffect'

    # Detect abstract effects that are parents within Loki
    if class_name in LOKI_ABSTRACT_CLASSES:
        # These are abstract, keep BaseEffect or detect from ctor
        pass

    # Specific DSL calls and what they mean
    has_addsubeffect = 'AddSubEffect' in content or 'AddSubEffectWithSameTurns' in content
    has_changestat = 'ChangeStat' in content
    has_effectbonus = 'EffectBonus_For' in content
    has_effectadditionalhits = 'EffectAdditionalHits' in content
    has_effectcappedbonus = 'CappedEffectBonus' in content
    has_effectoverridedamageprofile = 'EffectOverrideDamageProfileType' in content

    # Extract hex constants used in AddSubEffect (effect type IDs)
    subeffect_ids = re.findall(r'AddSubEffect\w*\(.*?,0x([0-9a-fA-F]+)', content)

    # Extract config constants
    config_consts = re.findall(r'GetNumberConstant\([^,]+,0x([0-9a-fA-F]+)', content)
    config_vars = re.findall(r'GetVariableForLevel\([^,]+,0x([0-9a-fA-F]+)', content)

    # Detect EffectConfig usage with index
    effect_config_indices = re.findall(r'EffectConfig\([^,]+,(\d+)', content)

    # Detect Stat..ctor patterns (stat_id, change_type)
    stat_patterns = re.findall(r'Stat\.\.ctor\([^,]+,(\d+),(\d+)', content)

    # Detect BondedEntitySelector usage
    has_bonded = 'BondedEntitySelector' in content

    # Detect SurroundingUnits usage
    has_surrounding = 'SurroundingUnits' in content

    # Detect UnitsFromFaction
    has_units_from_faction = 'UnitsFromFaction' in content

    # Detect specific condition patterns
    has_owner_is_caster = 'OwnerIsCaster' in content
    has_owner_is_target = 'OwnerIsTarget' in content
    has_owner_is_actor = 'OwnerIsActor' in content
    has_is_ranged_attack = 'IsRangedAttack' in content
    has_is_melee_attack = 'IsMeleeAttack' in content
    has_has_flag = 'HasFlag' in content
    has_has_trait = 'HasTrait' in content
    has_has_effect = 'HasEffect' in content
    has_on_predeath = 'OnPreDeath' in content
    has_on_death = 'OnDeath' in content
    has_is_alive = 'IsAlive' in content
    has_is_moving = 'IsMoving' in content
    has_can_move = 'CanMove' in content
    has_deactivate_effect = 'DeactivateEffect' in content
    has_remove_effect = 'RemoveEffect' in content
    has_revive = 'Revive' in content and 'HasBeenRevivedByAbility' not in content
    has_move_unit = 'MoveUnit' in content
    has_damage_transfer = 'DamageTransfer' in content
    has_triggered = 'DSLFactory_Triggered' in content
    has_ability_has_attack_type = 'AbilityHasAttackType' in content
    has_triggering_ability_is = 'TriggeringAbilityIs' in content

    # DSL fields accessed
    dsl_fields_accessed = set()
    for fld in ['0xf8', '0x128', '0x130', '0x148', '0x150', '0x160', '0x178',
                '0xa0', '0xb8', '400']:
        if fld in content:
            dsl_fields_accessed.add(fld)

    return {
        'class_name': class_name,
        'methods': methods,
        'method_count': method_count,
        'parent': parent,
        'content': content,
        'has_addsubeffect': has_addsubeffect,
        'has_changestat': has_changestat,
        'has_effectbonus': has_effectbonus,
        'has_effectadditionalhits': has_effectadditionalhits,
        'has_effectcappedbonus': has_effectcappedbonus,
        'has_effectoverridedamageprofile': has_effectoverridedamageprofile,
        'subeffect_ids': subeffect_ids,
        'config_consts': config_consts,
        'config_vars': config_vars,
        'effect_config_indices': effect_config_indices,
        'stat_patterns': stat_patterns,
        'has_bonded': has_bonded,
        'has_surrounding': has_surrounding,
        'has_units_from_faction': has_units_from_faction,
        'has_owner_is_caster': has_owner_is_caster,
        'has_owner_is_target': has_owner_is_target,
        'has_owner_is_actor': has_owner_is_actor,
        'has_is_ranged_attack': has_is_ranged_attack,
        'has_is_melee_attack': has_is_melee_attack,
        'has_has_flag': has_has_flag,
        'has_has_trait': has_has_trait,
        'has_has_effect': has_has_effect,
        'has_on_predeath': has_on_predeath,
        'has_on_death': has_on_death,
        'has_is_alive': has_is_alive,
        'has_is_moving': has_is_moving,
        'has_can_move': has_can_move,
        'has_deactivate_effect': has_deactivate_effect,
        'has_remove_effect': has_remove_effect,
        'has_revive': has_revive,
        'has_move_unit': has_move_unit,
        'has_damage_transfer': has_damage_transfer,
        'has_triggered': has_triggered,
        'has_ability_has_attack_type': has_ability_has_attack_type,
        'has_triggering_ability_is': has_triggering_ability_is,
        'dsl_fields_accessed': dsl_fields_accessed,
    }


def get_parent_import(parent):
    """Get the import statement for the parent class."""
    if parent in LOKI_ABSTRACT_CLASSES or parent in [v for v in LOKI_PARENTS.values()]:
        # Parent is in the same loki package
        return None
    return f"{BASE_PACKAGE}.{parent}"


def is_abstract(class_name):
    """Check if a class should be abstract."""
    return class_name in LOKI_ABSTRACT_CLASSES


def generate_method_body(info, method_name):
    """Generate a Java method body based on decompiled analysis."""

    # CreateActiveCondition
    if method_name == 'CreateActiveCondition':
        if 'HasTrait' in info['content'] and 'CreateActiveCondition' in str(info['content'].split('CreateActiveCondition')[1][:500] if 'CreateActiveCondition' in info['content'] else ''):
            return """    @Override
    protected Object createActiveCondition() {
        // From decompiled: checks trait condition via DSL
        return dsl().getAlwaysActiveCondition();
    }
"""
        # Check which DSL field is returned
        content = info['content']
        # Find the CreateActiveCondition section
        cac_idx = content.find('CreateActiveCondition')
        if cac_idx >= 0:
            section = content[cac_idx:cac_idx+500]
            if '0xf8' in section:
                return """    @Override
    protected Object createActiveCondition() {
        // From decompiled: returns dsl.alwaysActiveCondition (offset 0xf8)
        return dsl().getAlwaysActiveCondition();
    }
"""
            elif '0x128' in section:
                return """    @Override
    protected Object createActiveCondition() {
        // From decompiled: returns dsl.unitIsAliveCondition (offset 0x128)
        return dsl().getUnitIsAliveCondition();
    }
"""
            elif 'IsCanAddUnit' in section:
                return """    @Override
    protected Object createActiveCondition() {
        // From decompiled: tile can add unit condition
        return dsl().isCanAddUnit(dsl().getOwnerSelector());
    }
"""
            elif 'HasTrait' in section:
                trait_match = re.search(r'HasTrait\s*\([^,]+,[^,]+,0x([0-9a-fA-F]+)', section)
                trait_id = int(trait_match.group(1), 16) if trait_match else 0
                has_not = 'LogicalNot' in section
                if has_not:
                    return f"""    @Override
    protected Object createActiveCondition() {{
        // From decompiled: checks unit does NOT have trait 0x{trait_id:x}
        return dsl().not(dsl().hasTrait(dsl().getOwnerSelector(), 0x{trait_id:x}));
    }}
"""
                else:
                    return f"""    @Override
    protected Object createActiveCondition() {{
        // From decompiled: checks unit has trait 0x{trait_id:x}
        return dsl().hasTrait(dsl().getOwnerSelector(), 0x{trait_id:x});
    }}
"""
        return """    @Override
    protected Object createActiveCondition() {
        return dsl().getAlwaysActiveCondition();
    }
"""

    # CreateTargetSelector
    if method_name == 'CreateTargetSelector':
        content = info['content']
        cts_idx = content.find('CreateTargetSelector')
        if cts_idx >= 0:
            section = content[cts_idx:cts_idx+800]
            if 'SurroundingUnits' in section:
                range_match = re.search(r'GetNumberConstant\([^,]+,0x([0-9a-fA-F]+)', section)
                range_const = int(range_match.group(1), 16) if range_match else 0
                has_faction = 'UnitsFromFaction' in section
                faction_match = re.search(r'UnitsFromFaction\([^,]+,[^,]+,(\d+)', section)
                faction_id = int(faction_match.group(1)) if faction_match else 0
                if has_faction:
                    return f"""    @Override
    protected Object createTargetSelector() {{
        // From decompiled: surrounding units within range (config 0x{range_const:x}), filtered by faction {faction_id}
        int range = getConfigConstant(0x{range_const:x});
        Object surrounding = dsl().surroundingUnits(dsl().getOwnerSelector(), range, true);
        return dsl().unitsFromFaction(surrounding, {faction_id});
    }}
"""
                return f"""    @Override
    protected Object createTargetSelector() {{
        // From decompiled: surrounding units within range (config 0x{range_const:x})
        int range = getConfigConstant(0x{range_const:x});
        return dsl().surroundingUnits(dsl().getOwnerSelector(), range, true);
    }}
"""
            if 'BondedEntitySelector' in section:
                return """    @Override
    protected Object createTargetSelector() {
        // From decompiled: bonded entity selector
        return bondedEntitySelector();
    }
"""
        return """    @Override
    protected Object createTargetSelector() {
        // From decompiled: returns dsl.ownerSelector (offset 0x148)
        return dsl().getOwnerSelector();
    }
"""

    # ApplyInternal
    if method_name == 'ApplyInternal':
        content = info['content']
        ai_idx = content.find('ApplyInternal')
        if ai_idx >= 0:
            section = content[ai_idx:ai_idx+1000]
            if 'AddSubEffect' in section:
                se_match = re.search(r'AddSubEffect[^(]*\([^,]+,[^,]+,[^,]+,0x([0-9a-fA-F]+)', section)
                se_id = int(se_match.group(1), 16) if se_match else 0
                return f"""    @Override
    protected void applyInternal(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {{
        // From decompiled: adds sub-effect 0x{se_id:x}
        addSubEffect(targetEntity, sourceEntity, 0x{se_id:x});
    }}
"""
            if 'ChangeStat' in section:
                stat_match = re.search(r'Stat\.\.ctor\([^,]+,(\d+),(\d+)', section)
                stat_id = int(stat_match.group(1)) if stat_match else 0
                change_type = int(stat_match.group(2)) if stat_match else 5
                return f"""    @Override
    protected void applyInternal(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {{
        // From decompiled: changes stat {stat_id} (changeType={change_type}) on target
        applyStatChange(targetEntity, sourceEntity, {stat_id}, {change_type});
    }}
"""
            if 'ApplyModification' in section:
                return """    @Override
    protected void applyInternal(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {
        // From decompiled: delegates to ApplyModification
        applyModification(targetEntity, sourceEntity);
    }
"""
            if 'UnitFlagsComponent_Add' in section:
                flag_match = re.search(r'UnitFlagsComponent_Add\([^,]+,0x([0-9a-fA-F]+)', section)
                flag_id = int(flag_match.group(1), 16) if flag_match else 0
                return f"""    @Override
    protected void applyInternal(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {{
        // From decompiled: adds unit flag 0x{flag_id:x}
        addUnitFlag(targetEntity, 0x{flag_id:x});
    }}
"""
        return """    @Override
    protected void applyInternal(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {
        // From decompiled: applies effect to target
    }
"""

    # RevertInternal
    if method_name == 'RevertInternal':
        content = info['content']
        ri_idx = content.find('RevertInternal')
        if ri_idx >= 0:
            section = content[ri_idx:ri_idx+1000]
            if 'ChangeStat' in section:
                stat_match = re.search(r'Stat\.\.ctor\([^,]+,(\d+),(\d+)', section)
                stat_id = int(stat_match.group(1)) if stat_match else 0
                change_type = int(stat_match.group(2)) if stat_match else 6
                return f"""    @Override
    protected void revertInternal(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {{
        // From decompiled: reverts stat {stat_id} (changeType={change_type}) on target
        revertStatChange(targetEntity, sourceEntity, {stat_id}, {change_type});
    }}
"""
            if 'UnitFlagsComponent_Remove' in section:
                flag_match = re.search(r'UnitFlagsComponent_Remove\([^,]+,0x([0-9a-fA-F]+)', section)
                flag_id = int(flag_match.group(1), 16) if flag_match else 0
                return f"""    @Override
    protected void revertInternal(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {{
        // From decompiled: removes unit flag 0x{flag_id:x}
        removeUnitFlag(targetEntity, 0x{flag_id:x});
    }}
"""
        return """    @Override
    protected void revertInternal(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {
        // From decompiled: reverts effect on target
    }
"""

    # UpdateInternal
    if method_name == 'UpdateInternal':
        if 'ApplyModification' in info['content']:
            return """    @Override
    protected void updateInternal(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {
        // From decompiled: re-applies modification
        applyModification(targetEntity, sourceEntity);
    }
"""
        return """    @Override
    protected void updateInternal(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {
        // From decompiled: updates effect on target
    }
"""

    # RefreshInternal
    if method_name == 'RefreshInternal':
        return """    @Override
    protected void refreshInternal(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {
        // From decompiled: reverts then re-applies modification
        revertModification(targetEntity, sourceEntity);
        applyModification(targetEntity, sourceEntity);
    }
"""

    # CreateDamageModifier
    if method_name == 'CreateDamageModifier':
        return """    protected Object createDamageModifier() {
        // From decompiled: creates damage bonus from config
        return createDamageModifierFromConfig();
    }
"""

    # CreateDamageDefenseModifier
    if method_name == 'CreateDamageDefenseModifier':
        return """    protected Object createDamageDefenseModifier() {
        // From decompiled: creates damage defense modifier from config
        return createDamageDefenseModifierFromConfig();
    }
"""

    # CreateTargetTrigger
    if method_name == 'CreateTargetTrigger':
        return """    @Override
    protected void createTargetTrigger() {
        // From decompiled: sets up trigger conditions
        setupTargetTrigger();
    }
"""

    # CreateTargetTriggerBehaviour
    if method_name == 'CreateTargetTriggerBehaviour':
        content = info['content']
        ttb_idx = content.find('CreateTargetTriggerBehaviour')
        if ttb_idx >= 0:
            section = content[ttb_idx:ttb_idx+500]
            if 'DeactivateEffect' in section:
                deactivate_match = re.search(r'DeactivateEffect\s*\([^,]+,[^,]+,0x([0-9a-fA-F]+)', section)
                effect_id = int(deactivate_match.group(1), 16) if deactivate_match else 0
                return f"""    @Override
    protected void createTargetTriggerBehaviour() {{
        // From decompiled: deactivates effect 0x{effect_id:x} on trigger
        dsl().deactivateEffect(dsl().getOwnerSelector(), 0x{effect_id:x});
    }}
"""
        return """    @Override
    protected void createTargetTriggerBehaviour() {
        // From decompiled: defines behaviour when trigger fires
        setupTargetTriggerBehaviour();
    }
"""

    # CreateHandleTriggerAbilitiesInternal
    if method_name == 'CreateHandleTriggerAbilitiesInternal':
        return """    @Override
    protected Object createHandleTriggerAbilitiesInternal() {
        // From decompiled: creates triggered abilities for effect lifecycle
        return createTriggeredAbilities();
    }
"""

    # CreateEffectDamageBonusForAttack
    if method_name == 'CreateEffectDamageBonusForAttack':
        return """    @Override
    protected Object createEffectDamageBonusForAttack() {
        // From decompiled: creates damage bonus applied during attack
        return createDamageBonusForAttack();
    }
"""

    # CreateEffectHitsBonusForAttack
    if method_name == 'CreateEffectHitsBonusForAttack':
        return """    @Override
    protected Object createEffectHitsBonusForAttack() {
        // From decompiled: creates hits bonus applied during attack
        return createHitsBonusForAttack();
    }
"""

    # CreateRangeBonusForMovement
    if method_name == 'CreateRangeBonusForMovement':
        return """    @Override
    protected Object createRangeBonusForMovement() {
        // From decompiled: creates movement range bonus
        return createMovementRangeBonus();
    }
"""

    # CreateCritChanceBonus
    if method_name == 'CreateCritChanceBonus':
        return """    @Override
    protected Object createCritChanceBonus() {
        // From decompiled: creates crit chance bonus
        return createCritChanceBonusFromConfig();
    }
"""

    # CreateCritDamageBonus
    if method_name == 'CreateCritDamageBonus':
        return """    @Override
    protected Object createCritDamageBonus() {
        // From decompiled: creates crit damage bonus
        return createCritDamageBonusFromConfig();
    }
"""

    # CreateAdditionalHits
    if method_name == 'CreateAdditionalHits':
        return """    @Override
    protected Object createAdditionalHits() {
        // From decompiled: creates additional hits configuration
        return createAdditionalHitsFromConfig();
    }
"""

    # CreatePiercingBonusForAttack
    if method_name == 'CreatePiercingBonusForAttack':
        return """    @Override
    protected Object createPiercingBonusForAttack() {
        // From decompiled: creates piercing bonus for attack
        return createPiercingBonusFromConfig();
    }
"""

    # CreatePiercingMalusForDefense
    if method_name == 'CreatePiercingMalusForDefense':
        return """    @Override
    protected Object createPiercingMalusForDefense() {
        // From decompiled: creates piercing malus for defense
        return createPiercingMalusFromConfig();
    }
"""

    # CreateBlockHitReductionTrigger
    if method_name == 'CreateBlockHitReductionTrigger':
        return """    @Override
    protected Object createBlockHitReductionTrigger() {
        // From decompiled: creates block/hit reduction trigger
        return createBlockHitReduction();
    }
"""

    # CreateEffectDamageMalusForDefense
    if method_name == 'CreateEffectDamageMalusForDefense':
        return """    @Override
    protected Object createEffectDamageMalusForDefense() {
        // From decompiled: creates damage malus for defense
        return createDamageMalusForDefense();
    }
"""

    # CreateEffectCappedDamageMalusForDefense
    if method_name == 'CreateEffectCappedDamageMalusForDefense':
        return """    @Override
    protected Object createEffectCappedDamageMalusForDefense() {
        // From decompiled: creates capped damage malus for defense
        return createCappedDamageMalusFromConfig();
    }
"""

    # CreateEffectCappedDamageBonusForAttack
    if method_name == 'CreateEffectCappedDamageBonusForAttack':
        return """    @Override
    protected Object createEffectCappedDamageBonusForAttack() {
        // From decompiled: creates capped damage bonus for attack
        return createCappedDamageBonusFromConfig();
    }
"""

    # CreateOverrideDamageProfile
    if method_name == 'CreateOverrideDamageProfile':
        return """    @Override
    protected Object createOverrideDamageProfile() {
        // From decompiled: overrides the damage profile type
        return createOverrideDamageProfileFromConfig();
    }
"""

    # CreateSimulationActiveCondition
    if method_name == 'CreateSimulationActiveCondition':
        return """    @Override
    protected Object createSimulationActiveCondition() {
        // From decompiled: simulation-specific active condition
        return createActiveCondition();
    }
"""

    # CreateEffectHealBonus
    if method_name == 'CreateEffectHealBonus':
        return """    @Override
    protected Object createEffectHealBonus() {
        // From decompiled: creates heal bonus
        return createHealBonusFromConfig();
    }
"""

    # CreateEffectRepairBonus
    if method_name == 'CreateEffectRepairBonus':
        return """    @Override
    protected Object createEffectRepairBonus() {
        // From decompiled: creates repair bonus
        return createRepairBonusFromConfig();
    }
"""

    # CreateRangeBonusForDangerZone
    if method_name == 'CreateRangeBonusForDangerZone':
        return """    @Override
    protected Object createRangeBonusForDangerZone() {
        // From decompiled: creates danger zone range bonus
        return createDangerZoneRangeBonus();
    }
"""

    # CreateRemoveEffectTrigger
    if method_name == 'CreateRemoveEffectTrigger':
        return """    @Override
    protected void createRemoveEffectTrigger() {
        // From decompiled: creates trigger for effect removal
        setupRemoveEffectTrigger();
    }
"""

    # get_CanBeImmuneTo
    if method_name == 'get_CanBeImmuneTo':
        return """    @Override
    public boolean canBeImmuneTo() {
        return true;
    }
"""

    # get_KeepOnRevive
    if method_name == 'get_KeepOnRevive':
        content = info['content']
        kor_idx = content.find('get_KeepOnRevive')
        if kor_idx >= 0:
            section = content[kor_idx:kor_idx+200]
            if 'return 0' in section:
                return """    @Override
    public boolean keepOnRevive() {
        return false;
    }
"""
        return """    @Override
    public boolean keepOnRevive() {
        return true;
    }
"""

    # get_KeepOnChangeOwner
    if method_name == 'get_KeepOnChangeOwner':
        content = info['content']
        kco_idx = content.find('get_KeepOnChangeOwner')
        if kco_idx >= 0:
            section = content[kco_idx:kco_idx+200]
            if 'return 0' in section:
                return """    @Override
    public boolean keepOnChangeOwner() {
        return false;
    }
"""
        return """    @Override
    public boolean keepOnChangeOwner() {
        return true;
    }
"""

    # get_Priority
    if method_name == 'get_Priority':
        content = info['content']
        p_idx = content.find('get_Priority')
        if p_idx >= 0:
            section = content[p_idx:p_idx+200]
            ret_match = re.search(r'return (\d+)', section)
            if ret_match:
                return f"""    @Override
    public int getPriority() {{
        return {ret_match.group(1)};
    }}
"""
        return """    @Override
    public int getPriority() {
        return 0;
    }
"""

    # get_RemoveOnDeathStep
    if method_name == 'get_RemoveOnDeathStep':
        content = info['content']
        rds_idx = content.find('get_RemoveOnDeathStep')
        if rds_idx >= 0:
            section = content[rds_idx:rds_idx+200]
            if 'return 0' in section:
                return """    @Override
    public boolean removeOnDeathStep() {
        return false;
    }
"""
        return """    @Override
    public boolean removeOnDeathStep() {
        return true;
    }
"""

    # get_AllowInAtomicMode
    if method_name == 'get_AllowInAtomicMode':
        return """    @Override
    public boolean allowInAtomicMode() {
        return true;
    }
"""

    # get_AlwaysCreateOneEntityPerEffect
    if method_name == 'get_AlwaysCreateOneEntityPerEffect':
        return """    @Override
    public boolean alwaysCreateOneEntityPerEffect() {
        return true;
    }
"""

    # get_HasAutomaticActivation
    if method_name == 'get_HasAutomaticActivation':
        return """    @Override
    public boolean hasAutomaticActivation() {
        return true;
    }
"""

    # get_CanTargetSteppables
    if method_name == 'get_CanTargetSteppables':
        return """    @Override
    public boolean canTargetSteppables() {
        return true;
    }
"""

    # GetDynamicStatModificationAmount
    if method_name == 'GetDynamicStatModificationAmount':
        return """    @Override
    protected int getDynamicStatModificationAmount(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {
        // From decompiled: dynamic stat modification amount
        return calculateDynamicAmount(effectEntity, ownerEntity, targetEntity, sourceEntity);
    }
"""

    # GetStatModificationType
    if method_name == 'GetStatModificationType':
        return """    @Override
    protected int getStatModificationType() {
        // From decompiled: stat modification type
        return getStatType();
    }
"""

    # GetUnitEffectType
    if method_name == 'GetUnitEffectType':
        return """    @Override
    protected int getUnitEffectType() {
        // From decompiled: unit effect type indicator
        return getEffectTypeValue();
    }
"""

    # Other property-style methods - no @Override since they may not exist in parent
    if method_name.startswith('get_'):
        prop_name = method_name[4:]
        # Known int-returning properties
        INT_PROPERTIES = {'AbilityAttackType', 'Priority', 'UnitEffectType'}
        # Known boolean-returning properties
        BOOL_PROPERTIES = {'KeepOnRevive', 'KeepOnChangeOwner', 'RemoveOnDeathStep',
                          'CanTargetSteppables', 'CanBeImmuneTo', 'AlwaysCreateOneEntityPerEffect',
                          'AllowInAtomicMode', 'HasAutomaticActivation', 'ActivateOnResurrect',
                          'RemoveOnBondedEntityDeath', 'Adjacent', 'IsDynamic', 'SkipValidityChecks'}
        if prop_name in INT_PROPERTIES:
            # Parse return value from decompiled
            content = info['content']
            idx = content.find(f'get_{prop_name}')
            ret_val = 0
            if idx >= 0:
                section = content[idx:idx+200]
                ret_match = re.search(r'return (\d+)', section)
                if ret_match:
                    ret_val = int(ret_match.group(1))
            return f"""    @Override
    public int get{prop_name}() {{
        return {ret_val};
    }}
"""
        elif prop_name in BOOL_PROPERTIES:
            content = info['content']
            idx = content.find(f'get_{prop_name}')
            ret_val = 'true'
            if idx >= 0:
                section = content[idx:idx+200]
                if 'return 0' in section:
                    ret_val = 'false'
            return f"""    public boolean {'is' if prop_name.startswith('Is') else 'get'}{prop_name}() {{
        return {ret_val};
    }}
"""
        else:
            # Unknown property - no @Override, no super call
            return f"""    public Object get{prop_name}() {{
        // From decompiled: property getter for {prop_name}
        return null;
    }}
"""

    # For methods specific to Loki abstract parents
    if method_name == 'GetStructuralAnalyserBuffedFriends':
        return """    protected Object getStructuralAnalyserBuffedFriends() {
        // From decompiled: gets buffed friends for structural analyser
        return getBuffedFriends();
    }
"""

    if method_name == 'GetAffectedUnits':
        return """    protected Object getAffectedUnits() {
        // From decompiled: gets units affected by this effect
        return getAffectedUnitsInternal();
    }
"""

    if method_name == 'GetTargetIsOnFireTileCondition':
        return """    protected Object getTargetIsOnFireTileCondition() {
        // From decompiled: condition for target being on fire tile
        return createFireTileCondition();
    }
"""

    if method_name == 'GetAttackHasValidDamageProfileCondition':
        return """    protected Object getAttackHasValidDamageProfileCondition() {
        // From decompiled: condition for valid damage profile
        return createValidDamageProfileCondition();
    }
"""

    if method_name == 'GetMovingEffectType':
        return """    protected int getMovingEffectType() {
        // From decompiled: effect type for moving state
        return getMovingType();
    }
"""

    if method_name == 'GetAdditionalRemoveTriggers':
        return """    protected Object getAdditionalRemoveTriggers() {
        // From decompiled: additional triggers for effect removal
        return createAdditionalRemoveTriggers();
    }
"""

    if method_name == 'GetHitReductionEffectType':
        return """    protected int getHitReductionEffectType() {
        // From decompiled: hit reduction effect type
        return getHitReductionType();
    }
"""

    if method_name == 'GetOverwatchExtraDamage':
        return """    protected Object getOverwatchExtraDamage() {
        // From decompiled: extra damage during overwatch
        return createOverwatchDamageBonus();
    }
"""

    if method_name == 'GetAutoAttackType':
        return """    protected int getAutoAttackType() {
        // From decompiled: auto attack type
        return getAutoAttackTypeValue();
    }
"""

    if method_name == 'GetAutoAttackUnitType':
        return """    protected int getAutoAttackUnitType() {
        // From decompiled: auto attack unit type
        return getAutoAttackUnitTypeValue();
    }
"""

    if method_name == 'GetAutoAttackEffectType':
        return """    protected Object getAutoAttackEffectType() {
        // From decompiled: auto attack effect type
        return getAutoAttackEffectTypeValue();
    }
"""

    if method_name == 'IsValidExtraMove':
        return """    protected boolean isValidExtraMove(Object unit, Object tile) {
        // From decompiled: checks if extra move to tile is valid
        return validateExtraMove(unit, tile);
    }
"""

    if method_name == 'IsNearestTileToMoveToMeleeWithEnemy':
        return """    protected boolean isNearestTileToMoveToMeleeWithEnemy(Object unit, Object tile, Object enemy) {
        // From decompiled: checks nearest tile for melee approach
        return checkNearestMeleeTile(unit, tile, enemy);
    }
"""

    if method_name == 'CreateCheckAndRemoveEffectAbilities':
        return """    protected Object createCheckAndRemoveEffectAbilities(int eventType, Object condition) {
        // From decompiled: checks and removes effect abilities
        return setupCheckAndRemove(eventType, condition);
    }
"""

    if method_name == 'GetReactivateOverwatchEffectType':
        return """    protected int getReactivateOverwatchEffectType() {
        // From decompiled: overwatch reactivation effect type
        return getReactivateType();
    }
"""

    if method_name == 'GetSourceKey':
        return """    protected Object getSourceKey() {
        // From decompiled: effect source key
        return getSourceKeyValue();
    }
"""

    if method_name == 'CreateBondedAbilityTriggerAbilities':
        return """    protected Object createBondedAbilityTriggerAbilities() {
        // From decompiled: creates bonded ability triggers
        return setupBondedTriggers();
    }
"""

    if method_name == 'ApplyModification':
        return """    protected void applyModification(Object targetEntity, Object sourceEntity) {
        // From decompiled: applies stat modification
        applyStatModification(targetEntity, sourceEntity);
    }
"""

    if method_name == 'RevertModification':
        return """    protected void revertModification(Object targetEntity, Object sourceEntity) {
        // From decompiled: reverts stat modification
        revertStatModification(targetEntity, sourceEntity);
    }
"""

    # .ctor
    if method_name == '.ctor' or method_name == 'ctor':
        return None  # Handled by constructor generation

    # Fallback
    return f"""    protected void {method_name[0].lower() + method_name[1:]}() {{
        // From decompiled: {method_name}
    }}
"""


def generate_java_class(info):
    """Generate a complete Java class file."""
    class_name = info['class_name']
    parent = info['parent']
    methods = info['methods']
    is_abs = is_abstract(class_name)

    # Build imports
    imports = set()
    parent_import = get_parent_import(parent)
    if parent_import:
        imports.add(parent_import)

    # Build class
    abstract_kw = "abstract " if is_abs else ""

    lines = []
    lines.append(f"package {PACKAGE};")
    lines.append("")

    if imports:
        for imp in sorted(imports):
            lines.append(f"import {imp};")
        lines.append("")

    lines.append("/**")
    lines.append(f" * Mirrors IdunBattle.Entities.Effects.Loki.{class_name}.")
    lines.append(f" * Decompiled methods: {len(methods)}")
    lines.append(" */")
    lines.append(f"public {abstract_kw}class {class_name} extends {parent} {{")
    lines.append("")

    # Constructor
    if parent in ('StaticStatModifierEffect', 'ADynamicStatModifierEffect',
                  'AMutantStatModifierEffect', 'AStatModifierEffect'):
        lines.append(f"    public {class_name}() {{")
        lines.append("        super();")
        lines.append("    }")
    elif parent in ('APendingAttackEffect',):
        lines.append(f"    public {class_name}() {{")
        lines.append("        super();")
        lines.append("    }")
    elif parent in ('ABondEffect',):
        lines.append(f"    public {class_name}() {{")
        lines.append("        super();")
        lines.append("    }")
    elif parent in ('CounterAttackEffect',):
        lines.append(f"    public {class_name}() {{")
        lines.append("        super();")
        lines.append("    }")
    elif parent in ('ReviveEffect',):
        lines.append(f"    public {class_name}() {{")
        lines.append("        super();")
        lines.append("    }")
    elif parent in ('HealBlockingEffect',):
        lines.append(f"    public {class_name}() {{")
        lines.append("        super();")
        lines.append("    }")
    elif parent in ('MultiValueStatEntryEffect',):
        lines.append(f"    public {class_name}() {{")
        lines.append("        super();")
        lines.append("    }")
    elif parent in ('DamageModifierAbilityEffect',):
        lines.append(f"    public {class_name}() {{")
        lines.append("        super();")
        lines.append("    }")
    elif parent in ('PlayerTurnEffect',):
        lines.append(f"    public {class_name}() {{")
        lines.append("        super();")
        lines.append("    }")
    elif parent in ('ADamageDefenseModifierAbilityEffect',):
        lines.append(f"    public {class_name}() {{")
        lines.append("        super();")
        lines.append("    }")
    elif parent in ('AReactivateOverwatchEffect',):
        lines.append(f"    public {class_name}() {{")
        lines.append("        super();")
        lines.append("    }")
    else:
        # For Loki-internal parents or BaseEffect
        if not is_abs:
            lines.append(f"    public {class_name}() {{")
            lines.append("        super();")
            lines.append("    }")
        else:
            lines.append(f"    protected {class_name}() {{")
            lines.append("        super();")
            lines.append("    }")

    lines.append("")

    # Generate methods (skip .ctor as it's handled by constructor)
    skip_methods = {'.ctor', 'ctor'}
    generated_methods = set()
    for method in methods:
        if method in skip_methods:
            continue
        body = generate_method_body(info, method)
        if body:
            lines.append(body)
            generated_methods.add(method)

    # Ensure ADynamicStatModifierEffect subclasses implement the abstract method
    if parent == 'ADynamicStatModifierEffect' and not is_abs:
        if 'GetDynamicStatModificationAmount' not in generated_methods:
            lines.append("""    @Override
    protected int getDynamicStatModificationAmount(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {
        // From decompiled: dynamic stat modification amount
        return calculateDynamicAmount(effectEntity, ownerEntity, targetEntity, sourceEntity);
    }
""")

    lines.append("}")
    lines.append("")

    return "\n".join(lines)


def generate_base_classes():
    """Generate the base effect class hierarchy."""
    classes = {}

    # BaseEffect
    classes['BaseEffect'] = f"""package {BASE_PACKAGE};

/**
 * Base class for all battle effects.
 * Mirrors IdunBattle.Entities.Effects.BaseEffect.
 * 94 methods in decompiled source.
 */
public abstract class BaseEffect {{

    private Object dslFactory;
    private Object abilityConfig;
    private Object executionHandle;
    private Object cachedActiveCondition;
    private Object cachedTargetSelector;
    private Object cachedLevel;
    private boolean hasAutomaticActivation = true;

    protected BaseEffect() {{
    }}

    // --- DSL access ---

    protected DSLAccessor dsl() {{
        return new DSLAccessor(dslFactory);
    }}

    public void setDslFactory(Object dslFactory) {{
        this.dslFactory = dslFactory;
    }}

    public void setAbilityConfig(Object abilityConfig) {{
        this.abilityConfig = abilityConfig;
    }}

    public void setExecutionHandle(Object executionHandle) {{
        this.executionHandle = executionHandle;
    }}

    // --- Properties (virtual in C#) ---

    public int getPriority() {{ return 0; }}
    public boolean hasAutomaticActivation() {{ return hasAutomaticActivation; }}
    public boolean keepOnRevive() {{ return true; }}
    public boolean keepOnChangeOwner() {{ return true; }}
    public boolean removeOnDeathStep() {{ return true; }}
    public boolean canTargetSteppables() {{ return false; }}
    public boolean canBeImmuneTo() {{ return false; }}
    public boolean alwaysCreateOneEntityPerEffect() {{ return false; }}
    public boolean allowInAtomicMode() {{ return false; }}
    public int getAbilityAttackType() {{ return 2; }}

    // --- Core lifecycle (virtual) ---

    protected Object createActiveCondition() {{ return null; }}
    protected Object createTargetSelector() {{ return null; }}
    protected Object createSimulationActiveCondition() {{ return null; }}

    protected void applyInternal(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {{}}
    protected void updateInternal(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {{}}
    protected void refreshInternal(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {{}}
    protected void revertInternal(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {{}}

    protected void createTargetTrigger() {{}}
    protected void createTargetTriggerBehaviour() {{}}
    protected void createRemoveEffectTrigger() {{}}
    protected Object createHandleTriggerAbilitiesInternal() {{ return null; }}

    // --- Bonus creation (virtual) ---

    protected Object createEffectDamageBonusForAttack() {{ return null; }}
    protected Object createEffectCappedDamageBonusForAttack() {{ return null; }}
    protected Object createEffectDamageMalusForDefense() {{ return null; }}
    protected Object createEffectCappedDamageMalusForDefense() {{ return null; }}
    protected Object createEffectHealBonus() {{ return null; }}
    protected Object createEffectRepairBonus() {{ return null; }}
    protected Object createEffectHitsBonusForAttack() {{ return null; }}
    protected Object createBlockHitReductionTrigger() {{ return null; }}
    protected Object createRangeBonusForMovement() {{ return null; }}
    protected Object createRangeBonusForDangerZone() {{ return null; }}
    protected Object createCritChanceBonus() {{ return null; }}
    protected Object createCritDamageBonus() {{ return null; }}
    protected Object createAdditionalHits() {{ return null; }}
    protected Object createOverrideDamageProfile() {{ return null; }}
    protected Object createPiercingBonusForAttack() {{ return null; }}
    protected Object createPiercingMalusForDefense() {{ return null; }}

    // --- Utility methods ---

    protected void addSubEffect(Object target, Object source, int effectTypeId) {{
        // Stub: would call DSLFactory.AddSubEffect
    }}

    protected void addSubEffectWithSameTurns(Object target, Object source, int effectTypeId) {{
        // Stub: would call DSLFactory.AddSubEffectWithSameTurns
    }}

    protected void addUnitFlag(Object target, int flagId) {{
        // Stub: would call UnitFlagsComponent.Add
    }}

    protected void removeUnitFlag(Object target, int flagId) {{
        // Stub: would call UnitFlagsComponent.Remove
    }}

    protected void applyStatChange(Object target, Object source, int statId, int changeType) {{
        // Stub: would call DSLFactory.ChangeStat
    }}

    protected void revertStatChange(Object target, Object source, int statId, int changeType) {{
        // Stub: would call DSLFactory.ChangeStat (revert)
    }}

    protected void applyStatModification(Object target, Object source) {{
        // Stub: applies stat modification via DSL
    }}

    protected void revertStatModification(Object target, Object source) {{
        // Stub: reverts stat modification via DSL
    }}

    protected int getConfigConstant(int id) {{
        // Stub: would call AbilityConfiguration.GetNumberConstant
        return 0;
    }}

    protected int getConfigVariable(int id) {{
        // Stub: would call AbilityConfiguration.GetVariableForLevel
        return 0;
    }}

    protected Object createDamageModifierFromConfig() {{
        return null;
    }}

    protected Object createDamageDefenseModifierFromConfig() {{
        return null;
    }}

    protected void setupTargetTrigger() {{}}
    protected void setupTargetTriggerBehaviour() {{}}
    protected void setupRemoveEffectTrigger() {{}}
    protected Object createTriggeredAbilities() {{ return null; }}

    protected Object createDamageBonusForAttack() {{ return null; }}
    protected Object createHitsBonusForAttack() {{ return null; }}
    protected Object createMovementRangeBonus() {{ return null; }}
    protected Object createCritChanceBonusFromConfig() {{ return null; }}
    protected Object createCritDamageBonusFromConfig() {{ return null; }}
    protected Object createAdditionalHitsFromConfig() {{ return null; }}
    protected Object createPiercingBonusFromConfig() {{ return null; }}
    protected Object createPiercingMalusFromConfig() {{ return null; }}
    protected Object createBlockHitReduction() {{ return null; }}
    protected Object createDamageMalusForDefense() {{ return null; }}
    protected Object createCappedDamageMalusFromConfig() {{ return null; }}
    protected Object createCappedDamageBonusFromConfig() {{ return null; }}
    protected Object createOverrideDamageProfileFromConfig() {{ return null; }}
    protected Object createHealBonusFromConfig() {{ return null; }}
    protected Object createRepairBonusFromConfig() {{ return null; }}
    protected Object createDangerZoneRangeBonus() {{ return null; }}
    protected int getEffectTypeValue() {{ return 0; }}

    protected int calculateDynamicAmount(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {{
        return 0;
    }}

    protected int getStatType() {{ return 0; }}

    protected Object getBuffedFriends() {{ return null; }}
    protected Object getAffectedUnitsInternal() {{ return null; }}
    protected Object createFireTileCondition() {{ return null; }}
    protected Object createValidDamageProfileCondition() {{ return null; }}
    protected int getMovingType() {{ return 0; }}
    protected Object createAdditionalRemoveTriggers() {{ return null; }}
    protected int getHitReductionType() {{ return 0; }}
    protected Object createOverwatchDamageBonus() {{ return null; }}
    protected int getAutoAttackTypeValue() {{ return 0; }}
    protected int getAutoAttackUnitTypeValue() {{ return 0; }}
    protected Object getAutoAttackEffectTypeValue() {{ return null; }}
    protected boolean validateExtraMove(Object unit, Object tile) {{ return false; }}
    protected boolean checkNearestMeleeTile(Object unit, Object tile, Object enemy) {{ return false; }}
    protected Object setupCheckAndRemove(int eventType, Object condition) {{ return null; }}
    protected int getReactivateType() {{ return 0; }}
    protected Object getSourceKeyValue() {{ return null; }}
    protected Object setupBondedTriggers() {{ return null; }}

    protected void applyModification(Object targetEntity, Object sourceEntity) {{
        applyStatModification(targetEntity, sourceEntity);
    }}

    protected void revertModification(Object targetEntity, Object sourceEntity) {{
        revertStatModification(targetEntity, sourceEntity);
    }}
}}
"""

    # AStatModifierEffect
    classes['AStatModifierEffect'] = f"""package {BASE_PACKAGE};

/**
 * Abstract stat modifier effect.
 * Mirrors IdunBattle.Entities.Effects.AStatModifierEffect.
 * Provides stat modification apply/revert lifecycle.
 */
public abstract class AStatModifierEffect extends BaseEffect {{

    protected AStatModifierEffect() {{
        super();
    }}

    @Override
    protected void applyInternal(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {{
        applyModification(targetEntity, sourceEntity);
    }}

    @Override
    protected void revertInternal(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {{
        revertModification(targetEntity, sourceEntity);
    }}
}}
"""

    # StaticStatModifierEffect
    classes['StaticStatModifierEffect'] = f"""package {BASE_PACKAGE};

/**
 * Static stat modifier with fixed values.
 * Mirrors IdunBattle.Entities.Effects.StaticStatModifierEffect.
 */
public class StaticStatModifierEffect extends AStatModifierEffect {{

    public StaticStatModifierEffect() {{
        super();
    }}
}}
"""

    # ADynamicStatModifierEffect
    classes['ADynamicStatModifierEffect'] = f"""package {BASE_PACKAGE};

/**
 * Dynamic stat modifier that recalculates on refresh.
 * Mirrors IdunBattle.Entities.Effects.ADynamicStatModifierEffect.
 */
public abstract class ADynamicStatModifierEffect extends AStatModifierEffect {{

    protected ADynamicStatModifierEffect() {{
        super();
    }}

    @Override
    protected void refreshInternal(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity) {{
        revertModification(targetEntity, sourceEntity);
        applyModification(targetEntity, sourceEntity);
    }}

    protected abstract int getDynamicStatModificationAmount(Object effectEntity, Object ownerEntity, Object targetEntity, Object sourceEntity);

    public boolean isDynamic() {{
        return true;
    }}

    public boolean skipValidityChecks() {{
        return false;
    }}
}}
"""

    # AMutantStatModifierEffect
    classes['AMutantStatModifierEffect'] = f"""package {BASE_PACKAGE};

/**
 * Mutant stat modifier effect.
 * Mirrors IdunBattle.Entities.Effects.AMutantStatModifierEffect.
 */
public abstract class AMutantStatModifierEffect extends AStatModifierEffect {{

    protected AMutantStatModifierEffect() {{
        super();
    }}
}}
"""

    # APendingAttackEffect
    classes['APendingAttackEffect'] = f"""package {BASE_PACKAGE};

/**
 * Abstract pending attack effect.
 * Mirrors IdunBattle.Entities.Effects.APendingAttackEffect.
 */
public abstract class APendingAttackEffect extends BaseEffect {{

    protected APendingAttackEffect() {{
        super();
    }}
}}
"""

    # ABondEffect
    classes['ABondEffect'] = f"""package {BASE_PACKAGE};

/**
 * Abstract bond effect connecting two entities.
 * Mirrors IdunBattle.Entities.Effects.ABondEffect.
 */
public abstract class ABondEffect extends BaseEffect {{

    protected ABondEffect() {{
        super();
    }}

    protected Object bondedEntitySelector() {{
        // Stub: returns bonded entity selector from DSL
        return null;
    }}
}}
"""

    # AReactivateOverwatchEffect
    classes['AReactivateOverwatchEffect'] = f"""package {BASE_PACKAGE};

/**
 * Abstract reactivate overwatch effect.
 * Mirrors IdunBattle.Entities.Effects.AReactivateOverwatchEffect.
 */
public abstract class AReactivateOverwatchEffect extends BaseEffect {{

    protected AReactivateOverwatchEffect() {{
        super();
    }}
}}
"""

    # CounterAttackEffect
    classes['CounterAttackEffect'] = f"""package {BASE_PACKAGE};

/**
 * Counter attack effect base.
 * Mirrors IdunBattle.Entities.Effects.CounterAttackEffect.
 */
public class CounterAttackEffect extends BaseEffect {{

    public CounterAttackEffect() {{
        super();
    }}
}}
"""

    # ReviveEffect
    classes['ReviveEffect'] = f"""package {BASE_PACKAGE};

/**
 * Revive effect base.
 * Mirrors IdunBattle.Entities.Effects.ReviveEffect.
 */
public class ReviveEffect extends BaseEffect {{

    public ReviveEffect() {{
        super();
    }}
}}
"""

    # HealBlockingEffect
    classes['HealBlockingEffect'] = f"""package {BASE_PACKAGE};

/**
 * Heal blocking effect base.
 * Mirrors IdunBattle.Entities.Effects.HealBlockingEffect.
 */
public class HealBlockingEffect extends BaseEffect {{

    public HealBlockingEffect() {{
        super();
    }}
}}
"""

    # MultiValueStatEntryEffect
    classes['MultiValueStatEntryEffect'] = f"""package {BASE_PACKAGE};

/**
 * Multi-value stat entry effect.
 * Mirrors IdunBattle.Entities.Effects.MultiValueStatEntryEffect.
 */
public class MultiValueStatEntryEffect extends BaseEffect {{

    public MultiValueStatEntryEffect() {{
        super();
    }}
}}
"""

    # DamageModifierAbilityEffect
    classes['DamageModifierAbilityEffect'] = f"""package {BASE_PACKAGE};

/**
 * Damage modifier ability effect.
 * Mirrors IdunBattle.Entities.Effects.DamageModifierAbilityEffect.
 */
public class DamageModifierAbilityEffect extends BaseEffect {{

    public DamageModifierAbilityEffect() {{
        super();
    }}
}}
"""

    # ADamageDefenseModifierAbilityEffect
    classes['ADamageDefenseModifierAbilityEffect'] = f"""package {BASE_PACKAGE};

/**
 * Abstract damage defense modifier ability effect.
 * Mirrors IdunBattle.Entities.Effects.ADamageDefenseModifierAbilityEffect.
 */
public abstract class ADamageDefenseModifierAbilityEffect extends BaseEffect {{

    protected ADamageDefenseModifierAbilityEffect() {{
        super();
    }}

    protected abstract Object createDamageDefenseModifier();
}}
"""

    # PlayerTurnEffect
    classes['PlayerTurnEffect'] = f"""package {BASE_PACKAGE};

/**
 * Player turn effect base.
 * Mirrors IdunBattle.Entities.Effects.PlayerTurnEffect.
 */
public class PlayerTurnEffect extends BaseEffect {{

    public PlayerTurnEffect() {{
        super();
    }}
}}
"""

    # DSLAccessor helper
    classes['DSLAccessor'] = f"""package {BASE_PACKAGE};

/**
 * Helper class for DSL factory method access.
 * Wraps the IL2CPP DSLFactory with typed Java methods.
 */
public class DSLAccessor {{

    private final Object factory;

    public DSLAccessor(Object factory) {{
        this.factory = factory;
    }}

    public Object getAlwaysActiveCondition() {{ return null; }}
    public Object getUnitIsAliveCondition() {{ return null; }}
    public Object getOwnerSelector() {{ return null; }}
    public Object getEffectSelector() {{ return null; }}
    public Object getSourceUnitSelector() {{ return null; }}

    public Object isCanAddUnit(Object selector) {{ return null; }}
    public Object hasTrait(Object selector, int traitId) {{ return null; }}
    public Object hasFlag(Object selector, int flagId) {{ return null; }}
    public Object hasEffect(Object selector, int effectTypeId, int minLevel, int mode) {{ return null; }}
    public Object not(Object condition) {{ return null; }}
    public Object and(Object a, Object b) {{ return null; }}
    public Object or(Object a, Object b) {{ return null; }}

    public Object surroundingUnits(Object selector, int range, boolean includeSelf) {{ return null; }}
    public Object unitsFromFaction(Object units, int factionId) {{ return null; }}

    public Object ownerIsCaster() {{ return null; }}
    public Object ownerIsTarget() {{ return null; }}
    public Object ownerIsActor() {{ return null; }}
    public Object isRangedAttack() {{ return null; }}
    public Object isMeleeAttack() {{ return null; }}
    public Object isAlive(Object selector) {{ return null; }}
    public Object isMoving(Object selector) {{ return null; }}
    public Object canMove(Object selector) {{ return null; }}

    public void deactivateEffect(Object selector, int effectTypeId) {{}}
    public Object removeEffect(Object selector) {{ return null; }}

    public Object on(int eventType, int mode) {{ return null; }}
    public Object onPreDeath(int mode, boolean flag) {{ return null; }}
    public Object onDeath(int mode, boolean flag) {{ return null; }}

    public Object triggered(Object trigger, Object behaviour) {{ return null; }}
    public Object effectSource(Object selector) {{ return null; }}
    public Object areEqual(Object a, Object b) {{ return null; }}
    public Object contains(Object collection, Object element) {{ return null; }}
    public Object tiles(Object selector) {{ return null; }}
    public Object adjacentTiles(Object selector) {{ return null; }}
    public Object safestTiles(Object tiles, Object unit) {{ return null; }}
    public Object pickRandomly(Object collection, int count) {{ return null; }}
    public Object moveUnit(Object unit, Object target) {{ return null; }}
    public Object ifCondition(Object condition, Object thenBehaviour, Object elseBehaviour) {{ return null; }}
    public Object configConst(int id, Object config) {{ return null; }}
    public Object direct(int value) {{ return null; }}
    public Object multiply(Object a, Object b) {{ return null; }}
    public Object negative(Object value) {{ return null; }}
    public Object effectConfig(int index) {{ return null; }}
    public Object statAmount(Object selector, int statId, int mode) {{ return null; }}
    public Object revive(Object unit, Object source, Object amount, int mode) {{ return null; }}
    public Object abilityHasAttackType(Object selector) {{ return null; }}
    public Object triggeringAbilityIs(Object abilityId) {{ return null; }}
    public Object conditionalAmount(Object condition, Object ifTrue, Object ifFalse) {{ return null; }}
}}
"""

    return classes


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(EFFECTS_BASE_DIR, exist_ok=True)

    # Generate base classes
    base_classes = generate_base_classes()
    for name, content in base_classes.items():
        filepath = os.path.join(EFFECTS_BASE_DIR, f"{name}.java")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Generated base: {name}.java")

    # Process all Loki effect files
    generated = 0
    errors = []

    c_files = sorted([f for f in os.listdir(DECOMPILED_DIR) if f.endswith('.c')])
    for c_file in c_files:
        filepath = os.path.join(DECOMPILED_DIR, c_file)
        try:
            info = parse_c_file(filepath)
            if info is None:
                errors.append(f"Could not parse: {c_file}")
                continue

            java_code = generate_java_class(info)
            output_path = os.path.join(OUTPUT_DIR, f"{info['class_name']}.java")
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(java_code)
            generated += 1
        except Exception as e:
            errors.append(f"Error processing {c_file}: {e}")

    print(f"\nGenerated {generated} Loki effect classes")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for err in errors:
            print(f"  - {err}")

    # Count total files
    total_java = len([f for f in os.listdir(OUTPUT_DIR) if f.endswith('.java')])
    total_base = len([f for f in os.listdir(EFFECTS_BASE_DIR) if f.endswith('.java')])
    print(f"\nTotal Java files: {total_java} (loki) + {total_base} (base) = {total_java + total_base}")


if __name__ == '__main__':
    main()
