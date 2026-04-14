"""Rebuild i2_lookup.json from symbols.json enums + i2_en.json.

Direct mapping: enum name → I2 key → stripped description.
No fuzzy matching. Run from the tacticus workdir:

    python scripts/rebuild-i2-lookup.py
"""

import json
import re
import sys
from pathlib import Path

WORKDIR = Path(__file__).resolve().parent.parent

# Tag stripping: remove <style="...">, </style>, <link="...">, </link>
# Keep <i>, </i> and inner text of all tags.
_STRIP_RE = re.compile(r"</?(?:style|link)[^>]*>")


def strip_tags(text: str) -> str:
    return _STRIP_RE.sub("", text)


def _name_variants(name: str) -> list[str]:
    """Generate name variants by progressively stripping _Suffix then Prefix_."""
    variants = [name]
    # Strip suffixes: A_B_C → A_B → A
    parts = name.split("_")
    for i in range(len(parts) - 1, 0, -1):
        variants.append("_".join(parts[:i]))
    # Strip prefixes: A_B_C → B_C
    for i in range(1, len(parts)):
        variants.append("_".join(parts[i:]))
    return variants


def build_section(enum_map: dict[str, str], i2: dict[str, str],
                  key_pattern: str) -> tuple[dict[str, dict[str, str]], int]:
    """Map enum int→name, look up I2 key, return ({int_str: {description}}, fallback_count)."""
    result = {}
    fallbacks = 0
    for int_val, name in enum_map.items():
        for i, variant in enumerate(_name_variants(name)):
            key = key_pattern.format(name=variant)
            raw = i2.get(key)
            if raw:
                result[int_val] = {"description": strip_tags(raw)}
                if i > 0:
                    fallbacks += 1
                break
    return result, fallbacks


def main():
    symbols_path = WORKDIR / "symbols.json"
    i2_path = WORKDIR / "i2_en.json"
    output_path = WORKDIR / "i2_lookup.json"

    print(f"Loading {symbols_path.name}...")
    with open(symbols_path, encoding="utf-8") as f:
        syms = json.load(f)
    enums = syms.get("enums", {})

    print(f"Loading {i2_path.name}...")
    with open(i2_path, encoding="utf-8") as f:
        i2 = json.load(f)

    # --- Active abilities ---
    active_enum = enums.get("IdunBattle.Entities.Enum.ActiveAbilityType", {})
    active, af = build_section(active_enum, i2,
                               "Abilities/{name}_CurrentLevelDescription")
    print(f"  active: {len(active)}/{len(active_enum)} ({af} via variant)")

    # --- Triggered abilities ---
    trig_enum = enums.get("IdunBattle.Entities.Enum.TriggeredAbilityType", {})
    triggered, tf = build_section(trig_enum, i2,
                                  "Abilities/{name}_CurrentLevelDescription")
    print(f"  triggered: {len(triggered)}/{len(trig_enum)} ({tf} via variant)")

    # --- Traits ---
    trait_enum = enums.get("IdunBattle.Entities.Enum.UnitTrait", {})
    traits, trf = build_section(trait_enum, i2, "Traits/{name}_Description")
    print(f"  traits: {len(traits)}/{len(trait_enum)} ({trf} via variant)")

    # --- Effects ---
    # Effect I2 keys are less consistent. Try multiple sources in order:
    #   1. UnitEffects/{name}_Description              (direct)
    #   2. UnitEffects/{name}_UnitEffect_Description   (some add _UnitEffect)
    #   3. UnitEffects/{parent}_Description            (sub-effects → parent)
    #   4. Abilities/{name}_CurrentLevelDescription    (effect = ability)
    #   5. Traits/{parent}_Description                 (effect from trait)
    effect_enum = enums.get("IdunBattle.Entities.Enum.EffectType", {})
    _JUNK = {"None", "UNKNOWN"}
    effects = {}
    stats = {"direct": 0, "parent_ue": 0, "ability": 0, "trait": 0}
    for int_val, name in effect_enum.items():
        if name in _JUNK or name.startswith("Test"):
            continue
        parent = name.rsplit("_", 1)[0] if "_" in name else None
        # UnitEffects direct / _UnitEffect variant
        for pattern in [
            f"UnitEffects/{name}_Description",
            f"UnitEffects/{name}_UnitEffect_Description",
        ]:
            raw = i2.get(pattern)
            if raw:
                effects[int_val] = {"description": strip_tags(raw)}
                stats["direct"] += 1
                break
        else:
            # UnitEffects parent
            if parent:
                raw = i2.get(f"UnitEffects/{parent}_Description")
                if raw:
                    effects[int_val] = {"description": strip_tags(raw)}
                    stats["parent_ue"] += 1
                    continue
            # Abilities exact name
            raw = i2.get(f"Abilities/{name}_CurrentLevelDescription")
            if raw:
                effects[int_val] = {"description": strip_tags(raw)}
                stats["ability"] += 1
                continue
            # Traits via parent name
            if parent:
                raw = i2.get(f"Traits/{parent}_Description")
                if raw:
                    effects[int_val] = {"description": strip_tags(raw)}
                    stats["trait"] += 1
    detail = ", ".join(f"{v} {k}" for k, v in stats.items() if v)
    print(f"  effects: {len(effects)}/{len(effect_enum)} ({detail})")

    # --- Write output ---
    lookup = {
        "active": active,
        "triggered": triggered,
        "effects": effects,
        "traits": traits,
    }
    total = sum(len(v) for v in lookup.values())

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(lookup, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {output_path.name}: {total} entries")
    print(f"  (was: 209 active, 368 triggered, 263 effects, 57 traits = 897)")


if __name__ == "__main__":
    main()