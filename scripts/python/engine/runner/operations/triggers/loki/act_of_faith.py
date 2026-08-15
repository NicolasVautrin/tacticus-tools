"""`Abilities.Active.Loki.ActOfFaithAbility` (IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaithAbility$$CreateTrigger) + `ActOfFaith_RemoveEffectAbility` (IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaith_RemoveEffectAbility$$CreateTrigger)
— ACCUMULATION (au kill d'un allie Imperial) et RESET (au crit du porteur) du buff crit ActOfFaith
(Adepta Sororitas). Cf. `loki/__init__.py` pour le regroupement « Loki »."""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import StatsComponent, OwnerComponent, UnitComponent
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect, RemoveEffect
from ....abilities.behaviours.lifecycle import TriggerAbilityDelayed
from .....entities.stats import StatType
from .....entities.effect_type import EffectType
from .....entities.behaviours import op_add, If, Maybe
from .....entities.triggers import (TriggerAnd, HasGrandAlliance, AreFriends, AreEnemies, AreEqual,
                                    IsMeleeAttack)
from .....entities.formulas import UnitNormalAttackType, ConfigVarForEntity
from .....entities.selectors.accessors import Actor, Owner, Target
from .....entities.selectors.tiles import Caster
from .....entities.active_ability_type import ActiveAbilityType
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent, _faction_id

ACTOFFAITH_EFFECT = int(EffectType.ActOfFaith_Effect)  # 1017 — ActOfFaithBuffEffect, buff crit empilable
#: `TriggerAbilityDelayed(Owner@+0x30, 0x3fa, 3)` de la branche `!= Custom` du reset (#1001-r1) : le
#: `TriggeredAbilityType` de l'ability elle-meme, exactement comme `BladeOfTheAncestors` (0x5d3).
ACT_OF_FAITH_ABILITY = int(TriggeredAbilityType.ActOfFaithAbility)          # 0x3fa = 1018
#: `unitSelectionType` (4e argument natif) du `TriggerAbilityDelayed` -- trace, jamais lu.
DELAYED_UNIT_SELECTION_TYPE = 3
#   (ATTENTION #158 : 1017 = EffectType.ActOfFaith_Effect ICI, PAS UnitTrait.BigTarget=1017 — contexte = effet)
# Grand-alliance « Imperial » = trait 0x1a=26 (`idun.Idun.Source.Shared.GrandAlliance$$GetTrait → 0x1a si "Imperial").
# Le natif teste `HasTrait(unit, 26)` ; offline = appartenance de `FactionId` au groupe Imperial. Les 10
# factions impériales des 22 du jeu (Chaos: BlackLegion/DeathGuard/ThousandSons/WorldEaters/EmperorsChildren ;
# Xenos: Necrons/Orks/Aeldari/Tau/Tyranids/Genestealers/LeaguesOfVotann). Stable (lore WH40K + GrandAlliance).
IMPERIAL_FACTIONS = frozenset({
    "AdeptusAstartes", "Ultramarines", "BlackTemplars", "SpaceWolves", "DarkAngels", "BloodAngels",
    "AdeptusMechanicus", "AstraMilitarum", "Sisterhood", "Custodes",
})
CRIT_CHANCE_MAX = 100   # crit-chance plafonnée (StatComponent.GetClampedValue ; confirmé live cc 100+10→100)


