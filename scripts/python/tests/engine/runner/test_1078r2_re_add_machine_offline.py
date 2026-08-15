"""#1078-r2 -- l'etage `ReAddMachine` et les DEUX classes natives de `1497 HunterOfSouls`.

GARDE OFFLINE, six etages. Chacun a ete VU ROUGE par mutation avant d'etre livre :

  1. `test_..._operation_gates`        -- les TROIS refus natifs, dans leur ordre ;
  2. `test_..._reset_flags_litteraux`  -- `RemoveTurnFlags(includeNoAction = 1, newActivation = 0)` :
                                          les deux litteraux ne sont PAS interchangeables ;
  3. `test_..._resetflags_est_un_predicat` -- le 2e argument DIFFERE entre les deux classes ;
  4. `test_..._un_seul_id_deux_classes`    -- 1497 est l'id des DEUX (mesure sur le build) ;
  5. `test_..._registre_et_vecteurs`   -- inscription + vecteurs DISTINCTS ;
  6. `test_..._ordinaux`               -- les ordinaux ECRITS aux sites.

⚠ Ce que ce fichier NE garde PAS : le tour joue par `PerformAIAttack` (il depend du walk IA, pas
de ce module) ni la magnitude de l'effet `1495` (hors tranche, residu nomme dans le module).
"""
from __future__ import annotations

import os

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/engine/runner/operations/re_add_machine.py",
        "scripts/python/engine/runner/abilities/behaviours/lifecycle.py",
        "scripts/python/engine/runner/operations/triggers/loki/hunter_of_souls.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/runner/components.py",
    ),
    "build": True,            # les enums (UnitFlag, EventTriggerType, TriggeredAbilityType) sont per-build
    "toujours": False,
    "raison": ("garde l'Operation `ReAddMachine` (gates, rattachement, litteraux de "
               "`RemoveTurnFlags`), le fait que son 2e argument est un PREDICAT et non un booleen, "
               "et le port des DEUX classes natives du triggered 1497"),
}

import pytest                                                                    # noqa: E402

from engine.dsl.effects import ExecutionContext                                  # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                       # noqa: E402
from engine.entities.effect_type import EffectType                               # noqa: E402
from engine.entities.selectors.accessors import Owner                            # noqa: E402
from engine.entities.selectors.tiles import Parent                               # noqa: E402
from engine.entities.triggers import HasUnitFlag, Not, YesTrigger                # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType          # noqa: E402
from engine.entities.unit_flag import UnitFlag                                   # noqa: E402
from engine.runner.abilities.behaviours.context import entities_from_state       # noqa: E402
from engine.runner.abilities.behaviours.lifecycle import ReAddMachine            # noqa: E402
from engine.runner.components import (HealthComponent, MachineComponent,         # noqa: E402
                                      OwnerComponent, PositionComponent,
                                      UnitComponent, UnitFlagsComponent)
from engine.runner.operations.re_add_machine import ReAddMachineOperation        # noqa: E402
from engine.runner.operations.triggers.loki import hunter_of_souls as HOS        # noqa: E402
from engine.runner.state import State                                            # noqa: E402

_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))                       # .../scripts/python

MOW_ID, SUMMON_ID, FOE_ID = 1, 2, 3


def _state(mow_removed: bool = True, mow_flags=(), summon_alive: bool = True) -> State:
    """Une MoW RETIREE (l'etat que laisse `RemoveMachine`) et son summon."""
    st = State()
    m = st.add_entity(MOW_ID)
    m.add_component(UnitComponent(visual_id="ultraDreadnought", alive=True))
    m.add_component(OwnerComponent(team=1, player=1))
    m.add_component(MachineComponent(slot=MachineComponent.SLOT_BOTTOM, removed=mow_removed))
    fl = UnitFlagsComponent()
    for f in mow_flags:
        fl.flags.add(int(f))
    m.add_component(fl)
    s = st.add_entity(SUMMON_ID)
    s.add_component(UnitComponent(visual_id="thousSmnDaemonPrince", alive=summon_alive,
                                  parent_id=MOW_ID))
    s.add_component(OwnerComponent(team=1, player=1))
    s.add_component(PositionComponent(col=2, row=2))
    s.add_component(HealthComponent(hp=0 if not summon_alive else 500, hp_max=500))
    s.add_component(UnitFlagsComponent())
    f = st.add_entity(FOE_ID)
    f.add_component(UnitComponent(visual_id="foe", alive=True))
    f.add_component(OwnerComponent(team=2, player=2))
    f.add_component(PositionComponent(col=5, row=5))
    f.add_component(HealthComponent(hp=500, hp_max=500))
    return st


