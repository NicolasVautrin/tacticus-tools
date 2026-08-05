"""#302 tranche 5 -- GARDE offline du canal `MachineOfWarPosition`, EPROUVEE PAR MUTANTS.

Ce que garde ce fichier (le probe `probe_302_5_mow_position_channel.py` MESURE, ce test GARDE) :

1. l'ORDRE de la cascade -- le natif INVOQUE (`boardGraph.mowPositions`) passe devant le mirror
   de la BC, qui passe devant le slot de la MoW deployee ;
2. le TRI-ETAT du lecteur -- `None` (pas mesure) n'est jamais rabattu sur `{}` ni sur `0` ;
3. le fait que `0` est une valeur LEGITIME (`MachineOfWarPosition.None_`, portee par la majorite
   des boards) et non un « absent » ;
4. le mirror de `GroupForPlayer` / du repli natif, transcrit du decompile.

Etage MUTANTS (le point le plus important) : chaque invariant ci-dessus est re-joue contre une
version DELIBEREMENT FAUSSE du code, et le test EXIGE que la garde rougisse. Une garde qu'aucun
mutant ne fait rougir est INERTE -- c'est le defaut le plus frequent du depot, et il passe pour
vert. `a_mordu` est donc mesure ICI, pas suppose.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "python"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import engine.ai.context as AICTX                              # noqa: E402
from engine.services.machine_of_war_position import (          # noqa: E402
    MachineOfWarPosition, group_for_player, machine_of_war_position_for_player,
    spawn_groups_from_battle_config, team_with_player_index,
)

# `MC1_67` : declaration == repli -> REGIME DEGENERE (celui ou #311 ne pouvait pas trancher).
GROUPES_DEGENERES = [{"TeamWithPlayerIndex": 0, "MachineOfWarPosition": 2},
                     {"TeamWithPlayerIndex": 1, "MachineOfWarPosition": 1}]
# `C1_01` : declaration != repli -> REGIME DISCRIMINANT (552 fichiers de `data/boards`).
GROUPES_DISCRIMINANTS = [{"TeamWithPlayerIndex": 1, "MachineOfWarPosition": 0},
                         {"TeamWithPlayerIndex": 0, "MachineOfWarPosition": 0}]

CUR = 3          # `decisionView.currentPlayer` -- MEME espace d'ids que `mowPositions[].playerId`
TEAM = 1


# --------------------------------------------------------------- 1. l'ordre de la cascade

def test_le_natif_invoque_passe_devant_le_mirror():
    """Le canal `mowPositions` est `GetPositionMachineForPlayer` INVOQUE : il gagne sur le mirror
    de la BC, qui DEVINE `playerNr = 0` la ou le natif le lit de `StateExtensions$$GetTeam`."""
    # La BC dirait 2 ; le natif dit 1. C'est le natif qui doit sortir.
    assert AICTX._machine_of_war_position(GROUPES_DEGENERES, TEAM, {}, CUR, {CUR: 1}) == 1


def test_le_mirror_prend_le_relais_quand_le_canal_est_absent():
    """Chemin OFFLINE (`state_bridge`) : aucun RPC, donc aucun `mowPositions`. Le mirror reste
    la seule voie -- le retirer casserait la face PREDICTION hors-live."""
    assert AICTX._machine_of_war_position(GROUPES_DEGENERES, TEAM, {}, CUR, None) == 2


def test_le_slot_de_la_mow_reste_le_dernier_repli():
    assert AICTX._machine_of_war_position(None, None, {CUR: 1}, CUR, None) == 1


def test_ignorance_assumee_quand_rien_n_est_lisible():
    """Le port ne DEVINE pas : appliquer le repli natif a l'aveugle serait faux sur la majorite
    des plateaux. `None` = non mesure -> le predicat rend False."""
    assert AICTX._machine_of_war_position(None, None, {}, CUR, None) is None


def test_un_joueur_absent_de_la_table_ne_court_circuite_pas_la_cascade():
    """La table peut etre non vide SANS porter le joueur courant (elle n'enumere que les entites
    `EntityType.Player` du runner). Un `.get` manquant doit laisser la cascade continuer."""
    assert AICTX._machine_of_war_position(GROUPES_DEGENERES, TEAM, {}, 99, {CUR: 1}) == 2


# --------------------------------------------------------------- 2. le tri-etat du lecteur

def _rpc_rendant(payload):
    return lambda method, body, timeout=60: payload


@pytest.fixture(autouse=True)
def _cache_propre():
    """Le cache `boardGraph` est module-level et partage : le vider isole chaque cas."""
    AICTX._BOARD_GRAPH_CACHE.clear()
    yield
    AICTX._BOARD_GRAPH_CACHE.clear()


def test_canal_absent_rend_none_pas_un_dict_vide():
    """`mowPositions` absent (bundle anterieur a #311, ou methode irresolue) = PAS MESURE.
    Le rabattre sur `{}` ferait passer un capteur MORT pour un plateau sans joueurs."""
    assert AICTX._board_mow_positions(_rpc_rendant({"tiles": []}), 1) is None
    assert AICTX._board_mow_positions(_rpc_rendant({"tiles": [], "mowPositions": None}), 2) is None


def test_canal_mesure_et_vide_rend_un_dict_vide():
    assert AICTX._board_mow_positions(_rpc_rendant({"mowPositions": []}), 3) == {}


def test_entree_en_erreur_est_ecartee_jamais_rabattue_sur_zero():
    """Le hook publie `machineOfWarPosition: null` + `error` quand l'invocation a leve. `0` est une
    valeur LEGITIME (`MachineOfWarPosition.None_`) : confondre les deux inventerait une mesure."""
    payload = {"mowPositions": [{"playerId": 3, "teamId": 1, "machineOfWarPosition": None,
                                 "error": "boom"},
                                {"playerId": 4, "teamId": 2, "machineOfWarPosition": 0}]}
    table = AICTX._board_mow_positions(_rpc_rendant(payload), 4)
    assert table == {4: 0}, "l'entree en erreur doit etre ECARTEE, pas rabattue sur 0"
    assert 3 not in table


def test_zero_est_une_valeur_pas_un_absent():
    """Le piege central : `{cur: 0}` est truthy-vide en Python. Un `or` mal place ferait tomber la
    cascade sur le mirror et rendrait 2 la ou le natif dit 0 -- sur 552 fichiers de board."""
    assert AICTX._machine_of_war_position(GROUPES_DEGENERES, TEAM, {}, CUR, {CUR: 0}) == 0


def test_un_seul_fetch_boardGraph_alimente_tiles_ET_mowpositions():
    """Le branchement ne doit couter AUCUN RPC : `tiles` et `mowPositions` sortent du meme fetch."""
    appels = []

    def rpc(method, body, timeout=60):
        appels.append(method)
        return {"tiles": [{"id": 1, "col": 0, "row": 0, "neighbours": []}],
                "mowPositions": [{"playerId": 3, "teamId": 1, "machineOfWarPosition": 2}]}

    AICTX._board_graph_tiles(rpc, 7)
    AICTX._board_mow_positions(rpc, 7)
    AICTX._board_graph_tiles(rpc, 7)
    assert appels == ["boardGraph"], "un seul fetch attendu, obtenu %r" % (appels,)


# --------------------------------------------------------------- 3. le mirror du decompile

def test_team_with_player_index_transcrit_le_decompile():
    """`SpawnPointSetConfiguration$$GroupForPlayer` : teamId 0 -> 6 ; 1 -> (playerNr ? 2 : 0) ;
    2 -> (playerNr ? 3 : 1) ; 3 -> (playerNr ? 5 : 4)."""
    assert [team_with_player_index(t) for t in (0, 1, 2, 3)] == [6, 0, 1, 4]
    assert [team_with_player_index(t, 1) for t in (0, 1, 2, 3)] == [6, 2, 3, 5]
    assert team_with_player_index(4) is None       # le natif leve ; le port rend None


def test_le_repli_natif_ne_tire_que_faute_de_groupe():
    """`if (grp != null) return grp.<+0x14>` PUIS `if (uVar1 != 1) return (uVar1 == 2); return 2;`
    -- mesure live #302-5 (board `C1_01`) : le natif rend 0/0 la ou le repli rendrait 2/1."""
    assert machine_of_war_position_for_player(GROUPES_DISCRIMINANTS, 1) == 0
    assert machine_of_war_position_for_player(GROUPES_DISCRIMINANTS, 2) == 0
    assert machine_of_war_position_for_player([], 1) == int(MachineOfWarPosition.Bottom)
    assert machine_of_war_position_for_player([], 2) == int(MachineOfWarPosition.Top)
    assert machine_of_war_position_for_player([], 0) == int(MachineOfWarPosition.None_)


def test_spawn_groups_from_battle_config_distingue_absent_de_vide():
    assert spawn_groups_from_battle_config({}) is None
    assert spawn_groups_from_battle_config(
        {"Board": {"SpawnPointSets": [{"SpawnPointGroups": []}]}, "SpawnPointSetIndex": 0}) == []
    assert group_for_player(None, 1) is None


# --------------------------------------------------------------- 4. MUTANTS : la garde MORD-elle ?

def _cascade_sans_le_cran_natif(spawn_groups, team, slots, cur, table=None):
    """MUTANT 1 -- le port d'AVANT la tranche (canal ignore)."""
    if spawn_groups is not None and team is not None:
        return machine_of_war_position_for_player(spawn_groups, int(team))
    return (slots or {}).get(cur)


def _cascade_avec_or_fautif(spawn_groups, team, slots, cur, table=None):
    """MUTANT 2 -- `table.get(cur) or <suite>` : le piege du `0` falsy."""
    if table:
        pos = table.get(cur)
        if pos:                       # <-- FAUTE : 0 est falsy
            return pos
    if spawn_groups is not None and team is not None:
        return machine_of_war_position_for_player(spawn_groups, int(team))
    return (slots or {}).get(cur)


def _lecteur_qui_rabat_le_tri_etat(rpc, rid):
    """MUTANT 3 -- `None` (pas mesure) rabattu sur `{}` (mesure et vide)."""
    mp = (rpc("boardGraph", {"runnerId": rid}, 60) or {}).get("mowPositions")
    return {e["playerId"]: e["machineOfWarPosition"] for e in (mp or [])
            if e.get("playerId") is not None and e.get("machineOfWarPosition") is not None}


def _lecteur_qui_fabrique_un_zero(rpc, rid):
    """MUTANT 4 -- une entree en ERREUR rabattue sur 0 (invente une mesure)."""
    mp = (rpc("boardGraph", {"runnerId": rid}, 60) or {}).get("mowPositions")
    if not isinstance(mp, list):
        return None
    return {e.get("playerId"): int(e.get("machineOfWarPosition") or 0) for e in mp}


MUTANTS_CASCADE = [
    ("sans le cran natif", _cascade_sans_le_cran_natif),
    ("`or` fautif sur le 0", _cascade_avec_or_fautif),
]
MUTANTS_LECTEUR = [
    ("tri-etat rabattu", _lecteur_qui_rabat_le_tri_etat),
    ("zero fabrique", _lecteur_qui_fabrique_un_zero),
]

# Les cas de garde qui doivent DISTINGUER le vrai code du mutant. Chacun est un couple
# (arguments, valeur ATTENDUE du vrai code).
CAS_CASCADE = [
    ((GROUPES_DEGENERES, TEAM, {}, CUR, {CUR: 1}), 1),      # natif prioritaire
    ((GROUPES_DEGENERES, TEAM, {}, CUR, {CUR: 0}), 0),      # 0 legitime
]


@pytest.mark.parametrize("nom,mutant", MUTANTS_CASCADE)
def test_mutant_de_cascade_fait_rougir_la_garde(nom, mutant):
    """`a_mordu` MESURE : au moins un cas de garde doit SEPARER le vrai code du mutant."""
    a_mordu = []
    for args, attendu in CAS_CASCADE:
        vrai = AICTX._machine_of_war_position(*args)
        assert vrai == attendu, "la garde elle-meme est fausse sur %r" % (args,)
        if mutant(*args) != attendu:
            a_mordu.append(args)
    assert a_mordu, ("MUTANT INERTE (%s) : aucun cas de garde ne le distingue du vrai code. "
                     "La garde ne protege rien." % nom)


@pytest.mark.parametrize("nom,mutant", MUTANTS_LECTEUR)
def test_mutant_de_lecteur_fait_rougir_la_garde(nom, mutant):
    cas = [
        ({"tiles": []}, None),                                            # canal absent
        ({"mowPositions": [{"playerId": 3, "teamId": 1,
                            "machineOfWarPosition": None, "error": "boom"}]}, {}),
    ]
    a_mordu = []
    for payload, attendu in cas:
        AICTX._BOARD_GRAPH_CACHE.clear()
        vrai = AICTX._board_mow_positions(_rpc_rendant(payload), 42)
        assert vrai == attendu, "la garde elle-meme est fausse sur %r" % (payload,)
        AICTX._BOARD_GRAPH_CACHE.clear()
        if mutant(_rpc_rendant(payload), 42) != attendu:
            a_mordu.append(payload)
    assert a_mordu, ("MUTANT INERTE (%s) : aucun cas de garde ne le distingue du vrai code."
                     % nom)


def test_les_mutants_ne_sont_pas_tous_le_meme_code():
    """Contre-epreuve de la contre-epreuve : si deux 'mutants' etaient identiques au vrai code,
    les tests ci-dessus passeraient en ne prouvant rien. On exige une DIFFERENCE observable."""
    args, _ = CAS_CASCADE[1]                     # le cas `0` legitime
    vrai = AICTX._machine_of_war_position(*args)
    distincts = {nom for nom, m in MUTANTS_CASCADE if m(*args) != vrai}
    assert distincts, "aucun mutant de cascade ne differe du vrai code sur le cas `0`"
