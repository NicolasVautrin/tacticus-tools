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
from engine.services.damage_prediction import get_attack_prediction
from engine.services.min_max_damage import MinMaxDamage
from engine.services.damage_modifiers import (
    ELEVATION_BONUS_PCT, EFFECT_NO_ELEVATION, add_modifier,
    calculate_elevation_bonus_modifier, calculate_ranged_in_melee_reduction,
    calculate_trench_reduction)
from engine.services.battle_query import select_weapon_pierce, are_tiles_adjacent
from engine.services.attack_hits_formula import attack_hits_with_modifiers
from engine.playbook.probable_damage_event import ProbableDamageEvent

import json as _json
_DMG_CFG: dict = _json.loads(_weights.DEFAULT_BC.read_text(encoding="utf-8")).get("Damage", {}) \
    if _weights.DEFAULT_BC.exists() else {}
# Feuilles positionnelles de CalculateAttackerModifiersForPrediction @181000590 (PAS des effets) :
# ELEVATION : le builder PREDICTION @181000590 l'INCLUT, INLINEE (read-L1161-1192 : gate !HasEffect(0x423)
# attaquant ET cible + GetMainTile(cible) + `target.elev < attackTile.elev` -> +config.ElevationBonus) —
# AUCUN appel a la feuille @181003ea0 (inlining), d'ou le faux verdict xref #67 « pas d'elevation en
# prediction » (REFUTE #98 : aiPredict u80 (6,6) elev2>1 = x2.25 = CrushingStrike(1.5) x Elevation(1.5) ;
# tuile candidate (5,7) elev egale = x1.0 EXACT -> evaluee a la TUILE CANDIDATE). Cf.
# `_add_positional_and_defender_mods`. RangedInMelee/defenseur aussi dans le preview (10/11).
# RANGED_IN_MELEE_PCT / TRENCH_PCT (ci-dessous) : config native = pourcentage NEGATIF (ReductionPercentage
# =-50) ; le port passe la MAGNITUDE a calculate_*_reduction (kind PercentDecrease -> add_modifier flippe le
# signe -> x0.5). Cf.
# calculate_*_reduction (kind PercentDecrease -> add_modifier flippe le signe -> x0.5). Cf.
# GetMultiplierFromDamageBonus @181005210 (value<1 -> 1-|value|/100), decompile confirme x0.5.
RANGED_IN_MELEE_PCT: int = abs(int(_DMG_CFG.get("RangedInMeleeReductionPercentage", -50)))  # @181004700
TRENCH_PCT: int = abs(int(_DMG_CFG.get("TrenchReductionPercentage", -50)))                  # @181004830
# Profils de degat qui IGNORENT la reduction Trench (`IgnoreTrenchReduction @181559b70` =
# `List.Contains(staticList, profile)`). La liste native est un config STATIQUE hors section Damage de la
# BC (aucune cle ici) -> defaut VIDE (aucun profil exempte) tant qu'elle n'est pas RE'd/exposee. A raffiner
# si un cas live montre une NON-reduction sur-trench pour un profil donne (#125).
_TRENCH_IGNORED_PROFILES: "frozenset[str]" = frozenset()
_PROFILE_INDEX = {name: idx for idx, name in _PROFILE_BY_INDEX.items()}


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
                                      damage_profile=None, is_normal_attack: bool = True):
    """Ajoute au `mods` les feuilles NON-effet du builder natif `CalculateAttackerModifiersForPrediction`
    @181000590 (positionnelles, géométrie) + les modifiers DÉFENSEUR. Le pipeline natif
    `CalculateDamagePredictionScenario` les applique à TOUT dégât (normal ET spécial) APRÈS perçage/armure.
      • ElevationBonus (`CalculateElevationBonusModifier @181003ea0`, surplomb +50%).
      • RangedInMelee (`CalculateRangedInMeleeReduction @181004700`, ranged adjacent à un ennemi → ×0.5).
      • Trench (`CalculateTrenchReduction @181004830`) — HYPOTHÈSE : flag `isTrench` NON capturé dans la
        Scene → non applicable tant que la donnée tuile-trench n'est pas exposée (structurellement présent,
        no-op ici : `target_on_trench=False`).
      • DÉFENSEUR (`CalculateDefenderModifiersForPrediction` : effets de la CIBLE réduisant le dégât reçu)."""
    # ELEVATION (#98 — RENVERSE le verdict #67 « pas d'elevation en prediction ») : le builder PREDICTION
    # @181000590 (qui FIRE bien 33x par tour de decision, mesure modifier-observe) l'applique INLINEE
    # (read-L1161-1192, aucun appel a @181003ea0 -> le xref-check #67 ne pouvait pas la voir) :
    #   if attackTile && !HasEffect(att,0x423) && !HasEffect(tgt,0x423) && GetMainTile(tgt):
    #       if tgt.elev < attackTile.elev : bonus = Nullable(config.ElevationBonus)   # -> Add (%-list)
    # Evaluee a la TUILE CANDIDATE `attack_pos` (mirror local_588) vs la tuile REELLE de la cible.
    # GROUND TRUTH #98 (u80 darkaTerminator seed777 r1) : aiPredict (6,6) elev2>1 not-moved = x2.25
    # = CrushingStrike(1.5) x Elevation(1.5) EXACT ([11940,17907] = port x2.25) ; candidates (5,7)/(5,6)/
    # (6,8) elev1=1 = x1.0 EXACT. Les contre-cas historiques #67 (u90 : dmg identique tuiles elev2/elev3 ;
    # u88 : elev2>1 sans bonus) sont a re-verifier avec la methode artefact-aware (#96 : le cache aiPredict
    # collisionne par (unit,cible,tuile) et peut servir une valeur d'une autre ability/etat) — anomalies
    # tracees dans docs/rl/playbook/prediction.md, PAS une raison de forker le port du builder lu.
    if scene.elev_by_pos and attack_pos and t_pos:
        a_elev = scene.elev_by_pos.get(tuple(attack_pos))
        t_elev = scene.elev_by_pos.get(tuple(t_pos))
        if a_elev is not None and t_elev is not None:
            att_effects_ = scene.effects(att_id)
            tgt_effects_ = scene.effects(tgt_id)
            no_elev = any(e.effect_type == EFFECT_NO_ELEVATION for e in att_effects_) \
                or any(e.effect_type == EFFECT_NO_ELEVATION for e in tgt_effects_)
            eb = calculate_elevation_bonus_modifier(a_elev, t_elev, ELEVATION_BONUS_PCT, no_elev)
            if eb is not None:
                add_modifier(mods, eb)
    is_ranged = not is_melee
    if is_ranged and _should_apply_ranged_in_melee(scene, att_id, attack_pos):     # trait 0xb + adjacence
        eb = calculate_ranged_in_melee_reduction(True, RANGED_IN_MELEE_PCT)
        if eb is not None:
            add_modifier(mods, eb)
    tgt_effects = scene.effects(tgt_id)
    # Trench (CalculateTrenchReduction @181004830) : -TrenchReductionPercentage% (=-50) SI la cible porte
    # l'effet Trench (natif HasEffect(target,0x423) ; effet de TUILE pose par TrenchAbility @1811c8e30,
    # IsActive => cible sur/adjacente a une tuile Trench — confirme live SyncPvp_Arctic_06 u84 : 'Trench'
    # present sur-trench, DROP hors-trench) ET profil non-exempte (IgnoreTrenchReduction @181559b70, defaut
    # vide #125). calculate_trench_reduction owner_is_caster=True = maths identiques a un -50% defenseur.
    target_on_trench = (any(getattr(e, "name", None) == "Trench" for e in tgt_effects)
                        and (not damage_profile or damage_profile not in _TRENCH_IGNORED_PROFILES))
    eb = calculate_trench_reduction(target_on_trench, TRENCH_PCT)
    if eb is not None:
        add_modifier(mods, eb)
    # attacker_ctx : identité + niveau/mult du Neurothrope SOURCE (gate + magnitude Neuroparasite). L'attaquant
    # ETANT le source (AreEqual), extraDmg s'indexe sur SON ablvl x SON multiplier.
    # `is_normal_attack` propagé au gate `IsNormalAttack` des malus défenseur (ex. MartialKatah -20% #105 :
    # réduit UNIQUEMENT les attaques normales, no-op sur les spéciales config-based).
    att_ctx = {"id": att_id, "ability_level": scene.ablvl_by_id.get(att_id), "multiplier": scene.mult(att_id),
               "is_normal_attack": is_normal_attack}
    def_mods = build_defender_modifiers_from_effects(tgt_effects, is_melee, damage_profile, attacker_ctx=att_ctx)
    for mult, cap in def_mods.pct_list:
        mods.pct_list.append((mult, cap))
    # ADDITIF défenseur (ForAddition, ex. Neuroparasite +extraDmg x niveau) — le %-list SEUL était fusionné,
    # l'additif défenseur était DROPPE. PLACEMENT = MÊME slot @+0x10 que l'additif ATTAQUANT #75 : ajouté à la
    # base PRÉ-perçage, puis traverse perçage et est scalé ×%-list UNE fois (le natif ajoute l'additif @+0x10
    # à la base int AVANT `CalculateBaseDamageWithAllModifiers @18102d3f0`, qui NE re-consomme PAS @+0x10 —
    # cf. `attacker_additive_pre=True` dans `predict_attack_raw`/`calculate_damage_prediction_scenario`). Donc
    # on AJOUTE l'additif BRUT (SANS pré-scale) : le chemin attacker_additive_pre applique déjà le %-list ×M.
    # #121 (CONFIRMÉ LIVE 2026-07-12, Neurothrope u82 -> custoTrajann level 1, A=1696 M=1.064) : ORACLE
    # contribution = 1804 = A*M (natif single-scale) ; le pré-scale ×M produisait A*M^2 = 1920 (port sur-préd
    # +116) -> RETIRÉ. Reproduit les 2 séparateurs #88 (RangedSpecialist ON M=1.33 -> A*M=2256 ; OFF M=1 ->
    # 1696) : l'ancien pré-scale ×M compensait le PLACEMENT POST-%-list de `apply_all_modifiers` (additif après
    # %-list, non scalé) ; #70/#111 a basculé la prédiction sur attacker_additive_pre (additif pré-perçage,
    # %-list re-appliqué) -> le pré-scale devint un DOUBLE-comptage. ≠ flat_reductions (Nightshroud ci-dessous,
    # #120) qui n'est PAS pré-scalé non plus. Combat : def additive=0 (parasite non matérialisé) -> inerte.
    if def_mods.additive:
        mods.additive += def_mods.additive
    # Réductions DYNAMIQUES CAPÉES défenseur (GuardianOrganism -min(pct%×dmg, cap)) — appliquées post-mods
    # dans apply_all_modifiers (CurrentDamage). Le %-list SEUL était fusionné (comme l'additif, cf. #86a).
    if def_mods.capped_reductions:
        mods.capped_reductions.extend(def_mods.capped_reductions)
    # Réductions PLATES CONSTANTES défenseur (Nightshroud_DmgReduction ForSubtraction = ConfigVar(0x12)=
    # dmgReduction×mult, ex. 499 @{lvl50,mult180}) — additif DÉFENSEUR sur le slot @+0x10 : soustrait de la
    # BASE **PRÉ-perçage** (comme l'additif attaquant #75), donc DILUÉ par perçage/armure PUIS scalé ×%-list
    # UNE fois (mirror CBDWAM @18102d3f0 : le natif ajoute l'additif @+0x10 à la base int AVANT Calculate
    # BaseDamageWithAllModifiers, CBDWAM ne le re-consomme pas). CONFIRMÉ LIVE : le config 499 dilué par le
    # facteur perçage/armure (~0.31 vs custoTrajann) -> ~155/coup de dégât santé = oracle [1620,2744] (le
    # residu apparent "155" N'EST PAS la valeur config mais 499 traversant l'armure). PAS de pré-scale ×M
    # (≠ l'additif Neuroparasite ci-dessus qui compense le placement post-%-list du COMBAT) : le chemin
    # attacker_additive_pre scale déjà ×%-list une fois.
    if def_mods.flat_reductions:
        mods.additive -= sum(def_mods.flat_reductions)


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
    # BeastSlayer (target-conditionnel) : traits de la CIBLE (mirror HasTrait) -> gate BigTarget/Vehicle.
    _tgt_traits = frozenset((GC.unit(scene.vis_by_id.get(tgt_id)) or {}).get("traits") or [])
    mods = calculate_attacker_modifiers_for_prediction(att_effects, is_ranged=_ranged, has_moved=_hm,
                                                       target_traits=_tgt_traits)
    # #49/#153 : base de l'attaque NORMALE en PREDICTION DISPLAY = Initial + auras stat-mod re-evaluees
    # a la TUILE CANDIDATE. On part de INITIAL (bare, exclut TOUTE modification captee dans le snapshot
    # -> pas de double-compte) puis on re-ajoute les AURAS stat-mod d'allies (RitesOfBattle @181225340,
    # PathOfCommand @181110f10) evaluees a `attack_pos` (tuile candidate ; None -> position reelle).
    # NB : le residu `+400` (autre aura non identifiee) n'est PAS couvert ici.
    _ap = attack_pos or scene.pos(att_id)
    # #153 (tranche le flip-flop #45/#58/#67) : la chaine display threade la position candidate de bout
    # en bout — `DamagePredictionQuery.GetAllPredictions @181090f50` construit `UnitPosition(tuile de
    # selection)` et la passe au service ; `DamagePrediction.PredictNormalAttack @181037cd0` en tire
    # `get_MainTile` et la pose comme CasterTile dans `AbilityEntities.ctor`. Les auras d'attaque-stat
    # sont donc re-evaluees PAR TUILE CANDIDATE (PAS la valeur bakee a la position reelle). MESURE
    # discriminante seed-31337 (1 decisionView, attaquant reel FIXE adjacent au porteur, seule la tuile
    # varie) : u92 out-ring 12/12 = base Initial (aura PERDUE malgre le stat-mod +1298 present live) ;
    # u96 (reel LOIN du porteur, aucun stat-mod) sur tuile in-ring = base Initial+aura (aura GAGNEE).
    # L'ancien verdict #67 (« aura bakee a la position reelle, GetStat sans position ») etait un artefact :
    # son test etait circulaire (port-vs-port) et son unique GetStat de GetAttackHitPrediction @1811af4e0
    # lit en realite `GetStat(AbilityEntities.Target@+0x10, Health=5, Current)` (HP cible), pas un Attack.
    _att_gu = GC.unit(scene.vis_by_id.get(att_id)) or {}
    att_grand = _att_gu.get("GrandAllianceId")           # gate RitesOfBattle (Imperial)
    att_faction = _att_gu.get("FactionId")               # gate PathOfCommand (IsSameFaction = FactionId)
    aura_ctx = {"att_id": att_id, "att_pos": _ap, "att_team": scene.team(att_id),
                "att_grand_alliance": att_grand, "att_faction": att_faction, "board": scene.board}
    carriers = [(uid, scene.pos(uid), scene.team(uid), scene.mult(uid), scene.ablvl_by_id.get(uid),
                 (GC.unit(scene.vis_by_id.get(uid)) or {}).get("GrandAllianceId"),   # owner grande-alliance
                 (GC.unit(scene.vis_by_id.get(uid)) or {}).get("FactionId"),         # owner faction
                 scene.effects(uid)) for uid in scene.pos_by_id                      # (type-level, miroir-safe)
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
             "pos_by_id": scene.pos_by_id, "team_by_id": scene.team_by_id,
             # faction par unité — gate GetBonusHitChance de GetStuckIn (orks_adj>=2, @180f83460, #98)
             "faction_by_id": {uid: scene.faction(uid) for uid in scene.pos_by_id}}
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


