"""#462-r4e-o-r2-r1-r1-r1 -- CLIQUET du choix du joueur suivant (`ChangeTurnOperation`).

Le natif choisit le joueur suivant en QUATRE etages SEPARES, que le port fondait en un seul
(<< cycle sur les joueurs a >= 1 unite vivante, tries >>) :

    ChangeTurnOperation$$FindNextPlayer(matchEntity) :
        order   = query.GetPlayerTurnOrder()     # slot IBattleQuery 0x18, arite 0 -> CONFIG
        index   = FindTurnIndex(current)         # position dans l'ordre COMPLET, sans skip
        i = (index.HasValue ? index.Value : -1)
        for (offset = 1 ; offset <= players.Count ; offset++) {
            pid = order[(i + offset) % order.Count]
            if (!query.ShouldPlayerSkipTurn(GetPlayer(state, pid)))  break   # slot 0x1a, arite 1
        }
        return player.Id                          # null quand la borne est atteinte

CE FICHIER GARDE TROIS CHOSES, ET AUCUNE NE SUFFIT SEULE :

  1. la VALEUR, sur les regimes que `rl_duel build` ne monte pas (>= 3 joueurs, joueur courant
     entierement mort). Le regime confrontable LIVE -- deux camps + Environment sans unite -- est
     une ALTERNANCE STRICTE ou les quatre etages ne se separent PAS : un test qui n'exercerait que
     lui serait vert sans rien mesurer ;
  2. la SEPARATION elle-meme (PROVENANCE, par AST) : une recopie locale strictement equivalente est
     comportementalement indistinguable, donc AUCUN critere de valeur ne peut la voir (angle mort
     mesure en #643 puis #646). On exige que `find_next_player` APPELLE les trois etages nommes ;
  3. le fait que l'ordre de tour NE FILTRE PAS la vivacite -- c'est le correctif, et c'est aussi
     ce qui se ferait re-fondre en premier.

Le quatrieme cran -- que les slots 0x18 / 0x1a cites soient toujours ceux du build -- est tenu
AILLEURS, par `probe_477r25_slots_autres_interfaces.py`, dont le perimetre balaye `engine/**/*.py`
et confronte chaque citation a `data/symbols/<build>/metadata/interface_slots.tsv`.

100 % OFFLINE. ASCII only.
"""
from __future__ import annotations

import ast
import inspect

from engine.runner.components import OwnerComponent, UnitComponent
from engine.runner.operations import turnflow as TF
from engine.runner.state import State


def _etat(specs, cur):
    """`State` synthetique : `specs` = [(joueur, nb_vivantes, nb_mortes), ...]."""
    st = State()
    st.current_player_id = cur
    uid = 100
    for pl, vivantes, mortes in specs:
        for alive in ([True] * vivantes) + ([False] * mortes):
            uid += 1
            e = st.add_entity(uid)
            e.add_component(OwnerComponent(team=pl, player=pl))
            e.add_component(UnitComponent(visual_id="u%d" % uid, alive=alive))
    return st


# ------------------------------------------------------------------ 1. la VALEUR

#: `(libelle, specs, courant, attendu)` -- `attendu` DERIVE du decompile, etage par etage.
REGIMES = [
    ("duel, courant 3 vivant",          [(3, 2, 0), (4, 2, 0)],            3, 4),
    ("duel, courant 4 vivant",          [(3, 2, 0), (4, 2, 0)],            4, 3),
    ("duel, camp 4 entierement mort",   [(3, 2, 0), (4, 0, 2)],            3, 3),
    ("duel, COURANT 4 mort",            [(3, 2, 0), (4, 0, 2)],            4, 3),
    ("courant absent de l'ordre",       [(3, 2, 0), (4, 2, 0)],            9, 3),
    ("tous les joueurs morts",          [(3, 0, 2), (4, 0, 2)],            3, None),
    ("un seul joueur",                  [(3, 2, 0)],                       3, 3),
    ("3 joueurs, tous vivants",         [(3, 2, 0), (4, 2, 0), (5, 2, 0)], 4, 5),
    ("3 joueurs, le 2e mort",           [(3, 2, 0), (4, 0, 2), (5, 2, 0)], 3, 5),
    ("3 joueurs, COURANT 4 mort",       [(3, 2, 0), (4, 0, 2), (5, 2, 0)], 4, 5),
    ("4 joueurs, COURANT 4 et 5 morts",
     [(3, 2, 0), (4, 0, 2), (5, 0, 2), (6, 2, 0)],                         4, 6),
]


def test_find_next_player_suit_le_decompile_sur_les_onze_regimes():
    ecarts = [(lib, att, TF.find_next_player(_etat(sp, cur)))
              for lib, sp, cur, att in REGIMES
              if TF.find_next_player(_etat(sp, cur)) != att]
    assert not ecarts, "port != natif sur %d regime(s) : %r" % (len(ecarts), ecarts)


def _port_davant(state):
    """`find_next_player` TEL QU'IL ETAIT avant cette tranche -- les quatre etages fondus en un."""
    joueurs = set()
    for e in state.entities.values():
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        if oc is None or oc.player is None or (uc is not None and not uc.alive):
            continue
        joueurs.add(int(oc.player))
    order = sorted(joueurs)
    if not order:
        return None
    cur = state.current_player_id
    if cur not in order:
        return order[0]
    return order[(order.index(cur) + 1) % len(order)]


