"""#486-r27 / #486-r30 -- le gate qu'un auteur INTERROGE doit juger ce qui compte.

#486-r27 : LE HOOK PYTEST NE VALIDAIT QUE LA PRESENCE
------------------------------------------------------
`declencheur_guard` n'exposait que `manquants()` (presence, derivee de `git ls-files`) et
n'appelait JAMAIS `declencheur_cliquet.valider`. La FORME et la CONFRONTATION n'etaient jugees
que par `probe_486r15`, qu'aucune passe de test ne joue et dont l'obligation est levee depuis le
2026-08-07.

MESURE (PR #824) : `test_448_r1_r1_r2_r2_gates_abandon_offline.py` est passe avec DEUX cles sur
quatre (`build` et `raison` absentes) et un chemin non couvert, et son auteur a ecrit
<< `DECLENCHEUR` pose pour garder rc 0 >>. Le gate qu'il a interroge lui a repondu VERT.

L'arbitrage est tranche par le COUT : la FORME est pure (un `dict` deja en memoire, aucune I/O)
donc elle descend dans le hook ; la CONFRONTATION coute une fermeture d'imports par fichier
(~440 modules pour un seul test) donc elle reste au probe. Ces tests gardent LES DEUX MOITIES
de cet arbitrage -- y compris que la seconde n'est PAS descendue.

#486-r30 : UN ROUGE QUI NE DIT PAS CE QU'IL N'A PAS REGARDE
-------------------------------------------------------------
`probe_486r15` s'arretait a la declaration MAL FORMEE avant de confronter le perimetre. Mesure
du 2026-08-08 sur `test_175e_175r_tile_meta_live.py` : une seconde faute (6 chemins de fermeture
non declares) etait CACHEE par la premiere (`build`/`toujours` absents), et il a fallu DEUX
tranches pour les trouver l'une apres l'autre.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        "scripts/python/declencheur_guard.py",
        "scripts/python/declencheur_cliquet.py",
        "scripts/python/probe_486r15_declencheurs_tests.py",
        "scripts/python/repo_read.py",
    ),
    "build": False,
    "toujours": False,
    "raison": (
        "Il garde les DEUX moities de l'arbitrage presence/forme/confrontation : le hook de "
        "collecte (`declencheur_guard`), le contrat de forme qu'il appelle desormais "
        "(`declencheur_cliquet.valider`), et le probe qui garde la confrontation. Il monte "
        "des declarations en memoire et un arbre synthetique -- aucune donnee lue."
    ),
}

import sys                                                                    # noqa: E402
from pathlib import Path                                                      # noqa: E402

import pytest                                                                 # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import declencheur_cliquet as DC                                              # noqa: E402
import declencheur_guard as GU                                                # noqa: E402
import probe_486r15_declencheurs_tests as G                                   # noqa: E402

REL = "scripts/python/tests/test_a_offline.py"

#: La declaration EXACTE de la PR #824 : deux cles sur quatre. Elle etait acceptee par le hook.
DECL_824 = {"chemins": ("scripts/python/engine/ai/context.py",), "toujours": False}

BONNE = {"chemins": ("scripts/python/cible.py",), "build": False, "toujours": False,
         "raison": "r" * (DC.RAISON_MIN + 5)}


class _Item:
    """Le minimum qu'un item pytest doit offrir a `pytest_collection_modifyitems`."""

    def __init__(self, module, chemin):
        self.module = module
        self.path = chemin


class _Module:
    def __init__(self, decl):
        if decl is not None:
            setattr(self, GU.NOM, decl)
        self.__file__ = str(GU.RACINE / REL)


def _collecte(monkeypatch, decl, suivi=True, dette=()):
    """Joue le hook de collecte sur UN fichier portant `decl`, et rend `fautifs()`."""
    monkeypatch.setattr(GU, "_MANQUANTS", {})
    monkeypatch.setattr(GU, "dette", lambda: set(dette))
    monkeypatch.setattr(GU, "_suivis_par_git", lambda: {REL} if suivi else set())
    mod = _Module(decl)
    GU.pytest_collection_modifyitems(None, None, [_Item(mod, GU.RACINE / REL)])
    return GU.fautifs()


