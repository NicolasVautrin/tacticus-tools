"""#943-r7 -- les HUIT sites recables decident-ils sur la LISTE STOCKEE, et les DEUX FACES
repondent-elles PAREIL ?

`probe_433r4r1r4r2_neigh_channel_wired` garde la FORME (le canal est passe, consomme, et la
geometrie ne decide pas malgre lui). Il ne dit RIEN du COMPORTEMENT : un port peut recevoir le
canal, le lire, et rendre le meme verdict qu'avant. Ce fichier-ci mesure le VERDICT -- et, pour le
foyer commun, l'ACCORD DES DEUX FACES, qui est l'objet meme du residu.

LE SCENARIO EST CRAFTE POUR QUE LE CABLAGE CHANGE LE RESULTAT, jamais << pris tel quel >> : deux
tuiles a distance hex **1** qui ne sont **PAS** voisines dans la liste stockee du
`ConnectivityComponent`. Regime REEL, pas une curiosite -- mesure live du 2026-08-12
(`probe_433r4r1r4r2_is_adjacent_substrat_live.py --board MC2_60 --board C4_69`) : **22** aretes de
ce type sur `MC2_60` et **8** sur `C4_69`, pour **0** dans l'autre sens.

⚠ CE QUE CE FICHIER NE MESURE PAS, et le dire evite de croire qu'une mesure couvre l'autre : la
PORTE d'elevation (`|dElev| < 2`) est le SECOND etage, et les deux ecarts sont DISJOINTS -- sur les
22 aretes de `MC2_60`, `|dElev|` vaut 0 ou 1 (elles tombent par l'ENUMERATION, pas par la porte),
alors qu'offline la porte seule coupe 8,9 % des aretes des 779 boards versionnes. Ici on exerce
l'ENUMERATION ; la porte a ses gardes dans `test_943r4_adjacence_cablee_offline.py`.

LES HUIT SITES, ET POURQUOI CEUX-LA (le tri est dans le registre de `probe_433r4r1r4r2`) : leur
face JUMELLE lit DEJA un substrat stocke, donc le cablage RESORBE une divergence de faces au lieu
d'en creer une. Les onze autres `LISTE_STOCKEE` restent nus, et c'est DELIBERE.

100 % OFFLINE, aucun runner. ASCII only.
"""
#: Ce qui doit changer pour que ces gardes puissent changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des conftest et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER. Le verdict traverse le foyer commun
        # (`entities/effect_targets.py`), ses DEUX substrats (`playbook/scene.py`,
        # `runner/components.py`), trois faces DECISION (`playbook/psyker.py`,
        # `playbook/prediction/abilities.py`, `playbook/noncomparable/get_em_runtz.py`), le foyer
        # de l'adjacence (`engine/battle_query.py`) et les DEUX foyers de canal
        # (`entities/pathfinding/board.py`) -- plus tout ce que la cascade tire au chargement.
        # Une liste choisie ne tiendrait pas : `engine/**` en entier.
        "scripts/python/engine/**/*.py",
        "scripts/python/*.py",
        # ENTREE VERSIONNEE lue pendant la passe : la cascade des conftest la charge.
        "data/seed-bc.json",
    ),
    "build": False,
    "toujours": False,
    "raison": "Gardes OFFLINE du recablage d'adjacence des faces jumelles : le board temoin est un "
              "VRAI `Board` bati en memoire, donc aucun runner n'est monte et le build n'entre pas "
              "au declencheur. La confrontation LIVE du substrat vit dans "
              "`probe_433r4r1r4r2_is_adjacent_substrat_live.py`.",
}

import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0].rstrip("\\/"))

import hexgeo                                                              # noqa: E402
from engine import battle_query as bq                                      # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.playbook.scene import Scene                                    # noqa: E402

