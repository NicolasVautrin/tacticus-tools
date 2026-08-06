"""#366-r1 -- le canal OVERRIDE (`IdunBattle.Entities.Effects.StatOverrideEffect`, parts 7/8) est
pilote par le MEME driver que le canal additif, et le SEED doit le poser comme un OVERRIDE, jamais
comme une modification.

Pourquoi les deux volets tiennent ensemble, lu au decompile :

  `IdunBattle.Operations.RefreshEffectsOperation$$ApplyEffectsForTargets`  -> `IEffect+0xe`
  `IdunBattle.Operations.RefreshEffectsOperation$$RevertEffectsForTargets` -> `IEffect+0xf`

  = `IdunBattle.Entities.Effects.BaseEffect$$Apply` / `$$Revert`, qui delegent aux virtuels
  `<Effect>.ApplyInternal` (`*(vtable+0x548)`) / `RevertInternal` (`*(vtable+0x578)`). Le refresh ne
  connait donc PAS la famille de l'effet : pour un `AStatModifierEffect` cela donne le couple
  additif (part 5|9 / part 6), pour un `StatOverrideEffect` cela donne
  `ValueOverride.SetOverride` (part 7) / `RemoveOverride` (part 8).

Le piege que ce fichier RETIENT -- l'ATTRIBUTION AU SEED. `IdunBattle.Entities.Components.
StatComponent$$get_CurrentValue` rend `override + (isModifiable ? modTotal : 0)` et IGNORE la base.
Verser le delta capte (`Current - Initial`) d'un stat OVERRIDE dans le residu opaque
`CAPTURED_SOURCE`, comme le fait le chemin ordinaire, y laisse donc une modification FANTOME :
invisible tant que l'override est la (il domine), et qui REVIENT integralement des que le driver
joue le `RemoveOverride`. Symptome exact, avec `blockChance` forcee a 100 par `1109
ReinforcedHiveNode_ExtraBlock` : le port reste a 100 la ou le natif retombe a 0.

ASCII only.
"""
from __future__ import annotations

from engine.entities.effects_state import EffectsState
from engine.entities.effects import effect_stat_overrides, stat_overrides_by_stat
from engine.entities.effects.factory import EffectFactory
from engine.entities.effect_type import EffectType
from engine.entities.stats import CAPTURED_SOURCE, StatType, seed_unit_stats
from engine.entities.unit_context import UnitContext
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, UnitComponent)
from engine.runner.operations.refresh_effects import refresh_stat_modifier_effects
from engine.runner.state import State

EXTRA_BLOCK = "ReinforcedHiveNode_ExtraBlock"        # EffectType 0x455 = 1109
BLOCK = int(StatType.BLOCK_CHANCE)                   # 7
TURNS = int(StatType.TURNS_STARTED)                  # 0xc


def _state_with_block_override(turns_started: int, active: bool):
    """`State` minimal : UNE unite portant UNE instance de `1109`, seedee comme le fait
    `UnitContext.from_snapshot` -- `blockChance` Initial 0 + l'override de l'effet quand il est
    ACTIF (c'est ce que la capture publie : Current 100 / Initial 0 aux parites paires)."""
    st = State()
    st.effects = EffectsState.seed({})
    e = st.add_entity()
    e.add_component(UnitComponent(visual_id="tyranNpc4Warrior", alive=True))
    e.add_component(OwnerComponent(team=1, player=1))
    inst = EffectFactory.create({"name": EXTRA_BLOCK,
                                 "effectType": int(EffectType.ReinforcedHiveNode_ExtraBlock),
                                 "remaining": 0, "active": active})
    inst.target = e.id
    # Le seed EXACT de la production : meme fonction, meme entree que `from_snapshot`.
    live_block = 100 if active else 0
    us = seed_unit_stats({"blockChance": live_block, "turnsStarted": turns_started},
                         {"blockChance": live_block} if live_block else {},
                         {"blockChance": BLOCK, "turnsStarted": TURNS},
                         attributed=None, overrides=stat_overrides_by_stat([inst]))
    ctx = UnitContext(entity_id=e.id, visual_id="tyranNpc4Warrior", active_ability_level=50,
                      passive_ability_level=50, ability_variables_multiplier=100, stats=us)
    e.add_component(StatsComponent(ctx=ctx))
    e.add_component(HealthComponent(hp=1000, hp_max=1000))
    e.add_component(PositionComponent(col=2, row=2))
    st.effects.add_effect(e.id, inst)
    return st, e.id, inst


def test_1109_declares_the_native_triple():
    """CLIQUET du canal DATA : `applied_stat_overrides` doit rendre le triplet natif
    `(statType, amount, isModifiable)` -- 3e argument litteral d'`AddStatOverrideEffectToOwner`,
    `Direct(GetNumberConstant(0x2d = blockChance))` evalue, et le champ `+0x480` du DEF ecrit par
    `IdunBattle.Entities.Effects.Loki.ReinforcedHiveNode_ExtraBlockEffect$$.ctor` (`r8 = 0`)."""
    from engine.entities.effects.magnitude import ability_var
    inst = EffectFactory.create({"name": EXTRA_BLOCK, "effectType": 1109,
                                 "remaining": 0, "active": True})
    expected = ability_var("ReinforcedHiveNode", "blockChance", is_constant=True)
    assert expected, "constante gameconfig `blockChance` introuvable"
    assert effect_stat_overrides(inst) == [(BLOCK, int(expected), False)], (
        "le triplet declare ne mirrore plus la feuille native : %s"
        % (effect_stat_overrides(inst),))


