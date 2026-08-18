"""GARDE OFFLINE #448-r1-r1-r2-r1 -- le vecteur after-move est joue PAR L'OPERATION.

CE QUE LE DECOMPILE DIT (relu sur `rnca9r7q6c`).
`IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers` a **DEUX** xrefs CODE dans tout
le binaire, toutes deux dans `IdunBattle.Operations.MoveUnitOperation$$Execute` : la branche
« position VIDE + `allowNullTargetPosition` » (qui le joue avec `movementSteps = 0` juste apres
avoir retire l'unite de ses tuiles) et la branche REELLE (entre les deux
`RefreshEffects({trigger = 7, effectEntity = null})`). Le vecteur appartient donc a l'Operation, pas
a son appelant -- et c'est ce qui le fait EMERGER pour toute feuille DSL de mouvement au lieu de
l'enumerer a la main (frontiere #149 : au-dessus du `.Execute` d'une feuille = declaratif, en
dessous = imperatif ; un vecteur joue par l'Operation est du BON cote).

Le corps, remis en C# :

    publish On(0x24 = UnitPositionChanged_1);
    if (isInterimStep) return;                          // 6e argument = `MoveUnitOptions+0x14`
    publish On(4    = UnitAfterMove);                   // OVERWATCH
    publish On(0x1d = UnitPositionChanged_2);

et, DANS `Execute` et autour de cet appel :

    if (options+0x10 == 0) newlyAdded = UnitFlagsComponent.Add(UnitFlag.ArrivedAtFinalTile = 1);
    ... EvaluateAfterMoveTriggers(..., isInterimStep = options+0x14, ...) ...
    if (newlyAdded) publish On(0x1c = ArrivedAtFinalTile);

`IdunBattle.Entities.Behaviours.MoveUnitBehaviour$$Execute` empaquette les SIX selecteurs de
`MoveUnitBehaviourOptions` (`+0x10..+0x38`, ranges par le ctor aux champs `MoveUnitBehaviour+0x70..
+0x98`) dans `MoveUnitOptions+0x10..+0x16`, et INVERSE les deux premiers ENSEMBLE
(`CONCAT11(sel@+0x18, sel@+0x10) ^ 0x101`). Leurs defauts DIFFERENT (`+0x10` -> VRAI, `+0x18` ->
FAUX), donc apres inversion une feuille DSL a selecteurs nuls donne
`options+0x10 = 1` (**pas** de `ArrivedAtFinalTile`) et `options+0x11 = 0` (`SetMovedFlag` POSE).
C'est ce couple asymetrique qui rend la lecture non-devinable.

LA FACE INVERSE, LUE elle aussi. Le push, le pull, le switch et le revive n'entrent JAMAIS dans
`MoveUnitOperation$$Execute` : `IdunBattle.Operations.DisplaceUnitOperation$$Execute`,
`$$SwitchPosition` et `IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition` prennent le
slot `SetUnitPosition` de l'`IOperationProcessor` (3 arguments : unit, position, un OCTET qui gate
`ResetPreviousTile`), la ou `MoveUnitBehaviour$$Execute` et la lambda de
`Visit(CheatMoveUnitMessage)` prennent le slot `MoveUnit` (4 arguments : unit, position,
triggeringAbilityOrEffect, options). `IdunBattle.Operations.SetUnitPositionOperation$$Execute`
n'emet AUCUN event. `IdunBattle.Operations.FleeOperation$$Execute`, lui, n'appelle NI l'un NI
l'autre.

Detail : `docs/rl/case-448-r1-r1-r2-r1-vecteur-after-move-dsl.md`. ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from engine.runner.components import (OwnerComponent, PositionComponent,      # noqa: E402
                                      UnitComponent, UnitFlagsComponent)
from engine.runner.events import EventBus                                     # noqa: E402
from engine.runner.state import State                                         # noqa: E402
from engine.runner.operations import movement as MV                           # noqa: E402
from engine.runner.operations.triggers.dispatch import move_death as MD       # noqa: E402


# ---------------------------------------------------------------------------- montage minimal
def _state(units=((1, (1, 1), 0), (2, (4, 4), 1))):
    """`units` = [(id, (col,row), team)]. Board VOLONTAIREMENT absent : les sous-vecteurs sont
    substitues (on garde ICI la SEQUENCE et le CABLAGE, pas le pathfinding -- c'est le test live
    qui confronte la geometrie)."""
    st = State()
    for uid, pos, team in units:
        e = st.add_entity(uid)
        e.add_component(PositionComponent(pos[0], pos[1]))
        e.add_component(UnitComponent("u%d" % uid, True))
        e.add_component(OwnerComponent(team))
    return st


@pytest.fixture()
def seq(monkeypatch):
    """Substitue les DEUX foyers d'emission de `after_move_triggers` et rend la SEQUENCE d'events.

    `evaluate_trigger_operation` est le foyer des quatre events dispatches (`On(0x24)`, `On(4)`,
    `On(0x1d)`, `On(0x1c)`) ; `light_cover_on_enter` est la tile-ability hors registre."""
    events: list = []

    def fake_eval(state, ev):
        events.append((int(ev.event_id), ev.movement_steps))
        return [{"ev": int(ev.event_id)}]

    monkeypatch.setattr(MD, "evaluate_trigger_operation", fake_eval)
    from engine.runner.operations.triggers import tiles as TILES
    monkeypatch.setattr(TILES, "light_cover_on_enter", lambda state, uid: [])
    return events


# =============================================================== 1. la SEQUENCE et ses deux gates
@pytest.mark.parametrize("interim,arrive,expected", [
    (False, True,  [0x24, 4, 0x1d, 0x1c]),   # mouvement JOUEUR (options entierement nulles)
    (False, False, [0x24, 4, 0x1d]),         # feuille DSL (`options+0x10` = 1 par inversion)
    (True,  True,  [0x24]),                  # pas INTERMEDIAIRE : la coupure du natif
    (True,  False, [0x24]),                  # idem -- `On(0x1c)` est en aval de la coupure
])
def test_gates_du_vecteur(seq, interim, arrive, expected):
    """`if (isInterimStep) return;` coupe APRES `On(0x24)` ; `options+0x10` coupe `On(0x1c)`.

    Les quatre combinaisons sont balayees : un port qui brancherait « tout ou rien » passerait les
    deux lignes extremes et TOMBERAIT sur les deux du milieu."""
    st = _state()
    MD.after_move_triggers(st, 1, movement_steps=5,
                           is_interim_step=interim, arrive_at_final_tile=arrive)
    assert [e for e, _ in seq] == expected


def test_movement_steps_propage_aux_trois_events(seq):
    """Le natif batit UN SEUL `AbilityEntities` pour les trois events -> `movementSteps` est porte
    par les trois, pas seulement par `On(0x24)` (le seul consommateur porte le lit sur `On(0x24)`,
    mais un port qui ne le threaderait qu'a lui creerait un ecart invisible)."""
    st = _state()
    MD.after_move_triggers(st, 1, movement_steps=7)
    assert [s for e, s in seq if e in (0x24, 4, 0x1d)] == [7, 7, 7]


def test_arrived_at_final_tile_pose_le_flag_seulement_si_ouvert(seq):
    """`Add(UnitFlag.ArrivedAtFinalTile)` est DANS le meme gate que `On(0x1c)` : quand la feuille
    DSL ferme le gate, le flag ne doit pas etre pose non plus (sinon le `On(0x1c)` d'un
    `FinishUnitTurnOperation` ulterieur serait AVALE par un flag qui n'aurait jamais du exister)."""
    st = _state()
    MD.after_move_triggers(st, 1, arrive_at_final_tile=False)
    fl = st.get_entity(1).get_component(UnitFlagsComponent)
    assert fl is None or not fl.has(UnitFlagsComponent.ARRIVED_AT_FINAL_TILE)
    MD.after_move_triggers(st, 1, arrive_at_final_tile=True)
    assert st.get_entity(1).get_component(UnitFlagsComponent).has(
        UnitFlagsComponent.ARRIVED_AT_FINAL_TILE)


# ================================================ 2. le vecteur est joue PAR L'OPERATION, UNE fois
@pytest.fixture()
def spy(monkeypatch):
    """Espionne `after_move_triggers` sur son module de DEFINITION.

    `MoveUnitOperation.execute` l'appelle en forme MODULE (`move_death.after_move_triggers(...)`,
    #485-r1-r1), donc l'attribut est relu A L'APPEL : ce stub mord quelle que soit la forme de
    l'import du consommateur. Il visait auparavant le package `triggers` -- une adresse de
    COMMODITE fabriquee par le baril, qu'un hissage aurait desarmee EN SILENCE."""
    calls: list = []

    def fake(state, mover_id, movement_steps=None, *, is_interim_step=False,
             arrive_at_final_tile=True):
        calls.append({"mover": mover_id, "steps": movement_steps,
                      "interim": is_interim_step, "arrive": arrive_at_final_tile})
        return [{"spy": mover_id}]

    monkeypatch.setattr(MD, "after_move_triggers", fake)
    monkeypatch.setattr(MV, "refresh_effects_after_move_triggers", lambda state: [])
    return calls


def test_operation_joue_le_vecteur(spy):
    """C'EST LA TRANCHE. Avant #448-r1-r1-r2-r1 `MoveUnitOperation.execute` ne jouait RIEN : seul
    `MovementHandler.visit_MoveUnitMessage` appelait le vecteur, donc tout deplacement issu d'une
    feuille DSL etait MUET."""
    st = _state()
    op = MV.MoveUnitOperation(1, (1, 2))
    op.execute(st, EventBus())
    assert len(spy) == 1
    assert spy[0]["mover"] == 1 and spy[0]["interim"] is False and spy[0]["arrive"] is True
    assert op.last_after_move == [{"spy": 1}]


def test_handler_ne_double_pas(spy):
    """`MovementHandler` ne rejoue PLUS le vecteur : il republie celui de l'Operation. Un appel
    laisse en place chez l'appelant produirait DEUX overwatchs par pas."""
    st = _state()
    h = MV.MovementHandler(st, EventBus())

    class _Msg:
        unit_id, to = 1, (1, 2)

    h.visit_MoveUnitMessage(_Msg())
    assert len(spy) == 1
    assert h.after_move == [{"spy": 1}]


def test_relance_apres_override_remonte_le_vecteur_de_la_relance(monkeypatch, spy):
    """`OverrideMovementTargetOperation` devie le pas : le natif RELANCE `Execute` (avec
    `options+0x12 = 1`) et c'est CET appel-la qui joue le vecteur -- le mouvement abandonne n'en
    joue AUCUN. Un seul appel, sur la destination DEVIEE."""
    st = _state()
    e = st.get_entity(1)

    def fake_pre(state, mover_id, dest_tile=None):
        e.get_component(UnitComponent).movement_target_override = (3, 3)
        return []

    monkeypatch.setattr(MD, "pre_move_triggers", fake_pre)
    op = MV.MoveUnitOperation(1, (1, 2))
    op.execute(st, EventBus())
    assert len(spy) == 1
    assert (e.get_component(PositionComponent).col,
            e.get_component(PositionComponent).row) == (3, 3)
    assert op.last_after_move == [{"spy": 1}]


# ================================================================= 3. les call-sites, un par un
def _move_unit_calls(mod):
    """Les `MoveUnitOperation(...)` d'un module, avec leurs KWARGS -- releves par AST, jamais par
    comptage de chaine (un commentaire qui cite le drapeau ne doit pas compter comme un call-site)."""
    return [kw for _owner, kw in _move_unit_call_sites(mod)]


def _move_unit_call_sites(mod):
    """`(classe porteuse, kwargs)` par call-site, TRIE PAR LIGNE.

    Le porteur est nomme parce qu'un COMPTE NU ne dit pas QUI a bouge : ce test comptait `4` sur
    `displace.py` et #488 y a ajoute un 5e call-site legitime (`DirectDisplaceOperation`, le
    `Teleport`) -- le rouge accusait alors le fichier entier au lieu de designer l'entrant. La
    liste NOMMEE garde exactement le meme invariant (le compte en decoule) en le rendant lisible.
    `ast.walk` est un BFS : sans le tri par `lineno` l'ordre ne serait pas celui du source."""
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(mod))
    porteur = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for ln in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                porteur[ln] = node.name
    out = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "MoveUnitOperation"):
            out.append((node.lineno, porteur.get(node.lineno, "<module>"),
                        {kw.arg: ast.unparse(kw.value) for kw in node.keywords if kw.arg}))
    return [(o, kw) for _ln, o, kw in sorted(out, key=lambda t: t[0])]


