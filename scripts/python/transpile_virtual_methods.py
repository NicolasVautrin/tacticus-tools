#!/usr/bin/env python3
"""
Transpile decompiled C virtual methods (CreateBehaviour, CreateTrigger, ExecuteBehaviour)
into Java method bodies for the ability classes.

Reads each .c file's VIRTUAL METHOD OVERRIDES section, parses the DSL calls,
and generates Java method bodies that use the sentinel-based DSLFactory/DSLAccessor API.
"""

import os
import re
import sys
import glob
from pathlib import Path

# --- Configuration ---
DECOMPILED_DIR = Path(r"C:\Users\nicolasv\tacticus-tools\data\decompiled_tacticus\IdunBattleLogic\Entities\Abilities")
JAVA_DIR = Path(r"C:\Users\nicolasv\tacticus-tools\app\src\main\java\tacticus\idunbattlelogic\entities\abilities")

# --- Offset mappings ---

# BaseTriggeredAbility offsets (param_1 + offset)
TRIGGERED_FIELD_MAP = {
    0x10: "abilityConfigId",
    0x20: "config",
    0x28: "dsl",
    0x30: "state",
    0x38: "query",
    0x40: "operationProcessor",
    0x48: "effectsDatabase",
    0x50: "logger",
    0x58: "cachedTrigger",
}

# AActiveAbility offsets (param_1 + offset)
ACTIVE_FIELD_MAP = {
    0x10: "abilityType",
    0x18: "state",
    0x20: "battleQuery",
    0x28: "attackQuery",
    0x30: "dsl",
    0x38: "movementQuery",
    0x40: "operationProcessor",
    0x48: "effectsQuery",
    0x50: "logger",
    0x58: "targetingQuery",
    0x60: "config",
}

# DSLFactory field offsets (dsl + offset) -> symbolic name
DSL_FIELD_MAP = {
    0x10: "matchState",
    0x18: "prng",
    0x20: "param4",
    0x28: "param5",
    0x70: "param7",
    0xa0: "ownerIsCasterTile",
    0xa8: "preBuiltTrigger_a8",
    0xb0: "preBuiltField_b0",
    0xb8: "ZERO",
    0xc0: "ONE",
    0xc8: "TWO",
    0xd0: "HUNDRED",
    0xd8: "MINUS_ONE",
    0xe0: "resultDamage",
    0xe8: "resultHeal",
    0xf0: "currentDamageFormula",
    0xf8: "yesTrigger",
    0x100: "neverTrigger",
    0x108: "isOwnerEmptyTrigger",
    0x110: "hasActiveAbilityUsedTrigger",
    0x118: "noTrigger1",
    0x120: "noTrigger2",
    0x128: "yesTrigger2",
    0x130: "currentAbilitySelector",
    0x138: "triggeringAbilitySelector",
    0x140: "parentAbilitySelector",
    0x148: "owner",
    0x150: "effectEntity",
    0x158: "sourceUnit",
    0x160: "casterUnit",
    0x168: "casterTile",
    0x170: "targetTile",
    0x178: "targetUnit",
    0x180: "actorUnit",
    0x188: "field_188",
    0x190: "field_190",
}


def get_dsl_field(offset):
    """Convert an offset to the DSLFactory field name."""
    if isinstance(offset, str):
        offset = int(offset, 16)
    return DSL_FIELD_MAP.get(offset, f"field_0x{offset:x}")


def extract_method_blocks(c_content):
    """
    Extract method blocks from both VIRTUAL METHOD OVERRIDES and
    ABILITY HELPERS (ADDITIONAL METHODS) sections.
    Returns list of (method_type, full_body) tuples.

    method_type is:
      - "CreateBehaviour", "CreateTrigger", "ExecuteBehaviour" for virtual overrides
      - ("Helper", raw_method_name) for helper methods
    """
    methods = []

    for marker in (
        "// ========== VIRTUAL METHOD OVERRIDES ==========",
        "// ========== ABILITY HELPERS (ADDITIONAL METHODS) ==========",
    ):
        idx = c_content.find(marker)
        if idx < 0:
            continue

        # Find end of this section (start of next section or end of file)
        next_section_idx = len(c_content)
        for next_marker in (
            "// ========== VIRTUAL METHOD OVERRIDES ==========",
            "// ========== ABILITY HELPERS (ADDITIONAL METHODS) ==========",
        ):
            if next_marker == marker:
                continue
            nidx = c_content.find(next_marker, idx + len(marker))
            if 0 < nidx < next_section_idx:
                next_section_idx = nidx

        section = c_content[idx:next_section_idx]

        # Split on method headers
        header_re = re.compile(r'// === [^\n]*?\.(\w+)\s+\(RVA:[^\n]*?\)\s*===')
        headers = list(header_re.finditer(section))

        for i, hdr in enumerate(headers):
            method_name = hdr.group(1)
            start = hdr.end()
            end = headers[i + 1].start() if i + 1 < len(headers) else len(section)
            body_text = section[start:end].strip()

            # Find the function body between { and }
            brace_start = body_text.find('{')
            if brace_start < 0:
                continue
            depth = 0
            brace_end = -1
            for j in range(brace_start, len(body_text)):
                if body_text[j] == '{':
                    depth += 1
                elif body_text[j] == '}':
                    depth -= 1
                    if depth == 0:
                        brace_end = j
                        break
            if brace_end < 0:
                body = body_text[brace_start + 1:]
            else:
                body = body_text[brace_start + 1:brace_end]

            if "CreateBehaviour" in method_name and "Simulation" not in method_name:
                methods.append(("CreateBehaviour", body))
            elif "CreateTrigger" in method_name:
                methods.append(("CreateTrigger", body))
            elif "ExecuteBehaviour" in method_name:
                methods.append(("ExecuteBehaviour", body))
            elif method_name.startswith("get_"):
                # Property getter: get_FieldName → public Object getFieldName() { return ...; }
                methods.append((("Getter", method_name), body))
            elif method_name == "ctor" or method_name.startswith("_ctor"):
                # Skip constructors — already generated
                continue
            else:
                # Generic helper method
                methods.append((("Helper", method_name), body))

    return methods


