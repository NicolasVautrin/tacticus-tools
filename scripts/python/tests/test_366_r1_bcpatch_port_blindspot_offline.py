"""#366-r1-bcpatch-invisible -- GARDE du croisement PATCH(seed BC) x LECTURE(port). OFFLINE.

CE QUE CETTE GARDE TIENT. Une variable d'ability patchee dans un seed BC n'est lue QUE par le
natif : le moteur Python la lit dans `gameconfig` (`magnitude.ability_var`). Tant que l'effet vise
n'est pas porte, la fixture passe pour une neutralisation ; le jour ou il l'est, le MEME geste
devient une desynchronisation. Mesure du 2026-08-01 : le montage de `1115` posait
`InescapableAccuracy.extraCritDmg = 0` -- inerte des deux cotes la veille, FAUX de 997 points le
lendemain.

L'INVARIANT est `intersection == 0`, avec des exceptions NOMMEES et justifiees une par une
(jamais un seuil : un seuil cesse de couvrir des que le gisement bouge).

Un recenseur dont on n'a jamais vu le rouge ne garantit rien : ces tests sont sa MORSURE, figee --
les quatre formes d'ecriture (helper, indirection par constante/ternaire, ecriture directe, alias
de sous-arbre) doivent rougir, et un patch de variable NON lue doit rester vert.

ASCII only (cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_366_r1_bcpatch_port_blindspot as P                        # noqa: E402


@pytest.fixture(scope="module")
def reads():
    return P.scan_reads()


@pytest.fixture(scope="module")
def patches():
    return P.scan_patches()


# --- L'INVARIANT --------------------------------------------------------------------------------

def test_aucune_intersection_non_declaree(reads, patches):
    """Le cliquet. Rouge = un patch de seed BC que le moteur relit depuis gameconfig."""
    rep = P.intersect(reads, patches)
    assert rep["red"] == [], [(r["ability"], r["var"], r["origins"]) for r in rep["red"]]
    P.assert_no_blind_patch(patches=patches, reads=reads)       # ne leve pas


def test_aucune_exception_orpheline(reads, patches):
    """Une exception qui ne correspond a AUCUN patch reel donne un blanc-seing a un couple qui
    n'existe plus -- meme faute qu'une epingle orpheline (#375)."""
    rep = P.intersect(reads, patches)
    assert rep["orphan_exceptions"] == [], rep["orphan_exceptions"]


def test_la_couverture_reste_nommee(reads, patches):
    """Un site du moteur ou NI l'ability NI la variable ne sont determinables rend le recensement
    aveugle sur son axe. Les connus sont NOMMES ; un NOUVEAU doit rougir."""
    rep = P.intersect(reads, patches)
    assert rep["holes"] == [], rep["holes"]
    assert rep["unresolved"] == [], rep["unresolved"]


# --- LA MORSURE ---------------------------------------------------------------------------------

@pytest.mark.parametrize("tag,source,want_red", [
    ("helper", P._SELF_TEST_RED, True),
    ("var_non_lue", P._SELF_TEST_GREEN, False),
    ("indirection", P._SELF_TEST_INDIRECT, True),
    ("ecriture_directe", P._SELF_TEST_DIRECT, True),
    ("alias", P._SELF_TEST_ALIAS, True),
    ("relais_parametre", P._SELF_TEST_RELAY, True),
])
def test_le_recenseur_mord(tmp_path, reads, tag, source, want_red):
    """Contre-epreuve : on REINTRODUIT le geste de `1115`, sous ses quatre formes d'ecriture.

    `exceptions={}` -- on mesure le RECENSEUR, pas la liste des exemptions. Sans cela une exemption
    suffirait a rendre le test vert, et la morsure ne prouverait plus rien.
    """
    f = tmp_path / ("fixture_%s.py" % tag)
    f.write_text(source, encoding="utf-8")
    rep = P.intersect(reads, P.scan_patches(files=[f]), exceptions={})
    assert bool(rep["red"]) is want_red, rep


def test_le_port_voit_les_deux_temoins(reads):
    """Sans ces deux couples, les bras ci-dessus rougiraient pour la mauvaise raison.

    `InescapableAccuracy/extraCritDmg` = lecture DIRECTE (le port de `1116`) ;
    `RighteousRepugnance/chance` = lecture via un RELAIS parametre (`ConfigVarForEntity`), que seul
    le point fixe resout -- c'est la contre-epreuve du resolveur, pas du croisement.
    """
    assert ("InescapableAccuracy", "extraCritDmg") in reads["pairs"]
    assert ("RighteousRepugnance", "chance") in reads["pairs"]


def test_seconde_source_le_grep_ne_voit_rien_que_l_AST_rate(reads):
    """Contre-epreuve INDEPENDANTE du resolveur : les couples litteraux, lus au grep.

    Un couple vu ici et absent du recensement est un FAUX NEGATIF -- exactement ce qui laisserait
    passer un patch dangereux. Mesure du 2026-08-01 : trois paires manquaient (`FleshmetalGuns`,
    variable ecrite `"minDmg" + sfx`) et SEULE cette seconde source les a montrees.
    """
    lost = sorted(P.grep_literal_pairs() - reads["pairs"])
    assert lost == [], lost


def test_le_foyer_de_lecture_existe_toujours():
    """Un recenseur indexe sur un NOM doit rougir si le nom disparait, jamais rendre zero."""
    assert P.check_reader()


def test_aucun_second_foyer_de_lecture_gameconfig():
    """`ability_var` est le foyer DECLARE. Une lecture directe de `gameconfig.ability(...)
    ["variables"]` dans `engine/**` rendrait le recensement partiel -- et un partiel qui rend zero
    se lit comme « rien a signaler »."""
    assert P.scan_direct_gameconfig() == []
