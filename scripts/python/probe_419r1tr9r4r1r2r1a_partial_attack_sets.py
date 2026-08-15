#!/usr/bin/env python3
"""LES SETS STATIQUES DE `StaticBattleRules` -- lus par les OCTETS, pas par le decompile.

LE TROU QUE CE PROBE BOUCHE
---------------------------
Trois predicats natifs de `StaticBattleRules` sont des `Contains` sur un ensemble STATIQUE bati
par le `.cctor` de leur classe :

    idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$IsTileStatusEffect
    idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$IsPartialAttack
    idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.TriggeredAbility$$IsPartialAttackAbility

Le contenu de ces ensembles n'est PAS lisible au decompile : le `.cctor` de
`StaticBattleRules.Effect` fait **0xd120 octets** (53 536), il DEPASSE le budget de
`mcp__ghidra__decompile_function`. DEUX tranches (#1103, #1107) ont bute dessus pour cette seule
raison, et le point `Fire in IsTileStatusEffect ?` de `#368-r2` est reste NON TRANCHE.

LA VOIE QUI MARCHE, ET POURQUOI ELLE EST STRUCTURELLE
------------------------------------------------------
Un `.cctor` IL2CPP qui remplit un `HashSet<T>`/`OrderedSet<T>` d'un type ENUM emet, pour chaque
membre, une sequence a immediat LISIBLE :

    mov  r8,  qword ptr [rip + X]     ; MethodInfo* de l'Add inflate
    lea  rdx, [rbp + N]               ; &valeur
    mov  rcx, rbx                     ; le set en construction
    mov  dword ptr [rbp + N], <IMM>   ; <-- L'ORDINAL, EN CLAIR
    call ...$$Add

puis range le set dans son champ statique :

    mov  rax, qword ptr [rip + C]     ; Il2CppClass*
    mov  rcx, qword ptr [rax + 0xb8]  ; Il2CppClass::static_fields
    mov  qword ptr [rcx + OFF], rbx   ; <-- LE CHAMP

Le probe n'a donc PAS besoin de comprendre le `.cctor` : il lui suffit de (1) lire l'ACCESSEUR --
petit, il donne le couple `(Il2CppClass*, OFF)` -- puis (2) desassembler le `.cctor` de cette
classe, reperer le store a `OFF`, et remonter jusqu'au store precedent pour delimiter le segment.
Les immediats de ce segment SONT les membres.

CE QUI EST MESURE, ET CE QUI NE L'EST PAS
------------------------------------------
MESURE : le contenu exact des trois ensembles, sur le PE du build COURANT.
NON MESURE : rien n'est deduit. Si le PE est absent (build desinstalle), le probe le DIT
(`rc 2`, << PE ABSENT >>) -- il ne rend jamais un ensemble vide qui se lirait comme << pas de
membre >>. Meme discipline tri-etat que `host_inputs.py`.

Etape 3 confronte les trois ensembles au port Python
(`engine/services/static_battle_rules.py`). C'est le CLIQUET : un renumerotage d'enum au prochain
build fait rougir ici, pas en silence a l'usage.

USAGE
    python probe_419r1tr9r4r1r2r1a_partial_attack_sets.py
    python probe_419r1tr9r4r1r2r1a_partial_attack_sets.py --pe <chemin GameAssembly.dll>
"""
from __future__ import annotations

import argparse
import bisect
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

IMAGE_BASE = 0x180000000
#: `Il2CppClass::static_fields` -- offset LU dans les trois accesseurs (`mov rax, [rax + 0xb8]`),
#: identique dans les trois, donc une propriete du runtime Unity 6 et pas de la classe.
IL2CPP_CLASS_STATIC_FIELDS = 0xB8

#: Les trois accesseurs a mesurer : symbole -> (enum du membre, nom du mirror Python).
CIBLES = (
    ("idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$IsTileStatusEffect",
     "EffectType", "TILE_STATUS_EFFECT_TYPES"),
    ("idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$IsPartialAttack",
     "EffectType", "PARTIAL_ATTACK_EFFECT_TYPES"),
    ("idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.TriggeredAbility"
     "$$IsPartialAttackAbility",
     "TriggeredAbilityType", "PARTIAL_ATTACK_TRIGGERED_ABILITY_TYPES"),
)


def _build_courant() -> str:
    jeux = sorted(p.name for p in (Path.home() / "AppData/Local/tacticus/games").glob("*")
                  if p.is_dir() and not p.name.startswith("."))
    return jeux[0] if len(jeux) == 1 else (jeux[-1] if jeux else "")


