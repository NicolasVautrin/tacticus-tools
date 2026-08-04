"""#457-r8 -- garde de la SELECTION PAR DIFF de `probe_457` (`--since`).

Une selection par diff est le SEUL endroit de ce depot ou l'on peut fabriquer un FAUX VERT : elle
retire des tests du perimetre. Ce fichier garde la propriete qui la rend acceptable --
**tout ce qui n'est pas PROUVE independant est rejoue**, et un doute rejoue TOUT en le DISANT.

Aucune dependance a `logs/` : l'empreinte y vit (gitignore, #455), donc chaque test injecte la
sienne. Un checkout frais joue donc ces gardes a l'identique.

ASCII only (console cp1252).
"""
import sys
from pathlib import Path

import pytest

_PYDIR = Path(__file__).resolve().parents[1]
if str(_PYDIR) not in sys.path:
    sys.path.insert(0, str(_PYDIR))

import probe_457_offline_tests_green as P  # noqa: E402


PERIMETRE = ["tests/a_offline.py", "tests/b_offline.py", "tests/c_offline.py"]


@pytest.fixture
def empreinte(monkeypatch):
    """Injecte une empreinte SYNTHETIQUE et un diff controle."""
    MESURE = "mesure_ref"

    def poser(globales, par_test, changes, mods=None, inverse=None, incertains=None):
        # `_commit` est OBLIGATOIRE depuis le versionnement : une empreinte sans lui a un age
        # inverifiable et rejoue tout. Ici la mesure est supposee A JOUR (rien change depuis).
        monkeypatch.setattr(P, "_footprints",
                            lambda: {"_commit": MESURE, "_globales": globales,
                                     "par_test": par_test})
        monkeypatch.setattr(P, "_changed",
                            lambda ref: [] if ref == MESURE else changes)
        monkeypatch.setattr(P, "_import_graph",
                            lambda m: (inverse or {}, incertains or set()))
        if mods is not None:
            import subprocess

            class _R:
                returncode = 0
                stdout = "\n".join(mods)

            monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    return poser


def test_une_ref_inconnue_rejoue_TOUT_et_le_dit(monkeypatch):
    monkeypatch.setattr(P, "_changed", lambda ref: None)
    retenus, raison = P.impacted_files(PERIMETRE, "pas_une_ref")
    assert retenus == PERIMETRE, "une ref inconnue DOIT rejouer tout le perimetre"
    assert "TOUT rejoue" in raison, "le rejeu total doit etre DIT, pas silencieux"


def test_sans_empreinte_mesuree_on_rejoue_TOUT(monkeypatch):
    monkeypatch.setattr(P, "_changed", lambda ref: ["scripts/python/engine/x.py"])
    monkeypatch.setattr(P, "_footprints", dict)
    retenus, raison = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == PERIMETRE, "sans empreinte, aucune independance n'est PROUVEE"
    assert "AUCUNE empreinte" in raison


def test_un_changement_dans_une_lecture_GLOBALE_rejoue_TOUT(empreinte):
    empreinte(globales=["data/seed-bc.json"], par_test={}, changes=["data/seed-bc.json"], mods=[])
    retenus, raison = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == PERIMETRE, "une lecture globale n'est attribuable a personne -> impacte tout"
    assert "GLOBALE" in raison


def test_les_pyc_ne_declenchent_PAS_un_rejeu_total(empreinte):
    # 521 des 527 lectures globales mesurees sont des `.pyc` : les compter rendrait la selection
    # inutile, et ils ne peuvent PAS apparaitre dans un diff (bytecode non versionne).
    empreinte(globales=["scripts/python/__pycache__/x.cpython-313.pyc"],
              par_test={}, changes=["docs/rl/note.md"], mods=[])
    retenus, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == [], "un .pyc en globale ne doit pas forcer le rejeu total"


