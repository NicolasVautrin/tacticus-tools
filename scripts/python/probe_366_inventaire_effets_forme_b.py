"""Probe #366 -- l'INVENTAIRE des `EffectType` que l'ancien balayage de #358 rendait « absents ».

LA QUESTION, EN DEUX TEMPS :
  1. Quels sont, NOMMEMENT, les `EffectType` que l'inventaire corrige (#382) fait apparaitre ?
  2. Parmi eux, lesquels sont VIVANTS et NON PORTES cote Python -- c'est-a-dire lesquels changent
     quelque chose si on les porte ?

RIEN N'EST RECOPIE : la liste est RE-DERIVEE du binaire a chaque execution. Le probe partitionne les
enregistrements de `IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects` selon la FORME
d'appel de leur cle, puis croise le resultat avec les registres du port.

LES DEUX FORMES (relues au desassemblage, cf. `probe_364.key_in_edx` / `key_by_stack_slot`) :

  FORME A -- `mov edx, <EffectType>` juste avant l'appel : la cle est un immediat dans `edx`.
  FORME B -- `lea rdx, [rsp+disp]` + `mov dword ptr [rsp+disp], <EffectType>` : le dictionnaire
             gshared a une cle ValueType, donc IL2CPP la passe PAR ADRESSE. Le litteral est bien
             la, simplement en pile.

L'ancien #358 cherchait des octets : la cle `4c 8b c6` (`mov r8, rsi`) SUIVIE de `BA`
(`mov edx, imm32`). Or `4c 8b c6` apparait 607 fois dans le corps -- une par enregistrement, les
DEUX formes confondues -- et seules 511 sont suivies de `BA`. Le motif voyait donc tous les sites
et en REJETAIT 96 sur le second octet. C'est reproduit tel quel par `legacy_blind_scan`, et c'est
ce qui rend la cecite MESURABLE au lieu d'etre racontee.

CE QUE LE PROBE MESURE (etapes independantes, chacune rend un chiffre) :

  etape 1  La partition A / B des enregistrements, et le total. Attendu : 511 + 96 = 607, disjoints.
  etape 2  Le balayage AVEUGLE reproduit (`legacy_blind_scan`) : il doit rendre EXACTEMENT la
           forme A, et etre un SOUS-ENSEMBLE STRICT du recensement complet.
  etape 3  Les 96 de la forme B, NOMMES depuis `data/symbols/<build>/frida/enums.tsv` -- jamais
           depuis le mirror Python (`EffectType` a eu 2 membres RENUMEROTES silencieusement, #318).
  etape 4  Ce que chaque fabrique CONSTRUIT, par IDENTITE DE CLASSE et non par nom de ctor : le
           slot `Il2CppClass*` charge dans `rcx` avant `il2cpp_object_new`. Deux lambdas qui
           construisent la meme classe chargent le MEME slot.
           ⚠ MESURE : 607 lambdas -> 440 slots distincts mais seulement 365 noms de ctor distincts,
           dont 51 couvrent PLUSIEURS slots. Le nom du ctor N'EST DONC PAS un nom de classe : IL2CPP
           deduplique les corps triviaux (cf. CLAUDE.md « L'ABSENCE d'une methode dans les tables ne
           prouve RIEN »). Le champion `...MV71SniperDroneSquad_ResetInitialDmgEffect$$.ctor` porte
           13 classes distinctes. Le probe le DIT au lieu de rendre un nom faux.
  etape 5  Le croisement avec le port : `EFFECT_CLASSES` (cle = NOM d'EffectType) et
           `EFFECT_TRIGGERS` (cle = id). Le nom capte cote live est le membre d'enum -- c'est bien
           la meme cle.

Usage :
    python probe_366_inventaire_effets_forme_b.py              # les 5 etapes
    python probe_366_inventaire_effets_forme_b.py --csv        # la table brute, une ligne par effet
    python probe_366_inventaire_effets_forme_b.py --step 4

ENTREE GITIGNOREE : `GameAssembly.dll` vit hors du depot (`%LOCALAPPDATA%/tacticus/games/<hash>/`).
Absent -> le probe le DIT et sort en erreur (rc 2) ; il ne rend JAMAIS un zero silencieux. Le hash
est lu dans `data/symbols/CURRENT` (entree VERSIONNEE).
ASCII only (console cp1252). Lecture pure -- aucune ecriture.
"""
from __future__ import annotations

import argparse
import struct
import sys
from collections import defaultdict
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_358_effects_database_registry as p358           # noqa: E402
import probe_364_effect_1582_registration as p364            # noqa: E402

#: `mov r8, rsi` -- l'octet-cle PARTAGE par les deux balayages de #358. Il marque les DEUX formes.
LEGACY_KEY = bytes.fromhex("4c8bc6")
#: `mov edx, imm32` -- le second octet, celui qui rejetait les 96 de la forme B.
LEGACY_EDX = 0xBA


