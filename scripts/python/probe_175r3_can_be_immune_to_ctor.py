#!/usr/bin/env python
"""probe #175-r3 -- `get_CanBeImmuneTo` quand le getter lit un CHAMP D'INSTANCE.

`probe_175r2_can_be_immune_to.py` tranche par les OCTETS du corps du getter, et il REFUSE de
conclure pour **49** classes dont le corps est `movzx eax, byte ptr [rcx+0x480] ; ret` : la valeur
n'y est pas une constante de classe, elle est ECRITE PAR LE `.ctor`. Ce probe-ci va la chercher la.

## L'ETAGE, lu au decompile (`t6dpr4k06g`)

    IdunBattle.Entities.Effects.AStatModifierEffect$$.ctor(
        this, sourceAbility, unitEffectType, canBeImmuneTo, keepOnRevive, isMultiply)
        -> this+0x480 = canBeImmuneTo ;  +0x481 = keepOnRevive ;  +0x482 = isMultiply

`get_CanBeImmuneTo` relit `+0x480`. En x64 MS, `canBeImmuneTo` est donc en **r9** pour ce `.ctor`
-- et c'est le PIEGE de cette lecture : les `.ctor` INTERMEDIAIRES n'ont pas la meme signature, et
lire r9 partout ferait rendre `isNegative` pour trois classes. Les positions sont donc DECLAREES
ci-dessous, une par `.ctor` intermediaire, chacune LUE au decompile.

## Ce que ce probe REFUSE de faire

  * deviner : une forme d'encodage non reconnue, un `.ctor` sans symbole (corps fondu par l'ICF) ou
    un `.ctor` intermediaire hors table sortent en `INDETERMINE`, jamais en `0` ;
  * conclure sans le jeu : sans `GameAssembly.dll`, il rend `NON MESURE` (rc 3), pas un verdict.

## Reproduire

    python probe_175r3_can_be_immune_to_ctor.py            # tableau + bilan
    python probe_175r3_can_be_immune_to_ctor.py --vrais    # seulement les `canBeImmuneTo = 1`

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import codecs
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pin                                     # noqa: E402
import probe_175r2_can_be_immune_to as P175          # noqa: E402

CTOR = "$" + "$.ctor"

#: OU se trouve `canBeImmuneTo` dans l'appel, PAR `.ctor` d'ancetre -- chaque entree LUE au
#: decompile, jamais deduite d'une convention. `"r9"` = 4e argument (registre), `"pile+0x20"` = 5e.
#: Un `.ctor` d'ancetre ABSENT de cette table rend `INDETERMINE` : c'est le refus, pas un defaut.
POSITION_PAR_CTOR = {
    # `.ctor(this, sourceAbility, unitEffectType, canBeImmuneTo, keepOnRevive, isMultiply)`
    "IdunBattle.Entities.Effects.AStatModifierEffect": "r9",
    # meme signature, verifiee : elle FORWARDE ses trois derniers arguments tels quels.
    "IdunBattle.Entities.Effects.StaticStatModifierEffect": "r9",
    # `.ctor(this, abilityType, variableType, isNegative, canBeImmuneTo)` -- r9 y est `isNegative`.
    "IdunBattle.Entities.Effects.DynamicStatModifierEffect": "pile+0x20",
}


def _sym_table(build: str) -> dict:
    p = HERE.parents[1] / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    out = {}
    if not p.is_file():
        return out
    for line in codecs.open(p, encoding="utf-8"):
        c = line.rstrip("\n").split("\t")
        if len(c) == 2:
            out[int(c[0], 16)] = c[1]
    return out


def _lire(pe, va: int, n: int) -> bytes:
    return bytes(int(x, 16) for x in (pe.octets(va, n) or "").split())


def analyser(pe, sym: dict, effets: set, va: int, n: int = 384):
    """`(valeur|None, forme, ctor_ancetre|None)` -- la DERNIERE ecriture de l'emplacement designe
    par `POSITION_PAR_CTOR[ancetre]`, avant le transfert vers ce `.ctor` d'ancetre."""
    b = _lire(pe, va, n)
    r9 = pile20 = None
    f9 = f20 = ""
    i = 0
    while i < len(b) - 5:
        # ---- r9 (4e argument)
        if b[i:i + 3] in (b"\x45\x33\xc9", b"\x4d\x33\xc9"):
            r9, f9, i = 0, "xor r9d,r9d", i + 3
            continue
        if b[i] == 0x41 and b[i + 1] == 0xB9:
            r9 = int.from_bytes(b[i + 2:i + 6], "little")
            f9, i = "mov r9d,0x%x" % r9, i + 6
            continue
        if b[i] == 0x41 and b[i + 1] == 0xB1:
            r9, f9, i = b[i + 2], "mov r9b,0x%x" % b[i + 2], i + 3
            continue
        if b[i] == 0x4C and b[i + 1] == 0x8B and (b[i + 2] & 0xC0) == 0xC0:
            r9, f9, i = None, "mov r9,<reg>", i + 3        # non litteral -> INDETERMINE
            continue
        # ---- [rsp+0x20] (5e argument) : `mov byte/dword ptr [rsp+0x20], imm`
        if b[i:i + 4] == b"\xc6\x44\x24\x20":
            pile20, f20, i = b[i + 4], "mov byte [rsp+0x20],0x%x" % b[i + 4], i + 5
            continue
        if b[i:i + 4] == b"\xc7\x44\x24\x20":
            pile20 = int.from_bytes(b[i + 4:i + 8], "little")
            f20, i = "mov dword [rsp+0x20],0x%x" % pile20, i + 8
            continue
        if b[i:i + 4] in (b"\x44\x88\x4c\x24", b"\x44\x89\x4c\x24") and b[i + 4] == 0x20:
            pile20, f20, i = None, "mov [rsp+0x20],r9 (non litteral)", i + 5
            continue
        # ---- transfert
        if b[i] in (0xE8, 0xE9):
            rel = int.from_bytes(b[i + 1:i + 5], "little", signed=True)
            nom = sym.get(va + i + 5 + rel, "")
            if nom.endswith(CTOR) and nom[:-len(CTOR)] in effets:
                anc = nom[:-len(CTOR)]
                pos = POSITION_PAR_CTOR.get(anc)
                if pos == "r9":
                    return r9, f9 or "(aucune ecriture de r9)", anc
                if pos == "pile+0x20":
                    return pile20, f20 or "(aucune ecriture de [rsp+0x20])", anc
                return None, "ctor d'ancetre HORS TABLE", anc
            i += 5
            continue
        i += 1
    return None, "aucun `.ctor` d'ancetre dans la fenetre", None


