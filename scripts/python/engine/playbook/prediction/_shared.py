"""Socle PARTAGE de la prediction de degat : bloc d'imports (vocabulaire commun aux 3 modules du package),
constantes de module (`RANGED_IN_MELEE_PCT`, `_PROFILE_INDEX`) et les 6 helpers d'ASSEMBLAGE des modifiers
(positionnels + defenseur + auras) consommes par `normal_attack` ET `abilities` (et importes directement par
`playbook/fury_of_the_ancients.py`, `playbook/psyker.py`, les probes).

`normal_attack.py` et `abilities.py` font `from ._shared import *` (recupere tout le vocabulaire non-underscore)
+ un import explicite des helpers/constantes underscore dont ils ont besoin. cf. `__init__.py`."""
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
# Feuilles positionnelles de IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction (PAS des effets) :
# ELEVATION : le builder PREDICTION IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction l'INCLUT, INLINEE (read-L1161-1192 : gate !HasEffect(0x423)
# attaquant ET cible + GetMainTile(cible) + `target.elev < attackTile.elev` -> +config.ElevationBonus) —
# AUCUN appel a la feuille IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier (inlining), d'ou le faux verdict xref #67 « pas d'elevation en
# prediction » (REFUTE #98 : aiPredict u80 (6,6) elev2>1 = x2.25 = CrushingStrike(1.5) x Elevation(1.5) ;
# tuile candidate (5,7) elev egale = x1.0 EXACT -> evaluee a la TUILE CANDIDATE). Cf.
# `_add_positional_and_defender_mods`. RangedInMelee/defenseur aussi dans le preview (10/11).
# RANGED_IN_MELEE_PCT : config native = pourcentage NEGATIF (ReductionPercentage=-50) ; le port passe la
# MAGNITUDE a calculate_ranged_in_melee_reduction (kind PercentDecrease -> add_modifier flippe le signe ->
# x0.5 ; IdunBattle.Core.Services.DamageCalculations$$GetMultiplierFromDamageBonus value<1 -> 1-|value|/100, decompile confirme). RangedInMelee
# = PREDICTION-only (trait 0xb jamais assigne, #161). TRENCH_PCT / _TRENCH_IGNORED_PROFILES deplaces en
# services.damage_modifiers (source unique partagee PREDICTION+COMBAT, #181).
RANGED_IN_MELEE_PCT: int = abs(int(_DMG_CFG.get("RangedInMeleeReductionPercentage", -50)))  # IdunBattle.Core.Services.DamageCalculations$$CalculateRangedInMeleeReduction
_PROFILE_INDEX = {name: idx for idx, name in _PROFILE_BY_INDEX.items()}


def _weapon_pierce(scene, att_id, is_adjacent, dist=None):
    """Arme + percage de l'attaque normale — DELEGUE au service PARTAGE `battle_query.select_weapon_pierce`
    (MEME port que le combat/runner ; `is_adjacent` = adjacence HEX native, `dist` = distance HEX pour la
    porte de portee ranged #188, cf. `make_normal_attack_predictions`). Renvoie
    `(pierce, is_ranged, weapon_hits, profile_name)`."""
    return select_weapon_pierce(scene.ctx(att_id), is_adjacent, dist)


