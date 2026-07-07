"""Prédiction de dégât — orchestration MINCE du playbook (`IdunBattle.AI.Playbook`, RE gqfc5mff6c).

Stratification native (RE) : le PLAYBOOK est mince (énumère cibles, wrap en `ProbableDamageEvent`) ; toute
la mécanique de dégât vit dans l'ABILITY (`<Ability>.PredictAttack`, slot +0x21 / per-target +0x27) et les
SERVICES (`BattleQuery` sélection d'arme, `DamagePrediction` perçage/get_attack_prediction, `DamageCalculations`
défenseur/élévation/bouclier). Ce module porte la couche playbook + assemble la chaîne sur le modèle objet
(`Scene` + `UnitContext` + `AActiveAbility` + `ProbableDamageEvent`). Remplace le monolithe `predict_validate`
(PV) : MÊME calcul (validé), forme objet.

  - `make_normal_attack_predictions` = `ALoki_NormalAttackPlaybook.MakeDamagePredictions @181372730`
    (mono-cible : `ability.PredictAttack @1811afa50` -> 1 `ProbableDamageEvent`).
  - `generate_multi_hit_attack_prediction` = per-cible de `GenerateMultiHitAttackPredictions @181409da0`.
  - `make_damage_predictions` = `<Ability>Playbook.MakeDamagePredictions` (liste : cible + AoE + self).
"""
from __future__ import annotations

import gameconfig as GC
from engine import dsl, weights as _weights
from engine.entities.abilities.active_ability import (
    active_ability_for, makes_damage_predictions, _PROFILE_BY_INDEX)
from engine.entities.abilities.ability_configuration import AbilityConfiguration
from engine.entities.effects import (
    aura_attack_bonus_from_allies, aura_hits_malus_for_defense,
    aura_attack_damage_malus_from_enemies,
    calculate_attacker_modifiers_for_prediction, build_defender_modifiers_from_effects,
    hits_bonus_from_effects, hits_malus_from_defender_effects)
from engine.entities.traits import attacker_bonus_hits
from engine.entities.stats import StatType, StatPart
from engine.services.damage_prediction import get_attack_prediction, get_multi_hit_attack_prediction
from engine.services.min_max_damage import MinMaxDamage
from engine.services.damage_modifiers import (
    add_modifier, calculate_elevation_bonus_modifier, calculate_ranged_in_melee_reduction,
    calculate_trench_reduction, ELEVATION_BONUS_PCT, EFFECT_NO_ELEVATION)
from engine.services.battle_query import select_weapon_pierce, are_tiles_adjacent
from engine.services.attack_hits_formula import attack_hits_with_modifiers
from engine.playbook.probable_damage_event import ProbableDamageEvent

import json as _json
_DMG_CFG: dict = _json.loads(_weights.DEFAULT_BC.read_text(encoding="utf-8")).get("Damage", {}) \
    if _weights.DEFAULT_BC.exists() else {}
# Feuilles positionnelles de CalculateAttackerModifiersForPrediction @181000590 (PAS des effets) :
# ELEVATION_BONUS_PCT + EFFECT_NO_ELEVATION vivent dans le port de DamageCalculations (`damage_modifiers`),
# importes ci-dessus, consommes a l'identique par la prediction ET le combat (#58, pas de fork).
# RANGED_IN_MELEE_PCT / TRENCH_PCT (ci-dessous) : config native = pourcentage NEGATIF (ReductionPercentage
# =-50) ; le port passe la MAGNITUDE a calculate_*_reduction (kind PercentDecrease -> add_modifier flippe le
# signe -> x0.5). Cf.
# calculate_*_reduction (kind PercentDecrease -> add_modifier flippe le signe -> x0.5). Cf.
# GetMultiplierFromDamageBonus @181005210 (value<1 -> 1-|value|/100), decompile confirme x0.5.
RANGED_IN_MELEE_PCT: int = abs(int(_DMG_CFG.get("RangedInMeleeReductionPercentage", -50)))  # @181004700
TRENCH_PCT: int = abs(int(_DMG_CFG.get("TrenchReductionPercentage", -50)))                  # @181004830
_PROFILE_INDEX = {name: idx for idx, name in _PROFILE_BY_INDEX.items()}


