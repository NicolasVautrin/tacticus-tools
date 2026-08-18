"""GARDE #448-r7 (OFFLINE PURE) -- `+0x88` SURVIT au retrait de plateau, comme son jumeau `+0x98`.

## L'ecart, et pourquoi c'est un probleme d'EMPLACEMENT et non d'ECRITURE

`IdunBattle.Operations.SetUnitPositionOperation$$SavePreviousPosition` ecrit DEUX
`Nullable<UnitPositionId>` avec la MEME valeur, et le decompile de
`IdunBattle.Operations.RemoveUnitFromTilesOperation$$Execute` montre qu'ils vivent sur le MEME
composant : les deux ecritures resolvent leur composant par le MEME `GetComponent<...>` et deposent
le MEME `UnitPositionId`, construit une seule fois --

    *(comp + 0x88) = Nullable(id)        <- `PreviousTile`
    *(comp + 0x98) = Nullable(id)        <- `GetPreviousPositionThisTurn`

Ce composant est le `MovementComponent`, et le retrait de plateau **ne le touche pas** (il ne met a
zero que les `TileId` des pieds).

Cote port, `+0x98` etait deja sur le `UnitComponent` (#1082), mais `+0x88` etait reste sur la
`PositionComponent` -- que `set_unit_feet(uid, [])` **SUPPRIME**. L'ecriture etait donc JUSTE, et
aucun `write` n'etait fautif : c'est le PORTEUR du champ qui le faisait disparaitre.

## Ce que ce fichier NE pretend PAS

**Aucun vecteur observable n'est etabli**, et c'est un resultat mesure, pas un aveu. Le seul
consommateur porte de `PreviousTileSelector` est `HaywireMineAbility$$CreateBehaviour`
(`AmountIsGreaterThanZero(PreviousTile(Owner))` en garde, puis `CanAddUnit(PreviousTile(Owner))`
comme tuile de pose), et son `Owner` est SUR le plateau au moment du cast -- il vient d'y bouger.
Le regime << porteur retire du plateau PUIS interroge sur sa tuile precedente >> n'a donc aucun
appelant porte aujourd'hui. Le correctif est de FIDELITE STRUCTURELLE : il ferme le canal avant
qu'un consommateur ne l'emprunte, et ce fichier fige le fait.

ASCII only (console cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.components import (PositionComponent, UnitComponent,    # noqa: E402
                                      previous_tiles, save_previous_position,
                                      set_unit_feet)
from engine.runner.snapshot import load_state                              # noqa: E402

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/operations/remove_unit_from_tiles.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/entities/selectors/tiles.py",
    ),
    "build": False,
    "toujours": False,
    "raison": ("100 % offline : la lecture native (`SavePreviousPosition` ecrit `+0x88` et `+0x98` "
               "sur le MEME composant, que le retrait de plateau ne touche pas) est gravee par les "
               "docstrings du foyer ; ce fichier mesure le PORT."),
}

COLS, ROWS, UID = 5, 5, 30
AVANT = [(1, 1)]


def _state():
    import hexgeo
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [c * ROWS + r + 1 for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": col * ROWS + row + 1, "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    decision = {"currentPlayer": 1, "units": [
        {"id": UID, "visualId": "orksNob", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 2, "row": 2}, "effects": []}]}
    observe = {"units": [{"squadId": UID, "hp": 1000, "hpMax": 1000}]}
    return load_state(decision, observe, board=Board(tiles, adjacency="evenq"))


# --------------------------------------------------------------- etage 1 : LE FIX

def test_le_retrait_de_plateau_CONSERVE_la_position_precedente():
    """LE FIX. `set_unit_feet(uid, [])` retire l'unite du plateau (il SUPPRIME la
    `PositionComponent`), et `PreviousTileSelector` doit continuer de rendre la tuile QUITTEE --
    c'est ce que fait le natif, dont le `MovementComponent` n'est pas touche par ce retrait."""
    st = _state()
    assert save_previous_position(st, UID, AVANT) is True
    ent = st.get_entity(UID)
    assert previous_tiles(ent) == AVANT, "montage : l'ecriture n'a pas pris"

    set_unit_feet(st, UID, [])                       # retrait du plateau

    assert ent.get_component(PositionComponent) is None, (
        "montage DEGENERE : la `PositionComponent` n'a pas ete supprimee, donc ce test ne mesure "
        "pas le regime du residu")
    assert previous_tiles(ent) == AVANT, (
        "la position precedente a ete DETRUITE par le retrait de plateau : %s"
        % previous_tiles(ent))


def test_le_champ_ne_vit_PLUS_sur_la_PositionComponent():
    """INVARIANT STRUCTUREL : le champ a bien DEMENAGE, il n'est pas duplique.

    Une duplication laisserait le test precedent vert tout en gardant une copie que le retrait
    detruit -- et un futur lecteur pourrait consulter la mauvaise."""
    assert "previous" not in PositionComponent.__slots__, PositionComponent.__slots__
    assert "previous_position" in UnitComponent.__slots__


def test_les_deux_slots_recoivent_la_MEME_valeur():
    """`SavePreviousPosition` ecrit `+0x88` et `+0x98` avec le MEME `UnitPositionId`, construit une
    seule fois. Ils ne divergent qu'aux remises a zero."""
    st = _state()
    save_previous_position(st, UID, AVANT)
    uc = st.get_entity(UID).get_component(UnitComponent)
    assert uc.previous_position == AVANT
    assert uc.previous_position_this_turn == AVANT
    # ... mais ce sont DEUX copies, et il faut le mesurer par une mutation EN PLACE.
    # ⚠ UNE PREMIERE VERSION FAISAIT `uc.previous_position_this_turn = None` : ca REBINDE le nom, ca
    # ne mute pas la liste -- l'assertion passait meme quand les deux slots partageaient le MEME
    # objet (mutant joue : il NE MORDAIT PAS). Le seul geste qui distingue partage et copie est la
    # mutation de l'objet lui-meme.
    assert uc.previous_position is not uc.previous_position_this_turn, (
        "les deux slots sont le MEME objet -- toute mutation en place de l'un emporterait l'autre")
    uc.previous_position_this_turn.append((9, 9))
    assert uc.previous_position == AVANT, (
        "muter `+0x98` a modifie `+0x88` : les deux slots partagent leur liste, alors que leurs "
        "remises a zero sont distinctes (`StartTurnOperation` n'efface que `+0x98`)")


