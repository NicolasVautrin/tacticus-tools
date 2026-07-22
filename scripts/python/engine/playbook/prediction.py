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
import hexgeo
from engine.dsl import nodes as dsl   # facade DSLFactory (construction des noeuds)
from engine import weights as _weights
from engine.entities.abilities.active_ability import (
    active_ability_for, makes_damage_predictions, _PROFILE_BY_INDEX)
from engine.entities.abilities.ability_configuration import AbilityConfiguration
from engine.entities.effects import (
    aura_attack_bonus_from_allies, aura_hits_malus_for_defense,
    aura_attack_damage_malus_from_enemies, aura_attack_damage_bonus_from_allies,
    aura_defense_damage_malus_from_units,
    calculate_attacker_modifiers_for_prediction, build_defender_modifiers_from_effects,
    hits_bonus_from_effects, hits_malus_from_defender_effects, additional_hit_groups,
    aura_additional_hits_from_allies)
from engine.entities.effects.loki import LIGHT_COVER_TILE_ID
from engine.entities.traits import attacker_bonus_hits, target_hit_multiplier, TraitFactory
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.damage_trait import DamageTrait
from engine.entities.stats import StatType, StatPart, ARMOR_STAT_TYPES
from engine.services.damage_prediction import get_attack_prediction
from engine.services.min_max_damage import MinMaxDamage
from engine.services.damage_modifiers import (
    ELEVATION_BONUS_PCT, EFFECT_NO_ELEVATION, add_modifier,
    calculate_elevation_bonus_modifier, calculate_ranged_in_melee_reduction,
    calculate_trench_reduction,
    TRENCH_PCT, _TRENCH_IGNORED_PROFILES)
from engine.services.battle_query import select_weapon_pierce, are_tiles_adjacent
from engine.entities.effects.magnitude import ability_var
from engine.dsl.base import _round_fix64
from fractions import Fraction
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
# RANGED_IN_MELEE_PCT : config native = pourcentage NEGATIF (ReductionPercentage=-50) ; le port passe la
# MAGNITUDE a calculate_ranged_in_melee_reduction (kind PercentDecrease -> add_modifier flippe le signe ->
# x0.5 ; GetMultiplierFromDamageBonus @181005210 value<1 -> 1-|value|/100, decompile confirme). RangedInMelee
# = PREDICTION-only (trait 0xb jamais assigne, #161). TRENCH_PCT / _TRENCH_IGNORED_PROFILES deplaces en
# services.damage_modifiers (source unique partagee PREDICTION+COMBAT, #181).
RANGED_IN_MELEE_PCT: int = abs(int(_DMG_CFG.get("RangedInMeleeReductionPercentage", -50)))  # @181004700
_PROFILE_INDEX = {name: idx for idx, name in _PROFILE_BY_INDEX.items()}


def _weapon_pierce(scene, att_id, is_adjacent, dist=None):
    """Arme + perçage de l'attaque normale — DÉLÈGUE au service PARTAGÉ `battle_query.select_weapon_pierce`
    (MÊME port que le combat/runner ; `is_adjacent` = adjacence HEX native, `dist` = distance HEX pour la
    porte de portée ranged #188, cf. `make_normal_attack_predictions`). Renvoie
    `(pierce, is_ranged, weapon_hits, profile_name)`."""
    return select_weapon_pierce(scene.ctx(att_id), is_adjacent, dist)