def _has_effect_type(effects, etype) -> bool:
    """True si un effet ACTIF de la liste a cet `effectType` (int)."""
    return any(getattr(e, "effect_type", None) == etype for e in (effects or []))


def _weapon_pierce(scene, att_id, is_adjacent):
    """Arme + perçage de l'attaque normale — DÉLÈGUE au service PARTAGÉ `battle_query.select_weapon_pierce`
    (MÊME port que le combat/runner ; `is_adjacent` = adjacence HEX native, cf.
    `make_normal_attack_predictions`). Renvoie `(pierce, is_ranged, weapon_hits, profile_name)`."""
    return select_weapon_pierce(scene.ctx(att_id), is_adjacent)


def _should_apply_ranged_in_melee(scene, att_id, attack_pos) -> bool:
    """`ShouldApplyRangedInMelee @181005810` : depuis `attack_pos`, existe-t-il un ENNEMI melee-able
    ADJACENT ? (any-enemy, PAS seulement la cible — le natif boucle sur les tuiles adjacentes de
    l'attaquant). Filtres : ennemi (team != attaquant) + vivant + `CanMeleeAttackOverElevationDifference`
    (|Δelev|<2). Adjacence HEX via le service PARTAGÉ `are_tiles_adjacent` (board natif si dispo).
    Le gate trait 0xb (ranged) est vérifié par l'appelant (`is_ranged`)."""
    if attack_pos is None:
        return False
    att_team = scene.team(att_id)
    a_elev = scene.elev_by_pos.get(attack_pos) if scene.elev_by_pos else None
    for uid, epos in scene.pos_by_id.items():
        if uid == att_id or epos is None or scene.team(uid) == att_team:
            continue
        if (scene.hp(uid) or 0) <= 0:                      # IsAlive
            continue
        if are_tiles_adjacent(attack_pos, epos, scene.board) is not True:
            continue
        if a_elev is not None and scene.elev_by_pos:       # CanMeleeAttackOverElevationDifference
            e_elev = scene.elev_by_pos.get(epos)
            if e_elev is not None and abs(a_elev - e_elev) >= 2:
                continue
        return True
    return False


def _add_positional_and_defender_mods(mods, scene, att_id, tgt_id, is_melee, attack_pos, t_pos,
                                      damage_profile=None):
    """Ajoute au `mods` les feuilles NON-effet du builder natif `CalculateAttackerModifiersForPrediction`
    @181000590 (positionnelles, géométrie) + les modifiers DÉFENSEUR. Le pipeline natif
    `CalculateDamagePredictionScenario` les applique à TOUT dégât (normal ET spécial) APRÈS perçage/armure.
      • ElevationBonus (`CalculateElevationBonusModifier @181003ea0`, surplomb +50%).
      • RangedInMelee (`CalculateRangedInMeleeReduction @181004700`, ranged adjacent à un ennemi → ×0.5).
      • Trench (`CalculateTrenchReduction @181004830`) — HYPOTHÈSE : flag `isTrench` NON capturé dans la
        Scene → non applicable tant que la donnée tuile-trench n'est pas exposée (structurellement présent,
        no-op ici : `target_on_trench=False`).
      • DÉFENSEUR (`CalculateDefenderModifiersForPrediction` : effets de la CIBLE réduisant le dégât reçu)."""
    if scene.elev_by_pos and attack_pos and t_pos:
        a_elev, t_elev = scene.elev_by_pos.get(attack_pos), scene.elev_by_pos.get(t_pos)
        if a_elev is not None and t_elev is not None:
            # Gate 0x423 (CalculateElevationBonusModifier @181003ea0) : élévation SAUTÉE si l'attaquant OU
            # la cible a un effet "no elevation bonus" (effectType 1059). Non testé (1059 absent des seeds
            # courants) mais fidèle au décompilé. Comparaison a_elev>t_elev = tuile attaquant > tuile cible
            # (mesuré : (5,4)elev3 vs cible elev2 -> x1.5 EXACT ; per-tuile candidate, cf. #58).
            no_elev = (_has_effect_type(scene.effects(att_id), EFFECT_NO_ELEVATION)
                       or _has_effect_type(scene.effects(tgt_id), EFFECT_NO_ELEVATION))
            eb = calculate_elevation_bonus_modifier(a_elev, t_elev, ELEVATION_BONUS_PCT,
                                                    attacker_or_target_has_no_elev_effect=no_elev)
            if eb is not None:
                add_modifier(mods, eb)
    is_ranged = not is_melee
    if is_ranged and _should_apply_ranged_in_melee(scene, att_id, attack_pos):     # trait 0xb + adjacence
        eb = calculate_ranged_in_melee_reduction(True, RANGED_IN_MELEE_PCT)
        if eb is not None:
            add_modifier(mods, eb)
    eb = calculate_trench_reduction(False, TRENCH_PCT)      # target_on_trench=False (data non capturée)
    if eb is not None:
        add_modifier(mods, eb)
    tgt_effects = scene.effects(tgt_id)
    def_mods = build_defender_modifiers_from_effects(tgt_effects, is_melee, damage_profile)
    for mult, cap in def_mods.pct_list:
        mods.pct_list.append((mult, cap))