def act_of_faith_accumulate_tree(effect_type: int):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaithAbility$$CreateBehaviour` (MIRROR 1:1 du DECOMPILE ; branche
    `triggerType != 0x20 = Custom` — la branche `== 0x20` = `DSLBehaviors$$Nothing()`, appelee au DRAIN
    et qui ne fait RIEN, exactement comme celle de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.BladeOfTheAncestorsAbility$$CreateBehaviour`, son
    jumeau de forme -- cf. `act_of_faith_delayed_tree` pour l'autre moitie de la fourche, #1001-r1) :
        op_Addition(
            AddEffect(0x3f9, source=AbilityStateReference, target=Owner@+0x30),                   # [1] GARANTI
            If( HasTrait(killer@+0x40, Imperial=0x1a) & AreFriends(killer@+0x40, Owner@+0x30)
                  & AreEnemies(Target@+0x60, Owner@+0x30, 0)
                  & AreEqual(UnitNormalAttackType(killer@+0x40), RighteousRepugnance_NormalAttack=1182)
                  & IsMeleeAttack(...),
                Maybe( AddEffect(0x3f9), chance=ConfigVar(RighteousRepugnance=1107, killer, chance) ) ) )  # [2]

    [1] STACK GARANTI = feuille `AddEffect(ACTOFFAITH_EFFECT, Caster())` (Owner==Caster pour un triggered).
        La feuille declenche `ActOfFaithBuffEffect.ApplyModification` via `AddEffectOperation` (part DATA
        `applied_stat_mods` = 2 ChangeStat : crit-chance += extraCritChance, crit-damage += Ceiling(base_
        Initial x extraCritDmgPct%)) ; l'effet `stacks_stat_mod_on_add` -> une NOUVELLE instance par proc
        (empilement additif, live-valide 3 stacks +63 plat), revert par-source via la feuille `RemoveEffect`
        (cf. `_reset_act_of_faith`). MEME frontiere declaratif/imperatif que le reset (feuille au-dessus,
        Operation/effet en dessous).

    [2] STACK CONDITIONNEL (2e stack PROBA) = `If(<cond>, Maybe(chance, AddEffect(0x3f9, Caster())))` : un 2e
        stack quand le TUEUR (Actor@0x158) est un allie Imperial dont le normal-attack est RighteousRepugnance_
        NormalAttack (Morvenn Vahl, seul porteur — passive RighteousRepugnance) ET le coup fatal etait en MELEE.
        - `cond` = `HasGrandAlliance(killer, Imperial)` [mirror `HasTrait(killer,0x1a=26)` via faction] &
          `AreFriends(killer, owner)` & `AreEqual(UnitNormalAttackType(killer), RighteousRepugnance_NormalAttack
          =1182)` & `IsMeleeAttack()` (lit `ctx.attack_kind`, cable depuis `ev.ranged` du trigger MORT).
        - `chance` = `ConfigVarForEntity("RighteousRepugnance","chance", killer, slot="passive")` = ability_var
          au NIVEAU PASSIF du killer (40-60% selon niveau, capte offline via `passive_ability_level`) — mirror
          exact de `ConfigVar(RighteousRepugnance=1107, killer, chance=0x3a=58)`.
        - `Maybe` exige `ectx.rng` cale (tirage `next_bool(chance)`) ; sinon no-op documente. Le 2e
          `AddEffect(Caster())` empile un stack de plus (meme feuille -> ApplyModification).
        Entierement resoluble offline (killer=Morvenn : kit->1182, faction->Imperial, passive_ability_level
        ->chance) -> LIVE-VALIDATABLE (equipe 2 heroines Sororitas : Morvenn tue en melee, la porteuse
        ActOfFaith gagne le 2e stack selon le roll).

    `effect_type` passe par l'appelant (constante `ACTOFFAITH_EFFECT`) pour eviter le couplage d'import."""
    # #98 : le decompile IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaithAbility$$CreateBehaviour passe `AddEffect(factory, 0x3f9, stateRef, self@0x148, 0, 0)` --
    # le slot duree vaut NULL -> duree PAR DEFAUT ; `DefaultAmountOfRounds(0x3f9=1017)` est ABSENT du
    # switch idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds -> **PERMANENT** (le stack est retire par `ActOfFaith_RemoveEffectAbility`
    # IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaith_RemoveEffectAbility$$CreateBehaviour, deja porte -- cf. `act_of_faith_reset_tree`). Le port passait le defaut positionnel
    # `duration_rounds=1` (les stacks se seraient evapores au 1er tick) -> `duration_rounds=None`.
    base = AddEffect(effect_type, "ActOfFaith_Effect", Caster(), duration_rounds=None)   # [1] AddEffect(0x3f9, Self@0x148)
    # [2] cond = HasTrait(killer,Imperial=0x1a) & AreFriends(killer,owner) & AreEnemies(Target,owner)
    #            & AreEqual(UnitNormalAttackType(killer), RighteousRepugnance_NormalAttack=1182)
    #            & IsMeleeAttack  (op_BitwiseAnd, gauche->droite)
    # ⚠ `AreEnemies(Targets@+0x60, Owner@+0x30, 0)` etait ABSENT du port (#1001-r1, mesure du meme
    # decompile) : sans lui, la branche 1 du `CreateTrigger` (« un allie Imperial MEURT ») pouvait
    # accorder le 2e stack PROBA alors que le natif le reserve au cas ou la VICTIME est un ennemi.
    cond = TriggerAnd(TriggerAnd(TriggerAnd(TriggerAnd(
        HasGrandAlliance(Actor(), IMPERIAL_FACTIONS),                    # HasTrait(killer@+0x40, 26=Imperial)
        AreFriends(Actor(), Owner())),                                   # AreFriends(killer@+0x40, Owner@+0x30)
        AreEnemies(Target(), Owner())),                                  # AreEnemies(Target@+0x60, Owner@+0x30)
        AreEqual(UnitNormalAttackType(Actor()),                         # UnitNormalAttackType(killer) == 1182
                 Const(int(ActiveAbilityType.RighteousRepugnance_NormalAttack)))),
        IsMeleeAttack())                                                 # coup fatal en melee (ctx.attack_kind)
    chance = ConfigVarForEntity("RighteousRepugnance", "chance", Actor(), slot="passive")   # ConfigVar(1107,killer,58)
    bonus = If(cond, Maybe(chance, AddEffect(effect_type, "ActOfFaith_Effect", Caster(),
                                              duration_rounds=None)))   # If(cond, Maybe(chance, AddEffect))
    return op_add(base, bonus)                                           # op_Addition([1] garanti, [2] conditionnel)


def act_of_faith_delayed_tree():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaith_RemoveEffectAbility$$CreateBehaviour`,
    branche `triggerType != 0x20 = Custom` = `TriggerAbilityDelayed(Owner@+0x30, 0x3fa = 1018, 3)` --
    l'ENFILEMENT, aucun retrait ici (#1001-r1).

    ⚠ CE QUE #1001-r1 A CORRIGE, ET POURQUOI L'ANCIENNE LECTURE ETAIT FAUSSE. Le port ecartait cette
    branche en la disant << cross-instantiation d'un corps gshared >>. Le corps N'EST PAS gshared : il
    est NOMME, il appartient a cette seule classe, et le seul appel `Il2CppFullySharedGeneric` qu'il
    contient est le `.ctor` de `System.Nullable<EffectType>` -- une construction de valeur, pas un
    partage de corps. La preuve est le JUMEAU DE FORME
    `IdunBattleLogic.Entities.Abilities.Active.Loki.BladeOfTheAncestors_RemoveEffectAbility$$CreateBehaviour`,
    dont le decompile est structurellement IDENTIQUE au token pres (`0x5d3`/`0x5d1` au lieu de
    `0x3fa`/`0x3f9`) et dont la lecture a ete CONFRONTEE LIVE (#1001) : le natif retire le buff APRES
    la cloture de l'attaque, pas au milieu de la salve.

    L'argument qui avait fait ecarter la branche -- << l'accumulate a `Nothing` en `==0x20` et le REEL
    en `!=0x20`, donc les assignations sont OPPOSEES >> -- ne conclut rien : les deux classes de 1018
    fourchent sur le MEME test et se PARTAGENT le travail, exactement comme les deux classes de 1491.
    Au drain, le natif rappelle le slot 4 de CHACUNE avec `triggerType = Custom` :

        ActOfFaithAbility                  (Custom) -> `DSLBehaviors$$Nothing()`   = no-op
        ActOfFaith_RemoveEffectAbility     (Custom) -> `RemoveEffect(Owner, 0x3f9)`

    OBSERVABLE : les coups SUIVANTS de l'attaque qui a crite gardent le buff crit ; il ne tombe qu'une
    fois l'attaque TERMINEE (drain de `ProcessPendingTriggeredAbilities`, cf. `dispatch/pending.py`)."""
    return TriggerAbilityDelayed(Owner(), ACT_OF_FAITH_ABILITY,
                                 unit_selection_type=DELAYED_UNIT_SELECTION_TYPE)


