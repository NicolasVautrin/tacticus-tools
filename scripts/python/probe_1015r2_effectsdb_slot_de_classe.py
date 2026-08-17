"""Probe #1015-r2 -- QUELLE CLASSE D'EFFET sert chaque `EffectType` : le SLOT `Il2CppClass*`.

POURQUOI CE PROBE EXISTE ALORS QUE #10018 LIT DEJA LA TABLE.
`probe_10018_effectsdatabase_registry.py` etablit l'appariement `b__14_N -> EffectType` (la N-ieme
cle inscrite par `IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects`). Il DIT lui-meme
ce qu'il ne fait pas : << les `.ctor` triviaux sont dedupliques par ICF, donc le SYMBOLE du ctor
ne nomme PAS toujours la classe construite [...] Ce qui identifie la classe est le slot
`Il2CppClass*` charge juste avant, pas le nom du ctor. >> Ce probe-ci LIT ce slot.

Sans lui, une question comme #1015-r2 (<< quels `EffectType` sont servis par une classe qui ecrit
`MovementComponent+0x50` ? >>) n'a que le NOM pour repondre -- exactement le vice de
`docs/rl/case-270r1-volet2-cles-ambigues.md`. Et le cout de l'erreur est reel : la famille
`Taunted` compte QUATRE effets servis par QUATRE classes distinctes
(`27 -> TauntedEffect`, `26 -> BlockActiveAbilityEffect`, `1237 ->
Taunted_RefreshUnitTurnFinishedEffect`, `25 -> <slot 3 effets>`), donc << meme prefixe de nom >>
ne dit rien.

CE QUI EST LU, ET COMMENT.
Chaque lambda `EffectsDatabase.<>c$$<InitializeEffects>b__14_N` a le corps :

    obj = il2cpp_codegen_object_new(<slot Il2CppClass*>)      # `mov rcx, [rip + X]` puis call
    <Classe>..ctor(obj, ...)                                   # appel DIRECT, corps ICF possible
    return obj

Le probe desassemble CHAQUE lambda (bornes derivees par SYMBOLE dans `ghidra/functions.tsv`,
aucune VA en dur), releve le slot et l'adresse du ctor, et GROUPE par slot : deux `EffectType` qui
portent le meme slot sont servis par la MEME classe. Un groupe est NOMMABLE quand son symbole de
ctor n'est porte par AUCUN autre groupe (le ctor n'est alors pas un corps ICF partage).

DEUXIEME VOIE D'INDEXATION, ET C'EST LE CONTROLE.
`#10018` indexe par le FLUX (n-ieme cle <-> n-ieme delegue). Ce probe indexe par l'OFFSET du champ
statique de cache du delegue (`<>c.<>9__14_N`, lu dans `mov rsi, [rax + off]` / `mov [rcx + off],
rsi`), qui croit de 8 en 8 dans l'ordre de declaration des lambdas. Les deux voies sont
INDEPENDANTES et doivent rendre le meme appariement, sinon le probe REFUSE DE CONCLURE.

Usage (offline, aucun runner, aucune session Frida) :
    python probe_1015r2_effectsdb_slot_de_classe.py
    python probe_1015r2_effectsdb_slot_de_classe.py --effet 25 --effet 91 --effet 1016 --effet 1235
    python probe_1015r2_effectsdb_slot_de_classe.py --tsv ../../logs/effectsdb_classes.tsv

Codes de retour : 0 = tout tient ; 1 = un controle est tombe ; 99 = NON MESURE (le binaire du
build n'est pas sur cette machine -- tri-etat, jamais un zero deguise).

ASCII only (cp1252).
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, OrderedDict
from pathlib import Path

import probe_10018_effectsdatabase_registry as P10018

#: Les QUATRE `EffectType` dont le nom porte `_BlockMovement` -- ce probe ne s'en sert PAS pour
#: conclure (ce serait l'inference qu'il combat), seulement pour l'affichage cible.
CIBLES_1015R2 = (25, 91, 1016, 1235)

#: CONTRE-EPREUVE. `1235 InstinctiveBehaviour_BlockMovement` est le SEUL des quatre dont
#: l'appariement `EffectType -> classe` etait etabli AVANT ce probe, et par une voie totalement
#: independante : `InstinctiveBehaviour_InitAbility$$GetEffectType` a pour corps entier
#: `return 0x4d3`, et `IdunBattle.Entities.Effects.Loki.InstinctiveBehaviourBlockMovementEffect`
#: est l'unique sous-classe de `BlockUnitMovementEffect` du build (`frida/classes.tsv`). Si la
#: methode de ce probe est juste, elle doit RETROUVER cet appariement. Si elle ne le retrouve pas,
#: elle est fausse -- et le probe le dit au lieu de conclure.
CONTRE_EPREUVE = (
    1235,
    "IdunBattle.Entities.Effects.Loki.InstinctiveBehaviourBlockMovementEffect$$.ctor",
)


def _capstone():
    import capstone

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    return capstone, md


def bornes_par_symbole() -> list[tuple[int, str, int]]:
    """(va, symbole, va_suivante) -- la borne haute d'une fonction est le symbole SUIVANT."""
    tries = P10018.symboles_tries()
    out = []
    for i, (va, nom) in enumerate(tries):
        suivante = tries[i + 1][0] if i + 1 < len(tries) else va + 0x1000
        out.append((va, nom, suivante))
    return out


