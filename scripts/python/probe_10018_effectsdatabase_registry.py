"""Probe #10018 -- LIRE la table `EffectType -> fabrique` d'`EffectsDatabase$$InitializeEffects`.

POURQUOI. `IdunBattle.Entities.Effects.BlockActiveAbilityEffect$$.ctor` a exactement TROIS
appelants, tous des lambdas `EffectsDatabase.<>c$$<InitializeEffects>b__14_<N>` aux memes
litteraux `(hasAutomaticActivation = 1, includeNormalAttack = 0, includeMachinePrimaryAbility = 1)`.
Deux membres de la famille sont nommes par leur enum (`26 Taunted_CantUseAbility`,
`1165 Stunned_CantUseAbility`) ; le TROISIEME n'avait jamais ete lu -- seulement devine
(`#1020-r5`, `#1020-r7`). Les lambdas n'ont AUCUNE xref de code : le corps d'`InitializeEffects`
ne les designe que par leur `MethodInfo*`, resolu au runtime.

COMMENT. `InitializeEffects` inscrit chaque fabrique par
`Dictionary<EffectType, Func<BaseEffect>>.Add(&cle, delegue)`. La cle est un `int` pose sur la
pile juste avant l'appel, donc elle EST dans le code, en clair. Ce probe desassemble la fonction
depuis le PE (pas depuis un dump derive) et rend la SEQUENCE des cles inscrites.

CE QUI FAIT DE CETTE MESURE UNE LECTURE ET NON UNE INFERENCE. L'indice de lambda `b__14_N` est
l'ordinal SOURCE du lambda dans la methode ; les inscriptions sont donc dans le meme ordre. Le
probe ne le POSTULE pas : il le VERIFIE sur les deux membres deja nommes de la famille
(`b__14_14 -> 26`, `b__14_165 -> 1165`) et sur le cardinal (607 lambdas <-> 607 inscriptions).
Si l'un des trois controles tombe, le probe REFUSE de conclure.

Aucune VA n'est ecrite en dur : les bornes viennent de `ghidra/functions.tsv`, par SYMBOLE.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
BUILD_ATTENDU = "t6dpr4k06g"

SYM_FONCTION = "IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects"
NOM_ENUM = "IdunBattle.Entities.Enum.EffectType"

MOTIF_LAMBDA = re.compile(
    r"IdunBattle\.Core\.Services\.EffectsDatabase\.u003Cu003Ec\$\$"
    r"u003CInitializeEffectsu003Eb__(\d+)_(\d+)$"
)

# Les TROIS lambdas qui construisent `BlockActiveAbilityEffect` -- LUES par
# `list_xrefs` sur `IdunBattle.Entities.Effects.BlockActiveAbilityEffect$$.ctor`.
LAMBDAS_BLOCK_ACTIVE_ABILITY = (14, 165, 581)

# Les deux membres de la famille deja NOMMES par leur enum, et deja traites comme tels par le
# port (`engine/battle_query.py::can_use_ability`). Ce sont les TEMOINS : le probe n'apparie
# PAS un lambda a un membre (ce serait l'inference qu'on cherche a eviter) -- il exige que
# l'ENSEMBLE des trois cles lues CONTIENNE ces deux-la. C'est falsifiable : si la table lue
# etait decalee, l'ensemble ne les contiendrait pas.
TEMOINS_FAMILLE = {26, 1165}

# Controle INDEPENDANT du code machine : la classe reellement construite par un lambda, LUE au
# decompile (`mcp__ghidra__decompile_function`). Ne sont retenues que les classes dont le nom
# apparie EXACTEMENT un membre d'`EffectType` -- l'appariement est donc falsifiable.
# PIEGE, et il est la raison pour laquelle cette liste est COURTE : les `.ctor` triviaux sont
# dedupliques par ICF, donc le SYMBOLE du ctor ne nomme PAS toujours la classe construite
# (`b__14_1` et `b__14_2` portent le meme symbole de ctor pour deux classes distinctes, et
# `b__14_583` porte `Test_CritDmgModifierEffect$$.ctor` alors que sa cle est `Stunned_DamageModifier`).
# Ce qui identifie la classe est le slot `Il2CppClass*` charge juste avant, pas le nom du ctor.
CLASSES_LUES = {
    0: "BlockEnteringUnits",
    3: "Fire",
    12: "Electrified_CounterAttack",
    100: "HazeOfCorruption_DamageTransfer",
    163: "NetworkedTargeting_DmgBonus",
    580: "Stunned",
}


def chemin_build() -> tuple[str, Path]:
    """(hash du build, chemin de GameAssembly.dll). Refuse si le dump et le jeu divergent."""
    marqueur = RACINE / "data" / "symbols" / BUILD_ATTENDU / "BUILD"
    if not marqueur.exists():
        raise SystemExit("table de symboles absente pour %s" % BUILD_ATTENDU)
    jeux = Path.home() / "AppData" / "Local" / "tacticus" / "games"
    dll = jeux / BUILD_ATTENDU / "GameAssembly.dll"
    if not dll.exists():
        raise SystemExit("GameAssembly.dll introuvable pour le build %s : %s" % (BUILD_ATTENDU, dll))
    return BUILD_ATTENDU, dll


def table_ghidra() -> Path:
    return RACINE / "data" / "symbols" / BUILD_ATTENDU / "ghidra" / "functions.tsv"


def symboles_tries() -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    with table_ghidra().open("r", encoding="utf-8", errors="replace") as fh:
        for ligne in fh:
            p = ligne.rstrip("\n").split("\t")
            if len(p) < 2:
                continue
            try:
                out.append((int(p[0], 16), p[1]))
            except ValueError:
                continue
    out.sort()
    return out


def bornes_fonction(symbole: str) -> tuple[int, int]:
    """VA de debut et VA de la fonction SUIVANTE (borne haute exclusive)."""
    tries = symboles_tries()
    for i, (va, nom) in enumerate(tries):
        if nom == symbole:
            suivante = tries[i + 1][0] if i + 1 < len(tries) else va + 0x100000
            return va, suivante
    raise SystemExit("symbole introuvable : %s" % symbole)


def lambdas_par_indice() -> dict[int, int]:
    out: dict[int, int] = {}
    for va, nom in symboles_tries():
        m = MOTIF_LAMBDA.match(nom)
        if m:
            out[int(m.group(2))] = va
    return out


def effect_types_declares() -> list[tuple[int, str]]:
    """(valeur, nom) dans l'ORDRE DE DECLARATION du dump IL2CPP -- source independante du code."""
    chemin = RACINE / "data" / "symbols" / BUILD_ATTENDU / "frida" / "enums.tsv"
    with chemin.open("r", encoding="utf-8", errors="replace") as fh:
        for ligne in fh:
            p = ligne.rstrip("\n").split("\t")
            if len(p) >= 2 and p[0] == NOM_ENUM:
                out: list[tuple[int, str]] = []
                for morceau in p[1].split(","):
                    if "=" in morceau:
                        v, n = morceau.split("=", 1)
                        out.append((int(v), n))
                return out
    raise SystemExit("enum %s introuvable" % NOM_ENUM)


