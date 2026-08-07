"""#486-r23 -- la VALIDITE du ledger du vert OFFLINE, prouvee dans les DEUX sens.

CE QUE CE FICHIER DOIT EMPECHER, et c'est le piege que `#465` a nomme : rendre le ledger
PERMISSIF. Un ledger offline sert a **SAUTER** un test ; toute entree qu'il declare valable a
tort est un FAUX VERT, silencieux par construction -- le test n'est pas joue, donc rien ne le
signale. C'est l'exact inverse du ledger LIVE (`probe_462`), ou une entree perimee ne fait que
mal RACONTER un rouge qui reste bloquant.

Le test central est `test_AUCUN_chemin_ne_rend_le_ledger_permissif` : il balaie le produit
CARTESIEN (verdict x ancres ECRITES x ancre EFFECTIVE x blob de l'entree x blob courant x impact,
soit 576 combinaisons) et exige que `raison_de_rejeu` ne rende `None` que sur UNE seule FORME --
le vert non impacte, au blob courant, avec une ancre lisible.

⚠ IL ASSERTIONNE SON PROPRE NON-VIDE. Un balayage cartesien qui porterait sur un ensemble vide
passerait pour VERT sans rien avoir eprouve ; c'est le vice mesure sur `#270-r1-r1-r3`, ou un
test << les ordinaux communs nomment autre chose >> a d'abord rendu un ensemble VIDE.

ASCII only (cp1252).
"""
from __future__ import annotations

import itertools
import json
import subprocess

import pytest

import ledger_vert_offline as L

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#:
#: ETROIT, et c'est MESURE, pas espere : ce fichier n'importe QUE `ledger_vert_offline` (jamais
#: `probe_457`, dont il n'eprouve pas le cablage), et il fabrique ses depots git dans `tmp_path`.
#:
#: ⚠ La premiere redaction declarait 6 chemins et `probe_486r15_declencheurs_tests` l'a rendue
#: ROUGE : **8 chemins de plus** sont lus, tous par la CASCADE DES CONFTEST, qu'aucune lecture du
#: source de ce fichier ne montre. La liste ci-dessous est celle du cliquet, pas une estimation.
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test : la cascade des deux `conftest.py` et sa
        # FERMETURE. Aucun test ne les IMPORTE (semantique pytest), et ils portent le
        # `green_skip_guard` de #455 plus des fixtures `autouse`.
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
    "raison": "Le seul module sous test est `ledger_vert_offline`. Les ledgers et les depots git "
              "sont FABRIQUES dans tmp_path -- aucun artefact versionne n'entre dans le verdict.",
}

_BLOB_A = "a" * 40
_BLOB_B = "b" * 40


_ANCRE = "c" * 40
_BASE = "e" * 40


def _entree(verdict=L.VERT, blob=_BLOB_A, depuis=_ANCRE, base=_BASE, **kw):
    e = {"_at": 1, "_blob": blob, "_commit": "d" * 40, "_depuis": depuis, "_base": base,
         "verdict": verdict, "sec": 1.0, "messages": [],
         "passed": 3, "failed": 0, "error": 0, "skipped": 0, "xfailed": 0}
    e.update(kw)
    return e


# ------------------------------------------------------- LE BALAYAGE CARTESIEN (coeur du fichier)

