"""#462-r6 -- LE GARDE DU CANAL qui nomme le ROUGE DE SCENARIO.

Le mecanisme vit dans `scripts/python/counterproof.py` : deux types d'exception (`InertCounterproof`,
`UnconfrontableSample`) sous `ScenarioRed`, poses au niveau de l'ASSERTION. Sa valeur tient ENTIEREMENT
au fait que le NOM DU TYPE traverse la chaine jusqu'au lecteur -- pytest, puis le junitxml, puis le
ledger de `probe_462`. Un mecanisme qui nomme mais dont le nom se perd en route ne vaut rien.

CE FICHIER EST OFFLINE, donc joue par `probe_457` (perimetre DERIVE de `git ls-files
scripts/python/tests`, tout ce qui n'est pas `_live.py`), donc par la banque `scripts/ratchets.ps1`.
C'est pourquoi #462-r6 n'ajoute AUCUNE entree a la banque : la regle #427 (« un cliquet doit etre
dans une liste qu'on lance ») est satisfaite par ce canal-la, et #457-r6 a precisement retire les
trois entrees `pytest_*` qui nommaient leurs fichiers a la main.

TROIS VOLETS, ET CHACUN GARDE UN MAILLON DISTINCT
-------------------------------------------------
1. LE CONTRAT du helper : il ne leve rien quand la garde mord, il leve le BON type sinon, le
   message commence par le marqueur, et les quatre champs y sont TOUS (sans le remede, nommer la
   cause laisse le lecteur au meme carrefour).
2. LE CANAL : un pytest reel, dans un tmpdir SYSTEME, produit un junitxml que l'on relit AVEC LE
   VRAI CONSOMMATEUR (`probe_462._parse_junit`) -- pas une simulation. Le nom du type doit ressortir
   dans le `message` que le ledger conserve verbatim.
3. LE GISEMENT d'usurpation : personne ne doit ecrire le marqueur A LA MAIN dans un message
   d'assertion. Un rouge de PORT dont la prose porte `CONTRE-CONTROLE INERTE` serait classe a
   l'envers -- l'erreur exactement symetrique de celle que #462-r6 ferme. Le marqueur en
   COMMENTAIRE ou en DOCSTRING reste libre (ces fichiers doivent pouvoir se documenter).

⚠ Le volet 3 ne pretend PAS deriver « ceci est un contre-controle » : c'est indecidable
(`m0_n > live_n` et `m1_n == live_n` sont syntaxiquement jumeaux et de natures opposees). Il garde
la seule chose qui SOIT derivable -- que la declaration ne puisse pas etre contrefaite.

ASCII only (cp1252). Aucune ecriture sous `scripts/python/` (#455 : la banque tourne en parallele).
"""
from __future__ import annotations

import ast
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import counterproof as CP
import probe_462_live_tests_status as P462
import repo_read
from counterproof import (InertCounterproof, ScenarioRed, UnconfrontableSample,
                          assert_counterproof, assert_sample_confrontable)

PYDIR = Path(__file__).resolve().parents[1]
REPO = PYDIR.parents[1]

CHAMPS = dict(mutation="MUTATION-XYZ", doit_casser="DOIT-CASSER-XYZ", observe="OBSERVE-XYZ",
              remede="REMEDE-XYZ")

# (helper, type attendu, marqueur attendu)
HELPERS = [
    (assert_counterproof, InertCounterproof, CP.MARKER_COUNTERPROOF),
    (assert_sample_confrontable, UnconfrontableSample, CP.MARKER_SAMPLE),
]


# ------------------------------------------------------------------ 1. le CONTRAT du helper

@pytest.mark.parametrize("helper,exc,marker", HELPERS, ids=["counterproof", "sample"])
def test_helper_is_silent_when_the_guard_bites(helper, exc, marker):
    """La garde mord -> rien. Un helper qui leverait TOUJOURS transformerait chaque scenario sain
    en rouge de scenario, et se ferait desarmer dans la semaine."""
    assert helper(True, **CHAMPS) is None


@pytest.mark.parametrize("helper,exc,marker", HELPERS, ids=["counterproof", "sample"])
def test_helper_raises_its_own_named_type(helper, exc, marker):
    """Le TYPE est le vehicule : c'est lui que pytest imprime, et lui que le junitxml transporte.

    Il reste une `AssertionError` a dessein -- meme couleur, meme comptage, et tout `except
    AssertionError` existant continue de le voir. Ce qui change est le NOM."""
    with pytest.raises(exc) as ei:
        helper(False, **CHAMPS)
    assert issubclass(exc, ScenarioRed) and issubclass(ScenarioRed, AssertionError)
    assert str(ei.value).startswith(marker), (
        "le message doit COMMENCER par le marqueur : `probe_462` tronque a 300 caracteres apres "
        "avoir aplati les sauts de ligne, et pytest n'affiche que la premiere ligne en short "
        "summary. Message : %r" % str(ei.value)[:120])