class Image:
    """Sections EXECUTABLES + table de symboles du build, sans Ghidra."""

    def __init__(self, pe_path: Path, build: str):
        import pefile
        self.build = build
        pe = pefile.PE(str(pe_path), fast_load=True)
        self.sections = []
        for s in pe.sections:
            va = IMAGE_BASE + s.VirtualAddress
            self.sections.append((va, va + max(s.Misc_VirtualSize, s.SizeOfRawData), s.get_data()))
        tsv = REPO / "data" / "symbols" / build / "ghidra" / "functions.tsv"
        self.syms = {}
        for line in tsv.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line or line.startswith("#"):
                continue
            p = line.split("\t")
            if len(p) >= 2:
                try:
                    self.syms[int(p[0], 16)] = p[1]
                except ValueError:
                    pass
        self.par_nom = {v: k for k, v in self.syms.items()}
        self.addrs = sorted(self.syms)

    def lire(self, va: int, n: int) -> bytes:
        for lo, hi, data in self.sections:
            if lo <= va < hi:
                return data[va - lo:va - lo + n]
        raise KeyError("VA hors sections : 0x%x" % va)

    def taille(self, va: int) -> int:
        i = bisect.bisect_right(self.addrs, va)
        return (self.addrs[i] - va) if i < len(self.addrs) else 0x1000

    def sym(self, va: int) -> str:
        return self.syms.get(va, "")


def _desassembler(img: Image, va: int, taille: int):
    """Desassemble en RE-SYNCHRONISANT sur octet invalide (un `.cctor` de 53 Ko traverse des
    ilots de donnees ; s'arreter au premier octet illisible perdrait la fin de la fonction)."""
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    code = img.lire(va, taille)
    out, off = [], 0
    while off < len(code):
        n = 0
        for ins in md.disasm(code[off:], va + off):
            out.append(ins)
            n += ins.size
        if n == 0:
            off += 1            # octet indecodable : on avance d'un cran
        else:
            off += n
            if off < len(code):
                off += 1        # l'arret venait d'un octet invalide juste apres
    return out


def _rip_cible(ins) -> "int | None":
    import capstone
    for op in ins.operands:
        if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
            return ins.address + ins.size + op.mem.disp
    return None


def lire_accesseur(img: Image, symbole: str):
    """Rend `(class_ptr_va, offset_statique, symbole_du_Contains)` d'un accesseur `Contains`."""
    import capstone
    va = img.par_nom.get(symbole)
    if va is None:
        return None, None, "SYMBOLE ABSENT"
    ins_list = _desassembler(img, va, img.taille(va))
    # ⚠ Le `Il2CppClass*` se capture AU MOMENT du `[reg + 0xb8]`, jamais << le dernier `[rip+C]`
    # rencontre >> : l'accesseur charge ENSUITE le `MethodInfo*` de l'`Add` inflate par la meme
    # forme d'instruction, et il ECRASERAIT la classe (mesure : `IsTileStatusEffect` rendait le
    # MethodInfo au lieu de `StaticBattleRules.Effect`, donc aucun store trouve dans le .cctor).
    cls_of_reg = {}
    cls_ptr, statics_reg, offset, contains = None, None, None, ""
    for ins in ins_list:
        if ins.mnemonic == "mov" and len(ins.operands) == 2:
            d, s = ins.operands
            if (d.type == capstone.x86.X86_OP_REG and s.type == capstone.x86.X86_OP_MEM
                    and s.mem.base == capstone.x86.X86_REG_RIP):
                cls_of_reg[d.reg] = _rip_cible(ins)
            # mov rX, qword [rY + 0xb8]  -- `Il2CppClass::static_fields` de la classe portee par rY
            elif (d.type == capstone.x86.X86_OP_REG and s.type == capstone.x86.X86_OP_MEM
                  and s.mem.disp == IL2CPP_CLASS_STATIC_FIELDS and s.mem.index == 0):
                statics_reg = d.reg
                cls_ptr = cls_of_reg.get(s.mem.base, cls_ptr)
            # mov rcx, qword [<statics> + OFF]  -- LE champ lu
            elif (statics_reg is not None and d.type == capstone.x86.X86_OP_REG
                  and s.type == capstone.x86.X86_OP_MEM and s.mem.base == statics_reg
                  and s.mem.index == 0):
                offset = s.mem.disp
        elif (ins.mnemonic == "call" and ins.operands
              and ins.operands[0].type == capstone.x86.X86_OP_IMM):
            nom = img.sym(ins.operands[0].imm)
            if "Contains" in nom:
                contains = nom
    return cls_ptr, offset, contains


