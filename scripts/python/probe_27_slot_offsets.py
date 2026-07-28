"""probe #27 -- quelles classes portent CalculateCustomUtility HORS du slot
+0x338 (celles qu'un balayage a offset FIGE rate silencieusement)."""
from __future__ import annotations

import sys

import probe_27_custom_utility_inventory as INV


def main() -> int:
    sid = INV._session_id()
    owners = INV.table_owners("gqfc5mff6c")
    found = INV.rpc(sid, "findClassesNamed", ["Playbook"])
    classes = sorted({(r["ns"], r["cls"]) for r in found["results"]})
    rows = INV.sweep_vtable(sid, classes)
    print("classes=%d" % len(classes))
    for ns, cls, rva, off, status in rows:
        if status != "ok" or off == "0x338":
            continue
        print("off=%-8s rva=0x%-8x owner=%-70s cls=%s.%s"
              % (off, rva, owners.get(rva, "<non nomme>"), ns, cls))
    return 0


if __name__ == "__main__":
    sys.exit(main())
