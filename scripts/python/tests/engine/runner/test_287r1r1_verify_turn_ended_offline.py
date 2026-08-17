"""#287-r1-r1 -- `VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded` : la voie qui RE-OUVRE.

CE QUE CE FICHIER GARDE, en six etages. Le fil conducteur : #287-r1 avait porte la POSE du flag
`UnitFlag.NoActionAvailable` (par `FinishUnitTurnOperation`), pas son RETRAIT -- et le flag est
COLLANT (`UnitFlagsComponent$$RemoveTurnFlags(includeNoAction: 0)` le CONSERVE au changement de
tour). Le port ne pouvait donc que SUR-FERMER : une unite marquee une fois le restait pour toujours.

  1. `has_tiles_to_move_to` = `MovementQuery$$HasAnyMovablePositionsFor` : les gardes d'entree de
     `FindAnyOrAllMoveableTiles`, LUES -- `Has(UnitFlag.Moved) && ignoreUnitFlags == 0`, et
     `UnitExtensions$$CanMove` (type d'entite, trait `Stationary`). TRI-ETAT : sans board, `None`
     (NON MESURE), jamais `False` -- un `False` fabrique ferait POSER le flag a tort.

  2. `has_action_available` = `AttackQuery$$CanAttackAnyUnitFromAnyTileWithAnyAbility` : ses deux
     gates PUR-FLAG (`TurnEnded`, `Has(ActiveAbilityUsed)`) rendent `False` avec CERTITUDE ;
     `ActiveAbilitiesComponent` absent (canal `allAbilities` non demande) rend `None`.

  3. `_can_act` = le OU **court-circuite** du natif : `HasTilesToMoveTo` d'abord, et la propagation
     tri-etat ne fabrique jamais un verdict.

  4. `verify_unit_turn_ended` : les CINQ issues du corps natif (tour deja fini / unite morte / POSE /
     RETRAIT / rien), et l'ABSTENTION sur indetermine.

  5. LE BRANCHEMENT dans `Runner.apply` (ancrage LU : slot `IOperationProcessor` 0x21 de
     `IdunBattle.Messages.InputMessageProcessor$$RunPhase`), avec sa CONTRE-EPREUVE de PORTEE : le
     balayage ne touche QUE le joueur courant -- une unite adverse dans le meme etat n'est pas
     marquee. Sans cette contre-epreuve, « le flag est pose » ne prouverait pas que la borne native
     (`PlayerComponent$$get_CurrentlyOwnedUnitIds`) est respectee.

  6. LE FOYER : toute mutation du flag passe par `MarkUnitAsNoActionAvailableOperation` (#287-r1),
     jamais par une ecriture directe du composant. C'est ce qui empeche la 2e source de verite.

OFFLINE pur (aucune session live). ASCII only.
"""
from __future__ import annotations

from engine.entities.unit_flag import UnitFlag
from engine.runner.messages import EndTurnMessage
from engine.runner.runner import Runner
from engine.runner.state import State
from engine.runner.components import (ActiveAbilitiesComponent, MachineComponent, OwnerComponent,
                                      PositionComponent, UnitComponent, UnitFlagsComponent)
from engine.runner.operations import turnflow as TF
from engine.runner.operations.turnflow import (VerifyUnitsTurnFinishedOperation, _can_act,
                                               has_action_available,
                                               has_tiles_to_move_to, verify_units_turn_finished)
# #590-r6-r2 : `UnitExtensions$$CanMove` a demenage vers `runner/components.py` (suppression de
# l'arete d'import qui imposait un differe a `abilities/loki/attempted_possession.py`).
from engine.runner.components import unit_extensions_can_move as _can_move


def _mk_state(current_player: int = 3) -> State:
    """State minimal, SANS board : u1 (team 1, player 3), u2 (team 2, player 4)."""
    st = State()
    st.current_player_id = current_player
    for uid, (vid, team, player, col) in {1: ("unitA", 1, 3, 3), 2: ("unitB", 2, 4, 9)}.items():
        e = st.add_entity(uid)
        e.add_component(UnitComponent(vid, True))
        e.add_component(OwnerComponent(team=team, player=player))
        e.add_component(PositionComponent(col, col))
        e.add_component(UnitFlagsComponent())
    return st


def _flags(st: State, uid: int) -> UnitFlagsComponent:
    return st.get_entity(uid).get_component(UnitFlagsComponent)


# ------------------------------------------- 1. `HasTilesToMoveTo` : les gardes d'entree, LUES