COLS = ROWS = 5


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _board(coupe=(), with_neighbours: bool = True, elev=None) -> Board:
    """Board 5x5 plein. `coupe` = aretes NON DIRIGEES retirees du champ `neighbours` des DEUX cotes
    -- le patron `Bridge` mesure live (le `ConnectivityComponent` ne relie pas le pont a son voisin
    de niveau, alors que la couronne hex, elle, les voit adjacents).

    `with_neighbours=False` retire le CHAMP : c'est l'etat << canal absent >> (board bati a la main,
    `boardGraph` anterieur au capteur), a ne PAS confondre avec une liste vide (#381-r3)."""
    elev = elev or {}
    coupees = set()
    for (a, b) in coupe:
        coupees.add((a, b))
        coupees.add((b, a))
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            t = {"id": _tid(col, row), "col": col, "row": row, "walkable": True,
                 "isWall": False, "elevation": int(elev.get((col, row), 0))}
            if with_neighbours:
                t["neighbours"] = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                                   if 0 <= c < COLS and 0 <= r < ROWS
                                   and ((col, row), (c, r)) not in coupees]
            tiles.append(t)
    return Board(tiles)


def _board_dirige(depuis, vers) -> Board:
    """Board 5x5 dont l'arete `depuis -> vers` est retiree D'UN SEUL COTE.

    Sert au SEUL cran qui mesure la DIRECTION : le champ `neighbours` est le champ BRUT du
    `boardGraph` (`Board.neighbours_native` : ni trie ni symetrise), donc `is_adjacent(a, b)` -- qui
    lit `neigh[a]` -- n'est PAS le meme predicat que `is_adjacent(b, a)`. La couronne hex, elle, est
    symetrique par construction : l'ancien port ne POUVAIT pas voir cet axe."""
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            v = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                 if 0 <= c < COLS and 0 <= r < ROWS
                 and not ((col, row) == depuis and (c, r) == vers)]
            tiles.append({"id": _tid(col, row), "col": col, "row": row, "walkable": True,
                          "isWall": False, "elevation": 0, "neighbours": v})
    return Board(tiles)


#: Le patron mesure : `PORTEUR` et `AMI` sont hex-voisins, et c'est CETTE arete qu'on coupe de la
#: liste stockee. `AUTRE` est le TEMOIN NON NUL -- une arete que la liste PORTE.
PORTEUR = (2, 2)
AMI = hexgeo.neighbors(2, 2)[0]        # (2, 3)
AUTRE = hexgeo.neighbors(2, 2)[1]      # (2, 1) -- voisin de PORTEUR, mais PAS d'AMI
LOIN = (0, 0)


def test_le_montage_est_bien_DISCRIMINANT():
    """PREMISSE. Sans ce cran, tous les autres pourraient etre verts pour la mauvaise raison : il
    faut que l'arete coupee soit VRAIMENT dans la couronne (sinon l'ecart mesure n'en est pas un),
    et que le temoin `AUTRE` soit une VRAIE arete de la liste stockee."""
    from engine.entities.pathfinding.board import adjacent_neigh_by_pos, elevations_by_pos
    assert hexgeo.distance(PORTEUR, AMI) == 1
    assert hexgeo.distance(PORTEUR, AUTRE) == 1 and AUTRE != AMI
    assert hexgeo.distance(PORTEUR, LOIN) > 1
    bd = _board(coupe=[(PORTEUR, AMI)])
    neigh, elev = adjacent_neigh_by_pos(bd), elevations_by_pos(bd)
    assert neigh is not None, "canal absent : le montage ne mesurerait rien"
    assert bq.is_adjacent(PORTEUR, AMI, elev, neigh) is False     # coupee -> le natif dit FAUX
    assert bq.is_adjacent(PORTEUR, AUTRE, elev, neigh) is True    # temoin NON NUL


# --------------------------------------------------------------------------------------------
# 1. LE FOYER COMMUN -- `entities/effect_targets.py::_adjacent_friends`, et l'ACCORD DES 2 FACES
# --------------------------------------------------------------------------------------------

