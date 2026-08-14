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
        # PROPRE A CE FICHIER :
        "scripts/python/probe_457_offline_tests_green.py",
        # Entre dans la cascade avec #486-r23 : `probe_457` importe le ledger.
        "scripts/python/ledger_vert_offline.py",
        # #463-r1 : le FOYER du recensement offline, dont `probe_457` ET `loop_status` (tous deux
        # sous test ici) tirent leur perimetre.
        "scripts/python/probe_463r1_ecart_empreinte_offline.py",
        # ROUGES PREEXISTANTS de `master`, mesures le 2026-08-07 sur `3a09dc1d` : la
        # confrontation lisait deja ces deux-la sans qu'ils soient declares. Repares ici parce
        # que ce fichier est de toute facon touche -- ils n'ont rien a voir avec #463-r1.
        "scripts/python/verdict_cache.py",
        "scripts/ratchets-457-footprints.json",
        "scripts/python/probe_486r15_declencheurs_tests.py",
        "scripts/python/declencheur_cliquet.py", "scripts/python/repo_read.py",
        "scripts/python/tests/**/*.py",
        "scripts/ratchets-486r15-dette-declencheurs.txt",
        # Le capteur de visibilite (#467) et sa dependance de flotte.
        "scripts/python/loop_status.py", "scripts/python/fleet_board.py",
        # #547-r2 : la confrontation ECHANTILLONNE des entrees de l'empreinte et OUVRE les
        # fichiers qu'elles nomment -- ce module `engine` y entre par cette voie, jamais par un
        # import. L'empreinte REECRITE en entier l'a montre.
        "scripts/python/engine/runner/operations/triggers/__init__.py",
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
    rouges, _, _ = G.confronter({fichier: ampute})
    assert rouges, "une declaration amputee de sa dependance doit ROUGIR"
    assert any("verdict_cache" in x for x in rouges[0][1])


def test_la_confrontation_DIT_ce_qu_elle_n_a_pas_pu_mesurer():
    """TRI-ETAT : une entree d'empreinte absente n'est pas << il n'ouvre rien >>, c'est
    << pas mesure >>. Le garde ne doit pas valider par defaut sur cette absence."""
    tem, mesure = G.temoins_mesures("scripts/python/tests/test_qui_n_existe_pas_offline.py")
    assert tem == () and mesure is False


# ---------------------------------------------------------- 6. le CAPTEUR de visibilite (#467)

import json                                                             # noqa: E402
import loop_status as LS                                                # noqa: E402


class _SourcesJetables(LS.Sources):
    """Un depot ECRIT, pour exercer le capteur sans dependre de l'etat du checkout courant."""

    def __init__(self, repo, fichiers, rc=0):
        super().__init__(repo=repo, ttl_cache=0.0)
        self._fichiers, self._rc = fichiers, rc

    def git(self, *args):
        assert args[:1] == ("ls-files",), args
        return self._rc, self._fichiers


def _repo_jetable(tmp_path, emp):
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    if emp is not None:
        (tmp_path / "scripts" / "ratchets-457-footprints.json").write_text(
            json.dumps(emp), encoding="utf-8")
    return tmp_path


def test_le_capteur_VOIT_l_empreinte_incomplete(tmp_path):
    """LE CAPTEUR QUI MANQUAIT. La degradation etait DITE par `probe_457`, dans une ligne noyee
    que personne n'a lue pendant 3 jours et ~40 commits -- un capteur muet est un garde-fou mort."""
    repo = _repo_jetable(tmp_path, {"_format": P.FORMAT_EMPREINTE,
                                    "par_test": {"tests/test_a_offline.py": _entree()}})
    src = _SourcesJetables(repo, "scripts/python/tests/test_a_offline.py\n"
                                 "scripts/python/tests/test_b_offline.py\n"
                                 "scripts/python/tests/test_c_live.py\n")
    d = LS.mesurer_empreinte(src)
    assert d["couverture"].mesuree
    # #463-r1 : la valeur porte desormais la VENTILATION (`manquants` / `fantomes`) et non plus
    # le seul compte d'INTERSECTION -- une intersection ne montre jamais ce qui deborde. Le point
    # que ce cas garde depuis #486-r15 est INCHANGE (le `_live.py` ne compte pas, donc
    # `perimetre == 2`) ; l'egalite reste STRICTE, sur un dict plus large, et le manquant est
    # desormais NOMME, ce que l'ancienne forme ne permettait pas.
    assert d["couverture"].valeur == {"format": 2, "couverts": 1, "perimetre": 2,
                                      "manquants": ["tests/test_b_offline.py"],
                                      "fantomes": []}, \
        "le `_live.py` ne doit pas compter -- `probe_457` ne le selectionne pas"
    sig, _ctx = LS.signaux({"flotte": _FLOTTE, "livraison": _LIVRAISON, "harnais": _HARNAIS,
                            "empreinte": d})
    assert any(s.cle == "empreinte" for s in sig), "l'incompletude doit etre ACTIONNABLE"


