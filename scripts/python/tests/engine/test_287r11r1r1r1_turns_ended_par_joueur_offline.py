"""#287-r11-r1-r1-r1 -- CLIQUET du compteur `TurnComponent.<Dictionary @+0x40>`, VENTILE PAR JOUEUR.

Le second bras de `IdunBattle.Core.Services.BattleQuery$$HasMinimumRemainingTurns` a besoin de
`IdunBattle.Entities.Components.TurnComponent$$GetAmountOfTurnsEndedByPlayer(GetPlayerTurnOrder()[0])`.
Le port n'avait AUCUN substrat pour ce dictionnaire et LEVAIT (`NotImplementedError`). Les deux
candidats voisins n'en sont pas, et ce fichier garde qu'on n'y retombe pas :

  * `State.turn_counts` mirroir `TurnComponent+0x38` -- les tours **DEMARRES** ;
  * `decisionView.turnsEnded` publie `GetAmountOfTurnsEnded(matchTurn, 0)` = `Sum(dict.Values)`,
    la **SOMME sur tous les joueurs**.

CE QUI A DEBLOQUE LA TRANCHE N'EST PAS UNE FORMULE, C'EST UN FAIT DE STRUCTURE.
`IdunBattle.Entities.Components.TurnComponent$$SetCurrentPlayer` est l'ecrivain **UNIQUE** des DEUX
dictionnaires (verifie sur les 19 methodes de `TurnComponent` : `.ctor` les cree vides, `Copy` les
clone, aucune autre ne les touche) et il n'a qu'UN appelant,
`IdunBattle.Operations.ChangeTurnOperation$$Execute`. Son corps, verbatim :

    if (get_CurrentPlayerId() == nextPlayerId)  return;                    # NO-OP, AVANT tout bump
    if (!started.ContainsKey(next))             started.Add(next, 0);
    if (get_CurrentPlayerId() != 0) { ended.TryAdd(cur, 0); ended[cur] += 1; }
    prev = get_CurrentPlayerId(); <+0x24> = next; <+0x18> = prev;
    started[get_CurrentPlayerId()] += 1;

D'ou l'IDENTITE, LUE et non ajustee : `ended[p] == started[p] - (p == CurrentPlayerId ? 1 : 0)`.
C'est elle que `snapshot._load_turns_ended` utilise pour SEEDER, et `turnflow.set_current_player`
pour TENIR le dict pendant la partie.

CE FICHIER GARDE SIX ETAGES, et aucun ne suffit seul :
  1. le SUBSTRAT existe, et il est DISTINCT de ses deux voisins ;
  2. l'ECRIVAIN : bump du SORTANT seulement, NO-OP respecte, joueur `0` ecarte ;
  3. l'IDENTITE, verifiee sur une sequence de tours REELLE (`ChangeTurn` + `StartTurn`) ;
  4. le SEED, et son TRI-ETAT ;
  5. la LECTURE : `!ContainsKey -> 0`, et elle est VENTILEE (le compteur d'un autre joueur ne fuit
     pas) ;
  6. le FOYER UNIQUE de `GetPlayerTurnOrder` -- deux stand-ins qui derivent seraient un bug muet.

Plus le MUTANT : un port qui lirait `turn_counts` (DEMARRES) au lieu de `turns_ended` doit etre
SEPARE par au moins un point, et le test ASSERTIONNE SON PROPRE NON-VIDE.

100 % OFFLINE. ASCII only (cp1252).
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: PERIMETRE MESURE, pas suppose : l'import de ce module charge **389** modules `engine/**` et
#: exactement DEUX modules hors `engine/` (`gameconfig.py`, `hexgeo.py`) -- compte re-derivable en
#: important le fichier et en filtrant `sys.modules` sur `scripts/python/`. C'est pourquoi ce
#: declencheur ne porte PAS le glob `scripts/python/*.py` du parc : il nomme les deux.
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des conftest et sa fermeture. Aucun
        # test ne les IMPORTE (c'est de la semantique pytest) et le verdict en depend.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # PROPRE A CE FICHIER. `engine/**` est pris en bloc et c'est une MESURE : 389 de ses
        # modules entrent dans la fermeture (le turn-flow tire tout le dispatch de triggers).
        # Une liste feuille a feuille serait perimee au premier import ajoute -- exactement le
        # faux vert que ce cliquet combat. Foyers vraiment load-bearing, pour la relecture :
        # `engine/runner/state.py` (le champ `turns_ended`),
        # `engine/runner/operations/turnflow.py` (`set_current_player`, l'ecrivain),
        # `engine/runner/snapshot.py` (`_load_turns_ended`, le seed),
        # `engine/services/battle_query.py` (`get_amount_of_turns_ended_by_player`,
        # `get_player_turn_order`, `has_minimum_remaining_turns`).
        "scripts/python/engine/**/*.py",
        # Les DEUX seuls modules hors `engine/` de la fermeture, MESURES.
        "scripts/python/gameconfig.py", "scripts/python/hexgeo.py",
        # `victory_config.get_max_rounds` DERIVE son defaut de la seed versionnee quand
        # `State.victory_conditions` est `None` (tri-etat) : une seed qui porterait
        # `MainPlayerRoundLimitation` armerait le bit pour tous les etats non explicites.
        "data/seed-bc.json",
    ),
    "build": True,
    "toujours": False,
    "raison": "Verdicts figes : l'existence et la DISTINCTION du mirror `TurnComponent+0x40` "
              "(`State.turns_ended`) face a ses deux voisins, le comportement de l'ecrivain unique "
              "`SetCurrentPlayer` (bump du SORTANT, NO-OP, joueur 0), l'IDENTITE "
              "`ended = started - [courant]` sur une sequence de tours reelle, le seed et son "
              "tri-etat, la lecture `!ContainsKey -> 0` ventilee, le MUTANT `turn_counts`, et le "
              "foyer unique de `GetPlayerTurnOrder` verifie par MORSURE. Aucun runner, aucune "
              "session Frida. `build: True` parce que `gameconfig.py` est dans la fermeture et lit "
              "le gameconfig du JEU INSTALLE, hors arbre : un changement de build peut donc "
              "basculer un verdict sans qu'aucun fichier du depot ne bouge.",
}

from engine.runner.components import OwnerComponent, UnitComponent  # noqa: E402
from engine.runner.operations import turnflow as TF                 # noqa: E402
from engine.runner.state import State                               # noqa: E402
from engine.services import battle_query as BQ                      # noqa: E402


def _etat(specs, cur):
    """`State` synthetique : `specs` = [(joueur, nb_vivantes), ...]. Meme forme que le cliquet
    `test_462r4eor2r1r1r1_cycle_de_tour_offline.py`, dont ce fichier prolonge le regime."""
    st = State()
    st.current_player_id = cur
    uid = 100
    for pl, vivantes in specs:
        for _ in range(vivantes):
            uid += 1
            e = st.add_entity(uid)
            e.add_component(OwnerComponent(team=pl, player=pl))
            e.add_component(UnitComponent(visual_id="u%d" % uid, alive=True))
    return st


# =================================================================================================
# ETAGE 1 -- LE SUBSTRAT EXISTE, ET IL N'EST NI L'UN NI L'AUTRE DES DEUX VOISINS
# =================================================================================================

def test_le_state_porte_le_dict_des_tours_TERMINES():
    """`State.turns_ended` -- le mirror de `TurnComponent+0x40`. Il n'existait pas."""
    st = State()
    assert hasattr(st, "turns_ended"), "`State` ne porte pas le mirror de `TurnComponent+0x40`"
    assert st.turns_ended == {}, "les deux dicts naissent VIDES (`TurnComponent$$.ctor`)"
    assert st.turns_ended is not st.turn_counts, (
        "`turns_ended` et `turn_counts` doivent etre DEUX dictionnaires -- le natif en a deux "
        "(`+0x40` termines, `+0x38` demarres), ecrits sur deux joueurs DIFFERENTS")


