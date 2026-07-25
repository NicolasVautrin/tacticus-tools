"""Effets `Effects.Loki` — famille STATUT / COMPOSITE / STAT-MOD : effets qui mutent une stat
(`get_stat_modification_*`, HP-floor, ActOfFaith crit), les composites qui spawnent des sous-effets
(`sub_effects_on_apply` : Stunned, Taunted) et les modificateurs multi-axes (BlessingsOfKhorne).
1 classe par effet natif (VA citée). Cf. `loki/__init__.py`."""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import (EffectBonus, for_addition, for_subtraction,
                                       for_percent_decrease, for_percent_increase,
                                       for_percent_subtraction_capped)
from ..base import BaseEffect, SubEffectSpec, SAME_TURNS
from ..magnitude import ability_var, bc_effect_config, global_value, trait_var


class HypersensoryMinimalHealthEffect(BaseEffect):
    """`HypersensoryAbilities_MinimalHealthEffect` (Effects.Idun, effet 0x564=1380 ; IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$.ctor).

    HP-FLOOR passif de Judh (genesJudh). i2 : « The first time each enemy turn that Judh is attacked, she
    cannot fall below 50% of her current Health. » Posé sur le porteur à l'init de l'ability passive
    `HypersensoryAbilities` (owner-effect `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypersensoryAbilitiesAbility$$CreateBehaviour = `AddEffect(0x564, owner)`).

    - `IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$ApplyInternal : `floor = Min(Round(GetStat(Health,Current) x hpPct/100), current-1)` ->
      `HealthComponent.MinimalHealth @+0x1c` (Nullable). SNAPSHOT du HP COURANT au moment de l'Apply.
    - `IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$RevertInternal : `MinimalHealth = null` (efface le plancher).
    - `IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$CreateActiveCondition : `IsEnemyTurn(owner) & Not(HasBeenAttackedAmountThisTurn(owner)>=1)`
      = actif au tour ENNEMI, la 1re attaque SEULEMENT (retiré après -> le 2e coup peut tuer).

    hpPct[L1..65] = 30..50 (var 0x26, level-indexée, NON rarity-scalée : `variablesAffectedByRarityBonus` =
    [minDmg,maxDmg] seulement). Apply/Revert (IMPÉRATIF, mute `HealthComponent`) = `MinimalHealthEffectOperation`
    côté runner (évalué par le driver `evaluate_minimal_health` aux transitions turn-start / après-attaque) ;
    cette classe porte la FORMULE du plancher + le pct config (frontière déclaratif/impératif : la condition +
    la formule ici, la mutation ECS dans l'Operation)."""

    def minimal_health_pct(self) -> "int | None":
        """`hpPct[ability_level]` (%) — var 0x26, level-indexée, NON rarity-scalée. Niveau = celui de l'ability
        PASSIVE HypersensoryAbilities (fallback stack level)."""
        lvl = self.ability_level if self.ability_level is not None else self.level
        return ability_var("HypersensoryAbilities", "hpPct", lvl)

    def compute_floor(self, current_hp: "int | None") -> "int | None":
        """`IdunBattle.Entities.Effects.Idun.HypersensoryAbilities_MinimalHealthEffect$$ApplyInternal : `Min(Round(current_hp x hpPct/100), current_hp - 1)`. None si pct absent
        ou hp<=0. `Fix64.Round` = RoundToNearest half-to-even == `round()` Python (le facteur pct/100 est exact
        en Fix64 ; l'arrondi ne joue que pour un hp impair a 50 %)."""
        pct = self.minimal_health_pct()
        if pct is None or current_hp is None or int(current_hp) <= 0:
            return None
        raw = int(round(int(current_hp) * pct / 100.0))
        return min(raw, int(current_hp) - 1)


class ContaminatedUnitEffect(BaseEffect):
    """`Contaminated_Unit` (effet 0x4dd=1245, `ContaminatedStatModifierEffect`, IdunBattle.Entities.Effects.Loki.ContaminatedStatModifierEffect$$.ctor =
    ADynamicStatModifierEffect FixedArmor) — SOUS-effet pose sur une UNITE occupant/entrant une tuile
    `Contaminated` (0x4dc), 1 round. Debuff dynamique de la stat FixedArmor (=16).

    Le NATIF calcule le montant a l'apply (`IdunBattle.Entities.Effects.ADynamicStatModifierEffect$$GetStatModificationAmount`
    -> `IdunBattle.Entities.Effects.Loki.ContaminatedStatModifierEffect$$GetDynamicStatModificationAmount` = -X% du FixedArmor courant) et l'applique via ChangeStat.
    Cote port : le vecteur tile-effect (#128, `ContaminatedTileEffect`) calcule le delta a l'apply et le stocke
    dans `self.value` -> `get_stat_modification_amount` renvoie `self.value`.

    >>> MAGNITUDE (#132 RESOLUE 2026-07-14, RE re-expert decompile) : `IdunBattle.Entities.Effects.Loki.ContaminatedStatModifierEffect$$GetDynamicStatModificationAmount` = `-BattleQuery.GetEffectConfig(EffectType=6)` (interface IBattleQuery slot 0xbe, arg 6 =
    EffectType litteral). `IdunBattle.Core.Services.BattleQuery$$GetEffectConfig` = lookup `Dict<EffectType,int>@+0xd0`
    peuple par `IdunBattle.Core.Services.BattleQuery$$InitEffectConfig` depuis `BattleConfiguration.Effect` ; l'entree EffectType=6
    (offset +0x28) = **`ContaminatedArmorReductionPct` = 30**. => -30 % du FixedArmor cible. Source = section
    `Effect` de la BC (lue, PAS hardcodee) ; le vecteur `ContaminatedTileEffect` pre-calcule le DELTA PLAT
    `value = -round(FixedArmor * 30/100)` a la pose (le stat-layer l'applique en additif). ⚠ MODE % infere
    du nom `...Pct` + magnitude (le -30 flat serait negligeable) ; le modKind exact du chemin ChangeStat
    partage (flat vs percent) et le %-de-base-vs-courant restent a CONFIRMER live (drop d'armure via
    statModSources sur un occupant contamine)."""

    def get_stat_modification_stat(self) -> int | None:
        return 16                                    # StatType.FIXED_ARMOR

    def get_stat_modification_amount(self) -> int | None:
        # Delta calcule a l'apply par le vecteur (= -round(FixedArmor_courant * X/100)) et stocke dans value.
        # None tant que X non resolu (#132) -> aucune contribution stat (mais l'effet reste PRESENT).
        return self.value


