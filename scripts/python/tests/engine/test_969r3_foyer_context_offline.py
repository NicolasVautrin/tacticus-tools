"""Le foyer `engine/ai/context.py` -- CINQ residus fermes par la meme tranche, gardes ICI.

Tous les volets sont OFFLINE et sur substrat SYNTHETIQUE : aucun runner, aucun RPC. C'est
deliberé -- les cinq portent sur des canaux dont le regime MORDANT n'existe pas dans les montages
de duel courants (aucune unite multi-hex, aucun effet de tuile inactif), donc un test live
rendrait un VERT DEGENERE. Ce que ces etages gardent, c'est la MECANIQUE, exercee dans son regime.

  1. `#969-r3` -- l'occupation se derive de l'EMPREINTE (`battle_query.occupied_positions`).
  2. `#419-r1-tr11-r1` -- `1545 SpecialIssueCombiMelta` prend le MIN sur les PIEDS de la cible.
  3. `#433-r4-r3-r3` -- `scene_tile_leaf_ctx` produit `unit_parent_id`.
  4. `#425-r1` -- les feuilles de tuile voient la liste POSSEDEE, la `Scene` reste ACTIF-ONLY.
  5. `#433-r4-r2-r1-r1-a-r1` -- le gate `GATE_VALID_ON_EMPTY_TILE` retire une tuile OCCUPEE,
     et son canal est en TRI-ETAT DERIVE (une table vide n'est pas une mesure).

DEUX PROPRIETES SONT EXIGEES DE CHAQUE VOLET, et la seconde est celle qui coute :

  * il MORD dans le regime qu'il porte (multi-hex, effet inactif, tuile occupee, parent present) ;
  * il est un NO-OP EXACT hors de ce regime. C'est ce qui rend la tranche sure : sur tout montage
    mono-pied / sans effet inerte / sans occupant, le port rend BIT POUR BIT ce qu'il rendait avant.
    Un port qui ne demontre que sa morsure ne dit rien de ce qu'il a casse ailleurs.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from engine import battle_query as bq                            # noqa: E402
from engine.ai import context as aictx                           # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402
from engine.services import ability_range as ar                  # noqa: E402
from engine.utilities import tile as tilemod                     # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # Les cinq foyers portes par la tranche, un par volet.
        "scripts/python/engine/battle_query.py",                       # occupied_positions
        "scripts/python/engine/playbook/special_issue_combi_melta.py",  # 1545, empreinte cible
        "scripts/python/engine/playbook/adjacency.py",                 # iterate_tiles, son foyer
        "scripts/python/engine/utilities/tile.py",                     # les 3 tile_leaf_ctx
        "scripts/python/engine/ai/context.py",                         # canaux tuile + occupant
        "scripts/python/engine/services/ability_range.py",             # GATE_VALID_ON_EMPTY_TILE
        # Les enums dont les etages LISENT un membre nomme : un renumerotage les deplace.
        "scripts/python/engine/entities/active_ability_type.py",
    ),
    "build": False,     # aucun etage ne lit le binaire ni `data/symbols/**`
    "toujours": False,
    "raison": (
        "Les cinq volets sont OFFLINE et n'ouvrent aucun transport : leur verdict ne depend que "
        "des six foyers ci-dessus et de l'enum qu'ils citent. Aucune donnee de `data/` n'est lue "
        "(les substrats sont SYNTHETIQUES, construits dans le fichier), donc ni le gameconfig ni "
        "la seed BC ne peuvent les faire basculer. Un changement du CAPTEUR (`tileMeta` / "
        "`readTileOccupants`) ne les touche pas non plus -- il ferait bouger la CONFRONTATION "
        "live, qui vit dans le rapport de tranche, pas ici."
    ),
}


# ---------------------------------------------------------------------------------------------
# Substrats synthetiques
# ---------------------------------------------------------------------------------------------
class _Ctx:
    """Le minimum qu'un playbook NonComparable lit : `units` (lignes `decisionView`), `epos`,
    `fpos`, `origin`. MEME forme que ce que `action_generators` construit."""

    def __init__(self, units, epos, fpos, origin):
        self.units, self.epos, self.fpos, self.origin = units, epos, fpos, origin


def _u(uid, col, row, feet=None, alive=True):
    d = {"id": uid, "pos": {"col": col, "row": row}, "alive": alive}
    if feet is not None:
        d["feet"] = [{"col": c, "row": r} for (c, r) in feet]
    return d


# ---------------------------------------------------------------------------------------------
# 1. #969-r3 -- l'occupation PAR PIED
# ---------------------------------------------------------------------------------------------
def test_occupation_multi_hex_ajoute_les_pieds_secondaires():
    """`TileExtensions$$CanAddUnit` interroge le `TileContentComponent` DE LA TUILE : une entite
    multi-hex remplit CHACUN de ses pieds. Le port ne voyait que la MainTile."""
    ctx = _Ctx([_u(1, 0, 0, [(0, 0)]), _u(2, 3, 3, [(3, 3), (4, 3), (3, 4)])],
               epos=[(3, 3)], fpos=[], origin=(0, 0))
    occ = bq.occupied_positions(ctx)
    assert (3, 3) in occ, "la MainTile de l'ennemi doit rester occupee"
    assert (4, 3) in occ and (3, 4) in occ, "les PIEDS SECONDAIRES doivent occuper aussi"
    assert (0, 0) in occ, "l'origine du caster entre par `include_origin` (fpos l'exclut)"


def test_occupation_est_un_noop_exact_hors_multi_hex():
    """CONTRE-EPREUVE de non-regression : sur des unites a un pied, ou sans canal `feet` du tout,
    le foyer rend EXACTEMENT l'ensemble d'avant (`epos | fpos | {origin}`)."""
    avant = {(3, 3), (5, 5), (0, 0)}
    sans_canal = _Ctx([_u(1, 0, 0), _u(2, 3, 3), _u(3, 5, 5)],
                      epos=[(3, 3)], fpos=[(5, 5)], origin=(0, 0))
    un_pied = _Ctx([_u(1, 0, 0, [(0, 0)]), _u(2, 3, 3, [(3, 3)]), _u(3, 5, 5, [(5, 5)])],
                   epos=[(3, 3)], fpos=[(5, 5)], origin=(0, 0))
    assert bq.occupied_positions(sans_canal) == avant, "`feet` absent = NON MESURE, pas un pied"
    assert bq.occupied_positions(un_pied) == avant


def test_occupation_n_elargit_pas_l_univers_de_l_appelant():
    """L'expansion est une correction d'EMPREINTE, jamais d'UNIVERS : une unite que l'appelant n'a
    pas mise dans `epos`/`fpos` (typiquement une MoW, canal `.mows` separe) n'ajoute RIEN."""
    ctx = _Ctx([_u(9, 7, 7, [(7, 7), (8, 7)])], epos=[], fpos=[], origin=None)
    assert bq.occupied_positions(ctx) == set()


