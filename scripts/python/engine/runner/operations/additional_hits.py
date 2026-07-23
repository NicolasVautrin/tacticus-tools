"""Canal COUPS ADDITIONNELS HETEROGENES (#179/#202-B) — face COMBAT, extrait de
`AttackDamageOperation` (scission du module >1000 lignes, vecteur de croissance : chaque patron
custom normal-attack / effet declarant des coups additionnels atterrit ICI).

Deux fonctions LIBRES appelees par `AttackDamageOperation.execute` :
  - `collect_additional_hit_groups` : mirror `AdditionalHitsFromEffects.GetAdditionalHitsFromEffects
    Internal @180e59150` (enumeration GLOBALE des descripteurs : effets du porteur + auras d'allies) ;
  - `execute_additional_hits` : mirror `ExecuteAdditionalHitsWithDamageProfileTypeOperation.Execute
    @180e70600` (chaque groupe = sous-operation de degat au profil PROPRE, apres les coups d'arme).

`execute_additional_hits` rappelle les primitives de tirage de `AttackDamageOperation`
(`_apply_max_out`/`_run_hits`/`_target_limits`/`_deplete_shield`/`_apply_damage_pipeline`) : import
LAZY de la classe (rompt le cycle module `damage` <-> `additional_hits` — au moment de l'appel, en
pleine bataille, `damage` est entierement charge)."""
from __future__ import annotations

from ..components import (StatsComponent, HealthComponent, PositionComponent, UnitComponent,
                          OwnerComponent)
from ..damage_model import target_trait_names
from ..state import State
from ...services.damage_prediction import get_base_damage_fix64, apply_pierce_and_modifiers
from ...services.damage_modifiers import apply_all_modifiers
from ...entities.effects import additional_hit_groups, aura_additional_hits_from_allies


def collect_additional_hit_groups(state: State, attacker_id: int, target_id: int,
                                  att_active, is_melee: bool, tgt_active) -> list:
    """#202-B : mirror `AdditionalHitsFromEffects.GetAdditionalHitsFromEffectsInternal @180e59150`
    cote ECS — enumeration GLOBALE des effets declarant des coups additionnels HETEROGENES (canal
    #179) : (a) effets du PORTEUR (`additional_hit_groups`, ex. SquigHound/CordClaw/FoulInfusion) ;
    (b) effets-AURA hostes sur d'AUTRES unites VIVANTES (`create_aura_additional_hits_for_ally`,
    ex. ExplosiveMaladies/InfernalPacts) — adjacence evaluee aux positions REELLES de l'ECS, mirror
    du refresh natif `PreAttack(5)` (l'aura est reevaluee au moment de l'attaque, @180f52730).
    Retour [] strict (aucun carrier -> no-op, AUCUNE conso RNG)."""
    import gameconfig as GC
    att = state.get_entity(attacker_id)
    ap = att.get_component(PositionComponent) if att is not None else None
    aoc = att.get_component(OwnerComponent) if att is not None else None
    auc = att.get_component(UnitComponent) if att is not None else None
    asc = att.get_component(StatsComponent) if att is not None else None
    if ap is None or aoc is None:
        return []
    gu = (GC.unit(auc.visual_id) or {}) if auc is not None else {}
    # gates CIBLE des descripteurs du porteur (#57e, ex. CyclicIonBlaster HasEffect(Markerlight)).
    ah_ctx = {"is_melee": is_melee,
              "tgt_traits": frozenset(target_trait_names(state, target_id) or ()),
              "tgt_effect_names": frozenset(
                  n for n in (getattr(e, "name", None) for e in (tgt_active or [])) if n)}
    groups = list(additional_hit_groups(att_active, ah_ctx))
    carriers = []
    for uid, e in state.entities.items():
        if uid == attacker_id:
            continue
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        oc = e.get_component(OwnerComponent)
        hc = e.get_component(HealthComponent)
        if uc is None or pc is None or oc is None or not uc.alive:
            continue
        effs = (state.effects.active_effects(uid, {"hp": hc.hp if hc is not None else None})
                if state.effects is not None else [])
        if not effs:
            continue
        sc2 = e.get_component(StatsComponent)
        ctx2 = sc2.ctx if sc2 is not None else None
        gu2 = GC.unit(uc.visual_id) or {}
        carriers.append((uid, (pc.col, pc.row), oc.team,
                         int(getattr(ctx2, "ability_variables_multiplier", 100) or 100),
                         getattr(ctx2, "passive_ability_level", None),
                         gu2.get("GrandAllianceId"), gu2.get("FactionId"), effs))
    groups += aura_additional_hits_from_allies(
        carriers, {"att_id": attacker_id, "att_pos": (ap.col, ap.row), "att_team": aoc.team,
                   "att_faction": gu.get("FactionId"),
                   "att_grand_alliance": gu.get("GrandAllianceId"),
                   "att_traits": frozenset(getattr(asc.ctx, "traits", None) or ())
                   if asc is not None else frozenset(),
                   "is_melee": is_melee})
    return groups