def lire_cctor(img: Image, cls_ptr: int, offset: int, cctor_sym: str):
    """Rend la LISTE ORDONNEE des immediats `Add`-es dans le champ statique `+offset`.

    Le segment est delimite par les DEUX stores au bloc de statiques qui l'encadrent : le natif
    construit le set dans un registre, l'alimente, puis le range -- l'ordre du corps IL2CPP est
    donc `Add`... `store`."""
    import capstone
    va = img.par_nom.get(cctor_sym)
    if va is None:
        return None, "CCTOR ABSENT"
    ins_list = _desassembler(img, va, img.taille(va))
    statics_regs = {}
    cls_of_reg = {}
    dernier_cls = None
    bornes = []                      # (index, offset_du_store)
    for i, ins in enumerate(ins_list):
        if ins.mnemonic != "mov" or len(ins.operands) != 2:
            continue
        d, s = ins.operands
        if d.type == capstone.x86.X86_OP_REG and s.type == capstone.x86.X86_OP_MEM:
            if s.mem.base == capstone.x86.X86_REG_RIP:
                dernier_cls = _rip_cible(ins)
                cls_of_reg[d.reg] = dernier_cls
            elif s.mem.disp == IL2CPP_CLASS_STATIC_FIELDS and s.mem.index == 0:
                statics_regs[d.reg] = cls_of_reg.get(s.mem.base, dernier_cls)
        elif (d.type == capstone.x86.X86_OP_MEM and d.mem.base in statics_regs
              and d.mem.index == 0 and s.type == capstone.x86.X86_OP_REG):
            if statics_regs[d.mem.base] == cls_ptr:
                bornes.append((i, d.mem.disp))
    cible = [k for k, (_i, off) in enumerate(bornes) if off == offset]
    if not cible:
        return None, "AUCUN STORE A +0x%x" % offset
    k = cible[-1]
    fin = bornes[k][0]
    debut = bornes[k - 1][0] if k > 0 else 0
    membres, en_attente = [], None
    for ins in ins_list[debut:fin]:
        # `mov dword ptr [rbp + N], <IMM>` -- l'ordinal, pose juste avant son `Add`
        if (ins.mnemonic == "mov" and len(ins.operands) == 2
                and ins.operands[0].type == capstone.x86.X86_OP_MEM
                and ins.operands[1].type == capstone.x86.X86_OP_IMM
                and ins.operands[0].size == 4):
            en_attente = ins.operands[1].imm
        elif (ins.mnemonic == "call" and ins.operands
              and ins.operands[0].type == capstone.x86.X86_OP_IMM):
            nom = img.sym(ins.operands[0].imm)
            if ".Add" in nom or nom.endswith("$$Add"):
                if en_attente is not None:
                    membres.append(en_attente)
                en_attente = None
    return membres, ""


def _enum_noms(build: str, enum_court: str) -> dict:
    p = REPO / "data" / "symbols" / build / "frida" / "enums.tsv"
    if not p.exists():
        return {}
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#"):
            continue
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 2 or parts[0].split(".")[-1] != enum_court:
            continue
        m = {}
        for kv in parts[1].split(","):
            if "=" in kv:
                k, v = kv.split("=", 1)
                try:
                    m[int(k)] = v
                except ValueError:
                    pass
        return m
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pe", default=None)
    ap.add_argument("--build", default=None)
    args = ap.parse_args()

    build = args.build or _build_courant()
    pe = Path(args.pe) if args.pe else (
        Path.home() / "AppData/Local/tacticus/games" / build / "GameAssembly.dll")
    print("=== probe #419-r1-tr9-r4-r1-r2-r1a -- sets statiques de StaticBattleRules ===")
    print("build      : %s" % (build or "<INCONNU>"))
    print("PE         : %s" % pe)
    if not build or not pe.exists():
        print("PE ABSENT -- rien n'est mesure (aucun ensemble n'est rendu VIDE).")
        return 2
    if not (REPO / "data" / "symbols" / build / "ghidra" / "functions.tsv").exists():
        print("TABLE DE SYMBOLES ABSENTE pour %s -- rien n'est mesure." % build)
        return 2

    img = Image(pe, build)
    mesures = {}
    rc = 0

    print("\n--- etape 1/2 : accesseur -> champ statique -> membres du .cctor ---")
    for symbole, enum_court, mirror in CIBLES:
        cls_ptr, offset, contains = lire_accesseur(img, symbole)
        court = symbole.split("$$")[-1]
        if cls_ptr is None or offset is None:
            print("[%-24s] NON LU (%s)" % (court, contains or "accesseur illisible"))
            rc = 1
            continue
        proprio = symbole.split("$$")[0]
        cctor = proprio + "$$.cctor"
        membres, err = lire_cctor(img, cls_ptr, offset, cctor)
        if membres is None:
            print("[%-24s] statics+0x%-3x  CCTOR NON LU (%s)" % (court, offset, err))
            rc = 1
            continue
        noms = _enum_noms(build, enum_court)
        rendu = ", ".join("%s(%d)" % (noms.get(v, "<INCONNU>"), v) for v in membres)
        print("[%-24s] statics+0x%-3x  %-58s  %d membre(s)"
              % (court, offset, contains.split("$$")[-1], len(membres)))
        print("%-26s %s" % ("", rendu))
        mesures[mirror] = [int(v) for v in membres]

    print("\n--- etape 3 : confrontation au port Python ---")
    sys.path.insert(0, str(REPO / "scripts" / "python"))
    import engine.services.static_battle_rules as sbr
    for _symbole, _enum, mirror in CIBLES:
        attendu = mesures.get(mirror)
        if attendu is None:
            print("[%-38s] NON MESURE -- pas de confrontation" % mirror)
            continue
        porte = getattr(sbr, mirror, None)
        if porte is None:
            print("[%-38s] ABSENT DU PORT -- le natif en porte %d" % (mirror, len(attendu)))
            rc = 1
            continue
        p = sorted(int(x) for x in porte)
        n = sorted(attendu)
        if p == n:
            print("[%-38s] OK  %d membre(s) identiques" % (mirror, len(n)))
        else:
            print("[%-38s] ECART  natif=%s  port=%s" % (mirror, n, p))
            rc = 1

    print("\nrc = %d" % rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