# =====================================================================================
#  [1] #486-r27 -- LA FORME EST JUGEE PAR LE GATE QUE L'AUTEUR INTERROGE
# =====================================================================================
def test_la_declaration_EXACTE_de_la_PR_824_est_desormais_REFUSEE(monkeypatch):
    """Deux cles sur quatre. C'est litteralement ce qui est passe le 2026-08-07."""
    faux = _collecte(monkeypatch, DECL_824)
    assert REL in faux, "le hook doit voir la faute que `probe_486r15` voyait seul"
    assert faux[REL] is not None, "et la distinguer d'une declaration ABSENTE"
    joint = " ".join(faux[REL])
    assert "build" in joint and "raison" in joint, joint


def test_une_declaration_BIEN_FORMEE_reste_VERTE(monkeypatch):
    """Contre-epreuve : sans elle, un hook qui rougirait sur TOUT passerait pour un cran."""
    assert _collecte(monkeypatch, BONNE) == {}


def test_l_ABSENCE_reste_distincte_de_la_MALFORMATION(monkeypatch):
    """Les deux fautes n'ont pas le meme remede, ni la meme tolerance par la dette."""
    faux = _collecte(monkeypatch, None)
    assert faux == {REL: None}


@pytest.mark.parametrize("decl,attendu", [
    ({**BONNE, "raison": "trop courte"}, "trop courte"),
    ({**BONNE, "chemins": ("C:/absolu/x.py",)}, "ABSOLU"),
    ({**BONNE, "chemins": ("scripts\\python\\x.py",)}, "separateur Windows"),
    ({**BONNE, "toujours": "oui"}, "booleen"),
    ({**BONNE, "chemins": ("../dehors.py",)}, "ne sort pas du depot"),
    ({**BONNE, "inventee": 1}, "cle(s) inconnue(s)"),
    ({**BONNE, "chemins": 42}, "tuple/list"),
    ("pas un dict", "n'est pas un dict"),
])
def test_le_hook_porte_TOUT_le_contrat_de_forme_pas_un_sous_ensemble(monkeypatch, decl, attendu):
    """Le hook APPELLE `valider`, il ne recopie pas ses regles -- sinon les deux moities
    divergeraient, exactement le vice que `#526-r4` a trouve sur la grammaire des ids."""
    faux = _collecte(monkeypatch, decl)
    assert REL in faux and attendu in " ".join(faux[REL]), faux.get(REL)


def test_la_DETTE_ne_tolere_que_l_ABSENCE_jamais_une_declaration_MAL_FORMEE(monkeypatch):
    """Un fichier qui ECRIT la constante a cesse de s'appuyer sur la tolerance."""
    assert _collecte(monkeypatch, None, dette=(REL,)) == {}, "l'absence, elle, est toleree"
    faux = _collecte(monkeypatch, DECL_824, dette=(REL,))
    assert REL in faux and faux[REL] is not None


def test_un_REACTIF_synthetique_non_versionne_reste_hors_de_portee(monkeypatch):
    """Plusieurs cliquets deposent des fichiers de test synthetiques pour prouver qu'ils
    mordent. Leur demander une declaration n'a aucun sens -- et le filtre git valait DEJA
    pour l'absence : il doit valoir aussi pour la forme."""
    assert _collecte(monkeypatch, DECL_824, suivi=False) == {}


def test_git_MUET_garde_TOUS_les_candidats(monkeypatch):
    """Tri-etat : sur-selectionner un rouge est sain, l'inverse serait un faux vert."""
    monkeypatch.setattr(GU, "_MANQUANTS", {})
    monkeypatch.setattr(GU, "dette", set)
    monkeypatch.setattr(GU, "_suivis_par_git", lambda: None)
    GU.pytest_collection_modifyitems(None, None,
                                     [_Item(_Module(DECL_824), GU.RACINE / REL)])
    assert REL in GU.fautifs()


# =====================================================================================
#  [1bis] #486-r31 -- LA REGLE DU PERIMETRE VIDE A DEUX POPULATIONS, ET DEUX VERITES
# =====================================================================================
#: La declaration EXACTE de `tests/engine/runner/test_refresh_active_flag_discriminant_offline.py`
#: (merge par la PR #834) : `valider` rendait 1 erreur quand `perimetre` rendait 475 chemins.
VIDE = {"chemins": (), "build": False, "toujours": False,
        "raison": "r" * (DC.RAISON_MIN + 5)}