def _voisinage(va: int | None, rayon: int = 2) -> list[str]:
    """Les symboles qui encadrent `va` dans l'ordre des adresses (`<-` marque la cible)."""
    if va is None:
        return []
    tries = P10018.symboles_tries()
    idx = next((i for i, (a, _) in enumerate(tries) if a == va), None)
    if idx is None:
        return []
    out = []
    for i in range(max(0, idx - rayon), min(len(tries), idx + rayon + 1)):
        a, nom = tries[i]
        out.append("%s %s%s" % ("<-" if i == idx else "  ", nom,
                                "" if i != idx else "   (le ctor)"))
    return out


def slots_des_lambdas(dll: Path, lam: dict[int, int],
                      bornes: dict[int, int]) -> dict[int, tuple[int, int]]:
    """{N: (slot Il2CppClass*, VA du ctor appele)}.

    L'allocateur n'est PAS ecrit en dur : c'est la cible d'appel presente dans le plus grand
    nombre de lambdas -- toutes en font exactement un.
    """
    capstone, md = _capstone()
    import pefile

    pe = pefile.PE(str(dll), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    image = pe.get_memory_mapped_image()
    pe.close()

    corps: dict[int, list] = {}
    for n, va in lam.items():
        fin = min(bornes.get(va, va + 0x400), va + 0x400)
        code = image[va - base:fin - base]
        corps[n] = list(md.disasm(code, va))

    # L'ALLOCATEUR SE DERIVE, il ne s'ecrit pas en dur : c'est la cible d'appel qui, dans le plus
    # grand nombre de lambdas, est PRECEDEE d'un `mov rcx, qword ptr [rip + X]` (le chargement du
    # slot `Il2CppClass*`). Ce critere ecarte `il2cpp_codegen_initialize_runtime_metadata`, qui
    # est encore plus frequent mais recoit une ADRESSE (`lea rcx, [rip + X]`), pas un slot.
    frequence: Counter = Counter()
    for insns in corps.values():
        vus = set()
        for i, ins in enumerate(insns):
            if (ins.mnemonic == "call" and ins.operands
                    and ins.operands[0].type == capstone.x86.X86_OP_IMM):
                fenetre = insns[max(0, i - 4):i]
                if any(k.mnemonic == "mov" and k.op_str.startswith("rcx, qword ptr [rip")
                       for k in fenetre):
                    vus.add(ins.operands[0].imm)
        frequence.update(vus)
    if not frequence:
        return {}
    allocateur = frequence.most_common(1)[0][0]

    out: dict[int, tuple[int, int]] = {}
    for n, insns in corps.items():
        slot = None
        pending = None
        ctor = None
        for ins in insns:
            if ins.mnemonic == "mov" and ins.op_str.startswith("rcx, qword ptr ["):
                for op in ins.operands:
                    if (op.type == capstone.x86.X86_OP_MEM
                            and op.mem.base == capstone.x86.X86_REG_RIP):
                        pending = ins.address + ins.size + op.mem.disp
            if (ins.mnemonic == "call" and ins.operands
                    and ins.operands[0].type == capstone.x86.X86_OP_IMM):
                cible = ins.operands[0].imm
                if cible == allocateur and slot is None:
                    slot = pending
                elif slot is not None and ctor is None and cible != allocateur:
                    ctor = cible
        if slot is not None:
            out[n] = (slot, ctor)
    return out


def indices_par_offset_statique(code: bytes, va_debut: int) -> list[tuple[int, int]]:
    """[(offset du champ `<>9__14_N`, cle EffectType)] dans l'ordre du code -- 2e voie.

    Le delegue de chaque lambda est mis en cache dans un champ statique de `<>c` dont l'offset
    croit de 8 en 8 dans l'ordre de DECLARATION des lambdas. On releve, pour chaque inscription,
    l'offset touche et la cle posee.
    """
    capstone, md = _capstone()
    insns = list(md.disasm(code, va_debut))

    out: list[tuple[int, int]] = []
    for i, ins in enumerate(insns):
        if ins.mnemonic != "call" or not ins.operands:
            continue
        if ins.operands[0].type != capstone.x86.X86_OP_IMM:
            continue
        # UNE INSCRIPTION SE RECONNAIT A SON 3e ARGUMENT, pas a la cible appelee : le delegue
        # vient d'etre construit et vit dans `rsi`, donc `mov r8, rsi` precede immediatement
        # l'appel a `Dictionary.Add` (les DEUX formes du site, thunk et corps specialise, le
        # portent). Filtrer par la cible obligerait a ecrire deux VA en dur.
        # Le `mov r8, rsi` doit etre le plus proche EN ARRIERE et AUCUN `call` ne doit s'intercaler
        # entre lui et l'appel courant -- sinon le meme setup serait compte deux fois.
        pose = None
        for k in range(i - 1, max(-1, i - 9), -1):
            if insns[k].mnemonic == "call":
                break
            if insns[k].mnemonic == "mov" and insns[k].op_str == "r8, rsi":
                pose = k
                break
        if pose is None:
            continue
        # une inscription = un `Dictionary.Add` : on la reconnait a ce qu'elle est precedee, dans
        # sa fenetre, d'une ecriture/lecture du champ statique de cache ET d'une cle immediate.
        off = None
        cle = None
        slot_pile = None
        j = i - 1
        while j >= 0 and i - j < 60:
            k = insns[j]
            # `mov edx, imm` : capstone rend `0x3f7` en hexa MAIS `1` / `2` en decimal --
            # n'accepter que le prefixe `0x` perdait exactement les cles 1 et 2 (mesure).
            if cle is None and k.mnemonic == "mov" and k.op_str.startswith("edx, "):
                v = k.op_str.split(", ", 1)[1]
                try:
                    cle = int(v, 16) if v.startswith("0x") else int(v)
                except ValueError:
                    pass
            if cle is None and slot_pile is None and k.mnemonic == "lea" \
                    and k.op_str.startswith("rdx, ["):
                slot_pile = k.op_str[k.op_str.index("[") + 1:k.op_str.rindex("]")].strip()
                for m in range(max(0, i - 60), i):
                    q = insns[m]
                    if (q.mnemonic == "mov"
                            and q.op_str.startswith("dword ptr [%s], " % slot_pile)):
                        v = q.op_str.split(", ", 1)[1]
                        try:
                            cle = int(v, 16) if v.startswith("0x") else int(v)
                        except ValueError:
                            pass
            if off is None and k.mnemonic == "mov" \
                    and k.op_str.startswith("rsi, qword ptr [rax"):
                s = k.op_str
                off = int(s.split("+")[1].strip().rstrip("]"), 16) if "+" in s else 0
            if off is None and k.mnemonic == "mov" and k.op_str.startswith("qword ptr [rcx"):
                s = k.op_str.split(", ")[0]
                off = int(s.split("+")[1].strip().rstrip("]"), 16) if "+" in s else 0
            if off is not None and cle is not None:
                break
            j -= 1
        if off is not None and cle is not None:
            out.append((off, cle))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--effet", type=int, action="append", default=[],
                    help="EffectType dont on veut le groupe de classe")
    ap.add_argument("--tsv", type=Path, default=None,
                    help="ecrit la table complete (JAMAIS sous data/)")
    ap.add_argument("--groupes", type=int, default=0,
                    help="affiche les N plus gros groupes de classe")
    args = ap.parse_args()

    try:
        build, dll = P10018.chemin_build()
    except SystemExit as exc:
        print("NON MESURE : %s" % exc)
        print("  (le binaire du build n'est pas sur cette machine -- tri-etat, pas un zero)")
        return 99
    if args.tsv is not None and "data" in args.tsv.resolve().parts[-3:]:
        print("REFUS : une sortie de run ne va jamais sous data/ (voir CLAUDE.md)")
        return 2

    va_debut, va_fin = P10018.bornes_fonction(P10018.SYM_FONCTION)
    code, base = P10018.lire_code(dll, va_debut, va_fin)
    print("BUILD %s ; image base 0x%x" % (build, base))

    lam = P10018.lambdas_par_indice()
    et = P10018.effect_types()
    cles, regularite = P10018.sequence_des_cles(code, va_debut)
    print("lambdas : %d ; cles inscrites : %d ; flux : %s" % (len(lam), len(cles), regularite))

    # --- VOIE 2 : indexation par l'offset du champ statique de cache -------------------------
    par_offset = indices_par_offset_statique(code, va_debut)
    offs = sorted(set(o for o, _ in par_offset))
    pas = sorted(set(offs[i + 1] - offs[i] for i in range(len(offs) - 1)))
    ok_offsets = (len(par_offset) == len(cles) and len(offs) == len(cles) and pas == [8])
    print("VOIE 2 -- offsets de cache : %d distincts, pas %s : %s"
          % (len(offs), pas, "OK" if ok_offsets else "ECHEC"))
    base_off = offs[0] if offs else 0
    voie2 = {}
    for o, cle in par_offset:
        voie2[(o - base_off) // 8] = cle
    voie1 = {i: v for i, (_, v) in enumerate(cles)}
    desaccords = sorted(n for n in voie1 if voie1[n] != voie2.get(n))
    ok_croise = not desaccords
    print("CONTROLE A -- les DEUX voies d'indexation s'accordent : %s%s"
          % ("OK" if ok_croise else "ECHEC",
             "" if ok_croise else " (%d desaccords, ex. %s)" % (len(desaccords), desaccords[:5])))

    # --- SLOTS DE CLASSE ----------------------------------------------------------------------
    bornes = {va: suiv for va, _, suiv in bornes_par_symbole()}
    slots = slots_des_lambdas(dll, lam, bornes)
    ok_slots = len(slots) == len(lam)
    print("CONTROLE B -- un slot Il2CppClass* lu pour chaque lambda : %s (%d / %d)"
          % ("OK" if ok_slots else "ECHEC", len(slots), len(lam)))

    noms_fn = {va: nom for va, nom in P10018.symboles_tries()}
    groupes: "OrderedDict[int, list[int]]" = OrderedDict()
    for n in sorted(slots):
        slot, _ctor = slots[n]
        groupes.setdefault(slot, []).append(voie1.get(n))
    print("classes distinctes (slots) : %d pour %d EffectType" % (len(groupes), len(slots)))

    # un ctor NOMME est un ctor porte par UN SEUL groupe (pas de corps ICF partage)
    ctor_de_groupe = {slot: slots[[n for n in slots if slots[n][0] == slot][0]][1]
                      for slot in groupes}
    ctor_compte = Counter(ctor_de_groupe.values())
    partages = {c for c, k in ctor_compte.items() if k > 1}

    # --- CONTRE-EPREUVE -----------------------------------------------------------------------
    eff_ce, sym_ce = CONTRE_EPREUVE
    slot_ce = next((slots[n][0] for n in slots if voie1.get(n) == eff_ce), None)
    grp_ce = groupes.get(slot_ce, [])
    ctor_ce = ctor_de_groupe.get(slot_ce)
    ok_ce = (slot_ce is not None and grp_ce == [eff_ce]
             and noms_fn.get(ctor_ce) == sym_ce and ctor_ce not in partages)
    print("CONTROLE C -- contre-epreuve %d : groupe %s, ctor %s : %s"
          % (eff_ce, grp_ce, noms_fn.get(ctor_ce, "?"), "OK" if ok_ce else "ECHEC"))

    if not (ok_offsets and ok_croise and ok_slots and ok_ce):
        print("")
        print("REFUS DE CONCLURE : un controle est tombe.")
        return 1

    # --- LE RESULTAT DE LA TRANCHE ------------------------------------------------------------
    print("")
    print("=== GROUPES DE CLASSE DES CIBLES ===")
    for eff in args.effet or list(CIBLES_1015R2):
        slot = next((slots[n][0] for n in slots if voie1.get(n) == eff), None)
        if slot is None:
            print("  %5d %-40s : ABSENT de la table (aucune fabrique)" % (eff, et.get(eff, "?")))
            continue
        grp = groupes[slot]
        ctor = ctor_de_groupe[slot]
        sym = noms_fn.get(ctor, "?")
        qualif = "ICF PARTAGE (ne nomme pas la classe)" if ctor in partages else "PROPRE"
        print("  %5d %-40s -> slot 0x%x ; %d effet(s) : %s"
              % (eff, et.get(eff, "?"), slot, len(grp),
                 ", ".join("%d=%s" % (v, et.get(v, "?")) for v in grp)))
        print("        ctor %s [%s]" % (sym, qualif))
        # VOISINAGE DE CODE. IL2CPP emet les corps groupes PAR CLASSE ; quand le symbole du ctor
        # est un corps ICF dont le proprietaire declare est une AUTRE classe, sa POSITION reste
        # celle de la classe qui l'a fait emettre. C'est un indice, pas une preuve -- il est
        # imprime pour etre confronte, jamais pour conclure seul.
        for enc in _voisinage(ctor, 2):
            print("          %s" % enc)

    if args.groupes:
        print("")
        print("=== %d PLUS GROS GROUPES ===" % args.groupes)
        for slot, effs in sorted(groupes.items(), key=lambda kv: -len(kv[1]))[:args.groupes]:
            print("  0x%x : %d : %s" % (slot, len(effs),
                                        ", ".join(str(v) for v in effs[:20])))

    if args.tsv:
        args.tsv.parent.mkdir(parents=True, exist_ok=True)
        with args.tsv.open("w", encoding="utf-8") as fh:
            fh.write("#lambda\teffect_type\teffect_name\tclass_slot\tctor_va\tctor_symbol\t"
                     "ctor_partage\tgroupe_taille\n")
            for n in sorted(slots):
                slot, ctor = slots[n]
                eff = voie1.get(n)
                fh.write("%d\t%s\t%s\t0x%x\t%s\t%s\t%s\t%d\n"
                         % (n, eff, et.get(eff, "?"), slot,
                            ("0x%x" % ctor) if ctor else "", noms_fn.get(ctor, ""),
                            "1" if ctor in partages else "0", len(groupes[slot])))
        print("")
        print("table complete ecrite : %s" % args.tsv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
