"""`engine.entities.effects` — port des effets de combat `IdunBattle.Entities.Effects.*` en hiérarchie
de classes (BaseEffect + sous-classes 1:1 + factory + registre), remplaçant l'ancien registre de données
(`effects_damage_bonus.EffectDef`). Mirror fidèle du modèle natif « 1 classe par effet ».

Ce module héberge AUSSI la tranche « builders qui ITERENT LES EFFETS » de `IdunBattle.Core.Services.
DamageCalculations` (convention repo : DamageCalculations eclatee par concern — cf. en-tete de
`services/damage_modifiers.py`) : `build_attacker_modifiers_from_effects` = `CalculateAttackerModifiers
ForPrediction @181000590` (boucle effets), `build_defender_modifiers_from_effects` = `CalculateDefender
ModifiersForPrediction @181002c30`, + les axes COUPS (`hits_bonus_from_effects` / `_defender_` / auras).
Ils sont ICI (et pas dans damage_modifiers.py) parce que leur corps EST la boucle sur les effets.

API :
  • `BaseEffect` / sous-classes (loki.py …) — 1 classe par effet, override des méthodes implémentées.
  • `EffectFactory` / `EFFECT_CLASSES` — instancie la bonne classe depuis un effet capté.
  • `build_attacker_modifiers_from_effects(effects)` → `DamageModifiers` (builder
    `CalculateAttackerModifiersForPrediction` : itère les effets ACTIFS, agrège damage-bonus + pénétration).
  • `hits_bonus_from_effects(effects)` → int (axe COUPS, `CreateEffectHitsBonusForAttack`).
`effects` accepte des instances `BaseEffect` (déjà matérialisées/filtrées par EffectsState) OU des dicts
captés (matérialisés à la volée via la factory).
"""
from __future__ import annotations

from collections.abc import Mapping

from ...services.damage_modifiers import (
    DamageModifiers, add_modifier, build_attacker_modifiers, build_defender_modifiers,
    calculate_modifiers_from_stat_modifications,
)
from ...services.effect_bonus import for_armor_penetration
from .base import BaseEffect, SubEffectSpec, SAME_TURNS
from .factory import EFFECT_CLASSES, EffectFactory
from .loki import (
    CrushingStrikeEffect,
    KanOpenerEffect,
    PowerTripFullHealthEffect,
    PowerTripIgnoreArmorEffect,
    RapidAssaultExtraDamageEffect,
    SquigHoundAdditionalHitsEffect,
    StunnedEffect,
)

__all__ = [
    "BaseEffect", "SubEffectSpec", "SAME_TURNS", "EffectFactory", "EFFECT_CLASSES",
    "CrushingStrikeEffect", "RapidAssaultExtraDamageEffect", "PowerTripFullHealthEffect",
    "PowerTripIgnoreArmorEffect", "KanOpenerEffect", "StunnedEffect", "SquigHoundAdditionalHitsEffect",
    "build_attacker_modifiers_from_effects", "calculate_attacker_modifiers_for_prediction",
    "build_defender_modifiers_from_effects",
    "hits_bonus_from_effects", "hits_malus_from_defender_effects", "aura_hits_malus_for_defense",
    "aura_hits_bonus_for_attack", "additional_hit_groups", "aura_defense_damage_malus_from_units",
    "aura_attack_damage_bonus_from_allies", "aura_fixed_armor_bonus_for_defense",
    "crit_chance_bonus_from_effects", "crit_damage_bonus_from_effects",
    "apply_effect_stat_modifications", "stat_modifications_by_source",
]


def _as_effects(effects) -> list[BaseEffect]:
    """Normalise une liste hétérogène (instances BaseEffect ou dicts captés) → instances BaseEffect."""
    out: list[BaseEffect] = []
    for e in (effects or []):
        if isinstance(e, BaseEffect):
            out.append(e)
        elif isinstance(e, Mapping) and e.get("name"):
            out.append(EffectFactory.create(e))
    return out


