"""#10024 -- CLIQUET : le slot 2 d'`IBattleQuery` compare des EMPREINTES, jamais des MAIN TILES.

Ce que ce fichier garde, et qu'aucune mesure de degat ne garde : le port comparait
`casterPosition.MainTile` a `target.MainTile`, la ou le natif compare l'EMPREINTE COMPLETE des
deux entites. Quatre lectures du build `t6dpr4k06g` l'etablissent, et chacune a son etage ici :

  1. `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack(ability, caster, casterPosition, target)`
     -- le 3e parametre est type `IdunBattle.Core.UnitPosition` (signature LUE dans
     `data/symbols/<build>/frida/methods.tsv`) ;
  2. `IdunBattle.Core.UnitPosition` est un `System.ValueType` a UN champ, une `List<IEntity>` :
     `$$.ctor(tile)` construit la liste et n'y ajoute la tuile que si elle est non nulle,
     `$$get_MainTile` rend `list[0]`, `$$IsEmpty` est `MainTile == null`, `$$NullPosition` rend la
     liste VIDE ;
  3. le corps d'`IsMeleeAttack` passe ce parametre TEL QUEL a la surcharge
     `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent(tiles:IList<IEntity>, unit:IEntity)`
     (xref LUE ; `$$IsRangedAttack` et les DEUX sites de `$$GetAttackRangeType` appellent la MEME),
     dont le corps est `tiles2 = EntityExtensions.GetTiles(unit, state); return
     MovementUtil.AreTilesAdjacent(tiles, tiles2);` -- un OU sur TOUTES les paires ;
  4. `IdunBattle.Entities.EntityExtensions$$GetUnitPosition(unit, state)` -- ce que passe tout
     appelant sans ancre d'ability -- a pour corps ENTIER `return GetTiles(unit, state);`.

REGIME MESURE (`probe_10024_empreinte_is_melee.py --volet geometrie`, 24 boards dumpes, 5 322
empreintes 3-hex) : **20 644** configurations ou le natif accorde l'adjacence contre **16 820** ou
les deux modeles s'accordent -- 55 % de la couronne etait perdue. CONFRONTATION LIVE (runner 702,
Galatian pose par `DutyEternal`, pieds (0,3)(0,4)(1,4)) : depuis (2,3), distance 2 de la MAIN TILE
et 1 d'un pied, le natif rend `isMeleeAttack = True` (`ncPlaybookPredict.gates`), le port d'AVANT
rendait `False`.

⚠ CHAQUE ETAGE PORTE SA CONTRE-EPREUVE : le regime MAIN TILE est rejoue TEL QUEL a cote et doit
DIVERGER. Sans ce cran, un montage ou les deux coincident rendrait le test vert sans rien prouver.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PYDIR = Path(__file__).resolve().parents[3]                  # scripts/python
sys.path.insert(0, str(PYDIR))

from engine import battle_query as _bq                                       # noqa: E402
from engine.runner import battle_query_state as BQS                          # noqa: E402
from engine.runner.components import (PositionComponent, StatsComponent,     # noqa: E402
                                      get_unit_feet, set_unit_feet)
from engine.runner.state import State                                        # noqa: E402
from engine.services import battle_query as SBQ                              # noqa: E402

DECLENCHEUR = {
    "chemins": (),
    "build": False,
    "toujours": False,
    "raison": "RIEN a declarer hors de la cascade DERIVEE (#531) : `probe_486r15 --proposer` rend "
              "une fermeture d'imports de 749 modules qui contient DEJA les quatre foyers que ce "
              "fichier garde -- `engine/services/battle_query.py` (le switch du slot 2 et de ses "
              "deux freres), `engine/battle_query.py` (la primitive `AreTilesAdjacent` scalaire), "
              "`engine/runner/battle_query_state.py` (le montage de substrat runner) et "
              "`engine/runner/components.py` (`get_unit_feet` = `EntityExtensions$$GetTiles`). "
              "Les redeclarer ferait du bruit sans rien ajouter. `build: False` : ce fichier ne "
              "lit AUCUNE entree gameconfig ni `data/symbols/**` -- toutes ses abilities sont "
              "`None` (branche `Normal(3)`) ou substituees par `monkeypatch`, et sa geometrie est "
              "un litteral (`FEET_3HEX`), pas un board dumpe.",
}

#: Empreinte TEMOIN : trois tuiles mutuellement adjacentes en colonne/diagonale, la forme que
#: `DutyEternal` pose au sol (i2 : << a 3 hex area >>) et celle MESUREE live sur Galatian.
#: `feet[0]` est la main tile (`UnitPosition$$get_MainTile` = `list[0]`).
FEET_3HEX = [(0, 3), (0, 4), (1, 4)]


def _ctx():
    """`UnitContext` reduit : ce fichier mesure un AIGUILLAGE GEOMETRIQUE, aucune stat n'est lue."""
    return SimpleNamespace(visual_id=None, normal_hits=None, traits=(),
                           extra_pierce=0, extra_pierce_melee=0, extra_pierce_ranged=0,
                           passive_abilities=[], active_abilities=[],
                           config_active_abilities=None)