def test_occupation_base_explicite_est_respectee():
    """Les deux corps qui derivent leur univers d'`obs_units` passent par `base` : l'expansion s'y
    applique, et `include_origin` n'y ajoute rien."""
    ctx = _Ctx([_u(2, 3, 3, [(3, 3), (4, 3)])], epos=[(3, 3)], fpos=[], origin=(0, 0))
    assert bq.occupied_positions(ctx, base={(3, 3)}) == {(3, 3), (4, 3)}
    assert (0, 0) not in bq.occupied_positions(ctx, include_origin=False)


# ---------------------------------------------------------------------------------------------
# 2. #419-r1-tr11-r1 -- le MIN sur les PIEDS de la cible (1545)
# ---------------------------------------------------------------------------------------------
class _Scene:
    """Le strict necessaire pour `SpecialIssueCombiMeltaPlaybook` : `pos()` et `feet_by_id`."""

    def __init__(self, pos_by_id, feet_by_id=None):
        self.pos_by_id, self.feet_by_id = pos_by_id, (feet_by_id or {})
        self.units = []

    def pos(self, uid):
        return self.pos_by_id.get(uid)


class _Wt:
    def triggered(self, key):
        assert key == "SpecialIssueCombiMelta_LikesRange3"
        return 25.0


class _AtkCtx:
    def __init__(self, scene):
        self.scene, self.wt = scene, _Wt()


