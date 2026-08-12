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
from ...predict import calculate_repair_modifier_for_prediction
from ...predict import repair_amount as _repair_amount
from ...services.trait_damage_limits import get_group_unit_heal_limit
from ..components import unit_state_for_effects
from .fill_up_prediction import group_unit_members as _group_unit_members
from .fill_up_prediction import is_boss as _is_boss

if TYPE_CHECKING:
    from ..state import State


def _repair_modifier(state: "State", target_id: int, ability_or_effect=None) -> tuple:
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

    RESIDU LEVE PAR #908 -- il etait **ATTEIGNABLE**, et il est desormais ATTEINT. Le 3e
    implementeur `NetherRealmCasket_LivingMetalBonusEffect` (1456) est le SEUL dont le gate
    `TriggeringAbilityIs(LivingMetalRepair)` PEUT etre satisfait ici -- depuis #310 le trigger
    LivingMetal passe bien par cette Operation, donc la face COMBAT est le seul chemin ou ce bonus
    vaut autre chose que 0.
    #310 l'avait classe DEAD sur `python unit_map.py find --ability NetherRealmCasket` = **0 unite**.
    Ce zero etait un FAUX NEGATIF : `unit_map find --ability` ne lisait que `activeAbilities` +
    `passiveAbilities`, il etait **aveugle aux RELIQUES** -- **CORRIGE par #323** (5 voies lues,
    la commande rend desormais 18 porteurs ; cf. `docs/rl/case-323-unit-map-attribution-voies.md`).
    `NetherRealmCasket` est l'ability de l'item
    `R_Booster_Crit_NetherRealmCasket`, `allowedUnits = [necroWarden, necroSpyder, necroDestroyer]`
    -- TROIS heros DU POOL -- et `necroSpyder` (traits `Hero`/`LivingMetal`/`Mechanical`/`Mechanic`)
    la porte DEJA EQUIPEE dans le seed BC courant (`Units[].TertiaryAbility = 1462`).
    Des DEUX canaux que #317 nommait comme manquants, il reste UN :
      * `ability_or_effect` -- la CAUSE que le gate du descripteur consomme : **PORTE (#908)**, du
        `RepairBehaviour+0x68` jusqu'ici, en mirror du 5e argument `source` de
        `IdunBattle.Core.Services.RepairCalculations$$CalculateRepairModifierForPrediction` ;
      * le kit declenche REEL d'une unite (traits + reliques) n'est PAS expose au rail COMBAT --
        `collect_triggered_abilities` derive du gameconfig ; la lecture fidele
        (`engine/ai/context.py::live_triggered_ability_ids`, RPC `unitAbilityStates`) n'existe que
        cote DECISION ; gap deja mesure par `probe_193_move_playbook_inventory.py` volet 2. TOUJOURS
        OUVERT -- mais il ne bloque PAS ce bonus-ci : l'EFFET 1456 arrive dans l'etat du port par la
        CAPTURE (`state.effects`), pas par le registre d'abilities.
    Detail et re-derivation : `docs/rl/case-317-repair-callers-inventory.md` par. 1.

    `ability_or_effect` = un ordinal `TriggeredAbilityType`, ou `None` = cause NON THREADEE (le gate
    rend alors FAUX -- jamais permissif). Le niveau du bonus est resolu par le foyer UNIQUE
    `runner/operations/triggers/base.py::triggered_ability_state` (#357), sans quoi une relique de
    niveau 1 lirait le dernier palier de `hpToHeal`.

    Rend `(mod_add, mod_mul)`. Aucun effet contributeur -> `(0, 1.0)` = no-op EXACT (`Empty`)."""
    if state.effects is None or target_id is None:
        return 0, 1.0
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

    def _ability_state(ability_name):
        """`GetAbilityState(effect)` du PORTEUR de l'effet -- et le porteur EST la cible, puisque
        `get_OwnerIsTarget` est ce qui a laisse passer l'effet dans `rows`. Delegue au foyer UNIQUE
        `triggered_ability_state` (#357) : etat TERTIAIRE pour une relique EQUIPEE, PASSIF sinon."""
        from .triggers.base import triggered_ability_state
        return triggered_ability_state(state, int(target_id), ability_name)

    return calculate_repair_modifier_for_prediction(rows, heal_config=_cfg,
                                                    ability_or_effect=ability_or_effect,
                                                    ability_state_of=_ability_state)


def predict_repair(state: "State", caster_id, target_id: int, amount: int,
                   scope: int = 0, ability_or_effect=None) -> int:
    """`IdunBattle.Core.Services.DamagePrediction$$PredictRepair` -> son champ `fillUp` (le HIGH dword
    du `CONCAT44(MaxFillUp(...), GetStat(target, Health))` que le natif renvoie).

    Le champ LOW (`currentHealth`) n'est PAS rendu : cote EXECUTION il n'a aucun consommateur (c'est
    la face PREDICTION qui le lit, `engine.predict.RepairPrediction`). Etages, dans l'ORDRE natif :

      1. `RepairModifier`, GATE par `IsActor(caster)` -- un caster non-acteur (tuile, effet) laisse
         `amount` intact ;
      2. cap de GROUPE `GetGroupUnitHealLimit`, GATE par `scope == 1` -- PORTE depuis #310, quand
         `LivingMetalRepairAbility` a ete rebranche sur cette Operation. C'est le seul call-site
         PORTE a armer `scope 1` ; ce n'est PAS le seul du BUILD (correction #317 : les deux autres
         sont `IdunBattle.Entities.Effects.Loki.LifeStealEffect$$CreateTargetTriggerBehaviour`, via
         `$$ForRegenerate`, et `...Triggered.Loki.EnhancementRegenerationAbility$$CreateBehaviour`,
         via un `RepairBehaviourOptions` construit a la main -- aucun des deux n'est porte).
         Avant #310 la branche etait inerte (`ForRepair` = `scope 0` partout) ET le cap etait
         re-calcule A LA MAIN dans le trigger, AVANT le `RepairModifier` -- donc dans le MAUVAIS
         ORDRE. Il est desormais a sa place native : `Min(amount, GetGroupUnitHealLimit)` APRES le
         modifier ;
      3. cap BOSS `GetStat(Health, Initial) - current`, gate `IsBoss(target)` ;
      4. `MaxFillUp` = `Min(amount, CurrentMaximumValue - current)`.

    `ability_or_effect` (#908) = le 6e argument natif de `PredictRepair`, relaye tel quel au 5e
    (`source`) de `CalculateRepairModifierForPrediction`. ⚠ **`PredictHeal` NE LE PORTE PAS** -- les
    deux `Predict*` ne sont PAS jumeaux sur ce point, et c'est LU au decompile :
    `IdunBattle.Core.Services.DamagePrediction$$PredictHeal(this, caster, casterTile, target,
    amount, scope)` construit son `AbilityEntities` INLINE, sans champ de cause, tandis que
    `PredictRepair` passe le sien a `CalculateRepairModifierForPrediction`. Cf.
    `tests/engine/test_520_heal_pipeline_offline.py`, qui garde cette asymetrie."""
    from ..abilities.targeting import is_actor
    e = state.get_entity(int(target_id))
    hc = e.get_component(HealthComponent) if e is not None else None
    if hc is None or hc.hp is None or hc.hp_max is None:
        return 0
    amt = int(amount)
    if caster_id is not None and is_actor(state, int(caster_id)):
        mod_add, mod_mul = _repair_modifier(state, int(target_id),
                                            ability_or_effect=ability_or_effect)
        amt = _repair_amount(amt, mod_add, mod_mul)
    cur, mx = int(hc.hp), int(hc.hp_max)
    # (2) `if (scope == 1) predicted = Min(predicted, GetGroupUnitHealLimit(target, health))` :
    #     le cap « ce qu'on peut restaurer SANS REVEILLER de membre mort » d'une unite multi-membres.
    #     `GetGroupUnitHealLimit` rend `int.MaxValue` a `nrOfMembers < 2` (heros) -> `Min` no-op,
    #     exactement comme le natif : la branche est prise, elle ne mord simplement pas.
    if int(scope) == 1:
        amt = min(amt, get_group_unit_heal_limit(mx, _group_unit_members(state, int(target_id)),
                                                 cur))
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
        Le SEUL consommateur porte de `On(48 = UnitRepaired)` est le stat-mod EXTRA_HITS du trait `Swarm`
        (`IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateTrigger`), deja cable
        par l'appel direct a `on_group_unit_hp_changed` ci-dessous -- MEME raccourci que
        `HealUnitOperation`, et deja valide live (`probe_203_swarm.py`)."""
    __slots__ = ()

    @staticmethod
    def execute(state: "State", caster_id, target_id: int, amount: int,
                scope: int = 0, remove_effects: bool = False, ability_or_effect=None) -> int:
        """Repare `target_id` et rend le montant REELLEMENT restaure (0 si le gate refuse, si la
        cible est deja pleine, ou si ses PV ne sont pas lisibles).

        `scope` / `remove_effects` = `RepairBehaviourOptions+0x10` / `+0x14`, ecrits par
        `IdunBattle.Entities.Behaviours.RepairBehaviourOptions$$ForRepair` (= `0` / `1`) ou
        `$$ForRegenerate` (= `1` / `0`) -- ce sont les deux SEULES fabriques du build (relues
        verbatim sur `rnca9r7q6c` : `ForRegenerate` ecrit `+0x10 = 1` puis `+0x14 = 0`, `ForRepair`
        l'inverse).

        `ability_or_effect` = `RepairBehaviour+0x68` (`source`), le SEPTIEME argument natif -- celui
        que Ghidra ne nomme pas parce qu'il arrive sur la PILE (`in_stack_00000040`), et que le
        decompile montre recopie en 0x1c octets avant l'appel a `PredictRepair`. Il n'a qu'UN
        consommateur porte, le gate `TriggeringAbilityIs` du descripteur
        `NetherRealmCasket_LivingMetalBonusEffect$$CreateEffectRepairBonus` (#908) ; les vecteurs de
        trigger `On(0x30)` / `On(0x1e)` qui le lisent aussi cote natif ne sont pas modelises.
        ⚠ Ghidra DECALE la signature de cette fonction d'un cran (son 1er parametre est le buffer
        de retour `OperationResult`, son `caster` est l'Operation elle-meme, et ce qu'il nomme
        `source` est en realite `removeEffects`) -- meme piege que `HealUnitOperation$$Execute`,
        deja documente dans `heal.py`. La lecture ci-dessus est celle des ARGUMENTS REELS,
        recoupee par le call-site `RepairBehaviour$$Execute`.

        SOUS `scope == 1`, le gate natif prend une CONDITION DE PLUS : `if (scope == 0) return true;
        return !AttackQuery.IsAtGroupUnitHealLimit(entity);`. Cote port
        `attack_query.is_at_group_unit_heal_limit` est un stub `False` (residu NOMME la-bas), donc le
        gate laisse passer. CONSEQUENCE CHIFFREE : **nulle sur l'etat PV**, et ce n'est pas une
        indulgence -- `IsAtGroupUnitHealLimit` est, terme a terme, `GetGroupUnitHealLimit <= 0` (les
        deux natifs calculent le MEME `GetGroupUnitMaxHealthWithRemainingMembers`, l'un le compare a
        `currentHealth`, l'autre l'en soustrait). L'etage (2) de `predict_repair` rend donc
        `predicted <= 0` exactement quand le gate aurait refuse -> `filled <= 0` -> `return 0`, sans
        mutation ni trigger. Le seul ecart residuel serait un `OperationResult` non vide, que le port
        n'expose pas."""
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
        predicted = predict_repair(state, caster_id, int(target_id), int(amount), scope=int(scope),
                                   ability_or_effect=ability_or_effect)
        # `FillUpStatComponent$$FillUp` : `filled = Min(amount, CurrentMaximumValue - current)` ;
        # `current += filled` ; le champ `+0x24` (over-reduce) est remis a 0. PORTE depuis
        # #462-r4e-o-r2 via le foyer unique `HealthComponent.fill_up` -- appele AVANT la sortie
        # anticipee, comme le natif (son `if (filled < 1 && shieldPart < 1 && !HasFlag(target, 0x18))
        # return;` est APRES le `FillUp`).
        filled = hc.fill_up(int(predicted))
        if filled <= 0:
            return 0
        # `On(UnitRepaired = 0x30)` -> bras `On(UnitRepaired=48)` du trait `Swarm` : la remontee de PV
        # REVEILLE des membres, donc le malus EXTRA_HITS doit etre re-evalue (cf. `heal.py`, #60).
        from ..abilities.loki.swarm import on_group_unit_hp_changed
        on_group_unit_hp_changed(state, int(target_id))
        # `processor.<slot 0x51>(caster, caster, target, 0x30 UnitRepaired, ...)` -- le vecteur
        # GENERIQUE, ajoute par #964-r1. Il n'existait pas : la docstring ci-dessus le nommait comme
        # non porte, au motif qu'un seul consommateur existait et qu'il etait court-circuite. Ce
        # n'est plus vrai (`ECogSupportAbility$$CreateTrigger`), et le raccourci `Swarm` ci-dessus
        # n'est PAS double (le trait n'a pas d'entree `event_id == 48` dans `TRAIT_TRIGGERS`).
        # Place FIDELE : apres la mutation et apres le gate de sortie anticipee.
        from .triggers.dispatch import repair as _repair_dispatch   # lazy : cycle repair<->triggers
        _repair_dispatch.unit_repaired_triggers(state, caster_id, int(target_id))
        return filled
