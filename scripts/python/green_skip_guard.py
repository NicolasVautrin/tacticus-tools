"""Garde-fou #455 -- un FICHIER de test qui n'a RIEN confronte, sous ses deux formes.

DEUX CRITERES, UN SEUL VICE
---------------------------
  * `passed == 0 and skipped > 0`  -- le fichier INTEGRALEMENT SKIPPE (#455) ;
  * 0 TEST COLLECTE                -- le fichier dont les tests ont DISPARU (#455-r3).

Le second n'est pas une variante du premier : il lui est structurellement INVISIBLE. Le critere
de bilan lit des REPORTS D'EXECUTION, et un fichier sans test n'en emet AUCUN -- il ne figure meme
pas dans `stats`. Detail et mesures : la section « #455-r3 » plus bas.

LE GISEMENT
-----------
`test_summon_trait_effects_live.py` rendait **8 skipped, 0 passed** sur `origin/master` -- rc 0,
banniere verte, ZERO assertion evaluee. Il a ete trouve en ECARTANT une PR, pas cherche : rien dans
le depot ne le signalait.

Le skip n'est PAS le defaut. C'est la bonne reponse a un montage qui rate : un test qui echouerait
franchement sur un montage impossible serait un faux rouge, et demeler un rouge de MONTAGE d'un
rouge de PORT a deja coute des heures ici. Le defaut, c'est qu'un fichier INTEGRALEMENT skippe **ne
se voit pas** : la suite le compte comme un succes.

L'echelle qui compte est donc le FICHIER, pas le test. Un test skippe parmi dix qui passent est une
information ; un fichier ou RIEN n'a ete evalue est un vert qui ment -- il occupe la place d'une
garde et n'en est plus une.

CE QUE CE PLUGIN N'EST PAS
--------------------------
Ce n'est pas le pendant du bloc « un SKIP harnais indisponible est un ECHEC » de
`tests/conftest.py` (#77), et les deux ne se recouvrent pas. Celui-la lit la RAISON d'un skip
(cap de runners, drain, session absente, amorce KO) et la convertit test par test. Celui-ci ne lit
AUCUNE raison : il lit un BILAN, a l'echelle du fichier. Un skip de MONTAGE parfaitement legitime
-- « la cible n'a pas de tuile libre au contact » -- ne porte aucun marqueur de harnais, passe donc
intact le premier garde, et c'est exactement ce qui a rendu #455 invisible.

QUAND IL SE TAIT (et pourquoi ce sont les seuls cas)
----------------------------------------------------
Le bilan d'un fichier ne conclut que si la SELECTION a ete COMPLETE. Trois causes de bilan partiel,
toutes lues sur la session -- aucune n'est saisie :
  * des items DESELECTIONNES (`-k`, `-m`, `--deselect`, `--lf`) -> hook `pytest_deselected` ;
  * un nodeid EXPLICITE en argument (`fichier.py::test_x`) -> `config.args` ;
  * une session INTERROMPUE (`-x`, `--maxfail`, KeyboardInterrupt) -> `session.shouldstop`.
Plus l'echappatoire CONSCIENTE `TACTICUS_ALLOW_GREEN_SKIP=1`, deja utilisee par le garde #77 pour
inspecter la collecte sans jeu lance (sans elle, TOUT fichier live serait 100 % skippe et le
verdict n'apprendrait rien).

`xfail`/`xpass` comptent comme JOUES : l'assertion a bien ete evaluee, son echec etait attendu.

OU IL EST BRANCHE
-----------------
`tests/conftest.py` importe ses hooks (un conftest non-racine ne peut pas declarer
`pytest_plugins`). Le garde vit ICI, et pas dans le conftest, pour etre chargeable par `-p
green_skip_guard` sur un repertoire arbitraire -- c'est ce qui rend le cliquet `probe_455` capable
de le mettre a l'epreuve sur des fichiers de test SYNTHETIQUES, hors de la suite reelle.

Cliquet : `probe_455_all_skipped_file.py` (banque `scripts/ratchets.ps1`). Il prouve les DEUX sens
(rouge sur un fichier inerte, vert sans) ET le CABLAGE (un fichier synthetique depose sous
`scripts/python/tests/` rougit sans aucun `-p`, donc via le conftest de production).

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import os

#: Variable d'echappement -- la MEME que le garde #77 de `tests/conftest.py`. Un seul geste
#: conscient debranche les deux : « je regarde la collecte, je ne valide rien ».
ENV_ALLOW = "TACTICUS_ALLOW_GREEN_SKIP"

#: Fichiers dont la selection est PARTIELLE (deselection). Etat de module : les hooks de session
#: n'ont pas de porteur naturel, et pytest ne rejoue pas un plugin dans le meme processus.
_DESELECTIONNES: set = set()

_VIDE = {"passed": 0, "skipped": 0, "failed": 0, "error": 0, "xfailed": 0, "xpassed": 0}


def _fichier(nodeid: str) -> str:
    """Chemin du fichier porteur d'un nodeid (`a/b.py::Classe::test` -> `a/b.py`)."""
    return (nodeid or "").split("::")[0].replace("\\", "/")


