"""Operation de SOIN — `IdunBattle.Operations.HealUnitOperation$$IdunBattle.Operations.HealUnitOperation$$Execute`.

Mutateur ECS inverse du degat : remonte les PV d'une cible, plafonne a `hp_max` (FillUp).
KEYSTONE de la categorie HEAL/REPAIR/lifesteal du runner combat (cf.
`docs/rl/combat-ability-coverage.md`, tache #94) : SpiritLeech lifesteal, MassHeal (8), Repair (28),
Repair_GalvanicField (1119), etc. delegueront ici pour muter les PV cote EXECUTION (le runner no-op-ait
SILENCIEUSEMENT ces abilities, cf. doctrine CLAUDE.md "DECIDER != EXECUTER").
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ..components import HealthComponent
from ...entities.effect_type import EffectType

if TYPE_CHECKING:
    from ..state import State

# EffectType.Cursed (79) — GATE heal-block. `HealUnitOperation$$IdunBattle.Operations.HealUnitOperation$$Execute` fait
# `EntityExtensions.HasEffect(target, Cursed)` : si l'effet est present, le montant de soin est force
# a 0 (branche `if ((char)param_6 == '\0') healAmount = computed;` sinon healAmount reste 0). #158.
CURSED = int(EffectType.Cursed)


class HealUnitOperation:
    """`IdunBattle.Operations.HealUnitOperation$$IdunBattle.Operations.HealUnitOperation$$Execute` (caller mince
    `Core.Services.OperationProcessor$$Core.Services.OperationProcessor$$HealUnit`).

    Coeur = la mutation PV via `IdunBattle.Entities.Components.FillUpStatComponent$$FillUp` :
        `healed = Min(amount, CurrentMaximumValue - current)` ; `current += healed` ; rend `healed`.
    (`IdunBattle.Entities.Components.FillUpStatComponent$$get_CurrentMaximumValue` = plafond courant ; ici on lit `HealthComponent.hp_max`
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
        tgt = state.get_entity(target_id)
        thc = tgt.get_component(HealthComponent) if tgt is not None else None
        if thc is None or thc.hp is None or thc.hp_max is None:
            return 0
        # GATE heal-block EffectType.Cursed(79) : HasEffect(target, 0x4f). Le natif n'en fait PAS une
        # sortie anticipee -- il calcule `healAmount = cursed ? 0 : predicted` et appelle `FillUp`
        # AVEC 0 (#462-r4e-o-r2). La difference est observable : `FillUp` purge `over_reduce` en
        # queue, inconditionnellement. Sortir ici laisserait l'accumulateur intact a tort.
        if state.effects is not None and state.effects.has_effect(target_id, effect_type=CURSED):
            amount = 0
        # `IdunBattle.Entities.Components.FillUpStatComponent$$FillUp` : healed = Min(amount, max - cur) ;
        # cur += healed ; `+0x24 = 0`. FOYER UNIQUE (`HealthComponent.fill_up`) -- appele AVANT toute
        # sortie anticipee, comme le natif (son early-return `healed < 1` est APRES le `FillUp`).
        healed = thc.fill_up(amount)
        if healed <= 0:
            return 0
        # #60 : bras `On(UnitHealed=43) & OwnerIsTarget` (+ `On(UnitRepaired=48)`, le repair HP passant
        # par ce meme mutateur) du `IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateTrigger` — re-evalue le stat-mod
        # EXTRA_HITS du trait Swarm apres la remontee de PV (des membres reviennent -> malus reduit).
        from ..abilities.loki.swarm import on_group_unit_hp_changed
        on_group_unit_hp_changed(state, target_id)
        return healed
