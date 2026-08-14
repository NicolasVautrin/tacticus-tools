"""GARDE #448-r2b tranche 2/4 (OFFLINE PURE) -- `1140 StormboyzStrike_TeleportingIn`, la seule
derivee d'`IdunBattle.Entities.Effects.Loki.ATeleportingEffect` SANS `*_Moving`.

CE QU'ELLE PROTEGE, et pourquoi chaque bloc peut regresser SILENCIEUSEMENT :

  1. **L'INSCRIPTION des quatre `Triggered()`** de la base, avec leurs `event_id`. En perdre un ne
     casse rien : l'unite reste seulement non-ciblable et sur son pathfinder de teleport plus
     longtemps que le natif -- degradation PERMISSIVE, sans erreur ni crash.
  2. **La branche `Nothing()` de T4** : `MOVING_EFFECT_TYPE is None`. C'est le point PROPRE de
     cette tranche, et il ne se deduit PAS d'une absence de symbole -- la surcharge
     `StormboyzStrike_TeleportingInEffect$$GetMovingEffectType` EXISTE (vslot 0x758, trouvee a la
     profondeur 0 par le RPC `resolveMethodPtr`), son corps est DEDUPLIQUE avec
     `Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId` et vaut `xor eax, eax ; ret` :
     `Nullable<EffectType>` (int32 + bool, 8 octets) revient dans RAX, donc `hasValue = 0`.
     Un port qui lui donnerait un `*_Moving` par SYMETRIE avec ses trois soeurs poserait un
     marqueur qui n'existe pas -- et le test verifie AUSSI qu'aucun `StormboyzStrike_Moving`
     n'existe dans l'`EffectType` du build.
  3. **Le gate `HasTile(Owner)` de T3**, exerce sur ses DEUX bras. 1140 est la SEULE des quatre
     dont le poseur (`...StormboyzStrike_TeleportAbility$$CreateBehaviour`) appelle
     `RemoveUnitFromItsTiles` : sous 1140 l'unite est HORS PLATEAU, `HasTile` est FAUX, T3 ne fire
     pas et l'effet SURVIT a la fin de son tour. Un port qui perdrait le gate le retirerait --
     l'unite redeviendrait ciblable et sortirait du pathfinder de teleport en pleine descente.
  4. **L'ABSENCE de couche imperative derriere le retrait** : contrairement a 1035, la
     specialisation de 1140 ne porte PAS `_TeleportStrikeLandingMixin`. Le regime est l'inverse :
     c'est `On(0x21 = AbilityInit)` qui POSE 1140, donc les owner-effects du porteur sont deja
     initialises quand l'effet arrive (mesure live : volet E1b du probe, le porteur greffe arrive
     sous 1140 avec ses `BeastSlayer_*`). Ajouter le mixin ici serait une couche SPECULATIVE.
  5. **Le DOMAINE de non-ciblabilite** : le flag `UnitFlag 0x11` vient de
     `IdunBattle.Entities.Effects.Common.UntargetableEffect$$ApplyInternal`, donc de la BASE et non
     de l'effet feuille. Le port en fait un domaine (`UNTARGETABLE_EFFECT_TYPES`) et non une
     constante. 1238 / 1573 / `JustSummonedEffect` en restent DEHORS tant que leur tranche n'est
     pas confrontee -- un ajout speculatif retirerait des cibles a l'IA sans mesure.

Confrontation LIVE : `python scripts/python/probe_448_r2b_stormboyz_teleporting_in.py`.
RE : `docs/rl/case-448-r2b-stormboyz-teleporting-in.md`. ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import hexgeo                                                            # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType               # noqa: E402
from engine.ai.state_bridge import _is_untargetable                      # noqa: E402
from engine.entities.effects_state import EffectsState  # noqa: E402
from engine.entities.effect_type import EffectType                       # noqa: E402
from engine.entities.effects.aura_selectors import (                     # noqa: E402
    UNTARGETABLE_EFFECT_TYPES, is_targetable)
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.components import (PositionComponent, UnitComponent,   # noqa: E402
                                      get_unit_feet, set_unit_feet)
from engine.runner.operations.triggers.base import TriggerEvent          # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS  # noqa: E402
from engine.runner.operations.triggers.dispatch.turn import (            # noqa: E402
    unit_finished_turn_triggers)
from engine.runner.operations.triggers.loki.teleporting_in import (      # noqa: E402
    ATeleportingRemoveTrigger,
    STORMBOYZ_STRIKE_TELEPORTING_IN, TELEPORT_STRIKE_TELEPORTING_IN,
    StormboyzStrikeTeleportingInAddMovingOnPreMove,
    StormboyzStrikeTeleportingInRemoveOnAfterMove,
    StormboyzStrikeTeleportingInRemoveOnPreUnitAbility,
    StormboyzStrikeTeleportingInRemoveOnUnitFinishedTurn)
from engine.runner.operations.effects import AddEffectOperation          # noqa: E402
from engine.runner.snapshot import load_state                            # noqa: E402

COLS, ROWS = 7, 7
CARRIER, ALLY, FOE = 10, 40, 20

REMOVE_CLASSES = [StormboyzStrikeTeleportingInRemoveOnAfterMove,
                  StormboyzStrikeTeleportingInRemoveOnPreUnitAbility,
                  StormboyzStrikeTeleportingInRemoveOnUnitFinishedTurn]


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles() -> list:
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return out


@pytest.fixture
def state():
    board = Board(_tiles(), adjacency="evenq")
    decision = {"currentPlayer": 1, "units": [
        {"id": CARRIER, "visualId": "orksNob", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 0, "row": 3}, "effects": []},
        {"id": ALLY, "visualId": "orksWarboss", "alive": True, "team": 1, "owner": 1,
         "pos": {"col": 1, "row": 3}, "effects": []},
        {"id": FOE, "visualId": "ultraTitus", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 6, "row": 6}, "effects": []},
    ]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000}
                         for u in decision["units"]]}
    snapshot = {"units": [{"entityId": u["id"], "entityType": 1,
                           "stats": {"health": 1000, "movement": 3, "turnsStarted": 0},
                           "healthMax": 1000, "traits": [], "unitFlags": [],
                           "unitConfig": {"visualId": u["visualId"], "level": 50,
                                          "passiveAbilityLevel": 50, "activeAbilityLevel": 50,
                                          "abilityVariablesMultiplier": 100}}
                          for u in decision["units"]]}
    st = load_state(decision, observe, snapshot, board=board, ability_states=False)
    if st.effects is None:
        st.effects = EffectsState()
    return st


def _put(st, uid, effect_type, name, duration=None):
    AddEffectOperation.execute(st, source=uid, target=uid, effect_type=int(effect_type),
                               name=name, duration_override=duration)


def _live(st, uid, effect_type) -> list:
    return [e for e in (st.effects.by_unit.get(int(uid)) or [])
            if int(getattr(e, "effect_type", -1)) == int(effect_type) and not e.consumed]


def _ev(event_id, actor=CARRIER):
    return TriggerEvent(int(event_id), actor, actor, ranged=False, profile=None)


def _off_board(st, uid):
    """`...StormboyzStrike_TeleportAbility$$CreateBehaviour` -> `RemoveUnitFromItsTiles(Owner,
    removeTileFromUnit: true)`, dont le port mirror le collapse par `set_unit_feet(..., [])` :
    empreinte VIDE **et** `PositionComponent` retiree (#366-r1/#438)."""
    set_unit_feet(st, int(uid), [])


# --------------------------------------------------------- 1. l'inscription au registre

def test_the_registry_holds_the_four_triggers_for_1140():
    got = EFFECT_TRIGGERS.get(STORMBOYZ_STRIKE_TELEPORTING_IN) or []
    assert [c.__name__ for c in got] == [
        "StormboyzStrikeTeleportingInRemoveOnAfterMove",
        "StormboyzStrikeTeleportingInRemoveOnPreUnitAbility",
        "StormboyzStrikeTeleportingInRemoveOnUnitFinishedTurn",
        "StormboyzStrikeTeleportingInAddMovingOnPreMove"], [c.__name__ for c in got]
    assert [c.event_id for c in got] == [int(EventTriggerType.UnitAfterMove),      # On(0x04)
                                         int(EventTriggerType.PreUnitAbility),     # On(0x2a)
                                         int(EventTriggerType.UnitFinishedTurn),   # On(0x28)
                                         int(EventTriggerType.PreUnitMove)]        # On(0x1f)
    assert all(c.effect_type == STORMBOYZ_STRIKE_TELEPORTING_IN for c in got)
    assert int(EffectType.StormboyzStrike_TeleportingIn) == 1140


# --------------------------------------------------------- 2. la branche Nothing() de T4

def test_T4_declares_no_moving_effect_and_poses_nothing(state):
    """`GetMovingEffectType()` rend un `Nullable` VIDE -> `Nothing()`. T4 doit MATCHER (sa
    condition est vraie) et ne RIEN poser : c'est la difference entre << la condition est fausse >>
    et << la condition est vraie mais le behaviour est `Nothing()` >>, et seule la seconde est le
    natif."""
    assert StormboyzStrikeTeleportingInAddMovingOnPreMove.MOVING_EFFECT_TYPE is None
    _put(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN, "StormboyzStrike_TeleportingIn")
    before = sorted(int(e.effect_type)
                    for e in (state.effects.by_unit.get(CARRIER) or []) if not e.consumed)
    trig = StormboyzStrikeTeleportingInAddMovingOnPreMove(CARRIER)
    assert trig.matches(state, _ev(EventTriggerType.PreUnitMove)) is True
    assert trig.execute_behaviour(state, _ev(EventTriggerType.PreUnitMove)) is None
    after = sorted(int(e.effect_type)
                   for e in (state.effects.by_unit.get(CARRIER) or []) if not e.consumed)
    assert after == before, "T4 a POSE quelque chose alors que le Nullable natif est VIDE"


def test_no_StormboyzStrike_Moving_exists_in_the_build_enum():
    """CLIQUET sur la SOURCE. Les `*_Moving` du build sont EXACTEMENT trois -- ceux des trois
    soeurs -- et `TeleportMovingEffect$$.ctor` n'a que trois appelants. Si un
    `StormboyzStrike_Moving` apparaissait, le corps `xor eax,eax ; ret` de
    `StormboyzStrike_TeleportingInEffect$$GetMovingEffectType` serait a relire."""
    moving = sorted(m.name for m in EffectType if m.name.endswith("_Moving"))
    assert moving == ["FearOfTheUnseen_Moving", "TeleportStrike_Moving",
                      "TitanhammerSquad_Moving"], moving


# --------------------------------------------------------- 3. le gate HasTile de T3

def test_T3_keeps_the_effect_while_the_carrier_is_off_board(state):
    """LE point de la tranche. Hors plateau -> `HasTile(Owner)` FAUX -> T3 ne matche PAS et
    l'effet SURVIT ; une fois repose (ce que fait `...StormboyzStrike_FallbackAbility`, NON
    PORTEE), le MEME trigger retire."""
    _put(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN, "StormboyzStrike_TeleportingIn")
    _off_board(state, CARRIER)
    assert get_unit_feet(state, CARRIER) == []
    assert state.get_entity(CARRIER).get_component(PositionComponent) is None
    assert state.get_entity(CARRIER).get_component(UnitComponent).alive is True

    # On passe par le VECTEUR de production (`On(0x28)`), pas par `execute_behaviour` : c'est
    # `evaluate_trigger_operation` qui evalue `matches` avant le behaviour -- exactement comme le
    # `Triggered(cond, behaviour)` natif. Appeler le behaviour en direct court-circuiterait le gate
    # qu'on veut precisement mesurer.
    t3 = StormboyzStrikeTeleportingInRemoveOnUnitFinishedTurn(CARRIER)
    assert t3.matches(state, _ev(EventTriggerType.UnitFinishedTurn)) is False
    unit_finished_turn_triggers(state, CARRIER)
    assert len(_live(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN)) == 1, \
        "T3 a retire l'effet d'une unite HORS PLATEAU -- le gate `HasTile(Owner)` est perdu"

    set_unit_feet(state, CARRIER, [(2, 2)])                 # sortie observee du Fallback
    assert t3.matches(state, _ev(EventTriggerType.UnitFinishedTurn)) is True
    unit_finished_turn_triggers(state, CARRIER)
    assert _live(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN) == []


def test_only_T3_carries_the_HasTile_gate(state):
    """T1, T2 et T4 ne portent PAS `HasTile` : hors plateau ils matchent quand meme. C'est ce qui
    permet a T1 de retirer l'effet a l'arrivee du pas de teleport (l'unite part de nulle part)."""
    _put(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN, "StormboyzStrike_TeleportingIn")
    _off_board(state, CARRIER)
    for cls in (StormboyzStrikeTeleportingInRemoveOnAfterMove,
                StormboyzStrikeTeleportingInRemoveOnPreUnitAbility,
                StormboyzStrikeTeleportingInAddMovingOnPreMove):
        assert cls(CARRIER).matches(state, _ev(cls.event_id)) is True, \
            "%s ne doit PAS porter le gate HasTile" % cls.__name__


@pytest.mark.parametrize("cls", REMOVE_CLASSES)
def test_each_removal_trigger_drops_1140_when_its_condition_holds(state, cls):
    _put(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN, "StormboyzStrike_TeleportingIn")
    assert len(_live(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN)) == 1
    out = cls(CARRIER).execute_behaviour(state, _ev(cls.event_id))
    assert _live(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN) == []
    assert out is not None and out["removed"] == 1, out


@pytest.mark.parametrize("cls", REMOVE_CLASSES + [
    StormboyzStrikeTeleportingInAddMovingOnPreMove])
def test_owner_is_actor_is_exercised_both_ways(state, cls):
    """`get_OwnerIsActor` sur les QUATRE. Sans lui, le pas d'une unite quelconque ferait atterrir
    tous les Stormboyz du plateau."""
    _put(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN, "StormboyzStrike_TeleportingIn")
    trig = cls(CARRIER)
    assert trig.matches(state, _ev(cls.event_id, actor=CARRIER)) is True
    assert trig.matches(state, _ev(cls.event_id, actor=ALLY)) is False


# --------------------------------------------------------- 4. AUCUNE couche imperative

@pytest.mark.parametrize("cls", REMOVE_CLASSES)
def test_no_deferred_passive_layer_is_attached_to_1140(state, cls):
    """1140 ne porte PAS `_TeleportStrikeLandingMixin` : `_after_remove` doit etre celui de la
    BASE (liste vide). Le regime << passives DEFERREES >> est propre a 1035 -- pour 1140 c'est
    `On(0x21 = AbilityInit)` lui-meme qui pose l'effet, donc les owner-effects du porteur sont
    deja la (mesure live E1b). L'`_after_remove` remonte aussi dans le retour du trigger, ce que
    le test verifie plutot que d'inspecter la MRO."""
    assert cls._after_remove is ATeleportingRemoveTrigger._after_remove, (
        "%s a acquis une couche imperative d'atterrissage -- le natif ne fait que "
        "`RemoveEffect(EffectSelf)`" % cls.__name__)
    _put(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN, "StormboyzStrike_TeleportingIn")
    out = cls(CARRIER).execute_behaviour(state, _ev(cls.event_id))
    assert out is not None and out["after"] == [], out


# --------------------------------------------------------- 5. le domaine UntargetableEffect

def test_1140_makes_its_carrier_untargetable(state):
    """`UntargetableEffect$$ApplyInternal` -> `UnitFlagsComponent$$Add(0x11)` : le flag vient de la
    BASE, donc de TOUTE derivee. Les deux lecteurs du port (`_is_untargetable` cote decision,
    `is_targetable` cote selecteur d'aura) partagent le MEME domaine."""
    assert _is_untargetable(state, CARRIER) is False
    assert is_targetable(state, CARRIER) is True
    _put(state, CARRIER, STORMBOYZ_STRIKE_TELEPORTING_IN, "StormboyzStrike_TeleportingIn")
    assert _is_untargetable(state, CARRIER) is True
    assert is_targetable(state, CARRIER) is False
    assert _is_untargetable(state, ALLY) is False          # exerce dans les deux sens


def test_the_untargetable_domain_holds_only_the_confronted_slices():
    """CLIQUET. Fermeture NATIVE de `UntargetableEffect` = les 4 `ATeleportingEffect` +
    `JustSummonedEffect`. Le port n'inscrit que ce qu'il a CONFRONTE SUR CE CANAL : 1035 (#448-r2),
    1140 (#448-r2b) et 1238 (#448-r2b-r1).

    ⚠ `1573` reste DEHORS -- il arrive avec #448-r2d et son poseur n'est pas porte.
    Ce test tombe des qu'une inscription se fait sans sa confrontation."""
    assert sorted(UNTARGETABLE_EFFECT_TYPES) == [TELEPORT_STRIKE_TELEPORTING_IN,
                                                 STORMBOYZ_STRIKE_TELEPORTING_IN,
                                                 int(EffectType.FearOfTheUnseen_TeleportingIn)]
    assert int(EffectType.TitanhammerSquad_TeleportingIn) not in UNTARGETABLE_EFFECT_TYPES, (
        "TitanhammerSquad_TeleportingIn inscrite au domaine sans que la face DECISION soit "
        "CONFRONTEE (le port de ses triggers ne suffit pas -- cf. #448-r2d)")


#: Les QUATRE `EffectType` que materialise `IdunBattle.Entities.Effects.Loki.JustSummonedEffect`.
#: L'ENSEMBLE est etabli par CARDINAL, pas par appariement un-a-un : `JustSummonedEffect$$.ctor` a
#: exactement QUATRE appelants, tous des lambdas d'`IdunBattle.Core.Services.EffectsDatabase$$
#: InitializeEffects` (`<>c$$<InitializeEffects>b__14_62..65`), et le build ne porte QUE ces quatre
#: `EffectType` dont le nom contient `JustSummoned` (`data/symbols/<build>/frida/enums.tsv`).
#: 4 = 4, et le domaine est un ENSEMBLE : cela suffit a le clore.
JUST_SUMMONED_FAMILY = (EffectType.JustSummoned,                            # 1
                        EffectType.GeminaeSuperia_JustSummonedEffect,       # 0x425 = 1061
                        EffectType.SwornProtector_JustSummonedEffect,       # 0x4ce = 1230
                        EffectType.DecoysAndMisdirection_JustSummonedEffect)  # 0x56e = 1390


def _scan_add_effect(base) -> dict:
    """`{ordinal: {fichiers}}` des `AddEffect(<ordinal>, ...)` EXECUTABLES sous `base`.

    C'est la seule ecriture par laquelle un effet entre dans `state.effects` cote port.

    ⚠ La lecture se fait sur l'**AST**, jamais sur le texte. Un premier jet en `re` a rendu
    « 1061 est POSE par spawn.py » : la ligne trouvee etait la PROSE « aucun AddEffect(1061) dans
    ce kit » -- un commentaire qui dit exactement le CONTRAIRE de ce que le balayage en concluait.
    Un critere textuel ne peut pas separer le code de ce qui parle du code."""
    import ast

    def _ordinal(node, consts):
        """L'ordinal `EffectType` qu'un noeud d'ARGUMENT designe, ou `None`. QUATRE ecritures :
        litteral nu, `EffectType.<Nom>`, l'enveloppe `int(...)`, et un NOM de constante de module.

        ⚠ La 4e n'y etait pas, et c'est la CONTRE-EPREUVE qui l'a montre : le seul poseur porte de
        `1238` s'ecrit `AddEffect(FEAR_TELEPORTING_IN, ...)` -- le balayage rendait donc « 0 poseur »
        pour lui AUSSI, ce qui aurait fait passer pour un fait mesure ce qui n'etait qu'un angle
        mort du recenseur."""
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return node.value
        if isinstance(node, ast.Attribute):
            m = getattr(EffectType, node.attr, None)
            return None if m is None else int(m)
        if isinstance(node, ast.Name):
            return consts.get(node.id)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "int" and node.args):
            return _ordinal(node.args[0], consts)
        return None

    poses: dict = {}
    lus = 0
    for p in sorted(base.rglob("*.py")):
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:                      # pragma: no cover - arbre casse = un autre test
            continue
        lus += 1
        consts: dict = {}                        # `NOM = <ordinal>` au niveau MODULE
        for n in arbre.body:
            if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                    and isinstance(n.targets[0], ast.Name):
                o = _ordinal(n.value, {})
                if o is not None:
                    consts[n.targets[0].id] = o
        for n in ast.walk(arbre):
            if not isinstance(n, ast.Call):
                continue
            nom = n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", None)
            if nom != "AddEffect" or not n.args:
                continue
            o = _ordinal(n.args[0], consts)
            if o is not None:
                poses.setdefault(o, set()).add(p.name)
    poses["__modules_lus__"] = lus
    return poses


