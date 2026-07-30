"""Operation de REPARATION — `IdunBattle.Operations.RepairUnitOperation$$Execute` (#299).

Mutateur ECS de la reparation, JUMEAU du soin (`operations/heal.py`) mais **pas son alias** : le
natif a deux Operations distinctes, et celle-ci porte TROIS etages que le soin n'a pas (le gate
`EntityCanBeRepaired`, le `RepairModifier` de la CIBLE, les caps `scope`/boss de `PredictRepair`).

POURQUOI CE MODULE EXISTE (residu #299 sorti de #298). Le rail de DECISION de la reparation etait
complet -- `28 Repair` / `1119 Repair_GalvanicField` etaient enumerees, ciblees, predites, choisies
par l'IA -- et la face COMBAT etait un **NO-OP** : ni `28` ni `1119` n'etaient dans
`ABILITY_CLASSES`, donc `AbilityHandler` posait les flags de tour et rendait `ported: False`. Le cast
etait ACCEPTE, le tour CONSOMME, et **zero PV restaure**. Aucune erreur, aucun crash : exactement la
degradation silencieuse que la doctrine « DECIDER != EXECUTER » nomme.

CHAINE NATIVE (decompile = verite), du behaviour jusqu'a la mutation :

    IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$CreateBehaviour
      -> IdunBattleLogic.Entities.DSLBehaviors$$Repair(mechanic, selector, amount, source, options)
      -> IdunBattle.Entities.Behaviours.RepairBehaviour$$Execute
           mechanic = SelectSingle(+0x50)         # le REPARATEUR (`Caster`)
           foreach target in Select(+0x58) :      # les cibles
               amount = (+0x60).Calculate(entities)
               processor.<slot 0x58>(mechanic, target, amount,
                                     options.scope@+0x10, options.removeEffects@+0x14,
                                     source@+0x68)
      -> Core.Services.OperationProcessor$$RepairUnit         (caller MINCE, aucune logique)
      -> IdunBattle.Operations.RepairUnitOperation$$Execute   <-- CE MODULE

`RepairUnitOperation$$Execute` (MIRROR, lu verbatim) :

    if (!attackQuery.<slot 0x12>(caster, target, scope, removeEffects)) return {};   # EntityCanBeRepaired
    fillUp = target.GetComponent<FillUpStatComponent>(Health)
    casterPos = EntityExtensions.GetUnitPosition(caster, state)
    pred = damagePrediction.<slot 2>(caster, target, casterPos, amount, scope, abilityOrEffect)
                                                                     # = DamagePrediction$$PredictRepair
    repaired = FillUpStatComponent.FillUp(fillUp, pred.fillUp)       # <-- LA MUTATION
    processor.<slot 0x5c>(target)
    if (removeEffects) cleansed = processor.<slot 0x5b>(target, ...)
    if (repaired < 1 && cleansed < 1 && !HasFlag(target, 0x18)) return {}
    result.repaired += repaired ; <statistiques> ; <event UnitRepaired> ;
    processor.<slot 0x51>(caster, caster, target, 0x30 UnitRepaired, ...)
    if (repaired > 0) processor.<slot 0x51>(target, target, target, 0x1e, ...)

`IdunBattle.Core.Services.DamagePrediction$$PredictRepair` (MIRROR) :

    predicted = amount
    if (EntityExtensions.IsActor(caster)) {
        mod = repairCalculations.<slot 0>(caster, target, casterPos, source)
                                          # = RepairCalculations$$CalculateRepairModifierForPrediction
        predicted = (int)( Fix64((int)mod.flatBonus + amount) * mod.multiplier )
    }
    health = UnitExtensions.GetStat(target, 5 Health, 0 Current)
    if (scope == 1) predicted = Min(predicted, GetGroupUnitHealLimit(target, health))
    if (UnitExtensions.IsBoss(target))
        predicted = Min(predicted, GetStat(target, 5 Health, 3 Initial) - health)
    return CONCAT44( FillUpStatComponent.MaxFillUp(fillUp, predicted), health )

et `FillUp` / `MaxFillUp` sont le MEME `Min(amount, CurrentMaximumValue - current)` : `MaxFillUp` le
CALCULE, `FillUp` l'APPLIQUE. La composition `FillUp(MaxFillUp(x))` du chemin natif se reduit donc a
`Min(x, max - current)` -- une seule saturation, pas deux.

ASCII only (console cp1252).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..components import HealthComponent, StatsComponent

if TYPE_CHECKING:
    from ..state import State


def _repair_modifier(state: "State", target_id: int) -> tuple:
    """`IdunBattle.Core.Services.RepairCalculations$$CalculateRepairModifierForPrediction` cote RUNNER.

    Le natif part de `IdunBattle.Core.Services.RepairModifier$$Empty` = `{multiplier = Fix64.One,
    flatBonus = 0}` puis FOLD, via les deux surcharges d'`IdunBattle.Core.Services.RepairModifier$$Add`,
    les descripteurs `IdunBattle.Entities.Effects.BaseEffect$$RepairBonus` de TOUS les
    `EffectComponent` du combat -- la condition `OwnerIsTarget` du descripteur ne laisse passer que
    les effets PORTES PAR LA CIBLE (bonus sur reparations RECUES). D'ou la lecture des seuls effets
    de `target_id`.

    La REGLE elle-meme (quels EffectType contribuent, add vs pct) n'est pas re-ecrite ici : elle vit
    deja dans `engine.predict.calculate_repair_modifier_for_prediction` (RE #45d, les 3 SEULS
    implementeurs du build : `NanoscarabRepairProtocolsEffect` 1545 ForAddition,
    `VoltagheistField_RepairReductionEffect` 1382 ForPercentDecrease,
    `NetherRealmCasket_LivingMetalBonusEffect` 1456 gate `TriggeringAbilityIs(LivingMetalRepair)`).
    Ce helper n'en est que l'ADAPTATEUR de substrat : il convertit les instances `BaseEffect` du
    runner au format `{name, level, source}` que cette fonction consomme. Une seule lecture du natif,
    deux substrats -- surtout pas deux tables.

    Rend `(mod_add, mod_mul)`. Aucun effet contributeur -> `(0, 1.0)` = no-op EXACT (`Empty`)."""
    from ...predict import calculate_repair_modifier_for_prediction
    if state.effects is None or target_id is None:
        return 0, 1.0
    from ..components import unit_state_for_effects
    try:
        effs = state.effects.active_effects(int(target_id),
                                            unit_state_for_effects(state, int(target_id)))
    except Exception:                                  # pragma: no cover - substrat sans vue d'etat
        effs = state.effects.by_unit.get(int(target_id), [])
    rows = [{"name": getattr(e, "name", None), "level": getattr(e, "level", None),
             "source": getattr(e, "source", None)} for e in (effs or [])]

    def _cfg(uid):
        """`heal_config(source)` = `{multiplier}` du POSEUR de l'effet (scaling rarete de sa var)."""
        e = state.get_entity(int(uid)) if uid is not None else None
        sc = e.get_component(StatsComponent) if e is not None else None
        mult = getattr(sc.ctx, "ability_variables_multiplier", 100) if sc is not None else 100
        return {"multiplier": int(mult or 100)}

    return calculate_repair_modifier_for_prediction(rows, heal_config=_cfg)


