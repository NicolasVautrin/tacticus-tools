"""TheQuickening (active 1151, bloodMephiston) — teleport-ECHANGE + free melee attack faction-gatee.

`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$ExecuteBehaviour` (IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$.ctor) : cast TILE-TARGET (le joueur/IA
choisit une TUILE a portee-mouvement 2). Le caster s'y TELEPORTE ; l'unite eventuellement presente sur la
tuile (filtre `Attackable`) est ECHANGEE vers la tuile d'origine du caster. Puis le caster ET l'unite
echangee, SI faction BloodAngels (natif `HasFaction(unit, 0xe=14)`), executent une attaque melee immediate
depuis leur nouvelle position, avec le stat Attack OVERRIDE par la formule config
(`PercentageOfAttackCappedAtMax`).

Arbre natif (`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$ExecuteBehaviour`, 7 `AActiveAbility.Execute` sequentiels) :
  1. `SetCache(CasterTile@0x168) & Reserve(Caster@0x160, Target@0x178) &
      GetMoveOutBehaviour(Caster) & GetMoveOutBehaviour(Attackable@Target)`
  2. `GetMoveInBehaviour(Caster -> Target) & GetMoveInBehaviour(Attackable -> CasterTile@0x168)`
  3. `GetTriggerMovementAbilitiesBehaviour(Caster)`   (EvaluateAbilities(0x1c=28) on-move)
  4. `GetTriggerAttackBehaviour(Caster)`               (free attack, gate HasFaction 14)
  5. `GetTriggerMovementAbilitiesBehaviour(Attackable)`
  6. `GetTriggerAttackBehaviour(Attackable)`
  7. `InvalidateCaches`

`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$GetMoveOutBehaviour` : `RemoveEffect(EffectFromOwner(unit, 0x19)) & AddEffect(0x414 Untargetable,
caster-src, unit) & MoveUnit(unit -> Null)`  (lift off-board, marqueur transit).
`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$GetMoveInBehaviour`  : `MoveUnit(unit -> tile) & RemoveEffect(unit, 0x414)`  (atterrissage).
`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$GetTriggerAttackBehaviour` : `If(HasFaction(unit, 0xe=14),
    AddStatOverrideEffect(unit, 0x510 Attack_Override, PercentageOfAttackCappedAtMax(Attack, dmgPct, maxDmg))
    & AddEffect(0x529 ForcedInMelee, ...) & PerformAIAttackFromCurrentPosition(unit)
    & RemoveEffect(unit, 0x510) & RemoveEffect(unit, 0x529))`.

MESURE LIVE (probe_217, runner build) — cast de meph(2,6) sur tuile ally(4,7) : POST meph=(4,7)
ally=(2,6) (SWAP net) ; effets Untargetable(0x414)/ForcedInMelee(0x529)/TemporaryStatOverride(0x510)
TOUS ajoutes ET retires DANS le cast (net-zero, aucun effet persistant) ; Attack_Override meph=1204,
ally=4818 = la formule config. Le port materialise donc l'observable NET :
  - l'ECHANGE de positions (deterministe, coeur de la divergence) ;
  - la free-attack melee faction-BloodAngels (override Attack, cible ennemi adjacent) via
    `set_stat_override`(= 0x510) + le pipeline d'attaque normale + `remove_stat_override`.

RESIDUS documentes (case-217) :
  - EvaluateAbilities(28) (phases 3/5, on-move triggers) NON porte -> surface passive separee
    (aucun on-move passif BloodAngels au roster teste) ;
  - le filtre `Attackable = UnitsWithoutTrait(0x1b=27)` du swap-unit est APPROXIME par « toute unite
    vivante sur la tuile cible autre que le caster » (aucune unite trait-27 sur une tuile de swap teste) ;
  - le CHOIX de cible de `PerformAIAttackFromCurrentPosition` (AI natif) est approxime par l'ennemi
    ADJACENT le plus proche (ForcedInMelee -> melee, dist 1) ; le roll de degat reste RNG (non bit-exact).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC
import hexgeo

from ..base import ActiveAbility
from ...operations.damage import AttackDamageOperation
from ...operations.movement import MoveUnitOperation
from ...components import (StatsComponent, OwnerComponent, PositionComponent,
                          UnitComponent)
from ....entities.stats import StatType
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.effects.magnitude import ability_var
from ....dsl.effects import ExecutionContext

if TYPE_CHECKING:
    from ...state import State

# `HasFaction(unit, 0xe=14)` IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$GetTriggerAttackBehaviour : faction hardcodee du gate free-attack = BloodAngels (la
# faction de Mephiston, le porteur ; l'echange ne beneficie du coup gratuit QU'aux BloodAngels).
_BLOODANGELS = "BloodAngels"
_ABILITY = "TheQuickening"


def _pos(e) -> Optional[tuple]:
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _tile_pos(state: "State", tile_id) -> Optional[tuple]:
    board = getattr(state, "board", None)
    if board is None or tile_id is None:
        return None
    t = board.by_id.get(tile_id) if hasattr(board, "by_id") else None
    if not t:
        return None
    return (t.get("col"), t.get("row"))


def _living_unit_id_on(state: "State", pos: tuple, exclude_id: int) -> Optional[int]:
    """Id de l'unite VIVANTE occupant la tuile `pos` (autre que `exclude_id`) — approx du selecteur natif
    `Attackable(Units(Target)) = UnitsWithoutTrait(0x1b=27)` (le filtre trait-27 n'est pas materialise :
    aucune unite trait-27 sur une tuile de swap teste). Tie-break `id` (deterministe)."""
    best = None
    for oid, e in state.entities.items():
        if oid == exclude_id:
            continue
        uc = e.get_component(UnitComponent)
        if uc is not None and not uc.alive:
            continue
        if _pos(e) == pos and (best is None or oid < best):
            best = oid
    return best


def _unit_faction(state: "State", unit_id: int) -> Optional[str]:
    """FactionId (string gameconfig) de l'unite — gate `HasFaction(unit, 0xe=14=BloodAngels)`."""
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    vis = uc.visual_id if uc is not None else None
    if vis is None:
        return None
    return (GC.unit(vis) or {}).get("FactionId")


