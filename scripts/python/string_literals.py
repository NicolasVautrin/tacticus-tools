#!/usr/bin/env python3
"""LECTEUR de `data/symbols/<build>/metadata/string_literals.tsv` (#477-r15-r1).

    python scripts/python/string_literals.py whereis 183386748     # slot -> valeur
    python scripts/python/string_literals.py find Overwatch        # valeur -> index + slot
    python scripts/python/string_literals.py resolve <symbole>     # tous les slots d'une fn

CE QU'IL SERT
-------------
Rendre lisible le `DAT_<slot>` que Ghidra affiche au site d'utilisation d'une chaine .NET.
Les chaines IL2CPP vivent dans `global-metadata.dat`, pas dans le PE : sans cette table, le
`sourceId` d'un `StreamCache$$StartGroup` -- donc le champ `Source=` de chaque ligne de
groupe du flux de replay -- est illisible statiquement.

⚠ LA TABLE REFUSE DE SERVIR SUR UN AUTRE BUILD, ET C'EST LE POINT.
   Index et RVA sont TOUS DEUX des cles de build : la RVA parce que les adresses changent a
   100 % entre builds, l'index parce que c'est un rang d'emission du compilateur (la table
   n'est pas triee -- verifie). Resoudre un slot contre la mauvaise table rendrait une chaine
   PLAUSIBLE ET FAUSSE, en silence. `charger()` confronte donc les DEUX sha256 estampilles
   (le PE *et* le fichier de metadonnees) au binaire installe, et LEVE en cas d'ecart.

   L'echappatoire `verifier=False` existe pour la consultation humaine d'un build archive.
   Elle ne ment pas : l'objet rendu porte `verifiee = False`, et tout appelant qui rend un
   VERDICT doit le regarder.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from il2cpp_provenance import (ProvenanceError, installed_dll, parse_stamp,  # noqa: F401
                               sha256_of)

REPO = Path(__file__).resolve().parents[2]
SYMBOLS = REPO / "data" / "symbols"
META_REL = Path("Tacticus_Data") / "il2cpp_data" / "Metadata" / "global-metadata.dat"


class TableAbsente(RuntimeError):
    """Pas de table pour ce build -- la produire, pas s'en passer."""


class TableLitteraux:
    """La table des litteraux d'UN build. Immuable une fois chargee."""

    __slots__ = ("build", "image_base", "verifiee", "_valeurs", "_rva", "_par_rva")

    def __init__(self, build: str, image_base: int, verifiee: bool,
                 valeurs: list[str], rva: list[int | None]) -> None:
        self.build = build
        self.image_base = image_base
        #: False = la provenance n'a PAS ete confrontee au binaire installe.
        self.verifiee = verifiee
        self._valeurs = valeurs
        self._rva = rva
        self._par_rva = {r: i for i, r in enumerate(rva) if r is not None}

    def __len__(self) -> int:
        return len(self._valeurs)

    @property
    def slots_joints(self) -> int:
        """Nombre de litteraux dont le slot PE est connu (le pont vers le decompile)."""
        return len(self._par_rva)

    def by_index(self, index: int) -> str:
        return self._valeurs[index]

    def rva_of(self, index: int) -> int | None:
        return self._rva[index]

    def by_rva(self, rva: int) -> str | None:
        """La valeur du slot d'adresse RELATIVE donnee. `None` = ce n'est pas un litteral."""
        i = self._par_rva.get(rva)
        return None if i is None else self._valeurs[i]

    def by_va(self, va: int) -> str | None:
        """Idem depuis une adresse ABSOLUE (ce que Ghidra affiche : `DAT_183386748`).

        La RVA est CALCULEE ici (`va - image_base`), l'image base etant lue dans le PE au
        moment de la production -- jamais une constante transcrite."""
        return self.by_rva(va - self.image_base)

    def index_of_rva(self, rva: int) -> int | None:
        return self._par_rva.get(rva)

    def find(self, fragment: str, limite: int = 50) -> list[tuple[int, int | None, str]]:
        """Les litteraux CONTENANT `fragment`, en (index, rva, valeur)."""
        out = []
        for i, v in enumerate(self._valeurs):
            if fragment in v:
                out.append((i, self._rva[i], v))
                if len(out) >= limite:
                    break
        return out

    def resolve_dats(self, texte: str) -> dict[int, str]:
        """Tous les `DAT_<hex>` d'un decompile qui sont des LITTERAUX, en {va: valeur}.

        Les autres `DAT_` (MethodInfo*, Il2CppClass*, statiques) sont simplement absents du
        resultat : ce n'est pas une erreur, c'est la reponse."""
        import re
        out: dict[int, str] = {}
        for m in set(re.findall(r"DAT_([0-9a-fA-F]{6,16})", texte)):
            va = int(m, 16)
            v = self.by_va(va)
            if v is not None:
                out[va] = v
        return out


