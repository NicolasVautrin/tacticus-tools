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
    """`HypersensoryAbilities_MinimalHealthEffect` (Effects.Idun, effet 0x564=1380 ; ctor @180f448f0).

    HP-FLOOR passif de Judh (genesJudh). i2 : « The first time each enemy turn that Judh is attacked, she
    cannot fall below 50% of her current Health. » Posé sur le porteur à l'init de l'ability passive
    `HypersensoryAbilities` (owner-effect `CreateBehaviour` @180f87870 = `AddEffect(0x564, owner)`).

    - `ApplyInternal` @180f445a0 : `floor = Min(Round(GetStat(Health,Current) x hpPct/100), current-1)` ->
      `HealthComponent.MinimalHealth @+0x1c` (Nullable). SNAPSHOT du HP COURANT au moment de l'Apply.
    - `RevertInternal` @180f44820 : `MinimalHealth = null` (efface le plancher).
    - `CreateActiveCondition` @180f447a0 : `IsEnemyTurn(owner) & Not(HasBeenAttackedAmountThisTurn(owner)>=1)`
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
        """`ApplyInternal` @180f445a0 : `Min(Round(current_hp x hpPct/100), current_hp - 1)`. None si pct absent
        ou hp<=0. `Fix64.Round` = RoundToNearest half-to-even == `round()` Python (le facteur pct/100 est exact
        en Fix64 ; l'arrondi ne joue que pour un hp impair a 50 %)."""
        pct = self.minimal_health_pct()
        if pct is None or current_hp is None or int(current_hp) <= 0:
            return None
        raw = int(round(int(current_hp) * pct / 100.0))
        return min(raw, int(current_hp) - 1)


class ContaminatedUnitEffect(BaseEffect):
    """`Contaminated_Unit` (effet 0x4dd=1245, `ContaminatedStatModifierEffect`, ctor @180f3a560 =
    ADynamicStatModifierEffect FixedArmor) — SOUS-effet pose sur une UNITE occupant/entrant une tuile
    `Contaminated` (0x4dc), 1 round. Debuff dynamique de la stat FixedArmor (=16).

    Le NATIF calcule le montant a l'apply (`ADynamicStatModifierEffect.GetStatModificationAmount @180f090f0`
    -> `GetDynamicStatModificationAmount @180f3a460` = -X% du FixedArmor courant) et l'applique via ChangeStat.
    Cote port : le vecteur tile-effect (#128, `ContaminatedTileEffect`) calcule le delta a l'apply et le stocke
    dans `self.value` -> `get_stat_modification_amount` renvoie `self.value`.

    >>> MAGNITUDE (#132 RESOLUE 2026-07-14, RE re-expert decompile) : `GetDynamicStatModificationAmount
    @180f3a460` = `-BattleQuery.GetEffectConfig(EffectType=6)` (interface IBattleQuery slot 0xbe, arg 6 =
    EffectType litteral). `BattleQuery.GetEffectConfig @1810610b0` = lookup `Dict<EffectType,int>@+0xd0`
    peuple par `InitEffectConfig @18106e9c0` depuis `BattleConfiguration.Effect` ; l'entree EffectType=6
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
    (l'unité se buffe elle-même en « stand vigil » = sans se déplacer). `GetDynamicStatModificationAmount
    @180f6d910` = `ConfigVar(key 0x51c=1308, EffectSource, 0x1b)` = ability var
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


class BlessingsOfKhorneModifiersEffect(BaseEffect):
    """`BlessingsOfKhorne_ModifiersEffect` (EffectType 0x4ee=1262, nom capté "BlessingsOfKhorne" ;
    config-owner TriggeredAbilityType 0x4c0=1216) — trait BlessingsOfKhorne (1046), TOUTE la faction
    World Eaters (11 carriers : Azkor worldEightbound, Kharn, Wrask, Macer, + bosses LHE). DEUX
    value-modifications sur le PORTEUR, toutes deux scalées par le MÊME multiplicateur N (#185) :

    - DÉFENSE `CreateEffectDamageMalusForDefense @180f34c50` : `(OwnerIsTarget & DamageProfileIs(0xd=
      Psychic)) -> -ConfigConst(0x4c=DmgPctReduction) x N` ⇒ le dégât PSYCHIQUE reçu par le porteur
      est réduit de `8% x N` (max -64%).
    - ATTAQUE `CreateEffectDamageBonusForAttack @180f34ae0` : `get_OwnerIsCaster` SEUL (AUCUN filtre
      profil/normal/spéciale) `-> +ConfigConst(0xf=ExtraDmgPct) x N` ⇒ TOUT le dégât sortant du
      porteur est augmenté de `3% x N` (max +24%).

    N = `GetMultiplierBasedOnDefeatedInMelee @180f34ea0` = `Min(Count(NormalUnits(UnitsDefeatedBy-
    MeleeAttack(AllUnits))) [+ TalismanOfRage self-kills], ConfigConst(0x43=MaxDefeatedUnits=8))`.
    Le compte de base est GLOBAL (unités normales des DEUX camps tuées par une attaque de MÊLÉE,
    flag `UnitComponent.DefeatedByMeleeAttack @0x178` écrit par `KillUnitOperation @180e76470`,
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
        """`GetMultiplierBasedOnDefeatedInMelee @180f34ea0` : Min(count, MaxDefeatedUnits=8)."""
        if self.melee_defeats is None:
            return 0
        cap = trait_var("BlessingsOfKhorne", "blessingsOfKhorneMaxDefeatedUnits")   # ConfigConst 0x43 (=8)
        return min(int(self.melee_defeats), int(cap) if cap else 8)

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if (damage_profile or "") != "Psychic":               # DamageProfileIs(0xd) @180f34c50
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
        # trigger natif @180f34ae0 = get_OwnerIsCaster SEUL — tous profils, normale ET spéciale.
        n = self._n()
        if n <= 0:
            return None
        pct = trait_var("BlessingsOfKhorne", "blessingsOfKhorneExtraDmgPct")        # ConfigConst 0xf (=3)
        if not pct:
            return None
        return for_percent_increase(True, abs(int(pct)) * n)


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


class StunnedDamageModifierEffect(BaseEffect):
    """`Stunned_DamageModifierEffect` (enfant 0x48f=1167 du composite Stunned, posé par
    `StunnedEffect.ApplyDamageModifier @180f6e9b0` = DSL `AddEffect(0x48f)`) — le malus de DÉGÂT
    SORTANT du porteur stunné (#29 lead 2, la pièce ×0.5 du miss 777 s15).

    `CreateEffectDamageMalusForDefense @180f6f770` : `EffectBonus.ForPercentDecrease(
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
        """`ActOfFaithBuffEffect.ApplyModification @180f302f0` (part DATA côté `entities/`, mirror des DEUX
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
        """`ActOfFaithBuffEffect.RevertInternal @180f306e0` annule les DEUX `ChangeStat` de CE stack :
        crit-chance (Position(9,5)) + crit-damage (Position(10,5)). Ces StatTypes sont lus par la feuille
        `RemoveEffect` (runner) pour `revert_change_stat(…, stat_mod_source)` par-source."""
        from ...stats import StatType
        return [StatType.CRIT_CHANCE, StatType.CRIT_DAMAGE]


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
    pas avancer le tour suivant). `EffectConfig(1)` = BC `Effect.PinnedMovementReduction` (mapping
    ordinal→champ DTO prouvé par `InitEffectConfig @18106e9c0` : +0x10→0, +0x14→1, +0x1c→2, ... —
    recoupé par Stunned EffectConfig(2)=StunnedDmgReductionPct bit-exact).

    MALUS DE DÉGÂT ATTAQUANT (#57b, famille ×0.70 du batch #52) : `CreateEffectDamageBonusForAttack
    @180f5e8e0` = `EffectBonus.ForPercentIncrease(get_OwnerIsCaster, Negative(EffectConfig(0)))` —
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
