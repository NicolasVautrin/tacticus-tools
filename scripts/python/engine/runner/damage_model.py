"""Plage de tirage de dégât calculée PAR LE RUNNER depuis son ECS (stats + effets).

Le but du chantier : un runner AUTONOME (fidèle ET modifiable). Cette couche assemble,
depuis les composants ECS (`StatsComponent` + `State.effects`), les entrées de la chaîne
de dégât VALIDÉE (`engine.services.damage_prediction.get_attack_prediction`) — au lieu de
relire l'oracle live. Elle expose la **plage BRUTE d'un coup** (pré-armure, pré-perçage,
mono-coup) = le `HitDamage` que `AttackDamageOperation.ExecuteHit` tire.

Découpage volontaire (couche stats+effets uniquement) :
  • base PAR COUP = `stat Attack` (StatAmountFormula(Attack)) → spread BC (CalculateDamageSpread).
  • × MODIFIERS attaquant bâtis depuis les EFFETS actifs (post-perçage §17.7 ; pré-perçage = id
    ici car armure/perçage = 0). Effets pré-tirage (ex. +ExtraDmg sur le stat) déjà cuits dans
    `ctx.attack`.
  • PAS de hits / arme / perçage / armure / cible : ce sont des paliers DAMAGE séparés. La plage
    d'UN coup est indépendante d'eux (perçage/armure s'appliquent APRÈS le tirage).

Validé par agrément : plage runner == plage `aiPredict` (pré-armure) PAR COUP, sur les unités
(`tests/engine/runner/test_runner_stats_effects_live.py`).
"""
from __future__ import annotations

from typing import Optional, Tuple

from .state import State
from .components import StatsComponent, HealthComponent
from ..entities.stats import StatType
from ..services.damage_prediction import get_attack_prediction, apply_pierce_and_modifiers
from ..services.battle_query import (
    get_attack_weapon_for_default_normal_attack,
    select_weapon_pierce as _bq_select_weapon_pierce)
from ..entities.effects import (
    build_attacker_modifiers_from_effects, build_defender_modifiers_from_effects,
    hits_bonus_from_effects,
)

_BIG_HP = 1 << 30          # santé cible « infinie » → scenario sans overkill/cap


