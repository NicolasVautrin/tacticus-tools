#!/usr/bin/env python3
"""FOYER UNIQUE des artefacts du build du jeu, pour toute analyse OFFLINE (#431).

POURQUOI CE MODULE EXISTE
-------------------------
`CLAUDE.md` prescrit depuis longtemps : « si le hash installe et le hash du dump ne
matchent pas, REFUSER l'analyse offline ». La prescription etait tenue par les artefacts
CENTRAUX (`symbols_sync.py` axe 1 compare le sha256 du binaire installe aux estampilles
des tables versionnees) -- mais elle ne tenait RIEN au POINT D'USAGE. Un script qui ecrit

    GAME_DLL = Path(r"C:\\Users\\...\\tacticus\\games\\gqfc5mff6c\\GameAssembly.dll")

ne consulte ni `data/symbols/CURRENT` ni le binaire installe : `symbols_sync` peut etre
VERT, il lira quand meme le mauvais build. Mesure du 2026-08-01 : CINQ probes etaient
dans cet etat.

LES TROIS AXES D'EPINGLAGE, ET POURQUOI LES TRAITER ENSEMBLE
------------------------------------------------------------
Un probe offline lit trois choses, et chacune est datee du build :

  1. le BINAIRE  (`GameAssembly.dll`) ;
  2. la TABLE de symboles (`data/symbols/<build>/ghidra/functions.tsv`) ;
  3. des VA / ordinaux TRANSCRITS A LA MAIN depuis ghidra (call-sites, thunks, temoins).

Corriger le seul axe 1 -- « que le probe resolve sa DLL par le build COURANT » -- est une
REGRESSION quand l'axe 3 est epingle : le probe passe de « echoue franchement » a
« mesure faux en silence ». MESURE, et c'est le coeur du cas :

  * les 55 call-sites transcrits de `probe_88_event_emitters` resolvent 55/55 contre la
    table `gqfc5mff6c` et 0/55 contre `rnca9r7q6c` -- chacun tombe dans une fonction d'UI
    sans rapport (`idun.ui.UnitDeploymentHud$$...`), avec un decodage d'immediat
    parfaitement plausible a la sortie ;
  * les thunks de publication ont DEPLACE : `0x180026490` (debut de fonction sur
    `gqfc5mff6c`) tombe a `FUN_180026460+0x30` sur `rnca9r7q6c`.

D'ou l'API : on ne rend JAMAIS un chemin de binaire sans avoir verifie que le build
installe == `data/symbols/CURRENT`, et un porteur de valeurs transcrites DECLARE son
build (`require_pinned`) -- il est refuse des que la declaration ne colle plus.

REFUSER, PAS DEGRADER
---------------------
Toute impossibilite leve `BuildPinRefused`. Un appelant qui veut sortir proprement
attrape et imprime -- le vocabulaire du depot est `NON MESURE`. Ce qu'on ne fait jamais :
retomber sur « le seul autre build present », deviner, ou rendre un resultat vide qui se
lira comme une mesure.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import bisect
import os
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "python") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "python"))

from il2cpp_provenance import installed_builds  # noqa: E402
from symbols_layout import LayoutError, build_dir, current_build  # noqa: E402

__all__ = [
    "BuildPinRefused",
    "SymbolIndex",
    "archived_build",
    "functions_tsv",
    "game_dll",
    "global_metadata",
    "install_dir",
    "installed_build",
    "load_dll",
    "pe_sections",
    "require_pinned",
    "va_to_file_offset",
    "versioned_build",
]

DLL_NAME = "GameAssembly.dll"


class BuildPinRefused(RuntimeError):
    """Analyse offline REFUSEE : le build ne peut pas etre etabli, ou il a bouge.

    Levee a la place d'un chemin/resultat. « Je ne peux pas mesurer » et « j'ai mesure,
    c'est vide » ne doivent jamais rendre la meme chose -- c'est la meme discipline
    tri-etat que `host_inputs.HostInputUnavailable`, sur l'autre gisement d'entrees
    (celles qui vivent hors du depot, sous `%LOCALAPPDATA%`).
    """


# ----------------------------------------------------------------- les deux hashes


def installed_build() -> str:
    """Nom du build INSTALLE sur la machine. Refuse si 0 ou plusieurs (ambigu)."""
    try:
        builds = [b for b in installed_builds() if (b / DLL_NAME).is_file()]
    except OSError as exc:                                          # noqa: BLE001
        raise BuildPinRefused("installation Tacticus illisible : %s" % exc) from exc
    if not builds:
        raise BuildPinRefused(
            "NON MESURE : aucun build Tacticus installe ne porte %s.\n"
            "  Le binaire est une ENTREE hors depot (%%LOCALAPPDATA%%/tacticus/games/<hash>/) :\n"
            "  absent, il n'y a rien a mesurer -- et surtout pas 'zero occurrence'." % DLL_NAME)
    if len(builds) > 1:
        raise BuildPinRefused(
            "PLUSIEURS builds installes (%s) : lequel est courant ? On ne devine PAS."
            % ", ".join(b.name for b in builds))
    return builds[0].name


def versioned_build() -> str:
    """Nom du build qui FAIT FOI dans le depot (`data/symbols/CURRENT`)."""
    try:
        return current_build()
    except LayoutError as exc:
        raise BuildPinRefused(str(exc)) from exc


def _assert_same(installed: str, versioned: str) -> None:
    if installed == versioned:
        return
    raise BuildPinRefused(
        "DESYNCHRONISATION build installe / tables versionnees -- analyse offline REFUSEE.\n"
        "  installe (%%LOCALAPPDATA%%/tacticus/games/) : %s\n"
        "  data/symbols/CURRENT                      : %s\n"
        "  Toute adresse lue dans l'un et resolue dans l'autre est FAUSSE, et d'apparence\n"
        "  propre. Remettre a niveau AVANT de mesurer : CLAUDE.md, « Hash du build = identite\n"
        "  du dump », puis `python scripts/python/symbols_sync.py`." % (installed, versioned))


# -------------------------------------------------------------------- les artefacts


def game_dll() -> Path:
    """`GameAssembly.dll` du build installe, SEULEMENT s'il est celui qui fait foi.

    Le double controle est le point du module : rendre la DLL installee sans verifier
    qu'elle correspond aux tables versionnees, c'est exactement le montage ou l'on
    decompile un binaire en citant les symboles d'un autre.
    """
    inst = installed_build()
    _assert_same(inst, versioned_build())
    p = Path.home() / "AppData" / "Local" / "tacticus" / "games" / inst / DLL_NAME
    if not p.is_file():                                  # course entre le listing et l'ouverture
        raise BuildPinRefused("NON MESURE : %s a disparu entre le listing et la lecture" % p)
    return p


def functions_tsv(build: str | None = None) -> Path:
    """`data/symbols/<build>/ghidra/functions.tsv` (defaut : le build qui fait foi)."""
    try:
        p = build_dir(build) / "ghidra" / "functions.tsv"
    except LayoutError as exc:
        raise BuildPinRefused(str(exc)) from exc
    if not p.is_file():
        raise BuildPinRefused(
            "table Ghidra absente : %s\n"
            "  L'extraire : python scripts/python/ghidra_symbols.py dump" % p.as_posix())
    return p


def global_metadata() -> Path:
    """`global-metadata.dat` du build installe, SEULEMENT s'il est celui qui fait foi.

    Pendant exact de `game_dll()` sur l'AUTRE moitie d'un build IL2CPP. Le binaire porte
    le CODE, le metadata porte la STRUCTURE -- dont le champ `slot` des `MethodInfo`, seul
    endroit ou se lit le rang d'une methode dans la table d'une interface. Une interface
    n'ayant aucun corps, ce rang est INVISIBLE au decompile et absent de
    `data/symbols/<build>/frida/methods.tsv` (indexee par adresse) : sans ce fichier, un
    slot ne se reconstruit que par recoupement -- c'est ce qui a produit #477-r24-r1.

    Meme double controle et meme tri-etat que `game_dll()` : on ne lit JAMAIS le metadata
    d'un build en citant les symboles d'un autre.
    """
    inst = installed_build()
    _assert_same(inst, versioned_build())
    p = (Path.home() / "AppData" / "Local" / "tacticus" / "games" / inst
         / "Tacticus_Data" / "il2cpp_data" / "Metadata" / "global-metadata.dat")
    if not p.is_file():
        raise BuildPinRefused(
            "NON MESURE : le metadata IL2CPP du build %s est introuvable (%s).\n"
            "  C'est une ENTREE hors depot, comme le binaire : absente, il n'y a rien a\n"
            "  mesurer -- et surtout pas 'zero slot'." % (inst, p))
    return p


def install_dir(strict: bool = True) -> Path | None:
    """Racine d'installation du jeu (bundles, StreamingAssets, binaire).

    `TACTICUS_INSTALL` reste l'echappatoire (installation deplacee, copie d'archive) ;
    a defaut, c'est le build INSTALLE -- jamais un hash ecrit en dur, qui devient un
    repertoire inexistant a la premiere mise a jour du jeu.

    `strict=False` rend `None` au lieu de lever, pour les outils qui ont un REPLI legitime
    (`build_asset_manifest` retombe sur un pull d'assets). `None` doit alors etre traite
    comme tel : c'est « pas d'installation », pas « installation vide ».
    """
    env = os.environ.get("TACTICUS_INSTALL")
    if env:
        return Path(env)
    try:
        return Path.home() / "AppData" / "Local" / "tacticus" / "games" / installed_build()
    except BuildPinRefused:
        if strict:
            raise
        return None


# ----------------------------------------------------------- valeurs TRANSCRITES A LA MAIN


def archived_build(name: str, what: str) -> str:
    """Un build de REFERENCE, DELIBEREMENT anterieur (diff inter-build, migration).

    Ce n'est pas la meme demande que `require_pinned` : ici on veut EXPRESSEMENT un autre
    build que l'installe -- c'est le sens meme d'un diff. Ce qu'on verifie, c'est que sa
    table est encore VERSIONNEE : sans elle, l'outil ne compare a rien et son « aucune
    difference » se lit comme un resultat.

    Le litteral reste ecrit a la main, et c'est correct : un build de reference est une
    donnee du CAS, pas de la machine. Ce qui change, c'est qu'il est desormais CONTROLE --
    et c'est ce qui le distingue, pour le cliquet `probe_431`, d'un chemin perime.
    """
    p = REPO / "data" / "symbols" / name
    if p.is_dir():
        return name
    dispo = sorted(d.name for d in (REPO / "data" / "symbols").iterdir() if d.is_dir())
    raise BuildPinRefused(
        "NON MESURE : le build de REFERENCE '%s' n'est plus versionne.\n"
        "  a quoi il sert ici : %s\n"
        "  builds versionnes  : %s\n"
        "  Les archives sont conservees EXPRES (leur diff EST le rapport de changement du\n"
        "  jeu). Si celle-ci a ete supprimee, la comparaison n'a plus de reference -- on le\n"
        "  DIT, on ne rend pas un diff vide." % (name, what, ", ".join(dispo) or "aucun"))


def require_pinned(pinned_build: str, what: str, how: str = "") -> str:
    """Autorise l'usage de valeurs LUES A LA MAIN dans ghidra contre `pinned_build`.

    C'est le seul axe qu'aucun balayage du depot ne peut deriver : la source est HORS
    depot (une session ghidra, un `list_xrefs` recopie). Le porteur declare donc son
    build, et ce foyer le confronte au build installe.

    Rend le build (pour l'imprimer) ; leve `BuildPinRefused` des qu'il a bouge -- avec
    `how`, la procedure de re-derivation, sinon le refus est un cul-de-sac.
    """
    inst = installed_build()
    if inst == pinned_build:
        return inst
    msg = [
        "NON MESURE : valeurs epinglees sur un AUTRE build -- refus de mesurer faux.",
        "  epinglees sur : %s" % pinned_build,
        "  build installe : %s" % inst,
        "  ce qui est epingle : %s" % what,
        "  Ces valeurs ont ete TRANSCRITES A LA MAIN depuis ghidra ; aucune ne survit a un",
        "  changement de build (mesure : 55 call-sites, 55/55 justes sur leur build d'origine,",
        "  0/55 sur le suivant -- et le decodage rend quand meme un resultat plausible).",
    ]
    if how:
        msg.append("  RE-DERIVER : %s" % how)
    raise BuildPinRefused("\n".join(msg))


# ---------------------------------------------------------------------- PE + symboles


def pe_sections(buf: bytes) -> tuple[int, list[tuple[str, int, int, int, int]]]:
    """(image_base, [(nom, vaddr, vsize, praw, rawsz)]) d'un PE64 en memoire.

    Mutualise : quatre des cinq probes de #431 en portaient leur propre copie, a la
    virgule pres. Une copie de plus, c'est une occasion de plus de diverger.
    """
    pe = struct.unpack_from("<I", buf, 0x3C)[0]
    if buf[pe:pe + 4] != b"PE\x00\x00":
        raise BuildPinRefused("NON MESURE : le fichier n'est pas un PE (signature absente)")
    n_sec = struct.unpack_from("<H", buf, pe + 6)[0]
    opt_size = struct.unpack_from("<H", buf, pe + 20)[0]
    image_base = struct.unpack_from("<Q", buf, pe + 24 + 24)[0]
    sec_off = pe + 24 + opt_size
    out = []
    for i in range(n_sec):
        o = sec_off + i * 40
        out.append((buf[o:o + 8].rstrip(b"\x00").decode("ascii", "replace"),
                    struct.unpack_from("<I", buf, o + 12)[0],
                    struct.unpack_from("<I", buf, o + 8)[0],
                    struct.unpack_from("<I", buf, o + 20)[0],
                    struct.unpack_from("<I", buf, o + 16)[0]))
    return image_base, out


# Sections qui portent du CODE. `.text` seul rend 0 hit sur un binaire IL2CPP : le code
# AOT vit dans `il2cpp` (~40 Mo), `.text` ne porte que le runtime Unity.
CODE_SECTIONS = (".text", "il2cpp")


class SymbolIndex:
    """`functions.tsv` d'un build, interrogeable par adresse ET par nom."""

    def __init__(self, path: Path, build: str):
        self.build = build
        pairs = []
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("#"):
                    continue
                addr, _, name = line.rstrip("\n").partition("\t")
                if not name:
                    continue
                try:
                    pairs.append((int(addr, 16), name))
                except ValueError:
                    continue
        pairs.sort()
        self.addrs = [a for a, _ in pairs]
        self.names = [n for _, n in pairs]
        self.by_name: dict[str, int] = {}
        for a, n in pairs:
            self.by_name.setdefault(n, a)

    @classmethod
    def current(cls) -> "SymbolIndex":
        b = versioned_build()
        return cls(functions_tsv(b), b)

    def resolve(self, va: int) -> tuple[str, int]:
        """(symbole englobant, offset). Sans borne -- cf. `span` pour l'etendue reelle."""
        i = bisect.bisect_right(self.addrs, va) - 1
        if i < 0:
            return "?", 0
        return self.names[i], va - self.addrs[i]

    def va_of(self, symbol: str) -> int:
        """VA d'un symbole NOMME. Leve si absent -- un ancrage muet n'est pas un ancrage."""
        va = self.by_name.get(symbol)
        if va is None:
            raise BuildPinRefused(
                "NON MESURE : le symbole d'ancrage est ABSENT de la table %s :\n"
                "    %s\n"
                "  Un ancrage introuvable ne se remplace pas par une adresse -- c'est la table\n"
                "  ou le nom qu'il faut reprendre." % (self.build, symbol))
        return va

    def span(self, va: int) -> int:
        """Etendue MAJORANTE d'une fonction : jusqu'au symbole suivant."""
        i = bisect.bisect_right(self.addrs, va) - 1
        if i < 0:
            return 0
        return (self.addrs[i + 1] - self.addrs[i]) if i + 1 < len(self.addrs) else 0x2000


def va_to_file_offset(image_base: int, secs, va: int) -> int | None:
    rva = va - image_base
    for _nm, vaddr, vsize, praw, _rawsz in secs:
        if vaddr <= rva < vaddr + vsize:
            return praw + (rva - vaddr)
    return None


def load_dll() -> tuple[bytes, int, list, SymbolIndex]:
    """(octets, image_base, sections, index) du build courant -- ou `BuildPinRefused`.

    L'entree unique des probes offline : les trois artefacts sortent ENSEMBLE, du MEME
    build, ou aucun ne sort.
    """
    dll = game_dll()
    buf = dll.read_bytes()
    image_base, secs = pe_sections(buf)
    return buf, image_base, secs, SymbolIndex.current()


def main() -> int:                                       # diagnostic ASCII
    try:
        inst, vers = installed_build(), versioned_build()
        print("build installe        : %s" % inst)
        print("data/symbols/CURRENT  : %s" % vers)
        print("GameAssembly.dll      : %s" % game_dll().as_posix())
        print("ghidra/functions.tsv  : %s" % functions_tsv().as_posix())
        print("racine d'installation : %s" % install_dir().as_posix())
    except BuildPinRefused as exc:
        print("REFUS -- %s" % str(exc).replace("\n", "\n"))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