@pytest.mark.parametrize("helper,exc,marker", HELPERS, ids=["counterproof", "sample"])
def test_helper_message_carries_the_four_fields(helper, exc, marker):
    """Les quatre champs sont dans le message. Le REMEDE compte autant que la cause : les trois
    rouges de #462-r6 nommaient tous leur symptome, aucun ne disait quoi en faire."""
    with pytest.raises(exc) as ei:
        helper(False, **CHAMPS)
    msg = str(ei.value)
    for valeur in CHAMPS.values():
        assert valeur in msg, "champ %r absent du message" % valeur


@pytest.mark.parametrize("helper,exc,marker", HELPERS, ids=["counterproof", "sample"])
def test_helper_refuses_a_positional_or_missing_field(helper, exc, marker):
    """Les quatre champs sont KEYWORD-ONLY et OBLIGATOIRES : un helper qu'on peut appeler sans
    remede redevient un prefixe de message, et derive."""
    with pytest.raises(TypeError):
        helper(False)
    with pytest.raises(TypeError):
        helper(False, mutation="m", doit_casser="d", observe="o")       # remede manquant
    with pytest.raises(TypeError):
        helper(False, "m", "d", "o", "r")                               # positionnels


# ------------------------------------------------------------------ 2. le CANAL jusqu'au ledger

_MODULE_SOUS_TEST = '''
import sys
sys.path.insert(0, %r)
from counterproof import assert_counterproof, assert_sample_confrontable


def test_inerte():
    assert_counterproof(False, mutation="M-CANAL", doit_casser="D-CANAL", observe="O-CANAL",
                        remede="R-CANAL")


def test_echantillon():
    assert_sample_confrontable(False, mutation="M-CANAL", doit_casser="D-CANAL",
                               observe="O-CANAL", remede="R-CANAL")
'''


def test_type_name_survives_pytest_junit_and_probe_462_reader():
    """LE MAILLON CRITIQUE : `probe_462` conserve `child.get("message")` du `<failure>` junitxml et
    l'ecrit VERBATIM dans `scripts/ratchets-462-live-attestations.json`. Si pytest cessait d'y mettre
    le nom de la classe (changement de `junit_family`, exception qui ne derive plus
    d'`AssertionError`, helper rabattu sur un `pytest.fail`), le mecanisme deviendrait decoratif :
    vert ici, muet la ou on le lit.

    On ne SIMULE pas ce chemin -- on lance un vrai pytest, et on relit son XML avec la vraie
    fonction du vrai consommateur. Tmpdir SYSTEME (`mkdtemp()` sans `dir=`) : un cliquet n'ecrit
    JAMAIS sous `scripts/python/`, la banque tourne en parallele (#455)."""
    tmp = Path(tempfile.mkdtemp(prefix="cp462r6-"))
    try:
        cible = tmp / "test_canal_462r6.py"
        cible.write_text(_MODULE_SOUS_TEST % str(PYDIR), encoding="utf-8")
        xml = tmp / "junit.xml"
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             "--junitxml=%s" % xml, str(cible)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(tmp))
        assert xml.exists(), "pytest n'a pas produit de junitxml : %s" % (r.stdout or "")[-400:]

        # Le VRAI lecteur, avec son index reconstruit comme il le fait (classname -> chemin).
        index = P462._classname_index(["test_canal_462r6.py"])
        res = P462._parse_junit(xml, index)
        assert res, "le lecteur de probe_462 n'a rien indexe (index=%s)" % index
        counts = res["test_canal_462r6.py"]
        assert counts["failed"] == 2, "attendu 2 echecs, obtenu %s" % counts
        messages = " | ".join(counts["messages"])
        for attendu in ("InertCounterproof", "UnconfrontableSample",
                        CP.MARKER_COUNTERPROOF, CP.MARKER_SAMPLE):
            assert attendu in messages, (
                "%r absent des messages que le ledger conserverait : %s" % (attendu, messages))
        # Et le verdict du fichier reste ROUGE : nommer la cause ne fait PAS taire l'echec.
        assert P462._verdict(counts) == "ROUGE"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ 3. le GISEMENT d'usurpation

def _perimetre() -> list:
    """Les `.py` VERSIONNES de `scripts/python`, chemins ABSOLUS.

    Derive de `git ls-files` -- donc borne au checkout courant PAR CONSTRUCTION : depuis un
    worktree, git ne liste que ce worktree ; depuis l'arbre principal, `.claude/worktrees/` est un
    AUTRE checkout et n'y figure pas. Pas de `rglob` depuis la racine, pas d'exclusion a saisir
    (#434 / #440)."""
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "scripts/python"],
                         capture_output=True, text=True, check=True)
    return [REPO / line.strip() for line in out.stdout.splitlines()
            if line.strip().endswith(".py")]