def _attacker_effect_bonuses(effects, is_ranged: bool | None, is_normal_attack: bool,
                             has_moved: bool | None, target_traits=None, is_prediction=False,
                             target_armor_reduced: bool | None = None, att_ctx=None) -> list:
    """Boucle EFFETS de l'attaquant (contribution PARTAGÉE prédiction/combat) : pour chaque effet ACTIF,
    `create_effect_damage_bonus_for_attack` (additif/percent) + `get_armor_penetration` (axe armure) →
    liste d'`EffectBonus`. C'est la boucle `param_5` commune aux deux slots natifs (0xd préd / 0xf combat).
    `target_armor_reduced` = gate `HasNegativeModifier(cible armure)` (ConquerorImperative) threadé du site.
    `att_ctx` = contexte POSITIONNEL {att_pos, tile_effects_by_pos} pour les bonus à magnitude
    position-dépendante (LordOfTempests @180f569a0) ; None = inconnu (ces bonus rendent None)."""
    bonuses = []
    for e in _as_effects(effects):
        db = e.create_effect_damage_bonus_for_attack(is_ranged, has_moved, target_traits=target_traits,
                                                     is_prediction=is_prediction,
                                                     is_normal_attack=is_normal_attack,
                                                     target_armor_reduced=target_armor_reduced,
                                                     att_ctx=att_ctx)
        if db is not None:
            bonuses.append(db)
        pen = e.get_armor_penetration(is_normal_attack)
        if pen is not None:
            bonuses.append(for_armor_penetration(True, pen))
    return bonuses


def build_attacker_modifiers_from_effects(effects, is_ranged: bool | None = None,
                                          is_normal_attack: bool = True,
                                          has_moved: bool | None = None,
                                          target_traits=None,
                                          target_armor_reduced: bool | None = None,
                                          att_ctx=None) -> DamageModifiers:
    """DamageModifiers **COMBAT** (chemin runner) depuis les EFFETS ACTIFS de l'attaquant (§17.8) —
    agrège damage-bonus (`create_effect_damage_bonus_for_attack`) + pénétration d'armure. C'est la
    contribution EFFETS SEULE (boucle `param_5`), **SANS le debuff stat-modifications** : le combat
    (`CalculateAbilityDamage`/`HitDamage.GetDamage`) déale la base PLEINE (Current) — cf. xref
    `CalculateModifiersFromStatModifications` prédiction-only. La PRÉDICTION passe par
    `calculate_attacker_modifiers_for_prediction` (= cette boucle + le debuff).
    Effets déjà filtrés actifs (EffectsState.active_effects) ; dicts → aucun filtre is_active.
    `is_ranged` → bonus gated `IsRangedAttack` ; `is_normal_attack` → pénétrations gated normal-only ;
    `has_moved` → bonus gated no-move (HeavyWeapon @180f4f030) ; `target_armor_reduced` → bonus gated
    `HasNegativeModifier(cible armure)` (ConquerorImperative @180f39650)."""
    return build_attacker_modifiers(
        _attacker_effect_bonuses(effects, is_ranged, is_normal_attack, has_moved, target_traits,
                                 target_armor_reduced=target_armor_reduced, att_ctx=att_ctx))


def calculate_attacker_modifiers_for_prediction(
        effects, is_ranged: bool | None = None, is_normal_attack: bool = True,
        has_moved: bool | None = None, attack_stat=None,
        apply_stat_mod_debuff: bool = False, target_traits=None,
        target_armor_reduced: bool | None = None, att_ctx=None) -> DamageModifiers:
    """`CalculateAttackerModifiersForPrediction @181000590` (slot 0xd) — chemin **PRÉDICTION**, DISTINCT
    du combat. = la boucle EFFETS partagée (`_attacker_effect_bonuses`) **PLUS** la conversion
    stat-modifications `CalculateModifiersFromStatModifications` (prédiction-only, xref @181000cac).

    RE #194 (corrige la lecture #49 « debuff Current→Initial ») : la face attaquant native lit
    l'**AttackComponent** de l'attaquant (cctor @180f95c80) avec negate=**0** et convertit chaque
    modification en entrée **POURCENT** de la %-list (`1+v/100`, cf. @181004380/@181005210) — PAS un
    flat-subtract. Son gate d'activation (entité contexte@0x08 nullable + interface slot 3
    `DAT_1831b7f78`) n'est PAS élucidé, et il est prouvé INERTE sur le chemin normal-attack (#49 :
    aura Calgar +1298 Attack présente, prédiction bit-exacte SANS cette contribution — +1298% aurait
    explosé). → RESTE GATÉ par `apply_stat_mod_debuff` (défaut False, aucun call-site ne l'active) ;
    le câbler exigerait d'abord la RE du gate (tâche dédiée). La face DÉFENSEUR (DefenseComponent,
    negate=1) est, elle, PORTÉE et validée (#194, prediction.py)."""
    # #71 : chemin PREDICTION -> is_prediction=True. Le noeud DSL IsNormalAttack (trigger SmashaEad
    # @180f6bee0) evalue FALSE ici (verdict re-expert) -> SmashaEad n'entre pas dans la DamageModifiers de
    # prediction (matche le DISPLAY decisionView). Le COMBAT (build_attacker_modifiers_from_effects) garde
    # is_prediction=False (defaut) -> SmashaEad applique. RapidAssault (OwnerIsCaster seul) non affecte.
    bonuses = _attacker_effect_bonuses(effects, is_ranged, is_normal_attack, has_moved, target_traits,
                                       is_prediction=True, target_armor_reduced=target_armor_reduced,
                                       att_ctx=att_ctx)
    if apply_stat_mod_debuff and attack_stat is not None:
        # negate=False : mirror de l'appel natif @181000cac (3e arg = 0, face attaquant NON négée).
        bonuses += calculate_modifiers_from_stat_modifications(attack_stat, negate=False)
    return build_attacker_modifiers(bonuses)


