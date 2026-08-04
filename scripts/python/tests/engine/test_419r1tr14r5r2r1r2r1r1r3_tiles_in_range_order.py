"""#419-r1-tr14-r5-r2-r1-r2-r1-r1-r3 -- l'ORDRE des deux tests de `GetTilesInRange`.

`IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange` teste `(int)range == 0` **AVANT**
`range._4_1_ OnlyAdjacent` et rend alors `casterTiles` (rayon 0), pas les tuiles adjacentes
(rayon 1). Le port testait dans l'autre ordre.

Ce que ces crans gardent :

  1. **L'ORDRE**, sur un `TargetingRange` SYNTHETIQUE -- le seul cran qui puisse ROUGIR, puisque le
     gisement REEL est vide (cran 3). Sans lui, le garde-fou serait un inventaire.
  2. **LE CONTRE-CRAN** : le port ne doit pas rendre `0` partout. Portee 1 + `OnlyAdjacent` -> 1,
     et `RANGE_SELF` (portee 0, `OnlyAdjacent` faux) -> 0 comme avant.
  3. **LE GISEMENT EST VIDE, ET C'EST UNE MESURE** : aucune ability RE-lue ne combine une portee
     nulle avec un gate d'adjacence arme. Le correctif est donc un MIRROR STRUCTUREL -- port fidele
     NON CONFRONTE live, et non un bug corrige. Si ce cran rougit un jour, c'est qu'une ability
     neuve a ouvert le regime : il faut alors le CONFRONTER, pas ajuster le chiffre.
  4. **L'ETAGE JUMEAU N'EST TOUJOURS PAS ALIGNE SUR `get_range`** : le `None` de
     `tiles_in_range_reach` sur une portee NON OBSERVABLE reste. C'est le piege pose par #587 --
     ici la valeur est lue AVANT `OnlyAdjacent`, donc sans elle on ne sait pas quelle branche
     prendre. Le cran est REDONDANT avec celui de
     `test_419r1tr14r5r2r1r2r1r1_only_adjacent_live.py`, et c'est voulu : la tentation de
     l'alignement vit desormais dans CE fichier-ci.

RE et mesures : `docs/rl/case-419-r1-tr14-r5-r2-r1-r2-r1-r1-only-adjacent-portee-non-observable.md`.
Probe jumeau : `probe_419r1tr14r5r2r1r2r1r1r3_tiles_in_range_order.py`. ASCII only.
"""
from __future__ import annotations

import probe_419r1tr14r5r2r1r2r1r1r3_tiles_in_range_order as P
from engine.services import ability_range as AR
from engine.runner.abilities.targeting import (RANGED_BOOL_FALSE, RANGED_BOOL_TRUE,
                                               TargetingRange)


def _reach(rng, vis):
    with P._Synth(rng):
        return AR.tiles_in_range_reach(P._SYNTH_ID, vis)


def test_portee_nulle_lemporte_sur_only_adjacent():
    """(1) `{onlyAdjacent = True, overrideRange = 0}` -> rayon **0** (`casterTiles`), pas 1."""
    vis = P._catalogue()[0]
    got = _reach(TargetingRange(only_adjacent=RANGED_BOOL_TRUE, override_range=0), vis)
    assert got == 0, (
        "`GetTilesInRange` teste `(int)range == 0` AVANT `OnlyAdjacent` et rend `casterTiles` ; "
        f"le port rend {got}")


def test_le_contre_cran_le_port_ne_rend_pas_zero_partout():
    """(2) Une portee NON nulle avec `OnlyAdjacent` doit toujours rendre 1, et `RANGE_SELF` doit
    rester a 0 : la correction d'ordre ne doit ni ecraser la branche d'adjacence, ni changer le
    statu quo de la portee nulle non adjacente."""
    vis = P._catalogue()[0]
    assert _reach(TargetingRange(only_adjacent=RANGED_BOOL_TRUE, override_range=1), vis) == 1
    assert _reach(TargetingRange(only_adjacent=RANGED_BOOL_FALSE, override_range=0), vis) == 0


def test_le_gisement_reel_est_vide_et_cest_une_mesure():
    """(3) Le balayage `abilities RE-lues x catalogue` : perimetre NON vide, et **0** couple
    deplace. C'est ce qui justifie l'etiquette « mirror structurel NON CONFRONTE »."""
    aids, cat = P._ability_ids(), P._catalogue()
    assert len(aids) >= 50 and len(cat) >= 100, "perimetre trop maigre pour garder quoi que ce soit"
    resolus = deplaces = 0
    for aid in aids:
        for vis in cat:
            got = P._resolved_range(aid, vis)
            if got is None:
                continue
            resolus += 1
            ov, adj = got
            deplaces += int(ov == 0 and adj)
    assert resolus > 1000, f"seulement {resolus} couples resolus -- substrat suspect"
    assert deplaces == 0, (
        f"{deplaces} couple(s) (ability, unite) combinent une portee NULLE et un gate d'adjacence "
        "arme : le regime est desormais ATTEIGNABLE -> il doit etre CONFRONTE live, pas chiffre")


def test_letage_jumeau_reste_none_sur_portee_non_observable():
    """(4) Le piege de #587, garde ICI aussi : `tiles_in_range_reach` doit RESTER `None` quand la
    portee d'arme n'est pas observable -- surtout pas le tri-etat de `get_range`."""
    import probe_419r1tr14r5r2r1r2r1r1_range_only_adjacent as PR
    assert PR.jumeau_toujours_none() is True