def generate_multi_hit_attack_prediction(scene, uid, tgt, ability_id, ability_name, attack_pos=None,
                                         base_bonus: int = 0, base_override=None,
                                         hits_override=None, profile_override=None):
    """Per-cible de `ComparablePlaybook.GenerateMultiHitAttackPredictions @181409da0` : `DamagePredictionResult`
    d'UNE cible via le `(damage, hits, profile, pierce)` PROPRE de l'ability (`<Ability>.PredictAttack`,
    slot +0x27). None si non-attaque.

    `base_override`/`hits_override`/`profile_override` (défaut None = comportement inchangé) : substituent
    la base/hits/profil lus de l'ability. Requis par l'utilité de DÉCISION NonComparable de HammerOfWrath
    (#114), dont `CalculateUtilityFromDamageEvent` @1814aa3d0/@1814aa6d0 appelle `PredictAttack(0x27)` avec
    `damage=GetMinDamage`(var12) + `hits=GetHits`(const47) [primary] / `GetMinDamage2`(var54)+
    `GetHitsToBonusTarget`(const50)+profil2 [secondary] au lieu de avg(minDmg,maxDmg)/hits config. Le RESTE
    du pipeline (spread ±20%, pierce, armure, mods attaquant/positionnels, bouclier per-coup) est identique."""
    ctx = scene.ctx(uid)
    if ctx is None:
        return None
    cfg = AbilityConfiguration.from_gameconfig(ability_name, GC.ability(ability_name))
    if cfg is None or not (cfg.has_variable("minDmg") or cfg.has_variable("maxDmg")):
        return None
    # AbilityState PER-ABILITY (#100) : le natif indexe les variables config par le couple
    # {Level, VariableMultiplierPercentage} PROPRE de l'ability (entrée ActiveAbilityComponent
    # ._abilityState @0x4c, forwardé au playbook en 5e arg de MakeDamagePredictions) — consommé par
    # TryGetVariableArrayForLevel @181577510 (idx = Level.ToZeroBasedIndex clampé ; × mult/100 si
    # var ∈ variablesAffectedByRarityBonus). Le canal global (ctx.active_ability_level ×
    # scene.mult) est un AUTRE couple (mesuré u80 PlasmaCannon : per-ability 65×120 → 1396 vs
    # global 50×180 → 1594, faux) → capteur combatSnapshot.abilityStates, fallback global.
    st = scene.ability_state(uid, ability_id)
    ab = active_ability_for(ability_name, ability_id, ctx, cfg, ability_state=st)
    # Base de la PRÉDICTION spéciale = `GetDamageFormula` du playbook (PlasmaCannonPlaybook
    # @181150b10) = `AActiveAbility.MinMaxDamage @180fb2dc0` (avgFlag) = **avg(minDmg, maxDmg)**
    # scalés per-entrée ×mult/100 (ab.get_damage, DÉCOMPOSÉ PAR ÉTAGE #100 : varLevelDumps
    # min 1197 + max 1595 → avg 1396 ; bouts prédiction [1117,1675] = ±20% EXACT ; ×mods 1.875
    # → per-coup [2094,3141] == aiPlaybookPredict). Le « base = maxDmg seul » (#96) est RÉFUTÉ —
    # 1396 se décomposait AUSSI en maxDmg[65]×1.2 (sous-détermination du dégât final). Le couple
    # (level, mult) = AbilityState PER-ABILITY (capteur, fallback global via ab.level/ab.multiplier).
    lvl = ab.level
    base = ab.get_damage() if base_override is None else float(base_override)   # HammerOfWrath: GetMinDamage
    if base <= 0:
        return None
    # #108 GetCorrectDamage : clause conditionnelle sur le NB de cibles AJOUTÉE À LA BASE avant spread/mods
    # (ex. MurderousSwing single-enemy +extraDmg). `base_bonus` fourni par `make_damage_predictions` (qui
    # connaît le compte AoE) ; 0 pour toutes les abilities sans clause (get_correct_damage identité).
    base += int(base_bonus or 0)
    a = GC.ability(ability_name) or {}
    is_melee = (a.get("attackRangeType") or "").lower() == "melee"
    hits = max(1, ab.get_special_hits(is_melee) if hits_override is None else int(hits_override))
    profile_name = ab.get_damage_profile() if profile_override is None else profile_override
    profile_idx = _PROFILE_INDEX.get(profile_name, 0)
    dp = GC.damage_profile(profile_name) or {}
    dir_pierce = ctx.extra_pierce_melee if is_melee else ctx.extra_pierce_ranged
    pierce = max(0, min(100, int(dp.get("PiercingRatio") or 0) + ctx.extra_pierce + dir_pierce))
    # Mods attaquant : MÊME builder @181000590 que la normale (le natif ne distingue pas par ability) —
    # threader la nature du coup + le flag has-moved de la tuile candidate (gates IsRangedAttack /
    # NOT HasMoved des effets, ex. HeavyWeapon +25% ranged not-moved s'applique aux spéciales ranged).
    _hm = (attack_pos != scene.pos(uid)) if attack_pos else None
    mods = calculate_attacker_modifiers_for_prediction(scene.effects(uid), is_ranged=not is_melee,
                                                       has_moved=_hm, is_normal_attack=False)
    t_pos = scene.pos(tgt)
    _add_positional_and_defender_mods(mods, scene, uid, tgt, is_melee, attack_pos, t_pos,
                                      damage_profile=profile_name, is_normal_attack=False)
    tgt_shield = scene.shield(tgt)
    # Base spéciale = `base` (avg(minDmg,maxDmg) scalé rareté) route par le MÊME chemin que la normale
    # (GetBaseDamageFix64 ±20% dans predict_attack_raw). L'ancien chemin `get_multi_hit_attack_prediction(
    # damage=...)` (plage empirique 0.8/2.2·d/hits) était FAUX (RE PredictAttackRaw @181032fb0 : base = 1 int
    # -> ±20% [0.8/1.2], aucun 2.2) -> SUPPRIMÉ. Les specials Attack-based (PlasmaCannon/SpiritLeech) ne
    # passent PAS ici (routés via _PREDICT_VIA_NORMAL_ATTACK). Le bouclier est déplété PAR COUP (prev).
    return get_attack_prediction(
        target_current_health=scene.hp(tgt) or 0, initial_damage=base, hits=hits,
        profile_type=profile_idx, pierce_pct=pierce, armor=scene.armor(tgt),
        mods=mods, target_shield=tgt_shield,
        target_limits=_target_damage_limits(scene, tgt))


