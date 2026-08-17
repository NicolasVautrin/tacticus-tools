"""LivingMetal (UnitTrait 1000, tout le roster Necron : 41 npc + 6 lineup + 4 summons) -- regen
% des PV au debut du tour du proprietaire (#203).

Kit natif -- l'ability triggered `LivingMetalRepair` (TriggeredAbilityType 0x3f2=1010) accordee
par le trait LivingMetal ; DEUX arbres DSLFactory (mirror STRUCTURE, pas les noms gshared) :

- `IdunBattleLogic.Entities.Abilities.Active.Loki.LivingMetalRepairAbility$$CreateTrigger` =
      OwnerIsActor(@0xa0) & On(TurnStart_Other=0x13=19) & IsDamaged(self)
  * `On(TurnStart_Other=19)` = 2e des 5 events emis par `IdunBattle.Operations.StartTurnOperation$$Execute`
    (sequence FUN_1800280e0(..,0x12->0x13->0x14->0x15->0x16) ; 0x16=TurnStart_Actions). Le meme
    event 0x13 porte FirstAid (tiles.py). Vecteur porte = `turn_start_other_triggers` (dispatch.py).
  * `@0xa0` (`IdunBattleLogic.Entities.DSLTriggers$$InitializeShared`, ctor gshared) = scoping "le proprietaire est
    le joueur ENTRANT" -- PROUVE live (probe_203) : la regen ne fire QU'AU tour du proprietaire
    (delta 0 au tour adverse). Porte ici = `ev.player_id == OwnerComponent.player`.
  * `IsDamaged(self)` (`IdunBattleLogic.Entities.DSLTriggers$$IsDamaged`) = `Not(UnitsWithStatEqualToTrigger(self,
    HEALTH=5, part MISSING=4, Direct(0)@factory+0xb8))` = missing HP > 0 = HP courant < HP max.
    (Le dispatch gate deja owner VIVANT -> une unite MORTE ne regen pas : pas d'auto-resurrection,
    conforme au decompile -- LivingMetalRepairAbility n'est PAS fire_on_death.)
- `IdunBattleLogic.Entities.Abilities.Active.Loki.LivingMetalRepairAbility$$CreateBehaviour` =
      Repair(source=self, target=self,
             amount = PercentageOf(StatAmount(self, HEALTH=5, MAXIMUM=2)=maxHP,
                                   Direct(GetNumberConstant(0x12))),
             cause = AbilityOrEffect(LivingMetalRepair 0x3f2), options = ForRegenerate)
  * `IdunBattle.Entities.Formulas.PercentageOf$$CalculateInternal` + `IdunBattle.DSL.AAmountFormula$$RoundFix64Result` (mode 0 =
    `Fix64.Round`, round-half-to-even) => **amount = round_half_even(maxHP * pct / 100)**. `pct` =
    `GetNumberConstant(0x12)` = trait var gameconfig `livingMetalHp` = 10 -> **regen = 10% du maxHP**.
  * `IdunBattle.Entities.Behaviours.RepairBehaviour$$Execute` -> `IdunBattle.Operations.RepairUnitOperation$$Execute`
    (`operations/repair.py`) -- pas `HealUnitOperation`, cf. « LE MUTATEUR » ci-dessous.

LE MUTATEUR : `RepairUnitOperation`, PAS `HealUnitOperation` (#310). Jusqu'a #310 ce trigger appelait
`HealUnitOperation` : l'etat PV bougeait bien (les deux Operations finissent sur le MEME
`FillUpStatComponent$$FillUp`), mais les TROIS etages propres a la reparation etaient court-circuites,
et les deux Operations natives ne sont PAS interchangeables. Les ecarts, lus au decompile :

  * gate `IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired` (surcharge 5 arguments, relue
    verbatim sur `rnca9r7q6c`) = `!EntityExtensions.IsMachine(entity) & (IsDamagedUnit(entity) ||
    (removeEffects && HasNegativeUnitEffect(entity)) || (caster != null && HasFlag(caster, 0x18))) &
    !UnitExtensions.HasHealBlockers(entity) & UnitExtensions.IsAffectedByHealType(entity, 1)`, puis
    `if (scope == 0) return true; return !IsAtGroupUnitHealLimit(entity);`.
    ⚠ SUR CE CHEMIN LE GATE EST TAUTOLOGIQUE, et il faut le dire plutot que de le vendre comme un
    verrou : la cible est le PORTEUR lui-meme (`Repair(self, self, ...)`), or
    `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType(unit, 1)` = `HasTrait(0x421
    AffectedByHealAndRepair) || IsMechanical(unit)` et `IdunBattle.Entities.UnitExtensions$$IsMechanical`
    = `HasTrait(Mechanical 5) || HasTrait(LivingMetal 1000) || HasTrait(Vehicle 0x405)`. **Porter
    LivingMetal, c'est etre Mechanical** -> le disjunct passe TOUJOURS. `IsMachine` (Machine of War)
    ne mord pas non plus : `python unit_map.py find --trait LivingMetal` rend 52 porteurs (41 npc,
    6 lineup, 4 summons, 1 tuto), AUCUNE MoW. Et `IsDamagedUnit` est deja garanti par le
    `IsDamaged(self)` du `CreateTrigger`. Le gate est donc porte pour rester isomorphe, pas parce
    qu'un montage saurait le faire refuser ;
  * `RepairModifier` de `IdunBattle.Core.Services.DamagePrediction$$PredictRepair`, gate `IsActor` :
    les bonus de reparation RECUS par la cible s'appliquent -- `NanoscarabRepairProtocolsEffect`
    (1545, `+hpToRepair`, pose par `necroReanimator` sur ses allies Mechanical, donc sur les Necrons
    porteurs de LivingMetal) et `VoltagheistField_RepairReductionEffect` (1382, `x(1 - healthPct/100)`).
    Passer par `HealUnitOperation` les IGNORAIT tous : c'est l'ecart CHIFFRE de ce bug ;
  * gate `EffectType.Cursed` (79), et il joue A L'ENVERS. `IdunBattle.Operations.HealUnitOperation$$Execute`
    fait `EntityExtensions.HasEffect(entity, 0x4f)` et force le montant a 0 ;
    `RepairUnitOperation$$Execute` **n'a pas ce test** (son seul equivalent est
    `UnitExtensions$$HasHealBlockers` = `HealthComponent+0x78`, un dict DISTINCT -- aucune classe
    `CursedEffect` n'existe dans le build, l'EffectType 79 n'est lu QUE par le heal). L'ancien port
    REFUSAIT donc une regen que le natif accorde : une degradation RESTRICTIVE, l'inverse du sens
    habituel, et c'est elle qui rend le bug testable ;
  * `scope`/`removeEffects` = `IdunBattle.Entities.Behaviours.RepairBehaviourOptions$$ForRegenerate`
    = `(+0x10 = 1, +0x14 = 0)`. `scope == 1` arme l'etage cap-de-GROUPE de `PredictRepair`
    (`Min(amount, GetGroupUnitHealLimit)`) -- LivingMetal est le SEUL call-site `ForRegenerate` du
    build, donc le seul a l'armer. Ce cap etait deja porte, mais RE-ECRIT ICI et applique AVANT le
    `RepairModifier` : il est desormais dans `predict_repair`, a sa place native (apres).

Face COMBAT uniquement (la regen dans les ops turn-start du runner). Aucune face DECISION/PREDICTION
consommatrice.

Mesure live (probe_203_livingmetal.py) : maxHP 30000 -> +3000 au tour du proprietaire (NON cape),
0 au tour adverse (scoping), cape a maxHP, stop a PV pleins (IsDamaged). Swarm `necroSmnSwarm` : le
cap de groupe rend LivingMetal INERTE a une frontiere de membre (probe_203_swarm.py).
"""
from __future__ import annotations

