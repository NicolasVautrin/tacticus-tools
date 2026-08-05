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
  cible d'un call/jmp externe          -> `<F>` + l'EMPREINTE de la cible (jamais son nom,
  cible RIP-relative vers du code         cf. l'avertissement de la classe Normaliseur)
  cible RIP-relative vers des donnees  -> `<X>`, un jeton UNIQUE (limite : cf. plus bas)
  adresse absolue dans un immediat     -> le meme traitement que ci-dessus
  branchement INTERNE a la fonction    -> son delta, qui est deja invariant (le corps
                                          se deplace en BLOC, les sauts internes suivent)
                                       registres, mnemoniques, ordre des instructions
                                       offsets de struct (`[rcx + 0xa8]`)
                                       constantes immediates (les formules !)

CINQ COUCHES, PAS UNE -- pour que le diff VENTILE au lieu de dire seulement <<ca a change>> :

  h_local  sha1 du corps PROPRE, references de code anonymisees ... LE VERDICT
  h_body   h_local + l'empreinte de chaque cible referencee ....... corps + appeles
  h_mnem   sha1 de la seule sequence de mnemoniques ............... operandes ignorees
  h_calls  sha1 des empreintes des cibles d'APPEL ................. qui la fonction appelle
  h_imm    sha1 des litteraux conserves ........................... constantes et offsets
  n_ins    nombre d'instructions

`h_local` et `h_body` repondent a deux questions qu'il ne faut pas confondre : <<CE code
a-t-il change ?>> et <<ce code, OU CE QU'IL APPELLE, a-t-il change ?>>. Le second propage d'un
niveau ; seul le premier perime un port. Un `h_mnem` identique avec un `h_local` different dit
<<meme squelette, operandes changees>> : typiquement une constante de formule ou un offset de
struct -- le signal le plus interessant pour un mirror.

CE QUE L'EMPREINTE NE VOIT PAS (limite ASSUMEE, mesuree par la garde)
--------------------------------------------------------------------
Une reference vers une DONNEE (`mov rcx, qword ptr [rip + X]` chargeant un `Il2CppClass*`) est
reduite au jeton unique `<X>` : deux classes differentes donnent le meme jeton. Une fonction
dont SEULE une reference de donnee change est donc un FAUX NEGATIF. On ne peut pas faire mieux
sans une table de symboles de DONNEES par build -- `functions.tsv` ne contient que des
fonctions. La garde `probe_482_empreinte_structurelle.py` (etage 3) mesure ce trou au lieu de
le taire, et rougit s'il S'AGRANDIT.

Ne sont chargees que les sections EXECUTABLES, des deux cotes. C'est un choix de SYMETRIE :
nommer `.rdata` vs `.data` demanderait de charger les sections de donnees, or le dump d'un
build archive n'en extrait pas les octets -- l'asymetrie qui en resulterait fabriquerait des
divergences bien plus couteuses que la finesse gagnee.

DEUX SOURCES D'OCTETS, UN SEUL PIPELINE
---------------------------------------
Le build COURANT a son `GameAssembly.dll` sur disque -> lu par pefile.
Un build ARCHIVE n'existe plus que comme projet Ghidra -> ses octets sont extraits par
`scripts/ghidra/GhidraDumpCodeBytes.java` (analyzeHeadless -readOnly, independant du serveur
ghidra-mcp). Les deux alimentent la MEME normalisation : un ecart mesure ne peut donc pas
venir d'une difference de chaine d'extraction.

ARCHIVER, C'EST LA MOITIE DU DISPOSITIF (#482-r3)
-------------------------------------------------
Les octets d'un build DISPARAISSENT : le lanceur efface `games/<HASH>/` a chaque mise a jour.
`empreinte` calcule ; `archiver` RANGE le resultat sous `data/symbols/<build>/fingerprints/`,
ou il est VERSIONNE et survit a tout. Le capteur qui dit ou en est chaque build --  et par
quelle voie une archive manquante est encore recuperable -- vit dans
`build_fingerprint_archive.py` ; il est branche sur la garde `symbols_sync.py`, elle-meme
declenchee par le hook `SessionStart`.

USAGE
    python fingerprint_functions.py empreinte --build rnca9r7q6c --pe <chemin GameAssembly.dll>
    python fingerprint_functions.py empreinte --build gqfc5mff6c --blocs logs/ghidra-dump/gqfc5mff6c
    python fingerprint_functions.py archiver                       # le build courant, depuis son PE
    python fingerprint_functions.py archiver --build gqfc5mff6c --depuis-ghidra
    python fingerprint_functions.py diff --avant logs/fingerprints/gqfc5mff6c.tsv \\
                                          --apres logs/fingerprints/rnca9r7q6c.tsv
"""
from __future__ import annotations

import argparse
import bisect
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
    langue = ""
    if img_meta.exists():
        for ligne in img_meta.read_text(encoding="utf-8").splitlines():
            if ligne.startswith("imageBase\t"):
                base = int(ligne.split("\t", 1)[1].strip(), 16)
            elif ligne.startswith("language\t"):
                langue = ligne.split("\t", 1)[1].strip()
    # GARDE D'ARCHITECTURE (#482-r3). `empreinter_build` desassemble en x86-64 EN DUR
    # (`Cs(CS_ARCH_X86, CS_MODE_64)`). Sur un binaire d'une autre architecture, capstone ne
    # leve PAS : il rend des instructions plausibles et FAUSSES, donc une empreinte
    # silencieusement fausse -- exactement le mode de panne qu'une empreinte est censee
    # eliminer. Le cas n'est pas theorique : le projet `ghidra_tacticus` porte un
    # `libil2cpp.so` ANDROID (382 405 fonctions, VA a 7 chiffres, 0 symbole en `$$`), et il
    # etait cite comme <<extractible par la meme voie>>.
    # Une langue ABSENTE ne bloque pas : les premiers dumps n'ecrivaient pas le champ, et
    # refuser dessus rejetterait un artefact valable. C'est le REFUS SUR PREUVE, jamais sur
    # silence -- meme discipline que le tri-etat du capteur.
    if langue and not langue.startswith("x86:LE:64"):
        raise SystemExit(
            "ERREUR: %s decrit un binaire '%s', pas du x86-64.\n"
            "  L'empreinte structurelle desassemble en x86-64 EN DUR : sur une autre\n"
            "  architecture capstone ne leve pas, il rend des instructions FAUSSES et\n"
            "  l'empreinte serait silencieusement fausse. Ce build est hors du pipeline."
            % (img_meta, langue))
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
    """Transforme une instruction desassemblee en jeton INVARIANT A LA RELOCATION.

    POURQUOI LE NOM DE LA CIBLE N'EST PAS UTILISABLE -- mesure, pas supposition.
    Une premiere version citait le SYMBOLE de la cible d'appel, par analogie avec la regle
    du depot <<on cite un symbole, jamais une adresse>>. Elle rendait 52 % de corps changes
    entre gqfc5mff6c et rnca9r7q6c, alors que la sequence d'opcodes (`h_mnem`, qui n'utilise
    AUCUN nom) etait identique a 95,0 % : 48 221 fonctions avaient exactement les memes
    opcodes et un `h_body` different.

    La cause est structurelle, et le CLAUDE.md la nomme deja : IL2CPP DEDUPLIQUE les corps.
    Un corps partage par N methodes n'a qu'UN SEUL proprietaire dans la table, et ce
    proprietaire est ARBITRAIRE -- il change d'un dump a l'autre. Mesure ici : 53,5 % des
    fonctions de gqfc et 55,1 % de rnca vivent dans un groupe de corps partage, le plus gros
    groupe comptant 3 196 fonctions. Temoin : `AK.Wwise.BaseType$$GetHashCode` <<appelait>>
    `GooglePlayServices` dans un build et `BurstString.tBigInt$$GetLength` dans l'autre, pour
    108 instructions rigoureusement identiques des deux cotes.

    Un appel se normalise donc par l'EMPREINTE de sa cible, jamais par son nom. Le nom est
    instable ; le corps ne l'est pas. C'est la regle du depot appliquee un cran plus bas :
    ce qui identifie du code, c'est le code.
    """

    def __init__(self, image: ImageCode, par_va: dict, debuts: list):
        self.image = image
        self.par_va = par_va
        self.debuts = debuts            # VA de debut de fonction, TRIEES (recherche binaire)
        self.va_min = image.va_min
        self.va_max = image.va_max
        self.refs = []                  # VA de fonction referencees par l'instruction courante

    def _jeton_cible(self, cible: int) -> str:
        """Une adresse ABSOLUE -> un jeton stable entre builds.

        Une reference vers du CODE devient `<F>` (anonyme) et la VA de la fonction visee est
        accumulee dans `self.refs` : c'est l'appelant qui decidera de la remplacer par
        l'empreinte de la cible. Le jeton lui-meme ne porte donc AUCUN nom.
        """
        if cible in self.par_va:
            self.refs.append(cible)
            return "<F>"
        sect = self.image.nom_section(cible)
        if sect is None:
            return "<X>"                # hors image : import, thunk, donnee non mappee
        seg = self.image.segment_de(cible)
        if seg is not None and self._est_executable(seg):
            # Adresse INTERNE a une fonction (saut dans un corps, table de sauts). On vise la
            # fonction contenante et on garde l'offset, qui est relatif donc stable.
            i = bisect.bisect_right(self.debuts, cible) - 1
            if i >= 0:
                self.refs.append(self.debuts[i])
                return "<F+0x%x>" % (cible - self.debuts[i])
        return "<D:%s>" % sect

    def _est_executable(self, seg):
        # Les segments proviennent de sections/blocs deja filtres sur l'attribut executable.
        return True

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


def _illisible(va, sym, flag):
    """Fonction dont aucun corps n'a pu etre lu. On la RENVOIE quand meme, avec sa raison :
    un symbole absent du fichier de sortie serait indistinguable d'un symbole disparu."""
    return dict(va=va, sym=sym, taille=0, n_ins=0, h_local="-", h_body="-",
                h_mnem="-", h_calls="-", h_imm="-", flags=flag, _refs=(), _appels=())


