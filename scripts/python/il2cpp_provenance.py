#!/usr/bin/env python3
"""PROVENANCE des artefacts IL2CPP : de QUEL binaire un dump/TSV a-t-il ete tire ?

POURQUOI CE MODULE EXISTE (incident 2026-07-25, mesure) :
`data/il2cpp_{methods,classes,enums}.tsv` et `data/il2cpp_full.json` dataient du 20 mai
(build de mai) alors que le projet Ghidra porte le build de juin `gqfc5mff6c`. Rien ne le
signalait : ni marqueur, ni en-tete, ni garde. Et `GhidraApplyIl2CppSymbols.java` lit ces
TSV **en dur** a la racine de `data/` -> un simple `run` du script aurait applique les noms
de MAI sur le binaire de JUIN, en silence, detruisant le seul artefact correct restant.
Preuve de l'ecart : `BattleQuery.ConvertRoundsToTurns` est a la RVA 0x10e25f0 dans les TSV,
et a 0x1058af0 dans le binaire courant (verifie au decompile).

LE PIVOT = le SHA256 du `GameAssembly.dll`. Pas le hash du dossier de build (il ne bouge pas
si le binaire est repatche en place), pas un fichier marqueur a cote (ca se perd : c'est
exactement ainsi que `data/win_dump` est devenu une junction morte). Le SHA256 voyage DANS
l'artefact, en 1re ligne, et ne peut pas s'en separer.

FORMAT (1re ligne de chaque TSV) :
    #!il2cpp-provenance\tsha256=<64 hex>\tbuild=<hash dossier>\tgenerated=<iso8601>\tsource=<fichier>

Les consommateurs (`GhidraApplyIl2CppSymbols.java`, outils Python) DOIVENT :
  - refuser si la ligne est ABSENTE (pas de provenance = artefact d'origine inconnue) ;
  - refuser si le sha256 ne correspond pas au binaire qu'ils s'appretent a modifier.
FAIL-CLOSED : sans preuve d'origine, on n'ecrit rien.
"""
from __future__ import annotations

import datetime
import hashlib
import re
from pathlib import Path

MAGIC = "#!il2cpp-provenance"
GAMES_DIR = Path.home() / "AppData" / "Local" / "tacticus" / "games"


class ProvenanceError(RuntimeError):
    """Provenance absente, illisible ou discordante — TOUJOURS bloquant."""


def installed_builds() -> list[Path]:
    """Dossiers de build installes (`.temp` exclu : ce n'est pas un build)."""
    if not GAMES_DIR.is_dir():
        return []
    return sorted(p for p in GAMES_DIR.iterdir()
                  if p.is_dir() and not p.name.startswith("."))


def installed_dll() -> Path:
    """Le `GameAssembly.dll` du build installe. Erreur si 0 ou >1 build (ambigu)."""
    builds = [b for b in installed_builds() if (b / "GameAssembly.dll").is_file()]
    if not builds:
        raise ProvenanceError(
            "aucun build Tacticus installe sous %s (le jeu est-il installe ?)" % GAMES_DIR)
    if len(builds) > 1:
        raise ProvenanceError(
            "PLUSIEURS builds installes (%s) : impossible de deduire lequel est courant.\n"
            "  Passer le binaire explicitement (--dll) pour lever l'ambiguite."
            % ", ".join(b.name for b in builds))
    return builds[0] / "GameAssembly.dll"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stamp_for(dll: Path, source: str = "") -> str:
    """Construit la ligne de provenance pour le binaire donne."""
    return "%s\tsha256=%s\tbuild=%s\tgenerated=%s\tsource=%s" % (
        MAGIC, sha256_of(dll), dll.parent.name,
        datetime.datetime.now().replace(microsecond=0).isoformat(), source)


def parse_stamp(line: str) -> dict:
    if not line.startswith(MAGIC):
        raise ProvenanceError("1re ligne sans marqueur de provenance")
    out = {}
    for field in line.rstrip("\r\n").split("\t")[1:]:
        k, _, v = field.partition("=")
        out[k] = v
    if not re.fullmatch(r"[0-9a-f]{64}", out.get("sha256", "")):
        raise ProvenanceError("provenance sans sha256 exploitable : %r" % line[:120])
    return out


def read_stamp(artifact: Path) -> dict:
    """Lit la provenance d'un artefact. Leve si absente/illisible (FAIL-CLOSED)."""
    if not artifact.is_file():
        raise ProvenanceError("artefact absent : %s" % artifact)
    with artifact.open(encoding="utf-8", errors="replace") as fh:
        first = fh.readline()
    try:
        return parse_stamp(first)
    except ProvenanceError as exc:
        raise ProvenanceError(
            "%s : %s.\n"
            "  Cet artefact a ete produit AVANT la mise en place de la provenance, ou par un\n"
            "  outil qui ne la pose pas. Son build d'origine est INCONNU -> il est INUTILISABLE\n"
            "  pour appliquer des symboles. Le regenerer :\n"
            "    1) dump live   : scripts/frida/dump-il2cpp-full.js -> data/il2cpp_full.json\n"
            "    2) TSV         : python scripts/python/preprocess_il2cpp_dump.py\n"
            % (artifact.name, exc))


def assert_matches(artifact: Path, dll: Path | None = None) -> dict:
    """Verifie qu'un artefact vient bien du binaire donne (defaut : le build installe)."""
    dll = dll or installed_dll()
    stamp = read_stamp(artifact)
    actual = sha256_of(dll)
    if stamp["sha256"] != actual:
        raise ProvenanceError(
            "DESYNCHRONISATION — %s ne vient PAS du binaire courant.\n"
            "  artefact  : sha256=%s  build=%s  genere=%s\n"
            "  binaire   : sha256=%s  build=%s\n"
            "  L'utiliser produirait des symboles FAUX en silence. Regenerer le dump."
            % (artifact.name, stamp["sha256"][:16] + "...", stamp.get("build", "?"),
               stamp.get("generated", "?"), actual[:16] + "...", dll.parent.name))
    return stamp


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Verifie la provenance d'artefacts IL2CPP.")
    ap.add_argument("artifacts", nargs="*", help="fichiers a verifier (defaut : les 3 TSV)")
    ap.add_argument("--dll", help="binaire de reference (defaut : le build installe)")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[2]
    paths = ([Path(a) for a in args.artifacts] or
             [repo / "data" / ("il2cpp_%s.tsv" % k) for k in ("methods", "classes", "enums")])
    dll = Path(args.dll) if args.dll else None

    rc = 0
    for p in paths:
        try:
            st = assert_matches(p, dll)
            print("OK      %-24s build=%s genere=%s" % (p.name, st.get("build"), st.get("generated")))
        except ProvenanceError as exc:
            print("REFUSE  %s\n        %s" % (p.name, str(exc).replace("\n", "\n        ")))
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