def _state(apos: tuple, cible_feet) -> State:
    """Un caster MONO-tuile en `apos`, une cible dont on pose l'EMPREINTE via l'ecrivain unique
    (`set_unit_feet`, mirror de la boucle de pose d'`AddUnitOperation$$Execute`)."""
    st = State()
    a = st.add_entity(1)
    a.add_component(StatsComponent(_ctx()))
    a.add_component(PositionComponent(apos[0], apos[1]))
    t = st.add_entity(2)
    t.add_component(StatsComponent(_ctx()))
    t.add_component(PositionComponent(cible_feet[0][0], cible_feet[0][1]))
    if len(cible_feet) > 1:
        set_unit_feet(st, 2, list(cible_feet))
    return st


# --------------------------------------------------------------------------------------------
# ETAGE 1 -- `as_unit_position` est le mirror d'`IdunBattle.Core.UnitPosition`.
# --------------------------------------------------------------------------------------------

def test_etage1_unit_position_ctor_dune_tuile():
    """`UnitPosition$$.ctor(tile)` : une `List` neuve, la tuile ajoutee si non nulle."""
    assert SBQ.as_unit_position((3, 7)) == [(3, 7)]


def test_etage1_unit_position_dune_empreinte():
    """`EntityExtensions$$GetTiles` : la liste telle quelle, DANS L'ORDRE des pieds."""
    assert SBQ.as_unit_position(FEET_3HEX) == FEET_3HEX
    assert SBQ.as_unit_position(FEET_3HEX)[0] == (0, 3), "feet[0] EST la main tile"


def test_etage1_null_position_est_une_liste_vide():
    """`UnitPosition$$NullPosition` rend une `List` VIDE -- et `AreTilesAdjacent(IList, IList)`
    rend alors FAUX par boucle vide, jamais une levee."""
    assert SBQ.as_unit_position(None) == []
    assert SBQ.as_unit_position([]) == []
    assert SBQ.are_entities_adjacent(None, FEET_3HEX) is False
    assert SBQ.are_entities_adjacent(FEET_3HEX, []) is False


def test_etage1_une_tuile_nulle_nest_pas_ajoutee():
    """`$$.ctor` teste `tile != null` avant `Add` -- une entree nulle ne peuple pas la liste."""
    assert SBQ.as_unit_position([(0, 1), None, (0, 2)]) == [(0, 1), (0, 2)]


