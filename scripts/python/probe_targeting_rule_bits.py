"""CONFRONTE la table `TARGETING_RULE_BITS` ecrite a la main au dump du build COURANT.

POURQUOI
--------
`frida/hooks/data/targeting-rule-names.ts` porte les 58 bits de
`IdunBattle.Core.Services.TargetingRule`. Elle a ete extraite A LA MAIN d'un `dump.cs`
Il2CppDumper du build **kqkbjqfb6c** -- un AUTRE build que le courant. Rien, jusqu'ici, ne
disait si les indices de bits avaient bouge : notre propre dump lisait les enums en 32 bits
et perdait justement les membres hauts (cf. probe_enum_dump_width).

Depuis que le dump lit a la largeur reelle, la question devient MECANIQUE : on regenere la
table depuis `data/symbols/<build>/frida/enums.tsv` et on diffe. Ce probe est cette
confrontation, et il ECHOUE si un bit a bouge -- ce qui invaliderait d'un coup tous les
masques `TARGETING_OPTIONS` du registre.

Sortie ASCII only (console Windows cp1252).
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TS = REPO / "frida" / "hooks" / "data" / "targeting-rule-names.ts"
ENUM = "IdunBattle.Core.Services.TargetingRule"


def build_hash() -> str:
    stamps = sorted((REPO / "data" / "symbols").glob("*/BUILD"))
    if not stamps:
        raise RuntimeError("aucun data/symbols/<build>/BUILD")
    return stamps[0].read_text(encoding="utf-8").strip()


def from_dump(build: str) -> dict:
    """{index de bit: nom} depuis le dump. Les composites (plusieurs bits) sont ecartes,
    comme dans la table TS."""
    p = REPO / "data" / "symbols" / build / "frida" / "enums.tsv"
    line = None
    for ln in p.open(encoding="utf-8"):
        if ln.startswith(ENUM + "\t"):
            line = ln.rstrip("\n")
            break
    if line is None:
        raise RuntimeError(f"{ENUM} absent de {p}")
    out = {}
    for kv in line.split("\t", 1)[1].split(","):
        raw, name = kv.split("=", 1)
        v = int(raw)
        if v <= 0:
            continue                      # 0 / negatifs : pas un bit simple
        if v & (v - 1):
            continue                      # plusieurs bits -> composite, ecarte
        out[v.bit_length() - 1] = name
    return out


def from_ts() -> dict:
    txt = TS.read_text(encoding="utf-8")
    return {int(m.group(1)): m.group(2)
            for m in re.finditer(r'^\s*(\d+):\s*"([^"]+)",', txt, re.M)}


def from_python() -> dict:
    """Le module GENERE consomme par le registre. S'il derive du dump, tous les masques
    nommes deviennent faux SILENCIEUSEMENT -- d'ou sa presence ici."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from engine.runner.abilities.targeting_rule import TargetingRule
    out = {}
    for m in TargetingRule:
        v = int(m)
        if v > 0 and not (v & (v - 1)):
            out[v.bit_length() - 1] = m.name
    return out


def _confronte(gauche: dict, droite: dict, nom_g: str, nom_d: str) -> list:
    return [(bit, gauche.get(bit), droite.get(bit))
            for bit in sorted(set(gauche) | set(droite))
            if gauche.get(bit) != droite.get(bit)]


def main() -> int:
    build = build_hash()
    dump, ts, py = from_dump(build), from_ts(), from_python()
    print("build=%s  dump=%d bits simples | table TS=%d | module Python=%d"
          % (build, len(dump), len(ts), len(py)))

    rc = 0
    for droite, nom in ((ts, "table TS (hooks/data)"), (py, "module Python genere")):
        bad = _confronte(dump, droite, "dump", nom)
        if bad:
            rc = 1
            print("DIVERGENCES dump <-> %s -- les masques du registre sont SUSPECTS :" % nom)
            for bit, d, x in bad:
                print("  bit %-3d  dump=%-40s %s=%s" % (bit, d, nom, x))
    if rc:
        return rc

    print("OK: les %d bits concordent sur les TROIS sources" % len(dump))
    print("    (dump du build courant, table ecrite a la main sous kqkbjqfb6c, module genere)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
