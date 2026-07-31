"""Probe #364 -- l'`EffectType` 1582 est-il enregistre dans `EffectsDatabase$$InitializeEffects` ?

LA QUESTION EST BINAIRE, et la reponse heritee de #358 etait un ZERO. Un zero ne vaut que si le
balayage qui l'a produit est EXHAUSTIF. Or les deux balayages de `probe_358` partageaient le meme
octet-cle `4c 8b c6` (`mov r8, rsi`) : ils n'etaient PAS independants -- un enregistrement qui
charge sa cle autrement echappait aux DEUX, et l'accord parfait qu'ils affichaient (511 == 511)
etait un accord sur la MEME cecite.

CE PROBE NE SUPPOSE AUCUN MOTIF DE REGISTRE. Il DESASSEMBLE (capstone) le corps de
`InitializeEffects` instruction par instruction et mesure, dans l'ordre :

  etape 1  Toutes les instructions `call <rel32>` du corps, groupees par cible RESOLUE. Rien n'est
           suppose sur la maniere dont les arguments sont charges. Il y a DEUX cibles d'ajout, pas
           une -- c'est le fait que #358 ne voyait pas.
  etape 2  Pour chaque `call Add`, la cle (2e argument = l'`EffectType`) obtenue par un mini suivi
           de flot LINEAIRE en arriere, dans les DEUX formes d'appel (cf. `key_before`).
  etape 3  Le test DIRECT : l'immediat 1582 apparait-il, sous n'importe quelle forme d'instruction
           (encodage 32 ET 16 bits), dans le corps de `InitializeEffects` ?
  etape 4  Fermeture de l'inventaire : les fabriques `<>c$$<InitializeEffects>b__14_N` presentes en
           binaire sont-elles TOUTES reliees a un `Add` ? C'est la source INDEPENDANTE qui rend le
           balayage falsifiable.
  etape 5  Qui, dans TOUT le segment de code, charge l'immediat ? -- la reponse a « qui le POSE ».
  etape 6  La COHORTE : quels membres de l'enum n'ont aucune fabrique, et lesquels d'entre eux sont
           malgre tout charges par du code du jeu. C'est le contexte de population qui empeche de
           lire l'absence de 1582 comme une singularite.

Chaque etape rend un chiffre ; aucune ne rend un booleen deduit d'une autre.

CE QUE LE NATIF FAIT D'UN `EffectType` SANS FABRIQUE -- lu dans
`IdunBattle.Core.Services.EffectsDatabase$$GetEffect` : le cache (`this+0x50`) rate, puis le
`TryGetValue` sur le dictionnaire de fabriques (`this+0x48`) rate a son tour ; le natif formate
alors `System.Enum$$ToString` de la cle dans un message de log, et construit un
`IdunBattle.Entities.Effects.NoneEffect`. Il n'y a donc NI crash NI exception : la degradation est
definie, silencieuse cote gameplay, visible seulement au log. « Sans fabrique » veut donc dire
« meme pose, il ne ferait rien » -- pas « impossible a poser ».

LIMITE ASSUMEE DU BALAYAGE D'IMMEDIAT (etapes 5 et 6) : un immediat n'est pas TYPE. `mov edx, 79`
peut etre un `EffectType.Cursed` comme n'importe quel autre entier, et les petites valeurs sont
partout. Le balayage n'est donc discriminant que pour les valeurs HAUTES et rares -- ce qu'est
1582. Il s'interprete par CONTRASTE (cf. etape 6), jamais comme un typage.

Usage :
    python probe_364_effect_1582_registration.py                 # les 6 etapes
    python probe_364_effect_1582_registration.py --effect 1582   # cible un autre EffectType
    python probe_364_effect_1582_registration.py --step 5        # une seule etape

ENTREE GITIGNOREE : `GameAssembly.dll` vit hors du depot (`%LOCALAPPDATA%/tacticus/games/<hash>/`).
Absent -> le probe le DIT et sort en erreur (rc 2), il ne rend jamais un zero silencieux. Le hash
est lu dans `data/symbols/CURRENT` (entree VERSIONNEE).
ASCII only (console cp1252). Lecture pure -- aucune ecriture.
"""
from __future__ import annotations

