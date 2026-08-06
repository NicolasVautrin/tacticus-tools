"""#486-r15 -- garde du TAMPON PAR ENTREE de l'empreinte et de la moitie DECLAREE de la selection.

CE QU'IL GARDE, ET POURQUOI CHAQUE ETAGE EXISTE
------------------------------------------------
La selection par diff est le SEUL endroit de ce depot ou l'on peut fabriquer un FAUX VERT : elle
RETIRE des tests du perimetre. Trois proprietes la rendent acceptable, et ce fichier les tient :

  1. **un tampon PAR ENTREE, jamais un tampon GLOBAL.** L'empreinte portait un `_commit` unique,
     ecrit dans le worktree d'un AGENT donc sur une branche que le squash-merge remplace puis
     SUPPRIME. Mesure du 2026-08-07 : `57bb2a7c` inconnu de git, et `--since` rendait **220/220
     fichiers sur chacune des 8 dernieres bases de PR**. Un seul sha mort effondrait 49 entrees
     autonomes ;
  2. **JAMAIS MESURE n'est pas MESURE-ET-VIDE.** L'absence d'entree se lisait << ce test n'ouvre
     aucun fichier du depot >>, une affirmation jamais gagnee -- 88 entrees pour 220 fichiers
     offline sur `master`. Une empreinte videe ne sur-selectionne pas, elle SOUS-selectionne ;
  3. **la mise a jour PARTIELLE ne pretend rien sur ce qu'elle n'a pas joue.** C'est elle qui rend
     la fraicheur auto-reparatrice : un module change entre dans le diff, donc son test est
     selectionne, donc joue, donc son entree est REECRITE.

BON MARCHE PAR CONSTRUCTION. Aucun etage ne calcule le graphe d'imports de l'arbre reel (29,5 s
mesurees) : les cas injectent un graphe synthetique. Le seul etage qui touche l'arbre reel est le
cliquet d'obligation, mesure a 2,5 s. C'est la lecon de #486-r5 -- une garde qui re-balaie le
corpus rouvre le gisement qu'elle ferme.

ASCII only (console cp1252).
"""

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: Meme contrat que les cliquets de la banque (`declencheur_cliquet.py`).
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
        "scripts/python/probe_486r15_declencheurs_tests.py",
        "scripts/python/declencheur_cliquet.py", "scripts/python/repo_read.py",
        "scripts/python/tests/**/*.py",
        "scripts/ratchets-486r15-dette-declencheurs.txt",
    ),
    "build": False,
    "toujours": False,
    "raison": "Les deux probes sous test, leurs foyers importes, la DETTE versionnee que le "
              "cliquet d'obligation confronte, et TOUS les fichiers de test -- le perimetre du "
              "cliquet en est DERIVE par `git ls-files`, donc un fichier de test ajoute ou "
              "retire change ce qu'il compte et ce qu'il exige.",
}

import sys                                                              # noqa: E402
from pathlib import Path                                                # noqa: E402

import pytest                                                           # noqa: E402

_PYDIR = Path(__file__).resolve().parents[1]
if str(_PYDIR) not in sys.path:
    sys.path.insert(0, str(_PYDIR))

import declencheur_cliquet as DC                                        # noqa: E402
import probe_457_offline_tests_green as P                               # noqa: E402
import probe_486r15_declencheurs_tests as G                             # noqa: E402

PERIMETRE = ["tests/a_offline.py", "tests/b_offline.py", "tests/c_offline.py"]


def _entree(dirs=(), commit="mort", at=1):
    """Une entree d'empreinte au FORMAT 2. `_commit` y est du CONTEXTE, jamais un critere."""
    return {"_at": at, "_commit": commit, "dirs": list(dirs), "temoins": []}


@pytest.fixture
def empreinte(monkeypatch):
    """Injecte une empreinte SYNTHETIQUE, un diff controle et un graphe NEUTRE.

    Rien de l'arbre reel n'entre ici : le graphe d'imports de ce depot coute 29,5 s, et une garde
    qui le paie a chaque cas serait exactement le cliquet trop cher de #486-r5."""
    def poser(par_test, changes, globales=(), mods=None, inverse=None, incertains=None,
              declares=None, format_=P.FORMAT_EMPREINTE):
        monkeypatch.setattr(P, "_footprints",
                            lambda: {"_format": format_, "_globales": list(globales),
                                     "par_test": par_test})
        monkeypatch.setattr(P, "_changed", lambda ref: changes)
        monkeypatch.setattr(P, "_import_graph",
                            lambda m: (inverse or {}, incertains or set()))
        monkeypatch.setattr(P, "_modules_du_graphe", lambda racine=None:
                            {m: m for m in (mods or [])})
        monkeypatch.setattr(P, "declencheurs_du_perimetre",
                            lambda perim, racine=None: (dict(declares or {}), {}))
    return poser