def test_AUCUN_chemin_ne_rend_le_ledger_permissif():
    """`raison_de_rejeu` ne rend `None` que sur UNE combinaison, et on les essaie TOUTES."""
    verdicts = [L.VERT, L.ROUGE, L.SETUP, L.VIDE, "?", None]
    ancres_ecrites = [(_ANCRE, _BASE), (None, _BASE), (None, None), ("", "")]
    ancres_effectives = [_ANCRE, None]
    blobs_entree = [_BLOB_A, None]
    blobs_courants = [_BLOB_A, _BLOB_B, None]
    impacts = [True, False]

    combinaisons = list(itertools.product(verdicts, ancres_ecrites, ancres_effectives,
                                          blobs_entree, blobs_courants, impacts))
    # ANTI-VACUITE : un cartesien vide passerait pour vert sans rien eprouver.
    assert len(combinaisons) == 6 * 4 * 2 * 2 * 3 * 2 == 576, len(combinaisons)

    passants = []
    for verdict, (depuis, base), ancre, blob_e, blob_c, impacte in combinaisons:
        entree = None if verdict is None else _entree(verdict=verdict, blob=blob_e,
                                                      depuis=depuis, base=base)
        motif = L.raison_de_rejeu("tests/x_offline.py", entree, blob_c, ancre, impacte)
        if motif is None:
            passants.append((verdict, depuis, base, ancre, blob_e, blob_c, impacte))
        else:
            assert isinstance(motif, str) and motif, \
                "un rejeu doit DIRE pourquoi : %r" % (motif,)

    # Une seule FORME passe : VERT, blob courant, une ancre EFFECTIVE, non impacte. Elle se
    # decline sur les 2 facons d'avoir une ancre ECRITE non vide -- `ancre_effective` a deja
    # tranche laquelle des deux sert, ce n'est plus la question de `raison_de_rejeu`.
    attendu = {(L.VERT, _ANCRE, _BASE, _ANCRE, _BLOB_A, _BLOB_A, False),
               (L.VERT, None, _BASE, _ANCRE, _BLOB_A, _BLOB_A, False)}
    assert set(passants) == attendu, (
        "le ledger laisse passer %d combinaison(s) au lieu de %d : %s"
        % (len(passants), len(attendu), [p for p in passants if p not in attendu]))


@pytest.mark.parametrize("verdict", [L.ROUGE, L.SETUP, L.VIDE, "?"])
def test_un_NON_VERT_ne_passe_JAMAIS(verdict):
    """Meme au blob courant, meme sur une ancre connue, meme non impacte."""
    motif = L.raison_de_rejeu("tests/x.py", _entree(verdict=verdict), _BLOB_A, _ANCRE, False)
    assert motif is not None and verdict in motif


def test_une_edition_NON_COMMITEE_invalide_le_vert():
    """Le cran que `git diff <ref> HEAD` ne peut PAS voir -- et c'est pour lui que la cle
    porte le blob du WORKTREE, jamais celui de l'index."""
    motif = L.raison_de_rejeu("tests/x.py", _entree(), _BLOB_B, _ANCRE, False)
    assert motif is not None and "CHANGE" in motif


def test_un_blob_NON_MESURABLE_rejoue_au_lieu_de_passer():
    """`None` veut dire << git n'a pas su hacher >>. C'est une panne de MESURE, pas un fait :
    la rabattre sur << blob egal >> serait exactement le faux vert."""
    motif = L.raison_de_rejeu("tests/x.py", _entree(), None, _ANCRE, False)
    assert motif is not None and "PAS MESURE" in motif


def test_aucune_ancre_LISIBLE_rejoue_le_defaut_de_486r15():
    """Une attestation dont les DEUX ancres sont mortes ne porte sur aucun arbre d'ici."""
    motif = L.raison_de_rejeu("tests/x.py", _entree(), _BLOB_A, None, False)
    assert motif is not None and "INCONNU" in motif


def test_une_dependance_CHANGEE_rejoue():
    """La composition avec l'empreinte : c'est `impacted_files` qui repond, pas le ledger."""
    motif = L.raison_de_rejeu("tests/x.py", _entree(), _BLOB_A, _ANCRE, True)
    assert motif is not None and "dependance" in motif


# ------------------------------------------------------------------------------- DEUX ANCRES

def test_l_ancre_PRECISE_prime_sur_la_SURVIVANTE():
    """`_depuis` (HEAD) fait gagner entre deux passes d'une meme tranche ; `_base` ne fait que
    reproduire la selection de `--since`. Mesure du 2026-08-07 : avec la base SEULE,
    `--depuis-ledger` rend EXACTEMENT 33 fichiers / 494 s, comme `--since <base>`."""
    assert L.ancre_effective(_entree(), {_ANCRE: True, _BASE: True}) == _ANCRE


def test_l_ancre_MORTE_se_replie_sur_la_BASE_au_lieu_de_tout_perdre():
    """C'est ce qui empeche le ledger de naitre MORT a chaque squash-merge (defaut #486-r15)."""
    assert L.ancre_effective(_entree(), {_ANCRE: False, _BASE: True}) == _BASE


def test_deux_ancres_MORTES_ne_rendent_AUCUNE_ancre():
    assert L.ancre_effective(_entree(), {_ANCRE: False, _BASE: False}) is None
    assert L.ancre_effective(None, {}) is None


