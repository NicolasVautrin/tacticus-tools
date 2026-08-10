"""#547-r7 -- l'ecriture MULTI-SHARD du ledger, et le faux vert qu'elle ne doit pas ouvrir.

CE QUE CE FICHIER GARDE. `_ecrire_ledger` REFUSAIT toute ecriture des que `n_shards > 1`, et la
raison ecrite etait juste : 8 processus en read-modify-write sur un meme JSON VERSIONNE perdent
des ecritures, et chacun ne connait que sa part. Ce que ce refus protegeait, ce n'est donc pas
<< l'ecriture multi-shard >>, c'est **l'ecriture CONCURRENTE du fichier versionne**.

La levee garde la propriete au lieu de la contourner : chaque shard depose une PART -- un fichier
par `(jeton, n, k)`, donc DISJOINT -- et un seul processus fusionne. Deux crans sont donc a tenir,
et ce fichier les tient tous les deux :

  1. LA DISJONCTION : deux shards n'ecrivent jamais le meme fichier. C'est ce qui remplace le
     verrou, et c'est ce qui rend le mecanisme sur SANS rien a liberer si un shard meurt.
  2. LE REFUS D'UNE PART ETRANGERE : une part oubliee d'un run precedent porte des verts gagnes
     sur un AUTRE arbre. Les fusionner serait le FAUX VERT exact que `#465` interdit -- et il
     serait silencieux, puisqu'un vert au ledger SAUTE le test.

Le test central est `test_AUCUNE_part_etrangere_n_est_retenue` : produit CARTESIEN des trois
criteres, avec l'exigence que `parts_retenues` ne garde QU'UNE forme -- meme jeton, meme HEAD,
meme perimetre. Il ASSERTIONNE SON PROPRE NON-VIDE : un cartesien vide passerait pour vert sans
rien avoir eprouve.

Ce fichier n'eprouve PAS le cablage de `probe_457` (mode `--jobs`, consolidation de bout en bout) :
cela demande de vrais sous-processus pytest sur un depot jetable, donc du MUR -- c'est la mesure
de `probe_547r7_ledger_multi_shard.py`, qui confronte les deux ledgers entree par entree.

ASCII only (cp1252).
"""
from __future__ import annotations

import itertools
import json

import ledger_vert_offline as L

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#:
#: Le socle commun (cascade des conftest et sa FERMETURE) est celui que
#: `probe_486r15_declencheurs_tests` MESURE -- il n'est deduit d'aucune lecture du source, aucun
#: test n'important les conftest. Le seul chemin PROPRE a ce fichier est le module sous test.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/pytest.ini",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER :
        "scripts/python/ledger_vert_offline.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Le seul module sous test est `ledger_vert_offline` (parts, refus, consolidation). "
              "Les parts et les ledgers sont FABRIQUES dans tmp_path -- aucun artefact versionne "
              "n'entre dans le verdict, et aucun sous-processus n'est lance.",
}

_JETON = "run-courant"
_HEAD = "a" * 40
_SHA = "b" * 40


def _entree(verdict=L.VERT, passed=3, failed=0):
    return {"_at": 1, "_blob": "c" * 40, "_commit": _HEAD, "_depuis": _HEAD, "_base": _HEAD,
            "verdict": verdict, "sec": 1.0, "messages": [],
            "passed": passed, "failed": failed, "error": 0, "skipped": 0, "xfailed": 0}


# ------------------------------------------------------ CRAN 1 : LA DISJONCTION DES ECRITURES

def test_huit_shards_ecrivent_huit_fichiers_DISJOINTS(tmp_path):
    """La propriete qui REMPLACE le verrou : aucun shard n'ecrit le fichier d'un autre.

    C'est exactement ce que le refus historique protegeait ; on le verifie, on ne le suppose pas.
    """
    for k in range(8):
        L.ecrire_part(tmp_path, _JETON, _HEAD, _SHA, k, 8,
                      {"tests/test_%d_offline.py" % k: _entree()}, 0)
    fichiers = sorted(p.name for p in L.chemin_parts(tmp_path).glob("part-*.json"))
    assert len(fichiers) == 8, fichiers
    assert len(set(fichiers)) == 8, "deux shards ont vise le MEME fichier : la course revient"

    parts, anomalies = L.lire_parts(tmp_path)
    assert not anomalies, anomalies
    assert len(parts) == 8
    # AUCUNE entree perdue : c'est le mode de defaillance du read-modify-write concurrent.
    cles = set()
    for p in parts:
        cles |= set(p["fichiers"])
    assert cles == {"tests/test_%d_offline.py" % k for k in range(8)}, sorted(cles)