def empreinter_build(build, image, entrees, par_va, verbose=True, garder_jetons=None):
    """Calcule l'empreinte de chaque fonction. Rend une liste de dicts.

    `garder_jetons` : ensemble de symboles dont on CONSERVE la suite de jetons normalises
    (dans la cle `jetons`). C'est l'outil de DECOMPOSITION PAR ETAGE : quand un diff annonce
    un ecart, on ne le croit pas sur parole -- on regarde quel jeton, exactement, a bouge.
    """
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = False                 # disasm_lite : ~4x plus rapide, suffisant ici
    debuts = [va for va, _s in entrees]
    norm = Normaliseur(image, par_va, debuts)
    resultats = []
    t0 = time.time()
    n = len(entrees)

    for idx, (va, sym) in enumerate(entrees):
        if verbose and idx % 20000 == 0 and idx:
            print("    ... %d/%d fonctions (%.0f s)" % (idx, n, time.time() - t0))
        seg = image.segment_de(va)
        if seg is None:
            resultats.append(_illisible(va, sym, "hors-image"))
            continue
        seg_deb, seg_fin, _nom, data = seg
        borne = entrees[idx + 1][0] if idx + 1 < n else seg_fin
        if borne <= va or borne > seg_fin:
            borne = seg_fin
        borne = min(borne, va + MAX_FN_BYTES)

        code = data[va - seg_deb: borne - seg_deb]
        insns = list(md.disasm_lite(code, va))
        if not insns:
            resultats.append(_illisible(va, sym, "vide"))
            continue

        nb, va_fin, flag = delimiter_corps(insns, va, borne)
        corps = insns[:nb]
        # Le bourrage inter-fonctions n'appartient a personne : on l'ecarte pour que l'empreinte
        # ne bouge pas au gre de l'alignement du voisin.
        while corps and corps[-1][2] in PADDING:
            corps.pop()
        if not corps:
            resultats.append(_illisible(va, sym, "padding"))
            continue

        jetons, mnems, imms = [], [], []
        refs_fn, appels_fn = [], []
        for (addr, size, mnem, ops) in corps:
            norm.refs = []
            j = norm.instruction(addr, size, mnem, ops, va, va_fin)
            jetons.append(j)
            mnems.append(mnem)
            if norm.refs:
                refs_fn.extend(norm.refs)
                if mnem == "call":
                    appels_fn.extend(norm.refs)
            for m in RE_HEX.finditer(j):
                imms.append(m.group(0))

        entree = dict(
            va=va, sym=sym,
            taille=corps[-1][0] + corps[-1][1] - va,
            n_ins=len(corps),
            # h_local : le corps PROPRE, references de code anonymisees. Aucun nom, aucune
            # adresse -- donc rien qui puisse bouger sans que le code ait bouge.
            h_local=sha1_12(jetons),
            h_mnem=sha1_12(mnems),
            h_imm=sha1_12(imms) if imms else "-",
            flags=flag,
            _refs=tuple(refs_fn),
            _appels=tuple(appels_fn),
        )
        if garder_jetons is not None and sym in garder_jetons:
            entree["jetons"] = jetons
        resultats.append(entree)

    # -- SECONDE PASSE : resoudre chaque reference de code par l'EMPREINTE de sa cible.
    #    C'est ce qui remplace le nom (instable a cause de la deduplication IL2CPP) par
    #    quelque chose qui ne bouge que si le code bouge.
    local_par_va = {r["va"]: r["h_local"] for r in resultats}
    for r in resultats:
        if r["h_local"] == "-":
            r["h_body"] = r["h_calls"] = "-"
            continue
        refs = [local_par_va.get(v, "?") for v in r["_refs"]]
        r["h_body"] = sha1_12([r["h_local"]] + refs)
        app = [local_par_va.get(v, "?") for v in r["_appels"]]
        r["h_calls"] = sha1_12(app) if app else "-"
        del r["_refs"], r["_appels"]
    if verbose:
        print("    %d fonctions empreintees en %.0f s" % (n, time.time() - t0))
    return resultats