@pytest.mark.parametrize("entree,attendu", [
    # les DEUX formes de tuile que le port produit -- COUPLE (face COMBAT,
    # `runner.components.get_unit_feet`) et DICT (face DECISION, `decisionView.units[].feet`,
    # forme de `readTileCoord`). C'est la seconde qui avait fait LEVER `dsl/base.py::_feet`
    # (`KeyError: 0`) quand le capteur `#419-r1-tr10-r2` a ouvert le canal.
    ({"col": 1, "row": 2}, [(1, 2)]),
    ([{"col": 1, "row": 2}, {"col": 1, "row": 3}], [(1, 2), (1, 3)]),
    # une forme INCONNUE est SAUTEE, jamais devinee : sans ce refus, `list("ab")` fabriquerait la
    # tuile `('a', 'b')` -- un couple plausible qui ne designe rien.
    ("ab", []),
    (["ab", "cd"], []),
    ([(0, 1), "ab", (0, 2)], [(0, 1), (0, 2)]),
    ({"col": None, "row": 2}, []),
    ([True, False], []),                  # un bool n'est pas une coordonnee
    ((0,), []),                           # un couple incomplet n'est pas une tuile
])
def test_etage1_les_formes_de_tuile_et_les_refus(entree, attendu):
    assert SBQ.as_unit_position(entree) == attendu


# --------------------------------------------------------------------------------------------
# ETAGE 2 -- les TROIS slots freres lisent l'EMPREINTE, avec la contre-epreuve MAIN TILE.
# --------------------------------------------------------------------------------------------

#: La tuile qui SEPARE les deux modeles : distance 2 de `FEET_3HEX[0]`, distance 1 de `(1,4)`.
TUILE_DISCRIMINANTE = (2, 3)
#: TEMOIN NEGATIF : distance >= 2 de TOUS les pieds -- les deux modeles doivent dire FAUX.
TUILE_LOIN = (1, 2)
#: TEMOIN POSITIF : adjacente a la MAIN TILE -- les deux modeles doivent dire VRAI.
TUILE_CONTACT = (0, 2)


def test_etage2_le_montage_est_bien_discriminant():
    """Assertionner son propre NON-VIDE : si la geometrie temoin ne separait pas les deux modeles,
    tous les etages qui suivent passeraient sans rien prouver."""
    main = FEET_3HEX[0]
    assert not _bq.are_entities_adjacent(TUILE_DISCRIMINANTE, main), (
        "la tuile discriminante DOIT etre non adjacente a la main tile")
    assert any(_bq.are_entities_adjacent(TUILE_DISCRIMINANTE, f) for f in FEET_3HEX[1:]), (
        "la tuile discriminante DOIT etre adjacente a un pied NON principal")
    assert not any(_bq.are_entities_adjacent(TUILE_LOIN, f) for f in FEET_3HEX), (
        "le temoin negatif DOIT etre loin de TOUS les pieds")
    assert _bq.are_entities_adjacent(TUILE_CONTACT, main), (
        "le temoin positif DOIT etre adjacent a la main tile")


@pytest.mark.parametrize("tuile,attendu", [
    (TUILE_DISCRIMINANTE, True),      # #10024 : le natif accorde, l'ancien port refusait
    (TUILE_CONTACT, True),
    (TUILE_LOIN, False),
])
def test_etage2_is_melee_attack_lit_lempreinte(tuile, attendu):
    assert SBQ.is_melee_attack(None, tuile, FEET_3HEX) is attendu


def test_etage2_contre_epreuve_le_regime_main_tile_diverge():
    """Le port d'AVANT #10024, rejoue LITTERALEMENT (deux tuples = deux main tiles). Il DOIT
    diverger sur la tuile discriminante -- sinon l'etage precedent ne mesure rien."""
    avant = SBQ.is_melee_attack(None, TUILE_DISCRIMINANTE, FEET_3HEX[0])
    apres = SBQ.is_melee_attack(None, TUILE_DISCRIMINANTE, FEET_3HEX)
    assert avant is False and apres is True, (
        "regime MAIN TILE attendu FAUX et regime EMPREINTE attendu VRAI -- mesure %r / %r"
        % (avant, apres))