def test_se_replier_sur_la_base_SUR_selectionne_et_ne_peut_pas_faire_sauter_un_test():
    """La degradation est SURE : une ancre plus ancienne allonge le diff, donc plus de fichiers
    sont juges impactes. On perd du mur, jamais de la surete."""
    e = _entree()
    # Avec l'ancre precise ET non impacte : le vert tient.
    assert L.raison_de_rejeu("tests/x.py", e, _BLOB_A, _ANCRE, False) is None
    # Repli sur la base : le diff est plus long, donc `impacte` devient vrai -> rejeu.
    assert L.raison_de_rejeu("tests/x.py", e, _BLOB_A, _BASE, True) is not None


# ------------------------------------------------------------------ VERDICT DERIVE DU BILAN (#455)

def test_un_fichier_INTEGRALEMENT_SKIPPE_n_est_PAS_VERT():
    """Le garde #455, porte par le BILAN VENTILE. `rc 0` + 0 assertion = un vert qui ment.

    C'est la raison pour laquelle le ledger ne stocke pas qu'un champ `verdict` : un verdict
    seul ne saurait pas distinguer ce cas d'un vrai vert."""
    assert L.verdict_de_bilan({"passed": 0, "skipped": 8}) == L.VIDE
    # ... et il ne passe donc pas la validite, meme cle parfaite :
    e = _entree(verdict=L.verdict_de_bilan({"passed": 0, "skipped": 8}),
                passed=0, skipped=8)
    assert L.raison_de_rejeu("tests/x.py", e, _BLOB_A, _ANCRE, False) is not None


def test_une_ERREUR_de_setup_n_est_pas_un_ROUGE_d_assertion():
    """Confondre les deux fait accuser le depot pour une panne de montage."""
    assert L.verdict_de_bilan({"passed": 2, "error": 1}) == L.SETUP
    assert L.verdict_de_bilan({"passed": 2, "failed": 1}) == L.ROUGE
    assert L.verdict_de_bilan({"passed": 2}) == L.VERT


def test_l_ordre_des_criteres_place_ERROR_avant_FAILED():
    """Un fichier qui a les deux est SETUP : la panne de montage explique l'echec."""
    assert L.verdict_de_bilan({"passed": 1, "failed": 3, "error": 1}) == L.SETUP


# ------------------------------------------------------------------------ LECTURE TOLERANTE

def test_un_ledger_ABSENT_rend_vide_ET_LE_DIT(tmp_path):
    entrees, anomalies = L.lire(tmp_path)
    assert entrees == {} and anomalies and "ABSENT" in anomalies[0]


def test_un_ledger_ILLISIBLE_rend_vide_ET_LE_DIT(tmp_path):
    p = L.chemin(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ pas du json", encoding="utf-8")
    entrees, anomalies = L.lire(tmp_path)
    assert entrees == {} and anomalies and "ILLISIBLE" in anomalies[0]


def test_un_FORMAT_INCONNU_ne_se_devine_pas(tmp_path):
    p = L.chemin(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"_format": L.FORMAT + 99, "fichiers": {"a": {}}}),
                 encoding="utf-8")
    entrees, anomalies = L.lire(tmp_path)
    assert entrees == {}, "un format inconnu lu avec nos regles produirait un faux vert"
    assert anomalies and "format" in anomalies[0]


def test_une_entree_ABIMEE_est_ecartee_SEULE(tmp_path):
    """La tolerance a la LIGNE : une fusion git abimee ne doit pas faire tomber les autres."""
    p = L.chemin(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"_format": L.FORMAT, "fichiers": {
        "tests/bon.py": _entree(), "tests/abime.py": "pas un dict"}}), encoding="utf-8")
    entrees, anomalies = L.lire(tmp_path)
    assert set(entrees) == {"tests/bon.py"}
    assert any("ECARTEE" in a for a in anomalies)


# --------------------------------------------------------------------------------- ECRITURE

def test_ecrire_puis_lire_conserve_les_entrees(tmp_path):
    entrees = {"tests/a.py": _entree(), "tests/b.py": _entree(verdict=L.ROUGE, failed=1)}
    L.ecrire(tmp_path, entrees)
    relues, anomalies = L.lire(tmp_path)
    assert relues == entrees and not anomalies


