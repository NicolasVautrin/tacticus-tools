"""#457-r8 -- garde de la SELECTION PAR DIFF de `probe_457` (`--since`).

Une selection par diff est le SEUL endroit de ce depot ou l'on peut fabriquer un FAUX VERT : elle
retire des tests du perimetre. Ce fichier garde la propriete qui la rend acceptable --
**tout ce qui n'est pas PROUVE independant est rejoue**, et un doute rejoue TOUT en le DISANT.

Aucune dependance a `logs/` : l'empreinte y vit (gitignore, #455), donc chaque test injecte la
sienne. Un checkout frais joue donc ces gardes a l'identique.

ASCII only (console cp1252).
"""


#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict
#: (#486-r15). Meme contrat que les cliquets de la banque (`declencheur_cliquet.py`).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des deux `conftest.py` et sa
        # fermeture. Aucun test ne les IMPORTE -- c'est de la semantique pytest -- et ils
        # portent le `green_skip_guard` de #455 plus trois fixtures `autouse`, dont le
        # verdict de CHAQUE test depend. Liste EXPLICITE et non `scripts/python/*.py` : le
        # glob large retiendrait ce test a chaque modification d'un probe quelconque.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER :
        "scripts/python/probe_457_offline_tests_green.py",
        "scripts/python/repo_read.py", "scripts/python/declencheur_cliquet.py",
        "scripts/python/tests/**/*.py", "scripts/ratchets-457-footprints.json",
    ),
    "build": False,
    "toujours": False,
    "raison": "Le probe sous test et ses deux foyers, l'EMPREINTE versionnee qu'il confronte "
              "reellement dans ses contre-epreuves, et TOUS les fichiers de test -- le perimetre "
              "reel sert d'anti-vacuite a plusieurs cas, donc un fichier ajoute ou retire change "
              "ce que ce fichier prouve.",
}

import sys
from pathlib import Path

import pytest

_PYDIR = Path(__file__).resolve().parents[1]
if str(_PYDIR) not in sys.path:
    sys.path.insert(0, str(_PYDIR))

import probe_457_offline_tests_green as P  # noqa: E402


PERIMETRE = ["tests/a_offline.py", "tests/b_offline.py", "tests/c_offline.py"]


def _e(dirs=()):
    """Une entree d'empreinte au FORMAT 2 (#486-r15) : un DICT, jamais une simple liste.

    `_commit` y est du CONTEXTE et non un critere -- la fraicheur ne se lit plus dans un sha qui
    meurt au squash-merge. Une entree PRESENTE avec `dirs` vide vaut << mesure, n'ouvre rien >> ;
    une entree ABSENTE vaut << jamais mesure >> et rejoue."""
    return {"_at": 1, "_commit": "contexte", "dirs": list(dirs), "temoins": []}


@pytest.fixture
def empreinte(monkeypatch):
    """Injecte une empreinte SYNTHETIQUE, un diff controle et AUCUNE declaration.

    Les `DECLENCHEUR` reels du depot sont NEUTRALISES ici : ce fichier garde la moitie MESUREE de
    la selection. La moitie DECLAREE a sa propre garde
    (`test_486r15_empreinte_par_entree_offline.py`)."""
    def poser(globales, par_test, changes, mods=None, inverse=None, incertains=None):
        monkeypatch.setattr(P, "_footprints",
                            lambda: {"_format": P.FORMAT_EMPREINTE, "_globales": globales,
                                     "par_test": par_test})
        monkeypatch.setattr(P, "_changed", lambda ref: changes)
        monkeypatch.setattr(P, "_import_graph",
                            lambda m: (inverse or {}, incertains or set()))
        monkeypatch.setattr(P, "declencheurs_du_perimetre", lambda perim, racine=None: ({}, {}))
        if mods is not None:
            import subprocess

            class _R:
                returncode = 0
                stdout = "\n".join(mods)

            monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    return poser


#: Toutes les entrees MESUREES et vides : le regime ou la selection peut reellement retirer des
#: fichiers. Sans cela, chaque cas ci-dessous rendrait << jamais mesure >> pour tout le monde et
#: serait VACUEUX.
def _toutes_vides(perimetre=None):
    return {rel: _e() for rel in (perimetre or PERIMETRE)}


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
    empreinte(globales=["data/seed-bc.json"], par_test=_toutes_vides(),
              changes=["data/seed-bc.json"], mods=[])
    retenus, raison = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == PERIMETRE, "une lecture globale n'est attribuable a personne -> impacte tout"
    assert "GLOBALE" in raison


