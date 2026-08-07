"""#465 -- la VALIDITE d'un verdict du ledger `probe_462`, prouvee OFFLINE dans les DEUX sens.

Le defaut repare : la cle du ledger est le BLOB du fichier de test. Elle repond a << ce CONTENU
a-t-il ete mesure ? >>, jamais a << l'a-t-il ete sur CET arbre ? >>. Un verdict NON-VERT depend
pourtant du depot ENTIER. Mesure du 2026-08-04 : les trois ROUGES du ledger etaient PERIMES (2
passed, 5 passed, et une cause fermee depuis par #462-r4c) et ont failli faire renvoyer trois PR.

CE QUE CE FICHIER DOIT EMPECHER, et c'est le piege annonce : rendre le ledger PERMISSIF. La
reparation ne doit EFFACER aucun rouge -- elle doit distinguer << mesure et rouge >> de << mesure
sur un autre arbre >>. Le test central est donc `test_AUCUN_chemin_ne_rend_la_gate_permissive`,
qui balaie le produit CARTESIEN verdict x position-du-commit x blob et exige que la gate ne passe
QUE sur (VERT, blob courant) -- pour toute position de commit, y compris celles que la reparation
introduit.

ASCII only (cp1252).
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict
#: (#486-r15). Meme contrat que les cliquets de la banque (`declencheur_cliquet.py`).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des deux `conftest.py` et sa
        # fermeture. Aucun test ne les IMPORTE -- c'est de la semantique pytest -- et ils
        # portent le `green_skip_guard` de #455 plus trois fixtures `autouse`, dont le
        # verdict de CHAQUE test depend. Liste EXPLICITE et non `scripts/python/*.py` : le
        # glob large retiendrait ce test a chaque modification d'un probe quelconque.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER :
        "scripts/python/probe_462_live_tests_status.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Le seul probe sous test. Le ledger d'attestations est injecte SYNTHETIQUEMENT par "
              "chaque cas (aucune lecture du ledger versionne), donc seul le code de validite du "
              "ledger peut changer son verdict.",
}

import json
import subprocess
from pathlib import Path

import pytest

import probe_462_live_tests_status as P

#: Ce qui doit changer pour que cette contre-epreuve puisse changer d'avis.
#:
#: ⚠ CE QUE LA MESURE A REFUTE. On la croyait de portee la plus etroite du lot -- << son verdict
#: ne depend que de {la source du cliquet teste, la sienne} >>, puisque son depot est FABRIQUE
#: (`tmp_path_factory`) et que `probe_462.repo_root` y est SUBSTITUE. La lecture du source le
#: laissait croire. La TRACE dit autre chose (audit hook `declencheur_trace`, arme AVANT le
#: premier import, 2026-08-07) : 7 lectures du depot, dont TROIS qu'une declaration
#: << deux fichiers >> ratait --
#:   * `scripts/ratchets-462-live-attestations.json` : le VRAI ledger. Tous les tests ne
#:     substituent pas `repo_root` ; le depot reel entre donc bien dans le verdict.
#:   * `scripts/python/conftest.py` et `scripts/python/green_skip_guard.py` : le harnais pytest
#:     de la RACINE, invisible du source du fichier de test.
#: Les ~75 sous-process `git`, eux, restent hors de portee du hook (`MESURE INCOMPLETE`) : ils
#: ne parlent qu'a l'arbre jetable, mais c'est un fait LU, pas mesure.
#: Cout ISOLE mesure le 2026-08-07 : 73,9 s (25 tests).
DECLENCHEUR = {
    "chemins": ("scripts/python/probe_462_live_tests_status.py",
                "scripts/ratchets-462-live-attestations.json",
                "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
                "scripts/python/green_skip_guard.py", "scripts/python/pytest.ini"),
    "build": False,
    "toujours": False,
    "raison": "Elle eprouve `verdict_effectif` / `_verdict` de `probe_462` sur un depot git "
              "JETABLE, mais tous ses tests ne substituent pas `repo_root` : le VRAI ledger "
              "entre dans son verdict, ainsi que le harnais pytest de la racine.",
}

_CIBLE = "tests/engine/runner/test_x_live.py"

#: Tous les verdicts que `_verdict` peut produire, plus ceux que le ledger peut porter.
_TOUS_VERDICTS = ["VERT", "ROUGE", "SETUP", "VIDE", "NON JOUE", P.A_RECONFRONTER, "?"]


# --------------------------------------------------------------------------- SETUP vs ASSERTION

def test_un_echec_d_ASSERTION_est_ROUGE():
    assert P._verdict({"passed": 3, "failed": 1, "error": 0, "skipped": 0, "xfailed": 0}) == "ROUGE"


def test_un_echec_de_SETUP_SEUL_est_SETUP_pas_ROUGE():
    """Ce que le verdict dit : OU l'echec est survenu (avant toute assertion). Ce qu'il ne dit
    PAS : a QUI il est imputable -- une fixture peut casser parce que le depot a regresse. Le
    probe ne classe pas (#533), il situe.

    Motivation mesuree : `test_fabricator_claw_cap_live.py`, 10 `error` sur un `ImportError` cite
    depuis le worktree d'un agent DISPARU. Un `f=0 e=10` se lit d'un coup d'oeil quand le verdict
    le dit ; noye dans << ROUGE >>, il se lit comme une regression du depot."""
    assert P._verdict({"passed": 0, "failed": 0, "error": 10, "skipped": 0, "xfailed": 0}) == "SETUP"


def test_une_ASSERTION_echouee_PRIME_sur_un_error_du_meme_fichier():
    """Un fichier qui porte les deux a bien vu une assertion echouer : c'est un verdict sur le
    depot, et il ne doit pas etre range en SETUP -- ce qui l'adoucirait a la lecture."""
    assert P._verdict({"passed": 1, "failed": 1, "error": 3, "skipped": 0, "xfailed": 0}) == "ROUGE"


def test_un_SETUP_est_AUSSI_BLOQUANT_qu_un_ROUGE(gate465):
    """La ventilation sert la LECTURE, jamais l'indulgence. Si SETUP passait la gate, #465 aurait
    ouvert le trou qu'il pretend fermer."""
    gate465({"verdict": "SETUP", "_blob": "blobCOURANT", "_commit": P._head()})
    assert P._do_gate("origin/master") == 1


def test_un_SETUP_COMPTE_dans_le_code_de_sortie(capsys):
    s = {"verdict": "SETUP", "passed": 0, "failed": 0, "error": 10, "skipped": 0, "xfailed": 0}
    assert P._print_inventaire({_CIBLE: s}, [_CIBLE]) == 1
    assert "HORS ASSERTION" in capsys.readouterr().out


# --------------------------------------------------------------------------- etat_commit

@pytest.fixture(scope="module")
def _depot_shas(tmp_path_factory):
    """Un VRAI depot git jetable, avec une branche DIVERGENTE. Construit UNE FOIS.

    Monkeypatcher `etat_commit` aurait teste le cablage sans tester la detection ; or c'est la
    detection qui porte tout le verdict de #465. Un depot reel prouve les quatre etats pour de bon.

    `scope="module"` n'est pas cosmetique : ~25 commits, soit ~75 sous-processus git sous Windows.
    En scope fonction, ce fichier depassait DEUX MINUTES ; le depot etant immuable (aucun test
    n'ecrit dedans), le partager est sans risque."""
    racine = tmp_path_factory.mktemp("depot465")

    def g(*a):
        return subprocess.run(["git", "-C", str(racine), *a], capture_output=True, text=True,
                              encoding="utf-8", errors="replace")

    g("init", "-q", "-b", "principale")
    g("config", "user.email", "t@t"), g("config", "user.name", "t")
    shas = {}
    for i in range(P.DISTANCE_MAX_COMMITS + 5):
        (racine / "f.txt").write_text("v%d" % i, encoding="utf-8")
        g("add", "f.txt")
        g("commit", "-q", "-m", "c%d" % i)
        shas["c%d" % i] = g("rev-parse", "HEAD").stdout.strip()
    # La branche d'un AGENT : elle existe, elle n'est PAS dans l'histoire de `principale`.
    g("checkout", "-q", "-b", "agent", shas["c0"])
    (racine / "g.txt").write_text("agent", encoding="utf-8")
    g("add", "g.txt")
    g("commit", "-q", "-m", "travail d agent")
    shas["agent"] = g("rev-parse", "HEAD").stdout.strip()
    g("checkout", "-q", "principale")
    shas["HEAD"] = g("rev-parse", "HEAD").stdout.strip()
    shas["_racine"] = racine
    return shas


@pytest.fixture()
def depot(_depot_shas, monkeypatch):
    """Le depot partage, avec `repo_root` recable pour CE test (le monkeypatch reste par-test)."""
    monkeypatch.setattr(P, "repo_root", lambda: _depot_shas["_racine"])
    return _depot_shas


def test_etat_commit_reconnait_CET_arbre(depot):
    assert P.etat_commit(depot["HEAD"], depot["HEAD"]) == ("HEAD", 0)


def test_etat_commit_mesure_la_DISTANCE_d_un_ancetre(depot):
    dernier = P.DISTANCE_MAX_COMMITS + 4
    assert P.etat_commit(depot["c%d" % (dernier - 3)], depot["HEAD"]) == ("ancetre", 3)


def test_etat_commit_voit_qu_une_branche_d_AGENT_est_HORS_de_l_histoire(depot):
    """Le cas MESURE : 237 des 254 entrees du ledger portent un sha de ce type -- une attestation
    est ecrite AVANT le rebase de l'agent, donc son sha meurt au rebase. C'est l'etat des trois
    rouges geles."""
    etat, _ = P.etat_commit(depot["agent"], depot["HEAD"])
    assert etat == "HORS"


def test_etat_commit_ne_confond_pas_un_sha_INCONNU_avec_un_non_ancetre(depot):
    """Un objet absent (worktree disparu, objets jamais fetches) rend le meme code que
    `--is-ancestor` sur un non-ancetre. Les confondre ferait ecrire << hors de l'histoire >> la ou
    la verite est << ce depot ne connait pas ce commit >>."""
    assert P.etat_commit("0" * 40, depot["HEAD"]) == ("INCONNU", -1)
    assert P.etat_commit("", depot["HEAD"]) == ("INCONNU", -1)


# --------------------------------------------------------------------------- verdict_effectif

def test_un_VERT_ne_PERIME_JAMAIS_quelle_que_soit_la_position(depot):
    """LA direction inverse, et elle est vitale. Perimer les verts invaliderait 234 attestations
    sur 251 (mesure du 2026-08-04) et redonnerait les << non mesure >> silencieux que #462 existe
    pour fermer -- le piege explicitement nomme dans l'enonce de #465."""
    for sha in (depot["HEAD"], depot["c0"], depot["agent"], "0" * 40, ""):
        eff, _ = P.verdict_effectif({"verdict": "VERT", "_commit": sha}, depot["HEAD"])
        assert eff == "VERT", sha


def test_un_ROUGE_mesure_sur_CET_arbre_reste_ROUGE(depot):
    """Sans cette direction, la reparation effacerait les rouges au lieu de les qualifier."""
    eff, pourquoi = P.verdict_effectif({"verdict": "ROUGE", "_commit": depot["HEAD"]},
                                       depot["HEAD"])
    assert eff == "ROUGE"
    assert "CET arbre" in pourquoi


def test_un_ROUGE_PROCHE_reste_ROUGE(depot):
    """La boucle de merge ajoute 2 a 3 commits entre la mesure et sa relecture. Si un rouge frais
    basculait aussitot en `A RECONFRONTER`, le rapport ne saurait plus jamais accuser le depot."""
    dernier = P.DISTANCE_MAX_COMMITS + 4
    eff, _ = P.verdict_effectif({"verdict": "ROUGE", "_commit": depot["c%d" % (dernier - 2)]},
                                depot["HEAD"])
    assert eff == "ROUGE"


def test_un_ROUGE_HORS_HISTOIRE_devient_A_RECONFRONTER(depot):
    eff, pourquoi = P.verdict_effectif({"verdict": "ROUGE", "_commit": depot["agent"]},
                                       depot["HEAD"])
    assert eff == P.A_RECONFRONTER
    assert "HORS de l'histoire" in pourquoi


def test_un_ROUGE_DISTANCE_devient_A_RECONFRONTER(depot):
    """L'autre porte du meme gel : un rouge mesure sur master il y a 200 commits n'est pas un fait
    sur cet arbre. Ne fermer que la porte << hors histoire >> laisserait celle-ci grande ouverte."""
    eff, pourquoi = P.verdict_effectif({"verdict": "ROUGE", "_commit": depot["c0"]}, depot["HEAD"])
    assert eff == P.A_RECONFRONTER
    assert "commits en arriere" in pourquoi


def test_le_seuil_de_DISTANCE_est_en_COMMITS_pas_en_JOURS():
    """Piste ECARTEE par mesure, et la trace doit rester : les trois rouges geles avaient 0,4 JOUR
    d'age. Tout seuil temporel utile les laissait passer. `_at` reste au ledger pour la lecture,
    mais il ne doit JAMAIS redevenir le critere."""
    assert isinstance(P.DISTANCE_MAX_COMMITS, int) and P.DISTANCE_MAX_COMMITS > 0
    ancien = {"verdict": "ROUGE", "_commit": "0" * 40, "_at": 0}
    frais = {"verdict": "ROUGE", "_commit": "0" * 40, "_at": 9_999_999_999}
    assert P.verdict_effectif(ancien, "abc")[0] == P.verdict_effectif(frais, "abc")[0]


# --------------------------------------------------------------------------- la gate

@pytest.fixture()
def gate465(tmp_path, monkeypatch):
    """Cable la gate sur un ledger jetable. tmpdir SYSTEME (#455)."""
    ledger = tmp_path / "attestations.json"
    monkeypatch.setattr(P, "ledger_path", lambda: ledger)
    monkeypatch.setattr(P, "_live_in_diff", lambda ref: ([_CIBLE], "1 fichier (simule)"))
    monkeypatch.setattr(P, "_blobs", lambda rels: {r: "blobCOURANT" for r in rels})

    def ecrire(entree):
        ledger.write_text(json.dumps({"fichiers": {_CIBLE: entree}}), encoding="utf-8")
    return ecrire


def test_AUCUN_chemin_ne_rend_la_gate_permissive(gate465, depot):
    """LE test de #465. Produit CARTESIEN verdict x position-du-commit x blob : la gate ne passe
    QUE sur (VERT, blob courant), pour TOUTE position -- y compris celles que la reparation
    introduit. C'est la preuve que perimer un non-vert ne peut pas desserrer la gate : seul VERT
    la fait passer, et VERT ne traverse aucune branche de peremption.

    Un test cas-par-cas aurait laisse le trou exactement la ou on n'aurait pas pense a regarder."""
    positions = [depot["HEAD"], depot["c0"], depot["agent"], "0" * 40, ""]
    passes, refuses = [], []
    for verdict in _TOUS_VERDICTS:
        for sha in positions:
            for blob in ("blobCOURANT", "blobDAVANT"):
                gate465({"verdict": verdict, "_blob": blob, "_commit": sha})
                (passes if P._do_gate("origin/master") == 0 else refuses).append(
                    (verdict, sha[:8], blob))
    assert all(v == "VERT" and b == "blobCOURANT" for v, _, b in passes), passes
    attendu = len(positions)          # VERT x toutes positions, au bon blob -- et rien d'autre
    assert len(passes) == attendu, passes
    assert len(refuses) == len(_TOUS_VERDICTS) * len(positions) * 2 - attendu


def test_la_gate_DIT_que_l_attestation_a_ete_mesuree_ailleurs(gate465, depot, capsys):
    """Le refus doit changer de RECIT, pas de verdict : << rejoue-le >> et non << c'est casse >>.
    C'est ce recit qui manquait le 2026-08-04, et son absence a failli couter trois PR."""
    gate465({"verdict": "ROUGE", "_blob": "blobCOURANT", "_commit": depot["agent"]})
    assert P._do_gate("origin/master") == 1
    sortie = capsys.readouterr().out
    assert P.A_RECONFRONTER in sortie and "HORS de l'histoire" in sortie


def test_un_ROUGE_reproduit_ICI_est_annonce_comme_tel(gate465, capsys):
    gate465({"verdict": "ROUGE", "_blob": "blobCOURANT", "_commit": P._head()})
    assert P._do_gate("origin/master") == 1
    assert "reproduite sur cet arbre" in capsys.readouterr().out


# --------------------------------------------------------------------------- code de sortie

def test_le_code_de_sortie_reste_le_NOMBRE_de_NON_VERTS(capsys):
    """#465 ne touche PAS au code de sortie -- `SETUP` et `A RECONFRONTER` sont des
    RE-ETIQUETAGES de ce qui comptait deja. Le defaut mesure etait un defaut de LECTURE, pas de
    rc ; ne pas y toucher supprime tout risque de permissivite non prevu.

    Formule invariante : rc == nombre d'entrees dont le verdict n'est pas VERT."""
    entrees = {}
    for i, v in enumerate(_TOUS_VERDICTS):
        entrees["tests/engine/runner/test_%d_live.py" % i] = {
            "verdict": v, "passed": 1 if v == "VERT" else 0, "failed": 1 if v == "ROUGE" else 0,
            "error": 10 if v == "SETUP" else 0, "skipped": 0, "xfailed": 0}
    attendu = sum(1 for e in entrees.values() if e["verdict"] != "VERT")
    assert P._print_inventaire(entrees, list(entrees)) == attendu
    capsys.readouterr()


# --------------------------------------------------------------------------- --stale / --report

def test_stale_reprend_les_non_VERTS_EFFECTIFS_et_PAS_les_verts(tmp_path, monkeypatch, depot):
    """Sans voie de sortie, `A RECONFRONTER` nommerait le probleme et le figerait ailleurs. Et
    `_stale` doit rester DISTINCT de `_unmeasured` : l'un dit << on n'a aucune mesure >>, l'autre
    << on en a une, il faut savoir si elle est encore vraie ICI >>."""
    ledger = tmp_path / "l.json"
    monkeypatch.setattr(P, "ledger_path", lambda: ledger)
    ledger.write_text(json.dumps({"fichiers": {
        "a_live.py": {"verdict": "VERT", "_commit": depot["agent"]},
        "b_live.py": {"verdict": "ROUGE", "_commit": depot["agent"]},
        "c_live.py": {"verdict": "SETUP", "_commit": depot["HEAD"]},
    }}), encoding="utf-8")
    assert P._stale(["a_live.py", "b_live.py", "c_live.py"]) == ["b_live.py", "c_live.py"]


def test_stale_ne_reclame_RIEN_quand_tout_est_vert(tmp_path, monkeypatch):
    ledger = tmp_path / "l.json"
    monkeypatch.setattr(P, "ledger_path", lambda: ledger)
    ledger.write_text(json.dumps({"fichiers": {"a_live.py": {"verdict": "VERT"}}}),
                      encoding="utf-8")
    assert P._stale(["a_live.py"]) == []


def test_report_since_n_est_PLUS_AVALE_en_silence(tmp_path, monkeypatch, capsys):
    """Le mode `--report` sortait AVANT de regarder `--since` : une lecture qu'on croyait bornee
    au diff rendait TOUT le ledger. C'est ce qui a fait lire trois rouges anciens comme << les
    rouges de la soiree >>."""
    ledger = tmp_path / "l.json"
    ledger.write_text(json.dumps({"fichiers": {
        "vieux_live.py": {"verdict": "ROUGE", "_commit": "0" * 40},
        "dudiff_live.py": {"verdict": "VERT", "_commit": "0" * 40},
    }}), encoding="utf-8")
    monkeypatch.setattr(P, "ledger_path", lambda: ledger)
    monkeypatch.setattr(P, "_live_in_diff", lambda ref: (["dudiff_live.py"], "1 fichier (simule)"))
    assert P._do_report(["vieux_live.py", "dudiff_live.py"], "origin/master") == 0
    sortie = capsys.readouterr().out
    assert "vieux_live.py" not in sortie
    # Sans `--since`, le meme ledger DOIT toujours rendre le rouge : la restriction est demandee,
    # jamais subie.
    assert P._do_report(["vieux_live.py", "dudiff_live.py"]) == 1


def test_une_ref_inconnue_en_report_est_un_REFUS_pas_un_vert(tmp_path, monkeypatch):
    """<< Un echec RENDU se lit comme une mesure >> : rendre 0 ici ferait passer une lecture qui
    n'a RIEN lu pour une lecture verte."""
    ledger = tmp_path / "l.json"
    ledger.write_text(json.dumps({"fichiers": {}}), encoding="utf-8")
    monkeypatch.setattr(P, "ledger_path", lambda: ledger)
    monkeypatch.setattr(P, "_live_in_diff", lambda ref: (None, "ref inconnue"))
    assert P._do_report(["a_live.py"], "pasunref") == 2


# --------------------------------------------------------------------------- format du ledger

def test_le_ledger_porte_la_RACINE_de_la_mesure_comme_TRACE(tmp_path, monkeypatch):
    """`_root` est une TRACE, pas un critere -- et c'est la piste 1 telle qu'elle a ete ARBITREE.
    Invalider sur la racine etait tentant (les trois rouges venaient d'un worktree disparu), mais
    la mesure l'interdit : 237 des 254 entrees viennent d'un worktree d'agent DISPARU, c'est le
    regime NOMINAL. Le critere qui discrimine est le COMMIT ; la racine reste pour le lecteur."""
    monkeypatch.setattr(P, "ledger_path", lambda: tmp_path / "l.json")
    monkeypatch.setattr(P, "_blobs", lambda rels: {r: "B" for r in rels})
    doc = P._merge_ledger({_CIBLE: {"verdict": "VERT", "passed": 1}}, "deadbeef")
    e = doc["fichiers"][_CIBLE]
    assert e["_root"] and Path(e["_root"]).name
    assert e["_commit"] == "deadbeef"


def test_la_relecture_du_LEDGER_REEL_ne_change_AUCUN_verdict_VERT():
    """Garde d'integration sur le vrai ledger versionne : la reparation ne doit toucher que des
    non-verts. Si elle mordait sur un vert, la gate reclamerait des rejeux en masse."""
    fichiers = P.entrees_du_ledger()
    if not fichiers:
        pytest.skip("aucun ledger dans ce checkout")
    verts = [r for r, c in fichiers.items() if c.get("verdict") == "VERT"]
    assert verts, "un ledger sans aucun vert rendrait ce test creux"
    vus, _ = P._relire(fichiers, verts)
    assert all(c.get("verdict") == "VERT" for c in vus.values())

