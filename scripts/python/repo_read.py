"""Lecture PARALLELE de l'arbre -- meme texte que `Path.read_text`, pour un cinquieme du temps.

CE QUE CE MODULE CORRIGE, ET LA MESURE QUI L'ETABLIT (#457-r6)
--------------------------------------------------------------
Une dizaine de cliquets de `scripts/ratchets.ps1` balaient le meme arbre. On croyait leur cout
dominant dans `ast.parse` ; il ne l'est pas. Mesure du 2026-08-03, machine calme, arbre du
worktree (3254 fichiers versionnes, 58,7 Mo) :

    lecture en SERIE, dans un process FRAIS      16,8 s
    lecture en SERIE, 2e passe du MEME process    0,4 s
    lecture en 16 THREADS, process frais       3,3 - 7,6 s
    decodage utf-8 + fins de ligne des 58,7 Mo    0,16 s
    `ast.parse` de tout `scripts/python/**`        7,1 s

Autrement dit : **l'OUVERTURE des fichiers pesait plus que tout l'AST reuni**, et elle ne se
paie qu'au PREMIER acces de chaque processus. La ventilation par racine le localise -- sur les
memes 58,7 Mo, `scripts/` coute 7,4 ms par fichier quand `data/` en coute 0,75 et `docs/` 0,65 :
c'est un filtre systeme a l'ouverture (antivirus), qui vise les extensions executables. Le
constat n'est pas neuf -- `probe_273` le porte depuis #409, avec son propre lecteur a 16 threads.
Ce module GENERALISE cette recette au lieu de la laisser dans un seul probe.

L'`open()` bloque HORS du GIL : des threads suffisent, aucun `multiprocessing` n'est requis, et
le parallelisme de la banque n'est pas double (16 threads d'E/S bloquante, pas 16 coeurs).

POURQUOI DES OCTETS, ET PAS DU TEXTE
------------------------------------
`Path.read_text(encoding="utf-8")` ouvre un `TextIOWrapper` : il decode et traduit les fins de
ligne de facon INCREMENTALE, tampon par tampon. `read_bytes` puis un `decode` EN BLOC rend
exactement la meme chaine -- `to_text` reproduit ici la traduction universelle -- pour 0,16 s
sur l'arbre entier. Chaque appelant garde donc SON traitement d'erreur, au meme endroit :
`OSError` a la lecture (element `None`), `UnicodeDecodeError` au decodage (leve par `to_text`).
C'est ce qui preserve les denominateurs imprimes par les cliquets : un fichier non-UTF-8 reste
ECARTE, jamais compte comme balaye.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

#: Au-dela de 16 le rendement est plat (mesure du 2026-08-03 : 8 -> 5,75 s, 16 -> 5,67 s,
#: 32 -> 5,78 s). On ne monte pas plus haut : la banque lance deja plusieurs cliquets a la fois.
WORKERS = 16


def read_bytes_many(paths, workers: int = WORKERS) -> list:
    """`[octets | None]`, ALIGNE sur `paths`. `None` = `OSError` a la lecture.

    L'alignement positionnel est ce qui permet a l'appelant de garder son `zip(paths, ...)` et
    donc son ordre : aucun cliquet ne doit voir son ordre de rapport changer.
    """
    paths = list(paths)
    if not paths:
        return []

    def _read(p):
        try:
            return Path(p).read_bytes()
        except OSError:
            return None

    # Un seul fichier ne rachete pas le cout d'un pool.
    if len(paths) == 1:
        return [_read(paths[0])]
    with ThreadPoolExecutor(max_workers=min(workers, len(paths))) as ex:
        return list(ex.map(_read, paths))


def to_text(data: bytes, errors: str = "strict") -> str:
    """Ce que `Path.read_text(encoding="utf-8")` aurait rendu pour ces octets.

    La traduction UNIVERSELLE des fins de ligne est celle du mode texte de Python : `\\r\\n` et
    `\\r` isoles deviennent `\\n`. Sans elle, un fichier a fins de ligne Windows changerait de
    longueur de ligne et decalerait tout releve fonde sur `splitlines()`.
    """
    return data.decode("utf-8", errors).replace("\r\n", "\n").replace("\r", "\n")


def read_texts(paths, workers: int = WORKERS, errors: str = "strict") -> list:
    """`[texte | None]`, aligne sur `paths` -- `None` si le fichier est ILLISIBLE OU NON-UTF-8.

    A n'utiliser que la ou l'appelant traitait DEJA les deux echecs de la meme facon (un
    `except (UnicodeDecodeError, OSError): continue`). Sinon, passer par `read_bytes_many` et
    decoder soi-meme, pour garder la distinction.
    """
    out = []
    for data in read_bytes_many(paths, workers):
        if data is None:
            out.append(None)
            continue
        try:
            out.append(to_text(data, errors))
        except UnicodeDecodeError:
            out.append(None)
    return out
