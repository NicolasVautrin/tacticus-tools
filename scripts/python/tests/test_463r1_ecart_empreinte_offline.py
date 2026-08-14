"""#463-r1 -- garde du cliquet d'ECART entre le perimetre offline et l'empreinte de `probe_457`.

CE QUE CE FICHIER PROUVE, ET POURQUOI CHAQUE ETAGE EXISTE
----------------------------------------------------------
Le gisement : rien ne mesure automatiquement les poids d'un fichier de test offline NEUF.
`--measure-missing` est un geste EXPLICITE et son oubli est SILENCIEUX -- TROIS reouvertures le
2026-08-07 (231->232, 232->233, 233->234), toutes par nos propres livraisons.

Mais le remede EVIDENT est FAUX, et c'est ce que ce fichier garde autant que le cliquet lui-meme :
mesurer a la place de l'humain graverait, le jour ou le fichier est un test LIVE MAL NOMME
(`40917cd0`, le MEME jour), une empreinte derivee d'un run live -- donc une selection etroite,
donc un FAUX VERT durable. Le cliquet doit donc ROUGIR, NOMMER, et REFUSER DE TRANCHER.

  [1] la VENTILATION voit les DEUX sens (un compte d'INTERSECTION ne montre pas ce qui deborde) ;
  [2] le PERIMETRE est DERIVE, et c'est LE MEME que celui que `--measure-missing` joue ;
  [3] BOUT EN BOUT sur un depot JETABLE : le cliquet rend REELLEMENT 0 / 1 / 99. C'est l'etage
      qui separe un cliquet d'un INVENTAIRE DEGUISE -- `probe_181` rendait `0` inconditionnellement
      tout en IMPRIMANT son trou, et se lisait comme un garde-fou (#430) ;
  [4] l'INDICE est LU, pas COMPTE : un grep matche la PROSE (vecu sur
      `test_524r1_bond_sous_effets_offline.py`, ou `rpc` vivait dans une chaine de message) ;
  [5] le cliquet NE TRANCHE PAS -- les DEUX issues sont dites, aucune n'est choisie ;
  [6] AUCUNE allowlist, AUCUNE echappatoire d'environnement ;
  [7] l'ARBRE REEL : l'ecart y est nul, et ce test rougit le jour ou il ne l'est plus ;
  [8] `loop_status` ne DOUBLE plus le recensement -- il lit le MEME foyer.

CHAQUE MUTATION DOIT AVOIR MORDU. Un test qui rougit sur un ensemble VIDE passerait pour vert :
tous les etages assertionnent le NON-VIDE de leur propre temoin avant d'exiger le rouge.

BON MARCHE. Le seul etage qui lance des process est [3], sur un depot jetable de 6 fichiers ; les
autres sont des fonctions pures ou une lecture JSON. Aucun ne rejoue le corpus (#486-r5).

ASCII only (console cp1252).
"""

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # Entre dans la FERMETURE par l'import-graph de `probe_457` depuis #956. Un
        # declencheur trop etroit est un FAUX VERT : le fichier ne se rejoue pas sous
        # `--since` quand ce qu'il garde a bouge.
        "scripts/python/probe_956_purete_de_passe.py",
        # LA CASCADE DES `conftest.py` N'EST PLUS ICI : le foyer la DERIVE depuis #531 (436
        # chemins pour `tests/`), et les douze qui etaient recopies a cette place sont TOUS
        # dedans -- verifie, pas suppose.
        # `livraison.py` : foyer PARTAGE arrive avec #826, que la fermeture atteint PAR
        # `nettoyer_livraison`.
        "scripts/python/livraison.py",
        "scripts/python/fleet_board.py", "scripts/python/verdict_cache.py",
        # PROPRE A CE FICHIER : le cliquet sous test, son producteur (dont il lit le contrat par
        # import differe), le capteur qui partage son foyer, et l'empreinte VERSIONNEE que
        # l'etage 7 confronte a l'arbre reel.
        "scripts/python/probe_463r1_ecart_empreinte_offline.py",
        "scripts/python/probe_457_offline_tests_green.py",
        # Entre dans la cascade avec #486-r23 : `probe_457` importe le ledger.
        "scripts/python/ledger_vert_offline.py",
        "scripts/python/loop_status.py",
        "scripts/python/declencheur_cliquet.py", "scripts/python/repo_read.py",
        "scripts/ratchets-457-footprints.json",
        # Le perimetre de l'etage 7 est DERIVE par `git ls-files scripts/python/tests` : un
        # fichier de test ajoute ou retire change ce qu'il compte.
        "scripts/python/tests/**/*.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Le cliquet sous test, son producteur `probe_457` (contrat FORMAT/racine de "
              "fixture), le capteur `loop_status` qui partage son foyer, l'empreinte versionnee "
              "confrontee a l'arbre reel, et TOUS les fichiers de test -- dont le perimetre est "
              "DERIVE, donc un fichier ajoute ou retire change le verdict de l'etage 7.",
}

