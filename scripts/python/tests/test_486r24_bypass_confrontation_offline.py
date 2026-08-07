#!/usr/bin/env python
"""#486-r24 / #531 -- LE BYPASS DECLARE, ET LA CASCADE DE HARNAIS DERIVEE.

CE QUE CE FICHIER GARDE, ET POURQUOI IL FALLAIT LES DEUX ENSEMBLE
------------------------------------------------------------------
`probe_486r15` rougissait sur le TROP ETROIT et benissait le TROP LARGE. L'auteur rationnel
ecrivait donc un glob couvrant tout le Python : vert pour toujours. Mesure du 2026-08-07 sur
`origin/master` -- 54 des 63 declarations portaient au moins un glob INDISCRIMINANT (a joker,
couvrant un fichier de test ou un probe TIERS), et 0 declarait honnetement `toujours: True`.

Deux causes DISTINCTES, deux reponses DISTINCTES, et les confondre aurait juste renomme le
probleme :

  * **la CASCADE (29 fichiers)** -- ils n'etaient trop larges que par les `conftest.py` qu'ils
    trainent. Aucun test n'importe son conftest (semantique pytest, invisible a l'AST), et
    pourtant son verdict en depend. Reponse : le FOYER la DERIVE (`chemins_du_harnais`), le
    declarant ne l'ecrit plus. Ce n'est pas un assouplissement -- le perimetre effectif est le
    MEME qu'avec les lignes recopiees, seul l'auteur change ;
  * **le BALAYAGE (4 fichiers)** -- ils LISENT l'arbre, aucune enumeration ne les bornera.
    Reponse : `hors_confrontation`, une cle qui EST sa raison, comptee et attestee.

Les 19 restants n'ont besoin ni de l'un ni de l'autre : 1 a 12 chemins NOMMABLES, le plus
souvent le probe frere du test.

LE CRAN QUI EMPECHE LE BYPASS DE DEVENIR L'ECHAPPATOIRE UNIVERSELLE
---------------------------------------------------------------------
Un bypass qui ne masque AUCUN decouvert est un ROUGE (declaration MORTE). Sans lui, les 29 de la
cascade et les 2 decoratifs auraient pose la cle par imitation -- c'est exactement le mecanisme
mesure sur les imports differes (32 des 52 gratuits vivaient dans un module portant deja un
differe legitime). Le cran est un INVARIANT exact, pas un seuil : il se derive de la mesure du
fichier, il ne se degrade pas quand le parc grossit.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: La cascade des `conftest.py` n'y est PAS : le foyer la DERIVE (ajout 3). C'est le premier
#: fichier du depot a en faire l'economie, et c'est le point demontre plus bas.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/declencheur_cliquet.py",
        "scripts/python/probe_486r15_declencheurs_tests.py",
        "scripts/python/repo_read.py",
        "scripts/ratchets-486r24-bypass-confrontation.txt",
        # LU par l'anti-vacuite : les deux exemplaires du BALAYAGE, dont la declaration reelle
        # est confrontee ici.
        "scripts/python/tests/test_464_sibling_script_offline.py",
        "scripts/python/tests/test_457_r8_selection_par_diff_offline.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Le contrat (`declencheur_cliquet`), le cliquet qui l'applique aux tests, la "
              "population ATTESTEE du bypass, et les deux declarations reelles que l'anti-vacuite "
              "lit. La cascade de harnais est DERIVEE par le foyer, donc absente d'ici a dessein.",
    # LE BYPASS, APPLIQUE A CE FICHIER-CI -- et ce n'est pas une commodite, c'est la mesure.
    # `test_la_population_ATTESTEE_...` relit les 767 fichiers de test du depot pour verifier
    # que le fichier d'attestation correspond au depot, et `test_chaque_bypass_reel_...` resout
    # la fermeture d'imports des porteurs. Un garde de population LIT sa population : c'est
    # exactement le regime BALAYAGE des deux exemplaires ci-dessus, et le nier en enumerant
    # `scripts/python/tests/**` reviendrait a reecrire le glob universel sous un autre nom.
    "hors_confrontation":
        "Il BALAIE le parc : l'anti-vacuite relit les 767 fichiers de test versionnes pour "
        "confronter le fichier d'attestation au depot, et resout la fermeture d'imports des "
        "porteurs de bypass. Ce qu'il LIT est le parc entier ; ce dont son verdict DEPEND est "
        "le contrat et le cliquet, declares ci-dessus.",
}

import sys
from pathlib import Path

import pytest

import declencheur_cliquet as DC
import probe_486r15_declencheurs_tests as G

ROOT = Path(__file__).resolve().parents[3]


def _decl(**kw):
    d = {"chemins": ("a/b.py",), "build": False, "toujours": False,
         "raison": "x" * (DC.RAISON_MIN + 5)}
    d.update(kw)
    return d


# =============================================================== [1] LA FORME DE LA CLE
def test_la_cle_est_FACULTATIVE_et_son_absence_ne_vaut_PAS_un_bypass():
    assert DC.valider(_decl()) == []
    assert DC.hors_confrontation(_decl()) is None


def test_le_motif_EST_la_cle_donc_on_ne_peut_pas_bypasser_SANS_dire_pourquoi():
    """Il n'existe aucune valeur << vraie >> a poser : la cle porte une CHAINE ou rien.

    C'est la difference avec un `bypass: True` -- celui-la se copie-colle sans reflechir, et le
    lecteur suivant ne peut pas distinguer << ce test depend vraiment de tout >> de << j'ai pas
    eu le temps >>."""
    assert DC.valider(_decl(hors_confrontation=True)), "un booleen doit etre REFUSE"
    assert any("CHAINE" in f for f in DC.valider(_decl(hors_confrontation=True)))
    assert DC.valider(_decl(hors_confrontation="trop court")), "une raison courte est REFUSEE"
    motif = "il BALAIE scripts/python/** -- aucune enumeration ne borne ce fichier"
    assert DC.valider(_decl(hors_confrontation=motif)) == []
    assert DC.hors_confrontation(_decl(hors_confrontation=motif)) == motif


def test_un_bypass_sur_une_declaration_toujours_est_SANS_OBJET():
    """`toujours: True` n'est DEJA jamais confronte : y ajouter la cle est du copier-coller qui
    a l'air de faire quelque chose. Meme regle que la cle MORTE de `valider_par_entree`."""
    motif = "il BALAIE scripts/python/** -- aucune enumeration ne borne ce fichier"
    fautes = DC.valider(_decl(toujours=True, chemins=("*",), hors_confrontation=motif))
    assert any("SANS OBJET" in f for f in fautes), fautes