def table_path(build: str) -> Path:
    return SYMBOLS / build / "metadata" / "string_literals.tsv"


def charger(build: str | None = None, dll: Path | None = None,
            verifier: bool = True, path: Path | None = None) -> TableLitteraux:
    """Charge la table. Par defaut, REFUSE si elle ne vient pas du binaire installe.

    `path` vise un fichier EXPLICITE (au lieu de le deriver du build). Il existe pour que le
    REFUS lui-meme soit testable : sans lui, on ne pourrait verifier qu'une table etrangere
    est bien rejetee qu'en salissant `data/symbols/`."""
    if build is None:
        cur = SYMBOLS / "CURRENT"
        if not cur.is_file():
            raise TableAbsente("data/symbols/CURRENT absent : build courant inconnu")
        build = cur.read_text(encoding="utf-8").strip()
    path = path or table_path(build)
    if not path.is_file():
        raise TableAbsente(
            "aucune table de litteraux pour le build %s (%s).\n"
            "  La produire :  python scripts/python/dump_string_literals.py" % (build, path))

    with path.open(encoding="utf-8") as fh:
        stamp_line = fh.readline()
        meta_line = fh.readline()
        corps = fh.read().splitlines()

    stamp = parse_stamp(stamp_line)
    if not meta_line.startswith("#!string-literals"):
        raise ProvenanceError("2e ligne inattendue dans %s : %r" % (path.name, meta_line[:80]))
    champs = dict(f.split("=", 1) for f in meta_line.strip().split("\t")[1:])
    image_base = int(champs["image_base"], 16)

    verifiee = False
    if verifier:
        ref = dll or installed_dll()
        if stamp["sha256"] != sha256_of(ref):
            raise ProvenanceError(
                "DESYNCHRONISATION -- la table de litteraux de %s ne vient PAS du binaire\n"
                "  courant (%s). Index ET RVA seraient resolus contre le mauvais build :\n"
                "  chaque `DAT_<slot>` rendrait une chaine PLAUSIBLE ET FAUSSE.\n"
                "  Regenerer :  python scripts/python/dump_string_literals.py"
                % (stamp.get("build", "?"), ref.parent.name))
        meta = ref.parent / META_REL
        attendu = stamp.get("metadata_sha256")
        # Le PE et le fichier de metadonnees sont DEUX artefacts : un repatch pourrait ne
        # toucher que le second, et c'est LUI dont cette table est tiree.
        if attendu and meta.is_file() and sha256_of(meta) != attendu:
            raise ProvenanceError(
                "DESYNCHRONISATION -- le `global-metadata.dat` installe n'est pas celui dont\n"
                "  la table est tiree (le PE, lui, concorde). Regenerer la table.")
        verifiee = True

    valeurs: list[str] = []
    rvas: list[int | None] = []
    for n, ligne in enumerate(corps):
        if not ligne:
            continue
        idx, r, v = ligne.split("\t", 2)
        if int(idx) != len(valeurs):
            raise ProvenanceError("table trouee : index %s a la ligne %d (attendu %d)"
                                  % (idx, n, len(valeurs)))
        valeurs.append(json.loads(v))
        rvas.append(None if r == "-" else int(r, 16))
    return TableLitteraux(build, image_base, verifiee, valeurs, rvas)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("whereis", "find", "stats"))
    ap.add_argument("argument", nargs="?", default="")
    ap.add_argument("--build", help="build cible (defaut : data/symbols/CURRENT)")
    ap.add_argument("--sans-verification", action="store_true",
                    help="consulter un build archive (le rapport le DIT)")
    args = ap.parse_args()

    try:
        t = charger(args.build, verifier=not args.sans_verification)
    except (TableAbsente, ProvenanceError) as exc:
        print("REFUS : %s" % exc)
        return 2

    if not t.verifiee:
        print("!! provenance NON VERIFIEE -- table du build %s, binaire non confronte" % t.build)

    if args.action == "stats":
        print("build=%s  litteraux=%d  slots joints=%d  image_base=0x%x"
              % (t.build, len(t), t.slots_joints, t.image_base))
        return 0

    if args.action == "whereis":
        va = int(args.argument, 16)
        # Une adresse peut etre donnee en VA (Ghidra) ou en RVA : on essaie les deux et on
        # DIT laquelle a repondu, plutot que d'en supposer une.
        v = t.by_va(va)
        forme = "VA"
        if v is None:
            v, forme = t.by_rva(va), "RVA"
        if v is None:
            print("0x%x n'est pas un slot de litteral de %s" % (va, t.build))
            return 1
        print("%s 0x%x -> %s" % (forme, va, json.dumps(v)))
        return 0

    for i, r, v in t.find(args.argument):
        print("%-7d %-12s %s" % (i, ("0x%x" % r) if r is not None else "-", json.dumps(v)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
