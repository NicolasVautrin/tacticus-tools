"""Effets du namespace natif `IdunBattle.Entities.Effects.Loki` — 1 classe par effet (VA citée).

Chaque classe override UNIQUEMENT ce qu'elle implémente dans le natif (lu en ghidra). Les magnitudes
non encore confirmées par nom gameconfig renvoient None (pas de contribution) = on N'INVENTE PAS de
valeur non prouvée (cf. doc §17.4 « présent ≠ appliqué »). RapidAssault = seul cas magnitude validé.
"""
from __future__ import annotations

from collections.abc import Mapping

from ...services.effect_bonus import EffectBonus, for_addition, for_percent_decrease, for_percent_increase
from .base import BaseEffect, SubEffectSpec, SAME_TURNS
from .magnitude import ability_var, global_value, trait_var


class RapidAssaultExtraDamageEffect(BaseEffect):
    """`RapidAssault_ExtraDamageEffect` (effet 0x4cd=1229).
    - dégât @180f67940 : `ForPercentIncrease(ConfigConst key 0xf)` = trait var `rapidAssaultExtraDmgPct` (=25, scalaire).
    - cycle de vie : posé à l'init d'ability (`RapidAssaultAbility.CreateBehaviour` @181224950 `AddEffect(0x4cd)`),
      RETIRÉ en fin de tour si l'unité a attaqué (`RemoveExtraDamageEffectAbility.CreateTrigger` @181224af0 =
      `On(0x17) & UnitsAttackedThisTurn>0 & HasEffect(0x4cd)`).
    VALIDÉ live : +25% → u94→u84 3012-4524 EXACT."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None) -> EffectBonus | None:
        pct = trait_var("RapidAssault", "rapidAssaultExtraDmgPct")
        return for_percent_increase(True, pct) if pct is not None else None

    @property
    def removed_after_attack(self) -> bool:
        return True


class HeavyWeaponExtraDmgEffect(BaseEffect):
    """`HeavyWeapon_ExtraDmgEffect` (effet 1008 ; ctor `DamageModifierAbilityEffect(0x3e9)`).
    - dégât `CreateDamageModifier` @180f4f030 : `EffectBonus.ForPercentIncrease(cond, amount)` où
      `amount = ConditionalAmount(TriggeringAbilityIs(0x3ec) ? amount×2 : amount)`, `amount = ConfigConst
      key 0xf` = trait var `heavyWeaponExtraDmg` (=25, scalaire) ; condition = `OwnerIsCaster &
      IsRangedAttack & flags`. ⇒ **+25% de dégât sur les attaques RANGED** (le ×2 si l'ability
      déclenchante est 0x3ec = raffinement non porté ; l'attaque normale/overwatch n'est pas 0x3ec).
    Porté par le trait HeavyWeapon (qui accorde aussi l'Overwatch) → s'applique au tir d'overwatch."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None) -> EffectBonus | None:
        if not is_ranged:                        # gated IsRangedAttack (no-op sur mêlée / contexte inconnu)
            return None
        # Gate NO-MOVE (`!HasFlag(HasMoved=0)` @180f4f030 ; i2 : « When this unit has not moved this
        # turn »). En PRÉDICTION la tuile candidate fixe le flag : has_moved=True (candidat avec
        # déplacement) → pas de bonus (GROUND TRUTH step-23 : rangées ranged u78 SANS ×1.25 depuis les
        # tuiles déplacées ; step-11 : « ×1.25 selon tuile »). None (combat runner, état non tracé) →
        # comportement historique conservé (bonus appliqué).
        if has_moved:
            return None
        pct = trait_var("HeavyWeapon", "heavyWeaponExtraDmg")
        return for_percent_increase(True, pct) if pct is not None else None


class RangedSpecialistEffect(BaseEffect):
    """`RangedSpecialistEffect` (trait RangedSpecialist — i2 : « If this unit did not start its turn
    adjacent to an enemy unit, it deals +33% Damage with ranged attacks »).
    - dégât @180f67520 : `EffectBonus.ForPercentIncrease((OwnerIsCaster & IsRangedAttack &
      !TriggeringAbilityIs(0x434)) | (branche 0x434 overwatch), Get(ConfigConst 0xf))` =
      **+rangedSpecialistDmgPct% sur les attaques RANGED** (toutes tuiles — la condition « pas parti
      adjacent » est l'état ACTIF de l'effet, reflété par la capture isActive, PAS un gate de tuile).
    MAGNITUDE : `traitVariables.rangedSpecialistDmgPct` = 33. GROUND TRUTH step-8 seed777 :
    u80→u94 ranged natif = moteur ×1.33 exact (per-coup 534 = round(401×1.33)), mêlée intacte."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None) -> EffectBonus | None:
        if not is_ranged:                        # gated IsRangedAttack (@180f67520)
            return None
        pct = trait_var("RangedSpecialist", "rangedSpecialistDmgPct")
        return for_percent_increase(True, pct) if pct is not None else None


class TerrifyingExtraDefenseEffect(BaseEffect):
    """`Terrifying_ExtraDefense_Effect.CreateDamageModifier` @180f47ba0 : réduit le dégât MÊLÉE reçu par
    son PORTEUR (l'effet est sur la CIBLE). Trigger natif = `OwnerIsTarget & IsMeleeAttack` (AbilityOrEffect
    0x62) ; valeur = `ConfigConst(0x28)`. La valeur n'est PAS exposée par gameconfig (trait/effet Terrifying
    = variables vides) ; magnitude **30 confirmée LIVE** (scorer ×0.70 sur eldarMauganRa, seed777 step22).
    ⇒ malus défenseur `PercentDecrease(30)` gated `IsMeleeAttack` (no-op sur attaque ranged / contexte inconnu)."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None) -> EffectBonus | None:
        if not is_melee:                         # gated IsMeleeAttack
            return None
        return for_percent_decrease(False, 30)   # owner_is_caster=False (l'effet est sur le défenseur)