def _util_1545(scene, tgt, attack_tile):
    from engine.playbook.special_issue_combi_melta import SpecialIssueCombiMeltaPlaybook
    return SpecialIssueCombiMeltaPlaybook().calculate_attack_utility_in_steps(
        _AtkCtx(scene), 1, 1545, tgt, attack_tile)


def test_1545_cible_multi_hex_le_min_est_pris_sur_les_pieds():
    """`GetDistance(IEntity, IEntity)` resout la cible par `EntityExtensions$$GetTiles` puis prend
    le MIN sur les paires. Cible en MainTile (6,0) -- d=6 -- mais avec un pied en (3,0) : le natif
    rend 3, donc le poids TOMBE. Le port lisait la MainTile SEULE et rendait 0."""
    caster_tile = (0, 0)
    sans_feet = _Scene({7: (6, 0)})
    avec_feet = _Scene({7: (6, 0)}, {7: [(6, 0), (5, 0), (3, 0)]})
    assert _util_1545(sans_feet, 7, caster_tile) == 0.0, "MainTile seule -> d=6, hors gate `== 3`"
    assert _util_1545(avec_feet, 7, caster_tile) == 25.0, "un PIED a d=3 -> le gate passe"


def test_1545_mono_pied_est_un_noop_exact():
    """CONTRE-EPREUVE : sur une cible a un pied, avec ou sans table d'empreinte, le verdict est
    celui d'avant la tranche -- 25 a d==3, 0 partout ailleurs."""
    for scene in (_Scene({7: (3, 0)}), _Scene({7: (3, 0)}, {7: [(3, 0)]})):
        assert _util_1545(scene, 7, (0, 0)) == 25.0
        assert _util_1545(scene, 7, (1, 0)) == 0.0        # d == 2
        assert _util_1545(scene, 7, (5, 0)) == 0.0        # d == 2 de l'autre cote


def test_1545_cible_sans_aucune_tuile_ne_passe_jamais_le_gate():
    """`MovementQuery$$GetDistance` rend `int.MaxValue` des qu'un cote n'a pas de tuile -- jamais
    0, donc `== 3` ne peut pas passer."""
    assert _util_1545(_Scene({}), 7, (0, 0)) == 0.0


# ---------------------------------------------------------------------------------------------
# 3. #433-r4-r3-r3 -- `scene_tile_leaf_ctx` produit `unit_parent_id`
# ---------------------------------------------------------------------------------------------
class _SceneLeaf:
    """`Scene` reduite a ce que `scene_tile_leaf_ctx` interroge."""

    def __init__(self, parent_by_id):
        self.parent_by_id = parent_by_id
        self.units, self.vis_by_id, self.board = [], {}, None
        self.eff_state, self.hpmax_by_id, self.elev_by_pos = None, {}, {}

    def parent(self, uid):
        return self.parent_by_id.get(uid)

    def team(self, uid):
        return 1

    def ctx(self, uid):
        return None

    def pos(self, uid):
        return None

    def hp(self, uid):
        return None

    def hpmax(self, uid):
        return None


def test_scene_tile_leaf_ctx_produit_unit_parent_id():
    """Le TROISIEME jumeau etait le seul a ne pas poser la cle, alors que `Scene.parent` existe
    depuis #378 : les deux feuilles qui la GATENT (`savior_protocols` terme PARENT,
    `playbook/non_owner` gate `GetParent != owner`) rendaient 0 sur la face PREDICTION SEULE."""
    lc = tilemod.scene_tile_leaf_ctx(_SceneLeaf({42: 7}), 42)
    assert "unit_parent_id" in lc, "la cle doit EXISTER (son absence = feuille muette)"
    assert lc["unit_parent_id"] == 7


