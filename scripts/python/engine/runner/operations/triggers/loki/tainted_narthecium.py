"""`Abilities.Effects.Loki.TaintedNarthecium_ReviveEffect` (base `ReviveEffect`) -- passif de deathRotbone
(Death Guard/Chaos) : un allie Chaos adjacent(2) vaincu a 75% de chance d'etre revive-EN-PLACE a
min(reviveHP[level], maxPV), even-if-Overkilled, once-per-turn. case-66 (debloqueur sous-systeme REVIVE).

RE ghidra gqfc5mff6c (VA citees) + i2 authoritatif (« An adjacent friendly Chaos unit that is defeated has
a {chance}% chance to be revived with a maximum of {hp} Health, even if Overkilled. Can only be triggered
once per turn. »).

Artefact natif (frontiere #149) :
  base ReviveEffect.CreateTargetTrigger        @180f46d80  = OnPreDeath(target, ignoreOverkill) &
                                                             CanBeRevived(target) & CreateTargetFilter
  TaintedNarthecium_ReviveEffect.CreateTargetFilter @180f709b0 = baseFilter & AreFriends(self,target) &
                                                             HasTrait(target, Chaos=0x7ea=2026) &
                                                             IsAdjacent(self, target, 2)
  base ReviveEffect.CreateTargetTriggerBehaviour @180f46a70 = Maybe(chance){
                                                             Revive(self, target, Min(reviveHP,
                                                                    StatAmount(target,Health,max)), tile,
                                                                    sourceId=1067) ; DeactivateEffect }
  TaintedNarthecium ctor @180f70a90 : ReviveEffect.ctor(source=AbilityOrEffect(0x42b=1067)) ; ne surcharge
  QUE CreateTargetFilter (GetReviveHP=var 'hp' / GetReviveChance=const 'chance' herites -> gameconfig
  TaintedNarthecium).

Points RE cles :
- `OnPreDeath` @180df7f10 -> `OnDeathEvent(1, byte_738, 0)` @180df7ad0 : le byte (virtuel `GetIgnoreOverkill`
  @vtable+0x738) CONTROLE le gate overkill -- byte==0 -> ajoute `NOT(HasFlag(dying, 8=overkill))` (Narthecium,
  « unless Overkilled ») ; byte!=0 -> AUCUN gate overkill (TaintedNarthecium, « even if Overkilled »). D'ou :
  le port de TaintedNarthecium NE gate PAS sur `ev.overkill`. (Un 2e gate `NOT(CurrentShield(dying,0x1b))`
  = shield==0, TOUJOURS present -- implicite a la mort, non modelise.)
- `CanBeRevived` @181058a50 : `GetStat(unit,Health,0)<1` (mort) & IsAffectedByHealType(healType) &
  NOT flag 0xd & NOT HasTrait(PermaDeath=0x41a=1050) & NOT HasHealBlockers. Port : hp<1 & non-PermaDeath &
  (HasTrait(AffectedByHealAndRepair) OR NOT IsMechanical). Flag 0xd / HealBlockers non modelises (le flag
  overkill 0xd n'est pas encore pose au moment de l'OnPreDeath -> non-bloquant).
- `Maybe` @180fc9dc0 : 1 tirage `next_bool(chance=75)` ; DeactivateEffect (once-per-turn) execute UNIQUEMENT
  sur SUCCES du roll (dans le func) -> un roll RATE ne consomme PAS le gate (re-roll a la mort adjacente
  suivante du meme tour) ; « once per turn » = once SUCCESSFULLY revived per turn.
- HP = `Min(reviveHP[passive level, rarity-scaled], target.maxPV)` (reviveHP dans variablesAffectedByRarityBonus).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import StatsComponent, OwnerComponent, UnitComponent, HealthComponent
from ....abilities.behaviours import entities_from_state
from ....abilities.behaviours.stats import is_mechanical
from .....entities.behaviours import op_add, Maybe
from .....entities.selectors import Caster, Target
from .....entities.traits.unit_trait import UnitTrait
from .....entities.effects.magnitude import ability_var
from .....dsl.base import _units_of, _pos
from .....dsl.effects import AbilityBehaviour, OperationResult, ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent

import hexgeo

ABILITY_ID = "TaintedNarthecium"
CHAOS = int(UnitTrait.Chaos)                     # 0x7ea=2026 (HasTrait(target, Chaos))
PERMADEATH = int(UnitTrait.PermaDeath)           # 0x41a=1050 (NOT HasTrait -> CanBeRevived)
AFFECTED_BY_HEAL = int(UnitTrait.AffectedByHealAndRepair)  # 0x421=1057 (IsAffectedByHealType)
ADJACENCY_RANGE = 2                              # IsAdjacent(self, target, 2)


class Revive(AbilityBehaviour):
    """Feuille DSL `Revive` (`DSLFactory.Revive @180dfa4f0` -> `ReviveBehaviour.Execute @180fd1230`) : revive
    CHAQUE unite du selecteur `target_sel` (le mourant, `Target()@0x178`) a `Min(reviveHP, target.maxPV)`.
    Frontiere #149 : la FEUILLE (declaratif, ICI) APPELLE l'Operation IMPERATIVE `ReviveUnitOperation.execute`
    (operations/revive.py, EN-DESSOUS) -- on NE fusionne PAS. `reviveHP` = `ability_var(ability_id, 'hp',
    passive_level_du_CASTER, mult)` (mirror `GetReviveHP` = var 'hp' scalee rarete) ; `Min(reviveHP,
    target.hp_max)` = le noeud `Min(Direct(GetReviveHP), StatAmount(target, Health, max))` du behaviour natif.
    PUR (stop=False)."""
    __slots__ = ("target_sel", "ability_id", "hp_var")

    def __init__(self, target_sel, ability_id: str, hp_var: str = "hp"):
        self.target_sel, self.ability_id, self.hp_var = target_sel, ability_id, hp_var

    def execute(self, entities, ectx):
        from ...revive import ReviveUnitOperation
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        caster = entities.caster or {}
        cid = caster.get("id") if isinstance(caster, dict) else None
        ce = state.get_entity(cid) if cid is not None else None
        csc = ce.get_component(StatsComponent) if ce is not None else None
        level = getattr(csc.ctx, "passive_ability_level", None) if csc is not None else None
        mult = getattr(csc.ctx, "ability_variables_multiplier", 100) if csc is not None else 100
        revive_hp = ability_var(self.ability_id, self.hp_var, level, multiplier_pct=mult)  # GetReviveHP
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
            r = ReviveUnitOperation.execute(state, tid, hp)  # -> mutateur ECS impuratif (revive-en-place)
            ectx.emit("Revive", target=tid, hp=(r or {}).get("hp"), revive_hp=revive_hp,
                      revived=r is not None)
        return OperationResult.ok()


class ConsumeReviveGate(AbilityBehaviour):
    """Feuille `DeactivateEffect` (2e volet de l'`op_add` du `CreateTargetTriggerBehaviour @180f46a70`, execute
    APRES le `Revive` sur SUCCES du `Maybe`) : DESACTIVE l'effet revive du porteur -> gate once-per-turn.
    Port : pose `revive_used_this_turn=True` sur le CASTER (`Caster()@0x148`, owner du passif) ; reactive au
    turn-start (`reset_revive_gates`). PUR (stop=False)."""
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


def tainted_narthecium_revive_tree(chance: int):
    """Arbre de `ReviveEffect.CreateTargetTriggerBehaviour @180f46a70` (MIRROR) :
        Maybe(chance){ op_add( Revive(Target(), Min(reviveHP, target.maxPV)) ,
                               DeactivateEffect(Caster()) ) }
    Le `Maybe` fait 1 tirage `next_bool(chance)` ; sur SUCCES : Revive PUIS DeactivateEffect (consomme le gate
    once-per-turn). Sur ECHEC : rien (gate NON consomme)."""
    return Maybe(chance, op_add(
        Revive(Target(), ABILITY_ID),        # DSLFactory.Revive -> ReviveUnitOperation (revive-en-place)
        ConsumeReviveGate(Caster())))        # DSLFactory.DeactivateEffect -> gate once-per-turn


def _can_be_revived(entities, target_liveunit, target_id: int, state: State) -> bool:
    """`BattleQuery.CanBeRevived @181058a50` (mirror) : `GetStat(unit,Health,0)<1` (mort) & IsAffectedByHealType
    & NOT flag 0xd & NOT HasTrait(PermaDeath=1050) & NOT HasHealBlockers. Port : hp<1 (mort) & NOT PermaDeath &
    IsAffectedByHealType(0) = `HasTrait(AffectedByHealAndRepair) OR NOT IsMechanical` (mirror @180ed77d0 via le
    helper partage `is_mechanical`). Flag 0xd (overkill pas encore pose a l'OnPreDeath) & HealBlockers non
    modelises -> non-bloquants."""
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


class TaintedNartheciumReviveAbility(TriggeredAbility):
    """`TaintedNarthecium_ReviveEffect` (base `ReviveEffect`, ctor @180f70a90 / filter @180f709b0) -- passif
    revive-en-place de deathRotbone.

    `CreateTrigger` (base @180f46d80 + filtre @180f709b0) = `OnPreDeath(target, ignoreOverkill=TRUE) &
    CanBeRevived(target) & AreFriends(self,target) & HasTrait(target, Chaos) & IsAdjacent(self,target,2)`.
    `ignoreOverkill=TRUE` (virtuel 0x738 non-nul) -> AUCUN gate overkill (even if Overkilled). Behaviour
    (base @180f46a70) = `Maybe(chance=75){ Revive(...) ; DeactivateEffect }`.

    `matches` = checks directs (idiome ActOfFaith/FinalJustice) mirroir de chaque noeud du CreateTrigger ;
    `execute_behaviour` = arbre DSL `tainted_narthecium_revive_tree` (Maybe + Revive-leaf + gate). Le gate
    once-per-turn = `owner.revive_used_this_turn` (mirror effet DESACTIVE apres revive, reactive au turn-start)."""
    event_id = EventTriggerType.PreUnitDeath        # OnPreDeath -> OnDeathEvent(1)
    fire_on_death = False                           # owner (porteur du passif) doit etre VIVANT au fire

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        owner = state.get_entity(self.owner_id)
        if owner is None:
            return False
        ouc = owner.get_component(UnitComponent)
        oown = owner.get_component(OwnerComponent)
        if ouc is None or oown is None:
            return False
        # DeactivateEffect (once-per-turn) : l'effet est-il encore ACTIF ce tour ?
        if ouc.revive_used_this_turn:
            return False
        dying = ev.dying_id
        if dying is None:
            return False
        de = state.get_entity(dying)
        if de is None:
            return False
        # AreFriends(self, target) : meme equipe
        down = de.get_component(OwnerComponent)
        if down is None or down.team != oown.team:
            return False
        # Contexte DSL (caster=owner, target=dying) pour has_trait/positions (mirror ctx RevitalizingMalignancy)
        entities = entities_from_state(state, self.owner_id, dying)
        tgt = entities.target
        if tgt is None:
            return False
        ht = entities.has_trait
        # HasTrait(target, Chaos=0x7ea=2026)  (== GrandAlliance Chaos ; mirror @180f709b0)
        if ht is None or not ht(tgt, CHAOS):
            return False
        # IsAdjacent(self, target, 2) : distance hex <= 2 (helper 0x5f + range 2 @180f709b0)
        pa, pb = _pos(entities.caster), _pos(tgt)
        if pa is None or pb is None or hexgeo.distance(pa, pb) > ADJACENCY_RANGE:
            return False
        # CanBeRevived(target)  (@181058a50)
        if not _can_be_revived(entities, tgt, dying, state):
            return False
        # OnPreDeath ignoreOverkill=TRUE -> AUCUN gate `ev.overkill` (even if Overkilled)
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        # chance = GetReviveChance = GetNumberConstant(config, 'chance') = 75 (const, non scalee)
        chance = ability_var(ABILITY_ID, "chance", is_constant=True)
        if chance is None:
            return None
        entities = entities_from_state(state, self.owner_id, ev.dying_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        tainted_narthecium_revive_tree(int(chance)).execute(entities, ectx)
        revives = [p for n, p in ectx.emitted if n == "Revive" and p.get("revived")]
        consumed = any(n == "DeactivateReviveEffect" for n, _ in ectx.emitted)
        return {"ability": ABILITY_ID, "owner": self.owner_id, "dying": ev.dying_id,
                "chance": int(chance), "revives": revives, "gate_consumed": consumed,
                "rolled": state.rng is not None}
