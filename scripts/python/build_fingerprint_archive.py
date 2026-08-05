#!/usr/bin/env python3
"""ARCHIVE de l'empreinte structurelle d'un build -- ou en est-elle, et est-elle encore
RECUPERABLE ? (#482-r3)

LE RENVERSEMENT QUI FONDE CE MODULE
-----------------------------------
L'empreinte structurelle (#482) repond a <<ce symbole a-t-il le meme corps entre deux
builds ?>>. Pour la calculer il faut les OCTETS du build -- et les octets d'un build
DISPARAISSENT : le lanceur Tacticus efface `AppData/Local/tacticus/games/<HASH>/` a chaque
mise a jour, sans preavis.

L'intuition dit : <<detecter le changement de build, puis archiver le sortant>>. Le signal
naturel est la divergence entre le hash installe et `data/symbols/CURRENT`. MESURE, ce signal
arrive TROP TARD, et la preuve est sur disque au moment ou ces lignes sont ecrites :

    games/            -> rnca9r7q6c seul (+ un `.temp` VIDE)
    data/symbols/     -> gqfc5mff6c ET rnca9r7q6c

La divergence `gqfc5mff6c` a bien ete detectable -- mais le `GameAssembly.dll` de
`gqfc5mff6c` avait DEJA disparu quand elle l'est devenue. Un dispositif declenche sur la
divergence n'aurait rien pu archiver. Meme forme exactement que la perte du gameconfig de
`gqfc5mff6c`, documentee dans le skill d'orchestration : <<on ne saura JAMAIS ce que cette
mise a jour a change dans les donnees>>.

Le critere exploitable est donc l'INVERSE, et il ne parle pas du build sortant :

    << le build COURANT a-t-il DEJA son empreinte archivee ? >>

Il se verifie a tout instant, il se REPARE tant que le `.dll` est la, et quand le build
devient sortant son empreinte est deja au chaud. On n'archive pas le passe : on archive le
present pour qu'il survive.

CE QUE CE MODULE NE FAIT PAS
----------------------------
Il ne CALCULE rien -- c'est le role de `fingerprint_functions.py archiver`, qui importe
capstone et coute ~70 s par build. Ce module-ci est un CAPTEUR : il ne lit que des noms de
fichiers et des en-tetes, parce qu'il est appele par la garde `symbols_sync.py`, elle-meme
branchee sur le hook `SessionStart` (budget 15 s, cout mesure de la garde ~1,3 s).

TRI-ETAT, PARTOUT (discipline de `host_inputs.py` et de `loop_status.py`)
------------------------------------------------------------------------
Deux sondes portent sur des repertoires qui vivent HORS du depot :

    ~/AppData/Local/tacticus/games/<build>/GameAssembly.dll     le binaire installe
    ~/ghidra-projects/ghidra_<build>/                           le projet Ghidra

Chacune rend True / False / None, et `None` veut dire PAS MESURE -- jamais rabattu sur un
False. La distinction porte le verdict : <<pas de projet Ghidra>> conclut PERDUE (definitif),
alors que <<repertoire des projets introuvable>> ne conclut RIEN (INDETERMINEE). Rabattre le
second sur le premier ferait declarer irrecuperable un materiel qui existe.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from il2cpp_provenance import GAMES_DIR, ProvenanceError, read_stamp  # noqa: E402
from symbols_layout import LayoutError, current_build  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SYMBOLS = REPO / "data" / "symbols"

# L'archive vit DANS le repertoire du build, a cote de `frida/` et `ghidra/`. Un build = un
# repertoire, tout ce qui le decrit au meme endroit -- meme regle que `gameconfig.json`.
#
# POURQUOI `data/` ET PAS `logs/`, alors que la doctrine dit <<logs/ = ce qu'on ECRIT>> :
# une empreinte de build est une ENTREE. Elle est produite UNE FOIS, jamais re-derivable
# apres la disparition du binaire, et relue pendant des mois. `logs/` est gitignore et MEURT
# avec le worktree qui l'a ecrit -- ce n'est pas une crainte, c'est une MESURE : les deux
# empreintes calculees par #482 (dont celle d'un build dont le `.dll` n'existe plus) etaient
# introuvables quelques heures apres, l'agent ayant travaille en worktree.
# `probe_273 --only-scan` etape 0c l'admet : le premier segment sous `data/` est `symbols`,
# qui EST une entree versionnee.
ARCHIVE_REL = ("fingerprints", "functions.tsv")

MAGIC = "#!empreinte-structurelle"

# Racine des projets Ghidra -- HORS du depot (ils pesaient 14 Go dans `data/`).
# `TACTICUS_GHIDRA_PROJECTS` est l'echappatoire quand ils vivent ailleurs ; posee, elle est
# le SEUL candidat (un repli silencieux re-fabriquerait la panne que le tri-etat elimine).
_ENV_PROJETS = "TACTICUS_GHIDRA_PROJECTS"


def racine_projets_ghidra() -> Path:
    surcharge = os.environ.get(_ENV_PROJETS)
    return Path(surcharge) if surcharge else (Path.home() / "ghidra-projects")


def archive_path(build: str) -> Path:
    return SYMBOLS.joinpath(build, *ARCHIVE_REL)


# ---------------------------------------------------------------------------
# SONDES TRI-ETAT -- True / False / None(=pas mesure)
# ---------------------------------------------------------------------------
def dll_present(build: str) -> bool | None:
    """Le `GameAssembly.dll` de ce build est-il encore sur disque ?

    `None` si le repertoire des builds installes n'existe pas : on regarderait dans le vide,
    et un `False` s'y lirait comme <<le binaire a disparu>>, ce qui est un verdict.
    """
    if not GAMES_DIR.is_dir():
        return None
    return (GAMES_DIR / build / "GameAssembly.dll").is_file()


def projet_ghidra(build: str) -> Path | None:
    """Le projet Ghidra de ce build, ou None s'il n'existe pas.

    Ne DIT PAS a lui seul si la mesure a pu se faire : voir `projets_mesurables()`.
    """
    p = racine_projets_ghidra() / ("ghidra_%s" % build)
    return p if p.is_dir() else None


def projets_mesurables() -> bool:
    """La racine des projets Ghidra est-elle lisible ? Sinon toute absence est INDETERMINEE."""
    return racine_projets_ghidra().is_dir()


# ---------------------------------------------------------------------------
# ETAT D'UN BUILD
# ---------------------------------------------------------------------------
#   ARCHIVEE            fichier present, en-tete coherente
#   DISCORDANTE         fichier present, en-tete absente / build faux / sha256 faux  -> ECHEC
#   SANS_TABLE          pas de `ghidra/functions.tsv` : l'empreinte n'est PAS calculable
#   RECUPERABLE_PE      absente, mais le binaire est sur disque    -> le moins cher (~70 s)
#   RECUPERABLE_GHIDRA  absente, binaire disparu, projet Ghidra la -> plus cher, encore possible
#   PERDUE              absente, ni binaire ni projet, les DEUX mesures faites -> irrecuperable
#   INDETERMINEE        absente, et une sonde au moins n'a PAS pu mesurer -> on ne conclut RIEN
ARCHIVEE = "ARCHIVEE"
DISCORDANTE = "DISCORDANTE"
SANS_TABLE = "SANS_TABLE"
RECUPERABLE_PE = "RECUPERABLE_PE"
RECUPERABLE_GHIDRA = "RECUPERABLE_GHIDRA"
PERDUE = "PERDUE"
INDETERMINEE = "INDETERMINEE"

# Ce qui doit faire ECHOUER une garde. `PERDUE` n'y est PAS : c'est un constat definitif,
# repeter une alarme qu'aucune action ne peut eteindre apprend a l'ignorer (meme raison que
# `PERTES_CONNUES` dans `symbols_sync.py`).
ETATS_ECHEC = (DISCORDANTE,)
# Ce qui appelle une ACTION possible AUJOURD'HUI, donc ce qui doit faire PARLER le hook.
ETATS_ACTIONNABLES = (RECUPERABLE_PE, RECUPERABLE_GHIDRA)


@dataclass
class EtatArchive:
    build: str
    etat: str
    detail: str
    commande: str = ""
    fonctions: int = 0
    courant: bool = False

    @property
    def actionnable(self) -> bool:
        return self.etat in ETATS_ACTIONNABLES

    @property
    def echec(self) -> bool:
        return self.etat in ETATS_ECHEC


def _entete(p: Path) -> dict | None:
    """1re ligne de l'archive, parsee en dict. None si absente ou sans marqueur."""
    try:
        with p.open(encoding="utf-8", errors="replace") as fh:
            ligne = fh.readline()
    except OSError:
        return None
    if not ligne.startswith(MAGIC):
        return None
    out = {}
    for champ in ligne.rstrip("\r\n").split("\t")[1:]:
        k, _, v = champ.partition("=")
        out[k] = v
    return out


