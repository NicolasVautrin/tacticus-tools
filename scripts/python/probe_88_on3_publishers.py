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

BUILD (#431). DEUX epinglages ont ete retires ici, et le second etait deja FAUX :
  * les chemins en dur du binaire et de la table (`gqfc5mff6c`, build desinstalle) passent
    par `build_pin.load_dll()` -- les deux artefacts sortent ensemble ou aucun ne sort ;
  * les temoins etaient des ORDINAUX en dur (`0x2f`, `0x2c`) transcrits contre l'ancienne
    numerotation. Sur `rnca9r7q6c`, `0x2f` vaut `UnitMemberDeath` et `0x2c`
    `UnitHealedWithRemoveEffects` -- le probe aurait cherche deux autres evenements en
    annoncant les bons noms, et l'absence des temoins se serait lue comme un faux negatif
    du balayage. Ils sont desormais nommes, et l'ordinal vient d'`EventTriggerType`.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

from build_pin import CODE_SECTIONS, BuildPinRefused, load_dll

STACK_SLOTS = (0x20, 0x28, 0x30, 0x38, 0x40, 0x48, 0x50)

# Evenements-temoins : emis par une voie INLINE (donc invisibles du scan par thunk), avec leur
# emetteur natif connu -- ils valident que le balayage voit bien ce genre de site.
# Cle = NOM de l'`EventTriggerType` ; l'ordinal est resolu a l'execution (les enums sont
# RENUMEROTES d'un build a l'autre -- quatre l'ont ete entre gqfc5mff6c et rnca9r7q6c).
WITNESSES = {
    "ArrivedAtFinalTile": "MoveUnitOperation$$EvaluateArrivedAtFinalTileTrigger",
    "UnitResurrected": "ResurrectUnitOperation",
    "UnitHealed": "HealUnitOperation",
}
TARGET = "PendingDeathAdded"


def scan_immediate(buf, image_base, secs, value: int):
    """Toutes les ecritures de `value` comme argument (pile 5+ ou r9d) dans le code."""
    sites = []
    pats = [(bytes((0xC7, 0x44, 0x24, n)) + struct.pack("<I", value), "arg@rsp+0x%x" % n)
            for n in STACK_SLOTS]
    pats.append((b"\x41\xb9" + struct.pack("<I", value), "r9d"))
    for nm, vaddr, vsize, praw, rawsz in secs:
        if nm not in CODE_SECTIONS:
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
    try:
        buf, image_base, secs, index = load_dll()
    except BuildPinRefused as exc:
        print(str(exc))
        return 2
    print("build=%s" % index.build)

    def report(value, label, only_publishers=True):
        sites = scan_immediate(buf, image_base, secs, value)
        by_fn = {}
        for va, kind in sites:
            fn = index.resolve(va)[0]
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

    for name, who in WITNESSES.items():
        wv = int(EventTriggerType[name])
        report(wv, "TEMOIN %s -- %s" % (name, who))
    report(int(EventTriggerType[TARGET]), "CIBLE %s" % TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
