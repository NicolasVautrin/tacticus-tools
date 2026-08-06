"""Lecture du `global-metadata.dat` IL2CPP -- le SEUL porteur du champ `slot`.

POURQUOI CE MODULE EXISTE
-------------------------
Une methode d'INTERFACE n'a aucun corps. Elle n'a donc :

  * aucune ligne dans `data/symbols/<build>/frida/methods.tsv`, qui est indexee par ADRESSE
    (mesure : 0 ligne dont la colonne classe vaut `Core.Services.IOperationProcessor`) ;
  * aucun symbole dans `data/symbols/<build>/ghidra/functions.tsv` ;
  * rien a decompiler.

Or le decompile d'un appel d'interface IL2CPP ne porte QUE le numero de slot -- litteralement
additionne a l'`interfaceOffset` de la classe receveuse :

    if (*(longlong *)(*(longlong *)(K + 0xb0) + i * 0x10) == DAT_<Il2CppClass* de l'interface>) {
        puVar = (undefined8 *)
                ((longlong)(*(int *)(*(longlong *)(K + 0xb0) + 8 + i * 0x10) + <SLOT>) * 0x10
                 + 0x138 + K);

Sans le metadata, ce slot ne se traduit en NOM que par recoupement (arite, contexte), ce qui a
produit deux lectures publiees CONTRADICTOIRES (#477-r24-r1). Le champ `slot` de
`Il2CppMethodDefinition`, lui, le DONNE.

CE QU'ON NE LIT PAS : LE HEADER
-------------------------------
Ce build annonce `version = 39`, qui n'est aucune version Unity publique, et son header ne suit
pas le layout `Il2CppGlobalMetadataHeader` connu (mesure : la paire (offset, taille) de la table
des methodes n'est a aucune des positions attendues -- seule celle des CHAINES y tombe juste).
On ne lit donc AUCUN champ du header : les tables sont localisees PAR CONTENU, ce qui rend ce
module insensible au numero de version comme au reordonnancement des champs.

COMMENT ON LOCALISE, ET COMMENT ON LE VERIFIE
---------------------------------------------
1. Les methodes d'un type sont CONSECUTIVES dans la table (`methodStart .. +method_count`), et
   `Il2CppMethodDefinition.nameIndex` est un decalage dans la table de chaines. Le decalage de
   base des chaines est inconnu, mais les DIFFERENCES de `nameIndex` entre deux methodes valent
   exactement les differences de position de leurs chaines dans le fichier -- grandeur
   observable, elle. Trois ancres suffisent a fixer (base, pas) sans ambiguite.
2. La localisation n'est retenue que si elle se VERIFIE : on re-decode alors les N methodes de la
   classe et on exige que nom ET arite concordent avec `frida/methods.tsv` sur un prefixe long.
   Une localisation qui ne se verifie pas est REFUSEE, jamais rendue au petit bonheur.

Tri-etat : toute impossibilite LEVE `MetadataRefused`. « Je n'ai pas pu mesurer » et « j'ai
mesure, c'est vide » ne rendent jamais la meme chose (meme discipline que `build_pin` et
`host_inputs`).
"""
from __future__ import annotations

import re
import struct
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

__all__ = [
    "ATTR_ABSTRACT",
    "MetadataRefused",
    "MethodDef",
    "MetadataReader",
    "class_method_order",
]

#: `System.Reflection.MethodAttributes.Abstract` -- ce qui distingue une methode d'INTERFACE
#: (0x05c6 sur ce build) d'une implementation concrete scellee (0x01e6).
ATTR_ABSTRACT = 0x0400

#: Tailles d'entree `Il2CppMethodDefinition` plausibles selon la version du metadata
#: (v29 = 32 octets ; v31 ajoute `returnParameterToken` = 36). On les ESSAIE, on ne les
#: suppose pas : seule celle qui se verifie est retenue.
_ENTRY_SIZES = (28, 32, 36, 40, 44, 48)

#: Nombre minimal de methodes dont le couple (nom, arite) doit concorder pour qu'une
#: localisation soit acceptee. En dessous, on REFUSE plutot que de rendre une table douteuse.
_MIN_CONCORDANCE = 40


class MetadataRefused(RuntimeError):
    """Lecture du metadata REFUSEE (fichier absent, table introuvable, ou non verifiable)."""


@dataclass(frozen=True)
class MethodDef:
    """Une entree `Il2CppMethodDefinition`, reduite a ce que ce module sait lire SUREMENT."""

    name: str
    slot: int
    param_count: int
    flags: int
    file_offset: int

    @property
    def is_abstract(self) -> bool:
        return bool(self.flags & ATTR_ABSTRACT)


# --------------------------------------------------------------- l'ordre lu cote FRIDA


