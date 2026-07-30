"""CLIQUET #314 -- aucun script de `scripts/python/**` ne cite la racine du depot
par CHEMIN ABSOLU.

La question binaire : *un probe execute depuis un worktree peut-il encore ecrire
dans l'arbre principal ?* Un litteral pointant la racine du depot par lettre de
lecteur rend la reponse OUI, silencieusement -- le script tourne dans le worktree
de l'agent mais ECRIT (ou LIT) dans l'arbre de l'orchestrateur. Constat
d'origine : apres un run de validation, `data/_lot4pose_main_state.json`
apparaissait dans le `git status` de l'arbre principal, et TROIS probes se
partageaient ce meme nom de fichier.

Ce fichier N'ECRIT DONC JAMAIS le motif en clair : les cas de test le composent
par CONCATENATION (`_SEG`). Ecrit tel quel, il se ferait attraper par son propre
balayage -- ce qui est arrive au premier jet, et c'est la meilleure preuve que le
cliquet n'exempte personne, pas meme son auteur.

Ce test est le pendant OFFLINE de `probe_273_gitignored_inputs.py --only-scan`
etape 0b : meme balayage, meme allowlist, aucune session Frida. Il tient le
zero -- c'est un cliquet, pas une cible : chaque nouveau script qui reintroduit
le motif le rouvre.

Regles de remplacement :
  * SORTIE de run  -> `Path(__file__).resolve().parents[2] / "logs" / ...`
    (relatif au CHECKOUT ; `logs/` est gitignore et meurt avec le worktree) ;
  * ENTREE hors-depot -> `host_inputs.require()` / `host_inputs.find()`, qui
    LEVE en nommant les chemins essayes au lieu de rendre un zero muet (#273).
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[1]          # scripts/python
ROOT = Path(__file__).resolve().parents[3]           # racine du checkout
sys.path.insert(0, str(PYDIR))

import probe_273_gitignored_inputs as p273           # noqa: E402

_BS = chr(92)                                        # antislash
_SEG = "tacticus" + "-tools"                         # jamais en clair : cf. docstring


def test_no_absolute_repo_path_in_scripts_python():
    hits = p273._scan_abs_repo(ROOT)
    offenders = []
    for f, lineno, snippet in hits:
        try:
            rel = f.relative_to(ROOT).as_posix()
        except ValueError:
            rel = f.as_posix()
        if f"{rel}:{lineno}" not in p273._ALLOWED_ABS:
            offenders.append(f"{rel}:{lineno}  {snippet}")
    assert not offenders, (
        "chemin ABSOLU vers la racine du depot -- un script lance depuis un "
        "WORKTREE ecrirait (ou lirait) dans l'ARBRE PRINCIPAL :\n  "
        + "\n  ".join(offenders)
        + "\nSortie de run -> logs/ RELATIF ; entree hors-depot -> host_inputs."
    )


def test_scanner_actually_catches_the_pattern(tmp_path):
    """Contre-epreuve : le balayage DETECTE bien le motif qu'il proscrit.

    Sans elle, un regex casse rendrait « 0 occurrence » et le test ci-dessus
    passerait au vert pour la mauvaise raison -- exactement le faux negatif que
    #273 a mesure ailleurs (`git check-ignore` sans `-z` : 0 gitignore, en
    silence).
    """
    d = tmp_path / "scripts" / "python"
    d.mkdir(parents=True)
    (d / "_mutation.py").write_text(
        'STATE = Path(r"C:' + _BS + 'Users' + _BS + 'x' + _BS + _SEG
        + _BS + 'data' + _BS + '_x.json")\n', encoding="utf-8")
    (d / "_clean.py").write_text(
        'STATE = Path(__file__).resolve().parents[2] / "logs" / "_x.json"\n',
        encoding="utf-8")
    hits = p273._scan_abs_repo(tmp_path)
    names = sorted(f.name for f, _, _ in hits)
    assert names == ["_mutation.py"], names


def test_forward_slash_and_missing_trailing_separator(tmp_path):
    """Les DEUX formes qu'un premier jet du balayage ratait.

    Une racine SANS separateur final (puis `ROOT / "logs"`) perce l'isolation
    exactement comme un chemin complet : 7 fichiers sur 22 n'etaient visibles
    que par cette forme. La forme a slash avant doit tomber aussi.
    """
    d = tmp_path / "scripts" / "python"
    d.mkdir(parents=True)
    (d / "_no_sep.py").write_text(
        'ROOT = Path(r"C:' + _BS + 'Users' + _BS + 'x' + _BS + _SEG + '")\n',
        encoding="utf-8")
    (d / "_slash.py").write_text(
        "DECOMP = 'C:/Users/x/" + _SEG + "/data/decompiled_tacticus/'\n",
        encoding="utf-8")
    (d / "_prose.py").write_text(
        '"""' + _SEG + ' -- campagne de portage (mention en prose)."""\n',
        encoding="utf-8")
    (d / "_game_install.py").write_text(
        'DLL = Path(r"C:' + _BS + 'Users' + _BS + 'x' + _BS + 'AppData' + _BS
        + 'Local' + _BS + 'tacticus' + _BS + 'games' + _BS + 'rnca9r7q6c'
        + _BS + 'GameAssembly.dll")\n', encoding="utf-8")
    names = sorted(f.name for f, _, _ in p273._scan_abs_repo(tmp_path))
    # `_prose.py` : mention sans lettre de lecteur -> pas un chemin.
    # `_game_install.py` : l'INSTALLATION du jeu est hors depot et partagee par
    # nature -- la proscrire casserait tous les probes qui lisent la DLL.
    assert names == ["_no_sep.py", "_slash.py"], names