def test_inactive_instance_poses_no_override():
    """MEME regle d'activite que l'additif (`_carries_modification`) :
    `RefreshEffectsOperation$$DeactivateEffect` ecrit `IsActive @+0x5c = 0` PUIS
    `UpdateEffectTargets([])` -> `RevertInternal` = `RemoveOverride`. Un effet capte INERTE n'a
    donc AUCUN override chez sa cible."""
    inert = EffectFactory.create({"name": EXTRA_BLOCK, "effectType": 1109,
                                  "remaining": 0, "active": False})
    assert stat_overrides_by_stat([inert]) == {}, (
        "un effet capte INERTE s'est vu attribuer un override que le natif ne pose pas")


def test_seed_does_not_leave_a_phantom_modification_under_the_override():
    """LE PIEGE. Le delta capte d'un stat OVERRIDE ne doit PAS atterrir dans `CAPTURED_SOURCE` :
    il y serait invisible (l'override domine `get_CurrentValue`) et REVIENDRAIT au
    `RemoveOverride`."""
    st, uid, _ = _state_with_block_override(turns_started=0, active=True)
    us = st.get_entity(uid).get_component(StatsComponent).ctx.stats
    comp = us.components[BLOCK]
    assert us.get_stat(BLOCK) == 100, "le seed ne reproduit pas le `blockChance` capte"
    assert comp.get_stat_part(3) == 0, "part Initial != 0 -- le seed n'a pas lu Current - delta"
    assert CAPTURED_SOURCE not in comp.modification.per_source, (
        "modification FANTOME sous l'override (%s) -- elle reapparaitra au RemoveOverride"
        % (comp.modification.per_source,))
    assert comp.override.override == 100 and comp.override.is_modifiable is False


def test_driver_removes_the_override_when_the_condition_falls():
    """LE DRIVER, sens EXTINCTION : `turnsStarted` IMPAIR -> `AmountIsOdd(Sum(RoundsStarted, 1))`
    est faux -> `DeactivateEffect` -> `RemoveOverride` (part 8) -> `blockChance` retombe a sa part
    Initial. C'est la mesure live 100 <-> 0 du passif."""
    st, uid, inst = _state_with_block_override(turns_started=0, active=True)
    us = st.get_entity(uid).get_component(StatsComponent).ctx.stats
    assert us.get_stat(BLOCK) == 100
    # Le tour suivant du porteur : `StartTurnOperation` bump `turnsStarted` (compteur BRUT).
    us.increment_base(TURNS, 1)
    refresh_stat_modifier_effects(st, uid)
    assert inst.active is False, (
        "condition portee fausse (turnsStarted impair) et l'instance reste allumee")
    assert us.get_stat(BLOCK) == 0, (
        "l'override n'a PAS ete retire : blockChance=%d au lieu de 0" % us.get_stat(BLOCK))
    assert us.components[BLOCK].override.override is None


def test_driver_reposes_the_override_when_the_condition_comes_back():
    """LE DRIVER, sens RALLUMAGE : une instance seedee INACTIVE dont la condition PORTEE redevient
    vraie doit re-poser son override (`ActivateEffect` -> `ApplyInternal` -> `SetOverride`).
    C'est le pendant OVERRIDE du regime que `test_ported_condition_relights_a_seeded_inactive_
    instance` garde sur l'additif."""
    st, uid, inst = _state_with_block_override(turns_started=1, active=False)
    us = st.get_entity(uid).get_component(StatsComponent).ctx.stats
    assert us.get_stat(BLOCK) == 0, "montage casse : le regime INACTIF doit partir de 0"
    us.increment_base(TURNS, 1)                      # turnsStarted 1 -> 2 : PAIR, donc ACTIF
    refresh_stat_modifier_effects(st, uid)
    assert inst.active is True
    assert us.get_stat(BLOCK) == 100, (
        "l'override n'a PAS ete repose : blockChance=%d au lieu de 100" % us.get_stat(BLOCK))
    assert us.components[BLOCK].override.is_modifiable is False, (
        "`isModifiable` perdu -- les modifications par-source s'ajouteraient a l'override, ce que "
        "`ReinforcedHiveNode_ExtraBlockEffect$$.ctor` (r8 = 0) interdit")


def test_non_modifiable_override_ignores_per_source_modifications():
    """`IdunBattle.Entities.Components.ValueOverride$$GetOverrideValueWithModification` =
    `override + (isModifiable ? modTotal : 0)`. Avec `isModifiable = 0`, une modification posee par
    un AUTRE effet sur `blockChance` ne doit RIEN changer tant que 1109 est actif -- et redevenir
    visible des qu'il s'eteint."""
    st, uid, _ = _state_with_block_override(turns_started=0, active=True)
    us = st.get_entity(uid).get_component(StatsComponent).ctx.stats
    us.change_stat(BLOCK, ("statmod", 1200, 1, "AnvilShield_BlockChanceBelowHealthCap"), 20)
    assert us.get_stat(BLOCK) == 100, (
        "la modification +20 s'est ajoutee a un override NON modifiable (%d)" % us.get_stat(BLOCK))
    us.increment_base(TURNS, 1)
    refresh_stat_modifier_effects(st, uid)
    assert us.get_stat(BLOCK) == 20, (
        "override retire : la modification +20 doit redevenir visible, pas %d" % us.get_stat(BLOCK))


def test_additive_path_is_untouched_without_overrides():
    """NON-REGRESSION du chemin historique : sans `overrides`, `seed_unit_stats` garde EXACTEMENT
    son comportement (delta -> `CAPTURED_SOURCE`, aucun override pose)."""
    us = seed_unit_stats({"blockChance": 100}, {"blockChance": 100}, {"blockChance": BLOCK})
    comp = us.components[BLOCK]
    assert us.get_stat(BLOCK) == 100
    assert comp.modification.per_source == {CAPTURED_SOURCE: 100}
    assert comp.override.override is None
