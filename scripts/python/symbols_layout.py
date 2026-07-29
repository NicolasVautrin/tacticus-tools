#!/usr/bin/env python3
"""Ou vivent les tables de symboles, et LEQUEL des builds fait foi.

POURQUOI CE MODULE EXISTE
-------------------------
`data/symbols/` porte UN REPERTOIRE PAR BUILD (`<HASH>/BUILD`, `<HASH>/frida/*.tsv`,
`<HASH>/ghidra/functions.tsv`, `<HASH>/gameconfig.json`). Jusqu'au 2026-07-29 les outils
supposaient qu'il n'y en avait QU'UN, et la garde `symbols_sync.py` ECHOUAIT des qu'il y en
avait deux : « PLUSIEURS builds versionnes : lequel fait foi ? ». La seule sortie proposee
etait de SUPPRIMER l'ancien.

C'est un mauvais marche. Ce que la garde protege reellement, c'est « la table lue correspond-
elle au binaire installe ? » -- et elle sait deja le verifier par sha256. La MULTIPLICITE
n'etait qu'un PROXY d'ambiguite. En nommant explicitement le build courant, le controle
devient EXACT et la multiplicite cesse d'etre un probleme : on peut garder l'historique des
builds sans affaiblir la garde.

Ce que la conservation permet, et que la suppression interdisait :
  * diffe `enums.tsv` / `classes.tsv` entre deux builds A TOUT MOMENT -- pas seulement dans la
    fenetre de la migration. C'est LE seul moyen de voir une struct redisposee ou un enum
    renumerote (cf. la MAJ gqfc5mff6c -> rnca9r7q6c : QUATRE enums renumerotes, tache #252) ;
  * diffe `ghidra/functions.tsv` (apparitions / disparitions / renommages) sans course contre
    une suppression ;
  * comparer les gameconfig d'un build a l'autre.

LE FICHIER `data/symbols/CURRENT`
---------------------------------
Une ligne, le hash du build qui FAIT FOI. Versionne. Il remplace le `cat data/symbols/*/BUILD`
de la procedure, qui rendait plusieurs valeurs des qu'un ancien build trainait.

Ce que ce module NE fait PAS : deviner. Un `CURRENT` qui nomme un repertoire absent est une
ERREUR DURE, pas un cas a rattraper -- un pointeur casse qui retomberait silencieusement sur
« le seul autre repertoire » recreerait exactement la faute qu'on elimine.

`GhidraApplyIl2CppSymbols.java` n'utilise PAS ce pointeur et c'est VOULU : il balaye
`data/symbols/*/frida/` et retient celui dont l'estampille porte le sha256 du binaire qu'il a
CHARGE. Discriminer par le contenu est strictement plus sur que suivre un pointeur ; on ne le
degrade pas.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SYMBOLS = REPO / "data" / "symbols"
CURRENT_FILE = SYMBOLS / "CURRENT"


class LayoutError(RuntimeError):
    """Disposition de `data/symbols/` inexploitable -- toujours bloquant."""


def _build_dirs() -> list[Path]:
    if not SYMBOLS.is_dir():
        raise LayoutError("data/symbols absent -- aucune table de symboles versionnee")
    return [d for d in sorted(SYMBOLS.iterdir()) if d.is_dir()]


def current_build() -> str:
    """Le hash du build qui FAIT FOI.

    1. `data/symbols/CURRENT` s'il existe -- son contenu est la reponse, et un repertoire
       manquant est une erreur DURE (jamais de repli silencieux).
    2. sinon, s'il n'y a QU'UN repertoire, c'est lui (compatibilite : depots d'avant CURRENT).
    3. sinon, erreur -- et le correctif est d'ECRIRE `CURRENT`, pas de supprimer un build.
    """
    if CURRENT_FILE.is_file():
        nom = CURRENT_FILE.read_text(encoding="utf-8").strip()
        if not nom:
            raise LayoutError("data/symbols/CURRENT est vide -- y ecrire le hash du build courant")
        if not (SYMBOLS / nom).is_dir():
            raise LayoutError(
                "data/symbols/CURRENT designe '%s', mais data/symbols/%s n'existe pas.\n"
                "  Pointeur casse : corriger CURRENT ou restaurer le repertoire. On ne devine PAS."
                % (nom, nom))
        return nom
    dirs = _build_dirs()
    if not dirs:
        raise LayoutError("data/symbols vide -- aucune table de symboles versionnee")
    if len(dirs) > 1:
        raise LayoutError(
            "PLUSIEURS builds versionnes (%s) et pas de data/symbols/CURRENT : lequel fait foi ?\n"
            "  Ecrire le hash du build courant dans data/symbols/CURRENT -- les autres deviennent\n"
            "  des ARCHIVES, conservees exprès (leur diff EST le rapport de changement du jeu)."
            % ", ".join(d.name for d in dirs))
    return dirs[0].name


def build_dir(build: str | None = None) -> Path:
    """Le repertoire d'un build (celui qui fait foi par defaut). Erreur dure s'il manque."""
    nom = build or current_build()
    p = SYMBOLS / nom
    if not p.is_dir():
        raise LayoutError("data/symbols/%s absent" % nom)
    return p


def archived_builds() -> list[str]:
    """Les builds versionnes AUTRES que celui qui fait foi -- conserves pour le diff."""
    courant = current_build()
    return [d.name for d in _build_dirs() if d.name != courant]
