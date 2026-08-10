"""#419-r1-tr10-r2 (regression) -- GARDE des DEUX FORMES de tuile du canal `feet`. OFFLINE.

CE QUI S'EST PASSE. `a22c65ae` (2026-08-10 16:08) a ouvert le capteur MULTI-TUILES cote DECISION :
`projection.ts::readEntityFeet` = `IdunBattle.Entities.EntityExtensions$$GetTiles`, publie sous
`decisionView.units[].feet` -- en DICTS `{"col","row"}`, la forme de `readTileCoord`. La face COMBAT,
elle, porte des COUPLES `(col,row)` (`runner.components.get_unit_feet`). Trois lecteurs consommaient
la cle `feet` d'un dict d'unite ; UN SEUL normalisait :

    engine/playbook/adjacency.py::iterate_tiles  -> `_as_pos`, les deux formes      OK
    engine/dsl/base.py::_feet                    -> `(int(f[0]), int(f[1]))`        KeyError: 0
    engine/entities/selectors/tiles.py           -> recopie LOCALE de la regle      KeyError: 0

Le second est le foyer que TOUS les selecteurs DSL traversent (`accessors.py::TargetTile` ->
`_feet(ctx.target)`), d'ou deux rouges live immediats
(`test_ability_hits_channel_live::test_frenzied_firing_hits_is_geometric` et
`..._aoe_batch_matches_native`). Le message de `a22c65ae` dit -- justement --
<< Canal muet -> repli sur la MainTile, c.-a-d. le comportement d'avant, EXACTEMENT >> : c'est vrai
du canal MUET, et le canal ne l'est pas.

CE QUE CE FICHIER GARDE, et pourquoi offline. Le regime est un pur predicat de forme : aucun runner
ne peut le mesurer mieux qu'un dict fabrique, et un test live le paierait 30 s pour la meme
assertion. Quatre etages :

  1. le FOYER `_feet` rend la meme chose sur les DEUX formes, et retombe sur la main tile quand le
     canal est MUET (tri-etat `null`) ;
  2. le CHEMIN REEL qui a leve : `FrenziedFiringAbility._AOE` = `AdjacentEnemies(TargetTile(), 1)`
     sur un dict d'unite tel que le capteur le publie ;
  3. la DISCRIMINANCE : sur une cible MULTI-HEX, lire l'empreinte CHANGE l'ensemble rendu -- sans
     ce montage, l'etage 2 serait vert pour une unite mono-tuile, ou les deux lectures coincident
     par construction et ne prouvent rien ;
  4. la PROVENANCE : `selectors/tiles.py` passe par le foyer et ne recopie plus la regle. Une
     recopie corrigee serait indistinguable AUJOURD'HUI, et re-divergerait au prochain canal.

ASCII only (cp1252).
"""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import hexgeo                                                                 # noqa: E402
from engine.dsl.base import DslContext, _feet, _pos                           # noqa: E402
from engine.entities.abilities.active_ability import FrenziedFiringAbility    # noqa: E402
from engine.entities.selectors import tiles as SEL_TILES                      # noqa: E402

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
DECLENCHEUR = {
    "chemins": (),
    "build": False,
    "toujours": True,
    "raison": (
        "`chemins` VIDE, et c'est MESURE : `probe_486r15 --proposer` rend RIEN A DECLARER hors de "
        "la cascade -- la fermeture d'imports de ce fichier (les trois lecteurs de `feet` compris) "
        "y tient entierement, et on ne redeclare pas la cascade derivee du foyer (#531). D'ou "
        "`toujours: True` : un perimetre vide avec `toujours: False` ne serait JAMAIS rejoue, et "
        "ce fichier est offline et court (aucun runner, aucun RPC, board fabrique). "
        "`build: False` : aucune valeur n'est figee depuis le binaire -- ce qui est garde est la "
        "FORME du canal `decisionView.units[].feet` (dicts `{col,row}`) face a celle de la face "
        "COMBAT (couples), et la geometrie hex du board de test. Le jour ou le hook changerait la "
        "forme publiee, c'est l'etage 2 qui doit rougir, pas un ordinal."),
}


