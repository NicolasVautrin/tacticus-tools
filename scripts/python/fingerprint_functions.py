#!/usr/bin/env python3
"""Empreinte STRUCTURELLE par fonction : reperer <<meme nom, corps change>> entre deux builds.

LE TROU QUE CET OUTIL BOUCHE
----------------------------
Le depot tient sur une mesure : entre builds, les NOMS sont stables a 97,5 %, les ADRESSES
changent a 100 %. D'ou la regle <<on cite un SYMBOLE, jamais une adresse>>. Mais le diff de
`data/symbols/<build>/ghidra/functions.tsv` (forme `<adresse>\\t<symbole>`) ne voit qu'un nom
qui APPARAIT, DISPARAIT ou se RENOMME. Un `CalculateDirectDamage` dont la formule a bouge s'y
lit comme IDENTIQUE -- son nom n'a pas change, et son adresse change de toute facon.

C'est exactement ce qui perime un port en SILENCE : le mirror Python d'une fonction dont le
natif a bouge devient faux sans qu'aucun outil ne le signale.

LE CRITERE, AVANT LA METHODE
----------------------------
Question binaire : <<pour un symbole present dans les DEUX builds, son corps a-t-il change ?>>

Ce qui est difficile n'est pas de hacher -- c'est de hacher quelque chose qui SURVIT A LA
RELOCATION. Entre deux builds, le layout est entierement reorganise : chaque `call rel32` porte
un deplacement different parce que sa cible s'est deplacee differemment. Un sha256 des octets
bruts rendrait donc <<100 % des fonctions ont change>>, le resultat inutile par excellence.

On normalise ce qui est RELOCALISE, on garde ce qui est STRUCTUREL :

  RELOCALISE (neutralise)              STRUCTUREL (conserve)
  -------------------------            ----------------------------------------
  cible d'un call/jmp externe          -> le SYMBOLE de la cible, pas son delta
  cible RIP-relative vers du code      -> le SYMBOLE
  cible RIP-relative vers des donnees  -> un jeton par SECTION (limite : cf. plus bas)
  adresse absolue dans un immediat     -> `<ABS>` ou le symbole
  branchement INTERNE a la fonction    -> son delta, qui est deja invariant (le corps
                                          se deplace en BLOC, les sauts internes suivent)
                                       registres, mnemoniques, ordre des instructions
                                       offsets de struct (`[rcx + 0xa8]`)
                                       constantes immediates (les formules !)

CINQ COUCHES, PAS UNE -- pour que le diff VENTILE au lieu de dire seulement <<ca a change>> :

  h_body   sha1 du flux complet normalise ......... LE VERDICT
  h_mnem   sha1 de la seule sequence de mnemoniques  structure du code, operandes ignorees
  h_calls  sha1 des cibles d'appel NOMMEES ......... qui la fonction appelle
  h_imm    sha1 des litteraux conserves ............ constantes et offsets
  n_ins    nombre d'instructions .................... la mesure la plus grossiere

Un `h_mnem` identique avec un `h_body` different dit <<meme squelette, operandes changees>> :
typiquement une constante de formule ou une cible d'appel. C'est le signal le plus interessant
pour un port.

CE QUE L'EMPREINTE NE VOIT PAS (limite ASSUMEE, mesuree par la garde)
--------------------------------------------------------------------
Une reference vers une DONNEE (`mov rcx, qword ptr [rip + X]` chargeant un `Il2CppClass*`) est
reduite au jeton de sa section : deux classes differentes donnent le meme jeton. Une fonction
dont SEULE une reference de donnee change est donc un FAUX NEGATIF. On ne peut pas faire mieux
sans une table de symboles de DONNEES par build -- `functions.tsv` ne contient que des
fonctions. La garde `probe_253_empreinte_structurelle.py` mesure ce trou au lieu de le taire.

DEUX SOURCES D'OCTETS, UN SEUL PIPELINE
---------------------------------------
Le build COURANT a son `GameAssembly.dll` sur disque -> lu par pefile.
Un build ARCHIVE n'existe plus que comme projet Ghidra -> ses octets sont extraits par
`scripts/ghidra/GhidraDumpCodeBytes.java` (analyzeHeadless -readOnly, independant du serveur
ghidra-mcp). Les deux alimentent la MEME normalisation : un ecart mesure ne peut donc pas
venir d'une difference de chaine d'extraction.

USAGE
    python fingerprint_functions.py empreinte --build rnca9r7q6c --pe <chemin GameAssembly.dll>
    python fingerprint_functions.py empreinte --build gqfc5mff6c --blocs logs/ghidra-dump/gqfc5mff6c
    python fingerprint_functions.py diff --avant logs/fingerprints/gqfc5mff6c.tsv \\
                                          --apres logs/fingerprints/rnca9r7q6c.tsv
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SYMBOLS_DIR = REPO / "data" / "symbols"
# Les sorties sont des ARTEFACTS DE RUN : elles vont dans logs/, jamais dans data/ (qui ne
# contient que des ENTREES versionnees -- `probe_273 --only-scan` etape 0c rougit sinon).
LOGS_DIR = REPO / "logs" / "fingerprints"

IMAGE_BASE = 0x180000000
# Borne de securite sur la taille d'une fonction. La borne haute naturelle est l'adresse de la
# fonction SUIVANTE, mais quand celle-ci est tres loin (fin de section, trou de donnees) on
# desassemblerait des megaoctets pour rien.
MAX_FN_BYTES = 96 * 1024

# ---------------------------------------------------------------------------
# Mnemoniques : ce qui TERMINE un flux, ce qui BRANCHE.
# Servent a delimiter le corps reel d'une fonction sans dependre du voisin.
# ---------------------------------------------------------------------------
TERMINAUX = frozenset({"ret", "retf", "retfq", "iret", "iretd", "iretq",
                       "jmp", "ljmp", "int3", "ud0", "ud1", "ud2", "hlt"})
BRANCHES_COND = frozenset({
    "ja", "jae", "jb", "jbe", "jc", "jcxz", "je", "jecxz", "jg", "jge", "jl", "jle",
    "jna", "jnae", "jnb", "jnbe", "jnc", "jne", "jng", "jnge", "jnl", "jnle", "jno",
    "jnp", "jns", "jnz", "jo", "jp", "jpe", "jpo", "jrcxz", "js", "jz",
    "loop", "loope", "loopne", "loopnz", "loopz",
})
BRANCHES = BRANCHES_COND | {"jmp", "call"}
# Octets de bourrage emis par MSVC entre deux fonctions.
PADDING = frozenset({"int3", "nop"})

RE_HEX = re.compile(r"0x[0-9a-f]+")
RE_RIP = re.compile(r"\[rip ([+-]) (0x[0-9a-f]+)\]")


def sha1_12(parts) -> str:
    """Empreinte courte (12 hex = 48 bits). Le corpus fait ~150 000 fonctions : la probabilite
    de collision accidentelle y est negligeable, et la table reste lisible a l'oeil."""
    h = hashlib.sha1()
    for p in parts:
        h.update(p.encode("utf-8", "replace"))
        h.update(b"\x1f")
    return h.hexdigest()[:12]


