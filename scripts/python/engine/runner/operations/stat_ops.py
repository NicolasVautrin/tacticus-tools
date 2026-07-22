"""Opération `ChangeStat` du runner — applique/reverte une stat-modification sur `UnitStats` en cours
de bataille, mirror de `IdunBattle.Messages.ModifyStatMessage` (émis par `AStatModifierEffect.
ApplyModification @180f0a2f0` part 5/9 = apply, `RevertModification @180f0aa40` part 6 = revert) et de
`DSLFactory.ChangeStat @180debdc0`.

GÉNÉRALISE la mutation de stat ad-hoc (ActOfFaith `cc_delta/cd_delta`, `operations.triggers`) : la
**modification par-source** de `UnitStats` rend le revert EXACT **sans stocker de delta** (le natif
retire le modifier de la source via `ReverseModification`, la valeur observable se re-clampe au read).

Les consommateurs combat/prédiction lisent la stat via `UnitContext.stat(type)` / les propriétés
`ctx.<stat>` (= `get_stat(Current)`) → **aucune synchro de champ plat** : muter `UnitStats` suffit à ce
que le combat voie le stat-mod. Les 8 stats de base sont TOUJOURS seedées à la construction (from_snapshot
/ build_summon_context), donc `_ensure_component` ne crée un composant (`initial=0`) que pour un StatType
non-seedé (0 = défaut natif).
"""
from __future__ import annotations

from typing import Optional

from ...entities.stats import StatComponent, StatPart, STAT_CLAMP_MAX
from ..components import StatsComponent


def _ctx(state, unit_id: int):
    ent = state.get_entity(int(unit_id))
    sc = ent.get_component(StatsComponent) if ent is not None else None
    return sc.ctx if sc is not None else None


def _ensure_component(ctx, stat_type: int) -> StatComponent:
    """Garantit un `StatComponent` pour `stat_type` ; si absent, le seede `initial=0`. Les 8 stats de
    base sont déjà seedées à la construction (from_snapshot / build_summon_context) → ce chemin ne se
    déclenche que pour un StatType non-seedé (base 0 = défaut natif correct). Applique le plafond par-stat."""
    idx = int(stat_type)
    us = ctx.stats
    comp = us.components.get(idx)
    if comp is None:
        comp = StatComponent(initial=0, min_value=0, max_value=STAT_CLAMP_MAX.get(idx))
        us.set_component(idx, comp)
    return comp


def apply_change_stat(state, unit_id: int, stat_type: int, source, amount: int) -> Optional[int]:
    """`ModifyStatMessage` (apply, part 5/9) → `UnitStats.change_stat(stat_type, source, amount)`.
    Attribué à `source` (revertable individuellement). Le combat le voit via `ctx.stat(type)` (pas de
    synchro de champ plat). No-op (`None`) si l'unité n'a pas de stats. Renvoie la nouvelle valeur Current."""
    ctx = _ctx(state, unit_id)
    if ctx is None:
        return None
    _ensure_component(ctx, stat_type)
    ctx.stats.change_stat(int(stat_type), source, int(amount))
    return ctx.stats.get_stat(int(stat_type), StatPart.CURRENT)


def revert_change_stat(state, unit_id: int, stat_type: int, source) -> Optional[int]:
    """`ModifyStatMessage` (revert, part 6) → `UnitStats.revert_stat(stat_type, source)`. Revert EXACT
    par-source (`ReverseModification`), la valeur se re-clampe au read — pas de delta stocké. No-op
    (`None`) si pas de stats. Renvoie la nouvelle valeur Current."""
    ctx = _ctx(state, unit_id)
    if ctx is None:
        return None
    ctx.stats.revert_stat(int(stat_type), source)
    return ctx.stats.get_stat(int(stat_type), StatPart.CURRENT)


def apply_stat_override(state, unit_id: int, stat_type: int, value: int,
                        is_modifiable: bool = True) -> Optional[int]:
    """`ChangeStat` mode 4 + `Position(statType, part 7 = OVERRIDE)` (émis par ex. par
    `MV71SniperDroneSquad_InitialDmgEffect.ApplyStat @180f573f0`) → `StatComponent.ApplyModifier
    @180fa8800` case 7 → `ValueOverride.SetOverride @180faea70`. La valeur (ex. stat CURRENT du
    parent) est SNAPSHOTÉE par l'appelant (nœud `Direct(...)` évalué à l'exécution). Renvoie la
    nouvelle valeur Current (None si pas de stats)."""
    ctx = _ctx(state, unit_id)
    if ctx is None:
        return None
    ctx.stats.set_stat_override(int(stat_type), int(value), is_modifiable)
    return ctx.stats.get_stat(int(stat_type), StatPart.CURRENT)


def remove_stat_override(state, unit_id: int, stat_type: int) -> Optional[int]:
    """`ChangeStat` mode 4 + `Position(statType, part 8 = REMOVE_OVERRIDE)` (ex.
    `MV71SniperDroneSquad_InitialDmgEffect.ResetStat @180f57620`, appelé ×4 par `RevertInternal
    @180f577d0`) → `ApplyModifier @180fa8800` case 8 → `ValueOverride.RemoveOverride @180fae930`.
    Renvoie la nouvelle valeur Current (None si pas de stats)."""
    ctx = _ctx(state, unit_id)
    if ctx is None:
        return None
    ctx.stats.remove_stat_override(int(stat_type))
    return ctx.stats.get_stat(int(stat_type), StatPart.CURRENT)