from typing import Optional

from .....dsl.event_trigger_type import EventTriggerType
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....state import State
from ....components import HealthComponent, OwnerComponent
from ..base import TriggeredAbility, TriggerEvent
from ...repair import RepairUnitOperation

LIVING_METAL_TRAIT = "LivingMetal"
LIVING_METAL_HP_VAR = "livingMetalHp"      # trait var gameconfig (=10, %) -> `GetNumberConstant(0x12)`

# `IdunBattle.Entities.Behaviours.RepairBehaviourOptions$$ForRegenerate` : les DEUX champs qu'elle
# ecrit (`+0x10 = 1` = scope, `+0x14 = 0` = removeEffects), transcrits tels quels.
#
# ⚠ CORRECTION #317 -- ce commentaire disait « LivingMetal est le SEUL call-site `ForRegenerate` du
# build, les 12 autres passent `$$ForRepair` ». C'est FAUX, mesure re-derivee des 13 appelants de
# `IdunBattleLogic.Entities.DSLBehaviors$$Repair` (`probe_317_repair_callers_inventory.py`) :
#   * `IdunBattle.Entities.Effects.Loki.LifeStealEffect$$CreateTargetTriggerBehaviour` passe lui
#     aussi `$$ForRegenerate` ;
#   * DEUX appelants n'appellent AUCUNE fabrique -- ils ecrivent les champs a la main apres
#     `IdunBattle.Entities.Behaviours.RepairBehaviourOptions$$.ctor` :
#     `...Triggered.Loki.EnhancementRegenerationAbility$$CreateBehaviour` pose `+0x10 = 1` (scope,
#     donc le cap de GROUPE) / `+0x14 = 0` / `+0x15 = 1` / `+0x18 = 1`, et
#     `...Triggered.Loki.PowerUp_HealingAbility$$AdditionalBehavior` pose `+0x10 = 0` / `+0x14 = 1`
#     / `+0x16 = 1`.
# ⇒ **TROIS** call-sites arment `scope == 1`, pas un. Aucun des deux autres n'est porte cote COMBAT
# (tranches ouvertes, cf. `docs/rl/case-317-repair-callers-inventory.md`), donc l'etage cap-de-GROUPE
# de `predict_repair` n'a toujours qu'UN consommateur porte -- mais ce n'est plus le seul du BUILD.
REGENERATE_SCOPE = 1
REGENERATE_REMOVE_EFFECTS = False

