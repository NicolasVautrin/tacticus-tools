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

  1. Le motif d'ENREGISTREMENT, repete pour chaque `EffectType` : un store du delegate au champ
     statique `<>9__14_N` (`mov [rcx+off], rsi`) juste avant `Add(dict, effectType, delegate)`.
     Les statiques de `<>c` etant `[<>9, <>9__14_0, <>9__14_1, ...]`, on a `off = 8 * (N + 1)` --
     c'est CE qui relie une lambda a son `EffectType`. La loi est VERIFIEE, pas supposee : tous les
     offsets multiples de 8, autant d'indices `N` distincts que d'enregistrements, aucun `EffectType`
     enregistre deux fois, et autant d'enregistrements que de fabriques `<>9__14_N` en binaire.
     ⚠ L'`Add` prend DEUX formes d'appel (cle dans `edx` / cle par adresse depuis un slot de pile),
     et ne reconnaitre que la premiere a coute 96 enregistrements invisibles -- cf.
     `scan_registrations` et `probe_364`.
  2. Le balayage EXHAUSTIF des `Add`, delegue a `probe_364.registry` (desassemblage complet, aucun
     motif d'octets supposee) -- c'est lui qui autorise a dire d'un `EffectType` qu'il n'est PAS
     enregistre.
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


def scan_registrations(buf, secs, rows=None):
    """Rend (`{effectType: N}`, nombre TOTAL d'appels d'ajout vus).

    CORRIGE PAR #364 -- l'ancien balayage etait INCOMPLET, et son incompletude etait invisible.

    Il cherchait deux motifs d'octets qui partageaient la meme cle `4c 8b c6` (`mov r8, rsi`) : ils
    n'etaient donc PAS independants, et l'accord parfait qu'ils affichaient (511 == 511) etait un
    accord sur la MEME cecite. Mesure du 2026-07-31 : `InitializeEffects` fait **607**
    enregistrements, pas 511. Les **96** manquants passent leur cle PAR ADRESSE (`lea rdx, [slot]` +
    `mov dword ptr [slot], imm32`, le dictionnaire gshared ayant une cle ValueType) et appellent
    `Dictionary<,>$$Add` DIRECTEMENT, sans passer par le thunk -- apres `mov r8, rsi` l'octet suivant
    est `C7` (`mov mem, imm32`) et non `BA` (`mov edx, imm32`).

    Consequence de l'ancien balayage : 96 `EffectType` etaient rendus « NON ENREGISTRE -> aucune
    classe d'effet native », dont `5 Fire`, `17 Ice`, `31 StatModifier`, `1004 MightOfHeroes_ExtraHits`,
    `1099 Waaagh_ExtraMovement`, `1244 Contaminated` -- tous parfaitement vivants. C'est exactement
    le faux negatif que le CLAUDE.md interdit de traiter comme une preuve de mort.

    La resolution vit desormais dans `probe_364.registry` (implementation UNIQUE de la loi) : deux
    transcriptions du meme desassemblage finiraient par diverger, et c'est cette divergence-la qu'on
    vient de payer."""
    if rows is None:
        rows = functions(build_hash())
    import probe_364_effect_1582_registration as p364
    by_effect, unresolved, total = p364.registry(buf, secs, rows)
    if unresolved:
        raise SystemExit(
            "[358] %d appel(s) d'ajout sur %d n'ont pas de cle resolue : l'inventaire est INCOMPLET, "
            "il ne peut pas servir a conclure qu'un EffectType est absent." % (unresolved, total))
    return by_effect, total


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
    by_effect, total = scan_registrations(buf, secs, rows)
    lam = {name: addr for addr, name in rows if name.startswith(LAMBDA_PREFIX)}
    nxt = {addr: rows[i + 1][0] for i, (addr, _n) in enumerate(rows) if i + 1 < len(rows)}

    print("[358] build %s -- %s" % (bhash, INIT_EFFECTS))
    print("[358] Add(dict, effectType, delegate) : %d appels, %d effectType distincts"
          % (total, len(by_effect)))
    print("[358] stores de delegate <>9__14_N  : %d, indices distincts %d"
          % (sum(1 for n in by_effect.values() if n is not None), len(set(by_effect.values()))))
    # La coherence se mesure sur la BIJECTION `appel d'ajout <-> effectType <-> N`, et sur la
    # FERMETURE contre une source INDEPENDANTE : le nombre de fabriques `<>9__14_N` presentes en
    # binaire. Comparer `len(adds)` a `len(set(adds))` ne prouverait plus rien depuis que la liste
    # derive du dictionnaire (egalite vraie par construction) ; c'est `total` -- le compte des
    # appels REELLEMENT vus -- qui doit egaler les deux autres.
    # L'ancien critere `len(targets) == 1` (une seule cible d'appel) est SUPPRIME : c'est
    # precisement lui qui masquait les 96 enregistrements de la seconde forme.
    ok = (total == len(by_effect) == len(set(by_effect.values())) == len(lam)
          and all(n is not None for n in by_effect.values()))
    print("[358] fabriques <>9__14_N en binaire : %d  (doit egaler les %d appels d'ajout)"
          % (len(lam), total))
    print("[358] LOI off = 8*(N+1) : %s" % ("COHERENTE" if ok else "INCOHERENTE -- ne pas s'en servir"))
    print("[358] plage effectType enregistree : %d..%d" % (min(by_effect), max(by_effect)))
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