def build_defender_modifiers_from_effects(effects, is_melee: bool | None = None,
                                          damage_profile: str | None = None,
                                          attacker_ctx: Mapping | None = None,
                                          defense_stat=None) -> DamageModifiers:
    """`CalculateDefenderModifiersForPrediction` @181002c30 — DamageModifiers de la CIBLE (MODIFICATION du
    dégât reçu). Mirror COMPLET des DEUX moitiés du natif dans le MÊME accumulateur, dans l'ordre natif :
      1. **fold du stat-mod DEFENSE** (`defense_stat`, la 1re moitié @181003037→@181004380, negate=1) ;
      2. **boucle des effets** défenseur (`create_effect_damage_malus_for_defense`, slot 0x1a/0x1b/0x19).
    Symétrique de `build_attacker_modifiers_from_effects`. Effets déjà filtrés actifs (EffectsState.active_effects).

    ⚠ NE PAS forker la moitié DEFENSE hors d'ici : elle vivait dans le seul caller prédiction (#194) → le
    COMBAT/runner la ratait (#197, gap = ce fork). Les DEUX callers (prediction.py `_add_positional_and_
    defender_mods`, runner `damage_model.defender_modifiers`) passent DÉSORMAIS `defense_stat` → l'axe est
    partagé PAR CONSTRUCTION (comme le natif). La SOURCE de `defense_stat` diffère par nécessité (prédiction :
    `scene.defense_stat`, refresh par-pas car ctx COLD ; runner : `ctx.stats` DEFENSE de l'ECS live) — ce n'est
    PAS un fork du code (le fold est ICI), juste deux entrées vers la même DefenseComponent que le natif relit.

    `is_melee` = nature du coup (propagée aux malus gated `IsMeleeAttack`, ex. Terrifying_ExtraDefense) ;
    `damage_profile` = NOM du profil de dégât de l'attaque (propagé aux malus gated `DamageProfileIs`, ex.
    TerminatorArmour -75% SAUF Psychic/DirectDamage) ; `attacker_ctx` = `{id, ability_level, multiplier}` de
    l'ATTAQUANT (propagé aux malus gated sur l'identité de l'attaquant, ex. Neuroparasite : `AreEqual(
    BondedEntity, damageSource)` + magnitude indexée sur le niveau/mult du Neurothrope SOURCE) ;
    `defense_stat` = `StatComponent` DEFENSE (stat 3) de la CIBLE (ses modifications, ex. tuile Thorns −50 →
    +50 → ×1.5) ; None/no-mod → moitié DEFENSE no-op (rétro-compat).
    ⚠ Couvre la famille `ADamageDefenseModifierAbilityEffect` (EffectBonus PercentDecrease ConfigVar gated) +
    Terrifying_ExtraDefense + TerminatorArmour_ReduceDmg (réductions %) + Neuroparasite (ForAddition POSITIF) +
    stat-mods DEFENSE (Thorns/SpiderWeb/DryBush/Shrub) ; les réductions par COUPS (Parry_ReduceHits) ou par
    TRIGGER (predOptimistic) sont des axes SÉPARÉS (cf. docs/rl/runner-engine.md §1.8). Le résultat porte
    `additive` (Neuroparasite) ET `pct_list` (réductions + DEFENSE) — l'appelant DOIT fusionner LES DEUX
    (cf. prediction.py : additif défenseur longtemps oublié)."""
    maluses = []
    for e in _as_effects(effects):
        mb = e.create_effect_damage_malus_for_defense(is_melee, damage_profile, attacker_ctx)
        if mb is not None:
            maluses.append(mb)
    acc = build_defender_modifiers(maluses)
    # Moitié DEFENSE (1re du natif) : chaque modification du DefenseComponent → entrée %-list `1±v/100`
    # via `CalculateModifiersFromStatModifications @181004380` (negate=1). GROUND TRUTH #194/#197 (C2_19,
    # tuile Thorns −50 → ×1.5 en prédiction ET en combat réel, mesuré live). No-op si defense_stat None/no-mod.
    for eb in calculate_modifiers_from_stat_modifications(defense_stat, negate=True):
        add_modifier(acc, eb)
    return acc