class StandVigilExtraArmorEffect(BaseEffect):
    """`StandVigil_ExtraArmorEffect` (Effects.Loki) — buff **StatModification** +armure, **SELF-buff**
    (l'unité se buffe elle-même en « stand vigil » = sans se déplacer). `IdunBattle.Entities.Effects.Loki.StandVigil_ExtraArmorEffect$$GetDynamicStatModificationAmount` = `ConfigVar(key 0x51c=1308, EffectSource, 0x1b)` = ability var
    `StandVigil.extraArmor[level]` (FLAT), ajouté à la **modification** du stat **FixedArmor** (=16) via
    `ChangeStat` (part 5/9 ; revert part 6).

    **Self-buff** ⇒ la source EST l'unité porteuse → `level` = niveau de l'ability StandVigil de l'unité
    elle-même (`self.ability_level` capté depuis unitConfig, sinon `self.level`) → magnitude EXACTE
    offline ⇒ **résidu 0 validable live** (contrairement à RitesOfBattle, buff cross-unité)."""

    def get_stat_modification_stat(self) -> int | None:
        return 16                                   # StatType.FIXED_ARMOR

    def get_stat_modification_amount(self) -> int | None:
        # StandVigil = ability ACTIVE → indexer sur activeAbilityLevel (fallback passif, puis stack level).
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        return ability_var("StandVigil", "extraArmor", lvl)


class MasterOfTheTutelariesEffect(BaseEffect):
    """`MasterOfTheTutelariesEffect` (Effects.Loki, effet 0x4ad=1197 ; IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$.ctor =
    `BaseEffect(AbilityOrEffect(0x448=1096), 1)`) — marqueur until-EoT posé sur ABRAXAS
    (thousInfernalMaster) par l'execute de l'active 1096 (`MasterOfTheTutelariesAbility.
    IdunBattleLogic.Entities.Abilities.Active.Loki.MasterOfTheTutelariesAbility$$ExecuteBehaviour` : `AddEffect(0x4ad, stateRef, caster@0x160, caster@0x160,
    durée@dsl+0xc0)`, séquencé AVANT le Spawn du Pink Horror — l'attaque immédiate du Horror
    peut donc DÉJÀ déclencher un Screamer).

    - `IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$ApplyInternal` : `AddTriggeredAbility(Entity(target), 0x495=1173,
      GetAbilityState(...))` — ARME la triggered `MasterOfTheTutelaries_SummonAbility`
      (Screamer sur attaque Psychic contre un ennemi) sur le porteur ; l'ability-state de
      1096 est propagé (le niveau des summons en dérive).
    - `IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$RevertInternal` : `RemoveTriggeredAbility(Entity(target), 0x495)` —
      désarme à l'expiration (i2 « until the end of this turn » ; durée = 1 round posée
      par l'AddEffect de l'arbre actif, aucun défaut `_DEFAULT_ROUNDS` pour 1197).

    Port runner : le trigger 1173 vit dans `EFFECT_TRIGGERS[1197]` (triggers/dispatch.py) —
    `collect_effect_triggers` n'instancie le trigger QUE tant que l'effet est ACTIF sur le
    porteur, ce qui EST le Add/RemoveTriggeredAbility natif (le natif gate d'ailleurs
    DOUBLEMENT : le `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$CreateTrigger` re-teste `HasEffect(owner, 0x4ad)`).
    Marqueur pur : aucune stat-mod."""