# Abilities dont la PRÉDICTION de dégât SANTÉ est Attack-based (== l'attaque NORMALE), PAS le config
# minDmg/maxDmg. Chemin natif (RE #92) : `SpiritLeechPlaybook.MakeDamagePredictions @18115d490` calcule
# `GetAttackDamage @181209dd0` (config) MAIS le passe à `GenerateMultiHitAttackPredictions @181409da0`,
# qui invoque le slot virtuel +0x27 (`PredictAttack`) — lequel RECALCULE Attack-based (`FindAttackWeapon`
# @1811aeb80 -> `GetAttackHitPrediction @1811af4e0` = `GetStat(Attack,Current)`+arme), ignorant le config.
# PROUVÉ par le calcul : config-avg-scaled 2593 / config-max 2992 ≠ base live 2670 / dmax live 3205 (==
# native normale(69) EXACT). Le `GetAttackDamage` config alimente le HEAL (`GetHealAmountForPrediction`)
# + le COMBAT réel (`ExecuteBehaviour`), PAS ce preview. On route donc l'event de dégât principal vers
# `make_normal_attack_predictions` (mirror du slot 0x27 Attack-based : base/hits/mods/auras = la normale).
# ── Specials "Attack-based" : IL N'Y EN A AUCUN — set VIDE (reframing #99/#101a, decompile + live ;
#    detail : docs/rl/case-99-specials-attackbased-reframe.md). Prouvé ARTEFACT-FREE via le RPC
#    `resolveVtableSlot` (slot vtable PredictAttack = byte 0x328) : les 5 specials audités (SpiritLeech,
#    PlasmaCannon, Doombolt, JakhalStimms, GauntletsOfUltramar) résolvent tous PredictAttack vers le STUB
#    ABSTRAIT QUI THROW `AActiveAbility.PredictAttack @180fb2f20` — AUCUN n'hérite
#    `ALoki_NormalAttackAbility.PredictAttack @1811afa50` (Attack-based). L'HYPOTHÈSE #92 « SpiritLeech
#    hérite ALoki » (jamais lue au binaire) est RÉFUTÉE. Le vrai chemin de prédiction = chaque
#    `<Special>Playbook.MakeDamagePredictions → ComparablePlaybook.GenerateMultiHit(base = ability.GetAttackDamage(),
#    hits, profile)` ; `base` = CONFIG (`MinMaxDamage`) pour tous — `SpiritLeechAbility.GetAttackDamage @181209dd0`
#    = DSL `ConditionalAmount(¬HasEffect(Suppressed=1065), MinMaxDamage, +ConfigVar(8)=+1601)`, config.
# ⚠ Le "== normale 2670 bit-exact" historique (#90/#92) était l'ARTEFACT du preview
#    `GetAllPredictions @181090f50` (Attack-based quel que soit l'abilityType — piège #96/#101a) — CONFIRMÉ LIVE
#    (predict_sweep Neurothrope) : `aiPlaybookPredict(SpiritLeech)=[2074,3112]` (config) ≠ `disp`/artefact
#    `GetAllPredictions=[3111,4668]`. ⇒ SpiritLeech RETIRÉ ; tout special passe par le chemin CONFIG générique.
#    (PlasmaCannon avait déjà été retiré au #96.) La vérité per-ability = `aiPlaybookPredict` (#102), JAMAIS aiPredict.
_PREDICT_VIA_NORMAL_ATTACK = frozenset()