COLONNES = ["va", "sym", "taille", "n_ins", "h_local", "h_body", "h_mnem", "h_calls",
            "h_imm", "flags"]


def ecrire_tsv(chemin: Path, build: str, image: ImageCode, resultats, sha256: str = ""):
    """`sha256` = celui du binaire d'origine. Il VOYAGE DANS l'artefact, comme la provenance
    des tables Frida : un fichier range sous le mauvais build se detecte alors par son
    CONTENU et non par son emplacement. Cote PE il est mesure par `sha256_of` ; cote build
    archive il vient du champ `executableSHA256` qu'ecrit Ghidra dans `image.meta` -- deux
    chaines independantes de celle qui estampille `frida/methods.tsv`, ce qui rend leur
    accord verifiable (`build_fingerprint_archive._sha_attendu`)."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "w", encoding="utf-8", newline="\n") as f:
        f.write("#!empreinte-structurelle\tbuild=%s\torigine=%s\tfonctions=%d\tgenere=%s"
                "\tsha256=%s\n"
                % (build, image.origine, len(resultats),
                   time.strftime("%Y-%m-%dT%H:%M:%S"), sha256))
        f.write("#" + "\t".join(COLONNES) + "\n")
        for r in resultats:
            f.write("%x\t%s\t%d\t%d\t%s\t%s\t%s\t%s\t%s\t%s\n" % (
                r["va"], r["sym"], r["taille"], r["n_ins"], r["h_local"],
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
                           h_local=c[4], h_body=c[5], h_mnem=c[6], h_calls=c[7],
                           h_imm=c[8], flags=c[9] if len(c) > 9 else ""))
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
    """Ventile un couple (avant, apres) apparie. Rend (verdict, detail).

    TROIS verdicts, pas deux -- parce que <<ce code a change>> et <<ce que ce code APPELLE a
    change>> sont deux questions differentes, et les confondre rend le rapport inutilisable :

      IDENTIQUE       le corps propre ET tout ce qu'il appelle sont inchanges
      APPELES_CHANGES le corps propre est BIT A BIT le meme ; une de ses cibles a change.
                      Propagation d'un niveau, pas une reecriture de cette fonction-ci.
      CORPS_CHANGE    le corps propre lui-meme a change. C'EST le signal qui perime un port.
    """
    if a["h_local"] == "-" or b["h_local"] == "-":
        return "ILLISIBLE", a["flags"] or b["flags"] or "?"
    if a["h_local"] != b["h_local"]:
        quoi = []
        if a["n_ins"] != b["n_ins"]:
            quoi.append("n_ins %d->%d" % (a["n_ins"], b["n_ins"]))
        if a["h_mnem"] != b["h_mnem"]:
            quoi.append("opcodes")
        if a["h_imm"] != b["h_imm"]:
            quoi.append("litteraux")
        if a["h_mnem"] == b["h_mnem"]:
            # Meme squelette d'instructions, operandes differentes : le signal le plus utile
            # pour un port (une constante de formule ou un offset de struct a bouge).
            quoi.append("MEME-SQUELETTE")
        return "CORPS_CHANGE", ",".join(quoi) if quoi else "operandes"
    if a["h_body"] != b["h_body"]:
        return "APPELES_CHANGES", "appels" if a["h_calls"] != b["h_calls"] else "refs"
    return "IDENTIQUE", ""


def sha256_du_fichier(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for bloc in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def sha256_de_source(pe: str | None, blocs: str | None) -> str:
    """sha256 du binaire d'ORIGINE, quelle que soit la voie d'extraction.

    Voie PE     : mesure directe du fichier.
    Voie blocs  : `image.meta:executableSHA256`, ecrit par Ghidra a l'import -- la SEULE
                  trace de provenance qui survive a la disparition du `.dll`.
    Rend "" si aucune des deux ne repond ; c'est a l'appelant de decider s'il refuse.
    """
    if pe:
        return sha256_du_fichier(Path(pe))
    if blocs:
        meta = Path(blocs) / "image.meta"
        if meta.exists():
            for ligne in meta.read_text(encoding="utf-8").splitlines():
                if ligne.startswith("executableSHA256\t"):
                    return ligne.split("\t", 1)[1].strip()
    return ""


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
    ecrire_tsv(sortie, build, image, resultats, sha256=sha256_de_source(args.pe, args.blocs))
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
    for k in ("IDENTIQUE", "APPELES_CHANGES", "CORPS_CHANGE", "ILLISIBLE"):
        if k in cats:
            print("  %-16s %6d  (%5.1f %%)" % (k, cats[k], 100.0 * cats[k] / n_comm))
    print("  %-16s %6d" % ("APPARU", len(set(ib) - set(ia))))
    print("  %-16s %6d" % ("DISPARU", len(set(ia) - set(ib))))

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

    # -- FAUX POSITIF RESIDUEL, mesure et non estime.
    # L'appariement se fait par NOM. Or IL2CPP deduplique les corps : quand un corps est
    # partage par plusieurs symboles, celui qui en est le <<proprietaire>> dans la table est
    # ARBITRAIRE et peut changer d'un dump a l'autre. Comparer un tel nom revient alors a
    # comparer deux corps sans rapport -- un changement fabrique de toutes pieces.
    # Quand le corps est UNIQUE dans les deux builds, l'appariement par nom est sur.
    mult_a, mult_b = {}, {}
    for l in avant:
        mult_a[l["h_local"]] = mult_a.get(l["h_local"], 0) + 1
    for l in apres:
        mult_b[l["h_local"]] = mult_b.get(l["h_local"], 0) + 1
    sur = douteux = 0
    for _s, a, b, _d in changes:
        if mult_a.get(a["h_local"], 0) == 1 and mult_b.get(b["h_local"], 0) == 1:
            sur += 1
        else:
            douteux += 1
    n_ch = max(1, len(changes))
    print("\n-- FIABILITE DE L'APPARIEMENT des %d changements --" % len(changes))
    print("  corps UNIQUE des deux cotes (appariement sur)   : %6d  (%5.1f %%)"
          % (sur, 100.0 * sur / n_ch))
    print("  corps PARTAGE d'au moins un cote (nom arbitraire): %6d  (%5.1f %%)"
          % (douteux, 100.0 * douteux / n_ch))
    print("  -> le second groupe est la borne HAUTE du faux positif residuel.")

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


# ===========================================================================
# 4bis. ARCHIVER -- ranger l'empreinte la ou elle survit a la disparition du binaire
# ===========================================================================
def _analyze_headless() -> Path | None:
    """`analyzeHeadless.bat`, ou None. `GHIDRA_INSTALL_DIR` prime ; sinon on cherche par GLOB
    sous `~` -- surtout pas un numero de version en dur, qui se perimerait a la prochaine
    mise a jour de Ghidra et ferait rendre <<introuvable>> pour une installation presente."""
    import os
    racine = os.environ.get("GHIDRA_INSTALL_DIR")
    candidats = [Path(racine)] if racine else sorted(Path.home().glob("ghidra_*_PUBLIC"),
                                                     reverse=True)
    for c in candidats:
        bat = c / "support" / "analyzeHeadless.bat"
        if bat.is_file():
            return bat
    return None


def _dumper_blocs_ghidra(build: str, dest: Path) -> Path:
    """Extrait les octets d'un build ARCHIVE depuis son projet Ghidra, en `-readOnly`.

    `-readOnly` + `-noanalysis` : on ne modifie JAMAIS un projet archive, et le verrou d'un
    projet est propre a CE projet -- lancer ceci pendant que ghidra-mcp sert un AUTRE build
    ne les met pas en concurrence (c'est ce qui a rendu la confrontation de #482 possible).

    Toute impossibilite est NOMMEE et fait lever : un dump silencieusement vide produirait
    une empreinte fausse, ce qui est pire que pas d'empreinte.
    """
    import subprocess

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_fingerprint_archive as A

    projet = A.projet_ghidra(build)
    if projet is None:
        if not A.projets_mesurables():
            raise SystemExit(
                "REFUS: la racine des projets Ghidra (%s) est illisible -- recuperabilite\n"
                "  NON MESUREE. On ne conclut pas 'perdu' d'un capteur muet."
                % A.racine_projets_ghidra())
        raise SystemExit(
            "REFUS: aucun projet Ghidra 'ghidra_%s' sous %s.\n"
            "  Le binaire a disparu et le projet aussi : les corps de ce build ne sont plus\n"
            "  nulle part. L'empreinte n'est PAS recuperable." % (build, A.racine_projets_ghidra()))

    bat = _analyze_headless()
    if bat is None:
        raise SystemExit(
            "REFUS: analyzeHeadless introuvable (ni GHIDRA_INSTALL_DIR, ni ~/ghidra_*_PUBLIC).\n"
            "  Poser GHIDRA_INSTALL_DIR, ou produire les blocs a la main puis relancer avec\n"
            "  --blocs <dossier> :\n"
            "    analyzeHeadless <projet> gameassembly -process GameAssembly.dll -noanalysis\n"
            "      -readOnly -scriptPath scripts/ghidra -postScript GhidraDumpCodeBytes.java <out>")

    dest.mkdir(parents=True, exist_ok=True)
    cmd = [str(bat), str(projet), "gameassembly",
           "-process", "GameAssembly.dll", "-noanalysis", "-readOnly",
           "-scriptPath", str(REPO / "scripts" / "ghidra"),
           "-postScript", "GhidraDumpCodeBytes.java", str(dest)]
    print("[ghidra] %s (readOnly) -> %s" % (projet.name, dest))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if not (dest / "blocks.meta").is_file():
        queue = (r.stdout or "")[-1500:] + (r.stderr or "")[-1500:]
        raise SystemExit("REFUS: le dump Ghidra n'a produit aucun blocks.meta (rc=%d).\n%s"
                         % (r.returncode, queue))
    return dest


def cmd_archiver(args):
    """Calcule l'empreinte d'un build et la RANGE sous `data/symbols/<build>/fingerprints/`.

    LA SOURCE SE CHOISIT TOUTE SEULE, et l'ordre porte le sens : le PE d'abord (le moins
    cher, et c'est le regime du build COURANT -- celui qu'il faut archiver AVANT qu'il ne
    devienne sortant), le projet Ghidra ensuite (le rattrapage d'un build deja disparu).
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_fingerprint_archive as A
    from symbols_layout import current_build

    build = args.build or current_build()
    cible = A.archive_path(build)
    if cible.is_file() and not args.force:
        raise SystemExit(
            "REFUS: %s existe deja.\n"
            "  Une archive d'empreinte est une ENTREE, pas une sortie de run : on ne la\n"
            "  recalcule pas par habitude. --force pour l'ecraser volontairement."
            % cible.relative_to(REPO).as_posix())

    pe = blocs = None
    if args.blocs:
        blocs = args.blocs
    elif args.depuis_ghidra:
        blocs = str(_dumper_blocs_ghidra(build, REPO / "logs" / "ghidra-dump" / build))
    else:
        from il2cpp_provenance import GAMES_DIR
        cand = GAMES_DIR / build / "GameAssembly.dll"
        if cand.is_file():
            pe = str(cand)
        else:
            etat = A.etat_archive(build)
            raise SystemExit(
                "REFUS: pas de GameAssembly.dll pour '%s' sous %s.\n"
                "  etat mesure : %s -- %s\n"
                "  Voie de rattrapage : --depuis-ghidra (ou --blocs <dossier>)."
                % (build, GAMES_DIR, etat.etat, etat.detail))

    image = charger_depuis_pe(Path(pe)) if pe else charger_depuis_blocs(Path(blocs))
    print("[image] %s" % build)
    print(image.resume())

    sha = sha256_de_source(pe, blocs)
    if not sha:
        raise SystemExit(
            "REFUS: sha256 du binaire d'origine introuvable -- l'archive serait de\n"
            "  PROVENANCE INCONNUE, donc invalidable. Voie PE : le fichier lui-meme ;\n"
            "  voie blocs : le champ executableSHA256 de image.meta (re-dumper avec\n"
            "  GhidraDumpCodeBytes.java a jour).")

    entrees, par_va = charger_functions_tsv(build)
    print("[symboles] %d entrees dans functions.tsv" % len(entrees))
    resultats = empreinter_build(build, image, entrees, par_va)
    ecrire_tsv(cible, build, image, resultats, sha256=sha)

    etat = A.etat_archive(build)
    print("[archive] %s" % cible.relative_to(REPO).as_posix())
    print("[verdict] %s -- %s" % (etat.etat, etat.detail))
    if etat.etat != A.ARCHIVEE:
        print("ECHEC: l'archive vient d'etre ecrite et le capteur la refuse deja.")
        return 1
    print("[git]     git add %s" % cible.relative_to(REPO).as_posix())
    print("          Une archive non COMMITEE n'est protegee par RIEN : `git clean` et un")
    print("          `worktree remove --force` l'effacent sans trace.")
    return 0


RE_SYMBOLE_CITE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*\$\$[A-Za-z_.][A-Za-z0-9_.]*")


def cmd_impact(args):
    """Croise le diff avec les symboles que le DEPOT CITE -- <<est-ce que ca tombe sur des
    fonctions qu'on a portees ?>>.

    Un changement de corps n'a de cout que s'il touche quelque chose qu'on a mirrore. Le
    depot cite ses fonctions natives sous la forme `Classe$$Methode` (c'est la regle <<on
    cite un SYMBOLE, jamais une adresse>>), ce qui rend ce croisement possible par simple
    lecture des sources.
    """
    cites = {}
    racines = [REPO / d for d in args.racines]
    exts = {".py", ".md", ".ts", ".java", ".json", ".sql"}
    for racine in racines:
        if not racine.exists():
            continue
        for p in racine.rglob("*"):
            if p.suffix not in exts or not p.is_file():
                continue
            try:
                txt = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in RE_SYMBOLE_CITE.finditer(txt):
                cites.setdefault(m.group(0), set()).add(str(p.relative_to(REPO)))
    print("[citations] %d symboles natifs distincts cites dans %s"
          % (len(cites), ", ".join(args.racines)))

    changes = {}
    for ligne in Path(args.diff).read_text(encoding="utf-8").splitlines():
        if ligne.startswith("#"):
            continue
        c = ligne.split("\t")
        changes[c[0]] = c

    touches = sorted(set(cites) & set(changes))
    print("[impact] %d symboles CITES par le depot ont un CORPS CHANGE" % len(touches))
    if not touches:
        print("  (aucun -- mais verifier que le diff porte bien sur les bons builds)")
        return 0
    print()
    for s in touches:
        c = changes[s]
        fichiers = sorted(cites[s])
        print("  %-72s %s" % (s[:72], c[5] if len(c) > 5 else ""))
        print("      n_ins %s -> %s   cite par : %s%s"
              % (c[3], c[4], ", ".join(fichiers[:3]),
                 " (+%d)" % (len(fichiers) - 3) if len(fichiers) > 3 else ""))
    return 0


def charger_source(chemin: str) -> ImageCode:
    """Un dossier -> blocs Ghidra ; un fichier -> PE. Une seule facon de designer un build."""
    p = Path(chemin)
    return charger_depuis_blocs(p) if p.is_dir() else charger_depuis_pe(p)


def jetons_de(build, source, symboles):
    """Rend {symbole: [jetons]} pour un build donne."""
    image = charger_source(source)
    entrees, par_va = charger_functions_tsv(build)
    voulus = set(symboles)
    cibles = [(va, s) for (va, s) in entrees if s in voulus]
    # `entrees` COMPLET reste necessaire : le normaliseur resout les cibles d'appel par la
    # table entiere, et les bornes de fonction dependent du voisin immediat.
    index = {va: i for i, (va, _s) in enumerate(entrees)}
    out = {}
    for va, s in cibles:
        i = index[va]
        tranche = entrees[i:i + 2] if i + 1 < len(entrees) else entrees[i:i + 1]
        r = empreinter_build(build, image, tranche, par_va, verbose=False,
                             garder_jetons=voulus)[0]
        out[s] = r.get("jetons", [])
    return out


def cmd_enqueter(args):
    """Diff des JETONS d'un symbole entre deux builds -- l'outil de decomposition.

    Un verdict `CORPS_CHANGE` ne se croit pas sur parole : on regarde QUEL jeton a bouge.
    C'est ce qui distingue un vrai changement de code d'un artefact de la normalisation.
    """
    ba, sa = args.avant.split("=", 1)
    bb, sb = args.apres.split("=", 1)
    symboles = args.symbole
    ja = jetons_de(ba, sa, symboles)
    jb = jetons_de(bb, sb, symboles)

    for s in symboles:
        a, b = ja.get(s, []), jb.get(s, [])
        print("=" * 78)
        print("%s" % s)
        print("  %s : %d instructions      %s : %d instructions" % (ba, len(a), bb, len(b)))
        import difflib
        diff = list(difflib.unified_diff(a, b, lineterm="", n=args.contexte,
                                         fromfile=ba, tofile=bb))
        if not diff:
            print("  JETONS IDENTIQUES")
            continue
        montre = diff if args.tout else diff[:args.limite]
        for l in montre:
            print("  " + l)
        if not args.tout and len(diff) > args.limite:
            print("  ... (%d lignes de diff en tout, --tout pour les voir)" % len(diff))
    return 0


def cmd_ventiler(args):
    """Agrege, sur un ECHANTILLON de symboles changes, la NATURE des jetons qui different.

    Repond a la question qu'un pourcentage global ne peut pas trancher : <<ces 52 % sont-ils
    du vrai changement de code, ou un artefact de ma normalisation ?>>
    """
    ba, sa = args.avant.split("=", 1)
    bb, sb = args.apres.split("=", 1)
    _e, changes = [], []
    for ligne in Path(args.diff).read_text(encoding="utf-8").splitlines():
        if ligne.startswith("#"):
            continue
        changes.append(ligne.split("\t")[0])
    # Echantillon DETERMINISTE (pas de hasard : la mesure doit se rejouer a l'identique).
    pas = max(1, len(changes) // args.n)
    ech = changes[::pas][:args.n]
    print("[echantillon] %d symboles sur %d changes (pas=%d)" % (len(ech), len(changes), pas))

    ja = jetons_de(ba, sa, ech)
    jb = jetons_de(bb, sb, ech)

    import difflib
    familles = {}
    exemples = {}
    n_lignes = 0
    for s in ech:
        a, b = ja.get(s, []), jb.get(s, [])
        sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            for x in range(i1, i2):
                fam = _famille_jeton(a[x])
                familles[fam] = familles.get(fam, 0) + 1
                exemples.setdefault(fam, []).append((s, a[x], "-"))
                n_lignes += 1
            for y in range(j1, j2):
                fam = _famille_jeton(b[y])
                familles[fam] = familles.get(fam, 0) + 1
                exemples.setdefault(fam, []).append((s, b[y], "+"))
                n_lignes += 1

    print("\n-- NATURE des %d jetons qui different --" % n_lignes)
    for k, v in sorted(familles.items(), key=lambda kv: -kv[1]):
        print("  %-28s %6d  (%5.1f %%)" % (k, v, 100.0 * v / max(1, n_lignes)))
    if args.exemples:
        print("\n-- EXEMPLES par famille --")
        for k in sorted(familles, key=lambda k: -familles[k]):
            print("  [%s]" % k)
            for s, j, sens in exemples[k][:args.exemples]:
                print("    %s %-58s  %s" % (sens, j[:58], s[:44]))
    return 0


def _famille_jeton(j: str) -> str:
    """Classe un jeton par CE QUI POURRAIT AVOIR BOUGE -- pas par son mnemonique."""
    if "<F+" in j:
        return "ref INTERNE a une fonction"
    if "<F>" in j:
        return "appel/ref vers du CODE"
    if "<D:" in j:
        return "reference vers DONNEE"
    if "<X>" in j:
        return "reference HORS IMAGE"
    if RE_HEX.search(j):
        return "litteral conserve (const/offset)"
    if j.split(" ")[0] in BRANCHES:
        return "branchement interne"
    return "instruction pure (registres)"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("enqueter", help="diff des jetons d'un symbole entre deux builds")
    q.add_argument("--avant", required=True, help="<build>=<pe ou dossier de blocs>")
    q.add_argument("--apres", required=True, help="<build>=<pe ou dossier de blocs>")
    q.add_argument("--symbole", required=True, nargs="+")
    q.add_argument("--limite", type=int, default=60)
    q.add_argument("--contexte", type=int, default=2)
    q.add_argument("--tout", action="store_true")
    q.set_defaults(fn=cmd_enqueter)

    v = sub.add_parser("ventiler", help="nature des jetons qui different, sur un echantillon")
    v.add_argument("--avant", required=True)
    v.add_argument("--apres", required=True)
    v.add_argument("--diff", required=True, help="TSV produit par `diff --ecrire`")
    v.add_argument("--n", type=int, default=200)
    v.add_argument("--exemples", type=int, default=0)
    v.set_defaults(fn=cmd_ventiler)

    i = sub.add_parser("impact", help="quels symboles CITES par le depot ont un corps change")
    i.add_argument("--diff", required=True, help="TSV produit par `diff --ecrire`")
    i.add_argument("--racines", nargs="+",
                   default=["engine", "docs", "scripts", "frida/hooks"])
    i.set_defaults(fn=cmd_impact)

    e = sub.add_parser("empreinte", help="calcule l'empreinte de chaque fonction d'un build")
    e.add_argument("--build", required=True)
    e.add_argument("--pe", help="chemin du GameAssembly.dll (build courant)")
    e.add_argument("--blocs", help="dossier de blocs extraits par GhidraDumpCodeBytes.java")
    e.add_argument("--functions", help="functions.tsv explicite (defaut: data/symbols/<build>/...)")
    e.add_argument("--out", help="TSV de sortie (defaut: logs/fingerprints/<build>.tsv)")
    e.set_defaults(fn=cmd_empreinte)

    a = sub.add_parser("archiver",
                       help="calcule l'empreinte et la RANGE sous data/symbols/<build>/fingerprints/")
    a.add_argument("--build", help="defaut : le build courant (data/symbols/CURRENT)")
    a.add_argument("--depuis-ghidra", action="store_true",
                   help="build deja disparu : extraire ses octets de son projet Ghidra")
    a.add_argument("--blocs", help="reutiliser un dump de blocs deja produit")
    a.add_argument("--force", action="store_true", help="ecraser une archive existante")
    a.set_defaults(fn=cmd_archiver)

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