import argparse
import bisect
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
EFFECT_TYPE_ENUM = "IdunBattle.Entities.Enum.EffectType"


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


def enum_members(bhash: str) -> dict:
    """`IdunBattle.Entities.Enum.EffectType` depuis la table VERSIONNEE du build : `{valeur: nom}`.

    Foyer UNIQUE de cette lecture (le test de garde la consomme aussi) : deux transcriptions du
    meme TSV finiraient par diverger, et c'est exactement le genre de derive qui a renumerote
    1563/1564 sans que personne le voie (#318)."""
    p = ROOT / "data" / "symbols" / bhash / "frida" / "enums.tsv"
    with p.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[0] == EFFECT_TYPE_ENUM:
                out = {}
                for kv in parts[1].split(","):
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        try:
                            out[int(k)] = v
                        except ValueError:
                            pass
                return out
    raise SystemExit("%s absent de enums.tsv du build %s" % (EFFECT_TYPE_ENUM, bhash))


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


def code_section(secs, rows):
    """LA section executable, identifiee par CONFINEMENT de `InitializeEffects` -- jamais par nom."""
    anchor, _end = span(rows, INIT_EFFECTS)
    for sec in secs:
        vaddr, vsize, _raddr, rsize = sec
        if vaddr <= anchor - IMAGE_BASE < vaddr + max(vsize, rsize):
            return sec
    raise SystemExit("section de code introuvable")


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


def key_in_edx(insns, idx, window=64):
    """FORME A (511 sites) -- la cle est un immediat mis dans `edx` juste avant l'appel :

        mov qword ptr [rcx + 0x11f8], rsi     ; store du delegate au statique `<>9__14_574`
        mov r9, qword ptr [rip + ...]         ; MethodInfo* du gshared
        mov r8, rsi                           ; arg3 = le delegate
        mov edx, 0x62d                        ; arg2 = l'EffectType  (1581)
        mov rcx, rdi                          ; arg1 = le dictionnaire
        call <thunk> -> Dictionary<,>$$Add

    Rend `None` si la derniere ecriture d'`edx` n'est pas un immediat -- on ne devine pas."""
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
    """FORME B (96 sites) -- la cle est passee PAR ADRESSE, depuis un slot de pile :

        mov qword ptr [rcx + 0x20], rsi       ; store du delegate au statique `<>9__14_3`
        mov r9, qword ptr [rip + ...]
        lea rdx, [rsp + 0x28]                 ; arg2 = &slot
        mov r8, rsi                           ; arg3 = le delegate
        mov dword ptr [rsp + 0x28], 5         ; le LITTERAL, ecrit EN PILE  (5 = Fire)
        mov rcx, rdi
        call Dictionary<,>$$Add               ; appel DIRECT, sans thunk

    C'est la forme que le motif d'octets de #358 ne voyait pas : apres `mov r8, rsi` il attendait
    l'opcode `BA` (`mov edx, imm32`) et trouvait `C7` (`mov mem, imm32`). Le dictionnaire gshared a
    une cle ValueType, donc IL2CPP la passe par reference -- le litteral est bien la, simplement
    ailleurs. Les DEUX formes ont ete RELUES AU DESASSEMBLAGE, elles ne sont pas supposees."""
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
    """La cle du `Add` -- les DEUX formes, sans en privilegier aucune."""
    v = key_in_edx(insns, idx)
    return v if v is not None else key_by_stack_slot(insns, idx)