# ── Overrides d'ENTREE per-ability — mirror des `<Ability>Playbook.MakeDamagePredictions` qui SURCHARGENT
#    la base/hits generiques. Le natif dispatche par type d'ability (registre playbook / vtable) ; le port,
#    qui collapse tous les playbooks dans `make_damage_predictions`, dispatche par id via ce registre. Chaque
#    handler = HOMONYME du playbook natif + VA ; rend un dict `{base_override?, hits_override?, profile_override?}`
#    (kwargs de `generate_multi_hit_attack_prediction`) ou `{}`. La methode generique reste GENERIQUE : aucune
#    logique ability-specifique inline (ajouter une ability divergente = un handler + une entree registre).
def _martial_inspiration_inputs(scene, caster_id, ab, cfg) -> dict:
    """`MartialInspirationPlaybook.MakeDamagePredictions` (yield machine `<MakeDamagePredictions>d__2.MoveNext`
    @181162c90 ; Kariyan/custoBladeChampion, ability 1191) — SURCHARGE la base/hits generiques (#106) :
    emet UN coup (hits=1 literal `*(puVar25+0x40)=1`) de base `round(var12 * buff)`, PAS `avg(minDmg,maxDmg)`
    sur `nrOfHits=3` config (d'ou l'ancienne sur-pred x3.3).
        var12 = minDmg (id 0xc, GetVariableForLevel, rarity-scaled) ; var10 = extraDmgPct (id 0xa, +33%/tour
        CAP, NON rarity-scaled -> mult no-op) ; buff = (var10*count + 100)/100 ; count = TotalAttacksMade
        (+0x20, capteur actorStats -- PAS TotalTurnsWithAttacksMade +0x30 qu'utilise le COMBAT GetBuffPct :
        divergence prediction<->combat portee telle quelle). count=0 debut de bataille -> buff=1 -> base=minDmg.
    slot0x10 = `DamageCalculations.CalculateBaseDamageWithModifiers @1810021c0` = `round(a*b)`. Le RESTE (x1.875
    = DamageModifiers.Multiplier attaquant ; spread +/-20% ; pierce/armure) = pipeline STANDARD en aval."""
    lvl, mult = ab.level, ab.multiplier
    minv = cfg.get_variable_for_level("minDmg", lvl, 0, mult)          # var12 (rarity-scaled)
    extra = cfg.get_variable_for_level("extraDmgPct", lvl, 0, mult)    # var10 (NON rarity -> mult no-op)
    count = scene.total_attacks_made(caster_id)                        # TotalAttacksMade (+0x20)
    buff = (extra * count + 100) / 100.0
    return {"base_override": round(minv * buff), "hits_override": 1}


