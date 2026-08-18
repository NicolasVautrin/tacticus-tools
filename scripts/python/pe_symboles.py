#!/usr/bin/env python3
"""FOYER : resoudre un SYMBOLE Ghidra en ADRESSE(S), et lire les octets du PE a cette adresse.

POURQUOI CE MODULE EXISTE (#10026-r1, ferme par #10028)
-------------------------------------------------------
`#10026` a mesure qu'**un nom de `ghidra/functions.tsv` ne designe PAS une adresse** : C# surcharge,
IL2CPP nomme les surcharges a l'IDENTIQUE, et la table est indexee par ADRESSE. Sur les deux builds
dont ce depot porte la table, **5 341 noms sur 145 703 (3,7 %) portent PLUSIEURS VA**, a l'identique
sur `rnca9r7q6c` et `t6dpr4k06g` -- `IdunBattleLogic.Entities.DSLTriggers$$On` en a **TROIS**. Un
helper qui rend la PREMIERE ligne portant le nom lit donc les mauvais octets, et le rouge qui en
sort n'accuse RIEN du port.

Ce helper etait **RECOPIE dans TROIS fichiers de test**, avec trois corps legerement differents :
`test_936_wrathful_devotion_offline.py` (repare par #10026), `test_929_savage_killer_offline.py` et
`test_936r1_expiry_removal_offline.py` -- ces deux-la verts **PAR CHANCE**, leurs symboles n'ayant
qu'une VA sur ce build, pas par construction. Trois copies, c'est trois dates de peremption, et
c'est la MEME maladie que #10028 a soignee deux fois le meme jour sur l'axe des ORDINAUX
(`temoins_de_decalage`, `membres_decales`). Le foyer est ici.

CE QUE CE MODULE NE FAIT PAS -- dit, pas sous-entendu
-----------------------------------------------------
  * il ne DISTINGUE pas deux surcharges : le symbole, par construction, ne le permet pas. Il rend
    la FAMILLE (`vas_du_symbole`) et laisse l'appelant decider -- par l'arite, par la signature lue
    dans `frida/methods.tsv`, ou par le site d'appel. `va_du_symbole` REFUSE un nom partage au lieu
    d'en choisir un : une adresse prise au hasard dans une famille est une mesure FABRIQUEE ;
  * il ne dit RIEN d'un symbole absent de la table -- et l'absence ne prouve rien (CLAUDE.md,
    « l'ABSENCE d'une methode dans les tables ne prouve RIEN » : IL2CPP deduplique les corps
    triviaux, et les bases generiques sont hors du dump Frida) ;
  * aucune VA n'est jamais ECRITE ici ni chez ses appelants : elles sont LUES dans la table du
    build, et la RVA se calcule EN CODE (`va - IMAGE_BASE`).

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import os
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: Base de l'image PE de `GameAssembly.dll`. Ce n'est PAS une VA epinglee : c'est l'`ImageBase` du
#: header, le SEUL terme qui rende une RVA calculable depuis une VA lue dans la table.
IMAGE_BASE = 0x180000000


def build_avec_dll() -> "str | None":
    """Le build dont on a A LA FOIS la table de symboles VERSIONNEE et la DLL INSTALLEE.

    `data/symbols/` porte plusieurs builds ; prendre le premier par ordre alphabetique rendrait un
    hash PERIME (mesure : `gqfc5mff6c` sort avant `rnca9r7q6c`) et ferait skipper une garde alors
    que le binaire est la. Le discriminant est la CONCORDANCE des deux -- exactement la
    verification que le CLAUDE.md exige avant toute analyse offline."""
    d = ROOT / "data" / "symbols"
    for p in sorted(d.iterdir()) if d.exists() else []:
        if not ((p / "ghidra" / "functions.tsv").exists() and (p / "BUILD").exists()):
            continue
        if chemin_dll(p.name).exists():
            return p.name
    return None


def chemin_dll(build: str) -> Path:
    """Le `GameAssembly.dll` INSTALLE de ce build. Le fichier peut ne pas exister -- l'appelant
    teste, il ne suppose pas."""
    return (Path(os.environ.get("LOCALAPPDATA") or "") / "tacticus" / "games" / build
            / "GameAssembly.dll")


def vas_du_symbole(build: str, symbole: str) -> list:
    """TOUTES les VA que la table porte sous ce nom, dans l'ordre du fichier (adresses croissantes).

    ⚠ On cite le RANG, jamais l'adresse : les noms sont stables a 97,5 % entre builds, les adresses
    changent a 100 %. Et ici c'est le rang qui porte l'information, puisque le SYMBOLE, par
    construction, ne distingue pas les surcharges."""
    tsv = ROOT / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    out = []
    if not tsv.exists():
        return out
    for line in tsv.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#") or "\t" not in line:
            continue
        va, name = line.split("\t", 1)
        if name.strip() == symbole:
            out.append(int(va, 16))
    return out


def va_du_symbole(build: str, symbole: str) -> "int | None":
    """La VA d'un symbole dont l'UNICITE est ATTENDUE. `None` si absent.

    Un nom PARTAGE fait ROUGIR au lieu d'en choisir un : c'est le cran de #10026, et c'est ce qui
    empeche un appelant de croire mesurer une adresse alors qu'il en tire une au sort."""
    vas = vas_du_symbole(build, symbole)
    assert len(vas) <= 1, (
        "`%s` porte %d VA dans la table du build %s (%s) : ce site attend un symbole UNIQUE. "
        "Passer par `vas_du_symbole` et accepter la famille entiere, jamais en choisir un."
        % (symbole, len(vas), build, [hex(v) for v in vas]))
    return vas[0] if vas else None


def noms_a_plusieurs_va(build: str) -> int:
    """Combien de noms de la table portent PLUSIEURS VA -- la MESURE qui fonde ce module.

    Rendue pour qu'un cliquet puisse assertionner son propre non-vide : si ce compte tombe a 0, le
    cran de `va_du_symbole` ne peut plus rien attraper et il faut le DIRE, pas se rejouir."""
    tsv = ROOT / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    if not tsv.exists():
        return 0
    vus, doubles = set(), set()
    for line in tsv.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#") or "\t" not in line:
            continue
        nom = line.split("\t", 1)[1].strip()
        if nom in vus:
            doubles.add(nom)
        vus.add(nom)
    return len(doubles)


def lire_a_la_va(dll: Path, va: int, size: int) -> bytes:
    """Lit `size` octets a la VA `va`, en traduisant par les SECTIONS du PE.

    Mini-parseur : `e_lfanew`, `NumberOfSections`, `SizeOfOptionalHeader`, puis chaque
    `IMAGE_SECTION_HEADER` de 40 octets. La RVA est calculee EN CODE (`va - IMAGE_BASE`), jamais a
    la main. Rend `b""` si la VA ne tombe dans aucune section -- jamais une lecture au hasard."""
    rva = va - IMAGE_BASE
    with dll.open("rb") as f:
        head = f.read(0x400)
        e_lfanew = struct.unpack_from("<I", head, 0x3C)[0]
        nsec = struct.unpack_from("<H", head, e_lfanew + 6)[0]
        opt_size = struct.unpack_from("<H", head, e_lfanew + 20)[0]
        f.seek(e_lfanew + 24 + opt_size)
        secs = f.read(40 * nsec)
        for i in range(nsec):
            vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", secs, 40 * i + 8)
            if vaddr <= rva < vaddr + max(vsize, rawsize):
                f.seek(rawptr + (rva - vaddr))
                return f.read(size)
    return b""
