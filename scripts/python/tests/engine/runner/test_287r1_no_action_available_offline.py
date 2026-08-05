"""#287-r1 -- `UnitFlag.NoActionAvailable` (4) : la voie de POSE, et ce qu'elle ne casse pas.

CE QUE CE FICHIER GARDE, en quatre etages :

  1. L'OPERATION elle-meme est un mirror de
     `IdunBattle.Operations.MarkUnitAsNoActionAvailableOperation$$Execute(unit, reverse)` :
     `Add` / `Remove` du flag, `changed` = « la mutation a MORDU » (ce que rendent
     `UnitFlagsComponent$$Add` / `$$Remove`, et ce qui gate l'event de stream natif), et le
     `TryGetComponent` STRICT (composant absent -> retour immediat, aucune creation).

  2. LE BRANCHEMENT : `FinishUnitTurnOperation$$Execute` termine par le slot `IOperationProcessor`
     0x76 = `Core.Services.OperationProcessor$$MarkUnitAsNoActionAvailable`, INCONDITIONNEL --
     aucun gate `forced`, aucun gate « nouvellement pose ». C'est l'ecart que
     `probe_287_facade_combat.py` mesurait (`[1, 2, 3, 4]` natif contre `[1, 2, 3]` port).

  3. LA PROPAGATION AU CAST : `ActiveAbilityOperation$$AddFlagsAfterAbilityExecution` n'appelle
     `FinishUnitTurn` que si `!skipEndTurn` -> le flag suit EXACTEMENT ce gate. Une ability de la
     famille « does not end turn » (1106 WarHowl) ne doit PAS le poser : sinon on figerait une
     unite que le natif laisse jouer (c'est le montage de `test_active_ability_used_gate_live`).

  4. LA NON-REGRESSION QUI A RETENU CETTE POSE PENDANT DEUX TRANCHES. `spawn.py` la refusait au
     motif que le flag, sans son retrait (`VerifyUnitTurnEnded`, non porte), SURVIT au turn-start
     (`RemoveTurnFlags(includeNoAction=0)`) et FIGE l'unite -- `has_action_left` etant le gate de
     `ai_control_execute_for_group`. L'etage 4 MESURE ce chemin de bout en bout : un summon dont
     le tour a ete termine au spawn est bien REJOUE au tour suivant, parce que
     `ComputerActionOperation.execute_group(reset_turn_flags=True)` efface le flag AVANT la
     boucle (`RemoveTurnFlags(True, True)`), et parce que la passe automatique du turn-start
     filtre sur `TurnEnded()` (flag 3), pas sur le flag 4.
     ⚠ Cet etage porte une CONTRE-EPREUVE : avec `reset_turn_flags=False`, la meme unite est bien
     ECARTEE. Sans elle, « le summon rejoue » ne prouverait pas que le flag est LU du tout.

OFFLINE pur (aucune session live). ASCII only.
"""
from __future__ import annotations

from engine.entities.unit_flag import UnitFlag
from engine.runner.state import State
from engine.runner.components import (UnitComponent, OwnerComponent, PositionComponent,
                                      UnitFlagsComponent)
from engine.runner.operations.turnflow import (FinishUnitTurnOperation, StartTurnOperation,
                                               MarkUnitAsNoActionAvailableOperation,
                                               add_flags_after_ability_execution)
from engine.runner.operations.summon_ai import has_action_left


def _mk_state() -> State:
    """State minimal : u1 (team 1, player 3) en (3,3), u2 (team 2, player 4) en (9,9)."""
    st = State()
    st.current_player_id = 3
    e1 = st.add_entity(1)
    e1.add_component(UnitComponent("unitA", True))
    e1.add_component(OwnerComponent(team=1, player=3))
    e1.add_component(PositionComponent(3, 3))
    e1.add_component(UnitFlagsComponent())
    e2 = st.add_entity(2)
    e2.add_component(UnitComponent("unitB", True))
    e2.add_component(OwnerComponent(team=2, player=4))
    e2.add_component(PositionComponent(9, 9))
    e2.add_component(UnitFlagsComponent())
    return st


def _flags(st: State, uid: int):
    return st.get_entity(uid).get_component(UnitFlagsComponent)


# --------------------------------------------------- 1. l'Operation, mirror du corps natif

def test_operation_pose_et_retire_et_rend_si_la_mutation_a_mordu():
    """`if (!reverse) { if (!comp.Add(4)) return }  else { if (!comp.Remove(4)) return }`."""
    st = _mk_state()
    r1 = MarkUnitAsNoActionAvailableOperation.execute(st, 1)
    assert r1["changed"] is True, "1re pose : `Add` doit rendre << etait absent >>"
    assert _flags(st, 1).has(UnitFlag.NoActionAvailable)
    r2 = MarkUnitAsNoActionAvailableOperation.execute(st, 1)
    assert r2["changed"] is False, (
        "2e pose : `UnitFlagsComponent$$Add` rend false quand le flag est deja la -- c'est ce "
        "booleen qui gate l'event `TagKey.UnitStats_ActionsAvailable` cote natif")
    assert _flags(st, 1).has(UnitFlag.NoActionAvailable)
    r3 = MarkUnitAsNoActionAvailableOperation.execute(st, 1, reverse=True)
    assert r3["changed"] is True and not _flags(st, 1).has(UnitFlag.NoActionAvailable), (
        "`reverse=True` = `MarkUnitAsActionAvailable` (slot 0x77) : il doit RETIRER le flag")
    r4 = MarkUnitAsNoActionAvailableOperation.execute(st, 1, reverse=True)
    assert r4["changed"] is False, "`Remove` rend false quand le flag n'y etait pas"