# ---------------------------------------------------------------- 1. le tampon PAR ENTREE

def test_un_commit_MORT_dans_une_entree_n_empeche_PLUS_rien(empreinte):
    """LE DEFAUT REPARE. Un sha ecrit sur une branche d'agent est MORT-NE : le squash-merge cree
    un commit neuf et supprime la branche. Avant #486-r15 ce sha unique rendait l'empreinte
    ENTIERE inverifiable, et `--since` rejouait 220/220."""
    empreinte(par_test={r: _entree(commit="0" * 40) for r in PERIMETRE},
              changes=["docs/rl/note.md"])
    retenus, raison = P.impacted_files(PERIMETRE, "REF")
    assert retenus == [], (
        "un `_commit` inconnu de git ne doit plus rien invalider : il est du CONTEXTE (%s)"
        % raison)


def test_le_SQUASH_ne_tue_plus_l_empreinte(empreinte, monkeypatch):
    """Contre-epreuve DIRECTE du scenario mesure : la branche qui portait le commit a disparu.

    On rend `_changed` incapable de resoudre le sha de mesure -- exactement ce que git fait apres
    un squash-merge -- et l'empreinte doit rester EXPLOITABLE."""
    def diff(ref):
        return None if ref.startswith("0") else ["docs/rl/note.md"]

    empreinte(par_test={r: _entree(commit="0" * 40) for r in PERIMETRE}, changes=[])
    monkeypatch.setattr(P, "_changed", diff)
    retenus, _ = P.impacted_files(PERIMETRE, "REF")
    assert retenus == [], "l'empreinte ne doit plus rien demander a la ref de sa mesure"


# ------------------------------------------------- 2. JAMAIS MESURE n'est pas MESURE-ET-VIDE

def test_une_entree_ABSENTE_est_JAMAIS_MESUREE_donc_rejouee(empreinte):
    """LE FAUX VERT FERME. `rel not in par_test` se lisait << aucune dependance hors-.py >>."""
    empreinte(par_test={"tests/a_offline.py": _entree()}, changes=["docs/rl/note.md"])
    retenus, raison = P.impacted_files(PERIMETRE, "REF")
    assert set(retenus) == {"tests/b_offline.py", "tests/c_offline.py"}, (
        "un fichier sans entree n'a JAMAIS ete mesure -- il ne peut pas etre declare independant "
        "(%s)" % raison)
    assert "jamais mesure" in raison, "la cause doit etre DITE, pas devinee"


def test_une_entree_MESUREE_ET_VIDE_n_est_PAS_rejouee(empreinte):
    """LA BORNE : sans elle, le correctif ci-dessus rendrait la selection inutile (tout rejoue).

    Une entree presente avec `dirs` VIDE est une MESURE -- le test a tourne sous le hook d'audit
    et n'a ouvert aucun fichier du depot. C'est ce que le format 2 rend enfin distinguable."""
    empreinte(par_test={r: _entree() for r in PERIMETRE}, changes=["docs/rl/note.md"])
    retenus, _ = P.impacted_files(PERIMETRE, "REF")
    assert retenus == [], "une entree mesuree et vide PROUVE l'independance -- elle doit valoir"


def test_un_format_INCONNU_rejoue_TOUT_et_le_dit(empreinte):
    empreinte(par_test={}, changes=["docs/rl/note.md"], format_=1)
    retenus, raison = P.impacted_files(PERIMETRE, "REF")
    assert retenus == PERIMETRE
    assert "format" in raison and "TOUT rejoue" in raison


# ---------------------------------------------------------------- 3. mise a jour PARTIELLE

def _fusion(mesures, lus, complete, ancien, monkeypatch):
    monkeypatch.setattr(P, "_footprints", lambda: ancien)
    return P._empreinte_fusionnee(
        mesures=mesures, lus_par_test=lus,
        dossiers=lambda c: sorted({x.rsplit("/", 1)[0] for x in c if "/" in x}),
        temoins=lambda c: sorted(c),
        globales=["scripts/python/pytest.ini"], commit="abc", complete=complete,
        mods={})


def test_une_passe_PARTIELLE_ne_pretend_RIEN_sur_ce_qu_elle_n_a_pas_joue(monkeypatch):
    """LE COEUR DE LA TRANCHE. Le refus etait STRUCTUREL tant que `_commit` horodatait le tout."""
    ancien = {"_format": P.FORMAT_EMPREINTE, "_globales": ["data/seed-bc.json"],
              "par_test": {"tests/a_offline.py": _entree(["docs/rl"], commit="vieux", at=7),
                           "tests/b_offline.py": _entree(["data"], commit="vieux", at=7)}}
    emp = _fusion(["tests/b_offline.py"], {"tests/b_offline.py": ["frida/hooks/x.ts"]},
                  False, ancien, monkeypatch)
    assert emp["par_test"]["tests/a_offline.py"] == ancien["par_test"]["tests/a_offline.py"], \
        "une entree NON rejouee doit rester mot pour mot ce qu'elle etait"
    assert emp["par_test"]["tests/b_offline.py"]["dirs"] == ["frida/hooks"], \
        "l'entree rejouee doit etre REECRITE depuis la mesure de cette passe"
    assert emp["par_test"]["tests/b_offline.py"]["_commit"] == "abc"


