"""#486-r12 -- garde du MECANISME DE DECLENCHEUR (`declencheur_cliquet` + `probe_486r12`).

Ce que ce fichier fige, et pourquoi chaque propriete est la :

    GLOB        `**/` vaut ZERO segment ou plus. Ce depot a paye la semantique inverse DEUX
                fois (#458 : 967 fichiers versionnes dans aucun seau ; #457-r5 : les 24
                fichiers poses directement sous `tests/`, les plus lourds du perimetre). Un
                matcher qui rate ce que le declarant croyait couvrir EST le faux vert.
    FORME       une declaration mal formee doit etre NOMMEE, pas devinee : cle manquante ou
                inventee, type faux, chemin absolu, `..`, raison vide, et surtout le
                perimetre VIDE avec `toujours: False` -- qui ne serait rejoue par RIEN.
    LECTURE     le `DECLENCHEUR` se lit par AST : importer le cliquet pour le lire tirerait
                `engine/` ou `pytest`, et un cliquet dont l'IMPORT plante ne pourrait plus
                declarer -- alors que c'est l'etat ou l'on veut le savoir.
    ROUGE       le garde SAIT rougir (cf. `probe_439`) sur ses DEUX fautes : ne pas declarer,
                et declarer TROP ETROIT.
    TRI-ETAT    une panne d'outil ou une entree non mesuree sort en 99, jamais en vert ni en
                rouge (cf. `probe_471`).
    PEREMPTION  une empreinte dont le sha ne correspond plus MANQUE -- elle n'est jamais
                SERVIE. C'est la regle de `verdict_cache` (#486-r1) : une attestation qui ne
                peut que manquer ne peut pas mentir.

Montage 100 % offline et JETABLE (`tmp_path`) : aucun cliquet de la banque n'est joue.
Les etages de verdict SUBSTITUENT `PYDIR` / `EMPREINTE` / la banque -- forme B (`M.x`), la
seule des trois qui morde (cf. CLAUDE.md).

ASCII only (console cp1252).
"""
import sys
from pathlib import Path

import pytest

_PYDIR = Path(__file__).resolve().parents[1]
if str(_PYDIR) not in sys.path:
    sys.path.insert(0, str(_PYDIR))

import declencheur_cliquet as DC              # noqa: E402
import declencheur_trace as DT                # noqa: E402
import probe_439_cliquet_peut_rougir as B439  # noqa: E402
import probe_486r12_declencheurs as G         # noqa: E402


# ======================================================================== le matcher de globs
@pytest.mark.parametrize("glob,rel,attendu", [
    # `**/` = ZERO segment ou plus -- les deux sens, c'est tout le sujet.
    ("scripts/python/**/*.py", "scripts/python/probe_x.py", True),
    ("scripts/python/**/*.py", "scripts/python/tests/engine/test_y.py", True),
    ("scripts/python/**/*.py", "scripts/python/engine/x.pyc", False),
    ("scripts/python/**/*.py", "scripts/ratchets.ps1", False),
    ("frida/**", "frida/hooks/main.ts", True),
    ("frida/**", "frida/x.ts", True),
    ("frida/**", "scripts/x.ts", False),
    # `*` ne traverse PAS un separateur.
    ("docs/rl/*.md", "docs/rl/case-1.md", True),
    ("docs/rl/*.md", "docs/rl/sub/case-1.md", False),
    # un chemin nomme, sans joker.
    ("data/seed-bc.json", "data/seed-bc.json", True),
    ("data/seed-bc.json", "data/seed-bc.json.bak", False),
    # `?` = un caractere, hors separateur.
    ("data/i2_??.json", "data/i2_en.json", True),
    ("data/i2_??.json", "data/i2_e/n.json", False),
])
def test_le_glob_a_la_semantique_git_pathspec(glob, rel, attendu):
    assert (DC.couvre([glob], rel) is not None) is attendu


def test_couvre_rend_le_GLOB_et_pas_un_booleen():
    """Quand le garde rougit, il doit dire par quoi la lecture etait CENSEE etre couverte."""
    assert DC.couvre(["a/**", "scripts/python/**/*.py"], "scripts/python/x.py") == \
        "scripts/python/**/*.py"
    assert DC.couvre(["a/**"], "scripts/python/x.py") is None


# ============================================================================== la validation
def _decl(**kw):
    base = {"chemins": ("scripts/python/**/*.py",), "build": False, "toujours": False,
            "raison": "il balaie tout scripts/python en AST, un fichier a la fois"}
    base.update(kw)
    return base


