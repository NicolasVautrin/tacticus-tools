"""`Abilities.Triggered.Loki.ArcaneShieldAbility` (@180e16f60) — bouclier de Thaumachus (`thousSorcerer`,
ThousandSons, passive `ArcaneShield`). Cf. `loki/__init__.py` pour le regroupement « Loki »."""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import StatsComponent, OwnerComponent, UnitComponent
from ....abilities.behaviours import CreateShield, entities_from_state
from .....entities.traits import UnitTrait, has_trait
from .....entities.selectors import Target
from .....entities.effects.magnitude import ability_var
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent, _unit_tile, _hex_dist, _faction_id

# Grand-alliance « Chaos » (cf. GrandAlliance) — 5 factions Chaos des 22 du jeu (priorité de ciblage
# ArcaneShield : ThousandSons > autres Chaos > autres > soi). Stable (lore WH40K).
CHAOS_FACTIONS = frozenset({
    "BlackLegion", "DeathGuard", "ThousandSons", "WorldEaters", "EmperorsChildren",
})
ARCANESHIELD_RANGE = 2          # `ArcaneShield.constants.range` = 2 (rayon de l'ami ciblé)
ARCANESHIELD_TRAIT_EXCLUDE = UnitTrait.Steppable  # `UnitsWithoutTrait(0x1b=27=Steppable)` : exclus du ciblage.
# ⚠ FIX #135 : etait `0x1b` (int) compare a `ctx.traits` (NOMS gameconfig) -> `27 in [strings]` toujours False
#   (gate mort : les allies Steppable/tokens etaient ciblables a tort). Gate desormais via `has_trait` (#146 :
#   mapping id<->nom centralise dans UnitTrait -> plus de comparaison int-vs-str possible).


def _arcaneshield_target(state: State, owner_id: int) -> int:
    """`SurroundingFriends(range, sans trait 0x1b) → SortByFormula(faction, distance) → First(1)` sinon
    soi. Priorité : même faction (ThousandSons) > autre Chaos > autre > soi ; tie-break distance puis id.
    Sans board (pas d'adjacence) → soi."""
    board = state.board
    owner = state.get_entity(owner_id)
    if board is None or owner is None:
        return owner_id
    oc = owner.get_component(OwnerComponent)
    ot = _unit_tile(state, board, owner_id)
    if oc is None or ot is None:
        return owner_id
    own_fac = _faction_id(state, owner_id)
    cands: list[tuple[int, int, int]] = []
    for eid, e in state.entities.items():
        if eid == owner_id:
            continue
        c = e.get_component(OwnerComponent)
        u = e.get_component(UnitComponent)
        if c is None or c.team != oc.team:               # amis uniquement
            continue
        if u is not None and not u.alive:
            continue
        sc = e.get_component(StatsComponent)
        if sc is not None and has_trait(sc.ctx.traits, ARCANESHIELD_TRAIT_EXCLUDE):  # UnitsWithoutTrait(0x1b)
            continue
        t = _unit_tile(state, board, eid)
        if t is None:
            continue
        d = _hex_dist(board, ot, t, ARCANESHIELD_RANGE)  # dans le rayon
        if d is None:
            continue
        fac = _faction_id(state, eid)
        prio = 0 if (own_fac is not None and fac == own_fac) else (1 if fac in CHAOS_FACTIONS else 2)
        cands.append((prio, d, eid))
    if cands:
        cands.sort()                                     # (priorité, distance, id)
        return cands[0][2]
    return owner_id                                      # « lastly casting it on himself »


