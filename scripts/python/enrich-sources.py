"""
Enrich decompiled .cs sources with field offsets and method RVAs from symbols.json.

Reads:
  - data/symbols.json (methods, enums, fields with offsets)
  - sources/**/*.cs (Il2CppDumper skeleton files)

Writes:
  - sources/**/*.cs (enriched in-place with offset comments)

Field lines:   `public System.Boolean allowCheatMode; // 0x5C`
Method lines:  `public System.Void TryUnlock(System.Action callback) { } // RVA: 0x226A0B0`
"""

import json
import os
import re
import sys

SYMBOLS_PATH = "data/symbols.json"
SOURCES_DIR = "sources"


def load_symbols():
    with open(SYMBOLS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_method_index(methods):
    """Build class.method -> offset index from flat offset->fqn map."""
    index = {}  # "Namespace.Class.Method" -> [offsets]
    for offset_hex, fqn in methods.items():
        if fqn not in index:
            index[fqn] = []
        index[fqn].append(int(offset_hex, 16))
    return index


def build_field_index(fields):
    """Build class -> {fieldName: {offset, type}} index."""
    return fields  # already keyed by class name


def infer_class_fqn(cs_path):
    """Infer the fully qualified class name from the .cs file content."""
    ns = ""
    cls = ""
    with open(cs_path, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^namespace\s+([\w.]+)", line)
            if m:
                ns = m.group(1)
            m = re.match(
                r"^\s*public\s+(?:class|struct|interface|enum|abstract\s+class|sealed\s+class|static\s+class)\s+(\S+)",
                line,
            )
            if m:
                cls = m.group(1)
                # Strip generic params and base class
                cls = re.sub(r"<.*", "", cls)
                cls = re.sub(r"\s*:.*", "", cls)
                break
    if ns and cls:
        return ns + "." + cls
    return cls or None


def enrich_file(cs_path, method_index, field_data):
    fqn = infer_class_fqn(cs_path)
    if not fqn:
        return False

    class_fields = field_data.get(fqn, [])
    field_map = {f["n"]: f for f in class_fields}

    with open(cs_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    changed = False
    new_lines = []
    for line in lines:
        stripped = line.rstrip()

        # Skip lines already enriched
        if "// 0x" in stripped or "// RVA:" in stripped:
            new_lines.append(line)
            continue

        # Try to match field declaration
        fm = re.match(
            r"^(\s*public\s+\S+\s+)(\w+)\s*;(.*)$", stripped
        )
        if fm:
            field_name = fm.group(2)
            if field_name in field_map:
                offset = field_map[field_name]["o"]
                new_line = (
                    fm.group(1)
                    + field_name
                    + "; // 0x"
                    + format(offset, "X")
                    + "\n"
                )
                new_lines.append(new_line)
                changed = True
                continue

        # Try to match method declaration
        mm = re.match(
            r"^(\s*public\s+(?:static\s+|virtual\s+|override\s+|abstract\s+)?)"
            r"(\S+)\s+"
            r"(\w+)"
            r"\s*\(([^)]*)\)"
            r"\s*\{[^}]*\}(.*)$",
            stripped,
        )
        if mm:
            method_name = mm.group(3)
            lookup = fqn + "." + method_name
            offsets = method_index.get(lookup, [])
            if offsets:
                # Use first (smallest) offset
                rva = min(offsets)
                new_line = stripped + " // RVA: 0x" + format(rva, "X") + "\n"
                new_lines.append(new_line)
                changed = True
                continue

        new_lines.append(line)

    if changed:
        with open(cs_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    return changed


def main():
    print("Loading symbols...")
    data = load_symbols()
    method_index = build_method_index(data["methods"])
    field_data = build_field_index(data.get("fields", {}))
    print(
        f"  {len(data['methods'])} methods, {len(field_data)} classes with fields"
    )

    enriched = 0
    total = 0
    for root, dirs, files in os.walk(SOURCES_DIR):
        for fname in files:
            if not fname.endswith(".cs"):
                continue
            total += 1
            cs_path = os.path.join(root, fname)
            try:
                if enrich_file(cs_path, method_index, field_data):
                    enriched += 1
            except Exception as e:
                print(f"  ERROR {cs_path}: {e}")

    print(f"Enriched {enriched}/{total} files")


if __name__ == "__main__":
    main()