def _doit_entrer_au_domaine(ordinal: int, poses: dict, retraits: dict) -> bool:
    """LA REGLE, ecrite UNE fois et exercee DEUX fois (le reel ci-dessous, le synthetique ensuite).

    Un `EffectType` de la famille `JustSummoned` n'entre au domaine de non-ciblabilite que si le
    port porte SES DEUX FACES :

      * un POSEUR -- sans lui l'inscription est strictement inerte (`has_effect` rend toujours
        faux) tout en donnant l'illusion d'avoir ferme le trou ;
      * un RETIREUR -- `IdunBattle.Entities.Effects.Loki.JustSummonedEffect$$CreateRemoveEffectTrigger`
        = `On(0x3a = PhaseEnd) | (On(0x1f = PreUnitMove, true) & get_OwnerIsActor)
        | (On(0x2a = PreUnitAbility, true) & get_OwnerIsActor)`. Le flag `UnitFlag 0x11` que pose
        `UntargetableEffect$$ApplyInternal` est retire par `$$RevertInternal`, donc au retrait de
        l'effet -- et RIEN d'autre ne le retire.

    Inscrire un effet POSE mais JAMAIS RETIRE rendrait son porteur non ciblable **pour le reste de
    la bataille** : une divergence bien pire que l'absence d'inscription, et RESTRICTIVE au point
    de rendre le porteur inattaquable en self-play."""
    return bool(poses.get(ordinal)) and bool(retraits.get(ordinal))