def resolve_offset_field(offset_str, is_active):
    """Resolve a hex offset to a field name for 'this' pointer."""
    offset = int(offset_str, 16) if isinstance(offset_str, str) else offset_str
    field_map = ACTIVE_FIELD_MAP if is_active else TRIGGERED_FIELD_MAP
    return field_map.get(offset, f"field_0x{offset:x}")


def resolve_dsl_offset(offset_str):
    """Resolve a hex offset on the DSL factory object."""
    offset = int(offset_str, 16) if isinstance(offset_str, str) else offset_str
    return DSL_FIELD_MAP.get(offset, f"field_0x{offset:x}")


def extract_call_args_from_pos(text, start_pos):
    """Extract arguments from a function call starting at the opening paren."""
    depth = 0
    args = []
    current_arg = ""
    i = start_pos
    while i < len(text):
        ch = text[i]
        if ch == '(':
            if depth > 0:
                current_arg += ch
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                if current_arg.strip():
                    args.append(current_arg.strip())
                return args, i + 1
            current_arg += ch
        elif ch == ',' and depth == 1:
            args.append(current_arg.strip())
            current_arg = ""
        else:
            current_arg += ch
        i += 1
    return args, i


def resolve_arg(arg, var_map, is_active):
    """Resolve a function argument to a Java expression."""
    arg = arg.strip()
    if not arg:
        return "null"

    # Check variable map
    if arg in var_map:
        return var_map[arg]

    # C function params -> Java method params
    if arg == "param_1":
        return "this"
    if arg == "param_2":
        return "abilityState"
    if arg == "param_3":
        return "triggerType"
    if arg == "param_4":
        return "entities"

    # Nested dereference (most specific): *(undefined8 *)(*(long *)(param_1 + 0x28) + 0x148)
    m = re.match(
        r'\*\((?:undefined8|long|undefined4) \*\)\(\*\(long \*\)\(param_1 \+ (0x[0-9a-f]+)\) \+ (0x[0-9a-f]+)\)',
        arg
    )
    if m:
        return f"dsl.{resolve_dsl_offset(m.group(2))}"

    # Direct field access on param_1: *(undefined8 *)(param_1 + 0x20)
    m = re.match(r'\*\((?:undefined8|long|undefined4|int) \*\)\(param_1 \+ (0x[0-9a-f]+)\)', arg)
    if m:
        return resolve_offset_field(m.group(1), is_active)

    # Inline dsl field: *(undefined8 *)(lVar + 0x160)
    m = re.match(r'\*\((?:undefined8|long|undefined4) \*\)\((\w+) \+ (0x[0-9a-f]+)\)', arg)
    if m:
        base = var_map.get(m.group(1), m.group(1))
        offset = m.group(2)
        if base == "dsl" or (isinstance(base, str) and "dsl" in base.lower()):
            return f"dsl.{resolve_dsl_offset(offset)}"
        # For param_1 + offset, use the field map
        if m.group(1) == "param_1":
            return resolve_offset_field(offset, is_active)
        return f"{base}.{resolve_dsl_offset(offset)}"

    # Cast
    m = re.match(r'\((?:int|long|undefined4|uint|short)\)(.+)', arg)
    if m:
        return resolve_arg(m.group(1).strip(), var_map, is_active)

    # param_1 indexed: param_1[N]
    m = re.match(r'param_1\[(\w+)\]', arg)
    if m:
        idx = m.group(1)
        try:
            offset = int(idx, 0) * 8
            return resolve_offset_field(hex(offset), is_active)
        except ValueError:
            return f"this.field_{idx}"

    # Hex literal
    if re.match(r'^0x[0-9a-f]+$', arg, re.IGNORECASE):
        return arg

    # Decimal literal
    if re.match(r'^-?\d+$', arg):
        return arg

    # Negation
    m = re.match(r'^-(\w+)$', arg)
    if m:
        inner = var_map.get(m.group(1), m.group(1))
        return f"-{inner}"

    # Address-of
    if arg.startswith('&'):
        return "null"

    # PTR_DAT references
    if 'PTR_DAT' in arg:
        return "null"

    return var_map.get(arg, arg)


