"""#457-r5 -- GARDE : le perimetre de `probe_457` couvre TOUT fichier de test offline.

CE QU'IL EST SEUL A VOIR
------------------------
Un fichier de test offline que le cliquet `probe_457` n'ENUMERE PAS -- donc qui peut rougir sur
`master` sans que rien ne le dise, alors meme qu'un cliquet est cense garder ce gisement.

Mesure du 2026-08-02 : `TESTS_GLOB = "scripts/python/tests/**/test_*.py"` rendait 496 fichiers la
ou le depot en compte 519, parce que `**/` EXIGE un niveau intermediaire -- les 23 fichiers poses
DIRECTEMENT dans `tests/` en etaient exclus. 21 d'entre eux n'etaient joues par AUCUNE entree de
la banque (les 2 autres sont nommes a la main par `pytest_signatures` / `pytest_attestations`),
et ce sont des gardes de premier rang : build pin, host_inputs, identite de conftest, les quatre
ratchets d'enum, les voies d'attribution d'`unit_map`.

C'est le vice de #458 (`Path.match` n'etend pas `**`) sur un autre outil, et la CINQUIEME forme du
<< perimetre saisi au lieu d'etre derive >> -- ici le perimetre se voulait derive, mais la
semantique du glob le restreignait en silence.

POURQUOI CETTE FORME DE GARDE
-----------------------------
La verification est un ACCORD ENTRE DEUX DERIVATIONS INDEPENDANTES sur l'axe qui a casse :
`probe_457` enumere par un PATHSPEC passe a git ; cette garde enumere par un WALK DISQUE, puis
intersecte avec l'index (`git ls-files` SANS pathspec -- aucune semantique de glob possible).
Une seule des deux voies peut donc se tromper a la fois.

ANTI-VACUITE : deux ensembles VIDES seraient trivialement egaux. Chaque test asserte donc d'abord
que sa source n'est pas vide -- c'est la lecon du vert vacueux de #516, ou
`set([c]) == {c} | set([])` passait au vert sur un anneau vide.

ASCII only (cp1252).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_457_offline_tests_green as P                                # noqa: E402

REPO = PYDIR.parents[1]
TESTS_ROOT = PYDIR / "tests"


def _tracked_paths() -> set[str]:
    """Tous les chemins SUIVIS du depot, en relatif POSIX. Aucun pathspec : rien a mal interpreter."""
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                         cwd=str(REPO), check=True)
    return {line.strip() for line in out.stdout.splitlines() if line.strip()}


def _derived_by_disk_walk() -> set[str]:
    """Les fichiers de test offline, par WALK DISQUE puis intersection avec l'index.

    Voie INDEPENDANTE de celle du probe : c'est le systeme de fichiers qui enumere, pas git."""
    tracked = _tracked_paths()
    found = set()
    for path in TESTS_ROOT.rglob("*.py"):
        rel_repo = path.relative_to(REPO).as_posix()
        if rel_repo not in tracked:
            continue
        if path.name.endswith("_live.py") or not P._is_test_file(path.name):
            continue
        found.add(path.relative_to(PYDIR).as_posix())
    return found


def test_le_perimetre_egale_une_derivation_independante():
    """Accord exact entre le pathspec git du probe et un walk disque."""
    disk = _derived_by_disk_walk()
    assert len(disk) > 50, (
        "derivation par walk disque VIDE ou effondree (%d) -- la garde ne prouverait rien" % len(disk))

    probe = set(P.candidate_files())
    assert len(probe) > 50, "perimetre du probe effondre (%d fichiers)" % len(probe)

    manquants = sorted(disk - probe)
    en_trop = sorted(probe - disk)
    assert not manquants, (
        "%d fichier(s) de test offline INVISIBLES au cliquet (il ne peut donc pas les garder) :\n  %s"
        % (len(manquants), "\n  ".join(manquants)))
    assert not en_trop, (
        "%d fichier(s) enumeres par le probe mais absents du disque/index :\n  %s"
        % (len(en_trop), "\n  ".join(en_trop)))