import json                                                             # noqa: E402
import os                                                               # noqa: E402
import shutil                                                           # noqa: E402
import subprocess                                                       # noqa: E402
import sys                                                              # noqa: E402
from pathlib import Path                                                # noqa: E402

import pytest                                                           # noqa: E402

_PYDIR = Path(__file__).resolve().parents[1]
if str(_PYDIR) not in sys.path:
    sys.path.insert(0, str(_PYDIR))

import loop_status as LS                                                # noqa: E402
import probe_457_offline_tests_green as P457                            # noqa: E402
import probe_463r1_ecart_empreinte_offline as E                         # noqa: E402


# ------------------------------------------------------------------ 1. LA VENTILATION, DEUX SENS

def test_un_fichier_SANS_entree_est_un_manquant():
    ecart = E.ventiler(["tests/a_offline.py", "tests/b_offline.py"],
                       {"tests/a_offline.py": {"dirs": []}})
    assert ecart["manquants"] == ["tests/b_offline.py"], "le sens PERIMETRE \\ EMPREINTE"
    assert ecart["fantomes"] == []


def test_une_entree_HORS_perimetre_est_un_fantome():
    """LE SENS QUE LE COMPTE D'INTERSECTION NE VOYAIT PAS.

    Le capteur rendait `couverts = len([r for r in perimetre if r in entrees])`. Sur un perimetre
    integralement couvert, une empreinte portant en plus des entrees mortes affichait donc `N/N`
    et se taisait. Une intersection ne montre JAMAIS ce qui deborde -- et ce qui deborde ici est
    precisement la TRACE d'un renommage en `_live.py`, c'est-a-dire le contre-cas `40917cd0`.
    """
    ecart = E.ventiler(["tests/a_offline.py"],
                       {"tests/a_offline.py": {"dirs": []}, "tests/parti_offline.py": {"dirs": []}})
    assert ecart["manquants"] == [], "le perimetre est integralement couvert"
    assert ecart["fantomes"] == ["tests/parti_offline.py"], \
        "une entree hors perimetre DOIT ressortir -- sinon le compte se lit `N/N`"


def test_les_deux_sens_sont_NON_VIDES_ensemble():
    ecart = E.ventiler(["tests/a_offline.py", "tests/neuf_offline.py"],
                       {"tests/a_offline.py": {}, "tests/mort_offline.py": {}})
    assert ecart["manquants"] and ecart["fantomes"], "les deux sens sont independants"


# --------------------------------------------------------- 2. LE PERIMETRE EST DERIVE, ET UNIQUE

_LS_FILES = "\n".join([
    "scripts/python/tests/test_a_offline.py",
    "scripts/python/tests/test_b_live.py",             # exclu : suffixe live
    "scripts/python/tests/engine/test_c_offline.py",   # sous-repertoire
    "scripts/python/tests/d_test.py",                  # seconde convention pytest
    "scripts/python/tests/helper.py",                  # exclu : pas un fichier de test
    "scripts/python/tests/conftest.py",                # exclu : pas un fichier de test
    "scripts/python/tests/data/fixture.json",          # exclu : pas un .py
])


def test_le_filtre_suit_la_collecte_de_pytest_et_le_suffixe_live():
    assert E.perimetre_offline(_LS_FILES) == [
        "tests/d_test.py", "tests/engine/test_c_offline.py", "tests/test_a_offline.py"]


def test_un_fichier_a_la_RACINE_de_tests_est_couvert():
    """Le vice de #457-r5 : `scripts/python/tests/**/test_*.py` EXIGE un niveau intermediaire,
    donc les fichiers poses DIRECTEMENT dans `tests/` en etaient exclus -- 23 invisibles."""
    assert "tests/test_a_offline.py" in E.perimetre_offline(_LS_FILES)


def test_le_foyer_est_LE_MEME_que_celui_que_measure_missing_joue():
    """LE POINT DE LA DE-DUPLICATION. Deux derivations d'un meme critere ouvrent un ecart
    SILENCIEUX : le capteur compterait un perimetre, `--measure-missing` en jouerait un autre.
    On verifie l'IDENTITE DE FONCTION, pas l'egalite des resultats -- deux implementations qui
    concordent aujourd'hui peuvent diverger demain, et c'est exactement le mode de defaillance."""
    assert P457._is_test_file is E.est_fichier_de_test
    assert P457.TESTS_DIR == E.TESTS_DIR
    reel = P457.candidate_files()
    assert len(reel) > 100, "perimetre effondre (%d) -- la comparaison ne prouverait rien" % len(reel)
    assert reel == E.recenser(), "le producteur et le cliquet doivent recenser LE MEME ensemble"


