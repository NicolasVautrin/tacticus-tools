"""#486-r15 -- GARDE A LA COLLECTE : un fichier de test COLLECTE doit porter son `DECLENCHEUR`.

L'OBLIGATION, ET POURQUOI ELLE N'EST PAS UN HERITAGE
-----------------------------------------------------
La demande est : nul test ne doit pouvoir exister sans avoir declare ce qui doit changer pour
qu'il puisse changer de verdict. La forme spontanee -- une classe de base `TestOffline` portant
`should_trigger = False`, que les derivees seraient << obligees >> de surcharger -- ne tient pas,
et deux mesures le disent :

  * corpus reel du 2026-08-07 : **711 fichiers de test, 5 080 tests, 100 % en FONCTIONS de
    module, ZERO methode de classe**. L'heritage exigerait de convertir 5 080 tests dans 711
    fichiers, sur precisement le code qui garde tout le reste ;
  * en Python, heriter NE FORCE AUCUNE SURCHARGE. Une derivee distraite heriterait
    SILENCIEUSEMENT de `False` et cesserait d'etre jouee, sans un mot. C'est exactement #455
    (`test_summon_trait_effects_live.py` : 8 skipped / 0 passed / rc 0 sur `master`, zero
    assertion evaluee, trouve en ECARTANT une PR).

Un CLIQUET tient l'obligation que l'heritage promet sans la tenir : le fichier distrait ne
devient pas invisible, il CASSE.

LE CRITERE EST LA COLLECTE, PAS LA SELECTION
----------------------------------------------
`-k` / `-m` / `--deselect` filtrent APRES la collecte, et un nodeid explicite n'emet aucun report
de collecte : c'est la lecon de #455-r3, et c'est pourquoi ce garde lit les ITEMS COLLECTES
(`pytest_collection_modifyitems`) et non ce qui finit par tourner.

COUT NUL, ET C'EST LE POINT. La declaration est lue par `getattr` sur le MODULE DEJA IMPORTE --
ni lecture de fichier, ni `ast.parse`. Un garde de collecte qui ouvrirait 711 fichiers a chaque
passe couterait plus que les tests qu'il garde (les 165 fichiers offline les plus legers pesent
13,1 s A EUX TOUS).

LA DETTE, ET POURQUOI ELLE EXISTE
-----------------------------------
Poser l'obligation seche rendrait `master` ROUGE sur 711 fichiers le jour de sa livraison -- donc
la ferait desarmer dans l'heure. `scripts/ratchets-486r15-dette-declencheurs.txt` liste
l'existant TOLERE ; un fichier qui n'y est pas et ne declare pas est ROUGE tout de suite. La
dette est VERSIONNEE, donc tout elargissement apparait dans un diff : elle ne peut pas se
degrader en silence.

ECHAPPATOIRE CONSCIENTE : `TACTICUS_ALLOW_SANS_DECLENCHEUR=1`. Comme `TACTICUS_ALLOW_GREEN_SKIP`
(#455), c'est un geste, pas un defaut.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import os
from pathlib import Path

#: Nom de la constante, au niveau module. MEME nom que pour les cliquets (`declencheur_cliquet`) :
#: une seconde convention rendrait les deux moities inapariables.
NOM = "DECLENCHEUR"

ENV_ALLOW = "TACTICUS_ALLOW_SANS_DECLENCHEUR"

RACINE = Path(__file__).resolve().parents[2]
DETTE = RACINE / "scripts" / "ratchets-486r15-dette-declencheurs.txt"

#: Etat de module : les hooks de session n'ont pas de porteur naturel, et pytest ne rejoue pas un
#: plugin dans le meme processus. Meme forme que `green_skip_guard._DESELECTIONNES`.
_MANQUANTS: set = set()


def _rel(chemin) -> str:
    q = str(chemin).replace("\\", "/")
    r = str(RACINE).replace("\\", "/").rstrip("/") + "/"
    return q[len(r):] if q.lower().startswith(r.lower()) else q


def dette() -> set:
    """Les fichiers TOLERES sans declaration. Fichier absent -> ensemble VIDE (critere SEC).

    Un fichier de dette absent ne doit surtout pas se degrader en << tout est tolere >> : le sens
    sur est l'inverse, et c'est celui-ci."""
    try:
        lignes = DETTE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    return {l.strip() for l in lignes if l.strip() and not l.startswith("#")}


def pytest_collection_modifyitems(session, config, items):     # noqa: D103
    if os.environ.get(ENV_ALLOW):
        return
    toleres = dette()
    vus = {}
    for item in items:
        module = getattr(item, "module", None)
        if module is None:                       # item sans module (DoctestItem, ...) : hors sujet
            continue
        rel = _rel(getattr(item, "path", "") or getattr(module, "__file__", ""))
        if rel in vus:
            continue
        vus[rel] = getattr(module, NOM, None) is not None
    for rel, declare in vus.items():
        if not declare and rel not in toleres:
            _MANQUANTS.add(rel)


def _suivis_par_git() -> set:
    """Les fichiers de test VERSIONNES. `None` si git n'a pas repondu -- jamais un ensemble vide.

    POURQUOI CE FILTRE, ET POURQUOI IL EST PARESSEUX. Plusieurs cliquets de ce depot deposent des
    fichiers de test SYNTHETIQUES sous `tests/` pour prouver qu'un garde mord (`probe_455` le fait
    explicitement). Exiger d'eux une declaration n'aurait aucun sens : ils ne sont pas du code
    livre, ils sont le REACTIF d'une contre-epreuve.

    PARESSEUX parce que l'appel coute ~250 ms : il n'est fait que si au moins un candidat a ete
    trouve, c'est-a-dire jamais en regime nominal (l'existant est couvert par la dette).

    TRI-ETAT : git muet rend `None`, et l'appelant garde alors TOUS les candidats -- sur-selectionner
    un rouge est sain, l'inverse serait un faux vert.
    """
    import subprocess
    try:
        p = subprocess.run(["git", "-C", str(RACINE), "ls-files", "scripts/python/tests"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError:
        return None
    if p.returncode != 0:
        return None
    return {l.strip() for l in p.stdout.splitlines() if l.strip()}


def manquants() -> list:
    """Les fichiers en faute, filtres des reactifs synthetiques. Vide = rien a signaler."""
    if not _MANQUANTS:
        return []
    suivis = _suivis_par_git()
    if suivis is None:
        return sorted(_MANQUANTS)
    return sorted(rel for rel in _MANQUANTS if rel in suivis)


def pytest_terminal_summary(terminalreporter, exitstatus, config):   # noqa: D103
    fautifs = manquants()
    if not fautifs:
        return
    ecrire = terminalreporter.write_line
    ecrire("")
    ecrire("[486r15] %d fichier(s) de test COLLECTE(S) sans `%s` et hors dette :"
           % (len(fautifs), NOM))
    for rel in fautifs[:12]:
        ecrire("           %s" % rel)
    ecrire("[486r15] Un fichier de test doit DIRE ce qui doit changer pour qu'il puisse changer")
    ecrire("[486r15] de verdict. Modele : `scripts/python/tests/test_486r15_empreinte_par_"
           "entree_offline.py`.")
    ecrire("[486r15] Le defaut est `toujours: True` AVEC sa raison -- c'est un RESULTAT, pas un")
    ecrire("[486r15] aveu. Trop LARGE est sain ; trop ETROIT est un faux vert.")
    ecrire("[486r15] Echappatoire consciente : %s=1" % ENV_ALLOW)


def pytest_sessionfinish(session, exitstatus):                       # noqa: D103
    if manquants() and session.exitstatus == 0:
        session.exitstatus = 1
