"""`IdunBattle.Entities.Effects.ReviveEffect` -- BASE du sous-systeme REVIVE-EN-PLACE (case-66).

C'est une FAMILLE : la base fournit la STRUCTURE (trigger + behaviour DSL + les 3 virtuels), chaque
sous-classe `Loki.*_ReviveEffect` ne surcharge que le FILTRE, les vars et le gate d'overkill. Ce module
mirroir la BASE (ns natif `IdunBattle.Entities.Effects`, hors `Loki`) ; les sous-classes vivent dans
`triggers/loki/*.py` (ns natif `IdunBattle.Entities.Effects.Loki`).

Artefacts natifs (build gqfc5mff6c, VA citees ; RVA = VA - 0x180000000 calculee en code) :

    ReviveEffect..ctor                       @180f46e60  0x484=turnsEnabled, 0x480=activationFrequency,
                                                         0x488=removeEffect, source=AbilityOrEffect
    ReviveEffect.CreateTargetTrigger         @180f46d80  OnPreDeath(target, get_ReviveOnOverkill)
                                                         & CanBeRevived(target, get_HealType)
                                                         & CreateTargetFilter          (3 virtuels)
    ReviveEffect.CreateTargetTriggerBehaviour @180f46a70 Maybe(GetReviveChance){
                                                             Revive(self, target,
                                                                    Min(GetReviveHP,
                                                                        StatAmount(target,Health,max)),
                                                                    tile, sourceId) ;
                                                             DeactivateEffect }
    DSLFactory.Revive          @180dfa4f0 -> ReviveBehaviour.Execute @180fd1230 -> ReviveUnitMessage
                               -> OperationProcessor.ReviveUnit @180e0b510
                               -> ReviveUnitOperation.Execute @180e91bd0   (operations/revive.py)
    DSLFactory.DeactivateEffect @180dede20 -> ActivateEffectBehaviour(effect, active=false)
    BattleQuery.CanBeRevived    @181058a50

## Les 3 virtuels de `CreateTargetTrigger` (slots vtable resolus LIVE, `probe_79_revive_vtable.py`)

Le decompile appelle `(**(klass + 0x738))`, `(+0x748)`, `(+0x758)`. Le dump metadata NE LISTE PAS ces
corps (des `return 0` / `return 1` triviaux sont deduplique par ICF) -> resolus par le RPC
`resolveVtableSlot` (lecture de pointeurs, ZERO invoke) sur les classes CONCRETES :

    +0x728  get_ActivateOnResurrect  @1802b15a0 = `return 0`   (base, aucune sous-classe ne surcharge)
    +0x738  get_ReviveOnOverkill     @1802b15a0 = `return 0`   base + Narthecium_ReviveEffect
                                     @1802b1590 = `return 1`   TaintedNarthecium_ReviveEffect
    +0x748  get_HealType             @1802b15b0 = `return 0`   (base et sous-classes)
    +0x758  CreateTargetFilter       -> @180f5acf0 (Narthecium) / @180f709b0 (TaintedNarthecium) / ...

`get_ReviveOnOverkill` EST le byte `param_3` de `DSLFactory.OnDeathEvent @180df7ad0` :
  * `param_3 == 0` -> le trigger AJOUTE `NOT(HasFlag(dying, 8=overkill))`  => « unless Overkilled »
  * `param_3 != 0` -> AUCUN gate overkill                                  => « even if Overkilled »
(`param_4 == 0` -> AJOUTE `NOT(CurrentShieldAmountFormula(dying, 0x1b))` = shield==0, present pour TOUS,
implicite a la mort -> non modelise.)
"""
from __future__ import annotations

from typing import Optional

from ...state import State
from ...components import StatsComponent, OwnerComponent, UnitComponent, HealthComponent
from ...abilities.behaviours import entities_from_state
from ...abilities.behaviours.stats import is_mechanical
from ....entities.behaviours import op_add, Maybe
from ....entities.selectors import Caster, Target
from ....entities.traits.unit_trait import UnitTrait
from ....entities.effects.magnitude import ability_var
from ....dsl.base import _units_of
from ....dsl.effects import AbilityBehaviour, OperationResult, ExecutionContext
from ....dsl.event_trigger_type import EventTriggerType
from .base import TriggeredAbility, EffectTrigger, TriggerEvent

