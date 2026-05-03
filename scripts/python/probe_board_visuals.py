"""
Dump the FULL typetree of every MonoBehaviour in a list of board bundles, so
we can inspect any field we currently ignore (camera bounds, world origin,
cell size, anchor, etc.). Used to investigate grid/board misalignment in
the front-end overlay.

Usage:
    python scripts/python/probe_board_visuals.py c1_06 c1_07 c1_09

Outputs JSON to stdout (pretty-printed) — pipe to a file or | jq.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.8f1"

DEFAULT_INSTALL = Path(
    os.environ.get(
        "TACTICUS_INSTALL",
        os.path.expanduser("~/AppData/Local/tacticus/games/nb3o9lmt6c"),
    )
)
BOARDS_DIR = DEFAULT_INSTALL / "Tacticus_Data" / "StreamingAssets" / "Bundles" / "boards"


def find_bundle(board_id: str) -> Path | None:
    if not BOARDS_DIR.exists():
        return None
    for bundle in BOARDS_DIR.rglob(f"{board_id}_*"):
        if bundle.is_file():
            return bundle
    return None


def _coerce(v):
    """Convert UnityPy scalar/dict/list types to plain JSON-friendly values."""
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, dict):
        return {k: _coerce(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_coerce(x) for x in v]
    return repr(v)


def dump_bundle(board_id: str) -> dict:
    bundle_path = find_bundle(board_id)
    if not bundle_path:
        return {"board_id": board_id, "error": "bundle not found"}

    env = UnityPy.load(str(bundle_path))
    out = {
        "board_id": board_id,
        "bundle_path": str(bundle_path.relative_to(BOARDS_DIR.parent.parent)),
        "object_types": {},
        "monobehaviours": [],
        "scriptable_objects": [],
    }

    for obj in env.objects:
        t = obj.type.name
        out["object_types"][t] = out["object_types"].get(t, 0) + 1

    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            tree = obj.read_typetree()
        except Exception as exc:
            out["monobehaviours"].append({"error": f"typetree failed: {exc}"})
            continue
        out["monobehaviours"].append({
            "m_Name": tree.get("m_Name", ""),
            "fields": _coerce(tree),
        })

    return out


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: probe_board_visuals.py <board_id> [<board_id> ...]",
              file=sys.stderr)
        return 1
    result = [dump_bundle(b) for b in argv]
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False, default=repr)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
