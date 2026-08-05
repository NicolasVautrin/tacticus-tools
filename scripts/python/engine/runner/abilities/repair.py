"""Abilities de REPARATION REGULIERE — `28 Repair` et `1119 Repair_GalvanicField` (#299).

Module DEDIE et NON factionnel, a dessein : `28 Repair` n'appartient a aucune faction. C'est une
ability **DERIVEE D'UN TRAIT** — `IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities`
appelle `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetActiveAbility`
sur le trait `Mechanic`, et pousse le resultat dans `ActiveAbilityComponent$$Add`. Ses porteurs
traversent cinq factions (`admecDominus`, `admecManipulus`, `necroSpyder`, `orksBigMek`,
`votanIronmaster`), donc la ranger dans `admec.py` serait FAUX. `1119` la specialise (passif
`GalvanicField` d'`admecManipulus`) et HERITE d'elle au binaire — d'ou les deux classes ici.

COROLLAIRE A RETENIR (#298) : `28` est ABSENTE des `abilities` du gameconfig. Ce n'est PAS la preuve
qu'elle est dormante — c'est la signature d'une ability derivee. L'inventaire l'avait classee
« dormante » a tort ; `admecDominus` la porte en bataille.

`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsRegularRepair`
= EXACTEMENT `{0x1c = 28, 0x45f = 1119}` (lu au decompile ; `NanoscarabRepairProtocols` 1224 n'en
fait PAS partie). C'est le meme couple que `REGULAR_REPAIR_IDS` de la fixture `_repair_stage`.

------------------------------------------------------------------------------------------------
`IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$CreateBehaviour` (MIRROR du decompile) :

    mechanic = <bundle@0x90>+0x48                                  # `Caster`
    selector = <bundle@0x90>+0x60                                  # `ActiveTarget` (la cible du cast)
    amount   = this.<vtable +0x4b8>()                              # = `RepairAbility$$RepairAmount`
    source   = AbilityOrEffect.op_Implicit(this)
    options  = RepairBehaviourOptions.ForRepair()                  # scope 0, removeEffects 1
    return DSLBehaviors.Repair(mechanic, selector, amount, source, options)

(le slot `+0x4b8` est celui qui SUIT `CreateBehaviour` `+0x4a8` dans la vtable, cf.
`ADeprecatedActiveAbility$$ExecuteBehaviour` qui appelle `+0x4a8` ; son corps est
`IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$RepairAmount`.)

`IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$RepairAmount` :

    Multiply( StatAmount(Caster, 0 = ATTACK, 0 = Current),
              Max( WeaponHighestHits(Caster), Get(1) ) )

— exactement l'arbre d'`HealAbility$$HealAmount`, et exactement le texte i2 du trait `Mechanic`
(« The amount of Health restored equals the Mechanic's Damage multiplied by the highest number of
hits of any of their weapons »). Deja porte et CONFRONTE LIVE cote prediction
(`engine.predict.repair_amount_weapon`, #45d) -> on le REUTILISE, on ne le re-derive pas.

`IdunBattleLogic.Entities.Abilities.Active.Loki.Repair_GalvanicFieldAbility$$CreateBehaviour` :

    return RepairAbility.CreateBehaviour(this, state)
           & CreateAttackBehavior(dsl, actingUnits = <selector@0x60> - <mechanic@0x48>)

et `...$$CreateAttackBehavior` :

    affected = DSLSelectors.UnitsAffectedByHealType(actingUnits, 1 = Mechanical)
    node     = PercentageOfAttackCappedAtMax(Subject, 3 = Initial,
                                             ConfigVar(0x4af = 1199 GalvanicField, 0xd  maxDmg),
                                             ConfigVar(0x4af = 1199 GalvanicField, 0x4a dmgPct))
    return ( AddStatOverrideEffect(affected, 0x4da = 1242 GalvanicField_DmgOverride,
                                   0 = ATTACK, node, duree 0, modifiable 1)
           & PerformAIAttackFromCurrentPosition(affected, <abilityState@0x30>, 0, false) )
           & RemoveEffect(affected, Nullable(0x4da), 0)

— la machine REPAREE attaque immediatement, avec son Attack OVERRIDE par la formule du passif, puis
l'override est retire (net-zero). MEME patron, feuille pour feuille, que
`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$GetTriggerAttackBehaviour`
(`abilities/loki/quickening.py`), qui est le gabarit deja valide live de ce triptyque.

⚠ `CreateAttackBehavior` prend le **`dsl`** en `this`, pas l'ability : c'est une FONCTION du dsl, et
elle a DEUX appelants natifs. Le port la sort donc de la classe (`galvanic_field_attack_behavior`,
plus bas), parametree par l'`actingUnits` de chaque call-site :
  * `Repair_GalvanicFieldAbility$$CreateBehaviour` (1119) : `<Target@0x60> - <Caster@0x48>` ;
  * `IdunBattleLogic.Entities.Abilities.Active.Loki.DefendTheDivineWorkAbility$$ExecuteBehaviour`
    (1117, MEME porteur `admecManipulus`, porte par #334 dans `abilities/admec.py`) :
    `Friends(Caster@0x48, AdjacentUnits(CasterTile@0x50, 1, 3))` -- les amis adjacents, SANS le
    caster. Detail et desassemblage : `docs/rl/case-334-defend-the-divine-work.md`.

RESIDU NOMME, MESURE (case-299 §5, inventaire N20) -- `FabricatorClawArray`, le PASSIF du
`necroSpyder` (3e porteur du trait `Mechanic`), n'est PAS porte :

    FabricatorClawArrayAbility$$CreateTrigger
        = On(0x1c = ArrivedAtFinalTile) & OwnerIsActor & !AmountIsZero(GetTargetSelector())
    FabricatorClawArrayAbility$$CreateBehaviour
        = Repair(Owner, GetTargetSelector(), Direct(ConfigVar(0x24 = hpToRepair)), ForRepair)

Tout cast d'active TERMINE le tour (`AddFlagsAfterAbilityExecution` -> `FinishUnitTurnOperation` ->
`UnitFlags.Add(ArrivedAtFinalTile)`) : le Spyder qui repare restaure donc `RepairAmount` PUIS
`hpToRepair[level]`. MESURE sans saturation : natif 10457, port 6025, ecart 4432 = `hpToRepair[50]
2216 x multiplier 200 %` -- entierement explique. C'est une ability PASSIVE, hors perimetre de ce
module ; la garde qui la CHIFFRE est
`tests/engine/runner/test_repair_execution_live.py::test_necro_spyder_hits_factor_and_fabricator_claw_residue`.

ASCII only (console cp1252).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.effects import ExecutionContext
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.formulas import percentage_of_attack_capped_at_max
from ...entities.selectors import Caster, Sub, Subject, Target
from ...entities.stats import StatPart, StatType
from .base import ActiveAbility
from .behaviours import AddStatOverrideEffect, RemoveEffect, Repair, entities_from_state
from .targeting import (RANGE_ADJACENT, RANGED_BOOL_IF_RANGED_CASTER, TargetingOptions)
from .targeting_rule import TargetingRule as TR
from ...entities.effects.magnitude import ability_var
from ...entities.selectors import UnitSet
from ...entities.selectors import UnitsAffectedByHealType
from ...predict import repair_amount_weapon
from ..components import StatsComponent
from .targeting import (_resolves_to_unit, units_are_enemies,
                                valid_normal_attack_targets)
from .targeting import _resolves_to_unit, units_are_enemies

if TYPE_CHECKING:
    from ...dsl.base import TargetsSelector
    from ..state import State

# `idun...StaticBattleRules.ActiveAbility$$IsRegularRepair` : les DEUX seules valeurs comparees.
REGULAR_REPAIR_IDS = (int(ActiveAbilityType.Repair),                    # 0x1c  = 28
                      int(ActiveAbilityType.Repair_GalvanicField))     # 0x45f = 1119

# `AddStatOverrideEffect(..., 0x4da, ...)` / `RemoveEffect(..., Nullable(0x4da), ...)` du volet
# ATTAQUE de 1119 : l'override d'Attack que porte la machine reparee, le temps de son coup gratuit.
GALVANIC_DMG_OVERRIDE = int(EffectType.GalvanicField_DmgOverride)      # 0x4da = 1242

# `ConfigVar(0x4af, ...)` : `0x4af` = 1199 = `TriggeredAbilityType.GalvanicField`, le PASSIF qui
# accorde 1119. Ses deux variables (indices `0xd` maxDmg / `0x4a` dmgPct) s'indexent donc sur le
# niveau PASSIF du caster -- MEME resolution que la face DECISION (`ai/action_generators.py`).
GALVANIC_CONFIG = "GalvanicField"

# `TargetingOptions` COMMUNES aux deux abilities, lues sur
# `IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$.ctor` -- FORME 1 « FLAGS DIRECTS »
# (verifiee : la surcharge appelee est `TargetingOptions..ctor(this, isSelfCasting, range,
# forceMeleeTarget, rules, getDynamicInvalidCasterReason, getDynamicInvalidTargetReason)`, celle qui
# ECRIT `rules` telle quelle a `options+0x28` -- ni preset combine, ni copie statique) :
#
#   TargetingOptions..ctor(&opts, 0, &<TargetingRange statics>+0x30, 2, 0x8002, 0, 0)
#     isSelfCasting    = 0
#     range            = `TargetingRange` statics+0x30 = RANGE_ADJACENT (onlyAdjacent + overrideRange 1)
#     forceMeleeTarget = 2 = RangedBool.IfRangedCaster
#     rules            = 0x8002 = CasterIsPossibleTarget | TargetMatchesDynamicRule
#   puis `ADeprecatedActiveAbility..ctor(this, &opts, 2)` -> `AActiveAbility..ctor(..., 2)`.
#
# Le masque ne porte AUCUNE regle de camp ni de domaine : tout le refus vit dans la regle DYNAMIQUE
# (bit 1), d'ou l'importance de `get_dynamic_invalid_target_reason` ci-dessous. `CasterIsPossibleTarget`
# (bit 15) n'est pas une regle de refus mais une LECTURE du masque (le reparateur peut se cibler
# lui-meme), cf. l'inventaire en tete d'`abilities/targeting.py`.
# ⚠ `Repair_GalvanicFieldAbility$$.ctor` ne fait QUE `return RepairAbility..ctor(this)` : meme masque,
# meme range, meme forceMeleeTarget, meme `AbilityAttackType`. Herite, pas recopie a l'aveugle.
REPAIR_TARGETING_OPTIONS = TargetingOptions(
    rules=TR.CasterIsPossibleTarget | TR.TargetMatchesDynamicRule,
    self_cast=False, range=RANGE_ADJACENT,
    force_melee_target=RANGED_BOOL_IF_RANGED_CASTER)


def repair_amount(state: "State", caster_id: int) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$RepairAmount` =
    `Multiply(StatAmount(Caster, ATTACK, Current), Max(WeaponHighestHits(Caster), Get(1)))`.

    COLLAPSE V assume (doctrine slice-23) : les trois feuilles `DSLFormulas`
    (`StatAmount`/`WeaponHighestHits`/`Max`) se resolvent en deux lectures du `UnitContext` du
    caster, et le produit vit deja dans `engine.predict.repair_amount_weapon` -- la SEULE lecture
    de cette formule dans le moteur, CONFRONTEE LIVE (#45d, `pairUtility` natif bit-exact sur le cas
    discriminant `repairAmount < missing`). On l'appelle, on ne la duplique pas.

    `StatAmount(..., part 0 = Current)` = la stat Attack RESOLUE (initial + modifiers + overrides) ->
    `UnitStats.get_stat(ATTACK, CURRENT)`. 0 si le caster n'a pas de contexte de stats."""
    e = state.get_entity(int(caster_id)) if caster_id is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None)
    if ctx is None:
        return 0
    return int(repair_amount_weapon(int(ctx.stat(StatType.ATTACK)),
                                    int(getattr(ctx, "normal_weapon_hits", 1) or 1)))