def _scene(board, units, pos_by_id, team_by_id, eff_state=None) -> Scene:
    from engine.entities.pathfinding.board import elevations_by_pos
    return Scene(ctx_by_id={}, armor_by_id={}, shield_by_id={}, mult_by_id={}, ablvl_by_id={},
                 vis_by_id={}, units=units, hp_by_id={}, pos_by_id=pos_by_id,
                 team_by_id=team_by_id, eff_state=eff_state, board=board,
                 elev_by_pos=elevations_by_pos(board))


class _EffState:
    """`EffectsState` minimale : `has_effect(uid, type)` seul, ce que lit `world.carries`."""

    def __init__(self, porte):
        self.porte = {(int(u), int(t)) for (u, t) in porte}

    def has_effect(self, uid, effect_type, *a, **kw):
        return (int(uid), int(effect_type)) in self.porte


BIG_TARGET = int(EffectType.BigTarget_AdjacentEffect)      # 1026


def _monde_runner(board, positions, teams, porte):
    """Un `State` ECS minimal, substrat de `_RunnerEffectTargetWorld`."""
    from engine.runner.components import (OwnerComponent, PositionComponent, UnitComponent)
    from engine.runner.state import State
    st = State()
    st.board = board
    for uid, p in positions.items():
        e = st.add_entity(uid)
        e.add_component(PositionComponent(col=p[0], row=p[1]))
        e.add_component(OwnerComponent(team=teams[uid]))
        e.add_component(UnitComponent(visual_id="t", alive=True))
    st.effects = _EffState(porte)
    return st


@pytest.mark.parametrize("coupe,attendu", [(True, False), (False, True)])
def test_les_DEUX_faces_de_is_effect_target_suivent_la_liste_stockee(coupe, attendu):
    """LE CRAN CENTRAL DU RESIDU. `BigTargetAdjacentEffect$$CreateTargetSelector` =
    `AdjacentFriends(Owner, unitTile, unique)` -> `AdjacentTiles` -> `IterateAdjacentTiles`.

    Le port n'a qu'UN foyer (`entities/effect_targets.py::_adjacent_friends`) pour DEUX substrats
    (`_SceneEffectTargetWorld` cote decision, `_RunnerEffectTargetWorld` cote combat). Ce test
    exige les DEUX choses a la fois : que le verdict suive la LISTE STOCKEE, et que les deux faces
    rendent LA MEME chose -- une divergence ici serait exactement le vice que le residu combat.

    `u1` porte l'effet 1026 ; `u2` est son ami hex-voisin. Arete COUPEE -> le natif ne fait PAS de
    `u2` une cible ; arete PORTEE -> il le fait."""
    from engine.playbook.scene import _SceneEffectTargetWorld
    from engine.runner.components import _RunnerEffectTargetWorld
    from engine.entities.effect_targets import is_effect_target as foyer

    bd = _board(coupe=[(PORTEUR, AMI)] if coupe else [])
    positions = {1: PORTEUR, 2: AMI}
    teams = {1: 1, 2: 1}                       # AdjacentFriends : MEME equipe
    porte = [(1, BIG_TARGET)]                  # u1 est OWNER de l'effet

    sc = _scene(bd, [{"id": 1, "team": 1, "alive": True}, {"id": 2, "team": 1, "alive": True}],
                positions, teams, _EffState(porte))
    face_decision = foyer(_SceneEffectTargetWorld(sc), 2, BIG_TARGET)

    st = _monde_runner(bd, positions, teams, porte)
    face_combat = foyer(_RunnerEffectTargetWorld(st), 2, BIG_TARGET)

    assert face_decision is attendu, "face DECISION"
    assert face_combat is attendu, "face COMBAT"
    assert face_decision == face_combat, (
        "LES DEUX FACES DIVERGENT sur le meme selecteur natif -- c'est le vice que #943-r7 combat")