# DSL method name mapping
DSL_METHODS = {
    "Nothing": "nothing",
    "AddEffect": "addEffect",
    "AddBondEffect": "addBondEffect",
    "AddDynamicStatModifierEffect": "addDynamicStatModifierEffect",
    "AddStaticStatModifierEffect": "addStaticStatModifierEffect",
    "AddStaticStatModifierEffectToOwner": "addStaticStatModifierEffectToOwner",
    "AddTriggeredAbility": "addTriggeredAbility",
    "ActivateEffect": "activateEffect",
    "RemoveEffect": "removeEffect",
    "IncreaseEffectLevel": "increaseEffectLevel",
    "SetEffectLevel": "setEffectLevel",
    "AdjacentTiles": "adjacentTiles",
    "AdjacentUnits": "adjacentUnits",
    "AdjacentEnemies": "adjacentEnemies",
    "AdjacentFriends": "adjacentFriends",
    "Enemies": "enemies",
    "Friends": "friends",
    "Units": "units",
    "Tiles": "tiles",
    "Cache": "cache",
    "SetCache": "setCache",
    "If": "dslIf",
    "First": "first",
    "Last": "last",
    "Group": "group",
    "AtomicGroup": "atomicGroup",
    "Foreach": "foreach",
    "Maybe": "maybe",
    "Spawn": "spawn",
    "PickRandomly": "pickRandomly",
    "Randomize": "randomize",
    "Count": "count",
    "Sum": "sum",
    "Multiply": "multiply",
    "PercentageOf": "percentageOf",
    "StatAmount": "statAmount",
    "ChangeStat": "changeStat",
    "HasEffect": "hasEffect",
    "HasTrait": "hasTrait",
    "HasDeathReason": "hasDeathReason",
    "IsAlive": "isAlive",
    "IsAdjacent": "isAdjacent",
    "AreEnemies": "areEnemies",
    "AreFriends": "areFriends",
    "AreEqual": "areEqual",
    "Contains": "contains",
    "AmountIsEqual": "amountIsEqual",
    "AmountIsEqualOrGreater": "amountIsEqualOrGreater",
    "AmountIsGreater": "amountIsGreater",
    "AmountIsGreaterThanZero": "amountIsGreaterThanZero",
    "AmountIsZero": "amountIsZero",
    "Heal": "heal",
    "Kill": "kill",
    "MoveUnit": "moveUnit",
    "RemoveUnit": "removeUnit",
    "ReplaceUnit": "replaceUnit",
    "Inform": "inform",
    "InformWeapon": "informWeapon",
    "AttackWithAttackDamage": "attackWithAttackDamage",
    "AttackWithAbilityDamage": "attackWithAbilityDamage",
    "AbilityAreaDamage": "abilityAreaDamage",
    "Attack": "attack",
    "DamageProfileFromConfig": "damageProfileFromConfig",
    "KillDeadUnits": "killDeadUnits",
    "TurnsFromRounds": "turnsFromRounds",
    "RandomAmount": "randomAmount",
    "ConditionalAmount": "conditionalAmount",
    "UseActiveAbility": "useActiveAbility",
    "UseNormalAttack": "useNormalAttack",
    "UseNormalAttackIfAble": "useNormalAttackIfAble",
    "PerformAIAbility": "performAIAbility",
    "ChangeCooldown": "changeCooldown",
    "OnPreDeath": "onPreDeath",
    "OnDeath": "onDeath",
    "On": "on",
    "Direct": "direct",
    "Get": "get",
    "ConfigVar": "configVar",
    "ConfigConst": "configConst",
    "OnOwnerSpecificAbilityInit": "onOwnerSpecificAbilityInit",
    "Children": "children",
    "IsCharging": "isCharging",
    "IsPersistentData": "isPersistentData",
    "GetPersistentData": "getPersistentData",
    "SetPersistentData": "setPersistentData",
    "AddPersistentData": "addPersistentData",
    "RoundsStarted": "roundsStarted",
    "Walkable": "walkable",
    "FreeTilesOrAdjacentFreeTiles": "freeTilesOrAdjacentFreeTiles",
    "SortTilesByUtility": "sortTilesByUtility",
    "VectorFromAdjacentTo": "vectorFromAdjacentTo",
    "WithEntityId": "withEntityId",
    "CanAddUnit": "canAddUnit",
    "UnitsFromTeam": "unitsFromTeam",
    "UnitsFromTargetingOptions": "unitsFromTargetingOptions",
    "UnitsTeamId": "unitsTeamId",
    "UnitsWithTrait": "unitsWithTrait",
    "UnitsWithTraits": "unitsWithTraits",
    "UnitsWithoutTrait": "unitsWithoutTrait",
    "UnitsWithoutTraits": "unitsWithoutTraits",
    "UnitsWithId": "unitsWithId",
    "UnitsWithIds": "unitsWithIds",
    "UnitsWithVisualId": "unitsWithVisualId",
    "UnitsWithSameVisualId": "unitsWithSameVisualId",
    "UnitsWithShield": "unitsWithShield",
    "UnitsWithRangedWeapons": "unitsWithRangedWeapons",
    "UnitsWhoCanAttack": "unitsWhoCanAttack",
    "UnitsWithTriggeredAbility": "unitsWithTriggeredAbility",
    "UnitsWithUsedAbility": "unitsWithUsedAbility",
    "UnitsWithStatBiggerThan": "unitsWithStatBiggerThan",
    "UnitsThatCanHaveActiveAbilityReset": "unitsThatCanHaveActiveAbilityReset",
    "UnitsOnTilesWithEffect": "unitsOnTilesWithEffect",
    "Unobscured": "unobscured",
    "UnobscuredTiles": "unobscuredTiles",
    "ValidNormalAttackTargets": "validNormalAttackTargets",
    "EntitiesWithAnyEffect": "entitiesWithAnyEffect",
    "OwnerHasFinishedMinTurns": "ownerHasFinishedMinTurns",
    "WeaponHighestHits": "weaponHighestHits",
    "WasCrit": "wasCrit",
    "WasBlock": "wasBlock",
    "IsUnitWithVisualId": "isUnitWithVisualId",
    "HasNegativeModifier": "hasNegativeModifier",
    "VisualUnitIdFromUnit": "visualUnitIdFromUnit",
    "VisualUnitIdFromUnitId": "visualUnitIdFromUnitId",
    "TriggeringAbilityHasAttackType": "triggeringAbilityHasAttackType",
    "TilesInConeShapeForBossPlatform": "tilesInConeShapeForBossPlatform",
    "Negative": "negative",
    "MinMaxDamage": "minMaxDamage",
}

