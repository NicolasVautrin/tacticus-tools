"""#486-r29 -- L'ORDRE rend le rouge de `probe_486r15` STRUCTURELLEMENT INVISIBLE a son auteur.

CE QUE CE FICHIER GARDE, ET POURQUOI IL NE POUVAIT PAS EXISTER AVANT
--------------------------------------------------------------------
`probe_486r15` confronte une declaration a l'UNION de DEUX sources : la fermeture d'imports
(exacte, calculee) et les TEMOINS de l'empreinte `probe_457` (ce que le fichier a reellement
OUVERT). Sans entree d'empreinte, la seconde source est VIDE et le cliquet verifie la premiere
SEULE -- qui est strictement plus etroite.

Or l'ordre prescrit partout jusqu'au 2026-08-08 etait `probe_486r15` PUIS
`probe_457 --measure-missing`. L'auteur jouait donc le cliquet a UNE source, gravait l'empreinte
juste apres, et livrait ; la confrontation passait a DEUX sources AU MERGE.

MESURE : PR #832, verte chez son auteur, ROUGE sur `master` au commit de merge `18edd540` --
8 chemins manquants, TOUS apportes par les temoins, 0 par la fermeture, et l'entree d'empreinte
fautive arrivee DANS LA MEME PR. Parc au 2026-08-08 : 28 des 74 declarations (38 %) sans
entree d'empreinte ; 206 chemins apportes par les temoins et invisibles de la fermeture sur les
46 restantes.

LE TEMOIN CENTRAL est `test_le_verdict_BASCULE_de_VERT_a_ROUGE_par_la_seule_gravure_de_l_empreinte` :
MEME arbre, MEME declaration, MEME cliquet -- seule l'entree d'empreinte est ajoutee, et le rc
passe de 0 a 1. C'est exactement le regime de la PR #832, reproduit de bout en bout.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_486r15_declencheurs_tests.py",
        "scripts/python/declencheur_cliquet.py",
        "scripts/python/repo_read.py",
    ),
    "build": False,
    "toujours": False,
    "raison": (
        "Il garde la RESERVE que #486-r29 pose sur le verdict de `probe_486r15` : il monte un "
        "arbre de test synthetique et appelle `G.main`, donc il ne depend que du probe, du "
        "contrat de declaration qu'il consomme et de la lecture de depot partagee. Aucun "
        "chemin de donnee : l'empreinte et la dette sont ecrites dans `tmp_path`."
    ),
}

import json                                                                   # noqa: E402
import sys                                                                    # noqa: E402
from pathlib import Path                                                      # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import declencheur_cliquet as DC                                              # noqa: E402
import probe_486r15_declencheurs_tests as G                                   # noqa: E402

#: Le chemin que la declaration NE couvre PAS et que seule la seconde source revele : un
#: fichier OUVERT sans etre importe -- exactement ce que la fermeture d'imports ne peut pas voir.
OUVERT_SANS_IMPORT = "scripts/python/engine/runner/caches/ability_and_effect_cache.py"

REL = "scripts/python/tests/test_a_offline.py"


def _monte(tmp_path, monkeypatch, temoins=None, motif=None, couvre_l_ouvert=False):
    """Un depot minuscule : un module IMPORTE, et un chemin OUVERT que seuls les temoins voient.

    `temoins is None` => AUCUNE entree d'empreinte (le regime a UNE source).
    `temoins = (...)`  => l'entree existe (le regime a DEUX sources).
    """
    py = tmp_path / "scripts" / "python"
    (py / "tests").mkdir(parents=True)
    (py / "cible.py").write_text("X = 1\n", encoding="utf-8")

    chemins = ["scripts/python/cible.py"]
    if couvre_l_ouvert:
        chemins.append(OUVERT_SANS_IMPORT)
    decl = {"chemins": tuple(chemins), "build": False, "toujours": False,
            "raison": "r" * (DC.RAISON_MIN + 5)}
    if motif is not None:
        # Un bypass DOIT masquer quelque chose, sinon l'etage 3 le declare MORT (et il a
        # raison). On lui laisse donc un decouvert reel : la declaration ne couvre plus
        # l'import. `build=True` parce qu'un perimetre VIDE + `toujours: False` est refuse
        # par la FORME -- deux crans distincts qu'il ne faut pas confondre.
        decl.update({"chemins": (), "build": True, DC.CLE_HORS_CONFRONTATION: motif})
    (py / "tests" / "test_a_offline.py").write_text(
        "DECLENCHEUR = %r\nimport cible\n" % (decl,), encoding="utf-8")

    dette = tmp_path / "scripts" / "ratchets-486r15-dette-declencheurs.txt"
    dette.write_text("# vide\n", encoding="utf-8")
    bypass = tmp_path / "scripts" / "ratchets-486r24-bypass-confrontation.txt"
    bypass.write_text(("# atteste\n%s\n" % REL) if motif is not None else "# vide\n",
                      encoding="utf-8")

    empreinte = tmp_path / "scripts" / "ratchets-457-footprints.json"
    if temoins is None:
        # Le fichier d'empreinte EXISTE mais ne porte AUCUNE entree pour ce test : c'est le
        # regime exact d'un fichier de test NEUF, avant `--measure-missing`.
        empreinte.write_text(json.dumps({"_format": 2, "par_test": {}}), encoding="utf-8")
    else:
        empreinte.write_text(json.dumps({
            "_format": 2,
            "par_test": {"tests/test_a_offline.py": {"temoins": list(temoins), "dirs": []}},
        }), encoding="utf-8")

    monkeypatch.setattr(G, "ROOT", tmp_path)
    monkeypatch.setattr(G, "DETTE", dette)
    monkeypatch.setattr(G, "BYPASS", bypass)
    monkeypatch.setattr(G, "EMPREINTE", empreinte)
    monkeypatch.setattr(G, "fichiers_de_test", lambda: [REL])
    monkeypatch.setattr(DC, "RACINE", tmp_path)
    DC._HARNAIS.clear()


# =====================================================================================
#  [1] LE TEMOIN CENTRAL -- le verdict bascule par la SEULE gravure de l'empreinte
# =====================================================================================
def test_le_verdict_BASCULE_de_VERT_a_ROUGE_par_la_seule_gravure_de_l_empreinte(
        tmp_path, monkeypatch, capsys):
    """MEME arbre, MEME declaration. Sans empreinte : rc 0. Avec : rc 1. C'est la PR #832.

    Ce test est la raison d'etre de la reserve : il montre que le vert de l'auteur et le rouge
    du merge portent sur le MEME code, et ne different que par un artefact grave ENTRE les deux.
    """
    _monte(tmp_path, monkeypatch, temoins=None)
    assert G.main([]) == 0, "sans entree d'empreinte, la fermeture SEULE est verifiee -- vert"
    avant = capsys.readouterr().out
    assert "PASS SOUS RESERVE" in avant

    # ... et maintenant l'empreinte est gravee, comme `--measure-missing` le ferait.
    _monte(tmp_path / "apres", monkeypatch, temoins=(OUVERT_SANS_IMPORT,))
    assert G.main([]) == 1, ("avec l'entree d'empreinte, la seconde source revele le chemin "
                             "ouvert-sans-import -- ROUGE, sur un code INCHANGE")
    apres = capsys.readouterr().out
    assert "DECLARE TROP ETROIT" in apres
    assert OUVERT_SANS_IMPORT in apres


# =====================================================================================
#  [2] LE VERT SE QUALIFIE -- il dit de quoi il est le vert
# =====================================================================================
def test_un_fichier_SANS_empreinte_fait_QUALIFIER_le_verdict(tmp_path, monkeypatch, capsys):
    _monte(tmp_path, monkeypatch, temoins=None)
    assert G.main([]) == 0
    out = capsys.readouterr().out
    assert "PASS SOUS RESERVE" in out, "le verdict lui-meme doit porter la reserve"
    assert "1 a UNE SEULE" in out, "le COMPTE des declarations a une seule source est dit"
    assert REL in out, "et le fichier concerne est NOMME, pas seulement compte"


def test_le_verdict_est_un_PASS_PLEIN_des_que_la_confrontation_a_ses_DEUX_sources(
        tmp_path, monkeypatch, capsys):
    """La contre-epreuve : sans elle, `PASS SOUS RESERVE` pourrait etre l'unique sortie verte
    et l'assertion ci-dessus passerait pour un cran alors qu'elle ne discriminerait rien."""
    _monte(tmp_path, monkeypatch, temoins=(OUVERT_SANS_IMPORT,), couvre_l_ouvert=True)
    assert G.main([]) == 0
    out = capsys.readouterr().out
    assert "PASS SOUS RESERVE" not in out
    assert "VERDICT: PASS" in out
    assert "1 confrontee(s) aux DEUX sources" in out


def test_le_compte_des_CONFRONTEES_n_englobe_plus_les_NON_MESUREES(tmp_path, monkeypatch,
                                                                  capsys):
    """La faute EXACTE de l'ancienne sortie : `len(ok) - len(bypass)` rangeait les declarations
    sans empreinte parmi les << confrontee(s) >>, ce qui etait faux."""
    _monte(tmp_path, monkeypatch, temoins=None)
    G.main([])
    out = capsys.readouterr().out
    assert "0 confrontee(s) aux DEUX sources" in out, out[-400:]


# =====================================================================================
#  [3] L'ORDRE EST ECRIT LA OU IL EST JOUE, pas seulement dans un brief qu'on recopie
# =====================================================================================
def test_le_probe_PRESCRIT_l_ordre_quand_il_rend_une_reserve(tmp_path, monkeypatch, capsys):
    _monte(tmp_path, monkeypatch, temoins=None)
    G.main([])
    out = capsys.readouterr().out
    assert "--measure-missing" in out and "D'ABORD" in out, (
        "la reserve doit etre ACTIONNABLE : un agent qui la lit doit savoir quoi jouer, et "
        "dans quel ordre -- une prescription qui ne vit que dans un gabarit de brief se "
        "recopie sans etre relue")
    assert "18edd540" in out, "la mesure qui fonde l'ordre est citee, pas seulement l'ordre"


def test_un_PASS_PLEIN_ne_prescrit_RIEN(tmp_path, monkeypatch, capsys):
    """Un outil qui repete son conseil quand il n'a pas lieu d'etre finit par n'etre plus lu."""
    _monte(tmp_path, monkeypatch, temoins=(OUVERT_SANS_IMPORT,), couvre_l_ouvert=True)
    G.main([])
    assert "D'ABORD" not in capsys.readouterr().out


# =====================================================================================
#  [4] LA RESERVE NE COMPTE PAS CE QUI EST DEJA EXEMPTE
# =====================================================================================
def test_un_fichier_HORS_CONFRONTATION_n_entre_PAS_dans_la_reserve(tmp_path, monkeypatch,
                                                                  capsys):
    """Un bypass a DEJA renonce a la confrontation, et il l'a dit. L'absence d'empreinte n'y
    ajoute aucune incertitude : compter ces fichiers dans la reserve la diluerait, et une
    reserve diluee ne se lit plus."""
    _monte(tmp_path, monkeypatch, temoins=None,
           motif="il BALAIE l'arbre, aucune enumeration ne le borne")
    assert G.main([]) == 0
    out = capsys.readouterr().out
    assert "PASS SOUS RESERVE" not in out, out[-400:]
    assert "HORS CONFRONTATION" in out