def test_les_deux_dicts_divergent_des_le_premier_changement_de_joueur():
    """CONTRE-EPREUVE du precedent : deux dicts qui resteraient egaux ne prouveraient rien."""
    st = _etat([(3, 2), (4, 2)], 3)
    st.turn_counts = {3: 1}
    TF.ChangeTurnOperation.execute(st)               # 3 -> 4 : `ended[3] += 1`
    assert st.turns_ended == {3: 1}
    assert st.turn_counts == {3: 1}, "ChangeTurn ne doit PAS toucher le dict des DEMARRES ici"
    TF.StartTurnOperation.execute(st, 4)             # `started[4] += 1` (placement HERITE du port)
    assert st.turn_counts == {3: 1, 4: 1} and st.turns_ended == {3: 1}, (
        "apres la paire ChangeTurn+StartTurn les deux dicts DIFFERENT : le joueur 4 a demarre un "
        "tour qu'il n'a pas termine")


# =================================================================================================
# ETAGE 2 -- L'ECRIVAIN UNIQUE : `TurnComponent$$SetCurrentPlayer`
# =================================================================================================

def test_set_current_player_bumpe_le_SORTANT_et_lui_seul():
    """`ended[CurrentPlayerId] += 1` -- c'est le joueur qui PART, pas celui qui arrive."""
    st = _etat([(3, 2), (4, 2)], 3)
    TF.set_current_player(st, 4)
    assert st.turns_ended == {3: 1}, "le bump doit porter sur le SORTANT (3), pas l'entrant (4)"
    assert st.current_player_id == 4
    TF.set_current_player(st, 3)
    assert st.turns_ended == {3: 1, 4: 1}