def pytest_deselected(items):
    """Un item deselectionne rend le bilan de SON fichier partiel -- on n'en conclura rien."""
    for it in items:
        f = _fichier(getattr(it, "nodeid", ""))
        if f:
            _DESELECTIONNES.add(f)


def bilan_par_fichier(stats: dict) -> dict:
    """{fichier: {passed, skipped, failed, error, xfailed, xpassed}} depuis `terminalreporter.stats`.

    UN report par phase (`setup`/`call`/`teardown`) : `passed` ne se compte que sur `call`, sinon
    chaque test passant en vaudrait trois. Un test skippe AVANT son appel (fixture, `skipif`)
    n'emet, lui, qu'un report `setup` skipped -- d'ou le comptage des skips sur toutes les phases.
    """
    out: dict = {}
    for reports in stats.values():
        for rep in reports:
            nodeid = getattr(rep, "nodeid", None)
            when = getattr(rep, "when", None)
            if not nodeid or when is None:
                continue                       # entrees de synthese, warnings, ...
            d = out.setdefault(_fichier(nodeid), dict(_VIDE))
            xfail = hasattr(rep, "wasxfail")
            if rep.failed:
                d["failed" if when == "call" else "error"] += 1
            elif rep.skipped:
                d["xfailed" if xfail else "skipped"] += 1
            elif when == "call":
                d["xpassed" if xfail else "passed"] += 1
    return out


def fichiers_inertes(stats: dict, args=(), interrompu: bool = False) -> dict:
    """Sous-ensemble du bilan retenu par le critere `passed == 0 and skipped > 0`.

    Vide des que la selection est partielle (cf. docstring du module) : le silence est alors la
    reponse JUSTE, pas une exemption."""
    if os.environ.get(ENV_ALLOW) == "1" or interrompu:
        return {}
    partiels = set(_DESELECTIONNES)
    for a in (args or ()):
        if "::" in str(a):
            partiels.add(_fichier(str(a)))
    return {f: b for f, b in bilan_par_fichier(stats).items()
            if f not in partiels and b["passed"] == 0 and b["skipped"] > 0
            and b["xfailed"] == 0 and b["xpassed"] == 0}


def _interrompu(session) -> bool:
    """Session ARRETEE en cours de route (`-x`, `--maxfail`, KeyboardInterrupt) : les fichiers non
    atteints n'ont aucun report et ceux en cours ont un bilan tronque -- on ne conclut rien."""
    return bool(getattr(session, "shouldstop", False) or getattr(session, "shouldfail", False))