def _target_damage_limits(scene, tgt_id):
    """Champs STATIQUES cible pour `apply_trait_damage_limits_to_damage` (#56, `ApplyTraitDamageLimits
    ToDamage @18102c650`). SEUL **Resilient** est dérivable offline (trait gameconfig + hp/hpmax → cape
    le dégât à `HP-1`, la cible ne peut pas être one-shot). Les autres sous-limites restent des **NO-OP
    documentés** (defaults conservateurs) faute d'input offline : member-cap (`numberOfMembers` = StatType
    20, non mappé offline), Impervious (charge runtime non captée par combatSnapshot), boss-cap
    (`HasTriggeredAbility(0x5d4)` non vérifié offline). Le service porte les 5 ; ici on ne nourrit que ce
    qui est fidèlement dérivable."""
    utraits = set((GC.unit(scene.vis_by_id.get(tgt_id)) or {}).get("traits") or [])
    hpmax = scene.hpmax(tgt_id) or 0
    return {
        "target_has_resilient": "Resilient" in utraits,
        "target_has_impervious": "Impervious" in utraits,
        "impervious_stat_current": None,             # charge Impervious non captée offline -> no-op (TODO)
        "member_count": 1,                           # numberOfMembers (StatType 20) non mappé offline -> no-op (TODO)
        "member_total_hp": hpmax,
        "profile_has_hits_multiple_members": False,  # moot tant que member_count=1 (Blast skip member-cap)
        "max_health": hpmax,
        "target_has_boss_cap": False,                # HasTriggeredAbility(0x5d4) non vérifié offline -> no-op (TODO)
        "boss_cap_const": 0,
    }