def test_le_NO_OP_ne_bumpe_RIEN():
    """`if (get_CurrentPlayerId() == nextPlayerId) return;` est AVANT les deux bumps.

    ⚠ C'est le regime `un seul joueur encore jouable` : `FindNextPlayer` rend le joueur COURANT, et
    le natif ne compte alors AUCUN tour -- ni demarre, ni termine. La note du port ecrivait
    l'inverse (<< c'est un tour de plus pour lui >>) avant cette tranche."""
    st = _etat([(3, 2)], 3)
    st.turns_ended = {3: 2}
    TF.set_current_player(st, 3)
    assert st.turns_ended == {3: 2}, "le NO-OP a bumpe -- le retour anticipe precede les bumps"
    assert TF.ChangeTurnOperation.execute(st) == 3, "un seul joueur jouable -> FindNextPlayer rend 3"
    assert st.turns_ended == {3: 2}, "ChangeTurn sur le joueur COURANT ne doit rien compter"


def test_le_joueur_ZERO_est_ecarte():
    """`if (get_CurrentPlayerId() != 0)` : `0` = AUCUN joueur actif (`HasActivePlayer` = `!= 0`).
    Une cle `0` dans le dict natif serait impossible."""
    st = _etat([(3, 2), (4, 2)], 0)
    TF.set_current_player(st, 3)
    assert st.turns_ended == {}, "le joueur 0 ne doit JAMAIS entrer au dict"
    st2 = _etat([(3, 2), (4, 2)], None)
    TF.set_current_player(st2, 3)
    assert st2.turns_ended == {}, "`current_player_id is None` (etat non seede) n'est pas un joueur"


# =================================================================================================
# ETAGE 3 -- L'IDENTITE, SUR UNE SEQUENCE DE TOURS REELLE
# =================================================================================================