# ---------------------------- [1] LES TROIS GATES DE L'OPERATION ------------------------------
def test_1078r2_operation_gate_entite_absente():
    """1. `machine == 0` -> log d'erreur, RETURN (aucune mutation)."""
    st = _state()
    assert ReAddMachineOperation.execute(st, 999) is None
    assert ReAddMachineOperation.execute(st, None) is None


def test_1078r2_operation_gate_non_machine():
    """2. `EntityExtensions$$IsMachine` -- une UNITE n'est pas une Machine. Sans ce gate, le port
    rattacherait n'importe quoi (le summon lui-meme, par exemple)."""
    st = _state()
    assert ReAddMachineOperation.execute(st, SUMMON_ID) is None


def test_1078r2_operation_gate_deja_rattachee():
    """3. Le pool 6 contient DEJA la machine -> le natif log un AVERTISSEMENT et sort SANS MUTER.
    C'est ce qui rend un double `ReAddMachine` idempotent."""
    st = _state(mow_removed=False)
    assert ReAddMachineOperation.execute(st, MOW_ID) is None
    # et le second appel apres un rattachement reussi est lui aussi un no-op
    st2 = _state(mow_removed=True)
    assert ReAddMachineOperation.execute(st2, MOW_ID) is not None
    assert ReAddMachineOperation.execute(st2, MOW_ID) is None


def test_1078r2_le_rattachement_lui_meme():
    """`MachineComponent.removed = False` -- le SYMETRIQUE exact de `RemoveMachine` (#91)."""
    st = _state(mow_removed=True)
    mc = st.get_entity(MOW_ID).get_component(MachineComponent)
    assert mc.removed is True
    res = ReAddMachineOperation.execute(st, MOW_ID)
    assert res is not None and res["machine"] == MOW_ID
    assert mc.removed is False


def test_1078r2_ne_restaure_aucun_effet():
    """LECTURE : le retrait CONSOMME les effets (`RemoveMachineOperation$$RemoveEffects`), le
    rattachement n'en restaure AUCUN. Un port qui les ressusciterait inventerait."""
    from engine.entities.effects_state import EffectsState
    st = _state(mow_removed=True)
    st.effects = EffectsState()
    from engine.runner.operations.effects import AddEffectOperation
    eff = AddEffectOperation.execute(st, source=MOW_ID, target=MOW_ID,
                                     effect_type=int(EffectType.Fire), name="Fire")
    assert eff is not None
    eff.consumed = True                                  # etat laisse par `RemoveMachine`
    ReAddMachineOperation.execute(st, MOW_ID)
    assert eff.consumed is True, "le rattachement ne doit PAS ressusciter les effets consommes"


# ------------------- [2] LES DEUX LITTERAUX DE `RemoveTurnFlags`, LUS -------------------------
def test_1078r2_reset_flags_litteraux_ne_sont_pas_interchangeables():
    """`RemoveTurnFlags(&ret, comp, 1, 0)` : `includeNoAction = 1`, `newActivation = 0`.

    LE VICE QUE CE TEST GARDE : `new_activation` retirerait `Moved`/`Teleported`/
    `ArrivedAtFinalTile`. Ce site ne le fait PAS -- une MoW qui revient garde donc son etat de
    deplacement, et seuls les flags d'ACTION sont rouverts."""
    poses = (UnitFlag.Moved, UnitFlag.Teleported, UnitFlag.ArrivedAtFinalTile,
             UnitFlag.NoActionAvailable, UnitFlag.ActiveAbilityUsed, UnitFlag.TurnFinished)
    st = _state(mow_removed=True, mow_flags=poses)
    res = ReAddMachineOperation.execute(st, MOW_ID, reset_flags=True)
    assert res is not None
    cleared = set(res["flags_cleared"])
    # `includeNoAction = 1` + le bloc INCONDITIONNEL
    assert int(UnitFlag.NoActionAvailable) in cleared
    assert int(UnitFlag.ActiveAbilityUsed) in cleared
    assert int(UnitFlag.TurnFinished) in cleared
    # `newActivation = 0` -- ces trois-la RESTENT
    fl = st.get_entity(MOW_ID).get_component(UnitFlagsComponent)
    for f in (UnitFlag.Moved, UnitFlag.Teleported, UnitFlag.ArrivedAtFinalTile):
        assert int(f) not in cleared, "newActivation = 0 : %s ne doit PAS etre retire" % f.name
        assert int(f) in fl.flags


