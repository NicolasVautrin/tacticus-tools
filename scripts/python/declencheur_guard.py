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

PRESENCE **ET** FORME -- ET POURQUOI LA PRESENCE SEULE ETAIT UN FAUX VERT (#486-r27)
-------------------------------------------------------------------------------------
Ce garde ne validait QUE LA PRESENCE (`getattr(module, NOM) is not None`) et n'appelait JAMAIS
`declencheur_cliquet.valider`. Or c'est le SEUL gate qu'un auteur interroge reellement : la
FORME et la CONFRONTATION n'etaient jugees que par `probe_486r15`, qu'aucune passe de test ne
joue et dont l'obligation est levee depuis le 2026-08-07.

MESURE (PR #824) : `test_448_r1_r1_r2_r2_gates_abandon_offline.py` est passe avec **DEUX cles
sur quatre** (`build` et `raison` absentes) et un chemin non couvert, et son auteur a ecrit noir
sur blanc << `DECLENCHEUR` pose pour garder rc 0 >>. Le gate qu'il a interroge lui a repondu
VERT. Un dict a deux cles n'est pas une declaration -- c'est un jeton pose pour faire taire un
garde, et le garde le prenait pour argent comptant.

L'ARBITRAGE EST TRANCHE PAR LE COUT, et il est mesurable :
  * la FORME est ici. `valider` n'ouvre AUCUN fichier et ne parse RIEN -- il inspecte un `dict`
    DEJA EN MEMOIRE (le module est importe, la constante est un objet Python). Son module
    n'importe que `ast`/`re`/`pathlib`, du stdlib. Le cout reste celui du `getattr` ;
  * la CONFRONTATION reste dans `probe_486r15`. Elle exige une fermeture d'imports PAR FICHIER
    (~440 modules pour un seul test) : impayable dans un hook qui tourne a CHAQUE passe, y
    compris les passes live a 4 workers.

La DETTE ne tolere que l'ABSENCE. Une declaration PRESENTE mais mal formee est une faute meme
pour un fichier de la dette : il a cesse de s'appuyer sur la tolerance au moment ou il a ecrit
la constante. `DECLENCHEUR_PAR_ENTREE` n'est PAS valide ici -- `valider_par_entree` a besoin des
ids de banque du script, donc d'une lecture de `ratchets.ps1` : c'est de l'I/O, elle reste au
probe.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import os
from pathlib import Path

import declencheur_cliquet as DC

#: Nom de la constante, au niveau module. MEME nom que pour les cliquets (`declencheur_cliquet`) :
#: une seconde convention rendrait les deux moities inapariables.
NOM = "DECLENCHEUR"

ENV_ALLOW = "TACTICUS_ALLOW_SANS_DECLENCHEUR"

RACINE = Path(__file__).resolve().parents[2]
DETTE = RACINE / "scripts" / "ratchets-486r15-dette-declencheurs.txt"

#: Etat de module : les hooks de session n'ont pas de porteur naturel, et pytest ne rejoue pas un
#: plugin dans le meme processus. Meme forme que `green_skip_guard._DESELECTIONNES`.
#:
#: `rel -> None` = declaration ABSENTE (tolerable par la dette) ; `rel -> [fautes]` = declaration
#: PRESENTE mais MAL FORMEE (#486-r27), jamais tolerable : le fichier a cesse de s'appuyer sur la
#: dette au moment ou il a ecrit la constante.
_MANQUANTS: dict = {}


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
        vus[rel] = getattr(module, NOM, None)
    for rel, decl in vus.items():
        if decl is None:
            if rel not in toleres:
                _MANQUANTS[rel] = None
            continue
        # PRESENTE : on la VALIDE (#486-r27). La dette ne couvre que l'ABSENCE -- un fichier qui
        # ecrit la constante a cesse de s'appuyer sur elle. `valider` est pur : il inspecte un
        # dict deja en memoire, sans ouvrir ni parser quoi que ce soit.
        fautes = DC.valider(decl)
        if fautes:
            _MANQUANTS[rel] = fautes


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
    return sorted(fautifs())


def fautifs() -> dict:
    """`rel -> None (absente) | [fautes de forme]`, filtre des reactifs synthetiques."""
    if not _MANQUANTS:
        return {}
    suivis = _suivis_par_git()
    if suivis is None:
        return dict(_MANQUANTS)
    return {rel: v for rel, v in _MANQUANTS.items() if rel in suivis}


def pytest_terminal_summary(terminalreporter, exitstatus, config):   # noqa: D103
    faux = fautifs()
    if not faux:
        return
    absentes = sorted(r for r, v in faux.items() if v is None)
    malformees = sorted((r, v) for r, v in faux.items() if v is not None)
    ecrire = terminalreporter.write_line
    ecrire("")
    if absentes:
        ecrire("[486r15] %d fichier(s) de test COLLECTE(S) sans `%s` et hors dette :"
               % (len(absentes), NOM))
        for rel in absentes[:12]:
            ecrire("           %s" % rel)
    if malformees:
        # #486-r27 : la PRESENCE ne suffit pas. Un dict a deux cles est un jeton pose pour
        # faire taire un garde, pas une declaration -- et c'est le gate que l'auteur interroge.
        ecrire("[486r15] %d fichier(s) de test COLLECTE(S) dont le `%s` est MAL FORME "
               "(#486-r27) :" % (len(malformees), NOM))
        for rel, fautes in malformees[:8]:
            ecrire("           %s" % rel)
            for f in fautes[:4]:
                ecrire("               - %s" % f)
        ecrire("[486r15] La DETTE ne tolere que l'ABSENCE : un fichier qui ECRIT la constante a")
        ecrire("[486r15] cesse de s'appuyer sur elle. Aide : `python scripts/python/probe_486r15"
               "_declencheurs_tests.py --proposer <fichier>`.")
    ecrire("[486r15] Un fichier de test doit DIRE ce qui doit changer pour qu'il puisse changer")
    ecrire("[486r15] de verdict. Modele : `scripts/python/tests/test_486r15_empreinte_par_"
           "entree_offline.py`.")
    ecrire("[486r15] Le defaut est `toujours: True` AVEC sa raison -- c'est un RESULTAT, pas un")
    ecrire("[486r15] aveu. Trop LARGE est sain ; trop ETROIT est un faux vert.")
    ecrire("[486r15] Ce garde juge la PRESENCE et la FORME. La CONFRONTATION du perimetre a ce")
    ecrire("[486r15] que le fichier LIT reellement reste a `probe_486r15` -- elle coute une")
    ecrire("[486r15] fermeture d'imports par fichier, impayable a chaque passe.")
    ecrire("[486r15] Echappatoire consciente : %s=1" % ENV_ALLOW)


def pytest_sessionfinish(session, exitstatus):                       # noqa: D103
    if manquants() and session.exitstatus == 0:
        session.exitstatus = 1
