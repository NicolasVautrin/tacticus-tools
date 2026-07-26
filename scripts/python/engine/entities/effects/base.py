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


# ── nature du coup : mirror des DEUX prédicats natifs (#106) ────────────────────────────────────
# `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` / `IdunBattle.Core.Services.BattleQuery$$IsRangedAttack`
# (consommés par `IdunBattle.Entities.Triggers.IsMeleeAttackAbilityTrigger$$ShouldTrigger` /
# `IdunBattle.Entities.Triggers.IsRangedAttackAbilityTrigger$$ShouldTrigger`, eux-mêmes les nœuds
# `IdunBattleLogic.Entities.DSLFactory$$IsMeleeAttack` / `$$IsRangedAttack` des `CreateEffectDamageBonusForAttack`).
# Les DEUX partent de `GetAbilityAttackRangeType(abilityDuCoup)` et rendent un **bool**, jamais un tri-état :
#   • `Nullable<AbilityOrEffect>` VIDE (pas d'ability dans le contexte) → `GetAbilityAttackRangeType` = 0
#     → melee=FALSE **et** ranged=FALSE ;
#   • 0 (None)   → melee=FALSE, ranged=FALSE  (ni l'un ni l'autre — les deux gates se taisent) ;
#   • 1 (Melee)  → melee=TRUE,  ranged=FALSE ;
#   • 2 (Ranged) → melee=FALSE, ranged=TRUE  ;
#   • 3 (Both)   → `HasFlag(unit, 0x15)` ? (melee=FALSE, ranged=TRUE) : `AreUnitsInMelee(attPos, tgtPos)`
#                  (position-based, melee = AreUnitsInMelee, ranged = son complément).
# ⇒ le natif n'a PAS d'état « inconnu », et surtout : quand la nature n'est PAS déterminée, il ne se rabat
# JAMAIS sur mêlée. Côté port, `is_ranged=None` (nature non threadée par la façade appelante) doit donc
# faire TAIRE les DEUX familles de gates, comme l'axe COUPS (`att_ctx["is_melee"] is not True`) et les
# auras (`ctx["is_melee"]`) le font déjà. Le défaut FALSY de `if is_ranged:` faisait l'inverse sur l'axe
# DÉGÂT (contribution mêlée-only appliquée à un coup de nature inconnue) — c'était le fork du cas #106.
def is_melee_attack(is_ranged: "bool | None") -> bool:
    """`BattleQuery$$IsMeleeAttack` : VRAI seulement si la nature du coup est PROUVÉE mêlée."""
    return is_ranged is False


