"""Contre-epreuve de `probe_474_optional_locks` -- il doit ROUGIR sur son gisement (#439).

Un cliquet vert sur un arbre sain ne prouve RIEN tant qu'on n'a pas montre qu'il bascule.
Et sur une contre-epreuve, c'est le VERT qui est le resultat suspect : chaque scenario
verifie donc que sa mutation a MORDU avant de conclure.

Les mutations portent sur des TEXTES synthetiques et sur un monkeypatch, jamais sur les
fichiers du depot : la banque tourne en parallele, un cliquet qui salirait l'arbre le ferait
disparaitre sous les yeux d'un voisin (#455).

ASCII strict.
"""

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict
#: (#486-r15). Meme contrat que les cliquets de la banque (`declencheur_cliquet.py`).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des deux `conftest.py` et sa
        # fermeture. Aucun test ne les IMPORTE -- c'est de la semantique pytest -- et ils
        # portent le `green_skip_guard` de #455 plus trois fixtures `autouse`, dont le
        # verdict de CHAQUE test depend.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER, pose depuis la MESURE (empreinte #486-r15) : un seul
        # repertoire de deps, un seul temoin (`loop_status.py`), fermeture d'imports de trois
        # modules.
        "scripts/python/probe_474_optional_locks.py", "scripts/python/loop_status.py",
        "scripts/python/fleet_board.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Le probe sous test et les deux modules dont il verifie que les appels git portent "
              "`--no-optional-locks`. Sa dep MESUREE se reduit a un temoin unique -- "
              "`loop_status.py` -- et il monte ses depots git en repertoire jetable, hors de "
              "l'arbre.",
}

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import probe_474_optional_locks as P                                      # noqa: E402


# --------------------------------------------------------------------------- Python (AST)
@pytest.mark.parametrize("source,attendu,quoi", [
    ('argv = ["git", "status", "--porcelain"]', 1, "argv fautif nu"),
    ('argv = ["git", "-C", chemin, "status", "--porcelain=v2"]', 1,
     "un TROU (variable) apres -C ne doit pas faire sauter la sous-commande"),
    ('argv = ["git", "-c", "core.x=y", "status"]', 1, "-c consomme aussi sa valeur"),
    ('argv = ["git", "-C", c, "--no-optional-locks", *args]', 0,
     "le FOYER : *args est indecidable, on n accuse pas"),
    ('argv = ["git", "-C", c, *args]', 0, "argv indecidable : on n accuse pas"),
    ('argv = ["git", "-C", c, "--no-optional-locks", "status", "--porcelain"]', 0, "corrige"),
    ('argv = ["git", "--no-optional-locks", "status"]', 0, "corrige, option en tete"),
    ('argv = [r"C:\\Program Files\\Git\\cmd\\git.exe", "status"]', 1, "invoque par chemin"),
    ('argv = ["git", "add", "-A"]', 0, "add : le lock est une ECRITURE voulue"),
    ('argv = ["git", "diff", "--name-only"]', 0, "diff ne prend pas le lock (mesure 0/3)"),
    ('argv = ["git", "ls-files", "scripts"]', 0, "ls-files ne prend pas le lock"),
    ('argv = ["git", "describe", "--always"]', 0, "describe SANS --dirty ne le prend pas"),
    ('argv = ["git", "describe", "--dirty"]', 1, "describe --dirty le prend (mesure 1/3)"),
    ('# on lit l etat par git status --porcelain\nx = 1', 0, "COMMENTAIRE, pas du code"),
    ('"""Le garde-fou de l invariant est `git status`."""\nx = 1', 0, "DOCSTRING, pas du code"),
    ('x = "git status --porcelain"', 0, "chaine nue hors argv : pas une invocation"),
])
def test_ast_rougit_sur_son_gisement(source, attendu, quoi):
    fautes = P._fautes_python(source, "faux.py")
    assert len(fautes) == attendu, "%s -> %r" % (quoi, fautes)


# ---------------------------------------------------------------------------- PowerShell
@pytest.mark.parametrize("source,attendu,quoi", [
    ('$sale = @(git -C $repo status --porcelain --untracked-files=no)', 1,
     "la forme EXACTE du gisement de #474 (ratchets-bg.ps1)"),
    ('$sale = @(git -C $repo --no-optional-locks status --porcelain)', 0, "corrige"),
    ('git status', 1, "invocation nue"),
    ('& git status --short', 1, "appel par &"),
    ('# git status --porcelain sert de garde-fou', 0, "COMMENTAIRE"),
    ('   # $sale = @(git -C $repo status)', 0, "commentaire indente"),
    ('<#\n.SYNOPSIS git status quelque part\n#>\n$x = 1', 0, "bloc de commentaire"),
    ('git worktree list --porcelain', 0, "worktree list ne prend pas le lock"),
    ('git -C $repo rev-parse HEAD', 0, "rev-parse ne prend pas le lock"),
    ('$x = "git status"', 0, "chaine : pas en position de commande"),
])
def test_powershell_rougit_sur_son_gisement(source, attendu, quoi):
    fautes = P._fautes_powershell(source, "faux.ps1")
    assert len(fautes) == attendu, "%s -> %r" % (quoi, fautes)


# ------------------------------------------------------- etage 2 : le FOYER (comportement)
def test_etage_comportement_est_vert_sur_l_arbre_courant():
    assert P.etage_comportement() == 0


def test_etage_comportement_rougit_si_l_option_quitte_le_foyer(monkeypatch, capsys):
    """La regression que l'etage STATIQUE ne peut PAS voir.

    Dans `Sources.git`, l'option est posee a cote de `*args` : aucun littera n'y nomme
    `status`, donc l'AST est structurellement aveugle a son retrait. Seule la MESURE le voit.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import loop_status as LS

    def sans_option(self, *args):
        return self._run(["git", "-C", str(self.repo), *args])

    monkeypatch.setattr(LS.Sources, "git", sans_option)
    # la mutation a-t-elle MORDU ? (un patch qui ne prend pas rendrait un vert menteur)
    assert LS.Sources.git is sans_option

    assert P.etage_comportement() == 1
    assert "PREND `.git/index.lock`" in capsys.readouterr().out


# ------------------------------------------------------------- le perimetre est bien DERIVE
def test_le_perimetre_couvre_les_deux_porteurs_connus():
    """Les deux sites que #474 a identifies doivent etre DANS le perimetre analyse.

    Un cliquet dont le perimetre raterait son propre gisement serait vert pour rien.
    """
    out = P._git(["ls-files", "scripts"], "perimetre").stdout.splitlines()
    rels = {l.strip() for l in out}
    assert "scripts/ratchets-bg.ps1" in rels
    assert "scripts/python/loop_status.py" in rels
