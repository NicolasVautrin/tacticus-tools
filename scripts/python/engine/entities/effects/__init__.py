"""`engine.entities.effects` — port des effets de combat `IdunBattle.Entities.Effects.*` en hiérarchie
de classes (BaseEffect + sous-classes 1:1 + factory + registre), remplaçant l'ancien registre de données
(`effects_damage_bonus.EffectDef`). Mirror fidèle du modèle natif « 1 classe par effet ».

Ce module héberge AUSSI la tranche « builders qui ITERENT LES EFFETS » de `IdunBattle.Core.Services.
DamageCalculations` (convention repo : DamageCalculations eclatee par concern — cf. en-tete de
`services/damage_modifiers.py`) : `build_attacker_modifiers_from_effects` = `CalculateAttackerModifiers
ForPrediction IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` (boucle effets), `build_defender_modifiers_from_effects` = `CalculateDefender
ModifiersForPrediction IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction`, + les axes COUPS (`hits_bonus_from_effects` / `_defender_` / auras).
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
from .base import BaseEffect
from .factory import EffectFactory

__all__ = [
    "BaseEffect", "EffectFactory", "build_attacker_modifiers_from_effects",
    "calculate_attacker_modifiers_for_prediction", "build_defender_modifiers_from_effects",
    "hits_bonus_from_effects", "hits_malus_from_defender_effects", "aura_hits_malus_for_defense",
    "aura_hits_bonus_for_attack", "block_hits_reduction_from_effects", "board_effect_carriers",
    "additional_hit_groups", "aura_defense_damage_malus_from_units",
    "aura_attack_damage_bonus_from_allies", "aura_fixed_armor_bonus_for_defense",
    "crit_chance_bonus_from_effects", "crit_damage_bonus_from_effects",
    "piercing_bonus_from_effects", "apply_effect_stat_modifications",
    "stat_modifications_by_source", "statmod_source_key", "effect_stat_mod_key",
    "effect_stat_modifications", "effect_stat_overrides", "stat_overrides_by_stat",
    "match_wide_effects", "MATCH_WIDE_EFFECT_NAMES",
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


# --- Effets MATCH-WIDE : poses au `MatchInit` par une ability GLOBALE, portes par AUCUNE unite ---
#
# `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` n'itere PAS
# les effets de l'attaquant : il itere une collection recue en parametre, et invoque le slot de bonus
# sur chaque effet **SANS AUCUN FILTRE de proprietaire, de position ni d'adjacence** -- il passe
# l'`AbilityEntities` complet (attaquant / cible / tuile / arme) et laisse l'effet decider seul. Le
# port a scinde cette boucle unique en pattes (self, aura alliee, aura ennemie) : c'est un artefact du
# port, pas du natif (cf. `BaseEffect.create_aura_attack_damage_bonus_for_ally`). Il en manquait une :
# l'effet dont le porteur n'est NI l'attaquant NI une unite.
#
# UN SEUL membre a ce jour, et il est LU : `Melta_ExtraDmg` (0x511=1297), pose par
# `IdunBattleLogic.Entities.Abilities.Damage.Loki.OnMeltaDamageAbility$$CreateBehaviour` =
# `AddEffect(0x511, AbilityStateReference, targets = First(AllTiles(), 1))` sur UNE TUILE arbitraire,
# sous le trigger INCONDITIONNEL `On(0x19 = EventTriggerType.MatchInit, true)` d'une ability GLOBALE
# (aucun owner -- meme famille `Damage.Loki.*` que `OnFireDamageAbility` / `OnToxicDamageAbility`,
# cf. `GLOBAL_TRIGGERS`). Il est donc present dans TOUTE bataille, et ses deux conjoints de gate
# portent sur le COUP et la CIBLE, jamais sur le porteur.
#
# ⚠ POURQUOI PAS « lire l'effet de tuile depuis l'etat » : le canal des effets de tuile
# (`load_state(tiles=tileMeta)`) est **OPT-IN**, et la plupart des etats ne le passent pas (mesure
# citee par `ai/state_bridge.py`). Un port qui en dependrait serait inerte **en silence** dans ces
# chemins-la -- exactement la degradation permissive que la doctrine proscrit. La presence de l'effet
# n'est pas une donnee d'etat : c'est une INVARIANTE de bataille, et c'est ainsi qu'elle est portee.
# Aucun risque de double comptage : cette boucle ne recoit que les effets de l'ATTAQUANT, et aucun
# agregateur du port ne balaie les effets portes par une TUILE (trou documente de
# `board_effect_carriers`).
MATCH_WIDE_EFFECT_NAMES: tuple = ("Melta_ExtraDmg",)

_MATCH_WIDE_EFFECTS: list | None = None


def match_wide_effects() -> list:
    """Instances des effets MATCH-WIDE (cf. l'encadre ci-dessus). Memoise : ces effets n'ont ni
    niveau ni multiplicateur (leur magnitude est un `globalValues`), donc une instance suffit."""
    global _MATCH_WIDE_EFFECTS
    if _MATCH_WIDE_EFFECTS is None:
        _MATCH_WIDE_EFFECTS = [EffectFactory.create({"name": n}) for n in MATCH_WIDE_EFFECT_NAMES]
    return _MATCH_WIDE_EFFECTS


def _attacker_effect_bonuses(effects, is_ranged: bool | None, is_normal_attack: bool,
                             has_moved: bool | None, target_traits=None, is_prediction=False,
                             target_armor_reduced: bool | None = None, att_ctx=None) -> list:
    """Boucle EFFETS de l'attaquant (contribution PARTAGÉE prédiction/combat) : pour chaque effet ACTIF,
    `create_effect_damage_bonus_for_attack` (additif/percent) + `get_armor_penetration` (axe armure) →
    liste d'`EffectBonus`. C'est la boucle `param_5` commune aux deux slots natifs (0xd préd / 0xf combat).
    `target_armor_reduced` = gate `HasNegativeModifier(cible armure)` (ConquerorImperative) threadé du site.
    `att_ctx` = contexte POSITIONNEL {att_pos, tile_effects_by_pos} pour les bonus à magnitude
    position-dépendante (LordOfTempests IdunBattle.Entities.Effects.Loki.LordOfTempests_ExtraDamageEffect$$CreateEffectDamageBonusForAttack) ; None = inconnu (ces bonus rendent None)."""
    bonuses = []
    own = list(_as_effects(effects))
    # #1015-r1 -- `HasEffect(Owner@DSLSelectors+0x30, <type>, ...)` / `HasEffect(Caster@+0x48, ...)`
    # SUR L'ATTAQUANT LUI-MEME. Ce foyer-ci est le SEUL qui tienne la liste des effets de
    # l'attaquant (c'est son parametre `effects`), et il est PARTAGE prediction/combat -- la poser
    # chez les deux producteurs d'`att_ctx` forkerait ce que le natif ne forke pas (il n'a qu'UNE
    # boucle et qu'UN `AbilityEntities`). Premier consommateur : les TROIS `HasEffect` de
    # `CloseCombatWeakness_ReduceDmg_Effect` (Suppress 1144 / StartedTurnAdjacent 1129 /
    # SuppressRange 1159), tous sur le porteur de l'effet parcouru.
    # ⚠ Les effets MATCH-WIDE en sont EXCLUS : ce ne sont pas des effets PORTES par une unite
    # (cf. l'encadre ci-dessus), donc `HasEffect(Owner, ...)` ne peut pas les voir.
    # Un `frozenset` de NOMS (jamais d'ordinaux) : c'est la cle du registre `EFFECT_CLASSES` et
    # celle des membres d'`EffectType`, donc la comparaison est NOMMEE des deux cotes.
    att_ctx = dict(att_ctx or {})
    att_ctx["owner_effect_names"] = frozenset(str(e.name) for e in own if getattr(e, "name", None))
    # Les effets MATCH-WIDE entrent dans la MEME boucle que ceux de l'attaquant -- c'est exactement
    # ce que fait le natif, qui n'a qu'UNE boucle et aucun filtre de porteur (cf. l'encadre).
    for e in own + match_wide_effects():
        db = e.create_effect_damage_bonus_for_attack(is_ranged, has_moved, target_traits=target_traits,
                                                     is_prediction=is_prediction,
                                                     is_normal_attack=is_normal_attack,
                                                     target_armor_reduced=target_armor_reduced,
                                                     att_ctx=att_ctx)
        if db is not None:
            db.native_face = e.ATTACK_BONUS_NATIVE_FACE     # #437-r1-r1-r1 (cf. BaseEffect)
            bonuses.append(db)
        # #1008-r5 -- `is_ranged` EST threade ici, et ce n'est pas du zele : le trigger de
        # l'`EffectBonus` que `IdunBattle.Entities.Effects.BaseEffect$$DamageBonusForAttack` evalue
        # AVANT d'appeler `IgnoreArmor()` n'est PAS le meme d'un porteur a l'autre --
        # `PowerTrip_IgnoreArmorEffect` porte `IsNormalAttack`, `KanOpenerEffect` porte
        # `IsMeleeAttack`. Sans ce parametre, la gate de vecteur serait INEXPRIMABLE et le port
        # appliquerait la condition de l'un a l'autre, en silence.
        pen = e.get_armor_penetration(is_normal_attack, is_ranged=is_ranged)
        if pen is not None:
            # Axe ARMURE : le natif SOMME `@0x28` des DEUX accumulateurs avant
            # `GetBaseDamageWithFixedPiercedArmor` -> face sans consequence arithmetique.
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
    `has_moved` → bonus gated no-move (HeavyWeapon IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier) ; `target_armor_reduced` → bonus gated
    `HasNegativeModifier(cible armure)` (ConquerorImperative IdunBattle.Entities.Effects.Loki.ConquerorImperativeEffect$$CreateDamageModifier)."""
    return build_attacker_modifiers(
        _attacker_effect_bonuses(effects, is_ranged, is_normal_attack, has_moved, target_traits,
                                 target_armor_reduced=target_armor_reduced, att_ctx=att_ctx))


def calculate_attacker_modifiers_for_prediction(
        effects, is_ranged: bool | None = None, is_normal_attack: bool = True,
        has_moved: bool | None = None, attack_stat=None,
        apply_stat_mod_debuff: bool = False, target_traits=None,
        target_armor_reduced: bool | None = None, att_ctx=None) -> DamageModifiers:
    """`IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` (slot 0xd) — chemin **PRÉDICTION**, DISTINCT
    du combat. = la boucle EFFETS partagée (`_attacker_effect_bonuses`) **PLUS** la conversion
    stat-modifications `CalculateModifiersFromStatModifications` (prédiction-only, xref IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction+0x71c).

    RE #194 (corrige la lecture #49 « debuff Current→Initial ») : la face attaquant native lit
    l'**AttackComponent** de l'attaquant (IdunBattle.Entities.Components.AttackComponent$$.cctor) avec negate=**0** et convertit chaque
    modification en entrée **POURCENT** de la %-list (`1+v/100`, cf. IdunBattle.Core.Services.DamageCalculations$$CalculateModifiersFromStatModifications/IdunBattle.Core.Services.DamageCalculations$$GetMultiplierFromDamageBonus) — PAS un
    flat-subtract. Son gate d'activation (entité contexte@0x08 nullable + interface slot 3
    `DAT_1831b7f78`) n'est PAS élucidé, et il est prouvé INERTE sur le chemin normal-attack (#49 :
    aura Calgar +1298 Attack présente, prédiction bit-exacte SANS cette contribution — +1298% aurait
    explosé). → RESTE GATÉ par `apply_stat_mod_debuff` (défaut False, aucun call-site ne l'active) ;
    le câbler exigerait d'abord la RE du gate (tâche dédiée). La face DÉFENSEUR (DefenseComponent,
    negate=1) est, elle, PORTÉE et validée (#194, prediction.py)."""
    # #71 : chemin PREDICTION -> is_prediction=True. Le noeud DSL IsNormalAttack (trigger SmashaEad
    # IdunBattle.Entities.Effects.Loki.SmashaEadEffect$$CreateEffectDamageBonusForAttack) evalue FALSE ici (verdict re-expert) -> SmashaEad n'entre pas dans la DamageModifiers de
    # prediction (matche le DISPLAY decisionView). Le COMBAT (build_attacker_modifiers_from_effects) garde
    # is_prediction=False (defaut) -> SmashaEad applique. RapidAssault (OwnerIsCaster seul) non affecte.
    bonuses = _attacker_effect_bonuses(effects, is_ranged, is_normal_attack, has_moved, target_traits,
                                       is_prediction=True, target_armor_reduced=target_armor_reduced,
                                       att_ctx=att_ctx)
    if apply_stat_mod_debuff and attack_stat is not None:
        # negate=False : mirror de l'appel natif IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction+0x71c (3e arg = 0, face attaquant NON négée).
        bonuses += calculate_modifiers_from_stat_modifications(attack_stat, negate=False,
                                                               native_face="attacker")
    return build_attacker_modifiers(bonuses)


def build_defender_modifiers_from_effects(effects, is_melee: bool | None = None,
                                          damage_profile: str | None = None,
                                          attacker_ctx: Mapping | None = None,
                                          defense_stat=None) -> DamageModifiers:
    """`IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction — DamageModifiers de la CIBLE (MODIFICATION du
    dégât reçu). Mirror COMPLET des DEUX moitiés du natif dans le MÊME accumulateur, dans l'ordre natif :
      1. **fold du stat-mod DEFENSE** (`defense_stat`, la 1re moitié IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction+0x407→IdunBattle.Core.Services.DamageCalculations$$CalculateModifiersFromStatModifications, negate=1) ;
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
            # #437-r1-r1-r1 : cette boucle mirroire le slot 0x1a, donc l'accumulateur DEFENSEUR --
            # SAUF pour les classes dont le natif n'implemente PAS ce slot mais
            # `CreateDamageModifier` (famille `DamageModifierAbilityEffect`, forwarder ATTAQUANT).
            # Le port les evalue ici parce que leur trigger est `OwnerIsTarget` (donc leur porteur
            # est la CIBLE, la seule liste que cette boucle balaie), mais le natif verse leur
            # contribution dans `attackModifiers`. Cf. `BaseEffect.DEFENSE_MALUS_NATIVE_FACE`.
            mb.native_face = e.DEFENSE_MALUS_NATIVE_FACE
            maluses.append(mb)
            # #1008-r2 -- LA PENETRATION D'ARMURE PORTEE PAR UN EFFET DU **DEFENSEUR**.
            # `IdunBattle.Entities.Effects.BaseEffect$$DamageMalusForDefense` (le corps de ce slot
            # 0x1a) n'evalue pas que les formules de l'`EffectBonus` : elle appelle AUSSI
            # `this.IgnoreArmor()` (slot virtuel `+0x718`) et range le resultat dans
            # `DamageBonus+0x38`, que `CalculateDefenderModifiersForPrediction` accumule dans
            # `DamageModifiers+0x28` -- le MEME axe armure que la face attaquant.
            # ⚠ DANS CE BLOC, ET C'EST LA FIDELITE MEME : le natif evalue `IgnoreArmor()` APRES
            # avoir teste le trigger de l'`EffectBonus` et sous ce test. Lire la penetration hors
            # du bloc l'activerait meme quand la gate est fausse (pour `Helspear` :
            # `IsUnit(Caster)`, donc face a une source non-unite). La gate n'est donc pas
            # dupliquee ici -- c'est celle du malus, une seule fois, comme dans le natif.
            pen = e.get_armor_penetration(is_normal_attack=True)
            if pen:
                maluses.append(for_armor_penetration(False, pen))
        # #10007 -- LE SLOT DE PERCAGE **DEFENSEUR** (`0x19` = 25 `CreatePiercingMalusForDefense`),
        # celui que cette boucle-ci mirroire vraiment. Re-mesure au decompile (`t6dpr4k06g`) :
        # `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction`
        # invoque `0x1a` / `0x1b` / **`0x19`**, tandis que son homologue attaquant invoque
        # `0x16` / `0x17` / **`0x18` = 24**. Le port n'appelait QUE le 24 ici : le 25 etait MUET.
        pm = e.create_piercing_malus_for_defense(damage_profile, is_melee, attacker_ctx)
        if pm is not None:
            # L'accumulateur natif d'arrivee EST `defenseModifiers@+0x20` (le slot 25 n'est invoque
            # que par la boucle defenseur). Descriptif : `add_modifier` route le kind "Piercing"
            # vers l'axe `extra_pierce` UNIQUE, que le natif somme sur les deux faces.
            pm.native_face = "defender"
            maluses.append(pm)
        # #112 : axe PERCAGE porte par la CIBLE (`<Effect>.CreatePiercingBonusForAttack`, trigger
        # `OwnerIsTarget` -- ex. `Supercharge_ExtraPiercingEffect`). Slot d'interface DISTINCT ;
        # `add_modifier` route le kind "Piercing" vers `extra_pierce` (axe @0x20), JAMAIS vers le
        # scalaire degat. Aucun effet PREEXISTANT ne surcharge ce slot -> no-op strict pour eux.
        # ⚠ #10007 -- POURQUOI LE SLOT **24** RESTE APPELE ICI, dans la boucle DEFENSEUR : les DEUX
        # boucles natives recoivent LA MEME collection d'effets. Mesure (`t6dpr4k06g`) --
        # `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` la construit UNE FOIS
        # (`local_948`, un appel virtuel unique) et la passe INCHANGEE a l'appel du slot `0xd`
        # (attaquant) PUIS a celui du slot `0xe` (defenseur) : aucune reaffectation entre les deux.
        # Chaque boucle ecrit `AbilityEntities+0x18 (Owner) <- le porteur de l'effet courant` avant
        # d'evaluer le trigger, donc le tri natif se fait par le TRIGGER (`OwnerIsTarget` /
        # `OwnerIsCaster`), jamais par la liste. Le port, lui, decoupe par LISTE (effets de
        # l'attaquant / effets de la cible) : appeler le slot 24 ici est la SEULE voie par laquelle
        # il atteint un surchargeant `OwnerIsTarget` (`Supercharge`, `BloodChalice`, `AllIsDust`).
        # Ce n'est donc pas une erreur d'accumulateur -- et ce serait sans effet arithmetique de
        # toute facon, `CalculateBaseDamageWithAllModifiers` sommant `attackModifiers@0x20` et
        # `defenseModifiers@0x20` dans le meme `pierce_pct`.
        # #1052 : `attacker_ctx` est desormais THREADE ici aussi -- `AllIsDustEffect` lit sur le
        # CASTER les deux `StatAmount` de `GetPierceStatModifier` et la somme
        # `CasterEffectPierceAddition`, exactement comme les malus de defense lisent leurs noeuds
        # `Caster@<DSLSelectors+0x48>` par ce meme dict. Les deux implementations preexistantes
        # (Supercharge, BloodChalice) l'ignorent : signature elargie, comportement inchange.
        pb = e.create_piercing_bonus_for_attack(damage_profile, is_melee, attacker_ctx)
        if pb is not None:
            maluses.append(pb)
    acc = build_defender_modifiers(maluses)
    # Moitié DEFENSE (1re du natif) : chaque modification du DefenseComponent → entrée %-list `1±v/100`
    # via `IdunBattle.Core.Services.DamageCalculations$$CalculateModifiersFromStatModifications` (negate=1). GROUND TRUTH #194/#197 (C2_19,
    # tuile Thorns −50 → ×1.5 en prédiction ET en combat réel, mesuré live). No-op si defense_stat None/no-mod.
    # `native_face="defender"` (#437-r1-r1-r1) : ce fold est celui de `CalculateDefenderModifiers
    # ForPrediction` lui-meme, donc `defenseModifiers.Multiplier@0x30` -- c'est deja ce que faisait
    # le site de fusion en aval ; la face est simplement DITE a l'entree au lieu d'etre deduite.
    for eb in calculate_modifiers_from_stat_modifications(defense_stat, negate=True,
                                                          native_face="defender"):
        add_modifier(acc, eb)
    return acc


def defender_effect_block_sources(effects, defender_fixed_armor: int = 0,
                                  defender_attack: int = 0,
                                  defender_max_health: int = 0) -> list:
    """Sources de BLOCK supplementaires posees par les effets de la CIBLE (defenseur) — a AJOUTER a la
    chaine `apply_random_block_damage` APRES le block de base (scalaire `GetStat(7/8)`). Mirror des
    entrees SEPAREES de `GetMultiValueStat(7)` (`IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances`) posees par
    `AddExtraBlockEffectToOwner` (ex. BeastSlayer IdunBattleLogic.Entities.Abilities.Triggered.Loki.BeastSlayerAbility$$CreateAddBlockEffectBehaviour : chance 10% / amount=100% FixedArmor courant),
    ABSENTES du scalaire (verifie live : orksNob blockChance=0). Agrege
    `create_effect_block_source_for_defense(defender_fixed_armor)` (defaut None). Effets deja filtres actifs.
    Retourne [] si aucun effet ne pose de source -> combat exact inchange (no-op). #72.

    `defender_max_health` = `GetStat(cible, Health = 5, StatPart.Maximum = 2)` -- 3e substrat de la
    famille, consomme par `BeastSnagga_ExtraBlock` (#1015-r1). Meme regime que les deux autres :
    `0` = non threade -> la source concernee rend `None`."""
    out = []
    for e in _as_effects(effects):
        bs = e.create_effect_block_source_for_defense(defender_fixed_armor,
                                                      defender_attack=defender_attack,
                                                      defender_max_health=defender_max_health)
        if bs is not None:
            out.append(bs)
    return out


def _hits_contribution(hb, block_reduction: bool = False) -> int:
    """Contribution SIGNEE d'un `EffectBonus` a l'axe COUPS, APRES le tri natif par signe.

    Mirror du corps de boucle de `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` : chaque
    `HitsBonusForAttack` non nul est range dans l'une de DEUX listes selon que son `addition` est
    `< 0` (REDUCTION) ou `>= 0` (addition), et la liste des reductions n'est sommee que
    **si aucun effet n'a rendu `BlockHitsReduction == true`**. `block_reduction=True` rend donc 0
    pour toute contribution negative -- et ne touche a RIEN d'autre : les additions passent
    inchangees, le tri se fait bonus par bonus (jamais sur l'agregat), et le canal reste inerte
    tant qu'aucun effet n'arme le booleen (defaut `False`).

    Le SIGNE, et pas la provenance : le natif ne separe pas « effet de l'attaquant » de « effet du
    defenseur » sur cet axe (une seule boucle sur `GetActiveEffectsWithBonuses`). Une reduction
    portee par l'ATTAQUANT (`FightingRetreat_HitReduction`, trigger `OwnerIsCaster`) est donc
    bloquee au meme titre qu'un `Parry` de la cible. Foyer UNIQUE, partage par les QUATRE
    agregateurs de l'axe (attaquant / defenseur / aura defense / aura attaque)."""
    if hb is None:
        return 0
    if hb.kind == "Addition":
        v = int(hb.value)
    elif hb.kind == "Subtraction":
        v = -int(hb.value)
    else:
        return 0
    return 0 if (block_reduction and v < 0) else v


def board_effect_carriers(att_id, attacker_effects, tgt_id, target_effects, aura_sources) -> list:
    """Univers du balayage BOARD-WIDE de `block_hits_reduction_from_effects` : la liste
    `(owner_id, effets ACTIFS du porteur)` de TOUTES les unites du board, sans doublon.

    Mirror de `IdunBattle.Core.Services.EffectsQuery$$GetActiveEffectsWithBonuses`, RELU : la
    fonction ne prend AUCUN argument de portee -- elle enumere la liste globale des entites-effet du
    monde, filtre sur `EffectComponent+0x5c` (`IsActive`) et sur `targets.Count > 0`, puis rend
    `(effet, cibles)`. Aucun scope attaquant/defenseur nulle part.

    Cote port les trois collections que la formule tient deja RECOUVRENT ce meme univers : les
    `aura_sources` sont TOUTES les unites vivantes != cible (donc l'attaquant y est), et
    `target_effects` ferme la liste avec la cible. La dedup se fait par `owner_id` -- l'attaquant et
    la cible sont poses en TETE (leurs listes sont celles que la facade a explicitement collectees),
    les auras completent.

    ⚠ NON COUVERT : les effets portes par une TUILE. `GetActiveEffectsWithBonuses` enumere des
    entites-effet, dont les cibles peuvent etre des tuiles ; le port n'a d'`aura_sources` que pour
    les UNITES. Aucun des deux implementeurs de `BlockHitsReduction` n'est tile-borne (1117 sur
    `eldarMauganRa`, 1538 sur `votanSmnSteeljack`), donc le trou est documente, pas comble."""
    out: list = []
    seen = set()
    for oid, effs in ((att_id, attacker_effects), (tgt_id, target_effects)):
        out.append((oid, effs))
        if oid is not None:
            seen.add(oid)
    for c in (aura_sources or []):
        oid = c[0]
        if oid in seen:
            continue
        seen.add(oid)
        out.append((oid, c[-1]))
    return out


def block_hits_reduction_from_effects(carriers, att_ctx: Mapping | None = None) -> bool:
    """OU LOGIQUE de `IdunBattle.Entities.Effects.BaseEffect$$BlockHitsReduction` sur les effets
    ACTIFS du BOARD -- l'interrupteur qui eteint la liste des REDUCTIONS de coups (case-366-r1).

    Le natif l'evalue dans une boucle DEDIEE sur la MEME collection que les bonus de coups
    (`EffectsQuery$$GetActiveEffectsWithBonuses` = tous les effets actifs du board) et arme un
    simple flag des qu'UN effet rend `true` -- il n'y a ni cumul ni magnitude. La boucle est
    `effets x CIBLES` et ecrit `AbilityEntities+0x18 (Owner) <- la cible de l'effet` avant chaque
    appel : `carriers` = `[(owner_id, effets)]` est le mirror de ce couplage, et l'agregateur pose
    `owner_id` dans le contexte de chaque appel.

    ⚠ ELARGISSEMENT #366-r1-blockhits-purgeresponse : jusqu'a cette tranche le balayage se limitait
    aux effets de l'ATTAQUANT, ce qui RENDAIT le noeud `get_OwnerIsCaster` du seul implementeur
    alors porte (`InescapableAccuracy_OverridHitsEffect`). Le SECOND implementeur natif
    (`IdunBattle.Entities.Effects.Loki.PurgeResponseEffect$$CreateBlockHitReductionTrigger` =
    `TriggeringAbilityIs(EffectType.Overwatch_AutoAttack)`) n'a PAS ce noeud : son porteur peut etre
    n'importe qui sur le board, y compris dans l'autre camp. Le balayage est donc aligne sur
    l'univers natif (`board_effect_carriers`), et `get_OwnerIsCaster` a MIGRE dans la classe 1117
    qui le porte -- une seule semantique, deplacee a sa place native, pas ajoutee.

    L'`ActiveCondition` reste a SA place native : le natif filtre l'enumeration sur
    `EffectComponent.IsActive @+0x5c` (relu dans `GetActiveEffectsWithBonuses`), et le port recoit
    des effets deja passes par `EffectsState.active_effects`. Les classes qui portent ce canal
    rendent NEANMOINS leur condition une seconde fois dans le canal (meme discipline que 1115/1116,
    meme store `UnitFlagsComponent`) : redondant, jamais faux."""
    base = dict(att_ctx or {})
    for owner_id, effs in (carriers or []):
        octx = {**base, "owner_id": owner_id}
        for e in _as_effects(effs):
            if e.block_hits_reduction(octx):
                return True
    return False


def hits_bonus_from_effects(effects, is_normal_attack: bool = True,
                            att_ctx: Mapping | None = None,
                            block_reduction: bool = False) -> int:
    """Σ des bonus de COUPS (`CreateEffectHitsBonusForAttack`) des effets actifs (axe hits, ex.
    PowerTrip_FullHealth). Addition = +value, Subtraction = −value.
    `att_ctx` = le `board` de `AttackHitsWithModifiersFormula` + `tile_effects_by_pos` +
    `persistent_data` (cf. `BaseEffect.create_effect_hits_bonus_for_attack`) — requis par les bonus
    dont le gate porte sur la CIBLE (`LetTheGalaxyBurnEffect` IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits). None → ces bonus no-op.
    `block_reduction` = le flag `BaseEffect$$BlockHitsReduction` de l'attaque (cf.
    `_hits_contribution`) : les contributions NEGATIVES de ce canal sont alors ignorees --
    `FightingRetreat_HitReduction` en est une, portee par l'ATTAQUANT."""
    total = 0
    for e in _as_effects(effects):
        total += _hits_contribution(e.create_effect_hits_bonus_for_attack(is_normal_attack, att_ctx),
                                    block_reduction)
    return total


def additional_hit_groups(effects, ctx: Mapping | None = None) -> list:
    """Concatène les groupes de COUPS ADDITIONNELS HETEROGENES déclarés par les effets ACTIFS de
    l'attaquant (`additional_hit_groups`, ex. SquigHound_AdditionalHits : 2 coups [minDmg,maxDmg]
    profil Physical). Chaque groupe `{count, min, max, profile}` = des coups à dégât/profil PROPRE à
    matérialiser APRES les coups d'arme (prev-threadés). Mirror IdunBattle.Entities.Effects.EffectAdditionalHits$$Create.
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
    énumère les effets GLOBALEMENT (`IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsFromEffectsInternal`) et le
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
                                     dist: int | None = None,
                                     block_reduction: bool = False,
                                     is_normal_attack: bool = True,
                                     att_ctx: Mapping | None = None) -> int:
    """Σ des modifications de COUPS des effets actifs de la CIBLE (`create_effect_hits_malus_for_defense`,
    ex. LightCover IdunBattle.Entities.Effects.Loki.LightCoverEffect$$CreateEffectHitsBonusForAttack : -2 ranged ; Parry IdunBattle.Entities.Effects.Loki.ParryEffect$$CreateEffectHitsBonusForAttack : -1 mêlée ;
    Camouflage/Diminutive). Natif = même canal `CreateEffectHitsBonusForAttack` trigger
    `OwnerIsTarget` ; plancher min=1 appliqué chez le consommateur (`max(1, …)`).
    #204 / #10019 — `MasterAnnihilator_AdditionalHitEffect` est ici sur la SEULE face PREDICTION.
    Son artefact natif est bien `CreateAdditionalHits` (canal #179) et non
    `CreateEffectHitsBonusForAttack`, ce qui reste VRAI et gouverne le COMBAT : #204 y a mesure une
    valeur CONSTANTE (stat ATTACK a l'unite, 4617 sur 5/5) contre 8 valeurs distinctes sur 8 pour
    les coups d'arme, donc un GROUPE. Mais cette face-la n'avait jamais ete confrontee, et #10019
    l'a mesuree : le natif PREDIT un coup de plus au degat EXACT d'un coup d'arme (trois paires,
    six nombres, rapports entiers `(h+1)/h` sur les DEUX bornes). La classe rend donc sa
    contribution UNIQUEMENT quand `att_ctx["is_prediction"]` -- cf. sa docstring pour la voie
    native, qui reste non tranchee (`#10019-r1`).
    `defender_on_cover` = gate compute-time des effets de TUILE (LightCover `AreEqual(coverPatch,target)`,
    #113) : None=applique-sur-présence (prédiction), True/False=cible sur/hors sa tuile de cover (combat).
    `block_reduction` = le flag `BaseEffect$$BlockHitsReduction` de l'attaque : ce canal ne produit
    QUE des contributions negatives, il est donc integralement eteint quand le flag est arme
    (case-366-r1). Retour signé (à ADDITIONNER aux hits).
    `is_normal_attack` = nature du VECTEUR, threadee depuis la formule (MEME donnee que pour le canal
    ATTAQUANT `hits_bonus_from_effects`) : le noeud `IdunBattleLogic.Entities.DSLTriggers$$IsNormalAttack`
    existe AUSSI cote defense -- `IdunBattle.Entities.Effects.Loki.ShroudPsalmEffect$$
    CreateEffectHitsBonusForAttack` = `get_OwnerIsTarget & IsNormalAttack` (#419-r1-tr9-r4-r1-r2).
    Les quatre autres porteurs de ce canal (LightCover, Parry, Camouflage, Diminutive) n'ont PAS ce
    noeud : leur reduction porte aussi sur les attaques d'ABILITY.
    `att_ctx` = le `board` COMPLET de la formule, MEME dict que celui deja passe aux canaux
    ATTAQUANT et AURA -- le natif n'a QU'UN canal (`CreateEffectHitsBonusForAttack`) et passe le MEME
    `AbilityEntities` a tous les effets de sa boucle, donc rien n'y borne les noeuds lisibles au
    DEFENSEUR. Premier consommateur : `TerrorsLament_HitReduction`, dont le trigger porte sur
    l'ATTAQUANT (`IsAdjacent(Caster, Owner) & AreEnemies(Owner, Caster) & !HasTrait(Caster,
    Immune)`) et non sur la cible. Absent -> ces gates se taisent."""
    total = 0
    for e in _as_effects(effects):
        total += _hits_contribution(
            e.create_effect_hits_malus_for_defense(is_melee, damage_profile, defender_on_cover, dist,
                                                   is_normal_attack=bool(is_normal_attack),
                                                   att_ctx=att_ctx),
            block_reduction)
    return total


def aura_hits_malus_for_defense(units_effects, ctx, block_reduction: bool = False) -> int:
    """Σ des malus de COUPS projetés sur la CIBLE par des effets AURA possédés par d'AUTRES unités
    (`create_aura_hits_malus_for_defense`, ex. BigTargetAdjacentEffect IdunBattle.Entities.Effects.Loki.BigTargetAdjacentEffect$$CreateEffectHitsBonusForAttack : -1 ranged pour
    les alliés ring-1 du porteur). `units_effects` = itérable de (owner_id, owner_pos, owner_team,
    effets du porteur) ; `ctx` = {tgt_id, t_pos, tgt_team, is_melee}. Plancher min=1 chez le
    consommateur. `block_reduction` = le flag `BaseEffect$$BlockHitsReduction` (case-366-r1) : le
    natif range ces `-1` dans la MEME liste de reductions que `Parry`/`Camouflage` (tri par SIGNE,
    pas par provenance), donc ils sont eteints ensemble. Retour ≤ 0 (à ADDITIONNER aux hits)."""
    total = 0
    for owner_id, owner_pos, owner_team, effects in (units_effects or []):
        octx = {**(ctx or {}), "owner_id": owner_id, "owner_pos": owner_pos,
                "owner_team": owner_team}
        for e in _as_effects(effects):
            total += _hits_contribution(e.create_aura_hits_malus_for_defense(octx), block_reduction)
    return total


# #204 avait SUPPRIME `aura_hits_bonus_for_attack` (agregateur + hook) : son unique alimenteur
# d'alors, `AstartesBannerExtraHitEffect`, appelle en natif
# `IdunBattle.Entities.Effects.Loki.AstartesBanner_AdditionalHitsEffect$$CreateAdditionalHits`
# (canal #179) et non `CreateEffectHitsBonusForAttack` -- un canal sans alimenteur natif est un
# gate MORT, donc un piege. #372 le REOUVRE avec l'alimenteur natif qui manquait.
def aura_hits_bonus_for_attack(carriers, ctx, block_reduction: bool = False) -> int:
    """Somme des bonus de COUPS projetes sur l'ATTAQUANT par des effets-AURA possedes par d'AUTRES
    unites (`create_aura_hits_bonus_for_attack`).

    Alimenteur natif : `IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraHitsEffect$$
    CreateEffectHitsBonusForAttack` (1183 sur `tauShadowsun`, 1307 sur son summon Command-Link Drone)
    -- `EffectBonus.ForAddition(get_OwnerIsCaster & IsRangedAttack & !DamageProfileIs(0xd) &
    Maybe(chance), ConfigConst(0x2b = extraHit))`, donc un TERME de
    `IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula$$Calculate` -- pas un groupe #179.

    Mirror de la boucle NATIVE effets x cibles : `DamagePrediction$$GetAttackHits` prend TOUS les
    effets actifs du board (`EffectsQuery$$GetActiveEffectsWithBonuses`) et ecrit
    `AbilityEntities+0x18 (Owner) <- la cible de l'effet`. Cote port, chaque porteur re-evalue son
    selecteur sur l'ATTAQUANT (modele #49/#153, adjacence relue a la TUILE CANDIDATE) : le porteur
    lui-meme est exclu par le selecteur (`sel - Owner`), pas par cette boucle.

    `carriers` = les memes tuples que les autres canaux d'aura ([0]=owner_id, [1]=owner_pos,
    [2]=owner_team, [-1]=effets du porteur -- 4-tuple comme 8-tuple) ; `ctx` = {att_id, att_pos,
    att_team, att_faction, is_melee, damage_profile, turns_started_by_id, parent_by_id, rng}.
    `aura_peers` est injecte ICI : la branche `isDrone` du selecteur natif
    (`EntitiesIsNotTargetOfEffect`) doit pouvoir evaluer le selecteur d'un AUTRE porteur.
    `block_reduction` = le flag `BaseEffect$$BlockHitsReduction` (case-366-r1) -- inerte pour
    l'alimenteur actuel (`DefenderOfTheGreaterGood_ExtraHits` est un `ForAddition` POSITIF), threade
    par symetrie parce que le tri natif se fait au SIGNE de chaque bonus, pas au canal.
    Retour signe (a ADDITIONNER aux coups) ; 0 strict hors carrier."""
    total = 0
    cs = list(carriers or [])
    for c in cs:
        octx = {**(ctx or {}), "owner_id": c[0], "owner_pos": c[1], "owner_team": c[2],
                "aura_peers": cs}
        for e in _as_effects(c[-1]):
            total += _hits_contribution(e.create_aura_hits_bonus_for_attack(octx), block_reduction)
    return total


def aura_attack_bonus_from_allies(carriers, ctx) -> int:
    """Σ des bonus PLATS au stat Attack (BASE) projetés sur l'ATTAQUANT par les auras stat-mod possédées
    par ses ALLIÉS à portée (`create_aura_attack_bonus`, ex. `RitesOfBattleAbility` IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfBattleAbility$$CreateBehaviour :
    +extraDmg/_2 aux alliés ring-1, gate grande-alliance Imperial ; `PathOfCommandAbility` IdunBattleLogic.Entities.Abilities.Triggered.Loki.PathOfCommandAbility$$CreateBehaviour :
    +extraDmg(/_2 si même FACTION) aux alliés dans un rayon 2). `carriers` = itérable de (owner_id, owner_pos,
    owner_team, owner_mult, owner_level, owner_grand_alliance, owner_faction, effets du porteur) ; `ctx` =
    {att_id, att_pos, att_team, att_grand_alliance, att_faction, board, att_real_pos?}. Modélisé CÔTÉ
    SOURCE, évalué à la position passée dans `att_pos`. #153 (REFUTE l'ancien verdict #67 « position réelle
    jamais tuile candidate ») : en PRÉDICTION DISPLAY l'appelant passe la TUILE CANDIDATE (`attack_pos`,
    fallback position réelle) — la chaîne native threade la UnitPosition candidate de bout en bout
    (`IdunBattle.Core.Services.DamagePredictionQuery$$GetAllPredictions` -> `IdunBattle.Core.Services.DamagePrediction$$PredictNormalAttack` : CasterTile =
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
    DoctrinaImperatives IdunBattle.Entities.Effects.Loki.ConquerorImperativeEffect$$CreateTargetSelector : +extraArmor aux amis Mechanical ring-1 du porteur). SYMÉTRIQUE défenseur de
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
                eb.native_face = e.AURA_ATTACK_MALUS_NATIVE_FACE     # #437-r1-r1-r1
                out.append(eb)
    return out


def aura_attack_damage_bonus_from_allies(carriers, ctx) -> list:
    """Liste des bonus de DÉGÂT projetés sur l'ATTAQUANT par les auras d'effet possédées par ses ALLIÉS à
    portée (`create_aura_attack_damage_bonus_for_ally`, ex. `BeaconOfRage_FriendlyExtraDamageEffect`
    IdunBattle.Entities.Effects.Loki.BeaconOfRage_FriendlyExtraDamageEffect$$CreateEffectDamageBonusForAttack : +50% du bonus rage FLAT aux attaques MÊLÉE des amis Chaos adjacents d'Azkor, #191 ;
    `ConquerorImperativeEffect` IdunBattle.Entities.Effects.Loki.ConquerorImperativeEffect$$CreateDamageModifier : +extraDmg FLAT aux amis Mechanical adjacents vs cible à armure
    réduite, #23). SYMÉTRIQUE ALLIÉ de `aura_attack_damage_malus_from_enemies`. `carriers` = itérable (owner_id,
    owner_pos, owner_team, ..., effets du porteur) ; `ctx` = {att_id, att_pos, att_team,
    att_grand_alliance, att_traits, att_rarity, is_melee, target_armor_reduced, damage_profile, tgt_id, t_pos,
    tgt_team, tgt_traits, tile_effects_by_pos}. Renvoie une liste d'`EffectBonus` (chaque porteur à portée empile son
    bonus) à intégrer aux modifiers de l'attaquant via `add_modifier`. Chaque `carrier` = tuple dont
    [0]=owner_id, [1]=owner_pos, [2]=owner_team, [-1]=effets (accepte le 4-tuple comme le 8-tuple
    `carriers` de la prédiction).

    ⚠ Les appelants (`damage_model._apply_ally_attack_damage_auras`, prédiction
    `_apply_ally_attack_dmg_bonus`) EXCLUENT le porteur lui-même (`uid == att_id`) : c'est fidèle aux
    sélecteurs `AdjacentFriends`/`SurroundingFriends`, qui excluent la source. Un effet dont le
    trigger natif accorde AUSSI au porteur (`AreFriends(Owner, Caster)` sans aucun sélecteur —
    `PsychicStalk_FriendlyChaosExtraDamage`, #366-r1, car
    `IdunBattle.Entities.UnitExtensions$$IsFriend` n'écarte PAS l'égalité ; ou
    `SurroundingFriends(Owner) + Owner` — `DestroyTheWitch_ExtraDamage`) porte donc EN PLUS sa patte
    SELF dans `create_effect_damage_bonus_for_attack`. Les deux foyers sont DISJOINTS : ni trou, ni
    double-compte."""
    out = []
    cs = list(carriers or [])
    for c in cs:
        # #372 — `aura_peers` : la branche `isDrone` du selecteur de `DefenderOfTheGreaterGood`
        # (`EntitiesIsNotTargetOfEffect`) doit pouvoir evaluer le selecteur d'un AUTRE porteur.
        # Sans cette cle le gate se tait, et un DRONE double-compterait l'aura de son summoner.
        octx = {**(ctx or {}), "owner_id": c[0], "owner_pos": c[1], "owner_team": c[2],
                "aura_peers": cs}
        for e in _as_effects(c[-1]):
            eb = e.create_aura_attack_damage_bonus_for_ally(octx)
            if eb is not None:
                eb.native_face = e.AURA_ATTACK_BONUS_NATIVE_FACE     # #437-r1-r1-r1
                out.append(eb)
                # #1019-r1 -- LA PENETRATION D'ARMURE PORTEE PAR UN EFFET D'AURA.
                # `IdunBattle.Entities.Effects.BaseEffect$$DamageBonusForAttack` (le corps du slot
                # 0x16, celui que cette boucle-ci mirroire) ne se contente pas d'evaluer les
                # formules de l'`EffectBonus` : apres le test du trigger elle appelle AUSSI
                # `this.IgnoreArmor()` (slot virtuel `+0x718`), evalue le noeud rendu et range
                # l'entier dans `DamageBonus+0x38` -- que la boucle attaquant accumule dans
                # `DamageModifiers+0x28`, le MEME axe armure que les deux autres canaux.
                # ⚠ DANS CE BLOC, ET C'EST LA FIDELITE MEME : le natif lit `IgnoreArmor()` APRES le
                # test du trigger et SOUS ce test (lecture du decompile : tout le corps, y compris
                # l'appel `+0x718`, vit dans la branche `trigger == true`). La gate n'est donc pas
                # dupliquee ici -- c'est celle du bonus d'aura, une seule fois, comme dans le natif.
                # C'est la MEME structure que le canal DEFENSEUR (#1008-r2,
                # `build_defender_modifiers_from_effects`), pris ici par la face AURA.
                # ⚠ POURQUOI UN SLOT DE PORT DISTINCT de `get_armor_penetration` : le natif n'a
                # qu'UN slot (`IgnoreArmor`), mais il l'evalue une fois PAR (effet, cible du
                # selecteur) en ecrivant `AbilityEntities+0x18 (Owner) <- la cible courante`. Le
                # port, lui, decoupe par LISTE : `_attacker_effect_bonuses` ne voit que les effets
                # de l'attaquant, cette boucle-ci que ceux de ses ALLIES porteurs. Un effet d'aura
                # dont le selecteur EXCLUT son porteur (`SurroundingFriends` sans `+ Owner`, cas de
                # `WayOfTheShortBladeEffect`) ne doit RIEN donner quand son porteur attaque : le
                # brancher sur `get_armor_penetration` l'accorderait a Farsight lui-meme, que le
                # natif exclut par `get_OwnerIsCaster`. Meme raison exactement qui fait coexister
                # `create_effect_damage_bonus_for_attack` et `create_aura_attack_damage_bonus_for_ally`.
                # #1019-r4 : APPEL DIRECT du slot, plus un `getattr`. Le defaut
                # `aura_armor_penetration_for_ally(ctx) -> None` vit desormais sur `BaseEffect`,
                # a cote de `get_armor_penetration` -- meme slot natif (`<Effect>.IgnoreArmor`,
                # `<vtable +0x718>`), lu depuis la boucle d'AURA, ou `AbilityEntities+0x18 (Owner)`
                # vaut le BENEFICIAIRE et non le porteur. Le `getattr` d'origine ne simulait le
                # defaut que par l'ABSENCE d'attribut : une faute de frappe sur le nom d'une
                # surcharge se lisait alors comme « ce porteur n'ouvre pas l'axe armure », en
                # silence. Aucun changement de comportement : le seul implementeur est
                # `WayOfTheShortBladeDamageBuffEffect`.
                pen = e.aura_armor_penetration_for_ally(octx)
                if pen:
                    # `for_armor_penetration` -> kind "ArmorPenetration" -> `DamageModifiers.
                    # armor_penetration` (@0x28). Le natif SOMME `@0x28` des DEUX accumulateurs
                    # avant `GetBaseDamageWithFixedPiercedArmor` : la face est sans consequence
                    # arithmetique sur cet axe (meme note que `_attacker_effect_bonuses`).
                    out.append(for_armor_penetration(True, int(pen)))
    return out


def aura_defense_damage_malus_from_units(carriers, ctx) -> list:
    """Liste des modifiers %-DÉGÂT projetés sur la CIBLE d'un coup par les effets EffectWithTarget
    possédés par d'AUTRES unités (`create_aura_defense_damage_malus_for_ally`) — mirror de la boucle
    state-wide « TOUS les EffectWithTarget actifs × leurs cibles » de `CalculateDefenderModifiers-
    ForPrediction` IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction (cf. case-68) pour les effets dont le TargetSelector projette HORS du
    porteur. Ex. `DaughterOfTheAbyss_FriendlyDmgReductionPctEffect` IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_FriendlyDmgReductionPctEffect$$CreateEffectDamageMalusForDefense (-dmgReductionPct%
    Psychic aux amis rayon 2, #184) ; `DaughterOfTheAbyss_ExtraDamagePctEffect` IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_ExtraDamagePctEffect$$CreateEffectDamageBonusForAttack (+extraDmgPct%
    aux Psykers ennemis rayon 2) ; `PsychicStalk_ExtraAttackDamageEffect` IdunBattle.Entities.Effects.Loki.PsychicStalk_ExtraAttackDamageEffect$$CreateEffectDamageMalusForDefense
    (+extraDmgPct% aux ENNEMIS d'Ahriman sur un hex en feu, #366-r1 — SANS `CreateTargetSelector` :
    tout le ciblage vit dans le trigger, ce que cette boucle state-wide sait servir aussi).
    `carriers` = itérable (owner_id, owner_pos, owner_team, effets du
    porteur) ; `ctx` = {tgt_id, t_pos, tgt_team, tgt_traits, tgt_rarity, damage_profile, att_id, att_is_unit,
    tile_effects_by_pos}. Renvoie une liste
    d'`EffectBonus` à intégrer aux modifiers du coup via `add_modifier`. SYMÉTRIQUE défenseur de
    `aura_attack_damage_malus_from_enemies` (chaque carrier = tuple [0]=id, [1]=pos, [2]=team, [-1]=effets)."""
    out = []
    for c in (carriers or []):
        octx = {**(ctx or {}), "owner_id": c[0], "owner_pos": c[1], "owner_team": c[2]}
        for e in _as_effects(c[-1]):
            eb = e.create_aura_defense_damage_malus_for_ally(octx)
            if eb is not None:
                # #437-r1-r1-r1 : cette boucle mirroire la moitie `EffectWithTarget` du builder
                # DEFENSEUR, mais elle sert AUSSI des effets dont le natif implemente le slot
                # ATTAQUANT (`DaughterOfTheAbyss_ExtraDamagePct`) -- la face vient de la classe.
                eb.native_face = e.AURA_DEFENSE_MALUS_NATIVE_FACE
                out.append(eb)
    return out


def crit_chance_bonus_from_effects(carriers, att_ctx=None) -> int:
    """Σ des bonus de CHANCE de crit des effets ACTIFS du BOARD
    (`IdunBattle.Core.Services.DamagePrediction$$GetCritChanceBonusFromEffects) — couche calc-time ajoutée à
    `GetStat(9)` dans RollCritical (PAS dans GetStat ⇒ pas dans le combatSnapshot ⇒ à sommer ici).

    `att_ctx` = contexte du coup, threadé en UN SEUL point (`runner/operations/damage.py::
    AttackDamageOperation._crit_params`, la façade CRIT partagée par les 3 vecteurs d'attaque) —
    chaque effet évalue SES gates (`create_effect_crit_chance_bonus_for_attack(att_ctx)`). Le natif
    construit son `AbilityEntities` (caster = owner = attaquant, target = défenseur) DANS le canal,
    à partir des deux entités que son appelant lui passe : le contexte existe côté natif, il
    manquait seulement côté port — symétrique exact du résidu `N14` du canal crit-DÉGÂT.

    ⚠ ÉLARGISSEMENT #589-r1-r1 — même geste, même cause que `block_hits_reduction_from_effects`
    (`case-366-r1-blockhits-purgeresponse`), sur l'autre axe. Jusqu'à cette tranche la boucle ne
    balayait que les effets de l'ATTAQUANT, ce qui RENDAIT le nœud `get_OwnerIsCaster` des seuls
    implémenteurs alors portés (`WarHowl_ExtraDamage_Unstoppable` 1222,
    `InescapableAccuracy_extraCritChance` 1115). RELU dans le décompilé : le canal natif construit
    son `AbilityEntities` en `(attacker, attacker, defender)` puis, dans la boucle sur les effets,
    **ÉCRASE `AbilityEntities+0x18` (`Owner`) par le porteur de l'effet courant** — la même boucle
    `effets × cibles` que `DamagePrediction$$GetAttackHits`. Le porteur peut donc être n'importe
    qui sur le board, et `EmpyricAmbush` (1578) est justement porté par la **CIBLE**
    (`get_OwnerIsTarget`). Le balayage est aligné sur l'univers natif (`board_effect_carriers`), et
    `get_OwnerIsCaster` a MIGRÉ dans les classes qui le portent — une seule sémantique, déplacée à
    sa place native, pas ajoutée. Sans ce second geste l'élargissement rendrait 1222/1115
    PERMISSIFS (un porteur spectateur bufferait un tiers).

    `carriers` = `[(owner_id, effets)]`, et l'agrégateur pose `owner_id` dans le contexte de chaque
    appel : c'est le mirror de l'écriture `AbilityEntities+0x18`.

    No-op (0) tant qu'aucun effet n'override `create_effect_crit_chance_bonus_for_attack`."""
    base = dict(att_ctx or {})
    total = 0
    for owner_id, effs in (carriers or []):
        octx = {**base, "owner_id": owner_id}
        for e in _as_effects(effs):
            b = e.create_effect_crit_chance_bonus_for_attack(octx)
            if b is not None:
                total += b
    return total


def piercing_bonus_from_effects(effects, ctx=None) -> int:
    """Σ des bonus de PERÇAGE apportés par les effets ACTIFS de l'ATTAQUANT — mirror de la boucle native
    qui alimente les deux termes `Fix64` de
    `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio` depuis
    `IdunBattle.Entities.Effects.BaseEffect$$PiercingBonusForAttack` (un `EffectBonus` gaté par effet).

    `ctx` = contexte du coup ({owner_id/att_id/ability_type/target_traits/owner_ctx + is_ranged/
    is_overwatch/unit_ctx_of}) — chaque effet évalue SES gates
    (`create_effect_piercing_bonus_for_attack`). No-op (0) tant qu'aucun effet actif n'override le hook."""
    total = 0
    for e in _as_effects(effects):
        b = e.create_effect_piercing_bonus_for_attack(ctx)
        if b is not None:
            total += int(b)
    return total


def crit_damage_bonus_from_effects(carriers, att_ctx=None) -> int:
    """Σ des bonus de DÉGÂT de crit des effets ACTIFS du BOARD — mirror de la boucle
    `IdunBattle.Core.Services.DamagePrediction$$GetCritDamageBonusFromEffects`, couche calc-time
    ajoutée à `GetStat(10)` dans `IdunBattle.Core.Services.DamagePrediction$$CalculateCriticalDamage`.

    `att_ctx` = contexte du coup, threadé en UN SEUL point (`runner/operations/damage.py::
    AttackDamageOperation._crit_params`, la façade CRIT partagée par les 3 vecteurs d'attaque) —
    chaque effet évalue SES gates (`create_effect_crit_damage_bonus_for_attack(att_ctx)`). Le natif
    construit son `AbilityEntities` (caster = owner = attaquant, target = cible) DANS le canal, à
    partir des deux entités que `CalculateCriticalDamage` lui passe : le contexte existe côté
    natif, il manquait seulement côté port (résidu `N14`).

    ⚠ ÉLARGISSEMENT #589-r1-r1 — ce canal avait le MÊME résidu de portée que son frère crit-CHANCE,
    et il était déjà NOMMÉ ici : `AmuletOfTheVoidwyrm_CritDamageReductionEffect$$
    CreateCritDamageBonus` = `ForSubtraction(get_OwnerIsTarget, …)` vit sur la CIBLE. RELU dans le
    décompilé : la boucle native ÉCRASE `AbilityEntities+0x18` (`Owner`) par le porteur de l'effet
    courant à chaque itération, donc `get_OwnerIsTarget` y est parfaitement évaluable. Le balayage
    est aligné sur l'univers natif (`board_effect_carriers`) pour `EmpyricAmbush` (1578), qui est
    porté par la cible ; `get_OwnerIsCaster` a MIGRÉ dans les classes qui le portent (1116, 1222,
    `SmashaEad`), sans quoi l'élargissement les rendrait PERMISSIFS.

    `carriers` = `[(owner_id, effets)]`, et l'agrégateur pose `owner_id` dans le contexte de chaque
    appel : c'est le mirror de l'écriture `AbilityEntities+0x18`.

    ⚠ TOUJOURS NON COUVERT : `AmuletOfTheVoidwyrm_CritDamageReduction` n'est pas porté (il rend
    `None`) — l'axe RÉDUCTION défenseur de ce canal reste un gisement séparé. L'élargissement le
    rend désormais ATTEIGNABLE, il ne le porte pas."""
    base = dict(att_ctx or {})
    total = 0
    for owner_id, effs in (carriers or []):
        octx = {**base, "owner_id": owner_id}
        for e in _as_effects(effs):
            b = e.create_effect_crit_damage_bonus_for_attack(octx)
            if b is not None:
                total += b
    return total


def statmod_source_key(eff) -> tuple:
    """Cle de SOURCE d'une modification de stat DECLARATIVE (`AStatModifierEffect`), PARTAGEE entre
    l'attribution du seed (`stat_modifications_by_source`, `UnitContext.from_snapshot`) et le driver
    d'ActiveCondition (`runner/operations/refresh_effects.py`). MEME cle des deux cotes = le driver
    re-ecrit la MEME entree `ValueModification.per_source` (`Modify` = replace par-source, mirror
    `IdunBattle.Entities.Components.ValueModification$$Modify`) au lieu d'en creer une 2e -> aucun
    double-compte possible (piege deja rencontre avec `SWARM_HIT_REDUCTION_SOURCE`, cf.
    `unit_context.py`)."""
    return ("statmod", getattr(eff, "effect_type", None), getattr(eff, "source", None),
            getattr(eff, "name", None))


def effect_stat_mod_key(eff):
    """Cle UNIQUE de la `ValueModification` posee par CETTE instance d'effet — ou `None` si l'instance
    n'a pose aucune modification de stat.

    NATIF : la source d'un `ChangeStat` d'effet EST l'entite-effet elle-meme.
    `IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification` appelle
    `IdunBattleLogic.Entities.DSLBehaviors$$ChangeStat(Entity(target), Position(stat, part 5|9), 4,
    Direct(amount), Entity(<effectEntity>), ...)` et
    `IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification` rejoue le MEME appel avec
    `Position(stat, part 6)` et LA MEME `Entity(<effectEntity>)` ->
    `IdunBattle.Entities.Components.ValueModification$$ReverseModification` retire EXACTEMENT cette
    contribution. Il n'y a donc jamais DEUX entrees `per_source` pour une meme entite-effet.

    PORT : l'entite-effet n'existe pas offline, la cle est donc :
      1. `eff.stat_mod_source` si un chemin de POSE l'a renseignee (`AddEffectOperation._apply_stat_mods`,
         feuille `AddStaticStatModifierEffect`) ;
      2. sinon la cle DERIVEE `statmod_source_key(eff)` — c'est celle sous laquelle l'ATTRIBUTION DU SEED
         (`stat_modifications_by_source` -> `stats.seed_unit_stats(attributed=...)`) et le driver
         d'ActiveCondition (`runner/operations/refresh_effects.py`) ecrivent deja. Un effet SEEDE porte
         donc bien une modification par-source, RETIRABLE (c'est ce qui manquait : la cle etait calculee
         a l'attribution puis oubliee, donc l'expiration ne pouvait plus rien retirer) ;
      3. `None` si l'effet ne modifie AUCUN stat -> rien a reverter.

    DISCRIMINANT = `reverted_stats()` (R16). C'est le MEME predicat des deux cotes du natif : la paire
    `ApplyModification`/`RevertModification` construit son `Position(stat, part)` depuis le MEME
    `(**vtable+0x728)` = `GetStatModification()`, seule la `part` change (5|9 a l'apply, 6 au revert) —
    « un `AStatModifierEffect` reverte TOUJOURS le stat qu'il modifie ». Le predicat precedent
    (`get_stat_modification_stat() is not None`) ne voyait QUE la forme MONO-STAT de la base et rendait
    donc `None` pour toute la famille dont le `ApplyModification` est OVERRIDE (multi-stat / magnitude
    lue sur le ctx : `ActOfFaithBuffEffect`, `ProtectorImperativeEffect`, `AncestralFortune*`,
    `AugmentedAssault_ReduceArmor`, `BlackRage_ExtraMove`, `Waaagh_ExtraMovement`...). `reverted_stats()`
    couvre les DEUX formes (son defaut EST `[get_stat_modification_stat()]`)."""
    src = getattr(eff, "stat_mod_source", None)
    if src is not None:
        return src
    return statmod_source_key(eff) if eff.reverted_stats() else None


def effect_stat_modifications(eff, stats_ctx=None) -> list:
    """Les `(StatType, montant)` que l'APPLICATION de CET effet pose — **point de verite UNIQUE** des
    stat-modifications d'un effet, pour les DEUX formes natives (R16 : avant, deux chemins portaient le
    meme fait natif et un seul marchait selon la provenance de l'effet).

    NATIF — une seule paire de virtuels :
      • forme de BASE (mono-stat) : `IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification`
        lit `GetStatModification()` (`(**vtable+0x728)` -> ValueTuple<stat, amount, hidden> assemble par
        `IdunBattle.Entities.Effects.AStatModifierEffect$$GetStatModification` depuis les slots +0x748
        (`GetStatModificationStat`) et +0x758 (`GetStatModificationAmount`)) et emet UN `ChangeStat` ;
      • forme OVERRIDE (multi-stat / magnitude contextuelle) : la classe d'effet remplace
        `ApplyModification` et emet N `ChangeStat` (ex.
        `IdunBattle.Entities.Effects.Loki.ActOfFaithBuffEffect$$ApplyModification` = crit-chance +
        crit-damage, avec la part INITIAL du crit-damage du porteur en entree).

    PORT : la forme OVERRIDE est `applied_stat_mods(stats_ctx)` (elle a besoin du `StatsComponent.ctx`
    du porteur : niveau d'ability actif, multiplier de rarete, part INITIAL d'un autre stat) ; la forme
    de BASE est le couple `get_stat_modification_stat`/`get_stat_modification_amount`. L'override PRIME
    exactement comme cote natif (un `ApplyModification` surcharge remplace celui de la base) — c'est ce
    qui evite le DOUBLE-COMPTE des effets qui declarent les deux (`AnvilShield_FrozenAttackerAdvantage`,
    dont `applied_stat_mods` delegue justement a `get_stat_modification_amount`).

    `stats_ctx = None` (appelant sans ctx du porteur) -> seule la forme de BASE est lisible ; les
    magnitudes contextuelles ne sont PAS devinees (degradation fidele, pas d'invention). Montants nuls
    filtres (mirror de la garde `if (param_3 != 0)` de
    `IdunBattle.Entities.Components.ValueModification$$Modify` : `Modify(*, 0)` est un no-op natif)."""
    if stats_ctx is not None:
        mods = eff.applied_stat_mods(stats_ctx) or []
        if mods:
            return [(int(st), int(amt)) for st, amt in mods if amt]
    st = eff.get_stat_modification_stat()
    if st is None:
        return []
    amt = eff.get_stat_modification_amount()
    return [(int(st), int(amt))] if amt else []


def effect_stat_overrides(eff) -> list:
    """Les `(StatType, valeur, isModifiable)` que l'APPLICATION de CET effet pose en **OVERRIDE** —
    point de verite UNIQUE du canal part 7/8, pendant exact d'`effect_stat_modifications` pour le
    canal additif part 5/6.

    NATIF : les DEUX canaux sont pilotes par LE MEME couple de slots d'interface. `IdunBattle.
    Operations.RefreshEffectsOperation$$ApplyEffectsForTargets` appelle `IEffect+0xe`
    (= `IdunBattle.Entities.Effects.BaseEffect$$Apply` -> `<Effect>.ApplyInternal`) et
    `...$$RevertEffectsForTargets` appelle `IEffect+0xf` (= `IdunBattle.Entities.Effects.
    BaseEffect$$Revert` -> `<Effect>.RevertInternal`) : le refresh ne connait PAS la famille de
    l'effet. Pour un `AStatModifierEffect` c'est `ApplyModification`/`RevertModification`
    (`ChangeStat` part 5|9 / part 6) ; pour un `IdunBattle.Entities.Effects.StatOverrideEffect`
    c'est `SetOverride` (part 7) / `RemoveOverride` (part 8).

    Normalise le triplet declare par `BaseEffect.applied_stat_overrides` (cf. sa docstring pour la
    provenance de chaque membre). `[]` = l'effet ne pose aucun override (la quasi-totalite)."""
    out: list = []
    for row in (eff.applied_stat_overrides() or []):
        st, val, modifiable = row
        out.append((int(st), int(val), bool(modifiable)))
    return out


def _carries_modification(eff) -> bool:
    """Le FLAG `EffectComponent.IsActive @+0x5c` de CETTE instance — l'effet porte-t-il, OUI ou NON,
    une `ValueModification` chez sa cible ?

    NATIF, lu verbatim : `IdunBattle.Operations.RefreshEffectsOperation$$ActivateEffect` écrit
    `+0x5c = 1` (et `RefreshEffect` enchaîne `UpdateEffectTargets(<cibles réelles>)` ->
    `AStatModifierEffect$$ApplyModification`), tandis que
    `IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` écrit `+0x5c = 0` PUIS
    `UpdateEffectTargets(<liste VIDE>)` -> `RevertEffectsForTargets` ->
    `AStatModifierEffect$$RevertModification`. Un effet à `+0x5c == 0` n'a donc AUCUNE entrée
    `ValueModification.per_source` sur sa cible.

    Défaut `True` : le canal `decisionView` par DÉFAUT droppe les inertes (« présent == actif »),
    donc une entrée sans clé `active` EST active. Seul le canal `includeInactive` publie
    `active: false`, et c'est exactement cette entrée qu'il ne faut PAS attribuer."""
    return bool(getattr(eff, "active", True))


def stat_overrides_by_stat(effects) -> dict:
    """Overrides poses par les effets ACTIFS, groupes `{idxStatType: (valeur, isModifiable)}` — a
    passer a `stats.seed_unit_stats(overrides=...)`. Pendant OVERRIDE (part 7) de
    `stat_modifications_by_source` (part 5|9).

    MEME regle d'activite (`_carries_modification`, cf. sa docstring) : `IdunBattle.Operations.
    RefreshEffectsOperation$$DeactivateEffect` ecrit `EffectComponent.IsActive @+0x5c = 0` PUIS
    `UpdateEffectTargets([])` -> `RevertEffectsForTargets` -> `IdunBattle.Entities.Effects.
    StatOverrideEffect$$RevertInternal` = `RemoveOverride`. Un effet a `+0x5c == 0` n'a donc AUCUN
    override pose chez sa cible, exactement comme il n'a aucune `ValueModification`.

    Keye par STAT et non par SOURCE, et le dernier effet balaye gagne : cote natif il n'y a qu'UN
    slot `IdunBattle.Entities.Components.ValueOverride` par `StatComponent` (`+0x20`), et
    `IdunBattle.Entities.Components.ValueOverride$$SetOverride` ECRASE — un override ne cumule
    pas."""
    out: dict = {}
    for e in _as_effects(effects):
        if not _carries_modification(e):
            continue
        for st, val, modifiable in effect_stat_overrides(e):
            out[int(st)] = (int(val), bool(modifiable))
    return out


def stat_modifications_by_source(effects, source_of=None, stats_ctx=None) -> dict:
    """Contributions stat-mod des effets ACTIFS, groupées `{idxStatType: {source: amount}}` — à passer à
    `stats.seed_unit_stats(attributed=...)` pour une modification **attribuée** (résidu opaque réduit).
    Mirror de l'agrégation `AStatModifierEffect.ApplyModification` par (stat, source).
    `source_of(effect) -> clé de source` (défaut : tuple stable `("statmod", effect_type, source, name)`).

    `stats_ctx` = le `UnitContext`/`StatsComponent.ctx` du PORTEUR (R16) : il débloque la forme OVERRIDE
    d'`ApplyModification` (`applied_stat_mods`), dont la magnitude se lit justement sur ce ctx. Sans lui,
    seule la forme mono-stat de la base est attribuée et la contribution des effets à magnitude
    contextuelle reste dans le résidu opaque `CAPTURED_SOURCE` — donc NON RETIRABLE à leur retrait.
    No-op pour les effets non-StatModifier (cf. `effect_stat_modifications`).

    ⚠ « ACTIFS » n'était PAS implémenté avant #366-r1 : le filtre `_carries_modification` manquait,
    donc un effet capté INERTE par le canal `includeInactive` (`active: false`) se voyait attribuer
    une magnitude que le natif n'applique PAS -> `seed_unit_stats` compensait par un résidu NÉGATIF
    sous `CAPTURED_SOURCE`, et le premier `refresh_stat_modifier_effects` (qui retire la part
    attribuée, à raison) laissait le résidu négatif SEUL. MESURÉ (runner MC1_67, summon
    `tyranSmnWarrior` à `turnsStarted` impair, effet `1108 ReinforcedHiveNode_ExtraArmor` capté
    `active: false`) : `FixedArmor` port **0** contre live **1595**. Le trou concerne TOUTE classe
    à `CreateActiveCondition` portée qui déclare un stat-mod (17 au 2026-08-01) ; il n'était
    inobservable que parce qu'aucune n'avait encore été captée INERTE dans un test."""
    out: dict = {}
    for e in _as_effects(effects):
        if not _carries_modification(e):
            continue
        mods = effect_stat_modifications(e, stats_ctx)
        if not mods:
            continue
        src = source_of(e) if source_of else statmod_source_key(e)
        for st, amt in mods:
            d = out.setdefault(int(st), {})
            d[src] = d.get(src, 0) + int(amt)
    return out


def apply_effect_stat_modifications(unit_stats, effects, source_of=None, stats_ctx=None) -> list:
    """Applique sur `unit_stats` (`UnitStats`) les stat-modifications des effets actifs, attribuées à la
    source de chaque effet — mirror de `IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification (émet un `ChangeStat` sur la **modification** du stat, part 5/9). Réciproque =
    `unit_stats.revert_stat` (`IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification, part 6).

    `source_of(effect) -> clé de source` (défaut : tuple stable `("statmod", effect_type, source,
    name)`) sert au revert par-source ; `stats_ctx` = ctx du porteur (débloque la forme OVERRIDE, cf.
    `effect_stat_modifications`). No-op pour les effets non-StatModifier. Renvoie la liste des
    `(source, statType, amount)` appliqués (pour un revert ultérieur exact ou une validation
    d'attribution vs `statDelta`).

    MÊME filtre `_carries_modification` que `stat_modifications_by_source` (cf. sa docstring) : un
    effet à `EffectComponent.IsActive @+0x5c == 0` n'a AUCUNE `ValueModification` chez sa cible."""
    applied = []
    for e in _as_effects(effects):
        if not _carries_modification(e):
            continue
        src = source_of(e) if source_of else statmod_source_key(e)
        for st, amt in effect_stat_modifications(e, stats_ctx):
            unit_stats.change_stat(int(st), src, int(amt))
            applied.append((src, int(st), int(amt)))
    return applied