# Property getters
PROPERTY_GETTERS = {
    "get_OwnerIsTarget": "dsl.ownerIsTarget()",
    "get_OwnerIsCaster": "dsl.ownerIsCaster()",
    "get_OwnerIsActor": "dsl.ownerIsActor()",
    "get_OwnerIsCasterTile": "dsl.ownerIsCasterTile()",
    "get_OwnerIsTargetTile": "dsl.ownerIsTargetTile()",
    "get_OwnerOrOwnerTileIsTarget": "dsl.ownerOrOwnerTileIsTarget()",
    "get_CasterIsTarget": "dsl.casterIsTarget()",
    "get_IsNormalAttack": "dsl.isNormalAttack()",
    "get_IsRangedAttack": "dsl.isRangedAttack()",
    "get_IsMeleeAttack": "dsl.isMeleeAttack()",
    "IsMeleeAttack": "dsl.isMeleeAttack()",
    "IsRangedAttack": "dsl.isRangedAttack()",
    "IsNormalAttack": "dsl.isNormalAttack()",
}


def normalize_func_name(name):
    """Extract the DSL method name from a C function name."""
    # Remove common prefixes
    for prefix in [
        "IdunBattleLogic_Entities_DSLFactory_",
        "IdunBattleLogic.Entities.DSLFactory.",
        "DSLFactory__",
    ]:
        if name.startswith(prefix):
            return name[len(prefix):]

    if name.startswith("IdunBattle_DSL_AbilityTrigger_op_"):
        return "trigger_" + name[len("IdunBattle_DSL_AbilityTrigger_op_"):]
    if name.startswith("IdunBattle_DSL_AbilityBehaviour_op_"):
        return "behaviour_" + name[len("IdunBattle_DSL_AbilityBehaviour_op_"):]
    if name.startswith("IdunBattle_DSL_TargetsSelector_op_"):
        return "targets_" + name[len("IdunBattle_DSL_TargetsSelector_op_"):]
    if name.startswith("AbilityTrigger__op_"):
        return "trigger_" + name[len("AbilityTrigger__op_"):]

    if name.startswith("IdunBattle_Entities_Abilities_BaseTriggeredAbility_"):
        return "base_" + name[len("IdunBattle_Entities_Abilities_BaseTriggeredAbility_"):]
    if name.startswith("IdunBattle_Entities_Abilities_AActiveAbility_"):
        return "active_" + name[len("IdunBattle_Entities_Abilities_AActiveAbility_"):]
    if name.startswith("IdunBattle_Entities_Abilities_AOwnerEffectTriggeredAbility_"):
        return "ownerEffect_" + name[len("IdunBattle_Entities_Abilities_AOwnerEffectTriggeredAbility_"):]
    if name.startswith("IdunBattle_Configuration_AbilityConfiguration_"):
        return "config_" + name[len("IdunBattle_Configuration_AbilityConfiguration_"):]

    return name