def test_1078r2_reset_flags_faux_ne_touche_rien():
    """`resetFlags` FAUX : le natif saute entierement le `RemoveTurnFlags`."""
    poses = (UnitFlag.NoActionAvailable, UnitFlag.TurnFinished)
    st = _state(mow_removed=True, mow_flags=poses)
    res = ReAddMachineOperation.execute(st, MOW_ID, reset_flags=False)
    assert res is not None and res["flags_cleared"] == []
    fl = st.get_entity(MOW_ID).get_component(UnitFlagsComponent)
    assert {int(f) for f in poses} <= fl.flags


# ------------- [3] LE 2e ARGUMENT EST UN **PREDICAT**, ET IL DIFFERE ENTRE LES CLASSES ---------
@pytest.mark.parametrize("turn_finished,attendu", [
    (False, True),      # `NOT HasFlag(Owner, TurnFinished)` -> VRAI  -> les flags sont rouverts
    (True, False),      # le Prince avait deja fini son tour         -> ils ne le sont PAS
])
def test_1078r2_resetflags_est_un_predicat_evalue_a_l_execution(turn_finished, attendu):
    """LE VICE QUE CE TEST GARDE : figer `resetFlags` en `bool` a la construction. Le volet TUE
    passe `NOT HasFlag(Owner@+0x30, 0x3 = TurnFinished)` -- un predicat dont le verdict depend de
    l'ETAT du porteur au moment du declenchement, pas de l'arbre."""
    st = _state(mow_removed=True, mow_flags=(UnitFlag.NoActionAvailable,))
    if turn_finished:
        st.get_entity(SUMMON_ID).get_component(UnitFlagsComponent).flags.add(
            int(UnitFlag.TurnFinished))
    ectx = ExecutionContext(state=st, rng=st.rng)
    ReAddMachine(Parent(Owner()),
                 Not(HasUnitFlag(Owner(), int(UnitFlag.TurnFinished)))).execute(
        entities_from_state(st, SUMMON_ID, SUMMON_ID), ectx)
    emis = [p for n, p in ectx.emitted if n == "ReAddMachine"]
    assert len(emis) == 1 and emis[0]["machine"] == MOW_ID
    assert emis[0]["reset_flags"] is attendu


def test_1078r2_le_volet_tour_passe_le_yestrigger_constant():
    """`<DSLTriggers+0x70>` = `YesTrigger` : sur le volet TOUR, le rattachement remet TOUJOURS les
    flags a zero -- meme si le Prince avait le flag `TurnFinished`."""
    st = _state(mow_removed=True, mow_flags=(UnitFlag.TurnFinished,))
    st.get_entity(SUMMON_ID).get_component(UnitFlagsComponent).flags.add(
        int(UnitFlag.TurnFinished))
    ectx = ExecutionContext(state=st, rng=st.rng)
    ReAddMachine(Parent(Owner()), YesTrigger()).execute(
        entities_from_state(st, SUMMON_ID, SUMMON_ID), ectx)
    emis = [p for n, p in ectx.emitted if n == "ReAddMachine"]
    assert len(emis) == 1 and emis[0]["reset_flags"] is True
    assert YesTrigger().should_trigger(None) is True         # constante VRAIE, sans contexte


def test_1078r2_selectsingle_pas_select():
    """`SelectSingle` (slot 9) et non `Select` : le natif vise UNE machine. Un parent absent ->
    aucun appel a l'Operation, resultat VIDE."""
    st = _state(mow_removed=True)
    st.get_entity(SUMMON_ID).get_component(UnitComponent).parent_id = None
    ectx = ExecutionContext(state=st, rng=st.rng)
    ReAddMachine(Parent(Owner()), YesTrigger()).execute(
        entities_from_state(st, SUMMON_ID, SUMMON_ID), ectx)
    assert [p for n, p in ectx.emitted if n == "ReAddMachine"] == []
    assert st.get_entity(MOW_ID).get_component(MachineComponent).removed is True