def test_une_passe_PARTIELLE_ne_RETRECIT_jamais_les_globales(monkeypatch):
    """Les globales ne declenchent qu'un rejeu TOTAL : les retrecir est le seul sens dangereux.

    Une passe partielle n'a vu que la collecte de SES fichiers -- elle unit, elle ne remplace pas."""
    ancien = {"_format": P.FORMAT_EMPREINTE, "_globales": ["data/seed-bc.json"], "par_test": {}}
    emp = _fusion(["tests/a_offline.py"], {}, False, ancien, monkeypatch)
    assert set(emp["_globales"]) == {"data/seed-bc.json", "scripts/python/pytest.ini"}


def test_une_passe_COMPLETE_remplace_tout(monkeypatch):
    ancien = {"_format": P.FORMAT_EMPREINTE, "_globales": ["data/vieux.json"],
              "par_test": {"tests/disparu.py": _entree(["docs/rl"])}}
    emp = _fusion(["tests/a_offline.py"], {}, True, ancien, monkeypatch)
    assert list(emp["par_test"]) == ["tests/a_offline.py"], \
        "une passe complete a TOUT vu : une entree qu'elle n'a pas produite n'existe plus"
    assert emp["_globales"] == ["scripts/python/pytest.ini"]


def test_une_entree_est_ecrite_pour_CHAQUE_fichier_joue_meme_sans_lecture(monkeypatch):
    """C'est ce qui rend l'absence lisible comme << jamais mesure >> -- sans cela, rien ne
    distingue un test qui n'ouvre rien d'un test qui n'a jamais tourne."""
    emp = _fusion(["tests/a_offline.py", "tests/b_offline.py"],
                  {"tests/a_offline.py": ["docs/rl/x.md"]}, True, {}, monkeypatch)
    assert set(emp["par_test"]) == {"tests/a_offline.py", "tests/b_offline.py"}
    assert emp["par_test"]["tests/b_offline.py"]["dirs"] == []


# ---------------------------------------------------------------- 4. la moitie DECLAREE

def test_un_DECLENCHEUR_qui_matche_le_diff_retient_son_fichier(empreinte):
    empreinte(par_test={r: _entree() for r in PERIMETRE}, changes=["docs/rl/note.md"],
              declares={"tests/a_offline.py": ("docs/rl/*.md",)})
    retenus, raison = P.impacted_files(PERIMETRE, "REF")
    assert retenus == ["tests/a_offline.py"], raison
    assert "declare 1" in raison, "la cause doit etre ventilee"


def test_un_DECLENCHEUR_qui_ne_matche_PAS_ne_retient_pas(empreinte):
    empreinte(par_test={r: _entree() for r in PERIMETRE}, changes=["frida/hooks/x.ts"],
              declares={"tests/a_offline.py": ("docs/rl/*.md",)})
    retenus, _ = P.impacted_files(PERIMETRE, "REF")
    assert retenus == []


def test_le_GRAPHE_n_est_PAS_calcule_si_tout_est_declare(empreinte, monkeypatch):
    """LE GAIN. Le graphe pese 29,5 s ; l'evaluation des declarations, 0,23 s pour les 220
    fichiers (dont 1 ms d'appariement). Il ne doit donc etre paye que s'il reste a decider."""
    empreinte(par_test={}, changes=["docs/rl/note.md"],
              declares={r: ("docs/rl/*.md",) for r in PERIMETRE})

    def interdit(_mods):
        raise AssertionError("le graphe d'imports a ete calcule alors que TOUT etait declare")

    monkeypatch.setattr(P, "_import_graph", interdit)
    retenus, _ = P.impacted_files(PERIMETRE, "REF")
    assert set(retenus) == set(PERIMETRE)


def test_l_ordre_du_perimetre_est_CONSERVE(empreinte):
    """Les shards doivent voir exactement la meme liste : la partition est deterministe."""
    empreinte(par_test={r: _entree(["docs/rl"]) for r in PERIMETRE}, changes=["docs/rl/n.md"],
              declares={"tests/c_offline.py": ("docs/rl/*.md",)})
    retenus, _ = P.impacted_files(PERIMETRE, "REF")
    assert retenus == PERIMETRE, "l'ordre doit suivre le perimetre, pas l'ordre de decision"


