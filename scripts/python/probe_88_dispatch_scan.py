"""probe #88 -- balayage EXHAUSTIF des call-sites du publieur d'evenements de trigger.

`FUN_180026490(slot, <IEvents>, events, eventType, abilityEntities)` est le thunk generique qui
resout un slot d'interface et appelle `publish(eventType, abilityEntities)`. La liste `list_xrefs`
de ghidra en donne 55 -- mais elle ne vaut que ce que vaut l'analyse. Ce probe RE-DERIVE la liste
en balayant les octets : tout `E8 rel32` dont la cible est le thunk, puis decodage de l'immediat
`mov r9d, imm32` (= `eventType`) dans les 96 octets qui precedent, et resolution du call-site par
`data/symbols/<build>/ghidra/functions.tsv`.

But : etablir par CONSTAT (et non par absence de resultat de recherche) si `On(PendingDeathAdded=3)`
-- l'evenement qu'attend `FuelledByFury_ReviveAbility$$CreateTrigger` -- est emis quelque part.
Sortie ASCII pure.
"""
from __future__ import annotations

import bisect
import struct
from collections import Counter
from pathlib import Path

GAME_DLL = Path(r"C:\Users\nicolasv\AppData\Local\tacticus\games\gqfc5mff6c\GameAssembly.dll")
ROOT = Path(__file__).resolve().parents[2]
FUNCS_TSV = ROOT / "data" / "symbols" / "gqfc5mff6c" / "ghidra" / "functions.tsv"

# Thunks generiques d'appel de slot d'interface (meme famille, arites DIFFERENTES). Il y a au moins
# DEUX formes de publication d'evenement de trigger, et ne scanner que la premiere donne un FAUX
# NEGATIF (30 des 77 `EventTriggerType` -- dont `UnitDisplaced`, `UnitHealed`, `UnitResurrected`,
# tous bel et bien emis -- passent par la seconde) :
#   * `FUN_180026490(slot, iface, events, eventType, abilityEntities)` -> eventType en **r9d** (arg 4)
#   * `FUN_180028f50(slot, iface, events, owner, actor, target, x, list, eventType, opts, 0)`
#     -> eventType en **9e argument**, donc sur la pile a `[rsp+0x40]`
#     (lu dans `IdunBattle.Operations.DisplaceUnitOperation$$EventAndAbilitiesAndEffects`, qui publie
#      ainsi 0x24 UnitPositionChanged_1, 0x23 UnitDisplaced et 0x1d UnitPositionChanged_2).
DISPATCH_THUNKS = {
    0x180026490: "r9d",        # arg 4
    0x180028f50: "rsp+0x40",   # arg 9
}
BACK_WINDOW = 160


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
    return (names[i], va - addrs[i]) if i >= 0 else ("?", 0)


def main() -> int:
    buf = GAME_DLL.read_bytes()
    image_base, secs = _sections(buf)
    addrs, names = _load_symbols()
    from engine.dsl.event_trigger_type import EventTriggerType
    ev_names = {int(m): m.name for m in EventTriggerType}

    sites = []
    for nm, vaddr, vsize, praw, rawsz in secs:
        if nm not in (".text", "il2cpp"):
            continue
        body = buf[praw:praw + rawsz]
        i = 0
        n = len(body)
        while True:
            k = body.find(b"\xe8", i)
            if k < 0 or k + 5 > n:
                break
            i = k + 1
            rel = struct.unpack_from("<i", body, k + 1)[0]
            target = image_base + vaddr + (k + 5) + rel
            where = DISPATCH_THUNKS.get(target)
            if where is None:
                continue
            site = image_base + vaddr + k
            win = body[max(0, k - BACK_WINDOW):k]
            imm = None
            j = 0
            while j + 8 <= len(win):
                if where == "r9d":
                    if win[j] == 0x41 and win[j + 1] == 0xB9:          # mov r9d, imm32
                        imm = struct.unpack_from("<I", win, j + 2)[0]
                        j += 6
                        continue
                    if win[j] == 0x45 and win[j + 1] == 0x33 and win[j + 2] == 0xC9:   # xor r9d,r9d
                        imm = 0
                        j += 3
                        continue
                else:
                    # mov dword ptr [rsp+0x40], imm32  ->  C7 44 24 40 <imm32>
                    if (win[j] == 0xC7 and win[j + 1] == 0x44 and win[j + 2] == 0x24
                            and win[j + 3] == 0x40):
                        imm = struct.unpack_from("<I", win, j + 4)[0]
                        j += 8
                        continue
                j += 1
            sites.append((site, imm))

    print("call-sites des publieurs d'event (balayage octet) : %d" % len(sites))
    counts = Counter(imm for _, imm in sites)
    print("evenements distincts publies : %d" % len(counts))
    for imm in sorted(counts, key=lambda v: (v is None, v)):
        label = ev_names.get(imm, "?") if imm is not None else "(r9 non decode)"
        who = sorted({_resolve(addrs, names, s)[0] for s, m in sites if m == imm})
        print("  event %-5s %-30s x%-3d  %s" % (imm if imm is not None else "-", label,
                                                counts[imm], "; ".join(who[:4])))
    print()
    missing = [int(m) for m in EventTriggerType if int(m) not in counts]
    print("EventTriggerType JAMAIS publie par ce thunk : %s"
          % ", ".join("%d %s" % (v, ev_names[v]) for v in missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