def test_pour_un_CLIQUET_le_perimetre_VIDE_reste_ROUGE():
    """LE PREMIER des deux sens. Rien ne s'ajoute a ce qu'un cliquet de banque declare : son
    perimetre effectif EST son perimetre declare, donc `toujours: False` + rien = jamais rejoue.
    Une correction qui ne garderait que l'autre sens rouvrirait ce faux vert-la."""
    fautes = DC.valider(VIDE)
    assert any("perimetre VIDE" in f for f in fautes), fautes


def test_pour_un_TEST_le_perimetre_VIDE_est_BORNE_pas_vide():
    """LE SECOND. `perimetre(d, source_rel)` ajoute le fichier LUI-MEME et la cascade de ses
    `conftest.py` : `chemins: ()` y dit << rejoue-moi quand MOI ou mon harnais changent >>."""
    assert DC.valider(VIDE, perimetre_derive=True) == []


def test_les_DEUX_temoins_sont_NON_NULS_sur_le_depot_REEL():
    """Une regle a deux sens dont un seul est observable ne garde qu'a moitie.

    Cote TEST : le perimetre effectif d'un fichier de test REEL est massivement non vide --
    c'est la mesure (475 chemins) qui a montre la contradiction. Cote CLIQUET : `perimetre`
    sans `source_rel` ne rend rien de plus que le declare.
    """
    reel = "scripts/python/tests/test_486r27_forme_au_hook_offline.py"
    effectif = DC.perimetre(VIDE, reel)
    assert len(effectif) > 3, effectif
    assert reel in effectif, "le fichier LUI-MEME entre dans son propre perimetre"
    assert DC.perimetre(VIDE) == (), "sans source_rel, rien ne s'ajoute : c'est le cas CLIQUET"


def test_la_borne_ne_DISPARAIT_pas_pour_les_tests_elle_CHANGE_de_cran(tmp_path, monkeypatch,
                                                                     capsys):
    """Un test qui declare `chemins: ()` en important quelque chose reste ROUGE -- par la
    CONFRONTATION, qui est le garde adapte a cette question. On deplace la faute vers le cran
    qui sait la voir, on ne la supprime pas."""
    py = tmp_path / "scripts" / "python"
    (py / "tests").mkdir(parents=True)
    (py / "cible.py").write_text("X = 1\n", encoding="utf-8")
    (py / "tests" / "test_a_offline.py").write_text(
        "DECLENCHEUR = %r\nimport cible\n" % (VIDE,), encoding="utf-8")
    dette = tmp_path / "scripts" / "ratchets-486r15-dette-declencheurs.txt"
    dette.write_text("# vide\n", encoding="utf-8")
    (tmp_path / "scripts" / "ratchets-486r24-bypass-confrontation.txt").write_text(
        "# vide\n", encoding="utf-8")
    monkeypatch.setattr(G, "ROOT", tmp_path)
    monkeypatch.setattr(G, "DETTE", dette)
    monkeypatch.setattr(G, "BYPASS", tmp_path / "scripts"
                        / "ratchets-486r24-bypass-confrontation.txt")
    monkeypatch.setattr(G, "EMPREINTE", tmp_path / "absente.json")
    monkeypatch.setattr(G, "fichiers_de_test", lambda: [REL])
    monkeypatch.setattr(DC, "RACINE", tmp_path)
    DC._HARNAIS.clear()
    assert G.main([]) == 1
    out = capsys.readouterr().out
    assert "MAL FORMEE" not in out, "la FORME ne l'accuse plus -- c'etait la faute de #486-r31"
    assert "DECLARE TROP ETROIT" in out, out[-500:]
    assert "scripts/python/cible.py" in out


def test_la_CONFRONTATION_n_est_PAS_descendue_dans_le_hook(monkeypatch):
    """L'AUTRE moitie de l'arbitrage, et elle se garde aussi.

    Une declaration BIEN FORMEE mais TROP ETROITE doit rester VERTE au hook : la confronter
    exigerait une fermeture d'imports par fichier, a chaque passe, y compris les passes live a
    4 workers. Si un jour quelqu'un la descend ici << pendant qu'il y est >>, ce test tombe et
    l'arbitrage est re-instruit au lieu d'etre subi.
    """
    etroite = {"chemins": ("scripts/python/rien-du-tout.py",), "build": False,
               "toujours": False, "raison": "r" * (DC.RAISON_MIN + 5)}
    assert _collecte(monkeypatch, etroite) == {}


