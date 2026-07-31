"""Probe #358 -- QUI enregistre un `EffectType` dans `IdunBattle.Core.Services.EffectsDatabase`,
et avec quels arguments.

LA QUESTION BINAIRE : l'effet `1581 MyWillBeDoneOverlord_ExtraDamage` est POSE par le passif
`MyWillBeDoneOverlord`, mais sa magnitude n'est lue par AUCUNE fonction de la classe d'ability. Quelle
fonction native la consomme ?

REPONSE, et pourquoi elle n'est pas devinable depuis la classe d'ability : l'effet n'a **aucune classe
native dediee**. `EffectsDatabase$$InitializeEffects` enregistre, pour chaque `EffectType`, une FABRIQUE
(`Func<AEffect>`) qui est une lambda `<>c$$<InitializeEffects>b__14_N`. Pour 1581 cette lambda construit
une instance GENERIQUE `DynamicStatModifierEffect(AbilityType(1556), variableType, isNegative,
canBeImmuneTo)`, et c'est le corps generique
`DynamicStatModifierEffect$$GetDynamicStatModificationAmount` qui lit la magnitude
(`ConfigVar(abilityOrEffect, EffectSource(Get(effect)), variableType)`, niee si `isNegative`).

CE QUE LE PROBE MESURE (aucune deduction -- que des octets) :

  1. Le motif d'ENREGISTREMENT, repete pour chaque `EffectType` :
         48 89 b1 <off32>     mov [rcx+off], rsi     ; cache du delegate, champ statique `<>9__14_N`
         4c 8b 0d <rel32>     mov r9, [rip+..]       ; MethodInfo* de l'Add
         4c 8b c6             mov r8, rsi            ; le delegate
         ba <imm32>           mov edx, <effectType>
         48 8b cf             mov rcx, rdi           ; le dictionnaire
         e8 <rel32>           call <Add>
     Les statiques de `<>c` etant `[<>9, <>9__14_0, <>9__14_1, ...]`, on a `off = 8 * (N + 1)` --
     c'est CE qui relie une lambda a son `EffectType`. La loi est VERIFIEE, pas supposee : tous les
     offsets multiples de 8, autant d'indices `N` distincts que d'enregistrements, aucun `EffectType`
     enregistre deux fois, et tous les `Add` visent la MEME fonction.
  2. Le balayage EXHAUSTIF des `Add` (motif reduit, sans supposer qu'un delegate est cree juste avant)
     -- c'est lui qui autorise a dire d'un `EffectType` qu'il n'est PAS enregistre.
  3. Les arguments de la lambda demandee, LUS AU DESASSEMBLAGE (`mov edx` = l'`AbilityType`,
     `mov r8d` = le `variableType`, `xor r9d,r9d` / `mov r9d` = `isNegative`, `[rsp+0x20]` =
     `canBeImmuneTo`) -- ghidra perd l'immediat de l'`AbilityType` dans son decompile.

Usage :
    python probe_358_effects_database_registry.py                  # loi + les 1581/1582/1583
    python probe_358_effects_database_registry.py --effect 1581    # + desassemblage de sa lambda
    python probe_358_effects_database_registry.py --effect 1541 --effect 1485

ENTREE GITIGNOREE : `GameAssembly.dll` du build courant vit hors du depot
(`%LOCALAPPDATA%/tacticus/games/<hash>/`). Absent -> le probe le DIT et sort en erreur, il ne rend
jamais un zero silencieux. Le hash est lu dans `data/symbols/CURRENT` (entree VERSIONNEE).
ASCII only (console cp1252). Aucune ecriture -- lecture pure.
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
IMAGE_BASE = 0x180000000

#: symbole -> (VA de debut, VA de fin) ; la fin est la VA de la fonction SUIVANTE en memoire.
INIT_EFFECTS = "IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects"
LAMBDA_PREFIX = ("IdunBattle.Core.Services.EffectsDatabase."
                 "u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_")


def build_hash() -> str:
    return (ROOT / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()


def dll_path(bhash: str) -> Path:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "tacticus" / "games" / bhash / "GameAssembly.dll"


def functions(bhash: str) -> "list[tuple[int, str]]":
    """`data/symbols/<hash>/ghidra/functions.tsv` (entree VERSIONNEE), trie par adresse."""
    p = ROOT / "data" / "symbols" / bhash / "ghidra" / "functions.tsv"
    rows = []
    with p.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2:
                try:
                    rows.append((int(parts[0], 16), parts[1]))
                except ValueError:
                    continue
    rows.sort()
    return rows


def span(rows, symbol) -> "tuple[int, int]":
    """(VA de debut, VA de la fonction SUIVANTE) -- borne haute du corps a balayer."""
    for i, (addr, name) in enumerate(rows):
        if name == symbol:
            return addr, (rows[i + 1][0] if i + 1 < len(rows) else addr + 0x40000)
    raise SystemExit("symbole absent de functions.tsv: %s" % symbol)


def sections(buf) -> list:
    pe_off = struct.unpack_from("<I", buf, 0x3C)[0]
    if buf[pe_off:pe_off + 4] != b"PE\0\0":
        raise SystemExit("en-tete PE introuvable")
    nsec = struct.unpack_from("<H", buf, pe_off + 6)[0]
    opt_size = struct.unpack_from("<H", buf, pe_off + 20)[0]
    sec_off = pe_off + 24 + opt_size
    out = []
    for i in range(nsec):
        o = sec_off + i * 40
        vsize, vaddr, rsize, raddr = struct.unpack_from("<IIII", buf, o + 8)
        out.append((vaddr, vsize, raddr, rsize))
    return out


def va_to_off(secs, va) -> "int | None":
    rva = va - IMAGE_BASE
    for vaddr, vsize, raddr, rsize in secs:
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raddr + (rva - vaddr)
    return None


def scan_registrations(buf, secs, start_va, end_va):
    """Rend (`{effectType: N}`, `[effectType]` dans l'ordre des Add, `{cible d'appel: compte}`)."""
    s, e = va_to_off(secs, start_va), va_to_off(secs, end_va)
    by_effect, adds, targets = {}, [], {}
    # (1) motif COMPLET : store du delegate + Add -> relie `<>9__14_N` a l'effectType.
    pos = s
    while True:
        k = buf.find(bytes.fromhex("4889b1"), pos, e)
        if k < 0:
            break
        pos = k + 1
        off = struct.unpack_from("<I", buf, k + 3)[0]
        t = buf[k + 7:k + 7 + 24]
        if (t[0:3] == bytes.fromhex("4c8b0d") and t[7:10] == bytes.fromhex("4c8bc6")
                and t[10] == 0xBA and off % 8 == 0):
            by_effect[struct.unpack_from("<I", t, 11)[0]] = off // 8 - 1
    # (2) motif REDUIT : tous les Add, meme sans creation de delegate juste avant.
    pos = s
    while True:
        k = buf.find(bytes.fromhex("4c8bc6"), pos, e)
        if k < 0:
            break
        pos = k + 1
        if buf[k + 3] != 0xBA or buf[k + 8:k + 11] != bytes.fromhex("488bcf") or buf[k + 11] != 0xE8:
            continue
        rel = struct.unpack_from("<i", buf, k + 12)[0]
        tgt = start_va + (k - s) + 16 + rel
        targets[tgt] = targets.get(tgt, 0) + 1
        adds.append(struct.unpack_from("<I", buf, k + 4)[0])
    return by_effect, adds, targets


DYN_CTOR = "IdunBattle.Entities.Effects.DynamicStatModifierEffect$$.ctor"


def callees(buf, secs, rows, va, end_va) -> "list[str]":
    """Symboles appeles par le corps `[va, end_va)` -- la BORNE est la fonction SUIVANTE en memoire
    (sans elle, une fenetre fixe deborde sur la lambda voisine et on lit SES litteraux)."""
    by_addr = dict(rows)
    o, oe = va_to_off(secs, va), va_to_off(secs, end_va)
    body, out, k = buf[o:oe], [], 0
    while True:
        k = body.find(b"\xe8", k)
        if k < 0 or k + 5 > len(body):
            break
        rel = struct.unpack_from("<i", body, k + 1)[0]
        tgt = va + k + 5 + rel
        name = by_addr.get(tgt)
        if name and name not in out:
            out.append(name)
        k += 1
    return out


def lambda_args(buf, secs, va, end_va) -> dict:
    """Arguments du ctor `DynamicStatModifierEffect` lus AU DESASSEMBLAGE (cf. l'en-tete).
    Le corps est borne par la fonction SUIVANTE ; l'appelant a deja verifie que ce ctor est appele."""
    o, oe = va_to_off(secs, va), va_to_off(secs, end_va)
    body = buf[o:oe]
    out = {}
    k = 0
    while k >= 0 and "abilityType" not in out:
        k = body.find(b"\xba", k)                              # mov edx, imm32
        if k < 0:
            break
        if k + 10 <= len(body) and body[k + 5] == 0xE8:        # ... suivi de AbilityType$$op_Implicit
            out["abilityType"] = struct.unpack_from("<I", body, k + 1)[0]
        k += 1
    k = body.find(bytes.fromhex("41b8"))                       # mov r8d, imm32 = variableType
    if k >= 0:
        out["variableType"] = struct.unpack_from("<I", body, k + 2)[0]
    if body.find(bytes.fromhex("4533c9")) >= 0:                # xor r9d, r9d
        out["isNegative"] = 0
    else:
        for pat, width in ((bytes.fromhex("41b9"), 4), (bytes.fromhex("41b1"), 1)):
            k = body.find(pat)                                 # mov r9d, imm32 / mov r9b, imm8
            if k >= 0:
                out["isNegative"] = (struct.unpack_from("<I", body, k + 2)[0] if width == 4
                                     else body[k + 2])
                break
    k = body.find(bytes.fromhex("c64424"))                     # mov byte [rsp+disp8], imm8
    while k >= 0:                                              # le 5e argument passe en pile @+0x20
        if k + 5 <= len(body) and body[k + 3] == 0x20:
            out["canBeImmuneTo"] = body[k + 4]
            break
        k = body.find(bytes.fromhex("c64424"), k + 1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--effect", type=int, action="append", default=None,
                    help="EffectType a detailler (repetable) ; defaut 1581/1582/1583")
    a = ap.parse_args()
    probes = a.effect or [1581, 1582, 1583]

    bhash = build_hash()
    dll = dll_path(bhash)
    if not dll.exists():
        print("[358] ENTREE ABSENTE (non mesure, PAS un zero) : %s" % dll, file=sys.stderr)
        print("[358] le binaire du build %s n'est pas installe -- rien n'est conclu." % bhash,
              file=sys.stderr)
        return 2
    buf = dll.read_bytes()
    secs = sections(buf)
    rows = functions(bhash)
    start_va, end_va = span(rows, INIT_EFFECTS)
    by_effect, adds, targets = scan_registrations(buf, secs, start_va, end_va)
    lam = {name: addr for addr, name in rows if name.startswith(LAMBDA_PREFIX)}
    nxt = {addr: rows[i + 1][0] for i, (addr, _n) in enumerate(rows) if i + 1 < len(rows)}

    print("[358] build %s -- %s" % (bhash, INIT_EFFECTS))
    print("[358] Add(dict, effectType, delegate) : %d appels, %d effectType distincts, %d cible(s)"
          % (len(adds), len(set(adds)), len(targets)))
    print("[358] stores de delegate <>9__14_N  : %d, indices distincts %d"
          % (len(by_effect), len(set(by_effect.values()))))
    ok = (len(adds) == len(set(adds)) == len(by_effect) == len(set(by_effect.values()))
          and len(targets) == 1)
    print("[358] LOI off = 8*(N+1) : %s" % ("COHERENTE" if ok else "INCOHERENTE -- ne pas s'en servir"))
    print("[358] plage effectType enregistree : %d..%d" % (min(adds), max(adds)))
    rc = 0 if ok else 1
    for eff in probes:
        if eff not in by_effect:
            print("[358] effectType %d : NON ENREGISTRE (aucun Add) -> aucune classe d'effet native"
                  % eff)
            continue
        n = by_effect[eff]
        name = LAMBDA_PREFIX + str(n)
        va = lam.get(name)
        print("[358] effectType %d -> <>9__14_%d (statics+0x%x) -> %s"
              % (eff, n, 8 * (n + 1), name if va else "(lambda absente de functions.tsv)"))
        if not va:
            continue
        end = nxt.get(va)
        called = callees(buf, secs, rows, va, end)
        print("        fabrique -> %s" % (called or "(aucun appel nomme)"))
        if DYN_CTOR in called:
            print("        ctor DynamicStatModifierEffect (desassemblage) = %s"
                  % lambda_args(buf, secs, va, end))
        else:
            print("        (pas un DynamicStatModifierEffect -> pas de ConfigVar a lire ici)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