def make_normal_attack_predictions(scene, att_id, tgt_id, attack_pos, *, meta=False):
    """`ALoki_NormalAttackPlaybook.MakeDamagePredictions @181372730` -> `ability.PredictAttack @1811afa50` :
    base=Attack × hits + perçage + armure + MODIFIER (effets attaquant + ElevationBonus + défenseur).
    Renvoie 1 `ProbableDamageEvent` (l'attaque normale n'est pas AoE) ou None. `meta=True` -> `(event,
    meta_dict)` (base/pierce/armure/hits/mods/effets — diagnostic pour le harnais de validation)."""
    ctx = scene.ctx(att_id)
    if ctx is None:
        return None
    att_effects = scene.effects(att_id)
    t_pos = scene.pos(tgt_id)
    # Sélection d'arme mêlée<->ranged : service PARTAGÉ `BattleQuery.are_tiles_adjacent` (MÊME que le
    # runner combat). ADJACENCE HEX, PAS Chebyshev — une unité à armes mixtes (u92 : mêlée 4x + ranged
    # 3x Blast) bascule mêlée UNIQUEMENT sur une tuile hex-adjacente ; les tuiles cheby=1 mais hex=2
    # (ex. (5,5)->(6,6)) restent ranged. `scene.board` (si fourni) = voisins natifs, sinon evenq.
    is_adjacent = are_tiles_adjacent(attack_pos, t_pos, scene.board)
    pierce, _ranged, whits, prof_name = _weapon_pierce(scene, att_id, is_adjacent)
    is_melee = not _ranged
    _hm = (attack_pos != scene.pos(att_id)) if attack_pos else None
    # PRÉDICTION (slot 0xd) — branche distincte du combat (runner). Le debuff stat-modifications
    # (CalculateModifiersFromStatModifications @181004380, prédiction-only) reste GATÉ off : ce
    # N'EST PAS un modifier post-perçage mais un effet AU NIVEAU DE LA BASE (cf. base=Initial ci-dessous).
    mods = calculate_attacker_modifiers_for_prediction(att_effects, is_ranged=_ranged, has_moved=_hm)
    # #49 : base de l'attaque NORMALE en PRÉDICTION = `GetStat(Attack, Current)` RÉ-ÉVALUÉ PAR CANDIDAT
    # (GetAttackHitPrediction @1811af4e0 lit part0=Current ; Current=Initial+Σmods actifs). On part de
    # INITIAL (bare, exclut TOUTE modification captée dans le snapshot → pas de double-compte) puis on
    # ré-ajoute per-candidat les AURAS stat-mod d'alliés adjacents (RitesOfBattle @181225340 : +extraDmg/_2
    # aux alliés ring-1, gate Imperial) — leur appartenance au TargetSelector est ré-évaluée selon la tuile
    # d'attaque. Prouvé RE+oracle : u92 adjacent à Calgar → 3011+1298=4309 ; éloigné → 3011 (prediction.md
    # points 16/18). ⚠ Le résidu `+400` (autre aura non identifiée) n'est PAS couvert ici.
    _ap = attack_pos or scene.pos(att_id)
    att_grand = (GC.unit(scene.vis_by_id.get(att_id)) or {}).get("GrandAllianceId")
    aura_ctx = {"att_id": att_id, "att_pos": _ap, "att_team": scene.team(att_id),
                "att_grand_alliance": att_grand, "board": scene.board}
    carriers = [(uid, scene.pos(uid), scene.team(uid), scene.mult(uid), scene.ablvl_by_id.get(uid),
                 scene.effects(uid)) for uid in scene.pos_by_id
                if uid != att_id and (scene.hp(uid) or 0) > 0]
    attack_base = ctx.get_stat(StatType.ATTACK, StatPart.INITIAL) \
        + aura_attack_bonus_from_allies(carriers, aura_ctx)
    _add_positional_and_defender_mods(mods, scene, att_id, tgt_id, is_melee, attack_pos, t_pos,
                                      damage_profile=prof_name)
    # AURA ENNEMIE %-degat projetee sur l'ATTAQUANT : ShadowInTheWarp_LessDmg_Effect (-25% Psychic aux
    # ennemis a portee du porteur) — reutilise `carriers` (toutes les autres unites vivantes), gate Psychic
    # + team ennemie + portee dans le create_aura_. Ajoute aux modifiers %-list de l'attaquant.
    for _eb in aura_attack_damage_malus_from_enemies(
            carriers, {"att_id": att_id, "att_pos": _ap, "att_team": scene.team(att_id),
                       "damage_profile": prof_name}):
        add_modifier(mods, _eb)
    # Nb de coups : cette prediction EST la facade `DamagePrediction.GetAttackHits @18102f240` — elle
    # rassemble les entrees depuis la Scene puis appelle la FORMULE PARTAGEE `attack_hits_with_modifiers`
    # (`AttackHitsWithModifiersFormula.Calculate @180f0bf50`, MEME formule que la facade combat runner) :
    # base weapon+ExtraHits+effets, +GetStuckIn/traits, +malus defenseur (LightCover/Parry) + auras (BigTarget).
    board = {"att_id": att_id, "tgt_id": tgt_id, "attack_pos": attack_pos, "t_pos": t_pos,
             "tgt_team": scene.team(tgt_id), "is_melee": is_melee,
             "pos_by_id": scene.pos_by_id, "team_by_id": scene.team_by_id}   # pas de faction_of/visual_id (mort)
    tgt_effects = scene.effects(tgt_id)
    aura_sources = [(uid, scene.pos(uid), scene.team(uid), scene.effects(uid))
                    for uid in scene.pos_by_id if uid != tgt_id]
    hits = attack_hits_with_modifiers(weapon_hits=whits, extra_hits=ctx.stat(StatType.EXTRA_HITS),
                                      extra_hits_melee=ctx.extra_hits_melee,
                                      attacker_effects=att_effects, trait_objects=ctx.trait_objects(),
                                      target_effects=tgt_effects, aura_sources=aura_sources, board=board,
                                      is_melee=is_melee, damage_profile=prof_name,
                                      include_bonus_hit_behaviours=True)  # prediction folde GetStuckIn (deterministe)
    res = get_attack_prediction(
        target_current_health=scene.hp(tgt_id) or 0, initial_damage=attack_base, hits=hits,
        profile_type=0, pierce_pct=pierce, armor=scene.armor(tgt_id), mods=mods,
        target_shield=scene.shield(tgt_id), target_limits=_target_damage_limits(scene, tgt_id))
    ev = ProbableDamageEvent(target=tgt_id, prediction=res)
    if meta:
        return ev, {"base": attack_base, "pierce": pierce, "armor": scene.armor(tgt_id), "hits": hits,
                    "mods": [round(m, 3) for m, _c in mods.pct_list] or None,
                    "effects": [e.name for e in att_effects] or None}
    return ev