PERMADEATH = int(UnitTrait.PermaDeath)                     # 0x41a=1050 (NOT HasTrait -> CanBeRevived)
AFFECTED_BY_HEAL = int(UnitTrait.AffectedByHealAndRepair)  # 0x421=1057 (IsAffectedByHealType)


class Revive(AbilityBehaviour):
    """Feuille DSL `Revive` (`DSLFactory.Revive @180dfa4f0` -> `ReviveBehaviour.Execute @180fd1230`) : revive
    CHAQUE unite du selecteur `target_sel` (le mourant, `Target()@0x178`) a `Min(reviveHP, target.maxPV)`.
    Frontiere #149 : la FEUILLE (declaratif, ICI) APPELLE l'Operation IMPERATIVE `ReviveUnitOperation.execute`
    (operations/revive.py, EN-DESSOUS) -- on NE fusionne PAS. `reviveHP` = `ability_var(ability_id, 'hp',
    passive_level_du_CASTER, mult)` (mirror `GetReviveHP` = `GetVariableForLevel(config, 0x1d, level)` scalee
    rarete) ; `Min(reviveHP, target.hp_max)` = le noeud `Min(Direct(GetReviveHP), StatAmount(target, Health,
    max))` du behaviour natif. PUR (stop=False)."""
    __slots__ = ("target_sel", "ability_id", "hp_var", "level", "mult")

    def __init__(self, target_sel, ability_id: str, hp_var: str = "hp",
                 level=None, mult: int = 100):
        self.target_sel, self.ability_id, self.hp_var = target_sel, ability_id, hp_var
        # `GetReviveHP(abilityState)` = `GetVariableForLevel(config, 0x1d='hp', level)` ou `abilityState`
        # est celui de l'ABILITY SOURCE portee par l'effet. Le niveau/multiplicateur sont donc RESOLUS PAR
        # LE RAIL (cf. `_ReviveEffectCore.revive_level`) : passif du porteur pour un ReviveEffect pose
        # d'office par un passiveAbility ; niveau de l'ACTIVE du POSEUR (transporte par l'effet) pour un
        # ReviveEffect pose par une ability active. La feuille ne devine RIEN.
        self.level, self.mult = level, mult

    def execute(self, entities, ectx):
        from ..revive import ReviveUnitOperation
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        revive_hp = ability_var(self.ability_id, self.hp_var, self.level,
                                multiplier_pct=self.mult)      # GetReviveHP
        for u in _units_of(self.target_sel, entities):
            tid = u.get("id") if isinstance(u, dict) else None
            if tid is None:
                continue
            te = state.get_entity(tid)
            thc = te.get_component(HealthComponent) if te is not None else None
            maxhp = thc.hp_max if thc is not None else None
            hp = revive_hp
            if hp is not None and maxhp is not None:
                hp = min(int(hp), int(maxhp))                # Min(reviveHP, StatAmount(target,Health,max))
            r = ReviveUnitOperation.execute(state, tid, hp)  # -> mutateur ECS imperatif (revive-en-place)
            ectx.emit("Revive", target=tid, hp=(r or {}).get("hp"), revive_hp=revive_hp,
                      revived=r is not None)
        return OperationResult.ok()


class ConsumeReviveGate(AbilityBehaviour):
    """Feuille `DeactivateEffect` (2e volet de l'`op_add` du `CreateTargetTriggerBehaviour @180f46a70`, execute
    APRES le `Revive` sur SUCCES du `Maybe`) : DESACTIVE l'effet revive du porteur -> gate once-per-turn.
    Port : pose `revive_used_this_turn=True` sur le CASTER (`Caster()@0x148`, owner du passif/de l'effet) ;
    reactive au turn-start (`reset_revive_gates`). PUR (stop=False)."""
    __slots__ = ("owner_sel",)

    def __init__(self, owner_sel):
        self.owner_sel = owner_sel

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        for u in _units_of(self.owner_sel, entities):
            oid = u.get("id") if isinstance(u, dict) else None
            oe = state.get_entity(oid) if oid is not None else None
            ouc = oe.get_component(UnitComponent) if oe is not None else None
            if ouc is not None:
                ouc.revive_used_this_turn = True
        ectx.emit("DeactivateReviveEffect")
        return OperationResult.ok()