def add_sites(buf, secs, rows, tgts, by_addr):
    """Les cibles d'appel qui sont un `Add` de dictionnaire -- nommees OU atteintes par un thunk.

    C'est le coeur du probe : #358 n'en connaissait qu'UNE (celle que son motif atteignait). Il y en
    a DEUX -- l'appel DIRECT a `Dictionary<,>$$Add` et un thunk NON NOMME qui y mene. Ne retenir que
    la cible majoritaire redonnerait exactement le zero errone qu'on est venu verifier.

    Le thunk est identifie par sa STRUCTURE (son corps appelle un `...$$Add`), jamais par une VA en
    dur -- qui serait fausse au prochain build."""
    import capstone
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
            if ins.mnemonic == "call" and ins.operands \
                    and ins.operands[0].type == capstone.x86.X86_OP_IMM \
                    and by_addr.get(ins.operands[0].imm, "").endswith("$$Add"):
                out[va] = ("%s -> %s" % (name, by_addr[ins.operands[0].imm]), idxs)
                break
    return out


def imm_occurrences(insns, value, width=4):
    """Toutes les instructions du corps portant `value` comme operande immediat (32 ou 16 bits)."""
    import capstone
    mask = 0xFFFFFFFF if width == 4 else 0xFFFF
    hits = []
    for ins in insns:
        for op in ins.operands:
            if op.type == capstone.x86.X86_OP_IMM and (op.imm & mask) == (value & mask):
                hits.append(ins)
                break
    return hits


def delegate_index(insns, idx, window=16):
    """L'indice `N` du champ statique `<>9__14_N` ecrit juste avant l'`Add` (loi de #358).

    `off = 8 * (N + 1)`, les statiques de `<>c` etant `[<>9, <>9__14_0, ...]`. La loi vaut pour les
    DEUX formes d'enregistrement, et elle est FALSIFIABLE : l'etape 4 exige que les indices trouves
    soient distincts et couvrent exactement les fabriques presentes en binaire."""
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
    """LE RECENSEMENT COMPLET de `InitializeEffects` : `({effectType: N}, non_resolus, total)`.

    Implementation UNIQUE de la loi -- `probe_358` la consomme, le test de garde aussi : un seul
    endroit a corriger si un build change l'encodage. `total` est le nombre d'appels d'ajout VUS ;
    un appelant qui compare `len(by_effect)` a `total` detecte un ecrasement de cle, et un appelant
    qui lit `unresolved > 0` sait que son inventaire est incomplet AU LIEU de rendre un zero qui
    ressemble a une absence."""
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


def code_immediate_owners(buf, secs, rows, value, width=4) -> dict:
    """`{fonction proprietaire: [instruction, ...]}` -- QUI charge `value` comme immediat.

    Balayage du SEGMENT DE CODE entier. Chaque occurrence des octets est re-decodee en remontant
    jusqu'a 8 octets pour retrouver le debut d'instruction : un immediat n'est retenu que si une
    instruction VALIDE se termine exactement dessus.

    `width` = 4 (encodage `imm32`, le cas normal d'un enum int32) ou 2 (`imm16`, prefixe 0x66). Les
    DEUX sont balayes : ne verifier que l'un laisserait une porte ouverte.
    Rappel de la LIMITE (cf. en-tete) : un immediat n'est pas type."""
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    pat = struct.pack("<I", value) if width == 4 else struct.pack("<H", value & 0xFFFF)
    mask = 0xFFFFFFFF if width == 4 else 0xFFFF
    starts = [a for a, _n in rows]
    vaddr, _vsize, raddr, rsize = code_section(secs, rows)
    base = IMAGE_BASE + vaddr
    blob = buf[raddr:raddr + rsize]
    seen = {}
    k = blob.find(pat)
    while k >= 0:
        for back in range(1, 9):
            o = k - back
            if o < 0:
                break
            got = list(md.disasm(blob[o:o + 16], base + o, count=1))
            if not got or got[0].size != back + width:
                continue
            ins = got[0]
            if any(op.type == capstone.x86.X86_OP_IMM and (op.imm & mask) == (value & mask)
                   for op in ins.operands):
                j = bisect.bisect_right(starts, ins.address) - 1
                owner = rows[j][1] if j >= 0 else "(hors fonction nommee)"
                seen.setdefault(owner, []).append("%s %s" % (ins.mnemonic, ins.op_str))
                break
        k = blob.find(pat, k + 1)
    return seen