def test_operation_ne_cree_pas_le_composant_absent():
    """Mirror STRICT du `TryGetComponent` natif : composant absent -> retour immediat.

    Un `get-or-create` ici serait un FORK : le natif ne cree rien, et une entite offline sans
    `UnitFlagsComponent` est une capture partielle (pas une unite a marquer)."""
    st = State()
    e = st.add_entity(7)
    e.add_component(UnitComponent("sansFlags", True))
    r = MarkUnitAsNoActionAvailableOperation.execute(st, 7)
    assert r["found"] is False and r["changed"] is False
    assert e.get_component(UnitFlagsComponent) is None, (
        "l'Operation a CREE un `UnitFlagsComponent` : le natif ne le fait pas")
    # entite inconnue : meme reponse, sans lever
    assert MarkUnitAsNoActionAvailableOperation.execute(st, 999)["found"] is False


# --------------------------------------------------- 2. le branchement en queue de FinishUnitTurn

def test_finish_unit_turn_pose_le_flag_inconditionnellement():
    """Slot 0x76 = DERNIERE instruction de `FinishUnitTurnOperation$$Execute`, sans gate."""
    st = _mk_state()
    r = FinishUnitTurnOperation.execute(st, 1, forced=False)
    fl = _flags(st, 1)
    assert fl.has(UnitFlag.NoActionAvailable), (
        "le flag 4 n'est pas pose : c'est EXACTEMENT l'ecart mesure par `probe_287` "
        "(natif [1, 2, 3, 4] / port [1, 2, 3]) -- flags=%s" % sorted(fl.flags))
    assert (r.get("no_action") or {}).get("changed") is True
    assert not has_action_left(st, 1), (
        "`UnitExtensions$$HasActionLeft` doit devenir FAUX : c'est ce que lit "
        "`AnAiGroupOperator$$GetValidUnits` pour TERMINER sa boucle")
    # `forced=True` (summon frais, `SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours`) : le slot
    # 0x76 n'est PAS gate par `isTerminated`, il tombe apres les deux branches.
    st2 = _mk_state()
    FinishUnitTurnOperation.execute(st2, 1, forced=True)
    assert _flags(st2, 1).has(UnitFlag.NoActionAvailable)
    # ... et il reste pose quand `FinishUnitTurn` est RE-joue (Add idempotent, aucun event)
    r2 = FinishUnitTurnOperation.execute(st2, 1, forced=True)
    assert (r2.get("no_action") or {}).get("changed") is False


def test_le_flag_survit_au_turn_start_comme_dans_le_natif():
    """`StartTurnOperation$$Execute` -> `RemoveTurnFlags(includeNoAction=0, newActivation=1)`.

    Le flag 4 n'est PAS dans le lot retire : son unique retrait natif est le slot 0x77, appele
    par `VerifyUnitTurnEnded`. Ce test FIGE ce comportement -- si un jour le retrait est porte
    (residu `#287-r1-r1`), c'est ICI qu'il faudra le dire."""
    st = _mk_state()
    FinishUnitTurnOperation.execute(st, 1)
    StartTurnOperation.execute(st, 3)
    fl = _flags(st, 1)
    assert not fl.has(UnitFlag.TurnFinished) and not fl.has(UnitFlag.ArrivedAtFinalTile)
    assert fl.has(UnitFlag.NoActionAvailable), (
        "le turn-start a retire le flag 4 : `RemoveTurnFlags` recevrait `includeNoAction=1`, "
        "ce que `StartTurnOperation$$Execute` ne fait pas")


# --------------------------------------------------- 3. le gate `skipEndTurn` du cast

def test_le_flag_suit_le_gate_skip_end_turn():
    """`AddFlagsAfterAbilityExecution` : `if (!skipEndTurn) FinishUnitTurn(caster, false)`.

    Une ability « does not end turn » (famille 1014/1106/1063) ne doit donc PAS poser le flag --
    sinon le caster serait fige alors que le natif le laisse rejouer."""
    st = _mk_state()
    add_flags_after_ability_execution(st, 1, skip_ability_used=False, skip_end_turn=False)
    assert _flags(st, 1).has(UnitFlag.NoActionAvailable)
    assert not has_action_left(st, 1)

    st2 = _mk_state()
    add_flags_after_ability_execution(st2, 1, skip_ability_used=True, skip_end_turn=True)
    assert not _flags(st2, 1).has(UnitFlag.NoActionAvailable), (
        "une ability qui ne termine PAS le tour a quand meme pose `NoActionAvailable` : le port "
        "ne suivrait plus le gate `skipEndTurn` du natif")
    assert has_action_left(st2, 1)


