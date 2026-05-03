"""
Extract unit portraits + ability icons + board backgrounds from Unity
AssetBundles and build a JSON manifest consumed by the browser game view.

Inputs:
    frida/assets/raw/Bundles/avatars/<assetNaming>_<hash>     → hero portraits (256x256)
    frida/assets/raw/Bundles/atlases/**                        → NPC portraits (128x128, atlas-packed)
    frida/assets/raw/Bundles/boards/<category>/<id>_<hash>    → 1 Texture2D per board
    <Tacticus install>/Tacticus_Data/StreamingAssets/Bundles/abilities/{active2,triggered,triggered2}/<name>_<hash>.resource

Outputs:
    frida/assets/public/units/<assetNaming>.png
    frida/assets/public/abilities/<abilityKey>.png
    frida/assets/public/boards/<boardId>.png
    frida/assets/public/manifest.json
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.8f1"

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "frida" / "assets" / "raw" / "Bundles"
PUBLIC = ROOT / "frida" / "assets" / "public"

# Default install path (Windows). Override via TACTICUS_INSTALL env var.
DEFAULT_TACTICUS_INSTALL = Path(
    os.environ.get(
        "TACTICUS_INSTALL",
        os.path.expanduser("~/AppData/Local/tacticus/games/nb3o9lmt6c"),
    )
)

HASH_SUFFIX = re.compile(r"_[0-9a-f]{32}(?:\.resource)?$")


def strip_hash(name: str) -> str:
    return HASH_SUFFIX.sub("", name)


# Live game bundles (Windows install) take priority over the Android-pulled
# `frida/assets/raw/Bundles/` snapshot, which can lag by 1+ patch cycles.
# When the install path is missing or has fewer entries than the raw pull
# (rare), fall back to RAW.
INSTALL_BUNDLES = (
    DEFAULT_TACTICUS_INSTALL / "Tacticus_Data" / "StreamingAssets" / "Bundles"
)


def _bundle_dir(name: str) -> Path:
    """Resolve a bundle subdir (avatars/atlases/boards/abilities/languages),
    preferring the live install when it exists, falling back to the
    Android raw pull. The install path is queried fresh each call so a
    user override via `TACTICUS_INSTALL` env var is honoured."""
    install = INSTALL_BUNDLES / name
    if install.exists():
        return install
    return RAW / name


def extract_avatars() -> dict[str, str]:
    """Hero portraits: 1 Sprite per bundle, named `ui_avatar_<assetNaming>` (256x256)."""
    out_dir = PUBLIC / "units"
    out_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    src = _bundle_dir("avatars")
    if not src.exists():
        print(f"[warn] missing {src}", file=sys.stderr)
        return mapping

    print(f"[units/heroes] reading from {src}")
    bundles = sorted(p for p in src.iterdir() if p.is_file())
    for bundle in bundles:
        # Both `<name>_<hash>` (Android pull) and `<name>_<hash>.resource`
        # (Windows install) flavours need the hash + extension stripped.
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
    src = _bundle_dir("atlases")
    if not src.exists():
        print(f"[warn] missing {src}", file=sys.stderr)
        return 0

    print(f"[units/npcs] reading from {src}")
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
    src = _bundle_dir("boards")
    if not src.exists():
        print(f"[warn] missing {src}", file=sys.stderr)
        return png_mapping, visual_mapping
    print(f"[boards] reading from {src}")

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


def extract_languages() -> tuple[dict[str, str], dict[str, dict]]:
    """Extract I2 Localization terms from each language bundle.

    Each language `.resource` ships a single `LanguageSourceAsset` MonoBehaviour
    whose typetree exposes `mSource.mTerms` — a list of {Term, TermType,
    Languages, Flags}. `Languages[0]` is the localized string for the bundle's
    target language.

    We dump a flat `{ "Term/Path": "value", ... }` JSON per language. The
    front-end resolves placeholders like `{[Term/Path]}` (nested term lookup)
    and `{[varName]}` (runtime tag substitution) at render time.

    Returns (mapping_for_manifest, stats_per_language).
    """
    out_dir = PUBLIC / "i18n"
    out_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    stats: dict[str, dict] = {}

    install = DEFAULT_TACTICUS_INSTALL
    src = install / "Tacticus_Data" / "StreamingAssets" / "Bundles" / "languages"
    if not src.exists():
        print(f"[warn] missing {src} — set TACTICUS_INSTALL env var")
        return mapping, stats

    # Languages we care about right now. Drop a name from this set to skip,
    # add one to extract more. The bundle filename is "<lang>_<hash>.resource".
    WANTED = {"en", "fr"}
    for bundle in sorted(src.iterdir()):
        if not bundle.is_file() or not bundle.suffix == ".resource":
            continue
        lang = bundle.stem.split("_", 1)[0]
        if lang not in WANTED:
            continue
        try:
            env = UnityPy.load(str(bundle))
        except Exception as exc:
            print(f"[skip] {bundle.name}: {exc}", file=sys.stderr)
            continue

        mb = next((o for o in env.objects if o.type.name == "MonoBehaviour"), None)
        if mb is None:
            continue
        try:
            tree = mb.read_typetree()
        except Exception as exc:
            print(f"[skip] {bundle.name}: typetree {exc}", file=sys.stderr)
            continue

        terms_list = (tree.get("mSource") or {}).get("mTerms") or []
        flat: dict[str, str] = {}
        for term in terms_list:
            key = term.get("Term")
            langs = term.get("Languages") or []
            if not isinstance(key, str) or not langs:
                continue
            # Pick first non-empty string entry.
            value = next((s for s in langs if isinstance(s, str) and s), None)
            if value is None:
                continue
            flat[key] = value

        # Category breakdown (everything before the first '/').
        cats: dict[str, int] = {}
        for k in flat:
            cat = k.split("/", 1)[0] if "/" in k else "<no-category>"
            cats[cat] = cats.get(cat, 0) + 1

        out = out_dir / f"{lang}.json"
        # Write UTF-8 explicitly — locale strings contain non-cp1252 chars
        # (smart quotes, non-breaking hyphens, em dashes, accents).
        out.write_text(json.dumps(flat, ensure_ascii=False, indent=0),
                       encoding="utf-8")
        mapping[lang] = f"i18n/{lang}.json"
        stats[lang] = {"terms": len(flat), "categories": cats}
        # Top categories preview.
        top = sorted(cats.items(), key=lambda kv: -kv[1])[:8]
        print(f"[i18n/{lang}] {len(flat)} terms · top: "
              + ", ".join(f"{k}={v}" for k, v in top))

    return mapping, stats


def extract_abilities() -> dict[str, str]:
    """Ability icons: 1 Sprite per .resource bundle.

    The PC install ships them under
      Tacticus_Data/StreamingAssets/Bundles/abilities/{active2,triggered,triggered2,environment}/
    Each bundle is named `<keyname>_<32-hex-hash>.resource` where `keyname` is
    a lowercased ability key (no underscores between words, e.g. `aetherstride`,
    `loki_swoopinghawk` keeps the underscore separator inside the key).

    The frontend looks up `manifest.abilities[normalize(source)]` where
    `source` is the StartGroup source string from StreamDispatcher (e.g.
    "Loki_SwoopingHawk", "AdaptiveStrategy"). Normalisation: lowercase the
    whole string. We index the manifest by that lowercased form.
    """
    out_dir = PUBLIC / "abilities"
    out_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}

    install = DEFAULT_TACTICUS_INSTALL
    src = install / "Tacticus_Data" / "StreamingAssets" / "Bundles" / "abilities"
    if not src.exists():
        print(f"[warn] missing {src} — set TACTICUS_INSTALL env var")
        return mapping

    bundles: list[Path] = []
    for sub in ("active2", "triggered", "triggered2", "environment"):
        d = src / sub
        if d.exists():
            bundles.extend(sorted(p for p in d.iterdir() if p.is_file()))

    for bundle in bundles:
        # `loki_swoopinghawk_4b34f803...` → key = "loki_swoopinghawk"
        key = strip_hash(bundle.stem).lower()
        try:
            env = UnityPy.load(str(bundle))
        except Exception as exc:
            print(f"[skip] {bundle.name}: {exc}", file=sys.stderr)
            continue

        sprite_obj = next((o for o in env.objects if o.type.name == "Sprite"), None)
        if sprite_obj is None:
            # Some bundles may only have Texture2D (no Sprite metadata).
            tex_obj = next((o for o in env.objects if o.type.name == "Texture2D"), None)
            if tex_obj is None:
                continue
            data = tex_obj.read()
        else:
            data = sprite_obj.read()
        out = out_dir / f"{key}.png"
        try:
            data.image.save(out)
        except Exception as exc:
            print(f"[skip] {bundle.name}: save failed: {exc}", file=sys.stderr)
            continue
        mapping[key] = f"abilities/{key}.png"

    print(f"[abilities] extracted {len(mapping)} icons from {src}")
    return mapping


def main() -> int:
    units = extract_avatars()
    extract_atlases(units)
    abilities = extract_abilities()
    languages, lang_stats = extract_languages()
    boards, visuals = extract_boards()

    manifest = {
        "unityVersion": UnityPy.config.FALLBACK_UNITY_VERSION,
        "units": dict(sorted(units.items())),
        "abilities": dict(sorted(abilities.items())),
        "languages": dict(sorted(languages.items())),
        "boards": dict(sorted(boards.items())),
        "boardVisuals": dict(sorted(visuals.items())),
    }
    out = PUBLIC / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2))
    print(f"[manifest] {out}")
    print(f"  units={len(units)} abilities={len(abilities)} "
          f"languages={len(languages)} boards={len(boards)} visuals={len(visuals)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