def test_les_pyc_ne_declenchent_PAS_un_rejeu_total(empreinte):
    # 521 des 527 lectures globales mesurees sont des `.pyc` : les compter rendrait la selection
    # inutile, et ils ne peuvent PAS apparaitre dans un diff (bytecode non versionne).
    empreinte(globales=["scripts/python/__pycache__/x.cpython-313.pyc"],
              par_test=_toutes_vides(), changes=["docs/rl/note.md"], mods=[])
    retenus, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == [], "un .pyc en globale ne doit pas forcer le rejeu total"


def test_un_fichier_de_test_MODIFIE_est_toujours_retenu(empreinte):
    empreinte(globales=[], par_test=_toutes_vides(),
              changes=["scripts/python/tests/b_offline.py"], mods=[])
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
    par_test = _toutes_vides()
    par_test["tests/c_offline.py"] = _e(["docs/rl"])
    empreinte(globales=[], par_test=par_test, changes=["docs/rl/y.md"], mods=[])
    retenus, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == ["tests/c_offline.py"], "granularite repertoire attendue, ni plus ni moins"


def test_la_selection_est_INCLUSE_dans_le_perimetre(empreinte):
    par_test = _toutes_vides()
    par_test["tests/a_offline.py"] = _e(["data/symbols"])
    empreinte(globales=[], par_test=par_test, changes=["data/symbols/z.tsv"], mods=[])
    retenus, _ = P.impacted_files(PERIMETRE, "HEAD~1")
    assert set(retenus) <= set(PERIMETRE), "la selection ne peut pas INVENTER un fichier"
    assert len(retenus) == len(set(retenus)), "aucun doublon"


def test_un_diff_VIDE_ne_joue_rien(empreinte):
    empreinte(globales=[], par_test=_toutes_vides(), changes=[], mods=[])
    retenus, raison = P.impacted_files(PERIMETRE, "HEAD")
    assert retenus == [], "aucun changement -> aucun test a rejouer"
    assert "aucun fichier change" in raison


# ------------------------------------------------------------------------------------------------
# #486-r15 -- CE QUE TROIS GARDES DE CE FICHIER TENAIENT, ET POURQUOI ELLES ONT CHANGE D'OBJET.
#
# `test_une_empreinte_SANS_commit_de_mesure_rejoue_TOUT`, `test_un_commit_de_mesure_INCONNU...`
# et `test_le_diff_DEPUIS_LA_MESURE_est_UNI_a_celui_de_la_PR` gardaient le tampon GLOBAL : un
# `_commit` unique horodatait l'empreinte ENTIERE, et `impacted_files` unissait << tout ce qui a
# change depuis >> au diff de la PR.
#
# Ce critere n'a pas ete affaibli, il a ete SUPPRIME parce qu'il etait AUTO-DESTRUCTEUR : ce sha
# etait ecrit dans le worktree d'un AGENT, donc sur une branche que le squash-merge remplace par
# un commit neuf avant de la supprimer. Il naissait MORT a chaque livraison par PR. Mesure du
# 2026-08-07 : `57bb2a7c` inconnu de `git cat-file`, et `--since` rendait 220/220 fichiers sur
# CHACUNE des 8 dernieres bases -- la selection ne selectionnait plus rien depuis 3 jours.
#
# Ce qui le remplace n'est pas un autre tampon : c'est le DIFF, plus la mise a jour PARTIELLE qui
# rend la fraicheur auto-reparatrice (un module change entre dans le diff -> son test est
# selectionne -> il tourne -> son entree est REECRITE). Les gardes correspondantes vivent dans
# `test_486r15_empreinte_par_entree_offline.py` : survie au squash, tri-etat JAMAIS-MESURE vs
# MESURE-ET-VIDE, et non-contamination des entrees qu'une passe partielle n'a pas jouees.
# ------------------------------------------------------------------------------------------------


def test_le_perimetre_reel_est_NON_VIDE(monkeypatch):
    # Anti-vacuite : sans cela, tous les tests ci-dessus passeraient sur un perimetre effondre.
    reel = P.candidate_files()
    assert len(reel) > 50, "perimetre reel effondre (%d) -- les gardes ne prouveraient rien" % len(reel)


