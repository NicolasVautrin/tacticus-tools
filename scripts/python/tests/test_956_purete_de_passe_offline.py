"""#956 -- garde du cliquet de PURETE DE PASSE : une passe de tests n'ecrit AUCUN fichier VERSIONNE.

CE QUE CE FICHIER PROUVE, ET POURQUOI CHAQUE ETAGE EXISTE
----------------------------------------------------------
Le gisement : la banque offline repartit ses fichiers en SHARDS, plusieurs fichiers de test
tournent dans le MEME processus pytest, et N shards tournent EN PARALLELE sur UN SEUL arbre de
travail. Si un fichier de test ECRIT dans un fichier VERSIONNE, alors un autre fichier de test qui
le LIT voit un etat qui depend de QUI a tourne avant lui -- donc de `--jobs N`. Le verdict de la
banque devient fonction de son DECOUPAGE, et aucun de nos cliquets ne regardait cet axe.

  [1] les FONCTIONS PURES du filtre statique : ce qu'il retient, ce qu'il ecarte, et le fait
      qu'un fichier ILLISIBLE est RETENU (jamais ecarte en silence) ;
  [2] le PERIMETRE est DERIVE du meme foyer que `probe_463r1` -- pas une quatrieme derivation ;
  [3] BOUT EN BOUT sur un depot JETABLE : le cliquet rend REELLEMENT 0 / 1 / 99. C'est l'etage
      qui separe un cliquet d'un INVENTAIRE DEGUISE (`probe_181` rendait `0` inconditionnellement
      tout en IMPRIMANT son trou, #430) ;
  [4] les DEUX CANAUX sont COMPLEMENTAIRES, et c'est MESURE, pas suppose : le hook d'audit ne
      franchit pas la frontiere de PROCESSUS, `git status` ne voit pas une ecriture DEFAITE avant
      la borne. Chaque canal voit un cas que l'autre RATE ;
  [5] `_salissures` de `probe_457` : TRI-ETAT, sensible au CONTENU (pas seulement a la liste),
      et il voit la restauration comme un changement ;
  [6] `probe_457` PORTE reellement le capteur -- lu dans son SOURCE, comme `test_463r1` lit
      `loop_status`. Un cliquet qu'on ecrit sans le CABLER ne garde rien ;
  [7] l'ARBRE REEL : le filtre statique DISCRIMINE (sinon il ne bornerait rien) et retient les
      temoins connus.

CHAQUE MUTATION DOIT AVOIR MORDU : tout etage qui exige un rouge assertionne d'abord le NON-VIDE
de son propre temoin.

BON MARCHE. Les seuls process lances sont ceux de l'etage 3/4, sur un depot jetable de quelques
fichiers. Aucun etage ne rejoue le corpus (#486-r5), et AUCUN ne rejoue la banque.

ASCII only (console cp1252).
"""

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # Entre dans la FERMETURE par l'import-graph de `probe_457` depuis #956. Un
        # declencheur trop etroit est un FAUX VERT : le fichier ne se rejoue pas sous
        # `--since` quand ce qu'il garde a bouge.
        "scripts/python/ledger_vert_offline.py",
        "scripts/python/probe_956_purete_de_passe.py",
        # Le cliquet lit son perimetre dans ce foyer, et l'etage 6 lit le SOURCE de `probe_457`.
        "scripts/python/probe_463r1_ecart_empreinte_offline.py",
        "scripts/python/probe_457_offline_tests_green.py",
        # Le proprietaire du seul prefixe EXEMPTE (etage 5bis).
        "scripts/python/verdict_cache.py",
        "scripts/python/declencheur_cliquet.py", "scripts/python/repo_read.py",
        # Le perimetre de l'etage 7 est DERIVE par `git ls-files scripts/python/tests` : un
        # fichier de test ajoute ou retire change ce qu'il compte.
        "scripts/python/tests/**/*.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Le cliquet sous test, le foyer de recensement dont il derive son perimetre, le "
              "probe `probe_457` dont l'etage 6 lit le CABLAGE dans le source, et TOUS les "
              "fichiers de test -- dont le perimetre est DERIVE.",
}

import os                                                               # noqa: E402
import shutil                                                           # noqa: E402
import subprocess                                                       # noqa: E402
import sys                                                              # noqa: E402
from pathlib import Path                                                # noqa: E402

import pytest                                                           # noqa: E402