def test_emit_after_move_false_ne_joue_rien(spy):
    """La FACE INVERSE. `emit_after_move=False` = « ce call-site mirroite
    `SetUnitPositionOperation$$Execute` » (push / pull / switch) ou « le natif ne deplace pas du
    tout » (flee). Brancher indistinctement serait l'erreur symetrique, du cote permissif."""
    st = _state()
    op = MV.MoveUnitOperation(1, (1, 2), emit_after_move=False)
    op.execute(st, EventBus())
    assert spy == []
    assert op.last_after_move == []


def test_displace_push_et_pull_ne_jouent_pas_le_vecteur(spy):
    """`DisplaceUnitOperation$$Execute` ecrit la position par le slot `SetUnitPosition`, puis emet
    SON vecteur (`$$EventAndAbilitiesAndEffects` = `On(0x24)`/`On(0x23)`/`On(0x1d)`, porte par
    `displace_triggers`). AUCUN `On(4)` : un push n'a jamais declenche l'overwatch cote natif.

    LES CINQ PORTEURS SONT NOMMES, et le 5e est arrive APRES cette garde : #488 a porte le case
    **4** (`Direct`) de `DisplaceUnitOperation$$Execute`, dont le SEUL producteur est
    `IdunBattleLogic.Entities.DSLBehaviors$$Teleport`. Il rejoint la MEME queue commune que le push
    et le pull -- `SetUnitPosition(target, ..., false)` (slot `0x7e`) puis
    `EventAndAbilitiesAndEffects` -- donc `emit_after_move=False` y est la MEME lecture, pas une
    exception : c'est pour cela qu'il entre dans la liste plutot que dans une derogation."""
    from engine.runner.operations import displace as DP
    sites = _move_unit_call_sites(DP)
    assert [o for o, _kw in sites] == [
        "PullUnitOneTileOperation",                          # `$$Execute` type 2 = FindTileToPull
        "SwitchPositionOperation", "SwitchPositionOperation",  # les DEUX moities, independantes
        "DisplaceUnitOperation",                             # `$$Execute` type 1 = FindTileToPush
        "DirectDisplaceOperation",                           # `$$Execute` case 4 = Direct (#488)
    ], "call-site(s) `MoveUnitOperation` de `displace.py` : %r" % (sites,)
    assert all(kw.get("emit_after_move") == "False" for _o, kw in sites), sites