def test_une_cle_INVENTEE_reste_refusee_le_contrat_ne_s_etend_pas_par_l_usage():
    fautes = DC.valider(_decl(bypass=True))
    assert any("inconnue" in f for f in fautes), fautes


def test_un_motif_non_ASCII_est_refuse_car_il_est_IMPRIME():
    fautes = DC.valider(_decl(hors_confrontation="parce qu'il balaie l'arbre" + "é" * 30))
    assert any("ASCII" in f for f in fautes), fautes


# =============================================================== [2] LA CASCADE DERIVEE (#531)
def test_la_cascade_est_VIDE_hors_de_l_arbre_des_tests():
    """Un cliquet n'a pas de conftest ; lui en deriver un elargirait son perimetre pour rien."""
    assert DC.chemins_du_harnais("scripts/python/probe_x.py", ROOT) == ()
    assert DC.chemins_du_harnais("frida/hooks/x.ts", ROOT) == ()


def test_la_cascade_derivee_est_NON_VIDE_et_croit_avec_la_PROFONDEUR():
    """ANTI-VACUITE : sans ce cran, une derivation qui rendrait toujours `()` passerait pour
    verte -- et c'est exactement la forme du faux vert que cette famille combat."""
    a = DC.chemins_du_harnais("scripts/python/tests/test_x_offline.py", ROOT)
    b = DC.chemins_du_harnais("scripts/python/tests/engine/test_x_offline.py", ROOT)
    c = DC.chemins_du_harnais("scripts/python/tests/engine/runner/test_x_offline.py", ROOT)
    assert len(a) >= 8, a
    assert set(a) < set(b) < set(c), "la cascade d'un sous-arbre CONTIENT celle de son parent"


