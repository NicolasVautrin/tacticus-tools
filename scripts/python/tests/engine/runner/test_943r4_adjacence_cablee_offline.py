"""#943-r4 -- les TROIS sites recables decident-ils vraiment sur la LISTE STOCKEE ?

Le cliquet `probe_433r4r1r4r2_neigh_channel_wired` garde la FORME (le canal est passe, il est
consomme, la geometrie ne decide pas malgre lui). Il ne dit RIEN du COMPORTEMENT : un port peut
recevoir le canal, le lire, et rendre le meme verdict qu'avant. Ce fichier-ci mesure le verdict.

LE SCENARIO EST CRAFTE POUR QUE LE CABLAGE CHANGE LE RESULTAT, jamais << pris tel quel >> : le
board temoin porte deux tuiles a distance hex **1** qui ne sont **PAS** voisines dans la liste
stockee du `ConnectivityComponent`. C'est un regime REEL, pas une curiosite -- mesure live du
2026-08-12 (`probe_433r4r1r4r2_is_adjacent_substrat_live.py --board MC2_60 --board C4_69`) :
**22** aretes de ce type sur `MC2_60` et **8** sur `C4_69`, pour **0** dans l'autre sens, et le
port SANS canal y rend 22 / 8 desaccords contre le natif quand le port AVEC canal en rend **0**.
Le second etage (la porte `|dElev| < 2`) est exerce a part.

LES TROIS NATIFS, LUS (`docs/rl/case-943r4-le-critere-cessa-detre-de-la-prose.md`) :
  * `FightingRetreatAbility$$SetsActiveAbilityUsedFlag` = `Direct(!Any(<slot 0x7d>(caster, pid, 0)))`,
    slot 125 = `BattleQuery$$GetAdjacentEnemies` = `GetUnitsOnTiles(IterateAdjacentTiles(from, 0, 1, 1), ...)` ;
  * `AncestralFortuneAbility$$GetAttackTarget` -> `DSLSelectors$$AdjacentEnemies` -> `AdjacentTiles` ;
  * `ArcScourgeAbility$$GetDynamicInvalidTargetReason` -> slot 0x7a = `BattleQuery$$GetAdjacentUnits`.

Les trois descendent donc sur le MEME iterateur, et l'ecart est strictement RESTRICTIF.
100 % OFFLINE, aucun runner. ASCII only.
"""
#: Ce qui doit changer pour que ces gardes puissent changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des conftest et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER. Le verdict traverse les trois ports (`abilities/base.py`,
        # `abilities/votann.py`, `abilities/admec.py`), le foyer de l'adjacence
        # (`engine/battle_query.py`) et les DEUX foyers de canal
        # (`entities/pathfinding/board.py`) -- plus tout ce que l'arbre d'ability tire au
        # chargement. Une liste choisie ne tiendrait pas : `engine/**` en entier.
        "scripts/python/engine/**/*.py",
        "scripts/python/*.py",
        # ENTREE VERSIONNEE lue pendant la passe (mesuree par `probe_486r15`, pas supposee) : la
        # cascade des conftest la charge, et une ability qui lit le gameconfig la traverse.
        "data/seed-bc.json",
    ),
    "build": False,
    "toujours": False,
    "raison": "Gardes OFFLINE du recablage d'adjacence : le board temoin est SYNTHETIQUE (un "
              "duck-type a `by_id`, forme lue dans `entities/pathfinding/board.py`), donc aucun "
              "runner n'est monte et le build n'entre pas au declencheur. La confrontation LIVE du "
              "substrat vit dans `probe_433r4r1r4r2_is_adjacent_substrat_live.py`.",
}

import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0].rstrip("\\/"))

from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.abilities.admec import ArcScourgeAbility                # noqa: E402
from engine.runner.abilities.base import sets_end_turn_flags_for           # noqa: E402
from engine.runner.abilities.votann import _ancestral_fortune_attack_target  # noqa: E402
from engine.runner.components import (OwnerComponent, PositionComponent,   # noqa: E402
                                      UnitComponent)
from engine.runner.state import State                                      # noqa: E402

FIGHTING_RETREAT = int(ActiveAbilityType.FightingRetreat)

#: Les trois positions du scenario, EN LIGNE et voisines deux a deux sur la COURONNE HEX
#: (`hexgeo.distance == 1`). La troisieme ne sert qu'a `ArcScourge`, dont le natif exige un
#: CONDUCTEUR au contact de la CIBLE -- le caster n'en est pas un (il n'est ni son propre ennemi
#: ni mecanique), donc un montage a deux unites y mesurerait le refus par defaut, pas l'adjacence.
CASTER = (3, 3)
CIBLE = (4, 3)
CONDUCTEUR = (5, 3)


