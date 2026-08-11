#!/usr/bin/env python3
"""#951 -- trancher une surcharge par l'ADRESSE REELLE de la cible du `call` (`E8 rel32`).

POURQUOI
--------
Le pseudo-C de ghidra nomme la surcharge qu'il a choisie, pas celle que l'encodage designe.
`DSLBehaviors$$AttackWithAttackDamage` existe en **5** exemplaires, `DSLBehaviors$$AddEffect`
en **4**, `DSLTriggers$$On` en **3** : le nom rendu ne discrimine RIEN. Le seul canal fiable
est le `rel32` de l'instruction `E8`, resolu contre `data/symbols/<build>/ghidra/functions.tsv`.

Ce probe lit les octets par le serveur ghidra-mcp (meme binaire que le decompile), decode tous
les `call rel32` d'une fonction, et rend `<VA cible> -> <symbole>` avec la SIGNATURE lue dans
`frida/methods.tsv` quand elle y est.

TRI-ETAT : serveur injoignable -> rc 2 et rien d'affiche. Jamais un << 0 appel >> rassurant.

Sortie console ASCII stricte (cp1252).
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import capstone

import mcp_ghidra

IMAGE_BASE = 0x180000000
RACINE = Path(__file__).resolve().parents[2]

_MD = None


def _md():
    """Desassembleur x86-64. capstone lit l'ENCODAGE, pas le pseudo-C : c'est le seul
    canal qui distingue `AttackWithAttackDamage` (5 surcharges) de ses jumelles."""
    global _MD
    if _MD is None:
        _MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    return _MD


def _build() -> str:
    return (RACINE / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()


def _table_fonctions(build: str) -> dict[int, str]:
    p = RACINE / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    table: dict[int, str] = {}
    for ligne in io.open(p, encoding="utf-8"):
        f = ligne.rstrip("\n").split("\t")
        if len(f) < 2:
            continue
        try:
            table[int(f[0], 16)] = f[1]
        except ValueError:
            continue
    return table


def _table_signatures(build: str) -> dict[int, str]:
    """RVA -> `ret args` lu dans frida/methods.tsv (absent = corps non propre)."""
    p = RACINE / "data" / "symbols" / build / "frida" / "methods.tsv"
    table: dict[int, str] = {}
    for ligne in io.open(p, encoding="utf-8"):
        f = ligne.rstrip("\n").split("\t")
        if len(f) < 6:
            continue
        try:
            rva = int(f[0], 16)
        except ValueError:
            continue
        table[rva] = "%s (%s)" % (f[4], f[5])
    return table


def _resoudre(va: int, table: dict[int, str]) -> str:
    if va in table:
        return table[va]
    # point interne : plus grande entree <= va
    cands = [a for a in table if a <= va]
    if not cands:
        return "??"
    base = max(cands)
    return "%s+0x%x" % (table[base], va - base)


def _octets(mcp: mcp_ghidra.Mcp, binaire: str, va: int, taille: int) -> bytes:
    r = mcp._appel("tools/call", {
        "name": "read_bytes",
        "arguments": {"binary_name": binaire, "address": hex(va), "size": taille},
    })
    st = (r.get("result") or {}).get("structuredContent") or {}
    brut = st.get("data")
    if brut is None:                       # le repli TEXTE porte un JSON, pas du hex nu
        import json as _json
        for c in (r.get("result") or {}).get("content") or []:
            if c.get("type") == "text":
                brut = _json.loads(c["text"]).get("data")
                break
    if brut is None:
        raise RuntimeError("read_bytes muet: " + str(r)[:300])
    if isinstance(brut, list):
        return bytes(brut)
    return bytes.fromhex(str(brut).strip())


def analyser(noms: list[str], taille: int, detail: bool = False,
             fenetre: "tuple[int, int] | None" = None,
             binaire: str = "GameAssembly.dll") -> int:
    if mcp_ghidra.disponible() is None:
        print("ghidra-mcp INJOIGNABLE -- PAS MESURE")
        return 2
    build = _build()
    fonctions = _table_fonctions(build)
    signatures = _table_signatures(build)
    inverse = {}
    for va, nom in fonctions.items():
        inverse.setdefault(nom, va)

    mcp = mcp_ghidra.Mcp()
    mcp.ouvrir()
    for nom in noms:
        depart = inverse.get(nom)
        if depart is None:
            print("INTROUVABLE dans functions.tsv : %s" % nom)
            continue
        # borne : prochaine fonction connue
        suivantes = [a for a in fonctions if a > depart]
        fin = min(suivantes) if suivantes else depart + taille
        n = min(taille, fin - depart)
        data = _octets(mcp, binaire, depart, n)
        print("=== %s  (%d octets)" % (nom, n))
        for ins in _md().disasm(data, depart):
            off = ins.address - depart
            # E8 = call rel32 ; E9 = jmp rel32 (tail call : le DERNIER appel d'une
            # fonction n'est pas un `call`, et le rater fait conclure << aucun appel >>)
            if ins.mnemonic in ("call", "jmp") and ins.op_str.startswith("0x"):
                cible = int(ins.op_str, 16)
                if ins.mnemonic == "jmp" and depart <= cible < depart + len(data):
                    continue                    # saut INTERNE : pas un appel
                sig = signatures.get(cible - IMAGE_BASE)
                print("   +0x%-4x %-4s -> %s" % (off, ins.mnemonic,
                                                 _resoudre(cible, fonctions)))
                if sig:
                    print("            sig: %s" % sig)
            elif fenetre and fenetre[0] <= off <= fenetre[1]:
                print("   +0x%-4x %s %s" % (off, ins.mnemonic, ins.op_str))
            elif detail and (ins.mnemonic.startswith("mov") or ins.mnemonic == "xor"
                             or ins.mnemonic == "lea"):
                print("   +0x%-4x %s %s" % (off, ins.mnemonic, ins.op_str))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="#951 -- cibles reelles des `call rel32`")
    ap.add_argument("noms", nargs="+", help="symboles ghidra VERBATIM")
    ap.add_argument("--taille", type=int, default=0x800)
    ap.add_argument("--detail", action="store_true",
                    help="montre aussi mov/xor/lea -- les LITTERAUX passes aux appels")
    ap.add_argument("--fenetre", default=None,
                    help="DEB:FIN en hexa -- desassemblage INTEGRAL de la fenetre, seul canal"
                         " ou les tests et les sauts (donc les GATES) sont visibles")
    a = ap.parse_args()
    f = None
    if a.fenetre:
        d, _, g = a.fenetre.partition(":")
        f = (int(d, 16), int(g, 16))
    return analyser(a.noms, a.taille, a.detail, f)


if __name__ == "__main__":
    sys.exit(main())
