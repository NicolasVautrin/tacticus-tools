"""Opération `ChangeStat` du runner — applique/reverte une stat-modification sur `UnitStats` en cours
de bataille, mirror de `IdunBattle.Messages.ModifyStatMessage` (émis par `AStatModifierEffect.
ApplyModification @180f0a2f0` part 5/9 = apply, `RevertModification @180f0aa40` part 6 = revert) et de
`DSLFactory.ChangeStat @180debdc0`.

GÉNÉRALISE la mutation de stat ad-hoc (ActOfFaith `cc_delta/cd_delta`, `operations.triggers`) : la
**modification par-source** de `UnitStats` rend le revert EXACT **sans stocker de delta** (le natif
retire le modifier de la source via `ReverseModification`, la valeur observable se re-clampe au read).

Les consommateurs combat/prédiction lisent la stat via `UnitContext.stat(type)` (= `get_stat(Current)`
si le composant est seedé, sinon champ plat) → **plus de synchro de champ plat nécessaire** : muter
`UnitStats` suffit à ce que le combat voie le stat-mod.
"""
from __future__ import annotations

from typing import Optional

from ...entities.stats import StatComponent, StatPart, STAT_CLAMP_MAX
from ..components import StatsComponent

# StatType → champ plat `UnitContext` (ce que les consommateurs combat lisent encore ; None = aucun).
FLAT_FIELD = {
    0: "attack", 5: "health", 7: "block_chance", 8: "block_damage",
    9: "crit_chance", 10: "crit_damage", 16: "fixed_armor", 17: "extra_hits",
}


def _ctx(state, unit_id: int):
    ent = state.get_entity(int(unit_id))
    sc = ent.get_component(StatsComponent) if ent is not None else None
    return sc.ctx if sc is not None else None


def _ensure_component(ctx, stat_type: int) -> StatComponent:
    """Garantit un `StatComponent` pour `stat_type` ; si absent, le seede avec `initial` = valeur plate
    COURANTE (sinon la modification partirait d'une base 0 → Current faux). Applique le plafond par-stat."""
    idx = int(stat_type)
    us = ctx.stats
    comp = us.components.get(idx)
    if comp is None:
        field = FLAT_FIELD.get(idx)
        cur = int(getattr(ctx, field, 0) or 0) if field else 0
        comp = StatComponent(initial=cur, min_value=0, max_value=STAT_CLAMP_MAX.get(idx))
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