_TERMINATOR_EXCLUDED: "frozenset[str] | None" = None


def _terminator_excluded_profiles() -> "frozenset[str]":
    """Profils de dégât PERÇANT le TerminatorArmour (`terminatorArmourExcludedDmgProfiles` du trait,
    = "Psychic,DirectDamage") → set de noms. Lu une fois en gameconfig, mis en cache."""
    global _TERMINATOR_EXCLUDED
    if _TERMINATOR_EXCLUDED is None:
        raw = ""
        try:
            import gameconfig as _GC
            raw = ((_GC.trait("TerminatorArmour") or {}).get("variables") or {}).get(
                "terminatorArmourExcludedDmgProfiles") or ""
        except Exception:
            raw = ""
        _TERMINATOR_EXCLUDED = frozenset(p.strip() for p in raw.split(",") if p.strip())
    return _TERMINATOR_EXCLUDED


class TerminatorArmourReduceDmgEffect(BaseEffect):
    """`TerminatorArmour_ReduceDmg_Effect.CreateEffectDamageMalusForDefense` @180f70f80 : réduit de
    `terminatorArmourDmgReduction`% (=-75) le dégât reçu par son PORTEUR, SAUF si le profil de dégât de
    l'attaque figure dans `terminatorArmourExcludedDmgProfiles` (=Psychic,DirectDamage). Trigger natif =
    `OwnerIsTarget & NOT DamageProfileIs(excludedArray)` (ConfigConst 0x4c=reduction, 0x52=array via
    `EffectBonus.ForPercentIncrease`) — NON gated mêlée (≠ Terrifying, s'applique mêlée ET ranged).
    Valeurs LUES en gameconfig (trait TerminatorArmour), -75% confirmé LIVE (u96 encaisse 904 vs u94 3616,
    même attaquant → ratio 0.25 = -75%)."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None) -> EffectBonus | None:
        red = trait_var("TerminatorArmour", "terminatorArmourDmgReduction")   # -75 (magnitude 75)
        if not red:
            return None
        if damage_profile and damage_profile in _terminator_excluded_profiles():
            return None                                     # profil perçant (Psychic/DirectDamage) → pas de réduction
        return for_percent_decrease(False, abs(int(red)))   # owner=défenseur (l'effet est sur la cible)


class FightingRetreatDmgReductionEffect(BaseEffect):
    """`FightingRetreat_DamageReductionEffect` (effet 1157 `FightingRetreatDmgReduction`) — debuff posé
    par FightingRetreat (Darkstrider) sur les ennemis adjacents (« deal -582 Damage for one round »).
    - dégât @180f493a0 : `EffectBonus.ForAddition(OwnerIsCaster, Multiply(ConfigVar(0x12=dmgReduction),
      MinusOne))` = **-dmgReduction PLAT** sur les attaques du PORTEUR (additif, PAS un pct).
      `dmgReduction` = variable par niveau (lvl65=582), flaggée `variablesAffectedByRarityBonus`.
    ⚠ Niveau/multiplier fidèles = ceux du CASTER SOURCE (Darkstrider, abilityState de l'effet), non
      captés pour un debuff d'origine ennemie → fallback niveau/multiplier du PORTEUR (approximation
      documentée ; identique en pratique sur rosters au même palier)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None) -> EffectBonus | None:
        lvl = self.ability_level if self.ability_level is not None else self.level
        v = ability_var("FightingRetreat", "dmgReduction", lvl,
                        multiplier_pct=self.ability_variables_multiplier)
        return for_addition(True, -int(v)) if v else None