def test_flee_ne_DEPLACE_PAS_DU_TOUT():
    """`IdunBattle.Operations.FleeOperation$$Execute` n'appelle NI `MoveUnit` NI `SetUnitPosition`.

    ⚠ **CETTE ASSERTION A ETE RENFORCEE, PAS ADAPTEE (#429-r1-r3-r1-r2-r1).** Elle exigeait
    `len(calls) == 1` avec `emit_after_move=False`, c'est-a-dire << le port deplace, mais sans jouer
    le vecteur >>. Or le decompile, relu EN ENTIER, ne porte AUCUN deplacement a cet endroit et ne
    met rien a la place : l'unite vient d'etre RETIREE du plateau (`<slot 6 = RemoveUnit>`), sa
    position n'a plus de lecteur. Le deplacement du port (`_safest_tile`) est donc SUPPRIME, et ce
    cran exige desormais **ZERO** call-site -- strictement plus fort que ce qu'il gardait.

    Ne jamais le rabattre a `<= 1` : ce serait re-autoriser en silence exactement ce qui vient
    d'etre retire."""
    from engine.runner.operations import behaviour as BH
    calls = _move_unit_calls(BH)
    assert calls == [], (
        "`FleeOperation` construit %d `MoveUnitOperation` -- le natif n'en construit AUCUN : %r"
        % (len(calls), calls))