def test_un_fichier_de_test_MODIFIE_est_toujours_retenu(empreinte):
    empreinte(globales=[], par_test={}, changes=["scripts/python/tests/b_offline.py"], mods=[])
    retenus, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert "tests/b_offline.py" in retenus, "un test modifie DOIT etre rejoue"


def test_un_module_INCERTAIN_est_toujours_retenu(empreinte):
    # import dynamique / fichier illisible : on ne PRETEND pas savoir de quoi il depend.
    empreinte(globales=[], par_test={}, changes=["scripts/python/engine/x.py"], mods=[],
              incertains={"scripts/python/tests/c_offline.py"})
    retenus, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert "tests/c_offline.py" in retenus, "un module a resolution incertaine impacte par defaut"


def test_la_cloture_ARRIERE_des_imports_est_suivie(empreinte):
    # a_offline importe m2, qui importe m1. Changer m1 doit retenir a_offline.
    empreinte(globales=[], par_test={},
              changes=["scripts/python/engine/m1.py"],
              mods=["scripts/python/engine/m1.py"],
              inverse={"scripts/python/engine/m1.py": {"scripts/python/engine/m2.py"},
                       "scripts/python/engine/m2.py": {"scripts/python/tests/a_offline.py"}})
    retenus, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert "tests/a_offline.py" in retenus, "la dependance TRANSITIVE doit etre suivie"


def test_un_non_py_retient_les_tests_qui_lisent_son_REPERTOIRE(empreinte):
    # Granularite REPERTOIRE : un test qui lit docs/rl/x.md doit rejouer si docs/rl/y.md change --
    # sinon un fichier NEUF, absent de toute empreinte, passerait entre les mailles.
    empreinte(globales=[], par_test={"tests/c_offline.py": ["docs/rl/x.md"]},
              changes=["docs/rl/y.md"], mods=[])
    retenus, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == ["tests/c_offline.py"], "granularite repertoire attendue, ni plus ni moins"


def test_la_selection_est_INCLUSE_dans_le_perimetre(empreinte):
    empreinte(globales=[], par_test={"tests/a_offline.py": ["data/symbols/z.tsv"]},
              changes=["data/symbols/z.tsv"], mods=[])
    retenus, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert set(retenus) <= set(PERIMETRE), "la selection ne peut pas INVENTER un fichier"
    assert len(retenus) == len(set(retenus)), "aucun doublon"


def test_un_diff_VIDE_ne_joue_rien(empreinte):
    empreinte(globales=[], par_test={}, changes=[], mods=[])
    retenus, raison = P.impacted_files(PERIMETRE, "HEAD")
    assert retenus == [], "aucun changement -> aucun test a rejouer"
    assert "aucun fichier change" in raison


def test_une_empreinte_SANS_commit_de_mesure_rejoue_TOUT(monkeypatch):
    # L'empreinte est VERSIONNEE : sans commit d'horodatage, son age est inverifiable, donc son
    # contenu n'autorise a sauter AUCUN test. C'est ce qui rend le versionnement sur.
    monkeypatch.setattr(P, "_changed", lambda ref: ["scripts/python/engine/x.py"])
    monkeypatch.setattr(P, "_footprints", lambda: {"_globales": [], "par_test": {}})
    retenus, raison = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == PERIMETRE
    assert "SANS commit" in raison


def test_un_commit_de_mesure_INCONNU_rejoue_TOUT(monkeypatch):
    monkeypatch.setattr(P, "_footprints",
                        lambda: {"_commit": "dead" * 10, "_globales": [], "par_test": {}})
    monkeypatch.setattr(P, "_changed",
                        lambda ref: None if ref.startswith("dead") else ["scripts/python/e/x.py"])
    retenus, raison = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == PERIMETRE
    assert "inconnu de git" in raison