class FightingRetreatHitReductionEffect(BaseEffect):
    """`FightingRetreat_HitReductionEffect` (effet 1158 `FightingRetreatHitReduction`) — même debuff,
    axe COUPS (« They also have 1 fewer hits, to a minimum of one »).
    - hits @180f495d0 : `EffectBonus.ForAdditionWithMinimum(OwnerIsCaster, Multiply(MinusOne,
      ConfigConst(0x2c=hitsReduction=1)), min=Direct(1))` = **-1 coup, PLANCHER 1**. Le plancher est
      appliqué chez les consommateurs de hits (`max(1, …)`, cf. predict_validate)."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True) -> EffectBonus | None:
        # trigger natif = OwnerIsCaster SEUL (@180f495d0, pas de IsNormalAttack) -> TOUTES les attaques.
        n = ability_var("FightingRetreat", "hitsReduction", is_constant=True)   # ConfigConst 0x2c (=1)
        return for_addition(True, -int(n)) if n else None


class LightCoverEffect(BaseEffect):
    """`LightCoverEffect` — couverture légère (effet de TUILE posé par `LightCoverAbility`
    Abilities.Tiles.Loki, `UnitsThatNeedEffect` @1811c1830 = unités SUR les tuiles de couverture).
    - hits @180f556b0 : `EffectBonus.ForAdditionWithMinimum(OwnerIsTarget(tuiles égales) &
      !IsMeleeAttack, -ConfigConst(0x2c=hitsReduction), min=Direct(1))` = **-hitsReduction coups
      sur les attaques NON-mêlée reçues par le porteur, plancher 1**.
    MAGNITUDE : `globalValues.lightCoverHitReduction` = 2 (LightCoverAbility = ability de TUILE,
    absente de `units.abilities` — sa config vit dans les valeurs globales).
    GROUND TRUTH step-13 seed777 (trace AllMods, u90→u84 porteur LightCover) : ranged 4→2 coups
    partout, mêlée dist 1 → 4 coups (gate !IsMeleeAttack) — natif dMin/dMax reproduits exacts."""

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None) -> EffectBonus | None:
        if is_melee:                        # trigger natif = !IsMeleeAttack (@180f556b0)
            return None
        n = global_value("lightCoverHitReduction")   # miroir du ConfigConst 0x2c (=2)
        return for_addition(True, -int(n)) if n else None


class ParryEffect(BaseEffect):
    """`ParryEffect` (effet `Parry_ReduceHits`, trait Parry — i2 : « reduces incoming melee multi-hit
    attacks by 1 hit, to a minimum of 1 »).
    - hits @180f5d860 : `EffectBonus.ForAdditionWithMinimum(OwnerIsTarget & IsMeleeAttack,
      -ConfigConst(0x2c=hitsReduction), min=Direct(1))` = **-1 coup MÊLÉE reçu, plancher 1**
      (jumeau mêlée de LightCover). MAGNITUDE : `traitVariables.parryHitReduction` = 1.
    GROUND TRUTH step-6 seed777 (trace AllMods, u86→u94 porteur Parry) : mêlée dist 1 = 4 coups
    vs ranged = 5 (base 3 + PowerTrip 1 + MasterAnnihilator 1) — natif reproduit exact."""

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None) -> EffectBonus | None:
        if not is_melee:                    # trigger natif = IsMeleeAttack (@180f5d860)
            return None
        n = trait_var("Parry", "parryHitReduction")  # miroir du ConfigConst 0x2c (=1)
        return for_addition(True, -int(n)) if n else None


class MasterAnnihilatorAdditionalHitEffect(BaseEffect):
    """`MasterAnnihilator_AdditionalHitEffect` (effet `MasterAnnihilator_extraHit` — DEBUFF posé par
    Vitruvius sur SA cible d'attaque normale ; i2 : « Attacks by any friendly unit against the
    affected enemy score an additional hit, except attacks that deal Psychic Damage »).
    - hits @180f58d50 : `EffectAdditionalHits.Create(OwnerIsTarget & !AreEqual(
      CurrentAttackDamageProfile, 0xd=Psychic), count=ConfigConst(0x2f nrOfHits=1),
      dmg=FirstHitInCurrentAttackDamageRange capé ConfigVar(0xd maxDmg))` = **+1 coup reçu par le
      porteur (attaques non-Psychic)**. Les attaquants = ennemis du porteur = alliés du poseur (le
      gate « friendly unit » de l'i2 est structurel, pas dans le trigger).
    ⚠ CAP du coup bonus (dmg <= maxDmg[lvl] ex. 5456) non modélisé (per-coup observé << cap) — TODO.
    GROUND TRUTH step-6 seed777 : u86→u94 ranged = 5 coups (3 arme + 1 PowerTrip + 1 MA) vs 4 sur
    les cibles non marquées (88/96)."""

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None) -> EffectBonus | None:
        if damage_profile == "Psychic":     # !AreEqual(profil, 0xd=Psychic) (@180f58d50)
            return None
        n = ability_var("MasterAnnihilator", "nrOfHits", is_constant=True)   # ConfigConst 0x2f (=1)
        return for_addition(True, int(n)) if n else None


class BigTargetAdjacentEffect(BaseEffect):
    """`BigTargetAdjacentEffect` — AURA du trait BigTarget (i2 : « Adjacent friendly units receive
    -1 hit from ranged attacks, to a minimum of 1 »). L'effet est POSSÉDÉ par le porteur BigTarget
    (capté dans SA liste d'effets) ; ses bénéficiaires = les ALLIÉS ring-1 HEX désignés dynamiquement
    (TargetSelector @180f33c70, refresh @180f33ce0) — PAS le porteur lui-même (GROUND TRUTH step-13
    seed777 : u86 porteur = 4 coups pleins ; u80 allié adjacent = 3 coups).
    - hits @180f33ac0 : `ForAdditionWithMinimum(OwnerIsTarget & IsRangedAttack, Direct(-1),
      min=Direct(1))` — valeur -1 codée dans le natif (pas de config).
    Canal AURA (le porteur n'est pas la cible de l'attaque) : ctx fourni par l'agrégateur
    `aura_hits_malus_for_defense` = {owner_id/pos/team, tgt_id, t_pos, tgt_team, is_melee}."""

    def create_aura_hits_malus_for_defense(self, ctx: Mapping | None = None) -> EffectBonus | None:
        c = ctx or {}
        if c.get("is_melee") or c.get("owner_id") == c.get("tgt_id"):
            return None
        if c.get("owner_team") is None or c.get("owner_team") != c.get("tgt_team"):
            return None                     # bénéficiaires = alliés du porteur uniquement
        op, tp = c.get("owner_pos"), c.get("t_pos")
        if not op or not tp:
            return None
        import hexgeo                       # ring-1 HEX (parité validée vs boardGraph)
        if hexgeo.distance(op, tp) != 1:
            return None
        return for_addition(True, -1)       # Direct(-1) @180f33ac0


class PowerTripFullHealthEffect(BaseEffect):
    """`PowerTrip_FullHealthEffect` — axe COUPS (hits), actif SSI PV pleins.
    - hits @180f64cf0 : `ForAddition(ConfigConst key 0x2b)` = constante `extraHit` de l'ability PowerTrip (=1).
    - condition @180f64cb0 : `!IsDamaged` (hp == max).
    MAGNITUDE résolue : `gameconfig.ability('PowerTrip').constants['extraHit']` = 1 → +1 coup quand PV pleins."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True) -> EffectBonus | None:
        # trigger natif @180f64cf0 = `IsNormalAttack & OwnerIsCaster` -> ATTAQUE NORMALE SEULEMENT
        # (l'appliquer aux spéciales sur-prédisait DakkaDakkaDakka -> régression steps 6/13).
        if not is_normal_attack:
            return None
        n = ability_var("PowerTrip", "extraHit", is_constant=True)   # key 0x2b → constante extraHit (=1)
        return for_addition(True, n) if n else None

    def is_active(self, unit_state: Mapping | None = None) -> bool:
        s = unit_state or {}
        hp, mx = s.get("hp"), s.get("max_hp")
        if hp is None or mx is None:        # max_hp non capté → ne pas masquer l'effet à tort
            return True
        return hp >= mx


class PowerTripIgnoreArmorEffect(BaseEffect):
    """`PowerTrip_IgnoreArmorEffect` — « Normal attacks ignore X Armour » = axe PÉNÉTRATION.
    ⚠ Le natif `PowerTrip_IgnoreArmorEffect.CreateEffectDamageBonusForAttack` @180f64fa0 = NO-OP
    (EffectBonus condition-seule, valeur 0) ; la pénétration est en fait bâtie DIRECTEMENT dans
    `CalculateAttackerModifiersForPrediction` @181000590 (lit la config PowerTrip de l'attaquant), pas
    portée par l'effet — pattern d'exploitation directe (cf. §17.17). On l'attribue ICI (l'effet
    représente la présence de PowerTrip ⇒ sa présence GATE correctement la pénétration : normal attack,
    owner=caster). Magnitude = `armorIgnored[level] × AbilityVariablesMultiplierPercentage/100` arrondi
    (§17.21, var flaggée `variablesAffectedByRarityBonus`). VÉRIFIÉ live u90 : 277 × 1.8 = round(498.6)
    = 499 = pénétration @0x28 attaquant ⇒ per-bout u90→u86 [341,1265], ×6 = oracle [2048,7592].
    `armorReduction` (full-health) = axe SÉPARÉ (debuff stateful de la stat FixedArmor cible, hors
    prédiction — la prédiction lit l'armure courante) → non porté ici (cf. PowerTrip_OnAttackAbility)."""

    def get_armor_penetration(self, is_normal_attack: bool = True) -> int | None:
        # Gate ATTAQUE NORMALE (i2 : « Normal attacks ignore X Armour ») — GROUND TRUTH step-13 :
        # DakkaDakkaDakka (spéciale, même porteur u90) per-coup natif 404/728 vs 78 = armure PLEINE
        # (2208), la pénétration 499 ne s'applique qu'au normal (per-coup 416/1598).
        if not is_normal_attack:
            return None
        # armorIgnored indexé par le niveau de l'ABILITY (passive, =50), PAS le stack level (=1), scalé par
        # le multiplier de l'unité. `ability_level` seedé depuis l'unité ; fallback `level` si absent.
        lvl = self.ability_level if self.ability_level is not None else self.level
        return ability_var("PowerTrip", "armorIgnored", lvl,
                           multiplier_pct=self.ability_variables_multiplier)


class StunnedEffect(BaseEffect):
    """`StunnedEffect` (effet COMPOSITE 0x48a=1162) — `ApplyInternal` @180f6eb30 spawne 3 SOUS-effets
    quand Stunned est appliqué (confirmé live : parent rem=1 + enfants 1165 rem=1, 1166/1167 rem=0) :
      - `AddBlockAbilitiesSubEffect` @180f6e870 → 0x48d=1165 Stunned_CantUseAbility, via
        `AddSubEffectWithSameTurns` ⇒ MÊME durée que le parent.
      - `ApplyMovementModifier` @180f6ef30 → 0x48e=1166 Stunned_MovementOverride, via
        `AddStatOverrideEffect` (durée 0 = permanent/lié au parent) ; gardé par `StatAmount(movement)>0`
        côté natif (simplification ici : toujours spawné — la quasi-totalité des units ont movement>0 ;
        reverté par `ResetMovementModifier`).
      - `ApplyDamageModifier` @180f6e9b0 → 0x48f=1167 Stunned_DamageModifier, via `AddEffect(turns=0)`
        (permanent/lié au parent ; reverté par `ResetDamageModifier`).
    Les enfants portent `parent_type=1162` (lien `ParentEffect@+0x70`) ; ils n'ont pas eux-mêmes de
    sous-effets. VALIDÉ live (templSwordBrother/ThunderousAssault → tyranTyrantGuard)."""

    def sub_effects_on_apply(self) -> list[SubEffectSpec]:
        return [
            SubEffectSpec(0x48d, "Stunned_CantUseAbility", turns=SAME_TURNS),  # AddSubEffectWithSameTurns
            SubEffectSpec(0x48e, "Stunned_MovementOverride", turns=0),         # AddStatOverrideEffect (cond. mvt>0)
            SubEffectSpec(0x48f, "Stunned_DamageModifier", turns=0),           # AddEffect turns=0
        ]


class ActOfFaithBuffEffect(BaseEffect):
    """`ActOfFaithBuffEffect` (effet 0x3f9=1017, namespace `Effects.Loki`) — buff de crit empilable du
    trait ActOfFaith (Adepta Sororitas).

    C'est un effet **StatModification** (mute GetStat), PAS un modifier calc-time :
      - `ApplyModification` @180f302f0 : deux `ChangeStat` sur le porteur —
          crit-chance (`Position(9,5)`)  += `actOfFaithExtraCritChance` (=10) **FLAT** (la valeur
            observable get_CurrentValue plafonne à 100 via GetClampedValue) ;
          crit-damage (`Position(10,5)`) += `Ceiling(GetStat(10=critDmg, part=3) × actOfFaithExtraCritDmgPct%
            =25%)` où `part=3` = la stat de **BASE** (StatComponent.GetStatPart@180fa8bb0 → offset 0x48, SANS
            modifications) ⇒ boost **FLAT** sur la crit-dmg hors-ActOfFaith (PAS compound). Confirmé live :
            3 stacks base 250 → +63 plat à chaque fois (250->313->376->439).
      - `RevertInternal` @180f306e0 : annule les deux ChangeStat (delta natif stocké @+0xb8).

    Posé par `ActOfFaithAbility` (trigger mort/kill d'allié Imperial), retiré — TOUS les stacks — par
    `ActOfFaith_RemoveEffectAbility` au crit du porteur. La mutation de stat est faite par le TRIGGER
    (`operations.triggers`), PAS ici : ctx.crit_chance/crit_damage sont déjà effet-inclusifs (GetStat) →
    ne PAS contribuer aux hooks calc-time crit (sinon double-compte). Cette classe ne porte que les DELTAS
    appliqués par CE stack (`cc_delta`/`cd_delta`), pour un revert exact (l'addition compound est
    ordre-dépendante à l'aller, mais le revert = simple soustraction des deltas stockés, donc exact).

    ⚠ Un stack SEEDÉ depuis un snapshot live (déjà fondu dans ctx) ne connaît pas ses deltas (0 par
    défaut) : un reset de stacks seedés ne re-baisse pas la stat. Le chemin VALIDÉ accumule depuis 0
    (deltas exacts) ; le seeding mid-accumulation est un edge case documenté."""
    cc_delta: int = 0   # delta crit-chance appliqué par CE stack (revert exact)
    cd_delta: int = 0   # delta crit-damage appliqué par CE stack (revert exact)


class KanOpenerEffect(BaseEffect):
    """`KanOpenerEffect` (triggered) — `IgnoreArmor` @180f65100 = `ConfigVar(key 0x40)` = pénétration
    d'armure per-niveau (axe armure, contrairement à PowerTrip dont la réduction est stateful on-attack).
    ⚠ KillaKan n'a PAS KanOpener (kit = PowerTrip) ; clé 0x40 → nom var gameconfig non résolu pour les
    unités qui l'ont → pénétration None tant qu'inconnue (à mapper quand on porte une unité KanOpener)."""

    def get_armor_penetration(self, is_normal_attack: bool = True) -> int | None:
        # TODO: mapper la clé 0x40 → var gameconfig (per-niveau) puis return ability_var(..., self.level).
        return None


class TauntedEffect(BaseEffect):
    """`TauntedEffect.ApplyInternal` @180f47510 (effet COMPOSITE 27 = `Taunted_OnlySpecificTargets`,
    base `ABondEffect` — lien cible↔tauntant). À l'application, spawne 3 SOUS-effets via
    `AddSubEffectWithSameTurns` (⇒ MÊME durée que le parent) :
      - 0x19=25  `Taunted_BlockMovement`        (la cible ne peut plus se déplacer)
      - 0x1a=26  `Taunted_CantUseAbility`        (la cible ne peut plus utiliser d'ability active)
      - 0x4d5=1237 `Taunted_RefreshUnitTurnFinished`
    Le natif enregistre aussi le `BondedEntityId` (la cible est forcée d'attaquer le tauntant) — c'est un
    effet de CIBLAGE IA (concern playbook, non porté ici : on matérialise l'effet + ses enfants ; le
    `source` de l'effet = le tauntant capture la direction du bond). VALIDÉ live attendu : la cible porte
    27 + 25/26/1237 (parent 1 round, enfants same-turns) après CrushingClaws."""

    def sub_effects_on_apply(self) -> list[SubEffectSpec]:
        return [
            SubEffectSpec(0x19, "Taunted_BlockMovement", turns=SAME_TURNS),      # AddSubEffectWithSameTurns
            SubEffectSpec(0x1a, "Taunted_CantUseAbility", turns=SAME_TURNS),     # AddSubEffectWithSameTurns
            SubEffectSpec(0x4d5, "Taunted_RefreshUnitTurnFinished", turns=SAME_TURNS),
        ]


class PinnedEffect(BaseEffect):
    """`PinnedEffect.ApplyInternal` @180f5e6d0 (effet 1065 `Pinned` ; UI = « Suppressed »). Effet
    stat-mod SIMPLE (pas de sous-effet nommé) : un `ChangeStat(Position(1,5), statType=4 = Movement,
    valeur = Negative(EffectConfig(1)))` sur la cible ⇒ réduit le MOUVEMENT (la cible « pinned » ne peut
    pas avancer le tour suivant).

    ⚠ Contributions NON encore portées (présent ≠ appliqué, §17.4) : (1) la réduction de Movement (le
    mouvement n'est pas dans le chemin de combat/dégât porté) ; (2) `PinnedEffect.CreateEffectDamageBonusForAttack`
    @180f5e8e0 (malus de dégât quand l'unité Pinned attaque) — à RE + porter si on modélise le débuff
    offensif. Ici on MATÉRIALISE l'effet (nom 1065 sur la cible) — c'est le scope de la tranche EFFETS."""
