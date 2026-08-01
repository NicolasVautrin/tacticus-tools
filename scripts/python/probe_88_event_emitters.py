"""probe #88 -- QUI emet `On(<EventTriggerType>)` cote natif ?

Le dispatcher d'evenements de trigger est `FUN_1800280e0(msgId, <static>, events, eventType,
entities)` (convention x64 : rcx, rdx, r8, **r9d = eventType**). Les call-sites sont donnes par
ghidra (`list_xrefs FUN_1800280e0`) ; ce probe DECODE l'immediat charge dans `r9d` juste avant
chaque `call`, en lisant `GameAssembly.dll` -- aucune VA n'est ecrite a la main, le mapping
VA -> offset fichier est calcule depuis les sections du PE.

But immediat : localiser l'emetteur de `On(PendingDeathAdded = 3)` (residu A1 de
`docs/rl/case-66-revive-in-place.md` §8.1) et confirmer celui d'`On(PreUnitMove = 31)` (residu A2
§8.2). Sortie ASCII pure.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

GAME_DLL = Path(r"C:\Users\nicolasv\AppData\Local\tacticus\games\gqfc5mff6c\GameAssembly.dll")

# Call-sites de `FUN_1800280e0` rendus par `mcp__ghidra__list_xrefs` (type UNCONDITIONAL_CALL).
CALL_SITES = [
    ("ADamageOperation$$RegisterFinalDamage", 0x180e269c8),
    ("AbilityDamageOperation$$ExecuteHit", 0x180e2a277),
    ("ADamageOperation$$EvaluateAfterHitTriggers", 0x180e26347),
    ("ADamageOperation$$EvaluateAfterHitTriggers", 0x180e263f7),
    ("ActiveAbilityOperation$$ExecuteInternal", 0x180e45cd9),
    ("ActiveAbilityOperation$$ExecuteInternal", 0x180e46527),
    ("ActiveAbilityOperation$$ExecuteInternal", 0x180e46607),
    ("ActiveAbilityOperation$$ExecuteInternal", 0x180e467b7),
    ("AddEffectOperation$$Execute", 0x180e48e87),
    ("AddEffectOperation$$Execute", 0x180e49687),
    ("AddEffectOperation$$Execute", 0x180e49817),
    ("AddUnitOperation$$Execute", 0x180e557a7),
    ("AddUnitOperation$$Execute", 0x180e55bd7),
    ("ApplyDamageOperation$$Execute", 0x180e5b998),
    ("ApplyDamageOperation$$Execute", 0x180e5cac7),
    ("ApplyDamageOperation$$Execute", 0x180e5d097),
    ("AttackDamageOperation$$ExecuteHit", 0x180e5f7c7),
    ("AttackDamageOperation$$ExecuteHit", 0x180e5f877),
    ("DestroyMachineOperation$$Execute", 0x180e67247),
    ("DestroyMachineOperation$$Execute", 0x180e67547),
    ("EndPhaseOperation$$Execute", 0x180e6a1dc),
    ("FinishAttackOperation$$Execute", 0x180e718f9),
    ("FinishAttackOperation$$Execute", 0x180e719a8),
    ("KillUnitOperation$$Execute", 0x180e76c47),
    ("KillUnitOperation$$Execute", 0x180e76de5),
    ("KillUnitOperation$$Execute", 0x180e77264),
    ("KillUnitOperation$$Execute", 0x180e77317),
    ("KillUnitOperation$$Execute", 0x180e77497),
    ("MachineDamageOperation$$ExecuteHit", 0x180e78057),
    ("MoveUnitOperation$$Execute", 0x180e7a7d7),
    ("MoveUnitOperation$$EvaluateAfterMoveTriggers", 0x180e79a84),
    ("MoveUnitOperation$$EvaluateAfterMoveTriggers", 0x180e79b35),
    ("MoveUnitOperation$$EvaluateAfterMoveTriggers", 0x180e79bd6),
    ("MoveUnitOperation$$EvaluatePreMoveTriggers", 0x180e79fba),
    ("RemoveEffectOperation$$Execute", 0x180e87387),
    ("RemoveEffectOperation$$Execute", 0x180e876f7),
    ("RemoveEffectOperation$$Execute", 0x180e87837),
    ("ReviveUnitOperation$$Execute", 0x180e9268c),
    ("ReviveUnitOperation$$SetRevivePosition", 0x180e93b27),
    ("ReviveUnitOperation$$SetRevivePosition", 0x180e93bd7),
    ("SetupGameOperation$$Execute", 0x180e99cbb),
    ("SpawnUnitsOfTurnOperation$$Execute", 0x180ea030b),
    ("SpawnUnitsOfTurnOperation$$Execute", 0x180ea050a),
    ("StartAttackOperation$$Execute", 0x180ea25c7),
    ("StartTurnOperation$$Execute", 0x180ea5448),
    ("StartTurnOperation$$Execute", 0x180ea54f7),
    ("StartTurnOperation$$Execute", 0x180ea55a7),
    ("StartTurnOperation$$Execute", 0x180ea5657),
    ("StartTurnOperation$$Execute", 0x180ea5707),
    ("TransformActorToConfigIdOperation$$Execute", 0x180ea79ac),
    ("TransformActorToConfigIdOperation$$UpdateStats", 0x180ea90b9),
    ("VerifyTerritoryCaptureOperation$$Execute", 0x180eddd77),
    ("VerifyTerritoryCaptureOperation$$Execute", 0x180edde47),
    ("BaseTriggeredAbility$$Execute", 0x180fbc264),
    ("EvaluateAbilitiesBehaviour$$Execute", 0x180fc4dc5),
]

EVENT_NAMES = {}


def _load_event_names() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from engine.dsl.event_trigger_type import EventTriggerType
    for m in EventTriggerType:
        EVENT_NAMES[int(m)] = m.name


def _sections(buf: bytes):
    pe_off = struct.unpack_from("<I", buf, 0x3C)[0]
    n_sec = struct.unpack_from("<H", buf, pe_off + 6)[0]
    opt_size = struct.unpack_from("<H", buf, pe_off + 20)[0]
    image_base = struct.unpack_from("<Q", buf, pe_off + 24 + 24)[0]
    sec_off = pe_off + 24 + opt_size
    out = []
    for i in range(n_sec):
        o = sec_off + i * 40
        vaddr = struct.unpack_from("<I", buf, o + 12)[0]
        vsize = struct.unpack_from("<I", buf, o + 8)[0]
        praw = struct.unpack_from("<I", buf, o + 20)[0]
        out.append((vaddr, vsize, praw))
    return image_base, out


def va_to_off(image_base: int, secs, va: int):
    rva = va - image_base
    for vaddr, vsize, praw in secs:
        if vaddr <= rva < vaddr + vsize:
            return praw + (rva - vaddr)
    return None


def r9d_immediate(buf: bytes, off: int):
    """Dernier `mov r9d, imm32` (41 B9 xx xx xx xx) dans les 64 octets qui precedent le `call`.
    Renvoie None si l'immediat n'est pas materialise a proximite (r9 charge autrement)."""
    window = buf[off - 64:off]
    found = None
    i = 0
    while i + 6 <= len(window):
        if window[i] == 0x41 and window[i + 1] == 0xB9:
            found = struct.unpack_from("<I", window, i + 2)[0]
            i += 6
            continue
        i += 1
    return found


def main() -> int:
    _load_event_names()
    if not GAME_DLL.exists():
        print("ABSENT: %s" % GAME_DLL)
        return 2
    buf = GAME_DLL.read_bytes()
    image_base, secs = _sections(buf)
    print("image_base = 0x%x  sections = %d" % (image_base, len(secs)))
    print("%-46s %-12s %-6s %s" % ("emetteur", "call VA", "event", "nom EventTriggerType"))
    print("-" * 100)
    hits3, hits31 = [], []
    for name, va in CALL_SITES:
        off = va_to_off(image_base, secs, va)
        if off is None:
            print("%-46s 0x%-10x %-6s (hors section)" % (name, va, "?"))
            continue
        imm = r9d_immediate(buf, off)
        label = EVENT_NAMES.get(imm, "?") if imm is not None else "(r9 non immediat)"
        print("%-46s 0x%-10x %-6s %s" % (name, va, imm if imm is not None else "-", label))
        if imm == 3:
            hits3.append((name, va))
        if imm == 31:
            hits31.append((name, va))
    print("-" * 100)
    print("On(PendingDeathAdded=3)  emetteurs : %s" % (hits3 or "AUCUN parmi ces call-sites"))
    print("On(PreUnitMove=31)       emetteurs : %s" % (hits31 or "AUCUN parmi ces call-sites"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