def generate_multi_hit_attack_prediction(scene, uid, tgt, ability_id, ability_name, attack_pos=None):
    """Per-cible de `ComparablePlaybook.GenerateMultiHitAttackPredictions @181409da0` : `DamagePredictionResult`
    d'UNE cible via le `(damage, hits, profile, pierce)` PROPRE de l'ability (`<Ability>.PredictAttack`,
    slot +0x27). None si non-attaque."""
    ctx = scene.ctx(uid)
    if ctx is None:
        return None
    cfg = AbilityConfiguration.from_gameconfig(ability_name, GC.ability(ability_name))
    if cfg is None or not (cfg.has_variable("minDmg") or cfg.has_variable("maxDmg")):
        return None
    ab = active_ability_for(ability_name, ability_id, ctx, cfg)
    base = ab.get_damage()
    if base <= 0:
        return None
    a = GC.ability(ability_name) or {}
    affected = set(a.get("variablesAffectedByRarityBonus") or [])   # rarity mult (AbilityVariablesMultiplier)
    mult = scene.mult(uid)
    if mult and mult != 100 and ({"minDmg", "maxDmg"} & affected):
        base = (base * mult) // 100
    is_melee = (a.get("attackRangeType") or "").lower() == "melee"
    hits = max(1, ab.get_special_hits(is_melee))
    profile_name = ab.get_damage_profile()
    profile_idx = _PROFILE_INDEX.get(profile_name, 0)
    dp = GC.damage_profile(profile_name) or {}
    dir_pierce = ctx.extra_pierce_melee if is_melee else ctx.extra_pierce_ranged
    pierce = max(0, min(100, int(dp.get("PiercingRatio") or 0) + ctx.extra_pierce + dir_pierce))
    mods = calculate_attacker_modifiers_for_prediction(scene.effects(uid), is_normal_attack=False)
    t_pos = scene.pos(tgt)
    _add_positional_and_defender_mods(mods, scene, uid, tgt, is_melee, attack_pos, t_pos,
                                      damage_profile=profile_name)
    tgt_shield = scene.shield(tgt)
    d_multi = ab.get_multi_hit_damage()      # GetDamage int par-ability (slot virtuel)
    if d_multi and mult and mult != 100 and ("minDmg" in affected):
        d_multi = (d_multi * mult) // 100
    if d_multi:
        return get_multi_hit_attack_prediction(
            target_current_health=scene.hp(tgt) or 0, damage=d_multi, hits=hits,
            profile_type=profile_idx, pierce_pct=pierce, armor=scene.armor(tgt),
            mods=mods, target_shield=tgt_shield, target_limits=_target_damage_limits(scene, tgt))
    shield_raw = None
    if tgt_shield > 0:
        d_shield = ab.config.get_variable_for_level("minDmg", ab.caster.active_ability_level, 0) \
            if ab.config else 0
        if d_shield and mult and mult != 100 and ("minDmg" in affected):
            d_shield = (d_shield * mult) // 100
        if d_shield > 0:
            shield_raw = MinMaxDamage(min=round(d_shield * hits * 0.8), max=round(d_shield * hits * 1.2))
    return get_attack_prediction(
        target_current_health=scene.hp(tgt) or 0, initial_damage=base, hits=hits,
        profile_type=profile_idx, pierce_pct=pierce, armor=scene.armor(tgt),
        mods=mods, target_shield=tgt_shield, shield_raw=shield_raw,
        target_limits=_target_damage_limits(scene, tgt))