class _Board:
    """Board hex minimal : grille 7x7 complete, toutes tuiles marchables (meme patron que #433-r4)."""

    def __init__(self, cols: int = 7, rows: int = 7) -> None:
        self._ids = {}
        n = 1
        for col in range(cols):
            for row in range(rows):
                self._ids[(col, row)] = n
                n += 1
        self._pos = {v: k for k, v in self._ids.items()}
        self.by_id = {t: {"col": p[0], "row": p[1]} for t, p in self._pos.items()}

    def id_at(self, col, row):
        return self._ids.get((int(col), int(row)))

    def coord(self, tid):
        return self._pos.get(tid)

    def neighbours(self, tid):
        return [self._ids[p] for p in hexgeo.neighbors(*self._pos[tid]) if p in self._ids]

    def neighbours_native(self, tid):
        """Le champ `boardGraph.neighbours`, capte par `BattleQuery$$GetAdjacentTiles(t, false,
        false, true)` -- filtres de terrain OFF, porte d'ELEVATION ON. Sur ce board de test, toutes
        les tuiles sont a elevation 0 et la grille est pleine : la porte ne retranche aucune arete,
        donc le champ capte COINCIDE avec le voisinage hex. C'est une identite du MONTAGE, pas une
        simplification du mirror -- le vrai `Board.neighbours_native` lit la mesure."""
        return self.neighbours(tid)

    def walkable(self, tid):
        return tid in self._pos


BOARD = _Board()


def _combat(uid, team, feet, pos=None):
    """Dict d'unite face COMBAT (`behaviours/context.py::_unit_dict`) : `feet` en COUPLES."""
    p = pos if pos is not None else feet[0]
    return {"id": uid, "team": team, "alive": True, "hp": 100,
            "pos": {"col": p[0], "row": p[1]}, "feet": [tuple(f) for f in feet]}


def _decision(uid, team, feet, pos=None):
    """Dict d'unite face DECISION (`projection.ts`) : `feet` en DICTS, et `pos` = le DERNIER pied.

    Ce `pos`-la n'est pas un detail de montage : `decisionView` DEDUPLIQUE par unite alors que le
    projecteur emet une ligne par PIED, donc il porte le dernier projete -- pas la main tile
    (cf. `runner/snapshot.py::_load_feet`). C'est ce qui rend le repli main-tile FAUX cote DECISION,
    et pas seulement incomplet."""
    p = pos if pos is not None else feet[-1]
    return {"id": uid, "team": team, "alive": True, "hp": 100,
            "pos": {"col": p[0], "row": p[1]},
            "feet": [{"col": int(f[0]), "row": int(f[1])} for f in feet]}


def _muet(uid, team, pos):
    """Canal MUET (tri-etat `null`) : pas de cle `feet` -- le repli main tile s'applique."""
    return {"id": uid, "team": team, "alive": True, "hp": 100,
            "pos": {"col": pos[0], "row": pos[1]}}


#: Empreinte MULTI-HEX de la cible : trois pieds contigus (le patron d'un Galatian).
CIBLE_FEET = ((3, 3), (3, 4), (4, 3))


# ================================================================== 1. LE FOYER

@pytest.mark.parametrize("fabrique,libelle", [(_combat, "COMBAT (couples)"),
                                              (_decision, "DECISION (dicts)")],
                         ids=["couples", "dicts"])
def test_le_foyer_rend_la_meme_empreinte_sur_les_deux_formes(fabrique, libelle):
    """Les deux canaux publient la MEME empreinte ; seule la representation d'une tuile differe."""
    assert _feet(fabrique(2, 2, CIBLE_FEET)) == [tuple(f) for f in CIBLE_FEET], libelle


def test_le_canal_muet_retombe_sur_la_main_tile_et_pas_sur_une_liste_vide():
    """La DEGRADATION documentee, figee : sans canal, l'empreinte vaut `[pos]`. C'est exact pour
    toute unite mono-tuile (le natif rend alors lui aussi un seul pied)."""
    u = _muet(2, 2, (3, 3))
    assert _feet(u) == [_pos(u)] == [(3, 3)]


def test_une_entite_sans_position_rend_une_liste_VIDE():
    """`GetUnitFeetIds` rend une liste vide pour une entite hors plateau -- le port ne doit inventer
    aucune tuile (ses consommateurs, `AreTilesAdjacent(IList,IList)` / `GetMinDistance`, ne bouclent
    alors sur rien)."""
    assert _feet({"id": 9, "team": 1, "alive": True, "pos": None}) == []
    assert _feet(None) == []