def data_occurrences(buf, secs, rows, value) -> int:
    """Combien de fois `value` apparait sur 4 octets HORS du segment de code.

    Pourquoi c'est mesure : un tableau d'`EffectType` initialise statiquement
    (`RuntimeHelpers.InitializeArray` depuis `.rdata`) serait une voie de pose SANS aucun immediat
    en code -- le seul chemin credible qui echapperait a l'etape 5.

    Comment ca se lit : ce compte ne vaut RIEN seul (1582 est un entier banal). Il ne s'interprete
    que par COMPARAISON avec les voisins VIVANTS 1581/1583, qui sont, eux, enregistres ET poses. Si
    les trois se ressemblent, ces octets sont de la METADONNEE IL2CPP -- mesure sur `rnca9r7q6c` :
    les hits voisins forment des triplets de 12 octets `(index, valeur, 0xFFFFFFFF)` ou 1581, 1582
    et 1583 figurent au MEME titre. La presence en donnees ne distingue donc rien. C'est un
    CONTROLE NEGATIF, pas une preuve."""
    code = code_section(secs, rows)
    pat = struct.pack("<I", value)
    total = 0
    for sec in secs:
        if sec == code or sec[3] == 0:
            continue
        _v, _vs, raddr, rsize = sec
        blob = buf[raddr:raddr + rsize]
        k = blob.find(pat)
        while k >= 0:
            total += 1
            k = blob.find(pat, k + 1)
    return total