def make_damage_predictions(scene, caster_id, main_tgt_id, ability_id, ability_name, attack_pos=None):
    """`<Ability>Playbook.MakeDamagePredictions` : LISTE de `ProbableDamageEvent` = cible PRINCIPALE + AoE
    (`GetSurroundingUnits`/`GetOtherTargets`) + event SELF négatif (coût PV). `[]` si non-attaque."""
    if not makes_damage_predictions(ability_name):
        return []
    dp = generate_multi_hit_attack_prediction(scene, caster_id, main_tgt_id, ability_id, ability_name,
                                              attack_pos=attack_pos)
    if dp is None:
        return []
    events = [ProbableDamageEvent(target=main_tgt_id, prediction=dp)]
    ctx0 = scene.ctx(caster_id)
    cfg = AbilityConfiguration.from_gameconfig(ability_name, GC.ability(ability_name))
    if ctx0 is None or cfg is None:
        return events
    ab = active_ability_for(ability_name, ability_id, ctx0, cfg)
    by_id = {u.get("id"): u for u in scene.units}
    dctx = dsl.DslContext(units=scene.units, caster=by_id.get(caster_id), target=by_id.get(main_tgt_id),
                          config=cfg, ability_level=ctx0.active_ability_level,
                          times_attacked=getattr(ctx0, "times_attacked", 0) or 0,
                          caster_pos=attack_pos, elev_by_pos=scene.elev_by_pos)
    aoe = [t for t in ab.get_aoe_targets(dctx)
           if t.get("id") is not None and t.get("id") != main_tgt_id]
    # Plafond secondaire (`GetMaxSecondaryTargets`) -> poids batch `min(1, max/n)` = probability1.
    maxsec = ab.get_max_secondary_targets()
    prob1 = (min(1.0, maxsec / len(aoe)) if (maxsec is not None and aoe) else 1.0)
    for t in aoe:
        tid = t.get("id")
        adp = generate_multi_hit_attack_prediction(scene, caster_id, tid, ability_id, ability_name,
                                                   attack_pos=attack_pos)
        if adp is not None:
            events.append(ProbableDamageEvent(target=tid, prediction=adp, probability1=prob1))
    # Event SELF négatif — coût en PV (`ability.GetHealthToLose`), utilité NÉGÉE (friendly).
    hp_c = scene.hp(caster_id) or 0
    max_c = scene.hpmax(caster_id) or hp_c
    hl = ab.get_health_to_lose(max_c)
    if hl:
        self_dp = _self_damage_prediction(hp_c, hl)
        events.append(ProbableDamageEvent(target=caster_id, prediction=self_dp, friendly=True))
    return events


def _self_damage_prediction(hp_c: int, hl: int):
    """`DamagePredictionResult` du coût self (santé perdue `hl`, pas de bouclier, appliedHits=0)."""
    from engine.services.damage_prediction import DamagePredictionResult
    return DamagePredictionResult(
        current_health=hp_c, shield=0,
        accurate_health_damage=MinMaxDamage(min=min(hl, hp_c), max=min(hl, hp_c)),
        accurate_shield_damage=MinMaxDamage(min=0, max=0), applied_hits=0)