def test_UNE_LIGNE_PAR_ENTREE_et_c_est_ce_qui_borne_les_conflits(tmp_path):
    """Un JSON indente etalerait chaque entree sur ~12 lignes : deux agents attestant deux
    fichiers VOISINS produiraient des hunks qui se chevauchent, donc un conflit sur des faits
    qui ne se contredisent pas."""
    entrees = {"tests/a.py": _entree(), "tests/b.py": _entree(), "tests/c.py": _entree()}
    p = L.ecrire(tmp_path, entrees)
    lignes = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    portant_une_cle = [l for l in lignes if l.strip().startswith('"tests/')]
    assert len(portant_une_cle) == 3, lignes
    # Enveloppe = 6 lignes (`{`, `_format`, `_ecrit_le`, `"fichiers": {`, ` }`, `}`).
    assert len(lignes) == 3 + 6, "enveloppe + une ligne par entree, rien de plus : %s" % lignes


def test_la_fusion_CONSERVE_ce_que_la_passe_n_a_pas_joue(tmp_path):
    """Une passe de 10 fichiers ne doit pas detruire les 226 autres attestations."""
    anciennes = {"tests/a.py": _entree(), "tests/b.py": _entree()}
    neuves = {"tests/a.py": _entree(verdict=L.ROUGE, failed=1)}
    fusion = L.fusionner(anciennes, neuves, perimetre=["tests/a.py", "tests/b.py"])
    assert fusion["tests/a.py"]["verdict"] == L.ROUGE
    assert fusion["tests/b.py"]["verdict"] == L.VERT


def test_la_fusion_RETIRE_les_fantomes_hors_perimetre(tmp_path):
    """Un test supprime -- ou RENOMME en `_live.py` -- ne doit pas laisser une attestation que
    plus rien ne viendra jamais rafraichir."""
    fusion = L.fusionner({"tests/parti.py": _entree(), "tests/reste.py": _entree()}, {},
                         perimetre=["tests/reste.py"])
    assert set(fusion) == {"tests/reste.py"}


# ------------------------------------------------------------------------------- CONFLITS

_CONFLIT = '''{
 "_format": 1,
 "_ecrit_le": 1,
 "fichiers": {
  "tests/commun.py": %(a)s,
<<<<<<< HEAD
  "tests/mien.py": %(a)s,
  "tests/dispute.py": %(a)s,
=======
  "tests/tien.py": %(b)s,
  "tests/dispute.py": %(b)s,
>>>>>>> autre
  "tests/apres.py": %(a)s
 }
}
''' % {"a": json.dumps(_entree(), sort_keys=True),
       "b": json.dumps(_entree(blob=_BLOB_B), sort_keys=True)}


def test_une_entree_EN_CONFLIT_est_ABANDONNEE_pas_arbitree():
    """Deux agents qui attestent le meme test l'ont fait sur des arbres DIFFERENTS : ni l'une ni
    l'autre attestation ne porte sur l'arbre resultant. Choisir serait arbitraire ET faux."""
    retenues, abandonnees = L.resoudre_conflit(_CONFLIT)
    assert "tests/dispute.py" in abandonnees
    assert "tests/dispute.py" not in retenues


def test_la_resolution_CONSERVE_ce_qui_est_HORS_conflit():
    retenues, _ = L.resoudre_conflit(_CONFLIT)
    assert set(retenues) >= {"tests/commun.py", "tests/apres.py"}


def test_la_resolution_ne_peut_produire_qu_un_MUR_jamais_un_FAUX_VERT():
    """La propriete qui distingue ce ledger d'un doc genere : toute PERTE y est sure.

    On abandonne meme les cles qui n'apparaissent que d'un cote du hunk (git ne dit pas quelles
    lignes se contredisent). Sur-abandonner ne coute que du rejeu ; sous-abandonner ferait
    survivre une entree que personne n'a ecrite telle quelle."""
    retenues, abandonnees = L.resoudre_conflit(_CONFLIT)
    assert {"tests/mien.py", "tests/tien.py"} <= set(abandonnees)
    for cle in abandonnees:
        assert cle not in retenues
        # ... et une cle absente est lue << jamais joue >>, donc elle REJOUE :
        assert L.raison_de_rejeu(cle, retenues.get(cle), _BLOB_A, _ANCRE, False) is not None