def _board_temoin(voisins: bool, elev=(0, 0), champ_absent: bool = False) -> Board:
    """Un VRAI `Board` a deux tuiles -- pas un duck-type.

    Mesure du montage : un duck-type reduit a `by_id` suffit aux DEUX foyers de canal
    (`elevations_by_pos`, `adjacent_neigh_by_pos`), mais PAS au chemin complet -- la cible
    d'`AncestralFortune` passe par `first_by_damage_utility` -> `damage_model.
    apply_elevation_bonus`, qui appelle `board.tile_at`. Un board partiel y leve `AttributeError`,
    donc il ferait echouer le test pour une raison qui n'a rien a voir avec l'adjacence.

    ⚠ `neighbours` ABSENT != `neighbours` VIDE : `adjacent_neigh_by_pos` OMET la tuile dont le
    champ manque (le port retombe alors sur la couronne hex POUR ELLE) ; la coter `[]` la rendrait
    ISOLEE -- le vice de #381-r3. Les deux regimes sont exerces, et ils ne rendent pas la meme
    chose."""
    #: `elev` = (caster, cible, conducteur). Les DEUX aretes de la ligne portent alors le meme
    #: ecart quand on passe `(0, d, 0)` : `|e1-e2| = |e2-e3| = d`.
    elev = tuple(elev) + (0,) * (3 - len(elev))
    coords = (CASTER, CIBLE, CONDUCTEUR)
    tuiles = [{"id": i + 1, "col": c[0], "row": c[1], "elevation": elev[i], "walkable": True}
              for i, c in enumerate(coords)]
    if not champ_absent:
        # la ligne 1 -- 2 -- 3, ou rien du tout
        tuiles[0]["neighbours"] = [2] if voisins else []
        tuiles[1]["neighbours"] = [1, 3] if voisins else []
        tuiles[2]["neighbours"] = [2] if voisins else []
    return Board(tuiles)


def _state(board=None, cible=CIBLE, conducteur: bool = False) -> State:
    """u1 (team 1, le caster) en `CASTER` ; u2 (team 2) en `cible`.

    `conducteur=True` ajoute u3 (team 2, donc ENNEMI du caster) en `CONDUCTEUR` : c'est le seul
    montage ou le gate d'`ArcScourge` peut rendre 0, puisque le natif exige un ennemi -- ou un
    allie MECANIQUE -- AU CONTACT de la cible."""
    st = State()
    st.current_player_id = 3
    st.board = board
    e1 = st.add_entity(1)
    e1.add_component(UnitComponent("unitA", True))
    e1.add_component(OwnerComponent(team=1, player=3))
    e1.add_component(PositionComponent(*CASTER))
    e2 = st.add_entity(2)
    e2.add_component(UnitComponent("unitB", True))
    e2.add_component(OwnerComponent(team=2, player=4))
    e2.add_component(PositionComponent(*cible))
    if conducteur:
        e3 = st.add_entity(3)
        e3.add_component(UnitComponent("unitC", True))
        e3.add_component(OwnerComponent(team=2, player=4))
        e3.add_component(PositionComponent(*CONDUCTEUR))
    return st


# --------------------------------------------------------------- le regime de reference

def test_le_scenario_est_DISCRIMINANT_les_deux_positions_sont_hex_adjacentes():
    """PREMISSE, mesuree et non supposee : sans elle, tous les tests ci-dessous seraient verts
    pour la mauvaise raison (deux tuiles simplement lointaines)."""
    import hexgeo
    assert hexgeo.distance(CASTER, CIBLE) == 1, (
        "le scenario n'oppose plus la couronne hex a la liste stockee -- il ne mesure plus rien")


def test_sans_board_le_cablage_est_un_NO_OP_demontrable(monkeypatch):
    """`is_adjacent` degrade seul en `hexgeo` quand les DEUX canaux sont `None`.

    C'est ce qui rend les trois reparations sures la ou rien n'est capte -- et c'est aussi
    pourquoi le test historique `test_fighting_retreat_conditional_on_adjacency` (board `None`)
    n'a pas bouge."""
    st = _state(board=None)
    assert sets_end_turn_flags_for(FIGHTING_RETREAT, st, 1) is False   # ennemi adjacent -> pas de flags
    assert _ancestral_fortune_attack_target(st, 1) == 2
    st_loin = _state(board=None, cible=(9, 9))
    assert sets_end_turn_flags_for(FIGHTING_RETREAT, st_loin, 1) is True


# ------------------------------------------ ETAGE 1 : l'ENUMERATION (la liste stockee)

def test_fighting_retreat_LISTE_STOCKEE_contredit_la_couronne():
    """`GetAdjacentEnemies` n'enumere QUE la liste stockee : deux tuiles hex-voisines qui n'y
    figurent pas ne sont PAS adjacentes, donc le caster n'a AUCUN ennemi adjacent."""
    st = _state(board=_board_temoin(voisins=False))
    assert sets_end_turn_flags_for(FIGHTING_RETREAT, st, 1) is True, (
        "le port decide encore sur la couronne hex : la liste stockee ne le contredit pas")


