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

⚠ REPARE (#175-r2, 2026-08-08). Ce probe TRANCHAIT par TROIS VA LITTERALES (le stub `return 1`, le
corps de `BaseEffect$$EntityIsImmuneToEffect`, le stub `return null`) heritees d'un build
ANTERIEUR. Sur `rnca9r7q6c` il rendait donc `CanBeImmuneTo == TRUE (0)` -- un FAUX ZERO -- et
classait 9 classes sur 10 en `EntityIsImmuneToEffect SURCHARGE` alors qu'elles pointaient toutes sur
le corps de `BaseEffect` lui-meme. Les trois references sont desormais DERIVEES :
  * le corps de la BASE se lit sur `BaseEffect` elle-meme (rien n'est suppose de sa valeur) ;
  * `CanBeImmuneTo` se tranche par les OCTETS du corps (`b0 01 c3` / `32 c0 c3`), jamais par une VA.
Ce probe reste un INVENTAIRE RUNTIME, donc borne aux classes DEJA INITIALISEES et au namespace
`IdunBattle.Entities.Effects.*`. L'inventaire COMPLET (fermeture transitive, hors namespace inclus,
independant de l'initialisation) est `probe_175r2_can_be_immune_to.py`.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_224_can_be_immune_to.py [--ns IdunBattle.Entities.Effects.Loki] [--limit N]

ASCII only (cp1252). Lecture PURE (aucun runner, aucune invocation native).
"""
from __future__ import annotations

import argparse
import json
import struct
import urllib.request
from pathlib import Path

import rl_collect_batch as R

HOST = "http://127.0.0.1:8765"
CLASSES_TSV = (Path(__file__).resolve().parents[2] / "data" / "symbols")
WANTED = ("get_CanBeImmuneTo", "EntityIsImmuneToEffect", "CreateActiveCondition")
#: les deux corps triviaux, DESIGNES PAR LEURS OCTETS. `mov al,1 ; ret` / `xor eax,eax ; ret`.
OCTETS_VRAI, OCTETS_FAUX = "b0 01 c3", "32 c0 c3"
#: la classe dont on LIT les corps de reference (au lieu de les ecrire en dur).
REFERENCE = ("IdunBattle.Entities.Effects", "BaseEffect")


def _pe_octets():
    """`(va) -> octets hex`, ou `None` si le jeu n'est pas installe (PAS MESURE, jamais un vert)."""
    import build_pin
    try:
        meta = Path(build_pin.global_metadata())
    except build_pin.BuildPinRefused:
        return None
    dll = meta.parents[3] / "GameAssembly.dll"
    if not dll.is_file():
        return None
    data = dll.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 20)[0]
    secs = []
    for k in range(nsec):
        o = pe + 24 + opt + 40 * k
        vsz, vaddr, rsz, raddr = struct.unpack_from("<IIII", data, o + 8)
        secs.append((vaddr, vsz, raddr, rsz))

    def octets(va: int, n: int = 3):
        rva = va - 0x180000000
        for vaddr, vsz, raddr, rsz in secs:
            if vaddr <= rva < vaddr + max(vsz, rsz):
                off = raddr + (rva - vaddr)
                return data[off:off + n].hex(" ")
        return None
    return octets


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
    octets = _pe_octets()
    if octets is None:
        print("PAS MESURE : le jeu n'est pas installe -- les corps ne peuvent pas etre identifies "
              "par leurs octets. Aucun inventaire n'est rendu.")
        return
    # REFERENCES DERIVEES : le corps de `BaseEffect$$EntityIsImmuneToEffect` et celui du
    # `CreateActiveCondition` de la BASE, LUS sur la classe de reference -- jamais ecrits en dur.
    ref = {}
    for s in _slots(sid, *REFERENCE):
        m = s.get("method") or ""
        if m in WANTED:
            ref.setdefault(m, s.get("ghidraVA"))
    base_eii, base_ac = ref.get("EntityIsImmuneToEffect"), ref.get("CreateActiveCondition")
    if base_eii is None:
        print("PAS MESURE : la vtable de %s.%s ne porte pas `EntityIsImmuneToEffect` -- classe non "
              "initialisee ?" % REFERENCE)
        return
    # `CreateActiveCondition` : la BASE ne l'expose pas toujours dans la fenetre de slots balayee.
    # A defaut de reference LUE, un corps est dit TRIVIAL par ses OCTETS (`return null` = un
    # `xor <reg>,<reg> ; ret`). C'est le meme principe que pour `CanBeImmuneTo`, et il ne suppose
    # aucune adresse.
    STUBS_NULS = ("31 c0 c3", "33 c0 c3", "32 c0 c3")
    print("references LUES sur %s : EntityIsImmuneToEffect=%s, CreateActiveCondition=%s"
          % (REFERENCE[1], base_eii, base_ac or "(absente -> critere par OCTETS)"))
    immune_true, immune_over, active_cond, illisibles = [], [], [], []
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
        if cbi:
            # TRANCHE PAR LES OCTETS DU CORPS, jamais par la VA : les corps triviaux sont fondus
            # par l'ICF et leur adresse change a chaque build.
            oct_ = octets(int(cbi, 16)) or ""
            if oct_ == OCTETS_VRAI:
                immune_true.append((cls, cbi))
            elif oct_ != OCTETS_FAUX:
                illisibles.append((cls, "get_CanBeImmuneTo corps non trivial (%s, %s)"
                                   % (cbi, oct_ or "?")))
        eii = seen.get("EntityIsImmuneToEffect")
        if eii and eii != base_eii:                    # != le corps LU sur BaseEffect
            immune_over.append((cls, eii))
        ac = seen.get("CreateActiveCondition")
        if ac and (ac != base_ac if base_ac else (octets(int(ac, 16)) or "") not in STUBS_NULS):
            active_cond.append((cls, ac))
    print("\n== CanBeImmuneTo == TRUE (%d) ==" % len(immune_true))
    for c, va in immune_true:
        print("  %s" % c)
    if illisibles:
        print("\n== ILLISIBLES (%d) -- ni un vrai ni un faux ==" % len(illisibles))
        for c, why in illisibles:
            print("  %-50s %s" % (c, why))
    print("\n== EntityIsImmuneToEffect SURCHARGE (%d) ==" % len(immune_over))
    for c, va in immune_over:
        print("  %-50s %s" % (c, va))
    print("\n== CreateActiveCondition non trivial (%d) ==" % len(active_cond))
    for c, va in active_cond:
        print("  %-50s %s" % (c, va))


if __name__ == "__main__":
    main()