# ------------------------------------------------------------------------------------------------
# #464-r2 -- l'empreinte ne doit RIEN a l'etat du `__pycache__` de la machine qui la mesure.
#
# Mesure du 2026-08-04, MEME arbre MEME probe : `_globales` valait 552 sur un worktree froid
# (0 `__pycache__`) contre 3 sur un arbre chaud, et les 3 lectures NON-`.py` etaient les MEMES des
# deux cotes. Sans bytecode, l'import ouvre la SOURCE, et le hook d'audit `open` la compte comme
# lecture GLOBALE -- une information sur la MACHINE, jamais sur le depot.
#
# RIEN N'EST FILTRE : la CAUSE est traitee (prechauffage), et un GARDE DE REGIME verifie qu'elle
# l'a bien ete. Les gardes ci-dessous tiennent ce contrat -- et surtout la BORNE : aucune lecture
# n'est retiree, donc la selection ne peut pas devenir permissive.
# ------------------------------------------------------------------------------------------------

MODULE = "scripts/python/engine/foo.py"           # dans le domaine
HORS_DOMAINE = "dump_boards.py"                   # `.py` A LA RACINE : le graphe ne le resout pas


def test_le_prechauffage_vise_un_prefixe_HORS_scripts_python():
    """#455 : la banque enumere `scripts/python` en parallele -- le bytecode ne doit pas y naitre."""
    prefixe = str(P._pycache_prefix()).replace("\\", "/")
    pydir = str(P.repo_root() / "scripts" / "python").replace("\\", "/")
    assert not prefixe.startswith(pydir), \
        "le bytecode de la mesure irait dans l'arbre de production : %s" % prefixe
    assert "/logs/" in prefixe, "le prefixe doit vivre sous `logs/` (gitignore) : %s" % prefixe


def test_le_garde_de_regime_reconnait_les_modules_du_domaine():
    """`_est_module_du_domaine` decide du REFUS d'ecrire : aucune heuristique d'extension."""
    domaine = {MODULE: "engine.foo"}
    assert P._est_module_du_domaine(MODULE, domaine)
    for reste in (HORS_DOMAINE, "scripts/python/engine/bar.py", "data/seed-bc.json",
                  "docs/rl/note.md", "frida/hooks/x.ts", "scripts/python/pytest.ini"):
        assert not P._est_module_du_domaine(reste, domaine), \
            "%s n'est PAS dans le domaine -- il ne peut pas declencher le garde de regime" % reste


def test_AUCUNE_lecture_globale_n_est_retiree_a_la_lecture(empreinte):
    """LA BORNE de #464-r2 : la correction ne rend pas la selection permissive.

    Un module du domaine LAISSE dans une empreinte ancienne doit encore mordre par son repertoire
    -- c'est le sens SUR. Le regime est garanti a l'ecriture, jamais en effacant a la lecture."""
    empreinte(globales=[MODULE], par_test=_toutes_vides(),
              changes=["scripts/python/engine/table.json"], mods=[MODULE])
    retenus, raison = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == PERIMETRE, "une empreinte ancienne doit SUR-selectionner, jamais sous-selectionner"
    assert "GLOBALE" in raison


def test_un_py_HORS_domaine_en_globale_rejoue_TOUJOURS_TOUT(empreinte):
    empreinte(globales=[HORS_DOMAINE], par_test=_toutes_vides(), changes=[HORS_DOMAINE],
              mods=[MODULE])
    retenus, raison = P.impacted_files(PERIMETRE, "HEAD~1")
    assert retenus == PERIMETRE, "un `.py` hors du domaine du graphe n'est couvert par RIEN"
    assert "GLOBALE" in raison


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


def _empreinte_REELLE_toute_mesuree(monkeypatch, perimetre, change):
    """L'arbre REEL, avec une empreinte ou TOUT est mesure et vide -- le regime le plus EXIGEANT.

    Sans ce montage les deux gardes ci-dessous seraient VACUEUSES depuis #486-r15 : un `par_test`
    vide fait desormais rendre << jamais mesure >> pour chaque fichier, donc `len(retenus)` vaudrait
    trivialement `len(perimetre)` et le seuil passerait sans rien prouver. En declarant chaque
    fichier MESURE-ET-VIDE, la seule voie de retention qui reste est le GRAPHE -- c'est bien lui
    qu'on veut mesurer."""
    monkeypatch.setattr(P, "_footprints",
                        lambda: {"_format": P.FORMAT_EMPREINTE, "_globales": [],
                                 "par_test": {rel: _e() for rel in perimetre}})
    monkeypatch.setattr(P, "_changed", lambda ref: [change])
    # Les declarations REELLES sont neutralisees : c'est la moitie MESUREE qui est sous test.
    monkeypatch.setattr(P, "declencheurs_du_perimetre", lambda perim, racine=None: ({}, {}))


