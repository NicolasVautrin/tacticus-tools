"""`BaseEffect` — mirror de `IdunBattle.Entities.Effects.BaseEffect` + l'interface effet que les builders
de modifier/prédiction consomment (gqfc5mff6c).

Chaque effet du jeu = **UNE sous-classe** (1:1, le namespace natif = le module Python : `Loki` → loki.py).
Une sous-classe N'OVERRIDE QUE les méthodes qu'elle implémente réellement (lues dans ghidra, VA citée) ;
tout le reste = no-op par défaut (l'effet ne contribue rien / est actif tant que présent). C'est la
réplique fidèle du modèle natif « 1 classe par effet, interface uniforme » (doc §17.3/§17.13).

Méthodes d'interface (chacune = sa jumelle native) :
  • create_effect_damage_bonus_for_attack → `EffectBonus | None`  (CreateEffectDamageBonusForAttack)
  • create_effect_hits_bonus_for_attack   → `EffectBonus | None`  (CreateEffectHitsBonusForAttack)
  • get_armor_penetration                 → `int | None`          (IgnoreArmor, ex. KanOpener ConfigVar 0x40)
  • is_active(unit_state)                  → bool                  (CreateActiveCondition)
Cycle de vie (porté depuis les `*Ability.CreateTrigger` de pose/retrait) : `removed_after_attack`,
`one_shot`, `expired`.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ...services.effect_bonus import EffectBonus

# Sentinelle de durée d'un sous-effet : MÊME nombre de tours que le parent (mirror natif
# `AddSubEffectWithSameTurns`). Distinct de None (= permanent, lié au cycle de vie du parent).
SAME_TURNS = "same"


@dataclass
class SubEffectSpec:
    """Sous-effet (enfant) qu'un effet COMPOSITE spawne quand il est appliqué (mirror des
    `Add*SubEffect`/`AddEffect` de `<Effect>.ApplyInternal`). `turns` :
      • `SAME_TURNS` → même durée que le parent (`AddSubEffectWithSameTurns`)
      • `0` ou None  → permanent, lié au parent (rem=0 natif ; reverté à l'expiration du parent)
      • `N>0`        → N tours."""
    effect_type: int
    name: str
    turns: "int | str | None" = None


@dataclass
class BaseEffect:
    """Effet matérialisé : identité (seedée depuis la capture one-shot) + état de cycle de vie mutable."""
    name: str
    effect_type: int | None = None
    level: int | None = None                 # niveau de STACK capté (decisionView.effects[].level) — pour
                                             # les effets à empilement (ex. Contagions) ; ≠ niveau d'ability
    # Niveau de l'ABILITY source sur l'unité (active/passive/tertiary), qui indexe les `variables[level]`
    # d'ability (≠ stack `level`). Ex. PowerTrip.armorIgnored indexé par PassiveAbilityLevel (=50), PAS
    # par le stack level (=1). Seedé depuis l'unité ; None → fallback sur `level`. §17.21.
    ability_level: int | None = None
    # Niveau de l'ability ACTIVE de l'unité (unitConfig.activeAbilityLevel) — pour les stat-mods dont la
    # source est une ability ACTIVE (ex. StandVigil) : indexe `variables[level]` sur l'active, pas la
    # passive. `ability_level` reste le niveau passif (défaut). Un effet choisit le slot pertinent.
    active_ability_level: int | None = None
    remaining_turns: int | None = None      # None = permanent/aura ; sinon décrémenté en fin de tour
    source: int | None = None                # `EffectComponent` SourceUnit @+0x10 (qui a posé l'effet)
    # `EffectComponent` Target @+0x14 — l'unité QUI PORTE l'effet (peuplé à la MATÉRIALISATION,
    # AddEffectOperation/AddNewEffect ; les effets seedés one-shot le laissent None, l'unité porteuse
    # = la clé `EffectsState.by_unit`). Distinct de `source` (qui l'a posé).
    target: int | None = None
    # `EffectComponent` Value @+0x60/+0x64 (flag @+0x5d) — magnitude matérialisée (Nullable<int> natif :
    # None = effet sans valeur portée, la magnitude vient alors de la config d'ability). Peuplé par
    # AddEffectOperation depuis le builder (param_6) quand l'ability source porte une valeur explicite.
    value: int | None = None
    # `EffectComponent` ParentEffect @+0x70 — pour un SOUS-effet (enfant d'un effet composite), le type
    # de l'effet parent qui l'a spawné (ex. Stunned 1162 parent de 1165/1166/1167). None = effet racine.
    # Sert au cycle de vie (les enfants sont reverté quand le parent expire). §matérialisation composite.
    parent_type: int | None = None
    consumed: bool = False                   # retiré par le cycle de vie (one-shot / fin-de-tour)
    # `AbilityVariablesMultiplierPercentage` de l'unité porteuse (BC, défaut 100). Le natif bake le
    # scaling dans la config par-unité ; ici l'effet le porte pour scaler ses variables d'ability
    # affectées (`variablesAffectedByRarityBonus`) via `magnitude.ability_var(multiplier_pct=…)`. §17.21.
    ability_variables_multiplier: int = 100

    # ── contributions aux modifiers (None = pas de contribution) ────────────────────────────────────
    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True) -> EffectBonus | None:
        """`<Effect>.CreateEffectDamageBonusForAttack` — contribution au scalaire dégât (additif/percent).
        `target_traits` = noms de traits gameconfig de la CIBLE (mirror `HasTrait(target,…)` natif) pour
        les bonus target-conditionnels (ex. BeastSlayer vs BigTarget/Vehicle) ; None = cible inconnue.
        `is_ranged` = nature du coup courant : effets gated `IsRangedAttack` (HeavyWeapon_ExtraDmg,
        RangedSpecialist). `has_moved` = la position d'attaque diffère de la position COURANTE (candidat
        avec déplacement) : effets gated no-move (`!HasFlag(HasMoved=0)`, ex. HeavyWeapon @180f4f030 —
        GROUND TRUTH step-23 : les tuiles ranged AVEC déplacement de u78 collent SANS ×1.25 ; step-11 :
        « ×1.25 selon tuile »). `is_normal_attack` = mirror du nœud DSL `IsNormalAttack` (attaque normale
        vs spéciale — gate de CrushingStrike @180f3ad90 ; True par défaut : les call-sites normale ne le
        passent pas). None = contexte inconnu."""
        return None

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True) -> EffectBonus | None:
        """`<Effect>.CreateEffectHitsBonusForAttack` — contribution à l'axe COUPS (Addition/Subtraction)."""
        return None

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None,
                                             defender_on_cover: bool | None = None) -> EffectBonus | None:
        """Contribution DÉFENSEUR à l'axe COUPS (l'effet est sur la CIBLE, modifie les coups reçus).
        Natif : même canal `CreateEffectHitsBonusForAttack` mais trigger `OwnerIsTarget` (ex.
        `LightCoverEffect.CreateEffectHitsBonusForAttack` @180f556b0 = `ForAdditionWithMinimum(
        OwnerIsTarget(tuiles égales) & !IsMeleeAttack, -ConfigConst(0x2c hitsReduction), min=Direct(1))` ;
        `ParryEffect` @180f5d860 idem gated `IsMeleeAttack` ; `MasterAnnihilator_AdditionalHitEffect`
        @180f58d50 = +nrOfHits gated `!DamageProfileIs(Psychic)`) — le port eager sépare
        attaquant/défenseur, symétrique de `create_effect_damage_malus_for_defense`. `damage_profile` =
        NOM du profil de l'attaque (gate Psychic). `defender_on_cover` = gate compute-time des effets de
        TUILE (LightCover) : True=cible sur sa tuile de cover, False=hors-cover (effet périmé, ne s'applique
        pas), None=inconnu (applique sur présence — cas prédiction, cible immobile). Plancher min=1 chez le
        consommateur. Défaut None."""
        return None

    def create_aura_hits_malus_for_defense(self, ctx: Mapping | None = None) -> EffectBonus | None:
        """Contribution AURA à l'axe COUPS : l'effet est possédé par une AUTRE unité que la cible et
        projette un malus sur elle selon la géométrie (natif : effet à `CreateTargetSelector` +
        `GetRefreshTriggers`, ex. `BigTargetAdjacentEffect` @180f33ac0/@180f33c70 = alliés ring-1 du
        porteur, -1 coup ranged min 1). `ctx` = {owner_id/pos/team, tgt_id, t_pos, tgt_team, is_melee}
        fourni par l'agrégateur `aura_hits_malus_for_defense`. Défaut None = pas d'aura."""
        return None

    def create_aura_hits_bonus_for_attack(self, ctx: Mapping | None = None) -> EffectBonus | None:
        """Contribution AURA à l'axe COUPS côté ATTAQUANT : l'effet est possédé par un ALLIÉ de l'attaquant
        et lui projette un BONUS de coups selon la géométrie (natif : `CreateTargetSelector` = SurroundingFriends,
        ex. `AstartesBanner_AdditionalHitsEffect` @180f323b0 = +extraHits mêlée aux alliés dans le rayon 2 du
        porteur, exclut self). `ctx` = {owner_id/pos/team, att_id/att_pos/att_team, is_melee} fourni par
        l'agrégateur `aura_hits_bonus_for_attack`. Défaut None = pas d'aura. SYMÉTRIQUE du malus défenseur."""
        return None

    def create_aura_attack_bonus(self, ctx: Mapping | None = None) -> "int | None":
        """Contribution AURA à la BASE (stat Attack) : effet stat-mod possédé par un ALLIÉ du porteur qui
        buffe le dégât de base de l'attaquant quand il est à portée (natif : `DynamicStatModifierEffect` à
        `CreateTargetSelector` = `AdjacentUnits(1)→Friends→With/WithoutTrait`, ex. `RitesOfBattleAbility`
        @181225340). Ajouté PLAT à `GetStat(Attack, INITIAL)`, RÉ-ÉVALUÉ PAR CANDIDAT (adjacence à la tuile
        d'attaque). `ctx` = {owner_id/pos/team/mult/level, att_id/att_pos/att_team/att_grand_alliance, board}
        fourni par l'agrégateur `aura_attack_bonus_from_allies`. Défaut None = pas d'aura."""
        return None

    def create_aura_attack_damage_malus_for_enemy(self, ctx: Mapping | None = None) -> EffectBonus | None:
        """Contribution AURA %-DÉGÂT projetée sur un ENNEMI ATTAQUANT à portée (l'effet est possédé par une
        unité, se projette sur les ENNEMIS environnants qui subissent un malus sur LEUR propre attaque —
        natif : effet à `CreateEffectDamageBonusForAttack(OwnerIsActor & ...)` + `CreateTargetSelector` =
        `SurroundingEnemies(range)`, ex. `ShadowInTheWarp_LessDmg_Effect` @180f6b420/@180f6b5f0 = -25%
        Psychic). `ctx` = {owner_id/pos/team, att_id/att_pos/att_team, damage_profile} fourni par
        l'agrégateur `aura_attack_damage_malus_from_enemies`. Défaut None = pas d'aura."""
        return None

    def create_effect_crit_chance_bonus_for_attack(self) -> int | None:
        """Bonus de CHANCE de crit (%) — couche calc-time SÉPARÉE de `GetStat(9)`, sommée dans
        `DamagePrediction.GetCritChanceBonusFromEffects`@181031180 puis ajoutée à GetStat(9) dans
        `RollCritical` (cc = clamp(GetStat(9)+Σbonus, 0, 100)). Distinct des effets StatModification
        sur la crit-chance (eux DANS GetStat) → pas de double-compte. Défaut None = pas de bonus."""
        return None

    def create_effect_crit_damage_bonus_for_attack(self) -> int | None:
        """Bonus de DÉGÂT de crit — couche calc-time SÉPARÉE de `GetStat(10)`, sommée dans
        `DamagePrediction.GetCritDamageBonusFromEffects`@181031bb0 puis ajoutée à GetStat(10) dans
        `CalculateCriticalDamage` (critDmgPct = max(0, GetStat(10)+Σbonus)). Défaut None = pas de bonus."""
        return None

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                                damage_profile: str | None = None,
                                                attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        """`<Effect>.CreateEffectDamageMalusForDefense` — contribution DÉFENSEUR (l'effet est sur la CIBLE,
        MODIFIE le dégât reçu). Symétrique de `create_effect_damage_bonus_for_attack`. `is_melee` = nature
        du coup (certains malus sont gated `IsMeleeAttack`, ex. Terrifying_ExtraDefense) ; `damage_profile`
        = NOM du profil de dégât de l'attaque (certains malus sont gated `DamageProfileIs`, ex.
        TerminatorArmour réduit SAUF Psychic/DirectDamage). `attacker_ctx` = contexte de l'ATTAQUANT (source
        du coup) `{id, ability_level, multiplier}` — pour les malus gated sur l'IDENTITÉ de l'attaquant
        (ex. Neuroparasite : `AreEqual(BondedEntity, damageSource)` = seul LE Neurothrope qui a infecté
        bénéficie du +dégât ; sa magnitude `ConfigVar(source ability state)` s'indexe sur SON niveau/mult).
        Renvoie un `EffectBonus` (`PercentDecrease` de réduction OU `ForAddition` positif type Neuroparasite,
        gated par une condition d'effet) ou None.

        RE : `CalculateDefenderModifiersForPrediction` @181002c30 itère les effets de la cible et appelle
        cette méthode (interface effet, slot 0x1a) sur chacun → accumule un `DamageModifiers` (%-list).
        La famille `ADamageDefenseModifierAbilityEffect` (CloudOfFlies/ContemptuousDisregard/ForwardObservers/
        HuntersInstincts/… @180f08e60→BaseEffect.DamageMalusForDefense @180f10120) = `EffectBonus(PercentDecrease,
        ConfigVar(key))` gated (ex. ContemptuousDisregard @180f3a5b0 : OwnerIsTarget & HasUsedActiveAbilityThisTurn
        → ConfigVar 0x46). Défaut None = effet sans réduction défensive (dégradation fidèle)."""
        return None

    def create_effect_block_source_for_defense(self, defender_fixed_armor: int = 0):
        """`<Effect>.CreateAddBlockEffectBehaviour`/`AddExtraBlockEffectToOwner` @180e18b70 — source de
        BLOCK SUPPLEMENTAIRE possedee par la CIBLE (defenseur), AJOUTEE a la chaine
        `apply_random_block_damage` EN PLUS du block de base (scalaire `GetStat(7/8)`). Renvoie un
        `BlockSource(chance, amount)` ou None (defaut). Ex. BeastSlayer @180e18b70 :
        chance=`GetBlockChance @180e19120`=beastSlayerBlockChance ; amount=`GetBlockDamage @180e19160`=
        blockDmgPct% du FixedArmor COURANT du defenseur. Ces entrees sont ABSENTES du scalaire GetStat(7/8)
        (verifie live 2026-07-09 : orksNob blockChance=0 alors que BeastSlayer donne +10%) -> le natif les
        tient dans `GetMultiValueStat(7)` (`CalculateBlockChances @181002350`). `defender_fixed_armor` =
        FixedArmor courant de la CIBLE (pour les sources dont l'amount depend de l'armure). #72."""
        return None

    def get_armor_penetration(self, is_normal_attack: bool = True) -> int | None:
        """`<Effect>.IgnoreArmor` — pénétration d'armure (axe armure : armor_eff = max(armure − pén, 0)).
        `is_normal_attack` : certaines pénétrations sont gated attaque normale (i2 PowerTrip
        « NORMAL attacks ignore X Armour » — GROUND TRUTH step-13 : DakkaDakkaDakka (spéciale) du même
        porteur ne bénéficie PAS des 499 de pénétration, per-coup natif 404/728 vs 78 = armure pleine)."""
        return None

    # ── stat-modification (famille AStatModifierEffect) ─────────────────────────────────────────────
    def get_stat_modification_stat(self) -> "int | None":
        """`AStatModifierEffect.GetStatModificationStat @180f0a890` — le **StatType** que CET effet
        modifie (natif : `EffectComponent+0x10`). `None` = l'effet n'est pas un StatModifier (défaut).
        Un effet StatModification écrit sa magnitude dans la **modification** du stat (part 5/9),
        attribuée à sa source, appliquée via `ChangeStat` (cf. `UnitStats.change_stat`)."""
        return None

    def get_stat_modification_amount(self) -> "int | None":
        """`StaticStatModifierEffect.GetStatModificationAmount @180f47430` (natif : `EffectComponent+0x14`,
        fixe) / `ADynamicStatModifierEffect.GetStatModificationAmount @180f090f0` (calculé).
        Magnitude (delta additif) ajoutée à la modification du StatType de
        `get_stat_modification_stat`. `None`/0 = aucune (défaut). Un effet StatModification concret
        override les deux (StatType + magnitude, typiquement depuis sa config d'ability)."""
        return None

    # ── matérialisation composite ─────────────────────────────────────────────────────────────────
    def sub_effects_on_apply(self) -> list[SubEffectSpec]:
        """`<Effect>.ApplyInternal` — sous-effets (enfants) spawnés quand CET effet est appliqué.
        Défaut : aucun (effet simple). Un effet COMPOSITE (ex. Stunned) override pour déclarer ses
        enfants ; `AddEffectOperation` les matérialise après le parent (en propageant le lien parent)."""
        return []

    # ── cycle de vie ────────────────────────────────────────────────────────────────────────────────
    def is_active(self, unit_state: Mapping | None = None) -> bool:
        """`<Effect>.CreateActiveCondition` — l'effet contribue-t-il dans l'état courant ? (défaut : oui)."""
        return True

    @property
    def removed_after_attack(self) -> bool:
        """Retiré en fin de tour si l'unité a attaqué ce tour (cas RapidAssault)."""
        return False

    @property
    def one_shot(self) -> bool:
        """Consommé dès la 1re attaque de l'unité (effets « 1re attaque » stricts)."""
        return False

    @property
    def expired(self) -> bool:
        return self.remaining_turns is not None and self.remaining_turns <= 0