def test_scene_tile_leaf_ctx_parent_absent_rend_none_pas_une_absence_de_cle():
    """Semantique d'absence IDENTIQUE aux deux autres producteurs : la cle est POSEE a `None`.
    Une cle manquante et une cle a `None` se lisent pareil chez les lecteurs (`.get`), mais la
    poser est ce qui rend le canal VERIFIABLE."""
    lc = tilemod.scene_tile_leaf_ctx(_SceneLeaf({}), 42)
    assert lc["unit_parent_id"] is None


def test_les_trois_producteurs_de_tile_leaf_ctx_portent_la_meme_cle():
    """Le vice ferme ici est un ECART ENTRE JUMEAUX. Le garder exige de comparer les trois
    signatures, pas de re-tester le seul qu'on vient de corriger."""
    import inspect
    src_runner = inspect.getsource(tilemod.runner_tile_leaf_ctx)
    src_scene = inspect.getsource(tilemod.scene_tile_leaf_ctx)
    src_dec = inspect.getsource(tilemod.tile_leaf_ctx)
    for nom, src in (("runner", src_runner), ("scene", src_scene), ("decision", src_dec)):
        assert '"unit_parent_id"' in src, f"le producteur {nom} ne pose plus `unit_parent_id`"


# ---------------------------------------------------------------------------------------------
# 4. #425-r1 -- liste POSSEDEE pour les feuilles, ACTIF-ONLY pour la `Scene`
# ---------------------------------------------------------------------------------------------
_TILES = [
    {"col": 0, "row": 0, "effects": [{"name": "Fire", "effectType": 5, "active": True},
                                     {"name": "Ice", "effectType": 7, "active": False}]},
    {"col": 1, "row": 0, "effects": [{"name": "Thorns_DefenseReduction", "effectType": 11}]},
    {"col": 2, "row": 0, "effects": []},
]


def test_canal_des_feuilles_porte_les_effets_INACTIFS():
    """`TileEffectsUtility.<EvaluateMovementInSteps>d__1$$MoveNext` et
    `DespoiledGroundUtility.<...>d__5$$MoveNext` iterent `EffectsOwnedComponent` SANS gate
    `IsActive` (les deux corps LUS) : un effet pose-mais-inerte compte pour le natif."""
    possedee = aictx._tile_effect_names(_TILES, only_active=False)
    assert possedee[(0, 0)] == ["Fire", "Ice"]


def test_canal_de_la_scene_reste_ACTIF_ONLY():
    """La `Scene` n'est pas lue QUE par des feuilles : les bonus de degat a magnitude
    positionnelle la consomment. L'y basculer serait un elargissement PERMISSIF non confronte."""
    actifs = aictx._tile_effect_names(_TILES, only_active=True)
    assert actifs[(0, 0)] == ["Fire"], "l'effet INACTIF ne doit PAS atteindre la Scene"


def test_les_deux_canaux_DIFFERENT_le_test_n_est_pas_degenere():
    """Sans cette assertion, les deux etages ci-dessus passeraient sur un substrat ou aucun effet
    n'est inactif -- un VERT qui ne mesure rien."""
    a = aictx._tile_effect_names(_TILES, only_active=False)
    b = aictx._tile_effect_names(_TILES, only_active=True)
    assert a != b


def test_effet_sans_flag_active_est_garde_des_deux_cotes():
    """Bundle Frida anterieur au drapeau (ou RPC appele sans lui) : `active` est ABSENT. Absence
    de mesure -> on GARDE, jamais un retrait invente. Les deux tables redeviennent identiques."""
    sans_flag = [{"col": 9, "row": 9, "effects": [{"name": "X", "effectType": 1}]}]
    assert (aictx._tile_effect_names(sans_flag, only_active=False)
            == aictx._tile_effect_names(sans_flag, only_active=True) == {(9, 9): ["X"]})


