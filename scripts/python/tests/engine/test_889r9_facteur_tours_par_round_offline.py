"""#889-r9 OFFLINE -- le facteur `rounds -> tours` se LIT dans la BC, il ne s'estime plus.

CE QUE CE FICHIER GARDE. `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` compte les
joueurs du `BC.Player.TurnOrder` dont le `PlayerComponent.<+0x20>` (`PlayerType`) vaut autre chose
que `2` (Environment), et multiplie `rounds` par ce compte. Le port l'estimait par le PROXY
`observeBattle.counts.player - 1`, qui postule EXACTEMENT un Environment parmi les joueurs
PROJETES et qu'ils soient TOUS dans le `TurnOrder`.

⚠ LE TEMOIN DOIT DIVERGER, sinon il ne prouve rien. Sur nos runners les deux valent 2 (mesure
live du 2026-08-17, `probe_889r9_duree_pre_tick.py` : `counts.player = 3`, `TurnOrder = [11,12,13]`
de `PlayerType 0/1/2`) -- un test monte sur ce regime passerait AUSSI avec le proxy, et serait un
vert qui ne mesure rien. Chaque cas ci-dessous ecarte donc explicitement les deux valeurs, et
`test_le_temoin_DIVERGE_vraiment` asserte cet ecart avant de s'en servir.

CE QUE CE FICHIER NE GARDE PAS : la duree OBSERVEE apres un tick de fin de tour. Elle est mesuree
live par `probe_889r9_duree_pre_tick.py`, qui etablit que l'ecart `1` contre `2` de la fiche etait
un artefact de MONTAGE (le natif joue `IdunBattle.Operations.EndTurnOperation$$RefreshEffects`
avant la relecture, le port non).
"""
from __future__ import annotations

#: Perimetre : les deux bouts du canal, et le consommateur du facteur.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/catalog_inject.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/runner/abilities/base.py",
        "scripts/python/rl_duel.py",
        "data/seed-bc.json",
    ),
    "build": False,
    "toujours": False,
    "raison": "Offline : garde que le facteur rounds->tours vient du TurnOrder de la BC "
              "(mirror de BattleQuery$$ConvertRoundsToTurns) et non du proxy counts.player - 1, "
              "sur un temoin ou les deux DIVERGENT.",
}

import sys           # noqa: E402
from pathlib import Path                                                      # noqa: E402

import pytest        # noqa: E402

_SP = Path(__file__).resolve().parents[2]
if str(_SP) not in sys.path:
    sys.path.insert(0, str(_SP))

import catalog_inject as C                                                    # noqa: E402
from engine.runner import snapshot as S                                       # noqa: E402
from engine.runner.abilities import base as AB                                # noqa: E402

LABEL = "build#990889"          # id volontairement hors de portee d'un runner reel

#: Le TEMOIN : 6 joueurs projetes (donc proxy = 5), mais un `TurnOrder` de 3 entrees dont DEUX
#: Environment -> le compte natif vaut 1. Les deux mesures ne peuvent pas se confondre.
TURN_ORDER_TEMOIN = [11, 12, 13]
PLAYERS_TEMOIN = {
    "11": {"Name": "player", "PlayerType": 0},
    "12": {"Name": "env_a", "PlayerType": 2},
    "13": {"Name": "env_b", "PlayerType": 2},
}
COUNTS_PLAYER_TEMOIN = 6
FACTEUR_BC_ATTENDU = 1          # count(PlayerType != 2) sur le TurnOrder
FACTEUR_PROXY_ATTENDU = 5       # counts.player - 1


def _bc(players=None, turn_order=None) -> dict:
    return {"Player": {"Players": players if players is not None else dict(PLAYERS_TEMOIN),
                       "TurnOrder": list(turn_order) if turn_order is not None
                       else list(TURN_ORDER_TEMOIN)}}


@pytest.fixture(autouse=True)
def _propre():
    C.clear_runner_bc_sections(LABEL)
    yield
    C.clear_runner_bc_sections(LABEL)


@pytest.fixture
def _dec_obs_snap():
    """Le plus petit triplet que `load_state` accepte, porteur du LABEL et du `counts.player` du
    temoin -- c'est l'ARBITRAGE entre les deux sources qui est le sujet, pas la bataille."""
    dec = {"runner": LABEL, "units": []}
    obs = {"runner": LABEL, "units": [], "counts": {"player": COUNTS_PLAYER_TEMOIN}}
    snap = {"runner": LABEL, "units": []}
    return dec, obs, snap


# --------------------------------------------------------------------------- le temoin lui-meme

def test_le_temoin_DIVERGE_vraiment():
    """Un accord en regime degenere ne prouverait RIEN : on asserte l'ecart AVANT de s'en servir."""
    assert FACTEUR_BC_ATTENDU != FACTEUR_PROXY_ATTENDU, (
        "temoin degenere : le proxy et le compte natif rendraient la meme valeur, donc aucun des "
        "tests ci-dessous ne pourrait distinguer les deux sources")
    assert COUNTS_PLAYER_TEMOIN - 1 == FACTEUR_PROXY_ATTENDU
    assert sum(1 for p in TURN_ORDER_TEMOIN
               if int(PLAYERS_TEMOIN[str(p)]["PlayerType"]) != 2) == FACTEUR_BC_ATTENDU


