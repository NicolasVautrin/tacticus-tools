"""#433-r4-r3-r1-r3 -- le kit DECLENCHE d'un VOISIN est REMPLACE par la mesure, jamais unionne.

CE QUE CE FICHIER FIGE, ET POURQUOI IL EST NEUF. `engine/utilities/tile.py::_adjacent_units` etait
le DERNIER des trois jumeaux a UNIONNER le kit gameconfig avec la lecture live du
`TriggeredAbilityComponent`. Le MOVER est passe au remplacement par #304 et les deux autres
jumeaux (`runner_tile_leaf_ctx`, `scene_tile_leaf_ctx`, tous deux via le foyer
`entities.triggered_ability_type.entity_triggered_ability_ids`) par #456-r1 -- sur la meme mesure :
une union ne peut qu'AJOUTER, donc elle REINTRODUIT un passif que la bataille n'a PAS monte.

Le defaut ne se voit QUE la ou un montage ECARTE le kit gameconfig, c'est-a-dire sur une GREFFE.
MESURE LIVE (2026-08-15, `t6dpr4k06g`, montage #433-r4-r3-r1 :
`catalog_inject.graft_passive_ability('astraBullgryn', 'WatchedOver', replace=True)`) :

    avant   kit greffon -- port = [1028, 1524, 1030]   AbilitiesComponent NATIF = [1524, 1030]
    apres   kit greffon -- port = [1524, 1030]         AbilitiesComponent NATIF = [1524, 1030]

`1028` = `AvalancheOfMuscle`, le passif de kit que la greffe avait justement REMPLACE dans
`BC.Units[].PassiveAbilities`.

CE QUI EST GARDE -- et les deux sens comptent :

  1. la mesure REMPLACE (elle peut donc RETIRER un id du kit) ;
  2. une mesure VIDE pour cette entite laisse le kit gameconfig ENTIER (c'est le seul regime que
     le motif d'union protegeait, et il ne doit pas etre perdu) ;
  3. la table est lue PAR ENTITE : un voisin mesure et un voisin non mesure coexistent sans que
     l'un contamine l'autre ;
  4. le MOVER et ses VOISINS suivent la MEME regle dans le MEME producteur -- c'est l'asymetrie
     qui avait laisse le defaut vivre un an de tranches.

100 % OFFLINE (aucun runner, aucun RPC) : le `ctx` est un double minimal qui expose exactement les
attributs que `tile_leaf_ctx` lit. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PY = Path(__file__).resolve().parents[2]
if str(_PY) not in sys.path:
    sys.path.insert(0, str(_PY))

from engine.entities.triggered_ability_type import (TriggeredAbilityType,   # noqa: E402
                                                    triggered_ability_ids)
from engine.utilities.tile import tile_leaf_ctx                             # noqa: E402

#: Le greffon du montage #433-r4-r3-r1. Son kit gameconfig ne porte QUE `AvalancheOfMuscle`.
GREFFON = "astraBullgryn"
KIT_ID = int(TriggeredAbilityType.AvalancheOfMuscle)        # 1028
GREFFE = int(TriggeredAbilityType.WatchedOver)              # 1524
DERIVE = int(TriggeredAbilityType.BigTarget)                # 1030 -- accorde par le TRAIT BigTarget


class _Ctx:
    """Double minimal d'`AiDecisionContext` -- exactement les attributs que `tile_leaf_ctx` lit."""

    def __init__(self, units, kits, uid=1):
        self.units = units
        self.uid = uid
        self.me = next((u for u in units if u.get("id") == uid), {})
        self.scene = None
        self.hpmax_by_id = {}
        # `fpos` est le SEUL attribut que `tile_leaf_ctx` lit sans `getattr` -- un double qui
        # l'oublie tombe en `AttributeError` au lieu de mesurer.
        self.fpos = [(u["pos"]["col"], u["pos"]["row"]) for u in units
                     if u.get("ctrl") and u.get("id") != uid]
        self._kits = kits

    def live_triggered_kits(self):
        """La table COMPLETE -- ce que lit `_adjacent_units` (les VOISINS)."""
        return self._kits

    def live_triggered_ability_ids(self, unit_id):
        """La lecture PAR-UNITE -- ce que lit `tile_leaf_ctx` pour le MOVER. Le vrai
        `AiDecisionContext` alimente le MEME cache `(rid, unitId)` par les deux voies (cf. sa
        docstring), donc les servir depuis la meme table est le double FIDELE : les faire diverger
        ici fabriquerait une asymetrie que le code n'a pas."""
        return list(self._kits.get(int(unit_id)) or ())


