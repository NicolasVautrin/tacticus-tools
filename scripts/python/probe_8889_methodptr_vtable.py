"""Probe #88-#89 -- lire les METHODES d'une classe IL2CPP **sans** que sa classe soit initialisee.

PROBLEME. Le RPC `resolveVtableSlot` (probe_79_revive_vtable.py) lit `klass + off` LIVE : il exige que
`Il2CppClass` ait ete CONSTRUIT. Une classe dont le carrier n'est jamais montable (ex.
`ReanimationBeam_ReviveEffect` -> MoW `necroReanimator` hors pool, `RitesOfMorkaiEffect` ->
`spaceWolfPriest` hors pool) rend des slots NULS -> residu.

SOLUTION. La table `methodPointers` d'IL2CPP est presente TELLE QUELLE dans `GameAssembly.dll` (les
pointeurs y sont stockes en VA image-base 0x180000000, avant relocation) et couvre TOUTES les classes.
Les methodes d'un meme type y sont CONTIGUES, dans l'ordre de DECLARATION. Il suffit donc de :
  1. localiser 2 methodes de la classe dont on connait la VA (symbole ghidra : `.ctor`, un `Create*`) ;
  2. verifier que leurs offsets fichier sont adjacents (0x8) -> on tient le bloc ;
  3. dumper les qwords voisins : ce sont les AUTRES methodes, y compris celles que l'ICF a fondues
     (donc SANS symbole propre, invisibles a `search_symbols_by_name`).
Desambiguation de deux corps triviaux voisins : par la TAILLE DE RETOUR du corps folde
(`undefined1` = bool vs `undefined8` = int au decompile).

Ce probe est OFFLINE PUR (aucune session Frida, aucun hook) : il lit le PE sur disque.

ENTREE HORS DEPOT : `GameAssembly.dll` vit sous `%LOCALAPPDATA%/tacticus/games/<hash>/` et
son hash CHANGE a chaque mise a jour. Le binaire est donc resolu par `build_pin.game_dll()`
(build INSTALLE, confronte a `data/symbols/CURRENT`), jamais par un chemin en dur -- celui
qui etait ici pointait `gqfc5mff6c`, un build desinstalle depuis (#431). Les VA passees en
argument doivent venir du MEME build que celui que `build_pin` rend : une VA d'un build
anterieur trouve des pointeurs d'apparence normale et parfaitement faux.

    python probe_8889_methodptr_vtable.py IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect$$.ctor IdunBattle.Entities.Effects.Loki.ReanimationBeam_ReviveEffect$$CreateTargetFilter     # ReanimationBeam .ctor + filter
    python probe_8889_methodptr_vtable.py --window 10 IdunBattle.Entities.Effects.Loki.RitesOfMorkaiEffect$$.ctor

Sortie : les qwords autour du bloc, en VA ghidra. ASCII only.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

from build_pin import BuildPinRefused, game_dll

IMAGE_BASE = 0x180000000


def find_pointer(buf: bytes, va: int) -> list[int]:
    """Offsets FICHIER ou le qword `va` apparait (aligne 8 seulement : la table l'est)."""
    pat = struct.pack("<Q", va)
    out, i = [], buf.find(pat)
    while i != -1:
        if i % 8 == 0:
            out.append(i)
        i = buf.find(pat, i + 1)
    return out


def dump_block(buf: bytes, off: int, window: int) -> list[tuple[int, int]]:
    """`window` qwords de part et d'autre de `off` -> [(offset_fichier, va)]."""
    start = max(0, off - window * 8)
    return [(start + k * 8, struct.unpack_from("<Q", buf, start + k * 8)[0])
            for k in range(window * 2 + 1)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("vas", nargs="+", help="VA ghidra d'une methode connue de la classe (0x...)")
    ap.add_argument("--dll", default=None,
                    help="binaire a lire (defaut : celui du build COURANT, via build_pin). "
                         "Les VA passees en argument doivent venir du MEME build.")
    ap.add_argument("--window", type=int, default=6, help="qwords de contexte de part et d'autre")
    a = ap.parse_args()
    try:
        dll = Path(a.dll) if a.dll else game_dll()
    except BuildPinRefused as exc:
        print(str(exc))
        return 2
    a.dll = str(dll)
    buf = dll.read_bytes()
    print("dll=%s size=%d" % (a.dll, len(buf)))
    anchors = []
    for s in a.vas:
        va = int(s, 16)
        offs = find_pointer(buf, va)
        print("  VA %#x -> offsets %s" % (va, [hex(o) for o in offs]))
        anchors += offs
    if not anchors:
        print("AUCUN pointeur trouve (VA hors methodPointers ? ICF ? mauvais build ?)")
        return 1
    base = min(anchors)
    print("--- bloc methodPointers autour de %#x" % base)
    for off, va in dump_block(buf, base, a.window):
        mark = " <<" if off in anchors else ""
        rva = (va - IMAGE_BASE) if IMAGE_BASE <= va < IMAGE_BASE + len(buf) * 4 else None
        print("  %#010x  %#012x  rva=%s%s" % (off, va, hex(rva) if rva else "-", mark))
    return 0


if __name__ == "__main__":
    sys.exit(main())