def unregistered_members(by_effect, members) -> list:
    """Les membres de l'enum SANS fabrique, tries. La COHORTE de 1582."""
    return sorted(set(members) - set(by_effect))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--effect", type=int, default=1582, help="EffectType a trancher (defaut 1582)")
    ap.add_argument("--step", type=int, action="append", default=None,
                    help="n'executer que cette/ces etape(s) 1..6")
    a = ap.parse_args()
    steps = set(a.step) if a.step else {1, 2, 3, 4, 5, 6}
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
    members = enum_members(bhash)
    start_va, end_va = span(rows, INIT_EFFECTS)

    print("[364] build %s -- %s" % (bhash, INIT_EFFECTS))
    print("[364] cible : effectType %d = %s" % (target, members.get(target, "(hors enum)")))
    insns = disasm(buf, secs, start_va, end_va)
    print("[364] corps desassemble : %d octets, %d instructions"
          % (end_va - start_va, len(insns)))

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

    if steps & {2, 3, 4, 6}:
        for va, (_name, idxs) in adds.items():
            for i in idxs:
                v = key_before(insns, i)
                if v is None:
                    unknown += 1
                else:
                    registered.setdefault(v, []).append(i)
    if 2 in steps:
        print("\n[364][etape 2] EffectType passes a un Add, derives du FLOT (pas d'un motif)")
        print("        appels d'ajout                : %d" % sum(len(v[1]) for v in adds.values()))
        print("        cle immediate resolue         : %d" % sum(len(v) for v in registered.values()))
        print("        cle NON resolue (a expliquer) : %d" % unknown)
        if registered:
            print("        EffectType distincts          : %d (min %d, max %d)"
                  % (len(registered), min(registered), max(registered)))
        dupes = {k: len(v) for k, v in registered.items() if len(v) > 1}
        print("        EffectType enregistres 2x+    : %s" % (dupes or "aucun"))
        print("        cles hors enum EffectType     : %s"
              % (sorted(set(registered) - set(members)) or "aucune"))
        if unknown:
            rc = 1

    if 3 in steps:
        print("\n[364][etape 3] TEST DIRECT -- l'immediat %d (0x%x) dans le corps de InitializeEffects"
              % (target, target))
        for width in (4, 2):
            hits = imm_occurrences(insns, target, width=width)
            print("        encodage %d bits : %d occurrence(s)" % (width * 8, len(hits)))
            for ins in hits[:6]:
                print("        +0x%-6x %s %s" % (ins.address - start_va, ins.mnemonic, ins.op_str))
        neigh = [e for e in (target - 1, target + 1) if e in registered]
        print("        voisins immediats enregistres : %s" % (neigh or "aucun"))
        print("        VERDICT : %d est %s dans InitializeEffects"
              % (target, "ENREGISTRE" if target in registered
                 else "ABSENT (aucun Add, aucun immediat)"))

    if 4 in steps:
        print("\n[364][etape 4] FERMETURE -- fabriques <>c$$<InitializeEffects>b__14_N vs Add")
        lam = {}
        for addr, name in rows:
            if name.startswith(LAMBDA_PREFIX):
                try:
                    lam[int(name[len(LAMBDA_PREFIX):])] = addr
                except ValueError:
                    continue
        n_by_effect = {eff: delegate_index(insns, idxs[0]) for eff, idxs in registered.items()}
        used = {n for n in n_by_effect.values() if n is not None}
        print("        fabriques presentes dans functions.tsv : %d (N de %d a %d)"
              % (len(lam), min(lam), max(lam)))
        print("        N relies a un Add                      : %d" % len(used))
        print("        fabriques SANS Add                     : %d -> %s"
              % (len(set(lam) - used), sorted(set(lam) - used)[:20] or "aucune"))
        print("        Add sans indice N retrouve             : %d"
              % sum(1 for n in n_by_effect.values() if n is None))
        print("        => inventaire %s"
              % ("FERME (toute absence est opposable)" if len(lam) == len(used) == len(registered)
                 else "OUVERT -- aucune absence n'est opposable"))

    if 5 in steps:
        print("\n[364][etape 5] QUI charge l'immediat %d dans TOUT le segment de code" % target)
        for width in (4, 2):
            seen = code_immediate_owners(buf, secs, rows, target, width=width)
            game = {o: v for o, v in seen.items() if o.startswith("IdunBattle")}
            print("        %d bits : %d instruction(s) / %d fonction(s), dont IdunBattle : %d"
                  % (width * 8, sum(len(v) for v in seen.values()), len(seen), len(game)))
            for owner, lst in sorted(seen.items(), key=lambda kv: -len(kv[1]))[:5]:
                print("               %-4d x %-58s %s" % (len(lst), owner[:58], lst[0]))
            if not game:
                print("               AUCUNE fonction IdunBattle ne charge %d sur %d bits."
                      % (target, width * 8))
        print("        -- controle negatif en DONNEES (hors code), 4 octets --")
        for eff in (target - 1, target, target + 1):
            print("        %d %-46s : %d occurrence(s) hors code%s"
                  % (eff, members.get(eff, "(hors enum)"), data_occurrences(buf, secs, rows, eff),
                     "   <- ENREGISTRE, donc vivant" if eff in registered else ""))
        print("        (des comptes du meme ordre pour un enregistre et un non-enregistre = ces")
        print("         octets sont de la METADONNEE, pas une voie de pose -- cf. docstring)")

    if 6 in steps:
        print("\n[364][etape 6] COHORTE -- membres de l'enum SANS fabrique")
        orphans = unregistered_members(registered, members)
        print("        membres declares : %d | avec fabrique : %d | SANS : %d"
              % (len(members), len(registered), len(orphans)))
        for o in orphans:
            owners = code_immediate_owners(buf, secs, rows, o)
            game = sorted(k for k in owners if k.startswith("IdunBattle"))
            print("        %6d  %-46s  code IdunBattle : %-3d %s"
                  % (o, members[o][:46], len(game), "" if game else " <- AUCUN"))
        print("        (les petites valeurs sont BRUITEES -- un immediat n'est pas type ; ce")
        print("         tableau se lit par contraste sur les valeurs HAUTES et rares)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
