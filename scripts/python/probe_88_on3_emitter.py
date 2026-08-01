"""probe #88 -- localiser l'emetteur d'`On(PendingDeathAdded = 3)`.

`probe_88_event_emitters.py` a decode les 55 call-sites du dispatcher
`FUN_1800280e0(msgId, <static>, events, eventType, entities)` : AUCUN ne passe `eventType = 3`.
Il existe donc un (ou plusieurs) AUTRE(S) chemin(s) d'emission. Ce probe les cherche par BALAYAGE
DU CODE : dans `.text`, toute sequence `mov r9d, 3` (`41 B9 03 00 00 00`) suivie, dans les 64
octets, d'un `call rel32` -- puis resolution du call-site ET de la cible via la table de symboles
versionnee `data/symbols/<build>/ghidra/functions.tsv` (format `<adresse>\t<symbole>`).

Le meme balayage est fait pour `eventType = 31` (PreUnitMove, residu A2) a titre de temoin :
il DOIT retrouver `MoveUnitOperation$$Execute` / `$$EvaluatePreMoveTriggers`, ce qui valide la
methode. Sortie ASCII pure.

BUILD (#431). Le binaire ET la table de symboles sortent ENSEMBLE de `build_pin.load_dll()` :
lire les octets d'un build en resolvant les adresses dans la table d'un autre rend des noms
de fonctions plausibles et faux. Ce probe portait deux chemins en dur vers `gqfc5mff6c`, un
build desinstalle depuis. Il n'epingle en revanche AUCUNE VA : ses ancrages sont un motif
d'octets et une valeur d'`EventTriggerType`, donc il se re-derive sur n'importe quel build.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

from build_pin import CODE_SECTIONS, BuildPinRefused, load_dll

WINDOW = 64          # octets fouilles apres le `mov r9d, imm` pour trouver le `call`


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
    try:
        buf, image_base, secs, index = load_dll()
    except BuildPinRefused as exc:
        print(str(exc))
        return 2
    print("build=%s  dll=%d octets" % (index.build, len(buf)))
    # ATTENTION : le code IL2CPP AOT ne vit PAS dans `.text` (qui ne porte que le runtime Unity)
    # mais dans la section **`il2cpp`** (~40 Mo). Scanner `.text` seul rend 0 hit -- faux negatif.
    code_secs = [s for s in secs if s[0] in CODE_SECTIONS]
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from engine.dsl.event_trigger_type import EventTriggerType

    for imm in (int(EventTriggerType.PendingDeathAdded), int(EventTriggerType.PreUnitMove)):
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
            tname, toff = index.resolve(target)
            sites = by_target[target]
            # on n'affiche que les cibles plausibles : celles appelees depuis IdunBattle.Operations
            callers = sorted({index.resolve(s)[0] for s in sites})
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