# {ability_id: handler(scene, caster_id, ab, cfg) -> {base/hits/profile_override}}. Mirror du dispatch
# playbook natif (par type d'ability). HammerOfWrath (1153) a son propre chemin (make_hammer_wrath_events,
# NonComparable) ; ici = les playbooks Comparable qui surchargent juste les INPUTS de GenerateMultiHit.
_MAKE_DMG_INPUT_OVERRIDES = {1191: _martial_inspiration_inputs}


def make_damage_predictions(scene, caster_id, main_tgt_id, ability_id, ability_name, attack_pos=None):
    """`<Ability>Playbook.MakeDamagePredictions` : LISTE de `ProbableDamageEvent` = cible PRINCIPALE + AoE
    (`GetSurroundingUnits`/`GetOtherTargets`) + event SELF négatif (coût PV). `[]` si non-attaque."""
    if not makes_damage_predictions(ability_name):
        return []
    # PredictAttack HÉRITÉ de la normale (slot vtable 0x27 -> ALoki_NormalAttackAbility.PredictAttack) :
    # dégât santé = prédiction d'attaque NORMALE (Attack-based), le config minDmg/maxDmg est IGNORÉ.
    # SpiritLeech (#90) seul — PlasmaCannon RETIRÉ (#96 reverté : artefact de collision du cache aiPredict,
    # cf. le commentaire du set). Le batch principal ET les batches SECONDAIRES (AoE) passent tous par slot
    # 0x27 dans `<Ability>Playbook.MakeDamagePredictions` (PlasmaCannonPlaybook @181150b10 : main +
    # UnitsDirectlyBehind, les 2 via GenerateMultiHitAttackPredictions) -> routage PAR CIBLE homogène.
    via_normal = ability_name in _PREDICT_VIA_NORMAL_ATTACK
    # ab/cfg/aoe construits ICI (AVANT le main event) car le compte AoE TOTAL (nrEnemies = 1 + secondaires)
    # est requis pour la clause `GetCorrectDamage` (MurderousSwing : +extraDmg AJOUTÉ À LA BASE si UN seul
    # ennemi touché, #108). `base_bonus` = delta de base, 0 pour toute ability sans clause (get_correct_damage
    # = identité) -> aucun autre chemin affecté. Le natif calcule `nrEnemies=Count(targets)` de même AVANT
    # d'appeler GetCorrectDamage puis GenerateMultiHitAttackPredictions par cible (MakeDamagePredictions).
    ctx0 = scene.ctx(caster_id)
    cfg = AbilityConfiguration.from_gameconfig(ability_name, GC.ability(ability_name))
    ab = active_ability_for(ability_name, ability_id, ctx0, cfg,
                            ability_state=scene.ability_state(caster_id, ability_id)) \
        if (ctx0 is not None and cfg is not None) else None
    aoe = []
    if ab is not None:
        by_id = {u.get("id"): u for u in scene.units}
        dctx = dsl.DslContext(units=scene.units, caster=by_id.get(caster_id),
                              target=by_id.get(main_tgt_id), config=cfg, ability_level=ab.level,
                              times_attacked=getattr(ctx0, "times_attacked", 0) or 0,
                              caster_pos=attack_pos, elev_by_pos=scene.elev_by_pos)
        aoe = [t for t in ab.get_aoe_targets(dctx)
               if t.get("id") is not None and t.get("id") != main_tgt_id]
    base_bonus = 0
    if ab is not None:                               # GetCorrectDamage(base, nrEnemies) - base (>= 0)
        _b = ab.get_damage()
        base_bonus = max(0, ab.get_correct_damage(_b, 1 + len(aoe)) - _b)

    # Dispatch per-ability (mirror du registre playbook natif) : un handler ability-specifique fournit ses
    # overrides d'ENTREE (base/hits/profile) ; sinon `{}` -> chemin generique config inchange. La logique
    # ability-specifique vit dans son handler HOMONYME (cf. `_MAKE_DMG_INPUT_OVERRIDES`), jamais inline ici.
    _ovr_fn = _MAKE_DMG_INPUT_OVERRIDES.get(ability_id)
    overrides = _ovr_fn(scene, caster_id, ab, cfg) if (_ovr_fn and ab is not None and cfg is not None) else {}

    def _event(tid, prob1=1.0):
        if via_normal:
            ev = make_normal_attack_predictions(scene, caster_id, tid, attack_pos)
            if ev is not None and prob1 != 1.0:
                ev.probability1 = prob1
            return ev
        dp = generate_multi_hit_attack_prediction(scene, caster_id, tid, ability_id, ability_name,
                                                  attack_pos=attack_pos, base_bonus=base_bonus, **overrides)
        return ProbableDamageEvent(target=tid, prediction=dp, probability1=prob1) if dp is not None else None

    main = _event(main_tgt_id)
    if main is None:
        return []
    events = [main]
    if ab is None:
        return events
    # Plafond secondaire (`GetMaxSecondaryTargets`) -> poids batch `min(1, max/n)` = probability1.
    maxsec = ab.get_max_secondary_targets()
    prob1 = (min(1.0, maxsec / len(aoe)) if (maxsec is not None and aoe) else 1.0)
    for t in aoe:
        aev = _event(t.get("id"), prob1)
        if aev is not None:
            events.append(aev)
    # #108 count² : les abilities AoE SELF-centrées (MurderousSwing) RÉ-ÉMETTENT la liste d'events de dégât
    # `count` fois — le playbook natif boucle sur le set `AdjacentEnemies(caster)` (EXTERNE) ET
    # `GenerateMultiHitAttackPredictions` re-boucle sur ce MÊME set (INTERNE) -> count² events, chaque cible
    # `count` fois (CONFIRMÉ LIVE : K=1->1, K=2->4, K=3->9). `get_prediction_set_repeat` = count (= 1+len(aoe),
    # taille du set) pour ces abilities, 1 sinon (linéaire INCHANGÉ pour toutes les autres). Ordre = blocs
    # [main,aoe...] répétés (mirror boucle externe). Refs partagées OK (util Σ read-only). AVANT l'event SELF.
    rep = ab.get_prediction_set_repeat(1 + len(aoe))
    if rep > 1:
        events = events * rep
    # Event SELF négatif — coût en PV (`ability.GetHealthToLose`), utilité NÉGÉE (friendly).
    hp_c = scene.hp(caster_id) or 0
    max_c = scene.hpmax(caster_id) or hp_c
    hl = ab.get_health_to_lose(max_c)
    if hl:
        self_dp = _self_damage_prediction(hp_c, hl)
        events.append(ProbableDamageEvent(target=caster_id, prediction=self_dp, friendly=True))
    return events