class BlessingsOfKhorneModifiersEffect(BaseEffect):
    """`BlessingsOfKhorne_ModifiersEffect` (EffectType 0x4ee=1262, nom capté "BlessingsOfKhorne" ;
    config-owner TriggeredAbilityType 0x4c0=1216) — trait BlessingsOfKhorne (1046), TOUTE la faction
    World Eaters (11 carriers : Azkor worldEightbound, Kharn, Wrask, Macer, + bosses LHE). DEUX
    value-modifications sur le PORTEUR, toutes deux scalées par le MÊME multiplicateur N (#185) :

    - DÉFENSE `IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$CreateEffectDamageMalusForDefense` : `(OwnerIsTarget & DamageProfileIs(0xd=
      Psychic)) -> -ConfigConst(0x4c=DmgPctReduction) x N` ⇒ le dégât PSYCHIQUE reçu par le porteur
      est réduit de `8% x N` (max -64%).
    - ATTAQUE `IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$CreateEffectDamageBonusForAttack` : `get_OwnerIsCaster` SEUL (AUCUN filtre
      profil/normal/spéciale) `-> +ConfigConst(0xf=ExtraDmgPct) x N` ⇒ TOUT le dégât sortant du
      porteur est augmenté de `3% x N` (max +24%).

    N = `IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$GetMultiplierBasedOnDefeatedInMelee` = `Min(Count(NormalUnits(UnitsDefeatedBy-
    MeleeAttack(AllUnits))) [+ TalismanOfRage self-kills], ConfigConst(0x43=MaxDefeatedUnits=8))`.
    Le compte de base est GLOBAL (unités normales des DEUX camps tuées par une attaque de MÊLÉE,
    flag `UnitComponent.DefeatedByMeleeAttack @0x178` écrit par `KillUnitOperation IdunBattle.Operations.KillUnitOperation$$Execute`,
    capté #185 dans decisionView.units). La branche self-kills (`ActorHasTriggeredAbility(owner,
    1460=TalismanOfRage)` → double-compte des kills mêlée du porteur, killer = `DeathReason.KillerId`
    capté) est INERTE-PAR-ROSTER : AUCUN unit du gameconfig courant ne porte TalismanOfRage
    (vérifié unit_map) — non codée, à activer si un carrier apparaît (killerId déjà capté).

    `melee_defeats` = compte BRUT (non cappé) seedé par `Scene._seed_battle_counters()` depuis
    `scene.melee_defeats()` (decisionView.units) ; None (runner offline sans tracking, #185
    runner-side non porté) → effet INERTE (dégradation fidèle « présent ≠ appliqué »).
    Constantes gameconfig (trait BlessingsOfKhorne) : DmgPctReduction=8, ExtraDmgPct=3,
    MaxDefeatedUnits=8 (hors rarityBonus — pas de scaling multiplier)."""

    # Compte BRUT de melee-defeats (seedé par Scene ; None = pas de source -> inerte).
    melee_defeats: "int | None" = None

    def _n(self) -> int:
        """`IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$GetMultiplierBasedOnDefeatedInMelee` : Min(count, MaxDefeatedUnits=8)."""
        if self.melee_defeats is None:
            return 0
        cap = trait_var("BlessingsOfKhorne", "blessingsOfKhorneMaxDefeatedUnits")   # ConfigConst 0x43 (=8)
        return min(int(self.melee_defeats), int(cap) if cap else 8)

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if (damage_profile or "") != "Psychic":               # DamageProfileIs(0xd) IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$CreateEffectDamageMalusForDefense
            return None
        n = self._n()
        if n <= 0:
            return None
        pct = trait_var("BlessingsOfKhorne", "blessingsOfKhorneDmgPctReduction")    # ConfigConst 0x4c (=8)
        if not pct:
            return None
        return for_percent_decrease(False, abs(int(pct)) * n)   # owner=défenseur (effet sur la cible)

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        # trigger natif IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$CreateEffectDamageBonusForAttack = get_OwnerIsCaster SEUL — tous profils, normale ET spéciale.
        n = self._n()
        if n <= 0:
            return None
        pct = trait_var("BlessingsOfKhorne", "blessingsOfKhorneExtraDmgPct")        # ConfigConst 0xf (=3)
        if not pct:
            return None
        return for_percent_increase(True, abs(int(pct)) * n)


class StunnedEffect(BaseEffect):
    """`StunnedEffect` (effet COMPOSITE 0x48a=1162) — `IdunBattle.Entities.Effects.Loki.StunnedEffect$$ApplyInternal spawne 3 SOUS-effets
    quand Stunned est appliqué (confirmé live : parent rem=1 + enfants 1165 rem=1, 1166/1167 rem=0) :
      - `IdunBattle.Entities.Effects.Loki.StunnedEffect$$AddBlockAbilitiesSubEffect → 0x48d=1165 Stunned_CantUseAbility, via
        `AddSubEffectWithSameTurns` ⇒ MÊME durée que le parent.
      - `IdunBattle.Entities.Effects.Loki.StunnedEffect$$ApplyMovementModifier → 0x48e=1166 Stunned_MovementOverride, via
        `AddStatOverrideEffect` (durée 0 = permanent/lié au parent) ; gardé par `StatAmount(movement)>0`
        côté natif (simplification ici : toujours spawné — la quasi-totalité des units ont movement>0 ;
        reverté par `ResetMovementModifier`).
      - `IdunBattle.Entities.Effects.Loki.StunnedEffect$$ApplyDamageModifier → 0x48f=1167 Stunned_DamageModifier, via `AddEffect(turns=0)`
        (permanent/lié au parent ; reverté par `ResetDamageModifier`).
    Les enfants portent `parent_type=1162` (lien `ParentEffect@+0x70`) ; ils n'ont pas eux-mêmes de
    sous-effets. VALIDÉ live (templSwordBrother/ThunderousAssault → tyranTyrantGuard)."""

    def sub_effects_on_apply(self) -> list[SubEffectSpec]:
        return [
            SubEffectSpec(0x48d, "Stunned_CantUseAbility", turns=SAME_TURNS),  # AddSubEffectWithSameTurns
            SubEffectSpec(0x48e, "Stunned_MovementOverride", turns=0),         # AddStatOverrideEffect (cond. mvt>0)
            SubEffectSpec(0x48f, "Stunned_DamageModifier", turns=0),           # AddEffect turns=0
        ]