#: `cause = AbilityOrEffect(LivingMetalRepair 0x3f2)`, le 4e argument que
#: `...LivingMetalRepairAbility$$CreateBehaviour` passe a `IdunBattleLogic.Entities.DSLBehaviors$$
#: Repair`. PORTE depuis #908 : c'est ce que lit le gate `TriggeringAbilityIs` du descripteur
#: `RepairBonus` de `NetherRealmCasket_LivingMetalBonusEffect` (1456) -- le seul du build.
REPAIR_CAUSE = int(TriggeredAbilityType.LivingMetalRepair)      # 0x3f2 = 1010


def living_metal_pct() -> int:
    """`GetNumberConstant(config, 0x12)` = le pourcentage de regen, source gameconfig = trait var
    `livingMetalHp` (=10, flat -- pas de courbe par niveau : la valeur est un scalaire). Fallback 10."""
    import gameconfig as GC
    v = (GC.trait(LIVING_METAL_TRAIT).get("variables") or {}).get(LIVING_METAL_HP_VAR)
    return int(v) if v is not None else 10


def _round_half_even(x: float) -> int:
    """`IdunBattle.DSL.AAmountFormula$$RoundFix64Result` mode 0 = `FixMath.NET.Fix64$$Round` = round-half-to-even (banker's).
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
        # #149 : la FEUILLE (ce behaviour) calcule le montant declaratif et APPELLE l'Operation
        # imperative ; elle ne re-ecrit aucun de ses etages. Frontiere = le `.Execute` de la feuille.
        e = state.get_entity(self.owner_id)
        hc = e.get_component(HealthComponent) if e is not None else None
        if hc is None or hc.hp_max is None:
            return None
        pct = living_metal_pct()
        # amount = PercentageOf(StatAmount(self, HEALTH, MAXIMUM)=maxHP, Direct(pct)) round-half-even.
        amount = _round_half_even(int(hc.hp_max) * pct / 100)
        # `Repair(mechanic = self, selector = self, amount, cause, options = ForRegenerate)` :
        # `mechanic` (le REPARATEUR) et la cible sont le MEME `Owner@0x30` au decompile -> caster et
        # target = `self.owner_id`. `ForRegenerate` -> `scope = 1` (cap de GROUPE arme dans
        # `predict_repair`, cf. son etage (2)) et `removeEffects = 0`.
        #
        # `cause` = `AbilityOrEffect(LivingMetalRepair 0x3f2)`, le 4e argument de
        # `IdunBattleLogic.Entities.DSLBehaviors$$Repair` au decompile de `...LivingMetalRepair
        # Ability$$CreateBehaviour`. Il etait CONSTRUIT par le natif et JETE par le port : c'est ce
        # canal (`RepairBehaviour+0x68` -> `RepairUnitOperation$$Execute` -> `PredictRepair` ->
        # `CalculateRepairModifierForPrediction`) que lit le gate `TriggeringAbilityIs` du
        # descripteur `NetherRealmCasket_LivingMetalBonusEffect$$CreateEffectRepairBonus`. C'est le
        # SEUL call-site du build qui peut le satisfaire -- d'ou #908.
        repaired = RepairUnitOperation.execute(state, self.owner_id, self.owner_id, amount,
                                               scope=REGENERATE_SCOPE,
                                               remove_effects=REGENERATE_REMOVE_EFFECTS,
                                               ability_or_effect=REPAIR_CAUSE)
        if repaired <= 0:
            return None
        return {"type": "living_metal_repair", "unit": int(self.owner_id),
                "amount": amount, "repaired": repaired, "pct": pct}