def mesurer() -> dict | None:
    try:
        meta = Path(build_pin.global_metadata())
    except build_pin.BuildPinRefused:
        return None
    dll = meta.parents[3] / "GameAssembly.dll"
    if not dll.is_file():
        return None
    build = build_pin.current_build()
    table = P175.deriver()
    if table is None:
        return None
    champ = sorted(n for n, r in table.items() if r.get("valeur_effective") is None)
    sym = _sym_table(build)
    if not sym:
        return None
    par_nom: dict[str, list[int]] = {}
    for va, nom in sym.items():
        par_nom.setdefault(nom, []).append(va)
    desc, _ = P175.fermeture(build)
    effets = set(desc) | {P175.BASE}
    pe = P175._PE(dll)                                              # noqa: SLF001
    out = {}
    for cls in champ:
        vas = sorted(par_nom.get(cls + CTOR, ()))
        if not vas:
            out[cls] = {"valeur": None, "forme": "AUCUN symbole `.ctor` (corps fondu par l'ICF)",
                        "ancetre": None}
            continue
        # Une classe peut avoir PLUSIEURS `.ctor` (surcharges). On les lit tous et on ne conclut
        # que s'ils s'accordent -- un desaccord est un INDETERMINE, pas une majorite.
        lus = [analyser(pe, sym, effets, va) for va in vas]
        vals = {v for v, _, _ in lus}
        if len(vals) == 1 and None not in vals:
            v, f, a = lus[0]
            out[cls] = {"valeur": int(v), "forme": f, "ancetre": a}
        else:
            out[cls] = {"valeur": None,
                        "forme": " | ".join("%s (%s)" % (v, f) for v, f, _ in lus),
                        "ancetre": lus[0][2]}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vrais", action="store_true",
                    help="n'imprimer que les classes a `canBeImmuneTo = 1`")
    a = ap.parse_args()
    res = mesurer()
    if res is None:
        print("[175-r3] NON MESURE -- le jeu n'est pas installe (ou la table de symboles manque). "
              "Ce n'est PAS un `aucune classe a true`.")
        return 3
    vrais = sorted(n for n, r in res.items() if r["valeur"] == 1)
    faux = sorted(n for n, r in res.items() if r["valeur"] == 0)
    indet = sorted(n for n, r in res.items() if r["valeur"] is None)
    if not a.vrais:
        for n in sorted(res):
            r = res[n]
            print("  %-4s %-62s %s"
                  % ("?" if r["valeur"] is None else r["valeur"], n.split(".")[-1], r["forme"]))
    print("\n[175-r3] %d classes a getter sur CHAMP D'INSTANCE : "
          "%d a `canBeImmuneTo = 1`, %d a `0`, %d INDETERMINEES"
          % (len(res), len(vrais), len(faux), len(indet)))
    for n in vrais:
        print("   VRAI : %s   (%s, via %s)" % (n, res[n]["forme"], res[n]["ancetre"]))
    if indet:
        print("   INDETERMINEES (aucune valeur inventee) :")
        for n in indet:
            print("      %-62s %s" % (n.split(".")[-1], res[n]["forme"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