def test_sans_canal_le_foyer_commun_DEGRADE_en_couronne_hex():
    """CONTRE-EPREUVE. Sans le canal (`neighbours` ABSENT du board), le verdict doit etre l'ANCIEN
    -- sinon le cablage aurait change le comportement des montages qui n'ont pas de graphe, ce qui
    serait une regression et non une reparation. C'est le repli NOMME d'`is_adjacent`."""
    from engine.playbook.scene import _SceneEffectTargetWorld
    from engine.entities.effect_targets import is_effect_target as foyer

    bd = _board(with_neighbours=False)          # champ ABSENT != champ VIDE (#381-r3)
    sc = _scene(bd, [{"id": 1, "team": 1, "alive": True}, {"id": 2, "team": 1, "alive": True}],
                {1: PORTEUR, 2: AMI}, {1: 1, 2: 1}, _EffState([(1, BIG_TARGET)]))
    assert foyer(_SceneEffectTargetWorld(sc), 2, BIG_TARGET) is True


def test_le_protocole_EXIGE_le_canal_au_lieu_de_le_deviner():
    """`EffectTargetWorld` DECLARE `neigh_by_pos()`/`elev_by_pos()` : un substrat tiers qui ne les
    implemente pas doit LEVER, pas degrader en silence.

    Sans ce cran, la parade evidente serait un `getattr(world, ..., None)` defensif -- qui ferait
    passer un substrat incomplet pour un substrat sans canal, et rouvrirait le trou EN SILENCE."""
    from engine.entities.effect_targets import EffectTargetWorld
    with pytest.raises(NotImplementedError):
        EffectTargetWorld().neigh_by_pos()
    with pytest.raises(NotImplementedError):
        EffectTargetWorld().elev_by_pos()


# --------------------------------------------------------------------------------------------
# 2. LES QUATRE COMPTEURS DE `Scene` -- faces DECISION dont la jumelle COMBAT est deja cablee
# --------------------------------------------------------------------------------------------

TAUNTED = int(EffectType.Taunted_OnlySpecificTargets)      # 27
LIGHT_COVER = int(EffectType.LightCover)                   # 1013


@pytest.mark.parametrize("coupe,attendu", [(True, 0), (False, 1)])
def test_adjacent_taunted_enemies_suit_la_liste_stockee(coupe, attendu):
    """`ADaemonicPatronsEffect$$GetNumAdjacentTauntedEnemies` = `Count(Filter(AdjacentEnemies(Owner,
    1, 3), HasEffect(It, 27)))`. Jumelle COMBAT : `runner.components.
    adjacent_taunted_enemies_count`, qui execute l'arbre DSL -- donc deja sur la liste stockee."""
    bd = _board(coupe=[(PORTEUR, AMI)] if coupe else [])
    sc = _scene(bd, [{"id": 1, "team": 1, "alive": True}, {"id": 2, "team": 2, "alive": True}],
                {1: PORTEUR, 2: AMI}, {1: 1, 2: 2}, _EffState([(2, TAUNTED)]))
    assert sc.adjacent_taunted_enemies(1) == attendu


def test_adjacent_taunted_enemies_garde_son_TEMOIN_non_nul():
    """Un ennemi taunte sur une arete que la liste PORTE reste compte : sans ce cran, le test
    ci-dessus serait vert meme si le compteur rendait 0 partout."""
    bd = _board(coupe=[(PORTEUR, AMI)])
    sc = _scene(bd, [{"id": 1, "team": 1, "alive": True}, {"id": 3, "team": 2, "alive": True}],
                {1: PORTEUR, 3: AUTRE}, {1: 1, 3: 2}, _EffState([(3, TAUNTED)]))
    assert sc.adjacent_taunted_enemies(1) == 1


@pytest.mark.parametrize("coupe,attendu", [(True, 0), (False, 1)])
def test_enmity_adjacent_units_suit_la_liste_stockee(coupe, attendu):
    """`EnmityForTheUnworthy_ExtraDamagePctEffect$$AdjacentUnitsAmount` =
    `Count(NonSteppableOrObjectUnits(AdjacentUnits(Owner, 1, 3), 3))` -- AUCUN filtre d'equipe.
    Jumelle COMBAT : `runner.components.enmity_adjacent_units_count` (arbre DSL)."""
    bd = _board(coupe=[(PORTEUR, AMI)] if coupe else [])
    sc = _scene(bd, [{"id": 1, "team": 1, "alive": True}, {"id": 2, "team": 2, "alive": True}],
                {1: PORTEUR, 2: AMI}, {1: 1, 2: 2})
    assert sc.enmity_adjacent_units(1) == attendu