def is_ranged_attack(is_ranged: "bool | None") -> bool:
    """`BattleQuery$$IsRangedAttack` : VRAI seulement si la nature du coup est PROUVÉE distance."""
    return is_ranged is True


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
    # Empilement : un effet StatModifier qui applique un stat-mod FRAIS à CHAQUE pose (ActOfFaith) le passe
    # à True → `AddEffectOperation` ne no-op PAS sur « déjà présent » et matérialise une NOUVELLE instance
    # (revert par-source). Défaut False = comportement historique (un même-type déjà présent → no-op, mirror
    # du refresh des effets updatable Fire/Pinned/Stunned). §slice-20 (docs/rl/dsl-effect-nodes.md).
    # ⚠ PAS d'annotation de type (`: bool`) : ce serait un FIELD dataclass dont l'`__init__` écraserait
    # l'override de sous-classe (ex. `ActOfFaithBuffEffect.stacks_stat_mod_on_add = True`). Attribut de
    # classe SIMPLE = surchargeable par la MRO (même pattern que `cc_delta`/`stat_mod_source`).
    stacks_stat_mod_on_add = False
    # Journal des `AddUnitActiveAbilityModification` REELLEMENT poses par cette instance (liste de
    # `(target, key, delta)`), rempli par `operations/ability_modifications.py::apply_ability_modifications`
    # et NIE par `revert_ability_modifications` (mirror `RevertInternal` = les memes appels en `-delta`).
    # Meme regime d'attribut de classe SIMPLE que `stacks_stat_mod_on_add` (pas d'annotation -> pas de
    # field dataclass). None/[] = l'effet n'a pose aucune modification d'ability.
    applied_ability_modifications = None
    # CLE de la `ValueModification` que CETTE instance a posee sur le `UnitStats` de sa cible. Cote natif
    # c'est litteralement l'ENTITE-EFFET : `IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification`
    # passe `DSLFactory$$Entity(<effectEntity>)` en 6e argument de `IdunBattleLogic.Entities.DSLFactory$$ChangeStat`,
    # et `IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification` REPASSE LA MEME entite avec
    # `Position(stat, part 6)` -> `IdunBattle.Entities.Components.ValueModification$$ReverseModification`.
    # => UNE seule cle par instance d'effet, quel que soit le chemin qui l'a posee. Renseignee par les
    # chemins de pose OFFLINE (`AddEffectOperation._apply_stat_mods`, feuille `AddStaticStatModifierEffect`) ;
    # laissee None pour un effet SEEDE (la cle est alors DERIVEE — cf. `effect_stat_mod_key`).
    stat_mod_source = None
    # Marqueur d'idempotence du revert (`RevertModification` deja joue pour cette instance). Le revert
    # par-source est structurellement idempotent (`ReverseModification` pop une cle absente = no-op) ; ce
    # drapeau evite surtout de RE-LISTER le meme revert a chaque tick dans les diagnostics.
    stat_mod_reverted = False

    def applied_stat_mods(self, stats_ctx) -> "list":
        """`<Effect>.ApplyModification` (part DATA côté `entities/`) — liste des `(StatType, montant)` posés
        via `ChangeStat` quand l'effet est appliqué. La couche runner (`AddEffectOperation._apply_stat_mods`)
        les EXÉCUTE (`apply_change_stat`, keyé par source). Symétrique de `reverted_stats()` (que lit
        `RemoveEffect`). Défaut `[]` = effet sans stat-mod eager (la plupart)."""
        return []

    # ── contributions aux modifiers (None = pas de contribution) ────────────────────────────────────
    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        """`<Effect>.CreateEffectDamageBonusForAttack` — contribution au scalaire dégât (additif/percent).
        `target_traits` = noms de traits gameconfig de la CIBLE (mirror `HasTrait(target,…)` natif) pour
        les bonus target-conditionnels (ex. BeastSlayer vs BigTarget/Vehicle) ; None = cible inconnue.
        `is_ranged` = nature du coup courant : effets gated `IsRangedAttack` (HeavyWeapon_ExtraDmg,
        RangedSpecialist). `has_moved` = la position d'attaque diffère de la position COURANTE (candidat
        avec déplacement) : effets gated no-move (`!HasFlag(HasMoved=0)`, ex. HeavyWeapon IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier —
        GROUND TRUTH step-23 : les tuiles ranged AVEC déplacement de u78 collent SANS ×1.25 ; step-11 :
        « ×1.25 selon tuile »). `is_normal_attack` = mirror du nœud DSL `IsNormalAttack` (attaque normale
        vs spéciale — gate de CrushingStrike IdunBattle.Entities.Effects.Loki.CrushingStrikeEffect$$CreateDamageModifier ; True par défaut : les call-sites normale ne le
        passent pas). `target_armor_reduced` = évaluation du gate `HasNegativeModifier(cible, {ARMOR,
        FIXED_ARMOR})` (IdunBattle.Entities.Triggers.HasNegativeModifier$$ShouldTrigger ; la CIBLE porte ≥1 modification per-source <0 sur une stat d'armure =
        « armure réduite ») threadée depuis le site de résolution — pour les bonus gated sur l'état d'armure
        de la cible (ConquerorImperative IdunBattle.Entities.Effects.Loki.ConquerorImperativeEffect$$CreateDamageModifier). None = état inconnu. `att_ctx` (Mapping|None) =
        contexte POSITIONNEL de l'attaque pour les bonus dont la MAGNITUDE dépend de la position du caster
        (mirror du DSL qui lit la UnitPosition hypothétique, ex. LordOfTempests `SurroundingTiles(owner,0,1)`
        IdunBattle.Entities.Effects.Loki.LordOfTempests_ExtraDamageEffect$$GetHexesIncreasingDamage) : {"att_pos": (col,row) tuile candidate, "tile_effects_by_pos": {(col,row):[noms]}}.
        None = contexte inconnu -> ces bonus rendent None (« présent ≠ appliqué », dégradation fidèle)."""
        return None

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True,
                                            att_ctx: Mapping | None = None) -> EffectBonus | None:
        """`<Effect>.CreateEffectHitsBonusForAttack` — contribution à l'axe COUPS (Addition/Subtraction).
        `att_ctx` (Mapping|None) = le `board` de `AttackHitsWithModifiersFormula` ({att_id, tgt_id,
        attack_pos, t_pos, …}) ENRICHI de `tile_effects_by_pos` (tileMeta → nœud `HasTileStatusEffect`)
        et `persistent_data` (les clés `PersistentDataComponent` posées sur l'ATTAQUANT → nœud
        `IsPersistentData`), pour les bonus dont le gate porte sur la CIBLE ou sur un flag intra-attaque
        (ex. `IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits = `OwnerIsCaster &
        (TargetHasTileEffect | IsPersistentData)`). None = contexte inconnu → ces bonus rendent None."""
        return None

    def create_effect_hits_malus_for_defense(self, is_melee: bool | None = None,
                                             damage_profile: str | None = None,
                                             defender_on_cover: bool | None = None,
                                             dist: int | None = None) -> EffectBonus | None:
        """Contribution DÉFENSEUR à l'axe COUPS (l'effet est sur la CIBLE, modifie les coups reçus).
        Natif : même canal `CreateEffectHitsBonusForAttack` mais trigger `OwnerIsTarget` (ex.
        `IdunBattle.Entities.Effects.Loki.LightCoverEffect$$CreateEffectHitsBonusForAttack = `ForAdditionWithMinimum(
        OwnerIsTarget(tuiles égales) & !IsMeleeAttack, -ConfigConst(0x2c hitsReduction), min=Direct(1))` ;
        `ParryEffect` IdunBattle.Entities.Effects.Loki.ParryEffect$$CreateEffectHitsBonusForAttack idem gated `IsMeleeAttack` ; `MasterAnnihilator_AdditionalHitEffect`
        IdunBattle.Entities.Effects.Loki.MasterAnnihilator_AdditionalHitEffect$$CreateAdditionalHits = +nrOfHits gated `!DamageProfileIs(Psychic)`) — le port eager sépare
        attaquant/défenseur, symétrique de `create_effect_damage_malus_for_defense`. `damage_profile` =
        NOM du profil de l'attaque (gate Psychic). `defender_on_cover` = gate compute-time des effets de
        TUILE (LightCover) : True=cible sur sa tuile de cover, False=hors-cover (effet périmé, ne s'applique
        pas), None=inconnu (applique sur présence — cas prédiction, cible immobile). Plancher min=1 chez le
        consommateur. Défaut None."""
        return None

    def create_aura_hits_malus_for_defense(self, ctx: Mapping | None = None) -> EffectBonus | None:
        """Contribution AURA à l'axe COUPS : l'effet est possédé par une AUTRE unité que la cible et
        projette un malus sur elle selon la géométrie (natif : effet à `CreateTargetSelector` +
        `GetRefreshTriggers`, ex. `BigTargetAdjacentEffect` IdunBattle.Entities.Effects.Loki.BigTargetAdjacentEffect$$CreateEffectHitsBonusForAttack/IdunBattle.Entities.Effects.Loki.BigTargetAdjacentEffect$$CreateTargetSelector = alliés ring-1 du
        porteur, -1 coup ranged min 1). `ctx` = {owner_id/pos/team, tgt_id, t_pos, tgt_team, is_melee}
        fourni par l'agrégateur `aura_hits_malus_for_defense`. Défaut None = pas d'aura."""
        return None

    def create_aura_hits_bonus_for_attack(self, ctx: Mapping | None = None) -> EffectBonus | None:
        """Contribution AURA à l'axe COUPS côté ATTAQUANT : l'effet est possédé par un ALLIÉ de l'attaquant
        et lui projette un BONUS de coups selon la géométrie (natif : `CreateTargetSelector` = SurroundingFriends,
        ex. `AstartesBanner_AdditionalHitsEffect` IdunBattle.Entities.Effects.Loki.AstartesBanner_AdditionalHitsEffect$$CreateAdditionalHits = +extraHits mêlée aux alliés dans le rayon 2 du
        porteur, exclut self). `ctx` = {owner_id/pos/team, att_id/att_pos/att_team, is_melee} fourni par
        l'agrégateur `aura_hits_bonus_for_attack`. Défaut None = pas d'aura. SYMÉTRIQUE du malus défenseur."""
        return None

    def create_aura_attack_bonus(self, ctx: Mapping | None = None) -> "int | None":
        """Contribution AURA à la BASE (stat Attack) : effet stat-mod possédé par un ALLIÉ du porteur qui
        buffe le dégât de base de l'attaquant quand il est à portée (natif : `DynamicStatModifierEffect` à
        `CreateTargetSelector` = `AdjacentUnits(1)→Friends→With/WithoutTrait`, ex. `RitesOfBattleAbility`
        IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfBattleAbility$$CreateBehaviour). Ajouté PLAT à `GetStat(Attack, INITIAL)`, RÉ-ÉVALUÉ PAR CANDIDAT (adjacence à la tuile
        d'attaque). `ctx` = {owner_id/pos/team/mult/level, att_id/att_pos/att_team/att_grand_alliance, board}
        fourni par l'agrégateur `aura_attack_bonus_from_allies`. Défaut None = pas d'aura."""
        return None

    def create_aura_fixed_armor_bonus_for_defense(self, ctx: Mapping | None = None) -> "int | None":
        """Contribution AURA à la stat **FixedArmor(16)** du DÉFENSEUR : effet stat-mod possédé par un ALLIÉ
        du défenseur qui buffe l'armure de ce dernier quand il est à portée (natif : `DynamicStatModifierEffect`
        à `CreateTargetSelector` = self + `AdjacentFriends(1)` ∩ `UnitsWithTrait(5=Mechanical)`, ex.
        `ProtectorImperative` IdunBattle.Entities.Effects.Loki.ConquerorImperativeEffect$$CreateTargetSelector). Ajouté PLAT à `GetStat(FixedArmor)` du défenseur, RÉ-ÉVALUÉ PAR
        ADJACENCE au site de résolution armure (le natif écrit la ValueModification à TOUTES ses cibles-sélecteur
        → l'armure de l'allié à portée l'inclut). Le porteur (self) est déjà couvert par son stat-mod EAGER
        (`applied_stat_mods`, dans `GetStat`) → l'aura n'ajoute QUE pour un défenseur allié DISTINCT (pas de
        double-compte). `ctx` = {owner_id/pos/team/mult/level, def_id/def_pos/def_team/def_traits} fourni par
        l'agrégateur `aura_fixed_armor_bonus_for_defense`. SYMÉTRIQUE défenseur de `create_aura_attack_bonus`
        (attaquant). Défaut None = pas d'aura."""
        return None

    def create_aura_attack_damage_malus_for_enemy(self, ctx: Mapping | None = None) -> EffectBonus | None:
        """Contribution AURA %-DÉGÂT projetée sur un ENNEMI ATTAQUANT à portée (l'effet est possédé par une
        unité, se projette sur les ENNEMIS environnants qui subissent un malus sur LEUR propre attaque —
        natif : effet à `CreateEffectDamageBonusForAttack(OwnerIsActor & ...)` + `CreateTargetSelector` =
        `SurroundingEnemies(range)`, ex. `ShadowInTheWarp_LessDmg_Effect` IdunBattle.Entities.Effects.Loki.ShadowInTheWarp_LessDmg_Effect$$CreateEffectDamageBonusForAttack/IdunBattle.Entities.Effects.Loki.ShadowInTheWarp_LessDmg_Effect$$CreateTargetSelector = -25%
        Psychic). `ctx` = {owner_id/pos/team, att_id/att_pos/att_team, damage_profile} fourni par
        l'agrégateur `aura_attack_damage_malus_from_enemies`. Défaut None = pas d'aura."""
        return None

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        """Contribution AURA DÉGÂT projetée sur un ALLIÉ ATTAQUANT à portée (l'effet est possédé par une
        unité et BONIFIE le dégât que ses ALLIÉS environnants INFLIGENT — natif : effet à
        `CreateEffectDamageBonusForAttack(OwnerIsCaster & ...)` + `CreateTargetSelector` = `AdjacentFriends
        + UnitsWithTrait(...)`, ex. `BeaconOfRage_FriendlyExtraDamageEffect` IdunBattle.Entities.Effects.Loki.BeaconOfRage_FriendlyExtraDamageEffect$$CreateEffectDamageBonusForAttack : +50% du bonus rage
        FLAT aux attaques MÊLÉE des amis Chaos adjacents d'Azkor, #191 ; `ConquerorImperativeEffect` IdunBattle.Entities.Effects.Loki.ConquerorImperativeEffect$$CreateDamageModifier :
        +extraDmg FLAT aux amis Mechanical adjacents vs cible à armure réduite, #23). `ctx` = {owner_id/pos/team,
        att_id/att_pos/att_team, att_grand_alliance, att_traits, is_melee, target_armor_reduced} fourni par
        l'agrégateur `aura_attack_damage_bonus_from_allies` (les gates lisent le sous-ensemble pertinent :
        BeaconOfRage → att_grand_alliance+is_melee ; Conqueror → att_traits+target_armor_reduced). SYMÉTRIQUE
        ALLIÉ de `create_aura_attack_damage_malus_for_enemy`. Défaut None = pas d'aura."""
        return None

    def create_aura_defense_damage_malus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        """Contribution AURA %-DÉGÂT projetée sur une CIBLE alliée du porteur à portée (l'effet est possédé
        par une unité et RÉDUIT le dégât que ses ALLIÉS environnants REÇOIVENT — natif : effet EffectWithTarget
        à `CreateEffectDamageMalusForDefense(OwnerIsTarget & DamageProfileIs(...))` + `CreateTargetSelector` =
        `SurroundingFriends(range, exclut self)`, évalué state-wide par `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction (boucle « TOUS les EffectWithTarget actifs × leurs cibles », cf. case-68) — ex.
        `DaughterOfTheAbyss_FriendlyDmgReductionPctEffect` IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_FriendlyDmgReductionPctEffect$$CreateEffectDamageMalusForDefense : -dmgReductionPct% Psychic aux amis
        dans le rayon 2 d'Atlacoya (#184). La même boucle sert aussi les effets qui AUGMENTENT le dégât reçu
        par les ENNEMIS du porteur à portée (ex. `DaughterOfTheAbyss_ExtraDamagePctEffect` IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_ExtraDamagePctEffect$$CreateEffectDamageBonusForAttack :
        +extraDmgPct% aux Psykers ennemis, selector IdunBattle.Entities.Effects.Loki.DaughterOfTheAbyss_ExtraDamagePctEffect$$CreateTargetSelector `SurroundingEnemies+UnitsWithTrait(0x3ea)`).
        `ctx` = {owner_id/pos/team, tgt_id, t_pos, tgt_team, tgt_traits, damage_profile} fourni par
        l'agrégateur `aura_defense_damage_malus_from_units`. Défaut None = pas d'aura."""
        return None

    def create_effect_crit_chance_bonus_for_attack(self) -> int | None:
        """Bonus de CHANCE de crit (%) — couche calc-time SÉPARÉE de `GetStat(9)`, sommée dans
        `IdunBattle.Core.Services.DamagePrediction$$GetCritChanceBonusFromEffects puis ajoutée à GetStat(9) dans
        `RollCritical` (cc = clamp(GetStat(9)+Σbonus, 0, 100)). Distinct des effets StatModification
        sur la crit-chance (eux DANS GetStat) → pas de double-compte. Défaut None = pas de bonus."""
        return None

    def create_effect_piercing_bonus_for_attack(self, ctx: Mapping | None = None) -> "int | None":
        """`<Effect>.CreatePiercingBonusForAttack` — contribution ADDITIVE au **ratio de perçage** du coup
        courant (`IdunBattle.Entities.Effects.BaseEffect$$PiercingBonusForAttack` : le cache d'`EffectBonus`
        est évalué contre les `entities` du coup, `ForAddition` → +montant / `ForSubtraction` → −montant),
        consommée par `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio`
        (`Min(100, Max(base>0, dirPierce + extraPierce + <ces bonus> + basePiercingRatio))`).

        `ctx` = contexte du coup fourni par l'agrégateur `piercing_bonus_from_effects` :
        `{owner_id, att_id, ability_type, target_traits, owner_ctx, is_ranged, is_overwatch,
        unit_ctx_of}` — de quoi évaluer les gates natifs `get_OwnerIsCaster` (owner_id == att_id),
        `CurrentAbilityIs(<abilityOrEffect>)`, `HasTrait(target, …)` et la disjonction
        `IsRangedAttack | IsOverwatchAttack` (Hailstrike_ExtraPierce). `is_ranged` suit la convention
        tri-état #106 (None = nature non threadée ⇒ les DEUX gates se taisent) ; `unit_ctx_of` =
        résolveur `unit_id -> UnitContext` (mirror `GetAbilityState(effect)` quand la SOURCE de l'effet
        n'est pas son porteur). Défaut None = pas de contribution (la quasi-totalité des effets)."""
        return None

    def create_effect_crit_damage_bonus_for_attack(self) -> int | None:
        """Bonus de DÉGÂT de crit — couche calc-time SÉPARÉE de `GetStat(10)`, sommée dans
        `IdunBattle.Core.Services.DamagePrediction$$GetCritDamageBonusFromEffects puis ajoutée à GetStat(10) dans
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

        RE : `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction itère les effets de la cible et appelle
        cette méthode (interface effet, slot 0x1a) sur chacun → accumule un `DamageModifiers` (%-list).
        La famille `ADamageDefenseModifierAbilityEffect` (CloudOfFlies/ContemptuousDisregard/ForwardObservers/
        HuntersInstincts/… IdunBattle.Entities.Effects.ADamageDefenseModifierAbilityEffect$$CreateEffectDamageMalusForDefense→IdunBattle.Entities.Effects.BaseEffect$$DamageMalusForDefense) = `EffectBonus(PercentDecrease,
        ConfigVar(key))` gated (ex. ContemptuousDisregard IdunBattle.Entities.Effects.Loki.ContemptuousDisregard_DamageReductionEffect$$CreateEffectDamageMalusForDefense : OwnerIsTarget & HasUsedActiveAbilityThisTurn
        → ConfigVar 0x46). Défaut None = effet sans réduction défensive (dégradation fidèle)."""
        return None

    def create_piercing_bonus_for_attack(self, damage_profile: str | None = None,
                                         is_melee: bool | None = None) -> EffectBonus | None:
        """`<Effect>.CreatePiercingBonusForAttack` — slot d'interface DISTINCT de
        `CreateEffectDamageBonusForAttack` : il alimente l'axe PERCAGE (`DamageModifiers` @+0x20), PAS le
        scalaire degat. Mirror : `EffectBonus.ForPiercing(trigger, montant)`
        (`IdunBattle.Entities.Effects.EffectBonus$$ForPiercing`).

        Porte ici pour la variante **OwnerIsTarget** (l'effet vit sur la VICTIME et bonifie le percage de
        QUI l'attaque) : `IdunBattle.Entities.Effects.Loki.Supercharge_ExtraPiercingEffect$$CreatePiercingBonusForAttack`
        = `ForPiercing(DamageProfileIs(GetDamageProfile(config)) & get_OwnerIsTarget,
        ConfigVar(0x3f=extraPierceRatio))`. Agrege par `build_defender_modifiers_from_effects` (boucle des
        effets de la CIBLE) puis fusionne dans le percage effectif par
        `AttackDamageOperation._apply_defender_flat_reductions`.

        `damage_profile` = NOM du profil du coup (gate `DamageProfileIs`) ; `is_melee` = nature du coup
        (aucun call-site porte ne s'en sert encore). Defaut None = pas de bonus de percage."""
        return None

    def create_effect_block_source_for_defense(self, defender_fixed_armor: int = 0,
                                               defender_attack: int = 0):
        """`<Effect>.CreateAddBlockEffectBehaviour`/`AddExtraBlockEffectToOwner` IdunBattleLogic.Entities.Abilities.Triggered.Loki.BeastSlayerAbility$$CreateAddBlockEffectBehaviour — source de
        BLOCK SUPPLEMENTAIRE possedee par la CIBLE (defenseur), AJOUTEE a la chaine
        `apply_random_block_damage` EN PLUS du block de base (scalaire `GetStat(7/8)`). Renvoie un
        `BlockSource(chance, amount)` ou None (defaut). Ex. BeastSlayer IdunBattleLogic.Entities.Abilities.Triggered.Loki.BeastSlayerAbility$$CreateAddBlockEffectBehaviour :
        chance=`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BeastSlayerAbility$$GetBlockChance`=beastSlayerBlockChance ; amount=`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BeastSlayerAbility$$GetBlockDamage`=
        blockDmgPct% du FixedArmor COURANT du defenseur. Ces entrees sont ABSENTES du scalaire GetStat(7/8)
        (verifie live 2026-07-09 : orksNob blockChance=0 alors que BeastSlayer donne +10%) -> le natif les
        tient dans `GetMultiValueStat(7)` (`IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances`). `defender_fixed_armor` =
        FixedArmor courant de la CIBLE (pour les sources dont l'amount depend de l'armure). #72.
        `defender_attack` = stat Attack COURANTE de la CIBLE (sources type Daemon_ExtraBlock, #54A)."""
        return None

    def get_armor_penetration(self, is_normal_attack: bool = True) -> int | None:
        """`<Effect>.IgnoreArmor` — pénétration d'armure (axe armure : armor_eff = max(armure − pén, 0)).
        `is_normal_attack` : certaines pénétrations sont gated attaque normale (i2 PowerTrip
        « NORMAL attacks ignore X Armour » — GROUND TRUTH step-13 : DakkaDakkaDakka (spéciale) du même
        porteur ne bénéficie PAS des 499 de pénétration, per-coup natif 404/728 vs 78 = armure pleine)."""
        return None

    def additional_hit_groups(self, ctx: Mapping | None = None) -> "list[dict] | None":
        """`<Effect>.CreateAdditionalHits` (`IdunBattle.Entities.Effects.EffectAdditionalHits$$Create`) — coups ADDITIONNELS
        HETEROGENES a degat/profil PROPRE ajoutes a l'attaque du PORTEUR (trigger natif OwnerIsActor/
        OwnerIsCaster, evalue ; +gate nature d'attaque eventuel via `ctx["is_melee"]`, ex. FoulInfusion
        IsMeleeAttack). Renvoie une liste de groupes `{count, min, max, profile}` — `count` coups de
        degat [min,max] (RandomAmount = plage directe, PAS le spread ±20% de l'arme) — OU
        `{count, amount, profile}` (amount SEUL = ConfigVar : le pipeline applique le spread ±20%).
        A materialiser APRES les coups d'arme dans la MEME chaine prev-threadee (overkill continu).
        Defaut None = pas de coups additionnels. Ex. `SquigHound_AdditionalHits` = 2 coups
        [minDmg,maxDmg] profil Physical."""
        return None

    def create_aura_additional_hits_for_ally(self, ctx: Mapping) -> "dict | None":
        """`<Effect>.CreateAdditionalHits` + `CreateTargetSelector` (mold AURA, ex. ExplosiveMaladies
        IdunBattle.Entities.Effects.Loki.ExplosiveMaladies_ExtraRangedAttackEffect$$CreateAdditionalHits/IdunBattle.Entities.Effects.Loki.ExplosiveMaladies_ExtraMeleeAttackEffect$$CreateAdditionalHits + selecteur IdunBattle.Entities.Effects.Loki.ExplosiveMaladies_ExtraRangedAttackEffect$$CreateTargetSelector `AdjacentFriends(owner, 1)`) — coups additionnels
        projetes par un effet HOSTE SUR LE PORTEUR sur les attaques d'un ALLIE selectionne (adjacence
        re-evaluee a la TUILE CANDIDATE, modele #49/#153 : rien n'est poste sur le beneficiaire).
        `ctx` = {att_id, att_pos, att_team, att_faction, att_grand_alliance, att_traits, is_melee,
        owner_id, owner_pos, owner_team} (owner_* = le porteur ; att_traits = traits gameconfig de
        l'attaquant, gate Daemon d'InfernalPacts #202-B). Renvoie UN groupe `{count, amount|min/max,
        profile}` ou None (gates non satisfaites). Defaut None = pas d'aura additional-hits."""
        return None

    # ── stat-modification (famille AStatModifierEffect) ─────────────────────────────────────────────
    def get_stat_modification_stat(self) -> "int | None":
        """`IdunBattle.Entities.Effects.AStatModifierEffect$$GetStatModificationStat` — le **StatType** que CET effet
        modifie (natif : `EffectComponent+0x10`). `None` = l'effet n'est pas un StatModifier (défaut).
        Un effet StatModification écrit sa magnitude dans la **modification** du stat (part 5/9),
        attribuée à sa source, appliquée via `ChangeStat` (cf. `UnitStats.change_stat`)."""
        return None

    def get_stat_modification_amount(self) -> "int | None":
        """`IdunBattle.Entities.Effects.StaticStatModifierEffect$$GetStatModificationAmount` (natif : `EffectComponent+0x14`,
        fixe) / `IdunBattle.Entities.Effects.ADynamicStatModifierEffect$$GetStatModificationAmount` (calculé).
        Magnitude (delta additif) ajoutée à la modification du StatType de
        `get_stat_modification_stat`. `None`/0 = aucune (défaut). Un effet StatModification concret
        override les deux (StatType + magnitude, typiquement depuis sa config d'ability)."""
        return None

    def reverted_stats(self) -> "list":
        """StatTypes que `<Effect>.RevertInternal` annule quand l'effet est RETIRÉ (mirror des `ChangeStat`
        posés par `ApplyModification`, reverté par-source via la clé `stat_mod_source`). C'est la part DATA
        (côté `entities/`) que la feuille runner `RemoveEffect` lit pour exécuter le revert (`revert_change_stat`,
        côté `runner/`) — l'interface `get_stat_modification_stat` est SINGULIÈRE et ne couvre pas un effet
        multi-stat (ex. ActOfFaith = crit-chance ET crit-damage), d'où la liste.

        DÉFAUT = le stat de `get_stat_modification_stat()` (mirror EXACT de la paire native
        `IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification` /
        `IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification` : les DEUX construisent leur
        `Position(stat, part)` depuis le MÊME `(**vtable+0x728)` = `GetStatModification()`, seule la `part`
        change — 5/9 à l'apply, 6 au revert). Autrement dit un `AStatModifierEffect` reverte TOUJOURS le stat
        qu'il modifie ; il n'y a pas de famille « modifie mais ne reverte pas » côté natif. `[]` (défaut
        effectif) pour tout effet non-StatModifier."""
        st = self.get_stat_modification_stat()
        return [] if st is None else [int(st)]

    def overridden_stats(self) -> "list":
        """Part DATA d'un `ApplyInternal` qui OVERRIDE des stats du porteur (part 7, `ChangeStat` mode 4)
        aux valeurs **CURRENT du PARENT** du porteur — cas `MV71SniperDroneSquad_InitialDmgEffect
        IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$ApplyInternal` (4 stats). La couche runner (`AddEffectOperation._apply_stat_overrides`) SNAPSHOTE la
        valeur du parent (= `eff.source`, mirror `GetParentUnit`) et exécute `apply_stat_override`
        (part 7 → SetOverride) ; le retrait exécute `remove_stat_override` (part 8, mirror `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$RevertInternal` → ResetStat ×N). Défaut `[]` = pas d'override."""
        return []

    def ability_modifications(self) -> "list":
        """Part DATA d'un `ApplyInternal` qui ecrit des **modifications de constantes d'ABILITY** sur une
        unite (et NON une stat) — natif `IdunBattle.Operations.OperationProcessor$$AddUnitActiveAbilityModification`
        -> `IdunBattle.Operations.AddUnitActiveAbilityModificationOperation$$Execute` ->
        `IdunBattle.Entities.Components.ActiveAbilityModificationsComponent$$Add(key, delta)`.

        Rend une liste de `(key, delta)` ou `key` = l'index de constante d'ability (`AbilityVarOrConst`,
        ex. `0x10` = nrOfSummons, `0x16` = range) et `delta` = le montant ADDITIF. Le `RevertInternal`
        natif rejoue LES MEMES appels en `-delta` -> la couche runner reverte en niant cette liste (pas
        de table separee). Defaut `[]` = l'effet n'ecrit aucune modification d'ability.

        Unique porteur du build : `IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect` (0x426)."""
        return []

    def ability_modifications_target_selector(self):
        """`<Effect>.CreateTargetSelector` — le selecteur des entites sur lesquelles `ApplyInternal`
        ecrit ses `ability_modifications` (natif : `ApplyInternal(this, .., target, ..)` est appele PAR
        CIBLE rendue par ce selecteur). `None` (defaut) = le PORTEUR lui-meme.

        `IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect$$CreateTargetSelector` = `Parent(Self@0x148)`
        -> l'effet est PORTE par Kell mais MODIFIE son parent (Creed)."""
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