# ===========================================================================
# 1. SOURCES D'OCTETS -- deux origines, une seule interface
# ===========================================================================
class ImageCode:
    """Les octets executables d'un build, adressables par VA.

    `segments` est une liste de (va_debut, va_fin, nom_section, octets).
    """

    def __init__(self, segments, image_base, origine):
        self.segments = sorted(segments, key=lambda s: s[0])
        self.image_base = image_base
        self.origine = origine
        self.va_min = self.segments[0][0] if self.segments else 0
        self.va_max = max((s[1] for s in self.segments), default=0)

    def segment_de(self, va):
        for deb, fin, nom, data in self.segments:
            if deb <= va < fin:
                return (deb, fin, nom, data)
        return None

    def octets(self, va, taille):
        seg = self.segment_de(va)
        if seg is None:
            return b""
        deb, fin, _nom, data = seg
        off = va - deb
        return data[off:off + min(taille, fin - va)]

    def nom_section(self, va):
        seg = self.segment_de(va)
        return seg[2] if seg else None

    def resume(self):
        lignes = ["  origine=%s  image_base=0x%x" % (self.origine, self.image_base)]
        for deb, fin, nom, data in self.segments:
            lignes.append("    %-10s 0x%x..0x%x  %d octets" % (nom, deb, fin, len(data)))
        return "\n".join(lignes)