def _messages_dassertion(source: str) -> list:
    """Les litteraux de MESSAGE d'un ECHEC : 2e argument d'un `assert`, et arguments d'un `raise`
    dont la cible est une exception (`<X>Error`, ou les types de `counterproof`).

    On ne regarde QUE ce canal-la. Un commentaire, une docstring ou un `print` de verdict qui cite
    le marqueur reste legitime -- ces fichiers doivent pouvoir se documenter, et un probe imprime
    son verdict. Ce qui est garde, c'est qu'un ECHEC ne puisse pas se REVENDIQUER rouge de scenario
    sans passer par le type."""
    out = []

    def _litteraux(node):
        """Toutes les chaines CONSTANTES atteignables sans evaluer (concat, f-string, JoinedStr)."""
        vus = []
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                vus.append(sub.value)
        return vus

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assert) and node.msg is not None:
            out.extend(_litteraux(node.msg))
        elif isinstance(node, ast.Raise) and node.exc is not None:
            cible = node.exc
            nom = ""
            if isinstance(cible, ast.Call):
                f = cible.func
                nom = f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")
            elif isinstance(cible, ast.Name):
                nom = cible.id
            if nom.endswith("Error") or nom.endswith("Counterproof") or nom.endswith("Sample"):
                out.extend(_litteraux(cible))
    return out


def test_no_handwritten_marker_in_any_assertion_message():
    """Le marqueur ne s'ecrit PAS a la main dans un message d'echec : il vient du helper, ou il
    n'est pas la. Sinon un rouge de PORT peut porter le nom d'un rouge de SCENARIO, et le lecteur
    (ou le ledger) le classe a l'envers -- l'erreur symetrique de celle qu'on ferme.

    `counterproof.py` est le SEUL exempte, et il n'est pas exempte par une allowlist : il est le
    module qui DEFINIT les marqueurs, et c'est ce qui le designe."""
    fichiers = [p for p in _perimetre() if p.name != "counterproof.py"]
    textes = repo_read.read_texts(fichiers, errors="replace")
    fautifs = []
    balayes = 0
    for path, texte in zip(fichiers, textes):
        if texte is None:
            continue
        if not any(m in texte for m in CP.MARKERS):
            balayes += 1
            continue
        balayes += 1
        try:
            messages = _messages_dassertion(texte)
        except SyntaxError:
            continue
        for msg in messages:
            for marqueur in CP.MARKERS:
                if marqueur in msg:
                    fautifs.append("%s : %r" % (path.relative_to(REPO).as_posix(), msg[:110]))
    assert balayes > 0, "perimetre VIDE -- un balayage qui rend zero se lit comme `rien a signaler`"
    assert not fautifs, (
        "marqueur ecrit A LA MAIN dans %d message(s) d'echec (perimetre : %d fichiers). "
        "Passer par `counterproof.assert_counterproof` / `assert_sample_confrontable` : le "
        "verdict doit venir du TYPE, pas de la prose. %s" % (len(fautifs), balayes, fautifs))


@pytest.mark.parametrize("source,attendu", [
    ('assert x, "CONTRE-CONTROLE INERTE -- bidon"', 1),
    ('assert x, f"prefixe {v} ECHANTILLON NON CONFRONTABLE"', 1),
    ('raise AssertionError("CONTRE-CONTROLE INERTE : bidon")', 1),
    # Un `raise <X>Error` est un canal d'ECHEC comme un autre : le marqueur y usurpe le verdict
    # tout autant. Le detecteur le voit, et c'est VOULU -- l'attente inverse a ete ecrite d'abord,
    # et c'est le detecteur qui avait raison.
    ('raise RuntimeError("ECHANTILLON NON CONFRONTABLE")', 1),
    ('# CONTRE-CONTROLE INERTE : commentaire, legitime', 0),
    ('"""CONTRE-CONTROLE INERTE dans une docstring, legitime."""', 0),
    # Un probe IMPRIME son verdict ; ce n'est pas un canal d'echec et ca reste libre.
    ('print("CONTRE-CONTROLE INERTE : %s" % detail)', 0),
    ('assert x, "valeur inattendue"', 0),
    # L'appel legitime ne porte AUCUN marqueur : il vient du type. C'est tout l'interet.
    ('assert_counterproof(a > b, mutation="m", doit_casser="d", observe="o", remede="r")', 0),
], ids=["assert-msg", "fstring", "raise-AssertionError", "raise-RuntimeError", "commentaire",
        "docstring", "print", "temoin", "appel-legitime"])
def test_the_usurpation_detector_actually_bites(source, attendu):
    """AUTO-TEST du detecteur, sur des sources SYNTHETIQUES. Un balayage dont le detecteur a cesse
    de mordre rend VERT sur un depot fautif -- c'est ce que `probe_181` faisait avant #430. Les deux
    directions sont gardees : ce qui doit etre vu l'est, ce qui est legitime ne l'est pas."""
    trouves = [m for m in _messages_dassertion(source)
               if any(k in m for k in CP.MARKERS)]
    assert len(trouves) == attendu, "source %r -> %s" % (source, trouves)
