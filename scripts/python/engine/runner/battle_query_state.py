"""`IdunBattle.Core.Services.BattleQuery` monte depuis l'ECS `State` -- le SUBSTRAT, pas la regle.

Le SWITCH de `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` (slot 2 d'`IBattleQuery`) vit dans
UN seul endroit du port : `engine.services.battle_query.is_melee_attack`. Ce module-ci ne le
reecrit pas -- il ASSEMBLE ce que le foyer attend a partir d'un `State` runner (positions, graphe du
board, elevation, `UnitFlagsComponent`), parce que le natif prend ces quatre choses de l'etat de
match et que trois sites du port les remontaient chacun a sa facon.

Pourquoi un module, et pas une fonction de plus dans l'un des trois :
`operations/damage_utility.py` (face DECISION), `abilities/loki/heavy_bolt_pistol.py` (face COMBAT)
et `operations/triggers/loki/empyric_ambush.py` (face TRIGGER) consomment le MEME slot natif. Le
montage n'appartient a aucun des trois, et `abilities/targeting.py` -- ou vivent deja `_visual_id` /
`normal_attack_type_for` -- charge `operations/damage_utility.py`, donc l'y poser fermerait un cycle.

⚠ `caster_position` est un ARGUMENT, pas une lecture. C'est litteralement le 3e parametre du natif
(`IsMeleeAttack(ability, caster, casterPosition, target)`), et il vient de
`AbilityEntities.CasterPosition`, que `IdunBattle.Entities.Abilities.TriggerAbilityBehaviour$$Execute`
NE reecrit PAS quand il reecrit actor/caster/target/tuiles. Les appelants qui n'ont pas d'ancre
d'ability passent `None` et le module lit la position REELLE -- ce qui est correct partout ou les
deux coincident, et NOMME la ou elles pourraient diverger (residu `#419-r1-tr14-r4-r3`).
"""
from __future__ import annotations

from typing import Optional

from ..entities.active_ability_type import ActiveAbilityType
from ..entities.unit_flag import UnitFlag
from ..services.battle_query import is_melee_attack as _svc_is_melee_attack
from .components import PositionComponent, UnitFlagsComponent


def unit_position(state, unit_id) -> Optional[tuple]:
    """`IdunBattle.Entities.EntityExtensions$$GetUnitPosition(unit)` reduit a sa MAIN TILE --
    la tuile que les appelants du slot 2 passent en `casterPosition` quand aucune ancre d'ability
    ne la leur donne. `None` = pas de `PositionComponent` (entite morte ou hors board)."""
    e = state.get_entity(int(unit_id)) if unit_id is not None else None
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def force_ranged_attack(state, unit_id) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$HasFlag(caster, 0x15)` = `UnitFlag.ForceRangedAttack`
    (21), le premier conjoint de la branche `Normal(3)` du switch.

    Composant absent -> `False`. Le capteur `combatSnapshot.unitFlags` ne publie pas ce drapeau
    (residu `#419-r1-tr5-r1`) : degradation PERMISSIVE-EN-PLUS et NOMMEE -- on ne devine pas un
    drapeau qu'on ne mesure pas."""
    e = state.get_entity(int(unit_id)) if unit_id is not None else None
    fl = e.get_component(UnitFlagsComponent) if e is not None else None
    return bool(fl is not None and fl.has(UnitFlag.ForceRangedAttack))


def board_maps(state):
    """`(neigh_by_pos, elev_by_pos)` du board du runner -- le substrat de
    `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent` (`ConnectivityComponent` + elevation).
    `(None, None)` quand le `State` n'a pas de board (scene de test) : le foyer degrade alors en
    adjacence hex pure, degradation deja nommee dans sa docstring."""
    board = getattr(state, "board", None)
    if board is None:
        return None, None
    neigh, _walk, elev = board.walk_maps_by_pos()
    return neigh, elev


def normal_attack_name(state, unit_id) -> Optional[str]:
    """Le NOM d'`ActiveAbilityType` de l'attaque normale CONCRETE de l'entite -- c'est l'`ability`
    que le natif passe au slot 2 quand il predit l'attaque normale
    (`IdunBattle.Entities.UnitExtensions$$GetNormalAttackType(owner)`).

    Delegue a `runner.abilities.targeting.normal_attack_type_for`, FOYER UNIQUE de la cascade
    `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` cote runner ; on ne
    re-derive rien ici.

    ⚠ Le differe est PORTEUR, mesure : `import engine.runner.abilities.targeting` en process FRAIS
    charge `engine.runner.operations.damage_utility`, qui est l'un des consommateurs de ce module --
    hisser fermerait donc un cycle.

    `None` = l'entite n'a pas d'attaque normale resoluble ; l'appelant retombe alors sur la branche
    `Normal(3)`, ce qui est EXACTEMENT ce que le natif fait pour les 18 ids d'attaque normale du
    build courant (aucun n'a d'entree gameconfig, donc aucun `attackRangeType` -- mesure gardee par
    `probe_494r2_attack_range_type_normal.py` et par `test_494r2_normal_attack_is_melee_offline`)."""
    from .abilities.targeting import normal_attack_type_for   # differe PORTEUR (cf. docstring)
    aid = normal_attack_type_for(state, unit_id)
    if aid is None:
        return None
    try:
        return ActiveAbilityType(int(aid)).name
    except ValueError:
        return None


def is_melee_attack(state, ability_name: Optional[str], caster_id, target_id,
                    caster_position: Optional[tuple] = None) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack(ability, caster, casterPosition, target)`
    monte depuis le `State`. Le switch lui-meme est DANS
    `engine.services.battle_query.is_melee_attack` -- ici on ne fait que lui donner son substrat.

    `caster_position` = l'ancre d'ability (`AbilityEntities.CasterPosition`) quand l'appelant en a
    une ; `None` -> la position REELLE du caster (cf. l'avertissement d'en-tete).

    Cible absente / positions absentes -> `False` : le natif deref sans garde, on ne mirroir pas une
    levee, et l'absence de position ne peut pas valoir « au contact »."""
    if target_id is None:
        return False
    cpos = caster_position if caster_position is not None else unit_position(state, caster_id)
    tpos = unit_position(state, target_id)
    if cpos is None or tpos is None:
        return False
    neigh, elev = board_maps(state)
    return bool(_svc_is_melee_attack(ability_name, cpos, tpos, elev_by_pos=elev,
                                     force_ranged_attack=force_ranged_attack(state, caster_id),
                                     neigh_by_pos=neigh))


def normal_attack_is_melee(state, caster_id, target_id,
                           caster_position: Optional[tuple] = None) -> bool:
    """`IsMeleeAttack(GetNormalAttackType(caster), caster, casterPosition, target)` -- la forme que
    prend le slot 2 quand l'ability evaluee est l'ATTAQUE NORMALE du caster.

    C'est ce que `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` interroge (via
    `IdunBattle.Core.Services.DamagePrediction$$IsMeleeAttack`, qui delegue au meme slot) et ce que
    la face COMBAT interroge pour ses gates de nature de coup."""
    return is_melee_attack(state, normal_attack_name(state, caster_id), caster_id, target_id,
                           caster_position=caster_position)


__all__ = ["board_maps", "force_ranged_attack", "is_melee_attack", "normal_attack_is_melee",
           "normal_attack_name", "unit_position"]