@pytest.mark.parametrize("coupe,attendu", [(True, False), (False, True)])
def test_camo_cloak_cover_suit_la_liste_stockee_ET_son_foyer(coupe, attendu):
    """`CamoCloak_DmgReductionEffect$$HasValidEffectTrigger` = `HasEffect(1013) | IsEffectTarget(
    1026)`. Le second membre recompose `_adjacent_friends` A LA MAIN sur les tables de `Scene` : il
    doit donc suivre le MEME substrat que le foyer, cable dans le MEME commit.

    `u1` est le sujet ; `u2`, son ami hex-voisin, PORTE l'aura 1026."""
    bd = _board(coupe=[(PORTEUR, AMI)] if coupe else [])
    sc = _scene(bd, [{"id": 1, "team": 1, "alive": True}, {"id": 2, "team": 1, "alive": True}],
                {1: PORTEUR, 2: AMI}, {1: 1, 2: 1}, _EffState([(2, BIG_TARGET)]))
    out: dict = {}
    sc._camo_cloak_cover_keys(1, out)
    assert out["is_target_of_big_target_adjacent"] is attendu
    # la cle SOEUR (`HasEffect(1013)`) ne depend d'aucune geometrie : elle ne doit pas bouger
    assert out["has_effect_light_cover"] is False


# --------------------------------------------------------------------------------------------
# 3. LES TROIS AUTRES FACES DECISION
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("coupe,attendu", [(True, []), (False, [3])])
def test_psyker_possible_targets_suit_la_liste_stockee(coupe, attendu):
    """`PsykerExtraAttackAbility$$PossibleTargets` = `Damageable(Enemies(caster,
    AdjacentUnits(CIBLE, 1)))`. La docstring du port AFFIRMAIT << adjacence GEOMETRIQUE hex >> --
    REFUTE par le decompile (`AdjacentUnits` -> `AdjacentTiles` -> `IterateAdjacentTiles`).

    `u1` = caster (team 1) ; `u2` = la cible du case (team 2) ; `u3` = un autre ennemi, hex-voisin
    de la CIBLE. C'est l'arete CIBLE--u3 qui est coupee."""
    from engine.playbook.psyker import PsykerPlaybook
    bd = _board(coupe=[(PORTEUR, AMI)] if coupe else [])
    sc = _scene(bd, [{"id": 1, "team": 1, "alive": True}, {"id": 2, "team": 2, "alive": True},
                     {"id": 3, "team": 2, "alive": True}],
                {1: LOIN, 2: PORTEUR, 3: AMI}, {1: 1, 2: 2, 3: 2})
    assert PsykerPlaybook().possible_targets(sc, 1, 2) == attendu


def _scene_hammer(board):
    """`Scene` portant de quoi traverser `make_hammer_wrath_events` jusqu'au SELECTEUR.

    `u1` = le caster (team 1) place LOIN ; `u2` = la cible (team 2) en `PORTEUR` ; `u3` = un second
    ennemi en `AMI`, hex-voisin de la cible. C'est l'arete `PORTEUR--AMI` qu'on coupe.

    Le `UnitContext` est REEL (pas un duck-type) : `active_ability_for` le consomme pour resoudre
    niveau et multiplicateur, et un stub y ferait echouer le montage en amont du selecteur -- donc
    pour une raison etrangere a l'adjacence."""
    from engine.entities.unit_context import UnitContext
    from engine.entities.pathfinding.board import elevations_by_pos
    uc = UnitContext(entity_id=1, visual_id="bloodIntercessor", active_ability_level=50)
    return Scene(ctx_by_id={1: uc}, armor_by_id={}, shield_by_id={}, mult_by_id={1: 100},
                 ablvl_by_id={1: 50}, vis_by_id={1: "bloodIntercessor"},
                 units=[{"id": 1, "team": 1, "alive": True}, {"id": 2, "team": 2, "alive": True},
                        {"id": 3, "team": 2, "alive": True}],
                 hp_by_id={1: 100, 2: 100, 3: 100},
                 pos_by_id={1: LOIN, 2: PORTEUR, 3: AMI}, team_by_id={1: 1, 2: 2, 3: 2},
                 eff_state=None, board=board, elev_by_pos=elevations_by_pos(board))


