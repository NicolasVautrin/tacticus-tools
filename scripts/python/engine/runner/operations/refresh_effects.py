"""`IdunBattle.Operations.RefreshEffectsOperation` — ACTIVATION / DESACTIVATION des effets selon leur
`CreateActiveCondition`, et propagation sur les `AStatModifierEffect` (#100).

Chaine native RE'd (build gqfc5mff6c) :

    IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect
        if (EffectComponent+0x5c == 0) return ;              # deja inactif -> no-op
        EffectComponent+0x5c = 0 ; UpdateEffectTargets(...)  # +0x5c = le flag IsActive
    IdunBattle.Operations.ActivateEffectOperation$$Execute / DeactivateEffectOperation$$Execute
    IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification   -> ChangeStat(part 5) = +montant
    IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification  -> ChangeStat(part 6) = retrait
    IdunBattle.Entities.Effects.ADynamicStatModifierEffect$$RefreshValueInternal = Revert puis Apply

Le flag `+0x5c` est CE QUE LIT le gate `HasEffect(..., activeOnly=1)` :
`IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect` skippe toute entree dont `+0x5c == 0` quand son
4e argument est non nul (et TOUS les `DSLFactory$$HasEffect` du cluster AnvilShield passent 1).

## Pourquoi ce driver

Le port evalue `is_active()` A LA LECTURE (predicats/consommateurs) — c'est suffisant pour les GATES.
Mais la **contribution STAT** d'un `AStatModifierEffect` conditionnel doit, elle, entrer et sortir du
`UnitStats` quand la condition bascule : c'est exactement ce que fait `RefreshEffectsOperation` cote
natif. Cas porte : `AnvilShield_BlockChanceBelowHealthCap` (1200) dont l'`ActiveCondition` est
`healthPct(35) >= GetStat(HEALTH, CURRENT_PCT)` -> `blockChance` d'Arjac passe 0 -> 20 quand il tombe
sous 35 % PV (GROUND TRUTH LIVE #100), et redescend s'il repasse au-dessus.

## Perimetre (blast radius NUL par construction)

`refresh_stat_modifier_effects` ne touche QUE les effets qui :
  1. declarent un `get_stat_modification_stat()` (famille `AStatModifierEffect`), ET
  2. ne declarent AUCUN `applied_stat_mods` (= les stat-mods « declaratifs », ceux que l'ATTRIBUTION du
     seed pose via `stat_modifications_by_source`) — les effets a stat-mod EAGER (ActOfFaith,
     DoctrinaImperatives, `AnvilShield_FrozenAttackerAdvantage`...) sont poses/revertes par
     `AddEffectOperation._apply_stat_mods` / la feuille `RemoveEffect` sous LEUR propre cle et sont
     donc SKIPPES ici.
La cle de source utilisee est **exactement** celle du seed (`statmod_source_key`) et
`ValueModification.Modify` est un **replace par-source** -> re-appliquer la meme valeur est un NO-OP
exact. Seule la bascule `is_active() == False` change quelque chose (retrait de la contribution).
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import StatsComponent, HealthComponent
from ...entities.effects import statmod_source_key


def _unit_state(state: State, unit_id: int) -> dict:
    """`{hp, max_hp}` — l'argument `unit_state` des `is_active()` (mirror des `StatAmount(Self, HEALTH,
    CURRENT/CURRENT_PCT)` des `CreateActiveCondition`)."""
    ent = state.get_entity(unit_id)
    hc = ent.get_component(HealthComponent) if ent is not None else None
    if hc is None:
        return {}
    return {"hp": hc.hp, "max_hp": hc.hp_max}


def refresh_stat_modifier_effects(state: State, unit_id: Optional[int] = None) -> list:
    """Mirror `RefreshEffectsOperation` (volet stat-modifier) : pour chaque effet DECLARATIF a stat-mod
    porte par `unit_id` (ou par TOUTES les unites si None), applique sa modification si son
    `ActiveCondition` est vraie, la reverte sinon. Renvoie la liste des `(unit, stat, amount|None)`
    effectivement (re)ecrits — diagnostic.

    Idempotent : meme cle de source que l'attribution du seed + `Modify` = replace par-source."""
    out: list = []
    if state.effects is None:
        return out
    uids = [int(unit_id)] if unit_id is not None else list(state.effects.by_unit.keys())
    for uid in uids:
        effs = state.effects.by_unit.get(int(uid))
        if not effs:
            continue
        ent = state.get_entity(uid)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        us = getattr(sc.ctx, "stats", None) if sc is not None else None
        if us is None:
            continue
        ustate = _unit_state(state, uid)
        for e in effs:
            if e.consumed or e.expired:
                continue
            stat = e.get_stat_modification_stat()
            if stat is None:
                continue
            if e.applied_stat_mods(getattr(sc, "ctx", None)):
                continue                      # stat-mod EAGER : gere par AddEffect/RemoveEffect
            src = statmod_source_key(e)
            if e.is_active(ustate):
                amt = e.get_stat_modification_amount()
                if amt:
                    us.change_stat(int(stat), src, int(amt))   # ApplyModification (part 5)
                    out.append((int(uid), int(stat), int(amt)))
            else:
                us.revert_stat(int(stat), src)                 # RevertModification (part 6)
                out.append((int(uid), int(stat), None))
    return out
