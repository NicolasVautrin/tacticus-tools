#!/usr/bin/env python3
"""#431-r1 -- garde du cliquet << un `**` ne part pas vers un matcher qui ne le developpe pas >>.

Ce que ce fichier tient, et que le probe seul ne tient pas : le probe MESURE (il rend le compte
du jour) ; ici on GARDE la propriete -- le critere discrimine, l'exemption de contre-epreuve
reste structurelle, et le perimetre reste l'ARBRE et non une liste de racines.

Le temoin fondateur (etage 1) est celui de #458 : `PurePath.match` ne developpe pas `**`. S'il
tombe, la CAUSE a change (une version de Python qui aligne `match` sur `full_match`), et alors
le cliquet lui-meme n'a plus le meme objet -- c'est ce qu'on veut apprendre, pas taire.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_431r1_globs_non_recursifs as P  # noqa: E402

DECLENCHEUR = {
    "chemins": ("scripts/python/probe_431r1_globs_non_recursifs.py",),
    "build": False,
    "toujours": False,
    "raison": "Ce fichier garde EXACTEMENT le cliquet #431-r1 : son critere, son exemption de "
              "contre-epreuve et la derivation de son perimetre. Rien d'autre ne le fait "
              "changer d'avis.",
}


# ================================================ 1. la CAUSE, isolee -- le temoin de #458
@pytest.mark.parametrize("rel", [
    "scripts/python/engine/runner/operations/triggers/loki/x.py",   # TROP profond
    "scripts/python/tests/engine/runner/test_x.py",                 # TROP profond
    "scripts/x.py",                                                 # PAS ASSEZ profond
])
def test_TEMOIN_PurePath_match_ne_developpe_toujours_pas_les_deux_etoiles(rel):
    """La cause du trou de 967 fichiers, en une ligne et sans balayage.

    `**` y vaut UN segment, et le match part de la DROITE -- donc le motif ne selectionne
    QUE la profondeur 3. Si cet assert tombe un jour, ce n'est pas une bonne nouvelle a
    ignorer : c'est que le langage a change sous le cliquet.
    """
    assert not Path(rel).match("scripts/**/*.py"), \
        "si ce temoin tombe, la cause de #458 a change -- re-deriver le diagnostic"


def test_TEMOIN_rglob_et_full_match_DEVELOPPENT_les_deux_etoiles(tmp_path):
    """Le pendant : les matchers HORS perimetre le sont parce qu'ils sont CORRECTS.

    Sans ce temoin, << rglob n'est pas compte >> serait indiscernable d'un oubli.
    """
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "x.py").write_text("", encoding="utf-8")
    assert [p.name for p in tmp_path.rglob("*.py")] == ["x.py"]
    if hasattr(Path, "full_match"):        # 3.13+
        assert Path("scripts/python/engine/x.py").full_match("scripts/**/*.py")


# ============================================ 2. le CRITERE discrimine (preuve de morsure)
def test_les_mutants_discriminent_tous():
    """La preuve de morsure du probe, rejouee ici comme GARDE.

    Le probe l'imprime a chaque run (idiome #421 : prouver la couverture dans le meme
    processus que la conformite) ; l'avoir aussi en test evite qu'un ecart parte en simple
    ligne de sortie qu'on ne lit pas.
    """
    ecarts = P.etape_morsure()
    assert ecarts == [], "le critere ne discrimine plus : " + " | ".join(ecarts)


def test_le_jeu_de_mutants_porte_les_DEUX_polarites():
    """Un jeu de mutants tout-positif prouverait la morsure, jamais l'absence de bruit.

    Assertionner son propre non-vide dans les deux sens : c'est ce qui a sauve le controle
    d'ordinaux de #270-r1-r1-r3, dont le premier ensemble etait VIDE.
    """
    positifs = [t for t, _s, a in P.MUTANTS if a > 0]
    negatifs = [t for t, _s, a in P.MUTANTS if a == 0]
    assert len(positifs) >= 3, "moins de 3 mutants FAUTIFS : la morsure n'est pas etablie"
    assert len(negatifs) >= 5, "moins de 5 mutants SAINS : le bruit n'est pas borne"


@pytest.mark.parametrize("src,attendu", [
    # les trois familles, une par matcher
    ("ok = Path(rel).match('scripts/**/*.py')\n", 1),
    ("import glob\nfs = glob.glob('a/**/b.py')\n", 1),
    ("from fnmatch import fnmatch\nok = fnmatch(r, 'a/**/b.py')\n", 1),
    # le meme motif, vers un matcher qui le developpe
    ("import glob\nfs = glob.glob('a/**/b.py', recursive=True)\n", 0),
    ("fs = list(root.rglob('*.py'))\n", 0),
    # un `**` qui n'est pas un glob de chemin
    ("out.append('- **PORTE** : %d')\n", 0),
    ("x = a ** b\n", 0),
])
def test_le_critere_par_famille(src, attendu):
    assert len(P.analyser("<t>", src)) == attendu


# ================================== 3. l'EXEMPTION de contre-epreuve est STRUCTURELLE
def test_une_contre_epreuve_assert_not_ne_rougit_PAS():
    """`assert not Path(x).match('a/**/b.py')` DEMONTRE le vice -- le compter le supprimerait.

    L'exemption se derive de la FORME (`assert not <appel>`), jamais d'une liste de chemins :
    une allowlist se perime et devient une echappatoire.
    """
    src = "assert not Path(rel).match('scripts/**/*.py')\n"
    assert P.analyser("<t>", src) == []


def test_mais_un_appel_NON_nie_rougit_dans_le_MEME_fichier():
    """La contre-partie exacte : l'exemption porte sur l'APPEL, pas sur le fichier.

    Sans ce cran, ecrire un seul `assert not` en tete d'un fichier le rendrait muet.
    """
    src = ("assert not Path(a).match('scripts/**/*.py')\n"
           "ok = Path(b).match('scripts/**/*.py')\n")
    fautes = P.analyser("<t>", src)
    assert len(fautes) == 1 and fautes[0][0] == 2


def test_un_regex_compile_teste_un_SUJET_pas_un_motif():
    """`RX.match(s)` prend la chaine a tester : un `**` dedans ne designe aucun chemin.

    Le nom lie par `re.compile` est releve DANS le fichier -- exact, pas heuristique.
    """
    assert P.analyser("<t>", "import re\nRX = re.compile('x')\nok = RX.match('a/**/b')\n") == []
    # ... et sans la liaison, le meme appel redevient suspect : c'est ce qui prouve que le
    # discriminant est bien la liaison, pas le nom.
    assert len(P.analyser("<t>", "ok = RX.match('a/**/b.py')\n")) == 1


# ====================================== 4. le PERIMETRE est l'ARBRE, pas une liste de racines
def test_le_perimetre_est_derive_de_git_ls_files():
    """La lecon de #458 : une liste de racines se perime EN SILENCE.

    On ne verifie pas un compte (il bouge a chaque commit) mais la PROPRIETE : le perimetre
    contient des fichiers a des profondeurs differentes, y compris hors `scripts/python/`.
    """
    fichiers = P.tracked_py()
    assert len(fichiers) > 1000, "perimetre suspect : %d fichiers" % len(fichiers)
    profondeurs = {f.count("/") for f in fichiers}
    assert len(profondeurs) >= 4, \
        "le perimetre ne voit qu'une poignee de profondeurs -- regression de #458 : %s" \
        % sorted(profondeurs)
    assert any(f.startswith("scripts/python/engine/") for f in fichiers), \
        "engine/** hors perimetre : c'est EXACTEMENT le trou de #458"
    assert any(f.startswith("scripts/python/tests/") for f in fichiers), \
        "tests/** hors perimetre : c'est EXACTEMENT le trou de #458"


def test_le_cliquet_est_VERT_sur_l_arbre_courant():
    """Le zero du jour. Il n'est pas un acquis : c'est ce que le cliquet MAINTIENT."""
    fautes = []
    for rel in P.tracked_py():
        src = (P.REPO / rel).read_text(encoding="utf-8", errors="replace")
        try:
            fautes += [(rel,) + f for f in P.analyser(rel, src)]
        except SyntaxError as exc:
            pytest.fail("%s ne parse pas : %s" % (rel, exc))
    assert fautes == [], "motif(s) recursif(s) vers un matcher non recursif : %r" % (fautes[:5],)


def test_le_probe_porte_son_DECLENCHEUR():
    """Contrat de forme (#486) : un cliquet declare ce qui le fait changer d'avis."""
    src = (P.REPO / "scripts/python/probe_431r1_globs_non_recursifs.py").read_text(
        encoding="utf-8")
    arbre = ast.parse(src)
    decl = None
    for node in arbre.body:
        cibles = node.targets if isinstance(node, ast.Assign) else []
        if any(isinstance(t, ast.Name) and t.id == "DECLENCHEUR" for t in cibles):
            decl = ast.literal_eval(node.value)
    assert decl is not None, "le probe ne declare pas de DECLENCHEUR"
    assert set(decl) >= {"chemins", "build", "toujours", "raison"}
    assert len(decl["raison"]) >= 40