@pytest.mark.parametrize("coupe,secondaires", [(True, 0), (False, 1)])
def test_hammer_of_wrath_secondaries_suivent_la_liste_stockee(coupe, secondaires, monkeypatch):
    """`HammerOfWrathAbility$$GetAdjacentTargets` = `Enemies(caster, AdjacentUnits(target, 1))`.
    Jumelle COMBAT : `runner/abilities/bloodangels.py::hammer_of_wrath_get_adjacent_targets`, un
    arbre DSL -- donc DEJA sur la liste stockee. Cabler ici RESORBE.

    ⚠ MONTAGE : on SUBSTITUE `generate_multi_hit_attack_prediction` pour isoler le SELECTEUR du
    pipeline de degat (armure, spread, mods positionnels), etranger a l'adjacence. Le stub rend une
    sentinelle NON-`None` -- sinon le test serait vert par absence de PREDICTION et non par absence
    de CIBLE, un regime degenere qui ne prouverait rien. Il enregistre aussi les cibles appelees,
    pour que le compte d'events ne puisse pas etre juste par compensation."""
    from engine.playbook.prediction import abilities as A

    appels: list = []

    def _stub(scene, caster_id, target_id, *a, **kw):
        appels.append(int(target_id))
        return object()                      # non-`None` : sinon l'event serait filtre en aval

    # forme B : `make_hammer_wrath_events` appelle le nom en GLOBAL du module -> le patch MORD.
    monkeypatch.setattr(A, "generate_multi_hit_attack_prediction", _stub)
    sc = _scene_hammer(_board(coupe=[(PORTEUR, AMI)] if coupe else []))
    events = A.make_hammer_wrath_events(sc, 1, 2, LOIN)
    assert events, "montage CASSE : aucun event, pas meme le PRIMARY -- le test ne mesure rien"
    assert len(events) == 1 + secondaires          # 1 PRIMARY (la cible) + les SECONDARY
    assert appels == [2] + ([3] if secondaires else [])


#: Le CASTER de GetEmRuntz, un ENNEMI, et la tuile de spawn `T` qui est voisine des DEUX (c'est la
#: conjonction meme du selecteur). Positions LUES de `hexgeo`, pas devinees -- cf. la premisse.
GER_CASTER = (2, 2)
GER_ENNEMI = (3, 3)
GER_TUILE = (2, 3)


def _ctx_runtz(board):
    from engine.playbook.noncomparable._base import NCContext
    from engine.entities.pathfinding.board import adjacent_neigh_by_pos, elevations_by_pos
    return NCContext(uid=1, origin=GER_CASTER, reach_nc=set(), epos=[GER_ENNEMI], fpos=[],
                     plan=None, hp_cur_by_id={}, elev_by_pos=elevations_by_pos(board),
                     neigh_by_pos=adjacent_neigh_by_pos(board))


def test_get_em_runtz_le_montage_est_DISCRIMINANT():
    """PREMISSE : `T` doit etre voisin du CASTER **et** de l'ENNEMI, sinon couper une arete ne
    prouverait rien -- la conjonction du selecteur ne serait deja pas satisfaite."""
    assert hexgeo.distance(GER_CASTER, GER_TUILE) == 1
    assert hexgeo.distance(GER_ENNEMI, GER_TUILE) == 1
    from engine.playbook.noncomparable.get_em_runtz import GetEmRuntzPlaybook
    assert GetEmRuntzPlaybook()._spawn_tile_count(_ctx_runtz(_board())) > 0, "temoin NUL"


