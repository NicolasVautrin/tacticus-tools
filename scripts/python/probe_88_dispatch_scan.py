"""probe #88 -- balayage EXHAUSTIF des call-sites du publieur d'evenements de trigger.

Le thunk generique qui resout un slot d'interface et appelle `publish(eventType,
abilityEntities)` est un corps SANS SYMBOLE (`FUN_<addr>`). Ce probe RE-DERIVE la liste de
ses call-sites en balayant les octets : tout `E8 rel32` dont la cible est le thunk, puis
decodage de l'immediat qui porte l'`eventType`, et resolution du call-site par
`data/symbols/<build>/ghidra/functions.tsv`.

But : etablir par CONSTAT (et non par absence de resultat de recherche) si
`On(PendingDeathAdded)` -- l'evenement qu'attend `FuelledByFury_ReviveAbility$$CreateTrigger`
-- est emis quelque part. Sortie ASCII pure.

LES THUNKS NE S'ECRIVENT PLUS EN DUR (#431)
-------------------------------------------
Ils l'etaient, contre `gqfc5mff6c`. La doctrine du CLAUDE.md autorise la VA quand le
"symbole" n'est qu'un `FUN_<addr>` deguise -- mais elle n'exempte pas de la PEREMPTION :
mesure du 2026-08-01, `0x180026490` est un debut de fonction sur `gqfc5mff6c` et tombe a
`FUN_180026460+0x30` sur `rnca9r7q6c`. Un balayage lance avec l'ancienne valeur sur le
binaire courant ne trouve rien, et son zero se lit « aucun evenement publie ».

On les RE-DERIVE donc, a chaque run, en s'ancrant sur ce qui SURVIT : un symbole NOMME et
une valeur d'enum NOMMEE. Le thunk est simplement la cible du premier `call` qui suit la
materialisation de l'`eventType` dans le corps de l'emetteur d'ancrage.
"""
from __future__ import annotations

import struct
from collections import Counter

from build_pin import CODE_SECTIONS, BuildPinRefused, load_dll, va_to_file_offset

BACK_WINDOW = 160
FORWARD_WINDOW = 96          # octets fouilles apres l'immediat pour trouver le `call`

# Il y a au moins DEUX formes de publication d'evenement de trigger, et ne scanner que la
# premiere donne un FAUX NEGATIF (30 des 77 `EventTriggerType` -- dont `UnitDisplaced`,
# `UnitHealed`, `UnitResurrected`, tous bel et bien emis -- passent par la seconde) :
#   * thunk a 5 arguments  -> `eventType` en **r9d** (arg 4) ;
#   * thunk a 11 arguments -> `eventType` en **9e** argument, donc sur la pile.
#
# ANCRES : pour chaque forme, un emetteur NOMME et l'evenement NOMME qu'il publie. Lus au
# decompile (ghidra-mcp, `/GameAssembly.dll`) :
#   IdunBattle.Operations.MoveUnitOperation$$EvaluatePreMoveTriggers -> PreUnitMove en r9d ;
#   IdunBattle.Operations.DisplaceUnitOperation$$EventAndAbilitiesAndEffects -> UnitDisplaced
#     (puis UnitPositionChanged_1 / _2) dans un slot de pile.
ANCHORS = (
    ("r9d",
     "IdunBattle.Operations.MoveUnitOperation$$EvaluatePreMoveTriggers",
     "PreUnitMove"),
    ("stack",
     "IdunBattle.Operations.DisplaceUnitOperation$$EventAndAbilitiesAndEffects",
     "UnitDisplaced"),
)
STACK_SLOTS = (0x20, 0x28, 0x30, 0x38, 0x40, 0x48, 0x50)


def _immediate_patterns(kind: str, value: int):
    """Octets qui materialisent `value` comme argument, par forme d'appel."""
    if kind == "r9d":
        return [(b"\x41\xb9" + struct.pack("<I", value), "r9d")]
    return [(bytes((0xC7, 0x44, 0x24, n)) + struct.pack("<I", value), "rsp+0x%x" % n)
            for n in STACK_SLOTS]