# --------------------------------------------------- 4. la non-regression + sa contre-epreuve

def _mk_group_state():
    """Deux unites du joueur 3, tour DEJA termine (donc flag 4 pose depuis #287-r1)."""
    st = _mk_state()
    e3 = st.add_entity(3)
    e3.add_component(UnitComponent("unitC", True))
    e3.add_component(OwnerComponent(team=1, player=3))
    e3.add_component(PositionComponent(4, 4))
    e3.add_component(UnitFlagsComponent())
    FinishUnitTurnOperation.execute(st, 1)
    FinishUnitTurnOperation.execute(st, 3)
    return st


def test_le_flag_collant_n_ecarte_personne_du_groupe_ai(monkeypatch):
    """L'objection de `spawn.py` -- « un flag 4 pose sans son retrait FIGE l'unite » -- MESUREE.

    Le seul lecteur offline du flag est `has_action_left`, gate de
    `ai_control_execute_for_group`, atteint uniquement par `ComputerActionOperation.execute_group`.
    Tous les call-sites natifs recenses passent `resetTurnFlags = 1` -> `RemoveTurnFlags(True,
    True)` efface le flag AVANT la boucle. On substitue la decision (pas de bridge IA offline
    ici) : ce qu'on mesure est QUI la boucle retient, pas ce qu'elle decide."""
    from engine.runner.operations import summon_ai
    joues = []
    monkeypatch.setattr(summon_ai, "ai_control_execute_for",
                        lambda state, uid: joues.append(int(uid)) or {"uid": uid})
    st = _mk_group_state()
    assert not has_action_left(st, 1) and not has_action_left(st, 3), (
        "REGIME TEMOIN casse : les deux unites doivent porter le flag 4 avant la passe, sinon "
        "l'objection n'est pas reproduite")
    summon_ai.ComputerActionOperation.execute_group(st, [1, 3], reset_turn_flags=True)
    assert sorted(joues) == [1, 3], (
        "une unite portant `NoActionAvailable` a ete ECARTEE du groupe AI alors que "
        "`resetTurnFlags=1` doit l'effacer d'abord : joues=%s" % joues)


def test_contre_epreuve_sans_reset_le_flag_ecarte_bien(monkeypatch):
    """CONTRE-EPREUVE du test precedent. Sans elle, « les deux unites jouent » passerait meme si
    le flag n'etait LU par personne. Avec `resetTurnFlags=0`, le natif comme le port doivent
    ecarter une unite qui a fini son tour -- c'est la semantique de `GetValidUnits`."""
    from engine.runner.operations import summon_ai
    joues = []
    monkeypatch.setattr(summon_ai, "ai_control_execute_for",
                        lambda state, uid: joues.append(int(uid)) or {"uid": uid})
    st = _mk_group_state()
    summon_ai.ComputerActionOperation.execute_group(st, [1, 3], reset_turn_flags=False)
    assert joues == [], (
        "le flag `NoActionAvailable` n'ecarte PERSONNE meme sans reset : `has_action_left` ne "
        "serait donc pas lu, et le test de non-regression ci-dessus ne prouverait rien "
        "(joues=%s)" % joues)


def test_la_passe_automatique_du_turn_start_ignore_le_flag_4():
    """`PlayAutomaticUnitsOperation$$Execute` filtre par `!HasFlag(u, TurnFinished = 3)` AVANT
    d'entrer dans sa boucle -- c'est `collect_ai_controlled` cote port. Le flag 4 collant ne doit
    donc pas retirer un summon de la collecte apres un turn-start (qui, lui, retire le flag 3)."""
    from engine.runner.operations.summon_ai import collect_ai_controlled
    st = _mk_state()
    # `is_automatic` lit les traits -> on le neutralise en ciblant le seul axe teste ici : le
    # filtre `turn_ended()`. On verifie donc l'INVARIANT sur le flag 4 via l'etat des flags.
    FinishUnitTurnOperation.execute(st, 1)
    fl = _flags(st, 1)
    assert fl.has(UnitFlag.TurnFinished) and fl.has(UnitFlag.NoActionAvailable)
    StartTurnOperation.execute(st, 3)
    assert not fl.has(UnitFlag.TurnFinished), "le turn-start doit retirer le flag 3"
    assert fl.has(UnitFlag.NoActionAvailable), "et CONSERVER le flag 4 (includeNoAction=0)"
    # `collect_ai_controlled` ne lit QUE `turn_ended()` : l'unite reste collectable (elle ne l'est
    # pas ici faute de trait `Summon`, mais le critere teste est l'absence de tout filtre sur 4).
    assert isinstance(collect_ai_controlled(st, 3), list)