def _should_apply_ranged_in_melee(scene, att_id, attack_pos) -> bool:
    """`ShouldApplyRangedInMelee @181005810` : le natif gate la réduction RangedInMelee sur
    `HasTrait(ATTAQUANT, UnitTrait.Ranged=0xb=11)` (param_4=0 dans le chemin prédiction
    `CalculateRangedInMeleeReduction @181004700`) — PAS sur le `is_ranged` de l'ability. Or ce trait
    n'est porté par AUCUNE unité : absent de gameconfig (0 unité) ET de la BC `Units[].Traits` — c'est un
    trait RUNTIME jamais assigné en pratique (`IsRanged @180ed8f00` = HasTrait(0xb) OR HasRangedWeapon se
    réduit donc à HasRangedWeapon, la branche trait étant morte). CONSÉQUENCE : le natif N'APPLIQUE JAMAIS
    RangedInMelee en prédiction. On mirror le gate EXACT (HasTrait), donc sans le trait Ranged -> False.
    L'ancien gate `is_ranged` de l'appelant SUR-appliquait la ×0.5 aux casters HYBRIDES tirant une ability
    ranged en mêlée (#161 : Neurothrope/SpiritLeech = ×2 faux). Si un jour une unité porte le trait Ranged,
    la suite (ennemi mêlée-able adjacent) s'active fidèlement.

    Suite (native, quand HasTrait) : depuis `attack_pos`, existe-t-il un ENNEMI mêlée-able ADJACENT ?
    (any-enemy, boucle sur les tuiles adjacentes) — ennemi (team != attaquant) + vivant +
    `CanMeleeAttackOverElevationDifference` (|Δelev|<2). Adjacence HEX via `are_tiles_adjacent`."""
    ctx = scene.ctx(att_id)
    traits = getattr(ctx, "traits", None) or ()
    if UnitTrait.Ranged.name not in traits:        # HasTrait(attaquant, 0xb) — absent partout => inerte (#161)
        return False
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
      • Trench (`CalculateTrenchReduction @181004830`, −50%) : réduction PAR DÉFAUT si la cible porte l'effet
        Trench, SUPPRIMÉE quand l'attaquant est lui-même sur une tuile Trench ET voisin hex de la cible
        (#177 : polarité tranchée + 3 mesures live ; `board.terrain_at`=#124, résidus CASE3/IndirectFire #182).
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
    # Trench (CalculateTrenchReduction @181004830) : gate COMPLET dans la fonction nommee (main gate +
    # sous-branche IsTrench(attackerTile), #177 polarite tranchee + 3 mesures live board C2_19). attackerTile
    # = attack_pos, tuile cible = t_pos (GetMainTile(cible)=sa position), board threade (#183 : plus latent).
    # Gate IndirectFire(0x3ed) PORTE ; seul residu = CASE3 ligne-toute-Trench (delegate @LAB_181004bb9 non-RE'd, #182).
    att_ctx_traits = getattr(scene.ctx(att_id), "traits", None) or ()
    eb = calculate_trench_reduction(
        attack_pos, t_pos,
        any(getattr(e, "name", None) == "Trench" for e in tgt_effects),        # HasEffect(cible, Trench 0x423)
        UnitTrait.IndirectFire.name in att_ctx_traits,                         # HasTrait(att, IndirectFire 0x3ed)
        bool(damage_profile) and damage_profile in _TRENCH_IGNORED_PROFILES,   # IgnoreTrenchReduction
        scene.board, TRENCH_PCT)
    if eb is not None:
        add_modifier(mods, eb)
    # attacker_ctx : identité + niveau/mult du Neurothrope SOURCE (gate + magnitude Neuroparasite). L'attaquant
    # ETANT le source (AreEqual), extraDmg s'indexe sur SON ablvl x SON multiplier.
    # `is_normal_attack` propagé au gate `IsNormalAttack` des malus défenseur (ex. MartialKatah -20% #105 :
    # réduit UNIQUEMENT les attaques normales, no-op sur les spéciales config-based).
    # #61bis tranche 3 : FACTION de l'attaquant threadée pour les malus défenseur gates par faction —
    # Markerlight (1122) : `OwnerIsTarget & HasFaction(actor, 9=T'au) & IsRangedAttack ->
    # ForPercentIncrease(MarkerlightDmgBonusPct=15)` (`CreateDamageModifier @180f58170`). MÊME source
    # que le combat (`damage_model.defender_modifiers` : `_faction(visual_id)` gameconfig).
    from engine.ai.action_generators import _faction as _fac
    att_ctx = {"id": att_id, "ability_level": scene.ablvl_by_id.get(att_id), "multiplier": scene.mult(att_id),
               "is_normal_attack": is_normal_attack,
               "faction": _fac(scene.vis_by_id.get(att_id))}
    # STAT-MODS DEFENSE de la CIBLE (#194/#197) : moitié DEFENSE de `CalculateDefenderModifiersForPrediction
    # @181002c30` (DefenseComponent stat 3 @181003066 → `CalculateModifiersFromStatModifications @181004380`
    # negate=1 → `1±v/100`). Ex. tuile Thorns −50 → +50 → ×1.5 (GROUND TRUTH C2_19). PORTÉE DANS la fonction
    # partagée (plus de fold séparé ici) → l'entrée sort via `def_mods.pct_list` et est recopiée ci-dessous,
    # EXACTEMENT comme avant (composition %-list commutative sans arrondi intermédiaire, #98) : #194 bit-exact
    # préservé, et le COMBAT/runner l'obtient par la MÊME fonction (fin du fork #197). `scene.defense_stat` =
    # capture combatSnapshot refreshée par-pas (None/no-mod → inerte).
    def_mods = build_defender_modifiers_from_effects(tgt_effects, is_melee, damage_profile,
                                                     attacker_ctx=att_ctx,
                                                     defense_stat=scene.defense_stat(tgt_id))
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
    # (moitié DEFENSE stat-mods #194/#197 : DÉSORMAIS foldée DANS build_defender_modifiers_from_effects
    # ci-dessus → transite via def_mods.pct_list, plus de fold séparé ici — fin du fork prédiction/combat.)
    # AURAS-DÉFENSE state-wide (#184) : effets EffectWithTarget possédés par d'AUTRES unités dont le
    # TargetSelector projette sur la CIBLE du coup — boucle « TOUS les EffectWithTarget actifs × leurs
    # cibles » de `CalculateDefenderModifiersForPrediction @181002c30` (cf. case-68), qui ne se réduit PAS
    # aux effets portés par la cible. Ex. DaughterOfTheAbyss (Atlacoya) : -dmgReductionPct% (33 @L50)
    # Psychic aux AMIS rayon 2 (racine du ~1.49x bloodMephiston seed 2024 : 1003×1.25×3×0.67 = 2016,3024
    # natif vs 3006,4515 port) ; +extraDmgPct% aux Psykers ENNEMIS rayon 2. Cibles/positions RÉELLES
    # (la cible ne bouge pas pendant la prédiction) ; porteurs vivants uniquement.
    _tgt_traits_names = frozenset((GC.unit(scene.vis_by_id.get(tgt_id)) or {}).get("traits") or [])
    _def_carriers = [(uid, scene.pos(uid), scene.team(uid), scene.effects(uid))
                     for uid in scene.pos_by_id
                     if uid != tgt_id and (scene.hp(uid) or 0) > 0]
    for _eb in aura_defense_damage_malus_from_units(
            _def_carriers, {"tgt_id": tgt_id, "t_pos": t_pos, "tgt_team": scene.team(tgt_id),
                            "tgt_traits": _tgt_traits_names, "damage_profile": damage_profile}):
        add_modifier(mods, _eb)


def _target_damage_limits(scene, tgt_id, damage_profile: str | None = None):
    """Champs STATIQUES cible pour `apply_trait_damage_limits_to_damage` (#56, `ApplyTraitDamageLimits
    ToDamage @18102c650`). Dérivables offline : **Resilient** (trait gameconfig + hp/hpmax → cape le
    dégât à `HP-1`) et **member-cap Swarm** (#57d : `nrOfMembers` gameconfig de la cible + hpmax =
    répartition native `GetGroupUnitMemberHealth @1810050f0` ; skip si le profil de L'ATTAQUE a
    `DamageTrait.HitsMultipleMembers` (2) = Blast — d'où `damage_profile` threadé par l'appelant).
    Validé bit-exact 1357 s16 (u139 5 hits 1197/1795 vs necroSmnSwarm 5×444 : caps 442,444,444,444
    puis dernier membre NON cappé → [2971,3569] == natif). Les autres sous-limites restent des **NO-OP
    documentés** (defaults conservateurs) faute d'input offline : Impervious (charge runtime non captée
    par combatSnapshot), boss-cap (`HasTriggeredAbility(0x5d4)` non vérifié offline)."""
    gu = GC.unit(scene.vis_by_id.get(tgt_id)) or {}
    utraits = set(gu.get("traits") or [])
    hpmax = scene.hpmax(tgt_id) or 0
    _dp_traits = (GC.damage_profile(damage_profile) or {}).get("Traits") or [] if damage_profile else []
    return {
        "target_has_resilient": "Resilient" in utraits,
        "target_has_impervious": "Impervious" in utraits,
        "impervious_stat_current": None,             # charge Impervious non captée offline -> no-op (TODO)
        "member_count": int(gu.get("nrOfMembers") or 1),   # GroupUnitComponent (@18102bfe0 lit le composant)
        "member_total_hp": hpmax,
        "profile_has_hits_multiple_members": DamageTrait.HitsMultipleMembers.name in _dp_traits,
        "max_health": hpmax,
        "target_has_boss_cap": False,                # HasTriggeredAbility(0x5d4) non vérifié offline -> no-op (TODO)
        "boss_cap_const": 0,
    }


def _apply_ally_attack_dmg_bonus(mods, scene, att_id, att_pos, is_melee, tgt_armor_reduced, carriers=None,
                                 tgt_id=None, is_normal_attack=None):
    """AURA ALLIEE +degat FLAT projetee sur l'ATTAQUANT par les effets `create_aura_attack_damage_bonus_for_ally`
    de ses ALLIES a portee (canal cote SOURCE) : `BeaconOfRage_FriendlyExtraDamage` (#191 : +50% rage aux amis
    Chaos adjacents en melee), `ConquerorImperative` (#23 : +extraDmg aux amis Mechanical ring-1 vs cible a
    armure reduite), `LordOfTheHost_ExtraDamage` (#57c : +extraDmg melee aux amis RapidAssault/Flying rayon 2
    de Dante) et `Doom_extraDmg` (#57c : +extraDmg aux attaques des amis d'Eldryon CONTRE la cible doomee a
    exactement 2 hexes — gate cote CIBLE, d'ou tgt_id/t_pos/tgt_team dans le ctx). Le +extraDmg de Conqueror
    s'applique a TOUTES les attaques (aucun IsNormalAttack) -> appele par la NORMALE ET la SPECIALE
    (`is_normal_attack` threade pour les gates qui distinguent, ex. la branche non-Aeldari de Doom).
    `carriers` (8-tuple de la normale) reutilisable ; sinon construit un 4-tuple (uid,pos,team,effets). Le ctx
    est keye sur l'ATTAQUANT (+ cible), les gates lisant le sous-ensemble pertinent. Symetrique combat de
    `damage_model._apply_ally_attack_damage_auras`."""
    if carriers is None:
        carriers = [(uid, scene.pos(uid), scene.team(uid), scene.effects(uid))
                    for uid in scene.pos_by_id if uid != att_id and (scene.hp(uid) or 0) > 0]
    att_gu = GC.unit(scene.vis_by_id.get(att_id)) or {}
    ctx = {"att_id": att_id, "att_pos": att_pos, "att_team": scene.team(att_id),
           "att_grand_alliance": att_gu.get("GrandAllianceId"),
           "att_faction": att_gu.get("FactionId"),
           "att_traits": frozenset(att_gu.get("traits") or ()),
           # UnitsWithRangedAttacks (selector SpotterReworked @180f6c860) = UNION {arme ranged au kit}
           # + {diff elevation <= 2 vs tuile porteur} (@180e00610) -> board pour le terme elevation
           "att_has_ranged_weapon": any(w.get("Range") for w in (att_gu.get("weapons") or ())),
           "board": scene.board,
           "is_melee": is_melee, "target_armor_reduced": tgt_armor_reduced,
           "is_normal_attack": is_normal_attack,
           "tgt_id": tgt_id,
           "t_pos": scene.pos(tgt_id) if tgt_id is not None else None,
           "tgt_team": scene.team(tgt_id) if tgt_id is not None else None}
    for eb in aura_attack_damage_bonus_from_allies(carriers, ctx):
        add_modifier(mods, eb)


def defender_prediction_block_amount(scene, tgt_id) -> int:
    """Amount de BLOCK du défenseur pour le scénario `list[0]@0x50` de la prédiction (#54A) —
    mirror des entrées `CalculateBlockChances @181002350` consommées par le scénario block
    (`CalculateDamagePredictionScenario @18102ed00`) : scalaire GetStat(7/8)
    (blockChance/blockDamage) + sources multi-value des EFFETS du défenseur (Daemon_ExtraBlock
    25 %/50 %×Attack courant, BeastSlayer_ExtraBlock…). Approximation documentée : sources
    multiples SOMMÉES (un seul cas mesuré, mono-source Daemon — 1357 s15). 0 = pas de block
    → liste native vide → WillBeKill/WillBeOverkill retombent sur les scalaires raw."""
    amt = 0
    tctx = scene.ctx(tgt_id)
    if tctx is not None and int(tctx.block_chance or 0) > 0:
        amt += int(tctx.block_damage or 0)
    from ..entities.effects import defender_effect_block_sources
    for bs in defender_effect_block_sources(scene.effects(tgt_id), scene.armor(tgt_id),
                                            defender_attack=scene.attack_current(tgt_id)):
        amt += int(bs.amount or 0)
    return amt


# ── #57c-C : overrides `<Boss>_NormalAttackAbility.PredictAttack` (attaque normale + follow-up) ──
# Dispatch natif ActiveAbilityType→classe : l'attaque NORMALE de certains boss est instanciée sur une
# SOUS-CLASSE qui surcharge PredictAttack = base ALoki (@1811afa50) + prédiction ADDITIONNELLE calculée
# sur scénario VIERGE puis sommée via `DamagePredictionResult.Add @18102a710` (appliedHits natif 1+1=2).
# Deux molds (corps COMDAT partagés par famille — l'instance porte la CONFIG du passif du kit) :
#  - RANGED (`Boltstorm_NormalAttackAbility.PredictAttack @1811bd950`, gate arme choisie `!IsMelee`) :
#    `GetAdditionalDamagePrediction @1811bd170` = éval MODE 4 (= MIN) de `GetAdditionalDamageAmount
#    @1811bceb0` = `RandomAmount(var 0xc minDmg, var 0xd maxDmg)` → hits = ConfigConst(0x2f nrOfHits),
#    profil = `AbilityConfiguration.GetDamageProfile` du passif, slot 0x27 SANS widgets modifiers.
#    ⚠ AUCUN porteur confirmé : l'hypothèse « Gulgortz/LightImUp = ce mold » est RÉFUTÉE (varTrace
#    2468 s14 : le +3×1496 de u89 = les 3 effets FoulInfusion_ExtraHits du canal #179 GLOBAL, cf.
#    FoulInfusionExtraHitsEffect ; la coïncidence LightImUp.minDmg[50] == FoulInfusion.dmg[50] == 831
#    a masqué la vraie source). Registre VIDE tant qu'un porteur réel du mold n'est pas mesuré.
#  - MELEE (`ProperKilly_NormalAttackAbility.PredictAttack @1811fc690`, gate `!IsRanged`) :
#    `GetKlawAttack1Prediction @1811fbe10` = n = ConfigConst(0x2f nrOfHits=1) coups de
#    `GetFirstAttackDamage @1811fb760` = `PercentageOf(StatAmount(target, Health=5, part=2 Max),
#    ConfigConst(0x3b dmgPct=60), mode 0)`, profil Power(40), chaque coup via `GetKlawAttack1Hit-
#    Prediction @1811fb800` (même slot standard). Ghazghkull — NON exercé au batch gen (port 1:1
#    du décompilé, non validé live).
# Clé de dispatch = le PASSIF du kit gameconfig (l'instance native lit SA config = celle du passif).
_RANGED_FOLLOWUP_PASSIVES = ()          # vide — cf. réfutation LightImUp ci-dessus (#57c-C)
_MELEE_KLAW_PASSIVES = ("ProperKilly",)


def get_additional_damage_prediction(scene, att_id, tgt_id, ability_name):
    """`Boltstorm_NormalAttackAbility.GetAdditionalDamagePrediction @1811bd170` — follow-up RANGED :
    amount = MIN du `RandomAmount(minDmg, maxDmg)` (éval mode 4), hits = nrOfHits, profil propre du
    passif, mods attaquant ABSENTS (le call slot 0x27 natif ne passe pas les widgets modifiers),
    scénario VIERGE (armure/bouclier de la cible re-disponibles — quirk natif mirroré)."""
    ctx = scene.ctx(att_id)
    if ctx is None:
        return None
    lvl = scene.ablvl_by_id.get(att_id)
    amount = ability_var(ability_name, "minDmg", lvl, multiplier_pct=scene.mult(att_id))
    n = ability_var(ability_name, "nrOfHits", is_constant=True)
    if not amount or amount <= 0 or not n or n <= 0:
        return None
    prof = ((GC.ability(ability_name) or {}).get("constants") or {}).get("damageProfile") or ""
    prof_ratio = int((GC.damage_profile(prof) or {}).get("PiercingRatio") or 0)
    # pierce = profil + ExtraPierce stat (GetAttackPiercingDamageRatio @181030a20, même pipeline 0x27)
    pierce = max(0, min(100, prof_ratio + ctx.extra_pierce + ctx.extra_pierce_ranged))
    tgt_hit_mult = target_hit_multiplier(
        TraitFactory.create_many((GC.unit(scene.vis_by_id.get(tgt_id)) or {}).get("traits")))
    return get_attack_prediction(
        target_current_health=scene.hp(tgt_id) or 0, initial_damage=int(amount), hits=int(n),
        profile_type=_PROFILE_INDEX.get(prof, 0), pierce_pct=pierce, armor=scene.armor(tgt_id),
        mods=None, hit_mult=tgt_hit_mult, target_shield=scene.shield(tgt_id),
        target_limits=_target_damage_limits(scene, tgt_id, prof),
        defender_block_amount=defender_prediction_block_amount(scene, tgt_id))


def get_klaw_attack1_prediction(scene, att_id, tgt_id, ability_name):
    """`ProperKilly_NormalAttackAbility.GetKlawAttack1Prediction @1811fbe10` — klaw MELEE : n coups de
    `PercentageOf(MaxHealth EFFECTIF de la cible, dmgPct, mode 0)` (`GetFirstAttackDamage @1811fb760`),
    profil propre (Power 40), scénario VIERGE, coups chaînés (armure déplétée entre coups — c'est le
    per-coup standard de get_attack_prediction)."""
    ctx = scene.ctx(att_id)
    if ctx is None:
        return None
    pct = ability_var(ability_name, "dmgPct", is_constant=True)
    n = ability_var(ability_name, "nrOfHits", is_constant=True)
    hpmax = scene.hpmax(tgt_id)
    if not pct or pct <= 0 or not n or n <= 0 or not hpmax:
        return None
    amount = _round_fix64(Fraction(int(pct) * int(hpmax), 100), 0)   # PercentageOf mode 0 (half-to-even)
    prof = ((GC.ability(ability_name) or {}).get("constants") or {}).get("damageProfile") or ""
    prof_ratio = int((GC.damage_profile(prof) or {}).get("PiercingRatio") or 0)
    pierce = max(0, min(100, prof_ratio + ctx.extra_pierce + ctx.extra_pierce_melee))
    tgt_hit_mult = target_hit_multiplier(
        TraitFactory.create_many((GC.unit(scene.vis_by_id.get(tgt_id)) or {}).get("traits")))
    return get_attack_prediction(
        target_current_health=scene.hp(tgt_id) or 0, initial_damage=int(amount), hits=int(n),
        profile_type=_PROFILE_INDEX.get(prof, 0), pierce_pct=pierce, armor=scene.armor(tgt_id),
        mods=None, hit_mult=tgt_hit_mult, target_shield=scene.shield(tgt_id),
        target_limits=_target_damage_limits(scene, tgt_id, prof),
        defender_block_amount=defender_prediction_block_amount(scene, tgt_id))


def _normal_attack_followup_prediction(scene, att_id, tgt_id, is_melee, weapon_found):
    """Sélecteur du mold follow-up de l'attaquant (cf. bloc ci-dessus). None = pas de fold
    (pas d'arme trouvée / kit sans passif concerné / gate mêlée-ranged non satisfaite)."""
    if not weapon_found:
        return None                       # mirror `FindAttackWeapon != null` (@1811bd950 / @1811fc690)
    try:
        kit = GC.unit_abilities(scene.vis_by_id.get(att_id)) or {}
    except Exception:
        return None
    names = {(a.get("name") or "") for lst in (kit.get("passive"), kit.get("active"))
             for a in (lst or [])}
    if not is_melee:
        for nm in _RANGED_FOLLOWUP_PASSIVES:
            if nm in names:
                return get_additional_damage_prediction(scene, att_id, tgt_id, nm)
    else:
        for nm in _MELEE_KLAW_PASSIVES:
            if nm in names:
                return get_klaw_attack1_prediction(scene, att_id, tgt_id, nm)
    return None


def _display_attack_base(scene, att_id, attack_pos, is_melee):
    """Base ATTACK de la chaîne DISPLAY, re-positionnée à la tuile candidate (#49/#153/#57a) :
    base = CURRENT(du pas) − aura_modèle(position réelle) + aura_modèle(tuile candidate). Les AURAS
    stat-mod d'alliés (RitesOfBattle @181225340, PathOfCommand @181110f10) sont ré-évaluées à
    `attack_pos` ; les mods NON-positionnels (ex. SummaryExecution_BaseEffect 1043 +400, #57a)
    restent inclus via CURRENT. FOYER PARTAGÉ (#61bis tranche 3) : l'attaque normale ALoki
    (`GetAttackHitPrediction @1811af4e0` = GetStat(Attack, Current) + arme) ET le chemin drone MV71
    (délégué b__1 @181119590 = `StatAmount(Caster, ATTACK, CURRENT)`) font la MÊME lecture native.
    Renvoie `(attack_base, carriers, att_grand, att_faction, _ap)` (carriers/gates réutilisés par
    l'appelant normal pour les hits/auras)."""
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
    # #41 : gate de MATÉRIALISATION pour la MÊLÉE SEULEMENT (att_real_pos=None -> gate inactif).
    # Mesures seed-31337 (2026-07-20) : RANGED suit purement la tuile CANDIDATE (#153 confirmé, gain
    # inclus — u95 thousAhriman réel dist-3 de Calgar, candidate (4,5) in-ring : natif = base+898 sur
    # les 2 canaux ranked/aiPlaybookPredict) ; MÊLÉE ne gagne PAS l'aura d'une tuile candidate (u93
    # deathRotbone s13 : candidate (2,3) in-ring, natif = base Initial ×1.5 élévation EXACT). Le seul
    # cas mêlée+matérialisé mesuré ((6,5) u91) est candidate-out-ring (les deux modèles le couvrent) —
    # si un futur contre-cas mêlée+matérialisé+in-ring sort sans aura native, passer la mêlée en
    # « jamais d'aura » (v4) et RE le read natif du stat Attack en prédiction.
    aura_ctx = {"att_id": att_id, "att_pos": _ap, "att_team": scene.team(att_id),
                "att_grand_alliance": att_grand, "att_faction": att_faction, "board": scene.board,
                "att_real_pos": scene.pos(att_id) if is_melee else None}
    carriers = [(uid, scene.pos(uid), scene.team(uid), scene.mult(uid), scene.ablvl_by_id.get(uid),
                 (GC.unit(scene.vis_by_id.get(uid)) or {}).get("GrandAllianceId"),   # owner grande-alliance
                 (GC.unit(scene.vis_by_id.get(uid)) or {}).get("FactionId"),         # owner faction
                 scene.effects(uid)) for uid in scene.pos_by_id                      # (type-level, miroir-safe)
                if uid != att_id and (scene.hp(uid) or 0) > 0]
    # #41 : tuile candidate NON-ENTRABLE (BlockEnteringUnits, ex. mur Thorns (1,3) MC1_67) -> le natif
    # perd l'aura MÊME matérialisée+in-ring (u89 s11 : candidate (1,3) = base Initial 803 ×1.5 élévation
    # EXACT, vs (3,3) propre = 2101 gardé) : `GetUnitPositionAtTile` sur tuile bloquée rend une position
    # dégénérée -> l'adjacence du re-check échoue. L'élévation, lue sur la TUILE, s'applique toujours.
    _cand_blocked = "BlockEnteringUnits" in ((scene.tile_effects_by_pos or {}).get(tuple(_ap)) or ())
    # #57a : la base CONSERVE les stat-mods NON-positionnels courants (SummaryExecution_BaseEffect
    # 1043 : +400 flat aux Friends(UnitsWithTrait), sélecteur SANS nœud d'adjacence — décompilé
    # `SummaryExecutionEffect.CreateTargetSelector @180f6f8a0` ; vécu 1357 s15 u135 : natif per-hit
    # = 1.2/1.8 × 1496 (CURRENT) et non ×1096 (INITIAL)). Modèle : base = CURRENT(du pas)
    # − aura_modèle(position réelle) + aura_modèle(tuile candidate) — algébriquement
    # = INITIAL + mods-non-aura + auras ré-évaluées (#153) ; identique à l'ancien INITIAL+aura
    # quand aucun mod non-aura n'est posé (aura_baked == aura_modèle(réel), cf. #49 exact).
    _aura_cand = 0 if _cand_blocked else aura_attack_bonus_from_allies(carriers, aura_ctx)
    _rp = scene.pos(att_id)
    _aura_real = (aura_attack_bonus_from_allies(
        carriers, {**aura_ctx, "att_pos": _rp, "att_real_pos": _rp if is_melee else None})
        if _rp is not None else 0)
    attack_base = scene.attack_current(att_id) - _aura_real + _aura_cand
    return attack_base, carriers, att_grand, att_faction, _ap


_MV71_CONFIG = "MV71SniperDroneSquad"    # l'entrée gameconfig (passif 1119) qui porte constants/variables


def _make_mv71_drone_predictions(scene, att_id, tgt_id, attack_pos, *, meta=False):
    """`MV71SniperDroneSquadAttackAbility.PredictAttack @18110a5f0`, branche DISTANCE (#61bis
    tranche 3 — la branche mêlée délègue à ALoki et reste dans `make_normal_attack_predictions`).

    Mirror du décompilé (re-lu 2026-07-22) :
      - tile = PickTile — délégué b__0 @1811194e0 = `() => PickTile(entities, firstOnly=0)`, LE MÊME
        PickTile que l'exécution (mémoïsé par un service de cache) -> `pick_tile_scene` (hydrateur
        scene du port runner, scoring partagé). Parent = la POSITION CANDIDATE (#153).
        **Aucune tuile -> prédiction VIDE** (memset 0xc0 + liste block vide = résultat ZÉRO, pas
        d'absence d'event).
      - hits = `ExtraHitsComponent(CASTER).CurrentValue + 1`, stocké DisplayClass@0x148 et consommé
        par le 3ᵉ délégué (DAT_183279860 — « b__2 » sans symbole ghidra, alias « m860 ») : rôle
        compte-de-coups tranché PAR ÉLIMINATION (b__0 = tile, b__1 = dégât : aucun autre lecteur
        possible du champ @0x148) + position = celle du délégué hits par défaut du fallback ALoki
        (slot 0x25, DAT_183283000). Confronté live via `appliedHits` d'aiPlaybookPredict.
      - dégât = délégué b__1 @181119590 = `StatAmount(Caster, ATTACK, CURRENT)` ->
        `_display_attack_base` (MÊME lecture display que la normale, re-positionnée #153).
      - arme = la config d'attaque du DRONE (service slot 0xc0 = unit-config par id, champ @0x18),
        résolue par la distance TUILE DU DRONE -> cible (le drone tire de SA tuile) ; pierce =
        PiercingRatio du profil + ExtraPierce de l'unité passée au service (`GetUnit(tile) ?? caster`
        -> le CASTER à la prédiction, aucun drone encore posé — flag : au fallback-cap la tuile porte
        un drone, l'unité native serait CE drone, ExtraPierce 0 dans les deux cas).
      - attribution = Nullable<AbilityOrEffect>(1076) ; canal additional-hits keyé sur l'attackTypeId
        du drone (unit-config @0x10) : `GetAdditionalHitsFromEffectsForPrediction` +
        `AddAdditionalHitsToPrediction` — MÊME canal #179 que la normale (effets du CASTER + auras).
      - modifiers (ARBITRÉ LIVE, probe_61bis_pred seed 61011) : le widget attaquant est **ZÉROÉ**
        (memset `&local_3f8` — le `param_4` du playbook N'EST PAS forwardé, contrairement à la
        branche mêlée qui le passe à ALoki) -> AUCUN mod ATTAQUANT-effets (builder @181000590 côté
        appelant ; résidu flaggé : aucun datapoint caster-avec-effet-d'attaque encore). MAIS les
        mods POSITIONNELS + DÉFENSEUR sont calculés EN AVAL DANS le service et S'APPLIQUENT :
          . ÉLÉVATION évaluée à la TUILE DU DRONE vs cible (rows x1.5 EXACT quand la tuile choisie
            est surélevée : (3,6)/(2,6)/(6,6) elev2 vs cible elev1 — le flip post-cast de (4,6)
            1.5->1.15 quand le drone réel occupe (3,6) le prouve) ;
          . DÉFENSEUR : cible Markerlit -> x1.15 EXACT sur les rows plates (3694,5541 = 3212,4818
            x1.15), composé x1.725 = 1.5x1.15 sur les rows surélevées.
        -> port : `_add_positional_and_defender_mods(attack_pos = TUILE DU DRONE)` sur un
        `DamageModifiers()` vierge (l'attaquant du coup = le drone, identité/niveau = caster,
        mirror du `unit` passé au service)."""
    ctx = scene.ctx(att_id)
    if ctx is None:
        return None
    consts = (GC.ability(_MV71_CONFIG) or {}).get("constants") or {}
    unit_id = consts.get("unitId")                       # GetStringConstant(cfg, 0) = tauSmnDroneSniper
    max_summons = int(consts.get("maxSummons") or 3)
    t_pos = scene.pos(tgt_id)
    if unit_id is None or t_pos is None:
        return None
    from engine.runner.abilities.loki.mv71 import pick_tile_scene
    tile_pos = pick_tile_scene(scene, att_id, tgt_id, unit_id, max_summons,
                               parent_pos=attack_pos or scene.pos(att_id))
    if tile_pos is None:
        from engine.services.damage_prediction import DamagePredictionResult
        ev = ProbableDamageEvent(target=tgt_id, prediction=DamagePredictionResult())
        return (ev, {"mv71": True, "tile": None}) if meta else ev
    # hits (délégué « m860 ») = ExtraHits CURRENT du CASTER + 1 — PAS la formule arme
    # (AttackHitsWithModifiersFormula n'est PAS appelée sur ce chemin : ni GetStuckIn, ni malus
    # défenseur LightCover/Parry, ni hits d'arme).
    _xh = scene.extra_hits_current(att_id)
    hits = 1 + int(_xh if _xh is not None else (ctx.stat(StatType.EXTRA_HITS) or 0))
    # dégât (délégué b__1) = StatAmount(Caster, ATTACK, CURRENT) — foyer partagé display (#153).
    attack_base, carriers, att_grand, att_faction, _ap = _display_attack_base(
        scene, att_id, attack_pos, is_melee=False)
    # arme du drone par distance tuile->cible (mirror config d'attaque @0x18 du unit-config drone).
    from engine.services.battle_query import get_attack_weapon_for_default_normal_attack
    _adj = are_tiles_adjacent(tile_pos, t_pos, scene.board)
    _d = hexgeo.distance(tile_pos, t_pos)
    w, w_ranged = get_attack_weapon_for_default_normal_attack(unit_id, _adj, dist=_d)
    prof_name = (w or {}).get("DamageProfile")
    _dpw = GC.damage_profile(prof_name) or {}
    dir_pierce = ctx.extra_pierce_ranged if w_ranged else ctx.extra_pierce_melee
    pierce = max(0, min(100, int(_dpw.get("PiercingRatio") or 0) + ctx.extra_pierce + dir_pierce))
    from engine.services.damage_modifiers import DamageModifiers
    mods = DamageModifiers()                             # widget attaquant ZÉROÉ (cf. docstring)
    # POSITIONNELS + DÉFENSEUR (service-side, arbitré live) : attack_pos = LA TUILE DU DRONE
    # (élévation drone->cible), défenseur incl. Markerlight (faction caster = T'au, threadée #61bis).
    _add_positional_and_defender_mods(mods, scene, att_id, tgt_id, not w_ranged, tuple(tile_pos),
                                      t_pos, damage_profile=prof_name)
    # canal additional-hits #179 (clé native = attackTypeId du drone) — mêmes sources que la normale.
    att_effects = scene.effects(att_id)
    _ah_ctx = {"is_melee": False,
               "tgt_traits": frozenset((GC.unit(scene.vis_by_id.get(tgt_id)) or {}).get("traits") or ()),
               "tgt_effect_names": frozenset(
                   n for n in (getattr(_e, "name", None) for _e in (scene.effects(tgt_id) or [])) if n)}
    _aura_hits = aura_additional_hits_from_allies(
        carriers, {"att_id": att_id, "att_pos": _ap, "att_team": scene.team(att_id),
                   "att_faction": att_faction, "att_grand_alliance": att_grand,
                   "is_melee": False})
    _extra_groups = []
    for _g in list(additional_hit_groups(att_effects, _ah_ctx)) + _aura_hits:
        _dp2 = GC.damage_profile(_g["profile"]) or {}
        _gp = max(0, min(100, int(_dp2.get("PiercingRatio") or 0) + ctx.extra_pierce))
        _entry = {"count": _g["count"], "pierce_pct": _gp,
                  "profile_type": _PROFILE_INDEX.get(_g["profile"], 0), "mods": mods,
                  "profile_has_hits_multiple_members":
                      DamageTrait.HitsMultipleMembers.name in (_dp2.get("Traits") or [])}
        if "amount" in _g:
            _entry["amount"] = _g["amount"]
        else:
            _entry["predefined"] = MinMaxDamage(min=_g["min"], max=_g["max"])
        _extra_groups.append(_entry)
    tgt_hit_mult = target_hit_multiplier(
        TraitFactory.create_many((GC.unit(scene.vis_by_id.get(tgt_id)) or {}).get("traits")))
    res = get_attack_prediction(
        target_current_health=scene.hp(tgt_id) or 0, initial_damage=attack_base, hits=hits,
        profile_type=_PROFILE_INDEX.get(prof_name, 0), pierce_pct=pierce, armor=scene.armor(tgt_id),
        mods=mods, hit_mult=tgt_hit_mult, target_shield=scene.shield(tgt_id),
        target_limits=_target_damage_limits(scene, tgt_id, prof_name),
        extra_groups=_extra_groups,
        defender_block_amount=defender_prediction_block_amount(scene, tgt_id))
    ev = ProbableDamageEvent(target=tgt_id, prediction=res)
    if meta:
        return ev, {"mv71": True, "tile": tile_pos, "base": attack_base, "hits": hits,
                    "pierce": pierce, "profile": prof_name}
    return ev


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
    # --- #61bis tranche 3 : dispatch NormalAttackType CONCRET -> override `MV71SniperDroneSquad-
    # AttackAbility.PredictAttack @18110a5f0` (1076). Le natif dispatche par vtable (l'attaque normale
    # per-unit EST l'instance MV71 pour un porteur du passif) ; le port dispatche par kit. MÊLÉE
    # (`IsMeleeAttack @181109960`, évaluée sur la POSITION CANDIDATE threadée par la chaîne display) ->
    # délégation TOTALE à ALoki.PredictAttack AVEC les modifiers d'origine = on RESTE ici (chemin
    # arme) ; DISTANCE -> chemin drone (config du drone, dégât StatAmount(caster), widget mods zéroé).
    if is_adjacent is not True:
        from engine.runner.abilities.loki.mv71 import is_mv71_normal_attacker
        if is_mv71_normal_attacker(scene.vis_by_id.get(att_id)):
            return _make_mv71_drone_predictions(scene, att_id, tgt_id, attack_pos, meta=meta)
    _dist = hexgeo.distance(attack_pos, t_pos) if (attack_pos and t_pos) else None   # porte portée ranged #188
    pierce, _ranged, whits, prof_name = _weapon_pierce(scene, att_id, is_adjacent, _dist)
    is_melee = not _ranged
    _hm = (attack_pos != scene.pos(att_id)) if attack_pos else None
    # PRÉDICTION (slot 0xd) — branche distincte du combat (runner). Le debuff stat-modifications
    # (CalculateModifiersFromStatModifications @181004380, prédiction-only) reste GATÉ off : ce
    # N'EST PAS un modifier post-perçage mais un effet AU NIVEAU DE LA BASE (cf. base=Initial ci-dessous).
    # BeastSlayer (target-conditionnel) : traits de la CIBLE (mirror HasTrait) -> gate BigTarget/Vehicle.
    _tgt_traits = frozenset((GC.unit(scene.vis_by_id.get(tgt_id)) or {}).get("traits") or [])
    # gate ConquerorImperative (#22, self face) : la CIBLE a-t-elle l'armure REDUITE (>=1 mod <0 sur
    # ARMOR/FIXED_ARMOR) -> +extraDmg FLAT du porteur. OwnerIsCaster TRUE en display (cf. DecoysAndMisdirection).
    _tctx = scene.ctx(tgt_id)
    _tgt_armor_reduced = (_tctx.stats.has_negative_modifier(ARMOR_STAT_TYPES)
                          if _tctx is not None and _tctx.stats is not None else None)
    # att_ctx POSITIONNEL (#29) : magnitude re-countee a la TUILE CANDIDATE pour les bonus dont le DSL lit
    # la UnitPosition hypothetique (LordOfTempests : Count(Ice ring-1) @180f56b40 — meme threading candidat
    # que les auras #153). tile_effects_by_pos = tileMeta FRAIS du pas (la glace s'accumule).
    _att_ctx = {"att_pos": attack_pos or scene.pos(att_id),
                "tile_effects_by_pos": scene.tile_effects_by_pos}
    mods = calculate_attacker_modifiers_for_prediction(att_effects, is_ranged=_ranged, has_moved=_hm,
                                                       target_traits=_tgt_traits,
                                                       target_armor_reduced=_tgt_armor_reduced,
                                                       att_ctx=_att_ctx)
    # #49/#153/#57a : base display re-positionnée à la tuile candidate — foyer PARTAGÉ `_display_
    # attack_base` (aussi consommé par le chemin drone MV71, #61bis tranche 3 : délégué b__1 = la
    # même lecture native StatAmount(Caster, ATTACK, CURRENT)).
    attack_base, carriers, att_grand, att_faction, _ap = _display_attack_base(
        scene, att_id, attack_pos, is_melee)
    _add_positional_and_defender_mods(mods, scene, att_id, tgt_id, is_melee, attack_pos, t_pos,
                                      damage_profile=prof_name)
    # AURA ENNEMIE %-degat projetee sur l'ATTAQUANT : ShadowInTheWarp_LessDmg_Effect (-25% Psychic aux
    # ennemis a portee du porteur) — reutilise `carriers` (toutes les autres unites vivantes), gate Psychic
    # + team ennemie + portee dans le create_aura_. Ajoute aux modifiers %-list de l'attaquant.
    for _eb in aura_attack_damage_malus_from_enemies(
            carriers, {"att_id": att_id, "att_pos": _ap, "att_team": scene.team(att_id),
                       "damage_profile": prof_name}):
        add_modifier(mods, _eb)
    # AURA ALLIEE FLAT-degat projetee sur l'ATTAQUANT (canal cote SOURCE) : BeaconOfRage_FriendlyExtraDamage
    # (+50% rage aux amis Chaos adjacents en melee, #191) + ConquerorImperative (+extraDmg aux amis Mechanical
    # ring-1 vs cible a armure reduite, #23). Reutilise `carriers` (8-tuple) ; gates (is_melee/grande-alliance ;
    # Mechanical/target_armor_reduced) dans le create_aura_. Additif -> mods.additive (meme canal que le self,
    # deja bit-exact). NB : le self (le porteur attaque) et l'aura (un ami attaque) portent sur des ATTAQUANTS
    # distincts -> jamais cumules.
    _apply_ally_attack_dmg_bonus(mods, scene, att_id, _ap, is_melee, _tgt_armor_reduced, carriers,
                                 tgt_id=tgt_id, is_normal_attack=True)
    # Nb de coups : cette prediction EST la facade `DamagePrediction.GetAttackHits @18102f240` — elle
    # rassemble les entrees depuis la Scene puis appelle la FORMULE PARTAGEE `attack_hits_with_modifiers`
    # (`AttackHitsWithModifiersFormula.Calculate @180f0bf50`, MEME formule que la facade combat runner) :
    # base weapon+ExtraHits+effets, +GetStuckIn/traits, +malus defenseur (LightCover/Parry) + auras (BigTarget).
    # VIVANTS SEULEMENT (#57m) : le board natif = OCCUPATION DE TUILE (`AdjacentUnits @180de8320` =
    # `Units(AdjacentTiles(.)) - .`) — les cadavres de scene.pos_by_id (decisionView les garde) n'y
    # sont plus : ni compte GetStuckIn (@180f83460), ni porteur d'aura (idiome hp>0, cf. l.227/276).
    _alive_ids = [uid for uid in scene.pos_by_id
                  if uid in (att_id, tgt_id) or (scene.hp(uid) or 0) > 0]
    board = {"att_id": att_id, "tgt_id": tgt_id, "attack_pos": attack_pos, "t_pos": t_pos,
             "tgt_team": scene.team(tgt_id), "is_melee": is_melee,
             "pos_by_id": {uid: scene.pos_by_id[uid] for uid in _alive_ids},
             "team_by_id": scene.team_by_id,
             # faction par unité — gate GetBonusHitChance de GetStuckIn (orks_adj>=2, @180f83460, #98)
             "faction_by_id": {uid: scene.faction(uid) for uid in _alive_ids}}
    tgt_effects = scene.effects(tgt_id)
    aura_sources = [(uid, scene.pos(uid), scene.team(uid), scene.effects(uid))
                    for uid in _alive_ids if uid != tgt_id]
    # #57a : EXTRA_HITS DU PAS (scene, refresh par-pas) et non le cold ctx — les stat-mods hits
    # dynamiques (Swarm_HitReduction : -1 hit/membre perdu) sont posés APRES l'hydratation.
    _xh = scene.extra_hits_current(att_id)
    # #62 : gates/branches TUILE compute-time des malus défenseur — le natif les évalue AUSSI en
    # prédiction (formule PARTAGÉE @180f0bf50) : LightCover `AreEqual(coverPatch, target)` @180f556b0,
    # Camouflage branche -3 `HasTile(TilesWithTriggeredAbility(Tiles(Target), 57))` @181107180. Terrain
    # de la CIBLE (immobile : seule la tuile candidate de l'attaquant varie) via scene.board (#124),
    # mirror du call-site combat (operations/damage.py). Board KO -> None = applique-sur-présence.
    _t_terrain = scene.board.terrain_at(t_pos[0], t_pos[1]) if scene.board is not None else None
    _on_cover = (_t_terrain == LIGHT_COVER_TILE_ID) if _t_terrain is not None else None
    hits = attack_hits_with_modifiers(weapon_hits=whits,
                                      extra_hits=_xh if _xh is not None else ctx.stat(StatType.EXTRA_HITS),
                                      extra_hits_melee=ctx.extra_hits_melee,
                                      attacker_effects=att_effects, trait_objects=ctx.trait_objects(),
                                      target_effects=tgt_effects, aura_sources=aura_sources, board=board,
                                      is_melee=is_melee, damage_profile=prof_name,
                                      include_bonus_hit_behaviours=True,  # prediction folde GetStuckIn (deterministe)
                                      defender_on_cover=_on_cover)
    # MkXGravis (trait CIBLE 0x3f5) : l'armure est traversée 2× → hit_mult=2 dans predict_attack_raw
    # (GetBaseDamageWithFixedPiercedArmor @181030d10). No-op (=1) pour toute cible sans trait hit-twice.
    tgt_hit_mult = target_hit_multiplier(TraitFactory.create_many(_tgt_traits))
    # #179 : coups additionnels HETEROGENES (SquigHound_AdditionalHits) — dégât/profil PROPRE, prev-threadés
    # APRES les coups d'arme (overkill continu). Chaîne native (RE) : `AActiveAbility.AddAdditionalHitsTo-
    # Prediction @180faff30` -> par coup `get_DefaultBlockScenario(result)` (prev threadé) puis `GetEffect-
    # AdditionalHitPrediction @180fb1260` -> le MEME delegate PredictAttack (slot 0x26) / `PredictAttackRaw
    # @181032fb0` que les coups d'arme, avec le CONTEXTE MODIFIERS COURANT. Donc chaque groupe : `count` coups
    # [min,max] (predefined, sans spread ±20% = RandomAmount natif) au profil propre (pierce = PiercingRatio du
    # profil + extra_pierce), MEME armure/hp/bouclier/hit_mult(MkXGravis) que la cible, ET `mods` COMPLET — le
    # coup subit le même pipeline : réductions défenseur plates (Nightshroud_DmgReduction, fusionnées dans
    # mods.additive) + %-mods/additif attaquant. Mirror `EffectAdditionalHits.Create @180f405b0`. [] hors carrier.
    # #57c-C : deux sources de groupes — (a) effets du PORTEUR (SquigHound/CordClaw/FoulInfusion,
    # triggers OwnerIsActor/OwnerIsCaster+IsMeleeAttack EVALUES : ctx is_melee threade) ; (b) effets-
    # AURA d'ALLIES adjacents (ExplosiveMaladies : adjacence re-evaluee a la TUILE CANDIDATE, mirror
    # de l'enumeration globale @180e59150 + selecteur @180f43ef0). Les groupes "amount" (ConfigVar
    # seul) prennent le spread ±20% du pipeline ; TOUS les groupes recoivent les %-mods attaquant
    # (mesure 2468 s14 : le coup ExplosiveMaladies de u89 subit bien le x1.5 CrushingStrike).
    _extra_groups = []
    # #57e : gates CIBLE des descripteurs additional-hits (ex. CyclicIonBlaster ConditionalAmount
    # HasEffect(target, Markerlight) | HasTrait(target, Mechanical)) — traits gameconfig + noms
    # d'effets ACTIFS de la cible threades dans le ctx du canal #179.
    _ah_ctx = {"is_melee": is_melee,
               "tgt_traits": frozenset((GC.unit(scene.vis_by_id.get(tgt_id)) or {}).get("traits") or ()),
               "tgt_effect_names": frozenset(
                   n for n in (getattr(_e, "name", None) for _e in (scene.effects(tgt_id) or [])) if n)}
    _aura_hits = aura_additional_hits_from_allies(
        carriers, {"att_id": att_id, "att_pos": _ap, "att_team": scene.team(att_id),
                   "att_faction": att_faction, "att_grand_alliance": att_grand,
                   "is_melee": is_melee})
    for _g in list(additional_hit_groups(att_effects, _ah_ctx)) + _aura_hits:
        _dp = GC.damage_profile(_g["profile"]) or {}
        _gp = max(0, min(100, int(_dp.get("PiercingRatio") or 0) + ctx.extra_pierce))
        _entry = {"count": _g["count"], "pierce_pct": _gp,
                  "profile_type": _PROFILE_INDEX.get(_g["profile"], 0), "mods": mods,
                  # #57d : le member-cap Swarm lit le profil DU COUP (param_5 d'@18102bfe0) — un coup
                  # additionnel Blast (HitsMultipleMembers) skippe le cap meme si l'arme ne le fait pas.
                  "profile_has_hits_multiple_members":
                      DamageTrait.HitsMultipleMembers.name in (_dp.get("Traits") or [])}
        if "amount" in _g:
            # #65 : PAS de troncature int — un amount midpoint (Average natif, ex. FleshmetalGuns)
            # peut valoir x.5 ; le spread Fix64 (`calculate_damage_spread` from_number) le gere exact.
            _entry["amount"] = _g["amount"]
        else:
            _entry["predefined"] = MinMaxDamage(min=_g["min"], max=_g["max"])
        _extra_groups.append(_entry)
    res = get_attack_prediction(
        target_current_health=scene.hp(tgt_id) or 0, initial_damage=attack_base, hits=hits,
        profile_type=0, pierce_pct=pierce, armor=scene.armor(tgt_id), mods=mods, hit_mult=tgt_hit_mult,
        target_shield=scene.shield(tgt_id), target_limits=_target_damage_limits(scene, tgt_id, prof_name),
        extra_groups=_extra_groups,
        defender_block_amount=defender_prediction_block_amount(scene, tgt_id))
    # #57c-C : override PredictAttack des attaques normales de boss (Gulgortz/LightImUp, Ghazghkull/
    # ProperKilly) — prédiction ADDITIONNELLE sur scénario VIERGE sommée via DamagePredictionResult.add
    # (@18102a710), cf. bloc _RANGED_FOLLOWUP_PASSIVES ci-dessus.
    _fw = _normal_attack_followup_prediction(scene, att_id, tgt_id, is_melee, prof_name is not None)
    if _fw is not None:
        res.add(_fw)
    ev = ProbableDamageEvent(target=tgt_id, prediction=res)
    if meta:
        _m = {"base": attack_base, "pierce": pierce, "armor": scene.armor(tgt_id), "hits": hits,
              "mods": [round(m, 3) for m, _c in mods.pct_list] or None,
              "effects": [e.name for e in att_effects] or None}
        if _fw is not None:
            _m["followup"] = {"min": _fw.raw_health_damage.min, "max": _fw.raw_health_damage.max}
        return ev, _m
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
    # gate ConquerorImperative (#22) : +extraDmg s'applique AUSSI aux attaques SPECIALES du porteur (trigger
    # OwnerIsCaster & HasNegativeModifier, AUCUN IsNormalAttack) vs cible a armure reduite.
    _tctx = scene.ctx(tgt)
    _tgt_armor_reduced = (_tctx.stats.has_negative_modifier(ARMOR_STAT_TYPES)
                          if _tctx is not None and _tctx.stats is not None else None)
    mods = calculate_attacker_modifiers_for_prediction(scene.effects(uid), is_ranged=not is_melee,
                                                       has_moved=_hm, is_normal_attack=False,
                                                       target_armor_reduced=_tgt_armor_reduced,
                                                       att_ctx={"att_pos": attack_pos or scene.pos(uid),
                                                                "tile_effects_by_pos":
                                                                    scene.tile_effects_by_pos})
    t_pos = scene.pos(tgt)
    _add_positional_and_defender_mods(mods, scene, uid, tgt, is_melee, attack_pos, t_pos,
                                      damage_profile=profile_name, is_normal_attack=False)
    # AURA ALLIEE +extraDmg (ConquerorImperative #23 / BeaconOfRage #191) : le +extraDmg de Conqueror n'a AUCUN
    # gate IsNormalAttack -> s'applique aussi quand un ami Mechanical adjacent utilise une attaque SPECIALE vs
    # cible a armure reduite (symetrique de la normale). Gates dans le create_aura_ (Mechanical/adjacence/team/
    # target_armor_reduced ; BeaconOfRage : is_melee/Chaos).
    _apply_ally_attack_dmg_bonus(mods, scene, uid, attack_pos or scene.pos(uid), is_melee, _tgt_armor_reduced,
                                 tgt_id=tgt, is_normal_attack=False)
    tgt_shield = scene.shield(tgt)
    # Base spéciale = `base` (avg(minDmg,maxDmg) scalé rareté) route par le MÊME chemin que la normale
    # (GetBaseDamageFix64 ±20% dans predict_attack_raw). L'ancien chemin `get_multi_hit_attack_prediction(
    # damage=...)` (plage empirique 0.8/2.2·d/hits) était FAUX (RE PredictAttackRaw @181032fb0 : base = 1 int
    # -> ±20% [0.8/1.2], aucun 2.2) -> SUPPRIMÉ. Les specials Attack-based (PlasmaCannon/SpiritLeech) ne
    # passent PAS ici (routés via _PREDICT_VIA_NORMAL_ATTACK). Le bouclier est déplété PAR COUP (prev).
    # MkXGravis (trait CIBLE 0x3f5) : armure traversée 2× aussi pour les spéciales (CalculateBaseDamage
    # WithAllModifiers appelé quel que soit l'ability). No-op (=1) si la cible n'a pas le trait hit-twice.
    tgt_hit_mult = target_hit_multiplier(
        TraitFactory.create_many((GC.unit(scene.vis_by_id.get(tgt)) or {}).get("traits")))
    return get_attack_prediction(
        target_current_health=scene.hp(tgt) or 0, initial_damage=base, hits=hits,
        profile_type=profile_idx, pierce_pct=pierce, armor=scene.armor(tgt),
        mods=mods, target_shield=tgt_shield, hit_mult=tgt_hit_mult,
        target_limits=_target_damage_limits(scene, tgt, profile_name),
        defender_block_amount=defender_prediction_block_amount(scene, tgt))


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
# #171 — SorcerousFacade (1100, thousTzaangor) EST un membre LEGITIME (distinct des specials #99 ci-dessus).
#    Son `SorcerousFacadePlaybook.MakeDamagePredictions @18115bb90` construit pour la cible ENNEMIE
#    (`TargetsSelector.SelectFirst @18115bcf0`) un EVENT #1 = ATTAQUE NORMALE du caster, via l'interface
#    `DAT_18327ff80` slot 0x21 @~18115bd60 — le MEME mecanisme que `NormalAttackPlaybook.MakeDamagePredictions
#    @18149eeb0` (= "profil d'attaque normale du caster vs target"). PUIS un event #2 secondaire
#    `GenerateMultiHit(base=Half(Sum(minDmg,maxDmg)) config, profile=null)` = [1197,1795] (AddRange) que
#    l'ORACLE ne remonte PAS (dedup aval + regle : l'ennemi ne subit QUE l'attaque normale declenchee ; le
#    728-1455 Psychic est un BUFF pour les futures attaques normales). L'event ennemi expose par
#    aiPlaybookPredict = l'attaque normale -> [1623,3591] bit-exact live (probe171, side-by-side vs id 69).
#    Ce N'EST PAS le cas #92 refute (heritage vtable PredictAttack Attack-based) : ici le playbook EMET
#    explicitement une prediction d'attaque normale. Cf. docs/rl/case-171-sorcerousfacade-normal-attack.md.
_PREDICT_VIA_NORMAL_ATTACK = frozenset({"SorcerousFacade"})


# ── Overrides d'ENTREE per-ability — mirror des `<Ability>Playbook.MakeDamagePredictions` qui SURCHARGENT
#    la base/hits generiques. Le natif dispatche par type d'ability (registre playbook / vtable) ; le port,
#    qui collapse tous les playbooks dans `make_damage_predictions`, dispatche par id via ce registre. Chaque
#    handler = HOMONYME du playbook natif + VA ; rend un dict `{base_override?, hits_override?, profile_override?}`
#    (kwargs de `generate_multi_hit_attack_prediction`) ou `{}`. La methode generique reste GENERIQUE : aucune
#    logique ability-specifique inline (ajouter une ability divergente = un handler + une entree registre).
def _martial_inspiration_inputs(scene, caster_id, target_id, ab, cfg) -> dict:  # target_id ignoré (contrat registre)
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


def _crushing_claws_inputs(scene, caster_id, target_id, ab, cfg) -> dict:  # target_id ignoré (contrat registre)
    """`CrushingClawsPlaybook.MakeDamagePredictions @1811274b0` (tyranTyrantGuard, ability 1105) — la
    PRÉDICTION ignore le `damageProfile` de l'ability : le playbook passe **`param_8 = null`**
    (`Nullable<DamageProfile>` sans valeur) à `GenerateMultiHitAttackPredictions @181409da0`, pour la cible
    principale ET chaque splash (les DEUX appels natifs passent 0). Le profil de prédiction vient de CE
    param_8 (choix du playbook), PAS de `ability.damageProfile` -> null = profil `None` (enum -1) -> **pierce 0**
    (l'armure s'applique PLEINE), au lieu du `Piercing{PiercingRatio:80}` de l'ability. C'est un quirk NATIF
    (le playbook « oublie » de passer le profil) : l'IA SOUS-évalue CrushingClaws face à une cible blindée.
        Contraste `HarvesterOfSoulsPlaybook @1811428b0` : passe `Nullable(0x13=19=HeavyRound)` -> pierce 55
        (le port le retrouve via `ab.get_damage_profile()`, d'où sa justesse générique).
    PROUVÉ LIVE (2 niveaux d'armure, base avg 1746 = (minDmg1496+maxDmg1996)/2, pierce 0) :
      - cible armure 2312 : base±20% [1397,2095] − 2312 < 0 -> plancher 1/coup -> main [2,2] / splash [1,1] EXACT.
      - cible armure 1003 : [1397−1003, 2095−1003] = [394,1092]/coup -> main(2c) [788,2184] / splash(1c) [394,1092] EXACT.
    Le port appliquait `dp.PiercingRatio=80` -> [2236,3352] (sur-prédiction). Fix = mirror param_8=null =
    profil `None` (pierce 0, profile_idx -1). Cf. docs/rl/case-164-crushingclaws-pierce.md."""
    return {"profile_override": "None"}


def _hellfire_shells_inputs(scene, caster_id, target_id, ab, cfg) -> dict:
    """`HellfireShellsPlaybook.MakeDamagePredictions @181143a00` (carrier NPC/summon ultraNpc4Heavy-
    Intercessor / ultraSmnHeavyIntercessor, ability 1080) — mirror parfait de `CrushingClawsPlaybook
    @1811274b0` (meme signature, meme appel `GenerateMultiHitAttackPredictions @181409da0`). SURCHARGE :
      - BASE = `Direct(GetVariableForLevel(0xc=minDmg))` @180dee2a0 = minDmg SEUL (rarity-scaled), PAS
        l'avg(minDmg,maxDmg) generique (@lvl65 mult100 : minDmg 582 vs avg 727 -> generique sur-pred +145/coup).
      - HITS = `GetNumberConstant(0x2f=nrOfHits)` + (`HasTrait(target, 0x3f9=BigTarget)` ?
        `GetNumberConstant(0x2b=extraHit)` : 0) = 2 vs cible normale, 4 vs BigTarget. Litteral (PAS +ExtraHits
        stat). Trait lu sur la CIBLE (`param_4`). Concorde avec le COMBAT `HellfireShellsAbility.Execute-
        Behaviour @1811e8030` (meme `If(HasTrait(target,BigTarget), base+bonus, base)`).
      - PROFIL = param_8 null -> `None` (pierce 0, armure PLEINE), MEME quirk que CrushingClaws #164.
    NON mesurable live (carrier NPC campagne + summon Environment, non-spawnable via rl_duel build) -> verdict
    decompile-proof (standard #169 HarbingerOfDestruction). Cf. docs/rl/case-173-hellfire-shells-base-hits.md."""
    lvl, mult = ab.level, ab.multiplier
    base = cfg.get_variable_for_level("minDmg", lvl, 0, mult)     # var 0xc = minDmg (Direct), rarity-scaled
    hits = int((cfg.constants or {}).get("nrOfHits") or 0)        # const 0x2f = nrOfHits
    tgt_traits = (GC.unit(scene.vis_by_id.get(target_id)) or {}).get("traits") or ()
    if "BigTarget" in tgt_traits:                                # HasTrait(target, 0x3f9=BigTarget)
        hits += int((cfg.constants or {}).get("extraHit") or 0)   # const 0x2b = extraHit (+2)
    return {"base_override": base, "hits_override": hits, "profile_override": "None"}


def _great_frost_axe_inputs(scene, caster_id, target_id, ab, cfg) -> dict:  # target_id ignoré (contrat registre)
    """`GreatFrostAxePlaybook.MakeDamagePredictions @18113fbd0` (ability 1089) — BASE =
    `Get(GetVariableForLevel(0xc=minDmg, state))` = **minDmg SEUL** (rarity-scaled), PAS l'avg
    (minDmg+maxDmg)/2 générique. hits = GetNumberConstant(0x2f=nrOfHits=4) et profil =
    GetDamageProfile config (Piercing 80) = identiques au chemin générique -> pas d'override.
    Mesuré 54321 s18 (u85 ab1089 -> t93) : off avg-based [4020,6032] vs nat minDmg-based
    [3576,5364] — centres per-hit 1256.4 vs 1117.5, ratio = (1+1.25)/2 = le maxDmg/minDmg
    config exact. Même mold que HellfireShells #173 (Direct minDmg). #57e."""
    lvl, mult = ab.level, ab.multiplier
    base = cfg.get_variable_for_level("minDmg", lvl, 0, mult)     # var 0xc = minDmg (Get), rarity-scaled
    return {"base_override": base}


# {ability_id: handler(scene, caster_id, target_id, ab, cfg) -> {base/hits/profile_override}}. Mirror du dispatch
# playbook natif (par type d'ability). HammerOfWrath (1153) a son propre chemin (make_hammer_wrath_events,
# NonComparable) ; ici = les playbooks Comparable qui surchargent juste les INPUTS de GenerateMultiHit.
_MAKE_DMG_INPUT_OVERRIDES = {1191: _martial_inspiration_inputs, 1105: _crushing_claws_inputs,
                             1080: _hellfire_shells_inputs, 1089: _great_frost_axe_inputs}


# Override de PROFIL DE PREDICTION par-ability (audit #165) — mirror du `param_8`
# (`Nullable<DamageProfile>`) que le `<Ability>Playbook.MakeDamagePredictions` bespoke passe a
# `GenerateMultiHitAttackPredictions @181409da0`. Le port derive par defaut le profil de
# `ab.get_damage_profile()` (damageProfile config, sinon arme ranged-first) ; ces playbooks passent
# EXPLICITEMENT un autre profil (ou `null` = profil `None`, enum -1 -> pierce 0, armure PLEINE). Sans
# override, le port applique le PiercingRatio du profil derive -> sur/sous-prediction vs le natif.
# {ability_id: nom de profil passe par le playbook natif}. "None" = param_8 null (pierce 0). VA = playbook.
# CrushingClaws (1105) reste dans _crushing_claws_inputs (case-164, bit-exact live). Les autres candidats de
# l'audit #165 (param_8=null confirme par decompile) NE sont retenus QUE s'ils sont VALIDES LIVE OK sur cible
# blindee (ultraTitus armure 2312) : le seul override pierce ne corrige que les abilities dont le pierce est le
# SEUL gap. La confrontation live a montre que la majorite des candidats null ont un gap PLUS PROFOND (hits/base)
# que l'override ne touche pas -> NON retenus (taches dediees). Cf. docs/rl/case-165-playbook-param8-profile.md.
_PLAYBOOK_PROFILE_OVERRIDE = {
    1020: "None",     # HeraldOfTheApocalypse @181144390 (blackHaarken ; null ; Piercing 80) — VALIDE LIVE OK
    1062: "None",     # SanctorumMissile @1811582c0 (adeptMorvenn ; null, main+bonus ; Blast 15) — VALIDE LIVE OK
    1017: "None",     # FragBomb @18113c9a0 (astraBullgryn ; null ; Blast 15) — hits config 6 OK, pierce SEUL gap. VALIDE LIVE [6,6] [#168]
    1006: "None",     # MultiThreatEliminator @18114d530 (necroDestroyer ; null ; Gauss 60) — + hits static 6 (subclass). VALIDE LIVE [6,6] [#167]
    1066: "Psychic",  # Executioner GeneratePredictions @181130150 (eldarFarseer ; Nullable(0xd=13=Psychic, pierce 100)) — hits=RoundsStarted (subclass) [#166]
    1008: "None",     # HarbingerOfDestruction @1811423f0 (necroPlasmancer ; null@1811425bc ; ability DirectDamage pierce 100) [#169]
    #   RE PROUVE pierce-SEUL gap : base=ArcScourge.GetDamage=avg@18114252c OK, hits=ArmoriumCherub.GetHits config@18114255e OK.
    #   NON confronte live (necroPlasmancer = UNSPAWNABLE_FALLBACK ; autres carriers = NPC necroBoss*). Retenu sur preuve
    #   decompile (structure IDENTIQUE aux 1020/1062 valides live) — le deep-read RE a explicitement exclu tout gap base/hits.
    # --- audit #165 param_8=null : les 5 AUTRES candidats NE sont PAS des overrides pierce (confronte #169) :
    #   1027 PsychicMaelstrom @181153b50 : param_8 = Nullable(BasiliskBarrage.GetDamageProfile) EXPLICITE (PAS null ; l'audit
    #     d'arite confondait param_8=profil et param_9=poids Fix64). Live OK bit-exact [2792,4188] (astraPrimarisPsy). AUCUN override.
    #   1100 SorcerousFacade @18115bb90 : base=Half(Sum(var0xc,var0xd)) DSL != avg -> gap BASE (tache dediee).
    1148: "None",     # DaemonicOrdnance @181128bc0 (blackForgefiend MoW) ; param_8=null -> pierce 0/armure pleine [#172]
    1147: "None",     # HadesAutocannons @181140a60 (blackForgefiend MoW) ; param_8=null -> pierce 0/armure pleine [#172]
    #   ^1148/1147 : RE #172 REFUTE l'ancienne hypothese "gap BASE". base = DaemonicOrdnance.GetDamage @1811cfbb0 /
    #   LightOfSanguinius.GetDamage @1811b2010 = AActiveAbility.MinMaxDamage(avgFlag) @180fb2dc0 = Half(Sum(minDmg 0xc,maxDmg 0xd))
    #   = avg GENERIQUE (== ab.get_damage) ; hits = ArmoriumCherub.GetHits @180fb16c0 = nrOfHits GENERIQUE. Seul gap = param_8=null.
    #   param_8 (GenerateMultiHit sig @181409da0) = profil passe a PredictAttack slot 0x27 ; 1147/1148 ont 0 en param_8 ET param_10
    #   (poids Fix64) -> l'arite qui confondait 1027 (param_8 vs param_10) est ici tranchee. Decompile-proof (base/hits exclus,
    #   meme standard que 1008) ; carrier MoW -> confront live via aiPlaybookPredict (harnais #172) = gate ideal residuel.
    #   1080 HellfireShells @181143a00 : base=Direct(0xc=minDmg SEUL) + hits=nrOfHits(+extraHit si cible BigTarget)
    #     + param_8=null -> PORTE #173 via _hellfire_shells_inputs (base+hits+profile ensemble). Cf. case-173.
}


def make_damage_predictions(scene, caster_id, main_tgt_id, ability_id, ability_name, attack_pos=None):
    """`<Ability>Playbook.MakeDamagePredictions` : LISTE de `ProbableDamageEvent` = cible PRINCIPALE + AoE
    (`GetSurroundingUnits`/`GetOtherTargets`) + event SELF négatif (coût PV). `[]` si non-attaque."""
    if not makes_damage_predictions(ability_name):
        return []
    # #99 REFRAMING (case-99) : les specials ne sont PAS Attack-based. L'hypothèse historique
    # « SpiritLeech hérite ALoki_NormalAttackAbility.PredictAttack (slot vtable 0x27) » est RÉFUTÉE — les
    # 5 specials audités résolvent `PredictAttack` vers le STUB ABSTRAIT `AActiveAbility.PredictAttack
    # @180fb2f20` (qui THROW). Le vrai chemin = `<Special>Playbook.MakeDamagePredictions` ->
    # `GenerateMultiHitAttackPredictions(base = ability.GetAttackDamage() = CONFIG minmax)`. Donc
    # `_PREDICT_VIA_NORMAL_ATTACK` est VIDE (via_normal toujours False) ; la branche est conservée morte
    # au cas où un special s'avérerait un jour réellement Attack-based.
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
    overrides = _ovr_fn(scene, caster_id, main_tgt_id, ab, cfg) if (_ovr_fn and ab is not None and cfg is not None) else {}
    # Profil de prediction par-ability (audit #165) : le playbook natif passe un param_8 explicite (ou null).
    _prof_ovr = _PLAYBOOK_PROFILE_OVERRIDE.get(ability_id)
    if _prof_ovr is not None and "profile_override" not in overrides:
        overrides = {**overrides, "profile_override": _prof_ovr}

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
      - SECONDARY (chaque ennemi VIVANT adjacent à la cible, `GetAdjacentTargets @1811e6150` =
        `Enemies(AdjacentUnits(TARGET, r=1))` où `AdjacentUnits @180de8320` = `Units(AdjacentTiles(target))
        − target` : unités lues par OCCUPATION DE TUILE → un mort n'est plus sur le board (notre
        pos_by_id garde les cadavres, d'où le filtre hp>0 explicite — #57m, corpse u95 +120 à 54321 s8),
        plafond `SelectUniqueUnits(3)`) : base=`minDmg_2` (var 54,
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
        # `AdjacentUnits @180de8320` = Units(AdjacentTiles(target)) − target : occupation de TUILE
        # → vivants seulement (pos_by_id garde les cadavres ; idiome hp>0 = IsAlive, cf. l.227/276).
        adj = [u for u in scene.pos_by_id
               if u != target_id and scene.team(u) != caster_team
               and (scene.hp(u) or 0) > 0
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