def _arcaneshield_grant(state: State, owner_id: int) -> Optional[dict]:
    """Behaviour ArcaneShield (CreateBehaviour@180e16b40), MIGRÉ en ARBRE DSL (#149 slice-23) :
    `CreateShield(<best>, ConfigVar(0x27=shieldHp), self.Id, TurnsFromRounds(1))`. Le montant
    `shieldHp[passive_level] × mult%` (formule V `ConfigVar`) est calculé IMPÉRATIVEMENT (`ability_var`)
    et passé comme scalaire ; le sélecteur AI-target LOURD (S) reste `_arcaneshield_target`, COLLAPSÉ en
    `Target()` (== FinalJustice, doctrine slice-18/19). Bit-exact vs l'ancien corps impératif BY
    CONSTRUCTION : la feuille `CreateShield` appelle le MÊME `ShieldComponent.add_or_update_shield(amount,
    "ArcaneShield", remaining=1)`. No-op si amount<=0 (stats/config absents)."""
    owner = state.get_entity(owner_id)
    sc = owner.get_component(StatsComponent) if owner is not None else None
    if sc is None:
        return None
    ctx = sc.ctx
    amount = int(ability_var("ArcaneShield", "shieldHp", int(getattr(ctx, "passive_ability_level", 0) or 0),
                             multiplier_pct=int(getattr(ctx, "ability_variables_multiplier", 100) or 100)) or 0)
    if amount <= 0:
        return None
    target = _arcaneshield_target(state, owner_id)
    if state.get_entity(target) is None:
        return None
    ectx = ExecutionContext(state=state, rng=state.rng)
    # #98 : le 4e arg natif est `TurnsFromRounds(1)` (CreateBehaviour @180e16b40) -> la duree du
    # BOUCLIER passe elle aussi par `BattleQuery.ConvertRoundsToTurns @181058af0`. Le decay est
    # `RemoveOneTurnOnShields @180e6c4e0` (1 par EndTurn) = MEME cadence que le tick d'effets.
    from ....abilities.base import convert_rounds_to_turns
    dur = convert_rounds_to_turns(state, 1)
    CreateShield(Target(), amount, duration=dur, source="ArcaneShield").execute(  # TurnsFromRounds(1)
        entities_from_state(state, owner_id, target), ectx)
    p = next((p for (n, p) in ectx.emitted if n == "CreateShield"), None)
    if p is None:
        return None
    return {"ability": "ArcaneShield", "owner": owner_id, "target": target, "amount": amount,
            "remaining": dur, "shield_total": p.get("shield_total")}


class ArcaneShieldAbility(TriggeredAbility):
    """`ArcaneShieldAbility` (@180e16f60 CreateTrigger / @180e16b40 CreateBehaviour) — bouclier de
    Thaumachus (`thousSorcerer`, ThousandSons, passive `ArcaneShield`).

    Natif : `CreateTrigger = On(0x1c) & OwnerIsActor & OwnerIsCaster` — `0x1c` = activation TERMINÉE de
    l'owner (APRÈS son move, OU fin de tour s'il ne bouge pas). Behaviour = accorde un bouclier `shieldHp`
    (variable rareté → `× AbilityVariablesMultiplier`) durée **1 round** à l'ami le plus proche dans le
    rayon (`range`=2 ; `UnitsWithoutTrait(0x1b)`), préféré ThousandSons > autres Chaos > autres > **soi**
    (sinon soi) → `CreateShield` (`AddOrUpdateShield`).

    ⚠ APPROXIMATION du VECTEUR : le runner n'a pas d'event « activation terminée » (0x1c). On le modélise
    sur le vecteur **after-move** (`On(4)`) quand le MOVER EST l'owner (= cas « après son move », le plus
    courant). Le cas « fin de tour sans déplacement » n'est pas couvert (raffinement = vecteur 0x1c propre
    avec la boucle d'activation). La sélection multi-amis (priorité faction) est portée mais validée
    seulement sur le cas SOLO (target = soi). Behaviour/cible = `_arcaneshield_grant`/`_arcaneshield_target`."""
    event_id = EventTriggerType.UnitAfterMove

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id != self.owner_id:                 # OwnerIsActor : l'owner vient de bouger
            return False
        owner = state.get_entity(self.owner_id)
        uc = owner.get_component(UnitComponent) if owner is not None else None
        if uc is not None and not uc.alive:
            return False
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return _arcaneshield_grant(state, self.owner_id)