def load(bhash=None):
    """(buf, sections, rows, membres d'enum) du build courant. Foyer unique du chargement."""
    bhash = bhash or p364.build_hash()
    dll = p364.dll_path(bhash)
    if not dll.exists():
        raise SystemExit(
            "[366] ENTREE ABSENTE (non mesure, PAS un zero) : %s\n"
            "[366] le binaire du build %s n'est pas installe -- rien n'est conclu." % (dll, bhash))
    buf = dll.read_bytes()
    secs = p364.sections(buf)
    rows = p364.functions(bhash)
    return bhash, buf, secs, rows, p364.enum_members(bhash)


def partition(buf, secs, rows):
    """({effectType: N} forme A, {effectType: N} forme B, non resolus, total appels d'ajout).

    Meme desassemblage que `probe_364.registry` -- mais il rend la FORME, que `registry` fond.
    On NE re-transcrit PAS la resolution de cle : `key_in_edx` / `key_by_stack_slot` restent le
    foyer unique (deux transcriptions du meme desassemblage finiraient par diverger, c'est
    exactement la divergence que #364 a payee)."""
    by_addr = dict(rows)
    start_va, end_va = p364.span(rows, p364.INIT_EFFECTS)
    insns = p364.disasm(buf, secs, start_va, end_va)
    adds = p364.add_sites(buf, secs, rows, p364.call_targets(insns), by_addr)
    a, b, unresolved, total = {}, {}, 0, 0
    for _va, (_name, idxs) in adds.items():
        for i in idxs:
            total += 1
            k = p364.key_in_edx(insns, i)
            if k is not None:
                a[k] = p364.delegate_index(insns, i)
                continue
            k = p364.key_by_stack_slot(insns, i)
            if k is None:
                unresolved += 1
                continue
            b[k] = p364.delegate_index(insns, i)
    return a, b, unresolved, total


def legacy_blind_scan(buf, secs, rows):
    """LE BALAYAGE AVEUGLE DE #358, reproduit a l'octet pres : `mov r8, rsi` SUIVI de `mov edx, imm32`.

    Rend `(cles vues, occurrences de l'octet-cle partage)`. La seconde valeur est ce qui rend la
    cecite lisible : l'octet-cle est present 607 fois -- une par enregistrement -- et le balayage
    n'en retient que 511. L'accord `511 == 511` des deux balayages de #358 etait un accord sur CE
    rejet, pas sur une mesure."""
    start_va, end_va = p364.span(rows, p364.INIT_EFFECTS)
    o, oe = p364.va_to_off(secs, start_va), p364.va_to_off(secs, end_va)
    body = buf[o:oe]
    keys, occ, k = {}, 0, body.find(LEGACY_KEY)
    while k >= 0:
        occ += 1
        if k + 8 <= len(body) and body[k + 3] == LEGACY_EDX:
            keys[struct.unpack_from("<I", body, k + 4)[0]] = k
        k = body.find(LEGACY_KEY, k + 1)
    return keys, occ


def _lambdas(rows):
    lam = {}
    for addr, name in rows:
        if name.startswith(p364.LAMBDA_PREFIX):
            try:
                lam[int(name[len(p364.LAMBDA_PREFIX):])] = addr
            except ValueError:
                continue
    return lam


def factory_class_slots(buf, secs, rows, indices):
    """`{N: (slot Il2CppClass*, nom du ctor appele)}` pour chaque fabrique `<>9__14_N`.

    IDENTITE DE CLASSE = le slot charge dans `rcx` avant le premier `call` du corps (l'allocation
    `il2cpp_object_new`). C'est une donnee de METADONNEE, pas un nom : deux lambdas qui construisent
    la meme classe chargent le meme slot, et deux classes distinctes ne peuvent pas le partager.
    Le nom du ctor est rendu A COTE, pour pouvoir CONSTATER qu'il ne suffit pas (etape 4)."""
    import capstone
    by_addr = dict(rows)
    lam = _lambdas(rows)
    nxt = {addr: rows[i + 1][0] for i, (addr, _n) in enumerate(rows) if i + 1 < len(rows)}
    out = {}
    for n in indices:
        va = lam.get(n)
        if va is None:
            continue
        slot, ctor, pending = None, None, None
        for ins in p364.disasm(buf, secs, va, nxt.get(va, va + 0x200)):
            ops = ins.operands
            if ins.mnemonic == "mov" and len(ops) == 2 \
                    and ops[0].type == capstone.x86.X86_OP_REG \
                    and ins.reg_name(ops[0].reg) == "rcx" \
                    and ops[1].type == capstone.x86.X86_OP_MEM \
                    and ins.reg_name(ops[1].mem.base or 0) == "rip":
                pending = ins.address + ins.size + ops[1].mem.disp
            if ins.mnemonic == "call" and ops and ops[0].type == capstone.x86.X86_OP_IMM:
                if slot is None and pending is not None:
                    slot = pending
                nm = by_addr.get(ops[0].imm, "")
                if ctor is None and nm.endswith("$$.ctor"):
                    ctor = nm
        out[n] = (slot, ctor)
    return out


