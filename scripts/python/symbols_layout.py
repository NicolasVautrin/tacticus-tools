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

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SYMBOLS = REPO / "data" / "symbols"
CURRENT_FILE = SYMBOLS / "CURRENT"

#: Ce module est importe par des outils qui vivent AILLEURS (probes, tests, `symbols_sync`), et
#: son repertoire n'est donc pas garanti sur `sys.path`. On l'y met plutot que de RECOPIER le
#: parseur d'estampille : deux implementations jumelles du meme format divergeraient.
_ICI = Path(__file__).resolve().parent
if str(_ICI) not in sys.path:
    sys.path.insert(0, str(_ICI))

import il2cpp_provenance as _prov   # noqa: E402  -- FORME B (liaison de MODULE)

#: Les tables ou l'estampille de provenance (`generated=<iso8601>`) est POSEE, dans l'ordre ou on
#: les interroge. Seules les tables `frida/` en portent une : `ghidra/functions.tsv` et
#: `fingerprints/functions.tsv` ont une 1re ligne `# build=...` qui n'est PAS ce format -- mesure
#: du 2026-08-18 sur les quatre builds versionnes, `read_stamp` y leve `ProvenanceError`.
_TABLES_ESTAMPILLEES = (("frida", "enums.tsv"), ("frida", "classes.tsv"), ("frida", "methods.tsv"))


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


def build_generated(build: str) -> "str | None":
    """L'horodatage `generated=<iso8601>` des tables d'un build, ou `None` = PAS MESURE.

    TRI-ETAT, jamais une chaine vide ni une date inventee : `None` veut dire << ce build ne porte
    aucune table estampillee >>, ce qui est un ETAT REEL du depot (mesure du 2026-08-18 :
    `kqkbjqfb6c`, archive par `630a9c59` pour conserver l'empreinte STRUCTURELLE d'un binaire
    disparu, n'a ni `frida/enums.tsv` ni aucune autre table estampillee).

    Les trois tables sont interrogees dans l'ordre et la PREMIERE lisible fait foi : elles sont
    produites par la meme passe, donc portent le meme horodatage -- verifie sur les trois builds
    qui en ont (`gqfc5mff6c` 2026-07-27T16:19:50, `rnca9r7q6c` 2026-07-29T13:08:41,
    `t6dpr4k06g` 2026-08-15T00:15:00, identiques entre `enums`, `classes` et `methods`).
    """
    rep = SYMBOLS / build
    for rel in _TABLES_ESTAMPILLEES:
        p = rep.joinpath(*rel)
        if not p.is_file():
            continue
        try:
            g = _prov.read_stamp(p).get("generated")
        except _prov.ProvenanceError:
            continue                      # table anterieure a la provenance : pas une date
        if g:
            return g
    return None


def builds_sans_date() -> list[str]:
    """Les builds versionnes dont l'horodatage n'est PAS mesurable. ENUMERABLES, jamais tus.

    Meme patron que `probe_283.builds_sans_table_enums` : un filtre MUET redevient un faux vert.
    Un appelant qui ordonne par date doit pouvoir NOMMER ce qu'il n'a pas su ordonner.
    """
    return [d.name for d in _build_dirs() if build_generated(d.name) is None]


def archived_builds() -> list[str]:
    """Les builds versionnes AUTRES que celui qui fait foi -- conserves pour le diff.

    ⚠ L'ORDRE EST CHRONOLOGIQUE QUAND IL EST MESURABLE, ET JAMAIS PRESENTE COMME TEL SINON
    (#10023-r2). Jusqu'au 2026-08-18 il venait de `sorted(SYMBOLS.iterdir())`, donc du NOM -- or
    un hash de build est ALEATOIRE, et rien ne garantissait l'accord des deux ordres. Ce n'etait
    pas une inquietude theorique : les deux ordres DIVERGENT DEJA sur le depot. `kqkbjqfb6c` est
    entre dans l'arbre le 2026-08-06 (`630a9c59`), soit APRES `rnca9r7q6c` (2026-07-29), et le
    tri par nom le place pourtant AVANT. La ligne de backlog qui ouvrait ce residu affirmait
    l'inverse (<< se trouvent etre dans l'ordre de sortie du jeu >>) : mesure, c'est faux.

    La date vient de l'estampille de provenance DEJA POSEE dans les tables (`generated=`), pas
    d'un fichier neuf : c'est la meme source que `symbols_sync._reference_la_plus_recente`, qui
    ordonnait deja par la. Un build NON DATABLE (`build_generated` -> `None`) ne peut pas etre
    ordonne : il est place EN FIN et reste ENUMERE par `builds_sans_date()`. On ne lui invente
    ni une date, ni un rang -- sa position en fin est une CONVENTION de tri total, pas une mesure,
    et tout consommateur qui en depend doit interroger `builds_sans_date()`.
    """
    courant = current_build()
    noms = [d.name for d in _build_dirs() if d.name != courant]
    #: Cle de tri TOTALE et DETERMINISTE : (pas de date ?, date, nom). Le nom departage deux
    #: builds de meme horodatage et rend l'ordre stable d'une execution a l'autre.
    return sorted(noms, key=lambda n: (build_generated(n) is None, build_generated(n) or "", n))
