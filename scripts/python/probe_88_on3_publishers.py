"""probe #88 -- l'evenement `On(PendingDeathAdded = 3)` est-il PUBLIE quelque part ?

`FuelledByFury_ReviveAbility$$CreateTrigger` (le volet REVIVE du passif d'`ultraTitus`) ecoute
`On(3)`. Le case-doc `docs/rl/case-66-revive-in-place.md` §8.1 le declarait bloque sur un emetteur
<< non localise >>. Ce probe tranche par BALAYAGE, sans supposer une forme d'appel unique.

Constat de forme (lu au decompile) : la publication d'un evenement de trigger prend l'`eventType`
tantot en **r9d** (`FUN_1800280e0`), tantot en **5e argument** (slot d'interface INLINE, ex.
`IdunBattle.Operations.MoveUnitOperation$$EvaluateArrivedAtFinalTileTrigger` -> `0x1c`), tantot en
**9e** (`FUN_180028f50`, ex. `IdunBattle.Operations.DisplaceUnitOperation$$EventAndAbilitiesAndEffects`
-> `0x24`/`0x23`/`0x1d`). Les arguments 5+ passent par la pile : `mov dword ptr [rsp+N], imm32`.

=> On balaie donc TOUTE la section `il2cpp` pour l'ecriture d'un immediat dans un slot d'argument de
pile (`C7 44 24 N imm32`, N = 0x20..0x50) ET pour `mov r9d, imm32`, on resout la fonction contenante
par `data/symbols/<build>/ghidra/functions.tsv`, et on ne RETIENT que les fonctions qui referencent
l'interface de publication de triggers. Temoins obligatoires : les emetteurs CONNUS d'evenements
publies par cette voie inline (`0x1c` ArrivedAtFinalTile, `0x2e` UnitResurrected, `0x2b` UnitHealed)
doivent ressortir -- sinon le balayage est en faux negatif et sa conclusion ne vaut rien.

Sortie ASCII pure.
"""
from __future__ import annotations

import bisect
import struct
import sys
from pathlib import Path

GAME_DLL = Path(r"C:\Users\nicolasv\AppData\Local\tacticus\games\gqfc5mff6c\GameAssembly.dll")
ROOT = Path(__file__).resolve().parents[2]
FUNCS_TSV = ROOT / "data" / "symbols" / "gqfc5mff6c" / "ghidra" / "functions.tsv"

STACK_SLOTS = (0x20, 0x28, 0x30, 0x38, 0x40, 0x48, 0x50)

# Evenements-temoins : emis par une voie INLINE (donc invisibles du scan par thunk), avec leur
# emetteur natif connu -- ils valident que le balayage voit bien ce genre de site.
WITNESSES = {
    0x1c: "MoveUnitOperation$$EvaluateArrivedAtFinalTileTrigger (28 ArrivedAtFinalTile)",
    0x2f: "ResurrectUnitOperation (46 UnitResurrected)",
    0x2c: "HealUnitOperation (43 UnitHealed)",
}


def _sections(buf: bytes):
    pe_off = struct.unpack_from("<I", buf, 0x3C)[0]
    n_sec = struct.unpack_from("<H", buf, pe_off + 6)[0]
    opt_size = struct.unpack_from("<H", buf, pe_off + 20)[0]
    image_base = struct.unpack_from("<Q", buf, pe_off + 24 + 24)[0]
    sec_off = pe_off + 24 + opt_size
    out = []
    for i in range(n_sec):
        o = sec_off + i * 40
        out.append((buf[o:o + 8].rstrip(b"\x00").decode("ascii", "replace"),
                    struct.unpack_from("<I", buf, o + 12)[0],
                    struct.unpack_from("<I", buf, o + 8)[0],
                    struct.unpack_from("<I", buf, o + 20)[0],
                    struct.unpack_from("<I", buf, o + 16)[0]))
    return image_base, out


def _load_symbols():
    addrs, names = [], []
    with FUNCS_TSV.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            p = line.rstrip("\n").split("\t")
            if len(p) < 2:
                continue
            try:
                addrs.append(int(p[0], 16))
            except ValueError:
                continue
            names.append(p[1])
    order = sorted(range(len(addrs)), key=lambda i: addrs[i])
    return [addrs[i] for i in order], [names[i] for i in order]


def _resolve(addrs, names, va):
    i = bisect.bisect_right(addrs, va) - 1
    return names[i] if i >= 0 else "?"


def scan_immediate(buf, image_base, secs, value: int):
    """Toutes les ecritures de `value` comme argument (pile 5+ ou r9d) dans le code."""
    sites = []
    pats = [(bytes((0xC7, 0x44, 0x24, n)) + struct.pack("<I", value), "arg@rsp+0x%x" % n)
            for n in STACK_SLOTS]
    pats.append((b"\x41\xb9" + struct.pack("<I", value), "r9d"))
    for nm, vaddr, vsize, praw, rawsz in secs:
        if nm not in (".text", "il2cpp"):
            continue
        body = buf[praw:praw + rawsz]
        for pat, kind in pats:
            start = 0
            while True:
                k = body.find(pat, start)
                if k < 0:
                    break
                start = k + 1
                sites.append((image_base + vaddr + k, kind))
    return sites


def main() -> int:
    buf = GAME_DLL.read_bytes()
    image_base, secs = _sections(buf)
    addrs, names = _load_symbols()

    def report(value, label, only_publishers=True):
        sites = scan_immediate(buf, image_base, secs, value)
        by_fn = {}
        for va, kind in sites:
            fn = _resolve(addrs, names, va)
            by_fn.setdefault(fn, []).append(kind)
        keep = {}
        for fn, kinds in by_fn.items():
            if only_publishers and not (".Operations." in fn or ".Messages." in fn
                                        or "Behaviours." in fn or "Triggers." in fn):
                continue
            keep[fn] = kinds
        print("=== immediat %d (0x%x) %s : %d site(s), %d fonction(s) retenue(s) ==="
              % (value, value, label, len(sites), len(keep)))
        for fn in sorted(keep):
            kinds = keep[fn]
            print("   %-88s %s" % (fn[:88], ",".join(sorted(set(kinds)))))
        print()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from engine.dsl.event_trigger_type import EventTriggerType

    for wv, who in WITNESSES.items():
        report(wv, "TEMOIN %s -- %s" % (EventTriggerType(wv).name, who))
    report(3, "CIBLE PendingDeathAdded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