def find_publisher_thunks(buf, image_base, secs, index):
    """{VA du thunk: forme de passage de l'eventType}, RE-DERIVE sur le build charge.

    Ancrage sur un SYMBOLE et une valeur d'ENUM, jamais sur une adresse : c'est le seul
    couple qui traverse un changement de build. Leve `BuildPinRefused` si une ancre ne
    donne rien -- un thunk introuvable doit ARRETER le balayage, pas le laisser rendre
    zero call-site.
    """
    from engine.dsl.event_trigger_type import EventTriggerType

    thunks = {}
    for kind, symbol, event in ANCHORS:
        va = index.va_of(symbol)
        off = va_to_file_offset(image_base, secs, va)
        if off is None:
            raise BuildPinRefused("ancre %s : VA hors section" % symbol)
        body = buf[off:off + index.span(va)]
        found = None
        for pat, where in _immediate_patterns(kind, int(EventTriggerType[event])):
            k = body.find(pat)
            if k < 0:
                continue
            j = k + len(pat)
            end = min(j + FORWARD_WINDOW, len(body) - 5)
            while j < end:
                if body[j] == 0xE8:
                    rel = struct.unpack_from("<i", body, j + 1)[0]
                    found = (va + (j + 5) + rel, where)
                    break
                j += 1
            if found:
                break
        if found is None:
            raise BuildPinRefused(
                "NON MESURE : thunk de publication INTROUVABLE pour la forme '%s'.\n"
                "  ancre : %s publiant On(%s)\n"
                "  Le corps de l'ancre ne materialise plus l'evenement de la facon attendue.\n"
                "  Relire l'ancre au decompile (ghidra-mcp, binaire /GameAssembly.dll) et\n"
                "  corriger ANCHORS -- ne PAS reintroduire une VA en dur." % (kind, symbol, event))
        thunks[found[0]] = found[1]
    return thunks


def _decode_event(win: bytes, where: str):
    """Dernier immediat charge dans le slot d'argument, dans la fenetre qui precede."""
    imm = None
    if where == "r9d":
        j = 0
        while j + 6 <= len(win):
            if win[j] == 0x41 and win[j + 1] == 0xB9:                       # mov r9d, imm32
                imm = struct.unpack_from("<I", win, j + 2)[0]
                j += 6
                continue
            if win[j] == 0x45 and win[j + 1] == 0x33 and win[j + 2] == 0xC9:  # xor r9d, r9d
                imm = 0
                j += 3
                continue
            j += 1
        return imm
    slot = int(where.split("+")[1], 16)
    pat = bytes((0xC7, 0x44, 0x24, slot))
    j = 0
    while j + 8 <= len(win):
        if win[j:j + 4] == pat:
            imm = struct.unpack_from("<I", win, j + 4)[0]
            j += 8
            continue
        j += 1
    return imm


def main() -> int:
    try:
        buf, image_base, secs, index = load_dll()
        thunks = find_publisher_thunks(buf, image_base, secs, index)
    except BuildPinRefused as exc:
        print(str(exc))
        return 2
    from engine.dsl.event_trigger_type import EventTriggerType
    ev_names = {int(m): m.name for m in EventTriggerType}

    print("build=%s" % index.build)
    for va, where in sorted(thunks.items()):
        print("  thunk re-derive : %s  (eventType en %s)" % (index.resolve(va)[0], where))

    sites = []
    for nm, vaddr, vsize, praw, rawsz in secs:
        if nm not in CODE_SECTIONS:
            continue
        body = buf[praw:praw + rawsz]
        i, n = 0, len(body)
        while True:
            k = body.find(b"\xe8", i)
            if k < 0 or k + 5 > n:
                break
            i = k + 1
            rel = struct.unpack_from("<i", body, k + 1)[0]
            where = thunks.get(image_base + vaddr + (k + 5) + rel)
            if where is None:
                continue
            site = image_base + vaddr + k
            sites.append((site, _decode_event(body[max(0, k - BACK_WINDOW):k], where)))

    print("call-sites des publieurs d'event (balayage octet) : %d" % len(sites))
    counts = Counter(imm for _, imm in sites)
    print("evenements distincts publies : %d" % len(counts))
    for imm in sorted(counts, key=lambda v: (v is None, v)):
        label = ev_names.get(imm, "?") if imm is not None else "(immediat non decode)"
        who = sorted({index.resolve(s)[0] for s, m in sites if m == imm})
        print("  event %-5s %-30s x%-3d  %s" % (imm if imm is not None else "-", label,
                                                counts[imm], "; ".join(who[:4])))
    print()
    missing = [int(m) for m in EventTriggerType if int(m) not in counts]
    print("EventTriggerType JAMAIS publie par ces thunks : %s"
          % ", ".join("%d %s" % (v, ev_names[v]) for v in missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