_PYDIR = Path(__file__).resolve().parents[1]
if str(_PYDIR) not in sys.path:
    sys.path.insert(0, str(_PYDIR))

import probe_457_offline_tests_green as P457                            # noqa: E402
import probe_463r1_ecart_empreinte_offline as ECART                     # noqa: E402
import probe_956_purete_de_passe as P                                   # noqa: E402


# ------------------------------------------------------ 1. LE FILTRE STATIQUE, FONCTION PURE

def test_une_ecriture_de_fichier_est_un_site():
    sites = P.sites_d_ecriture("from pathlib import Path\n"
                               "def test_x():\n    Path('a').write_text('b')\n")
    assert [f for f, _ in sites] == ["write_text"]


def test_un_open_en_LECTURE_n_est_PAS_un_site():
    """LA BORNE. Un filtre qui retiendrait tout ne bornerait rien, et le perimetre par defaut
    coincideraient avec la banque entiere -- donc ne serait jamais joue."""
    assert P.sites_d_ecriture("def test_x():\n    open('a').read()\n") == []
    assert P.sites_d_ecriture("def test_x():\n    open('a', 'r').read()\n") == []


@pytest.mark.parametrize("mode", ["w", "a", "x", "r+", "wb"])
def test_tous_les_modes_ECRIVANTS_sont_vus(mode):
    sites = P.sites_d_ecriture("def test_x():\n    open('a', %r)\n" % mode)
    assert sites, "mode %r non reconnu comme ecrivant" % mode


def test_un_lancement_de_PROCESSUS_est_un_site():
    """Un test qui sous-traite peut ecrire sans jamais ouvrir de fichier lui-meme : le filtre
    doit le RETENIR, sinon le canal 2 ne serait jamais arme sur lui."""
    sites = P.sites_d_ecriture("import subprocess\n"
                               "def test_x():\n    subprocess.run(['git', 'status'])\n")
    assert [f for f, _ in sites] == ["subprocess.run"]


def test_un_fichier_ILLISIBLE_est_RETENU_et_le_DIT():
    """Un source non parsable ne permet RIEN d'affirmer. L'ecarter serait un zero rendu sur ce
    qu'on n'a pas visite -- le vice recurrent de ce depot."""
    assert P.sites_d_ecriture("def test_x(:\n") == [("ILLISIBLE", 0)]


# ------------------------------------------------------ 2. LE PERIMETRE EST DERIVE, PAS RECOPIE

def test_le_perimetre_vient_du_FOYER_de_recensement():
    """Une seconde derivation du meme critere ouvrirait un ecart SILENCIEUX : ce cliquet
    jouerait un perimetre, `probe_463r1` en compterait un autre. On verifie l'IDENTITE DE
    FONCTION, pas l'egalite des resultats -- deux implementations qui concordent aujourd'hui
    peuvent diverger demain."""
    src = (_PYDIR / "probe_956_purete_de_passe.py").read_text(encoding="utf-8")
    assert "ECART.recenser(" in src, "le perimetre doit venir du foyer, jamais d'un glob local"
    assert "ECART.TESTS_DIR" in src or "ECART.PREFIXE_ROOTDIR" in src


# ---------------------------------------------- 3. BOUT EN BOUT : LE CLIQUET REND 0 / 1 / 99