def _cheby(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def select_weapon(ctx, dist: Optional[int]):
    """Arme de l'attaque normale par PORTÉE — DÉLÈGUE au service PARTAGÉ
    `battle_query.get_attack_weapon_for_default_normal_attack` (foyer natif BattleQuery ; MÊME port que
    la prédiction). `dist` = distance hex du runner (1=adjacent via `board.neighbours`, 2=tir) → is_adjacent.
    Renvoie le dict d'arme gameconfig (ou None)."""
    w, _ranged = get_attack_weapon_for_default_normal_attack(
        ctx.visual_id, is_adjacent=(dist is not None and dist <= 1), prefer_hits=ctx.normal_hits)
    return w


def select_weapon_pierce(ctx, dist: Optional[int]) -> Tuple[int, bool, int]:
    """Arme + perçage par PORTÉE — DÉLÈGUE au service PARTAGÉ `battle_query.select_weapon_pierce`
    (un service natif = UN port, prédiction ET combat l'appellent). `dist` hex (1=adjacent) → is_adjacent.
    Renvoie `(pierce, is_ranged, whits)` (le profil est fourni séparément par `select_weapon`)."""
    pierce, is_ranged, whits, _prof = _bq_select_weapon_pierce(ctx, dist is not None and dist <= 1)
    return pierce, is_ranged, whits


def resolve_one_hit(roll: int, pierce: int, armor: int, mods=None) -> int:
    """Réduction d'UN coup tiré = **BASE COMMUNE** avec la prédiction : délègue à
    `apply_pierce_and_modifiers` (la fn par-valeur que la prédiction applique à ses bornes).
    Combat = même fn sur la valeur TIRÉE ⇒ dégâts identiques à la prédiction par construction."""
    return apply_pierce_and_modifiers(roll, pierce, armor, mods)


def attacker_modifiers(state: State, unit_id: int, hp: Optional[int], is_ranged: Optional[bool] = None):
    """`DamageModifiers` de l'attaquant depuis ses EFFETS actifs (None-safe). `is_ranged` = nature du coup
    (propagée aux bonus gated `IsRangedAttack`, ex. HeavyWeapon_ExtraDmg). `has_moved` (#60) = l'unité a-t-elle
    BOUGE ce tour (state.moved_this_turn) -> gate no-move : HeavyWeapon_ExtraDmg s'ANNULE si l'unité a bougé
    (verdict RE cluster #60 : le combat lisait has_moved=None -> bonus TOUJOURS appliqué, FAUX)."""
    active = (state.effects.active_effects(unit_id, {"hp": hp})
              if state.effects is not None else [])
    has_moved = unit_id in state.moved_this_turn
    return build_attacker_modifiers_from_effects(active, is_ranged, has_moved=has_moved), active


def defender_modifiers(state: State, unit_id: int, hp: Optional[int],
                       is_melee: Optional[bool] = None, damage_profile: Optional[str] = None):
    """`DamageModifiers` de réduction du DÉFENSEUR (cible) depuis ses EFFETS actifs (symétrique attaquant ;
    `CalculateDefenderModifiersForPrediction`). Renvoie (mods, active_effects). None-safe (mods vide → no-op).

    `is_melee`/`damage_profile` = nature du coup, propagés aux malus GATÉS (mirror de la prédiction, #59) :
    `IsMeleeAttack` (ex. Terrifying_ExtraDefense : `if not is_melee: return None`) et `DamageProfileIs`
    (ex. TerminatorArmour : PAS de réduction si profil ∈ Psychic/DirectDamage). None (défaut, ex. chemins
    ability non encore câblés) = comportement historique (les malus gatés IsMeleeAttack ne s'appliquent pas ;
    TerminatorArmour s'applique quel que soit le profil) — INERTE pour une cible sans effet de défense gaté."""
    active = (state.effects.active_effects(unit_id, {"hp": hp})
              if state.effects is not None else [])
    return build_defender_modifiers_from_effects(active, is_melee, damage_profile), active


def apply_elevation_bonus(state: State, mods, attacker_id: int, target_id: int) -> None:
    """#58 : ajoute au `mods` de l'ATTAQUANT le bonus d'ELEVATION (+surplomb) — feuille positionnelle du
    builder PARTAGE `CalculateAttackerModifiersForPrediction @181000590` que le COMBAT applique AUSSI
    (verdict RE cluster : misnomer "ForPrediction"). Elevations = `state.board` aux tuiles REELLES
    (attaquant/cible) ; gate no-elevation (effet 0x423 sur attaquant OU cible). No-op sans board/positions
    (mods inchange). MEME service `calculate_elevation_bonus_modifier` (DamageCalculations) que la
    prediction, MEME constante `ELEVATION_BONUS_PCT` (pas de fork)."""
    board = state.board          # toujours present (__slots__) ; None tant que le boardGraph n'est pas cale
    if board is None:
        return
    from .components import PositionComponent
    from ..services.damage_modifiers import (add_modifier, calculate_elevation_bonus_modifier,
                                             ELEVATION_BONUS_PCT, EFFECT_NO_ELEVATION)
    ea, et = state.get_entity(attacker_id), state.get_entity(target_id)
    pa = ea.get_component(PositionComponent) if ea is not None else None
    pt = et.get_component(PositionComponent) if et is not None else None
    if pa is None or pt is None:
        return
    ta, tt = board.tile_at(pa.col, pa.row), board.tile_at(pt.col, pt.row)
    if ta is None or tt is None:
        return
    a_elev, t_elev = ta.get("elevation"), tt.get("elevation")
    if a_elev is None or t_elev is None:
        return

    def _has_no_elev(uid: int) -> bool:
        e = state.get_entity(uid)
        hc = e.get_component(HealthComponent) if e is not None else None
        effs = (state.effects.active_effects(uid, {"hp": hc.hp if hc is not None else None})
                if state.effects is not None else [])
        return any(getattr(ef, "effect_type", None) == EFFECT_NO_ELEVATION for ef in effs)

    no_elev = _has_no_elev(attacker_id) or _has_no_elev(target_id)
    eb = calculate_elevation_bonus_modifier(a_elev, t_elev, ELEVATION_BONUS_PCT,
                                            attacker_or_target_has_no_elev_effect=no_elev)
    if eb is not None:
        add_modifier(mods, eb)


def build_hits_board(state: State, att_id: int, tgt_id: int,
                     attack_pos, t_pos, is_melee: Optional[bool]):
    """Bâtit `(board, aura_sources, target_effects)` pour `attack_hits_with_modifiers` depuis l'ECS
    (positions/teams/effets REELS). `board` = {att_id, tgt_id, attack_pos, t_pos, tgt_team, is_melee,
    pos_by_id, team_by_id} (base_hits posé par la Formule) ; `aura_sources` = [(owner_id, pos, team, effets)]
    des unités != cible (porteurs d'auras de coups type BigTarget) ; `target_effects` = effets actifs de la
    cible (LightCover/Parry). Identité = **entity_id**, team = **OwnerComponent.team** (instance-safe). PAS
    de `faction_of`/visual_id : le comptage par faction de GetStuckIn est retiré, aucun consommateur ne le
    lit — et `visual_id` ne distinguerait pas 2 instances du même type en miroir (danger connu)."""
    from .components import PositionComponent, OwnerComponent, HealthComponent
    pos_by_id: dict = {}
    team_by_id: dict = {}
    aura_sources = []
    target_effects: list = []
    for uid, e in state.entities.items():
        pc = e.get_component(PositionComponent)
        oc = e.get_component(OwnerComponent)
        hc = e.get_component(HealthComponent)
        if pc is not None:
            pos_by_id[uid] = (pc.col, pc.row)
        if oc is not None:
            team_by_id[uid] = oc.team
        effs = (state.effects.active_effects(uid, {"hp": hc.hp if hc is not None else None})
                if state.effects is not None else [])
        if uid == tgt_id:
            target_effects = effs
        else:
            aura_sources.append((uid, pos_by_id.get(uid), team_by_id.get(uid), effs))
    board = {"att_id": att_id, "tgt_id": tgt_id, "attack_pos": attack_pos, "t_pos": t_pos,
             "tgt_team": team_by_id.get(tgt_id), "is_melee": is_melee,
             "pos_by_id": pos_by_id, "team_by_id": team_by_id}
    return board, aura_sources, target_effects


def normal_attack_per_hit_range(state: State, unit_id: int) -> Optional[dict]:
    """Plage BRUTE (pré-armure) d'UN coup d'attaque normale de l'unité, calculée depuis
    l'ECS (StatsComponent + effets actifs). Renvoie `{min, max, base, effects, hasMods}`
    ou None si l'unité n'a pas de StatsComponent (stats non chargées).

    `min/max` = ce que `HitDamage.GetDamage` tirera (avant réduction perçage/armure)."""
    e = state.get_entity(unit_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return None
    ctx = sc.ctx
    hc = e.get_component(HealthComponent) if e is not None else None
    hp = hc.hp if hc is not None else None
    active = (state.effects.active_effects(unit_id, {"hp": hp})
              if state.effects is not None else [])
    mods = build_attacker_modifiers_from_effects(active)
    # armure=0 & perçage=100 → réduction = identité ⇒ la plage retournée est BRUTE (pré-armure),
    # = ce que `aiPredict` (pré-armure) renvoie par coup ; les MODIFIERS d'effet sont inclus.
    res = get_attack_prediction(
        target_current_health=_BIG_HP, initial_damage=ctx.stat(StatType.ATTACK), hits=1,
        profile_type=ctx.damage_type, armor=0, pierce_pct=100, mods=mods)
    r = res.accurate_health_damage
    return {
        "min": r.min, "max": r.max, "base": ctx.stat(StatType.ATTACK),
        "effects": [getattr(ef, "name", None) for ef in active],
        "hasMods": bool(mods is not None and (mods.pct_list or getattr(mods, "additive", 0))),
    }