def _is_boss(state: "State", unit_id: int) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsBoss` -- NON PORTE, et le decompile dit POURQUOI :

        TryGetComponent<UnitComponent>(unit, out c) && *(byte*)(c + 0x88)

    Ce n'est PAS `HasTrait(Boss)` (l'erreur naturelle : `UnitTrait.Boss` existe et vaut 2023) mais un
    CHAMP du `UnitComponent`, qu'aucun canal de seed du runner n'expose (`components.UnitComponent`
    n'a pas d'attribut boss -- et tous les appelants de `predict.repair_utility` passent deja
    `is_boss=False`). Rendu `False` = le cap boss de `PredictRepair` ne s'applique jamais.

    CONSEQUENCE CHIFFREE, et elle est nulle sur le substrat runner : le cap boss vaut
    `GetStat(Health, Initial) - current`, tandis que l'etage SUIVANT (`MaxFillUp`) cape a
    `CurrentMaximumValue - current`. Le canal offline n'expose qu'UN SEUL plafond (`hp_max`), donc
    les deux bornes s'y confondent -- meme argument, mot pour mot, que la branche BOSS d'
    `attack_query.is_damaged_unit`. Un port qui INVENTERAIT `Initial != hp_max` fabriquerait un cap
    la ou le natif n'en met pas."""
    return False


def predict_repair(state: "State", caster_id, target_id: int, amount: int,
                   scope: int = 0) -> int:
    """`IdunBattle.Core.Services.DamagePrediction$$PredictRepair` -> son champ `fillUp` (le HIGH dword
    du `CONCAT44(MaxFillUp(...), GetStat(target, Health))` que le natif renvoie).

    Le champ LOW (`currentHealth`) n'est PAS rendu : cote EXECUTION il n'a aucun consommateur (c'est
    la face PREDICTION qui le lit, `engine.predict.RepairPrediction`). Etages, dans l'ORDRE natif :

      1. `RepairModifier`, GATE par `IsActor(caster)` -- un caster non-acteur (tuile, effet) laisse
         `amount` intact ;
      2. cap de GROUPE `GetGroupUnitHealLimit`, GATE par `scope == 1` : NON PORTE (le cap « sans
         reveiller de membre » vit dans `services/trait_damage_limits.py` et demande le detail des
         membres, absent du substrat runner). Tous les call-sites portes passent
         `RepairBehaviourOptions.ForRepair` -> `scope = 0` -> la branche est INERTE ;
      3. cap BOSS `GetStat(Health, Initial) - current`, gate `IsBoss(target)` ;
      4. `MaxFillUp` = `Min(amount, CurrentMaximumValue - current)`."""
    from ..abilities.targeting import is_actor
    from ...predict import repair_amount as _repair_amount
    e = state.get_entity(int(target_id))
    hc = e.get_component(HealthComponent) if e is not None else None
    if hc is None or hc.hp is None or hc.hp_max is None:
        return 0
    amt = int(amount)
    if caster_id is not None and is_actor(state, int(caster_id)):
        mod_add, mod_mul = _repair_modifier(state, int(target_id))
        amt = _repair_amount(amt, mod_add, mod_mul)
    cur, mx = int(hc.hp), int(hc.hp_max)
    # (2) `scope == 1` -> cap de groupe : NON PORTE (aucun call-site porte n'arme ce scope).
    # (3) cap BOSS : `_is_boss` rend toujours False (champ `UnitComponent+0x88` hors substrat, cf.
    #     sa docstring) -- la branche est ecrite pour rester isomorphe au natif, jamais inventee.
    _ = _is_boss(state, int(target_id))
    return max(0, min(amt, mx - cur))                         # (4) MaxFillUp


class RepairUnitOperation:
    """`IdunBattle.Operations.RepairUnitOperation$$Execute` (caller mince
    `Core.Services.OperationProcessor$$RepairUnit`).

    Impératif par DOCTRINE (#149) : c'est un mutateur ECS, pas un arbre DSL. La feuille DSL qui
    l'appelle est `runner/abilities/behaviours/stats.py::Repair`
    (`IdunBattleLogic.Entities.DSLBehaviors$$Repair` -> `RepairBehaviour$$Execute`).

    NON PORTE (nomme, secondaire pour la fidelite d'ETAT PV) :
      * le volet `removeEffects` (`processor.<slot 0x5b>`, purge des effets negatifs de la cible) :
        `RepairBehaviourOptions$$ForRepair` pose bien `removeEffects = 1`, mais le port n'a pas de
        marqueur « effet negatif » (meme trou que `attack_query.has_negative_unit_effect`, NOMME
        la-bas). Consequence CHIFFREE : `cleansed` vaut toujours 0 cote port, donc un cast qui ne
        restaure AUCUN PV et ne fait que purger rend `repaired = 0` des deux cotes -- l'ecart ne
        porte que sur les effets purges, jamais sur les PV ;
      * l'EVENT `UnitRepaired` (dict health/shield/members) et les statistiques
        (`ActorStatisticsComponent$$AddRestoreHealthAction`, compteurs `+0xcc/+0xd0/+0xe0/+0xe4`) ;
      * les vecteurs de trigger `processor.<slot 0x51>` `On(0x30 = 48 UnitRepaired)` et `On(0x1e)`.
        Le SEUL consommateur porte de `On(48)` est le stat-mod EXTRA_HITS du trait `Swarm`
        (`IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateTrigger`), deja cable
        par l'appel direct a `on_group_unit_hp_changed` ci-dessous -- MEME raccourci que
        `HealUnitOperation`, et deja valide live (`probe_203_swarm.py`)."""
    __slots__ = ()

    @staticmethod
    def execute(state: "State", caster_id, target_id: int, amount: int,
                scope: int = 0, remove_effects: bool = False) -> int:
        """Repare `target_id` et rend le montant REELLEMENT restaure (0 si le gate refuse, si la
        cible est deja pleine, ou si ses PV ne sont pas lisibles).

        `scope` / `remove_effects` = `RepairBehaviourOptions+0x10` / `+0x14`, ecrits par
        `IdunBattle.Entities.Behaviours.RepairBehaviourOptions$$ForRepair` (= `0` / `1`) ou
        `$$ForRegenerate` (= `1` / `0`) -- ce sont les deux SEULES fabriques du build."""
        from ..abilities.attack_query import entity_can_be_repaired
        if target_id is None:
            return 0
        # GATE `attackQuery.<slot 0x12>` = `IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired`
        # (surcharge 5 arguments, caster en tete) -- mirror deja porte, cf. `abilities/attack_query.py`.
        # Le natif sort ICI sur un `OperationResult` VIDE : aucune mutation, aucun event, aucun trigger.
        if not entity_can_be_repaired(state, caster_id, int(target_id),
                                      scope=int(scope), remove_effects=bool(remove_effects)):
            return 0
        e = state.get_entity(int(target_id))
        hc = e.get_component(HealthComponent) if e is not None else None
        if hc is None or hc.hp is None or hc.hp_max is None:
            return 0
        predicted = predict_repair(state, caster_id, int(target_id), int(amount), scope=int(scope))
        # `FillUpStatComponent$$FillUp` : `filled = Min(amount, CurrentMaximumValue - current)` ;
        # `current += filled` ; le champ `+0x24` (over-reduce) est remis a 0 -- pas de pendant porte.
        filled = min(int(predicted), int(hc.hp_max) - int(hc.hp))
        if filled <= 0:
            return 0
        hc.hp = int(hc.hp) + filled
        # `On(UnitRepaired = 0x30)` -> bras `On(UnitRepaired=48)` du trait `Swarm` : la remontee de PV
        # REVEILLE des membres, donc le malus EXTRA_HITS doit etre re-evalue (cf. `heal.py`, #60).
        from ..abilities.loki.swarm import on_group_unit_hp_changed
        on_group_unit_hp_changed(state, int(target_id))
        return filled