def _should_apply_ranged_in_melee(scene, att_id, attack_pos) -> bool:
    """`IdunBattle.Core.Services.DamageCalculations$$ShouldApplyRangedInMelee` : le natif gate la reduction RangedInMelee sur
    `HasTrait(ATTAQUANT, UnitTrait.Ranged=0xb=11)` (param_4=0 dans le chemin prediction
    `IdunBattle.Core.Services.DamageCalculations$$CalculateRangedInMeleeReduction`) — PAS sur le `is_ranged` de l'ability. Or ce trait
    n'est porte par AUCUNE unite : absent de gameconfig (0 unite) ET de la BC `Units[].Traits` — c'est un
    trait RUNTIME jamais assigne en pratique (`IdunBattle.Entities.UnitExtensions$$IsRanged` = HasTrait(0xb) OR HasRangedWeapon se
    reduit donc a HasRangedWeapon, la branche trait etant morte). CONSEQUENCE : le natif N'APPLIQUE JAMAIS
    RangedInMelee en prediction. On mirror le gate EXACT (HasTrait), donc sans le trait Ranged -> False.
    L'ancien gate `is_ranged` de l'appelant SUR-appliquait la ×0.5 aux casters HYBRIDES tirant une ability
    ranged en melee (#161 : Neurothrope/SpiritLeech = ×2 faux). Si un jour une unite porte le trait Ranged,
    la suite (ennemi melee-able adjacent) s'active fidelement.

    Suite (native, quand HasTrait) : depuis `attack_pos`, existe-t-il un ENNEMI melee-able ADJACENT ?
    (any-enemy, boucle sur les tuiles adjacentes) — ennemi (team != attaquant) + vivant +
    `CanMeleeAttackOverElevationDifference` (|Delta elev|<2). Adjacence HEX via `are_tiles_adjacent`."""
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
    """Ajoute au `mods` les feuilles NON-effet du builder natif `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction (positionnelles, geometrie) + les modifiers DEFENSEUR. Le pipeline natif
    `CalculateDamagePredictionScenario` les applique a TOUT degat (normal ET special) APRES percage/armure.
      • ElevationBonus (`IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier`, surplomb +50%).
      • RangedInMelee (`IdunBattle.Core.Services.DamageCalculations$$CalculateRangedInMeleeReduction`, ranged adjacent a un ennemi → ×0.5).
      • Trench (`IdunBattle.Core.Services.DamageCalculations$$CalculateTrenchReduction`, −50%) : reduction PAR DEFAUT si la cible porte l'effet
        Trench, SUPPRIMEE quand l'attaquant est lui-meme sur une tuile Trench ET voisin hex de la cible
        (#177 : polarite tranchee + 3 mesures live ; `board.terrain_at`=#124, residus CASE3/IndirectFire #182).
      • DEFENSEUR (`CalculateDefenderModifiersForPrediction` : effets de la CIBLE reduisant le degat recu)."""
    # ELEVATION (#98 — RENVERSE le verdict #67 « pas d'elevation en prediction ») : le builder PREDICTION
    # IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction (qui FIRE bien 33x par tour de decision, mesure modifier-observe) l'applique INLINEE
    # (read-L1161-1192, aucun appel a IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier -> le xref-check #67 ne pouvait pas la voir) :
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
    # Trench (IdunBattle.Core.Services.DamageCalculations$$CalculateTrenchReduction) : gate COMPLET dans la fonction nommee (main gate +
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
    # attacker_ctx : identite + niveau/mult du Neurothrope SOURCE (gate + magnitude Neuroparasite). L'attaquant
    # ETANT le source (AreEqual), extraDmg s'indexe sur SON ablvl x SON multiplier.
    # `is_normal_attack` propage au gate `IsNormalAttack` des malus defenseur (ex. MartialKatah -20% #105 :
    # reduit UNIQUEMENT les attaques normales, no-op sur les speciales config-based).
    # #61bis tranche 3 : FACTION de l'attaquant threadee pour les malus defenseur gates par faction —
    # Markerlight (1122) : `OwnerIsTarget & HasFaction(actor, 9=T'au) & IsRangedAttack ->
    # ForPercentIncrease(MarkerlightDmgBonusPct=15)` (`IdunBattle.Entities.Effects.Loki.MarkerlightEffect$$CreateDamageModifier`). MEME source
    # que le combat (`damage_model.defender_modifiers` : `_faction(visual_id)` gameconfig).
    from engine.ai.action_generators import _faction as _fac
    att_ctx = {"id": att_id, "ability_level": scene.ablvl_by_id.get(att_id), "multiplier": scene.mult(att_id),
               "is_normal_attack": is_normal_attack,
               "faction": _fac(scene.vis_by_id.get(att_id))}
    # STAT-MODS DEFENSE de la CIBLE (#194/#197) : moitie DEFENSE de `CalculateDefenderModifiersForPrediction
    # IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` (DefenseComponent stat 3 IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction+0x436 → `IdunBattle.Core.Services.DamageCalculations$$CalculateModifiersFromStatModifications`
    # negate=1 → `1±v/100`). Ex. tuile Thorns −50 → +50 → ×1.5 (GROUND TRUTH C2_19). PORTEE DANS la fonction
    # partagee (plus de fold separe ici) → l'entree sort via `def_mods.pct_list` et est recopiee ci-dessous,
    # EXACTEMENT comme avant (composition %-list commutative sans arrondi intermediaire, #98) : #194 bit-exact
    # preserve, et le COMBAT/runner l'obtient par la MEME fonction (fin du fork #197). `scene.defense_stat` =
    # capture combatSnapshot refreshee par-pas (None/no-mod → inerte).
    def_mods = build_defender_modifiers_from_effects(tgt_effects, is_melee, damage_profile,
                                                     attacker_ctx=att_ctx,
                                                     defense_stat=scene.defense_stat(tgt_id))
    for mult, cap in def_mods.pct_list:
        mods.pct_list.append((mult, cap))
    # ADDITIF defenseur (ForAddition, ex. Neuroparasite +extraDmg x niveau) — le %-list SEUL etait fusionne,
    # l'additif defenseur etait DROPPE. PLACEMENT = MEME slot @+0x10 que l'additif ATTAQUANT #75 : ajoute a la
    # base PRE-percage, puis traverse percage et est scale ×%-list UNE fois (le natif ajoute l'additif @+0x10
    # a la base int AVANT `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`, qui NE re-consomme PAS @+0x10 —
    # cf. `attacker_additive_pre=True` dans `predict_attack_raw`/`calculate_damage_prediction_scenario`). Donc
    # on AJOUTE l'additif BRUT (SANS pre-scale) : le chemin attacker_additive_pre applique deja le %-list ×M.
    # #121 (CONFIRME LIVE 2026-07-12, Neurothrope u82 -> custoTrajann level 1, A=1696 M=1.064) : ORACLE
    # contribution = 1804 = A*M (natif single-scale) ; le pre-scale ×M produisait A*M^2 = 1920 (port sur-pred
    # +116) -> RETIRE. Reproduit les 2 separateurs #88 (RangedSpecialist ON M=1.33 -> A*M=2256 ; OFF M=1 ->
    # 1696) : l'ancien pre-scale ×M compensait le PLACEMENT POST-%-list de `apply_all_modifiers` (additif apres
    # %-list, non scale) ; #70/#111 a bascule la prediction sur attacker_additive_pre (additif pre-percage,
    # %-list re-applique) -> le pre-scale devint un DOUBLE-comptage. != flat_reductions (Nightshroud ci-dessous,
    # #120) qui n'est PAS pre-scale non plus. Combat : def additive=0 (parasite non materialise) -> inerte.
    if def_mods.additive:
        mods.additive += def_mods.additive
    # Reductions DYNAMIQUES CAPEES defenseur (GuardianOrganism -min(pct%×dmg, cap)) — appliquees post-mods
    # dans apply_all_modifiers (CurrentDamage). Le %-list SEUL etait fusionne (comme l'additif, cf. #86a).
    if def_mods.capped_reductions:
        mods.capped_reductions.extend(def_mods.capped_reductions)
    # Reductions PLATES CONSTANTES defenseur (Nightshroud_DmgReduction ForSubtraction = ConfigVar(0x12)=
    # dmgReduction×mult, ex. 499 @{lvl50,mult180}) — additif DEFENSEUR sur le slot @+0x10 : soustrait de la
    # BASE **PRE-percage** (comme l'additif attaquant #75), donc DILUE par percage/armure PUIS scale ×%-list
    # UNE fois (mirror CBDWAM IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers : le natif ajoute l'additif @+0x10 a la base int AVANT Calculate
    # BaseDamageWithAllModifiers, CBDWAM ne le re-consomme pas). CONFIRME LIVE : le config 499 dilue par le
    # facteur percage/armure (~0.31 vs custoTrajann) -> ~155/coup de degat sante = oracle [1620,2744] (le
    # residu apparent "155" N'EST PAS la valeur config mais 499 traversant l'armure). PAS de pre-scale ×M
    # (!= l'additif Neuroparasite ci-dessus qui compense le placement post-%-list du COMBAT) : le chemin
    # attacker_additive_pre scale deja ×%-list une fois.
    if def_mods.flat_reductions:
        mods.additive -= sum(def_mods.flat_reductions)
    # (moitie DEFENSE stat-mods #194/#197 : DESORMAIS foldee DANS build_defender_modifiers_from_effects
    # ci-dessus → transite via def_mods.pct_list, plus de fold separe ici — fin du fork prediction/combat.)
    # AURAS-DEFENSE state-wide (#184) : effets EffectWithTarget possedes par d'AUTRES unites dont le
    # TargetSelector projette sur la CIBLE du coup — boucle « TOUS les EffectWithTarget actifs × leurs
    # cibles » de `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` (cf. case-68), qui ne se reduit PAS
    # aux effets portes par la cible. Ex. DaughterOfTheAbyss (Atlacoya) : -dmgReductionPct% (33 @L50)
    # Psychic aux AMIS rayon 2 (racine du ~1.49x bloodMephiston seed 2024 : 1003×1.25×3×0.67 = 2016,3024
    # natif vs 3006,4515 port) ; +extraDmgPct% aux Psykers ENNEMIS rayon 2. Cibles/positions REELLES
    # (la cible ne bouge pas pendant la prediction) ; porteurs vivants uniquement.
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
    ToDamage IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage`). Derivables offline : **Resilient** (trait gameconfig + hp/hpmax → cape le
    degat a `HP-1`) et **member-cap Swarm** (#57d : `nrOfMembers` gameconfig de la cible + hpmax =
    repartition native `IdunBattle.Core.Services.DamageCalculations$$GetGroupUnitMemberHealth` ; skip si le profil de L'ATTAQUE a
    `DamageTrait.HitsMultipleMembers` (2) = Blast — d'ou `damage_profile` threade par l'appelant).
    Valide bit-exact 1357 s16 (u139 5 hits 1197/1795 vs necroSmnSwarm 5×444 : caps 442,444,444,444
    puis dernier membre NON cappe → [2971,3569] == natif). Les autres sous-limites restent des **NO-OP
    documentes** (defaults conservateurs) faute d'input offline : Impervious (charge runtime non captee
    par combatSnapshot), boss-cap (`HasTriggeredAbility(0x5d4)` non verifie offline)."""
    gu = GC.unit(scene.vis_by_id.get(tgt_id)) or {}
    utraits = set(gu.get("traits") or [])
    hpmax = scene.hpmax(tgt_id) or 0
    _dp_traits = (GC.damage_profile(damage_profile) or {}).get("Traits") or [] if damage_profile else []
    return {
        "target_has_resilient": "Resilient" in utraits,
        "target_has_impervious": "Impervious" in utraits,
        "impervious_stat_current": None,             # charge Impervious non captee offline -> no-op (TODO)
        "member_count": int(gu.get("nrOfMembers") or 1),   # GroupUnitComponent (IdunBattle.Core.Services.DamagePrediction$$ApplyGroupUnitDamageLimit lit le composant)
        "member_total_hp": hpmax,
        "profile_has_hits_multiple_members": DamageTrait.HitsMultipleMembers.name in _dp_traits,
        "max_health": hpmax,
        "target_has_boss_cap": False,                # HasTriggeredAbility(0x5d4) non verifie offline -> no-op (TODO)
        "boss_cap_const": 0,
    }


def _apply_ally_attack_dmg_bonus(mods, scene, att_id, att_pos, is_melee, tgt_armor_reduced, carriers=None,
                                 tgt_id=None, is_normal_attack=None, damage_profile=None):
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
           # UnitsWithRangedAttacks (selector SpotterReworked IdunBattle.Entities.Effects.Loki.SpotterReworked_ExtraDamageEffect$$CreateTargetSelector) = UNION {arme ranged au kit}
           # + {diff elevation <= 2 vs tuile porteur} (IdunBattleLogic.Entities.DSLFactory$$UnitsWithRangedAttacks) -> board pour le terme elevation
           "att_has_ranged_weapon": any(w.get("Range") for w in (att_gu.get("weapons") or ())),
           "board": scene.board,
           "is_melee": is_melee, "target_armor_reduced": tgt_armor_reduced,
           "is_normal_attack": is_normal_attack,
           # DefenderOfTheGreaterGood_ExtraDmg (#220, aura Tau) : gate !DamageProfileIs(Psychic) IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraDmgEffect$$CreateDamageModifier.
           "damage_profile": damage_profile,
           "tgt_id": tgt_id,
           "t_pos": scene.pos(tgt_id) if tgt_id is not None else None,
           "tgt_team": scene.team(tgt_id) if tgt_id is not None else None}
    for eb in aura_attack_damage_bonus_from_allies(carriers, ctx):
        add_modifier(mods, eb)


def defender_prediction_block_amount(scene, tgt_id, damage_profile: str | None = None) -> int:
    """Amount de BLOCK du defenseur pour le scenario `list[0]@0x50` de la prediction (#54A) —
    mirror des entrees `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances` consommees par le scenario block
    (`IdunBattle.Core.Services.DamagePrediction$$CalculateDamagePredictionScenario`) : scalaire GetStat(7/8)
    (blockChance/blockDamage) + sources multi-value des EFFETS du defenseur (Daemon_ExtraBlock
    25 %/50 %×Attack courant, BeastSlayer_ExtraBlock…). Approximation documentee : sources
    multiples SOMMEES (un seul cas mesure, mono-source Daemon — 1357 s15). 0 = pas de block
    → liste native vide → WillBeKill/WillBeOverkill retombent sur les scalaires raw.

    #69 : GATE `NoBlocking` (DamageTrait 0) du PROFIL de degat — mirror du gate COMBAT
    `AttackDamageOperation._block_sources` (`runner/operations/damage.py`) ET du skip natif de la
    PREDICTION : `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` fait `DamageProfile.HasTrait(profile,
    0=NoBlocking)` (IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x2bec) et SKIP toute la boucle de construction du scenario block
    (`param_1[10]`, list[0]@0x50) quand le flag est pose (`if (blockList != 0 && (char)HasTrait == 0)
    {...}`). Un profil `Psychic` (Traits=['NoBlocking'], PiercingRatio 100 ; wiki « Cannot be
    blocked ») bypasse donc le block en PREDICTION comme en COMBAT -> amount 0 -> `_with_block` no-op
    -> block_raw_min reste None -> WillBeKill/WillBeOverkill retombent sur le scalaire raw (== natif :
    liste block vide). Sans ce gate, la prediction sur-comptait le block d'une attaque Psychic
    (kill-prediction IA faussee ; residu documente case-65-noblocking-block-bypass §« Non couvert »)."""
    if damage_profile is not None:
        if DamageTrait.NoBlocking.name in ((GC.damage_profile(damage_profile) or {}).get("Traits") or []):
            return 0        # profil NoBlocking -> block bypasse (mirror IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x2bec + _block_sources)
    amt = 0
    tctx = scene.ctx(tgt_id)
    if tctx is not None and int(tctx.block_chance or 0) > 0:
        amt += int(tctx.block_damage or 0)
    from engine.entities.effects import defender_effect_block_sources
    for bs in defender_effect_block_sources(scene.effects(tgt_id), scene.armor(tgt_id),
                                            defender_attack=scene.attack_current(tgt_id)):
        amt += int(bs.amount or 0)
    return amt
