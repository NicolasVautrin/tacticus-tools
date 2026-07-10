"""Operation de SOIN — `IdunBattle.Operations.HealUnitOperation$$Execute @180e733d0`.

Mutateur ECS inverse du degat : remonte les PV d'une cible, plafonne a `hp_max` (FillUp).
KEYSTONE de la categorie HEAL/REPAIR/lifesteal du runner combat (cf.
`docs/rl/combat-ability-coverage.md`, tache #94) : SpiritLeech lifesteal, MassHeal, MechRepair,
BattleTinkererRepair, etc. delegueront ici pour muter les PV cote EXECUTION (le runner no-op-ait
SILENCIEUSEMENT ces abilities, cf. doctrine CLAUDE.md "DECIDER != EXECUTER").
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ..components import HealthComponent

if TYPE_CHECKING:
    from ..state import State

# EffectType.Cursed (79 = 0x4f) — GATE heal-block. `HealUnitOperation$$Execute @180e733d0` fait
# `EntityExtensions.HasEffect(target, 0x4f)` : si l'effet est present, le montant de soin est force
# a 0 (branche `if ((char)param_6 == '\0') healAmount = computed;` sinon healAmount reste 0).
CURSED = 0x4f


class HealUnitOperation:
    """`IdunBattle.Operations.HealUnitOperation$$Execute @180e733d0` (caller mince
    `Core.Services.OperationProcessor$$HealUnit @180e082d0`).

    Coeur = la mutation PV via `FillUpStatComponent.FillUp @180f9b2e0` :
        `healed = Min(amount, CurrentMaximumValue - current)` ; `current += healed` ; rend `healed`.
    (`get_CurrentMaximumValue @180f9c010` = plafond courant ; ici on lit `HealthComponent.hp_max`
    deja resolu, MEME source que le cap overkill `MaxReduceByMinimum` cote degat.) Gate heal-block
    `EffectType.Cursed`(79).

    NON porte (documente, secondaire pour la fidelite d'ETAT PV — le coeur = la mutation PV) :
    l'EVENT `UnitHealed` (`FUN_18001cd40(2, DAT_1831e5000, ...)` dict health/source/members), les
    triggers post-heal (`FUN_180028e70(0x51, ...)`), le member-fill statistique et
    `ActorStatisticsComponent.AddRestoreHealthAction`. A ajouter si un trigger consomme le heal.
    """
    __slots__ = ()

    @staticmethod
    def execute(state: "State", target_id: int, heal_amount: int,
                source_id: Optional[int] = None) -> int:
        """Soigne `target_id` de `heal_amount` PV (plafonne a `hp_max`). Rend le montant REELLEMENT
        soigne (0 si deja plein / Cursed / cible sans PV) — pour le chaining lifesteal."""
        amount = int(heal_amount)
        if amount <= 0:
            return 0
        # GATE heal-block EffectType.Cursed(79) : HasEffect(target, 0x4f) -> soin annule (healed=0).
        if state.effects is not None and state.effects.has_effect(target_id, effect_type=CURSED):
            return 0
        tgt = state.get_entity(target_id)
        thc = tgt.get_component(HealthComponent) if tgt is not None else None
        if thc is None or thc.hp is None or thc.hp_max is None:
            return 0
        # FillUp @180f9b2e0 : healed = Min(amount, max - cur) ; cur += healed.
        healed = min(amount, int(thc.hp_max) - int(thc.hp))
        if healed <= 0:
            return 0
        thc.hp = int(thc.hp) + healed
        return healed