def repair_tree(state: "State", caster_id: int) -> Repair:
    """L'arbre de `RepairAbility$$CreateBehaviour` : la feuille `DSLBehaviors$$Repair` NUE.

    `targets_sel = Target()` (le `<bundle@0x90>+0x60` = `ActiveTarget`), `guard = None` -- le natif ne
    pre-filtre PAS ce selecteur (contraste `InspiredToGreatness`, qui l'enveloppe d'un
    `HealableUnitsSelector`) : c'est le gate `AttackQuery$$EntityCanBeRepaired` DE L'OPERATION qui
    tranche, exactement la ou le natif le place. `scope=0` / `remove_effects=True` = les deux champs
    de `RepairBehaviourOptions$$ForRepair`."""
    return Repair(Target(), repair_amount(state, caster_id), guard=None,
                  scope=0, remove_effects=True)


class RepairAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.RepairAbility` (id 28, `ActiveAbilityType.Repair`)
    — la reparation GENERIQUE accordee par le trait `Mechanic`.

    Cast sur un ALLIE MECANIQUE endommage ADJACENT (`RANGE_ADJACENT`) : restaure
    `Attack(caster) x Max(WeaponHighestHits(caster), 1)` PV, cape a ce qui manque
    (`FillUpStatComponent$$MaxFillUp`). Aucun degat, aucun effet pose.

    C'est cette entree au registre qui ferme le residu #299 : avant elle, `AbilityHandler` rendait
    `ported: False`, posait les flags de tour et NE MUTAIT RIEN -- cast accepte, tour consomme, zero
    PV restaure."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Repair)   # 28
    # Ability DERIVEE d'un trait -> AUCUNE entree gameconfig (cf. l'en-tete de module). `None` rend
    # `AActiveAbility$$SetConfigValuesInTargetingOptions` inerte -- ce qui est CORRECT ici, le range
    # etant `RANGE_ADJACENT` (litteral) et non `RANGE_FROM_CONFIG`.
    ABILITY_ID = None
    TARGETING_OPTIONS = REPAIR_TARGETING_OPTIONS

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        repair_tree(state, caster_id).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        rep = next((p for n, p in ectx.emitted if n == "Repair"), None) or {}
        return {"ability": "Repair", "caster": caster_id, "target": target_id,
                "amount": rep.get("amount"), "repairs": rep.get("repairs"), "dsl": True}

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$GetDynamicInvalidTargetReason`
        — MIRROR du decompile, verbatim :

            if (UnitExtensions.IsEnemy(target, caster, state))       return 0x400  TargetIsFriendly;
            if (!EntityExtensions.IsUnit(target))                    return 0;
            if (!attackQuery.<slot 0x12>(caster, target, 0, true))   return 0x10000 TargetIsRepairable;
            return 0;

        Le slot 0x12 est `IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired` (surcharge 5
        arguments, caster en tete) -- deja porte 1:1 dans `abilities/attack_query.py`, qui CITE ce
        call-site. `scope = 0` / `removeEffects = true` sont les LITTERAUX de l'appel, pas les
        options de la behaviour."""
        from .attack_query import entity_can_be_repaired
        if target_id is None:
            return 0
        if units_are_enemies(state, int(target_id), int(caster_id)):
            return int(TR.TargetIsFriendly)
        if not _resolves_to_unit(state, int(target_id)):
            return 0                          # `!IsUnit(target)` -> le natif rend 0 (pas de refus)
        if not entity_can_be_repaired(state, int(caster_id), int(target_id),
                                      scope=0, remove_effects=True):
            return int(TR.TargetIsRepairable)
        return 0


def galvanic_override_amount(state: "State", caster_id: int):
    """Le noeud MONTANT du volet attaque de 1119 :
    `PercentageOfAttackCappedAtMax(Subject, 3 = Initial, ConfigVar(GalvanicField, maxDmg),
    ConfigVar(GalvanicField, dmgPct))` = `Min(maxDmg, PercentageOf(Attack(Subject, Initial), dmgPct))`.

    Le SUJET est l'unite qui RECOIT l'override (la machine reparee), pas le caster : c'est
    `AddStatOverrideEffect` qui le lie (`param_3[4] = current` au decompile) avant d'evaluer le
    noeud. D'ou le selecteur `Subject()`.

    `maxDmg`/`dmgPct` viennent en revanche de la config du PASSIF `GalvanicField` (1199) du CASTER,
    au niveau PASSIF et avec SON multiplicateur de rarete -- MEME resolution que la face DECISION
    (`ai/action_generators.py`, lot #85). COLLAPSE V des deux `ConfigVar` : ils sont resolus ici en
    scalaires, la formule les accepte tels quels. `None` si la config n'est pas lisible."""
    e = state.get_entity(int(caster_id)) if caster_id is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None)
    if ctx is None:
        return None
    lvl = getattr(ctx, "passive_ability_level", None)
    if lvl is None:
        lvl = getattr(ctx, "active_ability_level", None)
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
    cap = ability_var(GALVANIC_CONFIG, "maxDmg", lvl, multiplier_pct=mult)   # rarity-scale
    pct = ability_var(GALVANIC_CONFIG, "dmgPct", lvl, multiplier_pct=mult)   # non rarity-scale
    if cap is None or pct is None:
        return None
    return percentage_of_attack_capped_at_max(Subject(), int(cap), int(pct),
                                              stat_part=int(StatPart.INITIAL))