def map_call_to_java(func_name, raw_args, var_map, is_active):
    """Map a C function call to a Java expression string."""
    norm = normalize_func_name(func_name)

    # Resolve args
    args = [resolve_arg(a, var_map, is_active) for a in raw_args]

    # Property getters
    if norm in PROPERTY_GETTERS:
        return PROPERTY_GETTERS[norm]

    # Trigger operators
    if norm == "trigger_BitwiseAnd":
        return f"dsl.triggerAnd({args[0] if args else 'null'}, {args[1] if len(args) > 1 else 'null'})"
    if norm == "trigger_BitwiseOr":
        return f"dsl.triggerOr({args[0] if args else 'null'}, {args[1] if len(args) > 1 else 'null'})"
    if norm == "trigger_LogicalNot":
        return f"dsl.triggerNot({args[0] if args else 'null'})"

    # Behaviour operators
    if norm == "behaviour_BitwiseAnd":
        return f"dsl.behaviourAnd({args[0] if args else 'null'}, {args[1] if len(args) > 1 else 'null'})"
    if norm == "behaviour_Addition":
        return f"dsl.behaviourAdd({args[0] if args else 'null'}, {args[1] if len(args) > 1 else 'null'})"

    # Targets operators
    if norm == "targets_Addition":
        return f"dsl.targetsAdd({args[0] if args else 'null'}, {args[1] if len(args) > 1 else 'null'})"
    if norm == "targets_Subtraction":
        return f"dsl.targetsSub({args[0] if args else 'null'}, {args[1] if len(args) > 1 else 'null'})"
    if norm == "targets_BitwiseAnd":
        return f"dsl.targetsAnd({args[0] if args else 'null'}, {args[1] if len(args) > 1 else 'null'})"
    if norm.startswith("targets_"):
        op = norm[len("targets_"):]
        return f"dsl.targets{op}({', '.join(args)})"

    # Base class methods
    base_methods = {
        "base_get_AbilityType": "getAbilityType()",
        "base_get_AbilityStateReference": "getAbilityStateReference()",
        "base_get_AbilityConfigId": "getAbilityConfigId()",
        "base_MinMaxDamage": "minMaxDamage(abilityState)",
        "base_MinMaxDamage2": "minMaxDamage2(abilityState)",
        "base_GetHits": "getHits()",
        "base_GetHits2": "getHits2()",
        "base_GetDamageProfileOrDefault": "getDamageProfile()",
        "base_DmgDamage": "dmgDamage(abilityState)",
    }
    if norm in base_methods:
        return base_methods[norm]

    # Active ability methods
    active_methods = {
        "active_get_AbilityStateReference": "getAbilityStateReference()",
        "active_Execute": "execute(abilityState, entities)",
        "active_ExecuteAtomic": "executeAtomic(abilityState, entities)",
        "active_MinMaxDamage": "minMaxDamage(abilityState)",
        "active_MinMaxDamageAverage": "minMaxDamageAverage(abilityState)",
        "active_GetHits": "getHits()",
        "active_GetDamageProfile": "getDamageProfile()",
    }
    if norm in active_methods:
        return active_methods[norm]

    # Configuration methods
    if norm == "config_GetVariableForLevel":
        # args: config, constId, abilityState, triggerType, ...
        filtered = [a for a in args[1:] if a not in ('0',)]
        return f"config.getVariableForLevel({', '.join(args[1:4])})"
    if norm == "config_GetNumberConstant":
        return f"config.getNumberConstant({args[1] if len(args) > 1 else args[0]})"
    if norm == "config_GetStringConstant":
        return f"config.getStringConstant({args[1] if len(args) > 1 else args[0]})"
    if norm == "config_GetDamageProfile":
        return "config.getDamageProfile()"

    # AbilityOrEffect.op_Implicit - type conversion, skip
    if "AbilityOrEffect" in func_name and "op_Implicit" in func_name:
        return None

    # DSL methods - first arg is dsl reference, rest are actual args
    if norm in DSL_METHODS:
        java_method = DSL_METHODS[norm]
        actual = args[1:] if len(args) > 1 else []
        # Remove the last arg only if it's the trailing 0 (Ghidra adds a method info pointer)
        # Only remove the very last 0 (it's the il2cpp method descriptor)
        if actual and actual[-1] == '0':
            actual = actual[:-1]
        return f"dsl.{java_method}({', '.join(actual)})"

    # Generic ability method calls
    if "IdunBattleLogic_Entities_Abilities_" in func_name:
        # Extract method name
        parts = func_name.split('_')
        method = parts[-1] if parts else func_name
        method = method[0].lower() + method[1:] if method else method
        return f"{method}({', '.join(args)})"

    return None


