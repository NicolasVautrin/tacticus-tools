#!/usr/bin/env python
"""probe_224_can_be_immune_to -- INVENTAIRE du drapeau `get_CanBeImmuneTo` par classe d'effet.

`IdunBattle.Entities.Effects.BaseEffect$$EntityIsImmuneToEffect` =
`HasTrait(entity, 0x19 = 25 = UnitTrait.Immune) && this.CanBeImmuneTo` -- ou `CanBeImmuneTo` est un
VIRTUEL (slot de vtable) dont la base rend FAUX. Aucun `get_CanBeImmuneTo` n'apparait dans
`data/symbols/<build>/frida/methods.tsv` (les corps triviaux `return 0` / `return 1` sont PARTAGES par
IL2CPP, et le dump est keye par RVA -> une seule ligne survit). Le seul inventaire fiable est donc la
lecture de la VTABLE RUNTIME, par classe (`resolveVtableSlot`), en matchant le NOM de la methode (jamais
un offset fixe : le bloc des virtuels de classe est decale par le nombre d'interfaces implementees).

Sortie : une ligne par classe d'effet portant `CanBeImmuneTo = true`, plus les surcharges de
`EntityIsImmuneToEffect` et de `CreateActiveCondition` reperees au passage.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_224_can_be_immune_to.py [--ns IdunBattle.Entities.Effects.Loki] [--limit N]

ASCII only (cp1252). Lecture PURE (aucun runner, aucune invocation native).
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

import rl_collect_batch as R

HOST = "http://127.0.0.1:8765"
CLASSES_TSV = (Path(__file__).resolve().parents[2] / "data" / "symbols")
WANTED = ("get_CanBeImmuneTo", "EntityIsImmuneToEffect", "CreateActiveCondition")


def _classes():
    build = None
    for p in sorted(CLASSES_TSV.glob("*/BUILD")):
        build = p.parent
    if build is None:
        raise RuntimeError("data/symbols/<build> introuvable")
    out = []
    with open(build / "frida" / "classes.tsv", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#!"):
                continue
            name = line.split("\t")[0]
            if name.startswith("IdunBattle.Entities.Effects.") and not name.endswith("[]"):
                out.append(name)
    return out


def _slots(sid, ns, cls, start=0x148, end=0x680):
    body = json.dumps({"method": "resolveVtableSlot",
                       "args": {"ns": ns, "cls": cls, "start": start, "end": end},
                       "timeout": 30000}).encode()
    req = urllib.request.Request("%s/api/scripts/%s/rpc" % (HOST, sid), data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as fh:
        res = json.loads(fh.read().decode()).get("result") or {}
    return res.get("slots") or []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    sid = R._resolve_session()
    names = _classes()
    if a.only:
        keep = set(a.only.split(","))
        names = [n for n in names if n.rsplit(".", 1)[-1] in keep]
    if a.limit:
        names = names[:a.limit]
    print("classes d'effet: %d" % len(names))
    immune_true, immune_over, active_cond = [], [], []
    for full in names:
        ns, cls = full.rsplit(".", 1)
        try:
            slots = _slots(sid, ns, cls)
        except Exception as exc:                       # classe non trouvee / non initialisee
            print("  SKIP %s (%s)" % (full, exc))
            continue
        seen = {}
        for s in slots:
            m = s.get("method") or ""
            if m in WANTED:
                seen.setdefault(m, s.get("ghidraVA"))
        cbi = seen.get("get_CanBeImmuneTo")
        if cbi == "0x1802b1590":                       # stub partage `return 1`
            immune_true.append((cls, cbi))
        eii = seen.get("EntityIsImmuneToEffect")
        if eii and eii != "0x180f109b0":               # != BaseEffect$$EntityIsImmuneToEffect
            immune_over.append((cls, eii))
        ac = seen.get("CreateActiveCondition")
        if ac and ac != "0x1802b15b0":                 # != stub `return null`
            active_cond.append((cls, ac))
    print("\n== CanBeImmuneTo == TRUE (%d) ==" % len(immune_true))
    for c, va in immune_true:
        print("  %s" % c)
    print("\n== EntityIsImmuneToEffect SURCHARGE (%d) ==" % len(immune_over))
    for c, va in immune_over:
        print("  %-50s %s" % (c, va))
    print("\n== CreateActiveCondition non trivial (%d) ==" % len(active_cond))
    for c, va in active_cond:
        print("  %-50s %s" % (c, va))


if __name__ == "__main__":
    main()