def test_au_moins_un_regime_separe_l_ancien_port_du_natif():
    """SANS CE TEST, LE PRECEDENT POURRAIT ETRE VERT EN NE MESURANT RIEN. Si aucun regime ne
    distinguait l'ancien port du natif, la restructuration serait invisible et le cliquet ne
    garderait qu'une tautologie -- le vice de l'ensemble VIDE qui passe pour vert."""
    separants = [lib for lib, sp, cur, att in REGIMES
                 if _port_davant(_etat(sp, cur)) != att]
    assert separants, "aucun regime ne separe l'ancien port du natif -- le cliquet ne garde rien"
    # Les deux regimes MESURES le 2026-08-06 : joueur COURANT entierement mort et >= 3 joueurs.
    # L'ancien port ne le trouvait plus dans son ordre (filtre en amont) et repartait de `order[0]`.
    assert "3 joueurs, COURANT 4 mort" in separants
    assert "4 joueurs, COURANT 4 et 5 morts" in separants


# ------------------------------------------------------------------ 2. la SEPARATION (AST)

ETAGES = ("player_turn_order", "find_turn_index", "should_player_skip_turn")


def test_find_next_player_appelle_les_trois_etages_nommes():
    """PROVENANCE, pas VALEUR : une recopie locale equivalente rendrait les memes verdicts."""
    arbre = ast.parse(inspect.getsource(TF.find_next_player))
    appels = {n.func.id for n in ast.walk(arbre)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    manquants = [e for e in ETAGES if e not in appels]
    assert not manquants, (
        "`find_next_player` n'appelle plus %r : les etages natifs sont re-fondus. Le natif les "
        "SEPARE (ordre de config / index sans filtre / skip dans la boucle) et c'est la separation "
        "que cette tranche porte." % (manquants,))


def test_les_trois_etages_citent_leur_symbole_natif():
    """Chaque etage porte le NOM natif qu'il mirrore -- c'est ce qui rend le grep code <-> table
    immediat, et ce qui survit au changement de build (les noms sont stables a 97,5 %, les adresses
    changent a 100 %)."""
    attendu = {
        "player_turn_order": "GetPlayerTurnOrder",
        "find_turn_index": "ChangeTurnOperation$$FindTurnIndex",
        "should_player_skip_turn": "ShouldPlayerSkipTurn",
        "find_next_player": "ChangeTurnOperation$$FindNextPlayer",
    }
    for nom, symbole in attendu.items():
        doc = (getattr(TF, nom).__doc__ or "")
        assert symbole in doc, "`%s` ne cite plus `%s`" % (nom, symbole)


# ------------------------------------------------------------------ 3. l'ORDRE ne filtre PAS

def test_l_ordre_de_tour_garde_un_joueur_entierement_mort():
    """`GetPlayerTurnOrder` est un accesseur de CONFIG (`BC.Player.TurnOrder`) : un joueur n'en
    sort JAMAIS. C'est le SKIP, dans la boucle, qui l'ecarte -- pas l'ordre."""
    st = _etat([(3, 2, 0), (4, 0, 2)], 3)
    assert TF.player_turn_order(st) == [3, 4], "le joueur 4 (toutes unites mortes) a quitte l'ordre"
    assert TF.should_player_skip_turn(st, 4) is True
    assert TF.should_player_skip_turn(st, 3) is False


def test_find_turn_index_rend_none_et_jamais_moins_un():
    """Le natif rend un `Nullable<int>` SANS valeur ; c'est l'APPELANT qui rabat sur `-1`. Les deux
    ne se confondent pas -- un `-1` rendu ici entrerait dans le `%` comme un index valide."""
    st = _etat([(3, 2, 0), (4, 2, 0)], 3)
    assert TF.find_turn_index(st, 3) == 0
    assert TF.find_turn_index(st, 4) == 1
    assert TF.find_turn_index(st, 9) is None
    assert TF.find_turn_index(st, None) is None
    assert TF.find_turn_index(st, 0) is None      # `if (playerEntityId == 0) return null`


def test_la_boucle_est_bornee_et_rend_none_quand_tous_sont_skippes():
    """`for (offset = 1 ; offset <= players.Count ; offset++)` puis `return null` : le natif ne
    boucle pas indefiniment quand aucun joueur n'est jouable."""
    st = _etat([(3, 0, 2), (4, 0, 2), (5, 0, 2)], 3)
    assert TF.find_next_player(st) is None
    assert TF.ChangeTurnOperation.execute(st) is None
    assert st.current_player_id == 3               # aucun `SetCurrentPlayer` n'a eu lieu


def test_change_turn_pose_le_joueur_calcule():
    st = _etat([(3, 2, 0), (4, 2, 0)], 3)
    assert TF.ChangeTurnOperation.execute(st) == 4
    assert st.current_player_id == 4
    assert TF.ChangeTurnOperation.execute(st) == 3
    assert st.current_player_id == 3