# ------------------------------------------- etage 2 : LE REGIME NOMINAL EST INCHANGE

def test_le_gate_Count_inferieur_a_1_n_ecrit_toujours_RIEN():
    """`if (previousPosition.Count < 1) return` -- gate natif, inchange par le demenagement."""
    st = _state()
    assert save_previous_position(st, UID, []) is False
    uc = st.get_entity(UID).get_component(UnitComponent)
    assert uc.previous_position is None and uc.previous_position_this_turn is None


def test_sans_ecriture_le_selecteur_rend_une_liste_VIDE():
    """`Nullable` vide -> `new List<TileEntity>()`. Le defaut ne doit pas devenir non-vide."""
    st = _state()
    assert previous_tiles(st.get_entity(UID)) == []


def test_une_entite_sans_UnitComponent_rend_VIDE_sans_lever():
    """DEGRADATION NOMMEE, inchangee : le natif LEVE quand le composant manque, le port rend `[]`
    (cf. `selectors/tiles.py::PreviousTile`). Seule la CLASSE consultee a change."""
    st = _state()
    e = st.add_entity()
    assert previous_tiles(e) == []
    assert previous_tiles(None) == []


def test_le_selecteur_suit_une_RE_ECRITURE():
    """Le champ reste vivant : une seconde ecriture ECRASE la premiere (le natif re-construit un
    `UnitPositionId` a chaque `SavePreviousPosition`)."""
    st = _state()
    save_previous_position(st, UID, AVANT)
    save_previous_position(st, UID, [(3, 4)])
    assert previous_tiles(st.get_entity(UID)) == [(3, 4)]
