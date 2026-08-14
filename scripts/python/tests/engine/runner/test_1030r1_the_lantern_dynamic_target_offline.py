"""GARDE #1030-r1 (OFFLINE PURE) -- le gate dynamique CIBLE de `1094 TheLantern`, et l'etage
`get_adjacent_tiles(only_empty_or_steppable=False)` qu'il a fallu ouvrir pour l'ecrire.

Levee dans la tranche #287-r11 : `probe_287r5_etages_bloquants.py` rendait `rc=1` sur `master`
(<< ids a surcharge native SANS etage recense : 1 TheLantern >>) -- 1094 etait la DERNIERE dette
reelle du recensement avec `1213 DeathOnTheWind`.

CE QUE CE FICHIER PROTEGE :

  1. **LA GEOMETRIE**, et elle est LE livrable. Corps natif :

         A = battleQuery.<IBattleQuery 81 GetAdjacentTiles>(casterTiles, 0, 1, 1)
         B = battleQuery.<IBattleQuery 79 GetAdjacentTiles>(targetTile,  0, 1, 1)
         A.<ISet<T> slot 1>(B) ; return (A.Count == 1) ? 0 : 2

     Le slot 1 est `IntersectWith`, et c'est une REFUTATION (cf. la docstring de la methode) :
     `ExceptWith` refuserait TOUT cast, or l'ability est castee en jeu. Le cran executable de cette
     refutation est `test_le_gate_ne_refuse_PAS_TOUT` ci-dessous -- un ensemble accepte VIDE est
     exactement ce que rendrait la mauvaise lecture.

  2. **LE FLAG `onlyEmptyOrSteppable` GATE le filtre, il ne l'INVERSE pas.** `targeting.
     get_adjacent_tiles` LEVAIT sur `False` (aucun call-site porte ne le passait). L'ouvrir est un
     etage : a `False`, le terme `IsEmptyOrSteppable` DISPARAIT de la cascade -- une tuile occupee
     entre dans le resultat. La confondre avec une inversion donnerait l'ensemble complementaire.

MESURE (la geometrie tuile par tuile, sur un plateau 13x13) :
`python scripts/python/probe_1030r1_the_lantern_dynamic_target.py`.
ASCII only. Aucune VA en dur ; les symboles sont cites verbatim.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import hexgeo                                                            # noqa: E402
from engine.entities.effects_state import EffectsState                   # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.abilities import targeting as TGT                     # noqa: E402
from engine.runner.abilities.deathguard import TheLanternAbility         # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES              # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.components import set_unit_feet                       # noqa: E402
from engine.runner.snapshot import load_state                            # noqa: E402

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15). PRIS LARGE : la
#: geometrie mesuree depend du board ET de l'etage `get_adjacent_tiles`, et le masque de 1094 vient
#: du registre -- un declencheur limite a `deathguard.py` serait un FAUX VERT.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/abilities/**/*.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/entities/pathfinding/board.py",
        "scripts/python/hexgeo.py",
    ),
    "build": False,       # la geometrie est calculee, aucun symbole n'est lu ici
    "toujours": False,
    "raison": (
        "Le gate compose `get_adjacent_tiles` (targeting.py), l'empreinte du caster "
        "(components.get_unit_feet) et la geometrie hex du board -- trois foyers distincts, dont "
        "aucun ne vit dans `deathguard.py`. Le declencheur reste large sur `abilities/**` parce "
        "que l'etage `get_adjacent_tiles` est partage : un autre call-site qui le durcirait "
        "casserait ce gate sans toucher a 1094."),
}

COLS, ROWS = 13, 13
CENTRE = (6, 6)
CASTER, FOE, BLOQUEUR = 10, 20, 30
THE_LANTERN = 1094                      # ActiveAbilityType.TheLantern


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles() -> list:
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return out


def _empreinte_7() -> list:
    """Le centre + sa couronne = les SEPT tuiles de Mortarion (le masque pose `CasterHas7Tiles`)."""
    return [CENTRE] + list(hexgeo.neighbors(*CENTRE))


@pytest.fixture
def monte():
    board = Board(_tiles(), adjacency="evenq")
    decision = {"currentPlayer": 1, "units": [
        {"id": CASTER, "visualId": "deathBossMortarion", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": CENTRE[0], "row": CENTRE[1]}, "effects": []},
        {"id": FOE, "visualId": "ultraTitus", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 0, "row": 0}, "effects": []},
    ]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000}
                         for u in decision["units"]]}
    st = load_state(decision, observe, board=board)
    if st.effects is None:
        st.effects = EffectsState()
    set_unit_feet(st, CASTER, _empreinte_7())
    return st, board


def _acceptees(st, board) -> list:
    ab = TheLanternAbility()
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            tid = board.id_at(col, row)
            if tid is not None and ab.get_dynamic_invalid_target_reason(st, CASTER, tid) == 0:
                out.append((col, row))
    return out


# --------------------------------------------------------------------- 1. la geometrie

def test_le_gate_ne_refuse_PAS_TOUT(monte):
    """LE CRAN DE LA REFUTATION. Avec `ExceptWith` au lieu d'`IntersectWith`, `|A \\ B| >= |A| - 6`
    et `|A| = 19` au regime nominal -> AUCUNE tuile ne serait jamais acceptee, et l'ability serait
    incastable. Un ensemble accepte VIDE est donc la signature exacte de la mauvaise lecture du
    slot 1 -- et un test qui ne verifierait que << les mauvaises tuiles refusent >> serait vert."""
    st, board = monte
    assert _acceptees(st, board), (
        "AUCUNE tuile acceptee : c'est ce que rendrait `ExceptWith` -- or l'ability est castee en "
        "jeu (effets 1194/1195 poses, phase 2 observee)")


def test_exactement_les_SIX_directions_de_l_i2(monte):
    """`Abilities/TheLantern_CurrentLevelDescription` : << in **one of six directions** >>. Le gate
    accepte SIX tuiles, toutes a distance 3 du CENTRE de l'empreinte -- les six axes. Les tuiles de
    milieu d'arete, elles, touchent DEUX tuiles de `A`, donc `Count == 2` -> refus."""
    st, board = monte
    got = _acceptees(st, board)
    assert len(got) == 6, "l'i2 dit six directions ; le port en accepte %d : %r" % (len(got), got)
    d = sorted({hexgeo.distance(t, CENTRE) for t in got})
    assert d == [3], "les six directions sont a distance 3 du centre ; mesure %r sur %r" % (d, got)


