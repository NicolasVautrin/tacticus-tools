"""probe #27 -- dump BRUT de la vtable d'une classe (controle de bornes).

Sert a verifier qu'un slot trouve hors de l'offset habituel n'est pas une
lecture HORS vtable (les Il2CppClass sont contigus en memoire : depasser la
vtable d'une classe retombe sur la suivante et peut rendre un MethodInfo
parfaitement nomme -- faux positif).

Usage : python probe_27_vtable_dump.py <ns> <cls> [start] [end]
"""
from __future__ import annotations

import sys

import probe_27_custom_utility_inventory as INV


def main() -> int:
    ns, cls = sys.argv[1], sys.argv[2]
    start = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x108
    end = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0x808
    sid = INV._session_id()
    res = INV.rpc(sid, "resolveVtableSlot",
                  [{"ns": ns, "cls": cls, "start": start, "end": end}])
    if not res or not res.get("ok"):
        print("KO %r" % res)
        return 1
    print("klass=%s %s.%s" % (res["klass"], ns, cls))
    for s in res["slots"]:
        print("  %-6s rva=%-10s %s"
              % (s["off"], s["funcRVA"] or "-", s["method"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