def test_une_part_VIDE_est_ecrite_et_se_distingue_d_une_part_ABSENTE(tmp_path):
    """Tri-etat entre processus : << joue, aucun report >> n'est pas << jamais rendu la main >>."""
    perimetre = ["tests/x_offline.py"]
    L.ecrire_part(tmp_path, _JETON, _HEAD, L.sha_perimetre(perimetre), 0, 2, {}, 0)
    parts, _ = L.lire_parts(tmp_path)
    assert [p["_k"] for p in parts] == [0]
    assert parts[0]["fichiers"] == {}

    cr = L.consolider(tmp_path, _JETON, _HEAD, perimetre)
    # Le shard 1 n'a rien depose : la consolidation le NOMME, elle ne l'invente pas.
    assert cr["gardees"] and cr["manquants"] == [1], (cr["gardees"], cr["manquants"])
    assert cr["neuves"] == {}


# --------------------------------------- CRAN 2 : AUCUNE PART ETRANGERE N'ENTRE (contre-epreuve)

def test_AUCUNE_part_etrangere_n_est_retenue(tmp_path):
    """Produit CARTESIEN des trois criteres : UNE seule forme est retenue, et on les essaie toutes.

    Contre-epreuve de permissivite, transposee de `test_486r23_ledger_vert_offline`. Le sens
    dangereux est UNIQUE : retenir une part qui ne porte pas sur cet arbre.
    """
    jetons = [_JETON, "run-etranger", None, ""]
    heads = [_HEAD, "9" * 40, None]
    shas = [_SHA, "8" * 40, None]

    combinaisons = list(itertools.product(jetons, heads, shas))
    # ANTI-VACUITE : un cartesien vide passerait pour vert sans rien eprouver.
    assert len(combinaisons) == 4 * 3 * 3 == 36, len(combinaisons)

    retenues_attendues = 0
    for jeton, head, sha in combinaisons:
        part = {"_format": L.FORMAT_PART, "_jeton": jeton, "_head": head,
                "_perimetre_sha": sha, "_k": 0, "_n": 1, "_rc": 0,
                "_chemin": str(tmp_path / "part-x.json"), "fichiers": {}}
        gardees, ecartees = L.parts_retenues([part], _JETON, _HEAD, _SHA)
        conforme = (jeton == _JETON and head == _HEAD and sha == _SHA)
        if conforme:
            retenues_attendues += 1
            assert gardees == [part], (jeton, head, sha)
            assert ecartees == []
        else:
            assert gardees == [], ("part etrangere RETENUE", jeton, head, sha)
            assert len(ecartees) == 1
            # Une part ecartee DIT pourquoi : sans la raison, un manque se lit comme une absence.
            assert ecartees[0][1], "part ecartee SANS raison"
    assert retenues_attendues == 1, retenues_attendues


def test_une_part_d_un_AUTRE_run_n_atteint_pas_le_ledger(tmp_path):
    """Bout en bout sur `consolider` : la part menteuse ne laisse AUCUNE trace dans la fusion."""
    perimetre = ["tests/test_rouge_offline.py"]
    L.ecrire_part(tmp_path, "run-oublie", _HEAD, L.sha_perimetre(perimetre), 0, 1,
                  {"tests/test_rouge_offline.py": _entree(verdict=L.VERT)}, 0)
    cr = L.consolider(tmp_path, _JETON, _HEAD, perimetre)
    assert cr["gardees"] == []
    assert cr["neuves"] == {}
    assert cr["fusion"] == {}, "un vert d'un AUTRE run est entre dans la fusion"
    assert len(cr["ecartees"]) == 1 and "AUTRE run" in cr["ecartees"][0][1]


def test_purger_parts_empeche_une_part_d_etre_consommee_deux_fois(tmp_path):
    perimetre = ["tests/a_offline.py"]
    L.ecrire_part(tmp_path, _JETON, _HEAD, L.sha_perimetre(perimetre), 0, 1,
                  {"tests/a_offline.py": _entree()}, 0)
    cr = L.consolider(tmp_path, _JETON, _HEAD, perimetre)
    assert len(cr["gardees"]) == 1
    assert L.purger_parts(tmp_path, cr["gardees"]) == 1
    apres, _ = L.lire_parts(tmp_path)
    assert apres == []


# ------------------------------------------------------------------ LE SHA DU PERIMETRE

def test_sha_perimetre_depend_du_CONTENU_et_de_l_ORDRE():
    """Il attrape l'arbre qui BOUGE pendant le run -- fichier ajoute, retire, ou reordonne."""
    base = ["tests/a_offline.py", "tests/b_offline.py"]
    assert L.sha_perimetre(base) == L.sha_perimetre(list(base))
    assert L.sha_perimetre(base) != L.sha_perimetre(base + ["tests/c_offline.py"])
    assert L.sha_perimetre(base) != L.sha_perimetre(base[:1])
    assert L.sha_perimetre(base) != L.sha_perimetre(list(reversed(base)))
    # Pas de collision par simple concatenation des noms.
    assert L.sha_perimetre(["ab", "c"]) != L.sha_perimetre(["a", "bc"])


# ------------------------------------------------------------------ FUSION ET RESTRICTION

