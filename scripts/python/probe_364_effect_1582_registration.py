"""Probe #364 -- l'`EffectType` 1582 est-il enregistre dans `EffectsDatabase$$InitializeEffects` ?

LA QUESTION EST BINAIRE, et la reponse heritee de #358 est un ZERO. Un zero ne vaut que si le
balayage qui l'a produit est EXHAUSTIF. Or les deux balayages de `probe_358` partagent le meme
octet-cle `4c 8b c6` (`mov r8, rsi`) : ils ne sont PAS independants -- un enregistrement qui
chargerait le delegate autrement echapperait aux DEUX, et l'accord parfait qu'ils affichent
(511 == 511) serait un accord sur la meme cecite.

CE PROBE NE SUPPOSE AUCUN MOTIF DE REGISTRE. Il DESASSEMBLE (capstone) le corps de
`InitializeEffects` instruction par instruction et mesure, dans l'ordre :

  etape 1  Toutes les instructions `call <rel32>` du corps, groupees par cible RESOLUE. Le
           `Add` du dictionnaire est la cible majoritaire ; on n'a rien suppose sur la maniere
           dont ses arguments sont charges.
  etape 2  Pour chaque `call Add`, la valeur de `edx` (2e argument = l'`EffectType`) obtenue par
           un mini suivi de flot LINEAIRE en arriere : le dernier `mov edx, imm32` / `xor edx,edx`
           qui precede l'appel. C'est la LISTE des effectType enregistres, derivee des appels et
           non d'un motif.
  etape 3  Le test DIRECT et sans intermediaire : l'immediat 1582 (0x62e) apparait-il, sous
           n'importe quelle forme d'instruction, dans le corps de `InitializeEffects` ? Si un
           enregistrement existait -- quel que soit son encodage -- l'immediat y serait.
  etape 4  Inventaire des lambdas `<>c$$<InitializeEffects>b__14_N` : combien, quel N maximum,
           quels indices ne sont relies a AUCUN `Add`. Les 511 enregistrements pour un N max de
           574 impliquent des trous ; ce sont eux qu'il faut expliquer avant de conclure.
  etape 5  Qui, dans TOUT le binaire, charge l'immediat 1582 ? (fonctions nommees, via les
           bornes de `functions.tsv`). C'est la reponse a « qui le POSE ».

Chaque etape rend un chiffre ; aucune ne rend un booleen deduit d'une autre.

Usage :
    python probe_364_effect_1582_registration.py                 # les 5 etapes
    python probe_364_effect_1582_registration.py --effect 1582   # cible un autre EffectType
    python probe_364_effect_1582_registration.py --step 5        # une seule etape

ENTREE GITIGNOREE : `GameAssembly.dll` vit hors du depot (`%LOCALAPPDATA%/tacticus/games/<hash>/`).
Absent -> le probe le DIT et sort en erreur (rc 2), il ne rend jamais un zero silencieux. Le hash
est lu dans `data/symbols/CURRENT` (entree VERSIONNEE).
ASCII only (console cp1252). Lecture pure -- aucune ecriture.
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

INIT_EFFECTS = "IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects"
LAMBDA_PREFIX = ("IdunBattle.Core.Services.EffectsDatabase."
                 "u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_")


def build_hash() -> str:
    return (ROOT / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()


def dll_path(bhash: str) -> Path:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "tacticus" / "games" / bhash / "GameAssembly.dll"


def functions(bhash: str):
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


def span(rows, symbol):
    for i, (addr, name) in enumerate(rows):
        if name == symbol:
            return addr, (rows[i + 1][0] if i + 1 < len(rows) else addr + 0x40000)
    raise SystemExit("symbole absent de functions.tsv: %s" % symbol)


def sections(buf):
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


def va_to_off(secs, va):
    rva = va - IMAGE_BASE
    for vaddr, vsize, raddr, rsize in secs:
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raddr + (rva - vaddr)
    return None


def disasm(buf, secs, start_va, end_va):
    """Desassemblage LINEAIRE du corps [start_va, end_va). Rend la liste des instructions."""
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    o, oe = va_to_off(secs, start_va), va_to_off(secs, end_va)
    return list(md.disasm(buf[o:oe], start_va))


def call_targets(insns):
    """{cible resolue: [index d'instruction]} pour les `call <imm>` (rel32 deja resolu)."""
    import capstone
    out = {}
    for i, ins in enumerate(insns):
        if ins.mnemonic != "call" or len(ins.operands) != 1:
            continue
        op = ins.operands[0]
        if op.type == capstone.x86.X86_OP_IMM:
            out.setdefault(op.imm, []).append(i)
    return out


def edx_before(insns, idx, window=64):
    """Derniere valeur ecrite dans edx/rdx avant l'instruction `idx` (suivi LINEAIRE en arriere).

    Rend `None` si la derniere ecriture n'est pas un immediat -- on ne devine pas."""
    import capstone
    for j in range(idx - 1, max(-1, idx - window) - 1, -1):
        ins = insns[j]
        ops = ins.operands
        if ins.mnemonic == "call":                       # ne pas franchir un autre appel
            return None
        if not ops or ops[0].type != capstone.x86.X86_OP_REG:
            continue
        reg = ins.reg_name(ops[0].reg)
        if reg not in ("edx", "rdx", "dx", "dl"):
            continue
        if ins.mnemonic == "mov" and len(ops) == 2 and ops[1].type == capstone.x86.X86_OP_IMM:
            return ops[1].imm & 0xFFFFFFFF
        if ins.mnemonic == "xor" and len(ops) == 2 and ops[1].type == capstone.x86.X86_OP_REG \
                and ins.reg_name(ops[1].reg) == reg:
            return 0
        return None                                       # ecriture non-immediate -> inconnue
    return None


def key_by_stack_slot(insns, idx, window=26):
    """Cle passee PAR ADRESSE : `lea rdx, [slot]` + `mov dword ptr [slot], imm32`.

    C'est la SECONDE forme d'enregistrement, celle des 96 appels directs a `Dictionary<,>$$Add`
    que le motif de #358 ne voyait pas : le dictionnaire gshared a une cle ValueType, donc IL2CPP
    la passe par reference depuis un slot de pile au lieu de la mettre dans `edx`. Le litteral est
    bien la -- il est simplement ECRIT EN PILE avant l'appel."""
    import capstone
    slot = None
    for j in range(idx - 1, max(-1, idx - window) - 1, -1):
        ins = insns[j]
        if ins.mnemonic == "lea" and len(ins.operands) == 2 \
                and ins.operands[0].type == capstone.x86.X86_OP_REG \
                and ins.reg_name(ins.operands[0].reg) == "rdx" \
                and ins.operands[1].type == capstone.x86.X86_OP_MEM:
            m = ins.operands[1].mem
            slot = (m.base, m.disp)
            break
    if slot is None:
        return None
    for j in range(idx - 1, max(-1, idx - window) - 1, -1):
        ins = insns[j]
        if ins.mnemonic != "mov" or len(ins.operands) != 2:
            continue
        d, s = ins.operands
        if d.type == capstone.x86.X86_OP_MEM and s.type == capstone.x86.X86_OP_IMM \
                and (d.mem.base, d.mem.disp) == slot:
            return s.imm & 0xFFFFFFFF
    return None


def key_before(insns, idx):
    """La cle du `Add` -- les DEUX formes d'enregistrement, sans en privilegier aucune."""
    v = edx_before(insns, idx)
    return v if v is not None else key_by_stack_slot(insns, idx)


def add_sites(buf, secs, rows, tgts, by_addr):
    """Les cibles d'appel qui sont un `Add` de dictionnaire -- nommees OU atteintes par un thunk.

    ATTENTION, c'est le coeur du probe : #358 n'en connaissait qu'UNE (celle que son motif
    `mov r8, rsi` atteignait). Il y en a DEUX -- l'appel DIRECT a `Dictionary<,>$$Add` et un
    helper NON NOMME qui y mene. Ne retenir que la cible majoritaire redonnerait exactement le
    zero errone qu'on est venu verifier.

    Le helper est identifie par sa STRUCTURE (son corps appelle un `...$$Add`), jamais par une VA
    en dur -- qui serait fausse au prochain build."""
    by_start = {a: i for i, (a, _n) in enumerate(rows)}
    out = {}
    for va, idxs in tgts.items():
        name = by_addr.get(va, "")
        if name.endswith("$$Add"):
            out[va] = (name, idxs)
            continue
        if not name.startswith("FUN_") or va not in by_start:
            continue
        i = by_start[va]
        end = rows[i + 1][0] if i + 1 < len(rows) else va + 0x200
        if end - va > 0x400:                      # un thunk est court ; au-dela on ne devine pas
            continue
        for ins in disasm(buf, secs, va, end):
            if ins.mnemonic == "call" and ins.operands and \
                    ins.operands[0].type == 2 and by_addr.get(ins.operands[0].imm, "").endswith("$$Add"):
                out[va] = ("%s -> %s" % (name, by_addr[ins.operands[0].imm]), idxs)
                break
    return out


def imm_occurrences(insns, value):
    """Toutes les instructions du corps portant `value` comme operande immediat."""
    import capstone
    hits = []
    for ins in insns:
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_IMM and (op.imm & 0xFFFFFFFF) == value:
                hits.append(ins)
                break
    return hits


def delegate_index(insns, idx, window=16):
    """L'indice `N` du champ statique `<>9__14_N` ecrit juste avant l'`Add` (loi de #358).

    `off = 8 * (N + 1)`, les statiques de `<>c` etant `[<>9, <>9__14_0, ...]`. La loi vaut pour les
    DEUX formes d'enregistrement -- c'est mesure, pas suppose (cf. etape 4)."""
    import capstone
    for j in range(idx - 1, max(-1, idx - window) - 1, -1):
        ins = insns[j]
        if ins.mnemonic != "mov" or len(ins.operands) != 2:
            continue
        d, s = ins.operands
        if d.type == capstone.x86.X86_OP_MEM and s.type == capstone.x86.X86_OP_REG \
                and d.mem.disp and d.mem.disp % 8 == 0:
            return d.mem.disp // 8 - 1
    return None


def registry(buf, secs, rows):
    """LE RECENSEMENT COMPLET de `InitializeEffects` : `{effectType: N}`, les DEUX formes.

    C'est l'API que `probe_358` consomme : elle existe pour qu'il n'y ait qu'UNE implementation de
    la loi, donc qu'un seul endroit a corriger si un build change l'encodage. Rend aussi le nombre
    d'appels d'ajout NON resolus -- un appelant qui lit `unresolved > 0` sait que son inventaire
    est incomplet AU LIEU de rendre un zero qui ressemble a une absence."""
    by_addr = dict(rows)
    start_va, end_va = span(rows, INIT_EFFECTS)
    insns = disasm(buf, secs, start_va, end_va)
    adds = add_sites(buf, secs, rows, call_targets(insns), by_addr)
    by_effect, unresolved, total = {}, 0, 0
    for _va, (_name, idxs) in adds.items():
        for i in idxs:
            total += 1
            v = key_before(insns, i)
            if v is None:
                unresolved += 1
                continue
            by_effect[v] = delegate_index(insns, i)
    return by_effect, unresolved, total


def code_immediate_owners(buf, secs, rows, value) -> dict:
    """`{fonction proprietaire: [instruction, ...]}` -- QUI charge `value` comme immediat.

    Balayage du SEGMENT DE CODE entier (la section qui porte `InitializeEffects`, identifiee par
    confinement, jamais par un nom en dur). Chaque occurrence des 4 octets est re-decodee en
    remontant jusqu'a 8 octets pour retrouver le debut d'instruction : un immediat n'est retenu que
    si une instruction VALIDE se termine exactement dessus."""
    import bisect
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    pat = struct.pack("<I", value)
    starts = [a for a, _n in rows]
    anchor, _end = span(rows, INIT_EFFECTS)
    code = [(v, vs, r, rs) for (v, vs, r, rs) in secs
            if v <= anchor - IMAGE_BASE < v + max(vs, rs)]
    seen = {}
    for vaddr, _vsize, raddr, rsize in code:
        base = IMAGE_BASE + vaddr
        blob = buf[raddr:raddr + rsize]
        k = blob.find(pat)
        while k >= 0:
            for back in range(1, 9):
                o = k - back
                if o < 0:
                    break
                got = list(md.disasm(blob[o:o + 16], base + o, count=1))
                if not got or got[0].size != back + 4:
                    continue
                ins = got[0]
                if any(op.type == capstone.x86.X86_OP_IMM
                       and (op.imm & 0xFFFFFFFF) == value for op in ins.operands):
                    j = bisect.bisect_right(starts, ins.address) - 1
                    owner = rows[j][1] if j >= 0 else "(hors fonction nommee)"
                    seen.setdefault(owner, []).append("%s %s" % (ins.mnemonic, ins.op_str))
                    break
            k = blob.find(pat, k + 1)
    return seen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--effect", type=int, default=1582, help="EffectType a trancher (defaut 1582)")
    ap.add_argument("--step", type=int, action="append", default=None,
                    help="n'executer que cette/ces etape(s) 1..5")
    a = ap.parse_args()
    steps = set(a.step) if a.step else {1, 2, 3, 4, 5}
    target = a.effect

    bhash = build_hash()
    dll = dll_path(bhash)
    if not dll.exists():
        print("[364] ENTREE ABSENTE (non mesure, PAS un zero) : %s" % dll, file=sys.stderr)
        print("[364] le binaire du build %s n'est pas installe -- rien n'est conclu." % bhash,
              file=sys.stderr)
        return 2
    buf = dll.read_bytes()
    secs = sections(buf)
    rows = functions(bhash)
    by_addr = dict(rows)
    start_va, end_va = span(rows, INIT_EFFECTS)

    print("[364] build %s -- %s" % (bhash, INIT_EFFECTS))
    print("[364] corps desassemble : %d octets" % (end_va - start_va))
    insns = disasm(buf, secs, start_va, end_va)
    print("[364] instructions decodees : %d (derniere a +0x%x, fin du corps a +0x%x)"
          % (len(insns), insns[-1].address - start_va, end_va - start_va))

    tgts = call_targets(insns)
    adds = add_sites(buf, secs, rows, tgts, by_addr)
    rc = 0
    registered = {}
    unknown = 0

    if 1 in steps:
        print("\n[364][etape 1] cibles d'appel du corps (sans supposer AUCUN motif de registre)")
        for va, idxs in sorted(tgts.items(), key=lambda kv: -len(kv[1]))[:6]:
            print("        %-6d appel(s) -> %s" % (len(idxs), by_addr.get(va, "(non nomme)")))
        print("        SITES D'AJOUT retenus (nom en $$Add, ou thunk qui y mene) : %d" % len(adds))
        for va, (name, idxs) in sorted(adds.items(), key=lambda kv: -len(kv[1][1])):
            print("        %-6d appel(s) -> %s" % (len(idxs), name))
        print("        TOTAL appels d'ajout : %d   (#358 n'en comptait que 511)"
              % sum(len(v[1]) for v in adds.values()))

    if steps & {2, 3, 4}:
        for va, (_name, idxs) in adds.items():
            for i in idxs:
                v = key_before(insns, i)
                if v is None:
                    unknown += 1
                else:
                    registered.setdefault(v, []).append(i)
    if 2 in steps:
        print("\n[364][etape 2] EffectType passes a un Add, derives du FLOT (pas d'un motif)")
        print("        appels d'ajout               : %d" % sum(len(v[1]) for v in adds.values()))
        print("        edx immediat resolu          : %d" % sum(len(v) for v in registered.values()))
        print("        edx NON resolu (a expliquer) : %d" % unknown)
        if registered:
            print("        EffectType distincts         : %d (min %d, max %d)"
                  % (len(registered), min(registered), max(registered)))
        dupes = {k: len(v) for k, v in registered.items() if len(v) > 1}
        print("        EffectType enregistres 2x+   : %s" % (dupes or "aucun"))
        if unknown:
            rc = 1

    if 3 in steps:
        print("\n[364][etape 3] TEST DIRECT -- l'immediat %d (0x%x) dans le corps de InitializeEffects"
              % (target, target))
        hits = imm_occurrences(insns, target)
        print("        occurrences : %d" % len(hits))
        for ins in hits[:10]:
            print("        +0x%-6x %s %s" % (ins.address - start_va, ins.mnemonic, ins.op_str))
        neigh = [e for e in (target - 1, target + 1) if e in registered]
        print("        voisins enregistres : %s" % (neigh or "aucun"))
        print("        VERDICT : %d est %s dans InitializeEffects"
              % (target, "ENREGISTRE" if target in registered else "ABSENT (aucun Add, aucun immediat)"))

    if 4 in steps:
        print("\n[364][etape 4] lambdas <>c$$<InitializeEffects>b__14_N vs enregistrements")
        lam = {}
        for addr, name in rows:
            if name.startswith(LAMBDA_PREFIX):
                try:
                    lam[int(name[len(LAMBDA_PREFIX):])] = addr
                except ValueError:
                    continue
        print("        lambdas presentes dans functions.tsv : %d (N de %d a %d)"
              % (len(lam), min(lam), max(lam)))
        # relier chaque Add a l'index N via le store `mov [rcx+off], rsi` qui le precede
        import capstone
        n_by_effect = {}
        for eff, idxs in registered.items():
            i = idxs[0]
            for j in range(i - 1, max(-1, i - 16) - 1, -1):
                ins = insns[j]
                if ins.mnemonic != "mov" or len(ins.operands) != 2:
                    continue
                d, s = ins.operands
                if d.type == capstone.x86.X86_OP_MEM and s.type == capstone.x86.X86_OP_REG \
                        and d.mem.disp and d.mem.disp % 8 == 0:
                    n_by_effect[eff] = d.mem.disp // 8 - 1
                    break
        used = set(n_by_effect.values())
        missing = sorted(set(lam) - used)
        print("        N relies a un Add                    : %d" % len(used))
        print("        N presents en binaire SANS Add       : %d -> %s"
              % (len(missing), missing[:20] if missing else "aucun"))
        holes = sorted(set(range(min(lam), max(lam) + 1)) - set(lam))
        print("        N absents de functions.tsv (trous)   : %d -> %s"
              % (len(holes), holes[:20] if holes else "aucun"))
        print("        (rappel CLAUDE.md : un trou de TABLE ne prouve rien -- corps dedupliques)")

    if 5 in steps:
        print("\n[364][etape 5] QUI charge l'immediat %d dans TOUT le segment de code" % target)
        seen = code_immediate_owners(buf, secs, rows, target)
        print("        instructions trouvees : %d, dans %d fonction(s)"
              % (sum(len(v) for v in seen.values()), len(seen)))
        if not seen:
            print("        AUCUNE instruction du segment de code ne charge %d." % target)
            print("        -> l'EffectType %d n'est POSE par aucun code natif : il est INERTE."
                  % target)
        for owner, lst in sorted(seen.items(), key=lambda kv: -len(kv[1])):
            print("        %-4d x %s" % (len(lst), owner))
            for txt in lst[:3]:
                print("               %s" % txt)
    return rc


if __name__ == "__main__":
    sys.exit(main())
