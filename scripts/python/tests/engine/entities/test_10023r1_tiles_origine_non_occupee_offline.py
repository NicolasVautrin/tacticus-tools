"""#10023-r1 -- `Tiles(origin)` resout la TUILE en son OCCUPANT, et s'applique PAR ENTITE.

CLIQUET, pas inventaire. Chaque etage de `probe_10023r1_tiles_origine_non_occupee.py` est joue
ici comme un test, et chacun porte sa MUTATION : on retablit le port d'AVANT
(`_main_tiles(origin, board, units) == _origin_tiles(origin, board)[:1]`, la tuile BRUTE) et on
exige que l'etage ROUGISSE. Un cliquet vert dans les deux regimes ne mesure rien.

RE relue VERBATIM sur `t6dpr4k06g` -- la chaine est citee en tete du probe. Les trois proprietes
gardees ici :

  1. une origine TUILE VIDE ne designe AUCUNE entite (`UnitExtensions$$GetUnit` rend null sur un
     `TileContentComponent` non rempli), donc `Tiles(origin)` est vide et le natif ne retranche
     RIEN ;
  2. une origine qui designe un PIED SECONDAIRE retranche la MAIN TILE de l'occupant, jamais le
     pied donne (`EntityExtensions$$GetMainTile` = la tuile du PREMIER pied) ;
  3. `GetMainTile` est applique PAR ENTITE, donc une origine a N unites distinctes retranche N
     tuiles -- et une origine multi-hex n'en retranche toujours qu'UNE (non-regression #10023).

⚠ LA MUTATION PATCHE **DEUX** LIAISONS, et ce n'est pas une precaution : `accessors.py` importe
`_main_tiles` en FORME A (`from ...dsl.base import _main_tiles`), donc un `monkeypatch.setattr`
sur le seul `engine.dsl.base._main_tiles` NE MORD PAS sur ce module-la (doctrine « HISSER, OUI --
MAIS EN FORME B »). Patcher la seule liaison du foyer rendrait les mutations des etages 1/1bis/3
INERTES, et le cliquet serait vert des deux cotes.

ASCII only (cp1252). Aucun runner, aucun RPC.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/hexgeo.py",
        "scripts/python/probe_10023r1_tiles_origine_non_occupee.py",
        # PRIS LARGE : l'etage 0 RECENSE les call-sites de `_main_tile*` et les appelants de
        # `_within` dans TOUT `engine/**`, et l'etage 6 y recense les instanciations des quatre
        # noeuds a exclusion. Une liste de fichiers choisis ne pourrait pas montrer le call-site
        # qu'elle a oublie -- c'est exactement le gisement que ce cliquet garde.
        "scripts/python/engine/**/*.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Cliquet OFFLINE de `Tiles(origin)` : resolution TUILE -> OCCUPANT, exclusion PAR "
              "ENTITE, et recensement des call-sites. Aucun runner, aucun RPC.",
}

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import probe_10023r1_tiles_origine_non_occupee as P      # noqa: E402
from engine.dsl import base as B                          # noqa: E402


#: Les DEUX liaisons de `_main_tiles` -- cf. l'avertissement en tete de module.
_LIAISONS = ("engine.dsl.base._main_tiles",
             "engine.entities.selectors.accessors._main_tiles")


def _port_d_avant_tuile_brute(origin, board=None, units=None) -> list:
    """Le port d'AVANT #10023-r1, tel que l'appelait `accessors.SurroundingTiles` : la PREMIERE
    tuile de l'origine aplatie, BRUTE -- `board` passe, `units` jamais consulte.

    Ni resolution d'occupant (une tuile VIDE retranchait quand meme, un pied SECONDAIRE se
    retranchait lui-meme au lieu de la main tile), ni application par entite (N unites n'en
    retranchaient qu'une)."""
    return B._origin_tiles(origin, board)[:1]


def _port_d_avant_sans_board(origin, board=None, units=None) -> list:
    """Le port d'AVANT tel que l'appelait `dsl/base._within` : `_main_tile(center)`, SANS `board`.

    Mutation DISTINCTE de la precedente, et il en faut deux : la faute de `_within` n'etait pas
    dans la fonction mais dans ce qu'elle ne recevait PAS. Sur une origine en domaine ID,
    `_origin_tiles(list[int], None)` rend `[]` -- exclusion silencieusement VIDE. La mutation
    `tuile brute`, qui passe `board`, ne la reproduit donc pas et laisse l'etage 2 VERT."""
    return B._origin_tiles(origin, None)[:1]


def _mutateur(monkeypatch, remplacant):
    """Substitue sur les DEUX liaisons, puis VERIFIE que ca a mordu."""
    def _armer():
        for cible in _LIAISONS:
            monkeypatch.setattr(cible, remplacant)
        mod, _, nom = _LIAISONS[1].rpartition(".")
        assert getattr(sys.modules[mod], nom) is remplacant, (
            "la mutation n'a PAS mordu sur %s -- la contre-epreuve serait vacue" % _LIAISONS[1])
    return _armer


@pytest.fixture()
def mutation(monkeypatch):
    return _mutateur(monkeypatch, _port_d_avant_tuile_brute)


@pytest.fixture()
def mutation_sans_board(monkeypatch):
    return _mutateur(monkeypatch, _port_d_avant_sans_board)


# --- ETAGE 0 : le RECENSEMENT (aucune mutation : c'est une mesure statique de l'arbre) ---
def test_e0_les_call_sites_passent_board_et_units():
    assert P.etage0_recensement() == 0


# --- ETAGES 1 a 5 : le mirror, puis sa MUTATION ---
@pytest.mark.parametrize("etage", [
    P.etage1_tuile_vide,
    P.etage1bis_pied_secondaire,
    P.etage2_within_domaine_id,
    P.etage3_multi_unites,
    P.etage4_non_regression_10023,
    P.etage5_substrat_absent,
], ids=lambda f: f.__name__)
def test_le_mirror_tient(etage):
    assert etage() == 0


@pytest.mark.parametrize("etage", [
    P.etage1_tuile_vide,          # tuile VIDE -> le port d'avant retranchait la tuile
    P.etage1bis_pied_secondaire,  # pied secondaire -> il coupait le pied au lieu de la main tile
    P.etage3_multi_unites,        # N unites -> il n'en retranchait qu'UNE
    P.etage5_substrat_absent,     # substrat PRESENT -> il ne resolvait pas l'occupant
], ids=lambda f: f.__name__)
def test_la_mutation_TUILE_BRUTE_fait_ROUGIR_l_etage(etage, mutation):
    """DISCRIMINANT : le port d'avant doit faire echouer chacun de ces quatre etages."""
    mutation()
    assert etage() == 1, (
        "l'etage %s reste VERT sous le port d'avant : il ne mesure pas ce qu'il pretend garder"
        % etage.__name__)


def test_la_mutation_SANS_BOARD_fait_ROUGIR_l_etage2(mutation_sans_board):
    """L'etage 2 exige SA mutation, et c'est le fait le plus instructif de ce fichier.

    La faute (b) n'etait pas dans `_main_tile` mais dans l'ARGUMENT qu'on ne lui passait pas :
    sous la mutation `tuile brute` -- qui, elle, passe `board` -- l'etage 2 reste VERT. Un cliquet
    qui n'aurait eu qu'une mutation aurait donc declare l'etage 2 non discriminant, alors qu'il
    l'est pour une autre cause."""
    mutation_sans_board()
    assert P.etage2_within_domaine_id() == 1


@pytest.mark.parametrize("etage", [P.etage2_within_domaine_id, P.etage4_non_regression_10023],
                         ids=lambda f: f.__name__)
def test_ces_etages_survivent_a_la_mutation_TUILE_BRUTE_et_c_est_MESURE(etage, mutation):
    """Le pendant du test precedent : il faut DIRE ce que la mutation `tuile brute` ne montre pas.

    `etage4` (non-regression #10023) : le port d'avant le passait DEJA, la premiere tuile de
    l'empreinte ETANT la main tile. `etage2` : sa faute est l'argument manquant, pas la fonction.
    Les ranger en silence parmi les discriminants rendrait ce fichier faux, pas plus severe."""
    mutation()
    assert etage() == 0


# --- ETAGE 6 : l'INVENTAIRE d'atteignabilite (jamais bloquant, mais il doit MESURER) ---
def test_e6_l_inventaire_d_atteignabilite_est_NON_VIDE():
    """Il rend `0` par construction -- ce qu'on garde ici, c'est qu'il ne mesure pas le VIDE.

    Un recenseur qui ne visiterait plus rien rendrait `0` lui aussi, et se lirait « rien a
    signaler » : l'assertion de non-vide est ce qui empeche ce faux vert."""
    assert P.etage6_atteignabilite_multi_unites() == 0