@pytest.mark.parametrize("tuile,attendu", [
    (TUILE_DISCRIMINANTE, False),     # frere du slot 2 : `!AreEntitiesAdjacent` sur `Normal(3)`
    (TUILE_CONTACT, False),
    (TUILE_LOIN, True),
])
def test_etage2_is_ranged_attack_lit_la_meme_empreinte(tuile, attendu):
    """`$$IsRangedAttack` appelle LA MEME surcharge `AreEntitiesAdjacent(tiles, unit)` (xref lue).
    Ce n'est PAS la negation de son frere -- ils divergent sur `None(0)` -- mais sur `Normal(3)`
    ils lisent la meme geometrie."""
    assert SBQ.is_ranged_attack(None, tuile, FEET_3HEX) is attendu


@pytest.mark.parametrize("tuile,attendu", [
    (TUILE_DISCRIMINANTE, "Melee"),
    (TUILE_CONTACT, "Melee"),
    (TUILE_LOIN, "Ranged"),
])
def test_etage2_get_attack_range_type_lit_la_meme_empreinte(tuile, attendu):
    """TROISIEME frere (`$$GetAttackRangeType`, slot 4) -- ses DEUX sites d'appel visent la meme
    surcharge. Il rend le MEMBRE, pas un booleen."""
    assert SBQ.get_attack_range_type(None, tuile, FEET_3HEX) == attendu


def test_etage2_les_branches_non_normal_ne_lisent_aucune_position(monkeypatch):
    """Les cases `Melee(1)` / `Ranged(2)` / `None(0)` du switch natif ne consultent AUCUNE
    geometrie -- la correction d'empreinte ne doit pas les avoir ouvertes."""
    for rt, attendu in (("Melee", True), ("Ranged", False), ("None", False)):
        monkeypatch.setattr("engine.services.battle_query.attack_range_type", lambda _n, _r=rt: _r)
        assert SBQ.is_melee_attack("PeuImporte", TUILE_LOIN, FEET_3HEX) is attendu


# --------------------------------------------------------------------------------------------
# ETAGE 3 -- le SUBSTRAT runner : `unit_tiles` est `GetUnitPosition`, c.-a-d. `GetTiles`.
# --------------------------------------------------------------------------------------------

def test_etage3_unit_tiles_rend_lempreinte_complete():
    st = _state(TUILE_DISCRIMINANTE, FEET_3HEX)
    assert BQS.unit_tiles(st, 2) == FEET_3HEX
    assert get_unit_feet(st, 2) == FEET_3HEX, "meme foyer : `unit_tiles` DELEGUE, il ne re-derive pas"


def test_etage3_unit_position_reste_la_main_tile():
    """`unit_position` n'est PAS `GetUnitPosition` : c'est `get_MainTile` applique a son resultat.
    Il reste pour les appelants qui veulent une tuile unique -- et hors du chemin du predicat."""
    st = _state(TUILE_DISCRIMINANTE, FEET_3HEX)
    assert BQS.unit_position(st, 2) == FEET_3HEX[0]


def test_etage3_une_unite_mono_tuile_rend_un_seul_pied():
    """Le cas NOMINAL : `UnitComponent.feet` n'est pas materialise, `GetTiles` rend la seule tuile
    de la `PositionComponent`. La correction est un STRICT no-op sur ces unites."""
    st = _state(TUILE_DISCRIMINANTE, [(0, 3)])
    assert BQS.unit_tiles(st, 2) == [(0, 3)]


def test_etage3_entite_sans_position_rend_une_liste_vide():
    """`GetUnitFeetIds` sur une entite qui n'est pas une unite rend une liste vide -> le predicat
    rend FAUX par boucle vide, jamais une levee."""
    st = State()
    st.add_entity(9)
    assert BQS.unit_tiles(st, 9) == []
    assert BQS.is_melee_attack(st, None, 9, 9) is False


