"""GARDE #895-r2 / #895-r3 (OFFLINE PURE) -- les deux clauses du volet CASTER de
`engine/runner/abilities/targeting.py::get_invalid_caster_reason` posees par cette tranche.

CE QU'ELLE PROTEGE, et pourquoi chacune peut regresser SILENCIEUSEMENT : les deux etaient des
degradations **PERMISSIVES** -- ni erreur, ni crash, le port ACCEPTAIT simplement un cast que
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason` REFUSE. C'est exactement le trou
qu'un entrainement RL irait exploiter, et rien d'autre que ce fichier ne le voit.

  1. **LES TROIS FILTRES DE `GetFeetCount`** (#895-r2) -- `CasterHas1Tiles` / `CasterHas3Tiles` /
     `CasterHas7Tiles`, bits 35/36/37. VERBATIM du decompile (build `rnca9r7q6c`) :

         feet = UnitExtensions.GetFeetCount(caster, state);
         if ((rules >> 0x23 & 1) && feet != 1) return broken(0x800000000);
         if ((rules >> 0x24 & 1) && feet != 3) return broken(0x1000000000);
         if ((rules >> 0x25 & 1) && feet != 7) return broken(0x2000000000);

     Les porteurs sont RE-DERIVES du registre, jamais enumeres : le gisement bouge avec notre
     propre cadence de portage (la fiche du residu n'en nommait qu'UN, il y en a quatre).
  2. **LA DELEGUE DE `1192 NovaBoost`** (#895-r3) --
     `...NovaBoostAbility$$GetDynamicInvalidCasterReason` = `Count(Enemies(Caster@+0x48,
     GetMarkedTilesSelector(), 3)) > 1 ? 0 : 4`. L'ETAGE qui l'invoque (`CasterMatchesDynamicRule`,
     etage 5 de la cascade) existait deja depuis #250 ; ce qui manquait etait la surcharge.

  3. **L'ORDRE**, et il est LOAD-BEARING : le natif place les trois filtres de cardinal APRES la
     regle-delegue et AVANT `CasterHas2TurnsLeft`. L'ordre fixe LAQUELLE des clauses est rendue
     quand plusieurs sont rompues -- un port juste sur chaque clause prise seule peut rendre la
     MAUVAISE raison, et aucun bras de verdict binaire ne le verrait.

MESURE (les memes bras, plus la contre-epreuve sur arbre TEMOIN) :
`python scripts/python/probe_895r2r3_caster_gates.py`.
ASCII only. Aucune VA en dur ; les symboles sont cites verbatim.
"""
from __future__ import annotations

import ast
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import hexgeo                                                            # noqa: E402
from engine.entities.effects_state import EffectsState                   # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES              # noqa: E402
from engine.runner.abilities.targeting import get_invalid_caster_reason  # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.components import set_unit_feet                       # noqa: E402
from engine.runner.snapshot import load_state                            # noqa: E402

COLS, ROWS = 9, 9
CASTER, FOE_A, FOE_B, ALLY = 10, 20, 21, 30
NOVA_BOOST = 1192                       # ActiveAbilityType.NovaBoost

#: bit -> cardinal EXIGE, LU dans le decompile cite en tete de module.
CARDINAL = {int(TR.CasterHas1Tiles): 1, int(TR.CasterHas3Tiles): 3, int(TR.CasterHas7Tiles): 7}


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles(trenches=()) -> list:
    """`trenches` = les `(col,row)` a marquer `tileDefId = "Trench"`. C'est le TERRAIN STATIQUE que
    `IdunBattle.Entities.TileExtensions$$IsTrench` lit -- pas l'effet de tuile `EffectType.Trench`
    (1059), qui est un autre canal."""
    marquees = {(int(c), int(r)) for c, r in trenches}
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            t = {"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                 "walkable": True, "isWall": False, "neighbours": nb}
            if (col, row) in marquees:
                t["tileDefId"] = "Trench"
            out.append(t)
    return out


def _monter(unites: list, trenches=()):
    board = Board(_tiles(trenches), adjacency="evenq")
    decision = {"currentPlayer": 1, "units": [
        {"id": uid, "visualId": "tauBossRiptide" if uid == CASTER else "ultraTitus",
         "alive": True, "team": team, "owner": team,
         "pos": {"col": pos[0], "row": pos[1]}, "effects": []}
        for uid, team, pos in unites]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000}
                         for u in decision["units"]]}
    st = load_state(decision, observe, board=board)
    if st.effects is None:
        st.effects = EffectsState()
    return st


