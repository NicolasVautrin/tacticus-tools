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


# --- LA PREMISSE, MESUREE (et non supposee) -----------------------------------------------------

def test_le_patch_arrive_au_natif_et_PAS_au_port(tmp_path):
    """LES DEUX LECTURES, cote a cote. C'est tout le cas, en six lignes.

    On patche `InescapableAccuracy.extraCritDmg` a une valeur impossible, puis on lit :
      * par le CHEMIN DU BUILD (`_load_seed_bc`, celui que le runner natif recoit) -> la valeur
        patchee, epinglee (#375) donc survivante ;
      * par le FOYER DU PORT (`magnitude.ability_var`) -> la valeur du GAMECONFIG, intacte.
    Sans cette mesure, le cliquet reposerait sur une premisse supposee.
    """
    import catalog_inject as CI
    from rl_collect_batch import _load_seed_bc
    from engine.entities.effects.magnitude import ability_var

    forced = 12345
    p, _rep = CI.write_variable_patched_seed_bc(
        tmp_path / "bc.json", [("InescapableAccuracy", 50, {"extraCritDmg": forced})])

    bc = _load_seed_bc(str(p))
    arr = (bc["Abilities"]["PassiveAbilities"]["InescapableAccuracy"]["Variables"]["extraCritDmg"])
    assert int(arr[49]) == forced, "le NATIF doit voir le patch (sinon c'est #375, pas ce cas)"

    import gameconfig as GC
    from_gc = int(((GC.ability("InescapableAccuracy") or {})["variables"]["extraCritDmg"])[49])
    port = ability_var("InescapableAccuracy", "extraCritDmg", 50)
    assert port == from_gc != forced, (
        "le PORT doit lire le GAMECONFIG, pas le patch -- si ce test devient rouge, `ability_var` "
        "a change de source et TOUT ce cliquet est a re-deriver")


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


def test_aucun_trou_declare_orphelin(reads, patches):
    """LE CRAN SYMETRIQUE DE `test_aucune_exception_orpheline` (#10027).

    Un fichier NOMME dans `_COVERAGE_HOLES` qui n'est plus aveugle est un FANTOME : il donne un
    blanc-seing a un trou qui n'existe plus, et surtout il masquerait sa REAPPARITION -- le site
    pourrait redevenir indeterminable sans que rien ne rougisse. C'est exactement le vice que la
    garde des exemptions interdit deja de l'autre cote du croisement.

    Ce cran n'existait pas, et il aurait du : l'extension du resolveur de cette tranche a rendu
    DEUX entrees mortes d'un coup (`predict.py`, `genestealer.py`, tous deux #935) -- rien ne
    l'aurait dit."""
    rep = P.intersect(reads, patches)
    vivants = set(rep["holes_declared"]) | set(rep["holes"])
    fantomes = sorted(set(P._COVERAGE_HOLES) - vivants)
    assert not fantomes, (
        "trou(s) de couverture NOMME(s) mais plus aveugle(s) : %s. Le resolveur les atteint "
        "desormais -- les RETIRER de `_COVERAGE_HOLES` (en DISANT ce qui a change), sinon leur "
        "reapparition passerait inapercue." % (fantomes,))
    # NON-DEGENERESCENCE : la liste ne doit pas etre vide au point que ce cran ne mesure plus rien.
    assert P._COVERAGE_HOLES, "plus aucun trou nomme : ce cran ne porte plus sur rien"


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