def test_the_just_summoned_family_stays_out_because_its_REMOVAL_is_not_ported():
    """CLIQUET du REFUS RE-MESURE (#1074). La premisse de #448-r2b-r1 -- « aucun site du port ne
    les POSE » -- est MORTE : `GeminaeSuperiaAbility$$CreateBehaviour` est porte depuis #963
    (`triggers/loki/geminae_superia.py`), et son `opts.<+0x10>` fait
    `AddEffect(0x425 = GeminaeSuperia_JustSummonedEffect, ..., Target@+0x60)`.

    LA QUESTION RE-TRANCHEE. `JustSummonedEffect` derive bien d'`UntargetableEffect`
    (`data/symbols/<build>/frida/classes.tsv`), donc 1061 rend son porteur -- CELESTINE, le trigger
    exigeant `get_OwnerIsTarget` -- non ciblable. Mais l'arbre du passif ne le retire JAMAIS : c'est
    l'effet lui-meme qui porte `$$CreateRemoveEffectTrigger`, et ce trigger-la n'est PAS porte
    (`EFFECT_TRIGGERS` n'a aucune entree pour 1061). Inscrire 1061 au domaine aujourd'hui rendrait
    donc Celestine non ciblable POUR LE RESTE DE LA BATAILLE.

    Le refus tient toujours, mais son FONDEMENT a change : ce n'est plus l'absence de POSEUR, c'est
    l'absence de RETIREUR. Le cran ci-dessous est BIDIRECTIONNEL -- il rougit aussi le jour ou le
    retrait est porte sans que l'inscription suive, c'est-a-dire quand le blocage est leve.
    Residu ouvert : `#1074` (porter `JustSummonedEffect$$CreateRemoveEffectTrigger`, puis inscrire).
    """
    from pathlib import Path
    base = Path(__file__).resolve().parents[3] / "engine"
    assert base.is_dir(), "arbre `engine/` introuvable depuis %s" % __file__

    poses = _scan_add_effect(base)
    lus = poses.pop("__modules_lus__")
    assert lus > 100, "balayage trop maigre (%d modules) -- un vide passerait pour un vert" % lus
    assert poses, "aucun `AddEffect(<ordinal>)` trouve : le critere ne mesure plus rien"
    # Le RETIREUR se lit au registre des effet-triggers -- meme canal que les quatre `Triggered()`
    # d'`ATeleportingEffect` portes par cette tranche.
    assert len(EFFECT_TRIGGERS) >= 40, (
        "registre des effet-triggers effondre (%d types) : `retraits.get(...)` rendrait vide POUR "
        "TOUT LE MONDE, donc le cran serait vert sans avoir rien mesure" % len(EFFECT_TRIGGERS))

    for eff in JUST_SUMMONED_FAMILY:
        attendu = _doit_entrer_au_domaine(int(eff), poses, EFFECT_TRIGGERS)
        present = int(eff) in UNTARGETABLE_EFFECT_TYPES
        assert present == attendu, (
            "%s : pose par %s, retrait porte = %s -> %s au domaine, or il y est %s. "
            "Poseur SANS retireur = porteur non ciblable pour le reste de la bataille ; "
            "retireur porte SANS inscription = le blocage est leve, inscris-le (#1074)."
            % (eff.name, sorted(poses.get(int(eff)) or ()) or "personne",
               bool(EFFECT_TRIGGERS.get(int(eff))),
               "doit entrer" if attendu else "doit rester dehors",
               "present" if present else "absent"))

    # LA PREMISSE NEUVE EST ELLE-MEME MESUREE : si plus aucun membre n'etait pose, ce cran ne
    # garderait plus que l'ancienne question (« rien ne les pose »), et son intitule mentirait.
    assert any(poses.get(int(e)) for e in JUST_SUMMONED_FAMILY), (
        "plus aucun membre de la famille JustSummoned n'est POSE : le fondement du refus est "
        "redevenu l'absence de poseur -- re-trancher, et renommer ce cran")
    # CONTRE-EPREUVE : le meme balayage DOIT voir le poseur de 1238, sans quoi il ne prouverait
    # rien sur les quatre ci-dessus (un recenseur aveugle rend « 0 poseur » partout).
    assert int(EffectType.FearOfTheUnseen_TeleportingIn) in poses, (
        "le balayage ne voit pas le poseur de 1238 (`abilities/tyranids.py`) : son zero sur la "
        "famille JustSummoned ne prouve donc rien")


def test_the_domain_rule_still_MEANS_something_when_the_real_population_is_EMPTY():
    """BRAS SYNTHETIQUE. Le cran ci-dessus interroge le REEL ; s'il tombait a une population vide
    (aucun poseur, aucun retireur) il resterait vert sans rien garder. On FABRIQUE donc les quatre
    combinaisons et on exige que la regle les separe -- c'est le seul moyen de savoir qu'elle dit
    encore quelque chose."""
    o = int(EffectType.GeminaeSuperia_JustSummonedEffect)
    pose, vide = {o: {"geminae_superia.py"}}, {}
    retrait = {o: [object()]}
    assert _doit_entrer_au_domaine(o, vide, vide) is False        # ni pose ni retire
    assert _doit_entrer_au_domaine(o, pose, vide) is False         # POSE seul = l'etat COURANT
    assert _doit_entrer_au_domaine(o, vide, retrait) is False      # retire seul (inerte)
    assert _doit_entrer_au_domaine(o, pose, retrait) is True       # les DEUX faces -> inscrire