def test_les_fichiers_a_la_racine_de_tests_sont_couverts():
    """La regression PRECISE de #457-r5 : `**/` excluait la profondeur 1.

    Formule comme une PROPRIETE (tous les fichiers de profondeur 1 sont couverts), jamais comme la
    liste figee des 23 trouves ce jour-la -- une liste en dur serait le perimetre SAISI qu'on ferme."""
    disk = _derived_by_disk_walk()
    profondeur1 = {rel for rel in disk if rel.count("/") == 1}
    assert profondeur1, (
        "aucun fichier de test offline directement dans `tests/` -- la garde est devenue VACUEUSE, "
        "elle ne peut plus voir revenir l'exclusion de la profondeur 1")

    probe = set(P.candidate_files())
    rates = sorted(profondeur1 - probe)
    assert not rates, (
        "%d fichier(s) de profondeur 1 exclus du perimetre -- c'est EXACTEMENT #457-r5 qui revient "
        "(un glob `**/` exige un niveau intermediaire) :\n  %s" % (len(rates), "\n  ".join(rates)))


@pytest.mark.parametrize("n", [1, 2, 3, 8, 12, 37])
def test_les_bins_partitionnent_le_perimetre_SANS_trou_ni_doublon(n):
    """#457-r6 -- le mode de defaillance a exclure ABSOLUMENT du partitionnement par cout.

    Un fichier qui tomberait dans ZERO bin ne serait jamais joue, sous un verdict VERT : le trou
    serait SILENCIEUX, exactement le vice que ce cliquet repare. Un fichier dans DEUX bins ne
    ment pas, mais double son cout. On asserte donc la PARTITION, pas seulement la couverture."""
    files = P.candidate_files()
    assert len(files) > 50, "perimetre effondre (%d) -- le test ne prouverait rien" % len(files)

    bins = P.bins_of(files, n, P._weights())
    assert len(bins) == n

    plat = [rel for b in bins for rel in b]
    assert sorted(plat) == sorted(files), "les bins ne partitionnent pas le perimetre"
    assert len(plat) == len(set(plat)), "un fichier apparait dans PLUSIEURS bins"


def test_la_partition_est_DETERMINISTE_entre_deux_appels():
    """Les 8 shards sont des PROCESSUS distincts : ils doivent calculer la MEME partition.

    Si `bins_of` dependait de l'ordre d'iteration d'un dict ou d'un tri instable, deux shards du
    meme run verraient des partitions differentes -- et un fichier pourrait n'etre joue par aucun."""
    files = P.candidate_files()
    poids = P._weights()
    assert P.bins_of(files, 8, poids) == P.bins_of(list(reversed(files)), 8, poids)


def test_le_partitionnement_EQUILIBRE_quand_les_poids_existent():
    """Sans cette propriete, le cout du shardage par cout serait paye sans son benefice.

    Mesure du 2026-08-02 : le repli md5 rendait 106 s pour `s7` contre 4,8 s pour `s3` -- un seul
    shard faisait TOUT le mur de la banque. Le critere porte sur le rapport max/moyenne, pas sur
    une valeur absolue (les poids se re-mesurent, l'equilibre doit tenir quand meme).

    Le plancher est le fichier le PLUS LOURD, insecable : on ne peut pas exiger mieux que lui."""
    poids = P._weights()
    if not poids:
        pytest.skip("aucun poids mesure (probe_457_durations.json absent) -- repli md5")

    files = P.candidate_files()
    charges = [sum(poids.get(r, 0.0) for r in b) for b in P.bins_of(files, 8, poids)]
    plancher = max(poids.get(r, 0.0) for r in files)
    moyenne = sum(charges) / len(charges)
    assert max(charges) <= max(plancher, moyenne) * 1.35, (
        "shards desequilibres : max=%.1f s, moyenne=%.1f s, plancher=%.1f s" % (
            max(charges), moyenne, plancher))


@pytest.mark.parametrize("name, attendu", [
    ("test_foo.py", True),          # convention pytest n1
    ("foo_test.py", True),          # convention pytest n2 -- absente du depot, mais collectee
    ("test_foo_live.py", True),     # `_is_test_file` ne juge PAS du live : c'est l'appelant qui filtre
    ("conftest.py", False),
    ("helper.py", False),
    ("test_foo.txt", False),
])
def test_le_critere_suit_les_deux_conventions_pytest(name, attendu):
    """`pytest.ini` ne pose pas `python_files` -- le defaut couvre `test_*.py` ET `*_test.py`.

    Un perimetre derive doit couvrir ce que pytest COLLECTE, pas ce qui se trouve exister."""
    assert P._is_test_file(name) is attendu