def act_of_faith_reset_tree(effect_type: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaith_RemoveEffectAbility$$CreateBehaviour`,
    branche `triggerType == 0x20 = Custom` (MIRROR 1:1 du DECOMPILE) :
        RemoveEffect( targets = Owner@+0x30, effectType = Nullable(0x3f9 = 1017),
                      replaceableEffectType = null )
    Retire TOUS les stacks ActOfFaith du porteur et revert leur ChangeStat (crit-chance + crit-damage,
    `reverted_stats()`) -- MEME Operation de revert par-source (`revert_change_stat`) que l'ancien
    `_reset_act_of_faith` -> bit-exact BY CONSTRUCTION. `effect_type` passe par l'appelant (constante
    `ACTOFFAITH_EFFECT`) pour eviter le couplage d'import.

    ⚠ Cette branche n'est PLUS atteinte par le bus d'events (#1001-r1) : elle n'est joignable que par
    le DRAIN de `state.pending_triggered_abilities`, via `CUSTOM_TRIGGERED_ABILITIES[1018]`."""
    return RemoveEffect(effect_type, Owner())


def _reset_act_of_faith(state: State, owner_id: int) -> Optional[dict]:
    """Branche `Custom` de `ActOfFaith_RemoveEffectAbility` = arbre DSL `act_of_faith_reset_tree()`
    (mirror `RemoveEffect(Owner@+0x30, 0x3f9)`
    IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaith_RemoveEffectAbility$$CreateBehaviour) :
    retire chaque ActOfFaithBuffEffect du porteur et revert son
    ChangeStat (soustrait par-source ; la somme annule exactement l'accumulation compound, quel que soit
    l'ordre). No-op si pas d'effets. Le gate `matches` (On(9) & OwnerIsCaster & WasCrit & HasEffect) reste
    upstream, sur la classe qui ENFILE ; ici le seul gate est celui du drain (`IsUnit => IsAlive`).
    Le report (cc_back/cd_back/removed) est reconstruit autour de l'arbre."""
    owner = state.get_entity(owner_id)
    sc = owner.get_component(StatsComponent) if owner is not None else None
    if sc is None or state.effects is None:
        return None
    ctx = sc.ctx
    cc_before = ctx.stat(StatType.CRIT_CHANCE)
    cd_before = ctx.stat(StatType.CRIT_DAMAGE)
    # behaviour = arbre DSL RemoveEffect(0x3f9, Caster()) ; la feuille itere les stacks du porteur et
    # revert_change_stat(CRIT_CHANCE/CRIT_DAMAGE, stat_mod_source) par stack -> == l'ancien corps (bit-exact).
    ectx = ExecutionContext(state=state)
    act_of_faith_reset_tree(ACTOFFAITH_EFFECT).execute(
        entities_from_state(state, owner_id, None), ectx)
    removed = sum(p["removed"] for n, p in ectx.emitted if n == "RemoveEffect")
    return {"trait": "ActOfFaith", "owner": owner_id, "removed": removed,
            "cc_back": cc_before - ctx.stat(StatType.CRIT_CHANCE),
            "cd_back": cd_before - ctx.stat(StatType.CRIT_DAMAGE),
            "crit_chance": ctx.stat(StatType.CRIT_CHANCE), "crit_damage": ctx.stat(StatType.CRIT_DAMAGE)}


class ActOfFaithAccumulateAbility(TriggeredAbility):
    """`ActOfFaithAbility` (IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaithAbility$$CreateTrigger CreateTrigger / IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaithAbility$$CreateBehaviour CreateBehaviour) — ACCUMULATION du buff
    crit du trait ActOfFaith (Adepta Sororitas).

    IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaithAbility$$CreateTrigger = `OnPreDeath` où **(killer = allié Imperial) OR (mourant = allié Imperial)**
    (`HasTrait(slot,26=Imperial) & AreFriends(slot,owner)` sur 0x158=killer et 0x178=dying, op_BitwiseOr),
    `& IsUnit & OnPreDeath & NOT(owner crit_damage == 0)` (gate `IsUnitWithStatAmount(owner,10,0)`→NOT :
    inutile d'accumuler si le crit-dmg de base est nul). BehaviourIdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaithAbility$$CreateBehaviour = `AddEffect(0x3f9)` sur le
    porteur (la branche conditionnelle interne mêlée/normalAttack module un cas particulier de l'auteur ;
    le NET pour la prédiction de crit = +1 stack par déclenchement). i2 : « +X% Crit Chance et +Y% Crit
    Damage chaque fois qu'un allié Imperial meurt ou tue un ennemi »."""
    event_id = EventTriggerType.PreUnitDeath

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        osc = owner.get_component(StatsComponent)
        oown = owner.get_component(OwnerComponent)
        if osc is None or oown is None:
            return False
        if osc.ctx.stat(StatType.CRIT_DAMAGE) == 0:    # NOT(owner crit_damage == 0)
            return False

        def _friendly_imperial(uid: Optional[int]) -> bool:
            if uid is None:
                return False
            e = state.get_entity(uid)
            if e is None:
                return False
            oc = e.get_component(OwnerComponent)
            if oc is None or oc.team != oown.team:                # AreFriends(unit, owner) = même équipe
                return False
            return _faction_id(state, uid) in IMPERIAL_FACTIONS   # HasTrait(unit, 26 = Imperial)

        return _friendly_imperial(ev.killer_id) or _friendly_imperial(ev.dying_id)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        # behaviour = arbre DSL `act_of_faith_accumulate_tree()` (mirror 1:1 de IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaithAbility$$CreateBehaviour) :
        # AddEffect(0x3f9, Caster()) [+ 2e stack conditionnel RighteousRepugnance, tranche suivante]. La
        # feuille `AddEffect` declenche `ActOfFaithBuffEffect.ApplyModification` (2 ChangeStat crit) via
        # `AddEffectOperation` -> MEME mutation que l'ancien `_apply_act_of_faith_stack` (bit-exact BY
        # CONSTRUCTION : memes constantes 0x30/0x31, meme Ceiling(Initial x pct%), meme source par-stack).
        # Contexte AbilityEntities : caster/owner = le porteur (Self@0x148 == Caster pour un triggered),
        # actor = killer@0x158, target = dying@0x178 ; `attack_kind` (IsMeleeAttack du 2e stack) = le coup
        # fatal etait-il melee (ev.ranged du trigger MORT).
        owner = state.get_entity(self.owner_id)
        sc = owner.get_component(StatsComponent) if owner is not None else None
        if sc is None:
            return None
        ctx = sc.ctx
        cc_before = ctx.stat(StatType.CRIT_CHANCE)
        cd_before = ctx.stat(StatType.CRIT_DAMAGE)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, ev.dying_id, actor_id=ev.killer_id)
        entities.attack_kind = "ranged" if ev.ranged else "melee"
        act_of_faith_accumulate_tree(ACTOFFAITH_EFFECT).execute(entities, ectx)
        stacks = sum(1 for n, p in ectx.emitted if n == "AddEffect" and p.get("placed"))
        return {"trait": "ActOfFaith", "owner": self.owner_id, "stacks_added": stacks,
                "cc_delta": ctx.stat(StatType.CRIT_CHANCE) - cc_before,
                "cd_delta": ctx.stat(StatType.CRIT_DAMAGE) - cd_before,
                "crit_chance": ctx.stat(StatType.CRIT_CHANCE), "crit_damage": ctx.stat(StatType.CRIT_DAMAGE)}


class ActOfFaithResetAbility(TriggeredAbility):
    """`ActOfFaith_RemoveEffectAbility` (IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaith_RemoveEffectAbility$$CreateTrigger CreateTrigger / IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaith_RemoveEffectAbility$$CreateBehaviour CreateBehaviour) — RESET du
    buff au crit du porteur.

    IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaith_RemoveEffectAbility$$CreateTrigger = `On(9,1) & OwnerIsCaster & WasCrit & HasEffect(owner,0x3f9)` (confirmé décompilé).
    `On(9)=Attack` est un event GÉNÉRIQUE — émis par `FinishAttackOperation IdunBattle.Operations.FinishAttackOperation$$Execute` à la FIN de TOUTE attaque,
    NORMALE ET ability (`DSLFactory.On` BRUT ; verdict RE re-expert G6b). Le reset n'a AUCUN gate normal/ability :
    `WasCrit` est le SEUL filtre de type → **le porteur reset ses stacks sur un crit d'attaque NORMALE COMME
    d'ability**. ⚠ CORRECTION de #151 (via G6b) : #151 confondait `On(9)` BRUT avec le helper
    `IdunBattleLogic.Entities.DSLTriggers$$OnNormalAttackOrSmite` (= `On(38)|(On(9)&Smite)`, NON utilisé par ce trigger) et croyait `On(9)`
    ability-only → il n'émettait `On(9)` qu'en voie ability, d'où un reset MANQUANT sur crit normal (bug). Depuis
    G6b, `On(9)` est émis EN PLUS par `after_hit_normal_attack` (FinishAttack générique), gaté `is_crit` — le
    reset fire donc désormais sur les DEUX voies. Il N'écoute PAS le vecteur after-hit `On(8)` (per-coup).
    `OwnerIsCaster` = owner est l'attaquant (`actor_id`).
    ⚠ **LE BEHAVIOUR N'EST PLUS LE RETRAIT, C'EST L'ENFILEMENT (#1001-r1)** :
    `...ActOfFaith_RemoveEffectAbility$$CreateBehaviour` FOURCHE sur son 3e parametre, et la branche
    prise par le bus d'events (`triggerType != 0x20 = Custom`) vaut
    `TriggerAbilityDelayed(Owner@+0x30, 0x3fa = 1018, 3)`. Le `RemoveEffect(0x3f9)` est l'AUTRE
    branche (`== Custom`), rappelee au DRAIN -- cf. `ActOfFaithCustomRemoveEffectAbility` plus bas.
    Le port collapsait la fourche sur `RemoveEffect` en croyant la branche differee inatteignable ;
    consequence mesurable : les stacks tombaient UN CRAN TROP TOT (au milieu de la salve au lieu
    d'apres sa cloture). Le gate `HasEffect` reste ici et garde l'idempotence (une seule mise en file
    par attaque tant que le buff n'est pas retire).
    ⚠ Approximation (pré-existante) : le vecteur reste AGRÉGÉ (1×/attaque d'ability, `is_crit` agrégé)
    et non per-coup — mais depuis #1001-r1 l'ecart qu'elle causait est ETEINT sur l'axe qui comptait :
    le natif lui-meme ne retire rien avant la cloture de l'attaque. overwatch = non couvert (pas de
    vecteur ability-attack dédié)."""
    event_id = EventTriggerType.Attack
    TRIGGERED_ABILITY_ID = ACT_OF_FAITH_ABILITY                  # 0x3fa = 1018

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if self.owner_id != ev.actor_id:                         # OwnerIsCaster
            return False
        if not ev.is_crit:                                       # WasCrit
            return False
        if state.effects is None or not state.effects.has_effect(  # HasEffect(owner, 0x3f9)
                self.owner_id, effect_type=ACTOFFAITH_EFFECT):
            return False
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        # branche `triggerType != Custom` = `TriggerAbilityDelayed(Owner@+0x30, 0x3fa, 3)`
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, int(self.owner_id), None, actor_id=ev.actor_id)
        act_of_faith_delayed_tree().execute(entities, ectx)
        delayed = [p for n, p in ectx.emitted if n == "TriggerAbilityDelayed"]
        return {"trait": "ActOfFaith", "owner": int(self.owner_id),
                "queued": bool(delayed and delayed[0].get("queued")),
                "dispatched": bool(delayed and delayed[0].get("dispatched")), "dsl": True}


class ActOfFaithCustomRemoveEffectAbility(TriggeredAbility):
    """`ActOfFaith_RemoveEffectAbility$$CreateBehaviour`, branche `triggerType == 0x20 = Custom` --
    LE RESET (#1001-r1). Jamais atteinte par le bus d'events : inscrite dans
    `CUSTOM_TRIGGERED_ABILITIES[1018]`, elle n'est joignable que par le drain de
    `state.pending_triggered_abilities`.

    `matches` rend `True` : sur ce chemin le natif ne RE-EVALUE aucun trigger
    (`IdunBattle.Operations.TriggerTriggeredAbilityOperation$$TriggerAbility` n'appelle que le slot 4).
    Le seul gate qui reste est celui du drain (`IsUnit(entity) => IsAlive(entity)`), porte par
    `dispatch/pending.trigger_triggered_ability`.

    ⚠ Le jumeau `ActOfFaithAbility` a LUI AUSSI une branche `Custom`, et elle vaut
    `IdunBattleLogic.Entities.DSLBehaviors$$Nothing()` : le natif l'appelle au drain et elle ne fait
    RIEN. Elle n'est donc pas inscrite au registre -- une classe de no-op y serait un mensonge de
    couverture, pas une fidelite. MEME arbitrage que `BladeOfTheAncestors` (#1001)."""

    event_id = int(EventTriggerType.Custom)          # 0x20 -- jamais emis par le bus du port
    TRIGGERED_ABILITY_ID = ACT_OF_FAITH_ABILITY      # 0x3fa = 1018

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return _reset_act_of_faith(state, self.owner_id)

