"""SwarmAbility (trait **Swarm**, ability 0x3ff=1023) — malus EXTRA_HITS dynamique du swarm (#60).

i2 : « For each member defeated, the swarm attacks with 1 fewer hit. »

Natif (DSL, mirror noeud a noeud) :
  * `SwarmAbility.CreateBehaviour @181225e20` =
        AddOrUpdateStaticStatModifierEffect(Self@+0x148, effectType 0x3fd=1021 Swarm_HitReduction,
            statType 0x11=EXTRA_HITS,
            Negative(Min(Difference(StatAmount(Self, 20, part 3=INITIAL), Const1@factory+0xc0),
                         StatAmount(Self, 20, part 4=MISSING))))
    = **-min(nrOfMembers - 1, membres MORTS)** (plancher structurel : jamais moins de 1 hit).
  * `SwarmAbility.CreateTrigger @181225f50` =
        (On(UnitRepaired=49,1) | On(UnitHealed=44,1) | On(UnitMemberDeath=48,0) | On(UnitRevived=46,1))
        & OwnerIsTarget  |  OnOwnerSpecificAbilityInit(0x3ff=1023)
    — exactement les evenements qui changent le compte de membres du porteur.
  * Stat 20 (NUMBER_OF_MEMBERS) : handler jumptable 0x14 de `GetStat @180ed30d0` (bloc @180ed3929) →
    `GetComponent<GroupUnitComponent>` (fill-up {+0x10=nrOfMembers, +0x18=membres restants}) puis
    `FillUpStatComponent.GetStatPart @180f9b3a0`. Offline le champ « courant » est DERIVE de l'etat PV
    (`group_unit_stat_part`, services/trait_damage_limits.py) — meme invariant, les mainteneurs natifs
    etant exactement les evenements PV ci-dessus.

Port offline :
  * L'ARBRE VALEUR est un vrai arbre DSL (noeuds `StatAmount`/`Difference`/`Min`/`Negative`/`Const`),
    evalue via `entities_from_state` (ctx.get_stat → branche stat 20). La logique EMERGE des noeuds.
  * Le TRIGGER est rendu par les points de mutation PV du runner (chaque call-site annote son bras
    natif) : le montant ne depend que de l'etat PV du porteur → recalculer a chaque mutation PV est
    IDEMPOTENT sur l'etat (AddOrUpdate re-poste la meme valeur hors franchissement de seuil de membre).
  * AddOrUpdate = `revert + change_stat` sous la cle partagee `SWARM_HIT_REDUCTION_SOURCE` (mirror
    Reverse+Apply de l'update d'un effet statique ; `ValueModification.Modify(*, 0)` natif est un no-op
    → le passage a 0 (membres tous revives) passe par le revert). La meme cle est posee par
    l'attribution d'hydratation (`UnitContext.from_snapshot`) → le 1er refresh REMPLACE, jamais de
    double-compte.
"""
from __future__ import annotations

from ....dsl.base import Const
from ....entities.formulas import Difference, Min, Negative, StatAmount
from ....entities.selectors import Caster
from ....entities.stats import StatPart, StatType
from ....entities.effects.loki.hits import SWARM_HIT_REDUCTION_SOURCE
from ...components import HealthComponent, StatsComponent, UnitComponent


def swarm_hit_reduction_formula() -> Negative:
    """Arbre VALEUR de `SwarmAbility.CreateBehaviour @181225e20` (mirror noeud a noeud).
    `Caster()` = le selecteur Self (`factory+0x148` — sur un behaviour de trait Owner==Caster)."""
    self_sel = Caster()
    return Negative(Min(
        Difference(StatAmount(self_sel, int(StatType.NUMBER_OF_MEMBERS), int(StatPart.INITIAL)),
                   Const(1)),
        StatAmount(self_sel, int(StatType.NUMBER_OF_MEMBERS), int(StatPart.MISSING))))


def refresh_swarm_hit_reduction(state, unit_id: int) -> None:
    """`AddOrUpdateStaticStatModifierEffect(Self, 0x3fd, EXTRA_HITS, formule)` — le behaviour de
    SwarmAbility, execute apres une mutation PV du porteur. No-op rapide si l'unite n'est pas un swarm
    vivant (gate = trait Swarm & nrOfMembers>1, mirror : l'ability 1023 n'existe que via le trait)."""
    e = state.get_entity(unit_id) if unit_id is not None else None
    if e is None:
        return
    uc = e.get_component(UnitComponent)
    if uc is not None and not uc.alive:
        return
    sc = e.get_component(StatsComponent)
    ctx = sc.ctx if sc is not None else None
    if ctx is None or "Swarm" not in (ctx.traits or []) or int(getattr(ctx, "number_of_members", 1)) < 2:
        return
    us = getattr(ctx, "stats", None)
    if us is None:
        return
    from ..behaviours import entities_from_state
    entities = entities_from_state(state, caster_id=int(unit_id))
    amount = int(swarm_hit_reduction_formula().evaluate(entities))
    # AddOrUpdate : Reverse+Apply sous LA cle partagee (Modify(*,0) natif = no-op → revert explicite).
    us.revert_stat(StatType.EXTRA_HITS, SWARM_HIT_REDUCTION_SOURCE)
    if amount != 0:
        us.change_stat(StatType.EXTRA_HITS, SWARM_HIT_REDUCTION_SOURCE, amount)


def on_group_unit_hp_changed(state, unit_id: int) -> None:
    """Point d'entree des call-sites de mutation PV (damage/heal/resurrect) — chaque call-site annote
    le bras natif du `CreateTrigger @181225f50` qu'il rend. Alias mince de `refresh` (le montant ne
    depend que de l'etat PV courant)."""
    refresh_swarm_hit_reduction(state, unit_id)