def test_le_capteur_VOIT_un_format_perime(tmp_path):
    """Le format 1 est ce que `master` portait : `--since` le refuse et rejoue TOUT, en silence."""
    repo = _repo_jetable(tmp_path, {"_commit": "x", "par_test": {"tests/test_a_offline.py": ["docs"]}})
    src = _SourcesJetables(repo, "scripts/python/tests/test_a_offline.py\n")
    d = LS.mesurer_empreinte(src)
    sig, _ = LS.signaux({"flotte": _FLOTTE, "livraison": _LIVRAISON, "harnais": _HARNAIS,
                         "empreinte": d})
    assert any(s.cle == "empreinte-format" for s in sig)


def test_le_capteur_se_TAIT_quand_l_empreinte_est_COMPLETE(tmp_path):
    """LA BORNE : sans elle, un capteur qui alarme toujours passerait les deux cas ci-dessus --
    et se ferait desarmer dans la semaine."""
    repo = _repo_jetable(tmp_path, {"_format": P.FORMAT_EMPREINTE,
                                    "par_test": {"tests/test_a_offline.py": _entree()}})
    src = _SourcesJetables(repo, "scripts/python/tests/test_a_offline.py\n")
    sig, _ = LS.signaux({"flotte": _FLOTTE, "livraison": _LIVRAISON, "harnais": _HARNAIS,
                         "empreinte": LS.mesurer_empreinte(src)})
    assert not [s for s in sig if s.cle.startswith("empreinte")]


@pytest.mark.parametrize("cas", ["git muet", "empreinte absente", "aucun test"])
def test_le_capteur_ne_fabrique_JAMAIS_un_zero(tmp_path, cas):
    """TRI-ETAT (#467) : `null` = PAS mesure, jamais un zero -- ni alarmant, ni rassurant."""
    if cas == "git muet":
        src = _SourcesJetables(_repo_jetable(tmp_path, {}), "", rc=LS.Sources.RC_MUET)
    elif cas == "empreinte absente":
        src = _SourcesJetables(_repo_jetable(tmp_path, None),
                               "scripts/python/tests/test_a_offline.py\n")
    else:
        src = _SourcesJetables(_repo_jetable(tmp_path, {}), "")
    d = LS.mesurer_empreinte(src)
    assert not d["couverture"].mesuree, "%s doit rendre PAS MESURE" % cas
    assert d["couverture"].valeur is None
    sig, ctx = LS.signaux({"flotte": _FLOTTE, "livraison": _LIVRAISON, "harnais": _HARNAIS,
                           "empreinte": d})
    assert not [s for s in sig if s.cle.startswith("empreinte")], \
        "une PANNE de capteur ne doit pas se lire comme un gisement"
    assert any("empreinte 457" in c for c in ctx), "elle doit quand meme etre DITE"


def test_le_format_attendu_par_le_capteur_SUIT_la_source():
    """La constante est RECOPIEE dans `loop_status` (l'importer y traine pytest). Une recopie qui
    derive ferait alarmer a tort -- benin -- mais rien ne le dirait. Ceci le dit."""
    assert LS.FORMAT_EMPREINTE_ATTENDU == P.FORMAT_EMPREINTE


#: Etats NEUTRES des trois autres postes : ces cas ne jugent que l'empreinte.
_FLOTTE = {"en_vol": LS._ok(0, "t"), "libres": LS._ok(0, "t"), "plafond": 6,
           "noms": LS._ok([], "t"), "chemins": set()}
_LIVRAISON = {"avance": LS._ok(0, "t"), "retard": LS._ok(0, "t"),
              "suivis_sales": LS._ok([], "t"),
              "worktrees": LS._ok([], "t"), "nettoyables": LS._ok([], "t"),
              "pr_ouvertes": LS._ok([], "t"), "branche": LS._ok("master", "t"),
              "non_suivis": LS._ok(0, "t"), "non_suivis_inconnus": LS._ok([], "t")}
_HARNAIS = {"session": LS._ok(None, "t"), "drain": LS._ok(False, "t"),
            "jeu": LS._ok(True, "t"), "live_runners": LS._ok(0, "t")}


