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


#: Seuil d'equilibre : `max(charges) <= max(plancher, moyenne) * MARGE`. Le plancher est le fichier
#: le PLUS LOURD, insecable -- on ne peut pas exiger mieux que lui.
MARGE_EQUILIBRE = 1.35


def test_le_partitionnement_EQUILIBRE_quand_les_poids_existent():
    """Sans cette propriete, le cout du shardage par cout serait paye sans son benefice.

    Mesure du 2026-08-02 : le repli md5 rendait 106 s pour `s7` contre 4,8 s pour `s3` -- un seul
    shard faisait TOUT le mur de la banque. Le critere porte sur le rapport max/moyenne, pas sur
    une valeur absolue (les poids se re-mesurent, l'equilibre doit tenir quand meme).

    #463 -- LE CRITERE PORTE SUR LES SEULS FICHIERS PESES, et le nom de ce test l'annoncait deja
    (<< quand les poids existent >>). Un fichier de test offline NEUF n'a pas de poids ; `bins_of`
    lui donne le MAXIMUM connu (choix sur), donc il DEPLACE les vrais lourds et fait monter la
    charge maximale -- sans qu'aucun poids ne soit faux, sans le moindre risque de faux vert, et
    pour un defaut qui est une ABSENCE DE DONNEE, pas un desequilibre.

    Rougir dessus imposait 976,9 s de passe complete (mesure du 2026-08-04, 1471 tests) par PR, pour
    une OPTIMISATION de mur -- et l'asymetrie trahissait le mauvais calibrage : `logs/` est
    gitignore, donc un agent en worktree frais n'a AUCUN poids, ce test SKIPPE chez lui, et la
    garde ne tirait que dans l'arbre de l'orchestrateur, sur le chemin critique de livraison.

    Elle rougit toujours sur un desequilibre REEL (poids presents) -- prouve par MUTATION dans
    `test_le_critere_d_equilibre_REJETTE_une_partition_desequilibree`.
    """
    poids = P._weights()
    if not poids:
        pytest.skip("aucun poids mesure (logs/ratchets/457-durations.json absent) -- repli md5")

    files = P.candidate_files()
    diag = P.equilibre_des_bins(files, 8, poids)
    assert len(diag["peses"]) > 50, (
        "seulement %d fichier(s) PESES sur %d -- la garde ne prouverait rien ; rejouer "
        "`--measure`" % (len(diag["peses"]), len(files)))

    if diag["inconnus"]:
        # RAPPORTE, jamais bloquant : le remede coute quelques secondes (`--measure-missing`), et
        # le probe l'imprime lui-meme a chaque shard.
        print("[457-r5] %d fichier(s) SANS poids (mur sous-optimal, verdict inchange) : %s"
              % (len(diag["inconnus"]), ", ".join(sorted(diag["inconnus"])[:5])))

    assert diag["ratio"] <= MARGE_EQUILIBRE, (
        "shards desequilibres SUR LES FICHIERS PESES : max=%.1f s, moyenne=%.1f s, plancher=%.1f s "
        "(ratio %.2f > %.2f) -- %d peses, %d sans poids" % (
            max(diag["charges"]), diag["moyenne"], diag["plancher"], diag["ratio"],
            MARGE_EQUILIBRE, len(diag["peses"]), len(diag["inconnus"])))


#: Profil de poids REALISTE, fige depuis la queue lourde mesuree (case-457 SS7 : 268 / 258 / 234 /
#: 201 / 169 s) sur un fond de fichiers legers. Deterministe -- aucun `random` dans un garde.
def _profil_mesure(nb_neufs: int):
    poids = {"tests/lourd_%d.py" % i: v
             for i, v in enumerate((268.0, 258.0, 234.0, 201.0, 169.0))}
    poids.update({"tests/leger_%03d.py" % i: 4.0 for i in range(105)})
    return poids, sorted(poids) + ["tests/neuf_%d.py" % i for i in range(nb_neufs)]


def _ancien_critere(files, poids, n=8):
    """Le critere TEL QU'IL ETAIT avant #463 : la partition porte sur l'ensemble COMPLET, les
    fichiers sans poids comptant 0 dans les charges mais le MAXIMUM dans le placement."""
    charges = [sum(poids.get(r, 0.0) for r in b) for b in P.bins_of(files, n, poids)]
    plancher = max(poids.get(r, 0.0) for r in files)
    moyenne = sum(charges) / len(charges)
    reference = max(plancher, moyenne)
    return (max(charges) / reference if reference else 0.0), charges


