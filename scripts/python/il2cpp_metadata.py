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
from collections import Counter
from math import gcd as _gcd
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

__all__ = [
    "ATTR_ABSTRACT",
    "MetadataRefused",
    "MethodDef",
    "MetadataReader",
    "TypeLayout",
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

#: Tailles d'entree `Il2CppTypeDefinition` essayees pour la grille des TYPES. Ce build n'en
#: porte AUCUNE des tailles publiees (mesure : 82 octets, non multiple de 4) -- d'ou la
#: derivation par PGCD plutot qu'une liste. La constante ne borne que la recherche.
_TYPE_STEP_MIN, _TYPE_STEP_MAX = 40, 200

#: Facteur du crible de cardinalite : le compte lu doit valoir au moins ce que Frida
#: attribue au type (jamais moins -- le dump PERD des surcharges), et rester du meme ordre.
#: Il ne sert qu'a BORNER les candidats ; c'est le controle par les NOMS qui tranche.
_MARGE_COUNT = 2


class MetadataRefused(RuntimeError):
    """Lecture du metadata REFUSEE (fichier absent, table introuvable, ou non verifiable)."""


def _dernier_segment(nom: str) -> str:
    """`IFoo.Bar` -> `Bar`, `.ctor` -> `ctor`. La convention de `class_method_order`."""
    return nom.rsplit(".", 1)[-1]


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


@dataclass(frozen=True)
class TypeLayout:
    """Ce qu'on a DERIVE de la grille `Il2CppTypeDefinition` -- rien n'y est suppose.

    `step` (pas de la grille), `off_method_start` / `off_method_count` (positions des deux
    champs DANS l'entree) et `method_table_base` (offset fichier de la 1re entree de la table
    des methodes) sont tous obtenus par INTERSECTION sur plusieurs types ancres, jamais par
    un layout recopie d'une version d'IL2CPP.
    """

    step: int
    off_method_start: int
    off_method_count: int
    method_table_base: int
    ancres: tuple[str, ...]


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
        self._types: TypeLayout | None = None

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

    # ------------------------------------------------- la grille des TYPES (#477-r25)

    def all_string_pos(self, name: str) -> list[int]:
        """Toutes les positions ou `name` apparait comme chaine COMPLETE."""
        needle = name.encode("utf-8") + b"\x00"
        out: list[int] = []
        pos = self.blob.find(needle)
        while pos >= 0:
            if pos > 0 and self.blob[pos - 1] == 0:
                out.append(pos)
            pos = self.blob.find(needle, pos + 1)
        return out

    def typedef_offsets(self, namespace: str, name: str) -> list[int]:
        """Offsets fichier des entrees `Il2CppTypeDefinition` de ce type.

        Le discriminant est la PAIRE ADJACENTE (`nameIndex`, `namespaceIndex`) -- les deux
        premiers champs de la structure, tous deux relatifs au meme `string_offset` deja
        derive. Chercher la paire, et non chaque index isolement, est ce qui rend
        l'identification exacte : un `nameIndex` seul se retrouve dans des dizaines de
        contextes (mesure : 19 430 entrees decodent sur la grille, mais chacun des types
        cherches n'y apparait qu'UNE fois).
        """
        if self.string_offset is None:
            raise MetadataRefused("locate() n'a pas ete appele")
        so = self.string_offset
        hits: list[int] = []
        for np_ in self.all_string_pos(name):
            for sp in self.all_string_pos(namespace):
                pat = struct.pack("<ii", np_ - so, sp - so)
                pos = self.blob.find(pat)
                while pos >= 0:
                    hits.append(pos)
                    pos = self.blob.find(pat, pos + 1)
        return sorted(set(hits))

    def _typedef_unique(self, namespace: str, name: str) -> int:
        hits = self.typedef_offsets(namespace, name)
        if len(hits) != 1:
            raise MetadataRefused(
                "NON MESURE : `%s.%s` a %d entree(s) de type dans le metadata -- on ne DEVINE "
                "pas laquelle." % (namespace, name, len(hits)))
        return hits[0]

    def locate_types(self, ancres: Sequence[tuple[str, str, Sequence[tuple[str, int]]]]) -> TypeLayout:
        """Derive la grille des types, PUIS la CONFRONTE aux noms de methodes des ancres.

        `ancres` : `(namespace, nom de type, ordre des methodes lu cote Frida)` -- des
        CLASSES CONCRETES presentes dans `frida/methods.tsv`.

        ⚠ CE QU'ON N'UTILISE PAS : L'ORDRE DU DUMP FRIDA. `methods.tsv` est triee par
        ADRESSE, et l'ordre d'emission des corps ne suit l'ordre de declaration que par
        accident (mesure : il concorde sur 87 methodes pour `Core.Services.OperationProcessor`
        et sur 1 seule pour `IdunBattle.Core.Services.BattleQuery`). Un critere de PREFIXE
        ordonne echoue donc sur 5 classes sur 6. On ne compare que des ENSEMBLES de noms.

        TROIS derivations, aucune recopiee d'un layout publie :

        1. `step` : PGCD des ecarts entre entrees de type. Au moins 3 ancres -- deux
           rendraient leur ecart, qui peut etre un MULTIPLE du pas.
        2. un CRIBLE de cardinalite : pour chaque couple (u32 `debut`, u16 `compte`), le
           compte lu doit valoir AU MOINS ce que Frida attribue au type, et rester du meme
           ordre. L'inegalite a un sens precis : `methods.tsv` est indexee par ADRESSE, donc
           elle PERD des surcharges -- le metadata en a toujours autant ou plus, jamais moins.
        3. le CONTROLE PAR LES NOMS, qui seul TRANCHE : `method_table_base` se deduit de
           l'unique classe deja localisee par `locate()`, puis on exige que le bloc lu pour
           chaque ancre CONTIENNE tous les noms que Frida lui attribue. Un couple qui ne le
           fait pas est ECARTE ; s'il n'en reste aucun, ou plus d'un, on REFUSE.

        ⚠ CE QU'ON N'UTILISE PAS NON PLUS : la relation `debut(t) + compte(t) == debut(t+1)`.
        Elle parait ideale et elle est FAUSSE ici -- mesure : sur 599 paires consecutives,
        67 la violent, la table des types n'etant pas strictement ordonnee par `methodStart`
        (deux entrees voisines lues a 60723 puis 60726 puis 60724). S'en servir comme critere
        aurait demande un seuil arbitraire ; le crible + les noms n'en demandent aucun.
        """
        if self.entry_size is None or self.string_offset is None or self._class_base is None:
            raise MetadataRefused("locate() n'a pas ete appele")
        if len(ancres) < 3:
            raise MetadataRefused(
                "NON MESURE : %d ancre(s) de type -- il en faut au moins 3 pour que le PGCD "
                "des ecarts designe le PAS et non un de ses multiples." % len(ancres))

        vus: list[tuple[str, str, str, int, Sequence[tuple[str, int]]]] = []
        for ns, nom, ordre in ancres:
            try:
                toff = self._typedef_unique(ns, nom)
            except MetadataRefused:
                continue
            vus.append(("%s.%s" % (ns, nom), ns, nom, toff, ordre))
        if len(vus) < 3:
            raise MetadataRefused(
                "NON MESURE : seules %d ancre(s) sur %d ont une entree de type UNIQUE -- pas "
                "assez pour deriver la grille." % (len(vus), len(ancres)))

        offs = sorted(t for _, _, _, t, _ in vus)
        step = 0
        for a, b in zip(offs, offs[1:]):
            step = _gcd(step, b - a)
        if not _TYPE_STEP_MIN <= step <= _TYPE_STEP_MAX:
            raise MetadataRefused(
                "INCOHERENT : le PGCD des ecarts entre entrees de type vaut %d, hors des "
                "bornes plausibles [%d, %d] -- la grille n'est pas reguliere."
                % (step, _TYPE_STEP_MIN, _TYPE_STEP_MAX))

        #: La classe dont `locate()` a fixe le bloc : c'est la SEULE dont on connaisse
        #: l'offset FICHIER, donc la seule qui puisse convertir un index en offset.
        t0 = vus[0][3]
        size = self.entry_size
        n = len(self.blob)

        starts_ok: list[tuple[int, int]] = []               # (off_debut, table_base)
        for o in range(0, step - 3):
            valeurs = [struct.unpack_from("<i", self.blob, t + o)[0] for _, _, _, t, _ in vus]
            if any(v < 0 for v in valeurs):
                continue
            table_base = self._class_base - valeurs[0] * size
            if table_base < 0 or any(table_base + v * size + size > n for v in valeurs):
                continue
            starts_ok.append((o, table_base))
        if not starts_ok:
            raise MetadataRefused(
                "NON MESURE : aucun champ u32 ne rend, pour les %d ancres, un index de "
                "methode qui retombe dans le fichier." % len(vus))

        couples: list[tuple[int, int, int]] = []            # (off_debut, off_compte, base)
        for off_ms, table_base in starts_ok:
            for c in range(0, step - 1):
                ok = True
                for _, _, _, t, ordre in vus:
                    cnt = struct.unpack_from("<H", self.blob, t + c)[0]
                    if not len(ordre) <= cnt <= _MARGE_COUNT * len(ordre) + _MARGE_COUNT:
                        ok = False
                        break
                if ok:
                    couples.append((off_ms, c, table_base))
        if not couples:
            raise MetadataRefused(
                "NON MESURE : aucun champ u16 ne rend un compte de methodes compatible avec "
                "ce que Frida attribue aux %d ancres." % len(vus))

        retenus: list[TypeLayout] = []
        for off_ms, off_cnt, table_base in couples:
            lay = TypeLayout(step=step, off_method_start=off_ms, off_method_count=off_cnt,
                             method_table_base=table_base,
                             ancres=tuple(nom for nom, _, _, _, _ in vus))
            if all(self._noms_concordent(lay, t, ordre) for _, _, _, t, ordre in vus):
                retenus.append(lay)
        if not retenus:
            raise MetadataRefused(
                "NON MESURE : aucun des %d couple(s) de champs ne rend, pour les %d ancres, "
                "un bloc CONTENANT les noms que Frida leur attribue -- ce ne sont donc pas "
                "les methodes." % (len(couples), len(vus)))
        if len({(x.off_method_start, x.off_method_count) for x in retenus}) > 1:
            raise MetadataRefused(
                "AMBIGU : %d couples de champs se verifient (%s) -- ajouter des ancres."
                % (len(retenus),
                   ", ".join("%d/%d" % (x.off_method_start, x.off_method_count)
                             for x in retenus)))
        self._types = retenus[0]
        return self._types

    def _noms_concordent(self, lay: TypeLayout, toff: int,
                         ordre: Sequence[tuple[str, int]]) -> bool:
        """Le bloc lu pour ce type CONTIENT-il tous les noms que Frida lui attribue ?

        Inclusion, jamais egalite : `methods.tsv` est indexee par ADRESSE, donc elle PERD
        les surcharges a corps deduplique (mesure : 149 lignes pour 150 entrees reelles).
        C'est le metadata qui en a plus, jamais l'inverse -- une inclusion violee accuse
        donc le layout, pas le dump.

        ⚠ Les deux cotes sont ramenes au segment APRES LE DERNIER POINT. Sans cela, le
        constructeur ne concorde JAMAIS : le metadata l'ecrit `.ctor`, et le nom court que
        `class_method_order` derive du dump vaut `ctor` -- une seule ancre suffit alors a
        faire echouer une localisation JUSTE (mesure : 14 couples candidats, 0 retenu).
        """
        size = self.entry_size or 0
        start = struct.unpack_from("<i", self.blob, toff + lay.off_method_start)[0]
        count = struct.unpack_from("<H", self.blob, toff + lay.off_method_count)[0]
        base = lay.method_table_base + start * size
        if start < 0 or count == 0 or base < 0 or base + count * size > len(self.blob):
            return False
        try:
            lus = [_dernier_segment(self.entry(base + k * size).name) for k in range(count)]
        except (struct.error, MetadataRefused):
            return False
        return not (Counter(_dernier_segment(nm) for nm, _ in ordre) - Counter(lus))

    def type_methods(self, namespace: str, name: str) -> list[MethodDef]:
        """Les `method_count` methodes DECLAREES par ce type, dans l'ordre de la table.

        Pour une INTERFACE, l'index dans cette liste est le SLOT (verifie : `slot == idx`
        pour les 150 de `Core.Services.IOperationProcessor`) -- mais on rend le `slot` LU,
        jamais l'index : une interface qui en ETEND une autre demarre au-dessus de 0, et
        rendre l'index a sa place fabriquerait un mapping faux sans rien signaler.
        """
        if self._types is None:
            raise MetadataRefused("locate_types() n'a pas ete appele")
        lay = self._types
        toff = self._typedef_unique(namespace, name)
        start = struct.unpack_from("<i", self.blob, toff + lay.off_method_start)[0]
        count = struct.unpack_from("<H", self.blob, toff + lay.off_method_count)[0]
        if start < 0 or count == 0:
            raise MetadataRefused(
                "NON MESURE : `%s.%s` ne declare aucune methode (methodStart=%d, count=%d)."
                % (namespace, name, start, count))
        base = lay.method_table_base + start * (self.entry_size or 0)
        if base < 0 or base + count * (self.entry_size or 0) > len(self.blob):
            raise MetadataRefused(
                "INCOHERENT : le bloc de `%s.%s` sort du fichier." % (namespace, name))
        return [self.entry(base + k * (self.entry_size or 0)) for k in range(count)]

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


# ------------------------------------------------------------------------------------------------
# LES NOMS DECLARES PAR UN TYPE, MIS EN CACHE PAR LE BUILD (#1029)
#
# Le cout n'est pas la lecture d'un type : c'est le MONTAGE du lecteur (`read` + `locate` +
# `locate_types`), qui re-derive la grille du metadata a chaque appel. Mesure sur
# `test_932_deathwing_offline` : 19,2 s pour interroger DEUX types.
#
# Ce montage ne depend QUE du build (`global-metadata.dat` et `frida/methods.tsv`), donc son
# resultat ne peut bouger qu'a une mise a jour du jeu -- l'invalidation est une CLE, pas une
# heuristique.
_CACHE_NOMS = None


def _cache_noms():
    global _CACHE_NOMS
    if _CACHE_NOMS is None:
        import verdict_cache
        ici = Path(__file__).resolve().parent
        _CACHE_NOMS = verdict_cache.CacheCliquet(
            "il2cpp_noms_declares",
            contexte=verdict_cache.sha_fichiers_texte(ici / "il2cpp_metadata.py"),
            notes=("# Cle de validation = sha256 de `global-metadata.dat` (hors depot) et de",
                   "# `frida/methods.tsv`. `appel` porte les ANCRES et le TYPE demande : deux",
                   "# appelants qui n'ancrent pas la grille au meme endroit ne partagent pas",
                   "# leur verdict -- ce serait servir une lecture faite sur une AUTRE grille."))
    return _CACHE_NOMS


def noms_declares(meta: Path, methods_tsv: Path, ancres, types) -> dict | None:
    """`{(ns, nom): [noms de methodes declarees]}` pour `types`, ou `None` si NON MESURABLE.

    `ancres` = les `(ns, nom)` qui servent a caler la grille ; `types` = ceux qu'on interroge.

    ⚠ LES ANCRES ENTRENT DANS LA CLE. Un appelant qui cale la grille sur d'autres ancres lit
    potentiellement d'autres offsets : partager le verdict entre deux ancrages differents
    reviendrait a servir une lecture faite sur une AUTRE grille, sans que rien ne le signale.

    ⚠ ON NE CACHE PAS UN REFUS. Un `MetadataRefused` (jeu absent, alignement refuse) rend `None`
    et n'ecrit rien : figer un << pas mesure >> jusqu'au prochain build ferait taire l'appelant
    sur un vrai probleme.
    """
    import verdict_cache
    sha = verdict_cache.sha_gros_fichiers(meta, methods_tsv)
    ancres = tuple(tuple(a) for a in ancres)
    types = tuple(tuple(t) for t in types)
    appel = "noms|ancres=%s|types=%s" % (
        ",".join("%s.%s" % a for a in ancres), ",".join("%s.%s" % t for t in types))
    cle_rel = str(meta.name)
    if sha is not None:
        cache = _cache_noms()
        vu = cache.obtenir(cle_rel, appel, sha)
        if vu is not verdict_cache.MANQUE:
            return {tuple(k.split("|", 1)): v for k, v in vu.items()}
    try:
        rd = read(meta)
        ordre: list = []
        for ns, nm in ancres:
            ordre.extend(class_method_order(methods_tsv, "%s.%s" % (ns, nm)))
        rd.locate(ordre)
        rd.locate_types(tuple((ns, nm, class_method_order(methods_tsv, "%s.%s" % (ns, nm)))
                              for ns, nm in ancres))
        table = {(ns, nm): [m.name for m in rd.type_methods(ns, nm)] for ns, nm in types}
    except MetadataRefused:
        return None
    if sha is not None:
        cache.poser(cle_rel, appel, sha,
                    {"%s|%s" % k: v for k, v in table.items()})
        cache.enregistrer()
    return table