def test_un_fichier_SANS_conflit_traverse_la_resolution_intact():
    """ANTI-VACUITE de la resolution : elle ne doit pas << reussir >> en vidant tout."""
    propre = '''{
 "_format": 1,
 "_ecrit_le": 1,
 "fichiers": {
  "tests/a.py": %s
 }
}
''' % json.dumps(_entree(), sort_keys=True)
    retenues, abandonnees = L.resoudre_conflit(propre)
    assert abandonnees == [] and set(retenues) == {"tests/a.py"}


# ------------------------------------------------------------- BLOB DU WORKTREE (depot jetable)

def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


@pytest.fixture()
def depot(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "x@y.z")
    _git(tmp_path, "config", "user.name", "x")
    d = tmp_path / "scripts" / "python" / "tests"
    d.mkdir(parents=True)
    (d / "t_offline.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_blobs_courants_voit_une_edition_NON_COMMITEE(depot):
    """LE cran que l'index ne donne pas : `git ls-files -s` lirait l'INDEX et resterait aveugle."""
    rel = "tests/t_offline.py"
    avant = L.blobs_courants(depot, [rel])[rel]
    assert avant, "temoin vide : le blob initial doit etre mesurable"
    (depot / "scripts" / "python" / rel).write_text(
        "def test_x():\n    assert False\n", encoding="utf-8")
    apres = L.blobs_courants(depot, [rel])[rel]
    assert apres and apres != avant, "une edition non commitee doit changer le blob"
    assert L.raison_de_rejeu(rel, _entree(blob=avant), apres, _ANCRE, False) is not None


def test_un_fichier_ABSENT_rend_un_blob_NON_MESURE_pas_un_faux(depot):
    blobs = L.blobs_courants(depot, ["tests/t_offline.py", "tests/jamais_ecrit.py"])
    assert blobs["tests/jamais_ecrit.py"] is None
    # le lot entier retombe a None : c'est le sens SUR (rejeu), jamais une valeur devinee.
    assert L.raison_de_rejeu("tests/jamais_ecrit.py", _entree(),
                             blobs["tests/jamais_ecrit.py"], _ANCRE, False) is not None


def test_le_CLI_resoudre_reecrit_par_le_FOYER_d_ecriture(tmp_path, capsys):
    """Le point d'entree existe, et il ne bricole pas le texte : il passe par `ecrire`, donc le
    fichier resolu est a l'octet pres celui qu'une passe normale aurait produit."""
    p = L.chemin(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_CONFLIT, encoding="utf-8")
    assert L.main(["--resoudre", "--racine", str(tmp_path)]) == 0
    relues, anomalies = L.lire(tmp_path)
    assert not anomalies, anomalies
    assert "tests/dispute.py" not in relues
    assert {"tests/commun.py", "tests/apres.py"} <= set(relues)
    # ... et le fichier resolu est RELISIBLE (pas de virgule orpheline, pas de marqueur reste).
    assert "<<<<<<<" not in p.read_text(encoding="utf-8")


def test_le_CLI_resoudre_ne_touche_PAS_un_fichier_sans_conflit(tmp_path):
    """Une resolution qui reecrirait un fichier sain ferait bouger `_ecrit_le` pour rien, donc
    fabriquerait le conflit qu'elle est censee resoudre."""
    entrees = {"tests/a.py": _entree()}
    L.ecrire(tmp_path, entrees)
    avant = L.chemin(tmp_path).read_text(encoding="utf-8")
    assert L.main(["--resoudre", "--racine", str(tmp_path)]) == 0
    assert L.chemin(tmp_path).read_text(encoding="utf-8") == avant


def test_commits_connus_distingue_un_sha_MORT(depot):
    tete = _git(depot, "rev-parse", "HEAD").stdout.strip()
    connus = L.commits_connus(depot, [tete, "0" * 40])
    assert connus[tete] is True
    assert connus["0" * 40] is False


def test_la_base_de_fraicheur_se_replie_sur_HEAD_et_LE_DIT(depot):
    """Sans `origin/master`, l'attestation ne survivra pas a un squash-merge -- ce qui coute du
    mur au prochain agent, jamais un faux vert. Le repli doit donc etre DIT."""
    sha, comment = L.base_de_fraicheur(depot)
    assert sha == _git(depot, "rev-parse", "HEAD").stdout.strip()
    assert "HEAD" in comment and "squash" in comment
