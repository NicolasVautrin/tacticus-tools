"""#576-r1 -- `1369 BloodChalice_ExtraPiercing` est POSE et INERTE A VIE, et sa contribution SORT.

LA MESURE QUI FONDE CES ETAGES (chaine LUE sur `rnca9r7q6c`, aucun maillon deduit) :

  1. `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` `memset` son `AbilityEntities`
     de 0x128 octets a ZERO, puis n'ecrit QUE `<+0x08>` = owner, `<+0x18>` = owner,
     `<+0x50>` = activePlayer, `<+0x58>` = effectEntity ;
  2. `IdunBattle.Entities.Selectors.TargetSelector$$Select` lit `ctx+0x10` -- **jamais ecrit** --
     et rend une `List` VIDE (temoins du meme corps : `OwnerSelector$$Select` -> `ctx+0x18`,
     `EffectSelector$$Select` -> `ctx+0x58`, tous deux RENSEIGNES) ;
  3. `IdunBattle.DSL.TargetsSelector$$SelectUnit` rend `0` sur liste vide ;
  4. `IdunBattle.Entities.Triggers.IsChargingTrigger$$ShouldTrigger` court-circuite
     (`if (SelectUnit(caster) == 0 || SelectUnit(target) == 0) return false`) sans meme appeler
     `IdunBattle.Core.Services.BattleQuery$$IsCharging`.

=> la `CreateActiveCondition` de `1369` (`IsCharging(Owner@sel+0x30, Target@sel+0x60)`) est
FAUSSE dans le seul contexte qui l'evalue. Concorde avec la mesure live #576 : apres le cast,
`decisionView` publie `1368` sur la cible et RIEN pour `1369` (`readEffectsByUnit` droppe
`IsActive == 0`).

CE QUE CES ETAGES GARDENT, et dans cet ordre : le verdict de la condition (etage 1), le fait que
l'effet sorte des `active_effects` (etage 2), et le RETRAIT de sa contribution `ExtraPierceMelee`
par le driver de refresh (etages 3-4) -- ce dernier etant le cran qui change un chiffre.

CE QUI N'EST PAS COUVERT, et qu'il faut lire : la FENETRE entre la pose et le premier refresh. La
feuille `AddStaticStatModifierEffect` applique la stat A LA POSE ; le driver ne tourne qu'aux
declencheurs natifs (`TurnChanged`, `UnitPositionChanged`, degat sur la cible). Le natif, lui,
n'applique la modification QUE par `RefreshEffectsOperation$$ApplyEffectsForTargets`, donc jamais.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/engine/entities/effects/loki/blood_chalice.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects_state.py",
        "scripts/python/engine/runner/operations/refresh_effects.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/entities/stats.py",
        # Le POSEUR : c'est lui qui installe `stat_mod_source` + `reverted_stats` sur l'instance,
        # les deux entrees dont l'etage 4 depend.
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Purement offline : aucun runner, aucun RPC. Les etages montent un `State` a la main "
              "et n'exercent que la classe d'effet, `EffectsState.active_effects` et le driver "
              "`refresh_stat_modifier_effects`.",
}

import os                                                                # noqa: E402
import sys                                                               # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))                       # noqa: E402

from engine.entities.effect_type import EffectType                       # noqa: E402
from engine.entities.effects.factory import EffectFactory                # noqa: E402
from engine.entities.effects.loki.blood_chalice import (                 # noqa: E402
    BloodChaliceExtraPiercingEffect)
from engine.entities.stats import StatType                               # noqa: E402
from engine.runner.operations.refresh_effects import (                   # noqa: E402
    refresh_stat_modifier_effects)

BENEF = 42
PIERCE = int(StatType.EXTRA_PIERCE_MELEE)
KEY = "eff:%d:%d:test" % (int(EffectType.BloodChalice_ExtraPiercing), BENEF)


def _placed_effect():
    """L'instance telle que la feuille `AddStaticStatModifierEffect` la laisse : materialisee, sa
    contribution DEJA posee sous SA cle (`stat_mod_source`), et `reverted_stats` installe en
    callable sur l'instance (c'est litteralement ce que fait la feuille)."""
    eff = EffectFactory.create({"name": "BloodChalice_ExtraPiercing",
                                "effectType": int(EffectType.BloodChalice_ExtraPiercing),
                                "level": 1, "remaining": 2, "source": 7})
    eff.target = BENEF
    eff.stat_mod_source = KEY
    eff.reverted_stats = (lambda st=PIERCE: [st])
    return eff


def test_la_classe_est_bien_celle_du_port():
    """Etage 0 -- sans lui, tout le reste pourrait porter sur un `BaseEffect` anonyme (le defaut
    quand un nom n'est pas au registre), dont `is_active` rend `True` : les etages 1-4 seraient
    alors verts POUR LA MAUVAISE RAISON, ou rouges sans rapport avec la RE."""
    assert isinstance(_placed_effect(), BloodChaliceExtraPiercingEffect)


def test_la_condition_est_FAUSSE_quel_que_soit_l_etat():
    """Etage 1 -- le verdict natif, et son INDEPENDANCE a l'etat. `is_active` ne doit pas se
    contenter de rendre faux sur un `unit_state` vide (ce serait la degradation habituelle, qui va
    dans l'autre sens) : elle rend faux MEME sur un contexte riche."""
    eff = _placed_effect()
    assert eff.is_active(None) is False
    assert eff.is_active({}) is False
    assert eff.is_active({"hp": 100, "max_hp": 100, "traits": ["Chaos"],
                          "owner_id": BENEF, "has_moved": False}) is False
    assert eff.active_condition_ported is True, (
        "sans ce drapeau, le flag CAPTE/pose (`active=True`) ferait foi et `active_effects` "
        "rendrait l'effet contribuant malgre la condition")


def test_l_effet_SORT_des_effets_actifs():
    """Etage 2 -- l'observable de LECTURE. `EffectsState.active_effects` conjugue le flag et la
    condition ; c'est ce que consultent tous les gates `HasEffect(..., activeOnly)`."""
    from engine.entities.effects_state import EffectsState
    st = EffectsState()
    eff = _placed_effect()
    st.add_effect(BENEF, eff)
    assert eff.active is True, "temoin : le FLAG est pose (pose offline), c'est la CONDITION qui ferme"
    assert st.active_effects(BENEF, {}) == []


def _state_with_placed_effect():
    """Un `State` minimal portant le beneficiaire, ses stats, et l'instance deja posee."""
    from engine.entities.effects_state import EffectsState
    from engine.entities.stats import UnitStats
    from engine.runner.components import StatsComponent
    from engine.runner.state import State

    state = State()
    ent = state.add_entity(BENEF)
    us = UnitStats()

    class _Ctx:
        traits = []
        stats = us

        def get_stat(self, *_a, **_k):
            return 0
    ent.add_component(StatsComponent(ctx=_Ctx()))
    state.effects = EffectsState()
    eff = _placed_effect()
    state.effects.add_effect(BENEF, eff)
    us.change_stat(PIERCE, KEY, 15)                 # ce que la feuille a pose a la pose
    return state, us, eff


def test_temoin_NON_NUL_la_contribution_est_bien_POSEE_avant_le_refresh():
    """Etage 3 -- le temoin. Sans lui, l'etage 4 serait vert par vacuite : retirer une
    contribution qui n'a jamais ete posee ne prouve rien."""
    _state, us, _eff = _state_with_placed_effect()
    assert us.get_stat(PIERCE) == 15


def test_le_refresh_RETIRE_la_contribution_dont_la_condition_est_fausse():
    """Etage 4 -- LE cran. Mirror de `DeactivateEffect` -> `UpdateEffectTargets([])` ->
    `RevertEffectsForTargets` -> slot `IEffect+0xf` : la `ValueModification` de l'entite-effet sort
    du `UnitStats`. Le driver ne RE-APPLIQUE jamais une instance posee offline -- il ne fait que la
    retirer quand la condition PORTEE est fausse."""
    state, us, eff = _state_with_placed_effect()
    out = refresh_stat_modifier_effects(state, BENEF)
    assert us.get_stat(PIERCE) == 0, (
        "le natif ne compte JAMAIS le +extraPierceRatio de 1369 (sa condition d'activite est "
        "structurellement fausse) : le port doit retirer la contribution, pas la garder")
    assert (BENEF, PIERCE, None) in out
    assert eff.active is False, "mirror de `DeactivateEffect` : `EffectComponent.IsActive` = 0"