def defender_effect_block_sources(effects, defender_fixed_armor: int = 0,
                                  defender_attack: int = 0) -> list:
    """Sources de BLOCK supplementaires posees par les effets de la CIBLE (defenseur) — a AJOUTER a la
    chaine `apply_random_block_damage` APRES le block de base (scalaire `GetStat(7/8)`). Mirror des
    entrees SEPAREES de `GetMultiValueStat(7)` (`CalculateBlockChances @181002350`) posees par
    `AddExtraBlockEffectToOwner` (ex. BeastSlayer @180e18b70 : chance 10% / amount=100% FixedArmor courant),
    ABSENTES du scalaire (verifie live : orksNob blockChance=0). Agrege
    `create_effect_block_source_for_defense(defender_fixed_armor)` (defaut None). Effets deja filtres actifs.
    Retourne [] si aucun effet ne pose de source -> combat exact inchange (no-op). #72."""
    out = []
    for e in _as_effects(effects):
        bs = e.create_effect_block_source_for_defense(defender_fixed_armor,
                                                      defender_attack=defender_attack)
        if bs is not None:
            out.append(bs)
    return out


def hits_bonus_from_effects(effects, is_normal_attack: bool = True,
                            att_ctx: Mapping | None = None) -> int:
    """Σ des bonus de COUPS (`CreateEffectHitsBonusForAttack`) des effets actifs (axe hits, ex.
    PowerTrip_FullHealth). Addition = +value, Subtraction = −value.
    `att_ctx` = le `board` de `AttackHitsWithModifiersFormula` + `tile_effects_by_pos` +
    `persistent_data` (cf. `BaseEffect.create_effect_hits_bonus_for_attack`) — requis par les bonus
    dont le gate porte sur la CIBLE (`LetTheGalaxyBurnEffect` @180f54e30). None → ces bonus no-op."""
    total = 0
    for e in _as_effects(effects):
        hb = e.create_effect_hits_bonus_for_attack(is_normal_attack, att_ctx)
        if hb is None:
            continue
        if hb.kind == "Addition":
            total += hb.value
        elif hb.kind == "Subtraction":
            total -= hb.value
    return total


def additional_hit_groups(effects, ctx: Mapping | None = None) -> list:
    """Concatène les groupes de COUPS ADDITIONNELS HETEROGENES déclarés par les effets ACTIFS de
    l'attaquant (`additional_hit_groups`, ex. SquigHound_AdditionalHits : 2 coups [minDmg,maxDmg]
    profil Physical). Chaque groupe `{count, min, max, profile}` = des coups à dégât/profil PROPRE à
    matérialiser APRES les coups d'arme (prev-threadés). Mirror EffectAdditionalHits.Create @180f405b0.
    Retour [] si aucun effet n'en déclare (no-op strict → prédiction inchangée hors carrier concerné)."""
    out: list = []
    for e in _as_effects(effects):
        g = e.additional_hit_groups(ctx)
        if g:
            out.extend(g)
    return out


def aura_additional_hits_from_allies(carriers, ctx: Mapping) -> list:
    """Groupes de coups additionnels PROJETES sur l'ATTAQUANT par les effets-AURA d'AUTRES unités
    (`create_aura_additional_hits_for_ally`, ex. ExplosiveMaladies : +1 coup Blast aux attaques
    normales des amis adjacents a Pestillian — ranged pour tous, melee pour les Chaos). Le natif
    énumère les effets GLOBALEMENT (`GetAdditionalHitsFromEffectsInternal @180e59150`) et le
    descripteur porte sélecteur + trigger ; en display l'adjacence est ré-évaluée à la TUILE
    CANDIDATE (mesuré 2468 s14 : u89 gagne le coup à (2,3) adjacent de u91, rien à (0,3)).
    `carriers` = même 8-tuple que les autres canaux d'aura ; retour [] strict."""
    out: list = []
    att_id = ctx.get("att_id")
    for uid, pos, team, mult, ablvl, grand, faction, effs in carriers:
        if uid == att_id or pos is None:
            continue
        octx = {**ctx, "owner_id": uid, "owner_pos": pos, "owner_team": team,
                "owner_mult": mult, "owner_ablvl": ablvl,
                "owner_grand_alliance": grand, "owner_faction": faction}
        for e in _as_effects(effs):
            g = e.create_aura_additional_hits_for_ally(octx)
            if g:
                out.append(g)
    return out