def test_le_flag_moved_ferme_le_deplacement():
    """`if ((unitFlags.Has(UnitFlag.Moved) && !ignoreUnitFlags) || !CanMove(unit)) return false`.

    `ignoreUnitFlags` vaut **0** au call-site de `HasTilesToMoveTo` (litteral) : le gate MORD.
    C'est lui qui explique la mesure live du bras `apres_deplacement` -- une unite qui vient de
    bouger n'a plus de tuile ou aller, et se fait marquer si elle n'a en plus aucune cible."""
    st = _mk_state()
    _flags(st, 1).add(UnitFlag.Moved)
    assert has_tiles_to_move_to(st, 1) is False


def test_sans_board_le_verdict_est_NON_MESURE_pas_faux():
    """TRI-ETAT. Aucun gate ne mord et il n'y a pas de board -> `None`.

    Un `False` de repli serait la degradation DANGEREUSE : `_can_act` conclurait « plus d'options »
    et POSERAIT le flag sur une unite que le natif laisse jouer -- exactement la sur-fermeture que
    cette tranche existe pour reduire."""
    st = _mk_state()
    assert st.board is None
    assert has_tiles_to_move_to(st, 1) is None


def test_can_move_ferme_sur_le_type_d_entite_et_sur_Stationary():
    """`UnitExtensions$$CanMove` : `GetEntityType(unit) != EntityType.Unit` -> false. Une MACHINE OF
    WAR (`EntityType.Machine`) ne passe JAMAIS ce gate -- c'est aussi pourquoi le natif ne lui
    applique pas `VerifyUnitTurnEnded` mais `$$VerifyMachineTurnEnded`."""
    st = _mk_state()
    st.get_entity(1).add_component(MachineComponent())
    assert _can_move(st, 1) is False
    assert has_tiles_to_move_to(st, 1) is False


# --------------------------------- 2. `HasActionAvailable` : les verdicts CERTAINS, et le `None`

def test_les_deux_gates_pur_flag_rendent_faux_avec_certitude():
    """`if (flags.TurnEnded()) return false` puis `if (flags.Has(ActiveAbilityUsed)) return false`
    -- les deux premieres instructions de
    `AttackQuery$$CanAttackAnyUnitFromAnyTileWithAnyAbility`."""
    st = _mk_state()
    _flags(st, 1).add(UnitFlag.TurnFinished)
    assert has_action_available(st, 1) is False
    st2 = _mk_state()
    _flags(st2, 1).add(UnitFlag.ActiveAbilityUsed)
    assert has_action_available(st2, 1) is False


def test_composant_d_abilities_absent_rend_NON_MESURE():
    """`ActiveAbilitiesComponent` n'est peuple que si le seed a demande `allAbilities: true`. Son
    absence n'est PAS « aucune ability » : la boucle native itererait la `KeyedCollection` reelle.
    -> `None`, jamais `False`."""
    st = _mk_state()
    assert st.get_entity(1).get_component(ActiveAbilitiesComponent) is None
    assert has_action_available(st, 1, movable_is_empty=True) is None


# ------------------------------------------------------- 3. `_can_act` : le OU COURT-CIRCUITE

def test_le_ou_est_court_circuite_dans_l_ordre_natif(monkeypatch):
    """Les DEUX branches de `VerifyUnitTurnEnded` evaluent `HasTilesToMoveTo` EN PREMIER, et le OU
    court-circuite : quand il rend vrai, `HasActionAvailable` n'est PAS evalue. Ce n'est pas une
    optimisation -- c'est ce qui garantit que le port n'appelle `has_action_available` que dans le
    regime ou sa position d'evaluation (la tuile courante) est la BONNE."""
    st = _mk_state()
    appels: list = []
    monkeypatch.setattr(TF, "has_tiles_to_move_to", lambda s, u: True)
    monkeypatch.setattr(TF, "has_action_available",
                        lambda s, u, movable_is_empty=None: appels.append(u) or True)
    assert _can_act(st, 1) is True
    assert appels == [], "`HasActionAvailable` a ete evalue alors que le OU etait deja tranche"


def test_la_propagation_tri_etat_ne_fabrique_aucun_verdict(monkeypatch):
    """`None` d'un cote et `False` de l'autre = INDETERMINE, pas `False`."""
    st = _mk_state()
    monkeypatch.setattr(TF, "has_tiles_to_move_to", lambda s, u: None)
    monkeypatch.setattr(TF, "has_action_available", lambda s, u, movable_is_empty=None: False)
    assert _can_act(st, 1) is None
    monkeypatch.setattr(TF, "has_tiles_to_move_to", lambda s, u: False)
    assert _can_act(st, 1) is False