def charger_depuis_pe(chemin: Path) -> ImageCode:
    """Sections executables d'un PE sur disque (le build COURANT)."""
    import pefile

    pe = pefile.PE(str(chemin), fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    IMAGE_SCN_MEM_EXECUTE = 0x20000000
    segments = []
    for s in pe.sections:
        if not (s.Characteristics & IMAGE_SCN_MEM_EXECUTE):
            continue
        nom = s.Name.rstrip(b"\x00").decode("ascii", "replace")
        data = s.get_data()
        # VirtualSize peut depasser les donnees brutes (bss-like) : on borne sur ce qu'on a.
        taille = min(s.Misc_VirtualSize or len(data), len(data))
        deb = base + s.VirtualAddress
        segments.append((deb, deb + taille, nom, data[:taille]))
    pe.close()
    if not segments:
        raise SystemExit("ERREUR: aucune section executable dans %s" % chemin)
    return ImageCode(segments, base, "PE:%s" % chemin.name)


def charger_depuis_blocs(dossier: Path) -> ImageCode:
    """Blocs memoire extraits d'un projet Ghidra (un build ARCHIVE).

    Produit par `scripts/ghidra/GhidraDumpCodeBytes.java`.
    """
    meta = dossier / "blocks.meta"
    if not meta.exists():
        raise SystemExit("ERREUR: %s introuvable (lancer GhidraDumpCodeBytes.java)" % meta)
    base = IMAGE_BASE
    img_meta = dossier / "image.meta"
    if img_meta.exists():
        for ligne in img_meta.read_text(encoding="utf-8").splitlines():
            if ligne.startswith("imageBase\t"):
                base = int(ligne.split("\t", 1)[1].strip(), 16)
    segments = []
    for ligne in meta.read_text(encoding="utf-8").splitlines():
        if ligne.startswith("#") or not ligne.strip():
            continue
        champs = ligne.split("\t")
        if len(champs) < 8 or not champs[7]:
            continue
        nom, start_va, taille = champs[0], int(champs[1], 16), int(champs[2])
        data = (dossier / champs[7]).read_bytes()
        taille = min(taille, len(data))
        segments.append((start_va, start_va + taille, nom, data[:taille]))
    if not segments:
        raise SystemExit("ERREUR: aucun bloc executable dans %s" % dossier)
    return ImageCode(segments, base, "ghidra-blocks:%s" % dossier.name)


# ===========================================================================
# 2. TABLE DES SYMBOLES
# ===========================================================================
def charger_functions_tsv(build: str, chemin: Path | None = None):
    """Rend (liste triee de (va, symbole), dict va -> symbole).

    `functions.tsv` n'est PAS trie (mesure : 29 741 inversions sur rnca9r7q6c) -- on trie ici.
    Les adresses, elles, sont uniques (mesure : 0 doublon sur les deux builds).
    """
    p = chemin or (SYMBOLS_DIR / build / "ghidra" / "functions.tsv")
    if not p.exists():
        raise SystemExit("ERREUR: %s introuvable" % p)
    entrees = []
    for ligne in p.read_text(encoding="utf-8").splitlines():
        if ligne.startswith("#") or not ligne.strip():
            continue
        a, _, s = ligne.partition("\t")
        if not s:
            continue
        entrees.append((int(a, 16), s))
    entrees.sort(key=lambda e: e[0])
    return entrees, dict(entrees)


# ===========================================================================
# 3. NORMALISATION + HACHAGE
# ===========================================================================
class Normaliseur:
    """Transforme une instruction desassemblee en jeton INVARIANT A LA RELOCATION."""

    def __init__(self, image: ImageCode, par_va: dict):
        self.image = image
        self.par_va = par_va
        self.va_min = image.va_min
        self.va_max = image.va_max
        self._cache_section = {}

    def _jeton_cible(self, cible: int) -> str:
        """Une adresse ABSOLUE -> un jeton stable entre builds.

        Une fonction connue rend son SYMBOLE : c'est ce qui survit a la relocation, et c'est
        la meme regle que <<on cite un symbole, jamais une adresse>>, appliquee a la machine.
        """
        sym = self.par_va.get(cible)
        if sym is not None:
            # Un `FUN_<addr>` porte l'adresse DANS son nom : le citer reintroduirait
            # exactement la volatilite qu'on cherche a neutraliser.
            return "<F>" if sym.startswith("FUN_") else "<F:%s>" % sym
        sect = self.image.nom_section(cible)
        if sect is not None:
            return "<D:%s>" % sect
        if self.va_min <= cible < self.va_max:
            return "<D:?>"
        return "<X>"      # hors image : import, thunk, donnee non mappee

    def _jeton_imm(self, m) -> str:
        """Un litteral hexadecimal dans les operandes.

        On ne neutralise QUE ce qui est une adresse dans l'image. Les offsets de struct
        (`+0xa8`) et les constantes de formule sont STRUCTURELS : les effacer viderait
        l'empreinte de ce qui fait justement la valeur d'un port.
        """
        v = int(m.group(0), 16)
        if self.va_min <= v < self.va_max:
            return self._jeton_cible(v)
        return m.group(0)

    def instruction(self, addr, size, mnem, ops, fn_deb, fn_fin):
        if not ops:
            return mnem
        if mnem in BRANCHES and ops.startswith("0x") and " " not in ops:
            cible = int(ops, 16)
            if fn_deb <= cible < fn_fin:
                # Saut INTERNE : le delta est deja invariant, le corps se deplace en bloc.
                d = cible - addr
                return "%s .%s0x%x" % (mnem, "+" if d >= 0 else "-", abs(d))
            return "%s %s" % (mnem, self._jeton_cible(cible))
        if "0x" not in ops:
            return "%s %s" % (mnem, ops)          # chemin rapide : rien a normaliser
        if "rip" in ops:
            suivante = addr + size
            def _rip(m):
                disp = int(m.group(2), 16)
                cible = suivante + disp if m.group(1) == "+" else suivante - disp
                return "[%s]" % self._jeton_cible(cible)
            ops = RE_RIP.sub(_rip, ops)
        return "%s %s" % (mnem, RE_HEX.sub(self._jeton_imm, ops))


def delimiter_corps(insns, fn_deb, borne):
    """Coupe la liste d'instructions a la FIN REELLE de la fonction.

    POURQUOI CE N'EST PAS <<jusqu'a la fonction suivante>> : cette borne-la depend du VOISIN.
    Si le voisin se deplace entre deux builds, l'empreinte bougerait sans que le corps ait
    change -- un faux positif pur, et massif. On s'arrete donc au premier flux TERMINAL
    (`ret`, `jmp`, `int3`...) au-dela duquel plus aucun branchement interne ne pointe.

    Rend (index_de_fin_exclu, va_fin, drapeau).
    """
    max_cible = fn_deb
    for i, (addr, size, mnem, ops) in enumerate(insns):
        if mnem in BRANCHES and ops.startswith("0x") and " " not in ops:
            cible = int(ops, 16)
            if fn_deb <= cible < borne and cible > max_cible:
                max_cible = cible
        suivante = addr + size
        if mnem in TERMINAUX and max_cible < suivante:
            return i + 1, suivante, ""
    # Aucun terminal atteint : soit capstone a bute sur des donnees, soit la borne du voisin
    # a coupe la fonction. On le DIT au lieu de rendre une empreinte silencieusement partielle.
    fin = insns[-1][0] + insns[-1][1] if insns else fn_deb
    return len(insns), fin, "trunc"


def empreinter_build(build, image, entrees, par_va, verbose=True):
    """Calcule l'empreinte de chaque fonction. Rend une liste de dicts."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = False                 # disasm_lite : ~4x plus rapide, suffisant ici
    norm = Normaliseur(image, par_va)
    resultats = []
    t0 = time.time()
    n = len(entrees)

    for idx, (va, sym) in enumerate(entrees):
        if verbose and idx % 20000 == 0 and idx:
            print("    ... %d/%d fonctions (%.0f s)" % (idx, n, time.time() - t0))
        seg = image.segment_de(va)
        if seg is None:
            resultats.append(dict(va=va, sym=sym, taille=0, n_ins=0, h_body="-",
                                  h_mnem="-", h_calls="-", h_imm="-", flags="hors-image"))
            continue
        seg_deb, seg_fin, _nom, data = seg
        borne = entrees[idx + 1][0] if idx + 1 < n else seg_fin
        if borne <= va or borne > seg_fin:
            borne = seg_fin
        borne = min(borne, va + MAX_FN_BYTES)

        code = data[va - seg_deb: borne - seg_deb]
        insns = list(md.disasm_lite(code, va))
        if not insns:
            resultats.append(dict(va=va, sym=sym, taille=0, n_ins=0, h_body="-",
                                  h_mnem="-", h_calls="-", h_imm="-", flags="vide"))
            continue

        nb, va_fin, flag = delimiter_corps(insns, va, borne)
        corps = insns[:nb]
        # Le bourrage inter-fonctions n'appartient a personne : on l'ecarte pour que l'empreinte
        # ne bouge pas au gre de l'alignement du voisin.
        while corps and corps[-1][2] in PADDING:
            corps.pop()
        if not corps:
            resultats.append(dict(va=va, sym=sym, taille=0, n_ins=0, h_body="-",
                                  h_mnem="-", h_calls="-", h_imm="-", flags="padding"))
            continue

        jetons, mnems, appels, imms = [], [], [], []
        for (addr, size, mnem, ops) in corps:
            j = norm.instruction(addr, size, mnem, ops, va, va_fin)
            jetons.append(j)
            mnems.append(mnem)
            if mnem == "call":
                appels.append(j[5:])
            for m in RE_HEX.finditer(j):
                imms.append(m.group(0))

        resultats.append(dict(
            va=va, sym=sym,
            taille=corps[-1][0] + corps[-1][1] - va,
            n_ins=len(corps),
            h_body=sha1_12(jetons),
            h_mnem=sha1_12(mnems),
            h_calls=sha1_12(appels) if appels else "-",
            h_imm=sha1_12(imms) if imms else "-",
            flags=flag,
        ))
    if verbose:
        print("    %d fonctions empreintees en %.0f s" % (n, time.time() - t0))
    return resultats


COLONNES = ["va", "sym", "taille", "n_ins", "h_body", "h_mnem", "h_calls", "h_imm", "flags"]


def ecrire_tsv(chemin: Path, build: str, image: ImageCode, resultats):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "w", encoding="utf-8", newline="\n") as f:
        f.write("#!empreinte-structurelle\tbuild=%s\torigine=%s\tfonctions=%d\tgenere=%s\n"
                % (build, image.origine, len(resultats),
                   time.strftime("%Y-%m-%dT%H:%M:%S")))
        f.write("#" + "\t".join(COLONNES) + "\n")
        for r in resultats:
            f.write("%x\t%s\t%d\t%d\t%s\t%s\t%s\t%s\t%s\n" % (
                r["va"], r["sym"], r["taille"], r["n_ins"],
                r["h_body"], r["h_mnem"], r["h_calls"], r["h_imm"], r["flags"]))


def lire_tsv(chemin: Path):
    """Rend (entete_dict, liste de dicts)."""
    if not chemin.exists():
        raise SystemExit("ERREUR: %s introuvable" % chemin)
    entete, lignes = {}, []
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        if ligne.startswith("#!"):
            for champ in ligne[2:].split("\t")[1:]:
                k, _, v = champ.partition("=")
                entete[k] = v
            continue
        if ligne.startswith("#") or not ligne.strip():
            continue
        c = ligne.split("\t")
        lignes.append(dict(va=int(c[0], 16), sym=c[1], taille=int(c[2]), n_ins=int(c[3]),
                           h_body=c[4], h_mnem=c[5], h_calls=c[6],
                           h_imm=c[7], flags=c[8] if len(c) > 8 else ""))
    return entete, lignes


# ===========================================================================
# 4. LE DIFF
# ===========================================================================
def apparier(avant, apres):
    """Appariement par SYMBOLE, avec les inappariables mis DE COTE et COMPTES.

    Deux familles ne peuvent structurellement pas etre appariees par nom :
      - `FUN_<adresse>` : le nom CONTIENT l'adresse, il change donc a chaque build par
        construction (mesure : 14,8 % / 15,8 % des lignes) ;
      - les symboles presents PLUSIEURS FOIS dans un meme build (mesure : 5 341 / 4 901) --
        corps gshared et surcharges dedupliquees. Les fondre choisirait un appariement au
        hasard et fabriquerait des changements imaginaires.
    Les taire gonflerait artificiellement APPARU/DISPARU : on les rend a part.
    """
    def indexer(lignes):
        par_sym, ambigus = {}, set()
        for l in lignes:
            s = l["sym"]
            if s.startswith("FUN_"):
                continue
            if s in par_sym:
                ambigus.add(s)
            else:
                par_sym[s] = l
        for s in ambigus:
            par_sym.pop(s, None)
        return par_sym, ambigus

    ia, amb_a = indexer(avant)
    ib, amb_b = indexer(apres)
    communs = sorted(set(ia) & set(ib))
    return ia, ib, communs, amb_a, amb_b


def classifier(a, b):
    """Ventile un couple (avant, apres) apparie. Rend (verdict, detail)."""
    if a["h_body"] == "-" or b["h_body"] == "-":
        return "ILLISIBLE", a["flags"] or b["flags"] or "?"
    if a["h_body"] == b["h_body"]:
        return "IDENTIQUE", ""
    quoi = []
    if a["n_ins"] != b["n_ins"]:
        quoi.append("n_ins %d->%d" % (a["n_ins"], b["n_ins"]))
    if a["h_mnem"] != b["h_mnem"]:
        quoi.append("opcodes")
    if a["h_calls"] != b["h_calls"]:
        quoi.append("appels")
    if a["h_imm"] != b["h_imm"]:
        quoi.append("litteraux")
    if a["h_mnem"] == b["h_mnem"]:
        # Meme squelette d'instructions, operandes differentes : le signal le plus utile
        # pour un port (une constante de formule ou une cible d'appel a bouge).
        quoi.append("MEME-SQUELETTE")
    return "CORPS_CHANGE", ",".join(quoi) if quoi else "operandes"


def cmd_empreinte(args):
    build = args.build
    if args.pe:
        image = charger_depuis_pe(Path(args.pe))
    elif args.blocs:
        image = charger_depuis_blocs(Path(args.blocs))
    else:
        raise SystemExit("ERREUR: --pe ou --blocs requis")
    print("[image] %s" % build)
    print(image.resume())

    entrees, par_va = charger_functions_tsv(build, Path(args.functions) if args.functions else None)
    print("[symboles] %d entrees dans functions.tsv" % len(entrees))
    resultats = empreinter_build(build, image, entrees, par_va)

    sortie = Path(args.out) if args.out else (LOGS_DIR / ("%s.tsv" % build))
    ecrire_tsv(sortie, build, image, resultats)
    print("[sortie] %s" % sortie)

    # -- pouvoir DISCRIMINANT, mesure et non postule : combien de fonctions distinctes
    #    partagent la meme empreinte ? Une empreinte tres collisionnante ne peut pas
    #    detecter un changement qui transformerait un corps en un autre deja present.
    lisibles = [r for r in resultats if r["h_body"] != "-"]
    par_body = {}
    for r in lisibles:
        par_body.setdefault(r["h_body"], 0)
        par_body[r["h_body"]] += 1
    uniques = sum(1 for v in par_body.values() if v == 1)
    flags = {}
    for r in resultats:
        flags[r["flags"] or "ok"] = flags.get(r["flags"] or "ok", 0) + 1
    print("[discrimination] %d fonctions lisibles, %d empreintes distinctes, "
          "%d uniques (%.1f%%)" % (len(lisibles), len(par_body), uniques,
                                   100.0 * uniques / max(1, len(lisibles))))
    print("[drapeaux] " + "  ".join("%s=%d" % (k, v) for k, v in sorted(flags.items())))
    return 0


def cmd_diff(args):
    ea, avant = lire_tsv(Path(args.avant))
    eb, apres = lire_tsv(Path(args.apres))
    ba, bb = ea.get("build", "?"), eb.get("build", "?")
    print("=" * 78)
    print("RAPPORT DE DIFF STRUCTUREL   %s -> %s" % (ba, bb))
    print("=" * 78)
    print("  avant : %6d fonctions (%s)" % (len(avant), args.avant))
    print("  apres : %6d fonctions (%s)" % (len(apres), args.apres))

    ia, ib, communs, amb_a, amb_b = apparier(avant, apres)
    n_fun_a = sum(1 for l in avant if l["sym"].startswith("FUN_"))
    n_fun_b = sum(1 for l in apres if l["sym"].startswith("FUN_"))
    print("\n-- PERIMETRE DE L'APPARIEMENT (ce que la mesure NE couvre PAS) --")
    print("  FUN_* ecartes (nom = adresse, inappariable) : %d avant, %d apres" % (n_fun_a, n_fun_b))
    print("  symboles ambigus ecartes (plusieurs corps)  : %d avant, %d apres"
          % (len(amb_a), len(amb_b)))
    print("  symboles appariables                        : %d avant, %d apres"
          % (len(ia), len(ib)))
    print("  PRESENTS DANS LES DEUX BUILDS               : %d" % len(communs))

    cats = {}
    changes = []
    for s in communs:
        v, detail = classifier(ia[s], ib[s])
        cats[v] = cats.get(v, 0) + 1
        if v == "CORPS_CHANGE":
            changes.append((s, ia[s], ib[s], detail))

    n_comm = max(1, len(communs))
    print("\n-- VERDICT sur les %d symboles communs --" % len(communs))
    for k in ("IDENTIQUE", "CORPS_CHANGE", "ILLISIBLE"):
        if k in cats:
            print("  %-14s %6d  (%5.1f %%)" % (k, cats[k], 100.0 * cats[k] / n_comm))
    print("  %-14s %6d" % ("APPARU", len(set(ib) - set(ia))))
    print("  %-14s %6d" % ("DISPARU", len(set(ia) - set(ib))))

    # Ventilation du changement : DE QUOI est fait le <<corps change>>.
    vent = {}
    for _s, _a, _b, d in changes:
        for tag in d.split(","):
            tag = tag.split(" ")[0]
            vent[tag] = vent.get(tag, 0) + 1
    if vent:
        print("\n-- DE QUOI SONT FAITS LES %d CHANGEMENTS --" % len(changes))
        for k, v in sorted(vent.items(), key=lambda kv: -kv[1]):
            print("  %-16s %6d" % (k, v))

    if args.ecrire:
        p = Path(args.ecrire)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write("#!diff-structurel\tavant=%s\tapres=%s\tcommuns=%d\tchanges=%d\n"
                    % (ba, bb, len(communs), len(changes)))
            f.write("#symbole\tva_avant\tva_apres\tn_ins_avant\tn_ins_apres\tdetail\n")
            for s, a, b, d in sorted(changes, key=lambda t: t[0]):
                f.write("%s\t%x\t%x\t%d\t%d\t%s\n"
                        % (s, a["va"], b["va"], a["n_ins"], b["n_ins"], d))
        print("\n[sortie] %s" % p)

    if args.top:
        print("\n-- %d PLUS GROS CHANGEMENTS (par delta d'instructions) --" % args.top)
        for s, a, b, d in sorted(changes, key=lambda t: -abs(t[1]["n_ins"] - t[2]["n_ins"]))[:args.top]:
            print("  %+5d ins  %-70s %s" % (b["n_ins"] - a["n_ins"], s[:70], d))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("empreinte", help="calcule l'empreinte de chaque fonction d'un build")
    e.add_argument("--build", required=True)
    e.add_argument("--pe", help="chemin du GameAssembly.dll (build courant)")
    e.add_argument("--blocs", help="dossier de blocs extraits par GhidraDumpCodeBytes.java")
    e.add_argument("--functions", help="functions.tsv explicite (defaut: data/symbols/<build>/...)")
    e.add_argument("--out", help="TSV de sortie (defaut: logs/fingerprints/<build>.tsv)")
    e.set_defaults(fn=cmd_empreinte)

    d = sub.add_parser("diff", help="compare deux empreintes")
    d.add_argument("--avant", required=True)
    d.add_argument("--apres", required=True)
    d.add_argument("--ecrire", help="TSV detaille des corps changes")
    d.add_argument("--top", type=int, default=0, help="afficher les N plus gros changements")
    d.set_defaults(fn=cmd_diff)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