def test_feuilles_dsl_ferment_arrive_at_final_tile():
    """Les feuilles `MoveUnit` / `FlyUnit` passent `arrive_at_final_tile=_DSL_ARRIVE_AT_FINAL_TILE`
    (= False), qui est l'octet `MoveUnitOptions+0x10` INVERSE depuis un selecteur a defaut FAUX."""
    from engine.runner.abilities.behaviours import movement as BM
    assert BM._DSL_ARRIVE_AT_FINAL_TILE is False
    calls = _move_unit_calls(BM)
    assert len(calls) == 2, "les feuilles `FlyUnit` et `MoveUnit`"
    assert all(c.get("arrive_at_final_tile") == "_DSL_ARRIVE_AT_FINAL_TILE" for c in calls), calls
    assert all("emit_after_move" not in c for c in calls), "une feuille DSL JOUE le vecteur"
    fly = [c for c in calls if "pathfinder_type_override" in c]
    assert len(fly) == 1, "`FlyUnit` est le seul a poser le `Nullable<PathfinderType>`"


def test_les_deux_call_sites_dsl_du_moteur_suivent_le_meme_defaut():
    """`HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateBehaviour` et les deux moities de
    `TheQuickeningAbility` (`$$GetMoveInBehaviour` / `$$GetMoveOutBehaviour`) sont, aux XREFS
    exhaustives, des call-sites de `IdunBattleLogic.Entities.DSLBehaviors$$MoveUnit` : leurs moves
    passent donc par `MoveUnitOperation$$Execute` et JOUENT le vecteur, avec le meme
    `arrive_at_final_tile` ferme que la feuille."""
    from engine.runner.operations.triggers import genestealer as GS
    from engine.runner.abilities.loki import quickening as QK
    gs = _move_unit_calls(GS)
    assert len(gs) == 1 and gs[0].get("arrive_at_final_tile") == "False"
    assert "emit_after_move" not in gs[0]
    qk = _move_unit_calls(QK)
    assert len(qk) == 2
    assert all(c.get("arrive_at_final_tile") == "False" for c in qk), qk
    assert all("emit_after_move" not in c for c in qk), qk