def port_status():
    """(`EFFECT_CLASSES`, `EFFECT_TRIGGERS`) du port -- les registres REELS, pas une transcription."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    return EFFECT_CLASSES, EFFECT_TRIGGERS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, action="append", default=None, help="etape(s) 1..5")
    ap.add_argument("--csv", action="store_true",
                    help="table brute des 96 (id;nom;slot;ctor;EFFECT_CLASSES;EFFECT_TRIGGERS)")
    a = ap.parse_args()
    steps = set(a.step) if a.step else {1, 2, 3, 4, 5}

    bhash, buf, secs, rows, members = load()
    formA, formB, unresolved, total = partition(buf, secs, rows)
    lam = _lambdas(rows)
    classes, triggers = port_status()

    print("[366] build %s -- %s" % (bhash, p364.INIT_EFFECTS))

    if 1 in steps:
        print("\n[366][etape 1] PARTITION des enregistrements par forme d'appel de la cle")
        print("        forme A (mov edx, imm32)          : %d" % len(formA))
        print("        forme B (cle PAR ADRESSE, pile)   : %d" % len(formB))
        print("        cle NON resolue                   : %d" % unresolved)
        print("        intersection A/B                  : %d" % len(set(formA) & set(formB)))
        print("        total appels d'ajout vus          : %d" % total)
        print("        fabriques <>9__14_N en binaire    : %d  (source INDEPENDANTE)" % len(lam))

    if 2 in steps:
        keys, occ = legacy_blind_scan(buf, secs, rows)
        print("\n[366][etape 2] le balayage AVEUGLE de #358, reproduit a l'octet pres")
        print("        occurrences de l'octet-cle partage `mov r8, rsi` : %d" % occ)
        print("        retenues (suivies de `mov edx, imm32`)           : %d" % len(keys))
        print("        rejetees sur le SECOND octet                     : %d" % (occ - len(keys)))
        print("        legacy == forme A                               : %s"
              % (set(keys) == set(formA)))
        print("        legacy STRICTEMENT inclus dans A+B              : %s"
              % (set(keys) < (set(formA) | set(formB))))

    if 3 in steps:
        print("\n[366][etape 3] les %d `EffectType` de la forme B, NOMMES depuis enums.tsv"
              % len(formB))
        hors = sorted(set(formB) - set(members))
        print("        hors enum EffectType : %s" % (hors or "aucun"))
        for eff in sorted(formB):
            print("        %6d  %s" % (eff, members.get(eff, "(HORS ENUM)")))

    slots = factory_class_slots(buf, secs, rows, sorted(set(formA.values()) | set(formB.values())))
    if 4 in steps:
        byslot, byctor = defaultdict(list), defaultdict(set)
        for n, (slot, ctor) in slots.items():
            byslot[slot].append(n)
            byctor[ctor].add(slot)
        amb = {c: s for c, s in byctor.items() if len(s) > 1}
        print("\n[366][etape 4] IDENTITE DE CLASSE des fabriques -- par slot Il2CppClass*")
        print("        fabriques profilees        : %d" % len(slots))
        print("        slots Il2CppClass* distincts : %d" % len(byslot))
        print("        noms de ctor distincts       : %d" % len(byctor))
        print("        ctors couvrant PLUSIEURS slots (nom NON fiable) : %d" % len(amb))
        for c, s in sorted(amb.items(), key=lambda kv: -len(kv[1]))[:5]:
            print("           %-72s %d classes" % (str(c)[:72], len(s)))

    if 5 in steps:
        porte_nom = [e for e in sorted(formB) if members.get(e) in classes]
        porte_id = [e for e in sorted(formB) if e in triggers]
        couvert = sorted(set(porte_nom) | set(porte_id))
        print("\n[366][etape 5] croisement avec le PORT (registres reels, pas une transcription)")
        print("        EFFECT_CLASSES (par NOM)   : %d entrees" % len(classes))
        print("        EFFECT_TRIGGERS (par id)   : %d entrees" % len(triggers))
        print("        parmi les %d de la forme B : %d avec classe d'effet, %d avec trigger, "
              "%d couverts au total" % (len(formB), len(porte_nom), len(porte_id), len(couvert)))
        print("        NON couverts par le port   : %d" % (len(formB) - len(couvert)))

    if a.csv:
        print("\nid;nom;slot;ctor;EFFECT_CLASSES;EFFECT_TRIGGERS")
        for eff in sorted(formB):
            n = formB[eff]
            slot, ctor = slots.get(n, (None, None))
            nm = members.get(eff, "(HORS ENUM)")
            print("%d;%s;0x%x;%s;%s;%s" % (eff, nm, slot or 0, ctor,
                                           "OUI" if nm in classes else "-",
                                           "OUI" if eff in triggers else "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