def class_method_order(methods_tsv: Path, klass: str) -> list[tuple[str, int]]:
    """(nom court, nombre d'arguments) des methodes de `klass`, DANS L'ORDRE du dump.

    Le dump Frida enumere par `il2cpp_class_get_methods`, donc dans l'ordre de la table du
    metadata. Il sert d'ANCRE, pas de verite : il est indexe par adresse, donc il PERD les
    surcharges a corps deduplique (mesure : 149 lignes pour 150+ entrees reelles sur
    `Core.Services.OperationProcessor`). C'est pourquoi seul un PREFIXE est exige concordant.
    """
    out: list[tuple[str, int]] = []
    with methods_tsv.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#!"):
                continue
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 3 or cols[2] != klass:
                continue
            short = cols[1].rsplit(".", 1)[-1]
            args = cols[5] if len(cols) > 5 else ""
            n = len(re.split(r",(?![^<>]*>)", args)) if args else 0
            out.append((short, n))
    if not out:
        raise MetadataRefused(
            "NON MESURE : aucune methode de `%s` dans %s -- la classe a-t-elle change de nom ?"
            % (klass, methods_tsv.as_posix()))
    return out


# ------------------------------------------------------------------------ le lecteur


class MetadataReader:
    """Localise la table `methods` PAR CONTENU, puis en extrait les slots d'une interface."""

    def __init__(self, blob: bytes) -> None:
        self.blob = blob
        self._u32 = array("I")
        self._u32.frombytes(blob[: (len(blob) // 4) * 4])
        self.entry_size: int | None = None
        self.string_offset: int | None = None
        self._class_base: int | None = None

    # ------------------------------------------------------------------ chaines

    def cstr(self, file_offset: int) -> str:
        end = self.blob.find(b"\x00", file_offset)
        if end < 0:
            raise MetadataRefused("chaine non terminee a %d" % file_offset)
        return self.blob[file_offset:end].decode("utf-8", "replace")

    def _unique_string_pos(self, name: str) -> int | None:
        """Position de `name` s'il apparait EXACTEMENT une fois comme chaine complete."""
        needle = name.encode("utf-8") + b"\x00"
        hits: list[int] = []
        pos = self.blob.find(needle)
        while pos >= 0:
            if pos > 0 and self.blob[pos - 1] == 0:      # debut de chaine, pas un suffixe
                hits.append(pos)
                if len(hits) > 1:
                    return None
            pos = self.blob.find(needle, pos + 1)
        return hits[0] if len(hits) == 1 else None

    # ------------------------------------------------------- localisation de la table

    def locate(self, order: Sequence[tuple[str, int]]) -> None:
        """Fixe (entry_size, string_offset, base de la classe) depuis l'ordre de ses methodes."""
        anchors = [(i, self._unique_string_pos(nm)) for i, (nm, _) in enumerate(order)]
        anchors = [(i, p) for i, p in anchors if p is not None]
        if len(anchors) < 3:
            raise MetadataRefused(
                "NON MESURE : moins de 3 noms de methode UNIQUES dans le metadata "
                "(%d trouve(s)) -- impossible de fixer le pas de la table sans ambiguite."
                % len(anchors))

        (i0, p0), (i1, p1), (i2, p2) = anchors[0], anchors[1], anchors[2]
        d01 = (p1 - p0) & 0xFFFFFFFF
        d02 = (p2 - p0) & 0xFFFFFFFF
        n = len(self._u32)

        found: list[tuple[int, int]] = []                      # (entry_size, base)
        for size in _ENTRY_SIZES:
            step = size // 4
            span = max(i1 - i0, i2 - i0) * step
            for k in range(n - span):
                if (self._u32[k + (i1 - i0) * step] - self._u32[k]) & 0xFFFFFFFF != d01:
                    continue
                if (self._u32[k + (i2 - i0) * step] - self._u32[k]) & 0xFFFFFFFF != d02:
                    continue
                found.append((size, k * 4 - i0 * size))

        verified = [(size, base, ok) for size, base in found
                    for ok in (self._concordance(order, size, base, p0 - self._name_index(base, size, i0)),)
                    if ok >= _MIN_CONCORDANCE]
        if not verified:
            raise MetadataRefused(
                "NON MESURE : table des methodes introuvable -- %d candidat(s) brut(s), "
                "aucun ne se VERIFIE a %d methodes concordantes (nom + arite). Le layout du "
                "metadata a-t-il change ?" % (len(found), _MIN_CONCORDANCE))
        if len({(s, b) for s, b, _ in verified}) > 1:
            raise MetadataRefused(
                "AMBIGU : %d localisations distinctes se verifient -- on ne DEVINE pas."
                % len(verified))

        size, base, _ = verified[0]
        self.entry_size = size
        self._class_base = base
        self.string_offset = p0 - self._name_index(base, size, i0)

    def _name_index(self, base: int, size: int, idx: int) -> int:
        return struct.unpack_from("<I", self.blob, base + idx * size)[0]

    def _concordance(self, order: Sequence[tuple[str, int]], size: int, base: int,
                     string_offset: int) -> int:
        """Longueur du PREFIXE de `order` que cette localisation reproduit (nom + arite)."""
        if base < 0 or base + len(order) * size > len(self.blob) or string_offset < 0:
            return 0
        hit = 0
        for idx, (name, nargs) in enumerate(order):
            try:
                ent = self._entry(base + idx * size, size, string_offset)
            except (struct.error, MetadataRefused):
                break
            if ent.name != name or ent.param_count != nargs:
                break
            hit += 1
        return hit

    def _entry(self, file_offset: int, size: int, string_offset: int) -> MethodDef:
        name_index = struct.unpack_from("<I", self.blob, file_offset)[0]
        flags, _iflags, slot, param_count = struct.unpack_from("<HHHH", self.blob,
                                                               file_offset + size - 8)
        return MethodDef(name=self.cstr(string_offset + name_index), slot=slot,
                         param_count=param_count, flags=flags, file_offset=file_offset)

    def entry(self, file_offset: int) -> MethodDef:
        if self.entry_size is None or self.string_offset is None:
            raise MetadataRefused("locate() n'a pas ete appele")
        return self._entry(file_offset, self.entry_size, self.string_offset)

    # -------------------------------------------------------- la table d'une interface

    def interface_table(self, anchor_names: Iterable[str]) -> list[MethodDef]:
        """Les methodes d'une interface, INDEXEES PAR LEUR SLOT.

        `anchor_names` : des noms de methodes, uniques dans le metadata, portes par l'interface
        cherchee. Chacun y apparait deux fois -- une entree ABSTRAITE (l'interface) et une
        concrete (l'implementation) ; on retient l'abstraite.

        LE CONTROLE QUI REND CE RESULTAT SUR : chaque ancre propose l'ensemble des debuts de
        table `file_offset - slot * pas` compatibles avec elle, et on retient l'INTERSECTION.
        Si elle est vide, les ancres ne decrivent aucune table commune ; si elle en garde
        plusieurs, elles n'en designent pas UNE. Les deux LEVENT : on ne devine pas.

        ⚠ D'ou vient la multiplicite -- ce n'est PAS la surcharge. Dans une table CONTIGUE,
        `file_offset - slot * pas` vaut la meme chose pour toutes les entrees de la meme
        interface, surchargees ou non (mesure : `EvaluateAbilities` occupe les slots 77-79 et
        81-82 et ne propose qu'UNE base ; `GetAdjacentEnemies` en occupe quatre d'affilee sur
        `IBattleQuery`, meme resultat). Ce qui multiplie les candidats, ce sont les interfaces
        HOMONYMES : `StartMatch` est declaree par CINQ interfaces distinctes, donc cinq bases.
        C'est exactement ce que l'intersection dissout -- et c'est aussi pourquoi UNE ancre ne
        suffit pas des que son nom est banal.
        """
        if self.entry_size is None or self.string_offset is None:
            raise MetadataRefused("locate() n'a pas ete appele")
        size = self.entry_size
        noms = list(anchor_names)
        candidats: set[int] | None = None
        vues: list[str] = []
        for name in noms:
            propose = {ent.file_offset - ent.slot * size
                       for ent in self._entries_named(name) if ent.is_abstract}
            if not propose:
                continue                      # nom absent ou non unique : cette ancre ne dit rien
            vues.append(name)
            candidats = propose if candidats is None else candidats & propose
        if not vues or candidats is None:
            raise MetadataRefused(
                "NON MESURE : aucune des %d ancres ne designe une methode ABSTRAITE unique -- "
                "l'interface a-t-elle change de nom ?" % len(noms))
        if not candidats:
            raise MetadataRefused(
                "INCOHERENT : les ancres %s ne partagent AUCUN debut de table. Elles ne "
                "decrivent donc pas la meme interface, ou `slot` n'indexe plus une table "
                "contigue -- toute lecture par index serait fausse." % ", ".join(vues))
        if len(candidats) > 1:
            raise MetadataRefused(
                "AMBIGU : %d debuts de table restent compatibles avec les ancres %s. En "
                "ajouter d'autres, portees par cette interface, jusqu'a n'en laisser qu'un."
                % (len(candidats), ", ".join(vues)))

        base = next(iter(candidats))
        out: list[MethodDef] = []
        idx = 0
        while base + (idx + 1) * size <= len(self.blob):
            ent = self.entry(base + idx * size)
            if ent.slot != idx or not ent.is_abstract:
                break                                   # fin de table : la suivante est concrete
            out.append(ent)
            idx += 1
        if not out:
            raise MetadataRefused("NON MESURE : table d'interface vide")
        return out

    def _entries_named(self, name: str) -> Iterator[MethodDef]:
        """Toutes les entrees de la table portant ce nom (alignees sur le pas de la table)."""
        if self.entry_size is None or self.string_offset is None or self._class_base is None:
            raise MetadataRefused("locate() n'a pas ete appele")
        pos = self._unique_string_pos(name)
        if pos is None:
            return
        want = pos - self.string_offset
        if want < 0:
            return
        size, start = self.entry_size, 0
        while True:
            try:
                start = self._u32.index(want, start)
            except ValueError:
                return
            off = start * 4
            start += 1
            if (off - self._class_base) % size:
                continue                                 # pas une entree : mauvais alignement
            try:
                yield self.entry(off)
            except MetadataRefused:
                continue


def read(path: Path) -> MetadataReader:
    try:
        return MetadataReader(path.read_bytes())
    except OSError as exc:                                              # noqa: BLE001
        raise MetadataRefused("NON MESURE : metadata illisible (%s)" % exc) from exc