def test_fighting_retreat_reste_FIDELE_quand_la_liste_CONFIRME():
    """CONTRE-EPREUVE : le cablage ne doit pas SUR-restreindre. Liste qui confirme -> verdict
    d'avant."""
    st = _state(board=_board_temoin(voisins=True))
    assert sets_end_turn_flags_for(FIGHTING_RETREAT, st, 1) is False


def test_ancestral_fortune_LISTE_STOCKEE_contredit_la_couronne():
    """`AdjacentEnemies` -> `AdjacentTiles` : plus aucun candidat, donc aucune cible."""
    st = _state(board=_board_temoin(voisins=False))
    assert _ancestral_fortune_attack_target(st, 1) is None
    st_ok = _state(board=_board_temoin(voisins=True))
    assert _ancestral_fortune_attack_target(st_ok, 1) == 2, "CONTRE-EPREUVE : sur-restriction"


def test_arc_scourge_LISTE_STOCKEE_contredit_la_couronne():
    """`GetAdjacentUnits(target)` (slot 0x7a) : sans conducteur AU CONTACT de la cible, l'arc est
    REFUSE (`TargetMatchesDynamicRule`).

    u3 est hex-adjacent a la cible dans les DEUX montages -- seule la liste stockee les separe."""
    from engine.runner.abilities.targeting_rule import TargetingRule as TR
    ab = ArcScourgeAbility()
    st_nu = _state(board=_board_temoin(voisins=False), conducteur=True)
    assert ab.get_dynamic_invalid_target_reason(st_nu, 1, 2) == int(TR.TargetMatchesDynamicRule)
    st_ok = _state(board=_board_temoin(voisins=True), conducteur=True)
    assert ab.get_dynamic_invalid_target_reason(st_ok, 1, 2) == 0, (
        "CONTRE-EPREUVE : le gate refuse meme quand la liste CONFIRME l'adjacence")


def test_arc_scourge_SANS_conducteur_refuse_meme_liste_CONFIRMEE():
    """PREMISSE du test ci-dessus : c'est bien u3 qui fait passer le gate, pas le caster.

    Sans lui, la seule unite au contact de la cible est le CASTER -- ni son propre ennemi, ni
    mecanique -- donc le natif REFUSE, liste stockee ou pas. Sans ce cran, le test precedent
    pourrait etre vert pour la mauvaise raison."""
    from engine.runner.abilities.targeting_rule import TargetingRule as TR
    ab = ArcScourgeAbility()
    st = _state(board=_board_temoin(voisins=True), conducteur=False)
    assert ab.get_dynamic_invalid_target_reason(st, 1, 2) == int(TR.TargetMatchesDynamicRule)


# ------------------------------------------ ETAGE 2 : la PORTE `|dElev| < 2`

@pytest.mark.parametrize("delev,adjacent", [(0, True), (1, True), (2, False), (3, False)])
def test_la_porte_d_elevation_mord_sur_les_trois_sites(delev, adjacent):
    """`IterateAdjacentTiles` : `if (|elev0 - elev| < 2) yield`. La porte est INCONDITIONNELLE et
    s'applique APRES l'enumeration -- ici la liste CONFIRME, donc seule la porte peut trancher.

    Ampleur re-derivee offline sur les 779 boards versionnes : 10 129 aretes hex sur 113 260
    (8,9 %) sont coupees par cette seule porte, jusqu'a 39,2 % sur `MC2_60`.

    ⚠ C'est exactement ce qui etait MORT dans `admec.py` : son canal d'elevation visait
    `state.board.elevation_by_pos`, un attribut qui n'existe nulle part."""
    from engine.runner.abilities.targeting_rule import TargetingRule as TR
    board = _board_temoin(voisins=True, elev=(0, delev, 0))
    st = _state(board=board, conducteur=True)
    assert sets_end_turn_flags_for(FIGHTING_RETREAT, st, 1) is not adjacent
    assert (_ancestral_fortune_attack_target(st, 1) is not None) is adjacent
    attendu = 0 if adjacent else int(TR.TargetMatchesDynamicRule)
    assert ArcScourgeAbility().get_dynamic_invalid_target_reason(st, 1, 2) == attendu


# ------------------------------------------ le TRI-ETAT du canal (#381-r3)

def test_champ_neighbours_ABSENT_nest_pas_un_voisinage_VIDE():
    """`adjacent_neigh_by_pos` OMET la tuile dont le champ manque -- le port retombe alors sur la
    couronne hex POUR ELLE. Coter `[]` la rendrait ISOLEE : c'est le vice de #381-r3, et il
    rendrait ces trois gates RESTRICTIFS a tort partout ou le capteur n'a rien vu."""
    st = _state(board=_board_temoin(voisins=False, champ_absent=True))
    assert sets_end_turn_flags_for(FIGHTING_RETREAT, st, 1) is False, (
        "un champ `neighbours` ABSENT a ete lu comme un voisinage VIDE")
    assert _ancestral_fortune_attack_target(st, 1) == 2