# --------------------------------------------------------------------------------------------
# ETAGE 4 -- CABLAGE : le predicat runner passe-t-il VRAIMENT par l'empreinte ?
# Une valeur juste dans le foyer qui n'arriverait pas au montage serait un fix INVISIBLE.
# --------------------------------------------------------------------------------------------

def test_etage4_le_predicat_runner_accorde_par_un_pied_non_principal():
    st = _state(TUILE_DISCRIMINANTE, FEET_3HEX)
    assert BQS.is_melee_attack(st, None, 1, 2) is True, (
        "le caster est a distance 2 de la MAIN TILE de la cible et 1 de son 3e pied -- "
        "`AreEntitiesAdjacent(casterPosition, target)` rend VRAI")


def test_etage4_temoin_negatif_du_predicat_runner():
    st = _state(TUILE_LOIN, FEET_3HEX)
    assert BQS.is_melee_attack(st, None, 1, 2) is False


def test_etage4_la_mutation_de_unit_tiles_MORD(monkeypatch):
    """CONTRE-EPREUVE DE CABLAGE, par mutation : on rabat `unit_tiles` sur la main tile -- ce que
    faisait litteralement le port d'AVANT -- et le verdict DOIT basculer. S'il ne bougeait pas,
    c'est que le predicat lit encore autre chose que l'empreinte."""
    st = _state(TUILE_DISCRIMINANTE, FEET_3HEX)
    assert BQS.is_melee_attack(st, None, 1, 2) is True
    monkeypatch.setattr(BQS, "unit_tiles",
                        lambda state, uid: ([BQS.unit_position(state, uid)]
                                            if BQS.unit_position(state, uid) else []))
    assert BQS.is_melee_attack(st, None, 1, 2) is False, (
        "la mutation MAIN TILE n'a pas mordu -- le predicat ne passe pas par `unit_tiles`")


def test_etage4_la_mutation_est_inerte_sur_une_unite_mono_tuile(monkeypatch):
    """La MEME mutation ne doit RIEN changer quand la cible n'a qu'un pied : c'est ce qui etablit
    que la correction ne touche que les entites multi-hex."""
    st = _state(TUILE_CONTACT, [(0, 3)])
    avant = BQS.is_melee_attack(st, None, 1, 2)
    monkeypatch.setattr(BQS, "unit_tiles",
                        lambda state, uid: ([BQS.unit_position(state, uid)]
                                            if BQS.unit_position(state, uid) else []))
    assert BQS.is_melee_attack(st, None, 1, 2) is avant is True


# --------------------------------------------------------------------------------------------
# ETAGE 5 -- l'INVARIANT du regime : l'empreinte DOMINE la main tile, jamais l'inverse.
# Pas un seuil (un seuil se degrade en silence) : une propriete d'ordre, vraie sur tout board.
# --------------------------------------------------------------------------------------------

def test_etage5_lempreinte_domine_toujours_la_main_tile():
    """`MovementUtil$$AreTilesAdjacent(IList, IList)` est un OU sur les paires, et la paire des
    main tiles EN FAIT PARTIE : le verdict EMPREINTE ne peut jamais etre plus restrictif. Balaye
    une couronne complete autour de l'empreinte temoin, et EXIGE que la divergence soit non vide."""
    main = FEET_3HEX[0]
    zone = [(c, r) for c in range(-2, 5) for r in range(0, 8) if (c, r) not in FEET_3HEX]
    accord = divergent = 0
    for cible in zone:
        a = SBQ.is_melee_attack(None, cible, main)
        b = SBQ.is_melee_attack(None, cible, FEET_3HEX)
        assert not (a and not b), (
            "INVERSION IMPOSSIBLE en %r : le regime main tile accorde ce que l'empreinte refuse"
            % (cible,))
        if a and b:
            accord += 1
        elif b:
            divergent += 1
    assert accord > 0 and divergent > 0, (
        "regime DEGENERE (accord=%d divergents=%d) -- ce balayage ne prouverait rien"
        % (accord, divergent))