def _quickening_override(state: "State", attacker_id: int, level, mult: int) -> Optional[int]:
    """Valeur d'override Attack de la free-attack = `IdunBattleLogic.Entities.DSLFactory$$PercentageOfAttackCappedAtMax` :
    `min(maxDmg[level]xmult, round(unit.Attack x dmgPct[level]/100))`. `level`/`mult` = ceux de
    l'ability de MEPH (config lue via `ability+0x60`) ; `Attack` = celui de l'unite qui attaque
    (`StatAmount(unit, Attack)`). maxDmg est rarity-scale (`variablesAffectedByRarityBonus`), dmgPct non."""
    e = state.get_entity(attacker_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return None
    atk = int(sc.ctx.stat(StatType.ATTACK))
    pct = ability_var(_ABILITY, "dmgPct", level, multiplier_pct=mult)          # non rarity-scale -> mult inerte
    cap = ability_var(_ABILITY, "maxDmg", level, multiplier_pct=mult)          # rarity-scale par mult
    if pct is None:
        return None
    val = round(atk * int(pct) / 100.0)
    if cap is not None:
        val = min(val, int(cap))
    return int(val)


def _nearest_adjacent_enemy(state: "State", unit_id: int) -> Optional[int]:
    """Ennemi VIVANT ADJACENT (dist hex 1) — cible de la free-attack MELEE (ForcedInMelee -> melee only).
    Approx du choix AI natif de `PerformAIAttackFromCurrentPosition`. None si aucun adjacent. Tie-break id."""
    e = state.get_entity(unit_id)
    pc = e.get_component(PositionComponent) if e is not None else None
    oc = e.get_component(OwnerComponent) if e is not None else None
    if pc is None or oc is None:
        return None
    src = (pc.col, pc.row)
    best = None
    for oid, o in state.entities.items():
        if oid == unit_id:
            continue
        ooc = o.get_component(OwnerComponent)
        ouc = o.get_component(UnitComponent)
        opc = o.get_component(PositionComponent)
        if ooc is None or opc is None or ooc.team == oc.team:
            continue
        if ouc is not None and not ouc.alive:
            continue
        if hexgeo.distance(src, (opc.col, opc.row)) != 1:      # ForcedInMelee -> adjacent seulement
            continue
        if best is None or oid < best:
            best = oid
    return best


def _free_melee_attack(state: "State", unit_id: int, level, mult: int) -> Optional[dict]:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$GetTriggerAttackBehaviour` pour UNE unite (gate `HasFaction 14`=BloodAngels deja
    verifie par l'appelant). Mirror : `AddStatOverrideEffect(0x510)` -> `PerformAIAttackFromCurrentPosition`
    -> `RemoveEffect(0x510)`. Le `set_stat_override(ATTACK, V)` = le canal 0x510 (Attack_Override) ; le
    pipeline d'attaque normale lit `ctx.stat(ATTACK)=V` (base=V) ; l'override est RETIRE apres (net-zero,
    conforme a la cascade live). None si rng non cale / pas de cible adjacente / override indisponible."""
    if state.rng is None:
        return None
    tgt = _nearest_adjacent_enemy(state, unit_id)
    if tgt is None:
        return None                                            # PerformAIAttack no-op sans cible (trace live)
    V = _quickening_override(state, unit_id, level, mult)
    if V is None:
        return None
    e = state.get_entity(unit_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return None
    sc.ctx.stats.set_stat_override(StatType.ATTACK, int(V))     # 0x510 TemporaryStatOverride (Attack_Override)
    try:
        r = AttackDamageOperation.execute(state, unit_id, tgt)  # dist 1 -> arme melee auto (ForcedInMelee)
    finally:
        sc.ctx.stats.remove_stat_override(StatType.ATTACK)      # RemoveEffect(0x510) -> net-zero
    if r is None:
        return None
    return {"attacker": unit_id, "target": tgt, "override": int(V), "total": r.get("total")}


class TheQuickeningAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$ExecuteBehaviour` (id 1151, bloodMephiston). Cast TILE-TARGET :
    le caster se TELEPORTE sur la tuile ciblee (portee-mouvement 2) ; l'unite eventuellement presente y
    est ECHANGEE vers la tuile d'origine du caster ; puis caster + unite-echangee (SI BloodAngels)
    attaquent en melee depuis leur nouvelle position (Attack override par la formule config).

    `target_id` = id de TUILE (cast tile-target, `NCContext.tile_id_by_pos` cote decision ; abilityTargets
    kind='tile'). IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$.ctor : `TargetingOptions(...,0x806000000)` + `AActiveAbility(...,2)`."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.TheQuickening)  # 1151

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        board = getattr(state, "board", None)
        caster = state.get_entity(caster_id)
        if caster is None or board is None:
            return {"quickening": True, "swapped": None, "moved": False}
        origin = _pos(caster)
        target_pos = _tile_pos(state, target_id)
        if target_pos is None or origin is None or target_pos == origin:
            return {"quickening": True, "swapped": None, "moved": False}
        # unite echangee = occupant vivant de la tuile cible (approx `Attackable(Units(Target))`)
        swap_id = _living_unit_id_on(state, target_pos, caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)     # porte le bus des Operations (MoveUnit)
        # --- phases 1-2 : SWAP (MoveOut+MoveIn ; effets Untargetable transitoires = net-zero) ---------
        # natif = lift-off (MoveUnit -> Null) puis MoveIn ; MoveUnitOperation pose la position sans check
        # d'occupation -> l'echange direct (caster->target, swap->origin) rend l'etat NET identique.
        MoveUnitOperation(caster_id, target_pos).execute(state, ectx.bus)
        if swap_id is not None:
            MoveUnitOperation(swap_id, origin).execute(state, ectx.bus)
        # --- phases 4/6 : free melee attack faction-BloodAngels (caster PUIS unite-echangee) ----------
        # config (maxDmg/dmgPct/level/mult) = celle de l'ability de MEPH (le caster) ; Attack = per-unit.
        csc = caster.get_component(StatsComponent)
        level = getattr(csc.ctx, "active_ability_level", None) if csc else None
        mult = int(getattr(csc.ctx, "ability_variables_multiplier", 100) or 100) if csc else 100
        attacks = []
        for uid in ([caster_id] + ([swap_id] if swap_id is not None else [])):
            if _unit_faction(state, uid) != _BLOODANGELS:      # gate HasFaction(unit, 14)
                continue
            a = _free_melee_attack(state, uid, level, mult)
            if a is not None:
                attacks.append(a)
        return {"quickening": True, "caster": caster_id, "target_tile": target_id,
                "to": target_pos, "swapped": swap_id, "moved": True, "attacks": attacks, "dsl": False}