# ------------------------------------------- 4. `VerifyUnitTurnEnded` : les cinq issues du corps

def _verifie(st, uid):
    return VerifyUnitsTurnFinishedOperation.verify_unit_turn_ended(st, uid)


def test_tour_deja_fini_et_unite_morte_sortent_sans_rien_faire():
    """`if (flags.TurnEnded()) return` puis
    `if (TryGetComponent<HealthComponent>(out hp) && hp.IsDead()) return`."""
    st = _mk_state()
    _flags(st, 1).add(UnitFlag.TurnFinished)
    r = _verifie(st, 1)
    assert r["action"] is None and r["reason"] == "turn_ended"
    assert not _flags(st, 1).has(UnitFlag.NoActionAvailable)
    st2 = _mk_state()
    st2.get_entity(1).get_component(UnitComponent).alive = False
    r2 = _verifie(st2, 1)
    assert r2["action"] is None and r2["reason"] == "dead"


def test_pose_quand_l_unite_n_a_plus_d_options(monkeypatch):
    """Branche `!Has(NoActionAvailable)` : `if (HasTilesToMoveTo) return ; if (HasActionAvailable)
    return ;` puis slot 0x76."""
    st = _mk_state()
    monkeypatch.setattr(TF, "has_tiles_to_move_to", lambda s, u: False)
    monkeypatch.setattr(TF, "has_action_available", lambda s, u, movable_is_empty=None: False)
    r = _verifie(st, 1)
    assert r["action"] == "mark" and r["can_act"] is False
    assert _flags(st, 1).has(UnitFlag.NoActionAvailable)


def test_retrait_quand_l_unite_regagne_des_options(monkeypatch):
    """Branche `Has(NoActionAvailable)` : `if (!HasTilesToMoveTo && !HasActionAvailable) return ;`
    puis slot 0x77 (`MarkUnitAsActionAvailable`). C'est LA voie qui donne son nom a la tranche."""
    st = _mk_state()
    _flags(st, 1).add(UnitFlag.NoActionAvailable)
    monkeypatch.setattr(TF, "has_tiles_to_move_to", lambda s, u: True)
    r = _verifie(st, 1)
    assert r["action"] == "unmark" and r["can_act"] is True
    assert not _flags(st, 1).has(UnitFlag.NoActionAvailable)


def test_abstention_sur_indetermine_ne_mute_rien(monkeypatch):
    """`_can_act` indetermine -> NI pose NI retrait, dans les DEUX etats de depart. C'est ce qui
    empeche le port de fabriquer une mutation que rien n'a mesuree."""
    monkeypatch.setattr(TF, "has_tiles_to_move_to", lambda s, u: None)
    monkeypatch.setattr(TF, "has_action_available", lambda s, u, movable_is_empty=None: None)
    st = _mk_state()
    r = _verifie(st, 1)
    assert r["action"] is None and r["reason"] == "undetermined"
    assert not _flags(st, 1).has(UnitFlag.NoActionAvailable)
    st2 = _mk_state()
    _flags(st2, 1).add(UnitFlag.NoActionAvailable)
    r2 = _verifie(st2, 1)
    assert r2["action"] is None and r2["reason"] == "undetermined"
    assert _flags(st2, 1).has(UnitFlag.NoActionAvailable), (
        "l'abstention doit CONSERVER l'etat, pas le remettre a zero")


def test_rien_a_faire_quand_le_flag_est_deja_coherent(monkeypatch):
    """Les deux issues « return » du natif : flag absent + options presentes, flag pose + aucune
    option."""
    monkeypatch.setattr(TF, "has_tiles_to_move_to", lambda s, u: True)
    st = _mk_state()
    assert _verifie(st, 1)["action"] is None
    assert not _flags(st, 1).has(UnitFlag.NoActionAvailable)
    monkeypatch.setattr(TF, "has_tiles_to_move_to", lambda s, u: False)
    monkeypatch.setattr(TF, "has_action_available", lambda s, u, movable_is_empty=None: False)
    st2 = _mk_state()
    _flags(st2, 1).add(UnitFlag.NoActionAvailable)
    assert _verifie(st2, 1)["action"] is None
    assert _flags(st2, 1).has(UnitFlag.NoActionAvailable)