def test_la_cascade_derivee_REPRODUIT_le_socle_que_trois_fichiers_recopiaient():
    """LE TEMOIN de #531. Trois declarations portent, mot pour mot, un bloc << SOCLE COMMUN a
    TOUT fichier de test >> -- douze chemins recopies a la main, avec le commentaire qui explique
    qu'aucun test ne les importe. La derivation rend EXACTEMENT ces douze : le travail etait
    juste, il etait seulement fait au mauvais endroit."""
    socle = {
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py", "scripts/python/gameconfig.py",
        "scripts/python/enum_maps.py", "scripts/python/host_inputs.py",
        "scripts/python/rl_collect_batch.py", "scripts/python/stream_events.py",
        "scripts/python/symbols_layout.py", "scripts/python/engine/runner/snapshot.py",
    }
    derive = set(DC.chemins_du_harnais("scripts/python/tests/test_x_offline.py", ROOT))
    assert socle <= derive, sorted(socle - derive)


def test_le_PERIMETRE_EFFECTIF_porte_la_cascade_sans_que_le_declarant_l_ecrive():
    d = _decl(chemins=("scripts/python/probe_x.py",))
    globs = DC.perimetre(d, "scripts/python/tests/engine/test_x_offline.py", ROOT)
    assert DC.couvre(globs, "scripts/python/tests/engine/conftest.py")
    assert DC.couvre(globs, "scripts/python/engine_agreement_stages.py"), \
        "il n'est tire QUE par la cascade des conftest -- c'est le module type de #531"
    # ... et le meme declencheur, porte par un CLIQUET, ne l'attrape pas.
    globs_cliquet = DC.perimetre(d, "scripts/python/probe_y.py", ROOT)
    assert not DC.couvre(globs_cliquet, "scripts/python/engine_agreement_stages.py")


def test_un_import_RELATIF_ne_se_resout_PAS_contre_la_racine():
    """LA MOITIE QU'ON N'ATTENDAIT PAS. Resoudre `from .board import X` comme le nom `board` ne
    fait pas que MANQUER `engine/entities/pathfinding/board.py` -- il FABRIQUE une cible fausse,
    `scripts/python/board.py`, qu'AUCUN module du depot n'importe (mesure du 2026-08-07 :
    0 importateur sur les 4 189 fichiers versionnes). C'est ce faux positif que #531 citait
    comme preuve que << le harnais live tire `board` >>."""
    f = DC.Fermeture(ROOT)
    cibles = f.cibles("scripts/python/engine/entities/pathfinding/pathfinders.py")
    assert "scripts/python/board.py" not in cibles, \
        "un import relatif ne doit JAMAIS resoudre contre `scripts/python/`"
    casc = DC.chemins_du_harnais("scripts/python/tests/engine/test_x_offline.py", ROOT)
    assert "scripts/python/board.py" not in casc


@pytest.mark.parametrize("rel,niveau,attendu", [
    ("scripts/python/engine/runner/snapshot.py", 1, ["engine", "runner"]),
    ("scripts/python/engine/runner/snapshot.py", 2, ["engine"]),
    ("scripts/python/engine/runner/__init__.py", 1, ["engine", "runner"]),
    ("scripts/python/probe_x.py", 1, []),
    ("scripts/python/probe_x.py", 2, None),          # on remonte plus haut que le paquet
    ("frida/hooks/x.py", 1, None),                   # hors de l'arbre importable
])
def test_le_paquet_d_un_import_relatif_est_DERIVE_du_chemin(rel, niveau, attendu):
    assert DC.Fermeture._paquet(rel, niveau) == attendu