# --------------- [4] UN SEUL id, DEUX CLASSES -- ET C'EST MESURE, PAS SUPPOSE -----------------
def test_1078r2_un_seul_id_pour_les_deux_classes():
    """`TriggeredAbilityType` du build ne porte QU'UN membre `HunterOfSouls` : les deux classes
    natives partagent donc l'id 1497. Le gameconfig concorde."""
    import gameconfig as GC
    noms = [m.name for m in TriggeredAbilityType if "HunterOfSouls" in m.name]
    assert noms == ["HunterOfSouls"], "un membre `HunterOfSouls_Killed` changerait la lecture"
    assert int(TriggeredAbilityType.HunterOfSouls) == 1497
    assert GC.ability("HunterOfSouls") not in (None, {})
    assert GC.ability("HunterOfSouls_Killed") in (None, {})
    assert HOS.HunterOfSoulsAbility.TRIGGERED_ABILITY_ID == 1497
    assert HOS.HunterOfSoulsKilledAbility.TRIGGERED_ABILITY_ID == 1497


# --------------------------- [5] LE REGISTRE ET LES DEUX VECTEURS -----------------------------
def test_1078r2_registre_et_vecteurs_distincts():
    """Les DEUX classes sont au registre sous la MEME cle, sur des vecteurs DISTINCTS -- si elles
    ecoutaient le meme event, l'une des deux serait morte."""
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS as A
    classes = A.get("HunterOfSouls") or []
    assert [c.__name__ for c in classes] == ["HunterOfSoulsAbility", "HunterOfSoulsKilledAbility"]
    assert {int(c.event_id) for c in classes} == {int(EventTriggerType.TurnStart_Actions),
                                                  int(EventTriggerType.UnitDefeated)}
    # `On(0x36, ownerNeedsToBeAlive = 0)` : le porteur EST le vaincu -- sans ce cran le trigger ne
    # firerait JAMAIS.
    assert HOS.HunterOfSoulsKilledAbility.fire_on_death is True


def test_1078r2_le_volet_tour_exige_le_tour_du_porteur():
    """`<DSLTriggers+0x28>` = `IsTurnOf(Owner@+0x30)`.

    LE VICE QUE CE TEST GARDE : re-collapser `IsTurnOf` a la main dans `matches` (un SECOND port du
    meme noeud natif). Le noeud lit `ctx.current_player_id` -- la garde de tete du natif
    (`ctx@+0x50 == null -> false`) -- et **PAS** le `player_id` de l'evenement. Les deux valeurs
    sont donc posees SEPAREMENT ici, et volontairement DISCORDANTES : un port qui lirait
    `ev.player_id` passerait le 3e cas et echouerait sur le 4e."""
    from engine.runner.operations.triggers.base import TriggerEvent
    st = _state()
    ab = HOS.HunterOfSoulsAbility(SUMMON_ID)

    def _ev(player):
        return TriggerEvent(int(EventTriggerType.TurnStart_Actions), -1, -1,
                            ranged=False, profile=None, player_id=player)
    st.current_player_id = None
    assert ab.matches(st, _ev(1)) is False, "`ctx@+0x50 == null -> return false`"
    st.current_player_id = 2                       # tour de l'ADVERSAIRE
    assert ab.matches(st, _ev(1)) is False
    st.current_player_id = 1                       # tour du porteur
    assert ab.matches(st, _ev(None)) is True, \
        "le noeud lit `current_player_id`, pas `ev.player_id` (sinon : SECOND port du noeud)"
    st.current_player_id = 2                       # discordant avec `ev.player_id = 1`
    assert ab.matches(st, _ev(1)) is False, \
        "un collapse par `ev.player_id` passerait ici -- c'est le fork que ce cas interdit"
    st.current_player_id = 1
    st.get_entity(SUMMON_ID).get_component(UnitComponent).alive = False
    assert ab.matches(st, _ev(1)) is False, "`ownerNeedsToBeAlive = 1`"


