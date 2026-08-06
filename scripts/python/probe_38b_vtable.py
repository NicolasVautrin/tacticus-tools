"""Probe #38b — resolution OFFICIELLE des slots IBattleQuery via la vtable runtime de BattleQuery.

Le gate 1118 (`IdunBattle.AI.Playbook.Loki.DoctrinaImperativesPlaybook$$EvaluateNonComparable`) dispatch sur l'interface IBattleQuery
(DAT_18327ff80) aux slots 0x41 (via GetEligibleTargetsForNormalAttack) et 0x51 (adj) et 0xc9
(ReachedSummonCap). Le helper de dispatch du call-site 0x51 (`FUN_180003bd0`) ne passe QU'UN
argument -> la methode au slot 0x51 a exactement 1 parametre ; or toutes les surcharges
`GetAdjacentUnits` en prennent 3 (from, friendsOf, enemiesOf). Ce probe dump la vtable LIVE
de BattleQuery (RPC resolveVtableSlot, lecture pointeurs only), ancre le bloc interface via
IdunBattle.Core.Services.BattleQuery$$ReachedSummonCap (slot 0xca verifie) puis imprime les methodes aux slots vises.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

# VAs ghidra (build gqfc5mff6c) des candidats — RVA = VA - 0x180000000 calcule en code.
KNOWN = {
    0x181070f60: "BattleQuery.ReachedSummonCap",
    0x18105bca0: "BattleQuery.GetAdjacentUnits(list)",
    0x18105bc10: "BattleQuery.GetAdjacentUnits(single)",
    0x1810570c0: "AttackQuery.GetValidTargets",
    0x181057540: "AttackQuery.HasValidTargets",
    0x18106e8d0: "BattleQuery.HasValidTargets",
}


def main() -> int:
    sid = _resolve_session()
    rows = []
    # vtable Il2CppClass demarre a 0x138 ; scan large (0x138 .. 0x138 + 0x10*560)
    for start in range(0x138, 0x138 + 0x10 * 560, 0x10 * 70):
        end = start + 0x10 * 69
        r = _rpc(sid, "resolveVtableSlot",
                 [{"ns": "IdunBattle.Core.Services", "cls": "BattleQuery",
                   "start": start, "end": end}], timeout=60).get("result") or {}
        if not r.get("ok"):
            print("KO:", r.get("error"))
            return 1
        rows.extend(r.get("slots") or [])
    out = []
    anchor_c9 = None
    for s in rows:
        off = int(s["off"], 16)
        gva = s.get("ghidraVA") or ""
        try:
            g = int(gva, 16) if gva else 0
        except ValueError:
            g = 0
        tag = KNOWN.get(g, "")
        out.append({"off": hex(off), "slot_abs": hex((off - 0x138) // 0x10),
                    "ghidraVA": gva, "method": s.get("method"), "tag": tag})
        if g == 0x181070f60:
            anchor_c9 = off
    # SORTIE de run -> `logs/` RELATIF au checkout (#314) : un chemin absolu
    # ferait ecrire ce probe dans l'arbre principal depuis un worktree d'agent.
    dump = PYDIR.parents[1] / "logs" / "probes" / "_probe38b_vtable.json"
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"dumped {len(out)} slots -> logs/probes/_probe38b_vtable.json")
    if anchor_c9 is None:
        print("ANCHOR ReachedSummonCap NOT FOUND in scanned range")
        # print any named slots for manual inspection
        named = [o for o in out if o["method"]]
        print(f"named slots: {len(named)} (first 20)")
        for o in named[:20]:
            print(" ", o["off"], o["ghidraVA"], o["method"])
        return 2
    itf_base = anchor_c9 - 0xc9 * 0x10
    print(f"anchor ReachedSummonCap at byte off {hex(anchor_c9)} -> itf base {hex(itf_base)}"
          f" (abs slot {(itf_base - 0x138) // 0x10})")
    for slot in (0x3f, 0x41, 0x44, 0x51, 0x7f, 0xc9):
        off = itf_base + slot * 0x10
        o = next((x for x in out if int(x["off"], 16) == off), None)
        if o:
            print(f"  itf slot {hex(slot)}: off={o['off']} va={o['ghidraVA']} "
                  f"method={o['method']} {o['tag']}")
        else:
            print(f"  itf slot {hex(slot)}: off={hex(off)} HORS SCAN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