def hits_malus_from_defender_effects(effects, is_melee: bool | None = None,
                                     damage_profile: str | None = None,
                                     defender_on_cover: bool | None = None,
                                     dist: int | None = None) -> int:
    """Σ des modifications de COUPS des effets actifs de la CIBLE (`create_effect_hits_malus_for_defense`,
    ex. LightCover @180f556b0 : -2 ranged ; Parry @180f5d860 : -1 mêlée ; MasterAnnihilator
    @180f58d50 : +1 non-Psychic). Natif = même canal `CreateEffectHitsBonusForAttack` trigger
    `OwnerIsTarget` ; plancher min=1 appliqué chez le consommateur (`max(1, …)`).
    `defender_on_cover` = gate compute-time des effets de TUILE (LightCover `AreEqual(coverPatch,target)`,
    #113) : None=applique-sur-présence (prédiction), True/False=cible sur/hors sa tuile de cover (combat).
    Retour signé (à ADDITIONNER aux hits)."""
    total = 0
    for e in _as_effects(effects):
        hb = e.create_effect_hits_malus_for_defense(is_melee, damage_profile, defender_on_cover, dist)
        if hb is None:
            continue
        if hb.kind == "Addition":
            total += hb.value
        elif hb.kind == "Subtraction":
            total -= hb.value
    return total


def aura_hits_malus_for_defense(units_effects, ctx) -> int:
    """Σ des malus de COUPS projetés sur la CIBLE par des effets AURA possédés par d'AUTRES unités
    (`create_aura_hits_malus_for_defense`, ex. BigTargetAdjacentEffect @180f33ac0 : -1 ranged pour
    les alliés ring-1 du porteur). `units_effects` = itérable de (owner_id, owner_pos, owner_team,
    effets du porteur) ; `ctx` = {tgt_id, t_pos, tgt_team, is_melee}. Plancher min=1 chez le
    consommateur. Retour ≤ 0 (à ADDITIONNER aux hits)."""
    total = 0
    for owner_id, owner_pos, owner_team, effects in (units_effects or []):
        octx = {**(ctx or {}), "owner_id": owner_id, "owner_pos": owner_pos,
                "owner_team": owner_team}
        for e in _as_effects(effects):
            hb = e.create_aura_hits_malus_for_defense(octx)
            if hb is None:
                continue
            if hb.kind == "Addition":
                total += hb.value
            elif hb.kind == "Subtraction":
                total -= hb.value
    return total


def aura_hits_bonus_for_attack(units_effects, ctx) -> int:
    """Σ des bonus de COUPS projetés sur l'ATTAQUANT par des effets AURA possédés par ses ALLIÉS à portée
    (`create_aura_hits_bonus_for_attack`, ex. AstartesBannerExtraHitEffect @180f323b0 : +extraHits mêlée aux
    alliés dans le rayon 2 du porteur, exclut self). SYMÉTRIQUE de `aura_hits_malus_for_defense` (défenseur).
    `units_effects` = itérable de (owner_id, owner_pos, owner_team, effets du porteur) ; `ctx` = {att_id,
    att_pos, att_team, is_melee}. Retour >= 0 (à ADDITIONNER aux hits)."""
    total = 0
    for owner_id, owner_pos, owner_team, effects in (units_effects or []):
        octx = {**(ctx or {}), "owner_id": owner_id, "owner_pos": owner_pos, "owner_team": owner_team}
        for e in _as_effects(effects):
            hb = e.create_aura_hits_bonus_for_attack(octx)
            if hb is None:
                continue
            if hb.kind == "Addition":
                total += hb.value
            elif hb.kind == "Subtraction":
                total -= hb.value
    return total