def test_1078r2_le_volet_tue_exige_owner_is_target():
    """`get_OwnerIsTarget` : le VAINCU doit etre le porteur."""
    from engine.runner.operations.triggers.base import TriggerEvent
    st = _state(summon_alive=False)
    ab = HOS.HunterOfSoulsKilledAbility(SUMMON_ID)
    assert ab.matches(st, TriggerEvent(int(EventTriggerType.UnitDefeated), FOE_ID, SUMMON_ID,
                                       ranged=False, profile=None)) is True
    assert ab.matches(st, TriggerEvent(int(EventTriggerType.UnitDefeated), FOE_ID, FOE_ID,
                                       ranged=False, profile=None)) is False


@pytest.mark.parametrize("turn_finished,reset_attendu", [
    (False, True),      # le Prince n'avait PAS fini son tour -> la MoW repart les flags rouverts
    (True, False),      # il avait fini                        -> elle repart SANS les rouvrir
])
def test_1078r2_le_volet_tue_bout_en_bout(turn_finished, reset_attendu):
    """L'arbre complet : `AddFlag(PreventResurrect) + ReAddMachine(Parent, NOT TurnFinished)`.

    LE VICE QUE LES DEUX PARAMETRES GARDENT : substituer `YesTrigger` au predicat. Le cas
    `turn_finished = False` passe des DEUX cotes (le predicat rend VRAI, comme la constante) --
    c'est le second qui discrimine, et sans lui la mutation reste VERTE (mesure du 2026-08-15 :
    8 mutations sur 9 detectees, celle-ci passait)."""
    from engine.runner.operations.triggers.base import TriggerEvent
    st = _state(mow_removed=True, mow_flags=(UnitFlag.NoActionAvailable,), summon_alive=False)
    if turn_finished:
        st.get_entity(SUMMON_ID).get_component(UnitFlagsComponent).flags.add(
            int(UnitFlag.TurnFinished))
    out = HOS.HunterOfSoulsKilledAbility(SUMMON_ID).execute_behaviour(
        st, TriggerEvent(int(EventTriggerType.UnitDefeated), FOE_ID, SUMMON_ID,
                         ranged=False, profile=None))
    assert out is not None
    assert out["prevent_resurrect"] is True
    assert out["machine"] == [MOW_ID] and out["reset_flags"] == [reset_attendu]
    assert int(UnitFlag.PreventResurrect) in \
        st.get_entity(SUMMON_ID).get_component(UnitFlagsComponent).flags
    # le RATTACHEMENT a lieu dans les DEUX cas -- seul le reset des flags est conditionne.
    assert st.get_entity(MOW_ID).get_component(MachineComponent).removed is False
    fl = st.get_entity(MOW_ID).get_component(UnitFlagsComponent)
    assert (int(UnitFlag.NoActionAvailable) in fl.flags) is (not reset_attendu)


# ------------------------------------ [6] LES ORDINAUX ----------------------------------------
@pytest.mark.parametrize("membre,attendu,ou", [
    (int(TriggeredAbilityType.HunterOfSouls), 1497, "l'unique membre `HunterOfSouls` du build"),
    (int(EffectType.HunterOfSouls_ExtraDamage), 1495, "`DSLBehaviors$$AddEffect(this, 0x5d7, ...)`"),
    (int(UnitFlag.PreventResurrect), 22, "`DSLBehaviors$$AddFlag(this, Owner, 0x16)`"),
    (int(UnitFlag.TurnFinished), 3, "`DSLTriggers$$HasFlag(this, Owner, 0x3)`"),
    (int(EventTriggerType.TurnStart_Actions), 22, "`DSLTriggers$$On(this, 0x16, 1)`"),
    (int(EventTriggerType.UnitDefeated), 54, "`DSLTriggers$$On(this, 0x36, 0)`"),
])
def test_1078r2_ordinaux_ecrits_au_site(membre, attendu, ou):
    """Fige l'ordinal MESURE a la conversion. ⚠ `22` designe DEUX choses distinctes dans ce module
    (`UnitFlag.PreventResurrect` et `EventTriggerType.TurnStart_Actions`) : l'ordinal nu y serait
    ambigu, le NOM ne l'est pas."""
    assert membre == attendu, "ordinal glisse -- lu au site %s" % (ou,)