def test_identite_ended_egale_started_moins_le_courant():
    """`ended[p] == started[p] - (p == CurrentPlayerId ? 1 : 0)`, apres CHAQUE tour joue.

    On enchaine `ChangeTurn` puis `StartTurn` -- exactement la paire qu'`advance_turn` emet -- et on
    verifie l'identite a chaque pas. Elle est le SEUL fondement du seed : si elle cesse de tenir, le
    seed devient une supposition."""
    st = _etat([(3, 2), (4, 2)], 3)
    st.turn_counts = {3: 1}                      # le joueur 3 a demarre le tour en cours
    for _ in range(6):
        nxt = TF.ChangeTurnOperation.execute(st)
        assert nxt is not None
        TF.StartTurnOperation.execute(st, nxt)
        cur = st.current_player_id
        for p, started in st.turn_counts.items():
            attendu = int(started) - (1 if int(p) == int(cur) else 0)
            assert st.turns_ended.get(int(p), 0) == attendu, (
                "identite rompue pour le joueur %d : ended=%r started=%r courant=%r"
                % (p, st.turns_ended.get(int(p)), started, cur))
    assert sum(st.turns_ended.values()) >= 5, "la sequence doit avoir vraiment compte des tours"


def test_la_SOMME_n_est_pas_la_VENTILATION():
    """`decisionView.turnsEnded` publie `Sum(dict.Values)`. Le rabattre serait FAUX des que les
    joueurs n'ont pas termine le meme nombre de tours -- et ce test assertionne son propre non-vide."""
    st = _etat([(3, 2), (4, 2)], 3)
    TF.set_current_player(st, 4)                 # ended = {3: 1}
    somme = sum(st.turns_ended.values())
    ventile = BQ.get_amount_of_turns_ended_by_player(st, 4)
    assert somme == 1 and ventile == 0, (somme, ventile)
    assert somme != ventile, "regime DEGENERE : la somme et la ventilation coincident"


# =================================================================================================
# ETAGE 4 -- LE SEED (`snapshot._load_turns_ended`) ET SON TRI-ETAT
# =================================================================================================

def test_le_seed_reconstruit_la_ventilation_depuis_le_dict_jumeau():
    from engine.runner.snapshot import _load_turns_ended
    st = _etat([(3, 2), (4, 2)], 3)
    st.turn_counts = {3: 4, 4: 3}
    _load_turns_ended(st)
    assert st.turns_ended == {3: 3, 4: 3}, (
        "le COURANT (3) a un tour demarre de plus que termine ; l'autre est a egalite")
    st.current_player_id = 4
    st.turns_ended = {}
    _load_turns_ended(st)
    assert st.turns_ended == {3: 4, 4: 2}


def test_le_seed_ne_fabrique_aucune_cle():
    """TRI-ETAT : un joueur ABSENT de `turn_counts` (aucune unite vivante portant la stat 12) reste
    ABSENT ici. On ne fabrique pas un `0` qui se lirait comme une mesure -- c'est la LECTURE
    (`!ContainsKey -> 0`) qui rend le zero, et elle, elle mirroir le natif."""
    from engine.runner.snapshot import _load_turns_ended
    st = _etat([(3, 2), (4, 2)], 3)
    st.turn_counts = {3: 2}
    _load_turns_ended(st)
    assert st.turns_ended == {3: 1}, "le joueur 4, non mesure, ne doit pas entrer au dict"
    assert 4 not in st.turns_ended


def test_le_seed_ne_rend_jamais_un_compte_negatif():
    """`turn_counts` est DERIVE (max de la stat 12 per-unite) : il peut valoir `0` pour le joueur
    courant sur une capture partielle. `0 - 1` serait un compte negatif que le natif ne peut pas
    produire."""
    from engine.runner.snapshot import _load_turns_ended
    st = _etat([(3, 2)], 3)
    st.turn_counts = {3: 0}
    _load_turns_ended(st)
    assert st.turns_ended == {3: 0}


# =================================================================================================
# ETAGE 5 -- LA LECTURE : `GetAmountOfTurnsEndedByPlayer`
# =================================================================================================

def test_cle_absente_rend_zero_par_LECTURE():
    """`if (!ended.ContainsKey(playerId)) return 0;` -- branche LUE du decompile."""
    st = _etat([(3, 2), (4, 2)], 3)
    st.turns_ended = {3: 5}
    assert BQ.get_amount_of_turns_ended_by_player(st, 3) == 5
    assert BQ.get_amount_of_turns_ended_by_player(st, 4) == 0
    assert BQ.get_amount_of_turns_ended_by_player(st, None) == 0
    assert BQ.get_amount_of_turns_ended_by_player(None, 3) == 0     # pas de match -> dict vide