def test_le_diff_DEPUIS_LA_MESURE_est_UNI_a_celui_de_la_PR(monkeypatch):
    # Coeur de l'invalidation par l'age : un test modifie APRES la mesure mais AVANT la ref de la
    # PR n'est dans aucun des deux diffs pris seuls -- il ne doit pas passer entre les mailles.
    monkeypatch.setattr(P, "_footprints",
                        lambda: {"_commit": "abc123", "_globales": [], "par_test": {}})

    def diff(ref):
        if ref == "abc123":
            return ["scripts/python/tests/c_offline.py"]   # change depuis la MESURE
        return ["docs/rl/note.md"]                          # diff de la PR : sans rapport

    monkeypatch.setattr(P, "_changed", diff)
    monkeypatch.setattr(P, "_import_graph", lambda m: ({}, set()))

    import subprocess

    class _R:
        returncode = 0
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    retenus, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert "tests/c_offline.py" in retenus, \
        "un test modifie depuis la MESURE doit etre rejoue meme s'il est hors du diff de la PR"


def test_le_perimetre_reel_est_NON_VIDE(monkeypatch):
    # Anti-vacuite : sans cela, tous les tests ci-dessus passeraient sur un perimetre effondre.
    reel = P.candidate_files()
    assert len(reel) > 50, "perimetre reel effondre (%d) -- les gardes ne prouveraient rien" % len(reel)


# ------------------------------------------------------------------------------------------------
# #464-r2 -- l'empreinte ne doit RIEN a l'etat du `__pycache__` de la machine qui la mesure.
#
# Mesure du 2026-08-04, MEME arbre MEME probe : `_globales` valait 552 sur un worktree froid
# (0 `__pycache__`) contre 9 sur un arbre chaud, et les 3 lectures NON-`.py` etaient les MEMES des
# deux cotes. Sans bytecode, l'import ouvre la SOURCE, et le hook d'audit `open` la compte comme
# lecture GLOBALE -- une information sur la MACHINE, jamais sur le depot.
#
# La correction ne SUPPRIME pas une garde : elle exige une PREUVE. Une lecture n'est retiree que si
# elle est couverte par le graphe d'imports statique, et l'unique motif admis est
# << module `.py` VERSIONNE du domaine >>. Les gardes ci-dessous tiennent les deux bords : ce que
# le filtre a le droit de retirer, et surtout tout ce qu'il ne doit PAS toucher.
# ------------------------------------------------------------------------------------------------

MODULE = "scripts/python/engine/foo.py"           # dans le domaine
HORS_DOMAINE = "dump_boards.py"                   # `.py` A LA RACINE : le graphe ne le resout pas


def test_un_module_du_domaine_en_globale_ne_change_RIEN_a_la_selection(empreinte):
    """L'invariant de COUVERTURE, celui qui autorise le retrait -- verifie, pas postule.

    Un module du domaine ne peut PAS entrer dans `hors_py` (`impacted_files` en retire tout ce qui
    est dans `mods`), donc le porter en globale n'ajoute aucune selection quand LUI change."""
    empreinte(globales=[MODULE], par_test={}, changes=[MODULE], mods=[MODULE])
    avec, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    empreinte(globales=[], par_test={}, changes=[MODULE], mods=[MODULE])
    sans, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert avec == sans, ("la globale d'un module du domaine doit etre SANS EFFET -- si elle en a "
                          "un, le retirer PERD de la couverture au lieu de retirer du bruit")


def test_un_py_HORS_domaine_en_globale_rejoue_TOUJOURS_TOUT(empreinte):
    """La BORNE du filtre : il ne retire que ce qu'il prouve, jamais << tout ce qui finit en .py >>."""
    empreinte(globales=[HORS_DOMAINE], par_test={}, changes=[HORS_DOMAINE], mods=[MODULE])
    retenus, raison = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == PERIMETRE, "un `.py` hors du domaine du graphe n'est couvert par RIEN"
    assert "GLOBALE" in raison