def test_des_fichiers_SANS_poids_ne_font_PAS_rougir_la_garde_d_equilibre():
    """#463 -- la propriete que la degradation doit tenir, sur un profil de poids MESURE.

    Aucune dependance a `logs/` : un worktree frais joue ce test a l'identique. Sans cela, la
    propriete ne serait verifiable que la ou le defaut mordait -- c'est-a-dire nulle part chez un
    agent, puisque `logs/` est gitignore et que la garde y SKIPPE.

    ⚠ NUANCE MESUREE le 2026-08-04, qui corrige l'enonce << tout fichier neuf fait rougir >> : le
    declenchement est en `nb_neufs % 8`. Un fichier sans poids occupe un bin au poids MAXIMUM
    connu ; tant que les bins ainsi bloques sont moins de la moitie, LPT redistribue et le ratio
    reste sous la marge. Mesure sur ce profil, 0 a 8 neufs :
    ratio 1,000 / 1,000 / 1,000 / 1,104 / **1,381** / **1,623** / **1,836** / **1,963** / 1,000.
    Rouge pour 4 a 7, vert pour 0 a 3 et 8 -- et le ratio est INDEPENDANT du poids des legers
    (identique a 2,0 et 5,0 s), il est porte par la structure. Un seul fichier neuf ne suffit donc
    PAS ; c'est un lot (une tranche qui en ajoute 4+) qui bloquait la livraison.
    """
    poids, files = _profil_mesure(5)

    diag = P.equilibre_des_bins(files, 8, poids)
    assert diag["inconnus"] == ["tests/neuf_%d.py" % i for i in range(5)]
    assert len(diag["peses"]) == len(poids)
    assert diag["ratio"] <= MARGE_EQUILIBRE, (
        "la degradation ne tient pas : ratio %.3f sur un profil dont les fichiers PESES se "
        "partitionnent parfaitement" % diag["ratio"])

    # CONTRE-EPREUVE : sur ce MEME montage, l'ANCIEN critere rougit. Sans elle, l'assertion
    # ci-dessus serait un vert VACUEUX -- elle passerait sur un montage qui ne reproduit rien.
    ratio_avant, charges = _ancien_critere(files, poids)
    assert ratio_avant > MARGE_EQUILIBRE, (
        "l'ancien critere ne rougit PAS sur ce montage -- il ne reproduit donc pas #463 "
        "(ratio %.3f, charges=%s)" % (ratio_avant, [round(c) for c in charges]))


@pytest.mark.parametrize("k, rouge_avant", [(0, False), (3, False), (4, True), (7, True),
                                            (8, False)])
def test_la_degradation_tient_QUEL_QUE_SOIT_le_nombre_de_fichiers_neufs(k, rouge_avant):
    """La degradation ne doit pas dependre du reste modulo 8 -- sinon elle ne ferait que DEPLACER
    le seuil de blocage au lieu de le supprimer. Les cas `rouge_avant` sont ceux, MESURES, ou
    l'ancien critere bloquait la livraison."""
    poids, files = _profil_mesure(k)
    assert P.equilibre_des_bins(files, 8, poids)["ratio"] <= MARGE_EQUILIBRE
    assert (_ancien_critere(files, poids)[0] > MARGE_EQUILIBRE) is rouge_avant, (
        "le profil fige ne reproduit plus la mesure du 2026-08-04 pour %d fichier(s) neuf(s)" % k)


def test_le_critere_d_equilibre_REJETTE_une_partition_desequilibree():
    """MUTATION : la garde degradee doit toujours MORDRE. Deux montages independants.

    Sans ce test, la degradation ci-dessus serait indistinguable d'un desarmement."""
    # (a) Le gisement HISTORIQUE : la partition md5 (`shard_of`) repartit par NOMBRE, pas par COUT.
    #     Mesure du 2026-08-02 : elle avait concentre 4 fichiers lourds dans le seul `s7` (106 s
    #     isole contre 4,8 s pour `s3`). Meme jeu de poids, deux partitions -> LPT passe, md5 non.
    poids = {"leger%03d.py" % i: 1.0 for i in range(80)}
    poids.update({"lourd%d.py" % i: 90.0 for i in range(6)})
    files = sorted(poids)

    lpt = P.equilibre_des_bins(files, 8, poids)
    assert lpt["ratio"] <= MARGE_EQUILIBRE, "LPT devrait equilibrer ce jeu (ratio %.2f)" % lpt["ratio"]

    md5 = [sum(poids[r] for r in files if P.shard_of(r, 8) == k) for k in range(8)]
    moyenne = sum(md5) / len(md5)
    assert max(md5) > max(90.0, moyenne) * MARGE_EQUILIBRE, (
        "le critere ACCEPTE la partition md5 -- il ne distingue donc plus le shardage par cout du "
        "repli, et ne garde plus rien (charges md5=%s)" % md5)

    # (b) Un desequilibre INSECABLE mais REEL, tous poids presents : 9 fichiers egaux pour 8 bins.
    #     Aucun fichier sans poids -> la degradation de #463 ne s'applique pas, la garde doit tirer.
    egaux = {"e%d.py" % i: 10.0 for i in range(9)}
    diag = P.equilibre_des_bins(sorted(egaux), 8, egaux)
    assert diag["inconnus"] == [], "montage invalide : ce cas doit etre integralement PESE"
    assert diag["ratio"] > MARGE_EQUILIBRE, (
        "la garde ne rougit plus sur un desequilibre a poids COMPLETS (ratio %.2f, charges %s)"
        % (diag["ratio"], diag["charges"]))


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