def test_une_declaration_MAL_FORMEE_n_est_PAS_servie():
    """Servir une declaration douteuse serait le seul sens dangereux : elle RETIRE des tests."""
    assert DC.valider({"chemins": ("a/*.py",), "build": False, "toujours": False,
                       "raison": "x"}), "une raison de 1 caractere doit etre refusee"
    assert DC.valider({"chemins": ("/abs/x.py",), "build": False, "toujours": False,
                       "raison": "une raison assez longue pour passer le seuil de forme du "
                                 "contrat"}), "un chemin ABSOLU doit etre refuse"
    assert not DC.valider({"chemins": ("scripts/python/x.py",), "build": False,
                           "toujours": False,
                           "raison": "une raison assez longue pour passer le seuil de forme du "
                                     "contrat partage"})


def test_les_declarations_REELLES_de_l_echantillon_sont_BIEN_FORMEES():
    """Anti-vacuite : sans ce non-vide, tous les etages declaratifs ci-dessus ne prouveraient rien."""
    servis, _ = P.declencheurs_du_perimetre(P.candidate_files())
    assert len(servis) >= 8, "echantillon de declarations effondre (%d)" % len(servis)
    for rel, globs in servis.items():
        assert "scripts/python/" + rel in globs, \
            "%s : le foyer doit ajouter le SOURCE lui-meme au perimetre" % rel


# ---------------------------------------------------------------- 5. le cliquet d'OBLIGATION

def test_le_perimetre_du_cliquet_est_DERIVE_et_NON_VIDE():
    """Jamais une allowlist : un fichier de test NEUF doit y entrer TOUT SEUL (#457-r5, #455-r3)."""
    fichiers = G.fichiers_de_test()
    assert len(fichiers) > 400, "perimetre effondre (%d) -- le cliquet ne prouverait rien" % len(
        fichiers)
    assert all(f.startswith("scripts/python/tests/") for f in fichiers)
    # Les DEUX conventions de collecte de pytest, pas seulement celle qui se trouve exister.
    assert G.est_fichier_de_test("test_x.py") and G.est_fichier_de_test("x_test.py")
    assert not G.est_fichier_de_test("conftest.py")


def test_un_fichier_de_test_NEUF_sans_declaration_est_ROUGE(tmp_path, monkeypatch):
    """L'OBLIGATION. La dette TOLERE l'existant ; elle ne peut pas absoudre un fichier neuf."""
    neuf = tmp_path / "test_neuf_sans_declaration.py"
    neuf.write_text("def test_rien():\n    assert True\n", encoding="utf-8")
    monkeypatch.setattr(G, "ROOT", tmp_path)
    ok, ko = G.declarations([neuf.name])
    assert ok == {} and neuf.name in ko
    assert "aucun `DECLENCHEUR`" in ko[neuf.name]


def test_la_DETTE_ne_peut_pas_absoudre_ce_qui_declare_deja():
    """Une entree de dette PERIMEE (le fichier declare depuis) doit etre SIGNALEE, pas ignoree --
    sinon la dette cesserait de retrecir sans que personne le voie."""
    dette = G.lire_dette()
    assert dette, "dette absente -- le cliquet jouerait le critere SEC sans le dire"
    declarants, _ = G.declarations(G.fichiers_de_test())
    assert not (dette & set(declarants)), \
        "la dette porte des fichiers qui declarent : la regenerer (--ecrire-dette)"


def test_la_CONFRONTATION_voit_une_declaration_TROP_ETROITE():
    """MUTATION : sans elle, un `PASS` ne prouverait que l'absence de declaration a confronter.

    On ampute une declaration REELLE de son entree specifique et on exige que le garde rougisse.
    """
    fichier = "scripts/python/tests/test_486_r1_cache_verdict_offline.py"
    vraie = DC.lire(G.ROOT / fichier)
    assert not G.confronter({fichier: vraie})[0], \
        "la declaration REELLE doit passer -- sinon la mutation ci-dessous ne prouve rien"

    ampute = dict(vraie)
    ampute["chemins"] = tuple(c for c in vraie["chemins"]
                              if "verdict_cache" not in c and "cliquets-cache" not in c)
    assert len(ampute["chemins"]) < len(vraie["chemins"]), "la mutation n'a pas MORDU"
    rouges, _ = G.confronter({fichier: ampute})
    assert rouges, "une declaration amputee de sa dependance doit ROUGIR"
    assert any("verdict_cache" in x for x in rouges[0][1])


def test_la_confrontation_DIT_ce_qu_elle_n_a_pas_pu_mesurer():
    """TRI-ETAT : une entree d'empreinte absente n'est pas << il n'ouvre rien >>, c'est
    << pas mesure >>. Le garde ne doit pas valider par defaut sur cette absence."""
    tem, mesure = G.temoins_mesures("scripts/python/tests/test_qui_n_existe_pas_offline.py")
    assert tem == () and mesure is False