def aura_attack_bonus_from_allies(carriers, ctx) -> int:
    """Σ des bonus PLATS au stat Attack (BASE) projetés sur l'ATTAQUANT par les auras stat-mod possédées
    par ses ALLIÉS à portée (`create_aura_attack_bonus`, ex. `RitesOfBattleAbility` @181225340 :
    +extraDmg/_2 aux alliés ring-1, gate grande-alliance Imperial ; `PathOfCommandAbility` @181110f10 :
    +extraDmg(/_2 si même FACTION) aux alliés dans un rayon 2). `carriers` = itérable de (owner_id, owner_pos,
    owner_team, owner_mult, owner_level, owner_grand_alliance, owner_faction, effets du porteur) ; `ctx` =
    {att_id, att_pos, att_team, att_grand_alliance, att_faction, board, att_real_pos?}. Modélisé CÔTÉ
    SOURCE, évalué à la position passée dans `att_pos`. #153 (REFUTE l'ancien verdict #67 « position réelle
    jamais tuile candidate ») : en PRÉDICTION DISPLAY l'appelant passe la TUILE CANDIDATE (`attack_pos`,
    fallback position réelle) — la chaîne native threade la UnitPosition candidate de bout en bout
    (`GetAllPredictions @181090f50` -> `DamagePrediction.PredictNormalAttack @181037cd0` : CasterTile =
    tuile candidate dans `AbilityEntities.ctor`) et RE-VÉRIFIE l'aura PAR TUILE.

    RAFFINEMENT #41 (2026-07-20) : la re-vérification per-candidate est SPLITTÉE PAR ARME (mesures
    seed-31337, les 2 canaux natifs ranked==aiPlaybookPredict concordants partout) :
    - RANGED = sémantique #153 pure (tuile candidate, GAIN INCLUS) : u95 thousAhriman réel dist-3 du
      porteur, candidate (4,5) in-ring -> natif base 3011+898 ; u92 #153 12 out-ring PERDUES / 2
      in-ring gardées ; u89 s11/s13 base 2101=803+1298 bit-exact ×4 tuiles. L'appelant ne passe PAS
      `att_real_pos` (None) -> gate inactif.
    - MÊLÉE = pas de GAIN depuis une tuile candidate (u93 deathRotbone s13 : candidate (2,3) in-ring
      de Calgar, natif = base Initial 1408 ×1.5 élévation EXACT, zéro flat). L'appelant passe
      `ctx["att_real_pos"]` = position réelle : chaque effet doit fire AUSSI à la position réelle
      (matérialisation du stat-mod) pour contribuer — l'amount est celui du candidat (identique :
      montants niveau-source). Seul cas mêlée+matérialisé mesuré = candidate-out-ring (drop, couvert).
    - Tuile candidate NON-ENTRABLE (BlockEnteringUnits) : aura PERDUE même matérialisée+in-ring (u89
      s11 candidate (1,3) : natif base 803 ×1.5) — guard au call-site prédiction (mirror
      `GetUnitPositionAtTile` dégénérée sur tuile bloquée).
    Retour >= 0 (à AJOUTER à `GetStat(Attack, INITIAL)`). NB gates DIFFÉRENTS : RitesOfBattle =
    grande-alliance (Imperial), PathOfCommand = faction (IsSameFaction)."""
    total = 0
    c0 = ctx or {}
    rp = c0.get("att_real_pos")
    cand = c0.get("att_pos")
    for owner_id, owner_pos, owner_team, owner_mult, owner_level, owner_ga, owner_faction, effects \
            in (carriers or []):
        octx = {**c0, "owner_id": owner_id, "owner_pos": owner_pos, "owner_team": owner_team,
                "owner_mult": owner_mult, "owner_level": owner_level, "owner_grand_alliance": owner_ga,
                "owner_faction": owner_faction}
        for e in _as_effects(effects):
            b = e.create_aura_attack_bonus(octx)
            if not b:
                continue
            # #41 : matérialisation — pas de GAIN d'aura depuis une tuile candidate si l'effet ne
            # fire pas à la position RÉELLE (stat-mod absent du store natif -> rien à re-vérifier).
            if rp is not None and cand is not None and tuple(rp) != tuple(cand) \
                    and not e.create_aura_attack_bonus({**octx, "att_pos": rp}):
                continue
            total += int(b)
    return total


def aura_fixed_armor_bonus_for_defense(carriers, ctx) -> int:
    """Σ des bonus PLATS à la stat **FixedArmor(16)** projetés sur le DÉFENSEUR par les auras stat-mod possédées
    par ses ALLIÉS adjacents (`create_aura_fixed_armor_bonus_for_defense`, ex. `ProtectorImperative` de
    DoctrinaImperatives @180f39890 : +extraArmor aux amis Mechanical ring-1 du porteur). SYMÉTRIQUE défenseur de
    `aura_attack_bonus_from_allies` (attaquant). `carriers` = itérable de (owner_id, owner_pos, owner_team,
    owner_mult, owner_level, effets du porteur) ; `ctx` = {def_id, def_pos, def_team, def_traits}. Le porteur
    (self) est déjà buffé par son stat-mod EAGER (`GetStat`) → l'effet aura s'auto-exclut quand def==owner (pas
    de double-compte). L'adjacence hex (ring-1) + le gate trait Mechanical sont vérifiés dans la méthode d'effet.
    Retour >= 0 (à AJOUTER à `GetStat(FixedArmor)` du défenseur, RÉ-ÉVALUÉ PAR ADJACENCE)."""
    total = 0
    for owner_id, owner_pos, owner_team, owner_mult, owner_level, effects in (carriers or []):
        octx = {**(ctx or {}), "owner_id": owner_id, "owner_pos": owner_pos, "owner_team": owner_team,
                "owner_mult": owner_mult, "owner_level": owner_level}
        for e in _as_effects(effects):
            b = e.create_aura_fixed_armor_bonus_for_defense(octx)
            if b:
                total += int(b)
    return total