def test_les_types_d_effet_suivent_la_liste_possedee():
    """`tile_effect_type_ids_by_pos` n'a qu'un lecteur -- `apply_tile_attributes` (feuilles 23/25/28),
    toutes du meme regime sans gate. Elle porte donc l'INACTIF aussi."""
    _terr, tids = aictx._tile_attribute_maps(_TILES)
    assert tids[(0, 0)] == [5, 7]


# ---------------------------------------------------------------------------------------------
# 5. #433-r4-r2-r1-r1-a-r1 -- la tuile OCCUPEE, et le tri-etat DERIVE
# ---------------------------------------------------------------------------------------------
_AID_EMPTY_GATE = int(ActiveAbilityType.DeathOnTheWind)   # 1213


def test_le_regime_du_gate_est_bien_celui_qu_on_croit():
    """Assertionner sa propre premisse : si `1213` cessait d'etre `GATE_VALID_ON_EMPTY_TILE`, les
    deux etages suivants passeraient pour de mauvaises raisons."""
    assert ar.dynamic_target_gate_of(_AID_EMPTY_GATE) == ar.GATE_VALID_ON_EMPTY_TILE


def test_gate_retire_la_tuile_occupee_et_garde_la_tuile_libre():
    """`DeathOnTheWindAbility$$GetDynamicInvalidTargetReason` : `GetUnit(tile)` nul -> `0` (valide),
    sinon il exige `GetNumAttacksReceivedThisTurn != 0`. Le port ne modelisait AUCUN retrait."""
    caster, tile = (0, 0), (4, 0)
    libre = ar.is_tile_in_range_of_any_ability(caster, tile, None, ability_ids=[_AID_EMPTY_GATE],
                                               occupant_by_pos={(9, 9): 77})
    occupee = ar.is_tile_in_range_of_any_ability(caster, tile, None, ability_ids=[_AID_EMPTY_GATE],
                                                 occupant_by_pos={(4, 0): 77})
    assert libre is True and occupee is False


def test_canal_absent_ne_retire_rien_statu_quo():
    """`None` = non mesure. La degradation reste PERMISSIVE, c.-a-d. EXACTEMENT le comportement
    d'avant la tranche -- jamais un refus invente sur une donnee non lue."""
    assert ar.is_tile_in_range_of_any_ability((0, 0), (4, 0), None,
                                              ability_ids=[_AID_EMPTY_GATE]) is True


def test_tri_etat_du_canal_occupant_est_DERIVE_pas_un_bool():
    """Le vice #943-r8 : un transport MORT ressemble a une mesure honnete. Une table VIDE alors que
    des unites sont vivantes et positionnees ne peut etre qu'un capteur muet -- c'est le temoin NON
    DEGENERE, et il se derive sans second canal."""
    units = [{"id": 1, "alive": True, "pos": {"col": 0, "row": 0}}]
    assert aictx.occupant_channel_is_measured({}, units) is False, "capteur MUET, pas un plateau libre"
    assert aictx.occupant_channel_is_measured({}, []) is True, "aucune unite -> le vide EST la mesure"
    assert aictx.occupant_channel_is_measured({(1, 1): 5}, units) is True


def test_occupant_by_pos_ne_porte_que_les_tuiles_OCCUPEES():
    """Une tuile libre est ABSENTE de la table, jamais presente a `None` : c'est ce qui autorise le
    consommateur a tester `.get(pos) is not None`."""
    m = aictx._occupant_by_pos([{"col": 0, "row": 0, "occupantId": 12},
                                {"col": 1, "row": 0, "occupantId": None},
                                {"col": 2, "row": 0}])
    assert m == {(0, 0): 12}


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-q"]))