# --------------------------------------------------------------------------- le lecteur

def test_le_compte_mirrore_le_TurnOrder_et_ecarte_Environment():
    C.publish_runner_bc_sections(LABEL, _bc())
    assert S._facteur_tours_par_round(LABEL) == FACTEUR_BC_ATTENDU


def test_l_ORDRE_ne_change_rien_mais_le_CONTENU_oui():
    """Le natif compte des entrees, pas des positions : deux joueurs non-Environment -> 2."""
    C.publish_runner_bc_sections(
        LABEL, _bc(players={"11": {"PlayerType": 0}, "12": {"PlayerType": 1},
                            "13": {"PlayerType": 2}}))
    assert S._facteur_tours_par_round(LABEL) == 2


def test_un_joueur_HORS_TurnOrder_n_est_PAS_compte():
    """C'est le postulat exact que le proxy ne peut pas verifier : `counts.player` compte les
    entites Player PROJETEES, la boucle native n'itere que le `TurnOrder`."""
    C.publish_runner_bc_sections(
        LABEL, _bc(players={"11": {"PlayerType": 0}, "12": {"PlayerType": 1},
                            "13": {"PlayerType": 2}, "14": {"PlayerType": 0}},
                   turn_order=[11, 13]))
    assert S._facteur_tours_par_round(LABEL) == 1


# --------------------------------------------------------------------------- les degradations

def test_pas_de_section_Player_rend_None():
    C.publish_runner_bc_sections(LABEL, {"Damage": {"DamageSpreadPercentage": 7}})
    assert S._facteur_tours_par_round(LABEL) is None


def test_un_id_du_TurnOrder_SANS_joueur_rend_None():
    """Le natif LEVE (`GetPlayer` nul -> le corps saute au throw). Le port ne peut pas mirrorer un
    throw sans casser des etats legitimes : il rend `None` et retombe sur le proxy, ce qui est une
    degradation VISIBLE plutot qu'un compte invente."""
    C.publish_runner_bc_sections(LABEL, _bc(turn_order=[11, 12, 13, 99]))
    assert S._facteur_tours_par_round(LABEL) is None


def test_un_PlayerType_absent_rend_None():
    C.publish_runner_bc_sections(LABEL, _bc(players={"11": {"Name": "player"},
                                                     "12": {"PlayerType": 2},
                                                     "13": {"PlayerType": 2}}))
    assert S._facteur_tours_par_round(LABEL) is None


def test_un_TurnOrder_VIDE_rend_None():
    C.publish_runner_bc_sections(LABEL, _bc(turn_order=[]))
    assert S._facteur_tours_par_round(LABEL) is None


# --------------------------------------------------------------------------- l'arbitrage

def test_load_state_PREFERE_la_BC_au_proxy(_dec_obs_snap):
    dec, obs, snap = _dec_obs_snap
    C.publish_runner_bc_sections(LABEL, _bc())
    st = S.load_state(dec, obs, snap, ability_states=False)
    assert st.turn_order_player_count == FACTEUR_BC_ATTENDU, (
        "le facteur doit venir du TurnOrder de la BC, pas de counts.player - 1")


def test_load_state_RETOMBE_sur_le_proxy_sans_canal(_dec_obs_snap):
    """La degradation est exactement celle d'avant ce canal -- aucun etat sans BC ne change."""
    dec, obs, snap = _dec_obs_snap
    st = S.load_state(dec, obs, snap, ability_states=False)
    assert st.turn_order_player_count == FACTEUR_PROXY_ATTENDU


def test_convert_rounds_to_turns_CONSOMME_le_facteur_lu(_dec_obs_snap):
    """Le facteur ne sert a rien s'il n'atteint pas le mirror : on va jusqu'au bout de la chaine."""
    dec, obs, snap = _dec_obs_snap
    C.publish_runner_bc_sections(LABEL, _bc(players={"11": {"PlayerType": 0},
                                                     "12": {"PlayerType": 1},
                                                     "13": {"PlayerType": 2}}))
    st = S.load_state(dec, obs, snap, ability_states=False)
    assert AB.convert_rounds_to_turns(st, 1) == 2
    assert AB.convert_rounds_to_turns(st, 3) == 6
    # `TurnsUntilEndOfCurrentPlayersNextTurn` = `TurnsFromRounds(1) + Direct(1)` : seul le premier
    # terme passe par le facteur.
    assert AB.turns_until_end_of_current_players_next_turn(st) == 3


def test_la_section_Player_est_PUBLIEE_par_le_montage():
    """Publier une section que personne ne lit fabriquerait du code mort a l'air de canal --
    l'inverse est pire : un lecteur sans producteur est un canal MORT qui se lit comme un repli."""
    assert C.BC_SECTIONS_PUBLIEES == ("Damage", "Player")
    p = C.publish_runner_bc_sections(LABEL, _bc())
    assert p is not None and p.exists()
    assert S._section_bc_du_runner(LABEL, "Player") is not None