def _sha_attendu(build: str) -> str | None:
    """sha256 du binaire d'origine, LU dans l'estampille versionnee de `frida/methods.tsv`.

    C'est un controle CROISE, pas circulaire : cette estampille vient du dump Frida
    (`preprocess_il2cpp_dump.py`), l'archive tient le sien du PE lu par pefile ou du champ
    `executableSHA256` qu'ecrit Ghidra. Deux chaines independantes qui doivent s'accorder --
    et c'est ce qui attrape une archive rangee sous le mauvais build.
    """
    try:
        return read_stamp(SYMBOLS / build / "frida" / "methods.tsv").get("sha256")
    except ProvenanceError:
        return None


def etat_archive(build: str, courant: bool = False) -> EtatArchive:
    p = archive_path(build)
    cmd_pe = ("python scripts/python/fingerprint_functions.py archiver --build %s" % build)
    cmd_gh = ("python scripts/python/fingerprint_functions.py archiver --build %s "
              "--depuis-ghidra" % build)

    if p.is_file():
        en = _entete(p)
        if en is None:
            return EtatArchive(build, DISCORDANTE,
                               "en-tete absente ou sans marqueur %s" % MAGIC,
                               commande=cmd_pe, courant=courant)
        if en.get("build") != build:
            return EtatArchive(build, DISCORDANTE,
                               "en-tete annonce build=%s, rangee sous %s"
                               % (en.get("build"), build), commande=cmd_pe, courant=courant)
        try:
            n = int(en.get("fonctions", "0"))
        except ValueError:
            n = 0
        if n <= 0:
            return EtatArchive(build, DISCORDANTE, "en-tete annonce fonctions=%s"
                               % en.get("fonctions"), commande=cmd_pe, courant=courant)
        attendu = _sha_attendu(build)
        vu = en.get("sha256")
        if attendu and vu and attendu != vu:
            return EtatArchive(
                build, DISCORDANTE,
                "sha256 de l'archive (%s...) != estampille frida/methods.tsv (%s...)"
                % (vu[:12], attendu[:12]), commande=cmd_pe, courant=courant, fonctions=n)
        if not vu:
            return EtatArchive(build, DISCORDANTE,
                               "en-tete sans sha256 : provenance du binaire inconnue",
                               commande=cmd_pe, courant=courant, fonctions=n)
        # Le croisement n'a pas TOUJOURS lieu : un build dont il ne reste que le projet Ghidra
        # n'a pas de `frida/methods.tsv` (le dump Frida exige le jeu qui tourne, et ce
        # jeu-la n'existe plus). L'archive reste valable -- elle porte son propre sha256, mesure
        # par Ghidra -- mais elle n'est verifiee que par UNE source. Le DIRE : sans ca,
        # <<ARCHIVEE>> se lit comme <<verifiee des deux cotes>>, ce qui est faux ici.
        confiance = ("" if attendu else
                     " ; sha256 NON CROISE (pas de frida/methods.tsv pour ce build)")
        return EtatArchive(build, ARCHIVEE, "%d fonctions, genere %s%s"
                           % (n, en.get("genere", "?"), confiance),
                           fonctions=n, courant=courant)

    # -- pas d'archive : par quelle voie est-elle encore calculable ?
    if not (SYMBOLS / build / "ghidra" / "functions.tsv").is_file():
        return EtatArchive(build, SANS_TABLE,
                           "ghidra/functions.tsv absent : aucun symbole a apparier, "
                           "l'empreinte n'est pas calculable", courant=courant)

    dll = dll_present(build)
    if dll:
        return EtatArchive(build, RECUPERABLE_PE,
                           "le GameAssembly.dll est encore sur disque -- "
                           "il disparaitra a la prochaine mise a jour du jeu",
                           commande=cmd_pe, courant=courant)

    proj = projet_ghidra(build)
    if proj is not None:
        return EtatArchive(build, RECUPERABLE_GHIDRA,
                           "binaire disparu ; le projet Ghidra %s le conserve" % proj.name,
                           commande=cmd_gh, courant=courant)

    if dll is None or not projets_mesurables():
        quoi = []
        if dll is None:
            quoi.append("%s illisible" % GAMES_DIR)
        if not projets_mesurables():
            quoi.append("%s illisible" % racine_projets_ghidra())
        return EtatArchive(build, INDETERMINEE,
                           "recuperabilite NON MESUREE (%s) -- ne pas lire ce silence "
                           "comme une perte" % ", ".join(quoi), courant=courant)

    return EtatArchive(build, PERDUE,
                       "ni binaire installe ni projet Ghidra : les corps de ce build "
                       "ne sont plus nulle part", courant=courant)