def aura_attack_damage_malus_from_enemies(carriers, ctx) -> list:
    """Liste des malus %-DÉGÂT projetés sur l'ATTAQUANT par les auras d'effet possédées par ses ENNEMIS à
    portée (`create_aura_attack_damage_malus_for_enemy`, ex. `ShadowInTheWarp_LessDmg_Effect` : -25% Psychic
    aux ennemis environnants dans la portée du porteur). `carriers` = itérable (owner_id, owner_pos,
    owner_team, effets du porteur) ; `ctx` = {att_id, att_pos, att_team, damage_profile}. Renvoie une liste
    d'`EffectBonus` (chaque porteur à portée empile son malus) à intégrer aux modifiers de l'attaquant via
    `add_modifier`. Chaque `carrier` = tuple dont [0]=owner_id, [1]=owner_pos, [2]=owner_team, [-1]=effets
    (accepte le 4-tuple dédié comme le 6-tuple `carriers` de la prédiction)."""
    out = []
    for c in (carriers or []):
        octx = {**(ctx or {}), "owner_id": c[0], "owner_pos": c[1], "owner_team": c[2]}
        for e in _as_effects(c[-1]):
            eb = e.create_aura_attack_damage_malus_for_enemy(octx)
            if eb is not None:
                out.append(eb)
    return out


def aura_attack_damage_bonus_from_allies(carriers, ctx) -> list:
    """Liste des bonus de DÉGÂT projetés sur l'ATTAQUANT par les auras d'effet possédées par ses ALLIÉS à
    portée (`create_aura_attack_damage_bonus_for_ally`, ex. `BeaconOfRage_FriendlyExtraDamageEffect`
    @180f33370 : +50% du bonus rage FLAT aux attaques MÊLÉE des amis Chaos adjacents d'Azkor, #191 ;
    `ConquerorImperativeEffect` @180f39650 : +extraDmg FLAT aux amis Mechanical adjacents vs cible à armure
    réduite, #23). SYMÉTRIQUE ALLIÉ de `aura_attack_damage_malus_from_enemies`. `carriers` = itérable (owner_id,
    owner_pos, owner_team, ..., effets du porteur) ; `ctx` = {att_id, att_pos, att_team,
    att_grand_alliance, att_traits, is_melee, target_armor_reduced}. Renvoie une liste d'`EffectBonus` (chaque porteur à portée empile son
    bonus) à intégrer aux modifiers de l'attaquant via `add_modifier`. Chaque `carrier` = tuple dont
    [0]=owner_id, [1]=owner_pos, [2]=owner_team, [-1]=effets (accepte le 4-tuple comme le 8-tuple
    `carriers` de la prédiction)."""
    out = []
    for c in (carriers or []):
        octx = {**(ctx or {}), "owner_id": c[0], "owner_pos": c[1], "owner_team": c[2]}
        for e in _as_effects(c[-1]):
            eb = e.create_aura_attack_damage_bonus_for_ally(octx)
            if eb is not None:
                out.append(eb)
    return out


def aura_defense_damage_malus_from_units(carriers, ctx) -> list:
    """Liste des modifiers %-DÉGÂT projetés sur la CIBLE d'un coup par les effets EffectWithTarget
    possédés par d'AUTRES unités (`create_aura_defense_damage_malus_for_ally`) — mirror de la boucle
    state-wide « TOUS les EffectWithTarget actifs × leurs cibles » de `CalculateDefenderModifiers-
    ForPrediction` @181002c30 (cf. case-68) pour les effets dont le TargetSelector projette HORS du
    porteur. Ex. `DaughterOfTheAbyss_FriendlyDmgReductionPctEffect` @180f3cde0 (-dmgReductionPct%
    Psychic aux amis rayon 2, #184) ; `DaughterOfTheAbyss_ExtraDamagePctEffect` @180f3cb60 (+extraDmgPct%
    aux Psykers ennemis rayon 2). `carriers` = itérable (owner_id, owner_pos, owner_team, effets du
    porteur) ; `ctx` = {tgt_id, t_pos, tgt_team, tgt_traits, damage_profile}. Renvoie une liste
    d'`EffectBonus` à intégrer aux modifiers du coup via `add_modifier`. SYMÉTRIQUE défenseur de
    `aura_attack_damage_malus_from_enemies` (chaque carrier = tuple [0]=id, [1]=pos, [2]=team, [-1]=effets)."""
    out = []
    for c in (carriers or []):
        octx = {**(ctx or {}), "owner_id": c[0], "owner_pos": c[1], "owner_team": c[2]}
        for e in _as_effects(c[-1]):
            eb = e.create_aura_defense_damage_malus_for_ally(octx)
            if eb is not None:
                out.append(eb)
    return out