def _git(base: Path, *argv) -> None:
    r = subprocess.run(["git", "-C", str(base), *argv], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("montage du depot jetable : `git %s` rc=%d %s"
                           % (argv[0], r.returncode, (r.stderr or "")[:200]))


def _cloture_locale(source: Path) -> set:
    """Les modules FRERES de `scripts/python` que `source` importe, TRANSITIVEMENT.

    DERIVEE et non ecrite a la main : c'est la lecon de #486-r14, ou la liste recopiee d'un
    voisin s'est perimee des que le probe a acquis une dependance, et ou les scenarios sortaient
    en `ModuleNotFoundError` -- le cliquet rougissait SANS RIEN MESURER.
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


#: Un test qui n'ecrit RIEN.
_PUR = "def test_pur():\n    assert True\n"

#: Un test qui ECRIT dans un fichier VERSIONNE du depot jetable. Le chemin est resolu depuis le
#: fichier de test lui-meme : rien n'est suppose du CWD.
_ECRIVAIN = (
    "from pathlib import Path\n"
    "def test_ecrit():\n"
    "    p = Path(__file__).resolve().parents[2] / 'artefact.json'\n"
    "    p.write_text('{\"n\": 1}', encoding='utf-8')\n"
    "    assert p.exists()\n")

#: Un test qui ecrit le MEME artefact PAR UN PROCESSUS FILS -- invisible du hook d'audit.
_SOUS_TRAITANT = (
    "import subprocess, sys\n"
    "from pathlib import Path\n"
    "def test_fils():\n"
    "    p = Path(__file__).resolve().parents[2] / 'artefact.json'\n"
    "    r = subprocess.run([sys.executable, '-c',\n"
    "                        'import sys,pathlib;"
    "pathlib.Path(sys.argv[1]).write_text(chr(123)+chr(125))', str(p)])\n"
    "    assert r.returncode == 0\n")

#: Un test qui ECRIT puis RESTAURE : invisible d'un `git status` pris aux bornes, VU par le hook.
_TRANSITOIRE = (
    "from pathlib import Path\n"
    "def test_transitoire():\n"
    "    p = Path(__file__).resolve().parents[2] / 'artefact.json'\n"
    "    avant = p.read_text(encoding='utf-8')\n"
    "    p.write_text('{\"n\": 99}', encoding='utf-8')\n"
    "    p.write_text(avant, encoding='utf-8')\n")


@pytest.fixture(scope="module")
def depot(tmp_path_factory):
    """Un depot git JETABLE : le cliquet, sa cloture, un artefact VERSIONNE, quatre tests.

    Le cliquet derive sa racine de son PROPRE fichier et son perimetre de `git ls-files` :
    le recopier dans une arborescence `scripts/python/` suffit a le faire travailler sur ce
    depot-la. La contre-epreuve est donc REELLE (le vrai binaire, le vrai git), pas simulee.
    """
    base = tmp_path_factory.mktemp("956")
    py = base / "scripts" / "python"
    (py / "tests").mkdir(parents=True)
    for src in sorted(_cloture_locale(_PYDIR / "probe_956_purete_de_passe.py")):
        shutil.copy2(src, py / src.name)
    (py / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n", encoding="utf-8")
    (base / "scripts" / "artefact.json").write_text('{"n": 0}\n', encoding="utf-8")
    (py / "tests" / "test_pur_offline.py").write_text(_PUR, encoding="utf-8")
    (py / "tests" / "test_ecrivain_offline.py").write_text(_ECRIVAIN, encoding="utf-8")
    (py / "tests" / "test_fils_offline.py").write_text(_SOUS_TRAITANT, encoding="utf-8")
    (py / "tests" / "test_transitoire_offline.py").write_text(_TRANSITOIRE, encoding="utf-8")
    _git(base, "init", "-q")
    _git(base, "add", "-A")
    _git(base, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "socle")
    return base


def _jouer(base: Path, *argv) -> tuple:
    env = dict(os.environ)
    # Empeche git de remonter au-dessus du depot jetable : sans ce plafond, un scenario
    # << git hors service >> tomberait sur un depot parent et mesurerait autre chose.
    env["GIT_CEILING_DIRECTORIES"] = str(base.parent)
    proc = subprocess.run([sys.executable, "probe_956_purete_de_passe.py", *argv],
                          cwd=str(base / "scripts" / "python"), env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    return int(proc.returncode), (proc.stdout or "") + (proc.stderr or "")


def _restaurer(base: Path) -> None:
    (base / "scripts" / "artefact.json").write_text('{"n": 0}\n', encoding="utf-8")


def test_le_cliquet_est_VERT_sur_un_test_PUR(depot):
    """LA BORNE. Sans elle, un cliquet qui rougirait TOUJOURS passerait tous les cas ci-dessous
    -- et se ferait desarmer dans la semaine."""
    _restaurer(depot)
    rc, sortie = _jouer(depot, "--fichiers", "tests/test_pur_offline.py")
    assert rc == 0, sortie
    assert "VERDICT: PASS" in sortie


def test_le_cliquet_ROUGIT_sur_une_ecriture_VERSIONNEE(depot):
    _restaurer(depot)
    rc, sortie = _jouer(depot, "--fichiers", "tests/test_ecrivain_offline.py")
    assert rc == 1, sortie
    assert "tests/test_ecrivain_offline.py" in sortie, "le fichier fautif doit etre NOMME"
    assert "scripts/artefact.json" in sortie, "le chemin ECRIT doit etre NOMME"
    assert "VERDICT: FAIL" in sortie


def test_le_cliquet_NE_TRANCHE_PAS_et_dit_les_DEUX_issues(depot):
    _restaurer(depot)
    _, sortie = _jouer(depot, "--fichiers", "tests/test_ecrivain_offline.py")
    assert "tmp_path" in sortie, "l'issue (a) doit etre dite"
    assert "depot JETABLE" in sortie or "jetable" in sortie, "l'issue (b) doit etre dite"
    assert "n'en choisit AUCUNE" in sortie


def test_git_hors_service_rend_NON_MESURE_et_pas_un_rouge(depot, tmp_path_factory):
    """TRI-ETAT (#471). Une panne d'outil sortait en rc=1, indistinguable d'un ecart reel --
    c'est le crash EXACT mesure sur `probe_457:s3` (rc 128 lu comme << un test est rouge >>)."""
    casse = tmp_path_factory.mktemp("956-sans-git")
    shutil.copytree(depot / "scripts", casse / "scripts")
    rc, sortie = _jouer(casse, "--fichiers", "tests/test_pur_offline.py")
    assert rc == P.EX_NON_MESURE, sortie
    assert "MONTAGE EN ECHEC" in sortie
    assert "VERDICT: FAIL" not in sortie, "une panne d'outil n'est PAS un verdict"


def test_un_chemin_HORS_perimetre_est_un_REFUS_D_USAGE(depot):
    """Ni un vert ni un rouge : jouer un fichier qu'on n'a pas recense ne mesure rien."""
    _restaurer(depot)
    rc, sortie = _jouer(depot, "--fichiers", "tests/pas_un_test.py")
    assert rc == 2, sortie
    assert "REFUS D'USAGE" in sortie


# --------------------------------------- 4. LES DEUX CANAUX, ET CE QUE CHACUN RATE

def test_le_hook_SEUL_rate_une_ecriture_par_PROCESSUS_FILS(depot):
    """LA FRONTIERE DU CANAL 1, MESUREE. `sys.addaudithook` est per-processus : un test qui
    sous-traite n'ouvre RIEN lui-meme. C'est pour cela que le canal 2 existe."""
    _restaurer(depot)
    rc, sortie = _jouer(depot, "--sans-git", "--fichiers", "tests/test_fils_offline.py")
    assert rc == 0, "le hook seul ne peut PAS voir l'ecriture du fils :\n%s" % sortie
    assert "SOUS-TRAITANTS" in sortie, "le tri-etat doit etre DIT, pas tu"
    assert "tests/test_fils_offline.py" in sortie


def test_le_canal_GIT_rattrape_l_ecriture_par_PROCESSUS_FILS(depot):
    """... et il la rattrape. Les deux canaux ne sont donc pas redondants : le second voit ce
    que le premier ne PEUT pas voir."""
    _restaurer(depot)
    rc, sortie = _jouer(depot, "--fichiers", "tests/test_fils_offline.py")
    assert rc == 1, sortie
    assert "scripts/artefact.json" in sortie
    assert "borne" in sortie, "le canal qui a mordu doit etre NOMME"


def test_le_canal_GIT_SEUL_rate_une_ecriture_TRANSITOIRE(depot):
    """LA FRONTIERE DU CANAL 2, MESUREE, et elle est le SYMETRIQUE de la precedente : un fichier
    ecrit puis restaure est identique aux deux bornes. Le hook, lui, l'a VU -- et c'est le bon
    critere, puisqu'un shard VOISIN a pu lire PENDANT."""
    _restaurer(depot)
    rc, sortie = _jouer(depot, "--fichiers", "tests/test_transitoire_offline.py")
    assert rc == 1, sortie
    assert "hook d'audit" in sortie, "seul le canal 1 peut voir une ecriture defaite"
    assert "borne" not in sortie.split("ECRIT DU VERSIONNE")[1], \
        "le canal 2 ne DOIT PAS pretendre avoir vu une ecriture restauree"


def test_toute_la_sortie_du_cliquet_est_ASCII(depot):
    """La console Windows tourne en cp1252 : un seul caractere non-ASCII imprime leve
    `UnicodeEncodeError` et fait CRASHER le cliquet -- un faux negatif qui masque le vrai
    resultat. On exerce le chemin ROUGE, celui qui imprime le plus."""
    _restaurer(depot)
    rc, sortie = _jouer(depot, "--fichiers", "tests/test_ecrivain_offline.py")
    assert rc == 1 and len(sortie) > 600, "temoin trop maigre : %d octets" % len(sortie)
    non_ascii = sorted({c for c in sortie if ord(c) > 127})
    assert non_ascii == [], "caracteres non-ASCII imprimes : %r" % non_ascii


# ------------------------------------------- 5. `_salissures` DE `probe_457` : TRI-ETAT ET CONTENU

def test_une_mesure_impossible_ne_rend_PAS_un_arbre_propre():
    """`None` = PAS MESURE. Le rabattre sur `[]` ferait lire << la passe est pure >> pour une
    panne de `git` -- exactement le zero fabrique que ce depot proscrit partout."""
    assert P457._salissures(None, {}) is None
    assert P457._salissures({}, None) is None


def test_un_fichier_NEUVELLEMENT_sale_est_vu():
    assert P457._salissures({}, {"scripts/a.json": "aa"}) == ["scripts/a.json"]


def test_un_fichier_DEJA_sale_dont_le_CONTENU_change_est_vu():
    """LE CAS QUI A FAIT NAITRE #956. Un worktree d'agent est SALE avant la passe -- un worktree
    propre est auto-supprime. Comparer deux LISTES rendrait ce cas invisible, et c'est exactement
    l'etat de l'arbre ou la confusion est nee."""
    assert P457._salissures({"scripts/a.json": "aa"}, {"scripts/a.json": "bb"}) \
        == ["scripts/a.json"]


def test_un_fichier_RESTAURE_pendant_la_passe_est_vu():
    """Il a bouge DEUX fois. Un shard voisin a pu lire entre les deux."""
    assert P457._salissures({"scripts/a.json": "aa"}, {}) == ["scripts/a.json"]


def test_une_salete_PREEXISTANTE_INCHANGEE_ne_compte_PAS():
    """LA BORNE. Sans elle le capteur rougirait dans TOUT worktree d'agent, donc serait desarme
    le jour meme."""
    etat = {"scripts/a.json": "aa", "docs/rl/backlog.md": "bb"}
    assert P457._salissures(etat, dict(etat)) == []


# ------------------------- 5bis. L'EXEMPTION EST UNIQUE, DERIVEE, ET SA PREUVE EXISTE

def test_l_exemption_est_UNIQUE_et_designe_le_cache_de_verdict():
    """UNE seule classe d'artefact est exemptee, et c'est ce que ce test garde.

    L'exemption existe parce que le CACHE DE VERDICT (#486-r1) est content-addressed : une entree
    perimee ne peut que MANQUER, donc faire recalculer. Toute exemption AJOUTEE ici doit venir
    avec le cliquet qui PROUVE sa neutralite -- sans ce cran, la classe s'elargirait entree par
    entree et redeviendrait une allowlist ordinaire."""
    import verdict_cache as VC
    assert P.prefixes_neutres() == (VC.DOSSIER.relative_to(VC.RACINE).as_posix() + "/",)


def test_la_PREUVE_de_neutralite_du_cache_EXISTE_et_recalcule():
    """L'exemption n'est legitime QUE tant que quelqu'un prouve, en RECALCULANT, que le cache ne
    peut pas mentir. Si cette preuve disparait, l'exemption doit tomber avec elle."""
    import verdict_cache as VC
    assert callable(getattr(VC, "verifier", None)), \
        "`verdict_cache.verifier` (le recalcul sans cache) a disparu"
    preuve = _PYDIR / "tests" / "test_486_r1_cache_verdict_offline.py"
    assert preuve.exists(), "le cliquet qui PROUVE la neutralite du cache a disparu"
    src = preuve.read_text(encoding="utf-8")
    assert "verifier(" in src, "la preuve ne recalcule plus rien"


def test_une_ecriture_du_CACHE_ne_salit_PAS_la_passe():
    prefixe = P.prefixes_neutres()[0]
    assert P457._salissures({}, {prefixe + "probe_x.tsv": "aa"}) == []


def test_un_VOISIN_du_cache_salit_bel_et_bien():
    """LA BORNE. Sans elle, une exemption trop large passerait ce fichier sans qu'on le voie --
    et `scripts/` porte precisement les quatre artefacts a cliquets."""
    assert P457._salissures({}, {"scripts/ratchets-457-durations.json": "aa"}) \
        == ["scripts/ratchets-457-durations.json"]


def test_probe_457_DELEGUE_l_exemption_au_FOYER():
    """Deux derivations d'un meme critere ouvrent un ecart SILENCIEUX : le capteur du shard
    pourrait exempter ce que `probe_956` accuse. On verifie la DELEGATION, pas l'egalite des
    valeurs -- deux implementations qui concordent aujourd'hui peuvent diverger demain."""
    src = (_PYDIR / "probe_457_offline_tests_green.py").read_text(encoding="utf-8")
    assert "from probe_956_purete_de_passe import prefixes_neutres" in src
    assert P457._prefixes_neutres() == P.prefixes_neutres()


# ------------------------------------------------- 6. `probe_457` PORTE REELLEMENT LE CAPTEUR

def test_la_passe_de_shard_MESURE_l_arbre_de_part_et_d_autre():
    """Un cliquet ecrit mais non CABLE ne garde rien. On lit le CABLAGE dans le source, comme
    `test_463r1` lit celui de `loop_status`."""
    src = (_PYDIR / "probe_457_offline_tests_green.py").read_text(encoding="utf-8")
    assert "avant_arbre = _etat_suivi()" in src, "la mesure AVANT la passe est absente"
    assert "_salissures(avant_arbre, _etat_suivi())" in src, "la mesure APRES la passe est absente"


def test_le_ledger_REFUSE_de_s_ecrire_sur_une_passe_impure():
    """Une attestation dit << vert SUR CET ARBRE >>. Si la passe a change l'arbre, elle ne
    designe plus un etat retrouvable."""
    src = (_PYDIR / "probe_457_offline_tests_green.py").read_text(encoding="utf-8")
    assert "salies=salies" in src, "le refus n'est pas alimente"
    assert "ledger NON ECRIT : la passe a MODIFIE" in src


def test_la_mesure_de_l_arbre_precede_l_ecriture_du_ledger():
    """L'INSTRUMENT NE SE MESURE PAS LUI-MEME (#547-r5). Le ledger que ce probe ecrit est un
    fichier VERSIONNE : mesure APRES, il ressortirait comme une salissure a chaque passe."""
    src = (_PYDIR / "probe_457_offline_tests_green.py").read_text(encoding="utf-8")
    i_mesure = src.index("_salissures(avant_arbre, _etat_suivi())")
    i_ledger = src.index("_ecrire_ledger(perimetre_complet, mine, bilan")
    assert i_mesure < i_ledger, "la seconde mesure doit PRECEDER l'ecriture du ledger"


def test_le_capteur_n_prend_PAS_le_verrou_de_l_index():
    """`git status` RAFRAICHIT l'index par defaut, donc prend `index.lock`. Ce capteur tourne
    dans CHAQUE shard et `--jobs N` en lance N en meme temps : sans `--no-optional-locks`, le
    capteur de la dependance au decoupage serait lui-meme dependant du decoupage."""
    src = (_PYDIR / "probe_457_offline_tests_green.py").read_text(encoding="utf-8")
    bloc = src.split("def _etat_suivi(")[1].split("\ndef ")[0]
    assert '"--no-optional-locks"' in bloc


def test_un_verdict_VERT_de_shard_affirme_desormais_les_DEUX_faits():
    """Le contrat rendu au lecteur : pytest vert ET arbre inchange. S'il ne disait que le
    premier, le second ne serait garde par rien de lisible."""
    src = (_PYDIR / "probe_457_offline_tests_green.py").read_text(encoding="utf-8")
    assert "VERDICT: PASS -- tous les tests offline du shard sont verts, et la passe n'a " in src


# ------------------------------------------------------------------- 7. L'ARBRE REEL

def test_le_filtre_statique_DISCRIMINE_sur_l_arbre_reel():
    """Un filtre qui retiendrait tout ne bornerait rien (le mode par defaut coincideraient avec
    la banque entiere, donc ne serait jamais joue) ; un filtre qui ne retiendrait rien ne
    mesurerait rien. On garde les deux bouts."""
    cands, perimetre = P.candidats()
    assert len(perimetre) > 100, "perimetre effondre (%d)" % len(perimetre)
    assert 0 < len(cands) < len(perimetre), \
        "%d candidat(s) sur %d : le filtre ne discrimine plus" % (len(cands), len(perimetre))


def test_un_temoin_connu_est_RETENU_par_le_filtre():
    """Anti-vacuite : le filtre doit retenir un fichier dont on SAIT qu'il lance des process.
    Sans ce cran, le test ci-dessus passerait sur un filtre devenu arbitraire."""
    cands, _ = P.candidats()
    temoin = "tests/test_463r1_ecart_empreinte_offline.py"
    assert temoin in cands, "%s lance des sous-processus et n'est pas retenu" % temoin