# ================================================================== 2. LE CHEMIN QUI LEVAIT

def _ctx(units, caster, target):
    return DslContext(units=units, caster=caster, target=target, board=BOARD)


def _aoe_ids(cible, autres):
    """`FrenziedFiringAbility._AOE` = `AdjacentEnemies(TargetTile(), 1)` -- le selecteur REEL dont
    `accessors.py::TargetTile` appelle `_feet(ctx.target)`, donc le chemin qui levait."""
    caster = _combat(1, 1, [(0, 0)])
    units = [caster, cible] + list(autres)
    got = FrenziedFiringAbility(0, None, None, {"level": 50}).get_aoe_targets(
        _ctx(units, caster, cible))
    return sorted(u["id"] for u in got)


def test_le_selecteur_traverse_un_dict_DECISION_sans_lever():
    """LE ROUGE, reproduit : avant la reparation, `_feet` faisait `f[0]` sur un dict -> `KeyError: 0`,
    et les deux tests live de FrenziedFiring tombaient a cet endroit exact."""
    voisin = _combat(7, 2, [(2, 3)])            # adjacent au pied (3,3) de la cible
    assert _aoe_ids(_decision(2, 2, CIBLE_FEET), [voisin]) == [7]


# ================================================================== 3. DISCRIMINANCE

def test_lire_l_empreinte_CHANGE_l_ensemble_rendu_sur_une_multi_hex():
    """CONTRE-CONTROLE. Un ennemi adjacent au SEUL pied `(3,4)` n'est PAS adjacent au `pos` que
    `decisionView` porte pour cette cible : le repli main-tile le manquerait, l'empreinte le trouve.

    Sans cet etage, l'etage 2 resterait vert sur une unite mono-tuile -- ou empreinte et main tile
    coincident par construction, donc ou aucune lecture n'est distinguable de l'autre."""
    cible = _decision(2, 2, CIBLE_FEET)
    pos_publie = _pos(cible)
    voisins_du_pied = [p for p in hexgeo.neighbors(3, 4)
                       if BOARD.id_at(*p) is not None and p not in CIBLE_FEET
                       and hexgeo.distance(p, pos_publie) > 1]
    assert voisins_du_pied, (
        "le montage ne separe plus les deux lectures : aucune tuile n'est adjacente au pied (3,4) "
        "sans l'etre au `pos` publie. Le board ou l'empreinte ont change -- re-choisir les pieds.")
    loin = _combat(8, 2, [voisins_du_pied[0]])
    assert _aoe_ids(cible, [loin]) == [8], (
        "l'ennemi adjacent au pied (3,4) n'est pas selectionne : le foyer ne lit pas l'empreinte.")
    # ... et le MEME ennemi est INVISIBLE si le canal est muet (repli main tile) : c'est la mesure
    # de l'ecart, pas une supposition.
    assert _aoe_ids(_muet(2, 2, pos_publie), [loin]) == [], (
        "le repli main-tile selectionne quand meme cet ennemi : les deux lectures coincident sur "
        "ce montage, il ne prouve donc rien.")


# ================================================================== 4. PROVENANCE

def test_le_second_lecteur_passe_par_le_foyer_et_ne_recopie_plus_la_regle():
    """PROVENANCE, par AST : `selectors/tiles.py` recopiait `feet` sinon `[_pos]` -- une recopie
    corrigee serait indistinguable en VALEUR aujourd'hui, et re-divergerait au prochain canal."""
    src = inspect.getsource(SEL_TILES)
    tree = ast.parse(src)
    recopies = [n.lineno for n in ast.walk(tree)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "get" and len(n.args) == 1
                and isinstance(n.args[0], ast.Constant) and n.args[0].value == "feet"]
    assert not recopies, (
        "`selectors/tiles.py` relit la cle `feet` en direct (lignes %r) au lieu de passer par "
        "`_feet` : la normalisation des deux formes n'est plus au foyer." % recopies)
    assert "_feet" in {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}, (
        "`selectors/tiles.py` n'appelle plus `_feet` du tout.")