def transpile_body(body, method_type, is_active):
    """
    Transpile a C method body into a list of Java statements.
    """
    java_stmts = []
    var_map = {}
    var_counter = [0]
    last_result = [None]

    def new_var():
        var_counter[0] += 1
        return f"v{var_counter[0]}"

    # Check for simple pattern: just returns a DSL field
    m = re.search(
        r'return \*\((?:undefined8|long) \*\)\(\*\(long \*\)\(param_1 \+ (0x[0-9a-f]+)\) \+ (0x[0-9a-f]+)\)',
        body
    )
    if m:
        dsl_field = resolve_dsl_offset(m.group(2))
        return [f"return dsl.{dsl_field};"]

    # Check for simple nothing pattern
    if re.search(r'DSLFactory_Nothing|DSLFactory\.Nothing', body) and body.count('DSLFactory') <= 2:
        return ["return dsl.nothing();"]

    # Pre-process: join multi-line statements (continuation lines)
    raw_lines = body.split('\n')
    joined_lines = []
    current = ""
    for raw_line in raw_lines:
        stripped = raw_line.strip()
        if not stripped:
            if current:
                joined_lines.append(current)
                current = ""
            continue
        current = (current + " " + stripped) if current else stripped
        # Check if statement is complete (ends with ; or { or })
        if stripped.endswith(';') or stripped.endswith('{') or stripped == '}':
            joined_lines.append(current)
            current = ""
    if current:
        joined_lines.append(current)

    lines = joined_lines

    for line in lines:
        line = line.strip()
        if not line or line == ';' or line == '{' or line == '}' or line == 'return;':
            continue

        # Skip noise
        if any(x in line for x in ['il2cpp_', 'DAT_', 'PTR_DAT_', 'thunk_', 'puVar',
                                     'WARNING:', 'Subroutine', 'System.Object',
                                     'memmove', 'memcpy', '__ctor', 'il2cpp_codegen',
                                     'local_', 'uStack_', 'auStack_']):
            # But keep lines that also have DSL calls
            if not any(x in line for x in ['DSLFactory', 'AbilityTrigger', 'AbilityBehaviour',
                                            'TargetsSelector', 'AbilityConfiguration',
                                            'BaseTriggeredAbility', 'AActiveAbility',
                                            'AOwnerEffectTriggeredAbility']):
                continue

        # Handle variable declarations that are just type declarations
        if re.match(r'^(undefined[0-9]*|long|int|short|char|void|bool|float|double)\s+\w+;$', line):
            continue

        # Handle field access stored to local var: lVar2 = *(long *)(param_1 + 0x28);
        m = re.match(
            r'(\w+)\s*=\s*\*\((?:long|undefined8|undefined4) \*\)\(param_1 \+ (0x[0-9a-f]+)\)\s*;',
            line
        )
        if m:
            var_map[m.group(1)] = resolve_offset_field(m.group(2), is_active)
            continue

        # Handle DSL field access: uVar2 = *(undefined8 *)(lVar5 + 0x160);
        m = re.match(
            r'(\w+)\s*=\s*\*\((?:undefined8|long|undefined4) \*\)\((\w+) \+ (0x[0-9a-f]+)\)\s*;',
            line
        )
        if m:
            base = var_map.get(m.group(2), m.group(2))
            offset = m.group(3)
            if base == "dsl" or "dsl" in str(base).lower():
                var_map[m.group(1)] = f"dsl.{resolve_dsl_offset(offset)}"
            else:
                var_map[m.group(1)] = f"{base}.{resolve_dsl_offset(offset)}"
            continue

        # Handle simple conditions
        if re.match(r'if\s*\(', line):
            continue

        # Find function calls in this line
        # Pattern: result = FuncName(args); or FuncName(args);
        # We need to find all recognized function calls

        call_patterns = [
            r'(\w+)\s*=\s*((?:IdunBattleLogic[\w.]*|DSLFactory[\w.]*|IdunBattle[\w.]*|AbilityTrigger[\w.]*)\w*)\s*\(',
            r'()((?:IdunBattleLogic[\w.]*|DSLFactory[\w.]*|IdunBattle[\w.]*|AbilityTrigger[\w.]*)\w*)\s*\(',
        ]

        matched = False
        for pat in call_patterns:
            m = re.search(pat, line)
            if m:
                result_var = m.group(1).strip() if m.group(1).strip() else None
                func_name = m.group(2)

                # Extract args
                paren_pos = line.find('(', m.start(2))
                if paren_pos >= 0:
                    raw_args, _ = extract_call_args_from_pos(line, paren_pos)
                else:
                    raw_args = []

                java_call = map_call_to_java(func_name, raw_args, var_map, is_active)

                if java_call is not None:
                    if result_var:
                        vname = new_var()
                        var_map[result_var] = vname
                        last_result[0] = vname
                        java_stmts.append(f"Object {vname} = {java_call};")
                    else:
                        last_result[0] = java_call
                        java_stmts.append(f"{java_call};")
                    matched = True
                    break

        if matched:
            continue

        # Handle return statements
        m = re.match(r'return\s+(.*);', line)
        if m:
            expr = m.group(1).strip()
            resolved = resolve_arg(expr, var_map, is_active)
            java_stmts.append(f"return {resolved};")
            continue

    # Remove duplicate consecutive statements
    deduped = []
    for s in java_stmts:
        if not deduped or s != deduped[-1]:
            deduped.append(s)
    java_stmts = deduped

    # Sanitize statements: convert anything containing raw C syntax to a TODO comment
    # so the generated Java compiles.
    BAD_PATTERNS = [
        r'\*+\(undefined',                     # raw pointer dereference (incl. **)
        r'\*+\(long \*+\)',                    # raw long pointer(s)
        r'\*+\(int \*+\)',
        r'field_0x',                            # unresolved field offset
        r'\b[a-z]{1,3}Var\d+\b',                # Ghidra auto-named locals: lVar1, uVar2, iVar1, pVar1, puVar1, piVar1, ppVar1, etc.
        r'\bauStack_',
        r'\blocal_[0-9a-f]+',
        r'\bextraout_',
        r'\bparam_[1-9]\b',                     # raw C param (param_1..9) - only if not transpiled
        r'\bDAT_[0-9a-f]+',                     # raw data references
        r'\bPTR_[A-Z]+_[0-9a-f]+',              # pointer table references
        r'undefined\d* \*',                     # any "undefined N *" cast
    ]
    bad_re = re.compile('|'.join(BAD_PATTERNS))

    sanitized = []
    for s in java_stmts:
        if bad_re.search(s):
            # Replace the whole statement with a TODO comment.
            # Escape so multi-line or braces don't break Java.
            safe = s.replace('*/', '*\\/')
            sanitized.append(f"// TODO: manual transpile: {safe}")
        else:
            sanitized.append(s)
    java_stmts = sanitized

    # If the last statement was replaced by a TODO, drop trailing TODO-only tail
    # so that method still produces a valid return.
    while java_stmts and java_stmts[-1].startswith("// TODO:"):
        java_stmts.pop()

    # Also clear last_result[0] if it references a bad pattern (otherwise it
    # will be re-injected below as `return {last_result[0]};`).
    if last_result[0] and bad_re.search(str(last_result[0])):
        last_result[0] = None

    # Smart dedup: if a void call is immediately followed by return of same expression
    # e.g., "dsl.foo(a, b);" then "return dsl.foo(a, b);" -> just "return dsl.foo(a, b);"
    cleaned = []
    for i, s in enumerate(java_stmts):
        if i + 1 < len(java_stmts):
            next_s = java_stmts[i + 1]
            if next_s.startswith("return ") and s.endswith(";") and not s.startswith("return ") \
                    and not s.startswith("Object "):
                expr = s.rstrip(";").strip()
                ret_expr = next_s[len("return "):].rstrip(";").strip()
                if expr == ret_expr:
                    continue  # Skip the void call, keep the return
        cleaned.append(s)
    java_stmts = cleaned

    # Normalize method_type for comparison (tuples for helpers/getters)
    mt_name = method_type if isinstance(method_type, str) else method_type[0]

    # Add return if needed
    if mt_name in ("CreateTrigger", "CreateBehaviour", "Helper", "Getter"):
        if not java_stmts or not java_stmts[-1].strip().startswith("return"):
            if last_result[0]:
                last = java_stmts[-1] if java_stmts else ""
                expected_void = f"{last_result[0]};"
                if last == expected_void:
                    java_stmts[-1] = f"return {last_result[0]};"
                else:
                    java_stmts.append(f"return {last_result[0]};")
            elif mt_name == "CreateTrigger":
                java_stmts.append("return dsl.noTrigger2;")
            elif mt_name == "CreateBehaviour":
                java_stmts.append("return dsl.nothing();")
            else:
                java_stmts.append("return null;")

    if not java_stmts:
        if mt_name == "CreateTrigger":
            return ["return dsl.noTrigger2;"]
        elif mt_name == "CreateBehaviour":
            return ["return dsl.nothing();"]
        elif mt_name == "ExecuteBehaviour":
            return ["// Transpiled from decompiled C (no DSL calls found)"]
        elif mt_name in ("Helper", "Getter"):
            return ["return null;"]

    return java_stmts


