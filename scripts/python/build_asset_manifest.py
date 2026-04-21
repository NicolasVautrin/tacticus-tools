"""
Extract unit portraits + board backgrounds from pulled Unity AssetBundles
and build a JSON manifest consumed by the browser game view.

Inputs (produced by `adb pull Bundles/...` — see frida/assets/INVESTIGATION.md):
    frida/assets/raw/Bundles/avatars/<assetNaming>_<hash>     → hero portraits (256x256)
    frida/assets/raw/Bundles/atlases/**                        → NPC portraits (128x128, atlas-packed)
    frida/assets/raw/Bundles/boards/<category>/<id>_<hash>    → 1 Texture2D per board

Outputs:
    frida/assets/public/units/<assetNaming>.png
    frida/assets/public/boards/<boardId>.png
    frida/assets/public/manifest.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.8f1"

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "frida" / "assets" / "raw" / "Bundles"
PUBLIC = ROOT / "frida" / "assets" / "public"

HASH_SUFFIX = re.compile(r"_[0-9a-f]{32}$")


def strip_hash(name: str) -> str:
    return HASH_SUFFIX.sub("", name)


def extract_avatars() -> dict[str, str]:
    """Hero portraits: 1 Sprite per bundle, named `ui_avatar_<assetNaming>` (256x256)."""
    out_dir = PUBLIC / "units"
    out_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    src = RAW / "avatars"
    if not src.exists():
        print(f"[warn] missing {src}", file=sys.stderr)
        return mapping

    bundles = sorted(p for p in src.iterdir() if p.is_file())
    for bundle in bundles:
        asset_naming = strip_hash(bundle.name)
        try:
            env = UnityPy.load(str(bundle))
        except Exception as exc:
            print(f"[skip] {bundle.name}: {exc}", file=sys.stderr)
            continue

        sprite_obj = next((o for o in env.objects if o.type.name == "Sprite"), None)
        if sprite_obj is None:
            continue

        data = sprite_obj.read()
        out = out_dir / f"{asset_naming}.png"
        data.image.save(out)
        mapping[asset_naming] = f"units/{asset_naming}.png"

    print(f"[units/heroes] extracted {len(mapping)} portraits from avatars/")
    return mapping


ATLAS_ROUND_PREFIX = "ui_image_RoundPortrait_"
ATLAS_PORTRAIT_PREFIX = "ui_image_portrait_"


def extract_atlases(existing: dict[str, str]) -> int:
    """NPC portraits live atlas-packed. Priority:
    1. `ui_image_RoundPortrait_<assetNaming>` — 128x128 round crop (preferred).
    2. `ui_image_portrait_<assetNaming>` — rectangular fallback for a handful
       of NPCs (aelda_guardian_01, astra_npc_02/03, guild_tervigon_*) that
       have no round variant.

    Skips silhouette variants and any key already in `existing` (hero avatars
    from avatars/ win since they're 256x256)."""
    src = RAW / "atlases"
    if not src.exists():
        print(f"[warn] missing {src}", file=sys.stderr)
        return 0

    out_dir = PUBLIC / "units"
    bundles = sorted(p for p in src.rglob("*") if p.is_file())

    # Pass 1: RoundPortrait.
    added_round = 0
    # Pass 2 candidates: collect (asset_naming → sprite obj) from portrait_
    # prefix while iterating, apply after pass 1 if still missing.
    rect_candidates: dict[str, object] = {}

    for bundle in bundles:
        try:
            env = UnityPy.load(str(bundle))
        except Exception as exc:
            print(f"[skip] {bundle.relative_to(src)}: {exc}", file=sys.stderr)
            continue

        for obj in env.objects:
            if obj.type.name != "Sprite":
                continue
            data = obj.read()
            name = data.m_Name
            if name.startswith(ATLAS_ROUND_PREFIX):
                asset_naming = name[len(ATLAS_ROUND_PREFIX):]
                if asset_naming in existing:
                    continue
                out = out_dir / f"{asset_naming}.png"
                data.image.save(out)
                existing[asset_naming] = f"units/{asset_naming}.png"
                added_round += 1
            elif name.startswith(ATLAS_PORTRAIT_PREFIX):
                asset_naming = name[len(ATLAS_PORTRAIT_PREFIX):]
                if asset_naming.startswith("silhouette_"):
                    continue
                rect_candidates[asset_naming] = data

    added_rect = 0
    for asset_naming, data in rect_candidates.items():
        if asset_naming in existing:
            continue
        out = out_dir / f"{asset_naming}.png"
        data.image.save(out)
        existing[asset_naming] = f"units/{asset_naming}.png"
        added_rect += 1

    print(f"[units/npcs] extracted {added_round} round + {added_rect} rect "
          f"portrait fallbacks from atlases/")
    return added_round + added_rect


VISUAL_FIELDS = (
    "Theme", "VignetteVariant", "Width", "Height",
    "PlayableMinCol", "PlayableMaxCol", "PlayableMinRow", "PlayableMaxRow",
)


def extract_boards() -> tuple[dict[str, str], dict[str, dict]]:
    """Each board bundle holds 1 Texture2D `<BoardId>_Visual` + 2 MonoBehaviour:
    the logic `BoardConfiguration` and the visual `<BoardId>_Config_Visual`.

    Returns (png_mapping, visual_mapping) — the second maps boardId →
    {Theme, PlayableMin/MaxCol/Row, Width, Height} so the frontend can place
    its hex grid on top of the PNG correctly.
    """
    out_dir = PUBLIC / "boards"
    out_dir.mkdir(parents=True, exist_ok=True)
    png_mapping: dict[str, str] = {}
    visual_mapping: dict[str, dict] = {}
    src = RAW / "boards"
    if not src.exists():
        print(f"[warn] missing {src}", file=sys.stderr)
        return png_mapping, visual_mapping

    bundles = sorted(p for p in src.rglob("*") if p.is_file())
    for bundle in bundles:
        try:
            env = UnityPy.load(str(bundle))
        except Exception as exc:
            print(f"[skip] {bundle.relative_to(src)}: {exc}", file=sys.stderr)
            continue

        tex = next((o for o in env.objects if o.type.name == "Texture2D"), None)
        if tex is None:
            continue
        tex_data = tex.read()
        board_id = re.sub(r"_Visual$", "", tex_data.m_Name).lower()
        tex_data.image.save(out_dir / f"{board_id}.png")
        png_mapping[board_id] = f"boards/{board_id}.png"

        # Read the visual MonoBehaviour (the one whose m_Name ends with _Visual)
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                tree = obj.read_typetree()
            except Exception:
                continue
            if not str(tree.get("m_Name", "")).endswith("_Visual"):
                continue
            visual_mapping[board_id] = {
                k: tree[k] for k in VISUAL_FIELDS if k in tree
            }
            break

    print(
        f"[boards] extracted {len(png_mapping)} backgrounds, "
        f"{len(visual_mapping)} visual configs"
    )
    return png_mapping, visual_mapping


def main() -> int:
    units = extract_avatars()
    extract_atlases(units)
    boards, visuals = extract_boards()

    manifest = {
        "unityVersion": UnityPy.config.FALLBACK_UNITY_VERSION,
        "units": dict(sorted(units.items())),
        "boards": dict(sorted(boards.items())),
        "boardVisuals": dict(sorted(visuals.items())),
    }
    out = PUBLIC / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2))
    print(f"[manifest] {out}")
    print(f"  units={len(units)} boards={len(boards)} visuals={len(visuals)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