def test_le_conftest_REEL_du_depot_retient_massivement(monkeypatch):
    """Sur l'arbre REEL : le conftest qui porte les fixtures `autouse` doit rejouer la suite."""
    perimetre = P.candidate_files()
    conftest = "scripts/python/tests/conftest.py"
    assert (P.repo_root() / conftest).exists(), "conftest de reference absent -- garde vacueuse"

    _empreinte_REELLE_toute_mesuree(monkeypatch, perimetre, conftest)
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

    _empreinte_REELLE_toute_mesuree(monkeypatch, perimetre, cible)
    retenus, _ = P.impacted_files(perimetre, "REF")
    assert len(retenus) > len(perimetre) // 2, \
        ("changer %s ne retient que %d/%d fichiers -- la chaine module -> conftest -> tests est "
         "coupee" % (cible, len(retenus), len(perimetre)))


def test_un_module_QUELCONQUE_ne_retient_PAS_tout(monkeypatch):
    """LA BORNE des deux gardes ci-dessus : sans elle, une selection qui retiendrait TOUJOURS tout
    les ferait passer toutes les deux. On exige donc qu'un module a la portee ETROITE reste
    etroit."""
    perimetre = P.candidate_files()
    cible = "scripts/python/verdict_cache.py"
    assert (P.repo_root() / cible).exists(), "cible de reference absente -- garde vacueuse"

    _empreinte_REELLE_toute_mesuree(monkeypatch, perimetre, cible)
    retenus, _ = P.impacted_files(perimetre, "REF")
    assert 0 < len(retenus) < len(perimetre) // 2, \
        ("changer %s retient %d/%d fichiers : la selection ne discrimine plus rien"
         % (cible, len(retenus), len(perimetre)))


# ------------------------------------------------------------------------------------------------
# CONTRE-EPREUVE #464-r2, sur l'empreinte VERSIONNEE REELLE : une dependance HORS-`.py` doit
# TOUJOURS selectionner son test. C'est le trou qu'une empreinte videe ouvrait (#464 :
# `rel not in par_test` lu comme << aucune dependance >>, donc test SAUTE, faux vert versionne).
# ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("racine", ["data", "docs", "frida"])
def test_une_donnee_hors_py_qui_change_selectionne_TOUJOURS_son_test(racine, monkeypatch):
    emp = P._footprints()
    assert emp.get("par_test"), "empreinte versionnee absente ou vide -- contre-epreuve vacueuse"
    assert emp.get("_format") == P.FORMAT_EMPREINTE, \
        ("empreinte au format %s : la contre-epreuve ci-dessous lit les entrees du format %d"
         % (emp.get("_format"), P.FORMAT_EMPREINTE))

    # Un test REEL de l'empreinte dont une dependance mesuree vit sous cette racine.
    cas = [(t, d) for t, e in emp["par_test"].items() for d in (e.get("dirs") or ())
           if d.split("/")[0] == racine]
    assert cas, "aucun test de l'empreinte ne depend de `%s/` -- contre-epreuve vacueuse" % racine
    test, dossier = sorted(cas)[0]

    # On fait changer un fichier NEUF de ce repertoire : la granularite REPERTOIRE est ce qui
    # empeche un fichier jamais lu de passer entre les mailles.
    change = dossier + "/fichier_neuf_de_contre_epreuve.bin"
    monkeypatch.setattr(P, "_footprints", lambda: emp)
    monkeypatch.setattr(P, "_changed", lambda ref: [change])
    monkeypatch.setattr(P, "_import_graph", lambda m: ({}, set()))   # graphe NEUTRALISE
    monkeypatch.setattr(P, "declencheurs_du_perimetre", lambda perim, racine=None: ({}, {}))

    retenus, raison = P.impacted_files([test], "REF")
    assert retenus == [test], \
        ("%s depend de `%s/` mais un changement dans `%s` ne le selectionne pas (%s)"
         % (test, dossier, change, raison))