# =============================================================== [3] LE CLIQUET
def test_un_bypass_DESARME_la_confrontation_de_CE_fichier_seulement():
    """MUTATION : on ampute une declaration REELLE, on verifie qu'elle rougit, puis on lui pose
    le bypass et on verifie qu'elle ne rougit plus. Sans la premiere moitie, le vert de la
    seconde ne prouverait rien."""
    rel = "scripts/python/tests/test_486_r1_cache_verdict_offline.py"
    vraie = DC.lire(ROOT / rel)
    ampute = dict(vraie)
    ampute["chemins"] = tuple(c for c in vraie["chemins"] if "verdict_cache" not in c)
    assert len(ampute["chemins"]) < len(vraie["chemins"]), "la mutation n'a pas MORDU"

    rouges, _, bypass = G.confronter({rel: ampute})
    assert rouges and not bypass, "l'ampute doit ROUGIR avant qu'on lui pose la cle"

    avec = dict(ampute)
    avec[DC.CLE_HORS_CONFRONTATION] = ("mutation de test : la fermeture ne borne pas ce fichier")
    rouges2, _, bypass2 = G.confronter({rel: avec})
    assert not rouges2, "le bypass doit desarmer la confrontation"
    assert len(bypass2) == 1 and bypass2[0][0] == rel
    assert bypass2[0][2], "le bypass doit COMPTER ce qu'il masque, pas seulement le taire"


def test_un_bypass_qui_ne_masque_RIEN_est_vu_comme_MORT():
    """Le cran anti-imitation. Une declaration deja juste qui pose la cle << au cas ou >> doit
    etre refusee -- sinon les 29 de la cascade l'auraient copiee et rien n'aurait change."""
    rel = "scripts/python/tests/test_486_r1_cache_verdict_offline.py"
    vraie = dict(DC.lire(ROOT / rel))
    vraie[DC.CLE_HORS_CONFRONTATION] = "pose au cas ou, alors que la confrontation passe deja"
    _, _, bypass = G.confronter({rel: vraie})
    assert len(bypass) == 1
    assert bypass[0][2] == [], "cette declaration ne masque RIEN : le cliquet doit le voir"


def test_le_probe_ROUGIT_sur_un_bypass_MORT(tmp_path, monkeypatch, capsys):
    # La declaration couvre DEJA tout ce que le fichier importe : le bypass ne masque rien.
    _monte_arbre(tmp_path, monkeypatch, motif="pose au cas ou, alors que rien ne le justifie",
                 chemins=("scripts/python/cible.py",), atteste=True)
    assert G.main([]) == 1
    assert "NE MASQUE RIEN" in capsys.readouterr().out


def test_le_probe_ROUGIT_sur_un_bypass_NON_ATTESTE(tmp_path, monkeypatch, capsys):
    _monte_arbre(tmp_path, monkeypatch, motif="il BALAIE l'arbre, aucune enumeration ne le borne",
                 chemins=(), atteste=False)
    assert G.main([]) == 1
    assert "SANS ETRE ATTESTE" in capsys.readouterr().out


def test_le_probe_est_VERT_sur_un_bypass_UTILE_et_ATTESTE(tmp_path, monkeypatch, capsys):
    _monte_arbre(tmp_path, monkeypatch, motif="il BALAIE l'arbre, aucune enumeration ne le borne",
                 chemins=(), atteste=True)
    assert G.main([]) == 0
    sortie = capsys.readouterr().out
    assert "HORS CONFRONTATION" in sortie
    assert "il BALAIE l'arbre" in sortie, "le MOTIF doit etre imprime, pas seulement compte"