# --------------------------------------------------- 5. `Execute` et le BRANCHEMENT dans `apply`

def test_execute_ne_balaye_que_le_joueur_courant_et_ecarte_la_MoW(monkeypatch):
    """`Execute` itere `PlayerComponent$$get_CurrentlyOwnedUnitIds` du joueur COURANT (dont le
    `RemoveAll(<defait>)`), et traite la MACHINE OF WAR par `$$VerifyMachineTurnEnded`, un corps
    DIFFERENT -- que le port n'a pas : elle est donc COMPTEE, pas silencieusement traitee comme une
    unite."""
    monkeypatch.setattr(TF, "has_tiles_to_move_to", lambda s, u: False)
    monkeypatch.setattr(TF, "has_action_available", lambda s, u, movable_is_empty=None: False)
    st = _mk_state(current_player=3)
    mow = st.add_entity(5)
    mow.add_component(UnitComponent("mow", True))
    mow.add_component(OwnerComponent(team=1, player=3))
    mow.add_component(UnitFlagsComponent())
    mow.add_component(MachineComponent())
    mort = st.add_entity(6)
    mort.add_component(UnitComponent("mort", False))
    mort.add_component(OwnerComponent(team=1, player=3))
    mort.add_component(UnitFlagsComponent())
    bilan = verify_units_turn_finished(st)
    assert bilan["marked"] == 1 and bilan["machines_skipped"] == 1
    assert _flags(st, 1).has(UnitFlag.NoActionAvailable)
    assert not _flags(st, 5).has(UnitFlag.NoActionAvailable), "la MoW ne passe pas par cette voie"
    assert not _flags(st, 6).has(UnitFlag.NoActionAvailable), "une unite morte est hors de la liste"
    assert not _flags(st, 2).has(UnitFlag.NoActionAvailable), (
        "CONTRE-EPREUVE DE PORTEE : l'unite du joueur ADVERSE, dans le meme etat, n'est pas "
        "balayee -- sans ce cran, la borne `CurrentlyOwnedUnitIds` ne serait pas gardee")


def test_le_branchement_dans_apply_est_arme(monkeypatch):
    """L'ancrage : `Runner.apply` (borne du message top-level cote port) invoque la voie, comme
    `RunPhase` invoque le slot 0x21 en phase NON interne. Sans handler installe, le message ne fait
    rien d'autre -- ce qui isole le geste mesure."""
    monkeypatch.setattr(TF, "has_tiles_to_move_to", lambda s, u: False)
    monkeypatch.setattr(TF, "has_action_available", lambda s, u, movable_is_empty=None: False)
    st = _mk_state()
    r = Runner(st)
    assert r.last_verify_turn_finished is None
    r.apply(EndTurnMessage(advance=False))
    assert (r.last_verify_turn_finished or {}).get("marked") == 1
    assert _flags(st, 1).has(UnitFlag.NoActionAvailable)


# --------------------------------------------------------------- 6. le FOYER UNIQUE de la mutation

def test_la_mutation_passe_par_le_foyer_MarkUnitAsNoActionAvailable(monkeypatch):
    """#287-r1 a fait de `MarkUnitAsNoActionAvailableOperation` le FOYER UNIQUE du flag. Cette
    tranche n'ouvre pas une 2e source de verite : les deux slots (0x76 POSE / 0x77 RETRAIT) y
    passent, `reverse` faisant la difference."""
    appels: list = []
    orig = TF.MarkUnitAsNoActionAvailableOperation.execute

    def _spy(state, unit_id, reverse=False):
        appels.append((int(unit_id), bool(reverse)))
        return orig(state, unit_id, reverse)

    monkeypatch.setattr(TF.MarkUnitAsNoActionAvailableOperation, "execute", staticmethod(_spy))
    monkeypatch.setattr(TF, "has_tiles_to_move_to", lambda s, u: False)
    monkeypatch.setattr(TF, "has_action_available", lambda s, u, movable_is_empty=None: False)
    st = _mk_state()
    _verifie(st, 1)
    monkeypatch.setattr(TF, "has_tiles_to_move_to", lambda s, u: True)
    _verifie(st, 1)
    assert appels == [(1, False), (1, True)], (
        "la POSE doit passer par `reverse=False` et le RETRAIT par `reverse=True`, tous deux par "
        "le foyer -- une ecriture directe du composant ne serait pas vue ici")