def get_java_class_info(java_path):
    """Extract class info from Java file."""
    with open(java_path, 'r', encoding='utf-8') as f:
        content = f.read()

    is_active = "extends AActiveAbility" in content or "extends ANormalAttackAbility" in content
    is_triggered = not is_active

    has_create_trigger = "createTrigger()" in content
    has_create_behaviour = "createBehaviour(" in content
    has_execute_behaviour = "executeBehaviour(" in content

    return {
        "is_active": is_active,
        "is_triggered": is_triggered,
        "has_create_trigger": has_create_trigger,
        "has_create_behaviour": has_create_behaviour,
        "has_execute_behaviour": has_execute_behaviour,
        "content": content,
    }


def rebuild_java_file(java_content, transpiled_methods, is_active):
    """
    Rebuild the Java file with transpiled method bodies.
    Replaces existing method bodies and adds missing methods.
    """
    # Strategy: find each method and replace its body using brace matching
    # If a method doesn't exist, add it before the class closing brace

    result = java_content

    for method_type, stmts in transpiled_methods:
        body_text = "\n".join(f"        {s}" for s in stmts)

        # Tuple form for helpers/getters: (kind, raw_method_name)
        if isinstance(method_type, tuple):
            kind, raw_name = method_type

            if kind == "Getter":
                # get_FieldName → getFieldName()
                field = raw_name[4:]  # strip "get_"
                java_name = "get" + field[0].upper() + field[1:] if field else raw_name
                method_sig = f"public Object {java_name}()"
                result = replace_or_add_method(result, method_sig, body_text, "Object")

            elif kind == "Helper":
                # PascalCase → camelCase
                java_name = raw_name[0].lower() + raw_name[1:] if raw_name else raw_name
                # Reserve common parameter hint: helpers with "param_2" usually take abilityState
                body_has_ability_state = any("abilityState" in s for s in stmts)
                body_has_trigger_type = any("triggerType" in s for s in stmts)
                body_has_entities = any("entities" in s for s in stmts)
                params = []
                if body_has_ability_state:
                    params.append("Object abilityState")
                if body_has_trigger_type:
                    params.append("Object triggerType")
                if body_has_entities:
                    params.append("AbilityEntities entities")
                method_sig = f"public Object {java_name}({', '.join(params)})"
                result = replace_or_add_method(result, method_sig, body_text, "Object")

            continue

        if method_type == "CreateTrigger":
            method_sig = "protected Object createTrigger()"
            result = replace_or_add_method(result, method_sig, body_text, "Object")

        elif method_type == "CreateBehaviour":
            if is_active:
                method_sig = "public Object createBehaviour(Object abilityState, Object triggerType)"
            else:
                method_sig = "protected Object createBehaviour(Object abilityState, Object triggerType)"
            result = replace_or_add_method(result, method_sig, body_text, "Object")

        elif method_type == "ExecuteBehaviour":
            method_sig = "public void executeBehaviour(Object abilityState, AbilityEntities entities)"
            result = replace_or_add_method(result, method_sig, body_text, "void")

    return result