_HAMMER_ABILITY_NAME = "HammerOfWrath"
_HAMMER_MAX_SECONDARY = 3   # SelectUniqueUnits(GetAdjacentTargets, 3)


def make_hammer_wrath_events(scene, caster_id, target_id, attack_pos):
    """Events dégât INTERNES de HammerOfWrath (id 1153) pour scorer son utilité de DÉCISION NonComparable
    (`HammerOfWrathPlaybook.EvaluateNonComparable @181141680`), depuis `attack_pos` (tuile où le caster
    charge). Bypass du gate d'affichage #109 (Hammer n'émet AUCUN ProbableDamageEvent affiché ; le dégât est
    consommé EN INTERNE par l'utilité). Chaque event = `PredictAttack(0x27)` avec les `(damage, hits, profile)`
    PROPRES de Hammer (config gqfc5mff6c vérifiée) :
      - PRIMARY (cible) : base=`minDmg` (AbilityVariableType 12, GetMinDamage @1811e6660), hits=`nrOfHits`
        (AbilityConstantType 47, ArmoriumCherubAbility.GetHits @180fb16c0 = 2), profil=`damageProfile` (Power).
      - SECONDARY (chaque ennemi adjacent à la cible, `GetAdjacentTargets @1811e6150` =
        `Enemies(AdjacentUnits(TARGET, r=1))`, plafond `SelectUniqueUnits(3)`) : base=`minDmg_2` (var 54,
        GetMinDamage2 @1811e6610), hits=`nrOfHits_2` (const 50, BringerOfDespair.GetHitsToBonusTarget = 1),
        profil=`damageProfile_2` (Physical).
    Le reste du pipeline (spread ±20%, pierce, armure, mods attaquant/positionnels, bouclier) est identique au
    chemin normal via `generate_multi_hit_attack_prediction` (base/hits/profile override). `[]` si indisponible."""
    import hexgeo
    ctx0 = scene.ctx(caster_id)
    cfg = AbilityConfiguration.from_gameconfig(_HAMMER_ABILITY_NAME, GC.ability(_HAMMER_ABILITY_NAME))
    if ctx0 is None or cfg is None:
        return []
    ab = active_ability_for(_HAMMER_ABILITY_NAME, 1153, ctx0, cfg,
                            ability_state=scene.ability_state(caster_id, 1153))
    lvl, mult = ab.level, ab.multiplier
    minv = cfg.get_variable_for_level("minDmg", lvl, 0, mult)         # var 12 (GetMinDamage)
    minv2 = cfg.get_variable_for_level("minDmg_2", lvl, 0, mult)      # var 54 (GetMinDamage2)
    consts = cfg.constants or {}
    hits1 = max(1, int(consts.get("nrOfHits") or 1))                  # const 47 (GetHits = 2)
    hits2 = max(1, int(consts.get("nrOfHits_2") or 1))               # const 50 (GetHitsToBonusTarget = 1)
    prof1 = consts.get("damageProfile")                              # Power
    prof2 = consts.get("damageProfile_2")                            # Physical
    dp = generate_multi_hit_attack_prediction(scene, caster_id, target_id, 1153, _HAMMER_ABILITY_NAME,
                                              attack_pos=attack_pos, base_override=minv,
                                              hits_override=hits1, profile_override=prof1)
    if dp is None:
        return []
    events = [ProbableDamageEvent(target=target_id, prediction=dp)]
    # SECONDARIES : Enemies(du caster) adjacents à la CIBLE (hex dist 1), plafond 3.
    caster_team = scene.team(caster_id)
    t_pos = scene.pos(target_id)
    if t_pos is not None:
        adj = [u for u in scene.pos_by_id
               if u != target_id and scene.team(u) != caster_team
               and scene.pos(u) is not None and hexgeo.distance(scene.pos(u), t_pos) == 1]
        for sid in adj[:_HAMMER_MAX_SECONDARY]:
            sdp = generate_multi_hit_attack_prediction(scene, caster_id, sid, 1153, _HAMMER_ABILITY_NAME,
                                                      attack_pos=attack_pos, base_override=minv2,
                                                      hits_override=hits2, profile_override=prof2)
            if sdp is not None:
                events.append(ProbableDamageEvent(target=sid, prediction=sdp))
    return events


def _self_damage_prediction(hp_c: int, hl: int):
    """`DamagePredictionResult` du coût self (santé perdue `hl`, pas de bouclier, appliedHits=0)."""
    from engine.services.damage_prediction import DamagePredictionResult
    return DamagePredictionResult(
        current_health=hp_c, shield=0,
        accurate_health_damage=MinMaxDamage(min=min(hl, hp_c), max=min(hl, hp_c)),
        accurate_shield_damage=MinMaxDamage(min=0, max=0), applied_hits=0)
