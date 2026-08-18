"""#10023-r1 -- `Tiles(origin)` en domaine TUILE : LA PREMISSE DU RESIDU ETAIT FAUSSE.

CLIQUET, pas inventaire. Chaque etage de `probe_10023r1_tiles_origine_non_occupee.py` est joue ici
comme un test, et chacun porte SA mutation. Il y en a **TROIS**, distinctes, parce que les trois
defauts annonces par le residu n'avaient ni la meme cause ni le meme verdict :

  * `_resolution_occupant` -- LA THESE REFUTEE. Le residu demandait de resoudre chaque
    entite-TUILE en son OCCUPANT avant `GetMainTile`. **11 casts live sur 11** de `1201 SquigMine`
    (masque `TargetTileIsFree` -> tuile ciblee toujours VIDE) disent l'inverse : la tuile EST
    retranchee (`probe_10023r1_squig_pool_live.py` ; `0,5^11 = 0,05 %` par hasard). Les etages
    1, 1bis et 5 doivent ROUGIR sous elle.
  * `_ts0_partout` -- le port d'avant STRICT. Correct en domaine tuile, faux en domaine UNITE ou
    `UnitsMainTilesSelector$$Select` applique `GetMainTile` PAR ENTITE : l'etage 3 rougit.
  * `_sans_board` -- le seul defaut REEL du residu : `_within` appelait `_main_tile(center)` sans
    `board`, donc `[]` sur une origine en domaine ID, donc exclusion silencieusement VIDE.
    L'etage 2 rougit.

⚠ **UN TEMOIN INDEPENDANT existait deja, et il n'est PAS celui qu'on attendait.** Contre-epreuve
JOUEE (these refutee cablee dans `_main_tiles`, quatre tests cibles rejoues) : trois des quatre
restent VERTS -- dont `test_1030_the_lantern_offline`, le plus proche du sujet, parce que sur son
call-site les sept entites-tuile d'une empreinte resolvent TOUTES vers la meme unite et que les
deux theses y rendent la MEME tuile (c'est exactement pourquoi #10023 n'avait pas pu trancher).
Le quatrieme, lui, ROUGIT :
`test_967r2_include_non_walkable_offline.py::test_etage4_les_deux_faces_de_1187_s_accordent`
(`1187 ThriceBlessedConflagration`, `sisterhood.py::SurroundingTiles(Target())`) -- une face
DECISION/COMBAT qui cesse de s'accorder. La banque refusait donc deja la these du residu, par un
fichier qu'aucune lecture de la fiche n'aurait designe.

⚠ LES MUTATIONS PATCHENT **DEUX** LIAISONS, et ce n'est pas une precaution : `accessors.py`
importe `_main_tiles` en FORME A (`from ...dsl.base import _main_tiles`), donc un
`monkeypatch.setattr` sur le seul `engine.dsl.base._main_tiles` NE MORD PAS sur ce module-la
(doctrine « HISSER, OUI -- MAIS EN FORME B »). Patcher la seule liaison du foyer rendrait les
mutations des etages 1/1bis/3 INERTES, et le cliquet serait vert des deux cotes.

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


def _resolution_occupant(origin, board=None, units=None) -> list:
    """LA THESE QUE LA MESURE LIVE A REFUTEE : resoudre chaque entite-TUILE en son OCCUPANT
    (`TargetsSelector$$SelectUnit` -> `UnitExtensions$$GetUnit`) avant `GetMainTile`.

    C'est ce que l'enonce de #10023-r1 demandait de porter, et c'est ce que 11 casts live de
    `1201 SquigMine` contredisent. La garder ici comme MUTATION est ce qui empeche qu'elle
    revienne : les etages 1, 1bis et 5 doivent rougir sous elle."""
    occ = B._occupants_by_tile(units or ())
    out: list = []
    for e in B._origin_entities(origin):
        u = e if B._est_unite(e, units) else None
        if u is None:
            for p in B._origin_tiles(e, board):
                u = occ.get(p)
                if u is not None:
                    break
        if u is None:                       # tuile VIDE -> `IsFilled == 0` -> null -> rien ajoute
            continue
        feet = B._feet(u)
        if feet and feet[0] not in out:
            out.append(feet[0])
    return out


def _ts0_partout(origin, board=None, units=None) -> list:
    """Le port d'AVANT, STRICT : la premiere tuile de l'origine aplatie, quel que soit le domaine.

    En domaine TUILE il coincide avec le port courant (c'est ce que la mesure valide) ; en domaine
    UNITE il n'en rend qu'UNE la ou `UnitsMainTilesSelector$$Select` en rend N. Discriminant du
    seul etage 3."""
    return B._origin_tiles(origin, board)[:1]


def _sans_board(origin, board=None, units=None) -> list:
    """Le port d'AVANT tel que l'appelait `dsl/base._within` : `_main_tile(center)`, SANS `board`.

    Mutation DISTINCTE des deux autres, et il en faut trois : la faute de `_within` n'etait pas
    dans la fonction mais dans ce qu'elle ne recevait PAS. Sur une origine en domaine ID,
    `_origin_tiles(list[int], None)` rend `[]` -- exclusion silencieusement VIDE."""
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
def mutation_resolution(monkeypatch):
    return _mutateur(monkeypatch, _resolution_occupant)


@pytest.fixture()
def mutation_ts0(monkeypatch):
    return _mutateur(monkeypatch, _ts0_partout)


@pytest.fixture()
def mutation_sans_board(monkeypatch):
    return _mutateur(monkeypatch, _sans_board)


# --- ETAGE 0 : le RECENSEMENT (aucune mutation : c'est une mesure statique de l'arbre) ---
def test_e0_les_call_sites_passent_board_et_units():
    assert P.etage0_recensement() == 0


# --- ETAGES 1 a 5 : le port, puis les TROIS mutations ---
@pytest.mark.parametrize("etage", [
    P.etage1_tuile_vide,
    P.etage1bis_pied_secondaire,
    P.etage2_within_domaine_id,
    P.etage3_multi_unites,
    P.etage4_non_regression_10023,
    P.etage5_domaine_tuile_insensible_a_units,
], ids=lambda f: f.__name__)
def test_le_port_tient(etage):
    assert etage() == 0


@pytest.mark.parametrize("etage", [
    P.etage1_tuile_vide,                        # la tuile VIDE cesserait d'etre retranchee
    P.etage1bis_pied_secondaire,                # la MAIN TILE serait coupee a la place du pied
    P.etage5_domaine_tuile_insensible_a_units,  # la sortie se mettrait a dependre de `units`
], ids=lambda f: f.__name__)
def test_la_RESOLUTION_D_OCCUPANT_fait_ROUGIR_l_etage(etage, mutation_resolution):
    """LE cliquet de cette tranche : la these REFUTEE ne doit pas pouvoir revenir en silence.

    Elle est seduisante -- elle se lit directement dans `TargetsSelector$$SelectUnit` -- et c'est
    precisement pour ca qu'il faut un refus EXECUTABLE et pas une phrase de docstring. Un lecteur
    qui « aligne le code sur le decompile » la reintroduirait, et le seul temoin qui l'attraperait
    ailleurs est `test_967r2_include_non_walkable_offline::test_etage4_les_deux_faces_de_1187_s
    _accordent` -- un fichier que rien ne designe depuis ici (contre-epreuve jouee, cf. l'en-tete
    de module)."""
    mutation_resolution()
    assert etage() == 1, (
        "l'etage %s reste VERT sous la resolution d'occupant : il ne garde pas la mesure live"
        % etage.__name__)


def test_le_PORT_D_AVANT_fait_ROUGIR_l_etage3(mutation_ts0):
    """En domaine UNITE, `ts[0]` ne rend qu'UNE main tile la ou la boucle native en rend N."""
    mutation_ts0()
    assert P.etage3_multi_unites() == 1


def test_SANS_BOARD_fait_ROUGIR_l_etage2(mutation_sans_board):
    """L'etage 2 exige SA mutation, et c'est le fait le plus instructif de ce fichier.

    La faute (b) n'etait pas dans `_main_tile` mais dans l'ARGUMENT qu'on ne lui passait pas : les
    deux autres mutations passent `board` et laissent l'etage 2 VERT. Un cliquet a mutation unique
    l'aurait donc declare non discriminant, alors qu'il l'est pour une autre cause."""
    mutation_sans_board()
    assert P.etage2_within_domaine_id() == 1


@pytest.mark.parametrize("etage", [P.etage2_within_domaine_id, P.etage3_multi_unites,
                                   P.etage4_non_regression_10023],
                         ids=lambda f: f.__name__)
def test_ces_etages_survivent_a_la_RESOLUTION_et_c_est_MESURE(etage, mutation_resolution):
    """Le pendant du test precedent : il faut DIRE ce que la mutation `resolution` ne montre pas.

    `etage2` : sa faute est l'argument manquant, pas la fonction. `etage3` : son origine est en
    domaine UNITE, ou la resolution est un no-op. `etage4` (non-regression #10023) : les sept
    entites-tuile resolvent TOUTES vers la meme unite, donc la resolution y rend AUSSI une seule
    tuile -- c'est exactement pourquoi #10023 ne pouvait pas distinguer les deux theses, et
    pourquoi il a fallu un call-site a tuile VIDE pour trancher."""
    mutation_resolution()
    assert etage() == 0


# --- ETAGE 6 : l'INVENTAIRE d'atteignabilite (jamais bloquant, mais il doit MESURER) ---
def test_e6_l_inventaire_d_atteignabilite_est_NON_VIDE():
    """Il rend `0` par construction -- ce qu'on garde, c'est qu'il ne mesure pas le VIDE.

    Un recenseur qui ne visiterait plus rien rendrait `0` lui aussi et se lirait « rien a
    signaler » ; l'etage rougit sur son propre ensemble vide, et ce test le joue."""
    assert P.etage6_atteignabilite_multi_unites() == 0


