"""#448-r1 -- gardes OFFLINE du port de `StormboyzStrike_FallbackAbility` / `_MissAbility`.

Ce que ce fichier verrouille, etage par etage (tout ce qui ne demande PAS de session) :

  O1  L'ARBRE du Fallback est celui du decompile, et le noeud selecteur est **PARTAGE** par
      `MoveUnit` et `AddEffect` -- c'est ce partage qui produit le quirk #425 (la tuile marquee
      n'est pas celle d'atterrissage). Un port qui construirait DEUX noeuds serait vert partout
      ailleurs et faux ici.
  O2  Le noeud `SortTilesByUtility` SE RE-EVALUE : le meme objet rend une tuile DIFFERENTE une fois
      que le caster occupe la premiere. C'est la mecanique du quirk, prouvee sans le natif.
  O3  Le canal d'OVERRIDE de bout en bout -- `OverrideMovementTargetOperation` pose,
      `MoveUnitOperation` relit, CONSOMME et RELANCE vers la nouvelle tuile.
  O4  CONTRE-BRAS : sans override, le mouvement va exactement ou on le lui demande (le canal ne
      doit pas devier « tout seul »), et le champ est remis a `None` dans les DEUX cas.
  O5  La RELANCE ne re-emet PAS les pre-move triggers (`skipPreMoveTriggers`) -- sans quoi un Miss
      re-firerait sur son propre reroutage, en boucle.
  O6  `Kill` tue, respecte ses trois gates natifs, et est IDEMPOTENT sur une unite deja morte.
  O7  `FullThrottle` (1134) est au registre du noeud `TriggerAbility` avec la chance du gameconfig.
  O8  Les TROIS classes du `TriggeredAbilityType` 1141 sont inscrites sous la meme cle de passif,
      sur les TROIS evenements distincts.

ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

from engine.entities.pathfinding.board import Board
from engine.runner.state import State
from engine.runner.events import EventBus
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      UnitComponent, UnitFlagsComponent)
from engine.runner.operations.movement import MoveUnitOperation, OverrideMovementTargetOperation

ALREADY_USED_TILE = 1179
TELEPORTING_IN = 1140
FULL_THROTTLE = 1134


def _grid(cols=4, rows=4):
    """Plateau plat `cols x rows`, toutes tuiles marchables, adjacence evenq (celle du moteur)."""
    tiles = []
    tid = 1
    for c in range(cols):
        for r in range(rows):
            tiles.append({"id": tid, "col": c, "row": r, "walkable": True, "elevation": 0,
                          "neighbours": []})
            tid += 1
    return Board(tiles, adjacency="evenq")


def _state(board, units):
    """`State` minimal : des unites positionnees sur `board`. `units` = [(id, (col,row), team)]."""
    st = State()
    st.board = board
    for uid, pos, team in units:
        e = st.add_entity(uid)
        e.add_component(UnitComponent(visual_id="u%d" % uid, alive=True))
        e.add_component(OwnerComponent(team=team, player=2 + team))
        e.add_component(HealthComponent(hp=100, hp_max=100))
        if pos is not None:
            e.add_component(PositionComponent(pos[0], pos[1]))
        e.add_component(UnitFlagsComponent())
    return st


# --------------------------------------------------------------------------- O1 / O2

def test_O1_l_arbre_du_fallback_partage_UN_SEUL_noeud_selecteur():
    """O1 -- `local_78` du decompile est passe A LA FOIS a `MoveUnitBehaviour` et a `AddEffect`.

    Le port doit partager le MEME objet Python, pas construire deux sous-arbres equivalents : c'est
    la seule facon que la RE-EVALUATION apres le move change la tuile (quirk #425). Deux noeuds
    jumeaux donneraient le meme resultat sur toute mesure ou la tuile ne bouge pas -- donc un vert
    trompeur."""
    from engine.runner.operations.triggers.loki.stormboyz_strike import (
        stormboyz_strike_fallback_tree)
    from engine.runner.abilities.behaviours import AddEffect, MoveUnit
    from engine.entities.behaviours import Seq, If

    tree = stormboyz_strike_fallback_tree()
    assert isinstance(tree, Seq) and isinstance(tree.left, Seq) and isinstance(tree.right, If)
    move, add = tree.left.left, tree.left.right
    assert isinstance(move, MoveUnit) and isinstance(add, AddEffect)
    assert add.effect_type == ALREADY_USED_TILE
    assert add.duration_turns == 1 and add.duration_rounds is None, (
        "la surcharge `turns: Nullable<int>(1)` range un `Direct(1)` tel quel -- une duree DEJA EN "
        "TOURS, pas un `TurnsFromRounds`")
    assert add.source_from_target is True, (
        "la surcharge sans selecteur `source` passe `0` -> `AddEffectBehaviour$$Execute` retombe "
        "sur la cible (`SourceUnitId == OwnerId`, mesure #425)")
    assert move.dest_tile_sel is add.target_sel, (
        "MoveUnit et AddEffect doivent partager le MEME objet-noeud (local_78) -- sinon le quirk "
        "#425 (tuile marquee != tuile d'atterrissage) est perdu SILENCIEUSEMENT")


def test_O2_le_noeud_SortTilesByUtility_se_RE_EVALUE():
    """O2 -- la mecanique du quirk, sans le natif : le MEME noeud rend une tuile DIFFERENTE une
    fois que la premiere est occupee, parce que `CanAddUnit` la retire du pool.

    On neutralise le classement (`sort_tiles_by_utility` = identite) pour isoler la seule variable
    qui compte ici : l'occupation."""
    from engine.entities.selectors import AllTiles, CanAddUnit, Caster, PickFirstN
    from engine.entities.selectors import SortTilesByUtility
    from engine.dsl.base import Const, DslContext
    from engine.utilities.utility_type import UtilityType

    board = _grid(2, 2)
    sel = PickFirstN(SortTilesByUtility(CanAddUnit(AllTiles()), Caster(),
                                        int(UtilityType.UnitMovement)), Const(1))
    # `_is_alive` = `alive and hp > 0` -- le `hp` n'est pas decoratif : sans lui l'unite est MORTE
    # pour le DSL et n'occupe donc rien (le contre-test aurait ete vert pour la mauvaise raison).
    caster = {"id": 1, "pos": None, "alive": True, "hp": 100}
    ctx = DslContext(units=[caster], caster=caster, owner=caster, actor=caster, board=board,
                     sort_tiles_by_utility=lambda tiles, uid, ut, pid=None: list(tiles))
    first = list(sel.evaluate(ctx))
    assert first, "pool vide : le scenario n'exerce rien"
    # le caster occupe desormais la tuile choisie -> `CanAddUnit` l'exclut a la RE-EVALUATION
    caster["pos"] = {"col": board.by_id[first[0]]["col"], "row": board.by_id[first[0]]["row"]}
    second = list(sel.evaluate(ctx))
    assert second and second[0] != first[0], (
        "le noeud n'est pas re-evalue (ou `CanAddUnit` ne voit pas l'occupant) : la tuile marquee "
        "serait celle d'atterrissage, ce que #425 a mesure FAUX")


# --------------------------------------------------------------------------- O3 / O4 / O5

def test_O3_l_override_devie_le_mouvement():
    """O3 -- la chaine complete : l'Operation pose le canal, `MoveUnitOperation` le relit APRES le
    vecteur pre-move, le CONSOMME, et RELANCE le mouvement vers la tuile deviee.

    On simule le trigger `PreUnitMove` en posant l'override juste avant l'appel -- exactement ce que
    `OverrideUnitMovementTargetBehaviour$$Execute` ferait depuis le vecteur."""
    board = _grid()
    st = _state(board, [(1, (0, 0), 1)])
    uc = st.get_entity(1).get_component(UnitComponent)

    class _Vec:
        """Faux vecteur pre-move : pose l'override, comme le ferait le Miss."""
        def __init__(self, to):
            self.to = to

        def __call__(self, state, unit_id, dest_tile=None):
            OverrideMovementTargetOperation.execute(state, unit_id, [self.to])
            return []

    import engine.runner.operations.triggers as T
    orig = T.pre_move_triggers
    T.pre_move_triggers = _Vec((2, 2))
    try:
        MoveUnitOperation(1, (1, 1)).execute(st, EventBus())
    finally:
        T.pre_move_triggers = orig
    pc = st.get_entity(1).get_component(PositionComponent)
    assert (pc.col, pc.row) == (2, 2), (
        "le mouvement n'a pas ete DEVIE : arrive en (%d,%d) au lieu de (2,2)" % (pc.col, pc.row))
    assert uc.movement_target_override is None, (
        "le canal n'a pas ete CONSOMME -- le natif remet le champ a zero avant de relancer")


def test_O4_sans_override_le_mouvement_va_ou_on_lui_demande():
    """O4 -- CONTRE-BRAS. Le canal ne devie rien tout seul, et il est remis a `None` aussi dans ce
    cas (le natif ecrit `comp.<+0xa8> = 0` inconditionnellement apres la relecture)."""
    board = _grid()
    st = _state(board, [(1, (0, 0), 1)])
    MoveUnitOperation(1, (1, 1)).execute(st, EventBus())
    pc = st.get_entity(1).get_component(PositionComponent)
    assert (pc.col, pc.row) == (1, 1)
    assert st.get_entity(1).get_component(UnitComponent).movement_target_override is None


def test_O5_la_relance_ne_re_emet_pas_les_pre_move_triggers():
    """O5 -- `options.skipPreMoveTriggers = true` sur la RELANCE (l'octet `+0x12`, pose juste avant
    l'appel recursif). Sans lui, un Miss se re-declencherait sur son propre reroutage : boucle."""
    board = _grid()
    st = _state(board, [(1, (0, 0), 1)])
    calls = []

    def _vec(state, unit_id, dest_tile=None):
        calls.append(tuple(dest_tile))
        if len(calls) == 1:                       # le trigger ne devie qu'au PREMIER passage
            OverrideMovementTargetOperation.execute(state, unit_id, [(2, 2)])
        return []

    import engine.runner.operations.triggers as T
    orig = T.pre_move_triggers
    T.pre_move_triggers = _vec
    try:
        MoveUnitOperation(1, (1, 1)).execute(st, EventBus())
    finally:
        T.pre_move_triggers = orig
    assert calls == [(1, 1)], (
        "le vecteur pre-move a ete emis %d fois (%s) -- la relance doit porter "
        "`skip_pre_move_triggers=True`" % (len(calls), calls))


def test_O5b_l_unite_TUEE_par_un_trigger_pre_move_ne_bouge_pas():
    """O5b -- le SECOND bras du gate natif `if (!ovr.HasValue || IsDead(unit)) { ... return }`.
    Ce n'est pas theorique : le Miss finit par `TriggerAbility(FullThrottle)` = `If(Maybe(chance),
    Kill(Caster))`. Un port qui ignorerait ce bras ferait bouger un cadavre."""
    board = _grid()
    st = _state(board, [(1, (0, 0), 1)])

    def _vec(state, unit_id, dest_tile=None):
        state.get_entity(unit_id).get_component(UnitComponent).alive = False
        return []

    import engine.runner.operations.triggers as T
    orig = T.pre_move_triggers
    T.pre_move_triggers = _vec
    try:
        MoveUnitOperation(1, (1, 1)).execute(st, EventBus())
    finally:
        T.pre_move_triggers = orig
    pc = st.get_entity(1).get_component(PositionComponent)
    assert (pc.col, pc.row) == (0, 0), "une unite tuee par un pre-move trigger a quand meme bouge"


def test_O3b_l_operation_refuse_ce_que_le_natif_refuse():
    """O3b -- les gates de `OverrideMovementTargetOperation$$Execute` : `!IsUnit(unit)` (cote port,
    absence de `UnitComponent`) et la liste de tuiles VIDE."""
    board = _grid()
    st = _state(board, [(1, (0, 0), 1)])
    st.add_entity(99)                                     # entite SANS UnitComponent = pas une unite
    assert OverrideMovementTargetOperation.execute(st, 99, [(1, 1)]) is None
    assert OverrideMovementTargetOperation.execute(st, 1, []) is None
    assert st.get_entity(1).get_component(UnitComponent).movement_target_override is None


# --------------------------------------------------------------------------- O6

def test_O6_Kill_tue_et_respecte_ses_gates():
    """O6 -- `KillUnitBehaviour$$Execute` : les trois `HasFlag` (`9 Fled`, `6 Dead` -> collapse
    `alive`, `0x1a Removed`) sont des CONTINUE, pas des exceptions. Et une unite deja morte n'est
    pas re-tuee (sans quoi les death-triggers double-firent)."""
    from engine.runner.abilities.behaviours import Kill, entities_from_state
    from engine.entities.selectors import Caster
    from engine.dsl.effects import ExecutionContext

    board = _grid()
    st = _state(board, [(1, (0, 0), 1), (2, (1, 1), 2), (3, (2, 2), 2)])
    st.get_entity(2).get_component(UnitFlagsComponent).add(UnitFlagsComponent.FLED)
    st.get_entity(3).get_component(UnitFlagsComponent).add(UnitFlagsComponent.REMOVED)

    ectx = ExecutionContext(state=st, rng=None)
    Kill(Caster(), Caster()).execute(entities_from_state(st, 1), ectx)
    assert st.get_entity(1).get_component(UnitComponent).alive is False
    assert st.get_entity(1).get_component(HealthComponent).hp == 0
    killed = [p for n, p in ectx.emitted if n == "Kill"]
    assert killed and killed[-1]["killed"] == [1]

    # re-jeu sur le cadavre : AUCUN kill supplementaire (gate `HasFlag(6 = Dead)`)
    ectx2 = ExecutionContext(state=st, rng=None)
    Kill(Caster(), Caster()).execute(entities_from_state(st, 1), ectx2)
    assert [p for n, p in ectx2.emitted if n == "Kill"][-1]["killed"] == []

    # gates `Fled` / `Removed`
    for uid in (2, 3):
        e3 = ExecutionContext(state=st, rng=None)
        Kill(Caster(), Caster()).execute(entities_from_state(st, uid), e3)
        assert [p for n, p in e3.emitted if n == "Kill"][-1]["killed"] == [], (
            "l'unite %d porte un flag qui INTERDIT le kill (Fled/Removed)" % uid)
        assert st.get_entity(uid).get_component(UnitComponent).alive is True


# --------------------------------------------------------------------------- O7 / O8

def test_O7_FullThrottle_est_au_registre_de_TriggerAbility():
    """O7 -- sans cette entree, le dernier terme du Miss (`TriggerAbility(Caster, 0x46e)`) rendrait
    `dispatched: False` : un gap VISIBLE, mais un gap. La chance vient du gameconfig, jamais d'un
    litteral en dur."""
    import gameconfig as GC
    from engine.runner.abilities.behaviours import TRIGGERED_ABILITY_BEHAVIOURS
    import engine.runner.operations.triggers.dispatch.registry  # noqa: F401 (inscription import-time)

    assert FULL_THROTTLE in TRIGGERED_ABILITY_BEHAVIOURS
    consts = (GC.ability("FullThrottle") or {}).get("constants") or {}
    assert int(consts.get("chance")) == 30, (
        "`GetNumberConstant(0x2a = chance)` de FullThrottle a change : %s" % (consts,))
    assert int(consts.get("movement")) == 3, (
        "`GetNumberConstant(0x51 = movement)` -- la constante du gate NON PORTE (residu nomme)")


def test_O7b_FullThrottle_tue_a_100_pourcent_et_jamais_a_0():
    """O7b -- les DEUX bras du `If(Maybe(chance), Kill(Caster), null)`, en forcant le tirage.
    Le bras `chance = 0` est le contre-bras qui prouve que le `Maybe` gate REELLEMENT le kill."""
    from engine.runner.operations.triggers.loki.full_throttle import full_throttle_tree
    from engine.runner.abilities.behaviours import entities_from_state
    from engine.dsl.effects import ExecutionContext

    class _RNG:
        def __init__(self, verdict):
            self.verdict = verdict
            self.calls = 0

        def next_bool(self, chance):
            self.calls += 1
            return self.verdict

    board = _grid()
    for verdict, expected in ((True, False), (False, True)):
        st = _state(board, [(1, (0, 0), 1)])
        rng = _RNG(verdict)
        ectx = ExecutionContext(state=st, rng=rng)
        full_throttle_tree(30, rng).execute(entities_from_state(st, 1), ectx)
        assert rng.calls == 1, "le `Maybe` doit consommer EXACTEMENT un tirage (%d)" % rng.calls
        assert st.get_entity(1).get_component(UnitComponent).alive is expected


def test_O7c_TriggerAbility_n_execute_QUE_sur_une_cible_QUI_PORTE_l_ability():
    """O7c -- le gate `GetAbilityState` d'`IdunBattle.Operations.TriggerTriggeredAbilityOperation$$
    TriggerAbility`, TROUVE EN MESURANT (#448-r1).

    Le natif ne declenche l'ability que si la cible la PORTE (`ignoreUnitHavingAbility = false` aux
    deux call-sites portes) ; sinon, **aucun tirage**. Le port ne le gatait pas : sur le montage
    greffe du kit Stormboyz -- ou la greffe REMPLACE `passiveAbilities` et ou le porteur n'a donc
    PAS `FullThrottle` -- il consommait un `Maybe(chance = 30)` de trop. Ecart INVISIBLE sur tout
    observable d'etat (position, marque, PV identiques), visible UNIQUEMENT sur le flux PRNG : natif
    2 `genrand_int32`, port 3 -- et ce decalage vaut pour tout le reste de la bataille.

    Les deux bras sont ici : PORTEUR -> execute ; NON PORTEUR -> zero tirage, cible listee dans
    `notCarrying`."""
    from engine.runner.abilities.behaviours import TriggerAbility, entities_from_state
    from engine.runner.components import StatsComponent
    from engine.entities.selectors import Caster
    from engine.dsl.effects import ExecutionContext

    class _Ctx:
        def __init__(self, ids):
            self.triggered_abilities = list(ids)     # image de l'`AbilitiesComponent`
            self.visual_id = None
            self.traits = []
            self.passive_abilities = []

    class _RNG:
        def __init__(self):
            self.calls = 0

        def next_bool(self, chance):
            self.calls += 1
            return True                      # le pire cas : si l'ability part, elle TUE

    board = _grid()
    for ids, doit_partir in (([FULL_THROTTLE], True), ([], False)):
        st = _state(board, [(1, (0, 0), 1)])
        st.get_entity(1).add_component(StatsComponent(ctx=_Ctx(ids)))
        rng = _RNG()
        st.rng = rng            # `execute_full_throttle` prend le PRNG sur le `State`, comme le natif
        ectx = ExecutionContext(state=st, rng=rng)
        TriggerAbility(Caster(), FULL_THROTTLE).execute(entities_from_state(st, 1), ectx)
        emitted = [p for n, p in ectx.emitted if n == "TriggerAbility"][-1]
        assert emitted["targets"] == [1], (
            "le gate porte sur l'EXECUTION, pas sur la resolution du selecteur -- `targets` doit "
            "rester la liste resolue par `TriggerAbilityBehaviour$$Execute`")
        assert emitted["notCarrying"] == ([] if doit_partir else [1])
        assert rng.calls == (1 if doit_partir else 0), (
            "porte=%s : %d tirage(s) consomme(s), attendu %d"
            % (doit_partir, rng.calls, 1 if doit_partir else 0))
        assert st.get_entity(1).get_component(UnitComponent).alive is not doit_partir


def test_O8_les_TROIS_classes_de_1141_sont_inscrites():
    """O8 -- le builder natif `AbilitiesDatabase.u003Cu003Ec$$u003CInitializeTriggeredAbilities
    u003Eb__28_134` construit une `List` de TROIS instances pour l'unique entree `0x475` : le
    passif les monte toutes. Le registre du port doit les porter toutes les trois, sur leurs TROIS
    evenements distincts."""
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
    from engine.dsl.event_trigger_type import EventTriggerType

    classes = ABILITY_TRIGGERS.get("StormboyzStrike") or []
    assert len(classes) == 3, [c.__name__ for c in classes]
    assert {c.event_id for c in classes} == {int(EventTriggerType.AbilityInit),        # 0x21
                                             int(EventTriggerType.UnitFinishedTurn),   # 0x28
                                             int(EventTriggerType.PreUnitMove)}        # 0x1f
    assert all(c.TRIGGERED_ABILITY_ID == 1141 for c in classes), (
        "les trois partagent le MEME `TriggeredAbilityType` (1141) -- il n'y en a qu'UN dans l'enum")


def test_O9_le_miss_bati_sans_destination_ne_leve_pas():
    """O9 -- `<Sel+0x78>` VIDE. Le natif resoudrait un selecteur vide -> `Count > 0` FAUX -> pas de
    deviation, mais les TROIS autres termes de l'arbre s'executent quand meme. Le port ne doit ni
    lever ni sortir en no-op silencieux."""
    from engine.runner.operations.triggers.loki.stormboyz_strike import stormboyz_strike_miss_tree
    from engine.runner.abilities.behaviours import entities_from_state
    from engine.dsl.effects import ExecutionContext

    class _RNG:
        def next_bool(self, chance):
            return True                       # le pire cas : le `Maybe` PASSE, il n'y a rien a devier

    board = _grid()
    st = _state(board, [(1, (0, 0), 1)])
    ectx = ExecutionContext(state=st, rng=_RNG())
    stormboyz_strike_miss_tree(None, 20, _RNG()).execute(entities_from_state(st, 1), ectx)
    ovr = [p for n, p in ectx.emitted if n == "OverrideUnitMovementTarget"]
    assert ovr and ovr[-1]["applied"] is False and ovr[-1]["reason"] == "no-tile"
    assert st.get_entity(1).get_component(UnitComponent).movement_target_override is None
    assert [n for n, _ in ectx.emitted if n == "TriggerAbility"], (
        "le `TriggerAbility(FullThrottle)` est HORS du `If` : il doit partir dans tous les cas")
