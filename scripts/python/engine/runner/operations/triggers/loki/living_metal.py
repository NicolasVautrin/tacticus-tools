"""LivingMetal (UnitTrait 1000, tout le roster Necron : 41 npc + 6 lineup + 4 summons) -- regen
% des PV au debut du tour du proprietaire (#203).

Kit natif -- l'ability triggered `LivingMetalRepair` (TriggeredAbilityType 0x3f2=1010) accordee
par le trait LivingMetal ; DEUX arbres DSLFactory (mirror STRUCTURE, pas les noms gshared) :

- `LivingMetalRepairAbility.CreateTrigger @181222630` =
      OwnerIsActor(@0xa0) & On(TurnStart_Other=0x13=19) & IsDamaged(self)
  * `On(TurnStart_Other=19)` = 2e des 5 events emis par `StartTurnOperation.Execute @180ea3fb0`
    (sequence FUN_180026490(..,0x12->0x13->0x14->0x15->0x16) ; 0x16=TurnStart_Actions). Le meme
    event 0x13 porte FirstAid (tiles.py). Vecteur porte = `turn_start_other_triggers` (dispatch.py).
  * `@0xa0` (`DSLFactory.InitializeShared @180df2670`, ctor gshared) = scoping "le proprietaire est
    le joueur ENTRANT" -- PROUVE live (probe_203) : la regen ne fire QU'AU tour du proprietaire
    (delta 0 au tour adverse). Porte ici = `ev.player_id == OwnerComponent.player`.
  * `IsDamaged(self)` (`DSLFactory.IsDamaged @180df32e0`) = `Not(UnitsWithStatEqualToTrigger(self,
    HEALTH=5, part MISSING=4, Direct(0)@factory+0xb8))` = missing HP > 0 = HP courant < HP max.
    (Le dispatch gate deja owner VIVANT -> une unite MORTE ne regen pas : pas d'auto-resurrection,
    conforme au decompile -- LivingMetalRepairAbility n'est PAS fire_on_death.)
- `LivingMetalRepairAbility.CreateBehaviour @1812224e0` =
      Repair(source=self, target=self,
             amount = PercentageOf(StatAmount(self, HEALTH=5, MAXIMUM=2)=maxHP,
                                   Direct(GetNumberConstant(0x12))),
             cause = AbilityOrEffect(LivingMetalRepair 0x3f2), options = ForRegenerate)
  * `PercentageOf.CalculateInternal @180f20fc0` + `RoundFix64Result @180ffa110` (mode 0 =
    `Fix64.Round`, round-half-to-even) => **amount = round_half_even(maxHP * pct / 100)**. `pct` =
    `GetNumberConstant(0x12)` = trait var gameconfig `livingMetalHp` = 10 -> **regen = 10% du maxHP**.
  * `RepairBehaviour.Execute @180fce990` -> `RepairUnitOperation.Execute @180e8b820` ->
    `FillUpStatComponent.FillUp` (cape a maxHealth). Gate `EntityCanBeRepaired @181055080` =
    `!IsMachine & IsDamaged & !HasHealBlockers & IsAffectedByHealType(1)` ; `IsAffectedByHealType(1)
    @180ed77d0` = IsMechanical (TOUS les porteurs LivingMetal sont Mechanical -> gate toujours vraie)
    & `!HasHealBlockers @180ed6810` (dict heal-blockers, ou vit Cursed). Pas de group-heal-cap sur le
    repair (case-60 : le repair REVIVE les membres de swarm).

Face COMBAT uniquement (la regen dans les ops turn-start du runner). Aucune face DECISION/PREDICTION
consommatrice : l'effet 1456 `NetherRealmCasket_LivingMetalBonus` est documente INERTE sur le chemin
Repair/Galvanic (predict.py, case-34).

Port du mutateur = `HealUnitOperation` (meme `FillUpStatComponent.FillUp` : cape maxHP + gate heal-block
Cursed + re-derivation swarm via `on_group_unit_hp_changed`). Mesure live (probe_203_livingmetal.py) :
maxHP 30000 -> +3000 au tour du proprietaire (NON cape), 0 au tour adverse (scoping), cape a maxHP,
stop a PV pleins (IsDamaged). Swarm `necroSmnSwarm` : la remontee de PV re-derive les membres vivants
(case-60, 444->1775 = ~6 ticks de 10%).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.event_trigger_type import EventTriggerType
from .....services.trait_damage_limits import get_group_unit_heal_limit
from ....state import State
from ....components import HealthComponent, OwnerComponent, StatsComponent
from ..base import TriggeredAbility, TriggerEvent

LIVING_METAL_TRAIT = "LivingMetal"
LIVING_METAL_HP_VAR = "livingMetalHp"      # trait var gameconfig (=10, %) -> `GetNumberConstant(0x12)`


def living_metal_pct() -> int:
    """`GetNumberConstant(config, 0x12)` = le pourcentage de regen, source gameconfig = trait var
    `livingMetalHp` (=10, flat -- pas de courbe par niveau : la valeur est un scalaire). Fallback 10."""
    import gameconfig as GC
    v = (GC.trait(LIVING_METAL_TRAIT).get("variables") or {}).get(LIVING_METAL_HP_VAR)
    return int(v) if v is not None else 10


def _round_half_even(x: float) -> int:
    """`RoundFix64Result @180ffa110` mode 0 = `Fix64.Round @1815636e0` = round-half-to-even (banker's).
    Python `round()` est banker's -> identique (Fix64 fixed-point, ecarts a l'exact-.5 non observes sur
    les maxHP bornes du jeu)."""
    return int(round(x))


class LivingMetalRepairAbility(TriggeredAbility):
    """`LivingMetalRepairAbility` (triggered 0x3f2=1010, trait LivingMetal) -- cf. en-tete de module.
    `On(TurnStart_Other=19) & OwnerIsActor & IsDamaged(self)` -> `Repair(self, round(10% maxHP))`."""
    event_id = int(EventTriggerType.TurnStart_Other)      # On(0x13=19)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        e = state.get_entity(self.owner_id)
        if e is None:
            return False
        # OwnerIsActor(@0xa0) : la regen ne fire qu'au debut du tour du PROPRIETAIRE (prouve live).
        oc = e.get_component(OwnerComponent)
        if oc is None or ev.player_id is None or oc.player != int(ev.player_id):
            return False
        # IsDamaged(self) : missing HP > 0 (HP courant < HP max).
        hc = e.get_component(HealthComponent)
        if hc is None or hc.hp is None or hc.hp_max is None:
            return False
        return int(hc.hp) < int(hc.hp_max)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        from ...heal import HealUnitOperation      # lazy : primitive de soin runner (cape maxHP + swarm)
        e = state.get_entity(self.owner_id)
        hc = e.get_component(HealthComponent) if e is not None else None
        if hc is None or hc.hp_max is None:
            return None
        pct = living_metal_pct()
        # amount = PercentageOf(StatAmount(self, HEALTH, MAXIMUM)=maxHP, Direct(pct)) round-half-even.
        amount = _round_half_even(int(hc.hp_max) * pct / 100)
        # GROUP-UNIT (swarm) : `ForRegenerate` (+0x10=1,+0x14=0 @180fce8c0) = repair "NO-WAKE" -> le montant
        # est cape au `get_group_unit_heal_limit @1810325e0` (= maxHealthWith(membres RESTANTS) - hp = ce
        # qu'on peut soigner SANS reveiller de membre mort), DISTINCT de `ForRepair` (+0x14=1 @180fce920,
        # ex. admecManipulus Repair_GalvanicField) qui REVEILLE des membres. Les membres d'un swarm
        # member-cape sont TOUJOURS pleins a une frontiere -> heal-limit 0 -> et 10% du maxHP (222 pour un
        # scarab 2218/5) < 1 membre (444) => LivingMetal est INERTE sur le swarm (PROUVE live probe_203_swarm :
        # scarab bloque a 888/2218). Le "444->1775 revive" de case-60 etait admecManipulus (ForRepair),
        # MAL attribue a LivingMetal. Single unit (member_count<2) -> get_group_unit_heal_limit = int.MaxValue
        # (pas de cap) -> heal les 10% pleins (necroWarden : +3000 valide).
        sc = e.get_component(StatsComponent)
        n = int(getattr(sc.ctx, "number_of_members", 1) or 1) if (sc is not None and sc.ctx is not None) else 1
        if n >= 2:
            amount = min(amount, get_group_unit_heal_limit(int(hc.hp_max), n, int(hc.hp)))
        if amount <= 0:
            return None
        healed = HealUnitOperation.execute(state, self.owner_id, amount, source_id=self.owner_id)
        if healed <= 0:
            return None
        return {"type": "living_metal_repair", "unit": int(self.owner_id),
                "amount": amount, "healed": healed, "pct": pct}
