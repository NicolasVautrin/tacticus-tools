"""GARDE OFFLINE #448-r1-r1 -- le gate de `1134 FullThrottle` et son SEUIL.

CE QUI REGRESSERAIT SANS ELLE. Deux fautes SYMETRIQUES, toutes deux silencieuses :

  * ne pas inscrire le `CreateTrigger` du tout -> le passif autonome redevient INERTE (l'etat
    d'avant cette tranche : `orksNpc6Stormboy` ne perdait jamais son jetpack en poussant les gaz) ;
  * l'inscrire avec le seuil NAIF -> `movementSteps` lu comme « nombre de pas » au lieu de
    `path.Count`. Le gate ne mordrait plus qu'a 3 pas alors que le natif mord des 2. MESURE LIVE
    (`probe_448_r1_r1_full_throttle.py`, greffe sur 5 unites du pool, board MC1_67) :

        pas parcourus | path.Count | NATIF          | PORT     | PORT si le `+1` est retire
              1       |     2      | 0 / 15 mort    |   0.0 %  |   0.0 %
              2       |     3      | 3 / 10 (30 %)  |  33.5 %  |   0.0 %   <- diverge du natif
              3       |     4      | 4 / 10 (40 %)  |  26.0 %  |  26.0 %

    P(0 mort sur 15 | gate vrai) = 0.7^15 = 0.47 % : le bras a 1 pas EXCLUT que le gate morde la,
    et le bras a 2 pas EXCLUT qu'il n'y morde pas. Le seuil est donc tranche des DEUX cotes.

RE : `IdunBattle.DSL.MovementStepFormula$$Calculate` = `Nullable<int>.GetValueOrDefault(
AbilityEntities+0x11c)`, champ nomme `movementSteps` dans la signature du ctor a 33 parametres
d'`IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` ; renseigne par le seul
`IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers`, qui le recoit d'
`IdunBattle.Operations.MoveUnitOperation$$Execute` ou il vaut `path.Count` (marcheur).
Detail : `docs/rl/case-448-r1-r1-full-throttle-gate.md`. ASCII only.
"""
from __future__ import annotations

import pytest

import gameconfig as GC
from engine.dsl.event_trigger_type import EventTriggerType
from engine.runner.abilities.behaviours.lifecycle import TRIGGERED_ABILITY_BEHAVIOURS
from engine.runner.operations.triggers.base import TriggerEvent
from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS
from engine.runner.operations.triggers.loki.full_throttle import (FULL_THROTTLE,
                                                                  FullThrottlePassiveAbility)

_EV = int(EventTriggerType.UnitPositionChanged_1)


def _ev(steps, actor=7):
    return TriggerEvent(_EV, actor, actor, ranged=False, profile=None, movement_steps=steps)


def test_registre_porte_les_deux_faces():
    """La face AUTONOME (`ABILITY_TRIGGERS`) et la face DIRECTE (`TRIGGERED_ABILITY_BEHAVIOURS`,
    exercee par `...StormboyzStrike_MissAbility` via le nœud `TriggerAbility`) coexistent : la
    seconde etait la seule portee avant cette tranche, et elle ne doit pas disparaitre."""
    assert FullThrottlePassiveAbility in (ABILITY_TRIGGERS.get("FullThrottle") or [])
    assert FULL_THROTTLE in TRIGGERED_ABILITY_BEHAVIOURS


def test_vecteur_est_bien_on_0x24():
    """`On(0x24 = UnitPositionChanged_1)` -- litteral LU. C'est le SEUL des trois events after-move
    emis aussi sur un pas intermediaire (`isInterimStep` court-circuite les deux autres)."""
    assert int(FullThrottlePassiveAbility.event_id) == 0x24


def test_constantes_du_kit():
    consts = (GC.ability("FullThrottle") or {}).get("constants", {})
    assert str(consts.get("movement")) == "3"
    assert str(consts.get("chance")) == "30"


@pytest.mark.parametrize("steps,expect", [(None, False), (0, False), (1, False), (2, False),
                                          (3, True), (4, True), (9, True)])
def test_seuil_du_gate(steps, expect):
    """`AmountIsEqualOrGreater(MovementSteps(), Direct(movement = 3))`, balaye sur tout le canal.

    `None` = le `Nullable` VIDE du natif : `GetValueOrDefault()` rend 0, donc gate FAUX. Ce n'est
    PAS un tri-etat « se taire » -- c'est la reponse native, et les trois emetteurs qui laissent le
    champ nul (`On(0x1f)` pre-move, `DisplaceUnitOperation$$EventAndAbilitiesAndEffects`,
    `ReviveUnitOperation$$SetRevivePosition`) comptent dessus."""
    assert bool(FullThrottlePassiveAbility(owner_id=7).matches(None, _ev(steps))) is expect


def test_owner_is_actor():
    """`get_OwnerIsActor` : le passif d'une unite ne fire pas sur le mouvement d'une AUTRE."""
    trig = FullThrottlePassiveAbility(owner_id=7)
    assert trig.matches(None, _ev(9, actor=8)) is False


def test_movement_steps_vaut_path_count_pas_le_nombre_de_pas():
    """LE POINT QUI A ETE MESURE. `_movement_steps` doit rendre `path.Count` = `pas + 1`, jamais le
    nombre de pas -- sinon le seuil glisse de 2 a 3 et le port cesse de tuer la ou le natif tue.

    On ne monte pas de board ici (c'est le role du test LIVE) : on verifie la LOI de conversion
    au-dessus de `_num_tiles_moved`, qui est la seule chose que ce module ajoute."""
    from engine.runner.operations import movement as MV

    calls = {}

    def fake_num_tiles(state, mover_id, from_pos, to_pos):
        calls["n"] = calls.get("n", 0) + 1
        return fake_num_tiles.value

    class _Sc:
        class ctx:
            traits = []

    class _E:
        def get_component(self, _cls):
            return _Sc()

    class _St:
        def get_entity(self, _uid):
            return _E()

    orig = MV._num_tiles_moved
    MV._num_tiles_moved = fake_num_tiles
    try:
        for pas, attendu in ((0, 0), (1, 2), (2, 3), (3, 4), (7, 8)):
            fake_num_tiles.value = pas
            got = MV._movement_steps(_St(), 1, (0, 0), (1, 1))
            assert got == attendu, "pas=%d -> movement_steps=%d (attendu %d)" % (pas, got, attendu)
    finally:
        MV._num_tiles_moved = orig


def test_canal_movement_steps_default_none():
    """Le canal est OPTIONNEL et vaut `None` par defaut : tout emetteur d'event qui ne le threade
    pas (la quasi-totalite) reste sur le `Nullable` vide, comme le natif."""
    assert TriggerEvent(_EV, 1, 1, ranged=False, profile=None).movement_steps is None