# ------------------------------------------------------ 3. BOUT EN BOUT : LE CLIQUET REND 0/1/99

def _git(base: Path, *argv) -> None:
    r = subprocess.run(["git", "-C", str(base), *argv], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("montage du depot jetable : `git %s` rc=%d %s"
                           % (argv[0], r.returncode, (r.stderr or "")[:200]))


def _cloture_locale(source: Path) -> set:
    """Les modules FRERES de `scripts/python` que `source` importe, TRANSITIVEMENT.

    DERIVEE et non ecrite a la main : c'est la lecon de #486-r14, ou la liste recopiee de
    `probe_471` s'est perimee des que `probe_457` a acquis `repo_read`, et ou les scenarios
    sortaient en `ModuleNotFoundError` -- le cliquet rougissait SANS RIEN MESURER.

    Les imports DIFFERES comptent : `ast.walk` les voit, et c'est necessaire ici puisque
    `_contrat_de_probe_457` est justement un differe porteur.
    """
    import ast
    vus, pile = set(), [source]
    while pile:
        p = pile.pop()
        if p in vus or not p.exists():
            continue
        vus.add(p)
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for n in ast.walk(arbre):
            noms = []
            if isinstance(n, ast.Import):
                noms = [a.name.split(".")[0] for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                noms = [n.module.split(".")[0]]
            for nom in noms:
                frere = _PYDIR / (nom + ".py")
                if frere.exists():
                    pile.append(frere)
    return vus


@pytest.fixture(scope="module")
def depot(tmp_path_factory):
    """Un depot git JETABLE : le cliquet, sa cloture, DEUX tests offline et UN test live.

    Le cliquet derive sa racine de son PROPRE fichier et son perimetre de `git ls-files` :
    le recopier dans une arborescence `scripts/python/` suffit a le faire travailler sur ce
    depot-la. La contre-epreuve est donc REELLE (le vrai binaire, le vrai git), pas simulee.
    """
    base = tmp_path_factory.mktemp("463r1")
    py = base / "scripts" / "python"
    (py / "tests").mkdir(parents=True)
    for src in sorted(_cloture_locale(_PYDIR / "probe_463r1_ecart_empreinte_offline.py")):
        shutil.copy2(src, py / src.name)
    # Le SOURCE du producteur : le cliquet y LIT son contrat (`_contrat_de_probe_457`) sans
    # jamais l'importer, donc sa cloture d'imports n'a pas a suivre -- c'est precisement ce que
    # l'extraction par `ast` achete (1,53 s d'import evitees a chaque run).
    shutil.copy2(_PYDIR / E.SOURCE_457, py / E.SOURCE_457)
    (py / "tests" / "test_offline_pur.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8")
    (py / "tests" / "test_mal_nomme.py").write_text(
        '"""Contrepartie OFFLINE -- mais elle monte un runner."""\n'
        "def test_ko(live_session, rpc):\n    assert live_session\n", encoding="utf-8")
    (py / "tests" / "test_vrai_live.py").write_text(
        "def test_l(host):\n    assert host\n", encoding="utf-8")
    # Le conftest qui DEFINIT les fixtures live : l'indice les DERIVE de la, jamais d'une liste.
    (py / "tests" / "conftest.py").write_text(
        "import pytest\n\n"
        "@pytest.fixture(scope='session')\ndef host():\n    return 1\n\n"
        "@pytest.fixture(scope='session')\ndef live_session(host):\n    return host\n\n"
        "@pytest.fixture(scope='session')\ndef rpc(host, live_session):\n    return host\n",
        encoding="utf-8")
    _git(base, "init", "-q")
    _git(base, "add", "-A")
    return base


def _empreinte(base: Path, par_test: dict) -> None:
    (base / "scripts").mkdir(parents=True, exist_ok=True)
    (base / E.EMPREINTE).write_text(
        json.dumps({"_format": P457.FORMAT_EMPREINTE, "_globales": [], "par_test": par_test}),
        encoding="utf-8")


def _jouer(base: Path, env_sup=None) -> tuple:
    env = dict(os.environ)
    # Empeche git de remonter au-dessus du depot jetable : sans ce plafond, le scenario
    # << git hors service >> tomberait sur un depot parent et mesurerait autre chose.
    env["GIT_CEILING_DIRECTORIES"] = str(base.parent)
    env.update(env_sup or {})
    proc = subprocess.run([sys.executable, "probe_463r1_ecart_empreinte_offline.py"],
                          cwd=str(base / "scripts" / "python"), env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    return int(proc.returncode), (proc.stdout or "") + (proc.stderr or "")


_COMPLETE = {"tests/test_offline_pur.py": {"dirs": [], "temoins": []},
             "tests/test_mal_nomme.py": {"dirs": [], "temoins": []}}


def test_le_cliquet_est_VERT_quand_l_empreinte_couvre_le_perimetre(depot):
    """LA BORNE. Sans elle, un cliquet qui rougirait TOUJOURS passerait tous les cas ci-dessous
    -- et se ferait desarmer dans la semaine."""
    _empreinte(depot, _COMPLETE)
    rc, sortie = _jouer(depot)
    assert rc == 0, sortie
    assert "VERDICT: PASS" in sortie


def test_le_cliquet_ROUGIT_sur_une_entree_RETIREE(depot):
    """L'AUTO-CONTROLE. `probe_181` rendait `0` inconditionnellement tout en IMPRIMANT son trou :
    seule l'EXECUTION separe un cliquet d'un inventaire deguise."""
    ampute = {k: v for k, v in _COMPLETE.items() if k != "tests/test_offline_pur.py"}
    assert len(ampute) < len(_COMPLETE), "la mutation n'a pas MORDU -- rien n'a ete retire"
    _empreinte(depot, ampute)
    rc, sortie = _jouer(depot)
    assert rc == 1, sortie
    assert "tests/test_offline_pur.py" in sortie, "le fichier concerne doit etre NOMME"
    assert "NON MESURE" in sortie


def test_le_cliquet_ROUGIT_sur_une_entree_FANTOME(depot):
    """L'autre sens. Une entree qui ne designe plus rien est la TRACE d'un renommage."""
    avec_fantome = dict(_COMPLETE)
    avec_fantome["tests/test_disparu_offline.py"] = {"dirs": [], "temoins": []}
    _empreinte(depot, avec_fantome)
    rc, sortie = _jouer(depot)
    assert rc == 1, sortie
    assert "FANTOME" in sortie and "tests/test_disparu_offline.py" in sortie


def test_un_FORMAT_inconnu_rougit_SANS_accuser_les_fichiers(depot):
    """Sur un format inconnu, `par_test` n'a pas la forme attendue : conclure << 3 non mesures >>
    accuserait les fichiers d'un defaut qui est celui de l'EMPREINTE."""
    (depot / E.EMPREINTE).write_text(
        json.dumps({"_format": 1, "par_test": {"tests/test_offline_pur.py": ["docs"]}}),
        encoding="utf-8")
    rc, sortie = _jouer(depot)
    assert rc == 1, sortie
    assert "format" in sortie.lower()
    assert "NON MESURE  tests/" not in sortie, "le format ne doit accuser aucun fichier"


def test_git_hors_service_rend_NON_MESURE_et_pas_un_rouge(depot, tmp_path_factory):
    """TRI-ETAT (#471). Une panne d'outil sortait en rc=1, indistinguable d'un ecart reel --
    c'est le crash EXACT mesure sur `probe_457:s3` (rc 128 lu comme << un test est rouge >>)."""
    casse = tmp_path_factory.mktemp("463r1-sans-git")
    shutil.copytree(depot / "scripts", casse / "scripts")
    shutil.rmtree(casse / ".git", ignore_errors=True)
    _empreinte(casse, _COMPLETE)
    rc, sortie = _jouer(casse)
    assert rc == E.EX_NON_MESURE, sortie
    assert "MONTAGE EN ECHEC" in sortie
    assert "VERDICT: FAIL" not in sortie, "une panne d'outil n'est PAS un verdict"


def test_une_empreinte_ABSENTE_rend_NON_MESURE(depot, tmp_path_factory):
    """Un `{}` silencieux ferait rendre << tous les fichiers non mesures >> pour une panne de
    lecture : un rouge de gisement pour un echec de MONTAGE."""
    sans = tmp_path_factory.mktemp("463r1-sans-empreinte")
    shutil.copytree(depot / "scripts", sans / "scripts")
    shutil.copytree(depot / ".git", sans / ".git")
    (sans / E.EMPREINTE).unlink(missing_ok=True)
    rc, sortie = _jouer(sans)
    assert rc == E.EX_NON_MESURE, sortie
    assert "MONTAGE EN ECHEC" in sortie


# ---------------------------------------------------- 4. L'INDICE EST LU, PAS COMPTE

_LIVE = {"host", "live_session", "rpc", "build_runner"}


def test_une_fixture_live_est_lue_dans_la_SIGNATURE():
    src = "def test_x(live_session, rpc):\n    assert live_session\n"
    trouves = E.reclamations_live(src, _LIVE)
    assert trouves, "le temoin doit MORDRE -- sinon l'assertion inverse ne prouverait rien"
    assert {p for _, p, _ in trouves} == {"live_session", "rpc"}


def test_usefixtures_compte_aussi():
    src = ('import pytest\n@pytest.mark.usefixtures("host")\n'
           "def test_x():\n    assert True\n")
    trouves = E.reclamations_live(src, _LIVE)
    assert trouves and "usefixtures" in trouves[0][1]


def test_le_meme_NOM_dans_une_CHAINE_n_est_PAS_une_reclamation():
    """LE PIEGE DU FILTRE, mesure sur `test_524r1_bond_sous_effets_offline.py` : un grep
    `live_session|build_runner|rpc` matche AUSSI la PROSE. Ici `rpc` vit dans un message."""
    src = ('def test_x():\n    assert 1, "timeout rpc depasse"\n')
    assert E.reclamations_live(src, _LIVE) == [], "aucune fixture n'est reclamee"
    classees = E.occurrences_classees(src, _LIVE)
    assert classees, "l'occurrence existe bel et bien -- le temoin doit etre NON VIDE"
    assert {c for c, _, _ in classees} == {"STRING"}, \
        "elle doit etre classee PROSE, et le lecteur doit pouvoir la LIRE"


def test_un_mot_qui_CONTIENT_un_nom_live_n_est_pas_une_occurrence():
    """Bornes de mot : sans elles `host` matcherait `ghost` et `hostile`, et l'indice bruiterait
    exactement la ou il doit rassurer."""
    assert E.occurrences_classees('X = "ghost hostile"\n', {"host"}) == []


def test_le_contrat_EXTRAIT_est_celui_que_l_import_REEL_rend():
    """LE CRAN QUI INTERDIT A L'EXTRACTION DE MENTIR.

    Le cliquet LIT `FORMAT_EMPREINTE` et `LIVE_FIXTURE_ROOT` dans le SOURCE de `probe_457`
    (`ast`) au lieu de l'importer -- 1,53 s economisees a chaque run. Une lecture de source peut
    diverger de la valeur reelle (constante deplacee dans une classe, calculee, redefinie plus
    bas) ; ce test, LUI, importe pour de vrai et confronte. Sans lui, l'optimisation aurait
    exactement la forme d'une RECOPIE qui derive en silence."""
    fmt, racine = E._contrat_de_probe_457()
    assert (fmt, racine) == (P457.FORMAT_EMPREINTE, P457.LIVE_FIXTURE_ROOT)


def test_un_contrat_ILLISIBLE_rend_NON_MESURE_et_le_DIT(tmp_path):
    """La fragilite de l'extraction est NOMMEE, jamais silencieuse : une constante devenue
    non-litterale doit rendre 99 (<< je n'ai pas pu lire le contrat >>), pas une valeur devinee."""
    py = tmp_path / "scripts" / "python"
    py.mkdir(parents=True)
    (py / E.SOURCE_457).write_text(
        "LIVE_FIXTURE_ROOT = 'host'\nFORMAT_EMPREINTE = int('2')\n", encoding="utf-8")
    with pytest.raises(E.MontageImpossible) as exc:
        E._contrat_de_probe_457(tmp_path)
    assert "FORMAT_EMPREINTE" in str(exc.value), "la constante manquante doit etre NOMMEE"


def test_les_fixtures_live_sont_DERIVEES_des_conftest(depot):
    """Jamais une liste ecrite dans le cliquet : une fixture live ajoutee demain y manquerait,
    et l'indice se degraderait EN SILENCE -- le vice meme qu'il ferme."""
    live = E.fixtures_live(depot)
    assert {"host", "live_session", "rpc"} <= live, live
    assert P457.LIVE_FIXTURE_ROOT in live, "la RACINE entre toujours, meme sans conftest lisible"


# --------------------------------------------------- 5. LE CLIQUET REFUSE DE TRANCHER

def test_la_sortie_porte_LES_DEUX_ISSUES_et_n_en_choisit_AUCUNE(depot):
    """LE COEUR DE LA TRANCHE. Un cliquet qui recommanderait `--measure-missing` tout court
    ferait exactement la faute du contre-cas `40917cd0` : mesurer un test LIVE mal nomme grave
    une empreinte derivee d'un run live, donc un FAUX VERT durable."""
    _empreinte(depot, {})
    rc, sortie = _jouer(depot)
    assert rc == 1
    assert "--measure-missing" in sortie, "l'issue (a) doit etre dite"
    assert "RENOMMER" in sortie and "_live.py" in sortie, "l'issue (b) doit etre dite"
    assert "40917cd0" in sortie, "le contre-cas doit etre CITE, pas seulement connu de l'auteur"
    assert "N'EN CHOISIT AUCUNE" in sortie


def test_l_indice_DISTINGUE_le_mal_nomme_du_purement_offline(depot):
    """Les deux fichiers sont NON MESURES de la meme facon ; seul l'INDICE les separe, et il est
    LU : `test_mal_nomme` reclame `live_session` dans sa SIGNATURE."""
    _empreinte(depot, {})
    rc, sortie = _jouer(depot)
    assert rc == 1
    bloc = sortie.split("NON MESURE  tests/test_mal_nomme.py")[1].split("NON MESURE")[0]
    assert "RECLAMENT une fixture LIVE" in bloc and "live_session" in bloc
    pur = sortie.split("NON MESURE  tests/test_offline_pur.py")[1].split("NON MESURE")[0]
    assert "AUCUNE fonction ne reclame" in pur


# ------------------------------------------------- 6. AUCUNE ALLOWLIST, AUCUNE ECHAPPATOIRE

@pytest.mark.parametrize("var", ["TACTICUS_ALLOW_RATCHETS", "TACTICUS_ALLOW_GREEN_SKIP",
                                 "TACTICUS_457_ACCEPTE_PY_GLOBAUX"])
def test_aucune_variable_d_environnement_ne_fait_TAIRE_le_rouge(depot, var):
    """Le brief de la tranche l'exige, et la mesure le permet : l'ecart sur `master` etait de
    ZERO quand ce cliquet a ete ecrit, donc aucune dette n'est necessaire. En inventer une
    fabriquerait d'avance le trou par lequel le gisement revient (cf. la DETTE de #486-r15, qui
    n'existe que parce que l'obligation seche y rendait 711 fichiers rouges)."""
    _empreinte(depot, {})
    rc, _ = _jouer(depot, {var: "1"})
    assert rc == 1, "%s ne doit RIEN changer au verdict" % var


def test_toute_la_sortie_du_cliquet_est_ASCII(depot):
    """La console Windows tourne en cp1252 : un seul caractere non-ASCII imprime leve
    `UnicodeEncodeError` et fait CRASHER le cliquet -- un faux negatif qui masque le vrai
    resultat. On exerce le chemin ROUGE, celui qui imprime le plus (indices, angle mort, les
    deux issues), pas seulement le PASS d'une ligne."""
    _empreinte(depot, {})
    rc, sortie = _jouer(depot)
    assert rc == 1 and len(sortie) > 800, "temoin trop maigre : %d octets" % len(sortie)
    non_ascii = sorted({c for c in sortie if ord(c) > 127})
    assert non_ascii == [], "caracteres non-ASCII imprimes : %r" % non_ascii


def test_le_source_ne_lit_AUCUNE_variable_d_environnement():
    """Le test ci-dessus ne peut couvrir que les variables qu'on a PENSE a nommer -- une
    allowlist de noms ne montre jamais celui qu'elle a oublie. Ce balayage-ci est exhaustif."""
    src = (_PYDIR / "probe_463r1_ecart_empreinte_offline.py").read_text(encoding="utf-8")
    executables = [l for l in src.splitlines()
                   if "os.environ" in l and not l.lstrip().startswith("#")]
    assert executables == [], executables


# ------------------------------------------------------------------- 7. L'ARBRE REEL

def test_l_ecart_est_NUL_sur_ce_checkout():
    """CE QUI FAIT DE CE FICHIER UN CLIQUET, pas un inventaire : il rougit le jour ou quelqu'un
    ajoute un fichier de test offline sans le mesurer -- c'est-a-dire a la cadence mesuree de
    TROIS fois par jour. Le geste qui l'eteint est l'un des deux que le cliquet nomme, jamais
    une exception ecrite ici.

    BON MARCHE : un `git ls-files` et une lecture JSON, aucun test rejoue.

    ⚠ CE CAS EST AUTO-REFERENT, et une seule fois : la passe `--measure-missing` qui INSCRIT ce
    fichier dans l'empreinte le joue AVANT que son entree existe, donc il y rougit -- puis il est
    vert au rejeu. C'est la sequence normale (mesurer, puis rejouer), pas un defaut, et `probe_457`
    ecrit sa mesure meme sur `rc=1` (les fichiers ONT ete joues). S'exclure lui-meme du recensement
    pour eviter ce rouge serait une ALLOWLIST -- exactement ce que cette tranche refuse."""
    m = E.mesurer()
    assert m["perimetre"], "perimetre effondre -- ce test ne prouverait rien"
    assert m["format_lu"] == m["format_attendu"], \
        "empreinte au format %s (attendu %s)" % (m["format_lu"], m["format_attendu"])
    ecart = m["ecart"]
    assert ecart["manquants"] == [], (
        "%d fichier(s) offline NON MESURE(S) : %s -- DEUX issues, a trancher : (a) le mesurer "
        "(`probe_457 --measure-missing`) si le fichier est reellement offline ; (b) le RENOMMER "
        "en `*_live.py` s'il reclame une fixture live. `python "
        "probe_463r1_ecart_empreinte_offline.py` donne l'indice."
        % (len(ecart["manquants"]), ", ".join(ecart["manquants"][:5])))
    assert ecart["fantomes"] == [], (
        "%d entree(s) FANTOME(S) : %s -- purge par `probe_457 --measure`."
        % (len(ecart["fantomes"]), ", ".join(ecart["fantomes"][:5])))


# ------------------- 7bis. LE GESTE RECOMMANDE DOIT ETRE PRATICABLE LA OU IL EST LU

class _PoidsAbsents:
    """Substitue le CHEMIN des poids par un fichier qui n'existe pas -- l'etat de tout worktree."""

    def __init__(self, monkeypatch, tmp_path, existe: bool):
        chemin = tmp_path / "457-durations.json"
        if existe:
            chemin.write_text(json.dumps({}), encoding="utf-8")
        monkeypatch.setattr(P457, "_weights_path", lambda: chemin)
        monkeypatch.setattr(P457, "_weights", lambda: {})


def _joues_par_measure_missing(perimetre, entrees):
    """Ce que `--measure-missing` RETIENDRAIT, sans rien jouer.

    On rejoue le critere du mode plutot que d'invoquer pytest : mesurer pour de vrai coute ici
    ~976 s (c'est le fait meme que ce cas garde), et l'objet du test est le CRITERE."""
    poids_absents = not P457._weights_path().exists()
    poids = P457._weights()
    if poids_absents:
        return [r for r in perimetre if r not in entrees]
    return [r for r in perimetre if r not in poids or r not in entrees]


def test_sans_poids_measure_missing_ne_rejoue_PAS_tout_le_perimetre(monkeypatch, tmp_path):
    """LE DEFAUT REPARE, ET IL RENDAIT LE GESTE RECOMMANDE INAPPLICABLE.

    `logs/` est GITIGNORE : un worktree d'agent n'a JAMAIS de poids. Le critere « sans poids »
    valait donc pour TOUT LE MONDE, et `--measure-missing` retenait **235 fichiers sur 235** --
    un `--measure` complet (~976 s) la ou le mode existe pour en couter quelques secondes.
    Mesure apres reparation, sur ce worktree : **1 fichier sur 235, 15 s de mur**.

    C'est le tri-etat du depot applique aux poids : `{}` parce que le FICHIER est absent n'est
    pas `{}` parce qu'aucun fichier n'a de poids."""
    _PoidsAbsents(monkeypatch, tmp_path, existe=False)
    perimetre = ["tests/a_offline.py", "tests/b_offline.py", "tests/neuf_offline.py"]
    entrees = {"tests/a_offline.py": {}, "tests/b_offline.py": {}}
    joues = _joues_par_measure_missing(perimetre, entrees)
    assert joues == ["tests/neuf_offline.py"], \
        "seul le fichier SANS entree d'empreinte doit etre rejoue"


def test_avec_un_fichier_de_poids_le_critere_des_poids_REDEVIENT_actif(monkeypatch, tmp_path):
    """LA BORNE. Sans elle, la reparation ci-dessus aurait pu se degrader en « on ignore les
    poids », et un fichier PESE-mais-perime cesserait d'etre remesure dans l'arbre principal."""
    _PoidsAbsents(monkeypatch, tmp_path, existe=True)
    perimetre = ["tests/a_offline.py", "tests/neuf_offline.py"]
    entrees = {"tests/a_offline.py": {}, "tests/neuf_offline.py": {}}
    joues = _joues_par_measure_missing(perimetre, entrees)
    assert joues == perimetre, \
        "poids PRESENTS mais vides : les deux criteres s'appliquent, tout est sans poids"


def test_sans_poids_aucun_fichier_de_poids_PARTIEL_n_est_ecrit(monkeypatch, tmp_path):
    """Un fichier de poids a UNE entree est PIRE que pas de poids : `bins_of` prend
    `defaut = max(weights.values())`, donc le poids du seul fichier mesure deviendrait la valeur
    supposee des 234 autres. Le repli md5, lui, repartit par nombre et reste honnete."""
    chemin = tmp_path / "457-durations.json"
    monkeypatch.setattr(P457, "_weights_path", lambda: chemin)
    monkeypatch.setattr(P457, "_modules_du_graphe", lambda racine=None: {})

    class _Horloge:
        sec = {"tests/neuf_offline.py": 1.5}
        n = {"tests/neuf_offline.py": 3}

    rc = P457._ecrire_mesure(["tests/a_offline.py", "tests/neuf_offline.py"],
                             ["tests/neuf_offline.py"], _Horloge(), None, 0, 1.5, {},
                             complete=False, ecrire_poids=False)
    # ⚠ CE TEST GARDE L'ECRITURE, PAS LE VERDICT -- et les deux etaient confondus par un `rc == 0`
    # qui n'etait qu'un effet de bord. Depuis #547-r1, une passe PARTIELLE (`complete=False`) rend
    # `EX_NON_MESURE` : elle n'a pas regarde la verdeur des fichiers qu'elle n'a pas joues, donc
    # son `0` se lisait << l'arbre offline est vert >> a tort. L'objet du test -- aucun fichier de
    # poids PARTIEL sur disque -- est inchange et reste assertionne juste en dessous.
    assert rc == P457.EX_NON_MESURE
    assert not chemin.exists(), "aucun fichier de poids partiel ne doit apparaitre"


# ------------------------------------------- 8. `loop_status` NE DOUBLE PLUS LE RECENSEMENT

class _SourcesJetables(LS.Sources):
    def __init__(self, repo, fichiers):
        super().__init__(repo=repo, ttl_cache=0.0)
        self._fichiers = fichiers

    def git(self, *args):
        assert args[:1] == ("ls-files",), args
        return 0, self._fichiers


def test_le_capteur_lit_LE_MEME_foyer_que_le_cliquet():
    """La recopie du filtre dans `loop_status` etait une SECONDE derivation du meme critere :
    le capteur pouvait compter un perimetre pendant que `--measure-missing` en jouait un autre,
    sans que rien ne le dise."""
    src = (_PYDIR / "loop_status.py").read_text(encoding="utf-8")
    assert "ecart_empreinte.perimetre_offline(" in src
    # Le critere porte sur le FILTRE EXECUTABLE, pas sur la chaine `_live.py`, que le signal
    # cite legitimement en PROSE pour nommer l'issue (b). C'est le meme piege que le cliquet
    # traite chez les autres, applique ici : on lit la correspondance, on ne la compte pas.
    filtres = [l for l in src.splitlines()
               if 'endswith("_live.py")' in l and not l.lstrip().startswith("#")]
    assert filtres == [], filtres


def test_le_capteur_VOIT_desormais_les_FANTOMES(tmp_path):
    """Ce que le compte d'intersection lui cachait : perimetre integralement couvert, empreinte
    qui deborde -- l'ancien capteur affichait `1/1` et se taisait."""
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / E.EMPREINTE).write_text(json.dumps(
        {"_format": P457.FORMAT_EMPREINTE,
         "par_test": {"tests/test_a_offline.py": {"dirs": []},
                      "tests/test_parti_offline.py": {"dirs": []}}}), encoding="utf-8")
    src = _SourcesJetables(tmp_path, "scripts/python/tests/test_a_offline.py\n")
    d = LS.mesurer_empreinte(src)
    assert d["couverture"].valeur["couverts"] == d["couverture"].valeur["perimetre"], \
        "le perimetre EST couvert -- c'est ce qui rendait le fantome invisible"
    assert d["couverture"].valeur["fantomes"] == ["tests/test_parti_offline.py"]
    sig, _ = LS.signaux({"flotte": _FLOTTE, "livraison": _LIVRAISON, "harnais": _HARNAIS,
                         "empreinte": d})
    assert any(s.cle == "empreinte-fantome" for s in sig), "le fantome doit etre ACTIONNABLE"


def test_le_signal_du_capteur_NOMME_et_ne_TRANCHE_PAS(tmp_path):
    """Il disait << regenerer : --measure-missing >>, donc il CHOISISSAIT la mesure -- la faute
    exacte du contre-cas `40917cd0`. Il doit nommer le fichier et rendre la main."""
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / E.EMPREINTE).write_text(
        json.dumps({"_format": P457.FORMAT_EMPREINTE, "par_test": {}}), encoding="utf-8")
    src = _SourcesJetables(tmp_path, "scripts/python/tests/test_neuf_offline.py\n")
    sig, _ = LS.signaux({"flotte": _FLOTTE, "livraison": _LIVRAISON, "harnais": _HARNAIS,
                         "empreinte": LS.mesurer_empreinte(src)})
    ligne = [s.ligne for s in sig if s.cle == "empreinte"]
    assert ligne, "l'incompletude doit rester ACTIONNABLE"
    assert "tests/test_neuf_offline.py" in ligne[0], "le fichier doit etre NOMME"
    assert "RENOMMER" in ligne[0] and "--measure-missing" in ligne[0], "les DEUX issues"


#: Etats NEUTRES des trois autres postes : ces cas ne jugent que l'empreinte.
_FLOTTE = {"en_vol": LS._ok(0, "t"), "libres": LS._ok(0, "t"), "plafond": 5,
           "noms": LS._ok([], "t"), "chemins": set()}
_LIVRAISON = {"avance": LS._ok(0, "t"), "retard": LS._ok(0, "t"),
              "suivis_sales": LS._ok([], "t"),
              "worktrees": LS._ok([], "t"), "nettoyables": LS._ok([], "t"),
              "pr_ouvertes": LS._ok([], "t"), "branche": LS._ok("master", "t"),
              "non_suivis": LS._ok(0, "t"), "non_suivis_inconnus": LS._ok([], "t")}
_HARNAIS = {"session": LS._ok(None, "t"), "drain": LS._ok(False, "t"),
            "jeu": LS._ok(True, "t"), "live_runners": LS._ok(0, "t")}
