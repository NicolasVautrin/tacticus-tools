"""Garde-fou #455 -- un FICHIER de test dont le bilan est `passed == 0 and skipped > 0`.

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
(cap de runners, drain, session absente, warmup KO) et la convertit test par test. Celui-ci ne lit
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
`tests/conftest.py` importe ses trois hooks (un conftest non-racine ne peut pas declarer
`pytest_plugins`). Le garde vit ICI, et pas dans le conftest, pour etre chargeable par `-p
green_skip_guard` sur un repertoire arbitraire -- c'est ce qui rend le cliquet `probe_455` capable
de le mettre a l'epreuve sur des fichiers de test SYNTHETIQUES, hors de la suite reelle.

Cliquet : `probe_455_all_skipped_file.py` (banque `scripts/ratchets.ps1`). Il prouve les DEUX sens
(rouge sur un fichier 100 % skippe, vert sans) ET le CABLAGE (un fichier synthetique depose sous
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


def pytest_sessionstart(session):
    """Rend la session lisible depuis `pytest_terminal_summary`, dont l'ordre d'appel par rapport
    a notre `pytest_sessionfinish` n'est pas garanti."""
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


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Section de resume -- le seul endroit ou le gisement se LIT."""
    inertes = fichiers_inertes(getattr(terminalreporter, "stats", {}) or {},
                               args=getattr(config, "args", ()) or (),
                               interrompu=_interrompu(getattr(config, "_green_skip_session", None)))
    if not inertes:
        return
    terminalreporter.write_sep("=", "FICHIERS 100 POURCENT SKIPPES (#455)", red=True, bold=True)
    for ln in _lignes(inertes):
        terminalreporter.write_line(ln)


def pytest_sessionfinish(session, exitstatus):
    """Le verdict : un fichier inerte rend la passe ROUGE (sans lui, rien ne le signalerait)."""
    tr = session.config.pluginmanager.get_plugin("terminalreporter")
    if tr is None:                                    # `-p no:terminal` : pas de stats agregees
        return
    inertes = fichiers_inertes(getattr(tr, "stats", {}) or {},
                               args=getattr(session.config, "args", ()) or (),
                               interrompu=_interrompu(session))
    if inertes and session.exitstatus == 0:
        session.exitstatus = 1