def test_has_minimum_remaining_turns_lit_le_PREMIER_de_l_ordre_de_tour():
    """Le natif compte les tours de `GetPlayerTurnOrder()[0]`, PAS ceux du proprietaire du caster.
    Le test le montre en ne bougeant QUE le compteur du second joueur : le verdict ne doit pas
    bouger."""
    st = _etat([(3, 2), (4, 2)], 3)
    st.victory_conditions = {"MainPlayerRoundLimitation": 3}
    st.turns_ended = {3: 1, 4: 1}
    assert BQ.has_minimum_remaining_turns(999, 2, state=st) is True          # 2 <= 3 - 1
    st.turns_ended = {3: 1, 4: 99}
    assert BQ.has_minimum_remaining_turns(999, 2, state=st) is True          # 4 n'est PAS lu
    st.turns_ended = {3: 2, 4: 0}
    assert BQ.has_minimum_remaining_turns(999, 2, state=st) is False         # 2 <= 3 - 2


def test_MUTANT_lire_les_tours_DEMARRES_est_SEPARE():
    """FRONTIERE. Un port qui aurait rabattu le second bras sur `State.turn_counts` (le dict
    `+0x38`) coinciderait souvent -- les deux ne different que d'UN, et seulement pour le joueur
    COURANT. Ce test exhibe le point de separation et ASSERTIONNE SON PROPRE NON-VIDE."""
    separateurs = []
    for started in range(0, 6):
        st = _etat([(3, 2), (4, 2)], 3)
        st.victory_conditions = {"MainPlayerRoundLimitation": 3}
        st.turn_counts = {3: started, 4: started}
        from engine.runner.snapshot import _load_turns_ended
        _load_turns_ended(st)
        vrai = BQ.has_minimum_remaining_turns(999, 2, state=st)
        mutant = (2 <= 3 - int(st.turn_counts.get(3, 0)))
        if vrai != mutant:
            separateurs.append(started)
    assert separateurs, (
        "aucun point ne separe `turns_ended` de `turn_counts` -- le cliquet ne garderait rien")


# =================================================================================================
# ETAGE 6 -- LE FOYER UNIQUE DE `GetPlayerTurnOrder`
# =================================================================================================

def test_player_turn_order_a_UN_SEUL_foyer(monkeypatch):
    """`turnflow.player_turn_order` DELEGUE a `battle_query.get_player_turn_order`, son foyer natif
    (`GetPlayerTurnOrder` est une methode de `BattleQuery`, et `HasMinimumRemainingTurns` l'appelle).

    ⚠ La delegation est verifiee par MORSURE, pas par lecture du source : c'est la seule facon de
    distinguer une delegation d'une recopie equivalente. Un `from ... import get_player_turn_order`
    au niveau module (forme A) gelerait la liaison et NE MORDRAIT PAS -- exactement le vice mesure
    par #484/#429-r1."""
    monkeypatch.setattr(BQ, "get_player_turn_order", lambda state=None: [77, 88])
    assert TF.player_turn_order(_etat([(3, 2), (4, 2)], 3)) == [77, 88], (
        "`turnflow.player_turn_order` ne delegue pas -- deux stand-ins de l'ordre de tour peuvent "
        "desormais deriver l'un de l'autre en silence")


def test_l_ordre_de_tour_reste_le_stand_in_par_ids_croissants():
    """Le corps a demenage, le COMPORTEMENT ne bouge pas : ids d'entite croissants des joueurs
    porteurs d'unites, SANS filtre de vivacite (c'est le SKIP qui ecarte, pas l'ordre)."""
    st = _etat([(5, 1), (3, 1), (4, 1)], 3)
    assert BQ.get_player_turn_order(st) == [3, 4, 5]
    assert TF.player_turn_order(st) == [3, 4, 5]
    assert BQ.get_player_turn_order(None) == [], "pas d'etat -> aucun joueur, jamais une exception"