def test_consolider_RESTREINT_au_perimetre(tmp_path):
    """Une entree hors perimetre ne survit pas -- meme regle que `fusionner`, cf. les FANTOMES."""
    perimetre = ["tests/vivant_offline.py"]
    L.ecrire_part(tmp_path, _JETON, _HEAD, L.sha_perimetre(perimetre), 0, 1,
                  {"tests/vivant_offline.py": _entree(),
                   "tests/supprime_offline.py": _entree()}, 0)
    cr = L.consolider(tmp_path, _JETON, _HEAD, perimetre)
    assert set(cr["fusion"]) == {"tests/vivant_offline.py"}


def test_un_fichier_atteste_par_DEUX_shards_est_ABANDONNE(tmp_path):
    """La partition est censee etre disjointe : deux attestations du meme fichier sont ANORMALES.

    On ne CHOISIT pas -- les deux sont abandonnees, et le fichier rejouera. Meme regle que
    `resoudre_conflit` : toute perte y est SURE, un choix arbitraire ne l'est pas.
    """
    perimetre = ["tests/a_offline.py", "tests/b_offline.py"]
    sha = L.sha_perimetre(perimetre)
    L.ecrire_part(tmp_path, _JETON, _HEAD, sha, 0, 2,
                  {"tests/a_offline.py": _entree(), "tests/b_offline.py": _entree()}, 0)
    L.ecrire_part(tmp_path, _JETON, _HEAD, sha, 1, 2,
                  {"tests/a_offline.py": _entree(verdict=L.ROUGE, passed=0, failed=1)}, 1)
    cr = L.consolider(tmp_path, _JETON, _HEAD, perimetre)
    assert set(cr["neuves"]) == {"tests/b_offline.py"}, sorted(cr["neuves"])
    assert any("PLUSIEURS shards" in a for a in cr["anomalies"]), cr["anomalies"]


def test_consolider_CONSERVE_les_entrees_hors_run(tmp_path):
    """Une passe partielle n'efface pas ce qu'elle n'a pas joue -- c'est ce que `fusionner` tient."""
    perimetre = ["tests/a_offline.py", "tests/b_offline.py"]
    L.ecrire(tmp_path, {"tests/b_offline.py": _entree(verdict=L.VERT)})
    L.ecrire_part(tmp_path, _JETON, _HEAD, L.sha_perimetre(perimetre), 0, 1,
                  {"tests/a_offline.py": _entree()}, 0)
    cr = L.consolider(tmp_path, _JETON, _HEAD, perimetre)
    assert set(cr["fusion"]) == {"tests/a_offline.py", "tests/b_offline.py"}


# ------------------------------------------------------------------ TOLERANCE A LA LECTURE

def test_une_part_ILLISIBLE_est_ecartee_SEULE_et_le_DIT(tmp_path):
    """Meme tolerance que `lire` : une part abimee coute du MUR, jamais un faux vert."""
    perimetre = ["tests/a_offline.py"]
    L.ecrire_part(tmp_path, _JETON, _HEAD, L.sha_perimetre(perimetre), 0, 2,
                  {"tests/a_offline.py": _entree()}, 0)
    (L.chemin_parts(tmp_path) / "part-abimee-01sur02.json").write_text("{ pas du json",
                                                                      encoding="utf-8")
    parts, anomalies = L.lire_parts(tmp_path)
    assert len(parts) == 1, "la part saine a ete emportee avec l'abimee"
    assert any("ILLISIBLE" in a for a in anomalies), anomalies


def test_une_part_d_un_AUTRE_FORMAT_est_ecartee_et_le_DIT(tmp_path):
    d = L.chemin_parts(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / "part-futur-00sur01.json").write_text(
        json.dumps({"_format": L.FORMAT_PART + 1, "fichiers": {}}), encoding="utf-8")
    parts, anomalies = L.lire_parts(tmp_path)
    assert parts == []
    assert any("format" in a for a in anomalies), anomalies


def test_lire_parts_sur_repertoire_ABSENT_ne_leve_pas(tmp_path):
    """Aucune part n'est un etat NORMAL (passe mono-shard) -- pas une anomalie."""
    parts, anomalies = L.lire_parts(tmp_path / "inexistant")
    assert parts == [] and anomalies == []


# ------------------------------------------------------------------ LE JETON

def test_jeton_courant_LIT_l_environnement_et_ne_FABRIQUE_rien(monkeypatch):
    """Un jeton fabrique par le shard ne servirait a rien : chacun en aurait un different."""
    monkeypatch.delenv(L.VAR_JETON, raising=False)
    assert L.jeton_courant() is None
    monkeypatch.setenv(L.VAR_JETON, "   ")
    assert L.jeton_courant() is None, "un jeton vide doit se lire comme ABSENT"
    monkeypatch.setenv(L.VAR_JETON, "abc123")
    assert L.jeton_courant() == "abc123"


def test_deux_jetons_neufs_different():
    assert L.nouveau_jeton() != L.nouveau_jeton()