# ==============================================================================================
#  #455-r3 -- LE FICHIER A 0 TEST COLLECTE. Meme vice, autre porte : l'INVISIBILITE.
# ==============================================================================================
#
# Le critere de bilan ci-dessus lit `terminalreporter.stats`, donc des REPORTS D'EXECUTION. Un
# fichier dont TOUS les tests ont disparu n'en emet AUCUN : il n'apparait pas dans `stats`, donc
# `bilan_par_fichier` ne le connait pas, donc `fichiers_inertes` ne peut pas le retenir. Ce n'est
# pas un reglage a elargir -- il n'y a rien a lire.
#
# MESURE DU 2026-08-03. Un `test_x.py` sans test, joue A COTE d'un fichier sain : `rc=0`, aucun
# rapport de garde. Joue SEUL, il rend `rc=5` (`EXIT_NOTESTSCOLLECTED`) -- et c'est exactement ce
# qui masque le trou, puisque personne ne joue un fichier seul.
#
# LE SIGNAL EST LA COLLECTE, PAS LA SELECTION. C'est lui qui separe les quatre causes d'un fichier
# a 0 test SANS aucune allowlist -- un perimetre saisi a la main est le vice recurrent de ce depot.
# Les quatre, et leur discriminant MESURE :
#
#   * tests SUPPRIMES        le `CollectReport` du Module est `passed` et aucun ITEM terminal
#                            n'apparait sous ce fichier.  <- C'EST LE GISEMENT.
#   * fichier FILTRE a 100 % `-k` / `-m` / `--deselect` filtrent APRES la collecte : `report.result`
#                            est INCHANGE. Mesure : `test_deux.py` garde ses deux `Function` sous
#                            `-k test_a`. Immunise STRUCTURELLEMENT, rien a declarer.
#   * nodeid EXPLICITE       pytest court-circuite le Module, qui n'emet AUCUN report de collecte
#                            (mesure : la session rend directement `[Function]`). Immunise de meme.
#   * fichier de SUPPORT     il ne matche pas `python_files`, donc pytest ne le collecte pas. Le
#                            depot tient deja cette convention -- ses 24 helpers sous `tests/` sont
#                            prefixes `_`, et 0 des 530 `test_*.py` est sans test.
#   * collecte EN ECHEC      `report.failed` (import KO) : pytest rend deja `rc=2`. On ne le double
#                            pas -- ce garde ne voit que ce que rien d'autre ne voit.
#
# CE VOLET NE LIT PAS `terminalreporter.stats`. Son etat vient des hooks de collecte, donc il
# survit a `-p no:terminal` -- le residu #455-r2 ne le concerne pas (il reste ouvert pour l'autre
# critere). Il n'a pas non plus de garde « session interrompue » : un module non atteint n'emet
# aucun report de collecte, donc il n'entre jamais dans le calcul.

#: Fichiers dont un collecteur a REUSSI, et fichiers sous lesquels au moins un ITEM terminal est
#: apparu. C'est leur DIFFERENCE qui porte le critere.
_COLLECTES: set = set()
_AVEC_ITEM: set = set()


def _est_item(noeud) -> bool:
    """Un ITEM terminal (`Function`) plutot qu'un COLLECTEUR (`Module`, `Class`).

    `isinstance(noeud, pytest.Item)` serait l'ecriture directe. Elle est ecartee pour deux
    raisons : elle imposerait a ce module d'importer `pytest` pour etre seulement LU, et surtout
    elle le rendrait INTESTABLE hors d'une vraie session -- on ne fabrique pas un `pytest.Item`
    sans son machinery, donc l'auto-test du cliquet ne pourrait pas exercer ce chemin.
    Le discriminant retenu est celui que pytest expose dans ses deux classes de base : un `Item`
    porte `runtest`, un `Collector` porte `collect`. L'etape 1 du cliquet le confronte a de VRAIS
    noeuds pytest (classe vide, `__test__ = False`), ou une equivalence supposee se verrait."""
    return hasattr(noeud, "runtest")


def pytest_collectreport(report):
    """Alimente les deux ensembles depuis la COLLECTE (cf. le bloc ci-dessus).

    Un `Class` vide compte : son propre report porte le meme fichier et un `result` vide, donc le
    fichier reste hors de `_AVEC_ITEM` -- mesure du 2026-08-03 sur `class TestVide: pass`, que le
    seul report du Module (`result=[Class]`) aurait laisse passer."""
    if not getattr(report, "passed", False):
        return                                   # collecte EN ECHEC : pytest rend deja rc=2
    fichier = _fichier(getattr(report, "nodeid", "") or "")
    if not fichier.endswith(".py"):
        return                                   # Session, Dir, Package : pas un fichier de test
    _COLLECTES.add(fichier)
    for noeud in getattr(report, "result", ()) or ():
        if _est_item(noeud):
            _AVEC_ITEM.add(fichier)
            break


def fichiers_sans_test() -> list:
    """Les fichiers COLLECTES sans qu'un seul test en sorte. Vide sous l'echappatoire consciente."""
    if os.environ.get(ENV_ALLOW) == "1":
        return []
    return sorted(_COLLECTES - _AVEC_ITEM)