def effect_types() -> dict[int, str]:
    return dict(effect_types_declares())


def lire_code(dll: Path, va_debut: int, va_fin: int) -> tuple[bytes, int]:
    import pefile

    pe = pefile.PE(str(dll), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    rva_debut = va_debut - base
    rva_fin = va_fin - base
    data = pe.get_memory_mapped_image()
    pe.close()
    return data[rva_debut:rva_fin], base


def flux_evenements(code: bytes, va_debut: int) -> list[tuple[str, int, int]]:
    """Flux ordonne des evenements d'inscription : ("CLE", va, imm) et ("DELEGUE", va, cible).

    Motif LU dans le code (pas postule) : chaque inscription fait
      1. `il2cpp_codegen_object_new(<>c)` puis `Delegate$$.ctor` -- corps ICF partage, unique et
         appele EXACTEMENT 607 fois, soit le cardinal des lambdas `b__14_N` ;
      2. la pose de la cle `EffectType`, en DEUX formes selon le site :
         `mov dword ptr [mem], imm32` (96 sites, cle passee par adresse au thunk generique
         `Dictionary<...>$$Add`) ou `mov r32, imm32` (511 sites, cle passee en registre au
         corps specialise). 96 + 511 = 607.
    Le probe ne choisit pas une forme : il prend les DEUX et verifie l'appariement 1 pour 1.
    """
    import capstone
    from collections import Counter

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True

    # La cible d'appel qui revient exactement autant de fois qu'il y a de lambdas EST le
    # constructeur de delegue (corps ICF). On la DERIVE, on ne l'ecrit pas en dur.
    appels: Counter = Counter()
    for ins in md.disasm(code, va_debut):
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            appels[ins.operands[0].imm] += 1
    cible_delegue = None
    attendu = len(lambdas_par_indice())
    for cible, n in appels.items():
        if n == attendu:
            cible_delegue = cible
            break

    flux: list[tuple[str, int, int]] = []
    for ins in md.disasm(code, va_debut):
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            if ins.operands[0].imm == cible_delegue:
                flux.append(("DELEGUE", ins.address, ins.operands[0].imm))
            continue
        if ins.mnemonic != "mov" or len(ins.operands) != 2:
            continue
        dst, src = ins.operands
        if src.type != capstone.x86.X86_OP_IMM or dst.size != 4:
            continue
        if dst.type in (capstone.x86.X86_OP_MEM, capstone.x86.X86_OP_REG):
            flux.append(("CLE", ins.address, src.imm))
    return flux


def sequence_des_cles(code: bytes, va_debut: int) -> tuple[list[tuple[int, int]], str]:
    """(VA, cle) dans l'ordre du code, plus le verdict de REGULARITE du flux."""
    flux = flux_evenements(code, va_debut)
    cles = [(va, imm) for genre, va, imm in flux if genre == "CLE"]
    delegues = [va for genre, va, _ in flux if genre == "DELEGUE"]
    if len(cles) != len(delegues):
        return cles, "IRREGULIER : %d cles pour %d delegues" % (len(cles), len(delegues))
    # Chaque cle doit tomber dans le MEME bloc d'inscription que son delegue : entre deux
    # delegues consecutifs il ne doit y avoir qu'UNE cle.
    genres = [g for g, _, _ in flux]
    blocs = "".join("C" if g == "CLE" else "D" for g in genres)
    irreguliers = len(re.findall(r"CC|DD", blocs))
    if irreguliers:
        return cles, "IRREGULIER : %d alternances rompues dans le flux" % irreguliers
    return cles, "REGULIER : alternance stricte cle/delegue sur %d inscriptions" % len(cles)


def diagnostic(code: bytes, va_debut: int) -> None:
    """Ventile ce que le code contient reellement, pour ne pas postuler un motif."""
    import capstone
    from collections import Counter

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    appels: Counter = Counter()
    stores: Counter = Counter()
    movs_reg: Counter = Counter()
    total = 0
    for ins in md.disasm(code, va_debut):
        total += 1
        if ins.mnemonic == "call" and ins.operands and ins.operands[0].type == capstone.x86.X86_OP_IMM:
            appels[ins.operands[0].imm] += 1
        if ins.mnemonic == "mov" and len(ins.operands) == 2:
            dst, src = ins.operands
            if src.type == capstone.x86.X86_OP_IMM:
                if dst.type == capstone.x86.X86_OP_MEM:
                    stores[dst.size] += 1
                elif dst.type == capstone.x86.X86_OP_REG:
                    movs_reg[dst.size] += 1
    print("")
    print("DIAGNOSTIC -- %d instructions decodees" % total)
    noms = {va: nom for va, nom in symboles_tries()}
    print("  cibles d'appel les plus frequentes :")
    for cible, n in appels.most_common(8):
        print("    %6d x  0x%x  %s" % (n, cible, noms.get(cible, "<inconnu>")))
    print("  `mov [mem], imm` par taille : %s" % dict(stores))
    print("  `mov reg, imm`   par taille : %s" % dict(movs_reg))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--diagnostic", action="store_true")
    ap.add_argument("--json", type=Path, default=None, help="ecrit la table complete (hors data/)")
    ap.add_argument("--resoudre", type=int, action="append", default=[],
                    help="indice de lambda dont on veut l'EffectType")
    ap.add_argument("--fenetre", type=int, default=2)
    args = ap.parse_args()

    build, dll = chemin_build()
    va_debut, va_fin = bornes_fonction(SYM_FONCTION)
    code, base = lire_code(dll, va_debut, va_fin)
    print("BUILD %s ; image base 0x%x" % (build, base))
    print("%s : %d octets de code" % (SYM_FONCTION, len(code)))

    lam = lambdas_par_indice()
    print("lambdas <InitializeEffects>b__14_N : %d (indices %d..%d)"
          % (len(lam), min(lam), max(lam)))

    if args.diagnostic:
        diagnostic(code, va_debut)
        return 0

    cles, regularite = sequence_des_cles(code, va_debut)
    print("cles inscrites LUES dans le code    : %d" % len(cles))
    print("flux d'inscription                  : %s" % regularite)

    et = effect_types()
    doublons = len(cles) - len(set(v for _, v in cles))
    print("cles en double                      : %d" % doublons)
    inconnues = [v for _, v in cles if v not in et]
    print("cles hors de l'enum EffectType      : %d" % len(inconnues))

    # --- CONTROLES : la loi n'est retenue que si les trois passent ---
    ok_cardinal = len(cles) == len(lam)
    print("")
    print("CONTROLE 1 -- cardinal cles == cardinal lambdas : %s (%d vs %d)"
          % ("OK" if ok_cardinal else "ECHEC", len(cles), len(lam)))

    famille = {cles[i][1] for i in LAMBDAS_BLOCK_ACTIVE_ABILITY if i < len(cles)}
    ok_temoins = TEMOINS_FAMILLE <= famille
    print("CONTROLE 2 -- cles des trois lambdas BlockActiveAbilityEffect : %s"
          % ", ".join("%d = %s" % (v, et.get(v, "?")) for v in sorted(famille)))
    print("             contient les deux membres deja NOMMES %s : %s"
          % (sorted(TEMOINS_FAMILLE), "OK" if ok_temoins else "ECHEC"))

    ok_unicite = doublons == 0 and not inconnues
    print("CONTROLE 3 -- cles uniques et toutes dans EffectType : %s"
          % ("OK" if ok_unicite else "ECHEC"))

    ok_regulier = regularite.startswith("REGULIER")
    print("CONTROLE 4 -- alternance stricte du flux             : %s"
          % ("OK" if ok_regulier else "ECHEC"))

    ok_classes = True
    detail_classes = []
    for indice, attendu in sorted(CLASSES_LUES.items()):
        lu = et.get(cles[indice][1], "?") if indice < len(cles) else "?"
        bon = lu == attendu
        ok_classes &= bon
        detail_classes.append("b__14_%d %s%s" % (indice, lu, "" if bon else " != %s" % attendu))
    print("CONTROLE 6 -- classe LUE au decompile == nom de la cle : %s"
          % ("OK" if ok_classes else "ECHEC"))
    print("             %s" % " ; ".join(detail_classes))

    if not (ok_cardinal and ok_temoins and ok_unicite and ok_regulier and ok_classes):
        print("")
        print("REFUS DE CONCLURE : un controle est tombe, l'appariement n'est pas etabli.")
        return 1

    # CONTROLE 5 -- source INDEPENDANTE. `frida/enums.tsv` preserve l'ordre de DECLARATION des
    # membres (il n'est pas trie numeriquement) et vient du dump IL2CPP, pas du code machine.
    # Si la sequence lue est la bonne, elle doit en etre une SOUS-SUITE presque parfaite.
    declares = effect_types_declares()
    positions = {v: i for i, (v, _) in enumerate(declares)}
    suite = [positions.get(v, -1) for _, v in cles]
    inversions = sum(1 for a, b in zip(suite, suite[1:]) if a >= b)
    print("CONTROLE 5 -- sous-suite de l'ordre DECLARE (source independante) : "
          "%d inversions sur %d transitions" % (inversions, len(suite) - 1))
    absents = [v for v, _ in declares if v not in {c for _, c in cles}]
    print("             membres DECLARES sans fabrique : %d -> %s"
          % (len(absents), ", ".join("%d=%s" % (v, et.get(v, "?")) for v in absents[:12])))

    print("")
    print("APPARIEMENT ETABLI : la N-ieme cle inscrite est celle de b__14_N.")
    troisieme = sorted(famille - TEMOINS_FAMILLE)
    print("TROISIEME MEMBRE DE LA FAMILLE, LU : %s"
          % ", ".join("%d = %s" % (v, et.get(v, "?")) for v in troisieme))

    for indice in args.resoudre:
        if not (0 <= indice < len(cles)):
            print("  b__14_%d : hors table" % indice)
            continue
        print("")
        for d in range(-args.fenetre, args.fenetre + 1):
            j = indice + d
            if 0 <= j < len(cles):
                v = cles[j][1]
                marque = "  <== " if d == 0 else "      "
                print("%s b__14_%-4d -> EffectType %5d = %s" % (marque, j, v, et.get(v, "?")))

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps({str(i): {"effect_type": v, "nom": et.get(v, "?")}
                        for i, (_, v) in enumerate(cles)},
                       indent=1, ensure_ascii=True),
            encoding="utf-8",
        )
        print("")
        print("table complete ecrite : %s" % args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
