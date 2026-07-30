"""
rl_gen_enum_columns.py — stratégie hybride des enums (cf.
.claude/skills/tacticus/references/rl-database.md § Enums).

Depuis le dump.cs du build COURANT, génère :
  - scripts/sql/013_enum_fk_and_names.sql
      * FK des id-dims (active/triggered ability, effect_type, visual_id) vers
        les ref tables (grosse cardinalité → normalisé).
      * Colonnes `*_name` dénormalisées pour les petits enum-type
        (effect_type, active/passive_ability_type, damage_profile_type,
        unit_spawn_source) + backfill depuis les enums IL2CPP.
  - scripts/python/enum_maps.py : dicts id→nom, importés par l'ingest
    (rl_collect_batch.py) pour remplir les `*_name` à l'insert.

Les ids enum sont spécifiques au build → tout repart de resolve_dump_cs().
Lancer avec --apply pour exécuter le SQL en base.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from rl_gen_ref_tables import ROOT, _sql_escape, resolve_dump_cs

SQL_OUT = ROOT / "scripts" / "sql" / "013_enum_fk_and_names.sql"
MAPS_OUT = ROOT / "scripts" / "python" / "enum_maps.py"

# Colonne stream_event -> enum IL2CPP (petits enum-type, dénormalisés en *_name).
ENUM_COLS: dict[str, str] = {
    "effect_type": "EffectType",
    "active_ability_type": "ActiveAbilityType",
    "passive_ability_type": "TriggeredAbilityType",
    "damage_profile_type": "DamageProfileType",
    "unit_spawn_source": "SpawnSource",
}

# FK des id-dims (grosse cardinalité) -> ref tables. (col, ref_table, ref_key)
# NB: effect_id n'est PAS ici — c'est un id d'instance, pas l'enum EffectType.
FKS: list[tuple[str, str, str]] = [
    ("active_ability_id", "ref_active_ability", "ability_id"),
    ("effect_source_active_ability", "ref_active_ability", "ability_id"),
    ("triggered_ability_id", "ref_triggered_ability", "ability_id"),
    ("effect_source_triggered_ability", "ref_triggered_ability", "ability_id"),
    ("effect_type", "ref_effect", "effect_id"),
]
# FK visual_id -> ref_unit (sur d'autres tables que stream_event).
VISUAL_FKS: list[tuple[str, str]] = [("unit_state", "visual_id"),
                                     ("mow_state", "visual_id")]


def parse_enum(text: str, name: str) -> dict[int, str]:
    m = re.search(r"public enum " + name + r"[^{]*\{(.*?)^\}", text, re.M | re.S)
    out: dict[int, str] = {}
    if m:
        for em in re.finditer(
                r"public const " + name + r" (\w+) = (-?\d+);", m.group(1)):
            out[int(em.group(2))] = em.group(1)
    return out


def gen_maps_py(enums: dict[str, dict[int, str]]) -> str:
    lines = [
        "# enum_maps.py — GENERE par rl_gen_enum_columns.py depuis dump.cs.",
        "# Ids enum spécifiques au build → re-générer au changement de build.",
        "# Importé par rl_collect_batch.py pour remplir les colonnes *_name.",
        "",
    ]
    const_by_col = {}
    for col, enum_name in ENUM_COLS.items():
        const = col.upper()
        const_by_col[col] = const
        d = enums[enum_name]
        lines.append(f"# {col} <- enum {enum_name} ({len(d)} membres)")
        lines.append(f"{const} = {{")
        for i, n in sorted(d.items()):
            lines.append(f"    {i}: {n!r},")
        lines.append("}")
        lines.append("")
    lines.append("BY_COLUMN = {")
    for col, const in const_by_col.items():
        lines.append(f"    {col!r}: {const},")
    lines.append("}")
    lines.append("")
    # GroupType : pour group_name sur stream_group (014), pas une colonne se.
    gt = enums.get("GroupType", {})
    lines.append(f"# GroupType ({len(gt)} membres) — pour stream_group.group_name (014)")
    lines.append("GROUP_TYPE = {")
    for i, n in sorted(gt.items()):
        lines.append(f"    {i}: {n!r},")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def gen_sql(enums: dict[str, dict[int, str]]) -> str:
    L = [
        "-- 013_enum_fk_and_names.sql — GENERE par rl_gen_enum_columns.py.",
        "-- Stratégie hybride : FK pour les id-dims, libellé dénormalisé pour",
        "-- les petits enum-type. Idempotent.",
        "",
        "-- ============ FK des id-dims vers les ref tables ============",
    ]
    # FK sur stream_event + index (les FK ne créent pas d'index en PG).
    for col, rt, rk in FKS:
        cname = f"se_{col}_fkey"
        L += [
            "DO $$ BEGIN",
            f"  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='{cname}') THEN",
            f"    ALTER TABLE tacticus.stream_event ADD CONSTRAINT {cname}",
            f"      FOREIGN KEY ({col}) REFERENCES tacticus.{rt}({rk});",
            "  END IF;",
            "END $$;",
            f"CREATE INDEX IF NOT EXISTS stream_event_{col}_idx "
            f"ON tacticus.stream_event ({col});",
            "",
        ]
    # FK visual_id -> ref_unit (unit_state, mow_state)
    for tbl, col in VISUAL_FKS:
        cname = f"{tbl}_{col}_fkey"
        L += [
            "DO $$ BEGIN",
            f"  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='{cname}') THEN",
            f"    ALTER TABLE tacticus.{tbl} ADD CONSTRAINT {cname}",
            f"      FOREIGN KEY ({col}) REFERENCES tacticus.ref_unit(unit_id);",
            "  END IF;",
            "END $$;",
            "",
        ]

    L += ["-- ============ Colonnes *_name dénormalisées + backfill ============"]
    for col, enum_name in ENUM_COLS.items():
        d = enums[enum_name]
        ncol = f"{col}_name"
        L += [
            f"ALTER TABLE tacticus.stream_event "
            f"ADD COLUMN IF NOT EXISTS {ncol} TEXT;  -- <- enum {enum_name}",
        ]
        vals = ",\n  ".join(f"({i}, '{_sql_escape(n)}')" for i, n in sorted(d.items()))
        L += [
            f"UPDATE tacticus.stream_event se SET {ncol} = m.name",
            f"  FROM (VALUES\n  {vals}\n  ) AS m(id, name)",
            f" WHERE se.{col} = m.id AND se.{col} IS NOT NULL;",
            "",
        ]
    return "\n".join(L)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv[1:])

    text = resolve_dump_cs().read_text(encoding="utf-8", errors="ignore")
    # GroupType n'est pas une colonne stream_event (pas dans ENUM_COLS) mais
    # sert à dénormaliser group_name sur stream_group (migration 014).
    enums = {name: parse_enum(text, name)
             for name in set(ENUM_COLS.values()) | {"GroupType"}}
    for name, d in sorted(enums.items()):
        print(f"  enum {name}: {len(d)} membres")
        if not d:
            raise SystemExit(f"enum {name} introuvable dans dump.cs")

    SQL_OUT.write_text(gen_sql(enums), encoding="utf-8")
    MAPS_OUT.write_text(gen_maps_py(enums), encoding="utf-8")
    print(f"Wrote {SQL_OUT}")
    print(f"Wrote {MAPS_OUT}")

    if args.apply:
        import psycopg2
        # #273 : `.env` est gitignore -- absent d'un worktree frais. Le
        # `read_text` nu levait bien, mais sur un `FileNotFoundError` qui ne
        # disait ni QUI remplit ce fichier ni qu'un autre arbre le porte.
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import host_inputs
        envfile = host_inputs.require(".env")
        pg = {}
        for line in envfile.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                pg[k.strip()] = v.strip()
        conn = psycopg2.connect(
            host=pg.get("PG_HOST", "localhost"), port=pg.get("PG_PORT", "5433"),
            dbname=pg.get("PG_DATABASE", "TACTICUS"),
            user=pg.get("PG_USER", "postgres"), password=pg.get("PG_PASSWORD", ""))
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SET search_path TO tacticus")
        cur.execute(SQL_OUT.read_text(encoding="utf-8"))
        print("Applied 013 OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