def test_une_declaration_bien_formee_ne_produit_aucune_faute():
    assert DC.valider(_decl()) == []


@pytest.mark.parametrize("mutation,fragment", [
    ({"chemins": ("C:/ailleurs/**",)}, "ABSOLU"),
    ({"chemins": ("/etc/**",)}, "ABSOLU"),
    ({"chemins": ("../voisin/**",)}, ".."),
    ({"chemins": ("scripts\\python\\**",)}, "separateur Windows"),
    ({"chemins": ("",)}, "vide"),
    ({"build": 1}, "booleen"),
    ({"toujours": "oui"}, "booleen"),
    ({"raison": "parce que"}, "trop courte"),
    ({"raison": 42}, "chaine"),
])
def test_chaque_faute_de_forme_est_NOMMEE(mutation, fragment):
    fautes = DC.valider(_decl(**mutation))
    assert fautes, "la mutation %r n'a produit AUCUNE faute" % (mutation,)
    assert any(fragment in f for f in fautes), fautes


def test_une_cle_manquante_et_une_cle_inventee_sont_les_deux_vues():
    d = _decl()
    del d["build"]
    d["chemin"] = ("x/**",)            # faute de frappe : personne ne la lirait
    fautes = DC.valider(d)
    assert any("manquante" in f for f in fautes), fautes
    assert any("inconnue" in f for f in fautes), fautes


def test_un_perimetre_VIDE_avec_toujours_False_est_REFUSE():
    """Le seul faux vert que la FORME seule peut voir : rien ne le rejouerait jamais."""
    fautes = DC.valider(_decl(chemins=(), toujours=False, build=False))
    assert any("rejouerait" in f for f in fautes), fautes
    # ... et `toujours: True` avec un perimetre vide est LEGITIME : c'est le defaut du contrat.
    assert DC.valider(_decl(chemins=(), toujours=True)) == []


def test_une_raison_non_ASCII_est_refusee():
    """Elle est IMPRIMEE sur une console cp1252 : un accent y leve `UnicodeEncodeError`."""
    fautes = DC.valider(_decl(raison="il balaie tout scripts/python, un fichier " + chr(224)))
    assert any("ASCII" in f for f in fautes), fautes


# ================================================================= le perimetre EFFECTIF
def test_le_perimetre_ajoute_le_SOURCE_du_cliquet_et_le_BUILD():
    d = _decl(chemins=("frida/**",), build=True)
    p = DC.perimetre(d, source_rel="scripts/python/probe_x.py")
    assert "frida/**" in p
    assert "data/symbols/**" in p, "build: True doit ouvrir la table de symboles"
    assert "scripts/python/probe_x.py" in p, "un cliquet doit toujours se rejouer sur SA modif"
    assert DC.couvre(p, "scripts/python/probe_x.py") is not None


def test_le_perimetre_ne_repete_pas_un_glob():
    d = _decl(chemins=("a/**", "a/**"))
    assert DC.perimetre(d, source_rel="a/x.py").count("a/**") == 1


# ================================================================= la lecture par AST
def test_le_DECLENCHEUR_se_lit_SANS_executer_le_module(tmp_path):
    f = tmp_path / "cliquet.py"
    f.write_text(
        "raise SystemExit('ce module ne doit JAMAIS etre execute')\n"
        "DECLENCHEUR = {'chemins': ('a/**',), 'build': False, 'toujours': False,\n"
        "               'raison': 'il ne lit que a/, un fichier a la fois, rien de plus'}\n",
        encoding="utf-8")
    d = DC.lire(f)
    assert d["chemins"] == ("a/**",)
    assert DC.valider(d) == []


def test_une_expression_meme_constante_n_est_PAS_un_litteral(tmp_path):
    """`'x' * 50` ou `A + B` levent : `ast.literal_eval` refuse toute OPERATION. C'est voulu --
    une declaration calculee ne se relit pas sans executer, et c'est tout l'objet du contrat.
    La concatenation IMPLICITE (`'a' 'b'`), elle, est fusionnee par le parser : les raisons
    multi-lignes des vrais declencheurs passent."""
    f = tmp_path / "c.py"
    f.write_text("DECLENCHEUR = {'chemins': ('a/**',), 'build': False, 'toujours': False,\n"
                 "               'raison': 'x' * 60}\n", encoding="utf-8")
    with pytest.raises(DC.DeclencheurAbsent):
        DC.lire(f)
    g = tmp_path / "d.py"
    g.write_text("DECLENCHEUR = {'chemins': ('a/**',), 'build': False, 'toujours': False,\n"
                 "               'raison': 'il ne lit que a/, un fichier a la fois, '\n"
                 "                         'et rien de plus'}\n", encoding="utf-8")
    assert DC.valider(DC.lire(g)) == []