def builds_versionnes() -> list[str]:
    if not SYMBOLS.is_dir():
        return []
    return sorted(d.name for d in SYMBOLS.iterdir() if d.is_dir())


def inventaire() -> list[EtatArchive]:
    """Etat de CHAQUE build versionne, le courant en tete."""
    try:
        courant = current_build()
    except LayoutError:
        courant = ""
    return [etat_archive(b, courant=(b == courant))
            for b in sorted(builds_versionnes(), key=lambda b: (b != courant, b))]


def projets_orphelins() -> list[str] | None:
    """Projets Ghidra SANS repertoire `data/symbols/<build>` -- du materiel present que
    rien ne permet d'exploiter (pas de table de symboles versionnee).

    Rend `None` si la racine des projets n'est pas lisible : une liste vide dirait
    <<aucun orphelin>>, ce qui est un verdict qu'on n'a pas le droit de rendre.
    """
    if not projets_mesurables():
        return None
    connus = set(builds_versionnes())
    out = []
    for d in sorted(racine_projets_ghidra().iterdir()):
        if not d.is_dir() or not d.name.startswith("ghidra_"):
            continue
        nom = d.name[len("ghidra_"):]
        if nom not in connus:
            out.append(nom)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _imprimer(inv: list[EtatArchive]) -> None:
    for e in inv:
        marque = "*" if e.courant else " "
        print("  %s %-12s %-18s %s" % (marque, e.build, e.etat, e.detail))
        if e.commande:
            print("      -> %s" % e.commande)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", help="n'inspecter que ce build (defaut : tous)")
    args = ap.parse_args(argv)

    inv = [etat_archive(args.build)] if args.build else inventaire()
    print("ARCHIVE D'EMPREINTE STRUCTURELLE -- %d build(s) versionne(s)  (* = courant)"
          % len(inv))
    _imprimer(inv)

    orphelins = projets_orphelins()
    if orphelins is None:
        print("\n  projets Ghidra orphelins : NON MESURE (%s illisible)"
              % racine_projets_ghidra())
    elif orphelins:
        print("\n  %d projet(s) Ghidra SANS table de symboles versionnee : %s"
              % (len(orphelins), ", ".join(orphelins)))
        print("      Le materiel (les octets) existe, mais aucun `data/symbols/<build>/"
              "ghidra/functions.tsv`")
        print("      ne permet de l'apparier. Extraire la table AVANT de compter dessus.")

    echecs = [e for e in inv if e.echec]
    actions = [e for e in inv if e.actionnable]
    if echecs:
        print("\nRESULTAT: ECHEC -- %d archive(s) DISCORDANTE(s)" % len(echecs))
        return 1
    if actions:
        print("\nRESULTAT: %d archive(s) manquante(s) et ENCORE recuperable(s)" % len(actions))
        return 0
    print("\nRESULTAT: rien a archiver")
    return 0


if __name__ == "__main__":
    sys.exit(main())