def _monte_arbre(tmp_path, monkeypatch, motif, chemins, atteste):
    """Un depot minuscule : un module, un test qui l'importe, et une declaration qui l'ignore."""
    py = tmp_path / "scripts" / "python"
    (py / "tests").mkdir(parents=True)
    (py / "cible.py").write_text("X = 1\n", encoding="utf-8")
    decl = {"chemins": chemins, "build": False, "toujours": False,
            "raison": "r" * (DC.RAISON_MIN + 5), DC.CLE_HORS_CONFRONTATION: motif}
    if not chemins:
        decl["build"] = True          # un perimetre VIDE + toujours False est refuse par la forme
    (py / "tests" / "test_a_offline.py").write_text(
        "DECLENCHEUR = %r\nimport cible\n" % (decl,), encoding="utf-8")
    dette = tmp_path / "scripts" / "ratchets-486r15-dette-declencheurs.txt"
    dette.write_text("# vide\n", encoding="utf-8")
    bypass = tmp_path / "scripts" / "ratchets-486r24-bypass-confrontation.txt"
    bypass.write_text(("# atteste\nscripts/python/tests/test_a_offline.py\n"
                       if atteste else "# vide\n"), encoding="utf-8")
    monkeypatch.setattr(G, "ROOT", tmp_path)
    monkeypatch.setattr(G, "DETTE", dette)
    monkeypatch.setattr(G, "BYPASS", bypass)
    monkeypatch.setattr(G, "EMPREINTE", tmp_path / "absente.json")
    monkeypatch.setattr(G, "fichiers_de_test",
                        lambda: ["scripts/python/tests/test_a_offline.py"])
    monkeypatch.setattr(DC, "RACINE", tmp_path)
    DC._HARNAIS.clear()


# =============================================================== [4] LA POPULATION REELLE
def test_la_population_ATTESTEE_est_exactement_celle_qui_bypasse():
    """Le fichier versionne n'est pas une intention : il doit correspondre au depot, sinon la
    croissance de la population cesserait d'etre visible dans un diff."""
    fichiers = G.fichiers_de_test()
    ok, _ko = G.declarations(fichiers)
    porteurs = {r for r in ok if DC.hors_confrontation(ok[r]) is not None}
    assert G.lire_bypass_atteste() == porteurs, \
        "regenerer : python scripts/python/probe_486r15_declencheurs_tests.py --ecrire-bypass"


def test_chaque_bypass_reel_MASQUE_quelque_chose_et_le_DIT():
    """ANTI-VACUITE sur la population reelle : un fichier atteste dont le bypass ne servirait a
    rien serait un bypass d'imitation -- et le compte imprime serait un chiffre creux."""
    fichiers = G.fichiers_de_test()
    ok, _ko = G.declarations(fichiers)
    _, _, bypass = G.confronter(ok)
    assert bypass, "la population est VIDE : ce test ne prouverait rien (cf. #270-r1-r1-r3)"
    for rel, motif, decouverts in bypass:
        assert len(motif) >= DC.RAISON_MIN, rel
        assert decouverts, "%s : bypass qui ne masque rien" % rel


@pytest.mark.parametrize("rel", [
    "scripts/python/tests/test_464_sibling_script_offline.py",
    "scripts/python/tests/test_457_r8_selection_par_diff_offline.py",
])
def test_les_exemplaires_du_BALAYAGE_ne_declarent_plus_de_glob_universel(rel):
    """Ce que le bypass REMPLACE : ces deux-la portaient `scripts/python/**/*.py` avec un
    commentaire << LARGE A DESSEIN >>. Le glob est parti, la raison est restee -- et elle est
    desormais dans une cle que le cliquet COMPTE."""
    d = DC.lire(ROOT / rel)
    assert DC.hors_confrontation(d), rel
    for g in d.get("chemins") or ():
        assert g != "scripts/python/**/*.py", "%s garde le glob que le bypass remplace" % rel