def crit_chance_bonus_from_effects(effects) -> int:
    """Σ des bonus de CHANCE de crit des effets ACTIFS de l'attaquant
    (`DamagePrediction.GetCritChanceBonusFromEffects`@181031180) — couche calc-time ajoutée à
    `GetStat(9)` dans RollCritical (PAS dans GetStat ⇒ pas dans le combatSnapshot ⇒ à sommer ici).
    No-op (0) tant qu'aucun effet n'override `create_effect_crit_chance_bonus_for_attack`."""
    total = 0
    for e in _as_effects(effects):
        b = e.create_effect_crit_chance_bonus_for_attack()
        if b is not None:
            total += b
    return total


def crit_damage_bonus_from_effects(effects) -> int:
    """Σ des bonus de DÉGÂT de crit des effets ACTIFS de l'attaquant
    (`DamagePrediction.GetCritDamageBonusFromEffects`@181031bb0) — couche calc-time ajoutée à
    `GetStat(10)` dans CalculateCriticalDamage. No-op (0) tant qu'aucun effet n'override
    `create_effect_crit_damage_bonus_for_attack`."""
    total = 0
    for e in _as_effects(effects):
        b = e.create_effect_crit_damage_bonus_for_attack()
        if b is not None:
            total += b
    return total


def stat_modifications_by_source(effects, source_of=None) -> dict:
    """Contributions stat-mod DÉCLARÉES par les effets actifs, groupées `{idxStatType: {source: amount}}`
    — à passer à `stats.seed_unit_stats(attributed=...)` pour une modification **attribuée** (résidu
    opaque réduit). Mirror de l'agrégation `AStatModifierEffect.ApplyModification` par (stat, source).
    `source_of(effect) -> clé de source` (défaut : tuple stable `("statmod", effect_type, source, name)`).
    No-op pour les effets non-StatModifier (stat `None` / amount `None`/0)."""
    out: dict = {}
    for e in _as_effects(effects):
        st = e.get_stat_modification_stat()
        if st is None:
            continue
        amt = e.get_stat_modification_amount()
        if not amt:
            continue
        src = (source_of(e) if source_of else
               ("statmod", getattr(e, "effect_type", None), getattr(e, "source", None),
                getattr(e, "name", None)))
        d = out.setdefault(int(st), {})
        d[src] = d.get(src, 0) + int(amt)
    return out


def apply_effect_stat_modifications(unit_stats, effects, source_of=None) -> list:
    """Applique sur `unit_stats` (`UnitStats`) les stat-modifications DÉCLARÉES par les effets actifs
    (`AStatModifierEffect` : `get_stat_modification_stat` + `get_stat_modification_amount`),
    attribuées à la source de chaque effet — mirror de `AStatModifierEffect.ApplyModification`
    @180f0a2f0 (émet un `ChangeStat` sur la **modification** du stat, part 5/9). Réciproque =
    `unit_stats.revert_stat` (`RevertModification` @180f0aa40, part 6).

    `source_of(effect) -> clé de source` (défaut : tuple stable `("statmod", effect_type, source,
    name)`) sert au revert par-source. No-op pour les effets non-StatModifier (stat `None` /
    amount `None`/0). Renvoie la liste des `(source, statType, amount)` appliqués (pour un revert
    ultérieur exact ou une validation d'attribution vs `statDelta`)."""
    applied = []
    for e in _as_effects(effects):
        st = e.get_stat_modification_stat()
        if st is None:
            continue
        amt = e.get_stat_modification_amount()
        if not amt:
            continue
        src = (source_of(e) if source_of else
               ("statmod", getattr(e, "effect_type", None), getattr(e, "source", None),
                getattr(e, "name", None)))
        unit_stats.change_stat(int(st), src, int(amt))
        applied.append((src, int(st), int(amt)))
    return applied