@pytest.mark.parametrize("arete", [(GER_CASTER, GER_TUILE), (GER_ENNEMI, GER_TUILE)])
def test_get_em_runtz_les_DEUX_AdjacentTiles_portent_le_substrat_stocke(arete):
    """`GetEmRuntzAbility$$GetSpawnTileSelector` -- DECOMPILE RELU (#943-r7) :

        CanAddUnit( AdjacentTiles(Caster@+0x50) )
      & Unique( AdjacentTiles( UnitsWithoutTrait(Enemies(...), 0x1b = Steppable, 3) ) )

    DEUX `AdjacentTiles`, donc les DEUX comparaisons portent le substrat stocke. Ce test coupe
    CHACUNE des deux aretes a son tour : l'une comme l'autre doit retirer `T` du compte. Un port
    qui n'aurait cable que la premiere serait vert sur le premier cas et ROUGE sur le second."""
    from engine.playbook.noncomparable.get_em_runtz import GetEmRuntzPlaybook
    p = GetEmRuntzPlaybook()
    base = p._spawn_tile_count(_ctx_runtz(_board()))
    coupe = p._spawn_tile_count(_ctx_runtz(_board(coupe=[arete])))
    assert base > 0, "temoin NUL : le montage ne mesure rien"
    assert coupe == base - 1, (
        "couper l'arete %s doit retirer EXACTEMENT la tuile de spawn du compte" % (arete,))


def test_get_em_runtz_lit_la_DIRECTION_du_second_AdjacentTiles():
    """LE CRAN QUE LA GEOMETRIE NE POUVAIT PAS PORTER. `AdjacentTiles(source)` enumere le voisinage
    de la tuile SOURCE, et le champ `neighbours` est BRUT (ni trie ni symetrise, cf.
    `Board.neighbours_native`) : le second terme du selecteur est `AdjacentTiles(ENNEMIS)`, donc
    `is_adjacent(ennemi, T)` -- pas l'inverse.

    On retire l'arete `ennemi -> T` D'UN SEUL COTE ; `T -> ennemi` reste. Un port qui aurait ecrit
    les arguments a l'envers compterait encore la tuile. `hexgeo.distance`, symetrique par
    construction, ne pouvait de toute facon pas distinguer les deux sens -- ce cran ne devient
    observable QU'APRES le cablage."""
    from engine.playbook.noncomparable.get_em_runtz import GetEmRuntzPlaybook
    from engine.entities.pathfinding.board import adjacent_neigh_by_pos
    p = GetEmRuntzPlaybook()
    bd = _board_dirige(depuis=GER_ENNEMI, vers=GER_TUILE)
    neigh = adjacent_neigh_by_pos(bd)
    # PREMISSE : l'asymetrie existe VRAIMENT dans le canal, et dans CE sens-la seulement
    assert GER_TUILE not in [tuple(x) for x in neigh[GER_ENNEMI]]
    assert GER_ENNEMI in [tuple(x) for x in neigh[GER_TUILE]]
    base = p._spawn_tile_count(_ctx_runtz(_board()))
    assert p._spawn_tile_count(_ctx_runtz(bd)) == base - 1, (
        "le second `AdjacentTiles` doit lire le voisinage de l'ENNEMI (`is_adjacent(e, T)`), "
        "pas celui de la tuile")


def test_get_em_runtz_sans_canal_DEGRADE_en_couronne_hex():
    """CONTRE-EPREUVE : sans canal, le compte est l'ANCIEN. Le cablage ne doit rien changer aux
    montages sans graphe -- `is_adjacent` degrade SEUL, c'est son repli NOMME."""
    from engine.playbook.noncomparable.get_em_runtz import GetEmRuntzPlaybook
    p = GetEmRuntzPlaybook()
    avec = p._spawn_tile_count(_ctx_runtz(_board()))
    sans = p._spawn_tile_count(_ctx_runtz(_board(with_neighbours=False)))
    assert sans == avec > 0, "sans canal, le compte doit rester celui de la couronne hex"