def execute_additional_hits(state: State, attacker_id: int, target_id: int, tgt, thc,
                            groups: list, mods, def_mods, armor: int, hit_mult: int,
                            block_sources, shc, spread_pct: int = 20,
                            extra_pierce: int = 0) -> "Optional[dict]":
    """#202-B : face COMBAT du canal #179 — mirror `ExecuteAdditionalHitsWithDamageProfileType
    Operation.Execute @180e70600` (schedule : `OperationProcessor.ExecuteAdditionalHitsWith
    DamageProfileType @180e07fb0`) : chaque groupe qualifie execute ses coups comme SOUS-OPERATION
    de degat APRES les coups d'arme. Bornes = plage PREDEFINED [min,max] (RandomAmount natif —
    PAS de spread ±20% ; forme `amount` = spread standard) REDUITE par perce(profil du GROUPE)
    + armure + mods — MEMES mods attaquant/defenseur que l'arme (mirror de la prediction #179,
    mesure 2468 s14 : le coup ExplosiveMaladies subit le x1.5 CrushingStrike). Tirage TOUJOURS
    consomme (mode-1 attaque, etage limites au profil DU GROUPE #57d). Max-out WeaverOfFate
    (#202-A) : bornes degenerees (max,max), symetrique de la degenerescence `predefined` de
    `predict_attack_raw`.

    Chaque groupe passe par `_apply_damage_pipeline` avec SON profil (mirror RegisterDamage
    per-sous-operation -> un coup Psychic d'InfernalPacts alimente `received_damage_this_turn`
    donc WeaverOfFate) et `is_attack=False` (le compteur d'attaque est celui de l'ATTAQUE,
    deja pose par la phase d'arme).

    A CONFIRMER LIVE (case-202 §7, conso RNG discriminante) : (1) PAS de crit-roll sur les coups
    bonus (le descripteur natif ne porte aucune plage crit ; `predict_attack_raw` ne crit-folde
    pas un predefined) -> 1 tirage/coup ici, 2 si le natif crit-rolle ; (2) gate `hp > 0` (cible
    morte pendant la phase d'arme -> sous-operations non emises) ; (3) `failed_block` remis a
    zero entre phase d'arme et groupes (le natif persiste la failedList PAR ATTAQUE — residu).
    None si aucun groupe qualifie (strict no-op retro-compat).

    Rappelle les primitives de tirage de `AttackDamageOperation` : import LAZY (cycle module
    damage <-> additional_hits ; `damage` est charge au moment de l'appel en bataille)."""
    if not groups or thc is None or int(thc.hp or 0) <= 0:
        return None
    import gameconfig as GC
    from .damage import AttackDamageOperation, HitDamage
    death = None
    out = {"groups": 0, "hits": 0, "total": 0, "per_hit": [], "rolls": [], "profiles": []}
    for g in groups:
        if int(thc.hp or 0) <= 0:
            break
        g_profile = g.get("profile")
        dp = GC.damage_profile(g_profile) or {}
        g_pierce = max(0, min(100, int(dp.get("PiercingRatio") or 0) + int(extra_pierce or 0)))
        # bi-canal (mesure 202b) : la face COMBAT resout le noeud RandomAmount du descripteur
        # (field[1] -> plage DIRECTE min/max) ; `amount` (field[2] Average) = canal PREDICTION.
        # Un groupe amount-seul (ex. FoulInfusion ConfigVar) prend le spread ±20% standard.
        if "min" in g and "max" in g:
            g_min, g_max = int(g.get("min") or 0), int(g.get("max") or 0)
        else:
            mm = get_base_damage_fix64(g.get("amount") or 0, spread_pct=spread_pct)
            g_min, g_max = mm.min, mm.max
        lo = apply_all_modifiers(apply_pierce_and_modifiers(
            g_min, g_pierce, armor, mods, hit_mult=hit_mult, attacker_additive_pre=True), def_mods)
        hi = apply_all_modifiers(apply_pierce_and_modifiers(
            g_max, g_pierce, armor, mods, hit_mult=hit_mult, attacker_additive_pre=True), def_mods)
        hd = HitDamage(lo, hi)
        hd, _ = AttackDamageOperation._apply_max_out(state, attacker_id, hd, hd)
        shield_total = shc.get_total_shield() if shc is not None else 0
        r = AttackDamageOperation._run_hits(
            state.rng, hd, hd, 0, False, max(0, int(g.get("count") or 0)), block_sources,
            shield=shield_total,
            limits=AttackDamageOperation._target_limits(tgt, thc, g_profile, is_special=1),
            limits_hp=int(thc.hp or 0))
        AttackDamageOperation._deplete_shield(shc, r)
        d = AttackDamageOperation._apply_damage_pipeline(
            state, target_id, attacker_id, tgt, thc, r["total"], g_profile,
            r["shield_dmg"], r["armor_dmg"], is_attack=False)
        death = death or d
        out["groups"] += 1
        out["hits"] += max(0, int(g.get("count") or 0))
        out["total"] += r["total"]
        out["per_hit"] += r["per_hit"]
        out["rolls"] += r["rolls"]
        out["profiles"].append(g_profile)
    out["death"] = death
    return out if out["groups"] else None