class StunnedDamageModifierEffect(BaseEffect):
    """`Stunned_DamageModifierEffect` (enfant 0x48f=1167 du composite Stunned, posé par
    `IdunBattle.Entities.Effects.Loki.StunnedEffect$$ApplyDamageModifier` = DSL `AddEffect(0x48f)`) — le malus de DÉGÂT
    SORTANT du porteur stunné (#29 lead 2, la pièce ×0.5 du miss 777 s15).

    `IdunBattle.Entities.Effects.Loki.Stunned_DamageModifierEffect$$CreateEffectDamageMalusForDefense` : `EffectBonus.ForPercentDecrease(
    get_OwnerIsActor, EffectConfig(2))`. ⚠ Le hook natif est le SLOT DÉFENSE mais son trigger est
    **OwnerIsActor** (pas OwnerIsTarget) : le malus s'applique quand le PORTEUR est l'ACTEUR du coup
    (la boucle défense native est state-wide, le trigger route). Mapping port fidèle = la boucle
    ATTAQUANT (`create_effect_damage_bonus_for_attack`), qui n'itère que les effets de l'attaquant =
    OwnerIsActor par construction. Aucun autre gate (tous profils, normale ET spéciale, prédiction
    ET combat — le natif l'inclut dans l'oracle décision : mesuré aiPlaybookPredict s15).

    MAGNITUDE `EffectConfig(2)` = entrée BC `Effect.StunnedDmgReductionPct` (=50) — table
    `BattleConfiguration.Effect` (`EffectConfigAmount`, cf. `bc_effect_config`), PAS une var
    d'ability. VALIDÉ BIT-EXACT (777 s15, u83 admecDominus stunné -> u87 custoVexilusPraetor) :
    1607-3213 pré-mods × 0.8 (MartialKatah) × 0.5 (CE malus) × 0.34 (VexillaMagnifica) = 219-437
    == natif. Runner offline : l'enfant est matérialisé par `StunnedEffect.sub_effects_on_apply`
    -> le combat offline porte le malus dès la pose du stun (même canal)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        pct = bc_effect_config("StunnedDmgReductionPct", 50)   # EffectConfig(2) — BC Effect section
        if not pct:
            return None
        return for_percent_decrease(True, abs(int(pct)))


class ActOfFaithBuffEffect(BaseEffect):
    """`ActOfFaithBuffEffect` (effet 0x3f9=1017, namespace `Effects.Loki`) — buff de crit empilable du
    trait ActOfFaith (Adepta Sororitas).

    C'est un effet **StatModification** (mute GetStat), PAS un modifier calc-time :
      - `IdunBattle.Entities.Effects.Loki.ActOfFaithBuffEffect$$ApplyModification : deux `ChangeStat` sur le porteur —
          crit-chance (`Position(9,5)`)  += `actOfFaithExtraCritChance` (=10) **FLAT** (la valeur
            observable get_CurrentValue plafonne à 100 via GetClampedValue) ;
          crit-damage (`Position(10,5)`) += `Ceiling(GetStat(10=critDmg, part=3) × actOfFaithExtraCritDmgPct%
            =25%)` où `part=3` = la stat de **BASE** (IdunBattle.Entities.Components.StatComponent$$GetStatPart → offset 0x48, SANS
            modifications) ⇒ boost **FLAT** sur la crit-dmg hors-ActOfFaith (PAS compound). Confirmé live :
            3 stacks base 250 → +63 plat à chaque fois (250->313->376->439).
      - `IdunBattle.Entities.Effects.Loki.ActOfFaithBuffEffect$$RevertInternal : annule les deux ChangeStat (delta natif stocké @+0xb8).

    Posé par `ActOfFaithAbility` (trigger mort/kill d'allié Imperial), retiré — TOUS les stacks — par
    `ActOfFaith_RemoveEffectAbility` au crit du porteur. La mutation de stat est faite par le TRIGGER
    (`operations.triggers`), PAS ici : ctx.crit_chance/crit_damage sont déjà effet-inclusifs (GetStat) →
    ne PAS contribuer aux hooks calc-time crit (sinon double-compte). Cette classe ne porte que les DELTAS
    appliqués par CE stack (`cc_delta`/`cd_delta`), pour un revert exact (l'addition compound est
    ordre-dépendante à l'aller, mais le revert = simple soustraction des deltas stockés, donc exact).

    ⚠ Un stack SEEDÉ depuis un snapshot live (déjà fondu dans ctx) ne connaît pas ses deltas (0 par
    défaut) : un reset de stacks seedés ne re-baisse pas la stat. Le chemin VALIDÉ accumule depuis 0
    (deltas exacts) ; le seeding mid-accumulation est un edge case documenté."""
    cc_delta: int = 0   # delta crit-chance OBSERVÉ par CE stack (info/report)
    cd_delta: int = 0   # delta crit-damage OBSERVÉ par CE stack (info/report)
    stat_mod_source = None   # clé de source ChangeStat (revert par-source via UnitStats.revert_stat)
    # Cet effet applique un stat-mod FRAIS à CHAQUE pose (accumulation) → la feuille `AddEffect` /
    # `AddEffectOperation` NE doit PAS le no-op sur « déjà présent » (contrairement à Fire/Pinned/Stunned
    # updatable qui refresh). RE slice-20 (Q3) : `IsUpdatable(1017)`=TRUE par fallback, mais chaque proc
    # a une source/évènement distinct → le natif STACKE (observable live-validé : 3 stacks +63 plat chacun).
    # On reproduit l'observable additif via N instances (chacune son `stat_mod_source`), pas via le compteur
    # `UpdateExistingEffect@0x6c` (source-matching natif non porté — divergence de représentation flaggée
    # validator, observable IDENTIQUE).
    stacks_stat_mod_on_add = True

    def applied_stat_mods(self, stats_ctx) -> "list":
        """`IdunBattle.Entities.Effects.Loki.ActOfFaithBuffEffect$$ApplyModification` (part DATA côté `entities/`, mirror des DEUX
        `ChangeStat` — symétrique de `reverted_stats()`). La couche runner (`AddEffectOperation._apply_stat_mods`)
        EXÉCUTE chaque `(StatType, montant)` via `apply_change_stat`, keyé par une source unique par instance
        (revert par-source exact via la feuille `RemoveEffect`). Deux stat-mods FLAT de CE stack :
          - crit-chance (`Position(9,5)`)  += `actOfFaithExtraCritChance` (GetNumberConstant 0x30=48, =10) ;
            la valeur observable get_CurrentValue plafonne à 100 (clamp fait par `apply_change_stat`) ;
          - crit-damage (`Position(10,5)`) += `Ceiling(GetStat(critDmg, part=3=Initial) × actOfFaithExtraCritDmgPct
            (0x31=49, =25)%)` FLAT (base hors-ActOfFaith → boost PLAT, PAS compound ; live : 3 stacks +63 plat).
        `stats_ctx` = le `StatsComponent.ctx` du porteur (duck-typé : `.stats.components`/`.stats.get_stat`,
        fallback `.crit_damage` si le composant crit-dmg n'est pas seedé)."""
        from ...stats import StatType, StatPart
        cc = int(global_value("actOfFaithExtraCritChance") or 0)   # GetNumberConstant 0x30 (=10)
        cd_pct = int(global_value("actOfFaithExtraCritDmgPct") or 0)   # GetNumberConstant 0x31 (=25)
        if int(StatType.CRIT_DAMAGE) in stats_ctx.stats.components:
            base_cd = stats_ctx.stats.get_stat(int(StatType.CRIT_DAMAGE), int(StatPart.INITIAL))
        else:
            base_cd = int(getattr(stats_ctx, "crit_damage", 0) or 0)
        cd_amount = -(-(base_cd * cd_pct) // 100)                 # Ceiling(base_cd × cd_pct%) entier (0.25 exact)
        return [(int(StatType.CRIT_CHANCE), cc), (int(StatType.CRIT_DAMAGE), cd_amount)]

    def reverted_stats(self) -> "list":
        """`IdunBattle.Entities.Effects.Loki.ActOfFaithBuffEffect$$RevertInternal` annule les DEUX `ChangeStat` de CE stack :
        crit-chance (Position(9,5)) + crit-damage (Position(10,5)). Ces StatTypes sont lus par la feuille
        `RemoveEffect` (runner) pour `revert_change_stat(…, stat_mod_source)` par-source."""
        from ...stats import StatType
        return [StatType.CRIT_CHANCE, StatType.CRIT_DAMAGE]


class TauntedEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal (effet COMPOSITE 27 = `Taunted_OnlySpecificTargets`,
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
    """`IdunBattle.Entities.Effects.Loki.PinnedEffect$$ApplyInternal (effet 1065 `Pinned` ; UI = « Suppressed »). Effet
    stat-mod SIMPLE (pas de sous-effet nommé) : un `ChangeStat(Position(1,5), statType=4 = Movement,
    valeur = Negative(EffectConfig(1)))` sur la cible ⇒ réduit le MOUVEMENT (la cible « pinned » ne peut
    pas avancer le tour suivant). `EffectConfig(1)` = BC `Effect.PinnedMovementReduction` (mapping
    ordinal→champ DTO prouvé par `IdunBattle.Core.Services.BattleQuery$$InitEffectConfig` : +0x10→0, +0x14→1, +0x1c→2, ... —
    recoupé par Stunned EffectConfig(2)=StunnedDmgReductionPct bit-exact).

    MALUS DE DÉGÂT ATTAQUANT (#57b, famille ×0.70 du batch #52) : `IdunBattle.Entities.Effects.Loki.PinnedEffect$$CreateEffectDamageBonusForAttack` = `EffectBonus.ForPercentIncrease(get_OwnerIsCaster, Negative(EffectConfig(0)))` —
    quand le PORTEUR attaque, son dégât est réduit de `EffectConfig(0)` = BC
    `Effect.PinnedDmgReductionPct` (=30) ⇒ ×0.70. Trigger OwnerIsCaster == boucle ATTAQUANT du port
    (même mapping que Stunned_DamageModifier ci-dessus). Aucun autre gate (mêlée ET ranged, tous
    profils). GROUND TRUTH : 54321 s16 u81 bloodIntercessor Pinned -> t89, natif 2192/3288 =
    off 3132/4698 × 0.700 EXACT (probe_57b_x070.py).

    ⚠ Contribution NON portée restante (présent ≠ appliqué, §17.4) : la réduction de Movement
    (le mouvement n'est pas dans le chemin de combat/dégât porté)."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        pct = bc_effect_config("PinnedDmgReductionPct", 30)   # EffectConfig(0) — BC Effect section
        if not pct:
            return None
        # ForPercentIncrease(Negative(pct)) natif == percent-decrease de pct (1 - pct/100).
        return for_percent_decrease(True, abs(int(pct)))


class MV71InitialDmgEffect(BaseEffect):
    """`MV71SniperDroneSquad_InitialDmgEffect` (effet **1132=0x46c**, posé sur le DRONE par
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour` — `AddEffect(0x46c, stateRef,
    Get(drone))`, source = le CASTER Sho'syl = le PARENT du drone).

    `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$ApplyInternal` : `parent = GetParentUnit(drone)` puis `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$ApplyStat` sur
    **4 stats — 0 ATTACK, 9 CRIT_CHANCE, 10 CRIT_DAMAGE, 0x11 EXTRA_HITS** : chaque `ApplyStat` lit
    `GetStat(parent, stat, CURRENT)` (SNAPSHOT au moment de l'apply, nœud `Direct(valeur)`) et émet
    `ChangeStat(drone, Position(stat, part 7 = OVERRIDE), mode 4, Direct(valeur))` → `IdunBattle.Entities.Components.StatComponent$$ApplyModifier` case 7 → `IdunBattle.Entities.Components.ValueOverride$$SetOverride` (**modifiable** : les buffs PROPRES du drone
    continuent de s'appliquer par-dessus — i2 « uses Sho'syl's Damage stat, while other effects,
    like buffs, are taken from the Drone »). `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$RevertInternal` = `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$ResetStat`
    ×4 (part 8 = REMOVE_OVERRIDE).

    Cycle de vie : `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$CreateTargetTrigger` = `On(AttackDamageAttack=10, 1) & OwnerIsCaster`
    → l'effet est retiré (RevertInternal) dès que le DRONE porte une attaque — l'attaque COMMANDÉE du
    cast (GT §2 case-61bis : après le cast, le drone ne porte plus que RangedSpecialist). Côté port,
    la consommation+revert est exécutée par l'ability juste après l'attaque commandée (seul On(10)
    du porteur atteignable dans ce cast — collapse documenté)."""

    def overridden_stats(self) -> "list":
        from ...stats import StatType
        return [StatType.ATTACK, StatType.CRIT_CHANCE, StatType.CRIT_DAMAGE, StatType.EXTRA_HITS]


class MV71ResetInitialDmgEffect(BaseEffect):
    """`MV71SniperDroneSquad_ResetInitialDmg` (effet **1133=0x46d**, posé sur le DRONE juste APRÈS
    1132 par le même `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour` — `AddEffect(0x46d, stateRef, Get(drone))`).

    ⚠ Skew de nommage ARBITRÉ (#61bis §6) : le `.ctor` ghidra passant `0x46d` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.CyclicIonBlaster_AdditionalHitsEffect$$.ctor,
    « CyclicIonBlaster_AdditionalHitsEffect ») passe en réalité `AbilityOrEffect(TriggeredAbilityType.
    CyclicIonBlaster = 1133)` — l'ATTRIBUTION SOURCE de l'effet CyclicIonBlaster (EffectType 1148),
    PAS un EffectType. L'enum EffectType du dump (1133 = MV71SniperDroneSquad_ResetInitialDmg) est
    la bonne lecture du `AddEffect(0x46d)` de l'arbre MV71.

    Rôle : effet-compagnon du reset — retiré AVEC 1132 après l'attaque commandée du drone (GT : ni
    1132 ni 1133 présents post-cast). Aucun comportement observable propre lu dans le décompilé →
    matérialisation pure (présence + retrait), pas de contribution."""


class BlackRageExtraMoveEffect(BaseEffect):
    """`BlackRage_ExtraMove` (EffectType 0x53e=1342) — buff **StatModification** +MOUVEMENT, SELF-buff
    posé par `IdunBattleLogic.Entities.Abilities.Active.Loki.BlackRageAbility$$ExecuteBehaviour` via `AddStaticStatModifierEffect(caster@0x160,
    1342, stat=MOVEMENT(1), amount=ConfigConst(0xe=extraMovement))`. AUCUNE classe d'effet native bespoke
    (StaticStatModifierEffect générique — cf. `IdunBattleLogic.Entities.DSLFactory$$AddStaticStatModifierEffect`) : ici on porte le
    stat-mod EAGER (chemin runner `AddEffectOperation._apply_stat_mods` -> `apply_change_stat`, keyé par
    source) = +`extraMovement` (constante gameconfig = 1) à la stat MOVEMENT.

    VALIDÉ live (statModSources 31337) : movement total=1, bySource=[{source=effet 98, amount=1}]. Reverte
    MOVEMENT au retrait (`reverted_stats`, symétrique via la feuille `RemoveEffect`)."""

    def applied_stat_mods(self, stats_ctx) -> "list":
        from ...stats import StatType
        amt = ability_var("BlackRage", "extraMovement", is_constant=True)   # ConfigConst(0xe) = 1
        return [(int(StatType.MOVEMENT), int(amt))] if amt else []

    def reverted_stats(self) -> "list":
        from ...stats import StatType
        return [StatType.MOVEMENT]


class BlackRageExtraDamageEffect(BaseEffect):
    """`BlackRage_ExtraDamageEffect` (EffectType 0x53f=1343 ; `IdunBattle.Entities.Effects.Loki.BlackRage_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`)
    — posé sur le caster (self) par `ExecuteBehaviour` via `AddEffect(1343, caster@0x160)`. Le natif =
    `ForAddition((get_OwnerIsCaster & IsCharging(caster,target) & IsNormalAttack), ConfigVar(8=extraDmg))`
    = +`extraDmg[level]` au dégât de l'attaque NORMALE de CHARGE du porteur (le coup qui suit le MoveUnit du
    MÊME cast).

    MARQUEUR porté (présent/diffable) — la CONTRIBUTION +extraDmg n'est PAS modélisée (RÉSIDU documenté) :
    (a) magnitude NÉGLIGEABLE (extraDmg[L]=[10,12,14,...] vs ~3000/coup mesuré live = <0.5%) ; (b) le gate
    natif `IsCharging` (unité entrée AU CONTACT durant CE cast) n'est PAS exprimable dans le canal modifier
    EAGER sans SUR-APPLIQUER aux attaques HORS-charge du porteur (l'effet persiste remaining=0). Posé pour
    le diff structurel ; si une tranche future porte `IsCharging` (cf. FeederTendrils gate charge), brancher
    `create_effect_damage_bonus_for_attack` = ForAddition(ConfigVar(8)) gated charge."""


class BlackRageAutomaticUnitEffect(BaseEffect):
    """`BlackRage_AutomaticUnitEffect` (EffectType 0x540=1344 ; IdunBattle.Entities.Effects.Loki.BlackRage_AutomaticUnitEffect$$.ctor = `BaseEffect(AbilityOrEffect(
    0x48b=1163), 1)`) — posé sur le caster (self) par `ExecuteBehaviour` via `AddEffect(1344, caster@0x160)`.
    MARQUEUR pur (aucune stat-mod) : arme la triggered `BlackRage_ActivationAbility` (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BlackRage_ActivationAbility$$CreateTrigger`
    = `On(0x16) & HasEffect(self, 0x540)` -> `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BlackRage_ActivationAbility$$CreateBehaviour` = `PerformAIAction(self)`) = Lucien
    REJOUE une action (berserk Death Company « acts again »).

    Le mécanisme ACT-AGAIN (triggered `PerformAIAction` sur event 0x16) n'est PAS modélisé (RÉSIDU documenté,
    tranche triggered dédiée : nécessite le vecteur On(0x16) + un re-tour d'action offline) ; l'effet est posé
    pour le diff structurel (présent/diffable, remaining=0)."""


class WaaaghExtraMovementEffect(BaseEffect):
    """`Waaagh_ExtraMovement` (EffectType 0x44b=1099) -- buff **StatModification** +MOUVEMENT pose par
    `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour` via
    `AddStaticStatModifierEffect(<selecteur Waaagh>, 1099, stat=MOVEMENT(1),
                                 Direct(GetNumberConstant(0xe)=extraMovement), duree=Direct(1)@dsl+0xc0)`.
    AUCUNE classe d'effet native bespoke (StaticStatModifierEffect generique, `IdunBattleLogic.Entities.DSLFactory$$AddStaticStatModifierEffect`) : on porte le stat-mod EAGER (canal `applied_stat_mods` -> `AddEffectOperation.
    _apply_stat_mods` -> `apply_change_stat`, keye par source) = +`extraMovement` (constante gameconfig = 1)
    a la stat MOVEMENT. MEME template que `BlackRageExtraMoveEffect` (1342, valide live statModSources).

    CE PORT EST REQUIS PAR L'ETAGE MOVE de Waaagh : `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetPossibleMovementTiles`
    calcule sa portee via `IdunBattleLogic.Entities.DSLFactory$$UnitMovementRangeWithBonus(caster@0x160, 1099, Direct(extraMovement))` = `If( HasEffect(caster, 1099), StatAmount(caster, MOVEMENT), Sum(StatAmount(caster,
    MOVEMENT), bonus) )` -- le natif ANTI-DOUBLE-COMPTE : quand l'effet est DEJA pose (c'est le cas, le
    Group buff @0x25 s'execute AVANT le Group move @0x23 dans l'ordre d'`Execute` de IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour), la portee
    lit la stat MOVEMENT *deja bonifiee*. Sans `applied_stat_mods`, la charge perdrait son +1 hex."""

    def applied_stat_mods(self, stats_ctx) -> "list":
        from ...stats import StatType
        amt = ability_var("Waaagh", "extraMovement", is_constant=True)   # ConfigConst(0xe) = 1
        return [(int(StatType.MOVEMENT), int(amt))] if amt else []

    def reverted_stats(self) -> "list":
        from ...stats import StatType
        return [StatType.MOVEMENT]


class WaaaghExtraDamageEffect(BaseEffect):
    """`Waaagh_ExtraDamage` (EffectType 0x44c=1100 ; `IdunBattle.Entities.Effects.Loki.Waaagh_ExtraDamageEffect$$.ctor`
    = `BaseEffect(AbilityOrEffect(0x422=1058 Waaagh), 1)` -> sa config = celle de l'ability WAAAGH) -- pose
    sur le SELECTEUR Waaagh (caster + allies adjacents + TOUS les allies de faction Orks) par
    `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour` via
    `AddEffect(0x44c, AbilityStateReference, caster@0x160, <selecteur>, duree=Direct(1)@dsl+0xc0)`.

    CANAL PORTE (#95) -- `IdunBattle.Entities.Effects.Loki.Waaagh_ExtraDamageEffect$$CreateEffectDamageBonusForAttack`,
    MIRROR 1:1 du decompile :
        `EffectBonus.ForAddition( IsNormalAttack & IsMeleeAttack & get_OwnerIsCaster,
                                  ConfigVar(8=extraDmg, GetAbilityState(effet), effet+0x60) )`
    (ordre de lecture natif : `IsNormalAttack` puis `op_BitwiseAnd(IsMeleeAttack)` puis
    `op_BitwiseAnd(get_OwnerIsCaster)`, puis `ForAddition(cond, ConfigVar(...))`).
    => +`extraDmg[niveau Waaagh du POSEUR]` PLAT (multiplier resolu = 100, cf. plus bas), PAR COUP, sur
    les attaques **NORMALES MELEE** du porteur. `OwnerIsCaster` est vrai par construction sur ce canal (il n'est appele que pour
    les attaques du porteur, cf. `_attacker_effect_bonuses`). Canal `additive @+0x10` (`DamageModifiers.Add`)
    -- MEME canal que SmashaEad/DecoysAndMisdirection/LordOfTempests.

    NIVEAU = celui du POSEUR : `IdunBattle.Entities.Formulas.ConfigAmount$$GetAbilityState` resout le
    selecteur `AbilityStateFromEffect` (-> `EffectComponent.AbilityState` = {Owner=le Warboss,
    Ability=1058, Nullable<AbilityState> **VIDE** -- MESURE live `effectAbilityStates(1100)` :
    stateRaw=[81,1,1058,0,0,0,...]}) puis le passe au slot 0xd4 du `BattleQuery` -> l'AbilityState de
    l'ability 1058 de son OWNER. Cote port : le vecteur de pose passe `scale_from_source=True`
    (`runner/abilities/behaviours/effects.py::_source_scaling`) -> `active_ability_level` de la SOURCE.

    MULTIPLIER = **100** (aucun scaling de rarete), MESURE LIVE -- ne PAS passer celui du porteur ni
    celui du caster. `IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel`
    applique bien `Round(value x AbilityState.VariableMultiplierPercentage/100)` quand la cle est dans
    `variablesAffectedByRarityBonus` (c'est le cas d'`extraDmg`) : c'est donc le MULTIPLIER RESOLU qui
    vaut 100 ici. GROUND TRUTH (probe_95_waaagh_contrib, MC1_67 seed 31337, Warboss L50 mult 200,
    beneficiaire orksNob mult 180) : la contribution mesuree par la preview NATIVE (`aiPredict` ->
    `GetAllPredictions`) est **+443 par coup**, EXACTEMENT `extraDmg[L50]=443` BRUT --
    ni x200 % (=886, multiplier du caster) ni x180 % (=797, multiplier du porteur). Le facteur 200 est
    d'ailleurs arithmetiquement REFUTE : 443 est impair, aucun `extraDmg[L]` x2 ne le produit.
    (Meme famille que le gap #68/#75 « multiplier COMBAT d'un additif d'effet » -- ici MESURE, pas
    suppose.)

    PAS de gate `is_prediction` (contrairement a SmashaEad #71) : le calque est `CrushingStrikeEffect`
    (meme couple `IsNormalAttack & IsMeleeAttack`), et la contribution est MESUREE PRESENTE dans la
    preview native (face prediction) -- cf. GROUND TRUTH ci-dessus."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: "bool | None" = None,
                                              has_moved: "bool | None" = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: "bool | None" = True,
                                              target_armor_reduced: "bool | None" = None,
                                              att_ctx=None) -> "EffectBonus | None":
        if is_ranged:                        # IsMeleeAttack (IdunBattleLogic.Entities.DSLFactory$$IsMeleeAttack)
            return None
        if is_normal_attack is False:        # IsNormalAttack (IdunBattleLogic.Entities.DSLFactory$$IsNormalAttack)
            return None
        # ConfigVar(8=extraDmg, GetAbilityState(effet)) : NIVEAU du poseur, multiplier RESOLU = 100
        # (mesure live +443 = extraDmg[L50] brut ; cf. docstring). `multiplier_pct` laisse a 100.
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else (self.ability_level if self.ability_level is not None else self.level))
        amt = ability_var("Waaagh", "extraDmg", lvl)
        return for_addition(True, int(amt)) if amt else None


class WaaaghExtraHitsEffect(BaseEffect):
    """`Waaagh_ExtraHits` (EffectType 0x44d=1101) -- pose sur le MEME selecteur que 1100 par
    `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetBuffBehaviour` (`AddEffect(0x44d, ..., duree=Direct(1)@dsl+0xc0)`).

    CANAL PORTE (#95) -- `IdunBattle.Entities.Effects.Loki.Waaagh_ExtraHitsEffect$$CreateEffectHitsBonusForAttack`,
    MIRROR 1:1 du decompile (JUMEAU EXACT du canal degat 1100, meme condition, autre magnitude) :
        `EffectBonus.ForAddition( IsNormalAttack & IsMeleeAttack & get_OwnerIsCaster,
                                  ConfigConst(0x2b=extraHit, effet+0x60) )`
    => **+extraHit coup** (CONSTANTE gameconfig Waaagh = 1, NON rarity-scalee -- `GetNumberConstant`, cf.
    `IdunBattle.Entities.Formulas.ConfigAmount$$Calculate` branche constante) sur les attaques **NORMALES
    MELEE** du porteur. Canal `CreateEffectHitsBonusForAttack` = axe COUPS attaquant
    (`entities.effects.hits_bonus_from_effects` -> `IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula$$Calculate`),
    exactement comme `PowerTrip_FullHealthEffect` (dont le gate est `IsNormalAttack & OwnerIsCaster`, SANS
    le `IsMeleeAttack` d'ici).

    `is_melee` vient de l'`att_ctx` (= le `board` de la formule de coups, peuple par les DEUX facades :
    combat `damage_model.build_hits_board` et prediction `playbook/prediction/normal_attack.py`) ;
    contexte ABSENT / nature inconnue -> pas de contribution (degradation fidele « present != applique »)."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True,
                                            att_ctx: "Mapping | None" = None) -> "EffectBonus | None":
        if not is_normal_attack:             # IsNormalAttack (IdunBattleLogic.Entities.DSLFactory$$IsNormalAttack)
            return None
        # IsMeleeAttack (IdunBattleLogic.Entities.DSLFactory$$IsMeleeAttack) : la nature du coup est portee par
        # l'att_ctx (board de la formule). None/absent = inconnu -> aucune contribution.
        if (att_ctx or {}).get("is_melee") is not True:
            return None
        n = ability_var("Waaagh", "extraHit", is_constant=True)   # ConfigConst(0x2b) = 1
        return for_addition(True, int(n)) if n else None
