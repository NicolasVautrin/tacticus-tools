"""Opération `ChangeStat` du runner — applique/reverte une stat-modification sur `UnitStats` en cours
de bataille, mirror de `IdunBattle.Messages.ModifyStatMessage` (émis par `AStatModifierEffect.
IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification` part 5/9 = apply, `IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification` part 6 = revert) et de
`IdunBattleLogic.Entities.DSLBehaviors$$ChangeStat`.

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

from ...entities.stats import (FillUpStatComponent, StatComponent, StatPart, StatType,
                               STAT_CLAMP_MAX)
from ..components import HealthComponent, StatsComponent


def _ctx(state, unit_id: int):
    ent = state.get_entity(int(unit_id))
    sc = ent.get_component(StatsComponent) if ent is not None else None
    return sc.ctx if sc is not None else None


# ── #572-r1 : le DISPATCH natif, lu verbatim dans le switch d'`ApplyStatModifier` ────────────────
#
# `IdunBattle.Entities.UnitExtensions$$ApplyStatModifier` est le foyer UNIQUE de toute
# stat-modification (xref unique d'`ApplyModifier`). Son `switch (statModifier.StatType)` a
# exactement TROIS cases qui appellent
# `IdunBattle.Entities.Components.FillUpStatComponent$$ApplyModifier` -- toutes les autres vont
# a `IdunBattle.Entities.Components.StatComponent$$ApplyModifier` :
#
#     case 4  = StatType.Armor              -> FillUpStatComponent (`ArmorComponent`)
#     case 5  = StatType.Health             -> FillUpStatComponent (`HealthComponent`)
#     case 20 = StatType.NumberOfMembers    -> FillUpStatComponent (`NumberOfMembersComponent`)
#
# ⚠ Pour ces trois-la, le natif n'a **AUCUN** `StatComponent` : la modification vit dans le
# `ValueModification` du composant fill-up, et elle releve le MAXIMUM
# (`get_CurrentMaximumValue`), pas la valeur courante. Le port l'ecrivait dans
# `UnitStats.components[<stat>]`, **que rien ne relit pour les PV** -- le no-op silencieux de
# #572-r1 (natif `+9970` de max, port `+0`).
#
# #572-r3 -- LES DEUX AUTRES CASES, ET POURQUOI ELLES SE TRAITENT DIFFEREMMENT.
#
# * `StatType.HEALTH` a un composant ECS DEDIE (`HealthComponent`, #572-r1) : c'est LUI le
#   reservoir, et `UnitStats.components[5]` n'est qu'un doublon que `GetStat` court-circuite.
# * `StatType.NUMBER_OF_MEMBERS` vit dans `UnitStats.components[20]`, seede en
#   `FillUpStatComponent` depuis #572-r3 -- c'est le MEME layout natif
#   (`NumberOfMembersComponent : FillUpStatComponent`), donc la meme famille d'ecritures
#   (`ModifyMax` / `ReverseMaxModification` / `OverrideMax` / `RemoveMaxOverride`).
# * `StatType.ARMOR` n'est PAS route : MESURE live (#572-r3, `probe_572r3_membres_et_armure.py`,
#   13 entites x 14 tours) -- `observeBattle.armor` et `combatSnapshot.armorMax` valent **0** sur
#   TOUTES, et le gameconfig ne porte QUE `FixedArmor` (aucune des 683 configurations `lineup`/
#   `npc`/`summons` n'a de stat `Armor`). Le canal existe, le regime est VIDE : router l'ecriture
#   serait un port SPECULATIF, invalidable par construction. Verdict et temoins : la case-doc.
_FILLUP_STAT_COMPONENTS = {
    StatType.HEALTH: HealthComponent,      # case 5 -- `IdunBattle.Entities.Components.HealthComponent`
}

#: Les stats fill-up dont le composant vit dans `UnitStats` (et non en composant ECS dedie).
#: case 20 -- `IdunBattle.Entities.Components.NumberOfMembersComponent`.
_FILLUP_DANS_UNIT_STATS = (StatType.NUMBER_OF_MEMBERS,)


def _fillup_component(state, unit_id: int, stat_type: int):
    """Le composant fill-up qui porte `stat_type`, ou `None` si le port n'en a pas (stat non
    fill-up, ou unite sans le composant).

    C'est le mirror du dispatch ci-dessus : quand il rend un composant, l'ecriture DOIT y aller et
    NON dans le `StatComponent` de `UnitStats` -- sinon deux reservoirs pour une meme grandeur, et
    un seul bouge."""
    idx = int(stat_type)
    cls = _FILLUP_STAT_COMPONENTS.get(idx)
    if cls is not None:
        ent = state.get_entity(int(unit_id))
        return None if ent is None else ent.get_component(cls)
    if idx in _FILLUP_DANS_UNIT_STATS:
        ctx = _ctx(state, unit_id)
        comp = ctx.stats.components.get(idx) if ctx is not None else None
        return comp if isinstance(comp, FillUpStatComponent) else None
    return None


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
    hc = _fillup_component(state, unit_id, stat_type)
    if hc is not None:
        # `ApplyModifier` part `StatPart.MODIFICATION` -> `ModifyMax` : c'est le MAXIMUM qui monte
        # (`get_CurrentMaximumValue`), la valeur COURANTE ne bouge pas -- le natif ne la touche
        # dans aucune branche de modification. Le `+extraHp` de PV COURANTS qui accompagne un tel
        # buff vient d'un `ChangeStat(Current, mode Add)` SEPARE, pas d'ici.
        hc.modify_max(source, int(amount))
        return hc.get_stat_part(StatPart.CURRENT)
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
    hc = _fillup_component(state, unit_id, stat_type)
    if hc is not None:
        hc.reverse_max_modification(source)              # `ApplyModifier` part RESET_MODIFICATION
        return hc.get_stat_part(StatPart.CURRENT)
    ctx = _ctx(state, unit_id)
    if ctx is None:
        return None
    ctx.stats.revert_stat(int(stat_type), source)
    return ctx.stats.get_stat(int(stat_type), StatPart.CURRENT)


def apply_stat_override(state, unit_id: int, stat_type: int, value: int,
                        is_modifiable: bool = True) -> Optional[int]:
    """`ChangeStat` mode 4 + `Position(statType, part 7 = OVERRIDE)` (émis par ex. par
    `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$ApplyStat`) → `IdunBattle.Entities.Components.StatComponent$$ApplyModifier` case 7 → `IdunBattle.Entities.Components.ValueOverride$$SetOverride`. La valeur (ex. stat CURRENT du
    parent) est SNAPSHOTÉE par l'appelant (nœud `Direct(...)` évalué à l'exécution). Renvoie la
    nouvelle valeur Current (None si pas de stats)."""
    hc = _fillup_component(state, unit_id, stat_type)
    if hc is not None:
        hc.override_max(int(value), is_modifiable)       # `ApplyModifier` case 7 -> `OverrideMax`
        return hc.get_stat_part(StatPart.CURRENT)
    ctx = _ctx(state, unit_id)
    if ctx is None:
        return None
    ctx.stats.set_stat_override(int(stat_type), int(value), is_modifiable)
    return ctx.stats.get_stat(int(stat_type), StatPart.CURRENT)


def remove_stat_override(state, unit_id: int, stat_type: int) -> Optional[int]:
    """`ChangeStat` mode 4 + `Position(statType, part 8 = REMOVE_OVERRIDE)` (ex.
    `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$ResetStat`, appelé ×4 par `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$RevertInternal`) → `IdunBattle.Entities.Components.StatComponent$$ApplyModifier` case 8 → `IdunBattle.Entities.Components.ValueOverride$$RemoveOverride`.
    Renvoie la nouvelle valeur Current (None si pas de stats)."""
    hc = _fillup_component(state, unit_id, stat_type)
    if hc is not None:
        hc.remove_max_override()                         # `ApplyModifier` case 8 -> `RemoveMaxOverride`
        return hc.get_stat_part(StatPart.CURRENT)
    ctx = _ctx(state, unit_id)
    if ctx is None:
        return None
    ctx.stats.remove_stat_override(int(stat_type))
    return ctx.stats.get_stat(int(stat_type), StatPart.CURRENT)