def test_betrayer_ne_double_plus_le_vecteur():
    """`TheBetrayer_TakeTurnAbility` portait un `Emit("BetrayerAfterMove")` explicite APRES sa
    feuille `MoveUnit` -- sa propre docstring prescrivait de le RETIRER le jour ou l'Operation
    replierait le vecteur. C'est ce jour-la."""
    import inspect
    from engine.runner.operations.triggers.loki import betrayer as BT
    src = inspect.getsource(BT.take_turn) if hasattr(BT, "take_turn") else inspect.getsource(BT)
    assert "BetrayerAfterMove" not in src.split('"""')[-1]


# ============================================================================ 4. contre-epreuve
def test_contre_epreuve_sans_le_repli_la_feuille_dsl_redevient_muette(monkeypatch, spy):
    """MUTATION = l'etat d'AVANT la tranche (`emit_after_move` force a False partout). La garde
    `test_operation_joue_le_vecteur` doit alors TOMBER -- c'est ce qui prouve qu'elle mord sur son
    gisement et pas sur autre chose."""
    st = _state()
    real_init = MV.MoveUnitOperation.__init__

    def muted_init(self, *a, **kw):
        kw["emit_after_move"] = False
        real_init(self, *a, **kw)

    monkeypatch.setattr(MV.MoveUnitOperation, "__init__", muted_init)
    op = MV.MoveUnitOperation(1, (1, 2))
    op.execute(st, EventBus())
    assert spy == [], "la mutation doit RENDRE le port muet -- sinon la garde ne mesure rien"