def replace_or_add_method(java_content, method_sig, body_text, return_type):
    """Replace an existing method body or add the method if missing."""
    # Extract just the method name for searching
    method_name_match = re.search(r'(\w+)\s*\(', method_sig)
    if not method_name_match:
        return java_content
    method_name = method_name_match.group(1)

    # Try to find the existing method
    # Pattern: optional @Override, then the method signature, then {
    escaped_name = re.escape(method_name)
    pattern = re.compile(
        r'([ \t]*@Override\s*\n)?'
        r'([ \t]*(?:protected|public)\s+\w+\s+' + escaped_name + r'\s*\([^)]*\)\s*\{)',
        re.DOTALL
    )

    m = pattern.search(java_content)
    if m:
        # Found existing method - replace its body
        open_brace_pos = m.end() - 1  # position of {
        depth = 1
        pos = open_brace_pos + 1
        while pos < len(java_content) and depth > 0:
            if java_content[pos] == '{':
                depth += 1
            elif java_content[pos] == '}':
                depth -= 1
            pos += 1

        if depth != 0:
            return java_content

        # Build replacement
        override = m.group(1) or "    @Override\n"
        decl = m.group(2)
        new_method = f"{override}{decl}\n{body_text}\n    }}"

        return java_content[:m.start()] + new_method + java_content[pos:]

    else:
        # Method doesn't exist - add it before the last }
        last_brace = java_content.rfind('}')
        if last_brace < 0:
            return java_content

        new_method = f"\n    @Override\n    {method_sig} {{\n{body_text}\n    }}\n"
        return java_content[:last_brace] + new_method + java_content[last_brace:]


def process_all_files():
    """Process all matching C and Java file pairs."""
    c_files = []
    for c_path in DECOMPILED_DIR.rglob("*.c"):
        with open(c_path, 'r', encoding='utf-8') as f:
            content = f.read()
        if "VIRTUAL METHOD OVERRIDES" in content:
            c_files.append((c_path, content))

    print(f"Found {len(c_files)} C files with virtual method overrides")

    updated = 0
    skipped = 0
    no_java = 0
    errors = 0

    for c_path, c_content in c_files:
        class_name = c_path.stem
        # Search recursively for the Java file (may be in active/, active/loki/, etc.)
        matches = list(JAVA_DIR.rglob(f"{class_name}.java"))
        if not matches:
            no_java += 1
            continue
        java_path = matches[0]

        try:
            class_info = get_java_class_info(java_path)
            methods = extract_method_blocks(c_content)

            if not methods:
                skipped += 1
                continue

            transpiled = []
            for method_type, body in methods:
                stmts = transpile_body(body, method_type, class_info["is_active"])
                if stmts:
                    transpiled.append((method_type, stmts))

            if not transpiled:
                skipped += 1
                continue

            new_content = rebuild_java_file(
                class_info["content"], transpiled, class_info["is_active"]
            )

            if new_content != class_info["content"]:
                with open(java_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                updated += 1
                if updated % 50 == 0:
                    print(f"  ... updated {updated} files")
            else:
                skipped += 1

        except Exception as e:
            errors += 1
            print(f"  ERROR processing {class_name}: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()

    print(f"\nResults:")
    print(f"  Updated: {updated}")
    print(f"  Skipped (no changes): {skipped}")
    print(f"  No Java file: {no_java}")
    print(f"  Errors: {errors}")

    return updated


if __name__ == "__main__":
    updated = process_all_files()
    if updated > 0:
        print(f"\nSuccessfully transpiled {updated} files.")
    else:
        print("\nNo files were updated.")