class RemoveReviveEffect(AbilityBehaviour):
    """Feuille `BaseEffect.GetRemoveEffectBehaviour` -- 2e volet du `CreateTargetTriggerBehaviour
    @180f46a70` quand le champ `removeEffect` (0x488, pose au ctor) vaut TRUE. Contrairement a
    `DeactivateEffect` (desactivation reactivee au turn-start = once-per-TURN), `RemoveEffect` RETIRE
    l'effet -> le revive est one-shot DEFINITIF (« the FIRST TIME ... would be defeated »).
    Port : marque l'effet `consumed=True` dans `state.effects` (le collecteur `collect_effect_triggers`
    skippe les effets consommes -> le trigger ne peut plus refirer). PUR (stop=False)."""
    __slots__ = ("owner_sel", "effect_type")

    def __init__(self, owner_sel, effect_type: int):
        self.owner_sel, self.effect_type = owner_sel, effect_type

    def execute(self, entities, ectx):
        state = ectx.state
        eff = getattr(state, "effects", None) if state is not None else None
        if eff is None:
            return OperationResult.ok()
        for u in _units_of(self.owner_sel, entities):
            oid = u.get("id") if isinstance(u, dict) else None
            if oid is None:
                continue
            for e in (eff.by_unit.get(int(oid)) or []):
                if e.effect_type == self.effect_type:
                    e.consumed = True
        ectx.emit("RemoveReviveEffect", effect_type=self.effect_type)
        return OperationResult.ok()


def create_target_trigger_behaviour(chance: int, ability_id: str, hp_var: str = "hp",
                                    remove_effect: bool = False, effect_type: int = -1,
                                    owner_sel=None, level=None, mult: int = 100):
    """Arbre de `ReviveEffect.CreateTargetTriggerBehaviour @180f46a70` (MIRROR, base -> partage par TOUTES
    les sous-classes) :

        chance   = GetReviveChance                       (virtuel @vtable+0x768)
        reviveHP = GetReviveHP(abilityState)             (virtuel @vtable+0x778)
        amount   = Min(Direct(reviveHP), StatAmount(target@0x178, Health=5, max=3))
        revive   = Revive(self@0x148, target@0x178, amount, GetHealType@0x748, sourceId)
        second   = (removeEffect@0x488 == 0) ? DeactivateEffect(effect)
                                             : BaseEffect.GetRemoveEffectBehaviour(effect)
        Maybe(func{ revive ; second }, target@0x178, chance)

    `Maybe @180df6610 -> MaybeBehaviour.Execute @180fc9dc0` fait UN tirage `next_bool(chance)` ; le func
    ne s'execute QUE sur SUCCES -> un roll RATE ne consomme PAS le gate."""
    owner_sel = Caster() if owner_sel is None else owner_sel
    second = (RemoveReviveEffect(owner_sel, effect_type) if remove_effect
              else ConsumeReviveGate(owner_sel))
    return Maybe(chance, op_add(
        Revive(Target(), ability_id, hp_var, level, mult),  # DSLFactory.Revive -> ReviveUnitOperation
        second))                                # DeactivateEffect (once-per-turn) | RemoveEffect (one-shot)


def can_be_revived(entities, target_liveunit, target_id: int, state: State) -> bool:
    """`BattleQuery.CanBeRevived @181058a50` (mirror, appele par le noeud `CanBeRevived` du
    `CreateTargetTrigger @180f46d80` via `DSLFactory.CanBeRevived @180deb4a0 -> CanBeRevivedTrigger
    @180f96b00`) : `GetStat(unit,Health,0) < 1` (mort) & `IsAffectedByHealType(healType)` &
    `NOT HasFlag(unit,0xd)` & `NOT HasTrait(PermaDeath=0x41a=1050)` & `NOT HasHealBlockers`.

    Port : hp<1 (mort) & NOT PermaDeath & IsAffectedByHealType(0) = `HasTrait(AffectedByHealAndRepair)
    OR NOT IsMechanical` (mirror @180ed77d0 via le helper partage `is_mechanical`). `healType` = le virtuel
    `get_HealType @+0x748` = 0 pour la base ET toutes les sous-classes (lu LIVE, cf. entete). Flag 0xd
    (pas encore pose a l'instant de l'OnPreDeath) & HealBlockers non modelises -> non-bloquants."""
    e = state.get_entity(target_id)
    hc = e.get_component(HealthComponent) if e is not None else None
    if hc is None or hc.hp is None or int(hc.hp) >= 1:        # GetStat(Health,0) < 1 : doit etre mort
        return False
    ht = entities.has_trait
    if ht is None:
        return True                                          # pas de resolveur trait -> defaut revivable
    if ht(target_liveunit, PERMADEATH):                      # NOT HasTrait(PermaDeath=1050)
        return False
    # IsAffectedByHealType(0) @180ed77d0 : HasTrait(AffectedByHealAndRepair=1057) OR NOT IsMechanical
    return bool(ht(target_liveunit, AFFECTED_BY_HEAL) or not is_mechanical(ht, target_liveunit))


