"""Probe #79 -- resolution LIVE des slots virtuels de `ReviveEffect` (base) et de ses 4
sous-classes, pour trancher le gate overkill par LECTURE (jamais par deduction).

`ReviveEffect.CreateTargetTrigger @180f46d80` appelle 3 virtuels :
    byte  <- (**(klass + 0x738))(this, klass+0x740)   -> `ignoreOverkill` passe a OnPreDeath
    int   <- (**(klass + 0x748))(this, klass+0x750)   -> healType passe a CanBeRevived
    trig  <- (**(klass + 0x758))(this, klass+0x760)   -> CreateTargetFilter (override connu)

Le dump metadata ne liste PAS les corps foldes (`return 0` / `return 1` sont dedupliques par
ICF), donc le slot 0x738 est invisible offline. Le RPC `resolveVtableSlot` (introspect.ts,
lecture de pointeurs, ZERO invoke) rend le nom + la VA ghidra de chaque slot pour la CLASSE
CONCRETE -> on compare les 4 sous-classes entre elles et avec l'ancre 0x758 (CreateTargetFilter,
dont on connait la VA par classe).

Sortie : data/_probe79_revive_vtable.json (ASCII only sur la console).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

NS_LOKI = "IdunBattle.Entities.Effects.Loki"
NS_BASE = "IdunBattle.Entities.Effects"

# ancres VA connues (ghidra, build gqfc5mff6c) -> RVA calculee en code par le hook
ANCHORS = {
    0x180f5acf0: "Narthecium_ReviveEffect.CreateTargetFilter",
    0x180f709b0: "TaintedNarthecium_ReviveEffect.CreateTargetFilter",
    0x180f67ac0: "ReanimationBeam_ReviveEffect.CreateTargetFilter",
    0x180f69c10: "RitesOfMorkaiEffect.CreateTargetFilter",
    0x180f46d80: "ReviveEffect.CreateTargetTrigger",
    0x180f46a70: "ReviveEffect.CreateTargetTriggerBehaviour",
}

CLASSES = [
    (NS_LOKI, "Narthecium_ReviveEffect"),
    (NS_LOKI, "TaintedNarthecium_ReviveEffect"),
    (NS_LOKI, "ReanimationBeam_ReviveEffect"),
    (NS_LOKI, "RitesOfMorkaiEffect"),
    (NS_BASE, "ReviveEffect"),
]

# Les slots lus par le decompile sont a 0x738/0x748/0x758 -> l'alignement de la vtable est
# ...8 (offset impair de 8 par rapport a 0x10). On scanne donc 0x6f8..0x7a8 par pas de 0x10.
START = 0x6F8
END = 0x7A8


def main() -> int:
    sid = _resolve_session()
    out = {}
    for ns, cls in CLASSES:
        r = _rpc(sid, "resolveVtableSlot",
                 [{"ns": ns, "cls": cls, "start": START, "end": END}],
                 timeout=60).get("result") or {}
        if not r.get("ok"):
            print(f"KO {cls}: {r.get('error')}")
            out[cls] = {"error": r.get("error")}
            continue
        slots = []
        for s in r.get("slots") or []:
            gva = s.get("ghidraVA") or ""
            try:
                g = int(gva, 16) if gva else 0
            except ValueError:
                g = 0
            slots.append({"off": s["off"], "va": gva, "funcVA": s.get("funcVA"),
                          "method": s.get("method"), "anchor": ANCHORS.get(g, "")})
        out[cls] = {"klass": r.get("klass"), "slots": slots}
        print(f"=== {cls} klass={r.get('klass')}")
        for s in slots:
            print(f"  {s['off']:>6} va={s['va']:>12} m={s['method']} {s['anchor']}")
    Path(r"C:\Users\nicolasv\tacticus-tools\data\_probe79_revive_vtable.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")
    print("-> data/_probe79_revive_vtable.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