def test_le_filtre_de_couverture_ne_retient_QUE_le_domaine():
    """`_couverte_par_le_graphe` est le foyer du retrait : aucune heuristique d'extension."""
    domaine = {MODULE: "engine.foo"}
    assert P._couverte_par_le_graphe(MODULE, domaine)
    for reste in (HORS_DOMAINE, "scripts/python/engine/bar.py", "data/seed-bc.json",
                  "docs/rl/note.md", "frida/hooks/x.ts", "scripts/python/pytest.ini"):
        assert not P._couverte_par_le_graphe(reste, domaine), \
            "%s n'est PAS dans le domaine -- il doit rester une lecture globale" % reste


def test_l_empreinte_est_INDEPENDANTE_de_l_etat_du_pycache():
    """LA propriete de #464-r2, sur le critere qui compte : `_globales` ecrite.

    On rejoue le FILTRE (fonction pure des chemins) sur les deux jeux de lectures brutes que les
    deux regimes produisent -- FROID = l'import ouvre les sources de TOUT le domaine, CHAUD = il
    n'ouvre que les rares modules dont le `.pyc` a vieilli. La difference entre les deux regimes
    etant par construction contenue dans le domaine, `_globales` doit etre IDENTIQUE."""
    domaine = P._modules_du_graphe()
    assert len(domaine) > 500, "domaine effondre (%d) -- la garde ne prouverait rien" % len(domaine)

    noyau = ["data/seed-bc.json", "data/symbols/CURRENT", "scripts/python/pytest.ini"]
    modules = sorted(domaine)
    brutes_froid = set(noyau) | set(modules)                 # tout le domaine ouvert en source
    brutes_chaud = set(noyau) | set(modules[:6])             # quelques `.pyc` perimes seulement

    def filtre(brutes):
        return sorted(g for g in brutes if not P._couverte_par_le_graphe(g, domaine))

    assert filtre(brutes_froid) == filtre(brutes_chaud) == sorted(noyau), \
        "l'empreinte doit rendre le MEME `_globales` a froid et a chaud"


def test_les_lectures_hors_py_survivent_au_filtre_meme_dans_le_domaine():
    """CONTRE-EPREUVE : un non-`.py` POSE DANS `scripts/python` reste global.

    C'est le cas le plus proche du bord -- meme repertoire que les modules retires. `pytest.ini`
    en est l'exemplaire reel (mesure : present dans les DEUX regimes)."""
    domaine = P._modules_du_graphe()
    for donnee in ("scripts/python/pytest.ini", "scripts/python/tests/fixture.json"):
        assert not P._couverte_par_le_graphe(donnee, domaine), \
            "%s n'est pas un module -- le graphe ne dit RIEN de lui" % donnee


# ------------------------------------------------------------------------------------------------
# #464-r2 -- le trou du graphe qu'il a fallu fermer pour que la preuve de couverture soit VRAIE.
# Aucun test n'IMPORTE son `conftest.py` : la cloture arriere s'arretait donc sur lui, et sur tout
# ce qu'il importe. Mesure sur `origin/master` : changer n'importe lequel des 4 `conftest.py` ne
# retenait que 2 fichiers de test sur 132.
# ------------------------------------------------------------------------------------------------

def test_un_conftest_MODIFIE_retient_les_tests_de_son_sous_arbre():
    mods = {"scripts/python/tests/conftest.py": "tests.conftest",
            "scripts/python/tests/engine/conftest.py": "tests.engine.conftest",
            "scripts/python/tests/test_a.py": "tests.test_a",
            "scripts/python/tests/engine/test_b.py": "tests.engine.test_b"}
    aretes = P._conftest_edges(mods)
    assert aretes["scripts/python/tests/conftest.py"] == {
        "scripts/python/tests/test_a.py", "scripts/python/tests/engine/test_b.py"}, \
        "un conftest sert TOUT son sous-arbre, pas seulement son repertoire"
    assert aretes["scripts/python/tests/engine/conftest.py"] == {
        "scripts/python/tests/engine/test_b.py"}, \
        "un conftest profond ne sert PAS les tests de son parent"


