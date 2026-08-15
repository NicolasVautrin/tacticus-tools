"""#943-r7 -- les DIX-NEUF sites recables decident-ils sur la LISTE STOCKEE, et les DEUX FACES
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

LES SS1-3 COUVRENT LES HUIT PREMIERS (2026-08-12), ET LE CRITERE QUI LES AVAIT CHOISIS ETAIT
L'ETAT DE LA FACE JUMELLE : la leur lisait DEJA un substrat stocke, donc le cablage RESORBAIT une
divergence au lieu d'en creer une.

LA SS4 COUVRE LES ONZE DERNIERS (2026-08-15), et leur blocage ecrit (`BLOCAGE: seeding`) etait plus
LARGE que le fait -- RE-MESURE site par site : trois avaient DEJA `ctx["board"]` sur leurs deux
faces, cinq ne demandaient qu'UNE cle ajoutee a un dict dont le constructeur tenait le board, le
COUPLE `IconOfObstinacy` se fermait des que sa jumelle etait cablable, et le seul dont l'analyse
tenait (`momentum`) l'etait pour une AUTRE raison : SUBSTRAT AUTRE (`ConnectivityComponent` BRUT,
sans porte d'elevation).

⚠ LE `momentum` EST LE SEUL DONT LE CANAL N'EXISTE QU'EN LIVE : le champ `connectivity` du
`boardGraph` est construit en bataille par `InitializeConnectivityOperation$$Execute`, et les
`data/boards/*.json` sont des ASSETS. Le board TEMOIN de ce fichier le fabrique (`connectivite=True`)
-- ce qui exerce le PREDICAT, pas la capture. La confrontation LIVE du champ reste due.

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


def _board(coupe=(), with_neighbours: bool = True, elev=None,
           connectivite=None, coupe_connectivite=()) -> Board:
    """Board 5x5 plein. `coupe` = aretes NON DIRIGEES retirees du champ `neighbours` des DEUX cotes
    -- le patron `Bridge` mesure live (le `ConnectivityComponent` ne relie pas le pont a son voisin
    de niveau, alors que la couronne hex, elle, les voit adjacents).

    `with_neighbours=False` retire le CHAMP : c'est l'etat << canal absent >> (board bati a la main,
    `boardGraph` anterieur au capteur), a ne PAS confondre avec une liste vide (#381-r3).

    `connectivite=True` ajoute le champ `connectivity` -- le `ConnectivityComponent` BRUT, SANS la
    porte `|dElev| < 2` (#448-r1-r1-r1-r1-r2). C'est le canal que lit `TileExtensions$$IsNeighbourOf`
    (#943-r7, `momentum`), et il est DISTINCT de `neighbours` : le laisser absent est le regime des
    `data/boards/*.json` versionnes, qui sont des ASSETS. `coupe_connectivite` coupe des aretes de
    CE champ-la seulement."""
    elev = elev or {}
    coupees = set()
    for (a, b) in coupe:
        coupees.add((a, b))
        coupees.add((b, a))
    coupees_conn = set()
    for (a, b) in coupe_connectivite:
        coupees_conn.add((a, b))
        coupees_conn.add((b, a))
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            t = {"id": _tid(col, row), "col": col, "row": row, "walkable": True,
                 "isWall": False, "elevation": int(elev.get((col, row), 0))}
            if with_neighbours:
                t["neighbours"] = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                                   if 0 <= c < COLS and 0 <= r < ROWS
                                   and ((col, row), (c, r)) not in coupees]
            if connectivite:
                t["connectivity"] = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                                     if 0 <= c < COLS and 0 <= r < ROWS
                                     and ((col, row), (c, r)) not in coupees_conn]
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
#: Un voisin d'`AMI` qui n'est PAS `PORTEUR` -- le TIERS des montages a trois unites (#943-r7 SS4 :
#: l'allie de `LegendaryCommander`, le second Ork de `GetStuckIn`). DERIVE de `hexgeo`, pas ecrit :
#: une coordonnee en dur se perimerait au moindre changement de repere, et la premisse ci-dessous
#: la re-mesure a chaque passe.
AUTRE_VOISIN_D_AMI = next(p for p in hexgeo.neighbors(*AMI)
                          if tuple(p) != PORTEUR and 0 <= p[0] < COLS and 0 <= p[1] < ROWS)


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


# ============================================================================================
# 4. LES ONZE DERNIERS (#943-r7, 2026-08-15) -- les ctx d'AURA, le COUPLE, et le SUBSTRAT AUTRE
# ============================================================================================
#
# Ce qui les bloquait etait ecrit `BLOCAGE: seeding` (<< les cabler exige de PUBLIER les deux cartes
# en amont, dans `damage_model.attacker_modifiers` ET dans la face PREDICTION >>). RE-MESURE : c'est
# plus LARGE que le fait. Trois d'entre eux avaient DEJA `ctx["board"]` sur leurs deux faces ; pour
# les autres le seeding tient en UNE cle ajoutee a un dict dont le constructeur avait le board sous
# la main. Le seul dont l'analyse tenait est `momentum`, et pour une autre raison : SUBSTRAT AUTRE.
#
# CHAQUE test ci-dessous exerce le regime DISCRIMINANT (arete de la liste stockee coupee alors que
# la couronne hex la voit), garde un TEMOIN NON NUL, et verifie le repli SANS canal.


def _ch(board):
    """`(elev_by_pos, neigh_by_pos)` du board temoin -- le MEME foyer que les ports."""
    from engine.entities.pathfinding.board import adjacency_channels
    return adjacency_channels(board)


def test_le_montage_a_TROIS_unites_est_DISCRIMINANT():
    """PREMISSE des montages de la SS4. Sans ce cran, couper une arete ne prouverait rien : il faut
    que le TIERS soit voisin d'`AMI` (donc comptable) et DISTINCT de `PORTEUR`."""
    assert hexgeo.distance(AMI, AUTRE_VOISIN_D_AMI) == 1
    assert AUTRE_VOISIN_D_AMI != PORTEUR
    _elev, neigh = _ch(_board())
    assert AUTRE_VOISIN_D_AMI in [tuple(x) for x in neigh[AMI]], "temoin NUL dans la liste stockee"


# ---- 4.1 les DEUX ctx d'aura de `DoctrinaImperatives` (`imperative.py`) --------------------------

def _protector(level=50, mult=180):
    from engine.entities.effects.loki.imperative import ProtectorImperativeEffect
    return ProtectorImperativeEffect("ProtectorImperative")


def _conqueror(level=50, mult=180):
    from engine.entities.effects.loki.imperative import ConquerorImperativeEffect
    e = ConquerorImperativeEffect("ConquerorImperative")
    e.active_ability_level, e.ability_variables_multiplier = level, mult
    return e


@pytest.mark.parametrize("coupe,attendu", [(True, None), (False, "non nul")])
def test_protector_imperative_armure_suit_la_liste_stockee(coupe, attendu):
    """`ConquerorImperativeEffect$$CreateTargetSelector` = self + `AdjacentFriends(Owner, unique, 3)`
    filtre `UnitsWithTrait(5 = Mechanical)`. `AdjacentFriends(unit, ...)` =
    `Friends(unit, Units(AdjacentTiles(unit), ...) - unit, ...)` -- LU : l'ENUMERATION part du
    PORTEUR, sur la liste STOCKEE.

    Le canal entre par `ctx["board"]`, pose par `damage_model.defender_fixed_armor` (face UNIQUE :
    la prediction IA est PRE-armure)."""
    bd = _board(coupe=[(PORTEUR, AMI)] if coupe else [])
    ctx = {"owner_id": 1, "def_id": 2, "owner_team": 0, "def_team": 0,
           "def_traits": ("Mechanical",), "owner_pos": PORTEUR, "def_pos": AMI,
           "owner_level": 50, "owner_mult": 180, "board": bd}
    got = _protector().create_aura_fixed_armor_bonus_for_defense(ctx)
    if attendu is None:
        assert got is None, "arete COUPEE de la liste stockee : le natif n'accorde pas l'aura"
    else:
        assert got, "TEMOIN NUL : l'aura ne se pose meme pas sur une arete PORTEE"


def test_protector_imperative_sans_canal_DEGRADE_en_couronne_hex():
    """CONTRE-EPREUVE : `board` absent -> repli NOMME, le comportement d'avant le cablage."""
    ctx = {"owner_id": 1, "def_id": 2, "owner_team": 0, "def_team": 0,
           "def_traits": ("Mechanical",), "owner_pos": PORTEUR, "def_pos": AMI,
           "owner_level": 50, "owner_mult": 180}
    assert _protector().create_aura_fixed_armor_bonus_for_defense(ctx), (
        "sans canal, la couronne hex doit encore accorder l'aura")


@pytest.mark.parametrize("coupe,accorde", [(True, False), (False, True)])
def test_conqueror_imperative_degat_suit_la_liste_stockee(coupe, accorde):
    """MEME `CreateTargetSelector`, autre canal (`aura_attack_damage_bonus_from_allies`), dont le
    ctx PORTAIT DEJA `board` sur ses DEUX faces -- ZERO seeding, exactement comme
    `extra_damage_aura::create_aura_attack_bonus` en #983."""
    bd = _board(coupe=[(PORTEUR, AMI)] if coupe else [])
    ctx = {"target_armor_reduced": True, "owner_id": 1, "att_id": 2,
           "owner_team": 0, "att_team": 0, "att_traits": ("Mechanical",),
           "owner_pos": PORTEUR, "att_pos": AMI, "board": bd}
    assert bool(_conqueror().create_aura_attack_damage_bonus_for_ally(ctx)) is accorde


def test_conqueror_imperative_lit_la_DIRECTION_du_selecteur():
    """`AdjacentFriends(Owner)` enumere depuis le PORTEUR : `is_adjacent(owner, att)`. On retire
    l'arete `owner -> ami` D'UN SEUL COTE ; l'arete inverse reste. Un port qui aurait ecrit les
    arguments a l'envers accorderait encore -- et `hexgeo.distance`, symetrique, ne pouvait de toute
    facon pas distinguer les deux sens."""
    bd = _board_dirige(depuis=PORTEUR, vers=AMI)
    ctx = {"target_armor_reduced": True, "owner_id": 1, "att_id": 2,
           "owner_team": 0, "att_team": 0, "att_traits": ("Mechanical",),
           "owner_pos": PORTEUR, "att_pos": AMI, "board": bd}
    assert _conqueror().create_aura_attack_damage_bonus_for_ally(ctx) is None
    # PREMISSE : l'asymetrie est bien dans le canal, et dans CE sens-la seulement
    _elev, neigh = _ch(bd)
    assert AMI not in [tuple(x) for x in neigh[PORTEUR]]
    assert PORTEUR in [tuple(x) for x in neigh[AMI]]


# ---- 4.2 les quatre ctx de `hits.py` ------------------------------------------------------------

@pytest.mark.parametrize("coupe,accorde", [(True, False), (False, True)])
def test_big_target_malus_de_coups_suit_la_liste_stockee(coupe, accorde):
    """`BigTargetAdjacentEffect$$CreateTargetSelector` = `Friends(Owner@+0x30,
    AdjacentUnits(Owner@+0x30, unique, 3), 3)` -- LU. Le canal entre par le BOARD DE COUPS, monte
    par `build_hits_board` (COMBAT) et par `playbook/prediction/normal_attack.py` (PREDICTION) :
    PENDANTS EXACTS, donc les deux faces bougent ensemble."""
    from engine.entities.effects.loki.hits import BigTargetAdjacentEffect
    bd = _board(coupe=[(PORTEUR, AMI)] if coupe else [])
    ctx = {"is_melee": False, "owner_id": 1, "tgt_id": 2, "owner_team": 0, "tgt_team": 0,
           "owner_pos": PORTEUR, "t_pos": AMI, "board": bd}
    got = BigTargetAdjacentEffect("BigTarget_AdjacentEffect").create_aura_hits_malus_for_defense(ctx)
    assert bool(got) is accorde
    if accorde:
        assert int(got.value) == -1, "le montant natif est `Direct(-1)`, pas un compte"


@pytest.mark.parametrize("coupe,accorde", [(True, False), (False, True)])
def test_explosive_maladies_coups_additionnels_suivent_la_liste_stockee(coupe, accorde):
    """`ExplosiveMaladies_ExtraRangedAttackEffect$$CreateTargetSelector` =
    `UnitsWithRangedWeapons(AdjacentFriends(owner, 1))`. Canal
    `aura_additional_hits_from_allies` -- ctx monte par `runner/operations/additional_hits.py`
    (COMBAT) et par les DEUX ctx de `normal_attack.py` (PREDICTION)."""
    from engine.entities.effects.loki.hits import ExplosiveMaladiesExtraRangedAttackEffect
    e = ExplosiveMaladiesExtraRangedAttackEffect("ExplosiveMaladies_ExtraRangedAttack")
    e.ability_level, e.ability_variables_multiplier = 50, 180
    bd = _board(coupe=[(PORTEUR, AMI)] if coupe else [])
    ctx = {"att_pos": AMI, "owner_pos": PORTEUR, "att_team": 0, "owner_team": 0,
           "is_melee": False, "board": bd}
    assert bool(e.create_aura_additional_hits_for_ally(ctx)) is accorde


@pytest.mark.parametrize("coupe,accorde", [(True, False), (False, True)])
def test_infernal_pacts_coups_additionnels_suivent_la_liste_stockee(coupe, accorde):
    """`InfernalPacts_AdditionalHitsEffect$$CreateTargetSelector` = `Unique(
    UnitsWithRangedWeapons(UnitsWithTrait(AdjacentFriends(Caster,1), Chaos)) + ... )` -- le `Caster`
    du selecteur EST le porteur de l'effet, donc l'enumeration part de lui."""
    from engine.entities.effects.loki.hits import InfernalPactsAdditionalHitsEffect
    e = InfernalPactsAdditionalHitsEffect("InfernalPacts_AdditionalHits")
    e.ability_level, e.ability_variables_multiplier = 50, 180
    bd = _board(coupe=[(PORTEUR, AMI)] if coupe else [])
    ctx = {"att_pos": AMI, "owner_pos": PORTEUR, "att_team": 0, "owner_team": 0,
           "att_grand_alliance": "Chaos", "att_traits": (), "is_melee": False, "board": bd}
    assert bool(e.create_aura_additional_hits_for_ally(ctx)) is accorde


def _legendary(pos_by_id, team_by_id, used, board):
    from engine.entities.effects.loki.hits import LegendaryCommanderExtraHitsEffect
    e = LegendaryCommanderExtraHitsEffect("LegendaryCommander_ExtraHits")
    ctx = {"tgt_id": 2, "owner_id": 1, "owner_pos": PORTEUR, "owner_team": 0,
           "pos_by_id": pos_by_id, "team_by_id": team_by_id, "used_active_by_id": used,
           "t_pos": pos_by_id[2], "board": board}
    return e.aura_selector_covers(ctx)


@pytest.mark.parametrize("coupe,couvre", [(True, False), (False, True)])
def test_legendary_commander_le_noeud_IsAdjacent_suit_la_liste_stockee(coupe, couvre):
    """4e noeud, PROPRE a 1395 : `Filter(., IsAdjacent(Owner@0x30, Subject@0x68, 3))`. `IsAdjacent`
    descend sur `AreEntitiesAdjacent` -> `AreTilesAdjacent` = `(|dElev| < 2) & (t1 == t2 ||
    ConnectivityComponent$$IsNeighbour)`. On coupe l'arete `owner -- cible`."""
    bd = _board(coupe=[(PORTEUR, AMI)] if coupe else [])
    # u1 = Trajann (owner, team 0) ; u2 = la CIBLE ennemie ; u3 = un allie de Trajann ayant utilise
    # une active ce tour, adjacent a la cible -> le second noeud est satisfait dans les deux cas.
    got = _legendary({1: PORTEUR, 2: AMI, 3: AUTRE_VOISIN_D_AMI},
                     {1: 0, 2: 1, 3: 0}, {1: True, 3: True}, bd)
    assert got is couvre


@pytest.mark.parametrize("coupe,couvre", [(True, False), (False, True)])
def test_legendary_commander_le_noeud_AdjacentEnemies_suit_la_liste_stockee(coupe, couvre):
    """`AdjacentEnemies(Filter(Friends(Owner, AllUnits, 3), HasUsedActiveAbilityThisTurn), 1, 3)` =
    `Enemies(X, Units(AdjacentTiles(X), ...) - X, 3)` : l'ENUMERATION part de CHAQUE ALLIE retenu,
    donc `is_adjacent(allie, cible)`. On coupe l'arete `allie -- cible`, en laissant celle de
    l'owner intacte -- le PREMIER noeud reste donc satisfait, seul le SECOND tombe."""
    bd = _board(coupe=[(AUTRE_VOISIN_D_AMI, AMI)] if coupe else [])
    got = _legendary({1: PORTEUR, 2: AMI, 3: AUTRE_VOISIN_D_AMI},
                     {1: 0, 2: 1, 3: 0}, {1: False, 3: True}, bd)
    assert got is couvre


def test_legendary_commander_sans_canal_DEGRADE_en_couronne_hex():
    bd = _board(with_neighbours=False)
    assert _legendary({1: PORTEUR, 2: AMI, 3: AUTRE_VOISIN_D_AMI},
                      {1: 0, 2: 1, 3: 0}, {1: True, 3: True}, bd) is True


# ---- 4.3 le ctx de TRAIT : `GetStuckIn` ---------------------------------------------------------

def _get_stuck_in(board, pos_by_id, faction_by_id):
    from engine.entities.traits.combat import GetStuckInTrait
    ctx = {"attack_pos": pos_by_id[1], "t_pos": pos_by_id[2], "base_hits": 4,
           "att_id": 1, "tgt_id": 2, "pos_by_id": pos_by_id,
           "team_by_id": {u: (0 if u != 2 else 1) for u in pos_by_id},
           "faction_by_id": faction_by_id, "board": board}
    return GetStuckInTrait("GetStuckIn").as_attacker_bonus_hits(ctx)


@pytest.mark.parametrize("coupe,bonus", [(True, 0), (False, 2)])
def test_get_stuck_in_compte_les_voisins_de_la_CIBLE_sur_la_liste_stockee(coupe, bonus):
    """`GetStuckInAbility$$GetBonusHitChance` : `AdjacentUnits(<DSLSelectors+0x60> = Target, unique,
    3)` -- LU au call-site (le 2e argument est `+0x60`, la CIBLE, pas le caster). L'ENUMERATION part
    donc de la TUILE DE LA CIBLE : `is_adjacent(cible, unite)`.

    Montage : la cible en `AMI`, DEUX Orks allies adjacents a elle (`PORTEUR` = l'attaquant et
    `AUTRE_VOISIN_D_AMI`) -> `orks_adj >= 2` -> `chance_2 = 100` -> `floor(4/2) = 2` coups bonus.
    Couper l'arete `cible -- attaquant` fait tomber le compte a 1, donc la chance a 30, donc le
    Nullable est EXCLU de la prediction -> 0."""
    bd = _board(coupe=[(AMI, PORTEUR)] if coupe else [])
    got = _get_stuck_in(bd, {1: PORTEUR, 2: AMI, 3: AUTRE_VOISIN_D_AMI},
                        {1: "Orks", 2: "Orks", 3: "Orks"})
    assert got == bonus


def test_get_stuck_in_sans_canal_DEGRADE_en_couronne_hex():
    bd = _board(with_neighbours=False)
    assert _get_stuck_in(bd, {1: PORTEUR, 2: AMI, 3: AUTRE_VOISIN_D_AMI},
                         {1: "Orks", 2: "Orks", 3: "Orks"}) == 2


# ---- 4.4 le COUPLE `IconOfObstinacy` : les DEUX expressions du MEME selecteur natif --------------

def _monde_icon(board, positions, teams, traits):
    """`State` ECS minimal + `StatsComponent.ctx.traits`, ce que lit `target_trait_names`."""
    from engine.runner.components import (OwnerComponent, PositionComponent, StatsComponent,
                                          UnitComponent)
    from engine.runner.state import State
    from engine.entities.unit_context import UnitContext
    st = State()
    st.board = board
    for uid, p in positions.items():
        e = st.add_entity(uid)
        e.add_component(PositionComponent(col=p[0], row=p[1]))
        e.add_component(OwnerComponent(team=teams[uid]))
        e.add_component(UnitComponent(visual_id="t", alive=True))
        uc = UnitContext(entity_id=uid, visual_id="t")
        uc.traits = frozenset(traits.get(uid, ()))
        e.add_component(StatsComponent(ctx=uc))
    return st


@pytest.mark.parametrize("coupe,affecte", [(True, False), (False, True)])
def test_icon_of_obstinacy_les_DEUX_faces_suivent_la_liste_stockee(coupe, affecte):
    """LE COUPLE QUE #943-r7 DECLARAIT NON FERMABLE. `AIconOfObstinacyAbility$$GetAffectedUnits` =
    `Owner + UnitsWithTrait(AdjacentFriends(Owner, unique, 3), 0x40f, 3)` a DEUX expressions cote
    port : le selecteur du TRIGGER (face COMBAT, contre l'ECS) et le ctx d'AURA du bonus de degat
    (faces COMBAT+PREDICTION). Le natif les fait COINCIDER -- c'est UN selecteur, pas deux.

    Ce test exige les deux choses a la fois : que chaque face suive la liste stockee, et qu'elles
    rendent LE MEME verdict. Les cabler separement aurait fait diverger le buff d'ARMURE du bonus de
    DEGAT, ce qui est exactement la crainte que la fiche nommait."""
    from engine.runner.operations.triggers.loki.icon_of_obstinacy import (
        icon_of_obstinacy_affected_units)
    from engine.entities.effects.loki.icon_of_obstinacy import IconOfObstinacyExtraDmgEffect
    from engine.entities.traits.unit_trait import UnitTrait
    term = UnitTrait.TerminatorArmour.name
    bd = _board(coupe=[(PORTEUR, AMI)] if coupe else [])
    st = _monde_icon(bd, {1: PORTEUR, 2: AMI}, {1: 0, 2: 0}, {1: (term,), 2: (term,)})
    face_combat = 2 in icon_of_obstinacy_affected_units(st, 1)

    d = IconOfObstinacyExtraDmgEffect("IconOfObstinacy_ExtraDmg")
    d.ability_level, d.ability_variables_multiplier = 50, 180
    face_aura = d.create_aura_attack_damage_bonus_for_ally(
        {"owner_id": 1, "att_id": 2, "owner_team": 0, "att_team": 0,
         "owner_pos": PORTEUR, "att_pos": AMI, "att_traits": (term,), "board": bd}) is not None

    assert face_combat is affecte, "face COMBAT (selecteur du trigger)"
    assert face_aura is affecte, "face AURA (bonus de degat)"
    assert face_combat == face_aura, (
        "LES DEUX EXPRESSIONS DU MEME SELECTEUR NATIF DIVERGENT -- c'est le couple que #943-r7 "
        "declarait non fermable")


def test_icon_of_obstinacy_le_PORTEUR_reste_dans_le_set_sans_arete():
    """`op_Addition(Owner, ...)` : le porteur entre SANS passer par le selecteur, donc sans aucune
    arete. Un cablage qui l'aurait fait traverser `is_adjacent` le retirerait de sa propre aura."""
    from engine.runner.operations.triggers.loki.icon_of_obstinacy import (
        icon_of_obstinacy_affected_units)
    bd = _board(coupe=[(PORTEUR, AMI)])
    st = _monde_icon(bd, {1: PORTEUR, 2: AMI}, {1: 0, 2: 0}, {1: (), 2: ()})
    assert icon_of_obstinacy_affected_units(st, 1) == [1]


# ---- 4.5 `aura_selectors.adjacent_friends_including_owner` (KustomForceField) --------------------

@pytest.mark.parametrize("coupe,dedans", [(True, False), (False, True)])
def test_kustom_force_field_selecteur_suit_la_liste_stockee(coupe, dedans):
    """`Owner + AdjacentFriends(Owner, unique, 3)` -- le noeud de TETE des DEUX
    `CreateTargetSelector` de `KustomForceFieldReworked` (#930). AUCUN blocage propre : la fonction
    recoit l'ECS, donc `State.board`, et n'a qu'UNE face."""
    from engine.entities.effects.aura_selectors import adjacent_friends_including_owner
    bd = _board(coupe=[(PORTEUR, AMI)] if coupe else [])
    st = _monde_icon(bd, {1: PORTEUR, 2: AMI}, {1: 0, 2: 0}, {})
    out = set(adjacent_friends_including_owner(st, 1))
    assert 1 in out, "`op_Addition(Owner, ...)` : le porteur est TOUJOURS dans son aura"
    assert (2 in out) is dedans


# ---- 4.6 `TerrorsLament` : les QUATRE call-sites d'un helper PARTAGE -----------------------------

@pytest.mark.parametrize("coupe,accorde", [(True, False), (False, True)])
def test_terrors_lament_les_quatre_pattes_suivent_la_liste_stockee(coupe, accorde):
    """`IsAdjacent(Caster@+0x48, Owner@+0x30, 3)` -- l'ORDRE est LU
    (`IsAdjacentAbilityTrigger$$.ctor` : `selector1 -> +0x20`, `selector2 -> +0x28` ;
    `ShouldTrigger` appelle `AreEntitiesAdjacent(<+0x20>, <+0x28>)`), donc l'enumeration part de la
    tuile du CASTER.

    Les QUATRE pattes passent par le MEME helper : deux sur le canal DEGAT (ctx defenseur), deux sur
    le canal COUPS (board de coups). Les quatre ctx publient `board` depuis le meme commit, sur les
    DEUX faces -- c'est ce qui rend l'ecart impossible entre pattes."""
    from engine.entities.effects.loki.terrors_lament import (TerrorsLamentDamageReductionEffect,
                                                             TerrorsLamentHitReductionEffect)
    bd = _board(coupe=[(AMI, PORTEUR)] if coupe else [])   # `caster` en AMI, `owner` en PORTEUR
    dmg = TerrorsLamentDamageReductionEffect("TerrorsLament_DamageReduction")
    dmg.ability_level, dmg.ability_variables_multiplier = 50, 180
    hits = TerrorsLamentHitReductionEffect("TerrorsLament_HitReduction")
    # patte SELF du canal DEGAT (`attacker_ctx`)
    self_dmg = dmg.create_effect_damage_malus_for_defense(
        is_melee=True, attacker_ctx={"owner_pos": PORTEUR, "owner_team": 0,
                                     "att_pos": AMI, "team": 1, "board": bd})
    # patte AURA du canal DEGAT
    aura_dmg = dmg.create_aura_defense_damage_malus_for_ally(
        {"owner_pos": PORTEUR, "owner_team": 0, "att_pos": AMI, "att_team": 1,
         "is_melee": True, "board": bd})
    # patte SELF du canal COUPS (`att_ctx` = le board de coups)
    self_hits = hits.create_effect_hits_malus_for_defense(
        is_melee=True, att_ctx={"t_pos": PORTEUR, "tgt_team": 0, "attack_pos": AMI,
                                "att_id": 9, "team_by_id": {9: 1}, "att_traits": (),
                                "board": bd})
    # patte AURA du canal COUPS
    aura_hits = hits.create_aura_hits_bonus_for_attack(
        {"owner_pos": PORTEUR, "owner_team": 0, "att_pos": AMI, "att_team": 1,
         "is_melee": True, "att_traits": (), "board": bd})
    for (nom, got) in (("self degat", self_dmg), ("aura degat", aura_dmg),
                       ("self coups", self_hits), ("aura coups", aura_hits)):
        assert bool(got) is accorde, "patte %s" % nom


# ---- 4.7 `momentum` : le SUBSTRAT AUTRE (`connectivity`, SANS porte d'elevation) -----------------

def _momentum_step(board, monkeypatch):
    """Rend `(resultat du pas, les tuiles ou `_move` a ete atteint)`.

    `_move` est SUBSTITUE SUR LA CLASSE (l'instance porte `__slots__ = ()`) : le pas complet touche
    au deplacement ECS, etranger a l'adjacence. Le stub rend `True` -- un stub rendant `False`
    rendrait le test vert par absence de MOUVEMENT et non par refus du GATE, un regime degenere."""
    from engine.runner.abilities.loki import momentum as M
    from engine.runner.components import OwnerComponent, PositionComponent, UnitComponent
    from engine.runner.state import State
    st = State()
    st.board = board
    e = st.add_entity(1)
    e.add_component(PositionComponent(col=PORTEUR[0], row=PORTEUR[1]))
    e.add_component(OwnerComponent(team=0))
    e.add_component(UnitComponent(visual_id="t", alive=True))
    vus: list = []
    monkeypatch.setattr(M.UnstoppableMomentumReworkedAbility, "_move",
                        lambda self, state, cid, tid, out: (vus.append(int(tid)), True)[1])
    ok = M.UnstoppableMomentumReworkedAbility()._execute_behaviour_step(
        st, 1, (0, 0, 0), _tid(*AMI), 0,
        {"moves": [], "attacks": [], "effects": [], "pushes": [], "switches": []})
    return ok, vus


def test_momentum_lit_le_ConnectivityComponent_BRUT_et_pas_la_couronne(monkeypatch):
    """`TileExtensions$$IsNeighbourOf(targetTile, GetMainTile(caster))` -- corps LU : il enumere
    `ConnectivityComponent+0x10` de la tuile CIBLE et compare l'id de la tuile du caster, **SANS
    AUCUNE PORTE D'ELEVATION**. C'est le seul site de la famille dont le substrat n'est PAS celui
    d'`IterateAdjacentTiles` : `is_adjacent` y serait FAUX (il ajouterait la porte) et
    `neighbours_native` aussi (le champ capte EST deja `connectivity INTERSECTE {|dElev| < 2}`).

    TEMOIN NON NUL : avec le canal complet, le pas passe."""
    ok, vus = _momentum_step(_board(connectivite=True), monkeypatch)
    assert ok is True and vus == [_tid(*AMI)], "TEMOIN NUL : le pas ne passe meme pas"


def test_momentum_refuse_le_pas_quand_la_CONNECTIVITE_ne_porte_pas_l_arete(monkeypatch):
    """Le regime DISCRIMINANT : l'arete existe dans la couronne hex mais PAS dans le
    `ConnectivityComponent`. Avant le cablage, le port l'acceptait."""
    bd = _board(connectivite=True, coupe_connectivite=[(AMI, PORTEUR)])
    ok, vus = _momentum_step(bd, monkeypatch)
    assert ok is False and vus == [], "le pas doit etre REFUSE : l'arete n'est pas dans la liste"


def test_momentum_ne_lit_PAS_le_champ_neighbours(monkeypatch):
    """CONTRE-EPREUVE DE SUBSTRAT, et c'est elle qui separe ce site des dix autres. On coupe
    `neighbours` (le champ AMPUTE par la porte d'elevation) en laissant `connectivity` INTACT : le
    pas doit passer QUAND MEME. Un port qui aurait pris `is_adjacent`/`neighbours_native` le
    refuserait -- il ajouterait une porte que le natif n'applique pas ici."""
    bd = _board(coupe=[(AMI, PORTEUR)], connectivite=True)
    ok, _vus = _momentum_step(bd, monkeypatch)
    assert ok is True, (
        "le pas est refuse alors que `connectivity` porte l'arete : le port lit le MAUVAIS champ")


def test_momentum_sans_canal_de_connectivite_DEGRADE_en_couronne_hex(monkeypatch):
    """TRI-ETAT. Le champ `connectivity` n'existe QU'EN LIVE (les `data/boards/*.json` sont des
    ASSETS que `InitializeConnectivityOperation$$Execute` n'a jamais touches) : canal absent ->
    repli GEOMETRIQUE nomme, c.-a-d. le comportement d'avant. Un `[]` rabattu isolerait au contraire
    toutes les tuiles -- le faux negatif de #381-r3."""
    from engine.entities.pathfinding.board import connectivity_neighbours
    bd = _board()                                     # PAS de champ `connectivity`
    assert connectivity_neighbours(bd, _tid(*AMI)) is None, (
        "premisse : le board temoin ne doit porter AUCUN canal de connectivite")
    ok, vus = _momentum_step(bd, monkeypatch)
    assert ok is True and vus == [_tid(*AMI)]


# ---- 4.8 LE SEEDING EST-IL REELLEMENT PUBLIE ? --------------------------------------------------

def test_le_board_de_coups_PUBLIE_le_canal_sur_la_face_COMBAT():
    """UN CABLAGE DONT LE CTX NE PORTE PAS LA CLE EST INERTE, et il en a exactement l'ALLURE.
    C'est la forme (a) de l'etape 3 du cliquet, transposee au SEEDING : `build_hits_board` doit
    poser `board`, sinon `BigTargetAdjacent` / `GetStuckIn` / `LegendaryCommander` lisent `None` et
    degradent en couronne hex pour toujours, sans que rien ne le dise."""
    from engine.runner.damage_model import build_hits_board
    bd = _board()
    st = _monde_icon(bd, {1: PORTEUR, 2: AMI}, {1: 0, 2: 1}, {})
    board_coups, _auras, _tgt = build_hits_board(st, 1, 2, PORTEUR, AMI, is_melee=True)
    assert board_coups.get("board") is bd, (
        "`build_hits_board` ne publie pas `board` : les trois consommateurs du canal COUPS sont "
        "INERTES cote COMBAT")