class _ReviveEffectCore:
    """Coeur PARTAGE de la base `ReviveEffect` (trigger @180f46d80 + behaviour @180f46a70). Mixe dans
    les DEUX rails du port (`ReviveEffectAbility` pour un effet pose par un PASSIF -> registre
    `ABILITY_TRIGGERS` ; `ReviveEffectTrigger` pour un effet pose par une ACTIVE -> registre
    `EFFECT_TRIGGERS`) : cote natif c'est le MEME `ReviveEffect`, seule change la facon dont l'effet
    arrive sur son porteur.

    Une sous-classe concrete fixe :
      * `ability_id`           -- cle gameconfig des vars ('hp') / constantes ('chance')
      * `revive_on_overkill`   -- virtuel `get_ReviveOnOverkill` @vtable+0x738 (False = « unless Overkilled »)
      * `remove_effect`        -- champ 0x488 du ctor : False = DeactivateEffect (once-per-turn, reactive
                                  au turn-start) ; True = RemoveEffect (one-shot definitif)
      * `create_target_filter` -- virtuel @vtable+0x758 (le SEUL noeud specifique a chaque consommateur)"""
    ability_id: str = ""
    revive_on_overkill: bool = False                # get_ReviveOnOverkill @vtable+0x738
    remove_effect: bool = False                     # champ 0x488 (ctor) : DeactivateEffect vs RemoveEffect
    effect_type: int = -1                           # EffectType du ReviveEffect (pour RemoveEffect)
    hp_var: str = "hp"
    chance_is_constant: bool = True                 # GetReviveChance = GetNumberConstant(config, 0x2a)
    # Fallback quand l'ability n'a PAS de constante 'chance' dans le gameconfig. Ce N'EST PAS un defaut
    # de confort : `AbilityConfiguration.GetNumberConstant @181576af0` delegue a `GetStringConstant
    # @181576bb0` qui **LANCE UNE EXCEPTION** si la cle est absente du dictionnaire. Une sous-classe dont
    # la config n'a pas 'chance' NE PEUT donc PAS partager le `GetReviveChance` de Narthecium
    # (@180f5ada0) : elle DOIT l'overrider par un corps litteral -- corps trivial (`return N`) donc
    # FOLDE par ICF, invisible au dump metadata, et sa vtable n'est pas lisible LIVE tant que sa classe
    # n'est pas initialisee (carrier hors pool). La valeur est donc une HYPOTHESE, posee par la
    # sous-classe et justifiee par son i2.
    default_chance: Optional[int] = None

    def create_target_filter(self, state: State, ev: TriggerEvent, entities) -> bool:
        """Virtuel @vtable+0x758 -- le seul noeud specifique. `entities` = ctx DSL (caster=owner du trigger,
        target=le mourant)."""
        raise NotImplementedError

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        ouc = owner.get_component(UnitComponent)
        if ouc is None:
            return False
        # DeactivateEffect (once-per-turn) : l'effet est-il encore ACTIF ce tour ? (variante RemoveEffect :
        # le gate est le retrait de l'effet lui-meme, deja filtre par `collect_effect_triggers`.)
        if (not self.remove_effect) and ouc.revive_used_this_turn:
            return False
        dying = ev.dying_id
        if dying is None:
            return False
        if state.get_entity(dying) is None:
            return False
        # OnPreDeath(target, ignoreOverkill=get_ReviveOnOverkill) @180df7f10 -> OnDeathEvent @180df7ad0 :
        # byte==0 -> AJOUTE `NOT(HasFlag(dying, 8=overkill))` ; byte!=0 -> AUCUN gate overkill.
        if (not self.revive_on_overkill) and ev.overkill:
            return False
        # Contexte DSL (caster=owner, target=dying) pour has_trait/positions
        entities = entities_from_state(state, self.owner_id, dying)
        tgt = entities.target
        if tgt is None:
            return False
        # CanBeRevived(target)  (@181058a50)
        if not can_be_revived(entities, tgt, dying, state):
            return False
        # CreateTargetFilter (virtuel @+0x758)
        return bool(self.create_target_filter(state, ev, entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        # chance = GetReviveChance = GetNumberConstant(config, 0x2a='chance')
        chance = ability_var(self.ability_id, "chance", is_constant=self.chance_is_constant)
        if chance is None:
            chance = self.default_chance          # cf. `default_chance` (override litteral cote natif)
        if chance is None:
            return None
        entities = entities_from_state(state, self.owner_id, ev.dying_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        level, mult = self.revive_level(state)
        create_target_trigger_behaviour(int(chance), self.ability_id, self.hp_var,
                                        remove_effect=self.remove_effect,
                                        effect_type=self.effect_type,
                                        level=level, mult=mult).execute(entities, ectx)
        revives = [p for n, p in ectx.emitted if n == "Revive" and p.get("revived")]
        consumed = any(n in ("DeactivateReviveEffect", "RemoveReviveEffect") for n, _ in ectx.emitted)
        return {"ability": self.ability_id, "owner": self.owner_id, "dying": ev.dying_id,
                "chance": int(chance), "revives": revives, "gate_consumed": consumed,
                "rolled": state.rng is not None}


class ReviveEffectAbility(_ReviveEffectCore, TriggeredAbility):
    """Rail PASSIF : le `ReviveEffect` est pose d'office par un passiveAbility du porteur (Narthecium,
    TaintedNarthecium) -> collecte par `ABILITY_TRIGGERS[<passiveAbility>]`."""
    event_id = EventTriggerType.PreUnitDeath        # OnPreDeath -> OnDeathEvent(eventType=1)
    fire_on_death = False                           # owner (porteur) doit etre VIVANT au fire

    def revive_level(self, state: State):
        """`abilityState` du `GetReviveHP` = celui du PASSIF du porteur (l'effet est pose d'office par ce
        passif) -> `passive_ability_level` + `ability_variables_multiplier` du porteur."""
        e = state.get_entity(self.owner_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        if sc is None:
            return None, 100
        return (getattr(sc.ctx, "passive_ability_level", None),
                getattr(sc.ctx, "ability_variables_multiplier", 100))


class ReviveEffectTrigger(_ReviveEffectCore, EffectTrigger):
    """Rail EFFET : le `ReviveEffect` est POSE par une ability ACTIVE (RitesOfMorkai, ReanimationBeam)
    -> il apparait dans `state.effects` du porteur et est collecte par `EFFECT_TRIGGERS[effect_type]`."""
    event_id = EventTriggerType.PreUnitDeath        # OnPreDeath -> OnDeathEvent(eventType=1)

    def revive_level(self, state: State):
        """`abilityState` du `GetReviveHP` = celui de l'ABILITY ACTIVE qui a POSE l'effet (portee par
        l'effet, pas par l'unite qui le subit) -> on lit le niveau/multiplicateur SUR L'EFFET
        (`BaseEffect.active_ability_level`/`ability_level`, `ability_variables_multiplier`), jamais sur le
        porteur (un allie inspire peut avoir un tout autre niveau que Baldr)."""
        eff = getattr(state, "effects", None)
        if eff is not None:
            for e in (eff.by_unit.get(int(self.owner_id)) or []):
                if e.effect_type == self.effect_type:
                    lvl = e.active_ability_level if e.active_ability_level is not None else e.ability_level
                    return lvl, (e.ability_variables_multiplier or 100)
        return None, 100


def are_friends(state: State, a_id: int, b_id: int) -> bool:
    """`DSLFactory.AreFriends(self@0x148, target@0x178)` -- meme equipe (`OwnerComponent.team`). Present dans
    le filtre de Narthecium/TaintedNarthecium/ReanimationBeam (PAS de RitesOfMorkai, qui est OwnerIsTarget)."""
    ea, eb = state.get_entity(a_id), state.get_entity(b_id)
    if ea is None or eb is None:
        return False
    oa, ob = ea.get_component(OwnerComponent), eb.get_component(OwnerComponent)
    return oa is not None and ob is not None and oa.team == ob.team