def _voisin(uid: int, vis: str, ctrl: bool = True) -> dict:
    return {"id": uid, "visualId": vis, "alive": True, "ctrl": ctrl,
            "pos": {"col": 1, "row": 1}, "hp": 10, "effects": ()}


def _mover(uid: int = 1) -> dict:
    return {"id": uid, "visualId": "darkaAzrael", "alive": True, "ctrl": True,
            "pos": {"col": 0, "row": 0}, "hp": 10, "effects": ()}


def _kit_du_voisin(ctx, uid: int) -> tuple:
    leaf = tile_leaf_ctx(ctx)
    for u in ((leaf.get("friend_units") or []) + (leaf.get("enemy_units") or [])):
        if u.get("id") == uid:
            return tuple(u.get("triggered") or ())
    raise AssertionError("le voisin %d n'est dans aucune des deux listes" % uid)


def test_le_kit_gameconfig_du_greffon_est_bien_celui_qu_on_croit():
    """TEMOIN NON DEGENERE : sans cette ligne, un `[]` des deux cotes ferait passer les tests
    suivants sans rien mesurer."""
    kit = triggered_ability_ids(GREFFON)
    assert kit == [KIT_ID], kit
    assert GREFFE not in kit and DERIVE not in kit


def test_la_mesure_REMPLACE_le_kit_du_voisin():
    """(1) LE POINT DU RESIDU. La greffe a retire `AvalancheOfMuscle` de `BC.Units[]`, donc
    l'`AbilitiesComponent` ne le porte plus -- et le port ne doit plus le voir."""
    ctx = _Ctx([_mover(), _voisin(83, GREFFON)], {83: [GREFFE, DERIVE]})
    got = _kit_du_voisin(ctx, 83)
    assert got == (GREFFE, DERIVE), got
    assert KIT_ID not in got, (
        "le kit gameconfig est REINTRODUIT par union -- c'est exactement le defaut mesure live : "
        "port=[1028, 1524, 1030] contre AbilitiesComponent natif=[1524, 1030]")


def test_une_mesure_VIDE_laisse_le_kit_gameconfig_ENTIER():
    """(2) Le seul regime que le motif d'union protegeait : RPC indisponible, entite absente de la
    table, contexte offline sans pont. Le repli doit rester INTACT -- sinon on remplacerait une
    reintroduction par une AMPUTATION, qui est le defaut symetrique."""
    for kits in ({}, {83: []}, {84: [GREFFE]}):
        ctx = _Ctx([_mover(), _voisin(83, GREFFON)], kits)
        assert _kit_du_voisin(ctx, 83) == (KIT_ID,), (kits, _kit_du_voisin(ctx, 83))


def test_la_table_est_lue_PAR_ENTITE():
    """(3) Deux voisins de MEME `visualId`, un mesure et un non : le remplacement ne doit toucher
    que celui qui est mesure. Une lecture par `visualId` les confondrait -- et c'est precisement
    ce que le kit gameconfig fait, d'ou le risque."""
    ctx = _Ctx([_mover(), _voisin(83, GREFFON), _voisin(84, GREFFON)], {83: [GREFFE]})
    assert _kit_du_voisin(ctx, 83) == (GREFFE,)
    assert _kit_du_voisin(ctx, 84) == (KIT_ID,)


def test_les_ENNEMIS_suivent_la_meme_regle_que_les_AMIS():
    """Le tri ami/ennemi ne doit pas changer la SOURCE du kit -- les deux listes sont bâties par la
    meme boucle, et un jour ou elles divergeraient, une feuille a gate d'ennemi lirait un kit
    perime sans que rien ne le dise."""
    ctx = _Ctx([_mover(), _voisin(83, GREFFON, ctrl=False)], {83: [GREFFE, DERIVE]})
    assert _kit_du_voisin(ctx, 83) == (GREFFE, DERIVE)


def test_le_MOVER_et_ses_VOISINS_suivent_la_MEME_regle():
    """(4) L'ASYMETRIE qui avait laisse le defaut vivre : le mover etait passe au remplacement
    (#304), ses voisins non. On assertionne l'egalite de traitement DANS LE MEME producteur, sur le
    MEME `visualId` et la MEME mesure -- si l'un des deux repart en union, ce test le dit."""
    ctx = _Ctx([_mover(), _voisin(83, GREFFON)], {1: [GREFFE], 83: [GREFFE]})
    leaf = tile_leaf_ctx(ctx)
    assert tuple(leaf["unit_triggered_abilities"]) == (GREFFE,), leaf["unit_triggered_abilities"]
    assert _kit_du_voisin(ctx, 83) == (GREFFE,)