@pytest.mark.parametrize("delta,libelle", [
    ((0, 1), "tuile de l'empreinte (d=0)"),
    ((0, 2), "ring-2, DANS A (d=2 du centre)"),
    ((0, 5), "trop loin, B ne touche pas A"),
])
def test_les_contre_bras_refusent(monte, delta, libelle):
    """CONTRE-BRAS : ni le disque interieur, ni le lointain ne passent. Sans eux, un port qui
    accepterait TOUT serait vert sur le test du non-vide ci-dessus."""
    st, board = monte
    tid = board.id_at(CENTRE[0] + delta[0], CENTRE[1] + delta[1])
    got = TheLanternAbility().get_dynamic_invalid_target_reason(st, CASTER, tid)
    assert got == int(TR.TargetMatchesDynamicRule), "%s : 0x%x, attendu un refus" % (libelle, got)


def test_1094_porte_bien_SA_surcharge(monte):
    """CRAN DU DESSOUS : les bras ci-dessus passeraient si la base rendait par hasard la bonne
    valeur -- or `ActiveAbility.get_dynamic_invalid_target_reason` rend `0` (permissif), donc le
    contre-bras la verrait. On exige quand meme la DECLARATION : c'est ce qui distingue
    << porte >> de << coincide >>."""
    assert "get_dynamic_invalid_target_reason" in vars(ABILITY_CLASSES[THE_LANTERN])


# ------------------------------------------- 2. l'etage `only_empty_or_steppable=False`

def test_le_flag_onlyEmptyOrSteppable_GATE_le_filtre_et_ne_l_INVERSE_pas(monte):
    """`if (onlyEmptyOrSteppable && !IsEmptyOrSteppable(tile, state)) continue` -- a `False` le
    terme DISPARAIT. Mesure des DEUX cotes sur la MEME tuile occupee : elle doit etre PRESENTE a
    `False` et ABSENTE a `True`. Une inversion rendrait le complementaire et passerait un test qui
    ne regarderait qu'un seul cote."""
    st, board = monte
    voisine = list(hexgeo.neighbors(0, 0))[0]        # une voisine de FOE, qu'on va occuper
    ent = st.get_entity(FOE)
    assert ent is not None
    # On pose un BLOQUEUR sur `voisine` : la tuile cesse d'etre `IsEmptyOrSteppable`.
    decision = {"currentPlayer": 1, "units": [
        {"id": CASTER, "visualId": "deathBossMortarion", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": CENTRE[0], "row": CENTRE[1]}, "effects": []},
        {"id": FOE, "visualId": "ultraTitus", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 0, "row": 0}, "effects": []},
        {"id": BLOQUEUR, "visualId": "ultraTitus", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": voisine[0], "row": voisine[1]}, "effects": []},
    ]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000}
                         for u in decision["units"]]}
    st2 = load_state(decision, observe, board=Board(_tiles(), adjacency="evenq"))
    if st2.effects is None:
        st2.effects = EffectsState()
    sans_filtre = TGT.get_adjacent_tiles(st2, FOE, False, True, True)
    avec_filtre = TGT.get_adjacent_tiles(st2, FOE, True, True, True)
    assert voisine in sans_filtre, (
        "a `onlyEmptyOrSteppable=False` la tuile OCCUPEE %r doit entrer : le terme disparait"
        % (voisine,))
    assert voisine not in avec_filtre, (
        "a `onlyEmptyOrSteppable=True` la tuile OCCUPEE %r doit sortir" % (voisine,))
    assert set(avec_filtre) < set(sans_filtre), (
        "le flag GATE : `True` doit rendre un SOUS-ENSEMBLE STRICT de `False`, pas un autre "
        "ensemble -- une inversion romprait l'inclusion")


def test_only_walkable_tiles_False_LEVE_toujours(monte):
    """L'autre flag n'a AUCUN call-site porte : il doit continuer a lever plutot que d'inventer un
    comportement. Le relacher << pendant qu'on y est >> ferait entrer des tuiles que le port ne
    sait pas qualifier."""
    st, _ = monte
    with pytest.raises(NotImplementedError):
        TGT.get_adjacent_tiles(st, CASTER, True, False, True)