def _voisines() -> list:
    return [(c, r) for (c, r) in hexgeo.neighbors(4, 4) if 0 <= c < COLS and 0 <= r < ROWS]


def _empreinte(n: int) -> list:
    return ([(4, 4)] + _voisines())[:n]


def _porteurs_feet() -> dict:
    """{ability_id: (classe, bit, cardinal)} RE-DERIVE du registre. Le gisement bouge avec notre
    propre cadence de portage -- l'enumerer figerait une photo perimee."""
    out = {}
    for aid, cls in ABILITY_CLASSES.items():
        rules = int(getattr(getattr(cls, "TARGETING_OPTIONS", None), "rules", 0) or 0)
        for bit, n in CARDINAL.items():
            if rules & bit:
                out[int(aid)] = (cls, bit, n)
    return out


# ------------------------------------------------------- 1. les trois filtres de GetFeetCount

def test_les_porteurs_des_trois_bits_ne_sont_PAS_un_ensemble_vide():
    """Le cran du dessous : une mesure sur un ensemble VIDE passerait pour verte. Si ce test tombe,
    ce n'est PAS que le port a regresse -- c'est que plus aucune ability du registre ne pose l'un
    des trois bits, donc que les tests suivants ne mesurent plus rien."""
    porteurs = _porteurs_feet()
    assert porteurs, ("aucun porteur de CasterHas1/3/7Tiles au registre : les bras ci-dessous "
                      "ne mesureraient plus rien")


@pytest.mark.parametrize("feet_n", [1, 3, 7])
def test_le_cardinal_des_pieds_refuse_ou_accepte_comme_le_natif(feet_n):
    """Pour CHAQUE porteur du registre : le cardinal EXIGE rend `0`, tout autre rend SON bit.
    Le bras qui MORD est celui ou le cardinal differe -- avant #895-r2 le port y rendait `0`."""
    for aid, (cls, bit, exige) in sorted(_porteurs_feet().items()):
        st = _monter([(CASTER, 1, (4, 4)), (FOE_A, 2, (8, 8))])
        set_unit_feet(st, CASTER, _empreinte(feet_n))
        got = get_invalid_caster_reason(st, CASTER, cls())
        attendu = 0 if feet_n == exige else int(bit)
        assert got == attendu, (
            "ability %d (%s) : feet=%d -> 0x%x, attendu 0x%x (le natif exige %d pied(s))"
            % (aid, cls.__name__, feet_n, got, attendu, exige))


def test_l_ordre_natif_place_les_filtres_de_cardinal_AVANT_CasterHas2TurnsLeft():
    """CRAN STRUCTUREL -- il ne se voit dans AUCUN bras de verdict, parce qu'aucun porteur ne pose
    aujourd'hui les DEUX familles de bits. L'ordre est ecrit fidele au natif ; on le garde par
    l'AST de la fonction, pas par un grep de source (un commentaire citant le meme nom de bit
    suffirait a rendre un grep vert).

    ⚠ `ast.walk` est un parcours en LARGEUR : il ne rend PAS l'ordre du source. Ce test l'a mesure
    sur lui-meme a sa premiere execution (il rendait `CasterHas2TurnsLeft` AVANT `CasterHas1Tiles`
    alors que le code ecrit l'inverse). L'ordre se prend donc sur la POSITION des noeuds."""
    import engine.runner.abilities.targeting as T
    src = open(T.__file__, encoding="utf-8").read()
    fn = next(n for n in ast.parse(src).body
              if isinstance(n, ast.FunctionDef) and n.name == "get_invalid_caster_reason")
    positions = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and node.value.id == "TR":
            pos = (node.lineno, node.col_offset)
            if node.attr not in positions or pos < positions[node.attr]:
                positions[node.attr] = pos
    vus = [nom for nom, _ in sorted(positions.items(), key=lambda kv: kv[1])]
    for bit in ("CasterHas1Tiles", "CasterHas3Tiles", "CasterHas7Tiles"):
        assert bit in vus, "%s n'est plus TESTE par get_invalid_caster_reason (#895-r2)" % bit
    assert "CasterMatchesDynamicRule" in vus and "CasterHas2TurnsLeft" in vus
    assert (vus.index("CasterMatchesDynamicRule") < vus.index("CasterHas1Tiles")
            < vus.index("CasterHas2TurnsLeft")), (
        "ORDRE NATIF rompu : le decompile place les trois filtres de GetFeetCount APRES la "
        "regle-delegue et AVANT CasterHas2TurnsLeft ; ordre lu = %r" % (vus,))