def pytest_sessionstart(session):
    """Rend la session lisible depuis `pytest_terminal_summary`, dont l'ordre d'appel par rapport
    a notre `pytest_sessionfinish` n'est pas garanti.

    Remet aussi a zero l'etat de collecte : `pytest.main` peut etre appele PLUSIEURS FOIS dans un
    meme process (c'est ce que font `probe_457` et ses mutants), et un plugin n'est pas re-importe
    entre deux sessions -- sans ce clear, la seconde heriterait des fichiers de la premiere."""
    _COLLECTES.clear()
    _AVEC_ITEM.clear()
    session.config._green_skip_session = session


def _lignes(inertes: dict) -> list:
    """Le rapport, en ASCII strict."""
    out = ["%d fichier(s) de test INERTE(S) -- aucune assertion evaluee, et la suite les compte "
           "comme un succes." % len(inertes)]
    for f in sorted(inertes):
        b = inertes[f]
        detail = "%d skipped" % b["skipped"]
        if b["failed"] or b["error"]:
            detail += ", %d failed, %d error" % (b["failed"], b["error"])
        out.append("  %s : 0 passed, %s" % (f, detail))
    out += [
        "",
        "Le skip n'est pas le defaut -- l'INVISIBILITE l'est. Ventiler chaque fichier :",
        "  * montage REPARABLE  -> le reparer (le skip disparait de lui-meme) ;",
        "  * montage IMPOSSIBLE -> le NOMMER (residu, case-doc) et faire echouer le montage",
        "    plutot que le skipper (#268), ou retirer le fichier.",
        "Inspection sans jeu lance : %s=1 (geste conscient, jamais un defaut)." % ENV_ALLOW,
    ]
    return out


def _lignes_sans_test(fichiers: list) -> list:
    """Le rapport du volet #455-r3, en ASCII strict."""
    out = ["%d fichier(s) de test COLLECTE(S) SANS AUCUN TEST -- rien n'a ete confronte, et la "
           "suite les compte comme un succes." % len(fichiers)]
    out += ["  %s : 0 test collecte" % f for f in fichiers]
    out += [
        "",
        "Ce n'est PAS une selection partielle : `-k`, `-m` et `--deselect` filtrent APRES la",
        "collecte, et un nodeid explicite n'emet aucun report de collecte. Ventiler :",
        "  * tests SUPPRIMES par erreur -> les restaurer ;",
        "  * fichier devenu SANS OBJET  -> le retirer du depot ;",
        "  * helper mal NOMME           -> le renommer hors de `python_files` (`_x.py`).",
        "Inspection sans jeu lance : %s=1 (geste conscient, jamais un defaut)." % ENV_ALLOW,
    ]
    return out


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Section de resume -- le seul endroit ou le gisement se LIT."""
    inertes = fichiers_inertes(getattr(terminalreporter, "stats", {}) or {},
                               args=getattr(config, "args", ()) or (),
                               interrompu=_interrompu(getattr(config, "_green_skip_session", None)))
    if inertes:
        terminalreporter.write_sep("=", "FICHIERS 100 POURCENT SKIPPES (#455)", red=True, bold=True)
        for ln in _lignes(inertes):
            terminalreporter.write_line(ln)

    vides = fichiers_sans_test()
    if vides:
        terminalreporter.write_sep("=", "FICHIERS SANS AUCUN TEST (#455-r3)", red=True, bold=True)
        for ln in _lignes_sans_test(vides):
            terminalreporter.write_line(ln)


def pytest_sessionfinish(session, exitstatus):
    """Le verdict : un fichier qui n'a rien confronte rend la passe ROUGE.

    Le volet #455-r3 est evalue MEME SANS terminalreporter : son etat vient de la collecte, pas
    de `stats`. Le sortir de la garde `tr is None` est ce qui le rend insensible au residu
    #455-r2 (`-p no:terminal` fait taire l'autre critere, sans le dire)."""
    if fichiers_sans_test() and session.exitstatus == 0:
        session.exitstatus = 1

    tr = session.config.pluginmanager.get_plugin("terminalreporter")
    if tr is None:                                    # `-p no:terminal` : pas de stats agregees
        return
    inertes = fichiers_inertes(getattr(tr, "stats", {}) or {},
                               args=getattr(session.config, "args", ()) or (),
                               interrompu=_interrompu(session))
    if inertes and session.exitstatus == 0:
        session.exitstatus = 1