def test_un_DECLENCHEUR_absent_ou_non_litteral_est_NOMME(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("X = 1\n", encoding="utf-8")
    with pytest.raises(DC.DeclencheurAbsent):
        DC.lire(f)
    g = tmp_path / "b.py"
    g.write_text("DECLENCHEUR = dict(chemins=('a/**',))\n", encoding="utf-8")
    with pytest.raises(DC.DeclencheurAbsent):
        DC.lire(g)                     # `dict(...)` est un APPEL, pas un litteral


def test_les_ONZE_cliquets_du_groupe_A_declarent_et_valident():
    """Cliquet du cliquet : la tranche #486-r12 a pose ces onze-la, ils doivent le rester."""
    onze = ["probe_181_targeting_gaps.py", "probe_437r1r1r1_effect_face_table.py",
            "probe_433r4r1r4r2_neigh_channel_wired.py", "probe_120_pre_unit_ability_fork.py",
            "probe_273_gitignored_inputs.py", "probe_319_scan_fidelity.py",
            "probe_365_versioned_imports_gitignored.py", "probe_464_sibling_script_cwd.py",
            "probe_391_conftest_dir_identity.py", "probe_313_enum_mirror_bijection.py",
            "probe_449r2_spread_inventory.py"]
    for nom in onze:
        d = DC.lire(_PYDIR / nom)
        assert DC.valider(d) == [], nom


def test_le_garde_est_soumis_a_SON_PROPRE_critere():
    """Exiger des autres une declaration sans en porter une serait indefendable -- meme
    principe que `probe_439`, qui est dans la banque qu'il garde."""
    d = DC.lire(_PYDIR / "probe_486r12_declencheurs.py")
    assert DC.valider(d) == []
    globs = DC.perimetre(d, source_rel="scripts/python/probe_486r12_declencheurs.py")
    # Les trois entrees qu'il LIT vraiment doivent etre couvertes par ce qu'il DECLARE.
    for lu in ("scripts/ratchets.ps1", "scripts/python/probe_181_targeting_gaps.py",
               "scripts/declencheurs-empreinte.tsv"):
        assert DC.couvre(globs, lu) is not None, lu


def test_le_programme_lance_est_lu_sous_la_forme_WINDOWS():
    """`sys.audit("subprocess.Popen", ...)` passe `exe=None` et une LIGNE DE COMMANDE sous
    Windows. Ne lire que `exe` rendait `programmes` vide -- donc `MESURE INCOMPLETE` muet sur
    les quatre cliquets qui lancent `git ls-files`."""
    assert DT.programme_de((None, "git --version", None, None)) == "git"
    assert DT.programme_de(("C:/x/git.exe", ["git", "status"], None, None)) == "git.exe"
    assert DT.programme_de((None, '"C:/Program Files/Git/git.exe" status', None, None)) \
        == "git.exe"
    assert DT.programme_de((None, ["pwsh", "-File", "x"], None, None)) == "pwsh"
    assert DT.programme_de((None, None, None, None)) == "<illisible>"


# ================================================================= le traceur de mesure
def test_le_pyc_est_ramene_a_sa_SOURCE():
    """Sans cette normalisation, la meme mesure rendrait deux perimetres selon l'etat du
    `__pycache__` de la machine -- le vice paye par #464-r2 sur `probe_457`."""
    assert DT.source_de("engine/__pycache__/x.cpython-313.pyc") == "engine/x.py"
    assert DT.source_de("a/b/__pycache__/mod.cpython-311.opt-1.pyc") == "a/b/mod.py"
    assert DT.source_de("engine/x.py") == "engine/x.py"


@pytest.mark.parametrize("args,ecriture", [
    (("p", "r", 0), False),
    (("p", "rb", 0), False),
    (("p", "w", 0), True),
    (("p", "a", 0), True),
    (("p", "r+", 0), True),
    (("p", None, 0), False),
])
def test_une_ECRITURE_n_entre_pas_dans_le_perimetre(args, ecriture):
    """Un cliquet ne DEPEND pas de ce qu'il produit (son cache, un tmpdir)."""
    assert DT._est_ecriture(args) is ecriture


def test_le_hook_enregistre_une_lecture_du_depot_et_ignore_le_reste(tmp_path):
    racine = tmp_path / "depot"
    (racine / "scripts").mkdir(parents=True)
    (racine / "logs").mkdir()
    dedans = racine / "scripts" / "x.py"
    dedans.write_text("# x\n", encoding="utf-8")
    sortie = racine / "logs" / "y.txt"
    sortie.write_text("# y\n", encoding="utf-8")
    dehors = tmp_path / "ailleurs.txt"
    dehors.write_text("# z\n", encoding="utf-8")

    t = DT._Trace.__new__(DT._Trace)       # sans `sys.addaudithook` : il est IRREVERSIBLE
    t.racine = str(racine).replace("\\", "/") + "/"
    t._prefixe = t.racine.lower()
    t._n = len(t.racine)
    t.dossier = tmp_path / "trace"
    t.lectures, t.programmes, t._ecrit = set(), set(), False

    for p in (dedans, sortie, dehors):
        t._hook("open", (str(p), "r", 0))
    t._hook("open", (str(dedans), "w", 0))
    t._hook("subprocess.Popen", ("C:/x/git.exe", ["git", "status"], None, None))

    assert t.lectures == {"scripts/x.py"}, t.lectures
    assert t.programmes == {"git.exe"}
    assert DT.opaques(t.programmes) == ["git.exe"]


# ================================================= le garde : ROUGE, VERT, et NON MESURE
BANQUE_JETABLE = """
$Ratchets = @(
    @{ Id = 'probe_zz'; Argv = @('probe_zz.py')
       Seul = 'rien -- banque jetable de test'
       Doc  = 'aucune' }
)
"""

CLIQUET_JETABLE = """DECLENCHEUR = {
    "chemins": (%s),
    "build": False,
    "toujours": %s,
    "raison": "banque jetable : il lit ce que le montage lui fait lire, rien d autre",
}
"""


def _montage(tmp_path, monkeypatch, chemins, lu, toujours="False", sha_juste=True):
    """Un depot JETABLE : une banque d'UNE entree, un cliquet, une empreinte fabriquee."""
    pydir = tmp_path / "scripts" / "python"
    pydir.mkdir(parents=True)
    src = CLIQUET_JETABLE % (chemins, toujours)
    (pydir / "probe_zz.py").write_text(src, encoding="utf-8")
    banque = tmp_path / "scripts" / "ratchets.ps1"
    banque.write_text(BANQUE_JETABLE, encoding="utf-8")
    emp = tmp_path / "scripts" / "declencheurs-empreinte.tsv"

    monkeypatch.setattr(B439, "BANQUE", banque)
    monkeypatch.setattr(G, "PYDIR", pydir)
    monkeypatch.setattr(G, "ROOT", tmp_path)
    monkeypatch.setattr(G, "EMPREINTE", emp)

    e = G.Empreinte()
    sha = G.sha_source("probe_zz.py") if sha_juste else "sha-perime"
    e.par_id["probe_zz"] = {"sha": sha, "lu": G.grouper(lu), "proc": [], "nproc": 1}
    e.ecrire(emp)
    return emp


def _rc(monkeypatch, argv=("probe_486r12_declencheurs.py",)):
    monkeypatch.setattr(sys, "argv", list(argv))
    return G.main()


def test_VERT_quand_tout_ce_qui_est_LU_est_couvert(tmp_path, monkeypatch, capsys):
    _montage(tmp_path, monkeypatch, chemins='"scripts/python/**/*.py",',
             lu=["scripts/python/a.py", "scripts/python/sous/b.py"])
    rc = _rc(monkeypatch)
    assert rc == 0, capsys.readouterr().out


def test_ROUGE_quand_le_cliquet_LIT_hors_de_son_perimetre(tmp_path, monkeypatch, capsys):
    """LA faute que ce cliquet existe pour voir : un declencheur trop ETROIT."""
    _montage(tmp_path, monkeypatch, chemins='"scripts/python/**/*.py",',
             lu=["scripts/python/a.py", "data/symbols/zz/frida/enums.tsv"])
    rc = _rc(monkeypatch)
    sortie = capsys.readouterr().out
    assert rc == 1, sortie
    assert "hors de leur perimetre DECLARE" in sortie
    assert "data/symbols/zz/frida/enums.tsv" in sortie


def test_ROUGE_quand_un_script_de_la_banque_ne_DECLARE_pas(tmp_path, monkeypatch, capsys):
    emp = _montage(tmp_path, monkeypatch, chemins='"scripts/python/**/*.py",',
                   lu=["scripts/python/a.py"])
    (tmp_path / "scripts" / "python" / "probe_zz.py").write_text("X = 1\n", encoding="utf-8")
    assert emp.is_file()
    rc = _rc(monkeypatch)
    sortie = capsys.readouterr().out
    assert rc == 1, sortie
    assert "sans `DECLENCHEUR`" in sortie


def test_toujours_True_ne_confronte_RIEN_et_reste_VERT(tmp_path, monkeypatch, capsys):
    """`toujours: True` = il se rejoue de toute facon : une lecture << hors perimetre >> n'y
    signifie plus rien, et l'accuser dissuaderait d'ecrire le defaut prudent."""
    _montage(tmp_path, monkeypatch, chemins="", toujours="True",
             lu=["n/importe/quoi.bin", "ailleurs/encore.txt"])
    assert _rc(monkeypatch) == 0, capsys.readouterr().out


def test_NON_MESURE_quand_l_empreinte_MANQUE(tmp_path, monkeypatch, capsys):
    emp = _montage(tmp_path, monkeypatch, chemins='"scripts/python/**/*.py",',
                   lu=["scripts/python/a.py"])
    emp.unlink()
    rc = _rc(monkeypatch)
    sortie = capsys.readouterr().out
    assert rc == 99, sortie
    assert "NON MESUREE" in sortie


def test_une_empreinte_PERIMEE_n_est_jamais_SERVIE(tmp_path, monkeypatch, capsys):
    """Le source du cliquet a change depuis la mesure : l'entree MANQUE, elle ne ment pas."""
    _montage(tmp_path, monkeypatch, chemins='"scripts/python/**/*.py",',
             lu=["scripts/python/a.py"], sha_juste=False)
    rc = _rc(monkeypatch)
    sortie = capsys.readouterr().out
    assert rc == 99, sortie
    assert "PERIMEE" in sortie


def test_une_mesure_a_ZERO_process_ne_vaut_pas_un_VERT(tmp_path, monkeypatch, capsys):
    """Un run tue avant d'avoir rien trace laisserait un perimetre VIDE, donc trivialement
    couvert. Un vert fabrique par une panne est pire qu'un rouge."""
    emp = _montage(tmp_path, monkeypatch, chemins='"scripts/python/**/*.py",', lu=[])
    txt = emp.read_text(encoding="utf-8").replace("probe_zz\tnproc\t1", "probe_zz\tnproc\t0")
    emp.write_text(txt, encoding="utf-8")
    rc = _rc(monkeypatch)
    assert rc == 99, capsys.readouterr().out


def test_INDISPONIBLE_quand_la_banque_n_est_pas_derivable(tmp_path, monkeypatch, capsys):
    """Panne d'OUTIL, jamais un verdict sur le depot (cf. `probe_471`)."""
    monkeypatch.setattr(B439, "BANQUE", tmp_path / "absente.ps1")
    rc = _rc(monkeypatch)
    sortie = capsys.readouterr().out
    assert rc == 99, sortie
    assert "RIEN n'a ete mesure" in sortie


def test_le_perimetre_du_garde_est_DERIVE_de_la_banque(tmp_path, monkeypatch):
    """Aucune liste ecrite a la main : une entree neuve doit entrer d'elle-meme."""
    _montage(tmp_path, monkeypatch, chemins='"scripts/python/**/*.py",',
             lu=["scripts/python/a.py"])
    banque = tmp_path / "scripts" / "ratchets.ps1"
    banque.write_text(BANQUE_JETABLE.replace(
        "    @{ Id = 'probe_zz'",
        "    @{ Id = 'probe_neuf'; Argv = @('probe_neuf.py')\n"
        "       Seul = 'entree neuve'\n"
        "       Doc  = 'aucune' }\n"
        "    @{ Id = 'probe_zz'"), encoding="utf-8")
    scripts = G.par_script(G.banque())
    assert set(scripts) == {"probe_zz.py", "probe_neuf.py"}


def test_les_shards_d_un_meme_script_partagent_UNE_declaration():
    """`probe_283:*` et `probe_457:*` sont des DECOUPAGES de cout, pas des perimetres. Une
    declaration par argv se perimerait au premier re-decoupage."""
    scripts = G.par_script({"a:s0": ["p.py", "--shard", "0/2"],
                            "a:s1": ["p.py", "--shard", "1/2"]})
    assert scripts == {"p.py": ["a:s0", "a:s1"]}