# ------------------------------------------------------------- 2. la delegue de 1192 NovaBoost

@pytest.mark.parametrize("libelle,autres,attendu", [
    ("0 ennemi adjacent", [], int(TR.CasterMatchesDynamicRule)),
    ("1 ennemi adjacent -- le DISCRIMINANT du `1 < Count`", "UN_ENNEMI",
     int(TR.CasterMatchesDynamicRule)),
    ("2 ennemis adjacents", "DEUX_ENNEMIS", 0),
    ("2 allies adjacents (le camp compte)", "DEUX_ALLIES", int(TR.CasterMatchesDynamicRule)),
    ("2 ennemis hors couronne (la zone compte)", [(FOE_A, 2, (0, 0)), (FOE_B, 2, (8, 8))],
     int(TR.CasterMatchesDynamicRule)),
])
def test_nova_boost_exige_au_moins_DEUX_ennemis_dans_la_couronne(libelle, autres, attendu):
    """`Count(Enemies(Caster@+0x48, GetMarkedTilesSelector(), 3)) > 1 ? 0 : 4`.

    Le bras `1 ennemi` est le DISCRIMINANT : un port qui aurait ecrit `Count >= 1` au lieu du
    `1 < Count` LU serait vert sur les quatre autres."""
    cls = ABILITY_CLASSES.get(NOVA_BOOST)
    assert cls is not None, "1192 NovaBoost absente du registre"
    v = _voisines()
    table = {"UN_ENNEMI": [(FOE_A, 2, v[0])],
             "DEUX_ENNEMIS": [(FOE_A, 2, v[0]), (FOE_B, 2, v[1])],
             "DEUX_ALLIES": [(ALLY, 1, v[0]), (FOE_B, 1, v[1])]}
    unites = table.get(autres, autres) if isinstance(autres, str) else autres
    st = _monter([(CASTER, 1, (4, 4))] + list(unites))
    got = get_invalid_caster_reason(st, CASTER, cls())
    assert got == attendu, "%s : 0x%x, attendu 0x%x" % (libelle, got, attendu)


def test_nova_boost_ECARTE_les_ennemis_poses_sur_une_tuile_TRENCH():
    """LE FILTRE `Not(IsTrenchTile(ActiveTarget))` du selecteur, exerce pour de vrai.

    Il a ete AJOUTE apres coup : la mutation « selecteur `AdjacentTiles` nu, sans le `Filter` »
    laissait les cinq bras ci-dessus VERTS, faute d'une seule tuile Trench sur le board de test.
    Un cran qu'aucune mutation ne fait rougir ne garde rien.

    Montage : DEUX ennemis adjacents -- assez pour passer le `1 < Count` -- mais l'un des deux est
    sur une tuile Trench, donc la couronne effective n'en compte qu'UN -> refus."""
    cls = ABILITY_CLASSES[NOVA_BOOST]
    v = _voisines()
    sans = _monter([(CASTER, 1, (4, 4)), (FOE_A, 2, v[0]), (FOE_B, 2, v[1])])
    assert get_invalid_caster_reason(sans, CASTER, cls()) == 0, (
        "temoin : sans trench, deux ennemis adjacents doivent SUFFIRE")
    avec = _monter([(CASTER, 1, (4, 4)), (FOE_A, 2, v[0]), (FOE_B, 2, v[1])],
                   trenches=[v[1]])
    assert get_invalid_caster_reason(avec, CASTER, cls()) == int(TR.CasterMatchesDynamicRule), (
        "la tuile Trench de %r doit sortir son occupant de la couronne "
        "(`Filter(AdjacentTiles(Caster), Not(IsTrenchTile(ActiveTarget)))`)" % (v[1],))


def test_nova_boost_porte_bien_la_surcharge_et_non_le_no_op_de_la_base():
    """CRAN DU DESSOUS : les bras ci-dessus passeraient aussi si `ActiveAbility` (base.py) rendait
    par hasard la bonne valeur. On exige que la surcharge soit DECLAREE sur la classe elle-meme --
    c'est ce qui distingue « porte » de « coincide »."""
    cls = ABILITY_CLASSES[NOVA_BOOST]
    assert "get_dynamic_invalid_caster_reason" in vars(cls), (
        "1192 n'a pas SA surcharge : elle heriterait du no-op permissif de `ActiveAbility`")