def test_le_conftest_REEL_du_depot_retient_massivement(monkeypatch):
    """Sur l'arbre REEL : le conftest qui porte les fixtures `autouse` doit rejouer la suite."""
    perimetre = P.candidate_files()
    conftest = "scripts/python/tests/conftest.py"
    assert (P.repo_root() / conftest).exists(), "conftest de reference absent -- garde vacueuse"

    monkeypatch.setattr(P, "_footprints",
                        lambda: {"_commit": "M", "_globales": [], "par_test": {}})
    monkeypatch.setattr(P, "_changed", lambda ref: [] if ref == "M" else [conftest])
    retenus, _ = P.impacted_files(perimetre, "REF")
    # AVANT #464-r2 : 2 fichiers sur 132. Le seuil vise la CLASSE de defaut, pas un chiffre exact.
    assert len(retenus) > len(perimetre) // 2, \
        ("changer %s ne retient que %d/%d fichiers : la semantique pytest n'est pas dans le graphe"
         % (conftest, len(retenus), len(perimetre)))


def test_un_module_importe_par_un_CONFTEST_retient_les_tests(monkeypatch):
    """La transitivite : le trou frappait aussi tout ce que le conftest importe (ex. le garde #455)."""
    perimetre = P.candidate_files()
    cible = "scripts/python/green_skip_guard.py"
    assert (P.repo_root() / cible).exists(), "cible de reference absente -- garde vacueuse"

    monkeypatch.setattr(P, "_footprints",
                        lambda: {"_commit": "M", "_globales": [], "par_test": {}})
    monkeypatch.setattr(P, "_changed", lambda ref: [] if ref == "M" else [cible])
    retenus, _ = P.impacted_files(perimetre, "REF")
    assert len(retenus) > len(perimetre) // 2, \
        ("changer %s ne retient que %d/%d fichiers -- la chaine module -> conftest -> tests est "
         "coupee" % (cible, len(retenus), len(perimetre)))


# ------------------------------------------------------------------------------------------------
# CONTRE-EPREUVE #464-r2, sur l'empreinte VERSIONNEE REELLE : une dependance HORS-`.py` doit
# TOUJOURS selectionner son test. C'est le trou qu'une empreinte videe ouvrait (#464 :
# `rel not in par_test` lu comme << aucune dependance >>, donc test SAUTE, faux vert versionne).
# ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("racine", ["data", "docs", "frida"])
def test_une_donnee_hors_py_qui_change_selectionne_TOUJOURS_son_test(racine, monkeypatch):
    emp = P._footprints()
    assert emp.get("par_test"), "empreinte versionnee absente ou vide -- contre-epreuve vacueuse"

    # Un test REEL de l'empreinte dont une dependance mesuree vit sous cette racine.
    cas = [(t, d) for t, dirs in emp["par_test"].items() for d in dirs
           if d.split("/")[0] == racine]
    assert cas, "aucun test de l'empreinte ne depend de `%s/` -- contre-epreuve vacueuse" % racine
    test, dossier = sorted(cas)[0]

    # On fait changer un fichier NEUF de ce repertoire : la granularite REPERTOIRE est ce qui
    # empeche un fichier jamais lu de passer entre les mailles.
    change = dossier + "/fichier_neuf_de_contre_epreuve.bin"
    monkeypatch.setattr(P, "_footprints", lambda: emp)
    monkeypatch.setattr(P, "_changed", lambda ref: [] if ref == emp["_commit"] else [change])
    monkeypatch.setattr(P, "_import_graph", lambda m: ({}, set()))   # graphe NEUTRALISE

    retenus, raison = P.impacted_files([test], "REF")
    assert retenus == [test], \
        ("%s depend de `%s/` mais un changement dans `%s` ne le selectionne pas (%s)"
         % (test, dossier, change, raison))
