"""probe #88 -- localiser l'emetteur d'`On(PendingDeathAdded = 3)`.

`probe_88_event_emitters.py` a decode les 55 call-sites du dispatcher
`FUN_180026490(msgId, <static>, events, eventType, entities)` : AUCUN ne passe `eventType = 3`.
Il existe donc un (ou plusieurs) AUTRE(S) chemin(s) d'emission. Ce probe les cherche par BALAYAGE
DU CODE : dans `.text`, toute sequence `mov r9d, 3` (`41 B9 03 00 00 00`) suivie, dans les 64
octets, d'un `call rel32` -- puis resolution du call-site ET de la cible via la table de symboles
versionnee `data/symbols/<build>/ghidra/functions.tsv` (format `<adresse>\t<symbole>`).

Le meme balayage est fait pour `eventType = 31` (PreUnitMove, residu A2) a titre de temoin :
il DOIT retrouver `MoveUnitOperation$$Execute` / `$$EvaluatePreMoveTriggers`, ce qui valide la
methode. Sortie ASCII pure.
"""
from __future__ import annotations

import bisect
import struct
import sys
from pathlib import Path

GAME_DLL = Path(r"C:\Users\nicolasv\AppData\Local\tacticus\games\gqfc5mff6c\GameAssembly.dll")
ROOT = Path(__file__).resolve().parents[2]
FUNCS_TSV = ROOT / "data" / "symbols" / "gqfc5mff6c" / "ghidra" / "functions.tsv"

WINDOW = 64          # octets fouilles apres le `mov r9d, imm` pour trouver le `call`


def _sections(buf: bytes):
    pe_off = struct.unpack_from("<I", buf, 0x3C)[0]
    n_sec = struct.unpack_from("<H", buf, pe_off + 6)[0]
    opt_size = struct.unpack_from("<H", buf, pe_off + 20)[0]
    image_base = struct.unpack_from("<Q", buf, pe_off + 24 + 24)[0]
    sec_off = pe_off + 24 + opt_size
    out = []
    for i in range(n_sec):
        o = sec_off + i * 40
        name = buf[o:o + 8].rstrip(b"\x00").decode("ascii", "replace")
        vaddr = struct.unpack_from("<I", buf, o + 12)[0]
        vsize = struct.unpack_from("<I", buf, o + 8)[0]
        praw = struct.unpack_from("<I", buf, o + 20)[0]
        rawsz = struct.unpack_from("<I", buf, o + 16)[0]
        out.append((name, vaddr, vsize, praw, rawsz))
    return image_base, out


def _load_symbols():
    addrs, names = [], []
    with FUNCS_TSV.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            try:
                a = int(parts[0], 16)
            except ValueError:
                continue
            addrs.append(a)
            names.append(parts[1])
    order = sorted(range(len(addrs)), key=lambda i: addrs[i])
    return [addrs[i] for i in order], [names[i] for i in order]


def _resolve(addrs, names, va):
    i = bisect.bisect_right(addrs, va) - 1
    if i < 0:
        return "?", 0
    return names[i], va - addrs[i]


def scan(buf, image_base, text, imm_value):
    name, vaddr, vsize, praw, rawsz = text
    body = buf[praw:praw + rawsz]
    pat = b"\x41\xb9" + struct.pack("<I", imm_value)
    hits = []
    start = 0
    while True:
        k = body.find(pat, start)
        if k < 0:
            break
        start = k + 1
        # cherche le PREMIER `call rel32` (E8) dans la fenetre qui suit, en s'arretant si un
        # autre `mov r9d, imm32` reecrit r9 (l'immediat scanne ne serait alors plus l'argument).
        j = k + 6
        end = min(k + 6 + WINDOW, len(body) - 5)
        target = None
        while j < end:
            if body[j] == 0x41 and body[j + 1] == 0xB9:
                break                      # r9 reecrit -> ce site ne porte pas notre immediat
            if body[j] == 0xE8:
                rel = struct.unpack_from("<i", body, j + 1)[0]
                target = image_base + vaddr + (j + 5) + rel
                break
            j += 1
        if target is not None:
            site = image_base + vaddr + j
            hits.append((site, target))
    return hits


def main() -> int:
    if not GAME_DLL.exists():
        print("ABSENT: %s" % GAME_DLL)
        return 2
    if not FUNCS_TSV.exists():
        print("ABSENT: %s" % FUNCS_TSV)
        return 2
    buf = GAME_DLL.read_bytes()
    image_base, secs = _sections(buf)
    # ATTENTION : le code IL2CPP AOT ne vit PAS dans `.text` (qui ne porte que le runtime Unity)
    # mais dans la section **`il2cpp`** (~40 Mo). Scanner `.text` seul rend 0 hit -- faux negatif.
    code_secs = [s for s in secs if s[0] in (".text", "il2cpp")]
    addrs, names = _load_symbols()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from engine.dsl.event_trigger_type import EventTriggerType

    for imm in (3, 31):
        try:
            label = EventTriggerType(imm).name
        except ValueError:
            label = "?"
        hits = []
        for sec in code_secs:
            hits += scan(buf, image_base, sec, imm)
        print("=== eventType = %d (%s) : %d site(s) `mov r9d,%d` + call ===" % (imm, label, len(hits), imm))
        by_target = {}
        for site, target in hits:
            by_target.setdefault(target, []).append(site)
        for target in sorted(by_target):
            tname, toff = _resolve(addrs, names, target)
            sites = by_target[target]
            # on n'affiche que les cibles plausibles : celles appelees depuis IdunBattle.Operations
            callers = sorted({_resolve(addrs, names, s)[0] for s in sites})
            interesting = [c for c in callers if "IdunBattle" in c or "Idun" in c]
            if not interesting:
                continue
            print("  -> cible %s%s  (%d site(s))" % (tname, ("+0x%x" % toff) if toff else "", len(sites)))
            for c in interesting[:20]:
                print("       depuis %s" % c)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