def galvanic_field_attack_behavior(state: "State", caster_id: int,
                                   acting_sel: "TargetsSelector") -> list:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.Repair_GalvanicFieldAbility$$CreateAttackBehavior(dsl, actingUnits)`
    — MIRROR du decompile, feuille par feuille. Fonction MODULE (et non methode) parce que le natif
    l'est aussi : le `this` du call est le **`dsl`**, pas l'ability -> DEUX appelants distincts la
    partagent, avec des `actingUnits` DIFFERENTS :

      * `Repair_GalvanicFieldAbility$$CreateBehaviour` : `actingUnits = <Target@0x60> - <Caster@0x48>` ;
      * `IdunBattleLogic.Entities.Abilities.Active.Loki.DefendTheDivineWorkAbility$$ExecuteBehaviour`
        (1117, MEME porteur `admecManipulus`) : `actingUnits = Friends(Caster@0x48,
        AdjacentUnits(CasterTile@0x50, 1, 3))` -- les amis adjacents, **SANS** le caster.

    Corps natif (relu verbatim) :

        affected = DSLSelectors.UnitsAffectedByHealType(actingUnits, 1 = Mechanical)
        node     = PercentageOfAttackCappedAtMax(Subject, 3 = Initial,
                                                 ConfigVar(0x4af = 1199 GalvanicField, Owner@0x30, 0xd),
                                                 ConfigVar(0x4af,                       Owner@0x30, 0x4a))
        return ( AddStatOverrideEffect(affected, 0x4da = 1242, 0 = ATTACK, node, duree 0, modifiable 1)
               & PerformAIAttackFromCurrentPosition(affected, <Owner@0x30>, 0, false) )
               & RemoveEffect(affected, Nullable(0x4da), 0)

    L'ORDRE d'execution est celui des deux `op_BitwiseAnd` : override POSE sur toutes les unites
    affectees, PUIS une attaque par unite (ordre du selecteur), PUIS retrait de l'override -> net-zero.

    ECART DE FORME ASSUME, precedent `TheQuickeningAbility$$GetTriggerAttackBehaviour`
    (`abilities/loki/quickening.py::_free_melee_attack`) : les etages 1 et 3 sont des feuilles DSL
    portees (et le filtre `UnitsAffectedByHealType` est bien le noeud NATIF), mais `PerformAIAttack-
    FromCurrentPosition` n'en est pas une -> la boucle d'attaque est ecrite imperativement ENTRE les
    deux feuilles. Meme forme, meme ordre, memes observables.

    Le CHOIX de cible n'est PLUS approxime (#338) : `perform_ai_attack_from_current_position` passe
    par le moteur d'utilite natif (`AiControl$$ExecuteAbilityActionFor` ->
    `DefaultAiUnitTactic.u003CCalculateAbilityActionForUnitu003Ed__6$$MoveNext`). RESIDU restant :
    le roll de degat RNG.

    `node is None` (config `GalvanicField` illisible) -> AUCUN override invente, aucune attaque :
    degradation fidele. Rend la liste des attaques declenchees."""
    from .loki.summon import perform_ai_attack_from_current_position
    out: list = []
    node = galvanic_override_amount(state, caster_id)
    if node is None:
        return out
    ents = entities_from_state(state, caster_id)
    affected = UnitsAffectedByHealType(acting_sel, 1)          # `UnitsAffectedByHealType(..., 1)`
    acting_ids = [u.get("id") for u in affected.evaluate(ents)
                  if isinstance(u, dict) and u.get("id") is not None]
    if not acting_ids:
        return out
    ectx = ExecutionContext(state=state, rng=state.rng)
    AddStatOverrideEffect(affected, GALVANIC_DMG_OVERRIDE, int(StatType.ATTACK), node,
                          name="GalvanicField_DmgOverride").execute(ents, ectx)
    try:
        for uid in acting_ids:                                 # ordre du SELECTEUR (natif : idem)
            r = perform_ai_attack_from_current_position(state, int(uid))
            if r is not None:
                out.append({"attacker": int(uid), "target": r.get("target"),
                            "total": r.get("total")})
    finally:
        RemoveEffect(GALVANIC_DMG_OVERRIDE, affected).execute(ents, ectx)
    return out


class Repair_GalvanicFieldAbility(RepairAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.Repair_GalvanicFieldAbility` (id 1119,
    `admecManipulus` — le passif `GalvanicField` SPECIALISE la reparation derivee du trait `Mechanic`).

    `CreateBehaviour` = `RepairAbility.CreateBehaviour & CreateAttackBehavior` : la reparation
    HERITEE (identique a 28, meme `RepairAmount`, aucun override du slot `+0x4b8` au binaire), PUIS
    la machine reparee attaque immediatement depuis sa position avec un Attack OVERRIDE.

    `Repair_GalvanicFieldAbility$$.ctor` = `return RepairAbility..ctor(this)` -> masque, range,
    forceMeleeTarget et `AbilityAttackType` STRICTEMENT hérités (d'ou l'heritage de classe ici, qui
    est le mirror exact de l'heritage natif -- pas une commodite Python)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Repair_GalvanicField)   # 1119
    ABILITY_ID = None

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        out = super().execute_behaviour(state, caster_id, target_id)
        if out is None:
            return None
        out["ability"] = "Repair_GalvanicField"
        out["attacks"] = self._attack_behavior(state, caster_id, target_id)
        return out

    def _attack_behavior(self, state: "State", caster_id: int, target_id: int) -> list:
        """`Repair_GalvanicFieldAbility$$CreateAttackBehavior` applique au call-site de CETTE ability.

        `actingUnits = <Target@0x60> - <Caster@0x48>` : sur un cast mono-cible, la cible SI elle n'est
        pas le caster (le masque `CasterIsPossibleTarget` autorise le self-cast, et c'est cette
        soustraction qui empeche alors le caster de s'auto-attaquer). Tout le reste du behaviour
        (`UnitsAffectedByHealType`, l'override, l'attaque, le retrait) vit dans
        `galvanic_field_attack_behavior`, MIRROR partage avec l'autre appelant natif (1117
        `DefendTheDivineWork`) -- comme le natif, dont `CreateAttackBehavior` est une fonction du
        `dsl`, pas une methode de l'ability.

        `entities_from_state(state, caster_id, target_id)` : le mirror partage rebatit son propre
        contexte SANS cible (le natif n'a pas besoin de `Target` dans `CreateAttackBehavior` -- il ne
        lit que `Owner@0x30`), donc on lui passe le selecteur DEJA resolu en `UnitSet` pour ce
        call-site mono-cible."""
        if target_id is None or int(target_id) == int(caster_id):
            return []                                    # `Target - Caster` = ensemble VIDE
        ents = entities_from_state(state, caster_id, int(target_id))
        acting = Sub(Target(), Caster()).evaluate(ents)   # `<Target@0x60> - <Caster@0x48>`
        return galvanic_field_attack_behavior(state, caster_id, UnitSet(list(acting)))

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.Repair_GalvanicFieldAbility$$GetDynamicInvalidTargetReason`
        — MIRROR du decompile (il SURCHARGE celui de `RepairAbility`, il ne l'appelle pas) :

            if (target != null && caster != target
                && attackQuery.<slot 2>(target, targetTiles[0], GetNormalAttackType(target))) {
                if (UnitExtensions.IsEnemy(target, caster, state)) return 0x400 TargetIsFriendly;
                return UnitExtensions.IsAffectedByHealType(target, 1) ? 0 : 1 ValidRequest;
            }
            if (EntityExtensions.IsUnit(target)
                && !attackQuery.<slot 0x13>(target, 0, true))       return 0x10000 TargetIsRepairable;
            return UnitExtensions.IsEnemy(target, caster, state) ? 0x400 : 0;

        Le slot 2 est `IdunBattle.Core.Services.AttackQuery$$HasValidTargets(attacker,
        attackerPosition, activeAbilityType)` — signature LUE (3 arguments + this : unite, position,
        type d'ability), et le 3e argument est ici `GetNormalAttackType(target)`, l'ability d'attaque
        NORMALE CONCRETE de la cible. Sens : « la cible a-t-elle quelqu'un a attaquer depuis sa
        tuile ». C'est le pendant exact du volet ATTAQUE : GalvanicField accepte une machine encore
        PLEINE si elle peut frapper (le coup gratuit suffit a justifier le cast), et ne retombe sur le
        gate de reparation standard que sinon.

        PORT : `targeting.valid_normal_attack_targets(state, target)` est le mirror deja en place de
        `ValidNormalAttackTargetsSelector$$Select` -> `TargetingQuery$$GetValidTargets(unit, ses
        tuiles, options de l'attaque normale)`, mesure depuis la position REELLE de l'unite --
        c'est-a-dire exactement `targetTiles[0]`. Le cooldown (`ActiveAbility$$get_CanCurrentlyBeUsed`
        sur le `GetOrNull(normalAttackType)` du natif) n'est pas modelise pour l'attaque normale ->
        degradation PERMISSIVE (le port peut prendre la branche A la ou le natif prendrait B)."""
        from .attack_query import entity_can_be_repaired
        if target_id is None:
            return 0            # `target == null` : le natif tombe en branche B, `IsUnit`/`IsEnemy` faux
        tid, cid = int(target_id), int(caster_id)
        if tid != cid and _resolves_to_unit(state, tid) and valid_normal_attack_targets(state, tid):
            if units_are_enemies(state, tid, cid):
                return int(TR.TargetIsFriendly)
            from .attack_query import is_affected_by_heal_type
            return 0 if is_affected_by_heal_type(state, tid, 1) else int(TR.ValidRequest)
        if _resolves_to_unit(state, tid) and not entity_can_be_repaired(
                state, None, tid, scope=0, remove_effects=True):
            # slot 0x13 = surcharge TROIS arguments d'`EntityCanBeRepaired` (SANS caster) : le mirror
            # porte est le meme corps avec `caster_id=None` -- le disjunct `caster != null &&
            # HasFlag(caster, 0x18)` de la surcharge 5-args tombe alors de lui-meme.
            return int(TR.TargetIsRepairable)
        return int(TR.TargetIsFriendly) if units_are_enemies(state, tid, cid) else 0