# =====================================================================================
#  [2] #486-r30 -- LE ROUGE DIT CE QU'IL N'A PAS REGARDE
# =====================================================================================
def _arbre(tmp_path, monkeypatch, decl):
    py = tmp_path / "scripts" / "python"
    (py / "tests").mkdir(parents=True)
    (py / "cible.py").write_text("X = 1\n", encoding="utf-8")
    (py / "tests" / "test_a_offline.py").write_text(
        "DECLENCHEUR = %r\nimport cible\n" % (decl,), encoding="utf-8")
    dette = tmp_path / "scripts" / "ratchets-486r15-dette-declencheurs.txt"
    dette.write_text("# vide\n", encoding="utf-8")
    (tmp_path / "scripts" / "ratchets-486r24-bypass-confrontation.txt").write_text(
        "# vide\n", encoding="utf-8")
    monkeypatch.setattr(G, "ROOT", tmp_path)
    monkeypatch.setattr(G, "DETTE", dette)
    monkeypatch.setattr(G, "BYPASS", tmp_path / "scripts"
                        / "ratchets-486r24-bypass-confrontation.txt")
    monkeypatch.setattr(G, "EMPREINTE", tmp_path / "absente.json")
    monkeypatch.setattr(G, "fichiers_de_test", lambda: [REL])
    monkeypatch.setattr(DC, "RACINE", tmp_path)
    DC._HARNAIS.clear()


def test_une_declaration_MAL_FORMEE_est_QUAND_MEME_confrontee(tmp_path, monkeypatch, capsys):
    """Les DEUX fautes dans la MEME passe -- c'est le gisement de `test_175e_175r`."""
    # Mal formee (`build`/`raison` absentes) ET trop etroite (elle n'annonce pas `cible.py`).
    _arbre(tmp_path, monkeypatch, {"chemins": ("scripts/python/ailleurs.py",),
                                   "toujours": False})
    assert G.main([]) == 1
    out = capsys.readouterr().out
    assert "MAL FORMEE" in out
    assert "SON PERIMETRE EST TROP ETROIT" in out, out[-700:]
    assert "scripts/python/cible.py" in out, "le chemin decouvert doit etre NOMME"


def test_une_declaration_MAL_FORMEE_mais_bien_BORNEE_le_DIT_aussi(tmp_path, monkeypatch,
                                                                 capsys):
    """Contre-epreuve : le probe ne doit pas se contenter d'accuser -- quand le perimetre est
    couvert, il le DIT, sinon << perimetre >> ne serait qu'un mot ajoute a chaque rouge."""
    _arbre(tmp_path, monkeypatch, {"chemins": ("scripts/python/cible.py",),
                                   "toujours": False})
    assert G.main([]) == 1
    out = capsys.readouterr().out
    assert "MAL FORMEE" in out
    assert "perimetre : couvert" in out, out[-700:]
    assert "TROP ETROIT" not in out


def test_une_declaration_ILLISIBLE_dit_que_le_perimetre_N_A_PAS_ete_examine(tmp_path,
                                                                           monkeypatch,
                                                                           capsys):
    """Le tri-etat du volet : quand la lecture echoue, on ne DEVINE pas un perimetre couvert."""
    py = tmp_path / "scripts" / "python"
    (py / "tests").mkdir(parents=True)
    (py / "tests" / "test_a_offline.py").write_text(
        "DECLENCHEUR = (\n", encoding="utf-8")            # syntaxe cassee : `lire` echoue
    dette = tmp_path / "scripts" / "ratchets-486r15-dette-declencheurs.txt"
    dette.write_text("# vide\n", encoding="utf-8")
    (tmp_path / "scripts" / "ratchets-486r24-bypass-confrontation.txt").write_text(
        "# vide\n", encoding="utf-8")
    monkeypatch.setattr(G, "ROOT", tmp_path)
    monkeypatch.setattr(G, "DETTE", dette)
    monkeypatch.setattr(G, "BYPASS", tmp_path / "scripts"
                        / "ratchets-486r24-bypass-confrontation.txt")
    monkeypatch.setattr(G, "EMPREINTE", tmp_path / "absente.json")
    monkeypatch.setattr(G, "fichiers_de_test", lambda: [REL])
    monkeypatch.setattr(DC, "RACINE", tmp_path)
    DC._HARNAIS.clear()
    assert G.main([]) == 1
    assert "PERIMETRE NON EXAMINE" in capsys.readouterr().out
